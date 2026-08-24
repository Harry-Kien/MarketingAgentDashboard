"""
Tiện ích dùng chung cho các test soi tài liệu.

VÌ SAO NẰM Ở ĐÂY CHỨ KHÔNG CHÉP VÀO TỪNG FILE
---------------------------------------------
`test_claude_md.py` và `test_dua_vao_doanh_nghiep.py` cùng cần một phép
kiểm: "đường dẫn tài liệu này nhắc tới còn sống không". Chép hai bản là tạo
đúng thứ vừa gây ra lỗi trong `agent/main.py` — hai bản sao của một việc,
rồi bản ít người đọc hơn mục đi. Ở đây nó lộ ra ngay khi viết: bản đầu tiên
quên xét thư mục cha, và bản thứ hai thừa hưởng nguyên lỗi ấy.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def duong_dan_con_song(duong: str) -> bool:
    """
    Đường dẫn còn sống: có thật, HOẶC có bản `.example` đi thay.

    Phải chấp nhận vế thứ hai vì repo cố ý không mang theo dữ liệu thật
    (`data/catalog.json`, `data/knowledge/`) — đòi chúng tồn tại là đòi
    đúng thứ đã quyết định không đưa lên, và test sẽ xanh trên máy đã cấu
    hình rồi đỏ trên mọi bản clone sạch.

    `.example` có thể nằm ở BẤT KỲ tầng nào của đường dẫn, không riêng tầng
    cuối. Cả hai dạng dưới đây đều hợp lệ và phải nhận cả hai:

        data/catalog.json                      -> data/catalog.example.json
        data/knowledge/chinh-sach.md           -> data/knowledge.example/chinh-sach.md

    Bỏ sót dạng thứ hai chính là cách bản đầu tiên của hàm này lọt lưới.
    """
    p = Path(duong.rstrip("/"))
    if (ROOT / p).exists():
        return True
    # Thử đổi từng tầng sang bản `.example`, từ tầng cuối ngược lên gốc.
    phan = list(p.parts)
    for i in range(len(phan) - 1, -1, -1):
        goc = Path(phan[i])
        thu = phan.copy()
        thu[i] = f"{goc.stem}.example{goc.suffix}"
        if (ROOT / Path(*thu)).exists():
            return True
    return False
