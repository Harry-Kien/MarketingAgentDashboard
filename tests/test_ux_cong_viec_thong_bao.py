"""
Đợt UX màn Công việc (STT 14) và chuông thông báo (STT 19).

Mỗi ràng buộc ở đây là một cách hỏng IM LẶNG nếu không có test canh:

  · Số trên chip lọc nhanh phải là số THẬT của máy chủ, tính trên phạm vi +
    bộ lọc phụ — không đếm trên danh sách đã cắt `limit`.
  · Ô gợi ý mã đơn KHÔNG được là cửa sau đọc đơn kênh khác; có khách thì chỉ
    đơn của khách ấy. Gõ tay mã đơn kênh khác lúc tạo việc cũng phải bị chặn
    — chặn ở gợi ý mà không chặn lúc tạo là chặn nửa vời.
  · Mô tả gợi ý khi tạo việc từ hội thoại là tin KHÁCH nguyên văn — không lẫn
    tin AI/nhân viên, không gọi mô hình, không mất tin chỉ có ảnh.
  · Danh sách người nhận nói ca và tải từ dữ liệu thật — không có nhãn đoán.
  · "Cần xử lý" của chuông theo TÌNH TRẠNG THẬT: việc đã xong thì thông báo
    "Được giao việc" của nó không còn đứng trong nhóm cần làm.
  · Mỗi loại lịch sử việc, mỗi loại thông báo đều được xếp nhóm — thêm loại
    mới mà quên xếp thì đỏ ở đây, thay vì lặng lẽ rơi khỏi bộ lọc.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import nguoi_thu  # noqa: E402
from tests.test_he_thong_giao_viec import (  # noqa: E402
    SEP_ID, _app, _chay, _dung, _sep,
)

SRC = ROOT / "dashboard" / "src"
TB_JS = (SRC / "19-thong-bao.js").read_text(encoding="utf-8")
CT_JS = (SRC / "25b-cong-viec-chi-tiet.js").read_text(encoding="utf-8")
TAO_JS = (SRC / "25c-cong-viec-tao.js").read_text(encoding="utf-8")
DS_JS = (SRC / "25-cong-viec.js").read_text(encoding="utf-8")

_ESC = ("function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;',"
        "'>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n")


def _node(ma: str):
    node = shutil.which("node")
    assert node, "Cần node để kiểm giao diện"
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True,
                       encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ------------------------------------------------------------------ không cần CSDL

def test_moi_loai_lich_su_deu_duoc_xep_nhom_loc():
    from agent.core import cong_viec as cv

    assert set(cv.NHOM_LICH_SU) == set(cv.LOAI_LICH_SU)
    assert set(cv.NHOM_LICH_SU.values()) <= set(cv.NHAN_NHOM_LICH_SU) | {"khac"}
    # Bốn bộ lọc của phiếu: Tất cả / Phân công / Tiến độ / Trạng thái & kết quả.
    assert list(cv.NHAN_NHOM_LICH_SU) == ["phan_cong", "tien_do", "trang_thai"]
    assert cv.NHOM_LICH_SU["chuyen"] == "phan_cong"
    assert cv.NHOM_LICH_SU["ket_qua"] == "trang_thai"


def test_mo_ta_goi_y_la_tin_khach_nguyen_van_va_ngan():
    from agent.core import cong_viec as cv

    luc = datetime(2026, 11, 25, 7, 5, tzinfo=timezone.utc)   # 14:05 giờ VN
    tin = [
        {"noi_dung": "tin cũ nhất không được lấy", "luc": luc},
        {"noi_dung": "Cho em đổi   sang tuýp 50ml", "luc": luc},
        {"noi_dung": "", "luc": luc},
        {"noi_dung": "x" * 400, "luc": luc},
    ]
    ra = cv.tom_tat_tin_khach(tin, kenh="Zalo cá nhân")
    assert ra.startswith("Khách nhắn gần nhất (Zalo cá nhân):")
    assert "tin cũ nhất" not in ra, "chỉ lấy SO_TIN_GOI_Y tin gần nhất"
    assert "• 14:05 25/11: Cho em đổi sang tuýp 50ml" in ra
    assert "(khách gửi ảnh/tệp đính kèm)" in ra, "tin chỉ có ảnh không được biến mất"
    dong_dai = ra.splitlines()[-1]
    assert dong_dai.endswith("…") and len(dong_dai) < 320
    assert cv.tom_tat_tin_khach([]) == ""


def test_moi_loai_thong_bao_deu_duoc_xep_can_xu_ly_hoac_thong_tin():
    from agent.core import thong_bao_noi_bo as tb

    hanh_dong = set(tb.LOAI_HANH_DONG)
    assert hanh_dong | tb.LOAI_THONG_TIN == set(tb.LOAI)
    assert not hanh_dong & tb.LOAI_THONG_TIN
    for loai in hanh_dong:
        assert f"WHEN '{loai}' THEN" in tb._SQL_CAN_XU_LY, loai
    assert tb.nhom_thong_bao("viec_huy", True) == "thong_tin"
    assert tb.nhom_thong_bao("duoc_giao_viec", True) == "can_xu_ly"
    assert tb.nhom_thong_bao("duoc_giao_viec", False) == "da_xu_ly"


def test_chuong_phan_nhom_rut_gon_va_an_huong_dan_khi_da_xong():
    ma = (_ESC + "function clock(x){return '21:00';}\nfunction $(s){return null;}\n"
          + TB_JS.split('$("#chuongNut")?.addEventListener')[0]
          + """
          const goc = {id:'1', loai:'duoc_giao_viec', nhan_loai:'Được giao việc', tieu_de:'Gọi lại khách',
                       tao_luc:'2026-11-25T21:00:00Z', da_doc:true, noi_dung:'a'.repeat(300)};
          const can = dongThongBao({...goc, nhom:'can_xu_ly', can_xu_ly:true});
          const xong = dongThongBao({...goc, nhom:'da_xu_ly', can_xu_ly:false});
          const tin = dongThongBao({...goc, loai:'viec_huy', nhom:'thong_tin', can_xu_ly:false});
          console.log(JSON.stringify({can, xong, tin}));
          """)
    r = _node(ma)
    assert "Cần xử lý" in r["can"] and "chuong__huongdan" in r["can"]
    assert "Đã xử lý" in r["xong"] and "chuong__huongdan" not in r["xong"]
    assert "Thông tin" in r["tin"] and "chuong__huongdan" not in r["tin"]
    mo_ta = r["can"].split('chuong__mota">')[1].split("</span>")[0]
    assert mo_ta.endswith("…") and len(mo_ta) <= 110, "mô tả chuông phải ngắn"


def test_xem_them_khoa_nut_hien_dang_tai_va_cuon_toi_dong_moi():
    nut = {"disabled": False, "innerHTML": "Xem thêm", "attrs": {}}
    ma = (_ESC + "const NUT = " + json.dumps(nut) + ";\n"
          "NUT.setAttribute = (k, v) => { NUT.attrs[k] = v; };\n"
          "function $(s){return s === '#chuongThem' ? NUT : null;}\n"
          + TB_JS.split('$("#chuongNut")?.addEventListener')[0]
          + """
          nutThemChuong(true);
          const dang = {disabled: NUT.disabled, html: NUT.innerHTML, busy: NUT.attrs['aria-busy']};
          nutThemChuong(false);
          console.log(JSON.stringify({dang, sau: {disabled: NUT.disabled, html: NUT.innerHTML}}));
          """)
    r = _node(ma)
    assert r["dang"] == {"disabled": True, "busy": "true",
                         "html": '<span class="chuong__xoay" aria-hidden="true"></span>Đang tải…'}
    assert r["sau"] == {"disabled": False, "html": "Xem thêm"}
    tai = TB_JS[TB_JS.index("async function taiDanhSachChuong"):]
    assert "scrollIntoView" in tai and "[soCu]" in tai, "phải cuộn tới dòng mới đầu tiên"
    assert 'q.set("can_xu_ly", "true")' in tai, "lọc Cần xử lý ở máy chủ, không ở trình duyệt"


def _hanh_dong(viec: dict, quyen: list[str], toi: str = "u1", xu_ly_don: bool = False) -> dict:
    ma = ("const state = {toiId: %s, toiQuyen: new Set(%s)};\n" % (json.dumps(toi), json.dumps(quyen))
          + "function cvxCo(q){return state.toiQuyen.has(q);}\n"
          + "function cvLaXuLyDon(v){return %s;}\nfunction cvDuocXacNhan(){return true;}\n"
          % ("true" if xu_ly_don else "false")
          + "const window = {matchMedia: () => ({matches: false})};\n"
          + "const document = {addEventListener(){}};\n"
          + CT_JS
          + "\nconsole.log(JSON.stringify(cvxHanhDong(%s)));" % json.dumps(viec))
    return _node(ma)


def test_chi_tiet_mot_nut_chinh_theo_trang_thai_con_lai_vao_menu():
    du = ["cong_viec.doc", "cong_viec.sua", "cong_viec.giao"]
    chua_giao = _hanh_dong({"trang_thai": "moi", "chua_phan_cong": True, "nguoi_nhan": None}, du)
    assert chua_giao["chinh"][0] == "nhan"
    cua_toi = _hanh_dong({"trang_thai": "moi", "chua_phan_cong": False, "nguoi_nhan": "u1"}, du)
    assert cua_toi["chinh"][0] == "bat-dau"
    dang = _hanh_dong({"trang_thai": "dang_lam", "chua_phan_cong": False, "nguoi_nhan": "u1"}, du)
    assert dang["chinh"][0] == "xong-nhanh" and dang["xongNhanh"] is True
    ma_menu = [m[0] for m in dang["them"]]
    assert ma_menu[-1] == "huy", "thao tác phá huỷ đứng cuối menu, tách khỏi nút chính"
    assert "xong-nhanh" not in ma_menu, "nút chính không lặp lại trong menu"
    xong = _hanh_dong({"trang_thai": "xong", "chua_phan_cong": False, "nguoi_nhan": "u1"}, du)
    assert xong["chinh"][0] == "mo-lai" and not xong["xongNhanh"]
    # Việc xử lý ĐƠN không bao giờ "Hoàn thành" nhanh: phải qua đối soát ERP.
    don = _hanh_dong({"trang_thai": "dang_lam", "chua_phan_cong": False, "nguoi_nhan": "u1"},
                     du, xu_ly_don=True)
    assert don["chinh"][0] == "don" and not don["xongNhanh"]
    # Chỉ có quyền đọc: không nút nào.
    doc = _hanh_dong({"trang_thai": "dang_lam", "chua_phan_cong": False, "nguoi_nhan": "u2"},
                     ["cong_viec.doc"])
    assert doc == {"chinh": None, "them": [], "xongNhanh": False}


def test_hoan_thanh_nhanh_van_bat_buoc_ghi_ket_qua():
    khoi = CT_JS[CT_JS.index("const xong = hd.xongNhanh"):CT_JS.index("o.innerHTML = `<div class=\"cvx-ngan__dau\">")]
    assert 'name="ket_qua"' in khoi and "required" in khoi
    gui = CT_JS[CT_JS.index("async function cvxXongNhanh"):CT_JS.index("function cvxBatSuKienNgan")]
    assert "if (!kq)" in gui and 'trang_thai: "xong", ket_qua: kq' in gui


def test_chon_nguoi_noi_ca_va_tai_tu_du_lieu_that():
    ma = (_ESC + "const window = {matchMedia: () => ({matches: false})};\n"
          "const document = {addEventListener(){}};\n" + CT_JS + """
          const html = cvxVeDsNguoi('x', [
            {id:'a', ten:'An', trong_ca_that:true, co_lich:true, san_sang:true, cung_kenh:true, so_mo:3, so_qua_han:1},
            {id:'b', ten:'Bình', trong_ca_that:false, co_lich:true, san_sang:false, cung_kenh:false, so_mo:0, so_qua_han:0},
            {id:'c', ten:'Chi', trong_ca_that:false, co_lich:false, san_sang:true, cung_kenh:true, so_mo:0, so_qua_han:0},
            {id:'d', ten:'Dũng', dang_nghi:true, trong_ca_that:false, co_lich:true, san_sang:true, cung_kenh:true, so_mo:1, so_qua_han:0},
          ], 'a');
          console.log(JSON.stringify(html));
          """)
    html = _node(ma)
    assert "cvx-cham--trong" in html and "Đang trong ca" in html
    assert "cvx-cham--ngoai" in html and "Ngoài ca" in html and "tắt sẵn sàng" in html
    assert "cvx-cham--chua" in html and "Chưa xếp ca" in html
    assert "cvx-cham--nghi" in html and "Đang nghỉ" in html
    assert html.count("Đang nghỉ") == 1, "chỉ người CÓ lịch nghỉ mới hiện Đang nghỉ"
    assert "3 việc mở · 1 quá hạn" in html and "KHÔNG thuộc kênh của việc" in html


def test_tao_viec_la_ngan_khong_phai_hop_hoi_va_khong_dung_hop_trinh_duyet():
    assert "hoiHop(" not in TAO_JS, "tạo việc phải ở ngăn riêng, không ở hộp hỏi hẹp"
    assert 'role="dialog"' in TAO_JS and 'aria-modal="true"' in TAO_JS
    assert 'role="combobox"' in TAO_JS and "/cong-viec/goi-y-don" in TAO_JS
    assert "/cong-viec/ngu-canh-tao" in TAO_JS
    for ten, js in (("25", DS_JS), ("25b", CT_JS), ("25c", TAO_JS), ("19", TB_JS)):
        for cam in ("confirm(", "prompt(", "alert("):
            assert cam not in js, f"{ten}: {cam}"


def test_mo_tu_chuong_ghim_viec_khong_khop_bo_loc():
    """UX-19-01: không lặng lẽ mở chi tiết của một việc không thấy trong danh sách."""
    tai = CT_JS[CT_JS.index("async function cvxTaiChiTiet"):CT_JS.index("/* ---------------- hành động")]
    assert "cvx.ghim = trongDs ? null : d.cong_viec" in tai
    assert "cvxDong(cvx.ghim, true)" in DS_JS
    assert "Mở từ thông báo — không khớp bộ lọc đang chọn" in DS_JS


# ------------------------------------------------------------------ dựng dữ liệu

async def _kenh(conn, ten: str) -> UUID:
    return await conn.fetchval(
        # `external_account_id` riêng: unique (channel, external_account_id)
        # coi hai NULL là trùng — hai kênh webchat không id ngoài thì nổ.
        "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
        "VALUES ('webchat', $1, 'active', $1) RETURNING id", ten)


async def _hoi_thoai(conn, tk: UUID, ext: str, ten: str) -> tuple[UUID, UUID]:
    kh = await conn.fetchval("INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ten)
    diem = await conn.fetchval(
        "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
        "VALUES ($1,$2,$3) RETURNING id", kh, tk, ext)
    cid = await conn.fetchval(
        "INSERT INTO conversations (account_id, channel, external_id, customer_ref, "
        "customer_name, contact_id, contact_point_id) VALUES ($1,'webchat',$2,$2,$3,$4,$5) "
        "RETURNING id", tk, ext, ten, kh, diem)
    return cid, kh


async def _don(conn, ma: str, cid: UUID | None, sdt: str = "0901234567") -> UUID:
    return await conn.fetchval(
        "INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt, khach_dia_chi, "
        "tong_tien) VALUES ($1,$2,'Khách','" + sdt + "','HN', 250000) RETURNING id", ma, cid)


def _hai_kenh(url: str):
    """Kênh A (nhân viên `an` là thành viên): khách Hoa có đơn A1, khách Lan có
    đơn A2. Kênh B: đơn B1. Trả (an_id, hoa_cid, hoa_kh, lan_cid)."""
    an, = _dung(url, ("an", {}))

    async def chay(conn):
        a = await _kenh(conn, "Kênh A")
        b = await _kenh(conn, "Kênh B")
        hoa, hoa_kh = await _hoi_thoai(conn, a, "hoa", "Chị Hoa")
        lan, _ = await _hoi_thoai(conn, a, "lan", "Chị Lan")
        ngoai, _ = await _hoi_thoai(conn, b, "ngoai", "Khách B")
        await _don(conn, "DH-A1", hoa, "0912 345 678")
        await _don(conn, "DH-A2", lan)
        await _don(conn, "DH-B1", ngoai)
        await conn.execute(
            "INSERT INTO account_memberships (account_id, user_id, role) VALUES ($1,$2,'agent')",
            a, UUID(an))
        return str(hoa), str(hoa_kh), str(lan)

    return (an, *_chay(url, chay))


# ------------------------------------------------------------------ đếm chip lọc nhanh

def test_danh_sach_tra_so_dem_chip_va_tong_that(csdl_kiem_thu):
    _dung(csdl_kiem_thu)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        qua = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        ids = [khach.post("/api/cong-viec", json={"tieu_de": f"Việc {i}"}).json()["id"]
               for i in range(5)]
        khach.post("/api/cong-viec", json={"tieu_de": "Gọi khách quá hạn", "han": qua})
        khach.put(f"/api/cong-viec/{ids[0]}", json={"trang_thai": "dang_lam", "nguoi_nhan": SEP_ID})
        khach.put(f"/api/cong-viec/{ids[1]}", json={"trang_thai": "xong", "ket_qua": "ok"})
        khach.put(f"/api/cong-viec/{ids[2]}", json={"trang_thai": "huy", "ghi_chu": "trùng"})

        d = khach.get("/api/cong-viec").json()
        assert d["dem"] == {"tat_ca": 6, "cho_xu_ly": 3, "dang_lam": 1, "qua_han": 1,
                            "hoan_thanh": 1, "da_huy": 1, "chua_phan_cong": 3}
        assert d["tong"] == 6

        # Chip đang bật KHÔNG làm các chip khác về 0; `tong` theo đúng bộ lọc.
        qh = khach.get("/api/cong-viec", params={"qua_han": "true"}).json()
        assert qh["tong"] == 1 and len(qh["cong_viec"]) == 1
        assert qh["dem"]["tat_ca"] == 6 and qh["dem"]["hoan_thanh"] == 1

        # Bộ lọc phụ (tìm) thu hẹp cả số đếm.
        tim = khach.get("/api/cong-viec", params={"q": "quá hạn"}).json()
        assert tim["dem"]["tat_ca"] == 1 and tim["dem"]["qua_han"] == 1

        # `tong` đếm bằng SQL, không bằng danh sách đã cắt `limit`.
        cat = khach.get("/api/cong-viec", params={"limit": 2}).json()
        assert len(cat["cong_viec"]) == 2 and cat["tong"] == 6


def test_dong_viec_mang_tien_do_that_va_lich_su_co_nhom(csdl_kiem_thu):
    _dung(csdl_kiem_thu)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        vid = khach.post("/api/cong-viec", json={"tieu_de": "Gọi lại khách"}).json()["id"]
        d = next(v for v in khach.get("/api/cong-viec").json()["cong_viec"] if v["id"] == vid)
        assert d["so_tien_do"] == 0 and d["tien_do_cuoi"] is None
        for chu in ("Đã gọi lần 1", "Khách hẹn 15h"):
            assert khach.post(f"/api/cong-viec/{vid}/tien-do", json={"noi_dung": chu}).status_code == 201
        khach.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": SEP_ID})
        d = next(v for v in khach.get("/api/cong-viec").json()["cong_viec"] if v["id"] == vid)
        assert d["so_tien_do"] == 2 and d["tien_do_cuoi"] == "Khách hẹn 15h" and d["tien_do_luc"]

        from agent.core import cong_viec as cv

        ct = khach.get(f"/api/cong-viec/{vid}").json()
        nhom = [(dong["loai"], dong["nhom"]) for dong in ct["lich_su"]]
        assert all(n == cv.NHOM_LICH_SU[loai] for loai, n in nhom), nhom
        assert [n for _, n in nhom].count("tien_do") == 2
        assert "phan_cong" in [n for _, n in nhom], "giao việc phải vào nhóm Phân công"
        assert [n["ma"] for n in ct["nhom_lich_su"]] == ["phan_cong", "tien_do", "trang_thai"]


# ------------------------------------------------------------------ gợi ý mã đơn

def test_goi_y_don_can_quyen_don_doc(csdl_kiem_thu):
    an, *_ = _hai_kenh(csdl_kiem_thu)
    nv = nguoi_thu("cong_viec.doc", "cong_viec.sua", id=an, ten="an")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        assert khach.get("/api/cong-viec/goi-y-don", params={"q": "DH"}).status_code == 403


def test_goi_y_don_chi_trong_kenh_minh_va_theo_khach(csdl_kiem_thu):
    an, hoa_cid, hoa_kh, _lan = _hai_kenh(csdl_kiem_thu)
    nv = nguoi_thu("don.doc", "cong_viec.doc", "cong_viec.sua", id=an, ten="an")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        ma = lambda **q: sorted(d["ma_don"] for d in  # noqa: E731
                                khach.get("/api/cong-viec/goi-y-don", params=q).json()["don"])
        assert ma(q="DH") == ["DH-A1", "DH-A2"], "đơn kênh B lọt qua ô gợi ý"
        assert ma(q="DH", contact_id=hoa_kh) == ["DH-A1"]
        assert ma(conversation_id=hoa_cid) == ["DH-A1"], "có hội thoại thì chỉ đơn của khách ấy"
        # Tra bằng SĐT (≥6 số, bỏ khoảng trắng) — nhưng không trả SĐT về.
        r = khach.get("/api/cong-viec/goi-y-don", params={"q": "912345"}).json()["don"]
        assert [d["ma_don"] for d in r] == ["DH-A1"] and "khach_sdt" not in r[0]
    qt = nguoi_thu("don.doc", "hoi_thoai.xem_tat_ca", id=SEP_ID, ten="sep")
    with TestClient(_app(csdl_kiem_thu, qt)) as khach:
        ds = khach.get("/api/cong-viec/goi-y-don", params={"q": "DH-B"}).json()["don"]
        assert [d["ma_don"] for d in ds] == ["DH-B1"]


def test_tao_viec_bang_ma_don_kenh_khac_bi_chan_nhu_don_khong_ton_tai(csdl_kiem_thu):
    an, *_ = _hai_kenh(csdl_kiem_thu)
    nv = nguoi_thu("don.doc", "cong_viec.doc", "cong_viec.sua", id=an, ten="an")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.post("/api/cong-viec", json={"tieu_de": "Gọi khách B", "ma_don": "DH-B1"})
        assert r.status_code == 422 and "Không tìm thấy đơn DH-B1" in r.text
        ok = khach.post("/api/cong-viec", json={"tieu_de": "Gọi chị Hoa", "ma_don": "DH-A1"})
        assert ok.status_code == 201, ok.text


# ------------------------------------------------------------------ ngữ cảnh tạo việc

def test_ngu_canh_tao_trich_tin_khach_va_viec_dang_mo(csdl_kiem_thu):
    an, hoa_cid, hoa_kh, lan_cid = _hai_kenh(csdl_kiem_thu)

    async def tin(conn):
        for i, (vai, chu) in enumerate([("customer", "Shop ơi"), ("agent", "Dạ em chào chị"),
                                        ("customer", "Cho chị đổi đơn sang tuýp 50ml"),
                                        ("staff", "Em kiểm tra nhé")]):
            await conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) "
                "VALUES ($1,$2,$3, now() - make_interval(mins => $4))",
                UUID(hoa_cid), vai, chu, 10 - i)
    _chay(csdl_kiem_thu, tin)

    nv = nguoi_thu("cong_viec.doc", "cong_viec.sua", id=an, ten="an")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        vid = khach.post("/api/cong-viec", json={"tieu_de": "Đổi đơn chị Hoa",
                                                  "conversation_id": hoa_cid}).json()["id"]
        d = khach.get("/api/cong-viec/ngu-canh-tao", params={"conversation_id": hoa_cid}).json()
        assert d["khach"] == {"id": hoa_kh, "ten": "Chị Hoa"}
        assert "Cho chị đổi đơn sang tuýp 50ml" in d["mo_ta_goi_y"]
        assert "Shop ơi" in d["mo_ta_goi_y"]
        assert "Dạ em chào chị" not in d["mo_ta_goi_y"] and "Em kiểm tra" not in d["mo_ta_goi_y"]
        assert [v["id"] for v in d["viec_mo"]] == [vid], "phải nói hội thoại đã có việc đang mở"
        assert d["don_gan_day"] is None, "không có don.doc thì không trả đơn"
    co_don = nguoi_thu("cong_viec.doc", "cong_viec.sua", "don.doc", id=an, ten="an")
    with TestClient(_app(csdl_kiem_thu, co_don)) as khach:
        d = khach.get("/api/cong-viec/ngu-canh-tao", params={"conversation_id": hoa_cid}).json()
        assert [x["ma_don"] for x in d["don_gan_day"]] == ["DH-A1"]


def test_ngu_canh_tao_kenh_khac_la_404(csdl_kiem_thu):
    _an, hoa_cid, *_ = _hai_kenh(csdl_kiem_thu)
    (binh,) = _dung(csdl_kiem_thu, ("binh", {}))
    nv = nguoi_thu("cong_viec.doc", "cong_viec.sua", id=binh, ten="binh")
    with TestClient(_app(csdl_kiem_thu, nv)) as khach:
        r = khach.get("/api/cong-viec/ngu-canh-tao", params={"conversation_id": hoa_cid})
        assert r.status_code == 404
    chi_doc = nguoi_thu("cong_viec.doc", id=binh, ten="binh")
    with TestClient(_app(csdl_kiem_thu, chi_doc)) as khach:
        r = khach.get("/api/cong-viec/ngu-canh-tao", params={"conversation_id": hoa_cid})
        assert r.status_code == 403, "không tạo được việc thì không cần ngữ cảnh tạo việc"


# ------------------------------------------------------------------ người nhận: ca + tải

def test_nguoi_nhan_duoc_noi_ca_nghi_va_tai_that(csdl_kiem_thu):
    an, chi, dung = _dung(csdl_kiem_thu, ("an", {}), ("chi", {"ca": False}), ("dung", {}))

    async def nghi(conn):
        await conn.execute(
            "INSERT INTO ca_nghi (nguoi_dung_id, tu_luc, den_luc, ly_do) "
            "VALUES ($1, now() - interval '1 hour', now() + interval '1 day', 'phép năm')", UUID(dung))
    _chay(csdl_kiem_thu, nghi)
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        for i in range(2):
            khach.post("/api/cong-viec", json={"tieu_de": f"Việc an {i}", "nguoi_nhan": an})
        ds = {n["id"]: n for n in khach.get("/api/cong-viec/nguoi-nhan-duoc").json()["nguoi"]}
    assert ds[an]["trong_ca_that"] is True and ds[an]["so_mo"] == 2
    # Không lịch ca: `dang_trong_ca` nói true cho mọi giờ (0034) — không được
    # hiện thành "đang trong ca".
    assert ds[chi]["co_lich"] is False and ds[chi]["trong_ca_that"] is False
    assert ds[chi]["so_mo"] == 0
    # Lịch nghỉ thật (ca_nghi) → "đang nghỉ", không phải "ngoài ca".
    assert ds[dung]["dang_nghi"] is True and ds[dung]["trong_ca_that"] is False
    assert ds[an]["dang_nghi"] is False


# ------------------------------------------------------------------ chuông: cần xử lý

def test_chuong_can_xu_ly_theo_tinh_trang_that(csdl_kiem_thu):
    (an,) = _dung(csdl_kiem_thu, ("an", {}))
    with TestClient(_app(csdl_kiem_thu, _sep())) as khach:
        mo = khach.post("/api/cong-viec", json={"tieu_de": "Việc còn mở", "nguoi_nhan": an}).json()["id"]
        xong = khach.post("/api/cong-viec", json={"tieu_de": "Việc đã xong", "nguoi_nhan": an}).json()["id"]
        huy = khach.post("/api/cong-viec", json={"tieu_de": "Việc bị hủy", "nguoi_nhan": an}).json()["id"]
        assert khach.put(f"/api/cong-viec/{xong}", json={"trang_thai": "xong", "ket_qua": "ok"}).status_code == 200
        assert khach.put(f"/api/cong-viec/{huy}", json={"trang_thai": "huy", "ghi_chu": "trùng"}).status_code == 200

    from agent.api.thong_bao_noi_bo import router as tb_router
    from agent.api.phu_thuoc import bat_buoc_dang_nhap

    app = _app(csdl_kiem_thu, nguoi_thu(id=an, ten="an"))
    app.include_router(tb_router)
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: {"id": an, "quyen": frozenset()}
    with TestClient(app) as khach:
        d = khach.get("/api/toi/thong-bao").json()
        nhom = {(t["loai"], t["lien_ket"]["id"]): t["nhom"] for t in d["thong_bao"]}
        assert nhom[("duoc_giao_viec", mo)] == "can_xu_ly"
        assert nhom[("duoc_giao_viec", xong)] == "da_xu_ly", "việc đã xong vẫn bị coi là cần làm"
        assert nhom[("duoc_giao_viec", huy)] == "da_xu_ly"
        assert nhom[("viec_huy", huy)] == "thong_tin"
        assert d["can_xu_ly"] == 1

        can = khach.get("/api/toi/thong-bao", params={"can_xu_ly": "true"}).json()
        assert [(t["loai"], t["lien_ket"]["id"]) for t in can["thong_bao"]] == [("duoc_giao_viec", mo)]
        # Đọc KHÔNG làm xong việc: đã đọc vẫn nằm trong "Cần xử lý".
        tid = can["thong_bao"][0]["id"]
        assert khach.post(f"/api/toi/thong-bao/{tid}/da-doc").status_code == 200
        assert khach.get("/api/toi/thong-bao", params={"can_xu_ly": "true"}).json()["can_xu_ly"] == 1


@pytest.mark.parametrize("tep", ["25-cong-viec.js", "25b-cong-viec-chi-tiet.js",
                                 "25c-cong-viec-tao.js", "19-thong-bao.js"])
def test_tep_giao_dien_khong_qua_1000_dong(tep):
    assert len((SRC / tep).read_text(encoding="utf-8").splitlines()) <= 1000
