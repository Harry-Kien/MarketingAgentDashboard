"""API máy chủ MCP — chỉ quản trị. Bí mật không bao giờ ra khỏi đường GET."""
# ĐỌC: Bản đồ đầy đủ: agent/ky_nang/kho_mcp.py (mục đầu tệp), spec §5.4.
# ĐỌC:
# ĐỌC: Tệp này KHÔNG tự kiểm địa chỉ, tên, header hay trần số lượng — mọi
# ĐỌC: luật ấy sống ở `kho_mcp.py`, nơi giữ CẢ bí mật lẫn nhật ký. Việc của
# ĐỌC: tệp này chỉ là ba thứ tầng dưới không làm: chặn quyền, đọc/gói JSON
# ĐỌC: của HTTP, và dịch lỗi của `kho_mcp` sang mã trạng thái — y hệt vai
# ĐỌC: trò `goi_ky_nang.py` với `ky_nang/goi.py`.
# ĐỌC:
# ĐỌC: KHÔNG `import agent.ky_nang.mcp_khach` ở đây — bài kiểm AST trong
# ĐỌC: `tests/test_ky_nang_plugin.py` chặn mọi nơi khác ngoài `kho_mcp.py`.
# ĐỌC: `LoiMCP` và `MCP_MAY_CHU_TOI_DA` lấy qua `kho_mcp` (tệp đó xuất lại
# ĐỌC: hai tên này đúng cho mục đích này).
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from agent.api.routes import bat_buoc_quan_tri
from agent.cau_hinh_dong import VaultChuaSanSang
from agent.ky_nang import kho_ky_nang
from agent.ky_nang import kho_mcp

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


class KiemBody(BaseModel):
    dia_chi: str
    headers: dict[str, str] | None = None


class ThemBody(BaseModel):
    ten: str
    nhan: str
    dia_chi: str
    headers: dict[str, str] | None = None


class BatTatBody(BaseModel):
    bat: bool


class CongCuBody(BaseModel):
    bat: bool | None = None
    ghi: bool | None = None
    ghi_cho_phep: bool | None = None


def _loi(exc: Exception) -> HTTPException:
    # Thứ tự không quan trọng ở đây: bốn nhóm lỗi của `kho_mcp` không lồng
    # nhau (không lớp nào kế thừa lớp kia), nên không có ca nào rơi nhầm
    # nhánh vì đứng sau.
    if isinstance(exc, (kho_mcp.LoiMCP, kho_mcp.LoiBanMoTa, kho_mcp.LoiMayChu, ValueError)):
        return HTTPException(422, str(exc))
    if isinstance(exc, kho_mcp.KhoDay):
        return HTTPException(409, str(exc))
    if isinstance(exc, kho_mcp.MayChuKhongTonTai):
        return HTTPException(404, str(exc))
    if isinstance(exc, VaultChuaSanSang):
        return HTTPException(503, str(exc))
    return HTTPException(502, f"{type(exc).__name__}: {str(exc)[:200]}")


@router.get("")
async def liet_ke(_: dict = Depends(bat_buoc_quan_tri)) -> dict:
    return {
        "may_chu": await kho_mcp.liet_ke(),
        "may_chu_toi_da": kho_mcp.MCP_MAY_CHU_TOI_DA,
        "plugin_toi_da": kho_ky_nang.PLUGIN_TOI_DA,
    }


@router.post("/kiem")
async def kiem(body: KiemBody, _: dict = Depends(bat_buoc_quan_tri)) -> dict:
    # KHÔNG ghi gì: `kiem_ket_noi` không đụng CSDL, chỉ nối thử và liệt kê —
    # đúng lý do nút "Kiểm" tồn tại (xem chú thích ở kho_mcp.kiem_ket_noi).
    try:
        return await kho_mcp.kiem_ket_noi(body.dia_chi, body.headers)
    except Exception as exc:  # noqa: BLE001 — dịch sang mã HTTP, không 500
        raise _loi(exc) from exc


@router.post("", status_code=201)
async def them(body: ThemBody, nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
    try:
        kq = await kho_mcp.them(body.ten, body.nhan, body.dia_chi, body.headers,
                                 boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    # `kho_mcp.them()` trả kết quả ĐỒNG BỘ (không có khoá "ten" — nó không
    # biết tên máy chủ, chỉ biết công cụ của nó); "ten" ở đây lấy từ đúng
    # tên đã gửi lên, vì tên hợp lệ đã ở đúng dạng chuẩn hoá (chữ thường).
    return {"ten": body.ten, "so_cong_cu": kq["so_cong_cu"], "so_bat": kq["so_bat"],
            "so_bo": kq["so_bo"], "bo": kq["bo"]}


@router.post("/{ten}/dong-bo")
async def dong_bo(ten: str, nguoi: dict = Depends(bat_buoc_quan_tri)) -> dict:
    try:
        return await kho_mcp.dong_bo(ten, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc


@router.post("/{ten}/bat-tat", status_code=204)
async def bat_tat(ten: str, body: BatTatBody, nguoi: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await kho_mcp.bat_tat(ten, body.bat, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return Response(status_code=204)


@router.post("/{ten}/cong-cu/{ten_cong_cu}", status_code=204)
async def dat_cong_cu(
    ten: str, ten_cong_cu: str, body: CongCuBody, nguoi: dict = Depends(bat_buoc_quan_tri)
) -> Response:
    try:
        await kho_mcp.dat_cong_cu(
            ten, ten_cong_cu, bat=body.bat, ghi=body.ghi, ghi_cho_phep=body.ghi_cho_phep,
            boi=nguoi["ten_dang_nhap"],
        )
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return Response(status_code=204)


@router.delete("/{ten}", status_code=204)
async def xoa(ten: str, nguoi: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await kho_mcp.xoa(ten, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return Response(status_code=204)
