"""
Thanh thông tin hội thoại và ô soạn tin (mục 6 + 9 của bảng việc).

Cấu trúc chủ dự án chốt: Tên | Nhãn hội thoại | Customer 360 | Hành động xử
lý | Chi tiết. Mỗi thứ đã gỡ khỏi thanh (trạng thái, kênh, Mode, ưu tiên,
Version, SLA, nút ghi chú) có một test canh — gỡ xong mà không canh thì một
lần "thêm lại cho tiện" là quay về mười thứ thường trực.

Chỗ nào logic tự chứa thì CHẠY THẬT bằng node: bảng nút theo trạng thái ×
quyền (`hanhDongXuLy`), đường gửi của ô soạn (`guiTuKhungSoan`), trộn ghi chú
vào luồng (`xenGhiChu`), tên người gửi tin cuối trong nhóm (`nguoiTinCuoi`).
Đọc mã bằng regex dễ xanh giả với mã đã bị tắt.
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
SRC = ROOT / "dashboard" / "src"
THANH = (SRC / "03b-thanh-hoi-thoai.js").read_text(encoding="utf-8")
HOI_THOAI = (SRC / "03-hoi-thoai.js").read_text(encoding="utf-8")
TRACH_NHIEM = (SRC / "19-trach-nhiem.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def _bo_chu_thich(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", " ", src)


def _ham(ten: str) -> str:
    m = re.search(r"(?m)^(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


def _hang(ten: str) -> str:
    """Một hằng cột 0: đối tượng (tới `};`) hoặc chuỗi mẫu (tới `` `; ``)."""
    m = re.search(r"(?m)^const " + ten + r" = ([{`])", JS)
    assert m, f"không thấy hằng {ten}"
    het = JS.index("\n};\n" if m.group(1) == "{" else "`;\n", m.start())
    return JS[m.start():het + 4] + "\n"


def _node(ma: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node trên PATH")
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _than_load_thread() -> str:
    i = HOI_THOAI.index("async function loadThread(id)")
    return HOI_THOAI[i:]


# ============================================================ 6.5 nút theo trạng thái × quyền

NV = ["hoi_thoai.doc", "hoi_thoai.nhan"]
QL = NV + ["hoi_thoai.xem_tat_ca"]
CHI_DOC = ["hoi_thoai.doc"]
TOI = "u-toi"

# (tên ca, hội thoại, quyền, giaoDuoc) -> (nút chính, menu "⋯", dòng "đang giữ")
BANG = [
    ("AI tự gửi, nhân viên",
     {"mode": "auto", "status": "auto"}, NV, False,
     ("btn-take", ["btn-chedo", "btn-giai-quyet"], "")),
    ("AI tự gửi, quản lý giao được",
     {"mode": "auto", "status": "auto"}, QL, True,
     ("btn-take", ["btn-chedo", "btn-giao", "btn-giai-quyet"], "")),
    ("AI gợi ý: mời trả về tự gửi",
     {"mode": "assist", "status": "assist"}, NV, False,
     ("btn-take", ["btn-chedo", "btn-giai-quyet"], "")),
    ("nhóm: không bao giờ mời AI tự trả lời",
     {"mode": "auto", "status": "auto", "thread_type": 1}, QL, True,
     ("btn-take", ["btn-giao", "btn-giai-quyet"], "")),
    ("AI chuyển người, chưa ai nhận, nhân viên",
     {"mode": "human", "status": "escalated"}, NV, False,
     ("btn-take", ["btn-giai-quyet"], "")),
    ("AI chuyển người, chưa ai nhận, quản lý",
     {"mode": "human", "status": "escalated"}, QL, True,
     ("btn-take", ["btn-giao", "btn-release", "btn-giai-quyet"], "")),
    ("của tôi",
     {"mode": "human", "status": "escalated", "assigned_to": TOI}, NV, False,
     ("btn-giai-quyet", ["btn-release"], "")),
    ("của tôi, giao được",
     {"mode": "human", "status": "escalated", "assigned_to": TOI}, QL, True,
     ("btn-giai-quyet", ["btn-giao", "btn-release"], "")),
    ("đồng nghiệp giữ, nhân viên: không nút, nói ai giữ",
     {"mode": "human", "status": "escalated", "assigned_to": "u-lan", "assigned_to_ten": "Lan"},
     NV, False, (None, [], "Lan đang giữ")),
    ("đồng nghiệp giữ, quản lý",
     {"mode": "human", "status": "escalated", "assigned_to": "u-lan", "assigned_to_ten": "Lan"},
     QL, True, ("btn-giao", ["btn-release", "btn-giai-quyet"], "Lan đang giữ")),
    ("AI đang theo dõi người khác (assist + assigned) vẫn mời tiếp quản",
     {"mode": "assist", "status": "assist", "assigned_to": "u-lan"}, NV, False,
     ("btn-take", ["btn-chedo", "btn-giai-quyet"], "")),
    ("đã giải quyết: chỉ Mở lại",
     {"mode": "auto", "status": "auto", "state": "resolved"}, QL, True,
     ("btn-mo-lai", [], "")),
    ("chỉ đọc: không nút nào",
     {"mode": "auto", "status": "auto"}, CHI_DOC, True, (None, [], "")),
    ("chỉ đọc, đồng nghiệp giữ: chỉ dòng chữ",
     {"mode": "human", "status": "escalated", "assigned_to": "u-lan", "assigned_to_ten": "Lan"},
     CHI_DOC, False, (None, [], "Lan đang giữ")),
]


def _chay_bang():
    ca = [{"c": {"id": "c1", **c}, "q": q, "g": g} for _, c, q, g, _ in BANG]
    ma = (_ham("laNhom") + _hang("HANH_DONG_HT") + _ham("hanhDongXuLy") + """
const ca = %s;
const kq = ca.map(({ c, q, g }) => {
  const r = hanhDongXuLy(c, { toiId: "%s", quyen: new Set(q), giaoDuoc: g });
  return { chinh: r.chinh && r.chinh.id, them: r.them.map((a) => a.id), giu: r.giu,
           chedo: [r.chinh, ...r.them].filter(Boolean).filter((a) => a.id === "btn-chedo")
                    .map((a) => a.che_do)[0] || null };
});
console.log(JSON.stringify(kq));
""" % (json.dumps(ca), TOI))
    return _node(ma)


def test_bang_nut_theo_trang_thai_va_quyen():
    kq = _chay_bang()
    for (ten, *_ , mong), r in zip(BANG, kq, strict=True):
        assert (r["chinh"], r["them"], r["giu"]) == mong, ten


def test_tu_gui_moi_duyet_truoc_va_nguoc_lai():
    kq = _chay_bang()
    assert kq[0]["chedo"] == "assist", "đang tự gửi thì nút phải là 'Duyệt trước khi gửi'"
    assert kq[2]["chedo"] == "auto", "đang gợi ý thì nút phải là 'Để agent tự trả lời'"


def test_khong_bao_gio_qua_nhieu_nut_mot_luc():
    """Một nút chính, phần còn lại trong menu — không bao giờ hiện cả hàng nút."""
    for r in _chay_bang():
        assert len(r["them"]) <= 3
        assert r["chinh"] not in r["them"]


def test_nut_dung_id_va_trinh_nghe_uy_quyen():
    for ma in ("btn-take", "btn-giao", "btn-release", "btn-chedo", "btn-giai-quyet", "btn-mo-lai"):
        assert f'id: "{ma}"' in THANH
    nghe = _bo_chu_thich(THANH[THANH.index("async function _goiHanhDong"):])
    for ma, duong in (("btn-take", "takeover"), ("btn-release", "release"),
                      ("btn-chedo", "che-do"), ("btn-mo-lai", "mo-lai")):
        assert f'ev.target.closest("#{ma}")' in nghe and f'_goiHanhDong("{duong}"' in nghe
    # Hai nút còn lại có trình nghe ở tệp riêng của chúng.
    assert 'closest("#btn-giao")' in TRACH_NHIEM
    assert 'closest("#btn-giai-quyet")' in (SRC / "14-cskh.js").read_text(encoding="utf-8")


def test_menu_them_nho_trang_thai_mo_qua_lan_dung_lai():
    ve = _ham("veHanhDongXuLy")
    assert "state.moHanhDong === String(c.id)" in ve and '${mo ? "open" : ""}' in ve
    assert 'class="hd-them"' in ve and 'role="menu"' in ve
    for lop in (".hd-them__menu", ".hd-them__muc", ".hd {"):
        assert lop in CSS


# ============================================================ 6.1–6.4, 6.7–6.10 cấu trúc thanh

def _ve_thanh(c: dict, quyen: list[str]) -> str:
    ma = (_ham("esc") + _ham("laNhom") + _ham("nhomBadge") + _hang("ICON_C360")
          + _hang("HANH_DONG_HT") + _ham("hanhDongXuLy") + _ham("_nutHanhDong")
          + _ham("veHanhDongXuLy") + _ham("veThanhThongTin") + """
const state = { moChiTietHT: null, moHanhDong: null };
function nhanHoiThoaiHtml(c) { return "<i>NHAN_HOI_THOAI</i>"; }
const c = %s;
const hd = hanhDongXuLy(c, { toiId: "u-toi", quyen: new Set(%s), giaoDuoc: true });
console.log(JSON.stringify({ html: veThanhThongTin(c, hd) }));
""" % (json.dumps(c), json.dumps(quyen)))
    return _node(ma)["html"]


def test_thu_tu_ten_nhan_c360_hanh_dong_chi_tiet():
    html = _ve_thanh({"id": "c1", "customer_name": "Chị Mai", "contact_id": "k1",
                      "mode": "auto", "status": "auto", "account_name": "Zalo shop",
                      "account_channel": "zalo_personal", "priority": "high", "version": 7,
                      "sla_breached": True, "first_response_due_at": "2026-11-22T10:00:00Z"}, QL)
    vt = [html.index(x) for x in ("Chị Mai", "NHAN_HOI_THOAI", 'id="open-contact"',
                                   'aria-label="Hành động xử lý"', 'id="btn-chitiet-ht"')]
    assert vt == sorted(vt), "sai thứ tự Tên | Nhãn | C360 | Hành động | Chi tiết"
    # Nhãn nằm NGAY DƯỚI tên: cùng khối `convo__danh`, trước khi khối ấy đóng.
    khoi = html[html.index('class="convo__danh"'):html.index('class="convo__spacer"')]
    assert "Chị Mai" in khoi and "NHAN_HOI_THOAI" in khoi
    # Customer 360 là nút biểu tượng, có nhãn cho trình đọc màn hình.
    assert 'aria-label="Mở Customer 360"' in html and "<svg" in html
    # Những thứ đã dời khỏi thanh (6.1, 6.2, 6.7, 6.8, 15.7).
    for khong in ("Zalo shop", "Zalo cá nhân", "Tự xử lý", "Mode", "Version", "cao",
                  "SLA", "Ghi chú nội bộ", "btn-them-ghichu"):
        assert khong not in html, f"thanh thông tin còn «{khong}»"


def test_nhom_khong_co_nut_customer_360():
    html = _ve_thanh({"id": "c1", "customer_name": "Nhóm Sỉ", "contact_id": "k1",
                      "thread_type": 1, "mode": "auto", "status": "auto"}, QL)
    assert 'id="open-contact"' not in html, "nhóm không phải một khách hàng (mục 9.7)"
    assert ">Nhóm<" in html, "nhãn Nhóm phải còn cạnh tên"


def test_load_thread_khong_ve_lai_nhung_thu_da_go():
    than = _bo_chu_thich(_than_load_thread())
    assert "${veThanhThongTin(c, hd)}" in than
    for cu in ("slaBadge(c)", "SIGNAL_LABEL[c.status]", "srcBadge(c.account_channel",
               'class="opsbar"', "Mode <b>", "Version <b>", "btn-them-ghichu",
               'class="ghichu"', "first_response_due_at", "nhanKhachHtml"):
        assert cu not in than, f"khung hội thoại còn vẽ {cu}"
    assert ".opsbar" not in CSS


def test_chi_tiet_hoi_thoai_co_uu_tien_version_che_do_khong_co_sla():
    than = TRACH_NHIEM[TRACH_NHIEM.index("function veChiTietHoiThoai"):TRACH_NHIEM.index("async function taiLichSuPhanCong")]
    ma = _bo_chu_thich(than)
    for co in ('"Chế độ AI"', "<b>Ưu tiên</b>", '"Version"', "data-doi-uu-tien", '"Trạng thái"'):
        assert co in ma, f"panel Chi tiết thiếu {co}"
    # "Đổi" ưu tiên chỉ mời người có quyền máy chủ đòi (uu_tien.py).
    assert 'has("hoi_thoai.nhan") && c.state !== "resolved"' in ma
    assert "sla" not in ma.lower(), "SLA không hiện thường trực trong Chi tiết (mục 15.7)"
    # Vẫn chỉ tải khi panel MỞ.
    assert than.index("state.moChiTietHT !== id) return") < than.index("taiLichSuPhanCong(c)")


# ============================================================ 6.6 ghi chú nội bộ trong ô soạn

def test_o_soan_kieu_ghi_chu_khong_bao_gio_goi_duong_gui():
    ma = (_ham("guiTuKhungSoan") + """
const goi = [];
async function api(duong, opts) { goi.push([duong, JSON.parse(opts.body)]); return { ok: true }; }
(async () => {
  await guiTuKhungSoan("c9", "khách này hay bom hàng", true);
  const ghi = goi.splice(0);
  await guiTuKhungSoan("c9", "Dạ em gửi ạ", false);
  console.log(JSON.stringify({ ghi, gui: goi }));
})();
""")
    kq = _node(ma)
    assert kq["ghi"] == [["/inbox/conversations/c9/ghi-chu", {"noi_dung": "khách này hay bom hàng"}]]
    assert kq["gui"] == [["/conversations/c9/send", {"text": "Dạ em gửi ạ"}]]


def test_ban_nhap_tach_theo_kieu_soan():
    """Ghi chú gõ dở không được nằm sẵn trong khung trả lời khách."""
    ma = (_ham("dangGhiChu") + _ham("khoaNhap") + """
const state = { soanGhiChu: { c1: true } };
console.log(JSON.stringify([khoaNhap("c1"), khoaNhap("c2")]));
""")
    assert _node(ma) == ["c1:ghichu", "c2"]
    than = _bo_chu_thich(_than_load_thread())
    assert "state.nhapTheoHoiThoai[id]" not in than, "bản nháp phải theo khoaNhap(id)"
    assert "state.nhapTheoHoiThoai[khoaNhap(id)] = o_moi.value" in than


def test_nop_form_doc_kieu_soan_truoc_khi_cho_mang():
    than = _bo_chu_thich(_than_load_thread())
    nop = than[than.index('$("#replyform").addEventListener("submit"'):]
    assert nop.index("const laGhiChu = dangGhiChu(id)") < nop.index("await guiTuKhungSoan(id, text, laGhiChu)")
    assert "/send`" not in nop, "form chỉ được gửi qua guiTuKhungSoan"
    # Tệp đính kèm đi thẳng tới khách: kiểu ghi chú không vẽ nút, và trình
    # nghe vẫn chặn.
    assert '${ghi ? "" : `<span class="convo__dinhkem">' in than
    assert "if (!f || dangGhiChu(id)) return;" in than


def test_che_do_soan_chi_cho_nguoi_co_quyen_ghi_chu():
    than = _bo_chu_thich(_than_load_thread())
    assert 'const ghiChuDuoc = !!(state.toiQuyen && state.toiQuyen.has("hoi_thoai.ghi_chu"))' in than
    assert "const ghi = ghiChuDuoc && dangGhiChu(id)" in than
    assert "${veCheDoSoan(id, ghiChuDuoc)}" in than
    ve = _ham("veCheDoSoan")
    assert 'if (!ghiChuDuoc) return "";' in ve
    assert "Trả lời khách" in ve and "Ghi chú nội bộ" in ve
    for lop in (".convo__bar--ghichu", ".soan__tab", ".btn--ghichu", ".msg--ghichu"):
        assert lop in CSS


def test_ghi_chu_xen_trong_luong_theo_thoi_gian():
    ma = (_ham("xenGhiChu") + """
const tin = [{ id: 1, created_at: "2026-11-22T08:00:00Z" }, { id: 2, created_at: "2026-11-22T08:10:00Z" }];
const ghi = [{ id: "g2", tao_luc: "2026-11-22T08:20:00Z" }, { id: "g1", tao_luc: "2026-11-22T08:05:00Z" }];
console.log(JSON.stringify(xenGhiChu(tin, ghi).map((x) => x.loai === "tin" ? x.m.id : x.g.id)));
""")
    assert _node(ma) == [1, "g1", 2, "g2"]
    ve = _ham("veGhiChuTrongLuong")
    # Ai viết, lúc nào, và nói rõ khách không thấy.
    assert "g.nguoi" in ve and "gioTin(g.tao_luc)" in ve and "khách không thấy" in ve
    assert "esc(g.noi_dung)" in ve
    assert "xenGhiChu(c.messages, ghiChu, deXuat)" in HOI_THOAI


# ============================================================ 9.5 danh sách: nhóm, người gửi tin cuối

def test_tin_cuoi_trong_nhom_kem_ten_nguoi_gui():
    ma = (_ham("laNhom") + _ham("nguoiTinCuoi") + """
const ca = [
  { thread_type: 1, last_role: "customer", last_sender_name: "Lan" },
  { thread_type: 1, last_role: "customer" },
  { thread_type: 1, last_role: "staff" },
  { thread_type: 0, last_role: "customer", last_sender_name: "Lan" },
];
console.log(JSON.stringify(ca.map(nguoiTinCuoi)));
""")
    assert _node(ma) == ["Lan", "Thành viên nhóm", "Nhân viên", ""]
    hang = _ham("convRow")
    assert "nguoiTinCuoi(c)" in hang and "nhomBadge(c)" in hang and "srcBadge(" in hang
    # Hạn SLA không thường trực trên dòng (15.7); huy hiệu khi sắp/quá hạn vẫn còn.
    assert "SLA ${clock(" not in hang and "slaBadge(c)" in hang


def test_api_danh_sach_tra_vai_va_ten_nguoi_gui_tin_cuoi():
    src = (ROOT / "agent" / "api" / "inbox.py").read_text(encoding="utf-8")
    assert "latest.role AS last_role" in src and "latest.sender_name AS last_sender_name" in src
    assert "SELECT content, delivery_status, role, sender_name" in src
