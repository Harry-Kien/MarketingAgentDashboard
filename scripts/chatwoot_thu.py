"""
Thử vòng khép kín Chatwoot: khách nhắn -> agent trả lời -> tin về Chatwoot.

    python -m scripts.chatwoot_thu "Da dầu nên dùng sữa rửa mặt nào?"

Dùng Public Client API của Chatwoot — đúng con đường một khách thật đi khi
nhắn qua widget website, nên không phải giả lập webhook bằng tay.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import settings  # noqa: E402

BASE = settings.chatwoot_base_url.rstrip("/")
ACC = settings.chatwoot_account_id
TOKEN = settings.chatwoot_api_token


def _inbox_identifier(http: httpx.Client) -> str:
    r = http.get(f"{BASE}/api/v1/accounts/{ACC}/inboxes",
                 headers={"api_access_token": TOKEN})
    r.raise_for_status()
    for ib in r.json().get("payload", []):
        if ib.get("channel_type") == "Channel::Api":
            return ib["inbox_identifier"]
    raise SystemExit("Không thấy hộp thư kênh API. Chạy scripts/chatwoot_setup.rb trước.")


def main(cau_hoi: str) -> int:
    if not (BASE and ACC and TOKEN):
        print("Chưa cấu hình CHATWOOT_* trong .env")
        return 1

    http = httpx.Client(timeout=30.0)
    ident = _inbox_identifier(http)
    print(f"Hộp thư: {ident}")

    src = f"khach-thu-{int(time.time())}"
    c = http.post(f"{BASE}/public/api/v1/inboxes/{ident}/contacts",
                  json={"identifier": src, "name": "Nguyễn Thị Mai"})
    c.raise_for_status()
    src_id = c.json()["source_id"]

    v = http.post(
        f"{BASE}/public/api/v1/inboxes/{ident}/contacts/{src_id}/conversations",
        json={})
    v.raise_for_status()
    conv_id = v.json()["id"]
    print(f"Hội thoại Chatwoot: {conv_id}")

    m = http.post(
        f"{BASE}/public/api/v1/inboxes/{ident}/contacts/{src_id}"
        f"/conversations/{conv_id}/messages",
        json={"content": cau_hoi})
    m.raise_for_status()
    print(f"Khách: {cau_hoi}")
    print("Chờ agent trả lời...")

    # Webhook -> agent -> gọi ngược API Chatwoot. Nhịp người thật có nghỉ
    # giữa các tin nên phải chờ đủ lâu để thấy hết.
    seen: set[int] = set()
    for _ in range(40):
        time.sleep(2)
        r = http.get(
            f"{BASE}/public/api/v1/inboxes/{ident}/contacts/{src_id}"
            f"/conversations/{conv_id}/messages")
        if r.status_code >= 400:
            continue
        for msg in r.json():
            if msg.get("message_type") == 1 and msg["id"] not in seen:
                seen.add(msg["id"])
                print(f"  Agent: {msg.get('content')}")
        if seen and len(seen) >= 1:
            # đợi thêm một nhịp phòng khi còn tin thứ hai đang trên đường
            time.sleep(4)
            r = http.get(
                f"{BASE}/public/api/v1/inboxes/{ident}/contacts/{src_id}"
                f"/conversations/{conv_id}/messages")
            for msg in r.json():
                if msg.get("message_type") == 1 and msg["id"] not in seen:
                    seen.add(msg["id"])
                    print(f"  Agent: {msg.get('content')}")
            break

    if not seen:
        print("\nKhông thấy agent trả lời. Kiểm tra:")
        print("  - Marketing Agent có đang chạy ở cổng 8000 không")
        print("  - Webhook trong Chatwoot có đúng token không")
        print("  - docker logs chatwoot-sidekiq-1 (Sidekiq gửi webhook)")
        return 1

    print(f"\nXONG — agent trả lời {len(seen)} tin qua Chatwoot.")
    return 0


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "Da dầu nên dùng sữa rửa mặt nào ạ?"
    raise SystemExit(main(q))
