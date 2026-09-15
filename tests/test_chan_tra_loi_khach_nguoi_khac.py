"""
Mức tầm nhìn phải chặn Ở MÁY CHỦ, không chỉ khoá nút trên màn hình.

LỖ HỔNG ĐÃ ĐO (15.09.2026)
--------------------------
`pham_vi.duoc_tra_loi()` có từ lâu và đúng, nhưng chỉ được gọi ở MỘT chỗ:
`agent/api/contacts.py` — để vẽ một cái cờ cho giao diện biết nên khoá nút
Gửi hay không. KHÔNG đường gửi tin nào hỏi tới nó.

Nghĩa là mức `chi_doc` ("đọc được, không trả lời được") và `an_noi_dung`
chỉ là một lớp sơn: ai gọi thẳng `POST /api/conversations/{id}/send` vẫn
nhắn được cho khách của người khác. `docs/van-hanh.md` thì hứa "nút gửi bị
khoá", nên chủ shop tin rằng khách đã giao được bảo vệ.

Tìm ra đúng lúc chủ dự án vừa bật mức `chi_doc` để đạt yêu cầu "giao khách
cho ai thì chỉ người đó đảm nhiệm". Nếu không vá, cấu hình vừa bật ấy không
bảo vệ gì cả — và không có gì đỏ để ai nhận ra.

BA ĐƯỜNG GỬI TIN, CẢ BA PHẢI CHẶN
  POST /api/conversations/{id}/send        gửi chữ
  POST /api/conversations/{id}/send-file   gửi ảnh, tệp
  POST /api/messages/{id}/approve          duyệt bản nháp của agent
Chặn một đường mà để hở đường kia là không chặn gì cả.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql, _them_thanh_vien,
)

TIN = {"text": "Dạ em xin phép trả lời chị ạ"}


def _dung_canh(app, qt, tk: str):
    """Một khách của `lan`, một hội thoại của khách ấy, và `minh` đứng ngoài."""
    _khach_nhan(app, tk, "Chị Hoa", "Shop còn hàng không?")
    cid = qt.get("/api/contacts").json()[0]["id"]
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app, tk, lan_id)
    _them_thanh_vien(app, tk, minh_id)
    assert qt.put(f"/api/contacts/{cid}/chu-so-huu",
                  json={"owner_user_id": lan_id, "ly_do": "Phân công"}).status_code == 200

    from agent import db

    async def doc():
        d = await db.fetchrow("SELECT id FROM conversations WHERE contact_id = $1::uuid", cid)
        return str(d["id"])
    return cid, _sql(app, doc), lan, minh


def test_muc_chi_doc_CHAN_gui_tin_cho_khach_nguoi_khac(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _cid, conv, lan, minh = _dung_canh(app_that, qt, tk)
    assert qt.put("/api/tam-nhin-khach", json={"muc": "chi_doc"}).status_code == 200

    r = minh.post(f"/api/conversations/{conv}/send", json=TIN)
    assert r.status_code == 403, r.text
    assert "đã giao cho người khác" in r.text

    # Chủ của khách thì vẫn gửi được — chặn nhầm cả chủ là làm hỏng việc.
    assert lan.post(f"/api/conversations/{conv}/send", json=TIN).status_code == 200


def test_chan_ca_duong_gui_ANH(app_that):
    """Gửi ảnh cho khách của người khác cũng là trả lời khách ấy."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _cid, conv, _lan, minh = _dung_canh(app_that, qt, tk)
    assert qt.put("/api/tam-nhin-khach", json={"muc": "chi_doc"}).status_code == 200

    r = minh.post(f"/api/conversations/{conv}/send-file", data={"ma_san_pham": "AS-CL01"})
    assert r.status_code == 403, r.text


def test_muc_tat_thi_khong_chan_ai(app_that):
    """Mặc định xuất xưởng: giao khách chỉ để ghi nhận, không hạn chế ai."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _cid, conv, _lan, minh = _dung_canh(app_that, qt, tk)
    assert qt.put("/api/tam-nhin-khach", json={"muc": "tat"}).status_code == 200

    assert minh.post(f"/api/conversations/{conv}/send", json=TIN).status_code == 200


def test_khach_chua_giao_van_la_cua_chung(app_that):
    """Bỏ vế này là khách mới nhắn tới không ai trả lời được — im lặng."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Khách mới", "alo shop")
    uid, nv = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, uid)
    assert qt.put("/api/tam-nhin-khach", json={"muc": "chi_doc"}).status_code == 200

    from agent import db

    async def doc():
        d = await db.fetchrow(
            "SELECT cv.id FROM conversations cv JOIN contacts ct ON ct.id = cv.contact_id "
            "WHERE ct.display_name = 'Khách mới'")
        return str(d["id"])
    conv = _sql(app_that, doc)

    assert nv.post(f"/api/conversations/{conv}/send", json=TIN).status_code == 200


def test_quan_tri_khong_bi_chan(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _cid, conv, _lan, _minh = _dung_canh(app_that, qt, tk)
    assert qt.put("/api/tam-nhin-khach", json={"muc": "chi_doc"}).status_code == 200

    assert qt.post(f"/api/conversations/{conv}/send", json=TIN).status_code == 200


def test_chot_dat_o_MOT_cho_dung_chung():
    """
    Ba route cùng gọi một hàm, thay vì mỗi route tự nhớ kiểm. Chép ba bản
    là bảo đảm sẽ có một bản quên — và bản quên không nổ, nó chỉ cho qua.
    """
    nguon = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert nguon.count("await chan_neu_khong_duoc_tra_loi(") == 3
    assert "async def chan_neu_khong_duoc_tra_loi(" in nguon
