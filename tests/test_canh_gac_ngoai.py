"""
Người canh ngoài phải TỰ DỰNG LẠI app, không chỉ báo. Không cần CSDL, không mạng.

LỖI ĐÃ XẢY RA THẬT (06.09.2026)
-------------------------------
App và sidecar chết lúc 6h27 sáng, không ai bật lại tới 12h. Người canh
chạy mỗi 5 phút, thấy chết, gửi Telegram đúng một lần lúc đổi trạng thái —
rồi 5 tiếng khách nhắn vào hư không. Báo đúng mà không làm gì thì với khách
cũng như không báo.

Ba ràng buộc được canh ở đây:
  * chỉ dựng lại sau HAI lần hỏng liên tiếp — một lần trượt mạng không được
    làm khởi động lại một app đang sống;
  * tối đa BA lần mỗi giờ — lỗi cấu hình mà cứ dựng lại là vòng lặp vô ích,
    lúc đó phải báo "bỏ cuộc" cho người;
  * mọi quyết định là hàm thuần trên trạng thái JSON, để test không cần
    chạy khoi_dong thật.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scripts import canh_gac_ngoai as cg

T0 = datetime(2026, 9, 6, 6, 0, tzinfo=timezone(timedelta(hours=7)))


def _sau(phut: int) -> datetime:
    return T0 + timedelta(minutes=phut)


def test_doc_trang_thai_cu_dang_chu_van_hieu():
    """File cũ chỉ ghi 'tot'/'hong' — bản mới phải đọc được, không nổ."""
    tt = cg.doc_trang_thai("hong")
    assert tt["trang_thai"] == "hong" and tt["hong_lien_tiep"] == 1 and tt["dung_lai"] == []
    assert cg.doc_trang_thai("")["trang_thai"] == ""
    assert cg.doc_trang_thai("rác không phải json")["trang_thai"] == ""


def test_hong_lan_dau_chi_bao_khong_dung_lai():
    tt, viec = cg.quyet_dinh(cg.doc_trang_thai("tot"), song=False, bay_gio=T0)
    assert viec == "bao_hong" and tt["hong_lien_tiep"] == 1 and tt["dung_lai"] == []


def test_hong_lan_hai_lien_tiep_thi_dung_lai():
    tt1, _ = cg.quyet_dinh(cg.doc_trang_thai("tot"), song=False, bay_gio=T0)
    tt2, viec = cg.quyet_dinh(tt1, song=False, bay_gio=_sau(5))
    assert viec == "dung_lai"
    assert tt2["dung_lai"] == [_sau(5).isoformat()]


def test_toi_da_ba_lan_moi_gio_roi_bo_cuoc():
    tt = cg.doc_trang_thai("hong")
    for i in range(3):
        tt, viec = cg.quyet_dinh(tt, song=False, bay_gio=_sau(5 * (i + 1)))
        assert viec == "dung_lai", i
    tt, viec = cg.quyet_dinh(tt, song=False, bay_gio=_sau(20))
    assert viec == "bo_cuoc"
    # Bỏ cuộc chỉ báo MỘT lần — lần sau vẫn hỏng thì im, đúng luật "chỉ báo khi đổi".
    tt, viec = cg.quyet_dinh(tt, song=False, bay_gio=_sau(25))
    assert viec is None


def test_qua_mot_gio_thi_duoc_dung_lai_tiep():
    tt = cg.doc_trang_thai("hong")
    for i in range(3):
        tt, _ = cg.quyet_dinh(tt, song=False, bay_gio=_sau(5 * (i + 1)))
    tt, viec = cg.quyet_dinh(tt, song=False, bay_gio=_sau(5 + 61))
    assert viec == "dung_lai"
    assert len(tt["dung_lai"]) == 3  # mốc cũ hơn một giờ bị bỏ, mốc mới thêm vào


def test_song_lai_thi_bao_phuc_hoi_va_reset_dem():
    tt, _ = cg.quyet_dinh(cg.doc_trang_thai("tot"), song=False, bay_gio=T0)
    tt, _ = cg.quyet_dinh(tt, song=False, bay_gio=_sau(5))
    tt, viec = cg.quyet_dinh(tt, song=True, bay_gio=_sau(10))
    assert viec == "bao_phuc_hoi"
    assert tt["trang_thai"] == "tot" and tt["hong_lien_tiep"] == 0 and tt["da_bo_cuoc"] is False
    # Mốc dựng lại vẫn giữ trong cửa sổ một giờ — sống lại rồi chết ngay
    # không được coi là "chưa từng dựng lại".
    assert len(tt["dung_lai"]) == 1


def test_song_binh_thuong_khong_bao():
    tt, viec = cg.quyet_dinh(cg.doc_trang_thai("tot"), song=True, bay_gio=T0)
    assert viec is None and tt["trang_thai"] == "tot"


def test_dung_lai_goi_dung_bon_buoc_khong_dung_tunnel(monkeypatch):
    goi: list[str] = []
    from scripts import khoi_dong as k

    monkeypatch.setattr(k, "buoc_docker", lambda: (goi.append("docker") or (True, "ok")))
    monkeypatch.setattr(k, "buoc_csdl", lambda: (goi.append("csdl") or (True, "ok")))
    monkeypatch.setattr(k, "buoc_app", lambda bat_lai=False: (goi.append(f"app:{bat_lai}") or (True, "ok")))
    monkeypatch.setattr(k, "buoc_sidecar", lambda: (goi.append("sidecar") or (True, "ok")))
    monkeypatch.setattr(k, "buoc_tunnel", lambda: (goi.append("tunnel") or (True, "", False)))
    monkeypatch.setattr(k, "buoc_bo_tunnel", lambda: (goi.append("bo_tunnel") or (True, "", False)))

    ok, mo_ta = cg.dung_lai()
    assert ok and goi == ["docker", "csdl", "app:True", "sidecar"]
    assert "tunnel" not in " ".join(goi)


def test_dung_lai_hong_o_buoc_nao_thi_noi_buoc_do(monkeypatch):
    from scripts import khoi_dong as k

    monkeypatch.setattr(k, "buoc_docker", lambda: (False, "Docker Desktop chưa chạy"))
    ok, mo_ta = cg.dung_lai()
    assert not ok and "Docker" in mo_ta


def test_main_hong_hai_lan_thi_dung_lai_va_bao(monkeypatch, tmp_path):
    bao: list[tuple[str, str]] = []
    trang_thai = tmp_path / "tt"
    trang_thai.write_text(json.dumps({"trang_thai": "hong", "hong_lien_tiep": 1,
                                      "dung_lai": [], "da_bo_cuoc": False}), encoding="utf-8")
    monkeypatch.setattr(cg, "TRANG_THAI", trang_thai)
    monkeypatch.setattr(cg, "_song", lambda: (False, "ConnectionRefusedError"))
    monkeypatch.setattr(cg, "_bao", lambda muc_do, chi_tiet: bao.append((muc_do, chi_tiet)))
    monkeypatch.setattr(cg, "dung_lai", lambda: (True, "app vừa bật · sidecar vừa bật"))
    monkeypatch.setattr(cg, "_song_sau_dung_lai", lambda: True)

    ma = cg.main()

    assert ma == 0
    assert bao and bao[0][0] == "tu_dung_lai" and "vừa bật" in bao[0][1]
    tt = json.loads(trang_thai.read_text(encoding="utf-8"))
    assert tt["trang_thai"] == "tot" and len(tt["dung_lai"]) == 1


def test_main_dung_lai_that_bai_thi_van_bao_va_thoat_khac_0(monkeypatch, tmp_path):
    bao: list[tuple[str, str]] = []
    trang_thai = tmp_path / "tt"
    trang_thai.write_text("hong", encoding="utf-8")
    monkeypatch.setattr(cg, "TRANG_THAI", trang_thai)
    monkeypatch.setattr(cg, "_song", lambda: (False, "ConnectionRefusedError"))
    monkeypatch.setattr(cg, "_bao", lambda muc_do, chi_tiet: bao.append((muc_do, chi_tiet)))
    monkeypatch.setattr(cg, "dung_lai", lambda: (False, "Postgres không nhận kết nối"))

    assert cg.main() == 1
    assert bao[0][0] == "tu_dung_lai_hong" and "Postgres" in bao[0][1]


def test_tieu_de_bao_dong_co_du_moi_muc_do():
    for muc in ("hong", "phuc_hoi", "tu_dung_lai", "tu_dung_lai_hong", "bo_cuoc"):
        assert cg.TIEU_DE[muc]


def test_tai_lieu_van_hanh_co_hai_muc_do_moi():
    from pathlib import Path

    doc = (Path(__file__).resolve().parent.parent / "docs" / "van-hanh.md").read_text(encoding="utf-8")
    assert "[tu_dung_lai]" in doc and "[bo_cuoc]" in doc
