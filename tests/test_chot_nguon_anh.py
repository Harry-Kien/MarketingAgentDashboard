"""
Ảnh gửi cho khách phải là ảnh CHỤP THẬT sản phẩm.

VÌ SAO CÓ CHỐT NÀY
------------------
Trong `data/products/` từng có một thư mục chứa không phải ảnh sản phẩm mà
là BANNER QUẢNG CÁO: huy hiệu GMP / FDA / ISO 9001:2015, dòng "đạt chuẩn
xuất khẩu Hoa Kỳ" và "đảm bảo thành phần tuyệt đối an toàn cho người sử
dụng".

`gui_anh_san_pham` gửi thẳng tệp trong thư mục cho khách, nên gửi tấm đó đi
là phát ngôn quảng cáo có huy hiệu chứng nhận.

ĐIỂM MÙ KIẾN TRÚC MÀ NÓ LỘ RA
-----------------------------
Sáu lớp lưới trong `agent/core/agent.py` đều soi CHỮ agent viết ra. Tuyên
bố nằm trong ẢNH đi qua được cả sáu — không lớp nào thấy. Nên chốt phải
đặt ở đúng chỗ ảnh rời hệ thống, không đặt thêm vào lớp đọc chữ.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import tools  # noqa: E402


# =====================================================================
#  Luật thuần — không chạm đĩa
# =====================================================================

def test_anh_chup_that_luon_gui_duoc():
    assert tools._duoc_gui_anh("chup", du_lieu_mau=True)[0] is True
    assert tools._duoc_gui_anh("chup", du_lieu_mau=False)[0] is True


def test_anh_sinh_gui_duoc_khi_con_du_lieu_mau():
    """Bản demo thì ảnh minh hoạ dùng được — đó là mục đích nó sinh ra."""
    duoc, _ = tools._duoc_gui_anh("sinh", du_lieu_mau=True)
    assert duoc is True


def test_anh_sinh_BI_CHAN_khi_danh_muc_da_la_hang_that():
    """
    `agent/video/catalog_images.py` nói rõ: khi bán hàng thật, ảnh chụp
    thật phải thay vào, vì "khách nhận hàng khác với hình đã xem là chuyện
    không sửa được bằng lời xin lỗi".

    Dùng lại cờ `du_lieu_mau` nghĩa là ngày cửa hàng thay danh mục thật,
    ảnh sinh TỰ ĐỘNG ngừng đi ra — không ai phải nhớ bật chốt.
    """
    duoc, vi_sao = tools._duoc_gui_anh("sinh", du_lieu_mau=False)
    assert duoc is False
    assert "không phải ảnh chụp sản phẩm thật" in vi_sao


@pytest.mark.parametrize("nguon", ["chua_co", "quang_cao", "banner", "tai_ve"])
def test_moi_nguon_la_deu_bi_chan(nguon):
    """
    Danh sách CHO PHÉP, không phải danh sách cấm.

    Cấm theo danh sách thì nguồn mới nào cũng lọt cho tới khi có người nhớ
    thêm vào — và người ta chỉ nhớ sau khi đã gửi nhầm.
    """
    duoc, vi_sao = tools._duoc_gui_anh(nguon, du_lieu_mau=True)
    assert duoc is False
    assert vi_sao


def test_thieu_manifest_thi_khong_gui():
    """Không biết ảnh là gì thì không gửi. Đường lui im lặng ở đây là gửi bừa."""
    duoc, vi_sao = tools._duoc_gui_anh("", du_lieu_mau=True)
    assert duoc is False
    assert "Không biết ảnh này từ đâu" in vi_sao


# =====================================================================
#  Đọc manifest
# =====================================================================

def test_doc_dung_nguon_tu_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ANH_DIR", tmp_path)
    (tmp_path / "X-1").mkdir()
    (tmp_path / "X-1" / "manifest.json").write_text(
        json.dumps({"ma": "X-1", "nguon": "chup"}), encoding="utf-8"
    )
    assert tools._nguon_anh("X-1") == "chup"


def test_manifest_hong_thi_coi_nhu_khong_biet(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ANH_DIR", tmp_path)
    (tmp_path / "X-2").mkdir()
    (tmp_path / "X-2" / "manifest.json").write_text("{ hỏng", encoding="utf-8")
    assert tools._nguon_anh("X-2") == ""


def test_khong_co_manifest_thi_rong(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ANH_DIR", tmp_path)
    assert tools._nguon_anh("KHONG-CO") == ""


# =====================================================================
#  Qua cả công cụ
# =====================================================================

def _goi(ten: str) -> dict:
    return asyncio.run(
        tools.run_tool("gui_anh_san_pham", {"ten_san_pham": ten}, None)
    )


@pytest.fixture
def kho_anh(tmp_path, monkeypatch):
    """Danh mục và thư mục ảnh dựng sẵn — không chạm dữ liệu thật."""
    monkeypatch.setattr(tools, "ANH_DIR", tmp_path)

    def dat(nguon: str | None, du_lieu_mau: bool):
        thu_muc = tmp_path / "SP-1"
        thu_muc.mkdir(exist_ok=True)
        (thu_muc / "img_00.jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 100)
        if nguon is not None:
            (thu_muc / "manifest.json").write_text(
                json.dumps({"ma": "SP-1", "nguon": nguon}), encoding="utf-8"
            )

        async def _gia():
            return {
                "du_lieu_mau": du_lieu_mau,
                "san_pham": [{"ma": "SP-1", "ten": "Serum thử", "gia": 100}],
            }
        monkeypatch.setattr(tools, "_catalog_song", _gia)
    return dat


def test_cong_cu_gui_duoc_anh_chup(kho_anh):
    kho_anh("chup", du_lieu_mau=False)
    kq = _goi("Serum thử")
    assert kq["gui_duoc"] is True
    assert kq["duong_dan"].endswith("img_00.jpg")


def test_cong_cu_chan_banner_quang_cao(kho_anh):
    """
    Ca thật đã gặp: thư mục `BLA-FACE-SCRUB-120G` chứa banner serum có huy
    hiệu GMP/FDA/ISO. Manifest của nó ghi `nguon: "chua_co"` và `anh: []`.
    """
    kho_anh("chua_co", du_lieu_mau=True)
    kq = _goi("Serum thử")
    assert kq["gui_duoc"] is False
    assert "Mô tả bằng lời" in kq["ly_do"]


def test_cong_cu_chan_anh_sinh_khi_hang_that(kho_anh):
    kho_anh("sinh", du_lieu_mau=False)
    kq = _goi("Serum thử")
    assert kq["gui_duoc"] is False


def test_cong_cu_van_gui_anh_sinh_o_ban_demo(kho_anh):
    """Không được phá luồng demo — nếu phá thì người ta gỡ chốt."""
    kho_anh("sinh", du_lieu_mau=True)
    assert _goi("Serum thử")["gui_duoc"] is True


def test_cong_cu_chan_khi_thieu_manifest(kho_anh):
    kho_anh(None, du_lieu_mau=True)
    kq = _goi("Serum thử")
    assert kq["gui_duoc"] is False


# =====================================================================
#  Dữ liệu thật trong repo
# =====================================================================

def test_thu_muc_banner_that_khong_con_anh_nao():
    """
    `BLA-FACE-SCRUB-120G` phải KHÔNG có tệp ảnh nào. Chốt ở trên là lớp
    thứ hai; lớp thứ nhất là không để tấm ảnh đó nằm trong repo.
    """
    thu_muc = ROOT / "data" / "products" / "BLA-FACE-SCRUB-120G"
    if not thu_muc.is_dir():
        pytest.skip("chưa có thư mục này")
    assert list(thu_muc.glob("img_*.jpg")) == []
    m = json.loads((thu_muc / "manifest.json").read_text(encoding="utf-8"))
    assert m["nguon"] == "chua_co"
    assert m["anh"] == []


def test_moi_thu_muc_co_anh_deu_khai_nguon():
    """
    Ảnh không khai nguồn thì chốt chặn — đúng, nhưng nghĩa là ảnh đó vô
    dụng. Bắt ở đây để người thêm ảnh biết ngay, thay vì phát hiện lúc
    khách hỏi mà agent không gửi được.
    """
    goc = ROOT / "data" / "products"
    if not goc.is_dir():
        pytest.skip("chưa có thư mục ảnh")
    thieu = []
    for thu_muc in sorted(goc.iterdir()):
        if not thu_muc.is_dir() or not list(thu_muc.glob("img_*.jpg")):
            continue
        p = thu_muc / "manifest.json"
        if not p.is_file():
            thieu.append(thu_muc.name)
            continue
        if not json.loads(p.read_text(encoding="utf-8")).get("nguon"):
            thieu.append(thu_muc.name)
    assert not thieu, f"có ảnh mà manifest không khai nguồn: {thieu}"
