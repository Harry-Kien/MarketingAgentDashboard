"""API native inbox có account scope, unread và SSE replay được."""
from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from agent import db
from agent.config import settings
from agent.core import nhan as nhan_loi
from agent.omnichannel.routing import (
    AssignmentDenied,
    ConversationConflict,
    ConversationNotFound,
    ConversationRoutingService,
    PostgresRoutingRepository,
    RoutingError,
)

from .routes import can_quyen, chan_neu_ngoai_kenh


router = APIRouter(prefix="/api/inbox", tags=["native-inbox"])


@dataclass(frozen=True, slots=True)
class InboxFilters:
    account_id: UUID | None = None
    channel: str | None = None
    status: str | None = None
    assignee_id: UUID | None = None
    nhan: str | None = None
    q: str | None = None
    # Ba bộ lọc người trực hỏi nhiều nhất mà API trước đây không có: hội
    # thoại CHƯA AI NHẬN, NHÓM hay RIÊNG (gõ vào nhóm là nói với cả nhóm),
    # và đã QUÁ HẠN SLA (đúng định nghĩa cột `sla_breached` bên dưới).
    chua_giao: bool = False
    loai_thread: Literal["nhom", "rieng"] | None = None
    qua_han_sla: bool = False
    # Lọc theo nhãn hội thoại trong danh mục (0056). `nhan` (tên) ở trên giữ
    # cho đường cũ; id là đường chính — đổi tên nhãn không làm gãy bộ lọc
    # đang chọn trên màn hình.
    nhan_id: UUID | None = None


# Tên hiển thị của một người dùng: họ tên, không có thì tên đăng nhập. MỘT
# biểu thức cho mọi chỗ — tên người ở danh sách, ở tin nhắn và ở lịch sử
# phân công mà lệch nhau thì người đọc tưởng là ba người khác nhau.
def _ten_nguoi_sql(dieu_kien: str) -> str:
    return ("(SELECT coalesce(nullif(nd.ho_ten, ''), nd.ten_dang_nhap) "
            f"FROM nguoi_dung nd WHERE {dieu_kien})")


_LOAI_TAC_GIA = {"customer": "khach", "agent": "ai", "staff": "nhan_vien",
                 "system": "he_thong"}

# Người làm của một sự kiện: `actor` là id người dùng (dạng chữ) ở các đường
# của routing, còn "giải quyết" ghi người bấm vào `detail.boi`.
_TEN_NGUOI_LAM_SU_KIEN = _ten_nguoi_sql(
    "nd.id::text = coalesce(nullif(e.detail->>'boi', ''), e.actor)")

# Sự kiện đi vào lịch sử phân công. Nhận/tự giao KHÔNG có ở đây: lấy từ
# `conversation_assignments` (có nhóm và lúc kết thúc) — lấy cả hai nguồn là
# mỗi lần nhận hiện hai dòng.
_SU_KIEN_LICH_SU = {
    "conversation.escalated": ("chuyen_nguoi", "Chuyển cho người"),
    "khach.doi_gap_nguoi": ("khach_doi_nguoi", "Khách đòi gặp nhân viên"),
    "conversation.released": ("tra_ai", "Kết thúc tiếp quản, trả về AI"),
    "conversation.che_do": ("doi_che_do", "Đổi chế độ AI"),
    "conversation.resolved": ("giai_quyet", "Đã giải quyết"),
}

_TEN_CHE_DO = {"auto": "AI tự trả lời", "assist": "AI soạn, người duyệt trước khi gửi"}


def _iso(luc: Any) -> Any:
    return luc.isoformat() if isinstance(luc, datetime) else luc


def _muc_phan_cong(r: dict[str, Any]) -> dict[str, Any]:
    nhan = r.get("nguoi_nhan") or "(người đã xoá)"
    if r.get("source") == "auto":
        loai, tieu_de = "tu_giao", f"Tự giao cho {nhan}"
    elif r.get("actor_id") and r.get("actor_id") == r.get("assigned_user_id"):
        loai, tieu_de = "tiep_quan", f"{nhan} tiếp quản"
    else:
        loai, tieu_de = "giao", f"{r.get('nguoi_lam') or 'Hệ thống'} giao cho {nhan}"
    if r.get("nhom"):
        tieu_de += f" · nhóm {r['nhom']}"
    return {
        "luc": _iso(r.get("started_at")), "ket_thuc": _iso(r.get("ended_at")),
        "loai": loai, "tieu_de": tieu_de, "chi_tiet": r.get("reason") or "",
        "nguoi_lam": r.get("nguoi_lam") or ("Hệ thống" if loai == "tu_giao" else None),
        "nguoi_nhan": r.get("nguoi_nhan"), "nhom": r.get("nhom"),
    }


def _muc_su_kien(r: dict[str, Any]) -> dict[str, Any]:
    detail = _doc_json(r.get("detail")) or {}
    if not isinstance(detail, dict):
        detail = {}
    loai, tieu_de = _SU_KIEN_LICH_SU.get(str(r.get("kind")), ("khac", str(r.get("kind"))))
    chi_tiet = str(detail.get("reason") or detail.get("ly_do") or "")
    if loai == "doi_che_do":
        tieu_de = f"Đổi chế độ: {_TEN_CHE_DO.get(str(detail.get('che_do')), detail.get('che_do'))}"
    elif loai == "giai_quyet" and detail.get("tu_dong"):
        tieu_de = "Tự giải quyết"
    nguoi_lam = r.get("nguoi_lam")
    if nguoi_lam is None and r.get("actor") in (None, "", "system"):
        # Chuyển người do AI/hệ thống — nói rõ, đừng để trống như thể mất dữ liệu.
        nguoi_lam = "AI" if loai == "chuyen_nguoi" else "Hệ thống"
    return {"luc": _iso(r.get("created_at")), "ket_thuc": None, "loai": loai,
            "tieu_de": tieu_de, "chi_tiet": chi_tiet, "nguoi_lam": nguoi_lam,
            "nguoi_nhan": None, "nhom": None}


def _doc_json(gia_tri: Any) -> Any:
    """JSONB từ asyncpg: dict khi codec chạy, chuỗi với dữ liệu ghi kiểu cũ."""
    if isinstance(gia_tri, str):
        try:
            return json.loads(gia_tri)
        except ValueError:
            return None
    return gia_tri


def tac_gia(message: dict[str, Any]) -> dict[str, Any]:
    """
    AI ĐÃ LÀM GÌ, NGƯỜI NÀO ĐÃ LÀM GÌ với tin này — đọc được không cần SQL.

    Trước đây dashboard chỉ hiện "Nhân viên" (không tên) và "đã sửa bởi
    <tên đăng nhập>"; người duyệt bản nháp thì không hiện gì. Khi khách khiếu
    nại một câu, câu hỏi đầu tiên là "ai cho câu này đi" — câu trả lời nằm
    trong CSDL mà không ai đọc được.
    """
    role = str(message.get("role") or "")
    dv = _doc_json(message.get("dau_vet_ai")) or {}
    ten: str | None
    if role == "staff":
        ten = message.get("gui_boi_ten")
    elif role == "customer":
        ten = message.get("sender_name")
    elif role == "agent":
        ten = ((dv.get("ho_so") or {}).get("ten") if isinstance(dv, dict) else None)
    else:
        ten = None
    return {
        "loai": _LOAI_TAC_GIA.get(role, role),
        "ten": ten,
        "sua_boi": message.get("sua_boi_ten") or message.get("sua_boi"),
        "sua_luc": message.get("sua_luc"),
        "duyet_boi": message.get("duyet_boi_ten"),
        "duyet_luc": message.get("duyet_luc"),
    }


def mau_tim(q: str) -> str:
    """
    Chuỗi tìm cho `LIKE`, đã thoát ký tự đại diện.

    Không thoát thì gõ "%" là khớp MỌI hội thoại, và gõ "_" là khớp mọi ký
    tự — người trực tưởng tìm được, thật ra là đang xem cả danh sách.
    """
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_cursor(updated_at: datetime, conversation_id: UUID) -> str:
    raw = json.dumps(
        [updated_at.isoformat(), str(conversation_id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        timestamp, conversation_id = json.loads(
            base64.urlsafe_b64decode(padded).decode()
        )
        return datetime.fromisoformat(timestamp), UUID(conversation_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("cursor inbox không hợp lệ") from exc


class PostgresInboxQueryRepository:
    # Bộ lọc "Quá hạn SLA" — CÙNG điều kiện với cột `sla_breached` ở dưới.
    # Hai định nghĩa lệch nhau thì danh sách lọc ra hội thoại không mang huy
    # hiệu "Quá hạn SLA", và người trực thôi tin bộ lọc.
    _SLA_QUA_HAN_SQL = """
        (
            conversation.state IN ('open', 'pending')
            AND conversation.first_responded_at IS NULL
            AND conversation.first_response_due_at IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM sla_events breached
                WHERE breached.conversation_id = conversation.id
                  AND breached.kind = 'first_response_breached'
                  AND breached.due_at = conversation.first_response_due_at
            )
        )
    """.strip()

    _SLA_STATUS_COLUMNS_SQL = """
        (
            SELECT warn.created_at
            FROM sla_events warn
            WHERE warn.conversation_id = conversation.id
              AND warn.kind = 'first_response_warning'
              AND warn.due_at = conversation.first_response_due_at
            ORDER BY warn.created_at DESC
            LIMIT 1
        ) AS first_response_warning_at,
        (
            SELECT breached.created_at
            FROM sla_events breached
            WHERE breached.conversation_id = conversation.id
              AND breached.kind = 'first_response_breached'
              AND breached.due_at = conversation.first_response_due_at
            ORDER BY breached.created_at DESC
            LIMIT 1
        ) AS first_response_breached_at,
        (
            conversation.state IN ('open', 'pending')
            AND conversation.first_responded_at IS NULL
            AND conversation.first_response_due_at IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM sla_events warn
                WHERE warn.conversation_id = conversation.id
                  AND warn.kind = 'first_response_warning'
                  AND warn.due_at = conversation.first_response_due_at
            )
            AND NOT EXISTS (
                SELECT 1 FROM sla_events breached
                WHERE breached.conversation_id = conversation.id
                  AND breached.kind = 'first_response_breached'
                  AND breached.due_at = conversation.first_response_due_at
            )
        ) AS sla_warning,
    """.strip() + "\n" + _SLA_QUA_HAN_SQL + " AS sla_breached"

    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def list_conversations(
        self,
        *,
        user_id: UUID,
        is_admin: bool,
        filters: InboxFilters,
        cursor: tuple[datetime, UUID] | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        args: list[Any] = [user_id, is_admin]

        def bind(value: Any) -> str:
            args.append(value)
            return f"${len(args)}"

        clauses = [
            "($2 OR EXISTS ("
            "SELECT 1 FROM account_memberships membership "
            "WHERE membership.account_id = conversation.account_id "
            "AND membership.user_id = $1))"
        ]
        if filters.account_id is not None:
            clauses.append(f"conversation.account_id = {bind(filters.account_id)}")
        if filters.channel:
            clauses.append(f"account.channel = {bind(filters.channel)}")
        if filters.status:
            clauses.append(f"conversation.status = {bind(filters.status)}")
        if filters.assignee_id is not None:
            clauses.append(
                f"conversation.assigned_to = {bind(filters.assignee_id)}"
            )
        if filters.chua_giao:
            clauses.append("conversation.assigned_to IS NULL")
        if filters.loai_thread == "nhom":
            clauses.append("conversation.thread_type = 1")
        elif filters.loai_thread == "rieng":
            # NULL = hội thoại cũ/kênh không có khái niệm nhóm: là RIÊNG.
            clauses.append("coalesce(conversation.thread_type, 0) <> 1")
        if filters.qua_han_sla:
            clauses.append(self._SLA_QUA_HAN_SQL)
        if filters.nhan_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM hoi_thoai_gan_nhan nhan_loc "
                "WHERE nhan_loc.conversation_id = conversation.id "
                f"AND nhan_loc.nhan_id = {bind(filters.nhan_id)})"
            )
        if filters.nhan:
            clauses.append(
                "EXISTS (SELECT 1 FROM hoi_thoai_gan_nhan nhan_loc "
                "JOIN nhan nhan_ten ON nhan_ten.id = nhan_loc.nhan_id "
                "WHERE nhan_loc.conversation_id = conversation.id "
                f"AND lower(nhan_ten.ten) = lower({bind(' '.join(filters.nhan.split()))}))"
            )
        if filters.q:
            # Bỏ dấu + chữ thường ở CẢ hai phía: gõ "kem chong nang" ra tin
            # "Kem chống nắng". Biểu thức khớp đúng chỉ mục trigram của
            # 0029_tim_noi_dung_tin.sql — viết khác đi là quét cả bảng.
            mau = bind(mau_tim(filters.q))
            tim = f"'%' || lower(public.bo_dau({mau})) || '%'"
            clauses.append(
                f"(lower(public.bo_dau(coalesce(conversation.customer_name, ''))) LIKE {tim} "
                "OR EXISTS (SELECT 1 FROM messages tim_tin "
                "WHERE tim_tin.conversation_id = conversation.id "
                f"AND lower(public.bo_dau(tim_tin.content)) LIKE {tim}))"
            )
        if cursor is not None:
            ts_param = bind(cursor[0])
            id_param = bind(cursor[1])
            clauses.append(
                "(conversation.updated_at, conversation.id) "
                f"< ({ts_param}, {id_param})"
            )
        limit_param = bind(max(1, min(limit, 100)))
        sql = f"""
            SELECT conversation.id, conversation.account_id,
                   account.channel, account.display_name AS account_name,
                   conversation.nen_tang, conversation.customer_name,
                   conversation.customer_ref, conversation.status,
                   -- Nhóm Zalo (1): dashboard gắn nhãn "Nhóm" — người trực
                   -- phải biết trước khi mở là mình sắp nói với cả nhóm.
                   conversation.thread_type,
                   conversation.outcome, conversation.mode, conversation.state,
                   conversation.priority, conversation.assigned_to,
                   conversation.assigned_team_id, conversation.version,
                   {_ten_nguoi_sql("nd.id = conversation.assigned_to")} AS assigned_to_ten,
                   conversation.first_response_due_at,
                   conversation.first_responded_at,
                   conversation.resolution_due_at,
                   {self._SLA_STATUS_COLUMNS_SQL},
                   conversation.msg_count, conversation.updated_at,
                   latest.content AS last_message,
                   latest.delivery_status AS last_delivery_status,
                   -- `nhan`: mảng TÊN, giữ cho mã cũ. `nhan_chi_tiet`: id,
                   -- màu, đang dùng — thứ chip trên màn hình cần.
                   ARRAY(
                       SELECT nhan_hien.ten FROM hoi_thoai_gan_nhan nhan_gan
                       JOIN nhan nhan_hien ON nhan_hien.id = nhan_gan.nhan_id
                       WHERE nhan_gan.conversation_id = conversation.id
                       ORDER BY nhan_hien.thu_tu, lower(nhan_hien.ten)
                   ) AS nhan,
                   {nhan_loi.sql_nhan_da_gan("hoi_thoai_gan_nhan", "conversation_id", "conversation.id")}
                       AS nhan_chi_tiet,
                   (
                       SELECT count(*)
                       FROM messages unread_message
                       WHERE unread_message.conversation_id = conversation.id
                         AND unread_message.role = 'customer'
                         AND unread_message.created_at > coalesce(
                             read_state.last_read_at, 'epoch'::timestamptz
                         )
                   ) AS unread_count
            FROM conversations conversation
            JOIN channel_accounts account ON account.id = conversation.account_id
            LEFT JOIN conversation_reads read_state
              ON read_state.conversation_id = conversation.id
             AND read_state.user_id = $1
            LEFT JOIN LATERAL (
                SELECT content, delivery_status
                FROM messages
                WHERE conversation_id = conversation.id
                ORDER BY created_at DESC, id DESC
                LIMIT 1
            ) latest ON true
            WHERE {" AND ".join(clauses)}
            ORDER BY conversation.updated_at DESC, conversation.id DESC
            LIMIT {limit_param}
        """
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(sql, *args)
        return [dict(row) for row in rows]

    async def get_conversation(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> dict[str, Any] | None:
        sql = f"""
            SELECT conversation.*, account.display_name AS account_name,
                   account.channel AS account_channel,
                   {_ten_nguoi_sql("nd.id = conversation.assigned_to")} AS assigned_to_ten,
                   (SELECT team.name FROM teams team
                    WHERE team.id = conversation.assigned_team_id) AS assigned_team_ten,
                   {nhan_loi.sql_nhan_da_gan("hoi_thoai_gan_nhan", "conversation_id", "conversation.id")}
                       AS nhan_chi_tiet,
                   {self._SLA_STATUS_COLUMNS_SQL}
            FROM conversations conversation
            JOIN channel_accounts account ON account.id = conversation.account_id
            WHERE conversation.id = $1
              AND ($3 OR EXISTS (
                  SELECT 1 FROM account_memberships membership
                  WHERE membership.account_id = conversation.account_id
                    AND membership.user_id = $2
              ))
        """
        async with self._pool_provider().acquire() as connection:
            conversation = await connection.fetchrow(
                sql, conversation_id, user_id, is_admin
            )
            if conversation is None:
                return None
            messages = await connection.fetch(
                f"""
                SELECT message.*,
                       {_ten_nguoi_sql("nd.id = message.gui_boi")} AS gui_boi_ten,
                       {_ten_nguoi_sql("nd.id = message.duyet_boi")} AS duyet_boi_ten,
                       -- `sua_boi` là TÊN ĐĂNG NHẬP (cột cũ, TEXT), không phải id.
                       {_ten_nguoi_sql("nd.ten_dang_nhap = message.sua_boi")} AS sua_boi_ten,
                       coalesce(jsonb_agg(
                           jsonb_build_object(
                               'id', attachment.id,
                               'kind', attachment.kind,
                               -- Đã có bản trên máy chủ thì KHÔNG đưa link CDN:
                               -- dashboard thấy `url` rỗng là lấy
                               -- `/api/attachments/{id}/file` — bản không hết
                               -- hạn. Chưa tải được thì vẫn còn link gốc.
                               'url', CASE WHEN attachment.media_trang_thai = 'da_tai'
                                            AND attachment.media_sha256 IS NOT NULL
                                       THEN NULL ELSE attachment.url END,
                               'url_goc', attachment.url,
                               'media_trang_thai', attachment.media_trang_thai,
                               'original_url', attachment.original_url,
                               'storage_key', attachment.storage_key,
                               'mime_type', attachment.mime_type,
                               'metadata', attachment.metadata
                           ) ORDER BY attachment.ordinal
                       ) FILTER (WHERE attachment.id IS NOT NULL), '[]') attachments
                FROM messages message
                LEFT JOIN attachments attachment ON attachment.message_id = message.id
                WHERE message.conversation_id = $1
                GROUP BY message.id
                ORDER BY message.created_at, message.id
                """,
                conversation_id,
            )
        result = dict(conversation)
        result["messages"] = []
        for row in messages:
            message = dict(row)
            message["dau_vet_ai"] = _doc_json(message.get("dau_vet_ai"))
            message["tac_gia"] = tac_gia(message)
            result["messages"].append(message)
        return result

    _THAY_DUOC_SQL = """
        SELECT conversation.account_id
        FROM conversations conversation
        WHERE conversation.id = $1
          AND ($3 OR EXISTS (
              SELECT 1 FROM account_memberships membership
              WHERE membership.account_id = conversation.account_id
                AND membership.user_id = $2
          ))
    """

    async def lich_su_phan_cong(
        self, *, conversation_id: UUID, user_id: UUID, is_admin: bool,
    ) -> list[dict[str, Any]] | None:
        """
        Ai đã cầm hội thoại này, ai giao, lúc nào, vì sao — cũ trước mới sau.

        Gộp HAI nguồn: `conversation_assignments` (giao/nhận/tự giao, có lúc
        kết thúc) và `events` (AI chuyển người, trả về AI, đổi chế độ, giải
        quyết). Lần nhận/tự giao cũng có dòng `events`, nhưng lấy từ bảng
        phân công vì chỉ ở đó có NHÓM và LÚC KẾT THÚC. None = không thấy.
        """
        async with self._pool_provider().acquire() as connection:
            if await connection.fetchrow(
                    self._THAY_DUOC_SQL, conversation_id, user_id, is_admin) is None:
                return None
            phan_cong = await connection.fetch(
                f"""
                SELECT a.started_at, a.ended_at, a.source, a.reason,
                       a.assigned_user_id, a.actor_id,
                       {_ten_nguoi_sql("nd.id = a.assigned_user_id")} AS nguoi_nhan,
                       {_ten_nguoi_sql("nd.id = a.actor_id")} AS nguoi_lam,
                       (SELECT team.name FROM teams team
                        WHERE team.id = a.assigned_team_id) AS nhom
                FROM conversation_assignments a
                WHERE a.conversation_id = $1
                ORDER BY a.started_at DESC LIMIT 200
                """,
                conversation_id,
            )
            su_kien = await connection.fetch(
                f"""
                SELECT e.kind, e.created_at, e.actor, e.detail,
                       {_TEN_NGUOI_LAM_SU_KIEN} AS nguoi_lam
                FROM events e
                WHERE e.ref_id = $1 AND e.kind = ANY($2::text[])
                ORDER BY e.created_at DESC LIMIT 200
                """,
                conversation_id,
                list(_SU_KIEN_LICH_SU),
            )
        # Sắp theo DATETIME, không theo chuỗi ISO: `isoformat()` bỏ phần
        # micro-giây khi bằng 0, nên so chuỗi đảo thứ tự hai việc cùng giây.
        cap = [(r["started_at"], _muc_phan_cong(dict(r))) for r in phan_cong]
        cap += [(r["created_at"], _muc_su_kien(dict(r))) for r in su_kien]
        cap.sort(key=lambda x: x[0])
        return [m for _, m in cap]

    async def nguoi_nhan_duoc(
        self, *, conversation_id: UUID, user_id: UUID, is_admin: bool,
    ) -> dict[str, Any] | None:
        """
        Người và nhóm nhận được hội thoại này — CÙNG luật với `can_assign`.

        Chỉ thành viên kênh của hội thoại, chưa bị khoá. Kèm `co_the_giao_khac`
        để màn hình không bày ra một danh sách mà bấm vào chỉ nhận 403.
        """
        async with self._pool_provider().acquire() as connection:
            thay = await connection.fetchrow(
                self._THAY_DUOC_SQL, conversation_id, user_id, is_admin)
            if thay is None:
                return None
            account_id = thay["account_id"]
            nguoi = await connection.fetch(
                """
                SELECT nd.id, coalesce(nullif(nd.ho_ten, ''), nd.ten_dang_nhap) AS ten,
                       membership.role AS vai_tro_kenh,
                       coalesce(jsonb_agg(jsonb_build_object('id', team.id, 'ten', team.name))
                                FILTER (WHERE team.id IS NOT NULL), '[]') AS nhom,
                       (SELECT count(*) FROM conversations dang
                        WHERE dang.assigned_to = nd.id
                          AND dang.state IN ('open', 'pending'))::int AS dang_giu
                FROM account_memberships membership
                JOIN nguoi_dung nd ON nd.id = membership.user_id AND NOT nd.khoa
                LEFT JOIN team_members tm ON tm.user_id = nd.id
                LEFT JOIN teams team ON team.id = tm.team_id AND team.status = 'active'
                WHERE membership.account_id = $1
                GROUP BY nd.id, membership.role
                ORDER BY 2
                """,
                account_id,
            )
            quan_ly = is_admin or bool(await connection.fetchval(
                "SELECT EXISTS(SELECT 1 FROM account_memberships "
                "WHERE account_id = $1 AND user_id = $2 AND role IN ('owner', 'manager'))",
                account_id, user_id))
        ds = []
        for r in nguoi:
            d = dict(r)
            d["nhom"] = _doc_json(d.get("nhom")) or []
            ds.append(d)
        nhom: dict[str, str] = {}
        for d in ds:
            for t in d["nhom"]:
                nhom[str(t["id"])] = t["ten"]
        return {
            "nguoi": ds,
            "nhom": [{"id": k, "ten": v} for k, v in sorted(nhom.items(), key=lambda x: x[1])],
            "co_the_giao_khac": quan_ly,
        }

    async def bo_loc(self, *, user_id: UUID, is_admin: bool) -> dict[str, Any]:
        """Kênh và nhân viên người này THẤY được — nguồn cho các ô lọc hộp thư."""
        async with self._pool_provider().acquire() as connection:
            kenh = await connection.fetch(
                """
                SELECT account.id, account.display_name AS ten, account.channel
                FROM channel_accounts account
                WHERE ($2 OR EXISTS (
                    SELECT 1 FROM account_memberships membership
                    WHERE membership.account_id = account.id
                      AND membership.user_id = $1))
                ORDER BY account.display_name
                """,
                user_id, is_admin,
            )
            nguoi = await connection.fetch(
                """
                SELECT DISTINCT nd.id,
                       coalesce(nullif(nd.ho_ten, ''), nd.ten_dang_nhap) AS ten
                FROM account_memberships membership
                JOIN nguoi_dung nd ON nd.id = membership.user_id AND NOT nd.khoa
                WHERE ($2 OR EXISTS (
                    SELECT 1 FROM account_memberships mine
                    WHERE mine.account_id = membership.account_id
                      AND mine.user_id = $1))
                ORDER BY 2
                """,
                user_id, is_admin,
            )
        return {"kenh": [dict(r) for r in kenh], "nguoi": [dict(r) for r in nguoi]}

    async def mark_read(
        self,
        *,
        conversation_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        async with self._pool_provider().acquire() as connection:
            allowed = await connection.fetchrow(
                """
                SELECT conversation.account_id
                FROM conversations conversation
                WHERE conversation.id = $1
                  AND ($3 OR EXISTS (
                      SELECT 1 FROM account_memberships membership
                      WHERE membership.account_id = conversation.account_id
                        AND membership.user_id = $2
                  ))
                """,
                conversation_id,
                user_id,
                is_admin,
            )
            if allowed is None:
                return False
            await connection.execute(
                """
                INSERT INTO conversation_reads (
                    conversation_id, user_id, last_read_at
                ) VALUES ($1,$2,now())
                ON CONFLICT (conversation_id, user_id)
                DO UPDATE SET last_read_at = excluded.last_read_at
                """,
                conversation_id,
                user_id,
            )
        return True

    async def events_after(
        self,
        *,
        user_id: UUID,
        is_admin: bool,
        after: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT event.*
                FROM inbox_events event
                WHERE event.sequence_id > $1
                  AND ($4 OR EXISTS (
                      SELECT 1 FROM account_memberships membership
                      WHERE membership.account_id = event.account_id
                        AND membership.user_id = $2
                  ))
                ORDER BY event.sequence_id
                LIMIT $3
                """,
                max(0, after),
                user_id,
                max(1, min(limit, 500)),
                is_admin,
            )
        return [dict(row) for row in rows]


def _json_default(value: Any) -> str:
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError(f"không thể JSON hoá {type(value).__name__}")


async def event_stream(
    repository: PostgresInboxQueryRepository,
    *,
    user_id: UUID,
    is_admin: bool,
    after: int,
    poll_seconds: float = settings.sse_poll_seconds,
) -> AsyncIterator[str]:
    cursor = max(0, after)
    while True:
        events = await repository.events_after(
            user_id=user_id,
            is_admin=is_admin,
            after=cursor,
        )
        if events:
            for event in events:
                sequence = int(event["sequence_id"])
                cursor = max(cursor, sequence)
                data = json.dumps(event, default=_json_default, ensure_ascii=False)
                yield f"id: {sequence}\nevent: {event['topic']}\ndata: {data}\n\n"
        else:
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll_seconds)


def get_inbox_repository() -> PostgresInboxQueryRepository:
    return PostgresInboxQueryRepository()


def get_routing_service() -> ConversationRoutingService:
    return ConversationRoutingService(PostgresRoutingRepository())


def _user_scope(user: dict) -> tuple[UUID, bool]:
    """
    (id người dùng, có thấy hội thoại của MỌI kênh không).

    `hoi_thoai.xem_tat_ca` không nằm trong tập vai trò `Nhân viên` nạp sẵn,
    nên ngữ nghĩa lọc giữ nguyên hệt trước bản này — xem chú thích cùng ý ở
    `agent/api/contacts.py::_scope`.
    """
    return UUID(str(user["id"])), "hoi_thoai.xem_tat_ca" in user.get("quyen", ())


def resolve_event_cursor(after: int | None, last_event_id: str | None) -> int:
    """Query tường minh thắng header; header phục hồi kết nối SSE chuẩn."""
    if after is not None:
        return max(0, after)
    if not last_event_id:
        return 0
    try:
        return max(0, int(last_event_id))
    except ValueError as exc:
        raise ValueError("Last-Event-ID không hợp lệ") from exc


class TakeoverIn(BaseModel):
    assignee_id: UUID | None = None
    team_id: UUID | None = None
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ReleaseIn(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class DatCheDoIn(BaseModel):
    """
    Đổi giữa `auto` và `assist`.

    KHÔNG nhận `human`: chuyển sang human là GIAO VIỆC cho một người cụ thể,
    cần biết giao cho ai và mở bản ghi phân công — `takeover` làm việc đó.
    Nhận cả ba ở đây là hai đường cùng đổi một trường theo hai luật khác nhau.
    """

    che_do: Literal["auto", "assist"]
    expected_version: int = Field(ge=1)
    # Cùng luật với takeover/release: nhật ký ghi "ai đó bật auto lúc 2 giờ
    # sáng" mà không có lý do thì nó không dùng được khi cần truy.
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _ly_do_khong_duoc_toan_khoang_trang(cls, v: str) -> str:
        """
        `min_length` đếm cả khoảng trắng, nên "   " lọt qua.

        Một lý do toàn dấu cách ghi vào nhật ký kiểm toán trông y hệt một lý
        do thật cho tới lúc có người mở ra đọc — và lúc đó thì đã cần nó rồi.
        """
        v = v.strip()
        if len(v) < 3:
            raise ValueError("lý do phải có ít nhất 3 ký tự thực")
        return v


def _routing_response(state) -> dict[str, Any]:
    return {
        "conversation_id": str(state.conversation_id),
        "mode": state.mode,
        "status": state.status,
        "assigned_to": str(state.assigned_to) if state.assigned_to else None,
        "assigned_team_id": (
            str(state.assigned_team_id) if state.assigned_team_id else None
        ),
        "version": state.version,
    }


def _raise_routing(exc: RoutingError) -> None:
    if isinstance(exc, ConversationNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, AssignmentDenied):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, ConversationConflict):
        raise HTTPException(409, str(exc)) from exc
    raise exc


@router.get("/conversations")
async def list_inbox_conversations(
    account_id: UUID | None = None,
    channel: str | None = None,
    status: str | None = None,
    assignee_id: UUID | None = None,
    nhan: str | None = Query(None, max_length=80),
    nhan_id: UUID | None = None,
    q: str | None = Query(None, max_length=100),
    chua_giao: bool = False,
    loai: Literal["nhom", "rieng"] | None = None,
    qua_han_sla: bool = False,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    decoded = None
    if cursor:
        try:
            decoded = decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    if chua_giao and assignee_id is not None:
        # Hai điều kiện loại trừ nhau: trả danh sách rỗng là để người trực
        # tưởng "không có hội thoại nào" — nói thẳng là bộ lọc mâu thuẫn.
        raise HTTPException(422, "chua_giao và assignee_id không dùng cùng nhau")
    user_id, is_admin = _user_scope(user)
    rows = await repository.list_conversations(
        user_id=user_id,
        is_admin=is_admin,
        # Dưới 2 ký tự thì bỏ qua: "a" khớp gần như mọi tin, một lượt quét
        # tốn mà không thu hẹp được gì.
        filters=InboxFilters(account_id, channel, status, assignee_id,
                             (nhan or "").strip() or None,
                             q.strip() if q and len(q.strip()) >= 2 else None,
                             chua_giao=chua_giao, loai_thread=loai,
                             qua_han_sla=qua_han_sla, nhan_id=nhan_id),
        cursor=decoded,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = None
    if has_more and visible:
        tail = visible[-1]
        next_cursor = encode_cursor(tail["updated_at"], tail["id"])
    return {"items": visible, "next_cursor": next_cursor}


@router.get("/conversations/{conversation_id}")
async def inbox_conversation_detail(
    conversation_id: UUID,
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    user_id, is_admin = _user_scope(user)
    conversation = await repository.get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    if conversation is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return conversation


@router.get("/conversations/{conversation_id}/lich-su-phan-cong")
async def lich_su_phan_cong(
    conversation_id: UUID,
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    """
    Dòng thời gian bàn giao: AI chuyển người, ai nhận, ai giao cho ai, trả AI.

    `conversation_assignments` ghi đủ từ 0005 nhưng không có đường nào đọc:
    câu "ai đã cầm khách này lúc 9 giờ" chỉ trả lời được bằng SQL tay.
    """
    user_id, is_admin = _user_scope(user)
    muc = await repository.lich_su_phan_cong(
        conversation_id=conversation_id, user_id=user_id, is_admin=is_admin)
    if muc is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return {"items": muc}


@router.get("/conversations/{conversation_id}/nguoi-nhan-duoc")
async def nguoi_nhan_duoc(
    conversation_id: UUID,
    user: dict = Depends(can_quyen("hoi_thoai.nhan")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    """Danh sách cho ô "Giao cho…" — máy chủ vẫn kiểm lại lúc giao (`can_assign`)."""
    user_id, is_admin = _user_scope(user)
    kq = await repository.nguoi_nhan_duoc(
        conversation_id=conversation_id, user_id=user_id, is_admin=is_admin)
    if kq is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return kq


@router.get("/bo-loc")
async def bo_loc_hop_thu(
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, Any]:
    """Kênh và người để dựng ô lọc — chỉ những gì người này THẤY được."""
    user_id, is_admin = _user_scope(user)
    return await repository.bo_loc(user_id=user_id, is_admin=is_admin)


@router.post("/conversations/{conversation_id}/read")
async def mark_inbox_read(
    conversation_id: UUID,
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> dict[str, bool]:
    user_id, is_admin = _user_scope(user)
    if not await repository.mark_read(
        conversation_id=conversation_id,
        user_id=user_id,
        is_admin=is_admin,
    ):
        raise HTTPException(404, "Không tìm thấy hội thoại")
    return {"ok": True}


@router.post("/conversations/{conversation_id}/takeover")
async def takeover_conversation(
    conversation_id: UUID,
    body: TakeoverIn,
    user: dict = Depends(can_quyen("hoi_thoai.nhan")),
    service: ConversationRoutingService = Depends(get_routing_service),
) -> dict[str, Any]:
    actor_id, is_admin = _user_scope(user)
    try:
        state = await service.takeover(
            conversation_id=conversation_id,
            actor_id=actor_id,
            assignee_id=body.assignee_id or actor_id,
            team_id=body.team_id,
            expected_version=body.expected_version,
            reason=body.reason,
            actor_is_admin=is_admin,
        )
    except RoutingError as exc:
        _raise_routing(exc)
    # Giao cho NGƯỜI KHÁC thì người ấy phải biết — không thì hội thoại nằm
    # trong "của tôi" của họ mà họ không hay. Tự nhận thì hàm tự bỏ qua.
    # Gọi SAU giao dịch giao: chuông hỏng không được làm hỏng lượt giao.
    if state.assigned_to is not None:
        from agent.core import thong_bao_noi_bo

        await thong_bao_noi_bo.bao_duoc_giao_hoi_thoai(
            conversation_id, state.assigned_to, boi=actor_id)
    return _routing_response(state)


def get_buoc_gianh_quyen_meta() -> Callable[[UUID], Any]:
    """
    Bước Messenger sau release: đổi cờ trong CSDL chưa đủ, phải giành lại
    thread control từ Meta — xem `hoi_thoai_cu.nhan_lai_quyen_sau_release`.
    Là dependency để test router trần (không CSDL) thay được, giống
    `get_routing_service`. Import muộn để tránh vòng import với route cũ.
    """
    from .hoi_thoai_cu import nhan_lai_quyen_sau_release

    return nhan_lai_quyen_sau_release


@router.post("/conversations/{conversation_id}/release")
async def release_conversation(
    conversation_id: UUID,
    body: ReleaseIn,
    user: dict = Depends(can_quyen("hoi_thoai.nhan")),
    service: ConversationRoutingService = Depends(get_routing_service),
    gianh_quyen: Callable[[UUID], Any] = Depends(get_buoc_gianh_quyen_meta),
) -> dict[str, Any]:
    actor_id, is_admin = _user_scope(user)
    try:
        state = await service.release(
            conversation_id=conversation_id,
            actor_id=actor_id,
            expected_version=body.expected_version,
            reason=body.reason,
            actor_is_admin=is_admin,
        )
    except RoutingError as exc:
        _raise_routing(exc)
    result = _routing_response(state)
    # Chưa giành lại được quyền Meta thì nói ra (dashboard hiện thành lỗi):
    # thiếu bước này agent "bật mà câm" với Messenger.
    if ghi_chu := await gianh_quyen(conversation_id):
        result["ghi_chu"] = ghi_chu
    return result


@router.post("/conversations/{conversation_id}/che-do")
async def dat_che_do_conversation(
    conversation_id: UUID,
    body: DatCheDoIn,
    user: dict = Depends(can_quyen("hoi_thoai.nhan")),
    service: ConversationRoutingService = Depends(get_routing_service),
) -> dict[str, Any]:
    """
    Trả hội thoại về cho agent tự xử lý, hoặc bắt duyệt trước khi gửi.

    Trước khi có đường này, hội thoại rơi xuống `assist` hoặc `human` là KẸT
    ở đó vĩnh viễn: chỉ có nút đi xuống, không có nút đi lên. Người trực xử
    lý xong một ca khó rồi muốn trả lại cho agent — không có cách nào. Mọi
    hội thoại cũ dồn dần vào hàng chờ duyệt.

    Phạm vi kênh chặn HAI lần: ở đây (404 trước khi đụng khoá hội thoại) và
    trong `dat_che_do` (route khác gọi service cũng không lọt).
    """
    await chan_neu_ngoai_kenh(conversation_id, user)
    actor_id, is_admin = _user_scope(user)
    try:
        state = await service.dat_che_do(
            conversation_id=conversation_id,
            actor_id=actor_id,
            che_do=body.che_do,
            expected_version=body.expected_version,
            reason=body.reason,
            actor_is_admin=is_admin,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RoutingError as exc:
        _raise_routing(exc)
    return _routing_response(state)


@router.get("/events")
async def inbox_events(
    after: int | None = Query(None, ge=0),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    user: dict = Depends(can_quyen("hoi_thoai.doc")),
    repository: PostgresInboxQueryRepository = Depends(get_inbox_repository),
) -> StreamingResponse:
    user_id, is_admin = _user_scope(user)
    try:
        cursor = resolve_event_cursor(after, last_event_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return StreamingResponse(
        event_stream(
            repository,
            user_id=user_id,
            is_admin=is_admin,
            after=cursor,
            poll_seconds=settings.sse_poll_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
