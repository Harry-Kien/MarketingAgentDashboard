"""
Công tắc tắt lớp lưới tồn tại để ĐO luận điểm trung tâm, và CHỈ để đo.

VÌ SAO CÓ CÔNG TẮC NÀY
----------------------
`docs/co-so-ly-thuyet.md` khẳng định cần đủ sáu lớp lưới, mỗi lớp canh một
cách trượt khác nhau. Bằng chứng trước đây là hai giai thoại. Phản biện sẽ
hỏi đúng câu: "tắt từng lớp thì sao?" — và không trả lời được nếu không có
cách tắt từng lớp trên CÙNG một bộ câu hỏi, CÙNG một commit.

VÌ SAO NÓ KHÔNG PHẢI LỖ HỔNG
----------------------------
Một công tắc tắt lưới an toàn là thứ nguy hiểm nhất có thể thêm vào file
này. Nên nó bị trói bốn cách, mỗi cách một test dưới đây:

1. ContextVar, không env/config/API — không đường nào từ webhook hay
   dashboard chạm tới.
2. Mặc định rỗng; ra khỏi khối `with` là bật lại.
3. Tên lưới lạ thì nổ — gõ sai không được thành "tắt nhầm cái khác".
4. Chỉ bộ đo được gọi nó; file thứ năm gọi tới là test đỏ.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agent.core import agent as A

ROOT = Path(__file__).resolve().parent.parent


def test_mac_dinh_khong_tat_luoi_nao():
    assert A.luoi_dang_tat() == frozenset()


def test_ma_la_thi_no():
    with pytest.raises(KeyError):
        with A.tat_luoi_de_do({"khong_ton_tai"}):
            pass


def test_ra_khoi_khoi_thi_bat_lai():
    with A.tat_luoi_de_do({"injection"}):
        assert A.luoi_dang_tat() == {"injection"}
    assert A.luoi_dang_tat() == frozenset()


def test_loi_trong_khoi_van_bat_lai():
    with pytest.raises(RuntimeError):
        with A.tat_luoi_de_do({"injection"}):
            raise RuntimeError("giữa chừng")
    assert A.luoi_dang_tat() == frozenset()


def test_chi_bo_do_duoc_goi():
    goi = set()
    for thu_muc in ("agent", "scripts", "tests"):
        for p in (ROOT / thu_muc).rglob("*.py"):
            if "tat_luoi_de_do(" in p.read_text(encoding="utf-8", errors="ignore"):
                goi.add(p.name)
    cho_phep = {"agent.py", "eval.py", "eval_nhieu_luot.py",
                "test_cong_tac_tat_luoi.py", "test_eval_tat_luoi.py"}
    assert goi <= cho_phep, f"công tắc tắt lưới bị gọi ngoài bộ đo: {goi - cho_phep}"


@pytest.mark.parametrize("ma", sorted(A.LOP_LUOI))
def test_moi_lop_luoi_deu_di_qua_cong(ma):
    """Lưới nào không đi qua `_bat()` thì ablation đo sai mà không ai biết."""
    src = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    assert f'_bat("{ma}")' in src, f"lưới {ma} không đi qua cổng _bat()"
