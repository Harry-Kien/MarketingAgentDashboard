"""
Sổ yêu cầu của chủ thể dữ liệu, kèm thời hạn luật định.

CĂN CỨ
------
Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 Điều 4 khoản 1 (quyền của chủ thể)
và Điều 4 khoản 5 (bên kiểm soát phải thực hiện trong thời hạn luật định);
thời hạn cụ thể ở Nghị định 356/2025/NĐ-CP Điều 5:

    phản hồi ban đầu                 2 ngày làm việc   (mọi loại)
    xem / sửa / cung cấp            10 ngày  · 15 nếu nhờ bên thứ ba · gia hạn ≤10
    rút đồng ý / hạn chế / phản đối 15 ngày  · 20                    · gia hạn ≤15
    xoá                             20 ngày  · 30                    · gia hạn ≤20
    áp biện pháp bảo vệ             15 ngày                          · gia hạn ≤15

Gia hạn tối đa một lần, phải nêu lý do và báo cho chủ thể.

TÍNH HẠN THEO HƯỚNG AN TOÀN
---------------------------
"Ngày làm việc" ở đây chỉ bỏ thứ Bảy, Chủ nhật — KHÔNG trừ ngày lễ. Bỏ sót
ngày lễ làm hạn đến SỚM hơn luật cho phép, không bao giờ muộn hơn. Sai về
phía sớm là nhân viên làm sớm một hôm; sai về phía muộn là vi phạm.

Hạn là CUỐI ngày (00:00 ngày kế tiếp, giờ Việt Nam): "trong 10 ngày" kể từ
ngày nhận nghĩa là hết ngày thứ mười, không phải đúng giờ nhận của ngày ấy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

VN = timezone(timedelta(hours=7))

CAN_CU = "Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 Điều 4; Nghị định 356/2025/NĐ-CP Điều 5"


@dataclass(frozen=True, slots=True)
class LoaiYeuCau:
    ten: str
    ngay: int
    ngay_ben_thu_ba: int
    gia_han_toi_da: int


LOAI: dict[str, LoaiYeuCau] = {
    "xem": LoaiYeuCau("Xem / cung cấp dữ liệu", 10, 15, 10),
    "sua": LoaiYeuCau("Sửa dữ liệu", 10, 15, 10),
    "xoa": LoaiYeuCau("Xoá dữ liệu", 20, 30, 20),
    "rut_dong_y": LoaiYeuCau("Rút lại sự đồng ý", 15, 20, 15),
    "han_che": LoaiYeuCau("Hạn chế xử lý", 15, 20, 15),
    "phan_doi": LoaiYeuCau("Phản đối xử lý", 15, 20, 15),
    "bao_ve": LoaiYeuCau("Áp biện pháp bảo vệ", 15, 15, 15),
}
NGAY_LAM_VIEC_PHAN_HOI = 2
KENH_NHAN = ("chat", "dien_thoai", "email", "truc_tiep", "van_ban")


class YeuCauHong(ValueError):
    """Thao tác không hợp lệ — thông báo đọc được cho người vận hành."""


def _cuoi_ngay(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time(0), tzinfo=VN)


def han_phan_hoi(nhan_luc: datetime) -> datetime:
    """Cuối ngày làm việc thứ hai SAU ngày nhận."""
    d = nhan_luc.astimezone(VN).date()
    dem = 0
    while dem < NGAY_LAM_VIEC_PHAN_HOI:
        d += timedelta(days=1)
        if d.isoweekday() <= 5:
            dem += 1
    return _cuoi_ngay(d)


def han_xu_ly(loai: str, nhan_luc: datetime, *, co_ben_thu_ba: bool = False) -> datetime:
    lc = LOAI[loai]
    so = lc.ngay_ben_thu_ba if co_ben_thu_ba else lc.ngay
    return _cuoi_ngay(nhan_luc.astimezone(VN).date() + timedelta(days=so))


def han_hien_hanh(r: dict[str, Any]) -> datetime:
    return r.get("gia_han_den") or r["han_xu_ly"]


def tinh_trang(r: dict[str, Any], bay_gio: datetime) -> str:
    """qua_han | qua_han_phan_hoi | sap_het_han (≤ 2 ngày) | dung_han | xong."""
    if r["trang_thai"] in ("da_xong", "tu_choi"):
        return "xong"
    if bay_gio >= han_hien_hanh(r):
        return "qua_han"
    if r["trang_thai"] == "moi" and bay_gio >= r["han_phan_hoi"]:
        return "qua_han_phan_hoi"
    if han_hien_hanh(r) - bay_gio <= timedelta(days=2):
        return "sap_het_han"
    return "dung_han"


def _dong(r: dict[str, Any], bay_gio: datetime) -> dict[str, Any]:
    iso = lambda v: v.isoformat() if v else None  # noqa: E731
    return {
        "id": str(r["id"]), "loai": r["loai"], "ten_loai": LOAI[r["loai"]].ten,
        "kenh_nhan": r["kenh_nhan"], "noi_dung": r["noi_dung"],
        "co_ben_thu_ba": r["co_ben_thu_ba"], "co_dau_van_tay": bool(r["dau_van_tay"]),
        "nhan_luc": iso(r["nhan_luc"]), "han_phan_hoi": iso(r["han_phan_hoi"]),
        "han_xu_ly": iso(han_hien_hanh(r)), "da_gia_han": r["gia_han_den"] is not None,
        "ly_do_gia_han": r["ly_do_gia_han"], "phan_hoi_luc": iso(r["phan_hoi_luc"]),
        "xong_luc": iso(r["xong_luc"]), "trang_thai": r["trang_thai"], "ket_qua": r["ket_qua"],
        "tinh_trang": tinh_trang(r, bay_gio),
    }


# ---------------------------------------------------------------- CSDL

async def tao(*, loai: str, sdt: str = "", kenh_nhan: str = "chat", noi_dung: str = "",
              co_ben_thu_ba: bool = False, nhan_luc: datetime | None = None,
              tao_boi: UUID | None = None) -> dict[str, Any]:
    from agent import db
    from agent.core import du_lieu_ca_nhan

    if loai not in LOAI:
        raise YeuCauHong(f"loại yêu cầu phải là một trong: {', '.join(LOAI)}")
    if kenh_nhan not in KENH_NHAN:
        raise YeuCauHong(f"kênh nhận phải là một trong: {', '.join(KENH_NHAN)}")
    bay_gio = datetime.now(timezone.utc)
    nhan = nhan_luc or bay_gio
    if nhan.tzinfo is None:
        raise YeuCauHong("thời điểm nhận phải kèm múi giờ")
    if nhan > bay_gio + timedelta(minutes=5):
        raise YeuCauHong("thời điểm nhận không được ở tương lai")
    dau = ""
    if sdt.strip():
        so = du_lieu_ca_nhan.chuan_hoa_sdt(sdt)
        if not 9 <= len(so) <= 11:
            raise YeuCauHong("số điện thoại không hợp lệ (9–11 chữ số)")
        dau = du_lieu_ca_nhan._dau_van_tay(so)
    r = await db.fetchrow(
        "INSERT INTO yeu_cau_chu_the (loai, dau_van_tay, kenh_nhan, noi_dung, co_ben_thu_ba, "
        "nhan_luc, han_phan_hoi, han_xu_ly, tao_boi) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",
        loai, dau, kenh_nhan, noi_dung.strip()[:500], co_ben_thu_ba, nhan,
        han_phan_hoi(nhan), han_xu_ly(loai, nhan, co_ben_thu_ba=co_ben_thu_ba), tao_boi)
    assert r is not None
    await db.log_event("bvdlcn.yeu_cau_moi", ref_id=r["id"], loai=loai, can_cu=CAN_CU)
    return _dong(r, bay_gio)


async def liet_ke(*, ca_da_xong: bool = False) -> list[dict[str, Any]]:
    from agent import db

    dk = "" if ca_da_xong else "WHERE trang_thai IN ('moi','da_phan_hoi') "
    rows = await db.fetch(f"SELECT * FROM yeu_cau_chu_the {dk}"  # noqa: S608 — dk là hằng
                          "ORDER BY coalesce(gia_han_den, han_xu_ly) LIMIT 500")
    bay_gio = datetime.now(timezone.utc)
    return [_dong(r, bay_gio) for r in rows]


async def _lay_mo(db, yid: UUID) -> dict[str, Any]:
    r = await db.fetchrow("SELECT * FROM yeu_cau_chu_the WHERE id = $1", yid)
    if r is None:
        raise LookupError("Không thấy yêu cầu.")
    if r["trang_thai"] in ("da_xong", "tu_choi"):
        raise YeuCauHong("yêu cầu đã đóng")
    return r


async def da_phan_hoi(yid: UUID, *, boi: UUID | None) -> dict[str, Any]:
    from agent import db

    await _lay_mo(db, yid)
    r = await db.fetchrow(
        "UPDATE yeu_cau_chu_the SET trang_thai = 'da_phan_hoi', phan_hoi_luc = now(), xu_ly_boi = $2 "
        "WHERE id = $1 AND trang_thai = 'moi' RETURNING *", yid, boi)
    if r is None:
        raise YeuCauHong("yêu cầu đã được phản hồi rồi")
    await db.log_event("bvdlcn.da_phan_hoi", ref_id=yid, can_cu=CAN_CU)
    return _dong(r, datetime.now(timezone.utc))


async def gia_han(yid: UUID, *, so_ngay: int, ly_do: str, boi: UUID | None) -> dict[str, Any]:
    from agent import db

    cu = await _lay_mo(db, yid)
    if cu["gia_han_den"] is not None:
        raise YeuCauHong("Nghị định 356/2025 chỉ cho gia hạn MỘT lần — yêu cầu này đã gia hạn")
    toi_da = LOAI[cu["loai"]].gia_han_toi_da
    if not 1 <= so_ngay <= toi_da:
        raise YeuCauHong(f"gia hạn {LOAI[cu['loai']].ten.lower()} tối đa {toi_da} ngày")
    if len(ly_do.strip()) < 5:
        raise YeuCauHong("gia hạn phải nêu lý do (và báo cho khách)")
    if datetime.now(timezone.utc) >= cu["han_xu_ly"]:
        # Gia hạn sau khi đã quá hạn là hợp thức hoá một vi phạm đã xảy ra.
        raise YeuCauHong("đã quá hạn — không gia hạn được nữa, xử lý ngay")
    r = await db.fetchrow_chac(
        "UPDATE yeu_cau_chu_the SET gia_han_den = han_xu_ly + make_interval(days => $2), "
        "ly_do_gia_han = $3, xu_ly_boi = $4 WHERE id = $1 RETURNING *",
        yid, so_ngay, ly_do.strip()[:300], boi)
    await db.log_event("bvdlcn.gia_han", ref_id=yid, so_ngay=so_ngay, can_cu=CAN_CU)
    return _dong(r, datetime.now(timezone.utc))


async def dong(yid: UUID, *, ket_qua: str, tu_choi: bool = False, boi: UUID | None) -> dict[str, Any]:
    from agent import db

    await _lay_mo(db, yid)
    if tu_choi and len(ket_qua.strip()) < 5:
        raise YeuCauHong("từ chối phải nêu căn cứ (Luật 91/2025 Điều 14 khoản 2, Điều 19)")
    r = await db.fetchrow_chac(
        "UPDATE yeu_cau_chu_the SET trang_thai = $2, xong_luc = now(), ket_qua = $3, xu_ly_boi = $4, "
        "phan_hoi_luc = coalesce(phan_hoi_luc, now()) WHERE id = $1 RETURNING *",
        yid, "tu_choi" if tu_choi else "da_xong", ket_qua.strip()[:500], boi)
    await db.log_event("bvdlcn.tu_choi" if tu_choi else "bvdlcn.da_xong", ref_id=yid,
                       qua_han=datetime.now(timezone.utc) >= han_hien_hanh(r), can_cu=CAN_CU)
    return _dong(r, datetime.now(timezone.utc))


async def dong_yeu_cau_xoa_theo_sdt(so_chuan: str, *, ket_qua: str) -> int:
    """
    Gọi SAU khi xoá xong dữ liệu của một số: đóng mọi yêu cầu xoá đang mở
    của số ấy. Không có bước này thì dữ liệu đã xoá mà sổ vẫn báo "quá
    hạn" — đỏ giả, và người ta thôi tin cái sổ.
    """
    from agent import db
    from agent.core import du_lieu_ca_nhan

    rows = await db.fetch(
        "UPDATE yeu_cau_chu_the SET trang_thai = 'da_xong', xong_luc = now(), ket_qua = $2, "
        "phan_hoi_luc = coalesce(phan_hoi_luc, now()) "
        "WHERE loai = 'xoa' AND dau_van_tay = $1 AND trang_thai IN ('moi','da_phan_hoi') RETURNING id",
        du_lieu_ca_nhan._dau_van_tay(so_chuan), ket_qua[:500])
    for r in rows:
        await db.log_event("bvdlcn.da_xong", ref_id=r["id"], tu_dong=True, can_cu=CAN_CU)
    return len(rows)


async def dem_canh_bao() -> dict[str, int]:
    """Cho san_sang và dashboard: bao nhiêu yêu cầu quá hạn / sắp hết hạn."""
    ds = await liet_ke()
    dem = {"qua_han": 0, "qua_han_phan_hoi": 0, "sap_het_han": 0, "dang_mo": len(ds)}
    for d in ds:
        if d["tinh_trang"] in dem:
            dem[d["tinh_trang"]] += 1
    return dem
