"""
Công việc: giao việc cho nhân viên và theo dõi tới khi xong.

VÌ SAO KHỐI NÀY TỒN TẠI
------------------------
Việc THẬT cần người làm phải có người chịu trách nhiệm: khách xin huỷ/sửa
đơn (`loai_xu_ly_don`), hãng vận chuyển báo giao hỏng, ERP giữ đơn nháp,
token kênh sắp hết hạn, quy tắc tự động "tạo việc", và việc người giao tay.

AI CHUYỂN NGƯỜI KHÔNG CÒN SINH VIỆC (mục 14.2, 21.11.2026)
---------------------------------------------------------
Trước bản này mỗi lần AI chuyển giao đẻ một việc "Khách cần người trả lời".
Việc ấy trùng nghiệp vụ với chính hội thoại đang chờ trong hàng chờ người:
nhân viên trả lời khách xong vẫn phải đi đóng thêm một việc, màn Công việc
đầy dòng không phải việc, và việc thật nằm lẫn trong đó. Nay chuyển giao là
THÔNG BÁO (`agent/core/thong_bao_noi_bo.py::bao_ai_chuyen_giao`) — nhắc và
dẫn đường, không phải hạng mục phải đóng.

Việc tự sinh cũ (nguon='agent', `loai_xu_ly_don` NULL) còn mở trong CSDL
đang chạy vẫn được `giai_quyet.dong_viec_tu_sinh` đóng khi giải quyết hay
trả hội thoại cho agent — không ai phải dọn tay.

`idx_cong_viec_agent_mot_viec` (một việc nguon='agent' đang mở mỗi hội
thoại) vẫn giữ: nay nó canh việc xử lý ĐƠN — khách nhắn "huỷ đơn" ba lần
không thành ba việc huỷ (`tao_tu_yeu_cau_xu_ly_don`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from agent import db

TRANG_THAI = ("moi", "dang_lam", "xong", "huy")
UU_TIEN = ("thap", "thuong", "cao", "gap")
NGUON = ("nguoi", "agent", "tu_dong", "van_chuyen", "don_hang")

NHAN_TRANG_THAI = {
    "moi": "Mới",
    "dang_lam": "Đang làm",
    "xong": "Xong",
    "huy": "Đã huỷ",
}
NHAN_UU_TIEN = {
    "thap": "Thấp", "thuong": "Thường", "cao": "Cao", "gap": "Gấp",
}

CHUA_XONG = ("moi", "dang_lam")
LOAI_XU_LY_DON = ("sua", "huy")
KET_QUA_XU_LY_DON = ("thanh_cong", "khong_the", "cho_doi_soat")


class CongViecHong(ValueError):
    """Dữ liệu công việc không hợp lệ."""


class KhongTimThayXuLyDon(LookupError):
    """Không tìm thấy Pending Action hoặc đơn liên quan."""


class KhongDuPhamViXuLyDon(PermissionError):
    """Nhân viên không được xử lý Pending Action này."""


class XungDotXuLyDon(ValueError):
    """Liên kết, loại nghiệp vụ hoặc bằng chứng ERP không khớp."""


@dataclass(frozen=True, slots=True)
class KetQuaXacNhanDon:
    """Kết quả service để API phân biệt hoàn tất, chờ và idempotent."""

    cong_viec_id: UUID
    order_id: UUID
    loai: str
    ket_qua: str
    trang_thai_cong_viec: str
    da_xu_ly_truoc: bool = False
    thong_bao: str = ""

    def api_dict(self) -> dict[str, Any]:
        return {
            "cong_viec_id": str(self.cong_viec_id),
            "order_id": str(self.order_id),
            "loai": self.loai,
            "ket_qua": self.ket_qua,
            "trang_thai_cong_viec": self.trang_thai_cong_viec,
            "da_xu_ly_truoc": self.da_xu_ly_truoc,
            "thong_bao": self.thong_bao,
        }


def kiem_trang_thai(gia_tri: str) -> str:
    if gia_tri not in TRANG_THAI:
        raise CongViecHong(
            f"Trạng thái không hợp lệ: {gia_tri!r}. "
            f"Chỉ nhận: {', '.join(TRANG_THAI)}")
    return gia_tri


def kiem_uu_tien(gia_tri: str) -> str:
    if gia_tri not in UU_TIEN:
        raise CongViecHong(
            f"Mức ưu tiên không hợp lệ: {gia_tri!r}. "
            f"Chỉ nhận: {', '.join(UU_TIEN)}")
    return gia_tri


def qua_han(viec: dict, bay_gio: datetime | None = None) -> bool:
    """
    Việc này đã quá hạn chưa.

    Việc đã `xong` hoặc `huy` thì KHÔNG bao giờ quá hạn, dù hạn đã qua. Đếm
    chúng vào là con số quá hạn chỉ tăng và không bao giờ giảm — và một con
    số chỉ tăng là con số người ta thôi nhìn.
    """
    han = viec.get("han")
    if not han or viec.get("trang_thai") not in CHUA_XONG:
        return False
    if isinstance(han, str):
        han = datetime.fromisoformat(han)
    moc = bay_gio or datetime.now(timezone.utc)
    if han.tzinfo is None:
        han = han.replace(tzinfo=timezone.utc)
    return han < moc


async def _doc_don_erp(erp_tham_chieu: str) -> dict | None:
    """Đọc trạng thái Sales Order hiện hành; tuyệt đối không ghi vào ERP."""
    from agent.erp import nha_may

    return await nha_may.cong().doc_don(erp_tham_chieu)


def _phien_ban_erp(gia_tri: Any) -> str:
    """Chuẩn hoá vừa đủ để so cùng một mốc `modified` do ERPNext trả về."""
    if isinstance(gia_tri, datetime):
        return gia_tri.isoformat()
    return str(gia_tri or "").strip().replace(" ", "T")


def _kiem_lien_ket_va_pham_vi(
    row: Any,
    *,
    order_id: UUID,
    loai: str,
    nguoi_id: UUID,
    quyen: frozenset[str] | set[str],
) -> None:
    if row is None:
        raise KhongTimThayXuLyDon("Không tìm thấy Pending Action")
    if row["order_id"] != order_id:
        raise XungDotXuLyDon("Pending Action không thuộc đơn hàng này")
    if row["loai_xu_ly_don"] != loai:
        raise XungDotXuLyDon("Loại xử lý không khớp Pending Action")
    if (
        row["nguoi_nhan"] is not None
        and row["nguoi_nhan"] != nguoi_id
        and "cong_viec.xem_tat_ca" not in quyen
    ):
        raise KhongDuPhamViXuLyDon(
            "Pending Action đang được giao cho nhân viên khác"
        )


def _ket_qua_da_chot(
    row: Any,
    *,
    order_id: UUID,
    loai: str,
    ket_qua: str,
) -> KetQuaXacNhanDon | None:
    if row["trang_thai"] != "xong":
        return None
    if row["ket_qua_xu_ly_don"] != ket_qua:
        raise XungDotXuLyDon(
            "Pending Action đã hoàn tất với một kết quả khác; không được ghi đè"
        )
    return KetQuaXacNhanDon(
        cong_viec_id=row["id"],
        order_id=order_id,
        loai=loai,
        ket_qua=ket_qua,
        trang_thai_cong_viec="xong",
        da_xu_ly_truoc=True,
        thong_bao="Kết quả này đã được xác nhận trước đó.",
    )


async def lay_bang_chung_xu_ly_don(
    *,
    order_id: UUID,
    cong_viec_id: UUID,
    nguoi_id: UUID,
    quyen: frozenset[str] | set[str],
) -> dict[str, Any]:
    """Đọc snapshot ERP hiện hành cho đúng Pending Action và phạm vi người dùng."""
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT v.id, v.order_id, v.loai_xu_ly_don, v.trang_thai,
                   v.ket_qua_xu_ly_don, v.nguoi_nhan, o.erp_ma_don
            FROM cong_viec v
            LEFT JOIN orders o ON o.id = v.order_id
            WHERE v.id = $1
            """,
            cong_viec_id,
        )
    if row is None:
        raise KhongTimThayXuLyDon("Không tìm thấy Pending Action")
    loai = row["loai_xu_ly_don"]
    if loai not in LOAI_XU_LY_DON:
        raise XungDotXuLyDon("Pending Action không phải yêu cầu sửa/hủy đơn")
    _kiem_lien_ket_va_pham_vi(
        row,
        order_id=order_id,
        loai=loai,
        nguoi_id=nguoi_id,
        quyen=quyen,
    )
    erp_tham_chieu = str(row["erp_ma_don"] or "").strip()
    if not erp_tham_chieu:
        raise XungDotXuLyDon("Đơn chưa có mã Sales Order ERPNext để đối soát")
    bang_chung = await _doc_don_erp(erp_tham_chieu)
    if not bang_chung:
        raise XungDotXuLyDon("ERPNext không trả về Sales Order tương ứng")
    if str(bang_chung.get("name") or "") != erp_tham_chieu:
        raise XungDotXuLyDon("Mã Sales Order ERPNext không khớp")
    return {
        "order_id": str(order_id),
        "cong_viec_id": str(cong_viec_id),
        "erp_tham_chieu": erp_tham_chieu,
        "trang_thai": str(bang_chung.get("status") or ""),
        "docstatus": int(bang_chung.get("docstatus") or 0),
        "modified": _phien_ban_erp(bang_chung.get("modified")),
    }


async def xac_nhan_ket_qua_don(
    *,
    order_id: UUID,
    cong_viec_id: UUID,
    loai: str,
    ket_qua: str,
    ly_do: str,
    erp_modified_at: datetime | None,
    nguoi_id: UUID,
    quyen: frozenset[str] | set[str],
) -> KetQuaXacNhanDon:
    """Đối soát ERP rồi cập nhật đúng một Pending Action, có khóa chống race.

    Hàm chỉ ĐỌC ERP. Trạng thái task được chốt trong transaction PostgreSQL;
    hai nhân viên xác nhận đồng thời sẽ tuần tự trên ``FOR UPDATE``.
    """
    if loai not in LOAI_XU_LY_DON:
        raise CongViecHong(f"Loại xử lý không hợp lệ: {loai!r}")
    if ket_qua not in KET_QUA_XU_LY_DON:
        raise CongViecHong(f"Kết quả xử lý không hợp lệ: {ket_qua!r}")
    ly_do = (ly_do or "").strip()
    if ket_qua == "khong_the" and len(ly_do) < 3:
        raise CongViecHong("Kết quả không thể xử lý phải có lý do rõ ràng")

    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT v.id, v.order_id, v.loai_xu_ly_don, v.trang_thai,
                   v.ket_qua_xu_ly_don, v.nguoi_nhan,
                   o.erp_ma_don, o.erp_dong_bo_luc
            FROM cong_viec v
            LEFT JOIN orders o ON o.id = v.order_id
            WHERE v.id = $1
            """,
            cong_viec_id,
        )
    _kiem_lien_ket_va_pham_vi(
        row,
        order_id=order_id,
        loai=loai,
        nguoi_id=nguoi_id,
        quyen=quyen,
    )
    da_chot = _ket_qua_da_chot(
        row, order_id=order_id, loai=loai, ket_qua=ket_qua
    )
    if da_chot is not None:
        return da_chot

    erp_tham_chieu = str(row["erp_ma_don"] or "").strip()
    erp_trang_thai = ""
    erp_sua_luc = ""
    ket_qua_luu = ket_qua
    ly_do_luu = ly_do
    trang_thai_task = "xong"
    thong_bao = "Đã ghi nhận kết quả đã được ERPNext xác minh."

    if ket_qua == "cho_doi_soat":
        trang_thai_task = "dang_lam"
        ly_do_luu = ly_do or "Nhân viên yêu cầu tiếp tục đối soát ERPNext"
        thong_bao = "Đã giữ Pending Action ở trạng thái chờ đối soát."
    elif not erp_tham_chieu:
        ket_qua_luu = "cho_doi_soat"
        trang_thai_task = "dang_lam"
        ly_do_luu = "Đơn chưa có mã Sales Order ERPNext để đối soát"
        thong_bao = "Đơn chưa có mã ERP; chưa thể xác minh kết quả."
    else:
        try:
            bang_chung = await _doc_don_erp(erp_tham_chieu)
        except Exception as exc:  # noqa: BLE001 — lỗi kỹ thuật luôn là chưa xác định
            ket_qua_luu = "cho_doi_soat"
            trang_thai_task = "dang_lam"
            ly_do_luu = (
                "Lỗi kỹ thuật khi đối soát ERPNext: "
                f"{type(exc).__name__}"
            )
            thong_bao = (
                "Chưa đối soát được ERPNext; Pending Action vẫn mở "
                f"({type(exc).__name__})."
            )
        else:
            if not bang_chung:
                raise XungDotXuLyDon(
                    "ERPNext không trả về Sales Order tương ứng; không thể hoàn tất"
                )
            if str(bang_chung.get("name") or "") != erp_tham_chieu:
                raise XungDotXuLyDon("Mã Sales Order ERPNext không khớp")
            erp_trang_thai = str(bang_chung.get("status") or "")
            erp_sua_luc = _phien_ban_erp(bang_chung.get("modified"))
            da_huy = (
                int(bang_chung.get("docstatus") or 0) == 2
                or erp_trang_thai.casefold() in {"cancelled", "canceled"}
            )

            if ket_qua == "thanh_cong" and loai == "huy" and not da_huy:
                raise XungDotXuLyDon(
                    "ERPNext chưa xác nhận Sales Order đã hủy; Pending Action vẫn mở"
                )
            if ket_qua == "thanh_cong" and loai == "sua":
                if da_huy:
                    raise XungDotXuLyDon(
                        "Sales Order đã hủy, không thể xác nhận kết quả sửa thành công"
                    )
                if erp_modified_at is None:
                    raise XungDotXuLyDon(
                        "Xác nhận sửa đơn cần phiên bản modified đọc từ ERPNext"
                    )
                if _phien_ban_erp(erp_modified_at) != erp_sua_luc:
                    raise XungDotXuLyDon(
                        "Sales Order đã thay đổi so với bằng chứng được gửi; tải lại ERPNext"
                    )
            if ket_qua == "khong_the" and loai == "huy" and da_huy:
                raise XungDotXuLyDon(
                    "ERPNext cho thấy đơn đã hủy; không thể ghi kết quả là không xử lý được"
                )

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            locked = await conn.fetchrow(
                """
                SELECT id, order_id, loai_xu_ly_don, trang_thai,
                       ket_qua_xu_ly_don, nguoi_nhan
                FROM cong_viec WHERE id = $1 FOR UPDATE
                """,
                cong_viec_id,
            )
            _kiem_lien_ket_va_pham_vi(
                locked,
                order_id=order_id,
                loai=loai,
                nguoi_id=nguoi_id,
                quyen=quyen,
            )
            da_chot = _ket_qua_da_chot(
                locked, order_id=order_id, loai=loai, ket_qua=ket_qua_luu
            )
            if da_chot is not None:
                return da_chot

            await conn.execute(
                """
                UPDATE cong_viec
                SET trang_thai = $2,
                    ket_qua_xu_ly_don = $3,
                    ly_do_ket_qua = $4,
                    erp_tham_chieu = $5,
                    erp_trang_thai = $6,
                    erp_sua_luc = $7,
                    xu_ly_boi = $8,
                    xu_ly_luc = now(),
                    xong_luc = CASE WHEN $2 = 'xong' THEN now() ELSE NULL END,
                    sua_luc = now()
                WHERE id = $1
                """,
                cong_viec_id,
                trang_thai_task,
                ket_qua_luu,
                ly_do_luu[:1000],
                erp_tham_chieu or None,
                erp_trang_thai or None,
                erp_sua_luc or None,
                nguoi_id,
            )

    return KetQuaXacNhanDon(
        cong_viec_id=cong_viec_id,
        order_id=order_id,
        loai=loai,
        ket_qua=ket_qua_luu,
        trang_thai_cong_viec=trang_thai_task,
        da_xu_ly_truoc=False,
        thong_bao=thong_bao,
    )


def dieu_kien_pham_vi(*, nguoi: dict, so_tham_so: int,
                      bi_danh: str = "cong_viec",
                      chi_loc_kenh: bool = False) -> tuple[str, list[Any]]:
    """
    Mệnh đề WHERE lọc công việc theo phạm vi của người này.

    Ai có `cong_viec.xem_tat_ca` thì thấy hết. Còn lại chỉ thấy việc mình
    NHẬN, việc mình GIAO, và việc CHƯA GIAO cho ai.

    Vế "chưa giao cho ai" là cố ý, cùng lý lẽ với khách vô chủ: việc chưa
    giao mà không ai thấy thì nó không tồn tại — và việc do agent đẩy sang
    luôn ra đời ở trạng thái chưa giao.

    NHƯNG việc chưa giao gắn hội thoại thì chỉ THÀNH VIÊN KÊNH của hội
    thoại ấy thấy. Trước 16.11.2026 vế này không xét kênh: nhân viên kênh A
    đọc được tên khách và lý do chuyển người của kênh B — mà lý do là "mang
    thai", "bệnh da", dữ liệu sức khoẻ theo Luật 91/2025 — trong khi hộp
    thư thì đã lọc theo `account_memberships` từ lâu. Ai thấy mọi kênh
    (`hoi_thoai.xem_tat_ca`) thì không bị lọc kênh.

    Việc mình NHẬN hay mình GIAO thì luôn thấy, dù không thuộc kênh: người
    điều phối đã chủ ý giao, giấu nó đi là giao một việc vô hình.

    `chi_loc_kenh=True` (dùng cho SỬA/XOÁ): chỉ chặn việc thuộc kênh khác,
    không chặn việc đã giao cho người khác cùng kênh. Chặn cả vế ấy thì
    người bấm "Nhận" chậm một nhịp nhận 404 thay vì 403 "việc này đã có
    người nhận" — một câu trả lời sai về chuyện vừa xảy ra; luật giành việc
    đã có ở `api/cong_viec.py::sua`.
    """
    quyen = nguoi.get("quyen") or ()
    if "cong_viec.xem_tat_ca" in quyen:
        return "TRUE", []
    n = so_tham_so + 1
    if "hoi_thoai.xem_tat_ca" in quyen:
        cung_kenh = "TRUE"
    else:
        cung_kenh = (
            f"({bi_danh}.conversation_id IS NULL OR EXISTS ("
            f"SELECT 1 FROM conversations pv_c JOIN account_memberships pv_m "
            f"ON pv_m.account_id = pv_c.account_id "
            f"WHERE pv_c.id = {bi_danh}.conversation_id AND pv_m.user_id = ${n}))"
        )
    if chi_loc_kenh:
        return (
            f"({bi_danh}.nguoi_nhan = ${n} OR {bi_danh}.nguoi_giao = ${n} "
            f"OR {cung_kenh})",
            [str(nguoi["id"])],
        )
    return (
        f"({bi_danh}.nguoi_nhan = ${n} OR {bi_danh}.nguoi_giao = ${n} "
        f"OR ({bi_danh}.nguoi_nhan IS NULL AND {cung_kenh}))",
        [str(nguoi["id"])],
    )


async def tao_tu_yeu_cau_xu_ly_don(
    *,
    order_id: UUID,
    conversation_id: UUID | str,
    loai: str,
    tieu_de: str,
    mo_ta: str,
) -> str | None:
    """Tạo hoặc bổ sung liên kết đơn cho việc xử lý đơn do agent ghi nhận.

    Chuyển người không còn sinh việc (mục 14.2), nhưng CSDL đang chạy có thể
    còn việc tự sinh cũ đang mở trên cùng hội thoại — chiếm chỗ của
    `idx_cong_viec_agent_mot_viec`. Câu UPSERT khi ấy biến chính việc cũ
    thành việc xử lý đơn (chỉ khi nó chưa gắn với đơn khác; không bao giờ
    ghi đè nhầm), thay vì im lặng không tạo được việc huỷ đơn nào.
    """
    if loai not in LOAI_XU_LY_DON:
        raise CongViecHong(f"Loại xử lý đơn không hợp lệ: {loai!r}")
    try:
        dong = await db.fetchrow(
            """
            INSERT INTO cong_viec (
                tieu_de, mo_ta, nguon, uu_tien, conversation_id,
                contact_id, order_id, loai_xu_ly_don
            )
            SELECT $1, $2, 'agent', 'cao', $3::uuid,
                   c.contact_id, $4::uuid, $5
            FROM (SELECT 1) _
            LEFT JOIN conversations c ON c.id = $3::uuid
            ON CONFLICT (conversation_id)
                WHERE nguon = 'agent'
                  AND trang_thai IN ('moi', 'dang_lam')
            DO UPDATE SET
                order_id = EXCLUDED.order_id,
                loai_xu_ly_don = EXCLUDED.loai_xu_ly_don,
                tieu_de = EXCLUDED.tieu_de,
                mo_ta = EXCLUDED.mo_ta,
                sua_luc = now()
            WHERE cong_viec.order_id IS NULL
               OR (
                    cong_viec.order_id = EXCLUDED.order_id
                    AND cong_viec.loai_xu_ly_don = EXCLUDED.loai_xu_ly_don
               )
            RETURNING id
            """,
            tieu_de[:200],
            mo_ta[:5000],
            str(conversation_id),
            order_id,
            loai,
        )
        return str(dong["id"]) if dong is not None else None
    except Exception as exc:  # noqa: BLE001 — không làm chết lượt chat
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được công việc xử lý đơn %s: %s: %s",
            order_id,
            type(exc).__name__,
            exc,
        )
        return None


async def tao_tu_van_chuyen(
    ma_don: str, *, tieu_de: str, mo_ta: str, khoa: str,
    conversation_id=None, uu_tien: str = "cao",
) -> str | None:
    """
    Hãng vận chuyển báo một chuyện cần NGƯỜI làm: giao thất bại, mã trạng
    thái lạ. Trả id việc vừa tạo, hoặc None khi đã có việc cùng `khoa`.

    Trước bản này hai chuyện ấy chỉ là một dòng nhật ký: kiện giao hỏng
    không ai gọi khách hẹn lại, hãng hoàn hàng về sau ba lần thử, shop chịu
    phí hoàn — mà không có gì báo lỗi ở đâu (rà soát 29.10.2026).

    `khoa` gắn theo mã vận đơn + trạng thái: hãng phát lại webhook không đẻ
    việc thứ hai (chỉ mục duy nhất ở CSDL, migration 0038). Không ném khi
    hỏng — webhook vẫn phải trả lời hãng — nhưng ghi nhật ký mức lỗi.
    """
    return await _tao_viec_he_thong(
        "van_chuyen", ma_don, tieu_de=tieu_de, mo_ta=mo_ta, khoa=khoa,
        conversation_id=conversation_id, uu_tien=uu_tien,
    )


async def tao_tu_don_hang(
    ma_don: str, *, tieu_de: str, mo_ta: str, khoa: str,
    conversation_id=None, uu_tien: str = "cao",
) -> str | None:
    """
    Chính ĐƠN HÀNG cần người làm tay: ERP nhận đơn trong lúc người huỷ (đơn
    huỷ bên này, còn sống bên ERP), ERP giữ bản nháp chưa submit, hãng báo
    đã giao một đơn đã huỷ. Trước bản này ba chuyện ấy hoặc không ai biết,
    hoặc chỉ là một dòng nhật ký (rà soát 11.2026).

    Cùng khuôn `tao_tu_van_chuyen`: `khoa` chống trùng ở CSDL, không ném.
    """
    return await _tao_viec_he_thong(
        "don_hang", ma_don, tieu_de=tieu_de, mo_ta=mo_ta, khoa=khoa,
        conversation_id=conversation_id, uu_tien=uu_tien,
    )


async def tao_tu_kenh(*, tieu_de: str, mo_ta: str, khoa: str) -> str | None:
    """
    Việc về KÊNH (token sắp hết hạn, phiên mất…), nguồn `tu_dong`.

    Không gắn hội thoại hay đơn: việc là của cả kênh. Khoá chống trùng để vòng
    canh chạy mỗi ngày không sinh mỗi ngày một việc. Không bao giờ ném — vòng
    canh gọi tới không được chết vì bảng công việc nấc.
    """
    try:
        dong = await db.fetchrow(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, khoa_chong_trung) "
            "VALUES ($1, $2, 'tu_dong', 'cao', $3) "
            "ON CONFLICT DO NOTHING RETURNING id",
            tieu_de[:200], mo_ta, khoa[:300])
        if dong is None:
            return None
        from agent import canh_gac

        canh_gac.bao_nhan_vien_nen(tieu_de, "Mở dashboard → Kết nối.")
        return str(dong["id"])
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được việc kênh %s: %s: %s", khoa, type(exc).__name__, exc)
        return None


async def _tao_viec_he_thong(
    nguon: str, ma_don: str, *, tieu_de: str, mo_ta: str, khoa: str,
    conversation_id=None, uu_tien: str = "cao",
) -> str | None:
    if nguon not in NGUON:
        raise CongViecHong(f"Nguồn việc lạ: {nguon!r}")
    try:
        dong = await db.fetchrow(
            "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, uu_tien, conversation_id, "
            "                       contact_id, khoa_chong_trung) "
            # Hội thoại đã kết thúc thì việc KHÔNG gắn vào nó (vẫn gắn khách).
            # Trigger 0045 cấm việc mở trên hội thoại đã đóng — để nguyên
            # conversation_id là "giao hàng thất bại" của một khách đã chat
            # xong hôm qua bị từ chối, rơi vào nhánh except dưới đây: không
            # ai gọi khách hẹn giao lại. Mã đơn trong tiêu đề đủ để lần ra.
            "SELECT $1, $2, $6, $3, "
            "       CASE WHEN c.state IN ('resolved', 'closed') THEN NULL ELSE c.id END, "
            "       c.contact_id, $5 "
            "FROM (SELECT 1) _ LEFT JOIN conversations c ON c.id = $4::uuid "
            "ON CONFLICT DO NOTHING RETURNING id",
            tieu_de[:200], mo_ta, kiem_uu_tien(uu_tien),
            str(conversation_id) if conversation_id else None, khoa[:300], nguon,
        )
        if dong is None:
            return None
        from agent import canh_gac

        # Mã đơn là mã nội bộ của cửa hàng, không phải dữ liệu của khách.
        canh_gac.bao_nhan_vien_nen(tieu_de, f"Đơn {ma_don}. Mở dashboard → Công việc.")
        return str(dong["id"])
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.cong_viec").error(
            "KHÔNG tạo được công việc nguồn %s (đơn %s): %s: %s",
            nguon, ma_don, type(exc).__name__, exc,
        )
        return None
