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

HAI CHẾ ĐỘ, VÀ CHỈ MỘT CÁI DÙNG ĐƯỢC VỚI KHÁCH THẬT
---------------------------------------------------
    TẠM (mặc định)  `cloudflared tunnel --url` cấp tên miền NGẪU NHIÊN mới
                    mỗi lần chạy. Dùng để thử, không dùng để chạy thật.
    CỐ ĐỊNH         `cloudflared tunnel run --token …` chạy một tunnel ĐÃ
                    ĐẶT TÊN trên Cloudflare, gắn với tên miền của shop.
                    Tên miền KHÔNG đổi, kể cả khi máy tắt rồi bật lại.

Vì sao chế độ tạm không dùng thật được — đo trên chính hệ thống này
(14–15.09.2026): tên miền đổi BỐN lần trong 24 giờ, và một lần trong số đó
cổng công khai chết lúc 0h20 dù máy vẫn chạy bình thường. Mỗi lần đổi là
Zalo OA và Facebook ngừng gọi được, không nền tảng nào báo, và tin khách
rơi vào hư không. Dán URL tạm vào Zalo Console là công sức bỏ đi.

BẬT CHẾ ĐỘ CỐ ĐỊNH — bốn bước, làm một lần
------------------------------------------
 1. Có một tên miền (mua ở đâu cũng được), thêm nó vào tài khoản Cloudflare
    miễn phí và trỏ nameserver theo hướng dẫn của Cloudflare.
 2. Vào Cloudflare **Zero Trust → Networks → Tunnels → Create a tunnel**,
    chọn *Cloudflared*, đặt tên (ví dụ `blanica`). Cloudflare hiện một lệnh
    có chuỗi token dài — chỉ cần lấy phần token ấy.
 3. Cũng trong màn đó, thêm **Public hostname**: tên miền con bạn muốn
    (ví dụ `api.tenmien.vn`) → Service `HTTP` → `localhost:8000`.
 4. Điền hai dòng vào `.env` rồi chạy lại `python -m scripts.khoi_dong`:

        CLOUDFLARE_TUNNEL_TOKEN=<token ở bước 2>
        PUBLIC_BASE_URL=https://api.tenmien.vn

Từ đó tên miền cố định vĩnh viễn, và script này KHÔNG bao giờ ghi đè
`PUBLIC_BASE_URL` nữa — dán URL webhook một lần là xong.
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


def _giet_tunnel_cu(*, chay=subprocess.run, nghi=time.sleep) -> int:
    """
    Tắt mọi cloudflared đang chạy TRƯỚC khi bật cái mới.

    Không tắt thì có hai tên miền cùng sống, `.env` giữ một, và cái kia mới
    là cái Zalo đang gọi tới. Đo được đúng chuyện này.

    CHỜ SAU KHI TẮT, VÀ CHỈ KHI CÓ TẮT ĐƯỢC GÌ
    ------------------------------------------
    `taskkill` trả về trước khi tiến trình nhả xong handle ghi `tunnel.log`.
    Mở lại file ngay là canh một cuộc đua với hệ điều hành — đã thua thật
    một lần, xem tests/test_chay_tunnel_nhat_ky.py. Không tắt được gì thì
    không có handle nào để chờ, nên không bắt người dùng đợi vô ích.
    """
    if sys.platform == "win32":
        r = chay(
            ["taskkill", "/F", "/IM", "cloudflared.exe"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    else:
        r = chay(["pkill", "-f", "cloudflared"], capture_output=True)
    if r.returncode:
        return 0
    nghi(1.5)
    return 1


def mo_nhat_ky(duong: Path, *, mo=open, cho_giay: float = 1.5):
    """
    Mở file nhật ký cho tunnel. KHÔNG BAO GIỜ ném — trả `(file, đường thực)`.

    THỨ TỰ ƯU TIÊN: TUNNEL LÀ VIỆC CHÍNH, NHẬT KÝ LÀ THỨ PHỤ
    --------------------------------------------------------
    Bản trước `unlink()` file này rồi mở lại, và trên Windows cái `unlink`
    ném `PermissionError [WinError 32]` khi tiến trình vừa bị kill chưa nhả
    handle. Ngoại lệ không ai bắt, script chết — SAU KHI đã tắt tunnel đang
    chạy. Kết quả tệ hơn lúc chưa chạy gì: trước còn một tunnel sống với tên
    miền cũ, sau thì không còn tunnel nào, và hai kênh mất chiều nhận tin.

    Nên ở đây: thử đường chính, chờ một nhịp rồi thử lại, xong lui sang tên
    có dấu thời gian, cuối cùng lui ra thư mục tạm. Mất nhật ký chịu được;
    mất tunnel thì không.

    Không `unlink` nữa: `open(..., "w")` đã tự cắt file về rỗng, nên cái
    `unlink` chỉ thêm đúng một cách để hỏng.
    """
    import tempfile
    from datetime import datetime

    ung_vien = [duong]
    if cho_giay > 0:
        ung_vien.append(duong)          # thử lại đường chính sau một nhịp chờ
    dau = datetime.now().strftime("%Y%m%d-%H%M%S")
    ung_vien.append(duong.with_name(f"{duong.stem}-{dau}{duong.suffix}"))
    ung_vien.append(Path(tempfile.gettempdir()) /
                    f"{duong.stem}-{dau}{duong.suffix}")

    for i, p in enumerate(ung_vien):
        try:
            return mo(p, "w", encoding="utf-8"), Path(p)
        except OSError:
            if i == 0 and cho_giay > 0:
                time.sleep(cho_giay)
            continue
    # Cạn mọi đường ghi ra đĩa thì vẫn KHÔNG được chặn tunnel.
    return subprocess.DEVNULL, duong


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


def _cho_domain(nhat_ky: Path = None, giay: float = 40.0) -> str | None:
    """
    Đợi cloudflared in ra tên miền, ĐỌC ĐÚNG file đang được ghi.

    Tham số `nhat_ky` không phải đồ trang trí: `mo_nhat_ky()` có thể đã lui
    sang một tên khác vì file chính bị giữ. Đọc cứng `NHAT_KY` khi ấy là
    chờ 40 giây trên một file không ai ghi, rồi báo "không lấy được tên
    miền" — trong lúc tunnel đã lên bình thường.
    """
    tep = nhat_ky or NHAT_KY
    han = time.time() + giay
    while time.time() < han:
        if tep.exists():
            m = _MAU_DOMAIN.search(
                tep.read_text(encoding="utf-8", errors="replace")
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


KET_QUA_THONG = "thong"
KET_QUA_DNS_NOI_BO_MU = "dns_noi_bo_mu"
KET_QUA_HONG = "hong"

# DNS-over-HTTPS của Cloudflare, gọi bằng ĐỊA CHỈ IP có chủ ý: phải phân giải
# một tên miền để hỏi về DNS thì đúng cái đang hỏng sẽ chặn luôn câu hỏi.
_DOH = "https://1.1.1.1/dns-query?type=A&name="


def doc_ket_qua_thong(*, so_lan_ok: int, dns_noi_bo_mu: bool,
                      ok_qua_ip: int) -> tuple[str, str]:
    """
    Phán quyết tách khỏi phần gọi mạng, để test lái được cả ba nhánh.

    BA CA, VÀ HAI CA GIỮA TỪNG BỊ GỘP THÀNH MỘT
    -------------------------------------------
    Bản trước chỉ đếm số lượt gọi thành công qua resolver của máy. Đo được
    15.09.2026 trên mạng VNPT: resolver trả "Non-existent domain" cho tên
    miền `trycloudflare` vừa cấp, trong khi 1.1.1.1 và 8.8.8.8 phân giải ra
    IP và gọi qua IP thì HTTP 200 — tunnel sống, chỉ máy này mù. Zalo và
    Meta dùng resolver của họ nên vẫn gọi vào bình thường.

    Gộp ca ấy vào "hỏng" gây hai thiệt hại: một dòng chữ sai, và — nặng hơn
    — `.env` giữ nguyên tên miền CŨ ĐÃ CHẾT vì `main()` thoát sớm.
    """
    if so_lan_ok:
        return KET_QUA_THONG, f"thông từ Internet ({so_lan_ok} lượt gọi thành công)"
    if dns_noi_bo_mu and ok_qua_ip:
        return KET_QUA_DNS_NOI_BO_MU, (
            "tunnel phục vụ được từ Internet, nhưng MÁY NÀY không phân giải "
            "được tên miền (DNS nội bộ). Zalo/Meta vẫn gọi vào bình thường; "
            "chỉ các phép kiểm chạy trên máy này là trượt")
    return KET_QUA_HONG, "không gọi tới được từ Internet"


def _la_loi_dns(exc: BaseException) -> bool:
    """Lỗi này là 'không dịch nổi tên miền', hay là 'nối được mà bị từ chối'?

    Chỗ khác nhau ấy chính là phán quyết, nên nó phải được đọc cho đúng.
    """
    import socket

    goc = getattr(exc, "reason", exc)
    return isinstance(goc, socket.gaierror) or "getaddrinfo" in str(goc).lower()


def _ip_qua_doh(host: str, timeout: float = 8.0) -> list[str]:
    """IP của `host` theo DNS công cộng. Rỗng khi không hỏi được."""
    import json as _json

    req = urllib.request.Request(
        _DOH + host, headers={"Accept": "application/dns-json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = _json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return [str(a.get("data")) for a in (d.get("Answer") or [])
            if a.get("type") == 1 and a.get("data")]


def _goi_qua_ip(host: str, ip: str, duong: str = "/healthz",
                timeout: float = 15.0) -> bool:
    """
    Gọi HTTPS tới `ip` nhưng SNI và Host vẫn là `host`.

    Đây là cách duy nhất hỏi được "Internet có tới được tunnel này không" mà
    không đi qua resolver của máy — thứ đang là nghi phạm.
    """
    import http.client
    import socket
    import ssl

    ctx = ssl.create_default_context()
    try:
        sock = socket.create_connection((ip, 443), timeout=timeout)
    except OSError:
        return False
    try:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            conn = http.client.HTTPSConnection(host, timeout=timeout)
            conn.sock = tls
            conn.request("GET", duong, headers={"Host": host})
            return conn.getresponse().status == 200
    except (OSError, ssl.SSLError, http.client.HTTPException):
        return False
    finally:
        try:
            sock.close()
        except OSError:
            pass


def kiem_thong(domain: str, han_giay: float = 60.0) -> tuple[str, str, int]:
    """
    Tunnel có phục vụ được từ Internet không — và nếu không, vì đâu.

    ĐỢI ĐỦ LÂU, và đây là chỗ bản đầu sai.

    `cloudflared` in ra tên miền NGAY khi đăng ký được kết nối đầu tiên,
    nhưng mạng biên của Cloudflare cần thêm khoảng 20–30 giây nữa mới định
    tuyến tới nó. Đo ngay sau khi có tên miền thì lượt nào cũng trượt, và
    script kết luận "không thông" cho một tunnel hoàn toàn khoẻ.

    Đo được: lượt 1 trượt, lượt 2–4 đều 200.

    Nên đếm trong một CỬA SỔ THỜI GIAN chứ không đếm theo số lần, và dừng
    sớm ngay khi có hai lượt liền nhau thành công.

    Chờ lâu thôi VẪN CHƯA ĐỦ — xem `_xoa_dem_dns`, và xem
    `doc_ket_qua_thong` cho ca resolver nội bộ mù hẳn.
    """
    host = domain.split("://", 1)[-1].rstrip("/")
    ok = lien_tiep = 0
    loi_dns = False
    han = time.time() + han_giay
    while time.time() < han:
        _xoa_dem_dns()
        try:
            with urllib.request.urlopen(f"{domain}/healthz", timeout=15) as r:
                if r.status == 200:
                    ok += 1
                    lien_tiep += 1
                    if lien_tiep >= 2:
                        trang, ly_do = doc_ket_qua_thong(
                            so_lan_ok=ok, dns_noi_bo_mu=False, ok_qua_ip=0)
                        return trang, ly_do, ok
                else:
                    lien_tiep = 0
        except (urllib.error.URLError, OSError) as exc:
            lien_tiep = 0
            if _la_loi_dns(exc):
                loi_dns = True
        time.sleep(3)

    # Resolver của máy mù hẳn thì hỏi DNS công cộng rồi gọi thẳng vào IP —
    # đó mới là câu hỏi ta thực sự cần trả lời.
    ok_ip = 0
    if not ok and loi_dns:
        for ip in _ip_qua_doh(host)[:2]:
            if _goi_qua_ip(host, ip):
                ok_ip = 1
                break
    trang, ly_do = doc_ket_qua_thong(
        so_lan_ok=ok, dns_noi_bo_mu=loi_dns, ok_qua_ip=ok_ip)
    return trang, ly_do, ok


def _doc_env(khoa: str) -> str:
    """Một khoá trong `.env`, chuỗi rỗng nếu không có. Không bao giờ in ra."""
    f = GOC / ".env"
    if not f.exists():
        return ""
    for dong in f.read_text(encoding="utf-8", errors="replace").splitlines():
        d = dong.strip()
        if d.startswith(f"{khoa}=") and not d.startswith("#"):
            return d.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def chay_co_dinh(exe: str, token: str, dia_chi: str) -> int:
    """
    Tunnel ĐÃ ĐẶT TÊN: tên miền của shop, không đổi giữa các lần chạy.

    KHÔNG ghi `.env` ở đây — và đó là điểm khác quan trọng nhất so với chế
    độ tạm. `PUBLIC_BASE_URL` lúc này do NGƯỜI đặt, khớp với public hostname
    đã khai trên Cloudflare; script tự ghi đè là tự phá cấu hình của họ.

    Token không bao giờ in ra: nó là chìa khoá mở đường vào máy chủ này từ
    Internet, và màn hình này hay bị chụp lại.
    """
    print("Tunnel CỐ ĐỊNH (tên miền riêng) — đang mở …")
    # Dùng `mo_nhat_ky` như nhánh tạm: nó không bao giờ ném, kể cả khi
    # Windows chưa nhả handle của tiến trình vừa bị kill. Mất nhật ký chịu
    # được; chết giữa chừng SAU KHI đã tắt tunnel cũ thì không.
    f, nhat_ky = mo_nhat_ky(NHAT_KY)
    if nhat_ky != NHAT_KY:
        print(f"  Không ghi được {NHAT_KY.name}, dùng {nhat_ky} thay thế.")
    subprocess.Popen(
        [exe, "tunnel", "--edge-ip-version", "4", "--protocol", "http2",
         "run", "--token", token],
        stdout=f, stderr=f,
    )

    if not dia_chi:
        print("  Thiếu PUBLIC_BASE_URL trong .env — điền tên miền bạn đã khai")
        print("  ở mục Public hostname trên Cloudflare, ví dụ:")
        print("      PUBLIC_BASE_URL=https://api.tenmien.vn")
        return 1

    # Dùng chung `kiem_thong` với nhánh tạm — nó phân biệt được ba ca, trong
    # đó có ca resolver của máy này mù trong khi tunnel vẫn sống (đo trên
    # mạng VNPT 15.09.2026). Gọi bộ đo riêng ở đây là chép lại ba ca ấy, và
    # bản chép sẽ lệch đúng vào lần sửa tiếp theo.
    trang, ly_do, ok = kiem_thong(dia_chi.rstrip("/"))
    if trang == KET_QUA_HONG:
        print(f"  Tunnel chạy nhưng {dia_chi} KHÔNG thông: {ly_do}")
        print(f"  Xem {nhat_ky.name}; kiểm lại Public hostname trên Cloudflare")
        print("  có trỏ về http://localhost:8000 không.")
        return 1

    print(f"\n  {dia_chi}")
    print(f"  {ly_do}")
    print("  Tên miền CỐ ĐỊNH — không phải dán lại URL webhook lần nào nữa.\n")
    return 0


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

    # Có token thì đi đường CỐ ĐỊNH. Đặt trước nhánh tạm để không bao giờ
    # có chuyện đã cấu hình tên miền riêng mà script vẫn lặng lẽ dựng một
    # tunnel tạm rồi ghi đè PUBLIC_BASE_URL bằng tên ngẫu nhiên.
    token = _doc_env("CLOUDFLARE_TUNNEL_TOKEN")
    if token:
        return chay_co_dinh(exe, token, _doc_env("PUBLIC_BASE_URL"))

    f, nhat_ky = mo_nhat_ky(NHAT_KY)
    if nhat_ky != NHAT_KY:
        print(f"Không ghi được {NHAT_KY.name}, dùng {nhat_ky} thay thế.")

    # `--edge-ip-version 4`: xem cái bẫy số 2 ở đầu tệp.
    try:
        subprocess.Popen(
            [exe, "tunnel", "--url", f"http://localhost:{CONG_APP}",
             "--edge-ip-version", "4", "--protocol", "http2"],
            stdout=f, stderr=f,
        )
    finally:
        if f is not subprocess.DEVNULL:
            f.close()

    print("Đang mở tunnel …")
    domain = _cho_domain(nhat_ky)
    if not domain:
        print(f"Không lấy được tên miền sau 40 giây. Xem {NHAT_KY.name}.")
        return 1

    trang, ly_do, ok = kiem_thong(domain)
    if trang == KET_QUA_HONG:
        print(f"Tunnel lên nhưng {ly_do}. Xem {nhat_ky.name}.")
        return 1

    # GHI `.env` KỂ CẢ KHI RESOLVER NỘI BỘ MÙ.
    #
    # Không ghi thì `.env` giữ tên miền CŨ ĐÃ CHẾT — tệ hơn hẳn lúc chưa
    # chạy gì, vì dashboard vẫn dựng URL webhook trỏ vào hư không, mà người
    # vận hành thì vừa được báo "tunnel không thông" nên đi tìm bệnh ở chỗ
    # khác. Tên miền ở đây lấy từ log của chính cloudflared SAU khi nó đăng
    # ký được kết nối, nên nó có thật.
    _doi_env(domain)
    print(f"\n  {domain}")
    print(f"  {ly_do[0].upper()}{ly_do[1:]}.")
    print("  Đã cập nhật PUBLIC_BASE_URL và WEBHOOK_PUBLIC_URL trong .env.\n")
    print("CÒN HAI VIỆC PHẢI LÀM TAY:")
    print("  1. Khởi động lại dashboard để nó đọc .env mới.")
    print("  2. Dán lại URL webhook vào Zalo/Meta Console — tên miền vừa đổi,")
    print("     và không nền tảng nào báo cho bạn biết nó đã ngừng gọi được.")
    print("\nĐÂY LÀ TUNNEL TẠM — đo trên chính máy này: tên miền đổi BỐN lần")
    print("trong 24 giờ. Chạy thật thì bật chế độ CỐ ĐỊNH: xem bốn bước ở đầu")
    print("scripts/chay_tunnel.py, hoặc mục Cổng công khai trong docs/van-hanh.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
