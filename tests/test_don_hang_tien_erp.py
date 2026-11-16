"""
Đơn hàng / tiền / ERP / vận chuyển — mười một lỗi rà soát 11.2026.

Phần lớn là hỏng IM LẶNG kiểu "báo đã xong mà không xong":

  - khách mua lại đúng món cũ bị chặn vĩnh viễn, agent nói "đơn đã ghi nhận"
    cho một đơn không tồn tại (chỉ mục UNIQUE không giới hạn thời gian);
  - hai khách chốt cùng giây, một người mất đơn mà vẫn được báo "đã ghi nhận";
  - khách đã chuyển khoản VietQR vẫn bị shipper thu COD lần hai;
  - đơn bị huỷ trong lúc vòng nền đẩy ERP / tạo vận đơn thì SỐNG LẠI;
  - trạng thái giao từ ERP không bao giờ chạy (lọc sai trường);
  - người lạ đoán mã đơn tra được mã vận đơn của khách khác.

Phần đụng CSDL chạy trên `app_that` — app đầy đủ, Postgres thật. Lỗi race
và lỗi SQL chỉ lộ ra trên Postgres thật; giả lập `db.fetchrow` thì xanh giả.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_hoan_thien_luong import _don, _dong, _webhook  # noqa: E402
from tests.test_nghiem_thu_saas import _quan_tri_vao, _sql  # noqa: E402

SP = {"ma": "SP1", "ten": "Kem dưỡng ẩm Aurora", "gia": 100000}
DIA_CHI = "12 Lê Lợi, Phường Bến Thành, TP Hồ Chí Minh"


def _hoi_thoai(app) -> uuid.UUID:
    from agent import db

    async def tao():
        tk = (await db.fetchrow(
            "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
            "VALUES ('webchat', 'Web', 'active', $1) RETURNING id", uuid.uuid4().hex))["id"]
        kh = (await db.fetchrow(
            "INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id"))["id"]
        ma = uuid.uuid4().hex
        d = (await db.fetchrow(
            "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
            "VALUES ($1, $2, $3) RETURNING id", kh, tk, ma))["id"]
        return (await db.fetchrow(
            "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
            "contact_id, contact_point_id) VALUES ($1, 'webchat', $2, $2, $3, $4) "
            "RETURNING id", tk, ma, kh, d))["id"]
    return _sql(app, tao)


def _ton(app, ma: str = "SP1", so: int = 100) -> None:
    from agent import db

    async def dat():
        await db.execute(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ($1, $2) "
            "ON CONFLICT (ma) DO UPDATE SET so_luong = EXCLUDED.so_luong", ma, so)
    _sql(app, dat)


@pytest.fixture
def chot_duoc(monkeypatch):
    """ERP giả còn hàng, ngưỡng tự chốt cao, ERP_GHI_DON tắt."""
    from agent.config import settings
    from agent.erp import nha_may
    from agent.erp.hop_dong import TonKho
    from tests.erp_gia import NguonGia

    n = NguonGia(ton={"SP1": TonKho(ban_duoc=100)})
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: n)
    monkeypatch.setattr(settings, "nguong_tu_chot_vnd", 100_000_000)
    monkeypatch.setattr(settings, "erp_ghi_don", False)
    yield n
    nha_may.dat_lai()


def _chot(app, conv, so_luong: int = 1) -> dict:
    from agent.core import tools

    async def goi():
        return await tools._tao_don_hang({
            "khach_da_xac_nhan": True, "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
            "khach_dia_chi": DIA_CHI,
            "items": [{"ten_san_pham": SP["ten"], "so_luong": so_luong}],
        }, products=[SP], conversation_id=conv)
    return _sql(app, goi)


def _dem_don(app, conv) -> int:
    return _dong(app, "SELECT count(*) n FROM orders WHERE conversation_id = $1", conv)["n"]


# ================================================================ 1. chống trùng

def test_mua_lai_sau_khi_don_cu_da_giao_tao_duoc_don_moi(app_that, chot_duoc):
    """Chỉ mục UNIQUE cũ chặn VĨNH VIỄN — và bảo agent nói 'đã ghi nhận'."""
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    dau = _chot(app_that, conv)
    assert dau["tao_duoc"] is True, dau
    # Đơn cũ đã giao từ tuần trước.
    _dong(app_that, "UPDATE orders SET trang_thai='da_giao', "
          "created_at = now() - interval '7 days' WHERE ma_don = $1 RETURNING 1", dau["ma_don"])

    lai = _chot(app_that, conv)
    assert lai["tao_duoc"] is True, lai
    assert lai["ma_don"] != dau["ma_don"]
    assert _dem_don(app_that, conv) == 2


def test_bam_ok_hai_lan_chi_mot_don_va_tra_ma_don_cu(app_that, chot_duoc):
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    dau = _chot(app_that, conv)
    lai = _chot(app_that, conv)
    assert lai["tao_duoc"] is False and lai["trung_don"] is True
    # Agent phải ĐỌC LẠI ĐƯỢC mã đơn cho khách, không phải câu chung chung.
    assert lai["ma_don"] == dau["ma_don"] and dau["ma_don"] in lai["ly_do"]
    assert _dem_don(app_that, conv) == 1


def test_hai_loi_goi_dong_thoi_chi_mot_don(app_that, chot_duoc):
    """Hai tiến trình cùng kiểm 'đã có chưa' cùng thấy chưa — advisory lock chặn."""
    from agent.core import tools

    _ton(app_that)
    conv = _hoi_thoai(app_that)
    args = {"khach_da_xac_nhan": True, "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
            "khach_dia_chi": DIA_CHI,
            "items": [{"ten_san_pham": SP["ten"], "so_luong": 1}]}

    async def song_song():
        return await asyncio.gather(*(
            tools._tao_don_hang(dict(args), products=[SP], conversation_id=conv)
            for _ in range(4)))
    kq = _sql(app_that, song_song)
    assert sum(1 for k in kq if k.get("tao_duoc")) == 1, kq
    assert all(k.get("trung_don") for k in kq if not k.get("tao_duoc")), kq
    assert _dem_don(app_that, conv) == 1


def test_schema_khong_dung_lai_chi_muc_chong_trung_vinh_vien():
    """schema.sql chạy TRƯỚC migration mỗi lần khởi động — để đó là dựng lại."""
    sql = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_order_dedupe" not in sql
    mig = (ROOT / "agent" / "migrations" / "versions"
           / "0041_don_hang_tien_va_chong_trung.sql").read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS idx_order_dedupe" in mig


def test_csdl_that_khong_con_chi_muc_chong_trung(app_that):
    co = _dong(app_that, "SELECT count(*) n FROM pg_indexes WHERE indexname = 'idx_order_dedupe'")
    assert co["n"] == 0


# ================================================================ 2. mã đơn

def test_ma_don_co_phan_ngau_nhien_va_khong_bi_che_nham():
    from agent.core import tools
    from agent.core.che_du_lieu import MatNa

    ma = {tools._sinh_ma_don() for _ in range(200)}
    assert len(ma) > 150, "phần ngẫu nhiên quá ít — hai khách cùng giây vẫn đụng"
    for m in ma:
        assert re.fullmatch(r"AS\d{12}[A-Z2-9]{3}", m), m
    che = MatNa()
    m = next(iter(ma))
    assert m in che.che(f"đơn {m} của chị"), "mã đơn bị che nhầm thành số điện thoại"


def test_trung_ma_don_thi_sinh_ma_khac(app_that, chot_duoc, monkeypatch):
    """Hai khách cùng giây: người thứ hai KHÔNG được mất đơn."""
    from agent.core import tools

    _ton(app_that)
    _don(app_that, "da_chot")  # một đơn khác đang giữ mã trùng (đặt bên dưới)
    _dong(app_that, "UPDATE orders SET ma_don = 'ASTRUNG' WHERE ma_don = "
          "(SELECT ma_don FROM orders LIMIT 1) RETURNING 1")
    lan = iter(["ASTRUNG", "ASTRUNG", "ASMOI1"])
    monkeypatch.setattr(tools, "_sinh_ma_don", lambda: next(lan))
    kq = _chot(app_that, _hoi_thoai(app_that))
    assert kq["tao_duoc"] is True and kq["ma_don"] == "ASMOI1", kq


def test_loi_luu_khac_KHONG_bao_da_ghi_nhan(app_that, chot_duoc, monkeypatch):
    """Nhánh except cũ bắt mọi 'duplicate' và bảo agent nói đơn đã ghi nhận."""
    from agent.core import tools

    _ton(app_that)
    monkeypatch.setattr(tools, "_sinh_ma_don", lambda: None)   # NOT NULL vỡ
    conv = _hoi_thoai(app_that)
    kq = _chot(app_that, conv)
    assert kq["tao_duoc"] is False and not kq.get("trung_don")
    assert "CHƯA" in kq["ly_do"] and "đã ghi nhận" not in kq["ly_do"].replace("CHƯA được ghi nhận", "")
    assert _dem_don(app_that, conv) == 0
    su_kien = _dong(app_that, "SELECT count(*) n FROM events WHERE kind = 'order.luu_that_bai'")
    assert su_kien["n"] == 1


# ================================================================ 4. giữ hàng

def test_giu_hang_gop_dong_cung_ma_khong_nem(app_that):
    """Hai dòng cùng mã: bản cũ kiểm từng dòng 'đủ' rồi đâm vào CHECK >= 0."""
    from agent.core import kho

    _ton(app_that, so=3)

    async def giu():
        return await kho.giu_hang(
            [{"ma": "SP1", "ten": "Kem", "so_luong": 2},
             {"ma": "SP1", "ten": "Kem", "so_luong": 2}], "DH-GOP")
    du, ly_do = _sql(app_that, giu)
    assert du is False and "không đủ 4" in ly_do
    assert _dong(app_that, "SELECT so_luong FROM ton_kho WHERE ma='SP1'")["so_luong"] == 3


def test_giu_hang_nem_loi_thi_xoa_don(app_that, chot_duoc, monkeypatch):
    from agent.core import kho

    _ton(app_that)

    async def no(*a, **k):
        raise RuntimeError("kho sập")
    monkeypatch.setattr(kho, "giu_hang", no)
    conv = _hoi_thoai(app_that)
    kq = _chot(app_that, conv)
    assert kq["tao_duoc"] is False
    assert _dem_don(app_that, conv) == 0, "đơn nằm lại mà kho không trừ"
    assert _dong(app_that, "SELECT count(*) n FROM events WHERE kind='order.giu_hang_loi'")["n"] == 1


# ================================================================ 9. kho nguyên tử

def test_kiem_ke_va_nhap_kho_nguyen_tu():
    import inspect

    from agent.core import kho

    for ham in (kho.nhap_hang, kho.dieu_chinh):
        src = inspect.getsource(ham)
        assert "conn.transaction()" in src, f"{ham.__name__} không nằm trong giao dịch"
    assert "FOR UPDATE" in inspect.getsource(kho.dieu_chinh)


def test_kiem_ke_ghi_dung_do_lech(app_that):
    from agent.core import kho

    _ton(app_that, so=10)

    async def lam():
        await kho.nhap_hang("SP1", 5, "lô A")
        return await kho.dieu_chinh("SP1", 12, "vỡ 3")
    r = _sql(app_that, lam)
    assert r == {"ma": "SP1", "cu": 15, "moi": 12, "lech": -3}
    tong = _dong(app_that, "SELECT sum(thay_doi) s FROM kho_bien_dong WHERE ma='SP1'")["s"]
    assert tong == 2   # +5 rồi -3: sổ cộng ra đúng phần thay đổi


# ================================================================ 3. đã thu tiền → COD

def test_da_thu_tien_thi_van_don_chi_thu_ho_phan_con_lai(app_that):
    from agent.shipping import service

    _ton(app_that)
    qt = _quan_tri_vao(app_that)
    oid, ma = _don(app_that, "da_chot")      # tổng 1.500.000
    r = qt.post(f"/api/orders/{oid}/da-thu-tien", json={"so_tien": 500000})
    assert r.status_code == 200, r.text
    assert r.json()["thu_ho_cod"] == 1000000
    # Bấm hai lần không cộng dồn.
    assert qt.post(f"/api/orders/{oid}/da-thu-tien",
                   json={"so_tien": 500000}).json()["so_tien_da_thu"] == 500000
    d = next(o for o in qt.get("/api/orders").json() if o["id"] == oid)
    assert d["so_tien_da_thu"] == 500000 and d["da_thu_luc"]

    async def tao():
        kq = await service.tao_van_don_cho_don(ma, "mock")
        return kq.ma_van_don, service.get_provider("mock")._storage[kq.ma_van_don]["thu_ho_cod"]
    ma_vd, cod = _sql(app_that, tao)
    assert cod == 1000000
    nguoi = _dong(app_that, "SELECT da_thu_boi FROM orders WHERE id=$1::uuid", oid)["da_thu_boi"]
    assert nguoi is not None, "phải ghi AI bấm đã nhận tiền"
    # Vận đơn đã tạo rồi mới ghi tiền: phải nhắc sửa COD bên hãng.
    r = qt.post(f"/api/orders/{oid}/da-thu-tien", json={"so_tien": 1500000}).json()
    assert ma_vd in r["can_sua_cod"] and r["thu_ho_cod"] == 0


def test_da_thu_tien_chan_so_am_don_huy_va_ghi_nhat_ky(app_that):
    qt = _quan_tri_vao(app_that)
    oid, _ = _don(app_that, "da_chot")
    assert qt.post(f"/api/orders/{oid}/da-thu-tien", json={"so_tien": 0}).status_code == 422
    huy, _ = _don(app_that, "da_huy")
    assert qt.post(f"/api/orders/{huy}/da-thu-tien", json={"so_tien": 1}).status_code == 409
    assert qt.post(f"/api/orders/{oid}/da-thu-tien", json={"so_tien": 1}).status_code == 200
    assert _dong(app_that, "SELECT count(*) n FROM events WHERE kind='thanh_toan.da_thu_tien'")["n"] == 1


def test_tien_thu_ho_khong_bao_gio_am():
    from agent.shipping.service import tien_thu_ho

    assert tien_thu_ho({"tong_tien": 300000, "so_tien_da_thu": 0}) == 300000
    assert tien_thu_ho({"tong_tien": 300000, "so_tien_da_thu": 330000}) == 0
    assert tien_thu_ho({"tong_tien": 300000}) == 300000


def test_man_don_co_nut_da_nhan_tien_dung_hoi_hop():
    js = (ROOT / "dashboard" / "src" / "05-don-kho.js").read_text(encoding="utf-8")
    assert "data-odathu" in js and '"/da-thu-tien"' in js
    khoi = js[js.index('$$("[data-odathu]")'):][:1200]
    assert "hoiHop(" in khoi and "prompt(" not in khoi
    assert "Đã thu" in js and "o.so_tien_da_thu" in js


def test_migration_them_cot_tien_khong_dung_schema():
    mig = (ROOT / "agent" / "migrations" / "versions"
           / "0041_don_hang_tien_va_chong_trung.sql").read_text(encoding="utf-8")
    sql = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    for cot in ("so_tien_da_thu", "da_thu_luc", "da_thu_boi"):
        assert cot in mig and cot not in sql


# ================================================================ 5. huỷ giữa chừng

def test_huy_trong_luc_tao_van_don_thi_khong_song_lai(app_that, monkeypatch):
    from agent import canh_gac
    from agent.shipping import service
    from agent.shipping.models import CreateWaybillResult

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: None)
    _ton(app_that)
    oid, ma = _don(app_that, "da_chot")
    hang = service.get_provider("mock")

    async def tao_roi_bi_huy(req):
        from agent import db
        await db.execute("UPDATE orders SET trang_thai='da_huy' WHERE ma_don=$1", req.ma_don)
        return CreateWaybillResult(ok=True, ma_van_don="MV-HUY-1", don_vi="mock")
    monkeypatch.setattr(hang, "tao_van_don", tao_roi_bi_huy)

    async def goi():
        return await service.tao_van_don_cho_don(ma, "mock")
    kq = _sql(app_that, goi)
    assert kq.ok is False and "MV-HUY-1" in kq.loi
    d = _dong(app_that, "SELECT trang_thai, ma_van_don FROM orders WHERE id=$1::uuid", oid)
    assert d["trang_thai"] == "da_huy" and d["ma_van_don"] is None
    viec = _dong(app_that, "SELECT count(*) n FROM cong_viec WHERE nguon='van_chuyen' "
                 "AND tieu_de LIKE '%MV-HUY-1%'")
    assert viec["n"] == 1


def test_vong_erp_khong_lam_song_lai_don_da_huy(app_that, monkeypatch):
    from agent import canh_gac
    from agent.erp.vong_dong_bo import PostgresKhoDon

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: None)
    oid, ma = _don(app_that, "da_huy")
    kd = PostgresKhoDon()

    async def lam():
        da_day = await kd.danh_dau_da_day(uuid.UUID(oid), "SAL-ORD-HUY")
        await kd.danh_dau_bo_cuoc(uuid.UUID(oid), "bỏ cuộc")
        return da_day
    assert _sql(app_that, lam) is False
    d = _dong(app_that, "SELECT trang_thai, erp_ma_don FROM orders WHERE id=$1::uuid", oid)
    assert d["trang_thai"] == "da_huy", "đơn huỷ sống lại"
    assert d["erp_ma_don"] == "SAL-ORD-HUY", "người huỷ tay cần biết mã ERP"
    viec = _dong(app_that, "SELECT count(*) n FROM cong_viec WHERE nguon='don_hang' "
                 "AND tieu_de LIKE '%SAL-ORD-HUY%'")
    assert viec["n"] == 1


def test_day_don_da_luu_khong_lam_song_lai_don_da_huy(app_that, monkeypatch):
    from agent.erp import day_don

    async def gia(**kw):
        return day_don.KetQuaDay(ket_cuc="cho_lai", ly_do="mạng chớp")
    monkeypatch.setattr(day_don, "day_don", gia)
    oid, ma = _don(app_that, "da_huy")

    async def lam():
        return await day_don.day_don_da_luu(uuid.UUID(oid), ma_don=ma, khach_ten="", khach_sdt="",
                                            khach_dia_chi="", items=[])
    _sql(app_that, lam)
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id=$1::uuid",
                 oid)["trang_thai"] == "da_huy"


def test_huy_don_cho_dong_bo_nhac_kiem_erp(app_that):
    qt = _quan_tri_vao(app_that)
    oid, ma = _don(app_that, "cho_dong_bo")
    r = qt.post(f"/api/orders/{oid}/cancel").json()
    assert "ERP" in r["can_huy_tay"] and ma in r["can_huy_tay"]


# ================================================================ 6. đơn đã giao

def test_khong_huy_duoc_don_da_giao(app_that):
    qt = _quan_tri_vao(app_that)
    _ton(app_that, so=7)
    oid, ma = _don(app_that, "da_giao")
    r = qt.post(f"/api/orders/{oid}/cancel")
    assert r.status_code == 409 and "đổi trả" in r.json()["detail"]
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id=$1::uuid", oid)["trang_thai"] == "da_giao"
    assert _dong(app_that, "SELECT so_luong FROM ton_kho WHERE ma='SP1'")["so_luong"] == 7


def test_hang_bao_da_giao_don_da_huy_thi_giu_trang_thai_va_sinh_viec(app_that, monkeypatch):
    from agent import canh_gac
    from agent.config import settings

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: None)
    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat-kiem-thu")
    oid, ma = _don(app_that, "da_huy", ma_van_don="MV-DG-1")
    kq = _webhook(app_that, ma, "delivered", "MV-DG-1")
    assert kq["ok"] and kq.get("can_nguoi_xem") is True
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id=$1::uuid", oid)["trang_thai"] == "da_huy"
    assert _dong(app_that, "SELECT count(*) n FROM events WHERE kind='shipping.giao_don_da_huy'")["n"] == 1
    assert _dong(app_that, "SELECT count(*) n FROM cong_viec WHERE nguon='don_hang' "
                 "AND tieu_de LIKE '%' || $1 || '%'", ma)["n"] == 1


def test_xin_huy_khong_gan_len_don_da_giao(app_that):
    from agent.core import tools

    conv = _hoi_thoai(app_that)
    oid, ma = _don(app_that, "da_giao", conversation_id=conv)

    async def gan():
        return await tools._danh_dau_xin_huy(ma, conv, "đổi ý")
    assert _sql(app_that, gan) is False
    assert _dong(app_that, "SELECT yeu_cau_huy_luc FROM orders WHERE id=$1::uuid",
                 oid)["yeu_cau_huy_luc"] is None


# ================================================================ 10. duyệt đơn đã bỏ cuộc

def test_duyet_don_erp_da_bo_cuoc_thi_dat_lai_so_lan_thu(app_that, monkeypatch):
    from agent.erp import day_don

    async def gia(**kw):
        return day_don.KetQuaDay(ket_cuc="cho_lai", ly_do="ERP bảo trì")
    monkeypatch.setattr(day_don, "day_don", gia)
    qt = _quan_tri_vao(app_that)
    oid, _ = _don(app_that, "cho_duyet", erp_so_lan_thu=8)
    assert qt.post(f"/api/orders/{oid}/approve").status_code == 200
    d = _dong(app_that, "SELECT trang_thai, erp_so_lan_thu FROM orders WHERE id=$1::uuid", oid)
    assert d["trang_thai"] == "cho_dong_bo"
    assert d["erp_so_lan_thu"] == 1, "vòng nền sẽ bỏ cuộc ngay lập tức"


# ================================================================ 11. tra cứu vận chuyển

def test_tra_cuu_van_chuyen_chi_don_cua_hoi_thoai(app_that):
    from agent.core import tools

    cua_lan = _hoi_thoai(app_that)
    nguoi_la = _hoi_thoai(app_that)
    _, ma = _don(app_that, "da_chot", conversation_id=cua_lan, ma_van_don="GHN-BI-MAT",
                 trang_thai_giao_hang="delivering")

    async def tra(ma_don, conv):
        return await tools.run_tool("tra_cuu_van_chuyen", {"ma_don": ma_don},
                                    conversation_id=conv)
    la = _sql(app_that, tra, ma, nguoi_la)
    assert la["tim_thay"] is False and la["can_xac_minh"] is True
    assert "GHN-BI-MAT" not in json.dumps(la, ensure_ascii=False)
    # Mã bịa và mã của người khác phải nhận CÙNG một câu — khác câu là lộ.
    assert _sql(app_that, tra, "AS000000000000XXX", nguoi_la) == la
    assert _sql(app_that, tra, ma, None) == la
    minh = _sql(app_that, tra, ma.lower(), cua_lan)
    assert minh["tim_thay"] is True and minh["ma_van_don"] == "GHN-BI-MAT"


# ================================================================ 7. lọc trạng thái giao từ ERP

def test_erpnext_loc_phieu_giao_theo_sales_order():
    """Test cũ dùng ERP giả trả kết quả cho MỌI bộ lọc — xanh giả. Đây soi bộ lọc."""
    from agent.erp.erpnext import NguonErpNext
    from tests.erp_gia import chay

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/Delivery Note"):
            loc = json.loads(req.url.params["filters"])
            khop = ["Delivery Note Item", "against_sales_order", "=", "SAL-ORD-0007"] in loc
            return httpx.Response(200, json={"data": [
                {"name": "DN-1", "status": "Completed"}] if khop else []})
        return httpx.Response(200, json={"data": []})

    n = NguonErpNext(goc="https://erp.thu", api_key="k", api_secret="s", ma_kho="K",
                     pricelist="P", client=httpx.AsyncClient(
                         transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"))
    assert chay(n.trang_thai_giao("SAL-ORD-0007")) == "delivered"
    assert chay(n.trang_thai_giao("SAL-ORD-0008")) is None


def test_odoo_loc_picking_theo_ten_sale_order():
    from agent.erp.odoo import NguonOdoo
    from tests.erp_gia import chay

    def xu_ly(req: httpx.Request) -> httpx.Response:
        p = json.loads(req.content)["params"]
        if p["service"] == "common":
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": 7})
        if p["args"][3] == "stock.picking":
            mien = p["args"][5][0]
            khop = ["sale_id.name", "=", "S00042"] in mien
            return httpx.Response(200, json={"jsonrpc": "2.0", "result": (
                [{"id": 1, "state": "done"}] if khop else [])})
        return httpx.Response(200, json={"jsonrpc": "2.0", "result": []})

    n = NguonOdoo(goc="https://odoo.thu", db="thu", dang_nhap="a@b.vn", api_key="k",
                  ma_kho="K", client=httpx.AsyncClient(
                      transport=httpx.MockTransport(xu_ly), base_url="https://odoo.thu"))
    assert chay(n.trang_thai_giao("S00042")) == "delivered"
    assert chay(n.trang_thai_giao("S00043")) is None


# ================================================================ 8. ERPNext submit

def _erpnext_submit(xu_ly):
    from agent.erp.erpnext import NguonErpNext

    return NguonErpNext(goc="https://erp.thu", api_key="k", api_secret="s", ma_kho="K",
                        pricelist="P", submit_don=True, client=httpx.AsyncClient(
                            transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"))


def test_tim_don_thay_ban_nhap_thi_submit_lai():
    from tests.erp_gia import chay

    da_put = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path.endswith("/Sales Order"):
            return httpx.Response(200, json={"data": [{"name": "SO-9", "docstatus": 0}]})
        if req.method == "PUT":
            da_put.append(req.url.path)
            return httpx.Response(200, json={"data": {"name": "SO-9", "docstatus": 1}})
        return httpx.Response(200, json={"data": []})

    assert chay(_erpnext_submit(xu_ly).tim_don("AS1")) == "SO-9"
    assert da_put and da_put[0].endswith("/Sales Order/SO-9")


@pytest.mark.parametrize("hong", ["mang", "5xx"])
def test_submit_hong_mang_hoac_5xx_la_LoiERP(hong):
    from agent.erp.hop_dong import LoiERP
    from tests.erp_gia import chay

    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "PUT":
            if hong == "mang":
                raise httpx.ConnectError("đứt", request=req)
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"data": [{"name": "SO-9", "docstatus": 0}]})

    with pytest.raises(LoiERP):
        chay(_erpnext_submit(xu_ly).tim_don("AS1"))


def test_ly_do_chua_submit_di_len_ket_qua_va_nhat_ky(monkeypatch):
    from agent.config import settings
    from agent.erp import day_don
    from agent.erp.hop_dong import KetQuaDon, NguonGhiERP
    from tests.erp_gia import chay

    class Nguon(NguonGhiERP):  # type: ignore[misc]
        ten = "gia"

        async def tim_don(self, khoa):
            return None

        async def bao_dam_khach(self, ten, sdt, dia_chi):
            return "KH-1"

        async def tao_don(self, khoa, khach_id, dong, ghi_chu=""):
            return KetQuaDon(thanh_cong=True, erp_ma_don="SO-1",
                             ly_do="đơn đã tạo nhưng CHƯA submit (x)")

    nhat_ky = []

    async def ghi(loai, **ct):
        nhat_ky.append(loai)
    monkeypatch.setattr(settings, "erp_ghi_don", True)
    monkeypatch.setattr(day_don, "_ghi_nhat_ky", ghi)
    kq = chay(day_don.day_don("AS1", "Lan", "0912345678", DIA_CHI,
                              [{"ma": "SP1", "so_luong": 1, "don_gia": 1}], nguon=Nguon()))
    assert kq.ket_cuc == "xong" and "CHƯA submit" in kq.ly_do
    assert "erp.don_chua_submit" in nhat_ky
