"""`scripts/thu_erp.py` — lớp IN mỏng trên `agent/erp/kiem_ket_noi.py`.

Phép kiểm nằm ở module kia và có bộ test riêng
(`tests/test_kiem_ket_noi_erp.py`). Ở đây chỉ canh ba việc của lớp in:

1. **Mã thoát khớp kết luận.** In chữ CHẶN màu đỏ rồi `exit 0` là đúng thứ
   hỏng im lặng repo này chống: ai gói lệnh vào script tự động sẽ đọc mã
   thoát, không đọc màu chữ.
2. **Không in bí mật.** Đầu ra hay bị dán vào chat nhờ xem hộ.
3. **Không tự dựng lại phép kiểm.** Hai bộ rời nhau sẽ lệch.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import httpx

from agent.config import settings
from agent.erp import nha_may
from agent.erp.erpnext import NguonErpNext
from scripts import thu_erp
from tests.erp_gia import chay

ROOT = Path(__file__).resolve().parent.parent
KHOA = "khoa-api-khong-duoc-in"
BI_MAT = "secret-khong-duoc-in"


def _chay() -> tuple[int, str]:
    dem = io.StringIO()
    with redirect_stdout(dem):
        ma = chay(thu_erp.chay())
    return ma, dem.getvalue()


def _noi_erp_gia(monkeypatch, **kw):
    ma_co = kw.pop("ma_co", None)
    if ma_co is None:
        from agent.erp.tep import NguonTep
        ma_co = [sp.ma for sp in chay(NguonTep().danh_sach_san_pham())]

    def xu_ly(req: httpx.Request) -> httpx.Response:
        d = req.url.path
        if d.endswith("/Item"):
            return httpx.Response(200, json={"data": [
                {"item_code": m, "item_name": f"Món {m}", "is_sales_item": 1}
                for m in ma_co]})
        if d.endswith("/Item Price"):
            return httpx.Response(200, json={"data": [
                {"price_list_rate": 245000.0, "currency": "VND",
                 "price_list": "Bán lẻ"}]})
        if d.endswith("/Bin"):
            return httpx.Response(200, json={"data": [
                {"actual_qty": 9.0, "reserved_qty": 2.0,
                 "warehouse": "KHO-HN"}]})
        return httpx.Response(200, json={"message": "ok"})

    monkeypatch.setattr(settings, "erp_loai", "erpnext")
    monkeypatch.setattr(settings, "erpnext_url", "https://erp.thu")
    monkeypatch.setattr(settings, "erp_ma_kho", "KHO-HN")
    monkeypatch.setattr(settings, "erp_pricelist", "Bán lẻ")
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: NguonErpNext(
        goc="https://erp.thu", api_key=KHOA, api_secret=BI_MAT,
        ma_kho="KHO-HN", pricelist="Bán lẻ",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"),
    ))


# --- 1. Mã thoát khớp kết luận ---------------------------------------

def test_chua_noi_erp_thi_thoat_KHAC_0(monkeypatch):
    # ĐẶT `tep` TƯỜNG MINH, KHÔNG ĐỌC `.env` CỦA MÁY.
    #
    # Bản trước dựa vào giá trị mặc định trong cấu hình, nên ca này ĐỎ ngay
    # khi lập trình viên nối ERPNext thật — một việc hoàn toàn hợp lệ. Đỏ
    # giả kiểu đó dạy người ta bỏ qua màu đỏ, và lần đỏ thật tiếp theo cũng
    # bị bỏ qua y như vậy.
    monkeypatch.setattr(settings, "erp_loai", "tep")

    nha_may.dat_lai()
    ma, ra = _chay()
    assert ma == 1
    assert "CHƯA DÙNG ĐƯỢC" in ra


def test_noi_duoc_thi_thoat_0(monkeypatch):
    _noi_erp_gia(monkeypatch)
    ma, ra = _chay()
    nha_may.dat_lai()
    assert ma == 0, ra
    assert "SẴN SÀNG" in ra


def test_anh_xa_lech_thi_thoat_KHAC_0(monkeypatch):
    # In chữ đỏ rồi trả 0 là đúng thứ hỏng im lặng: script tự động đọc mã
    # thoát chứ không đọc màu chữ.
    _noi_erp_gia(monkeypatch, ma_co=["MA-LA-01", "MA-LA-02"])
    ma, ra = _chay()
    nha_may.dat_lai()
    assert ma == 1
    assert "Ánh xạ mã" in ra


# --- 2. Không in bí mật ----------------------------------------------

def test_khong_bao_gio_in_khoa_api(monkeypatch):
    _noi_erp_gia(monkeypatch)
    _, ra = _chay()
    nha_may.dat_lai()
    assert KHOA not in ra
    assert BI_MAT not in ra


# --- 3. Không tự dựng lại phép kiểm ----------------------------------

def test_dung_chung_bo_kiem_voi_dashboard():
    ma = (ROOT / "scripts" / "thu_erp.py").read_text(encoding="utf-8")
    assert "kiem_ket_noi" in ma


def test_khong_ghi_gi_vao_erp():
    ma = (ROOT / "scripts" / "thu_erp.py").read_text(encoding="utf-8")
    for cam in (".post(", ".put(", ".delete(", ".patch("):
        assert cam not in ma, f"thu_erp.py không được ghi vào ERP: {cam}"


def test_in_du_moi_muc_bo_kiem_tra_ve(monkeypatch):
    # Lớp in bỏ sót một mục là người vận hành không thấy một cảnh báo có
    # thật — và không có gì báo rằng nó bị bỏ sót.
    _noi_erp_gia(monkeypatch)
    from agent.erp import kiem_ket_noi

    bc = chay(kiem_ket_noi.kiem_tat_ca())
    _, ra = _chay()
    nha_may.dat_lai()
    for m in bc["muc"]:
        assert m["ten"] in ra, f"lớp in bỏ sót mục {m['ten']!r}"
