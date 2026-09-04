"""
Bí mật sidecar là của MÁY CHỦ: mọi chỗ đọc đều lấy từ `.env`, không tin vault.

LỖI ĐÃ XẢY RA THẬT (04.09.2026)
-------------------------------
Vault giữ `sidecar_secret` cũ, sidecar chạy bí mật mới. Adapter dựng từ
vault ký sai -> 401 hai chiều -> kênh Zalo cá nhân chết tám ngày. Nút Quét
QR báo "sidecar chưa chạy" (sai), và không có nút nào để đồng bộ lại.

Ba đường đọc credential Zalo cá nhân — factory, endpoint QR, webhook
callback — giờ cùng đè bí mật từ `.env` lên bản vault. Test này canh cả ba,
vì sửa hai bỏ một là lỗi quay lại đúng ở đường bị bỏ.
"""
from __future__ import annotations

import asyncio
import inspect
from uuid import uuid4

from fastapi import HTTPException

from agent.channels.factory import AccountAdapterFactory, AccountAdapterNotFound
from agent.channels.zalo_personal import ZaloPersonalAdapter
from agent.config import settings
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount


class _Repo:
    def __init__(self, account):
        self._account = account

    async def get(self, account_id):
        return self._account if account_id == self._account.id else None


class _Vault:
    def __init__(self, credentials):
        self._credentials = credentials

    async def load(self, account_id):
        return dict(self._credentials)


def _tai_khoan():
    return ChannelAccount(
        id=uuid4(),
        channel=Channel.ZALO_PERSONAL,
        display_name="Zalo thử",
        external_account_id="1",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )


def test_factory_dung_bi_mat_env_ke_ca_khi_vault_giu_ban_cu(monkeypatch):
    monkeypatch.setattr(settings, "zalo_sidecar_secret", "moi-" * 10)
    monkeypatch.setattr(settings, "zalo_sidecar_url", "http://127.0.0.1:3210")
    account = _tai_khoan()

    adapter = asyncio.run(
        AccountAdapterFactory(
            _Repo(account),
            _Vault({"sidecar_secret": "cu-" * 12, "session": {"cookie": {}}}),
        ).create(account.id)
    )

    assert isinstance(adapter, ZaloPersonalAdapter)
    assert adapter._secret == "moi-" * 10
    asyncio.run(adapter.aclose())


def test_factory_that_bai_ro_rang_khi_env_chua_co_bi_mat(monkeypatch):
    """Điền rỗng là tài khoản trông y hệt tài khoản tốt — phải nổ thay vì im."""
    monkeypatch.setattr(settings, "zalo_sidecar_secret", "")
    account = _tai_khoan()

    try:
        asyncio.run(
            AccountAdapterFactory(
                _Repo(account), _Vault({"sidecar_secret": "cu-" * 12})
            ).create(account.id)
        )
    except AccountAdapterNotFound as exc:
        assert "ZALO_SIDECAR_SECRET" in str(exc)
    else:
        raise AssertionError("phải ném khi máy chủ chưa cấu hình bí mật")


def test_ca_ba_duong_doc_deu_de_bi_mat_may_chu():
    from agent.api import channel_accounts, zalo_personal_webhook
    from agent.channels import factory

    for ham in (
        channel_accounts._zalo_personal_adapter,
        zalo_personal_webhook.zalo_personal_callback,
        factory.AccountAdapterFactory.create,
    ):
        assert "bo_sung_bi_mat_may_chu" in inspect.getsource(ham), ham.__qualname__


def test_loi_chu_ky_khong_con_bi_goi_la_sidecar_chua_chay():
    """
    Ảnh chụp 04.09.2026: hộp thoại Quét QR ghi "Sidecar Zalo cá nhân chưa
    chạy" kèm "(Chữ ký sidecar không hợp lệ)" — hai câu mâu thuẫn trong
    cùng một dòng, và người dùng đi bật một thứ đang chạy.
    """
    from agent.api.channel_accounts import _loi_sidecar

    loi = _loi_sidecar(RuntimeError("Chữ ký sidecar không hợp lệ"))
    assert isinstance(loi, HTTPException)
    assert "chưa chạy" not in loi.detail
    assert "chay_sidecar_zalo" in loi.detail

    van_the = _loi_sidecar(RuntimeError("ConnectError: sidecar không phản hồi"))
    assert "chưa chạy" in van_the.detail
