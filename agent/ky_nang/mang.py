"""
Gọi HTTP cho plugin `goi_api_doc` — có rào SSRF.

MỐI NGUY. Plugin loại này để người vận hành nối agent vào một API nội bộ
sẵn có: tra điểm tích luỹ, tra bảo hành, tra lịch hẹn. Nhưng URL do người
gõ, và tiến trình agent ngồi TRONG mạng nội bộ. Một URL trỏ vào
`http://169.254.169.254/…` là đọc được thông tin đăng nhập của máy chủ đám
mây; trỏ vào `http://localhost:5433` là chạm thẳng vào Postgres.

Đó là SSRF, và nó không cần ai cố ý phá: gõ nhầm một địa chỉ nội bộ cũng ra
đúng kết quả ấy.

BỐN RÀO, xếp theo thứ tự chặn được nhiều nhất trước:

  1. Danh sách host cho phép  — quản trị viên phải ghi host vào .env trước
  2. Chặn dải IP nội bộ       — sau khi tra DNS, không phải trước
  3. Không đi theo redirect   — 302 sang địa chỉ nội bộ vô hiệu hoá rào 1
  4. Chỉ GET, có hạn giờ và trần kích thước

Rào 2 phải làm SAU khi tra DNS mới có tác dụng: `evil.com` hoàn toàn có thể
phân giải ra `127.0.0.1`. Chặn theo tên miền là chặn nhầm chỗ.

VẪN CÒN MỘT KHE HỞ, nói thẳng: giữa lúc kiểm IP và lúc httpx tự tra DNS lần
nữa để nối, bản ghi DNS có thể đổi (DNS rebinding). Bịt hẳn thì phải tự nối
tới IP đã kiểm rồi đặt lại header Host, và làm vậy là bỏ luôn việc kiểm
chứng thư TLS. Nên rào số 1 mới là rào chính: danh sách host cho phép nằm
trong `.env`, và không có đường nào sửa nó từ dashboard.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from agent.config import settings

# Trần kích thước phản hồi. Phản hồi đi thẳng vào ngữ cảnh model — một
# endpoint trả về 10MB JSON sẽ đốt sạch trần chi phí hội thoại trong một
# lời gọi, và lỗi ấy hiện ra dưới dạng hoá đơn chứ không phải dấu vết.
KICH_THUOC_TOI_DA = 16_000
HAN_GIAY_TOI_DA = 15.0


class LoiMang(RuntimeError):
    """Không gọi được, hoặc không được phép gọi."""


def _host_duoc_phep() -> frozenset[str]:
    """
    Host cho phép, đọc từ `KY_NANG_HOST_CHO_PHEP` trong .env.

    Mặc định RỖNG. Nghĩa là plugin `goi_api_doc` không chạy được cho tới khi
    quản trị viên chủ động ghi host vào .env — không có host nào được tin
    sẵn. Đây là chỗ duy nhất quyết định agent gọi ra ngoài tới đâu, và nó cố
    ý không sửa được từ dashboard: sửa được từ dashboard thì chiếm được một
    tài khoản quản trị là chiếm được cả đường ra mạng.
    """
    tho = getattr(settings, "ky_nang_host_cho_phep", "") or ""
    return frozenset(h.strip().lower() for h in tho.split(",") if h.strip())


def kiem_url(url: str) -> str:
    """
    Kiểm một URL trước khi gọi. Trả về host đã chuẩn hoá, hoặc ném `LoiMang`.

    Tách riêng khỏi `lay()` để test được mà không cần mạng, và để dashboard
    báo lỗi ngay lúc người vận hành bấm Lưu chứ không phải lúc khách hỏi.
    """
    try:
        u = urlparse(url)
    except ValueError as exc:
        raise LoiMang(f"URL không đọc được: {exc}") from exc

    if u.scheme not in ("http", "https"):
        raise LoiMang(f"Chỉ chấp nhận http/https, không phải {u.scheme!r}.")
    host = (u.hostname or "").lower()
    if not host:
        raise LoiMang("URL không có host.")

    cho_phep = _host_duoc_phep()
    if not cho_phep:
        raise LoiMang(
            "Chưa có host nào được cho phép. Thêm KY_NANG_HOST_CHO_PHEP vào "
            ".env (các host cách nhau bằng dấu phẩy) rồi khởi động lại."
        )
    if host not in cho_phep:
        raise LoiMang(
            f"Host {host!r} không nằm trong KY_NANG_HOST_CHO_PHEP. "
            "Thêm vào .env nếu đúng là host cần gọi."
        )

    # Tra DNS rồi mới kiểm dải IP. Kiểm theo tên miền là vô nghĩa: một tên
    # miền công khai phân giải ra 127.0.0.1 hoàn toàn hợp lệ về mặt DNS.
    try:
        thong_tin = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80))
    except OSError as exc:
        raise LoiMang(f"Không tra được DNS cho {host!r}: {exc}") from exc

    for *_, sockaddr in thong_tin:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise LoiMang(
                f"{host!r} phân giải ra địa chỉ nội bộ {ip}. Agent không được "
                "gọi vào mạng trong — đó là đường đọc trộm thông tin máy chủ."
            )
    return host


async def lay(url: str, han_giay: float = 5.0) -> str:
    """GET một URL đã qua `kiem_url`, trả về phần chữ đã cắt theo trần."""
    kiem_url(url)
    han = max(0.5, min(float(han_giay), HAN_GIAY_TOI_DA))
    try:
        # follow_redirects=False là bắt buộc, không phải tuỳ chọn: một
        # endpoint được phép trả 302 sang http://169.254.169.254 và httpx
        # sẽ ngoan ngoãn đi theo, ra ngoài mọi rào đã dựng ở trên.
        async with httpx.AsyncClient(timeout=han, follow_redirects=False) as c:
            r = await c.get(url, headers={"Accept": "application/json, text/plain"})
    except httpx.HTTPError as exc:
        raise LoiMang(f"Gọi thất bại: {exc}") from exc

    if r.is_redirect:
        raise LoiMang(
            f"Endpoint trả về chuyển hướng {r.status_code}. Không đi theo — "
            "chuyển hướng là đường vòng qua danh sách host cho phép."
        )
    if r.status_code >= 400:
        raise LoiMang(f"Endpoint trả về {r.status_code}.")
    return r.text[:KICH_THUOC_TOI_DA]
