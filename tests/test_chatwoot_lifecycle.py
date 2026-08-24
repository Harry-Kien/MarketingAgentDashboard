"""
Kiểm thử vòng đời Chatwoot hai chiều. Không gọi API thật, không cần CSDL.

Agent bàn giao sang người mới chỉ là nửa đầu. Nếu không nghe tin nhân viên và
trạng thái resolved/open từ Chatwoot, hai hệ thống sẽ có hai bản khác nhau về
việc ai đang chịu trách nhiệm — nguồn gốc của hai giọng nói hoặc khách bị bỏ
rơi trong im lặng.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac

from agent import main as app_main
from agent.channels import chatwoot
from agent.config import settings


def _outgoing(**them) -> dict:
    payload = {
        "event": "message_created",
        "id": 91,
        "message_type": "outgoing",
        "content": "Em đã kiểm tra đơn cho chị",
        "private": False,
        "content_attributes": {},
        "additional_attributes": {},
        "conversation": {"id": 42},
        "sender": {"id": 7, "name": "Linh", "type": "User"},
    }
    payload.update(them)
    return payload


def test_nhan_dien_dung_tin_nhan_vien():
    assert chatwoot.la_tin_nhan_vien(_outgoing())


def test_khong_nhan_webhook_vong_cua_agent_lam_nhan_vien():
    payload = _outgoing(
        content_attributes={chatwoot.DAU_TIN_AGENT: True}
    )
    assert chatwoot.la_tin_do_agent_gui(payload)
    assert not chatwoot.la_tin_nhan_vien(payload)


def test_khong_nhan_bot_automation_campaign_lam_nhan_vien():
    assert not chatwoot.la_tin_nhan_vien(
        _outgoing(sender={"type": "AgentBot"})
    )
    assert not chatwoot.la_tin_nhan_vien(
        _outgoing(content_attributes={"automation_rule_id": 1})
    )
    assert not chatwoot.la_tin_nhan_vien(
        _outgoing(additional_attributes={"campaign_id": 1})
    )
    assert not chatwoot.la_tin_nhan_vien(_outgoing(private=True))


class _HttpGia:
    def __init__(self):
        self.goi = []

    async def post(self, path, **kwargs):
        self.goi.append((path, kwargs))

        class _Tra:
            status_code = 200
            text = ""

        return _Tra()


def test_tin_agent_gui_ra_mang_dau_chong_echo(monkeypatch):
    """
    ÉP CẤU HÌNH bằng monkeypatch, KHÔNG đọc `.env` thật.

    Bản đầu dựa vào `.env` của máy đang chạy: `send_text` thoát sớm với
    `Delivery(False, "Chưa cấu hình")` khi thiếu CHATWOOT_*, nên ca này
    xanh trên máy đã cấu hình và ĐỎ trên mọi bản clone sạch — kể cả job
    `clone-sach` trong CI.

    Test phải nói về hành vi của mã, không nói về cấu hình của người chạy nó.
    """
    monkeypatch.setattr(settings, "chatwoot_base_url", "http://localhost:3200")
    monkeypatch.setattr(settings, "chatwoot_api_token", "token-thu")
    monkeypatch.setattr(settings, "chatwoot_account_id", "1")
    adapter = chatwoot.ChatwootAdapter()
    http = _HttpGia()
    adapter._client = http
    ket_qua = asyncio.run(adapter.send_text("42", "xin chào"))
    assert ket_qua.ok
    body = http.goi[0][1]["json"]
    assert body["content_attributes"][chatwoot.DAU_TIN_AGENT] is True


def test_chu_ky_chatwoot_dung_thi_nhan(monkeypatch):
    monkeypatch.setattr(settings, "chatwoot_webhook_secret", "bi-mat")
    body = b'{"event":"message_created"}'
    timestamp = "1724544000"
    signature = "sha256=" + hmac.new(
        b"bi-mat", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    assert app_main._chatwoot_signature_hop_le(
        body,
        {
            "x-chatwoot-timestamp": timestamp,
            "x-chatwoot-signature": signature,
        },
        now=int(timestamp),
    )


def test_chu_ky_sai_hoac_cu_bi_chan(monkeypatch):
    monkeypatch.setattr(settings, "chatwoot_webhook_secret", "bi-mat")
    headers = {
        "x-chatwoot-timestamp": "1724544000",
        "x-chatwoot-signature": "sha256=sai",
    }
    assert not app_main._chatwoot_signature_hop_le(
        b"{}", headers, now=1724544000
    )

    signature = "sha256=" + hmac.new(
        b"bi-mat", b"1724544000.{}", hashlib.sha256
    ).hexdigest()
    headers["x-chatwoot-signature"] = signature
    assert not app_main._chatwoot_signature_hop_le(
        b"{}", headers, now=1724545000
    )


def test_tin_nhan_vien_duoc_luu_va_khoa_agent(monkeypatch):
    sql_da_chay = []
    events = []

    async def seen(_key):
        return False

    async def fetchrow(sql, *_args):
        if sql.startswith("SELECT id FROM conversations"):
            return {"id": "conv-local"}
        return None

    async def execute(sql, *args):
        sql_da_chay.append((sql, args))
        return "OK"

    async def log(kind, **detail):
        events.append((kind, detail))

    monkeypatch.setattr(app_main.db, "seen_webhook", seen)
    monkeypatch.setattr(app_main.db, "fetchrow", fetchrow)
    monkeypatch.setattr(app_main.db, "execute", execute)
    monkeypatch.setattr(app_main.db, "log_event", log)

    asyncio.run(app_main._xu_ly_su_kien_chatwoot(_outgoing()))

    assert any("VALUES ($1,'staff'" in sql for sql, _ in sql_da_chay)
    assert any("status = 'escalated'" in sql for sql, _ in sql_da_chay)
    assert events[0][0] == "chatwoot.staff_takeover"


def test_resolved_dong_viec_va_open_chi_mo_khoa_viec_da_dong(monkeypatch):
    sql_da_chay = []
    events = []

    async def seen(_key):
        return False

    async def fetchrow(sql, *_args):
        sql_da_chay.append(sql)
        return {"id": "conv-local"}

    async def log(kind, **detail):
        events.append((kind, detail))

    monkeypatch.setattr(app_main.db, "seen_webhook", seen)
    monkeypatch.setattr(app_main.db, "fetchrow", fetchrow)
    monkeypatch.setattr(app_main.db, "log_event", log)

    base = {
        "event": "conversation_status_changed",
        "id": 42,
        "updated_at": 1724544000,
    }
    asyncio.run(
        app_main._xu_ly_su_kien_chatwoot({**base, "status": "resolved"})
    )
    asyncio.run(
        app_main._xu_ly_su_kien_chatwoot(
            {**base, "status": "open", "updated_at": 1724544001}
        )
    )

    assert "status = 'closed'" in sql_da_chay[0]
    assert "status = 'auto'" in sql_da_chay[1]
    assert "AND status = 'closed'" in sql_da_chay[1]
    assert [kind for kind, _ in events] == [
        "chatwoot.resolved",
        "chatwoot.agent_nhan_lai",
    ]
