"""
Quy tắc tự động hoá (agent/omnichannel/tu_dong.py).

Canh ba chốt ghi ở đầu mô-đun:
  1. gửi tin CHỈ bằng mẫu trả lời nhanh, mẫu soi lại cụm cấm LÚC GỬI;
  2. gửi mẫu / tạo việc tối đa MỘT lần mỗi hội thoại cho mỗi quy tắc;
  3. hỏng không chặn tin khách — nhưng cũng không im lặng.
Và một điều không ghi ở đó: danh sách ĐÓNG — khoá lạ là lỗi lúc lưu.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import asyncpg
import pytest

from agent.omnichannel import tu_dong
from agent.omnichannel.tu_dong import NguCanh, QuyTacHong, khop, kiem_dieu_kien, kiem_hanh_dong

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------ kiểm (thuần)

def test_dieu_kien_khoa_la_bi_tu_choi():
    with pytest.raises(QuyTacHong, match="url"):
        kiem_dieu_kien({"url": "http://x"})
    with pytest.raises(QuyTacHong, match="kênh không có"):
        kiem_dieu_kien({"kenh": ["telegram"]})
    with pytest.raises(QuyTacHong):
        kiem_dieu_kien({"ngoai_gio": "co"})          # không phải bool
    with pytest.raises(QuyTacHong):
        kiem_dieu_kien({"chua_tu": []})              # rỗng
    with pytest.raises(QuyTacHong):
        kiem_dieu_kien({"chua_tu": ["a"] * 31})      # quá giới hạn


def test_dieu_kien_chuan_hoa():
    assert kiem_dieu_kien({"chua_tu": [" đổi trả ", ""], "nhan_co": " VIP "}) == {
        "chua_tu": ["đổi trả"], "nhan_co": "vip"}
    assert kiem_dieu_kien({}) == {}


def test_hanh_dong_danh_sach_dong():
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([])
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([{"loai": "goi_webhook", "url": "http://x"}])
    with pytest.raises(QuyTacHong, match="khoá lạ"):
        kiem_hanh_dong([{"loai": "gan_nhan", "nhan": "a", "url": "http://x"}])
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([{"loai": "gan_nhan", "nhan": "a"}] * 6)
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([{"loai": "gui_mau"}])        # thiếu mã tắt
    assert kiem_hanh_dong([{"loai": "gan_nhan", "nhan": " Ngoài Giờ "},
                           {"loai": "gui_mau", "ma_tat": "Chao"}]) == [
        {"loai": "gan_nhan", "nhan": "ngoài giờ"}, {"loai": "gui_mau", "ma_tat": "chao"}]


def test_moi_hanh_dong_mot_lan_deu_co_trong_danh_sach():
    assert tu_dong.MOT_LAN <= set(tu_dong.HANH_DONG)


def _nc(**k) -> NguCanh:
    m = {"kenh": "facebook", "van_ban": "", "ngoai_gio": False, "lan_dau": False, "nhan": set()}
    m.update(k)
    return NguCanh(**m)


def test_khop_la_AND_va_bo_dau():
    dk = {"kenh": ["facebook"], "chua_tu": ["đổi trả"]}
    assert khop(dk, _nc(van_ban="Cho em hỏi DOI TRA thế nào"))
    assert not khop(dk, _nc(van_ban="giá bao nhiêu"))
    assert not khop(dk, _nc(kenh="zalo_oa", van_ban="đổi trả"))
    assert khop({}, _nc())                            # không điều kiện = mọi tin


def test_khop_gio_lan_dau_nhan():
    assert khop({"ngoai_gio": True}, _nc(ngoai_gio=True))
    assert not khop({"ngoai_gio": True}, _nc(ngoai_gio=False))
    assert khop({"lan_dau": True}, _nc(lan_dau=True))
    assert not khop({"lan_dau": False}, _nc(lan_dau=True))
    assert khop({"nhan_co": "vip"}, _nc(nhan={"vip"}))
    assert not khop({"nhan_co": "vip"}, _nc())
    assert not khop({"nhan_khong": "đã chào"}, _nc(nhan={"đã chào"}))


def test_hook_chay_truoc_agent():
    """Quy tắc 'chuyển người' phải chặn agent ngay ở tin này."""
    src = (ROOT / "agent" / "omnichannel" / "xu_ly_tin_vao.py").read_text(encoding="utf-8")
    i = src.index("tu_dong.chay_tin_khach(")
    assert i < src.index("agent_bat.agent_duoc_tra_loi(")
    assert "if tu_dong_kq.dung_agent:" in src[i:i + 200]


# ------------------------------------------------------------ chạy (Postgres thật)

async def _mo(url: str):
    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")

    db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with db._pool.acquire() as conn:
        await conn.execute((ROOT / "agent" / "schema.sql").read_text(encoding="utf-8"))
        await apply_all(conn)
        tk = await conn.fetchval(
            "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
            "VALUES ('facebook','fb','active','fb-1') RETURNING id")
        kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ('Chị Lan') RETURNING id")
        d = await conn.fetchval(
            "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
            "VALUES ($1,$2,'k1') RETURNING id", kh, tk)
        cid = await conn.fetchval(
            "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
            "customer_name, contact_id, contact_point_id) "
            "VALUES ($1,'facebook','k1','k1','Chị Lan',$2,$3) RETURNING id", tk, kh, d)
        await conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES ($1,'customer','alo')", cid)
    return db, tk, cid


async def _v(db, sql, *a):
    r = await db.fetchrow(sql, *a)
    return next(iter(r.values())) if r else None


async def _dong(db):
    await db._pool.close()
    db._pool = None


async def _quy_tac(db, ten, dk, hd, thu_tu=100):
    return await _v(db, 
        "INSERT INTO quy_tac_tu_dong (ten, su_kien, dieu_kien, hanh_dong, thu_tu) "
        "VALUES ($1,'tin_khach',$2::jsonb,$3::jsonb,$4) RETURNING id", ten, dk, hd, thu_tu)


def _msg(tk, text="alo"):
    return SimpleNamespace(channel="facebook", text=text, account_id=tk, conversation_ref="k1")


class _Kenh:
    def __init__(self, duoc=True):
        self.duoc = duoc

    async def can_send_now(self, _ref):
        return self.duoc


@pytest.fixture
def gio_lam(monkeypatch):
    from agent.core import gio_lam_viec
    trong = {"v": True}
    monkeypatch.setattr(gio_lam_viec, "dang_trong_gio", lambda *a, **k: trong["v"])
    return trong


@pytest.fixture
def kenh(monkeypatch):
    from agent.channels import registry
    k = _Kenh()

    async def lay(_id):
        return k
    monkeypatch.setattr(registry, "get_for_account", lay)
    return k


def test_gui_mau_mot_lan_moi_hoi_thoai(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await db.execute("INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES "
                             "('ngoaigio','Dạ shop đã nhận tin, sáng mai em trả lời chị ạ.')")
            await _quy_tac(db, "Chào ngoài giờ", {"ngoai_gio": True},
                           [{"loai": "gan_nhan", "nhan": "ngoài giờ"},
                            {"loai": "gui_mau", "ma_tat": "ngoaigio"}])
            gio_lam["v"] = False
            kq1 = await tu_dong.chay_tin_khach(_msg(tk), cid)
            kq2 = await tu_dong.chay_tin_khach(_msg(tk, "còn đó không"), cid)
            so_tin = await _v(db, 
                "SELECT count(*) FROM outbox_jobs WHERE conversation_id = $1", cid)
            nhan = await _v(db, 
                "SELECT count(*) FROM hoi_thoai_nhan WHERE conversation_id = $1", cid)
            lan = await db.fetch("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay ORDER BY id")
            return kq1, kq2, so_tin, nhan, lan
        finally:
            await _dong(db)

    kq1, kq2, so_tin, nhan, lan = asyncio.run(chay())
    assert "gửi mẫu /ngoaigio" in kq1.da_lam and not kq1.dung_agent
    assert not any("gửi mẫu" in x for x in kq2.da_lam)
    assert so_tin == 1                    # mười tin khách không thành mười câu chào
    assert nhan == 1
    assert [r["ket_qua"] for r in lan] == ["da_lam", "da_lam"]
    assert lan[0]["chi_tiet"]["mot_lan"] is True


def test_khong_khop_thi_khong_lam_gi(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Ngoài giờ", {"ngoai_gio": True},
                           [{"loai": "gan_nhan", "nhan": "x"}])
            gio_lam["v"] = True
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            return kq, await _v(db, "SELECT count(*) FROM quy_tac_lan_chay")
        finally:
            await _dong(db)

    kq, so = asyncio.run(chay())
    assert kq.da_lam == [] and so == 0


def test_chuyen_nguoi_dung_agent_va_tao_viec(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Đổi trả", {"chua_tu": ["đổi trả", "hoàn tiền"]},
                           [{"loai": "chuyen_nguoi", "ly_do": "khách hỏi đổi trả"}])
            kq = await tu_dong.chay_tin_khach(_msg(tk, "Em muốn DOI TRA hàng"), cid)
            await tu_dong.chay_tin_khach(_msg(tk, "hoàn tiền giúp em"), cid)
            conv = await db.fetchrow("SELECT status, mode FROM conversations WHERE id = $1", cid)
            viec = await _v(db, "SELECT count(*) FROM cong_viec WHERE conversation_id = $1", cid)
            su_kien = await _v(db, 
                "SELECT count(*) FROM events WHERE kind = 'conversation.escalated'")
            return kq, conv, viec, su_kien
        finally:
            await _dong(db)

    kq, conv, viec, su_kien = asyncio.run(chay())
    assert kq.dung_agent
    assert (conv["status"], conv["mode"]) == ("escalated", "human")
    assert viec == 1                      # chuyển người mà không có việc là kênh chết im lặng
    assert su_kien == 1                   # tin thứ hai không ghi thêm "chuyển người" giả


def test_mau_bi_sua_thanh_cau_cam_thi_khong_gui(csdl_kiem_thu, gio_lam, kenh):
    """Chốt 1: mẫu được soi LÚC GỬI, không chỉ lúc tạo quy tắc."""
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await db.execute("INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES "
                             "('chao','Serum này đặc trị mụn ạ')")   # sửa thẳng CSDL, lọt qua API
            await _quy_tac(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"}])
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            so_tin = await _v(db, "SELECT count(*) FROM outbox_jobs")
            lan = await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay")
            loi = await _v(db, "SELECT count(*) FROM events WHERE kind = 'tu_dong.loi'")
            return kq, so_tin, lan, loi
        finally:
            await _dong(db)

    kq, so_tin, lan, loi = asyncio.run(chay())
    assert so_tin == 0 and kq.da_lam == []
    assert lan["ket_qua"] == "hong" and "cấm" in lan["chi_tiet"]["loi"]
    assert loi == 1                       # hỏng mà không ai biết là hỏng tệ nhất


def test_ngoai_cua_so_gui_thi_ghi_hong(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await db.execute("INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES ('chao','Dạ chào chị')")
            await _quy_tac(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"}])
            kenh.duoc = False
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            return (await _v(db, "SELECT count(*) FROM outbox_jobs"),
                    await _v(db, "SELECT ket_qua FROM quy_tac_lan_chay"))
        finally:
            await _dong(db)

    assert asyncio.run(chay()) == (0, "hong")


def test_mot_quy_tac_hong_khong_chan_quy_tac_sau(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Hỏng", {}, [{"loai": "gui_mau", "ma_tat": "khongco"}], thu_tu=1)
            await _quy_tac(db, "Gắn nhãn", {}, [{"loai": "gan_nhan", "nhan": "mới"}], thu_tu=2)
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            return kq, await _v(db, "SELECT count(*) FROM hoi_thoai_nhan")
        finally:
            await _dong(db)

    kq, nhan = asyncio.run(chay())
    assert kq.da_lam == ["gắn nhãn mới"] and nhan == 1


def test_csdl_hong_khong_nem(monkeypatch):
    """Chốt 3: kể cả khi CSDL chết, tin của khách vẫn đi tiếp."""
    from agent import db

    async def no(*a, **k):
        raise ConnectionError("CSDL rớt")
    for ten in ("fetch", "fetchrow", "execute", "log_event"):
        monkeypatch.setattr(db, ten, no)
    kq = asyncio.run(tu_dong.chay_tin_khach(_msg(UUID(int=1)), UUID(int=2)))
    assert kq.da_lam == [] and not kq.dung_agent


def test_lan_dau_chi_tin_dau(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Khách mới", {"lan_dau": True}, [{"loai": "gan_nhan", "nhan": "khách mới"}])
            kq1 = await tu_dong.chay_tin_khach(_msg(tk), cid)
            await db.execute("INSERT INTO messages (conversation_id, role, content) "
                             "VALUES ($1,'customer','tin 2')", cid)
            kq2 = await tu_dong.chay_tin_khach(_msg(tk, "tin 2"), cid)
            return kq1, kq2
        finally:
            await _dong(db)

    kq1, kq2 = asyncio.run(chay())
    assert kq1.da_lam == ["gắn nhãn khách mới"] and kq2.da_lam == []
