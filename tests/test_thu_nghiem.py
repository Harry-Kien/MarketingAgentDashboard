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


def test_mo_phong_khong_nhan_khop_yeu():
    """
    Mô phỏng phải dùng cùng một ngưỡng khớp như bản thật: < 0.5 là
    không chấp nhận. Trước: `diem <= 0` (bất kỳ điểm dương nào cũng được);
    sau: `diem < 0.5` (ít nhất 50% từ phải khớp).
    """
    # Kiểm tính trung thực của test: `_score` trên từ này phải thực sự < 0.5
    sp = {"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}
    # "mặt" = một từ không khớp gì ngoài "mặt" → 1/1 = 1.0 (quá cao!)
    # Dùng "nhẹ" thay: "nhẹ" khớp với "nhẹ" (nhưng là một phần của "dịu nhẹ"
    # hay là một từ riêng?) — thử xem, nếu vẫn >= 0.5 thì chọn query khác.
    test_queries = ["nhẹ", "kem", "chống nắng"]
    chosen_q = None
    for q in test_queries:
        score = tools._score(q, sp)
        if score < 0.5:
            chosen_q = q
            break
    assert chosen_q is not None, f"Không tìm được từ khiếp < 0.5; các từ {test_queries} có score >= 0.5"

    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": chosen_q, "so_luong": 1}],
    }, [sp]))
    assert kq["tao_duoc"] is False
    assert "không tìm thấy" in kq["ly_do"].lower()


def test_mo_phong_bat_sdt_va_dia_chi_nhu_that():
    """
    Mô phỏng phải kiểm phone >= 9 chữ số và address >= 12 ký tự,
    đúng như bản thật tại tools.py dòng 960, 962.
    """
    # Sdt quá ngắn: "123" = 3 chữ số (< 9)
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "123",
        "khach_dia_chi": "A",
        "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 1}],
    }, [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq["tao_duoc"] is False
    assert "số điện thoại hợp lệ" in kq.get("thieu_thong_tin", [])
    assert "địa chỉ đầy đủ" in kq.get("thieu_thong_tin", [])


# --------- bộ dò công cụ GHI, suy ra từ chính mã nguồn ---------
#
# VÌ SAO SUY RA CHỨ KHÔNG GÕ SẴN BỐN CÁI TÊN
# ------------------------------------------
# Bản trước của test này khẳng định `{"tao_don_hang", ...} <= ghi` với đúng
# bốn tên gõ tay hai lần — trong test và trong `CO_TAC_DUNG_PHU`. Nó luôn
# xanh, kể cả khi có công cụ ghi THỨ NĂM: tập gõ tay không lớn lên, nên
# phép so `<=` vẫn đúng. Một lưới canh việc quên thêm tên mà chính nó lại
# quên theo là xanh giả — thứ nguy hiểm hơn đỏ giả, vì không ai đi kiểm.
#
# Nay tập công cụ ghi được DẪN RA từ `tools.py`: nhánh nào của `_run_tool_that`
# (thân sandbox thật sự — `run_tool` chỉ còn là lớp bọc ghi số đo) gọi một
# hàm mà thân hàm ấy (hoặc thân hàm `_` nó gọi tiếp) có chạm `db.execute`,
# có chuỗi SQL ghi, có `giu_hang` hay `request_video` thì tên công cụ của
# nhánh đó PHẢI nằm trong `CO_TAC_DUNG_PHU`.
_SQL_GHI = ("INSERT INTO", "UPDATE ", "DELETE FROM")
_HAM_GHI = ("giu_hang", "request_video")


def _ten_ham_duoc_goi(nut: ast.AST) -> str | None:
    if not isinstance(nut, ast.Call):
        return None
    if isinstance(nut.func, ast.Name):
        return nut.func.id
    if isinstance(nut.func, ast.Attribute):
        return nut.func.attr
    return None


def _la_db_execute(nut: ast.AST) -> bool:
    return (isinstance(nut, ast.Attribute) and nut.attr == "execute"
            and isinstance(nut.value, ast.Name) and nut.value.id == "db")


def _co_dau_hieu_ghi(than: list[ast.stmt]) -> bool:
    for goc in than:
        for nut in ast.walk(goc):
            if _la_db_execute(nut):
                return True
            if (isinstance(nut, ast.Constant) and isinstance(nut.value, str)
                    and any(k in nut.value for k in _SQL_GHI)):
                return True
            if _ten_ham_duoc_goi(nut) in _HAM_GHI:
                return True
    return False


def _ham_module(cay: ast.Module) -> dict[str, ast.stmt]:
    return {n.name: n for n in cay.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _cong_cu_ghi_suy_ra(nguon: str) -> set[str]:
    cay = ast.parse(nguon)
    ham_mod = _ham_module(cay)
    run_tool = ham_mod["_run_tool_that"]

    cap: list[tuple[str, str]] = []          # (tên công cụ, tên hàm giúp việc)
    for nut in ast.walk(run_tool):
        if not isinstance(nut, ast.If):
            continue
        t = nut.test
        if not (isinstance(t, ast.Compare) and isinstance(t.left, ast.Name)
                and t.left.id == "name" and len(t.ops) == 1
                and isinstance(t.ops[0], ast.Eq) and t.comparators
                and isinstance(t.comparators[0], ast.Constant)):
            continue
        ten_cong_cu = str(t.comparators[0].value)
        for con in ast.walk(nut):
            if (isinstance(con, ast.Await) and isinstance(con.value, ast.Call)
                    and isinstance(con.value.func, ast.Name)):
                cap.append((ten_cong_cu, con.value.func.id))

    ghi: set[str] = set()
    for ten_cong_cu, ten_ham in cap:
        ham = ham_mod.get(ten_ham)
        if ham is None:
            continue
        than = list(ham.body)
        # Một tầng nữa: `_xin_huy_don` không tự ghi, nó gọi `_danh_dau_xin_huy`.
        # Không đi xuống một tầng là bỏ sót đúng hai công cụ ghi.
        for goc in list(ham.body):
            for con in ast.walk(goc):
                g = _ten_ham_duoc_goi(con)
                if g and g.startswith("_") and g in ham_mod and g != ten_ham:
                    than.extend(ham_mod[g].body)
        if _co_dau_hieu_ghi(than):
            ghi.add(ten_cong_cu)
    return ghi


def test_ast_moi_cong_cu_ghi_deu_di_qua_chot_sandbox():
    """
    Thêm một công cụ ghi mới mà quên đưa vào CO_TAC_DUNG_PHU thì phòng thử
    lặng lẽ ghi thật. Test này DẪN RA tập công cụ ghi từ `tools.py` rồi đòi
    nó nằm gọn trong `CO_TAC_DUNG_PHU`.
    """
    nguon = (ROOT / "agent" / "core" / "tools.py").read_text(encoding="utf-8")
    ghi = _cong_cu_ghi_suy_ra(nguon)

    # Bộ dò phải còn CHẠY ĐƯỢC. Đổi cách viết `run_tool` khiến nó không tìm
    # thấy gì thì phép so `<=` bên dưới vẫn xanh — đúng kiểu xanh giả mà
    # test này sinh ra để diệt.
    assert ghi, "bộ dò không tìm thấy công cụ ghi nào — _run_tool_that đã đổi hình, cập nhật test"
    assert "tao_don_hang" in ghi, "bộ dò bỏ sót tao_don_hang — nó hỏng, không phải mã hỏng"

    thieu = ghi - set(thu_nghiem.CO_TAC_DUNG_PHU)
    assert not thieu, (
        "Công cụ GHI chưa có trong thu_nghiem.CO_TAC_DUNG_PHU: "
        + ", ".join(sorted(thieu))
        + " — phòng thử sẽ ghi thật khi gọi tới nó."
    )
    assert "thu_nghiem.dang_thu.get()" in nguon.split("async def _run_tool_that", 1)[1]


def test_bo_do_ast_bat_duoc_cong_cu_ghi_moi():
    """
    Kiểm tính trung thực của bộ dò: cho nó một `run_tool` giả có công cụ ghi
    thứ năm thì nó phải thấy. Không có test này thì một bộ dò hỏng cũng im
    lặng trả về tập rỗng, và `test_ast...` ở trên thành lời hứa suông.
    """
    gia = (
        "async def _run_tool_that(name, args, conversation_id=None):\n"
        "    if name == 'xoa_don':\n"
        "        return await _xoa_don(args)\n"
        "    if name == 'xem_don':\n"
        "        return await _xem_don(args)\n"
        "\n"
        "async def _xoa_don(args):\n"
        "    return await db.execute('DELETE FROM orders WHERE id = $1', args)\n"
        "\n"
        "async def _xem_don(args):\n"
        "    return await db.fetchrow('SELECT 1 FROM orders')\n"
    )
    assert _cong_cu_ghi_suy_ra(gia) == {"xoa_don"}


def test_mo_phong_don_duoi_nguong_da_chot():
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 1}],
    }, [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq["tao_duoc"] is True and kq["trang_thai"] == "da_chot"
    assert "đã chốt" in kq["ghi_chu_cho_agent"]


def test_mo_phong_don_vuot_nguong_thi_cho_duyet(monkeypatch):
    """
    Đơn to trong phòng thử phải ra `cho_duyet` y như thật. Bỏ chốt này thì
    người vận hành không bao giờ thấy câu agent nói khi đơn vượt ngưỡng —
    và nói nhầm "đã chốt" cho một đơn chờ duyệt là hứa sai với khách.
    """
    from agent.config import settings

    monkeypatch.setattr(settings, "nguong_tu_chot_vnd", 1_000_000)
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 5}],
    }, [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq["tao_duoc"] is True and kq["trang_thai"] == "cho_duyet"
    assert "ghi_chu_cho_agent" in kq
    assert "CHỜ NHÂN VIÊN DUYỆT" in kq["ghi_chu_cho_agent"]
    assert kq["ghi_chu"].startswith("ĐANG THỬ")


def test_mo_phong_het_hang_thi_tu_choi():
    """Tồn kho ghi trong danh mục vẫn chặn — chỉ ERP là không được hỏi."""
    args = {
        "khach_da_xac_nhan": True, "khach_ten": "A", "khach_sdt": "0901234567",
        "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
        "items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 2}],
    }
    kq = chay(thu_nghiem.mo_phong("tao_don_hang", args, [
        {"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000, "ton_kho": 1}]))
    assert kq["tao_duoc"] is False and "chỉ còn 1" in kq["ly_do"]

    kq0 = chay(thu_nghiem.mo_phong("tao_don_hang", args, [
        {"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000, "ton_kho": 0}]))
    assert kq0["tao_duoc"] is False and "hết hàng" in kq0["ly_do"]

    # Không có trường `ton_kho` (danh mục mẫu) thì KHÔNG chặn.
    kq_khong = chay(thu_nghiem.mo_phong("tao_don_hang", args, [
        {"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]))
    assert kq_khong["tao_duoc"] is True
