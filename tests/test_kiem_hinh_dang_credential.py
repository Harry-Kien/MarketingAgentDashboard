"""
Bắt lỗi DÁN NHẦM Ô ngay lúc lưu credential.

LỖI THẬT, NGƯỜI DÙNG GẶP HAI LẦN LIÊN TIẾP (03.09.2026)

Người dùng dán **Access token** (424 ký tự) vào ô **Secret key**. Trên
trang "Lấy Access Token" của Zalo Developers, hai thứ nằm ngay cạnh nhau,
và trên form của ta ô nào cũng là một chuỗi dài che bằng dấu chấm.

Hệ thống nhận, lưu vào kho mã hoá, báo thành công. Rồi tài khoản chuyển
`degraded` với `Invalid secret key` — thông điệp ĐÚNG nhưng không nói được
rằng họ dán nhầm Ô nào.

Họ thử lại, dán y hệt, hỏng y hệt. Vòng lặp ấy chỉ dừng khi có người đi đếm
độ dài chuỗi đang lưu — tức là phải mở terminal ra, không phải việc của
người vận hành.

Secret Key của Zalo là 32 ký tự. 424 ký tự không thể đúng ở bất kỳ phiên
bản nào.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.channels.kiem_hinh_dang import HinhDangSai, kiem  # noqa: E402

NGUON = (ROOT / "agent" / "api" / "channel_accounts.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------
#  Ca trung tâm — tái hiện đúng lỗi đã gặp
# ---------------------------------------------------------------

def test_access_token_dan_vao_o_secret_key_bi_chan():
    """424 ký tự — đúng con số đã đo được trên hệ thống thật."""
    with pytest.raises(HinhDangSai) as e:
        kiem("zalo_oa", {"secret_key": "H" * 424})
    thong_diep = str(e.value)
    assert "424" in thong_diep, "phải nói rõ đang dài bao nhiêu"
    assert "ACCESS TOKEN" in thong_diep, "phải đoán đúng thứ họ dán nhầm"
    assert "Cài đặt" in thong_diep, "phải chỉ đường lấy Secret Key thật"


def test_secret_key_dung_do_dai_thi_qua():
    """Secret Key thật của Zalo là 32 ký tự."""
    kiem("zalo_oa", {"secret_key": "a" * 32})


@pytest.mark.parametrize("n", [1, 16, 32, 64, 100])
def test_khong_chan_nham_do_dai_hop_ly(n):
    """
    Ranh giới đặt RỘNG RÃI. Ràng buộc đúng 32 sẽ hỏng vào ngày Zalo đổi
    định dạng — và lúc đó nó chặn một cấu hình hoàn toàn hợp lệ, ở một chỗ
    người dùng không sửa được.
    """
    kiem("zalo_oa", {"secret_key": "a" * n})


def test_khoang_trang_thua_khong_tinh_vao_do_dai():
    """Dán từ trình duyệt hay dính khoảng trắng — đừng chặn vì lý do đó."""
    kiem("zalo_oa", {"secret_key": "  " + "a" * 32 + "  "})


# ---------------------------------------------------------------
#  Không đụng thứ mình không hiểu
# ---------------------------------------------------------------

def test_refresh_token_dai_van_duoc_chap_nhan():
    """
    Refresh token của Zalo DÀI thật (đo được 419 ký tự trên hệ thống thật).
    Chặn nó là chặn một cấu hình đúng.
    """
    kiem("zalo_oa", {"refresh_token": "T" * 419, "secret_key": "a" * 32})


def test_kenh_chua_khai_thi_khong_kiem_gi():
    """
    Đây là lưới bắt lỗi dán nhầm ô, KHÔNG phải bộ xác thực credential. Thứ
    duy nhất xác thực được credential là provider.
    """
    kiem("facebook", {"secret_key": "x" * 9999})
    kiem("webchat", {"widget_secret": "y" * 9999})


def test_credential_rong_hoac_None_khong_no():
    kiem("zalo_oa", None)
    kiem("zalo_oa", {})


def test_gia_tri_khong_phai_chuoi_thi_bo_qua():
    """Kiểu sai là việc của Pydantic, không phải của lưới này."""
    kiem("zalo_oa", {"secret_key": 12345})
    kiem("zalo_oa", {"secret_key": None})


# ---------------------------------------------------------------
#  Cả HAI đường ghi credential đều phải kiểm
# ---------------------------------------------------------------

def _ham(ten: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(ast.parse(NGUON)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


@pytest.mark.parametrize("ham", ["create_account", "rotate_credentials"])
def test_ca_hai_duong_ghi_deu_kiem(ham):
    """
    `rotate_credentials` QUAN TRỌNG HƠN `create_account`: nó chính là đường
    người ta dùng để SỬA một credential dán nhầm. Không kiểm ở đó thì họ
    sửa, dán nhầm y hệt lần nữa, và lại nhận đúng một thông điệp vô nghĩa.
    """
    assert "kiem_hinh_dang" in ast.unparse(_ham(ham)), (
        f"{ham} không kiểm hình dạng credential"
    )


@pytest.mark.parametrize("ham", ["create_account", "rotate_credentials"])
def test_kiem_TRUOC_khi_luu(ham):
    """Kiểm sau khi lưu là đã ghi bí mật sai vào kho rồi mới báo lỗi."""
    than = _ham(ham)
    dong_kiem = dong_luu = None
    for n in ast.walk(than):
        if isinstance(n, ast.Call):
            t = ast.unparse(n.func)
            if "kiem_hinh_dang" in t and dong_kiem is None:
                dong_kiem = n.lineno
            if ("bo_sung_bi_mat_may_chu" in t) and dong_luu is None:
                dong_luu = n.lineno
    assert dong_kiem and dong_luu
    assert dong_kiem < dong_luu, f"{ham}: kiểm phải nằm TRƯỚC khi dựng credential"
