"""Bộ khẳng định CHUNG, chạy trên MỌI adapter kênh.

VÌ SAO CẦN
----------
`tests/test_hop_dong_chung.py` mở đầu bằng đúng lập luận này, và áp nó cho
ba adapter ERP: không có bộ test dùng chung thì các bản cài đặt sẽ trôi ra
xa nhau một cách âm thầm.

Lớp KÊNH có chín adapter — nhiều gấp ba, và gần khách hơn hẳn — mà không có
bộ nào như vậy. Mỗi kênh chỉ có test riêng của nó, nên không phép kiểm nào
đứng ở chỗ nhìn thấy được rằng Messenger có `bao_chuyen_nguoi` còn
Instagram thì không.

Và chúng đã trôi thật. Instagram với WhatsApp ngồi ngay cạnh Messenger,
cùng một tài khoản Meta, cùng kế thừa `_MetaAdapter` — nhưng Messenger được
viết thêm `bao_dang_go` và `bao_chuyen_nguoi`, hai kênh kia thì không. Đó
không phải quyết định, đó là sót.

CÁI GIÁ CỦA VIỆC SÓT `bao_chuyen_nguoi`
---------------------------------------
`base.py` đã ghi sẵn: agent chuyển người mà chỉ ghi vào CSDL của mình thì
nhân viên đang làm việc trong hộp thư của kênh KHÔNG THẤY GÌ. Hội thoại
trông như đã xử lý xong, khách ngồi chờ, và không ai biết.

Đúng họ với những lỗi nặng nhất của repo này: không nổ, không nhật ký.

CÁCH LƯỚI NÀY LÀM VIỆC
----------------------
Mỗi cặp (adapter, móc tuỳ chọn) chưa cài đặt phải nằm trong ĐÚNG MỘT bảng
dưới đây — `_KHONG_CAN` nếu là quyết định có lý do, `_CHUA_LAM` nếu là việc
còn nợ. Thiếu ở cả hai thì test đỏ.

Nghĩa là thêm một kênh mới không còn im lặng được nữa: tác giả buộc phải
viết ra, cho từng móc, rằng mình đã cân nhắc và chọn gì.

`_CHUA_LAM` không đỏ — nó là sổ nợ nhìn thấy được. Nhưng mục nào đã làm
xong mà còn nằm trong đó thì ĐỎ, để sổ nợ không mục theo thời gian.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.channels import (  # noqa: E402,F401 — import để lớp con tự đăng ký
    chatwoot,
    messenger,
    meta_channels,
    webchat,
    zalo_oa,
    zalo_personal,
    zalocrm,
)
from agent.channels.base import ChannelAdapter  # noqa: E402

# Móc TUỲ CHỌN: có mặc định ở `base.py`, kênh nào cần thì ghi đè.
# `parse`, `send_text`, `send_file` không nằm đây vì chúng là @abstractmethod —
# Python đã chặn ngay lúc dựng đối tượng, không cần lưới.
MOC_TUY_CHON = (
    "parse_nhieu", "verify_connection", "bao_dang_go",
    "bao_chuyen_nguoi", "can_send_now", "fetch_new",
)

# Chín adapter đang có. Danh sách này KHÔNG dùng để quét — quét bằng
# `__subclasses__` ở dưới — mà để phát hiện adapter biến mất hoặc bị đổi tên.
TEN_DA_BIET = {
    "ChatwootAdapter", "FacebookAdapter", "InstagramAdapter", "MessengerAdapter",
    "WebchatAdapter", "WhatsAppAdapter", "ZaloCRMAdapter", "ZaloOAAdapter",
    "ZaloPersonalAdapter",
}

# KHÔNG CẦN — dùng mặc định là ĐÚNG, kèm lý do.
_KHONG_CAN: dict[tuple[str, str], str] = {
    # `fetch_new`: chỉ kênh phải KÉO mới cần. Kênh đi bằng webhook mà cài
    # thêm là tạo ra đường thứ hai cho cùng một tin — trùng lặp, không thiếu.
    **{(ten, "fetch_new"): "đi bằng webhook, không kéo"
       for ten in ("FacebookAdapter", "InstagramAdapter", "MessengerAdapter",
                   "WebchatAdapter", "WhatsAppAdapter", "ZaloOAAdapter",
                   "ZaloPersonalAdapter")},

    # `parse_nhieu`: chỉ cần cho nhà cung cấp gộp nhiều tin vào MỘT POST.
    # Meta gộp; những kênh dưới đây đẩy từng tin một.
    ("ChatwootAdapter", "parse_nhieu"): "Chatwoot đẩy mỗi lần một tin",
    ("ZaloCRMAdapter", "parse_nhieu"): "ZaloCRM kéo từng tin một",
    ("ZaloOAAdapter", "parse_nhieu"): "Zalo OA đẩy mỗi webhook một sự kiện",
    ("ZaloPersonalAdapter", "parse_nhieu"): "sidecar đẩy mỗi lần một tin",
    ("WebchatAdapter", "parse_nhieu"): "widget gửi từng tin khi khách bấm gửi",

    # `can_send_now`: mặc định True. Chỉ kênh CÓ cửa sổ thời gian mới cần
    # ghi đè (Zalo OA 7 ngày, Meta 24 giờ).
    ("ZaloPersonalAdapter", "can_send_now"): "tài khoản cá nhân, không có cửa sổ",
    ("WebchatAdapter", "can_send_now"): "widget của chính mình, không có cửa sổ",
    ("ChatwootAdapter", "can_send_now"): "cửa sổ do nền tảng gốc phía sau Chatwoot lo",
    ("ZaloCRMAdapter", "can_send_now"): "connector cũ, không có khái niệm cửa sổ",

    # `verify_connection`: base trả False để connector không được kích hoạt.
    # Hai connector cũ CỐ Ý không kích hoạt được — đang bị thay bằng native.
    ("ChatwootAdapter", "verify_connection"): "connector cũ, cố ý không kích hoạt được",
    ("ZaloCRMAdapter", "verify_connection"): "connector cũ, cố ý không kích hoạt được",

    # `bao_dang_go` / `bao_chuyen_nguoi`: hai kênh dưới đây KHÔNG có hộp thư
    # ngoài. Nhân viên trực thẳng trong dashboard của hệ thống này, nên
    # không có bên thứ hai nào cần được báo.
    ("WebchatAdapter", "bao_dang_go"): "không có hộp thư ngoài — nhân viên trực trong dashboard",
    ("WebchatAdapter", "bao_chuyen_nguoi"): "không có hộp thư ngoài — nhân viên trực trong dashboard",
    ("ZaloPersonalAdapter", "bao_dang_go"): "zca-js chưa mở API báo đang gõ",
    ("ZaloPersonalAdapter", "bao_chuyen_nguoi"): "không có hộp thư ngoài — nhân viên trực trong dashboard",
    ("ZaloCRMAdapter", "bao_dang_go"): "Public API của ZaloCRM không có endpoint này",
    ("ZaloCRMAdapter", "bao_chuyen_nguoi"): "Public API của ZaloCRM không có endpoint này",
}

# CHƯA LÀM — sổ nợ nhìn thấy được. Mỗi mục ghi HẬU QUẢ, không ghi "TODO".
_CHUA_LAM: dict[tuple[str, str], str] = {
    ("InstagramAdapter", "bao_chuyen_nguoi"):
        "DM Instagram hiện trong Meta Business Suite, đúng chỗ nhân viên trực. "
        "Agent chuyển người mà hộp thư ấy không đổi gì: khách ngồi chờ, không ai biết. "
        "Messenger đã có; Instagram sót vì kế thừa _MetaAdapter chứ không kế thừa Messenger.",
    ("WhatsAppAdapter", "bao_chuyen_nguoi"):
        "Cùng lý do với Instagram — chung _MetaAdapter, chung hộp thư Meta.",
    ("ZaloOAAdapter", "bao_chuyen_nguoi"):
        "Zalo OA có trang quản lý hội thoại riêng. Chuyển người không tới được đó.",
    ("InstagramAdapter", "bao_dang_go"):
        "Meta dùng chung sender_action cho Messenger và Instagram, nên đây là "
        "sót chứ không phải giới hạn của nền tảng.",
    ("WhatsAppAdapter", "bao_dang_go"):
        "Cloud API có typing indicator; chưa nối.",
    ("ZaloOAAdapter", "bao_dang_go"):
        "Chưa kiểm Zalo OA có API báo đang gõ hay không.",
}


def _lop_cu_the() -> list[type[ChannelAdapter]]:
    """Quét thay vì gõ tay, vì danh sách gõ tay chỉ canh được thứ người ta nhớ."""
    def con(c: type) -> list[type]:
        ra = []
        for s in c.__subclasses__():
            ra.append(s)
            ra.extend(con(s))
        return ra
    return sorted(
        {c for c in con(ChannelAdapter) if not c.__name__.startswith("_")},
        key=lambda c: c.__name__,
    )


def _tu_cai_dat(lop: type, ten_moc: str) -> bool:
    """Lớp này (hoặc lớp cha của nó, trừ base) có tự viết móc đó không."""
    return any(ten_moc in k.__dict__ for k in lop.__mro__ if k is not ChannelAdapter)


def test_quet_ra_dung_cac_adapter_da_biet():
    """Canh chính cái lưới: quét hụt thì mọi phép dưới đây xanh giả."""
    ten = {c.__name__ for c in _lop_cu_the()}
    assert ten, "không quét ra adapter nào — import hỏng, lưới đang canh rỗng"
    assert ten == TEN_DA_BIET, (
        f"danh sách adapter đã đổi. Thừa: {ten - TEN_DA_BIET}. Thiếu: {TEN_DA_BIET - ten}. "
        "Thêm kênh mới thì khai vào TEN_DA_BIET và hai bảng năng lực."
    )


@pytest.mark.parametrize("lop", _lop_cu_the(), ids=lambda c: c.__name__)
def test_moi_adapter_tu_dong_tai_nguyen(lop):
    """
    `registry.dong_tat_ca()` gọi `aclose()` cho MỌI adapter trong cache mà
    không phòng bị. Quên khai là AttributeError đúng lúc tắt ứng dụng — và
    lỗi lúc shutdown là thứ không ai đọc.
    """
    assert _tu_cai_dat(lop, "aclose"), f"{lop.__name__} chưa khai aclose()"


@pytest.mark.parametrize("lop", _lop_cu_the(), ids=lambda c: c.__name__)
def test_moc_chua_cai_dat_phai_duoc_khai_bao(lop):
    """
    Mỗi móc chưa cài đặt phải là một quyết định VIẾT RA, không phải im lặng.

    Đây là toàn bộ giá trị của file này: thêm kênh mới mà quên `bao_chuyen_nguoi`
    thì đỏ ngay, kèm câu hỏi buộc phải trả lời — kênh này có hộp thư ngoài không?
    """
    for moc in MOC_TUY_CHON:
        if _tu_cai_dat(lop, moc):
            continue
        khoa = (lop.__name__, moc)
        assert khoa in _KHONG_CAN or khoa in _CHUA_LAM, (
            f"{lop.__name__} dùng mặc định cho `{moc}` mà không khai lý do.\n"
            f"Nếu mặc định là đúng → thêm vào _KHONG_CAN kèm lý do.\n"
            f"Nếu là việc còn nợ → thêm vào _CHUA_LAM kèm HẬU QUẢ khi thiếu."
        )
        assert not (khoa in _KHONG_CAN and khoa in _CHUA_LAM), (
            f"{khoa} nằm ở cả hai bảng — phải chọn một"
        )


def test_so_no_khong_muc():
    """
    Mục đã làm xong mà còn trong `_CHUA_LAM` thì ĐỎ.

    Sổ nợ không ai dọn sẽ đầy những dòng đã hết đúng, và khi ấy không ai đọc
    nó nữa — đúng cách một bảng luôn đỏ trở thành một bảng người ta bỏ qua.
    """
    theo_ten = {c.__name__: c for c in _lop_cu_the()}
    xong_roi = [
        khoa for khoa in _CHUA_LAM
        if khoa[0] in theo_ten and _tu_cai_dat(theo_ten[khoa[0]], khoa[1])
    ]
    assert not xong_roi, f"đã cài đặt rồi, xoá khỏi _CHUA_LAM: {xong_roi}"


def test_bang_nang_luc_khong_con_muc_thua():
    """Adapter đã xoá mà bảng còn nhắc thì bảng bắt đầu nói dối."""
    ten = {c.__name__ for c in _lop_cu_the()}
    thua = [k for k in (*_KHONG_CAN, *_CHUA_LAM) if k[0] not in ten]
    assert not thua, f"nhắc adapter không còn tồn tại: {thua}"


def test_moc_tuy_chon_khop_voi_base():
    """
    `MOC_TUY_CHON` gõ tay. `base.py` thêm móc mới mà quên thêm vào đây thì
    móc ấy không được canh — và nó sẽ là móc mới nhất, tức là móc dễ sót nhất.
    """
    nguon = (ROOT / "agent" / "channels" / "base.py").read_text(encoding="utf-8")
    than = nguon.split("class ChannelAdapter", 1)[1]
    for moc in MOC_TUY_CHON:
        assert f"def {moc}(" in than, f"`{moc}` không còn trong hợp đồng base"
