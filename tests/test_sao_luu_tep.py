"""
Sao lưu ảnh sản phẩm và tệp nhân viên đã gửi (rà soát 20.11.2026).

Bản trước chỉ gói CSDL + `data/knowledge`: máy hỏng là mất `data/products`
(ảnh gửi cho khách) và `data/uploads` (tệp trong hội thoại khách).
`uploads` cùng mức nhạy cảm với CSDL nên có mật khẩu thì phải mã hoá.
"""
from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _du_lieu_gia(tmp_path, monkeypatch):
    from scripts import sao_luu

    goc = tmp_path / "repo"
    (goc / "data" / "products" / "SP1").mkdir(parents=True)
    (goc / "data" / "products" / "SP1" / "img.jpg").write_bytes(b"anh")
    (goc / "data" / "uploads").mkdir(parents=True)
    (goc / "data" / "uploads" / "x.png").write_bytes(b"tep khach")
    monkeypatch.setattr(sao_luu, "ROOT", goc)
    return sao_luu


def _ten(tar_bytes: bytes) -> set[str]:
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as t:
        return set(t.getnames())


def test_goi_ca_products_va_uploads(tmp_path, monkeypatch):
    sao_luu = _du_lieu_gia(tmp_path, monkeypatch)
    monkeypatch.setattr(sao_luu.settings, "sao_luu_mat_khau", "")
    ok, ghi = sao_luu.sao_luu_tep(tmp_path / "out" / "tep-1.tar.gz")
    assert ok, ghi
    ten = _ten((tmp_path / "out" / "tep-1.tar.gz").read_bytes())
    assert "products/SP1/img.jpg" in ten and "uploads/x.png" in ten


def test_co_mat_khau_thi_ma_hoa(tmp_path, monkeypatch):
    from scripts import goi_ma_hoa

    sao_luu = _du_lieu_gia(tmp_path, monkeypatch)
    monkeypatch.setattr(sao_luu.settings, "sao_luu_mat_khau", "mat-khau-thu-dai")
    ok, _ = sao_luu.sao_luu_tep(tmp_path / "out" / "tep-2.tar.gz")
    assert ok
    assert not (tmp_path / "out" / "tep-2.tar.gz").exists(), "tệp khách nằm dạng thường"
    ma = tmp_path / "out" / "tep-2.tar.gz.cskh"
    buf = io.BytesIO()
    with ma.open("rb") as f:
        goi_ma_hoa.giai_ma(f, buf, "mat-khau-thu-dai")
    assert "uploads/x.png" in _ten(buf.getvalue())


def test_vong_sao_luu_hang_ngay_goi_tep():
    src = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert "bk.sao_luu_tep" in src


def test_ghi_hong_giua_chung_khong_de_lai_tep_cut(tmp_path):
    """
    22.11.2026: ổ đầy giữa lúc gói, lệnh để lại `tep-*.tar.gz` cụt mang tên
    của bản tốt. Nay hỏng giữa chừng thì KHÔNG có tệp đích, không sót tệp tạm.
    """
    from scripts import sao_luu

    dich = tmp_path / "tep-1.tar.gz"

    def ghi_hong(p):
        p.write_bytes(b"mot nua")
        raise OSError(28, "No space left on device")

    try:
        sao_luu._ghi_nguyen_tu(dich, ghi_hong)
    except OSError:
        pass
    else:
        raise AssertionError("lỗi ghi phải nổ ra ngoài")
    assert not dich.exists()
    assert list(tmp_path.iterdir()) == []

    sao_luu._ghi_nguyen_tu(dich, lambda p: p.write_bytes(b"du"))
    assert dich.read_bytes() == b"du"


def test_ba_loai_sao_luu_deu_ghi_nguyen_tu():
    src = (ROOT / "scripts" / "sao_luu.py").read_text(encoding="utf-8")
    for ham in ("def sao_luu_db", "def sao_luu_tai_lieu", "def sao_luu_tep"):
        than = src[src.index(ham):]
        than = than[:than.index("\ndef ", 5)]
        assert "_ghi_nguyen_tu(" in than, ham
