"""
Kiểm thử hồi quy cho BUG-12-01 và BUG-12-02 (phân quyền Dashboard).

- BUG-12-01: Menu Công việc (`congviec`, `cv-ca-truc`, `cv-danh-sach`) không được hiển thị
  cho tài khoản chỉ có `hoi_thoai.doc` mà thiếu `cong_viec.doc`; điều hướng trực tiếp
  qua `doiMan` tới màn/tab thiếu quyền phải bị chặn.
- BUG-12-02: Ô soạn tin (`#replyform`), nút đính kèm (`[data-dinhkem]`), chế độ ghi chú
  nội bộ (`veCheDoSoan`, `dangGhiChu`, `guiTuKhungSoan`), và nút Customer 360 (`#open-contact`)
  phải kiểm tra đúng các quyền `hoi_thoai.tra_loi`, `hoi_thoai.ghi_chu`, `khach.doc`.
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
HOI_THOAI = (SRC / "03-hoi-thoai.js").read_text(encoding="utf-8")
DIEU_HUONG = (SRC / "01b-dieu-huong.js").read_text(encoding="utf-8")


def _ham(ten: str) -> str:
    m = re.search(r"(?m)^(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}()"
    return m.group(0)


def _hang(ten: str) -> str:
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


# ============================================================ BUG-12-01

def test_bug_12_01_quyen_menu_cong_viec_va_ca_truc():
    """Chỉ có `hoi_thoai.doc` KHÔNG được thấy menu Công việc; có `cong_viec.doc` mới thấy."""
    ma = (
        _hang("MAN_CU") + _hang("QUYEN_TAB") + _hang("QUYEN_MAN")
        + _ham("duocThay") + _ham("manDuocThay")
        + """
const tabMap = {
  congviec: [{ id: "cv-ca-truc" }, { id: "cv-danh-sach" }],
  hoithoai: [], khachhang: [], donhang: [], kho: [], nhansu: [], sohieu: []
};
function cacTab(man) { return (tabMap[man] || []).map((t) => ({ id: t.id, classList: { contains: () => true } })); }
const tabDuocThay = (id) => duocThay(QUYEN_TAB[id]);
const state = {};
function check(quyen) {
  state.toiQuyen = new Set(quyen);
  return {
    congviec: manDuocThay("congviec"),
    ca_truc_tab: tabDuocThay("cv-ca-truc"),
    danh_sach_tab: tabDuocThay("cv-danh-sach"),
    hoithoai: manDuocThay("hoithoai"),
  };
}
console.log(JSON.stringify({
  chi_xem_ht: check(["hoi_thoai.doc"]),
  chi_xem_cv: check(["cong_viec.doc"]),
  du_ca_hai: check(["hoi_thoai.doc", "cong_viec.doc"]),
}));
"""
    )
    kq = _node(ma)
    assert kq["chi_xem_ht"] == {
        "congviec": False, "ca_truc_tab": False, "danh_sach_tab": False, "hoithoai": True
    }
    assert kq["chi_xem_cv"]["congviec"] is True
    assert kq["chi_xem_cv"]["danh_sach_tab"] is True
    assert kq["chi_xem_cv"]["hoithoai"] is False
    assert kq["du_ca_hai"] == {
        "congviec": True, "ca_truc_tab": True, "danh_sach_tab": True, "hoithoai": True
    }


def test_bug_12_01_chan_dieu_huong_truc_tiep_doi_man():
    """`doiMan()` phải chặn điều hướng trực tiếp tới màn hoặc tab không có quyền."""
    assert "if (state.toiQuyen)" in DIEU_HUONG
    ma = (
        _hang("MAN_CU") + _hang("QUYEN_TAB") + _hang("QUYEN_MAN")
        + _ham("duocThay") + _ham("manDuocThay") + _ham("doiMan")
        + """
const tabMap = {
  congviec: ["cv-ca-truc", "cv-danh-sach"],
  hoithoai: [], khachhang: [], donhang: [],
};
function cacTab(man) { return (tabMap[man] || []).map((id) => ({ id })); }
function manCuaTab(id) {
  for (const [m, ds] of Object.entries(tabMap)) if (ds.includes(id)) return m;
  return null;
}
const tabDuocThay = (id) => duocThay(QUYEN_TAB[id]);
const toasts = [];
const state = { view: "hoithoai", tab: {}, toiQuyen: new Set(["hoi_thoai.doc"]) };
function $(s) { return null; }
function $$(s) { return []; }
function toast(m, err) { toasts.push([m, !!err]); }
function veTab() {}
function moNhomCaiDat() {}
function dongMenuDiDong() {}
function refresh() {}

const r1 = doiMan("congviec");
const r2 = doiMan("cv-danh-sach");
const r3 = doiMan("ca");
const r4 = doiMan("khachhang");
const r5 = doiMan("hoithoai");
console.log(JSON.stringify({ r1, r2, r3, r4, r5, view: state.view, toastsCount: toasts.length }));
"""
    )
    kq = _node(ma)
    assert kq["r1"] is False
    assert kq["r2"] is False
    assert kq["r3"] is False
    assert kq["r4"] is False
    assert kq["r5"] is True
    assert kq["view"] == "hoithoai"
    assert kq["toastsCount"] == 4


# ============================================================ BUG-12-02

def test_bug_12_02_che_do_soan_va_gui_theo_quyen():
    """
    Kiểm tra logic `dangGhiChu`, `veCheDoSoan`, `guiTuKhungSoan`:
    - Có ghi chú nhưng thiếu trả lời: ép buộc chế độ ghi chú, không vẽ tab 'Trả lời khách',
      chặn gọi `/send`.
    - Thiếu cả hai: chặn cả `/send` và `/ghi-chu`.
    """
    ma = (
        _ham("dangGhiChu") + _ham("veCheDoSoan") + _ham("guiTuKhungSoan")
        + """
const state = { toiQuyen: null, soanGhiChu: {} };
const calls = [];
async function api(u, o) { calls.push([u, JSON.parse(o.body)]); return { ok: true }; }

(async () => {
  // 1. Có ghi chú, KHÔNG có trả lời
  state.toiQuyen = new Set(["hoi_thoai.doc", "hoi_thoai.ghi_chu"]);
  state.soanGhiChu["c1"] = false; // dù state cũ là false
  const ghi1 = dangGhiChu("c1");
  const html1 = veCheDoSoan("c1", true);
  let errSend1 = "";
  try { await guiTuKhungSoan("c1", "lén gửi", false); } catch (e) { errSend1 = e.message; }
  await guiTuKhungSoan("c1", "ghi chú hợp lệ", true);

  // 2. Chỉ có hoi_thoai.doc (không trả lời, không ghi chú)
  state.toiQuyen = new Set(["hoi_thoai.doc"]);
  const ghi2 = dangGhiChu("c1");
  let errNote2 = "";
  try { await guiTuKhungSoan("c1", "lén ghi chú", true); } catch (e) { errNote2 = e.message; }

  // 3. Có cả trả lời và ghi chú
  state.toiQuyen = new Set(["hoi_thoai.doc", "hoi_thoai.tra_loi", "hoi_thoai.ghi_chu"]);
  state.soanGhiChu["c1"] = false;
  const ghi3 = dangGhiChu("c1");
  const html3 = veCheDoSoan("c1", true);

  console.log(JSON.stringify({ ghi1, html1, errSend1, ghi2, errNote2, ghi3, html3, calls }));
})();
"""
    )
    kq = _node(ma)
    assert kq["ghi1"] is True
    assert "Ghi chú nội bộ" in kq["html1"]
    assert "Trả lời khách" not in kq["html1"]
    assert kq["errSend1"] != ""
    assert kq["ghi2"] is False
    assert kq["errNote2"] != ""
    assert kq["ghi3"] is False
    assert "Trả lời khách" in kq["html3"] and "Ghi chú nội bộ" in kq["html3"]
    assert kq["calls"] == [["/inbox/conversations/c1/ghi-chu", {"noi_dung": "ghi chú hợp lệ"}]]


def test_bug_12_02_an_customer_360_khi_thieu_khach_doc():
    """Nút `#open-contact` chỉ hiện khi có quyền `khach.doc`."""
    ma = (
        _ham("esc") + _ham("laNhom") + _ham("nhomBadge") + _hang("ICON_C360")
        + _hang("HANH_DONG_HT") + _ham("hanhDongXuLy") + _ham("_nutHanhDong")
        + _ham("veHanhDongXuLy") + _ham("veThanhThongTin")
        + """
const state = { moChiTietHT: null, moHanhDong: null, toiQuyen: null };
function nhanHoiThoaiHtml() { return ""; }
const c = { id: "c1", customer_name: "Khách A", contact_id: "k1", mode: "auto", status: "auto" };

state.toiQuyen = new Set(["hoi_thoai.doc"]);
const htmlNoKhach = veThanhThongTin(c, hanhDongXuLy(c, { toiId: "u1", quyen: state.toiQuyen, giaoDuoc: false }));

state.toiQuyen = new Set(["hoi_thoai.doc", "khach.doc"]);
const htmlCoKhach = veThanhThongTin(c, hanhDongXuLy(c, { toiId: "u1", quyen: state.toiQuyen, giaoDuoc: false }));

console.log(JSON.stringify({
  hasC360WithoutPerm: htmlNoKhach.includes('id="open-contact"'),
  hasC360WithPerm: htmlCoKhach.includes('id="open-contact"'),
}));
"""
    )
    kq = _node(ma)
    assert kq["hasC360WithoutPerm"] is False
    assert kq["hasC360WithPerm"] is True


def test_bug_12_02_khong_ve_replyform_va_chan_dinh_kem_trong_load_thread():
    """`loadThread` chỉ vẽ `#replyform` khi có `hoi_thoai.tra_loi` hoặc `hoi_thoai.ghi_chu`."""
    assert 'const traLoiDuoc = !!(state.toiQuyen && state.toiQuyen.has("hoi_thoai.tra_loi"));' in HOI_THOAI
    assert "const formSoan = (traLoiDuoc || ghiChuDuoc)" in HOI_THOAI
    assert 'if (state.toiQuyen && !state.toiQuyen.has("hoi_thoai.tra_loi"))' in HOI_THOAI
