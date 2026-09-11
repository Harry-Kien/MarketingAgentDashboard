"""
Phạm vi khách: "nhân viên này được thấy khách nào, và làm được gì với họ".

VÌ SAO CHỈ CÓ MỘT CHỖ SINH MỆNH ĐỀ WHERE
-----------------------------------------
Bốn mức tầm nhìn nghĩa là bốn nhánh lọc. Chép bốn nhánh ấy vào bốn truy vấn
là bảo đảm sẽ có một bản sai — và bản sai KHÔNG NỔ, nó chỉ trả thừa hoặc
thiếu vài dòng.

Thừa thì nhân viên thấy khách không phải của mình, và không có gì hỏng để
ai nhận ra. Thiếu thì họ mất khách, và triệu chứng là "dashboard trống",
không phải một lỗi. Cả hai đều lặng lẽ.

Nên: một hàm, và một test canh rằng `FROM contacts` chỉ xuất hiện trong
repository đi qua hàm này.

BỐN MỨC, VÀ VÌ SAO MẶC ĐỊNH LÀ `tat`
-------------------------------------
    tat           Không áp dụng sở hữu khách. MẶC ĐỊNH.
    an_noi_dung   Thấy tên và biết ai phụ trách; không đọc tin, không thấy PII
    chi_doc       Thấy và đọc đủ; nút gửi bị khoá
    an            Không thấy trong danh sách, không mở được, tìm không ra

Mặc định `tat` có chủ ý. Bật một tính năng phân quyền mà đổi ngay quyền của
mọi người đang làm việc là cách tạo sự cố: sáng hôm sau nhân viên mở
dashboard thấy trống, không ai hiểu vì sao, và người đầu tiên bị gọi là
người vừa triển khai. Quản trị bật khi đã giao khách xong.

KHÁCH CHƯA GIAO LÀ CỦA CHUNG
-----------------------------
Chủ dự án chọn: mọi người thấy, không tự gán chủ. Nên mọi nhánh lọc đều giữ
vế `owner_user_id IS NULL`. Bỏ vế ấy là khách mới nhắn tới thành vô hình
với tất cả mọi người — không lỗi, không nhật ký, khách ngồi chờ.

Hệ quả đã biết trước là khách vô chủ sẽ tích lại. Chặn bằng MÃ chứ không
bằng lời nhắc: chỉ số "khách chưa có chủ" thường trực trên trang Ca trực.
"""
from __future__ import annotations

from typing import Any

from agent import db

MUC_TAM_NHIN = ("tat", "an_noi_dung", "chi_doc", "an")
MUC_MAC_DINH = "tat"

# Khoá trong bảng `cau_hinh_agent`. Bảng ấy đã có, đã bền qua khởi động lại.
KHOA_CAU_HINH = "tam_nhin_khach_nguoi_khac"

# Người có quyền này thấy mọi khách, không mức nào lọc họ. Đây chính là thứ
# trước khối A gọi là `is_admin` và truyền thẳng vào mệnh đề WHERE.
QUYEN_XEM_TAT_CA = "khach.xem_tat_ca"


def _kiem_muc(muc: str) -> None:
    """
    Mức lạ thì NÉM.

    Trả `TRUE` cho mức lạ là mở toang danh bạ vì một lỗi gõ trong cấu hình,
    và mở toang thì không có gì hỏng để ai đi kiểm. Trả `FALSE` thì mọi
    người mất sạch khách — đỏ, nhưng đỏ mà không nói lý do.
    """
    if muc not in MUC_TAM_NHIN:
        raise ValueError(
            f"Mức tầm nhìn không hợp lệ: {muc!r}. "
            f"Chỉ nhận: {', '.join(MUC_TAM_NHIN)}"
        )


def _xem_tat_ca(nguoi: dict) -> bool:
    return QUYEN_XEM_TAT_CA in (nguoi.get("quyen") or ())


async def doc_muc() -> str:
    """
    Mức đang đặt, đọc từ `cau_hinh_agent`.

    Giá trị hỏng trong CSDL (người sửa tay, hoặc bản cũ) lui về mặc định
    thay vì ném: đây chạy ở mọi lần mở màn Khách hàng, và một ngoại lệ ở đây
    làm chết cả màn thay vì chỉ mất một thiết lập.
    """
    dong = await db.fetchrow(
        "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = $1", KHOA_CAU_HINH)
    if not dong:
        return MUC_MAC_DINH
    gia_tri = dong["gia_tri"]
    # Codec JSONB đã giải mã; dữ liệu cũ có thể còn là chuỗi JSON.
    if isinstance(gia_tri, str) and gia_tri.startswith('"'):
        import json
        try:
            gia_tri = json.loads(gia_tri)
        except ValueError:
            return MUC_MAC_DINH
    return gia_tri if gia_tri in MUC_TAM_NHIN else MUC_MAC_DINH


def dieu_kien_khach(
    *, nguoi: dict, muc: str, so_tham_so: int, bi_danh: str = "contacts",
) -> tuple[str, list[Any]]:
    """
    Mệnh đề `WHERE` lọc bảng `contacts` theo phạm vi của người này.

    Trả `(sql, tham_so)`. `so_tham_so` là số tham số truy vấn gọi tới ĐÃ
    dùng, để đánh số tiếp đúng chỗ — đánh lại từ `$1` là ghi đè tham số của
    người gọi, và Postgres không báo gì, nó chỉ so nhầm cột.

    `bi_danh` vì các truy vấn sẵn có đặt tên bảng khác nhau (`contact` ở
    `list_visible`). Gắn cứng `contacts.` vào đây thì mệnh đề ném
    `missing FROM-clause entry` — may là nổ to; nhưng nếu truy vấn nào đó
    TÌNH CỜ có cả bảng `contacts` lẫn bí danh khác thì nó lọc nhầm bảng, và
    cái đó thì không nổ.

    Chỉ mức `an` mới lọc danh sách. `an_noi_dung` và `chi_doc` vẫn cho thấy
    khách của người khác — chúng đổi hai cờ ở dưới. Lọc luôn ở hai mức ấy là
    biến chúng thành `an`, và ba lựa chọn trên màn Cấu hình thành hai.
    """
    _kiem_muc(muc)
    if muc != "an" or _xem_tat_ca(nguoi):
        return "TRUE", []
    n = so_tham_so + 1
    return (
        f"({bi_danh}.owner_user_id = ${n} "
        f"OR {bi_danh}.owner_user_id IS NULL)",
        [str(nguoi["id"])],
    )


def _cua_minh_hoac_vo_chu(nguoi: dict, khach: dict) -> bool:
    chu = khach.get("owner_user_id")
    return chu is None or str(chu) == str(nguoi.get("id"))


def duoc_tra_loi(nguoi: dict, khach: dict, *, muc: str) -> bool:
    """Người này gửi tin cho khách này được không."""
    _kiem_muc(muc)
    if muc == "tat" or _xem_tat_ca(nguoi):
        return True
    return _cua_minh_hoac_vo_chu(nguoi, khach)


def duoc_xem_noi_dung(nguoi: dict, khach: dict, *, muc: str) -> bool:
    """
    Người này đọc được tin nhắn và PII của khách này không.

    Chỉ `an_noi_dung` mới chặn. `chi_doc` cố ý cho đọc — tên nó nói vậy, và
    dùng nó để bàn giao ca là chuyện thường ngày.
    """
    _kiem_muc(muc)
    if muc != "an_noi_dung" or _xem_tat_ca(nguoi):
        return True
    return _cua_minh_hoac_vo_chu(nguoi, khach)
