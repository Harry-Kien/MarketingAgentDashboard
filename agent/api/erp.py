"""
Vỏ REST của cổng kho/ERP. CHỈ ĐỌC.

VÌ SAO KHÔNG CÓ ENDPOINT NÀO GHI
--------------------------------
Cùng lý do đã ghi trong docstring của `agent/mcp_server.py`: thứ gọi vào đây
là một hệ khác. Nó không đi qua năm lớp lưới tuân thủ trong
`agent/core/agent.py`, không có trần chi phí, không có lưới an toàn chuyển
người. Cho nó quyền tạo đơn hay trừ kho là giao chìa khoá cho một người lạ.

Muốn lên đơn thì đi qua agent, hoặc qua dashboard nơi có người thật bấm nút.

VÌ SAO 503 CHỨ KHÔNG PHẢI 200 KÈM SỐ CŨ
---------------------------------------
Cổng trả `None` nghĩa là "chưa tra được". Dịch nó thành 200 kèm con số lần
trước là để client tin tưởng một con số đã chết — và client thì không có
cách nào biết. 503 nói đúng sự thật.

`/suc-khoe` là ngoại lệ có chủ ý: nó LUÔN trả 200, vì nó là bộ đo chứ không
phải bộ phục vụ dữ liệu. Trả 503 ở đó thì bộ giám sát bên ngoài không phân
biệt được "ERP chết" với "chính API này chết".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent.erp import nha_may
from agent.erp.hop_dong import LoiERP

from .routes import bat_buoc_dang_nhap

router = APIRouter(prefix="/api/erp", tags=["erp"])


@router.get("/san-pham")
async def danh_sach_san_pham(_nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    try:
        data = await nha_may.cong().danh_muc()
    except LoiERP as exc:
        raise HTTPException(503, f"Chưa lấy được danh mục: {exc}") from exc
    return {"san_pham": data.get("san_pham", [])}


@router.get("/san-pham/{ma}")
async def mot_san_pham(
    ma: str, _nguoi: dict = Depends(bat_buoc_dang_nhap)
) -> dict:
    try:
        data = await nha_may.cong().danh_muc()
    except LoiERP as exc:
        raise HTTPException(503, f"Chưa lấy được danh mục: {exc}") from exc
    for sp in data.get("san_pham", []):
        if sp.get("ma") == ma:
            return sp
    raise HTTPException(404, f"Không có sản phẩm {ma}")


@router.get("/ton-kho/{ma}")
async def ton_kho(ma: str, _nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    # `bo_qua_cache=True`: ai gọi thẳng endpoint này là đang cần con số ngay
    # lúc này — thường để quyết định có bán hay không.
    t = await nha_may.cong().ton_kho(ma, bo_qua_cache=True)
    if t is None:
        raise HTTPException(503, f"Chưa tra được tồn kho của {ma}")
    return {"ma": ma, "ban_duoc": t.ban_duoc, "ma_kho": t.ma_kho}


@router.get("/suc-khoe")
async def suc_khoe(_nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    cong = nha_may.cong()
    return {**cong.trang_thai(), "song": await cong.suc_khoe()}
