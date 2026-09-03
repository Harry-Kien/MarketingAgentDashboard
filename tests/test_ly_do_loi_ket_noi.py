"""
Sự kiện sức khoẻ phải nói LÝ DO, không chỉ nói loại ngoại lệ.

LỖI THẬT, NGƯỜI DÙNG BÁO (03.09.2026)

Người dùng điền đủ bốn ô Zalo OA, bấm Lưu, tài khoản chuyển `degraded`.
Dashboard không nói vì sao. Bảng `account_health_events` ghi:

    {"error_type": "RuntimeError"}

Trong khi Zalo đã trả lời rõ ràng: **Invalid secret key**.

Hệ thống BIẾT câu trả lời và ném nó đi. Người dùng ngồi đoán, rồi phải hỏi
lại — và chỉ moi ra được bằng cách chạy tay adapter.

`RuntimeError` một mình không hành động được: nó đúng cho cả "sai secret
key" lẫn "mạng chết". Hai lỗi ấy sửa bằng hai cách hoàn toàn khác nhau.

KHẲNG ĐỊNH THỨ HAI, QUAN TRỌNG KHÔNG KÉM: PHẢI CHE BÍ MẬT

Thông điệp lỗi của httpx thường kèm URL ĐẦY ĐỦ. Với Meta, URL ấy là
`debug_token?input_token=…&access_token=…`. Sự kiện sức khoẻ sống trong
CSDL và hiện lên dashboard — lâu hơn một dòng log — nên không che ở đây
thì bí mật nằm trong bảng ấy vĩnh viễn.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.channels.ly_do_loi import DAI_TOI_DA, chi_tiet_loi  # noqa: E402
from agent.nhat_ky import CHE  # noqa: E402

ADAPTER = ("messenger", "meta_channels", "zalo_oa", "zalo_personal")


# ---------------------------------------------------------------
#  Có lý do, không chỉ có loại
# ---------------------------------------------------------------

def test_giu_lai_ly_do_that():
    """Ca trung tâm: tái hiện đúng lỗi người dùng gặp."""
    exc = RuntimeError(
        "Zalo OA không trả access_token: {'error_name': 'Invalid secret key'}"
    )
    d = chi_tiet_loi(exc)
    assert d["error_type"] == "RuntimeError"
    assert "Invalid secret key" in d["ly_do"], (
        "lý do bị ném đi — người vận hành lại phải đoán như lần trước"
    )


def test_van_giu_loai_ngoai_le():
    """Loại vẫn cần: nó phân biệt lỗi mạng với lỗi xác thực khi lý do trống."""
    assert chi_tiet_loi(TimeoutError()).get("error_type") == "TimeoutError"


def test_ngoai_le_khong_co_thong_diep_thi_khong_co_khoa_rong():
    """
    Khoá `ly_do` rỗng hiện lên dashboard thành một dòng trống khó hiểu hơn
    là không có dòng nào.
    """
    d = chi_tiet_loi(RuntimeError())
    assert "ly_do" not in d


def test_cat_bot_thong_diep_qua_dai():
    """
    Traceback nội bộ nhét nguyên vào JSONB rồi hiện lên dashboard là một
    bức tường chữ mà người vận hành không đọc.
    """
    d = chi_tiet_loi(RuntimeError("x" * 5000))
    assert len(d["ly_do"]) <= DAI_TOI_DA


# ---------------------------------------------------------------
#  Che bí mật — sự kiện này sống lâu hơn một dòng log
# ---------------------------------------------------------------

def test_che_token_trong_thong_diep_loi():
    """
    Đây là lý do phải dùng lại bộ che của `nhat_ky`, không viết bộ thứ hai.
    URL của Meta trong thông điệp lỗi chứa ĐÚNG hai bí mật.
    """
    exc = RuntimeError(
        "HTTPError: GET https://graph.facebook.com/v23.0/debug_token"
        "?input_token=EAAR0uVcY6DCb9LIDHaZCgvTA9sSP4ZCkZCw"
        "&access_token=1254239285864497%7Ce4e86a2904de0af40d8b57ca51445a4d"
    )
    ly_do = chi_tiet_loi(exc)["ly_do"]
    assert "EAAR0uVcY6DCb9LIDHaZ" not in ly_do
    assert "e4e86a2904de0af40d8b" not in ly_do
    assert CHE in ly_do
    # Vẫn phải đọc được là gọi đi đâu, nếu không thì che mất luôn giá trị
    # chẩn đoán và người ta sẽ gỡ bộ che.
    assert "graph.facebook.com" in ly_do


def test_che_mat_khau_trong_chuoi_ket_noi():
    exc = RuntimeError("could not connect: postgresql://agent:MatKhauThat@db:5432/x")
    assert "MatKhauThat" not in chi_tiet_loi(exc)["ly_do"]


def test_dung_lai_bo_che_cua_nhat_ky_khong_viet_bo_thu_hai():
    """
    Hai bộ che thì cái yếu hơn quyết định. Đọc AST để chắc module này gọi
    `nhat_ky.che`, không tự dựng regex riêng.
    """
    nguon = (ROOT / "agent" / "channels" / "ly_do_loi.py").read_text(encoding="utf-8")
    assert "nhat_ky.che" in nguon
    for node in ast.walk(ast.parse(nguon)):
        if isinstance(node, ast.Call) and "re.compile" in ast.unparse(node.func):
            raise AssertionError("ly_do_loi.py tự dựng regex che — dùng nhat_ky")


# ---------------------------------------------------------------
#  Bốn adapter đều phải dùng, không adapter nào bị bỏ quên
# ---------------------------------------------------------------

@pytest.mark.parametrize("ten", ADAPTER)
def test_adapter_khong_con_nem_ly_do_di(ten):
    """
    Bốn adapter cùng chép một dòng `detail={"error_type": ...}`. Sửa ba
    quên một thì đúng kênh bị quên sẽ im lặng như cũ — và không ai biết cho
    tới lúc nối kênh đó.
    """
    nguon = (ROOT / "agent" / "channels" / f"{ten}.py").read_text(encoding="utf-8")
    assert 'detail={"error_type": type(exc).__name__}' not in nguon, (
        f"{ten}.py còn ném lý do đi"
    )
    assert "chi_tiet_loi(exc)" in nguon, f"{ten}.py chưa dùng chi_tiet_loi"


@pytest.mark.parametrize("ten", ADAPTER)
def test_adapter_van_parse_duoc(ten):
    """
    Chèn import bằng script dễ rơi vào giữa một `from x import (` nhiều
    dòng — đã xảy ra đúng như vậy khi sửa `meta_channels.py`.
    """
    ast.parse((ROOT / "agent" / "channels" / f"{ten}.py").read_text(encoding="utf-8"))
