"""
Webhook Zalo OA — cửa vào tin nhắn từ Official Account.

VÌ SAO PHẢI CÓ ĐƯỜNG RIÊNG, KHÔNG DÙNG `/webhook/{kenh}`
--------------------------------------------------------
Đường chung đòi `WEBHOOK_SECRET` qua header `x-webhook-secret` hoặc query
`?token=`. Với Zalo OA cả hai đều sai:

  · Zalo OA Console KHÔNG cho thêm header vào webhook.
  · Nhét secret vào query là ghi một bí mật DÙNG CHUNG cho mọi kênh vào ô
    cấu hình của một bên thứ ba, ở dạng chữ thường. Ai đọc được màn hình
    console ấy là đọc được chìa khoá của cả hệ thống.

Và quan trọng hơn: `?token=` chỉ chứng minh "người gửi biết secret", không
chứng minh "tin này từ Zalo". Zalo đã ký sẵn mọi webhook — dùng chữ ký ấy
là đúng công cụ cho đúng việc.

CHỮ KÝ CỦA ZALO
---------------
Zalo gửi header `X-ZEvent-Signature` dạng `mac=<sha256 hex>`, với:

    mac = sha256(app_id + raw_body + timestamp + oa_secret_key)

`raw_body` là THÂN THÔ, không phải JSON đã parse rồi dump lại: `json.dumps`
đổi khoảng trắng và thứ tự khoá, và chữ ký sẽ lệch. Đây là chỗ mọi bản
hiện thực chữ ký webhook đều hỏng lần đầu.

Mỗi OA có secret key riêng, nên chữ ký được kiểm theo TỪNG tài khoản —
không có bí mật dùng chung nào ở đây cả.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from agent.channels.factory import AccountAdapterFactory
from agent.channels.ten_khach import lam_giau_ten
from agent.config import settings
from agent.omnichannel.account_repository import PostgresAccountRepository
from agent.omnichannel.accounts import Channel
from agent.omnichannel.credential_loader import VaultCredentialLoader
from agent.omnichannel.webhook_da_toi import ghi_nhan as ghi_nhan_webhook_da_toi
from agent.security.credential_vault import CredentialVault, parse_master_keys

router = APIRouter(prefix="/webhook/native/zalo-oa", tags=["zalo-oa-webhook"])


def tinh_mac(app_id: str, raw_body: bytes, timestamp: str, secret_key: str) -> str:
    """
    Chữ ký Zalo kỳ vọng cho một webhook.

    Tách khỏi hàm route để test được mà không cần dựng cả request — và để
    ca kiểm đối chiếu được với ví dụ trong tài liệu Zalo.
    """
    chuoi = app_id + raw_body.decode("utf-8", "replace") + timestamp + secret_key
    return hashlib.sha256(chuoi.encode("utf-8")).hexdigest()


def chu_ky_hop_le(
    header: str, app_id: str, raw_body: bytes, timestamp: str, secret_key: str
) -> bool:
    """
    Header `X-ZEvent-Signature` có khớp không.

    Thiếu bất kỳ mảnh nào -> TỪ CHỐI, không phải cho qua. Đây là lần thứ tư
    cùng một khuôn trong repo: `doc_thach_thuc` của Meta, `kiem_bi_mat_
    webhook` của vận chuyển, và nhánh `webhook_secret` trong `main.py` đều
    từng fail-open. Danh sách rỗng nghĩa là TỪ CHỐI.
    """
    if not header or not app_id or not secret_key or not timestamp:
        return False
    mong_doi = tinh_mac(app_id, raw_body, timestamp, secret_key)
    nhan_duoc = header.split("mac=", 1)[-1].strip()
    # `compare_digest` chứ không `==`: so sánh chuỗi thường thoát ra ở byte
    # đầu khác nhau, và thời gian thoát ra rò rỉ từng byte của chữ ký đúng.
    return hmac.compare_digest(nhan_duoc, mong_doi)


def moc_thoi_gian_co_the(raw_body: bytes, header_ts: str) -> list[str]:
    """
    Các giá trị `timestamp` có thể đã được Zalo dùng để ký, THEO THỨ TỰ.

    THÂN TIN TRƯỚC, HEADER SAU — và thứ tự này là cả vấn đề.

    Tài liệu Zalo và mọi bản hiện thực công khai đều ký bằng trường
    `timestamp` NẰM TRONG THÂN. Zalo không khai header mốc thời gian nào.
    Bản trước đọc header trước, nên chỉ cần một proxy hay tunnel ở giữa
    thêm một header trùng tên là mọi webhook thật bị từ chối 401 — và từ
    phía ta nhìn vào thì "bị từ chối hết" không khác gì "chưa ai nhắn":
    hộp thư trống, không lỗi, không nhật ký.

    Vẫn giữ header làm đường lui, vì kẻ gửi phải có secret key mới ký được
    dù mốc thời gian lấy từ đâu — thêm ứng viên không nới lỏng chốt chặn.

    Thân không phải JSON thì trả danh sách RỖNG, và người gọi phải hiểu đó
    là TỪ CHỐI. Ném lỗi ở đây làm route trả 500, mà Zalo thấy 5xx thì gửi
    lại mãi.
    """
    ra: list[str] = []
    try:
        than = json.loads(raw_body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return []
    if isinstance(than, dict) and than.get("timestamp") is not None:
        ra.append(str(than["timestamp"]))
    if header_ts and header_ts not in ra:
        ra.append(header_ts)
    return ra


def _kho():
    try:
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except ValueError as exc:
        raise HTTPException(503, "Kho credential native chưa sẵn sàng") from exc
    repo = PostgresAccountRepository()
    return repo, VaultCredentialLoader(repo, vault)


@router.post("/{account_id}")
async def zalo_oa_webhook(
    account_id: UUID, request: Request, tasks: BackgroundTasks
) -> JSONResponse:
    """
    Nhận tin từ một OA cụ thể.

    Đường có `account_id` chứ không dùng một đường chung: mỗi OA có secret
    key riêng, nên phải biết OA nào TRƯỚC khi kiểm được chữ ký. Đoán OA từ
    thân tin rồi mới kiểm là để kẻ gửi tự chọn khoá dùng để kiểm chính nó.
    """
    raw = await request.body()

    repo, loader = _kho()
    account = await repo.get(account_id)
    if account is None or account.channel != Channel.ZALO_OA:
        raise HTTPException(404, "Không tìm thấy tài khoản Zalo OA")

    cred = await loader.load(account_id)
    app_id = str(cred.get("app_id") or settings.zalo_oa_app_id or "")
    secret = str(cred.get("secret_key") or settings.zalo_oa_secret_key or "")

    chu_ky = request.headers.get("x-zevent-signature", "")
    ung_vien = moc_thoi_gian_co_the(
        raw, request.headers.get("x-zevent-timestamp", ""))
    if not any(chu_ky_hop_le(chu_ky, app_id, raw, ts, secret)
               for ts in ung_vien):
        raise HTTPException(401, "Chữ ký webhook Zalo OA không hợp lệ")

    # GHI LẠI TÊN MIỀN ZALO VỪA GỌI VÀO — sau chữ ký, không trước.
    #
    # Zalo không có API đọc địa chỉ webhook đã khai, mà `PUBLIC_BASE_URL` ở
    # đây là tên miền tunnel đổi mỗi lần khởi động. Lượt gọi qua được chữ ký
    # là bằng chứng duy nhất "địa chỉ này Zalo tới được"; `scripts.san_sang`
    # so nó với địa chỉ hiện tại để phát hiện URL trong Console đã cũ.
    #
    # Sau chữ ký vì trước chữ ký là để người lạ tự khai tên miền vào hồ sơ
    # tài khoản. Xem agent/omnichannel/webhook_da_toi.py.
    await ghi_nhan_webhook_da_toi(account_id, request.headers.get("host", ""))

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        raise HTTPException(400, "Payload không phải JSON") from None

    factory = AccountAdapterFactory(repo, loader)
    adapter = await factory.create(account_id)

    # ĐÓNG ADAPTER NGAY SAU KHI PARSE, trong `finally`.
    #
    # `__init__` của adapter tạo kèm một `httpx.AsyncClient` có pool kết
    # nối. Adapter này dùng một lần cho một webhook, nên không đóng là rò
    # một client mỗi tin khách — hỏng chậm và im lặng: chạy ngon cả tuần rồi
    # hết file descriptor vào đúng đợt đông khách, dấu vết để lại chẳng liên
    # quan gì tới Zalo.
    #
    # Đóng ở đây an toàn vì chỉ `parse` mới cần adapter này; chiều GỬI đi
    # qua adapter dài hạn của `channels.get_for_account()`.
    try:
        # `parse_nhieu` chứ không `parse`: một payload có thể mang nhiều tin,
        # và lấy đúng một tin nghĩa là những tin sau biến mất trong im lặng.
        tin = (
            adapter.parse_nhieu(payload)
            if hasattr(adapter, "parse_nhieu")
            else [t for t in [adapter.parse(payload)] if t]
        )
        # Webhook Zalo chỉ mang `sender.id`, không mang tên. Không hỏi thì
        # người trực nhìn danh sách hội thoại thấy toàn “Khách”. Làm ở đây,
        # TRƯỚC khi tin vào InboxService — sửa tên sau khi hội thoại đã tạo
        # là thêm một đường ghi nữa mà kết quả kém hơn.
        await lam_giau_ten(adapter, tin)
    finally:
        dong = getattr(adapter, "aclose", None)
        if dong is not None:
            await dong()
    if not tin:
        return JSONResponse({"ok": True, "skipped": "không phải tin văn bản đến"})

    # Trả 200 ngay để Zalo không gửi lại; xử lý ở nền.
    from agent.main import handle_inbound

    for m in tin:
        tasks.add_task(handle_inbound, m)
    return JSONResponse({"ok": True, "queued": len(tin)})
