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
from datetime import datetime, timedelta, timezone
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
        # Nhãn chữ trong các quy tắc CŨ bên dưới phải có trong danh mục
        # (0056): khoá cũ còn sót được tra theo tên, không tự tạo nhãn.
        await conn.execute(
            "INSERT INTO nhan (loai, ten) VALUES ('hoi_thoai','ngoài giờ'), "
            "('hoi_thoai','mới'), ('hoi_thoai','khách mới'), ('hoi_thoai','x')")
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
                "SELECT count(*) FROM hoi_thoai_gan_nhan WHERE conversation_id = $1", cid)
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


def test_chuyen_nguoi_dung_agent_va_bao_nhan_vien(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Đổi trả", {"chua_tu": ["đổi trả", "hoàn tiền"]},
                           [{"loai": "chuyen_nguoi", "ly_do": "khách hỏi đổi trả"}])
            # Một quản trị để chuông có người nhận (kênh chưa có thành viên ->
            # lui về người quản lý).
            qt = await _v(db, "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam) "
                              "VALUES ('qt', 'x') RETURNING id")
            await db.execute("INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
                             "SELECT $1, id FROM vai_tro WHERE ten = 'Quản trị'", qt)
            kq = await tu_dong.chay_tin_khach(_msg(tk, "Em muốn DOI TRA hàng"), cid)
            await tu_dong.chay_tin_khach(_msg(tk, "hoàn tiền giúp em"), cid)
            conv = await db.fetchrow("SELECT status, mode FROM conversations WHERE id = $1", cid)
            viec = await _v(db, "SELECT count(*) FROM cong_viec WHERE conversation_id = $1", cid)
            bao = await _v(db, "SELECT count(*) FROM thong_bao WHERE conversation_id = $1 "
                               "AND loai = 'ai_chuyen_giao'", cid)
            su_kien = await _v(db, 
                "SELECT count(*) FROM events WHERE kind = 'conversation.escalated'")
            return kq, conv, viec, bao, su_kien
        finally:
            await _dong(db)

    kq, conv, viec, bao, su_kien = asyncio.run(chay())
    assert kq.dung_agent
    assert (conv["status"], conv["mode"]) == ("escalated", "human")
    assert viec == 0                      # mục 14.2: chuyển người không sinh việc
    assert bao == 1                       # chuyển người mà không báo ai là kênh chết im lặng
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
            return kq, await _v(db, "SELECT count(*) FROM hoi_thoai_gan_nhan")
        finally:
            await _dong(db)

    kq, nhan = asyncio.run(chay())
    assert kq.da_lam == ["gắn nhãn hội thoại mới"] and nhan == 1


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
    assert kq1.da_lam == ["gắn nhãn hội thoại khách mới"] and kq2.da_lam == []


# ------------------------------------------------------------------ nhãn theo danh mục (0056)

def test_khop_tach_nhan_hoi_thoai_va_nhan_khach():
    """Cùng một id nhưng khác loại ô thì không khớp — hai loại độc lập."""
    a, b = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
    assert khop({"nhan_hoi_thoai_co": [a, b]}, _nc(nhan_hoi_thoai={b}))
    assert not khop({"nhan_hoi_thoai_co": [a]}, _nc(nhan_khach={a}))
    assert khop({"nhan_khach_co": [a]}, _nc(nhan_khach={a}))
    assert not khop({"nhan_khach_khong": [a, b]}, _nc(nhan_khach={b}))
    assert khop({"nhan_hoi_thoai_khong": [a]}, _nc(nhan_hoi_thoai={b}, nhan_khach={a}))


def test_kiem_khoa_nhan_moi():
    a = "11111111-1111-1111-1111-111111111111"
    assert kiem_dieu_kien({"nhan_khach_co": [a.upper(), a]}) == {"nhan_khach_co": [a]}
    with pytest.raises(QuyTacHong, match="id nhãn"):
        kiem_dieu_kien({"nhan_hoi_thoai_co": ["vip"]})
    with pytest.raises(QuyTacHong):
        kiem_dieu_kien({"nhan_khach_co": []})
    assert kiem_hanh_dong([{"loai": "gan_nhan_khach", "nhan_id": a}]) == [
        {"loai": "gan_nhan_khach", "nhan_id": a}]
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([{"loai": "gan_nhan_khach"}])


def test_gan_nhan_khach_theo_dieu_kien_nhan_hoi_thoai(csdl_kiem_thu, gio_lam, kenh):
    """
    Điều kiện đọc nhãn HỘI THOẠI, hành động gắn nhãn KHÁCH lên hồ sơ của
    hội thoại — và nhãn đã ngừng thì lần chạy ghi hỏng có lý do, không im.
    """
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            ht = await _v(db, "INSERT INTO nhan (loai, ten) VALUES ('hoi_thoai','khiếu nại') "
                              "RETURNING id::text")
            kh = await _v(db, "INSERT INTO nhan (loai, ten) VALUES ('khach','hay khiếu nại') "
                              "RETURNING id::text")
            await _quy_tac(db, "Đánh dấu khách", {"nhan_hoi_thoai_co": [ht]},
                           [{"loai": "gan_nhan_khach", "nhan_id": kh}])
            kq0 = await tu_dong.chay_tin_khach(_msg(tk), cid)         # chưa có nhãn hội thoại
            await db.execute("INSERT INTO hoi_thoai_gan_nhan (conversation_id, nhan_id) "
                             "VALUES ($1,$2::uuid)", cid, ht)
            kq1 = await tu_dong.chay_tin_khach(_msg(tk), cid)
            gan = await _v(db, "SELECT count(*) FROM khach_gan_nhan g JOIN conversations c "
                               "ON c.contact_id = g.contact_id WHERE c.id = $1", cid)
            su_kien = await _v(db, "SELECT actor FROM events WHERE kind = 'nhan.gan_khach'")
            await db.execute("DELETE FROM khach_gan_nhan")
            await db.execute("UPDATE nhan SET dang_dung = false WHERE id = $1::uuid", kh)
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            hong = await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay "
                                     "ORDER BY id DESC LIMIT 1")
            return kq0, kq1, gan, su_kien, hong
        finally:
            await _dong(db)

    kq0, kq1, gan, su_kien, hong = asyncio.run(chay())
    assert kq0.da_lam == []
    assert kq1.da_lam == ["gắn nhãn khách hay khiếu nại"] and gan == 1
    assert su_kien == "tu_dong"
    assert hong["ket_qua"] == "hong" and "ngừng" in hong["chi_tiet"]["loi"]


def test_khoa_cu_nhan_chu_khong_co_trong_danh_muc_thi_ghi_hong(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Cũ", {}, [{"loai": "gan_nhan", "nhan": "chưa từng tạo"}])
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            return (await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay"),
                    await _v(db, "SELECT count(*) FROM nhan WHERE ten = 'chưa từng tạo'"))
        finally:
            await _dong(db)

    lan, tao = asyncio.run(chay())
    assert lan["ket_qua"] == "hong" and "không có trong danh mục" in lan["chi_tiet"]["loi"]
    assert tao == 0, "quy tắc không được tự tạo nhãn chữ tự do"



# ------------------------------------------------------------------ rà soát 28.10.2026

def test_mau_hong_van_chuyen_nguoi(csdl_kiem_thu, gio_lam, kenh):
    """
    Bản cũ: mẫu bị xoá → cả quy tắc huỷ → "chuyển người" không chạy → AGENT
    trả lời đúng người cửa hàng muốn giao cho nhân viên.
    """
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Đổi trả", {}, [{"loai": "gui_mau", "ma_tat": "da_bi_xoa"},
                                               {"loai": "chuyen_nguoi", "ly_do": "đổi trả"}])
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            lan = await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay")
            return kq, lan
        finally:
            await _dong(db)

    kq, lan = asyncio.run(chay())
    assert kq.dung_agent is True
    assert lan["ket_qua"] == "da_lam" and "chuyển người" in lan["chi_tiet"]["lam"]
    assert "da_bi_xoa" in lan["chi_tiet"]["loi"]


def test_nguoi_dang_tiep_thi_khong_gui_mau(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await db.execute("INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES ('chao','Dạ chào chị')")
            await _quy_tac(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"}])
            await tu_dong.chay_tin_khach(_msg(tk), cid, nguoi_dang_tiep=True)
            return (await _v(db, "SELECT count(*) FROM outbox_jobs"),
                    await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay"))
        finally:
            await _dong(db)

    so, lan = asyncio.run(chay())
    assert so == 0 and lan["ket_qua"] == "bo_qua" and lan["chi_tiet"]["bo_qua"]


def test_tao_viec_dung_tieu_de_va_nguon_tu_dong(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            # Hội thoại ĐÃ có một việc agent đang mở: bản cũ vẫn ghi "đã tạo việc".
            await db.execute("INSERT INTO cong_viec (tieu_de, nguon, conversation_id) "
                             "VALUES ('Khách cần người trả lời', 'agent', $1)", cid)
            await _quy_tac(db, "Gọi lại", {}, [{"loai": "tao_viec", "tieu_de": "Gọi lại khách đêm"}])
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            return [dict(r) for r in await db.fetch(
                "SELECT tieu_de, nguon FROM cong_viec WHERE conversation_id = $1 ORDER BY tao_luc", cid)]
        finally:
            await _dong(db)

    viec = asyncio.run(chay())
    assert {"tieu_de": "Gọi lại khách đêm", "nguon": "tu_dong"} in viec


def test_chuyen_nguoi_bao_ca_khach_va_nhan_vien(csdl_kiem_thu, gio_lam, kenh, monkeypatch):
    from agent.omnichannel import xu_ly_tin_vao

    goi: list[str] = []

    async def bao_nv(*a, **k):
        goi.append("nhan_vien")

    async def bao_khach(*a, **k):
        goi.append("khach")
    monkeypatch.setattr(xu_ly_tin_vao, "bao_nhan_vien_tiep_quan", bao_nv)
    monkeypatch.setattr(xu_ly_tin_vao, "bao_khach_dang_chuyen_nguoi", bao_khach)

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac(db, "Chuyển", {}, [{"loai": "chuyen_nguoi"}])
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            await tu_dong.chay_tin_khach(_msg(tk, "còn đó không"), cid)   # đã ở chế độ người
            return await db.fetchrow("SELECT outcome FROM conversations WHERE id = $1", cid)
        finally:
            await _dong(db)

    c = asyncio.run(chay())
    assert goi == ["nhan_vien", "khach"] and c["outcome"] == "escalated"


def test_tieu_de_viec_qua_ngan_bi_chan_luc_luu():
    with pytest.raises(QuyTacHong):
        kiem_hanh_dong([{"loai": "tao_viec", "tieu_de": "ab"}])


# ------------------------------------------------------------------ thứ tự & xung đột (0060)
#
# Chính sách ở đầu agent/omnichannel/tu_dong.py. Mỗi điều một test: một
# chính sách không có test canh là chính sách sẽ bị "dọn" mất.

async def _quy_tac2(db, ten, dk, hd, thu_tu=100, **co):
    """Như `_quy_tac`, thêm cờ 0060 và (tuỳ) `tao_luc` / `id` để thử thứ tự."""
    cot = ["ten", "su_kien", "dieu_kien", "hanh_dong", "thu_tu"]
    gt: list = [ten, "tin_khach", dk, hd, thu_tu]
    for k in ("dung_xet_sau", "cho_ai_tra_loi", "tao_luc", "id"):
        if k in co:
            cot.append(k)
            gt.append(co[k])
    giu = ", ".join(f"${i + 1}" + ("::jsonb" if c in ("dieu_kien", "hanh_dong") else "")
                    for i, c in enumerate(cot))
    return await _v(db, f"INSERT INTO quy_tac_tu_dong ({', '.join(cot)}) VALUES ({giu}) "
                        "RETURNING id", *gt)


async def _mau(db, **ds):
    for ma, nd in ds.items():
        await db.execute("INSERT INTO tra_loi_nhanh (ma_tat, noi_dung) VALUES ($1,$2)", ma, nd)


async def _lan(db, qid):
    r = await db.fetchrow("SELECT ket_qua, chi_tiet FROM quy_tac_lan_chay WHERE quy_tac_id = $1 "
                          "ORDER BY id DESC LIMIT 1", qid)
    return None if r is None else (r["ket_qua"], r["chi_tiet"])


async def _tin_tu_dong(db, cid):
    return [r["content"] for r in await db.fetch(
        "SELECT content FROM messages WHERE conversation_id = $1 AND role = 'system' "
        "ORDER BY created_at", cid)]


def test_nhieu_quy_tac_khop_khach_nhan_mot_tin_nhan_gop(csdl_kiem_thu, gio_lam, kenh):
    """
    Chính sách a + b: hai quy tắc cùng khớp, cùng muốn gửi — khách nhận
    MỘT tin (của quy tắc ưu tiên hơn); nhãn của cả hai đều được gắn; quy
    tắc bị nhường ghi rõ VÌ SAO không gửi.
    """
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.", gia="Dạ giá serum 350.000đ ạ.")
            ht = await _v(db, "INSERT INTO nhan (loai, ten) VALUES ('hoi_thoai','hỏi giá') "
                              "RETURNING id::text")
            b = await _quy_tac2(db, "Hỏi giá", {"chua_tu": ["giá"]},
                                [{"loai": "gui_mau", "ma_tat": "gia"},
                                 {"loai": "gan_nhan_hoi_thoai", "nhan_id": ht}], thu_tu=20)
            a = await _quy_tac2(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"},
                                                 {"loai": "gan_nhan", "nhan": "mới"}], thu_tu=10)
            kq = await tu_dong.chay_tin_khach(_msg(tk, "shop ơi giá serum"), cid)
            return (kq, await _tin_tu_dong(db, cid), await _lan(db, a), await _lan(db, b),
                    await _v(db, "SELECT count(*) FROM hoi_thoai_gan_nhan WHERE conversation_id = $1",
                             cid))
        finally:
            await _dong(db)

    kq, tin, lan_a, lan_b, so_nhan = asyncio.run(chay())
    assert tin == ["Dạ shop chào chị ạ."], "hai quy tắc cùng khớp mà khách nhận hai câu"
    assert kq.da_gui_khach and kq.quy_tac_gui == "Chào" and kq.ai_nhuong
    assert so_nhan == 2, "nhãn của quy tắc bị nhường phải vẫn được gắn (gộp)"
    assert lan_a[0] == "da_lam" and lan_a[1]["ai_nhuong"] is True
    assert lan_b[0] == "da_lam" and "Chào" in lan_b[1]["bo_qua"][0]
    # Mẫu của B CHƯA gửi — tin sau nó vẫn còn quyền gửi (một-lần theo từng loại).
    assert "gui_mau" not in lan_b[1].get("mot_lan_loai", [])


def test_thu_tu_on_dinh_cung_so_uu_tien(csdl_kiem_thu, gio_lam, kenh):
    """Cùng `thu_tu`: tạo trước chạy trước; cùng lúc tạo: theo id."""
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, mot="Một.", hai="Hai.", ba="Ba.")
            await _quy_tac2(db, "Tạo sau", {}, [{"loai": "gui_mau", "ma_tat": "mot"}], thu_tu=5)
            await _quy_tac2(db, "Tạo trước", {}, [{"loai": "gui_mau", "ma_tat": "hai"}], thu_tu=5,
                            tao_luc=datetime.now(timezone.utc) - timedelta(hours=1))
            kq1 = await tu_dong.chay_tin_khach(_msg(tk), cid)
            await db.execute("DELETE FROM quy_tac_tu_dong")
            luc = datetime.now(timezone.utc)
            await _quy_tac2(db, "id lớn", {}, [{"loai": "gui_mau", "ma_tat": "mot"}], thu_tu=1,
                            tao_luc=luc, id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"))
            await _quy_tac2(db, "id nhỏ", {}, [{"loai": "gui_mau", "ma_tat": "ba"}], thu_tu=1,
                            tao_luc=luc, id=UUID("00000000-0000-0000-0000-00000000000a"))
            kq2 = await tu_dong.chay_tin_khach(_msg(tk), cid)
            return kq1, kq2
        finally:
            await _dong(db)

    kq1, kq2 = asyncio.run(chay())
    assert kq1.quy_tac_gui == "Tạo trước"
    assert kq2.quy_tac_gui == "id nhỏ"


def test_dung_xet_quy_tac_sau(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            a = await _quy_tac2(db, "Khiếu nại", {"chua_tu": ["khiếu nại"]},
                                [{"loai": "gan_nhan", "nhan": "x"}], thu_tu=1, dung_xet_sau=True)
            b = await _quy_tac2(db, "Mọi tin", {}, [{"loai": "gan_nhan", "nhan": "mới"}], thu_tu=2)
            await tu_dong.chay_tin_khach(_msg(tk, "em muốn khiếu nại"), cid)
            dung = (await _lan(db, a), await _lan(db, b))
            await tu_dong.chay_tin_khach(_msg(tk, "giá bao nhiêu"), cid)   # A không khớp
            return dung, await _lan(db, b)
        finally:
            await _dong(db)

    (lan_a, lan_b), lan_b2 = asyncio.run(chay())
    assert lan_a[0] == "da_lam" and lan_a[1]["dung_xet_sau"] is True
    assert lan_b is None, "quy tắc xếp sau vẫn được xét dù quy tắc trước bật «dừng xét»"
    assert lan_b2 is not None and lan_b2[0] == "da_lam", "không khớp thì cờ dừng không có tác dụng"


def test_mau_cua_quy_tac_chuyen_nguoi_la_cau_bao(csdl_kiem_thu, gio_lam, kenh, monkeypatch):
    """
    Quy tắc [chuyển người, gửi mẫu] — thứ tự nào cũng vậy: khách nhận MẪU,
    không nhận thêm câu báo chuyển người cố định; nhân viên vẫn được báo.
    """
    from agent.omnichannel import xu_ly_tin_vao

    goi: list[str] = []

    async def bao_nv(*a, **k):
        goi.append("nhan_vien")

    async def bao_khach(*a, **k):
        goi.append("khach")
    monkeypatch.setattr(xu_ly_tin_vao, "bao_nhan_vien_tiep_quan", bao_nv)
    monkeypatch.setattr(xu_ly_tin_vao, "bao_khach_dang_chuyen_nguoi", bao_khach)

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, doitra="Dạ em chuyển chị sang bạn phụ trách đổi trả ạ.")
            await _quy_tac2(db, "Đổi trả", {}, [{"loai": "chuyen_nguoi", "ly_do": "đổi trả"},
                                                {"loai": "gui_mau", "ma_tat": "doitra"}])
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            return kq, await _tin_tu_dong(db, cid)
        finally:
            await _dong(db)

    kq, tin = asyncio.run(chay())
    assert kq.dung_agent and kq.da_gui_khach
    assert tin == ["Dạ em chuyển chị sang bạn phụ trách đổi trả ạ."]
    assert goi == ["nhan_vien"], "khách nhận cả mẫu lẫn câu báo chuyển người"


@pytest.mark.parametrize("chuyen_truoc", [True, False])
def test_chuyen_nguoi_uu_tien_hon_thi_mau_sau_nhuong(csdl_kiem_thu, gio_lam, kenh, monkeypatch,
                                                    chuyen_truoc):
    """
    Quy tắc chuyển người xếp TRƯỚC: câu báo chuyển người là tin duy nhất;
    mẫu chào của quy tắc xếp sau nhường. Và ngược lại: mẫu xếp trước thì
    quy tắc chuyển người sau KHÔNG gửi thêm câu báo (ghi lý do).
    """
    from agent.omnichannel import xu_ly_tin_vao

    goi: list[str] = []

    async def bao_nv(*a, **k):
        goi.append("nhan_vien")

    async def bao_khach(*a, **k):
        goi.append("khach")
    monkeypatch.setattr(xu_ly_tin_vao, "bao_nhan_vien_tiep_quan", bao_nv)
    monkeypatch.setattr(xu_ly_tin_vao, "bao_khach_dang_chuyen_nguoi", bao_khach)

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.")
            c = await _quy_tac2(db, "Chuyển", {}, [{"loai": "chuyen_nguoi"}],
                                thu_tu=1 if chuyen_truoc else 2)
            m = await _quy_tac2(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"}],
                                thu_tu=2 if chuyen_truoc else 1)
            kq = await tu_dong.chay_tin_khach(_msg(tk), cid)
            return kq, await _tin_tu_dong(db, cid), await _lan(db, c), await _lan(db, m)
        finally:
            await _dong(db)

    kq, tin, lan_c, lan_m = asyncio.run(chay())
    assert kq.dung_agent
    if chuyen_truoc:
        assert goi == ["nhan_vien", "khach"] and tin == []
        assert lan_m[0] == "bo_qua" and "Chuyển" in lan_m[1]["bo_qua"][0]
    else:
        assert goi == ["nhan_vien"] and tin == ["Dạ shop chào chị ạ."]
        assert "Chào" in lan_c[1]["bo_qua"][0]


def test_viec_cung_tieu_de_chi_tao_mot(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _quy_tac2(db, "A", {}, [{"loai": "tao_viec", "tieu_de": "Gọi lại khách"}], thu_tu=1)
            await _quy_tac2(db, "B", {}, [{"loai": "tao_viec", "tieu_de": "Gọi lại khách"}], thu_tu=2)
            await _quy_tac2(db, "C", {}, [{"loai": "tao_viec", "tieu_de": "Gửi báo giá"}], thu_tu=3)
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            return sorted(r["tieu_de"] for r in await db.fetch(
                "SELECT tieu_de FROM cong_viec WHERE conversation_id = $1", cid))
        finally:
            await _dong(db)

    assert asyncio.run(chay()) == ["Gọi lại khách", "Gửi báo giá"]


def test_cho_ai_tra_loi_thi_ai_khong_nhuong(csdl_kiem_thu, gio_lam, kenh):
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.")
            await _quy_tac2(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"}],
                            cho_ai_tra_loi=True)
            return await tu_dong.chay_tin_khach(_msg(tk), cid)
        finally:
            await _dong(db)

    kq = asyncio.run(chay())
    assert kq.da_gui_khach and not kq.ai_nhuong


@pytest.mark.parametrize("tinh_huong", ["cho_nguoi", "duyet_rieng", "doi_gap_nguoi",
                                        "da_doi_gap_nguoi", "nhom"])
def test_khong_gui_mau_nhung_van_gan_nhan(csdl_kiem_thu, gio_lam, kenh, tinh_huong):
    """
    Năm lúc quy tắc không được NÓI với khách. Việc không nói ra (gắn nhãn)
    vẫn làm — để quy tắc phân loại hội thoại không ngừng chỉ vì có người.
    """
    from agent.omnichannel import thong_bao_ai

    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.")
            q = await _quy_tac2(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"},
                                                 {"loai": "gan_nhan", "nhan": "mới"}])
            van_ban = "alo"
            if tinh_huong == "cho_nguoi":
                await db.execute("UPDATE conversations SET status = 'escalated' WHERE id = $1", cid)
            elif tinh_huong == "duyet_rieng":
                await db.execute("UPDATE conversations SET duyet_truoc_khi_gui = true "
                                 "WHERE id = $1", cid)
            elif tinh_huong == "doi_gap_nguoi":
                van_ban = "cho em gặp nhân viên"
            elif tinh_huong == "da_doi_gap_nguoi":
                await db.log_event(thong_bao_ai.SU_KIEN_DOI_GAP_NGUOI, ref_id=cid)
            else:
                await db.execute("UPDATE conversations SET thread_type = 1 WHERE id = $1", cid)
            kq = await tu_dong.chay_tin_khach(_msg(tk, van_ban), cid)
            return (kq, await _v(db, "SELECT count(*) FROM outbox_jobs"), await _lan(db, q))
        finally:
            await _dong(db)

    kq, so_tin, lan = asyncio.run(chay())
    assert so_tin == 0, tinh_huong
    assert not kq.da_gui_khach and not kq.ai_nhuong
    assert lan[0] == "da_lam" and lan[1]["lam"] == ["gắn nhãn hội thoại mới"]
    assert lan[1]["bo_qua"][0].startswith("không gửi mẫu: ")


def test_mot_lan_tinh_theo_tung_loai_hanh_dong(csdl_kiem_thu, gio_lam, kenh):
    """
    Lần đầu mẫu bị bỏ qua (người đang tiếp) mà việc đã tạo: lần sau mẫu vẫn
    gửi được, việc KHÔNG tạo lại. Bản trước ghi "một lần" cho cả quy tắc —
    mẫu ấy không bao giờ được gửi nữa.
    """
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.")
            await _quy_tac2(db, "Chào + việc", {}, [{"loai": "gui_mau", "ma_tat": "chao"},
                                                    {"loai": "tao_viec", "tieu_de": "Gọi lại"}])
            await tu_dong.chay_tin_khach(_msg(tk), cid, nguoi_dang_tiep=True)
            await tu_dong.chay_tin_khach(_msg(tk, "tin 2"), cid)
            await tu_dong.chay_tin_khach(_msg(tk, "tin 3"), cid)
            return (await _tin_tu_dong(db, cid),
                    await _v(db, "SELECT count(*) FROM cong_viec WHERE conversation_id = $1", cid))
        finally:
            await _dong(db)

    tin, viec = asyncio.run(chay())
    assert tin == ["Dạ shop chào chị ạ."] and viec == 1


def test_dong_cu_mot_lan_khong_loai_van_tinh_ca_hai(csdl_kiem_thu, gio_lam, kenh):
    """Nhật ký trước 0060 chỉ có `mot_lan: true` — không được gửi lại lần nữa."""
    async def chay():
        db, tk, cid = await _mo(csdl_kiem_thu)
        try:
            await _mau(db, chao="Dạ shop chào chị ạ.")
            q = await _quy_tac2(db, "Chào", {}, [{"loai": "gui_mau", "ma_tat": "chao"},
                                                 {"loai": "tao_viec", "tieu_de": "Gọi lại"}])
            await db.execute("INSERT INTO quy_tac_lan_chay (quy_tac_id, conversation_id, ket_qua, "
                             "chi_tiet) VALUES ($1,$2,'da_lam',$3::jsonb)", q, cid,
                             {"lam": ["gửi mẫu /chao"], "mot_lan": True})
            await tu_dong.chay_tin_khach(_msg(tk), cid)
            return (await _v(db, "SELECT count(*) FROM outbox_jobs"),
                    await _v(db, "SELECT count(*) FROM cong_viec"))
        finally:
            await _dong(db)

    assert asyncio.run(chay()) == (0, 0)


def test_kiem_luc_luu_chan_mau_thuan():
    a = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(QuyTacHong, match="MỘT hành động gui_mau"):
        kiem_hanh_dong([{"loai": "gui_mau", "ma_tat": "a"}, {"loai": "gui_mau", "ma_tat": "b"}])
    with pytest.raises(QuyTacHong, match="chuyen_nguoi"):
        kiem_hanh_dong([{"loai": "chuyen_nguoi"}, {"loai": "chuyen_nguoi"}])
    with pytest.raises(QuyTacHong, match="hai lần"):
        kiem_hanh_dong([{"loai": "gan_nhan_khach", "nhan_id": a},
                        {"loai": "gan_nhan_khach", "nhan_id": a}])
    with pytest.raises(QuyTacHong, match="mâu thuẫn"):
        kiem_dieu_kien({"nhan_khach_co": [a], "nhan_khach_khong": [a]})
    # Hai LOẠI nhãn khác nhau cùng id thì không mâu thuẫn (hai danh mục riêng).
    kiem_dieu_kien({"nhan_hoi_thoai_co": [a], "nhan_khach_khong": [a]})
    # Đủ bốn loại hành động trong một quy tắc là hợp lệ (mục 7.4).
    assert len(kiem_hanh_dong([{"loai": "gan_nhan_hoi_thoai", "nhan_id": a},
                               {"loai": "gui_mau", "ma_tat": "chao"},
                               {"loai": "tao_viec", "tieu_de": "Gọi lại"},
                               {"loai": "chuyen_nguoi"}])) == 4


def test_ai_nhuong_dat_sau_cac_nhanh_chuyen_nguoi():
    """
    AI nhường tin cho quy tắc — nhưng KHÔNG được nuốt các nhánh giao người
    (agent tắt theo kênh, khách đòi gặp người, ảnh không chữ): một câu chào
    tự động không thay được việc báo nhân viên. Và phải TRƯỚC "em là trợ lý
    AI" cùng lời gọi model.
    """
    src = (ROOT / "agent" / "omnichannel" / "xu_ly_tin_vao.py").read_text(encoding="utf-8")
    i = src.index("if tu_dong_kq.ai_nhuong:")
    for truoc in ("agent_bat.agent_duoc_tra_loi(", "thong_bao_ai.khach_doi_gap_nguoi(",
                  "msg.attachments and not msg.text.strip()"):
        assert src.index(truoc) < i, truoc
    for sau in ("await thong_bao_ai.gui_neu_chua(", "reply = await brain.respond("):
        assert i < src.index(sau), sau
