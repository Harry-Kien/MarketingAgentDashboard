"""
Bước NHÌN ẢNH — đối trọng của `timing.py` ở phía hình ảnh.

`timing.py` từ chối để model đoán thời lượng: nó đo file giọng đọc thật bằng
ffprobe rồi mới dựng. Module này áp đúng nguyên tắc đó cho bố cục: nhìn ảnh
thật trước, rồi mới quyết chữ đặt ở đâu, màu gì.

Kết quả là một tầng dữ liệu KIỂM CHỨNG ĐƯỢC nằm giữa ảnh và khâu dựng — mở
DB ra xem được, viết test cho được, và khi video xấu thì truy ngược được là
model nhìn sai hay khâu dựng làm sai.

NGUYÊN TẮC CỨNG: module này KHÔNG BAO GIỜ được chặn dây chuyền. Gọi hỏng,
JSON sai, ảnh lỗi — tất cả đều rơi về mặc định an toàn rồi đi tiếp. Đánh đổi
độ tin cậy lấy thẩm mỹ là đánh đổi sai.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

from agent.config import ROOT, settings
from agent.core import llm
from agent.video import assets

PROMPT = (ROOT / "agent" / "prompts" / "vision_asset.md").read_text(encoding="utf-8")

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

DO_SANG = {"sang", "trung_binh", "toi"}
HUONG = {"doc", "ngang", "vuong"}
CHAT_LUONG = {"tot", "mo", "qua_toi", "nhieu_hat"}
VUNG_TRONG = {"tren", "duoi", "trai", "phai", "khong_co"}

# Mặc định an toàn: chữ ở nửa dưới, nền tối, coi như ảnh dùng được.
# Nửa dưới là chỗ ít rủi ro nhất — ảnh sản phẩm thường đặt món hàng ở giữa
# hoặc trên, và mắt người đọc chữ ở dưới là quen thuộc nhất.
DEFAULT: dict = {
    "mo_ta": "",
    "mau_chu_dao": "#14181C",
    "do_sang": "trung_binh",
    "huong": "doc",
    "chat_luong": "tot",
    "vung_trong": "duoi",
    "co_chu_san": False,
    "phu_hop": True,
    "nguon": "mac_dinh",
}


def _pick(raw: dict, key: str, allowed: set[str]) -> str:
    """Lấy một trường enum. Model trả giá trị lạ thì dùng mặc định."""
    val = str(raw.get(key, "")).strip().lower()
    return val if val in allowed else DEFAULT[key]


def coerce(raw: dict | None) -> dict:
    """
    Ép kết quả model về đúng lược đồ.

    Không tin model trả đúng định dạng — kiểm từng trường, sai trường nào thì
    thay trường đó bằng mặc định, không vứt cả bản ghi.
    """
    if not isinstance(raw, dict):
        return dict(DEFAULT)

    color = str(raw.get("mau_chu_dao", "")).strip()
    return {
        "mo_ta": str(raw.get("mo_ta", "")).strip()[:300],
        "mau_chu_dao": color if _HEX.match(color) else DEFAULT["mau_chu_dao"],
        "do_sang": _pick(raw, "do_sang", DO_SANG),
        "huong": _pick(raw, "huong", HUONG),
        "chat_luong": _pick(raw, "chat_luong", CHAT_LUONG),
        "vung_trong": _pick(raw, "vung_trong", VUNG_TRONG),
        "co_chu_san": bool(raw.get("co_chu_san", False)),
        "phu_hop": bool(raw.get("phu_hop", True)),
        "nguon": "model",
    }


def is_usable(analysis: dict) -> bool:
    """
    Ảnh có được dùng làm cảnh chính không.

    Ảnh mờ hoặc quá tối làm hỏng video nhiều hơn là không có ảnh. Ảnh đã có
    chữ in sẵn thì đắp chữ nữa sẽ rối — vẫn dùng được nhưng bị xếp sau.
    """
    return bool(analysis.get("phu_hop", True)) and analysis.get("chat_luong") == "tot"


async def analyse_one(file_path: str | Path) -> tuple[dict, float]:
    """Nhìn một ảnh. Trả (phân tích, chi phí USD). Hỏng thì trả mặc định."""
    try:
        block = assets.to_data_block(file_path)
    except OSError:
        return dict(DEFAULT), 0.0

    try:
        result = await llm.complete(
            system=llm.cached_system(PROMPT),
            messages=[
                {
                    "role": "user",
                    "content": [
                        block,
                        {"type": "text", "text": "Xem ảnh trên và trả JSON."},
                    ],
                }
            ],
            model=settings.model_cheap,
            max_tokens=400,
            effort="low",
        )
    except Exception:  # noqa: BLE001 — hỏng thì đi tiếp, không chặn dây chuyền
        return dict(DEFAULT), 0.0

    return coerce(llm.parse_json(result.text)), result.cost_usd


def huong_tu_kich_thuoc(width, height) -> str | None:
    """
    Hướng ảnh TÍNH TỪ SỐ ĐO, không hỏi model.

    Chúng ta đã biết chính xác chiều rộng và chiều cao từ lúc chuẩn hoá ảnh.
    Hỏi model một thứ mình đã đo được là vừa tốn token vừa mời sai sót: trong
    lần chạy thử, model gọi một tấm 1920x1080 là ảnh "vuông". Cùng lý do
    `timing.py` không hỏi model thời lượng cảnh.
    """
    if not width or not height:
        return None
    ratio = width / height
    if ratio > 1.15:
        return "ngang"
    if ratio < 0.87:
        return "doc"
    return "vuong"


async def analyse_all(asset_rows: list[dict]) -> tuple[list[dict], float]:
    """
    Nhìn cả lô ảnh, song song.

    Trả (danh sách bản ghi có thêm `analysis` và `usable`, tổng chi phí).
    Thứ tự giữ nguyên theo `ord` — khâu kịch bản đánh số ảnh theo thứ tự này.
    """
    if not asset_rows:
        return [], 0.0

    pairs = await asyncio.gather(
        *(analyse_one(row["file_path"]) for row in asset_rows)
    )

    out, total = [], 0.0
    for row, (analysis, cost) in zip(asset_rows, pairs, strict=True):
        total += cost
        do = huong_tu_kich_thuoc(row.get("width"), row.get("height"))
        if do:
            analysis["huong"] = do          # số đo thắng phán đoán của model
        out.append({**row, "analysis": analysis, "usable": is_usable(analysis)})
    return out, round(total, 6)


def catalogue(asset_rows: list[dict]) -> str:
    """
    Danh mục ảnh dạng chữ để nhét vào prompt kịch bản.

    Kịch bản chỉ đọc MÔ TẢ, không nhìn lại ảnh — rẻ hơn nhiều lần và cache
    được, vì phần mô tả là chuỗi ổn định.
    """
    lines = []
    for row in asset_rows:
        a = row.get("analysis") or {}
        trang_thai = "dùng được" if row.get("usable") else "chất lượng kém, tránh dùng"
        lines.append(
            f"[{row['ord']}] {a.get('mo_ta') or 'không có mô tả'} "
            f"(ảnh {a.get('huong', 'doc')}, nền {a.get('do_sang', 'trung_binh')}, "
            f"{trang_thai})"
        )
    return "\n".join(lines)
