"""
Màn hội thoại HIỆN được ai đã làm gì — canh bằng đọc mã nguồn dashboard.

Phần dữ liệu canh ở `test_trach_nhiem_hoi_thoai.py`. Ở đây canh rằng màn
hình thật sự dùng nó, theo quy ước hiển thị của chủ dự án (21.11.2026): một
dòng "Thời gian · Người gửi · Trạng thái"; thông tin kỹ thuật chỉ trong chi
tiết; độ tin cậy KHÔNG BAO GIỜ thành phần trăm; "Xem căn cứ" trên bản nháp
AI; lịch sử bàn giao trong panel "Chi tiết" của hội thoại.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "dashboard" / "src"
HOI_THOAI = (SRC / "03-hoi-thoai.js").read_text(encoding="utf-8")
TRACH_NHIEM = (SRC / "19-trach-nhiem.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")


def test_mot_dong_meta_thoi_gian_nguoi_gui_trang_thai():
    dong = HOI_THOAI[HOI_THOAI.index("const meta ="):].split(";", 1)[0]
    assert dong.strip() == ('const meta = [gioTin(m.created_at), who, trangThaiTin(m)]'
                            '.filter(Boolean).join(" · ")')
    # Nhãn người gửi theo quy ước.
    for nhan in ('agent: "AI Agent"', 'customer: "Khách hàng"', 'system: "Hệ thống"'):
        assert nhan in HOI_THOAI
    assert "`Nhân viên (${tg.ten})`" in TRACH_NHIEM
    assert "`Khách hàng (${tenKhach})`" in TRACH_NHIEM
    # Trạng thái lấy từ delivery_status thật, không bịa.
    for ma, nhan in (("sent", "Đã gửi"), ("delivered", "Đã nhận"), ("read", "Đã đọc")):
        assert f'{ma}: "{nhan}"' in TRACH_NHIEM


def test_khong_hien_ky_thuat_mac_dinh_va_khong_phan_tram_tin_cay():
    khoi_tin = HOI_THOAI[HOI_THOAI.index("const msgs = c.messages.map"):HOI_THOAI.index("const taken =")]
    for cam in ("m.confidence", "usd(m.cost", "m.latency_ms", "có nguồn tham chiếu"):
        assert cam not in khoi_tin, f"thông tin kỹ thuật lộ ra dòng meta: {cam}"
    for tep in SRC.glob("*.js"):
        chu = tep.read_text(encoding="utf-8")
        assert not re.search(r"pct\([^)]*(confidence|diem|tin_cay)", chu), \
            f"{tep.name} hiện độ tin cậy thành phần trăm"


def test_xem_can_cu_tren_ban_nhap_va_chi_tiet_tung_tin():
    assert "nutChiTietTin(m, draft)" in HOI_THOAI and "veChiTietTin(m, draft)" in HOI_THOAI
    assert 'draft ? "Xem căn cứ" : "Chi tiết"' in TRACH_NHIEM
    assert '"Có căn cứ"' in TRACH_NHIEM and '"Thiếu căn cứ"' in TRACH_NHIEM
    than = TRACH_NHIEM[TRACH_NHIEM.index("function veChiTietTin"):TRACH_NHIEM.index("function veChiTietHoiThoai")]
    for truong in ("dv.tri_thuc", "t.trich", "c.ket_qua", "dv.luoi", "dv.ho_so", "tg.duyet_boi", "tg.sua_boi"):
        assert truong in than, f"bảng chi tiết thiếu {truong}"
    # Người sửa/duyệt: chữ nhỏ cạnh dòng meta, không phải chip to.
    assert "ghiChuNguoiXuLy(m)" in HOI_THOAI and "msg__ghi" in TRACH_NHIEM


def test_lich_su_ban_giao_trong_panel_chi_tiet_va_giao_cho_nguoi_khac():
    assert 'id="btn-chitiet-ht"' in HOI_THOAI and "veChiTietHoiThoai(c, laCuaToi)" in HOI_THOAI
    assert "/lich-su-phan-cong" in TRACH_NHIEM and "/nguoi-nhan-duoc" in TRACH_NHIEM
    # Chỉ tải khi panel mở.
    than = TRACH_NHIEM[TRACH_NHIEM.index("function veChiTietHoiThoai"):]
    assert than.index("state.moChiTietHT !== id) return") < than.index("taiLichSuPhanCong(c)")
    # Người đang giữ có TÊN.
    assert "c.assigned_to_ten || \"Đồng nghiệp\"" in HOI_THOAI
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
