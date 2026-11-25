"""
Đợt UX hội thoại · nhãn · quy tắc tự động: UX-06-01, UX-07-01, UX-07-02,
UX-09-01, UX-16-01, UX-16-02, UX-18-04, MD-UX-18-02.

Logic tự chứa thì CHẠY THẬT bằng node trên đúng mã trong `dashboard/app.js`:
khứ hồi biểu mẫu quy tắc (định dạng JSON lưu xuống không được đổi), xếp
nguồn theo điểm, chip nhãn ngừng dùng, gộp lịch sử xử lý, ngăn lượt xử lý
gọi đúng đường có chặn theo kênh. Phần HTML/CSS kiểm bằng đọc tệp. Đường
sắp xếp quy tắc mới (`/api/tu-dong/sap-xep`) chạy trên Postgres thật.
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
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
SRC = ROOT / "dashboard" / "src"

ESC = ("function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;',"
       "'>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n")


def _ham(ten: str) -> str:
    m = re.search(r"(?m)^(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


def _hang(ten: str) -> str:
    """Hằng cột 0: một dòng (`;` cuối dòng), mảng (tới `];`) hay đối tượng (tới `};`)."""
    m = re.search(r"(?m)^const " + ten + r" = (.)", JS)
    assert m, f"không thấy hằng {ten}"
    mo = m.group(1)
    if mo in "[{" and JS[m.end():].startswith("\n"):
        het = JS.index("\n" + ("]" if mo == "[" else "}") + ";\n", m.start()) + 3
    else:
        het = JS.index(";\n", m.start()) + 1
    return JS[m.start():het] + "\n"


def _node(ma: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("không có node trên PATH")
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


# ============================================================ UX-07-01 biểu mẫu KHI – NẾU – THÌ

def _ma_quy_tac() -> str:
    return (_hang("QT_DK") + _hang("QT_HD") + _hang("QT_NHAN_O") + _hang("_tuKhoa")
            + _hang("_maTat") + _ham("quyTacTuGiaTri") + _ham("giaTriTuQuyTac") + _ham("khoiTrong"))


# Mỗi loại điều kiện và hành động máy chủ hiểu, viết đúng dạng máy chủ trả về.
QUY_TAC_MAU = [
    {"ten": "Chào ngoài giờ", "su_kien": "tin_khach", "bat": True, "thu_tu": 10,
     "dung_xet_sau": False, "cho_ai_tra_loi": True,
     "dieu_kien": {"ngoai_gio": True, "lan_dau": True},
     "hanh_dong": [{"loai": "gui_mau", "ma_tat": "ngoaigio"}]},
    {"ten": "Khiếu nại", "su_kien": "tin_khach", "bat": False, "thu_tu": 0,
     "dung_xet_sau": True, "cho_ai_tra_loi": False,
     "dieu_kien": {"kenh": ["zalo_personal", "facebook"], "chua_tu": ["đổi trả", "hoàn tiền"],
                   "ngoai_gio": False, "lan_dau": False,
                   "nhan_hoi_thoai_co": ["00000000-0000-4000-8000-000000000001"], "nhan_hoi_thoai_khong": ["00000000-0000-4000-8000-000000000002"],
                   "nhan_khach_co": ["00000000-0000-4000-8000-000000000011"], "nhan_khach_khong": ["00000000-0000-4000-8000-000000000012"]},
     "hanh_dong": [{"loai": "gan_nhan_hoi_thoai", "nhan_id": "00000000-0000-4000-8000-000000000003"},
                   {"loai": "gan_nhan_khach", "nhan_id": "00000000-0000-4000-8000-000000000013"},
                   {"loai": "gui_mau", "ma_tat": "doitra"},
                   {"loai": "tao_viec", "tieu_de": "Gọi lại khách", "giao_tu_dong": True},
                   {"loai": "chuyen_nguoi", "ly_do": "khách hỏi đổi trả"}]},
    {"ten": "Mọi tin", "su_kien": "tin_khach", "bat": True, "thu_tu": 100,
     "dung_xet_sau": False, "cho_ai_tra_loi": False, "dieu_kien": {},
     "hanh_dong": [{"loai": "tao_viec", "tieu_de": "Xem tin"}]},
]


def test_khu_hoi_quy_tac_giu_nguyen_dinh_dang_luu():
    """Quy tắc đã lưu -> biểu mẫu -> quy tắc gửi lên: KHÔNG đổi một khoá nào."""
    kq = _node(_ma_quy_tac() + """
const ds = %s;
console.log(JSON.stringify(ds.map((q) => { const { v, hien } = giaTriTuQuyTac(q);
  return { body: quyTacTuGiaTri(v, hien), trong: khoiTrong(v, hien), hien: [...hien].sort() }; })));
""" % json.dumps(QUY_TAC_MAU, ensure_ascii=False))
    for q, r in zip(QUY_TAC_MAU, kq, strict=True):
        assert r["body"] == q, q["ten"]
        assert r["trong"] == [], "khối hiện từ quy tắc đã lưu không được báo trống"
    # Quy tắc không điều kiện: chỉ khối hành động hiện, không bày ô thừa.
    assert kq[2]["hien"] == ["hd_tao_viec"]
    # Định dạng vẫn qua được bộ kiểm của máy chủ (danh sách đóng).
    from agent.omnichannel import tu_dong
    for r in kq:
        tu_dong.kiem_dieu_kien(r["body"]["dieu_kien"])
        tu_dong.kiem_hanh_dong(r["body"]["hanh_dong"])


def test_khoi_an_khong_vao_quy_tac_va_khoi_trong_bi_bao():
    """
    `form.reset()` đưa <select> về lựa chọn đầu: một ô ẩn mang "chỉ ngoài giờ"
    là điều kiện người dùng không thấy. Khối hiện mà trống thì phải báo, không
    lặng lẽ lưu ra quy tắc áp cho MỌI tin.
    """
    kq = _node(_ma_quy_tac() + """
const v = { ten: "x", thu_tu: "100", bat: true, kenh: ["facebook"], chua_tu: "  ,  ",
  ngoai_gio: "true", lan_dau: "true", nhan_khach_co: "n1", hd_gui_mau: "/chao",
  hd_tao_viec: "", hd_chuyen_nguoi: "", hd_gan_nhan_hoi_thoai: "", hd_gan_nhan_khach: "" };
const an = quyTacTuGiaTri(v, new Set(["hd_gui_mau"]));
const trong = khoiTrong(v, new Set(["chua_tu", "hd_gui_mau", "hd_tao_viec"]));
console.log(JSON.stringify({ an, trong }));
""")
    assert kq["an"]["dieu_kien"] == {}, "khối ẩn lọt vào quy tắc"
    assert kq["an"]["hanh_dong"] == [{"loai": "gui_mau", "ma_tat": "chao"}], "mã tắt bỏ dấu /"
    assert kq["trong"] == ["Tin có chứa từ", "Tạo công việc"]


def _bieu_mau() -> str:
    a = HTML.index('<form id="qtForm"')
    return HTML[a:HTML.index("</form>", a)]


def test_moi_khoi_co_nut_them_nut_bo_va_an_san():
    f = _bieu_mau()
    assert re.findall(r'data-qt-nhom="([a-z-]+)"', f) == ["thong-tin", "khi", "neu", "thi"]
    khoa = re.findall(r'const QT_(?:DK|HD) = \[(.*?)\n\];', JS, re.S)
    o = re.findall(r'\{ o: "([a-z_]+)"', "".join(khoa))
    assert len(o) == 13, o
    for k in o:
        khoi = re.search(r'<div class="qt-o" data-qt-o="%s"( hidden)?>' % k, f)
        assert khoi and khoi.group(1), f"khối {k} phải có và ẩn sẵn (tiết lộ dần)"
        assert f'data-qt-mo="{k}"' in f, f"thiếu mục «+ Thêm…» cho {k}"
        assert f'data-qt-bo="{k}"' in f, f"thiếu nút × bỏ {k}"
    # Ô chính của khối có đúng `name` mà `_docForm` đọc.
    for k in o:
        if k != "kenh":
            assert f'name="{k}"' in f, k
    # Biểu mẫu nằm trong ngăn bên, mở bằng "+ Tạo quy tắc" / "Sửa".
    a = HTML.index('id="qtNgan"')
    assert a < HTML.index('<form id="qtForm"') < HTML.index("</aside>", a)
    assert 'id="qtTaoMoi"' in HTML and "moNganQuyTac(q)" in _ham("_dongQuyTac") + JS


# ============================================================ UX-07-02 danh sách quy tắc

def test_dong_quy_tac_co_cong_tac_thu_tu_va_tom_tat():
    kq = _node(ESC + _hang("TEN_KENH") + _hang("QT_DK") + _ham("tenNhanTheoId")
               + _ham("_moTaQuyTacPhan") + _ham("_dongQuyTac") + """
function clock(x) { return "10:00"; }
const state = { tenNhan: { n1: "Chờ hàng" } };
const q = { id: "q1", ten: "Chào", thu_tu: 20, bat: false, sua_luc: "2026-11-25T00:00:00Z",
  dieu_kien: { ngoai_gio: true, nhan_hoi_thoai_co: ["n1"] },
  hanh_dong: [{ loai: "gui_mau", ma_tat: "chao" }], bay_ngay: {} };
console.log(JSON.stringify({ dau: _dongQuyTac(q, 0, 2, true), cuoi: _dongQuyTac(q, 1, 2, true),
  xem: _dongQuyTac(q, 0, 2, false) }));
""")
    dau = kq["dau"]
    assert 'role="switch"' in dau and 'data-qt-bat="q1"' in dau and "checked" not in dau
    assert "Đang tắt" in dau
    assert re.search(r'data-qt-len="q1"\s+disabled', dau), "quy tắc đầu không đưa lên được nữa"
    assert re.search(r'data-qt-xuong="q1"\s+disabled', kq["cuoi"])
    assert "Nếu</b> ngoài giờ và hội thoại có nhãn Chờ hàng" in dau
    assert "Thì</b> gửi mẫu /chao" in dau
    # Không có quyền sửa: thấy công tắc (bị khoá) nhưng không có nút sửa/xếp.
    assert "disabled" in kq["xem"] and "data-qt-sua" not in kq["xem"] and "data-qt-len" not in kq["xem"]
    # Đổi chỗ đi đường sắp xếp riêng, không PUT từng quy tắc.
    assert '"/tu-dong/sap-xep"' in _ham("_doiCho")


# ============================================================ UX-06-01 nhãn ngừng dùng

def test_nhan_ngung_dung_mot_kieu_khong_gach_ngang():
    kq = _node(ESC + _hang("MAU_NHAN_MAC_DINH") + _hang("GOI_Y_NGUNG") + _ham("_mauNhan")
               + _ham("mauChuNhan") + _ham("chipNhan") + """
console.log(JSON.stringify({
  ngung: chipNhan({ id: "n1", ten: "Khách sỉ", mau: "#ff0000", dang_dung: false }, { loai: "khach", dich: "k1" }),
  dung: chipNhan({ id: "n2", ten: "VIP", mau: "#ff0000", dang_dung: true }) }));
""")
    assert "is-ngung" in kq["ngung"] and "Ngừng dùng" in kq["ngung"]
    assert "--nhan-nen" not in kq["ngung"], "nhãn ngừng không được mang màu như nhãn đang dùng"
    assert 'data-nhan-go="n1"' in kq["ngung"], "vẫn gỡ được nhãn đã ngừng"
    assert "--nhan-nen:#ff0000" in kq["dung"] and "Ngừng dùng" not in kq["dung"]
    khoi = CSS[CSS.index(".nhan {"):]
    assert "line-through" not in khoi.split(".filterbar__chon")[0]
    cuoi = CSS[CSS.rindex(".nhan.is-ngung"):]
    assert "text-decoration: none" in cuoi.split("}")[0]
    # Một nguồn cho mọi nơi: hội thoại, Customer 360, chip lọc, danh mục.
    for ham in ("nhanHoiThoaiHtml", "nhanKhachHtml", "chipNhanDong", "veLocNhan", "_veQuanLyNhan"):
        assert "chipNhan(" in _ham(ham), ham
    assert "đã ngừng sử dụng</em>" not in _ham("_veQuanLyNhan"), "danh mục lặp chữ cạnh chip"


# ============================================================ UX-09-01 dấu nhóm

def test_dau_nhom_chi_o_danh_sach_canh_bao_o_o_soan():
    assert "nhomBadge(c)" in _ham("convRow")
    assert "nhomBadge(" not in _ham("veThanhThongTin")
    than = _ham("loadThread")
    assert 'nhom ? "Nhắn cho CẢ NHÓM' in than


# ============================================================ UX-16-01 / 16-02 căn cứ

def _ma_can_cu() -> str:
    return (ESC + _hang("TRICH_NGAN") + _hang("TAG_CAN_CU") + _hang("TRANG_THAI_TIN")
            + _ham("sapXepNguon") + _ham("veTrich") + _ham("dongCT") + _ham("nhanCanCu")
            + _ham("veCanCuPhanLoai") + _ham("veChiTietTin") + _ham("veCanCuDayDu")
            + "function gioTin(x) { return 'hh:mm'; }\nfunction usd(x) { return '$' + x; }\n")


DAI = "Đổi trả trong 7 ngày. " * 40
TIN_AI = {
    "id": "m1", "role": "agent", "delivery_status": "draft", "confidence": 0.82, "content": "Dạ",
    "tac_gia": {"duyet_boi": "Chị Sếp"},
    "dau_vet_ai": {
        "luot_id": "L-1", "can_cu": {"ma": "du", "nhan": "Đủ căn cứ"},
        "tri_thuc": [{"title": "Phí ship", "diem": 0.31, "trich": "ship 30k"},
                     {"title": "Không điểm", "trich": "x"},
                     {"title": "Đổi trả", "diem": 0.92, "version": 3, "trich": DAI},
                     {"title": "Bảo hành", "diem": 0.92, "trich": "12 tháng"}],
        "cong_cu": [{"ten": "tra_cuu_don", "ket_qua": {"ma_don": "DH-BI-MAT-123"}}],
        "luoi": None, "ho_so": {"ten": "Mặc định"}, "che_do": {"chung": "assist"}},
}


def test_nguon_xep_theo_diem_va_trich_doan_gap():
    kq = _node(_ma_can_cu() + """
const state = { chiTietTin: new Set(["m1"]) };
const m = %s;
console.log(JSON.stringify({ thu_tu: sapXepNguon(m.dau_vet_ai.tri_thuc).map((t) => t.title),
  day: veCanCuDayDu(m), ngan: veTrich("ngắn") }));
""" % json.dumps(TIN_AI, ensure_ascii=False))
    # Cao trước; bằng điểm giữ thứ tự gốc; thiếu điểm xuống cuối.
    assert kq["thu_tu"] == ["Đổi trả", "Bảo hành", "Phí ship", "Không điểm"]
    day = kq["day"]
    assert day.index("Đổi trả") < day.index("Bảo hành") < day.index("Phí ship")
    # Tên + đoạn trích chính trước, toàn văn gấp trong <details>.
    assert "Xem toàn văn đoạn trích" in day and DAI.strip() in day
    dau = day[:day.index("Xem toàn văn đoạn trích")]
    assert DAI.strip() not in dau, "đoạn dài phải gấp, không bung sẵn"
    assert "Xem toàn văn" not in kq["ngan"]
    # Điểm thô chỉ trong phần Kỹ thuật, không cạnh tên tài liệu; không phần trăm.
    kt = day[day.index("<summary>Kỹ thuật</summary>"):]
    assert "0.92" in kt and "0.92" not in day[:day.index("<summary>Kỹ thuật</summary>")]
    assert "%" not in day


def test_chi_tiet_trong_luong_chi_la_ban_tom():
    kq = _node(_ma_can_cu() + """
const state = { chiTietTin: new Set(["m1"]) };
console.log(JSON.stringify(veChiTietTin(%s, true)));
""" % json.dumps(TIN_AI, ensure_ascii=False))
    assert "Đổi trả · Bảo hành" in kq and "và 2 tài liệu khác" in kq
    for khong in ("ship 30k", "DH-BI-MAT-123", "<pre", "Đổi trả trong 7 ngày"):
        assert khong not in kq, f"bản tóm trong luồng tin còn bung {khong}"
    assert 'data-can-cu-day-du="m1"' in kq and 'data-xem-luot="L-1"' in kq
    assert "duyệt" in kq.lower() or "Duyệt bởi" in kq


# ============================================================ MD-UX-18-02 lượt xử lý

def test_ngan_luot_xu_ly_goi_duong_chan_theo_kenh():
    """Ngăn lượt gọi `/nhat-ky/hoi-thoai/{cid}/luot/{id}` — không bao giờ đường
    `/nhat-ky/luot/{id}` (đòi quyền nhật ký cả cửa hàng, không chặn kênh)."""
    luot = {"luot_id": "L-1", "tin_khach": {"luc": "2026-11-25T08:00:00Z", "noi_dung": "đổi được không"},
            "buoc": [{"hanh_dong": "AI soạn nháp", "luc": "2026-11-25T08:00:05Z",
                      "trang_thai": {"nhan": "Thành công"}}],
            "tra_loi": [{"luc": "2026-11-25T08:00:05Z", "trang_thai": "draft", "noi_dung": "Dạ được ạ",
                         "dau_vet": TIN_AI["dau_vet_ai"]}],
            "ket_qua": {"hanh_dong": "AI soạn nháp"}}
    kq = _node(_ma_can_cu() + _ham("moNganPhu") + _ham("capNhatNganPhu") + _ham("dongNganPhu")
               + _ham("veLuotXuLy") + _ham("moLuotXuLy") + """
const goi = [];
let than = { innerHTML: "" };
const dom = { "#nganPhuThan": than };
function $(s, r) { return r ? null : (dom[s] || null); }
const document = { createElement: () => ({ setAttribute() {}, set innerHTML(v) {} }),
                   body: { append() {} } };
const state = { openConv: "c-1" };
async function api(url) { goi.push(url); return %s; }
function toast() {}
(async () => {
  await moLuotXuLy("L-1");
  console.log(JSON.stringify({ goi, html: than.innerHTML }));
})();
""" % json.dumps(luot, ensure_ascii=False))
    assert kq["goi"] == ["/nhat-ky/hoi-thoai/c-1/luot/L-1"]
    html = kq["html"]
    buoc = ["Tin khách", "Tra tài liệu", "Gọi công cụ", "Kiểm tra chính sách", "Bản nháp / phê duyệt"]
    vt = [html.index(b) for b in buoc]
    assert vt == sorted(vt), "năm bước phải đúng thứ tự lượt xảy ra"
    assert "đổi được không" in html and "Dạ được ạ" in html and "Nhật ký các bước (1)" in html
    assert html.index("Đổi trả") < html.index("Phí ship"), "nguồn trong lượt cũng xếp theo điểm"
    assert "/nhat-ky/luot/" not in (SRC / "19b-can-cu-luot.js").read_text(encoding="utf-8")


# ============================================================ UX-18-04 lịch sử xử lý

def test_lich_su_xu_ly_gop_mot_dong_thoi_gian():
    kq = _node(_ham("gopLichSuXuLy") + """
const ds = gopLichSuXuLy({
  banGiao: [{ luc: "2026-11-25T08:00:00Z", loai: "chuyen_nguoi", tieu_de: "AI chuyển người", nguoi_lam: "AI" }],
  tin: [
    { id: "m1", role: "agent", created_at: "2026-11-25T08:01:00Z", content: "Dạ",
      tac_gia: { sua_boi: "Lan", sua_luc: "2026-11-25T08:02:00Z", duyet_boi: "Lan", duyet_luc: "2026-11-25T08:03:00Z" } },
    { id: "m2", role: "agent", created_at: "2026-11-25T08:04:00Z", delivery_status: "cancelled", tac_gia: {} },
    { id: "m3", role: "agent", created_at: "2026-11-25T08:06:00Z", delivery_status: "cancelled", tac_gia: {} },
    { id: "m4", role: "customer", created_at: "2026-11-25T08:07:00Z", tac_gia: {} } ],
  deXuat: [{ tao_luc: "2026-11-25T08:08:00Z", ten_hanh_dong: "Huỷ đơn", nhan_trang_thai: "Từ chối",
             tu_choi_boi: "Sếp", tu_choi_luc: "2026-11-25T08:09:00Z", ly_do_tu_choi: "đơn đã giao" }],
  suKien: [{ kind: "ai.ban_nhap.tu_choi", luc: "2026-11-25T08:05:00Z",
             tac_nhan: { loai: "nhan_vien", ten: "Minh" }, chi_tiet: { message_id: "m2", ly_do: "sai giá" } }],
});
// Nhật ký xếp nhầm tác nhân là AI: không được hiện "bởi AI" cho việc người bấm.
const ai = gopLichSuXuLy({ tin: [{ id: "m9", role: "agent", delivery_status: "cancelled", tac_gia: {} }],
  suKien: [{ kind: "ai.ban_nhap.tu_choi", luc: "2026-11-25T09:00:00Z", tac_nhan: { loai: "ai", nhan: "AI" },
             chi_tiet: { message_id: "m9" } }] });
console.log(JSON.stringify(ds.map((x) => [x.loai, x.nguoi, x.chi_tiet]).concat([["ai", ai[0].nguoi, ai[0].luc]])));
""")
    assert kq.pop() == ["ai", "", "2026-11-25T09:00:00Z"]
    assert [x[0] for x in kq] == ["de_xuat_tu_choi", "de_xuat", "tu_choi", "tu_choi", "duyet", "sua",
                                  "chuyen_nguoi"], "mới nhất ở trên, đủ năm loại việc"
    assert kq[0] == ["de_xuat_tu_choi", "Sếp", "Lý do: đơn đã giao"]
    assert kq[3] == ["tu_choi", "Minh", "Lý do: sai giá"], "ai từ chối lấy từ nhật ký"
    assert kq[2][1] == "" and "chưa cho biết ai" in kq[2][2], "thiếu nhật ký thì NÓI, không bịa tên"
    ve = JS[JS.index("function _noiDungChiTietHT"):JS.index("async function taiLichSuPhanCong")]
    assert "Lịch sử xử lý" in ve and "Lịch sử bàn giao" not in ve
    tai = _ham("taiLichSuPhanCong")
    assert "/lich-su-phan-cong" in tai and "/nhat-ky/hoi-thoai/${id}?limit=50" in tai
    # Từ chối không đổi version: khoá làm mới phải đổi theo tin bị huỷ.
    assert "cancelled" in _ham("khoaLichSu")


# ============================================================ /api/tu-dong/sap-xep (Postgres thật)

def test_sap_xep_quy_tac_danh_so_lai_khong_dong_sua_luc(csdl_kiem_thu):
    from fastapi.testclient import TestClient

    import sys

    sys.path.insert(0, str(ROOT))
    from conftest import nguoi_thu
    from tests.test_api_tu_dong import QL, _app

    mau = {"ten": "A", "dieu_kien": {}, "hanh_dong": [{"loai": "tao_viec", "tieu_de": "Gọi lại khách"}]}
    with TestClient(_app(csdl_kiem_thu, nguoi_thu(*QL))) as k:
        tao = []
        for ten, so in (("A", 100), ("B", 100), ("C", 5)):
            r = k.post("/api/tu-dong", json={**mau, "ten": ten, "thu_tu": so})
            assert r.status_code == 201, r.text
            tao.append(r.json())
        a, b, c = tao
        assert [q["ten"] for q in k.get("/api/tu-dong").json()["quy_tac"]] == ["C", "A", "B"]
        r = k.post("/api/tu-dong/sap-xep", json={"ids": [b["id"], c["id"], a["id"]]})
        assert r.status_code == 200, r.text
        ds = k.get("/api/tu-dong").json()["quy_tac"]
        assert [(q["ten"], q["thu_tu"]) for q in ds] == [("B", 10), ("C", 20), ("A", 30)]
        # Đổi chỗ không phải sửa: lỗi cũ của quy tắc không được ẩn đi.
        cu = {q["id"]: q["sua_luc"] for q in (a, b, c)}
        assert all(q["sua_luc"] == cu[q["id"]] for q in ds)
        # Danh sách lệch (thiếu một quy tắc) -> 409, không đoán.
        assert k.post("/api/tu-dong/sap-xep", json={"ids": [a["id"], b["id"]]}).status_code == 409
        assert k.post("/api/tu-dong/sap-xep", json={"ids": [a["id"], a["id"], b["id"]]}).status_code == 422
    with TestClient(_app(csdl_kiem_thu, nguoi_thu("dinh_tuyen.doc"))) as doc:
        assert doc.post("/api/tu-dong/sap-xep", json={"ids": [a["id"]]}).status_code == 403
