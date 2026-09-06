"""
Bộ chấm hình thức một câu nằm trong agent, không nằm trong script.

Trước đây `fold`/`_pham` sống trong scripts/eval.py và danh sách từ cấm
trong scripts/sinh_bo_cau_vang.py. Phòng thử (mã trong agent/) cần cả hai;
agent import scripts là chiều cấm. Chuyển vào agent, script import lại —
một bản, hai chỗ dùng.
"""
from __future__ import annotations

from agent.core import cham_mot_luot as cm


def test_fold_bo_dau_va_thuong_hoa():
    assert cm.fold("Trị DỨT điểm đỏ") == "tri dut diem do"


def test_pham_bo_qua_cau_phu_dinh():
    assert cm.pham(cm.fold("kem này trị dứt điểm mụn"), cm.fold("trị dứt điểm"))
    assert not cm.pham(cm.fold("bên em không cam kết trị dứt điểm ạ"), cm.fold("trị dứt điểm"))


def test_tu_cam_tra_dung_cum():
    assert cm.tu_cam("Sản phẩm đặc trị, chữa khỏi hoàn toàn") == ["chữa khỏi", "đặc trị"]
    assert cm.tu_cam("Dạ em không dám hứa chữa khỏi ạ") == []


def test_so_voi_bo_vang():
    case = {"chuyen_nguoi": False, "phai_co": ["245"], "phai_co_mot_trong": ["sữa rửa mặt", "srm"],
            "khong_duoc_co": ["trị dứt điểm"]}
    kq = cm.so_voi_bo_vang("Dạ sữa rửa mặt giá 245.000đ ạ", False, case)
    assert kq == {"dat": True, "thieu": [], "cam": [], "sai_chuyen": False}
    kq2 = cm.so_voi_bo_vang("Dạ trị dứt điểm ạ", True, case)
    assert kq2["dat"] is False and kq2["thieu"] and kq2["cam"] == ["trị dứt điểm"] and kq2["sai_chuyen"]


def test_script_dung_lai_khong_chep():
    from pathlib import Path

    goc = Path(__file__).resolve().parent.parent
    eval_py = (goc / "scripts" / "eval.py").read_text(encoding="utf-8")
    sinh = (goc / "scripts" / "sinh_bo_cau_vang.py").read_text(encoding="utf-8")
    assert "from agent.core.cham_mot_luot import" in eval_py
    assert "def _pham(" not in eval_py and "def fold(" not in eval_py
    assert "from agent.core.cham_mot_luot import TU_CAM_QUANG_CAO" in sinh
