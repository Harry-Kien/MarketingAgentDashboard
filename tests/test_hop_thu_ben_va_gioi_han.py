"""
Hộp thư bền (tin khách vào Postgres TRƯỚC khi trả 200) và giới hạn tần suất
webchat — rà soát 13.11.2026.

Lỗ cũ: mọi webhook trả 200 rồi mới xử lý trong BackgroundTasks; app chết
đúng lúc đó là tin biến mất, hãng không gửi lại vì đã nhận 200.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.channels.base import InboundMessage  # noqa: E402
from agent.core.gioi_han import GioiHanTanSuat  # noqa: E402
from agent.omnichannel import hop_thu_ben  # noqa: E402


def _tin(khoa: str = "zalo:m1") -> InboundMessage:
    return InboundMessage(
        account_id=uuid4(), channel="zalo_personal", conversation_ref="t1",
        customer_ref="c1", customer_name="Lan", text="còn hàng không ạ",
        dedupe_key=khoa, received_at=datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc),
        attachments=[{"loai": "image", "url": "https://x/1.jpg"}], meta={"thread_type": 0})


# ---------------------------------------------------------------- phần thuần

def test_ghi_va_doc_lai_tin_khong_mat_truong_nao():
    m = _tin()
    assert hop_thu_ben.tu_json(hop_thu_ben.ra_json(m)) == m


def test_thu_lai_gian_cach_co_tran():
    assert [hop_thu_ben.tre_lan_sau(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 80]
    assert hop_thu_ben.tre_lan_sau(20) == 600


def test_moi_webhook_ghi_ben_truoc_khi_tra_loi():
    """Không còn chỗ nào đẩy thẳng handle_inbound vào BackgroundTasks."""
    con_cu = []
    for p in (ROOT / "agent").rglob("*.py"):
        s = p.read_text(encoding="utf-8")
        if re.search(r"add_task\(\s*xu_ly_tin_vao\.handle_inbound", s):
            con_cu.append(str(p.relative_to(ROOT)))
    assert con_cu == []
    so = sum(p.read_text(encoding="utf-8").count("await hop_thu_ben.nhan(")
             for p in (ROOT / "agent").rglob("*.py"))
    assert so >= 7          # Meta ×2, webchat, Zalo OA, Zalo cá nhân, đường cũ ×2


def test_vong_nen_hop_thu_duoc_bat():
    import inspect

    import agent.main as m
    assert "hop_thu_ben_loop(" in inspect.getsource(m.lifespan)


def test_gioi_han_cua_so_truot():
    gio = [0.0]
    gh = GioiHanTanSuat(3, 60, dong_ho=lambda: gio[0])
    assert [gh.cho_phep("a") for _ in range(4)] == [True, True, True, False]
    assert gh.cho_phep("b") is True                 # khoá khác không bị ảnh hưởng
    assert 1 <= gh.con_cho("a") <= 61
    gio[0] = 60.0
    assert gh.cho_phep("a") is True                 # hết cửa sổ thì được tiếp


def test_gioi_han_don_khoa_cu_khong_phinh_bo_nho():
    gio = [0.0]
    gh = GioiHanTanSuat(1, 10, dong_ho=lambda: gio[0])
    for i in range(20_001):
        gh.cho_phep(f"ip{i}")
    gio[0] = 100.0
    gh.cho_phep("moi")
    assert len(gh._dem) < 100


def test_gia_dinh_mot_tien_trinh():
    """Bộ đếm trong bộ nhớ chỉ đúng khi chỉ có MỘT tiến trình phục vụ."""
    lenh = [d for d in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
            if d.strip() and not d.lstrip().startswith("#")]
    assert not any("--workers" in d for d in lenh)
    assert any("uvicorn" in d for d in lenh)


# ---------------------------------------------------------------- Postgres thật

def _sql(url: str, sql: str, *a):
    import asyncpg

    async def chay():
        conn = await asyncpg.connect(url)
        try:
            return await conn.fetchrow(sql, *a)
        finally:
            await conn.close()
    return asyncio.run(chay())


def _chay(url: str, ham, *a):
    from tests.test_giai_quyet_csat import _goi
    return _goi(url, ham, *a)


@pytest.fixture
def csdl(csdl_kiem_thu):
    from fastapi.testclient import TestClient

    from tests.conftest import nguoi_thu
    from tests.test_giai_quyet_csat import Q, _app
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*Q))):
        pass
    return csdl_kiem_thu


def test_ghi_ben_va_chong_trung_khi_hang_phat_lai(csdl):
    m = _tin("zalo:trung")
    id1 = _chay(csdl, hop_thu_ben.nhan, m)
    assert id1 is not None
    assert _chay(csdl, hop_thu_ben.nhan, m) is None          # hãng gửi lại
    r = _sql(csdl, "SELECT trang_thai, payload->>'text' AS t FROM tin_vao WHERE id=$1", id1)
    assert r["trang_thai"] == "cho" and r["t"] == "còn hàng không ạ"


def test_xu_ly_thanh_cong_thi_xong(csdl, monkeypatch):
    from agent.omnichannel import xu_ly_tin_vao

    nhan_duoc = []

    async def ok(msg):
        nhan_duoc.append(msg.dedupe_key)
    monkeypatch.setattr(xu_ly_tin_vao, "handle_inbound", ok)
    id_ = _chay(csdl, hop_thu_ben.nhan, _tin("zalo:ok"))
    assert _chay(csdl, hop_thu_ben.xu_ly_mot, id_) == "xong"
    assert nhan_duoc == ["zalo:ok"]
    assert _chay(csdl, hop_thu_ben.xu_ly_mot, id_) == "bo_qua"   # không xử lý hai lần


def test_hong_thi_thu_lai_roi_chet_va_bao_dong(csdl, monkeypatch):
    from agent import canh_gac
    from agent.omnichannel import xu_ly_tin_vao

    async def hong(msg):
        raise RuntimeError("CSDL chập chờn")
    bao = []

    async def ghi_bao(chi_tiet, **kw):
        bao.append(chi_tiet)
    monkeypatch.setattr(xu_ly_tin_vao, "handle_inbound", hong)
    monkeypatch.setattr(canh_gac, "bao_dong", ghi_bao)
    id_ = _chay(csdl, hop_thu_ben.nhan, _tin("zalo:hong"))
    assert _chay(csdl, hop_thu_ben.xu_ly_mot, id_) == "cho"
    r = _sql(csdl, "SELECT so_lan_thu, cho_den > now() AS hoan, loi FROM tin_vao WHERE id=$1", id_)
    assert r["so_lan_thu"] == 1 and r["hoan"] and "chập chờn" in r["loi"]
    # Lần cuối: đặt sẵn số lần đã thử và cho tới lượt ngay.
    _sql(csdl, "UPDATE tin_vao SET so_lan_thu=$2, cho_den=now() WHERE id=$1 RETURNING 1",
         id_, hop_thu_ben.SO_LAN_TOI_DA - 1)
    assert _chay(csdl, hop_thu_ben.xu_ly_mot, id_) == "chet"
    assert bao and "KHÔNG xử lý được" in bao[0]


def test_app_chet_giua_chung_thi_vong_nen_nhat_lai(csdl, monkeypatch):
    """Dòng `dang_xu_ly` của một tiến trình đã chết được chạy lại."""
    from agent.omnichannel import xu_ly_tin_vao

    nhan_duoc = []

    async def ok(msg):
        nhan_duoc.append(msg.dedupe_key)
    monkeypatch.setattr(xu_ly_tin_vao, "handle_inbound", ok)
    id_ = _chay(csdl, hop_thu_ben.nhan, _tin("zalo:bo-do"))
    _sql(csdl, "UPDATE tin_vao SET trang_thai='dang_xu_ly', so_lan_thu=1, "
               "khoa_luc = now() - interval '20 minutes' WHERE id=$1 RETURNING 1", id_)
    assert _chay(csdl, hop_thu_ben.quet_mot_luot) == {"xong": 1}
    assert nhan_duoc == ["zalo:bo-do"]


def test_don_tin_da_xong_cu(csdl):
    id_ = _chay(csdl, hop_thu_ben.nhan, _tin("zalo:cu"))
    _sql(csdl, "UPDATE tin_vao SET trang_thai='xong', updated_at = now() - interval '5 days' "
               "WHERE id=$1 RETURNING 1", id_)
    _chay(csdl, hop_thu_ben.don_cu)
    assert _sql(csdl, "SELECT 1 FROM tin_vao WHERE id=$1", id_) is None


# ---------------------------------------------------------------- đầu-cuối trên app thật

def test_tin_webchat_nam_trong_csdl_du_xu_ly_nen_khong_chay(app_that, monkeypatch):
    """
    Mô phỏng app chết NGAY sau khi trả 202: việc nền không chạy. Tin vẫn nằm
    trong `tin_vao`, và vòng nền đưa nó vào hộp thư như thường.
    """
    from agent import db
    from tests.test_nghiem_thu_saas import _kenh_webchat, _khach_nhan, _quan_tri_vao, _sql as goi

    async def chet(_id):
        return "bo_qua"
    monkeypatch.setattr(hop_thu_ben, "xu_ly_mot", chet)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "Shop còn kem chống nắng không?")

    async def dem():
        return (await db.fetchrow("SELECT count(*) n FROM tin_vao WHERE trang_thai='cho'"))["n"], \
               (await db.fetchrow("SELECT count(*) n FROM messages WHERE content LIKE '%kem chống nắng%'"))["n"]
    assert goi(app_that, dem) == (1, 0)

    monkeypatch.undo()
    goi(app_that, hop_thu_ben.quet_mot_luot)
    assert goi(app_that, dem) == (0, 1)


def test_webchat_qua_nhanh_thi_429(app_that):
    from fastapi.testclient import TestClient  # noqa: F401
    from tests.test_nghiem_thu_saas import GOC_WEB, _kenh_webchat, _quan_tri_vao

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    app_that.cookies.clear()
    ve = app_that.post(f"/webchat/{tk}/session", json={}, headers={"Origin": GOC_WEB}).json()["token"]
    ma = []
    for i in range(22):
        r = app_that.post(f"/webchat/{tk}/messages",
                          json={"client_message_id": str(uuid4()), "text": f"tin {i}"},
                          headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ve}"})
        ma.append(r.status_code)
    assert ma[:20] == [202] * 20 and ma[20] == 429
    assert "Retry-After" in r.headers
