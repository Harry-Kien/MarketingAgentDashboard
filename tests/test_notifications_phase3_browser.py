"""Playwright Chromium E2E trên kiemthu cho popup Chuông Thông báo (Giai đoạn 3).

RUN_NOTIF_BROWSER=1 DATABASE_URL=postgresql://agent:agent@127.0.0.1:5433/kiemthu .venv/bin/python -m pytest tests/test_notifications_phase3_browser.py -v --tb=short
"""
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import socket
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_NOTIF_BROWSER") != "1",
    reason="Opt-in kiemthu browser",
)


def test_notifications_phase3_desktop_and_mobile(monkeypatch):
    import uvicorn
    from playwright.sync_api import sync_playwright
    from agent import db
    from agent.api.routes import TEN_COOKIE
    from agent.config import settings
    from agent.core.xac_thuc import bam_token
    from agent.main import app
    from agent.migrations.runner import apply_all

    dsn = os.environ["DATABASE_URL"]
    assert urlsplit(dsn).path == "/kiemthu"

    admin_id = uuid4()
    limited_id = uuid4()
    acc_id = uuid4()
    acc_other_id = uuid4()
    contact_id = uuid4()
    cp_id = uuid4()
    conv_id = uuid4()
    conv_other_id = uuid4()
    order_id = uuid4()
    job_id = uuid4()

    token = uuid4().hex + uuid4().hex
    low_token = uuid4().hex + uuid4().hex
    marker = "TB3-" + uuid4().hex[:6]
    ma_don_test = f"DH-{marker}"
    shots = Path("docs/uat_evidence_notifications_phase3")
    shots.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(_):
        c = await asyncpg.connect(dsn)
        await c.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        await apply_all(c)
        protected = await c.fetchval(
            "SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'"
        )
        tx = c.transaction()
        await tx.start()
        lock = asyncio.Lock()

        class TransactionPool:
            def __getattr__(self, name):
                if name not in {"fetch", "fetchrow", "fetchval", "execute", "executemany"}:
                    raise AttributeError(name)

                async def call(*args, **kwargs):
                    async with lock:
                        return await getattr(c, name)(*args, **kwargs)

                return call

            @asynccontextmanager
            async def acquire(self):
                async with lock:
                    yield c

        db._pool = TransactionPool()
        try:
            for uid, tok, suffix in ((admin_id, token, "qt"), (limited_id, low_token, "nv")):
                await c.execute(
                    "INSERT INTO nguoi_dung(id, ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
                    "VALUES($1, $2, 'x', $3, 'nhan_vien')",
                    uid, marker + suffix, "Kiểm thử " + suffix.upper(),
                )
                await c.execute(
                    "INSERT INTO phien(token, nguoi_dung_id, het_han) VALUES($1, $2, now() + interval '1 hour')",
                    bam_token(tok), uid,
                )
            await c.execute(
                "INSERT INTO nguoi_dung_vai_tro(nguoi_dung_id, vai_tro_id) "
                "SELECT $1, id FROM vai_tro WHERE ten = 'Quản trị'",
                admin_id,
            )
            await c.execute(
                "INSERT INTO nguoi_dung_vai_tro(nguoi_dung_id, vai_tro_id) "
                "SELECT $1, id FROM vai_tro WHERE ten = 'Nhân viên'",
                limited_id,
            )
            await c.execute(
                "INSERT INTO channel_accounts(id, channel, display_name, external_account_id, status) "
                "VALUES($1, 'webchat', 'Web UAT TB3', $2, 'active')",
                acc_id, marker + "-1",
            )
            await c.execute(
                "INSERT INTO channel_accounts(id, channel, display_name, external_account_id, status) "
                "VALUES($1, 'zalo_personal', 'Zalo Ngoài Phạm Vi', $2, 'reauth_required')",
                acc_other_id, marker + "-2",
            )
            await c.execute("INSERT INTO contacts(id, display_name) VALUES($1, 'Chị Lan UAT')", contact_id)
            await c.execute(
                "INSERT INTO contact_points(id, contact_id, channel_account_id, external_user_id) "
                "VALUES($1, $2, $3, $4)",
                cp_id, contact_id, acc_id, marker + "-u1",
            )
            await c.execute(
                "INSERT INTO conversations(id, account_id, channel, external_id, customer_ref, customer_name, "
                "contact_id, contact_point_id, mode, status, state) "
                "VALUES($1, $2, 'webchat', $3, $3, 'Chị Lan UAT', $4, $5, 'human', 'escalated', 'open')",
                conv_id, acc_id, marker + "-c1", contact_id, cp_id,
            )
            # Hội thoại đã giải quyết để tạo thông báo ở trạng thái Đã xử lý
            cp2_id = uuid4()
            await c.execute(
                "INSERT INTO contact_points(id, contact_id, channel_account_id, external_user_id) "
                "VALUES($1, $2, $3, $4)",
                cp2_id, contact_id, acc_other_id, marker + "-u2",
            )
            await c.execute(
                "INSERT INTO conversations(id, account_id, channel, external_id, customer_ref, customer_name, "
                "contact_id, contact_point_id, mode, status, state, resolved_at) "
                "VALUES($1, $2, 'zalo_personal', $3, $3, 'Khách Đã Xong', $4, $5, 'human', 'resolved', 'resolved', now())",
                conv_other_id, acc_other_id, marker + "-c2", contact_id, cp2_id,
            )
            await c.execute(
                "INSERT INTO orders(id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai, conversation_id) "
                "VALUES($1, $2, 'webchat', 'Chị Lan UAT', '0909888777', '123 Lê Lợi, Q1', '[]', 450000, 'cho_duyet', $3)",
                order_id, ma_don_test, conv_id,
            )
            await c.execute(
                "INSERT INTO cong_viec(id, tieu_de, mo_ta, nguon, uu_tien, trang_thai, nguoi_nhan, conversation_id) "
                "VALUES($1, 'Gọi xác nhận đơn UAT', 'Xác nhận địa chỉ giao', 'don_hang', 'cao', 'moi', $2, $3)",
                job_id, admin_id, conv_id,
            )

            # Seed 22 thông báo cho Quản trị để kiểm tra phân trang "Xem thêm", các bộ lọc & điều hướng
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, order_id, tao_luc) "
                "VALUES($1, 'can_duyet', $2, 'AI đã lên đơn vượt ngưỡng tự chốt — cần người duyệt.', $3, $4, now())",
                admin_id, f"Đơn {ma_don_test} chờ duyệt", conv_id, order_id,
            )
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, tao_luc) "
                "VALUES($1, 'ai_chuyen_giao', 'AI chuyển hội thoại cho nhân viên', 'Khách hỏi thành phần sản phẩm.', $2, now() - interval '1 minute')",
                admin_id, conv_id,
            )
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, cong_viec_id, tao_luc) "
                "VALUES($1, 'duoc_giao_viec', 'Bạn được giao một việc', 'Gọi xác nhận đơn UAT', $2, now() - interval '2 minute')",
                admin_id, job_id,
            )
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, contact_id, da_doc_luc, tao_luc) "
                "VALUES($1, 'duoc_giao_khach', 'Bạn được giao phụ trách khách Chị Lan UAT', 'Phân công chăm sóc VIP', $2, now(), now() - interval '3 minute')",
                admin_id, contact_id,
            )
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, da_doc_luc, tao_luc) "
                "VALUES($1, 'ai_chuyen_giao', 'AI chuyển hội thoại (đã xử lý)', 'Ca đã hoàn tất giải quyết.', $2, now(), now() - interval '4 minute')",
                admin_id, conv_other_id,
            )
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, account_id, tao_luc) "
                "VALUES($1, 'kenh_can_xac_thuc', 'Kênh Zalo cá nhân cần xác thực lại', 'Mất phiên đăng nhập — cần quét QR lại.', $2, now() - interval '5 minute')",
                admin_id, acc_other_id,
            )
            for idx in range(18):
                await c.execute(
                    "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, da_doc_luc, tao_luc) "
                    "VALUES($1, 'ai_chuyen_giao', $2, 'Lịch sử chuyển giao cũ đã xong.', $3, now(), now() - make_interval(mins => $4))",
                    admin_id, f"Lịch sử ca #{idx + 1}", conv_other_id, 10 + idx,
                )

            # Seed cho nhân viên thường ngoài phạm vi acc_other_id để kiểm RBAC
            await c.execute(
                "INSERT INTO thong_bao(nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, tao_luc) "
                "VALUES($1, 'ai_chuyen_giao', 'AI chuyển hội thoại kênh ngoài', 'Cần xử lý', $2, now())",
                limited_id, conv_other_id,
            )
            yield
        finally:
            await tx.rollback()
            assert protected == await c.fetchval(
                "SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'"
            )
            db._pool = None
            await c.close()

    monkeypatch.setattr(settings, "database_url", dsn)
    monkeypatch.setattr(app.router, "lifespan_context", lifespan)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(100):
        try:
            s = socket.create_connection(("127.0.0.1", sock.getsockname()[1]), timeout=0.2)
            s.close()
            break
        except OSError:
            time.sleep(0.05)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_cookies([{
                "name": TEN_COOKIE, "value": token, "domain": "127.0.0.1",
                "path": "/", "httpOnly": True, "sameSite": "Lax",
            }])
            page = ctx.new_page()
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.on("response", lambda r: errs.append(f"{r.status} {r.url}") if r.status >= 500 else None)

            page.goto(base, wait_until="domcontentloaded")
            page.wait_for_selector("#chuongNut")
            page.wait_for_function("() => Number(document.querySelector('#chuongSo')?.textContent || '0') === 4")

            # 1) Mở popup chuông trên desktop
            page.click("#chuongNut")
            page.wait_for_selector("#chuongKhung:not([hidden])")
            page.wait_for_selector("#chuongDs .chuong__dong")
            items_count = page.locator("#chuongDs .chuong__dong").count()
            assert items_count == 20
            assert page.locator("#chuongThem").is_visible()
            page.screenshot(path=str(shots / "desktop-bell-open.png"))

            # Bấm Xem thêm để tải nốt 4 dòng còn lại
            page.click("#chuongThem")
            page.wait_for_function("() => document.querySelectorAll('#chuongDs .chuong__dong').length === 24")

            # Lọc "Cần xử lý"
            page.click('[data-chuong-loc="can_xu_ly"]')
            page.wait_for_function("() => document.querySelectorAll('#chuongDs .chuong__dong').length === 4")
            page.screenshot(path=str(shots / "desktop-bell-can-xu-ly.png"))

            # 2) BUG-TB-02: Bấm thông báo đơn hàng -> chuyển sang màn Đơn hàng và mở thẳng side panel chi tiết đơn
            page.locator("#chuongDs .chuong__dong", has_text=ma_don_test).click()
            page.wait_for_selector('[data-view="donhang"].view.is-active')
            page.wait_for_selector("#orderDetail:not([hidden])")
            page.wait_for_function(
                f"() => (document.querySelector('#orderDetail')?.textContent || '').includes({json.dumps(ma_don_test)})"
            )
            page.screenshot(path=str(shots / "desktop-bell-order-panel.png"))

            # 3) Bấm thông báo hội thoại -> mở thẳng hội thoại
            page.click("#chuongNut")
            page.wait_for_selector("#chuongKhung:not([hidden])")
            page.click('[data-chuong-loc=""]')
            page.wait_for_selector("#chuongDs .chuong__dong")
            page.locator("#chuongDs .chuong__dong", has_text="Khách hỏi thành phần sản phẩm").click()
            page.wait_for_selector('[data-view="hoithoai"].view.is-active')
            page.wait_for_function(
                "() => (document.querySelector('#convdetail')?.textContent || '').includes('Chị Lan UAT')"
            )

            # 4) Bấm thông báo công việc -> mở thẳng chi tiết công việc
            page.click("#chuongNut")
            page.wait_for_selector("#chuongKhung:not([hidden])")
            page.locator("#chuongDs .chuong__dong", has_text="Gọi xác nhận đơn UAT").click()
            page.wait_for_selector('[data-tab="cv-danh-sach"].is-active, #cvxCt:not([hidden])')
            page.wait_for_function(
                "() => (document.querySelector('#cvxCt')?.textContent || '').includes('Gọi xác nhận đơn UAT')"
            )

            # 5) Mobile 390x844: kiểm tra popup chuông & điều hướng đơn hàng không tràn ngang
            mob = browser.new_context(viewport={"width": 390, "height": 844})
            mob.add_cookies([{
                "name": TEN_COOKIE, "value": token, "domain": "127.0.0.1",
                "path": "/", "httpOnly": True, "sameSite": "Lax",
            }])
            mp = mob.new_page()
            mp.on("pageerror", lambda e: errs.append(str(e)))
            mp.goto(base, wait_until="domcontentloaded")
            mp.wait_for_selector("#chuongNut")
            mp.click("#chuongNut")
            mp.wait_for_selector("#chuongKhung:not([hidden])")
            mp.wait_for_selector("#chuongDs .chuong__dong")
            ov = mp.evaluate("() => ({sw: document.documentElement.scrollWidth, iw: window.innerWidth, box: document.querySelector('#chuongKhung').getBoundingClientRect()})")
            assert ov["sw"] <= ov["iw"], ov
            assert ov["box"]["left"] >= 0 and ov["box"]["right"] <= 390.5, ov
            mp.screenshot(path=str(shots / "mobile-bell-open.png"))

            mp.locator("#chuongDs .chuong__dong", has_text=ma_don_test).click()
            mp.wait_for_selector("#orderDetail:not([hidden])")
            mp.wait_for_function(
                f"() => (document.querySelector('#orderDetail')?.textContent || '').includes({json.dumps(ma_don_test)}) "
                "&& getComputedStyle(document.querySelector('#orderDetail')).opacity === '1'"
            )
            mp.screenshot(path=str(shots / "mobile-bell-order-panel.png"))

            # 6) Kiểm tra tài khoản bị mất quyền không mở được thông báo ngoài phạm vi
            low = browser.new_context(viewport={"width": 1440, "height": 900})
            low.add_cookies([{
                "name": TEN_COOKIE, "value": low_token, "domain": "127.0.0.1",
                "path": "/", "httpOnly": True, "sameSite": "Lax",
            }])
            lp = low.new_page()
            lp.on("pageerror", lambda e: errs.append(str(e)))
            lp.goto(base, wait_until="domcontentloaded")
            lp.wait_for_selector("#chuongNut")
            lp.wait_for_function("() => Number(document.querySelector('#chuongSo')?.textContent || '0') === 0")
            lp.click("#chuongNut")
            lp.wait_for_selector("#chuongDs .chuong__dong.chuong__dong--khoa")
            khoa_text = lp.locator("#chuongDs .chuong__dong.chuong__dong--khoa").first.inner_text()
            assert "AI chuyển hội thoại kênh ngoài" not in khoa_text
            assert "Ngoài phạm vi" in khoa_text
            lp.locator("#chuongDs .chuong__dong.chuong__dong--khoa").first.click()
            lp.wait_for_function(
                "() => (document.querySelector('#toast')?.textContent || '').includes('không còn quyền')"
            )

            assert not errs, errs
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
