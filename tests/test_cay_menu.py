"""
Cây menu theo phiếu việc của chủ dự án (20.11.2026), mục 1, 4, 5.

Canh CẤU TRÚC (index.html, app.js) và HỢP ĐỒNG điểm gắn `window.GAN_TAB` mà
ba mô-đun khác dựa vào: đổi một id tab là mô-đun ấy gắn vào hư không, không
lỗi, không nhật ký — đúng kiểu hỏng im lặng CLAUDE.md cảnh báo.

Hành vi công tắc AI toàn cục chạy thật trên Postgres ở
tests/test_cong_tac_ai_toan_cuc.py.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
SRC = ROOT / "dashboard" / "src"

SAU_MAN = [("hoithoai", "Hội thoại"), ("khachhang", "Khách hàng"), ("donhang", "Đơn hàng"),
           ("kho", "Kho"), ("congviec", "Công việc"), ("sohieu", "Phân tích")]
CAI_DAT = [("cauhinhchung", "Cấu hình chung"), ("cauhinhai", "Cấu hình AI Agent"),
           ("nhansu", "Nhân sự &amp; Phân quyền"), ("hethong", "Hệ thống &amp; Nhật ký")]
TAB = {
    "congviec": ["cv-ca-truc", "cv-danh-sach"],
    "cauhinhchung": ["cc-nhan", "cc-tu-dong", "cc-ket-noi", "cc-sla", "cc-dieu-phoi"],
    "cauhinhai": ["ai-co-ban", "ai-tri-thuc", "ai-ky-nang", "ai-chinh-sach", "ai-phong-thu"],
    "nhansu": ["ns-nhan-vien", "ns-vai-tro"],
    "hethong": ["ht-suc-khoe", "ht-sao-luu", "ht-nhat-ky"],
}


def _rail() -> str:
    return HTML[HTML.index('<nav class="rail"'):HTML.index("</nav>")]


def _view(ten: str) -> str:
    i = HTML.index(f'data-view="{ten}">', HTML.index("<main"))
    i = HTML.rfind("<section", 0, i)
    j = HTML.find('<section class="view', i + 10)
    return HTML[i:j if j != -1 else HTML.index("</main>")]


def _tab(tid: str) -> str:
    i = HTML.index(f'<section class="tabpanel" id="{tid}"')
    j = HTML.find('<section class="tabpanel"', i + 10)
    k = HTML.find('<section class="view', i)
    ends = [x for x in (j, k, HTML.index("</main>")) if x != -1]
    return HTML[i:min(ends)]


def _than_ham(ten: str) -> str:
    m = re.search(rf"(?:async )?function {ten}\(.*?\n\}}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


# ------------------------------------------------------------ thanh bên

def test_dung_sau_man_nghiep_vu_dung_thu_tu():
    rail = _rail()
    ngoai_nhom = rail[:rail.index('id="railCaiDat"')]
    thay = re.findall(r'class="rail__item[^"]*" data-view="([a-z]+)">\s*<svg.*?</svg>\s*'
                      r'<span>([^<]+)</span>', ngoai_nhom, re.S)
    assert thay == SAU_MAN, thay


def test_nhom_cai_dat_thu_gon_duoc_va_dung_bon_con():
    rail = _rail()
    nhom = rail[rail.index('id="railCaiDat"'):]
    assert "Cài đặt &amp; Quản trị" in nhom
    assert 'aria-expanded="false"' in nhom and 'aria-controls="railCaiDatCon"' in nhom
    assert re.search(r'id="railCaiDatCon"[^>]*hidden', nhom), "nhóm phải THU GỌN mặc định"
    con = re.findall(r'data-view="([a-z]+)">\s*<svg.*?</svg>\s*<span>([^<]+)</span>', nhom, re.S)
    assert con == CAI_DAT, con


def test_khong_con_video_dang_bai_hay_thong_bao_tren_thanh_ben():
    rail = _rail()
    for chu in ("Video", "Đăng bài", "Thông báo", "Sức khoẻ", "Ca trực"):
        assert chu not in rail, f"thanh bên còn mục «{chu}»"
    for cu in ("video", "dangbai", "noidung", "ca", "ketnoi", "trithuc", "kynang",
               "phongthu", "nhatky", "cauhinh"):
        assert f'data-view="{cu}"' not in HTML, f"còn màn cũ data-view={cu}"


def test_moi_muc_thanh_ben_co_dung_mot_man():
    man = HTML[HTML.index("<main"):]
    for v in re.findall(r'class="rail__item[^"]*" data-view="([a-z]+)"', _rail()):
        assert man.count(f'<section class="view" data-view="{v}">') + man.count(
            f'<section class="view is-active" data-view="{v}">') == 1, v


# ------------------------------------------------------------ tab + điểm gắn

@pytest.mark.parametrize("man,cac_tab", TAB.items())
def test_tab_dung_id_hop_dong_va_nam_dung_man(man, cac_tab):
    v = _view(man)
    nut = re.findall(r'class="tabbar__nut"[^>]*data-tab="([a-z-]+)"', v)
    assert nut == cac_tab, nut
    for t in cac_tab:
        assert f'<section class="tabpanel" id="{t}" data-gan="{t}"' in v, (
            f"tab #{t} phải nằm trong màn {man} và mang data-gan cùng tên")
        assert f'aria-controls="{t}"' in v


def test_khe_nha_cung_cap_nam_trong_ai_co_ban():
    t = _tab("ai-co-ban")
    assert 'data-gan="ai-co-ban-nha-cung-cap"' in t
    khe = t[t.index('data-gan="ai-co-ban-nha-cung-cap"'):]
    assert 'class="tab__goc"' in khe[:300], "khe phải có nội dung mặc định để thay thế"


def test_so_dang_ky_GAN_TAB_nap_dau_tien():
    tep = sorted(p.name for p in SRC.glob("*.js"))
    assert tep[0] == "00-gan-tab.js", tep[:3]
    dau = (SRC / "00-gan-tab.js").read_text(encoding="utf-8")
    assert "window.GAN_TAB = window.GAN_TAB || {};" in dau
    assert JS.index("window.GAN_TAB = window.GAN_TAB || {};") < JS.index("const state = {")


def test_gan_khe_an_noi_dung_goc_va_lui_lai_khi_mo_dun_hong():
    than = _than_ham("ganKhe")
    assert "o._daGan" in than, "phải gắn MỘT lần"
    assert 'contains("tab__goc")' in than and "goc.hidden = true" in than
    assert "catch" in than and "goc.hidden = false" in than and "toast(" in than, (
        "mô-đun hỏng phải trả nội dung mặc định VÀ báo người dùng")
    assert "GAN_LOI.add(id)" in than
    assert "GAN_LOI.has(id)" in _than_ham("daGan")


@pytest.mark.skipif(not shutil.which("node"), reason="cần node để chạy JS")
def test_gan_khe_chay_that_trong_node():
    """
    Chạy ĐÚNG mã ganKhe/daGan trong app.js trên một DOM giả tối thiểu:
    mô-đun được gọi một lần với chỗ vẽ mới, phần gốc ẩn; mô-đun ném lỗi thì
    phần gốc hiện lại, có toast, và daGan() trả false để vòng làm mới nạp
    nội dung mặc định như cũ.
    """
    ma = "\n".join([
        "const GAN_LOI = new Set();",
        _than_ham("daGan"), _than_ham("ganKhe"),
    ])
    kich_ban = r"""
    const window = { GAN_TAB: {} };
    const state = { toiQuyen: new Set(["x"]) };
    const api = () => {}, esc = (s) => s;
    const toasts = []; const toast = (m, bad) => toasts.push([m, bad]);
    console.error = () => {};
    function el(cls) {
      const e = { className: cls || "", dataset: {}, hidden: false, children: [],
        classList: { contains: (c) => (e.className || "").split(" ").includes(c) },
        after(x) { e.parent.children.splice(e.parent.children.indexOf(e) + 1, 0, x); x.parent = e.parent; },
        append(x) { e.children.push(x); x.parent = e; },
        remove() { const a = e.parent.children; a.splice(a.indexOf(e), 1); } };
      return e;
    }
    const document = { createElement: () => el("") };
    function khe(id) { const o = el("tabpanel"); o.dataset.gan = id; o.append(el("tab__goc")); return o; }
    __MA__
    const ra = {};
    // 1. chưa ai đăng ký: không đụng gì
    const a = khe("ns-nhan-vien"); ganKhe(a);
    ra.chuaDangKy = a.children.length === 1 && !a.children[0].hidden && !daGan("ns-nhan-vien");
    // 2. đăng ký: gọi một lần, gốc ẩn, chỗ vẽ mới đứng sau gốc
    let goi = 0;
    window.GAN_TAB["ns-nhan-vien"] = (o, ctx) => { goi++; o.ve = ctx.id; };
    ganKhe(a); ganKhe(a);
    ra.goiMotLan = goi === 1;
    ra.gocAn = a.children[0].hidden === true;
    ra.choVe = a.children[1].className === "tab__gan" && a.children[1].ve === "ns-nhan-vien";
    ra.daGan = daGan("ns-nhan-vien");
    // 3. mô-đun hỏng: gốc hiện lại, có toast đỏ, daGan false
    window.GAN_TAB["cc-nhan"] = () => { throw new Error("hỏng"); };
    const b = khe("cc-nhan"); ganKhe(b);
    ra.hongGocHien = b.children.length === 1 && b.children[0].hidden === false;
    ra.hongToast = toasts.length === 1 && toasts[0][1] === true;
    ra.hongKhongGan = daGan("cc-nhan") === false;
    console.log(JSON.stringify(ra));
    """.replace("__MA__", ma)
    kq = subprocess.run(["node", "-e", kich_ban], capture_output=True, text=True,
                        encoding="utf-8", timeout=60)
    assert kq.returncode == 0, kq.stderr
    import json
    ra = json.loads(kq.stdout.strip().splitlines()[-1])
    assert all(ra.values()), ra


def test_moi_tab_co_quyen_va_quyen_co_that():
    from agent.core.quyen import QUYEN

    khoi = JS[JS.index("const QUYEN_TAB = {"):]
    khoi = khoi[:khoi.index("};")]
    co = dict(re.findall(r'"([a-z-]+)":\s*\[([^\]]*)\]', khoi))
    for ds in TAB.values():
        for t in ds:
            assert t in co, f"tab {t} chưa khai quyền để thấy trong QUYEN_TAB"
    for t, ds in co.items():
        for q in re.findall(r'"([a-z_.]+)"', ds):
            assert q in QUYEN, f"QUYEN_TAB[{t}] dùng quyền không tồn tại: {q}"


def test_menu_an_theo_quyen_sau_khi_dang_nhap():
    then = JS[JS.index("kiemPhien().then("):][:200]
    assert then.index("apDungQuyenMenu()") < then.index("refresh()")
    than = _than_ham("apDungQuyenMenu")
    assert "manDuocThay" in than and "tabDuocThay" in than and "railCaiDat" in than


def test_ten_man_cu_van_dan_toi_dung_tab():
    """Thông báo trên máy, `di_toi_man` của máy chủ, mã cũ vẫn gọi tên cũ."""
    khoi = JS[JS.index("const MAN_CU = {"):]
    khoi = khoi[:khoi.index("};")]
    for cu, moi in [("ca", "cv-ca-truc"), ("ketnoi", "cc-ket-noi"), ("trithuc", "ai-tri-thuc"),
                    ("kynang", "ai-ky-nang"), ("phongthu", "ai-phong-thu"),
                    ("nhatky", "ht-nhat-ky"), ("cauhinh", "ai-co-ban")]:
        assert re.search(rf'\b{cu}: "{moi}"', khoi), (cu, moi)
    assert "MAN_CU[ten]" in _than_ham("doiMan")


# ------------------------------------------------------------ chuyển nội dung

@pytest.mark.parametrize("tid,ids", [
    ("cv-ca-truc", ["readout", "pnChet", "pnVoChu", "queue", "cvTrongCa", "cvChuaGiao", "cvSla"]),
    ("cv-danh-sach", ["cv-ds", "cv-them"]),
    ("cc-nhan", ["truong-ds"]),
    ("cc-tu-dong", ["mauNhanhDs", "qtDs", "qtForm"]),
    ("cc-ket-noi", ["connectiongrid", "kn-dieukien", "kn-suckhoe", "api-panel", "erpthu", "tichhop-ds"]),
    ("cc-sla", ["dtSla", "dtFormSla", "api-nhom-sla"]),
    ("cc-dieu-phoi", ["dtDoi", "dtLuat", "dtFormNguoi"]),
    ("ai-co-ban", ["aiBat", "cauhinh-ds", "cauhinh-lichsu", "hsa-ds", "api-nhom-model"]),
    ("ai-tri-thuc", ["docform", "docs", "probeform"]),
    ("ai-ky-nang", ["kynang-tatca", "pluginform", "mcpform"]),
    ("ai-phong-thu", ["phongthu-form", "phongthu-chat"]),
    ("ns-nhan-vien", ["nsNguoi", "nsFormNguoi", "lcPanel", "nsPanelGiaiThich"]),
    ("ns-vai-tro", ["nsVaiTro", "nsFormVaiTro", "tamnhin"]),
    ("ht-suc-khoe", ["hethong", "health", "healthrun"]),
    ("ht-sao-luu", ["ycPanel", "pdpdform", "dsRetention", "api-nhom-bvdlcn"]),
    ("ht-nhat-ky", ["events"]),
])
def test_noi_dung_cu_nam_dung_tab(tid, ids):
    t = _tab(tid)
    for i in ids:
        assert f'id="{i}"' in t, f"#{i} phải nằm trong tab {tid}"


def test_khoi_luon_o_lai_nam_ngoai_phan_bi_thay():
    """
    Mô-đun gắn vào chỉ thay `.tab__goc`. Kênh chat, lịch ca, mức tầm nhìn,
    trường thông tin khách KHÔNG được nằm trong đó — gắn mô-đun Tích hợp
    hay Nhân sự vào là chúng biến mất mà không ai thay.
    """
    for tid, oid in [("cc-ket-noi", "connectiongrid"), ("ns-nhan-vien", "lcPanel"),
                     ("ns-vai-tro", "tamnhin"), ("cc-nhan", "truong-ds"), ("ai-co-ban", "aiBat")]:
        t = _tab(tid)
        i = t.index(f'id="{oid}"')
        if 'class="tab__goc"' in t:
            g = t.index('class="tab__goc"')
            # nằm trước tab__goc, hoặc sau thẻ đóng của nó
            assert i < g or i > t.index("\n        </div>", g), f"#{oid} nằm trong .tab__goc của {tid}"


def test_chinh_sach_uy_quyen_la_cho_trong():
    assert "Nội dung chi tiết sẽ được hoàn thiện sau" in _tab("ai-chinh-sach")


def test_suc_khoe_he_thong_chi_o_he_thong_va_nhat_ky():
    assert "Sức khoẻ" not in _view("sohieu"), "màn Phân tích không được lặp Sức khoẻ"
    assert HTML.count('id="healthrun"') == 1 and 'id="healthrun"' in _tab("ht-suc-khoe")
    assert HTML.count("Sức khoẻ hệ thống") == 2  # nút tab + tiêu đề panel, cùng một tab


# ------------------------------------------------------------ mục 1, 5, ẩn CSAT/VietQR

def test_nut_quay_lai_hai_buoc():
    """Màn 2 lớp (hộp hỏi chung #congHoi) dùng "← Quay lại", không còn "Thôi, quay lại"."""
    assert "Thôi, quay lại" not in HTML
    hoi = HTML[HTML.index('id="congHoi"'):]
    assert '<a href="#" id="hoiHuy">← Quay lại</a>' in hoi[:900]


def test_bo_chon_che_do_roi_thanh_tren_vao_cau_hinh_co_ban():
    dau = HTML[HTML.index('<header class="masthead">'):HTML.index("</header>")]
    assert "data-mode" not in dau and 'class="modeswitch"' not in dau
    assert 'id="killswitch"' in dau, "ngắt khẩn cấp ở lại thanh trên"
    t = _tab("ai-co-ban")
    assert 'data-mode="assist"' in t and 'data-mode="auto"' in t
    assert HTML.count("data-mode=") == 2
    assert re.search(r'<input type="checkbox" id="aiBat"', t)


def test_cong_tac_ai_ghi_dung_duong_runtime():
    """Công tắc mới dùng đúng POST /runtime {enabled} — không đường ghi thứ hai."""
    i = JS.index('$("#aiBat")?.addEventListener("change"')
    khoi = JS[i:i + 900]
    assert 'api("/runtime"' in khoi and "enabled: bat" in khoi
    assert "e.target.checked = !bat" in khoi, "máy chủ từ chối thì công tắc phải trả về"
    than = _than_ham("applyRuntime")
    assert "#aiBat" in than and "rt.enabled" in than
    # Danh sách "Cấu hình agent" không vẽ lại hai khoá đã có khối riêng.
    assert 'new Set(["enabled", "mode"])' in JS and "KHOA_CO_KHOI_RIENG.has(m.khoa)" in _than_ham("loadCauHinh")


def test_csat_va_vietqr_khong_hien_nhung_ma_con():
    o = re.findall(r'data-api-cac-nhom="([^"]+)"', HTML)
    nhom = [x.strip() for ds in o for x in ds.split(",")]
    assert "csat" not in nhom and "thanh_toan" not in nhom
    for ma in ("model", "erp", "van_chuyen", "binh_luan", "bvdlcn", "sla"):
        assert nhom.count(ma) == 1, f"nhóm {ma} phải có đúng MỘT chỗ"
    # Mã giữ nguyên: bảng nhóm còn đủ, chỉ không có ô nào nhận.
    assert 'thanh_toan: "Thanh toán (VietQR)"' in JS and 'csat: "Khảo sát hài lòng (CSAT)"' in JS
    assert "const HIEN_VIETQR = false;" in JS
    assert "${HIEN_VIETQR && o.trang_thai" in JS
    assert "<th>CSAT</th>" not in JS
    assert "CSAT" not in HTML.replace("<!--", "\x00").split("\x00")[0]  # không lộ ở thanh trên


def test_csat_mac_dinh_tat():
    from agent import cau_hinh_dong
    from agent.config import Settings

    assert Settings.model_fields["csat_bat"].default == "tat"
    assert cau_hinh_dong.DANH_MUC["CSAT_BAT"].nhom == "csat"


def test_moi_nhom_khoa_moi_deu_co_cho_hien():
    """
    Nhóm khoá chỉ hiện khi có ô `data-api-cac-nhom` nhận nó. Thêm một nhóm
    mới vào cau_hinh_dong mà quên chỗ hiện thì khoá ấy không ai sửa được từ
    dashboard — và không có gì báo. Chỉ csat/thanh_toan được cố ý vắng.
    """
    from agent import cau_hinh_dong

    o = re.findall(r'data-api-cac-nhom="([^"]+)"', HTML)
    co_cho = {x.strip() for ds in o for x in ds.split(",")}
    nhom = {m.nhom for m in cau_hinh_dong.DANH_MUC.values()}
    assert nhom - co_cho == {"csat", "thanh_toan"}, nhom - co_cho


# ------------------------------------------------------------ vòng làm mới theo tab

@pytest.mark.parametrize("dieu_kien,loader", [
    ('dangMo("cv-ca-truc")', "loadTongQuanCa()"),
    ('dangMo("cv-danh-sach")', "loadCongViec()"),
    ('dangMo("cc-tu-dong")', "loadQuyTac()"),
    ('dangMo("ai-tri-thuc")', "loadDocs()"),
    ('dangMo("ai-ky-nang")', "loadKyNang()"),
    ('dangMo("ht-nhat-ky")', "loadEvents()"),
    ('dangMo("ht-suc-khoe")', "loadHeThong()"),
])
def test_vong_lam_moi_nap_theo_tab(dieu_kien, loader):
    than = _than_ham("refresh")
    dong = next((d for d in than.splitlines() if f"if ({dieu_kien}" in d), "")
    assert loader in dong, f"{loader} phải nạp dưới {dieu_kien}"


def test_tab_da_gan_mo_dun_thi_khong_nap_noi_dung_cu():
    assert "!daGan(id)" in _than_ham("dangMo")
    assert "ganTabDangHien()" in _than_ham("refresh")


# ------------------------------------------------------------ khổ hẹp

def test_thanh_ben_thu_gon_o_kho_hep():
    assert 'id="railMo"' in HTML[HTML.index('<header class="masthead">'):HTML.index("</header>")]
    cuoi = CSS[CSS.rindex("@media (max-width: 780px)"):]
    assert re.search(r"\.rail\s*\{\s*display:\s*none;", cuoi)
    assert ".rail.is-mo" in cuoi and "flex-direction: column" in cuoi
    assert re.search(r"\.tabbar\s*\{[^}]*overflow-x:\s*auto", CSS), (
        "thanh tab phải tự cuộn trong nó, không đẩy trang cuộn ngang")
    assert "dongMenuDiDong()" in _than_ham("doiMan")
