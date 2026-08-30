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

async def an_danh_ben_erp(sdt: str) -> dict:
    """Ẩn danh khách bên kho/ERP.

    VÌ SAO CẦN
    ----------
    Từ khi bật đẩy đơn, tên — số điện thoại — địa chỉ khách được tạo thành
    `Customer` (ERPNext) hoặc `res.partner` (Odoo) và nằm đó VĨNH VIỄN.
    Không có bước này thì hệ thống báo "đã xoá", nhật ký ghi
    `pdpd.xoa_du_lieu` làm bằng chứng tuân thủ — mà dữ liệu vẫn còn nguyên
    ở ERP. Đó là một bản ghi SAI SỰ THẬT về nghĩa vụ pháp lý.

    BA KẾT CỤC, KHÔNG PHẢI HAI
    --------------------------
      ap_dung=False   ERP chưa từng nhận dữ liệu khách (chưa bật ghi đơn,
                      hoặc nguồn là tệp). Không phải lỗi.
      da_lam=True     Đã ẩn danh xong.
      da_lam=False    ERP không với tới được. NGƯỜI VẬN HÀNH PHẢI BIẾT —
                      thời hạn đáp ứng yêu cầu xoá là do luật đặt, không
                      phải do hệ thống đặt.

    Không bao giờ ném: một lỗi ERP không được làm hỏng việc xoá dữ liệu ở
    những nơi khác vốn đã chạy đúng.
    """
    from agent.erp.hop_dong import NguonGhiERP

    if not settings.erp_ghi_don:
        return {"ap_dung": False, "da_lam": False, "so_ban_ghi": 0,
                "ghi_chu": "ERP_GHI_DON đang tắt — ERP chưa từng nhận dữ "
                           "liệu khách nào."}
    try:
        from agent.erp import nha_may

        nguon = nha_may.tao_nguon()
    except Exception as exc:  # noqa: BLE001
        return {"ap_dung": True, "da_lam": False, "so_ban_ghi": 0,
                "ly_do": f"{type(exc).__name__}: {exc}"[:200],
                "ghi_chu": "CHƯA ẩn danh được bên ERP — cần làm tay."}

    if not isinstance(nguon, NguonGhiERP):
        return {"ap_dung": False, "da_lam": False, "so_ban_ghi": 0,
                "ghi_chu": f"Nguồn {getattr(nguon, 'ten', '?')!r} không ghi "
                           "được — ERP chưa từng nhận dữ liệu khách nào."}

    try:
        n = await nguon.an_danh_khach(chuan_hoa_sdt(sdt))
    except Exception as exc:  # noqa: BLE001
        return {"ap_dung": True, "da_lam": False, "so_ban_ghi": 0,
                "ly_do": f"{exc}"[:200],
                "ghi_chu": "CHƯA ẩn danh được bên ERP — cần làm tay."}

    return {"ap_dung": True, "da_lam": True, "so_ban_ghi": int(n),
            "ghi_chu": f"Đã ẩn danh {n} bản ghi khách bên ERP."}


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

    # 4. Ẩn danh khách bên kho/ERP — nơi lưu THỨ BA, ngoài Postgres và hồ sơ
    #    ghi nhớ. Bỏ qua bước này là báo "đã xoá" trong khi ERP còn nguyên.
    erp = await an_danh_ben_erp(so)

    # 5. Ghi nhật ký để CHỨNG MINH đã thực hiện — băm số, không lưu số thật.
    #    Ghi CẢ phần chưa làm được: một bằng chứng tuân thủ che giấu phần
    #    còn thiếu thì tệ hơn không có bằng chứng nào.
    await db.log_event(
        "pdpd.xoa_du_lieu", actor="nguoi",
        dau_van_tay=_dau_van_tay(so),
        so_don_an_danh=truoc["so_don_hang"],
        so_hoi_thoai_xoa=hoi_thoai,
        so_ho_so_xoa=ho_so,
        erp_ap_dung=erp["ap_dung"],
        erp_da_lam=erp["da_lam"],
        erp_so_ban_ghi=erp["so_ban_ghi"],
        erp_ly_do=erp.get("ly_do", ""),
        ly_do=ly_do,
        can_cu="Nghị định 13/2023/NĐ-CP, Điều 9 khoản 1 mục đ",
    )
    con_thieu = erp["ap_dung"] and not erp["da_lam"]
    return {
        "so_dien_thoai": so,
        # `da_xoa` chỉ True khi MỌI nơi lưu đã xong. ERP còn nguyên mà báo
        # True là nói dối về một nghĩa vụ pháp lý.
        "da_xoa": not con_thieu,
        "con_viec_chua_xong": con_thieu,
        "don_hang_an_danh": truoc["so_don_hang"],
        "hoi_thoai_da_xoa": hoi_thoai,
        "ho_so_ghi_nho_da_xoa": ho_so,
        "erp": erp,
        "ghi_chu": (
            f"Đã ẩn danh {truoc['so_don_hang']} đơn hàng (giữ mã đơn và số "
            f"tiền cho sổ sách kế toán) và xoá hẳn {hoi_thoai} hội thoại "
            f"cùng toàn bộ tin nhắn. Không hoàn tác được. "
            + ("CHƯA XONG: " + erp["ghi_chu"] + " Phải vào ERP ẩn danh tay "
               "rồi ghi nhận lại." if con_thieu else erp["ghi_chu"])
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
