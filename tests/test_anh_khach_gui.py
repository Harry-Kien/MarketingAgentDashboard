"""
Kiểm thử ảnh khách gửi. Không gọi API, không cần CSDL.

LỖI FILE NÀY SINH RA ĐỂ CANH
----------------------------
Bộ đọc webhook Chatwoot từng có đúng ba dòng này:

    text = payload.get("content")
    if not isinstance(text, str) or not text.strip():
        return None      # ảnh, file, tin hệ thống — chưa xử lý

Chú thích nói "chưa xử lý". Thực tế là BIẾN MẤT: khách gửi ảnh không kèm
chữ thì không tạo hội thoại, không vào CSDL, không một dòng nhật ký nào.
Hệ thống không hề biết tin đó từng tồn tại, và khách ngồi chờ một câu trả
lời sẽ không bao giờ tới.

Trớ trêu là đúng những khách cần giúp nhất lại gửi kiểu đó — người ta chụp
chỗ da đang nổi mụn thay vì tả bằng lời.

Đây là kiểu hỏng tệ nhất trong cả hệ thống: im lặng, không dấu vết, và chỉ
lộ ra khi có người tình cờ đối chiếu hộp thư Chatwoot với dashboard.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import main as app_main  # noqa: E402
from agent.channels.chatwoot import ChatwootAdapter  # noqa: E402


def _tin(noi_dung=None, dinh_kem=None) -> dict:
    return {
        "event": "message_created",
        "message_type": "incoming",
        "id": 991,
        "content": noi_dung,
        "attachments": dinh_kem or [],
        "created_at": "2026-08-21T10:00:00Z",
        "conversation": {"id": 42, "channel": "Channel::FacebookPage"},
        "sender": {"id": 7, "name": "Chị Lan"},
    }


def _anh(url="http://localhost:3200/rails/active_storage/blobs/abc/da.jpg"):
    return {"id": 1, "file_type": "image", "data_url": url,
            "thumb_url": url + "?thumb=1"}


# =====================================================================
#  Không bao giờ đánh rơi tin nữa
# =====================================================================

def test_anh_khong_kem_chu_van_phai_vao_he_thong():
    """Ca gốc của lỗi. Trả None ở đây là khách biến mất."""
    m = ChatwootAdapter().parse(_tin(dinh_kem=[_anh()]))
    assert m is not None
    assert len(m.attachments) == 1


def test_anh_kem_chu_giu_ca_hai():
    m = ChatwootAdapter().parse(_tin("cái này còn hàng không ạ", [_anh()]))
    assert m.text == "cái này còn hàng không ạ"
    assert len(m.attachments) == 1


def test_nhieu_anh_giu_du():
    m = ChatwootAdapter().parse(_tin(dinh_kem=[_anh("http://h/a.jpg"),
                                               _anh("http://h/b.jpg")]))
    assert len(m.attachments) == 2


def test_tin_rong_that_su_van_bo():
    """
    Nới cho ảnh không có nghĩa là nhận mọi thứ. Tin không chữ không file là
    sự kiện vòng đời của Chatwoot, nhận vào chỉ tạo hội thoại rác.
    """
    assert ChatwootAdapter().parse(_tin()) is None
    assert ChatwootAdapter().parse(_tin("   ")) is None


def test_van_bo_tin_di_va_su_kien_khac():
    """Nhận tin của chính mình là agent tự trả lời mình, vòng lặp vô tận."""
    ra = _tin("xin chào", [_anh()])
    ra["message_type"] = "outgoing"
    assert ChatwootAdapter().parse(ra) is None

    ra2 = _tin("xin chào", [_anh()])
    ra2["event"] = "conversation_updated"
    assert ChatwootAdapter().parse(ra2) is None


def test_dinh_kem_hong_khong_lam_no():
    """Payload lạ không được làm sập bộ đọc webhook — mất luôn cả tin
    bình thường của mọi khách khác."""
    m = ChatwootAdapter().parse(_tin("có chữ", ["chuoi-la", {}, None,
                                                {"file_type": "image"}]))
    assert m is not None
    assert m.attachments == []


# =====================================================================
#  Đường dẫn đi qua proxy, không trỏ thẳng vào Chatwoot
# =====================================================================

def test_duong_dan_anh_di_qua_proxy():
    """
    `data_url` của Chatwoot đòi phiên đăng nhập CỦA CHATWOOT. Nhét thẳng
    vào dashboard thì người trực thấy ô ảnh vỡ, trừ khi tình cờ cũng đang
    đăng nhập Chatwoot ở tab khác.
    """
    m = ChatwootAdapter().parse(_tin(dinh_kem=[_anh()]))
    assert m.attachments[0]["url"].startswith("/tich-hop/chatwoot/")
    assert "rails/active_storage" in m.attachments[0]["url"]


def test_giu_lai_duong_dan_goc():
    """Để còn lần ra khi ảnh không hiện — không có nó thì chỉ biết là
    hỏng, không biết hỏng ở khâu nào."""
    m = ChatwootAdapter().parse(_tin(dinh_kem=[_anh()]))
    assert m.attachments[0]["goc"].startswith("http://localhost:3200/")


# =====================================================================
#  Ảnh không kèm chữ -> chuyển người, không đoán
# =====================================================================

def test_anh_khong_kem_chu_thi_chuyen_nguoi():
    """
    Người ta chụp chỗ da đang có vấn đề thay vì tả bằng lời. Nhìn ảnh da
    rồi khuyên dùng gì chính là CHẨN ĐOÁN — đúng việc mà prompt đã cấm và
    `_bat_buoc_chuyen` đã chặn khi khách mô tả bằng CHỮ.

    Chặn chữ mà bỏ lọt ảnh thì chốt tuân thủ chỉ là hình thức: khách nào
    gửi ảnh là đi vòng qua được.
    """
    src = inspect.getsource(app_main.handle_inbound)
    assert "msg.attachments and not msg.text.strip()" in src


def test_chuyen_nguoi_vi_anh_van_bao_cho_khach():
    """
    Nhánh này thoát sớm, không đi qua đoạn báo chuyển người ở cuối hàm.
    Quên gọi thì khách gửi ảnh xong nhận lại đúng sự im lặng — vẫn bị bỏ
    rơi, chỉ khác là nay có bản ghi để sau này truy ra.
    """
    src = inspect.getsource(app_main.handle_inbound)
    truoc_return = src.split("msg.attachments and not msg.text.strip()")[1]
    assert "adapter_bao_nguoi" in truoc_return.split("history = await")[0]


def test_bao_nguoi_cham_ca_hai_phia():
    """Nhân viên cần ghi chú trong hộp thư của kênh; khách cần một câu."""
    src = inspect.getsource(app_main.adapter_bao_nguoi)
    assert "bao_nhan_vien_tiep_quan" in src
    assert "bao_khach_dang_chuyen_nguoi" in src


def test_nhanh_anh_dung_CHUNG_duong_bao_voi_nhanh_chu():
    """
    Ca này canh đúng cái lỗi đã xảy ra, chứ không canh một dòng chữ.

    Hai nhánh — tin có chữ và tin CHỈ CÓ ẢNH — từng tự viết lấy đoạn báo
    chuyển người. Nhánh có chữ được sửa để ghi nhật ký khi gửi hỏng; nhánh
    ảnh thì không, và nó nằm im với `suppress(Exception)` câm. Bản sao ít
    người đọc hơn luôn là bản mục trước.

    Chừng nào cả hai còn gọi CÙNG một hàm thì lỗi ấy không tái phát được.
    Tách ra lần nữa là ca này đỏ.
    """
    anh = inspect.getsource(app_main.adapter_bao_nguoi)
    chu = inspect.getsource(app_main.handle_inbound)
    for ham in ("bao_nhan_vien_tiep_quan", "bao_khach_dang_chuyen_nguoi"):
        assert ham in anh and ham in chu, f"{ham} không dùng chung cho cả hai nhánh"
    # Và không nhánh nào được tự gọi thẳng xuống adapter nữa.
    assert "adapter.send_text" not in anh
    assert "adapter.bao_chuyen_nguoi" not in anh


def test_cau_bao_van_theo_gio_lam_viec():
    """Ngoài giờ thì không được hứa 'sẽ nhắn lại sớm' ở đây nữa."""
    src = inspect.getsource(app_main.bao_khach_dang_chuyen_nguoi)
    assert "gio_lam_viec.tin_chuyen_nguoi()" in src


def test_nhanh_anh_khong_con_nuot_loi_im_lang():
    """
    `suppress(Exception)` ở nhánh này nghĩa là: khách gửi ảnh, câu báo gửi
    hỏng, khách nhận lại đúng sự im lặng mà docstring của hàm nói là phải
    tránh — và không ai biết.
    """
    src = inspect.getsource(app_main.adapter_bao_nguoi)
    assert "suppress(Exception)" not in src


# =====================================================================
#  Ảnh kèm chữ: agent phải BIẾT là có ảnh
# =====================================================================

def test_agent_duoc_bao_la_co_anh():
    """
    Không nói thì agent trả lời câu chữ như thể ảnh không tồn tại — khách
    gửi ảnh kèm "cái này còn hàng không ạ?" mà nhận về "mình muốn hỏi sản
    phẩm nào ạ?".
    """
    src = inspect.getsource(app_main.handle_inbound)
    assert "khách gửi kèm" in src


def test_anh_duoc_luu_vao_csdl():
    """Không lưu thì dashboard không hiện được, và người trực vào sau
    không biết khách từng gửi gì."""
    from agent.omnichannel.inbox_service import PostgresInboxTransaction

    ingest = inspect.getsource(app_main._ingest_inbound)
    normalized = inspect.getsource(PostgresInboxTransaction.insert_attachment)
    assert "InboxService" in ingest
    assert "INSERT INTO attachments" in normalized
