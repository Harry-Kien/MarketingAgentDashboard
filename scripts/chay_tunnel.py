"""
Bật tunnel công khai và cập nhật `.env` — một lệnh, không sót bước nào.

    python -m scripts.chay_tunnel

BA CÁI BẪY ĐÃ DÍNH THẬT, SCRIPT NÀY TRÁNH CẢ BA
------------------------------------------------
1. CHẠY CHỒNG TUNNEL. Mỗi `cloudflared tunnel --url` cấp một tên miền
   NGẪU NHIÊN MỚI. Bật hai lần là có hai tên miền, `.env` giữ một cái, và
   cái kia mới là cái đang sống. Đo được: hai tiến trình cloudflared cùng
   chạy, `.env` trỏ vào tunnel đã chết, mọi webhook rơi vào hư không.

2. IPv6 RỚT LIÊN TỤC. Log đầy:

       ERR failed to serve tunnel connection
           error="control stream encountered a failure while serving"
           ip=2606:4700:a8::8
       INF Retrying connection in up to 1s / 4s / 8s

   `2606:4700:...` là địa chỉ IPv6 của Cloudflare. Nhiều mạng ở Việt Nam
   không đi IPv6 ổn định, và cloudflared cứ thử lại mãi. Ép IPv4 là hết.

3. QUÊN CẬP NHẬT `.env`. Tên miền đổi mà `.env` giữ cái cũ thì dashboard
   dựng URL webhook sai — và Zalo vẫn nhận URL ấy, chỉ là không bao giờ
   gọi tới được. Hỏng im lặng.

TÊN MIỀN VẪN ĐỔI MỖI LẦN CHẠY
-----------------------------
`trycloudflare` là tunnel dùng một lần, không đặt tên được. Script cập nhật
`.env` hộ, nhưng URL webhook trong Zalo/Meta Console thì PHẢI DÁN LẠI —
không có cách nào tự động, và không nền tảng nào báo cho bạn biết nó đã
ngừng gọi được.

Chạy thật thì cần tên miền riêng. Script in nhắc nhở đó mỗi lần.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
NHAT_KY = GOC / "tunnel.log"
CONG_APP = 8000
_MAU_DOMAIN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _cloudflared() -> str | None:
    tim = shutil.which("cloudflared")
    if tim:
        return tim
    for p in (
        r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
        r"C:\Program Files\cloudflared\cloudflared.exe",
    ):
        if Path(p).exists():
            return p
    return None


def _app_song() -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{CONG_APP}/healthz", timeout=3
        ) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _giet_tunnel_cu() -> int:
    """
    Tắt mọi cloudflared đang chạy TRƯỚC khi bật cái mới.

    Không tắt thì có hai tên miền cùng sống, `.env` giữ một, và cái kia mới
    là cái Zalo đang gọi tới. Đo được đúng chuyện này.
    """
    if sys.platform == "win32":
        r = subprocess.run(
            ["taskkill", "/F", "/IM", "cloudflared.exe"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return 0 if r.returncode else 1
    r = subprocess.run(["pkill", "-f", "cloudflared"], capture_output=True)
    return 0 if r.returncode else 1


def _doi_env(domain: str) -> None:
    tep = GOC / ".env"
    if not tep.exists():
        print("Không có .env — bỏ qua bước cập nhật.")
        return
    s = tep.read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"(?m)^PUBLIC_BASE_URL=.*$", f"PUBLIC_BASE_URL={domain}", s)
    s = re.sub(
        r"(?m)^WEBHOOK_PUBLIC_URL=.*$", f"WEBHOOK_PUBLIC_URL={domain}/webhook", s
    )
    tep.write_text(s, encoding="utf-8")


def _cho_domain(giay: float = 40.0) -> str | None:
    han = time.time() + giay
    while time.time() < han:
        if NHAT_KY.exists():
            m = _MAU_DOMAIN.search(
                NHAT_KY.read_text(encoding="utf-8", errors="replace")
            )
            if m:
                return m.group(0)
        time.sleep(1.0)
    return None


def _xoa_dem_dns() -> None:
    """
    Xoá bộ nhớ đệm DNS của máy trước mỗi lượt đo.

    ĐÂY LÀ CHỖ KIÊN NHẪN KHÔNG CỨU ĐƯỢC, và bản trước sai vì tưởng nó cứu.

    Tên miền `trycloudflare` vừa được cấp xong nên lượt hỏi DNS đầu tiên
    thường trả về "không có tên miền này". Windows GHI NHỚ câu trả lời phủ
    định ấy. Từ đó mọi lượt sau trong cùng tiến trình đều nhận lại câu trả
    lời đã lưu, không hỏi ra ngoài nữa — nên chờ 60 giây hay 600 giây cũng
    y hệt nhau.

    Đo được: `curl` trượt ở 0,003 giây với mã 6 ("không phân giải được"),
    trong khi `nslookup` cùng lúc trả về đủ bốn địa chỉ. Xoá đệm xong thì
    4/4 lượt đều 200.

    Hỏng thì bỏ qua: không xoá được đệm chỉ làm phép đo kém nhạy, còn làm
    chết cả script vì một lệnh phụ trợ thì tệ hơn nhiều.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(["ipconfig", "/flushdns"],
                           capture_output=True, timeout=10)
        else:
            # Không có lệnh chung cho Linux/macOS, và cũng không cần: hai hệ
            # này không nhớ đệm phủ định ở tầng hệ điều hành như Windows.
            pass
    except (OSError, subprocess.SubprocessError):
        pass


def _thong(domain: str, han_giay: float = 60.0) -> int:
    """
    Số lượt gọi thành công từ Internet, trong hạn `han_giay`.

    ĐỢI ĐỦ LÂU, và đây là chỗ bản đầu sai.

    `cloudflared` in ra tên miền NGAY khi đăng ký được kết nối đầu tiên,
    nhưng mạng biên của Cloudflare cần thêm khoảng 20–30 giây nữa mới định
    tuyến tới nó. Đo ngay sau khi có tên miền thì lượt nào cũng trượt, và
    script kết luận "không thông" cho một tunnel hoàn toàn khoẻ.

    Đo được: lượt 1 trượt, lượt 2–4 đều 200.

    Nên đếm trong một CỬA SỔ THỜI GIAN chứ không đếm theo số lần, và dừng
    sớm ngay khi có hai lượt liền nhau thành công.

    Chờ lâu thôi VẪN CHƯA ĐỦ — xem `_xoa_dem_dns`.
    """
    ok = lien_tiep = 0
    han = time.time() + han_giay
    while time.time() < han:
        _xoa_dem_dns()
        try:
            with urllib.request.urlopen(f"{domain}/healthz", timeout=15) as r:
                if r.status == 200:
                    ok += 1
                    lien_tiep += 1
                    if lien_tiep >= 2:
                        return ok
                else:
                    lien_tiep = 0
        except (urllib.error.URLError, OSError):
            lien_tiep = 0
        time.sleep(3)
    return ok


def main() -> int:
    exe = _cloudflared()
    if not exe:
        print("Không thấy cloudflared. Cài từ:")
        print("  https://developers.cloudflare.com/cloudflare-one/connections/"
              "connect-networks/downloads/")
        return 1

    if not _app_song():
        print(f"Dashboard chưa chạy trên cổng {CONG_APP}. Bật nó trước:")
        print("  python -m uvicorn agent.main:app --port 8000")
        return 1

    n = _giet_tunnel_cu()
    if n:
        print("Đã tắt tunnel cũ đang chạy.")
    NHAT_KY.unlink(missing_ok=True)

    # `--edge-ip-version 4`: xem cái bẫy số 2 ở đầu tệp.
    with open(NHAT_KY, "w", encoding="utf-8") as f:
        subprocess.Popen(
            [exe, "tunnel", "--url", f"http://localhost:{CONG_APP}",
             "--edge-ip-version", "4", "--protocol", "http2"],
            stdout=f, stderr=f,
        )

    print("Đang mở tunnel …")
    domain = _cho_domain()
    if not domain:
        print(f"Không lấy được tên miền sau 40 giây. Xem {NHAT_KY.name}.")
        return 1

    ok = _thong(domain)
    if ok == 0:
        print(f"Tunnel lên nhưng KHÔNG thông từ ngoài. Xem {NHAT_KY.name}.")
        return 1

    _doi_env(domain)
    print(f"\n  {domain}")
    print(f"  Thông từ Internet ({ok} lượt gọi thành công).")
    print("  Đã cập nhật PUBLIC_BASE_URL và WEBHOOK_PUBLIC_URL trong .env.\n")
    print("CÒN HAI VIỆC PHẢI LÀM TAY:")
    print("  1. Khởi động lại dashboard để nó đọc .env mới.")
    print("  2. Dán lại URL webhook vào Zalo/Meta Console — tên miền vừa đổi,")
    print("     và không nền tảng nào báo cho bạn biết nó đã ngừng gọi được.")
    print("\nChạy thật thì nên dùng tên miền riêng: dán một lần, không đổi nữa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
