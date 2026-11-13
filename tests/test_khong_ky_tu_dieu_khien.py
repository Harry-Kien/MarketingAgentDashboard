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
_BO_QUA = {"node_modules", ".venv", ".git", "__pycache__", "worktrees", "video-studio",
           "chatwoot-personal", "ZaloCRM"}
_DUOI = ("*.py", "*.js", "*.mjs", "*.html", "*.sql", "*.css", "*.md")
_XAU = {chr(c) for c in range(32)} - {"\n", "\r", "\t"}


def _cac_tep() -> list[Path]:
    ra: list[Path] = []
    # Cắt nhánh TRƯỚC khi duyệt: lọc sau rglob vẫn bò qua hàng vạn tệp
    # vendor, khiến hai test mất nhiều phút và còn vấp symlink của submodule.
    duoi = {mau[1:] for mau in _DUOI}
    for thu_muc, nhanh, tep in ROOT.walk():
        nhanh[:] = [n for n in nhanh if n not in _BO_QUA]
        ra.extend(thu_muc / ten for ten in tep if Path(ten).suffix in duoi)
    return ra


def test_co_quet_du_tep():
    """Đổi đường dẫn mà bộ quét thấy 0 tệp thì ca dưới xanh giả."""
    ten = {p.name for p in _cac_tep()}
    assert {"main.py", "app.js", "index.html", "schema.sql"} <= ten


def test_khong_duyet_sau_vao_submodule_va_node_modules(tmp_path, monkeypatch):
    import sys

    for ten in ("agent/main.py", "chatwoot-personal/app.js", "ZaloCRM/app.js",
                "connectors/x/node_modules/x/app.js"):
        p = tmp_path / ten
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    assert [p.relative_to(tmp_path).as_posix() for p in _cac_tep()] == ["agent/main.py"]


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
