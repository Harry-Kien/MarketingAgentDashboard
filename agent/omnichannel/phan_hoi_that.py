"""
Tin nào được tính là ĐÃ PHẢN HỒI khách — luật dùng chung cho mọi mục tiêu SLA.

ĐỊNH NGHĨA (phiếu việc chủ dự án, mục 15 — 22.11.2026)
------------------------------------------------------
PHẢN HỒI THẬT = tin chiều ra đã GỬI TỚI KÊNH (outbox `mark_sent`) với vai:
  * `agent` — câu trả lời của AI (model soạn, kể cả bản nháp người duyệt
    rồi gửi): AI đã thực sự trả lời câu khách hỏi;
  * `staff` — tin nhân viên gõ hoặc gửi tệp.

XÁC NHẬN TỰ ĐỘNG (KHÔNG tính) = mọi tin vai `system`:
  * thông báo minh bạch AI (`thong_bao_ai.gui_neu_chua`);
  * câu báo chuyển người, và câu báo NGOÀI GIỜ "mấy giờ có người"
    (`xu_ly_tin_vao._queue_handover_notice`);
  * tin mẫu tự gửi của quy tắc tự động (`tu_dong`, hành động `gui_mau`);
  * câu hỏi chấm điểm CSAT và lời cảm ơn (`giai_quyet`);
  * báo mã vận đơn (`shipping/service.py`).
Những câu ấy là câu cố định, không trả lời điều khách hỏi. Đếm chúng là
"đạt" hạn phản hồi đầu ở giây thứ hai cho một khách chưa ai trả lời — đúng
kiểu xanh giả mà repo này sợ nhất. Câu báo chuyển người còn tệ hơn: nó tới
ĐÚNG lúc khách bắt đầu chờ người.

Phản hồi SAU CHUYỂN GIAO hẹp hơn: chỉ tin `staff` chốt lượt — AI đã chuyển
thì câu của AI không phải câu khách đang chờ (`sla_chuyen_giao.py`).

Luật đi theo VAI của tin, không theo nội dung: vai được đặt ở đúng một chỗ
lúc xếp hàng (`OutboundService.queue_text(role=...)`), còn nội dung thì ai
cũng sửa được trên dashboard. Test canh từng nguồn xác nhận tự động ở trên
vẫn xếp hàng với vai `system`.
"""
from __future__ import annotations

# Vai của tin được tính là đã phản hồi đầu.
VAI_PHAN_HOI_THAT: frozenset[str] = frozenset({"agent", "staff"})
# Vai của tin chốt lượt chuyển giao.
VAI_PHAN_HOI_SAU_CHUYEN_GIAO: frozenset[str] = frozenset({"staff"})
# Vai của tin xác nhận tự động — không bao giờ tính.
VAI_XAC_NHAN_TU_DONG = "system"


def la_phan_hoi_that(vai: str | None) -> bool:
    return vai in VAI_PHAN_HOI_THAT


def chot_chuyen_giao(vai: str | None) -> bool:
    return vai in VAI_PHAN_HOI_SAU_CHUYEN_GIAO
