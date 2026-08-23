"""
Sinh bí mật và ghi THẲNG vào .env — không in ra màn hình lần nào.

    python -m scripts.sinh_token MCP_TOKEN
    python -m scripts.sinh_token WEBHOOK_SECRET

VÌ SAO CẦN, KHI ĐÃ CÓ `secrets.token_urlsafe(32)`
-------------------------------------------------
Cách thường dùng:

    python -c "import secrets; print(secrets.token_urlsafe(32))"

in bí mật ra màn hình. Nghe vô hại, nhưng nó tạo ra một chuỗi rò rỉ mà
không ai để ý:

  - nằm trong lịch sử cuộn của terminal, đọc lại được cả ngày sau
  - nằm trong lịch sử lệnh của PowerShell, ghi ra đĩa
  - và — đã xảy ra HAI LẦN trong chính dự án này — lọt vào ảnh chụp màn
    hình rồi được gửi đi

Bí mật lộ rồi thì không rút lại được. Cách duy nhất chắc chắn là **đừng
bao giờ hiện nó ra**: sinh và ghi trong cùng một tiến trình, người vận
hành chỉ thấy dòng "đã đặt".

GIỮ NGUYÊN PHẦN CÒN LẠI CỦA FILE
--------------------------------
Ghi đè cả `.env` là mất mọi giá trị khác. Chỉ thay đúng một dòng; khoá chưa
có thì thêm vào cuối.
"""
from __future__ import annotations

import re
import secrets
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"

# Chỉ cho đặt những khoá thật sự là bí mật sinh ngẫu nhiên được.
# Không có danh sách này thì một lần gõ nhầm tên khoá sẽ ghi đè
# GCP_PROJECT_ID bằng chuỗi ngẫu nhiên, và lỗi đó rất khó lần ra.
CHO_PHEP = {
    "MCP_TOKEN": "token cho ứng dụng ngoài gọi 9 công cụ MCP",
    "WEBHOOK_SECRET": "bí mật xác thực webhook Chatwoot",
}


def dat(khoa: str, dai: int = 32) -> str:
    """Sinh và ghi. Trả về THÔNG BÁO, không bao giờ trả về giá trị."""
    if khoa not in CHO_PHEP:
        return (f"Không đặt được {khoa!r}. Chỉ nhận: "
                + ", ".join(sorted(CHO_PHEP)))
    if not ENV.exists():
        return "Chưa có file .env. Chạy: cp .env.example .env"

    gia_tri = secrets.token_urlsafe(dai)

    # Sao lưu trước khi sửa: .env chứa mọi khoá kết nối của hệ thống, và
    # một lần ghi hỏng là mất hết.
    sao_luu = ENV.with_name(".env.bak")
    shutil.copyfile(ENV, sao_luu)

    noi_dung = ENV.read_text(encoding="utf-8")
    mau = re.compile(rf"^{re.escape(khoa)}=.*$", re.M)
    if mau.search(noi_dung):
        moi = mau.sub(f"{khoa}={gia_tri}", noi_dung, count=1)
        viec = "đã thay"
    else:
        moi = noi_dung.rstrip("\n") + f"\n{khoa}={gia_tri}\n"
        viec = "đã thêm"
    ENV.write_text(moi, encoding="utf-8")

    return (f"{viec} {khoa} ({dai} byte ngẫu nhiên) — "
            f"{CHO_PHEP[khoa]}.\n"
            f"Giá trị KHÔNG được in ra. Đọc bằng cách mở .env, "
            f"và đừng chụp màn hình chỗ đó.\n"
            f"Bản sao lưu file cũ: .env.bak (đã bị .gitignore chặn)")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        print("Khoá đặt được:")
        for k, v in sorted(CHO_PHEP.items()):
            print(f"  {k:16} {v}")
        return 1
    print(dat(sys.argv[1].strip().upper()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
