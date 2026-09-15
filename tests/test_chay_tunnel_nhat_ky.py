"""
Bật tunnel không được thất bại vì một file NHẬT KÝ.

LỖI ĐÃ XẢY RA THẬT (15.09.2026)
-------------------------------
`scripts.chay_tunnel` tắt tunnel cũ xong, rồi `NHAT_KY.unlink()` ném:

    PermissionError: [WinError 32] The process cannot access the file
    because it is being used by another process: 'tunnel.log'

Trên Windows, tiến trình con vừa bị `taskkill` chưa nhả ngay cái handle ghi
log. Ngoại lệ không ai bắt, script chết — SAU KHI đã tắt tunnel đang chạy.

Kết quả tệ hơn lúc chưa chạy gì: trước đó còn một tunnel sống với tên miền
cũ, sau đó KHÔNG CÒN TUNNEL NÀO. Đo được: `san_sang` báo "URL công khai
không gọi tới được", và Zalo OA lẫn Facebook mất hẳn chiều nhận tin.

Thứ tự đúng của ưu tiên: tunnel là việc chính, nhật ký là thứ phụ. Không
mở được log thì đổi tên khác mà chạy, tuyệt đối không bỏ cuộc.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.chay_tunnel import mo_nhat_ky  # noqa: E402


def test_mo_duoc_thi_dung_dung_duong_da_cho(tmp_path):
    duong = tmp_path / "tunnel.log"
    f, thuc = mo_nhat_ky(duong)
    try:
        assert thuc == duong
    finally:
        f.close()


def test_file_bi_giu_thi_LUI_SANG_TEN_KHAC_chu_khong_nem(tmp_path):
    """Đúng ca đã cắn: handle của tiến trình vừa bị kill chưa nhả."""
    duong = tmp_path / "tunnel.log"
    da_thu: list[Path] = []

    def mo_gia(p, *a, **k):
        da_thu.append(Path(p))
        if Path(p) == duong:
            raise PermissionError(32, "being used by another process")
        return open(p, *a, **k)

    f, thuc = mo_nhat_ky(duong, mo=mo_gia, cho_giay=0.0)
    try:
        assert thuc != duong, "vẫn cố ghi vào đúng file đang bị giữ"
        assert thuc.parent == duong.parent
        assert duong in da_thu, "chưa thử đường chính lần nào"
    finally:
        f.close()


def test_moi_duong_deu_bi_giu_thi_van_tra_ve_cho_ghi_duoc(tmp_path):
    """
    Cạn đường trong thư mục repo thì vẫn phải chạy tiếp — ghi tạm đâu cũng
    được, miễn là tunnel lên.
    """
    duong = tmp_path / "tunnel.log"

    def mo_gia(p, *a, **k):
        if Path(p).parent == tmp_path:
            raise PermissionError(32, "being used by another process")
        return open(p, *a, **k)

    f, thuc = mo_nhat_ky(duong, mo=mo_gia, cho_giay=0.0)
    try:
        assert thuc.parent != tmp_path
        f.write("thu")
    finally:
        f.close()


def test_khong_con_unlink_truoc_khi_mo():
    """
    `open(..., "w")` đã tự cắt file về rỗng. `unlink` trước đó không thêm gì
    ngoài đúng một cách để hỏng trên Windows.
    """
    nguon = (ROOT / "scripts" / "chay_tunnel.py").read_text(encoding="utf-8")
    assert "NHAT_KY.unlink" not in nguon


def test_giet_tunnel_cu_CHO_tien_trinh_thoat_truoc_khi_di_tiep():
    """
    Kill rồi mở log ngay là canh một cuộc đua với hệ điều hành: `taskkill`
    trả về TRƯỚC khi tiến trình nhả xong handle ghi file.
    """
    from scripts import chay_tunnel

    da_nghi: list[float] = []

    class _KetQua:
        returncode = 0          # 0 = có tiến trình bị tắt

    n = chay_tunnel._giet_tunnel_cu(
        chay=lambda *a, **k: _KetQua(), nghi=da_nghi.append)

    assert n == 1
    assert da_nghi and da_nghi[0] > 0, "không chờ tiến trình nhả handle"


def test_khong_co_tunnel_nao_thi_khong_cho_vo_ich():
    """Không tắt gì thì không có handle nào để chờ — đừng bắt người dùng đợi."""
    from scripts import chay_tunnel

    da_nghi: list[float] = []

    class _KetQua:
        returncode = 1          # khác 0 = không tìm thấy tiến trình nào

    n = chay_tunnel._giet_tunnel_cu(
        chay=lambda *a, **k: _KetQua(), nghi=da_nghi.append)

    assert n == 0
    assert da_nghi == []
