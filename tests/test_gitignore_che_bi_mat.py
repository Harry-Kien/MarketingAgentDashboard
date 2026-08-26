"""
`.gitignore` phải che MỌI biến thể của .env, không chỉ vài cái đoán trước.

CHUYỆN ĐÃ XẢY RA THẬT
---------------------
Một script sao lưu `.env` dùng `Path(".env").with_suffix(...)` — hàm đó
NỐI THÊM đuôi chứ không thay, nên sinh ra `.env.env.truoc-credential-key`.
Tên đó rơi ra ngoài cả ba mẫu đang có (`.env`, `.env.bak`, `.env.*.bak`),
và git nhìn thấy một bản sao ĐẦY ĐỦ của .env — có bí mật — ở dạng
untracked, sẵn sàng bị `git add -A` nuốt vào.

Bài học: liệt kê từng biến thể đoán trước là trò đuổi bắt không bao giờ
thắng. Chặn cả họ `.env*` rồi mở ngoại lệ cho đúng những bản mẫu.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = (ROOT / ".gitignore").read_text(encoding="utf-8")
DONG = [d.strip() for d in GITIGNORE.splitlines() if d.strip()]


def test_chan_ca_ho_env():
    assert ".env*" in DONG, "phải chặn cả họ .env*, không liệt kê từng biến thể"


@pytest.mark.parametrize("mau", [".env.example", ".env.chatwoot.example"])
def test_van_giu_ban_mau_di_theo_repo(mau):
    """Chặn cả họ mà quên ngoại lệ là máy vừa clone không có gì để chép."""
    assert f"!{mau}" in DONG, f"{mau} PHẢI lên repo"


@pytest.mark.parametrize(
    "rac",
    ["node_modules/", ".playwright-cli/", "output/", ".ruff_cache/"],
)
def test_chan_thu_muc_sinh_ra_khi_chay(rac):
    """
    node_modules của sidecar có hàng nghìn file. Lỡ commit một lần là lịch
    sử repo phình vĩnh viễn — git không quên được.
    """
    assert rac in DONG, f"{rac} không được vào repo"
