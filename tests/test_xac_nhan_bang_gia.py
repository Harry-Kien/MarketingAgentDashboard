"""
Xác nhận bảng giá — việc chỉ con người làm được.

VÌ SAO CÓ CƠ CHẾ NÀY

`kiem_ket_noi` có một mục vàng VĨNH VIỄN: "NGƯỜI phải xác nhận 'Standard
Selling' đúng là giá BÁN LẺ". Máy không tự biết bảng nào là bảng bán lẻ.

Nhưng cảnh báo không bao giờ tắt được thì tệ hơn không có cảnh báo. Người
vận hành mở bản kiểm, thấy vàng, và biết nó LÚC NÀO CŨNG vàng. Lần sau có
một mục vàng THẬT, mắt họ lướt qua. Đó là cách một bộ kiểm tự huỷ hoại
chính mình.

KHẲNG ĐỊNH TRUNG TÂM: `test_doi_bang_gia_thi_xac_nhan_HET_hieu_luc`

Xác nhận gắn với ĐÚNG TÊN bảng giá, không phải là nút tắt cảnh báo. Một
nút "tôi kiểm rồi" chung chung thì bấm một lần là im mãi mãi — kể cả sau
khi ai đó đổi sang bảng giá sỉ.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import runtime  # noqa: E402
from agent.erp import xac_nhan  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


class BangGia:
    """CSDL giả cho bảng `cau_hinh_agent`."""

    def __init__(self):
        self.dong: dict[str, str] = {}
        self.su_kien: list[str] = []

    async def execute(self, sql, *args):
        if "DELETE FROM cau_hinh_agent WHERE khoa = $1" in sql:
            n = 1 if args[0] in self.dong else 0
            self.dong.pop(args[0], None)
            return f"DELETE {n}"
        if "DELETE FROM cau_hinh_agent WHERE khoa = ANY" in sql:
            n = 0
            for k in list(args[0]):
                if k in self.dong:
                    del self.dong[k]
                    n += 1
            return f"DELETE {n}"
        if "INSERT INTO cau_hinh_agent" in sql:
            self.dong[args[0]] = args[1]
            return "INSERT 0 1"
        return "OK"

    async def fetchrow(self, sql, *args):
        if "FROM cau_hinh_agent WHERE khoa" in sql and args[0] in self.dong:
            return {"gia_tri": self.dong[args[0]]}
        return None

    async def fetch(self, sql, *args):
        return [{"khoa": k, "gia_tri": v} for k, v in self.dong.items()]

    async def log_event(self, kind, **kw):
        self.su_kien.append(kind)


@pytest.fixture
def bang(monkeypatch):
    b = BangGia()
    for mod in (xac_nhan.db, runtime.db):
        monkeypatch.setattr(mod, "execute", b.execute, raising=False)
        monkeypatch.setattr(mod, "fetchrow", b.fetchrow, raising=False)
        monkeypatch.setattr(mod, "fetch", b.fetch, raising=False)
        monkeypatch.setattr(mod, "log_event", b.log_event, raising=False)
    return b


# ---------------------------------------------------------------
#  Khẳng định trung tâm
# ---------------------------------------------------------------

def test_doi_bang_gia_thi_xac_nhan_HET_hieu_luc(bang):
    """
    Xác nhận cho 'Standard Selling' KHÔNG được che cho 'Wholesale'.

    Đây là khác biệt giữa một XÁC NHẬN và một cái NÚT TẮT TIẾNG. Không có
    ca này thì bấm một lần là im mãi, kể cả sau khi ai đó đổi sang bảng giá
    sỉ — và agent báo giá sỉ cho khách lẻ, rất tự tin, không cảnh báo nào.
    """
    chay(xac_nhan.ghi("Standard Selling", boi="admin"))
    assert chay(xac_nhan.da_xac_nhan("Standard Selling")) is not None
    assert chay(xac_nhan.da_xac_nhan("Wholesale")) is None
    assert chay(xac_nhan.da_xac_nhan("Standard Selling 2")) is None


def test_chua_xac_nhan_thi_tra_None(bang):
    assert chay(xac_nhan.da_xac_nhan("Standard Selling")) is None


def test_ghi_lai_AI_va_LUC_NAO(bang):
    """Một xác nhận không truy được người là một xác nhận không ai chịu trách nhiệm."""
    r = chay(xac_nhan.ghi("Standard Selling", boi="chi_lan"))
    assert r["boi"] == "chi_lan"
    assert r["ten"] == "Standard Selling"
    assert len(r["luc"]) >= 19          # ISO, có ngày giờ
    assert "erp.xac_nhan_bang_gia" in bang.su_kien


def test_khoang_trang_khong_lam_lech_khop(bang):
    """`ERP_PRICELIST` có thể có dấu cách thừa — không được vì thế mà mất xác nhận."""
    chay(xac_nhan.ghi("  Standard Selling  ", boi="admin"))
    assert chay(xac_nhan.da_xac_nhan("Standard Selling")) is not None


def test_khong_xac_nhan_suong_khi_chua_biet_bang_gia(bang):
    """Xác nhận một chuỗi rỗng là xác nhận không có nội dung."""
    with pytest.raises(ValueError):
        chay(xac_nhan.ghi("", boi="admin"))


def test_go_xac_nhan_thi_canh_bao_quay_lai(bang):
    chay(xac_nhan.ghi("Standard Selling", boi="admin"))
    assert chay(xac_nhan.go(boi="admin")) is True
    assert chay(xac_nhan.da_xac_nhan("Standard Selling")) is None


def test_go_cai_khong_co_thi_bao_False(bang):
    """`db.execute` trả CHUỖI "DELETE 0", và `bool("DELETE 0")` là True."""
    assert chay(xac_nhan.go(boi="admin")) is False


def test_gia_tri_rac_trong_csdl_khong_lam_no(bang):
    """Dòng hỏng phải thành 'chưa xác nhận', không thành sự cố."""
    bang.dong[xac_nhan.KHOA] = "{khong-phai-json"
    assert chay(xac_nhan.doc()) is None
    bang.dong[xac_nhan.KHOA] = json.dumps(["mang", "chu khong phai dict"])
    assert chay(xac_nhan.doc()) is None


def test_csdl_hong_thi_coi_nhu_chua_xac_nhan(monkeypatch):
    """
    Sai theo hướng AN TOÀN: đọc không được thì hiện cảnh báo, không im lặng
    coi như đã xác nhận.
    """
    async def no(*a, **k):
        raise RuntimeError("CSDL sập")

    monkeypatch.setattr(xac_nhan.db, "fetchrow", no)
    assert chay(xac_nhan.doc()) is None


# ---------------------------------------------------------------
#  Nút "Quay về mặc định" không được xoá nhầm
# ---------------------------------------------------------------

def test_dat_lai_cau_hinh_agent_KHONG_xoa_xac_nhan(bang):
    """
    LỖI TIỀM ẨN đã sửa: `dat_lai_mac_dinh` chạy `DELETE FROM cau_hinh_agent`
    trần. Bảng ấy là kho khoá–giá trị dùng chung, nên xác nhận bảng giá bị
    quét sạch khi ai đó bấm "Quay về mặc định" cho một việc hoàn toàn khác.

    Nút ấy hứa đặt lại BỐN thiết lập agent, không hứa xoá thứ người khác
    vừa xác nhận tuần trước.
    """
    chay(xac_nhan.ghi("Standard Selling", boi="admin"))
    chay(runtime.luu({"confidence_floor": 0.9}))

    chay(runtime.dat_lai_mac_dinh(boi="admin"))

    assert chay(xac_nhan.da_xac_nhan("Standard Selling")) is not None, (
        "nút Quay về mặc định đã xoá nhầm xác nhận bảng giá"
    )
    assert runtime.STATE["confidence_floor"] == runtime.MAC_DINH["confidence_floor"]


def test_xac_nhan_khong_bi_nap_vao_runtime_state(bang):
    """
    Khoá này ở chung bảng nhưng KHÔNG thuộc `KHOA_BEN_VUNG`. Nạp nhầm vào
    `STATE` thì màn Cấu hình hiện một thiết lập không điều khiển gì cả.
    """
    chay(xac_nhan.ghi("Standard Selling", boi="admin"))
    chay(runtime.nap())
    assert xac_nhan.KHOA not in runtime.STATE


# ---------------------------------------------------------------
#  Nối vào bản kiểm kết nối
# ---------------------------------------------------------------

def test_api_khong_nhan_ten_bang_gia_tu_client():
    """
    Cho gửi tên vào thân request là mở đường xác nhận một bảng giá KHÁC với
    bảng hệ thống thật sự đang dùng — và xác nhận ấy trông hợp lệ.
    """
    import ast

    cay = ast.parse((ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8"))
    for node in ast.walk(cay):
        if not (isinstance(node, ast.AsyncFunctionDef)
                and node.name == "ghi_xac_nhan_bang_gia"):
            continue
        nguon = ast.unparse(node)
        assert "settings.erp_pricelist" in nguon, (
            "phải lấy tên bảng giá từ cấu hình đang chạy"
        )
        # Không có tham số nào ngoài dependency xác thực.
        ten_tham_so = [a.arg for a in node.args.args]
        assert ten_tham_so == ["nguoi"], f"nhận thêm tham số: {ten_tham_so}"
        return
    raise AssertionError("không tìm thấy ghi_xac_nhan_bang_gia")


def test_kiem_ket_noi_doc_xac_nhan():
    """Không đọc thì mục ấy vàng vĩnh viễn dù người đã xác nhận."""
    nguon = (ROOT / "agent" / "erp" / "kiem_ket_noi.py").read_text(encoding="utf-8")
    assert "da_xac_nhan" in nguon, (
        "kiem_ket_noi không tra xác nhận — mục Bảng giá sẽ vàng mãi mãi"
    )
