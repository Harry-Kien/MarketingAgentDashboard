"""Dashboard: panel Máy chủ MCP. Theo mẫu tests/test_dashboard_goi_ky_nang.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten):
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, ten
    return m.group(0)


def _khoi_form(id_form):
    i = HTML.index(f'id="{id_form}"')
    j = HTML.index("</form>", i)
    return HTML[i:j]


def test_panel_va_form_co_mat():
    assert 'id="mcp-ds"' in HTML
    assert 'id="mcpform"' in HTML
    assert 'id="mcp-kiem"' in HTML and 'id="mcp-them"' in HTML
    assert 'id="mcp-ketqua"' in HTML


def test_form_co_du_truong_va_canh_bao_host():
    khoi = _khoi_form("mcpform")
    assert 'name="ten"' in khoi and r'pattern="[a-z][a-z0-9_]{1,19}"' in khoi
    assert 'name="nhan"' in khoi
    assert 'name="dia_chi"' in khoi
    assert 'name="headers"' in khoi
    # Cảnh báo host cố ý không sửa được ở dashboard — cùng lý do với
    # KY_NANG_HOST_CHO_PHEP ở panel "Không chỉnh được ở đây".
    assert "KY_NANG_HOST_CHO_PHEP" in khoi and "MCP_MAY_CHU_NOI_BO" in khoi


def test_loadMcp_dung_api_va_esc():
    src = _than_ham("loadMcp")
    assert "/mcp" in src and "esc(" in src
    # Không được nội suy trần — mọi chuỗi máy chủ (khách tự đặt tên, nhãn,
    # host, mô tả công cụ) phải đi qua esc() trước khi vào innerHTML.
    # `sk.loi`, `b.ten`, `b.ly_do` cũng là chữ của MÁY CHỦ NGOÀI — câu lỗi
    # đồng bộ và lý do bỏ công cụ đều do nó viết, và cả ba đi thẳng vào
    # innerHTML. Chúng NGUY hơn `m.nhan` (người trong nhà gõ), không kém.
    for bieu_thuc in ("m.nhan", "m.host", "c.mo_ta", "c.ten", "sk.loi", "b.ten", "b.ly_do"):
        assert f"${{{bieu_thuc}}}" not in src, bieu_thuc


def test_loadMcp_co_du_nut_va_cong_tac():
    src = _than_ham("loadMcp")
    for thuoc_tinh in (
        "data-mcp-dongbo", "data-mcp-battat", "data-mcp-xoa",
        "data-mcp-cc", "data-mcp-ghi",
    ):
        assert thuoc_tinh in src, thuoc_tinh


def test_moi_row_trong_loadMcp_deu_co_flag():
    """
    Hàng công cụ đi PHẲNG, không lồng trong `.row__body` của hàng máy chủ —
    lồng `<div>` vào trong phần tử dòng (`<span>`) là sai kiểu HTML, và mỗi
    hàng `.row` độc lập vẫn phải có `.row__flag` làm con đầu tiên, nếu không
    nội dung tụt vào cột 3px và biến mất (tests/test_row_co_du_cot.py).
    """
    src = _than_ham("loadMcp")
    assert src.count('<div class="row">') >= 2
    assert 'class="row__flag' in src


def test_loadKyNang_goi_loadMcp_trong_try_va_tu_bao_loi():
    src = _than_ham("loadKyNang")
    assert "await loadMcp();" in src
    assert re.search(r"try\s*\{\s*await loadMcp\(\);\s*\}\s*catch", src), (
        "loadMcp() lỗi (vd vault chưa cấu hình) không được lan lên vòng làm "
        "mới 6 giây, và panel #mcp-ds phải NÓI ra là không tải được."
    )
    assert "Không tải được máy chủ MCP" in src


def test_plugin_row_uu_tien_p_mcp_truoc_p_goi():
    """
    Cột `goi` mang cả hai loại chủ: tên gói THẬT và "mcp:<tên máy>". Kiểm
    `p.goi` trước `p.mcp` thì huy hiệu hiện trần "gói mcp:<tên máy>" — đúng
    chuỗi kỹ thuật mà khoá `mcp` sinh ra để KHÔNG phải hiện.
    """
    src = _than_ham("loadKyNang")
    assert "p.mcp" in src
    nhan_mcp = '<b class="pill">MCP · ${esc(p.mcp)}</b>'
    nhan_goi = '<b class="pill">gói ${esc(p.goi)}</b>'
    assert nhan_mcp in src
    # Nhánh MCP phải đứng TRƯỚC nhánh gói trong chính khối `row__side` —
    # so trên hai nhãn thật (không phải trên "p.mcp"/"p.goi" trần, vì cụm
    # đó còn xuất hiện sớm hơn ở dòng "gọi 7 ngày ... gói ..." phía trên).
    assert src.index(nhan_mcp) < src.index(nhan_goi)
    # Vẫn giữ đúng nhánh cũ và thứ tự cũ mà test_dashboard_goi_ky_nang.py
    # canh: nhãn "gói ..." đứng trước nút Xoá.
    assert src.index(nhan_goi) < src.index("data-plugin-xoa")
    # Công cụ của máy chủ MCP cũng KHÔNG có nút Xoá riêng — máy chủ đồng bộ
    # sẽ tự đặt lại nó ở lần đồng bộ kế tiếp.
    assert src.index(nhan_mcp) < src.index("data-plugin-xoa")


def test_kiemMcp_va_themMcp_dung_duong_va_esc():
    kiem = _than_ham("kiemMcp")
    assert "/mcp/kiem" in kiem and "esc(" in kiem
    them = _than_ham("themMcp")
    assert '"/mcp"' in them and "esc(" in them
    assert "await loadKyNang();" in them


def test_docFormMcp_bat_dong_header_thieu_dau_hai_cham():
    src = _than_ham("docFormMcp")
    assert 'indexOf(":")' in src
    assert "return null" in src


def _khoi_listener(neo: str) -> str:
    """Khối `document.addEventListener(...)` chứa `neo`, cắt tới `});`."""
    j = JS.index(neo)
    i = JS.rindex("document.addEventListener(", 0, j)
    k = JS.index("\n});", j)
    return JS[i:k]


def test_themMcp_noi_that_khi_dong_bo_hong():
    """
    201 KHÔNG có nghĩa là đã nối được: máy chủ vẫn được tạo khi lần đồng bộ
    đầu hỏng (cố ý — một lần mạng chập không được làm mất bản ghi và bí mật
    vừa mã hoá). Báo "Đã nối" ở ca ấy là người vận hành bỏ đi làm việc khác
    còn agent thì thiếu công cụ; sai địa chỉ, sai header và DNS hỏng đều
    trông y hệt một máy chủ thật không có công cụ nào.
    """
    src = _than_ham("themMcp")
    assert "d.ok" in src
    assert "chưa nối được" in src
    assert "bấm Đồng bộ" in src
    assert "esc(d.loi" in src, "câu lỗi do máy chủ ngoài viết — phải qua esc()"
    # Nhánh hỏng phải là toast ĐỎ, không phải toast xanh như lúc thành công.
    assert re.search(r"chưa nối được[^\n]*, true\)", src), "toast nhánh hỏng phải là toast đỏ"


def test_change_hoan_tac_checkbox_khi_api_loi():
    """
    Hai công tắc này ĐỔI TRẠNG THÁI TRÌNH DUYỆT NGAY khi bấm, còn máy chủ
    thì có thể từ chối (trần 12 công cụ, máy chủ đang tắt, luật hai lần bấm
    cho quyền ghi). Không hoàn tác thì ô vuông hiện một trạng thái mà CSDL
    không có — nguy nhất ở ô "cho phép ghi": người vận hành tưởng đã bật.
    """
    src = _khoi_listener('[data-mcp-cc]')
    assert "[data-mcp-cc]" in src and "[data-mcp-ghi]" in src
    for hoan in ("cc.checked = !cc.checked", "gh.checked = !gh.checked"):
        assert hoan in src, hoan
        # và nó phải nằm TRONG `catch`, không phải chạy vô điều kiện
        assert re.search(
            r"catch\s*\([^)]*\)\s*\{[^{}]*" + re.escape(hoan), src
        ), f"{hoan} phải nằm trong catch"


def test_goi_y_ten_tu_nhan_va_khong_de_len_chu_nguoi_go():
    """
    Ô Tên đòi chữ thường không dấu, người vận hành nghĩ bằng tiếng Việt có
    dấu — không gợi ý thì lỗi "tên không hợp lệ" nổ sau khi đã gõ xong cả
    form, ở đúng ô máy tự điền được. Nhưng đè lên chữ người đang gõ còn tệ
    hơn, nên phải có cờ "đã gõ tay".
    """
    src = _than_ham("sinhMaMcp")
    assert "sinhMaPlugin" in src, "dùng lại phép bỏ dấu đã có, không chép lại"
    assert "20" in src, "tên máy chủ MCP chặt hơn tên plugin (20 vs 40)"
    i = JS.index("function sinhMaMcp")
    khoi = JS[i:JS.index("$(\"#mcp-kiem\")", i)]
    assert "mcpTenGoTay" in khoi
    assert "elements.nhan" in khoi and "elements.ten" in khoi
    # Form reset xong thì gợi ý sống lại — form trống là một lần nhập mới.
    assert "mcpTenGoTay = false" in _than_ham("themMcp")
