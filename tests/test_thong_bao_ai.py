"""
Thông báo khách đang nói với AI + giữ lời hứa "nhắn gặp nhân viên".

NĐ 356/2025 Điều 10 khoản 3 (xử lý tự động: báo và cho lựa chọn), Điều 6
khoản 4 (báo dữ liệu nhạy cảm). Hai nửa không tách được: câu thông báo hứa
một lối thoát, và lối thoát ấy phải có thật trong mã.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest

from agent.omnichannel import thong_bao_ai as tb

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("cau", [
    "cho em gặp nhân viên", "Gặp nhân viên!", "gap nhan vien", "em muốn nói chuyện với người thật",
    "nói chuyện với nhân viên được không", "bạn có phải bot không, cho gặp người", "GẶP NGƯỜI",
    "em không muốn nói chuyện với AI",
])
def test_doi_gap_nguoi(cau):
    assert tb.khach_doi_gap_nguoi(cau), cau


@pytest.mark.parametrize("cau", [
    "nhân viên giao hàng chưa tới ạ", "serum này có hàng thật không", "giá bao nhiêu",
    "kem chống nắng dùng cho người da dầu được không", "", "hàng chính hãng hay hàng thật vậy",
    # Rà soát 28.10.2026 — bản cũ bắt nhầm những câu này sau khi bỏ dấu:
    "có ảnh feedback người thật không", "không phải bột đúng không ạ",
    "nhiều người thất vọng về mẫu cũ", "nhân viên thật nhiệt tình",
    "em không muốn nói chuyện với ai cả, chỉ hỏi giá",
])
def test_khong_nham(cau):
    assert not tb.khach_doi_gap_nguoi(cau), cau


def test_cau_thong_bao_giu_loi_hua_co_trong_ma():
    """Câu thông báo nhắc cụm nào thì cụm đó PHẢI kích hoạt chuyển người."""
    from agent.config import Settings

    mac_dinh = Settings.model_fields["tin_thong_bao_ai"].default
    assert '"gặp nhân viên"' in mac_dinh and tb.khach_doi_gap_nguoi("gặp nhân viên")
    assert "trợ lý AI" in mac_dinh and "nhạy cảm" in mac_dinh
    assert "24/7" not in mac_dinh           # chế độ Gợi ý: ban đêm không ai duyệt
    assert Settings.model_fields["thong_bao_ai"].default == "bat"


def test_thu_tu_trong_luong_tin_vao():
    """
    Đòi gặp người: SAU chốt agent_bat (agent tắt thì người đã tiếp rồi),
    TRƯỚC agent. Thông báo AI: chỉ ngay trước lúc agent trả lời — mọi nhánh
    phía trên là lúc người tiếp khách, "em là trợ lý AI" khi ấy là nói sai.
    """
    src = (ROOT / "agent" / "omnichannel" / "xu_ly_tin_vao.py").read_text(encoding="utf-8")
    i_bat = src.index("agent_bat.agent_duoc_tra_loi(")
    i_doi = src.index("thong_bao_ai.khach_doi_gap_nguoi(")
    i_anh = src.index("if msg.attachments and not msg.text.strip():")
    i_tb = src.index("thong_bao_ai.gui_neu_chua(")
    i_ls = src.index("history = await _history(cid)")
    assert i_bat < i_doi < i_anh < i_tb < i_ls


# ------------------------------------------------------------------ Postgres

class _Kenh:
    def __init__(self, duoc=True):
        self.duoc = duoc

    async def can_send_now(self, _ref):
        return self.duoc


async def _mo(url):
    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with db._pool.acquire() as conn:
        await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
        await apply_all(conn)
        tk = await conn.fetchval("INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
                                 "VALUES ('facebook','fb','active','fb-tb') RETURNING id")
        kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ('Lan') RETURNING id")
        d = await conn.fetchval("INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
                                "VALUES ($1,$2,'k1') RETURNING id", kh, tk)
        cid = await conn.fetchval(
            "INSERT INTO conversations (account_id, channel, external_id, customer_ref, customer_name, "
            "contact_id, contact_point_id) VALUES ($1,'facebook','k1','k1','Lan',$2,$3) RETURNING id", tk, kh, d)
    return db, tk, cid


@pytest.fixture
def kenh(monkeypatch):
    from agent.channels import registry
    k = _Kenh()

    async def lay(_id):
        return k
    monkeypatch.setattr(registry, "get_for_account", lay)
    return k


def test_gui_mot_lan_moi_hoi_thoai(csdl_kiem_thu, kenh, monkeypatch):
    from agent.core import tools
    monkeypatch.setattr(tools, "ten_thuong_hieu", lambda: "BLANICA")

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            msg = SimpleNamespace(account_id=tk, conversation_ref="k1")
            a = await tb.gui_neu_chua(msg, cid)
            b = await tb.gui_neu_chua(msg, cid)
            rows = await db.fetch("SELECT content FROM messages WHERE conversation_id = $1 "
                                  "AND client_idempotency_key = $2", cid, tb.khoa(cid))
            return a, b, [r["content"] for r in rows]
        finally:
            await db._pool.close()
            db._pool = None

    a, b, noi_dung = asyncio.run(chay())
    assert (a, b) == (True, False)
    assert len(noi_dung) == 1 and "trợ lý AI của BLANICA" in noi_dung[0]


def test_tat_thi_khong_gui(csdl_kiem_thu, kenh, monkeypatch):
    from agent import cau_hinh_dong
    monkeypatch.setattr(cau_hinh_dong, "lay", lambda k: "tat" if k == "THONG_BAO_AI" else "")

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            return await tb.gui_neu_chua(SimpleNamespace(account_id=tk, conversation_ref="k1"), cid)
        finally:
            await db._pool.close()
            db._pool = None

    assert asyncio.run(chay()) is False


def test_hong_khong_nem(monkeypatch):
    from uuid import UUID

    from agent import db

    async def no(*a, **k):
        raise ConnectionError("CSDL rớt")
    for ten in ("fetchrow", "log_event"):
        monkeypatch.setattr(db, ten, no)
    assert asyncio.run(tb.gui_neu_chua(SimpleNamespace(account_id=UUID(int=1), conversation_ref="x"),
                                       UUID(int=2))) is False


def test_san_sang():
    from scripts.san_sang import CANH_BAO, DU, doc_thong_bao_ai

    assert doc_thong_bao_ai("bat")["muc"] == DU
    assert doc_thong_bao_ai("tat")["muc"] == CANH_BAO



def test_lua_chon_gap_nguoi_duoc_nho_khi_mo_lai_hoi_thoai():
    """Mở lại hội thoại đã giải quyết thì agent không tự trả lời lại người vừa đòi gặp người."""
    src = (ROOT / "agent" / "omnichannel" / "xu_ly_tin_vao.py").read_text(encoding="utf-8")
    i = src.index("thong_bao_ai.khach_doi_gap_nguoi(")
    assert "await thong_bao_ai.da_doi_gap_nguoi(cid)" in src[i:i + 300]
    assert "SU_KIEN_DOI_GAP_NGUOI" in src[i:i + 500]
