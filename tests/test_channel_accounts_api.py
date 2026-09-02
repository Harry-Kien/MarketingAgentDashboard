"""API quản trị kết nối đa tài khoản."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agent.api.channel_accounts import (
    get_connection_verifier,
    get_account_repository,
    get_account_service,
    router,
)
from agent.channels.base import ConnectionCheck
from agent.api.routes import bat_buoc_dang_nhap, bat_buoc_quan_tri
from agent.omnichannel.account_service import ChannelAccountService
from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount
from agent.security.credential_vault import CredentialVault, SealedCredential


class _Repository:
    def __init__(self):
        self.accounts: dict[UUID, ChannelAccount] = {}
        self.secrets: dict[UUID, SealedCredential] = {}

    async def find_by_external(self, channel, external_account_id):
        return next(
            (
                account
                for account in self.accounts.values()
                if account.channel == channel
                and account.external_account_id == external_account_id
            ),
            None,
        )

    async def create(self, account, sealed, *, actor_id):
        self.accounts[account.id] = account
        if sealed:
            self.secrets[account.id] = sealed
        return account

    async def get(self, account_id):
        return self.accounts.get(account_id)

    async def list_for_user(self, user_id, *, is_admin):
        return list(self.accounts.values()) if is_admin else []

    async def has_credentials(self, account_id):
        return account_id in self.secrets

    async def store_credentials(self, account_id, sealed, *, actor_id):
        self.secrets[account_id] = sealed

    async def update_status(self, account_id, status, *, actor_id):
        old = self.accounts[account_id]
        updated = ChannelAccount(
            id=old.id,
            channel=old.channel,
            display_name=old.display_name,
            external_account_id=old.external_account_id,
            status=status,
            capabilities=old.capabilities,
            metadata=old.metadata,
            is_legacy=old.is_legacy,
        )
        self.accounts[account_id] = updated
        return updated

    async def latest_health(self, account_id):
        return None


def _app(*, logged_in: bool, admin: bool = True):
    app = FastAPI()
    app.include_router(router)
    repository = _Repository()
    vault = CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=1)
    service = ChannelAccountService(repository, vault)
    app.dependency_overrides[get_account_repository] = lambda: repository
    app.dependency_overrides[get_account_service] = lambda: service
    if logged_in:
        user = {
            "id": uuid4(),
            "ten_dang_nhap": "admin" if admin else "staff",
            "vai_tro": "quan_tri" if admin else "nhan_vien",
        }
        app.dependency_overrides[bat_buoc_dang_nhap] = lambda: user
        if admin:
            app.dependency_overrides[bat_buoc_quan_tri] = lambda: user
        else:
            def deny_admin():
                raise HTTPException(403, "Việc này cần quyền quản trị")

            app.dependency_overrides[bat_buoc_quan_tri] = deny_admin
    return app, repository


def _payload():
    return {
        "channel": "zalo_oa",
        "display_name": "OA Hà Nội",
        "external_account_id": "oa-1",
        "capabilities": {"send_text": True},
        "metadata": {},
        "credentials": {"access_token": "secret-token"},
    }


def test_list_accounts_bat_buoc_dang_nhap():
    app, _ = _app(logged_in=False)

    response = TestClient(app).get("/api/channel-accounts")

    assert response.status_code == 401


def test_admin_tao_account_ma_response_khong_echo_secret():
    app, _ = _app(logged_in=True)

    response = TestClient(app).post("/api/channel-accounts", json=_payload())

    assert response.status_code == 201
    assert response.json()["has_credentials"] is True
    assert "credentials" not in response.json()
    assert "secret-token" not in response.text


def test_nhan_vien_khong_duoc_tao_account():
    app, _ = _app(logged_in=True, admin=False)

    response = TestClient(app).post("/api/channel-accounts", json=_payload())

    assert response.status_code == 403


def test_list_chi_tra_account_repository_cho_phep():
    app, repository = _app(logged_in=True, admin=False)
    repository.accounts[uuid4()] = ChannelAccount(
        id=uuid4(),
        channel=Channel.FACEBOOK,
        display_name="Page không được gán",
        external_account_id="page-1",
        status=AccountStatus.ACTIVE,
        capabilities={},
        metadata={},
        is_legacy=False,
    )

    response = TestClient(app).get("/api/channel-accounts")

    assert response.status_code == 200
    assert response.json() == []


def test_rotate_enable_disable_khong_tra_secret():
    app, _ = _app(logged_in=True)
    client = TestClient(app)
    created = client.post("/api/channel-accounts", json=_payload()).json()
    account_id = created["id"]

    rotated = client.put(
        f"/api/channel-accounts/{account_id}/credentials",
        json={"credentials": {"access_token": "new-secret-token"}},
    )
    enabled = client.post(f"/api/channel-accounts/{account_id}/enable")
    disabled = client.post(f"/api/channel-accounts/{account_id}/disable")

    assert rotated.status_code == 204
    assert "new-secret-token" not in rotated.text
    assert enabled.json()["status"] == "active"
    assert disabled.json()["status"] == "disabled"


def test_health_chua_co_mau_do_tra_null_ro_rang():
    app, _ = _app(logged_in=True)
    client = TestClient(app)
    created = client.post("/api/channel-accounts", json=_payload()).json()

    response = client.get(f"/api/channel-accounts/{created['id']}/health")

    assert response.status_code == 200
    assert response.json() == {"latest": None}


def test_disable_account_khong_co_secret_khong_duoc_bao_co():
    app, _ = _app(logged_in=True)
    client = TestClient(app)
    payload = _payload()
    payload["credentials"] = None
    created = client.post("/api/channel-accounts", json=payload).json()

    response = client.post(f"/api/channel-accounts/{created['id']}/disable")

    assert response.status_code == 200
    assert response.json()["has_credentials"] is False


def test_verify_provider_moi_duoc_bao_san_sang():
    app, _ = _app(logged_in=True)
    client = TestClient(app)
    account_id = client.post("/api/channel-accounts", json=_payload()).json()["id"]

    class Verifier:
        async def verify(self, requested_id, *, actor_id):
            assert str(requested_id) == account_id
            assert actor_id
            return ConnectionCheck(True, "provider.ok", "oa-verified", {"name": "OA Hà Nội"})

    app.dependency_overrides[get_connection_verifier] = lambda: Verifier()
    response = client.post(f"/api/channel-accounts/{account_id}/verify")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "code": "provider.ok",
        "external_account_id": "oa-verified",
        "detail": {"name": "OA Hà Nội"},
    }
