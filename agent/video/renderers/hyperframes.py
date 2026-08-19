"""
Bậc 2 — HyperFrames. HTML/CSS -> MP4, bố cục đẹp hơn ffmpeg.

Ảnh sản phẩm vào đây thành `background-image` của từng cảnh, chữ nằm trên
lớp riêng có dải tối phía sau. Vùng đặt chữ lấy từ bước nhìn ảnh, giống hệt
bậc ffmpeg — hai bậc phải cho ra bố cục tương đương, chỉ khác độ tinh xảo.

Bậc này cần `npx hyperframes init video-studio` chạy một lần trong terminal
thật (lệnh hỏi tương tác). Chưa có thì trả lý do và router tụt xuống ffmpeg.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from agent.config import settings
from agent.video.renderers.base import RenderContext

NEWLINE = "\n"

CSS = """
  :root { --bg:#14181C; --fg:#F2F3F0; --accent:#1F6F5C; --muted:#8A938F; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1080px; height:1920px; background:var(--bg); color:var(--fg);
    font-family:"Segoe UI",system-ui,sans-serif; overflow:hidden;
  }
  .scene { position:absolute; inset:0; }
  .scene__img {
    position:absolute; inset:0; background-size:cover; background-position:center;
    animation:kb 8s ease-out both;
  }
  @keyframes kb { from { transform:scale(1); } to { transform:scale(1.1); } }
  .scene__scrim { position:absolute; inset:0; }
  .pos-duoi  .scene__scrim { background:linear-gradient(to top,rgba(8,10,12,.92) 22%,transparent 62%); }
  .pos-tren  .scene__scrim { background:linear-gradient(to bottom,rgba(8,10,12,.92) 22%,transparent 62%); }
  .pos-trai  .scene__scrim { background:linear-gradient(to right,rgba(8,10,12,.92) 30%,transparent 70%); }
  .pos-phai  .scene__scrim { background:linear-gradient(to left,rgba(8,10,12,.92) 30%,transparent 70%); }
  .scene__text { position:absolute; left:90px; right:90px; display:flex;
                 flex-direction:column; gap:26px; }
  .pos-duoi .scene__text, .pos-khong_co .scene__text { bottom:340px; }
  .pos-tren .scene__text { top:200px; }
  .pos-trai .scene__text { top:620px; right:auto; width:580px; }
  .pos-phai .scene__text { top:620px; left:auto; width:580px; }
  .kicker { font-size:30px; letter-spacing:.22em; color:var(--accent); font-weight:700; }
  .line { font-size:88px; line-height:1.14; font-weight:700; letter-spacing:-.02em; }
  .scene--accent .line { font-size:100px; }
  .rule { width:160px; height:5px; background:var(--accent); }
  .vo { position:absolute; left:90px; right:90px; bottom:110px; font-size:52px;
        line-height:1.34; text-shadow:0 2px 10px rgba(0,0,0,.9); }
"""


def _esc(s) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def build_html(ctx: RenderContext) -> str:
    blocks = []
    for i, scene in enumerate(ctx.scenes):
        asset = ctx.asset_for(scene)
        analysis = (asset or {}).get("analysis") or {}
        vung = analysis.get("vung_trong", "duoi")

        img = ""
        if asset and asset.get("file_path"):
            url = Path(asset["file_path"]).as_posix()
            img = f'    <div class="scene__img" style="background-image:url(\'{url}\')"></div>'

        audio = ctx.audio_dir / f"scene_{i:02d}.wav"
        audio_tag = ""
        if audio.exists():
            audio_tag = f'    <audio data-track src="{audio.as_posix()}"></audio>'

        cls = "scene scene--accent" if scene.get("nhan_manh") else "scene"
        blocks.append(
            f'  <section class="{cls} pos-{vung}" data-scene '
            f'data-duration="{scene.get("duration", 3)}">' + NEWLINE
            + img + NEWLINE
            + '    <div class="scene__scrim"></div>' + NEWLINE
            + audio_tag + NEWLINE
            + '    <div class="scene__text">' + NEWLINE
            + f'      <p class="kicker">{i + 1:02d}</p>' + NEWLINE
            + f'      <h2 class="line">{_esc(scene.get("text_man_hinh", ""))}</h2>' + NEWLINE
            + '      <div class="rule"></div>' + NEWLINE
            + "    </div>" + NEWLINE
            + f'    <p class="vo">{_esc(scene.get("loi_thoai", ""))}</p>' + NEWLINE
            + "  </section>"
        )

    return (
        "<!doctype html>" + NEWLINE
        + '<html lang="vi">' + NEWLINE + "<head>" + NEWLINE
        + '<meta charset="utf-8">' + NEWLINE
        + f"<title>{_esc(ctx.title)}</title>" + NEWLINE
        + "<style>" + CSS + "</style>" + NEWLINE
        + "</head>" + NEWLINE + "<body>" + NEWLINE
        + NEWLINE.join(blocks) + NEWLINE
        + "</body>" + NEWLINE + "</html>" + NEWLINE
    )


async def render(ctx: RenderContext) -> tuple[bool, str]:
    studio = settings.studio_path
    if not studio.exists():
        return False, "chưa có video-studio (chạy: npx hyperframes init video-studio)"
    if shutil.which("npx") is None:
        return False, "không thấy npx (cần Node 22+)"

    comp = studio / "src" / "composition.html"
    comp.parent.mkdir(parents=True, exist_ok=True)
    comp.write_text(build_html(ctx), encoding="utf-8")

    proc = await asyncio.create_subprocess_exec(
        "npx", "hyperframes", "render",
        "--input", str(comp),
        "--output", str(ctx.out_path),
        cwd=str(studio),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        proc.kill()
        return False, "hyperframes render quá 10 phút"

    if proc.returncode == 0 and ctx.out_path.exists():
        return True, "hyperframes"
    return False, out.decode(errors="replace")[-400:]
