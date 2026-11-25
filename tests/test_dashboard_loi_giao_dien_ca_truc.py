"""
Mười một lỗi giao diện tìm ra trong một lượt rà dashboard (16.11.2026).

Điểm chung: KHÔNG lỗi nào nổ. Mỗi cái là một thao tác trông như đã xong —
đăng nhập "phiên hết hạn", "Đã lưu 0 khoá" màu xanh, "xác minh xong" cho
credential sai, số chưa đọc không bao giờ giảm, ô chọn nhảy về đầu rồi
thêm nhầm người vào nhầm đội. Đúng loại hỏng im lặng CLAUDE.md xếp nguy
hiểm nhất.

Chỗ nào logic đủ tự chứa thì CHẠY THẬT bằng node (api(), ganLuaChon,
danhDauDaDoc) — đọc mã bằng regex dễ xanh giả với mã đã bị tắt. Chỗ còn
lại soi nguồn đã GỠ chú thích, cùng cách với test_man_khach_giu_chu_dang_go.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
DONG = JS.splitlines()


def _bo_chu_thich(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", " ", src)


def _than_ham(ten: str, giu_chu_thich: bool = False) -> str:
    """Thân một hàm khai ở cột 0, tới hàm cột-0 kế tiếp."""
    bien = [
        (i, m.group(1))
        for i, l in enumerate(DONG)
        if (m := re.match(r"(?:async )?function ([A-Za-z0-9_]+)\(", l))
    ]
    for k, (i, t) in enumerate(bien):
        if t == ten:
            het = bien[k + 1][0] if k + 1 < len(bien) else len(DONG)
            than = "\n".join(DONG[i:het])
            return than if giu_chu_thich else _bo_chu_thich(than)
    raise AssertionError(f"không thấy hàm {ten}()")


def _ham_chay_duoc(ten: str) -> str:
    """Đúng thân hàm (tới `}` ở cột 0) để nạp vào node."""
    m = re.search(r"(?m)^(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


def _doan(dau: str, do_dai: int = 3000) -> str:
    i = JS.index(dau)
    return _bo_chu_thich(JS[i:i + do_dai])


def _khoi_handler(dau: str) -> str:
    """
    Một khối gắn sự kiện, cắt tới câu lệnh cấp-cùng kế tiếp.

    Cắt theo độ dài cố định là lấy lẫn cả khối sau — khối sau có try/catch
    thì khối này xanh nhờ hàng xóm.
    """
    i = JS.index(dau)
    sau = JS[i + len(dau):]
    m = re.search(r"\n(?:  )?(?:\$\$?\(|const |async function |function |\})(?!\))", sau)
    het = m.start() if m else len(sau)
    # Khối nào cũng dài hơn vài dòng; cắt quá ngắn là regex trượt.
    return _bo_chu_thich(JS[i:i + len(dau) + het])


def _node(ma: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node trên PATH")
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- 1. 2FA

def test_401_cua_dang_nhap_khong_bi_coi_la_het_phien():
    """
    `/dang-nhap` trả 401 cho cả "cần mã 2FA", "mã sai" và "sai mật khẩu".
    Trước đây api() biến MỌI 401 thành "phiên hết hạn" trước khi đọc nội
    dung: ô mã 2FA không bao giờ hiện — ai bật 2FA là tự khoá mình ra.

    Chạy THẬT hàm api() trong node với fetch giả.
    """
    ma = """
const state = { timer: null, stream: null };
const $ = () => null;
let traVe;
globalThis.fetch = async () => traVe;
""" + _ham_chay_duoc("api") + """
const loi401 = (than) => ({ status: 401, ok: false, statusText: "Unauthorized",
                            json: async () => than });
(async () => {
  const kq = {};
  traVe = loi401({ detail: { can_ma_2fa: true, detail: "Nhập mã 6 số trong ứng dụng xác thực." } });
  try { await api("/dang-nhap", { method: "POST" }); }
  catch (e) { kq.can_ma = { msg: e.message, co: !!(e.chi_tiet && e.chi_tiet.can_ma_2fa), ma: e.ma }; }
  traVe = loi401({ detail: "Tên đăng nhập hoặc mật khẩu không đúng" });
  try { await api("/dang-nhap", { method: "POST" }); }
  catch (e) { kq.sai_mk = e.message; }
  traVe = loi401({ detail: "Chưa đăng nhập" });
  try { await api("/overview"); }
  catch (e) { kq.het_phien = e.message; }
  console.log(JSON.stringify(kq));
})();
"""
    kq = _node(ma)
    assert kq["can_ma"]["co"] is True, "ô mã 2FA sẽ không bao giờ hiện"
    assert kq["can_ma"]["ma"] == 401
    assert "hết hạn" not in kq["can_ma"]["msg"]
    assert kq["sai_mk"] == "Tên đăng nhập hoặc mật khẩu không đúng", (
        "sai mật khẩu phải báo sai mật khẩu, không phải 'phiên hết hạn'")
    # Nhánh hết phiên vẫn phải còn cho MỌI route khác.
    assert "hết hạn" in kq["het_phien"]


def test_form_dang_nhap_hien_o_ma_khi_can_2fa():
    than = _doan('$("#loginform").addEventListener("submit"', 1500)
    assert "err.chi_tiet.can_ma_2fa" in than
    assert '$("#loginMa").hidden = false' in than
    assert 'id="loginMa"' in HTML and 'name="ma_2fa"' in HTML


# --------------------------------------------- 2. vòng 6 giây xoá ô nhập

def test_gan_lua_chon_giu_gia_tri_dang_chon():
    """Chạy thật ganLuaChon với một <select> giả."""
    ma = """
class Sel {
  constructor() { this._h = ""; this.options = []; this._v = ""; }
  set innerHTML(h) {
    this._h = h;
    this.options = [...h.matchAll(/<option value="([^"]*)"/g)].map((m) => ({ value: m[1] }));
    this._v = this.options.length ? this.options[0].value : "";
  }
  get innerHTML() { return this._h; }
  get value() { return this._v; }
  set value(v) { if (this.options.some((o) => o.value === v)) this._v = v; }
}
const op = (...ds) => ds.map((d) => `<option value="${d}">${d}</option>`).join("");
""" + _ham_chay_duoc("ganLuaChon") + """
const s = new Sel();
const kq = {};
ganLuaChon(s, op("a", "b", "c"));
s.value = "b";
ganLuaChon(s, op("a", "b", "c"));    kq.khong_doi = s.value;
ganLuaChon(s, op("x", "a", "b"));    kq.doi_van_con = s.value;
ganLuaChon(s, op("x", "y"));         kq.da_mat = s.value;
ganLuaChon(null, op("x"));           // không nổ khi ô không có trên màn
console.log(JSON.stringify(kq));
"""
    kq = _node(ma)
    assert kq == {"khong_doi": "b", "doi_van_con": "b", "da_mat": "x"}


@pytest.mark.parametrize("ham, o", [
    ("loadDinhTuyen", ["#dtChonDoi", "#dtLuatDoi", "#dtChonNguoi", "#dtChonKenh", "#dtSlaKenh"]),
    ("gopDoO", ["#gopDich"]),
])
def test_o_chon_dinh_ky_khong_gan_innerhtml_tran(ham, o):
    than = _than_ham(ham)
    for sel in o:
        assert f'$("{sel}").innerHTML' not in than, (
            f"{ham} gán trần {sel}.innerHTML — chạy lại mỗi 6 giây là ô chọn "
            "nhảy về đầu, bấm Thêm là thêm NHẦM. Dùng ganLuaChon().")
    assert "ganLuaChon(" in than


@pytest.mark.parametrize("ham, goc", [
    ("loadCaiDatApi", "oGoc.innerHTML ="),
    ("loadCauHinh", "oGoc.innerHTML ="),
])
def test_khoi_cau_hinh_giu_chu_dang_go(ham, goc):
    """
    Ô nhập của hai khối này dựng trong HÀM PHỤ (oNhapApi, oNhapCauHinh),
    nên bộ canh chung ở test_man_khach_giu_chu_dang_go — tìm `<input` ngay
    trong thân hàm — không thấy chúng. Canh riêng, kèm thứ tự.
    """
    than = _than_ham(ham)
    luu, ve, tra = than.find("_luuDangGo("), than.find(goc), than.find("_traDangGo(")
    assert -1 not in (luu, ve, tra), f"{ham} phải lưu -> vẽ -> trả chữ đang gõ"
    assert luu < ve < tra


def test_tra_chu_truoc_khi_an_o_khoa_theo_provider():
    than = _than_ham("loadCaiDatApi")
    tra = than.find("_traDangGo(")
    assert tra != -1, "loadCaiDatApi không trả chữ đang gõ"
    assert tra < than.find("hienODungProvider()"), (
        "phải trả ô provider người dùng vừa đổi TRƯỚC khi quyết định ô khoá nào hiện")


def test_khoa_o_cau_hinh_khong_trung_nhau():
    """
    Ô cấu hình không nằm trong form và không có name. Không có khoá riêng thì
    mọi ô cùng khoá "khong-form:" — giá trị ô này bị trả vào ô kia.
    """
    than = _than_ham("_khoaO")
    assert "o.dataset.ch" in than and "o.dataset.apiKhoa" in than


def test_luu_cau_hinh_xong_hien_gia_tri_may_chu():
    """Sau khi lưu (kể cả lưu hỏng), thứ hiện phải là thứ máy chủ đang chạy."""
    i = JS.index('const el = e.target.closest("[data-ch]")')
    doan = _bo_chu_thich(JS[i:JS.index("\n});", i)])
    assert doan.count("loadCauHinh(false)") == 2, "cả nhánh lưu được lẫn nhánh lỗi"
    assert re.search(r"if \(dangGo\) _traDangGo", _than_ham("loadCauHinh"))


def test_luu_khoa_api_khong_bao_xanh_khi_khong_co_gi():
    doan = _doan('const luu = e.target.closest("[data-api-luu]")', 3500)
    assert "giaTriApiDangGo(ma, true)" in doan, "Lưu phải chỉ gửi ô đã sửa"
    i_rong = doan.find("Chưa nhập khoá nào")
    assert i_rong != -1, "không có gì để lưu thì phải nói ra"
    assert i_rong < doan.find("Đã lưu ${da_luu.length}"), (
        "câu 'Chưa nhập khoá nào' phải chặn TRƯỚC toast xanh 'Đã lưu N khoá'")
    assert "_oDaSua(o)" in _than_ham("giaTriApiDangGo")


# ------------------------------------------------- 3. số chưa đọc

def test_danh_dau_da_doc_goi_route_va_chi_goi_khi_co_tin_moi():
    ma = """
const state = {};
const $ = () => null;
const document = { visibilityState: "visible" };
const goi = [];
let hong = false;
const canh = [];
console.warn = (...a) => canh.push(a.join(" "));
const api = (p, o) => { goi.push([p, o && o.method]); return hong ? Promise.reject(new Error("x")) : Promise.resolve({ ok: true }); };
""" + _ham_chay_duoc("danhDauDaDoc") + """
const tin = (id, role) => ({ id, role });
(async () => {
  const kq = {};
  danhDauDaDoc("c1", [tin("m1", "customer"), tin("m2", "agent")]);
  danhDauDaDoc("c1", [tin("m1", "customer"), tin("m2", "agent"), tin("m3", "staff")]);
  kq.mo = goi.length;                                   // mở = 1 lần, tin không-phải-khách không gọi lại
  danhDauDaDoc("c1", [tin("m1", "customer"), tin("m4", "customer")]);
  kq.tin_khach_moi = goi.length;                        // khách nhắn thêm = gọi lại
  document.visibilityState = "hidden";
  danhDauDaDoc("c1", [tin("m5", "customer")]);
  kq.tab_an = goi.length;                               // tab nền: chưa ai đọc
  document.visibilityState = "visible";
  hong = true;
  danhDauDaDoc("c1", [tin("m5", "customer")]);
  await new Promise((r) => setTimeout(r, 10));
  kq.canh = canh.length;
  hong = false;
  danhDauDaDoc("c1", [tin("m5", "customer")]);
  kq.thu_lai = goi.length;                              // hỏng thì lần sau thử lại
  kq.duong = goi[0];
  console.log(JSON.stringify(kq));
})();
"""
    kq = _node(ma)
    assert kq["duong"] == ["/inbox/conversations/c1/read", "POST"]
    assert kq["mo"] == 1
    assert kq["tin_khach_moi"] == 2
    assert kq["tab_an"] == 2
    assert kq["canh"] == 1, "hỏng thì phải ghi console, không im lặng"
    assert kq["thu_lai"] == 4


def test_mo_hoi_thoai_thi_danh_dau_da_doc():
    assert "danhDauDaDoc(id, c.messages)" in _than_ham("loadThread")


# ------------------------------------------------- 4. thêm kênh xác minh

def test_them_kenh_doc_ok_cua_verify():
    doan = _doan("const kq = await api(`/channel-accounts/${account.id}/verify`", 600)
    assert "kq && kq.ok" in doan and "lyDoKetNoi(" in doan
    assert "!(kq && kq.ok)" in doan, "ok:false phải là toast LỖI"


# ------------------------------------------------- 5. nút tiếp quản

def test_nut_tiep_quan_theo_nguoi_giu():
    """
    Luật nút theo người giữ giờ là hàm thuần `hanhDongXuLy` (mục 6.5) — bảng
    trạng thái × quyền đầy đủ chạy THẬT bằng node ở
    tests/test_thanh_thong_tin_hoi_thoai.py. Ở đây chỉ canh lỗi cũ: hội
    thoại agent tự chuyển người (mode human, CHƯA ai nhận) phải mời "Tiếp
    quản", không phải "Kết thúc tiếp quản".
    """
    than = _than_ham("loadThread")
    assert "c.assigned_to" in than and "state.toiId" in than
    assert "hanhDongXuLy(c, { toiId: state.toiId, quyen: state.toiQuyen" in than
    # Hai nút tách hẳn: một nút lật theo `taken` là lỗi cũ.
    assert '${taken ? "release" : "takeover"}' not in _bo_chu_thich(JS)
    luat = _than_ham("hanhDongXuLy")
    assert 'co("hoi_thoai.xem_tat_ca")' in luat
    assert re.search(r'if \(c\.mode === "human" && quanLy\) ds\.push\(HANH_DONG_HT\.ketThuc\)', luat)


def test_release_hien_ghi_chu_thanh_loi():
    doan = _doan('else if (ev.target.closest("#btn-release"))', 700)
    assert '_goiHanhDong("release"' in doan
    assert "r.ghi_chu" in doan and "toast(r.ghi_chu, true)" in doan
    tk = _doan('if (ev.target.closest("#btn-take"))', 300)
    assert '_goiHanhDong("takeover"' in tk and "release" not in tk.split("else if")[0]


# ------------------------------------------------- 6. hoàn tác gộp

def test_gop_xong_co_nut_hoan_tac_goi_route_undo():
    assert 'data-merge-undo="${esc(r.merge_id)}"' in JS, (
        "nút hoàn tác phải giữ ĐỦ merge_id, không phải tám ký tự đầu")
    doan = _doan('const nut = e.target.closest("[data-merge-undo]")', 1500)
    assert "hoiHop(" in doan, "hoàn tác phải hỏi xác nhận"
    assert "/contacts/merges/${encodeURIComponent(nut.dataset.mergeUndo)}/undo" in doan
    assert "reason:" in doan
    assert "Hoàn tác được bằng mã" not in _bo_chu_thich(JS)


# ------------------------------------------------- 7. reset form khách

# `#contact-tag-form` (gõ nhãn chữ tự do) đã thay bằng ô chọn từ danh mục nhãn
# (0056, 21-nhan.js) — không còn ô gõ nào để reset.
@pytest.mark.parametrize("form", ["#contact-note-form", "#contact-consent-form"])
def test_form_khach_reset_truoc_khi_nap_lai(form):
    assert f'$("{form}")' in _than_ham("loadContactDetail")
    khoi = _khoi_handler(f'$("{form}")')
    assert "form.reset()" in khoi, f"{form}: không reset là chữ còn trong ô, gửi trùng"
    assert khoi.index("form.reset()") < khoi.index("await loadContactDetail(id)"), (
        "reset phải TRƯỚC khi nạp lại — loadContactDetail giữ mọi ô lệch defaultValue")


# ------------------------------------------------- 8. bắt lỗi + xác nhận

@pytest.mark.parametrize("dau", [
    '$$(\'[data-doc-archive]\')',
])
def test_nut_co_bat_loi(dau):
    doan = _khoi_handler(dau)
    assert "try {" in doan and "toast(e.message, true)" in doan, f"{dau}: lỗi bị nuốt"


@pytest.mark.parametrize("dau", ['$$(\'[data-doc-archive]\')'])
def test_xoa_tai_lieu_phai_hoi(dau):
    doan = _khoi_handler(dau)
    assert "confirm(" in doan and doan.index("confirm(") < doan.index("await api("), f"{dau}: phải hỏi TRƯỚC khi gọi"


# ------------------------------------------------- 11. khổ hẹp

def test_kho_hep_cuon_toi_chi_tiet():
    assert '"(max-width: 1180px)"' in JS
    assert re.search(r"@media \(max-width: 1180px\)\s*\{\s*\.split, \.convo",
                     (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")), (
        "điểm gãy CSS đổi thì hằng KHO_HEP_HOI_THOAI phải đổi theo")
    cuon = _than_ham("cuonToiChiTietNeuHep")
    assert '$("#convdetail")' in cuon and "scrollIntoView" in cuon
    assert "state.cuonToiChiTiet = true" in _than_ham("wireConvRows"), (
        "chỉ cú BẤM mới cuộn — vòng 6 giây vẽ lại mà cuộn là giật màn hình")
    assert "cuonToiChiTietNeuHep()" in _than_ham("loadThread")


# ------------------------------------------------- phụ: verify token

def test_o_verify_token_muc_kenh_khong_trung_o_suc_khoe():
    """
    Ô token mức kênh từng mang `data-tokenslot` TRÙNG id với ô Sức khoẻ của
    Trang đầu tiên, và chuỗi vừa hiện bị vòng 6 giây xoá.
    """
    # Ô token mức kênh nay nằm trong "Chi tiết nâng cao của kênh" (UX-08-03),
    # dựng ở knNangCaoKenh — loadKetNoi chỉ ghép thẻ.
    than = _than_ham("knNangCaoKenh") + _than_ham("loadKetNoi")
    assert 'data-tokenslot="${items[0].id}"' not in than
    assert "data-tokenslot-kenh=" in than and "oTokenDaHien(channel)" in than
    assert "knNangCaoKenh(channel, items, p)" in _than_ham("loadKetNoi")
    assert "state.tokenHien" in _than_ham("oTokenDaHien")
    assert "het" in _than_ham("oTokenDaHien"), "token phải tự ẩn, không nằm mãi trên màn"
