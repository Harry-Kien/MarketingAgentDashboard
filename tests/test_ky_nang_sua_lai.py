"""
Sửa lại một plugin đã lưu mà không phải gõ lại từ đầu.

VÌ SAO
------
`liet_ke()` trả tên, loại, mô tả và tên tham số — đủ để VẼ danh sách,
thiếu đúng thứ cần để SỬA: `cau_hinh`. Đổi một dòng phí ship vì thế là
gõ lại cả bảng, và người vận hành bỏ sau lần thứ hai. Một tính năng chỉ
tạo được mà không sửa được thì trên thực tế không ai dùng.

VÌ SAO LÀ MỘT Ô RIÊNG, KHÔNG PHẢI THÊM TRƯỜNG RỜI
-------------------------------------------------
`ban_mo_ta` là None cho công cụ THUỘC GÓI. `luu_plugin` đã từ chối sửa
những công cụ ấy (gói là nguồn sự thật, cài lại gói sẽ dựng đè). Trả None
để dashboard biết mà không hiện nút Sửa, thay vì hiện nút rồi để người
bấm xong mới ăn lỗi — cùng một luật, nói ở hai chỗ, giống mọi ràng buộc
khác trong repo này.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def chay(coro):
    return asyncio.run(coro)


BANG = {"đi làm": "Bôi hai đốt ngón tay.", "đi biển": "Chọn loại kháng nước."}

_THO = {
    "ten": "tra_cach_dung",
    "loai": "tra_bang",
    "mo_ta": "Tra cách dùng kem chống nắng theo hoàn cảnh. Không dùng cho câu hỏi về giá.",
    "tham_so": [{"ten": "khoa", "mo_ta": "Hoàn cảnh khách sẽ dùng", "bat_buoc": True}],
    "cau_hinh": {"bang": BANG},
}


@pytest.fixture
def kho_hai_plugin(monkeypatch):
    """Một plugin rời và một plugin thuộc gói, đọc từ CSDL giả."""
    from agent import db
    from agent.ky_nang import goi as g, kho_ky_nang

    thuoc_goi = dict(_THO, ten="cua_goi")

    async def fetch(sql, *a):
        if "ky_nang_cai_dat" in sql:
            return [
                {"ten": "tra_cach_dung", "bat": True, "ban_mo_ta": _THO, "goi": None},
                {"ten": "cua_goi", "bat": True, "ban_mo_ta": thuoc_goi,
                 "goi": "tu-van-chong-nang"},
            ]
        return []

    async def dem_gia():
        return {}

    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(g, "dem_goi_7_ngay", dem_gia)
    kho_ky_nang.xoa_dem()
    yield kho_ky_nang
    kho_ky_nang.xoa_dem()


def _plugin(ra: dict, ten: str) -> dict:
    return next(p for p in ra["plugin"] if p["ten"] == ten)


# --- Máy chủ ---------------------------------------------------------

def test_plugin_roi_tra_du_de_nap_lai_form(kho_hai_plugin):
    p = _plugin(chay(kho_hai_plugin.liet_ke()), "tra_cach_dung")
    bm = p["ban_mo_ta"]
    assert bm is not None, "thiếu ban_mo_ta thì sửa một dòng phải gõ lại cả bảng"
    assert bm["cau_hinh"]["bang"] == BANG
    assert bm["loai"] == "tra_bang"
    assert bm["tham_so"][0]["mo_ta"] == "Hoàn cảnh khách sẽ dùng", \
        "tham số phải có cả mô tả — form cần điền lại ô ấy"


def test_cong_cu_cua_goi_khong_sua_duoc_o_day(kho_hai_plugin):
    """
    `luu_plugin` từ chối những công cụ này. Trả None để dashboard không
    hiện nút Sửa, thay vì hiện rồi để người bấm xong mới ăn lỗi.
    """
    p = _plugin(chay(kho_hai_plugin.liet_ke()), "cua_goi")
    assert p["ban_mo_ta"] is None
    assert p["goi"] == "tu-van-chong-nang"


def test_ban_mo_ta_nap_lai_duoc_qua_bo_kiem(kho_hai_plugin):
    """Thứ trả về phải là thứ `luu_plugin` nhận lại được, không phải một
    hình dạng gần đúng."""
    from agent.ky_nang.ban_mo_ta import doc_ban_mo_ta

    bm = _plugin(chay(kho_hai_plugin.liet_ke()), "tra_cach_dung")["ban_mo_ta"]
    lai = doc_ban_mo_ta(dict(bm, ten="tra_cach_dung"))
    assert lai.cau_hinh["bang"] == BANG


def test_tham_so_cu_van_la_danh_sach_ten(kho_hai_plugin):
    """Cột phụ trong danh sách nối `tham_so` bằng dấu phẩy — đổi kiểu ở đây
    là dòng đó in ra `[object Object]`."""
    p = _plugin(chay(kho_hai_plugin.liet_ke()), "tra_cach_dung")
    assert p["tham_so"] == ["khoa"]


# --- Dashboard -------------------------------------------------------

def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_nut_sua_chi_hien_khi_sua_duoc():
    src = _than_ham("veDongKyNang")
    assert "data-plugin-sua" in src, "không có nút Sửa"
    i = src.index("data-plugin-sua")
    truoc = src[max(0, i - 260):i]
    assert "ban_mo_ta" in truoc, (
        "nút Sửa hiện vô điều kiện — công cụ thuộc gói bấm vào sẽ ăn lỗi "
        "từ luu_plugin, đúng thứ ban_mo_ta=None sinh ra để tránh"
    )


def test_co_ham_nap_plugin_vao_form():
    src = _than_ham("napPluginVaoForm")
    for o in ("nhan", "mo_ta", "loai"):
        assert o in src, o
    assert "datBang" in src, "bảng không được nạp lại thì vẫn phải gõ tay"
    assert "doiLoaiPlugin" in src, "không đổi loại thì hiện nhầm bộ ô"


def test_nap_form_khong_noi_suy_tran_chuoi_may_chu():
    """
    Bảng do người vận hành gõ, vẫn là chuỗi đi qua máy chủ rồi về DOM.

    Cấm NỘI SUY vào innerHTML, không cấm innerHTML: hàm này xoá ô kết quả
    bằng `innerHTML = ""`, và một test cấm cả chữ "innerHTML" bắt đỏ đúng
    dòng vô hại ấy. Đỏ giả thì người ta sửa test cho hết đỏ, và lần sau
    test không còn canh gì.
    """
    src = _than_ham("napPluginVaoForm")
    xau = re.findall(r"innerHTML\s*=\s*(.+)", src)
    for gan in xau:
        assert gan.strip().startswith(('""', "''")), \
            f"nội suy vào innerHTML: {gan.strip()[:60]}"


def test_sua_xong_luu_de_len_chinh_no():
    """
    Mã máy sinh từ TÊN. Sửa một plugin rồi lưu mà tên sinh ra khác đi thì
    nó thành plugin thứ hai, và bản cũ vẫn nằm đó với cấu hình cũ.
    """
    src = _than_ham("napPluginVaoForm")
    assert "capNhatMaPlugin" in src
    assert re.search(r"elements\.nhan\.value\s*=", src), "phải đặt lại ô tên"


def test_json_mau_khong_con_trong_form():
    """Chốt lại kết quả của lần trước: không ô nào bắt gõ JSON."""
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    form = re.search(r'<form id="pluginform".*?</form>', html, re.S).group(0)
    assert "JSON" not in form
    assert json  # giữ import cho các ca dùng sau
