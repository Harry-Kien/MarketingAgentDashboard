"""
Giọng đọc tiếng Việt — hai nhà cung cấp, tự chuyển.

    viet-tts  ->  Google Cloud TTS  ->  không lời

Giống thang ba bậc của bộ dựng hình: bậc trên chưa sẵn sàng thì tụt xuống
bậc dưới, và bậc cuối cùng luôn chạy được (video câm, thời lượng ước lượng
theo âm tiết). Không mảnh nào được phép chặn cả dây chuyền.

VÌ SAO THÊM GOOGLE CLOUD TTS
----------------------------
`viet-tts` phải tự dựng: clone repo, tải model, cấu hình riêng. Google Cloud
TTS thì nằm trên CHÍNH project GCP mà hệ thống này đã dùng cho Gemini và
embedding — cùng xác thực, không cài gì, có giọng tiếng Việt neural.

Đổi lại nó tính tiền theo ký tự, nên phải BẬT BẰNG TAY, không tự chạy:

    gcloud services enable texttospeech.googleapis.com --project <id>

Chưa bật thì API trả 403 và hệ thống lặng lẽ tụt xuống bậc dưới.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from agent.config import settings

GOOGLE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# Neural2 tự nhiên hơn Wavenet cho tiếng Việt; Wavenet là lưới an toàn nếu
# giọng Neural2 không có ở khu vực đó.
GOOGLE_VOICE_MAC_DINH = "vi-VN-Neural2-A"


def _nha_cung_cap() -> str:
    return (getattr(settings, "tts_provider", "auto") or "auto").strip().lower()


# ---------------------------------------------------------------
#  Bậc 1 — viet-tts (API tương thích chuẩn OpenAI TTS)
# ---------------------------------------------------------------

async def available() -> bool:
    """Còn giữ tên cũ vì `scripts/` và tài liệu đang gọi."""
    return await viettts_san_sang()


async def viettts_san_sang() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            r = await c.get(settings.tts_base_url.rstrip("/").rsplit("/v1", 1)[0] + "/")
        return r.status_code < 500
    except httpx.HTTPError:
        return False


async def _viettts(text: str, out_path: Path) -> Path | None:
    payload = {
        "model": "tts-1",
        "input": text,
        "voice": settings.tts_voice,
        "response_format": "wav",
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(
                settings.tts_base_url.rstrip("/") + "/audio/speech", json=payload
            )
        if r.status_code >= 400 or not r.content:
            return None
        out_path.write_bytes(r.content)
        return out_path
    except httpx.HTTPError:
        return None


# ---------------------------------------------------------------
#  Bậc 2 — Google Cloud TTS
# ---------------------------------------------------------------

async def _google(text: str, out_path: Path) -> Path | None:
    if not settings.gcp_project_id:
        return None

    from agent.core.llm import _token

    giong = getattr(settings, "google_tts_voice", "") or GOOGLE_VOICE_MAC_DINH
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "vi-VN", "name": giong},
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
            # Chậm hơn mặc định một chút: giọng đọc quảng cáo đọc quá nhanh
            # thì người xem không kịp đọc phụ đề chạy cùng.
            "speakingRate": 0.96,
        },
    }
    try:
        token = await _token()
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(
                GOOGLE_URL, json=body,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    # ADC cục bộ bắt buộc phải chỉ rõ project chịu hạn mức,
                    # thiếu header này thì API trả 403 dù quyền vẫn đủ.
                    "x-goog-user-project": settings.gcp_project_id,
                },
            )
    except httpx.HTTPError:
        return None

    if r.status_code >= 400:
        return None
    try:
        wav = base64.b64decode(r.json()["audioContent"])
    except (ValueError, KeyError):
        return None
    if not wav:
        return None
    out_path.write_bytes(wav)
    return out_path


# ---------------------------------------------------------------
#  Điều phối
# ---------------------------------------------------------------

async def synthesize(text: str, out_path: Path) -> Path | None:
    """
    Đọc `text` thành file wav. Trả None khi không nhà cung cấp nào chạy được.

    Trả None KHÔNG phải lỗi: `timing.py` sẽ chuyển sang ước lượng âm tiết và
    dây chuyền đi tiếp. Video câm còn hơn video không có.
    """
    text = (text or "").strip()
    if not text:
        return None

    out_path.parent.mkdir(parents=True, exist_ok=True)
    nha = _nha_cung_cap()

    if nha in ("auto", "viettts"):
        ket_qua = await _viettts(text, out_path)
        if ket_qua is not None:
            return ket_qua
        if nha == "viettts":
            return None

    if nha in ("auto", "google"):
        return await _google(text, out_path)

    return None


async def chan_doan() -> dict:
    """
    Nhà cung cấp nào đang dùng được. Dùng cho script kiểm tra và dashboard.

    Gọi thật chứ không đoán: một dịch vụ "đang chạy" mà trả 403 thì vẫn là
    không dùng được, và người vận hành cần biết điều đó trước khi dựng video
    chứ không phải sau khi nhận về một video câm.
    """
    import tempfile

    ket = {"nha_cung_cap": _nha_cung_cap(), "viettts": False, "google": False}
    ket["viettts"] = await viettts_san_sang()

    with tempfile.TemporaryDirectory() as d:
        thu = await _google("thử", Path(d) / "thu.wav")
        ket["google"] = thu is not None

    ket["dung_duoc"] = ket["viettts"] or ket["google"]
    return ket
