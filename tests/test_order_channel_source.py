"""
Regression test: đơn hàng tạo từ hội thoại phải lưu đúng nguồn kênh (`orders.channel`)
và trả đúng `channel` + `nen_tang` qua API `/api/orders` & hiển thị đúng `srcBadge`
cho Webchat, Zalo cá nhân, Zalo OA và Facebook/Messenger (không rơi về mặc định 'zalocrm').
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path
import pytest

from agent import db
from agent.api import don_kho
from agent.core import tools

KIEMTHU_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://agent:agent@127.0.0.1:5433/kiemthu",
)


@pytest.mark.parametrize(
    "conv_channel,conv_nen_tang,expected_channel,expected_badge",
    [
        ("webchat", "webchat", "webchat", "Web chat"),
        ("zalo_personal", "zalo_personal", "zalo_personal", "Zalo cá nhân"),
        ("zalo_oa", None, "zalo_oa", "Zalo OA"),
        ("facebook", "facebookpage", "facebook", "Facebook"),
        ("messenger", "facebookpage", "messenger", "Facebook"),
    ],
)
def test_luu_don_moi_luu_dung_kenh_tu_hoi_thoai_va_tra_qua_api(
    monkeypatch, conv_channel, conv_nen_tang, expected_channel, expected_badge
):
    """
    Chạy trực tiếp trên PostgreSQL `kiemthu` (tự dọn sạch sau mỗi case):
    - `_luu_don_moi` đọc `conversations.channel` trong cùng giao dịch và lưu vào `orders.channel`.
    - `GET /api/orders` (`don_kho.list_orders`) trả đúng `channel` và `nen_tang`.
    - `srcBadge(o.channel, o.nen_tang)` hiển thị đúng nhãn tiếng Việt của từng kênh.
    """
    monkeypatch.setattr(db.settings, "database_url", KIEMTHU_URL)

    async def chay():
        await db.init_db()
        acc_id = uuid.uuid4()
        contact_id = uuid.uuid4()
        cp_id = uuid.uuid4()
        conv_id = uuid.uuid4()
        order_id = None
        try:
            await db.execute(
                """
                INSERT INTO channel_accounts (id, channel, external_account_id, display_name, status)
                VALUES ($1, $2, $3, $4, 'active')
                """,
                acc_id, conv_channel, f"test-{acc_id.hex[:8]}", f"Test {conv_channel}",
            )
            await db.execute(
                "INSERT INTO contacts (id) VALUES ($1)",
                contact_id,
            )
            await db.execute(
                """
                INSERT INTO contact_points (id, contact_id, channel_account_id, external_user_id)
                VALUES ($1, $2, $3, $4)
                """,
                cp_id, contact_id, acc_id, f"u-{conv_id.hex[:8]}",
            )
            await db.execute(
                """
                INSERT INTO conversations (id, account_id, contact_id, contact_point_id, channel, nen_tang, external_id, customer_name, customer_ref, status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'open')
                """,
                conv_id, acc_id, contact_id, cp_id, conv_channel, conv_nen_tang, f"ext-{conv_id.hex[:8]}", f"Khach {conv_channel}", f"ref-{conv_id.hex[:8]}",
            )
            kq = await tools._luu_don_moi(
                conversation_id=conv_id,
                khach_ten=f"Khach {conv_channel}",
                khach_sdt="0901234567",
                khach_dia_chi="123 Le Loi, Q1, TP.HCM",
                lines=[{"ma": "SP-TEST", "ten": "SP Test", "don_gia": 100000, "so_luong": 1, "thanh_tien": 100000}],
                tong=100000,
                trang_thai="da_chot",
                ghi_chu="regression channel source",
            )
            assert "row" in kq, f"Lưu đơn thất bại: {kq}"
            order_id = kq["row"]["id"]
            ma_don = kq["row"]["ma_don"]

            # 1. Xác minh trực tiếp trong CSDL `orders.channel` (không phải 'zalocrm')
            row_db = await db.fetchrow("SELECT channel FROM orders WHERE id = $1", order_id)
            db_channel = row_db["channel"]
            assert db_channel == expected_channel
            assert db_channel != "zalocrm"

            # 2. Xác minh qua API `don_kho.list_orders`
            fake_admin = {"id": str(uuid.uuid4()), "quyen": ["don.doc", "hoi_thoai.xem_tat_ca"]}
            orders = await don_kho.list_orders(status="all", limit=20, _quyen=fake_admin)
            found = next((o for o in orders if o["ma_don"] == ma_don), None)
            assert found is not None
            assert found["channel"] == expected_channel
            assert found["nen_tang"] == conv_nen_tang
            return found
        finally:
            if order_id is not None:
                await db.execute("DELETE FROM orders WHERE id = $1", order_id)
            await db.execute("DELETE FROM conversations WHERE id = $1", conv_id)
            await db.execute("DELETE FROM contact_points WHERE id = $1", cp_id)
            await db.execute("DELETE FROM contacts WHERE id = $1", contact_id)
            await db.execute("DELETE FROM channel_accounts WHERE id = $1", acc_id)
            await db.close_db()

    found = asyncio.run(chay())

    # 3. Xác minh Frontend `srcBadge(o.channel, o.nen_tang)` hiển thị đúng nhãn kênh
    js_path = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "03-hoi-thoai.js"
    node_code = (
        "const fs = require('fs');"
        "const src = fs.readFileSync(process.argv[1], 'utf8');"
        "const esc = (s) => String(s ?? '');"
        "const m = src.slice(src.indexOf('const CHANNEL_LABEL'), src.indexOf('const CHO_LAU_PHUT'));"
        "eval(m);"
        "const o = JSON.parse(process.argv[2]);"
        "console.log(srcBadge(o.channel, o.nen_tang));"
    )
    html = subprocess.check_output(
        ["node", "-e", node_code, str(js_path), json.dumps({"channel": found["channel"], "nen_tang": found["nen_tang"]})],
        text=True,
    ).strip()
    assert f">{expected_badge}<" in html, f"Kỳ vọng nhãn '{expected_badge}', nhận được: {html}"
    assert "zalocrm" not in html.lower()


def test_luu_don_moi_khong_gan_cung_zalocrm_khi_khong_co_hoi_thoai(monkeypatch):
    """Khi không có `conversation_id` và truyền `channel`, lưu đúng `channel`; nếu cả hai trống dùng 'khong_ro' chứ không gán cứng 'zalocrm'."""
    monkeypatch.setattr(db.settings, "database_url", KIEMTHU_URL)

    async def chay():
        await db.init_db()
        created = []
        try:
            k1 = await tools._luu_don_moi(
                conversation_id=None, khach_ten="Test", khach_sdt="0901234568",
                khach_dia_chi="123 Test", lines=[{"ma": "SP", "ten": "SP", "don_gia": 10000, "so_luong": 1, "thanh_tien": 10000}],
                tong=10000, trang_thai="cho_duyet", ghi_chu=None, channel="webchat",
            )
            created.append(k1["row"]["id"])
            assert (await db.fetchrow("SELECT channel FROM orders WHERE id = $1", k1["row"]["id"]))["channel"] == "webchat"

            k2 = await tools._luu_don_moi(
                conversation_id=None, khach_ten="Test", khach_sdt="0901234569",
                khach_dia_chi="123 Test", lines=[{"ma": "SP", "ten": "SP", "don_gia": 10000, "so_luong": 1, "thanh_tien": 10000}],
                tong=10000, trang_thai="cho_duyet", ghi_chu=None,
            )
            created.append(k2["row"]["id"])
            ch2 = (await db.fetchrow("SELECT channel FROM orders WHERE id = $1", k2["row"]["id"]))["channel"]
            assert ch2 == "khong_ro"
            assert ch2 != "zalocrm"
        finally:
            for oid in created:
                await db.execute("DELETE FROM orders WHERE id = $1", oid)
            await db.close_db()

    asyncio.run(chay())
