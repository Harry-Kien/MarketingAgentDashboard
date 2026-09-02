"""
Bí mật không được lọt vào nhật ký.

LỖI THẬT ĐÃ GẶP (03.09.2026). `httpx` ghi URL đầy đủ kèm query string ở mức
INFO. Bộ kiểm sức khoẻ token Meta gọi `debug_token?input_token=…&
access_token=…`, nên MỖI lần canh gác chạy là hai bí mật vào log — không
lỗi, không cảnh báo, không ai biết.

Log bị chụp màn hình, dán vào issue, gom về máy chủ log tập trung. Một
token trong log phải coi như đã lộ.

Ca quan trọng nhất tệp này: `test_httpx_khong_con_ghi_o_muc_INFO` và
`test_che_dung_ca_URL_that_da_ro_ri`.
"""
from __future__ import annotations

import logging
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.nhat_ky import CHE, LocBiMat, che, dung_nhat_ky  # noqa: E402


# ---------------------------------------------------------------
#  Che theo tên tham số
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "tham_so",
    ["access_token", "input_token", "refresh_token", "api_key", "api_secret",
     "client_secret", "password", "secret", "token", "signature"],
)
def test_che_moi_tham_so_bi_mat(tham_so):
    ra = che(f"https://x.test/a?{tham_so}=SIEU_BI_MAT_123456&ok=1")
    assert "SIEU_BI_MAT_123456" not in ra
    assert CHE in ra


def test_giu_lai_tham_so_khong_bi_mat():
    """
    Che quá tay thì nhật ký gỡ lỗi mất hết giá trị. `fields=[...]` của
    ERPNext chứa chữ "code" và không được đụng tới.
    """
    goc = 'GET /api/resource/Bin?fields=["actual_qty","warehouse"]&limit_page_length=0'
    assert che(goc) == goc


def test_che_dung_ca_URL_that_da_ro_ri():
    """URL nguyên văn lấy từ log đã rò. Cả HAI bí mật phải biến mất."""
    goc = (
        "HTTP Request: GET https://graph.facebook.com/v23.0/debug_token"
        "?input_token=EAAR0uVcY6DCb9LIDHaZCgvTA9sSP4ZCkZCwCM6uz9F8j"
        "&access_token=1254239285864497%7Ce4e86a2904de0af40d8b57ca51445a4d"
        ' "HTTP/1.1 200 OK"'
    )
    ra = che(goc)
    assert "EAAR0uVcY6DCb9LIDHaZCgvTA9sSP4ZCkZCwCM6uz9F8j" not in ra
    assert "e4e86a2904de0af40d8b57ca51445a4d" not in ra
    # Vẫn phải đọc được là gọi đi đâu — che mà mất luôn khả năng gỡ lỗi thì
    # người ta sẽ tắt bộ lọc.
    assert "graph.facebook.com" in ra
    assert "debug_token" in ra


def test_che_mat_khau_trong_url_nhung_giu_ten_dang_nhap():
    ra = che("postgresql://agent:MatKhauSieuBiMat@localhost:5433/marketing_agent")
    assert "MatKhauSieuBiMat" not in ra
    assert "agent" in ra and "localhost:5433" in ra


@pytest.mark.parametrize("kieu", ["Bearer", "bearer", "Basic", "token"])
def test_che_header_authorization(kieu):
    ra = che(f"Authorization: {kieu} abcdef1234567890XYZ")
    assert "abcdef1234567890XYZ" not in ra


def test_chuoi_rong_khong_no():
    assert che("") == ""
    assert che(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------
#  Che theo GIÁ TRỊ — bắt cả đường chưa biết
# ---------------------------------------------------------------

def test_che_gia_tri_bi_mat_o_bat_ky_dau():
    """
    Che theo tên tham số chỉ bắt được query string. Bí mật còn lọt qua thân
    JSON, qua header in trong traceback, qua một print(cfg) nào đó.
    """
    bm = ("TOKEN_THAT_SU_RAT_DAI_123",)
    ra = che('{"cau_hinh": {"gi_do": "TOKEN_THAT_SU_RAT_DAI_123"}}', bm)
    assert "TOKEN_THAT_SU_RAT_DAI_123" not in ra
    assert CHE in ra


def test_khong_quet_gia_tri_qua_ngan():
    """
    Chuỗi ngắn dễ trùng một từ bình thường trong dòng log. Che nhầm còn tệ
    hơn không che — người ta mất niềm tin vào nhật ký.
    """
    from agent.nhat_ky import _DAI_TOI_THIEU

    assert _DAI_TOI_THIEU >= 8


# ---------------------------------------------------------------
#  Bộ lọc gắn vào handler
# ---------------------------------------------------------------

def test_loc_che_ban_ghi_that(caplog):
    loc = LocBiMat()
    ban_ghi = logging.LogRecord(
        name="httpx", level=logging.INFO, pathname="x", lineno=1,
        msg="GET https://a.test/?access_token=%s", args=("BI_MAT_RAT_DAI_9999",),
        exc_info=None,
    )
    loc.filter(ban_ghi)
    assert "BI_MAT_RAT_DAI_9999" not in ban_ghi.getMessage()


def test_bi_mat_bi_cat_doi_giua_mau_va_tham_so_van_bi_che():
    """
    Che riêng `msg` rồi che riêng từng `args` thì bí mật bị cắt đôi giữa
    hai bên không mảnh nào khớp mẫu. Phải dựng chuỗi cuối rồi che một lần.
    """
    loc = LocBiMat()
    ban_ghi = logging.LogRecord(
        name="httpx", level=logging.INFO, pathname="x", lineno=1,
        msg="GET /a?access_token=%s", args=("PHAN_CUOI_BI_MAT_123",),
        exc_info=None,
    )
    loc.filter(ban_ghi)
    assert "PHAN_CUOI_BI_MAT_123" not in ban_ghi.getMessage()


def test_loc_khong_bao_gio_nuot_ban_ghi():
    """
    `filter()` trả False là VỨT bản ghi. Bộ lọc này để CHE, không để lọc
    bỏ — nuốt mất một dòng lỗi là một sự cố không ai điều tra được.
    """
    loc = LocBiMat()
    for msg in ["bình thường", "access_token=abc", "", "%s không có args"]:
        r = logging.LogRecord("x", logging.ERROR, "p", 1, msg, None, None)
        assert loc.filter(r) is True


def test_loc_gan_vao_handler_khong_trung_lap():
    """Gọi `dung_nhat_ky()` nhiều lần không được chồng bộ lọc lên nhau."""
    h = logging.StreamHandler()
    logging.getLogger().addHandler(h)
    try:
        dung_nhat_ky()
        dung_nhat_ky()
        dung_nhat_ky()
        assert sum(isinstance(f, LocBiMat) for f in h.filters) == 1
    finally:
        logging.getLogger().removeHandler(h)


# ---------------------------------------------------------------
#  httpx không được ghi URL nữa
# ---------------------------------------------------------------

def test_httpx_khong_con_ghi_o_muc_INFO():
    """
    Ca canh ĐÚNG đường đã rò. `httpx` ở INFO là ghi URL đầy đủ kèm query
    string cho mọi lời gọi ra ngoài.
    """
    dung_nhat_ky()
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


def test_main_goi_dung_nhat_ky_ngay_dau_lifespan():
    """
    Cài bộ lọc sau lời gọi HTTP đầu tiên là đã muộn. Đọc AST chứ không so
    chuỗi — ba lần trước trong repo này, test so chuỗi đã bắt đúng đoạn chú
    thích giải thích vì sao không được viết như vậy.
    """
    import ast

    cay = ast.parse((ROOT / "agent" / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(cay):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            dau = node.body[0]
            assert isinstance(dau, ast.Expr), "câu lệnh đầu lifespan phải là lời gọi"
            assert "dung_nhat_ky" in ast.unparse(dau), (
                f"lifespan bắt đầu bằng {ast.unparse(dau)[:60]!r} chứ không "
                "phải dung_nhat_ky() — bí mật rò trong khoảng trước đó"
            )
            return
    raise AssertionError("không tìm thấy lifespan trong agent/main.py")
