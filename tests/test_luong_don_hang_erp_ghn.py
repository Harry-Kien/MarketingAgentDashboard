"""
Kiểm thử tích hợp luồng: Đặt hàng -> ERP -> GHN (4 điểm cải thiện).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from agent.config import settings
from agent.shipping.ghn import (
    CACHE_DIR,
    GHNShippingProvider,
    _read_disk_cache,
    _write_disk_cache,
)
from agent.shipping.mock import MockShippingProvider
from agent.shipping.models import CreateWaybillResult, InternalShippingStatus
from agent.shipping.service import huy_van_don_cho_don


# ===============================================================
# 1. Kiểm thử Cache 2 tầng của GHN (RAM + Disk Cache)
# ===============================================================

def test_ghn_disk_cache_read_write(tmp_path: Path, monkeypatch):
    test_cache_file = tmp_path / "test_districts.json"
    dummy_data = [{"DistrictID": 9999, "DistrictName": "Quận Thử Nghiệm"}]

    _write_disk_cache(test_cache_file, dummy_data)
    read_back = _read_disk_cache(test_cache_file)
    assert read_back == dummy_data

    # Kiểm tra TTL nếu file quá hạn
    monkeypatch.setattr("agent.shipping.ghn.GHN_CACHE_TTL_SECONDS", -1)
    assert _read_disk_cache(test_cache_file) is None


def test_ghn_resolve_address_uses_disk_cache(tmp_path: Path, monkeypatch):
    provider = GHNShippingProvider(token="test-token", shop_id="12345")

    cached_districts = [{
        "DistrictID": 777,
        "DistrictName": "Quan Ba Dinh",
        "NameExtension": ["Ba Dinh"],
    }]
    cached_wards = [{
        "WardCode": "1001",
        "WardName": "Phuong Dien Bien",
        "NameExtension": ["Dien Bien"],
    }]

    dist_file = tmp_path / "ghn_districts.json"
    ward_file = tmp_path / "ghn_wards_777.json"
    _write_disk_cache(dist_file, cached_districts)
    _write_disk_cache(ward_file, cached_wards)

    monkeypatch.setattr("agent.shipping.ghn.CACHE_DIR", tmp_path)
    monkeypatch.setattr("agent.shipping.ghn._DISTRICTS_CACHE", None)
    monkeypatch.setattr("agent.shipping.ghn._WARDS_CACHE", {})

    with patch("httpx.AsyncClient.get") as mock_get, patch("httpx.AsyncClient.post") as mock_post:
        dist_id, ward_code = asyncio.run(provider._resolve_address("12 Dien Bien, Ba Dinh, Ha Noi"))
        assert dist_id == 777
        assert ward_code == "1001"
        mock_get.assert_not_called()
        mock_post.assert_not_called()


def test_ghn_resolve_address_khong_nham_so_nha_voi_so_quan(tmp_path: Path, monkeypatch):
    """Đảm bảo số nhà '12 Lê Lợi' không bao giờ bị nhận nhầm thành Quận 12 khi khách ở Quận 1."""
    provider = GHNShippingProvider(token="test-token", shop_id="12345")

    cached_districts = [
        {"DistrictID": 1454, "DistrictName": "Quận 12", "NameExtension": ["Quận 12", "12"]},
        {"DistrictID": 1442, "DistrictName": "Quận 1", "NameExtension": ["Quận 1", "1"]},
    ]
    cached_wards_q1 = [
        {"WardCode": "20101", "WardName": "Phường Bến Nghé", "NameExtension": ["Bến Nghé"]},
    ]
    cached_wards_q12 = [
        {"WardCode": "20120", "WardName": "Phường Tân Thới Hiệp", "NameExtension": ["Tân Thới Hiệp"]},
    ]

    monkeypatch.setattr("agent.shipping.ghn.CACHE_DIR", tmp_path)
    monkeypatch.setattr("agent.shipping.ghn._DISTRICTS_CACHE", cached_districts)
    monkeypatch.setattr("agent.shipping.ghn._WARDS_CACHE", {1442: cached_wards_q1, 1454: cached_wards_q12})

    dist_id, ward_code = asyncio.run(provider._resolve_address("12 Lê Lợi, Phường Bến Nghé, Quận 1, TP.HCM"))
    assert dist_id == 1442  # Bắt buộc phải là Quận 1, không được là 1454 (Quận 12)
    assert ward_code == "20101"


# ===============================================================
# 2. Kiểm thử huỷ vận đơn GHN (huy_van_don)
# ===============================================================

def test_ghn_huy_van_don_thanh_cong():
    provider = GHNShippingProvider(token="valid-token", shop_id="12345")

    mock_resp = httpx.Response(
        status_code=200,
        json={
            "code": 200,
            "message": "Success",
            "data": [{"order_code": "GHN123", "result": True, "message": "OK"}],
        },
        request=httpx.Request("POST", "https://api.ghn.vn"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        ok, msg = asyncio.run(provider.huy_van_don("GHN123", ly_do="Khách đổi ý"))
        assert ok is True
        assert "thành công" in msg.lower()


def test_ghn_huy_van_don_that_bai_khi_hang_tu_choi():
    provider = GHNShippingProvider(token="valid-token", shop_id="12345")

    mock_resp = httpx.Response(
        status_code=200,
        json={
            "code": 200,
            "message": "Success",
            "data": [{"order_code": "GHN123", "result": False, "message": "Đơn đã giao không thể huỷ"}],
        },
        request=httpx.Request("POST", "https://api.ghn.vn"),
    )

    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
        ok, msg = asyncio.run(provider.huy_van_don("GHN123"))
        assert ok is False
        assert "không thể huỷ" in msg


def test_huy_van_don_cho_don_service(monkeypatch):
    from agent import db

    fake_order = {
        "ma_van_don": "MOCK-12345",
        "don_vi_van_chuyen": "mock",
        "conversation_id": None,
    }
    monkeypatch.setattr(db, "fetchrow", AsyncMock(return_value=fake_order))
    monkeypatch.setattr(db, "execute", AsyncMock(return_value=None))
    monkeypatch.setattr(db, "log_event", AsyncMock(return_value=None))

    ok, msg = asyncio.run(huy_van_don_cho_don("AS12345", ly_do="Test"))
    assert ok is True


# ===============================================================
# 3. Kiểm thử API tạo vận đơn thủ công (create-waybill)
# ===============================================================

def test_api_create_waybill(monkeypatch):
    from agent.api.routes import create_waybill_for_order
    from agent import db

    oid = uuid.uuid4()
    order_data = {"ma_don": "AS99999", "trang_thai": "da_chot", "ma_van_don": None}
    monkeypatch.setattr(db, "fetchrow", AsyncMock(return_value=order_data))

    mock_result = CreateWaybillResult(
        ok=True,
        ma_van_don="GHN_NEW_001",
        don_vi="ghn",
        phi_van_chuyen=30000,
        trang_thai_noi_bo=InternalShippingStatus.DELIVERING,
    )
    with patch("agent.shipping.tao_van_don_cho_don", new=AsyncMock(return_value=mock_result)):
        res = asyncio.run(create_waybill_for_order(str(oid)))
        assert res["ok"] is True
        assert res["ma_van_don"] == "GHN_NEW_001"
        assert res["don_vi"] == "ghn"


# ===============================================================
# 4. Kiểm thử duyệt đơn trên Dashboard (approve_order) đồng bộ ERP + GHN
# ===============================================================

def test_api_approve_order_dong_bo_erp_va_ghn(monkeypatch):
    from agent.api.routes import approve_order
    from agent import db
    from agent.erp.day_don import KetQuaDay

    oid = uuid.uuid4()
    order_data = {
        "id": oid,
        "ma_don": "AS88888",
        "khach_ten": "Nguyễn Văn A",
        "khach_sdt": "0987654321",
        "khach_dia_chi": "123 Đường Lê Lợi, Phường Bến Nghé, Quận 1, TP.HCM",
        "items": json.dumps([{"ma": "SKU01", "ten": "Serum", "so_luong": 1, "don_gia": 200000}]),
        "ghi_chu": "",
        "erp_ma_don": None,
        "ma_van_don": None,
    }
    monkeypatch.setattr(db, "fetchrow", AsyncMock(return_value=order_data))
    monkeypatch.setattr(db, "execute", AsyncMock(return_value=None))
    monkeypatch.setattr(db, "log_event", AsyncMock(return_value=None))

    monkeypatch.setattr(settings, "erp_ghi_don", True)
    monkeypatch.setattr(settings, "shipping_tu_dong_tao", True)

    mock_erp_result = KetQuaDay(ket_cuc="xong", erp_ma_don="SO-ERP-001")
    mock_ship_result = CreateWaybillResult(
        ok=True,
        ma_van_don="GHN_AUTO_888",
        don_vi="ghn",
        phi_van_chuyen=25000,
    )

    with patch("agent.erp.day_don.day_don", new=AsyncMock(return_value=mock_erp_result)), \
         patch("agent.shipping.tao_van_don_cho_don", new=AsyncMock(return_value=mock_ship_result)):
        res = asyncio.run(approve_order(str(oid)))
        assert res["ok"] is True
        assert res["trang_thai"] == "da_chot"
        assert res["erp_ma_don"] == "SO-ERP-001"
        assert res["ma_van_don"] == "GHN_AUTO_888"
