"""
Không dịch vụ nội bộ nào được nghe trên mọi giao diện mạng.

VÌ SAO ĐÂY LÀ LỖI THẬT, KHÔNG PHẢI LO XA
-----------------------------------------
Docker publish cổng theo mặc định là bind `0.0.0.0`, tức mở ra CẢ MẠNG LAN.
Và nó đi VÒNG QUA Windows Firewall, nên không có hộp thoại nào hỏi, không
có gì báo. Ngồi chung WiFi quán cà phê là vào được.

`docker-compose.yml` đã cảnh báo đúng điều này cho n8n và buộc cổng 5678 về
127.0.0.1 — nhưng Postgres thì không, dù nó giữ toàn bộ hội thoại khách,
đơn hàng, hồ sơ Customer 360, và đăng nhập bằng `agent/agent`.

`scripts/san_sang` phát hiện ra khi CSDL chạy lần đầu. Test này để nó không
quay lại: sửa compose thì phải sửa có ý thức, không phải vì tiện tay.

Chỉ cổng của lớp proxy có chốt đăng nhập mới được ra ngoài.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Cổng ánh xạ ra máy chủ, dạng "1234:5678" hoặc "127.0.0.1:1234:5678".
_ANH_XA = re.compile(r'^\s*-\s*"([^"]+)"\s*(?:#.*)?$')


def _cong_publish(file: Path) -> list[tuple[str, int]]:
    """(chuỗi ánh xạ, số dòng) của mọi cổng được publish trong một compose."""
    ra: list[tuple[str, int]] = []
    trong_khoi_ports = False
    for so_dong, dong in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        if re.match(r"^\s*ports:\s*$", dong):
            trong_khoi_ports = True
            continue
        if trong_khoi_ports:
            khop = _ANH_XA.match(dong)
            if khop:
                ra.append((khop.group(1), so_dong))
                continue
            if dong.strip() and not dong.strip().startswith("#"):
                trong_khoi_ports = False
    return ra


@pytest.mark.parametrize("ten_file", ["docker-compose.yml"])
def test_moi_cong_deu_buoc_ve_localhost(ten_file):
    file = ROOT / ten_file
    if not file.exists():
        pytest.skip(f"{ten_file} không có trên máy này")

    ho_hang = [
        f"{ten_file}:{so_dong} -> {anh_xa}"
        for anh_xa, so_dong in _cong_publish(file)
        if not anh_xa.startswith("127.0.0.1:")
    ]
    assert not ho_hang, (
        "cổng đang mở ra cả mạng LAN (Docker bind 0.0.0.0 và đi vòng qua "
        "Windows Firewall):\n  " + "\n  ".join(ho_hang)
    )
