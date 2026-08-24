"""
Mỗi dịch vụ hiện trên màn Sức khoẻ đều phải có đường khởi động.

VÌ SAO CẦN CA NÀY
-----------------
`agent/he_thong.py` liệt kê năm dịch vụ và hỏi sức khoẻ từng cái. Đó là
"một cổng vào duy nhất để nhớ" — nhưng nó chỉ có giá trị khi mọi ô trên đó
BẬT ĐƯỢC. Một dịch vụ được liệt kê mà không có gì khởi động nổi sẽ hiện đỏ
vĩnh viễn, và bảng giám sát luôn đỏ là bảng người ta ngừng đọc.

Đã xảy ra thật với n8n: README và `docs/phan-phoi-noi-dung.md` đều viết
"n8n đã chạy sẵn ở cổng 5678" và bảo người dùng mở trang đó ở bước đầu tiên
của phần đăng bài. Nhưng không có compose nào dựng nó. Trên máy vừa clone,
cổng 5678 chết, hướng dẫn đứt ngay bước 1, và không có gì trong hệ thống
nói ra điều đó — tài liệu khẳng định một chuyện, thực tế là chuyện khác.

Ca này buộc người thêm dịch vụ mới phải khai NÓ ĐẾN TỪ ĐÂU.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import he_thong  # noqa: E402

# Dịch vụ -> nguồn khởi động. Thêm dịch vụ vào `he_thong.DICH_VU` mà quên
# thêm vào đây là ca `test_moi_dich_vu_deu_khai_nguon` đỏ.
#
#   "app"       tiến trình chính, chạy bằng uvicorn — không phải container
#   file .yml   phải có service ĐÚNG TÊN đã khai bên trong file đó
#   "submodule" đến từ compose RIÊNG của ZaloCRM (giấy phép AGPL, không gộp)
NGUON = {
    # mã trên màn Sức khoẻ -> (nguồn, TÊN SERVICE trong compose đó)
    #
    # Tên service KHÔNG trùng mã, và đó là chuyện bình thường: ZaloCRM gọi
    # container của nó là `app`, Chatwoot gọi là `rails`. Ghi rõ cả hai ở
    # đây để phép kiểm bên dưới đối chiếu được đúng thứ, thay vì đoán.
    "dashboard": ("app", ""),
    "zalocrm": ("submodule", "app"),
    "chatwoot": ("docker-compose.chatwoot.yml", "rails"),
    "n8n": ("docker-compose.yml", "n8n"),
    "minio": ("submodule", "minio"),
}

# Submodule không được checkout trên bản clone sạch (CI đặt
# `submodules: false`), nên phần của nó chỉ kiểm khi có mặt.
SUBMODULE_COMPOSE = ROOT / "ZaloCRM" / "docker-compose.yml"


def _services(duong: Path) -> set[str]:
    """Tên service trong một file compose. Đọc thô, không cần thư viện yaml."""
    trong_services = False
    ten = set()
    for dong in duong.read_text(encoding="utf-8").splitlines():
        if dong.startswith("services:"):
            trong_services = True
            continue
        if trong_services and dong and not dong[0].isspace():
            break                      # sang khối cấp cao khác (volumes...)
        if trong_services and dong.startswith("  ") and not dong.startswith("   "):
            if dong.strip().endswith(":"):
                ten.add(dong.strip().rstrip(":"))
    return ten


def test_moi_dich_vu_deu_khai_nguon():
    thieu = [d["ma"] for d in he_thong.DICH_VU if d["ma"] not in NGUON]
    assert not thieu, (
        f"dịch vụ {thieu} hiện trên màn Sức khoẻ mà chưa khai khởi động từ đâu"
    )


def test_khong_khai_thua_dich_vu_da_bo():
    """Bỏ dịch vụ khỏi màn Sức khoẻ mà quên dọn ở đây thì bảng này thành
    tài liệu sai — loại rác khó thấy nhất."""
    co = {d["ma"] for d in he_thong.DICH_VU}
    thua = set(NGUON) - co
    assert not thua, f"khai nguồn cho dịch vụ không còn tồn tại: {sorted(thua)}"


def test_dich_vu_khai_tu_compose_thi_compose_that_su_co():
    """
    Đây là ca bắt được lỗi n8n. Khai "đến từ file này" mà file không có
    service ấy thì lời khai là văn xuôi, không phải sự thật kiểm được.
    """
    for ma, (nguon, service) in NGUON.items():
        if not nguon.endswith(".yml"):
            continue
        duong = ROOT / nguon
        assert duong.exists(), f"{nguon} không tồn tại"
        assert service in _services(duong), (
            f"{ma} khai đến từ {nguon}:{service} nhưng file đó không có service ấy"
        )


def test_dich_vu_tu_submodule_co_that_khi_submodule_da_checkout():
    """Bỏ qua trên bản clone sạch — ở đó `ZaloCRM/` rỗng có chủ ý."""
    if not SUBMODULE_COMPOSE.exists():
        return
    co = _services(SUBMODULE_COMPOSE)
    for ma, (nguon, service) in NGUON.items():
        if nguon == "submodule":
            assert service in co, (
                f"{ma} khai đến từ submodule:{service} nhưng compose của nó không có"
            )


def test_cong_tren_man_suc_khoe_khop_voi_compose():
    """
    Cổng lệch là kiểu hỏng tệ nhất: dịch vụ chạy tốt, màn hình vẫn đỏ, và
    người ta đi sửa thứ đang đúng.
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    n8n = next(d for d in he_thong.DICH_VU if d["ma"] == "n8n")
    assert "5678" in n8n["url"]
    assert "5678:5678" in compose


def test_n8n_khong_mo_ra_ca_mang_LAN():
    """
    Docker bind `0.0.0.0` theo mặc định và ĐI VÒNG QUA Windows Firewall —
    không có hộp thoại nào hỏi, nên lỗi này không bao giờ tự lộ ra. Ai ngồi
    chung WiFi cũng mở được n8n, mà n8n giữ OAuth Facebook/Instagram/TikTok
    của cửa hàng.

    `scripts/san_sang` canh việc này lúc chạy; ca này canh lúc viết mã.
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dong = [d.strip() for d in compose.splitlines()
            if d.strip().startswith("- \"") and "5678" in d]
    assert dong, "không tìm thấy khai báo cổng n8n"
    assert dong[0].startswith('- "127.0.0.1:'), dong[0]


def test_n8n_ghim_bang_digest():
    """
    `tests/test_ghim_anh.py` đã canh luật này cho mọi ảnh. Ca ở đây chỉ nói
    rõ vì sao n8n đặc biệt cần: ổ đĩa của nó giữ OAuth của Facebook và
    TikTok, và một bản nâng cấp ngoài ý muốn có thể mang theo di trú không
    lùi được cho đúng thứ mất 1-4 tuần chờ duyệt mới có lại.
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dong = [d.strip() for d in compose.splitlines()
            if d.strip().startswith("image:") and "n8n" in d]
    assert dong, "không tìm thấy image của n8n"
    assert "@sha256:" in dong[0], dong[0]


def test_o_dia_n8n_duoc_giu_lai():
    """
    Không gắn volume thì mỗi lần `docker compose down` là mất toàn bộ
    workflow VÀ credentials OAuth — thứ phải chờ 1-4 tuần duyệt mới có.
    """
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "n8n_data:/home/node/.n8n" in compose
    assert "\n  n8n_data:" in compose, "volume chưa khai ở khối volumes"
