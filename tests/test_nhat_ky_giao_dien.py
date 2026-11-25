"""
Giao diện Nhật ký (UX-18-01/02/03) và nhịp chung màn Cấu hình AI (UX-17-04).

Vẽ thật bằng Node trên chính `dashboard/src/27-nhat-ky.js` — đọc chuỗi mã
nguồn thì "có chữ data-nk-lk" vẫn xanh dù nút ấy hiện cho người không có
quyền.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC27 = ROOT / "dashboard" / "src" / "27-nhat-ky.js"
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")

_NODE = """
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const fn = new Function(
  'state', 'esc', 'gioTin', 'clock', 'dongCT', 'api', 'toast', 'hoiHop', 'window', 'document', 'GAN_TAB',
  src + '; return { nkDong, nkVeChiTiet, nkChuoiLoc, nk };');
const m = fn({ toiQuyen: new Set(['nhat_ky.doc']) },
  (s) => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'),
  () => '10:30', () => '10:30', (t, c) => `<div><b>${t}</b><span>${c}</span></div>`,
  async () => ({}), () => {}, async () => null, {}, { addEventListener() {} }, {});
const ds = JSON.parse(process.argv[2]);
console.log(JSON.stringify({
  dong: ds.map((b) => m.nkDong(b)),
  chi_tiet: m.nkVeChiTiet(ds[0]),
  loc: m.nkChuoiLoc(),
}));
"""


def _ban_ghi(**them) -> dict:
    b = {
        "id": 7, "luc": "2026-11-25T10:30:00+07:00", "kind": "order.created",
        "hanh_dong": "Lên đơn", "muc_do": {"ma": "nghiep_vu", "nhan": "Nghiệp vụ quan trọng"},
        "nhom": {"ma": "don_hang", "nhan": "Đơn hàng"}, "gom": None,
        "tac_nhan": {"loai": "ai", "nhan": "AI", "ten": None, "id": None},
        "tai_khoan": None, "doi_tuong": None, "hoi_thoai_id": None, "ref_id": None,
        "luot_id": None, "su_kien_goc": None, "che_do_ai": None, "muc_uy_quyen": None,
        "trang_thai": {"ma": "thanh_cong", "nhan": "Thành công"},
        "ket_qua": "mã đơn: DH1", "chi_tiet": {},
        "lien_ket": [
            {"loai": "don_hang", "id": "d1", "nhan": "Đơn DH1", "mo_duoc": True},
            {"loai": "hoi_thoai", "id": "h1", "nhan": "Hội thoại h1", "mo_duoc": False},
        ],
    }
    b.update(them)
    return b


def _ve(ds: list[dict]) -> dict:
    ra = subprocess.check_output(
        ["node", "-e", _NODE, str(SRC27), json.dumps(ds, ensure_ascii=False)])
    # Đọc bytes rồi giải UTF-8: `text=True` dùng mã trang của Windows (cp1258)
    # và vỡ ở chữ "Đ".
    return json.loads(ra.decode("utf-8"))


def test_dong_noi_ai_lam_gi_voi_ai_va_chi_mo_duoc_khi_co_quyen():
    kq = _ve([_ban_ghi(), _ban_ghi(
        id=8, kind="erp.ngat_mach", hanh_dong="ERP lỗi liên tiếp — tạm ngừng gọi",
        muc_do={"ma": "ky_thuat", "nhan": "Kỹ thuật"}, lien_ket=[],
        gom={"so_lan": 12, "id_cu_nhat": 1, "tu": "2026-11-25T08:00:00+07:00",
             "den": "2026-11-25T10:30:00+07:00"})])
    dong, gop = kq["dong"]
    # Đối tượng mở được là NÚT đi tới; không mở được chỉ là chữ.
    assert 'data-nk-lk="don_hang|d1"' in dong
    assert "data-nk-lk=\"hoi_thoai|h1\"" not in dong and "Hội thoại h1" in dong
    assert "Kết quả: mã đơn: DH1" in dong
    # Mã kỹ thuật không lên dòng — chỉ ở phần chi tiết kỹ thuật.
    assert "order.created" not in dong and "erp.ngat_mach" not in gop.split("data-nk-tung=")[0]
    assert "order.created" in kq["chi_tiet"] and "Dữ liệu kỹ thuật" in kq["chi_tiet"]
    # Dòng gộp: số lần, khoảng giờ, và lối xem từng lần.
    assert "×12" in gop and "12 lần" in gop and "data-nk-tung" in gop
    assert "Kỹ thuật" in gop


def test_mac_dinh_chi_nghiep_vu_va_gop_dong_lap():
    loc = _ve([_ban_ghi()])["loc"]
    assert "muc_do=nghiep_vu" in loc and "gom=true" in loc


def test_bo_loc_muc_khong_dung_lop_cua_cong_tac_ai():
    """
    `applyRuntime()` (01-nen.js) gỡ `is-on` và KHOÁ mọi `.modeswitch__opt`
    khi AI tắt — bộ lọc nhật ký mà mượn lớp ấy thì chết theo công tắc AI.
    """
    src = SRC27.read_text(encoding="utf-8")
    assert "modeswitch__opt" not in re.sub(r"<!--.*?-->", "", src, flags=re.S)
    assert "nk-hien__opt" in src
    nen = (ROOT / "dashboard" / "src" / "01-nen.js").read_text(encoding="utf-8")
    assert '$$(".modeswitch__opt")' in nen  # lý do của chốt trên vẫn còn


# ---------------------------------------------------------------- UX-17-04

_TAB_AI = ("ai-co-ban", "ai-tri-thuc", "ai-ky-nang", "ai-chinh-sach", "ai-phong-thu")


def test_moi_tab_cau_hinh_ai_co_mot_cau_dan_o_cung_cho():
    for tab in _TAB_AI:
        i = HTML.index(f'<section class="tabpanel" id="{tab}"')
        dau = HTML[i:i + 400]
        # Câu dẫn là con ĐẦU của tab, đứng TRƯỚC `.tab__goc` — mô-đun gắn
        # vào tab thay `.tab__goc`, không thay câu dẫn.
        assert re.search(r'role="tabpanel"[^>]*>\s*<p class="ai-tab__dan">[^<]{20,}</p>', dau), tab


def test_khoi_nha_cung_cap_nam_trong_panel_va_ky_nang_co_trang_thai_bang_chu():
    src23 = (ROOT / "dashboard" / "src" / "23-ai-co-ban.js").read_text(encoding="utf-8")
    assert '<section class="panel ai-ncc">' in src23
    src11 = (ROOT / "dashboard" / "src" / "11-ky-nang.js").read_text(encoding="utf-8")
    than = re.search(r"function veDongKyNang\(.*?\n\}\n", src11, re.S).group(0)
    assert '"Đang bật"' in than and '"Đang tắt"' in than
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")
    assert '.view[data-view="cauhinhai"] .pill' in css
    # Không còn khoảng cách viết cứng trong HTML của màn.
    i = HTML.index('<section class="view" data-view="cauhinhai">')
    j = HTML.index('<section class="view"', i + 20)
    assert 'style="margin-top' not in HTML[i:j]
