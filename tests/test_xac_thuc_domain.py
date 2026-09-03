"""
File xác thực quyền sở hữu domain — và cái bẫy bắt-tất suýt giết dashboard.

VÌ SAO CẦN

Zalo từ chối webhook cho tới khi domain được xác thực. Cách xác thực là đặt
một file ở gốc domain rồi Zalo tải về đối chiếu — họ không tra WHOIS, không
đòi DNS. Nghĩa là tên miền tạm kiểu `trycloudflare.com` VẪN xác thực được.

LỖI TỰ GÂY, BẮT ĐƯỢC NGAY LẦN CHẠY THỬ ĐẦU

Bản đầu dùng một mẫu bắt-tất `/{ten_file}` và đăng ký router ở CUỐI, tưởng
thế là đủ. Nhưng route khai bằng `@app.get` trong `main.py` nằm SAU mọi
`include_router`, nên mẫu bắt-tất vẫn khớp trước chúng:

    /healthz   -> 404
    /app.css   -> 404      dashboard mất sạch CSS

Ba đường tường minh (`/zalo_verifier{ma}.html`, `/google{ma}.html`,
`/{ten}.txt`) không thể va vào đường nào khác — thứ tự đăng ký thôi là
chuyện phải nhớ.

ĐÂY LÀ ĐƯỜNG KHÔNG CẦN ĐĂNG NHẬP

Bắt buộc, vì Zalo tải file khi chưa có phiên nào. Nên nó phải hẹp hết mức,
và các ca dưới canh đúng chuyện đó: không có ba chốt thì đây là một lỗ đọc
file tuỳ ý, phơi công khai.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api.xac_thuc_domain import hop_le, router  # noqa: E402

DUONG = {getattr(r, "path", "") for r in router.routes}


# ---------------------------------------------------------------
#  Không bắt-tất — lỗi đã gây ra
# ---------------------------------------------------------------

def test_khong_co_duong_bat_tat():
    """
    Mẫu `/{x}` khớp MỌI đường một đoạn. Đăng ký cuối cũng không cứu được,
    vì route khai bằng `@app.get` trong main.py nằm sau include_router.
    """
    for d in DUONG:
        assert d not in ("/{ten_file}", "/{ten}", "/{path}"), (
            f"{d} là mẫu bắt-tất — sẽ nuốt /healthz, /app.css và /"
        )


@pytest.mark.parametrize("he_thong", ["/healthz", "/", "/app.css", "/app.js", "/mcp"])
def test_khong_duong_nao_nuot_duong_he_thong(he_thong):
    """
    Ca canh trực tiếp lỗi đã gặp. Dựng router thật rồi hỏi Starlette xem
    đường hệ thống có khớp route nào của ta không.
    """
    from starlette.routing import Match

    scope = {"type": "http", "method": "GET", "path": he_thong,
             "path_params": {}, "headers": []}
    for r in router.routes:
        match, _ = r.matches(scope)
        assert match == Match.NONE, (
            f"{getattr(r, 'path', '?')} khớp {he_thong} — sẽ trả 404 cho một "
            "đường hệ thống đang hoạt động"
        )


def test_van_khop_duong_xac_thuc_that():
    """Chiều ngược lại: thu hẹp tới mức không khớp gì nữa thì vô dụng."""
    from starlette.routing import Match

    for p in ["/zalo_verifierAbC123.html", "/google0123456789abcdef.html",
              "/meta-xac-thuc.txt"]:
        scope = {"type": "http", "method": "GET", "path": p,
                 "path_params": {}, "headers": []}
        assert any(r.matches(scope)[0] != Match.NONE for r in router.routes), (
            f"không route nào khớp {p}"
        )


# ---------------------------------------------------------------
#  Chốt an toàn — đường này KHÔNG cần đăng nhập
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "ten",
    ["zalo_verifierAbC123.html", "google0123456789abcdef.html",
     "meta-domain-verification.txt"],
)
def test_ten_hop_le_thi_qua(ten):
    assert hop_le(ten) is True


@pytest.mark.parametrize(
    "ten",
    [
        "../.env", "..\\.env", "a/b.txt", "a\\b.txt",     # vượt thư mục
        ".env", "config.py", "catalog.json",              # tệp không phải xác thực
        "zalo_verifier.html",                             # mã quá ngắn
        "zalo_verifierABC.exe",                           # sai đuôi
        "", "   ",
        "x" * 200 + ".txt",                               # quá dài
    ],
)
def test_ten_khong_hop_le_bi_chan(ten):
    assert hop_le(ten) is False


def test_chan_vuot_thu_muc_TRUOC_khi_cham_dia():
    """
    `..` và gạch chéo bị chặn trước khi regex chạy. Dựa vào regex một mình
    là dựa vào việc mình viết regex không sót.
    """
    from agent.api import xac_thuc_domain as m

    nguon = (ROOT / "agent" / "api" / "xac_thuc_domain.py").read_text(encoding="utf-8")
    assert '".." in ten' in nguon
    assert m.hop_le("../abc.txt") is False


def test_thu_muc_bi_gitignore_chan():
    """
    File xác thực gắn với MỘT domain cụ thể. Đưa lên repo là đem theo dấu
    vết hạ tầng của cửa hàng sang mọi bản clone — vô dụng ở đó, và nói cho
    người đọc biết cửa hàng đang chạy ở đâu.
    """
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/xac_thuc_domain/" in ignore


def test_co_thu_muc_de_tha_file_vao():
    """Thiếu thư mục thì người vận hành phải tự tạo, và sẽ tạo sai chỗ."""
    assert (ROOT / "data" / "xac_thuc_domain").is_dir()
