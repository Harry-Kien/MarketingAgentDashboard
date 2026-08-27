"""
Sidecar Zalo phải cấp `imageMetadataGetter`, nếu không KHÔNG gửi được ảnh nào.

LỖI ĐÃ CÓ THẬT
--------------
Hàng đợi gửi tin có một job chết sau 8 lần thử:

    Missing `imageMetadataGetter`. Please provide it in the Zalo object options.

`zca-js` cần width/height/size để dựng khung xem trước bên Zalo. Trên trình
duyệt nó tự đọc từ thẻ <img>; ở Node không có DOM nên phải tự cấp.

Nghĩa là chức năng "agent gửi ảnh sản phẩm cho khách" hỏng 100% trên kênh
Zalo cá nhân — kênh chính ở Việt Nam. Khách hỏi "cho xem ảnh", agent gọi
công cụ, job vào hàng đợi, thử tám lần rồi chết. Trên dashboard không có gì
nói ra lý do; chỉ có khách là không nhận được gì.

File này canh ở phía Python vì `pytest` là thứ CI chạy mặc định. Phần kiểm
byte của bộ đọc nằm ở `connectors/zalo-personal-sidecar/test/`.
"""
from __future__ import annotations

from pathlib import Path

GOC = Path(__file__).resolve().parents[1] / "connectors" / "zalo-personal-sidecar"


def test_zalo_duoc_cap_image_metadata_getter():
    src = (GOC / "src" / "server.mjs").read_text(encoding="utf-8")
    khoi = src.split("new Zalo(", 1)[1].split("})", 1)[0]
    assert "imageMetadataGetter" in khoi, (
        "thiếu imageMetadataGetter — mọi lần gửi ảnh sẽ hỏng"
    )


def test_co_module_doc_kich_thuoc_anh():
    assert (GOC / "src" / "anh-metadata.mjs").exists()


def test_khong_them_phu_thuoc_npm_moi():
    """
    Sidecar này giữ phiên đăng nhập của chủ shop và đã mang rủi ro điều khoản
    Zalo. Thêm một phụ thuộc npm là thêm bề mặt chuỗi cung ứng cho đúng tiến
    trình nhạy cảm nhất — trong khi kích thước ảnh nằm ngay vài chục byte đầu
    file, đọc trực tiếp được.
    """
    import json

    pkg = json.loads((GOC / "package.json").read_text(encoding="utf-8"))
    assert set(pkg.get("dependencies", {})) == {"zca-js"}


def test_khong_doc_ca_file_vao_bo_nho():
    """
    Ảnh sản phẩm có thể vài megabyte, và lời gọi này nằm TRÊN đường trả lời
    khách. Mọi định dạng đều để kích thước trong vài chục byte đầu.
    """
    src = (GOC / "src" / "anh-metadata.mjs").read_text(encoding="utf-8")
    assert "readFile" not in src, "đang nạp cả file thay vì đọc phần đầu"
    assert "65536" in src


def test_khong_doc_duoc_thi_tra_null_chu_khong_doan():
    """
    Đoán 800x600 thì Zalo dựng khung xem trước sai tỉ lệ — ảnh hiện méo hoặc
    bị cắt. Hỏng theo kiểu khách nhìn thấy mà hệ thống không biết.
    """
    src = (GOC / "src" / "anh-metadata.mjs").read_text(encoding="utf-8")
    khoi = src.split("export async function layMetadataAnh", 1)[1]
    assert "return null" in khoi
    for doan_bua in ("800", "600", "1024,"):
        assert f"width: {doan_bua}" not in khoi


def test_jpeg_duyet_doan_chu_khong_dung_offset_cung():
    """
    Ảnh chụp từ điện thoại gần như luôn có EXIF trước SOF. Đọc offset cố định
    sẽ trúng giữa khối EXIF và trả ra số rác — đúng với loại ảnh khách hay
    gửi nhất.
    """
    src = (GOC / "src" / "anh-metadata.mjs").read_text(encoding="utf-8")
    khoi = src.split("function doJpeg", 1)[1].split("\n}", 1)[0]
    assert "while" in khoi, "không duyệt qua các đoạn JPEG"


def test_co_test_rieng_cho_bo_doc_byte():
    assert (GOC / "test" / "anh-metadata.test.mjs").exists()
