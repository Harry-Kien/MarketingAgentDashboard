"""
Tab Kết nối & Tích hợp bố cục lại (UX-08-01…09, UX-20-01…06, MD-UX-20-01/02).

Canh những chỗ mà lần dọn dẹp sau dễ gỡ mất:
- MỘT trạng thái cho mỗi tài khoản, suy từ sức khoẻ thật — không còn
  "Sẵn sàng" xanh cạnh chấm đỏ "lỗi kết nối" (UX-20-01).
- Mã kỹ thuật dịch thành chuyện gì / vì sao / làm gì; mã vẫn còn để tra
  (UX-20-05).
- Thao tác chia nhóm theo mục đích; thao tác nguy hiểm HỎI TRƯỚC qua hộp
  thoại chung và nói hậu quả (UX-08-05, UX-20-06).
- Kênh khách hàng tách khỏi hệ thống ngoài; mỗi dịch vụ một bảng gập
  (UX-08-01, UX-08-04, MD-UX-20-01).
- Khả năng nền tảng ghi rõ KHÔNG phải trạng thái (MD-UX-20-02).
- Dòng thời gian một tài khoản cần quyền VÀ phạm vi kênh (UX-08-09).

Không cần Postgres; phần CSDL thật ở test_ket_noi_hop_nhat_pg.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agent.api import ket_noi_tich_hop as api_kn
from agent.api.channel_accounts import _raise_public, get_account_repository
from agent.api.routes import nguoi_da_dang_nhap
from agent.omnichannel import giai_thich_loi_kenh as gtl
from agent.omnichannel import suc_khoe_kenh as skk
from agent.omnichannel.account_service import AccountAlreadyExists
from agent.omnichannel.accounts import AccountStatus
from conftest import nguoi_thu

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "src"
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def _src(ten: str) -> str:
    return (SRC / ten).read_text(encoding="utf-8")


# ------------------------------------------------------------------ một trạng thái

@pytest.mark.parametrize("status,muc,hanh_dong,ky_vong", [
    ("active", skk.XANH, "", skk.HOAT_DONG),
    ("active", skk.VANG, "nhan_thu", skk.HOAT_DONG),          # cảnh báo, vẫn chạy
    ("active", skk.DO, "dang_nhap_meta", skk.CAN_XAC_THUC),   # quyền Meta đã hết
    ("active", skk.DO, "", skk.LOI),
    ("pending", skk.VANG, "nhan_tin", skk.CHUA_KET_NOI),
    ("pending", skk.DO, "quet_qr", skk.CHUA_KET_NOI),
    ("degraded", skk.DO, "xac_minh", skk.LOI),
    ("reauth_required", skk.DO, "quet_qr", skk.CAN_XAC_THUC),
    ("disabled", skk.TAT, "bat_lai", skk.TAM_NGAT),
    ("trang_thai_la", skk.XANH, "", skk.LOI),                 # lạ -> đỏ, không xanh giả
])
def test_trang_thai_hop_nhat(status, muc, hanh_dong, ky_vong):
    assert skk.trang_thai_ket_noi(status=status, muc=muc, hanh_dong=hanh_dong) == ky_vong


def test_zalo_mat_ket_noi_khong_bao_gio_hien_hoat_dong():
    """Ví dụ gốc của UX-20-01: Zalo hiện "sẵn sàng" trong khi sức khoẻ ghi lỗi."""
    for st in ("degraded", "pending", "reauth_required"):
        d = skk.danh_gia(channel="zalo_personal", status=st, ly_do_hong="sidecar không phản hồi")
        tt = skk.trang_thai_ket_noi(status=st, muc=d.muc, hanh_dong=d.hanh_dong)
        assert tt != skk.HOAT_DONG, st


def test_nam_trang_thai_du_nhan_tieng_viet():
    assert list(skk.NHAN_TRANG_THAI_KET_NOI.values()) == [
        "Chưa kết nối", "Hoạt động", "Tạm ngắt", "Cần xác thực lại", "Lỗi"]


# ------------------------------------------------------------------ giải thích mã

def test_moi_trang_thai_tai_khoan_deu_co_loi_giai_thich():
    """Thêm một AccountStatus mới mà quên dịch là người dùng lại thấy mã thô."""
    for st in AccountStatus:
        if st.value == "active":
            continue
        g = gtl.tra(st.value)
        assert g is not None, st.value
        assert g.tieu_de and g.nguyen_nhan and g.cach_sua


@pytest.mark.parametrize("ma", [
    "reauth_required", "degraded", "disconnected", "AccountAlreadyExists",
    "provider.unreachable", "provider.unauthorized", "zalo_personal.can_quet_lai",
    "meta.token_chet",
])
def test_ma_backlog_neu_ten_duoc_dich(ma):
    g = gtl.giai_thich(ma, ly_do="lý do gốc")
    assert g and g["ma"] == ma and g["ly_do_goc"] == "lý do gốc"
    # Lời người đọc không lặp lại chính cái mã.
    for k in ("tieu_de", "nguyen_nhan", "cach_sua"):
        assert ma not in g[k] and g[k].strip()


def test_ma_la_van_noi_duoc_theo_ho():
    assert "nền tảng" in gtl.tra("provider.ma_moi_chua_co").tieu_de
    assert "Zalo" in gtl.tra("zalo_personal.gi_do").tieu_de
    assert gtl.tra("") is None and gtl.tra(None) is None
    assert gtl.tra("hoan_toan_la") is None


def test_cach_sua_rieng_theo_kenh():
    zalo = gtl.tra("provider.unreachable", kenh="zalo_personal").cach_sua
    chung = gtl.tra("provider.unreachable", kenh="webchat").cach_sua
    assert "sidecar" in zalo and zalo != chung
    assert "Facebook" in gtl.tra("reauth_required", kenh="instagram").cach_sua


def test_loi_409_kem_cach_sua():
    with pytest.raises(HTTPException) as e:
        _raise_public(AccountAlreadyExists("tài khoản kênh này đã tồn tại"))
    assert e.value.status_code == 409
    assert e.value.detail.startswith("tài khoản kênh này đã tồn tại — ")
    assert "Kiểm tra kết nối" in e.value.detail


# ------------------------------------------------------------------ dòng thời gian: quyền

class _KhoGia:
    def __init__(self, *tk):
        self.tk = tk

    async def list_for_user(self, user_id, *, is_admin):
        return list(self.tk)


def _app(*quyen, kho=None):
    app = FastAPI()
    app.include_router(api_kn.router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi_thu(*quyen, ten="nv", id=uuid4())
    app.dependency_overrides[get_account_repository] = lambda: kho or _KhoGia()
    return TestClient(app)


def test_dong_thoi_gian_can_quyen_doc_kenh():
    assert _app("cau_hinh.sua").get(f"/api/ket-noi/kenh/{uuid4()}/dong-thoi-gian").status_code == 403


def test_dong_thoi_gian_ngoai_pham_vi_kenh_la_404():
    """Đoán UUID của kênh không được giao thì không đọc được lịch sử của nó."""
    r = _app("kenh.doc").get(f"/api/ket-noi/kenh/{uuid4()}/dong-thoi-gian")
    assert r.status_code == 404


def test_dong_thoi_gian_an_so_cau_hinh_khi_thieu_quyen(monkeypatch):
    from types import SimpleNamespace

    from agent import ket_noi_tich_hop as kn
    from agent.omnichannel.accounts import Channel

    tk = SimpleNamespace(id=uuid4(), display_name="Zalo shop", channel=Channel.ZALO_PERSONAL)
    goi: dict = {}

    async def dtg(account_id, **kw):
        goi.update(kw)
        return []

    monkeypatch.setattr(kn, "dong_thoi_gian", dtg)
    d = _app("kenh.doc", kho=_KhoGia(tk)).get(f"/api/ket-noi/kenh/{tk.id}/dong-thoi-gian").json()
    assert goi["xem_cau_hinh"] is False and "cau_hinh" not in d["loai"]
    d = _app("kenh.doc", "cau_hinh.sua", kho=_KhoGia(tk)).get(
        f"/api/ket-noi/kenh/{tk.id}/dong-thoi-gian?loai=suc_khoe").json()
    assert goi["xem_cau_hinh"] is True and goi["loai"] == {"suc_khoe"}
    r = _app("kenh.doc", kho=_KhoGia(tk)).get(f"/api/ket-noi/kenh/{tk.id}/dong-thoi-gian?loai=bia")
    assert r.status_code == 422


# ------------------------------------------------------------------ giao diện: bố cục

def test_ba_khu_vuc_tach_kenh_khach_khoi_he_thong_ngoai():
    t = HTML[HTML.index('<section class="tabpanel" id="cc-ket-noi"'):HTML.index('id="cc-sla"')]
    for phan in ("kenh", "tich-hop", "lich-su"):
        assert f'data-kn-phan-nut="{phan}"' in t and f'data-kn-thuoc="{phan}"' in t
    assert "Kênh giao tiếp khách hàng" in t and "Tích hợp hệ thống ngoài" in t
    kenh = t[t.index('data-kn-thuoc="kenh"'):t.index('data-kn-thuoc="tich-hop"')]
    # Kênh khách KHÔNG lẫn ô của ERP/vận chuyển; lịch sử không nằm cuối trang kênh.
    for o in ('id="connectiongrid"', 'id="kn-suckhoe"', 'id="kn-dieukien"'):
        assert o in kenh
    assert "erp" not in kenh.lower() and 'id="kn-ls-o"' not in kenh
    assert 'id="kn-ls-o"' in t and 'id="kn-dtg-o"' in t
    # Mô-đun gắn vào tự chuyển vào khu vực tích hợp, không nằm lửng cuối tab.
    assert '$("#kn-phan-tich-hop")' in _src("22-ket-noi-tich-hop.js")


def test_mot_dich_vu_mot_bang_gap():
    src = _src("22-ket-noi-tich-hop.js")
    the = src[src.index("function knttTheDichVu"):src.index("function knttKenhCu")]
    assert 'aria-expanded="${mo ? "true" : "false"}"' in the
    assert '${mo ? "" : " hidden"}' in the, "bảng đóng sẵn, chỉ mở khi chọn"
    assert "knttDvMo = knttDvMo === ma ? null : ma" in src, "mở một bảng thì bảng khác đóng"
    # Webhook là chi tiết kỹ thuật -> nằm trong phần nâng cao.
    assert the.index("Chi tiết nâng cao") < the.index("wh.xac_minh")


def test_tai_khoan_khong_con_ve_o_ba_noi():
    """Plugin kênh không còn vẽ dòng tài khoản riêng (UX-08-02)."""
    src = _src("22-ket-noi-tich-hop.js")
    assert "function knttTaiKhoan" not in src and "knttPlugin" not in src
    assert "state.knttTk" in src and "state.knttTk" in _src("18a-ket-noi-tai-khoan.js")


def test_kha_nang_tach_khoi_trang_thai():
    src = _src("18a-ket-noi-tai-khoan.js")
    ham = src[src.index("function knKhaNang"):src.index("function knNangCaoKenh")]
    assert "Khả năng được nền tảng hỗ trợ" in ham
    assert "KHÔNG phải trạng thái tài khoản" in ham
    assert "<details" in ham, "dải khả năng phải gập được, không chiếm chỗ"


# ------------------------------------------------------------------ giao diện: chạy thật bằng node

def _node(ma: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("máy không có node")
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


_NEN = r"""
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const state = { knMo: {} };
const document = { addEventListener() {}, querySelector() { return null; } };
const $ = () => null, $$ = () => [];
const hoSoAgent = { ds: [] };
const CHANNEL_LABEL = { zalo_personal: "Zalo cá nhân", facebook: "Facebook", webchat: "Web chat",
  zalo_oa: "Zalo OA", instagram: "Instagram", whatsapp: "WhatsApp" };
const KN_NUT = { quet_qr: "Quét QR", xac_minh: "Xác minh lại", bat_lai: "Bật lại" };
function srcBadge(ch) { return `<span class="src">${ch}</span>`; }
function goc_cong_khai() { return "https://vd.test"; }
function knttLuc(x) { return String(x); }
function knttThongKe() { return ""; }
class HTMLDetailsElement {}
"""


def _ham(src: str, ten: str) -> str:
    i = src.index(f"function {ten}(")
    j = src.index("\n}\n", i) + 3
    return src[i:j]


def _ma_18a() -> str:
    src = _src("18a-ket-noi-tai-khoan.js")
    hang = "\n".join(src[src.index(f"const {t} ="):src.index(";\n", src.index(f"const {t} =")) + 2]
                     for t in ("KENH_META", "ACCOUNT_STATUS_LABEL", "KN_TT_TAM", "GOI_Y_LOI",
                               "KN_NOI_THEO_KENH", "KN_GOI_Y_NOI"))
    ham = "\n".join(_ham(src, t) for t in (
        "callbackTheoKenh", "connectionCallback", "knMo", "knTrangThai", "knPillTT", "knViecDeDoc",
        "knLoiDeDoc",
        "knNhomNut", "knNangCaoTaiKhoan", "knDongTaiKhoan", "knKenhChuaNoi", "lyDoKetNoi"))
    return _NEN + hang + "\n" + ham


def test_dong_tai_khoan_mot_trang_thai_va_nhom_nut():
    ma = _ma_18a() + r"""
    const tk = { id: "a1", channel: "zalo_personal", display_name: "Zalo Lan", status: "active",
                 external_account_id: "84901", agent_bat: true };
    state.knSucKhoe = { a1: { trang_thai: "loi", nhan_trang_thai: "Lỗi", canh_bao: false,
      viec: "Sidecar không phản hồi", hanh_dong: "quet_qr",
      giai_thich: { ma: "provider.unreachable", tieu_de: "Không liên lạc được với nền tảng",
        nguyen_nhan: "Sidecar chưa chạy.", cach_sua: "Bật sidecar.", ly_do_goc: "ECONNREFUSED" } } };
    const loi = knDongTaiKhoan(tk);
    state.knSucKhoe = {};
    const tam = knDongTaiKhoan({ ...tk, status: "disabled" });
    console.log(JSON.stringify({ loi, tam }));
    """
    d = _node(ma)
    loi, tam = d["loi"], d["tam"]
    # MỘT nhãn trạng thái; nhãn status thô "Sẵn sàng" không còn ở dòng chính.
    chinh = loi[:loi.index("knh-quanly")]
    assert chinh.count('class="knh-tt knh-tt--') == 1 and "Lỗi" in chinh
    assert "Sẵn sàng" not in chinh
    # Lời giải thích ở dòng chính, mã thô chỉ trong Chi tiết nâng cao.
    assert "Không liên lạc được với nền tảng" in chinh and "Bật sidecar." in chinh
    assert "provider.unreachable" not in chinh and "ECONNREFUSED" not in chinh
    nang_cao = loi[loi.index("Chi tiết nâng cao"):]
    assert "provider.unreachable" in nang_cao and "ECONNREFUSED" in nang_cao
    # Bốn nhóm theo mục đích; Xoá chỉ nằm trong nhóm nguy hiểm.
    for nhom in ("Kết nối", "Kiểm tra", "Điều khiển AI", "Quản lý tài khoản"):
        assert f'<span class="knh-nhom__ten">{nhom}</span>' in loi
    nguy = loi[loi.index("knh-nhom--nguy"):]
    assert "data-xoa-tk=" in nguy and "data-disable=" in nguy
    assert "data-xoa-tk=" not in loi[:loi.index("knh-nhom--nguy")]
    assert 'data-kn-lam="quet_qr"' in chinh, "nút chính theo sức khoẻ nằm ngay trên dòng"
    # Fallback khi sức khoẻ chưa về: vẫn MỘT nhãn, tạm ngắt có nút Bật lại.
    assert "Tạm ngắt" in tam and 'data-kn-lam="bat_lai"' in tam and "data-disable=" not in tam


def test_kenh_chua_noi_gon_mot_dong_kem_nut():
    ma = _ma_18a() + r"""
    state.knDangNhap = { meta: false, zalo_oa: true };
    console.log(JSON.stringify(knKenhChuaNoi(["facebook", "zalo_oa"])));
    """
    h = _node(ma)
    assert h.count("<li>") == 2 and h.count('data-kn-noi-nhanh="') == 2
    assert 'data-kn-noi-nhanh="meta" disabled' in h and "Chưa khai ứng dụng Meta" in h
    assert "channel-card" not in h, "kênh trống không chiếm một thẻ to"


def test_ly_do_ket_noi_noi_loi_truoc_ma_sau():
    ma = _ma_18a() + r"""
    console.log(JSON.stringify([
      lyDoKetNoi({ code: "provider.unauthorized", detail: { ly_do: "Invalid secret key" } }),
      lyDoKetNoi({}),
    ]));
    """
    a, b = _node(ma)
    assert a.startswith("Nền tảng từ chối") and a.endswith("(mã: provider.unauthorized)")
    assert "Invalid secret key" in a and b


def test_ly_do_ket_noi_o_cap_tep_khong_long():
    """Hàm lồng trong loadKetNoi gọi từ form thêm kênh là ReferenceError."""
    src = _src("18a-ket-noi-tai-khoan.js")
    assert re.search(r"^function lyDoKetNoi\(", src, re.M)
    assert "function lyDoKetNoi" not in _ham(src, "loadKetNoi")


# ------------------------------------------------------------------ thao tác nguy hiểm hỏi trước

def _khoi(src: str, dau: str, dai: int = 1600) -> str:
    i = src.index(dau)
    return src[i:i + dai]


@pytest.mark.parametrize("dau,goi", [
    ("$$('[data-disable]')", "/disable"),
    ('$$("[data-xoa-tk]")', 'method: "DELETE"'),
    ("$$('[data-agentbat]')", "/agent"),
    ("$$('[data-qr]')", "quetQR("),
])
def test_thao_tac_nguy_hiem_hoi_qua_hop_thoai_truoc_khi_goi(dau, goi):
    k = _khoi(_src("18a-ket-noi-tai-khoan.js"), dau, 2600)
    assert "hoiHop(" in k and k.index("hoiHop(") < k.index(goi), dau


def test_hop_thoai_noi_hau_qua():
    src = _src("18a-ket-noi-tai-khoan.js")
    ngat = _khoi(src, "$$('[data-disable]')")
    assert "KHÔNG vào hệ thống" in ngat and "nguy_hiem: true" in ngat
    xoa = _khoi(src, '$$("[data-xoa-tk]")', 2400)
    assert "KHÔNG khôi phục được" in xoa and "nguy_hiem: true" in xoa


def test_khu_ket_noi_khong_con_confirm_cua_trinh_duyet():
    for ten in ("18-ket-noi-kenh.js", "18a-ket-noi-tai-khoan.js", "22-ket-noi-tich-hop.js",
                "22b-ket-noi-lich-su.js"):
        ma = re.sub(r"/\*.*?\*/", "", _src(ten), flags=re.S)
        assert not re.search(r"(?<![\w.])confirm\(", ma), ten


def test_khong_dung_lai_luoi_khi_khong_doi():
    """Dựng lại mỗi 6 giây là đóng ô chọn đang mở và đóng `<details>` vừa mở."""
    than = _ham(_src("18a-ket-noi-tai-khoan.js"), "loadKetNoi")
    assert "if (luoi._knHtml === html) return;" in than
    assert than.index("luoi._knHtml === html") < than.index("$$('[data-verify]')")
    assert 'document.addEventListener("toggle"' in _src("18a-ket-noi-tai-khoan.js")


# ------------------------------------------------------------------ lịch sử

def test_lich_su_loc_o_may_chu():
    src = _src("22b-ket-noi-lich-su.js")
    assert "/ket-noi/lich-su?" in src and 'q.set("dich_vu"' in src and 'q.set("tu"' in src
    assert "/dong-thoi-gian?" in src and 'q.set("loai"' in src
    import inspect

    from agent import ket_noi_tich_hop as kn
    nguon = inspect.getsource(kn.doc_lich_su)
    assert "sua_luc >= ${}" in nguon and "account_id = ${}" in nguon


def test_dong_thoi_gian_chi_lay_lan_doi_trang_thai():
    import inspect

    from agent import ket_noi_tich_hop as kn
    nguon = inspect.getsource(kn.dong_thoi_gian)
    assert "IS DISTINCT FROM status" in nguon, "nhịp tim sidecar sẽ chôn dòng mất kết nối"
