"""
Bật sidecar Zalo cá nhân, đọc cấu hình từ `.env`.

    python -m scripts.chay_sidecar_zalo          chạy nền, trả lại terminal
    python -m scripts.chay_sidecar_zalo --hien   chạy trước mặt, xem log ngay

VÌ SAO CẦN SCRIPT NÀY
---------------------
Sidecar là tiến trình Node RIÊNG (`connectors/zalo-personal-sidecar`), không
nằm trong `docker-compose.yml` nên không tự chạy lại sau khi khởi động máy.

Bật tay thì phải nhớ ba biến môi trường, và chúng nằm rải trong `.env` với
tên hơi khác tên biến sidecar đọc:

    .env có ZALO_SIDECAR_SECRET, ZALO_CONTROL_PLANE_URL
    .env KHÔNG có ZALO_SIDECAR_HOST và ZALO_SIDECAR_PORT — sidecar tự mặc
    định, nhưng `ZALO_SIDECAR_URL` trong .env lại ghim cổng 3210

Quên một biến thì sidecar vẫn CHẠY, chỉ là app không gọi tới được — hoặc
gọi được mà chữ ký HMAC không khớp. Cả hai đều hỏng im lặng: dashboard hiện
"Gián đoạn", tin nhân viên vào outbox rồi chết sau tám lần thử.

VÌ SAO KHÔNG IN BÍ MẬT RA MÀN HÌNH
----------------------------------
`ZALO_SIDECAR_SECRET` được truyền qua biến môi trường của tiến trình con,
không qua tham số dòng lệnh và không in ra. Tham số dòng lệnh hiện trong
`ps`/Task Manager cho mọi tiến trình khác trên máy đọc được.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
THU_MUC = GOC / "connectors" / "zalo-personal-sidecar"
CONG_MAC_DINH = "3210"


def _doc_env() -> dict[str, str]:
    tep = GOC / ".env"
    if not tep.exists():
        return {}
    ra: dict[str, str] = {}
    for dong in tep.read_text(encoding="utf-8", errors="replace").splitlines():
        dong = dong.strip()
        if not dong or dong.startswith("#") or "=" not in dong:
            continue
        k, v = dong.split("=", 1)
        ra[k.strip()] = v.strip()
    return ra


def _cong_tu_url(url: str) -> str:
    """
    Cổng lấy từ `ZALO_SIDECAR_URL` — đó mới là địa chỉ APP sẽ gọi tới.

    Chạy sidecar ở cổng khác cổng app gọi là cách hỏng khó tìm nhất: cả hai
    bên đều chạy, đều không báo lỗi, chỉ là không bao giờ gặp nhau.
    """
    if ":" in url.rsplit("/", 1)[-1]:
        duoi = url.rstrip("/").rsplit(":", 1)[-1]
        if duoi.isdigit():
            return duoi
    return CONG_MAC_DINH


def _song(cong: str, giay: float = 45.0) -> bool:
    """
    Đợi sidecar trả lời `/healthz`, tối đa `giay` giây.

    VÌ SAO 45 CHỨ KHÔNG PHẢI 12

    Đo được (03.09.2026): script in "Sidecar không lên sau 12 giây" trong
    khi `sidecar.log` đã ghi "listening on http://127.0.0.1:3210" và cổng
    3210 đang nghe thật. Sidecar in dòng ấy lúc mở cổng, nhưng còn phải
    khôi phục phiên Zalo xong mới phục vụ được — mất hơn 12 giây.

    Báo hỏng cho một tiến trình đang khoẻ là kiểu sai đắt nhất ở đây: người
    vận hành đi bật lại một thứ đang chạy, hoặc tệ hơn, tin rằng kênh đã
    chết và thôi không dùng nữa.

    `time.sleep` phải nằm NGOÀI khối `except`. Để trong đó thì nhánh nối
    được-nhưng-không-phải-200 quay vòng không nghỉ, đốt CPU suốt thời gian
    chờ.
    """
    han = time.time() + giay
    while time.time() < han:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{cong}/healthz", timeout=3
            ) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.6)
    return False


def main() -> int:
    if not THU_MUC.is_dir():
        print(f"Không thấy {THU_MUC}. Submodule đã checkout chưa?")
        return 1
    if not (THU_MUC / "node_modules").is_dir():
        print("Chưa cài phụ thuộc. Chạy:")
        print(f"  cd {THU_MUC} && npm install")
        return 1

    env = _doc_env()
    bi_mat = env.get("ZALO_SIDECAR_SECRET", "")
    if not bi_mat:
        print("ZALO_SIDECAR_SECRET trống trong .env. Sinh bằng:")
        print("  python -m scripts.sinh_token ZALO_SIDECAR_SECRET")
        return 1

    cong = _cong_tu_url(env.get("ZALO_SIDECAR_URL", ""))
    if _song(cong, giay=1.5):
        print(f"Sidecar đã chạy sẵn trên cổng {cong}. Không bật thêm.")
        return 0

    moi_truong = {
        **os.environ,
        "ZALO_SIDECAR_SECRET": bi_mat,
        "ZALO_SIDECAR_HOST": "127.0.0.1",
        "ZALO_SIDECAR_PORT": cong,
        "ZALO_CONTROL_PLANE_URL": env.get(
            "ZALO_CONTROL_PLANE_URL",
            "http://127.0.0.1:8000/webhook/native/zalo-personal",
        ),
    }

    hien = "--hien" in sys.argv
    print(f"Bật sidecar trên 127.0.0.1:{cong} …")
    if hien:
        return subprocess.call(
            ["node", "src/server.mjs"], cwd=str(THU_MUC), env=moi_truong
        )

    nhat_ky = GOC / "sidecar.log"
    with open(nhat_ky, "a", encoding="utf-8") as f:
        subprocess.Popen(
            ["node", "src/server.mjs"],
            cwd=str(THU_MUC), env=moi_truong, stdout=f, stderr=f,
        )

    if _song(cong):
        print(f"Sidecar sống trên http://127.0.0.1:{cong} — nhật ký: {nhat_ky.name}")
        print("Vào dashboard → Kết nối → Xác minh provider.")
        return 0
    print(f"Sidecar không lên sau 45 giây. Xem {nhat_ky.name}, hoặc chạy lại")
    print("với --hien để nhìn log ngay trên terminal.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
