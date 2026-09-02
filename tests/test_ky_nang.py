"""
Sổ đăng ký kỹ năng: không lệch với `TOOLS`, và không tắt được đường lui.

Hai khẳng định quan trọng nhất trong tệp này:

  1. Mọi công cụ trong `TOOLS` có khai báo, và ngược lại — thêm công cụ mà
     quên khai báo là đỏ ngay, không phải phát hiện lúc vận hành.
  2. `chuyen_nhan_vien` không tắt được bằng bất kỳ đường nào.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib

import pytest

from agent.core import tools
from agent.ky_nang import so_dang_ky
from agent.ky_nang.ban_mo_ta import LoiBanMoTa
from agent.ky_nang.so_dang_ky import (
    KHONG_TAT_DUOC,
    MUC_RUI_RO,
    NHOM,
    SO_DANG_KY,
    khai_bao,
    ten_ky_nang_co_san,
)

GOC = pathlib.Path(__file__).resolve().parent.parent


def test_moi_cong_cu_deu_co_khai_bao():
    thieu = {t["name"] for t in tools.TOOLS} - ten_ky_nang_co_san()
    assert not thieu, (
        f"Công cụ {sorted(thieu)} có trong TOOLS nhưng chưa khai báo trong "
        "agent/ky_nang/so_dang_ky.py. Người vận hành sẽ không thấy nó trên "
        "dashboard, và không tắt được."
    )


def test_khong_khai_bao_thua():
    thua = ten_ky_nang_co_san() - {t["name"] for t in tools.TOOLS}
    assert not thua, (
        f"Khai báo {sorted(thua)} không ứng với công cụ nào trong TOOLS. "
        "Dashboard sẽ hiện một công tắc không điều khiển gì cả."
    )


def test_khai_bao_khong_trung_ten():
    ten = [k.ten for k in SO_DANG_KY]
    assert len(ten) == len(set(ten))


@pytest.mark.parametrize("k", SO_DANG_KY, ids=lambda k: k.ten)
def test_moi_khai_bao_hop_le(k):
    assert k.nhom in NHOM, f"{k.ten}: nhóm {k.nhom!r} không có"
    assert k.muc_rui_ro in MUC_RUI_RO, f"{k.ten}: mức rủi ro {k.muc_rui_ro!r} không có"
    assert k.tom_tat.strip(), f"{k.ten}: thiếu tóm tắt"
    # Người vận hành phải đọc được HẬU QUẢ trước khi bấm tắt. Một câu ba từ
    # kiểu "mất tính năng này" không phải hậu quả, nó là đồng nghĩa.
    assert len(k.tat_thi_mat_gi) >= 40, (
        f"{k.ten}: 'tắt thì mất gì' quá ngắn — viết rõ hậu quả, đây là thứ "
        "duy nhất người vận hành đọc trước khi tắt."
    )


def test_chuyen_nhan_vien_khong_tat_duoc():
    k = khai_bao("chuyen_nhan_vien")
    assert k is not None
    assert k.tat_duoc is False
    assert "chuyen_nhan_vien" in KHONG_TAT_DUOC


def test_moi_ky_nang_khong_tat_duoc_deu_ton_tai():
    """`KHONG_TAT_DUOC` chứa tên ma thì chốt bảo vệ chặn nhầm chỗ."""
    assert KHONG_TAT_DUOC <= ten_ky_nang_co_san()


def test_hai_danh_sach_co_cung_quan_diem_ve_tat_duoc():
    """`tat_duoc=False` và `KHONG_TAT_DUOC` phải nói cùng một điều."""
    theo_khai_bao = {k.ten for k in SO_DANG_KY if not k.tat_duoc}
    assert theo_khai_bao == set(KHONG_TAT_DUOC), (
        "Cờ tat_duoc trong khai báo lệch với KHONG_TAT_DUOC. Dashboard đọc cờ, "
        "mã chặn đọc tập — lệch nhau là nút hiện ra bấm được nhưng luôn lỗi."
    )


def test_tao_don_hang_la_hanh_dong():
    """Công cụ duy nhất có hậu quả không đảo ngược phải mang mức cao nhất."""
    assert khai_bao("tao_don_hang").muc_rui_ro == "hanh_dong"


def test_chi_mot_ky_nang_o_muc_hanh_dong():
    """
    Mức `hanh_dong` là mức làm dashboard cảnh báo đỏ. Nếu có ngày nó gắn cho
    nửa số công cụ thì màu đỏ hết nghĩa và người vận hành thôi đọc.
    """
    cao = [k.ten for k in SO_DANG_KY if k.muc_rui_ro == "hanh_dong"]
    assert cao == ["tao_don_hang"], (
        f"Đang có {cao} ở mức hanh_dong. Thêm cái thứ hai thì cân nhắc kỹ: "
        "mức này để dành cho việc không đảo ngược được."
    )


def test_khong_the_tat_chuyen_nhan_vien_qua_ham():
    from agent.ky_nang import kho_ky_nang

    with pytest.raises(LoiBanMoTa):
        asyncio.run(kho_ky_nang.dat_bat_tat("chuyen_nhan_vien", False))


def test_khong_the_tat_ky_nang_khong_ton_tai():
    from agent.ky_nang import kho_ky_nang

    with pytest.raises(LoiBanMoTa):
        asyncio.run(kho_ky_nang.dat_bat_tat("ky_nang_khong_co_that", False))


# ---------------------------------------------------------------
#  Đọc AST, không so chuỗi
# ---------------------------------------------------------------
#
# Ba lần trước trong repo này, test canh mã bằng `in` đã bắt đúng đoạn CHÚ
# THÍCH giải thích vì sao không được viết như vậy — test xanh, ràng buộc
# chưa từng được kiểm. Đọc AST thì chú thích không tồn tại.

def _cay(duong_dan: str) -> ast.Module:
    return ast.parse((GOC / duong_dan).read_text(encoding="utf-8"))


def test_agent_khong_con_truyen_thang_TOOLS():
    """
    `agent.py` phải gửi danh sách ĐÃ LỌC, không phải `tools.TOOLS`.

    Quay lại `tools.TOOLS` là công tắc tắt kỹ năng thành đồ trang trí: nút
    trên dashboard vẫn bấm được, vẫn ghi vào CSDL, vẫn hiện "đã tắt" — mà
    model vẫn nhận đủ lược đồ và vẫn gọi. Đúng kiểu hỏng im lặng.
    """
    for node in ast.walk(_cay("agent/core/agent.py")):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "tools":
                continue
            assert isinstance(kw.value, ast.Name), (
                "Tham số tools= phải là biến đã lọc (cong_cu), không phải "
                f"{ast.dump(kw.value)[:80]}"
            )
            assert kw.value.id == "cong_cu"


def test_chi_mot_noi_truyen_cong_cu_cho_model():
    """
    Vẫn đúng MỘT agent. Đây là khẳng định trung tâm của cả kiến trúc, nên
    nó phải có test — chứ không phải chỉ có trong tài liệu.
    """
    # `agent/core/llm.py` bị loại trừ: nó là ỐNG DẪN, chuyển tiếp tham số
    # tools= xuống đúng provider. Đếm cả nó thì con số nói về số provider
    # được hỗ trợ, không nói về số agent — và khẳng định mất hết ý nghĩa.
    noi: list[str] = []
    for tep in (GOC / "agent").rglob("*.py"):
        if tep.name == "llm.py":
            continue
        for node in ast.walk(ast.parse(tep.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and any(k.arg == "tools" for k in node.keywords):
                noi.append(f"{tep.relative_to(GOC)}:{node.lineno}")
    assert len(noi) == 1, (
        f"Có {len(noi)} nơi truyền tools= cho model: {noi}. Mỗi nơi thêm là "
        "một vòng lặp công cụ thứ hai, và nó nằm NGOÀI sáu lớp lưới trong "
        "respond()."
    )


def test_so_dang_ky_khong_nhap_khau_tools():
    """
    Sổ đăng ký phải độc lập với `tools.py`.

    Nhập khẩu ngược lại là vòng nhập khẩu: `tools.py` → `kho_ky_nang` →
    `so_dang_ky` → `tools.py`. Python sẽ báo lỗi lúc khởi động, nhưng chỉ
    trên đường nhập khẩu nào đó — nên có máy chạy được, máy khác thì không.
    """
    for node in ast.walk(_cay("agent/ky_nang/so_dang_ky.py")):
        if isinstance(node, ast.ImportFrom):
            assert "tools" not in (node.module or "")
        if isinstance(node, ast.Import):
            for a in node.names:
                assert "tools" not in a.name


def test_tai_lieu_ky_nang_khong_cu():
    """
    `docs/ky-nang.md` được SINH RA từ sổ đăng ký. Thêm kỹ năng mà quên sinh
    lại là tài liệu bắt đầu nói dối — im lặng, đúng kiểu repo này ghét nhất.

        python -m scripts.sinh_ky_nang --ghi
    """
    from scripts.sinh_ky_nang import dung_tai_lieu

    tep = GOC / "docs" / "ky-nang.md"
    assert tep.exists(), "Thiếu docs/ky-nang.md — chạy scripts.sinh_ky_nang --ghi"
    assert tep.read_text(encoding="utf-8") == dung_tai_lieu(), (
        "docs/ky-nang.md đã cũ so với agent/ky_nang/so_dang_ky.py. "
        "Chạy: python -m scripts.sinh_ky_nang --ghi"
    )


def test_khai_bao_bat_bien():
    """Dataclass đóng băng: không ai sửa được mức rủi ro lúc chạy."""
    # frozen=True + slots=True ném FrozenInstanceError (một lớp con của
    # AttributeError). Bắt đúng loại chứ không bắt Exception trần: bắt trần
    # thì một ngày nào đó dòng dưới ném TypeError vì lý do khác hẳn, và test
    # vẫn xanh trong khi ràng buộc "bất biến" đã biến mất.
    with pytest.raises(AttributeError):
        so_dang_ky.SO_DANG_KY[0].muc_rui_ro = "doc"  # type: ignore[misc]
