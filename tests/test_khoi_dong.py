"""
Dựng hệ thống bằng một lệnh — và không được nói dối về kết quả.

LỖI THẬT, ĐO ĐƯỢC (03.09.2026)

Máy tắt lúc 19:52, bật lại lúc 22:41. Không cổng nào trong 8000/5433/3210/
5678 còn nghe. Docker Desktop, Postgres, n8n, uvicorn, sidecar Node,
cloudflared — cả sáu đều không tự lên lại. Riêng các container ERPNext thì
lên, vì chúng CÓ SẴN `restart: unless-stopped`.

Ba tiếng đó khách nhắn vào rơi vào hư không. Không lỗi, không nhật ký, và
dashboard cũng không chạy để mà hiện đỏ. Đây là hỏng im lặng ở tầng tiến
trình — tầng mà sáu lớp lưới trong `agent/core/agent.py` không với tới.

VÌ SAO SOI BẰNG AST

Docstring của chính các test này chứa đủ chữ "restart: unless-stopped",
"uvicorn", "bat_lai". Quét chuỗi trên cả tệp thì xanh nhờ đọc trúng lời
giải thích của chính nó — xanh giả, cái bẫy đã dính năm lần trong repo này.
"""
from __future__ import annotations

import ast
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NGUON = (ROOT / "scripts" / "khoi_dong.py").read_text(encoding="utf-8")
CAY = ast.parse(NGUON)
COMPOSE = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _ham(ten: str) -> ast.FunctionDef:
    for node in ast.walk(CAY):
        if isinstance(node, ast.FunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


def _than(ten: str) -> str:
    """Thân hàm, ĐÃ BỎ docstring — xem lý do ở cuối phần mô tả tệp."""
    lenh = _ham(ten).body
    if (lenh and isinstance(lenh[0], ast.Expr)
            and isinstance(lenh[0].value, ast.Constant)
            and isinstance(lenh[0].value.value, str)):
        lenh = lenh[1:]
    return "\n".join(ast.unparse(x) for x in lenh)


# ---------------------------------------------------------------
#  Docker phải tự lên lại — nửa hệ thống này KHÔNG cần người
# ---------------------------------------------------------------

def _services() -> dict[str, str]:
    """Cắt `docker-compose.yml` thành từng khối service."""
    than = COMPOSE.split("\nservices:\n", 1)[-1].split("\nvolumes:", 1)[0]
    khoi, ten = {}, None
    for dong in than.splitlines():
        m = re.match(r"^  ([a-z0-9_-]+):\s*$", dong)
        if m:
            ten = m.group(1)
            khoi[ten] = ""
        elif ten:
            khoi[ten] += dong + "\n"
    return khoi


def test_co_service_de_kiem():
    assert _services(), "không cắt được service nào — phép kiểm dưới sẽ xanh oan"


@pytest.mark.parametrize("ten", sorted(_services()))
def test_moi_service_deu_tu_len_lai(ten):
    """
    Thiếu dòng này ở MỘT service là service đó không lên sau khi máy khởi
    động — và vì các service kia lên, hệ thống trông như đang chạy.
    """
    assert "restart:" in _services()[ten], (
        f"service {ten} không có chính sách restart — sẽ không tự lên lại"
    )


@pytest.mark.parametrize("ten", sorted(_services()))
def test_KHONG_dung_restart_always(ten):
    """
    `always` bật lại cả container mình vừa cố ý dừng để gỡ lỗi, tức chống
    lại chính người vận hành. `unless-stopped` nhớ ý định của người.
    """
    khoi = _services()[ten]
    if "restart:" not in khoi:
        pytest.skip("test kia đã bắt")
    assert "restart: unless-stopped" in khoi, f"{ten} nên dùng unless-stopped"


# ---------------------------------------------------------------
#  Không dựng một hệ thống TRÔNG như đang chạy
# ---------------------------------------------------------------

def test_khong_co_CSDL_thi_DUNG_han():
    """
    App lên mà không có Postgres thì mọi đường đều 500, còn cổng 8000 vẫn
    nghe — nhìn từ ngoài y hệt một hệ thống khoẻ. Thà dừng và nói rõ.
    """
    than = _than("main")
    i_db = than.find("buoc_csdl")
    i_app = than.find("buoc_app()")
    assert i_db != -1 and i_app != -1
    assert i_db < i_app, "bật app trước khi có CSDL"
    assert "return 1" in than[i_db:i_app], (
        "không có đường thoát khi CSDL hỏng — sẽ dựng tiếp một hệ thống rỗng"
    )


def test_con_gi_hong_thi_ma_thoat_KHAC_khong():
    """
    Trả 0 khi còn tầng hỏng là biến lệnh này thành thứ không tự động hoá
    được: mọi script gọi nó đều tưởng đã xong.
    """
    for node in ast.walk(_ham("main")):
        if not isinstance(node, ast.If):
            continue
        if ast.unparse(node.test) != "hong":
            continue
        trong = " ".join(ast.unparse(x) for x in node.body)
        assert "return 1" in trong, "nhánh còn-tầng-hỏng không trả mã thoát 1"
        return
    raise AssertionError("không có nhánh `if hong:` nào trong main")


# ---------------------------------------------------------------
#  Vòng phụ thuộc app ↔ tunnel
# ---------------------------------------------------------------

def test_bat_lai_app_SAU_khi_tunnel_ghi_env():
    """
    App đọc `.env` MỘT LẦN lúc khởi động. Tunnel ghi tên miền mới vào `.env`
    SAU đó. Không bật lại thì dashboard dựng URL webhook theo tên miền cũ —
    một URL trông đúng mà không ai gọi tới được.
    """
    than = _than("main")
    i_tunnel = than.find("buoc_tunnel()")
    i_bat_lai = than.find("bat_lai=True")
    assert i_tunnel != -1, "main không bật tunnel"
    assert i_bat_lai != -1, "main không bật lại app sau khi .env đổi"
    assert i_tunnel < i_bat_lai, "bật lại app TRƯỚC khi tunnel ghi .env"


def test_chi_bat_lai_KHI_ten_mien_thuc_su_doi():
    """
    Bật lại vô điều kiện là cắt mọi hội thoại đang mở mỗi lần chạy lệnh,
    kể cả khi chẳng có gì đổi.
    """
    than = _than("main")
    assert "if ok_tn and doi:" in than, (
        "bật lại app vô điều kiện — cắt hội thoại đang mở không lý do"
    )


def test_biet_ten_mien_co_doi_hay_khong():
    """So tên miền TRƯỚC và SAU, chứ không đoán."""
    than = _than("buoc_tunnel")
    assert than.count("_doc_env('PUBLIC_BASE_URL')") == 2, (
        "không so tên miền trước/sau — không biết .env có đổi thật không"
    )


# ---------------------------------------------------------------
#  Tắt app: đừng tắt nhầm tiến trình khác
# ---------------------------------------------------------------

def _bo_loc_tat_app() -> dict[str, str]:
    """
    Bộ lọc của TỪNG nhánh hệ điều hành, tách riêng.

    Bản đầu của test này gộp cả hàm rồi tìm chữ "uvicorn". Nhánh `pkill`
    (POSIX) có sẵn chữ ấy, nên khi thử thay bộ lọc PowerShell bằng `$true`
    — tức tắt MỌI tiến trình Python trên máy — test vẫn xanh. Xanh giả, tự
    tay dựng ra trong chính lượt viết test chống xanh giả.
    """
    ra: dict[str, str] = {}
    for node in ast.walk(_ham("_tat_app")):
        if not isinstance(node, ast.Call):
            continue
        doi = [a.value for a in node.args
               if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if any("pkill" in x for x in doi):
            ra["posix"] = " ".join(doi)
        if any("powershell" in x for x in doi):
            ra["windows"] = " ".join(doi)
    return ra


@pytest.mark.parametrize("he", ["posix", "windows"])
def test_tat_app_loc_DU_CHAT_khong_giet_nham(he):
    """
    Lọc mỗi "python" là tắt luôn tiến trình Python khác của người dùng — kể
    cả chính script này, đang chạy bằng Python.

    Kiểm TỪNG nhánh: hở một nhánh là hở trên đúng hệ điều hành đó, còn hệ
    kia vẫn xanh và che mất.
    """
    bo_loc = _bo_loc_tat_app()
    assert he in bo_loc, f"không tìm thấy nhánh {he} trong _tat_app"
    assert "uvicorn" in bo_loc[he] and "agent.main:app" in bo_loc[he], (
        f"bộ lọc nhánh {he} quá rộng — sẽ tắt nhầm tiến trình Python khác"
    )


# ---------------------------------------------------------------
#  Không chép lại thứ đã có chỗ ở
# ---------------------------------------------------------------

def test_giao_sidecar_va_tunnel_cho_script_rieng():
    """
    Ba biến môi trường của sidecar và cách truyền bí mật nằm trọn trong
    `chay_sidecar_zalo`; ba cái bẫy của tunnel nằm trong `chay_tunnel`.
    Chép lại ở đây là chép hai chỗ sẽ lệch nhau trong lần sửa tiếp theo.
    """
    assert "scripts.chay_sidecar_zalo" in _than("buoc_sidecar")
    assert "scripts.chay_tunnel" in _than("buoc_tunnel")
