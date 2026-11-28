"""
API công việc.

Phạm vi giống họ với khách: ai có `cong_viec.xem_tat_ca` thấy hết, còn lại
chỉ thấy việc mình nhận, việc mình giao, và việc CHƯA GIAO cho ai.

Vế cuối là cố ý. Việc do agent đẩy sang luôn ra đời ở trạng thái chưa giao
— nếu người trực không thấy nó thì cả khối này vô nghĩa. Nhưng việc chưa
giao gắn hội thoại chỉ thành viên kênh ấy thấy — xem `dieu_kien_pham_vi`.
Sửa và xoá chịu cùng phạm vi KÊNH với xem.

HỆ THỐNG GIAO VIỆC (phiếu việc mục 14)
--------------------------------------
  · Bốn trạng thái giữ MÃ cũ (`moi`, `dang_lam`, `xong`, `huy`), nhãn mới:
    Chờ xử lý, Đang thực hiện, Hoàn thành, Đã hủy. "Chưa phân công" là việc
    còn mở mà `nguoi_nhan IS NULL` — bộ lọc, không phải trạng thái thứ năm.
  · Giao tay (`cong_viec.giao`) hoặc tự động (`giao_tu_dong`, luật ở
    `agent/core/giao_viec.py`). Tự động không tìm được ai thì để Chưa phân
    công và báo người điều phối — không bao giờ giao "gần đúng".
  · Mọi đổi người nhận / trạng thái / kết quả vào `cong_viec_lich_su` bằng
    trigger (0061); API chỉ nói cho trigger biết AI làm và VÌ SAO
    (`cong_viec.dat_ngu_canh`). Tiến độ là dòng lịch sử ghi tay.
  · Chuông: được giao, được chuyển, việc bị hủy, việc chưa phân công, quá hạn.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.core import cong_viec as cv
from agent.core import giao_viec, thong_bao_noi_bo

from .routes import can_quyen

router = APIRouter(prefix="/api/cong-viec", tags=["cong-viec"])

_CHON = (
    "cong_viec.id, cong_viec.tieu_de, cong_viec.mo_ta, cong_viec.trang_thai, "
    "cong_viec.uu_tien, cong_viec.han, cong_viec.nguon, "
    "cong_viec.nguoi_nhan, cong_viec.nguoi_giao, cong_viec.contact_id, "
    "cong_viec.conversation_id, cong_viec.order_id, cong_viec.loai_xu_ly_don, "
    "cong_viec.ket_qua_xu_ly_don, cong_viec.ly_do_ket_qua, "
    "cong_viec.erp_tham_chieu, cong_viec.erp_trang_thai, "
    "cong_viec.erp_sua_luc, cong_viec.xu_ly_boi, cong_viec.xu_ly_luc, "
    "cong_viec.ket_qua, cong_viec.sua_luc, "
    "cong_viec.tao_luc, cong_viec.xong_luc, don.ma_don, "
    "don.trang_thai AS order_trang_thai, "
    "don.erp_ma_don AS order_erp_ma_don, "
    "nhan.ho_ten AS nguoi_nhan_ten, giao.ho_ten AS nguoi_giao_ten, "
    "xu_ly.ho_ten AS xu_ly_boi_ten, khach.display_name AS khach_ten, "
    "td.so_tien_do, td.tien_do_luc, td.tien_do_cuoi"
)
_JOIN = (
    "FROM cong_viec "
    "LEFT JOIN nguoi_dung nhan ON nhan.id = cong_viec.nguoi_nhan "
    "LEFT JOIN nguoi_dung giao ON giao.id = cong_viec.nguoi_giao "
    "LEFT JOIN nguoi_dung xu_ly ON xu_ly.id = cong_viec.xu_ly_boi "
    "LEFT JOIN orders don ON don.id = cong_viec.order_id "
    "LEFT JOIN contacts khach ON khach.id = cong_viec.contact_id "
    # TIẾN ĐỘ trên dòng việc (UX-14-01): đếm và dòng tiến độ mới nhất, đọc từ
    # chính lịch sử — không có cột "phần trăm" nào để người ta điền 80% cho
    # một việc chưa ai gọi khách. Chỉ mục (cong_viec_id, tao_luc) của 0061
    # làm câu này rẻ.
    "LEFT JOIN LATERAL (SELECT count(*)::int AS so_tien_do, "
    "       max(l.tao_luc) AS tien_do_luc, "
    "       (array_agg(l.ghi_chu ORDER BY l.tao_luc DESC))[1] AS tien_do_cuoi "
    "  FROM cong_viec_lich_su l "
    "  WHERE l.cong_viec_id = cong_viec.id AND l.loai = 'tien_do') td ON true"
)


class TaoIn(BaseModel):
    tieu_de: str = Field(min_length=3, max_length=200)
    mo_ta: str = Field("", max_length=5000)
    nguoi_nhan: UUID | None = None
    # Phân công tự động: người trong ca, sẵn sàng, lâu nhất chưa được giao.
    giao_tu_dong: bool = False
    uu_tien: str = "thuong"
    han: datetime | None = None
    contact_id: UUID | None = None
    conversation_id: UUID | None = None
    order_id: UUID | None = None
    # Mã đơn người dùng gõ (ĐH-...) — máy chủ đổi sang order_id. Người trực
    # nhớ mã đơn, không nhớ UUID.
    ma_don: str | None = Field(None, max_length=60)
    loai_xu_ly_don: Literal["sua", "huy"] | None = None


class SuaIn(BaseModel):
    tieu_de: str | None = Field(None, min_length=3, max_length=200)
    mo_ta: str | None = Field(None, max_length=5000)
    trang_thai: str | None = None
    uu_tien: str | None = None
    han: datetime | None = None
    nguoi_nhan: UUID | None = None
    # Phân biệt "không gửi" với "gửi null". Không có cờ này thì không thu
    # hồi được người nhận, và cũng không xoá được hạn.
    xoa_nguoi_nhan: bool = False
    xoa_han: bool = False
    ket_qua: str | None = Field(None, max_length=2000)
    # Vì sao: lý do chuyển việc, lý do hủy... Đi vào lịch sử hoạt động.
    ghi_chu: str | None = Field(None, max_length=500)


class TienDoIn(BaseModel):
    noi_dung: str = Field(min_length=1, max_length=2000)


def _sach(d: dict) -> dict:
    for k in (
        "id", "nguoi_nhan", "nguoi_giao", "contact_id", "conversation_id",
        "order_id", "xu_ly_boi",
    ):
        if d.get(k) is not None:
            d[k] = str(d[k])
    for k in ("han", "tao_luc", "xong_luc", "xu_ly_luc", "sua_luc", "tien_do_luc"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    d["qua_han"] = cv.qua_han(d)
    d["chua_phan_cong"] = d.get("nguoi_nhan") is None and d.get("trang_thai") in cv.CHUA_XONG
    d["nhan_trang_thai"] = cv.NHAN_TRANG_THAI.get(d.get("trang_thai") or "", d.get("trang_thai"))
    d["nhan_nguon"] = cv.NHAN_NGUON.get(d.get("nguon") or "", d.get("nguon"))
    return d


def _danh_muc() -> dict[str, Any]:
    return {
        "trang_thai": [{"ma": m, "nhan": cv.NHAN_TRANG_THAI[m]} for m in cv.TRANG_THAI],
        "uu_tien": [{"ma": m, "nhan": cv.NHAN_UU_TIEN[m]} for m in cv.UU_TIEN],
        "nguon": [{"ma": m, "nhan": cv.NHAN_NGUON[m]} for m in cv.NGUON],
        "nhan_chua_phan_cong": cv.NHAN_CHUA_PHAN_CONG,
    }


# Cùng định nghĩa với `cv.qua_han`: việc đã xong/hủy không bao giờ quá hạn —
# con số phải giảm được khi người ta làm xong.
_QUA_HAN = "(cong_viec.han < now() AND cong_viec.trang_thai IN ('moi', 'dang_lam'))"
_CHUA_PHAN_CONG = ("(cong_viec.nguoi_nhan IS NULL "
                   "AND cong_viec.trang_thai IN ('moi', 'dang_lam'))")


def _co(nguoi: dict, quyen: str) -> bool:
    return quyen in (nguoi.get("quyen") or ())


def _uid(nguoi: dict) -> UUID | None:
    return UUID(str(nguoi["id"])) if nguoi.get("id") else None


@router.get("")
async def liet_ke(
    trang_thai: str | None = Query(None),
    cua_toi: bool = Query(False),
    chua_phan_cong: bool = Query(False),
    nguoi_nhan: UUID | None = Query(None),
    uu_tien: str | None = Query(None),
    nguon: str | None = Query(None),
    qua_han: bool = Query(False),
    q: str | None = Query(None, max_length=100),
    conversation_id: UUID | None = Query(None),
    contact_id: UUID | None = Query(None),
    order_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=300),
    nguoi: dict = Depends(can_quyen("cong_viec.doc")),
) -> dict[str, Any]:
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=0)
    # Hai nhóm điều kiện (UX-14-02): `co_so` là phạm vi + bộ lọc phụ (tìm,
    # ưu tiên, nguồn, của tôi...); `chip` là bộ lọc NHANH theo tình trạng.
    # Số đếm trên từng chip tính trên `co_so` — chip "Quá hạn (3)" phải nói
    # đúng số việc quá hạn trong những gì người ta đang tìm, bất kể chip nào
    # đang bật; tính trên cả `chip` thì mọi chip khác luôn hiện 0.
    co_so = [loc]
    chip: list[str] = []

    def them(menh_de: str, gia_tri: Any, vao: list[str] = co_so) -> None:
        ts.append(gia_tri)
        vao.append(menh_de.replace("$?", f"${len(ts)}"))

    try:
        if trang_thai:
            them("cong_viec.trang_thai = $?", cv.kiem_trang_thai(trang_thai), chip)
        if uu_tien:
            them("cong_viec.uu_tien = $?", cv.kiem_uu_tien(uu_tien))
    except cv.CongViecHong as exc:
        raise HTTPException(422, str(exc)) from exc
    if nguon:
        if nguon not in cv.NGUON:
            raise HTTPException(422, f"Nguồn không hợp lệ: {nguon!r}")
        them("cong_viec.nguon = $?", nguon)
    if cua_toi:
        them("cong_viec.nguoi_nhan = $?", str(nguoi["id"]))
    if nguoi_nhan:
        them("cong_viec.nguoi_nhan = $?", nguoi_nhan)
    if chua_phan_cong:
        chip.append(_CHUA_PHAN_CONG)
    if qua_han:
        chip.append(_QUA_HAN)
    if conversation_id:
        them("cong_viec.conversation_id = $?", conversation_id)
    if contact_id:
        them("cong_viec.contact_id = $?", contact_id)
    if order_id:
        them("cong_viec.order_id = $?", order_id)
    if q and q.strip():
        # Ký tự đại diện của LIKE trong chữ người gõ là chữ, không phải lệnh.
        tu = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        them("(cong_viec.tieu_de ILIKE '%' || $? || '%' "
             " OR cong_viec.mo_ta ILIKE '%' || $? || '%' "
             " OR coalesce(cong_viec.ket_qua, '') ILIKE '%' || $? || '%' "
             " OR coalesce(khach.display_name, '') ILIKE '%' || $? || '%' "
             " OR coalesce(don.ma_don, '') ILIKE '%' || $? || '%')", tu)
    tham_so_dem = list(ts)
    ts.append(limit)

    where_co_so = " AND ".join(co_so)
    where_chip = " AND ".join(chip) or "TRUE"
    ds = await db.fetch(
        f"SELECT {_CHON} {_JOIN} WHERE {where_co_so} AND {where_chip} "   # noqa: S608
        # Việc chưa xong lên trước; trong đó việc có hạn gần lên trước.
        # `NULLS LAST` để việc không hạn không chen lên đầu — nó không gấp
        # hơn một việc phải xong chiều nay.
        f"ORDER BY (cong_viec.trang_thai IN ('xong','huy')), "
        f"         cong_viec.han NULLS LAST, cong_viec.tao_luc DESC "
        f"LIMIT ${len(ts)}",
        *ts)
    # Đếm bằng SQL, không đếm `ds`: danh sách cắt ở `limit`, và "Hiển thị 100"
    # khi thật ra có 240 việc là một con số nói dối.
    dem = await db.fetchrow(
        "SELECT count(*)::int AS tat_ca, "
        "  count(*) FILTER (WHERE cong_viec.trang_thai = 'moi')::int AS cho_xu_ly, "
        "  count(*) FILTER (WHERE cong_viec.trang_thai = 'dang_lam')::int AS dang_lam, "
        f" count(*) FILTER (WHERE {_QUA_HAN})::int AS qua_han, "
        "  count(*) FILTER (WHERE cong_viec.trang_thai = 'xong')::int AS hoan_thanh, "
        "  count(*) FILTER (WHERE cong_viec.trang_thai = 'huy')::int AS da_huy, "
        f" count(*) FILTER (WHERE {_CHUA_PHAN_CONG})::int AS chua_phan_cong, "
        f" count(*) FILTER (WHERE {where_chip})::int AS ket_qua "
        f"{_JOIN} WHERE {where_co_so}",   # noqa: S608
        *tham_so_dem)
    dem_dict = dict(dem) if dem else {}
    return {"cong_viec": [_sach(d) for d in ds],
            "tong": dem_dict.pop("ket_qua", len(ds)),
            "dem": dem_dict, **_danh_muc()}


def _kiem_loi_check_cong_viec(exc: asyncpg.CheckViolationError) -> None:
    """Chuyển lỗi trigger 0045 (tạo/mở task trên hội thoại đã đóng) thành HTTP 409."""
    if getattr(exc, "constraint_name", None) == "cong_viec_open_requires_active_conversation" or "kết thúc" in str(exc).lower():
        raise HTTPException(
            409,
            "Hội thoại đã kết thúc; hãy mở lại hội thoại trước khi tạo hoặc mở lại công việc.",
        ) from exc
    raise exc


# Nhân viên LÀM ĐƯỢC việc (có `cong_viec.doc`), kèm tình trạng ca và tải. $1 là
# id việc (hoặc NULL) — để đánh dấu ai không thuộc kênh của việc ấy.
_SQL_NHAN_VIEN = cv.SQL_VIEC_VA_QUYEN + f"""
    SELECT n.id, coalesce(n.ho_ten, n.ten_dang_nhap) AS ten,
           dang_trong_ca(n.id, now()) AS trong_ca,
           EXISTS (SELECT 1 FROM ca_truc ct WHERE ct.nguoi_dung_id = n.id) AS co_lich,
           -- Lịch nghỉ (0034) — để ô chọn người nói "Đang nghỉ" thay vì "Ngoài
           -- ca" (MD-UX-14-05): hai chuyện khác nhau với người điều phối.
           EXISTS (SELECT 1 FROM ca_nghi cn WHERE cn.nguoi_dung_id = n.id
                   AND now() >= cn.tu_luc AND now() < cn.den_luc) AS dang_nghi,
           NOT EXISTS (SELECT 1 FROM team_members tm
                       WHERE tm.user_id = n.id AND NOT tm.is_available) AS san_sang,
           q.sua,
           coalesce((SELECT {cv.SQL_CUNG_KENH} FROM viec), true) AS cung_kenh,
           (SELECT count(*) FROM cong_viec v WHERE v.nguoi_nhan = n.id
              AND v.trang_thai IN ('moi', 'dang_lam'))::int AS so_mo,
           (SELECT count(*) FROM cong_viec v WHERE v.nguoi_nhan = n.id
              AND v.trang_thai IN ('moi', 'dang_lam') AND v.han < now())::int AS so_qua_han
    FROM quyen q JOIN nguoi_dung n ON n.id = q.id
    WHERE q.doc
    ORDER BY (dang_trong_ca(n.id, now()) AND EXISTS (
                SELECT 1 FROM ca_truc ct WHERE ct.nguoi_dung_id = n.id)) DESC, ten
"""


async def _nhan_vien(conn: Any, cong_viec_id: UUID | None) -> list[dict[str, Any]]:
    return [{**dict(r), "id": str(r["id"]),
             # "Trong ca" chỉ đáng tin khi người ấy CÓ lịch — người chưa xếp
             # ca thì `dang_trong_ca` trả true cho mọi giờ (0034).
             "trong_ca_that": bool(r["trong_ca"] and r["co_lich"])}
            for r in await conn.fetch(_SQL_NHAN_VIEN, cong_viec_id)]


async def _kiem_nguoi_nhan(conn: Any, nguoi_nhan: UUID) -> None:
    """Người nhận phải còn hoạt động và MỞ được việc — không thì việc treo."""
    r = await conn.fetchrow(
        cv.SQL_VIEC_VA_QUYEN
        + "SELECT n.khoa, coalesce((SELECT q.doc FROM quyen q WHERE q.id = n.id), false) AS doc "
          "FROM nguoi_dung n WHERE n.id = $2",
        None, nguoi_nhan)
    if r is None or r["khoa"]:
        raise HTTPException(422, "Người nhận không tồn tại hoặc đã bị khoá.")
    if not r["doc"]:
        raise HTTPException(422, (
            "Người nhận không có quyền xem công việc (cong_viec.doc) — "
            "giao sang là một việc họ không mở được."))


@router.get("/tong-quan")
async def tong_quan(nguoi: dict = Depends(can_quyen("cong_viec.doc"))) -> dict[str, Any]:
    """
    Tổng quan ca trực, phần CÔNG VIỆC: tồn đọng, chưa phân công, quá hạn, ai
    đang trong ca. Số đếm chịu ĐÚNG phạm vi của người xem — tổng quan không
    được là cửa sau để đếm việc của kênh mình không thuộc.
    """
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=0)
    async with db.pool().acquire() as conn:
        dem = await conn.fetchrow(
            "SELECT count(*) FILTER (WHERE nguoi_nhan IS NULL "
            "         AND trang_thai IN ('moi','dang_lam'))::int AS chua_phan_cong, "
            "       count(*) FILTER (WHERE trang_thai = 'moi')::int AS cho_xu_ly, "
            "       count(*) FILTER (WHERE trang_thai = 'dang_lam')::int AS dang_thuc_hien, "
            "       count(*) FILTER (WHERE han < now() "
            "         AND trang_thai IN ('moi','dang_lam'))::int AS qua_han, "
            "       count(*) FILTER (WHERE trang_thai = 'xong' "
            # "Hôm nay" theo giờ Việt Nam UTC+7 cộng tay — cùng lý do với
            # agent/core/gio_lam_viec.py, không phụ thuộc bảng múi giờ của máy.
            "         AND xong_luc > (date_trunc('day', (now() AT TIME ZONE 'UTC') "
            "             + interval '7 hours') - interval '7 hours') AT TIME ZONE 'UTC'"
            "       )::int AS xong_hom_nay "
            f"FROM cong_viec WHERE {loc}", *ts)  # noqa: S608
        chua_giao = await conn.fetch(
            f"SELECT {_CHON} {_JOIN} WHERE {loc} AND cong_viec.nguoi_nhan IS NULL "  # noqa: S608
            "AND cong_viec.trang_thai IN ('moi','dang_lam') "
            "ORDER BY CASE cong_viec.uu_tien WHEN 'gap' THEN 0 WHEN 'cao' THEN 1 "
            "         WHEN 'thuong' THEN 2 ELSE 3 END, cong_viec.han NULLS LAST, "
            "         cong_viec.tao_luc LIMIT 10", *ts)
        # Tải của từng người là thông tin về đồng nghiệp — chỉ người điều
        # phối (hoặc thấy mọi việc) mới cần và mới được thấy.
        nhan_vien = None
        if _co(nguoi, "cong_viec.giao") or _co(nguoi, "cong_viec.xem_tat_ca"):
            nhan_vien = await _nhan_vien(conn, None)
    return {
        "dem": dict(dem) if dem else {},
        "chua_phan_cong": [_sach(d) for d in map(dict, chua_giao)],
        "nhan_vien": nhan_vien,
        # Tự phân công có chạy được LÚC NÀY không — nói trước, để người điều
        # phối không bấm "Tự động" rồi mới biết là không ai trong ca.
        "tu_dong_duoc": (sum(1 for n in nhan_vien if n["trong_ca_that"] and n["san_sang"]
                             and n["sua"]) if nhan_vien is not None else None),
        **_danh_muc(),
    }


@router.get("/nguoi-nhan-duoc")
async def nguoi_nhan_duoc(
    cong_viec_id: UUID | None = Query(None),
    _q: dict = Depends(can_quyen("cong_viec.giao")),
) -> dict[str, Any]:
    """
    Danh sách để CHỌN người nhận khi giao/chuyển. Không đòi `nguoi_dung.doc`:
    người điều phối việc không nhất thiết quản lý nhân sự, và thiếu danh sách
    này thì quyền `cong_viec.giao` lại thành quyền không có cửa.
    """
    async with db.pool().acquire() as conn:
        return {"nguoi": await _nhan_vien(conn, cong_viec_id)}


# ------------------------------------------------------------ gợi ý khi tạo việc

def _xem_moi_don(nguoi: dict) -> bool:
    """Cùng luật với `GET /api/orders` (don_kho.list_orders) — xem chú thích ở đó."""
    return _co(nguoi, "khach.xem_tat_ca") or _co(nguoi, "hoi_thoai.xem_tat_ca")


def _don_thay_duoc(bi_danh: str, n_moi: int, n_uid: int) -> str:
    """
    Đơn `bi_danh` người hỏi thấy được: xem mọi kênh, hoặc là thành viên kênh
    của hội thoại sinh ra đơn. Đơn mồ côi chỉ người xem-mọi-kênh thấy.

    MỘT luật cho cả gợi ý mã đơn lẫn lúc tạo việc bằng mã đơn: chặn ở gợi ý
    mà không chặn lúc tạo thì gõ tay mã đơn kênh khác vẫn gắn được — rồi tên
    khách kênh ấy hiện trên màn Công việc.
    """
    return (f"(${n_moi}::bool OR EXISTS (SELECT 1 FROM conversations dk "
            f"JOIN account_memberships dm ON dm.account_id = dk.account_id "
            f"WHERE dk.id = {bi_danh}.conversation_id AND dm.user_id = ${n_uid}::uuid))")


async def _goi_y_don(nguoi: dict, *, q: str = "", contact_id: UUID | None = None,
                     limit: int = 8) -> list[dict[str, Any]]:
    ts: list[Any] = [_xem_moi_don(nguoi), str(nguoi["id"])]
    dk = [_don_thay_duoc("o", 1, 2)]
    if contact_id is not None:
        ts.append(contact_id)
        dk.append(f"EXISTS (SELECT 1 FROM conversations kk WHERE kk.id = o.conversation_id "
                  f"AND kk.contact_id = ${len(ts)})")
    tu = q.strip()
    if tu:
        thuong = tu.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        ts.append(thuong)
        menh_de = f"o.ma_don ILIKE '%' || ${len(ts)} || '%'"
        so = "".join(ch for ch in tu if ch.isdigit())
        # Tra bằng SĐT chỉ khi gõ đủ dài: ba chữ số trùng trong gần như mọi
        # số điện thoại, gợi ý ra cả danh bạ. SĐT chỉ dùng để KHỚP, không
        # trả về — ô gợi ý không cần nó để người ta chọn đúng đơn.
        if len(so) >= 6:
            ts.append(so)
            menh_de += f" OR regexp_replace(o.khach_sdt, '\\D', '', 'g') LIKE '%' || ${len(ts)} || '%'"
        dk.append(f"({menh_de})")
    ts.append(limit)
    rows = await db.fetch(
        "SELECT o.id, o.ma_don, o.trang_thai, o.tong_tien, o.created_at, o.khach_ten, "
        "       o.conversation_id "
        f"FROM orders o WHERE {' AND '.join(dk)} "   # noqa: S608
        f"ORDER BY o.created_at DESC LIMIT ${len(ts)}", *ts)
    return [{"id": str(r["id"]), "ma_don": r["ma_don"], "trang_thai": r["trang_thai"],
             "tong_tien": int(r["tong_tien"] or 0), "khach_ten": r["khach_ten"],
             "conversation_id": str(r["conversation_id"]) if r["conversation_id"] else None,
             "tao_luc": r["created_at"].isoformat()} for r in rows]


@router.get("/goi-y-don")
async def goi_y_don(
    q: str = Query("", max_length=60),
    contact_id: UUID | None = Query(None),
    conversation_id: UUID | None = Query(None),
    limit: int = Query(8, ge=1, le=20),
    nguoi: dict = Depends(can_quyen("don.doc")),
) -> dict[str, Any]:
    """
    Gợi ý mã đơn cho ô "Đơn liên quan" lúc tạo việc (UX-14-04).

    Quyền `don.doc` và phạm vi KÊNH như màn Đơn hàng: ô gợi ý không được là
    cửa sau để đọc đơn (tên khách, giá trị) của kênh mình không thuộc. Có
    khách (hoặc hội thoại) thì CHỈ đơn của khách ấy — gắn nhầm đơn của người
    khác vào việc là người nhận việc gọi nhầm khách.
    """
    if conversation_id is not None and contact_id is None:
        contact_id = await db.pool().fetchval(
            "SELECT contact_id FROM conversations WHERE id = $1", conversation_id)
        if contact_id is None:
            return {"don": []}
    return {"don": await _goi_y_don(nguoi, q=q, contact_id=contact_id, limit=limit)}


@router.get("/ngu-canh-tao")
async def ngu_canh_tao(
    conversation_id: UUID = Query(...),
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    """
    Ngữ cảnh để tạo việc TỪ một hội thoại (UX-14-04): khách, kênh, vài tin
    khách gần nhất làm mô tả gợi ý (không gọi mô hình — xem
    `cv.tom_tat_tin_khach`), việc đang mở của hội thoại này (để không tạo
    trùng) và đơn gần đây của khách nếu người hỏi có `don.doc`.

    Cùng phạm vi kênh với `tao`: 404 chứ không 403 — không xác nhận hội
    thoại ấy tồn tại.
    """
    moi_kenh = _co(nguoi, "hoi_thoai.xem_tat_ca") or _co(nguoi, "cong_viec.xem_tat_ca")
    hk = await db.fetchrow(
        "SELECT c.id, c.contact_id, c.customer_name, c.channel, c.nen_tang, c.state, "
        "       ct.display_name AS khach_ten, ca.display_name AS kenh_ten, ca.channel AS kenh "
        "FROM conversations c "
        "LEFT JOIN contacts ct ON ct.id = c.contact_id "
        "LEFT JOIN channel_accounts ca ON ca.id = c.account_id "
        "WHERE c.id = $1 AND ($2::bool OR EXISTS ("
        " SELECT 1 FROM account_memberships m WHERE m.account_id = c.account_id "
        " AND m.user_id = $3::uuid))",
        conversation_id, moi_kenh, str(nguoi["id"]))
    if hk is None:
        raise HTTPException(404, "Không tìm thấy hội thoại")
    tin = await db.fetch(
        "SELECT content, created_at FROM messages "
        "WHERE conversation_id = $1 AND role = 'customer' "
        "ORDER BY created_at DESC LIMIT $2", conversation_id, cv.SO_TIN_GOI_Y)
    tin_khach = [{"noi_dung": r["content"], "luc": r["created_at"]} for r in reversed(tin)]
    kenh = thong_bao_noi_bo.TEN_KENH.get(hk["kenh"] or "", hk["kenh_ten"] or hk["channel"])
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1)
    viec_mo = await db.fetch(
        f"SELECT cong_viec.id, cong_viec.tieu_de, cong_viec.trang_thai FROM cong_viec "  # noqa: S608
        f"WHERE cong_viec.conversation_id = $1 AND cong_viec.trang_thai IN ('moi','dang_lam') "
        f"AND {loc} ORDER BY cong_viec.tao_luc DESC LIMIT 5", conversation_id, *ts)
    return {
        "hoi_thoai": {"id": str(hk["id"]), "kenh": kenh,
                      "trang_thai": hk["state"] or "open"},
        "khach": ({"id": str(hk["contact_id"]),
                   "ten": hk["khach_ten"] or hk["customer_name"] or "Khách"}
                  if hk["contact_id"] else None),
        "tin_khach": [{"noi_dung": t["noi_dung"], "luc": t["luc"].isoformat()} for t in tin_khach],
        "mo_ta_goi_y": cv.tom_tat_tin_khach(tin_khach, kenh=kenh),
        "viec_mo": [{"id": str(r["id"]), "tieu_de": r["tieu_de"],
                     "nhan_trang_thai": cv.NHAN_TRANG_THAI.get(r["trang_thai"], r["trang_thai"])}
                    for r in viec_mo],
        # None = không có quyền xem đơn (khác [] = khách chưa có đơn nào):
        # màn hình nói đúng câu nào, không để người ta tưởng khách chưa mua.
        "don_gan_day": (await _goi_y_don(nguoi, contact_id=hk["contact_id"], limit=5)
                        if _co(nguoi, "don.doc") and hk["contact_id"] else None),
    }


@router.post("", status_code=201)
async def tao(
    body: TaoIn,
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    try:
        cv.kiem_uu_tien(body.uu_tien)
    except cv.CongViecHong as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.nguoi_nhan and body.giao_tu_dong:
        raise HTTPException(422, "Chọn người nhận HOẶC phân công tự động, không cả hai.")

    order_id = body.order_id
    if order_id is None and body.ma_don and body.ma_don.strip():
        order_id = await db.pool().fetchval(
            "SELECT id FROM orders WHERE ma_don = $1", body.ma_don.strip())
        if order_id is None:
            raise HTTPException(422, f"Không tìm thấy đơn {body.ma_don.strip()}.")
    # Việc xử lý đơn (sửa/hủy) BẮT BUỘC có đơn. Chiều ngược lại thì không:
    # "gọi khách xác nhận địa chỉ đơn ĐH-12" là việc thường gắn với một đơn.
    if body.loai_xu_ly_don is not None and order_id is None:
        raise HTTPException(422, "Công việc xử lý đơn phải gắn với một đơn hàng (order_id)")
    if order_id is not None:
        # Đơn phải nằm trong phạm vi kênh của người tạo — cùng luật với ô gợi
        # ý mã đơn (`_don_thay_duoc`). Cùng câu trả lời với đơn không tồn tại:
        # không xác nhận mã đơn kênh khác là có thật.
        order = await db.fetchrow(
            f"SELECT o.conversation_id FROM orders o WHERE o.id = $1 "  # noqa: S608
            f"AND {_don_thay_duoc('o', 2, 3)}",
            order_id, _xem_moi_don(nguoi), str(nguoi["id"]))
        if order is None:
            if body.ma_don and body.order_id is None:
                raise HTTPException(422, f"Không tìm thấy đơn {body.ma_don.strip()}.")
            raise HTTPException(422, "Đơn hàng liên kết không tồn tại")
        if (
            body.loai_xu_ly_don is not None
            and body.conversation_id is not None
            and order["conversation_id"] != body.conversation_id
        ):
            raise HTTPException(422, "Đơn hàng không thuộc Conversation đã chọn")

    contact_id = body.contact_id
    if body.conversation_id is not None:
        # Gắn việc vào hội thoại của KÊNH mình không thuộc là đọc được tên
        # khách kênh ấy qua màn Công việc (việc mình tạo thì mình luôn thấy).
        # 404 chứ không 403: không xác nhận hội thoại ấy tồn tại.
        moi_kenh = _co(nguoi, "hoi_thoai.xem_tat_ca") or _co(nguoi, "cong_viec.xem_tat_ca")
        hk = await db.fetchrow(
            "SELECT c.contact_id FROM conversations c WHERE c.id = $1 AND ($2::bool OR EXISTS ("
            " SELECT 1 FROM account_memberships m WHERE m.account_id = c.account_id "
            " AND m.user_id = $3::uuid))",
            body.conversation_id, moi_kenh, str(nguoi["id"]))
        if hk is None:
            raise HTTPException(404, "Không tìm thấy hội thoại")
        contact_id = contact_id or hk["contact_id"]

    # Giao cho NGƯỜI KHÁC cần quyền riêng. Không tách thì bất kỳ ai tạo
    # được việc cũng đẩy được việc sang đầu người khác, và màn Công việc
    # của họ đầy thứ họ không nhận. Tự phân công cũng là giao cho người khác.
    if ((body.nguoi_nhan and str(body.nguoi_nhan) != str(nguoi["id"])) or body.giao_tu_dong) \
            and not _co(nguoi, "cong_viec.giao"):
        raise HTTPException(403, (
            "Thiếu quyền: cong_viec.giao — bạn tạo việc cho mình được, "
            "nhưng giao cho người khác thì cần quyền này."))

    kq_tu_dong: giao_viec.KetQuaGiao | None = None
    async with db.pool().acquire() as conn:
        if body.nguoi_nhan and str(body.nguoi_nhan) != str(nguoi["id"]):
            await _kiem_nguoi_nhan(conn, body.nguoi_nhan)
        try:
            async with conn.transaction():
                await cv.dat_ngu_canh(conn, nguoi_id=_uid(nguoi))
                d = await conn.fetchrow(
                    "INSERT INTO cong_viec (tieu_de, mo_ta, nguoi_nhan, nguoi_giao, "
                    "uu_tien, han, contact_id, conversation_id, order_id, "
                    "loai_xu_ly_don, nguon) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'nguoi') RETURNING id",
                    body.tieu_de.strip(), body.mo_ta.strip(), body.nguoi_nhan,
                    _uid(nguoi), body.uu_tien, body.han, contact_id,
                    body.conversation_id, order_id, body.loai_xu_ly_don)
                if body.giao_tu_dong:
                    kq_tu_dong = await giao_viec.tu_dong_giao(conn, d["id"], nguoi_id=_uid(nguoi))
        except asyncpg.CheckViolationError as exc:
            _kiem_loi_check_cong_viec(exc)

    tieu_de = body.tieu_de.strip()
    await db.log_event("cong_viec.tao", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=d["id"], tieu_de=tieu_de)
    nguoi_nhan = body.nguoi_nhan
    if body.nguoi_nhan:
        # Việc giao cho người khác mà người ấy không được báo là việc vô
        # hình cho tới khi họ tình cờ mở màn Công việc. Tự giao: hàm bỏ qua.
        await thong_bao_noi_bo.bao_duoc_giao_viec(
            d["id"], body.nguoi_nhan, boi=nguoi.get("id"), tieu_de_viec=tieu_de)
    elif kq_tu_dong is not None:
        nguoi_nhan = kq_tu_dong.nguoi_nhan
        await giao_viec.bao_sau_khi_giao(d["id"], kq_tu_dong, tieu_de_viec=tieu_de,
                                         boi=nguoi.get("id"))
    else:
        await thong_bao_noi_bo.bao_viec_chua_giao(
            d["id"], tieu_de_viec=tieu_de, tru=nguoi.get("id"))
    return {
        "id": str(d["id"]),
        "nguoi_nhan": str(nguoi_nhan) if nguoi_nhan else None,
        "ly_do_khong_giao": kq_tu_dong.ly_do if kq_tu_dong and not kq_tu_dong.nguoi_nhan else None,
    }


@router.get("/{cong_viec_id}")
async def chi_tiet(
    cong_viec_id: UUID,
    nguoi: dict = Depends(can_quyen("cong_viec.doc")),
) -> dict[str, Any]:
    """Một việc kèm LỊCH SỬ HOẠT ĐỘNG — cùng phạm vi với danh sách."""
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1)
    d = await db.fetchrow(
        f"SELECT {_CHON} {_JOIN} WHERE cong_viec.id = $1 AND {loc}",  # noqa: S608
        cong_viec_id, *ts)
    if d is None:
        raise HTTPException(404, "Không tìm thấy công việc")
    ls = await db.fetch(
        "SELECT l.loai, l.tu_trang_thai, l.den_trang_thai, l.ghi_chu, l.tao_luc, "
        "       l.nguoi_id, l.tu_nguoi, l.den_nguoi, "
        "       a.ho_ten AS nguoi_ten, b.ho_ten AS tu_nguoi_ten, c.ho_ten AS den_nguoi_ten "
        "FROM cong_viec_lich_su l "
        "LEFT JOIN nguoi_dung a ON a.id = l.nguoi_id "
        "LEFT JOIN nguoi_dung b ON b.id = l.tu_nguoi "
        "LEFT JOIN nguoi_dung c ON c.id = l.den_nguoi "
        "WHERE l.cong_viec_id = $1 ORDER BY l.tao_luc, l.id", cong_viec_id)
    lich_su = []
    for r in ls:
        ghi_chu = r["ghi_chu"]
        if r["loai"] == "sua":
            ghi_chu = "Đổi " + ", ".join(cv.NHAN_TRUONG.get(t, t) for t in ghi_chu.split(",") if t)
        lich_su.append({
            "loai": r["loai"],
            "nhan_loai": cv.LOAI_LICH_SU.get(r["loai"], r["loai"]),
            "nhom": cv.NHOM_LICH_SU.get(r["loai"], "khac"),
            # NULL = hệ thống: AI, quy tắc tự động, vòng nền, đường cũ.
            "nguoi": r["nguoi_ten"] or ("Hệ thống" if r["nguoi_id"] is None else "—"),
            "tu_nguoi": r["tu_nguoi_ten"], "den_nguoi": r["den_nguoi_ten"],
            "tu_trang_thai": cv.NHAN_TRANG_THAI.get(r["tu_trang_thai"] or "", r["tu_trang_thai"]),
            "den_trang_thai": cv.NHAN_TRANG_THAI.get(r["den_trang_thai"] or "", r["den_trang_thai"]),
            "ghi_chu": ghi_chu,
            "tao_luc": r["tao_luc"].isoformat(),
        })
    bien_dong_kho = []
    if d.get("ma_don"):
        bd_rows = await db.fetch(
            "SELECT id, ma, thay_doi, ly_do, ma_don, ghi_chu, luc "
            "FROM kho_bien_dong WHERE ma_don = $1 ORDER BY luc DESC, id DESC",
            d["ma_don"],
        )
        bien_dong_kho = [
            {
                "id": int(b["id"]),
                "ma": b["ma"],
                "thay_doi": int(b["thay_doi"]),
                "ly_do": b["ly_do"],
                "ma_don": b["ma_don"],
                "ghi_chu": b["ghi_chu"] or "",
                "luc": b["luc"].isoformat(),
            }
            for b in bd_rows
        ]
    return {"cong_viec": _sach(dict(d)), "lich_su": lich_su,
            "bien_dong_kho": bien_dong_kho,
            "nhom_lich_su": [{"ma": m, "nhan": n} for m, n in cv.NHAN_NHOM_LICH_SU.items()],
            **_danh_muc()}


@router.put("/{cong_viec_id}")
async def sua(
    cong_viec_id: UUID,
    body: SuaIn,
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    """
    Sửa một việc: trạng thái, ưu tiên, hạn, người nhận (giao/chuyển/thu hồi),
    kết quả.

    `xong_luc` do MÁY CHỦ đặt, không nhận từ client: cột ấy bị ràng buộc
    `CHECK ((trang_thai = 'xong') = (xong_luc IS NOT NULL))`, và để client
    tự điền là mời một 500 khó hiểu mỗi lần nó quên.
    """
    if body.trang_thai:
        try:
            cv.kiem_trang_thai(body.trang_thai)
        except cv.CongViecHong as exc:
            raise HTTPException(422, str(exc)) from exc
    if body.uu_tien:
        try:
            cv.kiem_uu_tien(body.uu_tien)
        except cv.CongViecHong as exc:
            raise HTTPException(422, str(exc)) from exc

    doi_nguoi_nhan = body.nguoi_nhan is not None or body.xoa_nguoi_nhan
    if doi_nguoi_nhan and not _co(nguoi, "cong_viec.giao"):
        # Nhận việc CHƯA AI NHẬN về cho mình thì không cần quyền giao — đó
        # là tự nhận việc, không phải đẩy việc sang người khác.
        tu_nhan = (body.nguoi_nhan is not None
                   and str(body.nguoi_nhan) == str(nguoi["id"]))
        if not tu_nhan:
            raise HTTPException(403, "Thiếu quyền: cong_viec.giao")

    # Sửa chịu cùng phạm vi KÊNH với xem. Trước 16.11.2026 PUT không lọc gì
    # — ai có `cong_viec.sua` cũng tự nhận được việc của kênh mình không
    # thuộc, chỉ cần đoán id. 404 chứ không 403. Việc đã giao cho người khác
    # cùng kênh thì không chặn ở đây: luật giành việc ngay dưới trả 403 có
    # lý do — xem `dieu_kien_pham_vi(chi_loc_kenh=True)`.
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1, chi_loc_kenh=True)
    async with db.pool().acquire() as conn:
        if body.nguoi_nhan is not None and str(body.nguoi_nhan) != str(nguoi["id"]):
            await _kiem_nguoi_nhan(conn, body.nguoi_nhan)
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT trang_thai, nguoi_nhan, nguoi_giao, order_id, loai_xu_ly_don, "
                "       ket_qua_xu_ly_don, tieu_de FROM cong_viec "
                f"WHERE id = $1 AND {loc} FOR UPDATE",  # noqa: S608
                cong_viec_id, *ts)
            if cu is None:
                raise HTTPException(404, "Không tìm thấy công việc")

            if (
                body.trang_thai == "xong"
                and cu["order_id"] is not None
                and cu["loai_xu_ly_don"] in cv.LOAI_XU_LY_DON
                and cu["ket_qua_xu_ly_don"] not in ("thanh_cong", "khong_the")
            ):
                raise HTTPException(409, (
                    "Công việc sửa/hủy đơn phải xác nhận kết quả và đối soát "
                    "ERPNext; không thể đánh dấu Xong trực tiếp."
                ))

            if (body.nguoi_nhan is not None
                    and str(body.nguoi_nhan) == str(nguoi["id"])
                    and cu["nguoi_nhan"] is not None
                    and str(cu["nguoi_nhan"]) != str(nguoi["id"])
                    and not _co(nguoi, "cong_viec.giao")):
                raise HTTPException(403, (
                    "Việc này đã có người nhận. Giành việc của người khác "
                    "cần quyền cong_viec.giao."))

            moi_tt = body.trang_thai or cu["trang_thai"]
            await cv.dat_ngu_canh(conn, nguoi_id=_uid(nguoi),
                                  ghi_chu=(body.ghi_chu or "").strip())
            try:
                await conn.execute(
                    "UPDATE cong_viec SET "
                    "  tieu_de = COALESCE($2, tieu_de), "
                    "  mo_ta = COALESCE($3, mo_ta), "
                    "  trang_thai = $4, "
                    "  uu_tien = COALESCE($5, uu_tien), "
                    "  han = CASE WHEN $6 THEN NULL ELSE COALESCE($7, han) END, "
                    "  nguoi_nhan = CASE WHEN $8 THEN NULL "
                    "                    ELSE COALESCE($9, nguoi_nhan) END, "
                    "  ket_qua = COALESCE($10, ket_qua), "
                    # Hạn đổi = lần quá hạn mới phải được báo lại (0061).
                    "  bao_qua_han_luc = CASE WHEN $6 OR $7::timestamptz IS NOT NULL "
                    "                         THEN NULL ELSE bao_qua_han_luc END, "
                    "  xong_luc = CASE WHEN $4 = 'xong' "
                    "                  THEN COALESCE(xong_luc, now()) ELSE NULL END, "
                    "  sua_luc = now() "
                    "WHERE id = $1",
                    cong_viec_id,
                    body.tieu_de.strip() if body.tieu_de else None,
                    body.mo_ta.strip() if body.mo_ta is not None else None,
                    moi_tt,
                    body.uu_tien,
                    body.xoa_han, body.han,
                    body.xoa_nguoi_nhan, body.nguoi_nhan,
                    body.ket_qua.strip() if body.ket_qua and body.ket_qua.strip() else None)
            except asyncpg.CheckViolationError as exc:
                _kiem_loi_check_cong_viec(exc)

    await db.log_event("cong_viec.sua", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=cong_viec_id, trang_thai=moi_tt)
    tieu_de = (body.tieu_de or cu["tieu_de"] or "").strip()
    # Chỉ khi người nhận ĐỔI sang một người mới: sửa tiêu đề hay đổi trạng
    # thái một việc đã giao không phải là "được giao" lần nữa.
    if (body.nguoi_nhan is not None and not body.xoa_nguoi_nhan
            and str(body.nguoi_nhan) != str(cu["nguoi_nhan"] or "")):
        await thong_bao_noi_bo.dong_bo_doi_nguoi_viec(
            cong_viec_id, body.nguoi_nhan, tieu_de_viec=tieu_de)
        await thong_bao_noi_bo.bao_duoc_giao_viec(
            cong_viec_id, body.nguoi_nhan, boi=nguoi.get("id"),
            tieu_de_viec=tieu_de, chuyen=cu["nguoi_nhan"] is not None)
    elif body.xoa_nguoi_nhan and cu["nguoi_nhan"] is not None and moi_tt in cv.CHUA_XONG:
        await thong_bao_noi_bo.dong_bo_doi_nguoi_viec(
            cong_viec_id, None, tieu_de_viec=tieu_de)
        # Thu hồi người nhận = việc quay về "Chưa phân công": phải có người biết.
        await thong_bao_noi_bo.bao_viec_chua_giao(
            cong_viec_id, tieu_de_viec=tieu_de, ly_do="đã thu hồi người nhận",
            tru=nguoi.get("id"))
    if moi_tt == "huy" and cu["trang_thai"] != "huy":
        nhan_moi = (None if body.xoa_nguoi_nhan
                    else body.nguoi_nhan or cu["nguoi_nhan"])
        await thong_bao_noi_bo.bao_viec_huy(
            cong_viec_id, nguoi_nhan=[nhan_moi, cu["nguoi_giao"]],
            boi=nguoi.get("id"), tieu_de_viec=tieu_de)
    return {"id": str(cong_viec_id), "trang_thai": moi_tt}


@router.post("/{cong_viec_id}/tien-do", status_code=201)
async def tien_do(
    cong_viec_id: UUID,
    body: TienDoIn,
    nguoi: dict = Depends(can_quyen("cong_viec.sua")),
) -> dict[str, Any]:
    """
    Ghi một dòng tiến độ ("đã gọi, khách hẹn chiều mai") vào lịch sử việc.
    Cùng phạm vi với sửa: ai sửa được việc thì ghi được tiến độ của nó.
    """
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1, chi_loc_kenh=True)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            co = await conn.fetchval(
                f"UPDATE cong_viec SET sua_luc = now() WHERE id = $1 AND {loc} "  # noqa: S608
                "RETURNING id", cong_viec_id, *ts)
            if co is None:
                raise HTTPException(404, "Không tìm thấy công việc")
            await conn.execute(
                "INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu) "
                "VALUES ($1, 'tien_do', $2, $3)",
                cong_viec_id, _uid(nguoi), body.noi_dung.strip())
    return {"id": str(cong_viec_id)}


@router.post("/{cong_viec_id}/tu-dong-giao")
async def tu_dong_giao(
    cong_viec_id: UUID,
    nguoi: dict = Depends(can_quyen("cong_viec.giao")),
) -> dict[str, Any]:
    """
    Phân công tự động một việc đang Chưa phân công. Không ai đủ điều kiện thì
    trả `nguoi_nhan: null` kèm lý do — việc ở nguyên chỗ cũ, không đoán.
    """
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1, chi_loc_kenh=True)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            tieu_de = await conn.fetchval(
                f"SELECT tieu_de FROM cong_viec WHERE id = $1 AND {loc}",  # noqa: S608
                cong_viec_id, *ts)
            if tieu_de is None:
                raise HTTPException(404, "Không tìm thấy công việc")
            kq = await giao_viec.tu_dong_giao(conn, cong_viec_id, nguoi_id=_uid(nguoi))
        ten = (await conn.fetchval(
            "SELECT coalesce(ho_ten, ten_dang_nhap) FROM nguoi_dung WHERE id = $1",
            kq.nguoi_nhan) if kq.nguoi_nhan else None)
    if kq.nguoi_nhan:
        await thong_bao_noi_bo.dong_bo_doi_nguoi_viec(
            cong_viec_id, kq.nguoi_nhan, tieu_de_viec=tieu_de)
        await thong_bao_noi_bo.bao_duoc_giao_viec(
            cong_viec_id, kq.nguoi_nhan, boi=nguoi.get("id"), tieu_de_viec=tieu_de,
            tu_dong=True)
        await db.log_event("cong_viec.tu_dong_giao", actor=nguoi.get("ten_dang_nhap", "?"),
                           ref_id=cong_viec_id, nguoi_nhan=str(kq.nguoi_nhan))
    return {"nguoi_nhan": str(kq.nguoi_nhan) if kq.nguoi_nhan else None,
            "nguoi_nhan_ten": ten, "ly_do": kq.ly_do}


@router.delete("/{cong_viec_id}", status_code=204)
async def xoa(
    cong_viec_id: UUID,
    nguoi: dict = Depends(can_quyen("cong_viec.giao")),
) -> None:
    """
    Xoá hẳn một việc.

    Cần `cong_viec.giao` chứ không `cong_viec.sua`: đánh dấu `huy` là thao
    tác hằng ngày và để lại dấu vết; xoá hẳn thì không, nên nó phải ở cùng
    bậc quyền với việc điều phối. Lịch sử hoạt động đi theo việc (CASCADE);
    dấu vết còn lại là sự kiện `cong_viec.xoa` trong nhật ký.
    """
    loc, ts = cv.dieu_kien_pham_vi(nguoi=nguoi, so_tham_so=1, chi_loc_kenh=True)
    r = await db.execute(
        f"DELETE FROM cong_viec WHERE id = $1 AND {loc}",  # noqa: S608
        cong_viec_id, *ts)
    if r.endswith(" 0"):
        raise HTTPException(404, "Không tìm thấy công việc")
    await db.log_event("cong_viec.xoa", actor=nguoi.get("ten_dang_nhap", "?"),
                       ref_id=cong_viec_id)
