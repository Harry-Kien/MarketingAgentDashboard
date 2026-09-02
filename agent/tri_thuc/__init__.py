"""
Khung kho tri thức theo ngành hàng.

Phân vai — và vai thứ ba là vai không thể thiếu:

    MÁY   biết cửa hàng ngành này CẦN trả lời được những câu gì
    NGƯỜI biết câu trả lời THẬT của cửa hàng mình
    MÃ    chặn phần chưa có người trả lời, không cho vào kho

Xem `hop_dong.py` cho lý do đầy đủ vì sao máy không được viết nội dung.
"""
from agent.tri_thuc.chot import da_dien_du, loc_tep_nap_duoc, thieu_o_dau
from agent.tri_thuc.hop_dong import DAU_CHUA_DIEN, KhungNganh, Muc, TaiLieu
from agent.tri_thuc.sinh import KetQuaSinh, sinh

__all__ = [
    "DAU_CHUA_DIEN",
    "KetQuaSinh",
    "KhungNganh",
    "Muc",
    "TaiLieu",
    "da_dien_du",
    "loc_tep_nap_duoc",
    "sinh",
    "thieu_o_dau",
]
