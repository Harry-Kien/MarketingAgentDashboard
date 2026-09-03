"""
Dựng cả hệ thống bằng MỘT lệnh, và nói thẳng cái nào chưa lên.

    python -m scripts.khoi_dong

VÌ SAO CẦN LỆNH NÀY
-------------------
Hệ thống là NĂM tiến trình rời nhau, và trước bản này không cái nào tự lên
lại sau khi máy khởi động:

    Docker Desktop  →  Postgres (5433) + n8n (5678)
    uvicorn         →  ứng dụng (8000)
    Node            →  sidecar Zalo cá nhân (3210)
    cloudflared     →  tunnel công khai, và tên miền ghi vào .env

ĐO ĐƯỢC 03.09.2026: máy tắt lúc 19:52, bật lại lúc 22:41. Không cổng nào
trong 8000/5433/3210/5678 còn nghe. Ba tiếng đó khách nhắn vào rơi vào hư
không — không lỗi, không nhật ký, và dashboard cũng không chạy để mà hiện
đỏ. Đây là kiểu hỏng im lặng ở tầng tiến trình, tầng mà sáu lớp lưới trong
`agent/core/agent.py` không với tới.

`restart: unless-stopped` trong `docker-compose.yml` lo được nửa Docker.
Ba tiến trình còn lại nằm ngoài Docker nên vẫn phải có người bật — lệnh này
là người đó.

VÌ SAO BẬT APP HAI LẦN
----------------------
Có một vòng phụ thuộc thật, không né được:

    `chay_tunnel` cần app đang chạy   (nó đo /healthz XUYÊN QUA tunnel để
                                       biết tunnel có thông từ ngoài không)
    app cần .env đã có tên miền mới   (nó đọc .env MỘT LẦN lúc khởi động)

Nên: bật app → bật tunnel (ghi .env) → nếu .env đổi thì bật lại app. Lần
bật thứ hai chỉ xảy ra khi tên miền thật sự khác, và script nói rõ vì sao.

Bỏ bước bật lại là dashboard dựng URL webhook theo tên miền CŨ — vẫn hiện
ra một URL trông đúng, chỉ là không ai gọi tới được.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
CONG_APP = 8000
CONG_SIDECAR = 3210
DOCKER_DESKTOP = (
    r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
    r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
)


# ---------------------------------------------------------------
#  Phép đo dùng chung
# ---------------------------------------------------------------

def _http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def _cho(dieu_kien, giay: float, nhip: float = 1.0) -> bool:
    han = time.time() + giay
    while time.time() < han:
        if dieu_kien():
            return True
        time.sleep(nhip)
    return dieu_kien()


def _chay(*lenh: str, giay: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(lenh), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=giay,
    )


def _doc_env(khoa: str) -> str:
    tep = GOC / ".env"
    if not tep.exists():
        return ""
    m = re.search(rf"(?m)^{re.escape(khoa)}=(.*)$",
                  tep.read_text(encoding="utf-8", errors="replace"))
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------
#  Từng tầng
# ---------------------------------------------------------------

def _docker_song() -> bool:
    try:
        return _chay("docker", "info", giay=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def buoc_docker() -> tuple[bool, str]:
    if _docker_song():
        return True, "đã chạy sẵn"

    exe = next((p for p in DOCKER_DESKTOP if Path(p).exists()), None)
    if not exe:
        return False, "không thấy Docker Desktop — bật tay rồi chạy lại"
    try:
        subprocess.Popen([exe])
    except OSError as e:
        return False, f"không gọi được Docker Desktop: {e}"

    # Docker Desktop dựng máy ảo Linux, chậm hơn hẳn mọi tầng khác.
    print("  … Docker Desktop đang lên, việc này mất khoảng một phút")
    if _cho(_docker_song, giay=240, nhip=5):
        return True, "vừa bật"
    return False, "không lên sau 4 phút"


def buoc_csdl() -> tuple[bool, str]:
    r = _chay("docker", "compose", "up", "-d", giay=300)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout or "").strip()[:160]

    def san_sang() -> bool:
        return _chay(
            "docker", "compose", "exec", "-T", "db",
            "pg_isready", "-U", "agent", giay=15,
        ).returncode == 0

    if _cho(san_sang, giay=90, nhip=2):
        return True, "Postgres 5433 + n8n 5678"
    return False, "container lên nhưng Postgres không nhận kết nối"


def _app_song() -> bool:
    return _http_ok(f"http://127.0.0.1:{CONG_APP}/healthz")


def _bat_app() -> None:
    with open(GOC / "app.log", "a", encoding="utf-8") as f:
        subprocess.Popen(
            [str(GOC / ".venv" / "Scripts" / "python.exe")
             if os.name == "nt" else sys.executable,
             "-m", "uvicorn", "agent.main:app", "--port", str(CONG_APP)],
            cwd=str(GOC), stdout=f, stderr=f,
        )


def _tat_app() -> None:
    """
    Tắt uvicorn đang chạy để bật lại với `.env` mới.

    Lọc theo CẢ `uvicorn` LẪN thư mục dự án. Lọc mỗi "python" là tắt nhầm
    tiến trình Python khác của người dùng — kể cả chính script này.
    """
    if os.name != "nt":
        _chay("pkill", "-f", "uvicorn agent.main:app", giay=20)
        return
    r = _chay(
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
        "Where-Object { $_.CommandLine -like '*uvicorn*agent.main:app*' } | "
        "Select-Object -ExpandProperty ProcessId",
        giay=60,
    )
    for dong in r.stdout.split():
        if dong.strip().isdigit():
            _chay("taskkill", "/F", "/PID", dong.strip(), giay=20)


def buoc_app(bat_lai: bool = False) -> tuple[bool, str]:
    if _app_song() and not bat_lai:
        return True, f"đã chạy sẵn trên {CONG_APP}"
    if bat_lai:
        _tat_app()
        time.sleep(2)
    _bat_app()
    if _cho(_app_song, giay=60):
        return True, ("bật lại để đọc .env mới" if bat_lai else "vừa bật")
    return False, "không lên sau 60 giây — xem app.log"


def buoc_sidecar() -> tuple[bool, str]:
    """
    Sidecar Zalo cá nhân. Giao hẳn cho `chay_sidecar_zalo` vì ba biến môi
    trường và cách truyền bí mật nằm trọn trong đó — chép lại ở đây là chép
    một chỗ dễ lệch.
    """
    if _http_ok(f"http://127.0.0.1:{CONG_SIDECAR}/healthz"):
        return True, f"đã chạy sẵn trên {CONG_SIDECAR}"
    r = _chay(sys.executable, "-m", "scripts.chay_sidecar_zalo", giay=180)
    if _http_ok(f"http://127.0.0.1:{CONG_SIDECAR}/healthz", timeout=8):
        return True, "vừa bật"
    return False, (r.stdout or r.stderr or "").strip().splitlines()[-1][:160] \
        if (r.stdout or r.stderr) else "không lên"


def buoc_tunnel() -> tuple[bool, str, bool]:
    """Trả về (được không, mô tả, .env có đổi không)."""
    truoc = _doc_env("PUBLIC_BASE_URL")
    r = _chay(sys.executable, "-m", "scripts.chay_tunnel", giay=300)
    sau = _doc_env("PUBLIC_BASE_URL")
    if r.returncode != 0:
        dong = [d for d in (r.stdout or "").splitlines() if d.strip()]
        return False, (dong[-1] if dong else "không bật được")[:160], False
    return True, sau, (sau != truoc)


# ---------------------------------------------------------------

def main() -> int:
    print("DỰNG HỆ THỐNG")
    print("─" * 62)

    ket: list[tuple[str, bool, str]] = []

    for ten, ham in (("Docker", buoc_docker), ("Postgres + n8n", buoc_csdl)):
        ok, mo_ta = ham()
        ket.append((ten, ok, mo_ta))
        print(f"  {'[đủ]' if ok else '[HỎNG]':<9}{ten:<18}{mo_ta}")
        if not ok:
            # Không có CSDL thì app lên rồi cũng chỉ để trả 500. Dừng ở đây
            # và nói rõ, hơn là dựng tiếp một hệ thống trông như đang chạy.
            print("\nDừng: các tầng sau đều cần Postgres.")
            return 1

    ok, mo_ta = buoc_app()
    ket.append(("Ứng dụng", ok, mo_ta))
    print(f"  {'[đủ]' if ok else '[HỎNG]':<9}{'Ứng dụng':<18}{mo_ta}")

    ok_sc, mo_ta_sc = buoc_sidecar()
    ket.append(("Sidecar Zalo", ok_sc, mo_ta_sc))
    print(f"  {'[đủ]' if ok_sc else '[HỎNG]':<9}{'Sidecar Zalo':<18}{mo_ta_sc}")

    ok_tn, mo_ta_tn, doi = buoc_tunnel()
    ket.append(("Tunnel", ok_tn, mo_ta_tn))
    print(f"  {'[đủ]' if ok_tn else '[HỎNG]':<9}{'Tunnel':<18}{mo_ta_tn}")

    if ok_tn and doi:
        ok, mo_ta = buoc_app(bat_lai=True)
        ket.append(("Ứng dụng (lần 2)", ok, mo_ta))
        print(f"  {'[đủ]' if ok else '[HỎNG]':<9}{'Ứng dụng':<18}{mo_ta}")

    print("─" * 62)
    hong = [t for t, ok, _ in ket if not ok]
    if hong:
        print("CHƯA XONG — còn hỏng: " + ", ".join(hong))
        return 1

    print(f"Xong. Dashboard: http://127.0.0.1:{CONG_APP}")
    if doi:
        print("\nTÊN MIỀN VỪA ĐỔI — phải dán lại URL webhook vào Zalo/Meta")
        print("Console. Không nền tảng nào báo cho bạn biết nó đã ngừng gọi")
        print("được, nên bỏ bước này là kênh chết im lặng.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
