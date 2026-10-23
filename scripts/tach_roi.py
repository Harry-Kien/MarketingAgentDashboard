"""
Bật một tiến trình chạy lâu (app, sidecar) TÁCH RỜI khỏi tiến trình bật nó.

VÌ SAO CÓ TỆP NÀY — ĐO ĐƯỢC 23.10.2026
--------------------------------------
Production chết rồi sống lại theo chu kỳ từ 11:15 đến 13:55: người canh
(task Windows `CanhGacMarketingAgent`) bật lại app, app lên, healthz 200,
rồi vài phút sau app biến mất — không một dòng "Shutting down" trong
app.log, tức bị GIẾT chứ không tự tắt.

Nguyên nhân: task có giới hạn chạy 3 phút. Đường dựng lại (Docker -> app
chờ tới 60 giây -> sidecar chờ tới 180 giây) vượt 3 phút khi máy đang bận,
Task Scheduler dừng lượt chạy — và dừng luôn cả CÂY tiến trình con, gồm
chính app vừa bật. Lần sau lại bật, lại bị giết. Cũng đúng cơ chế ấy làm
app do một phiên làm việc bật lên chết theo phiên (xem bộ nhớ dự án).

Tiến trình chạy lâu không được có số phận gắn với tiến trình ngắn hạn bật
nó. Nên mọi lần bật app/sidecar đi qua đây:

  · Windows: tách khỏi job (`CREATE_BREAKAWAY_FROM_JOB`), nhóm tiến trình
    riêng, không console — Ctrl+C hay đóng console của người bật không
    lan tới. Job không cho tách thì bật kiểu cũ VÀ NÓI RA, để nhật ký
    người canh cho thấy vì sao app có thể chết theo.
  · POSIX: phiên riêng (`start_new_session`) — cùng ý, khỏi SIGHUP.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

if os.name == "nt":
    _CO_RIENG = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    _CO_TACH_JOB = _CO_RIENG | subprocess.CREATE_BREAKAWAY_FROM_JOB


def bat(lenh: list[str], *, cwd: Path | str, nhat_ky: Path,
        env: dict[str, str] | None = None) -> str:
    """
    Bật `lenh` chạy nền, stdout/stderr ghi nối vào `nhat_ky`.

    Trả một câu mô tả cách đã bật — người gọi đưa nó vào nhật ký, vì "app
    vẫn có thể chết theo người bật" là điều người vận hành phải đọc được.
    """
    with open(nhat_ky, "a", encoding="utf-8") as f:
        chung = dict(cwd=str(cwd), stdout=f, stderr=f,
                     stdin=subprocess.DEVNULL, env=env)
        if os.name != "nt":
            subprocess.Popen(lenh, start_new_session=True, **chung)
            return "tách rời (phiên riêng)"
        try:
            subprocess.Popen(lenh, creationflags=_CO_TACH_JOB, **chung)
            return "tách rời (ngoài job của người bật)"
        except OSError as exc:
            # Job của người bật cấm tách (không có JOB_OBJECT_LIMIT_BREAKAWAY_OK).
            # Vẫn phải bật — app chết theo còn hơn không có app — nhưng nói ra.
            subprocess.Popen(lenh, creationflags=_CO_RIENG, **chung)
            return (f"KHÔNG tách được khỏi job ({exc.winerror if hasattr(exc, 'winerror') else exc}) "
                    "— sẽ chết nếu tiến trình bật nó bị dừng")
