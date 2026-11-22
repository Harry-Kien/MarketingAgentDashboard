"""
Kết nối & Tích hợp trên Postgres THẬT: sổ webhook, sổ kiểm, lịch sử thay đổi,
tuỳ chọn ẩn bình luận theo Trang, và luật "không lặp thông báo AI trong cùng
một hội thoại" — kể cả khi hai tin tới cùng lúc hay nội dung vừa được sửa.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import asyncpg
import pytest

from agent import cau_hinh_dong as cd
from agent import ket_noi_tich_hop as kn
from agent.api import ket_noi_tich_hop as api_kn
from agent.security.credential_vault import CredentialVault
from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent


async def _mo(url):
    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    db._pool = await asyncpg.create_pool(url, min_size=1, max_size=4, init=_codec)
    async with db._pool.acquire() as conn:
        await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
        await apply_all(conn)
        fb = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
            "VALUES ('facebook','Trang A','active','fb-kn') RETURNING id")
        oa = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
            "VALUES ('zalo_oa','OA B','degraded','oa-kn') RETURNING id")
        kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id")
        d = await conn.fetchval("INSERT INTO contact_points (contact_id, channel_account_id, "
                                "external_user_id) VALUES ($1,$2,'k1') RETURNING id", kh, fb)
        cid = await conn.fetchval(
            "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
            "customer_name, contact_id, contact_point_id) VALUES ($1,'facebook','k1','k1','Lan',$2,$3) "
            "RETURNING id", fb, kh, d)
    return db, fb, oa, cid


async def _dong(db):
    await db._pool.close()
    db._pool = None


def _chay(url, ham):
    async def bao():
        db, fb, oa, cid = await _mo(url)
        try:
            return await ham(db, fb, oa, cid)
        finally:
            await _dong(db)
    return asyncio.run(bao())


def test_so_webhook_ghi_thong_ke_va_lich_su(csdl_kiem_thu):
    async def ham(db, fb, oa, cid):
        await kn.ghi_webhook_nhan(phuong_thuc="POST", duong="/webhook/shipping/ghn",
                                  ma_http=200, ms=12, loi=None)
        await kn.ghi_webhook_nhan(phuong_thuc="POST", duong="/webhook/shipping/ghn",
                                  ma_http=401, ms=3, loi="Bí mật webhook không đúng")
        await kn.ghi_webhook_nhan(phuong_thuc="POST", duong=f"/webhook/native/zalo-oa/{oa}",
                                  ma_http=401, ms=4, loi="chữ ký sai")
        # UUID rác trong đường dẫn: vẫn phải vào sổ (không khoá ngoại để mà hỏng).
        await kn.ghi_webhook_nhan(phuong_thuc="POST", duong="/webhook/native/zalo-oa/rac",
                                  ma_http=404, ms=1, loi=None)
        tk = await kn.thong_ke_webhook(["ghn", "zalo_oa", "ghtk"])
        tk_tk = await kn.thong_ke_webhook_tai_khoan([oa, fb])
        ls = await kn.lich_su_webhook(dich_vu="ghn")
        ls_tk = await kn.lich_su_webhook(account_id=oa)
        return tk, tk_tk, ls, ls_tk

    tk, tk_tk, ls, ls_tk = _chay(csdl_kiem_thu, ham)
    assert tk["ghn"]["dem_24h"] == 2 and tk["ghn"]["loi_24h"] == 1
    assert tk["ghn"]["loi_cuoi"]["ma_http"] == 401
    assert "không đúng" in tk["ghn"]["loi_cuoi"]["loi"]
    assert tk["zalo_oa"]["dem_24h"] == 2
    assert tk["ghtk"] == {}
    oa_tk = next(v for k, v in tk_tk.items() if v.get("loi_cuoi"))
    assert oa_tk["loi_cuoi"]["loi"] == "chữ ký sai"
    assert [r["ma_http"] for r in ls["goi_vao"]] == [401, 200]
    assert len(ls_tk["goi_vao"]) == 1 and ls_tk["tin_da_nhan"] == []


def test_so_kiem_va_trang_thai(csdl_kiem_thu, monkeypatch):
    monkeypatch.setattr(kn.settings, "ghn_token", "t" * 20)
    monkeypatch.setattr(kn.settings, "ghn_shop_id", "88")
    cd._gia_tri.clear()

    async def ham(db, fb, oa, cid):
        await kn.ghi_ket_qua_kiem("ghn", ok=True, chi_tiet="ok", ms=5,
                                  van_tay=kn.dau_van_tay("ghn"), boi="qt")
        await kn.ghi_ket_qua_kiem("ghn", ok=False, chi_tiet="401", ms=6,
                                  van_tay=kn.dau_van_tay("ghn"), boi="qt2")
        return await kn.doc_ket_qua_kiem()

    so = _chay(csdl_kiem_thu, ham)
    assert so["ghn"]["ok"] is False and so["ghn"]["kiem_boi"] == "qt2"
    assert kn.trang_thai("ghn", so["ghn"]) == kn.LOI
    monkeypatch.setattr(kn.settings, "ghn_token", "u" * 20)
    assert kn.trang_thai("ghn", so["ghn"]) == kn.CHUA_KIEM_TRA


def test_lich_su_ghi_that_khong_co_gia_tri(csdl_kiem_thu, monkeypatch):
    monkeypatch.setattr(cd, "_vault",
                        lambda: CredentialVault({1: bytes.fromhex("06" * 32)}, active_version=1))
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)

    async def ham(db, fb, oa, cid):
        await cd.dat("ERPNEXT_API_SECRET", "ERP-gia-tri-that-9876", sua_boi="lan")
        await cd.xoa("ERPNEXT_API_SECRET", sua_boi="minh")
        ls = await kn.doc_lich_su(dich_vu="erpnext")
        tho = await db.fetch("SELECT * FROM lich_su_ket_noi")
        return ls, tho

    try:
        ls, tho = _chay(csdl_kiem_thu, ham)
    finally:
        cd._gia_tri.clear()
        cd._meta.clear()
    assert [(x["truong"], x["hanh_dong"], x["sua_boi"], x["bi_mat"]) for x in ls] == [
        ("ERPNEXT_API_SECRET", "xoa", "minh", True), ("ERPNEXT_API_SECRET", "dat", "lan", True)]
    assert "ERP-gia-tri-that-9876" not in repr(tho)


def test_tuy_chon_an_binh_luan_theo_trang_va_danh_sach_plugin(csdl_kiem_thu, monkeypatch):
    """
    Đặt tuỳ chọn riêng cho MỘT Trang qua API → `che_do_an_binh_luan` đọc đúng
    nó, Trang khác vẫn theo cấu hình chung, có dòng lịch sử; danh sách plugin
    hiện cả hai tài khoản và đúng tuỳ chọn.
    """
    from agent.omnichannel import xu_ly_tin_vao as x

    monkeypatch.setattr(x.cau_hinh_dong, "lay",
                        lambda k: "tat" if k == "AN_BINH_LUAN_CO_SDT" else "")

    async def ham(db, fb, oa, cid):
        # TestClient chạy vòng lặp riêng — gọi thẳng hàm route bằng client
        # sẽ không thấy pool của vòng lặp này, nên gọi hàm xử lý trực tiếp.
        nguoi = nguoi_thu("kenh.sua", ten="qt", id=uuid4())
        await api_kn.tuy_chon_kenh(fb, api_kn.TuyChonKenhIn(an_binh_luan_co_sdt="bat"), nguoi)
        rieng = await x.che_do_an_binh_luan(fb)
        khac = await x.che_do_an_binh_luan(oa)
        ds = await api_kn.plugin_kenh()
        ls = await kn.doc_lich_su()
        await api_kn.tuy_chon_kenh(fb, api_kn.TuyChonKenhIn(an_binh_luan_co_sdt="chung"), nguoi)
        ve_chung = await x.che_do_an_binh_luan(fb)
        with pytest.raises(Exception) as loi:
            await api_kn.tuy_chon_kenh(oa, api_kn.TuyChonKenhIn(an_binh_luan_co_sdt="bat"), nguoi)
        return rieng, khac, ds, ls, ve_chung, loi.value

    rieng, khac, ds, ls, ve_chung, loi = _chay(csdl_kiem_thu, ham)
    assert (rieng, khac, ve_chung) == ("bat", "tat", "tat")
    assert getattr(loi, "status_code", None) == 422     # OA không có bình luận
    fb_plugin = next(p for p in ds if p["ma"] == "facebook")
    assert fb_plugin["tai_khoan"][0]["an_binh_luan_co_sdt"]["rieng"] == "bat"
    assert {k["ma"] for k in fb_plugin["kha_nang"] if k["co"]} >= {"van_ban", "gui_anh", "an_binh_luan"}
    oa_plugin = next(p for p in ds if p["ma"] == "zalo_oa")
    oa_tk = oa_plugin["tai_khoan"][0]
    assert oa_tk["trang_thai"] == kn.CHUA_CAU_HINH        # chưa có credential
    assert oa_tk["url_webhook"].endswith(f"/webhook/native/zalo-oa/{oa_tk['id']}")
    assert ls[0]["hanh_dong"] == "doi_tuy_chon" and ls[0]["doi_tuong"] == "Trang A"


# ------------------------------------------------------------------ thông báo AI: không lặp

class _Kenh:
    async def can_send_now(self, _ref):
        return True


@pytest.fixture
def kenh(monkeypatch):
    from agent.channels import registry
    from agent.core import tools

    async def lay(_id):
        return _Kenh()

    monkeypatch.setattr(registry, "get_for_account", lay)
    monkeypatch.setattr(tools, "ten_thuong_hieu", lambda: "BLANICA")


def test_hai_tin_toi_cung_luc_chi_mot_thong_bao(csdl_kiem_thu, kenh):
    from agent.omnichannel import thong_bao_ai as tb

    async def ham(db, fb, oa, cid):
        msg = SimpleNamespace(account_id=fb, conversation_ref="k1")
        kq = await asyncio.gather(*(tb.gui_neu_chua(msg, cid) for _ in range(4)))
        n = await db.fetchrow("SELECT count(*) AS n FROM messages WHERE conversation_id = $1 "
                              "AND client_idempotency_key = $2", cid, tb.khoa(cid))
        return kq, n["n"]

    _kq, n = _chay(csdl_kiem_thu, ham)
    assert n == 1, "cùng một phiên hỗ trợ chỉ được báo MỘT lần"


def test_sua_noi_dung_khong_gui_lai_cho_hoi_thoai_da_bao(csdl_kiem_thu, kenh, monkeypatch):
    from agent.omnichannel import thong_bao_ai as tb

    moi = ('Mình là trợ lý AI của {ten}. Cần người thì nhắn "gặp nhân viên" nhé. '
           'Ảnh da là dữ liệu nhạy cảm.')

    async def ham(db, fb, oa, cid):
        msg = SimpleNamespace(account_id=fb, conversation_ref="k1")
        dau = await tb.gui_neu_chua(msg, cid)
        monkeypatch.setattr(cd, "lay", lambda k: moi if k == "TIN_THONG_BAO_AI" else
                            ("bat" if k == "THONG_BAO_AI" else ""))
        lai = await tb.gui_neu_chua(msg, cid)
        # Hội thoại MỚI của cùng kênh thì nhận câu mới.
        kh2 = await db.fetchrow("INSERT INTO contacts (display_name) VALUES ('Mai') RETURNING id")
        d2 = await db.fetchrow("INSERT INTO contact_points (contact_id, channel_account_id, "
                               "external_user_id) VALUES ($1,$2,'k2') RETURNING id", kh2["id"], fb)
        cid2 = await db.fetchrow(
            "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
            "customer_name, contact_id, contact_point_id) VALUES ($1,'facebook','k2','k2','Mai',$2,$3) "
            "RETURNING id", fb, kh2["id"], d2["id"])
        moi_hoi_thoai = await tb.gui_neu_chua(
            SimpleNamespace(account_id=fb, conversation_ref="k2"), cid2["id"])
        rows = await db.fetch("SELECT conversation_id, content FROM messages "
                              "WHERE client_idempotency_key LIKE 'thong_bao_ai:%' ORDER BY created_at")
        return dau, lai, moi_hoi_thoai, rows

    dau, lai, moi_hoi_thoai, rows = _chay(csdl_kiem_thu, ham)
    assert (dau, lai, moi_hoi_thoai) == (True, False, True)
    assert len(rows) == 2
    assert "Mình là trợ lý AI của BLANICA" in rows[1]["content"]
    assert "Mình là" not in rows[0]["content"]
