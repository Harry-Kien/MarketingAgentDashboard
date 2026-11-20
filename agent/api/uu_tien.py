"""
Đổi mức ưu tiên của một hội thoại — có lý do, có nhật ký, không né được SLA.

LUẬT ĐÃ CHỌN: ĐỔI HAI CHIỀU, NHƯNG HẠN CHỈ ĐƯỢC RÚT NGẮN
--------------------------------------------------------
Trước bản này `conversations.priority` không ai đổi được, nên chỉ chính sách
SLA mức `normal` từng có hiệu lực. Cho đổi ưu tiên thì phải trả lời: đổi
giữa chừng một chu kỳ SLA thì hạn đang chạy ra sao?

* NÂNG ưu tiên → hạn = min(hạn cũ, BÂY GIỜ + số phút của chính sách mới).
  Tính từ BÂY GIỜ chứ không từ lúc khách nhắn: tính lùi thì nâng "gấp" ở
  phút thứ 20 với hạn gấp 5 phút là trễ ngay tức khắc — và người ta sẽ
  thôi nâng ưu tiên để khỏi bị tính trễ. Một luật phạt người làm đúng là
  luật sinh ra hành vi sai.
* HẠ ưu tiên → hạn của chu kỳ đang chạy GIỮ NGUYÊN. Mức mới áp dụng từ chu
  kỳ sau (khi hội thoại mở lại). Hạ ưu tiên để "tặng thêm giờ" cho hội
  thoại sắp trễ là đúng kiểu né vi phạm.
* Hội thoại chưa có hạn (không có chính sách lúc tạo) → vẫn không có hạn
  trong chu kỳ này. Đổi ưu tiên không dựng một SLA mới giữa chừng.
* Hạn đã qua, hay mục tiêu đã đạt (đã phản hồi / đã giải quyết) → không đụng.

Luật "chỉ rút ngắn" nằm HAI chỗ: ở đây, và ở trigger
`prevent_sla_deadline_reset` (migration 0054) — kể cả một câu UPDATE gõ tay
cũng không kéo dài được hạn trong cùng chu kỳ.

Quyền `hoi_thoai.nhan` (nhận và chuyển hội thoại) + phạm vi kênh: người
được điều phối hội thoại là người đánh giá được độ gấp của nó.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.omnichannel.sla_gio import bieu_thuc_han, gio_sla

from .phu_thuoc import can_quyen, chan_neu_ngoai_kenh

router = APIRouter(prefix="/api/conversations", tags=["uu-tien"])

BAC = {"low": 0, "normal": 1, "high": 2, "urgent": 3}


class DoiUuTienIn(BaseModel):
    uu_tien: Literal["low", "normal", "high", "urgent"]
    # Bắt buộc lý do: đổi ưu tiên đổi hạn SLA, và người đọc nhật ký sau này
    # cần biết vì sao — "khách VIP", "khiếu nại", không phải chỉ "ai bấm".
    ly_do: str = Field(min_length=3, max_length=500)
    version: int | None = None


# Chính sách cho mức MỚI — cùng luật chọn với `giai_quyet._CHON_CHINH_SACH`:
# đúng mức (lui về `normal`), chính sách riêng của kênh thắng chính sách chung.
_SQL_HAN_MOI = """
    SELECT {han_dau} AS han_dau, {han_xong} AS han_xong
    FROM sla_policies policy
    WHERE policy.active
      AND policy.priority IN ($1, 'normal')
      AND (policy.account_id = $2 OR policy.account_id IS NULL)
    ORDER BY (policy.account_id IS NOT NULL) DESC, (policy.priority = $1) DESC
    LIMIT 1
"""


def han_sau_khi_doi(*, nang: bool, han_cu, han_chinh_sach, da_dat: bool, bay_gio):
    """
    Hạn mới của MỘT mục tiêu SLA. Hàm thuần — luật ở docstring module.

    `da_dat`: mục tiêu đã đạt (đã phản hồi đầu / đã giải quyết).
    """
    if not nang or da_dat or han_cu is None or han_chinh_sach is None:
        return han_cu
    if han_cu <= bay_gio:
        return han_cu
    return min(han_cu, han_chinh_sach)


@router.put("/{cid}/uu-tien")
async def doi_uu_tien(
    cid: uuid.UUID, body: DoiUuTienIn,
    nguoi: dict = Depends(can_quyen("hoi_thoai.nhan")),
) -> dict[str, Any]:
    await chan_neu_ngoai_kenh(cid, nguoi)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            c = await conn.fetchrow(
                "SELECT id, account_id, priority, state, version, sla_chu_ky, "
                "first_response_due_at, resolution_due_at, first_responded_at, "
                "resolved_at, now() AS bay_gio "
                "FROM conversations WHERE id = $1 FOR UPDATE", cid)
            if c is None:
                raise HTTPException(404, "Không thấy hội thoại")
            if c["state"] not in ("open", "pending"):
                raise HTTPException(409, "Hội thoại đã giải quyết — ưu tiên chỉ đổi khi còn mở.")
            if body.version is not None and body.version != c["version"]:
                raise HTTPException(409, "Hội thoại vừa thay đổi — tải lại rồi thử lại.")
            if body.uu_tien == c["priority"]:
                raise HTTPException(422, "Hội thoại đã ở mức ưu tiên này.")

            nang = BAC[body.uu_tien] > BAC[c["priority"]]
            moi = await conn.fetchrow(
                _SQL_HAN_MOI
                .replace("{han_dau}", bieu_thuc_han("first_response_minutes", 3, 4))
                .replace("{han_xong}", bieu_thuc_han("resolution_minutes", 3, 4)),
                body.uu_tien, c["account_id"], *gio_sla()) or {}
            han_dau = han_sau_khi_doi(
                nang=nang, han_cu=c["first_response_due_at"],
                han_chinh_sach=moi.get("han_dau"),
                da_dat=c["first_responded_at"] is not None, bay_gio=c["bay_gio"])
            han_xong = han_sau_khi_doi(
                nang=nang, han_cu=c["resolution_due_at"],
                han_chinh_sach=moi.get("han_xong"),
                da_dat=c["resolved_at"] is not None, bay_gio=c["bay_gio"])

            r = await conn.fetchrow(
                "UPDATE conversations SET priority = $2, first_response_due_at = $3, "
                "resolution_due_at = $4, version = version + 1, updated_at = now() "
                "WHERE id = $1 RETURNING priority, version, first_response_due_at, "
                "resolution_due_at", cid, body.uu_tien, han_dau, han_xong)

            # Cảnh báo 50% đã ghi theo hạn CŨ thì dời theo hạn mới: hộp thư so
            # `sla_events.due_at` với hạn hiện hành, lệch là dấu "Sắp hết SLA"
            # biến mất đúng lúc hạn vừa bị rút gần hơn. Hạn cũ giữ trong detail.
            for kind, cu, moi_han in (
                ("first_response_warning", c["first_response_due_at"], r["first_response_due_at"]),
                ("resolution_warning", c["resolution_due_at"], r["resolution_due_at"]),
            ):
                if cu is not None and moi_han != cu:
                    await conn.execute(
                        "UPDATE sla_events SET due_at = $4, "
                        "detail = detail || jsonb_build_object('han_truoc_khi_doi_uu_tien', $3::timestamptz) "
                        "WHERE conversation_id = $1 AND chu_ky = $2 AND kind = $5 AND due_at = $3",
                        cid, c["sla_chu_ky"], cu, moi_han, kind)

            def _iso(x):
                return x.isoformat() if x else None

            chi_tiet = {
                "tu": c["priority"], "den": body.uu_tien, "ly_do": body.ly_do.strip(),
                "chu_ky": c["sla_chu_ky"],
                "han_dau_cu": _iso(c["first_response_due_at"]),
                "han_dau_moi": _iso(r["first_response_due_at"]),
                "han_xong_cu": _iso(c["resolution_due_at"]),
                "han_xong_moi": _iso(r["resolution_due_at"]),
            }
            # Nhật ký kiểm toán TRONG giao dịch: đổi ưu tiên mà không để lại
            # dấu thì không ai trả lời được "vì sao hạn của khách này đổi".
            await conn.execute(
                "INSERT INTO events (kind, actor, ref_id, detail) "
                "VALUES ('conversation.priority_changed', $1, $2, $3)",
                nguoi.get("ten_dang_nhap") or str(nguoi.get("id")), cid, chi_tiet)
            await conn.execute(
                "INSERT INTO inbox_events (account_id, topic, ref_id, payload) "
                "VALUES ($1, 'conversation.priority_changed', $2, $3)",
                c["account_id"], cid, {"tu": c["priority"], "den": body.uu_tien})
    return {"uu_tien": r["priority"], "version": r["version"], **{
        k: chi_tiet[k] for k in ("han_dau_cu", "han_dau_moi", "han_xong_cu", "han_xong_moi")}}
