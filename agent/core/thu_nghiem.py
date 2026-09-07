"""
Chế độ THỬ: chạy agent thật, chặn tác dụng phụ thật.

VÌ SAO LÀ CỜ NGỮ CẢNH, KHÔNG PHẢI THAM SỐ
----------------------------------------
Phòng thử gọi `respond()`, `respond()` gọi `tools.run_tool()`, và
`run_tool()` gọi bốn hàm ghi với bốn chữ ký khác nhau. Luồn một tham số
`sandbox=` qua từng tầng là sửa năm chữ ký và mời gọi một chỗ quên. Một
`ContextVar` chặn đúng MỘT chỗ — trong `run_tool` — và test AST canh được
rằng mọi công cụ ghi đều đi qua chỗ đó.

VÌ SAO SỔ CHI PHÍ RIÊNG
-----------------------
Chi phí thử là tiền thật nhưng không phải tiền của khách. Cộng vào
`ngan_sach` là một buổi thử nghiệm có thể đẩy hệ thống chạm trần ngày và
chuyển MỌI khách sang người. Sổ riêng, trần riêng; còn trần sản xuất vẫn
được `respond()` kiểm trước khi gọi model, vì tiền là một túi.

MÚI GIỜ: CỘNG TAY, KHÔNG DÙNG zoneinfo
--------------------------------------
Cùng lý do với `agent/core/gio_lam_viec.py`: `zoneinfo.ZoneInfo` cần gói dữ
liệu `tzdata` mà Windows không có sẵn, nên import module là ném
`ZoneInfoNotFoundError` — một chốt sổ chi phí không được phép hỏng vì lý do
đó. Việt Nam ở UTC+7 cố định, không giờ mùa hè, cộng tay bảy tiếng là đủ.
"""
from __future__ import annotations

import secrets
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from agent.config import settings

dang_thu: ContextVar[bool] = ContextVar("dang_thu", default=False)

# Bốn công cụ ghi CSDL/ERP/hàng đợi. Thêm công cụ ghi mới là phải thêm vào
# đây — tests/test_thu_nghiem.py đọc AST của `run_tool` để bắt chỗ quên.
CO_TAC_DUNG_PHU = frozenset({"tao_don_hang", "tao_video", "xin_huy_don", "xin_doi_tra"})

_VN = timezone(timedelta(hours=7))
_da_tieu = 0.0
_ngay: str | None = None


@contextmanager
def bat_thu():
    """`with bat_thu(): ...` — mọi công cụ ghi bên trong đều được mô phỏng."""
    token = dang_thu.set(True)
    try:
        yield
    finally:
        dang_thu.reset(token)


def _ma_thu() -> str:
    return "THU-" + secrets.token_hex(3).upper()


async def mo_phong(ten: str, args: dict, products: list[dict]) -> dict:
    """
    Kết quả GIẢ, đúng hình dạng bản thật, để mô hình trả lời như thường.

    Giữ đúng các chốt của bản thật (xác nhận, đủ thông tin, mã hàng có
    thật) vì đó chính là hành vi người ta muốn thử. Chỉ bước GHI bị bỏ.
    """
    if ten == "tao_don_hang":
        return _mo_phong_don_hang(args, products)
    if ten == "tao_video":
        return {
            "thu_nghiem": True, "dat_duoc": True, "video_id": "thu-" + secrets.token_hex(3),
            "ghi_chu": "ĐANG THỬ: video KHÔNG được đặt vào hàng đợi. Trả lời khách "
                       "như đã ghi nhận yêu cầu và sẽ có người duyệt.",
        }
    if ten in ("xin_huy_don", "xin_doi_tra"):
        return {
            "thu_nghiem": True, "da_ghi_nhan": True, "ma_don": str(args.get("ma_don") or ""),
            "can_chuyen_nhan_vien": True,
            "ghi_chu": "ĐANG THỬ: yêu cầu KHÔNG được ghi lên đơn. Báo khách đã ghi "
                       "nhận và sẽ có nhân viên liên hệ, KHÔNG tự hứa kết quả.",
        }
    return {
        "thu_nghiem": True, "loi": f"Công cụ {ten!r} chưa có bản mô phỏng.",
        "can_chuyen_nhan_vien": True,
        "ghi_chu": "ĐANG THỬ: công cụ này chưa mô phỏng được. Chuyển người.",
    }


def _mo_phong_don_hang(args: dict, products: list[dict]) -> dict:
    if not args.get("khach_da_xac_nhan"):
        return {"thu_nghiem": True, "tao_duoc": False,
                "ly_do": "Khách chưa xác nhận. Hãy tóm tắt đơn đầy đủ rồi hỏi "
                         "khách xác nhận trước, chưa được lên đơn.",
                "ghi_chu": "ĐANG THỬ: chốt xác nhận vẫn áp dụng như thật."}

    # Chốt 2: đủ trường bắt buộc, không tự điền (phải khớp bản thật tại tools.py:953-963)
    thieu = [nhan for khoa, nhan in (("khach_ten", "họ tên"), ("khach_sdt", "số điện thoại"),
                                     ("khach_dia_chi", "địa chỉ"))
             if not str(args.get(khoa) or "").strip()]
    # Kiểm phone: ít nhất 9 chữ số (bỏ ký tự không phải chữ số)
    sdt = "".join(ch for ch in str(args.get("khach_sdt") or "") if ch.isdigit())
    if len(sdt) < 9:
        thieu.append("số điện thoại hợp lệ")
    # Kiểm address: ít nhất 12 ký tự sau khi loại bỏ khoảng trắng
    if len(str(args.get("khach_dia_chi") or "").strip()) < 12:
        thieu.append("địa chỉ đầy đủ")
    if thieu:
        return {"thu_nghiem": True, "tao_duoc": False, "thieu_thong_tin": thieu,
                "ly_do": "Thiếu thông tin giao hàng. Hỏi khách cho đủ, không tự điền.",
                "ghi_chu": "ĐANG THỬ: chốt đủ thông tin vẫn áp dụng như thật."}

    items = args.get("items") or []
    if not items:
        return {"thu_nghiem": True, "tao_duoc": False, "ly_do": "Chưa có sản phẩm nào trong đơn.",
                "ghi_chu": "ĐANG THỬ."}
    from agent.core.tools import _score

    dong, tong = [], 0
    for it in items:
        q = str(it.get("ten_san_pham") or it.get("ma") or "")
        diem, sp = max(((_score(q, sp), sp) for sp in products), key=lambda x: x[0],
                       default=(0, None))
        # Phòng thử phải dùng cùng ngưỡng như bản thật (tools.py:982):
        # < 0.5 = không chấp nhận; spec đòi "mã sai trả đúng lỗi như bản thật",
        # và ngưỡng lệch là phòng thử gắn nhầm hàng vào đơn giả.
        if sp is None or diem < 0.5:
            return {"thu_nghiem": True, "tao_duoc": False,
                    "ly_do": f"Không tìm thấy sản phẩm {q!r} trong danh mục.",
                    "ghi_chu": "ĐANG THỬ: hỏi lại khách tên sản phẩm chính xác."}
        sl = max(1, int(it.get("so_luong") or 1))

        # Tồn kho: dùng con số CÓ TRONG DANH MỤC, và chỉ khi có.
        #
        # Bản thật đọc tồn SỐNG từ ERP (tools.py chốt 4); phòng thử không
        # được gọi ERP, nên nó dùng số trong catalog — cũ hơn, nhưng đủ để
        # tái hiện đúng lời từ chối mà khách sẽ nghe. Không có trường
        # `ton_kho` thì BỎ QUA chốt này: danh mục mẫu không có nó, và chặn
        # theo một số không tồn tại là phòng thử từ chối mọi đơn.
        ton = sp.get("ton_kho")
        if ton is not None:
            ton = int(ton)
            if ton <= 0:
                return {"thu_nghiem": True, "tao_duoc": False,
                        "ly_do": f"{sp['ten']} đang hết hàng, không lên đơn được.",
                        "ghi_chu": "ĐANG THỬ: chốt tồn kho vẫn áp dụng, "
                                   "nhưng đọc số trong danh mục chứ không hỏi ERP."}
            if sl > ton:
                return {"thu_nghiem": True, "tao_duoc": False,
                        "ly_do": f"{sp['ten']} chỉ còn {ton} sản phẩm, không đủ {sl}.",
                        "ghi_chu": "ĐANG THỬ: chốt tồn kho vẫn áp dụng, "
                                   "nhưng đọc số trong danh mục chứ không hỏi ERP."}

        gia = int(sp.get("gia") or 0)
        dong.append({"ma": sp["ma"], "ten": sp["ten"], "so_luong": sl, "gia": gia})
        tong += gia * sl

    # Chốt ngưỡng duyệt phải giống bản thật (tools.py chốt 5). Bỏ nó thì
    # phòng thử luôn báo "đã chốt", và người vận hành không bao giờ nhìn
    # thấy câu agent sẽ nói với khách khi đơn to — đúng lúc câu chữ quan
    # trọng nhất, vì nói nhầm "đã chốt" cho đơn chờ duyệt là một lời hứa sai.
    tu_chot = tong < settings.nguong_tu_chot_vnd
    if not tu_chot:
        return {
            "thu_nghiem": True, "tao_duoc": True, "ma_don": _ma_thu(), "items": dong,
            "tong_tien": tong, "trang_thai": "cho_duyet",
            "ghi_chu_cho_agent": (
                "Đơn giá trị lớn nên đang CHỜ NHÂN VIÊN DUYỆT. Báo khách là đã ghi "
                "nhận và sẽ có người gọi xác nhận, KHÔNG nói là đã chốt xong."
            ),
            "ghi_chu": "ĐANG THỬ: đơn vượt ngưỡng tự chốt nên KHÔNG chốt — "
                       "chờ người duyệt, y như thật.",
        }
    return {
        "thu_nghiem": True, "tao_duoc": True, "ma_don": _ma_thu(), "items": dong,
        "tong_tien": tong, "trang_thai": "da_chot",
        "ghi_chu_cho_agent": "Đơn đã chốt. Báo mã đơn và tổng tiền cho khách.",
        "ghi_chu": "ĐANG THỬ: đơn KHÔNG được ghi vào hệ thống hay ERP. Trả lời "
                   "khách như đã lên đơn thành công với mã trên.",
    }


# ---------------- sổ chi phí thử ----------------

def _hom_nay() -> str:
    return datetime.now(_VN).strftime("%Y-%m-%d")


def xoa_dem() -> None:
    global _da_tieu, _ngay
    _da_tieu = 0.0
    _ngay = None


def _dong_bo_ngay() -> None:
    global _da_tieu, _ngay
    hom_nay = _hom_nay()
    if _ngay is not None and _ngay != hom_nay:
        _da_tieu = 0.0
    _ngay = hom_nay


def ghi_nhan(usd: float) -> None:
    global _da_tieu
    _dong_bo_ngay()
    if usd > 0:
        _da_tieu += float(usd)


def da_tieu_hom_nay() -> float:
    _dong_bo_ngay()
    return _da_tieu


def tran() -> float:
    """Đọc `runtime.STATE` chứ không đọc `settings` — cùng lý do với ngan_sach.tran()."""
    from agent import runtime

    gt = runtime.STATE.get("phong_thu_tran_ngay_usd", settings.phong_thu_tran_ngay_usd)
    try:
        return float(gt or 0.0)
    except (TypeError, ValueError):
        return 0.0


def con_tran() -> tuple[bool, float, float]:
    t = tran()
    da = da_tieu_hom_nay()
    if t <= 0:
        return True, da, t
    return da < t, da, t
