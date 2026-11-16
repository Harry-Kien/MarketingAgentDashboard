"""
Kiểm thử Handover Protocol của Messenger. Không gọi API, không cần CSDL.

VẤN ĐỀ NÓ GIẢI QUYẾT
--------------------
Với ZaloCRM và Chatwoot, "chuyển người" là một cờ trong CSDL của ta:
`status='escalated'` thì agent im. Đủ dùng, vì nhân viên làm việc trong
dashboard này.

Messenger thì khác: nhân viên có thể mở **Facebook Page Inbox** hoặc Meta
Business Suite trên điện thoại và trả lời khách trực tiếp ở đó. Hệ thống
này không hề hay biết. Agent vẫn tưởng mình phụ trách, khách nhắn tiếp là
nó trả lời tiếp — HAI GIỌNG NÓI cùng lúc với một khách hàng, và không có
gì trên màn hình nói ra điều đó.

`pass_thread_control` đẩy ranh giới xuống tầng Meta: sau khi trao quyền,
tin của khách không còn về `messaging[]` mà sang `standby[]`. Agent im vì
NỀN TẢNG không cho nó nói, không phải vì một cờ trong CSDL còn nhớ. Ranh
giới cưỡng chế được luôn đáng tin hơn ranh giới tự canh.

CHIỀU NGƯỢC LẠI CÒN DỄ SAI HƠN
------------------------------
Nhân viên bấm "Xong" trong Page Inbox thì Meta trả quyền về. Không nghe sự
kiện ấy thì hội thoại nằm `escalated` vĩnh viễn: nhân viên tưởng đã xong,
agent tưởng vẫn có người phụ trách, khách nhắn không ai trả lời. Cả hai bên
đều tin bên kia đang lo — và đó là cách khách bị bỏ rơi mà không ai sai.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.channels import messenger as ms  # noqa: E402


def _ad() -> ms.MessengerAdapter:
    return ms.MessengerAdapter()


def _tin(text="alo shop ơi", mid="m1", sender="u1"):
    return {"sender": {"id": sender}, "recipient": {"id": "page1"},
            "timestamp": 1735689600000, "message": {"mid": mid, "text": text}}


# =====================================================================
#  standby — tin khách gửi TRONG LÚC người thật đang phụ trách
# =====================================================================

def test_doc_duoc_tin_trong_standby():
    """
    Không đọc mảng này thì hồ sơ khách đứt một đoạn: suốt thời gian nhân
    viên trả lời trong Page Inbox, hệ thống không biết khách đã nói gì. Lần
    sau agent nhận lại việc, nó thiếu đúng khúc giữa — và hỏi lại những
    điều khách vừa kể cho người kia.
    """
    lo = {"object": "page", "entry": [{"standby": [_tin("em hỏi thêm ạ")]}]}
    ds = _ad().parse_nhieu(lo)
    assert len(ds) == 1
    assert ds[0].text == "em hỏi thêm ạ"


def test_tin_standby_MANG_CO_de_agent_khong_tra_loi():
    """
    Chỗ dễ sai nhất của Handover Protocol: đọc được tin rồi tưởng mình còn
    quyền, thế là hai giọng cùng nói với một khách.
    """
    lo = {"object": "page", "entry": [{"standby": [_tin()]}]}
    assert _ad().parse_nhieu(lo)[0].meta.get("standby") is True


def test_tin_thuong_KHONG_mang_co_standby():
    """Vế còn lại: gắn cờ nhầm cho tin thường thì agent câm hoàn toàn."""
    lo = {"object": "page", "entry": [{"messaging": [_tin()]}]}
    assert _ad().parse_nhieu(lo)[0].meta.get("standby") is not True


def test_lo_tron_ca_messaging_lan_standby():
    """Meta gộp được cả hai trong một entry."""
    lo = {"object": "page", "entry": [{
        "messaging": [_tin("tin thường", "m1")],
        "standby": [_tin("tin standby", "m2")],
    }]}
    ds = _ad().parse_nhieu(lo)
    assert {m.text: m.meta.get("standby") for m in ds} == {
        "tin thường": None, "tin standby": True,
    }


def test_luong_xu_ly_LUU_tin_standby_roi_moi_dung():
    """
    Thứ tự trong `handle_inbound` quyết định đúng/sai: chặn TRƯỚC khi lưu
    thì tin khách biến mất, đúng loại lỗi nghiêm trọng nhất repo từng có.
    Phải lưu xong rồi mới thoát.
    """
    from agent.omnichannel import xu_ly_tin_vao
    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    vi_tri_luu = src.index("_ingest_inbound(msg)")
    vi_tri_chan = src.index('.get("standby")')
    assert vi_tri_luu < vi_tri_chan, "chặn standby trước khi lưu -> mất tin khách"


def test_tin_standby_ep_hoi_thoai_sang_escalated():
    """
    Quyền có thể bị app khác giành, không đi qua đường chuyển người của ta.
    Lúc đó đây là lần DUY NHẤT hệ thống biết được điều đó.
    """
    from agent.omnichannel import xu_ly_tin_vao
    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    khoi = src[src.index('.get("standby")'):][:400]
    assert "escalated" in khoi


# =====================================================================
#  Trao quyền đi
# =====================================================================

def test_chuyen_nguoi_trao_quyen_cho_hop_thu_page():
    src = inspect.getsource(ms.MessengerAdapter.bao_chuyen_nguoi)
    assert "pass_thread_control" in src
    assert "APP_HOP_THU_PAGE" in src


def test_id_hop_thu_page_dung_hang_so_cua_meta():
    """
    Con số này do Meta đặt và giống nhau ở mọi Page trên thế giới. Ai đó
    tưởng nó là id của mình rồi sửa thành Page ID là bàn giao trao vào hư
    không — và hỏng im lặng, vì API vẫn trả 200.
    """
    assert ms.APP_HOP_THU_PAGE == "263902037430900"


def test_kem_ly_do_de_nhan_vien_khong_phai_doc_lai_ca_hoi_thoai():
    src = inspect.getsource(ms.MessengerAdapter.bao_chuyen_nguoi)
    assert "metadata" in src and "ly_do" in src


def test_trao_quyen_hong_thi_bao_len_tren():
    """
    `bao_nhan_vien_tiep_quan` trong main.py bắt và ghi
    `escalate.bao_kenh_that_bai`. Nuốt ở đây thì hàng chờ rò rỉ mà nhật ký
    sạch trơn.
    """
    src = inspect.getsource(ms.MessengerAdapter.bao_chuyen_nguoi)
    assert "raise" in src


# =====================================================================
#  Nhận quyền lại — chiều dễ bỏ quên
# =====================================================================

def test_doc_duoc_su_kien_tra_quyen_ve_cho_ta(monkeypatch):
    from agent.config import settings
    monkeypatch.setattr(settings, "messenger_app_id", "999")
    lo = {"object": "page", "entry": [{"messaging": [{
        "sender": {"id": "u1"},
        "pass_thread_control": {"new_owner_app_id": "999",
                                "previous_owner_app_id": ms.APP_HOP_THU_PAGE},
    }]}]}
    bg = _ad().doc_ban_giao(lo)
    assert len(bg) == 1
    assert bg[0]["khach"] == "u1"
    assert bg[0]["ve_tay_ta"] is True


def test_trao_cho_app_KHAC_khong_bi_hieu_la_ve_tay_ta(monkeypatch):
    """
    So bằng app id CỦA TA, không phải "khác Page Inbox". Một Page có thể
    gắn nhiều app, và trao cho app thứ ba không có nghĩa là ta được nhận
    lại — hiểu nhầm chỗ này là agent chen vào lúc app khác đang phụ trách.
    """
    from agent.config import settings
    monkeypatch.setattr(settings, "messenger_app_id", "999")
    lo = {"object": "page", "entry": [{"messaging": [{
        "sender": {"id": "u1"},
        "pass_thread_control": {"new_owner_app_id": "12345"},
    }]}]}
    assert _ad().doc_ban_giao(lo)[0]["ve_tay_ta"] is False


def test_chua_dat_app_id_thi_khong_bao_gio_tuong_la_ve_tay_ta(monkeypatch):
    """Cấu hình thiếu thì đoán bừa là agent chen ngang khi người đang nói."""
    from agent.config import settings
    monkeypatch.setattr(settings, "messenger_app_id", "")
    lo = {"object": "page", "entry": [{"messaging": [{
        "sender": {"id": "u1"},
        "pass_thread_control": {"new_owner_app_id": ""},
    }]}]}
    assert _ad().doc_ban_giao(lo)[0]["ve_tay_ta"] is False


def test_take_va_request_thread_control_cung_duoc_ghi_nhan():
    lo = {"object": "page", "entry": [{"messaging": [
        {"sender": {"id": "u1"}, "take_thread_control": {}},
        {"sender": {"id": "u2"}, "request_thread_control": {}},
    ]}]}
    loai = [b["loai"] for b in _ad().doc_ban_giao(lo)]
    assert loai == ["take_thread_control", "request_thread_control"]


def test_tin_thuong_khong_bi_doc_thanh_su_kien_ban_giao():
    assert _ad().doc_ban_giao(
        {"object": "page", "entry": [{"messaging": [_tin()]}]}) == []


def test_webhook_xu_ly_ban_giao_TRUOC_tin_nhan():
    """
    Cùng một lô vừa báo "quyền về tay ta" vừa mang tin mới thì tin ấy phải
    được agent trả lời, chứ không rơi vào nhánh `escalated` của trạng thái
    cũ. Thứ tự quyết định điều đó.
    """
    from agent import main as app_main
    src = inspect.getsource(app_main.webhook_messenger)
    assert src.index("doc_ban_giao") < src.index("parse_nhieu")


def test_nhan_lai_quyen_thi_mo_khoa_hoi_thoai():
    from agent import main as app_main
    src = inspect.getsource(app_main._ban_giao_messenger)
    assert "ve_tay_ta" in src and "'auto'" in src


# =====================================================================
#  Nút "Trả lại cho agent" phải giành quyền THẬT
# =====================================================================

def test_release_giu_lai_quyen_tu_meta_chu_khong_chi_doi_co():
    """
    Đổi cờ trong CSDL thôi thì tin khách vẫn đi vào `standby[]` — agent bật
    mà câm, và trên màn hình nó trông như đang chạy.
    """
    from agent.api import routes
    src = inspect.getsource(routes.release)
    assert "nhan_lai_quyen_sau_release(" in src
    assert "nhan_lai_quyen" in inspect.getsource(_buoc_meta())


def _buoc_meta():
    from agent.api import hoi_thoai_cu
    return hoi_thoai_cu.nhan_lai_quyen_sau_release


def test_release_hong_thi_noi_that_chu_khong_bao_ok_suong():
    from agent.api import routes
    assert "ghi_chu" in inspect.getsource(routes.release)
    assert "banGiao.nhan_lai_that_bai" in inspect.getsource(_buoc_meta())


def test_release_khong_no_voi_kenh_khong_co_ban_giao():
    """ZaloCRM và Chatwoot không có `nhan_lai_quyen`. `getattr` phải đỡ."""
    assert "getattr(ad" in inspect.getsource(_buoc_meta())


# ---------------------------------------------------------------------
#  Đường release MỚI (/api/inbox/.../release) — đường nút dashboard gọi
# ---------------------------------------------------------------------
#
# ĐO ĐƯỢC 16.11.2026: chỉ route cũ làm bước giành quyền. Nút "Kết thúc tiếp
# quản" đi đường inbox mới, nên với Messenger agent bật trong CSDL mà tin
# khách vẫn vào `standby[]` — bật mà câm. Ba test trên chỉ soi route cũ nên
# vẫn xanh suốt thời gian đó.

class _KqMeta:
    def __init__(self, ok, detail=""):
        self.ok, self.detail = ok, detail


def _gia_lap_meta(monkeypatch, *, kenh="messenger", kq=None, no=None):
    from agent import db
    from agent.api import hoi_thoai_cu

    goi, nhat_ky = [], []

    async def lay(external_id):
        goi.append(external_id)
        if no:
            raise no
        return kq

    class Ad:
        nhan_lai_quyen = staticmethod(lay)

    async def get_for_account(_tk):
        return Ad()

    async def fetchrow(_sql, *_a):
        return {"account_id": "tk", "channel": kenh, "external_id": "psid-1"}

    async def log_event(ten, **k):
        nhat_ky.append(ten)

    monkeypatch.setattr(hoi_thoai_cu.channels, "get_for_account", get_for_account)
    monkeypatch.setattr(db, "fetchrow", fetchrow)
    monkeypatch.setattr(db, "log_event", log_event)
    return goi, nhat_ky


def _release_moi():
    """Gọi thẳng hàm route inbox với dịch vụ định tuyến giả (release thành công)."""
    import asyncio
    from uuid import uuid4

    from agent.api import inbox
    from agent.omnichannel.routing import ConversationRoutingState

    cid = uuid4()

    class DichVu:
        async def release(self, **_k):
            return ConversationRoutingState(
                conversation_id=cid, mode="assist", status="assist",
                assigned_to=None, assigned_team_id=None, version=3)

    return asyncio.run(inbox.release_conversation(
        cid, inbox.ReleaseIn(expected_version=2, reason="Nhân viên kết thúc"),
        user={"id": str(uuid4()), "quyen": ["hoi_thoai.nhan"]},
        service=DichVu(),
        # Đúng thứ dependency mặc định trả về — cái app thật dùng.
        gianh_quyen=inbox.get_buoc_gianh_quyen_meta()))


def test_release_moi_mac_dinh_dung_buoc_gianh_quyen_that():
    """Dependency là chỗ test thay được; mặc định PHẢI là bước thật."""
    from agent.api import inbox
    assert inbox.get_buoc_gianh_quyen_meta() is _buoc_meta()


def test_release_moi_gianh_lai_quyen_meta(monkeypatch):
    goi, _ = _gia_lap_meta(monkeypatch, kq=_KqMeta(True))
    kq = _release_moi()
    assert goi == ["psid-1"], "đường release mới không xin lại thread control"
    assert "ghi_chu" not in kq and kq["mode"] == "assist"


def test_release_moi_meta_tu_choi_thi_tra_ghi_chu(monkeypatch):
    _, nhat_ky = _gia_lap_meta(monkeypatch, kq=_KqMeta(False, "(#10) quyền bị thu"))
    kq = _release_moi()
    assert "chưa giành lại được quyền" in kq["ghi_chu"]
    assert "(#10)" in kq["ghi_chu"]
    assert nhat_ky == ["banGiao.nhan_lai_that_bai"]


def test_release_moi_loi_mang_khong_thanh_500(monkeypatch):
    """CSDL đã release xong; ngoại lệ từ Meta phải thành ghi_chu, không nổ."""
    _gia_lap_meta(monkeypatch, no=TimeoutError("hết giờ"))
    kq = _release_moi()
    assert "TimeoutError" in kq["ghi_chu"]


def test_release_moi_kenh_khac_khong_goi_meta(monkeypatch):
    goi, _ = _gia_lap_meta(monkeypatch, kenh="zalo_personal", kq=_KqMeta(True))
    kq = _release_moi()
    assert goi == [] and "ghi_chu" not in kq
