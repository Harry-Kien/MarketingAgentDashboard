"""
Nhân viên phải là THÀNH VIÊN KÊNH mới thấy hội thoại, thấy khách, và mới
được bộ định tuyến giao việc — và phải có đường trên màn hình để làm việc đó.

VÌ SAO CẦN
----------
`account_memberships` là trục lọc của inbox, contacts và auto-routing, nhưng
trước bản này chỉ được ghi khi ai đó bấm nối kênh. Đo được trên hệ thống
thật 14.09.2026: nhân viên được giao 8 khách, là thành viên của 0 kênh, đăng
nhập vào thấy 0 hội thoại và 0 khách. Không lỗi, không nhật ký.

Kịch bản ở đây chạy trên `agent.main.app` đầy đủ + Postgres thật (fixture
`app_that`), đúng đường dashboard gọi.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao,
)

from agent.api.routing_admin import canh_bao_thanh_vien  # noqa: E402

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- hàm thuần

def _tv(user, team, **k):
    return {"user_id": user, "team_id": team, "ho_ten": f"nv-{user}",
            "ten_dang_nhap": f"nv-{user}", "khoa": False, "is_available": True, **k}


def test_canh_bao_nguoi_khong_o_kenh_nao():
    ra = canh_bao_thanh_vien(rules=[], members=[_tv("u1", "t1")],
                             thanh_vien_kenh=set(), ten_kenh={})
    assert len(ra) == 1 and "không bao giờ giao" in ra[0]["ly_do"]
    assert ra[0]["user_id"] == "u1" and ra[0]["team_id"] == "t1"


def test_canh_bao_luat_tro_kenh_nguoi_khong_o_trong():
    luat = [{"team_id": "t1", "account_id": "k2", "active": True}]
    ra = canh_bao_thanh_vien(luat, [_tv("u1", "t1")], {("u1", "k1")},
                             {"k1": "Zalo", "k2": "Facebook"})
    assert len(ra) == 1 and "Facebook" in ra[0]["ly_do"]


def test_khong_canh_bao_khi_du_kenh_va_bo_qua_nguoi_khoa():
    luat = [{"team_id": "t1", "account_id": "k1", "active": True},
            {"team_id": "t1", "account_id": None, "active": True}]
    ok = canh_bao_thanh_vien(luat, [_tv("u1", "t1")], {("u1", "k1")}, {"k1": "Zalo"})
    assert ok == []
    khoa = canh_bao_thanh_vien([], [_tv("u2", "t1", khoa=True)], set(), {})
    assert khoa == []
    # Luật đã TẮT không sinh cảnh báo — nó không chia gì cả.
    tat = canh_bao_thanh_vien([{"team_id": "t1", "account_id": "k9", "active": False}],
                              [_tv("u1", "t1")], {("u1", "k1")}, {"k9": "X"})
    assert tat == []


# ---------------------------------------------------------------- app thật

def test_nhan_vien_khong_thay_gi_cho_toi_khi_duoc_cho_vao_kenh(app_that):
    """
    BƯỚC 1  Quản trị nối kênh webchat, tạo nhân viên "lan" (vai trò Nhân viên).
    BƯỚC 2  Khách nhắn -> có hội thoại, có hồ sơ khách. Giao khách ấy cho lan.
    BƯỚC 3  lan đăng nhập: 0 hội thoại, 0 khách — kể cả khách vừa giao.
    BƯỚC 4  Quản trị bấm Kênh -> PUT /api/nguoi-dung/{id}/kenh.
    BƯỚC 5  lan thấy hội thoại và khách; /api/nguoi-dung báo so_kenh = 1.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _khach_nhan(app_that, tk, "Chị Hoa", "Shop còn hàng không?")
    cid = qt.get("/api/contacts").json()[0]["id"]
    assert qt.put(f"/api/contacts/{cid}/chu-so-huu",
                  json={"owner_user_id": lan_id, "ly_do": "ca sáng"}).status_code == 200

    assert lan.get("/api/contacts").json() == []
    assert lan.get("/api/inbox/conversations").json()["items"] == []
    r = qt.get(f"/api/nguoi-dung/{lan_id}/kenh").json()
    assert r["so_thanh_vien"] == 0
    assert any(k["id"] == tk and not k["thanh_vien"] for k in r["kenh"])

    r = qt.put(f"/api/nguoi-dung/{lan_id}/kenh", json={"kenh": [tk]})
    assert r.status_code == 200, r.text
    assert r.json()["so_thanh_vien"] == 1

    assert [c["id"] for c in lan.get("/api/contacts").json()] == [cid]
    assert len(lan.get("/api/inbox/conversations").json()["items"]) == 1
    nd = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"] if n["id"] == lan_id)
    assert nd["so_kenh"] == 1

    # Thay thế, không cộng dồn: gửi danh sách rỗng là gỡ hết.
    assert qt.put(f"/api/nguoi-dung/{lan_id}/kenh", json={"kenh": []}).json()["so_thanh_vien"] == 0
    assert lan.get("/api/contacts").json() == []


def test_owner_khong_bi_go_qua_o_tick(app_that):
    """Người đã nối kênh là `owner` — dấu vết ai nối, và là quyền xem PII. Ô tick không gỡ được."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    qt_id = qt.get("/api/toi").json()["id"]
    r = qt.put(f"/api/nguoi-dung/{qt_id}/kenh", json={"kenh": []}).json()
    assert r["so_thanh_vien"] == 1
    assert next(k for k in r["kenh"] if k["id"] == tk)["role"] == "owner"


def test_kenh_khong_ton_tai_thi_422_va_khong_ghi_gi(app_that):
    qt = _quan_tri_vao(app_that)
    lan_id, _ = _nhan_vien_moi(qt, "lan")
    r = qt.put(f"/api/nguoi-dung/{lan_id}/kenh", json={"kenh": [str(uuid4())]})
    assert r.status_code == 422
    assert qt.get(f"/api/nguoi-dung/{lan_id}/kenh").json()["so_thanh_vien"] == 0


def test_dinh_tuyen_canh_bao_thanh_vien_doi_chua_vao_kenh(app_that):
    """
    BƯỚC 1  Tạo đội, thêm lan vào đội, tạo luật mọi kênh -> đội.
    BƯỚC 2  GET /api/routing: có cảnh báo nêu tên lan — bộ định tuyến sẽ bỏ qua.
    BƯỚC 3  Cho lan vào kênh -> cảnh báo biến mất; members liệt kê lan.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, _ = _nhan_vien_moi(qt, "lan")
    doi = qt.post("/api/routing/teams", json={"name": "Ca sáng"}).json()["id"]
    assert qt.put(f"/api/routing/teams/{doi}/members/{lan_id}",
                  json={"max_active": 5}).status_code == 200
    assert qt.post("/api/routing/rules", json={"team_id": doi}).status_code == 201

    c = qt.get("/api/routing").json()
    assert [m["user_id"] for m in c["members"]] == [lan_id]
    assert len(c["canh_bao"]) == 1 and "Lan" in c["canh_bao"][0]["ly_do"]

    assert qt.put(f"/api/nguoi-dung/{lan_id}/kenh", json={"kenh": [tk]}).status_code == 200
    assert qt.get("/api/routing").json()["canh_bao"] == []


def test_nhan_vien_thuong_khong_doi_duoc_kenh_cua_nguoi_khac(app_that):
    qt = _quan_tri_vao(app_that)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    assert lan.put(f"/api/nguoi-dung/{lan_id}/kenh", json={"kenh": []}).status_code == 403


# ---------------------------------------------------------------- màn hình

def test_man_nhan_su_co_nut_kenh_va_bang_tick():
    assert 'data-gankenh="${esc(n.id)}"' in JS
    doan = JS[JS.index('const gan = e.target.closest("[data-gankenh]")'):]
    doan = doan[:doan.index("\n});\n")]
    assert "prompt(" not in doan and 'type="checkbox"' in doan
    assert "data-kenhluu" in doan and "data-kenhhuy" in doan
    assert '"/nguoi-dung/" + ' in JS or "`/nguoi-dung/${id}/kenh`" in JS


def test_vong_lam_moi_khong_xoa_bang_tick_dang_mo():
    """
    `loadNhanSu` chạy lại mỗi 6 giây và dựng lại `#nsNguoi`. Không có chốt
    này thì bảng tick vai trò/kênh biến mất trước khi kịp bấm Lưu — đo được
    trên hệ thống thật ngay lần thử đầu.
    """
    doan = JS[JS.index("async function loadNhanSu"):JS.index("function nsVeBangQuyen")]
    assert '#nsNguoi [data-vtbang], #nsNguoi [data-kenhbang]' in doan
    assert "if (!dangTick)" in doan


def test_dong_nhan_vien_bao_ngay_khi_chua_vao_kenh_nao():
    doan = JS[JS.index("function nsDongNguoi"):JS.index("function nsDongVaiTro")]
    assert "so_kenh" in doan and "chưa vào kênh nào" in doan
    # Quản trị thấy mọi kênh nhờ xem_tat_ca — với họ 0 kênh không phải cảnh báo.
    assert 'includes("Quản trị")' in doan


def test_tao_nhan_vien_mac_dinh_cho_vao_moi_kenh_dang_hoat_dong():
    khoi = HTML[HTML.index('id="nsFormNguoi"'):]
    khoi = khoi[:khoi.index("</form>")]
    assert 'name="moi_kenh"' in khoi and "checked" in khoi[khoi.index('name="moi_kenh"'):][:60]
    doan = JS[JS.index('$("#nsFormNguoi")?.addEventListener("submit"'):]
    doan = doan[:doan.index("\n});\n")]
    assert "d.moi_kenh" in doan and 'k.status === "active"' in doan
    assert "CHƯA cho vào kênh nào" in doan       # hỏng thì nói ra, không nuốt


def test_dinh_tuyen_hien_thanh_vien_doi_va_canh_bao():
    assert 'id="dtCanhBao"' in HTML
    doan = JS[JS.index("async function loadDinhTuyen"):JS.index("async function dtGui")]
    assert "c.members" in doan and "c.canh_bao" in doan
    assert "không giao được cho ai" in doan
