"""
Bậc 1 — Veo trên Vertex AI. Ảnh sản phẩm thành cảnh quay có chuyển động thật.

TRẠNG THÁI: viết theo tài liệu API, CHƯA CHẠY THỬ ĐƯỢC. Quota Veo chưa bật
trên project, và quota Gemini hiện đang báo 429. Không được coi bậc này là
đã kiểm chứng cho tới khi có một video thật ra lò từ nó.

Bậc này TẮT THEO MẶC ĐỊNH: `VEO_MODEL` rỗng thì trả lý do ngay và router tụt
xuống bậc dưới. Đây là chủ ý — Veo tính tiền theo giây, không được phép tự
chạy chỉ vì có ảnh trong tay.

Phân vai: Veo chỉ sinh LỚP NỀN chuyển động. Chữ và phụ đề vẫn do Pillow vẽ
và ffmpeg chồng lên, y như bậc 3 — để hai bậc cho ra bố cục giống nhau.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx

from agent.config import settings
from agent.video.renderers import layout, subtitles
from agent.video.renderers.base import RenderContext
from agent.video.renderers.ffmpeg import FPS, _ffmpeg, _run

# Veo chỉ nhận vài mốc thời lượng cố định; cảnh dài bao nhiêu thì chọn mốc
# gần nhất KHÔNG NGẮN HƠN, rồi cắt lại đúng số đo bằng ffmpeg. Cắt thì được,
# kéo dài thì không — nên luôn sinh dư.
ALLOWED_SECONDS = (4, 6, 8)
POLL_SECONDS = 10.0
POLL_MAX = 60          # tối đa 10 phút cho mỗi cảnh


def _model() -> str:
    # getattr thay vì truy cập thẳng: `config.py` đang được sửa song song ở
    # phiên khác, thiếu trường không được phép làm sập khâu dựng.
    return (getattr(settings, "veo_model", "") or "").strip()


def _region() -> str:
    # Veo không phục vụ ở `global`; dùng region của Gemini.
    return settings.gemini_region or "us-central1"


def _url(action: str) -> str:
    region = _region()
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/"
        f"{settings.gcp_project_id}/locations/{region}/publishers/google/"
        f"models/{_model()}:{action}"
    )


def _pick_seconds(duration: float) -> int:
    for s in ALLOWED_SECONDS:
        if s >= duration:
            return s
    return ALLOWED_SECONDS[-1]


def _prompt_for(scene: dict, analysis: dict) -> str:
    """
    Lời nhắc cho Veo: tả CHUYỂN ĐỘNG, không tả nội dung.

    Nội dung đã nằm trong ảnh đầu vào. Bảo Veo tả lại sản phẩm là mời nó bịa
    thêm chi tiết không có thật — đúng thứ nguyên tắc "không phát ngôn không
    căn cứ" của hệ thống này cấm.
    """
    what = (analysis or {}).get("mo_ta") or "sản phẩm"
    return (
        f"Máy quay lia chậm và ổn định quanh {what}. Giữ nguyên hình dáng, màu "
        "sắc và bố cục của ảnh gốc. Ánh sáng studio dịu, không thêm chữ, không "
        "thêm người, không thêm vật thể mới."
    )


async def _generate_clip(
    client: httpx.AsyncClient, token: str, scene: dict, asset: dict, dest: Path
) -> tuple[bool, str]:
    """Sinh một clip nền từ một ảnh. Trả (thành công, lý do nếu hỏng)."""
    try:
        raw = Path(asset["file_path"]).read_bytes()
    except OSError as exc:
        return False, f"không đọc được ảnh: {exc}"

    body = {
        "instances": [
            {
                "prompt": _prompt_for(scene, asset.get("analysis") or {}),
                "image": {
                    "bytesBase64Encoded": base64.b64encode(raw).decode("ascii"),
                    "mimeType": "image/jpeg",
                },
            }
        ],
        "parameters": {
            "aspectRatio": "9:16",
            "durationSeconds": _pick_seconds(float(scene.get("duration", 4.0))),
            "sampleCount": 1,
        },
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = await client.post(_url("predictLongRunning"), json=body, headers=headers)
    if r.status_code >= 400:
        return False, f"Veo {r.status_code}: {r.text[:200]}"
    op = (r.json() or {}).get("name")
    if not op:
        return False, "Veo không trả về tên tác vụ"

    for _ in range(POLL_MAX):
        await asyncio.sleep(POLL_SECONDS)
        p = await client.post(
            _url("fetchPredictOperation"), json={"operationName": op}, headers=headers
        )
        if p.status_code >= 400:
            return False, f"Veo poll {p.status_code}: {p.text[:200]}"
        data = p.json() or {}
        if not data.get("done"):
            continue
        if "error" in data:
            return False, f"Veo lỗi: {str(data['error'])[:200]}"
        videos = ((data.get("response") or {}).get("videos")) or []
        if not videos:
            return False, "Veo báo xong nhưng không có video"
        b64 = videos[0].get("bytesBase64Encoded")
        if not b64:
            return False, "Veo trả video không có dữ liệu"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(base64.b64decode(b64))
        return True, ""

    return False, "Veo quá thời gian chờ"


async def render(ctx: RenderContext) -> tuple[bool, str]:
    if not _model():
        return False, "Veo đang tắt (đặt VEO_MODEL trong .env để bật)"
    if not ctx.has_images:
        return False, "Veo cần ảnh sản phẩm làm đầu vào"
    if not settings.gcp_project_id:
        return False, "chưa đặt GCP_PROJECT_ID"

    try:
        from agent.core.llm import _vertex_token

        token = _vertex_token()
    except Exception as exc:  # noqa: BLE001
        return False, f"không lấy được token Vertex: {type(exc).__name__}"

    import shutil
    import tempfile

    work = Path(tempfile.mkdtemp(prefix="mkt_veo_"))
    try:
        parts: list[Path] = []
        async with httpx.AsyncClient(timeout=180.0) as client:
            for i, scene in enumerate(ctx.scenes):
                asset = ctx.asset_for(scene)
                if not asset:
                    return False, f"cảnh {i} không có ảnh; Veo không dựng được"

                clip = work / f"veo_{i:02d}.mp4"
                ok, why = await _generate_clip(client, token, scene, asset, clip)
                if not ok:
                    return False, why

                # Chồng lớp chữ và cắt đúng thời lượng đo được.
                _, over_png = layout.write_scene(scene, asset, work, i)
                dur = max(0.5, float(scene.get("duration", 4.0)))
                seg = work / f"seg_{i:02d}.mp4"
                code, log = await _run(
                    _ffmpeg(), "-y",
                    "-i", str(clip),
                    "-loop", "1", "-t", f"{dur:.3f}", "-i", str(over_png),
                    "-filter_complex",
                    f"[0:v]scale={layout.WIDTH}:{layout.HEIGHT}:"
                    "force_original_aspect_ratio=increase,"
                    f"crop={layout.WIDTH}:{layout.HEIGHT},setsar=1[bg];"
                    "[bg][1:v]overlay=0:0:format=auto[v]",
                    "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(FPS),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                    "-pix_fmt", "yuv420p", "-an", str(seg),
                )
                if code != 0:
                    return False, f"chồng chữ cảnh {i}: {log[-300:]}"
                parts.append(seg)

        listing = work / "parts.txt"
        listing.write_text(
            "\n".join("file '" + p.as_posix() + "'" for p in parts), encoding="utf-8"
        )
        ctx.out_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(listing)]
        note = "veo"
        if ctx.subtitles:
            ass = subtitles.build(ctx.scenes, work / "phude.ass")
            if ass is not None:
                cmd += ["-vf", f"ass='{subtitles.filter_arg(ass)}'"]
                note = "veo + phụ đề"
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", str(ctx.out_path),
        ]
        code, log = await _run(*cmd)
        if code != 0:
            return False, f"ghép: {log[-300:]}"
        return True, note
    finally:
        shutil.rmtree(work, ignore_errors=True)
