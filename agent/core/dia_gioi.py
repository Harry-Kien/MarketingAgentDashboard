"""
Danh mục đơn vị hành chính Việt Nam sau sáp nhập 01/07/2025 (34 tỉnh/thành,
hai cấp tỉnh — phường/xã/đặc khu). Dữ liệu: `agent/du_lieu/dia_gioi_vn.json`
(MIT, ThangLeQuoc/vietnamese-provinces-database; sinh bằng scripts.nap_dia_gioi).

CHỈ CHẶN KHI CHẮC CHẮN SAI
--------------------------
Khách vẫn ghi địa chỉ CŨ ba cấp ("Phường 1, Quận 3, TP HCM") — hãng vận
chuyển còn nhận, và danh mục mới không có tên cũ. Nên `mau_thuan()` chỉ lên
tiếng khi đủ cả ba điều:

  · địa chỉ kiểu MỚI — không có phần nào là quận/huyện/thị xã;
  · phần cuối là một tỉnh/thành MỚI, nhận ra không mơ hồ;
  · có phần mang tiền tố phường/xã/đặc khu, tên ấy CÓ trong danh mục cả nước,
    nhưng KHÔNG thuộc tỉnh đó.

Tên phường đánh số ("Phường 1") bỏ qua: số trùng nhau giữa các tỉnh, và địa
chỉ cũ dùng số rất nhiều. Chặn nhầm một khách thật đang đặt hàng tệ hơn để
hãng vận chuyển hỏi lại.
"""
from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path

TEP = Path(__file__).resolve().parent.parent / "du_lieu" / "dia_gioi_vn.json"

_TIEN_TO_TINH = ("thanh pho", "tinh", "tp")
_TIEN_TO_PHUONG = ("phuong", "xa", "dac khu", "p", "x")
# Chỉ tiền tố VIẾT ĐỦ mới đủ chắc để CHẶN: ở Hà Nội "P." là PHỐ ("P. Quang
# Trung, Hà Đông"), và "X." hiếm khi là xã (rà soát 28.10.2026).
_TIEN_TO_PHUONG_CHAC = ("phuong", "xa", "dac khu")
# Phần không phải phần cuối mà mang các tiền tố này là cấp HUYỆN cũ — kể cả
# thành phố/thị xã thuộc tỉnh ("Phường Tân Lập, Thành phố Nha Trang, Khánh Hòa").
_TIEN_TO_QUAN = ("quan", "huyen", "thi xa", "thanh pho", "thi tran", "tp", "q", "h", "tx")
# Cách gọi thường gặp → tên chuẩn đã bỏ tiền tố, bỏ dấu.
_BIET_DANH = {
    "hcm": "ho chi minh", "tphcm": "ho chi minh", "sai gon": "ho chi minh", "sg": "ho chi minh",
    "hn": "ha noi", "dn": "da nang", "hp": "hai phong", "ct": "can tho",
}


def chuan(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    s = "".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def _bo_tien_to(ten: str, tien_to: tuple[str, ...]) -> str:
    t = chuan(ten)
    for tt in sorted(tien_to, key=len, reverse=True):
        if t == tt:
            return ""
        if t.startswith(tt + " "):
            return t[len(tt) + 1:]
        # "Q.1", "P.Bến Thành" sau chuẩn hoá thành "q 1", "p ben thanh" — đã
        # khớp nhánh trên. "TP.HCM" thành "tp hcm" — cũng vậy.
    return t


def _co_tien_to(ten: str, tien_to: tuple[str, ...]) -> bool:
    t = chuan(ten)
    return any(t == tt or t.startswith(tt + " ") for tt in tien_to)


@lru_cache(maxsize=1)
def _du_lieu() -> dict:
    d = json.loads(TEP.read_text(encoding="utf-8"))
    tinh: dict[str, dict] = {}
    phuong_ca_nuoc: dict[str, set[str]] = {}
    for t in d["tinh"]:
        ten = _bo_tien_to(t["ten"], _TIEN_TO_TINH)
        phuong = {_bo_tien_to(p[1], _TIEN_TO_PHUONG) for p in t["phuong"]}
        tinh[ten] = {"ma": t["ma"], "ten": t["ten"], "phuong": phuong}
        for p in phuong:
            phuong_ca_nuoc.setdefault(p, set()).add(ten)
    return {"phien_ban": d["phien_ban"], "tinh": tinh, "phuong": phuong_ca_nuoc}


def phien_ban() -> str:
    return str(_du_lieu()["phien_ban"])


def tim_tinh(chu: str) -> dict | None:
    """Tỉnh/thành MỚI theo tên khách gõ, hoặc None nếu không nhận ra."""
    t = _bo_tien_to(chu, _TIEN_TO_TINH)
    t = _BIET_DANH.get(t.replace(" ", ""), _BIET_DANH.get(t, t))
    return _du_lieu()["tinh"].get(t)


def thuoc_tinh(ten_phuong: str, tinh: dict) -> bool:
    return _bo_tien_to(ten_phuong, _TIEN_TO_PHUONG) in tinh["phuong"]


def mau_thuan(dia_chi: str) -> str | None:
    """
    Câu giải thích nếu địa chỉ CHẮC CHẮN sai (phường mới không thuộc tỉnh mới
    ghi kèm); None nếu không chắc — kể cả khi chỉ là không nhận ra.
    """
    phan = [p.strip() for p in str(dia_chi or "").split(",") if p.strip()]
    if len(phan) < 2:
        return None
    if any(_co_tien_to(p, _TIEN_TO_QUAN) for p in phan[:-1]):
        return None                                   # địa chỉ cũ ba cấp
    tinh = tim_tinh(phan[-1])
    if tinh is None:
        return None
    # Địa chỉ MỚI hai cấp là "…, Phường X, Tỉnh Y": chỉ phần NGAY TRƯỚC tỉnh
    # mới là phường. Xét mọi phần là bắt cả "Phường Quang Trung" nằm trước
    # một tên huyện cũ không tiền tố ("…, Hà Đông, Hà Nội") — chặn nhầm khách.
    p = phan[-2]
    if not _co_tien_to(p, _TIEN_TO_PHUONG_CHAC):
        return None
    ten = _bo_tien_to(p, _TIEN_TO_PHUONG)
    if not ten or ten.isdigit():
        return None
    ca_nuoc = _du_lieu()["phuong"].get(ten)
    if ca_nuoc and not thuoc_tinh(p, tinh):
        noi = ", ".join(sorted(_du_lieu()["tinh"][x]["ten"] for x in ca_nuoc))
        return (f"«{p}» không thuộc {tinh['ten']} theo danh mục hành chính sau sáp nhập "
                f"(có ở: {noi}). Hỏi lại khách phường/xã và tỉnh/thành cho đúng.")
    return None
