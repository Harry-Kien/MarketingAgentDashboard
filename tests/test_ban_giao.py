"""
Kiểm thử bàn giao cho người. Không gọi API.

Bàn giao là chỗ agent và người gặp nhau, và cũng là chỗ dễ hỏng nhất trong
im lặng: agent ghi "đã chuyển người" vào CSDL của mình rồi coi như xong,
trong khi nhân viên đang làm việc trong hộp thư của kênh KHÔNG THẤY GÌ.
Hội thoại trông như đã xử lý, khách ngồi chờ, không ai biết.

Bàn giao chỉ là bàn giao khi CẢ HAI bên nhìn thấy:
  nhân viên  ghi chú nội bộ nói rõ vì sao, nhãn để lọc, hội thoại mở lại
  khách      một câu báo, để không ngồi im không biết ai đã thấy tin mình
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import main as app_main  # noqa: E402
from agent.channels.base import ChannelAdapter, Delivery  # noqa: E402
from agent.core import gio_lam_viec  # noqa: E402
from agent.channels.chatwoot import NHAN_CHO_NGUOI, ChatwootAdapter  # noqa: E402
from agent.channels.zalocrm import ZaloCRMAdapter  # noqa: E402
from agent.config import settings  # noqa: E402


# =====================================================================
#  Hợp đồng: kênh nào không hỗ trợ thì im lặng, không nổ
# =====================================================================

def test_moi_kenh_deu_co_hai_ham_ban_giao():
    for lop in (ChannelAdapter, ChatwootAdapter, ZaloCRMAdapter):
        assert hasattr(lop, "bao_chuyen_nguoi")
        assert hasattr(lop, "bao_dang_go")


def test_kenh_khong_ho_tro_thi_khong_no():
    """
    ZaloCRM không có endpoint nào cho việc này — Public API của nó không hỗ
    trợ. Mặc định phải là không làm gì, không phải ném lỗi, nếu không một
    kênh thiếu tính năng sẽ làm hỏng cả luồng xử lý tin.
    """
    import asyncio
    a = ZaloCRMAdapter()
    assert asyncio.run(a.bao_chuyen_nguoi("x", "y")) is None
    assert asyncio.run(a.bao_dang_go("x", True)) is None


# =====================================================================
#  Ba dấu hiệu phía nhân viên
# =====================================================================

def test_ghi_chu_phai_la_rieng_tu():
    """
    Ghi chú nói vì sao agent dừng. Khách KHÔNG được thấy nó — họ không cần
    đọc lý do kỹ thuật, và có lý do nghe như hệ thống đang trục trặc.
    """
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert '"private": True' in src


def test_ghi_chu_noi_ro_vi_sao_va_kem_tom_tat():
    """
    Nhân viên tiếp quản phải biết ngay vì sao, không phải đọc lại cả hội
    thoại để đoán.
    """
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert "[Agent chuyển người]" in src
    assert "tom_tat" in src


def test_gan_nhan_de_loc_duoc_hang_cho():
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert "/labels" in src and "NHAN_CHO_NGUOI" in src
    assert NHAN_CHO_NGUOI == "can-nguoi-ho-tro"


def test_mo_lai_hoi_thoai():
    """
    Chatwoot tự đóng hội thoại khi agent trả lời xong. Không mở lại thì nó
    nằm ở tab "đã xử lý" và không ai ngó tới.
    """
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert "toggle_status" in src and '"status": "open"' in src


def test_khong_tu_gan_cho_mot_nhan_vien_cu_the():
    """
    Gán sai người thì việc nằm im trong hàng của người đang nghỉ. Để hàng
    chờ chung, ai rảnh nhận — cách một tổ chăm sóc khách hàng thật vận hành.
    """
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert "assignments" not in src


def test_moi_loi_goi_deu_duoc_boc_loi_rieng():
    """
    Ba lời gọi độc lập. Gắn nhãn hỏng không được ngăn việc mở lại hội thoại
    — mất một dấu hiệu còn hơn mất cả ba.
    """
    src = inspect.getsource(ChatwootAdapter.bao_chuyen_nguoi)
    assert src.count("with suppress(httpx.HTTPError):") == 3


# =====================================================================
#  Phía khách
# =====================================================================

class _KenhGia:
    """Adapter giả, ghi lại đã gửi gì thay vì gọi ra ngoài."""

    def __init__(self, gui_duoc=True, ket_qua=None, no=None):
        self.gui_duoc = gui_duoc
        self.ket_qua = ket_qua if ket_qua is not None else Delivery(True)
        self.no = no
        self.da_gui: list[str] = []
        self.da_bao_kenh: list[tuple] = []

    async def can_send_now(self, _ref):
        return self.gui_duoc

    async def send_text(self, _ref, text):
        if self.no:
            raise self.no
        self.da_gui.append(text)
        return self.ket_qua

    async def bao_chuyen_nguoi(self, ref, ly_do, tom_tat=""):
        if self.no:
            raise self.no
        self.da_bao_kenh.append((ref, ly_do, tom_tat))


def _bat_nhat_ky(monkeypatch) -> list[tuple]:
    """Giữ lại `log_event` thay vì gọi CSDL — test này không cần Postgres."""
    ghi: list[tuple] = []

    async def gia(kind, **kw):
        ghi.append((kind, kw))

    monkeypatch.setattr(app_main.db, "log_event", gia)
    return ghi


def test_khach_duoc_bao_khi_chuyen_nguoi(monkeypatch):
    """Chuyển người mà không nói gì là để khách ngồi im, không biết có ai
    thấy tin của mình chưa."""
    _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia()
    da_queue = []

    async def queue(_cid, text):
        da_queue.append(text)

    monkeypatch.setattr(app_main, "_queue_handover_notice", queue)
    asyncio.run(app_main.bao_khach_dang_chuyen_nguoi(kenh, "c1", None))
    assert da_queue, "không xếp câu báo khách vào outbox"
    assert not kenh.da_gui, "đã gọi provider trước khi outbox commit"


def test_cau_bao_la_co_dinh_khong_phai_loi_model(monkeypatch):
    """
    Lúc chuyển người là lúc agent đã tự nhận không đủ thẩm quyền — đó chính
    là lúc KHÔNG nên để nó tự chọn chữ. Câu cố định không thể chứa lời
    khuyên, không thể hứa gì, không thể vi phạm quảng cáo.

    Đây là ca ĐO HÀNH VI chứ không soi văn bản mã nữa. Bản cũ cắt chuỗi
    `inspect.getsource` rồi tìm chữ trong đó — nó đỏ ngay khi hai nhánh
    trùng lặp được gộp về một hàm, dù hành vi tốt lên chứ không xấu đi. Một
    test vỡ vì dọn dẹp là test dạy người ta đừng dọn dẹp.
    """
    _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia()
    da_queue = []

    async def queue(_cid, text):
        da_queue.append(text)

    monkeypatch.setattr(app_main, "_queue_handover_notice", queue)
    asyncio.run(app_main.bao_khach_dang_chuyen_nguoi(kenh, "c1", None))
    # Chuỗi gửi đi phải là MỘT TRONG hai câu cố định của cấu hình.
    assert da_queue[0] in (settings.tin_chuyen_nguoi,
                           gio_lam_viec.tin_chuyen_nguoi())


def test_gui_hong_thi_phai_de_lai_dau_vet(monkeypatch):
    """
    Thất bại của kênh về bằng GIÁ TRỊ, không bằng ngoại lệ: `send_text` bắt
    `httpx.HTTPError` rồi trả `Delivery(False)`, và HTTP 500 cũng vậy. Chỉ
    bọc `try/except` là hụt đúng con đường hay hỏng nhất.
    """
    ghi = _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia(ket_qua=Delivery(False, "500 Internal Server Error"))

    async def queue(_cid, _text):
        raise RuntimeError("500 Internal Server Error")

    monkeypatch.setattr(app_main, "_queue_handover_notice", queue)
    asyncio.run(app_main.bao_khach_dang_chuyen_nguoi(kenh, "c1", None))

    loai = [k for k, _ in ghi]
    assert "escalate.bao_that_bai" in loai, "gửi hỏng mà không ai biết"
    ly_do = [kw.get("ly_do", "") for k, kw in ghi if k == "escalate.bao_that_bai"][0]
    # Dấu vết RỖNG cũng gần như không có dấu vết. Bản cũ đọc `kq.error`
    # trong khi `Delivery` chỉ có `ok` và `detail`, nên nhật ký luôn ghi
    # một lý do trống — có bản ghi mà không có manh mối.
    assert ly_do, "ghi nhật ký nhưng lý do trống"
    assert "500" in ly_do


def test_kenh_no_thi_khong_lam_sap_luong(monkeypatch):
    ghi = _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia(no=RuntimeError("mạng đứt"))
    asyncio.run(app_main.bao_khach_dang_chuyen_nguoi(kenh, "c1", None))
    assert "escalate.bao_that_bai" in [k for k, _ in ghi]


def test_ngoai_cua_so_gui_thi_van_ghi_nhat_ky(monkeypatch):
    """Không gửi được vì hết cửa sổ 24h cũng là khách không nhận được gì."""
    ghi = _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia(gui_duoc=False)
    asyncio.run(app_main.bao_khach_dang_chuyen_nguoi(kenh, "c1", None))
    assert not kenh.da_gui
    assert "escalate.khong_gui_duoc" in [k for k, _ in ghi]


def test_bao_nhan_vien_hong_cung_phai_keu(monkeypatch):
    """Hàng chờ rò rỉ là chuyện lớn, không phải chi tiết trang trí."""
    ghi = _bat_nhat_ky(monkeypatch)
    kenh = _KenhGia(no=RuntimeError("chatwoot sập"))
    asyncio.run(app_main.bao_nhan_vien_tiep_quan(kenh, "c1", None, "vượt thẩm quyền"))
    assert "escalate.bao_kenh_that_bai" in [k for k, _ in ghi]


def test_cau_bao_khong_hua_hen_gi():
    from agent.publish.service import kiem_tra_tuan_thu
    assert not kiem_tra_tuan_thu(settings.tin_chuyen_nguoi)
    thap = settings.tin_chuyen_nguoi.lower()
    for cam in ("phút", "giờ", "ngay lập tức", "chắc chắn"):
        assert cam not in thap, f"câu báo đang hứa {cam!r} — không giữ được"


def test_chi_bao_o_che_do_auto():
    """
    Chế độ assist thì người duyệt mọi thứ. Tự gửi thêm một câu là đi ngược
    ý nghĩa của chế độ đó.
    """
    src = inspect.getsource(app_main.handle_inbound)
    assert 'reply.escalate and runtime.mode() == "auto"' in src


# =====================================================================
#  Đang gõ
# =====================================================================

def test_bat_va_tat_dang_go():
    src = inspect.getsource(app_main.handle_inbound)
    assert "bao_dang_go(msg.conversation_ref, True)" in src
    assert "bao_dang_go(msg.conversation_ref, False)" in src


def test_tat_dang_go_nam_trong_finally():
    """Agent lỗi giữa chừng thì dấu 'đang gõ' vẫn phải tắt, không quay mãi."""
    src = inspect.getsource(app_main.handle_inbound)
    sau_finally = src.split("finally:", 1)[1][:300]
    assert "bao_dang_go(msg.conversation_ref, False)" in sau_finally
