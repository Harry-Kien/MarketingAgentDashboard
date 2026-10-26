"""
Bảng "sẵn sàng" chạy TRONG container cửa hàng (VPS) phải nói thật.

24.10.2026, dựng thật lần đầu: bảng gốc ra 5 việc CHẶN trong container, ba
giả (không có tệp .env, không có sao lưu, cổng 8000 "mở ra LAN") — vì sao
lưu và người canh chạy từ mặt phẳng điều khiển bên ngoài. Và ngược lại, nó
báo "đủ" cho ERP đã chết sáu ngày. Canh cả hai chiều.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang as ss  # noqa: E402


def _luc(gio_truoc: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=gio_truoc)).isoformat()


def test_co_silo_chi_bat_khi_dat_ro(monkeypatch):
    monkeypatch.delenv("CSKH_SILO", raising=False)
    assert not ss.trong_silo()
    monkeypatch.setenv("CSKH_SILO", "1")
    assert ss.trong_silo()


def test_mau_env_cua_hang_bat_co_silo():
    mau = (ROOT / "trien_khai" / "mau" / "env.cua_hang").read_text(encoding="utf-8")
    assert "\nCSKH_SILO=1\n" in mau


def test_silo_bi_mat_doc_bien_moi_truong(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "ROOT", tmp_path)            # không có tệp .env
    monkeypatch.setenv("CSKH_SILO", "1")
    monkeypatch.setenv("WEBHOOK_SECRET", "k3nD8sPqW2vXbY7mZ4tR")
    assert ss.kiem_bi_mat()["muc"] == ss.DU
    monkeypatch.setenv("WEBHOOK_SECRET", "changeme-bi-mat-that")
    m = ss.kiem_bi_mat()
    assert m["muc"] == ss.CHAN and "changeme" not in m["ghi"]


def test_ngoai_silo_thieu_env_van_chan(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    monkeypatch.delenv("CSKH_SILO", raising=False)
    assert ss.kiem_bi_mat()["muc"] == ss.CHAN


def test_sao_luu_silo_ba_muc():
    assert ss.doc_sao_luu_silo(None, None)["muc"] == ss.CHAN
    assert ss.doc_sao_luu_silo({"luc": _luc(50)}, None)["muc"] == ss.CANH_BAO
    m = ss.doc_sao_luu_silo({"luc": _luc(3)}, None)
    assert m["muc"] == ss.CANH_BAO and "CHƯA TỪNG thử phục hồi" in m["ghi"]
    assert ss.doc_sao_luu_silo({"luc": _luc(3)}, {"luc": _luc(24 * 40)})["muc"] == ss.CANH_BAO
    m = ss.doc_sao_luu_silo({"luc": _luc(3)}, {"luc": _luc(48), "so_bang": 61})
    assert m["muc"] == ss.DU and "61 bảng" in m["ghi"]


def test_sao_luu_silo_doc_dau_moc_trong_volume(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / ".sao_luu_ngoai").write_text(json.dumps({"luc": _luc(2)}), encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    monkeypatch.setenv("CSKH_SILO", "1")
    assert "CHƯA TỪNG" in ss.kiem_sao_luu()["ghi"]
    (tmp_path / "data" / ".sao_luu_ngoai").write_text("không phải json", encoding="utf-8")
    assert ss.kiem_sao_luu()["muc"] == ss.CHAN, "dấu mốc hỏng không được thành xanh"


def test_erp_khong_tra_loi_la_chan():
    assert ss.doc_erp_song("tep", None)["muc"] == ss.DU
    assert ss.doc_erp_song("erpnext", None)["muc"] == ss.DU
    m = ss.doc_erp_song("erpnext", "ConnectError")
    assert m["muc"] == ss.CHAN and "số cũ" in m["ghi"]


def test_erp_kiem_that_bang_mang(monkeypatch):
    """Không chỉ đọc công tắc: phải gọi ERP. Địa chỉ không ai nghe -> CHẶN."""
    import asyncio

    monkeypatch.setattr(ss.settings, "erp_loai", "erpnext")
    monkeypatch.setattr(ss.settings, "erpnext_url", "http://127.0.0.1:9")
    assert asyncio.run(ss.kiem_erp_song())["muc"] == ss.CHAN
    monkeypatch.setattr(ss.settings, "erp_loai", "odoo")
    assert asyncio.run(ss.kiem_erp_song())["muc"] == ss.CANH_BAO


def test_duong_dan_tep_khong_bi_coi_la_bi_mat_mac_dinh(monkeypatch, tmp_path):
    """`/run/secrets/gcp.json` chứa chữ "secret" — từng bị báo CHẶN oan."""
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    monkeypatch.setenv("CSKH_SILO", "1")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/run/secrets/gcp.json")
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    assert ss.kiem_bi_mat()["muc"] == ss.DU


def test_sao_luu_may_can_thu_phuc_hoi_moi_du():
    """Máy chạy tay: có bản sao lưu thôi chưa đủ — phải đã phục hồi thử được."""
    m = ss.doc_sao_luu_may(28, 0, None)
    assert m["muc"] == ss.CANH_BAO and "CHƯA TỪNG" in m["ghi"] and "--thu-phuc-hoi" in m["sua"]
    assert ss.doc_sao_luu_may(28, 0, {"luc": _luc(24 * 40)})["muc"] == ss.CANH_BAO
    m = ss.doc_sao_luu_may(28, 0, {"luc": _luc(2), "so_bang": 61})
    assert m["muc"] == ss.DU and "61 bảng" in m["ghi"]
    assert ss.doc_sao_luu_may(28, 5, {"luc": _luc(2)})["muc"] == ss.CANH_BAO, "bản cũ vẫn là cảnh báo"
