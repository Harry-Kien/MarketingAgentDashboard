"""
`san_sang` phải bắt được URL công khai đã chết. Không gọi mạng, không cần CSDL.

VÌ SAO PHÉP KIỂM CŨ LÀ XANH GIẢ
-------------------------------
Bản trước chỉ hỏi một câu: chuỗi trong `.env` có bắt đầu bằng `https://`
không. Có thì báo ĐỦ.

Nhưng thứ cần canh không phải chuỗi — mà là tên miền tunnel, và tên miền
`trycloudflare` ĐỔI MỖI LẦN CHẠY. Khởi động lại máy là có tên miền mới;
quên dán lại URL webhook ở Meta và Zalo OA thì hai kênh ấy chết im lặng.
Trong khi đó `.env` vẫn giữ nguyên chuỗi cũ có chữ `https`, nên bảng
readiness vẫn xanh suốt thời gian tin khách rơi vào hư không.

Zalo cá nhân không đi qua tunnel (sidecar gọi thẳng 127.0.0.1), nên vẫn có
tin mới chảy vào dashboard. Đó là thứ làm sự cố này khó thấy nhất: hệ thống
trông như đang sống, chỉ thiếu hẳn hai kênh.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402

URL = "https://vi-du.trycloudflare.com/webhook"


def test_chua_co_https_thi_CANH_BAO():
    """Chạy nội bộ không tunnel là mặc định xuất xưởng hợp lệ, không phải lỗi."""
    kq = san_sang.doc_callback_cong_khai("http://host.docker.internal:8000/webhook", None, None, False)
    assert kq["muc"] == san_sang.CANH_BAO


def test_goi_khong_toi_thi_CHAN():
    """Tunnel chết = Zalo OA và Facebook mất chiều nhận. Đó là mất tin thật."""
    kq = san_sang.doc_callback_cong_khai(URL, None, "ConnectError", False)
    assert kq["muc"] == san_sang.CHAN
    # Lời sửa phải nói ra bước hay bị quên nhất, không chỉ "bật tunnel lên".
    assert "DÁN LẠI" in kq["sua"]


def test_toi_duoc_nhung_khong_phai_app_nay_thi_CANH_BAO():
    """Tên miền cũ có thể đã được cấp cho tunnel của người khác."""
    kq = san_sang.doc_callback_cong_khai(URL, 404, None, False)
    assert kq["muc"] == san_sang.CANH_BAO
    assert "404" in kq["ghi"]


def test_toi_dung_app_thi_DU():
    assert san_sang.doc_callback_cong_khai(URL, 200, None, True)["muc"] == san_sang.DU


def test_phep_kiem_nam_trong_bang_tong():
    """Viết hàm mà quên đưa vào `chay()` thì bảng readiness vẫn xanh giả."""
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    than_chay = nguon.split("async def chay()", 1)[1]
    assert "await kiem_callback_cong_khai()" in than_chay


def test_van_con_goi_mang_that():
    """
    Canh chính chỗ đã hỏng một lần.

    Bốn phép kiểm trên chỉ lái hàm phán quyết thuần — chúng vẫn xanh nguyên
    nếu ai đó bỏ phần gọi mạng và quay về so chuỗi, vì lúc ấy không nhánh
    nào trong số đó được gọi tới nữa. Phép kiểm này canh việc hàm thật sự
    ra ngoài hỏi.
    """
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    than = nguon.split("async def kiem_callback_cong_khai()", 1)[1].split("\nasync def ", 1)[0]
    assert "httpx" in than, "phép kiểm không còn gọi mạng — đã quay về so chuỗi"
    assert "/healthz" in than, "không còn xác minh URL trỏ về đúng ứng dụng này"
