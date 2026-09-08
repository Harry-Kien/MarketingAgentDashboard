"""
Màn Kỹ năng: MỘT danh sách, MỘT điểm thêm, dù có bốn nguồn công cụ.

VÌ SAO GỘP
----------
Trước đợt này màn Kỹ năng có năm khối và HAI đường thêm kỹ năng đặt cạnh
nhau, trông ngang hàng, không chỗ nào nói khi nào dùng đường nào. Task 6
của kế hoạch MCP sẽ chèn thêm hai khối nữa, thành bảy khối và ba đường.

Người vận hành hỏi ba câu, và giao diện phải trả lời đúng ba chỗ:

  1. agent đang làm được gì?      → một danh sách gộp cả bốn nguồn
  2. thêm cái mới thế nào?        → một nút, ba lựa chọn có giải thích
  3. nguồn tôi đã nối ra sao?     → một danh sách gói và máy chủ MCP

Trần 12 suất cắm thêm đếm chung plugin rời, công cụ của gói và công cụ
MCP. Ba danh sách rời thì không chỗ nào hiện được tổng, và người vận hành
phải tự cộng để biết còn mấy suất — đúng lúc họ sắp chạm trần.

CÁI GÌ KHÔNG ĐỔI
----------------
Mọi id form (`#pluginform`, `#goiform`) và mọi ràng buộc an toàn giữ
nguyên. Đây thuần là sắp xếp lại chỗ; không API nào đổi, không phép kiểm
nào lỏng đi.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _man_ky_nang() -> str:
    i = HTML.index('<section class="view" data-view="kynang">')
    j = HTML.index('<section class="view" data-view=', i + 40)
    return HTML[i:j]


def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


# --- Ba khối, không phải bảy -----------------------------------------

def test_chi_con_ba_khoi():
    tieu_de = re.findall(r'<h2 class="panel__head">\s*([^<\n]+)', _man_ky_nang())
    assert len(tieu_de) == 3, f"đang có {len(tieu_de)} khối: {tieu_de}"


def test_mot_danh_sach_ky_nang_duy_nhat():
    man = _man_ky_nang()
    assert 'id="kynang-tatca"' in man
    for cu in ('id="kynang-cosan"', 'id="kynang-plugin"'):
        assert cu not in man, f"{cu} vẫn còn — vẫn là hai danh sách rời"


def test_mot_diem_them_duy_nhat():
    man = _man_ky_nang()
    chon = set(re.findall(r'data-them="([a-z]+)"', man))
    assert chon == {"bang", "goi", "mcp"}, chon
    o = set(re.findall(r'data-them-o="([a-z]+)"', man))
    assert o == chon, "mỗi lựa chọn phải có đúng một khung form"


def test_moi_lua_chon_noi_ro_khi_nao_dung():
    """
    Ba đường đặt cạnh nhau mà không nói khi nào dùng đường nào là lý do
    người vận hành đứng lại ở đây. Giải thích phải nằm trong MÃ, không
    phải trong đầu người đã đọc tài liệu.
    """
    m = re.search(r"const THEM_CACH = \{.*?\n\};\n", JS, re.S)
    assert m, "không thấy bảng THEM_CACH"
    khoi = m.group(0)
    for khoa in ("bang", "goi", "mcp"):
        assert re.search(khoa + r":\s*\{", khoi), khoa
    # Đếm độ dài thật, không chỉ đếm sự có mặt của chữ "giai_thich": một ô
    # rỗng vẫn qua được phép kiểm có-hay-không, và khi ấy giao diện im lặng
    # đúng ở chỗ nó sinh ra để nói.
    for gt in re.findall(r'giai_thich:\s*"([^"]*)"', khoi):
        assert len(gt) >= 60, f"giải thích quá ngắn: {gt!r}"
    assert len(re.findall(r"giai_thich:", khoi)) == 3
    assert "them-giaithich" in _than_ham("doiCachThem"), "giải thích không được vẽ ra"


# --- Chỗ để sẵn cho Task 6 của kế hoạch MCP --------------------------

def test_co_cho_san_cho_mcp():
    """
    Task 6 chèn form và danh sách máy chủ MCP. Để sẵn hai chỗ rỗng thì
    việc đó là điền vào chỗ trống, không phải thêm hai khối rời nữa.
    """
    man = _man_ky_nang()
    assert 'id="them-mcp"' in man, "thiếu chỗ cho form máy chủ MCP"
    assert 'id="nguon-mcp"' in man, "thiếu chỗ cho danh sách máy chủ MCP"


# --- Form cũ giữ nguyên id -------------------------------------------

def test_hai_form_cu_van_o_nguyen_id():
    man = _man_ky_nang()
    for i in ('id="pluginform"', 'id="goiform"', 'id="goi-ds"',
              'id="goi-kiem"', 'id="goi-cai"', 'id="plugin-thu"'):
        assert i in man, f"{i} mất — test cũ và kế hoạch MCP đều bám vào nó"


# --- Danh sách gộp phải nói rõ nguồn ---------------------------------

def test_moi_dong_mang_huy_hieu_nguon():
    """
    Gộp bốn nguồn vào một danh sách mà không nói dòng nào từ đâu thì người
    vận hành mất khả năng biết phải đi sửa ở chỗ nào: plugin rời sửa tại
    chỗ, công cụ của gói phải cài lại gói, công cụ MCP phải đồng bộ lại.
    """
    src = _than_ham("veDongKyNang")
    for nguon in ("viet_san", "mcp", "goi"):
        assert nguon in src, nguon
    assert "esc(" in src


def test_dem_suat_cam_them_tren_dau_danh_sach():
    """Trần 12 đếm chung ba nguồn cắm thêm. Không hiện tổng thì người vận
    hành chỉ biết mình chạm trần lúc bị từ chối."""
    src = _than_ham("loadKyNang")
    assert "plugin_toi_da" in src
    assert "kynang-dem" in src


def test_loc_theo_nguon():
    man = _man_ky_nang()
    loc = set(re.findall(r'data-loc-nguon="([a-z-]+)"', man))
    assert {"tat-ca", "viet-san", "tu-tao", "goi", "mcp"} <= loc, loc


# --- Không mất chức năng cũ ------------------------------------------

def test_van_bat_tat_duoc_ky_nang_viet_san():
    src = _than_ham("veDongKyNang")
    assert "data-kynang" in src, "mất công tắc bật/tắt kỹ năng viết sẵn"


def test_van_sua_va_xoa_duoc_plugin_roi():
    src = _than_ham("veDongKyNang")
    assert "data-plugin-sua" in src and "data-plugin-xoa" in src


def test_van_hien_khoa_khach_hoi_ma_bang_chua_co():
    src = _than_ham("veDongKyNang")
    assert "khong_khop" in src


def test_cong_cu_cua_goi_khong_co_nut_xoa_rieng():
    """Máy chủ từ chối xoá riêng nó; một nút luôn báo lỗi là nút dạy người
    ta bỏ qua thông báo lỗi."""
    src = _than_ham("veDongKyNang")
    i = src.index("data-plugin-xoa")
    truoc = src[:i]
    assert 'nguon === "tu_tao"' in truoc, (
        "nút Xoá không nằm sau nhánh chỉ-dành-cho-tự-tạo — công cụ của gói "
        "và của MCP sẽ có một nút mà máy chủ luôn từ chối"
    )
    # Nhánh cuối phải trả chuỗi rỗng, không phải rơi xuống nút xoá.
    assert re.search(r':\s*""\s*;', src), "thiếu nhánh 'không nút nào' cho gói/MCP"
