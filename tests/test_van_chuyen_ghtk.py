"""
Vận chuyển GHTK — canh những chỗ GHTK khác GHN mà hỏng thì im lặng.

Mỗi nhóm test ứng với một cách trượt cụ thể:
  · địa chỉ tách bừa → kiện hàng đi tìm một phường không có;
  · webhook dạng form bị cổng JSON trả 400 → đơn kẹt "đang giao" mãi;
  · "shipper báo đã giao" (45) đọc thành đã giao → cảm ơn khách khi hàng chưa tới;
  · mã chỉ-đối-soát (11) đọc thành hoàn về → cộng hàng vào kho khi kệ trống;
  · thử lại sau đứt mạng → vận đơn thứ hai cho cùng một đơn.
"""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

import httpx
import pytest

from agent.shipping import ghtk as g
from agent.shipping.ghtk import GHTKShippingProvider, tach_dia_chi
from agent.shipping.models import CreateWaybillRequest, InternalShippingStatus as S, ShippingItem

_AsyncClientThat = httpx.AsyncClient


def _nha_cung_cap(monkeypatch, cau_hinh: dict | None = None, handler=None) -> GHTKShippingProvider:
    cau_hinh = {"GHTK_TOKEN": "tok", "GHTK_KHO_ID": "kho-1", **(cau_hinh or {})}
    p = GHTKShippingProvider(api_url="https://ghtk.test")
    p._lay = lambda k: cau_hinh.get(k, "")
    goi: list[httpx.Request] = []

    def _xu_ly(req):
        goi.append(req)
        if handler is None:
            raise AssertionError("không được gọi mạng")
        return handler(req)

    monkeypatch.setattr(g.httpx, "AsyncClient",
                        lambda **kw: _AsyncClientThat(transport=httpx.MockTransport(_xu_ly)))
    p.goi = goi  # type: ignore[attr-defined]
    return p


def _don(dia_chi="12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh", **k) -> CreateWaybillRequest:
    m = dict(ma_don="DH1", khach_ten="Chị Lan", khach_sdt="0912345678", khach_dia_chi=dia_chi,
             items=[ShippingItem(ma="SR1", ten="Serum", so_luong=2, don_gia=150000, khoi_luong_gram=400)],
             tong_tien=300000, thu_ho_cod=300000, tong_khoi_luong_gram=500)
    m.update(k)
    return CreateWaybillRequest(**m)


# ------------------------------------------------------------------ địa chỉ

@pytest.mark.parametrize("dia_chi,mong", [
    ("12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh",
     ("12 Lê Lợi", "Phường Bến Nghé", "Quận 1", "TP Hồ Chí Minh")),
    ("Số 5, ngõ 2 Trần Phú, Xã Hồng Hà, Huyện Đan Phượng, Hà Nội",
     ("Số 5, ngõ 2 Trần Phú", "Xã Hồng Hà", "Huyện Đan Phượng", "Hà Nội")),
    ("88 Lê Lợi, P. Tân An, TP Tam Kỳ, Quảng Nam",
     ("88 Lê Lợi", "P. Tân An", "TP Tam Kỳ", "Quảng Nam")),
    ("7 Hùng Vương, Phường 5, Q.10, TP.HCM", ("7 Hùng Vương", "Phường 5", "Q.10", "TP.HCM")),
])
def test_tach_dia_chi_ro_rang(dia_chi, mong):
    d = tach_dia_chi(dia_chi)
    assert d and (d["address"], d["ward"], d["district"], d["province"]) == mong


@pytest.mark.parametrize("dia_chi", [
    "12 Lê Lợi, Quận 1, HCM",                         # thiếu phường
    "Số 5, Phường Bến Thành, TP Hồ Chí Minh",         # hai cấp sau sáp nhập: GHTK vẫn đòi quận
    "Hẻm 5, 123 Lê Lợi, Quận 1, HCM",                 # "123 Lê Lợi" không phải phường
    "12 Lê Lợi, Phường Bến Nghé, 1, HCM",             # "1" không phải quận
    "12 Lê Lợi, Phường 1, Quận 3, Phường 2",          # phần cuối là phường, không phải tỉnh
    "",
])
def test_khong_chac_thi_khong_tach(dia_chi):
    assert tach_dia_chi(dia_chi) is None


def test_dia_chi_khong_ro_thi_KHONG_goi_GHTK(monkeypatch):
    p = _nha_cung_cap(monkeypatch)
    kq = asyncio.run(p.tao_van_don(_don(dia_chi="12 Lê Lợi, Quận 1, HCM")))
    assert not kq.ok and kq.can_nguoi_xac_nhan and "Hỏi lại khách" in kq.loi
    assert p.goi == []


# ------------------------------------------------------------------ cấu hình

def test_thieu_token_noi_ro(monkeypatch):
    p = _nha_cung_cap(monkeypatch, {"GHTK_TOKEN": ""})
    kq = asyncio.run(p.tao_van_don(_don()))
    assert not kq.ok and "GHTK_TOKEN" in kq.loi and p.goi == []


def test_thieu_noi_lay_hang_noi_ro(monkeypatch):
    p = _nha_cung_cap(monkeypatch, {"GHTK_KHO_ID": "", "GHTK_LAY_TEN": "Shop"})
    kq = asyncio.run(p.tao_van_don(_don()))
    assert not kq.ok and "GHTK_KHO_ID" in kq.loi and "GHTK_LAY_SDT" in kq.loi
    assert p.goi == []


def test_du_dia_chi_lay_hang_thi_khong_can_ma_kho(monkeypatch):
    p = _nha_cung_cap(monkeypatch, {"GHTK_KHO_ID": "", "GHTK_LAY_TEN": "Shop", "GHTK_LAY_SDT": "0900",
                                    "GHTK_LAY_DIA_CHI": "1 A", "GHTK_LAY_TINH": "Hà Nội",
                                    "GHTK_LAY_HUYEN": "Quận Ba Đình"})
    assert asyncio.run(p.san_sang()) == (True, "")


# ------------------------------------------------------------------ tạo đơn

def test_tao_don_gui_dung_truong(monkeypatch):
    def h(req):
        assert req.url.path == "/services/shipment/order/"
        assert req.headers["Token"] == "tok" and req.headers["X-Client-Source"] == "S1"
        body = json.loads(req.content)
        o = body["order"]
        assert o["pick_address_id"] == "kho-1"
        assert (o["ward"], o["district"], o["province"]) == ("Phường Bến Nghé", "Quận 1", "TP Hồ Chí Minh")
        assert o["pick_money"] == 300000 and o["value"] == 300000
        assert o["weight_option"] == "gram" and o["total_weight"] == 500
        assert len(o["note"]) <= 120
        # Khối lượng MỘT đơn vị: 400g cho 2 chai là 200g mỗi chai.
        assert body["products"][0]["weight"] == 200 and body["products"][0]["quantity"] == 2
        return httpx.Response(200, json={"success": True, "order": {
            "label": "S1.A1.2001297581", "fee": "30400", "insurance_fee": "1500",
            "estimated_deliver_time": "Chiều 2026-10-30", "status_id": 2}})

    p = _nha_cung_cap(monkeypatch, {"GHTK_MA_DOI_TAC": "S1"}, h)
    kq = asyncio.run(p.tao_van_don(_don(ghi_chu="x" * 300)))
    assert kq.ok and kq.ma_van_don == "S1.A1.2001297581" and kq.don_vi == "ghtk"
    assert kq.phi_van_chuyen == 31900
    assert kq.ngay_du_kien_giao and kq.ngay_du_kien_giao.date().isoformat() == "2026-10-30"


def test_ma_don_da_ton_tai_thi_nhan_lai_ma_cu(monkeypatch):
    """Thử lại sau đứt mạng không được sinh vận đơn thứ hai."""
    def h(req):
        return httpx.Response(200, json={"success": False, "message": "đã tồn tại", "error": {
            "code": "ORDER_ID_EXIST", "partner_id": "DH1", "ghtk_label": "S1.A1.1737345", "status": 2}})

    kq = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tao_van_don(_don()))
    assert kq.ok and kq.ma_van_don == "S1.A1.1737345" and kq.thong_tin_them["da_co_san"]


def test_ma_don_da_ton_tai_nhung_da_huy_thi_goi_nguoi(monkeypatch):
    def h(req):
        return httpx.Response(200, json={"success": False, "error": {
            "code": "ORDER_ID_EXIST", "ghtk_label": "S1.A1.9", "status": -1}})

    kq = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tao_van_don(_don()))
    assert not kq.ok and kq.can_nguoi_xac_nhan and "huỷ" in kq.loi


def test_ghtk_tu_choi_thi_neu_loi_cua_ghtk(monkeypatch):
    def h(req):
        return httpx.Response(200, json={"success": False, "message": "Tỉnh không hợp lệ"})

    kq = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tao_van_don(_don()))
    assert not kq.ok and "Tỉnh không hợp lệ" in kq.loi


def test_dut_mang_khong_nem(monkeypatch):
    def h(req):
        raise httpx.ConnectTimeout("hết giờ")

    kq = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tao_van_don(_don()))
    assert not kq.ok and "Lỗi mạng" in kq.loi


# ------------------------------------------------------------------ trạng thái

@pytest.mark.parametrize("ma,mong", [
    ("1", S.DELIVERING), ("2", S.DELIVERING), ("4", S.DELIVERING), ("12", S.DELIVERING),
    ("5", S.DELIVERED), ("6", S.DELIVERED),
    ("21", S.RETURNED),
    ("-1", S.DELIVERY_FAILED), ("9", S.DELIVERY_FAILED), ("10", S.DELIVERY_FAILED),
    ("20", S.DELIVERY_FAILED),
])
def test_anh_xa_ma_ghtk(ma, mong):
    assert GHTKShippingProvider().map_status(ma) == mong


@pytest.mark.parametrize("ma", ["20", "26", "13", "11", "45", "9"])
def test_hang_chua_ve_shop_thi_KHONG_hoan_kho(ma):
    """RETURNED cộng hàng lại vào kho — chỉ 21 (đã trả về shop) được ở đó."""
    assert GHTKShippingProvider().map_status(ma) != S.RETURNED


def test_ma_la_tra_None():
    assert GHTKShippingProvider().map_status("999") is None


def test_so_cua_GHTK_khong_lan_vao_bang_chung():
    """Bảng chung dùng cho mọi hãng: "5" ở đó là "5" của mọi hãng cũng thành đã giao."""
    from agent.shipping.base import anh_xa_trang_thai
    from agent.shipping.ghn import GHNShippingProvider

    for ma in ("5", "21", "1"):
        assert anh_xa_trang_thai(ma)[0] is None
        assert GHNShippingProvider().map_status(ma) is None


def test_GHTK_khai_bang_khong_ghi_de_map_status():
    assert "map_status" not in vars(GHTKShippingProvider)


# ------------------------------------------------------------------ webhook

def _form(**k) -> dict:
    """Đúng hình dạng GHTK gửi: form urlencoded, mọi giá trị là chuỗi."""
    from agent.main import doc_than_webhook_van_chuyen

    d = doc_than_webhook_van_chuyen(urlencode(k).encode(), "application/x-www-form-urlencoded")
    assert d is not None
    return d


def test_cong_webhook_doc_duoc_form_va_json():
    from agent.main import doc_than_webhook_van_chuyen as doc

    assert doc(b"label_id=S1.A1.2&status_id=5", "application/x-www-form-urlencoded; charset=UTF-8") == {
        "label_id": "S1.A1.2", "status_id": "5"}
    assert doc(b'{"OrderCode":"G1"}', "application/json") == {"OrderCode": "G1"}
    assert doc(b"[1,2]", "application/json") is None
    assert doc(b"khong phai gi ca", "text/plain") is None


def test_webhook_da_giao():
    e = GHTKShippingProvider().parse_webhook(
        _form(label_id="S1.A1.2", partner_id="DH1", status_id=5, reason=""), {})
    assert e.hop_le and e.ma_van_don == "S1.A1.2" and e.ma_don == "DH1"
    assert e.trang_thai_noi_bo == S.DELIVERED and not e.chi_thong_tin


@pytest.mark.parametrize("ma", ["45", "49", "410", "123", "127", "128", "11"])
def test_ma_shipper_tu_bao_chi_de_tham_khao(ma):
    e = GHTKShippingProvider().parse_webhook(_form(label_id="S1", status_id=ma), {})
    assert e.hop_le and e.chi_thong_tin and e.trang_thai_noi_bo is None


def test_webhook_thieu_truong_thi_khong_hop_le():
    assert not GHTKShippingProvider().parse_webhook({"status_id": "5"}, {}).hop_le
    assert not GHTKShippingProvider().parse_webhook({"label_id": "S1"}, {}).hop_le


def test_ma_chi_thong_tin_KHONG_doi_don(monkeypatch):
    """Trọn đường service: 45 ghi nhật ký, không UPDATE đơn, không nhắn khách."""
    from agent.config import settings
    from agent.shipping import service

    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat")
    ghi: list[str] = []
    su_kien: list[str] = []

    async def fetchrow(sql, *a):
        return {"id": 1, "ma_don": "DH1", "ma_van_don": "S1.A1.2", "conversation_id": None}

    async def execute(sql, *a):
        ghi.append(sql)

    async def log_event(kind, **k):
        su_kien.append(kind)

    monkeypatch.setattr(service.db, "fetchrow", fetchrow)
    monkeypatch.setattr(service.db, "execute", execute)
    monkeypatch.setattr(service.db, "log_event", log_event)
    kq = asyncio.run(service.xu_ly_webhook_van_chuyen(
        "ghtk", _form(label_id="S1.A1.2", partner_id="DH1", status_id=45), {}, query_token="bi-mat"))
    assert kq == {"ok": True, "chi_thong_tin": True}
    assert ghi == [] and su_kien == ["shipping.thong_tin"]

    kq = asyncio.run(service.xu_ly_webhook_van_chuyen(
        "ghtk", _form(label_id="S1.A1.2", partner_id="DH1", status_id=5), {}, query_token="bi-mat"))
    assert kq["trang_thai_noi_bo"] == "delivered"
    assert any("trang_thai = 'da_giao'" in s for s in ghi)


def test_get_provider_tra_GHTK():
    from agent.shipping.service import get_provider

    assert get_provider("ghtk").code == "ghtk"


# ------------------------------------------------------------------ tra cứu, huỷ, kiểm token

def test_tra_cuu(monkeypatch):
    def h(req):
        assert req.url.path == "/services/shipment/v2/S1.A1.2"
        return httpx.Response(200, json={"success": True, "order": {
            "label_id": "S1.A1.2", "status": "4", "status_text": "Đang giao hàng"}})

    r = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tra_cuu("S1.A1.2"))
    assert r.ok and r.trang_thai_noi_bo == S.DELIVERING and r.vi_tri_hien_tai == "Đang giao hàng"


def test_tra_cuu_ma_chi_thong_tin_thi_khong_ghi_de(monkeypatch):
    def h(req):
        return httpx.Response(200, json={"success": True, "order": {"status": "11", "status_text": "Đã đối soát"}})

    r = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).tra_cuu("S1"))
    assert not r.ok and r.trang_thai_goc == "11"


def test_huy(monkeypatch):
    def h(req):
        assert req.method == "POST" and req.url.path == "/services/shipment/cancel/S1.A1.2"
        return httpx.Response(200, json={"success": False, "message": "Đơn đã lấy hàng, không thể hủy đơn."})

    ok, ly_do = asyncio.run(_nha_cung_cap(monkeypatch, handler=h).huy_van_don("S1.A1.2"))
    assert not ok and "đã lấy hàng" in ly_do


def _client(handler):
    return _AsyncClientThat(transport=httpx.MockTransport(handler))


def test_kiem_ket_noi():
    def dung(req):
        assert req.method == "GET" and req.headers["Token"] == "tok"
        return httpx.Response(200, json={"success": True, "data": []})

    def sai(req):
        return httpx.Response(401, json={"success": False})

    ok, chi_tiet, _ = asyncio.run(g.kiem_ket_noi(token="tok", api_url="https://ghtk.test", client=_client(dung)))
    assert ok and "hợp lệ" in chi_tiet
    ok, chi_tiet, _ = asyncio.run(g.kiem_ket_noi(token="x", api_url="https://ghtk.test", client=_client(sai)))
    assert not ok and "token" in chi_tiet


def test_mac_dinh_tro_vao_staging():
    from agent.config import Settings

    assert "staging" in Settings.model_fields["ghtk_api_url"].default
