"""
Đối soát tồn kho phải phân biệt "ERP chậm" với "mã đã rời danh mục bán".

LỖI THẬT, ĐO ĐƯỢC 14.09.2026
---------------------------
`doi_soat_ton_kho` gộp mọi mã không tra được vào một con số duy nhất,
`khong_tra_duoc`, rồi bỏ qua im lặng. Hai nguyên nhân rất khác nhau rơi
chung vào đó:

  * ERP chậm hoặc mạng trượt — TẠM THỜI, lần sau tự hết, báo động là nhiễu.
  * Mã đã bị vô hiệu hoặc xoá bên ERP — VĨNH VIỄN. Bảng `ton_kho` nội bộ
    giữ mãi một dòng mà sổ cái không còn công nhận, và không gì nói ra.

Gộp chúng là bảo đảm chuyện thứ hai không bao giờ được phát hiện: con số
`khong_tra_duoc` lúc nào cũng khác 0 vì ERP thỉnh thoảng chậm, nên nhìn
mãi thành quen.

KHÔNG TỰ XOÁ
------------
Vẫn giữ nguyên tắc cũ của hàm này: chỉ BÁO, không sửa. Máy tự xoá một dòng
tồn kho vì ERP bảo mã ấy không còn là xoá mất bằng chứng của một lần cấu
hình sai — và số lượng trong dòng ấy là hàng thật đang nằm trong kho.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.hop_dong import TonKho  # noqa: E402
from agent.erp.vong_dong_bo import doi_soat_ton_kho  # noqa: E402


def _chay(ton, hoi, **kw):
    ghi: list[tuple] = []

    async def nhat_ky(loai, **ct):
        ghi.append((loai, ct))

    kq = asyncio.run(doi_soat_ton_kho(ton, hoi, nhat_ky, **kw))
    return kq, ghi


def _ton(n: int) -> TonKho:
    return TonKho(ban_duoc=n, ma_kho="Stores")


# --- Ba trạng thái, ba con số ----------------------------------------

def test_ma_ngung_ban_duoc_dem_rieng():
    """`hoi_erp` trả `False` = ERP nói KHÔNG CÓ mã này, khác hẳn `None`."""
    async def hoi(ma):
        return {"A": _ton(5), "B": False, "C": None}[ma]

    kq, _ = _chay({"A": 5, "B": 3, "C": 7}, hoi)
    assert kq["khong_tra_duoc"] == 1, "ERP chậm phải đếm riêng"
    assert [x["ma"] for x in kq["ngung_ban"]] == ["B"]
    assert kq["ngung_ban"][0]["noi_bo"] == 3, "phải nói còn bao nhiêu hàng trong kho"


def test_ma_ngung_ban_thi_keu_len():
    async def hoi(ma):
        return False if ma == "B" else _ton(5)

    _, ghi = _chay({"A": 5, "B": 3}, hoi)
    assert any(l == "erp.ma_ngung_ban" for l, _ in ghi), \
        "không kêu thì dòng rác nằm mãi và không ai biết"


def test_khong_tu_xoa_dong_nao():
    """Chỉ báo. Số lượng trong dòng ấy là hàng thật đang nằm trong kho."""
    import inspect

    from agent.erp import vong_dong_bo

    src = inspect.getsource(vong_dong_bo.doi_soat_ton_kho)
    for cam in ("DELETE", "db.execute", "xoa_"):
        assert cam not in src, f"đối soát đang tự sửa dữ liệu: {cam}"


# --- Không đổi hành vi cũ --------------------------------------------

def test_erp_cham_van_bi_bo_qua_khong_keu():
    """`None` là tạm thời. Kêu ở đây là báo động giả hàng loạt mỗi lần
    ERP chậm — đúng thứ ghi chú cũ của hàm này cảnh báo."""
    async def hoi(ma):
        return None

    kq, ghi = _chay({"A": 5, "B": 3}, hoi)
    assert kq["khong_tra_duoc"] == 2
    assert kq["ngung_ban"] == []
    assert ghi == []


def test_lech_so_luong_van_keu_nhu_cu():
    async def hoi(ma):
        return _ton(9)

    kq, ghi = _chay({"A": 5}, hoi)
    assert len(kq["lech"]) == 1
    assert any(l == "erp.lech_ton_kho" for l, _ in ghi)


def test_nem_loi_van_tinh_la_chua_tra_duoc():
    async def hoi(ma):
        raise RuntimeError("mạng trượt")

    kq, ghi = _chay({"A": 5}, hoi)
    assert kq["khong_tra_duoc"] == 1 and kq["ngung_ban"] == [] and ghi == []


def test_moi_thu_binh_thuong_thi_im_lang():
    async def hoi(ma):
        return _ton(5)

    kq, ghi = _chay({"A": 5}, hoi)
    assert kq["lech"] == [] and kq["ngung_ban"] == [] and ghi == []
