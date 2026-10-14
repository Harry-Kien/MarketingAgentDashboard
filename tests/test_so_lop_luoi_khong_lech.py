"""
Số lớp lưới chỉ có MỘT nguồn sự thật, và tài liệu phải khớp nó.

ĐO ĐƯỢC 22.09.2026 — con số này được gõ tay ở năm chỗ và chia làm hai phe:

    sáu : CLAUDE.md, docs/ky-nang.md, chú thích trong agent.py
    năm : docs/co-so-ly-thuyet.md, docs/kien-truc.md, docs/thuc-nghiem.md

Sai con số mới là phần nhẹ. Phần nặng: bảng trong `co-so-ly-thuyet.md` liệt
kê `_stalls` như một lớp lưới — nó KHÔNG đặt `luoi_bat`, không chuyển người,
mà chỉ ép thêm đúng một vòng gọi công cụ — đồng thời BỎ SÓT lưới ③ (tin cậy
thấp) và lưới ⑥ (chẩn đoán y tế trong câu trả lời).

CLAUDE.md dặn "đừng gỡ lớp nào mà không đọc co-so-ly-thuyet.md mục 6", rồi
chính mục ấy mô tả sai tập hợp cần bảo vệ. Người tin nó sẽ đi bảo trì
`_stalls` như một lưới an toàn và không biết lưới ⑥ tồn tại — nghĩa là một
lớp chặn chẩn đoán y tế có thể bị gỡ trong một lần dọn dẹp, mà người gỡ tin
rằng mình đang làm đúng tài liệu.

Đúng điều CLAUDE.md cấm: **đừng gõ số vào tài liệu**.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent.core.agent import LOP_LUOI, MA_CHUYEN_KHAC, so_lop_luoi

ROOT = Path(__file__).resolve().parent.parent
AGENT_PY = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")

SO_CHU = {5: "năm", 6: "sáu", 7: "bảy", 8: "tám"}


def _ma_dung_trong_agent() -> set[str]:
    """Mọi giá trị `luoi_bat` mà agent.py thật sự gán."""
    ma = set(re.findall(r'luoi_bat\s*=\s*"([a-z_]+)"', AGENT_PY))
    ma |= set(re.findall(r'luoi_bat\s*=\s*luoi_bat\s+or\s+"([a-z_]+)"', AGENT_PY))
    return ma


def test_moi_ma_luoi_bat_deu_co_trong_danh_muc():
    """
    Gán một mã lạ thì dashboard hiện nhãn TRỐNG — không lỗi, không log,
    người trực chỉ thấy một ô thiếu chữ.
    """
    biet = set(LOP_LUOI) | set(MA_CHUYEN_KHAC)
    la = _ma_dung_trong_agent() - biet
    assert not la, (
        f"agent.py gán mã luoi_bat chưa khai: {sorted(la)}. "
        "Thêm vào LOP_LUOI (nếu là lưới bắt trượt) hoặc MA_CHUYEN_KHAC "
        "(nếu là đường chuyển người chạy đúng thiết kế)."
    )


def test_khong_co_lop_luoi_ma_khong_ai_gan():
    """Lưới khai mà mã không bao giờ gán là lưới đã chết — hoặc là số đếm phồng."""
    dung = _ma_dung_trong_agent()
    thua = set(LOP_LUOI) - dung
    assert not thua, (
        f"LOP_LUOI khai {sorted(thua)} nhưng agent.py không gán — lưới đã bị "
        "gỡ mà danh mục còn, nên số đếm và tài liệu đang nói quá thực tế"
    )


def test_stalls_khong_phai_mot_lop_luoi():
    """
    Chốt cho đúng sai sót đã xảy ra. `_stalls` ép thêm một vòng gọi công cụ
    rồi thôi; gọi nó là lưới an toàn là hiểu sai vai trò của nó.
    """
    assert "_stalls" in AGENT_PY, "hàm _stalls biến mất — đọc lại test này"
    assert "stalls" not in LOP_LUOI and "_stalls" not in LOP_LUOI
    khoi = AGENT_PY[AGENT_PY.find("if _stalls("):][:400]
    assert "luoi_bat" not in khoi, (
        "_stalls giờ có đặt luoi_bat — nếu đó là cố ý thì nó ĐÃ thành một "
        "lớp lưới: khai vào LOP_LUOI và sửa bảng trong co-so-ly-thuyet.md"
    )


def test_nhan_luoi_phu_het_moi_ma():
    """Thiếu nhãn thì dashboard hiện chuỗi rỗng, im lặng."""
    from agent.api.phong_thu_agent import NHAN_LUOI

    thieu = (set(LOP_LUOI) | set(MA_CHUYEN_KHAC)) - set(NHAN_LUOI)
    assert not thieu, f"NHAN_LUOI thiếu nhãn cho: {sorted(thieu)}"


@pytest.mark.parametrize("ten", [
    "CLAUDE.md",
    "docs/co-so-ly-thuyet.md",
    "docs/thuc-nghiem.md",
    "docs/kien-truc.md",
    "docs/ky-nang.md",
    # Ba tài liệu trên được SINH RA. Sửa tay bản .md mà bỏ quên script sinh
    # thì lần chạy `--ghi` sau đặt lại con số sai — và lần ấy trông như một
    # lượt sinh lại bình thường, không ai soi.
    "scripts/sinh_so_do.py",
    "scripts/sinh_thuc_nghiem.py",
    "scripts/sinh_ky_nang.py",
])
def test_tai_lieu_khong_noi_sai_so_lop_luoi(ten: str):
    """
    Mọi chỗ trong tài liệu nói "<số> lớp" đều phải nói đúng số hiện tại.

    Quét theo MẪU chứ không so nguyên văn: thêm một câu mới ghi sai số ở
    chỗ khác vẫn bị bắt.
    """
    n = so_lop_luoi()
    dung = {SO_CHU[n], SO_CHU[n].capitalize(), str(n)}
    src = (ROOT / ten).read_text(encoding="utf-8")

    sai = []
    for m in re.finditer(r"([A-Za-zÀ-ỹ0-9]+)\s+lớp(?:\s+lưới)?\b", src):
        tu = m.group(1)
        if tu in dung:
            continue
        # Chỉ xét các từ CHỈ SỐ LƯỢNG; "mỗi lớp", "một lớp", "hai lớp" (nói
        # về hai lớp trong phong_thu.py) không phải số lớp lưới.
        if tu.lower() in SO_CHU.values() or re.fullmatch(r"\d+", tu):
            dong = src[:m.start()].count("\n") + 1
            sai.append(f"{ten}:{dong} — “{m.group(0)}”")

    assert not sai, (
        f"Tài liệu nói sai số lớp lưới (đúng là {n} = “{SO_CHU[n]}”):\n  "
        + "\n  ".join(sai)
        + "\nĐừng gõ số vào tài liệu: đếm từ LOP_LUOI trong agent/core/agent.py."
    )


def test_bang_trong_co_so_ly_thuyet_liet_ke_du_moi_luoi():
    """
    Bảng phải khớp danh mục, không chỉ khớp con số. Đếm đúng mà liệt kê sai
    tên vẫn dẫn người bảo trì tới nhầm chỗ — đó chính là lỗi đã xảy ra.
    """
    src = (ROOT / "docs" / "co-so-ly-thuyet.md").read_text(encoding="utf-8")
    thieu = [ma for ma in LOP_LUOI if f"`{ma}`" not in src]
    assert not thieu, (
        f"co-so-ly-thuyet.md chưa liệt kê lưới: {thieu}. "
        "Bảng ở mục 6 phải có đủ mọi mã trong LOP_LUOI."
    )
