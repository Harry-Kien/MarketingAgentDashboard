"""
Bộ đăng ký kênh không được ĐOÁN khi gặp tên lạ. Không gọi API, không cần CSDL.

VÌ SAO
------
`registry.get()` từng trả adapter ZaloCRM cho mọi tên không khớp. Chỗ duy
nhất còn đưa tên tuỳ ý vào đó là `/webhook/{kenh}`, với `kenh` lấy thẳng từ
URL. Nghĩa là một POST tới `/webhook/webchat` (đúng secret, sai tên kênh)
được parse bằng adapter ZaloCRM và gán vào tài khoản ZaloCRM — tin sai chỗ
hoặc biến mất, không lỗi, không nhật ký. Đúng kiểu hỏng im lặng mà CLAUDE.md
xếp lên đầu.

Cùng file: `aclose` phải nằm trong hợp đồng `ChannelAdapter`, vì
`registry.dong_tat_ca()` gọi nó cho mọi adapter mà không phòng bị.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from agent.channels import registry
from agent.channels.base import ChannelAdapter, Delivery


def test_ten_la_thi_nem_khong_tra_zalocrm():
    with pytest.raises(registry.KenhKhongTonTai):
        registry.get("kenh_khong_ton_tai")


def test_ten_dung_van_tra_adapter():
    assert registry.get("chatwoot").name == "chatwoot"


def test_webhook_kenh_la_tra_404_sau_khi_da_kiem_secret(monkeypatch):
    """
    404 chứ không 401: người gọi CÓ secret, chỉ gõ sai tên kênh. Trả 401 là
    đẩy họ đi kiểm secret — thứ đang đúng.
    """
    from agent.config import settings
    from agent.main import app

    monkeypatch.setattr(settings, "webhook_secret", "bi-mat-thu")
    r = TestClient(app).post(
        "/webhook/kenh_khong_ton_tai",
        json={"event": "message"},
        headers={"x-webhook-secret": "bi-mat-thu"},
    )
    assert r.status_code == 404, r.text
    assert "không tồn tại" in r.json()["error"]


def test_webhook_sai_secret_van_401_truoc_khi_xet_ten_kenh(monkeypatch):
    """Thứ tự kiểm không đổi: chưa có quyền thì không được biết kênh nào tồn tại."""
    from agent.config import settings
    from agent.main import app

    monkeypatch.setattr(settings, "webhook_secret", "bi-mat-thu")
    r = TestClient(app).post(
        "/webhook/kenh_khong_ton_tai",
        json={},
        headers={"x-webhook-secret": "sai"},
    )
    assert r.status_code == 401


def test_aclose_nam_trong_hop_dong():
    class _ToiThieu(ChannelAdapter):
        name = "toi_thieu"

        def parse(self, payload):
            return None

        async def send_text(self, conversation_ref, text):
            return Delivery(True)

        async def send_file(self, conversation_ref, path, caption=""):
            return Delivery(True)

    # Adapter mới quên `aclose` không được làm `dong_tat_ca()` nổ lúc tắt.
    assert asyncio.run(_ToiThieu().aclose()) is None
