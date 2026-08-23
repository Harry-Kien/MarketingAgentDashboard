"""
Chấm điểm một cuộc hội thoại NHIỀU LƯỢT — thứ bộ 56 câu vàng không đo được.

VÌ SAO CẦN LỚP NÀY
------------------
Bộ vàng gọi `respond(history=[], ...)` cho từng ca: một câu hỏi, một câu
trả lời, rồi quên. Nó đo rất kỹ chuyện agent có nói bậy không.

Nhưng "tư vấn chuyên nghiệp" không nằm ở một lượt. Nó nằm ở chỗ: hỏi lại
đúng một câu trước khi khuyên, giữ mạch qua bảy lượt, KHÔNG hỏi lại điều
khách vừa nói, và dẫn khách tới quyết định thay vì để hội thoại chết.

Bốn lỗi dưới đây là bốn lỗi mà một nhân viên thật gần như không bao giờ
mắc, và là bốn lỗi model mắc thường xuyên nhất khi hội thoại dài ra. Cả
bốn đều nhận ra được từ văn bản, nên chấm được bằng mã — không cần một
model thứ hai đi chấm model thứ nhất, vốn đắt và cũng sai được.

RANH GIỚI CỦA LỚP NÀY
---------------------
Nó đo HÌNH THỨC của cuộc tư vấn, không đo NỘI DUNG lời khuyên. "Có hỏi
lại loại da trước khi gợi ý không" thì đo được; "gợi ý ấy có hợp với da
khách không" thì phải người trong nghề đọc mới biết. Đừng nhầm điểm cao ở
đây với tư vấn giỏi — nó chỉ nói agent không mắc lỗi ngớ ngẩn.
"""
from __future__ import annotations

import re

from .tu_nhien import khong_dau

# ---------------------------------------------------------------
#  1. Chào lại từ lượt thứ hai
# ---------------------------------------------------------------
# Prompt đã cấm rõ, và `tu_nhien._bo_chao_lai()` còn cắt hộ ở đường gửi.
# Vẫn phải đo, vì đo cái ĐÃ ĐƯỢC SỬA HỘ mới biết prompt còn yếu tới đâu —
# đúng logic hai mốc mà bộ vàng đang dùng cho dấu hiệu lộ bot.
_CHAO = re.compile(
    r"\b(chao (anh|chi|minh|ban|quy khach)|xin chao|em chao|da em chao)",
    re.I,
)


def chao_lai(tra_loi: list[str]) -> list[int]:
    """Chỉ số các lượt (từ 1 trở đi) mà agent chào lại. Rỗng là đạt."""
    return [
        i for i, t in enumerate(tra_loi)
        if i >= 1 and _CHAO.search(khong_dau(t))
    ]


# ---------------------------------------------------------------
#  2. Hỏi lại điều khách đã nói
# ---------------------------------------------------------------
# Lỗi số một biến một agent thành một cái máy: khách nói "em da dầu" ở lượt
# hai, tới lượt năm agent hỏi "da mình thuộc loại nào ạ?". Người thật không
# làm vậy, và khách nhận ra ngay.
#
# Đây cũng chính là phép đo TRỰC TIẾP cho `ho_so_khach` — module được xây để
# chống đúng lỗi này nhưng chưa từng có con số nào chứng minh nó có tác dụng.
#
# Mỗi mục: (tên việc, mẫu KHÁCH nói, mẫu AGENT hỏi lại)
_DA_BIET: tuple[tuple[str, re.Pattern, re.Pattern], ...] = (
    (
        "loại da",
        re.compile(r"da (dau|kho|hon hop|nhay cam|thuong|mun)\b"),
        re.compile(r"(loai da|da .{0,10}(thuoc )?loai (gi|nao)"
                   r"|da (minh|anh|chi|ban) (nhu the nao|sao|gi)"
                   r"|da kho hay (da )?dau)"),
    ),
    (
        "số điện thoại",
        re.compile(r"\b0\d{8,10}\b"),
        re.compile(r"(so dien thoai|sdt|so lien he|xin so cua)"),
    ),
    (
        "họ tên",
        re.compile(r"\b(minh|em|toi|chi|anh) ten (la )?\w+"),
        re.compile(r"(cho em xin (ho va )?ten|ten (cua )?(minh|anh|chi) la gi"
                   r"|minh ten (gi|la gi))"),
    ),
    (
        "ngân sách",
        re.compile(r"(tam \d|khoang \d|duoi \d|tren \d)[\d.,]* ?(k|nghin|trieu|d\b)"),
        re.compile(r"(ngan sach|tam gia|khoang bao nhieu|muc gia .{0,12}nao)"),
    ),
)


# XÁC NHẬN KHÔNG PHẢI HỎI LẠI.
#
# Prompt BẮT BUỘC agent tóm tắt lại cho khách xác nhận trước khi gọi
# `tao_don_hang`: sản phẩm gì, mấy cái, giao cho ai, số nào, địa chỉ nào.
# Một bộ đo phạt đúng cái prompt yêu cầu thì nó không đo agent nữa — nó
# chỉ đang cãi nhau với chính hệ thống.
#
# Đã bắt nhầm thật ở lần chạy đầu: agent viết "chị xác nhận lại giúp em họ
# tên đầy đủ và số điện thoại nhận hàng" — đúng nghiệp vụ, bị chấm là đãng
# trí.
_XAC_NHAN = re.compile(
    r"(xac nhan|xac minh|kiem tra lai|nhac lai|dung khong|co dung|chinh xac chua"
    r"|em ghi (lai )?(the )?nay|thong tin (giao hang|don hang))"
)


def hoi_lai_da_biet(luot: list[dict]) -> list[tuple[int, str]]:
    """
    Các lần agent hỏi lại điều khách đã nói ở lượt TRƯỚC đó.

    `luot` là danh sách theo thứ tự thời gian, mỗi phần tử:
        {"khach": "...", "agent": "..."}

    Trả về [(chỉ số lượt, tên việc bị hỏi lại)]. Rỗng là đạt.

    Chỉ tính lượt TRƯỚC, không tính lượt hiện tại: khách vừa nói loại da
    trong cùng một tin mà agent hỏi thêm cho rõ thì chưa phải lỗi — có thể
    khách nói "da dầu mà hay khô vùng má", hỏi lại là đúng nghiệp vụ.
    """
    loi: list[tuple[int, str]] = []
    da_noi: set[str] = set()
    for i, l in enumerate(luot):
        agent = khong_dau(l.get("agent", ""))
        dang_xac_nhan = bool(_XAC_NHAN.search(agent))
        for ten, _, mau_hoi in _DA_BIET:
            if ten in da_noi and mau_hoi.search(agent) and not dang_xac_nhan:
                loi.append((i, ten))
        khach = khong_dau(l.get("khach", ""))
        for ten, mau_noi, _ in _DA_BIET:
            if mau_noi.search(khach):
                da_noi.add(ten)
    return loi


# ---------------------------------------------------------------
#  3. Hỏi dồn nhiều câu một lúc
# ---------------------------------------------------------------
# Prompt viết rõ: "Đừng hỏi ba câu một lúc." Khách nhận ba câu hỏi trong
# một tin thì thường chỉ trả lời một câu, và hai câu kia thành rác — hoặc
# tệ hơn, khách thấy phiền và im luôn.
_CAU_HOI = re.compile(r"[^.!?]*\?")


def hoi_don_dap(tra_loi: str, toi_da: int = 2) -> int:
    """Số câu hỏi trong MỘT lượt. Trả về 0 nếu không vượt ngưỡng."""
    n = len(_CAU_HOI.findall(tra_loi))
    return n if n > toi_da else 0


# ---------------------------------------------------------------
#  4. Hội thoại chết
# ---------------------------------------------------------------
# "Bạn là nhân viên bán hàng, không phải máy tra cứu." Tư vấn xong mà không
# gợi bước tiếp thì khách phải tự nghĩ ra câu hỏi kế — và phần lớn khách sẽ
# không nghĩ, họ chỉ im rồi đi.
#
# KHÔNG tính là chết khi agent vừa chuyển người: lúc đó bước tiếp theo là
# một con người, và giục thêm là sai.
# Ba cách một lượt KHÔNG chết, học từ dữ liệu chạy thật:
#
#   hỏi          "...không ạ?"
#   xin thông tin "cho em xin tên sản phẩm", "chị xác nhận lại giúp em"
#   hứa việc     "em kiểm tra giá rồi báo tổng tiền"
#
# Bản đầu chỉ bắt cách thứ nhất và vài cụm của cách thứ ba, nên báo nhầm 3
# trong 5 ca ở lần chạy đầu tiên. Một bộ đo báo nhầm thì tệ hơn không có —
# nó chỉ sai chỗ, và người ta đi sửa prompt đang đúng.
_MOI_TIEP = re.compile(
    r"(\?"
    r"|cho em xin|xin phep|giup em|xac nhan"
    r"|(minh|anh|chi|ban) cho em"
    r"|de em|em (se )?(gui|bao|kiem tra|tu van|len don|dat|lay|chuan bi)"
    r"|(minh|anh chi) (co )?muon|minh lay|chot don|dat hang|xem (them|thu)"
    r"|can em)",
)


def hoi_thoai_chet(tra_loi: str, *, da_chuyen_nguoi: bool = False) -> bool:
    """Lượt cuối có bỏ rơi khách không."""
    if da_chuyen_nguoi:
        return False
    return not _MOI_TIEP.search(khong_dau(tra_loi))



# ---------------------------------------------------------------
#  5. Câu mở đường rỗng
# ---------------------------------------------------------------
# Prompt CẤM kết bằng "Anh/chị cần hỗ trợ gì thêm không ạ" — nó không mở ra
# gì cả, và nó là dấu hiệu bot rõ nhất trong tiếng Việt bán hàng.
#
# Phép kiểm này sinh ra từ một lỗi của chính bộ đo: sau khi siết prompt về
# "đừng để hội thoại chết", điểm lên 12/12 — nhưng đọc lại câu chữ thì một
# ca kết bằng "...sản phẩm nào HAY CÓ CẦN EM HỖ TRỢ GÌ THÊM KHÔNG Ạ".
#
# Bộ đo cho qua vì `_MOI_TIEP` chỉ tìm dấu hỏi. Nó thưởng cho MỌI câu hỏi,
# kể cả câu bị cấm — tức là một dấu XANH GIẢ, nguy hiểm hơn dấu đỏ giả
# nhiều: đỏ giả thì người ta đi kiểm, xanh giả thì không ai kiểm.
#
# `tu_nhien._bo_ket_sao_rong()` cũng không cắt được, vì câu cấm bị dán vào
# một câu hỏi hợp lệ bằng chữ "hay" — nên khách THẬT SỰ nhận nó.
_SAO_RONG = re.compile(
    r"(can (ho tro|giup) gi (them )?khong"
    r"|con gi (can|thac mac) (ho tro|giup) khong"
    r"|co gi (can|thac mac) khong"
    r"|em (co the )?(ho tro|giup) gi (them )?(cho minh )?khong)"
)


def cau_sao_rong(tra_loi: str) -> bool:
    """Có kết bằng câu mở đường rỗng mà prompt đã cấm không."""
    return bool(_SAO_RONG.search(khong_dau(tra_loi)))

# ---------------------------------------------------------------
#  Gộp
# ---------------------------------------------------------------

def cham(luot: list[dict], *, da_chuyen_nguoi: bool = False) -> dict:
    """
    Chấm cả cuộc hội thoại. `luot`: [{"khach": ..., "agent": ...}, ...]

    Trả về các lỗi tìm được cùng một cờ `dat` gộp — để bảng kết quả đọc
    được ngay mà không cần tự suy ra.
    """
    tra_loi = [l.get("agent", "") for l in luot]
    chao = chao_lai(tra_loi)
    hoi_lai = hoi_lai_da_biet(luot)
    don_dap = [(i, n) for i, t in enumerate(tra_loi) if (n := hoi_don_dap(t))]
    chet = bool(tra_loi) and hoi_thoai_chet(
        tra_loi[-1], da_chuyen_nguoi=da_chuyen_nguoi
    )
    rong = [i for i, t in enumerate(tra_loi) if cau_sao_rong(t)]
    return {
        "chao_lai": chao,
        "hoi_lai_da_biet": hoi_lai,
        "hoi_don_dap": don_dap,
        "hoi_thoai_chet": chet,
        "cau_sao_rong": rong,
        "dat": not (chao or hoi_lai or don_dap or chet or rong),
    }
