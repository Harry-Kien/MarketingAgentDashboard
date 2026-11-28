"""Opt-in Chromium acceptance cho module Kho trên kiemthu; không đụng production hay TEST-17-01.

RUN_KHO_BROWSER=1 DATABASE_URL=postgresql://agent:agent@127.0.0.1:5433/kiemthu pytest tests/test_kho_browser.py -v
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit
import uuid

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(os.getenv("RUN_KHO_BROWSER") != "1", reason="Opt-in real browser / kiemthu")


def test_kho_desktop_mobile(monkeypatch):
    import uvicorn
    from playwright.sync_api import expect, sync_playwright
    from agent import db
    from agent.api.routes import TEN_COOKIE
    from agent.config import settings
    from agent.core.xac_thuc import bam_token
    from agent.main import app

    dsn = os.environ["DATABASE_URL"]
    assert urlsplit(dsn).path == "/kiemthu", "Never run UI fixtures on production"
    marker = "UXKHO-" + uuid.uuid4().hex[:6]
    uid, token = uuid.uuid4(), uuid.uuid4().hex + uuid.uuid4().hex
    skus = [f"{marker}-{i:02d}" for i in range(12)]
    order_id = uuid.uuid4()
    ma_don = f"{marker}-DON-RET"
    shots = Path("docs/uat_evidence_kho")
    shots.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc)

    async def setup():
        c = await asyncpg.connect(dsn)
        tx = c.transaction()
        await tx.start()
        try:
            protected = await c.fetchval("SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'")
            await c.execute("INSERT INTO nguoi_dung (id,ten_dang_nhap,mat_khau_bam,ho_ten,vai_tro) VALUES ($1,$2,'x','Kho UI Test','quan_tri')", uid, marker)
            await c.execute("INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id,vai_tro_id) SELECT $1,id FROM vai_tro WHERE ten='Quản trị'", uid)
            await c.execute("INSERT INTO phien (token,nguoi_dung_id,het_han) VALUES ($1,$2,now()+interval '1 hour')", bam_token(token), uid)
            # Tạo 12 mã tạm (0 hết hàng, 1..3 sắp hết, còn lại >= 25) -> tổng trên kiemthu >= 25 mã để có phân trang
            for idx, sku in enumerate(skus):
                qty = 0 if idx == 0 else (5 if idx <= 3 else 25 + idx)
                await c.execute("INSERT INTO ton_kho (ma, so_luong) VALUES ($1, $2)", sku, qty)
            # Tạo 1 đơn hàng hoàn (returned) bán 3 / đã hoàn 1 (còn được nhập 2) cho sku đầu đủ tồn (skus[4])
            await c.execute(
                """INSERT INTO orders (id,ma_don,channel,khach_ten,khach_sdt,khach_dia_chi,items,tong_tien,
                                       trang_thai,trang_thai_giao_hang,van_don_da_lay_hang,created_at)
                   VALUES ($1,$2,'webchat','Khách hoàn Kho UX','0901010101','123 Test',$3::jsonb,300000,
                           'da_chot','returned',true,$4)""",
                order_id, ma_don,
                json.dumps([{"ma": skus[4], "ten": f"Sản phẩm {skus[4]}", "so_luong": 3, "don_gia": 100000, "thanh_tien": 300000}]),
                now - timedelta(minutes=30),
            )
            await c.execute(
                "INSERT INTO kho_bien_dong (ma,thay_doi,ly_do,ma_don,ghi_chu,luc) VALUES ($1,-3,'ban',$2,'',$3)",
                skus[4], ma_don, now - timedelta(minutes=25),
            )
            await c.execute(
                "INSERT INTO kho_bien_dong (ma,thay_doi,ly_do,ma_don,ghi_chu,luc) VALUES ($1,1,'hoan_hang',$2,'Kiểm hàng hoàn 1/3',$3)",
                skus[4], ma_don, now - timedelta(minutes=20),
            )
            # Tạo 19 biến động nhất quán với tồn kho (>= 25 trên skus[4..11]) để tồn sau luôn >= 0 và có 2 trang
            for j in range(19):
                s = skus[4 + (j % 8)]
                await c.execute(
                    "INSERT INTO kho_bien_dong (ma,thay_doi,ly_do,ghi_chu,luc) VALUES ($1,$2,$3,$4,$5)",
                    s, 2 if j % 2 == 0 else -1, "nhap" if j % 2 == 0 else "kiem_ke",
                    f"{marker} ghi chú dòng {j:02d}", now - timedelta(minutes=19 - j),
                )
            await tx.commit()
            return protected
        except BaseException:
            await tx.rollback()
            raise
        finally:
            await c.close()

    async def cleanup(protected):
        c = await asyncpg.connect(dsn)
        try:
            after = await c.fetchval("SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'")
            assert after == protected, "TEST-17-01 evidence changed"
        finally:
            await c.execute("DELETE FROM kho_bien_dong WHERE ma=ANY($1::text[]) OR ma_don=$2", skus, ma_don)
            await c.execute("DELETE FROM ton_kho WHERE ma=ANY($1::text[])", skus)
            await c.execute("DELETE FROM orders WHERE id=$1", order_id)
            await c.execute("DELETE FROM events WHERE detail->>'ma'=ANY($1::text[]) OR detail->>'ma_don'=$2", skus, ma_don)
            await c.execute("DELETE FROM phien WHERE nguoi_dung_id=$1", uid)
            await c.execute("DELETE FROM nguoi_dung_vai_tro WHERE nguoi_dung_id=$1", uid)
            await c.execute("DELETE FROM nguoi_dung WHERE id=$1", uid)
            await c.close()

    @asynccontextmanager
    async def test_lifespan(_):
        async def codec(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, init=codec)
        db._pool = pool
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    protected = asyncio.run(setup())
    monkeypatch.setattr(settings, "database_url", dsn)
    monkeypatch.setattr(app.router, "lifespan_context", test_lifespan)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as p:
            browser = p.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 1000})
            context.add_cookies([{"name": TEN_COOKIE, "value": token, "url": base}])
            page = context.new_page()
            failures = []
            page.on("pageerror", lambda e: failures.append(str(e)))
            # Chặn mọi request ra ngoài localhost (ERP / GHN / GHTK / internet)
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base + "/") else route.abort())

            page.goto(base)
            page.locator('button[data-view="kho"]').click()
            expect(page.locator(".kho-table")).to_be_visible()
            expect(page.locator("#khoCards .readout__cell")).to_have_count(4)
            assert "Giá trị tồn (giá bán)" in page.locator("#khoCards").inner_text()
            assert "tồn sống" not in page.locator("#khoCards").inner_text()
            assert "số sống" not in page.locator("#khoTabTon").inner_text()
            page.locator("#khoTabTon [data-sla-tip]").click()
            expect(page.locator("#khoTabTon .sla-tip")).to_contain_text("Nhập hàng hoàn")
            page.keyboard.press("Escape")
            assert "(" in page.locator('#khofilter [data-kcnt="all"]').inner_text()
            assert page.locator(".kho-table thead th").count() == 6
            page.screenshot(path=str(shots / "desktop-kho-ton.png"), full_page=True)

            # Kiểm tra sticky toolbar & sticky header bảng trên desktop
            sticky_top = page.locator("#khoToolbar").evaluate("e=>parseFloat(getComputedStyle(e).top)")
            page.evaluate("window.scrollTo(0, 420)")
            page.wait_for_function("window.scrollY >= 400")
            tb_box = page.locator("#khoToolbar").bounding_box()
            th_box = page.locator(".kho-table thead th").first.bounding_box()
            assert abs(tb_box["y"] - sticky_top) <= 2
            assert page.locator(".kho-table thead th").first.evaluate("e=>getComputedStyle(e).position") == "sticky"
            assert abs(th_box["y"] - (tb_box["y"] + tb_box["height"])) <= 4
            page.screenshot(path=str(shots / "desktop-kho-sticky.png"))
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")

            # Tìm kiếm + lọc theo danh mục & chip
            page.locator("#khoSearch").fill(skus[4])
            expect(page.locator(".kho-table tbody .dh-tr")).to_have_count(1)
            expect(page.locator(".kho-table tbody .kho-sp__info .kho-sku")).to_contain_text(skus[4])

            # UX-KHO-04: Modal Nhập kho -> nút X góc phải, Huỷ ngang hàng Xác nhận, ẩn ← Quay lại
            page.locator(f'.kho-table [data-knhap="{skus[4]}"]').click()
            expect(page.locator("#congHoi")).not_to_have_class("is-off")
            expect(page.locator("#hoiDongBtn")).to_be_visible()
            expect(page.locator("#hoiHuyBtn")).to_be_visible()
            expect(page.locator("#hoiHuy")).to_be_hidden()
            huy_box = page.locator("#hoiHuyBtn").bounding_box()
            ok_box = page.locator("#hoiNut").bounding_box()
            assert abs(huy_box["y"] - ok_box["y"]) <= 3 and huy_box["x"] < ok_box["x"]
            assert page.locator('#hoiform [name="so_luong"]').input_value() == ""
            page.locator('#hoiform [name="loai"]').select_option("hoan_hang")
            page.locator('#hoiform [name="ma_don"]').fill(ma_don)
            expect(page.locator(".kho-hoan-box")).to_contain_text("Còn được nhập")
            expect(page.locator(".kho-hoan-box")).to_contain_text("2")
            page.locator('#hoiform [name="so_luong"]').fill("5")
            expect(page.locator(".kho-hoan-box__loi")).to_contain_text("vượt quá")
            assert page.locator("#hoiNut").is_disabled()
            page.locator('#hoiform [name="so_luong"]').fill("2")
            expect(page.locator("[data-kdu-kien]")).to_have_text("31")
            assert not page.locator("#hoiNut").is_disabled()
            page.screenshot(path=str(shots / "desktop-kho-modal-nhap.png"))
            page.locator("#hoiDongBtn").click()
            expect(page.locator("#congHoi")).to_have_class("cong cong--hop is-off")

            # UX-KHO-05: Modal Kiểm kê -> tính chênh lệch live + nút Huỷ ngang hàng Ghi kiểm kê
            page.locator(f'.kho-table [data-kkiemke="{skus[4]}"]').click()
            expect(page.locator("#hoiTen")).to_contain_text("Kiểm kê")
            expect(page.locator("#hoiDongBtn")).to_be_visible()
            expect(page.locator("#hoiHuyBtn")).to_be_visible()
            page.locator('#hoiform [name="so_luong_moi"]').fill("33")
            expect(page.locator("[data-klech]")).to_have_text("+4")
            page.screenshot(path=str(shots / "desktop-kho-modal-kiemke.png"))
            page.locator("#hoiHuyBtn").click()

            # Xác nhận hoiHop() ở các module khác vẫn giữ ← Quay lại và ẩn #hoiDongBtn / #hoiHuyBtn
            other_ok = page.evaluate("""async () => {
                const p = hoiHop({ tieu_de: 'Khác Kho', nut: 'Xác nhận' });
                const ok = document.getElementById('hoiDongBtn').hidden
                    && document.getElementById('hoiHuyBtn').hidden
                    && !document.getElementById('hoiHuy').closest('.cong__note').hidden;
                hoiDong(null);
                await p;
                return ok;
            }""")
            assert other_ok is True

            page.locator("#khoReset").click()

            # UX-KHO-06: Tab Sổ biến động kho (lọc, phân trang, tồn sau, người thực hiện, tách Nhật ký)
            page.locator('[data-ktab="bien_dong"]').click()
            expect(page.locator("#khoTabBienDong")).to_be_visible()
            expect(page.locator(".kho-bd-table")).to_be_visible()
            page.locator("#khoBdSearch").fill(marker)
            expect(page.locator("#khoSo .dh-tr")).to_have_count(20)
            expect(page.locator("#khoBdPager")).to_be_visible()
            page.screenshot(path=str(shots / "desktop-kho-bien_dong.png"), full_page=True)
            page.locator('[data-kbdpage="2"]').click()
            expect(page.locator("#khoSo .dh-tr")).to_have_count(1)
            page.locator("#khoBdReset").click()

            # UX-KHO-07: Mobile responsive (390x844): 3 thẻ nhỏ trên hàng 1, Giá trị tồn 1 hàng riêng
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator('[data-ktab="ton_kho"]').click()
            expect(page.locator("#khoTabTon .dh-table-wrap")).to_be_hidden()
            expect(page.locator("#khoTabTon .dh-cards")).to_be_visible()
            kpi_boxes = page.evaluate("""() => [...document.querySelectorAll('#khoCards .readout__cell')]
                .map(e => { const r = e.getBoundingClientRect(); return { y: Math.round(r.y), w: Math.round(r.width) }; })""")
            assert len(kpi_boxes) == 4
            assert abs(kpi_boxes[0]["y"] - kpi_boxes[1]["y"]) <= 2 and abs(kpi_boxes[1]["y"] - kpi_boxes[2]["y"]) <= 2
            assert kpi_boxes[3]["y"] > kpi_boxes[0]["y"] and kpi_boxes[3]["w"] > kpi_boxes[0]["w"] * 2
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")
            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            page.screenshot(path=str(shots / "mobile-kho-ton.png"), full_page=True)

            page.evaluate("window.scrollTo(0, 700)")
            page.wait_for_function("window.scrollY >= 500")
            assert page.evaluate("""() => {
                const cards = [...document.querySelectorAll('#khoRows .dh-card')];
                const vis = cards.find(c => { const r = c.getBoundingClientRect(); return r.top >= 60 && r.bottom <= 844; });
                if (!vis) return false;
                const r = vis.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                return Boolean(hit && hit.closest('.dh-card'));
            }""")
            page.screenshot(path=str(shots / "mobile-kho-ton-scrolled.png"))

            # Mobile modal
            page.locator("#khoRows .dh-card [data-kkiemke]").first.click()
            expect(page.locator("#hoiTen")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(shots / "mobile-kho-modal.png"))
            page.locator("#hoiHuyBtn").click()

            # Mobile Sổ biến động kho
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")
            page.locator('[data-ktab="bien_dong"]').click()
            expect(page.locator("#khoSo .dh-cards")).to_be_visible()
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.screenshot(path=str(shots / "mobile-kho-bien_dong.png"))

            assert not failures, f"JS errors: {failures}"
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        asyncio.run(cleanup(protected))
