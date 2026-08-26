"""Contract của migration nền tảng nhiều tài khoản.

Các test này khóa những invariant cần có trước khi chạy integration trên
PostgreSQL thật. Test integration được bật bằng TEST_DATABASE_URL.
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import asyncpg
import pytest

from agent.migrations.runner import apply_all


ROOT = Path(__file__).resolve().parent.parent
MIGRATION = (
    ROOT
    / "agent"
    / "migrations"
    / "versions"
    / "0001_account_aware_foundation.sql"
)


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_migration_tao_du_bon_bang_nen_tang():
    """Bỏ một bảng sẽ làm mất vault, phân quyền hoặc lịch sử sức khỏe."""
    sql = _sql()
    for table in (
        "channel_accounts",
        "credential_secrets",
        "account_memberships",
        "account_health_events",
    ):
        assert f"create table if not exists {table}" in sql


def test_hoi_thoai_duoc_dinh_danh_trong_pham_vi_tai_khoan():
    """Cùng external_id ở hai account phải là hai hội thoại khác nhau."""
    sql = _sql()
    assert "add column if not exists account_id uuid" in sql
    assert "unique (account_id, external_id)" in sql
    assert "drop constraint if exists conversations_channel_external_id_key" in sql


def test_du_lieu_cu_duoc_backfill_truoc_khi_account_id_thanh_bat_buoc():
    """Nâng cấp DB đang có hội thoại không được làm mất hoặc bỏ rơi dữ liệu."""
    sql = _sql()
    insert_at = sql.index("insert into channel_accounts")
    update_at = sql.index("update conversations")
    not_null_at = sql.index("alter column account_id set not null")
    assert insert_at < update_at < not_null_at
    assert "select distinct" in sql[insert_at:update_at]


def test_bi_mat_chi_nam_trong_ciphertext():
    """Bảng vault không được có cột token dạng rõ."""
    sql = _sql()
    vault = sql.split("create table if not exists credential_secrets", 1)[1]
    vault = vault.split("create table", 1)[0]
    assert re.search(r"ciphertext\s+bytea\s+not null", vault)
    assert re.search(r"nonce\s+bytea\s+not null", vault)
    assert "access_token" not in vault
    assert "refresh_token" not in vault


def test_foundation_migration_chay_tren_postgresql_that_khi_duoc_cap_url():
    """Chạy baseline + migration hai lần và kiểm invariant bằng truy vấn thật."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    async def verify():
        admin = await asyncpg.connect(database_url)
        schema_name = "test_account_foundation"
        try:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            await admin.execute(f'CREATE SCHEMA "{schema_name}"')
            await admin.execute(f'SET search_path TO "{schema_name}", public')
            baseline = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
            await admin.execute(baseline)
            await admin.execute(
                """
                INSERT INTO conversations (channel, external_id, customer_name)
                VALUES ('messenger', 'same-id', 'Khách cũ')
                """
            )

            await apply_all(admin)
            await apply_all(admin)

            assert await admin.fetchval(
                "SELECT count(*) FROM conversations WHERE account_id IS NULL"
            ) == 0
            legacy_id = await admin.fetchval(
                "SELECT account_id FROM conversations WHERE external_id = 'same-id'"
            )
            await admin.execute(
                """
                INSERT INTO channel_accounts
                    (channel, display_name, external_account_id, status)
                VALUES ('messenger', 'Page thứ hai', 'page-2', 'active')
                """
            )
            second_id = await admin.fetchval(
                "SELECT id FROM channel_accounts WHERE external_account_id = 'page-2'"
            )
            # Từ migration 0004, `conversations.contact_id` và
            # `contact_point_id` là NOT NULL — mọi hội thoại phải thuộc về
            # một danh tính khách. Test này viết từ thời 0001 nên chèn thiếu
            # hai cột đó, và đã hỏng suốt từ lúc 0004 ra đời mà không ai
            # biết: nó luôn bị skip vì máy nào cũng thiếu TEST_DATABASE_URL.
            #
            # Giữ nguyên điều đang được kiểm — hai tài khoản dùng chung một
            # `external_id` — nhưng dựng đủ contact và contact_point trước.
            contact_id = await admin.fetchval(
                "INSERT INTO contacts (display_name) VALUES ('Khách page 2') "
                "RETURNING id"
            )
            point_id = await admin.fetchval(
                """
                INSERT INTO contact_points
                    (contact_id, channel_account_id, external_user_id)
                VALUES ($1, $2, 'khach-page-2')
                RETURNING id
                """,
                contact_id,
                second_id,
            )
            await admin.execute(
                """
                INSERT INTO conversations
                    (account_id, channel, external_id, contact_id, contact_point_id)
                VALUES ($1, 'messenger', 'same-id', $2, $3)
                """,
                second_id,
                contact_id,
                point_id,
            )
            assert second_id != legacy_id
            assert await admin.fetchval(
                "SELECT count(*) FROM conversations WHERE external_id = 'same-id'"
            ) == 2
        finally:
            await admin.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
            await admin.close()

    asyncio.run(verify())
