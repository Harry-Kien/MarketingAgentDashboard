"""Regression tests cho 3 cải tiến khôi phục trên baseline e0436d1:
1. Che thông tin xác thực (dấu chấm + Đã lưu + Chỉnh sửa/Hủy chỉnh sửa).
2. Lưu vào Dashboard cho trường .env không nhạy cảm (Kết nối & Tích hợp + Cấu hình AI).
3. Split Button xử lý hội thoại, giữ nguyên UX hội thoại nhóm (UX-09-01).
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS03B = (ROOT / "dashboard" / "src" / "03b-thanh-hoi-thoai.js").read_text(encoding="utf-8")
JS22 = (ROOT / "dashboard" / "src" / "22-ket-noi-tich-hop.js").read_text(encoding="utf-8")
JS23 = (ROOT / "dashboard" / "src" / "23-ai-co-ban.js").read_text(encoding="utf-8")
CSS = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")


def _node(ma: str):
    node = shutil.which("node")
    assert node, "Cần node"
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_che_bi_mat_va_luu_env_ket_noi_va_ai():
    assert "data-kntt-sua-bi-mat" in JS22 and "data-kntt-huy-bi-mat" in JS22
    assert "o.disabled || o.closest" in JS22
    assert "data-kntt-luu-env" in JS22 and "b.dataset.knttLuuEnv" in JS22
    # Giữ nguyên hợp nhất Kết nối & Tích hợp từ origin/main (e1a1434)
    assert "knttDvMo" in JS22 and "hoiHop({" in JS22
    # Cấu hình AI dùng chung knttDongNguon và giữ .panel.ai-ncc (UX-17-04)
    assert "knttDongNguon(" in JS23 and 'class="panel ai-ncc"' in JS23


def test_split_button_hoi_thoai_va_bao_toan_ux09_01():
    assert ".hd-split {" in CSS and ".hd-split__mui" in CSS
    ma = (
        "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n"
        "const state = { toiId: 'u1', moHanhDong: null, moChiTietHT: null, toiQuyen: new Set(['hoi_thoai.nhan', 'hoi_thoai.xem_tat_ca']) };\n"
        "function laNhom(c){return Number(c.thread_type||0)===1;}\n"
        "function nhanHoiThoaiHtml(){return '';}\n"
        + JS03B.split("document.addEventListener")[0]
        + """
        const ql = { toiId: 'u1', quyen: new Set(['hoi_thoai.nhan', 'hoi_thoai.xem_tat_ca']), giaoDuoc: true };
        const nv = { toiId: 'u1', quyen: new Set(['hoi_thoai.nhan']), giaoDuoc: false };
        const autoQl = veHanhDongXuLy({ id: 'c1', mode: 'auto', status: 'auto' }, hanhDongXuLy({ id: 'c1', mode: 'auto', status: 'auto' }, ql));
        const cuaToi = veHanhDongXuLy({ id: 'c2', mode: 'human', status: 'escalated', assigned_to: 'u1' }, hanhDongXuLy({ id: 'c2', mode: 'human', status: 'escalated', assigned_to: 'u1' }, ql));
        const resolved = veHanhDongXuLy({ id: 'c3', state: 'resolved', mode: 'auto', status: 'auto' }, hanhDongXuLy({ id: 'c3', state: 'resolved', mode: 'auto', status: 'auto' }, ql));
        const khacNv = veHanhDongXuLy({ id: 'c4', mode: 'human', status: 'escalated', assigned_to: 'u2', assigned_to_ten: 'An' }, hanhDongXuLy({ id: 'c4', mode: 'human', status: 'escalated', assigned_to: 'u2', assigned_to_ten: 'An' }, nv));
        const nhomHeader = veThanhThongTin({ id: 'c5', customer_name: 'Nhóm Sỉ', thread_type: 1, mode: 'auto', status: 'auto' }, hanhDongXuLy({ id: 'c5', thread_type: 1, mode: 'auto', status: 'auto' }, ql));
        console.log(JSON.stringify({ autoQl, cuaToi, resolved, khacNv, nhomHeader }));
        """
    )
    r = _node(ma)
    assert 'class="hd-split"' in r["autoQl"] and "Tiếp quản" in r["autoQl"] and "Kết thúc tiếp quản" not in r["autoQl"]
    assert 'class="hd-split"' in r["cuaToi"] and "Đã giải quyết" in r["cuaToi"] and "Kết thúc tiếp quản" in r["cuaToi"]
    assert 'class="hd-split"' not in r["resolved"] and "Mở lại" in r["resolved"]
    assert 'class="hd-split"' not in r["khacNv"] and "An đang giữ" in r["khacNv"]
    # UX-09-01: không lặp dấu Nhóm trên tiêu đề hội thoại
    assert "nhomBadge" not in JS03B.split("function veThanhThongTin")[1].split("document.addEventListener")[0]
    assert 'id="open-contact"' not in r["nhomHeader"]
