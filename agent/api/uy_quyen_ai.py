"""
Ủy quyền thực thi của AI (mục 17): chính sách theo hành động, và thẻ đề xuất
chờ duyệt trong hội thoại.

QUYỀN — VÀ VÌ SAO
-----------------
  xem chính sách    `cau_hinh.doc`      cùng quyền mở tab Cấu hình AI Agent
  sửa chính sách    `agent.dieu_khien`  cùng họ với đổi chế độ Gợi ý/Tự động
                                        và ngưỡng: đều là "AI được tự làm tới
                                        đâu". `cau_hinh.sua` là kho tri thức
                                        và cấu hình chung — người sửa tài liệu
                                        không vì thế mà được nới quyền của AI.
  xem thẻ đề xuất   `hoi_thoai.doc` + thuộc kênh của hội thoại
  duyệt / từ chối   `ai.duyet` + QUYỀN NGHIỆP VỤ của hành động (`don.sua` cho
                    tạo/huỷ đơn) + thuộc kênh. Duyệt không được là đường vòng
                    để làm qua AI việc mình không được làm tay ở màn Đơn hàng.

THI HÀNH KIỂM LẠI TỪ ĐẦU
------------------------
Đề xuất là ảnh chụp lúc AI soạn. Lúc người bấm Duyệt, tồn kho, giá, trạng
thái đơn có thể đã khác. Mỗi đường thi hành dưới đây chạy lại ĐÚNG hàm mà
người làm tay sẽ chạy (lên đơn, duyệt đơn, huỷ đơn), với đủ chốt của hàm ấy —
không tin `tham_so` là còn đúng.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import db
from agent.core import uy_quyen, xac_thuc

from .phu_thuoc import can_quyen, chan_neu_ngoai_kenh

router = APIRouter(prefix="/api", tags=["uy-quyen-ai"])


def _uuid(x: str, ten: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(x))
    except ValueError as exc:
        raise HTTPException(404, f"Không có {ten} này") from exc


def _ten(nguoi: dict) -> str:
    return str(nguoi.get("ten_dang_nhap") or "?")


# ---------------------------------------------------------------- chính sách

@router.get("/ai-uy-quyen")
async def xem_chinh_sach(_q: dict = Depends(can_quyen("cau_hinh.doc"))) -> dict:
    return await uy_quyen.mo_ta_chinh_sach()


class MucIn(BaseModel):
    muc: str = Field(max_length=20)
    nguong_vnd: int | None = Field(default=None, ge=0, le=10_000_000_000)


class ChinhSachIn(BaseModel):
    hanh_dong: dict[str, MucIn] = Field(default_factory=dict)
    han_gio: int | None = Field(default=None, ge=1, le=uy_quyen.HAN_TOI_DA_GIO)


@router.put("/ai-uy-quyen")
async def sua_chinh_sach(body: ChinhSachIn,
                         nguoi: dict = Depends(can_quyen("agent.dieu_khien"))) -> dict:
    """
    Kiểm HẾT rồi mới ghi: một dòng sai không được để nửa trên đã lưu, nửa
    dưới không — màn hình khi ấy nói "lỗi" trong khi một nửa chính sách đã đổi.
    """
    loi = []
    for ma, m in body.hanh_dong.items():
        hd = uy_quyen.DANH_MUC.get(ma)
        if hd is None:
            loi.append(f"Không có hành động {ma!r}")
        elif not (hd.ho_tro and hd.cau_hinh_duoc):
            loi.append(f"«{hd.ten}» không đổi được mức")
        elif m.muc not in uy_quyen.MUC:
            loi.append(f"Mức không hợp lệ cho «{hd.ten}»: {m.muc!r}")
        elif m.nguong_vnd is not None and not hd.co_nguong:
            loi.append(f"«{hd.ten}» không có ngưỡng giá trị")
    if loi:
        raise HTTPException(422, "; ".join(loi))
    for ma, m in body.hanh_dong.items():
        await uy_quyen.luu_chinh_sach(ma, m.muc, nguong_vnd=m.nguong_vnd, boi=_ten(nguoi))
    if body.han_gio is not None:
        await uy_quyen.luu_han_gio(body.han_gio, boi=_ten(nguoi))
    return await uy_quyen.mo_ta_chinh_sach()


# ------------------------------------------------------------- thẻ đề xuất

@router.get("/ai-de-xuat")
async def ds_de_xuat(hoi_thoai: str,
                     nguoi: dict = Depends(can_quyen("hoi_thoai.doc"))) -> dict:
    cid = _uuid(hoi_thoai, "hội thoại")
    await chan_neu_ngoai_kenh(cid, nguoi)
    return {"de_xuat": await uy_quyen.liet_ke(cid, nguoi=nguoi)}


async def _kiem_quyen_de_xuat(de_xuat_id: uuid.UUID, nguoi: dict) -> dict:
    dong = await db.fetchrow(
        "SELECT conversation_id, hanh_dong FROM ai_de_xuat WHERE id = $1", de_xuat_id)
    if dong is None:
        raise HTTPException(404, "Không có đề xuất này")
    await chan_neu_ngoai_kenh(dong["conversation_id"], nguoi)
    hd = uy_quyen.DANH_MUC.get(dong["hanh_dong"])
    if hd and hd.quyen_thi_hanh and not xac_thuc.duoc_phep(nguoi, hd.quyen_thi_hanh):
        raise HTTPException(403, f"Thiếu quyền: {hd.quyen_thi_hanh} — duyệt «{hd.ten}» "
                                 "cần cả quyền làm việc ấy bằng tay")
    return dong


async def _thi_hanh(dx: dict, nguoi: dict) -> tuple[bool, dict, str | None, Any]:
    """(ok, kết quả, lỗi, order_id mới). Kiểm lại điều kiện nghiệp vụ TỪ ĐẦU."""
    from agent.core import thao_tac_don, tools

    hanh_dong = dx["hanh_dong"]
    ts = dx.get("tham_so") or {}
    cid = dx["conversation_id"]
    if hanh_dong == "tao_don" and dx.get("order_id"):
        # Đơn đã ghi ở `cho_duyet` (Tự động vượt ngưỡng / Có phê duyệt):
        # duyệt = chính nút Duyệt của màn Đơn hàng, đủ chốt trạng thái + ERP.
        from agent.api import don_kho

        try:
            kq = await don_kho.approve_order(str(dx["order_id"]), nguoi)
        except HTTPException as exc:
            return False, {}, str(exc.detail), None
        if not kq.get("ok"):
            return False, kq, f"ERP từ chối đơn: {kq.get('erp_loi') or ''}".strip(), None
        return True, kq, None, None
    if hanh_dong == "tao_don":
        # Chế độ Gợi ý: đơn chưa từng được ghi. Chạy lại TOÀN BỘ đường lên
        # đơn — xác nhận, thông tin, địa giới, giá danh mục, tồn sống, chống
        # trùng, giữ hàng, ERP — chỉ khác là người đã duyệt nên chốt luôn.
        catalog = await tools._catalog_song()
        tham_so = {k: v for k, v in ts.items() if k != "tong_tien"}
        kq = await tools._tao_don_hang(
            tham_so, catalog.get("san_pham", []), cid,
            ep_da_chot=True, tong_phai_bang=ts.get("tong_tien"))
        if kq.get("tao_duoc") is not True:
            return False, kq, str(kq.get("ly_do") or "Không lên được đơn"), None
        moi = await db.fetchrow("SELECT id FROM orders WHERE ma_don = $1", kq.get("ma_don"))
        return True, kq, None, (moi["id"] if moi else None)
    if hanh_dong == "huy_don":
        oid = uuid.UUID(str(ts.get("order_id") or dx.get("order_id")))
        try:
            kq = await thao_tac_don.huy_don(oid, actor=_ten(nguoi), conversation_id=cid)
        except thao_tac_don.LoiThaoTacDon as exc:
            return False, {}, exc.thong_diep, None
        if kq.get("da_huy_tu_truoc"):
            return False, kq, "Đơn đã huỷ từ trước — không thi hành lần nữa.", None
        # Đề xuất khác còn chờ trên chính đơn này (vd. duyệt đơn) hết nghĩa.
        await uy_quyen.dong_theo_don(oid, "huy", boi=_ten(nguoi))
        return True, kq, None, None
    return False, {}, f"Không có đường thi hành cho {hanh_dong!r}", None


class TuChoiIn(BaseModel):
    ly_do: str = Field(default="", max_length=500)


@router.post("/ai-de-xuat/{de_xuat_id}/duyet")
async def duyet_de_xuat(de_xuat_id: str,
                        nguoi: dict = Depends(can_quyen("ai.duyet"))) -> dict:
    did = _uuid(de_xuat_id, "đề xuất")
    await _kiem_quyen_de_xuat(did, nguoi)
    try:
        dx = await uy_quyen.nhan_duyet(did, nguoi)
    except uy_quyen.LoiDeXuat as exc:
        raise HTTPException(exc.ma, exc.thong_diep) from exc
    try:
        ok, ket_qua, loi, order_moi = await _thi_hanh(dx, nguoi)
    except Exception as exc:  # noqa: BLE001 — không để đề xuất kẹt ở "đã duyệt"
        ok, ket_qua, loi, order_moi = False, {}, f"Lỗi hệ thống: {type(exc).__name__}", None
    if order_moi is not None:
        await db.execute("UPDATE ai_de_xuat SET order_id = $2 WHERE id = $1", did, order_moi)
    sau = await uy_quyen.ghi_ket_qua(did, ok=ok, ket_qua=ket_qua, loi=loi, actor=_ten(nguoi))
    return {"ok": ok, "trang_thai": sau["trang_thai"],
            "nhan_trang_thai": uy_quyen.NHAN_TRANG_THAI[sau["trang_thai"]],
            "ket_qua": ket_qua, "loi": loi}


@router.post("/ai-de-xuat/{de_xuat_id}/tu-choi")
async def tu_choi_de_xuat(de_xuat_id: str, body: TuChoiIn | None = None,
                          nguoi: dict = Depends(can_quyen("ai.duyet"))) -> dict:
    did = _uuid(de_xuat_id, "đề xuất")
    await _kiem_quyen_de_xuat(did, nguoi)
    try:
        dx = await uy_quyen.tu_choi(did, nguoi, body.ly_do if body else "")
    except uy_quyen.LoiDeXuat as exc:
        raise HTTPException(exc.ma, exc.thong_diep) from exc
    kq: dict = {"ok": True, "trang_thai": "tu_choi"}
    if dx["hanh_dong"] == "tao_don" and dx.get("order_id"):
        # Từ chối duyệt một đơn ĐÃ giữ hàng = huỷ đơn ấy và trả kho. Để nó
        # nằm `cho_duyet` là hàng bị giữ cho một đơn không ai duyệt nữa.
        from agent.core import thao_tac_don

        hien = await db.fetchrow("SELECT trang_thai FROM orders WHERE id = $1", dx["order_id"])
        if hien and hien["trang_thai"] == "cho_duyet":
            try:
                kq["huy_don"] = await thao_tac_don.huy_don(dx["order_id"], actor=_ten(nguoi))
            except thao_tac_don.LoiThaoTacDon as exc:
                kq["canh_bao"] = f"Chưa huỷ được đơn chờ duyệt: {exc.thong_diep}"
    return kq
