"""
Nhân sự đợt UX 25.11.2026: đặt lại mật khẩu, bắt đổi mật khẩu ở lần đăng
nhập tới, mở khoá tài khoản mang quyền nhạy cảm, và các hộp xác nhận trong
dashboard thay cho confirm() của trình duyệt.

Phần máy chủ chạy trên `agent.main.app` THẬT, Postgres thật, đăng nhập thật:
"mật khẩu tạm có bị chặn không" chỉ trả lời được qua đúng middleware chạy ở
mỗi request — một test gọi hàm với dict người giả sẽ xanh cả khi chốt ấy
chưa từng được gắn vào app.

Mỗi chốt ở đây canh một cách HỎNG IM LẶNG:
  - đặt lại mật khẩu mà không thu phiên: kẻ chiếm tài khoản vẫn ngồi trong;
  - cờ "phải đổi" chỉ ở màn hình: ai cầm mật khẩu tạm gọi thẳng API là xong;
  - mật khẩu lọt vào `events`: mọi người có `nhat_ky.doc` đọc được;
  - mở khoá một tài khoản "chỉ xem" còn mang Quản trị: trao toàn quyền bằng
    một cú bấm, như đã đo được với `staff_view` trên dữ liệu thật.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_nghiem_thu_saas import (  # noqa: E402
    MK, _dang_nhap, _nhan_vien_moi, _quan_tri_vao, _sql,
)

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
SRC = ROOT / "dashboard" / "src"
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def _id_vai_tro(qt, ten: str) -> str:
    return next(v["id"] for v in qt.get("/api/vai-tro").json()["vai_tro"] if v["ten"] == ten)


def _vai_tro(qt, ten: str, quyen: list[str]) -> str:
    r = qt.post("/api/vai-tro", json={"ten": ten, "mo_ta": "", "quyen": quyen})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _moi_events() -> list[str]:
    from agent import db
    return [r["t"] for r in await db.fetch("SELECT kind || ' ' || coalesce(detail::text, '') AS t FROM events")]


async def _co_phai_doi(ten: str) -> bool:
    from agent import db
    r = await db.fetchrow(
        "SELECT phai_doi_mat_khau FROM nguoi_dung WHERE ten_dang_nhap = $1", ten)
    return bool(r and r["phai_doi_mat_khau"])


# =====================================================================
#  Đặt lại mật khẩu (UX-13-07)
# =====================================================================

def test_dat_lai_mat_khau_thu_phien_va_bat_doi_o_lan_dang_nhap_toi(app_that):
    """
    BƯỚC 1  Nhân viên đang đăng nhập; quản trị bấm Đặt lại mật khẩu, để trống.
    BƯỚC 2  Máy chủ trả mật khẩu tạm MỘT lần, không cho lưu đệm; phiên cũ chết.
    BƯỚC 3  Mật khẩu cũ hết dùng; mật khẩu tạm đăng nhập được.
    BƯỚC 4  Với mật khẩu tạm: /api/toi được, mọi màn khác 403 kèm cờ.
    BƯỚC 5  "Đổi" sang chính mật khẩu tạm bị từ chối; đổi thật thì hết cờ.
    """
    qt = _quan_tri_vao(app_that)
    uid, nv = _nhan_vien_moi(qt, "lan.quen")
    assert nv.get("/api/toi").status_code == 200

    r = qt.post(f"/api/nguoi-dung/{uid}/dat-lai-mat-khau", json={})
    assert r.status_code == 200, r.text
    kq = r.json()
    assert r.headers.get("cache-control") == "no-store"
    tam = kq["mat_khau_tam"]
    assert len(tam) >= 12 and kq["so_phien_thu_hoi"] >= 1 and kq["phai_doi_mat_khau"] is True

    assert nv.get("/api/toi").status_code == 401, "phiên cũ phải bị thu hồi"
    assert _dang_nhap(app_that, "lan.quen", MK)[0] == 401, "mật khẩu cũ phải hết dùng"
    ma, nv2 = _dang_nhap(app_that, "lan.quen", tam)
    assert ma == 200

    toi = nv2.get("/api/toi")
    assert toi.status_code == 200 and toi.json()["phai_doi_mat_khau"] is True
    for duong in ("/api/nguoi-dung", "/api/quyen", "/api/toi/thong-bao/so-chua-doc"):
        bi = nv2.get(duong)
        assert bi.status_code == 403, (duong, bi.status_code)
        assert bi.json().get("phai_doi_mat_khau") is True

    giu = nv2.post("/api/toi/doi-mat-khau", json={"mat_khau_cu": tam, "mat_khau_moi": tam})
    assert giu.status_code == 422, giu.text
    assert _sql(app_that, _co_phai_doi, "lan.quen") is True

    doi = nv2.post("/api/toi/doi-mat-khau",
                   json={"mat_khau_cu": tam, "mat_khau_moi": "mat-khau-rieng-cua-lan"})
    assert doi.status_code == 200, doi.text
    assert _sql(app_that, _co_phai_doi, "lan.quen") is False
    ma, nv3 = _dang_nhap(app_that, "lan.quen", "mat-khau-rieng-cua-lan")
    assert ma == 200
    assert nv3.get("/api/toi").json()["phai_doi_mat_khau"] is False
    assert nv3.get("/api/nguoi-dung").status_code == 200


def test_mat_khau_khong_bao_gio_vao_nhat_ky(app_that):
    """Cả bản tự sinh lẫn bản quản trị gõ: không ký tự nào của nó trong `events`."""
    qt = _quan_tri_vao(app_that)
    a, _ = _nhan_vien_moi(qt, "nv.sinh")
    b, _ = _nhan_vien_moi(qt, "nv.go")
    sinh = qt.post(f"/api/nguoi-dung/{a}/dat-lai-mat-khau", json={}).json()["mat_khau_tam"]
    go = "Tam-thoi-quan-tri-go-1"
    r = qt.post(f"/api/nguoi-dung/{b}/dat-lai-mat-khau", json={"mat_khau_tam": go})
    assert r.status_code == 200 and "mat_khau_tam" not in r.json(), \
        "mật khẩu quản trị tự gõ không được vọng lại trong phản hồi"

    moi = _sql(app_that, _moi_events)
    assert moi, "không đọc được bảng events — phép kiểm hỏng"
    lo = [t for t in moi if sinh in t or go in t]
    assert not lo, f"mật khẩu lọt vào nhật ký: {lo[:2]}"

    ls = qt.get("/api/nhan-su/lich-su", params={"ref_id": a}).json()["lich_su"]
    dong = next(x for x in ls if x["loai"] == "nguoi_dung.dat_lai_mat_khau")
    assert dong["chi_tiet"]["tu_sinh"] is True and dong["nguoi_lam"] == "sep"


def test_dat_lai_mat_khau_khong_vuot_quyen(app_that):
    """
    Đặt lại mật khẩu của cấp trên = đăng nhập được bằng tài khoản cấp trên —
    leo thang đi đường vòng. Cùng luật `chan_cap_vuot` với gán vai trò, khoá.
    """
    qt = _quan_tri_vao(app_that, ten="giamdoc")
    vid = _vai_tro(qt, "Nhân sự", ["nguoi_dung.doc", "nguoi_dung.sua"])
    hr_id, hr = _nhan_vien_moi(qt, "nhansu.hr", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{hr_id}/vai-tro", json={"vai_tro": [vid]}).status_code == 200
    ma, hr = _dang_nhap(app_that, "nhansu.hr", MK)
    assert ma == 200

    sep = next(n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"] if n["ten_dang_nhap"] == "giamdoc")
    assert hr.post(f"/api/nguoi-dung/{sep['id']}/dat-lai-mat-khau", json={}).status_code == 403
    assert _sql(app_that, _co_phai_doi, "giamdoc") is False, "403 mà vẫn bật cờ là ghi nửa chừng"
    nv_id, _ = _nhan_vien_moi(qt, "nv.thuong")          # Nhân viên có quyền hr không có
    assert hr.post(f"/api/nguoi-dung/{nv_id}/dat-lai-mat-khau", json={}).status_code == 403

    yeu = _vai_tro(qt, "Chỉ xem NV", ["nguoi_dung.doc"])
    y_id, _ = _nhan_vien_moi(qt, "nv.yeu", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{y_id}/vai-tro", json={"vai_tro": [yeu]}).status_code == 200
    ma, hr = _dang_nhap(app_that, "nhansu.hr", MK)
    assert hr.post(f"/api/nguoi-dung/{y_id}/dat-lai-mat-khau", json={}).status_code == 200

    # Tự đặt lại cho mình đi đường vòng qua bước gõ mật khẩu hiện tại.
    assert hr.post(f"/api/nguoi-dung/{hr_id}/dat-lai-mat-khau", json={}).status_code == 422
    # Không có `nguoi_dung.sua` thì không có nút này.
    _, nv = _nhan_vien_moi(qt, "nv.khac")
    assert nv.post(f"/api/nguoi-dung/{y_id}/dat-lai-mat-khau", json={}).status_code == 403
    # Mật khẩu tạm tự gõ cũng phải đủ 8 ký tự.
    assert qt.post(f"/api/nguoi-dung/{y_id}/dat-lai-mat-khau",
                   json={"mat_khau_tam": "ngan"}).status_code == 422


def test_tao_tai_khoan_co_the_bat_doi_mat_khau_lan_dau(app_that):
    """Mật khẩu ban đầu là thứ người tạo biết; dashboard gửi cờ bật sẵn."""
    qt = _quan_tri_vao(app_that)
    r = qt.post("/api/nguoi-dung", json={"ten_dang_nhap": "moi.vao", "mat_khau": MK,
                                         "ho_ten": "Mới Vào", "phai_doi_mat_khau": True})
    assert r.status_code == 200 and r.json()["phai_doi_mat_khau"] is True
    ma, nv = _dang_nhap(app_that, "moi.vao", MK)
    assert ma == 200 and nv.get("/api/toi").json()["phai_doi_mat_khau"] is True
    assert nv.get("/api/nguoi-dung").status_code == 403
    # Lời gọi cũ không gửi cờ: giữ đúng hành vi cũ.
    _, nv2 = _nhan_vien_moi(qt, "cu.van.the")
    assert nv2.get("/api/toi").json()["phai_doi_mat_khau"] is False


# =====================================================================
#  Mở khoá tài khoản mang quyền nhạy cảm (SEC-13-01)
# =====================================================================

def test_mo_khoa_tai_khoan_mang_quan_tri_phai_xac_nhan_rieng(app_that):
    """
    BƯỚC 1  Tài khoản "chỉ xem" mang cả Quản trị + Nhân viên, đang khoá.
    BƯỚC 2  Mở khoá thường -> 409, nói rõ vai trò nào; tài khoản VẪN khoá.
    BƯỚC 3  Xác nhận riêng -> mở được; lịch sử ghi vai trò nhạy cảm đã được báo.
    BƯỚC 4  Mở khoá một nhân viên thường: không bị hỏi thêm.
    """
    qt = _quan_tri_vao(app_that)
    uid, _ = _nhan_vien_moi(qt, "staff_view")
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [
        _id_vai_tro(qt, "Quản trị"), _id_vai_tro(qt, "Nhân viên")]}).status_code == 200
    assert qt.post("/api/nguoi-dung/staff_view/khoa?khoa=true").status_code == 200

    r = qt.post("/api/nguoi-dung/staff_view/khoa?khoa=false")
    assert r.status_code == 409, r.text
    ct = r.json()["detail"]
    assert ct["can_xac_nhan_nhay_cam"] is True
    assert "Quản trị" in ct["vai_tro"] and "Nhân viên" not in ct["vai_tro"]
    assert "nguoi_dung.sua" in ct["vai_tro"]["Quản trị"]
    assert _dang_nhap(app_that, "staff_view", MK)[0] == 401, "409 mà vẫn mở là chốt vô dụng"

    r = qt.post("/api/nguoi-dung/staff_view/khoa?khoa=false&xac_nhan_nhay_cam=true")
    assert r.status_code == 200, r.text
    assert _dang_nhap(app_that, "staff_view", MK)[0] == 200
    ls = qt.get("/api/nhan-su/lich-su", params={"ref_id": uid}).json()["lich_su"]
    mo = next(x for x in ls if x["loai"] == "auth.khoa_nguoi_dung" and x["chi_tiet"]["khoa"] is False)
    assert "Quản trị" in mo["chi_tiet"]["vai_tro_nhay_cam"]

    _, _nv = _nhan_vien_moi(qt, "nv.binh.thuong")
    assert qt.post("/api/nguoi-dung/nv.binh.thuong/khoa?khoa=true").status_code == 200
    assert qt.post("/api/nguoi-dung/nv.binh.thuong/khoa?khoa=false").status_code == 200


def test_mo_khoa_vai_tro_tu_tao_co_quyen_nhay_cam_cung_bi_hoi(app_that):
    """Không chỉ Quản trị: vai trò tự tạo có `khach.xoa` cũng là chìa khoá nguy hiểm."""
    qt = _quan_tri_vao(app_that)
    vid = _vai_tro(qt, "Xoá dữ liệu", ["khach.doc", "khach.xoa"])
    uid, _ = _nhan_vien_moi(qt, "nv.xoa", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [vid]}).status_code == 200
    assert qt.post("/api/nguoi-dung/nv.xoa/khoa?khoa=true").status_code == 200
    r = qt.post("/api/nguoi-dung/nv.xoa/khoa?khoa=false")
    assert r.status_code == 409 and r.json()["detail"]["vai_tro"] == {"Xoá dữ liệu": ["khach.xoa"]}
    # Vai trò đã NGỪNG DÙNG không cấp gì -> không cảnh báo về nó.
    assert qt.post(f"/api/vai-tro/{vid}/trang-thai", json={"dang_dung": False}).status_code == 200
    assert qt.post("/api/nguoi-dung/nv.xoa/khoa?khoa=false").status_code == 200


def test_danh_muc_quyen_tra_danh_sach_nhay_cam(app_that):
    from agent.core.quyen import QUYEN_NHAY_CAM

    qt = _quan_tri_vao(app_that)
    assert qt.get("/api/quyen").json()["nhay_cam"] == QUYEN_NHAY_CAM


def test_quyen_nhay_cam_hop_le_va_khong_dung_quyen_nhan_vien_thuong():
    """
    Tô đỏ thứ ai cũng có là màu đỏ mất nghĩa — và mở khoá MỌI nhân viên sẽ
    thành một hộp cảnh báo người ta bấm qua theo phản xạ.
    """
    from agent.core.quyen import QUYEN, QUYEN_NHAY_CAM

    assert set(QUYEN_NHAY_CAM) <= set(QUYEN), sorted(set(QUYEN_NHAY_CAM) - set(QUYEN))
    assert {"nguoi_dung.sua", "cau_hinh.sua", "khach.xoa", "agent.dieu_khien"} <= set(QUYEN_NHAY_CAM)
    assert all(len(ly_do) > 20 for ly_do in QUYEN_NHAY_CAM.values()), "lý do phải nói được hậu quả"

    sql = (ROOT / "agent/migrations/versions/0019_quyen_va_vai_tro.sql").read_text(encoding="utf-8")
    khoi = sql[sql.index("CROSS JOIN (VALUES"):sql.index("WHERE vt.ten = 'Nhân viên'")]
    nhan_vien = set(re.findall(r"\('([a-z_]+\.[a-z_]+)'\)", khoi))
    assert len(nhan_vien) > 10, "đọc tập quyền Nhân viên hỏng — phép kiểm vô nghĩa"
    nhan_vien |= {"ai.duyet", "hoi_thoai.ghi_chu", "kho.doc"}   # 0058 cấp thêm theo quyền cũ
    assert not nhan_vien & set(QUYEN_NHAY_CAM), sorted(nhan_vien & set(QUYEN_NHAY_CAM))


# =====================================================================
#  Dashboard: hộp xác nhận chung và các màn Nhân sự
# =====================================================================

def _bo_chu_thich(js: str) -> str:
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", js)


def _than(ten: str) -> str:
    m = re.search(rf"(?:async )?function {ten}\(.*?\n\}}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


def test_hop_xac_nhan_chung_co_canh_bao_va_go_lai_ten():
    """API cũ của hoiHop giữ nguyên; tham số mới đều tuỳ chọn."""
    than = _than("hoiHop")
    for k in ("anh_huong", "canh_bao", "go_xac_nhan", "bi_mat", "nut_huy", "an_huy"):
        assert k in than.split(")")[0] or f"{k} =" in than, k
    assert 'nguy_hiem = false' in than and 'nut = "Lưu"' in than
    # Gõ lại: nút chính KHOÁ tới khi gõ đúng, và kiểm lại lúc gửi.
    assert "nutGui.disabled = !!go_xac_nhan" in than
    assert "d._go_xac_nhan !== can" in JS and "delete d._go_xac_nhan" in JS
    # Mọi chuỗi qua esc(): cảnh báo mang tên người, tên vai trò.
    assert "esc(x)" in _than("hoiVeKhoi") and "esc(bi_mat)" in _than("hoiVeKhoi")
    # Bí mật không nằm lại trong DOM sau khi đóng hộp.
    assert '$("#hoiKhoi").innerHTML = ""' in _than("hoiDong")
    assert 'id="hoiKhoi"' in HTML and 'aria-modal="true"' in HTML[HTML.index('id="congHoi"') - 80:]


def test_man_nhan_su_khong_con_confirm_cua_trinh_duyet():
    """UX-12-04, UX-13-05: ngừng dùng/xoá vai trò, khoá/mở khoá đi qua hoiHop."""
    for ten in ("24-nhan-su.js", "24b-nhan-su-nhan-vien.js", "24c-nhan-su-vai-tro.js", "09-nhan-su.js"):
        ma = _bo_chu_thich((SRC / ten).read_text(encoding="utf-8"))
        assert not re.search(r"(?<![\w.])confirm\(", ma), f"{ten} còn confirm()"
    for ham in ("nsvKhoa", "nsvHoiMoKhoa", "nsvDoiTrangThaiVai", "nsvXoaVaiTro", "nsvDatLaiMatKhau"):
        assert "hoiHop(" in _than(ham), ham


def test_mo_khoa_tren_man_hinh_canh_bao_va_bat_go_lai_ten():
    than = _than("nsvHoiMoKhoa")
    assert "canh_bao: ds.length" in than and "go_xac_nhan: ds.length ? n.ten_dang_nhap" in than
    mo = _than("nsvMoKhoa")
    assert "xac_nhan_nhay_cam=true" in mo and "can_xac_nhan_nhay_cam" in mo
    # Màn cũ cũng mở khoá qua cùng một hàm.
    assert "if (n) { await nsvKhoa(n, loadNhanSu); return; }" in JS


def test_khoa_mot_hop_noi_du_viec_dang_giu():
    than = _than("nsvKhoa")
    assert "canh_bao: viec.tong" in than and "__de_lai__" in than
    assert "nsvLietKeViec(viec)" in than


def test_dat_lai_mat_khau_tren_man_hinh_hien_mot_lan():
    than = _than("nsvDatLaiMatKhau")
    assert "/dat-lai-mat-khau" in than and "bi_mat: kq.mat_khau_tam" in than
    assert "an_huy: true" in than
    # Không đưa mật khẩu ra toast hay console.
    assert "toast(kq" not in than and "console" not in than


def test_bang_quyen_tim_duoc_thu_gon_duoc_va_giau_ma():
    """UX-12-03: nhóm thu gọn, ô tìm, quyền nhạy cảm tô đỏ, mã chỉ ở title."""
    than = _than("nsvBangQuyen")
    assert "<details" in than and "data-nsv-tim-quyen" in than
    assert "nsvTheNhayCam(q.ma)" in than and 'title="Mã: ${esc(q.ma)}"' in than
    assert "<code>" not in than, "mã quyền không còn hiện cạnh nhãn"
    assert "nsvBoDau" in _than("nsvLocQuyen")


def test_gan_vai_tro_co_tom_tat_quyen_hieu_luc_va_canh_bao():
    than = _than("nsvTomTatVai")
    assert "toan_quyen" in than and "nsvLaNhayCam" in than
    assert "nsvXacNhanVaiNhayCam(cu, vai, ten)" in _than("nsvLuuNguoi")


def test_xem_quyen_nguoi_co_tuy_chon_hien_ca_quyen_chua_cap():
    than = _than("nsvVeQuyenNguoi")
    assert "hienCa ? g.quyen : coNhom" in than and "data-nsv-hien-ca" in than


def test_bat_doi_mat_khau_khi_vao_dashboard():
    assert "if (nguoi.phai_doi_mat_khau) { nsvBatDoiMatKhau(); return false; }" in _than("kiemPhien")
    assert "dataset.batBuoc" in JS


def test_nhan_vien_co_tim_loc_va_lich_ca_o_tab_rieng():
    loc = _than("nsvHopLoc")
    for k in ("nsvLoc.chu", "nsvLoc.vai", '"khoa"', '"nhay_cam"'):
        assert k in loc, k
    assert 'if (tabDangHien("ns-lich-ca")) await loadLichCa();' in _than("refresh")
    assert 'GAN_TAB["ns-lich-su"]' in JS
    i = HTML.index('id="ns-lich-ca"')
    assert HTML.index('id="lcPanel"') > i


def test_chot_phai_doi_mat_khau_nam_o_middleware_that():
    """Che màn hình không đủ: chốt phải nằm ở middleware của app thật."""
    import inspect

    import agent.main as main

    nguon = inspect.getsource(main.chan_neu_chua_dang_nhap)
    assert 'nguoi.get("phai_doi_mat_khau")' in nguon
    assert main._MO_KHI_PHAI_DOI_MK == {"/api/toi", "/api/toi/doi-mat-khau"}
