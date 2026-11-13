"""DEV-09: xác nhận kết quả sửa/hủy đơn dựa trên bằng chứng ERPNext."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import nguoi_thu


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "agent" / "schema.sql"
USER_ID = UUID("00000000-0000-0000-0000-000000000091")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000092")
PERMISSIONS = ("don.sua", "cong_viec.sua", "cong_viec.doc")


async def _prepare(url: str) -> None:
    from agent.migrations.runner import apply_all

    connection = await asyncpg.connect(url)
    try:
        await connection.execute(SCHEMA.read_text(encoding="utf-8"))
        await apply_all(connection)
    finally:
        await connection.close()


def _app(url: str, user: dict) -> FastAPI:
    from agent import db
    from agent.api.don_kho import router
    from agent.api.phu_thuoc import nguoi_da_dang_nhap

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: user

    async def _codec(connection):
        await connection.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    @app.on_event("startup")
    async def _open():
        db._pool = await asyncpg.create_pool(
            url, min_size=1, max_size=8, init=_codec
        )
        async with db._pool.acquire() as connection:
            await connection.execute(SCHEMA.read_text(encoding="utf-8"))
            from agent.migrations.runner import apply_all

            await apply_all(connection)

    @app.on_event("shutdown")
    async def _close():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


def _user(*permissions: str, user_id: UUID = USER_ID, name: str = "dev09") -> dict:
    return nguoi_thu(*permissions, id=str(user_id), ten=name)


async def _seed(
    url: str,
    *,
    action: str = "sua",
    assigned_to: UUID | None = USER_ID,
) -> dict:
    await _prepare(url)
    connection = await asyncpg.connect(url)
    try:
        for user_id, name in ((USER_ID, "dev09"), (OTHER_USER_ID, "dev09-other")):
            await connection.execute(
                """
                INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, ho_ten)
                VALUES ($1, $2, 'x', $2) ON CONFLICT (id) DO NOTHING
                """,
                user_id,
                name,
            )
        account_id = await connection.fetchval(
            """
            INSERT INTO channel_accounts (
                channel, display_name, status, external_account_id
            ) VALUES ('webchat', 'DEV-09', 'active', $1) RETURNING id
            """,
            f"dev09-{uuid4()}",
        )
        contact_id = await connection.fetchval(
            "INSERT INTO contacts (display_name) VALUES ('Khach DEV-09') RETURNING id"
        )
        point_id = await connection.fetchval(
            """
            INSERT INTO contact_points (
                contact_id, channel_account_id, external_user_id
            ) VALUES ($1, $2, $3) RETURNING id
            """,
            contact_id,
            account_id,
            f"customer-{uuid4()}",
        )
        conversation_id = await connection.fetchval(
            """
            INSERT INTO conversations (
                account_id, channel, external_id, customer_ref, customer_name,
                contact_id, contact_point_id, state, status, mode
            ) VALUES ($1, 'webchat', $2, $2, 'Khach DEV-09', $3, $4,
                      'open', 'escalated', 'human') RETURNING id
            """,
            account_id,
            f"conversation-{uuid4()}",
            contact_id,
            point_id,
        )
        order_id = await connection.fetchval(
            """
            INSERT INTO orders (
                ma_don, conversation_id, khach_ten, khach_sdt,
                khach_dia_chi, items, trang_thai, erp_ma_don,
                erp_dong_bo_luc, yeu_cau_huy_luc, yeu_cau_huy_ly_do
            ) VALUES ($1, $2, 'Khach DEV-09', '0900000091', 'TP HCM',
                      '[]', 'da_chot', $3, now() - interval '1 hour',
                      CASE WHEN $4 = 'huy' THEN now() ELSE NULL END,
                      CASE WHEN $4 = 'huy' THEN 'Khach doi y' ELSE NULL END)
            RETURNING id
            """,
            f"DH-{uuid4().hex[:8]}",
            conversation_id,
            f"SAL-ORD-{uuid4().hex[:8]}",
            action,
        )
        task_id = await connection.fetchval(
            """
            INSERT INTO cong_viec (
                tieu_de, mo_ta, nguon, conversation_id, contact_id,
                nguoi_nhan, order_id, loai_xu_ly_don
            ) VALUES ($1, 'Yeu cau cua khach', 'agent', $2, $3, $4, $5, $6)
            RETURNING id
            """,
            "Xử lý sửa đơn" if action == "sua" else "Xử lý hủy đơn",
            conversation_id,
            contact_id,
            assigned_to,
            order_id,
            action,
        )
        order = await connection.fetchrow(
            "SELECT erp_ma_don, erp_dong_bo_luc FROM orders WHERE id = $1",
            order_id,
        )
        return {
            "order_id": order_id,
            "task_id": task_id,
            "conversation_id": conversation_id,
            "erp_ma_don": order["erp_ma_don"],
            "erp_dong_bo_luc": order["erp_dong_bo_luc"],
        }
    finally:
        await connection.close()


async def _row(url: str, sql: str, *args):
    connection = await asyncpg.connect(url)
    try:
        return await connection.fetchrow(sql, *args)
    finally:
        await connection.close()


def _body(case: dict, result: str = "thanh_cong", **extra) -> dict:
    return {
        "cong_viec_id": str(case["task_id"]),
        "loai": "sua",
        "ket_qua": result,
        "ly_do": "Đã đối chiếu trên ERPNext",
        **extra,
    }


def _erp_doc(case: dict, *, cancelled: bool = False) -> dict:
    modified = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "name": case["erp_ma_don"],
        "status": "Cancelled" if cancelled else "To Deliver and Bill",
        "docstatus": 2 if cancelled else 1,
        "modified": modified,
    }


def _patch_erp(monkeypatch: pytest.MonkeyPatch, document=None, error=None):
    from agent.core import cong_viec

    async def read(_erp_reference: str):
        if error is not None:
            raise error
        return document

    monkeypatch.setattr(cong_viec, "_doc_don_erp", read)


def test_tc01_confirm_verified_edit_completes_task(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="sua"))
    document = _erp_doc(case)
    _patch_erp(monkeypatch, document)
    body = _body(case, erp_modified_at=document["modified"].isoformat())

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result", json=body
        )

    assert response.status_code == 200, response.text
    assert response.json()["trang_thai_cong_viec"] == "xong"
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai, ket_qua_xu_ly_don, xu_ly_boi, xong_luc "
            "FROM cong_viec WHERE id = $1",
            case["task_id"],
        )
    )
    assert row["trang_thai"] == "xong"
    assert row["ket_qua_xu_ly_don"] == "thanh_cong"
    assert row["xu_ly_boi"] == USER_ID and row["xong_luc"] is not None


def test_dev10_reads_current_erp_evidence_for_linked_task(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="sua"))
    document = _erp_doc(case)
    _patch_erp(monkeypatch, document)

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.get(
            f"/api/orders/{case['order_id']}/action-evidence",
            params={"cong_viec_id": str(case["task_id"])},
        )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "order_id": str(case["order_id"]),
        "cong_viec_id": str(case["task_id"]),
        "erp_tham_chieu": case["erp_ma_don"],
        "trang_thai": document["status"],
        "docstatus": document["docstatus"],
        "modified": document["modified"].isoformat(),
    }


def test_dev10_evidence_requires_both_order_and_task_permissions(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy"))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=True))

    with TestClient(_app(csdl_kiem_thu, _user("cong_viec.sua"))) as client:
        response = client.get(
            f"/api/orders/{case['order_id']}/action-evidence",
            params={"cong_viec_id": str(case["task_id"])},
        )

    assert response.status_code == 403
    assert "don.sua" in response.json()["detail"]


def test_tc02_confirm_verified_cancel_completes_task(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy"))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=True))
    body = _body(case, loai="huy")

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result", json=body
        )

    assert response.status_code == 200, response.text
    assert response.json()["ket_qua"] == "thanh_cong"


def test_tc03_missing_permission_is_rejected(csdl_kiem_thu: str):
    case = asyncio.run(_seed(csdl_kiem_thu))
    with TestClient(_app(csdl_kiem_thu, _user("cong_viec.sua"))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result",
            json=_body(case),
        )
    assert response.status_code == 403


def test_tc04_task_from_another_order_is_rejected(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    first = asyncio.run(_seed(csdl_kiem_thu))
    second = asyncio.run(_seed(csdl_kiem_thu))
    _patch_erp(monkeypatch, _erp_doc(first))
    body = _body(second, erp_modified_at=datetime.now(timezone.utc).isoformat())

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{first['order_id']}/confirm-action-result", json=body
        )
    assert response.status_code == 409
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai FROM cong_viec WHERE id = $1",
            second["task_id"],
        )
    )
    assert row["trang_thai"] == "moi"


def test_tc05_erp_timeout_keeps_task_for_reconciliation(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    from agent.erp.hop_dong import LoiERP

    case = asyncio.run(_seed(csdl_kiem_thu))
    _patch_erp(monkeypatch, error=LoiERP("ERPNext timeout"))
    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result",
            json=_body(
                case, erp_modified_at=datetime.now(timezone.utc).isoformat()
            ),
        )

    assert response.status_code == 202, response.text
    assert response.json()["ket_qua"] == "cho_doi_soat"
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai, ket_qua_xu_ly_don, ly_do_ket_qua "
            "FROM cong_viec WHERE id = $1",
            case["task_id"],
        )
    )
    assert row["trang_thai"] == "dang_lam"
    assert row["ket_qua_xu_ly_don"] == "cho_doi_soat"
    assert "Lỗi kỹ thuật" in row["ly_do_ket_qua"]


def test_tc06_mismatching_erp_state_cannot_complete_cancel(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy"))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=False))
    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result",
            json=_body(case, loai="huy"),
        )
    assert response.status_code == 409
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai FROM cong_viec WHERE id = $1",
            case["task_id"],
        )
    )
    assert row["trang_thai"] != "xong"


def test_tc07_repeated_confirmation_is_idempotent(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy"))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=True))
    body = _body(case, loai="huy")

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        first = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result", json=body
        )
        second = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result", json=body
        )

    assert first.status_code == second.status_code == 200
    assert second.json()["da_xu_ly_truoc"] is True
    events = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT count(*) AS n FROM events "
            "WHERE kind = 'order.action_result.confirmed' AND ref_id = $1",
            case["task_id"],
        )
    )
    assert events["n"] == 1


def test_tc08_concurrent_confirmation_has_one_final_result(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy", assigned_to=None))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=True))
    body = _body(case, loai="huy")

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda _: client.post(
                        f"/api/orders/{case['order_id']}/confirm-action-result",
                        json=body,
                    ),
                    range(2),
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert sum(response.json()["da_xu_ly_truoc"] for response in responses) == 1
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai, ket_qua_xu_ly_don FROM cong_viec WHERE id = $1",
            case["task_id"],
        )
    )
    assert tuple(row.values()) == ("xong", "thanh_cong")


def test_tc09_verified_cannot_process_stores_reason(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="sua"))
    _patch_erp(monkeypatch, _erp_doc(case))
    body = _body(
        case,
        result="khong_the",
        ly_do="Đơn đã xuất kho nên không thể đổi sản phẩm",
    )

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result", json=body
        )

    assert response.status_code == 200, response.text
    row = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT trang_thai, ket_qua_xu_ly_don, ly_do_ket_qua "
            "FROM cong_viec WHERE id = $1",
            case["task_id"],
        )
    )
    assert row["trang_thai"] == "xong"
    assert row["ket_qua_xu_ly_don"] == "khong_the"
    assert "xuất kho" in row["ly_do_ket_qua"]


def test_tc10_completing_task_does_not_resolve_conversation(
    csdl_kiem_thu: str, monkeypatch: pytest.MonkeyPatch
):
    case = asyncio.run(_seed(csdl_kiem_thu, action="huy"))
    _patch_erp(monkeypatch, _erp_doc(case, cancelled=True))

    with TestClient(_app(csdl_kiem_thu, _user(*PERMISSIONS))) as client:
        response = client.post(
            f"/api/orders/{case['order_id']}/confirm-action-result",
            json=_body(case, loai="huy"),
        )

    assert response.status_code == 200
    conversation = asyncio.run(
        _row(
            csdl_kiem_thu,
            "SELECT state, status, mode, resolved_at "
            "FROM conversations WHERE id = $1",
            case["conversation_id"],
        )
    )
    assert tuple(conversation.values()) == ("open", "escalated", "human", None)


def test_cancel_intake_creates_order_linked_task_in_postgres(
    csdl_kiem_thu: str,
):
    """Câu UPSERT nối tool hủy với DEV-09 phải chạy được trên PostgreSQL."""

    async def scenario() -> None:
        from agent import db
        from agent.core import cong_viec

        case = await _seed(csdl_kiem_thu, action="huy", assigned_to=None)
        connection = await asyncpg.connect(csdl_kiem_thu)
        try:
            await connection.execute(
                "DELETE FROM cong_viec WHERE id = $1", case["task_id"]
            )
        finally:
            await connection.close()

        db._pool = await asyncpg.create_pool(csdl_kiem_thu, min_size=1, max_size=2)
        try:
            task_id = await cong_viec.tao_tu_yeu_cau_xu_ly_don(
                order_id=case["order_id"],
                conversation_id=case["conversation_id"],
                loai="huy",
                tieu_de="Xử lý yêu cầu hủy đơn",
                mo_ta="Khách đổi ý",
            )
            assert task_id is not None
            row = await db._pool.fetchrow(
                "SELECT order_id, loai_xu_ly_don, trang_thai "
                "FROM cong_viec WHERE id = $1",
                UUID(task_id),
            )
            assert tuple(row.values()) == (case["order_id"], "huy", "moi")
        finally:
            await db._pool.close()
            db._pool = None

    asyncio.run(scenario())
