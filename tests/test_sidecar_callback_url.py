"""
Đường callback của sidecar phải trỏ đúng router, không chỉ đúng host.

LỖI ĐÃ XẢY RA THẬT
------------------
`.env` đặt ZALO_CONTROL_PLANE_URL=http://127.0.0.1:8000 — trông hợp lý, và
sidecar khởi động bình thường, healthz xanh, QR sinh ra được.

Nhưng sidecar dựng đích bằng `${callbackUrl}/${accountId}`, nên nó POST vào
    http://127.0.0.1:8000/<account-id>
trong khi router nằm ở
    /webhook/native/zalo-personal/<account-id>

Kết quả: 404 ở mọi callback. Phiên đăng nhập sau khi quét QR không bao giờ
tới nơi, tài khoản kẹt vĩnh viễn ở `pending:`, và tin khách nhắn vào biến
mất. Không có dòng lỗi nào trên dashboard — sidecar vẫn "khoẻ", app vẫn
"khoẻ", chỉ có sợi dây giữa hai bên là đứt.

Đúng loại hỏng im lặng mà CLAUDE.md cảnh báo: mọi đèn đều xanh.

Test này neo ba thứ vào nhau: mặc định trong mã sidecar, hướng dẫn trong
.env.example, và prefix thật của router.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "connectors" / "zalo-personal-sidecar" / "src" / "server.mjs"


def _prefix_router() -> str:
    src = (ROOT / "agent" / "api" / "zalo_personal_webhook.py").read_text(encoding="utf-8")
    khop = re.search(r'prefix\s*=\s*"([^"]+)"', src)
    assert khop, "không đọc được prefix router zalo-personal"
    return khop.group(1)


def _mac_dinh_sidecar() -> str:
    src = SERVER.read_text(encoding="utf-8")
    khop = re.search(r"ZALO_CONTROL_PLANE_URL\s*\?\?\s*'([^']+)'", src)
    assert khop, "không đọc được mặc định ZALO_CONTROL_PLANE_URL trong sidecar"
    return khop.group(1)


def test_mac_dinh_sidecar_tro_dung_router():
    assert _mac_dinh_sidecar().endswith(_prefix_router())


def test_env_example_huong_dan_dung_duong_day_du():
    """
    Hướng dẫn thiếu đường dẫn thì người cài chép đúng cái sai.

    Giá trị trong .env.example phải là URL ĐẦY ĐỦ tới router, không phải chỉ
    host — vì nó là thứ người ta copy nguyên vào .env.
    """
    src = (ROOT / ".env.example").read_text(encoding="utf-8")
    khop = re.search(r"^ZALO_CONTROL_PLANE_URL=(.*)$", src, re.MULTILINE)
    assert khop, ".env.example phải khai ZALO_CONTROL_PLANE_URL"
    gia_tri = khop.group(1).strip()
    assert gia_tri.endswith(_prefix_router()), (
        f"ZALO_CONTROL_PLANE_URL trong .env.example là {gia_tri!r} — thiếu "
        f"đường dẫn router {_prefix_router()!r}, sidecar sẽ POST vào 404"
    )
