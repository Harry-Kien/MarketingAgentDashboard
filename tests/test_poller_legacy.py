"""
Poller ZaloCRM cũ chỉ được chạy khi có người BẬT nó một cách tường minh.

VÌ SAO CẦN TEST NÀY
-------------------
Trước lớp này, điều kiện khởi động poller là `if settings.zalocrm_api_key`.
Nghĩa là bất kỳ máy nào còn sót khoá cũ trong `.env` — rất dễ, vì `.env`
không đi theo repo và không ai dọn — sẽ chạy ĐỒNG THỜI cả hai đường nạp
tin: poller legacy và connector native.

Hậu quả: cùng một khách sinh hai hội thoại ở hai đường khác nhau, và không
có gì báo. Đúng loại hỏng im lặng mà CLAUDE.md cảnh báo.

Sự tồn tại của một khoá cấu hình KHÔNG PHẢI là ý định của người vận hành.
"""
from __future__ import annotations

from agent.main import nen_chay_poller_legacy


class _Cau_hinh:
    def __init__(self, *, api_key: str = "", bat: bool = False):
        self.zalocrm_api_key = api_key
        self.legacy_polling_bat = bat


def test_khong_chay_khi_chi_con_sot_api_key_cu():
    assert nen_chay_poller_legacy(_Cau_hinh(api_key="khoa-cu-con-sot")) is False


def test_chay_khi_duoc_bat_tuong_minh_va_co_khoa():
    assert nen_chay_poller_legacy(_Cau_hinh(api_key="khoa", bat=True)) is True


def test_khong_chay_khi_bat_nhung_thieu_khoa():
    """Bật mà không có khoá thì poller chỉ quay vòng vô ích."""
    assert nen_chay_poller_legacy(_Cau_hinh(bat=True)) is False


def test_lifespan_khong_con_nhanh_theo_khoa_tran():
    """
    Canh chỗ nối, không chỉ canh hàm.

    Hàm `nen_chay_poller_legacy` đúng mà `lifespan` vẫn tự kiểm khoá theo
    cách cũ thì chốt vô nghĩa. Test này đọc thẳng mã nguồn vì điều kiện nằm
    trong lifespan — thứ chỉ chạy khi cả ứng dụng khởi động.
    """
    import inspect

    import agent.main as main

    nguon = inspect.getsource(main)
    assert "if settings.zalocrm_api_key else None" not in nguon
    assert "nen_chay_poller_legacy()" in nguon
