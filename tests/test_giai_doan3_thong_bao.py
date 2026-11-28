"""Kiểm thử Giai đoạn 3 – Hoàn thiện Thông báo nội bộ (BUG-TB-01/02, GAP-TB-01..04, RBAC)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat,
    _khach_nhan,
    _nhan_vien_moi,
    _quan_tri_vao,
    _sql,
    _them_thanh_vien,
)
from tests.test_thong_bao_noi_bo import (  # noqa: E402
    _chay,
    _cid_moi_nhat,
    _ghi_bao,
    _mot,
    _tb,
)

SRC = ROOT / "dashboard" / "src"


def _role_id(app_that, ten_role: str) -> str:
    row = _mot(app_that, "SELECT id FROM vai_tro WHERE ten = $1 LIMIT 1", ten_role)
    assert row is not None
    return str(row["id"])


def test_bug_tb_01_ai_chuyen_giao_het_can_xu_ly_sau_tiep_quan(app_that, monkeypatch):
    """Đọc không làm xong việc; tiếp quản xong thì ai_chuyen_giao chuyển Đã xử lý nhưng giữ trạng thái đọc."""
    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Mai", "tư vấn giúp em")
    cid = _cid_moi_nhat(app_that, tk)

    # Trước tiếp quản: đọc vẫn là Cần xử lý.
    truoc = _tb(lan)["thong_bao"][0]
    assert truoc["loai"] == "ai_chuyen_giao" and truoc["nhom"] == "can_xu_ly"
    assert lan.post(f"/api/toi/thong-bao/{truoc['id']}/da-doc").status_code == 200
    sau_doc = _tb(lan)
    assert sau_doc["can_xu_ly"] == 1
    assert sau_doc["thong_bao"][0]["da_doc"] is True
    assert sau_doc["thong_bao"][0]["nhom"] == "can_xu_ly"

    # Nhân viên khác chưa đọc bấm tiếp quản -> ai_chuyen_giao thành Đã xử lý cho cả hai,
    # KHÔNG tự đánh dấu đã đọc hộ.
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app_that, tk, minh_id)
    from agent.core import thong_bao_noi_bo as tb

    _chay(app_that, lambda: tb.bao_ai_chuyen_giao(cid, ly_do="AI chuyển tiếp"))
    assert _tb(minh, chua_doc="true")["can_xu_ly"] == 1

    ver = _mot(app_that, "SELECT version FROM conversations WHERE id = $1::uuid", cid)["version"]
    r = minh.post(
        f"/api/inbox/conversations/{cid}/takeover",
        json={"expected_version": ver, "reason": "Nhận chăm sóc khách"},
    )
    assert r.status_code == 200, r.text

    d_lan = _tb(lan)
    d_minh = _tb(minh)
    assert d_lan["can_xu_ly"] == 0
    assert d_lan["thong_bao"][0]["nhom"] == "da_xu_ly"
    assert d_minh["can_xu_ly"] == 0
    assert d_minh["chua_doc"] == 1, "tiếp quản không được tự đánh dấu đã đọc hộ"
    assert d_minh["thong_bao"][0]["da_doc"] is False
    assert d_minh["thong_bao"][0]["nhom"] == "da_xu_ly"


def test_bug_tb_01_can_duyet_nhap_duyet_va_tu_choi(app_that, monkeypatch):
    """Duyệt hoặc từ chối bản nháp AI thì can_duyet hết Cần xử lý; nháp mới không làm nháp cũ sống lại."""
    from agent import runtime
    from agent.core import agent as brain

    async def tra_loi(**kw):
        return brain.Reply(text="Dạ sản phẩm đang có sẵn ạ", cost_usd=0.0)

    monkeypatch.setattr(brain, "respond", tra_loi)
    monkeypatch.setitem(runtime.STATE, "mode", "assist")

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    from tests.test_gui_tin_va_dieu_phoi import _khach

    gui = _khach(app_that, tk)
    gui("Giá bao nhiêu vậy shop?")
    cid = _cid_moi_nhat(app_that, tk)

    d1 = _tb(qt)
    assert d1["can_xu_ly"] == 1 and d1["thong_bao"][0]["nhom"] == "can_xu_ly"
    mid1 = str(_mot(
        app_that,
        "SELECT id FROM messages WHERE conversation_id = $1::uuid AND delivery_status = 'draft' LIMIT 1",
        cid,
    )["id"])
    # Đánh dấu đã đọc dòng 1 trước khi từ chối.
    assert qt.post(f"/api/toi/thong-bao/{d1['thong_bao'][0]['id']}/da-doc").status_code == 200
    assert _tb(qt)["can_xu_ly"] == 1

    r = qt.post(f"/api/messages/{mid1}/tu-choi", json={"ly_do": "Chỉnh lại câu"})
    assert r.status_code == 200, r.text
    d2 = _tb(qt)
    assert d2["can_xu_ly"] == 0
    assert d2["thong_bao"][0]["nhom"] == "da_xu_ly"

    # Nháp mới ở lượt sau tạo thông báo mới và dòng cũ VẪN giữ da_xu_ly.
    gui("Còn màu khác không?")
    d3 = _tb(qt)
    assert d3["can_xu_ly"] == 1
    assert [x["nhom"] for x in d3["thong_bao"]] == ["can_xu_ly", "da_xu_ly"]

    # Duyệt nháp mới -> về 0 Cần xử lý.
    mid2 = str(_mot(
        app_that,
        "SELECT id FROM messages WHERE conversation_id = $1::uuid AND delivery_status = 'draft' LIMIT 1",
        cid,
    )["id"])
    r_ok = qt.post(f"/api/messages/{mid2}/approve")
    assert r_ok.status_code == 200, r_ok.text
    assert _tb(qt)["can_xu_ly"] == 0


def test_bug_tb_01_can_duyet_de_xuat_va_don_hang(app_that, monkeypatch):
    """Đề xuất AI và đơn hàng khi duyệt / từ chối / hết hạn phải rời nhóm Cần xử lý."""
    from agent.core import thong_bao_noi_bo as tb
    from agent.core import uy_quyen

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Anh Nam", "đặt giúp anh")
    cid = _cid_moi_nhat(app_that, tk)

    # 1) AI đề xuất hết hạn
    quyet = uy_quyen.QuyetDinh(hanh_dong="tao_don", che_do="tu_dong", muc="co_phe_duyet")
    dx_id, moi = _chay(
        app_that,
        lambda: uy_quyen.tao_de_xuat(
            conversation_id=cid,
            quyet=quyet,
            ly_do_can_duyet="Chờ duyệt tạo đơn",
            tham_so={},
            de_xuat={"tieu_de": "Tạo đơn dưỡng ẩm"},
            can_cu={},
            khoa_trung=f"tao_don:{uuid4()}",
        ),
    )
    assert moi is True
    can_dx = [x for x in _tb(qt, can_xu_ly="true")["thong_bao"] if x["loai"] == "can_duyet"]
    assert len(can_dx) == 1

    # Hết hạn -> tự chuyển da_xu_ly khi het_han_qua_han chạy
    _mot(app_that, "UPDATE ai_de_xuat SET het_han_luc = now() - interval '1 minute' WHERE id = $1::uuid RETURNING 1", str(dx_id))
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "can_duyet" and x["nhom"] == "can_xu_ly"] == []
    _chay(app_that, uy_quyen.het_han_qua_han, cid)
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "can_duyet"][0]["nhom"] == "da_xu_ly"

    # 2) Đơn hàng chờ duyệt -> duyệt đơn -> rời Cần xử lý
    oid = str(uuid4())
    _mot(
        app_that,
        "INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai, conversation_id) "
        "VALUES ($1::uuid, 'DH-TB-01', 'webchat', 'Anh Nam', '0909000001', 'HCM', '[]', 500000, 'cho_duyet', $2::uuid) RETURNING id",
        oid, cid,
    )
    _chay(app_that, lambda: tb.bao_can_duyet_don(oid, conversation_id=cid, ma_don="DH-TB-01"))
    can_don = [x for x in _tb(qt, can_xu_ly="true")["thong_bao"]
               if x["loai"] == "can_duyet" and (x["lien_ket"] or {}).get("loai") == "don_hang"]
    assert len(can_don) == 1

    _mot(app_that, "UPDATE orders SET trang_thai = 'da_chot' WHERE id = $1::uuid RETURNING 1", oid)
    _chay(app_that, lambda: tb.ket_thuc_duyet_don(None, oid))
    assert [x for x in _tb(qt, can_xu_ly="true")["thong_bao"] if x["loai"] == "can_duyet"] == []


def test_bug_tb_01_sla_phan_hoi_va_chu_ky(app_that):
    """Thông báo SLA chuyển Đã xử lý ngay khi nhân viên phản hồi hoặc hội thoại đóng; chu kỳ mới không kẹt."""
    from agent.core import thong_bao_noi_bo as tb
    from agent.omnichannel import sla_chuyen_giao

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Vy", "hỏi giá")
    cid = _cid_moi_nhat(app_that, tk)

    # Bắn thông báo SLA phản hồi đầu + bàn giao
    async def ghi_sla_va_cg():
        from agent import db
        async with db.pool().acquire() as conn:
            await conn.execute(
                "INSERT INTO sla_chuyen_giao (conversation_id, chu_ky, lan, bat_dau, due_at, vi_pham_luc, ket_qua) "
                "VALUES ($1::uuid, 1, 1, now() - interval '10 minute', now() - interval '2 minute', now(), 'dang_cho')",
                cid,
            )
            await tb.bao_sla(conn, [
                (UUID(cid), "first_response_breached"),
                (UUID(cid), "handover_response_breached"),
            ])

    _chay(app_that, ghi_sla_va_cg)
    sla_mo = [x for x in _tb(lan, can_xu_ly="true")["thong_bao"] if x["loai"] in ("sla_sap_tre", "sla_tre")]
    assert len(sla_mo) == 2

    # Phản hồi đầu + phản hồi chuyển giao được ghi (trong khi hội thoại VẪN open!)
    async def ghi_phan_hoi():
        from agent import db
        async with db.pool().acquire() as conn:
            mid = await conn.fetchval(
                "INSERT INTO messages (conversation_id, role, content, delivery_status, gui_boi) "
                "VALUES ($1::uuid, 'staff', 'Dạ shop hỗ trợ ngay ạ', 'sent', $2::uuid) RETURNING id",
                cid, lan_id,
            )
            await conn.execute(
                "UPDATE conversations SET first_responded_at = now() WHERE id = $1::uuid", cid)
            await sla_chuyen_giao.ghi_phan_hoi_nhan_vien(conn, UUID(cid), mid)

    _chay(app_that, ghi_phan_hoi)
    d = _tb(lan)
    sla_sau = [x for x in d["thong_bao"] if x["loai"] in ("sla_sap_tre", "sla_tre")]
    assert len(sla_sau) == 2
    assert all(x["nhom"] == "da_xu_ly" for x in sla_sau), "nhân viên đã phản hồi thì cả 2 thông báo SLA phải hết Cần xử lý"

    # Mở chu kỳ SLA 2 -> dòng chu kỳ 1 VẪN da_xu_ly, dòng chu kỳ 2 mới là can_xu_ly
    async def mo_ck_2():
        from agent import db
        async with db.pool().acquire() as conn:
            await conn.execute(
                "UPDATE conversations SET sla_chu_ky = 2, first_responded_at = NULL WHERE id = $1::uuid", cid)
            await tb.bao_sla(conn, [(UUID(cid), "first_response_warning")])

    _chay(app_that, mo_ck_2)
    sla_ck2 = [x for x in _tb(lan)["thong_bao"] if x["loai"] in ("sla_sap_tre", "sla_tre")]
    assert sla_ck2[0]["loai"] == "sla_sap_tre"
    assert sla_ck2[0]["nhom"] == "can_xu_ly"
    assert all(x["nhom"] == "da_xu_ly" for x in sla_ck2[1:])


def test_bug_tb_01_giao_hoi_thoai_lai_cho_nguoi_khac(app_that, monkeypatch):
    """Hội thoại giao cho Lan rồi chuyển cho Minh thì Lan hết Cần xử lý, Minh có Cần xử lý."""
    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app_that, tk, lan_id)
    _them_thanh_vien(app_that, tk, minh_id)
    _khach_nhan(app_that, tk, "Chị Nga", "tư vấn")
    cid = _cid_moi_nhat(app_that, tk)

    v1 = _mot(app_that, "SELECT version FROM conversations WHERE id = $1::uuid", cid)["version"]
    r1 = qt.post(f"/api/inbox/conversations/{cid}/takeover",
                 json={"expected_version": v1, "reason": "Giao Lan", "assignee_id": lan_id})
    assert r1.status_code == 200
    assert _tb(lan, can_xu_ly="true")["can_xu_ly"] == 1

    r2 = qt.post(f"/api/inbox/conversations/{cid}/takeover",
                 json={"expected_version": r1.json()["version"], "reason": "Chuyển Minh", "assignee_id": minh_id})
    assert r2.status_code == 200
    assert _tb(lan, can_xu_ly="true")["can_xu_ly"] == 0
    assert _tb(minh, can_xu_ly="true")["can_xu_ly"] == 1


def test_gap_tb_01_kenh_can_xac_thuc_va_phan_quyen(app_that):
    """Mất kết nối cần xác thực lại chỉ gửi tới người có quyền kenh.noi/kenh.sua và đóng khi active."""
    from agent.channels.base import ConnectionCheck
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_verification import NativeConnectionVerifier
    from agent.omnichannel.accounts import AccountStatus

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    nv_id, nv = _nhan_vien_moi(qt, "nv_thuong")
    _them_thanh_vien(app_that, tk, nv_id)

    # Tạo vai trò kỹ thuật kênh có kenh.doc + kenh.noi
    r_vt = qt.post("/api/vai-tro", json={
        "ten": "Kỹ thuật kênh", "mo_ta": "Quản lý kết nối",
        "quyen": ["kenh.doc", "kenh.noi", "hoi_thoai.doc"],
    })
    assert r_vt.status_code == 201, r_vt.text
    kt_id, kt = _nhan_vien_moi(qt, "ky_thuat", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{kt_id}/vai-tro", json={"vai_tro": [r_vt.json()["id"]]}).status_code == 200
    _them_thanh_vien(app_that, tk, kt_id)

    class AdapterLoi:
        async def verify_connection(self):
            return ConnectionCheck(False, "provider.token_expired", detail={"message": "Token hết hạn"})

    verifier = NativeConnectionVerifier(PostgresAccountRepository(), lambda acc: AdapterLoi())
    _chay(app_that, lambda: verifier.verify(UUID(tk), actor_id=UUID(kt_id)))
    # Gọi lần 2 -> không đẻ dòng trùng
    _chay(app_that, lambda: verifier.verify(UUID(tk), actor_id=UUID(kt_id)))

    assert _tb(nv)["thong_bao"] == [], "nhân viên thường không có kenh.noi/sua không được nhận cảnh báo kênh"
    d_kt = _tb(kt)
    assert len(d_kt["thong_bao"]) == 1
    assert d_kt["thong_bao"][0]["loai"] == "kenh_can_xac_thuc"
    assert d_kt["thong_bao"][0]["nhom"] == "can_xu_ly"
    assert d_kt["thong_bao"][0]["lien_ket"] == {"loai": "tai_khoan_kenh", "id": tk}

    # Xác minh lại thành công -> chuyển sang da_xu_ly
    class AdapterOk:
        async def verify_connection(self):
            return ConnectionCheck(True, "ok")

    verifier_ok = NativeConnectionVerifier(PostgresAccountRepository(), lambda acc: AdapterOk())
    _chay(app_that, lambda: verifier_ok.verify(UUID(tk), actor_id=UUID(kt_id)))
    assert _tb(kt)["can_xu_ly"] == 0
    assert _tb(kt)["thong_bao"][0]["nhom"] == "da_xu_ly"
    assert _mot(app_that, "SELECT status FROM channel_accounts WHERE id = $1::uuid", tk)["status"] == AccountStatus.ACTIVE.value


def test_gap_tb_03_giao_khach_don_le_va_hang_loat(app_that):
    """GAP-TB-04: giao khách thông báo 1 dòng thông tin (chống spam hàng loạt, bỏ qua tự giao)."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Khách A", "hi")
    _khach_nhan(app_that, tk, "Khách B", "hi")
    cids = [
        str(r["id"]) for r in _sql(
            app_that,
            lambda: __import__("agent").db.fetch(
                "SELECT DISTINCT contact_id AS id FROM conversations WHERE account_id = $1::uuid ORDER BY id", tk),
        )
    ]
    assert len(cids) == 2

    # Tự giao cho chính qt -> không phát thông báo
    qt_id = str(_mot(app_that, "SELECT nguoi_dung_id AS id FROM nguoi_dung_vai_tro LIMIT 1")["id"])
    r_tu = qt.put(f"/api/contacts/{cids[0]}/chu-so-huu", json={"owner_user_id": qt_id, "ly_do": "Tự nhận"})
    assert r_tu.status_code == 200, r_tu.text
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "duoc_giao_khach"] == []
    r_giao = qt.put(f"/api/contacts/{cids[0]}/chu-so-huu", json={"owner_user_id": lan_id, "ly_do": "Khách VIP"})
    assert r_giao.status_code == 200, r_giao.text
    d = _tb(lan)
    assert [x["loai"] for x in d["thong_bao"] if x["loai"] == "duoc_giao_khach"] == ["duoc_giao_khach"]
    t = [x for x in d["thong_bao"] if x["loai"] == "duoc_giao_khach"][0]
    assert t["nhom"] == "thong_tin" and t["can_xu_ly"] is False
    assert t["lien_ket"] == {"loai": "khach_hang", "id": cids[0]}

    # Hàng loạt 2 khách -> chỉ thêm 1 dòng tổng hợp
    _mot(app_that, "UPDATE thong_bao SET da_doc_luc = now() WHERE nguoi_nhan_id = $1::uuid RETURNING 1", lan_id)
    r_hl = qt.put("/api/contacts/chu-so-huu/hang-loat", json={
        "contact_ids": cids, "owner_user_id": lan_id, "ly_do": "Phân ca sáng",
    })
    assert r_hl.status_code == 200, r_hl.text
    moi = _tb(lan, chua_doc="true")["thong_bao"]
    assert len(moi) == 1
    assert moi[0]["loai"] == "duoc_giao_khach" and "2 khách hàng" in moi[0]["tieu_de"]


def test_gap_tb_04_tin_nhan_that_bai_outbox_dead(app_that, monkeypatch):
    """GAP-TB-03: outbox đạt ngưỡng dead-letter phát tin_nhan_that_bai đúng kênh và tự đóng khi gửi lại."""
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository
    from agent.omnichannel.outbox import OutboxStatus, PostgresOutboxRepository

    monkeypatch.setattr("agent.canh_gac._bao", lambda *a, **k: None)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Anh Đức", "check đơn")
    cid = _cid_moi_nhat(app_that, tk)

    q = _chay(
        app_that,
        lambda: OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=UUID(cid), role="staff", text="Dạ em gửi ạ",
            idempotency_key=f"staff:{uuid4()}", gui_boi=UUID(lan_id),
        ),
    )
    repo = PostgresOutboxRepository()
    # Đưa thẳng attempts = max_attempts - 1 để claim + mark_failed thành DEAD
    _mot(app_that, "UPDATE outbox_jobs SET attempts = max_attempts - 1 WHERE id = $1::uuid RETURNING 1", str(q.job_id))
    jobs = _chay(app_that, lambda: repo.claim(worker_id="w-test"))
    assert len(jobs) == 1 and jobs[0].status == OutboxStatus.PROCESSING
    _chay(app_that, repo.mark_failed, jobs[0], "502 Bad Gateway")

    d = _tb(lan)
    tb_chet = [x for x in d["thong_bao"] if x["loai"] == "tin_nhan_that_bai"]
    assert len(tb_chet) == 1
    assert tb_chet[0]["nhom"] == "can_xu_ly"
    assert tb_chet[0]["lien_ket"] == {"loai": "hoi_thoai", "id": cid}

    # Khi retry/cancel outbox_jobs -> thông báo chuyển da_xu_ly
    _mot(app_that, "UPDATE outbox_jobs SET status = 'pending' WHERE id = $1::uuid RETURNING 1", str(q.job_id))
    assert all(x["nhom"] == "da_xu_ly" for x in _tb(lan)["thong_bao"] if x["loai"] == "tin_nhan_that_bai")


def test_gap_tb_02_bo_cuoc_dong_bo_erp_tai_su_dung_can_duyet_don(app_that):
    """Đơn bỏ cuộc đồng bộ ERP quay về cho_duyet tái sử dụng bao_can_duyet_don."""
    from agent.erp.vong_dong_bo import PostgresKhoDon

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Thảo", "mua")
    cid = _cid_moi_nhat(app_that, tk)
    oid = str(uuid4())
    _mot(
        app_that,
        "INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai, conversation_id) "
        "VALUES ($1::uuid, 'DH-ERP-BC', 'webchat', 'Chị Thảo', '0909111222', 'HN', '[]', 250000, 'cho_dong_bo', $2::uuid) RETURNING id",
        oid, cid,
    )
    _chay(app_that, PostgresKhoDon().danh_dau_bo_cuoc, UUID(oid), "Hết lượt thử ERP")
    ds = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "can_duyet" and (x["lien_ket"] or {}).get("id") == oid]
    assert len(ds) == 1 and ds[0]["nhom"] == "can_xu_ly"


def test_bug_tb_02_bao_mat_doi_tuong_bi_xoa_hoac_mat_quyen(app_that, monkeypatch):
    """Rút quyền kênh / xóa mềm khách hàng -> mo_duoc=False, can_xu_ly=False, không lộ PII."""
    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Khách Bí Mật", "giúp em")

    # Lúc còn thuộc kênh -> thấy bình thường
    co = _tb(lan)
    assert co["thong_bao"][0]["mo_duoc"] is True
    assert co["thong_bao"][0]["ten_khach"] == "Khách Bí Mật"

    # Rút lan khỏi account_memberships của kênh
    _mot(app_that, "DELETE FROM account_memberships WHERE account_id = $1::uuid AND user_id = $2::uuid RETURNING 1", tk, lan_id)
    mat = _tb(lan)
    assert mat["can_xu_ly"] == 0
    assert mat["thong_bao"][0]["mo_duoc"] is False
    assert mat["thong_bao"][0]["ten_khach"] is None
    assert mat["thong_bao"][0]["kenh"] is None

    # Không xem/đánh dấu đã đọc thông báo của người khác
    tb_qt = _tb(qt)["thong_bao"][0]["id"]
    assert lan.post(f"/api/toi/thong-bao/{tb_qt}/da-doc").status_code == 404


def test_node_dieu_huong_chuong_don_hang_va_khong_quyen():
    """BUG-TB-02: JS điều hướng mở thẳng side panel đơn, khách, kênh và chặn khi mất quyền."""
    node = shutil.which("node")
    assert node, "Cần node"
    tb_js = (SRC / "19-thong-bao.js").read_text(encoding="utf-8")
    nk_js = (SRC / "27-nhat-ky.js").read_text(encoding="utf-8")
    script = (
        "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n"
        "function clock(){return '12:00';}\n"
        "function $(s){return null;}\nfunction $$(s){return [];}\n"
        "const calls = [];\n"
        "const state = {view:'hoithoai', openConv:null, openContact:null, mobileViewingChat:false, cuonToiChiTiet:false};\n"
        "function toast(m, err){calls.push(['toast', m, !!err]);}\n"
        "function doiMan(v){calls.push(['doiMan', v]); if(v==='forbidden') return false; state.view=v; return true;}\n"
        "async function dhTaiChiTiet(id, cuon){calls.push(['dhTaiChiTiet', id, cuon]);}\n"
        "function openCustomer(id){calls.push(['openCustomer', id]); state.openContact=id; state.view='khachhang';}\n"
        "const window = {moCongViec: async (id) => { calls.push(['moCongViec', id]); return true; }};\n"
        + tb_js.split('$("#chuongNut")?.addEventListener')[0]
        + "\n"
        + nk_js[nk_js.index("async function nkDiToi"):nk_js.index("/* Đối tượng bị tác động")]
        + """
        (async () => {
          await diToiLienKet({loai:'don_hang', id:'ord-1'}, {mo_duoc:true});
          await diToiLienKet({loai:'don_hang', id:'ord-2'}, {mo_duoc:false, ly_do_khong_mo:'Không còn quyền'});
          await diToiLienKet({loai:'khach_hang', id:'kh-1'}, {mo_duoc:true});
          await diToiLienKet({loai:'tai_khoan_kenh', id:'acc-1'}, {mo_duoc:true});
          await nkDiToi({loai:'don_hang', id:'ord-3'});
          console.log(JSON.stringify(calls));
        })();
        """
    )
    r = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
    calls = json.loads(r.stdout)
    assert ["doiMan", "donhang"] in calls
    assert ["dhTaiChiTiet", "ord-1", True] in calls
    assert ["toast", "Không còn quyền", True] in calls
    assert ["dhTaiChiTiet", "ord-2", True] not in calls
    assert ["openCustomer", "kh-1"] in calls
    assert ["doiMan", "cc-ket-noi"] in calls
    assert ["dhTaiChiTiet", "ord-3", True] in calls


def test_tep_giao_dien_phase3_khong_qua_1000_dong():
    for tep in ("19-thong-bao.js", "27-nhat-ky.js"):
        assert len((SRC / tep).read_text(encoding="utf-8").splitlines()) <= 1000


def test_sec_tb_01_va_bug_tb_09_che_toan_bo_du_lieu_va_so_dem_khi_mat_quyen(app_that, monkeypatch):
    """SEC-TB-01 + BUG-TB-09: che mọi metadata/UUID ngoài phạm vi và đồng bộ dem_chua_doc."""
    from agent.core import thong_bao_noi_bo as tb
    from agent.core import uy_quyen
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_verification import NativeConnectionVerifier
    from agent.channels.base import ConnectionCheck
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository
    from agent.omnichannel.outbox import OutboxStatus, PostgresOutboxRepository

    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)

    # Tạo vai trò cho phép xem kênh/đơn/khách/hội thoại/việc theo phạm vi
    r_vt = qt.post("/api/vai-tro", json={
        "ten": "CSKH Phạm Vi", "mo_ta": "Kiểm tra che dữ liệu",
        "quyen": ["hoi_thoai.doc", "hoi_thoai.tra_loi", "ai.duyet", "don.doc",
                  "don.sua", "khach.doc", "cong_viec.doc", "kenh.doc", "kenh.noi"],
    })
    assert r_vt.status_code == 201, r_vt.text
    vt_id = r_vt.json()["id"]
    lan_id, lan = _nhan_vien_moi(qt, "lan_sec", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{lan_id}/vai-tro", json={"vai_tro": [vt_id]}).status_code == 200
    _them_thanh_vien(app_that, tk, lan_id)

    _khach_nhan(app_that, tk, "Chị Hoa Bí Mật", "cần tư vấn đơn")
    cid = _cid_moi_nhat(app_that, tk)

    # Tạo thêm: đơn hàng chờ duyệt, đề xuất AI, outbox dead, công việc gắn hội thoại, kênh lỗi
    oid = str(uuid4())
    _mot(
        app_that,
        "INSERT INTO orders (id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi, items, tong_tien, trang_thai, conversation_id) "
        "VALUES ($1::uuid, 'DH-BI-MAT-99', 'webchat', 'Chị Hoa Bí Mật', '0909888777', 'HN', '[]', 990000, 'cho_duyet', $2::uuid) RETURNING id",
        oid, cid,
    )
    _chay(app_that, lambda: tb.bao_can_duyet_don(oid, conversation_id=cid, ma_don="DH-BI-MAT-99"))

    quyet = uy_quyen.QuyetDinh(hanh_dong="tao_don", che_do="tu_dong", muc="co_phe_duyet")
    _chay(app_that, lambda: uy_quyen.tao_de_xuat(
        conversation_id=cid, quyet=quyet, ly_do_can_duyet="Đề xuất bí mật",
        tham_so={}, de_xuat={"tieu_de": "Đề xuất khách VIP"}, can_cu={}, khoa_trung=f"sec:{uuid4()}",
    ))

    q = _chay(app_that, lambda: OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=UUID(cid), role="staff", text="Nội dung nhạy cảm",
        idempotency_key=f"sec-ob:{uuid4()}", gui_boi=UUID(lan_id),
    ))
    _mot(app_that, "UPDATE outbox_jobs SET attempts = max_attempts - 1 WHERE id = $1::uuid RETURNING 1", str(q.job_id))
    ob_repo = PostgresOutboxRepository()
    jobs = _chay(app_that, lambda: ob_repo.claim(worker_id="w-sec"))
    assert len(jobs) == 1 and jobs[0].status == OutboxStatus.PROCESSING
    _chay(app_that, ob_repo.mark_failed, jobs[0], "Token hết hạn XYZ")

    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])
    r_cv = qt.post("/api/cong-viec", json={
        "tieu_de": "Việc bí mật của kênh", "conversation_id": cid,
    })
    assert r_cv.status_code == 201, r_cv.text
    vid = r_cv.json()["id"]
    _chay(app_that, lambda: tb.bao_duoc_giao_viec(vid, lan_id, boi=qt_id, tieu_de_viec="Việc bí mật của kênh"))

    class AdapterLoi:
        async def verify_connection(self):
            return ConnectionCheck(False, "provider.token_expired", detail={"message": "Secret token die"})

    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterLoi()).verify(UUID(tk), actor_id=UUID(lan_id)))

    truoc = _tb(lan, gioi_han=20)
    assert truoc["chua_doc"] >= 5
    assert truoc["chua_doc"] == lan.get("/api/toi/thong-bao/so-chua-doc").json()["chua_doc"]
    assert all(x["mo_duoc"] is True for x in truoc["thong_bao"])

    # Rút lan khỏi kênh và rút quyền khỏi vai trò
    _mot(app_that, "DELETE FROM account_memberships WHERE account_id = $1::uuid AND user_id = $2::uuid RETURNING 1", tk, lan_id)
    _mot(app_that, "UPDATE cong_viec SET nguoi_nhan = NULL WHERE id = $1::uuid RETURNING 1", vid)
    _mot(app_that, "DELETE FROM vai_tro_quyen WHERE vai_tro_id = $1::uuid RETURNING 1", vt_id)

    sau = _tb(lan, gioi_han=20)
    assert sau["chua_doc"] == 0, "BUG-TB-09: ngoài phạm vi không được cộng vào badge chưa đọc"
    assert sau["can_xu_ly"] == 0
    assert lan.get("/api/toi/thong-bao/so-chua-doc").json()["chua_doc"] == 0

    # Không tự mutate da_doc_luc trong DB
    raw_unread = _mot(app_that, "SELECT count(*) AS n FROM thong_bao WHERE nguoi_nhan_id = $1::uuid AND da_doc_luc IS NULL", lan_id)["n"]
    assert int(raw_unread) >= 5

    # Toàn bộ các loại đều bị che thông tin và không lộ UUID trong lien_ket
    assert len(sau["thong_bao"]) >= 5
    for item in sau["thong_bao"]:
        assert item["mo_duoc"] is False
        assert item["can_xu_ly"] is False
        assert item["lien_ket"] is None, f"{item['loai']} không được trả UUID trong lien_ket khi mo_duoc=False"
        assert item["ten_khach"] is None
        assert item["kenh"] is None
        assert item["huong_dan"] == ""
        assert item["ket_qua_nghiep_vu"] is None
        assert item["nhan_trang_thai"] is None
        assert "Bí Mật" not in item["tieu_de"] and "DH-BI-MAT-99" not in item["tieu_de"]
        assert "Secret token" not in item["noi_dung"] and "Token hết hạn" not in item["noi_dung"]
        assert "Việc bí mật" not in item["tieu_de"]


def test_bug_tb_03_chu_ky_gui_lai_va_huy_outbox(app_that, monkeypatch):
    """BUG-TB-03: retry/cancel đóng thông báo cũ trong transaction; lỗi lần sau sinh dòng mới."""
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository
    from agent.omnichannel.outbox import OutboxStatus, PostgresOutboxRepository

    _ghi_bao(monkeypatch)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Oanh", "check đơn")
    cid = _cid_moi_nhat(app_that, tk)

    q = _chay(app_that, lambda: OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=UUID(cid), role="staff", text="Chờ chút nhé",
        idempotency_key=f"ob3:{uuid4()}",
    ))
    jid = str(q.job_id)
    ob_repo = PostgresOutboxRepository()
    _mot(app_that, "UPDATE outbox_jobs SET attempts = max_attempts - 1 WHERE id = $1::uuid RETURNING 1", jid)
    jobs = _chay(app_that, lambda: ob_repo.claim(worker_id="w-tb3"))
    assert len(jobs) == 1 and jobs[0].status == OutboxStatus.PROCESSING
    _chay(app_that, ob_repo.mark_failed, jobs[0], "Mạng 502")

    # Retry sai ID (404) hoặc job không ở trạng thái được phép không được đóng thông báo đang mở
    assert qt.post(f"/api/outbox/jobs/{uuid4()}/retry").status_code == 404
    _mot(app_that, "UPDATE outbox_jobs SET status = 'processing' WHERE id = $1::uuid RETURNING 1", jid)
    assert qt.post(f"/api/outbox/jobs/{jid}/retry").status_code == 409
    _mot(app_that, "UPDATE outbox_jobs SET status = 'dead' WHERE id = $1::uuid RETURNING 1", jid)
    assert len([x for x in _tb(qt)["thong_bao"] if x["loai"] == "tin_nhan_that_bai" and x["nhom"] == "can_xu_ly"]) == 1

    # Retry thành công -> đóng chu kỳ thông báo cũ
    r_retry = qt.post(f"/api/outbox/jobs/{jid}/retry")
    assert r_retry.status_code == 200, r_retry.text
    dong_cu = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "tin_nhan_that_bai"]
    assert len(dong_cu) == 1 and dong_cu[0]["nhom"] == "da_xu_ly"
    old_tb_id = dong_cu[0]["id"]

    # Lượt retry chết lần hai -> dòng cũ PHẢI giữ da_xu_ly, sinh dòng mới Cần xử lý
    _mot(app_that, "UPDATE outbox_jobs SET attempts = max_attempts - 1 WHERE id = $1::uuid RETURNING 1", jid)
    jobs2 = _chay(app_that, lambda: ob_repo.claim(worker_id="w-tb3-2"))
    assert len(jobs2) == 1
    _chay(app_that, ob_repo.mark_failed, jobs2[0], "Lỗi lần 2")

    sau_lan2 = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "tin_nhan_that_bai"]
    assert len(sau_lan2) == 2
    by_id = {x["id"]: x for x in sau_lan2}
    assert by_id[old_tb_id]["nhom"] == "da_xu_ly", "thông báo chu kỳ cũ không được tự bật lại Cần xử lý"
    moi = [x for x in sau_lan2 if x["id"] != old_tb_id][0]
    assert moi["nhom"] == "can_xu_ly"

    # Cancel -> đóng chu kỳ thứ 2 với nhãn Đã hủy gửi
    assert qt.post(f"/api/outbox/jobs/{jid}/cancel").status_code == 200
    sau_huy = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "tin_nhan_that_bai"]
    assert all(x["nhom"] == "da_xu_ly" for x in sau_huy)
    assert any(x["nhan_trang_thai"] == "Đã hủy gửi" for x in sau_huy)


def test_bug_tb_04_enable_khong_gia_xac_thuc_va_oauth_khoi_phuc_tai_phat(app_that, monkeypatch):
    """BUG-TB-04: enable không đóng lỗi auth; verify/OAuth Meta/Zalo OA đóng chu kỳ và tái phát tạo chu kỳ mới."""
    from agent.channels.base import ConnectionCheck
    from agent.core import thong_bao_noi_bo as tb
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_verification import NativeConnectionVerifier
    from agent.omnichannel.accounts import AccountStatus
    from agent.api import oauth_meta, oauth_zalo_oa

    async def _bo_qua_han_muc(*a, **k):
        return None

    monkeypatch.setattr("agent.goi_cuoc.kiem_them_kenh", _bo_qua_han_muc)
    qt = _quan_tri_vao(app_that)

    # 1) enable_account không được xóa trạng thái reauth_required hay đóng thông báo
    tk = _kenh_webchat(qt)

    class AdapterLoi:
        async def verify_connection(self):
            return ConnectionCheck(False, "provider.unauthorized", detail={"message": "Token die"})

    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterLoi()).verify(UUID(tk), actor_id=uuid4()))
    assert _mot(app_that, "SELECT status FROM channel_accounts WHERE id = $1::uuid", tk)["status"] == AccountStatus.REAUTH_REQUIRED.value
    assert len([x for x in _tb(qt, can_xu_ly="true")["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]) == 1

    r_en = qt.post(f"/api/channel-accounts/{tk}/enable")
    assert r_en.status_code == 200
    assert r_en.json()["status"] == "reauth_required"
    assert len([x for x in _tb(qt, can_xu_ly="true")["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]) == 1

    # Kể cả disable rồi enable lại khi health cuối là reauth_required -> vẫn không tự active
    assert qt.post(f"/api/channel-accounts/{tk}/disable").status_code == 200
    r_en2 = qt.post(f"/api/channel-accounts/{tk}/enable")
    assert r_en2.status_code == 200
    assert r_en2.json()["status"] == "reauth_required"
    assert len([x for x in _tb(qt, can_xu_ly="true")["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]) == 1

    # 2) Verify OK -> đóng chu kỳ; sau đó tái phát -> tạo chu kỳ mới, chu kỳ cũ giữ nguyên
    class AdapterOk:
        async def verify_connection(self):
            return ConnectionCheck(True, "ok")

    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterOk()).verify(UUID(tk), actor_id=uuid4()))
    ds1 = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]
    assert len(ds1) == 1 and ds1[0]["nhom"] == "da_xu_ly"

    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterLoi()).verify(UUID(tk), actor_id=uuid4()))
    ds2 = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]
    assert len(ds2) == 2
    assert [x["nhom"] for x in ds2] == ["can_xu_ly", "da_xu_ly"]

    # 3) OAuth Meta reconnect
    import base64

    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])
    master_k = "1:" + base64.b64encode(b"\x01" * 32).decode()
    monkeypatch.setattr(oauth_meta.settings, "meta_app_id", "app-1")
    monkeypatch.setattr(oauth_meta.settings, "meta_app_secret", "sec-1")
    monkeypatch.setattr(oauth_meta.settings, "credential_master_keys", master_k)
    monkeypatch.setattr(oauth_meta.settings, "credential_active_key_version", 1)

    async def _dang_ky_ok(**kw):
        return True, ""

    monkeypatch.setattr("agent.channels.dang_ky_webhook_meta.dang_ky_webhook_trang", _dang_ky_ok)
    r_fb = qt.post("/api/channel-accounts", json={
        "channel": "facebook", "display_name": "Page Test", "external_account_id": "pg-999",
        "capabilities": {"send_text": True}, "metadata": {}, "credentials": {"access_token": "old", "app_secret": "s"},
    })
    assert r_fb.status_code == 201, r_fb.text
    fb = r_fb.json()
    _mot(app_that, "UPDATE channel_accounts SET status = 'reauth_required' WHERE id = $1::uuid RETURNING 1", fb["id"])
    _chay(app_that, lambda: tb.bao_kenh_can_xac_thuc(fb["id"], ten_tai_khoan="Page Test", kenh="facebook"))
    _chay(app_that, lambda: oauth_meta._tao_tai_khoan_tu_danh_sach(
        [{"id": "pg-999", "name": "Page Test", "access_token": "new-tok"}], qt_id,
    ))
    assert _mot(app_that, "SELECT status FROM channel_accounts WHERE id = $1::uuid", fb["id"])["status"] == "active"
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc" and (x["lien_ket"] or {}).get("id") == fb["id"]][0]["nhom"] == "da_xu_ly"

    # 4) OAuth Zalo OA reconnect
    monkeypatch.setattr(oauth_zalo_oa.settings, "zalo_oa_app_id", "oa-app")
    monkeypatch.setattr(oauth_zalo_oa.settings, "zalo_oa_secret_key", "oa-sec")
    r_oa = qt.post("/api/channel-accounts", json={
        "channel": "zalo_oa", "display_name": "OA Test", "external_account_id": "oa-999",
        "capabilities": {"send_text": True}, "metadata": {}, "credentials": {"app_id": "a", "secret_key": "s", "refresh_token": "old"},
    })
    assert r_oa.status_code == 201, r_oa.text
    oa = r_oa.json()
    _mot(app_that, "UPDATE channel_accounts SET status = 'reauth_required' WHERE id = $1::uuid RETURNING 1", oa["id"])
    _chay(app_that, lambda: tb.bao_kenh_can_xac_thuc(oa["id"], ten_tai_khoan="OA Test", kenh="zalo_oa"))
    _chay(app_that, lambda: oauth_zalo_oa._luu_tai_khoan(oa_id="oa-999", ten="OA Test", refresh_token="new-rt", nguoi_bam=qt_id))
    assert _mot(app_that, "SELECT status FROM channel_accounts WHERE id = $1::uuid", oa["id"])["status"] == "active"
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc" and (x["lien_ket"] or {}).get("id") == oa["id"]][0]["nhom"] == "da_xu_ly"


def test_bug_tb_05_doi_phu_trach_viec_hoi_thoai_va_khach_hang(app_that):
    """BUG-TB-05: đổi người phụ trách việc quá hạn, hội thoại SLA/duyệt/outbox và khách hàng loạt."""
    from agent.core import giao_viec, thong_bao_noi_bo as tb, uy_quyen

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    quyen_nv = [
        "hoi_thoai.doc", "hoi_thoai.tra_loi", "hoi_thoai.nhan", "ai.duyet",
        "khach.doc", "khach.sua", "don.doc", "kenh.doc", "cong_viec.doc", "cong_viec.sua",
    ]
    r_vt = qt.post("/api/vai-tro", json={"ten": "NV Tuyến Đầu", "quyen": quyen_nv})
    assert r_vt.status_code == 201, r_vt.text
    vt_nv = r_vt.json()["id"]
    lan_id, lan = _nhan_vien_moi(qt, "lan5", vai_tro=None)
    minh_id, minh = _nhan_vien_moi(qt, "minh5", vai_tro=None)
    for uid in (lan_id, minh_id):
        assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [vt_nv]}).status_code == 200
        _them_thanh_vien(app_that, tk, uid)

    # A) Công việc quá hạn đổi chủ từ lan -> minh
    vid = qt.post("/api/cong-viec", json={
        "tieu_de": "Gọi lại đơn gấp", "nguoi_nhan": lan_id,
        "han": "2026-01-01T00:00:00Z",
    }).json()["id"]
    assert _chay(app_that, giao_viec.quet_viec_qua_han) == 1
    assert any(x["loai"] == "viec_qua_han" and x["nhom"] == "can_xu_ly" for x in _tb(lan)["thong_bao"])

    assert qt.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": minh_id}).status_code == 200
    assert not any(x["can_xu_ly"] for x in _tb(lan)["thong_bao"] if (x["lien_ket"] or {}).get("id") == vid)
    minh_v = [x for x in _tb(minh)["thong_bao"] if (x["lien_ket"] or {}).get("id") == vid]
    assert any(x["loai"] == "duoc_giao_viec" and x["nhom"] == "can_xu_ly" for x in minh_v)
    assert any(x["loai"] == "viec_qua_han" and x["nhom"] == "can_xu_ly" for x in minh_v)

    # B) Hội thoại chưa gán -> lan & minh & qt đều nhận SLA + đề xuất; gán cho minh -> lan hết Cần xử lý, qt giữ SLA
    _khach_nhan(app_that, tk, "Khách Phân Công", "hỏi ship")
    cid = _cid_moi_nhat(app_that, tk)

    async def ban_sla():
        from agent import db
        async with db.pool().acquire() as conn:
            await conn.execute(
                "INSERT INTO sla_events (conversation_id, chu_ky, kind) VALUES ($1::uuid, 1, 'first_response_breached')",
                cid,
            )
            await tb.bao_sla(conn, [(UUID(cid), "first_response_breached")])

    _chay(app_that, ban_sla)
    _chay(app_that, lambda: uy_quyen.tao_de_xuat(
        conversation_id=cid,
        quyet=uy_quyen.QuyetDinh(hanh_dong="tao_don", che_do="tu_dong", muc="co_phe_duyet"),
        ly_do_can_duyet="Cần duyệt tạo đơn", tham_so={}, de_xuat={"tieu_de": "Tạo đơn"}, can_cu={}, khoa_trung=f"b5:{uuid4()}",
    ))
    assert len([x for x in _tb(lan, can_xu_ly="true")["thong_bao"] if (x["lien_ket"] or {}).get("id") == cid]) >= 2

    ver = _mot(app_that, "SELECT version FROM conversations WHERE id = $1::uuid", cid)["version"]
    assert qt.post(f"/api/inbox/conversations/{cid}/takeover", json={
        "expected_version": ver, "reason": "Chuyển Minh phụ trách", "assignee_id": minh_id,
    }).status_code == 200

    assert [x for x in _tb(lan, can_xu_ly="true")["thong_bao"] if (x["lien_ket"] or {}).get("id") == cid] == []
    assert any(x["loai"] == "sla_tre" and x["nhom"] == "can_xu_ly" for x in _tb(qt)["thong_bao"] if (x["lien_ket"] or {}).get("id") == cid)
    assert any(x["loai"] == "sla_tre" and x["nhom"] == "can_xu_ly" for x in _tb(minh)["thong_bao"] if (x["lien_ket"] or {}).get("id") == cid)

    # C) Giao khách hàng loạt -> thu hồi/chuyển hết sang Minh thì Lan mất mo_duoc & badge chưa đọc giảm
    c1, c2 = str(uuid4()), str(uuid4())
    for cid_k, ext in ((c1, "k1"), (c2, "k2")):
        _mot(app_that, "INSERT INTO contacts (id, display_name, status) VALUES ($1::uuid, $2, 'active') RETURNING id", cid_k, f"Khách {ext}")
        _mot(app_that, "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id) VALUES ($1::uuid, $2::uuid, $3) RETURNING id", cid_k, tk, f"u-{ext}")

    assert qt.put("/api/contacts/chu-so-huu/hang-loat", json={"contact_ids": [c1, c2], "owner_user_id": lan_id, "ly_do": "Giao ca sáng"}).status_code == 200
    b_lan = [x for x in _tb(lan)["thong_bao"] if x["loai"] == "duoc_giao_khach"]
    assert len(b_lan) == 1 and b_lan[0]["mo_duoc"] is True

    assert qt.put("/api/contacts/chu-so-huu/hang-loat", json={"contact_ids": [c1, c2], "owner_user_id": minh_id, "ly_do": "Chuyển Minh"}).status_code == 200
    b_lan_sau = [x for x in _tb(lan)["thong_bao"] if x["loai"] == "duoc_giao_khach"]
    assert b_lan_sau[0]["mo_duoc"] is False
    assert b_lan_sau[0]["lien_ket"] is None


def test_bug_tb_06_sla_lich_su_truoc_0071_khong_bat_lai(app_that):
    """BUG-TB-06: SLA pre-0071 (chu_ky_nghiep_vu=NULL) không bật lại Cần xử lý khi mở chu kỳ mới."""
    from agent.core import thong_bao_noi_bo as tb

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chú Hùng", "khiếu nại")
    cid = _cid_moi_nhat(app_that, tk)
    qt_id = str(_mot(app_that, "SELECT id FROM nguoi_dung WHERE ten_dang_nhap = 'sep'")["id"])

    # Chèn dữ liệu SLA chu kỳ 1 kiểu cũ trước migration 0071 (`chu_ky_nghiep_vu IS NULL`)
    _mot(app_that, "INSERT INTO sla_events (conversation_id, chu_ky, kind, created_at) VALUES ($1::uuid, 1, 'first_response_breached', now() - interval '20 minute') RETURNING id", cid)
    _mot(app_that,
         "INSERT INTO sla_chuyen_giao (conversation_id, chu_ky, lan, bat_dau, vi_pham_luc, ket_thuc_luc, ket_thuc_ly_do, ket_qua) "
         "VALUES ($1::uuid, 1, 1, now() - interval '20 minute', now() - interval '15 minute', now() - interval '10 minute', 'giai_quyet', 'tre') RETURNING id",
         cid)
    _mot(app_that,
         "INSERT INTO thong_bao (nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, khoa_chong_trung, chu_ky_nghiep_vu, tao_luc) "
         "VALUES ($1::uuid, 'sla_tre', 'SLA cũ phản hồi', '', $2::uuid, $3, NULL, now() - interval '15 minute') RETURNING id",
         qt_id, cid, f"sla:first_response_breached:{cid}")
    _mot(app_that,
         "INSERT INTO thong_bao (nguoi_nhan_id, loai, tieu_de, noi_dung, conversation_id, khoa_chong_trung, chu_ky_nghiep_vu, tao_luc) "
         "VALUES ($1::uuid, 'sla_tre', 'SLA cũ bàn giao', '', $2::uuid, $3, NULL, now() - interval '14 minute') RETURNING id",
         qt_id, cid, f"sla:handover_response_breached:{cid}")

    # Mở lại hội thoại vào chu kỳ 2 + lượt bàn giao 2
    _mot(app_that, "UPDATE conversations SET sla_chu_ky = 2, state = 'open', mode = 'human', first_responded_at = NULL, resolved_at = NULL WHERE id = $1::uuid RETURNING 1", cid)
    _mot(app_that, "INSERT INTO sla_events (conversation_id, chu_ky, kind, created_at) VALUES ($1::uuid, 2, 'started', now() - interval '5 minute') RETURNING id", cid)
    _mot(app_that, "INSERT INTO sla_events (conversation_id, chu_ky, kind, created_at) VALUES ($1::uuid, 2, 'first_response_breached', now() - interval '2 minute') RETURNING id", cid)
    _mot(app_that,
         "INSERT INTO sla_chuyen_giao (conversation_id, chu_ky, lan, bat_dau, vi_pham_luc, ket_qua) "
         "VALUES ($1::uuid, 2, 2, now() - interval '5 minute', now() - interval '1 minute', 'dang_cho') RETURNING id",
         cid)

    sla_cu = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "sla_tre"]
    assert len(sla_cu) == 2
    assert all(x["nhom"] == "da_xu_ly" for x in sla_cu), "SLA chu kỳ 1 trước 0071 không được sống lại ở chu kỳ 2"

    # Ghi nhận đúng chu kỳ 2 hậu 0071 -> chu kỳ 2 mới là Cần xử lý
    async def ghi_ck2():
        from agent import db
        async with db.pool().acquire() as conn:
            await tb.bao_sla(conn, [(UUID(cid), "first_response_breached")])

    _chay(app_that, ghi_ck2)
    sla_all = [x for x in _tb(qt)["thong_bao"] if x["loai"] == "sla_tre"]
    assert [x["nhom"] for x in sla_all] == ["can_xu_ly", "da_xu_ly", "da_xu_ly"]

    # Dữ liệu cũ không bị viết lại
    row_cu = _mot(app_that, "SELECT chu_ky_nghiep_vu, da_xu_ly_luc FROM thong_bao WHERE khoa_chong_trung = $1", f"sla:first_response_breached:{cid}")
    assert row_cu["chu_ky_nghiep_vu"] is None and row_cu["da_xu_ly_luc"] is None


def test_bug_tb_07_ngu_nghia_trang_thai_de_xuat_ai(app_that):
    """BUG-TB-07: không gán 'Đã xử lý' cho đề xuất hết hạn, từ chối, lỗi hoặc chờ xử lý thủ công."""
    from agent.core import thong_bao_noi_bo as tb, uy_quyen

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Mai", "đổi hàng")
    cid = _cid_moi_nhat(app_that, tk)

    quyet = uy_quyen.QuyetDinh(hanh_dong="tao_don", che_do="tu_dong", muc="co_phe_duyet")
    cac_ca = [
        ("het_han", "Đã hết hạn"),
        ("tu_choi", "Đã từ chối"),
        ("loi", "Thực thi lỗi"),
        ("cho_xu_ly_thu_cong", "Chờ xử lý thủ công"),
        ("da_thuc_hien", "Đã xử lý"),
    ]
    ids: dict[str, str] = {}
    for tt, _ in cac_ca:
        dx_id, _ = _chay(app_that, lambda tt=tt: uy_quyen.tao_de_xuat(
            conversation_id=cid, quyet=quyet, ly_do_can_duyet=f"Thử {tt}",
            tham_so={}, de_xuat={"tieu_de": f"Đề xuất {tt}"}, can_cu={}, khoa_trung=f"dx:{tt}:{uuid4()}",
        ))
        ids[tt] = str(dx_id)
        _mot(app_that, "UPDATE ai_de_xuat SET trang_thai = $2 WHERE id = $1::uuid RETURNING 1", str(dx_id), tt)
        _chay(app_that, lambda d=dx_id: tb.ket_thuc_duyet_de_xuat(None, d))

    ds = {
        next(k for k, v in ids.items() if k in x["tieu_de"]): x
        for x in _tb(qt, gioi_han=20)["thong_bao"]
        if x["loai"] == "can_duyet"
    }
    for tt, nhan in cac_ca:
        assert ds[tt]["nhom"] == "da_xu_ly"
        assert ds[tt]["ket_qua_nghiep_vu"] == tt
        assert ds[tt]["nhan_trang_thai"] == nhan

    # Kiểm tra render JS bằng node
    node = shutil.which("node")
    assert node
    tb_js = (SRC / "19-thong-bao.js").read_text(encoding="utf-8")
    script = (
        "function esc(s){return String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));}\n"
        "function clock(){return '12:00';}\nfunction $(s){return null;}\nfunction $$(s){return [];}\n"
        + tb_js.split('$("#chuongNut")?.addEventListener')[0]
        + "\nconsole.log(JSON.stringify("
        + json.dumps([ds[tt] for tt, _ in cac_ca])
        + ".map(dongThongBao)));"
    )
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, check=True).stdout
    htmls = json.loads(out)
    for (_, nhan), h in zip(cac_ca, htmls, strict=True):
        assert nhan in h
        if nhan != "Đã xử lý":
            assert "Đã xử lý" not in h


def test_bug_tb_08_meta_token_khong_trung_cong_viec_va_kenh_can_xac_thuc(app_that, monkeypatch):
    """BUG-TB-08: đã có công việc token Meta đang mở thì không phát trùng kenh_can_xac_thuc."""
    import base64
    from agent.channels.base import ConnectionCheck
    from agent.config import settings
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.account_verification import NativeConnectionVerifier

    monkeypatch.setattr(settings, "credential_master_keys", "1:" + base64.b64encode(b"\x01" * 32).decode())
    monkeypatch.setattr(settings, "credential_active_key_version", 1)
    qt = _quan_tri_vao(app_that)
    r_fb = qt.post("/api/channel-accounts", json={
        "channel": "facebook", "display_name": "Fanpage Chính", "external_account_id": f"pg-{uuid4().hex[:8]}",
        "capabilities": {"send_text": True}, "metadata": {}, "credentials": {"access_token": "tok"},
    })
    assert r_fb.status_code == 201, r_fb.text
    fb = r_fb.json()
    aid = fb["id"]
    vid = _mot(app_that,
               "INSERT INTO cong_viec (tieu_de, uu_tien, trang_thai, khoa_chong_trung) "
               "VALUES ('Token Facebook sắp hết hạn', 'gap', 'moi', $1) RETURNING id",
               f"kenh:token_meta:{aid}:2026-12-01")["id"]

    class AdapterHetHan:
        async def verify_connection(self):
            return ConnectionCheck(False, "provider.token_expired", detail={"message": "Expired"})

    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterHetHan()).verify(UUID(aid), actor_id=uuid4()))
    assert [x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"] == []

    # Khi việc Meta token đã đóng -> verify thất bại mới phát cảnh báo kênh
    _mot(app_that, "UPDATE cong_viec SET trang_thai = 'xong', xong_luc = now() WHERE id = $1::uuid RETURNING 1", str(vid))
    _chay(app_that, lambda: NativeConnectionVerifier(PostgresAccountRepository(), lambda _a: AdapterHetHan()).verify(UUID(aid), actor_id=uuid4()))
    assert len([x for x in _tb(qt)["thong_bao"] if x["loai"] == "kenh_can_xac_thuc"]) == 1


def test_tech_debt_kh_01_giao_hang_loat_mot_khach(app_that):
    """TECH-DEBT-KH-01: giao hàng loạt với đúng 1 khách vẫn lấy được tên khách và tạo thông báo."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Khach Don Le", "xin chao")
    cid_row = _mot(app_that, "SELECT id FROM contacts ORDER BY created_at DESC LIMIT 1")
    assert cid_row is not None

    r = qt.put(
        "/api/contacts/chu-so-huu/hang-loat",
        json={"contact_ids": [str(cid_row["id"])], "owner_user_id": lan_id, "ly_do": "Giao đơn lẻ"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["so_khach"] == 1
    tb = _tb(lan)
    assert any(
        x["loai"] == "duoc_giao_khach" and "Khach Don Le" in (x.get("tieu_de") or "")
        for x in tb["thong_bao"]
    )

