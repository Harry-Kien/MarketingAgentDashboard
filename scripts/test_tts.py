"""
Kiểm giọng đọc: nhà cung cấp nào đang dùng được, và nghe thử.

    python -m scripts.test_tts
    python -m scripts.test_tts "Câu muốn nghe thử"

Chạy cái này TRƯỚC khi dựng video. Không có giọng đọc thì video sẽ câm và
thời lượng chỉ là ước lượng âm tiết — biết trước vẫn hơn nhận về rồi mới
phát hiện.
"""
from __future__ import annotations

import asyncio
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import settings              # noqa: E402
from agent.video import timing, tts            # noqa: E402

CAU_MAU = (
    "Serum phục hồi Aurora, ba mươi mi-li-lít, sáu trăm chín mươi nghìn đồng."
)


async def main() -> int:
    cau = " ".join(sys.argv[1:]) or CAU_MAU

    print("Đang dò nhà cung cấp giọng đọc...\n")
    ch = await tts.chan_doan()

    def dau(x: bool) -> str:
        return "DÙNG ĐƯỢC" if x else "không"

    print(f"  cấu hình TTS_PROVIDER : {ch['nha_cung_cap']}")
    print(f"  viet-tts ({settings.tts_base_url:32s}): {dau(ch['viettts'])}")
    print(f"  Google Cloud TTS ({settings.google_tts_voice:16s}): {dau(ch['google'])}")

    if not ch["dung_duoc"]:
        print("\nKHÔNG có nhà cung cấp nào chạy được.")
        print("Video sẽ CÂM và thời lượng chỉ là ước lượng âm tiết.\n")
        print("Cách nhanh nhất — bật Google Cloud TTS (tính tiền theo ký tự):")
        print(f"  gcloud services enable texttospeech.googleapis.com "
              f"--project {settings.gcp_project_id}")
        print("\nHoặc dựng viet-tts theo README rồi trỏ TTS_BASE_URL vào nó.")
        return 1

    out = settings.video_out_path / "_test" / "tts.wav"
    print(f"\nĐang đọc: {cau}")
    p = await tts.synthesize(cau, out)
    if p is None:
        print("Dò thấy dịch vụ nhưng đọc không ra file. Xem lại cấu hình.")
        return 1

    giay = await timing.probe_duration(p)
    kb = p.stat().st_size / 1024
    print(f"\n  file:       {p}")
    print(f"  dung lượng: {kb:.0f} KB")
    print(f"  thời lượng: {giay}s  (đo bằng ffprobe — đúng con số dây chuyền dùng)")
    print("\nGIỌNG ĐỌC SẴN SÀNG. Video sẽ có tiếng và thời lượng đo thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
