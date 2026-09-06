# agent/core/phong_thu_phien.py
"""
Phiên phòng thử: lịch sử lượt trong RAM, một hội thoại giả trong CSDL.

VÌ SAO KHÔNG GHI `messages`
---------------------------
Lượt thử ghi vào `messages` là sai số liệu tổng quan, chi phí, và "tin
khách mới nhất" — đúng những con số người vận hành dựa vào để biết hệ
thống có sống không. Phiên thử là thứ dùng xong bỏ; RAM là đúng chỗ.

VÌ SAO VẪN CẦN MỘT DÒNG `conversations`
---------------------------------------
`respond()` đọc `cost_usd` của hội thoại, và công cụ tra đơn lọc theo
`conversation_id`. Dòng ấy được gắn vào tài khoản kênh "Phòng thử" đã
TẮT, `mode='human'`, `state='closed'`: auto_routing, sla, canh gác và
danh sách hội thoại đều không nhìn thấy nó.
"""
from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass, field

from agent import db

TOI_DA_PHIEN = 20
TTL_GIAY = 7200
TOI_DA_LUOT = 30


class PhienDayLuot(RuntimeError):
    """Phiên đã đủ số lượt cho phép."""


@dataclass
class Phien:
    id: str
    conversation_id: uuid.UUID
    history: list[dict] = field(default_factory=list)
    luot: list[dict] = field(default_factory=list)
    chi_phi: float = 0.0
    tao_luc: float = 0.0
    cap_nhat: float = 0.0


_PHIEN: dict[str, Phien] = {}


def _bay_gio() -> float:
    return time.monotonic()


def xoa_het() -> None:
    _PHIEN.clear()


def _don() -> None:
    """Bỏ phiên quá TTL; nếu vẫn đầy, bỏ phiên cũ nhất theo lần dùng cuối."""
    bay_gio = _bay_gio()
    for k in [k for k, p in _PHIEN.items() if bay_gio - p.cap_nhat > TTL_GIAY]:
        _PHIEN.pop(k, None)
    while len(_PHIEN) >= TOI_DA_PHIEN:
        cu_nhat = min(_PHIEN.values(), key=lambda p: p.cap_nhat)
        _PHIEN.pop(cu_nhat.id, None)


async def hoi_thoai_thu(phien_id: str) -> uuid.UUID:
    """
    Tạo hoặc lấy hội thoại giả cho phòng thử.

    VÌ SAO MỘT HỘI THOẠI CHO TẤT CẢ PHIÊN
    -----------------------------------
    Lịch sử lượt nằm trong RAM theo phiên (từng phiên độc lập). Hội thoại
    giả chỉ để `respond()` đọc `cost_usd` và công cụ tra đơn lọc theo
    `conversation_id`. Mỗi phiên tạo một hội thoại mới là tích luỹ rác
    trong CSDL — một dòng cho mọi phiên là cách duy nhất không rác.
    """
    tk = await db.fetchrow(
        """
        INSERT INTO channel_accounts (channel, display_name, external_account_id,
                                      status, capabilities, metadata, is_legacy)
        VALUES ('webchat', 'Phòng thử agent', 'phong-thu', 'disabled', '{}', '{}', FALSE)
        ON CONFLICT (channel, external_account_id) DO UPDATE SET status = 'disabled'
        RETURNING id
        """
    )
    account_id = tk["id"]
    # Kiểm xem đã có contact cho tài khoản này chưa, để tái dùng.
    lien_he = await db.fetchrow(
        "SELECT c.id FROM contacts c JOIN contact_points p ON p.contact_id = c.id "
        "WHERE p.channel_account_id = $1 AND p.external_user_id = 'phong-thu' LIMIT 1",
        account_id,
    )
    if lien_he is None:
        lien_he = await db.fetchrow(
            "INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", "Khách thử"
        )
    contact_id = lien_he["id"]
    diem = await db.fetchrow(
        """
        INSERT INTO contact_points (contact_id, channel_account_id, external_user_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (channel_account_id, external_user_id) DO UPDATE SET last_seen = now()
        RETURNING id
        """,
        contact_id, account_id, "phong-thu",
    )
    conv = await db.fetchrow(
        """
        INSERT INTO conversations (account_id, contact_id, contact_point_id, channel,
                                   nen_tang, external_id, customer_name, customer_ref,
                                   mode, state)
        VALUES ($1, $2, $3, 'phong_thu', 'phong_thu', $4, 'Khách thử', '', 'human', 'closed')
        ON CONFLICT (account_id, external_id) DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        account_id, contact_id, diem["id"], "phong-thu",
    )
    return conv["id"]


async def tao_phien() -> Phien:
    _don()
    pid = secrets.token_urlsafe(8)
    conv_id = await hoi_thoai_thu(pid)
    p = Phien(id=pid, conversation_id=conv_id, tao_luc=_bay_gio(), cap_nhat=_bay_gio())
    _PHIEN[pid] = p
    return p


def lay_phien(pid: str) -> Phien | None:
    p = _PHIEN.get(pid)
    if p is None:
        return None
    if _bay_gio() - p.cap_nhat > TTL_GIAY:
        _PHIEN.pop(pid, None)
        return None
    return p


def xoa_phien(pid: str) -> bool:
    return _PHIEN.pop(pid, None) is not None


def ghi_luot(phien: Phien, cau_hoi: str, reply: dict, tra_loi: str) -> None:
    """
    Nối một lượt. `history` chỉ mang chữ (user/assistant), KHÔNG mang
    `tool_calls`: lượt sau không được kéo theo dấu vết công cụ của lượt
    trước, nếu không mô hình sẽ "nhớ" một kết quả đã cắt bớt.
    """
    if len(phien.luot) >= TOI_DA_LUOT:
        raise PhienDayLuot(f"Phiên đã đủ {TOI_DA_LUOT} lượt — tạo phiên mới.")
    phien.history.append({"role": "user", "content": cau_hoi})
    phien.history.append({"role": "assistant", "content": tra_loi})
    phien.luot.append({"khach": cau_hoi, "agent": tra_loi, "reply": reply})
    phien.chi_phi += float(reply.get("cost_usd") or 0.0)
    phien.cap_nhat = _bay_gio()
