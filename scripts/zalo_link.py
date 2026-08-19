"""
Nối ZaloCRM vào hệ thống — chạy SAU KHI đã quét QR trong ZaloCRM.

    python -m scripts.zalo_link

Việc nó làm:
  1. Đọc API key công khai từ CSDL của ZaloCRM (hoặc sinh mới nếu chưa có).
  2. Tìm tài khoản Zalo đã kết nối để lấy id dùng cho việc GỬI tin.
  3. Ghi cả hai vào .env của hệ thống.
  4. Gọi thử Public API để xác nhận thông suốt.

Script này CHỈ ĐỌC cấu hình của ZaloCRM, không sửa mã nguồn của nó.
"""
from __future__ import annotations

import re
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CRM_DIR = ROOT / "ZaloCRM"
DB_CONTAINER = "zalo-crm-db"


def crm_env(key: str) -> str:
    env = CRM_DIR / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return ""


def sql(query: str) -> str:
    """Chạy một câu SQL trong container Postgres của ZaloCRM."""
    password = crm_env("DB_PASSWORD")
    user = crm_env("DB_USER") or "crmuser"
    name = crm_env("DB_NAME") or "zalocrm"
    proc = subprocess.run(
        ["docker", "exec", "-e", f"PGPASSWORD={password}", DB_CONTAINER,
         "psql", "-U", user, "-d", name, "-tAc", query],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:300])
    return proc.stdout.strip()


def patch_env(**values: str) -> None:
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in values.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    if not CRM_DIR.exists():
        print("Không thấy thư mục ZaloCRM/. Clone và khởi động nó trước.")
        return 1

    # --- 1. API key ---
    print("[1/4] Lấy API key công khai...")
    org = sql("SELECT id FROM organizations ORDER BY created_at LIMIT 1")
    if not org:
        print("  Chưa có tổ chức nào. Mở http://localhost:3080 và tạo tài khoản trước.")
        return 1

    key = sql(
        "SELECT value_plain FROM app_settings "
        f"WHERE org_id='{org}' AND setting_key='public_api_key' LIMIT 1"
    )
    if not key:
        key = "zcrm_" + secrets.token_hex(24)
        sql(
            "INSERT INTO app_settings (id, org_id, setting_key, value_plain, created_at, updated_at) "
            f"VALUES ('{uuid.uuid4()}','{org}','public_api_key','{key}',now(),now())"
        )
        print("  Chưa có key -> đã sinh mới.")
    print(f"  {key[:16]}...{key[-4:]}")

    # --- 2. Tài khoản Zalo ---
    print("[2/4] Tìm tài khoản Zalo đã kết nối...")
    rows = sql(
        "SELECT id || '|' || coalesce(display_name, zalo_uid, '?') || '|' || status "
        "FROM zalo_accounts WHERE archived_at IS NULL ORDER BY created_at"
    )
    accounts = [r.split("|") for r in rows.splitlines() if r.strip()]
    if not accounts:
        print("  CHƯA CÓ tài khoản Zalo nào.")
        print("  Mở http://localhost:3080 -> Tài khoản Zalo -> Thêm Zalo -> quét QR,")
        print("  rồi chạy lại lệnh này.")
        patch_env(ZALOCRM_API_KEY=key)
        print("\n  (Đã ghi API key vào .env; còn thiếu ZALOCRM_ACCOUNT_ID.)")
        return 1

    for acc_id, label, status in accounts:
        print(f"   - {acc_id}  {label}  [{status}]")
    connected = [a for a in accounts if a[2] == "connected"]
    chosen = (connected or accounts)[0]
    if not connected:
        print("  CẢNH BÁO: chưa tài khoản nào ở trạng thái 'connected'. Gửi tin sẽ lỗi 422.")
    print(f"  Dùng: {chosen[1]} ({chosen[0]})")

    # --- 3. Ghi .env ---
    print("[3/4] Ghi vào .env...")
    patch_env(
        ZALOCRM_API_KEY=key,
        ZALOCRM_ACCOUNT_ID=chosen[0],
        ZALOCRM_BASE_URL=f"http://localhost:{crm_env('APP_PORT') or '3080'}",
    )
    print("  xong")

    # --- 4. Thử API ---
    print("[4/4] Gọi thử Public API...")
    import httpx

    base = f"http://localhost:{crm_env('APP_PORT') or '3080'}"
    try:
        r = httpx.get(
            f"{base}/api/public/conversations",
            headers={"X-API-Key": key}, params={"limit": 5}, timeout=15,
        )
        if r.status_code == 200:
            n = len(r.json().get("conversations", []))
            print(f"  HTTP 200 - {n} hội thoại")
        else:
            print(f"  HTTP {r.status_code}: {r.text[:160]}")
            return 1
    except httpx.HTTPError as exc:
        print(f"  Lỗi kết nối: {exc}")
        return 1

    print("\nXong. Khởi động lại app để nạp cấu hình mới:")
    print("  .\\start.ps1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
