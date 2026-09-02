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
    from agent import main as app_main
    src = inspect.getsource(app_main.handle_inbound)
    vi_tri_luu = src.index("_ingest_inbound(msg)")
    vi_tri_chan = src.index('.get("standby")')
    assert vi_tri_luu < vi_tri_chan, "chặn standby trước khi lưu -> mất tin khách"


def test_tin_standby_ep_hoi_thoai_sang_escalated():
    """
    Quyền có thể bị app khác giành, không đi qua đường chuyển người của ta.
    Lúc đó đây là lần DUY NHẤT hệ thống biết được điều đó.
    """
    from agent import main as app_main
    src = inspect.getsource(app_main.handle_inbound)
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
    assert "nhan_lai_quyen" in src


def test_release_hong_thi_noi_that_chu_khong_bao_ok_suong():
    from agent.api import routes
    src = inspect.getsource(routes.release)
    assert "ghi_chu" in src
    assert "banGiao.nhan_lai_that_bai" in src


def test_release_khong_no_voi_kenh_khong_co_ban_giao():
    """ZaloCRM và Chatwoot không có `nhan_lai_quyen`. `getattr` phải đỡ."""
    from agent.api import routes
    src = inspect.getsource(routes.release)
    assert "getattr(ad" in src
