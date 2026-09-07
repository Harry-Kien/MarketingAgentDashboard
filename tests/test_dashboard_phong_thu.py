"""Màn Phòng thử: có, gọi đúng API, esc mọi chuỗi máy chủ, không tự tải lại."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_rail_va_view_co_mat():
    assert 'data-view="phongthu"' in HTML
    assert HTML.count('data-view="phongthu"') >= 2  # nút rail + section


def test_goi_dung_api():
    src = _than_ham("hoiPhongThu")
    assert "/phong-thu/phien/" in src and "/hoi" in src and "method: \"POST\"" in src
    assert "ky_vong" in src


def test_ve_ben_trong_qua_esc():
    src = _than_ham("veBenTrongPhongThu")
    for ten in ("tra_loi", "escalate_reason", "nhan_luoi", "model", "sources"):
        assert f"${{{ten}" not in src and f"${{d.{ten}" not in src, ten
    assert "esc(" in src and 'class="pre"' in src
    assert "JSON.stringify" in src and "esc(JSON.stringify" in src
    # d.sources được gán vào biến cục bộ `nguon` trước khi join — kiểm bằng
    # tên biến thật đó (không phải "${d.sources", đã cấm ở trên) để bỏ esc()
    # quanh nguon.join(...) là test đỏ. Không dùng "${nguon" trần: chuỗi đó
    # khớp cả "${nguon.length" hợp lệ ở nhánh điều kiện, gây báo đỏ oan.
    assert "esc(nguon.join(" in src
    assert "${nguon.join(" not in src


def test_ve_chat_qua_esc():
    """
    Lời khách và lời agent cũng là chuỗi từ máy chủ. Câu thử chứa `<script>`
    mà nội suy trần thì phòng thử — màn hình chỉ quản trị mới vào được —
    thành đường chạy mã ngay trong dashboard.
    """
    src = _than_ham("veChatPhongThu")
    for ten in ("khach", "agent"):
        assert f"${{l.{ten}}}" not in src, ten
        assert f"esc(l.{ten})" in src, ten


def test_khong_tu_tai_lai_theo_vong_refresh():
    src = _than_ham("refresh")
    assert "phongthu" in src
    assert "loadPhongThu()" in src and "state.phongThuDaTai" in src


def test_goi_y_dien_cau_va_ky_vong():
    assert "data-goiy" in JS and "phongThuKyVong" in JS


def test_an_toan_nhap_lieu():
    src = _than_ham("hoiPhongThu")
    assert ".trim()" in src


def test_co_nut_xoa_phien_va_goi_delete():
    """Xoá phiên phải có nút thật VÀ phải gọi DELETE trên máy chủ — nếu
    không, phiên bỏ đi vẫn nằm trong RAM tiến trình tới khi hết TTL 2 giờ."""
    assert 'id="phongthu-xoa"' in HTML
    # "Xoá phiên" không phải tên hàm riêng (_than_ham bắt `function <tên>`),
    # nên lấy nguyên khối "phòng thử agent" bằng marker chú thích rồi tìm
    # trong đó — khối kế tiếp là "cài đặt API".
    dau = JS.index("/* ---------------- phòng thử agent")
    cuoi = JS.index("/* ----------------", dau + 10)
    khoi = JS[dau:cuoi]
    assert 'method: "DELETE"' in khoi


def test_hien_tung_vong():
    """Chi phí/độ trễ/token phải hiện theo TỪNG vòng gọi model, không chỉ
    tổng — d.vong là mảng, mỗi phần tử một vòng (agent/core/agent.py Reply.vong)."""
    assert "d.vong.map" in _than_ham("veBenTrongPhongThu")
