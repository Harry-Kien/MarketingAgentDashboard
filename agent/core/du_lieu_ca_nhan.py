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
from uuid import UUID

from .. import db
from . import ho_so_khach
from ..config import settings

AN_DANH = "[đã ẩn danh theo yêu cầu]"


class ChuaDuyet(PermissionError):
    """
    Chưa có phiếu duyệt còn hiệu lực cho số này, nên không được xoá.

    Lớp riêng chứ không phải `ValueError`: route đã đổi `ValueError` thành
    422 "dữ liệu nhập sai", mà đây không phải chuyện nhập sai — người vận
    hành gõ đúng hết, chỉ là chưa có người thứ hai duyệt. Gộp hai thứ vào
    một mã lỗi là đẩy họ đi sửa ô nhập trong khi thứ cần làm nằm ở màn khác.
    """


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
        "SELECT DISTINCT c.id, c.channel, c.customer_name, c.msg_count, c.updated_at, "
        "       c.contact_id "
        "FROM conversations c JOIN messages m ON m.conversation_id = c.id "
        "WHERE regexp_replace(m.content, '\\D', '', 'g') LIKE $1 "
        "   OR c.id = ANY($2::uuid[]) "
        "ORDER BY c.updated_at DESC",
        f"%{so[-9:]}%",
        [d["conversation_id"] for d in don if d["conversation_id"]],
    )

    # Hồ sơ CRM — NƠI LƯU THỨ TƯ, và nơi bị bỏ quên lâu nhất.
    #
    # `contacts` giữ tên, số, email, hồ sơ; `contact_points` giữ danh tính
    # trên từng kênh (id Zalo, id Facebook); `contact_notes` giữ chữ nhân
    # viên viết về khách. Không đọc chúng ở đây thì màn "hệ thống đang giữ
    # gì" trả lời THIẾU cho đúng câu hỏi Điều 9.1.c đặt ra, và `xoa()` cũng
    # không có đường lần tới — hồ sơ ở lại nguyên vẹn sau khi báo "đã xoá".
    ho_so = await db.fetch(
        "SELECT c.id, c.display_name, c.status, "
        "       c.phone IS NOT NULL AS co_sdt, c.email IS NOT NULL AS co_email, "
        "       (SELECT count(*) FROM contact_points p WHERE p.contact_id = c.id) AS danh_tinh, "
        "       (SELECT count(*) FROM contact_notes n WHERE n.contact_id = c.id) AS ghi_chu, "
        "       (SELECT count(*) FROM contact_tags t WHERE t.contact_id = c.id) AS nhan, "
        "       (SELECT count(*) FROM contact_consents s WHERE s.contact_id = c.id) AS dong_y "
        "FROM contacts c "
        "WHERE c.status <> 'deleted' "
        "  AND (right(regexp_replace(coalesce(c.phone, ''), '\\D', '', 'g'), 9) = $1 "
        "       OR c.id = ANY($2::uuid[]))",
        so[-9:],
        [h["contact_id"] for h in hoi_thoai if h.get("contact_id")],
    )

    # Vòng hai: hội thoại của chính những hồ sơ ấy. Khách không phải lúc nào
    # cũng gõ số của mình vào chat — vòng một tìm theo nội dung tin nhắn nên
    # bỏ sót đúng những hội thoại ấy, mà chúng vẫn là dữ liệu của cùng một
    # người. Bỏ sót ở đây là xoá nửa vời mà vẫn báo "đã xoá".
    if ho_so:
        da_co = {h["id"] for h in hoi_thoai}
        them = await db.fetch(
            "SELECT DISTINCT c.id, c.channel, c.customer_name, c.msg_count, "
            "       c.updated_at, c.contact_id "
            "FROM conversations c WHERE c.contact_id = ANY($1::uuid[])",
            [h["id"] for h in ho_so],
        )
        hoi_thoai.extend(h for h in them if h["id"] not in da_co)
        hoi_thoai.sort(key=lambda h: h["updated_at"], reverse=True)

    for d in don:
        d["created_at"] = d["created_at"].isoformat()
        d["tong_tien"] = float(d["tong_tien"] or 0)
        d.pop("conversation_id", None)
    for h in hoi_thoai:
        h["id"] = str(h["id"])
        h["updated_at"] = h["updated_at"].isoformat()
        h.pop("contact_id", None)
    for h in ho_so:
        h["id"] = str(h["id"])

    return {
        "so_dien_thoai": so,
        "so_don_hang": len(don),
        "don_hang": don,
        "so_hoi_thoai": len(hoi_thoai),
        "hoi_thoai": hoi_thoai,
        "so_ho_so": len(ho_so),
        "ho_so_khach": ho_so,
        "co_du_lieu": bool(don or hoi_thoai or ho_so),
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


# ---------------------------------------------------------------
#  Phiếu duyệt bốn mắt cho việc xoá
#
#  Bảng `data_retention_jobs` có sẵn `requested_by` / `approved_by` và chốt
#  "người tạo không tự duyệt được" từ lâu. Thiếu đúng một việc: nút xoá
#  thật chưa bao giờ hỏi tới nó — nên quy trình duyệt chỉ canh việc ĐẾM,
#  còn việc không hoàn tác được thì một người bấm là xong.
#
#  Phiếu khoá theo SỐ ĐIỆN THOẠI vì đó là khoá mà `xoa()` dùng, và lưu dưới
#  dạng dấu vân tay vì phiếu ở lại bảng vĩnh viễn để làm bằng chứng — lưu số
#  thật là sau khi "đã xoá", chính số vừa hứa xoá vẫn nằm trong CSDL.
# ---------------------------------------------------------------

def che_sdt(so: str) -> str:
    """
    Số ở dạng che, đủ để người duyệt biết mình đang duyệt cho ai.

    Duyệt mà không biết duyệt cho số nào thì bốn mắt chỉ còn là hai cú bấm.
    """
    so = chuan_hoa_sdt(so)
    return f"{so[:4]}***{so[-2:]}" if len(so) >= 6 else "***"


def _van_tay_phieu(so: str) -> str:
    """Dấu vân tay dùng để khớp phiếu: băm 9 CHỮ SỐ CUỐI.

    Băm cả số thì "84967627336" và "0967627336" ra hai dấu khác nhau, và
    phiếu duyệt cho số này không khớp lúc xoá số kia — dù là một người.
    """
    return _dau_van_tay(chuan_hoa_sdt(so)[-9:])


async def xin_duyet_xoa(sdt: str, *, ly_do: str, nguoi_id, nguoi_ten: str = "?") -> dict:
    """
    Tạo phiếu xin xoá cho một số điện thoại. Người KHÁC phải duyệt.

    Trả lại phiếu đang có thay vì tạo phiếu thứ hai: bấm hai lần là chuyện
    thường, mà hai phiếu cho cùng một số nghĩa là duyệt một phiếu rồi vẫn
    còn một phiếu treo — không ai hiểu cái nào mới là cái đang có hiệu lực.
    """
    so = chuan_hoa_sdt(sdt)
    if len(so) < 9:
        raise ValueError("Số điện thoại không hợp lệ")
    van_tay = _van_tay_phieu(so)

    cu = await db.fetchrow(
        "SELECT id, status FROM data_retention_jobs "
        "WHERE kind = 'delete' AND sdt_van_tay = $1 AND xoa_thuc_hien_luc IS NULL "
        "  AND status IN ('pending_approval', 'approved') "
        "ORDER BY requested_at DESC LIMIT 1",
        van_tay,
    )
    if cu:
        return {"phieu_id": str(cu["id"]), "trang_thai": cu["status"], "da_co_san": True}

    row = await db.fetchrow(
        "INSERT INTO data_retention_jobs "
        "  (contact_id, kind, requested_by, reason, dry_run, sdt_van_tay, sdt_che) "
        "VALUES ("
        # Gắn contact nếu tra được, để màn Khách hàng có đường lần ra. Không
        # tra được cũng KHÔNG chặn: đo trên CSDL thật, phần lớn dòng
        # `contacts` không có `phone`, nên bắt buộc có contact là bắt buộc
        # phiếu không bao giờ tạo được.
        "  (SELECT id FROM contacts WHERE phone IS NOT NULL "
        "     AND right(regexp_replace(phone, '\\D', '', 'g'), 9) = $1 "
        "   ORDER BY last_seen DESC LIMIT 1), "
        "  'delete', $2, $3, true, $4, $5) "
        "RETURNING id, status",
        so[-9:], UUID(str(nguoi_id)), ly_do, van_tay, che_sdt(so),
    )
    await db.log_event(
        "pdpd.xin_duyet_xoa", actor=nguoi_ten, ref_id=row["id"],
        # `_dau_van_tay(so)` chứ không phải `van_tay` (băm 9 số cuối, dùng để
        # KHỚP phiếu): nhật ký `pdpd.xoa_du_lieu` băm cả số, và hai dấu khác
        # nhau cho cùng một người thì người đi soát không nối được "ai xin
        # xoá" với "đã xoá" — đúng câu hỏi mà nhật ký này sinh ra để trả lời.
        dau_van_tay=_dau_van_tay(so), ly_do=ly_do,
        can_cu="Nghị định 13/2023/NĐ-CP, Điều 9 khoản 1 mục đ",
    )
    return {"phieu_id": str(row["id"]), "trang_thai": row["status"], "da_co_san": False}


async def so_nguoi_duyet_duoc() -> int:
    """
    Có bao nhiêu người đang dùng được quyền `khach.xoa`.

    VÌ SAO PHẢI ĐẾM

    Chốt bốn mắt chặn người tạo tự duyệt. Nếu cả hệ thống chỉ có MỘT tài
    khoản mang quyền ấy thì mọi phiếu đều treo vĩnh viễn — và nó treo đúng
    kiểu hỏng im lặng tệ nhất: không lỗi, không nhật ký, dashboard chỉ hiện
    "chờ người khác duyệt" mãi mãi, trong khi thời hạn đáp ứng yêu cầu xoá
    là do luật đặt chứ không do hệ thống đặt.

    Đếm cả vai trò `Quản trị`: nó nhận toàn bộ danh mục quyền tính từ mã chứ
    không từ `vai_tro_quyen`, nên đếm theo bảng ấy thôi sẽ ra 0 ở đúng hệ
    thống đang có quản trị viên.
    """
    r = await db.fetchrow(
        "SELECT count(DISTINCT n.id) AS n FROM nguoi_dung n "
        "JOIN nguoi_dung_vai_tro x ON x.nguoi_dung_id = n.id "
        "JOIN vai_tro vt ON vt.id = x.vai_tro_id "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
        "     AND vq.quyen = 'khach.xoa' "
        "WHERE NOT n.khoa "
        "  AND (vq.quyen IS NOT NULL OR (vt.he_thong AND vt.ten = 'Quản trị'))"
    )
    return int((r or {}).get("n") or 0)


async def trang_thai_phieu(sdt: str) -> dict:
    """
    Số này đang có phiếu ở trạng thái nào — để giao diện nói trước, thay vì
    để người vận hành bấm Xoá rồi mới biết là chưa được phép.
    """
    so = chuan_hoa_sdt(sdt)
    nguoi_duyet = await so_nguoi_duyet_duoc()
    chua_co = {"co_phieu": False, "xoa_duoc": False, "trang_thai": None,
               "so_nguoi_duyet_duoc": nguoi_duyet}
    if len(so) < 9:
        return chua_co
    row = await db.fetchrow(
        "SELECT id, status, approved_by FROM data_retention_jobs "
        "WHERE kind = 'delete' AND sdt_van_tay = $1 AND xoa_thuc_hien_luc IS NULL "
        "  AND status IN ('pending_approval', 'approved', 'completed') "
        "ORDER BY requested_at DESC LIMIT 1",
        _van_tay_phieu(so),
    )
    if not row:
        return chua_co
    return {
        "co_phieu": True,
        "phieu_id": str(row["id"]),
        "trang_thai": row["status"],
        "xoa_duoc": row["approved_by"] is not None and row["status"] in ("approved", "completed"),
        "so_nguoi_duyet_duoc": nguoi_duyet,
    }


async def _gianh_phieu_duyet(so: str) -> dict:
    """
    Giành lấy một phiếu đã duyệt, chưa dùng, cho số này. Không có thì NÉM.

    Một câu lệnh duy nhất vừa tìm vừa đánh dấu đã dùng: tìm rồi mới cập nhật
    ở câu thứ hai thì hai người bấm Xoá cùng lúc sẽ cùng tìm thấy MỘT phiếu
    và cùng được đi tiếp — bốn mắt cho lần đầu, không mắt nào cho lần sau.
    `SKIP LOCKED` để hai lời gọi song song lấy hai phiếu khác nhau thay vì
    chờ nhau.

    Xoá luôn `sdt_che`: phiếu đã dùng ở lại làm bằng chứng, và thứ ở lại thì
    không được mang theo thông tin nhận dạng của số vừa hứa xoá.
    """
    row = await db.fetchrow(
        "UPDATE data_retention_jobs "
        "   SET xoa_thuc_hien_luc = now(), sdt_che = NULL "
        " WHERE id = (SELECT id FROM data_retention_jobs "
        "              WHERE kind = 'delete' AND sdt_van_tay = $1 "
        "                AND approved_by IS NOT NULL "
        "                AND status IN ('approved', 'completed') "
        "                AND xoa_thuc_hien_luc IS NULL "
        "              ORDER BY approved_at LIMIT 1 FOR UPDATE SKIP LOCKED) "
        "RETURNING id, requested_by, approved_by",
        _van_tay_phieu(so),
    )
    if row is None:
        raise ChuaDuyet(
            "Chưa có phiếu duyệt cho số này. Bấm 'Xin duyệt xoá', rồi một "
            "người KHÁC vào màn Nhật ký duyệt phiếu ấy — xoá dữ liệu cá nhân "
            "không hoàn tác được nên cần hai người."
        )
    return dict(row)


async def _nha_phieu_duyet(phieu_id) -> None:
    """
    Trả phiếu về trạng thái chưa dùng khi việc xoá hỏng giữa chừng.

    Không trả thì một lỗi mạng tới ERP là mất luôn phiếu, và người vận hành
    phải đi xin duyệt lại cho đúng việc vừa được duyệt xong — thủ tục lặp
    lại vì máy hỏng là thứ khiến người ta tìm đường vòng qua chốt.
    """
    await db.execute(
        "UPDATE data_retention_jobs SET xoa_thuc_hien_luc = NULL WHERE id = $1",
        phieu_id,
    )


def _dem(ket_qua: str) -> int:
    """Số dòng từ chuỗi asyncpg trả về ("DELETE 3" -> 3)."""
    duoi = str(ket_qua or "").split()
    return int(duoi[-1]) if duoi and duoi[-1].isdigit() else 0


async def _xoa_ho_so_crm(ho_so: list[dict]) -> dict:
    """
    Dọn hồ sơ CRM của khách: nơi lưu THỨ TƯ, ngoài đơn hàng, hội thoại và ERP.

    VÌ SAO BƯỚC NÀY TỪNG KHÔNG TỒN TẠI VÀ VÌ SAO NÓ QUAN TRỌNG

    `xoa()` trước đây chạm đơn hàng, hội thoại, hồ sơ ghi nhớ và ERP — không
    chạm `contacts`. Nghĩa là sau khi hệ thống báo "đã xoá" và ghi nhật ký
    tuân thủ, tên khách, số điện thoại, email, ghi chú nhân viên viết về họ,
    nhãn và danh tính trên từng kênh vẫn còn nguyên trong CRM. Trớ trêu nhất:
    "Chạy đếm" của phiếu duyệt đếm ĐÚNG những bảng ấy — đếm thứ sẽ không bị
    xoá.

    XOÁ HAY ẨN DANH, VẪN LÀ HAI CÁCH CHO HAI LOẠI

      ghi chú, nhãn        -> XOÁ HẲN. Chữ nhân viên viết về một người, không
                              có nghĩa vụ lưu giữ nào.
      danh tính từng kênh  -> ẨN DANH. Xoá hẳn thì hội thoại còn lại (của
                              khách khác cùng kênh) vướng khoá ngoại RESTRICT;
                              mà giữ `external_user_id` là giữ đúng thứ dùng
                              để nhận ra người ấy ở lần nhắn sau. Thay bằng
                              khoá ngẫu nhiên: tin nhắn sau tạo hồ sơ mới,
                              đúng nghĩa đã quên người cũ.
      đồng ý marketing     -> GIỮ DÒNG, BỎ NỘI DUNG. Dòng đồng ý là bằng
                              chứng pháp lý cho việc đã từng được phép nhắn;
                              `evidence` thì có thể chứa chính số vừa hứa xoá.
      hồ sơ khách          -> ẨN DANH + đánh dấu `deleted`, giữ id để đơn
                              hàng và hội thoại còn lại không mồ côi khoá
                              ngoại.
    """
    ids = [h["id"] for h in ho_so]
    if not ids:
        return {"ho_so": 0, "ghi_chu": 0, "nhan": 0, "danh_tinh": 0, "dong_y": 0}

    ghi_chu = _dem(await db.execute(
        "DELETE FROM contact_notes WHERE contact_id = ANY($1::uuid[])", ids))
    nhan = _dem(await db.execute(
        "DELETE FROM contact_tags WHERE contact_id = ANY($1::uuid[])", ids))
    danh_tinh = _dem(await db.execute(
        "UPDATE contact_points SET handle = $2, "
        "       external_user_id = 'an-danh:' || id::text, "
        "       metadata = '{}'::jsonb, verified_fields = '{}'::jsonb, "
        "       updated_at = now() "
        "WHERE contact_id = ANY($1::uuid[])", ids, AN_DANH))
    dong_y = _dem(await db.execute(
        "UPDATE contact_consents SET evidence = '{}'::jsonb, updated_at = now() "
        "WHERE contact_id = ANY($1::uuid[])", ids))
    # `merged_into = NULL` không phải dọn dẹp cho đẹp: ràng buộc
    # `contacts_check` bắt trạng thái khác 'merged' phải có `merged_into`
    # rỗng, nên một hồ sơ đã gộp mà không xoá ô ấy thì câu UPDATE này NÉM,
    # và ném ở đây là cả lần xoá hỏng giữa chừng.
    n_ho_so = _dem(await db.execute(
        "UPDATE contacts SET display_name = $2, phone = NULL, email = NULL, "
        "       profile = '{}'::jsonb, status = 'deleted', merged_into = NULL, "
        "       version = version + 1, updated_at = now() "
        "WHERE id = ANY($1::uuid[])", ids, AN_DANH))
    return {"ho_so": n_ho_so, "ghi_chu": ghi_chu, "nhan": nhan,
            "danh_tinh": danh_tinh, "dong_y": dong_y}


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

    # CHỐT BỐN MẮT. Ở TRONG LÕI, không ở route: route chỉ là một trong
    # những đường có thể gọi tới hàm này, và một chốt đặt trên đường đi thì
    # mỗi đường mới lại là một lần phải nhớ — quên một lần là phơi ra, không
    # ai báo. Ở đây thì mọi đường đều đi qua nó.
    #
    # Đặt SAU `co_du_lieu`: số không có dữ liệu gì thì không tiêu phiếu của
    # người ta cho một việc không làm gì cả.
    phieu = await _gianh_phieu_duyet(so)
    try:
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

        # 4. Dọn hồ sơ CRM — nơi lưu THỨ TƯ. Xem `_xoa_ho_so_crm` để biết vì
        #    sao mỗi bảng được xử lý một kiểu.
        crm = await _xoa_ho_so_crm(truoc["ho_so_khach"])

        # 5. Ẩn danh khách bên kho/ERP — nơi lưu THỨ NĂM, ngoài Postgres và hồ
        #    sơ ghi nhớ. Bỏ qua bước này là báo "đã xoá" trong khi ERP còn nguyên.
        erp = await an_danh_ben_erp(so)
    except Exception:
        # Hỏng giữa chừng thì trả phiếu về trạng thái chưa dùng: bắt đi xin
        # duyệt lại cho đúng việc vừa được duyệt xong là thủ tục lặp lại vì
        # máy hỏng, và đó là thứ khiến người ta tìm đường vòng qua chốt.
        await _nha_phieu_duyet(phieu["id"])
        raise

    # 6. Ghi nhật ký để CHỨNG MINH đã thực hiện — băm số, không lưu số thật.
    #    Ghi CẢ phần chưa làm được: một bằng chứng tuân thủ che giấu phần
    #    còn thiếu thì tệ hơn không có bằng chứng nào.
    await db.log_event(
        "pdpd.xoa_du_lieu", actor="nguoi",
        dau_van_tay=_dau_van_tay(so),
        so_don_an_danh=truoc["so_don_hang"],
        so_hoi_thoai_xoa=hoi_thoai,
        so_ho_so_xoa=ho_so,
        # Hồ sơ CRM: đếm riêng từng bảng. Gộp thành một con số thì lần sau
        # một bảng lặng lẽ rơi khỏi luồng xoá mà tổng vẫn trông hợp lý.
        crm_ho_so=crm["ho_so"],
        crm_ghi_chu=crm["ghi_chu"],
        crm_nhan=crm["nhan"],
        crm_danh_tinh=crm["danh_tinh"],
        erp_ap_dung=erp["ap_dung"],
        erp_da_lam=erp["da_lam"],
        erp_so_ban_ghi=erp["so_ban_ghi"],
        erp_ly_do=erp.get("ly_do", ""),
        ly_do=ly_do,
        # Bằng chứng bốn mắt: phiếu nào, ai xin, ai duyệt. Thiếu ba ô này
        # thì nhật ký chứng minh được "đã xoá" nhưng không chứng minh được
        # "có người thứ hai đồng ý", mà đó mới là thứ đang được hỏi khi có
        # tranh chấp.
        phieu_duyet=str(phieu["id"]),
        nguoi_xin=str(phieu["requested_by"]),
        nguoi_duyet=str(phieu["approved_by"]),
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
        "crm": crm,
        "erp": erp,
        "phieu_duyet": str(phieu["id"]),
        "ghi_chu": (
            f"Đã ẩn danh {truoc['so_don_hang']} đơn hàng (giữ mã đơn và số "
            f"tiền cho sổ sách kế toán) và xoá hẳn {hoi_thoai} hội thoại "
            f"cùng toàn bộ tin nhắn. "
            f"Hồ sơ CRM: {crm['ho_so']} hồ sơ ẩn danh, {crm['ghi_chu']} ghi "
            f"chú và {crm['nhan']} nhãn xoá hẳn, {crm['danh_tinh']} danh "
            f"tính kênh ẩn danh. Không hoàn tác được. "
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
