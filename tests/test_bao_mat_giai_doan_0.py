"""
Bốn lỗ tìm ra ở đợt rà bảo mật 14.10.2026 — mỗi lỗ một test canh.

Không lỗ nào khai thác được NGAY trên cấu hình đang chạy. Chúng là bẫy chờ
lần sửa sau: một hàm hỏng-mở được gọi từ chỗ mới, một cookie gửi qua HTTP
trần khi người vận hành bật tunnel mà quên đổi cờ, một bí mật nằm trong
file công khai mà không ai nghĩ là bí mật.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_chatwoot_thieu_secret_la_tu_choi(monkeypatch):
    """
    Hàm kiểm chữ ký phải hỏng-ĐÓNG tự thân, không dựa vào chỗ gọi.

    Bản trước trả True khi thiếu secret. Chỗ gọi duy nhất hiện tại có kiểm
    secret trước, nên chưa ai khai thác được — nhưng hàm mang tên "hợp lệ"
    mà trả True cho một webhook chưa xác minh là bẫy cho người gọi kế tiếp.
    """
    from agent import main
    monkeypatch.setattr(main.settings, "chatwoot_webhook_secret", "")
    assert main._chatwoot_signature_hop_le(b"{}", {}) is False


def test_token_mcp_so_hang_thoi_gian():
    """`==` trên chuỗi dừng ở ký tự sai đầu tiên → đo thời gian đoán dần được token."""
    src = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    khoi = src.split('if duong.startswith("/mcp")', 1)[1][:900]
    assert '== f"Bearer {khoa}"' not in khoi
    assert "compare_digest" in khoi


def test_cookie_tu_bat_secure_khi_https():
    """
    Địa chỉ công khai là https thì cookie phiên PHẢI Secure, bất kể cờ.

    Đo 14.10.2026: `.env` đang chạy có PUBLIC_BASE_URL=https://… cùng
    COOKIE_BAO_MAT=false — người vận hành bật tunnel và không biết còn một
    cờ thứ hai phải đổi theo.
    """
    from agent.config import Settings
    s = Settings(public_base_url="https://cskh.example.vn", cookie_bao_mat=False)
    assert s.cookie_can_secure is True
    s2 = Settings(public_base_url="http://host.docker.internal:8000",
                  cookie_bao_mat=False)
    assert s2.cookie_can_secure is False
    s3 = Settings(public_base_url="http://localhost:8000", cookie_bao_mat=True)
    assert s3.cookie_can_secure is True


def test_dang_nhap_dung_cookie_can_secure():
    src = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "secure=settings.cookie_bao_mat" not in src
    assert "secure=settings.cookie_can_secure" in src


def test_compose_khong_chua_bi_mat_cung():
    yml = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for khoa in ("NEXTAUTH_SECRET:", "SALT:", "ENCRYPTION_KEY:"):
        dong = next(d for d in yml.splitlines() if d.strip().startswith(khoa))
        assert "${" in dong, f"{khoa} còn giá trị gõ cứng trong docker-compose.yml"


def test_worktree_bi_ignore():
    """Một lần `git add .` là cả cây worktree — bản sao toàn bộ mã — lên GitHub."""
    dong = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/worktrees/" in [d.strip() for d in dong]


def test_chu_thich_khong_chua_dinh_danh_that():
    src = (ROOT / "agent" / "nhat_ky.py").read_text(encoding="utf-8")
    assert "EAAR0uVcY6D" not in src
    assert "1254239285864497" not in src
