"""
Người canh BÊN NGOÀI — bắt cả trường hợp agent chết hẳn.

    python -m scripts.canh_gac_ngoai

VÌ SAO CẦN CÁI NÀY KHI ĐÃ CÓ agent/canh_gac.py
----------------------------------------------
Vòng canh gác kia chạy TRONG tiến trình agent. Nó phát hiện được suy giảm —
model chết, kênh mất kết nối, sao lưu cũ — nhưng không phát hiện được chính
tiến trình chết, vì lúc đó nó cũng chết theo.

Đó không phải chi tiết lý thuyết: tiến trình chết là kiểu hỏng TỆ NHẤT và
cũng THƯỜNG GẶP NHẤT — hết bộ nhớ, máy khởi động lại sau khi cập nhật, ai
đó đóng nhầm cửa sổ.

Script này gọi `/healthz` từ ngoài. Không trả lời trong hạn, hoặc trả về mã
lỗi, là báo động.

ĐẶT LỊCH
--------
Windows — Task Scheduler, chạy mỗi 5 phút:

    schtasks /create /tn "CanhGacMarketingAgent" /sc minute /mo 5 ^
      /tr "C:\\Users\\PC\\Downloads\\Marketing\\.venv\\Scripts\\python.exe -m scripts.canh_gac_ngoai" ^
      /st 00:00

Linux — cron:

    */5 * * * * cd /duong/dan/du-an && .venv/bin/python -m scripts.canh_gac_ngoai

CỐ Ý KHÔNG DÙNG CSDL
--------------------
Script này phải chạy được cả khi Postgres chết. Trạng thái lần trước lưu
vào một file cạnh nó, không lưu vào bảng — dùng CSDL ở đây là để người canh
chết chung với thứ nó đang canh.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import settings  # noqa: E402

DIA_CHI = "http://127.0.0.1:8000/healthz"
CHO_GIAY = 10
# Trạng thái lần trước — file, không phải CSDL. Xem phần đầu.
TRANG_THAI = ROOT / "data" / ".canh_gac_ngoai"


def _doc_truoc() -> str:
    try:
        return TRANG_THAI.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _ghi(trang_thai: str) -> None:
    try:
        TRANG_THAI.parent.mkdir(parents=True, exist_ok=True)
        TRANG_THAI.write_text(trang_thai, encoding="utf-8")
    except OSError:
        pass


def _bao(muc_do: str, chi_tiet: str) -> None:
    print(f"[{muc_do}] {chi_tiet}")
    if not settings.canh_gac_webhook:
        return
    goi = json.dumps({
        "muc_do": muc_do,
        "tieu_de": ("Agent KHÔNG PHẢN HỒI" if muc_do == "hong"
                    else "Agent đã sống lại"),
        "chi_tiet": chi_tiet,
        "nguon": "canh_gac_ngoai",
    }).encode()
    yeu_cau = urllib.request.Request(
        settings.canh_gac_webhook, data=goi,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(yeu_cau, timeout=15).close()
    except (urllib.error.URLError, OSError) as exc:
        # Báo động gửi hỏng thì in ra rồi thôi. Người canh không được chết
        # vì nơi nhận báo động đang hỏng.
        print(f"  (không gửi được báo động: {exc})")


def main() -> int:
    truoc = _doc_truoc()
    try:
        with urllib.request.urlopen(DIA_CHI, timeout=CHO_GIAY) as r:
            song = r.status == 200
            ly_do = f"HTTP {r.status}"
    except (urllib.error.URLError, OSError) as exc:
        song = False
        ly_do = f"{type(exc).__name__}: {exc}"

    nay = "tot" if song else "hong"
    if nay == "hong" and truoc != "hong":
        _bao("hong", f"{DIA_CHI} không trả lời trong {CHO_GIAY}s — {ly_do}")
    elif nay == "tot" and truoc == "hong":
        _bao("phuc_hoi", f"{DIA_CHI} trả lời bình thường trở lại")
    else:
        print(f"[{nay}] {ly_do}")

    _ghi(nay)
    # Mã thoát khác 0 khi hỏng, để Task Scheduler và cron cũng biết.
    return 0 if song else 1


if __name__ == "__main__":
    raise SystemExit(main())
