"""
Kiểm chứng bộ dựng video mà KHÔNG cần Postgres, Vertex hay Zalo.

    python -m scripts.test_render                      # thẻ chữ, không ảnh
    python -m scripts.test_render --images data/mau    # có ảnh sản phẩm
    python -m scripts.test_render --images data/mau --vision   # gọi model nhìn ảnh

Chạy đúng đoạn khó nhất của dây chuyền: chuẩn hoá ảnh -> đo thời lượng ->
dựng hình -> ghép -> burn phụ đề. Xuất ra data/videos/_test/video.mp4

Không truyền `--vision` thì phân tích ảnh được gán tại chỗ, mỗi ảnh một vùng
trống khác nhau — để soi bố cục mà không tốn một lời gọi model nào.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

# Console Windows mac dinh cp1252 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import settings                       # noqa: E402
from agent.video import assets, timing                  # noqa: E402
from agent.video import renderers                       # noqa: E402
from agent.video.renderers import layout                # noqa: E402

SCENES = [
    {"loi_thoai": "Ngồi tám tiếng mà lưng vẫn không mỏi.",
     "text_man_hinh": "Tám tiếng, không mỏi"},
    {"loi_thoai": "Lưng lưới thoáng khí, tựa đầu chỉnh được ba hướng.",
     "text_man_hinh": "Tựa đầu chỉnh 3 hướng"},
    {"loi_thoai": "Ngả một trăm ba mươi lăm độ, có khoá ở mọi vị trí.",
     "text_man_hinh": "Ngả 135 độ", "nhan_manh": True},
    {"loi_thoai": "Aurora M một, bốn triệu hai trăm chín mươi nghìn.",
     "text_man_hinh": "Giá: 4.290.000đ. Bảo hành 24 tháng. Đặt ngay!",
     "nhan_manh": True},
    {"loi_thoai": "Nhắn tin ngay để giữ hàng hôm nay.",
     "text_man_hinh": "Nhắn để giữ hàng"},
]

# Xoay vòng đủ các vùng trống để một lần chạy soi được mọi bố cục.
FAKE_VUNG = ["duoi", "tren", "phai", "trai", "khong_co"]


async def prepare_assets(src_dir: Path, out_dir: Path, use_vision: bool):
    """Chuẩn hoá ảnh, rồi gán phân tích (thật hoặc tại chỗ)."""
    files = []
    for p in sorted(src_dir.iterdir()):
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            files.append((p.name, p.read_bytes()))
    if not files:
        print(f"    KHÔNG thấy ảnh nào trong {src_dir}")
        return []

    saved, warns = await assets.save_uploads(out_dir, files)
    for w in warns:
        print(f"    loại bỏ: {w}")
    print(f"    nhận {len(saved)}/{len(files)} ảnh")

    if use_vision:
        from agent.video import vision

        rows, cost = await vision.analyse_all(saved)
        print(f"    gọi model nhìn ảnh: {cost:.6f} USD")
        for r in rows:
            a = r["analysis"]
            print(f"      [{r['ord']}] vùng trống={a['vung_trong']:9s} "
                  f"nền={a['do_sang']:11s} chất lượng={a['chat_luong']:9s} "
                  f"dùng được={r['usable']}")
        return rows

    rows = []
    for i, row in enumerate(saved):
        rows.append({
            **row,
            "analysis": {
                "vung_trong": FAKE_VUNG[i % len(FAKE_VUNG)],
                "do_sang": ["sang", "toi", "trung_binh"][i % 3],
                "mau_chu_dao": "#1F6F5C",
            },
            "usable": True,
        })
        print(f"      [{i}] vùng trống={rows[-1]['analysis']['vung_trong']} (gán tại chỗ)")
    return rows


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", type=str, default="")
    ap.add_argument("--vision", action="store_true")
    args = ap.parse_args()

    out_dir = settings.video_out_path / "_test"
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "video.mp4"

    print("Font tìm thấy:", layout.font_path() or "KHÔNG THẤY — chữ sẽ không hiện")

    asset_rows = []
    if args.images:
        print(f"\n[0] Chuẩn hoá ảnh từ {args.images}")
        asset_rows = await prepare_assets(
            Path(args.images), out_dir / "assets", args.vision
        )
        for i, scene in enumerate(SCENES):
            scene["anh_index"] = i % max(1, len(asset_rows))

    # Có sẵn file giọng đọc trong thư mục audio thì ĐO THẬT bằng ffprobe.
    # Bản trước luôn truyền [None] nên bài test chưa bao giờ chạm vào đường
    # có âm thanh — và đó là lý do lỗi `-shortest` cắt mất khoảng nghỉ nằm
    # im suốt: không có audio thì không có gì để cắt.
    audio_paths = []
    for i in range(len(SCENES)):
        w = audio_dir / f"scene_{i:02d}.wav"
        audio_paths.append(w if w.exists() else None)
    co_tieng = sum(1 for a in audio_paths if a)

    if co_tieng:
        print(f"\n[1] Đo thời lượng ({co_tieng}/{len(SCENES)} cảnh có giọng đọc "
              "-> đo thật bằng ffprobe)")
    else:
        print("\n[1] Đo thời lượng (chưa có TTS -> dùng ước lượng âm tiết)")
    total = await timing.measure_scenes(SCENES, audio_paths)
    for i, s in enumerate(SCENES):
        print(f"    cảnh {i}: {s['duration']:>5.2f}s  bắt đầu {s['start']:>5.2f}s"
              f"  ({s['timing_source']})")
    print(f"    tổng: {total:.2f}s")

    print("\n[2] Dựng hình")
    result = await renderers.render(
        renderers.RenderContext(
            title="Giới thiệu ghế Aurora M1",
            scenes=SCENES,
            audio_dir=audio_dir,
            out_path=out_path,
            assets=asset_rows,
        )
    )
    print(f"    kết quả: {'THÀNH CÔNG' if result.ok else 'THẤT BẠI'}  "
          f"backend={result.backend}")
    if result.detail:
        print(f"    ghi chú: {result.detail[:500]}")
    if not result.ok:
        return 1

    measured = await timing.probe_duration(out_path)
    size_mb = out_path.stat().st_size / 1_048_576
    drift = abs((measured or 0) - total)

    print("\n[3] Nghiệm thu")
    print(f"    file:            {out_path}")
    print(f"    dung lượng:      {size_mb:.2f} MB")
    print(f"    thời lượng đích: {total:.2f}s")
    print(f"    thời lượng thật: {measured:.2f}s" if measured else "    đo lại: LỖI")
    print(f"    sai lệch:        {drift:.2f}s "
          f"{'(đạt)' if drift < 0.6 else '(LỆCH QUÁ NGƯỠNG)'}")

    # Video câm mà tưởng có tiếng là hỏng âm thầm — kiểm bằng số đo, không
    # bằng niềm tin. -91 dB là ngưỡng im lặng tuyệt đối của ffmpeg.
    if co_tieng:
        vol = await _do_am_luong(out_path)
        if vol is None:
            print("    âm lượng:        KHÔNG ĐO ĐƯỢC")
        else:
            print(f"    âm lượng TB:     {vol:.1f} dB "
                  f"{'(có tiếng)' if vol > -60 else '(CÂM — audio bị rớt)'}")
            if vol <= -60:
                return 1

    return 0 if measured and drift < 0.6 else 1


async def _do_am_luong(path: Path) -> float | None:
    """Âm lượng trung bình của file, qua bộ lọc volumedetect của ffmpeg."""
    import re
    import shutil

    proc = await asyncio.create_subprocess_exec(
        shutil.which("ffmpeg") or "ffmpeg", "-hide_banner", "-i", str(path),
        "-af", "volumedetect", "-f", "null", "-",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out.decode(errors="replace"))
    return float(m.group(1)) if m else None


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
