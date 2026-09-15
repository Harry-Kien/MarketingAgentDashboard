"""
`chay_tunnel` phải chạy được tunnel CỐ ĐỊNH, và không bao giờ phá cấu hình ấy.

VÌ SAO
------
Tunnel tạm (`cloudflared tunnel --url`) cấp tên miền ngẫu nhiên mới mỗi lần
chạy. Đo trên hệ thống thật 14–15.09.2026: tên miền đổi BỐN lần trong 24
giờ, và một lần cổng công khai chết lúc 0h20 trong khi máy vẫn chạy bình
thường (app sống suốt đêm, người canh ghi `[tot] HTTP 200` mỗi 5 phút).

Mỗi lần đổi là Zalo OA và Facebook ngừng gọi được. Không nền tảng nào báo,
dashboard vẫn xanh, và tin khách rơi vào hư không — hỏng im lặng ở tầng
ngoài cùng, tầng mà không một lớp lưới nào trong `agent/core/agent.py` với
tới. Nên dán URL tạm vào Zalo Console là công sức bỏ đi.

BA RÀNG BUỘC CANH Ở ĐÂY
  * có `CLOUDFLARE_TUNNEL_TOKEN` thì đi đường cố định — kiểm TRƯỚC nhánh
    tạm, không thì đã cấu hình tên miền riêng mà script vẫn lặng lẽ dựng
    tunnel tạm rồi ghi đè `PUBLIC_BASE_URL` bằng một tên ngẫu nhiên;
  * đường cố định KHÔNG ghi `.env` — tên miền ở đó do người đặt, khớp với
    public hostname đã khai trên Cloudflare;
  * token KHÔNG bao giờ in ra: nó là chìa khoá mở đường vào máy chủ này từ
    Internet, và màn hình terminal thì hay bị chụp lại.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NGUON = (ROOT / "scripts" / "chay_tunnel.py").read_text(encoding="utf-8")
CAY = ast.parse(NGUON)
ENV_MAU = (ROOT / ".env.example").read_text(encoding="utf-8")


def _ham(ten: str) -> ast.FunctionDef:
    for node in ast.walk(CAY):
        if isinstance(node, ast.FunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


def _than(ten: str) -> str:
    lenh = _ham(ten).body
    if (lenh and isinstance(lenh[0], ast.Expr)
            and isinstance(lenh[0].value, ast.Constant)
            and isinstance(lenh[0].value.value, str)):
        lenh = lenh[1:]
    return "\n".join(ast.unparse(x) for x in lenh)


def test_co_duong_chay_tunnel_co_dinh():
    than = _than("chay_co_dinh")
    assert "'run'" in than and "'--token'" in than


def test_kiem_token_TRUOC_khi_dung_tunnel_tam():
    """
    Thứ tự là cả vấn đề: kiểm sau thì hệ thống đã cấu hình tên miền riêng
    vẫn bị dựng tunnel tạm và ghi đè PUBLIC_BASE_URL bằng tên ngẫu nhiên.
    """
    than = _than("main")
    i_token = than.find("CLOUDFLARE_TUNNEL_TOKEN")
    i_tam = than.find("'--url'")
    assert i_token != -1, "main không đọc CLOUDFLARE_TUNNEL_TOKEN"
    assert i_tam != -1, "main không còn đường tunnel tạm"
    assert i_token < i_tam, "kiểm token SAU khi đã dựng tunnel tạm"
    assert "return chay_co_dinh" in than


def test_duong_co_dinh_KHONG_ghi_de_env():
    """Tên miền cố định do NGƯỜI đặt; script ghi đè là tự phá cấu hình của họ."""
    assert "_doi_env" not in _than("chay_co_dinh")


def test_khong_bao_gio_in_token():
    than = _than("chay_co_dinh")
    for node in ast.walk(ast.parse(than)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
            assert "token" not in ast.unparse(node).lower(), ast.unparse(node)


def test_van_do_thong_tu_ngoai_truoc_khi_bao_xong():
    """
    Tunnel chạy KHÔNG có nghĩa là Internet vào được. Bản tunnel tạm đã học
    bài này rồi (xem `_thong`); đường cố định không được bỏ qua nó.
    """
    than = _than("chay_co_dinh")
    assert "_thong(" in than and "return 1" in than


def test_env_mau_khai_bao_khoa_moi():
    """Khoá không có trong `.env.example` là khoá không ai biết để bật."""
    assert "CLOUDFLARE_TUNNEL_TOKEN=" in ENV_MAU
    assert "Zero Trust" in ENV_MAU


def test_san_sang_canh_bao_khi_con_dung_tunnel_tam():
    """
    "Gọi tới được" vẫn chưa phải "đủ".

    Mục này từng chỉ hỏi "có phải https không" — báo ĐỦ cho một tên miền đã
    chết ba tiếng. Bản sau gọi THẬT vào URL, nên bắt được tunnel chết. Nhưng
    một tunnel tạm đang SỐNG vẫn là tunnel sẽ chết ở lần chạy lại tiếp theo
    (đo được bốn lần đổi trong 24 giờ), nên nó phải là CẢNH BÁO: "hôm nay
    chạy" khác với "dán một lần là xong".
    """
    from scripts.san_sang import CANH_BAO, DU, doc_callback_cong_khai

    # (url, mã HTTP, lỗi, đúng app này) — tunnel tạm đang sống.
    tam = doc_callback_cong_khai(
        "https://camping-cables-isle.trycloudflare.com/webhook", 200, None, True)
    assert tam["muc"] == CANH_BAO
    assert "TẠM" in tam["ghi"] and "chay_tunnel" in tam["sua"]

    co_dinh = doc_callback_cong_khai("https://api.tenmien.vn/webhook", 200, None, True)
    assert co_dinh["muc"] == DU

    # Hai nhánh của phiên kia phải còn nguyên: chết hẳn, và không phải app này.
    from scripts.san_sang import CHAN

    assert doc_callback_cong_khai(
        "https://api.tenmien.vn/webhook", None, "ConnectError", False)["muc"] == CHAN
    assert doc_callback_cong_khai(
        "https://api.tenmien.vn/webhook", 404, None, False)["muc"] == CANH_BAO


def test_tai_lieu_noi_ro_bon_buoc():
    assert "BẬT CHẾ ĐỘ CỐ ĐỊNH" in NGUON
    for buoc in ("Zero Trust", "Public hostname", "CLOUDFLARE_TUNNEL_TOKEN",
                 "PUBLIC_BASE_URL"):
        assert buoc in NGUON
