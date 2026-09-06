"""
Phòng thử agent — API cho dashboard, chỉ quản trị.

Mọi lượt chạy trong `thu_nghiem.bat_thu()`: công cụ ghi được mô phỏng,
chi phí vào sổ thử. Lượt lỗi không được nối vào lịch sử, để lượt sau
không mang một câu trả lời chưa từng có.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from agent.api.routes import bat_buoc_quan_tri
from agent.core import agent as brain
from agent.core import cham_mot_luot, cham_nhieu_luot, phong_thu_phien as pp, thu_nghiem

router = APIRouter(prefix="/api/phong-thu", tags=["phong-thu"])
GOC = Path(__file__).resolve().parents[2]
BO_VANG = GOC / "data" / "eval" / "golden.jsonl"
BO_VANG_MAU = GOC / "data" / "eval" / "golden.example.jsonl"

# Nhãn tiếng Việt cho mã lớp lưới — một chỗ, dashboard không tự dịch.
NHAN_LUOI = {
    "tran_hoi_thoai": "Trần chi phí hội thoại", "tran_ngay": "Trần chi phí ngày",
    "injection": "Quét prompt injection", "tin_cay_thap": "Độ tin cậy thấp",
    "bat_buoc_chuyen": "Câu hỏi bắt buộc chuyển người", "hua_khong_goi": "Hứa chuyển mà không gọi",
    "chan_doan_y_te": "Chẩn đoán y tế trong câu trả lời",
    "cong_cu_chuyen_nguoi": "Agent chủ động chuyển người", "cong_cu_yeu_cau": "Công cụ yêu cầu người",
    "het_vong": "Vượt số vòng gọi công cụ",
}


class HoiBody(BaseModel):
    cau_hoi: str = Field(min_length=1, max_length=2000)
    ky_vong: dict[str, Any] | None = None


def reply_thanh_dict(r: brain.Reply) -> dict:
    return {
        "tra_loi": r.text, "escalate": r.escalate, "escalate_reason": r.escalate_reason,
        "luoi_bat": r.luoi_bat, "nhan_luoi": NHAN_LUOI.get(r.luoi_bat or "", ""),
        "grounded": r.grounded, "confidence": r.confidence, "sources": r.sources,
        "cong_cu": r.cong_cu, "vong": r.vong, "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms, "model": r.model,
        "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
    }


def doc_goi_y(duong: Path) -> dict[str, list[dict]]:
    ra: dict[str, list[dict]] = {}
    if not duong.exists():
        return ra
    for dong in duong.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        c = json.loads(dong)
        ra.setdefault(str(c.get("nhom", "khac")), []).append({
            "id": c.get("id", ""), "hoi": c.get("hoi", ""),
            "ky_vong": {k: c.get(k) for k in
                        ("chuyen_nguoi", "phai_co", "phai_co_mot_trong", "khong_duoc_co")},
        })
    return ra


def _phien(pid: str) -> pp.Phien:
    p = pp.lay_phien(pid)
    if p is None:
        raise HTTPException(404, "Phiên thử không tồn tại hoặc đã hết hạn")
    return p


@router.post("/phien", status_code=201)
async def tao_phien(_: dict = Depends(bat_buoc_quan_tri)) -> dict:
    p = await pp.tao_phien()
    return {"id": p.id}


@router.get("/phien/{pid}")
async def xem_phien(pid: str, _: dict = Depends(bat_buoc_quan_tri)) -> dict:
    p = _phien(pid)
    return {"id": p.id, "so_luot": len(p.luot), "chi_phi": p.chi_phi, "luot": p.luot}


@router.delete("/phien/{pid}", status_code=204)
async def xoa_phien(pid: str, _: dict = Depends(bat_buoc_quan_tri)) -> Response:
    _phien(pid)
    pp.xoa_phien(pid)
    return Response(status_code=204)


@router.post("/phien/{pid}/hoi")
async def hoi(pid: str, body: HoiBody, _: dict = Depends(bat_buoc_quan_tri)) -> dict:
    p = _phien(pid)
    cau_hoi = body.cau_hoi.strip()
    if not cau_hoi:
        raise HTTPException(422, "Câu hỏi trống")
    if len(p.luot) >= pp.TOI_DA_LUOT:
        raise HTTPException(409, f"Phiên đã đủ {pp.TOI_DA_LUOT} lượt — tạo phiên mới")
    con, da_tieu, tran = thu_nghiem.con_tran()
    if not con:
        raise HTTPException(429, f"Hết trần chi phí thử hôm nay ({da_tieu:.2f}/{tran:.2f} USD). "
                                 "Nâng 'Trần chi phí phòng thử' trong Cấu hình nếu cần.")
    bat_dau = time.perf_counter()
    try:
        with thu_nghiem.bat_thu():
            reply = await brain.respond(
                conversation_id=p.conversation_id, history=list(p.history),
                question=cau_hoi, customer_ref="", channel="phong_thu",
            )
    except Exception as exc:  # noqa: BLE001 — lỗi model phải thành câu trả lời có mã, không phải 500
        raise HTTPException(502, f"{type(exc).__name__}: {str(exc)[:200]}".replace(
            *_che_khoa(str(exc)))) from exc
    if reply.luoi_bat in ("tran_ngay",):
        # Không phải câu trả lời của agent — là hệ thống hết tiền. Trả 429
        # để dashboard không hiện nó như một lượt bình thường.
        raise HTTPException(429, {"ly_do": reply.escalate_reason, "luoi_bat": reply.luoi_bat})
    d = reply_thanh_dict(reply)
    d["ms_tong"] = int((time.perf_counter() - bat_dau) * 1000)
    thu_nghiem.ghi_nhan(reply.cost_usd)
    pp.ghi_luot(p, cau_hoi, {"cost_usd": reply.cost_usd, "luoi_bat": reply.luoi_bat}, reply.text)
    cham: dict[str, Any] = {
        "tu_cam": cham_mot_luot.tu_cam(reply.text),
        "hinh_thuc": cham_nhieu_luot.cham(
            [{"khach": l["khach"], "agent": l["agent"]} for l in p.luot],
            da_chuyen_nguoi=reply.escalate,
        ),
    }
    if body.ky_vong:
        cham["so_voi_bo_vang"] = cham_mot_luot.so_voi_bo_vang(reply.text, reply.escalate, body.ky_vong)
    d["cham"] = cham
    d["phien"] = {"id": p.id, "so_luot": len(p.luot), "chi_phi": p.chi_phi}
    return d


def _che_khoa(thong_diep: str) -> tuple[str, str]:
    """
    Che chuỗi trông như khoá API trong thông điệp lỗi (AIza…, sk-ant-…).

    Nhà cung cấp hiếm khi echo khoá, nhưng phòng thử là màn hình người ta
    chụp gửi nhau — một lần lộ là đủ. Trả về (cái cần thay, cái thay vào)
    để dùng với str.replace; không thấy gì thì thay rỗng bằng rỗng.
    """
    import re

    m = re.search(r"(AIza[0-9A-Za-z_\-]{10,}|sk-ant-[0-9A-Za-z_\-]{10,})", thong_diep)
    return (m.group(1), "···") if m else ("", "")


@router.get("/goi-y")
async def goi_y(_: dict = Depends(bat_buoc_quan_tri)) -> dict:
    return doc_goi_y(BO_VANG if BO_VANG.exists() else BO_VANG_MAU)


@router.get("/ngan-sach")
async def ngan_sach(_: dict = Depends(bat_buoc_quan_tri)) -> dict:
    _, da_tieu, tran = thu_nghiem.con_tran()
    return {"da_tieu": da_tieu, "tran": tran}
