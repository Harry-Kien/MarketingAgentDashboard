"""UX-LS/NK Phase 2 on isolated PostgreSQL; retain Phase 1 scope and redaction."""
from uuid import UUID, uuid4

from tests.test_nghiem_thu_saas import _quan_tri_vao, _sql, _kenh_webchat
from tests.test_giai_doan1_nhat_ky_va_lich_su import _chay_role


def seed_history(app, qt):
    from agent import db
    kid = _kenh_webchat(qt, ten='Kênh lịch sử UX')
    role = uuid4()

    async def seed():
        for i in range(25):
            await db.log_event('vai_tro.sua', actor='sep', ref_id=role,
                               ten='Vai trò đã xóa UX',
                               truoc={'ten':'Vai trò đã xóa UX','quyen':['don.doc']},
                               sau={'ten':'Vai trò đã xóa UX','quyen':['kho.doc']},
                               them=['kho.doc'], bot=['don.doc'])
            await db.log_event('nguoi_dung.vai_tro', actor='sep', ref_id=uuid4(),
                               ten_dang_nhap='Nhân viên UX', truoc=['Cũ'], sau=['Mới'],
                               quyen_them=['kho.doc'], quyen_bot=['don.doc'])
            await db.execute("INSERT INTO lich_su_ket_noi (dich_vu,truong,hanh_dong,bi_mat,sua_boi,account_id,doi_tuong) VALUES ('ghn','GHN_TOKEN','dat',true,'sep',NULL,$1)", f'Dịch vụ UX {i}')
            await db.execute("INSERT INTO lich_su_ket_noi (dich_vu,truong,hanh_dong,bi_mat,sua_boi,account_id,doi_tuong) VALUES ('webchat','credentials','doi_credential',true,'sep',$1,$2)", UUID(kid),f'Kênh UX {i}')
        oid = uuid4()
        await db.execute("INSERT INTO orders(id,ma_don,channel,khach_ten,khach_sdt,khach_dia_chi,items,tong_tien,trang_thai) VALUES($1,'UXLS-ORDER','webchat','Khách UX','','','[]',0,'da_chot')",oid)
        await db.log_event('order.duyet',actor='sep',ref_id=oid,ma_don='UXLS-ORDER')
        for i in range(3):
            await db.log_event('kho.nhap', actor='sep', ma='UXLS-SKU',ghi_chu=f'UXLS nội dung {i}', api_secret='SECRET-SHOULD-NOT-MATCH')
        return str(oid)
    return kid, _sql(app, seed)


def test_history_independent_pages_deleted_role(app_that):
    qt = _quan_tri_vao(app_that)
    kid, _ = seed_history(app_that,qt)
    one=qt.get('/api/nhan-su/lich-su',params={'loai':'vai_tro','q':'Vai trò đã xóa UX','limit':20}).json()
    two=qt.get('/api/nhan-su/lich-su',params={'loai':'vai_tro','q':'Vai trò đã xóa UX','limit':20,'truoc':one['next_cursor']}).json()
    assert len(one['lich_su'])==20 and len(two['lich_su'])==5 and two['next_cursor'] is None
    assert not ({x['id'] for x in one['lich_su']} & {x['id'] for x in two['lich_su']})
    svc1=qt.get('/api/ket-noi/lich-su?chi_dich_vu=true&gioi_han=20').json()
    svc2=qt.get('/api/ket-noi/lich-su?chi_dich_vu=true&gioi_han=20&bo_qua=20').json()
    assert len(svc1)==20 and len(svc2)==5
    assert all(x['account_id'] is None for x in svc1+svc2)
    path=f'/api/ket-noi/kenh/{kid}/dong-thoi-gian'
    a=qt.get(path,params={'loai':'cau_hinh','gioi_han':20}).json()['su_kien']
    b=qt.get(path,params={'loai':'cau_hinh','gioi_han':20,'bo_qua':20}).json()['su_kien']
    assert len(a)==20 and b
    assert qt.get(path+'?bo_qua=-1').status_code==422


def test_audit_search_pagination_csv_and_secret(app_that):
    qt=_quan_tri_vao(app_that)
    _,oid=seed_history(app_that,qt)
    p={'q':'UXLS-SKU','loai_doi_tuong':'san_pham','limit':2}
    a=qt.get('/api/nhat-ky',params=p).json()
    assert len(a['items'])==2 and a['next_cursor']
    b=qt.get('/api/nhat-ky',params={**p,'truoc':a['next_cursor']}).json()
    assert len(b['items'])==1 and b['next_cursor'] is None
    assert qt.get('/api/nhat-ky?q=SECRET-SHOULD-NOT-MATCH').json()['items']==[]
    csv=qt.get('/api/nhat-ky/xuat.csv',params={'q':'UXLS-SKU','loai_doi_tuong':'san_pham'})
    assert csv.status_code==200 and csv.text.count('kho.nhap')==3
    assert 'SECRET-SHOULD-NOT-MATCH' not in csv.text
    order=qt.get('/api/nhat-ky?q=UXLS-ORDER&loai_doi_tuong=don_hang').json()['items']
    assert any(lk['id']==oid and lk['mo_duoc'] for x in order for lk in x['lien_ket'])
    assert qt.get('/api/nhat-ky?loai_doi_tuong=invalid').status_code==422


def test_phase2_rbac_real_accounts(app_that):
    qt=_quan_tri_vao(app_that)
    kid,_=seed_history(app_that,qt)
    _,limited=_chay_role(app_that,qt,ten='uxls_limited',quyen=['nhat_ky.doc','don.doc'])
    _,none=_chay_role(app_that,qt,ten='uxls_none',quyen=['hoi_thoai.doc'])
    for user in (limited,none):
        assert user.get('/api/nhan-su/lich-su?loai=vai_tro&q=UX').status_code==403
        assert user.get('/api/ket-noi/lich-su?chi_dich_vu=true').status_code==403
    assert none.get('/api/nhat-ky?q=UX').status_code==403
    assert none.get('/api/nhat-ky/xuat.csv?q=UX').status_code==403
    assert limited.get('/api/nhat-ky?q=Vai trò đã xóa UX').json()['items']==[]
    assert 'vai_tro.sua' not in limited.get('/api/nhat-ky/xuat.csv?q=Vai trò đã xóa UX').text
    _,channel=_chay_role(app_that,qt,ten='uxls_channel',quyen=['kenh.doc'],kenh_ids=[kid])
    rows=channel.get(f'/api/ket-noi/kenh/{kid}/dong-thoi-gian').json()['su_kien']
    assert all(x['loai']!='cau_hinh' for x in rows)
    assert channel.get(f'/api/ket-noi/kenh/{uuid4()}/dong-thoi-gian').status_code==404


def test_bug_ls_02_va_tech_debt_nk_01_gop_hien_thi_co_can_cu(app_that):
    """BUG-LS-02 + TECH-DEBT-NK-01: gộp đúng cặp cùng thao tác, không gộp nhầm sự kiện độc lập."""
    from datetime import datetime, timezone
    from agent import db, ket_noi_tich_hop as kn
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao, _sql

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, ten="Zalo Gộp Hiển Thị")
    assert qt.post(f"/api/channel-accounts/{tk}/disable").status_code == 200
    assert qt.post(f"/api/channel-accounts/{tk}/enable").status_code == 200

    # Đọc dòng thời gian gộp: mỗi thao tác (tạo, tạm ngắt, bật) chỉ hiện 1 dòng nhưng vẫn giữ truy vết nguồn.
    dtg = qt.get(f"/api/ket-noi/kenh/{tk}/dong-thoi-gian").json()["su_kien"]
    tao = [x for x in dtg if x["ky_thuat"].get("hanh_dong") == "tao"]
    tat = [x for x in dtg if x["ky_thuat"].get("hanh_dong") == "tat"]
    bat = [x for x in dtg if x["ky_thuat"].get("hanh_dong") == "bat"]
    assert len(tao) == 1 and set(tao[0]["ky_thuat"]["nguon"]) == {"events", "lich_su_ket_noi"}
    assert len(tat) == 1 and set(tat[0]["ky_thuat"]["nguon"]) == {"lich_su_ket_noi", "events"}
    assert len(bat) == 2 and all(set(x["ky_thuat"]["nguon"]) == {"lich_su_ket_noi", "events"} for x in bat)
    assert not any(
        x["loai"] == "su_kien" and x["ky_thuat"].get("kind") == "channel_account.status_changed"
        for x in dtg
    )

    # Dữ liệu gốc trong từng bảng vẫn còn nguyên khi lọc riêng theo loại
    chi_ev = qt.get(f"/api/ket-noi/kenh/{tk}/dong-thoi-gian?loai=su_kien").json()["su_kien"]
    chi_ch = qt.get(f"/api/ket-noi/kenh/{tk}/dong-thoi-gian?loai=cau_hinh").json()["su_kien"]
    assert any(x["ky_thuat"]["kind"] == "channel_account.created" for x in chi_ev)
    assert any(x["ky_thuat"]["hanh_dong"] == "tao" for x in chi_ch)

    # Hai sự kiện độc lập CÙNG THỜI ĐIỂM (cùng timestamp) không được gộp nhầm;
    # riêng zalo_personal.can_quet_lai phân biệt theo mã sức khoẻ & lý do.
    t0 = datetime(2026, 11, 28, 3, 0, 0, tzinfo=timezone.utc)

    async def chen_doc_lap():
        # 1) doi_credential và degraded cùng lúc -> không cùng thao tác -> giữ cả 2
        await db.execute(
            "INSERT INTO lich_su_ket_noi (dich_vu, truong, hanh_dong, bi_mat, account_id, doi_tuong, sua_boi, sua_luc) "
            "VALUES ('zalo_personal', 'credentials', 'doi_credential', true, $1, 'Zalo Gộp', 'sep', $2)",
            UUID(tk), t0,
        )
        await db.execute(
            "INSERT INTO account_health_events (account_id, status, code, detail, observed_at) "
            "VALUES ($1, 'degraded', 'provider.unreachable', '{\"ly_do\":\"Timeout\"}', $2)",
            UUID(tk), t0,
        )
        # 2) channel_account.status_changed KHÁC trạng thái tại cùng thời điểm -> không gộp với degraded
        await db.execute(
            "INSERT INTO events (kind, actor, ref_id, detail, created_at) "
            "VALUES ('channel_account.status_changed', 'system', $1, '{\"status\":\"active\"}', $2)",
            UUID(tk), t0,
        )
        # 3) zalo_personal.can_quet_lai ở t0+10s đi kèm health cùng mã & lý do -> gộp 1;
        # còn zalo_personal.can_quet_lai khác lý do ở t0+20s -> giữ riêng sự kiện nghiệp vụ.
        t1 = t0.replace(second=10)
        t2 = t0.replace(second=20)
        await db.execute(
            "INSERT INTO account_health_events (account_id, status, code, detail, observed_at) "
            "VALUES ($1, 'reauth_required', 'zalo_personal.can_quet_lai', '{\"ly_do\":\"Hết phiên QR\"}', $2)",
            UUID(tk), t1,
        )
        await db.execute(
            "INSERT INTO events (kind, actor, ref_id, detail, created_at) "
            "VALUES ('zalo_personal.can_quet_lai', 'system', $1, '{\"ly_do\":\"Hết phiên QR\"}', $2)",
            UUID(tk), t1,
        )
        await db.execute(
            "INSERT INTO events (kind, actor, ref_id, detail, created_at) "
            "VALUES ('zalo_personal.can_quet_lai', 'system', $1, '{\"ly_do\":\"Đăng nhập thiết bị lạ\"}', $2)",
            UUID(tk), t2,
        )
        return await kn.dong_thoi_gian(UUID(tk), gioi_han=50)

    kq = _sql(app_that, chen_doc_lap)
    cung_t0 = [x for x in kq if datetime.fromisoformat(x["luc"]) == t0]
    assert {x["loai"] for x in cung_t0} == {"cau_hinh", "suc_khoe", "su_kien"}
    qr_gop = [x for x in kq if x["ky_thuat"].get("code") == "zalo_personal.can_quet_lai"]
    assert len(qr_gop) == 1 and "zalo_personal.can_quet_lai" in qr_gop[0]["ky_thuat"].get("kinds", [])
    qr_rieng = [x for x in kq if x["loai"] == "su_kien" and x["ky_thuat"].get("kind") == "zalo_personal.can_quet_lai"]
    assert len(qr_rieng) == 1 and qr_rieng[0]["ky_thuat"]["ly_do"] == "Đăng nhập thiết bị lạ"


def test_bug_ls_03_oauth_va_loi_ghi_lich_su_khong_bi_nuot(app_that, monkeypatch):
    """BUG-LS-03: OAuth Meta/Zalo OA ghi đầy đủ lịch sử; lỗi ghi lịch sử được ghi nhận kiểm chứng."""
    import base64
    from agent import db, ket_noi_tich_hop as kn
    from agent.api import oauth_meta, oauth_zalo_oa
    from tests.test_nghiem_thu_saas import _quan_tri_vao, _sql

    async def _bo_han_muc(*a, **k):
        return None

    monkeypatch.setattr("agent.goi_cuoc.kiem_them_kenh", _bo_han_muc)
    qt = _quan_tri_vao(app_that)
    qt_id = str(_sql(app_that, lambda: db.fetchrow("SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'"))["id"])
    master_k = "1:" + base64.b64encode(b"\x01" * 32).decode()
    monkeypatch.setattr(oauth_meta.settings, "meta_app_id", "app-ls3")
    monkeypatch.setattr(oauth_meta.settings, "meta_app_secret", "sec-ls3")
    monkeypatch.setattr(oauth_meta.settings, "credential_master_keys", master_k)
    monkeypatch.setattr(oauth_meta.settings, "credential_active_key_version", 1)

    async def _dk_ok(**kw):
        return True, ""

    monkeypatch.setattr("agent.channels.dang_ky_webhook_meta.dang_ky_webhook_trang", _dk_ok)

    # 1) OAuth Meta: tạo mới FB + IG rồi kết nối lại
    _sql(app_that, lambda: oauth_meta._tao_tai_khoan_tu_danh_sach(
        [{"id": "pg-ls3", "name": "Shop LS3", "access_token": "t1",
          "instagram_id": "ig-ls3", "instagram_username": "shopls3"}],
        qt_id,
    ))
    _sql(app_that, lambda: oauth_meta._tao_tai_khoan_tu_danh_sach(
        [{"id": "pg-ls3", "name": "Shop LS3", "access_token": "t2",
          "instagram_id": "ig-ls3", "instagram_username": "shopls3"}],
        qt_id,
    ))
    ls_meta = qt.get("/api/ket-noi/lich-su", params={"gioi_han": 50}).json()
    assert any(x["dich_vu"] == "facebook" and x["hanh_dong"] == "tao" and x["sua_boi"] == "sep" for x in ls_meta)
    assert any(x["dich_vu"] == "instagram" and x["hanh_dong"] == "tao" and x["sua_boi"] == "sep" for x in ls_meta)
    assert any(x["dich_vu"] == "facebook" and x["hanh_dong"] == "doi_credential" and x["sua_boi"] == "sep" for x in ls_meta)
    assert any(x["dich_vu"] == "instagram" and x["hanh_dong"] == "doi_credential" and x["sua_boi"] == "sep" for x in ls_meta)

    # 2) OAuth Zalo OA: tạo mới rồi kết nối lại
    monkeypatch.setattr(oauth_zalo_oa.settings, "zalo_oa_app_id", "oa-ls3")
    monkeypatch.setattr(oauth_zalo_oa.settings, "zalo_oa_secret_key", "oa-sec-ls3")
    _sql(app_that, lambda: oauth_zalo_oa._luu_tai_khoan(
        oa_id="oa-ls3", ten="OA LS3", refresh_token="rt1", nguoi_bam=qt_id,
    ))
    _sql(app_that, lambda: oauth_zalo_oa._luu_tai_khoan(
        oa_id="oa-ls3", ten="OA LS3", refresh_token="rt2", nguoi_bam=qt_id,
    ))
    ls_oa = qt.get("/api/ket-noi/lich-su", params={"dich_vu": "zalo_oa", "gioi_han": 50}).json()
    assert [x["hanh_dong"] for x in ls_oa][:2] == ["doi_credential", "tao"]
    assert all(x["sua_boi"] == "sep" for x in ls_oa[:2])

    # 3) Lỗi ghi lịch sử không được bỏ qua âm thầm
    kn._LOI_GHI_LICH_SU.clear()
    goc_exec = db.execute

    async def exec_hong(sql, *args, conn=None):
        if "INSERT INTO lich_su_ket_noi" in sql:
            raise RuntimeError("DB readonly test")
        return await goc_exec(sql, *args, conn=conn)

    monkeypatch.setattr(db, "execute", exec_hong)
    ok = _sql(app_that, lambda: kn.ghi_lich_su(
        dich_vu="ghn", truong="GHN_TOKEN", hanh_dong="dat", sua_boi="sep", bi_mat=True,
    ))
    assert ok is False
    loi = kn.lay_loi_ghi_lich_su_gan_day()
    assert loi and loi[-1]["dich_vu"] == "ghn" and "DB readonly test" in loi[-1]["loi"]
    ev_loi = _sql(app_that, lambda: db.fetch("SELECT kind, detail FROM events WHERE kind = 'lich_su_ket_noi.ghi_loi'"))
    assert len(ev_loi) == 1


def test_bug_ls_04_xoa_tai_khoan_kenh_phan_biet_yeu_cau_thanh_cong_va_that_bai(app_that, monkeypatch):
    """BUG-LS-04: không ghi kenh.xoa_tai_khoan nếu xóa thất bại; bảo toàn bất biến của events."""
    import asyncpg
    from agent import db
    from tests.test_nghiem_thu_saas import _kenh_webchat, _khach_nhan, _quan_tri_vao, _sql

    qt = _quan_tri_vao(app_that)

    # 1) Xóa thất bại do còn hội thoại -> chỉ có kenh.yeu_cau_xoa & kenh.xoa_that_bai, KHÔNG có kenh.xoa_tai_khoan
    tk_giu = _kenh_webchat(qt, ten="Kênh Đang Có Khách")
    _khach_nhan(app_that, tk_giu, "Khách Giữ Kênh", "hello")
    r_409 = qt.delete(f"/api/channel-accounts/{tk_giu}")
    assert r_409.status_code == 409
    kinds_giu = [
        r["kind"] for r in _sql(
            app_that, lambda: db.fetch("SELECT kind FROM events WHERE ref_id = $1 ORDER BY id", UUID(tk_giu))
        )
    ]
    assert "kenh.yeu_cau_xoa" in kinds_giu and "kenh.xoa_that_bai" in kinds_giu
    assert "kenh.xoa_tai_khoan" not in kinds_giu
    assert _sql(app_that, lambda: db.fetch("SELECT 1 FROM lich_su_ket_noi WHERE account_id = $1 AND hanh_dong = 'xoa_tai_khoan'", UUID(tk_giu))) == []

    # 2) Xóa thất bại do lỗi ràng buộc bên trong transaction -> rollback, không ghi nhận đã xóa
    tk_loi = _kenh_webchat(qt, ten="Kênh Lỗi TX")
    goc_exec = db.execute

    async def exec_fk_loi(sql, *args, conn=None):
        if conn is not None and "DELETE FROM channel_accounts" in sql:
            raise asyncpg.ForeignKeyViolationError("restrict simulated")
        return await goc_exec(sql, *args, conn=conn)

    monkeypatch.setattr(db, "execute", exec_fk_loi)
    assert qt.delete(f"/api/channel-accounts/{tk_loi}").status_code == 409
    monkeypatch.setattr(db, "execute", goc_exec)
    kinds_loi = [
        r["kind"] for r in _sql(
            app_that, lambda: db.fetch("SELECT kind FROM events WHERE ref_id = $1 ORDER BY id", UUID(tk_loi))
        )
    ]
    assert "kenh.yeu_cau_xoa" in kinds_loi and "kenh.xoa_that_bai" in kinds_loi
    assert "kenh.xoa_tai_khoan" not in kinds_loi
    assert _sql(app_that, lambda: db.fetchrow("SELECT 1 FROM channel_accounts WHERE id = $1", UUID(tk_loi))) is not None

    # 3) Xóa thành công -> có yêu cầu + xóa thành công + lịch sử kết nối + events bất biến
    r_ok = qt.delete(f"/api/channel-accounts/{tk_loi}")
    assert r_ok.status_code == 200
    kinds_ok = [
        r["kind"] for r in _sql(
            app_that, lambda: db.fetch("SELECT kind FROM events WHERE ref_id = $1 ORDER BY id", UUID(tk_loi))
        )
    ]
    assert "kenh.xoa_tai_khoan" in kinds_ok
    assert _sql(app_that, lambda: db.fetch("SELECT 1 FROM lich_su_ket_noi WHERE account_id = $1 AND hanh_dong = 'xoa_tai_khoan'", UUID(tk_loi)))
    nk_xoa = [x for x in qt.get("/api/nhat-ky", params={"loai_doi_tuong": "tai_khoan_kenh", "muc_do": ""}).json()["items"]
              if x["kind"] == "kenh.xoa_tai_khoan" and x["ref_id"] == tk_loi]
    assert nk_xoa and "tài khoản đã xoá" in (nk_xoa[0]["tai_khoan"] or {}).get("ten", "")


def test_bug_nk_04_va_tech_debt_nk_02_loai_bo_loadEvents_va_deprecate_api_events(app_that):
    """BUG-NK-04 + TECH-DEBT-NK-02: GET /api/events deprecated nhưng giữ bảo mật; JS bỏ caller loadEvents."""
    from pathlib import Path
    from agent.main import app
    from tests.test_nghiem_thu_saas import _nhan_vien_moi, _quan_tri_vao

    root = Path(__file__).resolve().parent.parent
    for fname in ("07-noi-dung.js", "08-tai-khoan.js", "10-vong-lam-moi.js"):
        src = (root / "dashboard" / "src" / fname).read_text(encoding="utf-8")
        assert "loadEvents(" not in src and "async function loadEvents" not in src, fname
    nk_js = (root / "dashboard" / "src" / "27-nhat-ky.js").read_text(encoding="utf-8")
    assert "window.nkLamMoi = nkLamMoi" in nk_js
    assert 'EventSource("/api/inbox/events")' in (root / "dashboard" / "src" / "10-vong-lam-moi.js").read_text(encoding="utf-8")

    # OpenAPI đánh dấu deprecated cho /api/events
    spec = app.openapi()
    assert spec["paths"]["/api/events"]["get"].get("deprecated") is True

    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "nv_nk04")
    assert nv.get("/api/events").status_code == 403
    r_ev = qt.get("/api/events?limit=10")
    assert r_ev.status_code == 200
    assert r_ev.headers.get("Deprecation") == "true"
    assert "/api/nhat-ky" in r_ev.headers.get("Link", "")
    assert isinstance(r_ev.json(), list)
