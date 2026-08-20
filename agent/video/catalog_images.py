"""
Kho ảnh sản phẩm — nguồn ảnh để agent tự dựng video mà không cần người tải lên.

VÌ SAO SINH ẢNH CHỨ KHÔNG TẢI VỀ
--------------------------------
Ảnh sản phẩm tìm trên Internet thuộc bản quyền người chụp. Dùng chúng trong
video marketing của doanh nghiệp là vi phạm, và rủi ro rơi vào doanh nghiệp.
Ảnh sinh bằng model trên chính project của bạn thì không vướng ai.

ĐIỀU PHẢI NÓI RÕ
----------------
Ảnh sinh ra KHÔNG phải ảnh chụp sản phẩm thật. Nó là hình minh hoạ đúng loại
sản phẩm, đúng dung tích, đúng tông thương hiệu — dùng cho video giới thiệu
và bản nháp thì được. Khi bán hàng thật, ảnh chụp sản phẩm thật vẫn phải
thay vào: khách nhận hàng khác với hình đã xem là chuyện không sửa được bằng
lời xin lỗi.

Vì vậy mỗi ảnh sinh ra được đánh dấu `nguon: "sinh"` trong manifest, và khâu
nào cần biết đều đọc được.

CÁCH LƯU
--------
    data/products/<ma>/img_00.jpg        ảnh đã chuẩn hoá
    data/products/<ma>/manifest.json     nguồn gốc, lời nhắc đã dùng, ngày
"""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx

from agent.config import ROOT, settings
from agent.video import assets

KHO = ROOT / "data" / "products"

# Model sinh ảnh trên Vertex. Đây là model DUY NHẤT trong ba model ảnh/video
# đã thử mà project này gọi được — Imagen 3/4 và Veo đều trả 404.
MODEL_ANH = "gemini-2.5-flash-image"

# Sinh một ảnh mất khoảng 90-100 giây. Đặt trần rộng, và đừng chạy quá nhiều
# ảnh cùng lúc kẻo nghẽn hạn mức.
TIMEOUT = 240.0
SONG_SONG = 2

# Ba góc chụp cho một sản phẩm: chính diện trên nền sạch (dùng cho cảnh giới
# thiệu), cận cảnh chất liệu (cảnh nói về công dụng), và đặt trong bối cảnh
# dùng thật (cảnh kêu gọi hành động).
GOC_CHUP = (
    (
        "chụp chính diện trên nền trắng phẳng, ánh sáng studio dịu, "
        "toàn bộ sản phẩm nằm trọn trong khung, có khoảng trống phía trên"
    ),
    (
        "cận cảnh chếch 45 độ, nền xám nhạt chuyển sắc, ánh sáng bên "
        "làm nổi chất liệu bề mặt, có khoảng trống phía dưới"
    ),
    (
        "đặt trên mặt đá sáng màu cạnh khăn bông và nhánh lá xanh, "
        "ánh sáng ban ngày tự nhiên, có khoảng trống bên phải"
    ),
)


def thu_muc(ma: str) -> Path:
    return KHO / ma.strip().upper()


def anh_cua(ma: str) -> list[Path]:
    """
    Ảnh đã có của một mã sản phẩm, theo thứ tự tên file.

    Tên file do `assets.save_uploads` đặt (`img_NN.jpg`) — kho này đi chung
    cửa chuẩn hoá với ảnh người dùng tải lên, nên phải khớp tên nó đặt.
    """
    d = thu_muc(ma)
    return sorted(d.glob("img_*.jpg")) if d.exists() else []


def manifest_cua(ma: str) -> dict:
    p = thu_muc(ma) / "manifest.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _nhan_tieng_anh(ten: str) -> str:
    """
    Phần tên tiếng Anh để in lên bao bì.

    Tên trong catalog có dạng "Serum phục hồi Aurora Revitalizing Serum" —
    phần mô tả tiếng Việt đứng trước, tên thương mại tiếng Anh đứng sau. Chỉ
    lấy từ chữ "Aurora" trở đi, vì bao bì mỹ phẩm không in mô tả tiếng Việt.
    """
    i = ten.find("Aurora")
    return (ten[i:] if i >= 0 else ten).strip()


def _loi_nhac(sp: dict, goc: str) -> str:
    """
    Lời nhắc sinh ảnh.

    CHỈ ĐỊNH chữ thay vì cấm chữ. Lần chạy đầu tôi ghi "KHÔNG in chữ" và
    model vẫn in — chỉ là may mà in đúng. Cấm một thứ model không tuân là tự
    thả nổi: sản phẩm sau nó in sai tên thì cả lô ảnh thành rác. Đưa đúng
    dòng chữ cần in rồi cấm mọi chữ khác thì kiểm được kết quả.

    Tả BAO BÌ và BỐ CỤC, không tả tác dụng — ảnh không được phép hứa hẹn
    điều mà tài liệu sản phẩm không nói.
    """
    nhan = _nhan_tieng_anh(sp.get("ten", "sản phẩm"))
    loai = sp.get("loai", "")
    dung_tich = sp.get("dung_tich", "")
    return (
        f"Ảnh sản phẩm thương mại của một {loai.lower()} chăm sóc da. "
        f"Bao bì tối giản, tông trắng ngà và xanh rêu nhạt. {goc}. "
        f"Trên bao bì in ĐÚNG ba dòng này, không thêm chữ nào khác: "
        f'"AURORA" / "{nhan}" / "{dung_tich}". '
        "Chữ in thẳng hàng, phông sans-serif mảnh, chính tả chính xác. "
        "Chất lượng ảnh quảng cáo, nét, không hạt. "
        "KHÔNG có người, KHÔNG khung viền, KHÔNG chữ ký, KHÔNG mã vạch."
    )


async def _goi_model(prompt: str) -> tuple[bytes | None, str]:
    """
    Gọi model sinh ảnh. Trả (bytes PNG hoặc None, lý do nếu hỏng).

    Phải trả LÝ DO chứ không chỉ None: bản đầu nuốt hết nguyên nhân, nên khi
    17/22 sản phẩm sinh hỏng thì không phân biệt được là hết hạn mức, bị chặn
    nội dung, hay model trả text thay vì ảnh. Lỗi câm là lỗi không sửa được.
    """
    from agent.core.llm import _token

    region = settings.gemini_region or "us-central1"
    url = (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/"
        f"{settings.gcp_project_id}/locations/{region}/publishers/google/"
        f"models/{MODEL_ANH}:generateContent"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }

    # 429 (chạm hạn mức) và 401 (token hết hạn giữa các lời gọi song song) đều
    # là lỗi TẠM THỜI. Lần chạy đầu không thử lại nên 17/22 sản phẩm sinh
    # hỏng — trong khi `llm.py` vốn đã thử lại đúng những mã này.
    TAM_THOI = {401, 429, 500, 503}
    cho = 5.0
    r = None

    for lan in range(3):
        try:
            # Lấy token MỖI LẦN, không dùng lại: 401 sinh ra chính vì token
            # cũ hết hạn trong lúc lô ảnh đang chạy.
            token = await _token()
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                r = await c.post(
                    url, json=body,
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
        except Exception as exc:  # noqa: BLE001 — hỏng thì bỏ ảnh, không chặn lô
            if lan == 2:
                return None, f"{type(exc).__name__}: {str(exc)[:100]}"
            await asyncio.sleep(cho)
            cho *= 2
            continue

        if r.status_code < 400:
            break
        if r.status_code not in TAM_THOI or lan == 2:
            break
        await asyncio.sleep(cho)
        cho *= 2

    if r is None:
        return None, "không gọi được model"

    if r.status_code >= 400:
        try:
            msg = (r.json().get("error", {}) or {}).get("message", "")[:140]
        except Exception:  # noqa: BLE001
            msg = r.text[:140]
        return None, f"HTTP {r.status_code}: {msg}"

    cand = (r.json().get("candidates") or [{}])[0]
    for part in cand.get("content", {}).get("parts", []) or []:
        if "inlineData" in part:
            try:
                return base64.b64decode(part["inlineData"]["data"]), ""
            except (ValueError, KeyError) as exc:
                return None, f"giải mã ảnh hỏng: {type(exc).__name__}"

    # Không có ảnh: model trả chữ, hoặc bị chặn. Cả hai đều cần biết.
    ly_do = cand.get("finishReason") or "không rõ"
    chu = " ".join(
        p.get("text", "") for p in cand.get("content", {}).get("parts", []) or []
    ).strip()
    return None, f"không có ảnh (finishReason={ly_do})" + (f": {chu[:100]}" if chu else "")


async def sinh_cho_san_pham(sp: dict, so_anh: int = 3) -> tuple[int, list[str]]:
    """
    Sinh và lưu ảnh cho một sản phẩm. Trả (số ảnh lưu được, lời cảnh báo).

    Ảnh đi qua đúng bộ chuẩn hoá của ảnh người dùng tải lên — cùng một cửa,
    cùng một mức kiểm.
    """
    ma = sp.get("ma", "").strip().upper()
    if not ma:
        return 0, ["sản phẩm không có mã"]

    goc = GOC_CHUP[:max(1, min(so_anh, len(GOC_CHUP)))]
    prompts = [_loi_nhac(sp, g) for g in goc]

    sem = asyncio.Semaphore(SONG_SONG)

    async def mot(prompt: str):
        async with sem:
            return await _goi_model(prompt)

    ket_qua = await asyncio.gather(*(mot(p) for p in prompts))

    files = [(f"{ma}_{i}.png", raw) for i, (raw, _) in enumerate(ket_qua) if raw]
    ly_do = [f"{ma}: {ly}" for raw, ly in ket_qua if not raw and ly]

    if not files:
        return 0, ly_do or [f"{ma}: model không trả về ảnh nào"]

    saved, warns = await assets.save_uploads(thu_muc(ma), files)
    warns = ly_do + warns

    manifest = {
        "ma": ma,
        "ten": sp.get("ten"),
        "nguon": "sinh",
        "model": MODEL_ANH,
        "ghi_chu": (
            "Ảnh do model sinh, KHÔNG phải ảnh chụp sản phẩm thật. "
            "Thay bằng ảnh chụp thật trước khi bán hàng."
        ),
        "loi_nhac": prompts[: len(saved)],
        "anh": [Path(a["file_path"]).name for a in saved],
    }
    (thu_muc(ma) / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return len(saved), warns


def asset_rows_cho(ma: str) -> list[dict]:
    """
    Ảnh của một mã sản phẩm, đúng dạng mà dây chuyền video nhận.

    Nhờ hàm này, video dựng từ kho ảnh và video dựng từ ảnh người dùng tải
    lên đi chung một đường — không có nhánh riêng nào phải bảo trì.
    """
    from PIL import Image

    rows = []
    for i, p in enumerate(anh_cua(ma)):
        try:
            with Image.open(p) as im:
                w, h = im.size
        except OSError:
            continue
        rows.append(
            {"ord": i, "file_path": str(p), "width": w, "height": h,
             "analysis": {}, "usable": True}
        )
    return rows
