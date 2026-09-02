"""
Tạo vận đơn xong phải BÁO MÃ CHO KHÁCH — và báo qua outbox, không gọi thẳng.

HAI LỖI TRONG PHẦN THỪA KẾ
==========================

1. MÃ VẬN ĐƠN KHÔNG BAO GIỜ TỚI KHÁCH
-------------------------------------
`tao_van_don_cho_don` tạo vận đơn, lưu `ma_van_don` vào bảng `orders`, rồi
DỪNG. Khách không nhận được gì.

Họ chỉ nghe tin khi hàng ĐÃ giao xong — tức là suốt hai đến bốn ngày chờ,
họ không biết đơn đã đi hay chưa, không có mã để tự tra trên ứng dụng hãng.
Đó chính là câu hỏi phổ biến nhất sau bán: "đơn em tới đâu rồi?".

2. TIN BÁO GIAO XONG GỌI THẲNG ADAPTER
--------------------------------------
    await adapter.send_text(conv["external_id"], msg_text)
    except Exception:
        pass

Bốn thứ mất cùng lúc:

    thử lại        provider lỗi một giây là tin bay mất
    chống trùng    webhook Meta/GHN phát lại là khách nhận hai lần
    lưu vết        tin KHÔNG vào bảng `messages`, nên nó không hiện trong
                   khung chat, Customer 360 không thấy, nhật ký không có
    báo lỗi        `except: pass` nuốt im — đúng loại hỏng repo này sợ nhất

Mọi tin khác trong hệ thống đều đi qua outbox. Riêng chỗ này thì không.
"""
from __future__ import annotations

import inspect

from agent.shipping import service


def _nguon_tao() -> str:
    return inspect.getsource(service.tao_van_don_cho_don)


def _nguon_webhook() -> str:
    return inspect.getsource(service.xu_ly_webhook_van_chuyen)


def _nguon_bao_khach() -> str:
    """
    Hàm DÙNG CHUNG cho mọi tin gửi khách từ phân hệ vận chuyển.

    Gom vào một chỗ có chủ ý: hai đường gọi (tạo vận đơn, webhook giao xong)
    phải cùng đi qua outbox, và một chỗ thì không lệch được với chính nó.
    """
    return inspect.getsource(service._bao_khach)


# --- Báo mã vận đơn khi TẠO ---

def test_tao_van_don_xong_thi_bao_khach():
    assert "_bao_khach" in _nguon_tao(), (
        "tạo vận đơn xong nhưng khách không nhận được mã"
    )


def test_tin_bao_co_ma_van_don():
    """Không có mã thì khách không tự tra được trên ứng dụng hãng."""
    khoi = _nguon_tao().split("_bao_khach", 1)[1][:900]
    assert "ma_van_don" in khoi


def test_khong_hua_ngay_giao():
    """
    Hệ thống đọc SỔ CỦA CỬA HÀNG, không đọc vị trí kiện hàng theo thời gian
    thực. Hứa "mai hàng tới" là hứa thứ mình không có cơ sở nào để biết —
    cùng giới hạn đã ghi trong mô tả công cụ `tra_cuu_van_chuyen`.
    """
    nguon = _nguon_tao()
    for hua in ("ngày mai", "mai hàng tới", "chắc chắn"):
        assert hua not in nguon


# --- Mọi tin đều qua outbox ---

def test_webhook_khong_goi_thang_adapter():
    assert "adapter.send_text" not in _nguon_webhook(), (
        "vẫn gọi thẳng provider — mất thử lại, chống trùng và lưu vết"
    )


def test_webhook_di_qua_outbox():
    assert "_bao_khach" in _nguon_webhook()


def test_ham_dung_chung_gui_qua_OUTBOX():
    """Đây là chỗ duy nhất được phép chạm tới lớp gửi tin."""
    assert "queue_text" in _nguon_bao_khach()
    assert "idempotency_key" in _nguon_bao_khach()


def _chi_ma(src: str) -> str:
    """
    Bỏ chú thích và docstring, chỉ giữ mã chạy được.

    Bản đầu của test dưới ĐỎ vì nó tìm thấy `except Exception: pass` trong
    chính docstring giải thích vì sao không dùng khuôn ấy nữa. Đây là lần
    thứ năm repo này mắc lỗi soi-nhầm-chú-thích — `tests/test_canh_gac.py`
    ghi lại những lần trước.
    """
    import io
    import tokenize

    ra = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            ra.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return " ".join(d for d in src.splitlines()
                        if not d.strip().startswith("#"))
    return " ".join(ra)


def test_khong_con_nuot_loi_im_lang():
    """
    `except Exception: pass` là loại hỏng repo này xếp nghiêm trọng nhất:
    không nổ, không ghi nhật ký, không ai biết.
    """
    for nguon in (_nguon_tao(), _nguon_webhook(), _nguon_bao_khach()):
        gon = _chi_ma(nguon).replace(" ", "")
        assert "exceptException:pass" not in gon
        assert "except:pass" not in gon


def test_khoa_chong_trung_gan_theo_MA_VAN_DON():
    """
    GHN phát lại webhook là chuyện thường. Khoá theo mã vận đơn thì lần phát
    thứ hai không sinh tin thứ hai cho khách.
    """
    khoi = _nguon_webhook().split("_bao_khach", 1)[1][:600]
    assert "ma_van_don" in khoi, "khoá chống trùng không gắn theo mã vận đơn"


# --- Tin báo là giao dịch, không phải quảng cáo ---

def test_tin_bao_la_giao_dich_khong_can_dong_y_marketing():
    """
    Báo mã vận đơn cho đơn khách vừa đặt là tin GIAO DỊCH. Xếp nhầm nó vào
    `marketing` là chốt chặn consent chặn luôn, và khách không bao giờ nhận
    được mã đơn của chính mình.
    """
    nguon = _nguon_tao() + _nguon_webhook()
    assert "marketing" not in nguon


# --- Hỏng thì phải thấy ---

def test_bao_khach_hong_khong_lam_hong_ca_van_don():
    """
    Vận đơn ĐÃ tạo ở phía hãng rồi. Để lỗi gửi tin làm cả hàm ném là hàng
    vẫn đi mà hệ thống tưởng chưa tạo — rồi có người tạo vận đơn thứ hai.
    """
    assert "except" in _nguon_bao_khach()


def test_hong_thi_ghi_nhat_ky():
    assert "log_event" in _nguon_bao_khach()
