"""
Bình luận Facebook vào inbox, ẩn bình luận có SĐT, trả lời riêng — không gọi mạng.

Ở VN đây là tính năng bắt buộc (Pancake, Haravan, Sapo đều có): khách hỏi
giá dưới bài đăng, để lại số điện thoại công khai, và đối thủ vào chép số.

Ba ràng buộc canh ở đây:
1. Bình luận của CHÍNH Trang (Trang trả lời công khai) không thành tin khách.
2. Mỗi bình luận một hội thoại `cmt:<comment_id>` — Meta chỉ cho trả lời
   riêng MỘT lần cho mỗi bình luận, nên tin thứ hai bị chặn ở API (409) thay
   vì vào outbox rồi chết.
3. Ẩn bình luận có SĐT chỉ khi cửa hàng BẬT, và lỗi Graph không bị nuốt.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from agent.channels import binh_luan_meta as blm
from agent.channels.base import Delivery
from agent.channels.messenger import MessengerAdapter

TRANG = "111222333"


def _payload(*, tu=("999", "Chị Hoa"), loi="Giá bao nhiêu shop?", verb="add",
             item="comment", cmt="555_777"):
    return {"object": "page", "entry": [{"id": TRANG, "time": 1760000000, "changes": [{
        "field": "feed", "value": {
            "from": {"id": tu[0], "name": tu[1]}, "post_id": f"{TRANG}_555",
            "comment_id": cmt, "created_time": 1760000000, "item": item,
            "parent_id": f"{TRANG}_555", "verb": verb, "message": loi}}]}]}


def _adapter() -> MessengerAdapter:
    ad = MessengerAdapter.__new__(MessengerAdapter)
    ad.account_id = uuid.uuid4()
    ad._page_id = TRANG
    return ad


def test_binh_luan_thanh_tin_khach():
    ds = blm.doc_binh_luan(_payload(), _adapter())
    assert len(ds) == 1
    m = ds[0]
    assert m.conversation_ref == "cmt:555_777"
    assert m.customer_ref == "999" and m.customer_name == "Chị Hoa"
    assert m.text == "Giá bao nhiêu shop?"
    assert m.meta["loai"] == "binh_luan" and m.meta["comment_id"] == "555_777"
    assert m.dedupe_key.endswith("cmt:555_777")


@pytest.mark.parametrize("kw", [
    dict(tu=(TRANG, "Trang")),          # Trang tự trả lời công khai
    dict(verb="remove"),                # bình luận bị xoá
    dict(verb="edited"),                # sửa — không tạo tin mới
    dict(item="reaction"),              # thả cảm xúc
    dict(loi=""),                       # bình luận chỉ có sticker/ảnh: không có chữ
])
def test_khong_phai_binh_luan_moi_cua_khach(kw):
    assert blm.doc_binh_luan(_payload(**kw), _adapter()) == []


@pytest.mark.parametrize("loi", [
    "0912345678", "sdt 0912 345 678 nhé", "+84912345678", "gọi 091.234.5678",
    "zalo 0387-123-456",
])
def test_nhan_ra_so_dien_thoai(loi):
    assert blm.co_so_dien_thoai(loi)


@pytest.mark.parametrize("loi", [
    "Giá 245000 ạ", "mã đơn AS2510140001", "size 36-38", "1234567", "",
])
def test_khong_nham_so_khac_la_sdt(loi):
    assert not blm.co_so_dien_thoai(loi)


def test_tra_loi_rieng_gui_toi_comment_id():
    ad = _adapter()
    gui = {}

    async def _gui(body):
        gui.update(body)
        return Delivery(True)
    ad.cau_hinh_du = lambda: True
    ad._gui = _gui
    asyncio.run(ad.send_text("cmt:555_777", "Dạ shop inbox chị ạ"))
    assert gui["recipient"] == {"comment_id": "555_777"}
    assert "messaging_type" not in gui or gui["messaging_type"] == "RESPONSE"


def test_tra_loi_rieng_khong_gui_duoc_tep():
    ad = _adapter()
    ad.cau_hinh_du = lambda: True
    kq = asyncio.run(ad.send_file("cmt:555_777", __file__))
    assert not kq.ok and "chữ" in kq.detail


def test_an_binh_luan_goi_graph_va_bao_loi(monkeypatch):
    ad = _adapter()
    goi = []

    class _R:
        def __init__(self, ma): self.status_code = ma
        def json(self): return {"success": self.status_code < 400}

    class _C:
        def __init__(self, ma): self.ma = ma
        async def post(self, url, params=None, data=None):
            goi.append((url, params, data))
            return _R(self.ma)

    ad._page_token = "tok"
    ad._client = _C(200)
    assert asyncio.run(ad.an_binh_luan("555_777")).ok
    assert goi[0][0] == "/555_777" and goi[0][2] == {"is_hidden": "true"}
    ad._client = _C(403)
    assert not asyncio.run(ad.an_binh_luan("555_777")).ok


def test_mot_binh_luan_chi_tra_loi_rieng_mot_lan(monkeypatch):
    from agent.omnichannel import cua_so_gui as cs

    class _Ad:
        name = "messenger"
        account_id = uuid.uuid4()
        async def can_send_now(self, ref): return True

    async def fetchrow(sql, *a):
        if "da_gui" in sql:
            return {"da_gui": 1}
        return {"account_id": uuid.uuid4(), "channel": "messenger", "external_id": "cmt:555_777"}

    async def get_for_account(_):
        return _Ad()
    monkeypatch.setattr(cs.db, "fetchrow", fetchrow)
    monkeypatch.setattr(cs, "get_for_account", get_for_account)
    qd = asyncio.run(cs.xet_tin_nhan_vien(uuid.uuid4()))
    assert not qd.duoc and "một lần" in qd.ly_do


def test_binh_luan_khong_gui_tep(monkeypatch):
    from agent.omnichannel import cua_so_gui as cs

    async def fetchrow(sql, *a):
        if "da_gui" in sql:
            return {"da_gui": 0}
        return {"account_id": uuid.uuid4(), "channel": "messenger", "external_id": "cmt:1_2"}
    monkeypatch.setattr(cs.db, "fetchrow", fetchrow)
    qd = asyncio.run(cs.xet_tin_nhan_vien(uuid.uuid4(), loai="tep"))
    assert not qd.duoc and "chữ" in qd.ly_do


def test_dang_ky_webhook_va_quyen_oauth_du():
    from agent.api import oauth_meta
    from agent.channels import dang_ky_webhook_meta as dk
    assert "feed" in dk.TRUONG_THEO_DOI
    pham_vi = " ".join(getattr(oauth_meta, n) if isinstance(getattr(oauth_meta, n), str)
                       else " ".join(getattr(oauth_meta, n))
                       for n in dir(oauth_meta) if n.isupper()
                       and isinstance(getattr(oauth_meta, n), (str, tuple, list)))
    for q in ("pages_read_engagement", "pages_manage_engagement"):
        assert q in pham_vi, q


# ---------------- nhánh bình luận trong handle_inbound ----------------

@pytest.fixture
def nhanh(monkeypatch):
    from agent.omnichannel import xu_ly_tin_vao
    hop = {"sql": [], "su_kien": [], "an": [], "bat": "bat", "loi": None}

    async def execute(sql, *a):
        hop["sql"].append(sql)

    async def log_event(kind, **kw):
        hop["su_kien"].append(kind)

    class _Ad:
        async def an_binh_luan(self, cmt):
            hop["an"].append(cmt)
            if hop["loi"]:
                raise RuntimeError(hop["loi"])
            return Delivery(True)

    async def get_for_account(_):
        return _Ad()

    monkeypatch.setattr(xu_ly_tin_vao.db, "execute", execute)
    monkeypatch.setattr(xu_ly_tin_vao.db, "log_event", log_event)
    monkeypatch.setattr(xu_ly_tin_vao.cau_hinh_dong, "lay",
                        lambda k: hop["bat"] if k == "AN_BINH_LUAN_CO_SDT" else "")
    monkeypatch.setattr(xu_ly_tin_vao.channels, "get_for_account", get_for_account)
    return xu_ly_tin_vao, hop


def _tin(loi):
    return blm.doc_binh_luan(_payload(loi=loi), _adapter())[0]


def test_binh_luan_chuyen_nguoi_khong_goi_agent(nhanh):
    xu_ly_tin_vao, hop = nhanh
    asyncio.run(xu_ly_tin_vao._xu_ly_binh_luan(_tin("giá bao nhiêu"), uuid.uuid4()))
    assert any("status = 'escalated'" in s for s in hop["sql"])
    assert hop["an"] == []                     # không có SĐT thì không ẩn


def test_co_sdt_va_da_bat_thi_an(nhanh):
    xu_ly_tin_vao, hop = nhanh
    asyncio.run(xu_ly_tin_vao._xu_ly_binh_luan(_tin("ib em 0912 345 678"), uuid.uuid4()))
    assert hop["an"] == ["555_777"] and "binh_luan.da_an" in hop["su_kien"]


def test_tat_thi_khong_an(nhanh):
    xu_ly_tin_vao, hop = nhanh
    hop["bat"] = "tat"
    asyncio.run(xu_ly_tin_vao._xu_ly_binh_luan(_tin("0912345678"), uuid.uuid4()))
    assert hop["an"] == []


def test_an_hong_thi_ghi_canh_bao_khong_nuot(nhanh):
    xu_ly_tin_vao, hop = nhanh
    hop["loi"] = "Graph 403"
    asyncio.run(xu_ly_tin_vao._xu_ly_binh_luan(_tin("0912345678"), uuid.uuid4()))
    assert "binh_luan.an_that_bai" in hop["su_kien"]


def test_kenh_khong_ho_tro_an_thi_bao_ly_do_doc_duoc(nhanh, monkeypatch):
    """
    Bình luận có SĐT tới từ một kênh không ẩn được: phải ghi `an_that_bai`
    với lý do người đọc hiểu, không phải "AttributeError: ...".
    """
    from agent.channels.base import ChannelAdapter

    class _KhongAn(ChannelAdapter):
        name = "kenh_thu"

        def parse(self, payload):
            return None

        async def send_text(self, conversation_ref, text):
            return Delivery(True)

        async def send_file(self, conversation_ref, path, caption=""):
            return Delivery(True)

    mod, hop = nhanh
    chi_tiet: list = []

    async def log_event(kind, **kw):
        hop["su_kien"].append(kind)
        chi_tiet.append(kw.get("chi_tiet"))

    async def get_for_account(_):
        return _KhongAn()

    monkeypatch.setattr(mod.db, "log_event", log_event)
    monkeypatch.setattr(mod.channels, "get_for_account", get_for_account)
    asyncio.run(mod._xu_ly_binh_luan(_tin("0912345678"), uuid.uuid4()))
    assert "binh_luan.an_that_bai" in hop["su_kien"]
    assert "không hỗ trợ ẩn bình luận" in (chi_tiet[-1] or "")
