"""
Gói cước và hạn mức của MỘT cửa hàng (mô hình silo: mỗi app một cửa hàng).

Hạn mức nằm trong `.env` của cửa hàng, do mặt phẳng điều khiển đặt theo gói
(`python -m scripts.cua_hang goi <ma> <ten_goi>`). 0 = không giới hạn — bản
chạy một cửa hàng như hiện nay không đổi gì.

VƯỢT HẠN MỨC KHÔNG ĐƯỢC LÀ IM LẶNG
---------------------------------
- Thêm kênh / nhân viên vượt gói: báo rõ gói cho tối đa bao nhiêu (402).
- Hết lượt hội thoại AI trong tháng: hội thoại MỚI chuyển cho người như khi
  agent tắt — sinh việc, ghi nhật ký — không ngừng trả lời mà không ai biết.
  Hội thoại AI đã trả lời trong tháng thì KHÔNG bị cắt giữa chừng: cắt giữa
  một cuộc tư vấn là tệ hơn cả không bắt đầu.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent import db
from agent.config import settings

# Ngày theo giờ Việt Nam: "tháng này" của chủ shop bắt đầu 0h ngày 1 giờ VN.
_DAU_THANG = "date_trunc('month', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') AT TIME ZONE 'Asia/Ho_Chi_Minh'"


class VuotHanMuc(ValueError):
    """Thao tác vượt hạn mức của gói hiện tại."""


@dataclass(frozen=True)
class HanMuc:
    goi: str
    kenh: int
    nhan_vien: int
    hoi_thoai_ai_thang: int


def han_muc() -> HanMuc:
    return HanMuc(settings.goi_cuoc or "khong_gioi_han", max(0, settings.gioi_han_kenh),
                  max(0, settings.gioi_han_nhan_vien),
                  max(0, settings.gioi_han_hoi_thoai_ai_thang))


async def dang_dung() -> dict[str, int]:
    r = await db.fetchrow(
        "SELECT "
        " (SELECT count(*) FROM channel_accounts WHERE NOT is_legacy "
        "    AND status <> 'disabled') AS kenh, "
        " (SELECT count(*) FROM nguoi_dung WHERE NOT khoa) AS nhan_vien, "
        f" (SELECT count(DISTINCT conversation_id) FROM messages WHERE role = 'agent' "
        f"    AND created_at >= {_DAU_THANG}) AS hoi_thoai_ai_thang")
    return {k: int(r[k] or 0) for k in ("kenh", "nhan_vien", "hoi_thoai_ai_thang")} if r else \
        {"kenh": 0, "nhan_vien": 0, "hoi_thoai_ai_thang": 0}


async def kiem_them_kenh() -> None:
    hm = han_muc()
    if hm.kenh and (await dang_dung())["kenh"] >= hm.kenh:
        raise VuotHanMuc(f"Gói {hm.goi} cho tối đa {hm.kenh} tài khoản kênh. "
                         "Tắt một kênh cũ hoặc nâng gói.")


async def kiem_them_nhan_vien() -> None:
    hm = han_muc()
    if hm.nhan_vien and (await dang_dung())["nhan_vien"] >= hm.nhan_vien:
        raise VuotHanMuc(f"Gói {hm.goi} cho tối đa {hm.nhan_vien} nhân viên đang hoạt động. "
                         "Khoá một tài khoản cũ hoặc nâng gói.")


async def con_luot_ai(conversation_id: Any) -> bool:
    """Agent còn được nhận hội thoại này không, theo hạn mức tháng."""
    hm = han_muc()
    if not hm.hoi_thoai_ai_thang:
        return True
    r = await db.fetchrow(
        f"SELECT EXISTS (SELECT 1 FROM messages WHERE conversation_id = $1 AND role = 'agent' "
        f"  AND created_at >= {_DAU_THANG}) AS da_co, "
        f" (SELECT count(DISTINCT conversation_id) FROM messages WHERE role = 'agent' "
        f"  AND created_at >= {_DAU_THANG}) AS da_dung", conversation_id)
    if r is None:
        return True
    return bool(r["da_co"]) or int(r["da_dung"] or 0) < hm.hoi_thoai_ai_thang
