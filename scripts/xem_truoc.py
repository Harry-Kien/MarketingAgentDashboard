"""
Chạy bản XEM TRƯỚC của dashboard — an toàn khi production đang chạy.

    python -m scripts.xem_truoc                 phục vụ mã của chính repo này
    python -m scripts.xem_truoc <thư mục mã>    phục vụ mã của một worktree

Hoặc ghi đường dẫn worktree vào `.claude/xem_truoc_thu_muc` (bị .gitignore
chặn) — công cụ xem trước chỉ gọi được lệnh không tham số.

VÌ SAO CÓ FILE NÀY
------------------
Đo được 14.10.2026: `.claude/launch.json` chỉ có cấu hình `dashboard` —
uvicorn ĐẦY ĐỦ trên cổng 8000. Một lần gọi công cụ xem trước là một bản app
thứ hai: vòng nền, outbox, sao lưu, tất cả chạy song song với production,
và app production của người canh mất cổng. Hai outbox cùng chạy là tin trùng
gửi cho khách.

Bản xem trước này khác production ở ba chỗ, và cả ba là cố ý:

1. `VAI_TRO_TIEN_TRINH=api` — không vòng nền nào: không outbox, không đăng
   bài theo lịch, không sao lưu, không giữ phiên Zalo.
2. CSDL riêng `kt_xem_truoc` — không đọc, không ghi dữ liệu khách thật.
3. Cổng 8010 — cổng 8000 là của người canh (`scripts/canh_gac_ngoai.py`).

Khoá tới hệ thống ngoài (ZaloCRM, webhook báo động, n8n) bị để trống.
Không in bí mật nào.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
CONG = 8010
CSDL = "kt_xem_truoc"


def _thu_muc_ma() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    ghi = GOC / ".claude" / "xem_truoc_thu_muc"
    if ghi.exists() and ghi.read_text(encoding="utf-8").strip():
        return Path(ghi.read_text(encoding="utf-8").strip()).resolve()
    return GOC


def dung_moi_truong() -> str:
    """Đặt biến môi trường cho bản xem trước. Trả URL máy chủ CSDL (không tên CSDL)."""
    # Đặt TRƯỚC khi đọc .env: vòng dưới không ghi đè biến đã có.
    for k in ("ZALOCRM_API_KEY", "CANH_GAC_WEBHOOK", "N8N_WEBHOOK_URL"):
        os.environ[k] = ""
    os.environ["LEGACY_POLLING_BAT"] = "false"
    os.environ["VAI_TRO_TIEN_TRINH"] = "api"
    os.environ["PUBLIC_BASE_URL"] = f"http://127.0.0.1:{CONG}"

    env = GOC / ".env"
    if env.exists():
        for dong in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z0-9_]+)=(.*)$", dong.strip())
            if m and m.group(1) not in os.environ:
                os.environ[m.group(1)] = m.group(2)
    url = os.environ.get("DATABASE_URL",
                         "postgresql://agent:agent@127.0.0.1:5433/marketing_agent")
    may_chu = url.rsplit("/", 1)[0]
    os.environ["DATABASE_URL"] = f"{may_chu}/{CSDL}"
    return may_chu


async def _tao_csdl(may_chu: str) -> None:
    import asyncpg

    c = await asyncpg.connect(f"{may_chu}/postgres")
    try:
        if not await c.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", CSDL):
            await c.execute(f'CREATE DATABASE "{CSDL}"')
    finally:
        await c.close()


def main() -> int:
    ma = _thu_muc_ma()
    may_chu = dung_moi_truong()
    asyncio.run(_tao_csdl(may_chu))
    os.chdir(ma)
    sys.path.insert(0, str(ma))
    print(f"Xem trước: mã {ma} · CSDL {CSDL} · http://127.0.0.1:{CONG} · vai api")
    import uvicorn

    uvicorn.run("agent.main:app", host="127.0.0.1", port=CONG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
