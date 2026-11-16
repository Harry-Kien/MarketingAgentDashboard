"""
`visitor_id` do MÁY CHỦ cấp — biết visitor_id của khách khác không đủ để đọc
hội thoại của họ.

Rà soát 16.11.2026: `POST /webchat/{acc}/session` nhận `visitor_id` từ thân
request rồi ký vé cho nó; vé đọc được `/history` và `/events`. Origin chặn
được trình duyệt, không chặn được curl. Giờ visitor_id cũ chỉ được giữ khi
kèm chữ ký máy chủ đã cấp — và widget vẫn giữ được lịch sử khi tải lại trang.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.api import webchat  # noqa: E402

GOC = "https://shop.vi-du.vn"
BI_MAT = "widget-secret-" + "k" * 32


@pytest.fixture
def khach(monkeypatch):
    async def cred(account_id):
        return None, {"widget_secret": BI_MAT, "allowed_origins": [GOC]}

    monkeypatch.setattr(webchat, "_account_credentials", cred)
    webchat.GH_PHIEN_THEO_IP._dem.clear()
    app = FastAPI()
    app.include_router(webchat.router)
    return TestClient(app)


def _phien(k, acc, body: dict) -> dict:
    r = k.post(f"/webchat/{acc}/session", json=body, headers={"Origin": GOC})
    assert r.status_code == 200, r.text
    return r.json()


def test_visitor_id_nan_nhan_khong_kem_chu_ky_thi_bi_bo_qua(khach):
    acc = uuid4()
    nan_nhan = _phien(khach, acc, {})
    ke_xau = _phien(khach, acc, {"visitor_id": nan_nhan["visitor_id"]})
    assert ke_xau["visitor_id"] != nan_nhan["visitor_id"]
    claims = webchat.verify_widget_token(ke_xau["token"], secret=BI_MAT, account_id=acc, origin=GOC)
    assert claims["visitor_id"] != nan_nhan["visitor_id"], "vé đọc được lịch sử người khác"


def test_chu_ky_sai_hay_cua_cua_hang_khac_cung_bi_bo_qua(khach):
    acc, khac = uuid4(), uuid4()
    nan_nhan = _phien(khach, acc, {})
    gia = _phien(khach, acc, {"visitor_id": nan_nhan["visitor_id"],
                              "visitor_sig": nan_nhan["visitor_sig"][:-2] + "AA"})
    assert gia["visitor_id"] != nan_nhan["visitor_id"]
    # Chữ ký gắn với account: mang sang cửa hàng khác không dùng được.
    o_khac = _phien(khach, khac, {"visitor_id": nan_nhan["visitor_id"],
                                  "visitor_sig": nan_nhan["visitor_sig"]})
    assert o_khac["visitor_id"] != nan_nhan["visitor_id"]


def test_tai_lai_trang_kem_chu_ky_thi_giu_lich_su(khach):
    """Vế còn lại: siết mà làm mất lịch sử mỗi lần F5 là hỏng kiểu khác."""
    acc = uuid4()
    lan_dau = _phien(khach, acc, {})
    lan_sau = _phien(khach, acc, {"visitor_id": lan_dau["visitor_id"],
                                  "visitor_sig": lan_dau["visitor_sig"]})
    assert lan_sau["visitor_id"] == lan_dau["visitor_id"]
    assert lan_sau["visitor_sig"] == lan_dau["visitor_sig"]


def test_widget_gui_va_cat_chu_ky():
    js = (ROOT / "dashboard" / "widget.js").read_text(encoding="utf-8")
    assert "visitor_sig: stored.visitorSig" in js
    assert "visitorSig: data.visitor_sig" in js
