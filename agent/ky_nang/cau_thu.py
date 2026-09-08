"""
Câu thử của một plugin tra bảng: chạy lại sau mỗi lần lưu.

VÌ SAO CẦN

Sửa một dòng trong bảng dài có thể làm hỏng dòng khác, và không gì bắt
được. Thêm bí danh "Sài Gòn" vào dòng Hồ Chí Minh là dòng "Sa Đéc" bỗng
khớp mập mờ; đổi một khoá là câu khách hỏi hôm qua hôm nay trượt. Không
lỗi, không nhật ký — agent chỉ trả lời kém đi ở đúng chỗ nó vốn trả lời
tốt, và người vận hành biết được điều đó qua một khách bực mình.

Câu thử là bộ nhớ của những gì ĐÃ từng đúng.

VÌ SAO TỆP NÀY PHẢI THUẦN

Nó chạy ở MỌI lần bấm Lưu. Một lời gọi mạng lọt vào đây là mỗi cú sửa
bảng thành một lần ra ngoài, và một cú bấm Lưu có thể treo vì máy chủ
khác đang chậm. `tests/test_ky_nang_cau_thu.py` canh bằng AST, cùng cách
canh ràng buộc chỉ-đọc của `chay.py`.

Đó cũng là lý do chỉ `tra_bang` được khai câu thử: `_tra_bang` là hàm
thuần, còn bốn loại kia đều ra ngoài.
"""
from __future__ import annotations

from agent.ky_nang.ban_mo_ta import BanMoTa, bo_dau
from agent.ky_nang.chay import chay_plugin


def _chua(noi_dung: str, mong_doi: str) -> bool:
    """
    So sau khi bỏ dấu và hạ chữ thường.

    Người vận hành gõ câu thử một lần rồi quên; bắt họ nhớ đúng hoa thường
    và đúng dấu của câu trả lời là biến câu thử thành nguồn báo đỏ giả, và
    báo đỏ giả thì họ xoá câu thử.
    """
    return bo_dau(mong_doi) in bo_dau(noi_dung)


async def chay_cau_thu(bm: BanMoTa) -> list[dict]:
    """
    Chạy mọi câu thử qua đúng `chay_plugin`, trả kết quả từng câu.

    Chạy qua bộ thi hành thật chứ không đọc lại bảng: khớp đúng, khớp
    chứa, bí danh và nhánh hỏi-lại đều nằm trong `_tra_bang`, và một bản
    sao logic ấy ở đây sẽ lệch đúng vào ngày nó cần đúng nhất.

    `mong_doi` rỗng nghĩa là câu này PHẢI trượt — ca quan trọng nhất của
    một bảng tra, vì nó canh việc agent nói "chưa có thông tin" thay vì
    đoán. Không khai được ca ấy thì câu thử chỉ canh nửa hành vi.
    """
    if not bm.cau_thu or not bm.tham_so:
        return []
    ten = bm.tham_so[0].ten

    ra: list[dict] = []
    for c in bm.cau_thu:
        kq = await chay_plugin(bm, {ten: c.hoi})
        tim_thay = bool(kq.get("tim_thay"))
        nhan = str(kq.get("gia_tri") or "")
        if not c.mong_doi:
            dat = not tim_thay
            nhan_duoc = nhan if tim_thay else "không khớp dòng nào"
        else:
            dat = tim_thay and _chua(nhan, c.mong_doi)
            nhan_duoc = nhan if tim_thay else (
                "khớp nhiều dòng: " + ", ".join(kq.get("nhieu_ket_qua") or [])
                if kq.get("nhieu_ket_qua") else "không khớp dòng nào"
            )
        ra.append({
            "hoi": c.hoi,
            "mong_doi": c.mong_doi,
            "dat": dat,
            "nhan_duoc": nhan_duoc,
        })
    return ra
