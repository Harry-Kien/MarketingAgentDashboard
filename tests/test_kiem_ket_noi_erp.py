"""Bộ kiểm kết nối ERP — MỘT nguồn cho cả terminal lẫn dashboard.

`scripts/thu_erp.py` in nó ra; `GET /api/erp/kiem-ket-noi` trả nó về trình
duyệt. Viết hai lần là hai bộ sẽ lệch, và người vận hành nhận hai câu trả
lời khác nhau cho cùng một câu hỏi.

Ba điều được canh, cả ba đều là chuyện an toàn chứ không phải tiện dụng:

1. KHÔNG bao giờ ném — endpoint phải trả báo cáo, không trả trang lỗi 500.
2. KHÔNG bao giờ lộ khoá API — kết quả này hay bị chụp màn hình gửi đi.
3. KHÔNG ghi gì vào ERP — có test quét mã nguồn.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from agent.config import settings
from agent.erp import kiem_ket_noi, nha_may
from agent.erp.erpnext import NguonErpNext
from tests.erp_gia import chay

ROOT = Path(__file__).resolve().parent.parent
KHOA = "khoa-api-tuyet-doi-khong-duoc-lo"
BI_MAT = "secret-tuyet-doi-khong-duoc-lo"


@pytest.fixture(autouse=True)
def _sach():
    nha_may.dat_lai()
    yield
    nha_may.dat_lai()


def _erpnext(monkeypatch, **kw):
    ma_co = kw.pop("ma_co", None)
    tra_gia = kw.pop("tra_gia", True)
    tra_ton = kw.pop("tra_ton", True)
    chet = kw.pop("chet", False)

    if ma_co is None:
        from agent.erp.tep import NguonTep
        ma_co = [sp.ma for sp in chay(NguonTep().danh_sach_san_pham())]

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if chet:
            raise httpx.ConnectError("đứt")
        d = req.url.path
        if d.endswith("/Item"):
            return httpx.Response(200, json={"data": [
                {"item_code": m, "item_name": f"Món {m}", "is_sales_item": 1}
                for m in ma_co
            ]})
        if d.endswith("/Item Price"):
            return httpx.Response(200, json={"data": [
                {"price_list_rate": 245000.0, "currency": "VND",
                 "price_list": "Bán lẻ"}] if tra_gia else []})
        if d.endswith("/Bin"):
            return httpx.Response(200, json={"data": [
                {"actual_qty": 9.0, "reserved_qty": 2.0,
                 "warehouse": "KHO-HN"}] if tra_ton else []})
        return httpx.Response(200, json={"message": "he-thong@thu.vn"})

    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.thu")
    monkeypatch.setattr(settings, "erp_ma_kho", "KHO-HN")
    monkeypatch.setattr(settings, "erp_pricelist", "Bán lẻ")

    nguon = NguonErpNext(
        goc="https://erp.thu", api_key=KHOA, api_secret=BI_MAT,
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"),
    )
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: nguon)
    return nguon


def _ten(bc: dict) -> list[str]:
    return [m["ten"] for m in bc["muc"]]


def _muc(bc: dict, ten: str) -> dict | None:
    for m in bc["muc"]:
        if m["ten"] == ten:
            return m
    return None


# --- Nhánh chưa nối ERP ----------------------------------------------

def test_dang_dung_tep_thi_CHAN_va_noi_ro(monkeypatch):
    # ĐẶT `tep` TƯỜNG MINH, KHÔNG ĐỌC `.env` CỦA MÁY.
    #
    # Bản trước dựa vào giá trị mặc định trong cấu hình, nên ca này ĐỎ ngay
    # khi lập trình viên nối ERPNext thật — một việc hoàn toàn hợp lệ. Đỏ
    # giả kiểu đó dạy người ta bỏ qua màu đỏ, và lần đỏ thật tiếp theo cũng
    # bị bỏ qua y như vậy.
    monkeypatch.setattr(settings, "erp_loai", "tep")

    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert bc["trang_thai"] == kiem_ket_noi.CHAN
    assert bc["san_sang"] is False
    assert "ERP_LOAI" in _muc(bc, "Cấu hình")["ghi_chu"]


# --- Đường suôn -------------------------------------------------------

def test_noi_duoc_thi_du_cac_muc(monkeypatch):
    _erpnext(monkeypatch)
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    for ten in ("Nguồn", "Kết nối", "Danh mục", "Giá", "Tồn kho", "Ánh xạ mã",
                "Độ trễ"):
        assert ten in _ten(bc), f"thiếu mục {ten!r}"


def test_ton_kho_hien_so_ban_duoc_da_tru_giu_cho(monkeypatch):
    _erpnext(monkeypatch)
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert "7 bán được" in _muc(bc, "Tồn kho")["ghi_chu"]   # 9 − 2


def test_luon_bat_NGUOI_xac_nhan_bang_gia(monkeypatch):
    # Máy không tự biết bảng nào là bảng bán lẻ. Im lặng coi như đúng là để
    # agent báo giá sỉ cho khách lẻ, rất tự tin.
    _erpnext(monkeypatch)
    m = _muc(chay(kiem_ket_noi.kiem_tat_ca()), "Bảng giá")
    assert m["trang_thai"] == kiem_ket_noi.CANH_BAO
    assert "BÁN LẺ" in m["ghi_chu"]


# --- 1. Không bao giờ ném --------------------------------------------

def test_erp_chet_thi_tra_bao_cao_chu_khong_nem(monkeypatch):
    # Endpoint phải trả báo cáo. Ném ra ngoài là người vận hành nhận một
    # trang lỗi 500 thay vì biết mình cấu hình thiếu chỗ nào.
    _erpnext(monkeypatch, chet=True)
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert bc["san_sang"] is False
    assert _muc(bc, "Kết nối")["trang_thai"] == kiem_ket_noi.CHAN


def test_cau_hinh_thieu_thi_tra_bao_cao_chu_khong_nem(monkeypatch):
    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "")
    nha_may.dat_lai()
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert bc["trang_thai"] == kiem_ket_noi.CHAN
    assert "ERPNEXT_URL" in _muc(bc, "Cấu hình")["ghi_chu"]


def test_danh_muc_rong_thi_CHAN(monkeypatch):
    _erpnext(monkeypatch, ma_co=[])
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert _muc(bc, "Danh mục")["trang_thai"] == kiem_ket_noi.CHAN
    assert bc["san_sang"] is False


def test_khong_tra_duoc_gia_thi_CHAN(monkeypatch):
    _erpnext(monkeypatch, tra_gia=False)
    assert _muc(chay(kiem_ket_noi.kiem_tat_ca()), "Giá")["trang_thai"] \
        == kiem_ket_noi.CHAN


def test_khong_co_ton_thi_chi_CANH_BAO_khong_chan(monkeypatch):
    # Món chưa từng nhập kho đó là chuyện bình thường; chặn ở đây là báo
    # động giả, và báo động giả nhiều thì người ta tắt báo động.
    _erpnext(monkeypatch, tra_ton=False)
    assert _muc(chay(kiem_ket_noi.kiem_tat_ca()), "Tồn kho")["trang_thai"] \
        == kiem_ket_noi.CANH_BAO


def test_anh_xa_ma_lech_thi_CHAN(monkeypatch):
    _erpnext(monkeypatch, ma_co=["MA-LA-01", "MA-LA-02"])
    bc = chay(kiem_ket_noi.kiem_tat_ca())
    assert _muc(bc, "Ánh xạ mã")["trang_thai"] == kiem_ket_noi.CHAN
    assert bc["san_sang"] is False


def test_canh_bao_phan_trang_khi_so_tron(monkeypatch):
    _erpnext(monkeypatch, ma_co=[f"SP-{i:03d}" for i in range(20)])
    assert _muc(chay(kiem_ket_noi.kiem_tat_ca()), "Phân trang") is not None


# --- 2. Không bao giờ lộ bí mật --------------------------------------

def test_bao_cao_KHONG_chua_khoa_api(monkeypatch):
    # Kết quả này đi qua HTTP tới trình duyệt và hay bị chụp màn hình gửi đi.
    _erpnext(monkeypatch)
    van_ban = repr(chay(kiem_ket_noi.kiem_tat_ca()))
    assert KHOA not in van_ban
    assert BI_MAT not in van_ban


def test_bao_cao_khong_chua_khoa_ke_ca_khi_hong(monkeypatch):
    _erpnext(monkeypatch, chet=True)
    van_ban = repr(chay(kiem_ket_noi.kiem_tat_ca()))
    assert KHOA not in van_ban and BI_MAT not in van_ban


# --- 3. Không ghi gì vào ERP -----------------------------------------

def test_bo_kiem_khong_co_loi_goi_ghi_nao():
    ma = (ROOT / "agent" / "erp" / "kiem_ket_noi.py").read_text(encoding="utf-8")
    for cam in ("tao_don", "bao_dam_khach", ".post(", ".put(", ".delete("):
        assert cam not in ma, f"bộ kiểm kết nối chỉ được ĐỌC, thấy: {cam}"


def test_script_thu_erp_dung_chung_bo_kiem_nay():
    # Hai bộ phép kiểm rời nhau sẽ lệch, và người vận hành nhận hai câu trả
    # lời khác nhau cho cùng một câu hỏi.
    ma = (ROOT / "scripts" / "thu_erp.py").read_text(encoding="utf-8")
    assert re.search(r"kiem_ket_noi", ma), (
        "scripts/thu_erp.py phải gọi agent.erp.kiem_ket_noi, không tự dựng "
        "lại bộ phép kiểm riêng"
    )


def test_soi_dung_cong_agent_dang_dung_khong_dung_nguon_moi(monkeypatch):
    """
    `kiem_ket_noi` phải soi ĐÚNG đối tượng agent đang dùng.

    Bản trước gọi `nha_may.tao_nguon()`, tức dựng một nguồn KHÁC từ cấu
    hình. Ca `test_kiem_ket_noi_khong_bao_gio_500` tiêm một nguồn HỎNG mà
    báo cáo vẫn trả về ERPNext thật — nó xanh suốt chỉ vì `ERP_LOAI=tep`
    thoát sớm, tức chưa từng kiểm thứ nó nói đang kiểm.

    Nặng hơn ở chạy thật: `Cong` có ngắt mạch. Mạch mở thì agent nhận
    "không biết", nhưng nguồn dựng mới gọi thẳng và báo XANH — xanh giả
    ngay tại màn hình người vận hành mở ra để biết hệ thống có ổn không.

    ĐỌC BẰNG AST: bản đầu của chính ca này so chuỗi và đỏ vì bắt nhầm dòng
    chú thích đang GIẢI THÍCH vì sao không dùng `tao_nguon`. Một phép kiểm
    bắt nhầm lời giải thích về chính nó là phép kiểm sẽ bị gỡ.
    """
    import ast
    import inspect

    from agent.erp import kiem_ket_noi as kkn

    cay = ast.parse(inspect.getsource(kkn.kiem_tat_ca).lstrip())
    goi = {
        ast.unparse(n.func)
        for n in ast.walk(cay)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "nha_may.cong" in goi, goi
    assert "nha_may.tao_nguon" not in goi, goi
