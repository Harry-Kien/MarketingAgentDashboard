"""Regression tests cho ĐỢT 6B.2: UX-06-02, UX-19-03 và UX-16-03."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from agent.core import agent as brain
from agent.core import thong_bao_noi_bo as tb

ROOT = Path(__file__).resolve().parents[1]
THANH_HT = (ROOT / "dashboard" / "src" / "03b-thanh-hoi-thoai.js").read_text(encoding="utf-8")
THONG_BAO_JS = (ROOT / "dashboard" / "src" / "19-thong-bao.js").read_text(encoding="utf-8")


def _chay_node(ma: str) -> dict | list:
    node = shutil.which("node")
    assert node, "Cần node để kiểm thử UI JS"
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_ux06_02_nut_tiep_quan_va_trang_thai_ro_rang():
    ma = (
        "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n"
        "const state = { toiId: 'u1', moHanhDong: null };\n"
        "function laNhom(c){return Number(c.thread_type||0)===1;}\n"
        + THANH_HT.split("document.addEventListener")[0]
        + """
        const ng = { toiId: 'u1', quyen: new Set(['hoi_thoai.nhan', 'hoi_thoai.xem_tat_ca']), giaoDuoc: true };
        const truoc = veHanhDongXuLy({id:'c1', mode:'auto', status:'auto'}, hanhDongXuLy({id:'c1', mode:'auto', status:'auto'}, ng));
        const cho = veHanhDongXuLy({id:'c2', mode:'human', status:'escalated'}, hanhDongXuLy({id:'c2', mode:'human', status:'escalated'}, ng));
        const sau = veHanhDongXuLy({id:'c3', mode:'human', status:'escalated', assigned_to:'u1'}, hanhDongXuLy({id:'c3', mode:'human', status:'escalated', assigned_to:'u1'}, ng));
        console.log(JSON.stringify({ truoc, cho, sau, lopTiepQuan: HANH_DONG_HT.tiepQuan.lop }));
        """
    )
    res = _chay_node(ma)
    assert res["lopTiepQuan"] == "btn--primary"
    assert "btn--halt" not in res["truoc"]
    assert "AI đang xử lý" in res["truoc"]
    assert "hd-them__goiy" in res["truoc"]
    assert "Chờ nhân viên tiếp quản" in res["cho"]
    assert "Bạn đang tiếp quản · AI đã tắt" in res["sau"]


def test_ux19_03_chuan_hoa_thong_bao_khong_lo_ma_ky_thuat():
    loi_tool = tb.chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", "Model dừng bất thường (tool_calls)")
    assert "tool_calls" not in loi_tool
    assert "lỗi kỹ thuật" in loi_tool.lower()

    thieu_tin_cay = tb.chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", "Độ tin cậy thấp (0.32)")
    assert "0.32" not in thieu_tin_cay
    assert "căn cứ" in thieu_tin_cay.lower()

    cat_do_dai = tb.chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", "Model dừng bất thường (MAX_TOKENS)")
    assert "MAX_TOKENS" not in cat_do_dai
    assert "độ dài" in cat_do_dai.lower()

    an_toan = tb.chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", "Nội dung cần nhân viên kiểm tra (SAFETY)")
    assert "SAFETY" not in an_toan

    assert set(tb.LOAI) == set(tb._HUONG_DAN)


def test_ux19_03_frontend_lam_sach_va_huong_dan():
    ma = (
        "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n"
        "function clock(x){return '21:00';}\n"
        "function $(s){return null;}\n"
        + THONG_BAO_JS.split('$("#chuongNut")?.addEventListener')[0]
        + """
        const h1 = dongThongBao({id:'1', loai:'ai_chuyen_giao', nhan_loai:'AI chuyển giao', tieu_de:'AI chuyển hội thoại', noi_dung:'Model dừng bất thường (tool_calls)', tao_luc:'2026-11-25T21:00:00Z', da_doc:false});
        const h2 = dongThongBao({id:'2', loai:'ai_chuyen_giao', nhan_loai:'AI chuyển giao', tieu_de:'AI chuyển hội thoại', noi_dung:'Độ tin cậy thấp (0.25)', tao_luc:'2026-11-25T21:00:00Z', da_doc:true});
        console.log(JSON.stringify({ h1, h2 }));
        """
    )
    res = _chay_node(ma)
    assert "tool_calls" not in res["h1"]
    assert "lỗi kỹ thuật" in res["h1"].lower()
    assert "chuong__huongdan" in res["h1"]
    assert "0.25" not in res["h2"]
    assert "căn cứ" in res["h2"].lower()


def test_ux16_03_phan_biet_loai_loi_ai():
    assert "lỗi kỹ thuật" in brain._mo_ta_ly_do_dung("tool_calls").lower()
    assert "vượt giới hạn độ dài" in brain._mo_ta_ly_do_dung("MAX_TOKENS").lower()
    assert "nhân viên kiểm tra" in brain._mo_ta_ly_do_dung("SAFETY").lower()
