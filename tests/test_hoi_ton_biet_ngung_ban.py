"""
Người gọi đối soát phải biết mã nào ĐÃ RỜI danh mục bán của ERP.

VÌ SAO KHÔNG SỬA `cong().ton_kho()`
-----------------------------------
Cách hiển nhiên là để cổng trả `False` khi mã không còn. Nhưng cổng hỏi
bảng `Bin` của ERPNext, và một mã đã vô hiệu VẪN CÓ `Bin` với số lượng
thật — đo được 14.09.2026: `AS-CB01` trả `TonKho(ban_duoc=25)` trong khi
nó không còn nằm trong danh mục bán. Cổng không có cách nào biết, và bắt
nó biết nghĩa là mỗi lần hỏi tồn kho lại kèm một lời gọi hỏi danh mục —
ở đúng chỗ nóng nhất, lúc chốt đơn.

Nên câu hỏi "mã này còn bán không" được trả lời MỘT LẦN mỗi vòng đối
soát, bằng một lần đọc danh mục, rồi dùng chung cho cả lượt quét.

`None` VÀ `False` LÀ HAI CHUYỆN
-------------------------------
`None` = chưa tra được, tạm thời, im lặng bỏ qua.
`False` = ERP không còn công nhận mã này, vĩnh viễn, phải kêu.
Gộp chúng thì chuyện thứ hai không bao giờ được phát hiện.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.erp.hop_dong import TonKho  # noqa: E402
from agent.erp.vong_dong_bo import hoi_ton_biet_ngung_ban  # noqa: E402


class _Cong:
    def __init__(self, ton: dict, ban: list[str], danh_muc_hong=False):
        self._ton, self._ban, self._hong = ton, ban, danh_muc_hong

    async def ton_kho(self, ma, bo_qua_cache=False):
        v = self._ton.get(ma)
        return TonKho(ban_duoc=v, ma_kho="Stores") if v is not None else None

    async def danh_muc(self):
        if self._hong:
            raise RuntimeError("ERP sập")
        return {"san_pham": [{"ma": m} for m in self._ban]}


def _hoi(cong):
    return asyncio.run(hoi_ton_biet_ngung_ban(cong))


def test_ma_con_ban_thi_tra_ton_kho():
    hoi = _hoi(_Cong({"A": 5}, ["A"]))
    assert asyncio.run(hoi("A")).ban_duoc == 5


def test_ma_roi_danh_muc_tra_False_du_van_con_ton():
    """Đúng ca của AS-CB01: Bin còn 25, danh mục bán không còn nó."""
    hoi = _hoi(_Cong({"A": 25}, []))
    assert asyncio.run(hoi("A")) is False


def test_ma_chua_tra_duoc_van_la_None():
    hoi = _hoi(_Cong({}, ["A"]))
    assert asyncio.run(hoi("A")) is None


def test_danh_muc_hong_thi_khong_vu_oan_ma_nao():
    """
    Không đọc được danh mục thì KHÔNG được kết luận mọi mã đã ngừng bán —
    một lần ERP trượt sẽ kêu lên toàn bộ bảng tồn kho, và lần sau không ai
    đọc cảnh báo ấy nữa.
    """
    hoi = _hoi(_Cong({"A": 5}, [], danh_muc_hong=True))
    assert asyncio.run(hoi("A")).ban_duoc == 5


def test_chi_doc_danh_muc_MOT_lan():
    """Đọc lại cho từng mã là nhân số lời gọi ERP với số dòng tồn kho."""
    dem = {"n": 0}

    class _Dem(_Cong):
        async def danh_muc(self):
            dem["n"] += 1
            return await super().danh_muc()

    hoi = _hoi(_Dem({"A": 1, "B": 2}, ["A", "B"]))
    for ma in ("A", "B", "A"):
        asyncio.run(hoi(ma))
    assert dem["n"] == 1


def test_vong_dong_bo_dung_ham_nay():
    """Thêm hàm mà không nối vào vòng thì nó không bao giờ chạy."""
    import inspect

    from agent.erp import vong_dong_bo

    src = inspect.getsource(vong_dong_bo.vong_dong_bo_loop)
    assert "hoi_ton_biet_ngung_ban" in src, \
        "vòng đồng bộ vẫn truyền hàm cũ — tính năng mới không có nguồn cấp"
