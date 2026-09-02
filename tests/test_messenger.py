"""
Kiểm thử adapter Facebook Messenger (nối thẳng Meta Graph API).

Kênh này CHƯA chạy với API thật — chưa có Page token. Test dùng payload giả,
nên XANH KHÔNG CÓ NGHĨA LÀ KÊNH CHẠY ĐƯỢC; nó chỉ có nghĩa là logic của ta
không sai. Tên trường và đường dẫn Graph API phải đối chiếu lại khi có
tài khoản.

Bốn chỗ Messenger khác mọi kênh khác trong repo, và cả bốn đều hỏng theo
kiểu im lặng nếu làm sai — nên phần lớn ca ở đây canh đúng chúng:

  1. MỘT POST mang NHIỀU tin  -> lấy một là đánh rơi phần còn lại
  2. Tin vọng (`is_echo`)     -> không lọc là agent trả lời chính nó, vô hạn
  3. Chữ ký HMAC trên thân THÔ -> parse rồi dumps lại là không bao giờ khớp
  4. Cửa sổ 24 giờ            -> ngoài cửa sổ Meta từ chối, tin bay vào hư không
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent.channels import messenger as ms  # noqa: E402
from agent.channels import registry  # noqa: E402
from agent.channels.base import ChannelAdapter  # noqa: E402
from agent.config import settings  # noqa: E402


def _ad() -> ms.MessengerAdapter:
    return ms.MessengerAdapter()


def test_verify_page_connection_tra_identity_ma_khong_gui_tin():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer page-token"
        return httpx.Response(200, json={"id": "page-77", "name": "CSKH"})

    client = httpx.AsyncClient(
        base_url="https://graph.example/v1",
        transport=httpx.MockTransport(handler),
    )
    adapter = ms.MessengerAdapter(
        account_id=uuid4(),
        credentials={"access_token": "page-token", "app_secret": "secret", "external_account_id": "pending:x"},
        client=client,
    )

    check = asyncio.run(adapter.verify_connection())

    assert check.ok is True
    assert check.external_account_id == "page-77"
    asyncio.run(adapter.aclose())


def _su_kien(text="giá bao nhiêu ạ", mid="m1", echo=False, dinh_kem=None, sender="u1"):
    tin = {"mid": mid}
    if text:
        tin["text"] = text
    if echo:
        tin["is_echo"] = True
    if dinh_kem:
        tin["attachments"] = dinh_kem
    return {"sender": {"id": sender}, "recipient": {"id": "page1"},
            "timestamp": 1735689600000, "message": tin}


def _lo(*su_kien):
    return {"object": "page", "entry": [{"id": "page1", "messaging": list(su_kien)}]}


# =====================================================================
#  Hợp đồng
# =====================================================================

def test_tuan_thu_hop_dong_va_dang_ky():
    assert issubclass(ms.MessengerAdapter, ChannelAdapter)
    assert _ad().name == "messenger"
    assert "messenger" in registry.tat_ca()
    assert registry.get("messenger").name == "messenger"


def test_thieu_khoa_thi_khong_bat(monkeypatch):
    """
    ÉP RỖNG bằng monkeypatch, KHÔNG đọc `.env` thật.

    Bản đầu của ca này chỉ gọi `cau_hinh_du()` rồi tin rằng kênh chưa cấu
    hình — đúng trên bản clone sạch, sai ngay khi máy đã điền khoá. Đó là
    lỗi "xanh chỗ này đỏ chỗ kia" quen thuộc, chỉ đảo chiều: xanh trên máy
    trống, đỏ trên máy thật. Test phải nói về HÀNH VI CỦA MÃ, không nói về
    cấu hình của người đang chạy nó.
    """
    monkeypatch.setattr(settings, "messenger_page_token", "")
    monkeypatch.setattr(settings, "messenger_app_secret", "")
    assert _ad().cau_hinh_du() is False


def test_du_khoa_thi_bat(monkeypatch):
    """Vế còn lại — siết quá tay thì kênh không bao giờ bật được."""
    monkeypatch.setattr(settings, "messenger_page_token", "tok")
    monkeypatch.setattr(settings, "messenger_app_secret", "sec")
    assert _ad().cau_hinh_du() is True
    assert "messenger" in registry.dang_bat()


def test_thieu_khoa_thi_gui_tra_ly_do_chu_khong_no(monkeypatch):
    monkeypatch.setattr(settings, "messenger_page_token", "")
    monkeypatch.setattr(settings, "messenger_app_secret", "")
    kq = asyncio.run(_ad().send_text("u1", "xin chào"))
    assert kq.ok is False and "chưa cấu hình" in kq.detail


# =====================================================================
#  ① Một POST mang nhiều tin
# =====================================================================

def test_MOT_POST_NHIEU_TIN_KHONG_DUOC_ROI():
    """
    Khách gõ ba tin liên tiếp thì Meta gói cả ba vào một request. Lấy một
    tin nghĩa là hai tin sau biến mất: không lỗi, không nhật ký, không ai
    biết.
    """
    lo = _lo(_su_kien("tin một", "m1"),
             _su_kien("tin hai", "m2"),
             _su_kien("tin ba", "m3"))
    ds = _ad().parse_nhieu(lo)
    assert len(ds) == 3
    assert [m.text for m in ds] == ["tin một", "tin hai", "tin ba"]


def test_nhieu_entry_cung_duoc_duyet_het():
    """Meta gộp cả nhiều `entry` khi lưu lượng cao."""
    lo = {"object": "page", "entry": [
        {"id": "p", "messaging": [_su_kien("a", "m1")]},
        {"id": "p", "messaging": [_su_kien("b", "m2")]},
    ]}
    assert len(_ad().parse_nhieu(lo)) == 2


def test_duong_webhook_dung_parse_nhieu_chu_khong_parse():
    """
    Ca này canh chỗ nối, không canh adapter. Đường webhook gọi `parse()` thì
    adapter có đúng đến mấy tin vẫn rơi.
    """
    import inspect

    from agent import main as app_main
    src = inspect.getsource(app_main.webhook_messenger)
    assert "parse_nhieu" in src
    chung = inspect.getsource(app_main.webhook)
    assert "parse_nhieu" in chung, "đường webhook chung cũng phải nhận được lô"


def test_object_khac_page_thi_bo_qua():
    """Instagram và WhatsApp đi `object` khác — không phải kênh này."""
    assert _ad().parse_nhieu({"object": "instagram", "entry": []}) == []


# =====================================================================
#  ② Tin vọng — vòng lặp vô hạn nếu bỏ sót
# =====================================================================

def test_TIN_VONG_BI_LOC():
    """
    Meta đẩy lại chính tin Page vừa gửi. Không lọc thì agent đọc câu trả
    lời của mình như tin khách, trả lời tiếp, rồi lại nhận vọng — vòng lặp
    vô hạn, và mỗi vòng đều tính tiền.
    """
    assert _ad().parse_nhieu(_lo(_su_kien("câu agent vừa gửi", echo=True))) == []


def test_tin_vong_lan_trong_lo_khong_lam_roi_tin_that():
    """Lô trộn: lọc đúng cái vọng, giữ nguyên cái thật."""
    ds = _ad().parse_nhieu(_lo(
        _su_kien("agent nói", "m1", echo=True),
        _su_kien("khách nói", "m2"),
    ))
    assert [m.text for m in ds] == ["khách nói"]


def test_su_kien_khong_phai_tin_thi_bo_qua():
    """`delivery`, `read`, `postback` — không phải tin nhắn."""
    for k in ("delivery", "read", "postback"):
        assert _ad().parse_nhieu(
            {"object": "page", "entry": [{"messaging": [{"sender": {"id": "u1"}, k: {}}]}]}
        ) == []


# =====================================================================
#  Tin chỉ có ảnh — lỗi nghiêm trọng nhất từng có trong repo
# =====================================================================

def test_TIN_CHI_CO_ANH_KHONG_BI_DANH_ROI():
    ds = _ad().parse_nhieu(_lo(_su_kien(
        text="", dinh_kem=[{"type": "image",
                            "payload": {"url": "https://cdn.fb/a.jpg"}}])))
    assert len(ds) == 1, "tin chỉ có ảnh bị đánh rơi"
    assert ds[0].text == ""
    assert ds[0].attachments[0]["url"] == "https://cdn.fb/a.jpg"


def test_dinh_kem_dung_hinh_dang_dashboard_dang_ve():
    ds = _ad().parse_nhieu(_lo(_su_kien(
        text="", dinh_kem=[{"type": "image", "payload": {"url": "https://x/a.jpg"}}])))
    a = ds[0].attachments[0]
    assert set(a) >= {"loai", "url"} and a["loai"] == "image"


def test_su_kien_rong_that_thi_bo_qua():
    assert _ad().parse_nhieu(_lo(_su_kien(text=""))) == []


def test_gan_nhan_nen_tang_de_dashboard_ve_dung_huy_hieu():
    m = _ad().parse_nhieu(_lo(_su_kien()))[0]
    # `dashboard/app.js` tra NEN_TANG_LABEL bằng chuỗi viết thường này.
    assert m.meta["nen_tang_goc"] == "facebookpage"


# =====================================================================
#  ③ Chữ ký HMAC
# =====================================================================

def _ky(than: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), than, hashlib.sha256).hexdigest()


def test_chu_ky_dung_thi_qua(monkeypatch):
    monkeypatch.setattr(settings, "messenger_app_secret", "bimat")
    than = json.dumps({"object": "page"}).encode()
    assert ms.kiem_chu_ky(than, _ky(than, "bimat")) is True


def test_chu_ky_sai_thi_chan(monkeypatch):
    monkeypatch.setattr(settings, "messenger_app_secret", "bimat")
    than = b'{"object":"page"}'
    assert ms.kiem_chu_ky(than, _ky(than, "secret-khac")) is False
    assert ms.kiem_chu_ky(than, "") is False


def test_THIEU_APP_SECRET_THI_CHAN_CHU_KHONG_BO_QUA(monkeypatch):
    """
    Bỏ qua phép kiểm khi thiếu khoá là để ngỏ: bất kỳ ai biết địa chỉ
    webhook đều bơm được tin giả vào hộp thư cửa hàng, và agent sẽ trả lời
    chúng như tin thật.
    """
    monkeypatch.setattr(settings, "messenger_app_secret", "")
    than = b'{"object":"page"}'
    assert ms.kiem_chu_ky(than, _ky(than, "bat_ky")) is False


def test_ky_tren_than_THO_chu_khong_phai_dict_da_parse(monkeypatch):
    """
    Chỗ mọi hiện thực webhook Meta sai ít nhất một lần: `json.dumps()` lại
    cho ra chuỗi khác về khoảng trắng, và HMAC không bao giờ khớp.
    """
    monkeypatch.setattr(settings, "messenger_app_secret", "bimat")
    tho = b'{"object": "page",  "entry": []}'          # có khoảng trắng thừa
    assert ms.kiem_chu_ky(tho, _ky(tho, "bimat")) is True
    dumps_lai = json.dumps(json.loads(tho)).encode()
    assert dumps_lai != tho
    assert ms.kiem_chu_ky(tho, _ky(dumps_lai, "bimat")) is False


def test_bat_tay_doi_lai_hub_challenge(monkeypatch):
    monkeypatch.setattr(settings, "messenger_verify_token", "tok")
    p = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "12345"}
    assert ms.tra_loi_xac_minh(p) == "12345"


def test_bat_tay_sai_token_thi_khong_doi(monkeypatch):
    monkeypatch.setattr(settings, "messenger_verify_token", "tok")
    assert ms.tra_loi_xac_minh(
        {"hub.mode": "subscribe", "hub.verify_token": "sai", "hub.challenge": "1"}
    ) is None


def test_bat_tay_khi_chua_dat_verify_token_thi_khong_doi(monkeypatch):
    """Chưa cấu hình mà vẫn dội lại là cho người lạ nối Page của họ vào."""
    monkeypatch.setattr(settings, "messenger_verify_token", "")
    assert ms.tra_loi_xac_minh(
        {"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}
    ) is None


def test_duong_messenger_dang_ky_TRUOC_duong_webhook_chung():
    """
    Thứ tự route quyết định đúng/sai ở đây. `/webhook/{kenh}` khớp cả
    `/webhook/messenger`; đăng ký nó trước thì Meta bị chốt WEBHOOK_SECRET
    chung chặn và không bao giờ tới được phép kiểm chữ ký.
    """
    from agent import main as app_main
    duong = [getattr(r, "path", "") for r in app_main.app.routes
             if "webhook" in getattr(r, "path", "")]
    assert duong.index("/webhook/messenger") < duong.index("/webhook/{kenh}")


# =====================================================================
#  ④ Cửa sổ 24 giờ — dùng chung một bản với Zalo OA
# =====================================================================

def test_dung_chung_ham_cua_so_voi_zalo_oa():
    """
    Hai kênh cùng một luật, hai con số. Viết hai bản là tự tạo lại lỗi
    hai-nhánh-song-sinh đã phải đi sửa ở `agent/main.py`.
    """
    import inspect
    for lop in (ms.MessengerAdapter, __import__(
            "agent.channels.zalo_oa", fromlist=["x"]).ZaloOAAdapter):
        assert "con_trong_cua_so" in inspect.getsource(lop.can_send_now)


def test_cua_so_mac_dinh_la_24_gio():
    assert settings.messenger_cua_so_gio == 24.0


# =====================================================================
#  Đọc kết quả Graph API
# =====================================================================

def _rep(status=200, body=None):
    return httpx.Response(status, json=body or {},
                          request=httpx.Request("POST", "https://x"))


def test_graph_bao_loi_trong_than_la_that_bai():
    """Graph API không phải lúc nào cũng kèm mã HTTP >= 400."""
    kq = ms._doc_ket_qua(_rep(200, {"error": {"code": 10, "message": "outside window"}}))
    assert kq.ok is False and "10" in kq.detail and "window" in kq.detail


def test_khong_co_error_la_thanh_cong():
    delivery = ms._doc_ket_qua(_rep(200, {"message_id": "m1"}))
    assert delivery.ok is True
    assert delivery.provider_message_id == "m1"


def test_http_loi_van_la_that_bai():
    assert ms._doc_ket_qua(_rep(500, {})).ok is False


def test_than_khong_phai_json_thi_that_bai():
    r = httpx.Response(200, text="<html>", request=httpx.Request("POST", "https://x"))
    assert ms._doc_ket_qua(r).ok is False


def test_co_dau_dang_go_that():
    """Messenger có `sender_action` thật — khác ZaloCRM vốn không hỗ trợ."""
    import inspect
    src = inspect.getsource(ms.MessengerAdapter.bao_dang_go)
    assert "typing_on" in src and "typing_off" in src
