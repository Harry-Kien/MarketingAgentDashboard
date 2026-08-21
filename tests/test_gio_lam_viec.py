"""
Kiểm thử giờ làm việc. Không gọi API, không cần CSDL.

Cả hệ thống được xây quanh nguyên tắc "không phát ngôn không có căn cứ":
giá phải từ tool, tồn kho phải từ tool, thiếu căn cứ thì chuyển người.

Rồi ở đúng bước cuối, nó nói với khách lúc 2 giờ sáng rằng "bạn ấy sẽ nhắn
lại cho mình sớm nhé" — trong khi không ai đang trực. Đó là chỗ hở cuối
cùng trong nguyên tắc ấy, và file này canh nó.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import settings  # noqa: E402
from agent.core import gio_lam_viec as glv  # noqa: E402


def _vn(gio: int, phut: int = 0) -> datetime:
    return datetime(2026, 8, 21, gio, phut, tzinfo=glv.VN)


# =====================================================================
#  Múi giờ
# =====================================================================

def test_mui_gio_viet_nam_la_utc_cong_7():
    """
    Cộng tay chứ không dùng zoneinfo: Windows KHÔNG có sẵn cơ sở dữ liệu
    múi giờ IANA, thiếu gói `tzdata` là ném ZoneInfoNotFoundError. Một chốt
    nghiệp vụ không được phép hỏng vì lý do đó.
    """
    assert glv.VN.utcoffset(None) == timedelta(hours=7)


def test_doi_dung_tu_utc():
    utc = datetime(2026, 8, 21, 2, 0, tzinfo=timezone.utc)   # 09:00 giờ VN
    assert glv.gio_vn(utc).hour == 9


def test_thoi_gian_khong_co_mui_thi_coi_la_utc():
    """`datetime.utcnow()` trả về thứ không có múi giờ. Đoán sai là lệch
    bảy tiếng, và lệch bảy tiếng thì cả chốt này vô nghĩa."""
    assert glv.gio_vn(datetime(2026, 8, 21, 2, 0)).hour == 9


# =====================================================================
#  Trong giờ / ngoài giờ
# =====================================================================

def test_giua_ngay_la_trong_gio():
    assert glv.dang_trong_gio(_vn(14))


def test_hai_gio_sang_la_ngoai_gio():
    assert not glv.dang_trong_gio(_vn(2))


def test_bien_dong_mo():
    """
    Khoảng [bat_dau, ket_thuc): 20:59 còn trong giờ, 21:00 thì hết. Người
    trực cuối ca cần biết chính xác lúc nào mình được về.
    """
    assert glv.dang_trong_gio(_vn(settings.gio_lam_viec_bat_dau, 0))
    assert glv.dang_trong_gio(_vn(settings.gio_lam_viec_ket_thuc - 1, 59))
    assert not glv.dang_trong_gio(_vn(settings.gio_lam_viec_ket_thuc, 0))
    assert not glv.dang_trong_gio(_vn(settings.gio_lam_viec_bat_dau - 1, 59))


def test_tat_di_thi_luc_nao_cung_trong_gio(monkeypatch):
    """Tiệm trực 24/7 phải tắt được chốt này, không phải sửa mã."""
    monkeypatch.setattr(settings, "gio_lam_viec_bat", False)
    assert glv.dang_trong_gio(_vn(3))


def test_cau_hinh_vo_ly_thi_hong_theo_huong_phuc_vu_khach(monkeypatch):
    """
    Ai đó gõ nhầm 21 → 8. Coi như trực suốt ngày thì tệ nhất là hứa hơi
    lạc quan; coi như đóng cửa suốt ngày thì mọi khách đều bị đuổi về.
    """
    monkeypatch.setattr(settings, "gio_lam_viec_bat_dau", 21)
    monkeypatch.setattr(settings, "gio_lam_viec_ket_thuc", 8)
    assert glv.dang_trong_gio(_vn(3))
    assert glv.dang_trong_gio(_vn(14))


# =====================================================================
#  Câu báo cho khách
# =====================================================================

def test_trong_gio_giu_nguyen_cau_cu():
    assert glv.tin_chuyen_nguoi(_vn(14)) == settings.tin_chuyen_nguoi


def test_ngoai_gio_khong_duoc_hua_sap_nhan_duoc():
    """
    "Sớm" lúc 2 giờ sáng nghĩa là sáu tiếng nữa. Khách nằm chờ một tin
    không tới, và đó là lời hứa hệ thống không giữ được.
    """
    tin = glv.tin_chuyen_nguoi(_vn(2))
    assert tin != settings.tin_chuyen_nguoi
    assert "sớm" not in tin


def test_ngoai_gio_phai_noi_ro_may_gio_co_nguoi():
    """Khách biết mình chờ tới bao giờ thì chờ được. Không biết thì bỏ đi."""
    tin = glv.tin_chuyen_nguoi(_vn(2))
    assert f"{settings.gio_lam_viec_bat_dau} giờ" in tin


def test_cau_bao_van_la_chuoi_co_dinh_khong_phai_loi_model():
    """
    Lúc agent tự nhận không đủ thẩm quyền chính là lúc KHÔNG nên để nó tự
    chọn chữ. Câu cố định không thể chứa lời khuyên, không thể hứa gì, và
    không thể vi phạm luật quảng cáo.
    """
    for t in (_vn(2), _vn(14)):
        assert glv.tin_chuyen_nguoi(t) in (
            settings.tin_chuyen_nguoi,
            settings.tin_chuyen_nguoi_ngoai_gio.format(
                gio_mo=f"{settings.gio_lam_viec_bat_dau} giờ"
            ),
        )
