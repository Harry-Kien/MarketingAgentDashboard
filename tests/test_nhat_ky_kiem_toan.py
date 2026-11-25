"""
Nhật ký kiểm toán có cấu trúc — phiếu việc mục 18 (trách nhiệm của AI).

Canh từng ràng buộc của tính năng, mỗi cái một test:
  · CHỈ THÊM: UPDATE/DELETE/TRUNCATE trên `events` bị CSDL chặn; lối ra
    `cskh.cho_xoa_nhat_ky` chỉ mở DELETE, chỉ trong giao dịch đặt nó; hạn
    lưu trữ (đường xoá dữ liệu khách) vẫn chạy được.
  · LƯỢT AI: mọi dòng ghi trong lượt mang chung `luot_id`; lượt đóng ở mọi
    lối ra; tra cả lượt từ một mã.
  · KHÔNG LỘ BÍ MẬT: khoá, token, số điện thoại, email, suy luận model bị che
    lúc ĐỌC — kể cả dòng cũ ghi trước khi có quy tắc.
  · TẦM NHÌN: tra toàn bộ cần `nhat_ky.doc`; nhân viên chỉ thấy nhật ký hội
    thoại thuộc kênh mình; ghi sự cố cần `nhat_ky.su_co`.
  · SỰ CỐ: dòng gốc không đổi một byte; sự cố, bước can thiệp, kết thúc,
    giải trình đều là dòng mới.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _hoi_thoai_dau, _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql,
    _them_thanh_vien,
)

TOKEN_META = "EAAB" + "x" * 40
SDT = "0911222333"


# =====================================================================
#  Làm sạch (điểm 13) — hàm thuần
# =====================================================================

def test_lam_sach_che_bi_mat_danh_tinh_va_suy_luan():
    from agent.core.nhat_ky_kiem_toan import AN, CHE, lam_sach

    ra = lam_sach({
        "access_token": "abc", "app_secret": "s", "mat_khau": "m", "api_key": "k",
        "idempotency_key": "ai:x", "tokens_in": 120, "tokens_out": 30,
        "loi": f"GET https://graph.facebook.com/x?access_token={TOKEN_META}&a=1",
        "ghi_chu": f"khách để lại số {SDT} và mail chi.a@vi-du.vn",
        "header": "Authorization: Bearer abcdefghijklmnop",
        "khach_ten": "Chị A", "dia_chi": "1 Đường B",
        "thinking": "mô hình nghĩ thầm...", "reasoning": "x",
        "long": {"sau": {"nua": {"token": "t", "thong_tin": TOKEN_META}}},
    })
    for k in ("access_token", "app_secret", "mat_khau", "api_key", "idempotency_key"):
        assert ra[k] == CHE, k
    # Số đếm token là số đo chi phí, không phải bí mật.
    assert ra["tokens_in"] == 120 and ra["tokens_out"] == 30
    assert TOKEN_META not in json.dumps(ra, ensure_ascii=False)
    assert SDT not in ra["ghi_chu"] and "chi.a@vi-du.vn" not in ra["ghi_chu"]
    assert "abcdefghijklmnop" not in ra["header"]
    assert ra["khach_ten"] == AN and ra["dia_chi"] == AN
    assert ra["thinking"] == AN and ra["reasoning"] == AN
    assert ra["long"]["sau"]["nua"]["token"] == CHE


def test_lam_sach_che_gia_tri_bi_mat_dang_cau_hinh(monkeypatch):
    """Khoá thật đang cấu hình bị che dù nằm dưới một khoá vô tội."""
    from agent.core import nhat_ky_kiem_toan as nk

    monkeypatch.setattr(nk, "_bi_mat_dang_cau_hinh", lambda: ("khoa-that-cua-shop-123",))
    ra = nk.lam_sach({"loi": "gọi thất bại với khoa-that-cua-shop-123"})
    assert "khoa-that-cua-shop-123" not in ra["loi"]


def test_lam_sach_co_tran_va_khong_nem():
    from agent.core.nhat_ky_kiem_toan import lam_sach

    ra = lam_sach({"dai": "a" * 5000, "ds": list(range(500)), "la": object(),
                   **{f"k{i}": i for i in range(200)}})
    assert len(json.dumps(ra, default=str)) < 20_000
    assert ra["dai"].endswith("…")


# =====================================================================
#  Lượt AI (điểm 4) — hàm thuần
# =====================================================================

def test_gan_vao_chi_trong_luot_va_khong_de_khoa():
    from agent.core import luot_ai

    cid = uuid.uuid4()
    assert luot_ai.gan_vao({"a": 1}, cid) == {"a": 1}
    with luot_ai.mo_luot(cid, "tin-1") as lid:
        tren_hoi_thoai = luot_ai.gan_vao({"a": 1}, cid)
        tren_don = luot_ai.gan_vao({"luot_id": "giu-nguyen"}, uuid.uuid4())
    assert tren_hoi_thoai == {"a": 1, "luot_id": lid, "tin_vao_id": "tin-1"}
    # ref_id là ĐƠN -> phải mang hội thoại theo, không thì lọc theo hội thoại mất nó.
    assert tren_don["hoi_thoai_id"] == str(cid)
    assert tren_don["luot_id"] == "giu-nguyen"
    assert luot_ai.hien_tai() is None


def test_pham_vi_luot_dong_luot_o_moi_loi_ra():
    """Worker xử lý tin tuần tự trên một task: lượt không đóng là dính sang tin sau."""
    from agent.core import luot_ai

    @luot_ai.pham_vi_luot
    async def xu_ly(nem: bool):
        luot_ai.bat_dau(uuid.uuid4())
        assert luot_ai.hien_tai() is not None
        if nem:
            raise RuntimeError("hỏng")

    async def chay():
        await xu_ly(False)
        assert luot_ai.hien_tai() is None
        with pytest.raises(RuntimeError):
            await xu_ly(True)
        assert luot_ai.hien_tai() is None

    asyncio.run(chay())


def test_handle_inbound_mo_luot_dung_cho():
    """
    Lượt mở SAU các nhánh hệ thống tự quyết (tin nhóm, agent tắt, khách đòi
    người, ảnh không chữ) và TRƯỚC lúc AI được gọi; hàm có decorator đóng lượt.
    """
    from agent.omnichannel import xu_ly_tin_vao

    assert hasattr(xu_ly_tin_vao.handle_inbound, "__wrapped__"), "thiếu @pham_vi_luot"
    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    assert "@luot_ai.pham_vi_luot" in src
    mo = src.index("luot_ai.bat_dau(")
    assert src.index("khách gửi ảnh không kèm chữ") < mo
    assert src.index("agent_bat.agent_duoc_tra_loi") < mo
    assert mo < src.index("await thong_bao_ai.gui_neu_chua") < src.index("= await brain.respond(")
    # Kết quả lượt có dòng nhật ký riêng cho cả hai đường.
    assert '"ai.tu_gui"' in src and '"ai.soan_nhap"' in src
    assert "luot=luot_ai.hien_tai()" in src


def test_dau_vet_ai_mang_ma_luot():
    from types import SimpleNamespace

    from agent.core import dau_vet_ai

    reply = SimpleNamespace(confidence=0.9, grounded=True, cong_cu=[], tri_thuc=[])
    dv = dau_vet_ai.dung(reply, ho_so=None, che_do_chung="auto", duyet_rieng=False,
                         tu_gui=True, luot={"luot_id": "L1", "tin_vao_id": "T1"})
    assert dv["luot_id"] == "L1" and dv["tin_vao_id"] == "T1"
    assert "luot_id" not in dau_vet_ai.dung(reply, ho_so=None, che_do_chung="auto",
                                            duyet_rieng=False, tu_gui=True)


def test_tien_to_bien_phien_khong_trung_quyen():
    """`cskh.*` dành cho biến phiên Postgres; test quyền-trong-migration bỏ qua nó."""
    from agent.core.quyen import QUYEN, QUYEN_DA_GO

    assert not [q for q in (*QUYEN, *QUYEN_DA_GO) if q.startswith("cskh.")]
    sql = (ROOT / "agent/migrations/versions/0064_nhat_ky_chi_them.sql").read_text(
        encoding="utf-8")
    assert "current_setting('cskh.cho_xoa_nhat_ky', true)" in sql


def test_dashboard_gan_tab_nhat_ky_va_nhat_ky_hoi_thoai():
    """
    Tab "Nhật ký" phải được mô-đun mới thay (GAN_TAB), app.js phải mang nó
    (tệp sinh ra — quên đóng gói là màn hình vẫn là danh sách thô), và panel
    Chi tiết hội thoại phải gọi phần nhật ký riêng của hội thoại.
    """
    src = (ROOT / "dashboard/src/27-nhat-ky.js").read_text(encoding="utf-8")
    app = (ROOT / "dashboard/app.js").read_text(encoding="utf-8")
    trach_nhiem = (ROOT / "dashboard/src/19-trach-nhiem.js").read_text(encoding="utf-8")
    assert 'GAN_TAB["ht-nhat-ky"]' in src and 'GAN_TAB["ht-nhat-ky"]' in app
    assert "veNhatKyHoiThoai(c)" in trach_nhiem
    for duong in ("/nhat-ky?", "/nhat-ky/danh-muc", "/nhat-ky/de-xuat",
                  "/nhat-ky/luot/", "/nhat-ky/hoi-thoai/", "/su-co", "/giai-trinh",
                  "/ket-thuc", "/buoc", "/api/nhat-ky/xuat.csv"):
        assert duong in src, duong
    # Nút ghi chỉ hiện khi có quyền ghi.
    assert 'nkCo("nhat_ky.su_co")' in src
    assert len(src.splitlines()) <= 1000


def test_mau_phan_loai_hop_le_va_moi_nhom_co_nhan():
    from agent.core import nhat_ky_kiem_toan as nk

    nk._sql_nhom()
    nk._sql_loai_tac_nhan()
    ma = [m for m, _, _ in nk.NHOM_HANH_DONG] + [nk.NHOM_MAC_DINH[0]]
    assert len(ma) == len(set(ma))
    with pytest.raises(ValueError):
        nk._sql_chuoi("x'; DROP TABLE events; --")


# =====================================================================
#  Chốt quyền trên router (điểm 9)
# =====================================================================

def test_ghi_can_quyen_su_co_doc_can_nhat_ky_hoac_hoi_thoai():
    """
    Đọc qua nguồn: chốt `can_quyen` là closure, không phải thuộc tính —
    nên kiểm chuỗi khai báo cạnh từng endpoint (khớp cách repo khai quyền).
    """
    from agent.api import nhat_ky_api

    cay = ast.parse(inspect.getsource(nhat_ky_api))
    gap = 0
    for f in cay.body:
        if not isinstance(f, ast.AsyncFunctionDef):
            continue
        tram = [d for d in f.decorator_list if isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute) and d.func.value.id == "router"]  # type: ignore[attr-defined]
        if not tram:
            continue
        gap += 1
        phuong = tram[0].func.attr  # type: ignore[attr-defined]
        duong = tram[0].args[0].value  # type: ignore[attr-defined]
        nguon = ast.get_source_segment(inspect.getsource(nhat_ky_api), f) or ""
        if phuong == "post":
            assert 'can_quyen("nhat_ky.su_co")' in nguon, duong
        elif duong.startswith("/hoi-thoai/"):
            assert 'can_quyen("hoi_thoai.doc")' in nguon, duong
            assert "chan_neu_ngoai_kenh(cid, nguoi)" in nguon, duong
        else:
            assert 'can_quyen("nhat_ky.doc")' in nguon, duong
    assert gap >= 10


# =====================================================================
#  Postgres thật
# =====================================================================

@pytest.fixture
def csdl(csdl_kiem_thu, monkeypatch):
    from agent import db
    from agent.config import settings

    monkeypatch.setattr(settings, "database_url", csdl_kiem_thu)
    db._pool = None
    yield csdl_kiem_thu
    db._pool = None


def _chay(coro_fn):
    from agent import db

    async def boc():
        await db.init_db()
        try:
            return await coro_fn()
        finally:
            await db.close_db()
    return asyncio.run(boc())


async def _hoi_thoai(ten="x") -> uuid.UUID:
    from agent import db

    ext = f"ext-{uuid.uuid4()}"
    tk = await db.fetchrow_chac(
        "INSERT INTO channel_accounts (channel, display_name, status) "
        "VALUES ('webchat', 'Web shop', 'active') RETURNING id")
    kh = await db.fetchrow_chac(
        "INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ten)
    diem = await db.fetchrow_chac(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1, $2, $3) RETURNING id", kh["id"], tk["id"], ext)
    r = await db.fetchrow_chac(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
        "customer_name, contact_id, contact_point_id) "
        "VALUES ($1, 'webchat', $2, $2, $3, $4, $5) RETURNING id",
        tk["id"], ext, ten, kh["id"], diem["id"])
    return r["id"]


def test_events_chi_them_va_loi_ra_chi_cho_delete(csdl):
    import asyncpg

    from agent import db

    async def kiem():
        await db.log_event("thu.mot", ref_id=None, a=1)
        r = await db.fetchrow_chac("SELECT id FROM events WHERE kind = 'thu.mot'")
        for lenh in ("UPDATE events SET detail = '{}' WHERE id = $1",
                     "DELETE FROM events WHERE id = $1"):
            with pytest.raises(asyncpg.InsufficientPrivilegeError, match="chỉ được thêm"):
                await db.execute(lenh, r["id"])
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await db.execute("TRUNCATE events")
        async with db.pool().acquire() as conn:
            # Lối ra: SET LOCAL trong giao dịch — UPDATE vẫn cấm, DELETE được.
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                async with conn.transaction():
                    await conn.execute("SET LOCAL cskh.cho_xoa_nhat_ky = 'on'")
                    await conn.execute("UPDATE events SET kind = 'x' WHERE id = $1", r["id"])
            async with conn.transaction():
                await conn.execute("SET LOCAL cskh.cho_xoa_nhat_ky = 'on'")
                await conn.execute("DELETE FROM events WHERE id = $1", r["id"])
            # Hết giao dịch là hết lối ra.
            await conn.execute("INSERT INTO events (kind) VALUES ('thu.hai')")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute("DELETE FROM events WHERE kind = 'thu.hai'")
        con = await db.fetch("SELECT kind FROM events WHERE kind LIKE 'thu.%'")
        assert [c["kind"] for c in con] == ["thu.hai"]

    _chay(kiem)


def test_han_luu_tru_van_chay_khi_nhat_ky_chi_them(csdl, monkeypatch):
    """
    Đường xoá dữ liệu khách xoá hội thoại — sự kiện trỏ vào hội thoại ấy KHÔNG
    bị kéo theo (không khoá ngoại) và không làm hỏng lượt dọn.
    """
    from agent import db
    from agent.config import settings
    from agent.core import du_lieu_ca_nhan

    monkeypatch.setattr(settings, "luu_hoi_thoai_ngay", 180)

    async def kiem():
        cid = await _hoi_thoai("Chị Cũ")
        await db.execute("UPDATE conversations SET updated_at = now() - interval '400 days' "
                         "WHERE id = $1", cid)
        await db.log_event("conversation.escalated", ref_id=cid, reason="cũ")
        kq = await du_lieu_ca_nhan.don_theo_thoi_han()
        assert kq["da_xoa"] == 1
        assert await db.fetchrow("SELECT 1 FROM conversations WHERE id = $1", cid) is None
        con = await db.fetch("SELECT kind FROM events WHERE ref_id = $1", cid)
        assert [c["kind"] for c in con] == ["conversation.escalated"]
        assert await db.fetchrow("SELECT 1 FROM events WHERE kind = 'pdpd.don_theo_thoi_han'")

    _chay(kiem)


def test_luot_ai_noi_moi_dong_va_tra_ca_luot(csdl):
    from agent import db
    from agent.core import luot_ai
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid = await _hoi_thoai()
        tin = await db.fetchrow_chac(
            "INSERT INTO messages (conversation_id, role, content, direction) "
            f"VALUES ($1, 'customer', 'cho em đặt, số {SDT}', 'inbound') RETURNING id", cid)
        don = uuid.uuid4()
        with luot_ai.mo_luot(cid, tin["id"]) as lid:
            await db.log_event("knowledge.retrieved", ref_id=cid, sources=[{"title": "a"}])
            await db.log_event("cong_cu.goi", ref_id=cid, ten="tao_don_hang", ok=True)
            await db.log_event("order.created", ref_id=don, ma_don="DH1", trang_thai="cho_duyet")
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, direction, "
                "delivery_status, dau_vet_ai) VALUES ($1, 'agent', 'Dạ em lên đơn ạ', "
                "'outbound', 'draft', $2)",
                cid, {"luot_id": lid, "tin_vao_id": str(tin["id"]), "tri_thuc": [],
                      "cong_cu": [{"ten": "tao_don_hang", "ket_qua": {"ma_don": "DH1"}}]})
            await db.log_event("ai.soan_nhap", actor="agent", ref_id=cid, che_do="assist",
                               co_can_cu=True, muc_uy_quyen=None)
        await db.log_event("ngoai.luot", ref_id=cid)  # SAU lượt: không mang mã

        theo_luot = await nk.tim(luot_id=lid)
        assert [b["kind"] for b in theo_luot["items"]] == [
            "ai.soan_nhap", "order.created", "cong_cu.goi", "knowledge.retrieved"]
        assert all(b["tac_nhan"]["loai"] == "ai" for b in theo_luot["items"])
        # Đơn (ref_id = đơn) vẫn thuộc hội thoại — lọc theo hội thoại có nó.
        theo_ht = await nk.tim(hoi_thoai_id=cid)
        assert "order.created" in [b["kind"] for b in theo_ht["items"]]
        assert "ngoai.luot" in [b["kind"] for b in theo_ht["items"]]

        lu = await nk.luot(lid)
        assert lu["hoi_thoai_id"] == str(cid)
        assert lu["tin_khach"]["id"] == str(tin["id"])
        assert SDT not in lu["tin_khach"]["noi_dung"]
        assert [t["noi_dung"] for t in lu["tra_loi"]] == ["Dạ em lên đơn ạ"]
        # Ảnh chụp căn cứ: kết quả công cụ lúc xử lý nằm trong lượt.
        assert lu["tra_loi"][0]["dau_vet"]["cong_cu"][0]["ket_qua"] == {"ma_don": "DH1"}
        assert lu["ket_qua"]["kind"] == "ai.soan_nhap"
        assert lu["ket_qua"]["trang_thai"]["ma"] == "cho_duyet"
        assert await nk.luot(str(uuid.uuid4())) is None

    _chay(kiem)


def test_mo_hinh_doc_chuan_hoa_tac_nhan_hoi_thoai_trang_thai(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        nd = await db.fetchrow_chac(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('lan', 'x', 'Chị Lan') RETURNING id")
        cid = await _hoi_thoai()
        tin = await db.fetchrow_chac(
            "INSERT INTO messages (conversation_id, role, content, direction) "
            "VALUES ($1, 'agent', 'x', 'outbound') RETURNING id", cid)
        await db.log_event("tin_nhan.duyet", actor="lan", ref_id=tin["id"])
        await db.log_event("conversation.takeover", actor=str(nd["id"]), ref_id=cid)
        await db.log_event("backup.failed", ref_id=None, loi="đĩa đầy")
        await db.log_event("conversation.escalated", ref_id=cid, reason="thấp")
        await db.log_event("cong_cu.goi", ref_id=cid, ten="x", ok=False)

        tat_ca = {b["kind"]: b for b in (await nk.tim())["items"]}
        duyet = tat_ca["tin_nhan.duyet"]
        assert duyet["tac_nhan"] == {"loai": "nhan_vien", "nhan": "Nhân viên",
                                     "ten": "Chị Lan", "id": str(nd["id"])}
        # ref_id là TIN -> quy về hội thoại của tin.
        assert duyet["hoi_thoai_id"] == str(cid)
        assert duyet["nhom"]["ma"] == "phe_duyet"
        assert tat_ca["conversation.takeover"]["tac_nhan"]["ten"] == "Chị Lan"
        assert tat_ca["backup.failed"]["tac_nhan"]["loai"] == "he_thong"
        assert tat_ca["backup.failed"]["trang_thai"]["ma"] == "loi"
        assert tat_ca["conversation.escalated"]["trang_thai"]["ma"] == "chuyen_nguoi"
        assert tat_ca["cong_cu.goi"]["trang_thai"]["ma"] == "loi"
        assert tat_ca["cong_cu.goi"]["tac_nhan"]["loai"] == "ai"
        for b in tat_ca.values():
            assert "muc_uy_quyen" in b and "che_do_ai" in b

        # Lọc + phân trang bằng con trỏ: không lặp, không sót.
        assert [b["kind"] for b in (await nk.tim(nguoi_id=nd["id"]))["items"]] == [
            "conversation.takeover", "tin_nhan.duyet"]
        he_thong = {b["kind"] for b in (await nk.tim(loai_tac_nhan="he_thong"))["items"]}
        assert {"backup.failed", "conversation.escalated"} <= he_thong
        assert not he_thong & {"cong_cu.goi", "tin_nhan.duyet", "conversation.takeover"}
        assert {b["kind"] for b in (await nk.tim(trang_thai="loi"))["items"]} == {
            "backup.failed", "cong_cu.goi"}
        tong = int((await db.fetchrow_chac("SELECT count(*) n FROM events"))["n"])
        ids: list[int] = []
        con_tro = None
        while True:
            trang = await nk.tim(limit=2, truoc=con_tro)
            ids += [b["id"] for b in trang["items"]]
            con_tro = trang["next_cursor"]
            if con_tro is None:
                break
        assert len(ids) == len(set(ids)) == tong and ids == sorted(ids, reverse=True)

    _chay(kiem)


def test_su_co_la_dong_moi_dong_goc_khong_doi(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid = await _hoi_thoai()
        await db.log_event("ai.tu_gui", actor="agent", ref_id=cid, co_can_cu=False,
                           che_do="auto", luot_id="L-goc")
        goc = await db.fetchrow_chac("SELECT * FROM events WHERE kind = 'ai.tu_gui'")

        sc = await nk.ghi_su_co(goc["id"], ghi_chu="AI khuyên sai cho bà bầu", boi="lan")
        with pytest.raises(nk.KhongHopLe):
            await nk.ghi_su_co(goc["id"], ghi_chu="lần hai", boi="lan")
        with pytest.raises(nk.KhongHopLe):
            await nk.ghi_su_co(sc, ghi_chu="sự cố của sự cố", boi="lan")
        await nk.ghi_buoc_can_thiep(sc, loai="tat_ai", ghi_chu="tắt AI kênh Zalo", boi="lan")
        await nk.ghi_ket_thuc_su_co(sc, ket_qua="đã gọi xin lỗi khách", ghi_chu="", boi="lan")
        with pytest.raises(nk.KhongHopLe):
            await nk.ghi_buoc_can_thiep(sc, loai="khac", ghi_chu="", boi="lan")
        await nk.ghi_giai_trinh(goc["id"], ghi_chu="tài liệu cũ chưa cập nhật", boi="lan")
        with pytest.raises(nk.KhongThay):
            await nk.ghi_su_co(10**9, ghi_chu="không có", boi="lan")

        sau = await db.fetchrow_chac("SELECT * FROM events WHERE id = $1", goc["id"])
        assert dict(sau) == dict(goc), "dòng gốc bị sửa"
        ban = await nk.mot(goc["id"])
        assert ban["trang_thai"]["ma"] == "su_co"
        assert [x["kind"] for x in ban["lien_quan"]] == [
            "su_co.danh_dau", "su_co.can_thiep", "su_co.ket_thuc", "nhat_ky.giai_trinh"]
        danh_dau = ban["lien_quan"][0]
        assert danh_dau["luot_id"] == "L-goc" and danh_dau["hoi_thoai_id"] == str(cid)
        assert danh_dau["tac_nhan"]["loai"] == "nhan_vien"

    _chay(kiem)


def test_de_xuat_co_hinh_dang_on_dinh(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        nd = await db.fetchrow_chac(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('lan', 'x', 'Chị Lan') RETURNING id")
        cid = await _hoi_thoai()
        await db.execute(
            "INSERT INTO messages (conversation_id, role, content, direction, delivery_status, "
            " dau_vet_ai) VALUES ($1, 'agent', 'nháp chờ', 'outbound', 'draft', $2)",
            cid, {"luot_id": "L1", "ho_so": {"ten": "Bán hàng"}})
        await db.execute(
            "INSERT INTO messages (conversation_id, role, content, direction, delivery_status, "
            " duyet_boi, duyet_luc, sua_boi, sua_luc) VALUES ($1, 'agent', 'đã sửa', 'outbound', "
            " 'sent', $2, now(), 'lan', now())", cid, nd["id"])
        kq = await nk.de_xuat(hoi_thoai_id=cid)
        tt = {i["tom_tat"]: i for i in kq["items"]}
        assert tt["nháp chờ"]["trang_thai"]["ma"] == "cho_duyet"
        assert tt["nháp chờ"]["luot_id"] == "L1"
        assert tt["nháp chờ"]["de_xuat_boi"] == {"loai": "ai", "ten": "Bán hàng"}
        assert tt["đã sửa"]["trang_thai"]["ma"] == "da_sua_va_duyet"
        assert tt["đã sửa"]["nguoi_quyet"] == "Chị Lan"
        khoa = {"id", "nguon", "loai", "hoi_thoai_id", "luot_id", "de_xuat_boi", "tom_tat",
                "luc_de_xuat", "trang_thai", "nguoi_quyet", "luc_quyet", "nguoi_sua",
                "luc_sua", "muc_uy_quyen"}
        assert all(set(i) == khoa for i in kq["items"])

    _chay(kiem)


def test_de_xuat_gom_ca_hanh_dong_ai_cung_hinh_dang(csdl):
    """Mục 17 ghi đề xuất HÀNH ĐỘNG vào ai_de_xuat — màn nhật ký phải thấy chúng."""
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid = await _hoi_thoai()
        await db.execute(
            "INSERT INTO ai_de_xuat (conversation_id, hanh_dong, che_do_ai, muc_uy_quyen, "
            " ly_do_can_duyet, de_xuat, khoa_trung, het_han_luc) "
            "VALUES ($1, 'huy_don', 'tu_dong', 'co_phe_duyet', 'chinh_sach', $2, 'k1', "
            " now() + interval '1 day')", cid, {"tieu_de": "Huỷ đơn DH1"})
        kq = await nk.de_xuat(hoi_thoai_id=cid)
        hd = [i for i in kq["items"] if i["nguon"] == "hanh_dong_ai"]
        assert len(hd) == 1 and hd[0]["loai"] == "huy_don"
        assert hd[0]["muc_uy_quyen"] == "co_phe_duyet"
        assert hd[0]["trang_thai"]["ma"] == "cho_duyet" and hd[0]["tom_tat"] == "Huỷ đơn DH1"
        khoa = {"id", "nguon", "loai", "hoi_thoai_id", "luot_id", "de_xuat_boi", "tom_tat",
                "luc_de_xuat", "trang_thai", "nguoi_quyet", "luc_quyet", "nguoi_sua",
                "luc_sua", "muc_uy_quyen"}
        assert set(hd[0]) == khoa
        assert (await nk.de_xuat(hoi_thoai_id=cid, trang_thai="tu_choi"))["items"] == []

    _chay(kiem)


# =====================================================================
#  App đầy đủ: quyền và che trên đường HTTP thật
# =====================================================================

def test_quyen_va_che_tren_app_that(app_that):
    """
    BƯỚC: quản trị nối kênh web (AI tắt) → khách nhắn → một dòng nhật ký cũ
    lỡ chứa token và SĐT → nhân viên KHÔNG có `nhat_ky.doc` bị chặn tra toàn
    bộ, chưa là thành viên kênh thì 404, thành viên thì thấy nhật ký hội thoại
    đã che → nhân viên không ghi được sự cố → quản trị đánh dấu sự cố.
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị A", "cho em hỏi giá")
    cid = str(_hoi_thoai_dau(app_that)["id"])

    async def ghi(c):
        await db.log_event("thu.lo_bi_mat", ref_id=uuid.UUID(c), access_token=TOKEN_META,
                           loi=f"https://x/?access_token={TOKEN_META}", ghi_chu=f"sđt {SDT}")
    _sql(app_that, ghi, cid)

    uid, nv = _nhan_vien_moi(qt, "nvnhatky")
    assert nv.get("/api/nhat-ky").status_code == 403
    assert nv.get("/api/nhat-ky/danh-muc").status_code == 403
    assert nv.get(f"/api/nhat-ky/hoi-thoai/{cid}").status_code == 404
    _them_thanh_vien(app_that, tk, uid)
    r = nv.get(f"/api/nhat-ky/hoi-thoai/{cid}")
    assert r.status_code == 200, r.text
    assert "thu.lo_bi_mat" in r.text
    assert TOKEN_META not in r.text and SDT not in r.text

    ev = next(b for b in r.json()["items"] if b["kind"] == "thu.lo_bi_mat")
    assert nv.post(f"/api/nhat-ky/{ev['id']}/su-co",
                   json={"ghi_chu": "lộ token"}).status_code == 403

    for duong in ("/api/nhat-ky", f"/api/nhat-ky?hoi_thoai_id={cid}",
                  f"/api/nhat-ky/{ev['id']}", "/api/events",
                  "/api/nhat-ky/xuat.csv"):
        rr = qt.get(duong)
        assert rr.status_code == 200, (duong, rr.text)
        assert TOKEN_META not in rr.text and SDT not in rr.text, duong

    rr = qt.post(f"/api/nhat-ky/{ev['id']}/su-co", json={"ghi_chu": "lộ token trong log"})
    assert rr.status_code == 201, rr.text
    assert qt.get(f"/api/nhat-ky/{ev['id']}").json()["trang_thai"]["ma"] == "su_co"
    assert qt.post(f"/api/nhat-ky/{ev['id']}/su-co",
                   json={"ghi_chu": "lần hai"}).status_code == 409
    assert qt.get("/api/nhat-ky?tu=2030-01-01T00:00:00&den=2029-01-01T00:00:00"
                  ).status_code == 422
    # Xuất CSV cũng để lại dấu.
    assert any(b["kind"] == "nhat_ky.xuat" for b in qt.get("/api/nhat-ky").json()["items"])


def test_thao_tac_cua_nguoi_tren_de_xuat_ai_xep_la_nhan_vien(csdl):
    """`ai.ban_nhap.tu_choi` do nhân viên bấm — không được ghi là AI làm."""
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid = await _hoi_thoai()
        await db.log_event("ai.ban_nhap.tu_choi", actor="lan", ref_id=cid)
        await db.log_event("ai.tu_gui", actor="system", ref_id=cid)
        kq = await nk.tim(hoi_thoai_id=cid)
        theo_kind = {i["kind"]: i for i in kq["items"]}
        assert theo_kind["ai.ban_nhap.tu_choi"]["tac_nhan"]["loai"] == "nhan_vien"
        assert theo_kind["ai.tu_gui"]["tac_nhan"]["loai"] == "ai"

    _chay(kiem)
