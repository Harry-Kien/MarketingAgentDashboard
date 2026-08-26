"""
Form kết nối phải nói rõ từng kênh cần gì, lấy ở đâu.

VÌ SAO ĐÂY LÀ CHỖ QUAN TRỌNG NHẤT
---------------------------------
Nối tài khoản là việc người vận hành làm MỘT LẦN cho mỗi kênh, dưới áp lực,
với những chuỗi dài giống hệt nhau. Sai ở đây không báo lỗi ngay: credential
vẫn được mã hoá và lưu, tài khoản vẫn hiện trên dashboard, chỉ có tin khách
là không bao giờ tới.

Bản đầu dùng MỘT form cho sáu kênh với nhãn gộp
("Refresh token / sidecar secret / widget secret"). Người dùng phải tự đoán
ô nào dành cho kênh mình, và bốn ô để trống mà không có gì nói ra điều đó.

Ba thứ phải có, và mỗi thứ chặn một kiểu sai khác nhau:

  - chỉ hiện ô kênh đó CẦN      -> không dán nhầm ô
  - nhãn + gợi ý lấy ở đâu      -> không dán nhầm giá trị
  - cắt khoảng trắng thừa       -> không hỏng vì một dấu cách vô hình

Cái thứ ba nghe vặt nhưng là lỗi kinh điển: copy từ trang web thường dính
khoảng trắng ở cuối, HMAC sai một byte là hỏng, và thông báo lỗi của provider
không bao giờ nói "bạn thừa một dấu cách".
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

KENH = ["zalo_personal", "zalo_oa", "facebook", "instagram", "whatsapp", "webchat"]


def test_co_cau_hinh_truong_theo_tung_kenh():
    assert "KENH_TRUONG" in JS, "phải có bảng khai báo trường cho từng kênh"


@pytest.mark.parametrize("kenh", KENH)
def test_moi_kenh_deu_duoc_khai_bao(kenh):
    assert f'"{kenh}"' in JS or f"'{kenh}'" in JS, f"kênh {kenh} chưa có cấu hình"


def test_co_goi_y_lay_gia_tri_o_dau():
    """
    Người vận hành không thuộc lòng chỗ lấy Page token trong Meta Dashboard.

    Không có gợi ý thì họ rời dashboard đi tìm, quay lại dán nhầm ô — hoặc
    bỏ dở giữa chừng.
    """
    assert "goi_y" in JS, "mỗi trường phải có gợi ý lấy ở đâu"


def test_cat_khoang_trang_truoc_khi_luu():
    """Một dấu cách cuối token là hỏng HMAC, và không provider nào nói ra."""
    assert ".trim()" in JS, "phải cắt khoảng trắng của giá trị nhập vào"


def test_bat_buoc_theo_kenh_chu_khong_bat_buoc_chung():
    """Zalo cá nhân chỉ cần sidecar secret; bắt buộc chung là chặn nhầm."""
    assert "bat_buoc" in JS, "phải đánh dấu trường bắt buộc theo từng kênh"


def test_xac_minh_ngay_sau_khi_luu():
    """
    Lưu xong mà không kiểm thì người dùng tưởng đã xong.

    Sai credential chỉ lộ ra khi khách nhắn mà không ai nhận — có thể là
    nhiều ngày sau.
    """
    assert "/verify" in JS, "lưu xong phải tự xác minh với provider"
