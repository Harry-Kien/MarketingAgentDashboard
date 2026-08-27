"""
Agent nhìn được ảnh khách gửi — và KHÔNG được chẩn đoán bệnh khi nhìn.

VÌ SAO HAI VIỆC NÀY NẰM CHUNG MỘT FILE
---------------------------------------
Chúng phải đi cùng nhau. Bật thị giác mà không có lưới thứ sáu là mở đúng
cánh cửa nguy hiểm nhất của một cửa hàng mỹ phẩm.

`_bat_buoc_chuyen` chỉ đọc CHỮ. Khách gửi ảnh vùng da viêm mà không kèm chữ
nào thì không từ khoá nào nổ. Trước đây điều đó vô hại — agent không nhìn
được ảnh nên không có gì để chẩn đoán. Bật thị giác lên là model NHÌN THẤY
vùng da đỏ, và câu trả lời tự nhiên nhất của nó là gọi tên bệnh.

Gọi tên bệnh cho một người cụ thể là hành nghề y không phép.
"""
from __future__ import annotations

import asyncio
import base64
import inspect

import pytest


# ===============================================================
#  Lọc đính kèm — không chạm mạng
# ===============================================================

def test_chi_lay_anh_bo_qua_thu_khac():
    from agent.core.anh_khach import loc_anh

    ra = loc_anh([
        {"loai": "image", "url": "https://x/a.jpg", "mime_type": "image/jpeg"},
        {"loai": "file", "url": "https://x/b.pdf", "mime_type": "application/pdf"},
        {"loai": "video", "url": "https://x/c.mp4", "mime_type": "video/mp4"},
    ])
    assert [a["url"] for a in ra] == ["https://x/a.jpg"]


def test_chan_duong_dan_khong_phai_http():
    """
    `file://` hay `data:` trong đính kèm là đường đọc file của MÁY CHỦ.

    Bộ đọc webhook không sinh ra chúng, nhưng đính kèm đến từ bên ngoài —
    và một bộ tải chịu đọc `file:///etc/passwd` là lỗ hổng, không phải tiện.
    """
    from agent.core.anh_khach import loc_anh

    for xau in ("file:///etc/passwd", "data:image/png;base64,AAA", "/tmp/x.jpg"):
        assert loc_anh([{"loai": "image", "url": xau}]) == []


def test_cat_bot_khi_khach_gui_ca_album():
    """Mỗi ảnh là một khối token đáng kể; ảnh thứ mười hiếm khi nói thêm gì."""
    from agent.core.anh_khach import TOI_DA_ANH, loc_anh

    nhieu = [{"loai": "image", "url": f"https://x/{i}.jpg"} for i in range(20)]
    assert len(loc_anh(nhieu)) == TOI_DA_ANH


def test_doan_kieu_tu_duoi_ten_khi_thieu_metadata():
    from agent.core.anh_khach import loc_anh

    ra = loc_anh([{"loai": "image", "url": "https://x/anh.PNG"}])
    assert ra[0]["mime"] == "image/png"


# ===============================================================
#  Tải ảnh — có giới hạn, và không bao giờ ném
# ===============================================================

class _R:
    def __init__(self, content=b"", status_code=200, ctype="image/jpeg"):
        self.content = content
        self.status_code = status_code
        self.headers = {"content-type": ctype}


class _Client:
    def __init__(self, tra=None, no=None):
        self.calls = []
        self._tra = tra if tra is not None else _R(b"anh-that")
        self._no = no

    async def get(self, url):
        self.calls.append(url)
        if self._no:
            raise self._no
        return self._tra if not isinstance(self._tra, dict) else self._tra[url]

    async def aclose(self):
        return None


def _chay(attachments, client):
    from agent.core.anh_khach import lay_khoi_anh

    return asyncio.run(lay_khoi_anh(attachments, client=client))


def test_dong_thanh_khoi_dung_dinh_dang_cho_llm():
    """
    Khoá phải khớp `llm._gemini_parts` và `llm._anthropic_content`.

    Sai một tên khoá thì ảnh lặng lẽ bị bỏ qua, và agent trả lời như thể
    khách không gửi gì.
    """
    client = _Client(_R(b"noi-dung-anh"))
    ra = _chay([{"loai": "image", "url": "https://x/a.jpg"}], client)

    assert len(ra) == 1
    assert ra[0]["type"] == "image"
    assert ra[0]["media_type"] == "image/jpeg"
    assert base64.b64decode(ra[0]["data"]) == b"noi-dung-anh"


def test_anh_qua_lon_bi_bo():
    from agent.core.anh_khach import TOI_DA_BYTE

    client = _Client(_R(b"x" * (TOI_DA_BYTE + 1)))
    assert _chay([{"loai": "image", "url": "https://x/a.jpg"}], client) == []


@pytest.mark.parametrize("hong", [
    _R(b"", 200), _R(b"abc", 404), _R(b"abc", 200, "application/pdf"),
])
def test_phan_hoi_hong_thi_bo_anh_do(hong):
    assert _chay([{"loai": "image", "url": "https://x/a.jpg"}], _Client(hong)) == []


def test_mang_hong_KHONG_lam_dut_luot_tra_loi():
    """
    Tin nhắn của khách mới là việc chính. Để một CDN chậm làm đứt cả lượt trả
    lời là đánh đổi sai — cùng nguyên tắc với việc lấy tên khách từ Graph.
    """
    client = _Client(no=RuntimeError("CDN chet"))
    assert _chay([{"loai": "image", "url": "https://x/a.jpg"}], client) == []


def test_mot_anh_hong_khong_chan_anh_con_lai():
    client = _Client({
        "https://x/hong.jpg": _R(b"", 500),
        "https://x/tot.jpg": _R(b"tot"),
    })
    ra = _chay([
        {"loai": "image", "url": "https://x/hong.jpg"},
        {"loai": "image", "url": "https://x/tot.jpg"},
    ], client)
    assert len(ra) == 1
    assert base64.b64decode(ra[0]["data"]) == b"tot"


def test_khong_co_dinh_kem_thi_khong_goi_mang():
    client = _Client()
    assert _chay([], client) == []
    assert client.calls == []


# ===============================================================
#  LƯỚI THỨ SÁU — cấm chẩn đoán
# ===============================================================

@pytest.mark.parametrize("cau", [
    "Dạ da chị bị viêm da cơ địa ạ",
    "Ảnh cho thấy vùng da bị nám nhé",
    "Đây là mụn bọc do nội tiết ạ",
    "Tình trạng này là chàm ạ",
    "Dạ em xem ảnh rồi, da chị bị viêm nang lông ạ",
])
def test_chan_cau_goi_ten_benh(cau):
    from agent.core.agent import _chan_doan_y_te

    assert _chan_doan_y_te(cau), f"lọt: {cau}"


@pytest.mark.parametrize("cau", [
    "Bên em có chính sách đổi trả nếu khách bị dị ứng trong 7 ngày",
    "Trường hợp da bị kích ứng thì chị ngưng dùng và báo em nhé",
    "Sản phẩm này không dùng cho da đang điều trị theo toa bác sĩ",
    "Kem chống nắng giúp hạn chế nám do tia UV",
    "Dạ serum này giá 690.000đ ạ",
    "Bên em gửi chị ảnh sản phẩm nhé",
])
def test_khong_chan_nham_cau_binh_thuong(cau):
    """
    Chặn nhầm câu chính sách thì agent chuyển người mỗi lần đọc chính sách
    của chính shop — và người trực sẽ tắt lưới đi sau vài ngày.
    """
    from agent.core.agent import _chan_doan_y_te

    assert _chan_doan_y_te(cau) is None, f"chặn nhầm: {cau}"


def test_khong_dua_em_vao_chu_ngu():
    """
    Trong lời ăn tiếng nói CSKH của người Việt, "em" là CHÍNH NHÂN VIÊN chứ
    không phải khách: "bên em có chính sách...", "em gửi chị ảnh".
    """
    from agent.core import agent as brain

    mau = brain._CHAN_DOAN_RE.pattern
    assert "|em|" not in mau


def test_luoi_duoc_GAN_vao_duong_chay():
    """Có hàm mà không ai gọi là mã chết — đã gặp ba lần trong dự án này."""
    from agent.core import agent as brain

    assert "_chan_doan_y_te" in inspect.getsource(brain.respond)


# ===============================================================
#  Nối vào đường chạy
# ===============================================================

def test_respond_nhan_tham_so_anh():
    from agent.core.agent import respond

    assert "anh" in inspect.signature(respond).parameters


def test_anh_di_CUNG_luot_hoi_khong_tach_ra():
    """
    Tách ra thì mô hình mất mối liên hệ giữa ảnh và câu hỏi: khách gửi ảnh
    kèm "cái này còn hàng không ạ" mà hai thứ ở hai lượt thì nó hỏi lại
    "mình muốn hỏi sản phẩm nào ạ?" — đúng lỗi bản trước đã gặp.
    """
    from agent.core import agent as brain

    nguon = inspect.getsource(brain.respond)
    assert "[*anh," in nguon.replace(" ", "") or "[*anh ," in nguon


def test_main_truyen_dinh_kem_sang_agent():
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agent" / "main.py").read_text(
        encoding="utf-8")
    assert "anh_khach.lay_khoi_anh" in src
    assert "anh=khoi_anh" in src


def test_tai_anh_hong_thi_noi_that_voi_model():
    """
    Không tải được thì phải nói rõ, không im lặng bỏ qua: model cần biết
    khách CÓ gửi gì đó để còn hỏi lại, thay vì trả lời như không có gì.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "agent" / "main.py").read_text(
        encoding="utf-8")
    assert "KHÔNG tải về xem được" in src


def test_prompt_cam_goi_ten_benh():
    """Ràng buộc phải có ở CẢ HAI chỗ: prompt và mã."""
    from pathlib import Path

    prompt = (Path(__file__).resolve().parents[1] / "agent" / "prompts"
              / "system.md").read_text(encoding="utf-8")
    assert "KHÔNG BAO GIỜ gọi tên bệnh" in prompt
