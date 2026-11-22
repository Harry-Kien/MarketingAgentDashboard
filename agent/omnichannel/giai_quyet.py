"""
Giải quyết hội thoại, mở lại khi khách nhắn tiếp, và khảo sát CSAT.

LỖ ĐO ĐƯỢC 15.10.2026
---------------------
Luồng native KHÔNG có thao tác "đã giải quyết" nào. `resolved_at` không bao
giờ được ghi, nên bộ canh SLA (`sla.py`) coi MỌI hội thoại có hạn giải quyết
là trễ — sớm muộn cái nào cũng thành `resolution_breached`. Một con số sai
trên báo cáo hiệu suất của từng nhân viên, và không gì báo nó sai.

CSAT HỎI SAU KHI GIẢI QUYẾT, ĐỌC TRƯỚC KHI AGENT TRẢ LỜI
-------------------------------------------------------
Khách trả lời "5" thì tin ấy là ĐIỂM, không phải câu hỏi mới — không được
để agent trả lời "Dạ 5 là gì ạ?". Chỉ một tin gồm đúng một chữ số 1–5
(cho phép thêm chữ "sao"), trong 24 giờ sau khi hỏi, mới tính là điểm.
"""
from __future__ import annotations

import re
import time
from typing import Any
from uuid import UUID

from agent import cau_hinh_dong, db
from agent.channels.base import THREAD_NHOM
from agent.core import cong_viec, thong_bao_noi_bo
from agent.omnichannel.sla_gio import bieu_thuc_han, gio_sla

CAU_HOI = ("Dạ shop cảm ơn anh/chị đã nhắn ạ. Anh/chị chấm giúp shop mức hài lòng "
           "từ 1 đến 5 nhé (5 là rất hài lòng) — chỉ cần nhắn một con số ạ.")
CAM_ON = "Dạ shop cảm ơn anh/chị đã đánh giá ạ!"
GIO_CHO = 24
_DIEM = re.compile(r"^\s*([1-5])\s*(sao|⭐)?\s*[.!]?\s*$", re.IGNORECASE)


class ConversationHasPendingTasksError(RuntimeError):
    """Conversation còn công việc phải đóng trước khi Resolve."""

    def __init__(self, tasks: list[dict[str, Any]]) -> None:
        self.tasks = tasks
        super().__init__("Không thể Resolve: còn công việc chưa hoàn tất.")

    def api_detail(self) -> dict[str, Any]:
        return {
            "code": "conversation_has_pending_tasks",
            "message": str(self),
            "pending_tasks": [
                {
                    "id": str(task["id"]),
                    "title": task["tieu_de"],
                    "state": task["trang_thai"],
                }
                for task in self.tasks
            ],
        }


async def kiem_tra_dieu_kien_resolve(conn: Any, cid: UUID) -> bool:
    """Khoá Conversation và xác nhận không còn Pending Action đang mở.

    Hàm nhận connection đang nằm trong transaction để cả manual Resolve và
    Auto Resolve dùng chung một chốt. Trả ``False`` nếu Conversation không
    tồn tại hoặc đã resolved; trả ``True`` nếu có thể tiếp tục Resolve.
    """
    conversation = await conn.fetchrow(
        "SELECT state FROM conversations WHERE id = $1 FOR UPDATE", cid
    )
    if conversation is None or conversation["state"] == "resolved":
        return False

    rows = await conn.fetch(
        """
        SELECT id, tieu_de, trang_thai
        FROM cong_viec
        WHERE conversation_id = $1
          AND trang_thai = ANY($2::text[])
          -- Việc tự sinh CŨ "khách cần người trả lời" (trước mục 14.2 —
          -- nay chuyển người chỉ sinh thông báo) KHÔNG chặn: nó chỉ để nhắc
          -- trả lời khách, và Resolve đóng nó ngay trong cùng giao dịch
          -- (`dong_viec_tu_sinh`). Việc xử lý ĐƠN (huỷ/đổi trả) cũng mang
          -- nguon='agent' nhưng có `loai_xu_ly_don` — việc đó PHẢI chặn.
          AND NOT (nguon = 'agent' AND loai_xu_ly_don IS NULL)
        ORDER BY tao_luc, id
        """,
        cid,
        list(cong_viec.CHUA_XONG),
    )
    if rows:
        raise ConversationHasPendingTasksError([dict(row) for row in rows])
    return True


def doc_diem(text: str) -> int | None:
    m = _DIEM.match(text or "")
    return int(m.group(1)) if m else None


async def _sau_khi_giai_quyet(conn, cid: UUID, chu_ky: int, han_xong) -> None:
    """
    Phần chung của mọi đường giải quyết (người bấm, worker tự giải quyết).
    Gọi TRONG giao dịch đã đổi trạng thái hội thoại.
    """
    # Kết thúc lượt giao đang mở: hội thoại đã xong, người ấy rảnh tay.
    await conn.execute(
        "UPDATE conversation_assignments SET ended_at = now() "
        "WHERE conversation_id = $1 AND ended_at IS NULL", cid)
    await dong_viec_tu_sinh(conn, cid)
    await thong_bao_noi_bo.ket_thuc_luot_chuyen_giao(conn, cid)
    # Ghi theo CHU KỲ SLA hiện tại — mỗi lượt phục vụ một dòng (migration 0039).
    await conn.execute(
        "INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at) "
        "SELECT $1, $3, 'resolution_met', $2::timestamptz "
        "WHERE $2::timestamptz IS NULL OR now() <= $2::timestamptz "
        "ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING",
        cid, han_xong, chu_ky)


async def dong_viec_tu_sinh(conn, cid: UUID) -> None:
    """
    Đóng việc "Khách cần người trả lời" (nguon='agent') đang mở của hội thoại.

    Từ mục 14.2 (21.11.2026) chuyển người KHÔNG sinh việc này nữa — chỉ sinh
    thông báo. Hàm còn lại để dọn việc cũ còn mở trong CSDL đang chạy: không
    có nó, việc cũ nằm mở mãi và chặn tự giải quyết.

    VÌ SAO PHẢI ĐÓNG Ở ĐÂY, TRONG CÙNG GIAO DỊCH
    ---------------------------------------------
    `idx_cong_viec_agent_mot_viec` cho mỗi hội thoại ĐÚNG MỘT việc tự sinh
    đang mở. Việc ấy không tự đóng khi người giải quyết hay trả lại cho
    agent, nên lần chuyển người SAU đụng chỉ mục, `ON CONFLICT DO NOTHING`
    nuốt nó — không việc mới, KHÔNG báo nhân viên, khách ngồi chờ mà không
    ai biết (rà soát 16.11.2026). Việc mở mãi cũng chặn luôn tự giải quyết
    (`_DIEU_KIEN_TU_GIAI_QUYET` loại hội thoại còn việc mở).

    Chỉ đóng việc nguon='agent': việc người giao tay ("gọi lại chị Hoa
    trước 5 giờ") vẫn phải làm dù hội thoại đã xong.

    KHÔNG đóng việc xử lý ĐƠN (`loai_xu_ly_don` khác NULL — khách xin huỷ,
    xin đổi/trả). Chúng cũng mang nguon='agent', nhưng phải được xác nhận
    kết quả và đối soát ERP (`cong_viec.xac_nhan_ket_qua_don`); đóng hộ ở
    đây là yêu cầu huỷ đơn của khách biến mất khi nhân viên trả lại cho agent.
    """
    # Lịch sử việc (0061) ghi lý do thay vì một dòng "Hệ thống đổi trạng thái"
    # không giải thích. Nơi gọi luôn ở trong giao dịch (xem docstring); kết
    # nối giả trong test đơn vị không có hàm này thì bỏ qua phần ghi chú.
    trong_gd = getattr(conn, "is_in_transaction", None)
    if callable(trong_gd) and trong_gd() is True:
        await conn.execute(
            "SELECT set_config('cong_viec.ghi_chu', $1, true)",
            "Tự đóng: hội thoại đã giải quyết hoặc trả lại cho agent")
    await conn.execute(
        "UPDATE cong_viec SET trang_thai = 'xong', xong_luc = now(), sua_luc = now() "
        "WHERE conversation_id = $1 AND nguon = 'agent' AND loai_xu_ly_don IS NULL "
        "AND trang_thai IN ('moi', 'dang_lam')", cid)


async def giai_quyet(cid: UUID, nguoi_id: UUID | None) -> dict[str, Any]:
    """Đánh dấu đã giải quyết. Trả `{da_truoc, csat}`; 404 do chỗ gọi lo."""
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if not await kiem_tra_dieu_kien_resolve(conn, cid):
                return {"da_truoc": True, "csat": None}
            r = await conn.fetchrow(
                "UPDATE conversations SET state = 'resolved', status = 'closed', "
                "outcome = 'resolved', resolved_at = now(), version = version + 1, "
                "updated_at = now() WHERE id = $1 AND state <> 'resolved' "
                "RETURNING id, assigned_to, resolution_due_at, external_id, sla_chu_ky, "
                "thread_type", cid)
            if r is None:
                return {"da_truoc": True, "csat": None}
            await _sau_khi_giai_quyet(conn, cid, r["sla_chu_ky"], r["resolution_due_at"])
    await db.log_event("conversation.resolved", ref_id=cid,
                       boi=str(nguoi_id) if nguoi_id else None, ly_do="nhân viên bấm")
    csat = await _hoi_csat(cid, str(r["external_id"]), r["assigned_to"] or nguoi_id,
                           la_nhom=r.get("thread_type") == THREAD_NHOM)
    return {"da_truoc": False, "csat": csat}


async def _hoi_csat(cid: UUID, external_id: str, nguoi_xu_ly: UUID | None,
                    *, la_nhom: bool = False) -> str:
    """Gửi câu hỏi CSAT nếu bật. Trả lý do bằng chữ — kể cả khi KHÔNG gửi."""
    if cau_hinh_dong.lay("CSAT_BAT") != "bat":
        return "tắt"
    if external_id.startswith("cmt:"):
        return "bình luận — không hỏi"
    # Nhóm Zalo: hỏi "anh/chị chấm mấy điểm" là hỏi cả nhóm, và câu "5" của
    # một thành viên bất kỳ sẽ thành điểm. Outbox cũng chặn tin máy vào nhóm
    # — kiểm ở đây trước để nút "Đã giải quyết" không nổ OutboundBlocked.
    if la_nhom:
        return "nhóm — không hỏi"
    from agent.omnichannel.cua_so_gui import xet_tin_nhan_vien
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository

    qd = await xet_tin_nhan_vien(cid)
    if not qd.duoc:
        # Ngoài cửa sổ: không hỏi được. Ghi lại để tỉ lệ phản hồi CSAT không
        # bị hiểu nhầm là "khách lười trả lời".
        await db.log_event("csat.khong_hoi", ref_id=cid, ly_do=qd.ly_do[:200])
        return "ngoài cửa sổ nhắn tin"
    await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid, role="system", text=CAU_HOI,
        idempotency_key=f"csat:{cid}:{int(time.time())}", the=qd.the)
    await db.execute("INSERT INTO csat (conversation_id, nguoi_xu_ly) VALUES ($1, $2)",
                     cid, nguoi_xu_ly)
    return "đã hỏi"


# Chọn chính sách SLA cho một hội thoại: đúng ưu tiên của nó (lui về
# `normal`), chính sách RIÊNG của kênh thắng chính sách chung.
#
# `ORDER BY (policy.account_id IS NOT NULL) DESC`, KHÔNG phải
# `(policy.account_id = c.account_id) DESC`: với chính sách chung vế so sánh
# ra NULL, và PostgreSQL xếp NULL LÊN ĐẦU khi DESC — chính sách chung luôn
# thắng, chính sách riêng của kênh chưa từng có hiệu lực (rà soát 12.11.2026).
_CHON_CHINH_SACH = """
    FROM sla_policies policy
    WHERE policy.active
      AND policy.priority IN (c.priority, 'normal')
      AND (policy.account_id = c.account_id OR policy.account_id IS NULL)
    ORDER BY (policy.account_id IS NOT NULL) DESC, (policy.priority = c.priority) DESC
    LIMIT 1"""


async def mo_lai_neu_da_giai_quyet(cid: UUID) -> bool:
    """
    Khách nhắn tiếp vào hội thoại đã giải quyết: mở lại, trả cho agent.

    Lượt phục vụ MỚI = CHU KỲ SLA MỚI (DEV-01, migration 0039): số chu kỳ
    tăng, hạn tính lại từ bây giờ theo giờ làm việc, `first_responded_at` xoá
    để đo phản hồi của lượt này, và một sự kiện `started` cho chu kỳ mới.
    Sự kiện của chu kỳ cũ giữ nguyên — lịch sử không bị ghi đè.

    Trước 12.11.2026 hạn mới bị trigger `prevent_sla_deadline_reset` lặng lẽ
    đè về hạn CŨ: hội thoại vừa mở lại đã trễ SLA ngay giây đầu.

    Agent nhận lại — giống đường Chatwoot cũ (`open` → `auto`): hội thoại
    xong rồi thì không còn ai đang cầm.
    """
    from agent.config import settings

    if not settings.sla_chu_ky_khi_mo_lai:
        # Tắt chu kỳ SLA (mặc định): mở lại, giữ nguyên chu kỳ và hạn của
        # lượt đầu — đúng hành vi trước DEV-01 (trigger vẫn chặn đổi hạn
        # trong cùng chu kỳ). `first_responded_at` xoá để hộp thư biết lượt
        # này chưa ai trả lời.
        r = await db.fetchrow(
            "UPDATE conversations SET state = 'open', status = 'auto', mode = 'auto', "
            "outcome = NULL, resolved_at = NULL, first_responded_at = NULL, "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1 AND state = 'resolved' RETURNING id", cid)
        if r is not None:
            await _ghi_mo_lai(cid, chu_ky_moi=False)
        return r is not None

    sql = ("""
        WITH mo AS (
            UPDATE conversations c SET
                state = 'open', status = 'auto', mode = 'auto', outcome = NULL,
                resolved_at = NULL, first_responded_at = NULL,
                sla_chu_ky = c.sla_chu_ky + 1,
                first_response_due_at = (SELECT {han_dau} """ + _CHON_CHINH_SACH + """),
                resolution_due_at = (SELECT {han_xong} """ + _CHON_CHINH_SACH + """),
                version = c.version + 1, updated_at = now()
            WHERE c.id = $1 AND c.state = 'resolved'
            RETURNING c.id, c.sla_chu_ky, c.first_response_due_at, c.resolution_due_at
        ), ghi AS (
            INSERT INTO sla_events (conversation_id, chu_ky, kind, due_at, detail)
            SELECT id, sla_chu_ky, 'started', first_response_due_at,
                   jsonb_build_object('first_response_due_at', first_response_due_at,
                                      'resolution_due_at', resolution_due_at,
                                      'mo_lai', true)
            FROM mo WHERE first_response_due_at IS NOT NULL
            ON CONFLICT (conversation_id, chu_ky, kind) DO NOTHING
            RETURNING 1
        )
        SELECT count(*) AS n FROM mo
        """).replace("{han_dau}", bieu_thuc_han("first_response_minutes", 2, 3))            .replace("{han_xong}", bieu_thuc_han("resolution_minutes", 2, 3))
    r = await db.fetchrow(sql, cid, *gio_sla())
    if r and r["n"]:
        await _ghi_mo_lai(cid, chu_ky_moi=True)
    return bool(r and r["n"])


async def _ghi_mo_lai(cid: UUID, *, chu_ky_moi: bool) -> None:
    """
    Sự kiện `conversation.reopened` — số "mở lại" ở màn Phân tích đếm nó.

    Trước bản này mở lại không để dấu vết nào ngoài `sla_events.started`,
    mà dòng ấy chỉ có khi BẬT chu kỳ SLA (mặc định tắt): số hội thoại mở lại
    — chỉ báo "giải quyết chưa thật xong" — không đếm được.
    """
    await db.log_event("conversation.reopened", ref_id=cid, chu_ky_moi=chu_ky_moi)


# ---------------------------------------------------------------- tự giải quyết (DEV-05)

# Điều kiện để một hội thoại được TỰ giải quyết. Mỗi dòng là một lý do để
# KHÔNG đóng — đóng nhầm một hội thoại khách đang chờ là tệ hơn nhiều so với
# để một hội thoại xong rồi mở thêm vài giờ.
_DIEU_KIEN_TU_GIAI_QUYET = """
    c.state IN ('open', 'pending')
    -- Nhân viên đang cầm, hoặc đã chuyển người: người quyết định khi nào xong.
    AND c.mode <> 'human' AND c.status NOT IN ('escalated', 'closed')
    -- Nhàn rỗi thật: không tin nào, theo chiều nào, trong khoảng chờ.
    AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id
                    AND m.created_at > now() - make_interval(secs => $1))
    -- Tin cuối KHÔNG phải của khách: khách hỏi mà chưa ai trả lời là yêu
    -- cầu chưa được giải quyết, không phải hội thoại đã xong.
    AND (SELECT m.role FROM messages m WHERE m.conversation_id = c.id
         ORDER BY m.created_at DESC LIMIT 1) IN ('agent', 'staff', 'system')
    -- Bản nháp chờ duyệt, tin chưa gửi xong hoặc gửi hỏng: còn việc dở.
    AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id
                    AND m.delivery_status IN ('draft', 'queued', 'sending', 'failed', 'dead'))
    AND NOT EXISTS (SELECT 1 FROM outbox_jobs j WHERE j.conversation_id = c.id
                    AND j.status IN ('pending', 'retry', 'processing', 'dead'))
    -- Công việc đang mở gắn với hội thoại: có người đang phải làm gì đó.
    AND NOT EXISTS (SELECT 1 FROM cong_viec v WHERE v.conversation_id = c.id
                    AND v.trang_thai IN ('moi', 'dang_lam'))
    -- Đơn còn treo: chờ duyệt, chờ đồng bộ ERP, khách xin huỷ hay đổi/trả.
    AND NOT EXISTS (SELECT 1 FROM orders o WHERE o.conversation_id = c.id AND (
            o.trang_thai IN ('cho_duyet', 'cho_dong_bo')
         OR (o.yeu_cau_huy_luc IS NOT NULL AND o.trang_thai <> 'da_huy')
         OR (o.yeu_cau_doi_tra_luc IS NOT NULL AND o.trang_thai <> 'da_huy'
             AND o.yeu_cau_doi_tra_luc > now() - interval '14 days')))
"""


async def tu_giai_quyet_mot_luot(gio: float, gioi_han: int = 50) -> list[UUID]:
    """
    Giải quyết các hội thoại nhàn rỗi quá `gio` giờ. Trả danh sách id đã đóng.

    CHỌN VÀ ĐÓNG TRONG MỘT GIAO DỊCH, KHOÁ DÒNG
    -------------------------------------------
    Chọn xong mới đóng ở câu sau là để lọt khoảnh khắc khách vừa nhắn tin
    mới: hội thoại bị đóng ngay sau khi khách hỏi. `FOR UPDATE` giữ dòng
    hội thoại tới khi đóng xong; tin mới của khách cập nhật hội thoại nên
    phải chờ — và điều kiện được kiểm lại trên đúng dòng đã khoá.

    KHÔNG hỏi CSAT: hỏi "anh/chị chấm điểm" sau bốn giờ im lặng là làm phiền,
    và tỉ lệ trả lời thấp sẽ kéo sai số đo hài lòng của nhân viên.
    """
    if gio <= 0:
        return []
    da_dong: list[UUID] = []
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                f"""
                WITH chon AS (
                    SELECT c.id FROM conversations c
                    WHERE {_DIEU_KIEN_TU_GIAI_QUYET}
                    ORDER BY c.updated_at
                    LIMIT $2
                    FOR UPDATE OF c SKIP LOCKED
                )
                UPDATE conversations c SET
                    state = 'resolved', status = 'closed', outcome = 'resolved',
                    resolved_at = now(), version = c.version + 1, updated_at = now()
                FROM chon WHERE c.id = chon.id
                RETURNING c.id, c.account_id, c.resolution_due_at, c.sla_chu_ky
                """, float(gio) * 3600, int(gioi_han))
            for r in rows:
                await _sau_khi_giai_quyet(conn, r["id"], r["sla_chu_ky"], r["resolution_due_at"])
                await conn.execute(
                    "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
                    "VALUES ($1, 'conversation.updated', $2, $3)",
                    r["account_id"], r["id"], {"tu_giai_quyet": True})
                da_dong.append(r["id"])
    for cid in da_dong:
        await db.log_event("conversation.resolved", ref_id=cid, boi=None, tu_dong=True,
                           ly_do=f"nhàn rỗi quá {gio:g} giờ, không còn việc dở")
    return da_dong


async def heartbeat_tu_giai_quyet(worker_id: str) -> None:
    await db.execute(
        "INSERT INTO worker_heartbeats (worker_name, worker_id, last_seen_at, detail) "
        "VALUES ('auto-resolve', $1, now(), '{}') "
        "ON CONFLICT (worker_name) DO UPDATE SET worker_id = excluded.worker_id, "
        "last_seen_at = excluded.last_seen_at", worker_id)


async def tu_giai_quyet_loop(*, worker_id: str, moi_giay: float = 300.0,
                             log_error=None) -> None:
    """Vòng nền: mỗi `moi_giay` một lượt. Không bao giờ chết vì một lượt hỏng."""
    import asyncio

    from agent.config import settings

    while True:
        try:
            await tu_giai_quyet_mot_luot(float(settings.tu_giai_quyet_sau_gio))
            await heartbeat_tu_giai_quyet(worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng nền phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        await asyncio.sleep(moi_giay)


async def ghi_diem_neu_la_csat(cid: UUID, text: str) -> bool:
    """
    Tin khách là điểm CSAT đang chờ? Ghi điểm, cảm ơn, đóng lại. True = đã xử lý.

    Gọi SAU khi tin đã lưu và TRƯỚC khi agent trả lời.
    """
    diem = doc_diem(text)
    if diem is None:
        return False
    # Phiếu chỉ còn hiệu lực khi câu hỏi CSAT là điều CUỐI CÙNG shop nói với
    # khách. Đo được 16.11.2026: hỏi CSAT → khách nhắn chuyện khác (mở lại)
    # → AI hỏi "chị lấy mấy hộp ạ?" → tự giải quyết → khách trả lời "2" —
    # và "2" thành điểm hài lòng 2/5 cho nhân viên, còn câu trả lời của
    # khách thì mất. Có tin shop gửi SAU phiếu (agent, nhân viên, hay tin hệ
    # thống khác) nghĩa là cuộc nói chuyện đã đi tiếp: con số khách nhắn
    # đang trả lời câu khác, không phải câu hỏi CSAT.
    r = await db.fetchrow(
        f"UPDATE csat SET diem = $2, tra_loi_luc = now() WHERE id = ("
        f"  SELECT p.id FROM csat p WHERE p.conversation_id = $1 AND p.diem IS NULL "
        f"  AND p.gui_luc > now() - interval '{GIO_CHO} hours' "
        f"  AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = $1 "
        f"      AND m.role IN ('agent', 'staff', 'system') AND m.created_at > p.gui_luc "
        f"      AND m.content IS DISTINCT FROM $3 "
        # Bản nháp chưa duyệt / tin đã huỷ: khách chưa từng thấy, không
        # làm cuộc nói chuyện đi tiếp.
        f"      AND coalesce(m.delivery_status, '') NOT IN ('draft', 'cancelled')) "
        f"  ORDER BY p.gui_luc DESC LIMIT 1) RETURNING id", cid, diem, CAU_HOI)
    if r is None:
        return False
    # Điểm không phải yêu cầu mới: hội thoại trở về trạng thái đã giải quyết.
    await db.execute(
        "UPDATE conversations SET state = 'resolved', status = 'closed', "
        "outcome = 'resolved', resolved_at = now(), updated_at = now() WHERE id = $1", cid)
    await db.log_event("csat.diem", ref_id=cid, diem=diem)
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository
    try:
        await OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=cid, role="system", text=CAM_ON,
            idempotency_key=f"csat-cam-on:{r['id']}")
    except Exception:  # noqa: BLE001 — điểm đã ghi; lời cảm ơn hỏng thì ghi lại
        await db.log_event("csat.cam_on_that_bai", ref_id=cid)
    return True
