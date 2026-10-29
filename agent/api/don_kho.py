"""
API đơn hàng, tồn kho, danh mục và ảnh sản phẩm.
"""
from __future__ import annotations

import uuid

from fastapi import (APIRouter, Depends, HTTPException)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agent import db
from agent.core import kho

from .phu_thuoc import (
    bat_buoc_dang_nhap,
    can_quyen,
)

router = APIRouter(prefix="/api")


@router.get("/san-pham/{ma}/anh")
async def anh_san_pham_file(ma: str, _nguoi: dict = Depends(bat_buoc_dang_nhap), _quyen: dict = Depends(can_quyen("don.doc"))):
    """
    Ảnh sản phẩm cho màn hình Kho và cho ô chọn khi nhân viên gửi ảnh.

    ĐƯỜNG DẪN DO MÁY CHỦ DỰNG, KHÔNG DO CLIENT
    ------------------------------------------
    `_anh_san_pham` tra mã trong danh mục rồi trả đường dẫn tương ứng. Client
    chỉ gửi MÃ, không gửi đường dẫn — nên một mã dạng `../../.env` không đi
    tới đâu cả: nó đơn giản không có trong danh mục.

    Đòi đăng nhập: ảnh sản phẩm không phải bí mật, nhưng mọi thứ dưới `/api`
    đều sau cổng đăng nhập, và mở một ngoại lệ là mở một đường để dò.
    """
    from agent.core.tools import _anh_san_pham

    duong = _anh_san_pham(ma)
    if duong is None or not duong.exists():
        raise HTTPException(404, f"Không có ảnh cho mã {ma}")
    return FileResponse(str(duong), media_type="image/jpeg")


# ---------------------------------------------------------------
#  Đơn hàng
# ---------------------------------------------------------------

@router.get("/orders")
async def list_orders(status: str | None = None, limit: int = 60, _quyen: dict = Depends(can_quyen("don.doc"))) -> list[dict]:
    sql = "SELECT * FROM orders"
    args: list = []
    if status and status != "all":
        sql += " WHERE trang_thai = $1"
        args.append(status)
    sql += f" ORDER BY created_at DESC LIMIT {int(limit)}"
    rows = await db.fetch(sql, *args)
    return [
        {
            "id": str(r["id"]),
            "ma_don": r["ma_don"],
            "khach_ten": r["khach_ten"],
            "khach_sdt": r["khach_sdt"],
            "khach_dia_chi": r["khach_dia_chi"],
            "items": r["items"],
            "tong_tien": int(r["tong_tien"]),
            "trang_thai": r["trang_thai"],
            "channel": r["channel"],
            "ghi_chu": r["ghi_chu"],
            "conversation_id": str(r["conversation_id"]) if r["conversation_id"] else None,
            "created_at": r["created_at"].isoformat(),
            # Màn Đơn hàng VẼ các trường dưới (cờ "Khách xin huỷ", lỗi đồng bộ
            # ERP, mã vận đơn) — nhưng trước 29.10.2026 API không trả chúng,
            # nên cờ xin huỷ KHÔNG BAO GIỜ hiện: hàng vẫn gói, khách từ chối
            # nhận, shop chịu phí hoàn, không lỗi nào. Có test canh mọi trường
            # màn hình đọc đều có mặt ở đây.
            **{k: _iso(r.get(k)) for k in _TRUONG_PHU_DON},
        }
        for r in rows
    ]


_TRUONG_PHU_DON = (
    "yeu_cau_huy_luc", "yeu_cau_huy_ly_do",
    "yeu_cau_doi_tra_luc", "yeu_cau_doi_tra_loai", "yeu_cau_doi_tra_ly_do",
    "erp_ma_don", "erp_loi", "erp_so_lan_thu",
    "ma_van_don", "don_vi_van_chuyen", "trang_thai_giao_hang",
)


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _items(gia_tri) -> list[dict]:
    if isinstance(gia_tri, str):
        import json

        try:
            gia_tri = json.loads(gia_tri)
        except ValueError:
            return []
    return list(gia_tri or [])


def _uuid_don(order_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(order_id)
    except ValueError:
        raise HTTPException(404, "Không có đơn này") from None


@router.post("/orders/{order_id}/approve")
async def approve_order(order_id: str, nguoi: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Duyệt đơn đang CHỜ DUYỆT (đơn từ ngưỡng tự chốt trở lên) — rồi đẩy sang
    ERP như đơn agent tự chốt.

    Hai lỗi của bản trước (rà soát 29.10.2026):
      - Không kiểm trạng thái: bấm Duyệt trên một đơn ĐÃ HUỶ (hàng đã trả về
        kho) làm nó thành `da_chot` mà kho không trừ lại — bán một món không
        còn trên kệ. Nay chỉ `cho_duyet` → `da_chot`, nguyên tử trong một câu.
      - Không đẩy ERP: đơn lớn nhất không bao giờ vào ERP. Xem
        `day_don.day_don_da_luu`.
    """
    from agent.erp import day_don

    oid = _uuid_don(order_id)
    don = await db.fetchrow(
        "UPDATE orders SET trang_thai='da_chot', updated_at=now() "
        "WHERE id=$1 AND trang_thai='cho_duyet' RETURNING *", oid,
    )
    if don is None:
        hien = await db.fetchrow("SELECT trang_thai FROM orders WHERE id=$1", oid)
        if hien is None:
            raise HTTPException(404, "Không có đơn này")
        raise HTTPException(
            409, f"Đơn đang ở trạng thái '{hien['trang_thai']}' — chỉ duyệt được "
                 "đơn đang chờ duyệt.")
    await db.log_event("order.approve", actor="staff", ref_id=oid, ma_don=don["ma_don"],
                       boi=nguoi.get("ten_dang_nhap"))
    kq = await day_don.day_don_da_luu(
        oid, ma_don=don["ma_don"], khach_ten=str(don.get("khach_ten") or ""),
        khach_sdt=str(don.get("khach_sdt") or ""),
        khach_dia_chi=str(don.get("khach_dia_chi") or ""),
        items=_items(don.get("items")), ghi_chu=str(don.get("ghi_chu") or ""),
    )
    trang_thai = {"tu_choi": "da_huy", "cho_lai": "cho_dong_bo"}.get(kq.ket_cuc, "da_chot")
    return {"ok": kq.ket_cuc != "tu_choi", "ma_don": don["ma_don"], "trang_thai": trang_thai,
            "erp": kq.ket_cuc, "erp_ma_don": kq.erp_ma_don or None, "erp_loi": kq.ly_do or None}


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: str, _quyen: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Huỷ đơn và TRẢ HÀNG VỀ KHO.

    Không trả lại thì mỗi đơn huỷ ăn mất tồn kho vĩnh viễn — bán mười đơn
    huỷ chín đơn là kho báo hết hàng trong khi hàng vẫn nằm nguyên trên kệ.
    """
    oid = _uuid_don(order_id)
    don = await db.fetchrow(
        "UPDATE orders SET trang_thai='da_huy', updated_at=now() "
        "WHERE id=$1 AND trang_thai <> 'da_huy' RETURNING ma_don, erp_ma_don, ma_van_don", oid,
    )
    if don is None:
        return {"ok": True, "ghi_chu": "Đơn đã huỷ từ trước, không trả kho lần nữa."}

    so_dong = await kho.tra_hang(don["ma_don"])
    await db.log_event("order.cancel", actor="staff", ref_id=oid,
                       ma_don=don["ma_don"], so_mat_hang_tra_kho=so_dong)
    kq: dict = {"ok": True, "ma_don": don["ma_don"], "da_tra_kho": so_dong}
    # Huỷ ở đây KHÔNG huỷ bên ERP hay bên hãng vận chuyển. Nói thẳng lúc
    # bấm, để người huỷ tay bên đó — im là ERP vẫn xuất kho, hãng vẫn đi
    # lấy hàng cho một đơn đã huỷ.
    ben = []
    if don.get("erp_ma_don"):
        ben.append(f"ERP (đơn {don['erp_ma_don']})")
    if don.get("ma_van_don"):
        ben.append(f"hãng vận chuyển (vận đơn {don['ma_van_don']})")
    if ben:
        kq["can_huy_tay"] = ("Đơn đã có bên " + " và ".join(ben)
                             + ": vào đó huỷ tay, hệ thống không tự huỷ hộ.")
        await db.log_event("order.cancel_can_huy_tay", ref_id=oid, ma_don=don["ma_don"],
                           erp_ma_don=don.get("erp_ma_don"), ma_van_don=don.get("ma_van_don"))
    return kq


@router.get("/van-chuyen/cau-hinh")
async def van_chuyen_cau_hinh(_quyen: dict = Depends(can_quyen("don.doc"))) -> dict:
    """Màn Đơn hàng hỏi: đã nối hãng thật chưa — để biết có hiện nút tạo vận đơn."""
    from agent.config import settings

    hang = (settings.shipping_provider or "mock").strip().lower()
    return {"hang": hang, "that": hang in HANG_THAT}


class VanDonIn(BaseModel):
    # Trống = hãng mặc định (SHIPPING_PROVIDER).
    hang: str = Field("", max_length=10)


@router.post("/orders/{order_id}/van-don")
async def tao_van_don(order_id: str, body: VanDonIn | None = None,
                      nguoi: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Tạo vận đơn GHN/GHTK cho một đơn đã chốt — nút "Tạo vận đơn" trên màn
    Đơn hàng. Bốn chốt (trạng thái, đủ thông tin, đã giữ hàng, chống trùng)
    nằm trong `shipping.service.tao_van_don_cho_don`; hàm ấy có từ lâu nhưng
    trước 29.10.2026 không nối vào đâu cả.

    TỪ CHỐI hãng giả lập: vận đơn giả vẫn nhắn khách "đã bàn giao cho hãng,
    mã vận đơn …" — một mã không tra được ở đâu, cho một kiện chưa rời kệ.

    Khoá theo mã đơn trong lúc gọi hãng: bấm hai lần (hai tab, mạng chậm)
    không được tạo hai vận đơn — chốt "chưa có mã vận đơn" chỉ đọc, hai lời
    gọi cùng lúc đều thấy chưa có.
    """
    from agent.config import settings
    from agent.shipping import service

    hang = ((body.hang if body else "") or settings.shipping_provider or "mock").strip().lower()
    if hang not in HANG_THAT:
        raise HTTPException(
            409, f"Chưa nối hãng vận chuyển thật (đang là '{hang}'). Đặt SHIPPING_PROVIDER="
                 "ghn hoặc ghtk cùng khoá API của hãng trong .env rồi khởi động lại.")
    oid = _uuid_don(order_id)
    don = await db.fetchrow("SELECT ma_don FROM orders WHERE id=$1", oid)
    if don is None:
        raise HTTPException(404, "Không có đơn này")
    ma_don = don["ma_don"]
    async with db.pool().acquire() as conn:
        if not await conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtext('van_don:' || $1))", ma_don):
            raise HTTPException(409, "Đang tạo vận đơn cho đơn này — đợi vài giây rồi tải lại.")
        try:
            kq = await service.tao_van_don_cho_don(ma_don, hang)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(hashtext('van_don:' || $1))", ma_don)
    if not kq.ok:
        await db.log_event("shipping.tao_that_bai", ref_id=oid, ma_don=ma_don, hang=hang,
                           loi=(kq.loi or "")[:300], boi=nguoi.get("ten_dang_nhap"))
        raise HTTPException(422, kq.loi or "Hãng từ chối tạo vận đơn.")
    return {"ok": True, "ma_don": ma_don, "ma_van_don": kq.ma_van_don, "hang": hang,
            "phi_van_chuyen": kq.phi_van_chuyen,
            "da_co_san": bool((kq.thong_tin_them or {}).get("da_co_san"))}


# Hãng có bộ nối thật. `mock` cố ý KHÔNG có ở đây — xem `tao_van_don`.
HANG_THAT = ("ghn", "ghtk")


# ---------------------------------------------------------------
#  Kho hàng
# ---------------------------------------------------------------

class NhapKhoIn(BaseModel):
    so_luong: int = Field(gt=0, le=100000)
    ghi_chu: str = Field("", max_length=300)


class KiemKeIn(BaseModel):
    so_luong_moi: int = Field(ge=0, le=100000)
    ly_do: str = Field(min_length=3, max_length=300)


@router.get("/kho")
async def kho_tong_quan(_quyen: dict = Depends(can_quyen("don.doc"))) -> dict:
    """Tồn kho sống của mọi mã, kèm tên và giá lấy từ danh mục."""
    from agent.core.tools import _anh_san_pham, _catalog

    danh_muc = {p["ma"]: p for p in _catalog().get("san_pham", [])}
    ton = await db.fetch("SELECT ma, so_luong, cap_nhat_luc FROM ton_kho ORDER BY ma")

    # Giá của mã KHÔNG nằm trong danh mục thì hỏi ERP.
    #
    # `catalog.json` cố ý chỉ chứa hàng ĐANG BÁN — đó là thứ agent được phép
    # tư vấn, và nhồi hàng ngừng bán vào đó là agent bắt đầu chào bán chúng.
    # Nhưng màn Kho trả lời một câu hỏi KHÁC: "trong kho còn gì, đáng bao
    # nhiêu". Đo được 14.09.2026: 22 trong 35 dòng tồn kho là hàng thật đã
    # ngừng bán, còn 1.088 đơn vị, có giá đầy đủ ở ERPNext — và ô "Giá trị
    # tồn" bỏ sót toàn bộ, riêng một mã đã 28 triệu.
    #
    # Hỏi SONG SONG và chỉ hỏi mã còn thiếu: mỗi lời gọi là một vòng mạng,
    # và cổng đã có cache giá TTL dài nên lần sau gần như miễn phí.
    thieu_gia = [x["ma"] for x in ton if x["ma"] not in danh_muc]
    gia_erp: dict[str, int | None] = {}
    if thieu_gia:
        import asyncio as _asyncio

        from agent.erp import nha_may as _nha_may

        _cong = _nha_may.cong()

        async def _hoi_gia(ma: str):
            try:
                g = await _cong.gia(ma)
            except Exception:  # noqa: BLE001 — ERP sập không được làm mất bảng
                return ma, None
            return ma, (int(g.gia_ban) if g and g.gia_ban else None)

        for ma, g in await _asyncio.gather(*(_hoi_gia(m) for m in thieu_gia)):
            gia_erp[ma] = g

    ra = []
    for t in ton:
        sp = danh_muc.get(t["ma"], {})
        # None = CHƯA TRA ĐƯỢC, khác hẳn 0. Gộp hai thứ là nói dối một cách
        # tự tin: cộng thêm 0 vào "giá trị tồn" trông y hệt như món ấy không
        # đáng gì, trong khi sự thật là chưa biết.
        gia = sp.get("gia") if t["ma"] in danh_muc else gia_erp.get(t["ma"])
        ra.append({
            "ma": t["ma"],
            "ten": sp.get("ten", "(không có trong danh mục)"),
            "loai": sp.get("loai", ""),
            "gia": gia,
            "so_luong": int(t["so_luong"]),
            "sap_het": int(t["so_luong"]) <= kho.NGUONG_SAP_HET,
            "cap_nhat_luc": t["cap_nhat_luc"].isoformat(),
            # Người trực cần thấy ẢNH để đối chiếu khi khách mô tả sản phẩm
            # bằng lời — "cái chai xanh xanh ấy" — thay vì mở thư mục ra tìm.
            "co_anh": _anh_san_pham(t["ma"]) is not None,
            "dung_tich": sp.get("dung_tich", ""),
            "da_phu_hop": sp.get("da_phu_hop", []),
            "van_de_ho_tro": sp.get("van_de_ho_tro", []),
        })
    het = [x for x in ra if x["so_luong"] == 0]
    sap = [x for x in ra if 0 < x["so_luong"] <= kho.NGUONG_SAP_HET]
    return {
        "san_pham": ra,
        "tong_ma": len(ra),
        "het_hang": len(het),
        "sap_het": len(sap),
        "nguong_sap_het": kho.NGUONG_SAP_HET,
        "gia_tri_ton": sum(x["so_luong"] * (x["gia"] or 0) for x in ra),
        # Đếm ra chứ không giấu: không có con số này thì người đọc tưởng
        # tổng đã đủ, trong khi vài mã còn chưa tra được giá.
        "so_ma_chua_biet_gia": sum(1 for x in ra if x["gia"] is None),
    }


@router.get("/kho/bien-dong")
async def kho_bien_dong(ma: str = "", limit: int = 50, _quyen: dict = Depends(can_quyen("don.doc"))) -> dict:
    return {"bien_dong": await kho.so_bien_dong(ma, limit)}


@router.post("/kho/{ma}/nhap")
async def kho_nhap(ma: str, body: NhapKhoIn, _quyen: dict = Depends(can_quyen("don.sua"))) -> dict:
    try:
        r = await kho.nhap_hang(ma, body.so_luong, body.ghi_chu)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("kho.nhap", actor="nguoi", ma=ma, so_luong=body.so_luong)
    return r


@router.post("/kho/{ma}/kiem-ke")
async def kho_kiem_ke(ma: str, body: KiemKeIn, _quyen: dict = Depends(can_quyen("don.sua"))) -> dict:
    """
    Đặt lại số tồn về đúng thực tế đếm được.

    Kho LUÔN lệch — vỡ, mất, đếm sai. Cần một đường sửa hợp lệ, và đường đó
    bắt buộc phải có lý do để sau này truy được.
    """
    try:
        r = await kho.dieu_chinh(ma, body.so_luong_moi, body.ly_do)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("kho.kiem_ke", actor="nguoi", **r, ly_do=body.ly_do)
    return r


@router.get("/catalog/products")
async def catalog_products(_quyen: dict = Depends(can_quyen("don.doc"))) -> dict:
    """
    Danh sách gọn cho ô gợi ý sản phẩm khi soạn bài hoặc đặt video.

    Đọc qua `tools._catalog()` chứ không mở thẳng `catalog.json`: máy vừa
    clone repo về chưa có file đó, mở thẳng là ném FileNotFoundError và cả
    trang trắng. Hàm kia tự rơi về bản mẫu đi kèm repo.

    `so_anh` cho biết sản phẩm nào dựng video có hình được, sản phẩm nào chỉ
    ra thẻ chữ — biết trước vẫn hơn nhận về rồi mới thấy.
    """
    from agent.core.tools import _catalog
    from agent.video import catalog_images

    return {"san_pham": [
        {
            "ma": p["ma"],
            "ten": p["ten"],
            "loai": p.get("loai", ""),
            "so_anh": len(catalog_images.anh_cua(p["ma"])),
        }
        for p in _catalog().get("san_pham", [])
    ]}
