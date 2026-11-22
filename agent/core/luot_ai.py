"""
Mã LƯỢT AI — nối mọi dấu vết của MỘT lần AI xử lý một tin khách.

Phiếu việc mục 18, điểm 4. Một lượt đi qua nhiều tầng: nhận tin, tra tài
liệu (`knowledge.retrieved`), gọi công cụ (`cong_cu.goi`, `order.created`…),
lưới an toàn, rồi trả lời / soạn nháp / chuyển người. Mỗi tầng tự ghi nhật
ký của mình; trước bản này chúng chỉ nối được với nhau bằng cách đoán theo
hội thoại và giờ — hai tin khách sát nhau là không còn biết lần gọi công cụ
nào thuộc câu trả lời nào.

VÌ SAO DÙNG ContextVar, KHÔNG TRUYỀN THAM SỐ
--------------------------------------------
Truyền `luot_id` qua tham số là sửa chữ ký của `respond()`, `run_tool()`,
từng công cụ, từng chỗ ghi nhật ký — và chỗ nào quên truyền là dấu vết đứt
lặng lẽ. `db.log_event` đọc biến ngữ cảnh này và tự gắn mã lượt vào
`detail`, nên mọi nơi ghi nhật ký trong lượt — kể cả chỗ viết sau này —
được nối mà không phải nhớ gì. asyncio chép ngữ cảnh sang task con, nên
`gather`/`create_task` bên trong lượt cũng mang theo.

MỞ LƯỢT Ở ĐÂU: ngay trước lúc AI được gọi (`xu_ly_tin_vao`), không phải lúc
nhận tin. Các nhánh trước đó (tin nhóm, agent bị tắt, khách đòi gặp người,
quy tắc tự động) là HỆ THỐNG quyết định, AI không hề chạy — gắn mã lượt AI
vào chúng là quy cho AI việc nó không làm. Tin khách vẫn nối vào lượt qua
`tin_vao_id`.
"""
from __future__ import annotations

import functools
import uuid
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar

T = TypeVar("T")

_LUOT: ContextVar[dict[str, str] | None] = ContextVar("luot_ai", default=None)


@contextmanager
def mo_luot(hoi_thoai_id: Any, tin_vao_id: Any = None) -> Iterator[str]:
    """Mở một lượt AI cho đến hết khối `with`. Trả mã lượt."""
    luot = {"luot_id": str(uuid.uuid4()), "hoi_thoai_id": str(hoi_thoai_id)}
    if tin_vao_id:
        luot["tin_vao_id"] = str(tin_vao_id)
    the = _LUOT.set(luot)
    try:
        yield luot["luot_id"]
    finally:
        _LUOT.reset(the)


def pham_vi_luot(ham: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """
    Decorator: lượt mở bằng `bat_dau()` bên trong hàm ĐÓNG khi hàm trả về,
    ở mọi lối ra — `return` sớm, ngoại lệ.

    Có cả decorator lẫn `mo_luot` vì `handle_inbound` là một hàm dài có hơn
    chục test đọc mã nguồn của chính nó (thứ tự các bước là ràng buộc). Bọc
    nửa sau vào `with` là thụt lề lại cả trăm dòng hoặc tách hàm — cả hai
    đều làm vỡ những chốt ấy. Decorator đóng lượt mà không đụng thân hàm.

    Không đóng thì sao: worker xử lý tin tuần tự trên CÙNG một task, nên mã
    lượt của tin trước dính sang mọi dòng nhật ký sau đó — tin sau bị quy
    vào lượt AI của tin trước.
    """
    @functools.wraps(ham)
    async def boc(*args: Any, **kwargs: Any) -> T:
        the = _LUOT.set(None)
        try:
            return await ham(*args, **kwargs)
        finally:
            _LUOT.reset(the)
    return boc


def bat_dau(hoi_thoai_id: Any, tin_vao_id: Any = None) -> str:
    """Mở lượt KHÔNG tự đóng — chỉ dùng trong hàm có `@pham_vi_luot`."""
    luot = {"luot_id": str(uuid.uuid4()), "hoi_thoai_id": str(hoi_thoai_id)}
    if tin_vao_id:
        luot["tin_vao_id"] = str(tin_vao_id)
    _LUOT.set(luot)
    return luot["luot_id"]


def hien_tai() -> dict[str, str] | None:
    """Lượt đang mở (bản sao), hoặc None ngoài lượt."""
    luot = _LUOT.get()
    return dict(luot) if luot else None


def gan_vao(detail: dict[str, Any], ref_id: Any = None) -> dict[str, Any]:
    """
    Gắn mã lượt vào `detail` của một sự kiện — KHÔNG đè khoá đã có.

    `hoi_thoai_id` chỉ thêm khi `ref_id` không phải chính hội thoại: sự kiện
    `order.created` có `ref_id` là ĐƠN, không có khoá này thì "mọi việc đã
    làm trong hội thoại này" bỏ sót đúng việc quan trọng nhất là lên đơn.
    """
    luot = _LUOT.get()
    if not luot:
        return detail
    ra = dict(detail)
    ra.setdefault("luot_id", luot["luot_id"])
    if luot.get("tin_vao_id"):
        ra.setdefault("tin_vao_id", luot["tin_vao_id"])
    if str(ref_id or "") != luot["hoi_thoai_id"]:
        ra.setdefault("hoi_thoai_id", luot["hoi_thoai_id"])
    return ra
