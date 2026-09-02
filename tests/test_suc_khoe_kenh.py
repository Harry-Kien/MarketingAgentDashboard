"""
Phép kiểm "Kênh nhận tin" phải nhìn cả kênh NATIVE, không chỉ hai kênh cũ.

Bản trước chỉ đọc `ZALOCRM_API_KEY` và `CHATWOOT_BASE_URL` — hai đường nạp
tin DI SẢN. Từ khi có connector native, khách vào qua `channel_accounts`
(Zalo cá nhân, Zalo OA, Facebook, Instagram, WhatsApp, web chat).

Đo được trên hệ đang chạy: 3 tài khoản `active`, 100 tin nhắn thật đã đi
qua — mà màn hình sức khoẻ vẫn báo "chưa nối kênh nào — hệ thống chạy nhưng
không có khách vào".

Báo sai kiểu này không mất dữ liệu, nhưng nó dạy người vận hành bỏ qua đúng
cái ô họ mở ra để tin. Và nếu kênh native chết thật, ô này vẫn nói y hệt —
vì nó chưa từng nhìn vào đó.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import suc_khoe  # noqa: E402
from agent.config import settings  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture
def khong_kenh_di_san(monkeypatch):
    """Tắt hai kênh cũ để chỉ còn native quyết định kết quả."""
    monkeypatch.setattr(settings, "zalocrm_api_key", "")
    monkeypatch.setattr(settings, "chatwoot_base_url", "")
    monkeypatch.setattr(settings, "chatwoot_api_token", "")


def _dat_tai_khoan(monkeypatch, rows: list[dict] | Exception):
    async def _fetch(sql, *args):
        if isinstance(rows, Exception):
            raise rows
        return rows
    monkeypatch.setattr(suc_khoe.db, "fetch", _fetch)


def test_co_tai_khoan_native_thi_TOT_du_hai_kenh_cu_deu_tat(
    khong_kenh_di_san, monkeypatch
):
    _dat_tai_khoan(monkeypatch, [
        {"channel": "zalo_personal", "status": "active", "n": 1},
        {"channel": "facebook", "status": "active", "n": 1},
    ])

    m = chay(suc_khoe._kiem_kenh())

    assert m["trang_thai"] == suc_khoe.TOT
    assert "zalo_personal" in m["ghi_chu"]
    assert "facebook" in m["ghi_chu"]


def test_bao_so_tai_khoan_can_xu_ly(khong_kenh_di_san, monkeypatch):
    """
    `degraded` và `reauth_required` là tài khoản còn đó nhưng KHÔNG nhận
    được tin. Không đếm ra thì người trực tưởng cả ba kênh đều chạy.
    """
    _dat_tai_khoan(monkeypatch, [
        {"channel": "zalo_personal", "status": "active", "n": 1},
        {"channel": "zalo_personal", "status": "degraded", "n": 1},
        {"channel": "facebook", "status": "reauth_required", "n": 2},
    ])

    m = chay(suc_khoe._kiem_kenh())

    assert m["trang_thai"] == suc_khoe.TOT
    assert "3 tài khoản cần xử lý" in m["ghi_chu"]


def test_khong_kenh_nao_thi_van_CANH_BAO(khong_kenh_di_san, monkeypatch):
    """Không kênh nào là lựa chọn hợp lệ, nhưng phải nói ra."""
    _dat_tai_khoan(monkeypatch, [])

    m = chay(suc_khoe._kiem_kenh())

    assert m["trang_thai"] == suc_khoe.CANH_BAO
    assert "chưa nối kênh nào" in m["ghi_chu"]


def test_chi_dem_tai_khoan_ACTIVE_la_kenh_dang_song(
    khong_kenh_di_san, monkeypatch
):
    """
    25 Trang Facebook ở `pending` không nhận được tin nào. Đếm chúng như
    kênh đang sống là báo xanh cho một thứ chưa hoạt động.
    """
    _dat_tai_khoan(monkeypatch, [
        {"channel": "facebook", "status": "pending", "n": 25},
    ])

    m = chay(suc_khoe._kiem_kenh())

    assert m["trang_thai"] == suc_khoe.CANH_BAO


def test_csdl_hong_thi_khong_lam_sap_phep_kiem(khong_kenh_di_san, monkeypatch):
    """
    CSDL hỏng đã có mục riêng báo. Mục này ném theo là một dòng đỏ thừa che
    mất dòng đỏ thật.
    """
    _dat_tai_khoan(monkeypatch, RuntimeError("CSDL sập"))

    m = chay(suc_khoe._kiem_kenh())

    assert m["trang_thai"] == suc_khoe.CANH_BAO
    assert "chưa nối kênh nào" in m["ghi_chu"]
