"""
Ghi nhận những xác nhận mà chỉ CON NGƯỜI làm được.

VÌ SAO CẦN
----------
`kiem_ket_noi` có một mục vàng vĩnh viễn: "NGƯỜI phải xác nhận 'Standard
Selling' đúng là giá BÁN LẺ". Máy không tự biết bảng nào là bảng bán lẻ —
nó chỉ thấy một cái tên và một con số.

Nhưng cảnh báo không bao giờ tắt được thì tệ hơn không có cảnh báo. Người
vận hành mở bản kiểm, thấy vàng, và biết rằng nó LÚC NÀO CŨNG vàng. Lần
sau có một mục vàng THẬT, mắt họ lướt qua. Đó là cách một bộ kiểm tự huỷ
hoại chính mình.

XÁC NHẬN GẮN VỚI GIÁ TRỊ, KHÔNG PHẢI LÀ NÚT TẮT CẢNH BÁO
--------------------------------------------------------
Đây là điểm mấu chốt. Xác nhận được ghi kèm CHÍNH TÊN bảng giá tại thời
điểm bấm. Đổi `ERP_PRICELIST` sang bảng khác thì cảnh báo quay lại ngay,
vì cái đã xác nhận không còn là cái đang chạy.

Một nút "tôi đã kiểm rồi" chung chung thì bấm một lần là im mãi mãi — kể
cả sau khi ai đó đổi sang bảng giá sỉ. Lúc đó nó không còn là xác nhận, nó
là cái nút tắt tiếng.

Và xác nhận ghi rõ AI, LÚC NÀO. Một xác nhận không truy được người là một
xác nhận không ai chịu trách nhiệm.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from agent import db

# Lưu trong `cau_hinh_agent` — kho khoá–giá trị dùng chung. Không dựng bảng
# riêng cho một dòng.
#
# `runtime.dat_lai_mac_dinh()` xoá theo DANH SÁCH khoá của nó, không xoá cả
# bảng, nên nút "Quay về mặc định" của màn Cấu hình không đụng tới đây.
KHOA = "bang_gia_da_xac_nhan"


async def doc() -> dict | None:
    """Xác nhận đang lưu, hoặc None. Không bao giờ ném."""
    try:
        r = await db.fetchrow(
            "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = $1", KHOA
        )
    except Exception:  # noqa: BLE001
        return None
    if not r:
        return None
    gt = r["gia_tri"]
    if isinstance(gt, str):
        try:
            gt = json.loads(gt)
        except ValueError:
            return None
    return gt if isinstance(gt, dict) else None


async def da_xac_nhan(ten_bang_gia: str) -> dict | None:
    """
    Bảng giá NÀY đã được xác nhận chưa.

    So khớp đúng tên. Xác nhận cho 'Standard Selling' không che cho
    'Wholesale' — đó là toàn bộ lý do hàm này nhận tham số.
    """
    ban_ghi = await doc()
    if not ban_ghi:
        return None
    if (ban_ghi.get("ten") or "").strip() != (ten_bang_gia or "").strip():
        return None
    return ban_ghi


async def ghi(ten_bang_gia: str, *, boi: str) -> dict:
    """Ghi nhận rằng người này đã xác nhận bảng giá này là giá bán lẻ."""
    ten = (ten_bang_gia or "").strip()
    if not ten:
        raise ValueError("Chưa biết đang dùng bảng giá nào — không xác nhận suông.")

    ban_ghi = {
        "ten": ten,
        "boi": boi,
        "luc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    await db.execute(
        """
        INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi)
        VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (khoa) DO UPDATE
            SET gia_tri = EXCLUDED.gia_tri, sua_boi = EXCLUDED.sua_boi,
                sua_luc = now()
        """,
        KHOA, json.dumps(ban_ghi, ensure_ascii=False), boi,
    )
    await db.log_event("erp.xac_nhan_bang_gia", actor=boi, bang_gia=ten)
    return ban_ghi


async def go(*, boi: str = "staff") -> bool:
    """Gỡ xác nhận — cảnh báo quay lại."""
    tt = await db.execute("DELETE FROM cau_hinh_agent WHERE khoa = $1", KHOA)
    # `db.execute` trả CHUỖI "DELETE 0", và `bool("DELETE 0")` là True.
    so_dong = int(str(tt).rsplit(" ", 1)[-1] or 0)
    if so_dong:
        await db.log_event("erp.go_xac_nhan_bang_gia", actor=boi)
    return so_dong > 0
