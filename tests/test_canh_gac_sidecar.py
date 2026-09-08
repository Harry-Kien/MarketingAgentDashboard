"""
Người canh phải thấy sidecar Zalo chết, không chỉ thấy app chết.

LỖI THẬT, ĐO ĐƯỢC 08.09.2026
---------------------------
Sidecar chết một mình. App vẫn trả `healthz` 200, nên `_song()` nói "sống"
và người canh không làm gì suốt cả quãng ấy. Không tin báo động nào. Chỉ
phát hiện khi có người chạy `san_sang` bằng tay.

Hậu quả nặng hơn vẻ ngoài của nó: chưa có HTTPS công khai nên Zalo cá nhân
là kênh DUY NHẤT còn nhận được tin khách. Sidecar chết là hệ thống không
nhận tin từ đâu cả, trong khi mọi đèn trên dashboard vẫn xanh.

`dung_lai()` vốn đã có bước sidecar — nó chỉ không bao giờ chạy, vì cửa
vào là "app chết". Sửa ở chỗ PHÁT HIỆN, không phải chỗ dựng lại.

VÌ SAO BẬT RIÊNG SIDECAR, KHÔNG DỰNG LẠI CẢ CHUỖI
-------------------------------------------------
`dung_lai()` tắt và bật lại app. App đang phục vụ tốt mà bị tắt vì sidecar
chết là tự gây ra một khoảng chết thứ hai để chữa khoảng chết thứ nhất.

VÌ SAO ĐỌC CẤU HÌNH CHỨ KHÔNG HỎI CSDL
--------------------------------------
Máy không dùng Zalo cá nhân thì sidecar không chạy là ĐÚNG, nên phải biết
có dùng hay không. Bản nháp đầu hỏi bảng `channel_accounts` — đúng hơn về
ngữ nghĩa, nhưng làm người canh chết chung với thứ nó đang canh, vì
Postgres sập là lúc nó cần chạy nhất. `test_nguoi_canh_ngoai_khong_dung_csdl`
bắt được ngay bộ test đầy đủ đầu tiên.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import canh_gac_ngoai as cg  # noqa: E402


def _gia(monkeypatch, *, app_song=True, sidecar_song=True, can_sidecar=True,
         bat_duoc=True) -> dict:
    """Dựng một vòng canh giả và ghi lại nó đã làm gì."""
    da_lam: dict = {"bat_sidecar": 0, "dung_lai": 0, "bao": []}

    monkeypatch.setattr(cg, "_song", lambda: (app_song, "HTTP 200" if app_song else "chết"))
    monkeypatch.setattr(cg, "_sidecar_song", lambda: sidecar_song)
    monkeypatch.setattr(cg, "_can_sidecar", lambda: can_sidecar)

    def bat():
        da_lam["bat_sidecar"] += 1
        return bat_duoc, "vừa bật" if bat_duoc else "không lên"

    def dung():
        da_lam["dung_lai"] += 1
        return True, "xong"

    monkeypatch.setattr(cg, "_bat_sidecar", bat)
    monkeypatch.setattr(cg, "dung_lai", dung)
    monkeypatch.setattr(cg, "_bao", lambda muc, ct: da_lam["bao"].append((muc, ct)))
    monkeypatch.setattr(cg, "_doc_truoc", dict)
    monkeypatch.setattr(cg, "_ghi", lambda t: None)
    return da_lam


def test_sidecar_chet_mot_minh_thi_bat_lai(monkeypatch):
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=False)
    cg.main()
    assert da_lam["bat_sidecar"] == 1, "sidecar chết mà người canh đứng nhìn"


def test_bat_sidecar_khong_dung_lai_ca_chuoi(monkeypatch):
    """App đang phục vụ tốt không được tắt để chữa sidecar."""
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=False)
    cg.main()
    assert da_lam["dung_lai"] == 0


def test_bat_lai_xong_thi_bao_cho_nguoi(monkeypatch):
    """Tự chữa trong im lặng thì không ai biết nó hay chết ở đâu."""
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=False)
    cg.main()
    assert any("sidecar" in ct.lower() for _, ct in da_lam["bao"])


def test_bat_khong_len_thi_bao_hong(monkeypatch):
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=False, bat_duoc=False)
    cg.main()
    assert any(muc == "hong" for muc, _ in da_lam["bao"])


def test_khong_dung_zalo_ca_nhan_thi_khong_dung_toi(monkeypatch):
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=False, can_sidecar=False)
    cg.main()
    assert da_lam["bat_sidecar"] == 0 and da_lam["bao"] == []


def test_ca_hai_song_thi_khong_lam_gi(monkeypatch):
    da_lam = _gia(monkeypatch, app_song=True, sidecar_song=True)
    cg.main()
    assert da_lam["bat_sidecar"] == 0 and da_lam["dung_lai"] == 0


def test_app_chet_thi_di_duong_cu_khong_bat_rieng_sidecar(monkeypatch):
    """
    App chết thì `dung_lai()` đã dựng cả bốn bước, trong đó có sidecar.
    Bật riêng thêm một lần nữa là chạy hai tiến trình sidecar tranh cổng.
    """
    da_lam = _gia(monkeypatch, app_song=False, sidecar_song=False)
    cg.main()
    assert da_lam["bat_sidecar"] == 0


def test_khong_cau_hinh_sidecar_thi_coi_nhu_khong_can(monkeypatch):
    """
    `zalo_sidecar_secret` rỗng nghĩa là sidecar chưa từng được cấu hình:
    nó không chạy là ĐÚNG, và báo động ở đó là đỏ vĩnh viễn.
    """
    monkeypatch.setattr(cg.settings, "zalo_sidecar_secret", "")
    assert cg._can_sidecar() is False
    monkeypatch.setattr(cg.settings, "zalo_sidecar_secret", "x" * 32)
    assert cg._can_sidecar() is True


def test_nguoi_canh_van_khong_dung_csdl():
    """
    Bản nháp đầu của `_can_sidecar` hỏi bảng `channel_accounts`. Đúng hơn
    về ngữ nghĩa, nhưng làm người canh chết chung với thứ nó đang canh —
    Postgres sập là lúc nó cần chạy nhất. Test cũ đã bắt được; giữ ca này
    ngay cạnh mã sidecar để lần sau không ai thêm lại.
    """
    src = (ROOT / "scripts" / "canh_gac_ngoai.py").read_text(encoding="utf-8")
    for cam in ("from agent import db", "agent.db", "import asyncpg"):
        assert cam not in src, cam
