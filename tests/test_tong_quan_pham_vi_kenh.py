"""
`/api/overview` phải lọc theo kênh được giao, như mọi màn hội thoại khác.

ĐO ĐƯỢC 16.11.2026: màn inbox, `GET /conversations` và chi tiết hội thoại
đều lọc theo `account_memberships`, nhưng overview thì không. Nhân viên chỉ
được giao kênh A vẫn thấy số chờ của kênh B, và băng ca trực (tooltip ở
thanh trên cùng) hiện TÊN KHÁCH kênh B. Lớp lọc ở danh sách thành lớp sơn.

Chạy trên app thật + Postgres thật (fixture `app_that`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat,
    _khach_nhan,
    _nhan_vien_moi,
    _quan_tri_vao,
    _them_thanh_vien,
)


def test_overview_chi_dem_va_hien_khach_kenh_duoc_giao(app_that):
    qt = _quan_tri_vao(app_that)
    kenh_a = _kenh_webchat(qt, "Web A")
    kenh_b = _kenh_webchat(qt, "Web B")
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, kenh_a, lan_id)

    _khach_nhan(app_that, kenh_a, "Khách Kênh A", "cho em hỏi giá")
    _khach_nhan(app_that, kenh_b, "Khách Bí Mật B", "shop ơi")

    r = lan.get("/api/overview")
    assert r.status_code == 200, r.text
    o = r.json()
    ten = {t["customer"] for t in o["tape"]}
    assert "Khách Kênh A" in ten
    assert "Khách Bí Mật B" not in ten, "băng ca trực lộ tên khách kênh không được giao"
    assert o["conversations"]["total"] == 1

    # Quản trị (xem mọi kênh) vẫn thấy cả hai — lọc không được làm mù người
    # có quyền, nếu không đây là xanh nhờ trả rỗng.
    o_qt = qt.get("/api/overview").json()
    ten_qt = {t["customer"] for t in o_qt["tape"]}
    assert {"Khách Kênh A", "Khách Bí Mật B"} <= ten_qt
    assert o_qt["conversations"]["total"] == 2


def test_nhan_vien_khong_thuoc_kenh_nao_khong_thay_gi(app_that):
    qt = _quan_tri_vao(app_that)
    kenh = _kenh_webchat(qt, "Web C")
    _, minh = _nhan_vien_moi(qt, "minh")
    _khach_nhan(app_that, kenh, "Khách Kênh C", "xin chào")

    o = minh.get("/api/overview").json()
    assert o["tape"] == []
    assert o["conversations"]["total"] == 0
