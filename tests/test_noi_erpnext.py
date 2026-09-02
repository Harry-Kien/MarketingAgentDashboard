"""
Script nối ERPNext: sinh khoá, chọn kho/bảng giá, ghi `.env`.

Hai ràng buộc quan trọng nhất được canh ở đây:

  1. KHÔNG BAO GIỜ IN BÍ MẬT. In khoá API ra màn hình là để nó lại trong
     lịch sử terminal và trong ảnh chụp màn hình — hai chỗ không xoá được.
     Cùng lý do `scripts/sinh_token.py` tồn tại.

  2. KHÔNG TỰ ĐOÁN KHO. `agent/erp/erpnext.py` ném ngay lúc khởi động nếu
     thiếu `ERP_MA_KHO`, vì thiếu mã kho thì `Bin` trả tồn của MỌI kho cộng
     lại — con số trông hợp lý và sai. Đoán bừa một kho còn tệ hơn: nó
     KHÔNG ném, và sai im lặng.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import noi_erpnext as ne  # noqa: E402

NGUON = (ROOT / "scripts" / "noi_erpnext.py").read_text(encoding="utf-8")


# =====================================================================
#  Không in bí mật
# =====================================================================

def test_khong_in_khoa_hay_bi_mat_ra_man_hinh():
    """
    Soi từng lời gọi `print` bằng AST: tên biến giữ bí mật không được xuất
    hiện trong bất kỳ đối số nào.

    Đọc bằng AST chứ không so chuỗi, để phần docstring nói VỀ bí mật không
    bị bắt nhầm — bài học từ `tests/test_ha_tang_erpnext.py`.
    """
    cay = ast.parse(NGUON)
    cam = {"khoa", "bi_mat", "api_key", "api_secret", "mat_khau"}
    pham = []
    for n in ast.walk(cay):
        if not (isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "print"):
            continue
        for ten in (x.id for x in ast.walk(n) if isinstance(x, ast.Name)):
            if ten in cam:
                pham.append((n.lineno, ten))
    assert not pham, f"print có thể lộ bí mật: {pham}"


def test_thong_bao_cuoi_noi_ro_la_khong_in():
    assert "KHÔNG được in ra" in NGUON


def test_sao_luu_env_truoc_khi_sua():
    """`.env` giữ mọi khoá kết nối; một lần ghi hỏng là mất hết."""
    assert ".env.bak" in NGUON
    assert "shutil.copyfile" in NGUON


def test_thay_tung_dong_chu_khong_ghi_de_ca_tep():
    assert "re.compile" in NGUON
    assert "count=1" in NGUON


# =====================================================================
#  Không tự đoán kho / bảng giá
# =====================================================================

def test_mot_lua_chon_thi_lay_luon(capsys):
    assert ne._chon("kho", ["Kho Chính - AS"]) == "Kho Chính - AS"


def test_nhieu_lua_chon_thi_KHONG_doan(capsys):
    """
    Đoán bừa một kho không ném lỗi — nó sai IM LẶNG, và triệu chứng duy
    nhất là tồn kho lệch mãi về sau.
    """
    kq = ne._chon("kho", ["Kho A", "Kho B", "Kho C"])
    assert kq is None
    ra = capsys.readouterr().out
    assert "Kho A" in ra and "Kho C" in ra


def test_khong_co_lua_chon_nao_thi_bao_ro(capsys):
    assert ne._chon("bảng giá", []) is None
    assert "chưa có" in capsys.readouterr().out


def test_thieu_kho_hoac_bang_gia_thi_khong_ghi_env():
    """Ghi .env một nửa là để hệ thống ở trạng thái nửa cấu hình."""
    assert "Thiếu kho hoặc bảng giá, dừng lại — không ghi .env." in NGUON


# =====================================================================
#  Ghi .env
# =====================================================================

def test_ghi_du_sau_khoa(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("ERP_LOAI=tep\nGIU_NGUYEN=1\n", encoding="utf-8")
    monkeypatch.setattr(ne, "ENV", env)

    ne._ghi_env({
        "ERP_LOAI": "erpnext",
        "ERPNEXT_URL": "http://localhost:8080",
        "ERPNEXT_API_KEY": "k",
        "ERPNEXT_API_SECRET": "s",
        "ERP_MA_KHO": "Kho Chính",
        "ERP_PRICELIST": "Bảng giá bán lẻ",
    })

    ra = env.read_text(encoding="utf-8")
    assert "ERP_LOAI=erpnext" in ra
    assert "ERP_LOAI=tep" not in ra          # thay, không thêm dòng thứ hai
    assert "GIU_NGUYEN=1" in ra              # dòng khác không bị đụng
    assert "ERP_MA_KHO=Kho Chính" in ra
    assert (tmp_path / ".env.bak").exists()


def test_che_do_xem_khong_sinh_khoa():
    """`--xem` phải thoát TRƯỚC generate_keys, không phải sau."""
    i_xem = NGUON.index("if a.xem:")
    i_sinh = NGUON.index("generate_keys")
    assert i_xem < i_sinh
