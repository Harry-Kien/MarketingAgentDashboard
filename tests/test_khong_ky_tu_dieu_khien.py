"""
Mã nguồn không được chứa ký tự điều khiển (trừ xuống dòng, tab).

Vá mã qua heredoc của shell từng ba lần biến `\\b`, `\\n` thành ký tự THẬT:
một lần làm `app.js` không parse được (test_javascript_chay_duoc), một lần
nằm trong regex của tests/test_plugin_lich_su.py — `\\b` thành ký tự lùi
(0x08), regex không bao giờ khớp, phép kiểm xanh vĩnh viễn (tìm ra
23.10.2026 nhờ ruff PLE2510). ruff chỉ soi chuỗi Python; tệp này soi cả
JavaScript, HTML, SQL.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_BO_QUA = {"node_modules", ".venv", ".git", "__pycache__", "worktrees", "video-studio"}
_DUOI = ("*.py", "*.js", "*.mjs", "*.html", "*.sql", "*.css", "*.md")
_XAU = {chr(c) for c in range(32)} - {"\n", "\r", "\t"}


def _cac_tep() -> list[Path]:
    ra: list[Path] = []
    for duoi in _DUOI:
        ra += [p for p in ROOT.rglob(duoi) if not _BO_QUA & set(p.relative_to(ROOT).parts)]
    return ra


def test_co_quet_du_tep():
    """Đổi đường dẫn mà bộ quét thấy 0 tệp thì ca dưới xanh giả."""
    ten = {p.name for p in _cac_tep()}
    assert {"main.py", "app.js", "index.html", "schema.sql"} <= ten


def test_khong_ky_tu_dieu_khien_trong_ma_nguon():
    hong = []
    for p in _cac_tep():
        try:
            s = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for i, dong in enumerate(s.splitlines(), 1):
            ky = sorted({hex(ord(c)) for c in dong if c in _XAU})
            if ky:
                hong.append(f"{p.relative_to(ROOT)}:{i} {ky}")
    assert not hong, "ký tự điều khiển trong mã (heredoc nuốt dấu \\?):\n" + "\n".join(hong[:20])
