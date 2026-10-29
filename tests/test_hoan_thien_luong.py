"""
Bốn đường đứt tìm ra khi soát tài liệu luồng (rà soát 29.10.2026).

Cả bốn cùng một kiểu hỏng IM LẶNG: có mã, có test cho phần lõi, nhưng không
nối vào đâu — hoặc nối nửa chừng.

  1. Nút Duyệt đơn không đẩy ERP, và duyệt được cả đơn đã huỷ.
  2. Hàm tạo vận đơn (bốn chốt) không có API, không có nút.
  3. Hãng báo giao thất bại / mã lạ: chỉ một dòng nhật ký, không ai được giao.
  4. Chuyển người trên Zalo, IG, WhatsApp, web: nhân viên không được báo.

Thêm một lỗi tìm ra trên đường: API danh sách đơn không trả các trường màn
hình vẽ, nên cờ "Khách xin huỷ" không bao giờ hiện.

Phần đụng CSDL chạy trên `app_that` — app đầy đủ, Postgres thật.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _quan_tri_vao, _sql,
)

JS_DON = (ROOT / "dashboard" / "src" / "05-don-kho.js").read_text(encoding="utf-8")


def _don(app, trang_thai: str, **them) -> tuple[str, str]:
    """Một đơn nằm thẳng trong CSDL. Trả (id, mã đơn)."""
    from agent import db

    ma = "DH" + uuid.uuid4().hex[:8].upper()

    async def tao():
        r = await db.fetchrow(
            "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, items, "
            "tong_tien, trang_thai) VALUES ($1, 'Chị Lan', '0912345678', "
            "'12 Lê Lợi, Phường Bến Thành, TP Hồ Chí Minh', $2, 1500000, $3) RETURNING id",
            ma, [{"ma": "SP1", "ten": "Kem", "so_luong": 1, "don_gia": 1500000,
                  "thanh_tien": 1500000}], trang_thai)
        for k, v in them.items():
            await db.execute(f"UPDATE orders SET {k} = $2 WHERE id = $1", r["id"], v)
        return str(r["id"])
    return _sql(app, tao), ma


def _dong(app, sql: str, *args):
    from agent import db

    async def doc():
        return await db.fetchrow(sql, *args)
    return _sql(app, doc)


# ------------------------------------------------------------- 1. duyệt đơn

def test_duyet_don_day_sang_erp_va_ghi_ma(app_that, monkeypatch):
    from agent.erp import day_don

    goi = []

    async def gia(**kw):
        goi.append(kw["ma_don"])
        return day_don.KetQuaDay(ket_cuc="xong", erp_ma_don="SAL-ORD-0001")
    monkeypatch.setattr(day_don, "day_don", gia)

    qt = _quan_tri_vao(app_that)
    oid, ma = _don(app_that, "cho_duyet")
    r = qt.post(f"/api/orders/{oid}/approve")
    assert r.status_code == 200, r.text
    assert r.json()["erp_ma_don"] == "SAL-ORD-0001" and goi == [ma]
    d = _dong(app_that, "SELECT trang_thai, erp_ma_don FROM orders WHERE id = $1::uuid", oid)
    assert d["trang_thai"] == "da_chot" and d["erp_ma_don"] == "SAL-ORD-0001"


def test_khong_duyet_duoc_don_da_huy_hay_da_duyet(app_that, monkeypatch):
    """Duyệt đơn đã huỷ là bán món đã trả về kho mà không trừ lại."""
    from agent.erp import day_don

    async def gia(**kw):
        return day_don.KetQuaDay(ket_cuc="tat")
    monkeypatch.setattr(day_don, "day_don", gia)

    qt = _quan_tri_vao(app_that)
    huy, _ = _don(app_that, "da_huy")
    assert qt.post(f"/api/orders/{huy}/approve").status_code == 409
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id = $1::uuid",
                 huy)["trang_thai"] == "da_huy"

    oid, _ = _don(app_that, "cho_duyet")
    assert qt.post(f"/api/orders/{oid}/approve").status_code == 200
    assert qt.post(f"/api/orders/{oid}/approve").status_code == 409
    assert qt.post("/api/orders/khong-phai-uuid/approve").status_code == 404


def test_erp_tu_choi_khi_duyet_thi_huy_don_va_tra_kho(app_that, monkeypatch):
    from agent.core import kho
    from agent.erp import day_don

    async def gia(**kw):
        return day_don.KetQuaDay(ket_cuc="tu_choi", ly_do="Hết hàng bên ERP")
    tra = []

    async def gia_tra(ma_don, ly_do="huy_don"):
        tra.append((ma_don, ly_do))
        return 1
    monkeypatch.setattr(day_don, "day_don", gia)
    monkeypatch.setattr(kho, "tra_hang", gia_tra)

    qt = _quan_tri_vao(app_that)
    oid, ma = _don(app_that, "cho_duyet")
    r = qt.post(f"/api/orders/{oid}/approve").json()
    assert r["ok"] is False and r["erp"] == "tu_choi" and r["trang_thai"] == "da_huy"
    assert tra == [(ma, "erp_tu_choi")]
    d = _dong(app_that, "SELECT trang_thai, erp_loi FROM orders WHERE id = $1::uuid", oid)
    assert d["trang_thai"] == "da_huy" and "Hết hàng" in d["erp_loi"]


def test_erp_mat_mang_khi_duyet_thi_cho_dong_bo():
    """Vòng nền chỉ thử lại `cho_dong_bo` — đơn duyệt mà lỗi mạng phải vào đúng hàng ấy."""
    import inspect

    from agent.erp import day_don

    src = inspect.getsource(day_don.day_don_da_luu)
    assert "trang_thai='cho_dong_bo'" in src and "erp_so_lan_thu + 1" in src


def test_lo_agent_va_lo_duyet_dung_chung_mot_ham_day_erp():
    """Hai bản của cùng ba kết cục là hai bản sớm muộn lệch nhau."""
    import inspect

    from agent.api import don_kho
    from agent.core import tools

    assert "day_don_da_luu(" in inspect.getsource(don_kho.approve_order)
    assert "_day_don.day_don_da_luu(" in inspect.getsource(tools)
    assert "_day_don.day_don(" not in inspect.getsource(tools)


def test_huy_don_da_co_ben_erp_thi_nhac_huy_tay(app_that):
    qt = _quan_tri_vao(app_that)
    oid, _ = _don(app_that, "da_chot", erp_ma_don="SAL-9", ma_van_don="GHN123")
    r = qt.post(f"/api/orders/{oid}/cancel").json()
    assert "SAL-9" in r["can_huy_tay"] and "GHN123" in r["can_huy_tay"]


# ------------------------------------------------------------- 2. vận đơn

def test_khong_tao_van_don_bang_hang_gia_lap(app_that, monkeypatch):
    """Vận đơn giả vẫn nhắn khách một mã không tra được ở đâu."""
    from agent.config import settings

    monkeypatch.setattr(settings, "shipping_provider", "mock")
    qt = _quan_tri_vao(app_that)
    oid, _ = _don(app_that, "da_chot")
    assert qt.get("/api/van-chuyen/cau-hinh").json() == {"hang": "mock", "that": False}
    r = qt.post(f"/api/orders/{oid}/van-don", json={})
    assert r.status_code == 409 and "SHIPPING_PROVIDER" in r.text
    r = qt.post(f"/api/orders/{oid}/van-don", json={"hang": "mock"})
    assert r.status_code == 409


def test_tao_van_don_goi_ham_bon_chot_va_bao_loi_ro(app_that, monkeypatch):
    from agent.config import settings
    from agent.shipping import service
    from agent.shipping.models import CreateWaybillResult

    goi = []

    async def gia(ma_don, hang):
        goi.append((ma_don, hang))
        if len(goi) == 1:
            return CreateWaybillResult(ok=True, ma_van_don="GHN-77", don_vi="ghn")
        return CreateWaybillResult(ok=False, loi="Thiếu thông tin giao hàng: Tên người nhận.")
    monkeypatch.setattr(settings, "shipping_provider", "ghn")
    monkeypatch.setattr(service, "tao_van_don_cho_don", gia)

    qt = _quan_tri_vao(app_that)
    assert qt.get("/api/van-chuyen/cau-hinh").json()["that"] is True
    oid, ma = _don(app_that, "da_chot")
    r = qt.post(f"/api/orders/{oid}/van-don", json={})
    assert r.status_code == 200 and r.json()["ma_van_don"] == "GHN-77"
    r = qt.post(f"/api/orders/{oid}/van-don", json={})
    assert r.status_code == 422 and "Tên người nhận" in r.json()["detail"]
    assert goi == [(ma, "ghn"), (ma, "ghn")]


def test_tao_van_don_khoa_theo_ma_don():
    """Hai cú bấm cùng lúc đều thấy 'chưa có mã vận đơn' — phải có khoá."""
    import inspect

    from agent.api import don_kho

    src = inspect.getsource(don_kho.tao_van_don)
    assert "pg_try_advisory_lock" in src and "pg_advisory_unlock" in src
    assert src.index("pg_advisory_unlock") > src.index("tao_van_don_cho_don(")


def test_tao_van_don_can_quyen_sua_don(app_that):
    from tests.test_nghiem_thu_saas import _nhan_vien_moi

    qt = _quan_tri_vao(app_that)
    _, ke_toan = _nhan_vien_moi(qt, "chixem", vai_tro=None)
    oid, _ = _don(app_that, "da_chot")
    assert ke_toan.post(f"/api/orders/{oid}/van-don", json={}).status_code == 403


# ------------------------------------------------------------- 3. vận chuyển sinh việc

def _webhook(app, ma_don: str, status: str, ma_van_don: str):
    from agent.shipping import service

    async def goi():
        return await service.xu_ly_webhook_van_chuyen(
            "mock", {"ma_don": ma_don, "ma_van_don": ma_van_don, "status": status,
                     "mo_ta": "Khách không nghe máy"},
            {}, query_token="bi-mat-kiem-thu")
    return _sql(app, goi)


def _viec_van_chuyen(app, ma_don: str) -> list[dict]:
    from agent import db

    async def doc():
        return await db.fetch(
            "SELECT tieu_de, uu_tien, nguon FROM cong_viec WHERE nguon = 'van_chuyen' "
            "AND (tieu_de LIKE '%' || $1 || '%' OR mo_ta LIKE '%' || $1 || '%')", ma_don)
    return _sql(app, doc)


def test_giao_that_bai_sinh_mot_viec_du_hang_phat_lai(app_that, monkeypatch):
    from agent import canh_gac
    from agent.config import settings

    bao = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: bao.append(t))
    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat-kiem-thu")
    _, ma = _don(app_that, "da_chot", ma_van_don="MV-1")

    assert _webhook(app_that, ma, "delivery_fail", "MV-1")["ok"]
    assert _webhook(app_that, ma, "delivery_fail", "MV-1")["ok"]     # hãng phát lại
    viec = _viec_van_chuyen(app_that, ma)
    assert len(viec) == 1 and viec[0]["uu_tien"] == "cao"
    assert "hẹn giao lại" in viec[0]["tieu_de"]
    assert bao == [viec[0]["tieu_de"]]                               # báo đúng một lần


def test_ma_trang_thai_la_sinh_viec_va_giu_nguyen_don(app_that, monkeypatch):
    from agent import canh_gac
    from agent.config import settings

    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: None)
    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat-kiem-thu")
    oid, ma = _don(app_that, "da_chot", ma_van_don="MV-2")

    kq = _webhook(app_that, ma, "ma_chua_tung_thay", "MV-2")
    assert kq["can_nguoi_xem"] is True
    viec = _viec_van_chuyen(app_that, "MV-2")
    assert len(viec) == 1 and "mã lạ" in viec[0]["tieu_de"]
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id = $1::uuid",
                 oid)["trang_thai"] == "da_chot"


# ------------------------------------------------------------- 4. báo nhân viên

def test_chuyen_nguoi_o_kenh_web_bao_nhan_vien_mot_lan(app_that, monkeypatch):
    """
    Kênh web không có `bao_chuyen_nguoi` — trước bản này nhân viên chỉ thấy
    con số nhảy trên dashboard. Nay mọi việc chuyển người MỚI đều báo ra
    ngoài, và khách nhắn thêm không thành thêm tin báo.
    """
    from agent import canh_gac

    bao: list[tuple[str, str]] = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen", lambda t, c: bao.append((t, c)))
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)                     # agent TẮT ở kênh này → chuyển người
    _khach_nhan(app_that, tk, "Chị Mai", "Cho em hỏi giá kem")
    _khach_nhan(app_that, tk, "Chị Mai", "Shop ơi")
    assert len(bao) >= 1
    assert all("Chat web" in c for _, c in bao)
    # Hai tin của CÙNG một khách (cùng phiên) chỉ một tin báo; webchat mở
    # phiên mới mỗi lần `_khach_nhan` nên có thể là hai hội thoại — đếm theo
    # số việc tự sinh, không theo số tin.
    from agent import db

    async def dem():
        return (await db.fetchrow(
            "SELECT count(*) n FROM cong_viec WHERE nguon = 'agent'"))["n"]
    assert len(bao) == _sql(app_that, dem)


def test_tin_bao_nhan_vien_khong_mang_ly_do_hay_loi_khach():
    """Lý do chuyển người có thể là 'mang thai', 'bệnh da' — dữ liệu sức khoẻ."""
    import inspect

    from agent.core import cong_viec

    src = inspect.getsource(cong_viec._bao_viec_moi_cho_nhan_vien)
    assert "ly_do" not in src.split('"""')[2]
    assert "customer_name" not in src


def test_bao_nhan_vien_dung_mau_va_khong_ghi_url_khi_loi(monkeypatch):
    import httpx

    from agent import canh_gac
    from agent.config import settings

    nhat_ky: list[dict] = []

    async def ghi(kind, **kw):
        nhat_ky.append({"kind": kind, **kw})
    monkeypatch.setattr(canh_gac.db, "log_event", ghi)

    gui: list[tuple[str, dict]] = []

    class Gia:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json):
            gui.append((url, json))
            yeu_cau = httpx.Request("POST", url)
            return httpx.Response(500 if "hong" in url else 200, request=yeu_cau)
    monkeypatch.setattr(canh_gac.httpx, "AsyncClient", Gia)

    # Không có nơi nhận nào → không gửi.
    monkeypatch.setattr(settings, "canh_gac_webhook", "")
    monkeypatch.setattr(settings, "bao_nhan_vien_webhook", "")
    assert asyncio.run(canh_gac.bao_nhan_vien("T", "C")) is False and gui == []

    # Đi chung đường báo động, đúng mẫu của nó.
    monkeypatch.setattr(settings, "canh_gac_webhook", "https://api.telegram.org/botTOKEN/sendMessage")
    monkeypatch.setattr(settings, "canh_gac_goi_tin", '{"chat_id":"1","text":"{tieu_de}: {chi_tiet}"}')
    assert asyncio.run(canh_gac.bao_nhan_vien("Khách cần người", "Kênh Zalo")) is True
    assert gui[-1][1] == {"chat_id": "1", "text": "Khách cần người: Kênh Zalo"}

    # Nơi nhận riêng thì dùng mẫu riêng; hỏng thì ghi lại mà KHÔNG lộ URL (token).
    monkeypatch.setattr(settings, "bao_nhan_vien_webhook", "https://hong.example/botBIMAT/x")
    monkeypatch.setattr(settings, "bao_nhan_vien_goi_tin", "")
    assert asyncio.run(canh_gac.bao_nhan_vien("T", "C")) is False
    assert gui[-1][0].startswith("https://hong.example")
    loi = [n for n in nhat_ky if n["kind"] == "bao_nhan_vien.loi_gui"]
    assert loi and loi[-1]["ma_http"] == 500
    assert "BIMAT" not in repr(nhat_ky)

    # Tắt hẳn.
    monkeypatch.setattr(settings, "bao_nhan_vien_chuyen_nguoi", False)
    n = len(gui)
    assert asyncio.run(canh_gac.bao_nhan_vien("T", "C")) is False and len(gui) == n


def test_bao_nhan_vien_chay_nen_khong_chan_luong_tin():
    import inspect

    from agent.core import cong_viec

    assert "bao_nhan_vien_nen(" in inspect.getsource(cong_viec._bao_viec_moi_cho_nhan_vien)
    assert "bao_nhan_vien_nen(" in inspect.getsource(cong_viec.tao_tu_van_chuyen)


def test_env_example_khai_bao_nhan_vien():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    for k in ("BAO_NHAN_VIEN_WEBHOOK=", "BAO_NHAN_VIEN_GOI_TIN=", "BAO_NHAN_VIEN_CHUYEN_NGUOI="):
        assert k in env


# ------------------------------------------------------------- 5. màn Đơn hàng

def test_api_don_tra_moi_truong_man_hinh_doc():
    """Màn hình đọc `o.yeu_cau_huy_luc` mà API không trả = cờ xin huỷ không bao giờ hiện."""
    import inspect

    from agent.api import don_kho

    doc = set(re.findall(r"\bo\.([a-z_]+)", JS_DON))
    src = inspect.getsource(don_kho.list_orders)
    co = set(re.findall(r'"([a-z_]+)":', src)) | set(don_kho._TRUONG_PHU_DON)
    # `nen_tang` là trường tuỳ chọn của srcBadge, đơn không có cũng không sao.
    assert doc - co - {"nen_tang"} == set()


def test_api_don_tra_co_xin_huy_that(app_that):
    from datetime import datetime, timezone

    qt = _quan_tri_vao(app_that)
    oid, _ = _don(app_that, "da_chot", yeu_cau_huy_luc=datetime.now(timezone.utc),
                  yeu_cau_huy_ly_do="Đặt nhầm")
    d = next(o for o in qt.get("/api/orders").json() if o["id"] == oid)
    assert d["yeu_cau_huy_luc"] and d["yeu_cau_huy_ly_do"] == "Đặt nhầm"


def test_man_don_co_nut_van_don_va_bao_dung_ket_qua():
    assert 'data-ovandon' in JS_DON and '"/van-don"' in JS_DON
    assert '"/van-chuyen/cau-hinh"' in JS_DON
    # Không còn báo "Đã duyệt đơn." vô điều kiện khi ERP vừa từ chối.
    assert 'r.erp === "tu_choi"' in JS_DON and "can_huy_tay" in JS_DON


def test_dashboard_bao_khi_co_khach_can_nguoi():
    js = (ROOT / "dashboard" / "src" / "02-van-hanh.js").read_text(encoding="utf-8")
    assert "function baoKhachCanNguoi" in js and "new Notification(" in js
    assert "baoKhachCanNguoi(o.conversations.escalated" in js
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert 'id="batThongBao"' in html


@pytest.mark.parametrize("tep", ["agent/migrations/versions/0038_cong_viec_van_chuyen.sql"])
def test_migration_cho_nguon_van_chuyen_va_khoa_chong_trung(tep):
    sql = (ROOT / tep).read_text(encoding="utf-8")
    assert "'van_chuyen'" in sql and "khoa_chong_trung" in sql and "UNIQUE INDEX" in sql
    # Cột mới chỉ nằm trong migration — schema.sql chạy TRƯỚC migration.
    assert "khoa_chong_trung" not in (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
