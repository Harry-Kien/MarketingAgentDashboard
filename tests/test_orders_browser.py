"""Opt-in Chromium acceptance on kiemthu; no workers, external API or order mutations.

RUN_ORDER_BROWSER=1 DATABASE_URL=.../kiemthu pytest tests/test_orders_browser.py -q
Creates only uniquely named local UI fixtures; removes exactly those rows afterwards.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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

pytestmark = pytest.mark.skipif(os.getenv("RUN_ORDER_BROWSER") != "1", reason="Opt-in real browser / kiemthu")


def test_orders_desktop_mobile(monkeypatch):
    import uvicorn
    from playwright.sync_api import sync_playwright, expect
    from agent import db
    from agent.config import settings
    from agent.core.xac_thuc import bam_token
    from agent.api.routes import TEN_COOKIE
    from agent.main import app

    dsn = os.environ["DATABASE_URL"]
    assert urlsplit(dsn).path == "/kiemthu", "Never run UI fixtures on production"
    marker = "UX-ORDER-" + uuid.uuid4().hex[:8]
    uid, token = uuid.uuid4(), uuid.uuid4().hex + uuid.uuid4().hex
    ids = [uuid.uuid4() for _ in range(23)]
    shots = Path("docs/uat_evidence_orders")
    shots.mkdir(exist_ok=True)

    async def setup():
        c = await asyncpg.connect(dsn)
        tx = c.transaction()
        await tx.start()
        try:
            protected = await c.fetchval("SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'")
            await c.execute("INSERT INTO nguoi_dung (id,ten_dang_nhap,mat_khau_bam,ho_ten,vai_tro) VALUES ($1,$2,'x','UI Test','quan_tri')", uid, marker)
            await c.execute("INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id,vai_tro_id) SELECT $1,id FROM vai_tro WHERE ten='Quản trị'", uid)
            await c.execute("INSERT INTO phien (token,nguoi_dung_id,het_han) VALUES ($1,$2,now()+interval '1 hour')", bam_token(token), uid)
            for i, oid in enumerate(ids):
                await c.execute(
                    """INSERT INTO orders (id,ma_don,channel,khach_ten,khach_sdt,khach_dia_chi,items,tong_tien,
                    trang_thai,erp_ma_don,ma_van_don,don_vi_van_chuyen,trang_thai_giao_hang,van_don_da_lay_hang,
                    erp_van_chuyen_trang_thai,created_at)
                    VALUES ($1,$2,'webchat','Khách kiểm thử UX','0900000000','Địa chỉ kiểm thử',$3::jsonb,200000,
                    'da_chot','SAL-' || $2,$2,'ghn','delivery_failed',true,'dead',now()+$4*interval '1 second')""",
                    oid, f"{marker}-{i:02d}", json.dumps([{"ma":"UX-SP","ten":"Sản phẩm kiểm thử","so_luong":2,"don_gia":100000,"thanh_tien":200000}]), i,
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
            await c.execute("DELETE FROM orders WHERE id=ANY($1::uuid[])", ids)
            await c.execute("DELETE FROM nguoi_dung WHERE id=$1", uid)
            await c.close()

    @asynccontextmanager
    async def readonly_lifespan(_):
        async def codec(c):
            await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=4, init=codec,
                                        server_settings={"default_transaction_read_only":"on"})
        db._pool = pool
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    protected = asyncio.run(setup())
    monkeypatch.setattr(settings, "database_url", dsn)
    monkeypatch.setattr(app.router, "lifespan_context", readonly_lifespan)
    # Bind a private ephemeral socket; never restart the operating application.
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
            context = browser.new_context(viewport={"width":1440,"height":1000})
            context.add_cookies([{"name":TEN_COOKIE,"value":token,"url":base}])
            page = context.new_page()
            failures = []
            page.on("pageerror", lambda e: failures.append(str(e)))
            # Refuse writes and external requests even if a UI handler regresses.
            def guard(route):
                if not route.request.url.startswith(base + "/") or route.request.method not in ("GET", "HEAD"):
                    route.abort()
                else:
                    route.continue_()
            page.route("**/*", guard)
            page.goto(base)
            page.locator('button[data-view="donhang"]').click()
            expect(page.locator("#orders")).to_have_attribute("aria-busy", "false")
            page.locator("#orderSearch").fill(marker)
            expect(page.locator("#orderSummary")).to_have_text("23 đơn khớp bộ lọc")
            expect(page.locator(".dh-table")).to_be_visible()
            expect(page.locator("#orders .dh-tr")).to_have_count(20)
            assert page.locator("#orderLayout").evaluate("e=>getComputedStyle(e).display") == "grid"
            assert page.locator(".dh-khung").evaluate("e=>getComputedStyle(e).overflowY") == "visible"
            assert page.locator("#orderToolbar").evaluate("e=>getComputedStyle(e).position") == "sticky"
            assert page.locator("#orderKpi .readout__cell").count() == 4
            assert page.locator("#orderToolbar").inner_text().find("Từ ngày") != -1
            assert page.locator("#orderToolbar").inner_text().find("Đến ngày") != -1
            assert page.locator(".dh-table .dh-tr [data-odathu]").first.inner_text().strip() == "Xác nhận đã nhận tiền"
            assert page.evaluate("""() => {
                const w = document.querySelector('.dh-table-wrap').getBoundingClientRect();
                const g = document.querySelector('.dh-table .dh-tr .dh-act-grp').getBoundingClientRect();
                return g.right <= w.right + 1;
            }""")
            page.screenshot(path=str(shots / "desktop-list.png"), full_page=True)
            # Verify the toolbar and table header stay pinned while the document actually scrolls.
            sticky_top = page.locator("#orderToolbar").evaluate("e=>parseFloat(getComputedStyle(e).top)")
            page.evaluate("window.scrollTo(0, 500)")
            page.wait_for_function("window.scrollY >= 500")
            expect(page.locator("#orderToolbar")).to_be_in_viewport()
            toolbar_box = page.locator("#orderToolbar").bounding_box()
            assert abs(toolbar_box["y"] - sticky_top) <= 2
            th_pos = page.locator(".dh-table thead th").first.evaluate("e=>getComputedStyle(e).position")
            th_box = page.locator(".dh-table thead th").first.bounding_box()
            assert th_pos == "sticky"
            assert abs(th_box["y"] - (toolbar_box["y"] + toolbar_box["height"])) <= 4
            page.evaluate("window.scrollTo(0, 700)")
            page.wait_for_function("window.scrollY >= 700")
            assert abs(page.locator("#orderToolbar").bounding_box()["y"] - sticky_top) <= 2
            page.screenshot(path=str(shots / "desktop-sticky.png"))
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")
            page.locator('[data-opage="2"]').click()
            expect(page.locator("#orders .dh-tr")).to_have_count(3)
            page.locator("#orderPay").select_option("da_thu_du")
            expect(page.locator("#orders")).to_contain_text("Không có đơn hàng")
            expect(page.locator("#orderPager")).to_be_hidden()
            page.locator("#orderPay").select_option("all")
            page.locator("#orderShip").select_option("delivery_failed")
            expect(page.locator("#orderSummary")).to_have_text("23 đơn khớp bộ lọc")
            page.screenshot(path=str(shots / "desktop-filters.png"), full_page=True)
            page.locator("#orderFrom").fill("2099-12-31")
            page.locator("#orderTo").fill("2099-01-01")
            expect(page.locator("#orders [role=alert]")).to_contain_text("Từ ngày")
            page.locator("#orderFrom").fill("")
            page.locator("#orderTo").fill("")
            expect(page.locator("#orderSummary")).to_have_text("23 đơn khớp bộ lọc")
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")
            page.locator(".dh-table .dh-code").first.click()
            expect(page.locator("#orderDetailTitle")).to_be_visible()
            expect(page.locator("#orderDetail .dh-alert-bar")).to_be_visible()
            assert page.locator("#orderDetail .dh-alert").count() == 0
            for tab in ("tong_quan", "van_chuyen", "erp"):
                page.locator(f'[data-otab="{tab}"]').click()
                expect(page.locator(f'[data-otab="{tab}"]')).to_have_attribute("aria-selected", "true")
                page.screenshot(path=str(shots / f"desktop-{tab}.png"), full_page=True)
            box = page.locator("#orderDetail").bounding_box()
            listing = page.locator(".dh-khung").bounding_box()
            assert box["x"] > listing["x"] and box["y"] < listing["y"] + 100
            page.keyboard.press("Escape")
            expect(page.locator("#orderDetail")).to_be_hidden()
            page.set_viewport_size({"width":390,"height":844})
            expect(page.locator("#orderDetail")).to_be_hidden()
            expect(page.locator(".dh-table-wrap")).to_be_hidden()
            expect(page.locator(".dh-cards")).to_be_visible()
            expect(page.locator("#orders .dh-card")).to_have_count(20)
            assert page.evaluate("""() => {
                const c = document.querySelector('#orders .dh-card');
                if (!c) return false;
                c.scrollIntoView({block: 'center'});
                const r = c.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                return Boolean(hit && hit.closest('.dh-card'));
            }""")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function("window.scrollY === 0")
            page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            page.screenshot(path=str(shots / "mobile-list.png"), full_page=True)
            # Verify mobile scrolling actually reveals later cards without clipping or blank screen.
            page.evaluate("window.scrollTo(0, 1200)")
            page.wait_for_function("window.scrollY >= 1000")
            assert page.evaluate("""() => {
                const cards = [...document.querySelectorAll('#orders .dh-card')];
                const vis = cards.find(c => { const r = c.getBoundingClientRect(); return r.top >= 60 && r.bottom <= 844; });
                if (!vis) return false;
                const r = vis.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                return Boolean(hit && hit.closest('.dh-card'));
            }""")
            page.screenshot(path=str(shots / "mobile-list-scrolled.png"))
            page.locator(".dh-cards .dh-code").first.click()
            expect(page.locator("#orderDetailTitle")).to_be_visible()
            assert page.locator("#orderDetail").evaluate("e=>getComputedStyle(e).position") == "fixed"
            for tab in ("tong_quan", "van_chuyen", "erp"):
                page.locator(f'[data-otab="{tab}"]').click()
                page.screenshot(path=str(shots / f"mobile-{tab}.png"))
            assert page.locator("#orderDetail").evaluate("e=>e.scrollWidth <= e.clientWidth+1")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            # Controlled response ordering in the browser only; API/DB acceptance above is real.
            races = page.evaluate("""async () => {
                const original = api, detail = dhState.detail;
                const checks = [];
                try {
                    const permissions = state.toiQuyen;
                    state.toiQuyen = new Set(['don.doc']);
                    checks.push(!dhVeNutNhom(detail, true).includes('data-odathu') && !dhVeNutNhom(detail, true).includes('data-ocancel'));
                    state.toiQuyen = permissions;
                    let pending = [];
                    api = () => new Promise(resolve => pending.push(resolve));
                    const a = dhTaiChiTiet('older', true), b = dhTaiChiTiet('newer', true);
                    pending[1]({...detail, id:'newer', ma_don:'NEWER'}); await b;
                    pending[0]({...detail, id:'older', ma_don:'OLDER'}); await a;
                    checks.push(dhState.openId === 'newer');
                    pending = [];
                    const closing = dhTaiChiTiet('closing', true);
                    dhDongNgan(); pending[0]({...detail, id:'closing'}); await closing;
                    checks.push(document.querySelector('#orderDetail').hidden);
                    pending = [];
                    const first = loadOrders(), second = loadOrders();
                    pending[1]({items:[], total:2, page:1, total_pages:1}); await second;
                    pending[0]({items:[], total:1, page:1, total_pages:1}); await first;
                    checks.push(document.querySelector('#orderSummary').textContent === '2 đơn khớp bộ lọc');
                    api = async () => { throw new Error('Lỗi kiểm thử kết nối'); };
                    await loadOrders();
                    checks.push(!!document.querySelector('#orders [role=alert]'));
                    checks.push(document.querySelector('#orders').getAttribute('aria-busy') === 'false');
                } finally { api = original; }
                return checks;
            }""")
            assert races == [True] * 6
            assert not failures, failures
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        asyncio.run(cleanup(protected))
