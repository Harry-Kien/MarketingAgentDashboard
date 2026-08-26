"""
Ghi verify token của các tài khoản Meta ra một file để dán vào Meta.

    python -m scripts.xem_verify_token

VÌ SAO CẦN SCRIPT NÀY
---------------------
Verify token là chuỗi Meta dội lại khi xác minh webhook. Người vận hành PHẢI
dán đúng chuỗi đó vào ô "Xác minh mã" bên Meta.

Nhưng nó nằm mã hoá trong vault — không mở bằng tay được. Không có đường đọc
thì tính năng nối kênh bế tắc ngay ở bước cuối, sau khi đã làm xong toàn bộ
phần khó.

VÌ SAO GHI RA FILE, KHÔNG IN RA MÀN HÌNH
----------------------------------------
Cùng lý do với `scripts/sinh_token.py`: thứ in ra terminal nằm lại trong lịch
sử cuộn, lịch sử lệnh, và trong ảnh chụp màn hình mà người ta hay gửi đi khi
hỏi han. File thì đọc xong đóng lại được.

File nằm trong `data/` và đã bị .gitignore chặn.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DICH = ROOT / "data" / "verify-token.txt"


async def main() -> int:
    from agent import db
    from agent.config import settings
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.accounts import Channel
    from agent.omnichannel.credential_loader import VaultCredentialLoader
    from agent.security.credential_vault import CredentialVault, parse_master_keys

    await db.init_db()
    try:
        repository = PostgresAccountRepository()
        vault = CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
        loader = VaultCredentialLoader(repository, vault)

        dong: list[str] = []
        for kenh in (Channel.FACEBOOK, Channel.INSTAGRAM, Channel.WHATSAPP):
            for account in await repository.list_active_by_channel(kenh):
                creds = await loader.load(account.id) or {}
                token = str(creds.get("verify_token") or "")
                if token:
                    dong.append(f"{account.display_name}\n  {token}\n")

        if not dong:
            print("Chưa có tài khoản Meta nào đang hoạt động, hoặc chưa có "
                  "verify token. Xác minh provider cho ít nhất một Trang trước.")
            return 1

        DICH.parent.mkdir(parents=True, exist_ok=True)
        DICH.write_text(
            "VERIFY TOKEN — dán vào ô 'Xác minh mã' bên Meta.\n"
            "Đọc xong nên xoá file này.\n\n" + "\n".join(dong),
            encoding="utf-8",
        )
        print(f"Đã ghi {len(dong)} verify token vào:\n  {DICH}")
        print("\nMở file đó, copy chuỗi, dán vào Meta.")
        print("Xong thì xoá file — nó chứa bí mật.")
        return 0
    finally:
        await db.close_db()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
