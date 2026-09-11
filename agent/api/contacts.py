"""API Customer 360: account-scoped, PII theo role và merge có preview."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.omnichannel.identity import (
    ContactConflict,
    ContactNotFound,
    IdentityError,
    IdentityService,
    InvalidMerge,
    PostgresIdentityRepository,
)

from agent.core import pham_vi, truong_khach

from .routes import can_quyen


router = APIRouter(prefix="/api/contacts", tags=["customer-360"])


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    return "*" * max(0, len(value) - 3) + value[-3:]


def _mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return "***" if value else value
    local, domain = value.rsplit("@", 1)
    return (local[:1] or "*") + "***@" + domain


def mask_contact_pii(contact: Mapping[str, Any]) -> dict[str, Any]:
    public = dict(contact)
    can_view = bool(public.pop("can_view_pii", False))
    if not can_view:
        public["phone"] = _mask_phone(public.get("phone"))
        public["email"] = _mask_email(public.get("email"))
    public["pii_masked"] = not can_view
    return public


class MergeContactsIn(BaseModel):
    source_id: UUID
    target_id: UUID
    reason: str = Field(min_length=3, max_length=500)
    expected_source_version: int = Field(ge=1)
    expected_target_version: int = Field(ge=1)


class UnmergeContactIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ContactTagIn(BaseModel):
    tag: str = Field(min_length=1, max_length=80)


class ContactNoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: str = Field(default="team", pattern="^(team|manager)$")


class ContactConsentIn(BaseModel):
    status: str = Field(pattern="^(granted|denied|withdrawn)$")
    source: str = Field(min_length=2, max_length=300)
    account_id: UUID | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class RetentionRequestIn(BaseModel):
    kind: str = Field(pattern="^(export|delete|retention)$")
    reason: str = Field(min_length=3, max_length=500)
    dry_run: bool = True


class PostgresContactRepository:
    def __init__(self, pool_provider: Callable[[], Any] = db.pool):
        self._pool_provider = pool_provider

    async def list_visible(
        self,
        *,
        user_id: UUID,
        is_admin: bool,
        query: str,
        account_id: UUID | None,
        limit: int,
        nguoi: dict[str, Any] | None = None,
        muc: str = pham_vi.MUC_MAC_DINH,
    ) -> list[dict[str, Any]]:
        # Mệnh đề phạm vi đến từ MỘT chỗ duy nhất — xem `agent/core/pham_vi.py`.
        # Viết tay ở đây là bản sao thứ hai của bốn nhánh lọc, và bản sao sẽ
        # lệch mà không nổ.
        loc, tham_so_pham_vi = pham_vi.dieu_kien_khach(
            nguoi=nguoi or {"id": user_id, "quyen": frozenset()},
            muc=muc, so_tham_so=5, bi_danh="contact",
        )
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                f"""
                SELECT contact.id, contact.display_name, contact.phone,
                       contact.email, contact.profile, contact.status,
                       contact.version, contact.first_seen, contact.last_seen,
                       contact.owner_user_id,
                       chu.ho_ten AS owner_ho_ten,
                       chu.ten_dang_nhap AS owner_ten_dang_nhap,
                       ($2 OR EXISTS (
                           SELECT 1 FROM contact_points pii_point
                           JOIN account_memberships pii_membership
                             ON pii_membership.account_id = pii_point.channel_account_id
                            AND pii_membership.user_id = $1
                            AND pii_membership.role IN ('owner', 'manager')
                           WHERE pii_point.contact_id = contact.id
                       )) AS can_view_pii,
                       (
                           SELECT count(*) FROM contact_points count_point
                           WHERE count_point.contact_id = contact.id
                       ) AS contact_point_count,
                       (
                           SELECT count(*) FROM conversations count_conversation
                           WHERE count_conversation.contact_id = contact.id
                       ) AS conversation_count
                FROM contacts contact
                LEFT JOIN nguoi_dung chu ON chu.id = contact.owner_user_id
                WHERE contact.status <> 'deleted'
                  AND {loc}
                  AND EXISTS (
                      SELECT 1 FROM contact_points visible_point
                      LEFT JOIN account_memberships visible_membership
                        ON visible_membership.account_id = visible_point.channel_account_id
                       AND visible_membership.user_id = $1
                      WHERE visible_point.contact_id = contact.id
                        AND ($2 OR visible_membership.user_id IS NOT NULL)
                        AND ($4::uuid IS NULL OR visible_point.channel_account_id = $4)
                  )
                  AND (
                      $3 = '' OR contact.display_name ILIKE '%' || $3 || '%'
                      OR ($2 AND (
                          contact.phone ILIKE '%' || $3 || '%'
                          OR contact.email ILIKE '%' || $3 || '%'
                      ))
                  )
                ORDER BY contact.last_seen DESC, contact.id DESC
                LIMIT $5
                """,
                user_id,
                is_admin,
                query,
                account_id,
                max(1, min(limit, 100)),
                *tham_so_pham_vi,
            )
        return [dict(row) for row in rows]

    async def get_visible(
        self,
        *,
        contact_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> dict[str, Any] | None:
        async with self._pool_provider().acquire() as connection:
            contact = await connection.fetchrow(
                """
                SELECT contact.*,
                       chu.ho_ten AS owner_ho_ten,
                       chu.ten_dang_nhap AS owner_ten_dang_nhap,
                       ($3 OR EXISTS (
                           SELECT 1 FROM contact_points point
                           JOIN account_memberships membership
                             ON membership.account_id = point.channel_account_id
                            AND membership.user_id = $2
                            AND membership.role IN ('owner', 'manager')
                           WHERE point.contact_id = contact.id
                       )) AS can_view_pii
                FROM contacts contact
                LEFT JOIN nguoi_dung chu ON chu.id = contact.owner_user_id
                WHERE contact.id = $1
                  AND EXISTS (
                      SELECT 1 FROM contact_points point
                      LEFT JOIN account_memberships membership
                        ON membership.account_id = point.channel_account_id
                       AND membership.user_id = $2
                      WHERE point.contact_id = contact.id
                        AND ($3 OR membership.user_id IS NOT NULL)
                  )
                """,
                contact_id,
                user_id,
                is_admin,
            )
            if contact is None:
                return None
            points = await connection.fetch(
                """
                SELECT point.id, point.channel_account_id, account.channel,
                       account.display_name AS account_name,
                       point.external_user_id, point.handle,
                       point.verified_fields, point.metadata,
                       point.first_seen, point.last_seen
                FROM contact_points point
                JOIN channel_accounts account ON account.id = point.channel_account_id
                LEFT JOIN account_memberships membership
                  ON membership.account_id = point.channel_account_id
                 AND membership.user_id = $2
                WHERE point.contact_id = $1
                  AND ($3 OR membership.user_id IS NOT NULL)
                ORDER BY point.last_seen DESC
                """,
                contact_id,
                user_id,
                is_admin,
            )
            conversations = await connection.fetch(
                """
                SELECT conversation.id, conversation.account_id,
                       conversation.status, conversation.outcome,
                       conversation.updated_at, account.channel,
                       account.display_name AS account_name
                FROM conversations conversation
                JOIN channel_accounts account ON account.id = conversation.account_id
                LEFT JOIN account_memberships membership
                  ON membership.account_id = conversation.account_id
                 AND membership.user_id = $2
                WHERE conversation.contact_id = $1
                  AND ($3 OR membership.user_id IS NOT NULL)
                ORDER BY conversation.updated_at DESC
                LIMIT 100
                """,
                contact_id,
                user_id,
                is_admin,
            )
            tags = await connection.fetch(
                "SELECT tag, created_at FROM contact_tags "
                "WHERE contact_id = $1 ORDER BY tag",
                contact_id,
            )
            notes = await connection.fetch(
                """
                SELECT id, body, visibility, created_by, created_at, updated_at
                FROM contact_notes
                WHERE contact_id = $1
                  AND (visibility = 'team' OR $2)
                ORDER BY created_at DESC
                LIMIT 100
                """,
                contact_id,
                bool(contact["can_view_pii"]),
            )
            consents = await connection.fetch(
                """
                SELECT id, account_id, purpose, status, source,
                       CASE WHEN $2 THEN evidence ELSE '{}'::jsonb END AS evidence,
                       captured_at, updated_at
                FROM contact_consents
                WHERE contact_id = $1
                ORDER BY purpose, account_id NULLS FIRST
                """,
                contact_id,
                bool(contact["can_view_pii"]),
            )
        result = dict(contact)
        result["contact_points"] = [dict(row) for row in points]
        result["conversations"] = [dict(row) for row in conversations]
        result["tags"] = [dict(row) for row in tags]
        result["notes"] = [dict(row) for row in notes]
        result["consents"] = [dict(row) for row in consents]
        return result

    async def merge_preview(
        self,
        *,
        source_id: UUID,
        target_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> dict[str, Any] | None:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT contact.id, contact.display_name, contact.status,
                       contact.version,
                       count(point.id) AS point_count,
                       count(point.id) FILTER (
                           WHERE $3 OR membership.user_id IS NOT NULL
                       ) AS visible_count,
                       count(point.id) FILTER (
                           WHERE $3 OR membership.role IN ('owner', 'manager')
                       ) AS manageable_count,
                       (SELECT count(*) FROM conversations conversation
                        WHERE conversation.contact_id = contact.id) AS conversation_count
                FROM contacts contact
                LEFT JOIN contact_points point ON point.contact_id = contact.id
                LEFT JOIN account_memberships membership
                  ON membership.account_id = point.channel_account_id
                 AND membership.user_id = $3
                WHERE contact.id = ANY($1::uuid[])
                GROUP BY contact.id
                """,
                [source_id, target_id],
                user_id,
                is_admin,
            )
        by_id = {row["id"]: dict(row) for row in rows}
        if source_id not in by_id or target_id not in by_id:
            return None
        source = by_id[source_id]
        target = by_id[target_id]
        if not source["visible_count"] or not target["visible_count"]:
            return None
        can_manage = all(
            int(item["point_count"]) == int(item["manageable_count"])
            for item in (source, target)
        )
        return {"source": source, "target": target, "can_manage": can_manage}

    async def can_manage_merge(
        self,
        *,
        merge_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        if is_admin:
            return True
        async with self._pool_provider().acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT count(point.id) > 0
                       AND bool_and(membership.role IN ('owner', 'manager'))
                    FROM contact_merges merge_row
                    JOIN contact_points point
                      ON point.contact_id = merge_row.target_contact_id
                    LEFT JOIN account_memberships membership
                      ON membership.account_id = point.channel_account_id
                     AND membership.user_id = $2
                    WHERE merge_row.id = $1 AND merge_row.status = 'active'
                    """,
                    merge_id,
                    user_id,
                )
            )

    async def can_manage_contact(
        self,
        *,
        contact_id: UUID,
        user_id: UUID,
        is_admin: bool,
    ) -> bool:
        if is_admin:
            return True
        async with self._pool_provider().acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT count(point.id) > 0
                       AND bool_and(membership.role IN ('owner', 'manager'))
                    FROM contact_points point
                    LEFT JOIN account_memberships membership
                      ON membership.account_id = point.channel_account_id
                     AND membership.user_id = $2
                    WHERE point.contact_id = $1
                    """,
                    contact_id,
                    user_id,
                )
            )

    async def add_tag(
        self, *, contact_id: UUID, tag: str, actor_id: UUID
    ) -> None:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    """
                    INSERT INTO contact_tags (contact_id, tag, created_by)
                    VALUES ($1,$2,$3) ON CONFLICT (contact_id, tag) DO NOTHING
                    """,
                    contact_id,
                    tag,
                    actor_id,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.tag_added',$1,$2,$3)",
                    str(actor_id),
                    contact_id,
                    {"tag": tag},
                )

    async def add_note(
        self,
        *,
        contact_id: UUID,
        body: str,
        visibility: str,
        actor_id: UUID,
    ) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO contact_notes (
                        contact_id, body, visibility, created_by
                    ) VALUES ($1,$2,$3,$4)
                    RETURNING id, contact_id, body, visibility, created_by, created_at
                    """,
                    contact_id,
                    body,
                    visibility,
                    actor_id,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.note_added',$1,$2,$3)",
                    str(actor_id),
                    contact_id,
                    {"note_id": str(row["id"]), "visibility": visibility},
                )
        return dict(row)

    async def set_consent(
        self,
        *,
        contact_id: UUID,
        purpose: str,
        status: str,
        source: str,
        account_id: UUID | None,
        evidence: Mapping[str, Any],
        actor_id: UUID,
    ) -> dict[str, Any] | None:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO contact_consents (
                        contact_id, account_id, purpose, status, source,
                        evidence, captured_by
                    )
                    SELECT $1,$2,$3,$4,$5,$6,$7
                    WHERE $2::uuid IS NULL OR EXISTS (
                        SELECT 1 FROM contact_points
                        WHERE contact_id = $1 AND channel_account_id = $2
                    )
                    ON CONFLICT (contact_id, account_id, purpose) DO UPDATE
                    SET status = EXCLUDED.status, source = EXCLUDED.source,
                        evidence = EXCLUDED.evidence,
                        captured_by = EXCLUDED.captured_by,
                        captured_at = now(), updated_at = now()
                    RETURNING id, contact_id, account_id, purpose, status,
                              source, captured_at, updated_at
                    """,
                    contact_id,
                    account_id,
                    purpose,
                    status,
                    source,
                    dict(evidence),
                    actor_id,
                )
                if row is None:
                    return None
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.consent_changed',$1,$2,$3)",
                    str(actor_id),
                    contact_id,
                    {
                        "purpose": purpose,
                        "status": status,
                        "account_id": str(account_id) if account_id else None,
                    },
                )
        return dict(row)

    async def request_retention(
        self,
        *,
        contact_id: UUID,
        kind: str,
        reason: str,
        dry_run: bool,
        actor_id: UUID,
    ) -> dict[str, Any]:
        async with self._pool_provider().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO data_retention_jobs (
                        contact_id, kind, requested_by, reason, dry_run
                    ) VALUES ($1,$2,$3,$4,$5)
                    RETURNING id, contact_id, kind, status, dry_run, requested_at
                    """,
                    contact_id,
                    kind,
                    actor_id,
                    reason,
                    dry_run,
                )
                await connection.execute(
                    "INSERT INTO events (kind, actor, ref_id, detail) "
                    "VALUES ('contact.retention_requested',$1,$2,$3)",
                    str(actor_id),
                    row["id"],
                    {"contact_id": str(contact_id), "kind": kind, "dry_run": dry_run},
                )
        return dict(row)


def get_contact_repository() -> PostgresContactRepository:
    return PostgresContactRepository()


def get_identity_service() -> IdentityService:
    return IdentityService(PostgresIdentityRepository())


async def get_muc_tam_nhin() -> str:
    """
    Mức tầm nhìn đang đặt, dưới dạng dependency.

    Gọi thẳng `pham_vi.doc_muc()` trong thân endpoint cũng chạy được, nhưng
    khi ấy mọi test dùng kho giả đều phải dựng một CSDL thật chỉ để đọc một
    thiết lập — và cách rẻ hơn mà người ta sẽ chọn là cho `doc_muc()` nuốt
    lỗi "chưa có pool" rồi trả mặc định. Nuốt lỗi ở đó là biến "CSDL chưa
    sẵn sàng" thành "mọi người thấy mọi khách", im lặng.

    Là dependency thì test ghi đè một dòng, và mã thật vẫn nổ khi mất CSDL.
    """
    return await pham_vi.doc_muc()


def _scope(user: Mapping[str, Any]) -> tuple[UUID, bool]:
    """
    (id người dùng, có thấy khách của MỌI kênh không).

    Cờ thứ hai đi thẳng vào mệnh đề WHERE của `list_visible` và quyết định
    cả ba việc: thấy khách ngoài kênh mình là thành viên, thấy PII, và tìm
    được theo số điện thoại.

    `khach.xem_tat_ca` KHÔNG nằm trong tập vai trò `Nhân viên` nạp sẵn, nên
    ngữ nghĩa lọc giữ nguyên hệt trước bản này. Gộp nó vào `khach.doc` là
    mở toàn bộ danh bạ cho mọi nhân viên — không có gì hỏng để ai nhận ra.
    """
    return UUID(str(user["id"])), "khach.xem_tat_ca" in user.get("quyen", ())


def _raise_identity(exc: IdentityError) -> None:
    if isinstance(exc, ContactNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ContactConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, InvalidMerge):
        raise HTTPException(422, str(exc)) from exc
    raise exc


@router.get("")
async def list_contacts(
    q: str = Query("", max_length=120),
    account_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    user: dict = Depends(can_quyen("khach.doc")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
    muc: str = Depends(get_muc_tam_nhin),
) -> list[dict[str, Any]]:
    user_id, is_admin = _scope(user)
    rows = await repository.list_visible(
        user_id=user_id,
        is_admin=is_admin,
        query=q.strip(),
        account_id=account_id,
        limit=limit,
        nguoi=user,
        muc=muc,
    )
    ra = []
    for row in rows:
        # Hai cờ đi KÈM từng khách, không phải một cờ chung cho cả danh sách:
        # cùng một màn hình có thể vừa có khách của mình (trả lời được) vừa
        # có khách của người khác (không). Một cờ chung thì hoặc khoá nhầm,
        # hoặc mở nhầm.
        cong_khai = mask_contact_pii(row)
        cong_khai["duoc_tra_loi"] = pham_vi.duoc_tra_loi(user, row, muc=muc)
        if not pham_vi.duoc_xem_noi_dung(user, row, muc=muc):
            cong_khai["phone"] = _mask_phone(cong_khai.get("phone"))
            cong_khai["email"] = _mask_email(cong_khai.get("email"))
            cong_khai["pii_masked"] = True
            cong_khai["an_noi_dung"] = True
        ra.append(cong_khai)
    return ra


@router.get("/merge/preview")
async def preview_contact_merge(
    source_id: UUID,
    target_id: UUID,
    user: dict = Depends(can_quyen("khach.gop")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    user_id, is_admin = _scope(user)
    preview = await repository.merge_preview(
        source_id=source_id,
        target_id=target_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    if preview is None:
        raise HTTPException(404, "Không tìm thấy đủ hai contact trong phạm vi quyền")
    return preview


@router.get("/{contact_id}")
async def contact_detail(
    contact_id: UUID,
    user: dict = Depends(can_quyen("khach.doc")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    user_id, is_admin = _scope(user)
    contact = await repository.get_visible(
        contact_id=contact_id, user_id=user_id, is_admin=is_admin
    )
    if contact is None:
        raise HTTPException(404, "Không tìm thấy contact")
    return mask_contact_pii(contact)


@router.post("/merge")
async def merge_contacts(
    body: MergeContactsIn,
    user: dict = Depends(can_quyen("khach.gop")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
    identity: IdentityService = Depends(get_identity_service),
) -> dict[str, Any]:
    user_id, is_admin = _scope(user)
    preview = await repository.merge_preview(
        source_id=body.source_id,
        target_id=body.target_id,
        user_id=user_id,
        is_admin=is_admin,
    )
    if preview is None:
        raise HTTPException(404, "Không tìm thấy đủ hai contact trong phạm vi quyền")
    if not preview["can_manage"]:
        raise HTTPException(403, "Cần quyền manager trên mọi account liên quan")
    try:
        result = await identity.merge_contacts(
            source_id=body.source_id,
            target_id=body.target_id,
            actor_id=user_id,
            reason=body.reason,
            expected_source_version=body.expected_source_version,
            expected_target_version=body.expected_target_version,
        )
    except IdentityError as exc:
        _raise_identity(exc)
    return {
        "merge_id": str(result.merge_id),
        "source_contact_id": str(result.source_contact_id),
        "target_contact_id": str(result.target_contact_id),
        "status": result.status,
    }


@router.post("/merges/{merge_id}/undo")
async def unmerge_contact(
    merge_id: UUID,
    body: UnmergeContactIn,
    user: dict = Depends(can_quyen("khach.gop")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
    identity: IdentityService = Depends(get_identity_service),
) -> dict[str, Any]:
    user_id, is_admin = _scope(user)
    if not await repository.can_manage_merge(
        merge_id=merge_id, user_id=user_id, is_admin=is_admin
    ):
        raise HTTPException(403, "Không có quyền hoàn tác merge này")
    try:
        result = await identity.unmerge_contact(
            merge_id=merge_id, actor_id=user_id, reason=body.reason
        )
    except IdentityError as exc:
        _raise_identity(exc)
    return {
        "merge_id": str(result.merge_id),
        "source_contact_id": str(result.source_contact_id),
        "target_contact_id": str(result.target_contact_id),
        "status": result.status,
    }


async def _require_contact_manager(
    contact_id: UUID,
    user: Mapping[str, Any],
    repository: PostgresContactRepository,
) -> UUID:
    user_id, is_admin = _scope(user)
    if not await repository.can_manage_contact(
        contact_id=contact_id, user_id=user_id, is_admin=is_admin
    ):
        raise HTTPException(403, "Cần quyền manager trên mọi account liên quan")
    return user_id


@router.post("/{contact_id}/tags", status_code=201)
async def add_contact_tag(
    contact_id: UUID,
    body: ContactTagIn,
    user: dict = Depends(can_quyen("khach.sua")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    actor_id = await _require_contact_manager(contact_id, user, repository)
    tag = body.tag.strip()
    await repository.add_tag(contact_id=contact_id, tag=tag, actor_id=actor_id)
    return {"contact_id": str(contact_id), "tag": tag}


@router.post("/{contact_id}/notes", status_code=201)
async def add_contact_note(
    contact_id: UUID,
    body: ContactNoteIn,
    user: dict = Depends(can_quyen("khach.sua")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    actor_id = await _require_contact_manager(contact_id, user, repository)
    return await repository.add_note(
        contact_id=contact_id,
        body=body.body.strip(),
        visibility=body.visibility,
        actor_id=actor_id,
    )


@router.put("/{contact_id}/consents/{purpose}")
async def set_contact_consent(
    contact_id: UUID,
    purpose: str,
    body: ContactConsentIn,
    user: dict = Depends(can_quyen("khach.sua")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    actor_id = await _require_contact_manager(contact_id, user, repository)
    consent = await repository.set_consent(
        contact_id=contact_id,
        purpose=purpose.strip()[:80],
        status=body.status,
        source=body.source.strip(),
        account_id=body.account_id,
        evidence=body.evidence,
        actor_id=actor_id,
    )
    if consent is None:
        raise HTTPException(422, "Account consent không thuộc contact")
    return consent


@router.post("/{contact_id}/retention-jobs", status_code=202)
async def request_contact_retention(
    contact_id: UUID,
    body: RetentionRequestIn,
    user: dict = Depends(can_quyen("khach.xoa")),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> dict[str, Any]:
    actor_id = await _require_contact_manager(contact_id, user, repository)
    return await repository.request_retention(
        contact_id=contact_id,
        kind=body.kind,
        reason=body.reason.strip(),
        dry_run=body.dry_run,
        actor_id=actor_id,
    )


# =====================================================================
#  Giao khách cho nhân viên
# =====================================================================
# Ba thứ phải ghi CÙNG một giao dịch: cột chủ, dòng lịch sử, nhật ký kiểm
# toán. Ghi cột mà mất lịch sử thì sáu tháng sau không ai trả lời được "ai
# giao khách này cho Thảo, và lúc nào" — và câu hỏi ấy luôn được hỏi vào
# đúng lúc có chuyện.

class ChuSoHuuIn(BaseModel):
    owner_user_id: UUID
    ly_do: str = Field(min_length=3, max_length=500)


async def _khach_ton_tai(conn, contact_id: UUID) -> None:
    co = await conn.fetchval(
        "SELECT 1 FROM contacts WHERE id = $1 AND status <> 'deleted'",
        contact_id)
    if not co:
        raise HTTPException(404, "Không tìm thấy khách hàng")


async def _ghi_chu_so_huu(conn, *, contact_id: UUID, chu: UUID | None,
                          actor: dict, ly_do: str) -> None:
    await conn.execute(
        "UPDATE contacts SET owner_user_id = $2, updated_at = now() "
        "WHERE id = $1", contact_id, chu)
    await conn.execute(
        "INSERT INTO contact_owner_history "
        "(contact_id, owner_user_id, actor_id, ly_do) VALUES ($1,$2,$3,$4)",
        contact_id, chu,
        UUID(str(actor["id"])) if actor.get("id") else None, ly_do)


@router.put("/{contact_id}/chu-so-huu")
async def giao_khach(
    contact_id: UUID,
    body: ChuSoHuuIn,
    user: dict = Depends(can_quyen("khach.giao")),
) -> dict[str, Any]:
    """
    Giao khách cho một nhân viên.

    Chặn giao cho người KHÔNG có `hoi_thoai.tra_loi`. Không chặn thì khách
    ấy chết câm: có chủ nên người khác thấy "đã có người phụ trách" và không
    vào, mà chủ thì không gửi được tin. Nó không hỏng — nó chỉ im, và triệu
    chứng duy nhất là một khách hàng thôi nhắn lại.
    """
    async with db.pool().acquire() as connection:
        async with connection.transaction():
            await _khach_ton_tai(connection, contact_id)

            nhan = await connection.fetchrow(
                "SELECT nd.ho_ten, nd.ten_dang_nhap, nd.khoa, "
                "       COALESCE(bool_or(vq.quyen = 'hoi_thoai.tra_loi' "
                "               OR (vt.he_thong AND vt.ten = 'Quản trị')), "
                "                false) AS tra_loi_duoc "
                "FROM nguoi_dung nd "
                "LEFT JOIN nguoi_dung_vai_tro ndvt ON ndvt.nguoi_dung_id = nd.id "
                "LEFT JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
                "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
                "WHERE nd.id = $1 GROUP BY nd.id",
                body.owner_user_id)
            if nhan is None:
                raise HTTPException(404, "Không tìm thấy nhân viên")
            if nhan["khoa"]:
                raise HTTPException(422, (
                    "Tài khoản này đang bị khoá — giao khách cho họ là khách "
                    "không có ai trả lời."))
            if not nhan["tra_loi_duoc"]:
                raise HTTPException(422, (
                    f"“{nhan['ho_ten'] or nhan['ten_dang_nhap']}” không có "
                    "quyền hoi_thoai.tra_loi. Giao khách cho họ là khách có "
                    "chủ nhưng không ai trả lời được — người khác thấy đã có "
                    "người phụ trách nên cũng không vào."))

            await _ghi_chu_so_huu(connection, contact_id=contact_id,
                                  chu=body.owner_user_id, actor=user,
                                  ly_do=body.ly_do.strip())

    await db.log_event("khach.giao", actor=user.get("ten_dang_nhap", "?"),
                       ref_id=contact_id, owner=str(body.owner_user_id),
                       ly_do=body.ly_do.strip())
    return {"contact_id": str(contact_id),
            "owner_user_id": str(body.owner_user_id),
            "owner_ho_ten": nhan["ho_ten"] or nhan["ten_dang_nhap"]}


@router.delete("/{contact_id}/chu-so-huu")
async def thu_hoi_khach(
    contact_id: UUID,
    ly_do: str = Query(min_length=3, max_length=500),
    user: dict = Depends(can_quyen("khach.giao")),
) -> dict[str, Any]:
    """
    Thu hồi: khách quay về trạng thái của chung.

    Vẫn ghi lịch sử với `owner_user_id = NULL`. Thu hồi là một sự kiện thật;
    không ghi thì khoảng trống giữa hai lần giao trở nên vô hình, và "từ lúc
    nào khách này không còn ai phụ trách" là câu hỏi không trả lời được.
    """
    async with db.pool().acquire() as connection:
        async with connection.transaction():
            await _khach_ton_tai(connection, contact_id)
            await _ghi_chu_so_huu(connection, contact_id=contact_id, chu=None,
                                  actor=user, ly_do=ly_do.strip())

    await db.log_event("khach.thu_hoi", actor=user.get("ten_dang_nhap", "?"),
                       ref_id=contact_id, ly_do=ly_do.strip())
    return {"contact_id": str(contact_id), "owner_user_id": None}


@router.get("/{contact_id}/chu-so-huu/lich-su")
async def lich_su_chu_so_huu(
    contact_id: UUID,
    _q: dict = Depends(can_quyen("khach.doc")),
) -> dict[str, Any]:
    ds = await db.fetch(
        "SELECT ls.id, ls.owner_user_id, ls.ly_do, ls.luc, "
        "       chu.ho_ten AS owner_ho_ten, "
        "       ai.ten_dang_nhap AS actor_ten_dang_nhap "
        "FROM contact_owner_history ls "
        "LEFT JOIN nguoi_dung chu ON chu.id = ls.owner_user_id "
        "LEFT JOIN nguoi_dung ai ON ai.id = ls.actor_id "
        "WHERE ls.contact_id = $1 ORDER BY ls.luc DESC, ls.id DESC LIMIT 100",
        contact_id)
    for d in ds:
        d["owner_user_id"] = (str(d["owner_user_id"])
                              if d["owner_user_id"] else None)
        d["luc"] = d["luc"].isoformat()
    return {"lich_su": ds}


# Router thứ hai, prefix `/api` chứ không `/api/contacts`.
#
# Không nhét `/vo-chu` vào router trên được: `/{contact_id}` đã khai ở phía
# trước, và FastAPI khớp theo THỨ TỰ KHAI — nên `/api/contacts/vo-chu` sẽ
# rơi vào `contact_detail` với `contact_id="vo-chu"`, trả 422 về kiểu UUID.
# Một lỗi 422 khó hiểu ở một đường vừa thêm là thứ mất nửa ngày để tìm.
router_vo_chu = APIRouter(prefix="/api", tags=["customer-360"])


# =====================================================================
#  Trường thông tin khách do người vận hành tự thêm
# =====================================================================

class TruongIn(BaseModel):
    ma: str
    nhan: str = Field(min_length=1, max_length=80)
    kieu: str
    goi_y: str = Field("", max_length=300)
    bat_buoc: bool = False
    lua_chon: list[str] = Field(default_factory=list)
    hien_danh_sach: bool = False
    thu_tu: int = 100


class TruongSuaIn(BaseModel):
    """
    Sửa được mọi thứ TRỪ `ma` và `kieu`.

    `ma` là khoá trong `contacts.profile` — đổi nó là mọi giá trị đã lưu
    thành mồ côi, vô hình trên màn hình và không ai gỡ được.

    `kieu` thì tệ hơn: đổi `chu` sang `so` không làm cho các giá trị đã lưu
    trở thành số. Chúng nằm nguyên đó dưới dạng chuỗi, và từ đó mỗi lần đọc
    là một lần kiểu nói một đằng dữ liệu một nẻo. Muốn đổi kiểu thì xoá
    trường rồi tạo lại — và lúc ấy hệ thống sẽ hỏi rõ về số giá trị sắp mất.
    """
    nhan: str = Field(min_length=1, max_length=80)
    goi_y: str = Field("", max_length=300)
    bat_buoc: bool = False
    lua_chon: list[str] = Field(default_factory=list)
    hien_danh_sach: bool = False
    thu_tu: int = 100


class HoSoIn(BaseModel):
    gia_tri: dict[str, Any]


async def _danh_sach_truong() -> list[dict[str, Any]]:
    ds = await db.fetch(
        "SELECT ma, nhan, kieu, goi_y, bat_buoc, lua_chon, hien_danh_sach, "
        "       thu_tu FROM truong_khach ORDER BY thu_tu, ma")
    for d in ds:
        # Codec JSONB đã giải mã; dữ liệu cũ có thể còn là chuỗi JSON.
        if isinstance(d["lua_chon"], str):
            import json
            d["lua_chon"] = json.loads(d["lua_chon"])
    return ds


@router_vo_chu.get("/truong-khach")
async def liet_ke_truong(
    _q: dict = Depends(can_quyen("khach.doc")),
) -> dict[str, Any]:
    return {
        "truong": await _danh_sach_truong(),
        "kieu": [{"ma": k, "nhan": truong_khach.NHAN_KIEU[k]}
                 for k in truong_khach.KIEU],
        "toi_da": truong_khach.SO_TRUONG_TOI_DA,
    }


@router_vo_chu.post("/truong-khach", status_code=201)
async def them_truong(
    body: TruongIn,
    nguoi: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict[str, Any]:
    try:
        ma = truong_khach.kiem_ma(body.ma)
    except truong_khach.TruongHong as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.kieu not in truong_khach.KIEU:
        raise HTTPException(422, f"Kiểu không hợp lệ: {body.kieu!r}")
    if body.kieu in ("chon", "nhieu_chon") and not body.lua_chon:
        raise HTTPException(422, (
            "Kiểu chọn phải có ít nhất một lựa chọn — không thì đó là một ô "
            "người dùng không chọn được gì, và nó trông hệt một ô đang tải."))

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            so = await conn.fetchval("SELECT count(*) FROM truong_khach")
            if so >= truong_khach.SO_TRUONG_TOI_DA:
                raise HTTPException(409, (
                    f"Đã đủ {truong_khach.SO_TRUONG_TOI_DA} trường. Một hồ sơ "
                    "khách dài hơn thế thì không ai điền hết, và ô trống thì "
                    "không phân biệt được với 'chưa hỏi'."))
            try:
                await conn.execute(
                    "INSERT INTO truong_khach (ma, nhan, kieu, goi_y, "
                    "bat_buoc, lua_chon, hien_danh_sach, thu_tu) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
                    ma, body.nhan.strip(), body.kieu, body.goi_y.strip(),
                    body.bat_buoc, body.lua_chon, body.hien_danh_sach,
                    body.thu_tu)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(
                    409, f"Đã có trường mã “{ma}”.") from exc

    await db.log_event("truong_khach.them", actor=nguoi.get("ten_dang_nhap", "?"),
                       ma=ma, kieu=body.kieu)
    return {"ma": ma, **body.model_dump(exclude={"ma"})}


@router_vo_chu.put("/truong-khach/{ma}")
async def sua_truong(
    ma: str,
    body: TruongSuaIn,
    nguoi: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict[str, Any]:
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT kieu, lua_chon FROM truong_khach WHERE ma = $1 "
                "FOR UPDATE", ma)
            if cu is None:
                raise HTTPException(404, "Không tìm thấy trường")
            if cu["kieu"] in ("chon", "nhieu_chon") and not body.lua_chon:
                raise HTTPException(422, "Kiểu chọn phải có ít nhất một lựa chọn.")
            await conn.execute(
                "UPDATE truong_khach SET nhan=$2, goi_y=$3, bat_buoc=$4, "
                "lua_chon=$5, hien_danh_sach=$6, thu_tu=$7, sua_luc=now() "
                "WHERE ma = $1",
                ma, body.nhan.strip(), body.goi_y.strip(), body.bat_buoc,
                body.lua_chon, body.hien_danh_sach, body.thu_tu)

    await db.log_event("truong_khach.sua", actor=nguoi.get("ten_dang_nhap", "?"),
                       ma=ma)
    return {"ma": ma, **body.model_dump()}


@router_vo_chu.delete("/truong-khach/{ma}")
async def xoa_truong(
    ma: str,
    xoa_ca_gia_tri: bool = Query(False),
    nguoi: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict[str, Any]:
    """
    Xoá một trường.

    Nếu còn hồ sơ khách đang giữ giá trị của trường ấy thì TỪ CHỐI, và nói
    ra con số — trừ khi người dùng khẳng định `xoa_ca_gia_tri=true`.

    Vì sao không lặng lẽ để giá trị nằm lại: đó là dữ liệu cá nhân không
    còn hiện ở đâu trên màn hình, không ai gỡ được, và không ai biết mình
    đang giữ (Nghị định 13/2023/NĐ-CP). "Xoá định nghĩa" mà dữ liệu vẫn nằm
    trong CSDL là đúng nghĩa giữ dữ liệu quá hạn trong im lặng.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            co = await conn.fetchval(
                "SELECT 1 FROM truong_khach WHERE ma = $1 FOR UPDATE", ma)
            if not co:
                raise HTTPException(404, "Không tìm thấy trường")

            so_ho_so = await conn.fetchval(
                "SELECT count(*) FROM contacts WHERE profile ? $1", ma)
            if so_ho_so and not xoa_ca_gia_tri:
                raise HTTPException(409, (
                    f"{so_ho_so} hồ sơ khách đang có giá trị ở trường này. "
                    "Xoá trường sẽ xoá luôn các giá trị ấy — gọi lại với "
                    "xoa_ca_gia_tri=true nếu đúng là bạn muốn vậy."))

            if so_ho_so:
                await conn.execute(
                    "UPDATE contacts SET profile = profile - $1, "
                    "updated_at = now() WHERE profile ? $1", ma)
            await conn.execute("DELETE FROM truong_khach WHERE ma = $1", ma)

    await db.log_event("truong_khach.xoa", actor=nguoi.get("ten_dang_nhap", "?"),
                       ma=ma, so_ho_so_mat_gia_tri=so_ho_so)
    return {"ma": ma, "so_ho_so_da_xoa_gia_tri": so_ho_so}


@router.put("/{contact_id}/truong")
async def dat_truong_khach(
    contact_id: UUID,
    body: HoSoIn,
    user: dict = Depends(can_quyen("khach.sua")),
) -> dict[str, Any]:
    """
    Ghi giá trị các trường tuỳ biến cho một khách.

    Kiểm kiểu ở MÃ, không chỉ ở giao diện — xem
    `agent/core/truong_khach.py`. Chỉ gộp những khoá gửi lên; khoá không
    gửi thì giữ nguyên, để sửa một ô không xoá mất các ô còn lại.
    """
    dinh_nghia = await _danh_sach_truong()
    try:
        sach = truong_khach.kiem_ho_so(dinh_nghia, body.gia_tri)
    except truong_khach.TruongHong as exc:
        raise HTTPException(422, str(exc)) from exc

    # Khoá gửi lên với giá trị rỗng nghĩa là XOÁ ô ấy — `kiem_ho_so` đã bỏ
    # chúng khỏi `sach`, nên phải trừ riêng, không thì ô rỗng không xoá được.
    xoa = [k for k in body.gia_tri if k not in sach]

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await _khach_ton_tai(conn, contact_id)
            moi = await conn.fetchval(
                "UPDATE contacts SET profile = (profile - $2::text[]) || $3, "
                "updated_at = now() WHERE id = $1 RETURNING profile",
                contact_id, xoa, sach)

    await db.log_event("khach.truong", actor=user.get("ten_dang_nhap", "?"),
                       ref_id=contact_id, truong=sorted(body.gia_tri))
    import json
    return {"profile": json.loads(moi) if isinstance(moi, str) else moi}


class TamNhinIn(BaseModel):
    muc: str


# Nhãn và HỆ QUẢ của từng mức, gửi kèm cho dashboard.
#
# Một ô chọn bốn giá trị mà không giải thích thì người ta chọn bừa, rồi
# không hiểu vì sao nhân viên kêu mất khách. Câu giải thích phải đi cùng
# lựa chọn, không nằm trong tài liệu ở đâu đó.
MO_TA_MUC = {
    "tat": ("Không áp dụng",
            "Mọi nhân viên thấy và trả lời được mọi khách trong kênh của "
            "mình, hệt như trước. Giao khách vẫn ghi nhận, chỉ là chưa dùng "
            "để hạn chế ai."),
    "an_noi_dung": ("Thấy tên, không đọc được",
                    "Nhân viên thấy khách của người khác trong danh sách và "
                    "biết ai phụ trách, nhưng không đọc tin nhắn, không thấy "
                    "số điện thoại và email."),
    "chi_doc": ("Đọc được, không trả lời được",
                "Nhân viên đọc đủ hội thoại của khách người khác — tiện bàn "
                "giao ca — nhưng nút gửi bị khoá."),
    "an": ("Ẩn hẳn",
           "Khách của người khác biến mất khỏi danh sách, không mở được, "
           "tìm cũng không ra. Chặt nhất, và cũng là mức dễ làm người trực "
           "tưởng hệ thống mất dữ liệu nhất."),
}


@router_vo_chu.get("/tam-nhin-khach")
async def doc_tam_nhin(
    _q: dict = Depends(can_quyen("cau_hinh.doc")),
) -> dict[str, Any]:
    dang_dat = await pham_vi.doc_muc()
    return {
        "muc": dang_dat,
        "mac_dinh": pham_vi.MUC_MAC_DINH,
        "cac_muc": [
            {"ma": m, "nhan": MO_TA_MUC[m][0], "he_qua": MO_TA_MUC[m][1]}
            for m in pham_vi.MUC_TAM_NHIN
        ],
    }


@router_vo_chu.put("/tam-nhin-khach")
async def dat_tam_nhin(
    body: TamNhinIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Đổi mức tầm nhìn.

    Quyền `nguoi_dung.sua` chứ không `cau_hinh.sua`: đây là một chính sách
    về AI THẤY GÌ, cùng họ với gán vai trò — không phải một tham số vận
    hành như ngưỡng tự tin hay trần chi phí.
    """
    if body.muc not in pham_vi.MUC_TAM_NHIN:
        raise HTTPException(422, (
            f"Mức không hợp lệ: {body.muc!r}. "
            f"Chỉ nhận: {', '.join(pham_vi.MUC_TAM_NHIN)}"))
    await db.execute(
        "INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi, sua_luc) "
        "VALUES ($1, $2, $3, now()) "
        "ON CONFLICT (khoa) DO UPDATE SET gia_tri = $2, sua_boi = $3, "
        "sua_luc = now()",
        pham_vi.KHOA_CAU_HINH, body.muc, nguoi.get("ten_dang_nhap", "?"))
    await db.log_event("tam_nhin_khach.dat",
                       actor=nguoi.get("ten_dang_nhap", "?"), muc=body.muc)
    return {"muc": body.muc}


@router_vo_chu.get("/khach-vo-chu")
async def khach_vo_chu(
    limit: int = Query(50, ge=1, le=200),
    _q: dict = Depends(can_quyen("khach.doc")),
) -> dict[str, Any]:
    """
    Khách chưa được giao cho ai.

    Chủ dự án chọn "mọi người thấy, không tự gán chủ", nên khách vô chủ sẽ
    TÍCH LẠI — đó là hệ quả đã biết trước. Chặn bằng mã chứ không bằng lời
    nhắc: endpoint này nuôi một chỉ số thường trực trên trang Ca trực.

    Số đếm và danh sách dùng CHUNG một mệnh đề. Hai định nghĩa "vô chủ" lệch
    nhau là con số nói một đằng, danh sách hiện một nẻo — rồi người ta thôi
    tin cả hai, và thôi nhìn cả hai.
    """
    dieu_kien = "owner_user_id IS NULL AND status = 'active'"
    tong = await db.fetchrow(
        f"SELECT count(*) AS so, min(first_seen) AS lau_nhat "  # noqa: S608
        f"FROM contacts WHERE {dieu_kien}")
    ds = await db.fetch(
        f"SELECT id, display_name, first_seen, last_seen "      # noqa: S608
        f"FROM contacts WHERE {dieu_kien} "
        f"ORDER BY first_seen LIMIT $1", limit)
    for d in ds:
        d["id"] = str(d["id"])
        for k in ("first_seen", "last_seen"):
            d[k] = d[k].isoformat()
    lau_nhat = tong["lau_nhat"]
    return {
        "so": tong["so"],
        "ngay_lau_nhat": lau_nhat.isoformat() if lau_nhat else None,
        "khach": ds,
    }
