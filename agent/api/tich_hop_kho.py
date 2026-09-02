"""
Sổ ứng dụng nhúng: bốn app viết sẵn + app người vận hành tự đăng ký.

RÀO ĐỊA CHỈ Ở ĐÂY LÀ ẢNH GƯƠNG CỦA RÀO TRONG `agent/ky_nang/mang.py`.

    Plugin `goi_api_doc`  MODEL chọn URL  → CHẶN dải mạng nội bộ
    Proxy nhúng           NGƯỜI chọn URL  → BẮT BUỘC dải mạng nội bộ

Nghe như mâu thuẫn, nhưng hai mối nguy khác hẳn nhau.

Với plugin, URL do mô hình sinh ra điền vào, và tiến trình agent ngồi trong
mạng nội bộ — cho nó gọi vào `169.254.169.254` là cho nó đọc thông tin đăng
nhập của máy chủ. Nên chặn nội bộ.

Với proxy nhúng, mục đích CHÍNH LÀ nhúng công cụ nội bộ: Grafana, Metabase,
n8n, Uptime Kuma. Mối nguy ngược lại — cho đăng ký một địa chỉ công khai là
biến dashboard thành máy chuyển tiếp mở: ai có phiên đăng nhập đều gửi được
request ra Internet mang danh máy chủ này, và log của bên nhận chỉ thấy IP
của cửa hàng. Nên bắt buộc nội bộ.

Cùng một câu hỏi — "ai chọn địa chỉ, và chuyện gì xảy ra nếu chọn sai" — ra
hai câu trả lời ngược nhau. Đó là lý do hai rào không dùng chung hàm.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

from agent import db
from agent.config import settings


class LoiUngDung(ValueError):
    """Đăng ký không hợp lệ. Thông điệp nói rõ sửa thế nào."""


# Tên đi thẳng vào đường dẫn `/tich-hop/<ten>/`. Ràng buộc chặt để không có
# ký tự nào cần thoát, và để `..` hay `/` không lọt vào.
_TEN_RE = re.compile(r"^[a-z][a-z0-9-]{1,30}$")

# Bốn app viết sẵn. Không xoá được, không ghi đè được — chúng có xử lý
# riêng trong `_dich()` (đọc `zalocrm_base_url` / `chatwoot_base_url`).
MAC_DINH: dict[str, str] = {
    "zalocrm": "http://127.0.0.1:3080",
    "chatwoot": "http://127.0.0.1:3200",
    "n8n": "http://127.0.0.1:5678",
    "minio": "http://127.0.0.1:9001",
}

NHAN_MAC_DINH = {
    "zalocrm": "ZaloCRM",
    "chatwoot": "Chatwoot",
    "n8n": "n8n",
    "minio": "MinIO",
}

# Trần số app tự đăng ký. Mỗi app là một tab trên dashboard; quá số này thì
# giao diện thành danh sách dài không ai dùng.
TOI_DA = 12

_DEM: dict[str, dict] | None = None


def xoa_dem() -> None:
    """Gọi sau MỌI lần ghi. Cũng dùng trong test để tách các ca khỏi nhau."""
    global _DEM
    _DEM = None


def kiem_dia_chi(dia_chi: str) -> str:
    """
    Kiểm địa chỉ đích. Trả về dạng đã chuẩn hoá, hoặc ném `LoiUngDung`.

    Tách riêng để test được và để dashboard báo lỗi ngay lúc bấm Lưu, chứ
    không phải lúc người dùng mở tab rồi thấy trang trắng.
    """
    dia_chi = (dia_chi or "").strip().rstrip("/")
    if not dia_chi:
        raise LoiUngDung("Thiếu địa chỉ.")
    if len(dia_chi) > 200:
        raise LoiUngDung("Địa chỉ quá 200 ký tự.")

    try:
        u = urlparse(dia_chi)
    except ValueError as exc:
        raise LoiUngDung(f"Địa chỉ không đọc được: {exc}") from exc

    if u.scheme not in ("http", "https"):
        raise LoiUngDung(
            f"Địa chỉ phải bắt đầu bằng http:// hoặc https://, không phải "
            f"{u.scheme or '(trống)'}."
        )
    if u.path not in ("", "/"):
        raise LoiUngDung(
            "Chỉ nhận địa chỉ GỐC, không kèm đường dẫn. "
            f"Dùng {u.scheme}://{u.netloc} thay vì {dia_chi}."
        )
    host = (u.hostname or "").lower()
    if not host:
        raise LoiUngDung("Địa chỉ không có host.")

    # Tra DNS rồi mới xét dải. Kiểm theo tên là kiểm nhầm chỗ — một tên
    # miền công khai hoàn toàn có thể phân giải ra 10.0.0.5, và ngược lại.
    try:
        thong_tin = socket.getaddrinfo(host, u.port or (443 if u.scheme == "https" else 80))
    except OSError as exc:
        raise LoiUngDung(
            f"Không tra được DNS cho {host!r}: {exc}. Ứng dụng đã chạy chưa?"
        ) from exc

    for *_, sockaddr in thong_tin:
        ip = ipaddress.ip_address(sockaddr[0])
        if not (ip.is_private or ip.is_loopback or ip.is_link_local):
            raise LoiUngDung(
                f"{host!r} phân giải ra địa chỉ CÔNG KHAI {ip}. Proxy nhúng "
                "chỉ dành cho công cụ nội bộ — cho phép địa chỉ công khai là "
                "biến dashboard thành máy chuyển tiếp mở, ai có phiên đăng "
                "nhập đều gửi được request ra Internet mang danh máy chủ này."
            )
    return dia_chi


def kiem_ten(ten: str) -> str:
    ten = (ten or "").strip().lower()
    if not _TEN_RE.match(ten):
        raise LoiUngDung(
            f"Tên {ten!r} không hợp lệ. Dùng chữ thường không dấu, số và gạch "
            "ngang, bắt đầu bằng chữ, dài 2–31 ký tự. Ví dụ: grafana."
        )
    if ten in MAC_DINH:
        raise LoiUngDung(
            f"{ten!r} là ứng dụng viết sẵn — không ghi đè được. Đổi tên khác."
        )
    return ten


async def _doc() -> dict[str, dict]:
    global _DEM
    if _DEM is not None:
        return _DEM
    try:
        rows = await db.fetch(
            "SELECT ten, nhan, dia_chi FROM tich_hop_ung_dung WHERE bat"
        )
    except Exception:  # noqa: BLE001
        # CSDL chưa migrate, hoặc đang chạy test không có CSDL. Rơi về "chỉ
        # có bốn app viết sẵn" — đúng trạng thái trước khi có tính năng này.
        _DEM = {}
        return _DEM
    _DEM = {
        r["ten"]: {"nhan": r["nhan"], "dia_chi": r["dia_chi"]} for r in rows
    }
    return _DEM


async def dia_chi_cua(ten: str) -> str | None:
    """Địa chỉ gốc của một app tự đăng ký, hoặc None."""
    return (await _doc()).get(ten, {}).get("dia_chi")


async def ten_hop_le() -> frozenset[str]:
    """
    Mọi tên proxy chấp nhận — viết sẵn cộng tự đăng ký.

    Đây là DANH SÁCH TRẮNG chống SSRF. Chuyển nó xuống CSDL không làm mất
    tính chất ấy: tên lấy từ URL vẫn phải TRA trong danh sách này, không
    bao giờ được ghép thẳng vào địa chỉ đích.
    """
    return frozenset(MAC_DINH) | frozenset(await _doc())


async def liet_ke() -> dict:
    """Toàn cảnh cho dashboard."""
    them = await _doc()
    return {
        "mac_dinh": [
            {
                "ten": t,
                "nhan": NHAN_MAC_DINH.get(t, t),
                "dia_chi": _dia_chi_mac_dinh(t),
                "xoa_duoc": False,
            }
            for t in MAC_DINH
        ],
        "tu_them": [
            {"ten": t, "nhan": v["nhan"], "dia_chi": v["dia_chi"], "xoa_duoc": True}
            for t, v in sorted(them.items())
        ],
        "toi_da": TOI_DA,
    }


def _dia_chi_mac_dinh(ten: str) -> str:
    if ten == "zalocrm" and settings.zalocrm_base_url:
        return settings.zalocrm_base_url.rstrip("/")
    if ten == "chatwoot" and settings.chatwoot_base_url:
        return settings.chatwoot_base_url.rstrip("/")
    return MAC_DINH[ten]


async def luu(ten: str, nhan: str, dia_chi: str, *, boi: str = "staff") -> dict:
    """Kiểm rồi lưu. Sai một chỗ thì không có gì được ghi."""
    ten = kiem_ten(ten)
    dia_chi = kiem_dia_chi(dia_chi)
    nhan = (nhan or ten).strip()[:60]

    dang_co = await _doc()
    if ten not in dang_co and len(dang_co) >= TOI_DA:
        raise LoiUngDung(
            f"Đã đủ {TOI_DA} ứng dụng tự thêm. Xoá bớt cái không dùng."
        )

    await db.execute(
        """
        INSERT INTO tich_hop_ung_dung (ten, nhan, dia_chi, tao_boi)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (ten) DO UPDATE
            SET nhan = EXCLUDED.nhan, dia_chi = EXCLUDED.dia_chi,
                bat = TRUE, sua_luc = now()
        """,
        ten, nhan, dia_chi, boi,
    )
    await db.log_event("tich_hop.luu", actor=boi, ten=ten, dia_chi=dia_chi)
    xoa_dem()
    return {"ten": ten, "nhan": nhan, "dia_chi": dia_chi}


async def xoa(ten: str, *, boi: str = "staff") -> bool:
    if ten in MAC_DINH:
        raise LoiUngDung(f"{ten!r} là ứng dụng viết sẵn — không xoá được.")
    # `db.execute` trả CHUỖI trạng thái kiểu "DELETE 0", không phải số dòng.
    # `bool("DELETE 0")` là True, nên xoá một tên không tồn tại sẽ báo thành
    # công và dashboard hiện "đã xoá" cho một việc chưa từng xảy ra.
    trang_thai = await db.execute(
        "DELETE FROM tich_hop_ung_dung WHERE ten = $1", ten
    )
    so_dong = int(str(trang_thai).rsplit(" ", 1)[-1] or 0)
    if so_dong:
        await db.log_event("tich_hop.xoa", actor=boi, ten=ten)
        xoa_dem()
    return so_dong > 0
