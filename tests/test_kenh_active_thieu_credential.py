"""
Kênh mang nhãn `active` mà không phục vụ nổi thì phải KÊU.

LỖI THẬT, ĐO ĐƯỢC 04.09.2026

Tài khoản webchat "Web thử nghiệm" hiện `active`, `ly_do_hong` rỗng, và
`/api/suc-khoe` báo "4 kênh native · tot". Nhưng khách bấm vào widget nhận:

    409 {"detail": "Webchat account thiếu widget secret"}

Bản ghi có `metadata` rỗng và KHÔNG một credential nào — nó được tạo rồi
đánh dấu `active` mà chưa từng cấu hình.

Chính docstring của `_kiem_kenh` đã tiên đoán chuyện này:

    "nếu một ngày kênh native chết thật, ô này vẫn nói y hệt —
     nó chưa từng nhìn vào đó"

Lời cảnh báo được viết ra, rồi mã vẫn đọc cột `status` thay vì gọi thử. Đó
là lý do mỗi ràng buộc phải có TEST canh, không chỉ có chú thích canh.

VÌ SAO KHÔNG GỌI `verify_connection()`

Nó đi ra mạng, mà `canh_gac` chạy mỗi 60 giây. `verify` của Zalo OA gọi
`_lay_token()`; access token có đệm nhưng đệm nằm trong INSTANCE adapter,
nên mỗi lượt kiểm dựng adapter mới là một lượt làm mới. Refresh token của
Zalo XOAY VÒNG — dùng một lần rồi chết. Đốt nó mỗi phút là tự tay giết kênh
mình đang canh.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import suc_khoe  # noqa: E402

NGUON = (ROOT / "agent" / "suc_khoe.py").read_text(encoding="utf-8")


def chay(coro):
    return asyncio.run(coro)


def _than(ten: str) -> str:
    """
    Thân hàm, ĐÃ BỎ docstring.

    Bản đầu của `test_KHONG_goi_verify_connection` soi cả `ast.unparse(node)`
    và đỏ ngay — vì docstring của chính hàm ấy giải thích VÌ SAO KHÔNG gọi
    `verify_connection`, nên chữ đó có mặt trong nguồn. Test đọc trúng lời
    giải thích của chính nó: lần thứ sáu dính bẫy này trong repo.
    """
    for node in ast.walk(ast.parse(NGUON)):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == ten):
            continue
        lenh = node.body
        if (lenh and isinstance(lenh[0], ast.Expr)
                and isinstance(lenh[0].value, ast.Constant)
                and isinstance(lenh[0].value.value, str)):
            lenh = lenh[1:]
        return "\n".join(ast.unparse(x) for x in lenh)
    raise AssertionError(f"không tìm thấy {ten}")


def dat_thieu(monkeypatch, ds: list[str]) -> None:
    async def gia():
        return ds

    monkeypatch.setattr(suc_khoe, "_tai_khoan_active_thieu_credential", gia)


def dat_bang(monkeypatch, hang: list[dict]) -> None:
    """Đứng thay `db.fetch` cho phần đếm kênh native của `_kiem_kenh`."""
    async def fetch(*a, **k):
        return hang

    monkeypatch.setattr(suc_khoe.db, "fetch", fetch)


# ---------------------------------------------------------------
#  Ca trung tâm
# ---------------------------------------------------------------

def test_active_ma_thieu_credential_thi_HONG(monkeypatch):
    dat_thieu(monkeypatch, ["webchat · Web thử nghiệm"])
    dat_bang(monkeypatch, [{"channel": "webchat", "status": "active", "n": 1}])
    m = chay(suc_khoe._kiem_kenh())
    assert m["trang_thai"] == suc_khoe.HONG, (
        "kênh active mà không có credential vẫn báo tốt — đúng xanh giả đã gặp"
    )
    assert "Web thử nghiệm" in m["ghi_chu"], "phải nói RÕ kênh nào"


def test_noi_ro_hau_qua_voi_khach(monkeypatch):
    """
    "thiếu credential" là chữ của người viết mã. Người trực cần biết điều
    ĐÓ NGHĨA LÀ GÌ với khách thì mới ưu tiên đúng.
    """
    dat_thieu(monkeypatch, ["webchat · Web thử nghiệm"])
    dat_bang(monkeypatch, [{"channel": "webchat", "status": "active", "n": 1}])
    assert "khách" in chay(suc_khoe._kiem_kenh())["ghi_chu"].lower()


def test_du_credential_thi_KHONG_keu(monkeypatch):
    dat_thieu(monkeypatch, [])
    dat_bang(monkeypatch, [{"channel": "zalo_personal", "status": "active", "n": 1}])
    assert chay(suc_khoe._kiem_kenh())["trang_thai"] != suc_khoe.HONG


def test_liet_ke_MOI_kenh_thieu_chu_khong_chi_cai_dau(monkeypatch):
    """Sửa một cái rồi tưởng xong, trong khi còn hai cái nữa."""
    dat_thieu(monkeypatch, ["webchat · A", "facebook · B", "zalo_oa · C"])
    dat_bang(monkeypatch, [{"channel": "webchat", "status": "active", "n": 3}])
    ghi = chay(suc_khoe._kiem_kenh())["ghi_chu"]
    for x in ("webchat · A", "facebook · B", "zalo_oa · C"):
        assert x in ghi, f"thiếu {x} trong ghi chú"


def test_HAM_TRUY_VAN_tra_du_moi_hang(monkeypatch):
    """
    Test ngay trên đã dùng bản giả của `_tai_khoan_active_thieu_credential`,
    nên nó chỉ soi cách `_kiem_kenh` ghép chuỗi — KHÔNG soi chính hàm truy
    vấn. Thử cắt hàm ấy còn `r[:1]` thì cả bộ vẫn xanh: đúng một lỗ xanh
    giả, và nó chỉ lộ ra khi đi gỡ từng ràng buộc.

    Đây là phép canh cho chính hàm truy vấn.
    """
    hang = [
        {"channel": "webchat", "display_name": "A"},
        {"channel": "facebook", "display_name": "B"},
        {"channel": "zalo_oa", "display_name": "C"},
    ]

    async def fetch(*a, **k):
        return hang

    monkeypatch.setattr(suc_khoe.db, "fetch", fetch)
    ra = chay(suc_khoe._tai_khoan_active_thieu_credential())
    assert len(ra) == 3, f"trả {len(ra)}/3 hàng — đang cắt bớt"
    assert ra == ["webchat · A", "facebook · B", "zalo_oa · C"]


# ---------------------------------------------------------------
#  Phải chặn TRƯỚC mọi nhánh trả `tot`
# ---------------------------------------------------------------

def test_kiem_TRUOC_khi_co_co_hoi_tra_tot():
    """
    `_kiem_kenh` có ba nhánh trả `tot`. Đặt phép kiểm này sau bất kỳ nhánh
    nào là nó không bao giờ chạy tới — mã có đủ, test có đủ, và vẫn xanh giả.
    """
    for node in ast.walk(ast.parse(NGUON)):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "_kiem_kenh"):
            continue
        than = ast.unparse(node)
        i_kiem = than.find("_tai_khoan_active_thieu_credential")
        i_tot = than.find("TOT")
        assert i_kiem != -1, "_kiem_kenh không gọi phép kiểm credential"
        assert i_tot == -1 or i_kiem < i_tot, (
            "phép kiểm nằm SAU một nhánh trả `tot` — sẽ không bao giờ chạy tới"
        )
        return
    raise AssertionError("không tìm thấy _kiem_kenh")


# ---------------------------------------------------------------
#  Không được đi ra mạng
# ---------------------------------------------------------------

def test_KHONG_goi_verify_connection():
    """
    Refresh token của Zalo xoay vòng và dùng một lần. Gọi `verify` trong
    vòng 60 giây là đốt token của chính kênh mình đang canh.
    """
    than = _than("_tai_khoan_active_thieu_credential")
    assert "verify_connection" not in than, (
        "gọi verify_connection trong vòng canh gác — sẽ đốt refresh token"
    )
    assert "httpx" not in than, "phép kiểm này phải thuần cục bộ"


def test_chi_soi_tai_khoan_ACTIVE():
    """
    Tài khoản `pending` chưa có credential là chuyện đương nhiên — hệ thống
    này có 26 trang Facebook `pending`. Kêu vì chúng là 26 dòng nhiễu, và
    người ta thôi đọc ô này.
    """
    assert "'active'" in _than("_tai_khoan_active_thieu_credential"), (
        "không lọc theo status active"
    )


# ---------------------------------------------------------------
#  Hỏng phép kiểm không được làm sập cả trang
# ---------------------------------------------------------------

@pytest.mark.parametrize("loi", [RuntimeError("CSDL sập"), OSError("mất kết nối"),
                                 KeyError("display_name")])
def test_CSDL_hong_thi_tra_rong_chu_KHONG_nem(monkeypatch, loi):
    """
    Ném ra ở đây là giết cả mục "Kênh nhận tin" — đổi một ô đỏ lấy một ô
    biến mất. Và im lặng là đúng: "Cơ sở dữ liệu" đã là mục riêng, nên trang
    đã đỏ sẵn khi CSDL sập; nói thêm lần nữa chỉ là nhiễu.

    Bản đầu của hàm này KHÔNG có khối `try`, và test cũ
    `test_csdl_hong_thi_khong_lam_sap_phep_kiem` — có từ trước — bắt được
    ngay. Đúng thứ mà "mỗi ràng buộc phải có test canh" sinh ra để làm.
    """
    async def no(*a, **k):
        raise loi

    monkeypatch.setattr(suc_khoe.db, "fetch", no)
    assert chay(suc_khoe._tai_khoan_active_thieu_credential()) == []


@pytest.mark.parametrize("loi", [RuntimeError("CSDL rớt"), OSError("mất kết nối")])
def test_phep_kiem_hong_KHONG_lam_mat_ca_trang(monkeypatch, loi):
    """
    `tong_kiem` gom bằng `asyncio.gather`. Một mục ném ra là mọi mục khác
    biến mất khỏi màn hình — đổi một ô đỏ lấy một trang trắng.
    """
    async def no():
        raise loi

    monkeypatch.setattr(suc_khoe, "_tai_khoan_active_thieu_credential", no)
    dat_bang(monkeypatch, [{"channel": "webchat", "status": "active", "n": 1}])
    with pytest.raises(type(loi)):
        chay(suc_khoe._kiem_kenh())
    # `tong_kiem` bọc bằng return_exceptions=True — canh luôn điều đó.
    for node in ast.walk(ast.parse(NGUON)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "tong_kiem":
            assert "return_exceptions=True" in ast.unparse(node)
            return
    raise AssertionError("không tìm thấy tong_kiem")
