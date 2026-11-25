"""
Nhật ký kiểm toán CÓ CẤU TRÚC — một mô hình đọc trên bảng `events`.

Phiếu việc mục 18 (trách nhiệm của AI), điểm 3–6, 8–13.

VÌ SAO LÀ MÔ HÌNH ĐỌC, KHÔNG VIẾT LẠI NƠI GHI
--------------------------------------------
Hơn trăm chỗ trong mã ghi `events` với `kind`/`actor`/`detail` mỗi chỗ một
kiểu: tác nhân lúc là tên đăng nhập, lúc là UUID, lúc là "system"; hội thoại
lúc ở `ref_id`, lúc ở `detail.conversation_id`, lúc ref_id là ĐƠN hay TIN.
Sửa trăm chỗ ghi là trăm chỗ để sót — và dữ liệu cũ vẫn mang dạng cũ. Nên
chuẩn hoá ở LÚC ĐỌC, một chỗ, cho cả dữ liệu cũ lẫn mới: thời gian, hội
thoại liên quan, tác nhân (AI / nhân viên tên gì / hệ thống), loại hành
động, chế độ AI, mức uỷ quyền, trạng thái xử lý, kết quả thực tế.

Phân loại (nhóm hành động, loại tác nhân, trạng thái) tính bằng SQL để lọc
và phân trang ĐÚNG trên máy chủ — lọc ở Python sau `LIMIT` là trang 1 có 3
dòng, trang 2 có 47.

BA RÀNG BUỘC, MỖI CÁI CÓ TEST CANH
---------------------------------
1. CHỈ THÊM. Bảng có trigger chặn UPDATE/DELETE (migration 0064). Sự cố,
   bước can thiệp, giải trình là DÒNG MỚI trỏ về dòng gốc bằng
   `detail.su_kien_goc` — `ghi_su_co()`, `ghi_buoc_can_thiep()`...
2. KHÔNG LỘ BÍ MẬT. `lam_sach()` chạy trên MỌI `detail` trước khi ra khỏi
   máy chủ: khoá mang tên bí mật bị che, giá trị bí mật đang cấu hình bị
   che, số điện thoại/email bị che, trường danh tính bị ẩn, suy luận nội bộ
   của model bị ẩn. Che lúc ĐỌC chứ không chỉ lúc ghi: dòng cũ đã ghi trước
   khi có quy tắc này vẫn nằm đó.
3. TẦM NHÌN. Tra toàn bộ cần `nhat_ky.doc`; nhân viên chỉ thấy nhật ký của
   hội thoại mình được xử lý (`agent/api/nhat_ky_api.py`).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from agent import db
from agent.core import che_du_lieu

CHE = "<đã che>"
AN = "[đã ẩn]"

# =====================================================================
#  LÀM SẠCH (điểm 13)
# =====================================================================

# Khoá mang bí mật, xét theo TỪNG THÀNH PHẦN giữa dấu gạch dưới: "token"
# khớp `access_token` nhưng không khớp `tokens_in` (số đếm token — thứ người
# soát chi phí cần đọc).
_KHOA_BI_MAT = re.compile(
    r"(?i)(?:^|_)(token|secret|password|passwd|pwd|mat_khau|bi_mat|apikey|key|"
    r"credential|credentials|signature|authorization|cookie|private|"
    r"qr|qr_image|qr_code|imei|session_data|session_cookie)(?:$|_)")

# Suy luận nội bộ của model: không phải căn cứ, không được lưu, không được
# hiện. Hệ thống hiện không ghi nó — danh sách này canh ngày có ai lỡ ghi.
_KHOA_SUY_LUAN = frozenset({
    "thinking", "reasoning", "suy_luan", "suy_nghi", "chain_of_thought",
    "noi_tam", "scratchpad",
})

# Trường danh tính khách — cùng danh sách đóng với dấu vết AI.
_KHOA_DANH_TINH = frozenset({
    "khach_ten", "khach_sdt", "khach_dia_chi", "khach_email",
    "ten_khach", "ho_ten", "dia_chi", "sdt", "so_dien_thoai", "email",
    "cccd", "nguoi_nhan", "ten_nguoi_nhan", "phone",
})

# Bí mật NHẬN RA ĐƯỢC BẰNG HÌNH DẠNG, kể cả khi nằm dưới một khoá vô tội
# ("loi": "...access_token=EAAB..."): token Meta, khoá OpenAI/Google, JWT.
_HINH_BI_MAT = re.compile(
    r"\b(EAA[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_\-]{16,}|AIza[0-9A-Za-z_\-]{20,}"
    r"|ya29\.[0-9A-Za-z_\-]{20,}|eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,})")

_CAT_CHUOI = 500
_TOI_DA_KHOA = 60
_TOI_DA_PHAN_TU = 50
_TOI_DA_TANG = 6


def _bi_mat_dang_cau_hinh() -> tuple[str, ...]:
    """Giá trị bí mật đang cấu hình (settings + cấu hình động) — cùng nguồn với bộ lọc log."""
    try:
        from agent.nhat_ky import LocBiMat

        return LocBiMat().bi_mat
    except Exception:  # noqa: BLE001 — làm sạch không được làm hỏng việc đọc
        return ()


def _sach_chuoi(s: str, mat_na: che_du_lieu.MatNa, bi_mat: tuple[str, ...]) -> str:
    from agent.nhat_ky import che

    s = che(s, bi_mat)
    s = _HINH_BI_MAT.sub(CHE, s)
    s = mat_na.che(s)
    return s if len(s) <= _CAT_CHUOI else s[:_CAT_CHUOI] + "…"


def lam_sach(x: Any, *, _mat_na: che_du_lieu.MatNa | None = None,
             _bi_mat: tuple[str, ...] | None = None, _tang: int = 0) -> Any:
    """
    Bản an toàn để HIỂN THỊ của một `detail` (hoặc bất kỳ giá trị JSON nào).

    Hàm thuần trên dữ liệu: không CSDL. Không bao giờ ném — dữ liệu lạ trả
    về dạng chuỗi đã làm sạch.
    """
    mat_na = _mat_na or che_du_lieu.MatNa()
    bi_mat = _bi_mat if _bi_mat is not None else _bi_mat_dang_cau_hinh()
    if _tang > _TOI_DA_TANG:
        return "…"
    if isinstance(x, str):
        return _sach_chuoi(x, mat_na, bi_mat)
    if isinstance(x, bool) or x is None or isinstance(x, (int, float)):
        return x
    if isinstance(x, dict):
        ra: dict[str, Any] = {}
        for k, v in list(x.items())[:_TOI_DA_KHOA]:
            khoa = str(k)
            thap = khoa.lower()
            if v in (None, ""):
                ra[khoa] = v
            elif _KHOA_BI_MAT.search(thap):
                ra[khoa] = CHE
            elif thap in _KHOA_SUY_LUAN or thap in _KHOA_DANH_TINH:
                ra[khoa] = AN
            else:
                ra[khoa] = lam_sach(v, _mat_na=mat_na, _bi_mat=bi_mat, _tang=_tang + 1)
        if len(x) > _TOI_DA_KHOA:
            ra["…"] = f"{len(x) - _TOI_DA_KHOA} khoá nữa không hiện"
        return ra
    if isinstance(x, (list, tuple)):
        ds = [lam_sach(v, _mat_na=mat_na, _bi_mat=bi_mat, _tang=_tang + 1)
              for v in list(x)[:_TOI_DA_PHAN_TU]]
        if len(x) > _TOI_DA_PHAN_TU:
            ds.append(f"… ({len(x) - _TOI_DA_PHAN_TU} mục nữa)")
        return ds
    return _sach_chuoi(str(x), mat_na, bi_mat)


# =====================================================================
#  PHÂN LOẠI (điểm 3)
# =====================================================================

# Nhóm hành động: (mã, nhãn, mẫu LIKE trên `kind`). THỨ TỰ CÓ NGHĨA — mẫu
# đầu tiên khớp thắng: `knowledge.retrieved` là AI tra tài liệu, các
# `knowledge.*` khác là người sửa tài liệu; `contact.retention%` là dữ liệu
# cá nhân, các `contact.*` khác là hồ sơ khách. Không khớp nhóm nào thì là
# vận hành hệ thống — kind mới không bao giờ rơi khỏi màn lọc.
NHOM_HANH_DONG: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("su_co", "Sự cố & giải trình", ("su_co.%", "nhat_ky.giai_trinh")),
    ("tra_loi_ai", "AI trả lời", (
        "ai.%", "agent.%", "dau_vet_ai.%", "che_du_lieu.%", "thong_bao_ai.%",
        "anh_khach.%", "anh.%")),
    ("tra_cuu_ai", "AI tra tài liệu & gọi công cụ", ("knowledge.retrieved", "cong_cu.%")),
    ("phe_duyet", "Duyệt / sửa bản nháp", ("tin_nhan.%",)),
    ("hoi_thoai", "Hội thoại & bàn giao", (
        "conversation.%", "banGiao.%", "csat.%", "khach.giao%", "khach.thu_hoi",
        "auto_routing.%", "auto_resolve.%", "binh_luan.%", "staff.%")),
    ("don_hang", "Đơn hàng & vận chuyển", ("order.%", "shipping.%", "thanh_toan.%")),
    ("cong_viec", "Công việc", ("cong_viec.%",)),
    ("du_lieu_ca_nhan", "Dữ liệu cá nhân", ("pdpd.%", "bvdlcn.%", "contact.retention%")),
    ("khach_hang", "Khách hàng & nhãn", (
        "contact.%", "nhan.%", "truong_khach.%", "tam_nhin_khach.%", "khach.%")),
    ("truy_cap", "Đăng nhập & phân quyền", (
        "auth.%", "nguoi_dung.%", "vai_tro.%", "phien.%")),
    ("cau_hinh", "Cấu hình & tài liệu", (
        "runtime.%", "ky_nang.%", "tich_hop.%", "ho_so_agent.%", "kenh.%", "channel.%",
        "channel_account.%", "routing.%", "tu_dong.%", "tra_loi_nhanh.%",
        "cau_hinh_api.%", "mcp.%", "lich_ca.%", "knowledge.%", "erp.xac_nhan_bang_gia",
        "erp.go_xac_nhan_bang_gia", "zalo.account.%")),
)
NHOM_MAC_DINH = ("he_thong", "Vận hành hệ thống")
NHAN_NHOM = {ma: nhan for ma, nhan, _ in NHOM_HANH_DONG} | {NHOM_MAC_DINH[0]: NHOM_MAC_DINH[1]}

# Tác nhân là AI khi: actor ghi rõ là agent, hoặc kind là việc chỉ AI làm.
# Ngoài ra MỌI việc mang `luot_id` mà actor là hệ thống — lên đơn, chuyển
# người, gọi công cụ trong một lượt AI là AI làm, chỉ là nơi ghi không biết
# điền gì vào actor ngoài "system".
_MAU_AI = ("ai.%", "agent.%", "cong_cu.%", "knowledge.retrieved", "dau_vet_ai.%",
           "che_du_lieu.%")
_ACTOR_HE_THONG = ("system", "he_thong", "", "00000000-0000-0000-0000-000000000000")
_MAU_ACTOR_HE_THONG = ("migration%", "claude:%", "don-dep%")
LOAI_TAC_NHAN = {"ai": "AI", "nhan_vien": "Nhân viên", "he_thong": "Hệ thống"}

TRANG_THAI = {
    "su_co": "Đã đánh dấu sự cố",
    "loi": "Lỗi",
    "cho_duyet": "Chờ người duyệt",
    "chuyen_nguoi": "Chuyển cho người",
    "thanh_cong": "Thành công",
}

# Nhãn cho người đọc của những hành động quan trọng; kind khác hiện nguyên.
NHAN_HANH_DONG = {
    "ai.tu_gui": "AI tự gửi trả lời",
    "ai.soan_nhap": "AI soạn nháp chờ duyệt",
    "agent.error": "AI lỗi, chuyển người",
    "agent.superseded": "Bỏ câu trả lời lỗi thời",
    "cong_cu.goi": "AI gọi công cụ",
    "knowledge.retrieved": "AI tra tài liệu",
    "conversation.escalated": "Chuyển cho người",
    "conversation.takeover": "Nhân viên tiếp quản",
    "conversation.released": "Trả hội thoại cho AI",
    "conversation.che_do": "Đổi chế độ AI của hội thoại",
    "conversation.resolved": "Giải quyết hội thoại",
    "conversation.reopened": "Mở lại hội thoại",
    "banGiao.trao_di": "Bàn giao sang hộp thư khác",
    "banGiao.nhan_lai": "Nhận lại hội thoại",
    "tin_nhan.duyet": "Duyệt bản nháp AI",
    "tin_nhan.sua_ban_nhap": "Sửa bản nháp AI",
    "tin_nhan.bo_qua_canh_bao_quang_cao": "Gửi dù có cụm cấm quảng cáo",
    "order.created": "Lên đơn",
    "order.approve": "Duyệt đơn",
    "order.cancel": "Huỷ đơn",
    "order.xin_huy": "Ghi yêu cầu huỷ đơn",
    "order.xin_doi_tra": "Ghi yêu cầu đổi trả",
    "shipping.created": "Tạo vận đơn",
    "cong_viec.tao": "Tạo công việc",
    "cong_viec.sua": "Sửa công việc",
    "nhan.gan_hoi_thoai": "Gắn nhãn hội thoại",
    "nhan.go_hoi_thoai": "Gỡ nhãn hội thoại",
    "nhan.gan_khach": "Gắn nhãn khách",
    "nhan.go_khach": "Gỡ nhãn khách",
    "runtime.update": "Đổi cấu hình AI",
    "nguoi_dung.vai_tro": "Đổi vai trò nhân viên",
    "vai_tro.tao": "Tạo vai trò",
    "auth.dang_nhap": "Đăng nhập",
    "auth.that_bai": "Đăng nhập thất bại",
    "su_co.danh_dau": "Đánh dấu sự cố",
    "su_co.can_thiep": "Bước can thiệp sự cố",
    "su_co.ket_thuc": "Kết thúc sự cố",
    "nhat_ky.giai_trinh": "Giải trình / đính chính",
    "nhat_ky.xuat": "Xuất nhật ký",
    "channel_account.created": "Tạo tài khoản kênh",
    "channel_account.status_changed": "Đổi trạng thái tài khoản kênh",
    "channel_account.identity_bound": "Gắn định danh tài khoản kênh",
    "channel_account.credentials_rotated": "Cập nhật thông tin xác thực kênh",
    "channel_account.reconnected": "Kết nối lại tài khoản kênh",
    "channel.dang_ky_webhook": "Đăng ký webhook kênh",
    "channel.dang_ky_webhook_loi": "Đăng ký webhook kênh thất bại",
    "zalo_personal.da_khoi_phuc": "Khôi phục phiên Zalo cá nhân",
    "zalo_personal.can_quet_lai": "Zalo cá nhân mất phiên (cần quét QR)",
    "zalo_personal.sidecar_khong_toi": "Sidecar Zalo cá nhân không phản hồi",
    "zalo_personal.lech_bi_mat_sidecar": "Lệch bí mật sidecar Zalo cá nhân",
    "zalo_personal.giu_phien.error": "Lỗi giữ phiên Zalo cá nhân",
    "zalo_personal.bo_tin_nhom": "Bỏ qua tin nhóm Zalo cá nhân",
    "zalo_personal.tin_bo_qua": "Bỏ qua tin Zalo cá nhân không đọc được",
    "ai.de_xuat.tao": "AI tạo đề xuất chờ duyệt",
    "ai.de_xuat.trung": "Gộp đề xuất AI trùng lặp",
    "ai.de_xuat.duyet": "Duyệt đề xuất hành động AI",
    "ai.de_xuat.thuc_hien": "Thực thi tự động đề xuất AI",
    "ai.de_xuat.cho_xu_ly_thu_cong": "Chờ xử lý thủ công đề xuất sửa đơn",
    "ai.de_xuat.xu_ly_thu_cong": "Xác nhận đã xử lý thủ công đề xuất sửa đơn",
    "ai.de_xuat.tu_choi": "Từ chối đề xuất hành động AI",
    "ai.de_xuat.het_han": "Đề xuất hành động AI hết hạn",
    "ai.de_xuat.loi": "Thực thi đề xuất hành động AI bị lỗi",
}

BUOC_CAN_THIEP = {
    "tiep_quan": "Nhân viên tiếp quản hội thoại",
    "tat_ai": "Tắt AI",
    "doi_chinh_sach": "Đổi chính sách / cấu hình",
    "lien_he_khach": "Liên hệ lại khách",
    "khac": "Việc khác",
}


def _sql_chuoi(s: str) -> str:
    """Hằng chuỗi SQL cho mẫu TRONG MÃ — chặn ký tự lạ thay vì tin là an toàn."""
    if not re.fullmatch(r"[A-Za-z0-9_.%:\-]*", s):
        raise ValueError(f"mẫu nhật ký có ký tự lạ: {s!r}")
    return "'" + s + "'"


def _like_bat_ky(cot: str, mau: tuple[str, ...]) -> str:
    return f"{cot} LIKE ANY (ARRAY[{', '.join(_sql_chuoi(m) for m in mau)}]::text[])"


def _sql_nhom() -> str:
    nhanh = "\n".join(f"      WHEN {_like_bat_ky('e.kind', mau)} THEN {_sql_chuoi(ma)}"
                      for ma, _, mau in NHOM_HANH_DONG)
    return f"CASE\n{nhanh}\n      ELSE {_sql_chuoi(NHOM_MAC_DINH[0])} END"


def _sql_actor_he_thong() -> str:
    return (f"(e.actor IN ({', '.join(_sql_chuoi(a) for a in _ACTOR_HE_THONG)}) "
            f"OR {_like_bat_ky('e.actor', _MAU_ACTOR_HE_THONG)})")


def _sql_loai_tac_nhan() -> str:
    he_thong = _sql_actor_he_thong()
    return (f"CASE WHEN e.actor IN ('agent', 'ai') OR {_like_bat_ky('e.kind', _MAU_AI)} "
            f"OR (e.detail ? 'luot_id' AND {he_thong}) THEN 'ai' "
            f"WHEN {he_thong} THEN 'he_thong' ELSE 'nhan_vien' END")


# Thành phần tên kind báo hỏng. Xét theo ranh giới `.`/`_` để `phong_thu`
# không khớp `hong`. KHÔNG có `tu_choi`: từ chối một yêu cầu xoá dữ liệu
# (`bvdlcn.tu_choi`) là một quyết định hợp lệ, không phải lỗi.
_MAU_LOI = (r"(^|[._])(error|errors|loi|that_bai|failed|chet|hong|invalid|"
            r"khong_hop_le|khong_doc_duoc|ngat_mach|khong_toi)($|[._])")

_SQL_TRANG_THAI = f"""CASE
      WHEN EXISTS (SELECT 1 FROM events s WHERE s.kind = 'su_co.danh_dau'
                     AND s.detail ? 'su_kien_goc'
                     AND s.detail ->> 'su_kien_goc' = e.id::text) THEN 'su_co'
      WHEN e.kind ~ '{_MAU_LOI}' OR e.detail ->> 'ok' = 'false'
           OR COALESCE(NULLIF(e.detail ->> 'trang_thai', ''), e.detail ->> 'status')
              IN ('loi', 'failed', 'error', 'that_bai', 'degraded', 'reauth_required') THEN 'loi'
      WHEN e.kind = 'ai.soan_nhap'
           OR COALESCE(NULLIF(e.detail ->> 'trang_thai', ''), e.detail ->> 'status') = 'cho_duyet' THEN 'cho_duyet'
      WHEN e.kind = 'conversation.escalated' THEN 'chuyen_nguoi'
      ELSE 'thanh_cong' END"""

# Hội thoại liên quan: khoá rõ ràng trong detail trước, rồi ref_id nếu nó là
# hội thoại, rồi hội thoại của TIN nếu ref_id là tin (duyệt/sửa nháp ghi
# ref_id = tin nhắn).
_SQL_HOI_THOAI = """COALESCE(
        CASE WHEN e.detail ->> 'hoi_thoai_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             THEN (e.detail ->> 'hoi_thoai_id')::uuid END,
        CASE WHEN e.detail ->> 'conversation_id' ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
             THEN (e.detail ->> 'conversation_id')::uuid END,
        cv.id, tn.conversation_id)"""

_SQL_GOC = f"""
SELECT e.id, e.kind, e.actor, e.ref_id, e.detail, e.created_at,
       nd.id AS nguoi_id,
       COALESCE(NULLIF(nd.ho_ten, ''), nd.ten_dang_nhap) AS nguoi_ten,
       ca.id AS kenh_tai_khoan_id,
       ca.display_name AS kenh_tai_khoan_ten,
       ca.channel AS kenh_tai_khoan_kenh,
       {_SQL_HOI_THOAI} AS hoi_thoai_id,
       {_sql_nhom()} AS nhom,
       {_sql_loai_tac_nhan()} AS loai_tac_nhan,
       {_SQL_TRANG_THAI} AS trang_thai
  FROM events e
  LEFT JOIN LATERAL (
       SELECT id, ho_ten, ten_dang_nhap FROM nguoi_dung
        WHERE ten_dang_nhap = e.actor
           OR id = CASE WHEN e.actor ~* '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$' THEN e.actor::uuid END
        LIMIT 1) nd ON true
  LEFT JOIN conversations cv ON cv.id = e.ref_id
  LEFT JOIN messages tn ON tn.id = e.ref_id AND cv.id IS NULL
  LEFT JOIN channel_accounts ca
    ON ca.id = COALESCE(
         CASE WHEN e.detail ? 'account_id'
               AND e.detail ->> 'account_id' ~* '^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'
              THEN (e.detail ->> 'account_id')::uuid END,
         cv.account_id,
         e.ref_id
       )
"""


def _la_su_kien_tai_khoan_kenh(kind: str, detail: dict[str, Any]) -> bool:
    return kind.startswith(("channel_account.", "zalo_personal.")) or bool(
        detail.get("account_id")
    )


def _thong_tin_tai_khoan(
    r: dict[str, Any],
    kind: str,
    sach: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Phân giải tên tài khoản từ `channel_accounts` hoặc giá trị dự phòng an toàn."""
    tk_id = (
        str(r["kenh_tai_khoan_id"])
        if r.get("kenh_tai_khoan_id")
        else (
            str(sach["account_id"]).strip()
            if isinstance(sach.get("account_id"), str) and sach["account_id"].strip()
            else (
                str(r["ref_id"])
                if _la_su_kien_tai_khoan_kenh(kind, sach) and r.get("ref_id")
                else None
            )
        )
    )
    tk_ten_goc = r.get("kenh_tai_khoan_ten")
    kenh = r.get("kenh_tai_khoan_kenh") or (
        sach.get("channel") if isinstance(sach.get("channel"), str) else None
    )
    if tk_ten_goc:
        ten = str(tk_ten_goc)
        return {"id": tk_id, "ten": ten, "kenh": kenh, "ton_tai": True}, ten
    if _la_su_kien_tai_khoan_kenh(kind, sach):
        du_phong = sach.get("display_name") or sach.get("tai_khoan")
        if isinstance(du_phong, str) and du_phong.strip():
            ten = f"{du_phong.strip()} (tài khoản đã xoá)"
        elif tk_id:
            ten = f"Tài khoản kênh đã xoá ({tk_id[:8]})"
        else:
            ten = "Tài khoản kênh không xác định"
        return {"id": tk_id, "ten": ten, "kenh": kenh, "ton_tai": False}, ten
    if r.get("hoi_thoai_id"):
        return None, f"Hội thoại {str(r['hoi_thoai_id'])[:8]}"
    if r.get("ref_id"):
        return None, str(r["ref_id"])
    return None, None


def ban_ghi(r: dict[str, Any], *, mat_na: che_du_lieu.MatNa | None = None) -> dict[str, Any]:
    """Một dòng `events` (đã qua `_SQL_GOC`) -> bản ghi có cấu trúc, ĐÃ làm sạch."""
    detail = _doc_json(r.get("detail")) or {}
    if not isinstance(detail, dict):
        detail = {"gia_tri": detail}
    sach = lam_sach(detail, _mat_na=mat_na)
    loai = r.get("loai_tac_nhan") or "he_thong"
    ten = None
    if loai == "nhan_vien":
        ten = r.get("nguoi_ten") or r.get("actor")
    elif loai == "ai":
        ten = detail.get("ho_so") if isinstance(detail.get("ho_so"), str) else None
    elif loai == "he_thong" and isinstance(sach.get("nguoi_thuc_hien"), str) and sach["nguoi_thuc_hien"].strip():
        ten = sach["nguoi_thuc_hien"].strip()
    tt = r.get("trang_thai") or "thanh_cong"
    nhom = r.get("nhom") or NHOM_MAC_DINH[0]
    tai_khoan, doi_tuong = _thong_tin_tai_khoan(r, str(r.get("kind") or ""), sach)
    return {
        "id": int(r["id"]),
        "luc": r["created_at"].isoformat() if r.get("created_at") else None,
        "kind": r["kind"],
        "hanh_dong": NHAN_HANH_DONG.get(r["kind"], r["kind"]),
        "nhom": {"ma": nhom, "nhan": NHAN_NHOM.get(nhom, nhom)},
        "tac_nhan": {
            "loai": loai, "nhan": LOAI_TAC_NHAN.get(loai, loai), "ten": ten,
            "id": str(r["nguoi_id"]) if r.get("nguoi_id") else None,
        },
        "tai_khoan": tai_khoan,
        "doi_tuong": doi_tuong,
        "hoi_thoai_id": str(r["hoi_thoai_id"]) if r.get("hoi_thoai_id") else None,
        "ref_id": str(r["ref_id"]) if r.get("ref_id") else None,
        "luot_id": detail.get("luot_id") if isinstance(detail.get("luot_id"), str) else None,
        "su_kien_goc": _so_nguyen(detail.get("su_kien_goc")),
        "che_do_ai": detail.get("che_do") if isinstance(detail.get("che_do"), str) else None,
        # Mức uỷ quyền của AI (phiếu việc mục 17) chưa có — trường có sẵn để
        # màn hình có cột và bản sau chỉ việc ghi `detail.muc_uy_quyen`.
        "muc_uy_quyen": detail.get("muc_uy_quyen") if isinstance(
            detail.get("muc_uy_quyen"), str) else None,
        "trang_thai": {"ma": tt, "nhan": TRANG_THAI.get(tt, tt)},
        "ket_qua": ket_qua(r["kind"], sach),
        "chi_tiet": sach,
    }


def _doc_json(x: Any) -> Any:
    """JSONB đọc ra: dict, hoặc CHUỖI ở dòng cũ bị mã hoá hai lần (xem db.py)."""
    if isinstance(x, str):
        import json

        try:
            return json.loads(x)
        except ValueError:
            return {"noi_dung": x}
    return x


def _so_nguyen(x: Any) -> int | None:
    try:
        return int(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


# Khoá nói lên KẾT QUẢ, theo thứ tự ưu tiên khi tóm một dòng.
_KHOA_KET_QUA = (
    "ket_qua", "ly_do", "reason", "loi", "error", "ghi_chu", "ma_don",
    "tieu_de", "trang_thai", "status", "ten", "tag", "che_do", "external_account_id",
)

_NHAN_TRANG_THAI_CHI_TIET = {
    "active": "Đang hoạt động (active)",
    "pending": "Chờ kết nối (pending)",
    "degraded": "Kết nối gián đoạn (degraded)",
    "reauth_required": "Cần xác thực lại (reauth_required)",
    "disabled": "Đã tắt (disabled)",
    "connected": "Đã kết nối (connected)",
    "disconnected": "Mất kết nối (disconnected)",
    "thanh_cong": "Thành công",
    "success": "Thành công",
    "that_bai": "Thất bại",
    "failed": "Thất bại",
    "loi": "Lỗi",
    "error": "Lỗi",
    "cho_duyet": "Chờ duyệt",
}


def _nhan_tt_chi_tiet(gia_tri: Any) -> str:
    s = str(gia_tri or "").strip()
    if not s:
        return ""
    return _NHAN_TRANG_THAI_NGHIEP_VU(s)


def _NHAN_TRANG_THAI_NGHIEP_VU(s: str) -> str:
    return _NHAN_TRANG_THAI_CHI_TIET.get(s.lower(), s)


def ket_qua(kind: str, sach: dict[str, Any]) -> str:
    """Một câu ngắn "đã xảy ra gì" từ detail ĐÃ làm sạch."""
    if kind == "ai.tu_gui":
        phan = [f"đã gửi {sach.get('so_tin') or 1} tin",
                "có căn cứ" if sach.get("co_can_cu") else "thiếu căn cứ"]
    elif kind == "ai.soan_nhap":
        phan = ["nháp chờ duyệt",
                "có căn cứ" if sach.get("co_can_cu") else "thiếu căn cứ"]
        if sach.get("chuyen_nguoi"):
            phan.append("AI xin chuyển người")
    elif kind == "cong_cu.goi":
        phan = [str(sach.get("ten") or "?"), "thành công" if sach.get("ok") else "lỗi"]
    elif kind == "knowledge.retrieved":
        nguon = sach.get("sources") or []
        phan = [f"{len(nguon) if isinstance(nguon, list) else 0} đoạn tài liệu"]
    elif kind == "channel_account.status_changed":
        st = sach.get("trang_thai") or sach.get("status")
        prev = sach.get("previous_status")
        if prev and st:
            phan = [f"{_nhan_tt_chi_tiet(prev)} → {_nhan_tt_chi_tiet(st)}"]
        elif st:
            phan = [f"trạng thái: {_nhan_tt_chi_tiet(st)}"]
        else:
            phan = ["đã đổi trạng thái tài khoản kênh"]
    elif kind == "channel_account.reconnected":
        st = sach.get("trang_thai") or sach.get("status") or "active"
        kq_tt = sach.get("ket_qua") or "thanh_cong"
        phan = [f"kết nối lại: {_nhan_tt_chi_tiet(kq_tt)}", f"trạng thái: {_nhan_tt_chi_tiet(st)}"]
        if sach.get("trigger"):
            phan.append(f"nguồn: {sach['trigger']}")
    elif kind == "channel_account.identity_bound":
        ext = sach.get("external_account_id")
        phan = [f"gắn định danh: {ext}" if ext else "đã gắn định danh tài khoản"]
    elif kind == "channel_account.credentials_rotated":
        st = sach.get("trang_thai") or sach.get("status")
        phan = ["đã làm mới thông tin xác thực"]
        if st:
            phan.append(f"trạng thái: {_nhan_tt_chi_tiet(st)}")
    elif kind == "channel_account.created":
        st = sach.get("trang_thai") or sach.get("status")
        kenh = sach.get("channel")
        phan = [f"kênh: {kenh}" if kenh else "tạo tài khoản kênh"]
        phan.append(f"trạng thái: {_nhan_tt_chi_tiet(st)}" if st else "thành công")
    elif kind == "ai.de_xuat.cho_xu_ly_thu_cong":
        phan = ["chờ xử lý thủ công — chưa sửa đơn"]
        if sach.get("loi"):
            phan.append(str(sach["loi"]))
    elif kind == "ai.de_xuat.xu_ly_thu_cong":
        kq_obj = sach.get("ket_qua") if isinstance(sach.get("ket_qua"), dict) else {}
        phan = ["đã xử lý thủ công"]
        if kq_obj.get("ma_don"):
            phan.append(f"đơn: {kq_obj['ma_don']}")
        if sach.get("ghi_chu"):
            phan.append(f"ghi chú: {sach['ghi_chu']}")
    else:
        phan = []
        da_co_trang_thai = False
        for k in _KHOA_KET_QUA:
            v = sach.get(k)
            if v in (None, "", [], {}):
                continue
            if k in ("trang_thai", "status"):
                if da_co_trang_thai:
                    continue
                da_co_trang_thai = True
                phan.append(f"trạng thái: {_nhan_tt_chi_tiet(v)}")
            else:
                phan.append(f"{k}: {v}" if not isinstance(v, (dict, list)) else f"{k}: …")
            if len(phan) >= 2:
                break
    if sach.get("luoi"):
        phan.append(f"lưới: {sach['luoi']}")
    return " · ".join(str(p) for p in phan)[:300]


# =====================================================================
#  TRUY VẤN (điểm 8)
# =====================================================================

TOI_DA_TRANG = 100


async def tim(*, tu: datetime | None = None, den: datetime | None = None,
              hoi_thoai_id: UUID | None = None, loai_tac_nhan: str | None = None,
              nguoi_id: UUID | None = None, nhom: str | None = None,
              kind: str | None = None, trang_thai: str | None = None,
              luot_id: str | None = None, truoc: int | None = None,
              limit: int = 50) -> dict[str, Any]:
    """
    Tìm theo bộ lọc, mới nhất trước, phân trang bằng con trỏ `id`.

    Con trỏ chứ không OFFSET: bảng chỉ thêm và thêm liên tục — OFFSET thì
    trang 2 lặp lại dòng cuối trang 1 mỗi khi có sự kiện mới chen vào.
    """
    limit = max(1, min(int(limit), TOI_DA_TRANG))
    dk: list[str] = []
    ts: list[Any] = []

    def them(mau: str, gia_tri: Any) -> None:
        ts.append(gia_tri)
        dk.append(mau.replace("$?", f"${len(ts)}"))

    if tu is not None:
        them("x.created_at >= $?", tu)
    if den is not None:
        them("x.created_at < $?", den)
    if hoi_thoai_id is not None:
        # Điều kiện trên CỘT GỐC (dùng được chỉ mục) chứ không trên cột tính.
        ts.append(hoi_thoai_id)
        n = len(ts)
        dk.append(f"x.id IN (SELECT id FROM events WHERE ref_id = ${n} "
                  f"UNION SELECT id FROM events WHERE detail ? 'hoi_thoai_id' "
                  f"AND detail ->> 'hoi_thoai_id' = ${n}::text "
                  f"UNION SELECT e2.id FROM events e2 JOIN messages m2 ON m2.id = e2.ref_id "
                  f"WHERE m2.conversation_id = ${n} "
                  f"UNION SELECT id FROM events WHERE detail ? 'conversation_id' "
                  f"AND detail ->> 'conversation_id' = ${n}::text)")
    if loai_tac_nhan:
        them("x.loai_tac_nhan = $?", loai_tac_nhan)
    if nguoi_id is not None:
        them("x.nguoi_id = $?", nguoi_id)
    if nhom:
        them("x.nhom = $?", nhom)
    if kind:
        them("x.kind = $?", kind)
    if trang_thai:
        them("x.trang_thai = $?", trang_thai)
    if luot_id:
        ts.append(luot_id)
        dk.append(f"x.id IN (SELECT id FROM events WHERE detail ? 'luot_id' "
                  f"AND detail ->> 'luot_id' = ${len(ts)})")
    if truoc is not None:
        them("x.id < $?", int(truoc))
    ts.append(limit + 1)
    sql = (f"SELECT * FROM ({_SQL_GOC}) x "
           f"{'WHERE ' + ' AND '.join(dk) if dk else ''} "
           f"ORDER BY x.id DESC LIMIT ${len(ts)}")
    rows = await db.fetch(sql, *ts)
    mat_na = che_du_lieu.MatNa()
    items = [ban_ghi(r, mat_na=mat_na) for r in rows[:limit]]
    return {"items": items,
            "next_cursor": items[-1]["id"] if len(rows) > limit and items else None}


async def mot(event_id: int) -> dict[str, Any] | None:
    """Một bản ghi + chuỗi sự cố/giải trình trỏ về nó (đều là dòng mới)."""
    rows = await db.fetch(f"SELECT * FROM ({_SQL_GOC}) x WHERE x.id = $1", int(event_id))
    if not rows:
        return None
    mat_na = che_du_lieu.MatNa()
    goc = ban_ghi(rows[0], mat_na=mat_na)
    lien = await db.fetch(
        f"SELECT * FROM ({_SQL_GOC}) x WHERE x.id IN ("
        "  SELECT id FROM events WHERE detail ? 'su_kien_goc' "
        "     AND detail ->> 'su_kien_goc' = $1::bigint::text"
        "  UNION"
        # Bước can thiệp/kết thúc trỏ về dòng SỰ CỐ, không về dòng gốc.
        "  SELECT b.id FROM events b JOIN events s "
        "    ON b.detail ->> 'su_co_id' = s.id::text "
        "   WHERE s.kind = 'su_co.danh_dau' AND s.detail ->> 'su_kien_goc' = $1::bigint::text"
        ") ORDER BY x.id", int(event_id))
    goc["lien_quan"] = [ban_ghi(r, mat_na=mat_na) for r in lien]
    return goc


async def hoi_thoai_cua_luot(luot_id: str) -> UUID | None:
    r = await db.fetchrow(
        f"SELECT x.hoi_thoai_id FROM ({_SQL_GOC}) x WHERE x.id IN ("
        "SELECT id FROM events WHERE detail ? 'luot_id' AND detail ->> 'luot_id' = $1) "
        "AND x.hoi_thoai_id IS NOT NULL LIMIT 1", luot_id)
    if r and r.get("hoi_thoai_id"):
        return r["hoi_thoai_id"]
    m = await db.fetchrow(
        "SELECT conversation_id FROM messages WHERE dau_vet_ai ->> 'luot_id' = $1 LIMIT 1",
        luot_id)
    return m["conversation_id"] if m else None


async def luot(luot_id: str) -> dict[str, Any] | None:
    """
    TOÀN BỘ một lượt AI (điểm 4–5): tin khách -> tra tài liệu -> công cụ ->
    lưới -> trả lời / nháp / chuyển người, theo thứ tự thời gian.

    Ảnh chụp căn cứ (điểm 5) là `dau_vet_ai` của tin trả lời: tài liệu
    (phiên bản, đoạn trích) và kết quả công cụ (dữ liệu ERP/đơn lúc xử lý),
    đã che và có trần kích thước (`agent/core/dau_vet_ai.py`).
    """
    rows = await db.fetch(
        f"SELECT * FROM ({_SQL_GOC}) x WHERE x.id IN ("
        "SELECT id FROM events WHERE detail ? 'luot_id' AND detail ->> 'luot_id' = $1"
        ") ORDER BY x.id", luot_id)
    mat_na = che_du_lieu.MatNa()
    buoc = [ban_ghi(r, mat_na=mat_na) for r in rows]
    cid = await hoi_thoai_cua_luot(luot_id)
    tin_vao_id = next((b["chi_tiet"].get("tin_vao_id") for b in buoc
                       if isinstance(b["chi_tiet"].get("tin_vao_id"), str)), None)
    tin: list[dict[str, Any]] = []
    if cid is not None:
        tin = await db.fetch(
            "SELECT id, role, content, delivery_status, created_at, dau_vet_ai, "
            "       duyet_luc, sua_boi, sua_luc, "
            "       (SELECT COALESCE(NULLIF(ho_ten, ''), ten_dang_nhap) FROM nguoi_dung "
            "         WHERE id = m.duyet_boi) AS duyet_boi_ten "
            "  FROM messages m WHERE m.conversation_id = $1 "
            "   AND (m.dau_vet_ai ->> 'luot_id' = $2 OR m.id::text = $3) "
            " ORDER BY m.created_at, m.id", cid, luot_id, tin_vao_id or "")
    for t in tin:
        dv = _doc_json(t.get("dau_vet_ai"))
        t["dau_vet_ai"] = dv if isinstance(dv, dict) else None
    if not buoc and not tin:
        return None
    if tin_vao_id is None:
        tin_vao_id = next((str((t.get("dau_vet_ai") or {}).get("tin_vao_id"))
                           for t in tin if (t.get("dau_vet_ai") or {}).get("tin_vao_id")), None)
    khach = next((t for t in tin if str(t["id"]) == str(tin_vao_id)), None)
    tra_loi = [t for t in tin if t["role"] == "agent"]
    ket = next((b for b in reversed(buoc) if b["kind"] in
                ("ai.tu_gui", "ai.soan_nhap", "agent.error", "agent.superseded",
                 "conversation.escalated")), None)
    return {
        "luot_id": luot_id,
        "hoi_thoai_id": str(cid) if cid else None,
        "tin_khach": ({"id": str(khach["id"]), "luc": khach["created_at"].isoformat(),
                       "noi_dung": lam_sach(khach.get("content") or "", _mat_na=mat_na)}
                      if khach else ({"id": tin_vao_id} if tin_vao_id else None)),
        "buoc": buoc,
        "tra_loi": [{
            "id": str(t["id"]),
            "luc": t["created_at"].isoformat(),
            "trang_thai": t.get("delivery_status"),
            "noi_dung": lam_sach(t.get("content") or "", _mat_na=mat_na),
            "dau_vet": lam_sach(t.get("dau_vet_ai") or {}, _mat_na=mat_na),
            "duyet_boi": t.get("duyet_boi_ten"),
            "duyet_luc": t["duyet_luc"].isoformat() if t.get("duyet_luc") else None,
            "sua_boi": t.get("sua_boi"),
            "sua_luc": t["sua_luc"].isoformat() if t.get("sua_luc") else None,
        } for t in tra_loi],
        "ket_qua": ket,
    }


# =====================================================================
#  ĐỀ XUẤT / PHÊ DUYỆT (điểm 6)
# =====================================================================

TRANG_THAI_DE_XUAT = {
    "cho_duyet": "Chờ duyệt",
    "da_duyet": "Đã duyệt",
    "da_sua_va_duyet": "Đã sửa rồi duyệt",
    "da_sua": "Đã sửa",
    "tu_choi": "Từ chối",
    # Vòng đời đề xuất HÀNH ĐỘNG AI (bảng ai_de_xuat, 0065/0066).
    "dang_thuc_thi": "Đang kiểm tra và xử lý yêu cầu",
    "cho_xu_ly_thu_cong": "Chờ xử lý thủ công — chưa sửa đơn",
    "da_xu_ly_thu_cong": "Đã xử lý thủ công",
    "da_thuc_hien": "Đã thực hiện",
    "loi": "Duyệt nhưng thực hiện lỗi",
    "het_han": "Hết hạn",
}

_SQL_TT_DE_XUAT = """CASE
      WHEN m.delivery_status = 'draft' THEN 'cho_duyet'
      WHEN m.duyet_boi IS NOT NULL AND m.sua_boi IS NOT NULL THEN 'da_sua_va_duyet'
      WHEN m.duyet_boi IS NOT NULL THEN 'da_duyet'
      ELSE 'da_sua' END"""


async def de_xuat(*, hoi_thoai_id: UUID | None = None, trang_thai: str | None = None,
                  truoc: datetime | None = None, limit: int = 50) -> dict[str, Any]:
    """
    Lịch sử đề xuất của AI và quyết định của người.

    HÌNH DẠNG ỔN ĐỊNH cho mục 17: mỗi bản ghi có `nguon` (hôm nay chỉ có
    `ban_nhap_ai` — bản nháp trả lời khách); phê duyệt hành động AI (lên
    đơn, huỷ đơn…) sau này thêm `nguon` mới với CÙNG các trường — đề xuất
    gì, ai/AI đề xuất, ai quyết, lúc nào, trạng thái, lượt AI nào.
    """
    limit = max(1, min(int(limit), TOI_DA_TRANG))
    dk = ["m.role = 'agent'",
          "(m.delivery_status = 'draft' OR m.duyet_boi IS NOT NULL OR m.sua_boi IS NOT NULL)"]
    ts: list[Any] = []
    if hoi_thoai_id is not None:
        ts.append(hoi_thoai_id)
        dk.append(f"m.conversation_id = ${len(ts)}")
    if trang_thai:
        ts.append(trang_thai)
        dk.append(f"({_SQL_TT_DE_XUAT}) = ${len(ts)}")
    if truoc is not None:
        ts.append(truoc)
        dk.append(f"m.created_at < ${len(ts)}")
    ts.append(limit + 1)
    rows = await db.fetch(
        f"SELECT m.id, m.conversation_id, m.created_at, m.content, "
        f"       m.dau_vet_ai ->> 'luot_id' AS luot_id, "
        f"       m.dau_vet_ai -> 'ho_so' ->> 'ten' AS ho_so, "
        f"       m.duyet_luc, m.sua_boi, m.sua_luc, "
        f"       (SELECT COALESCE(NULLIF(ho_ten, ''), ten_dang_nhap) FROM nguoi_dung "
        f"         WHERE id = m.duyet_boi) AS duyet_boi_ten, "
        f"       {_SQL_TT_DE_XUAT} AS trang_thai "
        f"  FROM messages m WHERE {' AND '.join(dk)} "
        f" ORDER BY m.created_at DESC, m.id DESC LIMIT ${len(ts)}", *ts)
    mat_na = che_du_lieu.MatNa()
    items = [{
        "id": str(r["id"]),
        "nguon": "ban_nhap_ai",
        "loai": "tra_loi_khach",
        "hoi_thoai_id": str(r["conversation_id"]),
        "luot_id": r.get("luot_id"),
        "de_xuat_boi": {"loai": "ai", "ten": r.get("ho_so") or "AI"},
        "tom_tat": lam_sach((r.get("content") or "")[:200], _mat_na=mat_na),
        "luc_de_xuat": r["created_at"].isoformat(),
        "trang_thai": {"ma": r["trang_thai"],
                       "nhan": TRANG_THAI_DE_XUAT.get(r["trang_thai"], r["trang_thai"])},
        "nguoi_quyet": r.get("duyet_boi_ten"),
        "luc_quyet": r["duyet_luc"].isoformat() if r.get("duyet_luc") else None,
        "nguoi_sua": r.get("sua_boi"),
        "luc_sua": r["sua_luc"].isoformat() if r.get("sua_luc") else None,
        "muc_uy_quyen": None,
    } for r in rows[:limit]]
    # Nguồn thứ hai: đề xuất HÀNH ĐỘNG của AI (lên đơn, huỷ đơn — bảng
    # ai_de_xuat, mục 17). Cùng hình dạng bản ghi, trộn theo thời gian; mỗi
    # nguồn lấy limit+1 nên trang sau không hụt dòng của nguồn nào.
    items.extend(await _de_xuat_hanh_dong(hoi_thoai_id, trang_thai, truoc, limit + 1, mat_na))
    items.sort(key=lambda x: x["luc_de_xuat"], reverse=True)
    con_nua = len(items) > limit or len(rows) > limit
    items = items[:limit]
    return {"items": items,
            "next_cursor": items[-1]["luc_de_xuat"] if con_nua and items else None}


async def _de_xuat_hanh_dong(hoi_thoai_id, trang_thai, truoc, gioi_han: int,
                             mat_na) -> list[dict[str, Any]]:
    dk: list[str] = ["TRUE"]
    ts: list[Any] = []
    if hoi_thoai_id is not None:
        ts.append(hoi_thoai_id)
        dk.append(f"d.conversation_id = ${len(ts)}")
    if trang_thai:
        if trang_thai == "da_xu_ly_thu_cong":
            dk.append("d.trang_thai = 'da_thuc_hien' AND d.ket_qua ->> 'qua' = 'xu_ly_thu_cong'")
        elif trang_thai == "da_thuc_hien":
            dk.append("d.trang_thai = 'da_thuc_hien' AND COALESCE(d.ket_qua ->> 'qua', '') <> 'xu_ly_thu_cong'")
        else:
            ts.append(trang_thai)
            dk.append(f"d.trang_thai = ${len(ts)}")
    if truoc is not None:
        ts.append(truoc)
        dk.append(f"d.tao_luc < ${len(ts)}")
    ts.append(gioi_han)
    rows = await db.fetch(
        "SELECT d.id, d.conversation_id, d.hanh_dong, d.trang_thai, d.muc_uy_quyen, "
        "       d.tao_luc, d.de_xuat ->> 'tieu_de' AS tieu_de, "
        "       d.ket_qua ->> 'qua' AS ket_qua_qua, "
        "       d.ket_qua ->> 'boi' AS ket_qua_boi, "
        "       d.thuc_hien_luc, "
        "       COALESCE(d.duyet_luc, d.tu_choi_luc) AS luc_quyet, "
        "       m.dau_vet_ai ->> 'luot_id' AS luot_id, "
        "       (SELECT COALESCE(NULLIF(ho_ten, ''), ten_dang_nhap) FROM nguoi_dung "
        "         WHERE id = COALESCE(d.duyet_boi, d.tu_choi_boi)) AS nguoi_quyet "
        "  FROM ai_de_xuat d LEFT JOIN messages m ON m.id = d.message_id "
        f" WHERE {' AND '.join(dk)} ORDER BY d.tao_luc DESC, d.id DESC LIMIT ${len(ts)}", *ts)
    ra: list[dict[str, Any]] = []
    for r in rows:
        ma_tt = (
            "da_xu_ly_thu_cong"
            if r["trang_thai"] == "da_thuc_hien" and r.get("ket_qua_qua") == "xu_ly_thu_cong"
            else r["trang_thai"]
        )
        luc_quyet = (
            r["thuc_hien_luc"].isoformat()
            if ma_tt == "da_xu_ly_thu_cong" and r.get("thuc_hien_luc")
            else (r["luc_quyet"].isoformat() if r.get("luc_quyet") else None)
        )
        nguoi_quyet = (
            r.get("ket_qua_boi") or r.get("nguoi_quyet")
            if ma_tt == "da_xu_ly_thu_cong"
            else r.get("nguoi_quyet")
        )
        ra.append({
            "id": str(r["id"]),
            "nguon": "hanh_dong_ai",
            "loai": r["hanh_dong"],
            "hoi_thoai_id": str(r["conversation_id"]),
            "luot_id": r.get("luot_id"),
            "de_xuat_boi": {"loai": "ai", "ten": "AI"},
            "tom_tat": lam_sach((r.get("tieu_de") or r["hanh_dong"])[:200], _mat_na=mat_na),
            "luc_de_xuat": r["tao_luc"].isoformat(),
            "trang_thai": {"ma": ma_tt,
                           "nhan": TRANG_THAI_DE_XUAT.get(ma_tt, ma_tt)},
            "nguoi_quyet": nguoi_quyet,
            "luc_quyet": luc_quyet,
            "nguoi_sua": None,
            "luc_sua": None,
            "muc_uy_quyen": r["muc_uy_quyen"],
        })
    return ra


# =====================================================================
#  SỰ CỐ VÀ GIẢI TRÌNH (điểm 10–12) — LUÔN LÀ DÒNG MỚI
# =====================================================================

class KhongThay(LookupError):
    """Dòng gốc không tồn tại."""


class KhongHopLe(ValueError):
    """Thao tác không hợp lệ với dòng này (ví dụ: sự cố đã đóng)."""


async def _ghi(kind: str, actor: str, ref_id: UUID | None, detail: dict[str, Any]) -> int:
    """
    Ghi MỘT dòng và trả id. Không qua `db.log_event`: nó nuốt lỗi (đúng cho
    nhật ký phụ của luồng chính), còn ở đây dòng nhật ký CHÍNH LÀ việc người
    dùng yêu cầu — hỏng thì phải báo họ, không được trả "đã ghi".
    """
    r = await db.fetchrow_chac(
        "INSERT INTO events (kind, actor, ref_id, detail) VALUES ($1, $2, $3, $4) "
        "RETURNING id", kind, actor, ref_id, detail)
    return int(r["id"])


async def _dong_goc(event_id: int) -> dict[str, Any]:
    rows = await db.fetch(f"SELECT * FROM ({_SQL_GOC}) x WHERE x.id = $1", int(event_id))
    if not rows:
        raise KhongThay(f"không thấy sự kiện {event_id}")
    return rows[0]


async def ghi_su_co(event_id: int, *, ghi_chu: str, boi: str) -> int:
    """Đánh dấu một hành động là SỰ CỐ. Dòng gốc không đổi một byte."""
    goc = await _dong_goc(event_id)
    if str(goc["kind"]).startswith("su_co.") or goc["kind"] == "nhat_ky.giai_trinh":
        raise KhongHopLe("không đánh dấu sự cố lên chính một dòng sự cố/giải trình")
    da = await db.fetchrow(
        "SELECT id FROM events WHERE kind = 'su_co.danh_dau' AND detail ? 'su_kien_goc' "
        "AND detail ->> 'su_kien_goc' = $1::bigint::text LIMIT 1", int(event_id))
    if da:
        raise KhongHopLe(f"sự kiện này đã được đánh dấu sự cố (#{da['id']})")
    detail = {"su_kien_goc": int(event_id), "kind_goc": goc["kind"],
              "ghi_chu": ghi_chu[:2000],
              "hoi_thoai_id": str(goc["hoi_thoai_id"]) if goc.get("hoi_thoai_id") else None}
    d_goc = _doc_json(goc.get("detail"))
    luot_goc = d_goc.get("luot_id") if isinstance(d_goc, dict) else None
    if luot_goc:
        detail["luot_id"] = luot_goc
    return await _ghi("su_co.danh_dau", boi, goc.get("hoi_thoai_id"), detail)


async def _su_co(su_co_id: int) -> dict[str, Any]:
    r = await db.fetchrow(
        "SELECT id, ref_id, detail FROM events WHERE id = $1 AND kind = 'su_co.danh_dau'",
        int(su_co_id))
    if not r:
        raise KhongThay(f"không thấy sự cố {su_co_id}")
    dong = await db.fetchrow(
        "SELECT id FROM events WHERE kind = 'su_co.ket_thuc' AND detail ->> 'su_co_id' = $1::bigint::text "
        "LIMIT 1", int(su_co_id))
    if dong:
        raise KhongHopLe("sự cố đã kết thúc — ghi giải trình nếu cần bổ sung")
    return r


async def ghi_buoc_can_thiep(su_co_id: int, *, loai: str, ghi_chu: str, boi: str) -> int:
    if loai not in BUOC_CAN_THIEP:
        raise KhongHopLe(f"loại bước lạ: {loai}")
    sc = await _su_co(su_co_id)
    d = _doc_json(sc["detail"])
    d = d if isinstance(d, dict) else {}
    return await _ghi("su_co.can_thiep", boi, sc.get("ref_id"), {
        "su_co_id": int(su_co_id), "su_kien_goc": d.get("su_kien_goc"),
        "loai": loai, "nhan": BUOC_CAN_THIEP[loai], "ghi_chu": ghi_chu[:2000]})


async def ghi_ket_thuc_su_co(su_co_id: int, *, ket_qua: str, ghi_chu: str, boi: str) -> int:
    sc = await _su_co(su_co_id)
    d = _doc_json(sc["detail"])
    d = d if isinstance(d, dict) else {}
    return await _ghi("su_co.ket_thuc", boi, sc.get("ref_id"), {
        "su_co_id": int(su_co_id), "su_kien_goc": d.get("su_kien_goc"),
        "ket_qua": ket_qua[:500], "ghi_chu": ghi_chu[:2000]})


async def ghi_giai_trinh(event_id: int, *, ghi_chu: str, boi: str) -> int:
    """Đính chính / giải trình cho một dòng — dòng mới, dòng cũ giữ nguyên."""
    goc = await _dong_goc(event_id)
    return await _ghi("nhat_ky.giai_trinh", boi, goc.get("hoi_thoai_id"), {
        "su_kien_goc": int(event_id), "kind_goc": goc["kind"], "ghi_chu": ghi_chu[:2000]})
