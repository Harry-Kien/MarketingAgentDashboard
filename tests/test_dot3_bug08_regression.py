"""
Bộ kiểm thử hồi quy ĐỢT 3 — BUG-08-01 (ghi nhận kết nối lại tài khoản Zalo
cá nhân) & BUG-08-02 (nhãn tiếng Việt, chuẩn hoá status/trang_thai, tên tài
khoản từ channel_accounts và hiển thị kiểm toán).

Sử dụng CSDL kiểm thử `kiemthu` (`app_that` / `csdl_kiem_thu`) và callback HMAC
giả lập — không kết nối Zalo thật, không chạm `marketing_agent`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent import db  # noqa: E402
from agent.api import zalo_personal_webhook as w  # noqa: E402
from agent.config import ROOT as AGENT_ROOT  # noqa: E402
from agent.core import nhat_ky_kiem_toan as nk  # noqa: E402
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount  # noqa: E402
from tests.test_nghiem_thu_saas import (  # noqa: E402
    _nhan_vien_moi, _quan_tri_vao, _sql,
)


def _sign_headers(secret: str, path: str, body: bytes, *, nonce: str | None = None) -> dict[str, str]:
    ts = str(int(time.time()))
    nc = nonce or uuid4().hex
    canonical = b".".join([ts.encode(), nc.encode(), b"POST", path.encode(), body])
    sig = "sha256=" + hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()
    return {
        "x-sidecar-timestamp": ts,
        "x-sidecar-nonce": nc,
        "x-sidecar-signature": sig,
        "content-type": "application/json",
    }


@pytest.fixture
def zalo_webhook_san(monkeypatch):
    """Dựng callback FastAPI có kiểm HMAC thật + lưu sự kiện/sức khoẻ vào bộ nhớ."""
    secret = "zalo-sidecar-secret-test-" + "9" * 16
    tk = ChannelAccount(
        id=uuid4(),
        channel=Channel.ZALO_PERSONAL,
        display_name="Zalo CSKH Chính",
        external_account_id="own-zalo-001",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )
    state: dict = {
        "account": tk,
        "events": [],
        "health": [],
        "rotations": [],
        "secret": secret,
    }

    class _Repo:
        async def get(self, aid):
            return state["account"] if aid == state["account"].id else None

        async def bind_external_identity(self, aid, ext_id, *, actor_id):
            acc = state["account"]
            if acc.external_account_id != ext_id and not acc.external_account_id.startswith("pending:"):
                raise RuntimeError("identity mismatch")
            state["account"] = ChannelAccount(
                id=acc.id, channel=acc.channel, display_name=acc.display_name,
                external_account_id=ext_id, status=acc.status,
                capabilities=acc.capabilities, metadata=acc.metadata,
                is_legacy=acc.is_legacy,
            )
            state["events"].append({
                "kind": "channel_account.identity_bound",
                "actor": str(actor_id),
                "ref_id": aid,
                "detail": {"external_account_id": ext_id},
            })

        async def record_health(self, aid, *, status, code, detail=None):
            state["health"].append({"account_id": aid, "status": status.value, "code": code, "detail": dict(detail or {})})

        async def update_status(self, aid, status, *, actor_id):
            acc = state["account"]
            state["account"] = ChannelAccount(
                id=acc.id, channel=acc.channel, display_name=acc.display_name,
                external_account_id=acc.external_account_id, status=status,
                capabilities=acc.capabilities, metadata=acc.metadata,
                is_legacy=acc.is_legacy,
            )
            state["events"].append({
                "kind": "channel_account.status_changed",
                "actor": str(actor_id),
                "ref_id": aid,
                "detail": {"status": status.value},
            })
            return state["account"]

    class _Loader:
        async def load(self, _aid):
            return {"sidecar_secret": secret, "sidecar_url": "http://127.0.0.1:3210"}

        async def store_rotated(self, aid, creds):
            state["rotations"].append({"account_id": aid, "keys": sorted(creds.keys())})
            state["events"].append({
                "kind": "channel_account.credentials_rotated",
                "actor": "00000000-0000-0000-0000-000000000000",
                "ref_id": aid,
                "detail": {},
            })

    async def log_event(kind, *, actor="system", ref_id=None, **detail):
        state["events"].append({"kind": kind, "actor": actor, "ref_id": ref_id, "detail": dict(detail)})

    async def fetchrow(sql, *args):
        # Giả lập tra cứu chống trùng event_id trong bảng events
        if "channel_account.reconnected" in sql and len(args) >= 2:
            aid, eid = args[0], args[1]
            for ev in state["events"]:
                if (
                    ev["kind"] == "channel_account.reconnected"
                    and ev["ref_id"] == aid
                    and ev["detail"].get("event_id") == eid
                ):
                    return {"1": 1}
        return None

    w._SEEN_NONCES.clear()
    w._DA_GHI_KET_NOI_LAI.clear()
    w._PHIEN_MOI_LAM_MOI.clear()

    monkeypatch.setattr(w, "PostgresAccountRepository", _Repo)
    monkeypatch.setattr(w, "_vault_loader", lambda _r: _Loader())
    monkeypatch.setattr(w, "bo_sung_bi_mat_may_chu", lambda _k, c: c)
    monkeypatch.setattr(db, "log_event", log_event)
    monkeypatch.setattr(db, "fetchrow", fetchrow)

    app = FastAPI()
    app.include_router(w.router)
    with TestClient(app) as client:
        yield client, state


# ══════════════════════════════════════════════════════════════════════════════
# A · BUG-08-01 — Nhật ký kết nối lại Zalo cá nhân
# ══════════════════════════════════════════════════════════════════════════════


def test_bug08_01_active_ket_noi_lai_van_ghi_su_kien_reconnected(zalo_webhook_san):
    """Kịch bản 1: Tài khoản đang ACTIVE, kết nối lại thành công -> ghi `channel_account.reconnected`."""
    client, state = zalo_webhook_san
    tk = state["account"]
    assert tk.status == AccountStatus.ACTIVE

    path = f"/webhook/native/zalo-personal/{tk.id}"
    body = json.dumps({
        "event": "health",
        "data": {"status": "connected", "own_id": "own-zalo-001", "trigger": "restore"},
    }).encode()
    resp = client.post(path, content=body, headers=_sign_headers(state["secret"], path, body))
    assert resp.status_code == 200
    assert resp.json()["reconnected_logged"] is True

    reconn = [e for e in state["events"] if e["kind"] == "channel_account.reconnected"]
    changed = [e for e in state["events"] if e["kind"] == "channel_account.status_changed"]
    assert changed == []  # Trạng thái vẫn ACTIVE -> không phát sinh status_changed giả
    assert len(reconn) == 1
    ev = reconn[0]
    assert ev["ref_id"] == tk.id
    assert ev["detail"]["account_id"] == str(tk.id)
    assert ev["detail"]["status"] == "active"
    assert ev["detail"]["previous_status"] == "active"
    assert ev["detail"]["ket_qua"] == "thanh_cong"
    assert ev["detail"]["trigger"] == "restore"


def test_bug08_01_disconnected_ket_noi_lai_ghi_doi_trang_thai_va_reconnected(zalo_webhook_san):
    """Kịch bản 2: Tài khoản bị degraded/reauth_required kết nối lại -> ghi cả status_changed và reconnected."""
    client, state = zalo_webhook_san
    acc = state["account"]
    state["account"] = ChannelAccount(
        id=acc.id, channel=acc.channel, display_name=acc.display_name,
        external_account_id=acc.external_account_id,
        status=AccountStatus.REAUTH_REQUIRED,
        capabilities=acc.capabilities, metadata=acc.metadata, is_legacy=acc.is_legacy,
    )

    path = f"/webhook/native/zalo-personal/{acc.id}"
    body = json.dumps({
        "event": "health",
        "data": {"status": "connected", "own_id": "own-zalo-001", "trigger": "qr"},
    }).encode()
    resp = client.post(path, content=body, headers=_sign_headers(state["secret"], path, body))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "health": "active", "reconnected_logged": True}
    assert state["account"].status == AccountStatus.ACTIVE

    kinds = [e["kind"] for e in state["events"]]
    assert "channel_account.status_changed" in kinds
    assert "channel_account.reconnected" in kinds
    reconn = next(e for e in state["events"] if e["kind"] == "channel_account.reconnected")
    assert reconn["detail"]["previous_status"] == "reauth_required"
    assert reconn["detail"]["status"] == "active"


def test_bug08_01_callback_loi_hoac_khong_hop_le_khong_ghi_reconnected(zalo_webhook_san):
    """Kịch bản 3: Sai chữ ký (401), JSON lỗi (400), hoặc status=disconnected -> không ghi reconnected."""
    client, state = zalo_webhook_san
    tk = state["account"]
    path = f"/webhook/native/zalo-personal/{tk.id}"

    # 1. Sai chữ ký HMAC
    bad_body = json.dumps({"event": "health", "data": {"status": "connected", "own_id": "own-zalo-001"}}).encode()
    r401 = client.post(path, content=bad_body, headers={
        **_sign_headers("wrong-secret-" + "x" * 24, path, bad_body),
    })
    assert r401.status_code == 401

    # 2. JSON hỏng dù chữ ký đúng
    corrupt = b"{not-json"
    r400 = client.post(path, content=corrupt, headers=_sign_headers(state["secret"], path, corrupt))
    assert r400.status_code == 400

    # 3. Callback báo disconnected (xác thực/kết nối thất bại)
    disc = json.dumps({"event": "health", "data": {"status": "disconnected"}}).encode()
    r200 = client.post(path, content=disc, headers=_sign_headers(state["secret"], path, disc))
    assert r200.status_code == 200
    assert r200.json()["reconnected_logged"] is False

    reconn = [e for e in state["events"] if e["kind"] == "channel_account.reconnected"]
    assert reconn == []


def test_bug08_01_heartbeat_binh_thuong_khong_spam_reconnected(zalo_webhook_san):
    """Kịch bản 4: Heartbeat (`heartbeat=true` và ping lặp định kỳ) không làm phát sinh nhiều `reconnected`."""
    client, state = zalo_webhook_san
    tk = state["account"]
    path = f"/webhook/native/zalo-personal/{tk.id}"

    # 4a. Heartbeat tường minh khi đang active -> 0 reconnected
    for i in range(4):
        hb = json.dumps({
            "event": "health",
            "data": {"status": "connected", "own_id": "own-zalo-001", "heartbeat": True, "seq": i},
        }).encode()
        r = client.post(path, content=hb, headers=_sign_headers(state["secret"], path, hb))
        assert r.status_code == 200
        assert r.json()["reconnected_logged"] is False
    assert [e for e in state["events"] if e["kind"] == "channel_account.reconnected"] == []
    assert len(state["health"]) == 4  # Bảng health vẫn ghi bình thường

    # 4b. Ping health lặp lại liên tục trong cửa sổ chống trùng -> tối đa 1 reconnected
    for _ in range(5):
        ping = json.dumps({"event": "health", "data": {"status": "connected", "own_id": "own-zalo-001"}}).encode()
        r = client.post(path, content=ping, headers=_sign_headers(state["secret"], path, ping))
        assert r.status_code == 200
    reconn = [e for e in state["events"] if e["kind"] == "channel_account.reconnected"]
    assert len(reconn) == 1


def test_bug08_01_callback_retry_cung_su_kien_khong_ghi_trung(zalo_webhook_san):
    """Kịch bản 5: Callback retry cùng `event_id` (dù đổi HTTP nonce hay mất cache RAM) chỉ ghi 1 dòng."""
    client, state = zalo_webhook_san
    tk = state["account"]
    path = f"/webhook/native/zalo-personal/{tk.id}"

    payload = {
        "event": "health",
        "event_id": "evt-reconnect-retry-001",
        "data": {"status": "connected", "own_id": "own-zalo-001", "reconnected": True},
    }
    body = json.dumps(payload).encode()

    # Lần gửi 1
    r1 = client.post(path, content=body, headers=_sign_headers(state["secret"], path, body, nonce="n1"))
    assert r1.status_code == 200 and r1.json()["reconnected_logged"] is True

    # Lần retry 2 với nonce mới (simulate queue retry của sidecar)
    r2 = client.post(path, content=body, headers=_sign_headers(state["secret"], path, body, nonce="n2"))
    assert r2.status_code == 200 and r2.json()["reconnected_logged"] is False

    # Lần retry 3 ngay cả sau khi mất RAM cache (kiểm tra đối chiếu CSDL `events`)
    w._DA_GHI_KET_NOI_LAI.clear()
    r3 = client.post(path, content=body, headers=_sign_headers(state["secret"], path, body, nonce="n3"))
    assert r3.status_code == 200 and r3.json()["reconnected_logged"] is False

    reconn = [e for e in state["events"] if e["kind"] == "channel_account.reconnected"]
    assert len(reconn) == 1


def test_bug08_01_audit_khong_chua_token_session_secret_hay_qr(zalo_webhook_san):
    """Kịch bản 6: Nhật ký không bao giờ chứa cookie, session secret, token, IMEI hay ảnh QR."""
    client, state = zalo_webhook_san
    tk = state["account"]
    path = f"/webhook/native/zalo-personal/{tk.id}"

    bi_mat = ("COOKIE-ZALO-SECRET-999", "IMEI-SECRET-888", "EAAB-TOKEN-SECRET-777", "QR-IMAGE-BASE64-SECRET", state["secret"])
    sess_body = json.dumps({
        "event": "session",
        "data": {"cookie": bi_mat[0], "imei": bi_mat[1], "userAgent": "ZaloAgent/1.0"},
    }).encode()
    assert client.post(path, content=sess_body, headers=_sign_headers(state["secret"], path, sess_body)).status_code == 200

    hl_body = json.dumps({
        "event": "health",
        "data": {
            "status": "connected",
            "own_id": "own-zalo-001",
            "token": bi_mat[2],
            "qr_image": bi_mat[3],
            "session_secret": state["secret"],
            "reconnected": True,
        },
    }).encode()
    assert client.post(path, content=hl_body, headers=_sign_headers(state["secret"], path, hl_body)).status_code == 200

    serialized = json.dumps(state["events"], ensure_ascii=False, default=str)
    for secret_val in bi_mat:
        assert secret_val not in serialized


# ══════════════════════════════════════════════════════════════════════════════
# B · BUG-08-02 — Nhãn tiếng Việt, chuẩn hoá kết quả, tên tài khoản & phân quyền
# ══════════════════════════════════════════════════════════════════════════════


def test_bug08_02_nhan_tieng_viet_va_chuan_hoa_status_trang_thai_thuan():
    """Kịch bản 7 & 8 (thuần): nhãn tiếng Việt cho mọi `channel_account.*` và chuẩn hoá `status` / `trang_thai`."""
    for kind in (
        "channel_account.created",
        "channel_account.status_changed",
        "channel_account.identity_bound",
        "channel_account.credentials_rotated",
        "channel_account.reconnected",
    ):
        assert nk.NHAN_HANH_DONG[kind] != kind
        assert not nk.NHAN_HANH_DONG[kind].startswith("channel_account.")

    # Cả `status` lẫn `trang_thai` phải cho kết quả rõ ràng như nhau
    kq_status = nk.ket_qua("channel_account.status_changed", {"status": "active"})
    kq_trang_thai = nk.ket_qua("channel_account.status_changed", {"trang_thai": "active"})
    assert "Đang hoạt động" in kq_status
    assert kq_status == kq_trang_thai

    kq_reconn = nk.ket_qua("channel_account.reconnected", {"status": "active", "ket_qua": "thanh_cong"})
    assert "Kết nối lại" in kq_reconn or "kết nối lại" in kq_reconn
    assert "Đang hoạt động" in kq_reconn

    kq_rot = nk.ket_qua("channel_account.credentials_rotated", {})
    assert kq_rot and "xác thực" in kq_rot

    kq_id = nk.ket_qua("channel_account.identity_bound", {"external_account_id": "zalo-42"})
    assert "zalo-42" in kq_id


def test_bug08_02_csdl_phan_giai_ten_tai_khoan_va_du_phong_khi_da_xoa(app_that, monkeypatch):
    """
    Kịch bản 7, 8, 9, 10, 11 & 12 trên Postgres `kiemthu`:
    - Tên tài khoản giải từ `channel_accounts.display_name`.
    - Tài khoản đã xoá / UUID không tồn tại có giá trị dự phòng an toàn, không lỗi danh sách.
    - Bộ lọc & phân trang `next_cursor` hoạt động chính xác.
    - Người thiếu quyền `nhat_ky.doc` nhận 403.
    """
    qt = _quan_tri_vao(app_that)
    _, nv_khong_quyen = _nhan_vien_moi(qt, "nv-no-audit-" + uuid4().hex[:6])

    acc_id = uuid4()
    deleted_acc_id = uuid4()
    unique_tag = "dot3-" + uuid4().hex[:6]

    async def _seed():
        await db.execute(
            "INSERT INTO channel_accounts (id, channel, display_name, external_account_id, status) "
            "VALUES ($1, 'zalo_personal', $2, $3, 'active')",
            acc_id,
            f"Zalo Shop {unique_tag}",
            f"ext-{unique_tag}",
        )
        # 1. Tạo sự kiện cho tài khoản còn tồn tại
        await db.execute(
            "INSERT INTO events (kind, actor, ref_id, detail) VALUES "
            "('channel_account.status_changed', '00000000-0000-0000-0000-000000000000', $1, $2), "
            "('channel_account.reconnected', '00000000-0000-0000-0000-000000000000', $1, $3), "
            "('channel_account.credentials_rotated', '00000000-0000-0000-0000-000000000000', $1, '{}'::jsonb), "
            "('channel_account.identity_bound', '00000000-0000-0000-0000-000000000000', $1, $4), "
            # 2. Sự kiện trỏ tới tài khoản đã bị xoá / không có trong channel_accounts
            "('channel_account.reconnected', '00000000-0000-0000-0000-000000000000', $5, $6)",
            acc_id,
            {"status": "reauth_required"},
            {"status": "active", "previous_status": "reauth_required", "ket_qua": "thanh_cong", "trigger": "qr"},
            {"external_account_id": f"ext-{unique_tag}"},
            deleted_acc_id,
            {"trang_thai": "active", "ket_qua": "thanh_cong", "token": "secret-should-hide"},
        )

    _sql(app_that, _seed)

    # Kịch bản 12: Thiếu quyền `nhat_ky.doc` -> 403 trên mọi cổng audit tổng
    for duong in ("/api/nhat-ky", "/api/nhat-ky/danh-muc", "/api/nhat-ky/xuat.csv"):
        r_cam = nv_khong_quyen.get(duong)
        assert r_cam.status_code == 403, f"{duong} trả {r_cam.status_code}"

    # Admin tra với bộ lọc `nhom=cau_hinh` và phân trang `limit=2`
    p1 = qt.get("/api/nhat-ky?nhom=cau_hinh&limit=2")
    assert p1.status_code == 200
    d1 = p1.json()
    assert len(d1["items"]) == 2
    assert d1["next_cursor"] is not None

    p2 = qt.get(f"/api/nhat-ky?nhom=cau_hinh&limit=10&truoc={d1['next_cursor']}")
    assert p2.status_code == 200
    tat_ca = d1["items"] + p2.json()["items"]

    # Kiểm tài khoản còn tồn tại phân giải đúng `channel_accounts.display_name`
    cua_acc = [b for b in tat_ca if b.get("ref_id") == str(acc_id)]
    assert len(cua_acc) >= 4
    for b in cua_acc:
        assert b["tai_khoan"]["ten"] == f"Zalo Shop {unique_tag}"
        assert b["tai_khoan"]["ton_tai"] is True
        assert b["doi_tuong"] == f"Zalo Shop {unique_tag}"
        assert b["ket_qua"] != ""
        assert b["hanh_dong"] != b["kind"]  # Nhãn tiếng Việt, không còn mã kỹ thuật thô

    st_loi = next(b for b in cua_acc if b["kind"] == "channel_account.status_changed")
    assert st_loi["trang_thai"]["ma"] == "loi"
    assert "reauth_required" in st_loi["ket_qua"]

    # Kiểm tài khoản đã xoá có giá trị dự phòng an toàn và che bí mật
    cua_deleted = next(b for b in tat_ca if b.get("ref_id") == str(deleted_acc_id))
    assert cua_deleted["tai_khoan"]["ton_tai"] is False
    assert str(deleted_acc_id)[:8] in cua_deleted["tai_khoan"]["ten"]
    assert "đã xoá" in cua_deleted["tai_khoan"]["ten"]
    assert "secret-should-hide" not in json.dumps(cua_deleted, ensure_ascii=False)

    # Kịch bản UI: Kiểm hàm `nkDong` và `nkVeChiTiet` trong dashboard/src/27-nhat-ky.js hiển thị đủ 5 thông tin
    js_path = AGENT_ROOT / "dashboard" / "src" / "27-nhat-ky.js"
    node_script = """
    const fs = require('fs');
    const src = fs.readFileSync(process.argv[1], 'utf8');
    const fn = new Function(
      'state', 'esc', 'gioTin', 'clock', 'dongCT', 'api', 'toast', 'hoiHop', 'window', 'document', 'GAN_TAB',
      src + '; return { nkDong, nkVeChiTiet };'
    );
    const api = fn(
      { toiQuyen: new Set(['nhat_ky.doc']) },
      (s) => String(s ?? ''),
      (iso) => '10:30',
      (iso) => '10:30',
      (t, c) => `<div><b>${t}</b><span>${c}</span></div>`,
      async () => ({}),
      () => {},
      async () => null,
      {},
      { addEventListener() {} },
      {}
    );
    const b = JSON.parse(process.argv[2]);
    console.log(JSON.stringify({
      row: api.nkDong(b),
      detail: api.nkVeChiTiet(b)
    }));
    """
    rendered = json.loads(
        subprocess.check_output(
            ["node", "-e", node_script, str(js_path), json.dumps(cua_acc[0], ensure_ascii=False)],
            text=True,
        )
    )
    assert f"Zalo Shop {unique_tag}" in rendered["row"]
    assert "Hệ thống" in rendered["row"]
    assert cua_acc[0]["ket_qua"] in rendered["row"]
    assert "10:30" in rendered["row"]
    assert "Tài khoản / đối tượng" in rendered["detail"]
    assert f"Zalo Shop {unique_tag}" in rendered["detail"]
