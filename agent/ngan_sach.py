"""
Trần chi phí TOÀN CỤC theo ngày.

VÌ SAO TRẦN MỖI HỘI THOẠI LÀ CHƯA ĐỦ
------------------------------------
`max_cost_per_conversation = 0.25` chặn được một hội thoại chạy loạn. Nó
KHÔNG chặn được nhiều hội thoại cùng chạy đúng luật:

    0,25 USD × 10.000 hội thoại = 2.500 USD

và không có gì trong hệ thống nói "khoan đã". Ba đường tới con số ấy, không
đường nào cần kẻ xấu:

  1. Một bài viral. Cửa hàng mừng, hoá đơn thì không.
  2. Một vòng lặp trong adapter kênh — webhook gửi lại, agent trả lời lại.
     Đây là lỗi phần mềm, và nó tiêu tiền trong lúc không ai nhìn.
  3. Một người gửi tin liên tục từ nhiều tài khoản.

Trần theo ngày là thứ chặn cả ba, và nó là hàng rào cuối giữa một sự cố kỹ
thuật và một hoá đơn thật.

ĐÂY LÀ MỞ RỘNG CỦA LỚP LƯỚI SỐ 1, KHÔNG PHẢI LỚP THỨ BẢY
--------------------------------------------------------
Kiến trúc có sáu lớp lưới, và lớp thứ nhất là "trần chi phí". Trần ngày là
CÙNG lớp ấy ở phạm vi rộng hơn — cùng câu hỏi (còn được phép tiêu không),
cùng hành động khi chạm (chuyển người). Gọi nó là lớp thứ bảy thì con số
sáu trong tài liệu sai, mà bản chất thì không có gì mới.

CHẠM TRẦN LÀ CHUYỂN NGƯỜI VÀ KÊU TO, KHÔNG PHẢI IM LẶNG BỎ TIN
--------------------------------------------------------------
Hết ngân sách mà lặng lẽ ngừng trả lời là kiểu hỏng tệ nhất: khách vẫn nhắn,
tin vẫn vào cơ sở dữ liệu, không ai trả lời, và không có gì báo. Nên chạm
trần thì mọi hội thoại chuyển sang người VÀ bắn cảnh báo — cửa hàng phải
biết ngay, vì họ cần quyết định nâng trần hay dừng.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from agent import db
from agent.config import settings

VN = timezone(timedelta(hours=7))

# Đệm kết quả truy vấn. `con_ngan_sach()` chạy ở MỌI tin nhắn, và một lượt
# SUM trên `messages` cho mỗi tin là lãng phí — chỉ mục `idx_msg_time` làm
# nó rẻ, nhưng rẻ nhân với mọi tin vẫn là tốn.
#
# 30 giây, không dài hơn: đệm càng lâu thì càng tiêu quá trần trước khi
# nhận ra. Với ~0,02 USD một tin, 30 giây ở nhịp cao nhất vẫn chỉ vượt vài
# xu — chấp nhận được, và đó là con số có thể nói ra chứ không phải đoán.
TTL_GIAY = 30.0

_dem_luc: float = 0.0
_dem_gia_tri: float = 0.0
# Chi phí phát sinh TRONG cửa sổ đệm, cộng thêm vào giá trị đã đọc. Không có
# nó thì suốt 30 giây hệ thống tin rằng mình chưa tiêu thêm đồng nào — và ở
# đúng lúc đang chạm trần, 30 giây là quãng nguy hiểm nhất.
_cong_them: float = 0.0

# Đã kêu cho ngày nào rồi. Chạm trần thì kêu MỘT LẦN, không phải mỗi tin —
# một cảnh báo mỗi giây thì người trực tắt thông báo, và lần sau có sự cố
# thật cũng không ai thấy.
_da_keu_ngay: str | None = None
# Ngày của giá trị đang giữ trong đệm. Qua 0 giờ thì mọi con số cũ vô nghĩa
# và phải bỏ hết — không có mốc này thì phép `max()` bên dưới giữ lại tổng
# của hôm qua và trần hôm nay chạm ngay từ tin nhắn đầu tiên.
_dem_ngay: str | None = None


def _hom_nay() -> str:
    return datetime.now(VN).strftime("%Y-%m-%d")


def xoa_dem() -> None:
    """Dùng trong test, và sau khi người vận hành nâng trần."""
    global _dem_luc, _dem_gia_tri, _cong_them, _da_keu_ngay, _dem_ngay
    _dem_luc = 0.0
    _dem_gia_tri = 0.0
    _cong_them = 0.0
    _da_keu_ngay = None
    _dem_ngay = None


def ghi_nhan(chi_phi: float) -> None:
    """
    Cộng chi phí vừa tiêu vào bộ đếm trong tiến trình.

    Gọi ngay sau mỗi lượt trả lời. Không gọi thì con số chỉ đúng tới lần
    làm mới đệm gần nhất.
    """
    global _cong_them
    if chi_phi > 0:
        _cong_them += float(chi_phi)


async def da_tieu_hom_nay(dong_ho=time.monotonic) -> float:
    """Tổng chi phí từ 0 giờ (giờ VN) tới giờ, tính bằng USD."""
    global _dem_luc, _dem_gia_tri, _cong_them, _dem_ngay

    bay_gio = dong_ho()
    ngay = _hom_nay()

    # Sang ngày mới thì mọi con số cũ vô nghĩa. Bỏ trước khi làm gì khác.
    if _dem_ngay is not None and _dem_ngay != ngay:
        _dem_luc = 0.0
        _dem_gia_tri = 0.0
        _cong_them = 0.0

    if _dem_luc and (bay_gio - _dem_luc) < TTL_GIAY:
        return _dem_gia_tri + _cong_them

    dau_ngay = datetime.now(VN).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        r = await db.fetchrow(
            "SELECT coalesce(sum(cost_usd), 0) AS tong "
            "FROM messages WHERE created_at >= $1",
            dau_ngay,
        )
        tu_csdl = float(r["tong"] if r else 0.0)
    except Exception:  # noqa: BLE001
        # Không đọc được thì KHÔNG chặn agent. Trần chi phí là hàng rào
        # phòng xa; biến một sự cố cơ sở dữ liệu thành "cửa hàng ngừng trả
        # lời khách" là đổi một vấn đề nhỏ lấy một vấn đề lớn hơn.
        return _dem_gia_tri + _cong_them

    # LẤY GIÁ TRỊ LỚN HƠN, không lấy thẳng con số từ CSDL.
    #
    # `ghi_nhan()` được gọi ngay khi `respond()` xong, còn dòng `messages`
    # thì do lớp gọi ghi vào SAU đó. Giữa hai thời điểm ấy có một khoảng —
    # và nếu lượt đọc CSDL rơi đúng vào khoảng đó, con số trả về THIẾU phần
    # vừa tiêu. Lấy thẳng nó là xoá mất phần ấy vĩnh viễn.
    #
    # Với một hàng rào chi phí, sai theo hướng báo ÍT hơn thực tế là sai
    # nguy hiểm: nó cho tiêu tiếp. Nên lấy con số lớn hơn giữa "CSDL nói" và
    # "ta đã đếm được" — cùng lắm là chặn sớm hơn vài xu.
    _dem_gia_tri = max(tu_csdl, _dem_gia_tri + _cong_them)
    _dem_luc = bay_gio
    _dem_ngay = ngay
    _cong_them = 0.0
    return _dem_gia_tri


def tran() -> float:
    """
    Trần ngày đang áp dụng. `<= 0` nghĩa là TẮT — không giới hạn.

    Đọc từ `runtime.STATE`, KHÔNG đọc thẳng `settings`. Đọc `settings` thì
    ô nhập trên dashboard thành đồ trang trí: bấm được, ghi được xuống CSDL,
    hiện đúng giá trị mới — mà lưới vẫn chặn theo con số trong `.env`.
    """
    from agent import runtime

    gt = runtime.STATE.get(
        "tran_chi_phi_ngay_usd",
        getattr(settings, "tran_chi_phi_ngay_usd", 0.0),
    )
    try:
        return float(gt or 0.0)
    except (TypeError, ValueError):
        return 0.0


async def con_ngan_sach() -> tuple[bool, float, float]:
    """
    (còn được tiêu không, đã tiêu, trần).

    Trần `<= 0` thì luôn còn — người vận hành tắt hẳn tính năng này.
    """
    t = tran()
    da = await da_tieu_hom_nay()
    if t <= 0:
        return True, da, t
    return da < t, da, t


async def keu_neu_cham_tran(da: float, t: float) -> None:
    """
    Bắn cảnh báo MỘT LẦN mỗi ngày khi chạm trần.

    Im lặng ngừng trả lời là kiểu hỏng tệ nhất: khách vẫn nhắn, tin vẫn vào
    cơ sở dữ liệu, không ai trả lời, và không có gì báo.
    """
    global _da_keu_ngay
    ngay = _hom_nay()
    if _da_keu_ngay == ngay:
        return
    _da_keu_ngay = ngay
    try:
        await db.log_event(
            "ngan_sach.cham_tran", actor="system",
            da_tieu=f"{da:.4f}", tran=f"{t:.4f}",
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from agent import canh_gac

        await canh_gac._bao(
            "nghiem_trong",
            "Chạm trần chi phí ngày",
            f"Đã tiêu {da:.2f} USD / trần {t:.2f} USD. Mọi hội thoại đang "
            "chuyển sang người. Nâng trần ở màn Cấu hình, hoặc để nguyên và "
            "xử lý bằng người tới hết ngày.",
            {},
        )
    except Exception:  # noqa: BLE001
        # Cảnh báo hỏng không được làm hỏng đường trả lời khách. Sự kiện ở
        # trên đã vào nhật ký, nên vẫn còn dấu vết.
        pass
