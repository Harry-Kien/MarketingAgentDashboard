"""
Thông báo nội bộ (mục 19) và "chuyển giao không sinh việc" (mục 14.2).

Phần đụng CSDL chạy trên `app_that` — app đầy đủ, Postgres thật, đăng nhập
thật qua cookie phiên — vì hai thứ quan trọng nhất ở đây là PHẠM VI (ai thấy
thông báo của ai) và NỐI DÂY (chuyển giao thật có sinh thông báo thật
không). Router trần với người giả không kiểm được cả hai.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import sys
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    Nguoi, _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql,
    _them_thanh_vien,
)


# ------------------------------------------------------------------ helpers

def _mot(app, sql: str, *args):
    from agent import db

    async def doc():
        return await db.fetchrow(sql, *args)
    return _sql(app, doc)


def _nhieu(app, sql: str, *args):
    from agent import db

    async def doc():
        return await db.fetch(sql, *args)
    return _sql(app, doc)


def _chay(app, coro_fn, *args):
    return _sql(app, coro_fn, *args)


def _ghi_bao(monkeypatch) -> list[str]:
    """Bắt tin báo NGOÀI dashboard (Telegram/n8n) — không gửi ra mạng."""
    from agent import canh_gac

    bao: list[str] = []
    monkeypatch.setattr(canh_gac, "bao_nhan_vien_nen",
                        lambda tieu_de, chi_tiet: bao.append(chi_tiet))
    return bao


def _cid_moi_nhat(app, tk: str) -> str:
    return str(_mot(app, "SELECT id FROM conversations WHERE account_id = $1::uuid "
                         "ORDER BY created_at DESC LIMIT 1", tk)["id"])


def _tb(nguoi: Nguoi, **q) -> dict:
    r = nguoi.get("/api/toi/thong-bao", params=q)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ 14.2: chuyển giao

def test_ai_chuyen_giao_sinh_THONG_BAO_khong_sinh_CONG_VIEC(app_that, monkeypatch):
    """
    Mục 14.2: AI chuyển giao KHÔNG tạo việc "Khách cần người trả lời" nữa —
    trùng nghiệp vụ với chính hội thoại trong hàng chờ người. Thay vào đó
    thành viên kênh có quyền nhận hội thoại được một thông báo, và tin báo
    ngoài dashboard vẫn đi như trước.
    """
    bao = _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)                 # agent TẮT -> mọi tin chuyển người
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Hoa", "kem này dùng cho bà bầu được không")
    cid = _cid_moi_nhat(app_that, tk)

    assert _mot(app_that, "SELECT count(*) n FROM cong_viec")["n"] == 0, (
        "chuyển giao vẫn đẻ công việc — trùng nghiệp vụ với hàng chờ người")
    d = _tb(lan)
    assert d["chua_doc"] == 1
    t = d["thong_bao"][0]
    assert t["loai"] == "ai_chuyen_giao" and t["da_doc"] is False
    assert t["lien_ket"] == {"loai": "hoi_thoai", "id": cid}
    assert t["ten_khach"] == "Chị Hoa", "tên khách đọc qua hội thoại lúc hiển thị"
    assert len(bao) == 1, "tin báo ngoài dashboard phải giữ"
    # Tin báo ngoài đi qua bên thứ ba: KHÔNG tên, KHÔNG lời khách.
    assert "Chị Hoa" not in bao[0] and "bầu" not in bao[0]


def test_khach_nhan_them_khong_doi_chuong_va_khong_doi_tin_bao(app_that, monkeypatch):
    """
    Trước đây chốt "một việc mỗi hội thoại" làm luôn việc chống dội. Nay chốt
    "một thông báo chưa đọc mỗi người mỗi chuyện" (chỉ mục duy nhất 0055) làm
    thay: công tắc toàn cục tắt thì MỖI tin khách đi qua đường chuyển giao.
    """
    from agent import runtime

    bao = _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    monkeypatch.setitem(runtime.STATE, "enabled", False)
    from tests.test_gui_tin_va_dieu_phoi import _khach

    gui = _khach(app_that, tk)
    for chu in ("alo", "shop ơi", "có ai không"):
        gui(chu)
    so = _mot(app_that, "SELECT count(*) n FROM thong_bao WHERE loai = 'ai_chuyen_giao'")["n"]
    nguoi = _mot(app_that, "SELECT count(DISTINCT nguoi_nhan_id) n FROM thong_bao")["n"]
    assert so == nguoi >= 1, "ba tin khách thành nhiều dòng chuông cho cùng một người"
    assert len(bao) == 1, "ba tin khách thành ba tin Telegram"


def test_lan_chuyen_giao_SAU_khi_giai_quyet_la_chuyen_moi(app_that, monkeypatch):
    """
    Lỗi việc tự sinh từng mắc (16.11.2026), nay canh cho thông báo: người trực
    CHƯA đọc thông báo lần trước, hội thoại đã giải quyết, khách quay lại —
    khoá chống dội không được nuốt lần này, và tin báo ngoài phải đi lại.
    """
    bao = _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    from tests.test_gui_tin_va_dieu_phoi import _khach

    gui = _khach(app_that, tk)
    gui("cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    assert _tb(qt)["chua_doc"] == 1 and len(bao) == 1

    r = qt.post(f"/api/inbox/conversations/{cid}/giai-quyet")
    assert r.status_code == 200, (
        "không còn việc tự sinh nên không có gì chặn giải quyết", r.text)
    gui("cho em hỏi thêm")
    assert _tb(qt)["chua_doc"] == 2, "lần chuyển giao sau bị nuốt"
    assert len(bao) == 2, "lần chuyển giao sau không báo ra ngoài"


def test_tra_cho_agent_roi_chuyen_giao_lai_cung_la_chuyen_moi(app_that, monkeypatch):
    bao = _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    from tests.test_gui_tin_va_dieu_phoi import _khach, _phien_ban

    gui = _khach(app_that, tk)
    gui("cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    r = qt.post(f"/api/inbox/conversations/{cid}/takeover",
                json={"expected_version": _phien_ban(app_that, cid), "reason": "nhận khách"})
    assert r.status_code == 200, r.text
    r = qt.post(f"/api/inbox/conversations/{cid}/release",
                json={"expected_version": r.json()["version"], "reason": "xong"})
    assert r.status_code == 200, r.text
    gui("alo shop")
    assert len(bao) == 2
    assert _mot(app_that, "SELECT count(*) n FROM thong_bao WHERE loai = 'ai_chuyen_giao' "
                          "AND conversation_id = $1::uuid", cid)["n"] == 2


# ------------------------------------------------------------------ người nhận

def test_nguoi_nhan_thanh_vien_kenh_co_quyen_khong_phai_nguoi_ngoai(app_that):
    """
    Chưa giao: CHỈ thành viên kênh có `hoi_thoai.nhan`. Nhân viên kênh khác
    không được thấy tên khách kênh này qua chuông (cùng lý do với phạm vi
    công việc 16.11.2026). Người bị khoá không nhận.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")           # KHÔNG thuộc kênh
    khoa_id, _ = _nhan_vien_moi(qt, "khoa")
    xem_id, xem = _nhan_vien_moi(qt, "xem", vai_tro=None)  # thuộc kênh, không quyền
    for uid in (lan_id, khoa_id, xem_id):
        _them_thanh_vien(app_that, tk, uid)
    _mot(app_that, "UPDATE nguoi_dung SET khoa = true WHERE id = $1::uuid RETURNING 1", khoa_id)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")

    nhan = {str(r["nguoi_nhan_id"]) for r in _nhieu(
        app_that, "SELECT nguoi_nhan_id FROM thong_bao WHERE loai = 'ai_chuyen_giao'")}
    assert lan_id in nhan
    assert minh_id not in nhan, "nhân viên kênh khác nhận thông báo kênh này"
    assert khoa_id not in nhan, "tài khoản đã khoá vẫn nhận thông báo"
    assert xem_id not in nhan, "người không có quyền nhận hội thoại vẫn được báo"
    assert _tb(minh)["thong_bao"] == []
    assert _tb(xem)["thong_bao"] == []


def test_kenh_khong_ai_phu_trach_thi_bao_nguoi_quan_ly(app_that):
    """
    Kênh chưa phân người mà chuông không reo ở đâu = hỏng im lặng. Lui về
    người có `hoi_thoai.xem_tat_ca` (Quản trị có mọi quyền).
    """
    from agent import db
    from agent.core import thong_bao_noi_bo as tb

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _mot(app_that, "DELETE FROM account_memberships WHERE account_id = $1::uuid RETURNING 1", tk)
    lan_id, lan = _nhan_vien_moi(qt, "lan")              # không thuộc kênh
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)

    async def nhan():
        async with db.pool().acquire() as conn:
            return await tb.nguoi_nhan_hoi_thoai(conn, cid, quyen="hoi_thoai.nhan")
    ds = {str(x) for x in _chay(app_that, nhan)}
    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])
    assert ds == {qt_id}
    assert _tb(qt)["chua_doc"] == 1
    assert _tb(lan)["chua_doc"] == 0


def test_hoi_thoai_da_giao_thi_chi_bao_nguoi_dang_cam_sla_bao_them_quan_ly(app_that):
    from agent import db
    from agent.core import thong_bao_noi_bo as tb

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, _ = _nhan_vien_moi(qt, "lan")
    minh_id, _ = _nhan_vien_moi(qt, "minh")
    for uid in (lan_id, minh_id):
        _them_thanh_vien(app_that, tk, uid)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    _mot(app_that, "UPDATE conversations SET assigned_to = $2::uuid WHERE id = $1::uuid "
                   "RETURNING 1", cid, lan_id)

    async def nhan(sla):
        async with db.pool().acquire() as conn:
            return await tb.nguoi_nhan_hoi_thoai(
                conn, cid, quyen="hoi_thoai.nhan", them_quan_ly=sla)
    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])
    assert {str(x) for x in _chay(app_that, nhan, False)} == {lan_id}
    assert {str(x) for x in _chay(app_that, nhan, True)} == {lan_id, qt_id}


# ------------------------------------------------------------------ API: phạm vi + đọc

def test_api_chi_thay_cua_minh_doc_khong_lam_xong_viec_gi(app_that, monkeypatch):
    """
    Mục 19.8: đọc thông báo chỉ là nhắc — không nhận hội thoại, không đóng
    việc, không duyệt gì. Và thông báo của người khác là 404, không phải 403.
    """
    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    r = qt.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Hoa", "nguoi_nhan": lan_id})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    truoc = _mot(app_that, "SELECT state, status, mode, assigned_to, version "
                           "FROM conversations WHERE id = $1::uuid", cid)

    d = _tb(lan)
    assert d["chua_doc"] == 2
    assert {t["loai"] for t in d["thong_bao"]} == {"ai_chuyen_giao", "duoc_giao_viec"}
    viec = next(t for t in d["thong_bao"] if t["loai"] == "duoc_giao_viec")
    assert viec["lien_ket"] == {"loai": "cong_viec", "id": vid}

    # Người khác không đọc / đánh dấu được thông báo của lan.
    assert qt.post(f"/api/toi/thong-bao/{viec['id']}/da-doc").status_code == 404
    assert all(t["id"] != viec["id"] for t in _tb(qt)["thong_bao"])

    assert lan.post(f"/api/toi/thong-bao/{viec['id']}/da-doc").status_code == 200
    assert lan.get("/api/toi/thong-bao/so-chua-doc").json() == {"chua_doc": 1}
    assert [t["loai"] for t in _tb(lan, chua_doc="true")["thong_bao"]] == ["ai_chuyen_giao"]
    r = lan.post("/api/toi/thong-bao/da-doc-het")
    assert r.status_code == 200 and r.json()["da_danh_dau"] == 1
    assert lan.get("/api/toi/thong-bao/so-chua-doc").json() == {"chua_doc": 0}

    assert _mot(app_that, "SELECT trang_thai FROM cong_viec WHERE id = $1::uuid",
                vid)["trang_thai"] == "moi", "đọc thông báo đã làm xong việc"
    sau = _mot(app_that, "SELECT state, status, mode, assigned_to, version "
                         "FROM conversations WHERE id = $1::uuid", cid)
    assert dict(sau) == dict(truoc), "đọc thông báo đã đổi hội thoại"


def test_api_doi_dang_nhap(app_that):
    app_that.cookies.clear()
    assert app_that.get("/api/toi/thong-bao").status_code == 401
    assert app_that.get("/api/toi/thong-bao/so-chua-doc").status_code == 401
    assert app_that.post("/api/toi/thong-bao/da-doc-het").status_code == 401
    assert app_that.post(f"/api/toi/thong-bao/{uuid4()}/da-doc").status_code == 401


def test_phan_trang(app_that):
    from agent.core import thong_bao_noi_bo as tb

    qt = _quan_tri_vao(app_that)
    uid = _mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"]
    for i in range(5):
        _chay(app_that, _ghi_mot, tb, uid, f"Việc {i}")
    d = _tb(qt, gioi_han=2)
    assert len(d["thong_bao"]) == 2 and d["con_nua"] is True and d["chua_doc"] == 5
    sau = _tb(qt, gioi_han=2, bo_qua=4)
    assert len(sau["thong_bao"]) == 1 and sau["con_nua"] is False
    tat_ca = [t["id"] for t in _tb(qt, gioi_han=10)["thong_bao"]]
    assert len(set(tat_ca)) == 5


async def _ghi_mot(tb, uid, tieu_de):
    from agent import db

    async with db.pool().acquire() as conn:
        return await tb._ghi(conn, [uid], loai="duoc_giao_viec", tieu_de=tieu_de)


# ------------------------------------------------------------------ các nguồn khác

def test_giao_viec_cho_nguoi_khac_thi_bao_tu_giao_thi_khong(app_that):
    qt = _quan_tri_vao(app_that)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])
    assert qt.post("/api/cong-viec", json={"tieu_de": "Việc tôi tự làm",
                                           "nguoi_nhan": qt_id}).status_code == 201
    assert _tb(qt)["chua_doc"] == 0, "tự giao cho mình mà vẫn tự báo mình"

    vid = qt.post("/api/cong-viec", json={"tieu_de": "Kiểm kho"}).json()["id"]
    assert _tb(lan)["chua_doc"] == 0
    assert qt.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": lan_id}).status_code == 200
    assert _tb(lan)["thong_bao"][0]["noi_dung"] == "Kiểm kho"
    # Sửa trạng thái việc đã giao không phải "được giao" lần nữa.
    assert qt.put(f"/api/cong-viec/{vid}", json={"trang_thai": "dang_lam"}).status_code == 200
    assert _tb(lan)["chua_doc"] == 1


def test_giao_hoi_thoai_cho_nguoi_khac_thi_bao(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    lan.post("/api/toi/thong-bao/da-doc-het")
    from tests.test_gui_tin_va_dieu_phoi import _phien_ban

    r = qt.post(f"/api/inbox/conversations/{cid}/takeover", json={
        "expected_version": _phien_ban(app_that, cid), "reason": "giao cho Lan",
        "assignee_id": lan_id})
    assert r.status_code == 200, r.text
    d = _tb(lan, chua_doc="true")
    assert [t["loai"] for t in d["thong_bao"]] == ["duoc_giao_hoi_thoai"]
    assert d["thong_bao"][0]["lien_ket"] == {"loai": "hoi_thoai", "id": cid}


def test_dinh_tuyen_tu_dong_giao_xong_thi_bao(app_that):
    from agent.omnichannel.auto_routing import AutoRoutingState, AutoRoutingWorker

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    _them_thanh_vien(app_that, tk, lan_id)
    cid = UUID(_cid_moi_nhat(app_that, tk))

    class Kho:
        async def pending_conversation_ids(self):
            return [cid]

        async def heartbeat(self, worker_id):
            return None

    class DichVu:
        async def route(self, conversation_id):
            return AutoRoutingState(conversation_id=conversation_id,
                                    assigned_to=UUID(lan_id),
                                    assigned_team_id=uuid4(), version=2)

    kq = _chay(app_that, AutoRoutingWorker(Kho(), DichVu()).scan_once, "w")
    assert kq == {"examined": 1, "assigned": 1}
    t = _tb(lan)["thong_bao"]
    assert [x["loai"] for x in t] == ["duoc_giao_hoi_thoai"]
    assert t[0]["noi_dung"] == "Định tuyến tự động"


def test_sla_tre_bao_nguoi_phu_trach_va_quan_ly(app_that):
    from agent.omnichannel.sla import PostgresSlaRepository

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    _mot(app_that, "UPDATE thong_bao SET da_doc_luc = now() RETURNING 1")
    _mot(app_that, "UPDATE conversations SET first_responded_at = NULL, state = 'open', "
                   "first_response_due_at = now() - interval '1 minute' "
                   "WHERE id = $1::uuid RETURNING 1", cid)

    _chay(app_that, PostgresSlaRepository().mark_breaches)
    _chay(app_that, PostgresSlaRepository().mark_breaches)      # lần 2: không báo lại
    for nguoi in (lan, qt):
        t = _tb(nguoi, chua_doc="true")["thong_bao"]
        assert [x["loai"] for x in t] == ["sla_tre"], t
        assert t[0]["lien_ket"] == {"loai": "hoi_thoai", "id": cid}


def test_xoa_hoi_thoai_thi_thong_bao_ve_khach_di_theo(app_that):
    """PDPD: xoá dữ liệu khách (xoá hội thoại) không để lại bản sao trong chuông."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")
    cid = _cid_moi_nhat(app_that, tk)
    assert _tb(qt)["chua_doc"] == 1
    _mot(app_that, "DELETE FROM conversations WHERE id = $1::uuid RETURNING 1", cid)
    assert _tb(qt)["thong_bao"] == []


# ------------------------------------------------------------------ không ném, không im

def test_hong_CSDL_khong_nem_vao_luot_tra_loi_nhung_ghi_loi_va_van_bao_ngoai(
        monkeypatch, caplog):
    from agent import db
    from agent.core import thong_bao_noi_bo as tb

    bao = _ghi_bao(monkeypatch)
    monkeypatch.setattr(db, "_pool", None)
    with caplog.at_level(logging.ERROR, logger="agent.thong_bao"):
        kq = asyncio.run(tb.bao_ai_chuyen_giao(uuid4(), ly_do="x"))
        assert asyncio.run(tb.bao_can_duyet_nhap(uuid4())) == 0
        assert asyncio.run(tb.bao_duoc_giao_viec(uuid4(), uuid4(), boi=None,
                                                 tieu_de_viec="x")) == 0
    assert kq == 0
    assert any("KHÔNG tạo được thông báo" in r.getMessage() for r in caplog.records), (
        "hỏng mà không ghi nhật ký — chuông chết câm")
    assert len(bao) == 1, "thông báo hỏng thì tin báo ngoài là đường duy nhất còn lại"


# ------------------------------------------------------------------ canh tĩnh

def test_loai_trong_ma_khop_check_cua_migration():
    """
    CHECK của `thong_bao.loai` dựng ở 0055, mở rộng ở 0061 (chuông công
    việc). So với bản MỚI NHẤT: migration sau cùng định nghĩa lại ràng buộc
    là bản đang chạy trên CSDL.
    """
    from agent.core import thong_bao_noi_bo as tb

    thu_muc = ROOT / "agent" / "migrations" / "versions"
    dinh_nghia_lai = [p for p in sorted(thu_muc.glob("*.sql"))
                      if "ADD CONSTRAINT thong_bao_loai_check" in p.read_text(encoding="utf-8")]
    if dinh_nghia_lai:
        sql = dinh_nghia_lai[-1].read_text(encoding="utf-8")
        khoi = sql[sql.index("ADD CONSTRAINT thong_bao_loai_check"):]
        khoi = khoi[:khoi.index(");")]
    else:
        sql = (thu_muc / "0055_thong_bao_noi_bo.sql").read_text(encoding="utf-8")
        khoi = sql[sql.index("loai             TEXT"):sql.index("tieu_de          TEXT")]
    assert set(re.findall(r"'([a-z_]+)'", khoi)) == set(tb.LOAI)


def test_khong_con_duong_tu_sinh_viec_khi_chuyen_giao():
    """
    Mục 14.2 nằm trong MÃ: hàm tạo việc từ chuyển người đã gỡ, và không
    đường chuyển giao nào chèn thẳng vào `cong_viec`. Ai thêm lại là test
    này đỏ — không phải một màn Công việc lặng lẽ đầy lên.
    """
    from agent.core import cong_viec
    from agent.omnichannel import agent_loi, hop_thu_ben, tu_dong, xu_ly_tin_vao

    assert not hasattr(cong_viec, "tao_tu_chuyen_nguoi")
    for mod in (xu_ly_tin_vao, agent_loi, hop_thu_ben):
        src = inspect.getsource(mod)
        assert "INSERT INTO cong_viec" not in src, mod.__name__
        assert "tao_tu_chuyen_nguoi" not in src, mod.__name__
        assert "bao_ai_chuyen_giao(" in src, mod.__name__
    nhanh = inspect.getsource(tu_dong.chay_tin_khach)
    nhanh = nhanh[nhanh.index('loai == "chuyen_nguoi"'):]
    assert "bao_ai_chuyen_giao(" in nhanh and "_tao_viec(" not in nhanh
    # Năm chỗ chuyển giao của handle_inbound + tin nhóm.
    assert inspect.getsource(xu_ly_tin_vao).count("bao_ai_chuyen_giao(") == 5


def test_ban_nhap_cho_duyet_thi_bao():
    from agent.omnichannel import xu_ly_tin_vao

    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    doan = src[src.index("stored_draft = not queued_parts"):src.index("if reply.escalate:\n")]
    assert "bao_can_duyet_nhap(cid)" in doan
    assert "not reply.escalate" in doan, "chuyển người đã tự báo — một chuyện hai tiếng chuông"


def test_moi_duong_thong_bao_duoc_khai_mien_tru_tung_cai():
    from agent.core.quyen import MIEN_TRU, moi_route
    from agent.main import app

    duong = {(pt, r.path) for r in moi_route(app.routes)
             if getattr(r, "path", "").startswith("/api/toi/thong-bao")
             for pt in r.methods}
    assert len(duong) == 4
    assert duong <= MIEN_TRU


def test_chuong_nam_o_thanh_tren_khong_co_muc_dieu_huong():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    dau = html[html.index('<header class="masthead">'):html.index("</header>")]
    assert 'id="chuongNut"' in dau and 'id="chuongSo"' in dau
    rail = html[html.index('<nav class="rail"'):html.index("</nav>")]
    assert "thong-bao" not in rail and "thongbao" not in rail and "Thông báo" not in rail
    js = (ROOT / "dashboard" / "src" / "10-vong-lam-moi.js").read_text(encoding="utf-8")
    lam_moi = js[js.index("async function refresh()"):js.index("function startInboxStream")]
    assert "taiSoThongBao()" in lam_moi, "số chưa đọc không làm mới theo vòng"


def test_che_do_goi_y_ban_nhap_cho_duyet_thi_bao_mot_lan_moi_hoi_thoai(app_that, monkeypatch):
    """
    Chế độ Gợi ý: AI soạn nháp cho TỪNG tin khách. Một thông báo chưa đọc
    mỗi hội thoại mỗi người — không phải một dòng cho mỗi tin.
    """
    from agent import runtime
    from agent.core import agent as brain

    async def tra_loi(**kw):
        return brain.Reply(text="Dạ kem này giá 250.000đ ạ", cost_usd=0.0)
    monkeypatch.setattr(brain, "respond", tra_loi)
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    from tests.test_gui_tin_va_dieu_phoi import _khach

    gui = _khach(app_that, tk)
    gui("Kem chống nắng giá bao nhiêu?")
    gui("Còn hàng không shop?")
    cid = _cid_moi_nhat(app_that, tk)
    assert _mot(app_that, "SELECT count(*) n FROM messages WHERE conversation_id = $1::uuid "
                          "AND delivery_status = 'draft'", cid)["n"] >= 1
    t = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "can_duyet"]
    assert len(t) == 1, t
    assert t[0]["lien_ket"] == {"loai": "hoi_thoai", "id": cid}
    assert _mot(app_that, "SELECT count(*) n FROM cong_viec")["n"] == 0
