"""
Trạng thái vận hành thay đổi được lúc chạy — không cần khởi động lại.

`enabled = False` là công tắc ngắt: mọi tin nhắn chuyển thẳng cho người.
Doanh nghiệp sẽ hỏi về nút này trước khi hỏi bất cứ điều gì khác.

VÌ SAO CÓ CẢ BỘ NHỚ LẪN CƠ SỞ DỮ LIỆU
-------------------------------------
`STATE` vẫn nằm trong bộ nhớ, vì `enabled()` và `mode()` bị gọi ở MỌI tin
nhắn và không được phép hỏi CSDL mỗi lần. Nhưng nó được NẠP LÊN từ bảng
`cau_hinh_agent` lúc khởi động, và mọi lần ghi đều xuống bảng ấy.

Trước bản này, `STATE` chỉ có bộ nhớ. Đo được:

    POST /api/runtime {"confidence_floor": 0.9, "mode": "auto"}
    -> 0.9 / auto
    khởi động lại
    -> 0.55 / assist        về mặc định, không một dòng cảnh báo

Tầng API vẫn gọi `db.log_event("runtime.update")`, nên nhật ký kiểm toán
ghi rằng người ta ĐÃ ĐỔI — trong khi giá trị không ở đâu cả. Nhật ký nói
một đằng, hệ thống chạy một nẻo.
"""
from __future__ import annotations

import json

from agent import db
from agent.config import settings

# Khoá nào được phép ghi xuống CSDL và nạp lên lại.
#
# `zalo_account_id` CỐ Ý không nằm đây: nó là con trỏ tới một tài khoản kênh
# cụ thể, và tài khoản ấy có thể bị xoá giữa hai lần khởi động. Nạp lên một
# id đã chết thì agent gửi tin vào hư không — im lặng. Để nó đọc từ cấu hình
# mỗi lần khởi động thì ít nhất nó luôn khớp với `.env` hiện tại.
KHOA_BEN_VUNG = (
    "enabled",
    "mode",
    "confidence_floor",
    "max_cost_per_conversation",
    "tran_chi_phi_ngay_usd",
)

STATE: dict[str, object] = {
    "enabled": settings.agent_enabled,
    "mode": settings.agent_mode,               # assist | auto
    "zalo_account_id": settings.zalocrm_account_id,
    "confidence_floor": settings.confidence_floor,
    "max_cost_per_conversation": settings.max_cost_per_conversation,
    "tran_chi_phi_ngay_usd": settings.tran_chi_phi_ngay_usd,
}

# Giá trị mặc định, chụp lại TRƯỚC khi nạp từ CSDL. Dashboard hiện nó cạnh
# giá trị đang dùng để người vận hành biết mình đã lệch khỏi mặc định bao
# nhiêu — và biết đường quay về.
MAC_DINH: dict[str, object] = dict(STATE)


def enabled() -> bool:
    return bool(STATE["enabled"])


def mode() -> str:
    return str(STATE["mode"])


def update(**fields) -> dict:
    """Đổi trong bộ nhớ. KHÔNG ghi CSDL — dùng `luu()` cho đường có ghi."""
    allowed = set(STATE)
    for k, v in fields.items():
        if k in allowed and v is not None:
            STATE[k] = v
    return dict(STATE)


async def nap() -> dict:
    """
    Nạp cấu hình đã lưu, gọi MỘT LẦN lúc khởi động.

    CSDL chưa migrate thì giữ nguyên mặc định và đi tiếp: máy vừa clone phải
    chạy được, và một bảng chưa có không phải lý do để agent không khởi động.
    """
    try:
        rows = await db.fetch("SELECT khoa, gia_tri FROM cau_hinh_agent")
    except Exception:  # noqa: BLE001
        return dict(STATE)

    for r in rows:
        khoa = r["khoa"]
        if khoa not in KHOA_BEN_VUNG:
            continue
        gt = r["gia_tri"]
        if isinstance(gt, str):
            try:
                gt = json.loads(gt)
            except ValueError:
                continue
        STATE[khoa] = gt
    return dict(STATE)


async def luu(fields: dict, *, boi: str = "staff") -> dict:
    """
    Đổi VÀ ghi xuống CSDL.

    Ghi trước, đổi bộ nhớ sau. Ngược lại thì ghi hỏng để lại một tiến trình
    đang chạy giá trị mới trong khi CSDL giữ giá trị cũ — và lần khởi động
    kế tiếp lặng lẽ quay về cái cũ, đúng lỗi mà cả tệp này sinh ra để sửa.
    """
    ghi = {k: v for k, v in fields.items()
           if k in KHOA_BEN_VUNG and v is not None}
    for k, v in ghi.items():
        await db.execute(
            """
            INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi)
            VALUES ($1, $2::jsonb, $3)
            ON CONFLICT (khoa) DO UPDATE
                SET gia_tri = EXCLUDED.gia_tri, sua_boi = EXCLUDED.sua_boi,
                    sua_luc = now()
            """,
            k, json.dumps(v), boi,
        )
    return update(**fields)


async def dat_lai_mac_dinh(*, boi: str = "staff") -> dict:
    """
    Xoá cấu hình đã lưu và quay về mặc định của `.env`.

    XOÁ ĐÚNG NHỮNG KHOÁ CỦA MÌNH, không xoá cả bảng.

    Bản đầu chạy `DELETE FROM cau_hinh_agent` trần. Bảng ấy là kho khoá–giá
    trị dùng chung, nên mọi thứ lưu thêm vào sau này — ví dụ xác nhận bảng
    giá — bị quét sạch khi ai đó bấm "Quay về mặc định" cho một việc hoàn
    toàn khác. Nút ấy hứa đặt lại BỐN thiết lập agent, không hứa xoá thứ
    người khác vừa xác nhận tuần trước.
    """
    await db.execute(
        "DELETE FROM cau_hinh_agent WHERE khoa = ANY($1)",
        list(KHOA_BEN_VUNG),
    )
    for k in KHOA_BEN_VUNG:
        STATE[k] = MAC_DINH[k]
    await db.log_event("runtime.dat_lai_mac_dinh", actor=boi)
    return dict(STATE)


# Hội thoại agent đang soạn trả lời — dashboard dùng để vẽ bong bóng "đang gõ".
BUSY: set[str] = set()


def mark_busy(conversation_id) -> None:
    BUSY.add(str(conversation_id))


def clear_busy(conversation_id) -> None:
    BUSY.discard(str(conversation_id))


def is_busy(conversation_id) -> bool:
    return str(conversation_id) in BUSY
