"""
Kiểm thử việc ghim ảnh Docker. Không gọi API, không cần Docker.

VÌ SAO CANH VIỆC NÀY
--------------------
Thẻ `latest` không phải một phiên bản — nó là con trỏ, và nó DI CHUYỂN.
Hai máy chạy cùng một file compose, cùng một ngày, có thể chạy hai bản
Chatwoot khác nhau. Và `docker compose pull` bất kỳ lúc nào cũng có thể
kéo về một bản mới mang theo di trú CSDL không lùi được.

Với ứng dụng đang giữ toàn bộ hộp thư khách hàng, đó là rủi ro không chấp
nhận được — và nó hỏng theo kiểu tệ nhất: máy phát triển vẫn chạy bản cũ
đã tải, chỉ máy vừa cài mới gặp bản mới.

Thêm một dịch vụ mới rồi quên ghim là chuyện xảy ra trong một phút. File
này bắt trong một giây.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ["docker-compose.yml", "docker-compose.chatwoot.yml"]

sys.path.insert(0, str(ROOT))


def _dong_image(f: str) -> list[tuple[int, str]]:
    ra = []
    for i, d in enumerate((ROOT / f).read_text(encoding="utf-8").splitlines(), 1):
        d = d.strip()
        if d.startswith("image:") and not d.startswith("#"):
            ra.append((i, d))
    return ra


def test_moi_anh_deu_ghim_bang_digest():
    for f in COMPOSE:
        for dong, noi_dung in _dong_image(f):
            assert "@sha256:" in noi_dung, f"{f}:{dong} chưa ghim — {noi_dung}"


def test_khong_con_the_latest():
    """`latest` là con trỏ di chuyển, không phải phiên bản."""
    for f in COMPOSE:
        for dong, noi_dung in _dong_image(f):
            truoc_chu_thich = noi_dung.split("#")[0]
            assert ":latest" not in truoc_chu_thich, f"{f}:{dong}"


def test_digest_dung_dinh_dang():
    """sha256 phải đủ 64 ký tự hex. Cắt ngắn là docker từ chối kéo, và lỗi
    đó chỉ hiện ra trên máy chưa có sẵn ảnh."""
    mau = re.compile(r"@sha256:([0-9a-f]{64})\b")
    for f in COMPOSE:
        for dong, noi_dung in _dong_image(f):
            assert mau.search(noi_dung), f"{f}:{dong} digest sai định dạng"


def test_giu_lai_ten_the_trong_chu_thich():
    """
    Digest không đọc được bằng mắt. Không ghi thẻ gốc bên cạnh thì sáu
    tháng sau không ai biết mình đang chạy Chatwoot phiên bản nào, và
    không tra được changelog để nâng cấp.
    """
    for f in COMPOSE:
        for dong, noi_dung in _dong_image(f):
            assert "#" in noi_dung, f"{f}:{dong} thiếu chú thích tên thẻ"


def test_co_giai_thich_vi_sao_ghim():
    """Ràng buộc không kèm lý do là ràng buộc sẽ bị gỡ."""
    for f in COMPOSE:
        s = (ROOT / f).read_text(encoding="utf-8")
        assert "GHIM ẢNH BẰNG DIGEST" in s, f
