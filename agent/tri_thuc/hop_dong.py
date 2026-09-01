"""
Hợp đồng cho khung kho tri thức theo ngành hàng.

VÌ SAO MÁY SINH KHUNG CHỨ KHÔNG SINH NỘI DUNG
---------------------------------------------
Kho tri thức là CĂN CỨ. `tim_kien_thuc` đọc nó, RAG đọc nó, và toàn bộ
nguyên tắc "không phát ngôn không có căn cứ" đứng trên nó.

Để mô hình tự viết nội dung là đảo ngược chính nguyên tắc ấy: agent sẽ
trích dẫn "chính sách đổi trả 7 ngày" từ một tài liệu có thật, điểm khớp
RAG cao, giọng tự tin — mà con số 7 do mô hình nghĩ ra. Không có gì nổ,
không dòng nhật ký nào, và cửa hàng chịu trách nhiệm cho một lời hứa chưa
ai duyệt.

Đó là xanh giả ở tầng sâu nhất: sai ngay tại nơi hệ thống đi tìm sự thật.

Nên phân vai dứt khoát:

    MÁY   biết cửa hàng ngành này CẦN trả lời những câu gì
    NGƯỜI biết câu trả lời THẬT của cửa hàng mình
    MÃ    chặn phần chưa có người trả lời, không cho vào kho

Vai thứ ba là vai không thể thiếu. Hai vai đầu chỉ là lời dặn, và lời dặn
thì trượt — đúng bài học của năm lớp lưới trong `agent/core/agent.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Dấu hiệu "chỗ này chưa có người trả lời".
#
# Chọn một chuỗi KHÔNG THỂ xuất hiện tình cờ trong văn bản tiếng Việt bình
# thường: có ngoặc vuông, có chữ in hoa, có dấu hai chấm. Chọn một cụm dễ
# gõ nhầm thành thật (ví dụ "TODO") là sớm muộn có tài liệu thật bị chặn
# oan, và người ta sẽ tắt chốt đi.
DAU_CHUA_DIEN = "[CẦN NGƯỜI ĐIỀN:"


@dataclass(frozen=True)
class Muc:
    """Một mục trong tài liệu — và những câu nó phải trả lời được."""

    tieu_de: str
    cau_hoi: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.cau_hoi:
            raise ValueError(f"Mục {self.tieu_de!r} không có câu hỏi nào")


@dataclass(frozen=True)
class TaiLieu:
    """Một tài liệu cửa hàng ngành này BẮT BUỘC phải có."""

    ten_tep: str
    tieu_de: str
    vi_sao: str
    muc: tuple[Muc, ...]

    def __post_init__(self) -> None:
        if not self.ten_tep.endswith(".md"):
            raise ValueError(f"{self.ten_tep!r} phải là tệp .md")
        if not self.muc:
            raise ValueError(f"Tài liệu {self.ten_tep!r} không có mục nào")
        # `vi_sao` là phần máy đóng góp giá trị thật: nó nói cho chủ cửa
        # hàng biết vì sao tài liệu này đáng viết. Bỏ trống thì khung này
        # chỉ còn là một danh sách tên tệp.
        if len(self.vi_sao.strip()) < 20:
            raise ValueError(f"Tài liệu {self.ten_tep!r} thiếu lý do tồn tại")


@dataclass(frozen=True)
class KhungNganh:
    """
    Khung kho tri thức cho MỘT ngành hàng.

    `van_ban_phap_ly` cố ý chỉ là CON TRỎ tới văn bản, không phải trích dẫn
    nội dung luật. Máy không được tóm tắt luật cho doanh nghiệp dựa vào —
    tóm tắt sai một câu là cửa hàng quảng cáo sai, và trách nhiệm thuộc về
    doanh nghiệp chứ không thuộc về công cụ (NĐ 181/2013).

    `cum_cam_goi_y` cũng vậy: đây là ĐIỂM KHỞI ĐẦU để người rà, không phải
    danh sách đã được thẩm định.
    """

    ma: str
    ten: str
    mo_ta: str
    tai_lieu: tuple[TaiLieu, ...]
    van_ban_phap_ly: tuple[str, ...] = field(default_factory=tuple)
    cum_cam_goi_y: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.tai_lieu:
            raise ValueError(f"Khung {self.ma!r} không có tài liệu nào")
        ten = [t.ten_tep for t in self.tai_lieu]
        if len(ten) != len(set(ten)):
            raise ValueError(f"Khung {self.ma!r} có tên tệp trùng nhau")

    def tong_cau_hoi(self) -> int:
        return sum(len(m.cau_hoi) for t in self.tai_lieu for m in t.muc)
