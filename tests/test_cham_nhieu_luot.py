"""
Kiểm thử bộ chấm hội thoại nhiều lượt. Không gọi API.

Bộ 56 câu vàng đo agent ở MỘT lượt và đo rất kỹ. Nhưng "tư vấn chuyên
nghiệp" không nằm ở một lượt — nó nằm ở chỗ giữ được mạch qua bảy lượt mà
không hỏi lại điều khách vừa nói.

File này canh chính bộ chấm đó. Một bộ chấm sai thì tệ hơn không có: nó
cho điểm cao và làm người ta tin nhầm.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import cham_nhieu_luot as cham  # noqa: E402


# =====================================================================
#  Chào lại từ lượt thứ hai
# =====================================================================

def test_chao_o_luot_dau_la_dung():
    assert cham.chao_lai(["Dạ em chào chị ạ", "Dạ sản phẩm này 690.000đ ạ"]) == []


def test_chao_lai_o_luot_sau_la_loi():
    """Lỗi làm lộ bot nhanh nhất, theo đúng chữ trong system prompt."""
    assert cham.chao_lai(["Dạ vâng ạ", "Chào chị, dạ sản phẩm này 690.000đ"]) == [1]


def test_bat_duoc_nhieu_cach_chao():
    for c in ("Chào anh", "Xin chào mình", "Dạ em chào chị"):
        assert cham.chao_lai(["mở đầu", c]) == [1], c


# =====================================================================
#  Hỏi lại điều khách đã nói  — phép đo trực tiếp cho ho_so_khach
# =====================================================================

def test_hoi_lai_loai_da_da_biet():
    luot = [
        {"khach": "em da dầu ạ", "agent": "Dạ em hiểu ạ"},
        {"khach": "giờ nên dùng gì", "agent": "Da mình thuộc loại nào ạ?"},
    ]
    assert cham.hoi_lai_da_biet(luot) == [(1, "loại da")]


def test_khong_hoi_lai_thi_dat():
    luot = [
        {"khach": "em da dầu ạ", "agent": "Dạ em hiểu ạ"},
        {"khach": "giờ nên dùng gì", "agent": "Da dầu thì mình nên bắt đầu từ sữa rửa mặt ạ"},
    ]
    assert cham.hoi_lai_da_biet(luot) == []


def test_hoi_trong_cung_luot_khong_tinh_la_loi():
    """
    Khách vừa nói loại da trong CÙNG một tin mà agent hỏi thêm cho rõ thì
    chưa phải lỗi — khách có thể nói "da dầu mà hay khô vùng má", và hỏi
    lại lúc đó là đúng nghiệp vụ, không phải đãng trí.
    """
    luot = [{"khach": "em da dầu", "agent": "Dạ da mình thuộc loại nào ạ?"}]
    assert cham.hoi_lai_da_biet(luot) == []


def test_hoi_lai_so_dien_thoai_da_cho():
    luot = [
        {"khach": "sđt em 0912345678", "agent": "Dạ em ghi nhận ạ"},
        {"khach": "ship về Q7 nhé", "agent": "Dạ chị cho em xin số điện thoại ạ"},
    ]
    assert cham.hoi_lai_da_biet(luot) == [(1, "số điện thoại")]


def test_hoi_lai_ngan_sach_da_noi():
    luot = [
        {"khach": "em tầm 500k thôi", "agent": "Dạ vâng ạ"},
        {"khach": "có gì không", "agent": "Ngân sách của mình khoảng bao nhiêu ạ?"},
    ]
    assert [t for _, t in cham.hoi_lai_da_biet(luot)] == ["ngân sách"]


# =====================================================================
#  Hỏi dồn
# =====================================================================

def test_mot_hai_cau_hoi_la_binh_thuong():
    assert cham.hoi_don_dap("Da mình loại nào ạ? Mình đang dùng gì rồi?") == 0


def test_ba_cau_hoi_mot_luc_la_loi():
    """
    Prompt viết rõ "đừng hỏi ba câu một lúc". Khách nhận ba câu thì thường
    chỉ trả lời một, hai câu kia thành rác — hoặc khách thấy phiền và im.
    """
    t = "Da mình loại nào ạ? Mình bao nhiêu tuổi? Ngân sách tầm nhiêu ạ?"
    assert cham.hoi_don_dap(t) == 3


# =====================================================================
#  Hội thoại chết
# =====================================================================

def test_tu_van_xong_ma_khong_goi_buoc_tiep_la_chet():
    assert cham.hoi_thoai_chet("Dạ sản phẩm này 690.000đ ạ.")


def test_co_moi_buoc_tiep_thi_khong_chet():
    for t in ("Mình muốn em lên đơn luôn không ạ?",
              "Dạ để em gửi ảnh cho mình xem nhé",
              "Em tư vấn thêm loại cho ban ngày nha"):
        assert not cham.hoi_thoai_chet(t), t


def test_vua_chuyen_nguoi_thi_khong_tinh_la_chet():
    """
    Bước tiếp theo lúc đó là một CON NGƯỜI. Giục thêm là sai nghiệp vụ, nên
    không được tính vào lỗi bỏ rơi khách.
    """
    t = "Dạ phần này em nhờ bạn chuyên môn bên em hỗ trợ mình cho chắc ạ."
    assert not cham.hoi_thoai_chet(t, da_chuyen_nguoi=True)


# =====================================================================
#  Gộp
# =====================================================================

def test_hoi_thoai_sach_thi_dat():
    luot = [
        {"khach": "da em dạo này xấu quá", "agent": "Dạ em chào chị. Da mình thuộc loại nào ạ?"},
        {"khach": "da dầu ạ", "agent": "Dạ da dầu thì nên bắt đầu từ sữa rửa mặt dịu nhẹ. Em gửi vài lựa chọn cho mình xem nhé?"},
    ]
    assert cham.cham(luot)["dat"]


def test_mot_loi_bat_ky_cung_lam_truot():
    luot = [
        {"khach": "em da dầu", "agent": "Dạ em chào chị"},
        {"khach": "nên dùng gì", "agent": "Da mình loại nào ạ?"},
    ]
    kq = cham.cham(luot)
    assert not kq["dat"]
    assert kq["hoi_lai_da_biet"]


def test_hoi_thoai_rong_khong_no():
    assert cham.cham([])["dat"]


# =====================================================================
#  Hồi quy từ DỮ LIỆU CHẠY THẬT
# =====================================================================
# Lần chạy đầu tiên của bộ nhiều lượt báo 5/12 ca "bỏ rơi khách". Đọc lại
# câu trả lời thật thì 3 trong 5 là bộ đo báo nhầm, không phải agent hỏng.
#
# Một bộ đo báo nhầm tệ hơn không có bộ đo: nó chỉ sai chỗ, và người ta đi
# sửa prompt đang đúng. Các ca dưới đây là câu chữ NGUYÊN VĂN từ lần chạy
# đó, giữ lại để lần sửa sau không làm hỏng lại.

def test_that_hua_kiem_tra_roi_bao_khong_phai_bo_roi():
    """kb-01, lượt cuối. Có gợi bước tiếp rõ ràng."""
    t = "Em kiểm tra giá sản phẩm rồi báo tổng tiền để mình xác nhận luôn nha."
    assert not cham.hoi_thoai_chet(t)


def test_xin_them_thong_tin_khong_phai_bo_roi():
    """kb-12, lượt cuối. Đang xin thông tin để lên đơn, không phải dừng."""
    t = ("Dạ vâng ạ. Chị Hương cho em xin tên sản phẩm kem chống nắng chị "
         "muốn lấy nhé.")
    assert not cham.hoi_thoai_chet(t)


def test_tra_loi_xong_roi_dung_han_la_bo_roi():
    """kb-06, lượt cuối. Đây mới là lỗi thật — nhân viên thật sẽ xoay sang
    hỏi khách cần gì cho da, chứ không đóng cửa cuộc trò chuyện."""
    t = ("Dạ hiện tại Aurora Skin chưa có sản phẩm son môi ạ. Bên em chuyên "
         "về các sản phẩm chăm sóc da thôi ạ.")
    assert cham.hoi_thoai_chet(t)


def test_giai_thich_xong_khong_dan_tiep_la_bo_roi():
    """kb-02, lượt cuối."""
    t = ("Dạ mình dùng sữa rửa mặt trước để làm sạch da, rồi sau đó mới đến "
         "kem dưỡng nha chị. Sữa rửa mặt là bước đầu tiên để loại bỏ bụi bẩn, "
         "dầu thừa, giúp da sạch thoáng ạ.")
    assert cham.hoi_thoai_chet(t)


def test_xac_nhan_truoc_khi_len_don_khong_phai_hoi_lai():
    """
    kb-12, lượt 3. Prompt BẮT BUỘC tóm tắt cho khách xác nhận trước khi gọi
    `tao_don_hang`. Bộ đo phạt đúng cái prompt yêu cầu thì nó không đo agent
    nữa — nó đang cãi nhau với chính hệ thống.
    """
    luot = [
        {"khach": "em tên Hương, sđt 0901234567", "agent": "Dạ vâng ạ"},
        {"khach": "lấy cho em 1 cái", "agent":
         "Chị xác nhận lại giúp em họ tên đầy đủ và số điện thoại nhận hàng nha"},
    ]
    assert cham.hoi_lai_da_biet(luot) == []


def test_hoi_lai_that_su_van_bi_bat():
    """Nới cho xác nhận không được nới luôn cho đãng trí."""
    luot = [
        {"khach": "em tên Hương, sđt 0901234567", "agent": "Dạ vâng ạ"},
        {"khach": "lấy cho em 1 cái", "agent": "Dạ chị cho em xin số điện thoại ạ"},
    ]
    assert [t for _, t in cham.hoi_lai_da_biet(luot)] == ["số điện thoại"]
