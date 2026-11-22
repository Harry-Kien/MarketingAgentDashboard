"""
Nhân sự & Phân quyền — phiếu việc mục 12 (RBAC) và 13 (vai trò động, quản
lý nhân viên).

Phần lớn chạy trên `agent.main.app` THẬT với Postgres thật và đăng nhập
bằng phiên thật: câu hỏi quan trọng nhất ở đây — "đổi vai trò thì người
đang đăng nhập có đổi quyền NGAY không" — chỉ trả lời được qua đúng đường
`doc_phien` chạy ở mỗi request. Một test gọi hàm với dict quyền giả sẽ xanh
cả khi phiên cache quyền cả tuần.
"""
from __future__ import annotations

import ast
import asyncio
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql,
    _them_thanh_vien,
)

LUOC_DO = ROOT / "agent" / "schema.sql"


def _vai_tro(qt, ten: str, quyen: list[str]) -> str:
    r = qt.post("/api/vai-tro", json={"ten": ten, "mo_ta": "", "quyen": quyen})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _id_vai_tro(qt, ten: str) -> str:
    return next(v["id"] for v in qt.get("/api/vai-tro").json()["vai_tro"]
                if v["ten"] == ten)


def _quyen_toi(nguoi) -> set[str]:
    r = nguoi.get("/api/toi")
    assert r.status_code == 200, r.text
    return set(r.json()["quyen"])


def _lich_su(qt, **qs) -> list[dict]:
    r = qt.get("/api/nhan-su/lich-su", params=qs)
    assert r.status_code == 200, r.text
    return r.json()["lich_su"]


# =====================================================================
#  Danh mục và nhóm hiển thị (mục 12.2)
# =====================================================================

NHOM_PHIEU_VIEC = [
    "Hội thoại", "Khách hàng", "Đơn hàng", "Kho", "Công việc", "Phân tích",
    "Cấu hình chung", "Cấu hình AI Agent", "Nhân sự & Phân quyền",
    "Hệ thống & Nhật ký", "Phê duyệt AI",
]


def test_moi_quyen_nam_trong_dung_mot_nhom_hien_thi():
    """
    Quyền mới quên xếp nhóm thì không hiện trên màn cấp quyền — không ai cấp
    được, và không có gì báo. Xếp hai lần thì một ô tick hiện hai chỗ, bỏ
    tick ở chỗ này mà chỗ kia vẫn tick.
    """
    from agent.core.quyen import NHOM_QUYEN, QUYEN

    ds = [q for _, _, nhom in NHOM_QUYEN for q in nhom]
    assert sorted(ds) == sorted(QUYEN), (
        f"thiếu: {sorted(set(QUYEN) - set(ds))} · lạ: {sorted(set(ds) - set(QUYEN))}")
    assert len(ds) == len(set(ds)), "có quyền nằm ở hai nhóm"


def test_nhom_dung_thu_tu_phieu_viec():
    from agent.core.quyen import NHOM_QUYEN

    assert [ten for _, ten, _ in NHOM_QUYEN] == NHOM_PHIEU_VIEC
    assert all(ds for _, _, ds in NHOM_QUYEN), "nhóm rỗng là một tiêu đề không có ô tick"


def test_quyen_tach_rieng_theo_phieu_viec():
    """Ba việc phiếu việc gọi tên riêng phải có quyền riêng, đúng nhóm."""
    from agent.core.quyen import NHOM_QUYEN

    nhom = {ma: set(ds) for ma, _, ds in NHOM_QUYEN}
    assert nhom["phe_duyet_ai"] == {"ai.duyet"}
    assert "hoi_thoai.ghi_chu" in nhom["hoi_thoai"]
    assert {"kho.doc", "kho.sua"} <= nhom["kho"]


def test_claude_md_noi_dung_so_quyen():
    """CLAUDE.md nói "danh mục N quyền" — lệch là tài liệu nói dối người mới."""
    from agent.core.quyen import QUYEN

    noi_dung = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert f"danh mục {len(QUYEN)} quyền" in noi_dung


# =====================================================================
#  Vai trò ngừng dùng không cấp quyền — ở MỌI chỗ tính quyền
# =====================================================================

def _chuoi_sql_theo_ham(tep: Path):
    """(tên hàm/hằng, mọi chuỗi trong nó nối lại) cho từng hàm và hằng mức module."""
    cay = ast.parse(tep.read_text(encoding="utf-8"))
    for nut in ast.walk(cay):
        if isinstance(nut, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign)):
            chu = " ".join(
                c.value for c in ast.walk(nut)
                if isinstance(c, ast.Constant) and isinstance(c.value, str))
            ten = getattr(nut, "name", None) or ast.unparse(nut.targets[0])  # type: ignore[attr-defined]
            yield ten, chu


def test_moi_cho_tinh_quyen_deu_loc_vai_tro_ngung_dung():
    """
    TEST QUAN TRỌNG NHẤT CỦA MỤC "NGỪNG DÙNG".

    Quyền được tính ở nhiều chỗ: phiên (`doc_phien`), chuông thông báo, đếm
    người duyệt PDPD, giao khách, chốt "người cuối cùng giữ nguoi_dung.sua".
    Quên lọc `dang_dung` ở MỘT chỗ là vai trò đã ngừng vẫn cấp quyền ở đúng
    chỗ ấy — ô "Ngừng dùng" thành trang trí, và không có gì đỏ.

    Mọi đoạn mã vừa đọc `vai_tro_quyen` vừa đi qua người dùng (nối
    `nguoi_dung_vai_tro`) phải nhắc `dang_dung`.
    """
    vi_pham = []
    for tep in (ROOT / "agent").rglob("*.py"):
        for ten, chu in _chuoi_sql_theo_ham(tep):
            if "vai_tro_quyen" in chu and "nguoi_dung_vai_tro" in chu \
                    and "JOIN" in chu and "dang_dung" not in chu:
                vi_pham.append(f"{tep.relative_to(ROOT)}::{ten}")
    assert not vi_pham, f"Tính quyền mà không lọc vai trò ngừng dùng: {vi_pham}"


def test_phep_quet_tren_that_su_bat_duoc_cho_quen():
    """Vế còn lại: một phép quét không bao giờ thấy gì cũng xanh."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        tep = Path(d) / "x.py"
        tep.write_text(
            'async def f():\n    return "SELECT 1 FROM nguoi_dung_vai_tro x '
            'JOIN vai_tro_quyen vq ON vq.vai_tro_id = x.vai_tro_id"\n',
            encoding="utf-8")
        ((ten, chu),) = [t for t in _chuoi_sql_theo_ham(tep) if t[0] == "f"]
        assert "vai_tro_quyen" in chu and "dang_dung" not in chu


def test_moi_loai_lich_su_deu_hien_tren_man_lich_su():
    """
    `ghi_lich_su("x.y", ...)` mà "x.y" không có trong `LOAI_LICH_SU` thì dòng
    ấy ghi vào CSDL nhưng vắng khỏi màn Lịch sử — đúng thứ mục 12.8 cấm.
    """
    from agent.api.nhan_su import LOAI_LICH_SU

    thay = set()
    for tep in (ROOT / "agent").rglob("*.py"):
        thay |= set(re.findall(r'ghi_lich_su\(\s*conn,\s*"([a-z_.]+)"',
                               tep.read_text(encoding="utf-8")))
        thay |= set(re.findall(r'"(vai_tro\.dung_lai)" if', tep.read_text(encoding="utf-8")))
        thay |= set(re.findall(r'else "(vai_tro\.ngung_dung)"', tep.read_text(encoding="utf-8")))
    assert thay, "không tìm thấy lời gọi ghi_lich_su nào — phép quét hỏng"
    assert thay <= set(LOAI_LICH_SU), sorted(thay - set(LOAI_LICH_SU))


# =====================================================================
#  Vòng đời vai trò trên app thật (mục 12.3, 12.5, 13.4–13.7, 13.9)
# =====================================================================

def test_doi_vai_tro_co_hieu_luc_ngay_voi_nguoi_dang_dang_nhap(app_that):
    """
    Vai trò động, nhiều vai trò, quyền = HỢP các vai trò đang dùng.

    BƯỚC 1  Quản trị tạo vai trò "Tra khách" (khach.doc) và "Kế toán nhỏ" (khach.doc).
    BƯỚC 2  Tạo nhân viên KÈM hai vai trò ngay trong lời tạo; họ đăng nhập thật.
    BƯỚC 3  Sửa "Tra khách" thêm don.doc → request kế tiếp của nhân viên có don.doc, không cần đăng nhập lại.
    BƯỚC 4  Ngừng dùng "Tra khách" → mất don.doc ngay, VẪN còn khach.doc vì "Kế toán nhỏ" cũng cấp.
    BƯỚC 5  Dùng lại → don.doc quay về. Gỡ "Kế toán nhỏ" → vẫn còn khach.doc từ "Tra khách".
    """
    qt = _quan_tri_vao(app_that)
    tra = _vai_tro(qt, "Tra khách", ["khach.doc"])
    ke = _vai_tro(qt, "Kế toán nhỏ", ["khach.doc"])

    r = qt.post("/api/nguoi-dung", json={
        "ten_dang_nhap": "nv.hai.vai", "mat_khau": "mat-khau-nghiem-thu-1",
        "ho_ten": "Hai Vai", "email": "Hai.Vai@Shop.vn", "vai_tro_ids": [tra, ke]})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "hai.vai@shop.vn"
    assert sorted(r.json()["vai_tro_ten"]) == ["Kế toán nhỏ", "Tra khách"]
    uid = r.json()["id"]
    from tests.test_nghiem_thu_saas import _dang_nhap
    ma, nv = _dang_nhap(qt.khach, "nv.hai.vai", "mat-khau-nghiem-thu-1")
    assert ma == 200
    assert _quyen_toi(nv) == {"khach.doc"}

    assert qt.put(f"/api/vai-tro/{tra}", json={
        "ten": "Tra khách", "mo_ta": "", "quyen": ["khach.doc", "don.doc"]}).status_code == 200
    assert _quyen_toi(nv) == {"khach.doc", "don.doc"}

    r = qt.post(f"/api/vai-tro/{tra}/trang-thai", json={"dang_dung": False})
    assert r.status_code == 200, r.text
    assert r.json()["so_nguoi_anh_huong"] == 1
    assert _quyen_toi(nv) == {"khach.doc"}, "vai trò ngừng dùng vẫn cấp quyền"
    gt = qt.get(f"/api/nguoi-dung/{uid}/quyen").json()
    assert gt["vai_tro"] == ["Kế toán nhỏ"] and gt["vai_tro_ngung"] == ["Tra khách"]
    ds = {n["ten_dang_nhap"]: n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"]}
    assert ds["nv.hai.vai"]["vai_tro_ten"] == ["Kế toán nhỏ"]
    assert ds["nv.hai.vai"]["vai_tro_ngung"] == ["Tra khách"]

    assert qt.post(f"/api/vai-tro/{tra}/trang-thai",
                   json={"dang_dung": True}).status_code == 200
    assert _quyen_toi(nv) == {"khach.doc", "don.doc"}

    # Người đang mang một vai trò đã từng ngừng vẫn đổi được phần còn lại —
    # ghi theo HIỆU, không xoá-chèn-lại.
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro",
                  json={"vai_tro": [tra]}).status_code == 200
    assert _quyen_toi(nv) == {"khach.doc", "don.doc"}


def test_vai_tro_ngung_dung_khong_gan_moi_duoc_va_khong_xoa_duoc(app_that):
    """
    BƯỚC 1  Vai trò đã gán rồi ngừng dùng: gán cho người mới → 422; tạo người kèm nó → 422.
    BƯỚC 2  Xoá vai trò ấy → 409, nói rõ phải Ngừng dùng thay vì xoá.
    BƯỚC 3  Vai trò tạo nhầm, CHƯA TỪNG gán ai → xoá được (204), và màn hình biết trước (`xoa_duoc`).
    BƯỚC 4  Vai trò dựng sẵn không ngừng dùng được (409).
    """
    qt = _quan_tri_vao(app_that)
    vid = _vai_tro(qt, "Thời vụ", ["khach.doc"])
    a, _ = _nhan_vien_moi(qt, "nv.thoi.vu", vai_tro="Thời vụ")
    # Gỡ hết người mang — lịch sử gán vẫn phải giữ vai trò lại.
    assert qt.put(f"/api/nguoi-dung/{a}/vai-tro", json={"vai_tro": []}).status_code == 200
    assert qt.post(f"/api/vai-tro/{vid}/trang-thai",
                   json={"dang_dung": False}).status_code == 200

    b, _ = _nhan_vien_moi(qt, "nv.moi.vao", vai_tro=None)
    r = qt.put(f"/api/nguoi-dung/{b}/vai-tro", json={"vai_tro": [vid]})
    assert r.status_code == 422 and "ngừng dùng" in r.text
    r = qt.post("/api/nguoi-dung", json={"ten_dang_nhap": "nv.kem.ngung",
                                         "mat_khau": "mat-khau-nghiem-thu-1",
                                         "vai_tro_ids": [vid]})
    assert r.status_code == 422
    ds = {n["ten_dang_nhap"] for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"]}
    assert "nv.kem.ngung" not in ds, "kiểm vai trò phải xảy ra TRƯỚC khi tạo tài khoản"

    v = next(x for x in qt.get("/api/vai-tro").json()["vai_tro"] if x["id"] == vid)
    assert v["dang_dung"] is False and v["xoa_duoc"] is False
    r = qt.delete(f"/api/vai-tro/{vid}")
    assert r.status_code == 409 and "Ngừng dùng" in r.text

    nham = _vai_tro(qt, "Tạo nhầm", ["khach.doc"])
    assert next(x for x in qt.get("/api/vai-tro").json()["vai_tro"]
                if x["id"] == nham)["xoa_duoc"] is True
    assert qt.delete(f"/api/vai-tro/{nham}").status_code == 204

    nv_he_thong = _id_vai_tro(qt, "Nhân viên")
    r = qt.post(f"/api/vai-tro/{nv_he_thong}/trang-thai", json={"dang_dung": False})
    assert r.status_code == 409


def test_khong_ngung_dung_hay_dung_lai_vai_tro_manh_hon_minh(app_that):
    """
    Luật chống leo thang mở rộng sang thao tác mới: người chỉ quản lý nhân sự
    không ngừng dùng (hạ cấp cả nhóm) hay dùng lại (cấp lại cả nhóm) một vai
    trò có quyền họ không có.
    """
    qt = _quan_tri_vao(app_that)
    hr_vai = _vai_tro(qt, "Nhân sự thôi", ["nguoi_dung.doc", "nguoi_dung.sua"])
    _, hr = _nhan_vien_moi(qt, "hr.thoi", vai_tro="Nhân sự thôi")
    assert hr_vai
    manh = _vai_tro(qt, "Kho trưởng", ["kho.doc", "kho.sua"])
    assert hr.post(f"/api/vai-tro/{manh}/trang-thai",
                   json={"dang_dung": False}).status_code == 403
    assert qt.post(f"/api/vai-tro/{manh}/trang-thai",
                   json={"dang_dung": False}).status_code == 200
    assert hr.post(f"/api/vai-tro/{manh}/trang-thai",
                   json={"dang_dung": True}).status_code == 403


def test_lich_su_doi_quyen_ghi_truoc_sau(app_that):
    """
    Lịch sử phân quyền: ai, lúc nào, vai trò nào, ĐỔI GÌ (mục 12.8).

    BƯỚC 1  Tạo vai trò, sửa (thêm don.doc, bỏ khach.sua), ngừng dùng.
    BƯỚC 2  Gán vai trò cho nhân viên rồi đổi sang vai trò khác.
    BƯỚC 3  /api/nhan-su/lich-su trả đủ các dòng, mỗi dòng có trước/sau và phần thêm/bớt.
    """
    qt = _quan_tri_vao(app_that, ten="giamdoc")
    vid = _vai_tro(qt, "Trực ca", ["khach.doc", "khach.sua"])
    assert qt.put(f"/api/vai-tro/{vid}", json={
        "ten": "Trực ca", "mo_ta": "ca tối", "quyen": ["khach.doc", "don.doc"]}).status_code == 200

    uid, _ = _nhan_vien_moi(qt, "nv.truc", vai_tro="Trực ca")
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro",
                  json={"vai_tro": [_id_vai_tro(qt, "Nhân viên")]}).status_code == 200
    assert qt.post(f"/api/vai-tro/{vid}/trang-thai", json={"dang_dung": False}).status_code == 200

    vt = _lich_su(qt, ref_id=vid)
    loai = [d["loai"] for d in vt]
    assert loai == ["vai_tro.ngung_dung", "vai_tro.sua", "vai_tro.tao"], loai
    sua = vt[1]
    assert sua["nguoi_lam"] == "giamdoc" and sua["luc"]
    assert sua["chi_tiet"]["truoc"]["quyen"] == ["khach.doc", "khach.sua"]
    assert sua["chi_tiet"]["sau"]["quyen"] == ["don.doc", "khach.doc"]
    assert sua["chi_tiet"]["them"] == ["don.doc"] and sua["chi_tiet"]["bot"] == ["khach.sua"]
    assert vt[0]["chi_tiet"]["bot"] == ["don.doc", "khach.doc"]

    nd = _lich_su(qt, ref_id=uid)
    gan = [d for d in nd if d["loai"] == "nguoi_dung.vai_tro"]
    assert gan[0]["chi_tiet"]["truoc"] == ["Trực ca"]
    assert gan[0]["chi_tiet"]["sau"] == ["Nhân viên"]
    assert "khach.sua" in gan[0]["chi_tiet"]["quyen_them"]
    assert any(d["loai"] == "auth.tao_nguoi_dung" for d in nd)

    # Lọc theo loại
    assert all(d["loai"].startswith("vai_tro.") for d in _lich_su(qt, loai="vai_tro"))


def test_lich_su_can_quyen_doc_nhan_su(app_that):
    qt = _quan_tri_vao(app_that)
    _vai_tro(qt, "Chỉ khách", ["khach.doc"])
    _, nv = _nhan_vien_moi(qt, "nv.chi.khach", vai_tro="Chỉ khách")
    assert nv.get("/api/nhan-su/lich-su").status_code == 403


# =====================================================================
#  Tài khoản nhân viên (mục 13.3)
# =====================================================================

def test_sua_thong_tin_nhan_vien_va_email_duy_nhat(app_that):
    """
    BƯỚC 1  Tạo nhân viên kèm email; email sai dạng → 422; email trùng (khác hoa thường) → 409.
    BƯỚC 2  Sửa họ tên + email → danh sách hiện đúng, lịch sử ghi trước/sau.
    BƯỚC 3  Người chỉ quản lý nhân sự không sửa được thông tin quản trị (403).
    """
    qt = _quan_tri_vao(app_that, ten="chu")
    r = qt.post("/api/nguoi-dung", json={"ten_dang_nhap": "lan.nv", "mat_khau": "mat-khau-dai-1",
                                         "ho_ten": "Lan", "email": "lan@shop.vn"})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    assert qt.post("/api/nguoi-dung", json={
        "ten_dang_nhap": "lan.hai", "mat_khau": "mat-khau-dai-1",
        "email": "khong-phai-email"}).status_code == 422
    assert qt.post("/api/nguoi-dung", json={
        "ten_dang_nhap": "lan.ba", "mat_khau": "mat-khau-dai-1",
        "email": "LAN@shop.vn"}).status_code == 409

    r = qt.put(f"/api/nguoi-dung/{uid}", json={"ho_ten": "Nguyễn Thị Lan", "email": "lan.nguyen@shop.vn"})
    assert r.status_code == 200, r.text
    d = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"] if n["id"] == uid)
    assert d["ho_ten"] == "Nguyễn Thị Lan" and d["email"] == "lan.nguyen@shop.vn"
    for k in ("tao_luc", "dang_nhap_cuoi", "khoa", "so_hoi_thoai_giu", "so_viec_chua_xong"):
        assert k in d
    sua = next(x for x in _lich_su(qt, ref_id=uid) if x["loai"] == "nguoi_dung.sua")
    assert sua["chi_tiet"]["truoc"]["ho_ten"] == "Lan"
    assert sua["chi_tiet"]["sau"]["email"] == "lan.nguyen@shop.vn"

    _vai_tro(qt, "HR", ["nguoi_dung.doc", "nguoi_dung.sua"])
    _, hr = _nhan_vien_moi(qt, "hr.nv", vai_tro="HR")
    chu = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"]
               if n["ten_dang_nhap"] == "chu")
    assert hr.put(f"/api/nguoi-dung/{chu['id']}",
                  json={"ho_ten": "Bị đổi", "email": None}).status_code == 403


# =====================================================================
#  Khoá kèm chuyển việc (mục 13.8)
# =====================================================================

def _giao_hoi_thoai(qt, khach, uid: str) -> str:
    from agent import db

    async def doc():
        return dict(await db.fetchrow(
            "SELECT id, version FROM conversations ORDER BY created_at DESC LIMIT 1"))
    c = _sql(khach, doc)
    r = qt.post(f"/api/inbox/conversations/{c['id']}/takeover", json={
        "assignee_id": uid, "expected_version": c["version"], "reason": "giao ca tối"})
    assert r.status_code == 200, r.text
    return str(c["id"])


def test_khoa_nguoi_dang_giu_viec_thi_canh_bao_roi_chuyen_viec(app_that):
    """
    Khoá tài khoản mà không làm gián đoạn CSKH.

    BƯỚC 1  Nhân viên A giữ một hội thoại (người tiếp quản) và một việc chưa xong.
    BƯỚC 2  Quản trị bấm Khoá A → máy chủ 409, nói rõ 1 hội thoại + 1 việc, KHÔNG khoá.
    BƯỚC 3  Chuyển việc sang người đã khoá / người không trả lời khách được → 422.
    BƯỚC 4  Chuyển việc sang B → hội thoại và việc về tay B, A không còn gì.
    BƯỚC 5  Khoá A → thành công, phiên của A bị đá; lịch sử ghi chuyển việc và khoá.
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    a, nv_a = _nhan_vien_moi(qt, "nv.a")
    b, _ = _nhan_vien_moi(qt, "nv.b")
    for u in (a, b):
        _them_thanh_vien(app_that, tk, u)
    _khach_nhan(app_that, tk, "Chị Mai", "em cần tư vấn kem")
    cid = _giao_hoi_thoai(qt, app_that, a)
    r = qt.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Mai", "nguoi_nhan": a})
    assert r.status_code == 201, r.text
    viec_id = r.json()["id"]

    r = qt.post("/api/nguoi-dung/nv.a/khoa?khoa=true")
    assert r.status_code == 409, r.text
    ct = r.json()["detail"]
    assert ct["can_chuyen_viec"] is True
    assert ct["viec"]["so_hoi_thoai"] == 1 and ct["viec"]["so_cong_viec"] == 1
    assert _quyen_toi(nv_a), "409 mà vẫn khoá là khách của A chờ trong im lặng"
    giu = qt.get(f"/api/nguoi-dung/{a}/viec-dang-giu").json()
    assert giu["tong"] == 2 and giu["hoi_thoai"][0]["id"] == cid

    # Người nhận không hợp lệ.
    _vai_tro(qt, "Chỉ xem khách", ["khach.doc", "cong_viec.doc"])
    c_id, _ = _nhan_vien_moi(qt, "nv.c", vai_tro="Chỉ xem khách")
    r = qt.post(f"/api/nguoi-dung/{a}/chuyen-viec", json={"nguoi_nhan": c_id})
    assert r.status_code == 422 and "hoi_thoai.tra_loi" in r.text
    d, _ = _nhan_vien_moi(qt, "nv.d")
    assert qt.post("/api/nguoi-dung/nv.d/khoa?khoa=true").status_code == 200
    assert qt.post(f"/api/nguoi-dung/{a}/chuyen-viec",
                   json={"nguoi_nhan": d}).status_code == 422

    r = qt.post(f"/api/nguoi-dung/{a}/chuyen-viec", json={"nguoi_nhan": b})
    assert r.status_code == 200, r.text
    kq = r.json()
    assert kq["so_hoi_thoai"] == 1 and kq["so_cong_viec"] == 1, kq
    assert kq["khong_chuyen_duoc"] == []

    async def doc(cid_, viec_):
        c = await db.fetchrow("SELECT assigned_to, mode FROM conversations WHERE id = $1::uuid", cid_)
        v = await db.fetchrow("SELECT nguoi_nhan FROM cong_viec WHERE id = $1::uuid", viec_)
        return str(c["assigned_to"]), c["mode"], str(v["nguoi_nhan"])
    giao, mode, nhan = _sql(app_that, doc, cid, viec_id)
    assert (giao, mode, nhan) == (b, "human", b)
    assert qt.get(f"/api/nguoi-dung/{a}/viec-dang-giu").json()["tong"] == 0

    assert qt.post("/api/nguoi-dung/nv.a/khoa?khoa=true").status_code == 200
    assert nv_a.get("/api/toi").status_code == 401

    loai = [x["loai"] for x in _lich_su(qt, ref_id=a)]
    assert "nguoi_dung.chuyen_viec" in loai and "auth.khoa_nguoi_dung" in loai


def test_khoa_de_lai_viec_phai_noi_ro_va_duoc_ghi_lai(app_that):
    """
    Có lúc phải khoá NGAY (nhân viên lộ mật khẩu) rồi mới tính chuyện việc.
    Đường ấy phải có, nhưng phải nói ra — `bo_qua_viec=true` — và lịch sử
    ghi lại số việc bị để lại.
    """
    qt = _quan_tri_vao(app_that)
    a, _ = _nhan_vien_moi(qt, "nv.lo.mk")
    assert qt.post("/api/cong-viec", json={"tieu_de": "Việc dở dang",
                                           "nguoi_nhan": a}).status_code == 201
    assert qt.post("/api/nguoi-dung/nv.lo.mk/khoa?khoa=true").status_code == 409
    assert qt.post("/api/nguoi-dung/nv.lo.mk/khoa?khoa=true&bo_qua_viec=true").status_code == 200
    khoa = next(x for x in _lich_su(qt, ref_id=a) if x["loai"] == "auth.khoa_nguoi_dung")
    assert khoa["chi_tiet"]["de_lai_viec"] == {"so_hoi_thoai": 0, "so_cong_viec": 1}
    # Mở khoá không bị hỏi về việc.
    assert qt.post("/api/nguoi-dung/nv.lo.mk/khoa?khoa=false").status_code == 200


def test_chuyen_viec_can_dung_quyen_va_khong_lay_viec_cap_tren(app_that):
    """
    Đường vòng qua màn Nhân sự không được rộng hơn đường chính: chuyển hội
    thoại cần `hoi_thoai.nhan`, chuyển việc cần `cong_viec.giao`, và không
    lấy việc của người mạnh hơn mình.
    """
    qt = _quan_tri_vao(app_that, ten="sep.lon")
    _vai_tro(qt, "HR thuần", ["nguoi_dung.doc", "nguoi_dung.sua"])
    _, hr = _nhan_vien_moi(qt, "hr.thuan", vai_tro="HR thuần")
    # Người bị lấy việc mang vai trò NHỎ hơn người điều phối — không thì
    # `chan_cap_vuot` chặn đúng như nó phải chặn, và vế "được phép" không
    # bao giờ được thử.
    _vai_tro(qt, "CSKH gọn", ["hoi_thoai.tra_loi", "cong_viec.doc"])
    a, _ = _nhan_vien_moi(qt, "nv.x", vai_tro="CSKH gọn")
    b, _ = _nhan_vien_moi(qt, "nv.y")
    r = hr.post(f"/api/nguoi-dung/{a}/chuyen-viec", json={"nguoi_nhan": b})
    assert r.status_code == 403 and "hoi_thoai.nhan" in r.text

    sep = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"]
               if n["ten_dang_nhap"] == "sep.lon")
    _vai_tro(qt, "Điều phối", ["nguoi_dung.doc", "nguoi_dung.sua", "hoi_thoai.nhan",
                                "cong_viec.giao", "hoi_thoai.tra_loi", "cong_viec.doc"])
    _, dp = _nhan_vien_moi(qt, "dieu.phoi", vai_tro="Điều phối")
    assert dp.post(f"/api/nguoi-dung/{sep['id']}/chuyen-viec",
                   json={"nguoi_nhan": b}).status_code == 403
    assert dp.post(f"/api/nguoi-dung/{a}/chuyen-viec",
                   json={"nguoi_nhan": b}).status_code == 200


# =====================================================================
#  Ba quyền mới tách ra: chốt ở máy chủ
# =====================================================================

def test_duyet_ban_nhap_can_ai_duyet_khong_phai_tra_loi(app_that):
    """
    `ai.duyet` là quyền RIÊNG: trả lời khách được mà thiếu nó thì 403 ở nút
    Duyệt — trước khi chạm tới bản nháp (id lạ cũng 403, không lộ tồn tại).
    """
    qt = _quan_tri_vao(app_that)
    _vai_tro(qt, "Trả lời thôi", ["hoi_thoai.doc", "hoi_thoai.tra_loi"])
    _, nv = _nhan_vien_moi(qt, "nv.tra.loi", vai_tro="Trả lời thôi")
    r = nv.post("/api/messages/00000000-0000-0000-0000-000000000099/approve")
    assert r.status_code == 403 and "ai.duyet" in r.text


def test_kho_co_quyen_rieng(app_that):
    qt = _quan_tri_vao(app_that)
    _vai_tro(qt, "Xem đơn thôi", ["don.doc"])
    _, nv = _nhan_vien_moi(qt, "nv.don", vai_tro="Xem đơn thôi")
    assert nv.get("/api/kho").status_code == 403
    assert nv.post("/api/kho/SP01/nhap", json={"so_luong": 1}).status_code == 403
    assert nv.get("/api/orders").status_code == 200


# =====================================================================
#  Migration 0058 trên CSDL ĐANG CHẠY
# =====================================================================

def _ap_migration(url: str, kich_ban):
    import asyncpg

    from agent.migrations.runner import apply_migrations, discover_migrations

    async def chay():
        conn = await asyncpg.connect(url)
        await conn.set_type_codec("jsonb", encoder=json.dumps,
                                  decoder=json.loads, schema="pg_catalog")
        try:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
            tat_ca = discover_migrations()
            truoc = [m for m in tat_ca if m.version < "0058"]
            await apply_migrations(conn, truoc)
            return await kich_ban(conn, lambda: apply_migrations(conn, tat_ca))
        finally:
            await conn.close()
    return asyncio.run(chay())


def test_migration_0058_giu_nguyen_ai_lam_duoc_gi(csdl_kiem_thu):
    """
    Nâng cấp không được lặng lẽ THU quyền: vai trò tự tạo trước 0058 có
    `hoi_thoai.tra_loi` thì vẫn duyệt được nháp và gắn nhãn được; có
    `don.doc`/`don.sua` thì vẫn xem/nhập kho được. Vai trò không có thì
    không tự dưng có.
    """
    async def kich_ban(conn, len_0058):
        cskh = await conn.fetchval(
            "INSERT INTO vai_tro (ten) VALUES ('CSKH cũ') RETURNING id")
        kho = await conn.fetchval(
            "INSERT INTO vai_tro (ten) VALUES ('Kho cũ') RETURNING id")
        await conn.execute(
            "INSERT INTO vai_tro_quyen (vai_tro_id, quyen) VALUES "
            "($1, 'hoi_thoai.tra_loi'), ($2, 'don.doc'), ($2, 'don.sua')", cskh, kho)
        nd = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam) VALUES ('cu', 'x') RETURNING id")
        await conn.execute(
            "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) VALUES ($1, $2)", nd, kho)
        await len_0058()
        q = {r["ten"]: set(r["q"]) for r in await conn.fetch(
            "SELECT vt.ten, array_agg(vq.quyen) AS q FROM vai_tro vt "
            "JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
            "WHERE vt.ten IN ('CSKH cũ', 'Kho cũ') GROUP BY vt.ten")}
        gan = {r["ten"]: r["tung_gan_luc"] is not None for r in await conn.fetch(
            "SELECT ten, tung_gan_luc FROM vai_tro WHERE ten IN ('CSKH cũ', 'Kho cũ')")}
        return q, gan

    q, gan = _ap_migration(csdl_kiem_thu, kich_ban)
    assert q["CSKH cũ"] == {"hoi_thoai.tra_loi", "ai.duyet", "hoi_thoai.ghi_chu"}
    assert q["Kho cũ"] == {"don.doc", "don.sua", "kho.doc", "kho.sua"}
    # Vai trò ĐANG có người mang lúc nâng cấp = đã có lịch sử, không xoá hẳn được.
    assert gan == {"CSKH cũ": False, "Kho cũ": True}


def test_csdl_chan_gan_vai_tro_ngung_dung_va_ngung_vai_tro_he_thong(csdl_kiem_thu):
    """
    Chốt ở CSDL — còn đứng khi API bị vòng qua (lệnh SQL cứu hộ, script).
    Gán lần đầu cũng tự đánh dấu `tung_gan_luc` bằng trigger.
    """
    import asyncpg

    async def kich_ban(conn, len_0058):
        await len_0058()
        vid = await conn.fetchval("INSERT INTO vai_tro (ten) VALUES ('Tạm') RETURNING id")
        nd = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam) VALUES ('t1', 'x') RETURNING id")
        await conn.execute(
            "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) VALUES ($1, $2)", nd, vid)
        da_gan = await conn.fetchval("SELECT tung_gan_luc IS NOT NULL FROM vai_tro WHERE id = $1", vid)
        await conn.execute("UPDATE vai_tro SET dang_dung = false WHERE id = $1", vid)
        nd2 = await conn.fetchval(
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam) VALUES ('t2', 'x') RETURNING id")
        loi_gan = loi_he_thong = None
        try:
            await conn.execute(
                "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) VALUES ($1, $2)", nd2, vid)
        except asyncpg.CheckViolationError as exc:
            loi_gan = str(exc)
        try:
            await conn.execute(
                "UPDATE vai_tro SET dang_dung = false WHERE he_thong AND ten = 'Quản trị'")
        except asyncpg.CheckViolationError as exc:
            loi_he_thong = str(exc)
        return da_gan, loi_gan, loi_he_thong

    da_gan, loi_gan, loi_he_thong = _ap_migration(csdl_kiem_thu, kich_ban)
    assert da_gan is True
    assert loi_gan and "vai_tro_ngung_dung" in loi_gan
    assert loi_he_thong and "vai_tro_he_thong_luon_dung" in loi_he_thong


# =====================================================================
#  Giao diện: gắn vào khung tab và ẩn thứ không dùng được (mục 12.6)
# =====================================================================

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_hai_tab_nhan_su_gan_vao_khung_tab():
    assert "GAN_TAB[\"ns-nhan-vien\"]" in JS
    assert "GAN_TAB[\"ns-vai-tro\"]" in JS


def test_giao_dien_goi_dung_cac_duong_moi():
    for duong in ("/chuyen-viec", "/viec-dang-giu", "/trang-thai", "/nhan-su/lich-su",
                  "nhom_hien_thi", "vai_tro_ids"):
        assert duong in JS, duong


def test_nut_duyet_an_khi_thieu_ai_duyet():
    """Hiện nút Duyệt cho người thiếu `ai.duyet` là mời một 403 mỗi lần bấm."""
    doan = JS[JS.index("function nutDuyetDuoc"):]
    assert 'has("ai.duyet")' in doan[:400]
    # Một lần khai báo + hai chỗ vẽ nút.
    assert JS.count("nutDuyetDuoc()") >= 3


def test_khoa_tren_man_hinh_hoi_ve_viec_dang_giu():
    doan = JS[JS.index("async function nsvKhoa"):]
    doan = doan[:doan.index("\n}\n")]
    assert "can_chuyen_viec" in doan and "bo_qua_viec" in doan

