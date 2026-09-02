"""
Gọi thật vào ERP và in ra thứ nó tìm thấy — không đoán, không suy diễn.

    python -m scripts.thu_erp

VÌ SAO CẦN LỆNH NÀY
-------------------
`agent/erp/erpnext.py` và `odoo.py` được dựng theo tài liệu, chưa từng gọi
vào một instance thật nào. Bốn thứ dưới đây KHÔNG thể biết nếu không gọi
thử, và cả bốn đều hỏng theo kiểu im lặng:

  1. Tên trường ở bản ERP của bạn có đúng như tài liệu không.
  2. Mã sản phẩm nội bộ có khớp mã bên ERP không. Không khớp thì việc hợp
     nhất hai nửa dữ liệu lặng lẽ trả rỗng.
  3. Bảng giá đang dùng có đúng là bảng BÁN LẺ không. Sai thì agent báo giá
     sỉ cho khách lẻ, rất tự tin.
  4. Độ trễ thật — quyết định `ERP_TTL_TON` và `ERP_NGAT_MACH_GIAY`.

CHỈ IN, KHÔNG NGHĨ
------------------
Toàn bộ phép kiểm nằm ở `agent/erp/kiem_ket_noi.py`, dùng chung với
`GET /api/erp/kiem-ket-noi` mà dashboard gọi. File này chỉ tô màu và in.

Hai bộ phép kiểm rời nhau sẽ lệch, và người vận hành nhận hai câu trả lời
khác nhau cho cùng một câu hỏi — tuỳ họ mở terminal hay mở trình duyệt.

Lệnh này CHỈ ĐỌC. Bí mật không bao giờ in ra: đầu ra hay bị dán vào chat.
"""
from __future__ import annotations

import asyncio
import sys

from agent.erp import kiem_ket_noi

_MAU = {
    kiem_ket_noi.TOT: "\033[32m",
    kiem_ket_noi.CANH_BAO: "\033[33m",
    kiem_ket_noi.CHAN: "\033[31m",
}
_TAT = "\033[0m"
_NHAN = {
    kiem_ket_noi.TOT: "đủ",
    kiem_ket_noi.CANH_BAO: "cảnh báo",
    kiem_ket_noi.CHAN: "CHẶN",
}


async def chay() -> int:
    bc = await kiem_ket_noi.kiem_tat_ca()

    print("─" * 66)
    print(f"Thử kết nối kho/ERP — ERP_LOAI={bc['erp_loai']} · "
          f"ghi đơn {'BẬT' if bc['ghi_don'] else 'tắt'}")
    print("─" * 66)

    for m in bc["muc"]:
        mau = _MAU.get(m["trang_thai"], "")
        nhan = _NHAN.get(m["trang_thai"], m["trang_thai"])
        print(f"{mau}[{nhan}]{_TAT} {m['ten']:<14} {m['ghi_chu']}")
        if m.get("goi_y"):
            print(f"             └─ {m['goi_y']}")

    print("─" * 66)
    if bc["san_sang"]:
        print("SẴN SÀNG đọc. Muốn đẩy đơn sang ERP thì đặt ERP_GHI_DON=true,")
        print("và mở ERP xem tận mắt đơn ĐẦU TIÊN trước khi để nó chạy.")
        print()
        print("Con số mặc định ERP_TTL_TON=60 và ERP_NGAT_MACH_GIAY=30 là chỗ")
        print("BẮT ĐẦU. Đo lại vào giờ cao điểm rồi chỉnh, đừng để nguyên vì")
        print("nó tròn.")
        return 0

    print("CHƯA DÙNG ĐƯỢC: còn việc CHẶN ở trên.")
    # Có in CHẶN thì PHẢI thoát khác 0. In chữ đỏ rồi trả 0 là đúng thứ hỏng
    # im lặng mà repo này chống: ai gói lệnh vào script tự động sẽ đọc mã
    # thoát, không đọc màu chữ.
    return 1


def main() -> None:
    sys.exit(asyncio.run(chay()))


if __name__ == "__main__":
    main()
