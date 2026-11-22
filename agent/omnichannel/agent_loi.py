"""
Agent NÉM LỖI giữa lượt trả lời → chuyển người ĐẦY ĐỦ, và báo động khi lặp.

VÌ SAO TÁCH RIÊNG
-----------------
Nhánh `except` quanh `brain.respond()` trong `xu_ly_tin_vao.handle_inbound`
trước đây chỉ làm hai việc: đặt hội thoại `escalated` và ghi `agent.error`.
So với mọi nhánh chuyển người khác trong cùng tệp, nó thiếu cả bốn thứ làm
nên một lần chuyển người THẬT:

  · không sinh CÔNG VIỆC  → không ai được giao, hội thoại chỉ đổi màu;
  · không báo NHÂN VIÊN   → người trực trên kênh không thấy gì;
  · không báo KHÁCH       → khách nhắn xong ngồi chờ trong im lặng;
  · không cộng CHI PHÍ    → vòng model đã chạy trước khi lỗi bị mất khỏi sổ.

Và đây không phải nhánh hiếm: khoá API hết hạn, hết hạn mức, nhà cung cấp
sập — MỌI tin khách đều rơi vào đây, cùng lúc, im lặng. Đúng kiểu hỏng
nguy hiểm nhất của repo này: không nổ, không ai biết.

Tách ra một tệp để nhánh ấy gọi đúng MỘT hàm, và để test gọi được hàm này
mà không phải dựng cả luồng tin vào.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Báo động TỐI ĐA một lần mỗi chừng này giây. Lỗi khoá API là lỗi HÀNG LOẠT:
# trăm tin khách là trăm lần lỗi, và trăm tin báo động thì người trực tắt
# kênh báo động — mất luôn lần báo sau, lúc cần thật.
CUA_SO_BAO_DONG_GIAY = 600

# Trong bộ nhớ, không trong CSDL: lúc nhánh này chạy CSDL có thể chính là thứ
# đang hỏng. Khởi động lại tiến trình thì mất trạng thái — tức báo thêm một
# lần, hướng an toàn.
@dataclass
class _TrangThai:
    lan_bao_cuoi: float | None = None
    dem_tu_lan_bao: int = 0


_trang_thai = _TrangThai()


def _nen_bao_dong(bay_gio: float) -> tuple[bool, int]:
    """(có báo không, số lỗi dồn lại kể cả lần này). Cập nhật trạng thái."""
    tt = _trang_thai
    tt.dem_tu_lan_bao += 1
    if tt.lan_bao_cuoi is not None and bay_gio - tt.lan_bao_cuoi < CUA_SO_BAO_DONG_GIAY:
        return False, tt.dem_tu_lan_bao
    dem, tt.lan_bao_cuoi, tt.dem_tu_lan_bao = tt.dem_tu_lan_bao, bay_gio, 0
    return True, dem


async def chuyen_nguoi_vi_agent_loi(msg, cid: uuid.UUID, adapter, exc: BaseException) -> None:
    """
    Làm ĐỦ những gì nhánh chuyển người ở cuối `handle_inbound` làm, cho lượt
    agent vừa ném lỗi.

    Báo động ngay từ lỗi ĐẦU TIÊN (giới hạn một lần/10 phút), không đợi đủ N
    lỗi: cửa hàng nhỏ có thể chỉ một tin mỗi giờ, và ngưỡng "3 lỗi trong 10
    phút" khi ấy không bao giờ chạm — khoá API chết cả buổi mà không ai biết.
    """
    from agent import db, runtime
    from agent.core import thong_bao_noi_bo
    from agent.omnichannel import xu_ly_tin_vao

    loi = f"{type(exc).__name__}: {exc}"[:500]
    # Vòng model chạy TRƯỚC khi lỗi đã tốn tiền. `brain.respond` gắn số đó
    # lên ngoại lệ (và đã cộng vào ngân sách ngày); ở đây cộng vào hội thoại
    # để trần chi phí MỘT hội thoại cũng thấy.
    chi_phi = float(getattr(exc, "chi_phi_da_tieu", 0.0) or 0.0)

    await db.execute(
        "UPDATE conversations SET status = 'escalated', mode = 'human', "
        "version = version + 1, outcome = 'escalated', "
        "cost_usd = cost_usd + $2, updated_at = now() "
        "WHERE id = $1",
        cid, chi_phi,
    )
    await db.log_event("agent.error", ref_id=cid, error=loi, cost_usd=chi_phi)
    ly_do = f"Agent gặp lỗi kỹ thuật ({type(exc).__name__}) — cần người trả lời."
    await db.log_event("conversation.escalated", ref_id=cid, reason=ly_do)
    await thong_bao_noi_bo.bao_ai_chuyen_giao(cid, ly_do=ly_do)

    # Hai lời báo hỏng thì KHÔNG được chặn báo động phía dưới: chính lúc
    # kênh và model cùng hỏng là lúc báo động cần nhất. Hai hàm này tự ghi
    # nhật ký khi hỏng (xem chú thích của chúng trong xu_ly_tin_vao).
    with suppress(Exception):
        await xu_ly_tin_vao.bao_nhan_vien_tiep_quan(
            adapter, msg.conversation_ref, cid, "agent gặp lỗi kỹ thuật",
            tom_tat=(msg.text or "")[:200],
        )
    # Cùng quy tắc với nhánh chuyển người cuối `handle_inbound`: chỉ chế độ
    # tự động mới tự gửi câu cho khách; chế độ Gợi ý thì người duyệt mọi thứ.
    if runtime.mode() == "auto":
        with suppress(Exception):
            await xu_ly_tin_vao.bao_khach_dang_chuyen_nguoi(
                adapter, msg.conversation_ref, cid)

    bao, dem = _nen_bao_dong(time.monotonic())
    if bao:
        try:
            from agent import canh_gac

            await canh_gac.bao_dong(
                f"Agent ném lỗi khi trả lời khách ({dem} lỗi kể từ lần báo trước). "
                f"Lỗi gần nhất: {loi[:200]}. Hội thoại đã chuyển người và có "
                "công việc; kiểm khoá API / hạn mức model ở dashboard → Cấu hình.",
                tieu_de="Agent không trả lời được khách", muc_do="hong",
            )
        except Exception:  # noqa: BLE001 — báo động hỏng không được làm hỏng luồng tin
            logger.exception("agent_loi: không phát được báo động")
