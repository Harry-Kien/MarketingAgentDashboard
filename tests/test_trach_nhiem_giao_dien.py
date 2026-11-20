"""
Màn hội thoại HIỆN được ai đã làm gì — canh bằng đọc mã nguồn dashboard.

Phần dữ liệu canh ở `test_trach_nhiem_hoi_thoai.py`. Ở đây canh rằng màn
hình thật sự dùng nó: một API trả tên người duyệt mà màn hình vẫn vẽ "Nhân
viên" là xanh giả — dữ liệu đúng, người trực vẫn mù.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "src"
HOI_THOAI = (SRC / "03-hoi-thoai.js").read_text(encoding="utf-8")
TRACH_NHIEM = (SRC / "19-trach-nhiem.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def test_tin_hien_ten_nguoi_gio_day_du_va_chip_sua_duyet():
    assert "tenTacGia(m, nguoiGui)" in HOI_THOAI
    # Giờ của tin đi qua `gioTin` (kèm ngày khi không phải hôm nay), không hhmm trần.
    assert "gioTin(m.created_at)" in HOI_THOAI and "hhmm(m.created_at)" not in HOI_THOAI
    assert "chipTrachNhiem(m)" in HOI_THOAI
    assert "Duyệt bởi" in TRACH_NHIEM and "Sửa bởi" in TRACH_NHIEM
    assert "tg.ten ? `Nhân viên ${tg.ten}`" in TRACH_NHIEM


def test_nut_vi_sao_ve_du_dau_vet():
    assert "nutViSao(m)" in HOI_THOAI and "veViSao(m)" in HOI_THOAI
    assert "Vì sao?" in TRACH_NHIEM
    than = TRACH_NHIEM[TRACH_NHIEM.index("function veViSao"):TRACH_NHIEM.index("function veNguoiGiu")]
    for truong in ("dv.ho_so", "tc.nguong", "dv.luoi", "dv.cong_cu", "dv.tri_thuc", "t.version"):
        assert truong in than, f"bảng Vì sao? thiếu {truong}"


def test_lich_su_ban_giao_va_giao_cho_nguoi_khac():
    assert "veLichSuPhanCong(c)" in HOI_THOAI
    assert "/lich-su-phan-cong" in TRACH_NHIEM and "/nguoi-nhan-duoc" in TRACH_NHIEM
    # Tên người đang giữ thay cho "Đồng nghiệp đang giữ" không tên.
    assert "veNguoiGiu(c, laCuaToi)" in HOI_THOAI
    assert "Đồng nghiệp đang giữ" not in HOI_THOAI
    # Nút giao chỉ hiện khi máy chủ nói giao được — không bày nút chỉ để nhận 403.
    assert re.search(r"giaoDuoc && c\.state !== \"resolved\" \? `<button[^`]*id=\"btn-giao\"", HOI_THOAI)
    assert "co_the_giao_khac" in TRACH_NHIEM
    assert "assignee_id: d.assignee_id, team_id: d.team_id || null" in TRACH_NHIEM


def test_bo_loc_hop_thu_co_du_bon_o_va_dung_tham_so_api():
    for ma in ("loc-kenh", "loc-giu", "loc-loai", "loc-sla"):
        assert f'id="{ma}"' in HTML
    for tham_so in ("account_id=", "chua_giao=true", "assignee_id=", "loai=", "qua_han_sla=true"):
        assert tham_so in TRACH_NHIEM
    assert "chuoiLocHopThu()" in HOI_THOAI


def test_moi_tep_nguon_duoi_1000_dong():
    for tep in SRC.glob("*.js"):
        assert len(tep.read_text(encoding="utf-8").splitlines()) <= 1000, tep.name
