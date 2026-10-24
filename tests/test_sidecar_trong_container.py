"""
Sidecar Zalo trong container phải KHỞI ĐỘNG ĐƯỢC.

24.10.2026, dựng thật lần đầu: Dockerfile đặt ZALO_SIDECAR_HOST=0.0.0.0
trong khi server.mjs cấm mọi địa chỉ khác localhost — container khởi động
lại vô hạn, Zalo cá nhân chết trên mọi bản triển khai Docker. Test của mặt
phẳng điều khiển dùng runner giả nên không thấy.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIDECAR = ROOT / "connectors" / "zalo-personal-sidecar"


def test_dockerfile_bat_co_container_khi_nghe_0000():
    df = (SIDECAR / "Dockerfile").read_text(encoding="utf-8")
    assert "ZALO_SIDECAR_HOST=0.0.0.0" in df
    assert "ZALO_SIDECAR_TRONG_CONTAINER=1" in df


def test_server_dung_chot_dia_chi_chung():
    src = (SIDECAR / "src" / "server.mjs").read_text(encoding="utf-8")
    assert "kiemDiaChiNghe(host, process.env)" in src


def test_compose_cua_hang_khong_publish_cong_sidecar():
    """Cờ container chỉ an toàn khi cổng 3210 KHÔNG mở ra máy chủ."""
    mau = (ROOT / "trien_khai" / "mau" / "compose.cua_hang.yml").read_text(encoding="utf-8")
    khoi = mau[mau.index("  sidecar:"):]
    khoi = khoi[:khoi.index("\nvolumes:")]
    assert "ports:" not in khoi
