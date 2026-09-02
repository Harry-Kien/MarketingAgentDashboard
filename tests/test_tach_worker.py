"""
Vòng lặp nền chỉ được chạy ở tiến trình ĐƯỢC GIAO chạy chúng.

VÌ SAO
------
`lifespan` khởi động outbox worker, SLA monitor, auto-routing, scheduler,
dọn dữ liệu, canh gác và backup — tất cả vô điều kiện. Chạy Uvicorn với
`--workers 4` là mỗi tiến trình dựng một bộ đầy đủ.

Outbox worker chịu được: nó claim job bằng `FOR UPDATE SKIP LOCKED`.
Backup loop thì KHÔNG: bốn `pg_dump` chạy song song trên cùng một CSDL vừa
tốn I/O vừa có thể sinh bản sao lưu cắt dở — mà bản sao lưu hỏng chỉ lộ ra
đúng lúc cần phục hồi.

Nên phải chia vai rõ: tiến trình `api` phục vụ HTTP, tiến trình `worker`
chạy vòng nền. Một biến môi trường, hai vai, không cái nào đoán.
"""
from __future__ import annotations

from agent.main import nen_chay_vong_nen


class _Cau_hinh:
    def __init__(self, vai: str):
        self.vai_tro_tien_trinh = vai


def test_mac_dinh_chay_ca_hai_de_may_le_van_dung_duoc():
    """Một máy một tiến trình là cách chạy phổ biến nhất; đừng bắt cấu hình thêm."""
    assert nen_chay_vong_nen(_Cau_hinh("tat_ca")) is True


def test_vai_api_khong_chay_vong_nen():
    assert nen_chay_vong_nen(_Cau_hinh("api")) is False


def test_vai_worker_chay_vong_nen():
    assert nen_chay_vong_nen(_Cau_hinh("worker")) is True


def test_vai_la_khong_duoc_am_tham_chay_vong_nen():
    """Gõ sai tên vai thì fail closed — thà không chạy còn hơn chạy trùng."""
    assert nen_chay_vong_nen(_Cau_hinh("wroker")) is False
