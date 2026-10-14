"""
API thanh toán: mã VietQR cho từng đơn, và gửi mã ấy cho khách.

Số tiền = tổng hàng + phí vận chuyển, đọc từ CSDL — KHÔNG nhận từ trình
duyệt. Nội dung chuyển khoản = mã đơn, để đối soát tiền về với đơn.

Đơn gắn với một hội thoại thì đi qua chốt phạm vi kênh: QR mang tên và
số tiền đơn của khách, xem nó cũng là xem dữ liệu của hội thoại ấy.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from agent import cau_hinh_dong, db
from agent.omnichannel.outbound_service import (
    ConversationNotFound,
    OutboundService,
    PostgresOutboundRepository,
)
from agent.thanh_toan import vietqr

from .routes import (
    THU_MUC_TAI_LEN,
    _nguoi_id,
    _xet_cua_so_hoac_409,
    can_quyen,
    chan_neu_khong_duoc_tra_loi,
    chan_neu_ngoai_kenh,
)

router = APIRouter(prefix="/api/orders", tags=["thanh-toan"])


def _ngan_hang() -> dict[str, str]:
    nh = {"bin": cau_hinh_dong.lay("VIETQR_BIN"),
          "so_tk": cau_hinh_dong.lay("VIETQR_SO_TK"),
          "ten": cau_hinh_dong.lay("VIETQR_TEN_TK")}
    thieu = [t for k, t in (("bin", "mã BIN ngân hàng"), ("so_tk", "số tài khoản"))
             if not nh[k]]
    if thieu:
        # 409 có lời giải thích, không 500: đây là cấu hình chưa xong, và
        # người bấm nút cần biết phải đi đâu để sửa.
        raise HTTPException(409, "Chưa cấu hình VietQR: thiếu " + ", ".join(thieu)
                            + ". Vào Cấu hình → Thanh toán (VietQR).")
    return nh


async def _don(order_id: UUID, nguoi: dict) -> dict[str, Any]:
    r = await db.fetchrow(
        "SELECT id, ma_don, tong_tien, phi_van_chuyen, trang_thai, conversation_id "
        "FROM orders WHERE id = $1", order_id)
    if r is None:
        raise HTTPException(404, "Không thấy đơn hàng.")
    if r["conversation_id"] is not None:
        await chan_neu_ngoai_kenh(r["conversation_id"], nguoi)
    if r["trang_thai"] == "da_huy":
        raise HTTPException(409, "Đơn đã huỷ — không tạo mã thanh toán.")
    return dict(r)


def _payload(don: dict, nh: dict) -> tuple[str, int]:
    so_tien = int(don["tong_tien"] or 0) + int(don["phi_van_chuyen"] or 0)
    try:
        return vietqr.tao_payload(bin_nh=nh["bin"], so_tk=nh["so_tk"],
                                  so_tien=so_tien, noi_dung=don["ma_don"]), so_tien
    except ValueError as exc:
        raise HTTPException(409, f"Không tạo được mã VietQR: {exc}") from exc


@router.get("/{order_id}/vietqr")
async def vietqr_json(order_id: UUID,
                      nguoi: dict = Depends(can_quyen("don.doc"))) -> dict[str, Any]:
    don = await _don(order_id, nguoi)
    nh = _ngan_hang()
    payload, so_tien = _payload(don, nh)
    return {"payload": payload, "so_tien": so_tien, "noi_dung": don["ma_don"],
            "ngan_hang": nh}


@router.get("/{order_id}/vietqr.svg")
async def vietqr_svg(order_id: UUID,
                     nguoi: dict = Depends(can_quyen("don.doc"))) -> Response:
    don = await _don(order_id, nguoi)
    payload, _ = _payload(don, _ngan_hang())
    return Response(vietqr.ve_svg(payload), media_type="image/svg+xml",
                    headers={"Cache-Control": "no-store"})


@router.post("/{order_id}/vietqr/gui")
async def gui_vietqr(order_id: UUID,
                     nguoi: dict = Depends(can_quyen("hoi_thoai.tra_loi"))) -> dict[str, Any]:
    """
    Gửi ảnh QR vào hội thoại của đơn — qua outbox, như mọi tin của người.

    Cùng ba chốt với nút Gửi: phạm vi kênh, mức tầm nhìn, cửa sổ nhắn tin.
    Khoá idempotency theo (đơn, số tiền): bấm hai lần không gửi hai mã; đơn
    đổi tiền thì gửi được mã mới.
    """
    if "don.doc" not in (nguoi.get("quyen") or ()):
        raise HTTPException(403, "Cần quyền xem đơn hàng.")
    don = await _don(order_id, nguoi)
    if don["conversation_id"] is None:
        raise HTTPException(409, "Đơn này không gắn với hội thoại nào — không có chỗ gửi.")
    cid = don["conversation_id"]
    await chan_neu_khong_duoc_tra_loi(cid, nguoi)
    the = await _xet_cua_so_hoac_409(cid)
    nh = _ngan_hang()
    payload, so_tien = _payload(don, nh)

    import segno

    THU_MUC_TAI_LEN.mkdir(parents=True, exist_ok=True)
    # Tên tất định theo (đơn, số tiền): bấm lại thì ghi đè đúng tệp ấy, không
    # để lại tệp mồ côi mỗi lần.
    duong = THU_MUC_TAI_LEN / f"vietqr-{order_id}-{so_tien}.png"
    segno.make(payload, error="m", micro=False).save(str(duong), kind="png", scale=8, border=3)
    chu = (f"Mã QR thanh toán đơn {don['ma_don']}: {so_tien:,}đ".replace(",", ".")
           + (f" — {nh['ten']}" if nh["ten"] else "")
           + ". Anh/chị quét bằng app ngân hàng, nội dung đã điền sẵn mã đơn ạ.")
    try:
        q = await OutboundService(PostgresOutboundRepository()).queue_file(
            conversation_id=cid, role="staff", path=str(duong), caption=chu,
            idempotency_key=f"vietqr:{order_id}:{so_tien}", the=the,
            gui_boi=_nguoi_id(nguoi))
    except ConversationNotFound as exc:
        raise HTTPException(404, "Không thấy hội thoại của đơn.") from exc
    await db.log_event("thanh_toan.gui_vietqr", actor=nguoi.get("ten_dang_nhap") or "?",
                       ref_id=cid, ma_don=don["ma_don"], so_tien=so_tien)
    return {"ok": True, "duplicate": q.duplicate, "message_id": str(q.message_id)}
