"""
Kiểm thử bộ kiểm "sẵn sàng chạy thật". Không gọi API, không cần CSDL.

Một bộ kiểm báo XANH sai còn nguy hiểm hơn không có bộ kiểm: người ta bật
hệ thống lên cho khách thật vì tin vào dấu xanh đó.

Chuyện ấy đã suýt xảy ra ngay trong lần chạy đầu tiên của chính script này:
nó báo "đủ — không cổng nào mở ra LAN" trong khi Docker đang tắt. Không có
gì để nối thì tất nhiên không nối được. Dấu xanh vì lý do đó khiến người ta
bật dịch vụ lên rồi tưởng đã kiểm rồi.
"""
from __future__ import annotations

import asyncio
import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang as ss  # noqa: E402


# =====================================================================
#  Không bao giờ báo xanh vì "không kiểm được"
# =====================================================================

def test_dich_vu_tat_thi_khong_ket_luan_an_toan(monkeypatch):
    """Lỗi thật của lần chạy đầu tiên."""
    monkeypatch.setattr(ss, "_dang_chay", lambda _: False)
    m = ss.kiem_cong()
    assert m["muc"] != ss.DU
    assert "chưa kiểm được" in m["ghi"]


def test_dich_vu_chay_va_dong_kin_thi_moi_la_du(monkeypatch):
    monkeypatch.setattr(ss, "_dang_chay", lambda _: True)
    monkeypatch.setattr(ss, "_cong_mo_ra_ngoai", lambda _: False)
    assert ss.kiem_cong()["muc"] == ss.DU


def test_cong_mo_ra_lan_thi_canh_bao(monkeypatch):
    monkeypatch.setattr(ss, "_dang_chay", lambda _: True)
    monkeypatch.setattr(ss, "_cong_mo_ra_ngoai", lambda c: c == 3210)
    m = ss.kiem_cong()
    assert m["muc"] == ss.CANH_BAO
    assert "Zalo sidecar" in m["ghi"]


# =====================================================================
#  Không bao giờ in ra giá trị bí mật
# =====================================================================

def test_chi_in_ten_khoa_khong_in_gia_tri(monkeypatch, tmp_path):
    """
    Bộ kiểm bí mật mà in luôn bí mật ra màn hình thì nó chính là đường rò —
    và người ta hay dán nguyên output ấy vào chat để hỏi.
    """
    env = tmp_path / ".env"
    env.write_text("WEBHOOK_SECRET=changeme-bi-mat-that\n", encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    m = ss.kiem_bi_mat()
    assert m["muc"] == ss.CHAN
    assert "WEBHOOK_SECRET" in m["ghi"]
    assert "changeme-bi-mat-that" not in m["ghi"], "ĐANG IN RA BÍ MẬT"


def test_bi_mat_that_thi_qua(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text("WEBHOOK_SECRET=k3nD8sPqW2vXbY7mZ4tR\n", encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    assert ss.kiem_bi_mat()["muc"] == ss.DU


def test_bo_qua_dong_chu_thich(monkeypatch, tmp_path):
    """Chú thích trong .env.example giải thích các giá trị mặc định, nên
    chính nó chứa đúng những chữ đang bị cấm."""
    env = tmp_path / ".env"
    env.write_text("# đổi changeme thành giá trị thật\nA=gia-tri-that-roi\n",
                   encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    assert ss.kiem_bi_mat()["muc"] == ss.DU


# =====================================================================
#  Dữ liệu hư cấu là việc CHẶN, không phải cảnh báo
# =====================================================================

def test_thuong_hieu_hu_cau_thi_chan(monkeypatch, tmp_path):
    """
    Bán hàng bằng ảnh và danh mục không phải của mình là quảng cáo sai sự
    thật — không phải "chưa lý tưởng".
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "catalog.json").write_text(
        '{"thuong_hieu": "Aurora Skin", "san_pham": []}', encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    m = ss.kiem_du_lieu_that()
    assert m["muc"] == ss.CHAN
    assert "thương hiệu mẫu cũ" in m["ghi"]


def test_chua_co_danh_muc_that_cung_chan(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    assert ss.kiem_du_lieu_that()["muc"] == ss.CHAN


def test_du_lieu_mau_MANG_TEN_THAT_van_bi_chan(monkeypatch, tmp_path):
    """
    Ca này canh đúng cái bẫy vừa suýt sập.

    Bản đầu của phép kiểm dò chuỗi "aurora". Nó đúng đúng một lần — với
    đúng bộ dữ liệu mẫu ban đầu. Người tập dùng hệ thống rất hay dựng dữ
    liệu mẫu MANG TÊN THƯƠNG HIỆU THẬT của mình, và lúc đó phép kiểm báo
    XANH cho một danh mục vẫn hoàn toàn bịa: giá bịa, tồn kho bịa, số công
    bố bịa — nhưng `san_sang` nói "đã sẵn sàng chạy với khách thật".

    Xanh giả nguy hiểm hơn đỏ giả: đỏ giả thì người ta đi kiểm, xanh giả
    thì không ai kiểm.
    """
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "catalog.json").write_text(
        '{"thuong_hieu": "Blanica", "du_lieu_mau": true, "san_pham": []}',
        encoding="utf-8")
    (tmp_path / "data" / "knowledge").mkdir()
    (tmp_path / "data" / "knowledge" / "x.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    m = ss.kiem_du_lieu_that()
    assert m["muc"] == ss.CHAN, "tên thật + dữ liệu bịa mà báo xanh"
    assert "MẪU" in m["ghi"]


def test_go_co_du_lieu_mau_thi_qua(monkeypatch, tmp_path):
    """Vế còn lại: gỡ cờ rồi mà vẫn chặn thì không ai chạy thật được."""
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "catalog.json").write_text(
        '{"thuong_hieu": "Blanica", "san_pham": []}', encoding="utf-8")
    (tmp_path / "data" / "knowledge").mkdir()
    (tmp_path / "data" / "knowledge" / "x.md").write_text("x", encoding="utf-8")
    monkeypatch.setattr(ss, "ROOT", tmp_path)
    assert ss.kiem_du_lieu_that()["muc"] == ss.DU


def test_danh_muc_mau_di_theo_repo_luon_mang_co():
    """
    `data/catalog.example.json` là thứ mã tự dùng khi chưa có danh mục
    thật. Thiếu cờ ở đó thì mọi bản clone sạch đều báo xanh sai.
    """
    import json
    from pathlib import Path
    goc = Path(__file__).resolve().parent.parent
    d = json.loads((goc / "data" / "catalog.example.json").read_text(encoding="utf-8"))
    assert d.get("du_lieu_mau") is True, "danh mục mẫu thiếu cờ du_lieu_mau"


# =====================================================================
#  Ba mức, không phải hai
# =====================================================================

def test_du_ba_muc():
    """
    Gộp "chưa lý tưởng" chung với "nguy hiểm" thì danh sách đỏ rực và
    người ta bỏ qua cả hai.
    """
    assert len({ss.CHAN, ss.CANH_BAO, ss.DU}) == 3


def test_bao_dong_trong_thi_canh_bao(monkeypatch):
    monkeypatch.setattr(ss.settings, "canh_gac_webhook", "")
    m = ss.kiem_bao_dong()
    assert m["muc"] == ss.CANH_BAO
    assert "KHÔNG ai nhận được tin" in m["ghi"]


def test_co_credential_ma_thieu_master_key_thi_chan(monkeypatch):
    """Ciphertext không có key giải mã là mất quyền vận hành mọi account."""
    from agent import db

    async def init_db():
        return None

    async def fetch(sql, *args):
        return [{"key_version": 1}]

    monkeypatch.setattr(db, "init_db", init_db)
    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(ss.settings, "credential_master_keys", "")
    monkeypatch.setattr(ss.settings, "credential_active_key_version", 1)

    result = asyncio.run(ss.kiem_kho_bi_mat_tai_khoan())

    assert result["muc"] == ss.CHAN
    assert "key version" in result["ghi"]
    assert "ciphertext" not in result["ghi"]


def test_master_key_du_phien_ban_thi_vault_san_sang(monkeypatch):
    from agent import db

    async def init_db():
        return None

    async def fetch(sql, *args):
        return [{"key_version": 1}]

    key = base64.b64encode(bytes.fromhex("01" * 32)).decode()
    monkeypatch.setattr(db, "init_db", init_db)
    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(ss.settings, "credential_master_keys", f"1:{key}")
    monkeypatch.setattr(ss.settings, "credential_active_key_version", 1)

    result = asyncio.run(ss.kiem_kho_bi_mat_tai_khoan())

    assert result["muc"] == ss.DU
    assert key not in result["ghi"]


def test_outbox_co_queue_ma_worker_khong_heartbeat_thi_chan(monkeypatch):
    from agent import db

    async def init_db():
        return None

    async def fetchrow(sql, *args):
        return {"pending": 4, "dead": 0, "last_seen_at": None}

    monkeypatch.setattr(db, "init_db", init_db)
    monkeypatch.setattr(db, "fetchrow", fetchrow)

    result = asyncio.run(ss.kiem_outbox())

    assert result["muc"] == ss.CHAN
    assert "4" in result["ghi"]
    assert "heartbeat" in result["ghi"]


def test_outbox_worker_song_va_queue_khong_tac_thi_du(monkeypatch):
    from datetime import datetime, timezone
    from agent import db

    async def init_db():
        return None

    async def fetchrow(sql, *args):
        return {
            "pending": 0,
            "dead": 0,
            "last_seen_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(db, "init_db", init_db)
    monkeypatch.setattr(db, "fetchrow", fetchrow)

    assert asyncio.run(ss.kiem_outbox())["muc"] == ss.DU
