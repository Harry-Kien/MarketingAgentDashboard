"""
Màn Nhật ký đọc được cho người vận hành — UX-18-02 và UX-18-03, trên
Postgres thật.

  · MỨC QUAN TRỌNG: lọc `muc_do` chạy TRÊN MÁY CHỦ (phân trang đúng), dòng đã
    đánh dấu sự cố luôn hiện dù ở mức nào.
  · GỘP DÒNG LẶP: dòng vận hành/kỹ thuật liền nhau cùng loại thành một bản
    ghi có số lần và khoảng thời gian; việc nghiệp vụ KHÔNG BAO GIỜ gộp;
    phân trang theo nhóm không lặp, không sót dòng nào.
  · ĐỐI TƯỢNG: mỗi dòng nói nó tác động lên đơn / việc / nhân viên / tài
    khoản kênh / hội thoại nào, và liên kết chỉ MỞ ĐƯỢC khi người xem có
    quyền mở màn đích — cùng luật với màn đích.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _hoi_thoai_dau, _kenh_webchat, _khach_nhan, _quan_tri_vao, _sql,
)


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


async def _hoi_thoai() -> tuple[uuid.UUID, uuid.UUID]:
    from agent import db

    ext = f"ext-{uuid.uuid4()}"
    tk = await db.fetchrow_chac(
        "INSERT INTO channel_accounts (channel, display_name, status) "
        "VALUES ('webchat', 'Web shop', 'active') RETURNING id")
    kh = await db.fetchrow_chac(
        "INSERT INTO contacts (display_name) VALUES ('Chị A') RETURNING id")
    diem = await db.fetchrow_chac(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1, $2, $3) RETURNING id", kh["id"], tk["id"], ext)
    r = await db.fetchrow_chac(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
        "customer_name, contact_id, contact_point_id) "
        "VALUES ($1, 'webchat', $2, $2, 'Chị A', $3, $4) RETURNING id",
        tk["id"], ext, kh["id"], diem["id"])
    return r["id"], tk["id"]


async def _nguoi(ten: str) -> uuid.UUID:
    from agent import db

    r = await db.fetchrow_chac(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
        "VALUES ($1, 'x', $2) RETURNING id", ten, ten.title())
    return r["id"]


# =====================================================================
#  UX-18-02 — mức quan trọng và gộp dòng lặp
# =====================================================================

def test_loc_muc_do_tren_may_chu_va_su_co_luon_hien(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid, _ = await _hoi_thoai()
        await db.log_event("ai.tu_gui", actor="agent", ref_id=cid, co_can_cu=True)
        await db.log_event("knowledge.retrieved", ref_id=cid, sources=[])
        await db.log_event("channel_account.status_changed", status="degraded")
        for _ in range(3):
            await db.log_event("erp.ngat_mach", ten="gia")
        lo = await db.fetchrow_chac(
            "SELECT id FROM events WHERE kind = 'erp.ngat_mach' ORDER BY id LIMIT 1")
        await nk.ghi_su_co(lo["id"], ghi_chu="ERP sập giờ cao điểm", boi="lan")

        nv = await nk.tim(muc_do=["nghiep_vu"])
        kinds = [b["kind"] for b in nv["items"]]
        assert "ai.tu_gui" in kinds and "su_co.danh_dau" in kinds
        assert "knowledge.retrieved" not in kinds
        assert "channel_account.status_changed" not in kinds
        # Dòng kỹ thuật ĐÃ đánh dấu sự cố vẫn hiện; hai dòng anh em của nó thì không.
        assert [b["id"] for b in nv["items"] if b["kind"] == "erp.ngat_mach"] == [lo["id"]]
        assert all(b["muc_do"]["ma"] == "nghiep_vu" or b["trang_thai"]["ma"] == "su_co"
                   for b in nv["items"])

        vh = {b["kind"] for b in (await nk.tim(muc_do=["nghiep_vu", "van_hanh"]))["items"]}
        assert "channel_account.status_changed" in vh and "knowledge.retrieved" not in vh
        tat_ca = {b["kind"] for b in (await nk.tim())["items"]}
        assert {"knowledge.retrieved", "erp.ngat_mach"} <= tat_ca
        # Phân trang trong bộ lọc mức: trang đầy, không hụt vì lọc sau LIMIT.
        assert len((await nk.tim(muc_do=["ky_thuat"], limit=3))["items"]) == 3
        b = next(x for x in (await nk.tim())["items"] if x["kind"] == "knowledge.retrieved")
        assert b["hanh_dong"] == "AI tra tài liệu" and b["muc_do"]["nhan"] == "Kỹ thuật"

    _chay(kiem)


def test_gop_dong_lap_lien_nhau_khong_gop_nghiep_vu(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid, _ = await _hoi_thoai()
        # Migration cũng ghi `events` (0056) — chỉ xét dòng của test này.
        tu = (await db.fetchrow_chac("SELECT clock_timestamp() AS t"))["t"]
        for _ in range(5):
            await db.log_event("erp.ngat_mach", ten="gia")
        await db.log_event("ai.tu_gui", actor="agent", ref_id=cid)
        await db.log_event("ai.tu_gui", actor="agent", ref_id=cid)
        for _ in range(2):
            await db.log_event("erp.ngat_mach", ten="gia")
        await db.log_event("zalo_personal.tin_bo_qua", ly_do="khong_co_chu_va_khong_co_tep")

        kq = await nk.tim(gom=True, tu=tu)
        hinh = [(b["kind"], (b["gom"] or {}).get("so_lan", 1)) for b in kq["items"]]
        assert hinh == [("zalo_personal.tin_bo_qua", 1), ("erp.ngat_mach", 2),
                        ("ai.tu_gui", 1), ("ai.tu_gui", 1), ("erp.ngat_mach", 5)]
        nhom = kq["items"][-1]["gom"]
        assert nhom["tu"] <= nhom["den"] and nhom["id_cu_nhat"] < kq["items"][-1]["id"]
        assert kq["items"][0]["ket_qua"] == "lý do: tin không có chữ cũng không có tệp"
        assert kq["items"][0]["hanh_dong"] == "Bỏ qua tin Zalo cá nhân không đọc được"

        # Phân trang THEO NHÓM: không lặp dòng, không sót dòng, mỗi trang 1 nhóm.
        tong = int((await db.fetchrow_chac(
            "SELECT count(*) n FROM events WHERE created_at >= $1", tu))["n"])
        assert tong == 10
        thay: list[int] = []
        dem, con_tro, so_trang = 0, None, 0
        while True:
            trang = await nk.tim(gom=True, limit=1, truoc=con_tro, tu=tu)
            so_trang += 1
            for b in trang["items"]:
                thay.append(b["id"])
                dem += (b["gom"] or {}).get("so_lan", 1)
            con_tro = trang["next_cursor"]
            if con_tro is None:
                break
        assert dem == tong and len(thay) == len(set(thay)) == so_trang == 5
        # Không gộp thì vẫn là từng dòng — CSV và lời gọi cũ không đổi.
        assert len((await nk.tim(tu=tu))["items"]) == tong

    _chay(kiem)


# =====================================================================
#  UX-18-03 — đối tượng và quyền mở liên kết
# =====================================================================

def _xem(uid, *quyen) -> dict:
    return {"id": str(uid), "quyen": frozenset({"nhat_ky.doc", *quyen})}


def test_lien_ket_doi_tuong_chi_mo_khi_nguoi_xem_co_quyen(csdl):
    from agent import db
    from agent.core import nhat_ky_kiem_toan as nk

    async def kiem():
        cid, tk = await _hoi_thoai()
        lan, minh, quan_ly = await _nguoi("lan"), await _nguoi("minh"), await _nguoi("quanly")
        don = await db.fetchrow_chac(
            "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, khach_dia_chi) "
            "VALUES ('DH-UX18', $1, 'Chị A', '0911222333', 'HN') RETURNING id", cid)
        viec = await db.fetchrow_chac(
            "INSERT INTO cong_viec (tieu_de, nguoi_nhan) VALUES ('Gọi lại 0911222333', $1) "
            "RETURNING id", lan)
        await db.log_event("order.created", actor="agent", ref_id=don["id"], ma_don="DH-UX18",
                           hoi_thoai_id=str(cid))
        await db.log_event("shipping.created", ma_don="DH-UX18", ma_van_don="GHN1")
        await db.log_event("cong_viec.tao", actor="quanly", ref_id=viec["id"], tieu_de="x")
        await db.log_event("nguoi_dung.vai_tro", actor="quanly", ref_id=minh)
        await db.log_event("conversation.takeover", actor="lan", ref_id=cid)

        async def doi_tuong(nguoi) -> dict[str, dict]:
            ra: dict[str, dict] = {}
            for b in (await nk.tim(nguoi=nguoi))["items"]:
                for lk in b["lien_ket"]:
                    ra[f"{b['kind']}/{lk['loai']}"] = lk
            return ra

        moi_quyen = _xem(quan_ly, "hoi_thoai.doc", "hoi_thoai.xem_tat_ca", "don.doc",
                         "cong_viec.doc", "cong_viec.xem_tat_ca", "nguoi_dung.doc", "kenh.doc")
        d = await doi_tuong(moi_quyen)
        assert d["order.created/don_hang"] == {"loai": "don_hang", "id": str(don["id"]),
                                               "nhan": "Đơn DH-UX18", "mo_duoc": True}
        assert d["order.created/hoi_thoai"]["id"] == str(cid)
        # Vận đơn chỉ ghi mã đơn — mô hình đọc vẫn tìm ra đơn.
        assert d["shipping.created/don_hang"]["id"] == str(don["id"])
        assert d["cong_viec.tao/cong_viec"]["mo_duoc"] is True
        # Tiêu đề việc là chữ người gõ: số điện thoại bị che trước khi ra ngoài.
        assert "0911222333" not in d["cong_viec.tao/cong_viec"]["nhan"]
        assert d["nguoi_dung.vai_tro/nhan_vien"] == {
            "loai": "nhan_vien", "id": str(minh), "nhan": "Nhân viên Minh", "mo_duoc": True}
        assert d["conversation.takeover/hoi_thoai"]["mo_duoc"] is True
        assert d["conversation.takeover/tai_khoan_kenh"]["id"] == str(tk)
        # Đối tượng chính đứng trước hội thoại.
        thu_tu = [lk["loai"] for b in (await nk.tim(nguoi=moi_quyen))["items"]
                  if b["kind"] == "order.created" for lk in b["lien_ket"]]
        assert thu_tu.index("don_hang") < thu_tu.index("hoi_thoai")

        # Chỉ có quyền đọc nhật ký + đọc hội thoại, KHÔNG thuộc kênh: tên
        # đối tượng vẫn hiện, nhưng không liên kết nào mở được.
        hep = _xem(minh, "hoi_thoai.doc")
        d = await doi_tuong(hep)
        assert d["conversation.takeover/hoi_thoai"]["mo_duoc"] is False
        assert d["order.created/don_hang"]["mo_duoc"] is False
        assert d["cong_viec.tao/cong_viec"]["mo_duoc"] is False
        assert d["nguoi_dung.vai_tro/nhan_vien"]["mo_duoc"] is False
        assert d["conversation.takeover/tai_khoan_kenh"]["mo_duoc"] is False
        # Thành viên kênh thì mở được hội thoại — y hệt chan_neu_ngoai_kenh.
        await db.execute("INSERT INTO account_memberships (account_id, user_id) VALUES ($1, $2)",
                         tk, minh)
        assert (await doi_tuong(hep))["conversation.takeover/hoi_thoai"]["mo_duoc"] is True

        # Công việc: người NHẬN mở được, người khác không có xem_tat_ca thì không.
        assert (await doi_tuong(_xem(lan, "cong_viec.doc")))[
            "cong_viec.tao/cong_viec"]["mo_duoc"] is True
        assert (await doi_tuong(_xem(minh, "cong_viec.doc")))[
            "cong_viec.tao/cong_viec"]["mo_duoc"] is False

        # Không biết người xem: hỏng-đóng.
        assert not any(lk["mo_duoc"] for lk in (await doi_tuong(None)).values())
        # Một dòng mở riêng cũng theo đúng người xem.
        tk_dong = next(b for b in (await nk.tim())["items"] if b["kind"] == "conversation.takeover")
        mot = await nk.mot(tk_dong["id"], nguoi=moi_quyen)
        assert any(lk["loai"] == "hoi_thoai" and lk["mo_duoc"] for lk in mot["lien_ket"])

    _chay(kiem)


def test_api_loc_muc_do_gop_va_lien_ket_tren_app_that(app_that):
    """Đường HTTP: tham số mới, 422 cho mức lạ, quản trị mở được hội thoại."""
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị B", "cho em hỏi giá")
    cid = str(_hoi_thoai_dau(app_that)["id"])

    async def ghi(c):
        for _ in range(3):
            await db.log_event("erp.ngat_mach", ten="gia")
        await db.log_event("conversation.takeover", actor="admin", ref_id=uuid.UUID(c))
    _sql(app_that, ghi, cid)

    assert qt.get("/api/nhat-ky?muc_do=quan_trong").status_code == 422
    dm = qt.get("/api/nhat-ky/danh-muc").json()
    assert [m["ma"] for m in dm["muc_do"]] == ["nghiep_vu", "van_hanh", "ky_thuat"]

    r = qt.get("/api/nhat-ky?muc_do=nghiep_vu&gom=true")
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert "erp.ngat_mach" not in [b["kind"] for b in items]
    tq = next(b for b in items if b["kind"] == "conversation.takeover")
    assert any(lk["loai"] == "hoi_thoai" and lk["id"] == cid and lk["mo_duoc"]
               for lk in tq["lien_ket"])

    gop = qt.get("/api/nhat-ky?muc_do=ky_thuat&gom=true").json()["items"]
    ngat = [b for b in gop if b["kind"] == "erp.ngat_mach"]
    assert len(ngat) == 1 and ngat[0]["gom"]["so_lan"] == 3
    # Mã kỹ thuật chỉ còn ở trường `kind`, tên hiển thị là tiếng Việt.
    assert ngat[0]["hanh_dong"] != "erp.ngat_mach"
    csv = qt.get("/api/nhat-ky/xuat.csv?muc_do=nghiep_vu")
    assert csv.status_code == 200 and "erp.ngat_mach" not in csv.text
