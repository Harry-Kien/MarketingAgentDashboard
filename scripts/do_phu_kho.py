"""
Đo độ phủ của kho tri thức — chỗ nào agent chưa trả lời được.

    python -m scripts.do_phu_kho

VÌ SAO CẦN
----------
"Kho đã đủ chưa" là câu hỏi không trả lời được bằng cảm tính. 6.959 từ nghe
nhiều, nhưng nhiều hay ít phụ thuộc vào việc khách hỏi gì.

Script này lấy một tập câu hỏi thật mà khách mỹ phẩm hay hỏi, chạy qua
đúng bộ tìm kiếm agent dùng, rồi chỉ ra câu nào KHÔNG lấy được đoạn nào
hoặc chỉ lấy được đoạn kém liên quan.

Điểm khớp dưới ngưỡng nghĩa là agent sẽ trả lời "chưa có thông tin đó" và
chuyển người — đúng thiết kế, nhưng mỗi lần như vậy là một khách phải chờ.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db  # noqa: E402
from agent.core import rag  # noqa: E402

# Câu hỏi thật, nhóm theo chủ đề. Không lấy từ bộ 56 câu vàng — bộ đó đã
# được dùng để chỉnh hệ thống nên nó đo lại chính mình.
CAU_HOI: dict[str, list[str]] = {
    "sản phẩm & cách dùng": [
        "Serum vitamin C dùng sáng hay tối ạ?",
        "Thoa kem chống nắng bao nhiêu là đủ cho mặt?",
        "Toner AHA dùng mấy lần một tuần?",
        "Mặt nạ đất sét để bao lâu thì rửa?",
        "Kem dưỡng mắt thoa trước hay sau serum?",
    ],
    "kết hợp hoạt chất": [
        "Retinol với vitamin C dùng chung được không?",
        "Niacinamide có kỵ gì không ạ?",
        "Dùng BHA rồi có cần tẩy tế bào chết nữa không?",
        "Thứ tự thoa các bước buổi tối như nào?",
    ],
    "loại da & tình huống": [
        "Da hỗn hợp thiên dầu nên bắt đầu từ đâu?",
        "Da em vừa đổ dầu vừa khô căng là sao ạ?",
        "Mùa hè có cần đổi sản phẩm không?",
        "Ngồi điều hoà cả ngày da khô phải làm sao?",
        "Nam giới lười thì dùng mấy bước là đủ?",
    ],
    "an toàn": [
        "Đang mang thai dùng được sản phẩm nào?",
        "Da em dị ứng thì thử sản phẩm mới thế nào?",
        "Vừa đi laser về có dùng được không?",
        "Trẻ em dùng kem chống nắng này được không?",
    ],
    "chính sách & mua hàng": [
        "Đổi trả trong bao nhiêu ngày?",
        "Ship COD được không ạ?",
        "Có được kiểm hàng trước khi trả tiền không?",
        "Mua combo rẻ hơn mua lẻ bao nhiêu?",
        "Bên mình có xuất hoá đơn không?",
    ],
    "hàng thật & bảo quản": [
        "Làm sao biết hàng chính hãng?",
        "Serum để tủ lạnh được không?",
        "Mở nắp rồi dùng được bao lâu?",
        "Sản phẩm đổi màu có sao không?",
    ],
    "bán hàng": [
        "Sao bên mình đắt hơn chỗ khác vậy?",
        "Dùng bao lâu thì thấy hiệu quả?",
        "Có chương trình khuyến mãi nào không?",
        "Mua nhiều có giảm giá không?",
    ],
}

# Dưới mức này coi như không tìm thấy: agent sẽ nói "chưa có thông tin".
NGUONG_DAT = 0.60
# Trên ngưỡng nhưng dưới mức này là khớp yếu — có đoạn nhưng chưa chắc đúng ý.
NGUONG_TOT = 0.72


async def main() -> int:
    await db.init_db()
    tong = dat = yeu = thieu = 0
    theo_nhom: dict[str, list[int]] = {}
    danh_sach_thieu: list[tuple[str, str, float]] = []

    for nhom, cau_hoi in CAU_HOI.items():
        print(f"\n{nhom.upper()}")
        diem_nhom = []
        for q in cau_hoi:
            ps = await rag.retrieve(q, k=3)
            diem = ps[0].score if ps else 0.0
            nguon = ps[0].doc_title if ps else "—"
            tong += 1
            diem_nhom.append(diem)

            if diem >= NGUONG_TOT:
                dat += 1
                dau = "tốt "
            elif diem >= NGUONG_DAT:
                yeu += 1
                dau = "YẾU "
            else:
                thieu += 1
                dau = "THIẾU"
                danh_sach_thieu.append((nhom, q, diem))
            print(f"  {dau} {diem:.3f}  {q[:48]:50} {nguon[:26]}")
            await asyncio.sleep(0.4)      # giãn nhịp tránh 429
        theo_nhom[nhom] = diem_nhom

    print("\n" + "=" * 68)
    print(f"  Tổng            {tong} câu")
    print(f"  Khớp tốt        {dat}/{tong}  ({dat / tong:.0%})   >= {NGUONG_TOT}")
    print(f"  Khớp yếu        {yeu}/{tong}  ({yeu / tong:.0%})")
    print(f"  THIẾU           {thieu}/{tong}  ({thieu / tong:.0%})   < {NGUONG_DAT}"
          f"   <-- agent sẽ chuyển người")

    print("\n  Điểm trung bình theo nhóm (thấp nhất trước):")
    for nhom, ds in sorted(theo_nhom.items(), key=lambda x: sum(x[1]) / len(x[1])):
        tb = sum(ds) / len(ds)
        thanh = "#" * int(tb * 30)
        print(f"    {nhom:24} {tb:.3f}  {thanh}")

    if danh_sach_thieu:
        print("\n  CÂU KHÔNG CÓ CĂN CỨ TRONG KHO:")
        for nhom, q, d in danh_sach_thieu:
            print(f"    [{nhom}] {q}   ({d:.3f})")

    await db.close_db()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
