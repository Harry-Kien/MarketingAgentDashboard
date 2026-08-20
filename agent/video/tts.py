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

import asyncio
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

async def _google(text: str, out_path: Path, ly_do: list | None = None) -> Path | None:
    """
    Đọc bằng Google Cloud TTS.

    `ly_do` là hộp để nhét NGUYÊN NHÂN hỏng ra ngoài. Bản đầu chỉ trả None,
    nên khi API báo 403 vì chưa bật dịch vụ thì người vận hành chỉ thấy chữ
    "không" và không biết phải làm gì — mất hẳn một buổi để lần ra.
    """
    def ghi(msg: str) -> None:
        if ly_do is not None:
            ly_do.append(msg)

    if not settings.gcp_project_id:
        ghi("chưa đặt GCP_PROJECT_ID trong .env")
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
    # THỬ LẠI cho lỗi tạm thời. Không có bước này thì một cảnh trong lô hỏng
    # là cảnh đó mất giọng đọc, và `timing.py` lặng lẽ chuyển riêng cảnh ấy
    # sang ước lượng âm tiết — video vẫn ra, vẫn có tiếng ở các cảnh khác,
    # nên không ai để ý. Đã bắt gặp đúng chuyện này: 4/5 cảnh đo thật, cảnh
    # thứ tư im lặng vì một lần gọi rớt.
    #
    # 403 (chưa bật API) và 400 (câu chữ sai) thì thử lại vô nghĩa.
    TAM_THOI = {429, 500, 502, 503, 504}
    cho = 2.0
    r = None

    for lan in range(3):
        try:
            token = await _token()
            async with httpx.AsyncClient(timeout=60.0) as c:
                r = await c.post(
                    GOOGLE_URL, json=body,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                        # ADC cục bộ bắt buộc phải chỉ rõ project chịu hạn
                        # mức, thiếu header này thì API trả 403 dù quyền đủ.
                        "x-goog-user-project": settings.gcp_project_id,
                    },
                )
        except httpx.HTTPError as exc:
            if lan == 2:
                ghi(f"không gọi được: {type(exc).__name__}")
                return None
            await asyncio.sleep(cho)
            cho *= 2
            continue
        except Exception as exc:  # noqa: BLE001 — token hỏng cũng phải nói ra
            ghi(f"{type(exc).__name__}: {str(exc)[:120]}")
            return None

        if r.status_code < 400 or r.status_code not in TAM_THOI or lan == 2:
            break
        await asyncio.sleep(cho)
        cho *= 2

    if r is None:
        ghi("không gọi được model")
        return None

    if r.status_code >= 400:
        try:
            msg = (r.json().get("error", {}) or {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = r.text[:200]
        if r.status_code == 403 and "has not been used" in msg:
            ghi("API chưa được bật trên project — xem hướng dẫn bên dưới")
        else:
            ghi(f"HTTP {r.status_code}: {msg[:180]}")
        return None

    try:
        wav = base64.b64decode(r.json()["audioContent"])
    except (ValueError, KeyError):
        ghi("API trả về dữ liệu âm thanh không đọc được")
        return None
    if not wav:
        ghi("API trả về file rỗng")
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

    ket = {"nha_cung_cap": _nha_cung_cap(), "viettts": False, "google": False,
           "ly_do_google": ""}
    ket["viettts"] = await viettts_san_sang()

    ly_do: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        thu = await _google("thử", Path(d) / "thu.wav", ly_do)
        ket["google"] = thu is not None
    ket["ly_do_google"] = "; ".join(ly_do)

    ket["dung_duoc"] = ket["viettts"] or ket["google"]
    return ket
