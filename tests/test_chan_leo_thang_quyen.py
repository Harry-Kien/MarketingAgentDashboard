"""
Không cấp được thứ mình không có — rà soát bảo mật 20.11.2026.

Trước bản này `nguoi_dung.sua` là chìa khoá vạn năng: người được giao quản lý
nhân sự tự gán "Quản trị" cho mình, hoặc tạo vai trò tick đủ mọi quyền rồi
gán cho mình. Kèm theo: nhật ký kiểm toán mở cho mọi người đọc hội thoại,
verify token Meta đọc được bằng quyền chỉ-đọc, và quản trị đầu tiên tạo bằng
script trên máy cài mới không có vai trò nào.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _nhan_vien_moi, _quan_tri_vao, _sql,
)


def _vai_tro(qt, ten: str, quyen: list[str]) -> str:
    r = qt.post("/api/vai-tro", json={"ten": ten, "mo_ta": "", "quyen": quyen})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _quan_ly_nhan_su(qt, ten="nhansu"):
    """Người chỉ có quyền quản lý nhân sự — đúng đối tượng có thể leo thang."""
    vid = _vai_tro(qt, f"Nhân sự {ten}", ["nguoi_dung.doc", "nguoi_dung.sua"])
    uid, hr = _nhan_vien_moi(qt, ten, vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [vid]}).status_code == 200
    return uid, hr


def _id_vai_tro(qt, ten: str) -> str:
    return next(v["id"] for v in qt.get("/api/vai-tro").json()["vai_tro"] if v["ten"] == ten)


def test_khong_tu_gan_quan_tri_cho_minh(app_that):
    qt = _quan_tri_vao(app_that)
    uid, hr = _quan_ly_nhan_su(qt)
    r = hr.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [_id_vai_tro(qt, "Quản trị")]})
    assert r.status_code == 403, r.text
    toi = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"] if n["id"] == uid)
    assert "Quản trị" not in toi["vai_tro_ten"]


def test_khong_tao_vai_tro_co_quyen_minh_khong_co(app_that):
    qt = _quan_tri_vao(app_that)
    _, hr = _quan_ly_nhan_su(qt)
    r = hr.post("/api/vai-tro", json={"ten": "Siêu", "mo_ta": "", "quyen": ["cau_hinh.sua"]})
    assert r.status_code == 403
    ok = hr.post("/api/vai-tro", json={"ten": "Xem NV", "mo_ta": "", "quyen": ["nguoi_dung.doc"]})
    assert ok.status_code == 201, "tạo vai trò trong phạm vi quyền của mình vẫn phải được"


def test_khong_sua_hay_xoa_vai_tro_manh_hon_minh(app_that):
    qt = _quan_tri_vao(app_that)
    _, hr = _quan_ly_nhan_su(qt)
    manh = _vai_tro(qt, "Kế toán", ["don.doc", "don.sua"])
    # Sửa — kể cả để BỚT quyền của vai trò mạnh hơn — là đụng tới cấp trên.
    assert hr.put(f"/api/vai-tro/{manh}", json={"ten": "Kế toán", "mo_ta": "", "quyen": []}).status_code == 403
    assert hr.delete(f"/api/vai-tro/{manh}").status_code == 403


def test_khong_ha_cap_hay_khoa_cap_tren(app_that):
    qt = _quan_tri_vao(app_that, ten="giamdoc")
    _, hr = _quan_ly_nhan_su(qt)
    ds = qt.get("/api/nguoi-dung").json()
    sep = next(n for n in ds.get("nguoi_dung", ds) if n["ten_dang_nhap"] == "giamdoc")
    assert hr.put(f"/api/nguoi-dung/{sep['id']}/vai-tro", json={"vai_tro": []}).status_code == 403
    assert hr.post("/api/nguoi-dung/giamdoc/khoa").status_code == 403


def test_quan_tri_van_lam_duoc_moi_viec(app_that):
    qt = _quan_tri_vao(app_that)
    uid, _ = _nhan_vien_moi(qt, "nv_binh_thuong")
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro",
                  json={"vai_tro": [_id_vai_tro(qt, "Quản trị")]}).status_code == 200


def test_nhat_ky_kiem_toan_can_quyen_rieng(app_that):
    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "nv_doc_nhat_ky")
    assert nv.get("/api/events").status_code == 403
    assert qt.get("/api/events").status_code == 200


def test_verify_token_can_quyen_sua_kenh():
    from agent.api import channel_accounts

    src = Path(channel_accounts.__file__).read_text(encoding="utf-8")
    i = src.index('@router.get("/{account_id}/verify-token")')
    assert 'can_quyen("kenh.sua")' in src[i:i + 400]


def test_script_tao_quan_tri_dau_tien_co_vai_tro_that(app_that):
    """Máy cài mới: quản trị tạo bằng script phải có vai trò Quản trị thật."""
    from agent import db
    from agent.core import xac_thuc

    async def tao():
        nd = await xac_thuc.tao_nguoi_dung("boss_vps", "matkhau-dai-123", vai_tro="quan_tri",
                                           gan_vai_tro_dung_san=True)
        return await db.fetchrow(
            "SELECT vt.ten FROM nguoi_dung_vai_tro x JOIN vai_tro vt ON vt.id = x.vai_tro_id "
            "WHERE x.nguoi_dung_id = $1::uuid", nd["id"])
    assert (_sql(app_that, tao) or {}).get("ten") == "Quản trị"


def test_tao_tren_dashboard_van_hong_dong():
    """Dashboard tạo người KHÔNG kèm vai trò: chưa gán thì không có quyền gì."""
    src = (ROOT / "agent" / "api" / "tai_khoan.py").read_text(encoding="utf-8")
    i = src.index("async def them_nguoi_dung")
    assert "gan_vai_tro_dung_san" not in src[i:i + 900]
