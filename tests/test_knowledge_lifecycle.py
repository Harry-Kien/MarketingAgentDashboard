"""DEV-11: vòng đời Draft/Published, versioning và Published-only RAG."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent import db
from agent.api import tri_thuc_api
from agent.api.routes import nguoi_da_dang_nhap
from agent.core import rag
from agent.migrations.runner import apply_all, apply_migrations, discover_migrations
from conftest import nguoi_thu


SCHEMA = Path(__file__).resolve().parents[1] / "agent" / "schema.sql"


async def _codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def _prepare(url: str) -> tuple[asyncpg.Pool, UUID, UUID]:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(SCHEMA.read_text(encoding="utf-8"))
        await apply_all(conn)
        account_a = await conn.fetchval(
            """
            INSERT INTO channel_accounts (
                channel, display_name, external_account_id, status
            ) VALUES ('webchat', 'Cua hang A', $1, 'active') RETURNING id
            """,
            f"kb-a-{uuid4()}",
        )
        account_b = await conn.fetchval(
            """
            INSERT INTO channel_accounts (
                channel, display_name, external_account_id, status
            ) VALUES ('webchat', 'Cua hang B', $1, 'active') RETURNING id
            """,
            f"kb-b-{uuid4()}",
        )
    finally:
        await conn.close()
    pool = await asyncpg.create_pool(
        url, min_size=1, max_size=6, init=_codec
    )
    return pool, account_a, account_b


async def _fake_vectors(texts: list[str], *, query: bool = False) -> list[list[float]]:
    del query
    return [[1.0] + [0.0] * (rag.EMBED_DIM - 1) for _ in texts]


async def _row(pool: asyncpg.Pool, sql: str, *args):
    async with pool.acquire() as conn:
        return await conn.fetchrow(sql, *args)


def test_new_upload_is_draft_and_draft_is_not_retrievable(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, _ = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            draft = await rag.save_draft(
                title="Chinh sach bi mat",
                source="dashboard:secret",
                text="draft_secret_only noi dung chi o ban nhap va chua duoc phep dung.",
                account_id=account_a,
                actor="editor",
            )
            doc = await _row(
                pool,
                """
                SELECT lifecycle_status, current_published_version_id,
                       current_draft_version_id
                FROM documents WHERE id=$1
                """,
                draft["document_id"],
            )
            hits = await rag.retrieve(
                "draft_secret_only", account_id=account_a, min_score=0
            )
            return draft, doc, hits
        finally:
            db._pool = previous
            await pool.close()

    draft, doc, hits = asyncio.run(run())
    assert draft["index_status"] == "ready"
    assert draft["version"] == 1
    assert doc["lifecycle_status"] == "draft"
    assert doc["current_published_version_id"] is None
    assert doc["current_draft_version_id"] == draft["version_id"]
    assert hits == []


def test_publish_makes_only_current_version_retrievable_with_metadata(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, _ = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            first = await rag.save_draft(
                title="Bao hanh",
                source="dashboard:warranty",
                text="warranty_old San pham duoc bao hanh mot nam neu con hoa don.",
                account_id=account_a,
                actor="editor",
            )
            published_first = await rag.publish_version(
                document_id=first["document_id"],
                version_id=first["version_id"],
                account_id=account_a,
                actor="publisher",
            )
            old_hits = await rag.retrieve(
                "warranty_old", account_id=account_a, min_score=0
            )
            second = await rag.save_draft(
                document_id=first["document_id"],
                title="Bao hanh",
                source="dashboard:warranty",
                text="warranty_new San pham duoc bao hanh hai nam neu con hoa don.",
                account_id=account_a,
                actor="editor",
            )
            while_draft = await rag.retrieve(
                "warranty_old", account_id=account_a, min_score=0
            )
            await rag.publish_version(
                document_id=second["document_id"],
                version_id=second["version_id"],
                account_id=account_a,
                actor="publisher",
            )
            new_hits = await rag.retrieve(
                "warranty_new", account_id=account_a, min_score=0
            )
            stale_hits = await rag.retrieve(
                "warranty_old", account_id=account_a, min_score=0
            )
            return published_first, old_hits, while_draft, second, new_hits, stale_hits
        finally:
            db._pool = previous
            await pool.close()

    published, old_hits, while_draft, second, new_hits, stale_hits = asyncio.run(run())
    assert published["published"] is True
    assert old_hits and old_hits[0].version == 1
    assert while_draft and while_draft[0].version == 1
    assert second["version"] == 2
    assert new_hits and new_hits[0].version == 2
    assert new_hits[0].document_id
    assert new_hits[0].version_id
    assert new_hits[0].chunk_id
    assert new_hits[0].source == "dashboard:warranty"
    assert new_hits[0].published_at is not None
    assert all(hit.version == 2 for hit in stale_hits)
    assert all("warranty_old" not in hit.content for hit in stale_hits)


def test_rollback_creates_new_published_version_and_keeps_history(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, _ = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            v1 = await rag.save_draft(
                title="Doi tra",
                source="dashboard:return",
                text="return_v1 Doi tra trong bay ngay voi hang con nguyen.",
                account_id=account_a,
                actor="editor",
            )
            await rag.publish_version(
                document_id=v1["document_id"], version_id=v1["version_id"],
                account_id=account_a, actor="publisher",
            )
            v2 = await rag.save_draft(
                document_id=v1["document_id"], title="Doi tra",
                source="dashboard:return",
                text="return_v2 Doi tra trong ba ngay voi hang con nguyen.",
                account_id=account_a, actor="editor",
            )
            await rag.publish_version(
                document_id=v2["document_id"], version_id=v2["version_id"],
                account_id=account_a, actor="publisher",
            )
            restored = await rag.rollback_version(
                document_id=v1["document_id"], source_version_id=v1["version_id"],
                account_id=account_a, actor="publisher",
            )
            hits = await rag.retrieve("return_v1", account_id=account_a, min_score=0)
            async with pool.acquire() as conn:
                versions = await conn.fetch(
                    """
                    SELECT version, status FROM document_versions
                    WHERE document_id=$1 ORDER BY version
                    """,
                    v1["document_id"],
                )
                audits = await conn.fetchval(
                    """
                    SELECT count(*) FROM events
                    WHERE ref_id=$1 AND kind IN (
                        'knowledge.published', 'knowledge.rolled_back'
                    )
                    """,
                    v1["document_id"],
                )
            return restored, hits, versions, audits
        finally:
            db._pool = previous
            await pool.close()

    restored, hits, versions, audits = asyncio.run(run())
    assert restored["version"] == 3
    assert hits and hits[0].version == 3 and "bay ngay" in hits[0].content
    assert [(r["version"], r["status"]) for r in versions] == [
        (1, "superseded"), (2, "superseded"), (3, "published")
    ]
    assert audits >= 4


def test_embedding_failure_keeps_existing_publish_and_marks_draft_failed(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, _ = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            v1 = await rag.save_draft(
                title="Thanh toan", source="dashboard:payment",
                text="payment_live Thanh toan bang chuyen khoan hoac tien mat.",
                account_id=account_a, actor="editor",
            )
            await rag.publish_version(
                document_id=v1["document_id"], version_id=v1["version_id"],
                account_id=account_a, actor="publisher",
            )

            async def broken(*_args, **_kwargs):
                raise RuntimeError("embedding timeout")

            monkeypatch.setattr(rag, "embed", broken)
            with pytest.raises(RuntimeError, match="embedding timeout"):
                await rag.save_draft(
                    document_id=v1["document_id"], title="Thanh toan",
                    source="dashboard:payment",
                    text="payment_broken Noi dung moi chua duoc lap chi muc.",
                    account_id=account_a, actor="editor",
                )
            doc = await _row(
                pool,
                """
                SELECT d.current_published_version_id, v.index_status, v.index_error
                FROM documents d JOIN document_versions v
                  ON v.id=d.current_draft_version_id
                WHERE d.id=$1
                """,
                v1["document_id"],
            )
            hits = await rag.retrieve("payment_live", account_id=account_a, min_score=0)
            return v1, doc, hits
        finally:
            db._pool = previous
            await pool.close()

    v1, doc, hits = asyncio.run(run())
    assert doc["current_published_version_id"] == v1["version_id"]
    assert doc["index_status"] == "failed"
    assert "embedding timeout" in doc["index_error"]
    assert hits and hits[0].version == 1


def test_concurrent_publish_is_idempotent_and_has_one_current_version(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, _ = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            draft = await rag.save_draft(
                title="Van chuyen", source="dashboard:shipping",
                text="shipping_live Giao hang trong hai ngay lam viec.",
                account_id=account_a, actor="editor",
            )
            results = await asyncio.gather(
                rag.publish_version(
                    document_id=draft["document_id"], version_id=draft["version_id"],
                    account_id=account_a, actor="publisher-a",
                ),
                rag.publish_version(
                    document_id=draft["document_id"], version_id=draft["version_id"],
                    account_id=account_a, actor="publisher-b",
                ),
            )
            async with pool.acquire() as conn:
                current = await conn.fetchval(
                    "SELECT count(*) FROM document_versions WHERE document_id=$1 AND status='published'",
                    draft["document_id"],
                )
                publish_events = await conn.fetchval(
                    "SELECT count(*) FROM events WHERE ref_id=$1 AND kind='knowledge.published'",
                    draft["document_id"],
                )
            return results, current, publish_events
        finally:
            db._pool = previous
            await pool.close()

    results, current, publish_events = asyncio.run(run())
    assert sum(not result["already_published"] for result in results) == 1
    assert current == 1
    assert publish_events == 1


def test_retrieval_never_crosses_account_scope(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    async def run():
        pool, account_a, account_b = await _prepare(csdl_kiem_thu)
        previous = db._pool
        db._pool = pool
        monkeypatch.setattr(rag, "embed", _fake_vectors)
        try:
            draft = await rag.save_draft(
                title="Noi bo A", source="dashboard:tenant-a",
                text="tenant_a_secret Chi danh cho tai khoan A va khong duoc lo.",
                account_id=account_a, actor="editor",
            )
            await rag.publish_version(
                document_id=draft["document_id"], version_id=draft["version_id"],
                account_id=account_a, actor="publisher",
            )
            own = await rag.retrieve("tenant_a_secret", account_id=account_a, min_score=0)
            other = await rag.retrieve("tenant_a_secret", account_id=account_b, min_score=0)
            no_scope = await rag.retrieve("tenant_a_secret", min_score=0)
            return own, other, no_scope
        finally:
            db._pool = previous
            await pool.close()

    own, other, no_scope = asyncio.run(run())
    assert own
    assert other == []
    assert no_scope == []


def test_legacy_migration_preserves_rows_as_unpublished_draft(csdl_kiem_thu: str):
    async def run():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            await conn.execute(SCHEMA.read_text(encoding="utf-8"))
            migrations = discover_migrations()
            before = [m for m in migrations if m.version <= "0041"]
            after = [m for m in migrations if m.version > "0041"]
            await apply_migrations(conn, before)
            doc_id = await conn.fetchval(
                """
                INSERT INTO documents (title, source, chunk_count)
                VALUES ('Legacy', 'legacy:file', 1) RETURNING id
                """
            )
            chunk_id = await conn.fetchval(
                """
                INSERT INTO chunks (document_id, ord, content)
                VALUES ($1, 0, 'legacy_content_must_survive') RETURNING id
                """,
                doc_id,
            )
            await apply_migrations(conn, after)
            return await conn.fetchrow(
                """
                SELECT d.lifecycle_status, d.current_published_version_id,
                       v.status, v.content, c.id AS chunk_id,
                       c.document_version_id
                FROM documents d
                JOIN document_versions v ON v.id=d.current_draft_version_id
                JOIN chunks c ON c.document_version_id=v.id
                WHERE d.id=$1
                """,
                doc_id,
            ), chunk_id
        finally:
            await conn.close()

    row, chunk_id = asyncio.run(run())
    assert row["lifecycle_status"] == "draft"
    assert row["current_published_version_id"] is None
    assert row["status"] == "draft"
    assert "legacy_content_must_survive" in row["content"]
    assert row["chunk_id"] == chunk_id
    assert row["document_version_id"] is not None


def test_api_rbac_draft_publish_history_and_probe(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    account_id = uuid4()
    user_id = uuid4()
    current_user = {
        "value": nguoi_thu("cau_hinh.doc", id=user_id, ten="viewer")
    }
    app = FastAPI()
    app.include_router(tri_thuc_api.router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: current_user["value"]
    monkeypatch.setattr(rag, "embed", _fake_vectors)

    @app.on_event("startup")
    async def startup():
        db._pool = await asyncpg.create_pool(
            csdl_kiem_thu, min_size=1, max_size=4, init=_codec
        )
        async with db._pool.acquire() as conn:
            await conn.execute(SCHEMA.read_text(encoding="utf-8"))
            await apply_all(conn)
            await conn.execute(
                """
                INSERT INTO nguoi_dung (
                    id, ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro
                ) VALUES ($1,'kb-user','x','KB User','nhan_vien')
                """,
                user_id,
            )
            await conn.execute(
                """
                INSERT INTO channel_accounts (
                    id, channel, display_name, external_account_id, status
                ) VALUES ($1,'webchat','KB Account',$2,'active')
                """,
                account_id,
                f"kb-api-{uuid4()}",
            )
            await conn.execute(
                """
                INSERT INTO account_memberships (account_id,user_id,role)
                VALUES ($1,$2,'manager')
                """,
                account_id,
                user_id,
            )

    @app.on_event("shutdown")
    async def shutdown():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    with TestClient(app) as client:
        payload = {
            "account_id": str(account_id),
            "title": "API Policy",
            "text": "api_policy_content Noi dung da duoc lap chi muc day du.",
        }
        denied = client.post("/api/knowledge", json=payload)
        assert denied.status_code == 403

        current_user["value"] = nguoi_thu(
            "cau_hinh.doc", "cau_hinh.sua", id=user_id, ten="publisher"
        )
        accounts = client.get("/api/knowledge/accounts")
        assert accounts.status_code == 200
        assert str(UUID(int=0)) not in {item["id"] for item in accounts.json()}

        current_user["value"] = nguoi_thu(
            "cau_hinh.doc",
            "cau_hinh.sua",
            "hoi_thoai.xem_tat_ca",
            id=user_id,
            ten="publisher-admin",
        )
        admin_accounts = client.get("/api/knowledge/accounts")
        assert str(UUID(int=0)) in {item["id"] for item in admin_accounts.json()}

        created = client.post("/api/knowledge", json=payload)
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "draft"

        probe_draft = client.post(
            "/api/knowledge/probe",
            json={"account_id": str(account_id), "question": "api_policy_content"},
        )
        assert probe_draft.status_code == 200
        assert probe_draft.json()["hits"] == []

        published = client.post(
            f"/api/knowledge/{body['document_id']}/publish",
            json={"account_id": str(account_id), "version_id": body["version_id"]},
        )
        assert published.status_code == 200

        history = client.get(
            f"/api/knowledge/{body['document_id']}/versions",
            params={"account_id": str(account_id)},
        )
        assert history.status_code == 200
        assert history.json()[0]["status"] == "published"

        probe_live = client.post(
            "/api/knowledge/probe",
            json={"account_id": str(account_id), "question": "api_policy_content"},
        )
        hit = probe_live.json()["hits"][0]
        assert hit["version"] == 1
        assert hit["version_id"] == body["version_id"]
        assert hit["chunk_id"]

