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
CHATWOOT_ENV = ROOT / ".env.chatwoot"

# Chỉ cho đặt những khoá thật sự là bí mật sinh ngẫu nhiên được.
# Không có danh sách này thì một lần gõ nhầm tên khoá sẽ ghi đè
# GCP_PROJECT_ID bằng chuỗi ngẫu nhiên, và lỗi đó rất khó lần ra.
CHO_PHEP = {
    "MCP_TOKEN": "token cho ứng dụng ngoài gọi 9 công cụ MCP",
    "WEBHOOK_SECRET": "bí mật xác thực webhook Chatwoot",
    # Chuỗi ta TỰ ĐẶT rồi dán y hệt sang ô "Verify Token" bên Meta. Chỉ
    # dùng cho lần bắt tay đầu tiên, nhưng vẫn phải ngẫu nhiên: đoán được
    # nó là người lạ nối được webhook của họ vào endpoint của ta.
    "MESSENGER_VERIFY_TOKEN": "chuỗi bắt tay webhook Facebook Messenger",
    "CHATWOOT_WEBHOOK_SECRET": "bí mật ký HMAC cho webhook Chatwoot",
    # Ký HMAC hai chiều giữa control plane và sidecar Zalo cá nhân. Cùng một
    # chuỗi phải nằm ở HAI nơi: biến môi trường của tiến trình sidecar, và
    # credential `sidecar_secret` của tài khoản trong vault. Lệch nhau thì
    # mọi lời gọi bị từ chối 401 mà không nói vì sao.
    "ZALO_SIDECAR_SECRET": "bí mật ký HMAC giữa app và sidecar Zalo cá nhân",
    # Nằm trong URL webhook ta khai với hãng vận chuyển. GHN không ký
    # webhook, nên đây là thứ duy nhất phân biệt hãng gọi với người lạ gọi.
    # Đoán được nó là đánh dấu được đơn "hoàn về" — và hoàn về thì hệ thống
    # tự cộng hàng lại vào kho.
    "SHIPPING_WEBHOOK_SECRET": "bí mật trong URL webhook hãng vận chuyển",
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

    dong_bo = ""
    if khoa == "CHATWOOT_WEBHOOK_SECRET" and CHATWOOT_ENV.exists():
        # Chatwoot ký bằng CW_WEBHOOK_SECRET, còn Agent kiểm bằng
        # CHATWOOT_WEBHOOK_SECRET. Hai tên khác nhau nhưng bắt buộc cùng
        # giá trị; bắt người vận hành copy tay là tạo một lỗi 401 rất khó
        # nhìn ra, và còn khuyến khích mở secret trên màn hình.
        sao_luu_cw = CHATWOOT_ENV.with_name(".env.chatwoot.bak")
        shutil.copyfile(CHATWOOT_ENV, sao_luu_cw)
        noi_dung_cw = CHATWOOT_ENV.read_text(encoding="utf-8")
        mau_url = re.compile(r"^(CW_WEBHOOK_URL=[^?\r\n]+)(?:\?[^\r\n]*)?$", re.M)
        noi_dung_cw = mau_url.sub(r"\1", noi_dung_cw)
        mau_cw = re.compile(r"^CW_WEBHOOK_SECRET=.*$", re.M)
        if mau_cw.search(noi_dung_cw):
            moi_cw = mau_cw.sub(f"CW_WEBHOOK_SECRET={gia_tri}", noi_dung_cw, count=1)
        else:
            moi_cw = noi_dung_cw.rstrip("\n") + f"\nCW_WEBHOOK_SECRET={gia_tri}\n"
        CHATWOOT_ENV.write_text(moi_cw, encoding="utf-8")
        dong_bo = "\nĐã đồng bộ an toàn sang .env.chatwoot; giá trị không được in."

    return (f"{viec} {khoa} ({dai} byte ngẫu nhiên) — "
            f"{CHO_PHEP[khoa]}.\n"
            f"Giá trị KHÔNG được in ra. Đọc bằng cách mở .env, "
            f"và đừng chụp màn hình chỗ đó.\n"
            f"Bản sao lưu file cũ: .env.bak (đã bị .gitignore chặn){dong_bo}")


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
