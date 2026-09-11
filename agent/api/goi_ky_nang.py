"""API gói kỹ năng — chỉ quản trị. Bản gói sai là 422 và không ghi gì."""
# ĐỌC: ══ TRẠM A2 · CỬA VÀO CỦA CHẶNG CÀI ═════════════════════════════════
# ĐỌC: Bản đồ đầy đủ ba chặng: agent/ky_nang/__init__.py
# ĐỌC:
# ĐỌC:   TRƯỚC  A1  dashboard/app.js — panel Gói kỹ năng
# ĐỌC:   SAU    A3  ky_nang/goi.py — tu_zip() rồi doc_goi()
# ĐỌC:
# ĐỌC: Tệp này KHÔNG kiểm nội dung gói. Nó chỉ làm ba việc mà tầng dưới
# ĐỌC: không làm được: chặn quyền, chặn kích thước tệp, và dịch lỗi của
# ĐỌC: `goi.py` sang mã HTTP. Mọi phép kiểm về gói nằm ở A3–A5.
# ĐỌC:
# ĐỌC: VÌ SAO CẢ ĐƯỜNG ĐỌC CŨNG CHỈ QUẢN TRỊ: `GET ""` trả về danh sách
# ĐỌC: chính xác những gì agent làm được và làm không được. Với người muốn
# ĐỌC: lách agent, đó là bản đồ — biết `tao_don_hang` đang tắt là biết
# ĐỌC: không cần thử con đường ấy nữa. Người trực ca không cần bản đồ đó.
# ĐỌC:
# ĐỌC: HAI ĐƯỜNG CÀI, MỘT BỘ KIỂM: `POST ""` nhận JSON, `POST "/tep"` nhận
# ĐỌC: tệp tải lên. Cả hai đổ về `_cai()` rồi `goi.cai()`, nên không có
# ĐỌC: đường nào lỏng hơn đường nào. Thêm đường thứ ba thì cũng phải đi
# ĐỌC: qua `_cai()`, đừng gọi thẳng `goi.cai()` từ handler mới.
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agent.api.routes import can_quyen
from agent.ky_nang import goi as g
from agent.ky_nang import nhap_skill_md
from agent.ky_nang import kho_ky_nang

router = APIRouter(prefix="/api/goi-ky-nang", tags=["goi-ky-nang"])


class BatTatBody(BaseModel):
    bat: bool


def _loi(exc: Exception) -> HTTPException:
    if isinstance(exc, g.LoiGoi):
        return HTTPException(422, str(exc))
    if isinstance(exc, g.KhoDay):
        return HTTPException(409, str(exc))
    if isinstance(exc, g.GoiKhongTonTai):
        return HTTPException(404, "Không tìm thấy gói kỹ năng")
    return HTTPException(502, f"{type(exc).__name__}: {str(exc)[:200]}")


@router.get("")
async def liet_ke(_: dict = Depends(can_quyen("ky_nang.doc"))) -> dict:
    # ĐẾM MỘT LẦN cho cả hai bảng. Trước đây `kho_ky_nang.liet_ke()` và
    # `g.liet_ke()` mỗi hàm tự gọi `dem_goi_7_ngay()` — hai lần quét 7 ngày
    # bảng `events` cho MỘT lần vẽ màn hình, mà màn hình này tự làm mới 6
    # giây một lần và `events` là bảng lớn nhất (mỗi lời gọi công cụ một dòng).
    dem = await g.dem_an_toan()
    kn = await kho_ky_nang.liet_ke(dem)
    return {
        "goi": await g.liet_ke(dem),
        "cong_cu": [{"ten": k["ten"], "so_lan": k.get("so_lan_7_ngay", 0), "so_loi": k.get("so_loi_7_ngay", 0)}
                    for k in [*kn["co_san"], *kn["plugin"]]],
        "goi_toi_da": g.GOI_TOI_DA,
    }


@router.post("/kiem")
async def kiem(body: dict, _: dict = Depends(can_quyen("ky_nang.sua"))) -> dict:
    try:
        x = g.doc_goi(body)
    except g.LoiGoi as exc:
        return {"hop_le": False, "loi": str(exc)}
    return {"hop_le": True, "tom_tat": {"ten": x.ten, "phien_ban": x.phien_ban, "so_cong_cu": len(x.cong_cu),
                                        "so_tai_lieu": len(x.tai_lieu), "tu_khoa": x.tu_khoa,
                                        "do_dai_huong_dan": len(x.huong_dan)}}


async def _cai(tho: dict, nguoi: dict) -> dict:
    try:
        x = await g.cai(tho, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001 — dịch sang mã HTTP, không 500
        raise _loi(exc) from exc
    return {"ten": x.ten, "phien_ban": x.phien_ban, "so_cong_cu": len(x.cong_cu), "so_tai_lieu": len(x.tai_lieu)}


@router.post("", status_code=201)
async def cai(body: dict, nguoi: dict = Depends(can_quyen("ky_nang.sua"))) -> dict:
    return await _cai(body, nguoi)


def _co_tep(du_lieu: bytes, ten: str) -> bool:
    """Zip có tệp tên này ở bất kỳ tầng nào? Zip hỏng thì trả False và để
    bộ đọc thật nêu lỗi — hai chỗ cùng báo một lỗi là hai thông điệp khác
    nhau cho cùng một sự việc."""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(du_lieu)) as z:
            return any(n.rsplit("/", 1)[-1] == ten for n in z.namelist())
    except zipfile.BadZipFile:
        return False


@router.post("/tep", status_code=201)
async def cai_tu_tep(tep: UploadFile = File(...), nguoi: dict = Depends(can_quyen("ky_nang.sua"))) -> dict:
    du_lieu = await tep.read()
    if len(du_lieu) > g.ZIP_TOI_DA:
        raise HTTPException(413, f"Tệp lớn hơn {g.ZIP_TOI_DA // 1024 // 1024} MB")
    ten = (tep.filename or "").lower()
    try:
        if ten.endswith(".zip"):
            # Hai định dạng zip, nhận cả hai: gói của repo (`goi.json`) và
            # chuẩn Agent Skills (`SKILL.md`). Nhìn vào NỘI DUNG chứ không
            # bắt người vận hành khai trước — họ tải một tệp về và không có
            # lý do gì phải biết nó viết theo chuẩn nào.
            tho = (g.tu_zip(du_lieu) if _co_tep(du_lieu, "goi.json")
                   else nhap_skill_md.tu_skill_md(du_lieu))
        else:
            tho = json.loads(du_lieu.decode("utf-8"))
    except nhap_skill_md.LoiSkillMd as exc:
        raise HTTPException(422, str(exc)) from exc
    except g.LoiGoi as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, f"Tệp không phải JSON hợp lệ: {exc}") from exc
    return await _cai(tho, nguoi)


@router.post("/{ten}/bat-tat", status_code=204)
async def bat_tat(ten: str, body: BatTatBody, nguoi: dict = Depends(can_quyen("ky_nang.sua"))) -> Response:
    try:
        await g.bat_tat(ten, body.bat, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return Response(status_code=204)


@router.delete("/{ten}", status_code=204)
async def xoa(ten: str, nguoi: dict = Depends(can_quyen("ky_nang.sua"))) -> Response:
    try:
        await g.xoa(ten, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return Response(status_code=204)


@router.get("/{ten}/xuat")
async def xuat(ten: str, _: dict = Depends(can_quyen("ky_nang.doc"))) -> Any:
    d = await g.xuat(ten)
    if d is None:
        raise HTTPException(404, "Không tìm thấy gói kỹ năng")
    return JSONResponse(d, headers={"Content-Disposition": f'attachment; filename="{ten}.json"'})


@router.get("/{ten}/lich-su")
async def lich_su(ten: str, _: dict = Depends(can_quyen("ky_nang.doc"))) -> list[dict]:
    return await g.lich_su(ten)


@router.post("/{ten}/khoi-phuc/{id_lich_su}")
async def khoi_phuc(ten: str, id_lich_su: int, nguoi: dict = Depends(can_quyen("ky_nang.sua"))) -> dict:
    try:
        x = await g.khoi_phuc(ten, id_lich_su, boi=nguoi["ten_dang_nhap"])
    except Exception as exc:  # noqa: BLE001
        raise _loi(exc) from exc
    return {"ten": x.ten, "phien_ban": x.phien_ban}
