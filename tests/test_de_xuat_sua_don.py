"""GAP-17-01: proposal-only order changes, no ERP mutation or paid model."""
import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from agent.api import uy_quyen_ai as api
from agent.core import thao_tac_don as service
from agent.core import tools, uy_quyen
from agent.erp import nha_may


@pytest.fixture
def context(monkeypatch):
    cid, oid = uuid4(), uuid4()
    order = dict(id=oid, ma_don="TEST-17", trang_thai="da_chot",
                 items=[dict(ma="SP1", ten="Sản phẩm thử", so_luong=1, don_gia=100)],
                 updated_at="2026-11-25", erp_ma_don="SO-TEST")

    async def read(sql, ma, conv):
        assert "conversation_id=$2" in sql
        return deepcopy(order) if ma == "TEST-17" and conv == cid else None

    monkeypatch.setattr(service.db, "fetchrow", read)
    erp = AsyncMock(return_value=dict(name="SO-TEST", docstatus=1,
                                     status="To Deliver and Bill", modified="v1"))
    gateway = type("ReadOnlyERP", (), {"doc_don": erp})()
    monkeypatch.setattr(nha_may, "cong", lambda: gateway)
    proposal = AsyncMock(return_value=(uuid4(), True))
    monkeypatch.setattr(uy_quyen, "tao_de_xuat", proposal)
    args = dict(ma_don="TEST-17", ma_san_pham="SP1", so_luong=2, ly_do="Khách cần thêm")
    return cid, order, args, proposal, erp


def test_quantity_proposal_no_execution(context):
    cid, order, args, proposal, erp = context
    result = asyncio.run(service.de_xuat_sua_don(args, cid))
    assert result["da_de_xuat"] and result["da_sua"] is False
    data = proposal.call_args.kwargs
    assert data["de_xuat"]["truoc"]["items"][0]["so_luong"] == 1
    assert data["de_xuat"]["sau"]["items"][0]["so_luong"] == 2
    assert order["items"][0]["so_luong"] == 1
    assert data["quyet"].can_duyet
    erp.assert_awaited_once_with("SO-TEST")


@pytest.mark.parametrize("key,value", [("ma_don", ""), ("ma_san_pham", ""),
    ("ly_do", ""), ("so_luong", None), ("so_luong", True), ("so_luong", 0),
    ("so_luong", 1000), ("so_luong", "2"), ("so_luong", 1), ("ma_san_pham", "OTHER")])
def test_missing_or_invalid_input(context, key, value):
    cid, _, args, proposal, _ = context
    args[key] = value
    assert not asyncio.run(service.de_xuat_sua_don(args, cid))["da_de_xuat"]
    proposal.assert_not_awaited()


@pytest.mark.parametrize("other_owner", [False, True])
def test_missing_or_foreign_order(context, other_owner):
    cid, _, args, proposal, erp = context
    if other_owner:
        cid = uuid4()
    else:
        args["ma_don"] = "NOT-FOUND"
    assert not asyncio.run(service.de_xuat_sua_don(args, cid))["da_de_xuat"]
    proposal.assert_not_awaited()
    erp.assert_not_awaited()


@pytest.mark.parametrize("field,value", [("trang_thai", "da_huy"),
    ("trang_thai", "da_giao"), ("trang_thai", "cho_dong_bo"),
    ("ma_van_don", "GHN1"), ("yeu_cau_huy_luc", "today")])
def test_ineligible_order(context, field, value):
    cid, order, args, proposal, _ = context
    order[field] = value
    assert not asyncio.run(service.de_xuat_sua_don(args, cid))["da_de_xuat"]
    proposal.assert_not_awaited()


@pytest.mark.parametrize("failure", [TimeoutError("SECRET"), RuntimeError("SECRET")])
def test_erp_errors_fail_closed(context, failure):
    cid, _, args, proposal, erp = context
    erp.side_effect = failure
    result = asyncio.run(service.de_xuat_sua_don(args, cid))
    assert not result["da_de_xuat"] and "SECRET" not in str(result)
    proposal.assert_not_awaited()


@pytest.mark.parametrize("changed", [None, "local", "erp", "owner"])
def test_approval_revalidates_and_never_claims_success(context, changed):
    cid, order, args, proposal, erp = context

    async def run():
        await service.de_xuat_sua_don(args, cid)
        data = proposal.call_args.kwargs
        dx = dict(hanh_dong="sua_don", conversation_id=cid, order_id=order["id"],
                  tham_so=data["tham_so"], de_xuat=data["de_xuat"])
        if changed == "local":
            order["updated_at"] = "v2"
        if changed == "erp":
            erp.return_value["modified"] = "v2"
        if changed == "owner":
            dx["conversation_id"] = uuid4()
        ok, result, error, _ = await api._thi_hanh(dx, {"ten_dang_nhap": "tester"})
        assert not ok and error
        assert result == {"can_xu_ly_thu_cong": True, "da_sua": False}
    asyncio.run(run())


def test_business_permission_required(monkeypatch):
    monkeypatch.setattr(api.db, "fetchrow", AsyncMock(return_value={
        "conversation_id": uuid4(), "hanh_dong": "sua_don"}))
    monkeypatch.setattr(api, "chan_neu_ngoai_kenh", AsyncMock())
    monkeypatch.setattr(api.xac_thuc, "duoc_phep", lambda *_: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._kiem_quyen_de_xuat(uuid4(), {}))
    assert exc.value.status_code == 403


def test_support_flag_and_dispatch(monkeypatch):
    assert not uy_quyen.DANH_MUC["sua_don"].ho_tro
    assert uy_quyen.DANH_MUC["sua_don"].quyen_thi_hanh == "don.sua"
    assert asyncio.run(uy_quyen.phan_loai_cong_cu("de_xuat_sua_don")) == "de_xuat_thu_cong"
    assert any(t["name"] == "de_xuat_sua_don" for t in tools.TOOLS)


def test_actual_tool_dispatch_and_skill_disable(context, monkeypatch):
    from agent.ky_nang import kho_ky_nang

    cid, _, args, proposal, _ = context
    monkeypatch.setattr(service.db, "log_event", AsyncMock())
    disabled = AsyncMock(return_value=False)
    monkeypatch.setattr(kho_ky_nang, "dang_tat", disabled)
    monkeypatch.setattr(kho_ky_nang, "tim_plugin", AsyncMock(return_value=None))
    assert asyncio.run(tools.run_tool("de_xuat_sua_don", args, cid))["da_de_xuat"]
    proposal.assert_awaited_once()
    disabled.return_value = True
    assert asyncio.run(tools.run_tool("de_xuat_sua_don", args, cid))["can_chuyen_nhan_vien"]
    proposal.assert_awaited_once()


def test_channel_scope_rechecked(monkeypatch):
    monkeypatch.setattr(api.db, "fetchrow", AsyncMock(return_value={
        "conversation_id": uuid4(), "hanh_dong": "sua_don"}))
    monkeypatch.setattr(api, "chan_neu_ngoai_kenh", AsyncMock(side_effect=HTTPException(403)))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._kiem_quyen_de_xuat(uuid4(), {}))
    assert exc.value.status_code == 403


def test_erp_timeout_during_approval(context):
    cid, order, args, proposal, erp = context

    async def run():
        await service.de_xuat_sua_don(args, cid)
        data = proposal.call_args.kwargs
        erp.side_effect = TimeoutError("sensitive detail")
        ok, result, error, _ = await api._thi_hanh(dict(
            hanh_dong="sua_don", conversation_id=cid, order_id=order["id"],
            tham_so=data["tham_so"], de_xuat=data["de_xuat"]), {})
        assert not ok and not result and "sensitive" not in error
        assert "đối soát" in error
    asyncio.run(run())


@pytest.mark.parametrize("status", ["Completed", "Closed", "Cancelled", "To Bill"])
def test_ineligible_erp_status(context, status):
    cid, _, args, proposal, erp = context
    erp.return_value["status"] = status
    assert not asyncio.run(service.de_xuat_sua_don(args, cid))["da_de_xuat"]
    proposal.assert_not_awaited()


@pytest.mark.parametrize("docstatus,status", [(0, "Draft"), (1, "To Deliver and Bill")])
def test_5b_no_verified_capability_requires_manual(context, docstatus, status):
    """Not a test of successful ERP edits: the supported fallback must not lie."""
    cid, order, args, proposal, erp = context
    erp.return_value.update(docstatus=docstatus, status=status)

    async def run():
        assert (await service.de_xuat_sua_don(args, cid))["da_de_xuat"]
        data = proposal.call_args.kwargs
        ok, result, reason, _ = await api._thi_hanh(dict(
            hanh_dong="sua_don", conversation_id=cid, order_id=order["id"],
            tham_so=data["tham_so"], de_xuat=data["de_xuat"]), {})
        assert not ok and result["can_xu_ly_thu_cong"] and not result["da_sua"]
        assert ("Draft" if docstatus == 0 else "Update Items") in reason
        for dependency in ("Delivery Note", "Sales Invoice", "Payment", "Stock Reservation"):
            assert dependency in reason
        assert "amendment" in reason if docstatus == 1 else "validation" in reason
        assert erp.await_count == 2  # read at proposal and at approval; no write method exists
    asyncio.run(run())
