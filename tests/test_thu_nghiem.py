# tests/test_thu_nghiem.py
"""
Chế độ thử: bốn công cụ có tác dụng phụ phải bị mô phỏng, không chạm gì.

Phòng thử gọi thẳng `respond()`; nếu `tao_don_hang` trong đó chạy thật thì
mỗi câu thử là một đơn thật nằm trong Postgres và ERP. Chốt nằm ở `run_tool`
— chỗ duy nhất mọi công cụ đi qua — và được canh bằng AST, không bằng lời
hứa.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from agent.core import thu_nghiem, tools

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _sach():
    thu_nghiem.xoa_dem()
    yield
    thu_nghiem.xoa_dem()


def chay(coro):
    return asyncio.run(coro)


def test_mac_dinh_khong_thu():
    assert thu_nghiem.dang_thu.get() is False
    with thu_nghiem.bat_thu():
        assert thu_nghiem.dang_thu.get() is True
    assert thu_nghiem.dang_thu.get() is False


def _no(*a, **k):
    raise AssertionError("sandbox KHÔNG được chạm CSDL")


async def _no_async(*a, **k):
    raise AssertionError("sandbox KHÔNG được chạm CSDL")


@pytest.mark.parametrize("ten", sorted(thu_nghiem.CO_TAC_DUNG_PHU))
def test_trong_sandbox_khong_cham_csdl(monkeypatch, ten):
    from agent import db

    monkeypatch.setattr(db, "execute", _no_async)
    monkeypatch.setattr(db, "fetch", _no_async)
    monkeypatch.setattr(db, "fetchrow", _no_async)
    monkeypatch.setattr(tools, "_catalog_song", lambda: _catalog_gia())
    args = {
        "tao_don_hang": {
            "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
            "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
            "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 2}],
        },
        "tao_video": {"tieu_de": "Thử", "yeu_cau": "giới thiệu", "loai": "explainer"},
        "xin_huy_don": {"ma_don": "DH-1", "ly_do": "đổi ý"},
        "xin_doi_tra": {"ma_don": "DH-1", "ly_do": "lỗi", "loai": "doi"},
    }[ten]
    with thu_nghiem.bat_thu():
        kq = chay(tools.run_tool(ten, args, conversation_id=None))
    assert kq.get("thu_nghiem") is True
    assert str(kq.get("ghi_chu", "")).startswith("ĐANG THỬ")


async def _catalog_gia():
    return {"san_pham": [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}],
            "don_hang": []}


def test_mo_phong_don_hang_giu_hinh_dang_ban_that():
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 2}],
    }, [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq["tao_duoc"] is True and kq["ma_don"].startswith("THU-")
    assert kq["tong_tien"] == 490000


def test_mo_phong_don_hang_van_bat_xac_nhan_va_ma_hang():
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {"items": []}, []))
    assert kq["tao_duoc"] is False and "xác nhận" in kq["ly_do"]
    kq2 = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": "không có", "so_luong": 1}],
    }, [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq2["tao_duoc"] is False and "không tìm thấy" in kq2["ly_do"].lower()


def test_ngoai_sandbox_run_tool_khong_re_nhanh(monkeypatch):
    # Chữ ký khớp `_tao_video(args, products, conversation_id)` thật —
    # ghi tên qua closure vì tham số không mang tên công cụ.
    goi = []

    async def gia(args, products, conversation_id):
        goi.append("tao_video")
        return {"dat_duoc": True}

    monkeypatch.setattr(tools, "_catalog_song", lambda: _catalog_gia())
    monkeypatch.setattr(tools, "_tao_video", gia)
    kq = chay(tools.run_tool("tao_video", {"tieu_de": "x"}, conversation_id=None))
    assert goi == ["tao_video"] and "thu_nghiem" not in kq


def test_so_chi_phi_thu_cong_don_va_tran(monkeypatch):
    from agent import runtime

    monkeypatch.setitem(runtime.STATE, "phong_thu_tran_ngay_usd", 0.5)
    thu_nghiem.ghi_nhan(0.2)
    thu_nghiem.ghi_nhan(0.2)
    assert thu_nghiem.da_tieu_hom_nay() == pytest.approx(0.4)
    con, da, tran = thu_nghiem.con_tran()
    assert con and tran == 0.5
    thu_nghiem.ghi_nhan(0.2)
    assert thu_nghiem.con_tran()[0] is False


def test_sang_ngay_moi_thi_ve_0(monkeypatch):
    thu_nghiem.ghi_nhan(0.3)
    monkeypatch.setattr(thu_nghiem, "_hom_nay", lambda: "2099-01-01")
    assert thu_nghiem.da_tieu_hom_nay() == 0.0


def test_ast_moi_cong_cu_ghi_deu_di_qua_chot_sandbox():
    """
    Thêm một công cụ ghi mới mà quên đưa vào CO_TAC_DUNG_PHU thì phòng thử
    lặng lẽ ghi thật. Test này đọc `run_tool`: mọi tên công cụ có nhánh
    `name == "..."` gọi hàm bắt đầu bằng `_tao_`/`_danh_dau_` phải nằm
    trong tập.
    """
    nguon = (ROOT / "agent" / "core" / "tools.py").read_text(encoding="utf-8")
    cay = ast.parse(nguon)
    ham = next(n for n in ast.walk(cay)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_tool")
    ghi: set[str] = set()
    for nut in ast.walk(ham):
        if (isinstance(nut, ast.Compare) and isinstance(nut.left, ast.Name)
                and nut.left.id == "name" and nut.comparators
                and isinstance(nut.comparators[0], ast.Constant)):
            ten = str(nut.comparators[0].value)
            ghi.add(ten)
    goi_ham = {
        n.func.id for n in ast.walk(ham)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and (n.func.id.startswith("_tao_") or n.func.id.startswith("_danh_dau_"))
    }
    assert goi_ham, "không thấy lời gọi hàm ghi nào trong run_tool — test cần cập nhật"
    assert {"tao_don_hang", "tao_video", "xin_huy_don", "xin_doi_tra"} <= ghi
    assert {"tao_don_hang", "tao_video", "xin_huy_don", "xin_doi_tra"} <= thu_nghiem.CO_TAC_DUNG_PHU
    assert "thu_nghiem.dang_thu.get()" in nguon.split("async def run_tool", 1)[1]
