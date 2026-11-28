"""
Regression tests cho giao diện quản trị & API đọc bảng/chi tiết Đơn hàng:
  - GET /api/orders/bang: tìm kiếm (mã đơn, tên, SĐT), lọc trạng thái, kênh,
    thanh toán, vận chuyển, ngày, KPI, đếm chip, phân trang và phạm vi kênh.
  - GET /api/orders/{order_id}: chi tiết 3 tab (tổng quan, vận chuyển + đối soát
    + biến động kho, đồng bộ ERP), chặn 404 ngoài phạm vi kênh và 403 thiếu quyền.
  - Giữ nguyên tương thích ngược của GET /api/orders và bảo toàn kênh cũ zalocrm.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from agent import db
from tests.test_nghiem_thu_saas import _quan_tri_vao


def _chay(app_that, coro):
    return app_that.portal.call(lambda: coro)


def test_api_bang_va_chi_tiet_don_hang_day_du(app_that):
    qt = _quan_tri_vao(app_that)

    async def seed():
        oid1, oid2, oid3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        ma1, ma2, ma3 = f"DHUX-{oid1.hex[:6]}", f"DHUX-{oid2.hex[:6]}", f"DHUX-{oid3.hex[:6]}"
        items = [{"ma": "SP-UX", "ten": "Kem Dưỡng UX", "don_gia": 200000, "so_luong": 1, "thanh_tien": 200000}]
        now = datetime.now(timezone.utc)
        await db.execute("INSERT INTO ton_kho (ma, so_luong) VALUES ('SP-UX', 50) ON CONFLICT (ma) DO NOTHING")
        # 1. Đơn Webchat chờ duyệt, chưa thu
        await db.execute(
            """INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai, created_at)
               VALUES ($1,$2,'webchat','Nguyễn Minh Anh','0901234567','10 Hai Bà Trưng, Q1',$3::jsonb,200000,'cho_duyet',$4)""",
            oid1, ma1, items, now - timedelta(hours=2),
        )
        # 2. Đơn cũ zalocrm đã chốt, đã thu đủ, có vận đơn delivery_failed + ERP dead
        await db.execute(
            """INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai,
                                   so_tien_da_thu, da_thu_luc, ma_van_don, don_vi_van_chuyen, trang_thai_giao_hang,
                                   van_don_da_lay_hang, phi_van_chuyen, erp_ma_don, erp_van_chuyen_trang_thai,
                                   erp_van_chuyen_loi, lich_su_giao_hang, created_at)
               VALUES ($1,$2,'zalocrm','Trần Bảo Châu','0987654321','20 Nguyễn Huệ, Q1',$3::jsonb,200000,'da_chot',
                       200000,now(),'GHNUX999','ghn','delivery_failed',true,30000,'SAL-UX-9','dead',
                       'Lỗi kết nối ERP',$4::jsonb,$5)""",
            oid2, ma2, items,
            [{"time": now.isoformat(), "status": "delivery_fail", "carrier": "ghn", "description": "Khách hẹn lại"}],
            now - timedelta(hours=1),
        )
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don) VALUES ('SP-UX', -1, 'ban', $1)",
            ma2,
        )
        # 3. Đơn Facebook đã hoàn về (returned) + công việc kiểm hàng hoàn
        await db.execute(
            """INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai,
                                   ma_van_don, don_vi_van_chuyen, trang_thai_giao_hang, van_don_da_lay_hang, created_at)
               VALUES ($1,$2,'facebook','Lê Thu Hà','0911222333','30 Lê Duẩn, Q1',$3::jsonb,200000,'da_huy',
                       'GHNUX888','ghn','returned',true,$4)""",
            oid3, ma3, items, now - timedelta(days=3),
        )
        await db.execute(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, order_id, khoa_chong_trung) "
            "VALUES ($1, 'Kiểm tra nguyên seal', 'don_hang', 'cao', $2, $3)",
            f"Kiểm tra hàng hoàn đơn {ma3}", oid3, f"don_hang:kiem_hang_hoan:{ma3}",
        )
        return (str(oid1), ma1), (str(oid2), ma2), (str(oid3), ma3)

    (oid1, ma1), (oid2, ma2), (oid3, ma3) = _chay(app_that, seed())

    # 1. KPI & đếm chip
    r_all = qt.get("/api/orders/bang?page=1&page_size=20")
    assert r_all.status_code == 200
    d_all = r_all.json()
    assert d_all["kpi"]["tong_don"] >= 3
    assert d_all["kpi"]["cho_duyet"] >= 1
    assert d_all["kpi"]["can_xu_ly"] >= 2  # cho_duyet + delivery_failed/erp dead
    assert d_all["dem_trang_thai"]["all"] == d_all["kpi"]["tong_don"]

    # 2. Tìm kiếm theo SĐT, tên, mã đơn
    assert any(x["ma_don"] == ma2 for x in qt.get("/api/orders/bang?q=0987654321").json()["items"])
    assert any(x["ma_don"] == ma1 for x in qt.get("/api/orders/bang?q=Minh+Anh").json()["items"])
    assert [x["ma_don"] for x in qt.get(f"/api/orders/bang?q={ma3}").json()["items"]] == [ma3]

    # 3. Lọc theo kênh (không gán sai đơn zalocrm cũ thành webchat)
    r_web = qt.get("/api/orders/bang?channel=webchat").json()["items"]
    assert any(x["ma_don"] == ma1 for x in r_web)
    assert all(x["ma_don"] != ma2 for x in r_web)
    r_old = qt.get("/api/orders/bang?channel=zalocrm").json()["items"]
    assert any(x["ma_don"] == ma2 and x["channel"] == "zalocrm" for x in r_old)
    r_fb = qt.get("/api/orders/bang?channel=facebook").json()["items"]
    assert any(x["ma_don"] == ma3 for x in r_fb)

    # 4. Lọc theo thanh toán, vận chuyển, cần xử lý, phân trang
    assert any(x["ma_don"] == ma2 for x in qt.get("/api/orders/bang?thanh_toan=da_thu_du").json()["items"])
    assert all(x["ma_don"] != ma2 for x in qt.get("/api/orders/bang?thanh_toan=chua_thu").json()["items"])
    assert any(x["ma_don"] == ma2 for x in qt.get("/api/orders/bang?van_chuyen=delivery_failed").json()["items"])
    assert any(x["ma_don"] == ma3 for x in qt.get("/api/orders/bang?van_chuyen=returned").json()["items"])
    assert any(x["ma_don"] == ma2 for x in qt.get("/api/orders/bang?status=can_xu_ly").json()["items"])
    r_pg = qt.get("/api/orders/bang?page=1&page_size=5").json()
    assert r_pg["page"] == 1 and r_pg["page_size"] == 5 and len(r_pg["items"]) <= 5

    # 5. Chi tiết đơn hàng 3 tab (GET /api/orders/{id})
    det2 = qt.get(f"/api/orders/{oid2}")
    assert det2.status_code == 200
    b2 = det2.json()
    assert b2["ma_don"] == ma2 and b2["erp_ma_don"] == "SAL-UX-9"
    assert len(b2["lich_su_giao_hang"]) == 1
    assert any(bd["ly_do"] == "ban" for bd in b2["bien_dong_kho"])
    assert b2["reconciliation"]["client_order_code"] == ma2

    det3 = qt.get(f"/api/orders/{oid3}").json()
    assert any("Kiểm tra hàng hoàn" in c["tieu_de"] for c in det3["cong_viec"])

    # 6. 404 với ID không tồn tại
    assert qt.get(f"/api/orders/{uuid.uuid4()}").status_code == 404

    # Bộ lọc ngày Việt Nam, giao nhau nhiều điều kiện và API cũ vẫn đọc được.
    assert any(x["id"] == oid2 for x in qt.get(
        "/api/orders/bang?channel=zalocrm&thanh_toan=da_thu_du&van_chuyen=delivery_failed"
    ).json()["items"])
    assert any(x["id"] == oid1 for x in qt.get("/api/orders").json())
    assert qt.get("/api/orders/bang?q=KHONG-CO-DON-UX").json()["total"] == 0
    assert qt.get("/api/orders/bang?page=999").json()["page"] == d_all["total_pages"]
    assert qt.get("/api/orders/bang?tu_ngay=2099-01-01").json()["total"] == 0


@pytest.mark.parametrize("query", [
    "tu_ngay=2026-02-30", "den_ngay=invalid",
    "tu_ngay=2026-12-02&den_ngay=2026-12-01", "page=0", "page_size=101",
])
def test_bo_loc_khong_hop_le_tra_422(app_that, query):
    qt = _quan_tri_vao(app_that)
    assert qt.get("/api/orders/bang?" + query).status_code == 422


def test_ngay_loc_theo_mui_gio_viet_nam():
    from agent.api.don_kho import _ngay_dau
    assert _ngay_dau("2026-11-27") == datetime(2026, 11, 26, 17, tzinfo=timezone.utc)
    assert _ngay_dau("") is None


def test_quyen_va_pham_vi_bang_chi_tiet(app_that):
    from conftest import _quan_tri, nguoi_thu
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.main import app
    from tests.test_don_hang_tien_erp import _hoi_thoai

    qt = _quan_tri_vao(app_that)
    cid = _hoi_thoai(app_that)

    async def seed():
        uid, _ = await _quan_tri("order-reader")
        oid = await db.fetchrow(
            "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, "
            "khach_dia_chi, items, tong_tien) VALUES ($1,$2,'UX','0900000000','Test','[]',100) RETURNING id",
            "DH-SCOPE-" + uuid.uuid4().hex[:8], cid,
        )
        return uid, str(oid["id"])

    uid, oid = _chay(app_that, seed())
    user = nguoi_thu("don.doc", id=str(uid))
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: user
    try:
        assert qt.get("/api/orders/bang").json()["total"] == 0
        assert qt.get(f"/api/orders/{oid}").status_code == 404
        _chay(app_that, db.execute(
            "INSERT INTO account_memberships (account_id,user_id) SELECT account_id,$1 FROM conversations WHERE id=$2",
            uid, cid,
        ))
        assert qt.get("/api/orders/bang").json()["total"] == 1
        assert qt.get(f"/api/orders/{oid}").status_code == 200
        user["quyen"] = frozenset()
        assert qt.get("/api/orders/bang").status_code == 403
        assert qt.get(f"/api/orders/{oid}").status_code == 403
    finally:
        app.dependency_overrides.pop(nguoi_da_dang_nhap, None)
