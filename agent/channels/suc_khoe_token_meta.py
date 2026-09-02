"""
Canh hạn Page token của Meta — trước khi nó chết, không phải sau.

VÌ SAO CẦN
----------
Đo trên tài khoản thật đang chạy:

    Homeseeker: token CÒN SỐNG
       hạn dùng: VĨNH VIỄN (token dài hạn)
       hạn truy cập dữ liệu: 2026-11-24

Token thì vĩnh viễn — Facebook Login for Business trả token dài hạn ngay,
khác Facebook Login cổ điển. Nhưng `data_access_expires_at` thì CÓ hạn: sau
mốc đó, app mất quyền đọc dữ liệu trừ khi người dùng cấp quyền lại.

Và không có gì trong hệ thống theo dõi mốc ấy.

HỎNG THẾ NÀO KHI TỚI HẠN
------------------------
Trang vẫn hiện xanh trên dashboard. Webhook vẫn đăng ký. Chỉ có Graph bắt
đầu trả `OAuthException`, tin khách không về nữa, và tin gửi đi thì hỏng —
tất cả cùng một lúc, không báo trước, thường vào một ngày không ai để ý.

Cách duy nhất biết trước là HỎI Meta. `debug_token` trả cả hạn token lẫn hạn
truy cập dữ liệu, và nó rẻ: một lời gọi cho mỗi tài khoản, một lần mỗi ngày.

VÌ SAO BÁO SỚM 14 NGÀY
----------------------
Cấp quyền lại cần CHỦ TRANG thao tác, không phải người trực. Báo trước một
ngày là báo cho người không tự xử lý được. Hai tuần đủ để hẹn được người có
quyền, kể cả khi họ đi vắng.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import httpx

# Báo trước ngần này ngày. Xem docstring: đủ để hẹn được chủ Trang.
NGAY_BAO_TRUOC = 14

# Mốc "còn sống mãi" của Meta. `expires_at = 0` nghĩa là không hết hạn.
VINH_VIEN = 0


def _ngay_con_lai(moc: Any, bay_gio: datetime) -> float | None:
    """Số ngày còn lại tới mốc unix, hoặc None nếu mốc là vĩnh viễn/rỗng."""
    try:
        so = int(moc or 0)
    except (TypeError, ValueError):
        return None
    if so == VINH_VIEN:
        return None
    return (datetime.fromtimestamp(so, timezone.utc) - bay_gio).total_seconds() / 86400


def doc_suc_khoe(
    du_lieu: Mapping[str, Any], *, bay_gio: datetime | None = None,
) -> dict:
    """
    Đọc phản hồi `debug_token` thành kết luận dùng được.

    Tách khỏi phần gọi mạng để test được mọi tình huống hạn dùng mà không
    cần dựng máy chủ giả.
    """
    bay_gio = bay_gio or datetime.now(timezone.utc)
    d = du_lieu.get("data") if isinstance(du_lieu.get("data"), Mapping) else du_lieu

    con_song = bool(d.get("is_valid"))
    ngay_token = _ngay_con_lai(d.get("expires_at"), bay_gio)
    ngay_du_lieu = _ngay_con_lai(d.get("data_access_expires_at"), bay_gio)

    # Lấy mốc GẦN NHẤT trong hai mốc: cái nào tới trước thì cái đó làm chết
    # kết nối trước.
    sap_het = [n for n in (ngay_token, ngay_du_lieu) if n is not None]
    con_lai = min(sap_het) if sap_het else None

    if not con_song:
        muc = "chet"
    elif con_lai is not None and con_lai <= 0:
        muc = "chet"
    elif con_lai is not None and con_lai <= NGAY_BAO_TRUOC:
        muc = "sap_het"
    else:
        muc = "on"

    return {
        "muc": muc,
        "con_song": con_song,
        "ngay_con_lai": con_lai,
        "ngay_token": ngay_token,
        "ngay_du_lieu": ngay_du_lieu,
        "loi": str((d.get("error") or {}).get("message") or "")[:200],
    }


async def hoi_meta(
    *, token: str, app_id: str, app_secret: str,
    client: httpx.AsyncClient | None = None,
) -> dict | None:
    """
    Hỏi `debug_token`. Trả None khi không hỏi được — KHÔNG ném.

    Mạng hỏng không được biến thành báo động giả "token chết": người trực sẽ
    đi cấp quyền lại cho một token vẫn còn tốt, và lần sau họ bỏ qua cảnh báo
    thật.
    """
    if not (token and app_id and app_secret):
        return None

    tu_mo = client is None
    from agent.config import settings

    client = client or httpx.AsyncClient(base_url=settings.graph_base, timeout=20)
    try:
        r = await client.get("/debug_token", params={
            "input_token": token,
            # Token của ứng dụng, dạng `app_id|app_secret`. Không bao giờ ra
            # khỏi máy chủ.
            "access_token": f"{app_id}|{app_secret}",
        })
        if getattr(r, "status_code", 200) >= 400:
            return None
        return doc_suc_khoe(r.json() or {})
    except Exception:  # noqa: BLE001 — xem docstring
        return None
    finally:
        if tu_mo:
            await client.aclose()
