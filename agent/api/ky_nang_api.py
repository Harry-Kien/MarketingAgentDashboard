"""
API kỹ năng cắm thêm và ứng dụng tích hợp.
"""
from __future__ import annotations


from fastapi import (APIRouter, Depends, HTTPException)
from pydantic import BaseModel, Field

from agent.api import tich_hop_kho
from agent.api.tich_hop_kho import LoiUngDung
from agent.ky_nang import kho_ky_nang
from agent.ky_nang.ban_mo_ta import LoiBanMoTa, doc_ban_mo_ta
from agent.ky_nang.cau_thu import chay_cau_thu
from agent.ky_nang.chay import chay_plugin

from .phu_thuoc import (
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Kỹ năng (skill) và kỹ năng cắm thêm (plugin)
# ---------------------------------------------------------------
#
# TOÀN BỘ nhóm này chỉ quản trị viên gọi được, kể cả đường ĐỌC.
#
# Đường đọc thường để công khai trong dashboard, nhưng ở đây nó trả về danh
# sách chính xác những gì agent làm được và làm không được. Với người muốn
# lách agent, đó là bản đồ — biết `tao_don_hang` đang tắt là biết không cần
# thử con đường ấy nữa. Không có lý do gì để người trực ca cần bản đồ đó.

@router.get("/ky-nang")
async def liet_ke_ky_nang(_: dict = Depends(can_quyen("ky_nang.doc"))) -> dict:
    return await kho_ky_nang.liet_ke()


class BatTatBody(BaseModel):
    ten: str = Field(min_length=3, max_length=40)
    bat: bool


@router.post("/ky-nang/bat-tat")
async def bat_tat_ky_nang(
    body: BatTatBody, nguoi: dict = Depends(can_quyen("ky_nang.sua"))
) -> dict:
    try:
        await kho_ky_nang.dat_bat_tat(body.ten, body.bat, boi=nguoi["ten_dang_nhap"])
    except LoiBanMoTa as exc:
        raise HTTPException(400, str(exc)) from exc
    return await kho_ky_nang.liet_ke()


@router.post("/ky-nang/plugin")
async def luu_ky_nang_plugin(
    body: dict, nguoi: dict = Depends(can_quyen("ky_nang.sua"))
) -> dict:
    """
    Tạo hoặc sửa một plugin.

    Nhận `dict` thô thay vì một model Pydantic: bộ kiểm thật nằm trong
    `doc_ban_mo_ta`, và nó ném ra câu nói rõ phải sửa gì. Dựng thêm một model
    Pydantic ở đây là có HAI bộ kiểm cho cùng một thứ, và cái nào lỏng hơn
    sẽ là cái quyết định.
    """
    try:
        bm = await kho_ky_nang.luu_plugin(body, boi=nguoi["ten_dang_nhap"])
    except LoiBanMoTa as exc:
        raise HTTPException(400, str(exc)) from exc
    # Chạy câu thử NGAY sau khi lưu, không đợi ai bấm nút.
    #
    # Một nút "chạy câu thử" riêng thì không ai bấm, và bộ câu thử không
    # được chạy là bộ câu thử không canh gì. Không CHẶN lưu khi trượt:
    # người vận hành có thể đang sửa dở (đổi khoá trước, sửa câu thử sau),
    # và chặn ở đó dạy họ cách nhanh nhất là xoá câu thử đi.
    return {"ten": bm.ten, "loai": bm.loai, "cau_thu": await chay_cau_thu(bm)}


@router.delete("/ky-nang/plugin/{ten}")
async def xoa_ky_nang_plugin(
    ten: str, nguoi: dict = Depends(can_quyen("ky_nang.sua"))
) -> dict:
    try:
        da_xoa = await kho_ky_nang.xoa_plugin(ten, boi=nguoi["ten_dang_nhap"])
    except LoiBanMoTa as exc:
        raise HTTPException(400, str(exc)) from exc
    if not da_xoa:
        raise HTTPException(404, f"Không có plugin tên {ten!r}.")
    return {"da_xoa": ten}


@router.get("/ky-nang/plugin/{ten}/lich-su")
async def lich_su_ky_nang_plugin(
    ten: str, _: dict = Depends(can_quyen("ky_nang.doc"))
) -> list[dict]:
    """Các bản cũ của một plugin rời, mới nhất trước. Không kèm nội dung."""
    return await kho_ky_nang.lich_su_plugin(ten)


@router.post("/ky-nang/plugin/{ten}/khoi-phuc/{id_ban}")
async def khoi_phuc_ky_nang_plugin(
    ten: str, id_ban: int, nguoi: dict = Depends(can_quyen("ky_nang.sua"))
) -> dict:
    """
    Đưa một bản cũ trở lại. Đi qua đúng `luu_plugin`, nên bản cũ vẫn phải
    qua bộ kiểm — một bản lưu trước ngày có luật mới có thể không còn hợp
    lệ, và cài đè nó lặng lẽ là mở lại lỗ hổng luật ấy sinh ra để bịt.
    """
    try:
        bm = await kho_ky_nang.khoi_phuc_plugin(
            ten, id_ban, boi=nguoi["ten_dang_nhap"])
    except kho_ky_nang.BanCuKhongCo as exc:
        raise HTTPException(404, f"Không có bản cũ #{id_ban} của {ten!r}.") from exc
    except LoiBanMoTa as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ten": bm.ten, "loai": bm.loai}


class ThuPluginBody(BaseModel):
    ban_mo_ta: dict
    args: dict = Field(default_factory=dict)


@router.post("/ky-nang/plugin/thu")
async def thu_ky_nang_plugin(
    body: ThuPluginBody, _: dict = Depends(can_quyen("ky_nang.sua"))
) -> dict:
    """
    Chạy thử một plugin CHƯA lưu, và không tốn một lượt gọi model nào.

    Cùng lý do với `POST /api/knowledge/probe`: người vận hành phải nhìn
    thấy plugin trả về cái gì TRƯỚC khi nó đi vào hội thoại thật. Không có
    nút này thì cách duy nhất để thử là bật lên rồi nhắn cho chính mình —
    và lúc đó nó đã sống trong mọi hội thoại đang mở.
    """
    try:
        bm = doc_ban_mo_ta(body.ban_mo_ta)
    except LoiBanMoTa as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ket_qua": await chay_plugin(bm, body.args)}


# ---------------------------------------------------------------
#  Ứng dụng nhúng (tích hợp)
# ---------------------------------------------------------------
#
# Chỉ quản trị viên, kể cả đường ĐỌC: danh sách này nói chính xác những
# dịch vụ nội bộ nào đang chạy và ở cổng nào. Với người muốn dò mạng trong,
# đó là bản đồ.

@router.get("/tich-hop/ung-dung")
async def liet_ke_ung_dung(_: dict = Depends(can_quyen("tich_hop.doc"))) -> dict:
    return await tich_hop_kho.liet_ke()


class UngDungBody(BaseModel):
    ten: str = Field(min_length=2, max_length=31)
    nhan: str = Field("", max_length=60)
    dia_chi: str = Field(min_length=8, max_length=200)


@router.post("/tich-hop/ung-dung")
async def luu_ung_dung(
    body: UngDungBody, nguoi: dict = Depends(can_quyen("tich_hop.sua"))
) -> dict:
    try:
        return await tich_hop_kho.luu(
            body.ten, body.nhan, body.dia_chi, boi=nguoi["ten_dang_nhap"]
        )
    except LoiUngDung as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/tich-hop/ung-dung/{ten}")
async def xoa_ung_dung(
    ten: str, nguoi: dict = Depends(can_quyen("tich_hop.sua"))
) -> dict:
    try:
        da_xoa = await tich_hop_kho.xoa(ten, boi=nguoi["ten_dang_nhap"])
    except LoiUngDung as exc:
        raise HTTPException(400, str(exc)) from exc
    if not da_xoa:
        raise HTTPException(404, f"Không có ứng dụng tên {ten!r}.")
    return {"da_xoa": ten}


@router.post("/tich-hop/ung-dung/thu")
async def thu_ung_dung(
    body: UngDungBody, _: dict = Depends(can_quyen("tich_hop.sua"))
) -> dict:
    """
    Thử một địa chỉ TRƯỚC khi lưu.

    Cùng lý do với `POST /api/knowledge/probe` và nút chạy thử của plugin:
    người vận hành phải thấy nó nối được hay không ngay tại form, chứ không
    phải lưu xong, mở tab, rồi nhìn một trang trắng và không biết vì sao.
    """
    try:
        dia_chi = tich_hop_kho.kiem_dia_chi(body.dia_chi)
    except LoiUngDung as exc:
        raise HTTPException(400, str(exc)) from exc

    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as c:
            r = await c.get(dia_chi + "/")
        return {"noi_duoc": True, "ma": r.status_code, "dia_chi": dia_chi}
    except httpx.HTTPError as exc:
        return {
            "noi_duoc": False,
            "dia_chi": dia_chi,
            "ly_do": f"{type(exc).__name__}: {exc}"[:200],
        }
