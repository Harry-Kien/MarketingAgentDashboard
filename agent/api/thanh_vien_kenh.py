"""
Nhân viên được vào KÊNH nào — màn hình cho `account_memberships`.

VÌ SAO PHẢI CÓ MÀN NÀY
----------------------
Mọi phép lọc hội thoại và khách (`agent/api/inbox.py`, `agent/api/contacts.py`)
và bộ định tuyến tự động (`agent/omnichannel/auto_routing.py`) đều siết qua
`account_memberships`: người không phải thành viên của tài khoản kênh thì
không thấy hội thoại của kênh ấy, không thấy khách của kênh ấy, và không bao
giờ được bộ định tuyến giao việc.

Bảng ấy chỉ được ghi ở MỘT chỗ: người bấm nối kênh (OAuth, quét QR) thành
`owner`. Không endpoint nào, không màn hình nào thêm người khác vào. Hệ quả
đo được trên hệ thống thật ngày 14.09.2026: nhân viên "kiên" được giao 8
khách, là thành viên của 0 kênh, đăng nhập vào thấy 0 hội thoại và 0 khách —
kể cả 8 khách của chính mình. Không lỗi, không nhật ký, không gì trên màn
hình nói vì sao. Đúng lớp lỗi "hỏng im lặng" mà CLAUDE.md liệt kê.

QUYỀN
-----
`nguoi_dung.doc` để xem, `nguoi_dung.sua` để đổi — cùng họ với gán vai trò:
đây là câu hỏi "người này làm được gì", không phải "kênh này cấu hình sao".

`owner` KHÔNG bị gỡ qua đường này. Đó là dấu vết ai đã nối kênh, và là thứ
cho phép họ xem PII của khách kênh ấy. Gỡ owner là việc của màn Kết nối khi
nào có, không phải tác dụng phụ của một ô tick bỏ trống.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db

from .routes import can_quyen

router = APIRouter(prefix="/api", tags=["thanh-vien-kenh"])


class GanKenhIn(BaseModel):
    kenh: list[UUID] = Field(default_factory=list, max_length=500)
    # `manager` xem được PII của khách trong kênh; `agent` thì không.
    role: Literal["agent", "manager"] = "agent"


async def _nguoi(nguoi_dung_id: UUID) -> dict:
    nd = await db.fetchrow(
        "SELECT id, ten_dang_nhap, ho_ten, khoa FROM nguoi_dung WHERE id = $1",
        nguoi_dung_id)
    if nd is None:
        raise HTTPException(404, "Không tìm thấy nhân viên")
    nd["id"] = str(nd["id"])
    return nd


async def _danh_sach(nguoi_dung_id: UUID) -> list[dict[str, Any]]:
    # MỌI tài khoản kênh, kể cả `pending` và `disabled`: một Trang Facebook
    # đang chờ xác minh hôm nay là kênh nhận tin ngày mai, và người vận hành
    # muốn tick sẵn. Màn hình tự xếp kênh đang hoạt động lên trước.
    rows = await db.fetch(
        """
        SELECT ca.id, ca.channel, ca.display_name, ca.status,
               am.role
        FROM channel_accounts ca
        LEFT JOIN account_memberships am
          ON am.account_id = ca.id AND am.user_id = $1
        ORDER BY (ca.status = 'active') DESC, ca.channel, ca.display_name
        """,
        nguoi_dung_id,
    )
    for r in rows:
        r["id"] = str(r["id"])
        r["thanh_vien"] = r["role"] is not None
    return rows


@router.get("/nguoi-dung/{nguoi_dung_id}/kenh")
async def kenh_cua_nguoi(
    nguoi_dung_id: UUID,
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    nd = await _nguoi(nguoi_dung_id)
    kenh = await _danh_sach(nguoi_dung_id)
    return {
        "nguoi_dung": nd,
        "kenh": kenh,
        "so_thanh_vien": sum(1 for k in kenh if k["thanh_vien"]),
    }


@router.put("/nguoi-dung/{nguoi_dung_id}/kenh")
async def gan_kenh(
    nguoi_dung_id: UUID,
    body: GanKenhIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Đặt danh sách kênh của một người — ngữ nghĩa THAY THẾ, không cộng dồn.

    Ô tick trên màn hình là trạng thái đầy đủ; gửi lên "thêm" và "bớt" riêng
    rẽ là hai đường có thể lệch nhau, và đường ít dùng sẽ hỏng trước.
    """
    await _nguoi(nguoi_dung_id)
    muon = set(body.kenh)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if muon:
                so = await conn.fetchval(
                    "SELECT count(*) FROM channel_accounts WHERE id = ANY($1::uuid[])",
                    list(muon))
                if so != len(muon):
                    raise HTTPException(422, "Có tài khoản kênh không tồn tại")

            # Gỡ những gì KHÔNG còn trong danh sách — trừ `owner` (xem docstring
            # đầu tệp).
            da_go = await conn.fetch(
                """
                DELETE FROM account_memberships
                WHERE user_id = $1 AND role <> 'owner'
                  AND NOT (account_id = ANY($2::uuid[]))
                RETURNING account_id
                """,
                nguoi_dung_id, list(muon),
            )
            for tk in sorted(muon, key=str):
                await conn.execute(
                    """
                    INSERT INTO account_memberships (account_id, user_id, role)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (account_id, user_id) DO UPDATE
                    SET role = CASE WHEN account_memberships.role = 'owner'
                                    THEN 'owner' ELSE EXCLUDED.role END
                    """,
                    tk, nguoi_dung_id, body.role,
                )

    await db.log_event(
        "nguoi_dung.kenh", actor=nguoi.get("ten_dang_nhap", "?"),
        ref_id=nguoi_dung_id, so_kenh=len(muon), da_go=len(da_go),
        role=body.role)
    kenh = await _danh_sach(nguoi_dung_id)
    return {
        "nguoi_dung": await _nguoi(nguoi_dung_id),
        "kenh": kenh,
        "so_thanh_vien": sum(1 for k in kenh if k["thanh_vien"]),
        "da_go": len(da_go),
    }
