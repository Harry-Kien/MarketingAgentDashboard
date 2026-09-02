"""
Kiểm thử adapter Zalo OA. Không gọi API, không cần CSDL.

Kênh này CHƯA chạy với API thật — chưa có Official Account. Nên bộ test ở
đây canh đúng những thứ canh được mà không cần khoá:

  * hợp đồng `ChannelAdapter` được tuân thủ đủ
  * kênh TẮT khi thiếu khoá, và tắt một cách im lặng có chủ ý
  * bộ đọc webhook không đánh rơi tin chỉ có ảnh
  * lỗi nghiệp vụ của Zalo (HTTP 200 kèm `error != 0`) không bị đọc thành
    thành công
  * cửa sổ gửi đo từ tin của KHÁCH

Cái nó KHÔNG canh được, và phải kiểm tay khi có tài khoản thật: tên trường
trong payload thật, đường dẫn API, độ dài cửa sổ. Test xanh ở đây KHÔNG có
nghĩa là kênh chạy được — nó chỉ có nghĩa là phần logic của ta không sai.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from agent.channels import registry  # noqa: E402
from agent.channels.base import ChannelAdapter  # noqa: E402
from agent.channels.zalo_oa import ZaloOAAdapter, _doc_ket_qua, _thoi_diem  # noqa: E402


def _ad() -> ZaloOAAdapter:
    return ZaloOAAdapter()


def _tin(su_kien="user_send_text", text="cho em hỏi giá", dinh_kem=None):
    tin = {"msg_id": "m1"}
    if text:
        tin["text"] = text
    if dinh_kem:
        tin["attachments"] = dinh_kem
    return {
        "event_name": su_kien,
        "sender": {"id": "u123"},
        "recipient": {"id": "oa1"},
        "message": tin,
        "timestamp": "1735689600000",
    }


# =====================================================================
#  Hợp đồng kênh
# =====================================================================

def test_tuan_thu_du_hop_dong_channeladapter():
    assert issubclass(ZaloOAAdapter, ChannelAdapter)
    # Khởi tạo được nghĩa là không còn @abstractmethod nào chưa hiện thực.
    assert _ad().name == "zalo_oa"


def test_da_dang_ky_de_webhook_ton_tai_san():
    """
    `/webhook/{kenh}` tra adapter qua registry. Không đăng ký thì đường
    `/webhook/zalo_oa` rơi về ZaloCRM và tin OA bị hiểu sai hoàn toàn.
    """
    assert "zalo_oa" in registry.tat_ca()
    assert registry.get("zalo_oa").name == "zalo_oa"


def test_thieu_khoa_thi_KHONG_bat():
    """Dựng sẵn mà tự bật là kênh chết chạy trong bóng tối."""
    assert _ad().cau_hinh_du() is False
    assert "zalo_oa" not in registry.dang_bat()


def test_thieu_khoa_thi_gui_tra_ve_ly_do_chu_khong_no():
    kq = asyncio.run(_ad().send_text("u123", "xin chào"))
    assert kq.ok is False
    assert "chưa cấu hình" in kq.detail


# =====================================================================
#  Bộ đọc webhook — chỗ đã từng đánh rơi tin trong im lặng
# =====================================================================

def test_doc_duoc_tin_van_ban():
    m = _ad().parse(_tin())
    assert m is not None
    assert m.channel == "zalo_oa"
    assert m.text == "cho em hỏi giá"
    assert m.customer_ref == "u123"
    assert m.dedupe_key == "zalo_oa:m1"


def test_TIN_CHI_CO_ANH_KHONG_BI_DANH_ROI():
    """
    Ca quan trọng nhất file này.

    Lỗi nghiêm trọng nhất từng tìm ra trong repo là bộ đọc webhook lặng lẽ
    bỏ tin chỉ có ảnh: khách gửi ảnh vùng da, tin biến mất hoàn toàn, không
    ai trả lời và không có gì báo. Adapter mới không được lặp lại.
    """
    p = _tin(su_kien="user_send_image", text="",
             dinh_kem=[{"type": "image",
                        "payload": {"url": "https://cdn.zalo/anh.jpg"}}])
    m = _ad().parse(p)
    assert m is not None, "tin chỉ có ảnh bị đánh rơi"
    assert m.text == ""
    assert len(m.attachments) == 1
    assert m.attachments[0]["url"] == "https://cdn.zalo/anh.jpg"


def test_dinh_kem_dung_hinh_dang_dashboard_dang_ve():
    """`dashboard/app.js` đọc `loai` và `url`. Kênh trả khác là ảnh vỡ."""
    p = _tin(su_kien="user_send_image", text="",
             dinh_kem=[{"type": "image", "payload": {"url": "https://x/a.jpg"}}])
    a = _ad().parse(p).attachments[0]
    assert set(a) >= {"loai", "url"}
    assert a["loai"] == "image"


def test_su_kien_khong_phai_tin_thi_bo_qua():
    """OA đẩy cả sự kiện theo dõi, bỏ theo dõi, đã xem — không phải tin."""
    for su_kien in ("follow", "unfollow", "user_seen_message", ""):
        assert _ad().parse(_tin(su_kien=su_kien)) is None


def test_thieu_id_nguoi_gui_thi_bo_qua():
    p = _tin()
    p["sender"] = {}
    assert _ad().parse(p) is None


def test_su_kien_rong_that_thi_bo_qua():
    """Không chữ, không đính kèm — khác hẳn với 'chỉ có ảnh'."""
    assert _ad().parse(_tin(text="")) is None


def test_thoi_diem_doc_dung_mili_giay():
    t = _thoi_diem("1735689600000")
    assert t.year == 2025 and t.tzinfo is not None
    # Rác thì lùi về 'bây giờ', không nổ giữa luồng webhook.
    assert _thoi_diem("rác").tzinfo is not None
    assert _thoi_diem(None).tzinfo is not None


# =====================================================================
#  Zalo trả HTTP 200 kèm lỗi — xanh giả kinh điển của API này
# =====================================================================

def _rep(status=200, body=None):
    return httpx.Response(status, json=body if body is not None else {},
                          request=httpx.Request("POST", "https://x"))


def test_error_khac_khong_la_THAT_BAI_du_http_200():
    """
    Chỉ nhìn mã HTTP là coi mọi lỗi nghiệp vụ — hết hạn mức, ngoài cửa sổ,
    sai user_id — thành thành công. Tin không tới, dashboard vẫn xanh.
    """
    kq = _doc_ket_qua(_rep(200, {"error": -216, "message": "User is out of window"}))
    assert kq.ok is False
    assert "-216" in kq.detail
    assert "window" in kq.detail


def test_error_bang_khong_la_thanh_cong():
    delivery = _doc_ket_qua(
        _rep(200, {"error": 0, "message": "Success", "data": {"message_id": "z1"}})
    )
    assert delivery.ok is True
    assert delivery.provider_message_id == "z1"


def test_khong_co_truong_error_van_coi_la_thanh_cong():
    """Một số endpoint trả 200 rỗng. Coi đó là hỏng thì ghi nhật ký giả."""
    assert _doc_ket_qua(_rep(200, {})).ok is True


def test_verify_oa_lay_token_va_doc_oa_id():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "oa-token", "refresh_token": "new-refresh", "expires_in": 3600})
        assert request.url.path.endswith("/getoa")
        assert request.headers["access_token"] == "oa-token"
        return httpx.Response(200, json={"error": 0, "data": {"oa_id": "oa-42", "name": "OA CSKH"}})

    client = httpx.AsyncClient(
        base_url="https://openapi.example/v3/oa",
        transport=httpx.MockTransport(handler),
    )
    adapter = ZaloOAAdapter(
        account_id=__import__("uuid").uuid4(),
        credentials={"app_id": "app", "secret_key": "secret", "refresh_token": "refresh"},
        client=client,
    )

    check = asyncio.run(adapter.verify_connection())

    assert check.ok is True
    assert check.external_account_id == "oa-42"
    asyncio.run(adapter.aclose())


def test_http_loi_van_la_that_bai():
    assert _doc_ket_qua(_rep(500, {"error": 0})).ok is False


def test_than_khong_phai_json_thi_that_bai():
    r = httpx.Response(200, text="<html>gateway</html>",
                       request=httpx.Request("POST", "https://x"))
    assert _doc_ket_qua(r).ok is False


# =====================================================================
#  Cửa sổ gửi
# =====================================================================

def _gia_lap_tin_cuoi(monkeypatch, luc):
    async def fetchrow(_sql, *_a):
        return {"lan_cuoi": luc}
    from agent import db
    monkeypatch.setattr(db, "fetchrow", fetchrow)


def test_trong_cua_so_thi_gui_duoc(monkeypatch):
    _gia_lap_tin_cuoi(monkeypatch, datetime.now(timezone.utc) - timedelta(hours=2))
    assert asyncio.run(_ad().can_send_now("u123")) is True


def test_ngoai_cua_so_thi_khong_gui(monkeypatch):
    _gia_lap_tin_cuoi(monkeypatch, datetime.now(timezone.utc) - timedelta(days=30))
    assert asyncio.run(_ad().can_send_now("u123")) is False


def test_khach_chua_tung_nhan_thi_khong_gui(monkeypatch):
    """Chưa có tin nào của khách nghĩa là chưa có cửa sổ nào mở."""
    _gia_lap_tin_cuoi(monkeypatch, None)
    assert asyncio.run(_ad().can_send_now("u123")) is False


def test_csdl_hong_thi_KHONG_doan_bua_la_gui_duoc(monkeypatch):
    """
    Chặn nhầm một tin gửi được thì người trực thấy `escalate.khong_gui_duoc`
    trong nhật ký và nhắn tay. Đoán bừa True thì tin bay vào hư không và
    không ai biết — im lặng luôn là hướng sai.
    """
    async def no(*_a, **_k):
        raise RuntimeError("mất kết nối CSDL")
    from agent import db
    monkeypatch.setattr(db, "fetchrow", no)
    assert asyncio.run(_ad().can_send_now("u123")) is False


def test_dat_cua_so_bang_khong_thi_tat_phep_kiem(monkeypatch):
    from agent.config import settings
    monkeypatch.setattr(settings, "zalo_oa_cua_so_gio", 0)
    assert asyncio.run(_ad().can_send_now("u123")) is True


# =====================================================================
#  Token xoay vòng — thứ không bổ sung được về sau
# =====================================================================

def test_co_bang_luu_refresh_token_trong_schema():
    """
    Refresh token của Zalo xoay vòng mỗi lần đổi. Không có chỗ bền để ghi
    thì sau lần khởi động lại đầu tiên, adapter cầm một token đã chết và
    kênh ngừng gửi trong im lặng.
    """
    sql = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS zalo_oa_token" in sql
    assert "refresh_token" in sql


def test_ghi_de_refresh_token_moi_khi_zalo_tra_ve():
    import inspect
    src = inspect.getsource(ZaloOAAdapter._lay_token)
    assert "_luu_refresh" in src, "không ghi lại refresh token mới = kênh chết sau 1 giờ"


def test_token_rong_thi_no_chu_khong_ghi_de():
    """Zalo trả HTTP 200 kèm thân lỗi. Coi 200 là thành công ở đây nghĩa là
    ghi một token rỗng đè lên token đang chạy."""
    import inspect
    src = inspect.getsource(ZaloOAAdapter._lay_token)
    assert "raise RuntimeError" in src
