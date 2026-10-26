"""
Cho Facebook nhận được tin khách — dựng lại tunnel nếu chết, rồi TỰ KHAI
địa chỉ webhook với Meta (không dán tay).

    python -m scripts.noi_lai_facebook             tunnel chết thì dựng lại, rồi khai Meta
    python -m scripts.noi_lai_facebook --chi-khai  chỉ khai Meta theo PUBLIC_BASE_URL hiện tại

Người canh (scripts/canh_gac_ngoai.py) bật lệnh này TÁCH RỜI khi thấy địa chỉ
công khai không trả lời — để tunnel tạm đổi tên miền không còn là "Facebook
chết im lặng tới khi có người để ý".

Zalo OA KHÔNG tự khai được: Zalo không có API đổi webhook — vẫn phải dán ở
developers.zalo.me. Lệnh này in sẵn địa chỉ để dán.

Mã thoát khác 0 khi Facebook vẫn chưa nhận được tin.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
NHAT_KY = GOC / "data" / "noi_lai_facebook.log"


SO_LAN_THU = 3


def cong_khai_song_nhanh(url: str, timeout: float = 10.0, *, so_lan: int = SO_LAN_THU,
                         nghi: float = 3.0) -> bool:
    """
    Địa chỉ công khai có trả lời /healthz không — cho người canh, 5 phút một lần.

    Kết luận "chết" là việc ĐẮT: người canh sẽ dựng lại tunnel, tên miền đổi,
    địa chỉ Zalo OA người vận hành đã dán thành vô hiệu. Nên chỉ kết luận chết
    khi MỌI đường đều không trả lời, qua nhiều lần thử:

      · DNS của máy lỗi -> hỏi DNS công cộng rồi gọi thẳng IP (resolver nhà
        mạng từng "mù" tên miền tunnel vừa cấp — bộ nhớ dự án);
      · QUÁ HẠN hay lỗi khác -> cũng thử đường IP, rồi thử lại lượt sau. Đo
        26.10.2026: tunnel trycloudflare thỉnh thoảng chậm quá 10 giây
        (`context canceled` trong tunnel.log), bản một-lần-thử báo "chết"
        cho một tunnel trả 200 sau 1,5 giây ở lần gọi kế tiếp.
    """
    from scripts import chay_tunnel as ct

    if not url.startswith("https://"):
        return False
    host = url.split("://", 1)[1].split("/", 1)[0]
    for lan in range(so_lan):
        try:
            with urllib.request.urlopen(f"{url.rstrip('/')}/healthz", timeout=timeout) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        if any(ct._goi_qua_ip(host, ip, timeout=timeout) for ip in ct._ip_qua_doh(host)[:2]):
            return True
        if lan + 1 < so_lan:
            time.sleep(nghi)
    return False


def _ghi(dong: str) -> None:
    print(dong, flush=True)
    try:
        NHAT_KY.parent.mkdir(parents=True, exist_ok=True)
        with open(NHAT_KY, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {dong}\n")
    except OSError:
        pass


async def _khai(url: str) -> tuple[bool, str]:
    from agent import db
    from agent.channels import webhook_app_meta

    await db.init_db()
    try:
        return await webhook_app_meta.dang_ky_cho_he_thong(url)
    finally:
        await db.close_db()


def chay(chi_khai: bool = False) -> int:
    from scripts import chay_tunnel as ct
    from scripts import khoi_dong as k

    if not k._app_song():
        _ghi("App chưa chạy trên cổng 8000 — người canh sẽ dựng lại app trước.")
        return 1
    url = ct._doc_env("PUBLIC_BASE_URL")
    if not chi_khai and not cong_khai_song_nhanh(url):
        _ghi(f"Địa chỉ công khai {url or '(trống)'} không trả lời — dựng lại tunnel …")
        ok, mo_ta, env_doi = k.buoc_tunnel()
        _ghi(f"tunnel: {mo_ta}")
        if not ok:
            return 1
        if env_doi:
            ok, mo_ta = k.buoc_app(bat_lai=True)
            _ghi(f"app: {mo_ta}")
            if not ok:
                return 1
        url = ct._doc_env("PUBLIC_BASE_URL")
    ok, mo_ta = asyncio.run(_khai(url))
    _ghi(("Facebook: " if ok else "Facebook CHƯA nhận được tin: ") + mo_ta)
    _ghi(f"Zalo OA (dán tay ở developers.zalo.me): {url.rstrip('/')}/webhook/native/zalo-oa/<account_id>")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m scripts.noi_lai_facebook")
    ap.add_argument("--chi-khai", action="store_true")
    return chay(chi_khai=ap.parse_args(argv).chi_khai)


if __name__ == "__main__":
    raise SystemExit(main())
