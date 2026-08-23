"""
Đọc danh sách nick Zalo đang kết nối trong ZaloCRM.

VÌ SAO PHẢI ĐỌC THẲNG CSDL
--------------------------
Public API của ZaloCRM (`/api/public/*`) có contacts, conversations,
messages, appointments — nhưng KHÔNG có endpoint nào liệt kê nick Zalo,
và `/api/public/conversations` cũng không nói hội thoại thuộc nick nào.
Endpoint nội bộ thì cần JWT của người dùng, tức là phải giữ mật khẩu
đăng nhập ZaloCRM trong hệ thống này — đắt hơn nhiều so với một truy vấn
SELECT.

Nên: mở kết nối CHỈ ĐỌC tới Postgres của ZaloCRM. Không INSERT, không
UPDATE, không sửa một dòng mã nào của ZaloCRM — ràng buộc AGPL-3.0 vẫn
nằm gọn trong container của nó.

Việc GỬI tin vẫn đi qua Public API như cũ. CSDL chỉ dùng để biết có
những nick nào.
"""
from __future__ import annotations


import asyncpg

from ..config import ROOT, settings

_CRM_ENV = ROOT / "ZaloCRM" / ".env"
_pool: asyncpg.Pool | None = None


def _dsn() -> str:
    if settings.zalocrm_db_url:
        return settings.zalocrm_db_url
    # Chưa cấu hình thì dựng từ .env của ZaloCRM — chạy được ngay sau khi
    # cài, không bắt người dùng chép mật khẩu qua lại giữa hai file.
    if not _CRM_ENV.exists():
        return ""
    env = {}
    for line in _CRM_ENV.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    user = env.get("DB_USER", "crmuser")
    pw = env.get("DB_PASSWORD", "")
    port = env.get("DB_PORT", "5434")
    name = env.get("DB_NAME", "zalocrm")
    if not pw:
        return ""
    return f"postgresql://{user}:{pw}@localhost:{port}/{name}"


async def _get_pool() -> asyncpg.Pool | None:
    global _pool
    if _pool is not None:
        return _pool
    dsn = _dsn()
    if not dsn:
        return None
    try:
        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2,
                                          command_timeout=10)
    except (OSError, asyncpg.PostgresError):
        return None
    return _pool


async def danh_sach() -> list[dict]:
    """
    Nick Zalo dùng được, mới kết nối trước.

    Bỏ nick đã lưu trữ (`archived_at`) — chúng vẫn nằm trong bảng nhưng
    gửi qua đó sẽ bị Public API trả 422.
    """
    pool = await _get_pool()
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            "SELECT id, zalo_uid, display_name, phone, status, "
            "       daily_message_cap, last_message_sent_at, last_connected_at "
            "FROM zalo_accounts WHERE archived_at IS NULL "
            "ORDER BY (status = 'connected') DESC, last_connected_at DESC NULLS LAST"
        )
    except asyncpg.PostgresError:
        return []
    return [
        {
            "id": r["id"],
            "ten": r["display_name"] or r["zalo_uid"],
            "zalo_uid": r["zalo_uid"],
            "sdt": r["phone"] or "",
            "trang_thai": r["status"],
            "san_sang": r["status"] == "connected",
            "han_muc_ngay": r["daily_message_cap"],
            "gui_gan_nhat": r["last_message_sent_at"],
        }
        for r in rows
    ]


async def hop_le(account_id: str) -> bool:
    """Nick này có tồn tại và đang kết nối không?"""
    return any(a["id"] == account_id and a["san_sang"] for a in await danh_sach())


async def aclose() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
