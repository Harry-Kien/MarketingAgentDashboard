"""
Người canh BÊN NGOÀI — bắt cả trường hợp agent chết hẳn, và TỰ DỰNG LẠI.

    python -m scripts.canh_gac_ngoai

VÌ SAO CẦN CÁI NÀY KHI ĐÃ CÓ agent/canh_gac.py
----------------------------------------------
Vòng canh gác kia chạy TRONG tiến trình agent. Nó phát hiện được suy giảm —
model chết, kênh mất kết nối, sao lưu cũ — nhưng không phát hiện được chính
tiến trình chết, vì lúc đó nó cũng chết theo.

Đó không phải chi tiết lý thuyết: tiến trình chết là kiểu hỏng TỆ NHẤT và
cũng THƯỜNG GẶP NHẤT — hết bộ nhớ, máy khởi động lại sau khi cập nhật, ai
đó đóng nhầm cửa sổ.

VÌ SAO KHÔNG CHỈ BÁO MÀ PHẢI DỰNG LẠI
------------------------------------
Đo được 06.09.2026: app và sidecar chết lúc 6h27, người canh gửi Telegram
đúng một lần lúc đổi trạng thái, rồi 5 tiếng khách nhắn vào hư không tới
khi có người mở terminal. Báo đúng mà không làm gì thì với khách cũng như
không báo. Nên khi app không trả lời HAI lần liên tiếp (10 phút), script
này tự gọi đúng bốn bước của `scripts.khoi_dong` — Docker, Postgres, app,
sidecar — và KHÔNG đụng tunnel hay `.env`: người canh không được tự đổi tên
miền công khai sau lưng người vận hành.

Hai lưới quanh việc dựng lại, vì dựng lại cũng có thể là sai:
  * chờ hai lần hỏng liên tiếp — một lần trượt mạng không được làm khởi động
    lại một app đang sống và làm rơi tin đang xử lý;
  * tối đa ba lần mỗi giờ — lỗi cấu hình mà cứ dựng lại là vòng lặp vô ích,
    lúc đó phải báo "bỏ cuộc" để người vào xem.

ĐẶT LỊCH
--------
Windows — Task Scheduler, chạy mỗi 5 phút bằng `scripts/canh_gac_ngoai.bat`
(file .bat cố ý không dấu; xem chú thích trong đó):

    schtasks /create /tn "CanhGacMarketingAgent" /sc minute /mo 5 ^
      /tr "D:\\Marketing Dasbhboard CSKH\\scripts\\canh_gac_ngoai.bat" /st 00:00

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
from datetime import datetime, timedelta, timezone
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

# Hỏng liên tiếp bao nhiêu lần thì dựng lại, và tối đa bao nhiêu lần một giờ.
NGUONG_DUNG_LAI = 2
TOI_DA_MOI_GIO = 3
_VN = timezone(timedelta(hours=7))

TIEU_DE = {
    "hong": "Agent KHÔNG PHẢN HỒI",
    "phuc_hoi": "Agent đã sống lại",
    "tu_dung_lai": "Agent chết — đã tự dựng lại",
    "tu_dung_lai_hong": "Agent chết — tự dựng lại THẤT BẠI",
    "bo_cuoc": f"Agent chết — đã dựng lại {TOI_DA_MOI_GIO} lần trong một giờ, bỏ cuộc",
}


def doc_trang_thai(tho: str) -> dict:
    """
    Trạng thái lần trước. Nhận cả dạng cũ (chỉ 'tot'/'hong') lẫn JSON.

    Dạng cũ vẫn phải hiểu được: máy đang chạy có sẵn file 'tot' hoặc
    'hong', và lần chạy đầu sau khi cập nhật không được coi đó là rác.
    """
    tho = (tho or "").strip()
    mac_dinh = {"trang_thai": "", "hong_lien_tiep": 0, "dung_lai": [], "da_bo_cuoc": False}
    if tho in ("tot", "hong"):
        return {**mac_dinh, "trang_thai": tho, "hong_lien_tiep": 1 if tho == "hong" else 0}
    try:
        d = json.loads(tho)
    except ValueError:
        return mac_dinh
    if not isinstance(d, dict):
        return mac_dinh
    return {
        "trang_thai": str(d.get("trang_thai") or ""),
        "hong_lien_tiep": int(d.get("hong_lien_tiep") or 0),
        "dung_lai": [str(x) for x in (d.get("dung_lai") or [])],
        "da_bo_cuoc": bool(d.get("da_bo_cuoc")),
    }


def _trong_mot_gio(moc: list[str], bay_gio: datetime) -> list[str]:
    ra = []
    for m in moc:
        try:
            if bay_gio - datetime.fromisoformat(m) < timedelta(hours=1):
                ra.append(m)
        except ValueError:
            continue
    return ra


def quyet_dinh(truoc: dict, *, song: bool, bay_gio: datetime) -> tuple[dict, str | None]:
    """
    Hàm THUẦN: từ trạng thái trước và kết quả thăm dò, quyết định làm gì.

    Trả về (trạng thái mới, việc) với việc là một trong:
      None            không làm gì (vẫn tốt, hoặc vẫn hỏng nhưng đã báo rồi)
      "bao_hong"      lần hỏng đầu — báo, chưa dựng lại
      "dung_lai"      hỏng đủ số lần và còn lượt trong giờ — dựng lại
      "bo_cuoc"       hết lượt trong giờ — báo một lần rồi im
      "bao_phuc_hoi"  sống lại sau khi hỏng
    """
    dung_lai = _trong_mot_gio(truoc.get("dung_lai", []), bay_gio)
    if song:
        moi = {"trang_thai": "tot", "hong_lien_tiep": 0, "dung_lai": dung_lai, "da_bo_cuoc": False}
        return moi, ("bao_phuc_hoi" if truoc.get("trang_thai") == "hong" else None)

    hong = int(truoc.get("hong_lien_tiep") or 0) + 1
    moi = {"trang_thai": "hong", "hong_lien_tiep": hong, "dung_lai": dung_lai,
           "da_bo_cuoc": bool(truoc.get("da_bo_cuoc"))}
    if hong < NGUONG_DUNG_LAI:
        return moi, ("bao_hong" if truoc.get("trang_thai") != "hong" else None)
    if len(dung_lai) < TOI_DA_MOI_GIO:
        moi["dung_lai"] = [*dung_lai, bay_gio.isoformat()]
        return moi, "dung_lai"
    if not moi["da_bo_cuoc"]:
        moi["da_bo_cuoc"] = True
        return moi, "bo_cuoc"
    return moi, None


def _doc_truoc() -> dict:
    try:
        return doc_trang_thai(TRANG_THAI.read_text(encoding="utf-8"))
    except OSError:
        return doc_trang_thai("")


def _ghi(trang_thai: dict) -> None:
    try:
        TRANG_THAI.parent.mkdir(parents=True, exist_ok=True)
        TRANG_THAI.write_text(json.dumps(trang_thai, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _bao(muc_do: str, chi_tiet: str) -> None:
    print(f"[{muc_do}] {chi_tiet}")
    if not settings.canh_gac_webhook:
        return
    # Dùng CHUNG bộ dựng gói tin với canh_gac trong app: một mẫu cấu hình
    # cho cả hai đường báo động, không phải khai hai lần rồi lệch nhau.
    from agent.canh_gac import dung_goi_bao_dong

    goi = json.dumps(dung_goi_bao_dong(
        {
            "muc_do": muc_do,
            "tieu_de": TIEU_DE.get(muc_do, muc_do),
            "chi_tiet": chi_tiet,
            "nguon": "canh_gac_ngoai",
        },
        mau=settings.canh_gac_goi_tin,
    ), ensure_ascii=False).encode()
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


def _song() -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(DIA_CHI, timeout=CHO_GIAY) as r:
            return r.status == 200, f"HTTP {r.status}"
    except (urllib.error.URLError, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def dung_lai() -> tuple[bool, str]:
    """
    Dựng lại bằng đúng bốn bước của `khoi_dong`, KHÔNG đụng tunnel.

    Gọi hàm chứ không gọi `python -m scripts.khoi_dong`: lệnh đó còn bước
    tunnel, và tuỳ cờ nó ghi lại `PUBLIC_BASE_URL` trong `.env`. Người canh
    không được đổi cấu hình công khai sau lưng người vận hành — nó chỉ được
    làm đúng việc "bật lại thứ đã chết".
    """
    from scripts import khoi_dong as k

    ket: list[str] = []
    for ten, buoc in (("Docker", k.buoc_docker), ("Postgres", k.buoc_csdl),
                      ("app", lambda: k.buoc_app(bat_lai=True)), ("sidecar", k.buoc_sidecar)):
        ok, mo_ta = buoc()
        ket.append(f"{ten}: {mo_ta}")
        if not ok:
            return False, " · ".join(ket)
    return True, " · ".join(ket)


def _song_sau_dung_lai() -> bool:
    return _song()[0]


def main() -> int:
    truoc = _doc_truoc()
    song, ly_do = _song()
    moi, viec = quyet_dinh(truoc, song=song, bay_gio=datetime.now(_VN))

    if viec == "bao_hong":
        _bao("hong", f"{DIA_CHI} không trả lời trong {CHO_GIAY}s — {ly_do}. "
                     f"Lần sau còn hỏng sẽ tự dựng lại.")
    elif viec == "dung_lai":
        ok, mo_ta = dung_lai()
        if ok and _song_sau_dung_lai():
            _bao("tu_dung_lai", f"{ly_do} → {mo_ta}")
            moi = {**moi, "trang_thai": "tot", "hong_lien_tiep": 0}
            song = True
        else:
            _bao("tu_dung_lai_hong", f"{ly_do} → {mo_ta}")
    elif viec == "bo_cuoc":
        _bao("bo_cuoc", f"{ly_do}. Đã dựng lại {TOI_DA_MOI_GIO} lần trong một giờ mà vẫn chết — "
                        "cần người xem app.log và chạy python -m scripts.san_sang")
    elif viec == "bao_phuc_hoi":
        _bao("phuc_hoi", f"{DIA_CHI} trả lời bình thường trở lại")
    else:
        print(f"[{moi['trang_thai']}] {ly_do}")

    _ghi(moi)
    # Mã thoát khác 0 khi hỏng, để Task Scheduler và cron cũng biết.
    return 0 if song else 1


if __name__ == "__main__":
    raise SystemExit(main())
