"""
Màn "Thử tính hạn" (UX-15-03) — `GET /api/sla/xem-truoc-han`.

Kiểu hỏng cần canh là XANH GIẢ: màn thử tính nói "hạn 08:05 thứ Hai" trong
khi hội thoại thật nhận hạn khác. Người quản trị tin con số trên màn hình,
không ai đi đối chiếu. Nên:

  1. Hạn trả về phải đi qua CHÍNH biểu thức SQL đặt hạn thật
     (`sla_gio.bieu_thuc_han`), chỉ thay `now()` bằng mốc giả định.
  2. Luật chọn chính sách phải trùng từng chữ với đường đổi ưu tiên và mở
     lại — chính sách riêng của kênh thắng, mức thiếu lui về "thường".
  3. Kết quả khớp phép tính Python `lich_lam_viec.han` (bản đã được test
     đối chiếu với SQL) trên cả 24/7, giờ làm việc, ngày nghỉ, ngày lễ.
  4. Chỉ đọc, và cần quyền `dinh_tuyen.doc`.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import nguoi_thu  # noqa: E402
from tests.test_phan_tich_va_sla import _chay, _kenh  # noqa: E402
from tests.test_sla_muc_tieu_lich import _TUAN, _app_sla  # noqa: E402

VN = timezone(timedelta(hours=7))


@pytest.fixture(autouse=True)
def _quen_bo_nho():
    from agent.omnichannel import sla_muc_tieu

    sla_muc_tieu.dat_lai_bo_nho()
    yield
    sla_muc_tieu.dat_lai_bo_nho()


def _gon(sql: str) -> str:
    return " ".join(sql.split())


def _khoi_chon(sql: str) -> str:
    """Đoạn FROM … LIMIT 1 — phần quyết định chính sách nào được chọn."""
    g = _gon(sql)
    return g[g.index("FROM sla_policies policy"):g.index("LIMIT 1") + len("LIMIT 1")]


def test_luat_chon_chinh_sach_trung_duong_doi_uu_tien_va_mo_lai():
    from agent.api import sla_cau_hinh, uu_tien
    from agent.omnichannel import giai_quyet

    xem = _khoi_chon(sla_cau_hinh._CHON_CHINH_SACH)
    assert xem == _khoi_chon(uu_tien._SQL_HAN_MOI)
    mo_lai = _khoi_chon(giai_quyet._CHON_CHINH_SACH.replace("c.priority", "$1")
                        .replace("c.account_id", "$2"))
    assert xem == mo_lai


def test_han_di_qua_dung_bieu_thuc_dat_han_that():
    from agent.api import sla_cau_hinh
    from agent.omnichannel.sla_gio import bieu_thuc_han

    # Mặc định giữ nguyên: ba chỗ đặt hạn thật vẫn tính từ now().
    assert bieu_thuc_han("first_response_minutes", 9).startswith("sla_han_lich(now(), ")
    sql = sla_cau_hinh._SQL_XEM_TRUOC
    for cot, so in (("first_response_minutes", 4), ("handover_response_minutes", 5),
                    ("resolution_minutes", 6)):
        that = bieu_thuc_han(cot, so)
        assert that.replace("now()", sla_cau_hinh._MOC, 1) in sql, cot
    assert "now()" not in sql, "thử tính không được lén dùng giờ hiện tại"
    # Không có câu ghi nào: màn này chỉ đọc.
    assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql, re.I)


def _vn(*a) -> datetime:
    return datetime(*a, tzinfo=VN)


def _xem(k: TestClient, **q) -> dict:
    r = k.get("/api/sla/xem-truoc-han", params=q)
    assert r.status_code == 200, r.text
    return r.json()


def _mt(d: dict) -> dict:
    return {m["ma"]: m for m in d["muc_tieu"]}


def test_xem_truoc_khop_han_that_24_7_gio_lam_viec_va_ngay_le(csdl_kiem_thu, monkeypatch):
    from agent.config import settings
    from agent.core import lich_lam_viec
    from agent.omnichannel import sla_muc_tieu

    monkeypatch.setattr(settings, "sla_theo_gio_lam_viec", False)
    qt = nguoi_thu("dinh_tuyen.doc", "dinh_tuyen.sua", ten="qt")
    with TestClient(_app_sla(csdl_kiem_thu, qt)) as k:
        # Chưa có chính sách nào: không hạn nào, nói rõ thay vì bịa.
        d = _xem(k, bat_dau="2026-11-21T11:50")
        assert d["chinh_sach"] is None and all(m["han"] is None for m in d["muc_tieu"])

        async def chinh_sach(conn, _pool):
            tk = await _kenh(conn, "xt-kenh")
            await conn.execute(
                "INSERT INTO sla_policies (priority, first_response_minutes, "
                "handover_response_minutes, resolution_minutes) VALUES ('normal', 15, 30, 1440)")
            await conn.execute(
                "INSERT INTO sla_policies (account_id, priority, first_response_minutes, "
                "resolution_minutes) VALUES ($1, 'urgent', 5, 120)", tk)
            return tk
        tk = _chay(csdl_kiem_thu, chinh_sach)

        # ---- 24/7 (lịch .env, mọi mục tiêu chọn 24/7)
        moc = _vn(2026, 11, 21, 23, 0)
        d = _xem(k, bat_dau="2026-11-21T23:00")
        assert datetime.fromisoformat(d["bat_dau"]) == moc
        mt = _mt(d)
        assert d["chinh_sach"]["pham_vi"] == "chung" and not d["chinh_sach"]["lui_ve_thuong"]
        for ma, phut in (("phan_hoi_dau", 15), ("phan_hoi_sau_chuyen_giao", 30), ("giai_quyet", 1440)):
            assert mt[ma]["che_do"] == "24_7"
            assert datetime.fromisoformat(mt[ma]["han"]) == moc + timedelta(minutes=phut), ma
            assert mt[ma]["cho_thuc_phut"] == phut
        assert mt["phan_hoi_dau"]["canh_bao_sau_phut"] == 12.0 and mt["phan_hoi_dau"]["nguong_phan_tram"] == 80

        # ---- lịch dashboard: T2–T6 8–21, T7 9–12, CN nghỉ, lễ thứ Năm 26.11
        assert k.put("/api/sla/lich-lam-viec", json={
            "bat": True, "tuan": _TUAN, "ngay_nghi": [{"ngay": "2026-11-26", "ten": "Lễ"}]}).status_code == 200
        assert k.put("/api/sla/muc-tieu", json={"muc_tieu": [
            {"ma": "phan_hoi_dau", "che_do": "gio_lam_viec", "nguong_canh_bao": 60},
            {"ma": "phan_hoi_sau_chuyen_giao", "che_do": "gio_lam_viec"},
            {"ma": "giai_quyet", "che_do": "24_7"}]}).status_code == 200
        lich = lich_lam_viec.hien_hanh()

        # T7 11:50 + 15' giờ làm việc = 10' thứ Bảy, nghỉ Chủ nhật, 5' sáng thứ Hai.
        moc = _vn(2026, 11, 21, 11, 50)
        mt = _mt(_xem(k, bat_dau="2026-11-21T11:50"))
        assert datetime.fromisoformat(mt["phan_hoi_dau"]["han"]) == _vn(2026, 11, 23, 8, 5)
        assert mt["phan_hoi_dau"]["han_chu"] == "Thứ Hai 23/11/2026 08:05"
        assert mt["phan_hoi_dau"]["cho_thuc_phut"] == (_vn(2026, 11, 23, 8, 5) - moc).total_seconds() / 60
        assert mt["phan_hoi_dau"]["canh_bao_sau_phut"] == 9.0, "ngưỡng riêng 60%"
        assert datetime.fromisoformat(mt["giai_quyet"]["han"]) == moc + timedelta(minutes=1440), \
            "giải quyết chọn 24/7 thì không đợi giờ mở cửa"
        for ma, phut in (("phan_hoi_dau", 15), ("phan_hoi_sau_chuyen_giao", 30)):
            assert mt[ma]["che_do"] == "gio_lam_viec"
            assert datetime.fromisoformat(mt[ma]["han"]) == lich_lam_viec.han(moc, phut, lich), ma

        # Tối thứ Tư + 30' sau chuyển giao: lễ thứ Năm bị bỏ qua → sáng thứ Sáu.
        mt = _mt(_xem(k, bat_dau="2026-11-25T20:45"))
        assert datetime.fromisoformat(mt["phan_hoi_sau_chuyen_giao"]["han"]) == _vn(2026, 11, 27, 8, 15)

        # Mốc có múi giờ tường minh (UTC) đọc đúng, không bị coi là giờ VN.
        mt = _mt(_xem(k, bat_dau="2026-11-23T02:00+00:00"))        # = 09:00 VN thứ Hai
        assert datetime.fromisoformat(mt["phan_hoi_dau"]["han"]) == _vn(2026, 11, 23, 9, 15)

        # ---- chọn chính sách: kênh riêng + đúng mức thắng; thiếu mức thì lui về "thường".
        d = _xem(k, bat_dau="2026-11-23T09:00", account_id=str(tk), uu_tien="urgent")
        assert d["chinh_sach"]["pham_vi"] == "kenh" and d["chinh_sach"]["muc"] == "urgent"
        mt = _mt(d)
        assert mt["phan_hoi_dau"]["phut"] == 5 and mt["phan_hoi_sau_chuyen_giao"]["han"] is None, \
            "chính sách không đặt hạn sau chuyển giao thì không bịa hạn"
        d = _xem(k, bat_dau="2026-11-23T09:00", account_id=str(tk), uu_tien="high")
        assert d["chinh_sach"]["pham_vi"] == "chung" and d["chinh_sach"]["lui_ve_thuong"]
        assert _mt(d)["phan_hoi_dau"]["phut"] == 15

        # Không thay đổi gì trong CSDL.
        async def dem(conn, _pool):
            return await conn.fetchval("SELECT count(*) FROM conversations")
        assert _chay(csdl_kiem_thu, dem) == 0
        assert sla_muc_tieu.che_do("phan_hoi_dau") == "gio_lam_viec"


def test_xem_truoc_chan_dau_vao_sai_va_can_quyen(csdl_kiem_thu):
    qt = nguoi_thu("dinh_tuyen.doc", ten="xem")
    with TestClient(_app_sla(csdl_kiem_thu, qt)) as k:
        assert k.get("/api/sla/xem-truoc-han", params={"bat_dau": "25/12 9h"}).status_code == 422
        assert k.get("/api/sla/xem-truoc-han", params={"uu_tien": "rat_gap"}).status_code == 422
        assert k.get("/api/sla/xem-truoc-han", params={"account_id": "khong-phai-uuid"}).status_code == 422
        d = k.get("/api/sla/xem-truoc-han").json()           # không mốc = bây giờ
        assert d["uu_tien"] == "normal" and len(d["muc_tieu"]) == 3
    khong_quyen = nguoi_thu("bao_cao.doc", ten="khac")
    with TestClient(_app_sla(csdl_kiem_thu, khong_quyen)) as k:
        assert k.get("/api/sla/xem-truoc-han").status_code == 403


def test_giao_dien_bon_khu_thu_tinh_goi_may_chu_va_bieu_do_khong_cdn():
    """UX-15-01/03/05/06 — các ràng buộc giao diện mà mắt thường không thấy hỏng."""
    src = ROOT / "dashboard" / "src"
    sla = (src / "26-sla.js").read_text(encoding="utf-8")
    thu = (src / "26b-sla-thu-tinh.js").read_text(encoding="utf-8")
    for khu in ("muc-tieu", "gio", "canh-bao", "thu-tinh"):
        assert f'["{khu}"' in sla, khu
    # applyRuntime() quét mọi `.modeswitch__opt` mỗi 6 giây: gỡ đánh dấu và
    # khoá nút khi AI bị ngắt. Thanh chọn khu mượn class ấy là chết theo.
    assert not re.search(r'class="[^"]*modeswitch__opt', sla + thu)
    assert 'class="sla-khu__nut' in sla
    # Máy tính hạn hỏi máy chủ, không tự cộng phút trên lịch.
    assert "/sla/xem-truoc-han" in thu
    assert "sla_han_lich" not in thu and "lan_mo_ke_tiep" not in thu
    # Ngưỡng / khi trễ lưu qua đúng đường Cài đặt API, khối khoá kỹ thuật
    # vẫn là MỘT ô trong index.html, chỉ dời vào phần "Nâng cao".
    assert "/cai-dat-api/" in sla and "data-sla-nang-cao" in sla
    assert 'getElementById("api-nhom-sla")' in sla
    # Biểu đồ xu hướng: SVG vẽ tay, không tải thư viện ngoài.
    pt = (src / "19-phan-tich.js").read_text(encoding="utf-8")
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert "_ptVeXuHuong(d.theo_ngay)" in pt and "ty_le_dung_han_xong" in pt
    # Máy chủ phải trả khoá ấy — thiếu là đường "Giải quyết" lặng lẽ trống trơn.
    import inspect

    from agent.api import phan_tich
    assert '"ty_le_dung_han_xong"' in inspect.getsource(phan_tich.tinh)
    assert 'id="ptSlaXuHuong"' in html and "data-pt-khoang" in html
    chi_tiet = html[html.index('class="nang-cao pt-chi-tiet"'):]
    chi_tiet = chi_tiet[:chi_tiet.index("</details>")]
    assert 'id="ptThoiGian"' in chi_tiet and 'id="ptNgay"' in chi_tiet, "bảng sâu nằm trong khối mở rộng"
    assert not re.search(r"<script[^>]+src=\"https?://", html), "dashboard không tải CDN"


def test_cau_hinh_tra_viec_khi_tre_bang_lua_chon_hop_le(csdl_kiem_thu):
    from agent import cau_hinh_dong

    qt = nguoi_thu("dinh_tuyen.doc", ten="xem")
    with TestClient(_app_sla(csdl_kiem_thu, qt)) as k:
        d = k.get("/api/sla/cau-hinh").json()
    assert d["khi_tre"] in cau_hinh_dong.DANH_MUC["SLA_KHI_TRE"].chon
