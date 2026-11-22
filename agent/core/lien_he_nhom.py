"""
Contact của NHÓM Zalo không phải một khách hàng (mục 9.7 của bảng việc).

VÌ SAO CÓ CONTACT CHO NHÓM MÀ LẠI PHẢI GIẤU NÓ
---------------------------------------------
Hội thoại nhóm vẫn gắn một `contact_id` (xem `resolve_contact_point` ở
`omnichannel/inbox_service.py`): bỏ trống là đổi hợp đồng của cả chục truy
vấn đọc `contact_id`. Nhưng contact ấy là CẢ NHÓM — không có số điện thoại,
không có loại da, không mua hàng. Để nó lọt vào Customer 360 thì:

  · danh sách khách có "Nhóm Zalo Sỉ Hà Nội" đứng cạnh người thật;
  · "khách mới" ở màn Phân tích đếm nhóm như một người;
  · "khách chưa có chủ" phình lên bằng những nhóm không ai giao được;
  · gộp nhầm nhóm vào hồ sơ một thành viên là trộn lịch sử của cả nhóm
    vào trí nhớ riêng của người đó — đúng thứ `ref_nhom` được dựng để chặn.

Không lỗi nào trong số đó nổ. Nên một chỗ sinh mệnh đề, và mọi truy vấn
"khách" đi qua nó — cùng khuôn với `pham_vi.dieu_kien_khach`.

DẤU NHẬN RA NHÓM
----------------
Một trong hai dấu trên điểm danh tính (`contact_points`) là đủ:
  `metadata.loai = 'nhom'`         ghi từ bản sửa nhóm (inbox_service)
  `external_user_id` bắt đầu `group:`  khoá danh tính nhóm (`ref_nhom`)
Đọc cả hai vì contact nhóm tạo trước khi có `metadata.loai` vẫn mang khoá
`group:`. Thành viên nhóm vẫn là khách riêng theo danh tính CỦA HỌ — không
bị lọc, vì điểm danh tính của họ không mang dấu nào ở trên.
"""
from __future__ import annotations

import re

from agent.channels.base import TIEN_TO_NHOM

# Tiền tố đi thẳng vào mẫu LIKE. Có `%` hay `_` trong đó là mẫu khớp nhầm cả
# khách thường — kiểm lúc import cho nó nổ to thay vì lọc sai lặng lẽ.
if re.search(r"[%_'\\]", TIEN_TO_NHOM):  # pragma: no cover - canh lúc import
    raise RuntimeError(f"TIEN_TO_NHOM có ký tự đặc biệt của LIKE: {TIEN_TO_NHOM!r}")

_BI_DANH = re.compile(r"^[a-z_][a-z0-9_]*$")


def sql_la_nhom(bi_danh: str = "contacts") -> str:
    """
    Biểu thức SQL đúng khi dòng `bi_danh` của bảng `contacts` là một NHÓM.

    `bi_danh` ghép thẳng vào câu SQL nên chỉ nhận tên định danh — một chuỗi
    lạ lọt vào đây là chèn SQL.
    """
    if not _BI_DANH.match(bi_danh):
        raise ValueError(f"Bí danh bảng không hợp lệ: {bi_danh!r}")
    return (
        "EXISTS (SELECT 1 FROM contact_points diem_nhom "
        f"WHERE diem_nhom.contact_id = {bi_danh}.id "
        "AND (diem_nhom.metadata->>'loai' = 'nhom' "
        f"OR diem_nhom.external_user_id LIKE '{TIEN_TO_NHOM}%'))"
    )


def sql_khong_phai_nhom(bi_danh: str = "contacts") -> str:
    return f"NOT {sql_la_nhom(bi_danh)}"
