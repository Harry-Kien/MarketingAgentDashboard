"""
Thông báo NỘI BỘ: cái chuông trên đầu dashboard.

VÌ SAO KHỐI NÀY TỒN TẠI
------------------------
Những chuyện cần người — AI chuyển hội thoại, được giao hội thoại, bản nháp
chờ duyệt, được giao việc, SLA sắp trễ — trước bản này chỉ hiện ra nếu
người trực tình cờ mở đúng màn. "Tình cờ" không phải một cơ chế.

Và mỗi lần AI chuyển giao lại đẻ một công việc "Khách cần người trả lời":
trùng nghiệp vụ với chính hội thoại đang nằm trong hàng chờ người, nên màn
Công việc đầy việc không phải việc, còn việc thật (huỷ đơn, giao hàng hỏng)
nằm lẫn trong đó. Chủ dự án chốt (mục 14.2): chuyển giao là THÔNG BÁO, công
việc chỉ dành cho việc thật.

THÔNG BÁO CHỈ NHẮC VÀ DẪN ĐƯỜNG
-------------------------------
Đọc một thông báo KHÔNG hoàn tất việc nào, KHÔNG duyệt bản nháp nào, KHÔNG
nhận hội thoại nào. Đánh dấu đã đọc chỉ đổi `da_doc_luc` của chính dòng ấy.
Thông báo cũng không bao giờ đi tới khách: không có đường nào từ bảng này
ra outbox.

AI NHẬN (`nguoi_nhan_hoi_thoai`)
-------------------------------
  1. Hội thoại đã giao cho ai (tài khoản không bị khoá) -> CHỈ người ấy.
     Người khác cùng kênh không cần biết; báo họ là dạy họ phớt lờ chuông.
  2. Chưa giao -> thành viên KÊNH của hội thoại (`account_memberships`) có
     quyền đúng việc (`hoi_thoai.nhan` cho chuyển giao và SLA,
     `hoi_thoai.tra_loi` cho bản nháp, `don.sua` cho đơn chờ duyệt).
  3. Kênh không có ai như thế -> người QUẢN LÝ (`hoi_thoai.xem_tat_ca`).
     Không lui về đây thì kênh chưa phân người là kênh mà chuông không reo
     ở đâu cả — đúng kiểu hỏng im lặng của repo này.
  4. SLA (sắp trễ / đã trễ) thì người quản lý LUÔN được báo thêm: trễ hạn
     là chuyện của người điều phối, không chỉ của người đang cầm.
  Vai trò `Quản trị` có mọi quyền (tính từ mã — xem `xac_thuc.doc_phien`),
  nên được tính như người có quyền ở mọi bước trên.

KHÔNG BAO GIỜ NÉM VÀO NƠI GỌI
------------------------------
Mọi hàm `bao_*` chạy trên đường xử lý tin khách hoặc trong vòng nền. Một
ngoại lệ ở đây làm chết cả lượt trả lời khách — để cứu một dòng thông báo ta
đánh mất câu trả lời. Nhưng cũng KHÔNG im lặng: hỏng thì ghi nhật ký mức
LỖI, và hội thoại không có ai nhận thông báo thì ghi CẢNH BÁO.
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from agent import db

log = logging.getLogger("agent.thong_bao")

# Loại -> nhãn hiện trên dashboard. CHECK ở migration (0055, mở rộng ở 0061)
# giữ đúng tập này; test canh hai nơi không lệch nhau.
LOAI: dict[str, str] = {
    "duoc_giao_hoi_thoai": "Được giao hội thoại",
    "ai_chuyen_giao": "AI chuyển giao",
    "can_duyet": "Cần duyệt",
    "duoc_giao_viec": "Được giao việc",
    "sla_sap_tre": "SLA sắp trễ",
    "sla_tre": "SLA đã trễ",
    "viec_chua_giao": "Việc chưa phân công",
    "viec_huy": "Việc bị hủy",
    "viec_qua_han": "Việc quá hạn",
}

_HUONG_DAN: dict[str, str] = {
    "ai_chuyen_giao": "Mở hội thoại để tiếp quản và trả lời khách.",
    "duoc_giao_hoi_thoai": "Mở hội thoại để kiểm tra và phản hồi khách.",
    "can_duyet": "Mở hội thoại hoặc màn đơn hàng để duyệt trước khi gửi.",
    "duoc_giao_viec": "Mở công việc để xem chi tiết và xử lý.",
    "sla_sap_tre": "Ưu tiên kiểm tra và phản hồi khách trước khi quá hạn SLA.",
    "sla_tre": "Hội thoại đã quá hạn SLA — ưu tiên xử lý ngay.",
    "viec_chua_giao": "Phân công nhân viên phụ trách cho công việc này.",
    "viec_huy": "Kiểm tra lại lý do hủy công việc nếu cần.",
    "viec_qua_han": "Mở công việc để xử lý hoặc cập nhật tiến độ.",
}

_MA_KY_THUAT_RE = re.compile(
    r"\s*\((?:tool_calls|tool_use|malformed_function_call|max_tokens|length|safety|recitation|content_filter|refusal|\d+(?:\.\d+)?)\)\s*",
    re.IGNORECASE,
)


def chuan_hoa_noi_dung_thong_bao(loai: str, noi_dung: str | None) -> str:
    """Chuẩn hóa nội dung thông báo sang tiếng Việt rõ ràng cho nhân viên.

    Loại bỏ mã kỹ thuật thô (`tool_calls`, `tool_use`, điểm độ tin cậy thô...)
    nhưng giữ đúng bản chất vấn đề: lỗi kỹ thuật / thiếu căn cứ / cần tiếp quản.
    Dữ liệu kỹ thuật thô vẫn được giữ nguyên trong `events` và `dau_vet_ai`.
    """
    goc = " ".join(str(noi_dung or "").split())
    if loai != "ai_chuyen_giao":
        return goc
    low = goc.lower()
    if any(k in low for k in ("tool_calls", "tool_use", "malformed_function_call", "gọi công cụ")):
        return "AI gặp lỗi kỹ thuật khi gọi công cụ hỗ trợ — chưa thể tự trả lời khách."
    if any(k in low for k in ("max_tokens", "giới hạn độ dài")):
        return "AI phản hồi bị gián đoạn do vượt giới hạn độ dài — cần nhân viên trả lời tiếp."
    if "safety" in low or "content_filter" in low or "recitation" in low:
        return "Nội dung cần nhân viên kiểm tra an toàn và phản hồi trực tiếp cho khách."
    if "model dừng bất thường" in low or "lỗi kỹ thuật" in low:
        return "AI gặp sự cố kỹ thuật khi xử lý câu trả lời — cần nhân viên tiếp quản."
    if "độ tin cậy thấp" in low or "không đủ căn cứ" in low or "chưa đủ căn cứ" in low:
        return "AI chưa đủ căn cứ rõ ràng từ tài liệu — cần nhân viên kiểm tra và phản hồi khách."
    sach = _MA_KY_THUAT_RE.sub(" ", goc).strip(" .—-")
    return sach or "Hội thoại cần nhân viên kiểm tra và tiếp quản."

# Quyền "người quản lý" — người được báo khi kênh không có ai, và luôn được
# báo khi SLA trễ. Dùng lại đúng quyền đã nói "thấy mọi kênh": người không
# thấy hội thoại thì báo cho họ chỉ là một dòng bấm vào ra 404.
QUYEN_QUAN_LY = "hoi_thoai.xem_tat_ca"

TEN_KENH = {
    "zalo_personal": "Zalo cá nhân", "zalo_oa": "Zalo OA",
    "facebook": "Facebook", "instagram": "Instagram",
    "whatsapp": "WhatsApp", "webchat": "Chat web",
}

# Người có quyền X (hoặc vai trò Quản trị), không bị khoá. `coalesce` vì
# LEFT JOIN vào `vai_tro_quyen` cho NULL ở vai trò không có dòng quyền nào,
# và `bool_or` toàn NULL ra NULL chứ không ra false.
_SQL_CO_QUYEN = """
    SELECT n.id
    FROM nguoi_dung n
    JOIN nguoi_dung_vai_tro x ON x.nguoi_dung_id = n.id
    JOIN vai_tro vt ON vt.id = x.vai_tro_id AND vt.dang_dung
    LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id
    WHERE NOT n.khoa
    GROUP BY n.id
    HAVING coalesce(bool_or(vq.quyen = $1 OR (vt.he_thong AND vt.ten = 'Quản trị')), false)
"""


@asynccontextmanager
async def _ket_noi(conn: Any = None) -> AsyncIterator[Any]:
    if conn is not None:
        yield conn
        return
    async with db.pool().acquire() as moi:
        yield moi


def _ngan(chu: str | None, toi_da: int) -> str:
    chu = " ".join(str(chu or "").split())
    return chu if len(chu) <= toi_da else chu[: toi_da - 1] + "…"


def _uuid(x: Any) -> UUID:
    return x if isinstance(x, UUID) else UUID(str(x))


async def _nguoi_co_quyen(conn: Any, quyen: str) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(_SQL_CO_QUYEN, quyen)]


async def nguoi_nhan_hoi_thoai(
    conn: Any, conversation_id: UUID | str, *, quyen: str,
    them_quan_ly: bool = False,
) -> list[UUID]:
    """Ai được báo về hội thoại này — luật ở docstring đầu tệp."""
    cid = _uuid(conversation_id)
    c = await conn.fetchrow(
        "SELECT c.account_id, c.assigned_to, (n.id IS NOT NULL AND NOT n.khoa) AS giao_song "
        "FROM conversations c LEFT JOIN nguoi_dung n ON n.id = c.assigned_to "
        "WHERE c.id = $1", cid)
    if c is None:
        return []
    quan_ly: list[UUID] | None = None
    if c["assigned_to"] is not None and c["giao_song"]:
        chinh = [c["assigned_to"]]
    else:
        co_quyen = set(await _nguoi_co_quyen(conn, quyen))
        thanh_vien = {
            r["user_id"] for r in await conn.fetch(
                "SELECT user_id FROM account_memberships WHERE account_id = $1",
                c["account_id"])
        }
        chinh = sorted(co_quyen & thanh_vien, key=str)
        if not chinh:
            quan_ly = await _nguoi_co_quyen(conn, QUYEN_QUAN_LY)
            chinh = list(quan_ly)
    if them_quan_ly:
        if quan_ly is None:
            quan_ly = await _nguoi_co_quyen(conn, QUYEN_QUAN_LY)
        chinh = list(dict.fromkeys([*chinh, *quan_ly]))
    return chinh


async def _ghi(
    conn: Any, nguoi_nhan: Iterable[UUID], *, loai: str, tieu_de: str,
    noi_dung: str = "", conversation_id: UUID | None = None,
    cong_viec_id: UUID | None = None, order_id: UUID | None = None,
    khoa: str | None = None,
) -> int:
    """
    Chèn một dòng cho mỗi người nhận. Trả số dòng MỚI.

    Trùng khoá với một thông báo CHƯA ĐỌC thì không chèn dòng thứ hai mà đẩy
    dòng cũ lên đầu (`tao_luc = now()`) với nội dung mới: khách nhắn thêm vào
    hội thoại đang chờ duyệt thì người trực thấy nó mới, nhưng chuông không
    đếm thành mười.
    """
    if loai not in LOAI:
        raise ValueError(f"Loại thông báo lạ: {loai!r}")
    ids = list(dict.fromkeys(_uuid(x) for x in nguoi_nhan))
    if not ids:
        return 0
    rows = await conn.fetch(
        """
        INSERT INTO thong_bao (nguoi_nhan_id, loai, tieu_de, noi_dung,
                               conversation_id, cong_viec_id, order_id,
                               khoa_chong_trung)
        SELECT u, $2, $3, $4, $5, $6, $7, $8 FROM unnest($1::uuid[]) AS u
        ON CONFLICT (nguoi_nhan_id, khoa_chong_trung)
            WHERE da_doc_luc IS NULL AND khoa_chong_trung IS NOT NULL
        DO UPDATE SET tao_luc = now(), tieu_de = EXCLUDED.tieu_de,
                      noi_dung = EXCLUDED.noi_dung
        RETURNING (xmax = 0) AS moi
        """,
        ids, loai, _ngan(tieu_de, 200), _ngan(noi_dung, 500),
        conversation_id, cong_viec_id, order_id, khoa[:300] if khoa else None,
    )
    return sum(1 for r in rows if r["moi"])


def _loi(viec: str, ref: Any, exc: BaseException) -> None:
    log.error("KHÔNG tạo được thông báo %s (%s): %s: %s",
              viec, ref, type(exc).__name__, exc)


def _khong_ai_nhan(viec: str, ref: Any) -> None:
    log.warning("Thông báo %s (%s) không có ai nhận: không người được giao, "
                "không thành viên kênh có quyền, không người quản lý.", viec, ref)


# ---------------------------------------------------------------------------
#  Nguồn sinh thông báo. MỌI hàm dưới đây không ném.
# ---------------------------------------------------------------------------

async def bao_ai_chuyen_giao(
    conversation_id: UUID | str, *, ly_do: str, conn: Any = None,
) -> int:
    """
    AI (hoặc hệ thống thay AI: agent tắt, lỗi kỹ thuật, quy tắc tự động,
    tin nhóm) vừa chuyển hội thoại cho người.

    Thay cho việc tự sinh "Khách cần người trả lời" (mục 14.2). Cùng với
    thông báo, giữ tin báo NGOÀI dashboard (`canh_gac.bao_nhan_vien_nen`)
    như trước — nhưng chỉ khi có ít nhất một thông báo MỚI. Trước đây chốt
    "một việc mỗi hội thoại" làm việc chống dội cho tin báo ngoài; nay chốt
    "một thông báo chưa đọc mỗi người" làm thay: khách nhắn thêm mười tin
    vào hội thoại đã chuyển người không thành mười tin Telegram.
    """
    try:
        async with _ket_noi(conn) as c:
            nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="hoi_thoai.nhan")
            moi = await _ghi(
                c, nhan, loai="ai_chuyen_giao",
                tieu_de="AI chuyển hội thoại cho nhân viên",
                noi_dung=chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", ly_do),
                conversation_id=_uuid(conversation_id),
                khoa=f"ai_chuyen_giao:{_uuid(conversation_id)}",
            )
            kenh = await c.fetchval(
                "SELECT ca.channel FROM conversations cv "
                "LEFT JOIN channel_accounts ca ON ca.id = cv.account_id WHERE cv.id = $1",
                _uuid(conversation_id))
        if not nhan:
            _khong_ai_nhan("ai_chuyen_giao", conversation_id)
        if moi or not nhan:
            _bao_ngoai(kenh or "")
        return moi
    except Exception as exc:  # noqa: BLE001 — không làm chết lượt trả lời khách
        _loi("ai_chuyen_giao", conversation_id, exc)
        # Thông báo hỏng thì tin báo ngoài là đường DUY NHẤT còn lại để có
        # người biết — gửi, dù có thể trùng.
        _bao_ngoai("")
        return 0


def _bao_ngoai(kenh: str) -> None:
    """
    Tin báo NGOÀI dashboard (n8n / Telegram / Zalo bot). Chỉ nói KÊNH, không
    nói lý do hay lời khách: lý do chuyển người có thể là "mang thai", "bệnh
    da" — dữ liệu sức khoẻ theo Luật 91/2025, không đi sang bên thứ ba chỉ để
    báo "có việc".
    """
    try:
        from agent import canh_gac

        canh_gac.bao_nhan_vien_nen(
            "Khách cần người trả lời",
            f"Kênh {TEN_KENH.get(kenh, kenh or 'không rõ')}: agent đã chuyển hội thoại "
            "cho người. Mở dashboard → chuông thông báo hoặc Công việc → Tổng quan ca trực để nhận.")
    except Exception as exc:  # noqa: BLE001
        _loi("bao_ngoai", kenh, exc)


async def bao_duoc_giao_hoi_thoai(
    conversation_id: UUID | str, nguoi_nhan_id: UUID | str, *,
    boi: UUID | str | None = None, tu_dong: bool = False, conn: Any = None,
) -> int:
    """
    Hội thoại vừa được giao cho một người. Tự nhận (người giao = người nhận)
    thì KHÔNG báo: báo người ta về việc họ vừa tự bấm là tiếng ồn.
    """
    if boi is not None and str(boi) == str(nguoi_nhan_id):
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(nguoi_nhan_id)], loai="duoc_giao_hoi_thoai",
                tieu_de="Bạn được giao một hội thoại",
                noi_dung="Định tuyến tự động" if tu_dong else "Người điều phối giao",
                conversation_id=_uuid(conversation_id),
                khoa=f"duoc_giao:{_uuid(conversation_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("duoc_giao_hoi_thoai", conversation_id, exc)
        return 0


async def bao_can_duyet_nhap(conversation_id: UUID | str, *, conn: Any = None) -> int:
    """
    Chế độ Gợi ý: AI vừa soạn một bản nháp chờ người duyệt. Một thông báo
    CHƯA ĐỌC mỗi hội thoại mỗi người — AI soạn nháp cho từng tin khách.
    """
    try:
        async with _ket_noi(conn) as c:
            # `ai.duyet`, không `hoi_thoai.tra_loi`: chuông "cần duyệt" gửi
            # cho người KHÔNG bấm được nút Duyệt là chuông họ học cách bỏ qua.
            nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="ai.duyet")
            if not nhan:
                _khong_ai_nhan("can_duyet", conversation_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de="Bản nháp AI chờ duyệt",
                noi_dung="AI đã soạn câu trả lời, cần người duyệt trước khi gửi.",
                conversation_id=_uuid(conversation_id),
                khoa=f"can_duyet:{_uuid(conversation_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet", conversation_id, exc)
        return 0


async def bao_can_duyet_don(
    order_id: UUID | str, *, conversation_id: UUID | str | None, ma_don: str,
    conn: Any = None,
) -> int:
    """
    AI vừa lên một đơn vượt ngưỡng tự chốt — đơn nằm ở `cho_duyet` tới khi
    có người duyệt. Mã đơn là mã nội bộ của cửa hàng, không phải dữ liệu
    của khách.
    """
    try:
        async with _ket_noi(conn) as c:
            if conversation_id is not None:
                nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="don.sua")
            else:
                nhan = await _nguoi_co_quyen(c, "don.sua")
            if not nhan:
                _khong_ai_nhan("can_duyet_don", order_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de=f"Đơn {ma_don} chờ duyệt",
                noi_dung="AI đã lên đơn vượt ngưỡng tự chốt — cần người duyệt.",
                conversation_id=_uuid(conversation_id) if conversation_id else None,
                order_id=_uuid(order_id),
                khoa=f"can_duyet_don:{_uuid(order_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet_don", order_id, exc)
        return 0


async def nguoi_duyet_de_xuat(
    conn: Any, conversation_id: UUID | str, quyen: Iterable[str],
) -> list[UUID]:
    """
    Ai được báo về một đề xuất hành động của AI: người có ĐỦ các quyền duyệt
    (`ai.duyet` + quyền nghiệp vụ của hành động) và THẤY được hội thoại.

    Khác `nguoi_nhan_hoi_thoai`: người đang cầm hội thoại chưa chắc duyệt
    được (nhân viên mới trả lời được nhưng chưa được huỷ đơn). Báo người
    không bấm được Duyệt là dạy họ phớt lờ chuông — nên lọc theo quyền ở
    MỌI nhánh, kể cả nhánh người được giao.
    """
    cid = _uuid(conversation_id)
    co_du: set[UUID] | None = None
    for q in quyen:
        bo = set(await _nguoi_co_quyen(conn, q))
        co_du = bo if co_du is None else co_du & bo
    if not co_du:
        return []
    c = await conn.fetchrow(
        "SELECT account_id, assigned_to FROM conversations WHERE id = $1", cid)
    if c is None:
        return []
    thanh_vien = {r["user_id"] for r in await conn.fetch(
        "SELECT user_id FROM account_memberships WHERE account_id = $1", c["account_id"])}
    chinh = co_du & thanh_vien
    if c["assigned_to"] in co_du:
        chinh.add(c["assigned_to"])
    if not chinh:
        chinh = co_du & set(await _nguoi_co_quyen(conn, QUYEN_QUAN_LY))
    return sorted(chinh, key=str)


async def bao_can_duyet_de_xuat(
    conversation_id: UUID | str, de_xuat_id: UUID | str, *, tieu_de: str,
    quyen_thi_hanh: str | None, conn: Any = None,
) -> int:
    """
    AI vừa chuẩn bị một hành động cần duyệt (mục 17). Chỉ gắn HỘI THOẠI, không
    gắn đơn: bấm vào phải mở đúng hội thoại có thẻ đề xuất, không phải màn Đơn
    hàng (`_lien_ket` ưu tiên đơn nếu có).
    """
    try:
        async with _ket_noi(conn) as c:
            quyen = ["ai.duyet", *([quyen_thi_hanh] if quyen_thi_hanh else [])]
            nhan = await nguoi_duyet_de_xuat(c, conversation_id, quyen)
            if not nhan:
                _khong_ai_nhan("can_duyet_de_xuat", de_xuat_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de=f"AI đề xuất: {tieu_de}",
                noi_dung="AI đã chuẩn bị một hành động, cần người có thẩm quyền duyệt.",
                conversation_id=_uuid(conversation_id),
                khoa=f"can_duyet_de_xuat:{_uuid(de_xuat_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet_de_xuat", de_xuat_id, exc)
        return 0


async def bao_duoc_giao_viec(
    cong_viec_id: UUID | str, nguoi_nhan_id: UUID | str, *,
    boi: UUID | str | None, tieu_de_viec: str, conn: Any = None,
    chuyen: bool = False, tu_dong: bool = False,
) -> int:
    """
    Một việc vừa được giao (hoặc CHUYỂN từ người khác) cho người này. Tự giao
    cho mình thì không báo. Chuyển và giao mới cùng một loại chuông — với
    người nhận đều là "có việc mới của tôi" — chỉ khác tiêu đề, để họ biết
    việc này đã có người làm dở.
    """
    if boi is not None and str(boi) == str(nguoi_nhan_id):
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(nguoi_nhan_id)], loai="duoc_giao_viec",
                tieu_de="Bạn được chuyển một việc" if chuyen else "Bạn được giao một việc",
                noi_dung=tieu_de_viec + (" (phân công tự động)" if tu_dong else ""),
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"duoc_giao_viec:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("duoc_giao_viec", cong_viec_id, exc)
        return 0


async def nguoi_dieu_phoi_viec(conn: Any, cong_viec_id: UUID | str) -> list[UUID]:
    """
    Ai được báo về một việc CHƯA AI NHẬN: người có `cong_viec.giao` (hoặc
    Quản trị) THẤY được việc ấy — việc gắn hội thoại thì phải thuộc kênh hoặc
    thấy mọi kênh. Báo người không mở được việc là một dòng bấm vào ra 404,
    và tệ hơn là đưa tên khách kênh khác cho họ đọc.
    """
    from agent.core import cong_viec as cv

    rows = await conn.fetch(
        cv.SQL_VIEC_VA_QUYEN
        + f"SELECT q.id FROM quyen q, viec WHERE q.giao AND {cv.SQL_CUNG_KENH} ORDER BY q.id",
        _uuid(cong_viec_id))
    return [r["id"] for r in rows]


async def bao_viec_chua_giao(
    cong_viec_id: UUID | str, *, tieu_de_viec: str, ly_do: str = "",
    tru: UUID | str | None = None, conn: Any = None,
) -> int:
    """
    Việc ra đời (hoặc bị thu hồi người nhận) mà không ai nhận — "Chưa phân
    công" là danh sách không ai mở nếu không có chuông. `tru` = người vừa
    thao tác: họ biết rồi.
    """
    try:
        async with _ket_noi(conn) as c:
            nhan = [u for u in await nguoi_dieu_phoi_viec(c, cong_viec_id)
                    if tru is None or str(u) != str(tru)]
            if not nhan and tru is None:
                _khong_ai_nhan("viec_chua_giao", cong_viec_id)
            return await _ghi(
                c, nhan, loai="viec_chua_giao",
                tieu_de="Việc chưa phân công",
                noi_dung=tieu_de_viec + (f" — {ly_do}" if ly_do else ""),
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"viec_chua_giao:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_chua_giao", cong_viec_id, exc)
        return 0


async def bao_viec_huy(
    cong_viec_id: UUID | str, *, nguoi_nhan: Iterable[UUID | str | None],
    boi: UUID | str | None, tieu_de_viec: str, conn: Any = None,
) -> int:
    """
    Việc bị hủy: báo người đang làm và người đã tạo — trừ chính người hủy.
    Không báo thì người nhận tiếp tục gọi khách cho một việc đã bỏ.
    """
    ids = [x for x in nguoi_nhan if x is not None and (boi is None or str(x) != str(boi))]
    if not ids:
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(x) for x in ids], loai="viec_huy",
                tieu_de="Việc đã bị hủy", noi_dung=tieu_de_viec,
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"viec_huy:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_huy", cong_viec_id, exc)
        return 0


async def bao_viec_qua_han(
    cong_viec_id: UUID | str, *, nguoi_nhan_id: UUID | str | None,
    tieu_de_viec: str, conn: Any = None,
) -> int:
    """
    Việc chưa xong đã qua hạn: báo người đang làm; chưa ai làm thì báo
    người điều phối — việc quá hạn mà không có chủ là việc dễ rơi nhất.
    """
    try:
        async with _ket_noi(conn) as c:
            nhan = ([_uuid(nguoi_nhan_id)] if nguoi_nhan_id is not None
                    else await nguoi_dieu_phoi_viec(c, cong_viec_id))
            if not nhan:
                _khong_ai_nhan("viec_qua_han", cong_viec_id)
            return await _ghi(
                c, nhan, loai="viec_qua_han",
                tieu_de="Việc đã quá hạn" if nguoi_nhan_id else "Việc quá hạn chưa ai nhận",
                noi_dung=tieu_de_viec,
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"viec_qua_han:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_qua_han", cong_viec_id, exc)
        return 0


_SLA = {
    "first_response_warning": ("sla_sap_tre", "SLA sắp trễ: khách chưa được trả lời"),
    "first_response_breached": ("sla_tre", "SLA đã trễ: quá hạn phản hồi đầu"),
    # Cảnh báo hạn giải quyết (migration 0054) — cùng loại "sắp trễ".
    "resolution_warning": ("sla_sap_tre", "SLA sắp trễ: gần hạn giải quyết"),
    "resolution_breached": ("sla_tre", "SLA đã trễ: quá hạn giải quyết"),
    # Hạn phản hồi sau chuyển giao (migration 0062) — cùng hai loại, cùng
    # người nhận: người đang cầm (hoặc thành viên kênh) CỘNG người quản lý.
    # Khoá chống dội theo hội thoại như các mục tiêu khác: lượt chuyển giao
    # sau mà thông báo lượt trước còn chưa đọc thì dòng ấy được đẩy lên đầu
    # với nội dung mới, không thành hai dòng.
    "handover_response_warning": (
        "sla_sap_tre", "SLA sắp trễ: chưa nhân viên nào nhắn sau khi AI chuyển giao"),
    "handover_response_breached": (
        "sla_tre", "SLA đã trễ: quá hạn phản hồi sau chuyển giao"),
}


async def bao_sla(conn: Any, su_kien: Iterable[tuple[UUID, str]]) -> int:
    """
    Gọi SAU khi bộ canh SLA đã chèn sự kiện (mỗi sự kiện chỉ chèn được một
    lần nhờ khoá (hội thoại, chu kỳ, loại) — nên đây cũng chỉ một lần).

    Người nhận: người đang cầm hoặc thành viên kênh, CỘNG người quản lý.
    Mỗi hội thoại xử lý riêng: một hội thoại hỏng không chặn những cái sau.
    """
    tong = 0
    for cid, kind in su_kien:
        if kind not in _SLA:
            continue
        loai, tieu_de = _SLA[kind]
        try:
            nhan = await nguoi_nhan_hoi_thoai(
                conn, cid, quyen="hoi_thoai.nhan", them_quan_ly=True)
            if not nhan:
                _khong_ai_nhan(loai, cid)
            tong += await _ghi(
                conn, nhan, loai=loai, tieu_de=tieu_de,
                conversation_id=_uuid(cid), khoa=f"sla:{kind}:{_uuid(cid)}",
            )
        except Exception as exc:  # noqa: BLE001 — vòng SLA không được chết vì chuông
            _loi(loai, cid, exc)
    return tong


async def ket_thuc_luot_chuyen_giao(conn: Any, conversation_id: UUID | str) -> None:
    """
    Lượt chuyển giao đã kết thúc (giải quyết, hoặc người trả lại cho agent):
    gỡ khoá chống dội khỏi thông báo chuyển giao CHƯA ĐỌC của hội thoại.

    Không gỡ thì lần chuyển giao SAU đụng khoá của lần trước (người trực
    chưa bấm đọc) — không dòng mới, KHÔNG tin báo ngoài, khách chờ mà không
    ai biết. Đúng lỗi việc tự sinh từng mắc (rà soát 16.11.2026, xem
    `giai_quyet.dong_viec_tu_sinh`). Thông báo cũ vẫn CHƯA ĐỌC — đọc hay
    không là việc của người nhận, máy không đọc hộ.

    Chạy TRONG giao dịch của nơi gọi, cùng chỗ với `dong_viec_tu_sinh`.
    """
    await conn.execute(
        "UPDATE thong_bao SET khoa_chong_trung = NULL "
        "WHERE conversation_id = $1 AND da_doc_luc IS NULL "
        "AND khoa_chong_trung = 'ai_chuyen_giao:' || $1::text",
        _uuid(conversation_id))


# ---------------------------------------------------------------------------
#  Đọc — luôn theo ĐÚNG người đang đăng nhập.
# ---------------------------------------------------------------------------

def _lien_ket(r: dict) -> dict | None:
    """Bấm vào thì đi đâu. Việc trước, rồi đơn, rồi hội thoại."""
    if r.get("cong_viec_id"):
        return {"loai": "cong_viec", "id": str(r["cong_viec_id"])}
    if r.get("order_id"):
        return {"loai": "don_hang", "id": str(r["order_id"]),
                "hoi_thoai_id": str(r["conversation_id"]) if r.get("conversation_id") else None}
    if r.get("conversation_id"):
        return {"loai": "hoi_thoai", "id": str(r["conversation_id"])}
    return None


async def liet_ke(nguoi_id: UUID, *, chi_chua_doc: bool = False,
                  gioi_han: int = 20, bo_qua: int = 0) -> list[dict]:
    """
    Tên khách đọc qua hội thoại lúc hiển thị, không chép vào bảng — xem
    migration 0055.
    """
    rows = await db.fetch(
        "SELECT t.id, t.loai, t.tieu_de, t.noi_dung, t.conversation_id, "
        "       t.cong_viec_id, t.order_id, t.tao_luc, t.da_doc_luc, "
        "       c.customer_name AS ten_khach, ca.channel AS kenh "
        "FROM thong_bao t "
        "LEFT JOIN conversations c ON c.id = t.conversation_id "
        "LEFT JOIN channel_accounts ca ON ca.id = c.account_id "
        "WHERE t.nguoi_nhan_id = $1 AND ($2::bool IS FALSE OR t.da_doc_luc IS NULL) "
        "ORDER BY t.tao_luc DESC, t.id DESC LIMIT $3 OFFSET $4",
        nguoi_id, chi_chua_doc, gioi_han, bo_qua)
    ra = []
    for r in rows:
        ra.append({
            "id": str(r["id"]),
            "loai": r["loai"],
            "nhan_loai": LOAI.get(r["loai"], r["loai"]),
            "tieu_de": r["tieu_de"],
            "noi_dung": chuan_hoa_noi_dung_thong_bao(r["loai"], r["noi_dung"]),
            "huong_dan": _HUONG_DAN.get(r["loai"], ""),
            "ten_khach": r["ten_khach"],
            "kenh": TEN_KENH.get(r["kenh"] or "", r["kenh"]),
            "tao_luc": r["tao_luc"].isoformat(),
            "da_doc": r["da_doc_luc"] is not None,
            "lien_ket": _lien_ket(r),
        })
    return ra


async def dem_chua_doc(nguoi_id: UUID) -> int:
    return int(await db.pool().fetchval(
        "SELECT count(*) FROM thong_bao WHERE nguoi_nhan_id = $1 AND da_doc_luc IS NULL",
        nguoi_id) or 0)


async def danh_dau_da_doc(nguoi_id: UUID, thong_bao_id: UUID) -> bool:
    """
    Trả False khi không có thông báo ấy CỦA người này — thông báo của người
    khác là 404, không phải 403: không xác nhận id ấy tồn tại.

    Chỉ đổi `da_doc_luc`. Không đụng hội thoại, công việc hay bản nháp nào.
    """
    r = await db.fetchrow(
        "UPDATE thong_bao SET da_doc_luc = coalesce(da_doc_luc, now()) "
        "WHERE id = $1 AND nguoi_nhan_id = $2 RETURNING id",
        thong_bao_id, nguoi_id)
    return r is not None


async def danh_dau_tat_ca(nguoi_id: UUID) -> int:
    kq = await db.execute(
        "UPDATE thong_bao SET da_doc_luc = now() "
        "WHERE nguoi_nhan_id = $1 AND da_doc_luc IS NULL", nguoi_id)
    phan = kq.split()
    return int(phan[-1]) if phan and phan[-1].isdigit() else 0
