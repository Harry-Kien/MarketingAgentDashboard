"""
Kiểm thử chiến dịch đa nền tảng. Không gọi API model.

Canh ba thứ:
  1. Chiến dịch KHÔNG được là đường vòng qua khâu duyệt.
  2. Giãn giờ đăng phải thật sự giãn — ô "giãn cách" từng im lặng không
     làm gì khi người dùng không nhập giờ bắt đầu.
  3. Một kênh soạn hỏng không được kéo đổ cả chiến dịch.
"""
from __future__ import annotations

import inspect
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.publish import chien_dich  # noqa: E402
from agent.publish.registry import KENH_HO_TRO  # noqa: E402


# =====================================================================
#  Không được vòng qua khâu duyệt
# =====================================================================

def test_chien_dich_khong_tu_dang():
    """
    `tao()` chỉ được gọi `tao_bai` (luôn đặt cho_duyet), tuyệt đối không
    gọi `dang_bai` hay `duyet`. Soạn nhanh hơn không có nghĩa là được
    quyết định thay người.
    """
    src = inspect.getsource(chien_dich.tao)
    for cam in ("dang_bai(", "duyet(", "trang_thai="):
        assert cam not in src, f"chiến dịch đang vòng qua khâu duyệt: {cam!r}"
    assert "tao_bai(" in src


def test_moi_bai_soan_rieng_cho_tung_kenh():
    """
    Copy-paste một caption ra bốn chỗ là cách làm đa nền tảng phổ biến
    nhất và kém hiệu quả nhất. Phải gọi copywriter RIÊNG cho mỗi kênh.
    """
    src = inspect.getsource(chien_dich)
    assert "_soan_mot(k, san_pham, y_tuong, video_id) for k in kenh" in src, (
        "phải soạn riêng từng kênh, không dùng chung một bản"
    )


# =====================================================================
#  Lọc kênh
# =====================================================================

def test_kenh_khong_hop_le_bi_loai():
    import asyncio
    with pytest.raises(ValueError, match="Không có kênh hợp lệ"):
        asyncio.run(chien_dich.tao(ten="x", kenh=["linkedin", "twitter"]))


def test_kenh_trung_lap_chi_tinh_mot_lan():
    """dict.fromkeys giữ thứ tự và bỏ trùng — hai bài Facebook là lãng phí."""
    src = inspect.getsource(chien_dich.tao)
    assert "dict.fromkeys(kenh)" in src


def test_moi_kenh_ho_tro_deu_co_giong_rieng():
    from agent.publish.copywriter import _GIONG
    thieu = set(KENH_HO_TRO) - set(_GIONG)
    assert not thieu, f"kênh chưa có hướng dẫn giọng văn riêng: {sorted(thieu)}"


# =====================================================================
#  Giãn giờ đăng
# =====================================================================

def test_gian_cach_co_tac_dung_khi_khong_nhap_gio_bat_dau():
    """
    Từng là bẫy thật: người dùng điền 'giãn cách 30 phút' rồi thấy cả bốn
    bài đăng cùng một lúc, vì không nhập giờ bắt đầu nên mốc là None và
    lịch của mọi bài đều None.
    """
    src = inspect.getsource(chien_dich.tao)
    assert "gian_cach_phut > 0 and len(kenh) > 1" in src, (
        "thiếu mốc mặc định — ô giãn cách sẽ im lặng không làm gì"
    )


def test_mot_kenh_thi_khong_can_gian_cach():
    """Giãn cách chỉ có nghĩa khi có từ hai bài trở lên."""
    src = inspect.getsource(chien_dich.tao)
    assert "len(kenh) > 1" in src


def test_gio_khong_mui_duoc_coi_la_utc():
    src = inspect.getsource(chien_dich.tao)
    assert "moc.replace(tzinfo=timezone.utc)" in src, (
        "so sánh datetime có múi với không múi sẽ ném TypeError giữa lúc duyệt"
    )


# =====================================================================
#  Một kênh hỏng không kéo đổ cả chiến dịch
# =====================================================================

def test_kenh_hong_duoc_bao_cao_chu_khong_nuot():
    src_soan = inspect.getsource(chien_dich._soan_mot)
    assert "except Exception" in src_soan and '"loi"' in src_soan

    src_tao = inspect.getsource(chien_dich.tao)
    assert "kenh_hong" in src_tao, "phải nói rõ kênh nào soạn hỏng"
    assert "hong.append" in src_tao


def test_ket_qua_luon_noi_ro_can_duyet():
    src = inspect.getsource(chien_dich.tao)
    assert "chờ duyệt" in src and "không tự đăng" in src, (
        "kết quả phải nói rõ bài chưa đăng, tránh người dùng tưởng đã xong"
    )
