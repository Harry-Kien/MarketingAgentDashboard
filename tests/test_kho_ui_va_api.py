"""
Regression tests cho các cải tiến Kho (UX-KHO-01 đến UX-KHO-07):
  - GET /api/kho/bien-dong/bang: tồn sau chính xác, tìm kiếm theo SKU/tên/mã đơn/ghi chú,
    lọc theo loại biến động/chiều tăng giảm/ngày VN, phân trang, người thực hiện và RBAC.
  - GET /api/kho/{ma}/hoan-hang-info: trả đúng điều kiện hoàn và số lượng đã bán / đã hoàn / còn lại.
  - POST /api/kho/{ma}/kiem-ke ghi đúng actor thực hiện để sổ biến động hiển thị.
  - Kiểm tra hợp đồng giao diện Kho 2 tab, nhãn giá bán, bỏ mặc định 50 và tách biệt Nhật ký.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import pytest

from agent import db
from tests.test_nghiem_thu_saas import _quan_tri_vao

ROOT = Path(__file__).resolve().parents[1]


def _chay(app_that, coro):
    return app_that.portal.call(lambda: coro)


def test_api_kho_bien_dong_bang_va_hoan_hang_info(app_that):
    qt = _quan_tri_vao(app_that)

    async def seed():
        ma = "BLA-BODY-ARMPIT-10ML"
        ma_don_ok = f"KHUX-OK-{uuid.uuid4().hex[:6]}"
        ma_don_bad = f"KHUX-BAD-{uuid.uuid4().hex[:6]}"
        oid_ok, oid_bad = uuid.uuid4(), uuid.uuid4()
        now = datetime.now(timezone.utc)

        await db.execute(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ($1, 20) "
            "ON CONFLICT (ma) DO UPDATE SET so_luong = 20",
            ma,
        )
        # Chuỗi biến động với tồn hiện tại = 20:
        # 1) ban -3 -> 2) nhap +10 -> 3) hoan_hang +1 -> 4) kiem_ke -2 => hiện tại 20
        # Vậy theo chiều mới -> cũ:
        #   kiem_ke -2  => tồn sau = 20
        #   hoan_hang +1 => tồn sau = 22
        #   nhap +10     => tồn sau = 21
        #   ban -3       => tồn sau = 11
        await db.execute(
            """INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi,
                                   items, tong_tien, trang_thai, trang_thai_giao_hang,
                                   van_don_da_lay_hang, created_at)
               VALUES ($1,$2,'webchat','Khách hoàn','0901112222','HCM','[]'::jsonb,300000,'da_chot','returned',true,$3),
                      ($4,$5,'webchat','Khách đang giao','0903334444','HN','[]'::jsonb,100000,'da_chot','delivering',true,$3)""",
            oid_ok, ma_don_ok, now, oid_bad, ma_don_bad,
        )
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don, ghi_chu, luc) VALUES ($1,-3,'ban',$2,'', $3)",
            ma, ma_don_ok, now - timedelta(minutes=4),
        )
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu, luc) VALUES ($1,10,'nhap','Nhập lô 01', $2)",
            ma, now - timedelta(minutes=3),
        )
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don, ghi_chu, luc) VALUES ($1,1,'hoan_hang',$2,'Hoàn 1 nguyên seal', $3)",
            ma, ma_don_ok, now - timedelta(minutes=2),
        )
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu, luc) VALUES ($1,-2,'kiem_ke','Vỡ 2 lọ khi kiểm', $2)",
            ma, now - timedelta(minutes=1),
        )
        return ma, ma_don_ok, ma_don_bad

    ma, ma_don_ok, ma_don_bad = _chay(app_that, seed())

    # 1. Sổ biến động dạng bảng trả đúng tồn sau theo chuỗi biến động
    r = qt.get("/api/kho/bien-dong/bang", params={"q": ma, "page_size": 20})
    assert r.status_code == 200, r.text
    items = [x for x in r.json()["items"] if x["ma"] == ma][:4]
    assert [(x["ly_do"], x["thay_doi"], x["ton_sau"]) for x in items] == [
        ("kiem_ke", -2, 20),
        ("hoan_hang", 1, 22),
        ("nhap", 10, 21),
        ("ban", -3, 11),
    ]
    assert items[0]["ghi_chu"] == "Vỡ 2 lọ khi kiểm"
    # Dữ liệu lịch sử thiếu audit event không suy đoán người thực hiện (rỗng), kể cả bán hàng (BUG-NK-02).
    assert items[0]["nguoi_thuc_hien"] == ""
    assert items[1]["nguoi_thuc_hien"] == ""
    assert items[2]["nguoi_thuc_hien"] == ""
    assert items[3]["nguoi_thuc_hien"] == ""
    assert all(x["do_tin_cay_ton"] == "khop" for x in items)

    # 2. Lọc theo chiều tăng / giảm và lý do
    tang = qt.get("/api/kho/bien-dong/bang", params={"q": ma, "chieu": "tang"}).json()
    assert all(x["thay_doi"] > 0 for x in tang["items"])
    giam = qt.get("/api/kho/bien-dong/bang", params={"q": ma, "chieu": "giam"}).json()
    assert all(x["thay_doi"] < 0 for x in giam["items"])
    loc_hoan = qt.get("/api/kho/bien-dong/bang", params={"q": ma_don_ok, "ly_do": "hoan_hang"}).json()
    assert loc_hoan["total"] == 1 and loc_hoan["items"][0]["ma_don"] == ma_don_ok

    # 3. Ngày lọc không hợp lệ trả 422
    assert qt.get("/api/kho/bien-dong/bang", params={"tu_ngay": "2026-02-30"}).status_code == 422
    assert qt.get("/api/kho/bien-dong/bang", params={"tu_ngay": "2026-12-05", "den_ngay": "2026-12-01"}).status_code == 422

    # 4. Nhập kho, nhập hàng hoàn và kiểm kê mới đều ghi đúng tên người thực hiện
    nhap_thuong = qt.post(f"/api/kho/{ma}/nhap", json={"loai": "nhap", "so_luong": 3, "ghi_chu": "Nhập lô mới UX"})
    assert nhap_thuong.status_code == 200
    nhap_hoan = qt.post(f"/api/kho/{ma}/nhap", json={"loai": "hoan_hang", "ma_don": ma_don_ok, "so_luong": 1, "ghi_chu": "Hoàn thêm 1 UX"})
    assert nhap_hoan.status_code == 200
    kk = qt.post(f"/api/kho/{ma}/kiem-ke", json={"so_luong_moi": 25, "ly_do": "Kiểm đếm bổ sung"})
    assert kk.status_code == 200

    for note in ("Nhập lô mới UX", "Hoàn thêm 1 UX", "Kiểm đếm bổ sung"):
        found = qt.get("/api/kho/bien-dong/bang", params={"q": note}).json()["items"]
        assert len(found) == 1
        assert found[0]["nguoi_thuc_hien"] == "sep"
    moi = qt.get("/api/kho/bien-dong/bang", params={"q": "Kiểm đếm bổ sung"}).json()["items"]
    assert moi[0]["ton_sau"] == 25

    # 5. Thông tin hàng hoàn (/hoan-hang-info) — đã hoàn 1 (seed) + 1 (nhập thêm) = 2/3 -> còn 1
    ok_info = qt.get(f"/api/kho/{ma}/hoan-hang-info", params={"ma_don": ma_don_ok})
    assert ok_info.status_code == 200
    assert ok_info.json()["du_dieu_kien"] is True
    assert ok_info.json()["da_ban"] == 3
    assert ok_info.json()["da_hoan"] == 2
    assert ok_info.json()["con_lai"] == 1

    bad_info = qt.get(f"/api/kho/{ma}/hoan-hang-info", params={"ma_don": ma_don_bad})
    assert bad_info.status_code == 200
    assert bad_info.json()["du_dieu_kien"] is False

    # 6. Quyền: tài khoản không có kho.doc bị 403; tài khoản chỉ có kho.doc không sửa được (403)
    from conftest import nguoi_thu
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.main import app

    try:
        app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi_thu("don.doc")
        assert qt.get("/api/kho/bien-dong/bang").status_code == 403
        assert qt.get(f"/api/kho/{ma}/hoan-hang-info", params={"ma_don": ma_don_ok}).status_code == 403

        app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi_thu("kho.doc")
        assert qt.get("/api/kho/bien-dong/bang").status_code == 200
        assert qt.post(f"/api/kho/{ma}/nhap", json={"so_luong": 1}).status_code == 403
        assert qt.post(f"/api/kho/{ma}/kiem-ke", json={"so_luong_moi": 25, "ly_do": "thử quyền"}).status_code == 403
    finally:
        app.dependency_overrides.pop(nguoi_da_dang_nhap, None)


def test_hop_dong_giao_dien_kho():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

    # 2 tab riêng trong Kho, tách biệt Nhật ký hệ thống (#events)
    assert 'data-ktab="ton_kho"' in html and 'data-ktab="bien_dong"' in html
    assert 'id="khoTabTon"' in html and 'id="khoTabBienDong"' in html
    assert 'id="khoSearch"' in html and 'id="khoCategory"' in html and 'id="khoStatus"' in html
    assert 'id="khoBdSearch"' in html and 'id="khoBdReason"' in html and 'id="khoBdDir"' in html

    # Giá bán rõ ràng, bỏ mặc định 50, bỏ cụm "số sống"/"tồn sống", có tooltip & preview
    assert "Giá trị tồn (giá bán)" in js
    assert "giá vốn" not in js.lower()
    kho_html = html[html.index('<section class="view" data-view="kho"'):html.index('<section class="view" data-view="congviec"')]
    assert "số sống" not in kho_html and "tồn sống" not in kho_html
    assert "tồn sống" not in js
    assert "sla-tip" in kho_html
    assert "Tồn dự kiến" in js and "Tồn hệ thống" in js and "Chênh lệch" in js
    assert 'value: "50"' not in js and "value: 50" not in js
    assert 'id="hoiDongBtn"' in html and 'id="hoiHuyBtn"' in html

    # Giới hạn <= 1000 dòng cho mỗi file JavaScript nguồn
    for p in sorted((ROOT / "dashboard" / "src").glob("*.js")):
        n = len(p.read_text(encoding="utf-8").splitlines())
        assert n <= 1000, f"{p.name} vượt 1000 dòng ({n})"
