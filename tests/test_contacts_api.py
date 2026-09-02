"""API Customer 360 scope theo account, mask PII và merge có quyền."""
from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.contacts import (
    get_contact_repository,
    get_identity_service,
    mask_contact_pii,
    router,
)
from agent.api.routes import bat_buoc_dang_nhap
from agent.omnichannel.identity import MergeResult


class _Repository:
    def __init__(self):
        self.items = []
        self.detail = None
        self.preview = None
        self.can_unmerge = False
        self.can_manage = False
        self.tags = []
        self.consents = []
        self.retention = []

    async def list_visible(self, **kwargs):
        self.list_kwargs = kwargs
        return self.items

    async def get_visible(self, **kwargs):
        self.get_kwargs = kwargs
        return self.detail

    async def merge_preview(self, **kwargs):
        self.preview_kwargs = kwargs
        return self.preview

    async def can_manage_merge(self, **kwargs):
        return self.can_unmerge

    async def can_manage_contact(self, **kwargs):
        return self.can_manage

    async def add_tag(self, **kwargs):
        self.tags.append(kwargs)

    async def set_consent(self, **kwargs):
        self.consents.append(kwargs)
        return {"id": uuid4(), **kwargs}

    async def request_retention(self, **kwargs):
        self.retention.append(kwargs)
        return {"id": uuid4(), "status": "pending_approval"}


class _Identity:
    def __init__(self):
        self.merges = []
        self.unmerges = []

    async def merge_contacts(self, **kwargs):
        self.merges.append(kwargs)
        return MergeResult(uuid4(), kwargs["source_id"], kwargs["target_id"], "active")

    async def unmerge_contact(self, **kwargs):
        self.unmerges.append(kwargs)
        return MergeResult(kwargs["merge_id"], uuid4(), uuid4(), "reverted")


def _client():
    app = FastAPI()
    app.include_router(router)
    repository = _Repository()
    identity = _Identity()
    user = {"id": uuid4(), "vai_tro": "nhan_vien"}
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: user
    app.dependency_overrides[get_contact_repository] = lambda: repository
    app.dependency_overrides[get_identity_service] = lambda: identity
    return TestClient(app), repository, identity, user


def test_mask_pii_khong_lo_sdt_email_day_du():
    masked = mask_contact_pii(
        {"phone": "0901234567", "email": "alice@example.com", "can_view_pii": False}
    )

    assert "0901234567" not in str(masked)
    assert "alice@example.com" not in str(masked)
    assert masked["phone"].endswith("567")
    assert masked["email"].endswith("@example.com")
    assert masked["pii_masked"] is True


def test_list_chuyen_user_scope_vao_repository_va_mask_theo_tung_contact():
    client, repository, _identity, user = _client()
    repository.items = [
        {"id": uuid4(), "phone": "0901234567", "email": "a@b.vn", "can_view_pii": False},
        {"id": uuid4(), "phone": "0911111111", "email": "c@d.vn", "can_view_pii": True},
    ]

    response = client.get("/api/contacts?q=An")

    assert response.status_code == 200
    assert repository.list_kwargs["user_id"] == user["id"]
    assert response.json()[0]["pii_masked"] is True
    assert response.json()[1]["phone"] == "0911111111"


def test_merge_bi_chan_neu_khong_quan_ly_du_moi_account_lien_quan():
    client, repository, identity, _user = _client()
    source, target = uuid4(), uuid4()
    repository.preview = {
        "source": {"id": source, "version": 1},
        "target": {"id": target, "version": 2},
        "can_manage": False,
    }

    response = client.post(
        "/api/contacts/merge",
        json={
            "source_id": str(source),
            "target_id": str(target),
            "reason": "Khách xác nhận",
            "expected_source_version": 1,
            "expected_target_version": 2,
        },
    )

    assert response.status_code == 403
    assert identity.merges == []


def test_merge_duoc_phep_goi_identity_service_voi_actor_va_version():
    client, repository, identity, user = _client()
    source, target = uuid4(), uuid4()
    repository.preview = {
        "source": {"id": source, "version": 1},
        "target": {"id": target, "version": 2},
        "can_manage": True,
    }

    response = client.post(
        "/api/contacts/merge",
        json={
            "source_id": str(source),
            "target_id": str(target),
            "reason": "Cùng số điện thoại đã xác minh",
            "expected_source_version": 1,
            "expected_target_version": 2,
        },
    )

    assert response.status_code == 200
    assert identity.merges[0]["actor_id"] == user["id"]
    assert identity.merges[0]["expected_target_version"] == 2


def test_mutation_customer_360_can_quyen_manager_tren_toan_bo_account():
    client, repository, _identity, _user = _client()
    contact_id = uuid4()

    denied = client.post(
        f"/api/contacts/{contact_id}/tags", json={"tag": "VIP"}
    )
    assert denied.status_code == 403
    assert repository.tags == []

    repository.can_manage = True
    allowed = client.post(
        f"/api/contacts/{contact_id}/tags", json={"tag": "VIP"}
    )
    assert allowed.status_code == 201
    assert repository.tags[0]["tag"] == "VIP"


def test_consent_va_retention_luon_ghi_actor_khong_thuc_thi_xoa_ngay():
    client, repository, _identity, user = _client()
    repository.can_manage = True
    contact_id = uuid4()

    consent = client.put(
        f"/api/contacts/{contact_id}/consents/marketing",
        json={"status": "withdrawn", "source": "Khách yêu cầu trong hội thoại"},
    )
    retention = client.post(
        f"/api/contacts/{contact_id}/retention-jobs",
        json={"kind": "delete", "reason": "Khách yêu cầu", "dry_run": True},
    )

    assert consent.status_code == 200
    assert repository.consents[0]["actor_id"] == user["id"]
    assert retention.status_code == 202
    assert retention.json()["status"] == "pending_approval"
    assert repository.retention[0]["dry_run"] is True
