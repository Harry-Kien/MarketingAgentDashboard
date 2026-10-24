"""
Đóng gói container cho SaaS — kiểm tĩnh, không cần Docker.

Mỗi ràng buộc ở đây là một cách hỏng IM LẶNG khi host:
- image lọt .env → mọi cửa hàng mang khoá của máy phát triển;
- chạy root → một lỗ ở đường xử lý tệp khách gửi là chiếm cả container;
- shell script CRLF → container chết với "not found", trỏ sai hướng;
- hai tiến trình app một cửa hàng → outbox và lịch đăng bài chạy đôi.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
SIDECAR = (ROOT / "connectors/zalo-personal-sidecar/Dockerfile").read_text(encoding="utf-8")
IGNORE = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def test_khong_chay_root():
    assert re.search(r"^USER (?!root)\S+", DOCKERFILE, re.M)
    assert re.search(r"^USER node", SIDECAR, re.M)


def test_co_healthcheck():
    assert "HEALTHCHECK" in DOCKERFILE and "/healthz" in DOCKERFILE
    assert "HEALTHCHECK" in SIDECAR


def test_dockerignore_chan_bi_mat_va_du_lieu():
    for mau in (".env", ".env.*", ".git", ".venv"):
        assert mau in IGNORE, mau
    assert "!.env.example" in IGNORE
    # data/ là danh sách CHO PHÉP từ 24.10.2026 (xem tests/test_dockerignore.py):
    # chặn hết, rồi mở đúng mục git theo dõi — catalog thật và tệp khách không được mở.
    assert "data/*" in IGNORE
    assert "!data/catalog.json" not in IGNORE and "!data/uploads/" not in IGNORE


def test_mot_tien_trinh_moi_cua_hang():
    lenh = DOCKERFILE.split("\nCMD ", 1)[1]
    assert "--workers" not in lenh, "nhiều worker = vòng nền chạy đôi"
    assert "VAI_TRO_TIEN_TRINH=tat_ca" in DOCKERFILE


def test_volume_du_lieu_va_entrypoint_khong_ghi_de():
    assert 'VOLUME ["/app/data"]' in DOCKERFILE
    sh = (ROOT / "trien_khai/entrypoint.sh").read_text(encoding="utf-8")
    assert "cp -rn" in sh, "chép mặc định phải KHÔNG ghi đè dữ liệu cửa hàng"
    assert 'exec "$@"' in sh


def test_tep_chay_tren_linux_la_lf():
    """Kiểm byte trên đĩa VÀ luật trong .gitattributes — cả hai mới đủ."""
    for f in ("trien_khai/entrypoint.sh", "Dockerfile",
              "connectors/zalo-personal-sidecar/Dockerfile"):
        assert b"\r\n" not in (ROOT / f).read_bytes(), f
    ga = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.sh        text eol=lf" in ga and "Dockerfile  text eol=lf" in ga


def test_proxy_headers_de_biet_ip_that():
    assert "--proxy-headers" in DOCKERFILE
