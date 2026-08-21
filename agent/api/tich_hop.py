"""
Nhúng ZaloCRM và Chatwoot vào thẳng dashboard — một cổng vào duy nhất.

VÌ SAO PHẢI CÓ LỚP NÀY, KHÔNG CHỈ LÀ MỘT THẺ <iframe>
-----------------------------------------------------
Cả hai ứng dụng tự CẤM bị nhúng, và cấm theo hai cách khác nhau:

    ZaloCRM  :3080   X-Frame-Options: DENY        cấm nhúng vào bất kỳ đâu
    Chatwoot :3200   X-Frame-Options: SAMEORIGIN  chỉ cho nhúng nếu cùng origin

Với Chatwoot, proxy qua cổng 8000 làm nó THÀNH cùng origin — nhúng được một
cách hợp lệ, không phá vỡ biện pháp bảo vệ nào. Với ZaloCRM thì `DENY` nghĩa
là nhà phát triển nói "đừng bao giờ nhúng tôi", nên lớp này phải XOÁ header
đó đi.

NÓI RÕ CÁI GIÁ CỦA VIỆC XOÁ HEADER ẤY
-------------------------------------
`X-Frame-Options` chống clickjacking: kẻ xấu nhúng trang thật vào trang giả,
phủ một lớp trong suốt lên trên, và cú bấm tưởng là "đóng quảng cáo" hoá ra
bấm vào "xoá tài khoản" trong trang thật.

Xoá header là tự nhận trách nhiệm đó về mình. Nó chấp nhận được ở đây vì:

  1. Proxy CHỈ chạy cho người đã đăng nhập dashboard (xem `_MO` và middleware
     trong `agent/main.py`) — trang giả không có phiên thì không proxy được.
  2. Cổng 8000 chỉ nghe 127.0.0.1.

Cả hai điều kiện đó mà mất một, lớp này thành lỗ hổng. Đưa dashboard ra
Internet thì PHẢI đọc lại đoạn này.

ĐƯỜNG DẪN TUYỆT ĐỐI — CHỖ MỌI PROXY SPA CHẾT
--------------------------------------------
ZaloCRM và Chatwoot là SPA. Trang HTML tải từ `/tich-hop/chatwoot/` nhưng
bên trong nó xin `/packs/js/app.js` — đường dẫn TUYỆT ĐỐI, đập thẳng vào gốc
cổng 8000, nơi có `StaticFiles` của dashboard đang đợi. Kết quả: 404 hàng
loạt, trang trắng.

Cách chữa ở đây là bám theo `Referer`: một request vào đường lạ mà Referer
trỏ về `/tich-hop/<app>/` thì thuộc về app đó. Hacky, và tôi nói thẳng là
hacky — nhưng nó đúng cho trường hợp này (một người dùng, một máy) và không
cần viết lại HTML/CSS/JS đang chảy qua.

Cách sạch hơn là cho mỗi app một tên miền phụ riêng. Cách đó cần DNS và
chứng chỉ, tức là cần một quyết định hạ tầng — không phải việc của một lớp
proxy.
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import Response
from starlette.websockets import WebSocketDisconnect

from ..config import settings

router = APIRouter(prefix="/tich-hop", tags=["tich-hop"])

TIEN_TO = "/tich-hop"

# Header phía ứng dụng đích chặn nhúng. Xoá hết, kể cả biến thể viết hoa
# khác nhau — HTTP không phân biệt hoa thường nhưng dict Python thì có.
_CHAN_NHUNG = ("x-frame-options", "content-security-policy",
               "content-security-policy-report-only")

# Header thuộc về TẦNG VẬN CHUYỂN của kết nối này, không được chép sang kết
# nối kia. Chép `content-length` sang khi nội dung đã bị giải nén là cách
# nhanh nhất để trình duyệt treo giữa chừng.
_BO_QUA = {"content-encoding", "content-length", "transfer-encoding",
           "connection", "keep-alive", "upgrade"}


def _dich(ten: str) -> str:
    """Địa chỉ gốc của một app. Tên lạ thì 404, không đoán."""
    if ten == "zalocrm":
        return (settings.zalocrm_base_url or "http://127.0.0.1:3080").rstrip("/")
    if ten == "chatwoot":
        return (settings.chatwoot_base_url or "http://127.0.0.1:3200").rstrip("/")
    raise HTTPException(404, f"Không biết ứng dụng {ten!r}")


def ung_dung_tu_referer(referer: str) -> str | None:
    """
    Request vào đường tuyệt đối thuộc về app nào, đoán từ Referer.

    Trả None nếu Referer không trỏ vào proxy — lúc đó request là của
    dashboard, và tuyệt đối KHÔNG được chuyển đi đâu cả.
    """
    if not referer or TIEN_TO not in referer:
        return None
    sau = referer.split(TIEN_TO + "/", 1)[-1]
    ten = sau.split("/", 1)[0].split("?", 1)[0]
    return ten if ten in ("zalocrm", "chatwoot") else None


def _sua_location(gia_tri: str, ten: str, goc: str) -> str:
    """
    Chuyển hướng phải ở LẠI trong proxy.

    Không sửa thì Chatwoot trả `Location: /app/login`, trình duyệt nhảy ra
    gốc cổng 8000, và người dùng rơi khỏi iframe vào giữa dashboard.
    """
    if gia_tri.startswith(goc):
        gia_tri = gia_tri[len(goc):] or "/"
    if gia_tri.startswith("/") and not gia_tri.startswith(TIEN_TO):
        return f"{TIEN_TO}/{ten}{gia_tri}"
    return gia_tri


async def chuyen_tiep(request: Request, ten: str, duong: str) -> Response:
    """Chuyển một request HTTP sang app đích và mang câu trả lời về."""
    goc = _dich(ten)
    url = f"{goc}/{duong.lstrip('/')}"
    if request.url.query:
        url += "?" + request.url.query

    # Host phải là host của app đích. Giữ nguyên `localhost:8000` thì Rails
    # của Chatwoot chặn ngay vì không khớp danh sách host cho phép.
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in {"host", "content-length", "accept-encoding"}
    }
    headers["host"] = goc.split("//", 1)[-1]
    headers["accept-encoding"] = "identity"   # không nén: còn sửa được nội dung

    than = await request.body()
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as http:
            tra = await http.request(request.method, url, headers=headers,
                                     content=than or None)
    except httpx.HTTPError as exc:
        # App đích tắt là chuyện thường (chưa `docker compose up`). Trả một
        # câu người đọc hiểu được, không phải 500 trống trơn trong iframe.
        return Response(
            f"<p style='font:14px system-ui;padding:24px'>Không nối được "
            f"<b>{ten}</b> tại {goc}.<br>{type(exc).__name__}</p>",
            status_code=502, media_type="text/html; charset=utf-8",
        )

    ra = {}
    for k, v in tra.headers.items():
        kl = k.lower()
        if kl in _BO_QUA or kl in _CHAN_NHUNG:
            continue
        if kl == "location":
            v = _sua_location(v, ten, goc)
        ra[k] = v

    return Response(content=tra.content, status_code=tra.status_code,
                    headers=ra, media_type=tra.headers.get("content-type"))


@router.api_route(
    "/{ten}/{duong:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy(request: Request, ten: str, duong: str = "") -> Response:
    return await chuyen_tiep(request, ten, duong)


@router.api_route("/{ten}", methods=["GET", "HEAD"])
async def proxy_goc(request: Request, ten: str) -> Response:
    return await chuyen_tiep(request, ten, "")


# ---------------------------------------------------------------
#  WebSocket — hộp thư Chatwoot sống nhờ nó
# ---------------------------------------------------------------
# Chatwoot dùng ActionCable ở `/cable` để đẩy tin mới về theo thời gian
# thực. Không chuyển tiếp WebSocket thì giao diện vẫn mở được, vẫn đăng nhập
# được, nhưng tin nhắn mới KHÔNG bao giờ tự hiện — người trực phải bấm F5,
# và đó là kiểu hỏng tệ nhất: trông như đang chạy.

async def _bom(doc, ghi) -> None:
    """Đọc một chiều tới khi đứt. Đứt là chuyện bình thường, không phải lỗi."""
    try:
        while True:
            await ghi(await doc())
    except Exception:  # noqa: BLE001
        return


async def cau_websocket(ws: WebSocket, ten: str, duong: str) -> None:
    import asyncio

    import websockets

    goc = _dich(ten).replace("http://", "ws://").replace("https://", "wss://")
    url = f"{goc}/{duong.lstrip('/')}"
    if ws.url.query:
        url += "?" + ws.url.query

    await ws.accept()
    try:
        # Cookie phải đi kèm: ActionCable xác thực bằng chính phiên đăng nhập
        # của Chatwoot, không có cookie thì bắt tay xong là bị đá ra ngay.
        cookie = ws.headers.get("cookie", "")
        async with websockets.connect(
            url, additional_headers={"Cookie": cookie} if cookie else None,
            open_timeout=20, ping_interval=None,
        ) as tren:
            await asyncio.gather(
                _bom(ws.receive_text, tren.send),
                _bom(tren.recv, ws.send_text),
            )
    except WebSocketDisconnect:
        return
    except Exception:  # noqa: BLE001
        # Không để một WebSocket hỏng làm sập tiến trình đang phục vụ khách.
        return
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
