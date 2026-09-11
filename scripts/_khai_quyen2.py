"""
Vá quyền cho contacts.py và inbox.py — theo TÊN HÀM. TỆP TẠM, xoá ở Việc 10.

Cả 16 endpoint ở hai file này dùng chung đúng một dòng tham số
`user: dict = Depends(bat_buoc_dang_nhap),`, nhưng chia ra sáu quyền khác
nhau. Vá theo dòng tham số là gán một quyền cho tất cả — và cái sai ấy chạy
được, không nổ, chỉ lặng lẽ cho nhân viên làm thứ họ không nên làm.

Chạy: python -m scripts._khai_quyen2
"""
from __future__ import annotations

import re
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
CU = "user: dict = Depends(bat_buoc_dang_nhap),"

# tệp -> {tên hàm: quyền}
BANG: dict[str, dict[str, str]] = {
    "agent/api/contacts.py": {
        "list_contacts": "khach.doc",
        "contact_detail": "khach.doc",
        "preview_contact_merge": "khach.gop",
        "merge_contacts": "khach.gop",
        "unmerge_contact": "khach.gop",
        "add_contact_tag": "khach.sua",
        "add_contact_note": "khach.sua",
        "set_contact_consent": "khach.sua",
        # Yêu cầu xoá dữ liệu cá nhân: cùng quyền với hàng chờ xoá ở
        # `retention.py`, vì đây chính là chỗ tạo ra các mục trong hàng chờ ấy.
        "request_contact_retention": "khach.xoa",
    },
    "agent/api/inbox.py": {
        "list_inbox_conversations": "hoi_thoai.doc",
        "inbox_conversation_detail": "hoi_thoai.doc",
        "inbox_events": "hoi_thoai.doc",
        # Đánh dấu đã đọc là thao tác của người ĐANG đọc, không phải hành vi
        # nhận việc — nên nó đi cùng `.doc`.
        "mark_inbox_read": "hoi_thoai.doc",
        "takeover_conversation": "hoi_thoai.nhan",
        "release_conversation": "hoi_thoai.nhan",
        # Đổi chế độ (agent tự trả lời / người trả lời) là quyết định ai cầm
        # hội thoại này, nên cùng họ với nhận và trả.
        "dat_che_do_conversation": "hoi_thoai.nhan",
    },
}


def main() -> int:
    tong = 0
    for duong, anh_xa in BANG.items():
        tep = GOC / duong
        noi_dung = tep.read_text(encoding="utf-8")

        for ten_ham, quyen in anh_xa.items():
            mau = re.compile(
                r"(async def " + re.escape(ten_ham) + r"\((?:(?!\nasync def).)*?)"
                + re.escape(CU),
                re.DOTALL,
            )
            moi_dong = f'user: dict = Depends(can_quyen("{quyen}")),'
            noi_dung, so = mau.subn(
                lambda m, d=moi_dong: m.group(1) + d, noi_dung, count=1)
            if so != 1:
                print(f"LỆCH {duong}::{ten_ham}: thay được {so} chỗ")
                return 1
            tong += 1

        con = noi_dung.count(CU)
        if con:
            print(f"LỆCH {duong}: còn {con} chỗ chưa khai quyền")
            return 1

        noi_dung = noi_dung.replace(
            "from .routes import bat_buoc_dang_nhap",
            "from .routes import can_quyen",
        )
        tep.write_text(noi_dung, encoding="utf-8")
        print(f"  {duong}: {len(anh_xa)} endpoint")

    print(f"Xong: {tong} endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
