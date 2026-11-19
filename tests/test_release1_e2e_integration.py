"""
DEV-12: Kiểm thử tích hợp tổng thể Release 1 trên ứng dụng FastAPI và PostgreSQL thật.

Bao phủ xuyên suốt 18 luồng E2E bắt buộc (E2E-01..E2E-18) cùng tương thích
migration (0001..0045), tương tác liên module giữa DEV-02/04/08/09/10/11 và
ERPNext development localhost (khi đang chạy), đồng thời không chạm logic SLA.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest

from agent import db, mcp_server
from agent.config import ROOT, settings
from agent.core import cong_viec, rag, tools
from agent.erp.hop_dong import LoiERP
from agent.omnichannel import giai_quyet
from agent.shipping import doi_soat, ghn as ghn_mod, service
from tests.test_hoan_thien_luong import _don
from tests.test_nghiem_thu_saas import (
    GOC_WEB,
    _kenh_webchat,
    _khach_nhan,
    _nhan_vien_moi,
    _quan_tri_vao,
    _sql,
)


def _fake_vectors(texts: list[str], **_kw: Any) -> list[list[float]]:
    vecs: list[list[float]] = []
    for text in texts:
        low = text.lower()
        v = [0.0] * 768
        if "phien_ban_v1" in low or "chinh_sach_v1" in low:
            v[0] = 1.0
        elif "phien_ban_v2" in low or "chinh_sach_v2" in low:
            v[1] = 1.0
        elif "draft_bi_mat" in low:
            v[2] = 1.0
        elif "account_rieng" in low:
            v[3] = 1.0
        else:
            v[4] = 1.0
        vecs.append(v)
    return vecs


async def _fake_vectors_async(texts: list[str], **kw: Any) -> list[list[float]]:
    return _fake_vectors(texts, **kw)


@asynccontextmanager
async def _pool(csdl_url: str):
    from scripts.dung_csdl_kiem_thu import dung

    await dung(csdl_url)

    async def codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(csdl_url, min_size=1, max_size=6, init=codec)
    old = db._pool
    db._pool = pool
    try:
        yield pool
    finally:
        await pool.close()
        db._pool = old


# ------------------------------------------------------------------
# 1. Migration Upgrade từ DB có sẵn dữ liệu trước 0039 -> 0045
# ------------------------------------------------------------------

def test_dev12_migration_upgrade_from_pre_0039_preserves_legacy_data(csdl_kiem_thu: str):
    migrations_dir = ROOT / "agent" / "migrations" / "versions"
    schema_sql = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    all_files = sorted(migrations_dir.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    pre_0039 = [p for p in all_files if int(p.name.split("_", 1)[0]) < 39]
    post_0039 = [p for p in all_files if int(p.name.split("_", 1)[0]) >= 39]
    # 0039–0044 của main (0043 bỏ trống), 0045–0050 là Release 1 đã đổi số.
    assert [p.name[:4] for p in post_0039] == [
        "0039", "0040", "0041", "0042", "0044",
        "0045", "0046", "0047", "0048", "0049", "0050",
    ]

    async def run():
        conn = await asyncpg.connect(csdl_kiem_thu)
        try:
            await conn.execute(schema_sql)
            for p in pre_0039:
                await conn.execute(p.read_text(encoding="utf-8"))

            # Seed dữ liệu lịch sử trước đợt 0039..0045
            uid = await conn.fetchval(
                "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
                "VALUES ('legacy_staff', 'x', 'Legacy Staff', 'quan_tri') RETURNING id"
            )
            acc_id = await conn.fetchval(
                "INSERT INTO channel_accounts (channel, display_name, external_account_id, status) "
                "VALUES ('webchat', 'Legacy Shop', 'leg-1', 'active') RETURNING id"
            )
            contact_id = await conn.fetchval(
                "INSERT INTO contacts (display_name, phone) "
                "VALUES ('Chị Mai', '0911111111') RETURNING id"
            )
            contact_point_id = await conn.fetchval(
                "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) "
                "VALUES ($1, $2, 'ext-leg-1') RETURNING id",
                contact_id,
                acc_id,
            )
            conv_id = await conn.fetchval(
                "INSERT INTO conversations (channel, contact_id, contact_point_id, external_id, customer_name, account_id, state) "
                "VALUES ('webchat', $1, $2, 'ext-leg-1', 'Chị Mai', $3, 'open') RETURNING id",
                contact_id,
                contact_point_id,
                acc_id,
            )
            await conn.execute(
                "INSERT INTO cong_viec (tieu_de, trang_thai, nguoi_giao, conversation_id) "
                "VALUES ('Việc lịch sử đang mở', 'moi', $1, $2)",
                uid,
                conv_id,
            )
            oid_ship = await conn.fetchval(
                "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, trang_thai, "
                "erp_ma_don, ma_van_don, don_vi_van_chuyen) "
                "VALUES ('LEG-SHIP-1', 'Chị Mai', '0911111111', '12 Lê Lợi Q1 HCM', 'da_chot', "
                "'SAL-LEG-1', 'GHN-LEG-1', 'ghn') RETURNING id"
            )
            oid_noship = await conn.fetchval(
                "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, trang_thai) "
                "VALUES ('LEG-NOSHIP-1', 'Chị Lan', '0922222222', '15 Hai Bà Trưng Q1 HCM', 'da_chot') RETURNING id"
            )
            doc_id = await conn.fetchval(
                "INSERT INTO documents (title, source, chunk_count) "
                "VALUES ('Legacy Policy', 'legacy.md', 1) RETURNING id"
            )
            vec = "[" + ",".join(["0.1"] * 768) + "]"
            await conn.execute(
                "INSERT INTO chunks (document_id, ord, content, embedding) "
                "VALUES ($1, 0, 'Noi dung lich su quan trong', $2::vector)",
                doc_id,
                vec,
            )

            # Nâng cấp tuần tự 0039 -> 0045
            for p in post_0039:
                await conn.execute(p.read_text(encoding="utf-8"))

            # Kiểm tra dữ liệu cũ được bảo toàn đúng kỳ vọng
            doc_row = await conn.fetchrow(
                "SELECT lifecycle_status, current_draft_version_id, current_published_version_id "
                "FROM documents WHERE id = $1",
                doc_id,
            )
            # Tài liệu cũ có chỉ mục đủ GIỮ Published khi nâng cấp (0048,
            # khi ghép vào main): nó đang là căn cứ trả lời khách.
            assert doc_row["lifecycle_status"] == "published"
            assert doc_row["current_draft_version_id"] is None
            assert doc_row["current_published_version_id"] is not None

            dv_row = await conn.fetchrow(
                "SELECT version, status, content, index_status FROM document_versions WHERE document_id = $1",
                doc_id,
            )
            assert dv_row["version"] == 1 and dv_row["status"] == "published"
            assert "Noi dung lich su quan trong" in dv_row["content"]
            assert dv_row["index_status"] == "ready"

            # Orders cũ có vận đơn + ERP -> queue sync + shipping_waybill_requests confirmed
            ship_row = await conn.fetchrow(
                "SELECT erp_van_chuyen_trang_thai FROM orders WHERE id = $1", oid_ship
            )
            assert ship_row["erp_van_chuyen_trang_thai"] == "pending"
            req_ship = await conn.fetchrow(
                "SELECT trang_thai, ma_van_don, client_order_code "
                "FROM shipping_waybill_requests WHERE order_id = $1",
                oid_ship,
            )
            assert req_ship["trang_thai"] == "confirmed"
            assert req_ship["ma_van_don"] == "GHN-LEG-1"
            assert req_ship["client_order_code"] == "LEG-SHIP-1"

            # Order chưa có vận đơn không bị tạo nhầm
            assert (
                await conn.fetchval(
                    "SELECT count(*) FROM shipping_waybill_requests WHERE order_id = $1",
                    oid_noship,
                )
                == 0
            )
        finally:
            await conn.close()

    asyncio.run(run())


# ------------------------------------------------------------------
# 2. E2E-01..E2E-07 & E2E-18: Inbox -> AI -> Handover -> Pending Action
#    -> ERP Confirm/Timeout -> Resolve Guard -> Reopen -> New Task
# ------------------------------------------------------------------

def test_e2e_01_to_07_inbox_handover_pending_action_resolve_and_reopen(
    app_that, monkeypatch: pytest.MonkeyPatch
):
    from agent.core import agent as agent_mod

    # Mock LLM trả lời tự động (không gọi API ngoài), vẫn kiểm chứng luồng auto-reply -> takeover
    async def _fake_respond(**_kw):
        return agent_mod.Reply(text="Chào chị, em đã ghi nhận và kiểm tra cho mình ngay ạ.")

    monkeypatch.setattr(agent_mod, "respond", _fake_respond)

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, "E2E Shop", agent_bat=True)
    uid_nv, nv = _nhan_vien_moi(qt, "nv_e2e")
    _, xem = _nhan_vien_moi(qt, "xem_e2e", vai_tro=None)
    from tests.test_nghiem_thu_saas import _them_thanh_vien

    _them_thanh_vien(app_that, tk, uid_nv, role="agent")

    # E2E-01: Khách gửi tin -> nhận đúng 1 hội thoại, idempotent theo client_message_id
    app_that.cookies.clear()
    ses = app_that.post(f"/webchat/{tk}/session", json={}, headers={"Origin": GOC_WEB}).json()["token"]
    m0 = app_that.post(
        f"/webchat/{tk}/messages",
        json={"client_message_id": str(uuid.uuid4()), "text": "Em ơi kiểm tra giúp chị đơn hàng", "visitor_name": "Chị Hoa"},
        headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ses}"},
    )
    assert m0.status_code == 202
    client_msg_id = str(uuid.uuid4())
    m1 = app_that.post(
        f"/webchat/{tk}/messages",
        json={"client_message_id": client_msg_id, "text": "Chị muốn hủy đơn này", "visitor_name": "Chị Hoa"},
        headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ses}"},
    )
    m2 = app_that.post(
        f"/webchat/{tk}/messages",
        json={"client_message_id": client_msg_id, "text": "Chị muốn hủy đơn này", "visitor_name": "Chị Hoa"},
        headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ses}"},
    )
    assert m1.status_code == 202 and m2.status_code == 202

    convs = qt.get("/api/inbox/conversations").json()["items"]
    assert len(convs) == 1
    conv_id = uuid.UUID(convs[0]["id"])

    async def _dem_tin():
        r = await db.fetchrow(
            "SELECT count(*) AS n FROM messages WHERE conversation_id = $1 AND role = 'customer'",
            conv_id,
        )
        return int(r["n"])

    # Tránh trùng lặp tin có cùng client_message_id
    so_tin = _sql(app_that, _dem_tin)
    assert so_tin == 2

    # E2E-02: Nhân viên takeover -> mode='human' (AI dừng tự động trả lời)
    detail_before = nv.get(f"/api/inbox/conversations/{conv_id}").json()
    take = nv.post(
        f"/api/inbox/conversations/{conv_id}/takeover",
        json={"expected_version": detail_before["version"], "reason": "Nhân viên tiếp quản xử lý hủy đơn"},
    )
    assert take.status_code == 200
    detail = nv.get(f"/api/inbox/conversations/{conv_id}").json()
    assert detail["mode"] == "human" and detail["status"] == "escalated"

    # Tạo đơn gắn với conversation_id này và giả lập AI chạy tool `_xin_huy_don`
    oid_s, ma_don = _don(app_that, "da_chot", conversation_id=conv_id, erp_ma_don="SAL-E2E-1")
    oid = uuid.UUID(oid_s)

    async def _ai_xin_huy():
        return await tools.run_tool(
            "xin_huy_don",
            {"ma_don": ma_don, "ly_do": "Khách đổi ý qua chat"},
            conv_id,
        )

    tool_out = _sql(app_that, _ai_xin_huy)
    assert "đã ghi nhận" in tool_out.get("ghi_chu", "").lower()

    # Kiểm tra đơn chưa tự hủy và đã sinh Pending Action gắn đúng order_id + conversation_id
    async def _doc_task_va_don():
        don = await db.fetchrow("SELECT trang_thai, yeu_cau_huy_luc FROM orders WHERE id = $1", oid)
        task = await db.fetchrow(
            "SELECT id, trang_thai, order_id, conversation_id, loai_xu_ly_don "
            "FROM cong_viec WHERE order_id = $1",
            oid,
        )
        return dict(don), dict(task)

    don_row, task_row = _sql(app_that, _doc_task_va_don)
    assert don_row["trang_thai"] == "da_chot" and don_row["yeu_cau_huy_luc"] is not None
    assert task_row["trang_thai"] == "moi"
    assert task_row["conversation_id"] == conv_id
    assert task_row["loai_xu_ly_don"] == "huy"
    task_id = str(task_row["id"])

    # E2E-03: Khi Pending Action còn mở -> Resolve bị chặn (HTTP 409)
    r_res_blocked = nv.post(f"/api/inbox/conversations/{conv_id}/giai-quyet")
    assert r_res_blocked.status_code == 409
    assert r_res_blocked.json()["detail"]["code"] == "conversation_has_pending_tasks"

    # Chặn bypass qua PUT /api/cong-viec/{id} đánh dấu xong trực tiếp
    r_bypass = nv.put(f"/api/cong-viec/{task_id}", json={"trang_thai": "xong"})
    assert r_bypass.status_code == 409

    # E2E-18: Người không có quyền đủ (`don.sua` + `cong_viec.sua`) bị 403 khi gọi confirm-action-result
    for khach_khong_quyen in (xem, nv):
        assert khach_khong_quyen.post(
            f"/api/orders/{oid_s}/confirm-action-result",
            json={"cong_viec_id": task_id, "loai": "huy", "ket_qua": "thanh_cong"},
        ).status_code == 403

    # E2E-07: ERPNext Timeout khi lấy bằng chứng / đối soát -> HTTP 503 / cho_doi_soat, KHÔNG tự xác nhận xong
    async def _timeout_doc_don(_erp_ma_don: str):
        raise LoiERP("ERPNext read timeout")

    monkeypatch.setattr(cong_viec, "_doc_don_erp", _timeout_doc_don)
    r_ev_timeout = qt.get(f"/api/orders/{oid_s}/action-evidence?cong_viec_id={task_id}")
    assert r_ev_timeout.status_code == 503

    r_confirm_timeout = qt.post(
        f"/api/orders/{oid_s}/confirm-action-result",
        json={"cong_viec_id": task_id, "loai": "huy", "ket_qua": "thanh_cong"},
    )
    assert r_confirm_timeout.status_code == 202
    assert r_confirm_timeout.json()["ket_qua"] == "cho_doi_soat"
    assert nv.post(f"/api/inbox/conversations/{conv_id}/giai-quyet").status_code == 409

    # E2E-06: ERPNext xác nhận Sales Order đã Cancelled -> confirm-action-result thành công (200) & idempotent
    async def _cancelled_doc_don(erp_ma_don: str):
        return {
            "name": erp_ma_don,
            "status": "Cancelled",
            "docstatus": 2,
            "modified": "2026-11-12 10:00:00",
        }

    monkeypatch.setattr(cong_viec, "_doc_don_erp", _cancelled_doc_don)
    r_confirm_ok = qt.post(
        f"/api/orders/{oid_s}/confirm-action-result",
        json={"cong_viec_id": task_id, "loai": "huy", "ket_qua": "thanh_cong"},
    )
    assert r_confirm_ok.status_code == 200
    assert r_confirm_ok.json()["ket_qua"] == "thanh_cong"
    assert r_confirm_ok.json()["trang_thai_cong_viec"] == "xong"

    # Gọi lặp lại lần 2 -> idempotent
    r_confirm_idem = qt.post(
        f"/api/orders/{oid_s}/confirm-action-result",
        json={"cong_viec_id": task_id, "loai": "huy", "ket_qua": "thanh_cong"},
    )
    assert r_confirm_idem.status_code == 200
    assert r_confirm_idem.json()["da_xu_ly_truoc"] is True

    # E2E-04: Pending Action đã xong -> Resolve thành công (200)
    r_resolve_ok = nv.post(f"/api/inbox/conversations/{conv_id}/giai-quyet")
    assert r_resolve_ok.status_code == 200
    res_detail = nv.get(f"/api/inbox/conversations/{conv_id}").json()
    assert res_detail["status"] == "closed"

    # Không thể tạo mới hoặc mở lại task trên hội thoại đang đóng (kiểm tra trigger 0040 + HTTP 409)
    r_task_closed = nv.post(
        "/api/cong-viec",
        json={"tieu_de": "Việc tạo khi đã đóng", "conversation_id": str(conv_id)},
    )
    assert r_task_closed.status_code == 409
    assert qt.put(f"/api/cong-viec/{task_id}", json={"trang_thai": "moi"}).status_code == 409

    # E2E-05: Khách nhắn lại cùng session -> Reopen hội thoại -> tạo công việc mới KHÔNG bị chặn sai
    app_that.cookies.clear()
    r_reopen_msg = app_that.post(
        f"/webchat/{tk}/messages",
        json={"client_message_id": str(uuid.uuid4()), "text": "Chị hỏi thêm về đơn mới", "visitor_name": "Chị Hoa"},
        headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ses}"},
    )
    assert r_reopen_msg.status_code == 202
    reopen_detail = nv.get(f"/api/inbox/conversations/{conv_id}").json()
    # Mở lại trả hội thoại cho agent; ở chế độ Gợi ý (mặc định của main)
    # agent soạn nháp ngay sau đó nên status thành 'assist' — cả hai đều là
    # "agent đang cầm", không phải người.
    assert reopen_detail["state"] == "open"
    assert reopen_detail["status"] in ("auto", "assist")

    r_task_reopened = nv.post(
        "/api/cong-viec",
        json={"tieu_de": "Việc mới sau reopen", "conversation_id": str(conv_id)},
    )
    assert r_task_reopened.status_code == 201


# ------------------------------------------------------------------
# 3. E2E-08, E2E-09, E2E-10: KB Draft -> Publish -> Tool/RAG/MCP -> Rollback
# ------------------------------------------------------------------

def test_e2e_08_09_10_kb_lifecycle_published_only_across_rag_tools_and_mcp(
    app_that, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(rag, "embed", _fake_vectors_async)
    monkeypatch.setattr(mcp_server, "_da_mo_db", True)

    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "nv_kb_e2e", vai_tro=None)
    tk_a = _kenh_webchat(qt, "KB Account A", agent_bat=False)
    tk_b = _kenh_webchat(qt, "KB Account B", agent_bat=False)

    # RBAC: nhân viên không có quyền cấu hình không được tạo/publish KB
    assert nv.post(
        "/api/knowledge",
        json={"account_id": tk_a, "title": "Cấm", "text": "Không được phép"},
    ).status_code == 403

    glob_scope = str(uuid.UUID(int=0))

    # Tạo Draft v1 cho Account A
    r_doc = qt.post(
        "/api/knowledge",
        json={
            "account_id": tk_a,
            "title": "Chính sách vận chuyển E2E",
            "text": "chinh_sach_v1 phien_ban_v1 Giao hàng toàn quốc trong 48 giờ",
        },
    )
    assert r_doc.status_code == 201
    doc_payload = r_doc.json()
    doc_id = doc_payload["document_id"]
    ver1_id = doc_payload["version_id"]

    # E2E-08: Khi còn ở Draft -> rag.retrieve, tool tim_kien_thuc, và MCP đều KHÔNG thấy Draft
    async def _check_draft():
        r1 = await rag.retrieve("phien_ban_v1 chinh_sach_v1", k=5, account_id=uuid.UUID(tk_a))
        t1 = await tools.run_tool("tim_kien_thuc", {"cau_hoi": "phien_ban_v1 chinh_sach_v1"})
        m1 = await mcp_server.tim_trong_kho_tri_thuc("phien_ban_v1 chinh_sach_v1", so_doan=5)
        return r1, t1, m1

    r1, t1, m1 = _sql(app_that, _check_draft)
    assert r1 == []
    assert t1["tim_thay"] is False
    assert m1["so_doan"] == 0

    # Publish v1
    pub1 = qt.post(
        f"/api/knowledge/{doc_id}/publish",
        json={"account_id": tk_a, "version_id": ver1_id},
    )
    assert pub1.status_code == 200 and pub1.json()["version"] == 1

    # E2E-09: Đã Publish v1 -> đúng account A thấy v1 qua rag.retrieve; account B cô lập hoàn toàn!
    async def _check_pub1():
        hit_a = await rag.retrieve("phien_ban_v1 chinh_sach_v1", k=5, account_id=uuid.UUID(tk_a))
        miss_b = await rag.retrieve("phien_ban_v1 chinh_sach_v1", k=5, account_id=uuid.UUID(tk_b))
        return hit_a, miss_b

    hit_a, miss_b = _sql(app_that, _check_pub1)
    assert len(hit_a) == 1 and hit_a[0].version == 1 and "48 giờ" in hit_a[0].content
    assert miss_b == []

    # Tạo bản global để kiểm chứng thêm cả tool `tim_kien_thuc` và `mcp_server.tim_trong_kho_tri_thuc`
    r_glob = qt.post(
        "/api/knowledge",
        json={
            "account_id": glob_scope,
            "title": "Quy định chung",
            "text": "phien_ban_v1 Chính sách đổi trả toàn hệ thống 7 ngày",
        },
    )
    assert r_glob.status_code == 201
    glob_payload = r_glob.json()
    glob_id = glob_payload["document_id"]
    glob_v1_id = glob_payload["version_id"]
    assert qt.post(
        f"/api/knowledge/{glob_id}/publish",
        json={"account_id": glob_scope, "version_id": glob_v1_id},
    ).status_code == 200

    # Tạo Draft v2 cho bản global, chưa Publish -> Tools & MCP vẫn CHỈ trả v1 (không trộn v2)
    r_d2 = qt.put(
        f"/api/knowledge/{glob_id}/draft",
        json={
            "account_id": glob_scope,
            "title": "Quy định chung",
            "text": "phien_ban_v2 draft_bi_mat Đổi trả mới 30 ngày chưa công bố",
        },
    )
    assert r_d2.status_code == 200
    glob_v2_id = r_d2.json()["version_id"]

    async def _check_no_mix_draft_v2():
        t_v1 = await tools.run_tool("tim_kien_thuc", {"cau_hoi": "phien_ban_v1"})
        m_v1 = await mcp_server.tim_trong_kho_tri_thuc("phien_ban_v1", so_doan=5)
        m_v2 = await mcp_server.tim_trong_kho_tri_thuc("draft_bi_mat", so_doan=5)
        return t_v1, m_v1, m_v2

    t_v1, m_v1, m_v2 = _sql(app_that, _check_no_mix_draft_v2)
    assert t_v1["tim_thay"] is True and t_v1["doan"][0]["phien_ban"] == 1
    assert m_v1["so_doan"] == 1 and m_v1["doan"][0]["phien_ban"] == 1
    assert m_v2["so_doan"] == 0

    # Publish v2 -> chuyển sang v2; sau đó Rollback về v1 -> lịch sử còn nguyên & truy xuất lại đúng nội dung v1
    pub2 = qt.post(
        f"/api/knowledge/{glob_id}/publish",
        json={"account_id": glob_scope, "version_id": glob_v2_id},
    )
    assert pub2.status_code == 200 and pub2.json()["version"] == 2
    rb = qt.post(
        f"/api/knowledge/{glob_id}/rollback",
        json={"account_id": glob_scope, "version_id": glob_v1_id},
    )
    assert rb.status_code == 200

    versions = qt.get(
        f"/api/knowledge/{glob_id}/versions",
        params={"account_id": glob_scope},
    ).json()
    assert len(versions) >= 3  # Không xóa lịch sử v1/v2

    async def _check_after_rollback():
        tool_rb = await tools.run_tool("tim_kien_thuc", {"cau_hoi": "phien_ban_v1"})
        mcp_rb = await mcp_server.tim_trong_kho_tri_thuc("phien_ban_v1", so_doan=5)
        return tool_rb, mcp_rb

    tool_rb, mcp_rb = _sql(app_that, _check_after_rollback)
    assert tool_rb["tim_thay"] is True and "7 ngày" in tool_rb["doan"][0]["noi_dung"]
    assert mcp_rb["so_doan"] == 1 and "7 ngày" in mcp_rb["doan"][0]["noi_dung"]


# ------------------------------------------------------------------
# 4. E2E-11..E2E-18: GHN Create Timeout -> Reconciliation -> Manual Confirm
#    -> DEV-02 ERP Sync -> Dashboard Bundle Verification
# ------------------------------------------------------------------

def test_e2e_11_to_17_ghn_timeout_reconcile_erp_and_dashboard_ui(
    app_that, monkeypatch: pytest.MonkeyPatch
):
    from agent.shipping.ghn import GHNShippingProvider

    # Kiểm tra Dashboard source & bundle đã chứa đầy đủ giao diện xử lý DEV-08
    js_src = (ROOT / "dashboard" / "src" / "05-don-kho.js").read_text(encoding="utf-8")
    js_bundle = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    for marker in ("data-odoisoat", "data-oxnvandon", "/shipping-reconcile", "/shipping-manual-confirm", "manual_required"):
        assert marker in js_src
        assert marker in js_bundle

    monkeypatch.setattr(settings, "shipping_provider", "ghn")
    qt = _quan_tri_vao(app_that)
    oid_s, ma_don = _don(
        app_that,
        "da_chot",
        khach_dia_chi="12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh",
        erp_ma_don="SAL-E2E-SHIP",
    )
    oid = uuid.UUID(oid_s)

    async def _prep_kho():
        await db.execute(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ('SP1', 50) "
            "ON CONFLICT (ma) DO UPDATE SET so_luong = 50"
        )

    _sql(app_that, _prep_kho)

    state = {"create_calls": 0, "lookup_mode": "503"}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            state["create_calls"] += 1
            raise httpx.ReadTimeout("timeout", request=req)
        if req.url.path.endswith("/shipping-order/detail-by-client-code"):
            if state["lookup_mode"] == "503":
                return httpx.Response(503, json={"message": "busy"})
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": {
                        "order_code": "GHN-E2E-REC",
                        "client_order_code": ma_don,
                        "status": "ready_to_pick",
                        "total_fee": 25000,
                    },
                },
            )
        raise AssertionError(f"Unexpected URL: {req.url}")

    goc_client = httpx.AsyncClient
    monkeypatch.setattr(ghn_mod.httpx, "AsyncClient", lambda **kw: goc_client(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(ghn_mod, "_DISTRICTS_CACHE", [{"DistrictID": 1442, "DistrictName": "Quận 1"}])
    monkeypatch.setattr(ghn_mod, "_WARDS_CACHE", {1442: [{"WardCode": "20101", "WardName": "Phường Bến Nghé"}]})
    monkeypatch.setitem(
        service._PROVIDERS,
        "ghn",
        GHNShippingProvider(api_url="https://dev-online-gateway.ghn.vn/shiip/public-api/v2", token="t", shop_id="1"),
    )

    # E2E-13: Timeout khi tạo -> HTTP 409, hiện trên /api/orders để Dashboard vẽ nút Kiểm tra/Xác nhận GHN
    r1 = qt.post(f"/api/orders/{oid_s}/van-don", json={})
    assert r1.status_code == 409 and state["create_calls"] == 1
    row_api = next(o for o in qt.get("/api/orders").json() if o["id"] == oid_s)
    assert row_api["van_don_trang_thai_yeucau"] == "unknown_timeout"

    # E2E-15: Đối soát hết hạn -> chuyển manual_required
    async def _force_exhaust():
        await db.execute(
            "UPDATE shipping_waybill_requests SET so_lan_doi_soat = $2, doi_soat_tiep_luc = now() WHERE order_id = $1",
            oid,
            doi_soat.SO_LAN_DOI_SOAT_TOI_DA - 1,
        )
        return await doi_soat.quet_doi_soat_van_don(limit=5)

    res_ex = _sql(app_that, _force_exhaust)
    assert res_ex["can_thu_cong"] == 1
    assert qt.get(f"/api/orders/{oid_s}/shipping-reconciliation").json()["reconciliation"]["trang_thai"] == "manual_required"

    # E2E-14 + E2E-12: Khi GHN trả về đơn khi bấm Kiểm tra GHN nhưng ERP lỗi -> vẫn khôi phục mã GHN và giữ ERP ở trạng thái retry (không gọi GHN create lại!)
    class FailingErp:
        async def dong_bo_van_don(self, **_kw):
            raise LoiERP("ERP temporary 503")

    monkeypatch.setattr("agent.erp.dong_bo_van_don._nguon_mac_dinh", lambda: FailingErp())
    state["lookup_mode"] = "found"
    r_re = qt.post(f"/api/orders/{oid_s}/shipping-reconcile")
    assert r_re.status_code == 200 and r_re.json()["ma_van_don"] == "GHN-E2E-REC"
    assert state["create_calls"] == 1

    # E2E-11: Retry riêng ERP thành công qua /shipping-erp-retry không gọi GHN create
    synced_calls: list[str] = []

    class WorkingErp:
        async def dong_bo_van_don(self, **kw):
            synced_calls.append(kw["ma_van_don"])
            return True

    monkeypatch.setattr("agent.erp.dong_bo_van_don._nguon_mac_dinh", lambda: WorkingErp())
    r_erp = qt.post(f"/api/orders/{oid_s}/shipping-erp-retry")
    assert r_erp.status_code == 200 and r_erp.json()["trang_thai"] == "synced"
    assert synced_calls == ["GHN-E2E-REC"]
    assert state["create_calls"] == 1

    # E2E-16 & E2E-18: Xác nhận vận đơn thủ công qua /shipping-manual-confirm khi manual_required + RBAC
    _, xem = _nhan_vien_moi(qt, "xem_ship_e2e", vai_tro=None)
    oid2_s, _ma_don2 = _don(
        app_that,
        "da_chot",
        khach_dia_chi="12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh",
        erp_ma_don="SAL-E2E-SHIP-2",
    )
    oid2 = uuid.UUID(oid2_s)
    state["lookup_mode"] = "503"
    r2 = qt.post(f"/api/orders/{oid2_s}/van-don", json={})
    assert r2.status_code == 409

    async def _force_exhaust2():
        await db.execute(
            "UPDATE shipping_waybill_requests SET so_lan_doi_soat = $2, doi_soat_tiep_luc = now() WHERE order_id = $1",
            oid2,
            doi_soat.SO_LAN_DOI_SOAT_TOI_DA - 1,
        )
        return await doi_soat.quet_doi_soat_van_don(limit=5)

    _sql(app_that, _force_exhaust2)

    assert xem.post(
        f"/api/orders/{oid2_s}/shipping-manual-confirm",
        json={"ket_qua": "da_co_van_don", "ma_van_don": "GHN-MANUAL-E2E", "ghi_chu": "Kiểm tra trực tiếp"},
    ).status_code == 403

    r_man = qt.post(
        f"/api/orders/{oid2_s}/shipping-manual-confirm",
        json={"ket_qua": "da_co_van_don", "ma_van_don": "GHN-MANUAL-E2E", "ghi_chu": "Đã đối chiếu cổng GHN"},
    )
    assert r_man.status_code == 200
    assert r_man.json()["ma_van_don"] == "GHN-MANUAL-E2E"
    assert synced_calls == ["GHN-E2E-REC", "GHN-MANUAL-E2E"]
