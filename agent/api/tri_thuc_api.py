"""API Knowledge Base: Draft/Published, versioning, rollback và probe RAG."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from agent import db
from agent.core import rag

from .phu_thuoc import can_quyen


router = APIRouter(prefix="/api")
GLOBAL_ACCOUNT_ID = UUID(int=0)


def _actor(user: dict) -> tuple[str, UUID | None]:
    try:
        actor_id = UUID(str(user["id"]))
    except (KeyError, TypeError, ValueError):
        actor_id = None
    return str(user.get("ten_dang_nhap") or user.get("ho_ten") or "unknown"), actor_id


async def _account_scope(account_id: UUID, user: dict) -> UUID | None:
    """Chốt tenant ở Backend; quyền cấu hình không tự mở mọi account."""
    try:
        user_id = UUID(str(user["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(403, "Không xác định được phạm vi tài khoản") from exc
    can_see_all = "hoi_thoai.xem_tat_ca" in (user.get("quyen") or ())
    if account_id == GLOBAL_ACCOUNT_ID:
        if not can_see_all:
            raise HTTPException(403, "Chỉ quản trị được quản lý kho tri thức dùng chung")
        return None
    allowed = await db.fetchrow(
        """
        SELECT id FROM channel_accounts account
        WHERE account.id=$1 AND (
            $3 OR EXISTS (
                SELECT 1 FROM account_memberships membership
                WHERE membership.account_id=account.id
                  AND membership.user_id=$2
            )
        )
        """,
        account_id,
        user_id,
        can_see_all,
    )
    if allowed is None:
        raise HTTPException(403, "Không có quyền truy cập kho tri thức của tài khoản")
    return account_id


async def _document_scope(
    document_id: UUID, account_id: UUID, user: dict
) -> tuple[dict, UUID | None]:
    scope = await _account_scope(account_id, user)
    row = await db.fetchrow(
        "SELECT * FROM documents WHERE id=$1 AND account_id IS NOT DISTINCT FROM $2",
        document_id,
        scope,
    )
    if row is None:
        raise HTTPException(404, "Không tìm thấy tài liệu trong tài khoản")
    return row, scope


@router.get("/knowledge/accounts")
async def knowledge_accounts(
    user: dict = Depends(can_quyen("cau_hinh.doc")),
) -> list[dict]:
    try:
        user_id = UUID(str(user["id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(403, "Không xác định được phạm vi tài khoản") from exc
    can_see_all = "hoi_thoai.xem_tat_ca" in (user.get("quyen") or ())
    rows = await db.fetch(
        """
        SELECT account.id, account.display_name, account.channel
        FROM channel_accounts account
        WHERE $2 OR EXISTS (
            SELECT 1 FROM account_memberships membership
            WHERE membership.account_id=account.id
              AND membership.user_id=$1
        )
        ORDER BY (account.status='active') DESC, account.display_name
        """,
        user_id,
        can_see_all,
    )
    result = [
        {"id": str(row["id"]), "name": row["display_name"], "channel": row["channel"]}
        for row in rows
    ]
    if can_see_all:
        result.insert(0, {
            "id": str(GLOBAL_ACCOUNT_ID),
            "name": "Kho dùng chung / dữ liệu legacy",
            "channel": "system",
        })
    return result


@router.get("/knowledge")
async def list_documents(
    account_id: UUID = Query(...),
    user: dict = Depends(can_quyen("cau_hinh.doc")),
) -> list[dict]:
    scope = await _account_scope(account_id, user)
    rows = await db.fetch(
        """
        SELECT d.id, d.title, d.source, d.chunk_count, d.lifecycle_status,
               d.created_at, d.updated_at,
               draft.id AS draft_version_id,
               draft.version AS draft_version,
               draft.index_status, draft.index_error,
               published.id AS published_version_id,
               published.version AS published_version,
               published.published_at
        FROM documents d
        LEFT JOIN document_versions draft ON draft.id=d.current_draft_version_id
        LEFT JOIN document_versions published
          ON published.id=d.current_published_version_id
        WHERE d.account_id IS NOT DISTINCT FROM $1
          AND d.lifecycle_status <> 'archived'
        ORDER BY d.updated_at DESC
        """,
        scope,
    )
    return [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "source": row["source"],
            "chunks": row["chunk_count"],
            "status": row["lifecycle_status"],
            "draft_version_id": str(row["draft_version_id"]) if row["draft_version_id"] else None,
            "draft_version": row["draft_version"],
            "index_status": row["index_status"],
            "index_error": row["index_error"],
            "published_version_id": (
                str(row["published_version_id"]) if row["published_version_id"] else None
            ),
            "published_version": row["published_version"],
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]


@router.get("/knowledge/{document_id}")
async def document_detail(
    document_id: UUID,
    account_id: UUID = Query(...),
    user: dict = Depends(can_quyen("cau_hinh.doc")),
) -> dict:
    await _document_scope(document_id, account_id, user)
    row = await db.fetchrow(
        """
        SELECT d.id, d.title, d.source, d.lifecycle_status,
               draft.id AS draft_version_id, draft.version AS draft_version,
               draft.content AS draft_content, draft.index_status,
               draft.index_error,
               published.id AS published_version_id,
               published.version AS published_version,
               published.content AS published_content,
               published.published_at
        FROM documents d
        LEFT JOIN document_versions draft ON draft.id=d.current_draft_version_id
        LEFT JOIN document_versions published
          ON published.id=d.current_published_version_id
        WHERE d.id=$1
        """,
        document_id,
    )
    return {
        key: (str(value) if key.endswith("_id") and value is not None else value)
        for key, value in dict(row).items()
    }


@router.get("/knowledge/{document_id}/versions")
async def document_versions(
    document_id: UUID,
    account_id: UUID = Query(...),
    user: dict = Depends(can_quyen("cau_hinh.doc")),
) -> list[dict]:
    await _document_scope(document_id, account_id, user)
    rows = await db.fetch(
        """
        SELECT id, version, status, content, index_status, index_error,
               chunk_count, created_at, published_at
        FROM document_versions
        WHERE document_id=$1 ORDER BY version DESC
        """,
        document_id,
    )
    return [
        {
            **dict(row),
            "id": str(row["id"]),
            "created_at": row["created_at"].isoformat(),
            "published_at": row["published_at"].isoformat() if row["published_at"] else None,
        }
        for row in rows
    ]


class DocBody(BaseModel):
    account_id: UUID
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20)


async def _save(body: DocBody, user: dict, document_id: UUID | None = None) -> dict:
    scope = await _account_scope(body.account_id, user)
    actor, actor_id = _actor(user)
    source = f"dashboard:{uuid4()}"
    if document_id is not None:
        document, scope = await _document_scope(document_id, body.account_id, user)
        source = str(document["source"])
    try:
        result = await rag.save_draft(
            document_id=document_id,
            title=body.title,
            source=source,
            text=body.text,
            account_id=scope,
            actor=actor,
            actor_id=actor_id,
        )
    except rag.KnowledgeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            503, f"Đã lưu Draft nhưng lập chỉ mục thất bại: {type(exc).__name__}: {exc}"
        ) from exc
    return {
        "document_id": str(result["document_id"]),
        "version_id": str(result["version_id"]),
        "version": result["version"],
        "index_status": result["index_status"],
        "chunks": result["chunks"],
        "status": "draft",
    }


@router.post("/knowledge", status_code=status.HTTP_201_CREATED)
async def add_document(
    body: DocBody,
    user: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict:
    return await _save(body, user)


@router.put("/knowledge/{document_id}/draft")
async def update_document_draft(
    document_id: UUID,
    body: DocBody,
    user: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict:
    return await _save(body, user, document_id)


class VersionBody(BaseModel):
    account_id: UUID
    version_id: UUID


@router.post("/knowledge/{document_id}/publish")
async def publish_document(
    document_id: UUID,
    body: VersionBody,
    user: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict:
    _document, scope = await _document_scope(document_id, body.account_id, user)
    actor, actor_id = _actor(user)
    try:
        result = await rag.publish_version(
            document_id=document_id, version_id=body.version_id,
            account_id=scope, actor=actor, actor_id=actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (rag.KnowledgeConflict, rag.KnowledgeNotReady) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {**result, "document_id": str(result["document_id"]), "version_id": str(result["version_id"])}


@router.post("/knowledge/{document_id}/rollback")
async def rollback_document(
    document_id: UUID,
    body: VersionBody,
    user: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict:
    _document, scope = await _document_scope(document_id, body.account_id, user)
    actor, actor_id = _actor(user)
    try:
        result = await rag.rollback_version(
            document_id=document_id, source_version_id=body.version_id,
            account_id=scope, actor=actor, actor_id=actor_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (rag.KnowledgeConflict, rag.KnowledgeNotReady) as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(503, f"Rollback chưa hoàn tất: {type(exc).__name__}: {exc}") from exc
    return {**result, "document_id": str(result["document_id"]), "version_id": str(result["version_id"])}


@router.delete("/knowledge/{document_id}")
async def delete_document(
    document_id: UUID,
    account_id: UUID = Query(...),
    user: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict:
    await _document_scope(document_id, account_id, user)
    actor, _actor_id = _actor(user)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE documents SET lifecycle_status='archived', updated_at=now() WHERE id=$1",
                document_id,
            )
            await conn.execute(
                "INSERT INTO events (kind,actor,ref_id,detail) VALUES ('knowledge.archived',$1,$2,'{}')",
                actor,
                document_id,
            )
    return {"ok": True, "archived": True}


class ProbeBody(BaseModel):
    account_id: UUID
    question: str = Field(min_length=2)


@router.post("/knowledge/probe")
async def probe(
    body: ProbeBody,
    user: dict = Depends(can_quyen("cau_hinh.doc")),
) -> dict:
    scope = await _account_scope(body.account_id, user)
    hits = (
        await rag.retrieve(body.question, k=5, account_id=scope)
        if scope is not None
        else await rag.retrieve(body.question, k=5)
    )
    return {
        "hits": [
            {
                "doc": hit.doc_title,
                "document_id": str(hit.document_id) if hit.document_id else None,
                "version_id": str(hit.version_id) if hit.version_id else None,
                "version": hit.version,
                "chunk_id": str(hit.chunk_id) if hit.chunk_id else None,
                "source": hit.source,
                "published_at": hit.published_at.isoformat() if hit.published_at else None,
                "score": round(hit.score, 4),
                "excerpt": hit.content[:280],
            }
            for hit in hits
        ]
    }
