"""Real HTTP + PostgreSQL kiemthu, all fixtures rolled back; no live workers.

RUN_HISTORY_BROWSER=1 DATABASE_URL=.../kiemthu pytest this_file -q
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

pytestmark = pytest.mark.skipif(os.getenv('RUN_HISTORY_BROWSER') != '1', reason='Opt-in kiemthu browser')


def test_history_phase2_desktop_mobile_rbac(monkeypatch):
    import uvicorn
    from playwright.sync_api import sync_playwright, expect
    from agent import db
    from agent.config import settings
    from agent.core.xac_thuc import bam_token
    from agent.main import app
    from agent.api.routes import TEN_COOKIE

    dsn = os.environ['DATABASE_URL']
    assert urlsplit(dsn).path == '/kiemthu'
    admin, limited, kid, oid, role = [uuid4() for _ in range(5)]
    token, lowtoken = uuid4().hex + uuid4().hex, uuid4().hex + uuid4().hex
    marker = 'LSUI-' + uuid4().hex[:8]
    evidence = {}
    shots = Path('docs/uat_evidence_history_phase2')
    shots.mkdir(exist_ok=True)

    @asynccontextmanager
    async def lifespan(_):
        c = await asyncpg.connect(dsn)
        await c.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
        protected = await c.fetchval("SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'")
        tx = c.transaction()
        await tx.start()
        lock = asyncio.Lock()

        class TransactionPool:
            def __getattr__(self, name):
                if name not in {'fetch', 'fetchrow', 'fetchval', 'execute', 'executemany'}:
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
            for uid, tok, suffix in ((admin,token,'admin'),(limited,lowtoken,'limited')):
                await c.execute("INSERT INTO nguoi_dung(id,ten_dang_nhap,mat_khau_bam,ho_ten,vai_tro) VALUES($1,$2,'x',$2,'nhan_vien')",uid,marker+suffix)
                await c.execute("INSERT INTO phien(token,nguoi_dung_id,het_han) VALUES($1,$2,now()+interval '1 hour')",bam_token(tok),uid)
            await c.execute("INSERT INTO nguoi_dung_vai_tro(nguoi_dung_id,vai_tro_id) SELECT $1,id FROM vai_tro WHERE ten='Quản trị'",admin)
            await c.execute("INSERT INTO channel_accounts(id,channel,display_name,external_account_id,status) VALUES($1,'webchat','Kênh kiểm thử lịch sử',$2,'active')",kid,marker)
            long_added = ['don.doc','don.sua','kho.doc','kho.sua','khach.doc','khach.sua','hoi_thoai.doc','hoi_thoai.tra_loi','cong_viec.doc','cong_viec.sua','bao_cao.doc','cau_hinh.doc']
            for i in range(25):
                for kind, ref, detail in [
                    ('vai_tro.sua',role,{'ten':'Vai trò lưu vết đã xóa','truoc':{'ten':'Vai trò lưu vết đã xóa','quyen':['don.doc','kenh.doc']},'sau':{'ten':'Vai trò lưu vết đã xóa','quyen':long_added},'them':long_added[1:],'bot':['kenh.doc']}),
                    ('nguoi_dung.vai_tro',limited,{'ten_dang_nhap':'Nhân viên kiểm thử','truoc':['Nhân viên'],'sau':['Điều phối'],'quyen_them':['kho.doc'],'quyen_bot':['don.doc']}),
                ]:
                    await c.execute("INSERT INTO events(kind,actor,ref_id,detail) VALUES($1,'Quản trị kiểm thử',$2,$3)",kind,ref,detail)
                for service, account in [('ghn',None),('webchat',kid)]:
                    await c.execute("INSERT INTO lich_su_ket_noi(dich_vu,truong,hanh_dong,bi_mat,sua_boi,account_id,doi_tuong,sua_luc) VALUES($1,'GHN_TOKEN','dat',true,'Quản trị kiểm thử',$2,$3,now()+$4*interval '1 second')",service,account,f'Đối tượng kiểm thử {i}',i)
            await c.execute("INSERT INTO orders(id,ma_don,channel,khach_ten,khach_sdt,khach_dia_chi,items,tong_tien,trang_thai) VALUES($1,$2,'webchat','Khách kiểm thử','','','[]',0,'da_chot')",oid,marker)
            await c.execute("INSERT INTO events(kind,actor,ref_id,detail) VALUES('order.duyet','Quản trị kiểm thử',$1,$2)",oid,{'ma_don':marker})
            yield
        finally:
            await tx.rollback()
            assert protected == await c.fetchval("SELECT to_jsonb(o)::text FROM orders o WHERE ma_don='AS2611262000164YS'")
            evidence['test17_unchanged'] = True
            db._pool = None
            await c.close()

    monkeypatch.setattr(settings,'database_url',dsn)
    monkeypatch.setattr(app.router,'lifespan_context',lifespan)
    sock = socket.socket()
    sock.bind(('127.0.0.1',0))
    base = f'http://127.0.0.1:{sock.getsockname()[1]}'
    server = uvicorn.Server(uvicorn.Config(app,log_level='error',timeout_graceful_shutdown=2))
    thread = threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as p:
            browser=p.chromium.launch()
            context=browser.new_context(viewport={'width':1440,'height':900})
            context.add_cookies([{'name':TEN_COOKIE,'value':token,'url':base}])
            page=context.new_page()
            failures=[]
            page.on('pageerror',lambda e:failures.append(str(e)))
            page.route('**/*',lambda r:r.continue_() if r.request.url.startswith(base+'/') and r.request.method in ('GET','HEAD') else r.abort())
            page.goto(base)
            page.wait_for_function("state.toiQuyen && state.toiQuyen.has('nguoi_dung.doc')")

            # 1. Desktop Lịch sử Kết nối & Tích hợp: 2 cột + cuộn độc lập + Việt hoá trường
            page.evaluate("doiMan('cc-ket-noi')")
            page.locator('[data-kn-phan-nut="lich-su"]').click()
            page.locator('#kn-dtg-tk').select_option(str(kid))
            expect(page.locator('#kn-ls-o [data-buoc="1"]')).to_be_enabled()
            expect(page.locator('#kn-dtg-o .ls-cuon')).to_contain_text('token Giao Hàng Nhanh')
            expect(page.locator('#kn-ls-o .ls-cuon')).not_to_contain_text('GHN_TOKEN')
            # Vùng danh sách cuộn độc lập, phân trang nằm ngoài vùng cuộn
            scroll_metrics = page.evaluate("""() => {
              const dtg = document.querySelector('#kn-dtg-o .ls-cuon');
              const ls = document.querySelector('#kn-ls-o .ls-cuon');
              const pager = document.querySelector('#kn-ls-o .ls-trang');
              const kn = document.querySelector('#kn-phan-lich-su');
              return {
                dtgScroll: dtg.scrollHeight > dtg.clientHeight,
                dtgH: dtg.getBoundingClientRect().height,
                lsScroll: ls.scrollHeight > ls.clientHeight,
                lsH: ls.getBoundingClientRect().height,
                pagerBelow: pager.getBoundingClientRect().top >= ls.getBoundingClientRect().bottom - 1,
                knH: kn.getBoundingClientRect().height,
                docH: document.documentElement.scrollHeight
              };
            }""")
            assert scroll_metrics['dtgScroll'] and scroll_metrics['lsScroll'], scroll_metrics
            assert scroll_metrics['dtgH'] <= 580 and scroll_metrics['lsH'] <= 580 and scroll_metrics['pagerBelow'], scroll_metrics
            assert scroll_metrics['knH'] <= 850, scroll_metrics
            page.locator('#kn-ls-o [data-buoc="1"]').click()
            expect(page.locator('#kn-ls-o .ls-trang')).to_contain_text('Trang 2')
            expect(page.locator('#kn-dtg-o .ls-trang')).to_contain_text('Trang 1')
            page.locator('#kn-ls-o [data-buoc="-1"]').click()
            expect(page.locator('#kn-ls-o .ls-trang')).to_contain_text('Trang 1')
            panels=page.locator('#kn-phan-lich-su > .panel')
            assert panels.nth(1).bounding_box()['x'] > panels.nth(0).bounding_box()['x']
            page.evaluate('window.scrollTo(0, 0)')
            page.screenshot(path=str(shots/'desktop-connections.png'))
            page.evaluate('window.scrollTo(0, 300)')
            assert page.locator('.masthead').bounding_box()['y'] == 0
            page.screenshot(path=str(shots/'desktop-connections-scrolled.png'))

            # 2. Desktop Lịch sử Nhân sự & Phân quyền + Modal chi tiết quyền
            page.evaluate('window.scrollTo(0, 0)')
            page.evaluate("doiMan('ns-lich-su')")
            expect(page.locator('[data-ls-next="vai_tro"]')).to_be_enabled()
            expect(page.locator('[data-ls-rows="vai_tro"].ls-cuon')).to_be_visible()
            ns_metrics = page.evaluate("""() => {
              const r = document.querySelector('[data-ls-rows="vai_tro"].ls-cuon');
              const p = document.querySelector('[data-ls-pager="vai_tro"]');
              const g = document.querySelector('#ns-lich-su .ls-hai-cot');
              return { canScroll: r.scrollHeight > r.clientHeight, h: r.getBoundingClientRect().height,
                       pagerBelow: p.getBoundingClientRect().top >= r.getBoundingClientRect().bottom - 1,
                       gridH: g.getBoundingClientRect().height,
                       docH: document.documentElement.scrollHeight };
            }""")
            assert ns_metrics['canScroll'] and ns_metrics['h'] <= 580 and ns_metrics['pagerBelow'], ns_metrics
            assert ns_metrics['gridH'] <= 850, ns_metrics
            page.locator('[data-ls-next="vai_tro"]').click()
            expect(page.locator('[data-ls-pager="vai_tro"]')).to_contain_text('Trang 2')
            expect(page.locator('[data-ls-pager="nguoi_dung"]')).to_contain_text('Trang 1')
            page.locator('[data-ls-prev="vai_tro"]').click()
            expect(page.locator('[data-ls-pager="vai_tro"]')).to_contain_text('Trang 1')
            assert page.locator('[data-ls-rows] .pill').count()==0
            page.screenshot(path=str(shots/'desktop-personnel.png'))
            page.locator('[data-ls-kind="vai_tro"]').first.click()
            expect(page.locator('dialog[open] [data-ls-close]')).to_be_visible()
            expect(page.locator('dialog[open]')).to_contain_text('Quyền được cấp (11)')
            expect(page.locator('dialog[open]')).to_contain_text('Quyền bị thu hồi (1)')
            page.screenshot(path=str(shots/'desktop-permissions.png'))
            page.locator('dialog[open] [data-ls-close]').click()
            expect(page.locator('dialog[open]')).to_have_count(0)

            # 3. Nhật ký hệ thống: bộ lọc nâng cao mặc định thu gọn + đồng bộ mô tả mức độ
            page.evaluate("doiMan('ht-nhat-ky')")
            expect(page.locator('.nk-loc-nangcao')).not_to_have_attribute('open', '')
            page.locator('[data-nk-loc] [name="q"]').fill(marker)
            page.locator('[data-nk-loc] [name="loai_doi_tuong"]').select_option('don_hang')
            page.locator('[data-nk-loc] button[type=submit]').click()
            expect(page.locator('[data-nk-ds]')).to_contain_text(marker)
            expect(page.locator('[data-nk-hien-ghi]')).to_contain_text('toàn bộ mức sự kiện')
            page.screenshot(path=str(shots/'desktop-audit.png'))
            page.locator(f'[data-nk-lk="don_hang|{oid}"]').first.click()
            expect(page.locator('#orderDetailTitle')).to_contain_text(marker)
            page.keyboard.press('Escape')

            # 4. Mobile: tab con 2 nhóm bảo toàn bộ lọc/trang + không ngắt chữ số ngày giờ
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('window.scrollTo(0, 0)')
            page.evaluate("doiMan('cc-ket-noi')")
            page.locator('[data-kn-phan-nut="lich-su"]').click()
            page.wait_for_timeout(300)
            expect(page.locator('#kn-dtg-panel')).to_be_visible()
            expect(page.locator('#kn-ls-panel')).to_be_hidden()
            page.screenshot(path=str(shots/'mobile-connections.png'))
            page.locator('[data-kn-ls-tab="dich_vu"]').click()
            expect(page.locator('#kn-ls-panel')).to_be_visible()
            expect(page.locator('#kn-dtg-panel')).to_be_hidden()
            page.locator('#kn-ls-o [data-buoc="1"]').click()
            expect(page.locator('#kn-ls-o .ls-trang')).to_contain_text('Trang 2')
            page.locator('[data-kn-ls-tab="kenh"]').click()
            page.locator('[data-kn-ls-tab="dich_vu"]').click()
            expect(page.locator('#kn-ls-o .ls-trang')).to_contain_text('Trang 2')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.screenshot(path=str(shots/'mobile-connections-services.png'))

            page.evaluate("doiMan('ns-lich-su')")
            page.wait_for_timeout(300)
            expect(page.locator('[data-ls-cot="nguoi_dung"]')).to_be_visible()
            expect(page.locator('[data-ls-cot="vai_tro"]')).to_be_hidden()
            page.screenshot(path=str(shots/'mobile-personnel.png'))
            page.locator('[data-ls-subtab="vai_tro"]').click()
            expect(page.locator('[data-ls-cot="vai_tro"]')).to_be_visible()
            expect(page.locator('[data-ls-cot="nguoi_dung"]')).to_be_hidden()
            page.locator('[data-ls-next="vai_tro"]').click()
            expect(page.locator('[data-ls-pager="vai_tro"]')).to_contain_text('Trang 2')
            page.locator('[data-ls-subtab="nguoi_dung"]').click()
            page.locator('[data-ls-subtab="vai_tro"]').click()
            expect(page.locator('[data-ls-pager="vai_tro"]')).to_contain_text('Trang 2')
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.locator('[data-ls-kind="vai_tro"]').first.click()
            expect(page.locator('dialog[open]')).to_be_visible()
            page.screenshot(path=str(shots/'mobile-permissions.png'))
            page.locator('dialog[open] [data-ls-close]').click()

            page.evaluate("doiMan('ht-nhat-ky')")
            page.wait_for_timeout(300)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            page.screenshot(path=str(shots/'mobile-audit.png'))

            limited_context=browser.new_context()
            limited_context.add_cookies([{'name':TEN_COOKIE,'value':lowtoken,'url':base}])
            for path in ['/api/nhat-ky?q=UX','/api/nhan-su/lich-su','/api/ket-noi/lich-su']:
                assert limited_context.request.get(base+path).status==403
            assert not failures, failures
            evidence['js_errors']=failures
            browser.close()
    finally:
        server.should_exit=True
        thread.join(timeout=15)
        sock.close()
    assert evidence.get('test17_unchanged')
