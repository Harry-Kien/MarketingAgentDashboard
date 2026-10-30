"""
Zalo mất phiên phải có NGƯỜI biết — đo trên máy thật 29.10.2026.

Cả hai nick Zalo cá nhân mất phiên từ ít nhất 22.10. Vòng giữ phiên ghi
542 dòng "cần quét QR" mỗi ngày vào nhật ký, và chỉ thế: không báo động nào
ra ngoài, tài khoản vẫn `active`, bảng sẵn sàng vẫn "đủ" (nó coi kênh là
thật khi kênh TỪNG có một lần xanh). Tin khách cuối cùng: 26.09.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.omnichannel.accounts import AccountStatus  # noqa: E402
from agent.omnichannel.zalo_session_keeper import (  # noqa: E402
    DAU_LECH_BI_MAT, bao_phien_hong, den_luot_thu,
)


@dataclass
class _Tk:
    display_name: str
    status: AccountStatus


class _Repo:
    def __init__(self, status=AccountStatus.ACTIVE):
        self.tk = _Tk("Mr Kiên", status)
        self.health: list = []
        self.doi: list = []

    async def get(self, _id):
        return self.tk

    async def record_health(self, _id, *, status, code, detail=None):
        self.health.append((status, code))

    async def update_status(self, _id, status, *, actor_id):
        self.doi.append(status)
        self.tk.status = status


def _bao(repo, ly_do, da_bao_lech=None):
    bao, ghi = [], []

    async def bao_dong(chi_tiet, **kw):
        bao.append(chi_tiet)

    async def ghi_nhat_ky(kind, **kw):
        ghi.append(kind)

    kq = asyncio.run(bao_phien_hong(
        repo, "acc-1", ly_do, da_bao_lech=set() if da_bao_lech is None else da_bao_lech,
        bao_dong=bao_dong, ghi_nhat_ky=ghi_nhat_ky))
    return kq, bao, ghi


def test_mat_phien_thi_doi_trang_thai_va_bao_dong_mot_lan():
    repo = _Repo()
    kq, bao, ghi = _bao(repo, "RuntimeError: Đăng nhập thất bại")
    assert kq is True
    assert repo.doi == [AccountStatus.REAUTH_REQUIRED]
    assert repo.health == [(AccountStatus.REAUTH_REQUIRED, "zalo_personal.can_quet_lai")]
    assert len(bao) == 1 and "Mr Kiên" in bao[0] and "Quét QR" in bao[0]
    assert ghi == ["zalo_personal.can_quet_lai"]

    # Phút sau, phút sau nữa: im lặng — không 542 dòng mỗi ngày.
    for _ in range(5):
        kq, bao, ghi = _bao(repo, "RuntimeError: Đăng nhập thất bại")
        assert kq is False and bao == [] and ghi == []
    assert repo.doi == [AccountStatus.REAUTH_REQUIRED]


def test_lech_bi_mat_bao_mot_lan_va_khong_doi_trang_thai():
    """Phiên Zalo vẫn tốt — chỉ sidecar cần khởi động lại; đừng bắt quét QR."""
    repo = _Repo()
    nho: set = set()
    ly_do = f"{DAU_LECH_BI_MAT}: sidecar đang chạy với bí mật khác"
    kq, bao, ghi = _bao(repo, ly_do, nho)
    assert kq is True and repo.doi == [] and "chay_sidecar_zalo" in bao[0]
    assert "KHÔNG cần quét QR" in bao[0]
    assert ghi == ["zalo_personal.lech_bi_mat_sidecar"]
    assert _bao(repo, ly_do, nho)[0] is False


def test_tai_khoan_can_quet_lai_duoc_thu_thua():
    """Sáu mươi lần đăng nhập hỏng một giờ trông như máy dò mật khẩu."""
    nho: dict = {}
    can = {"id": "a", "status": "reauth_required"}
    assert den_luot_thu(can, nho, khoang_giay=1800, bay_gio=1000.0) is True
    assert den_luot_thu(can, nho, khoang_giay=1800, bay_gio=1060.0) is False
    assert den_luot_thu(can, nho, khoang_giay=1800, bay_gio=2799.0) is False
    assert den_luot_thu(can, nho, khoang_giay=1800, bay_gio=2801.0) is True
    # Tài khoản đang tốt (vừa đứt vì sidecar khởi động lại): lượt nào cũng thử.
    tot = {"id": "b", "status": "active"}
    assert all(den_luot_thu(tot, nho, khoang_giay=1800, bay_gio=t) for t in (1.0, 2.0, 3.0))


def test_vong_giu_phien_dung_ham_bao_va_nhip_thua():
    import agent.main as m

    src = inspect.getsource(m.giu_phien_zalo_loop)
    assert "bao_phien_hong(" in src and "canh_gac.bao_dong" in src
    assert "den_luot_thu(" in src and "THU_LAI_KHI_CAN_QUET_GIAY" in src
    assert m.THU_LAI_KHI_CAN_QUET_GIAY >= 600


def test_quet_qr_xong_thi_tai_khoan_active_lai():
    """Đường về `active` có sẵn: sidecar báo connected → webhook đặt lại trạng thái."""
    from agent.api import zalo_personal_webhook as w

    src = inspect.getsource(w.zalo_personal_callback)
    assert "AccountStatus.ACTIVE if connected" in src and "update_status" in src


# ---------------------------------------------------------------- bảng sẵn sàng

def test_san_sang_hoi_that_sidecar_tung_nick():
    from scripts import san_sang

    assert san_sang.doc_phien_zalo({})["muc"] == san_sang.DU
    assert san_sang.doc_phien_zalo({"Mr Kiên": "connected"})["muc"] == san_sang.DU
    kq = san_sang.doc_phien_zalo({"Mr Kiên": "disconnected", "Baor": "connected"})
    assert kq["muc"] == san_sang.CHAN and "Mr Kiên" in kq["ghi"] and "Baor" not in kq["ghi"]
    assert "Quét QR" in kq["sua"]
    assert "await kiem_phien_zalo()" in inspect.getsource(san_sang.chay)


# ---------------------------------------------------------------- dựng lại tunnel / sidecar

def test_lenh_con_tren_windows_co_console_an_rieng(monkeypatch):
    """
    Người canh bật `noi_lai_facebook` tách rời (không console). Lệnh con dạng
    console bật trần từ đó chết sau vài giây (0xC000013A) — đo 29.10.2026,
    tunnel chết cả buổi chiều. `CREATE_NO_WINDOW` cho nó console ẩn riêng.
    """
    import subprocess

    from scripts import khoi_dong

    goi = {}

    def gia_run(lenh, **kw):
        goi.update(kw, lenh=lenh)
        return subprocess.CompletedProcess(lenh, 0, "", "")
    monkeypatch.setattr(khoi_dong.subprocess, "run", gia_run)
    monkeypatch.setattr(khoi_dong.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)

    monkeypatch.setattr(khoi_dong.os, "name", "nt")
    khoi_dong._chay("python", "-m", "scripts.chay_tunnel")
    assert goi["creationflags"] == 0x08000000

    monkeypatch.setattr(khoi_dong.os, "name", "posix")
    khoi_dong._chay("pkill", "-f", "cloudflared")
    assert goi["creationflags"] == 0
