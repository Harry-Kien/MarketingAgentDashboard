"""
`san_sang` phải biết provider hiện hành có API key không và lấy từ đâu.

Nếu provider cần key mà không có thì agent chưa trả lời được một tin nào.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402


def test_provider_can_khoa_ma_khong_co_thi_CHAN():
    kq = san_sang.doc_khoa_api("gemini_api", "trong", False, 0)
    assert kq["muc"] == san_sang.CHAN and "Cài đặt API" in kq["sua"]


def test_co_khoa_tu_csdl_thi_DU_va_noi_nguon():
    kq = san_sang.doc_khoa_api("anthropic", "csdl", True, 0)
    assert kq["muc"] == san_sang.DU and "dashboard" in kq["ghi"]


def test_vertex_khong_can_khoa():
    assert san_sang.doc_khoa_api("gemini", "trong", False, 0)["muc"] == san_sang.DU


def test_giai_ma_hong_thi_CHAN():
    kq = san_sang.doc_khoa_api("gemini_api", "csdl", True, 2)
    assert kq["muc"] == san_sang.CHAN and "khoá chủ" in kq["sua"]


def test_nam_trong_bang_tong():
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    assert "kiem_khoa_api()" in nguon.split("async def chay()", 1)[1]
