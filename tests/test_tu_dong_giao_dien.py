"""
Giao diện "Tin nhắn & Quy tắc tự động" (Cấu hình chung) — mục 7 bảng
"Check list công việc".

Hai thứ canh ở đây:
  · biểu mẫu quy tắc chia BA nhóm (Thông tin · Nếu · Thì), có đủ ô mà máy
    chủ hiểu, và nút Bật/Tắt không làm rơi cờ nào;
  · khung "/" + mã tắt trong ô nhắn tin THẬT SỰ chạy — chạy đoạn JS thật
    bằng node với DOM giả tối thiểu, không chỉ dò chữ trong mã.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS_QT = (ROOT / "dashboard" / "src" / "15-tu-dong.js").read_text(encoding="utf-8")
JS_CSKH = (ROOT / "dashboard" / "src" / "14-cskh.js").read_text(encoding="utf-8")


def _bieu_mau() -> str:
    a = HTML.index('<form id="qtForm"')
    return HTML[a:HTML.index("</form>", a)]


def test_bieu_mau_quy_tac_ba_nhom_dung_thu_tu_va_du_o():
    f = _bieu_mau()
    nhom = re.findall(r'data-qt-nhom="([a-z-]+)"', f)
    # KHI (sự kiện, cố định "khách nhắn tin") đứng trước NẾU – THÌ (UX-07-01).
    assert nhom == ["thong-tin", "khi", "neu", "thi"], nhom
    a, b = f.index('data-qt-nhom="neu"'), f.index('data-qt-nhom="thi"')
    thong_tin, neu, thi = f[:f.index('data-qt-nhom="khi"')], f[a:b], f[b:]
    for o in ("ten", "thu_tu", "bat", "dung_xet_sau"):
        assert f'name="{o}"' in thong_tin, o
    # Năm loại điều kiện của mục 7.3: kênh, từ khoá, giờ làm việc, tin đầu, nhãn.
    assert 'id="qtKenh"' in neu
    for o in ("chua_tu", "ngoai_gio", "lan_dau", "nhan_hoi_thoai_co", "nhan_hoi_thoai_khong",
              "nhan_khach_co", "nhan_khach_khong"):
        assert f'name="{o}"' in neu, o
    # Bốn loại hành động — điền nhiều ô là làm nhiều hành động (mục 7.4).
    for o in ("hd_gan_nhan_hoi_thoai", "hd_gan_nhan_khach", "hd_gui_mau", "hd_tao_viec",
              "hd_chuyen_nguoi", "cho_ai_tra_loi"):
        assert f'name="{o}"' in thi, o


def test_o_nhan_ghi_ro_nhan_hoi_thoai_hay_nhan_khach():
    """Mục 7.8: chữ trên ô phải nói LOẠI nhãn, và ô chỉ nạp đúng loại."""
    f = _bieu_mau()
    for ten, loai, chu in (("nhan_hoi_thoai_co", "hoi_thoai", "nhãn hội thoại"),
                           ("nhan_khach_co", "khach", "nhãn khách hàng"),
                           ("hd_gan_nhan_hoi_thoai", "hoi_thoai", "nhãn hội thoại"),
                           ("hd_gan_nhan_khach", "khach", "nhãn khách hàng")):
        i = f.index(f'name="{ten}"')
        o = f[f.rindex("<label", 0, i):f.index("</label>", i)]
        assert f'data-qt-nhan="{loai}"' in o and chu in o.lower(), ten


def test_gom_va_bat_tat_mang_du_hai_co():
    """
    Nút Bật/Tắt gửi lại CẢ quy tắc. Máy chủ giữ cờ khi thiếu khoá, nhưng
    giao diện vẫn gửi đủ — hai lớp, như mọi ràng buộc khác.
    """
    gom = JS_QT[JS_QT.index("function _gomQuyTac"):JS_QT.index("function _datQuyTac")]
    dat = JS_QT[JS_QT.index("function _datQuyTac"):JS_QT.index("function _xoaFormQuyTac")]
    bat = JS_QT[JS_QT.index("bat: !q.bat"):]
    for co in ("dung_xet_sau", "cho_ai_tra_loi"):
        assert co in gom and co in dat and co in bat[:200], co


def test_chinh_sach_hien_cho_nguoi_van_hanh():
    """Câu chính sách trên màn hình phải nói đúng ba điều khách sẽ gặp."""
    a = HTML.index('id="qtChinhSach"')
    doan = HTML[a:HTML.index("</p>", a)]
    for y in ("tối đa một tin tự động", "AI không trả lời chính tin đó", "nhóm"):
        assert y in doan, y


def test_dong_quy_tac_hien_dau_vet_chay():
    """Lần chạy cuối, lỗi cuối và nút lọc nhật ký theo quy tắc (dấu vết kiểm toán)."""
    for y in ("q.lan_chay_cuoi", "q.loi_cuoi", "data-qt-nhatky", "quy_tac_id="):
        assert y in JS_QT, y


_NODE_TEST = r"""
const elems = {};
function mkEl(tag) {
  return { tag, id: "", hidden: false, innerHTML: "", style: {}, attrs: {}, listeners: {},
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (this.listeners[t] ||= []).push(f); } };
}
globalThis.window = { innerHeight: 800, innerWidth: 1200 };
globalThis.Event = class { constructor(t) { this.type = t; } };
const o = { value: "", listeners: {},
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); },
  getBoundingClientRect() { return { left: 0, top: 500, width: 400 }; },
  focus() { document.activeElement = o; }, setSelectionRange() {},
  dispatchEvent(ev) { for (const f of this.listeners[ev.type] || []) f(ev); } };
globalThis.document = { activeElement: null, createElement: mkEl, addEventListener() {},
  body: { kids: [], appendChild(e) { this.kids.push(e); if (e.id) elems["#" + e.id] = e; },
          contains(e) { return e === o || this.kids.includes(e); } } };
globalThis.$ = (s) => elems[s] || null;
globalThis.esc = (s) => String(s);
const goiApi = [];
globalThis.api = async (url) => { goiApi.push(url); return { mau: [
  { ma_tat: "ship", noi_dung: "Dạ phí ship 30.000đ ạ." },
  { ma_tat: "shop", noi_dung: "Dạ shop mở cửa 8h ạ." }] }; };
const cho = (ms) => new Promise((r) => setTimeout(r, ms));
function kiem(dk, loi) { if (!dk) { console.log("HONG: " + loi); process.exit(1); } }
//MA_THAT//
(async () => {
  ganMauNhanh(o);
  o.value = "/sh"; o.dispatchEvent(new Event("input"));
  await cho(300);
  const k = $("#mau-nhanh");
  kiem(k && !k.hidden, "gõ /sh mà khung mẫu không mở");
  kiem(goiApi[0] === "/tra-loi-nhanh?q=sh", "không tìm mẫu theo mã đã gõ: " + goiApi[0]);
  kiem(k.innerHTML.includes("/ship") && k.innerHTML.includes("/shop"), "khung thiếu mẫu");
  let chan = false;
  const phim = (key) => ({ key, isComposing: false, keyCode: 0, preventDefault() {},
                           stopImmediatePropagation() { chan = true; } });
  for (const f of o.listeners.keydown) f(phim("ArrowDown"));
  for (const f of o.listeners.keydown) f(phim("Enter"));
  kiem(o.value === "Dạ shop mở cửa 8h ạ.", "Enter không chèn mẫu đang chọn: " + o.value);
  kiem(chan, "Enter chọn mẫu lọt xuống thành nút Gửi");
  kiem(k.hidden, "chèn xong khung không đóng");
  o.value = "chị ơi /sh"; o.dispatchEvent(new Event("input"));
  await cho(300);
  kiem(goiApi.length === 1, "'/' giữa câu cũng mở khung mẫu");
  console.log("OK");
})();
"""


def test_go_gach_cheo_chen_mau_tra_loi_nhanh(tmp_path):
    """
    Mục 7.5: nhân viên gõ "/" + mã tắt trong ô nhắn tin → khung gợi ý mẫu,
    ↓ chọn, Enter chèn (không gửi). Chạy ĐÚNG đoạn mã trong 14-cskh.js.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("máy không có node — phần kiểm tĩnh ở test_o_nhan_tin_gan_khung_mau vẫn chạy")
    ma = JS_CSKH[:JS_CSKH.index("async function loadMauNhanh")]
    tep = tmp_path / "go_gach_cheo.js"
    tep.write_text(_NODE_TEST.replace("//MA_THAT//", ma), encoding="utf-8")
    kq = subprocess.run([node, str(tep)], capture_output=True, text=True, encoding="utf-8",
                        timeout=60)
    assert kq.returncode == 0 and kq.stdout.strip().endswith("OK"), kq.stdout + kq.stderr


def test_o_nhan_tin_gan_khung_mau():
    """Khung chỉ chạy được khi ô nhắn tin của hội thoại GỌI `ganMauNhanh`."""
    src = (ROOT / "dashboard" / "src" / "03-hoi-thoai.js").read_text(encoding="utf-8")
    assert "ganMauNhanh(o_moi)" in src
    # Gắn TRƯỚC trình Enter-gửi: trình nghe gắn trước chạy trước, và nó chặn
    # (stopImmediatePropagation) để Enter chọn mẫu không thành Gửi.
    assert src.index("ganMauNhanh(o_moi)") < src.index('o_moi.addEventListener("keydown"')
