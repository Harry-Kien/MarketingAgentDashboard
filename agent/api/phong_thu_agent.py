"""
Phòng thử agent — API cho dashboard, chỉ quản trị.

Mọi lượt chạy trong `thu_nghiem.bat_thu()`: công cụ ghi được mô phỏng,
chi phí vào sổ thử. Lượt lỗi không được nối vào lịch sử, để lượt sau
không mang một câu trả lời chưa từng có.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from agent.api.routes import can_quyen
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


class KyVong(BaseModel):
    """
    Hình dạng kỳ vọng cố định — validate TRƯỚC khi chạm ghi_nhan/ghi_luot.

    Trước đây `ky_vong: dict` chấp nhận bất cứ gì, nên một giá trị sai kiểu
    (vd. `phai_co: 123`) chỉ nổ bên trong `so_voi_bo_vang` — SAU KHI lượt đã
    tốn tiền thật và đã ghi vào lịch sử phiên. Model này để FastAPI trả 422
    trước khi hàm `hoi()` chạy dòng nào.
    """

    chuyen_nguoi: bool = False
    phai_co: list[str] = Field(default_factory=list)
    phai_co_mot_trong: list[str] = Field(default_factory=list)
    khong_duoc_co: list[str] = Field(default_factory=list)


class HoiBody(BaseModel):
    cau_hoi: str = Field(min_length=1, max_length=2000)
    ky_vong: KyVong | None = None


def reply_thanh_dict(r: brain.Reply) -> dict:
    return {
        "tra_loi": r.text, "escalate": r.escalate, "escalate_reason": r.escalate_reason,
        "luoi_bat": r.luoi_bat, "nhan_luoi": NHAN_LUOI.get(r.luoi_bat or "", ""),
        "grounded": r.grounded, "confidence": r.confidence, "sources": r.sources,
        "cong_cu": r.cong_cu, "vong": r.vong, "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms, "model": r.model,
        "tokens_in": r.tokens_in, "tokens_out": r.tokens_out,
        "goi_ky_nang": r.goi_ky_nang,
    }


def doc_goi_y(duong: Path) -> dict[str, list[dict]]:
    ra: dict[str, list[dict]] = {}
    if not duong.exists():
        return ra
    for dong in duong.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        try:
            c = json.loads(dong)
        except ValueError:
            # Một dòng gõ tay hỏng không được kéo sập cả bảng gợi ý —
            # bỏ qua dòng đó, các dòng còn lại vẫn hiện lên dashboard.
            continue
        # Chuẩn hoá kiểu NGAY Ở ĐÂY, không để `None` lọt xuống dashboard.
        # Dòng bộ vàng thiếu một khoá là chuyện thường (viết tay), và một
        # `null` trong `ky_vong` sẽ thành `phai_co: null` gửi lên
        # `POST /hoi` — bị `KyVong` trả 422, người dùng chỉ thấy câu gợi ý
        # bấm vào là hỏng mà không biết vì sao.
        ra.setdefault(str(c.get("nhom", "khac")), []).append({
            "id": c.get("id", ""), "hoi": c.get("hoi", ""),
            "ky_vong": {
                "chuyen_nguoi": bool(c.get("chuyen_nguoi")),
                "phai_co": c.get("phai_co") or [],
                "phai_co_mot_trong": c.get("phai_co_mot_trong") or [],
                "khong_duoc_co": c.get("khong_duoc_co") or [],
            },
        })
    return ra


def _phien(pid: str) -> pp.Phien:
    p = pp.lay_phien(pid)
    if p is None:
        raise HTTPException(404, "Phiên thử không tồn tại hoặc đã hết hạn")
    return p


@router.post("/phien", status_code=201)
async def tao_phien(_: dict = Depends(can_quyen("phong_thu.dung"))) -> dict:
    p = await pp.tao_phien()
    return {"id": p.id}


@router.get("/phien/{pid}")
async def xem_phien(pid: str, _: dict = Depends(can_quyen("phong_thu.dung"))) -> dict:
    p = _phien(pid)
    return {"id": p.id, "so_luot": len(p.luot), "chi_phi": p.chi_phi, "luot": p.luot}


@router.delete("/phien/{pid}", status_code=204)
async def xoa_phien(pid: str, _: dict = Depends(can_quyen("phong_thu.dung"))) -> Response:
    _phien(pid)
    pp.xoa_phien(pid)
    return Response(status_code=204)


@router.post("/phien/{pid}/hoi")
async def hoi(pid: str, body: HoiBody, _: dict = Depends(can_quyen("phong_thu.dung"))) -> dict:
    p = _phien(pid)
    cau_hoi = body.cau_hoi.strip()
    if not cau_hoi:
        raise HTTPException(422, "Câu hỏi trống")
    if len(p.luot) >= pp.TOI_DA_LUOT:
        raise HTTPException(409, f"Phiên đã đủ {pp.TOI_DA_LUOT} lượt — tạo phiên mới")
    con, da_tieu, tran = thu_nghiem.con_tran()
    if not con:
        # Cấu trúc hoá thay vì chuỗi — dashboard cần đọc `tran`/`da_tieu` để vẽ
        # thanh ngân sách, không phải chỉ hiện lại câu chữ.
        raise HTTPException(429, {
            "ly_do": f"Hết trần chi phí thử hôm nay ({da_tieu:.2f}/{tran:.2f} USD). "
                     "Nâng 'Trần chi phí phòng thử' trong Cấu hình nếu cần.",
            "da_tieu": da_tieu, "tran": tran,
        })
    bat_dau = time.perf_counter()
    try:
        with thu_nghiem.bat_thu():
            reply = await brain.respond(
                conversation_id=p.conversation_id, history=list(p.history),
                question=cau_hoi, customer_ref="", channel="phong_thu",
            )
    except Exception as exc:  # noqa: BLE001 — lỗi model phải thành câu trả lời có mã, không phải 500
        # Che khoá TRƯỚC khi cắt: khoá dài ~39 ký tự có thể nằm vắt ngang mốc
        # 200 — cắt trước rồi che thì phần khoá sau mốc cắt lọt qua nguyên vẹn.
        thong_diep = _che(str(exc))
        raise HTTPException(502, f"{type(exc).__name__}: {thong_diep[:200]}") from exc
    if reply.luoi_bat in ("tran_ngay",):
        # Không phải câu trả lời của agent — là hệ thống hết tiền. Trả 429
        # để dashboard không hiện nó như một lượt bình thường.
        raise HTTPException(429, {"ly_do": reply.escalate_reason, "luoi_bat": reply.luoi_bat})
    d = reply_thanh_dict(reply)
    d["ms_tong"] = int((time.perf_counter() - bat_dau) * 1000)
    # KHÔNG gọi `thu_nghiem.ghi_nhan()` ở đây: `respond()` là nơi duy nhất
    # thấy tổng chi phí thật, kể cả khi API bỏ giữa chừng (ném 429/502 sau
    # khi model đã tiêu tiền). Ghi hai lần là sổ gấp đôi thực tế, và một sổ
    # sai gấp đôi thì trần chi phí chặn sớm gấp đôi — không ai biết vì sao.
    pp.ghi_luot(p, cau_hoi, {"cost_usd": reply.cost_usd, "luoi_bat": reply.luoi_bat}, reply.text)
    cham: dict[str, Any] = {
        "tu_cam": cham_mot_luot.tu_cam(reply.text),
        "hinh_thuc": cham_nhieu_luot.cham(
            [{"khach": l["khach"], "agent": l["agent"]} for l in p.luot],
            da_chuyen_nguoi=reply.escalate,
        ),
    }
    if body.ky_vong:
        cham["so_voi_bo_vang"] = cham_mot_luot.so_voi_bo_vang(
            reply.text, reply.escalate, body.ky_vong.model_dump())
    d["cham"] = cham
    d["phien"] = {"id": p.id, "so_luot": len(p.luot), "chi_phi": p.chi_phi}
    return d


_RE_KHOA = re.compile(r"AIza[0-9A-Za-z_\-]{10,}|sk-ant-[0-9A-Za-z_\-]{10,}")


def _che(thong_diep: str) -> str:
    """
    Che MỌI chuỗi trông như khoá API trong thông điệp lỗi (AIza…, sk-ant-…).

    Nhà cung cấp hiếm khi echo khoá, nhưng phòng thử là màn hình người ta
    chụp gửi nhau — một lần lộ là đủ. Dùng `re.sub` (không phải `re.search`
    + `str.replace` một lần) vì thông điệp có thể chứa nhiều khoá, hoặc
    cùng một khoá lặp lại nhiều lần trong traceback.
    """
    return _RE_KHOA.sub("···", thong_diep)


@router.get("/goi-y")
async def goi_y(_: dict = Depends(can_quyen("phong_thu.dung"))) -> dict:
    return doc_goi_y(BO_VANG if BO_VANG.exists() else BO_VANG_MAU)


@router.get("/ngan-sach")
async def ngan_sach(_: dict = Depends(can_quyen("phong_thu.dung"))) -> dict:
    _, da_tieu, tran = thu_nghiem.con_tran()
    return {"da_tieu": da_tieu, "tran": tran}
