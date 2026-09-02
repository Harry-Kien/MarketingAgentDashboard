"""Phiên hết hạn phải đưa người dùng về màn đăng nhập, không để họ đoán.

VÌ SAO
------
`api()` trong `dashboard/app.js` không xử lý 401. Hệ quả khi phiên hết hạn
giữa ca trực:

  1. Mọi panel hiện `res.statusText` — chữ "Unauthorized", tiếng Anh, giữa
     một giao diện tiếng Việt.
  2. Vòng làm mới 6 giây vẫn chạy, nên toast "Không nối được máy chủ:
     Unauthorized" bắn lại mỗi 6 giây, mãi mãi.
  3. Không chỗ nào bảo người dùng đăng nhập lại. Màn đăng nhập vẫn ẩn.

Ở contact center, người trực mở tab suốt ca. Phiên hết hạn là chuyện CHẮC
CHẮN xảy ra — do hết hạn thật, hoặc do máy chủ khởi động lại. Lúc đó họ nhìn
một màn hình đầy chữ Anh và không biết phải làm gì, trong khi khách vẫn đang
nhắn tới.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "dashboard" / "app.js"


def _than_api() -> str:
    ma = APP_JS.read_text(encoding="utf-8")
    i = ma.index("async function api(")
    return ma[i:ma.index("\n}", i)]


def test_api_xu_ly_401_rieng():
    than = _than_api()
    assert "401" in than, (
        "api() chưa phân biệt 401 với lỗi khác. Phiên hết hạn sẽ hiện ra như "
        "một lỗi mạng bất kỳ, và người trực không biết phải đăng nhập lại."
    )


def test_401_hien_lai_man_dang_nhap():
    than = _than_api()
    assert "#cong" in than, (
        "Gặp 401 phải hiện lại cổng đăng nhập (#cong). Không hiện thì người "
        "dùng nhìn một dashboard chết mà không có đường vào lại."
    )


def test_401_dung_vong_lam_moi():
    # Không dừng thì cứ 6 giây một toast lỗi, mãi mãi — và mỗi lần là một
    # request vô ích tới máy chủ.
    than = _than_api()
    assert "clearInterval" in than or "state.timer" in than, (
        "Gặp 401 phải dừng vòng làm mới 6 giây"
    )


def test_thong_bao_401_bang_tieng_viet():
    than = _than_api()
    assert re.search(r"[àáâãèéêìíòóôõùúýăđĩũơưạảấầẩẫậắằẳẵặẹẻẽếềể"
                     r"ễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", than, re.I), (
        "Thông báo 401 phải bằng tiếng Việt. 'Unauthorized' là chữ của tầng "
        "HTTP, không phải câu nói với người vận hành."
    )


def test_van_nem_loi_de_noi_goi_biet_ma_dung():
    # Nuốt lỗi thì panel gọi api() tưởng đã có dữ liệu và render undefined.
    than = _than_api()
    assert "throw" in than


def test_cu_phap_app_js_van_hop_le():
    ma = APP_JS.read_text(encoding="utf-8")
    assert ma.count("{") == ma.count("}")
    assert ma.count("(") == ma.count(")")
