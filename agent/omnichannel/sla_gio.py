"""
Giờ làm việc dùng để TÍNH HẠN SLA (DEV-06, mục 15 — 22.11.2026).

Hạn được tính trong SQL bằng `sla_han_lich()` (migration 0062) để mọi chỗ
đặt hạn — tạo hội thoại, mở lại, đổi ưu tiên — dùng chung một phép tính.
Mô-đun này chỉ dựng BIỂU THỨC; lịch truyền vào lấy từ
`sla_muc_tieu.tham_so_han()`: lịch chung (`agent/core/lich_lam_viec.py`)
cho mục tiêu chọn "giờ làm việc", NULL (24/7) cho mục tiêu chọn 24/7.
Cùng lịch ấy trả lời câu "ngoài giờ, mấy giờ có người" — hai nơi đọc hai
cấu hình là hai giờ mở cửa cho cùng một shop.

Giờ riêng của chính sách (`business_hours` {"bat_dau", "ket_thuc"}) chỉ
còn tác dụng khi CHƯA có lịch chung trên dashboard — `sla_lich_chinh_sach`
trong SQL quyết định, theo cờ `gio_rieng` của lịch.
"""
from __future__ import annotations

from agent.omnichannel.sla_muc_tieu import tham_so_han

__all__ = ["bieu_thuc_han", "tham_so_han"]


def bieu_thuc_han(cot_phut: str, so_lich: int, *, bang: str = "policy",
                  moc: str = "now()") -> str:
    """
    Biểu thức SQL: hạn = `moc` (mặc định bây giờ) + `cot_phut` phút tính
    theo lịch `$so_lich`.

    `$so_lich` là CHUỖI JSON của `Lich.json_sql()` hoặc NULL (24/7) — lấy từ
    `tham_so_han()`, mỗi mục tiêu một tham số vì mỗi mục tiêu chọn chế độ
    riêng.

    `moc` chỉ để màn "Thử tính hạn" (`/api/sla/xem-truoc-han`) đặt mốc giả
    định: nó phải đi qua ĐÚNG biểu thức này chứ không chép lại công thức —
    bản chép là bản sẽ lệch khi ai đó sửa luật lịch ở đây.
    """
    return (f"sla_han_lich({moc}, {bang}.{cot_phut}, "
            f"sla_lich_chinh_sach(${so_lich}::text::jsonb, {bang}.business_hours))")
