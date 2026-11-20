"""
Dấu vết AI của MỘT tin nhắn — trả lời được câu "vì sao AI nói câu này?".

Ghi vào `messages.dau_vet_ai` (migration 0053) ở cả hai đường: tin AI tự
gửi và bản nháp chờ duyệt. Dashboard vẽ nó thành nút "Vì sao?" dưới tin.

VÌ SAO CẦN
----------
Phòng thử có dấu vết đầy đủ, khách thật thì không. Khi khách khiếu nại "AI
bảo tôi dùng được khi mang thai", câu hỏi đầu tiên là: hồ sơ agent nào,
ngưỡng bao nhiêu, đã tra tài liệu phiên bản nào, lưới nào im lặng. Trước bản
này không câu nào trả lời được từ dữ liệu — chỉ đoán.

HAI RÀNG BUỘC, CẢ HAI CANH BẰNG TEST
-----------------------------------
1. KHÔNG thêm dữ liệu cá nhân thô. Tham số công cụ trong `Reply.cong_cu` là
   bản đã MỞ che (số điện thoại thật để lên đơn), không phải bản model thấy.
   Ở đây che LẠI bằng một `MatNa` mới — luôn che, bất kể công tắc
   `CHE_DU_LIEU_GUI_MODEL` — rồi ẩn hẳn các trường mang danh tính theo tên
   khoá (họ tên, địa chỉ: `MatNa` cố ý không che địa chỉ vì không có khuôn).
   Dấu vết sống lâu và được đọc bởi nhiều người hơn câu trả lời; nó không
   được là một bản sao thứ hai của hồ sơ khách.
2. KÍCH THƯỚC CÓ TRẦN. `tim_kien_thuc` trả tám đoạn tài liệu, `goi_y_san_pham`
   trả cả danh mục; ghi nguyên vào mỗi tin là mỗi tin vài chục KB nhân với
   mọi tin AI từng gửi. Trần nằm ở `TRAN_BYTE`, và vượt trần thì bỏ dần phần
   ít quan trọng nhất (kết quả công cụ, rồi tham số) chứ không cắt JSON giữa
   chừng — dấu vết hỏng cú pháp là dấu vết không đọc được.
"""
from __future__ import annotations

import json
from typing import Any

from agent.core import che_du_lieu

PHIEN_BAN = 1
TRAN_BYTE = 12_000
_TOI_DA_CONG_CU = 8
_TOI_DA_TRI_THUC = 10
_CAT_CHUOI = 300

# Trường mang DANH TÍNH, ẩn theo tên khoá. Danh sách đóng, không đoán: thêm
# khoá mơ hồ ("ten") là ẩn luôn tên sản phẩm — dấu vết mất đúng thứ cần đọc.
_KHOA_DANH_TINH = frozenset({
    "khach_ten", "khach_sdt", "khach_dia_chi", "khach_email",
    "ten_khach", "ho_ten", "dia_chi", "sdt", "so_dien_thoai", "email",
    "cccd", "nguoi_nhan", "ten_nguoi_nhan",
})
AN = "[đã ẩn]"


def _cat(x: Any, mat_na: che_du_lieu.MatNa) -> Any:
    """Che + ẩn danh tính + cắt ngắn, đệ quy. Nói RÕ chỗ đã cắt."""
    if isinstance(x, str):
        s = mat_na.che(x)
        return s if len(s) <= _CAT_CHUOI else s[:_CAT_CHUOI] + "…"
    if isinstance(x, dict):
        return {str(k): (AN if str(k).lower() in _KHOA_DANH_TINH and v not in (None, "")
                         else _cat(v, mat_na))
                for k, v in list(x.items())[:30]}
    if isinstance(x, (list, tuple)):
        ra = [_cat(v, mat_na) for v in list(x)[:10]]
        if len(x) > 10:
            ra.append(f"… ({len(x) - 10} mục nữa)")
        return ra
    if isinstance(x, (int, float, bool)) or x is None:
        return x
    return _cat(str(x), mat_na)


def _nhan_luoi(ma: str | None) -> tuple[str, bool]:
    """(nhãn cho người đọc, có phải LỚP LƯỚI không). Import muộn: tránh vòng."""
    if not ma:
        return "", False
    from agent.core.agent import LOP_LUOI, MA_CHUYEN_KHAC

    if ma in LOP_LUOI:
        return LOP_LUOI[ma], True
    return MA_CHUYEN_KHAC.get(ma, ma), False


def dung(reply: Any, *, ho_so: Any, che_do_chung: str, duyet_rieng: bool,
         tu_gui: bool) -> dict[str, Any]:
    """
    Dựng dấu vết từ `Reply` + những gì chỉ tầng kênh biết (hồ sơ, chế độ).

    Hàm THUẦN: không CSDL, không mạng — kiểm được bằng một Reply dựng tay.
    """
    mat_na = che_du_lieu.MatNa()
    nhan, la_luoi = _nhan_luoi(getattr(reply, "luoi_bat", None))
    cong_cu = list(getattr(reply, "cong_cu", None) or [])
    tri_thuc = list(getattr(reply, "tri_thuc", None) or [])
    dv: dict[str, Any] = {
        "phien_ban": PHIEN_BAN,
        "ho_so": {"id": getattr(ho_so, "id", None),
                  "ten": getattr(ho_so, "ten", "") or "Mặc định"},
        "che_do": {"chung": che_do_chung, "duyet_rieng": bool(duyet_rieng),
                   "tu_gui": bool(tu_gui)},
        "tin_cay": {"diem": float(getattr(reply, "confidence", 0.0) or 0.0),
                    "nguong": float(getattr(ho_so, "nguong_tu_tin", 0.0) or 0.0),
                    "co_can_cu": bool(getattr(reply, "grounded", False))},
        "luoi": ({"ma": reply.luoi_bat, "nhan": nhan, "la_luoi": la_luoi}
                 if getattr(reply, "luoi_bat", None) else None),
        "chuyen_nguoi": {"co": bool(getattr(reply, "escalate", False)),
                         "ly_do": _cat(getattr(reply, "escalate_reason", "") or "", mat_na)},
        "cong_cu": [
            {"ten": str(c.get("ten", "")), "vong": c.get("vong"), "ms": c.get("ms"),
             "tham_so": _cat(c.get("tham_so"), mat_na),
             "ket_qua": _cat(c.get("ket_qua"), mat_na)}
            for c in cong_cu[:_TOI_DA_CONG_CU]
        ],
        "cong_cu_bo_bot": max(0, len(cong_cu) - _TOI_DA_CONG_CU),
        "tri_thuc": [
            {k: r.get(k) for k in ("document_id", "version_id", "version",
                                   "chunk_id", "title", "published_at")}
            for r in tri_thuc[:_TOI_DA_TRI_THUC]
        ],
        "nguon": list(getattr(reply, "sources", None) or [])[:_TOI_DA_TRI_THUC],
        "goi_ky_nang": list(getattr(reply, "goi_ky_nang", None) or [])[:10],
        "model": getattr(reply, "model", "") or "",
        "cost_usd": float(getattr(reply, "cost_usd", 0.0) or 0.0),
        "tokens_in": int(getattr(reply, "tokens_in", 0) or 0),
        "tokens_out": int(getattr(reply, "tokens_out", 0) or 0),
        "latency_ms": int(getattr(reply, "latency_ms", 0) or 0),
        "so_vong": len(getattr(reply, "vong", None) or []),
    }
    return gioi_han(dv)


def _co(dv: dict) -> int:
    return len(json.dumps(dv, ensure_ascii=False, default=str).encode("utf-8"))


def gioi_han(dv: dict[str, Any]) -> dict[str, Any]:
    """Ép dưới `TRAN_BYTE` bằng cách bỏ dần phần ít quan trọng, ghi lại đã bỏ gì."""
    if _co(dv) <= TRAN_BYTE:
        return dv
    for khoa in ("ket_qua", "tham_so"):
        for c in dv.get("cong_cu", []):
            c[khoa] = AN if c.get(khoa) not in (None, AN) else c.get(khoa)
        dv["da_rut_gon"] = [*dv.get("da_rut_gon", []), khoa]
        if _co(dv) <= TRAN_BYTE:
            return dv
    # Nấc cuối: chỉ còn TÊN — vẫn trả lời được "đã gọi gì, đã đọc gì".
    dv["cong_cu"] = [{"ten": c.get("ten", "")} for c in dv.get("cong_cu", [])]
    dv["tri_thuc"] = [{"title": str(r.get("title") or "")[:_CAT_CHUOI]}
                      for r in dv.get("tri_thuc", [])]
    dv["nguon"] = [str(n)[:_CAT_CHUOI] for n in dv.get("nguon", [])]
    dv["da_rut_gon"] = [*dv.get("da_rut_gon", []), "chi_con_ten"]
    return dv
