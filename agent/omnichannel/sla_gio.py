"""
Giờ làm việc dùng để TÍNH HẠN SLA (DEV-06).

Hạn được tính trong SQL bằng `sla_han()` (migration 0039) để mọi chỗ đặt hạn
— tạo hội thoại, mở lại — dùng chung một phép tính. Mô-đun này chỉ quyết
định GIỜ MỞ/ĐÓNG truyền vào: lấy từ cùng cấu hình `GIO_LAM_VIEC_*` mà câu
"ngoài giờ, mấy giờ có người" (`agent/core/gio_lam_viec.py`) đang dùng. Hai
nơi đọc hai cấu hình khác nhau là hai giờ mở cửa khác nhau cho cùng một shop.

Chính sách SLA có thể ghi đè bằng `business_hours` {"bat_dau", "ket_thuc"}.
"""
from __future__ import annotations

from agent.config import settings


def gio_sla() -> tuple[int, int]:
    """
    (giờ mở, giờ đóng) theo giờ Việt Nam để tính hạn SLA.

    (0, 24) = đồng hồ chạy liên tục 24/7: khi tắt `SLA_THEO_GIO_LAM_VIEC`
    (mặc định), hoặc khi tắt giờ làm việc nói chung.
    """
    if not settings.sla_theo_gio_lam_viec or not settings.gio_lam_viec_bat:
        return 0, 24
    return int(settings.gio_lam_viec_bat_dau), int(settings.gio_lam_viec_ket_thuc)


def bieu_thuc_han(cot_phut: str, so_mo: int, so_dong: int, *, bang: str = "policy") -> str:
    """
    Biểu thức SQL: hạn = bây giờ + `cot_phut` phút GIỜ LÀM VIỆC.

    `so_mo`, `so_dong` là SỐ THỨ TỰ tham số ($n) mang giờ mở/đóng chung.

    Tắt `SLA_THEO_GIO_LAM_VIEC` thì bỏ qua cả giờ riêng của chính sách
    (`business_hours`): công tắc tắt là tắt hẳn, không nửa vời theo từng
    chính sách. Vẫn dùng đủ hai tham số — Postgres từ chối tham số không ai
    dùng tới.
    """
    if not settings.sla_theo_gio_lam_viec:
        return f"sla_han(now(), {bang}.{cot_phut}, ${so_mo}::int, ${so_dong}::int)"
    return (f"sla_han(now(), {bang}.{cot_phut}, "
            f"sla_gio({bang}.business_hours, 'bat_dau', ${so_mo}::int), "
            f"sla_gio({bang}.business_hours, 'ket_thuc', ${so_dong}::int))")
