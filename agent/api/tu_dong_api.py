"""
API quy tắc tự động hoá (agent/omnichannel/tu_dong.py).

Quyền dùng lại `dinh_tuyen.doc` / `dinh_tuyen.sua` ("luật định tuyến và
SLA"): quy tắc tự động là cùng loại việc — quyết định tin nào đi đâu, ai
nhận — và người được sửa định tuyến là người được sửa quy tắc. Thêm cặp
quyền riêng là thêm một ô người quản trị phải nhớ cấp, mà quên cấp thì
không ai sửa được quy tắc.

Kiểm ở MÁY CHỦ (danh sách đóng) và kiểm thêm lúc lưu: mẫu trả lời nhanh mà
quy tắc định gửi phải TỒN TẠI và SẠCH từ cấm quảng cáo — để lỗi lộ ra lúc
người vận hành bấm Lưu, không phải lúc khách đầu tiên nhắn vào.

Nhãn cũng vậy: id nhãn phải có trong danh mục và ĐÚNG LOẠI với khoá
(`nhan_khach_co` chỉ nhận nhãn khách). Khoá chữ cũ (`nhan_co`, `gan_nhan` +
tên) được đổi sang id ngay lúc lưu nếu tên có trong danh mục, không thì 422
— không còn đường nào lưu thêm nhãn chữ tự do vào quy tắc.
"""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agent import db
from agent.core import nhan as nhan_loi
from agent.core.cham_mot_luot import tu_cam_hai_dang
from agent.omnichannel import tu_dong

from .routes import can_quyen

router = APIRouter(prefix="/api/tu-dong", tags=["tu-dong"])


class QuyTacIn(BaseModel):
    ten: str = Field(min_length=1, max_length=80)
    su_kien: str = "tin_khach"
    dieu_kien: dict[str, Any] = Field(default_factory=dict)
    hanh_dong: list[dict[str, Any]]
    bat: bool = True
    thu_tu: int = Field(default=100, ge=0, le=10000)


async def _kiem(body: QuyTacIn) -> tuple[dict, list]:
    if body.su_kien not in tu_dong.SU_KIEN:
        raise HTTPException(422, f"Sự kiện phải là một trong: {', '.join(tu_dong.SU_KIEN)}")
    try:
        dk = tu_dong.kiem_dieu_kien(body.dieu_kien)
        hd = tu_dong.kiem_hanh_dong(body.hanh_dong)
    except tu_dong.QuyTacHong as exc:
        raise HTTPException(422, str(exc)) from exc
    dk, hd = await _chuan_nhan(dk, hd, bat=body.bat)
    # TẮT một quy tắc không được đòi nó hợp lệ: mẫu của quy tắc đã bị xoá
    # hay dính cụm cấm thì nút "Tắt" trả 422, quy tắc ghi "hỏng" mỗi tin
    # khách, và lối thoát duy nhất là Xoá (rà soát 28.10.2026).
    if not body.bat:
        return dk, hd
    for h in hd:
        if h["loai"] != "gui_mau":
            continue
        mau = await db.fetchrow("SELECT noi_dung FROM tra_loi_nhanh WHERE ma_tat = $1", h["ma_tat"])
        if mau is None:
            raise HTTPException(422, f"Không có mẫu trả lời nhanh /{h['ma_tat']} — tạo mẫu trước.")
        cum = tu_cam_hai_dang(mau["noi_dung"])
        if cum:
            raise HTTPException(422, f"Mẫu /{h['ma_tat']} chứa cụm cấm quảng cáo: {', '.join(cum)}")
    return dk, hd


async def _id_theo_ten(conn, ten: str) -> str:
    n = await nhan_loi.tim_theo_ten(conn, "hoi_thoai", ten)
    if n is None:
        raise HTTPException(422, (
            f"Chưa có nhãn hội thoại «{ten}» trong danh mục — tạo ở Cấu hình → "
            "Quản lý nhãn, rồi chọn nhãn trong quy tắc."))
    return str(n["id"])


async def _chuan_nhan(dk: dict, hd: list, *, bat: bool) -> tuple[dict, list]:
    """
    Đổi khoá nhãn chữ cũ sang id và kiểm mọi id nhãn với danh mục.

    Nhãn ĐÃ NGỪNG: điều kiện vẫn được trỏ tới (lọc hội thoại còn mang nhãn
    cũ là việc hợp lý), hành động GẮN thì không — trừ khi quy tắc đang tắt,
    cùng lý do tắt không đòi mẫu hợp lệ ở dưới: nút "Tắt" không được 422.
    """
    async with db.pool().acquire() as conn:
        dk = dict(dk)
        for cu, moi in (("nhan_co", "nhan_hoi_thoai_co"), ("nhan_khong", "nhan_hoi_thoai_khong")):
            if cu in dk:
                nid = await _id_theo_ten(conn, dk.pop(cu))
                dk[moi] = list(dict.fromkeys([*dk.get(moi, []), nid]))
        hd_moi = []
        for h in hd:
            if h["loai"] == "gan_nhan":
                h = {"loai": "gan_nhan_hoi_thoai", "nhan_id": await _id_theo_ten(conn, h["nhan"])}
            hd_moi.append(h)

        can: list[tuple[str, str, bool]] = []      # (id, loại phải có, cần đang dùng)
        for k, loai in tu_dong.DIEU_KIEN_NHAN.items():
            can += [(x, loai, False) for x in dk.get(k, [])]
        for h in hd_moi:
            if h["loai"] in tu_dong.HANH_DONG_NHAN:
                can.append((h["nhan_id"], tu_dong.HANH_DONG_NHAN[h["loai"]], bat))
        if can:
            co = {str(r["id"]): r for r in await conn.fetch(
                "SELECT id, loai, ten, dang_dung FROM nhan WHERE id = ANY($1::uuid[])",
                [UUID(x) for x, _, _ in can])}
            for x, loai, can_dung in can:
                r = co.get(x)
                if r is None:
                    raise HTTPException(422, f"Nhãn {x} không có trong danh mục.")
                if r["loai"] != loai:
                    raise HTTPException(422, (
                        f"«{r['ten']}» là {nhan_loi.TEN_LOAI[r['loai']].lower()} — ô này "
                        f"chỉ nhận {nhan_loi.TEN_LOAI[loai].lower()}."))
                if can_dung and not r["dang_dung"]:
                    raise HTTPException(422, (
                        f"Nhãn «{r['ten']}» đã ngừng sử dụng — không gắn mới được. "
                        "Chọn nhãn khác, hoặc bật lại nhãn trong Quản lý nhãn."))
    return dk, hd_moi


def _json(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def _dong(r) -> dict[str, Any]:
    return {"id": str(r["id"]), "ten": r["ten"], "su_kien": r["su_kien"],
            "dieu_kien": _json(r["dieu_kien"]), "hanh_dong": _json(r["hanh_dong"]),
            "bat": r["bat"], "thu_tu": r["thu_tu"], "sua_luc": r["sua_luc"].isoformat()}


@router.get("")
async def liet_ke(_q: dict = Depends(can_quyen("dinh_tuyen.doc"))) -> dict[str, Any]:
    rows = await db.fetch("SELECT * FROM quy_tac_tu_dong ORDER BY thu_tu, tao_luc")
    dem = {str(r["quy_tac_id"]): r for r in await db.fetch(
        "SELECT quy_tac_id, count(*) FILTER (WHERE ket_qua = 'da_lam') AS da_lam, "
        "count(*) FILTER (WHERE ket_qua = 'hong') AS hong, max(luc) AS lan_cuoi "
        "FROM quy_tac_lan_chay WHERE luc > now() - interval '7 days' GROUP BY 1")}
    ra = []
    for r in rows:
        d = _dong(r)
        t = dem.get(d["id"])
        d["bay_ngay"] = {"da_lam": int(t["da_lam"]) if t else 0, "hong": int(t["hong"]) if t else 0,
                         "lan_cuoi": t["lan_cuoi"].isoformat() if t and t["lan_cuoi"] else None}
        ra.append(d)
    return {"quy_tac": ra, "dieu_kien": list(tu_dong.DIEU_KIEN),
            "hanh_dong": list(tu_dong.HANH_DONG), "kenh": list(tu_dong.KENH)}


@router.post("", status_code=201)
async def tao(body: QuyTacIn, nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    dk, hd = await _kiem(body)
    r = await db.fetchrow(
        "INSERT INTO quy_tac_tu_dong (ten, su_kien, dieu_kien, hanh_dong, bat, thu_tu, tao_boi) "
        "VALUES ($1,$2,$3::jsonb,$4::jsonb,$5,$6,$7) RETURNING *",
        body.ten.strip(), body.su_kien, dk, hd, body.bat, body.thu_tu, UUID(str(nguoi["id"])))
    await db.log_event("tu_dong.tao", actor=nguoi.get("ten_dang_nhap") or "?", ten=body.ten.strip())
    return _dong(r)


@router.put("/{quy_tac_id}")
async def sua(quy_tac_id: UUID, body: QuyTacIn,
              nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> dict[str, Any]:
    dk, hd = await _kiem(body)
    r = await db.fetchrow(
        "UPDATE quy_tac_tu_dong SET ten=$2, su_kien=$3, dieu_kien=$4::jsonb, hanh_dong=$5::jsonb, "
        "bat=$6, thu_tu=$7, sua_luc=now() WHERE id=$1 RETURNING *",
        quy_tac_id, body.ten.strip(), body.su_kien, dk, hd, body.bat, body.thu_tu)
    if r is None:
        raise HTTPException(404, "Không thấy quy tắc.")
    await db.log_event("tu_dong.sua", actor=nguoi.get("ten_dang_nhap") or "?", ten=body.ten.strip())
    return _dong(r)


@router.delete("/{quy_tac_id}", status_code=204)
async def xoa(quy_tac_id: UUID, nguoi: dict = Depends(can_quyen("dinh_tuyen.sua"))) -> None:
    r = await db.fetchrow("DELETE FROM quy_tac_tu_dong WHERE id = $1 RETURNING ten", quy_tac_id)
    if r is None:
        raise HTTPException(404, "Không thấy quy tắc.")
    await db.log_event("tu_dong.xoa", actor=nguoi.get("ten_dang_nhap") or "?", ten=r["ten"])


@router.get("/lan-chay")
async def lan_chay(gioi_han: int = Query(50, ge=1, le=200),
                   _q: dict = Depends(can_quyen("dinh_tuyen.doc"))) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT l.*, q.ten FROM quy_tac_lan_chay l JOIN quy_tac_tu_dong q ON q.id = l.quy_tac_id "
        "ORDER BY l.luc DESC LIMIT $1", gioi_han)
    return {"lan_chay": [{"quy_tac": r["ten"], "conversation_id": str(r["conversation_id"] or ""),
                          "ket_qua": r["ket_qua"], "chi_tiet": _json(r["chi_tiet"]),
                          "luc": r["luc"].isoformat()} for r in rows]}
