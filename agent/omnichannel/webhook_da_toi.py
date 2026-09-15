"""
Zalo đã gọi webhook vào tên miền nào — sự thật mặt đất về địa chỉ đã khai.

VÌ SAO PHẢI SUY RA THAY VÌ HỎI
------------------------------
Zalo không có API nào để đọc hay đăng ký địa chỉ webhook của một OA; người
phải vào Console dán tay. Mà `PUBLIC_BASE_URL` ở đây là một tên miền
`trycloudflare` đổi mỗi lần chạy `scripts.khoi_dong`.

Nên mỗi lần khởi động lại mà quên dán lại URL là kênh chết theo kiểu tệ
nhất: OA vẫn gửi đi được, tin khách không vào, và không có gì đỏ — vì xét
riêng từng mảnh thì mảnh nào cũng đúng.

Không hỏi được Zalo thì đọc lịch sử: mỗi webhook QUA ĐƯỢC CHỮ KÝ là một
bằng chứng "địa chỉ này Zalo gọi tới được". Ghi lại tên miền ấy, rồi so với
tên miền hiện tại — lệch nghĩa là URL trong Console đã cũ.

GHI LẠI CHỈ KHI ĐỔI
-------------------
Một lượt UPDATE cho mỗi tin khách là một lượt ghi vô ích vào đường nóng.
Tên miền chỉ đổi khi tunnel đổi, nên so trước rồi mới ghi.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit
from uuid import UUID

KHOA = "webhook_da_toi"

TRANG_KHOP = "khop"
TRANG_LECH = "lech"
TRANG_CHUA_RO = "chua_ro"


def doc_host(url_hoac_host: str) -> str:
    """
    Tên miền trần, đã hạ về chữ thường.

    Nhận cả URL đầy đủ lẫn host trần — vì một đầu là `PUBLIC_BASE_URL`
    (URL), đầu kia là header `Host` của request (host trần).

    Hạ chữ thường vì host không phân biệt hoa thường: so chuỗi thô là báo
    lệch oan, và một cảnh báo sai là một cảnh báo người ta học cách bỏ qua.
    """
    s = (url_hoac_host or "").strip()
    if not s:
        return ""
    if "://" in s:
        s = urlsplit(s).netloc
    elif "/" in s or "." not in s:
        # Không phải URL và cũng không giống tên miền -> không đoán.
        return "" if "." not in s.split("/")[0] else s.split("/")[0].lower()
    # Bỏ `user:pass@` và cổng.
    s = s.rsplit("@", 1)[-1]
    if s.startswith("["):                       # IPv6 dạng [::1]:8000
        s = s.split("]", 1)[0] + "]"
    elif ":" in s:
        s = s.split(":", 1)[0]
    return s.lower()


def _da_toi(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Mảnh `webhook_da_toi` trong metadata, hoặc rỗng nếu hình dạng lạ.

    `metadata` là JSONB người sửa được bằng tay, nên mọi hình dạng đều có
    thể tới đây. Hình dạng lạ phải thành "chưa rõ", không thành traceback.
    """
    if not isinstance(metadata, Mapping):
        return {}
    muc = metadata.get(KHOA)
    return muc if isinstance(muc, Mapping) else {}


def so_dia_chi(
    metadata: Mapping[str, Any] | None, public_base_url: str
) -> tuple[str, str]:
    """
    So tên miền Zalo đã gọi vào với tên miền công khai hiện tại.

    Trả `(trạng thái, lý do đọc được)`.

    CHƯA TỪNG NHẬN LÀ "CHƯA RÕ", KHÔNG PHẢI "ĐỦ". Nhìn từ phía ta, "chưa ai
    nhắn" và "URL khai sai nên bị từ chối hết" giống hệt nhau. Gọi trạng
    thái ấy là đủ chính là xanh giả, và xanh giả thì không ai đi kiểm.
    """
    cu = doc_host(str(_da_toi(metadata).get("host") or ""))
    nay = doc_host(public_base_url)
    if not cu:
        return TRANG_CHUA_RO, (
            "chưa có webhook nào của Zalo tới được — chưa chứng minh được "
            "địa chỉ đã khai trong Zalo Console là đúng")
    if not nay:
        return TRANG_CHUA_RO, "chưa cấu hình địa chỉ công khai để so"
    if cu == nay:
        luc = str(_da_toi(metadata).get("luc") or "")
        return TRANG_KHOP, f"Zalo gọi vào đúng {nay}" + (f" (lần cuối {luc})" if luc else "")
    return TRANG_LECH, (
        f"Zalo đang gọi vào “{cu}”, còn địa chỉ công khai bây giờ là "
        f"“{nay}” — địa chỉ trong Zalo Console đã cũ")


async def ghi_nhan(account_id: UUID, host: str) -> None:
    """
    Ghi lại tên miền Zalo vừa gọi vào — CHỈ KHI nó khác lần trước.

    Gọi từ đường webhook SAU KHI chữ ký đã hợp lệ: chữ ký là thứ chứng minh
    lượt gọi này thật sự từ Zalo. Ghi trước khi kiểm là để người lạ tự khai
    tên miền vào hồ sơ tài khoản.
    """
    ten_mien = doc_host(host)
    if not ten_mien:
        return
    from agent import db

    dong = await db.fetchrow(
        "SELECT metadata FROM channel_accounts WHERE id = $1", account_id)
    if dong is None:
        return
    meta = dong["metadata"]
    if isinstance(meta, str):
        # Dữ liệu cũ còn bản JSONB đã mã hoá hai lần; đọc được cả hai dạng.
        import json
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    if doc_host(str(_da_toi(meta).get("host") or "")) == ten_mien:
        return

    moi = dict(meta if isinstance(meta, Mapping) else {})
    moi[KHOA] = {"host": ten_mien,
                 "luc": datetime.now(timezone.utc).isoformat()}
    await db.execute(
        "UPDATE channel_accounts SET metadata = $2, updated_at = now() "
        "WHERE id = $1", account_id, moi)
    await db.log_event("zalo_oa.webhook_ten_mien_moi", ref_id=account_id,
                       host=ten_mien)
