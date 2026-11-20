"""
Đường dẫn tệp trong CSDL phải sống qua việc chuyển máy (laptop Windows → VPS).

Đo 20.11.2026: mọi `attachments.storage_key` là `D:\...\data\...` — lên VPS
Linux là mọi tệp đã gửi thành "Tệp không còn trên máy chủ".
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.duong_dan_du_lieu import GOC_DU_LIEU, khoa_luu, mo_khoa  # noqa: E402


def test_luu_tuong_doi_khi_nam_trong_data():
    p = GOC_DU_LIEU / "uploads" / "abc.jpg"
    assert khoa_luu(p) == "data/uploads/abc.jpg"
    assert mo_khoa("data/uploads/abc.jpg") == p


def test_dong_cu_tuyet_doi_windows_doc_duoc_tren_may_khac():
    cu = r"D:\Marketing Dasbhboard CSKH\data\products\AS-CL02\img_00.jpg"
    assert mo_khoa(cu) == GOC_DU_LIEU / "products" / "AS-CL02" / "img_00.jpg"
    cu_linux = "/opt/cskh/data/uploads/x.png"
    assert mo_khoa(cu_linux) == GOC_DU_LIEU / "uploads" / "x.png"


def test_ngoai_data_giu_nguyen():
    assert khoa_luu("/tmp/khac.txt") == "/tmp/khac.txt"
    assert mo_khoa(None) is None


def test_ba_cho_dung_khoa_tuong_doi():
    """Xếp hàng lưu khoá tương đối; worker và route tải tệp đều giải khoá."""
    src = {f: (ROOT / f).read_text(encoding="utf-8") for f in (
        "agent/omnichannel/outbound_service.py", "agent/workers/outbox_worker.py",
        "agent/api/hoi_thoai_cu.py")}
    assert "khoa_luu(path)" in src["agent/omnichannel/outbound_service.py"]
    assert "mo_khoa(" in src["agent/workers/outbox_worker.py"]
    assert "mo_khoa(" in src["agent/api/hoi_thoai_cu.py"]
