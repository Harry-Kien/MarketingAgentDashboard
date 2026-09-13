"""
Luồng lõi đầu-cuối trên APP ĐẦY ĐỦ và Postgres THẬT:

    khách nhắn qua webchat
      -> middleware đăng nhập (bỏ qua vì /webchat không nằm dưới /api)
      -> handle_inbound
      -> tạo khách + hội thoại
      -> chốt agent theo kênh (TẮT)
      -> hội thoại chuyển người + sinh CÔNG VIỆC
      -> KHÔNG gọi model, KHÔNG tốn tiền

VÌ SAO TEST NÀY KHÁC MỌI TEST KHÁC
-----------------------------------
Mọi khối A–F đều có test riêng, và chúng xanh. Nhưng chúng kiểm từng mảnh:
router trần, kho giả, hàm đơn lẻ. Không test nào bơm một tin THẬT qua cổng
THẬT của app THẬT rồi nhìn xem các mảnh có nối nhau không.

Hai lỗi đã lọt qua đúng khe ấy: callback Zalo OA chết ở middleware mà test
router trần không thấy; `merge_preview` nổ ở SQL mà test kho giả không chạy.
Test này dựng `agent.main.app` với lifespan thật — cùng thứ uvicorn dựng.

VÌ SAO AGENT TẮT
----------------
"Agent là tuỳ chọn" là yêu cầu số 3 của chủ dự án. Đường agent tắt phải
KHÔNG IM: tin vào, hội thoại chuyển người, sinh việc. Đó là đường ta kiểm —
và tiện thể nó không gọi model, nên chạy được trong CI mà không tốn tiền.
"""
from __future__ import annotations

import base64
import os
import secrets
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import GOC_WEB, _quan_tri  # noqa: E402,F401


def test_khach_nhan_webchat_agent_tat_thi_chuyen_nguoi_va_sinh_viec(app_that):
    from agent import db

    khach = app_that
    from agent.api.routes import TEN_COOKIE

    # Pool đang mở trong loop của TestClient; các hàm db.* dùng được từ
    # thread test qua portal của TestClient.
    _, token = khach.portal.call(_quan_tri, "sep")
    khach.cookies.set(TEN_COOKIE, token)

    # 1. Quản trị nối một kênh webchat qua API THẬT (credential vào vault).
    r = khach.post("/api/channel-accounts", json={
        "channel": "webchat",
        "display_name": "Web shop",
        "capabilities": {"send_text": True, "receive_message": True},
        "credentials": {"widget_secret": secrets.token_urlsafe(24),
                        "allowed_origins": [GOC_WEB]},
    })
    assert r.status_code == 201, r.text
    tk = r.json()["id"]
    assert khach.post(f"/api/channel-accounts/{tk}/enable").status_code == 200

    # 2. Tắt agent cho ĐÚNG kênh này, có lý do.
    r = khach.post(f"/api/channel-accounts/{tk}/agent",
                   json={"bat": False, "ly_do": "Kênh mới, để người trực trước"})
    assert r.status_code == 200, r.text
    assert r.json()["agent_bat"] is False

    # 3. Khách (không đăng nhập, khác origin dashboard) mở phiên webchat.
    r = khach.post(f"/webchat/{tk}/session", json={},
                   headers={"Origin": GOC_WEB})
    assert r.status_code == 200, r.text
    ve = r.json()["token"]

    # 4. Khách nhắn. 202 = đã xếp hàng; TestClient chạy BackgroundTasks
    #    (handle_inbound) ngay sau khi trả phản hồi.
    r = khach.post(f"/webchat/{tk}/messages",
                   json={"client_message_id": str(uuid4()),
                         "text": "Chị ơi kem này dùng cho da dầu được không?",
                         "visitor_name": "Khách web"},
                   headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ve}"})
    assert r.status_code == 202, r.text

    # 5. Nhìn vào CSDL: mọi mảnh phải NỐI NHAU.
    async def doc():
        conv = await db.fetchrow(
            "SELECT id, status, mode, customer_name FROM conversations "
            "ORDER BY created_at DESC LIMIT 1")
        viec = await db.fetch("SELECT tieu_de, trang_thai, nguon FROM cong_viec")
        # `agent.db` cố ý không có fetchval — dùng fetchrow + bí danh.
        goi_model = (await db.fetchrow(
            "SELECT count(*) AS n FROM messages WHERE coalesce(cost_usd, 0) > 0"))["n"]
        su_kien = [r["kind"] for r in await db.fetch(
            "SELECT kind FROM events ORDER BY created_at")]
        tin = (await db.fetchrow("SELECT count(*) AS n FROM messages"))["n"]
        return conv, viec, goi_model, su_kien, tin

    conv, viec, goi_model, su_kien, tin = khach.portal.call(doc)

    assert conv is not None, "tin vào mà không có hội thoại nào — rơi im lặng"
    assert conv["status"] == "escalated" and conv["mode"] == "human", (
        "agent tắt mà hội thoại không chuyển người")
    assert tin >= 1, "tin khách không được lưu"

    # TẮT KHÔNG PHẢI LÀ IM: phải có việc cho người.
    assert viec, "agent tắt mà không sinh công việc — kênh chết im lặng"
    assert viec[0]["nguon"] == "agent"
    assert viec[0]["trang_thai"] == "moi"

    # Không tốn một đồng.
    assert goi_model == 0, "agent tắt mà vẫn gọi model"
    assert "conversation.escalated" in su_kien


def test_webchat_sai_origin_bi_chan_truoc_khi_vao_he_thong(app_that):
    """
    Cổng công khai duy nhất của hệ thống. Origin lạ phải bị chặn NGAY, không
    tạo phiên, không tạo tin — nếu không thì ai cũng nhét được tin vào hàng
    đợi của nhân viên.
    """
    from agent import db
    from agent.api.routes import TEN_COOKIE

    khach = app_that
    _, token = khach.portal.call(_quan_tri, "sep2")
    khach.cookies.set(TEN_COOKIE, token)
    tk = khach.post("/api/channel-accounts", json={
        "channel": "webchat", "display_name": "Web",
        "credentials": {"widget_secret": "s" * 24, "allowed_origins": [GOC_WEB]},
    }).json()["id"]
    khach.post(f"/api/channel-accounts/{tk}/enable")

    r = khach.post(f"/webchat/{tk}/session", json={},
                   headers={"Origin": "https://ke-la.test"})
    assert r.status_code == 403

    async def dem():
        return (await db.fetchrow("SELECT count(*) AS n FROM conversations"))["n"]
    assert khach.portal.call(dem) == 0
