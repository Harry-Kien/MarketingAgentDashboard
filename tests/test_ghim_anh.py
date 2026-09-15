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

VÌ SAO DANH SÁCH FILE PHẢI TỰ TÌM
---------------------------------
Trước đây danh sách này được GÕ TAY: `["docker-compose.yml",
"docker-compose.chatwoot.yml"]`. `docker-compose.erpnext.yml` ra đời sau,
không ai thêm tên nó vào đây — và bốn dịch vụ ERPNext chạy thẻ trôi
(`frappe/erpnext:v15`, `mariadb:10.6`, `nginx:alpine`, `redis:6.2-alpine`)
trong khi cả năm phép kiểm dưới đây vẫn xanh.

Đó là xanh giả, đúng kiểu nguy hiểm nhất: có lưới, lưới báo an toàn, và
không ai đi kiểm lại. Lưới gõ tay chỉ canh được những gì người ta nhớ ra —
mà thứ cần canh nhất luôn là thứ vừa quên.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Chỉ quét thư mục gốc. Submodule (`ZaloCRM/`, `chatwoot-personal/`) mang
# compose riêng theo vòng đời và giấy phép của upstream, không phải thứ repo
# này được quyền sửa.
COMPOSE = sorted(p.name for p in ROOT.glob("docker-compose*.yml"))

sys.path.insert(0, str(ROOT))


def _dong_image(f: str) -> list[tuple[int, str]]:
    ra = []
    for i, d in enumerate((ROOT / f).read_text(encoding="utf-8").splitlines(), 1):
        d = d.strip()
        if d.startswith("image:") and not d.startswith("#"):
            ra.append((i, d))
    return ra


def test_tim_duoc_file_compose():
    """Canh chính cái lưới.

    Mọi phép kiểm dưới đây lặp trên `COMPOSE`. Glob hỏng — đổi tên file, đổi
    chỗ đặt, chạy pytest từ thư mục khác — thì `COMPOSE` rỗng, mọi vòng lặp
    chạy không lần nào, và cả file này XANH HẾT trong khi không canh gì cả.

    Đổi danh sách gõ tay sang glob mà không có phép kiểm này là đổi một kiểu
    xanh giả lấy một kiểu xanh giả khác.
    """
    assert COMPOSE, f"không thấy docker-compose*.yml nào trong {ROOT} — lưới đang canh rỗng"

    # Ba file đã biết. Thiếu một trong ba nghĩa là file bị đổi tên hoặc bị
    # xoá; cả hai trường hợp đều cần người nhìn, không được lặng lẽ bỏ qua.
    for ten in ("docker-compose.yml", "docker-compose.chatwoot.yml", "docker-compose.erpnext.yml"):
        assert ten in COMPOSE, f"{ten} không còn trong danh sách quét: {COMPOSE}"


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
