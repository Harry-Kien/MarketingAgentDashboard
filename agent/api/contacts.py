"""API Customer 360: account-scoped, PII theo role và merge có preview."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

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

from .routes import bat_buoc_dang_nhap


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
    ) -> list[dict[str, Any]]:
        async with self._pool_provider().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT contact.id, contact.display_name, contact.phone,
                       contact.email, contact.profile, contact.status,
                       contact.version, contact.first_seen, contact.last_seen,
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
                WHERE contact.status <> 'deleted'
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
                       ($3 OR EXISTS (
                           SELECT 1 FROM contact_points point
                           JOIN account_memberships membership
                             ON membership.account_id = point.channel_account_id
                            AND membership.user_id = $2
                            AND membership.role IN ('owner', 'manager')
                           WHERE point.contact_id = contact.id
                       )) AS can_view_pii
                FROM contacts contact
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


def _scope(user: Mapping[str, Any]) -> tuple[UUID, bool]:
    return UUID(str(user["id"])), user["vai_tro"] == "quan_tri"


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
    user: dict = Depends(bat_buoc_dang_nhap),
    repository: PostgresContactRepository = Depends(get_contact_repository),
) -> list[dict[str, Any]]:
    user_id, is_admin = _scope(user)
    rows = await repository.list_visible(
        user_id=user_id,
        is_admin=is_admin,
        query=q.strip(),
        account_id=account_id,
        limit=limit,
    )
    return [mask_contact_pii(row) for row in rows]


@router.get("/merge/preview")
async def preview_contact_merge(
    source_id: UUID,
    target_id: UUID,
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
    user: dict = Depends(bat_buoc_dang_nhap),
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
