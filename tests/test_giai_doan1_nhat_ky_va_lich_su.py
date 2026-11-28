"""Kiểm thử hồi quy Giai đoạn 1: BUG-LS-01, BUG-NK-01, BUG-NK-02, BUG-NK-03, SEC-NK-01, TECH-DEBT-KHO-01."""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _hoi_thoai_dau,
    _kenh_webchat,
    _khach_nhan,
    _nhan_vien_moi,
    _quan_tri_vao,
    _sql,
    _them_thanh_vien,
)


def _chay_role(app_that, qt, *, ten: str, quyen: list[str], kenh_ids: list[str] = ()):
    vt_ten = f"vt-{ten}-{uuid.uuid4().hex[:6]}"
    r_vt = qt.post("/api/vai-tro", json={"ten": vt_ten, "mo_ta": "", "quyen": quyen})
    assert r_vt.status_code == 201, r_vt.text
    uid, client = _nhan_vien_moi(qt, ten, vai_tro=vt_ten)
    for kid in kenh_ids:
        _them_thanh_vien(app_that, kid, uid)
    return uid, client


# =====================================================================
#  BUG-LS-01: Tách lịch sử Kết nối & Tích hợp khỏi SLA / CSAT / VietQR
# =====================================================================

def test_bug_ls_01_tach_lich_su_ket_noi_khoi_cau_hinh_nghiep_vu(csdl_kiem_thu, monkeypatch):
    from agent import cau_hinh_dong as cd
    from agent import db
    from agent import ket_noi_tich_hop as kn
    from agent.config import settings
    from agent.security.credential_vault import CredentialVault

    monkeypatch.setattr(settings, "database_url", csdl_kiem_thu)
    monkeypatch.setattr(cd, "_vault",
                        lambda: CredentialVault({1: bytes.fromhex("07" * 32)}, active_version=1))
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    db._pool = None

    async def chay():
        await db.init_db()
        try:
            # Dòng lịch sử cũ trước bản vá: phải được giữ nguyên trong CSDL nhưng lọc khỏi doc_lich_su().
            await db.execute(
                "INSERT INTO lich_su_ket_noi (dich_vu, truong, hanh_dong, bi_mat, sua_boi) "
                "VALUES ('sla', 'SLA_CU', 'dat', false, 'admin_cu')"
            )
            await cd.dat("SLA_NGUONG_CANH_BAO", "85", sua_boi="lan")
            await cd.dat("CSAT_BAT", "bat", sua_boi="lan")
            await cd.dat("VIETQR_BIN", "970436", sua_boi="lan")
            await cd.dat("GHN_SHOP_ID", "999888", sua_boi="lan")

            ls = await kn.doc_lich_su()
            ls_sla = await kn.doc_lich_su(dich_vu="sla")
            tho = await db.fetch("SELECT dich_vu, truong FROM lich_su_ket_noi")
            evs = await db.fetch(
                "SELECT kind, actor, detail FROM events WHERE kind = 'cau_hinh_api.doi' ORDER BY id"
            )
            return ls, ls_sla, tho, evs
        finally:
            cd._gia_tri.clear()
            cd._meta.clear()
            await db.close_db()

    ls, ls_sla, tho, evs = asyncio.run(chay())
    assert [x["truong"] for x in ls] == ["GHN_SHOP_ID"]
    assert ls_sla == []
    # Dữ liệu cũ SLA_CU không bị xoá, các khoá mới SLA/CSAT/VietQR không ghi mới vào lich_su_ket_noi.
    truongs_trong_bang = {r["truong"] for r in tho}
    assert "SLA_CU" in truongs_trong_bang
    assert not (truongs_trong_bang & {"SLA_NGUONG_CANH_BAO", "CSAT_BAT", "VIETQR_BIN"})
    # Nhưng mọi thay đổi cấu hình vẫn truy vết đầy đủ trong events.
    ev_khoas = {
        e["detail"]["khoa"]: (e["actor"], e["detail"].get("nhom"))
        for e in evs if isinstance(e["detail"], dict)
    }
    assert ev_khoas["SLA_NGUONG_CANH_BAO"] == ("lan", "sla")
    assert ev_khoas["CSAT_BAT"] == ("lan", "csat")
    assert ev_khoas["VIETQR_BIN"] == ("lan", "thanh_toan")
    assert ev_khoas["GHN_SHOP_ID"] == ("lan", "van_chuyen")


# =====================================================================
#  BUG-NK-01 & BUG-NK-03: Chuẩn hoá actor & nhóm sự kiện
# =====================================================================

def test_bug_nk_01_va_nk_03_actor_va_nhom_su_kien(app_that, monkeypatch):
    from types import SimpleNamespace

    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk
    from agent.erp import day_don

    async def fake_erp(*a, **kw):
        return SimpleNamespace(ket_cuc="khong_bat", erp_ma_don=None, ly_do="")

    monkeypatch.setattr(day_don, "day_don_da_luu", fake_erp)

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _, nv = _chay_role(
        app_that, qt, ten="linh_nk01",
        quyen=["don.doc", "don.sua", "agent.dieu_khien", "dinh_tuyen.sua", "nhat_ky.doc"],
        kenh_ids=[tk],
    )

    async def seed():
        d1 = await db.fetchrow_chac(
            "INSERT INTO orders (ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai) "
            "VALUES ('DH-NK01-APP', 'webchat', 'A', '0901', 'HN', '[]'::jsonb, 100000, 'cho_duyet') RETURNING id"
        )
        d2 = await db.fetchrow_chac(
            "INSERT INTO orders (ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai) "
            "VALUES ('DH-NK01-CAN', 'webchat', 'B', '0902', 'HN', '[]'::jsonb, 100000, 'cho_duyet') RETURNING id"
        )
        return str(d1["id"]), str(d2["id"])

    oid1, oid2 = _sql(app_that, seed)
    assert nv.post(f"/api/orders/{oid1}/approve").status_code == 200
    assert nv.post(f"/api/orders/{oid2}/cancel").status_code == 200
    assert nv.post("/api/runtime", json={"mode": "assist"}).status_code == 200
    assert nv.put(
        "/api/routing/sla-policies",
        json={"account_id": tk, "priority": "normal", "first_response_minutes": 10,
              "resolution_minutes": 60, "business_hours": {}},
    ).status_code == 200

    async def kiem():
        await db.log_event("kho.nhap", actor="linh_nk01", ma="SP1", so_luong=5)
        await db.log_event("kho.nhap_hoan", actor="linh_nk01", ma="SP1", so_luong=1)
        await db.log_event("erp.anh_xa_lech", ma="SP1")
        await db.log_event("erp.don_da_day", ma_don="DH-NK01-APP")
        await db.log_event("sla.muc_tieu_doi", actor="linh_nk01", phut=15)
        await db.log_event("sla.error", loi="timeout")
        await db.log_event("lich_lam_viec.doi", actor="linh_nk01")
        await db.log_event("chatwoot.resolved", actor="chatwoot", nguon="tich_hop_ngoai")

        rows = await db.fetch(
            "SELECT kind, actor FROM events WHERE kind IN ('order.approve', 'order.cancel', "
            "'runtime.update', 'routing.sla_upserted') ORDER BY id"
        )
        kq = await nk.tim(limit=100)
        by_kind = {b["kind"]: b for b in kq["items"]}
        return rows, by_kind

    rows, by_kind = _sql(app_that, kiem)
    for r in rows:
        assert r["actor"] == "linh_nk01", r

    assert by_kind["kho.nhap"]["nhom"]["ma"] == "kho"
    assert by_kind["kho.nhap_hoan"]["nhom"]["ma"] == "kho"
    assert by_kind["erp.anh_xa_lech"]["nhom"]["ma"] == "kho"
    assert by_kind["erp.don_da_day"]["nhom"]["ma"] == "don_hang"
    assert by_kind["order.approve"]["nhom"]["ma"] == "don_hang"
    assert by_kind["sla.muc_tieu_doi"]["nhom"]["ma"] == "cau_hinh"
    assert by_kind["routing.sla_upserted"]["nhom"]["ma"] == "cau_hinh"
    assert by_kind["lich_lam_viec.doi"]["nhom"]["ma"] == "cau_hinh"
    assert by_kind["sla.error"]["nhom"]["ma"] == "he_thong"
    assert by_kind["chatwoot.resolved"]["nhom"]["ma"] == "hoi_thoai"
    assert by_kind["chatwoot.resolved"]["tac_nhan"]["loai"] == "tich_hop"


# =====================================================================
#  BUG-NK-02 & TECH-DEBT-KHO-01: Truy vết biến động kho & độ tin cậy tồn
# =====================================================================

def test_bug_nk_02_va_tech_debt_kho_01(app_that):
    from agent import db

    qt = _quan_tri_vao(app_that)
    now = datetime.now(timezone.utc)

    async def seed():
        ma1 = f"SKU-NK02-{uuid.uuid4().hex[:5].upper()}"
        ma2 = f"SKU-DEBT-{uuid.uuid4().hex[:5].upper()}"
        await db.execute(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ($1, 10), ($2, 5)",
            ma1, ma2,
        )
        # 1) Đơn DH-AI giữ hàng lúc T0 bởi AI Agent; nhân viên "linh" duyệt lúc T0 + 2 giờ.
        ma_don_a = f"DH-{uuid.uuid4().hex[:6].upper()}"
        t0 = now - timedelta(hours=3)
        t1 = now - timedelta(hours=1)
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don, ghi_chu, luc) "
            "VALUES ($1, -2, 'ban', $2, 'Giữ khi lên đơn', $3)",
            ma1, ma_don_a, t0,
        )
        await db.execute(
            "INSERT INTO events (kind, actor, detail, created_at) VALUES "
            "('order.created', 'agent', $1::jsonb, $2), "
            "('order.approve', 'linh', $3::jsonb, $4)",
            {"ma_don": ma_don_a, "nguoi_khoi_tao": "agent", "nguon_thuc_thi": "cho_duyet"},
            t0,
            {"ma_don": ma_don_a, "boi": "linh", "nguoi_phe_duyet": "linh"},
            t1,
        )
        # 2) Dữ liệu lịch sử thiếu event & thiếu mốc đầu kỳ (ton_kho=5 nhưng lịch sử có nhap +10 => tồn đầu suy diễn -5)
        ma_don_cu = f"DH-CU-{uuid.uuid4().hex[:5].upper()}"
        await db.execute(
            "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don, ghi_chu, luc) VALUES "
            "($1, -3, 'ban', $2, 'Lịch sử không event', $3), "
            "($4, 10, 'nhap', '', 'Thiếu mốc đầu kỳ', $5)",
            ma1, ma_don_cu, t0 - timedelta(hours=5), ma2, t0,
        )
        return ma1, ma2, ma_don_a, ma_don_cu

    ma1, ma2, ma_don_a, ma_don_cu = _sql(app_that, seed)

    r1 = qt.get("/api/kho/bien-dong/bang", params={"q": ma1, "page_size": 20})
    assert r1.status_code == 200
    by_don = {x["ma_don"]: x for x in r1.json()["items"] if x["ma"] == ma1}
    assert by_don[ma_don_a]["nguoi_thuc_hien"] == "AI Agent"
    assert by_don[ma_don_a]["nguoi_khoi_tao"] == "AI Agent"
    assert by_don[ma_don_a]["nguoi_phe_duyet"] == "linh"
    assert by_don[ma_don_a]["nguon_thuc_thi"] == "cho_duyet"
    # Lịch sử thiếu chứng cứ KHÔNG suy đoán thành "Hệ thống" hay gán cho ai.
    assert by_don[ma_don_cu]["nguoi_thuc_hien"] == ""

    r2 = qt.get("/api/kho/bien-dong/bang", params={"q": ma2, "page_size": 20})
    assert r2.status_code == 200
    debt_items = [x for x in r2.json()["items"] if x["ma"] == ma2]
    assert len(debt_items) == 1
    assert debt_items[0]["ton_sau"] == 5
    assert debt_items[0]["do_tin_cay_ton"] == "thieu_can_cu"
    assert "đầu kỳ" in debt_items[0]["ly_do_tin_cay"]


# =====================================================================
#  SEC-NK-01: Phân quyền theo phạm vi kênh và đối tượng trên mọi cổng Nhật ký
# =====================================================================

def test_sec_nk_01_pham_vi_kenh_va_doi_tuong_da_vai_tro(app_that):
    from agent import db
    from agent.core import luot_ai

    qt = _quan_tri_vao(app_that)
    tk_a = _kenh_webchat(qt, ten="Kênh A")
    tk_b = _kenh_webchat(qt, ten="Kênh B")

    _khach_nhan(app_that, tk_a, "Khách A", "số của chị là 0909888777")
    cid_a = str(_hoi_thoai_dau(app_that)["id"])
    _khach_nhan(app_that, tk_b, "Khách B", "tin bí mật kênh B 0988777666")

    async def lay_cid_b():
        r = await db.fetchrow_chac(
            "SELECT id FROM conversations WHERE account_id = $1 LIMIT 1", uuid.UUID(tk_b)
        )
        return str(r["id"])

    cid_b = _sql(app_that, lay_cid_b)

    uid_lead_a, lead_a = _chay_role(
        app_that, qt, ten="lead_kenh_a",
        quyen=["nhat_ky.doc", "nhat_ky.su_co", "hoi_thoai.doc", "don.doc", "cong_viec.doc"],
        kenh_ids=[tk_a],
    )
    _, chi_don = _chay_role(
        app_that, qt, ten="chuyen_don",
        quyen=["nhat_ky.doc", "don.doc"],
        kenh_ids=[tk_a],
    )
    _, nv_thuong = _chay_role(
        app_that, qt, ten="nv_thuong_nk",
        quyen=["hoi_thoai.doc"],
        kenh_ids=[tk_a],
    )
    uid_b, _ = _chay_role(
        app_that, qt, ten="nv_kenh_b",
        quyen=["hoi_thoai.doc"],
        kenh_ids=[tk_b],
    )

    async def seed():
        tin_a = await db.fetchrow_chac(
            "INSERT INTO messages (conversation_id, role, content, direction, delivery_status) "
            "VALUES ($1, 'agent', 'nháp A 0909888777', 'outbound', 'draft') RETURNING id",
            uuid.UUID(cid_a),
        )
        tin_b = await db.fetchrow_chac(
            "INSERT INTO messages (conversation_id, role, content, direction, delivery_status) "
            "VALUES ($1, 'agent', 'nháp B bí mật', 'outbound', 'draft') RETURNING id",
            uuid.UUID(cid_b),
        )
        with luot_ai.mo_luot(uuid.UUID(cid_a), tin_a["id"]) as lid_a:
            await db.log_event("ai.soan_nhap", actor="agent", ref_id=uuid.UUID(cid_a), co_can_cu=True)
        with luot_ai.mo_luot(uuid.UUID(cid_b), tin_b["id"]) as lid_b:
            await db.log_event("ai.soan_nhap", actor="agent", ref_id=uuid.UUID(cid_b), co_can_cu=True)

        await db.execute(
            "UPDATE messages SET dau_vet_ai = $2::jsonb WHERE id = $1",
            tin_a["id"], {"luot_id": lid_a},
        )
        await db.execute(
            "UPDATE messages SET dau_vet_ai = $2::jsonb WHERE id = $1",
            tin_b["id"], {"luot_id": lid_b},
        )

        ev_a = (await db.fetchrow_chac(
            "SELECT id FROM events WHERE kind = 'ai.soan_nhap' AND detail ->> 'luot_id' = $1", lid_a
        ))["id"]
        ev_b = (await db.fetchrow_chac(
            "SELECT id FROM events WHERE kind = 'ai.soan_nhap' AND detail ->> 'luot_id' = $1", lid_b
        ))["id"]
        await db.log_event("nguoi_dung.vai_tro", actor="admin", ref_id=uuid.UUID(uid_b))
        await db.log_event("sla.muc_tieu_doi", actor="admin", phut=12)
        sc_b = await db.fetchrow_chac(
            "INSERT INTO events (kind, actor, ref_id, detail) VALUES ('su_co.danh_dau', 'admin', $1, $2) RETURNING id",
            uuid.UUID(cid_b), {"su_kien_goc": int(ev_b), "kind_goc": "ai.soan_nhap", "hoi_thoai_id": cid_b, "ghi_chu": "lỗi B"},
        )
        return lid_a, lid_b, int(ev_a), int(ev_b), int(sc_b["id"])

    lid_a, lid_b, ev_a, ev_b, sc_b = _sql(app_that, seed)

    # 1. Nhân viên thường không có nhat_ky.doc -> 403 toàn bộ cổng /api/nhat-ky và /api/events
    assert nv_thuong.get("/api/nhat-ky").status_code == 403
    assert nv_thuong.get(f"/api/nhat-ky/{ev_a}").status_code == 403
    assert nv_thuong.get(f"/api/nhat-ky/luot/{lid_a}").status_code == 403
    assert nv_thuong.get("/api/events").status_code == 403

    # 2. Lead Kênh A thấy Kênh A, KHÔNG thấy Kênh B, KHÔNG thấy truy_cap / cau_hinh / danh sách toàn công ty
    r_list = lead_a.get("/api/nhat-ky?limit=100")
    assert r_list.status_code == 200
    kinds_and_cids = {(x["kind"], x["hoi_thoai_id"]) for x in r_list.json()["items"]}
    assert ("ai.soan_nhap", cid_a) in kinds_and_cids
    assert ("ai.soan_nhap", cid_b) not in kinds_and_cids
    assert not any(x["kind"] in ("nguoi_dung.vai_tro", "sla.muc_tieu_doi") for x in r_list.json()["items"])
    assert "0909888777" not in r_list.text

    # Đọc trực tiếp ID / lượt / đề xuất / sự cố thuộc Kênh B -> 404 hoặc không rò dữ liệu
    assert lead_a.get(f"/api/nhat-ky/{ev_a}").status_code == 200
    assert lead_a.get(f"/api/nhat-ky/{ev_b}").status_code == 404
    assert lead_a.get(f"/api/nhat-ky/luot/{lid_a}").status_code == 200
    assert lead_a.get(f"/api/nhat-ky/luot/{lid_b}").status_code == 404
    assert lead_a.post(f"/api/nhat-ky/{ev_b}/su-co", json={"ghi_chu": "thử vượt kênh"}).status_code == 404
    assert lead_a.post(f"/api/nhat-ky/{ev_b}/giai-trinh", json={"ghi_chu": "thử vượt kênh"}).status_code == 404
    assert lead_a.post(
        f"/api/nhat-ky/su-co/{sc_b}/buoc", json={"loai": "tat_ai", "ghi_chu": "thử"}
    ).status_code == 404

    # CSV, /api/events và /de-xuat cũng lọc theo phạm vi
    csv_r = lead_a.get("/api/nhat-ky/xuat.csv")
    assert csv_r.status_code == 200 and cid_b not in csv_r.text and lid_b not in csv_r.text
    dx_r = lead_a.get("/api/nhat-ky/de-xuat")
    assert dx_r.status_code == 200 and all(x["hoi_thoai_id"] != cid_b for x in dx_r.json()["items"])
    ev_r = lead_a.get("/api/events")
    assert ev_r.status_code == 200 and cid_b not in ev_r.text

    # Danh mục không liệt kê nhân sự ngoài kênh khi thiếu nguoi_dung.doc
    dm_r = lead_a.get("/api/nhat-ky/danh-muc")
    assert dm_r.status_code == 200
    dm_ids = {u["id"] for u in dm_r.json()["nguoi"]}
    assert uid_lead_a in dm_ids and uid_b not in dm_ids

    # 3. Người có nhat_ky.doc + don.doc nhưng KHÔNG có hoi_thoai.doc -> không đọc được lượt AI/tin khách
    assert chi_don.get(f"/api/nhat-ky/luot/{lid_a}").status_code == 404
    assert chi_don.get(f"/api/nhat-ky/{ev_a}").status_code == 404
