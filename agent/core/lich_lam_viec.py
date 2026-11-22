"""
Lịch làm việc CHUNG của cửa hàng — một nguồn cho mọi câu hỏi "giờ này có
người không".

VÌ SAO CÓ MÔ-ĐUN NÀY
--------------------
Rà soát 22.11.2026 tìm ra BA nguồn giờ làm việc:

  * `.env` GIO_LAM_VIEC_* — câu báo khách khi chuyển người ngoài giờ
    (`gio_lam_viec.tin_chuyen_nguoi`), điều kiện "ngoài giờ" của quy tắc tự
    động (`tu_dong.py`), cảnh báo sức khoẻ (`suc_khoe.py`);
  * cùng ô ấy truyền vào `sla_han()` để tính hạn SLA;
  * `sla_policies.business_hours` — giờ riêng từng chính sách SLA.

Ba nơi đọc ba thứ là ba giờ mở cửa cho một shop: khách nghe "8 giờ có
người" trong khi hạn SLA chạy từ 9 giờ, và chẳng nơi nào biết ngày nghỉ lễ.

THỨ TỰ ƯU TIÊN (đọc từ trên xuống, gặp là dừng)
-----------------------------------------------
  1. Lịch lưu trên dashboard (bảng `lich_lam_viec`, migration 0062): giờ mở
     và đóng THEO TỪNG THỨ, ngày nghỉ trong tuần, danh sách ngày lễ. Đã có
     lịch này thì nó là nguồn DUY NHẤT — `business_hours` của chính sách SLA
     thôi có tác dụng (dashboard nói rõ điều ấy).
  2. Chưa ai lưu lịch → `.env` GIO_LAM_VIEC_BAT / _BAT_DAU / _KET_THUC, cùng
     một khung giờ cho mọi ngày, không ngày lễ — đúng hành vi trước bản này,
     kể cả giờ riêng của chính sách SLA (`gio_rieng`, xem 0062).

Lịch nói GIỜ NÀO mở cửa. Mục tiêu SLA nào tính theo giờ ấy, mục tiêu nào
tính 24/7, là việc của `agent/omnichannel/sla_muc_tieu.py`.

VÌ SAO ĐỌC ĐỒNG BỘ TỪ BỘ NHỚ
----------------------------
`dang_trong_gio()` được gọi từ chỗ không có `await` (và đã có test giả nó
như hàm thường). Lịch nạp vào bộ nhớ lúc khởi động, sau mỗi lần lưu, mỗi
vòng canh SLA, và tự làm mới sau `TTL_GIAY` ở các đường xử lý tin
(`lam_moi_neu_cu`) — để tiến trình chỉ giữ vai `api` cũng thấy lịch mới mà
không cần khởi động lại.

Đọc CSDL hỏng thì GIỮ lịch đã nạp (hoặc `.env` nếu chưa từng nạp được) và
ghi CẢNH BÁO một lần mỗi lần chuyển từ được sang hỏng — không im lặng,
nhưng cũng không ghi một dòng mỗi tin khách.

MÚI GIỜ: UTC+7 cố định, cộng tay — xem `gio_lam_viec.py`.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..config import settings

log = logging.getLogger("agent.lich_lam_viec")

# Việt Nam: UTC+7 cố định, không có giờ mùa hè.
VN = timezone(timedelta(hours=7))
PHUT_NGAY = 24 * 60
THU = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật")
TOI_DA_NGAY_NGHI = 200
TTL_GIAY = 30.0

Khung = tuple[int, int]


def gio_vn(bay_gio: datetime | None = None) -> datetime:
    t = bay_gio or datetime.now(timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(VN)


def _nua_dem(ngay: date) -> datetime:
    return datetime(ngay.year, ngay.month, ngay.day, tzinfo=VN)


@dataclass(frozen=True, slots=True)
class Lich:
    """
    `tuan[0]` là Thứ Hai. Mỗi phần tử (phút mở, phút đóng) trong ngày,
    nửa mở `[mo, dong)` — `dong = 1260` nghĩa là 20:59 còn trong giờ, 21:00
    thì hết; None = nghỉ cả ngày.
    """
    bat: bool
    tuan: tuple[Khung | None, ...]
    ngay_nghi: tuple[tuple[date, str], ...] = ()
    nguon: str = "env"          # "csdl" | "env"
    sua_boi: str | None = None
    sua_luc: datetime | None = None

    @property
    def gio_rieng(self) -> bool:
        """Giờ riêng của chính sách SLA còn tác dụng không — chỉ khi lui về `.env`."""
        return self.nguon == "env"

    def co_gio_mo(self) -> bool:
        return any(k is not None for k in self.tuan)

    def _nghi(self) -> frozenset[date]:
        return frozenset(d for d, _ in self.ngay_nghi)

    def khung(self, ngay: date, nghi: frozenset[date] | None = None) -> Khung | None:
        if ngay in (self._nghi() if nghi is None else nghi):
            return None
        return self.tuan[ngay.weekday()]

    def dang_mo(self, bay_gio: datetime | None = None) -> bool:
        """
        Giờ này có người trực không. Tắt giờ làm việc, hoặc lịch không có
        ngày mở nào (cấu hình vô lý) → coi như trực suốt: hỏng theo hướng
        phục vụ khách, không theo hướng đóng cửa suốt ngày.
        """
        if not self.bat or not self.co_gio_mo():
            return True
        t = gio_vn(bay_gio)
        k = self.khung(t.date())
        if k is None:
            return False
        goc = _nua_dem(t.date())
        return goc + timedelta(minutes=k[0]) <= t < goc + timedelta(minutes=k[1])

    def lan_mo_ke_tiep(self, bay_gio: datetime | None = None) -> datetime | None:
        """Lúc có người gần nhất kể từ `bay_gio` (chính nó nếu đang trong giờ)."""
        t = gio_vn(bay_gio)
        if not self.bat or not self.co_gio_mo():
            return t
        nghi = self._nghi()
        for i in range(400):
            ngay = t.date() + timedelta(days=i)
            k = self.khung(ngay, nghi)
            if k is None:
                continue
            mo = _nua_dem(ngay) + timedelta(minutes=k[0])
            dong = _nua_dem(ngay) + timedelta(minutes=k[1])
            if t < mo:
                return mo
            if t < dong:
                return t
        return None

    def json_sql(self) -> dict[str, Any] | None:
        """
        Dạng truyền vào `sla_han_lich()` (0062). None = đồng hồ chạy 24/7.
        Hai bên (SQL đặt hạn, Python đo thời gian) đọc CÙNG một dạng này —
        test canh hai phép tính khớp nhau.
        """
        if not self.bat:
            return None
        return {"tuan": [list(k) if k else None for k in self.tuan],
                "nghi": sorted(d.isoformat() for d, _ in self.ngay_nghi),
                "gio_rieng": self.gio_rieng}


def tieu_thu(bat_dau: datetime, ket_thuc: datetime, lich: Lich | None) -> timedelta:
    """
    Thời gian TÍNH SLA giữa hai mốc: chỉ phần nằm trong giờ mở cửa của
    `lich`; `lich` None (hay tắt, hay không có ngày mở) → đồng hồ 24/7.
    Cùng luật với `sla_han_lich()` trong SQL.
    """
    if ket_thuc <= bat_dau:
        return timedelta(0)
    if lich is None or not lich.bat or not lich.co_gio_mo():
        return ket_thuc - bat_dau
    a, b = gio_vn(bat_dau), gio_vn(ket_thuc)
    nghi = lich._nghi()
    tong = timedelta(0)
    ngay = a.date()
    while ngay <= b.date():
        k = lich.khung(ngay, nghi)
        if k is not None:
            goc = _nua_dem(ngay)
            dau = max(a, goc + timedelta(minutes=k[0]))
            cuoi = min(b, goc + timedelta(minutes=k[1]))
            if cuoi > dau:
                tong += cuoi - dau
        ngay += timedelta(days=1)
    return tong


def han(bat_dau: datetime, phut: int, lich: Lich | None) -> datetime:
    """Bản Python của `sla_han_lich()` — dùng trong test đối chiếu và ước lượng."""
    con = timedelta(minutes=max(phut, 0))
    if lich is None or not lich.bat or not lich.co_gio_mo():
        return bat_dau + con
    nghi = lich._nghi()
    t = gio_vn(bat_dau)
    for _ in range(3700):
        ngay = t.date()
        goc = _nua_dem(ngay)
        k = lich.khung(ngay, nghi)
        if k is None:
            t = goc + timedelta(days=1)
            continue
        mo, dong = goc + timedelta(minutes=k[0]), goc + timedelta(minutes=k[1])
        t = max(t, mo)
        if t >= dong:
            t = goc + timedelta(days=1)
            continue
        if con <= dong - t:
            return t + con
        con -= dong - t
        t = goc + timedelta(days=1)
    return bat_dau + timedelta(minutes=max(phut, 0))


# ---------------------------------------------------------------- nguồn .env

def lich_env() -> Lich:
    """
    Lịch dựng từ `.env`, đọc LÚC GỌI (test và người vận hành đổi `settings`
    là có hiệu lực ngay). Giờ vô lý (mở >= đóng) → không ngày nào có khung
    → trực suốt, đúng quy ước cũ của `dang_trong_gio()` và `sla_han()`.
    """
    mo, dong = int(settings.gio_lam_viec_bat_dau), int(settings.gio_lam_viec_ket_thuc)
    khung: Khung | None = (mo * 60, dong * 60) if 0 <= mo < dong <= 24 else None
    return Lich(bat=bool(settings.gio_lam_viec_bat), tuan=(khung,) * 7, nguon="env")


# ---------------------------------------------------------------- bộ nhớ đệm

_lich_csdl: Lich | None = None
_nap_luc: float = 0.0
_dang_loi: bool = False


def hien_hanh() -> Lich:
    """Lịch đang có hiệu lực: lịch lưu trên dashboard, không có thì `.env`."""
    return _lich_csdl if _lich_csdl is not None else lich_env()


def _tu_dong(r: Any) -> Lich:
    tuan = r["tuan"]
    nghi = r["ngay_nghi"]
    if isinstance(tuan, str):          # CSDL không có codec JSONB (test thô)
        import json
        tuan, nghi = json.loads(tuan), json.loads(nghi)
    return Lich(
        bat=bool(r["bat"]),
        tuan=tuple((int(k[0]), int(k[1])) if k else None for k in tuan),
        ngay_nghi=tuple((date.fromisoformat(x["ngay"]), str(x.get("ten") or ""))
                        for x in nghi),
        nguon="csdl", sua_boi=r["sua_boi"], sua_luc=r["sua_luc"])


async def nap(conn: Any = None) -> Lich:
    """
    Đọc lại lịch từ CSDL. Không bao giờ ném: hỏng thì giữ lịch đang dùng và
    cảnh báo (một lần mỗi lần chuyển sang hỏng).
    """
    global _lich_csdl, _nap_luc, _dang_loi
    _nap_luc = time.monotonic()
    try:
        sql = ("SELECT bat, tuan, ngay_nghi, sua_boi, sua_luc "
               "FROM lich_lam_viec WHERE id = 1")
        if conn is None:
            from agent import db
            r = await db.fetchrow(sql)
        else:
            r = await conn.fetchrow(sql)
        _lich_csdl = _tu_dong(r) if r else None
        if _dang_loi:
            log.warning("lich_lam_viec: đọc lại được lịch từ CSDL")
        _dang_loi = False
    except Exception as exc:  # noqa: BLE001 — không làm chết đường gọi
        if not _dang_loi:
            log.warning("lich_lam_viec: không đọc được lịch (%s: %s) — dùng %s",
                        type(exc).__name__, exc,
                        "lịch đã nạp trước đó" if _lich_csdl else ".env")
        _dang_loi = True
    return hien_hanh()


async def lam_moi_neu_cu(ttl: float = TTL_GIAY) -> None:
    if time.monotonic() - _nap_luc >= ttl:
        await nap()


def dat_lai_bo_nho() -> None:
    """Cho test: quên lịch đã nạp, quay về `.env` cho tới lần nạp sau."""
    global _lich_csdl, _nap_luc, _dang_loi
    _lich_csdl, _nap_luc, _dang_loi = None, 0.0, False


# ---------------------------------------------------------------- kiểm & lưu

_GIO = re.compile(r"^(\d{1,2}):(\d{2})$")


def _phut(chu: Any, ten: str, *, cho_24: bool) -> int:
    m = _GIO.match(str(chu or "").strip())
    if not m:
        raise ValueError(f"{ten}: cần dạng GG:PP, ví dụ 08:30.")
    gio, phut = int(m.group(1)), int(m.group(2))
    if phut > 59 or gio > 24 or (gio == 24 and (phut or not cho_24)):
        raise ValueError(f"{ten}: giờ không hợp lệ.")
    return gio * 60 + phut


def chuan_hoa(du_lieu: dict[str, Any]) -> tuple[bool, list[list[int] | None], list[dict[str, str]]]:
    """
    Kiểm lịch người quản trị gửi lên, trả (bật, tuần, ngày nghỉ) ở dạng lưu.

    Chặn NGAY LÚC LƯU, không nuốt: một lịch lưu "thành công" mà hỏng thì mọi
    hạn SLA lặng lẽ chạy 24/7 (SQL lui về 24/7 để không chặn việc tạo hội
    thoại) trong khi dashboard nói đã có lịch.
    """
    bat = bool(du_lieu.get("bat", True))
    tuan_vao = du_lieu.get("tuan")
    if not isinstance(tuan_vao, list) or len(tuan_vao) != 7:
        raise ValueError("Lịch tuần cần đủ 7 ngày, Thứ Hai trước.")
    tuan: list[list[int] | None] = []
    for thu, ngay in zip(THU, tuan_vao, strict=True):
        if not isinstance(ngay, dict):
            raise ValueError(f"{thu}: dữ liệu không hợp lệ.")
        if ngay.get("nghi"):
            tuan.append(None)
            continue
        mo = _phut(ngay.get("mo"), f"{thu} — giờ mở", cho_24=False)
        dong = _phut(ngay.get("dong"), f"{thu} — giờ đóng", cho_24=True)
        if mo >= dong:
            raise ValueError(f"{thu}: giờ mở phải trước giờ đóng (không hỗ trợ ca qua đêm).")
        tuan.append([mo, dong])
    if bat and not any(tuan):
        raise ValueError("Không ngày nào mở cửa. Trực 24/7 thì tắt giờ làm việc thay vì đóng cả tuần.")
    ds = du_lieu.get("ngay_nghi") or []
    if not isinstance(ds, list) or len(ds) > TOI_DA_NGAY_NGHI:
        raise ValueError(f"Danh sách ngày nghỉ lễ tối đa {TOI_DA_NGAY_NGHI} ngày.")
    nghi: dict[str, str] = {}
    for x in ds:
        if not isinstance(x, dict):
            raise ValueError("Ngày nghỉ lễ không hợp lệ.")
        try:
            d = date.fromisoformat(str(x.get("ngay") or "").strip())
        except ValueError as exc:
            raise ValueError(f"Ngày nghỉ {x.get('ngay')!r}: cần dạng NNNN-TT-NN.") from exc
        ten = " ".join(str(x.get("ten") or "").split())[:80]
        if d.isoformat() in nghi:
            raise ValueError(f"Ngày nghỉ {d.isoformat()} bị lặp.")
        nghi[d.isoformat()] = ten
    return bat, tuan, [{"ngay": k, "ten": v} for k, v in sorted(nghi.items())]


async def luu(du_lieu: dict[str, Any], *, sua_boi: str) -> Lich:
    from agent import db

    bat, tuan, nghi = chuan_hoa(du_lieu)
    await db.execute(
        "INSERT INTO lich_lam_viec (id, bat, tuan, ngay_nghi, sua_boi, sua_luc) "
        "VALUES (1, $1, $2::text::jsonb, $3::text::jsonb, $4, now()) "
        "ON CONFLICT (id) DO UPDATE SET bat = EXCLUDED.bat, tuan = EXCLUDED.tuan, "
        "ngay_nghi = EXCLUDED.ngay_nghi, sua_boi = EXCLUDED.sua_boi, sua_luc = now()",
        bat, _json(tuan), _json(nghi), sua_boi)
    await db.log_event("lich_lam_viec.doi", actor=sua_boi, bat=bat,
                       so_ngay_mo=sum(1 for k in tuan if k), so_ngay_le=len(nghi))
    return await nap()


async def xoa(*, sua_boi: str) -> Lich:
    """Bỏ lịch trên dashboard: mọi nơi quay về `.env`."""
    from agent import db

    await db.execute("DELETE FROM lich_lam_viec WHERE id = 1")
    await db.log_event("lich_lam_viec.xoa", actor=sua_boi)
    return await nap()


def _json(x: Any) -> str:
    import json
    return json.dumps(x, ensure_ascii=False)


def mo_ta(lich: Lich) -> dict[str, Any]:
    """Dạng trả cho dashboard: giờ GG:PP để ô nhập dùng thẳng."""
    def gg(p: int) -> str:
        return f"{p // 60:02d}:{p % 60:02d}"
    return {
        "nguon": lich.nguon, "bat": lich.bat,
        "tuan": [{"thu": THU[i], "nghi": k is None,
                  "mo": gg(k[0]) if k else "", "dong": gg(k[1]) if k else ""}
                 for i, k in enumerate(lich.tuan)],
        "ngay_nghi": [{"ngay": d.isoformat(), "ten": t} for d, t in lich.ngay_nghi],
        "sua_boi": lich.sua_boi,
        "sua_luc": lich.sua_luc.isoformat() if lich.sua_luc else None,
    }
