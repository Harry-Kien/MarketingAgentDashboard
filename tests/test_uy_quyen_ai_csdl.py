"""
Ủy quyền thực thi của AI (mục 17) trên app ĐẦY ĐỦ và Postgres thật.

Đường đi thật: công cụ AI -> chốt ủy quyền -> đề xuất (bảng ai_de_xuat) ->
chuông -> người duyệt qua API -> thi hành KIỂM LẠI điều kiện -> kết quả và
sự kiện kiểm toán. Chống thi hành hai lần, hết hạn, quyền, phạm vi kênh và
chính sách đổi giữa chừng đều chỉ lộ ra trên Postgres thật (khoá dòng, chỉ
mục một-phần) — giả lập `db` thì xanh giả.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_don_hang_tien_erp import SP, _hoi_thoai, _ton, chot_duoc  # noqa: E402,F401
from tests.test_hoan_thien_luong import _dong  # noqa: E402
from tests.test_nghiem_thu_saas import (  # noqa: E402
    _nhan_vien_moi,
    _quan_tri_vao,
    _sql,
    _them_thanh_vien,
)

# ERP giả còn hàng, ERP_GHI_DON tắt (fixture của test_don_hang_tien_erp).
pytestmark = pytest.mark.usefixtures("chot_duoc")

DON = {
    "khach_da_xac_nhan": True, "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
    "khach_dia_chi": "12 Lê Lợi, Phường Bến Thành, TP Hồ Chí Minh",
    "items": [{"ten_san_pham": SP["ten"], "so_luong": 1}],
}


@pytest.fixture(autouse=True)
def _sach(monkeypatch):
    from agent.core import tools, uy_quyen

    async def catalog():
        return {"san_pham": [SP]}

    monkeypatch.setattr(tools, "_catalog_song", catalog)
    uy_quyen.xoa_dem()
    yield
    uy_quyen.xoa_dem()


def _che_do(monkeypatch, mode: str) -> None:
    from agent import runtime

    monkeypatch.setitem(runtime.STATE, "mode", mode)


def _cong_cu(app, ten: str, args: dict, conv) -> dict:
    from agent.core import tools

    async def goi():
        return await tools.run_tool(ten, args, conv)
    return _sql(app, goi)


def _de_xuat(app, conv) -> list[dict]:
    from agent import db

    async def doc():
        return [dict(r) for r in await db.fetch(
            "SELECT * FROM ai_de_xuat WHERE conversation_id = $1 ORDER BY tao_luc", conv)]
    return _sql(app, doc)


def _su_kien(app, conv) -> list[tuple[str, dict]]:
    from agent import db

    async def doc():
        return [(r["kind"], r["detail"]) for r in await db.fetch(
            "SELECT kind, detail FROM events WHERE ref_id = $1 AND kind LIKE 'ai.%' "
            "ORDER BY id", conv)]
    return _sql(app, doc)


def _don_da_chot(app, conv) -> dict:
    from agent.core import tools

    async def goi():
        return await tools._tao_don_hang(dict(DON), products=[SP], conversation_id=conv)
    kq = _sql(app, goi)
    assert kq["tao_duoc"] is True, kq
    return kq


def test_huy_don_de_xuat_duyet_mot_lan_va_thi_hanh_kiem_lai(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    don = _don_da_chot(app_that, conv)
    _che_do(monkeypatch, "auto")

    kq = _cong_cu(app_that, "xin_huy_don", {"ma_don": don["ma_don"], "ly_do": "đổi ý"}, conv)
    assert kq["da_de_xuat"] is True and kq["can_chuyen_nhan_vien"] is False
    d = _dong(app_that, "SELECT trang_thai, yeu_cau_huy_luc FROM orders WHERE ma_don=$1",
              don["ma_don"])
    assert d["trang_thai"] == "da_chot" and d["yeu_cau_huy_luc"] is not None, "chưa ai duyệt: chưa huỷ"
    dx = _de_xuat(app_that, conv)
    assert [x["trang_thai"] for x in dx] == ["cho_duyet"]
    assert dx[0]["muc_uy_quyen"] == "co_phe_duyet" and dx[0]["che_do_ai"] == "tu_dong"
    assert dx[0]["can_cu"]["nguon"] and "Huỷ đơn" in dx[0]["de_xuat"]["tieu_de"]

    # Khách nhắn "huỷ" lần nữa: KHÔNG thêm thẻ thứ hai.
    _cong_cu(app_that, "xin_huy_don", {"ma_don": don["ma_don"], "ly_do": "đổi ý"}, conv)
    assert len(_de_xuat(app_that, conv)) == 1

    # Chuông "cần duyệt" tới người duyệt được, bấm vào mở HỘI THOẠI.
    tb = [t for t in qt.get("/api/toi/thong-bao").json()["thong_bao"]
          if t["tieu_de"].startswith("AI đề xuất")]
    assert tb and tb[0]["loai"] == "can_duyet"
    assert tb[0]["lien_ket"] == {"loai": "hoi_thoai", "id": str(conv)}

    # Thẻ hiện trong hội thoại; quản trị duyệt được.
    ds = qt.get(f"/api/ai-de-xuat?hoi_thoai={conv}").json()["de_xuat"]
    assert ds[0]["duoc_duyet"] is True and ds[0]["nhan_trang_thai"] == "Chờ duyệt"

    did = str(dx[0]["id"])
    r = qt.post(f"/api/ai-de-xuat/{did}/duyet")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["trang_thai"] == "da_thuc_hien"
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE ma_don=$1",
                 don["ma_don"])["trang_thai"] == "da_huy"

    # Bấm lần hai (hai tab, mạng chậm): không thi hành lần nữa.
    r2 = qt.post(f"/api/ai-de-xuat/{did}/duyet")
    assert r2.status_code == 409
    assert qt.post(f"/api/ai-de-xuat/{did}/tu-choi", json={}).status_code == 409

    kinds = [k for k, _ in _su_kien(app_that, conv)]
    for k in ("ai.de_xuat.tao", "ai.de_xuat.trung", "ai.de_xuat.duyet", "ai.de_xuat.thuc_hien"):
        assert k in kinds, kinds
    for k, chi_tiet in _su_kien(app_that, conv):
        if k.startswith("ai.de_xuat."):
            assert chi_tiet["de_xuat_id"] == did and chi_tiet["muc_uy_quyen"] == "co_phe_duyet"
            assert chi_tiet["conversation_id"] == str(conv) and chi_tiet["hanh_dong"] == "huy_don"


def test_quyen_va_pham_vi_kenh_khi_duyet(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    don = _don_da_chot(app_that, conv)
    _che_do(monkeypatch, "auto")
    _cong_cu(app_that, "xin_huy_don", {"ma_don": don["ma_don"], "ly_do": "x"}, conv)
    did = str(_de_xuat(app_that, conv)[0]["id"])
    tk = _dong(app_that, "SELECT account_id FROM conversations WHERE id=$1", conv)["account_id"]

    # "lan": Nhân viên (có ai.duyet, KHÔNG có don.sua) và thuộc kênh.
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, str(tk), lan_id)
    ds = lan.get(f"/api/ai-de-xuat?hoi_thoai={conv}").json()["de_xuat"]
    assert ds[0]["duoc_duyet"] is False and "don.sua" in ds[0]["thieu_quyen"]
    r = lan.post(f"/api/ai-de-xuat/{did}/duyet")
    assert r.status_code == 403 and "don.sua" in r.text

    # "minh": không thuộc kênh — 404, không xác nhận đề xuất tồn tại.
    _, minh = _nhan_vien_moi(qt, "minh")
    assert minh.get(f"/api/ai-de-xuat?hoi_thoai={conv}").status_code == 404
    assert minh.post(f"/api/ai-de-xuat/{did}/duyet").status_code == 404
    assert _de_xuat(app_that, conv)[0]["trang_thai"] == "cho_duyet"


def test_tu_choi_don_cho_duyet_tra_kho_va_het_han_khong_thi_hanh(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    _che_do(monkeypatch, "auto")
    r = qt.put("/api/ai-uy-quyen", json={"hanh_dong": {"tao_don": {"muc": "co_phe_duyet"}}})
    assert r.status_code == 200, r.text

    kq = _cong_cu(app_that, "tao_don_hang", dict(DON), conv)
    assert kq["tao_duoc"] is True and kq["trang_thai"] == "cho_duyet"
    dx = _de_xuat(app_that, conv)[0]
    assert dx["order_id"] is not None and dx["hanh_dong"] == "tao_don"

    r = qt.post(f"/api/ai-de-xuat/{dx['id']}/tu-choi", json={"ly_do": "khách chưa chắc"})
    assert r.status_code == 200, r.text
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id=$1",
                 dx["order_id"])["trang_thai"] == "da_huy", "từ chối = huỷ đơn giữ hàng"
    sau = _de_xuat(app_that, conv)[0]
    assert sau["trang_thai"] == "tu_choi" and sau["ly_do_tu_choi"] == "khách chưa chắc"

    # Đơn thứ hai (khác số lượng), cho quá hạn rồi bấm Duyệt.
    kq2 = _cong_cu(app_that, "tao_don_hang",
                   {**DON, "items": [{"ten_san_pham": SP["ten"], "so_luong": 2}]}, conv)
    dx2 = [x for x in _de_xuat(app_that, conv) if x["trang_thai"] == "cho_duyet"][0]
    _dong(app_that, "UPDATE ai_de_xuat SET het_han_luc = now() - interval '1 minute' "
          "WHERE id=$1 RETURNING 1", dx2["id"])
    r = qt.post(f"/api/ai-de-xuat/{dx2['id']}/duyet")
    assert r.status_code == 409 and "hết hạn" in r.text
    assert _dong(app_that, "SELECT trang_thai FROM ai_de_xuat WHERE id=$1",
                 dx2["id"])["trang_thai"] == "het_han"
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE ma_don=$1",
                 kq2["ma_don"])["trang_thai"] == "cho_duyet", "hết hạn thì không đụng đơn"
    assert "ai.de_xuat.het_han" in [k for k, _ in _su_kien(app_that, conv)]


def test_duyet_o_man_don_hang_dong_the_de_xuat(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    _che_do(monkeypatch, "auto")
    # Ngưỡng do quản trị đặt trên dashboard (mức Tự động) — đơn 100.000đ vượt.
    assert qt.put("/api/ai-uy-quyen", json={"hanh_dong": {"tao_don": {
        "muc": "tu_dong", "nguong_vnd": 50_000}}}).status_code == 200
    kq = _cong_cu(app_that, "tao_don_hang", dict(DON), conv)
    assert kq["trang_thai"] == "cho_duyet"
    dx = _de_xuat(app_that, conv)[0]
    assert "ngưỡng" in dx["ly_do_can_duyet"]

    r = qt.post(f"/api/orders/{dx['order_id']}/approve")
    assert r.status_code == 200, r.text
    sau = _de_xuat(app_that, conv)[0]
    assert sau["trang_thai"] == "da_thuc_hien" and sau["ket_qua"]["qua"] == "man_don_hang"
    assert qt.post(f"/api/ai-de-xuat/{dx['id']}/duyet").status_code == 409


def test_goi_y_khong_ghi_don_duyet_thi_len_don_kiem_lai(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    _che_do(monkeypatch, "assist")

    kq = _cong_cu(app_that, "tao_don_hang", dict(DON), conv)
    assert kq["tao_duoc"] is False and kq["da_de_xuat"] is True
    assert _dong(app_that, "SELECT count(*) n FROM orders WHERE conversation_id=$1", conv)["n"] == 0
    assert _dong(app_that, "SELECT so_luong FROM ton_kho WHERE ma='SP1'")["so_luong"] == 100, \
        "Gợi ý không giữ hàng"
    dx = _de_xuat(app_that, conv)[0]
    assert dx["che_do_ai"] == "goi_y" and dx["order_id"] is None

    r = qt.post(f"/api/ai-de-xuat/{dx['id']}/duyet")
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    sau = _de_xuat(app_that, conv)[0]
    assert sau["order_id"] is not None and sau["trang_thai"] == "da_thuc_hien"
    assert _dong(app_that, "SELECT trang_thai FROM orders WHERE id=$1",
                 sau["order_id"])["trang_thai"] == "da_chot"


def test_chinh_sach_doi_sang_khong_su_dung_thi_de_xuat_cu_khong_chay(app_that, monkeypatch):
    qt = _quan_tri_vao(app_that)
    _ton(app_that)
    conv = _hoi_thoai(app_that)
    _che_do(monkeypatch, "assist")
    _cong_cu(app_that, "tao_don_hang", dict(DON), conv)
    dx = _de_xuat(app_that, conv)[0]
    assert qt.put("/api/ai-uy-quyen", json={"hanh_dong": {"tao_don": {
        "muc": "khong_su_dung"}}}).status_code == 200
    r = qt.post(f"/api/ai-de-xuat/{dx['id']}/duyet")
    assert r.status_code == 409 and "Không sử dụng" in r.text
    assert _dong(app_that, "SELECT count(*) n FROM orders WHERE conversation_id=$1", conv)["n"] == 0


def test_api_chinh_sach_quyen_va_kiem_het_truoc_khi_ghi(app_that):
    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")
    d = lan.get("/api/ai-uy-quyen")
    assert d.status_code == 200
    muc = {h["ma"]: h for h in d.json()["hanh_dong"]}
    assert muc["tao_don"]["muc"] == "tu_dong" and muc["huy_don"]["muc"] == "co_phe_duyet"
    assert muc["hoan_tien"]["ho_tro"] is False and muc["hoan_tien"]["muc"] == "khong_su_dung"
    assert muc["chuyen_nhan_vien"]["cau_hinh_duoc"] is False

    assert lan.put("/api/ai-uy-quyen", json={"hanh_dong": {
        "huy_don": {"muc": "tu_dong"}}}).status_code == 403

    r = qt.put("/api/ai-uy-quyen", json={"hanh_dong": {
        "huy_don": {"muc": "tu_dong"}, "hoan_tien": {"muc": "tu_dong"}}})
    assert r.status_code == 422
    assert {h["ma"]: h["muc"] for h in qt.get("/api/ai-uy-quyen").json()["hanh_dong"]}[
        "huy_don"] == "co_phe_duyet", "một dòng sai thì không dòng nào được ghi"

    r = qt.put("/api/ai-uy-quyen", json={"hanh_dong": {"huy_don": {"muc": "khong_su_dung"}},
                                         "han_gio": 4})
    assert r.status_code == 200, r.text
    assert r.json()["han_gio"] == 4
    ev = _dong(app_that, "SELECT detail FROM events WHERE kind='ai.uy_quyen.sua' "
               "ORDER BY id DESC LIMIT 1")["detail"]
    assert ev["muc_truoc"] == "co_phe_duyet" and ev["muc_sau"] == "khong_su_dung"
