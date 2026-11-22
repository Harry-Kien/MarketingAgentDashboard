"""
Ba mục tiêu SLA, mỗi mục tiêu một CHẾ ĐỘ TÍNH GIỜ và một NGƯỠNG CẢNH BÁO.

  phan_hoi_dau              khách nhắn → tin trả lời THẬT đầu tiên (AI hoặc
                            nhân viên — xem `phan_hoi_that.py`).
  phan_hoi_sau_chuyen_giao  AI chuyển cho người → tin NHÂN VIÊN đầu tiên
                            (`sla_chuyen_giao.py`, mỗi lượt chuyển một hạn).
  giai_quyet                bắt đầu lượt phục vụ → đã giải quyết.

CHẾ ĐỘ: `gio_lam_viec` (đồng hồ chỉ chạy trong giờ mở cửa của LỊCH CHUNG —
`agent/core/lich_lam_viec.py`) hoặc `24_7`. Chọn riêng từng mục tiêu vì
chúng đo những thứ khác nhau: AI trực đêm nên phản hồi đầu có thể đo 24/7,
còn "nhân viên nhận lời sau chuyển giao" lúc 2 giờ sáng thì chỉ đo được
theo giờ có người.

THỨ TỰ ƯU TIÊN
--------------
  chế độ:  dòng `sla_muc_tieu` (dashboard) → công tắc `.env`
           SLA_THEO_GIO_LAM_VIEC cũ (bật = giờ làm việc cho MỌI mục tiêu).
  ngưỡng:  `sla_muc_tieu.nguong_canh_bao` của mục tiêu → ngưỡng chung
           SLA_NGUONG_CANH_BAO (dashboard → `.env`) → 80%.
  giờ:     lịch chung — dashboard → `.env` (xem `lich_lam_viec.py`).

Chưa ai lưu gì trên dashboard thì mọi thứ chạy y như trước bản này.

CÙNG MỘT LỊCH CHO HẠN VÀ CHO ĐO
-------------------------------
Hạn đặt trong SQL (`sla_han_lich`, qua `sla_gio.bieu_thuc_han` với tham số
`tham_so_han()`), cảnh báo sớm và màn Phân tích đo bằng
`lich_lam_viec.tieu_thu` — cả hai lấy lịch từ `lich_cho(muc_tieu)`. Hạn
tính theo giờ làm việc mà cảnh báo đếm 24/7 là cảnh báo tới SAU vi phạm.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent.config import settings
from agent.core import lich_lam_viec
from agent.core.lich_lam_viec import Lich

log = logging.getLogger("agent.sla_muc_tieu")

MUC_TIEU: dict[str, str] = {
    "phan_hoi_dau": "Phản hồi đầu",
    "phan_hoi_sau_chuyen_giao": "Phản hồi sau chuyển giao",
    "giai_quyet": "Giải quyết",
}
CHE_DO: dict[str, str] = {"gio_lam_viec": "Theo giờ làm việc", "24_7": "Liên tục 24/7"}
NGUONG_CANH_BAO_MAC_DINH = 80


@dataclass(frozen=True, slots=True)
class DongMucTieu:
    che_do: str
    nguong_canh_bao: int | None
    sua_boi: str | None = None
    sua_luc: datetime | None = None


_dong: dict[str, DongMucTieu] = {}
_nap_luc: float = 0.0
_dang_loi: bool = False


def _che_do_env() -> str:
    return "gio_lam_viec" if settings.sla_theo_gio_lam_viec else "24_7"


def che_do(muc_tieu: str) -> str:
    _kiem_ma(muc_tieu)
    d = _dong.get(muc_tieu)
    return d.che_do if d else _che_do_env()


def lich_cho(muc_tieu: str) -> Lich | None:
    """Lịch đồng hồ SLA của mục tiêu chạy theo; None = 24/7."""
    if che_do(muc_tieu) == "24_7":
        return None
    lich = lich_lam_viec.hien_hanh()
    return lich if lich.bat else None


def lich_sql(muc_tieu: str) -> str | None:
    """
    Tham số `$n::text::jsonb` cho `sla_han_lich()`. CHUỖI chứ không dict:
    đi qua `::text` thì không phụ thuộc codec JSONB của pool — pool thiếu
    codec mà nhận dict là câu tạo hội thoại nổ.
    """
    lich = lich_cho(muc_tieu)
    j = lich.json_sql() if lich is not None else None
    return json.dumps(j) if j is not None else None


def tham_so_han() -> tuple[str | None, str | None]:
    """(lịch hạn phản hồi đầu, lịch hạn giải quyết) — hai tham số của câu đặt hạn."""
    return lich_sql("phan_hoi_dau"), lich_sql("giai_quyet")


def nguong_chung() -> int:
    """
    `SLA_NGUONG_CANH_BAO` (dashboard → `.env`). Giá trị hỏng lui về 80 chứ
    không ném: worker SLA chết vì một ô cấu hình là mất luôn cả vi phạm.
    """
    from agent import cau_hinh_dong

    try:
        phan_tram = int(str(cau_hinh_dong.lay("SLA_NGUONG_CANH_BAO")).strip())
    except (TypeError, ValueError):
        phan_tram = NGUONG_CANH_BAO_MAC_DINH
    if not 10 <= phan_tram <= 95:
        phan_tram = NGUONG_CANH_BAO_MAC_DINH
    return phan_tram


def nguong(muc_tieu: str) -> float:
    """Phần thời gian cho phép đã dùng thì cảnh báo (0.8 = 80%)."""
    _kiem_ma(muc_tieu)
    d = _dong.get(muc_tieu)
    if d is not None and d.nguong_canh_bao is not None:
        return d.nguong_canh_bao / 100
    return nguong_chung() / 100


def tieu_thu(bat_dau: datetime, ket_thuc: datetime, muc_tieu: str):
    return lich_lam_viec.tieu_thu(bat_dau, ket_thuc, lich_cho(muc_tieu))


def _kiem_ma(muc_tieu: str) -> None:
    if muc_tieu not in MUC_TIEU:
        raise KeyError(f"Mục tiêu SLA lạ: {muc_tieu!r}")


# ---------------------------------------------------------------- nạp / lưu

async def nap(conn: Any = None) -> None:
    """Nạp lại mục tiêu VÀ lịch chung. Không bao giờ ném."""
    global _nap_luc, _dang_loi
    _nap_luc = time.monotonic()
    await lich_lam_viec.nap(conn)
    try:
        sql = "SELECT muc_tieu, che_do, nguong_canh_bao, sua_boi, sua_luc FROM sla_muc_tieu"
        if conn is None:
            from agent import db
            rows = await db.fetch(sql)
        else:
            rows = await conn.fetch(sql)
        moi = {r["muc_tieu"]: DongMucTieu(r["che_do"], r["nguong_canh_bao"],
                                          r["sua_boi"], r["sua_luc"])
               for r in rows if r["muc_tieu"] in MUC_TIEU}
        _dong.clear()
        _dong.update(moi)
        _dang_loi = False
    except Exception as exc:  # noqa: BLE001 — giữ cấu hình đã nạp
        if not _dang_loi:
            log.warning("sla_muc_tieu: không đọc được cấu hình mục tiêu (%s: %s) — dùng %s",
                        type(exc).__name__, exc, "bản đã nạp" if _dong else ".env")
        _dang_loi = True


async def lam_moi_neu_cu(ttl: float = lich_lam_viec.TTL_GIAY, *, conn: Any = None) -> None:
    """Nạp lại nếu bản trong bộ nhớ cũ hơn `ttl` giây. Không bao giờ ném."""
    if time.monotonic() - _nap_luc >= ttl:
        await nap(conn)


def dat_lai_bo_nho() -> None:
    global _nap_luc, _dang_loi
    _dong.clear()
    _nap_luc, _dang_loi = 0.0, False
    lich_lam_viec.dat_lai_bo_nho()


def chuan_hoa(ds: Any) -> list[tuple[str, str, int | None]]:
    """Kiểm danh sách mục tiêu gửi lên; chặn lúc lưu thay vì nuốt lúc chạy."""
    if not isinstance(ds, list) or not ds:
        raise ValueError("Cần ít nhất một mục tiêu.")
    ra: dict[str, tuple[str, str, int | None]] = {}
    for x in ds:
        if not isinstance(x, dict) or x.get("ma") not in MUC_TIEU:
            raise ValueError(f"Mục tiêu không hợp lệ: {x!r}"[:120])
        if x.get("che_do") not in CHE_DO:
            raise ValueError(f"{MUC_TIEU[x['ma']]}: chế độ phải là giờ làm việc hoặc 24/7.")
        n = x.get("nguong_canh_bao")
        nguong_moi: int | None
        if n is None or n == "":
            nguong_moi = None
        else:
            try:
                nguong_moi = int(n)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{MUC_TIEU[x['ma']]}: ngưỡng cảnh báo là số nguyên 10–95.") from exc
            if not 10 <= nguong_moi <= 95:
                raise ValueError(f"{MUC_TIEU[x['ma']]}: ngưỡng cảnh báo là số nguyên 10–95.")
        ra[x["ma"]] = (x["ma"], x["che_do"], nguong_moi)
    return list(ra.values())


async def luu(ds: Any, *, sua_boi: str) -> None:
    from agent import db

    dong = chuan_hoa(ds)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            for ma, cd, ng in dong:
                await conn.execute(
                    "INSERT INTO sla_muc_tieu (muc_tieu, che_do, nguong_canh_bao, sua_boi, sua_luc) "
                    "VALUES ($1, $2, $3, $4, now()) ON CONFLICT (muc_tieu) DO UPDATE SET "
                    "che_do = EXCLUDED.che_do, nguong_canh_bao = EXCLUDED.nguong_canh_bao, "
                    "sua_boi = EXCLUDED.sua_boi, sua_luc = now()", ma, cd, ng, sua_boi)
    await db.log_event("sla.muc_tieu_doi", actor=sua_boi,
                       muc_tieu={ma: {"che_do": cd, "nguong": ng} for ma, cd, ng in dong})
    await nap()


def mo_ta() -> list[dict[str, Any]]:
    """Mỗi mục tiêu: chế độ, ngưỡng đang hiệu lực và chúng đến từ đâu."""
    ra = []
    for ma, ten in MUC_TIEU.items():
        d = _dong.get(ma)
        ra.append({
            "ma": ma, "ten": ten, "che_do": che_do(ma),
            "nguon_che_do": "csdl" if d else "env",
            "nguong_canh_bao": d.nguong_canh_bao if d else None,
            "nguong_hieu_luc": round(nguong(ma) * 100),
            "sua_boi": d.sua_boi if d else None,
            "sua_luc": d.sua_luc.isoformat() if d and d.sua_luc else None,
        })
    return ra
