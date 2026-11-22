"""
Dọn media theo thời hạn, dọn mồ côi, và số liệu cho bảng quản trị.

LUẬT DỌN
--------
  media khách gửi (`data/media`)
    xoá khi KHÔNG còn đính kèm nào gửi trong `MEDIA_LUU_NGAY` ngày gần đây —
    gồm cả trường hợp không còn đính kèm nào (hội thoại đã bị xoá theo thời
    hạn hay theo yêu cầu PDPD: tin nhắn và đính kèm đi theo CASCADE).
    Chống trùng nên "quá hạn" tính theo lần gửi GẦN NHẤT: khách gửi lại đúng
    tấm ảnh cũ hôm nay thì tấm ảnh ấy sống thêm trọn thời hạn.
  tệp nhân viên gửi (`data/uploads`)
    sống cùng hội thoại: xoá khi không còn đính kèm nào trỏ vào nó (và tệp
    đã đủ cũ để không phải một lần gửi đang dở).
  tệp trong `data/media` không dòng CSDL nào nhận -> mồ côi, xoá.
  dòng CSDL mà tệp không còn trên đĩa -> ĐÁNH DẤU `mat_tep`, KHÔNG xoá dòng:
    dựng CSDL trên máy mới trước khi chép `data/media` sang là trường hợp
    thật (`scripts.chuyen_nha`); xoá dòng lúc ấy thì chép tệp sang xong là
    toàn bộ kho thành "mồ côi" và bị lượt sau xoá nốt.

KHÔNG BAO GIỜ ĐỤNG
------------------
`data/products` (ảnh sản phẩm) và `data/knowledge` (tài liệu công ty): mọi
lệnh xoá đi qua `_xoa_an_toan`, chỉ nhận tệp nằm trong `data/media` hoặc
`data/uploads`. Một `storage_key` hỏng hay bị sửa tay không được biến lượt
dọn thành lệnh xoá ảnh sản phẩm.

XEM TRƯỚC RỒI MỚI XOÁ
---------------------
`xem_truoc=True` đếm đúng những gì sẽ xoá mà không xoá — bảng quản trị bắt
bấm xem trước, rồi mới hiện nút xác nhận.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from agent import db, duong_dan_du_lieu
from agent.omnichannel import media

# Tệp mồ côi phải cũ hơn ngần này mới bị xoá: tệp vừa chuyển vào kho mà
# giao dịch CSDL chưa xong, hay tệp nhân viên vừa tải lên mà tin chưa vào
# outbox, đều trông y hệt mồ côi trong vài mili-giây ấy.
MO_COI_SAU_GIAY = 3600
UPLOAD_MO_COI_SAU_GIAY = 2 * 24 * 3600
TAM_SAU_GIAY = 24 * 3600


def thu_muc_uploads() -> Path:
    return duong_dan_du_lieu.GOC_DU_LIEU / "uploads"


class XoaNgoaiVung(RuntimeError):
    """Một lệnh xoá trỏ ra ngoài `data/media` / `data/uploads`."""


def _xoa_an_toan(p: Path) -> int:
    """Xoá một tệp NẾU nó nằm trong vùng được dọn. Trả số byte giải phóng."""
    goc = duong_dan_du_lieu.GOC_DU_LIEU.resolve()
    that = p.resolve()
    cam = (goc / "products", goc / "knowledge")
    if any(c == that or c in that.parents for c in cam):
        raise XoaNgoaiVung(f"từ chối xoá trong vùng cấm: {that.name}")
    vung = (media.thu_muc_media().resolve(), thu_muc_uploads().resolve())
    if not any(v in that.parents for v in vung):
        raise XoaNgoaiVung(f"từ chối xoá ngoài data/media, data/uploads: {that.name}")
    if not that.is_file():
        return 0
    n = that.stat().st_size
    that.unlink()
    return n


async def _xoa_mot(sha: str, ngay: int | None) -> tuple[bool, int]:
    """
    Xoá MỘT nội dung nếu không còn ai giữ nó. Trả (đã xoá dòng?, số byte).

    `ngay=None`: chỉ xoá khi KHÔNG còn đính kèm nào (đường PDPD). Có `ngay`:
    xoá khi không còn đính kèm nào trong `ngay` ngày gần đây (thời hạn).
    Kiểm lại DƯỚI KHOÁ — khách có thể vừa gửi lại đúng nội dung này.
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1, hashtext($2))",
                               media.KHOA_MEDIA, sha)
            con = await conn.fetchval(
                "SELECT EXISTS (SELECT 1 FROM attachments WHERE media_sha256 = $1 "
                "AND ($2::int IS NULL OR created_at >= now() - make_interval(days => $2)))",
                sha, ngay)
            if con:
                return False, 0
            await conn.execute(
                "UPDATE attachments SET media_trang_thai = 'da_don' WHERE media_sha256 = $1",
                sha)
            r = await conn.fetchrow(
                "DELETE FROM media_tep WHERE sha256 = $1 RETURNING storage_key, size_bytes", sha)
            if r is None:
                return False, 0
            p = duong_dan_du_lieu.mo_khoa(r["storage_key"])
            # Xoá tệp TRONG giao dịch: hỏng xoá thì dòng CSDL quay lại, không
            # để lại một dòng "đã dọn" cho tệp vẫn còn nằm trên đĩa. Tệp đã
            # mất từ trước thì 0 byte — vẫn là một dòng đã dọn.
            return True, (_xoa_an_toan(p) if p is not None else 0)


async def _qua_han(ngay: int) -> list[dict]:
    return await db.fetch(
        "SELECT mt.sha256, mt.storage_key, mt.size_bytes FROM media_tep mt "
        "WHERE NOT EXISTS (SELECT 1 FROM attachments a WHERE a.media_sha256 = mt.sha256 "
        "                  AND a.created_at >= now() - make_interval(days => $1)) "
        "ORDER BY mt.tao_luc", ngay)


def _quet_tep(goc: Path, bo_qua: Iterable[str] = ()) -> list[tuple[Path, int, float]]:
    ra: list[tuple[Path, int, float]] = []
    if not goc.is_dir():
        return ra
    bo = set(bo_qua)
    for thu_muc, con, tep in os.walk(goc):
        con[:] = [c for c in con if c not in bo]
        for t in tep:
            p = Path(thu_muc) / t
            try:
                st = p.stat()
            except OSError:
                continue
            ra.append((p, st.st_size, st.st_mtime))
    return ra


def _tim_mo_coi(dang_ky: dict[str, str]) -> tuple[list[tuple[Path, int]], list[tuple[Path, int]]]:
    """(mồ côi trong kho, tệp tạm cũ) — chạy trong luồng riêng, đụng đĩa."""
    bay_gio = time.time()
    goc = media.thu_muc_media()
    hop_le = {os.path.normcase(str(duong_dan_du_lieu.mo_khoa(k))) for k in dang_ky.values()}
    mo_coi = [(p, n) for p, n, mt in _quet_tep(goc, bo_qua=(".tam",))
              if os.path.normcase(str(p)) not in hop_le and bay_gio - mt > MO_COI_SAU_GIAY]
    tam = [(p, n) for p, n, mt in _quet_tep(goc / ".tam") if bay_gio - mt > TAM_SAU_GIAY]
    return mo_coi, tam


def _upload_mo_coi(dang_dung: set[str]) -> list[tuple[Path, int]]:
    bay_gio = time.time()
    return [(p, n) for p, n, mt in _quet_tep(thu_muc_uploads())
            if str(p.resolve()) not in dang_dung and bay_gio - mt > UPLOAD_MO_COI_SAU_GIAY]


async def _uploads_dang_dung() -> set[str]:
    """Mọi tệp `data/uploads` còn được một đính kèm trỏ vào (khoá cũ tuyệt đối cũng tính)."""
    rows = await db.fetch(
        "SELECT DISTINCT storage_key FROM attachments "
        "WHERE storage_key IS NOT NULL AND storage_key LIKE '%uploads%'")
    ra: set[str] = set()
    for r in rows:
        p = duong_dan_du_lieu.mo_khoa(r["storage_key"])
        if p is not None:
            ra.add(str(p.resolve()))
    return ra


async def _soat_mat_tep(xem_truoc: bool) -> tuple[int, int]:
    """(số dòng mới mất tệp, số dòng tìm lại được tệp)."""
    rows = await db.fetch("SELECT sha256, storage_key, mat_tep_luc FROM media_tep")

    def _soi() -> list[bool]:
        ra = []
        for r in rows:
            p = duong_dan_du_lieu.mo_khoa(r["storage_key"])
            ra.append(bool(p and p.is_file()))
        return ra

    # MỘT luồng cho cả lượt soi đĩa, không một luồng mỗi dòng.
    co_tep = await asyncio.to_thread(_soi)
    mat = [r["sha256"] for r, co in zip(rows, co_tep, strict=True)
           if not co and r["mat_tep_luc"] is None]
    lai = [r["sha256"] for r, co in zip(rows, co_tep, strict=True)
           if co and r["mat_tep_luc"] is not None]
    if not xem_truoc:
        if mat:
            await db.execute(
                "UPDATE media_tep SET mat_tep_luc = now() WHERE sha256 = ANY($1::text[])", mat)
            await db.execute(
                "UPDATE attachments SET media_trang_thai = 'mat_tep' "
                "WHERE media_sha256 = ANY($1::text[]) AND media_trang_thai = 'da_tai'", mat)
        if lai:
            await db.execute(
                "UPDATE media_tep SET mat_tep_luc = NULL WHERE sha256 = ANY($1::text[])", lai)
            await db.execute(
                "UPDATE attachments SET media_trang_thai = 'da_tai' "
                "WHERE media_sha256 = ANY($1::text[]) AND media_trang_thai = 'mat_tep'", lai)
    return len(mat), len(lai)


async def don(*, nguon: str = "tu_dong", xem_truoc: bool = False,
              boi: str | None = None, ngay: int | None = None) -> dict[str, Any]:
    """Một lượt dọn đầy đủ. Ghi `media_lan_don` + nhật ký — kể cả khi xem trước."""
    ngay = int(ngay or media.luu_ngay())
    lan = await db.fetchrow_chac(
        "INSERT INTO media_lan_don (nguon, xem_truoc, thoi_han_ngay, boi) "
        "VALUES ($1, $2, $3, $4) RETURNING id", nguon, xem_truoc, ngay, boi)
    loi: list[str] = []

    # 1. Quá hạn / không còn ai dùng.
    qua_han = await _qua_han(ngay)
    so_tep = 0
    byte = 0
    if xem_truoc:
        so_tep = len(qua_han)
        byte = sum(int(r["size_bytes"] or 0) for r in qua_han)
    else:
        for r in qua_han:
            try:
                da_xoa, n = await _xoa_mot(r["sha256"], ngay)
            except (OSError, XoaNgoaiVung) as exc:
                loi.append(f"{r['sha256'][:12]}: {type(exc).__name__}: {exc}"[:200])
                continue
            so_tep += int(da_xoa)
            byte += n

    # 2. Dòng mất tệp / tìm lại tệp.
    mat, lai = await _soat_mat_tep(xem_truoc)

    # 3. Mồ côi trong kho + tệp tạm bỏ dở + tệp nhân viên không còn hội thoại.
    dang_ky = {r["sha256"]: r["storage_key"]
               for r in await db.fetch("SELECT sha256, storage_key FROM media_tep")}
    mo_coi, tam = await asyncio.to_thread(_tim_mo_coi, dang_ky)
    uploads = await asyncio.to_thread(_upload_mo_coi, await _uploads_dang_dung())
    so_mo_coi = 0
    byte_mo_coi = 0
    for p, n in [*mo_coi, *tam, *uploads]:
        if xem_truoc:
            so_mo_coi += 1
            byte_mo_coi += n
            continue
        try:
            byte_mo_coi += await asyncio.to_thread(_xoa_an_toan, p)
            so_mo_coi += 1
        except (OSError, XoaNgoaiVung) as exc:
            loi.append(f"{p.name}: {type(exc).__name__}: {exc}"[:200])

    chi_tiet = {"mo_coi_kho": len(mo_coi), "tep_tam": len(tam), "uploads": len(uploads),
                "byte_mo_coi": byte_mo_coi, "tim_lai_tep": lai, "loi": loi[:20]}
    await db.execute(
        "UPDATE media_lan_don SET xong_luc = now(), so_tep_xoa = $2, byte_giai_phong = $3, "
        "so_mo_coi_xoa = $4, so_dong_mat_tep = $5, chi_tiet = $6 WHERE id = $1",
        lan["id"], so_tep, byte + byte_mo_coi, so_mo_coi, mat, chi_tiet)
    ket = {"id": str(lan["id"]), "nguon": nguon, "xem_truoc": xem_truoc, "thoi_han_ngay": ngay,
           "so_tep_xoa": so_tep, "byte_qua_han": byte, "so_mo_coi": so_mo_coi,
           "byte_mo_coi": byte_mo_coi, "byte_giai_phong": byte + byte_mo_coi,
           "so_dong_mat_tep": mat, "tim_lai_tep": lai, "loi": loi[:20]}
    # Đếm RIÊNG từng loại, cả khi xem trước: lượt dọn xoá 0 tệp vì hỏng phải
    # trông khác hẳn lượt dọn xoá 0 tệp vì không có gì quá hạn.
    await db.log_event("media.xem_truoc_don" if xem_truoc else "media.don",
                       actor=boi or "system", **{k: v for k, v in ket.items() if k != "id"})
    return ket


# ---------------------------------------------------------------- PDPD

async def tham_chieu_cua(conv_ids: list, csdl: Any = db) -> dict[str, list[str]]:
    """
    Nội dung media + tệp nhân viên mà các hội thoại này đang giữ.

    Gọi TRƯỚC khi xoá hội thoại: sau đó đính kèm đã đi theo CASCADE và
    không còn đường nào biết tệp nào từng thuộc về khách này.
    `csdl` để `du_lieu_ca_nhan` truyền đúng mô-đun CSDL nó đang dùng.
    """
    if not conv_ids:
        return {"sha256": [], "uploads": []}
    rows = await csdl.fetch(
        "SELECT DISTINCT a.media_sha256, a.storage_key FROM attachments a "
        "JOIN messages m ON m.id = a.message_id "
        "WHERE m.conversation_id = ANY($1::uuid[]) "
        "  AND (a.media_sha256 IS NOT NULL OR a.storage_key IS NOT NULL)", conv_ids)
    sha = sorted({str(r.get("media_sha256")) for r in rows if r.get("media_sha256")})
    up = sorted({str(r.get("storage_key")) for r in rows
                 if r.get("storage_key") and "uploads" in str(r.get("storage_key"))})
    return {"sha256": sha, "uploads": up}


async def xoa_sau_pdpd(tham_chieu: dict[str, list[str]]) -> dict[str, int]:
    """
    Xoá ngay media của khách vừa bị xoá — trừ nội dung người khác còn giữ.

    Không chờ lượt dọn hằng ngày: khách đòi xoá thì ảnh da của họ phải đi
    cùng lúc với tin nhắn, không phải "trong vòng 24 giờ tới".
    """
    so = 0
    byte = 0
    loi = 0
    for sha in tham_chieu.get("sha256") or []:
        try:
            da_xoa, n = await _xoa_mot(sha, None)
        except (OSError, XoaNgoaiVung):
            loi += 1
            continue
        so += int(da_xoa)
        byte += n
    up = tham_chieu.get("uploads") or []
    if up:
        dang_dung = await _uploads_dang_dung()
        for k in up:
            p = duong_dan_du_lieu.mo_khoa(k)
            if p is None or str(p.resolve()) in dang_dung:
                continue
            try:
                n = await asyncio.to_thread(_xoa_an_toan, p)
            except (OSError, XoaNgoaiVung):
                loi += 1
                continue
            if n:
                so += 1
                byte += n
    return {"so_tep": so, "so_byte": byte, "so_loi": loi}


# ------------------------------------------------------------- số liệu

def _kich_thuoc_thu_muc(goc: Path) -> tuple[int, int]:
    tep = _quet_tep(goc)
    return len(tep), sum(n for _, n, _ in tep)


async def tong_quan() -> dict[str, Any]:
    """Mọi con số bảng quản trị cần — một lời gọi."""
    tong = await db.fetchrow_chac(
        "SELECT count(*) AS so_tep, coalesce(sum(size_bytes), 0) AS so_byte, "
        "count(*) FILTER (WHERE mat_tep_luc IS NOT NULL) AS mat_tep FROM media_tep")
    theo_loai = await db.fetch(
        "SELECT split_part(mime_type, '/', 1) AS loai, count(*) AS so_tep, "
        "coalesce(sum(size_bytes), 0) AS so_byte FROM media_tep GROUP BY 1 ORDER BY 3 DESC")
    trang_thai = await db.fetch(
        "SELECT media_trang_thai AS trang_thai, count(*) AS so FROM attachments "
        "WHERE media_trang_thai IS NOT NULL GROUP BY 1")
    trung = await db.fetchrow_chac(
        "SELECT count(*) AS so_dinh_kem, coalesce(sum(mt.size_bytes), 0) AS byte_dinh_kem "
        "FROM attachments a JOIN media_tep mt ON mt.sha256 = a.media_sha256")
    hong = await db.fetch(
        "SELECT a.id, a.kind, a.media_trang_thai, a.media_loi, a.media_so_lan_thu, a.created_at, "
        "       coalesce(a.original_url, a.url) AS nguon "
        "FROM attachments a WHERE a.media_trang_thai IN ('loi', 'het_han', 'qua_lon', 'mat_tep') "
        "ORDER BY a.created_at DESC LIMIT 10")
    lan = await db.fetchrow(
        "SELECT bat_dau, xong_luc, nguon, xem_truoc, thoi_han_ngay, so_tep_xoa, byte_giai_phong, "
        "so_mo_coi_xoa, so_dong_mat_tep, chi_tiet, boi FROM media_lan_don "
        "WHERE NOT xem_truoc ORDER BY bat_dau DESC LIMIT 1")
    nhip = await db.fetchrow(
        "SELECT last_seen_at FROM worker_heartbeats WHERE worker_name = $1", media.WORKER)
    so_up, byte_up = await asyncio.to_thread(_kich_thuoc_thu_muc, thu_muc_uploads())
    from agent import cau_hinh_dong

    so_byte = int(tong["so_byte"])
    byte_dinh_kem = int(trung["byte_dinh_kem"])
    return {
        "so_tep": int(tong["so_tep"]), "so_byte": so_byte, "so_mat_tep": int(tong["mat_tep"]),
        "theo_loai": [{"loai": r["loai"] or "khac", "so_tep": int(r["so_tep"]),
                       "so_byte": int(r["so_byte"])} for r in theo_loai],
        "trang_thai": {r["trang_thai"]: int(r["so"]) for r in trang_thai},
        # Chống trùng tiết kiệm được: đính kèm đang trỏ vào kho trừ đi số tệp
        # thật — mỗi lần khách gửi lại cùng một tấm ảnh là một bản không chép.
        "trung_lap": {"so_dinh_kem": int(trung["so_dinh_kem"]),
                      "so_ban_khong_chep": max(0, int(trung["so_dinh_kem"]) - int(tong["so_tep"])),
                      "byte_tiet_kiem": max(0, byte_dinh_kem - so_byte)},
        "uploads": {"so_tep": so_up, "so_byte": byte_up},
        "hong_gan_day": [{"id": str(r["id"]), "loai": r["kind"], "trang_thai": r["media_trang_thai"],
                          "ly_do": r["media_loi"] or "", "so_lan_thu": r["media_so_lan_thu"],
                          "luc": r["created_at"].isoformat(), "nguon": media.an_url(r["nguon"])}
                         for r in hong],
        "lan_don_cuoi": ({**{k: v for k, v in lan.items() if k not in ("bat_dau", "xong_luc")},
                          "bat_dau": lan["bat_dau"].isoformat(),
                          "xong_luc": lan["xong_luc"].isoformat() if lan["xong_luc"] else None}
                         if lan else None),
        "worker_luc": nhip["last_seen_at"].isoformat() if nhip else None,
        "thoi_han_ngay": media.luu_ngay(), "nguon_thoi_han": cau_hinh_dong.nguon("MEDIA_LUU_NGAY"),
        "toi_da_mb": media.toi_da_byte() // (1024 * 1024),
    }
