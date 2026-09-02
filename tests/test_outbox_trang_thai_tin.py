"""
Trạng thái job outbox và trạng thái giao tin là HAI bảng từ vựng khác nhau.

LỖI ĐÃ XẢY RA THẬT
------------------
`mark_failed` ghi thẳng `decision.status.value` vào `messages.delivery_status`.
Job có trạng thái `retry`; cột `messages.delivery_status` thì có CHECK chỉ
nhận `received, draft, queued, sending, sent, delivered, read, failed, dead,
cancelled`.

Nên lần gửi đầu thất bại là: ghi 'retry' -> CheckViolation -> transaction
rollback -> job không rời khỏi `processing` -> worker nhặt lại -> hỏng lại,
vô hạn. Và vì chính lệnh ghi-lại-lỗi bị rollback, **lý do thất bại thật
không bao giờ được lưu**.

Người dùng nhìn thấy: bấm "Duyệt và gửi" thành công, tin đứng ở `queued`,
khách không nhận được gì, dashboard không báo lỗi nào.

Ánh xạ phải tường minh, và mọi giá trị của OutboxStatus đều phải có đích
hợp lệ — thêm trạng thái job mới mà quên ánh xạ là lặp lại đúng lỗi này.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent.omnichannel.outbox import OutboxStatus, trang_thai_giao_tin

ROOT = Path(__file__).resolve().parents[1]


MIGRATION = ROOT / "agent" / "migrations" / "versions" / "0002_native_inbox_outbox.sql"


def _gia_tri_check_cho_phep() -> set[str]:
    """
    Đọc thẳng CHECK trong migration — không chép tay danh sách sang test.

    Chép tay thì ngày ai đó nới ràng buộc, test vẫn xanh với danh sách cũ và
    lại để lọt đúng loại lỗi này.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    khop = re.search(
        r"messages_delivery_status_check\s+CHECK\s*\(\s*delivery_status\s+IN\s*\((.*?)\)",
        sql, re.S | re.I,
    )
    assert khop, "không tìm được ràng buộc messages_delivery_status_check"
    return set(re.findall(r"'([a-z_]+)'", khop.group(1)))


@pytest.mark.parametrize("trang_thai", list(OutboxStatus))
def test_moi_trang_thai_job_deu_anh_xa_ra_gia_tri_hop_le(trang_thai):
    cho_phep = _gia_tri_check_cho_phep()
    assert trang_thai_giao_tin(trang_thai) in cho_phep


def test_retry_khong_bao_gio_ro_ri_ra_cot_tin_nhan():
    """`retry` là chuyện của hàng đợi, không phải trạng thái khách nhìn thấy."""
    assert trang_thai_giao_tin(OutboxStatus.RETRY) != "retry"


def test_dead_va_cancelled_giu_nguyen_nghia():
    assert trang_thai_giao_tin(OutboxStatus.DEAD) == "dead"
    assert trang_thai_giao_tin(OutboxStatus.CANCELLED) == "cancelled"
    assert trang_thai_giao_tin(OutboxStatus.SENT) == "sent"
