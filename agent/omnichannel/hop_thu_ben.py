"""
Hộp thư BỀN — tin khách nằm trong Postgres TRƯỚC khi webhook trả 200.

LỖ ĐƯỢC BỊT (rà soát 13.11.2026)
-------------------------------
Mọi webhook (Zalo cá nhân, Zalo OA, Meta, webchat, đường cũ) trả 200 rồi mới
gọi `handle_inbound` trong BackgroundTasks. Hãng nhận 200 là coi như đã giao
xong, không gửi lại. App chết đúng khoảnh khắc ấy — máy ngủ, người canh dựng
lại, deploy — là tin biến mất: CSDL không có dòng nào, không lỗi, không ai
biết. Trên laptop này app khởi động lại 29 lần trong 11 ngày.

LUỒNG MỚI
---------
  webhook  ->  nhan(): INSERT tin_vao (COMMIT)  ->  trả 200
           ->  BackgroundTasks: xu_ly_mot(id)    (nhanh như cũ)
  vòng nền ->  nhặt dòng `cho` quá hạn hoặc `dang_xu_ly` bị bỏ dở (app chết
               giữa chừng) và chạy lại.

CSDL hỏng thì `nhan()` ném lỗi, webhook trả 5xx, hãng TỰ GỬI LẠI — đúng hơn
trả 200 rồi mất tin.

CHẠY LẠI MỘT TIN ĐÃ XỬ LÝ DỞ CÓ AN TOÀN KHÔNG
--------------------------------------------
`handle_inbound` chống trùng theo `dedupe_key` ngay bước đầu (webhook_receipts):
tin đã lưu vào hộp thư thì lần chạy lại dừng ở đó, không trả lời khách lần
hai. Cái giá: nếu app chết SAU khi lưu tin mà TRƯỚC khi AI trả lời, lần chạy
lại không trả lời nữa — nhưng tin đã nằm trong hộp thư, hiện trên dashboard,
và canh gác "khách chờ người" sẽ báo. Mất câu trả lời tự động còn hơn trả lời
hai lần; mất hẳn tin thì không chấp nhận được.

KHÔNG DÙNG THƯ VIỆN HÀNG ĐỢI
----------------------------
PgQueuer, procrastinate, pgmq đều được cân nhắc: cái tự tạo bảng ngoài hệ
migration có checksum, cái đòi driver CSDL thứ hai, cái đòi extension không
có trong image Postgres. Cùng mẫu đã chạy ổn ở outbox (`FOR UPDATE SKIP
LOCKED`, thử lại có giãn cách, trạng thái chết) — một chỗ ít hơn để hỏng.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from agent import db
from agent.channels.base import InboundMessage

log = logging.getLogger("agent.hop_thu_ben")

SO_LAN_TOI_DA = 6
# Dòng `dang_xu_ly` lâu hơn mức này là của một tiến trình đã chết giữa chừng.
# Một lượt AI dài nhất cỡ một phút; mười phút là thừa an toàn.
BO_DO_SAU_GIAY = 600
GIU_XONG_NGAY = 3        # nội dung là lời khách: không giữ lâu hơn cần
GIU_CHET_NGAY = 30       # đủ để người tra lỗi


def tre_lan_sau(so_lan: int) -> int:
    """Giây chờ trước lần thử kế: 10, 20, 40, 80, 160 … tối đa 10 phút."""
    return int(min(10 * 2 ** max(so_lan - 1, 0), 600))


def ra_json(m: InboundMessage) -> dict[str, Any]:
    return {
        "account_id": str(m.account_id), "channel": m.channel,
        "conversation_ref": m.conversation_ref, "customer_ref": m.customer_ref,
        "customer_name": m.customer_name, "text": m.text, "dedupe_key": m.dedupe_key,
        "received_at": m.received_at.isoformat(),
        "attachments": list(m.attachments or []), "meta": dict(m.meta or {}),
    }


def tu_json(d: dict[str, Any]) -> InboundMessage:
    if isinstance(d, str):
        import json
        d = json.loads(d)
    return InboundMessage(
        account_id=UUID(str(d["account_id"])), channel=d["channel"],
        conversation_ref=d["conversation_ref"], customer_ref=d["customer_ref"],
        customer_name=d["customer_name"], text=d["text"], dedupe_key=d["dedupe_key"],
        received_at=datetime.fromisoformat(d["received_at"]),
        attachments=list(d.get("attachments") or []), meta=dict(d.get("meta") or {}),
    )


async def nhan(m: InboundMessage, tasks=None) -> UUID | None:
    """
    Ghi tin vào hộp thư bền (COMMIT ngay), rồi hẹn xử lý trong nền.

    Trả id dòng, hoặc None khi tin này đã có (hãng phát lại). KHÔNG nuốt lỗi
    CSDL: để webhook trả 5xx thì hãng gửi lại.
    """
    r = await db.fetchrow(
        "INSERT INTO tin_vao (dedupe_key, account_id, kenh, payload) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (dedupe_key) WHERE dedupe_key <> '' DO NOTHING RETURNING id",
        m.dedupe_key or "", m.account_id, m.channel, ra_json(m))
    if r is None:
        return None
    if tasks is not None:
        tasks.add_task(xu_ly_mot, r["id"])
    return r["id"]


async def _nhan_viec(id_: UUID) -> dict | None:
    """Giành quyền xử lý một dòng. None = đã có ai giành, hoặc chưa tới lượt."""
    return await db.fetchrow(
        "UPDATE tin_vao SET trang_thai = 'dang_xu_ly', khoa_luc = now(), "
        "so_lan_thu = so_lan_thu + 1, updated_at = now() "
        "WHERE id = $1 AND ((trang_thai = 'cho' AND cho_den <= now()) "
        "  OR (trang_thai = 'dang_xu_ly' AND khoa_luc < now() - make_interval(secs => $2))) "
        "RETURNING id, payload, so_lan_thu, dedupe_key", id_, BO_DO_SAU_GIAY)


async def xu_ly_mot(id_: UUID) -> str:
    """Chạy `handle_inbound` cho một dòng. Trả trạng thái cuối của dòng."""
    from agent.omnichannel import xu_ly_tin_vao

    dong = await _nhan_viec(id_)
    if dong is None:
        return "bo_qua"
    try:
        await xu_ly_tin_vao.handle_inbound(tu_json(dong["payload"]))
    except Exception as exc:  # noqa: BLE001 — một tin hỏng không được làm chết vòng
        loi = f"{type(exc).__name__}: {exc}"[:500]
        if dong["so_lan_thu"] >= SO_LAN_TOI_DA:
            await db.execute(
                "UPDATE tin_vao SET trang_thai = 'chet', loi = $2, khoa_luc = NULL, "
                "updated_at = now() WHERE id = $1", id_, loi)
            await db.log_event("tin_vao.chet", ref_id=id_, so_lan=dong["so_lan_thu"], loi=loi[:200])
            # Tin của khách không vào được hệ thống sau nhiều lần thử: phải có
            # NGƯỜI biết, không chỉ một dòng nhật ký.
            from agent import canh_gac
            await canh_gac.bao_dong(
                f"Một tin khách KHÔNG xử lý được sau {dong['so_lan_thu']} lần thử "
                f"({type(exc).__name__}). Xem bảng tin_vao / nhật ký 'tin_vao.chet'.",
                tieu_de="Tin khách không vào được", muc_do="hong")
            return "chet"
        await db.execute(
            "UPDATE tin_vao SET trang_thai = 'cho', loi = $2, khoa_luc = NULL, "
            "cho_den = now() + make_interval(secs => $3), updated_at = now() WHERE id = $1",
            id_, loi, tre_lan_sau(dong["so_lan_thu"]))
        log.warning("tin_vao %s hỏng lần %s: %s", id_, dong["so_lan_thu"], loi)
        return "cho"
    await db.execute(
        "UPDATE tin_vao SET trang_thai = 'xong', khoa_luc = NULL, loi = NULL, "
        "updated_at = now() WHERE id = $1", id_)
    return "xong"


async def quet_mot_luot(gioi_han: int = 20) -> dict[str, int]:
    """Nhặt tin còn chờ (lỗi trước, hoặc bị bỏ dở khi app chết) và chạy lại."""
    rows = await db.fetch(
        "SELECT id FROM tin_vao WHERE (trang_thai = 'cho' AND cho_den <= now()) "
        "  OR (trang_thai = 'dang_xu_ly' AND khoa_luc < now() - make_interval(secs => $1)) "
        "ORDER BY created_at LIMIT $2", BO_DO_SAU_GIAY, gioi_han)
    dem: dict[str, int] = {}
    for r in rows:
        kq = await xu_ly_mot(r["id"])
        dem[kq] = dem.get(kq, 0) + 1
    return dem


async def don_cu() -> None:
    await db.execute(
        "DELETE FROM tin_vao WHERE (trang_thai = 'xong' AND updated_at < now() - make_interval(days => $1)) "
        "OR (trang_thai = 'chet' AND updated_at < now() - make_interval(days => $2))",
        GIU_XONG_NGAY, GIU_CHET_NGAY)


async def hop_thu_ben_loop(*, worker_id: str, moi_giay: float = 15.0, log_error=None) -> None:
    """
    Vòng nền. Chạy một lượt NGAY lúc khởi động: tin bị bỏ dở lúc app chết
    được nhặt lại sớm nhất có thể (sau BO_DO_SAU_GIAY với dòng `dang_xu_ly`).
    """
    lan = 0
    while True:
        try:
            await quet_mot_luot()
            if lan % 240 == 0:          # ~ mỗi giờ
                await don_cu()
            await db.execute(
                "INSERT INTO worker_heartbeats (worker_name, worker_id, last_seen_at, detail) "
                "VALUES ('inbox-ben', $1, now(), '{}') ON CONFLICT (worker_name) DO UPDATE "
                "SET worker_id = excluded.worker_id, last_seen_at = excluded.last_seen_at",
                worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng nền phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        lan += 1
        await asyncio.sleep(moi_giay)

