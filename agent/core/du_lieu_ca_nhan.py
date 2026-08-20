"""
Bảo vệ dữ liệu cá nhân — Nghị định 13/2023/NĐ-CP.

VÌ SAO PHẦN NÀY TỒN TẠI
-----------------------
Hệ thống đang lưu họ tên, số điện thoại, địa chỉ giao hàng và toàn bộ nội
dung hội thoại của khách hàng thật. Nghị định 13/2023/NĐ-CP về bảo vệ dữ
liệu cá nhân — có hiệu lực từ 01/07/2023, là bản tương đương GDPR của Việt
Nam — đặt ra ba nghĩa vụ mà trước đây hệ thống không đáp ứng được câu nào:

  Điều 9 khoản 1 mục đ  Chủ thể dữ liệu có quyền YÊU CẦU XOÁ dữ liệu.
  Điều 9 khoản 1 mục c  Chủ thể dữ liệu có quyền BIẾT hệ thống giữ gì.
  Điều 16              Dữ liệu chỉ được lưu trong thời hạn phù hợp với
                       mục đích đã thông báo.

Không có ba thứ này thì câu hỏi "nếu doanh nghiệp thật dùng cái này thì có
hợp pháp không" chưa có câu trả lời.

XOÁ HAY ẨN DANH — HAI CÁCH KHÁC NHAU CHO HAI LOẠI DỮ LIỆU
---------------------------------------------------------
Không phải cứ yêu cầu xoá là xoá sạch mọi thứ. Đơn hàng là chứng từ kế
toán: Luật Kế toán 2015 Điều 41 buộc lưu tối thiểu 10 năm. Xoá thẳng bản
ghi đơn là vi phạm một luật khác.

Nên:
  Hội thoại và tin nhắn  ->  XOÁ HẲN. Nội dung chat chứa số điện thoại,
                             địa chỉ, đôi khi cả tình trạng sức khoẻ da —
                             không có nghĩa vụ lưu giữ nào cả.
  Đơn hàng               ->  ẨN DANH. Giữ mã đơn, số tiền, ngày, sản phẩm
                             cho sổ sách; thay tên, số điện thoại và địa
                             chỉ bằng dấu hiệu đã ẩn danh.

Cách này thoả cả hai luật cùng lúc, và là cách các hệ thống quốc tế xử lý
xung đột giữa "quyền được xoá" và "nghĩa vụ lưu chứng từ".

MỌI LẦN XOÁ ĐỀU ĐƯỢC GHI LẠI
----------------------------
Ghi vào bảng `events`, không ghi lại dữ liệu đã xoá — chỉ ghi số điện thoại
đã băm, thời điểm, và đếm số bản ghi bị tác động. Ghi để CHỨNG MINH đã thực
hiện, không phải để giữ lại thứ vừa hứa xoá.
"""
from __future__ import annotations

import hashlib
import re

from .. import db
from . import ho_so_khach
from ..config import settings

AN_DANH = "[đã ẩn danh theo yêu cầu]"


def chuan_hoa_sdt(sdt: str) -> str:
    """
    Bỏ mọi thứ không phải chữ số, và quy +84 về 0.

    Khách nhắn "0967 627 336", "+84967627336", "84.967.627.336" đều là một
    người. Không chuẩn hoá thì yêu cầu xoá trượt và dữ liệu vẫn nằm đó.
    """
    so = re.sub(r"\D", "", sdt or "")
    if so.startswith("84") and len(so) > 9:
        so = "0" + so[2:]
    return so


def _dau_van_tay(sdt: str) -> str:
    """
    Băm số điện thoại để ghi nhật ký.

    Ghi số thật vào nhật ký thì việc xoá thành vô nghĩa — dữ liệu chỉ chuyển
    từ bảng này sang bảng khác. Băm cho phép chứng minh "đã xử lý yêu cầu
    của số này" mà không giữ lại chính số đó.
    """
    return hashlib.sha256(sdt.encode()).hexdigest()[:16]


# ---------------------------------------------------------------
#  Quyền được biết (Điều 9.1.c)
# ---------------------------------------------------------------

async def tra_cuu(sdt: str) -> dict:
    """Hệ thống đang giữ những gì về số điện thoại này."""
    so = chuan_hoa_sdt(sdt)
    if len(so) < 9:
        raise ValueError("Số điện thoại không hợp lệ")

    don = await db.fetch(
        "SELECT ma_don, khach_ten, khach_dia_chi, tong_tien, trang_thai, "
        "       created_at, conversation_id "
        "FROM orders WHERE regexp_replace(khach_sdt, '\\D', '', 'g') LIKE $1 "
        "ORDER BY created_at DESC",
        f"%{so[-9:]}",
    )
    # Khách để lại số trong nội dung chat mà chưa lên đơn -> vẫn là dữ liệu
    # cá nhân đang lưu, phải tìm ra.
    hoi_thoai = await db.fetch(
        "SELECT DISTINCT c.id, c.channel, c.customer_name, c.msg_count, c.updated_at "
        "FROM conversations c JOIN messages m ON m.conversation_id = c.id "
        "WHERE regexp_replace(m.content, '\\D', '', 'g') LIKE $1 "
        "   OR c.id = ANY($2::uuid[]) "
        "ORDER BY c.updated_at DESC",
        f"%{so[-9:]}%",
        [d["conversation_id"] for d in don if d["conversation_id"]],
    )

    for d in don:
        d["created_at"] = d["created_at"].isoformat()
        d["tong_tien"] = float(d["tong_tien"] or 0)
        d.pop("conversation_id", None)
    for h in hoi_thoai:
        h["id"] = str(h["id"])
        h["updated_at"] = h["updated_at"].isoformat()

    return {
        "so_dien_thoai": so,
        "so_don_hang": len(don),
        "don_hang": don,
        "so_hoi_thoai": len(hoi_thoai),
        "hoi_thoai": hoi_thoai,
        "co_du_lieu": bool(don or hoi_thoai),
        "can_cu": "Nghị định 13/2023/NĐ-CP, Điều 9 khoản 1 mục c",
    }


# ---------------------------------------------------------------
#  Quyền được xoá (Điều 9.1.đ)
# ---------------------------------------------------------------

async def xoa(sdt: str, *, ly_do: str = "khách yêu cầu") -> dict:
    """
    Thực hiện yêu cầu xoá dữ liệu của một khách.

    KHÔNG HOÀN TÁC ĐƯỢC. Gọi `tra_cuu()` trước để người vận hành nhìn thấy
    sẽ mất gì.

    Hội thoại và tin nhắn xoá hẳn; đơn hàng ẩn danh để giữ nghĩa vụ lưu
    chứng từ kế toán. Xem phần đầu file để biết vì sao hai cách khác nhau.
    """
    so = chuan_hoa_sdt(sdt)
    if len(so) < 9:
        raise ValueError("Số điện thoại không hợp lệ")

    truoc = await tra_cuu(so)
    if not truoc["co_du_lieu"]:
        return {"so_dien_thoai": so, "da_xoa": False,
                "ghi_chu": "Không tìm thấy dữ liệu nào của số này."}

    conv_ids = [h["id"] for h in truoc["hoi_thoai"]]

    # 1. Ẩn danh đơn hàng — giữ mã đơn, tiền, ngày cho sổ sách.
    don = await db.execute(
        "UPDATE orders SET khach_ten = $2, khach_sdt = $2, khach_dia_chi = $2, "
        "       updated_at = now() "
        "WHERE regexp_replace(khach_sdt, '\\D', '', 'g') LIKE $1",
        f"%{so[-9:]}", AN_DANH,
    )

    # 2. Xoá hội thoại. Tin nhắn đi theo nhờ ON DELETE CASCADE.
    hoi_thoai = 0
    if conv_ids:
        r = await db.execute(
            "DELETE FROM conversations WHERE id = ANY($1::uuid[])", conv_ids
        )
        hoi_thoai = int(r.split()[-1]) if r.split()[-1].isdigit() else len(conv_ids)

    # 3. Xoá hồ sơ ghi nhớ. Xây trí nhớ mà quên đường xoá là tạo ra một kho
    #    dữ liệu cá nhân ngoài tầm kiểm soát.
    ho_so = await ho_so_khach.xoa(sdt=so)

    # 4. Ghi nhật ký để CHỨNG MINH đã thực hiện — băm số, không lưu số thật.
    await db.log_event(
        "pdpd.xoa_du_lieu", actor="nguoi",
        dau_van_tay=_dau_van_tay(so),
        so_don_an_danh=truoc["so_don_hang"],
        so_hoi_thoai_xoa=hoi_thoai,
        so_ho_so_xoa=ho_so,
        ly_do=ly_do,
        can_cu="Nghị định 13/2023/NĐ-CP, Điều 9 khoản 1 mục đ",
    )
    return {
        "so_dien_thoai": so,
        "da_xoa": True,
        "don_hang_an_danh": truoc["so_don_hang"],
        "hoi_thoai_da_xoa": hoi_thoai,
        "ho_so_ghi_nho_da_xoa": ho_so,
        "ghi_chu": (
            f"Đã ẩn danh {truoc['so_don_hang']} đơn hàng (giữ mã đơn và số "
            f"tiền cho sổ sách kế toán) và xoá hẳn {hoi_thoai} hội thoại "
            f"cùng toàn bộ tin nhắn. Không hoàn tác được."
        ),
        "chi_tiet_don": don,
    }


# ---------------------------------------------------------------
#  Thời hạn lưu trữ (Điều 16)
# ---------------------------------------------------------------

async def don_theo_thoi_han(chi_dem: bool = False) -> dict:
    """
    Xoá hội thoại quá thời hạn lưu trữ.

    Chạy tự động mỗi ngày. `chi_dem=True` để xem sẽ xoá bao nhiêu mà chưa
    xoá — người vận hành cần nhìn trước khi một vòng lặp nền xoá dữ liệu.

    KHÔNG đụng tới đơn hàng: chứng từ kế toán có thời hạn riêng dài hơn
    nhiều (Luật Kế toán 2015, Điều 41).
    """
    ngay = max(1, int(settings.luu_hoi_thoai_ngay))
    dem = await db.fetchrow(
        "SELECT count(*) c FROM conversations WHERE updated_at < now() - ($1 || ' days')::interval",
        str(ngay),
    )
    n = int(dem["c"] or 0)
    if chi_dem or n == 0:
        return {"thoi_han_ngay": ngay, "so_hoi_thoai_qua_han": n, "da_xoa": 0}

    await db.execute(
        "DELETE FROM conversations WHERE updated_at < now() - ($1 || ' days')::interval",
        str(ngay),
    )
    await db.log_event(
        "pdpd.don_theo_thoi_han", actor="system",
        so_hoi_thoai=n, thoi_han_ngay=ngay,
        can_cu="Nghị định 13/2023/NĐ-CP, Điều 16",
    )
    return {"thoi_han_ngay": ngay, "so_hoi_thoai_qua_han": n, "da_xoa": n}
