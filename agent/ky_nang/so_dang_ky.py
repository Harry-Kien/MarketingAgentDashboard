"""
Khai báo cho NGƯỜI đọc về từng kỹ năng có sẵn.

`TOOLS` trong `agent/core/tools.py` viết cho MODEL: nó nói công cụ làm gì và
nhận tham số nào. Sổ này viết cho NGƯỜI VẬN HÀNH: công cụ này rủi ro tới
đâu, nó cần hệ thống ngoài nào, và tắt nó đi thì mất gì.

Hai danh sách rời nhau thì sớm muộn lệch — nên `tests/test_ky_nang.py` bắt
mọi công cụ trong `TOOLS` phải có khai báo ở đây, và ngược lại. Thêm công cụ
mà quên khai báo là test đỏ ngay, không phải phát hiện lúc vận hành.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KyNang:
    """Một kỹ năng có sẵn, mô tả bằng ngôn ngữ người vận hành hiểu."""

    ten: str
    nhom: str            # tu_van | don_hang | sau_ban | marketing | con_nguoi
    muc_rui_ro: str      # doc | ghi_nhan | hanh_dong
    tom_tat: str         # một câu, hiện trên dashboard
    tat_thi_mat_gi: str  # hậu quả khi tắt — người vận hành phải đọc trước khi tắt
    can_erp: bool = False
    can_kho_tri_thuc: bool = False
    tat_duoc: bool = True


# Ba mức rủi ro, tăng dần. Dashboard tô màu theo mức này.
#
#   doc        chỉ đọc, sai thì khách đọc được câu trả lời sai
#   ghi_nhan   ghi một yêu cầu vào sổ, người xử lý sau — sai thì có người thấy
#   hanh_dong  có hậu quả thật, ra ngoài hệ thống — sai thì phải đi gỡ
MUC_RUI_RO = ("doc", "ghi_nhan", "hanh_dong")

NHOM = ("tu_van", "don_hang", "sau_ban", "marketing", "con_nguoi")


# KỸ NĂNG KHÔNG BAO GIỜ ĐƯỢC TẮT.
#
# `chuyen_nhan_vien` là đường lui của CẢ SÁU lớp lưới an toàn. Bốn trong sáu
# lớp kết thúc bằng "chuyển cho người": trần chi phí, quét injection, ngưỡng
# tin cậy, từ khoá bắt buộc. Tắt nó đi thì các lớp ấy vẫn chạy, vẫn quyết
# định đúng, nhưng không còn chỗ nào để giao hội thoại — và agent sẽ tự trả
# lời chính những câu mà lưới vừa phán là nó không được trả lời.
#
# Đây là lý do hằng số này nằm trong MÃ chứ không phải một cột trong CSDL:
# một hàng cấu hình sửa được thì sẽ có ngày ai đó sửa.
KHONG_TAT_DUOC = frozenset({"chuyen_nhan_vien"})


SO_DANG_KY: tuple[KyNang, ...] = (
    KyNang(
        ten="tim_kien_thuc",
        nhom="tu_van",
        muc_rui_ro="doc",
        tom_tat="Tra kho tài liệu công ty để trả lời có căn cứ.",
        tat_thi_mat_gi=(
            "Agent mất đường tra chính sách giữa chừng. Nó vẫn còn đoạn tài "
            "liệu nạp sẵn đầu lượt, nhưng khách hỏi lệch sang chuyện khác thì "
            "không tra thêm được — và sẽ chuyển người nhiều hơn hẳn."
        ),
        can_kho_tri_thuc=True,
    ),
    KyNang(
        ten="tra_cuu_san_pham",
        nhom="tu_van",
        muc_rui_ro="doc",
        tom_tat="Giá, tồn kho, thành phần của một mã hàng.",
        tat_thi_mat_gi=(
            "Agent không còn nguồn số liệu nào để nói giá. Đây là công cụ "
            "chống bịa số — tắt nó KHÔNG làm agent im lặng về giá, mà làm nó "
            "hết đường lấy giá thật. Tắt thì nên tắt cả nhóm tư vấn."
        ),
        can_erp=True,
    ),
    KyNang(
        ten="goi_y_san_pham",
        nhom="tu_van",
        muc_rui_ro="doc",
        tom_tat="Lọc sản phẩm theo loại da, nhu cầu và ngân sách.",
        tat_thi_mat_gi=(
            "Khách hỏi 'da dầu nên dùng gì' sẽ không được gợi ý nữa. Agent "
            "vẫn tra được từng mã nếu khách gọi đúng tên."
        ),
        can_erp=True,
    ),
    KyNang(
        ten="gui_anh_san_pham",
        nhom="tu_van",
        muc_rui_ro="doc",
        tom_tat="Gửi ảnh chụp thật của sản phẩm.",
        tat_thi_mat_gi="Khách xin xem ảnh sẽ được chuyển cho người.",
    ),
    KyNang(
        ten="tra_cuu_don_hang",
        nhom="sau_ban",
        muc_rui_ro="doc",
        tom_tat="Tình trạng một đơn theo mã đơn.",
        tat_thi_mat_gi=(
            "Mọi câu hỏi 'đơn em tới đâu rồi' đều thành việc của người trực."
        ),
    ),
    KyNang(
        ten="tra_cuu_van_chuyen",
        nhom="sau_ban",
        muc_rui_ro="doc",
        tom_tat="Mã vận đơn và hãng giao, đọc từ sổ cửa hàng.",
        tat_thi_mat_gi="Khách hỏi vận đơn sẽ được chuyển cho người.",
    ),
    KyNang(
        ten="xin_huy_don",
        nhom="sau_ban",
        muc_rui_ro="ghi_nhan",
        tom_tat="Ghi nhận yêu cầu huỷ — KHÔNG huỷ đơn.",
        tat_thi_mat_gi=(
            "Yêu cầu huỷ không vào sổ nữa mà đi thẳng tới người. Chậm hơn, "
            "nhưng không mất — an toàn nếu ca trực đủ người."
        ),
    ),
    KyNang(
        ten="xin_doi_tra",
        nhom="sau_ban",
        muc_rui_ro="ghi_nhan",
        tom_tat="Ghi nhận yêu cầu đổi hoặc trả sau khi đã giao.",
        tat_thi_mat_gi=(
            "Yêu cầu đổi trả đi thẳng tới người. Không mất, chỉ chậm hơn."
        ),
    ),
    KyNang(
        ten="tao_don_hang",
        nhom="don_hang",
        muc_rui_ro="hanh_dong",
        tom_tat="Lên đơn. Công cụ duy nhất có hậu quả không đảo ngược.",
        tat_thi_mat_gi=(
            "Agent không tự chốt đơn nữa — mọi đơn do người lên. Đây là cách "
            "chạy an toàn nhất trong tuần đầu vận hành thật."
        ),
        can_erp=True,
    ),
    KyNang(
        ten="tao_video",
        nhom="marketing",
        muc_rui_ro="ghi_nhan",
        tom_tat="Đặt hàng dựng video marketing. Luôn dừng ở chờ duyệt.",
        tat_thi_mat_gi="Không đặt được video từ hội thoại. Dashboard vẫn đặt được.",
    ),
    KyNang(
        ten="chuyen_nhan_vien",
        nhom="con_nguoi",
        muc_rui_ro="ghi_nhan",
        tom_tat="Giao hội thoại cho người thật.",
        tat_thi_mat_gi=(
            "KHÔNG TẮT ĐƯỢC. Bốn trong sáu lớp lưới an toàn kết thúc bằng "
            "'chuyển cho người'. Không có công cụ này thì các lớp ấy vẫn "
            "phán đúng nhưng không còn chỗ giao việc."
        ),
        tat_duoc=False,
    ),
)


def khai_bao(ten: str) -> KyNang | None:
    """Khai báo của một kỹ năng có sẵn, hoặc None nếu là plugin."""
    for k in SO_DANG_KY:
        if k.ten == ten:
            return k
    return None


def ten_ky_nang_co_san() -> frozenset[str]:
    """Tên của 11 kỹ năng viết sẵn trong mã — dùng để chặn plugin trùng tên."""
    return frozenset(k.ten for k in SO_DANG_KY)
