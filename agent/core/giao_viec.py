"""
Phân công công việc: tự động theo ca trực, báo việc chưa ai nhận, canh quá hạn.

PHIẾU VIỆC MỤC 14.5–14.6
------------------------
Hai cách giao: TAY (người có `cong_viec.giao`) và TỰ ĐỘNG. Tự động cố ý
đơn giản — không tính kỹ năng, không tính tải (mục 14.13):

  1. Ứng viên = nhân viên KHÔNG bị khoá, có `cong_viec.doc` + `cong_viec.sua`
     (giao cho người không mở được việc là giao một việc vô hình).
  2. ĐANG TRONG CA theo lịch đã xếp (`dang_trong_ca`, 0034) — và PHẢI có
     lịch. Bộ định tuyến hội thoại coi người chưa xếp ca là "luôn trực" để
     giữ hành vi cũ; ở đây thì không: người chưa có lịch là người ta KHÔNG
     BIẾT có đang làm hay không, và mục 14.6 nói rõ dữ liệu ca không đáng
     tin thì để "Chưa phân công", không đoán.
  3. SẴN SÀNG: không tự tắt "sẵn sàng" ở đội nào (`team_members.is_available`
     — cùng công tắc bộ định tuyến hội thoại đọc).
  4. Việc gắn hội thoại thì chỉ người thuộc KÊNH ấy (hoặc thấy mọi kênh).
     Việc đã giao thì người nhận luôn thấy (`dieu_kien_pham_vi`) — giao nhầm
     kênh là đưa tên khách và lý do chuyển người (có khi là dữ liệu sức khoẻ)
     sang người không được thấy.
  5. Trong số ấy: người LÂU NHẤT chưa được giao việc nào (xoay vòng theo
     lịch sử `cong_viec_lich_su`, không cần con trỏ riêng); hoà thì theo id
     cho ổn định. Khoá advisory để hai lần tự phân công cùng lúc không cùng
     chọn một người.

Không ai đủ điều kiện -> việc ở lại "Chưa phân công" và người điều phối được
báo (`thong_bao_noi_bo.bao_viec_chua_giao`). KHÔNG BAO GIỜ giao cho người
"gần đúng".
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from agent import db
from agent.core import cong_viec as cv
from agent.core import thong_bao_noi_bo

log = logging.getLogger("agent.giao_viec")

_SQL_UNG_VIEN = cv.SQL_VIEC_VA_QUYEN + f"""
    SELECT q.id,
           (SELECT max(l.tao_luc) FROM cong_viec_lich_su l
            WHERE l.den_nguoi = q.id) AS lan_cuoi
    FROM quyen q, viec
    WHERE q.doc AND q.sua
      AND EXISTS (SELECT 1 FROM ca_truc ct WHERE ct.nguoi_dung_id = q.id)
      AND dang_trong_ca(q.id, now())
      AND NOT EXISTS (SELECT 1 FROM team_members tm
                      WHERE tm.user_id = q.id AND NOT tm.is_available)
      AND {cv.SQL_CUNG_KENH}
    ORDER BY lan_cuoi ASC NULLS FIRST, q.id
"""

LY_DO_KHONG_CO_LICH = (
    "Chưa có lịch ca nào được xếp — không biết ai đang làm, nên không tự phân công.")
LY_DO_KHONG_AI = (
    "Không có nhân viên nào đang trong ca, sẵn sàng và có quyền làm việc này.")
LY_DO_DA_CO_NGUOI = "Việc đã có người nhận hoặc đã đóng."


@dataclass(frozen=True, slots=True)
class KetQuaGiao:
    nguoi_nhan: UUID | None
    ly_do: str


async def ung_vien(conn: Any, cong_viec_id: UUID) -> list[UUID]:
    """Người được tự phân công việc này, theo thứ tự ưu tiên — luật ở đầu tệp."""
    return [r["id"] for r in await conn.fetch(_SQL_UNG_VIEN, cong_viec_id)]


async def tu_dong_giao(conn: Any, cong_viec_id: UUID, *,
                       nguoi_id: Any = None) -> KetQuaGiao:
    """
    Chọn và giao NGAY trong giao dịch của nơi gọi. Không báo ai — báo SAU
    khi giao dịch chốt (`bao_sau_khi_giao`), cùng thứ tự với giao hội thoại:
    chuông hỏng không được làm hỏng lần giao.
    """
    if not conn.is_in_transaction():
        raise RuntimeError("tu_dong_giao phải chạy trong conn.transaction()")
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('cong_viec.tu_dong_giao'))")
    viec = await conn.fetchrow(
        "SELECT nguoi_nhan, trang_thai FROM cong_viec WHERE id = $1 FOR UPDATE",
        cong_viec_id)
    if viec is None or viec["nguoi_nhan"] is not None or viec["trang_thai"] not in cv.CHUA_XONG:
        return KetQuaGiao(None, LY_DO_DA_CO_NGUOI)
    ds = await ung_vien(conn, cong_viec_id)
    if not ds:
        co_lich = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM ca_truc)")
        return KetQuaGiao(None, LY_DO_KHONG_AI if co_lich else LY_DO_KHONG_CO_LICH)
    chon = ds[0]
    await cv.dat_ngu_canh(
        conn, nguoi_id=nguoi_id, tu_dong_giao=True,
        ghi_chu="Đang trong ca, sẵn sàng, lâu nhất chưa được giao việc")
    await conn.execute(
        "UPDATE cong_viec SET nguoi_nhan = $2, sua_luc = now() WHERE id = $1",
        cong_viec_id, chon)
    # Xoá ngữ cảnh: câu lệnh SAU trong cùng giao dịch (nếu có) không phải là
    # phân công tự động.
    await cv.dat_ngu_canh(conn, nguoi_id=nguoi_id)
    return KetQuaGiao(chon, "")


async def bao_sau_khi_giao(cong_viec_id: UUID, kq: KetQuaGiao, *,
                           tieu_de_viec: str, boi: Any = None) -> None:
    """Chuông sau khi giao dịch đã chốt. Không ném (thong_bao_noi_bo lo)."""
    if kq.nguoi_nhan is not None:
        await thong_bao_noi_bo.bao_duoc_giao_viec(
            cong_viec_id, kq.nguoi_nhan, boi=boi, tieu_de_viec=tieu_de_viec,
            tu_dong=True)
    else:
        await thong_bao_noi_bo.bao_viec_chua_giao(
            cong_viec_id, tieu_de_viec=tieu_de_viec, ly_do=kq.ly_do, tru=boi)


async def giao_tu_dong_va_bao(cong_viec_id: UUID | str, *,
                              nguoi_id: Any = None) -> KetQuaGiao:
    """
    Đường gọn cho nơi tạo việc ngoài API (quy tắc tự động): tự phân công
    trong giao dịch riêng rồi báo. Không ném: hỏng thì việc vẫn còn đó ở
    "Chưa phân công", người điều phối vẫn được báo, và nhật ký mức LỖI.
    """
    vid = cong_viec_id if isinstance(cong_viec_id, UUID) else UUID(str(cong_viec_id))
    tieu_de = ""
    try:
        async with db.pool().acquire() as conn:
            async with conn.transaction():
                tieu_de = await conn.fetchval(
                    "SELECT tieu_de FROM cong_viec WHERE id = $1", vid) or ""
                kq = await tu_dong_giao(conn, vid, nguoi_id=nguoi_id)
    except Exception as exc:  # noqa: BLE001 — việc đã tạo; chỉ mất phần tự giao
        log.error("KHÔNG tự phân công được việc %s: %s: %s", vid, type(exc).__name__, exc)
        kq = KetQuaGiao(None, f"Lỗi khi tự phân công: {type(exc).__name__}")
    await bao_sau_khi_giao(vid, kq, tieu_de_viec=tieu_de, boi=nguoi_id)
    return kq


async def bao_neu_chua_giao(cong_viec_id: UUID | str | None, *, ly_do: str = "") -> None:
    """
    Việc MÁY vừa tạo (AI đề xuất, vận chuyển, đơn hàng, kênh) mà chưa ai
    nhận: báo người điều phối. Không ném — nơi gọi là webhook hay lượt chat.
    """
    if not cong_viec_id:
        return
    try:
        r = await db.fetchrow(
            "SELECT tieu_de, nguoi_nhan, trang_thai FROM cong_viec WHERE id = $1::uuid",
            str(cong_viec_id))
        if r is None or r["nguoi_nhan"] is not None or r["trang_thai"] not in cv.CHUA_XONG:
            return
        await thong_bao_noi_bo.bao_viec_chua_giao(
            UUID(str(cong_viec_id)), tieu_de_viec=r["tieu_de"], ly_do=ly_do)
    except Exception as exc:  # noqa: BLE001 — việc đã tạo; chỉ mất chuông
        log.error("KHÔNG báo được việc chưa phân công %s: %s: %s",
                  cong_viec_id, type(exc).__name__, exc)


# ---------------------------------------------------------------------------
#  Canh quá hạn
# ---------------------------------------------------------------------------

async def quet_viec_qua_han(gioi_han: int = 200) -> int:
    """
    Đánh dấu và báo việc VỪA quá hạn. Trả số việc đã báo.

    Đánh dấu (`bao_qua_han_luc`) TRƯỚC rồi báo: hai tiến trình cùng quét thì
    UPDATE ... RETURNING chỉ trả mỗi việc cho một bên. Đổi lại, chuông hỏng
    ở bước sau thì việc ấy không được báo lại — nhưng vẫn nằm trên ô "quá
    hạn" của Tổng quan, và lỗi vào nhật ký mức LỖI.
    """
    rows = await db.fetch(
        "UPDATE cong_viec SET bao_qua_han_luc = now() WHERE id IN ("
        "  SELECT id FROM cong_viec WHERE han < now() AND bao_qua_han_luc IS NULL "
        "  AND trang_thai IN ('moi', 'dang_lam') ORDER BY han LIMIT $1) "
        "RETURNING id, tieu_de, nguoi_nhan", gioi_han)
    for r in rows:
        await thong_bao_noi_bo.bao_viec_qua_han(
            r["id"], nguoi_nhan_id=r["nguoi_nhan"], tieu_de_viec=r["tieu_de"])
    return len(rows)


async def vong_canh_viec_loop(*, moi_giay: float = 120.0, log_error=None) -> None:
    """Vòng nền: mỗi `moi_giay` quét việc quá hạn. Không chết vì một lượt hỏng."""
    while True:
        try:
            await quet_viec_qua_han()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng nền phải tự hồi phục
            log.error("Vòng canh công việc hỏng: %s: %s", type(exc).__name__, exc)
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        await asyncio.sleep(moi_giay)
