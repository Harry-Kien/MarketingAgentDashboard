"""
Hệ thống giao việc (phiếu việc mục 14) — chạy thật trên Postgres.

Ràng buộc canh ở đây, mỗi cái một cách hỏng IM LẶNG:

  · Phân công tự động KHÔNG BAO GIỜ giao "gần đúng": người ngoài ca, người
    chưa có lịch, người tắt sẵn sàng, người khác kênh đều bị loại; không ai
    đủ điều kiện thì việc ở Chưa phân công VÀ người điều phối được báo.
  · Xoay vòng: người lâu nhất chưa được giao việc được chọn trước.
  · Mọi đường đổi người nhận / trạng thái / kết quả đều vào lịch sử (trigger
    0061) với đúng người thao tác — kể cả đường chuyển việc ở màn Nhân sự.
  · Chuông: được chuyển việc, việc bị hủy, việc chưa phân công, quá hạn (một
    lần, và lại một lần khi hạn đổi).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import nguoi_thu, toan_quyen  # noqa: E402
from test_api_cong_viec import (  # noqa: E402
    SEP_ID,
    _app,
    _dung_hoi_thoai,
    _dung_luoc_do,
    _sql,
)

MIG = ROOT / "agent" / "migrations" / "versions" / "0061_he_thong_giao_viec.sql"


# ------------------------------------------------------------------ không cần CSDL

def test_nhan_trang_thai_theo_phieu_viec_ma_giu_nguyen():
    """Mục 14.7: mã cũ (dữ liệu đang chạy dùng chúng), nhãn mới."""
    from agent.core import cong_viec as cv

    assert cv.TRANG_THAI == ("moi", "dang_lam", "xong", "huy")
    assert cv.NHAN_TRANG_THAI == {
        "moi": "Chờ xử lý", "dang_lam": "Đang thực hiện",
        "xong": "Hoàn thành", "huy": "Đã hủy"}
    assert cv.NHAN_CHUA_PHAN_CONG == "Chưa phân công"
    assert set(cv.NHAN_NGUON) == set(cv.NGUON)
    assert cv.NHAN_NGUON["agent"] == "AI đề xuất"


def test_loai_lich_su_trong_ma_khop_check_cua_migration():
    from agent.core import cong_viec as cv

    sql = MIG.read_text(encoding="utf-8")
    khoi = sql[sql.index("loai           TEXT NOT NULL CHECK"):sql.index("-- Người thao tác.")]
    assert set(re.findall(r"'([a-z_]+)'", khoi)) == set(cv.LOAI_LICH_SU)


def test_quy_tac_tao_viec_nhan_giao_tu_dong_va_chan_gia_tri_la():
    from agent.omnichannel import tu_dong

    ra = tu_dong.kiem_hanh_dong([{"loai": "tao_viec", "tieu_de": "Gọi lại khách",
                                  "giao_tu_dong": True}])
    assert ra == [{"loai": "tao_viec", "tieu_de": "Gọi lại khách", "giao_tu_dong": True}]
    # Không bật thì quy tắc lưu y như trước — quy tắc cũ đọc lại không đổi.
    assert tu_dong.kiem_hanh_dong([{"loai": "tao_viec", "tieu_de": "Gọi lại"}]) == [
        {"loai": "tao_viec", "tieu_de": "Gọi lại"}]
    with pytest.raises(tu_dong.QuyTacHong):
        tu_dong.kiem_hanh_dong([{"loai": "tao_viec", "tieu_de": "Gọi lại",
                                 "giao_tu_dong": "co"}])


def test_dat_ngu_canh_ngoai_giao_dich_thi_no():
    """Ngoài giao dịch biến phiên chết ngay — lịch sử ghi sai người mà không lỗi."""
    from agent.core import cong_viec as cv

    class _Conn:
        def is_in_transaction(self):
            return False

    with pytest.raises(RuntimeError):
        asyncio.run(cv.dat_ngu_canh(_Conn(), nguoi_id="x"))


# ------------------------------------------------------------------ dựng dữ liệu

def _chay(url: str, coro_fn, *args):
    import asyncpg

    async def chay():
        conn = await asyncpg.connect(url)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            return await coro_fn(conn, *args)
        finally:
            await conn.close()

    return asyncio.run(chay())


async def _nhan_vien_db(conn, ten: str, *, ca: bool = True, san_sang: bool | None = None,
                        vai_tro: str = "Nhân viên") -> str:
    """Nhân viên THẬT trong CSDL: vai trò (quyền ở SQL), lịch ca 24/7 nếu `ca`."""
    uid = await conn.fetchval(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
        "VALUES ($1,'x',$1) RETURNING id", ten)
    await conn.execute(
        "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
        "SELECT $1, id FROM vai_tro WHERE ten = $2", uid, vai_tro)
    if ca:
        for thu in range(1, 8):
            await conn.execute(
                "INSERT INTO ca_truc (nguoi_dung_id, thu, bat_dau, ket_thuc) "
                "VALUES ($1, $2, 0, 1440)", uid, thu)
    if san_sang is not None:
        doi = await conn.fetchval(
            "INSERT INTO teams (name) VALUES ($1) ON CONFLICT (name) DO UPDATE "
            "SET name = EXCLUDED.name RETURNING id", "Đội CSKH")
        await conn.execute(
            "INSERT INTO team_members (team_id, user_id, is_available) VALUES ($1,$2,$3)",
            doi, uid, san_sang)
    return str(uid)


async def _sep_la_quan_tri(conn) -> None:
    """Người đăng nhập trong test (SEP_ID) là Quản trị THẬT ở CSDL: người điều phối."""
    await conn.execute(
        "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten) "
        "VALUES ($1,'sep','x','Sếp') ON CONFLICT DO NOTHING", SEP_ID)
    await conn.execute(
        "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
        "SELECT $1, id FROM vai_tro WHERE ten = 'Quản trị' ON CONFLICT DO NOTHING", SEP_ID)


def _sep() -> dict:
    return nguoi_thu("cong_viec.doc", "cong_viec.sua", "cong_viec.giao",
                     "cong_viec.xem_tat_ca", "hoi_thoai.xem_tat_ca", id=SEP_ID, ten="sep")


def _dung(url: str, *nhan_vien: tuple) -> list[str]:
    """Dựng lược đồ + sếp + các nhân viên `(ten, kwargs)`. Trả id theo thứ tự."""
    _dung_luoc_do(url)

    async def chay(conn):
        await _sep_la_quan_tri(conn)
        return [await _nhan_vien_db(conn, ten, **kw) for ten, kw in nhan_vien]

    return _chay(url, chay)


def _thong_bao(url: str, uid: str) -> list[tuple[str, str]]:
    async def chay(conn):
        return [(r["loai"], r["tieu_de"]) for r in await conn.fetch(
            "SELECT loai, tieu_de FROM thong_bao WHERE nguoi_nhan_id = $1 "
            "ORDER BY tao_luc", UUID(uid))]
    return _chay(url, chay)


def _lich_su(url: str, vid: str) -> list[dict]:
    async def chay(conn):
        return [dict(r) for r in await conn.fetch(
            "SELECT loai, nguoi_id, tu_nguoi, den_nguoi, tu_trang_thai, den_trang_thai, ghi_chu "
            "FROM cong_viec_lich_su WHERE cong_viec_id = $1 ORDER BY tao_luc, id", UUID(vid))]
    return _chay(url, chay)


# ------------------------------------------------------------------ phân công tự động

def test_tu_dong_xoay_vong_nguoi_trong_ca_lau_nhat_chua_duoc_giao(csdl_kiem_thu):
    an, binh = _dung(csdl_kiem_thu, ("an", {}), ("binh", {}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        nhan = []
        for i in range(3):
            r = khach.post("/api/cong-viec", json={"tieu_de": f"Việc {i}", "giao_tu_dong": True})
            assert r.status_code == 201, r.text
            nhan.append(r.json()["nguoi_nhan"])
    dau = min(an, binh)  # hoà (chưa ai được giao) thì theo id — ổn định
    sau = max(an, binh)
    assert nhan == [dau, sau, dau], "phải xoay vòng, không dồn hết cho một người"
    assert _thong_bao(csdl_kiem_thu, dau)[0] == ("duoc_giao_viec", "Bạn được giao một việc")


def test_tu_dong_loai_nguoi_ngoai_ca_chua_co_lich_tat_san_sang(csdl_kiem_thu):
    """
    Người CHƯA xếp ca: bộ định tuyến hội thoại coi là luôn trực, ở đây thì
    không — không biết họ có đang làm hay không thì không giao (mục 14.6).
    """
    async def ngoai_ca(conn, uid):
        # Nghỉ đang phủ lên lúc này -> ngoài ca dù có lịch 24/7.
        await conn.execute(
            "INSERT INTO ca_nghi (nguoi_dung_id, tu_luc, den_luc) "
            "VALUES ($1, now() - interval '1 hour', now() + interval '1 hour')", UUID(uid))

    _chua_lich, _tat, nghi, dung = _dung(
        csdl_kiem_thu, ("chualich", {"ca": False}), ("tat", {"san_sang": False}),
        ("nghi", {}), ("dung", {"san_sang": True}))
    _chay(csdl_kiem_thu, ngoai_ca, nghi)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        for i in range(3):
            r = khach.post("/api/cong-viec", json={"tieu_de": f"Việc {i}", "giao_tu_dong": True})
            assert r.json()["nguoi_nhan"] == dung, r.json()


def test_khong_ai_du_dieu_kien_thi_chua_phan_cong_va_bao_dieu_phoi(csdl_kiem_thu):
    from agent.core import giao_viec

    (khong_lich,) = _dung(csdl_kiem_thu, ("khonglich", {"ca": False}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/cong-viec", json={"tieu_de": "Gọi lại khách", "giao_tu_dong": True})
        assert r.status_code == 201
        d = r.json()
        assert d["nguoi_nhan"] is None
        assert d["ly_do_khong_giao"] == giao_viec.LY_DO_KHONG_CO_LICH
        v = khach.get(f"/api/cong-viec/{d['id']}").json()["cong_viec"]
        assert v["chua_phan_cong"] is True and v["trang_thai"] == "moi"
        ds = khach.get("/api/cong-viec?chua_phan_cong=true").json()["cong_viec"]
        assert [x["id"] for x in ds] == [d["id"]]
    # Người tạo là người điều phối duy nhất -> không tự báo mình; nhân viên
    # không có quyền giao -> không bị báo.
    assert _thong_bao(csdl_kiem_thu, khong_lich) == []


def test_tu_dong_chi_giao_nguoi_thuoc_kenh_cua_hoi_thoai(csdl_kiem_thu):
    """Giao nhầm kênh = đưa tên khách và lý do chuyển người sang người không được thấy."""
    ngoai, trong = _dung(csdl_kiem_thu, ("ngoai", {}), ("trong", {}))

    async def kenh(conn):
        cid = await _dung_hoi_thoai(conn, ext="ext-kenh", ten_khach="Chị Hoa")
        await conn.execute(
            "INSERT INTO account_memberships (account_id, user_id) "
            "SELECT account_id, $2 FROM conversations WHERE id = $1", cid, UUID(trong))
        return str(cid)

    cid = _chay(csdl_kiem_thu, kenh)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        for i in range(2):
            r = khach.post("/api/cong-viec", json={
                "tieu_de": f"Gọi lại chị Hoa {i}", "conversation_id": cid, "giao_tu_dong": True})
            assert r.json()["nguoi_nhan"] == trong, "không được giao cho người ngoài kênh"
        # Việc KHÔNG gắn hội thoại thì ai trong ca cũng nhận được: người
        # ngoài kênh (chưa từng được giao) được chọn trước theo xoay vòng.
        r = khach.post("/api/cong-viec", json={"tieu_de": "Việc chung", "giao_tu_dong": True})
        assert r.json()["nguoi_nhan"] == ngoai


def test_tu_dong_giao_viec_co_san_va_khong_giat_viec_da_co_nguoi(csdl_kiem_thu):
    from agent.core import giao_viec

    (an,) = _dung(csdl_kiem_thu, ("an", {}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec", json={"tieu_de": "Việc trống"}).json()["id"]
        r = khach.post(f"/api/cong-viec/{vid}/tu-dong-giao")
        assert r.status_code == 200 and r.json()["nguoi_nhan"] == an
        r = khach.post(f"/api/cong-viec/{vid}/tu-dong-giao")
        assert r.json() == {"nguoi_nhan": None, "nguoi_nhan_ten": None,
                            "ly_do": giao_viec.LY_DO_DA_CO_NGUOI}


def test_tu_dong_giao_can_quyen_giao(csdl_kiem_thu):
    _dung(csdl_kiem_thu)
    nv = nguoi_thu("cong_viec.doc", "cong_viec.sua", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.post("/api/cong-viec", json={"tieu_de": "Việc", "giao_tu_dong": True})
        assert r.status_code == 403


# ------------------------------------------------------------------ lịch sử

def test_lich_su_ghi_tao_giao_chuyen_trang_thai_ket_qua_tien_do(csdl_kiem_thu):
    an, binh = _dung(csdl_kiem_thu, ("an", {}), ("binh", {}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Hoa"}).json()["id"]
        assert khach.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": an}).status_code == 200
        assert khach.put(f"/api/cong-viec/{vid}", json={
            "nguoi_nhan": binh, "ghi_chu": "An nghỉ phép"}).status_code == 200
        assert khach.post(f"/api/cong-viec/{vid}/tien-do",
                          json={"noi_dung": "Đã gọi, khách hẹn chiều"}).status_code == 201
        assert khach.put(f"/api/cong-viec/{vid}", json={
            "trang_thai": "xong", "ket_qua": "Khách đồng ý nhận hàng"}).status_code == 200
        ct = khach.get(f"/api/cong-viec/{vid}").json()

    ls = _lich_su(csdl_kiem_thu, vid)
    assert [x["loai"] for x in ls] == ["tao", "giao", "chuyen", "tien_do", "trang_thai", "ket_qua"]
    assert all(str(x["nguoi_id"]) == SEP_ID for x in ls), "mọi dòng phải mang đúng người thao tác"
    chuyen = ls[2]
    assert (str(chuyen["tu_nguoi"]), str(chuyen["den_nguoi"])) == (an, binh)
    assert chuyen["ghi_chu"] == "An nghỉ phép"
    assert (ls[4]["tu_trang_thai"], ls[4]["den_trang_thai"]) == ("moi", "xong")
    assert ls[5]["ghi_chu"] == "Khách đồng ý nhận hàng"
    # Màn chi tiết đọc cùng lịch sử, có nhãn tiếng Việt.
    assert [x["nhan_loai"] for x in ct["lich_su"]][:3] == ["Tạo việc", "Giao việc", "Chuyển việc"]
    assert ct["lich_su"][4]["den_trang_thai"] == "Hoàn thành"
    assert ct["cong_viec"]["ket_qua"] == "Khách đồng ý nhận hàng"
    # Người được chuyển nhận chuông "chuyển", không phải "giao" lần nữa.
    assert ("duoc_giao_viec", "Bạn được chuyển một việc") in _thong_bao(csdl_kiem_thu, binh)


def test_lich_su_ghi_ca_duong_khong_qua_api_cong_viec(csdl_kiem_thu):
    """
    Trigger, không phải API, là chốt: đường cập nhật thẳng bằng SQL (định
    tuyến, đóng theo hội thoại, mã cũ) vẫn để lại dấu — người thao tác NULL
    = hệ thống, đúng sự thật hơn là đoán.
    """
    (an,) = _dung(csdl_kiem_thu, ("an", {}))
    vid = str(_sql(csdl_kiem_thu, "INSERT INTO cong_viec (tieu_de, nguon) "
                                  "VALUES ('Việc máy', 'tu_dong') RETURNING id"))
    _sql(csdl_kiem_thu, "UPDATE cong_viec SET nguoi_nhan = $2, uu_tien = 'gap' WHERE id = $1",
         UUID(vid), UUID(an))
    ls = _lich_su(csdl_kiem_thu, vid)
    assert [x["loai"] for x in ls] == ["tao", "giao", "sua"]
    assert all(x["nguoi_id"] is None for x in ls)
    assert ls[2]["ghi_chu"] == "uu_tien"


def test_chuyen_viec_o_man_nhan_su_ghi_lich_su_dung_nguoi(csdl_kiem_thu):
    from agent.api.nhan_su import router as ns_router

    an, binh = _dung(csdl_kiem_thu, ("an", {}), ("binh", {}))
    vid = str(_sql(csdl_kiem_thu, "INSERT INTO cong_viec (tieu_de, nguoi_nhan) "
                                  "VALUES ('Việc của An', $1) RETURNING id", UUID(an)))
    sep = toan_quyen(id=SEP_ID, ten="sep")
    app = _app(csdl_kiem_thu, sep)
    app.include_router(ns_router)
    with TestClient(app) as khach:
        r = khach.post(f"/api/nguoi-dung/{an}/chuyen-viec",
                       json={"nguoi_nhan": binh, "hoi_thoai": False, "cong_viec": True})
        assert r.status_code == 200, r.text
    ls = _lich_su(csdl_kiem_thu, vid)
    assert ls[-1]["loai"] == "chuyen" and str(ls[-1]["nguoi_id"]) == SEP_ID
    assert "Chuyển việc từ an sang binh" in ls[-1]["ghi_chu"]


# ------------------------------------------------------------------ chuông

def test_huy_viec_bao_nguoi_dang_lam(csdl_kiem_thu):
    (an,) = _dung(csdl_kiem_thu, ("an", {}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec", json={"tieu_de": "Gọi lại", "nguoi_nhan": an}).json()["id"]
        assert khach.put(f"/api/cong-viec/{vid}", json={
            "trang_thai": "huy", "ghi_chu": "khách tự xử lý"}).status_code == 200
    assert _thong_bao(csdl_kiem_thu, an) == [
        ("duoc_giao_viec", "Bạn được giao một việc"), ("viec_huy", "Việc đã bị hủy")]


def test_qua_han_bao_mot_lan_va_bao_lai_khi_doi_han(csdl_kiem_thu):
    from agent.core import giao_viec

    (an,) = _dung(csdl_kiem_thu, ("an", {}))
    qua = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec", json={
            "tieu_de": "Gọi lại", "nguoi_nhan": an, "han": qua}).json()["id"]
        assert khach.portal.call(giao_viec.quet_viec_qua_han) == 1
        assert khach.portal.call(giao_viec.quet_viec_qua_han) == 0, "không reo lại mỗi lượt"
        # Đổi hạn (vẫn đã qua) = lần quá hạn mới.
        qua2 = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert khach.put(f"/api/cong-viec/{vid}", json={"han": qua2}).status_code == 200
        assert khach.portal.call(giao_viec.quet_viec_qua_han) == 1
        # Việc xong rồi thì không bao giờ quá hạn.
        khach.put(f"/api/cong-viec/{vid}", json={"trang_thai": "xong", "han": qua2})
        assert khach.portal.call(giao_viec.quet_viec_qua_han) == 0
    assert [x for x in _thong_bao(csdl_kiem_thu, an) if x[0] == "viec_qua_han"] == [
        ("viec_qua_han", "Việc đã quá hạn")]  # chống dội: dòng chưa đọc được đẩy lên


def test_viec_ai_de_xuat_chua_phan_cong_nguon_agent_va_bao_dieu_phoi(csdl_kiem_thu):
    """Mục 14.3: AI đề xuất việc, KHÔNG tự chọn người làm."""
    from agent.core import cong_viec as cv

    _dung(csdl_kiem_thu)

    async def don(conn):
        cid = await _dung_hoi_thoai(conn, ext="ext-ai", ten_khach="Chị Mai")
        oid = await conn.fetchval(
            "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, "
            "khach_dia_chi, items) VALUES ('DH-AI-1', $1, 'Chị Mai', '0901', 'HN', '[]') "
            "RETURNING id", cid)
        return cid, oid

    cid, oid = _chay(csdl_kiem_thu, don)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.portal.call(lambda: cv.tao_tu_yeu_cau_xu_ly_don(
            order_id=oid, conversation_id=cid, loai="huy",
            tieu_de="Xử lý yêu cầu hủy đơn DH-AI-1", mo_ta="khách đổi ý"))
        v = khach.get(f"/api/cong-viec/{vid}").json()["cong_viec"]
    assert v["nguon"] == "agent" and v["nhan_nguon"] == "AI đề xuất"
    assert v["nguoi_nhan"] is None and v["chua_phan_cong"] is True
    assert ("viec_chua_giao", "Việc chưa phân công") in _thong_bao(csdl_kiem_thu, SEP_ID)


# ------------------------------------------------------------------ tạo, lọc, liên kết

def test_tao_tu_hoi_thoai_kenh_khac_thi_404(csdl_kiem_thu):
    _dung(csdl_kiem_thu)
    cid = str(_chay(csdl_kiem_thu, lambda c: _dung_hoi_thoai(c, ext="ext-x")))
    nv = nguoi_thu("cong_viec.doc", "cong_viec.sua", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.post("/api/cong-viec", json={"tieu_de": "Việc lén", "conversation_id": cid})
        assert r.status_code == 404


def test_tao_tu_hoi_thoai_tu_gan_khach_va_don_theo_ma(csdl_kiem_thu):
    _dung(csdl_kiem_thu)

    async def dung(conn):
        cid = await _dung_hoi_thoai(conn, ext="ext-y", ten_khach="Chị Lan")
        await conn.execute(
            "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, "
            "khach_dia_chi, items) VALUES ('DH-77', $1, 'Chị Lan', '0902', 'HN', '[]')", cid)
        return str(cid)

    cid = _chay(csdl_kiem_thu, dung)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/cong-viec", json={
            "tieu_de": "Xác nhận địa chỉ", "conversation_id": cid, "ma_don": "DH-77"})
        assert r.status_code == 201, r.text
        v = khach.get(f"/api/cong-viec/{r.json()['id']}").json()["cong_viec"]
        assert v["conversation_id"] == cid and v["contact_id"] and v["ma_don"] == "DH-77"
        assert v["khach_ten"] == "Chị Lan"
        assert khach.post("/api/cong-viec", json={
            "tieu_de": "Đơn ma", "ma_don": "KHONG-CO"}).status_code == 422
        # Tìm theo mã đơn, theo tên khách.
        for tu in ("DH-77", "lan"):
            ds = khach.get("/api/cong-viec", params={"q": tu}).json()["cong_viec"]
            assert [x["tieu_de"] for x in ds] == ["Xác nhận địa chỉ"], tu


def test_giao_cho_nguoi_khong_xem_duoc_viec_thi_422(csdl_kiem_thu):
    (khong_quyen,) = _dung(csdl_kiem_thu, ("khongquyen", {"vai_tro": "khong-co"}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        r = khach.post("/api/cong-viec", json={"tieu_de": "Việc", "nguoi_nhan": khong_quyen})
        assert r.status_code == 422 and "cong_viec.doc" in r.json()["detail"]


def test_tong_quan_dem_theo_pham_vi_va_nguoi_trong_ca(csdl_kiem_thu):
    an, _chua_lich = _dung(csdl_kiem_thu, ("an", {}), ("chualich", {"ca": False}))
    qua = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        khach.post("/api/cong-viec", json={"tieu_de": "Chưa ai nhận"})
        khach.post("/api/cong-viec", json={"tieu_de": "Của An", "nguoi_nhan": an, "han": qua})
        d = khach.get("/api/cong-viec/tong-quan").json()
    assert d["dem"]["chua_phan_cong"] == 1 and d["dem"]["qua_han"] == 1
    assert [v["tieu_de"] for v in d["chua_phan_cong"]] == ["Chưa ai nhận"]
    theo_id = {n["id"]: n for n in d["nhan_vien"]}
    assert theo_id[an]["trong_ca_that"] is True and theo_id[an]["so_qua_han"] == 1
    assert theo_id[_chua_lich]["trong_ca_that"] is False, (
        "người chưa xếp ca không được hiện là đang trong ca")
    assert d["tu_dong_duoc"] == 1


def test_tong_quan_nhan_vien_thuong_khong_thay_tai_dong_nghiep(csdl_kiem_thu):
    _dung(csdl_kiem_thu)
    nv = nguoi_thu("cong_viec.doc", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        d = khach.get("/api/cong-viec/tong-quan").json()
    assert d["nhan_vien"] is None and d["tu_dong_duoc"] is None


# ------------------------------------------------------------------ giao diện (tĩnh)

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
SRC = (ROOT / "dashboard" / "src" / "25-cong-viec.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def test_man_danh_sach_cong_viec_gan_vao_tab():
    assert 'GAN_TAB["cv-danh-sach"]' in SRC
    assert 'GAN_TAB["cv-ca-truc-viec"]' in SRC
    assert 'data-gan="cv-ca-truc-viec"' in HTML
    assert SRC in JS, "app.js chưa đóng gói lại"


def test_man_cong_viec_goi_du_cac_duong_api():
    for duong in ("/cong-viec/tong-quan", "/cong-viec/nguoi-nhan-duoc", "/tien-do",
                  "/tu-dong-giao", "giao_tu_dong", "chua_phan_cong", "ghi_chu", "ket_qua"):
        assert duong in SRC, duong


def test_tao_cong_viec_tu_hoi_thoai():
    """Mục 14.3: tạo việc NGAY từ hội thoại, gắn sẵn hội thoại + khách."""
    hoi_thoai = (ROOT / "dashboard" / "src" / "03-hoi-thoai.js").read_text(encoding="utf-8")
    assert 'id="btn-tao-viec-ht"' in hoi_thoai
    assert "#btn-tao-viec-ht" in SRC and "conversation_id" in SRC


def test_chuong_cong_viec_mo_chi_tiet_viec():
    tb = (ROOT / "dashboard" / "src" / "19-thong-bao.js").read_text(encoding="utf-8")
    assert "window.moCongViec" in tb and "window.moCongViec =" in SRC


def test_lien_ket_hoi_thoai_khach_don_bam_duoc():
    """Mục 14.8: mở thẳng ngữ cảnh từ việc."""
    for ham in ('doiMan("hoithoai")', "openCustomer(", 'doiMan("donhang")'):
        assert ham in SRC, ham


def test_khong_con_dau_xung_dot_merge_trong_giao_dien():
    """
    Một dòng `=======` sót lại từ lần gộp nhánh làm trình duyệt bỏ luôn luật
    CSS đứng sau nó — không lỗi, không cảnh báo, chỉ là giao diện lệch.
    """
    for tep in [ROOT / "dashboard" / "app.css", ROOT / "dashboard" / "index.html",
                *sorted((ROOT / "dashboard" / "src").glob("*.js"))]:
        for so, dong in enumerate(tep.read_text(encoding="utf-8").splitlines(), 1):
            assert not re.match(r"^(<{7}|={7}|>{7})( |$)", dong), f"{tep.name}:{so}"
