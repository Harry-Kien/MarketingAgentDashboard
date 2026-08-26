"""
Nối Telegram làm nơi nhận báo động — lấy chat id và ghi cấu hình hộ.

    1. Mở .env, thêm MỘT dòng tạm:
           TELEGRAM_BOT_TOKEN=<token BotFather đưa>
    2. Nhắn một câu bất kỳ cho bot (Telegram KHÔNG cho bot nhắn trước)
    3. Chạy:  python -m scripts.noi_telegram

Script tự lấy chat id, ghi `CANH_GAC_WEBHOOK` và `CANH_GAC_GOI_TIN`, rồi
XOÁ dòng token tạm đi.

VÌ SAO KHÔNG BẮT NGƯỜI DÙNG TỰ LÀM
----------------------------------
Chuỗi thao tác thủ công là: mở trình duyệt, gọi getUpdates, đọc JSON thô,
tìm đúng con số giữa đống dữ liệu, rồi tự ghép hai dòng cấu hình có dấu
ngoặc kép lồng nhau. Bốn chỗ có thể sai, và sai nào cũng dẫn tới cùng một
kết cục: báo động im lặng không hoạt động, mà không có gì nói ra điều đó.

VÌ SAO TOKEN ĐI QUA .env CHỨ KHÔNG QUA THAM SỐ DÒNG LỆNH
--------------------------------------------------------
Tham số dòng lệnh nằm trong lịch sử shell và trong danh sách tiến trình —
mọi người dùng khác trên máy đều đọc được. Đọc từ .env thì token chỉ đi từ
file vào bộ nhớ tiến trình rồi thôi.

Script này KHÔNG BAO GIỜ in token ra màn hình.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
KHOA_TAM = "TELEGRAM_BOT_TOKEN"


def chat_id_tu_getupdates(phan_hoi: dict) -> str:
    """
    Chat id MỚI NHẤT trong phản hồi getUpdates.

    Lấy cái mới nhất chứ không phải cái đầu tiên: người dùng thường nhắn thử
    vài lần, và ghi nhầm vào một cuộc trò chuyện đã bỏ nghĩa là báo động đi
    vào chỗ không ai đọc.
    """
    ket_qua = phan_hoi.get("result") or []
    for muc in reversed(ket_qua):
        tin = muc.get("message") or muc.get("edited_message") or {}
        chat = tin.get("chat") or {}
        if chat.get("id") is not None:
            return str(chat["id"])
    raise ValueError(
        "Chưa thấy cuộc trò chuyện nào. Telegram KHÔNG cho bot nhắn trước — "
        "hãy mở Telegram, NHẮN một câu bất kỳ cho bot, rồi chạy lại lệnh này."
    )


def dung_hai_dong(token: str, chat_id: str) -> tuple[str, str]:
    """Hai dòng cấu hình. Gói tin phải nằm TRỌN một dòng — .env không hiểu
    giá trị xuống dòng."""
    webhook = f"https://api.telegram.org/bot{token}/sendMessage"
    goi_tin = json.dumps(
        {"chat_id": chat_id,
         "text": "[{muc_do}] {tieu_de} — {chi_tiet}"},
        ensure_ascii=False, separators=(",", ":"),
    )
    return webhook, goi_tin


def _doc_token() -> str:
    if not ENV.exists():
        sys.exit(".env không tồn tại")
    for dong in ENV.read_text(encoding="utf-8").splitlines():
        dong = dong.strip()
        if dong.startswith(f"{KHOA_TAM}=") and not dong.startswith("#"):
            return dong.split("=", 1)[1].strip()
    sys.exit(
        f"Chưa thấy {KHOA_TAM} trong .env.\n"
        f"Thêm một dòng tạm:  {KHOA_TAM}=<token BotFather đưa>\n"
        "Script sẽ tự xoá dòng đó sau khi xong."
    )


def _dat(noi_dung: str, khoa: str, gia_tri: str) -> str:
    dong_moi = f"{khoa}={gia_tri}"
    mau = re.compile(rf"^{re.escape(khoa)}=.*$", re.MULTILINE)
    if mau.search(noi_dung):
        return mau.sub(lambda _: dong_moi, noi_dung, count=1)
    return noi_dung.rstrip("\n") + f"\n{dong_moi}\n"


def main() -> int:
    token = _doc_token()
    print("Đang hỏi Telegram xem ai đã nhắn cho bot…")
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getUpdates", timeout=25
        ) as r:
            phan_hoi = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        # KHÔNG in URL: nó chứa token.
        return _thoat(f"Telegram từ chối (HTTP {exc.code}). Token có đúng không?")
    except (urllib.error.URLError, OSError) as exc:
        return _thoat(f"Không gọi được Telegram: {exc}")

    if not phan_hoi.get("ok"):
        return _thoat("Telegram trả về lỗi. Kiểm lại token.")
    try:
        chat_id = chat_id_tu_getupdates(phan_hoi)
    except ValueError as exc:
        return _thoat(str(exc))

    webhook, goi_tin = dung_hai_dong(token, chat_id)
    noi_dung = ENV.read_text(encoding="utf-8")
    noi_dung = _dat(noi_dung, "CANH_GAC_WEBHOOK", webhook)
    noi_dung = _dat(noi_dung, "CANH_GAC_GOI_TIN", goi_tin)
    # Xoá dòng token tạm: nó đã làm xong việc, giữ lại là thêm một chỗ để lộ.
    noi_dung = re.sub(rf"^{KHOA_TAM}=.*\n?", "", noi_dung, flags=re.MULTILINE)
    ENV.write_text(noi_dung, encoding="utf-8")

    print(f"Xong. chat id = {chat_id}")
    print("Đã ghi CANH_GAC_WEBHOOK và CANH_GAC_GOI_TIN vào .env.")
    print(f"Đã xoá dòng {KHOA_TAM} tạm.")
    print("\nKhởi động lại app để nạp cấu hình mới.")
    return 0


def _thoat(ly_do: str) -> int:
    print(f"KHÔNG NỐI ĐƯỢC: {ly_do}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
