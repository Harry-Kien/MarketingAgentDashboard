"""
API cho mục Cài đặt API trên dashboard.

BA LUẬT
-------
1. Không có đường nào trả giá trị bí mật ra ngoài. `GET` chỉ trả bốn ký tự
   cuối; test đặt một khoá rồi tìm chuỗi ấy trong toàn bộ phản hồi.
2. `kiem-tra` chạy bằng giá trị NGƯỜI VỪA GÕ, gộp đè lên giá trị hiện hành,
   và KHÔNG lưu gì. Người dùng phải thấy khoá sống hay chết trước khi bấm Lưu.
3. Chỉ quản trị viên ghi; nhân viên xem được trạng thái để biết vì sao agent
   im lặng.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from agent import cau_hinh_dong
from agent.config import settings
from agent.core import llm
from agent.erp.erpnext import NguonErpNext
from agent.shipping import ghn

from .routes import bat_buoc_dang_nhap, bat_buoc_quan_tri

router = APIRouter(prefix="/api/cai-dat-api", tags=["cai-dat-api"])

NHOM_HOP_LE = ("model", "erp", "van_chuyen")


class GiaTriIn(BaseModel):
    gia_tri: str = Field(min_length=1, max_length=4000)


class KiemTraIn(BaseModel):
    nhom: str
    gia_tri: dict[str, str] = Field(default_factory=dict)


def _actor(user: dict) -> str:
    return str(user.get("ten_dang_nhap") or user.get("id") or "quan_tri")


def _hien_hanh(khoa: str, ghi_de: dict[str, str]) -> str:
    v = str(ghi_de.get(khoa) or "").strip()
    return v or cau_hinh_dong.lay(khoa)


async def kiem_nhom(nhom: str, ghi_de: dict[str, str]) -> dict[str, Any]:
    """Kiểm một nhóm bằng giá trị gửi lên đè lên hiện hành. Không lưu."""
    if nhom == "model":
        p = _hien_hanh("LLM_PROVIDER", ghi_de) or "gemini"
        khoa = _hien_hanh("GEMINI_API_KEY" if p == "gemini_api" else "ANTHROPIC_API_KEY", ghi_de)
        ok, chi_tiet, ms = await llm.kiem_khoa(
            provider_name=p,
            api_key=khoa if p in ("gemini_api", "anthropic") else "",
            model=_hien_hanh("MODEL_CHEAP", ghi_de) or settings.model_cheap,
        )
        return {"ok": ok, "chi_tiet": chi_tiet, "ms": ms}
    if nhom == "erp":
        try:
            nguon = NguonErpNext(
                goc=_hien_hanh("ERPNEXT_URL", ghi_de),
                api_key=_hien_hanh("ERPNEXT_API_KEY", ghi_de),
                api_secret=_hien_hanh("ERPNEXT_API_SECRET", ghi_de),
            )
            song = await nguon.suc_khoe()
        except ValueError as exc:
            # Adapter tự kiểm cấu hình lúc dựng và nói rõ thiếu gì.
            return {"ok": False, "chi_tiet": str(exc)[:200], "ms": 0}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "chi_tiet": f"{type(exc).__name__}: {exc}"[:200], "ms": 0}
        return {"ok": bool(song), "chi_tiet": "ERPNext xác thực được" if song else "ERPNext từ chối xác thực", "ms": 0}
    if nhom == "van_chuyen":
        ok, chi_tiet, ms = await ghn.kiem_ket_noi(
            token=_hien_hanh("GHN_TOKEN", ghi_de),
            shop_id=_hien_hanh("GHN_SHOP_ID", ghi_de),
        )
        return {"ok": ok, "chi_tiet": chi_tiet, "ms": ms}
    raise HTTPException(422, f"nhóm không hợp lệ: {nhom!r}")


@router.get("")
async def liet_ke(_: dict = Depends(bat_buoc_dang_nhap)) -> dict[str, Any]:
    return {"muc": cau_hinh_dong.liet_ke(), "vault_san_sang": cau_hinh_dong.vault_san_sang()}


@router.put("/{khoa}", status_code=status.HTTP_204_NO_CONTENT)
async def dat(khoa: str, body: GiaTriIn, user: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await cau_hinh_dong.dat(khoa, body.gia_tri, sua_boi=_actor(user))
    except cau_hinh_dong.KhoaKhongHopLe as exc:
        raise HTTPException(422, str(exc)) from exc
    except cau_hinh_dong.VaultChuaSanSang as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{khoa}", status_code=status.HTTP_204_NO_CONTENT)
async def xoa(khoa: str, user: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await cau_hinh_dong.xoa(khoa, sua_boi=_actor(user))
    except cau_hinh_dong.KhoaKhongHopLe as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/kiem-tra")
async def kiem_tra(body: KiemTraIn, _: dict = Depends(bat_buoc_quan_tri)) -> dict[str, Any]:
    if body.nhom not in NHOM_HOP_LE:
        raise HTTPException(422, f"nhóm không hợp lệ: {body.nhom!r}")
    ket = await kiem_nhom(body.nhom, body.gia_tri)
    # Chỉ ghi kết quả khi kiểm cấu hình ĐÃ LƯU: ghi "đạt" cho một khoá đang
    # lưu trong khi thứ vừa đạt là khoá chưa lưu là nói dối trên dashboard.
    if not body.gia_tri:
        for mo_ta in cau_hinh_dong.DANH_MUC.values():
            if mo_ta.nhom == body.nhom and mo_ta.bi_mat:
                await cau_hinh_dong.ghi_ket_qua_kiem(mo_ta.khoa, ket["ok"], ket["chi_tiet"])
    return ket
