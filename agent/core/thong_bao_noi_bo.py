"""
Thông báo NỘI BỘ: cái chuông trên đầu dashboard.

VÌ SAO KHỐI NÀY TỒN TẠI
------------------------
Những chuyện cần người — AI chuyển hội thoại, được giao hội thoại, bản nháp
chờ duyệt, được giao việc, SLA sắp trễ — trước bản này chỉ hiện ra nếu
người trực tình cờ mở đúng màn. "Tình cờ" không phải một cơ chế.

Và mỗi lần AI chuyển giao lại đẻ một công việc "Khách cần người trả lời":
trùng nghiệp vụ với chính hội thoại đang nằm trong hàng chờ người, nên màn
Công việc đầy việc không phải việc, còn việc thật (huỷ đơn, giao hàng hỏng)
nằm lẫn trong đó. Chủ dự án chốt (mục 14.2): chuyển giao là THÔNG BÁO, công
việc chỉ dành cho việc thật.

THÔNG BÁO CHỈ NHẮC VÀ DẪN ĐƯỜNG
-------------------------------
Đọc một thông báo KHÔNG hoàn tất việc nào, KHÔNG duyệt bản nháp nào, KHÔNG
nhận hội thoại nào. Đánh dấu đã đọc chỉ đổi `da_doc_luc` của chính dòng ấy.
Thông báo cũng không bao giờ đi tới khách: không có đường nào từ bảng này
ra outbox.

AI NHẬN (`nguoi_nhan_hoi_thoai`)
-------------------------------
  1. Hội thoại đã giao cho ai (tài khoản không bị khoá) -> CHỈ người ấy.
     Người khác cùng kênh không cần biết; báo họ là dạy họ phớt lờ chuông.
  2. Chưa giao -> thành viên KÊNH của hội thoại (`account_memberships`) có
     quyền đúng việc (`hoi_thoai.nhan` cho chuyển giao và SLA,
     `hoi_thoai.tra_loi` cho bản nháp, `don.sua` cho đơn chờ duyệt).
  3. Kênh không có ai như thế -> người QUẢN LÝ (`hoi_thoai.xem_tat_ca`).
     Không lui về đây thì kênh chưa phân người là kênh mà chuông không reo
     ở đâu cả — đúng kiểu hỏng im lặng của repo này.
  4. SLA (sắp trễ / đã trễ) thì người quản lý LUÔN được báo thêm: trễ hạn
     là chuyện của người điều phối, không chỉ của người đang cầm.
  Vai trò `Quản trị` có mọi quyền (tính từ mã — xem `xac_thuc.doc_phien`),
  nên được tính như người có quyền ở mọi bước trên.

KHÔNG BAO GIỜ NÉM VÀO NƠI GỌI
------------------------------
Mọi hàm `bao_*` chạy trên đường xử lý tin khách hoặc trong vòng nền. Một
ngoại lệ ở đây làm chết cả lượt trả lời khách — để cứu một dòng thông báo ta
đánh mất câu trả lời. Nhưng cũng KHÔNG im lặng: hỏng thì ghi nhật ký mức
LỖI, và hội thoại không có ai nhận thông báo thì ghi CẢNH BÁO.
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from agent import db

log = logging.getLogger("agent.thong_bao")

# Loại -> nhãn hiện trên dashboard. CHECK ở migration (0055, 0061, 0071)
# giữ đúng tập này; test canh hai nơi không lệch nhau.
LOAI: dict[str, str] = {
    "duoc_giao_hoi_thoai": "Được giao hội thoại",
    "ai_chuyen_giao": "AI chuyển giao",
    "can_duyet": "Cần duyệt",
    "duoc_giao_viec": "Được giao việc",
    "sla_sap_tre": "SLA sắp trễ",
    "sla_tre": "SLA đã trễ",
    "viec_chua_giao": "Việc chưa phân công",
    "viec_huy": "Việc bị hủy",
    "viec_qua_han": "Việc quá hạn",
    "kenh_can_xac_thuc": "Kênh cần xác thực lại",
    "tin_nhan_that_bai": "Tin nhắn gửi thất bại",
    "duoc_giao_khach": "Được giao khách hàng",
}

_HUONG_DAN: dict[str, str] = {
    "ai_chuyen_giao": "Mở hội thoại để tiếp quản và trả lời khách.",
    "duoc_giao_hoi_thoai": "Mở hội thoại để kiểm tra và phản hồi khách.",
    "can_duyet": "Mở hội thoại hoặc màn đơn hàng để duyệt trước khi gửi.",
    "duoc_giao_viec": "Mở công việc để xem chi tiết và xử lý.",
    "sla_sap_tre": "Ưu tiên kiểm tra và phản hồi khách trước khi quá hạn SLA.",
    "sla_tre": "Hội thoại đã quá hạn SLA — ưu tiên xử lý ngay.",
    "viec_chua_giao": "Phân công nhân viên phụ trách cho công việc này.",
    "viec_huy": "Kiểm tra lại lý do hủy công việc nếu cần.",
    "viec_qua_han": "Mở công việc để xử lý hoặc cập nhật tiến độ.",
    "kenh_can_xac_thuc": "Mở Kết nối kênh để xác thực lại hoặc quét QR kết nối.",
    "tin_nhan_that_bai": "Mở hội thoại hoặc Ca trực → Tin không gửi được để gửi lại.",
    "duoc_giao_khach": "Mở hồ sơ khách hàng để theo dõi và chăm sóc.",
}

# "CẦN XỬ LÝ" hay "THÔNG TIN" (UX-19-04). Phân theo LOẠI chưa đủ: mỗi loại
# hành động mang điều kiện TÌNH TRẠNG THẬT đọc lúc hiển thị từ đúng đối tượng
# và đúng chu kỳ nghiệp vụ phát sinh thông báo — đọc KHÔNG làm xong việc.
#
# Thêm một loại mới vào LOAI mà quên xếp vào một trong hai nhóm thì test đỏ
# (test_thong_bao_noi_bo) — không xếp là loại ấy lặng lẽ thành "Thông tin".
_SLA_MA = (
    "coalesce(t.nguon_chi_tiet, "
    "CASE WHEN t.khoa_chong_trung LIKE 'sla:%' THEN split_part(t.khoa_chong_trung, ':', 2) ELSE '' END)"
)

_QUAN_LY_HT = "(pm.qt OR 'hoi_thoai.xem_tat_ca' = ANY(pm.quyen))"
def _co_quyen_duyet_sql(uid_expr: str, quyen: str) -> str:
    return (
        "EXISTS (SELECT 1 FROM nguoi_dung_vai_tro r_v "
        "JOIN vai_tro vt_v ON vt_v.id = r_v.vai_tro_id AND vt_v.dang_dung "
        "LEFT JOIN vai_tro_quyen vq_v ON vq_v.vai_tro_id = vt_v.id "
        f"WHERE r_v.nguoi_dung_id = {uid_expr} "
        f"  AND ((vt_v.he_thong AND vt_v.ten = 'Quản trị') OR vq_v.quyen = '{quyen}'))"
    )


_CO_DUYET_DON_NGUOI_NHAN = _co_quyen_duyet_sql("c_o.assigned_to", "don.sua")
_CO_DUYET_AI_NGUOI_NHAN = _co_quyen_duyet_sql("c.assigned_to", "ai.duyet")
_SLA_CK_KHOP = (
    "(t.chu_ky_nghiep_vu = c.sla_chu_ky OR ("
    "  t.chu_ky_nghiep_vu IS NULL "
    "  AND NOT EXISTS (SELECT 1 FROM sla_events se_later "
    "                  WHERE se_later.conversation_id = t.conversation_id "
    "                    AND se_later.chu_ky = c.sla_chu_ky "
    "                    AND se_later.kind = 'started' "
    "                    AND se_later.created_at > t.tao_luc) "
    "  AND (c.sla_chu_ky = 1 OR EXISTS ("
    "    SELECT 1 FROM sla_events se_cur "
    "    WHERE se_cur.conversation_id = t.conversation_id "
    "      AND se_cur.chu_ky = c.sla_chu_ky "
    f"     AND se_cur.kind = {_SLA_MA} "
    "      AND se_cur.created_at <= t.tao_luc))"
    "))"
)
_SLA_CG_KHOP = (
    "(t.chu_ky_nghiep_vu = g.lan OR ("
    "  t.chu_ky_nghiep_vu IS NULL AND t.tao_luc >= g.bat_dau "
    "  AND NOT EXISTS (SELECT 1 FROM sla_chuyen_giao g_truoc "
    "                  WHERE g_truoc.conversation_id = t.conversation_id "
    "                    AND g_truoc.lan < g.lan "
    "                    AND g_truoc.ket_thuc_luc IS NOT NULL "
    "                    AND g_truoc.ket_thuc_luc > t.tao_luc)"
    "))"
)

LOAI_HANH_DONG: dict[str, str] = {
    # Việc còn mở và VẪN của mình — bị chuyển sang người khác thì hết phần mình.
    "duoc_giao_viec": "t.da_xu_ly_luc IS NULL AND v.trang_thai IN ('moi','dang_lam') AND v.nguoi_nhan = t.nguoi_nhan_id",
    # Quá hạn: tách việc đã có người nhận (chỉ người nhận thấy Cần xử lý) vs
    # việc chưa phân công (chỉ thông báo điều phối thấy Cần xử lý khi vẫn NULL).
    "viec_qua_han": (
        "t.da_xu_ly_luc IS NULL AND v.trang_thai IN ('moi','dang_lam') AND ("
        "(v.nguoi_nhan IS NOT NULL AND v.nguoi_nhan = t.nguoi_nhan_id) "
        "OR (v.nguoi_nhan IS NULL AND coalesce(t.nguon_chi_tiet, '') <> 'nguoi_nhan' "
        "    AND (t.nguon_chi_tiet = 'chua_phan_cong' OR t.tieu_de = 'Việc quá hạn chưa ai nhận'))"
        ")"
    ),
    "viec_chua_giao": "t.da_xu_ly_luc IS NULL AND v.trang_thai IN ('moi','dang_lam') AND v.nguoi_nhan IS NULL",
    # Đơn chờ duyệt: còn ở `cho_duyet`.
    # Đề xuất AI: `ai_de_xuat` còn `cho_duyet` và chưa hết hạn.
    # Bản nháp AI: hội thoại còn mở và vẫn còn tin `role='agent', delivery_status='draft'`.
    # Khi hội thoại đã giao người phụ trách cụ thể có quyền duyệt, người khác không còn Cần xử lý.
    "can_duyet": (
        "t.da_xu_ly_luc IS NULL AND ("
        "(t.order_id IS NOT NULL AND o.trang_thai = 'cho_duyet' "
        " AND (c_o.id IS NULL OR c_o.assigned_to IS NULL OR c_o.assigned_to = t.nguoi_nhan_id "
        f"      OR ({_QUAN_LY_HT} AND NOT {_CO_DUYET_DON_NGUOI_NHAN}))) "
        "OR (t.order_id IS NULL AND (t.de_xuat_id IS NOT NULL OR coalesce(t.khoa_chong_trung, '') LIKE 'can_duyet_de_xuat:%') "
        "    AND coalesce(c.state, 'open') IN ('open','pending') "
        "    AND (c.id IS NULL OR c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id "
        f"         OR ({_QUAN_LY_HT} AND NOT {_CO_DUYET_AI_NGUOI_NHAN})) "
        "    AND coalesce(dx.trang_thai, dx_k.trang_thai) = 'cho_duyet' "
        "    AND coalesce(dx.het_han_luc, dx_k.het_han_luc) > now()) "
        "OR (t.order_id IS NULL AND t.de_xuat_id IS NULL "
        "    AND coalesce(t.khoa_chong_trung, '') NOT LIKE 'can_duyet_de_xuat:%' "
        "    AND coalesce(c.state, 'open') IN ('open','pending') "
        "    AND (c.id IS NULL OR c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id "
        f"         OR ({_QUAN_LY_HT} AND NOT {_CO_DUYET_AI_NGUOI_NHAN})) "
        "    AND EXISTS (SELECT 1 FROM messages m_dr "
        "                WHERE m_dr.conversation_id = t.conversation_id "
        "                  AND m_dr.role = 'agent' AND m_dr.delivery_status = 'draft'))"
        ")"
    ),
    # AI chuyển giao chỉ còn Cần xử lý khi hội thoại còn mở ở mode='human',
    # chưa có nhân viên tiếp quản/điều phối nhận và chưa có tin trả lời nhân viên sau lúc báo.
    "ai_chuyen_giao": (
        "t.da_xu_ly_luc IS NULL AND coalesce(c.state, 'open') IN ('open','pending') "
        "AND c.mode = 'human' "
        "AND (c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id) "
        "AND NOT EXISTS (SELECT 1 FROM conversation_assignments ca_tk "
        "                WHERE ca_tk.conversation_id = t.conversation_id "
        "                  AND ca_tk.ended_at IS NULL "
        "                  AND ca_tk.started_at >= t.tao_luc - interval '5 seconds') "
        "AND NOT EXISTS (SELECT 1 FROM messages m_nv "
        "                WHERE m_nv.conversation_id = t.conversation_id "
        "                  AND m_nv.role = 'staff' "
        "                  AND coalesce(m_nv.delivery_status, 'sent') NOT IN ('failed','dead','cancelled') "
        "                  AND m_nv.created_at >= t.tao_luc - interval '1 second')"
    ),
    "duoc_giao_hoi_thoai": (
        "t.da_xu_ly_luc IS NULL AND coalesce(c.state, 'open') IN ('open','pending') "
        "AND c.assigned_to = t.nguoi_nhan_id"
    ),
    "sla_sap_tre": (
        "t.da_xu_ly_luc IS NULL AND coalesce(c.state, 'open') IN ('open','pending') "
        f"AND (c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id OR {_QUAN_LY_HT}) AND ("
        f"({_SLA_MA} = 'first_response_warning' AND c.first_responded_at IS NULL "
        f"  AND {_SLA_CK_KHOP} "
        "  AND NOT EXISTS (SELECT 1 FROM sla_events br WHERE br.conversation_id = t.conversation_id "
        "                  AND br.chu_ky = c.sla_chu_ky AND br.kind = 'first_response_breached')) "
        f"OR ({_SLA_MA} = 'handover_response_warning' AND c.mode = 'human' "
        "  AND EXISTS (SELECT 1 FROM sla_chuyen_giao g WHERE g.conversation_id = t.conversation_id "
        "              AND g.ket_thuc_luc IS NULL AND g.vi_pham_luc IS NULL "
        f"             AND {_SLA_CG_KHOP})) "
        f"OR ({_SLA_MA} = 'resolution_warning' AND c.resolved_at IS NULL "
        f"  AND {_SLA_CK_KHOP} "
        "  AND NOT EXISTS (SELECT 1 FROM sla_events br WHERE br.conversation_id = t.conversation_id "
        "                  AND br.chu_ky = c.sla_chu_ky AND br.kind = 'resolution_breached')) "
        f"OR ({_SLA_MA} NOT IN ('first_response_warning','handover_response_warning','resolution_warning') "
        "  AND c.resolved_at IS NULL "
        "  AND (t.chu_ky_nghiep_vu = c.sla_chu_ky OR ("
        "    t.chu_ky_nghiep_vu IS NULL AND c.sla_chu_ky = 1 "
        "    AND NOT EXISTS (SELECT 1 FROM sla_events se_later WHERE se_later.conversation_id = t.conversation_id "
        "                    AND se_later.chu_ky > 1 AND se_later.created_at > t.tao_luc))))"
        ")"
    ),
    "sla_tre": (
        "t.da_xu_ly_luc IS NULL AND coalesce(c.state, 'open') IN ('open','pending') "
        f"AND (c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id OR {_QUAN_LY_HT}) AND ("
        f"({_SLA_MA} = 'first_response_breached' AND c.first_responded_at IS NULL "
        f"  AND {_SLA_CK_KHOP}) "
        f"OR ({_SLA_MA} = 'handover_response_breached' AND c.mode = 'human' "
        "  AND EXISTS (SELECT 1 FROM sla_chuyen_giao g WHERE g.conversation_id = t.conversation_id "
        "              AND g.ket_thuc_luc IS NULL "
        f"             AND {_SLA_CG_KHOP})) "
        f"OR ({_SLA_MA} = 'resolution_breached' AND c.resolved_at IS NULL "
        f"  AND {_SLA_CK_KHOP}) "
        f"OR ({_SLA_MA} NOT IN ('first_response_breached','handover_response_breached','resolution_breached') "
        "  AND c.resolved_at IS NULL "
        "  AND (t.chu_ky_nghiep_vu = c.sla_chu_ky OR ("
        "    t.chu_ky_nghiep_vu IS NULL AND c.sla_chu_ky = 1 "
        "    AND NOT EXISTS (SELECT 1 FROM sla_events se_later WHERE se_later.conversation_id = t.conversation_id "
        "                    AND se_later.chu_ky > 1 AND se_later.created_at > t.tao_luc))))"
        ")"
    ),
    "kenh_can_xac_thuc": (
        "t.da_xu_ly_luc IS NULL AND ca_tb.id IS NOT NULL "
        "AND ca_tb.status IN ('reauth_required', 'degraded')"
    ),
    "tin_nhan_that_bai": (
        "t.da_xu_ly_luc IS NULL AND ob_tb.id IS NOT NULL AND ob_tb.status = 'dead' "
        "AND (c.id IS NULL OR c.assigned_to IS NULL OR c.assigned_to = t.nguoi_nhan_id)"
    ),
}
LOAI_THONG_TIN = frozenset({"viec_huy", "duoc_giao_khach"})

_CTE_PHAM_VI = """
    WITH pm AS (
        SELECT coalesce(bool_or(NOT n.khoa), false) AS hoat_dong,
               coalesce(bool_or(vt.he_thong AND vt.ten = 'Quản trị'), false) AS qt,
               coalesce(array_agg(DISTINCT vq.quyen) FILTER (WHERE vq.quyen IS NOT NULL), ARRAY[]::text[]) AS quyen
        FROM nguoi_dung n
        LEFT JOIN nguoi_dung_vai_tro x ON x.nguoi_dung_id = n.id
        LEFT JOIN vai_tro vt ON vt.id = x.vai_tro_id AND vt.dang_dung
        LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id
        WHERE n.id = $1
    )
"""

_SQL_MO_DUOC = (
    "coalesce(pm.hoat_dong, false) AND CASE "
    "WHEN t.cong_viec_id IS NOT NULL THEN ("
    "  v.id IS NOT NULL AND (pm.qt OR ('cong_viec.doc' = ANY(pm.quyen) AND ("
    "    v.conversation_id IS NULL OR 'cong_viec.xem_tat_ca' = ANY(pm.quyen) "
    "    OR 'hoi_thoai.xem_tat_ca' = ANY(pm.quyen) OR v.nguoi_nhan = $1 "
    "    OR EXISTS (SELECT 1 FROM account_memberships am WHERE am.account_id = c_v.account_id AND am.user_id = $1)"
    "  )))"
    ") "
    "WHEN t.order_id IS NOT NULL THEN ("
    "  o.id IS NOT NULL AND (pm.qt OR ('don.doc' = ANY(pm.quyen) AND ("
    "    'khach.xem_tat_ca' = ANY(pm.quyen) OR 'hoi_thoai.xem_tat_ca' = ANY(pm.quyen) "
    "    OR EXISTS (SELECT 1 FROM account_memberships am WHERE am.account_id = c_o.account_id AND am.user_id = $1)"
    "  )))"
    ") "
    "WHEN t.conversation_id IS NOT NULL THEN ("
    "  c.id IS NOT NULL AND (pm.qt OR ('hoi_thoai.doc' = ANY(pm.quyen) AND ("
    "    'hoi_thoai.xem_tat_ca' = ANY(pm.quyen) "
    "    OR EXISTS (SELECT 1 FROM account_memberships am WHERE am.account_id = c.account_id AND am.user_id = $1)"
    "  )))"
    ") "
    "WHEN t.contact_id IS NOT NULL THEN ("
    "  ct_tb.id IS NOT NULL AND ct_tb.status <> 'deleted' AND (pm.qt OR ('khach.doc' = ANY(pm.quyen) AND ("
    "    'khach.xem_tat_ca' = ANY(pm.quyen) OR ("
    "      (ct_tb.owner_user_id IS NULL OR ct_tb.owner_user_id = $1) "
    "      AND EXISTS (SELECT 1 FROM contact_points cp_tb "
    "                  JOIN account_memberships am ON am.account_id = cp_tb.channel_account_id AND am.user_id = $1 "
    "                  WHERE cp_tb.contact_id = ct_tb.id)"
    "    )"
    "  )))"
    ") "
    "WHEN t.loai = 'duoc_giao_khach' THEN ("
    "  CASE WHEN coalesce(t.nguon_chi_tiet, '') LIKE 'hang_loat:%' THEN EXISTS ("
    "    SELECT 1 FROM contacts ct_b "
    "    WHERE ct_b.id = ANY(string_to_array(substring(t.nguon_chi_tiet FROM 11), ',')::uuid[]) "
    "      AND ct_b.status <> 'deleted' "
    "      AND (pm.qt OR ('khach.doc' = ANY(pm.quyen) AND ("
    "        'khach.xem_tat_ca' = ANY(pm.quyen) OR ("
    "          ct_b.owner_user_id = $1 "
    "          AND EXISTS (SELECT 1 FROM contact_points cp_b "
    "                      JOIN account_memberships am_b ON am_b.account_id = cp_b.channel_account_id AND am_b.user_id = $1 "
    "                      WHERE cp_b.contact_id = ct_b.id)"
    "        )"
    "      )))"
    "  ) "
    "  ELSE (pm.qt OR ('khach.doc' = ANY(pm.quyen) AND ("
    "    'khach.xem_tat_ca' = ANY(pm.quyen) OR EXISTS ("
    "      SELECT 1 FROM contacts ct_b "
    "      WHERE ct_b.status <> 'deleted' "
    "        AND ct_b.owner_user_id = $1 "
    "        AND EXISTS (SELECT 1 FROM contact_points cp_b "
    "                    JOIN account_memberships am_b ON am_b.account_id = cp_b.channel_account_id AND am_b.user_id = $1 "
    "                    WHERE cp_b.contact_id = ct_b.id)"
    "    )"
    "  ))) END"
    ") "
    "WHEN t.account_id IS NOT NULL THEN ("
    "  ca_tb.id IS NOT NULL AND (pm.qt OR (("
    "    'kenh.doc' = ANY(pm.quyen) OR 'kenh.noi' = ANY(pm.quyen) OR 'kenh.sua' = ANY(pm.quyen)"
    "  ) AND ('hoi_thoai.xem_tat_ca' = ANY(pm.quyen) "
    "         OR EXISTS (SELECT 1 FROM account_memberships am WHERE am.account_id = ca_tb.id AND am.user_id = $1))))"
    ") "
    "WHEN t.de_xuat_id IS NOT NULL THEN (coalesce(dx.id, dx_k.id) IS NOT NULL AND pm.qt) "
    "WHEN t.outbox_job_id IS NOT NULL THEN (ob_tb.id IS NOT NULL AND pm.qt) "
    "ELSE (pm.qt AND t.cong_viec_id IS NULL AND t.order_id IS NULL AND t.conversation_id IS NULL "
    "      AND t.contact_id IS NULL AND t.account_id IS NULL AND t.de_xuat_id IS NULL "
    "      AND t.outbox_job_id IS NULL AND t.loai <> 'duoc_giao_khach') END"
)

# Một biểu thức cho cả cột `can_xu_ly`, bộ lọc và số đếm — ba bản là ba định
# nghĩa "cần xử lý" lệch nhau. Đối tượng bị xoá hoặc ngoài quyền xem (`_SQL_MO_DUOC`)
# thì KHÔNG còn là "cần xử lý" của người đó.
_SQL_CAN_XU_LY_GOC = "coalesce(CASE t.loai " + " ".join(
    f"WHEN '{loai}' THEN ({dk})" for loai, dk in LOAI_HANH_DONG.items()
) + " ELSE false END, false)"
_SQL_CAN_XU_LY = f"(({_SQL_CAN_XU_LY_GOC}) AND ({_SQL_MO_DUOC}))"
_JOIN_TINH_TRANG = (
    "CROSS JOIN pm "
    "LEFT JOIN conversations c ON c.id = t.conversation_id "
    "LEFT JOIN cong_viec v ON v.id = t.cong_viec_id "
    "LEFT JOIN conversations c_v ON c_v.id = v.conversation_id "
    "LEFT JOIN orders o ON o.id = t.order_id "
    "LEFT JOIN conversations c_o ON c_o.id = o.conversation_id "
    "LEFT JOIN ai_de_xuat dx ON dx.id = t.de_xuat_id "
    "LEFT JOIN ai_de_xuat dx_k ON t.de_xuat_id IS NULL AND t.khoa_chong_trung = 'can_duyet_de_xuat:' || dx_k.id::text "
    "LEFT JOIN channel_accounts ca_tb ON ca_tb.id = t.account_id "
    "LEFT JOIN contacts ct_tb ON ct_tb.id = t.contact_id "
    "LEFT JOIN outbox_jobs ob_tb ON ob_tb.id = t.outbox_job_id "
)

_MA_KY_THUAT_RE = re.compile(
    r"\s*\((?:tool_calls|tool_use|malformed_function_call|max_tokens|length|safety|recitation|content_filter|refusal|\d+(?:\.\d+)?)\)\s*",
    re.IGNORECASE,
)


def chuan_hoa_noi_dung_thong_bao(loai: str, noi_dung: str | None) -> str:
    """Chuẩn hóa nội dung thông báo sang tiếng Việt rõ ràng cho nhân viên.

    Loại bỏ mã kỹ thuật thô (`tool_calls`, `tool_use`, điểm độ tin cậy thô...)
    nhưng giữ đúng bản chất vấn đề: lỗi kỹ thuật / thiếu căn cứ / cần tiếp quản.
    Dữ liệu kỹ thuật thô vẫn được giữ nguyên trong `events` và `dau_vet_ai`.
    """
    goc = " ".join(str(noi_dung or "").split())
    if loai != "ai_chuyen_giao":
        return goc
    low = goc.lower()
    if any(k in low for k in ("tool_calls", "tool_use", "malformed_function_call", "gọi công cụ")):
        return "AI gặp lỗi kỹ thuật khi gọi công cụ hỗ trợ — chưa thể tự trả lời khách."
    if any(k in low for k in ("max_tokens", "giới hạn độ dài")):
        return "AI phản hồi bị gián đoạn do vượt giới hạn độ dài — cần nhân viên trả lời tiếp."
    if "safety" in low or "content_filter" in low or "recitation" in low:
        return "Nội dung cần nhân viên kiểm tra an toàn và phản hồi trực tiếp cho khách."
    if "model dừng bất thường" in low or "lỗi kỹ thuật" in low:
        return "AI gặp sự cố kỹ thuật khi xử lý câu trả lời — cần nhân viên tiếp quản."
    if "độ tin cậy thấp" in low or "không đủ căn cứ" in low or "chưa đủ căn cứ" in low:
        return "AI chưa đủ căn cứ rõ ràng từ tài liệu — cần nhân viên kiểm tra và phản hồi khách."
    sach = _MA_KY_THUAT_RE.sub(" ", goc).strip(" .—-")
    return sach or "Hội thoại cần nhân viên kiểm tra và tiếp quản."

# Quyền "người quản lý" — người được báo khi kênh không có ai, và luôn được
# báo khi SLA trễ. Dùng lại đúng quyền đã nói "thấy mọi kênh": người không
# thấy hội thoại thì báo cho họ chỉ là một dòng bấm vào ra 404.
QUYEN_QUAN_LY = "hoi_thoai.xem_tat_ca"

TEN_KENH = {
    "zalo_personal": "Zalo cá nhân", "zalo_oa": "Zalo OA",
    "facebook": "Facebook", "instagram": "Instagram",
    "whatsapp": "WhatsApp", "webchat": "Chat web",
}

# Người có quyền X (hoặc vai trò Quản trị), không bị khoá. `coalesce` vì
# LEFT JOIN vào `vai_tro_quyen` cho NULL ở vai trò không có dòng quyền nào,
# và `bool_or` toàn NULL ra NULL chứ không ra false.
_SQL_CO_QUYEN = """
    SELECT n.id
    FROM nguoi_dung n
    JOIN nguoi_dung_vai_tro x ON x.nguoi_dung_id = n.id
    JOIN vai_tro vt ON vt.id = x.vai_tro_id AND vt.dang_dung
    LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id
    WHERE NOT n.khoa
    GROUP BY n.id
    HAVING coalesce(bool_or(vq.quyen = $1 OR (vt.he_thong AND vt.ten = 'Quản trị')), false)
"""


@asynccontextmanager
async def _ket_noi(conn: Any = None) -> AsyncIterator[Any]:
    if conn is not None:
        yield conn
        return
    async with db.pool().acquire() as moi:
        yield moi


def _ngan(chu: str | None, toi_da: int) -> str:
    chu = " ".join(str(chu or "").split())
    return chu if len(chu) <= toi_da else chu[: toi_da - 1] + "…"


def _uuid(x: Any) -> UUID:
    return x if isinstance(x, UUID) else UUID(str(x))


async def _nguoi_co_quyen(conn: Any, quyen: str) -> list[UUID]:
    return [r["id"] for r in await conn.fetch(_SQL_CO_QUYEN, quyen)]


async def nguoi_nhan_hoi_thoai(
    conn: Any, conversation_id: UUID | str, *, quyen: str,
    them_quan_ly: bool = False,
) -> list[UUID]:
    """Ai được báo về hội thoại này — luật ở docstring đầu tệp."""
    cid = _uuid(conversation_id)
    c = await conn.fetchrow(
        "SELECT c.account_id, c.assigned_to, (n.id IS NOT NULL AND NOT n.khoa) AS giao_song "
        "FROM conversations c LEFT JOIN nguoi_dung n ON n.id = c.assigned_to "
        "WHERE c.id = $1", cid)
    if c is None:
        return []
    quan_ly: list[UUID] | None = None
    if c["assigned_to"] is not None and c["giao_song"]:
        chinh = [c["assigned_to"]]
    else:
        co_quyen = set(await _nguoi_co_quyen(conn, quyen))
        thanh_vien = {
            r["user_id"] for r in await conn.fetch(
                "SELECT user_id FROM account_memberships WHERE account_id = $1",
                c["account_id"])
        }
        chinh = sorted(co_quyen & thanh_vien, key=str)
        if not chinh:
            quan_ly = await _nguoi_co_quyen(conn, QUYEN_QUAN_LY)
            chinh = list(quan_ly)
    if them_quan_ly:
        if quan_ly is None:
            quan_ly = await _nguoi_co_quyen(conn, QUYEN_QUAN_LY)
        chinh = list(dict.fromkeys([*chinh, *quan_ly]))
    return chinh


async def _ghi(
    conn: Any, nguoi_nhan: Iterable[UUID], *, loai: str, tieu_de: str,
    noi_dung: str = "", conversation_id: UUID | None = None,
    cong_viec_id: UUID | None = None, order_id: UUID | None = None,
    de_xuat_id: UUID | None = None, account_id: UUID | None = None,
    contact_id: UUID | None = None, outbox_job_id: UUID | None = None,
    chu_ky_nghiep_vu: int | None = None, nguon_chi_tiet: str | None = None,
    khoa: str | None = None,
) -> int:
    """
    Chèn một dòng cho mỗi người nhận. Trả số dòng MỚI.

    Trùng khoá với một thông báo CHƯA ĐỌC thì không chèn dòng thứ hai mà đẩy
    dòng cũ lên đầu (`tao_luc = now()`) với nội dung mới: khách nhắn thêm vào
    hội thoại đang chờ duyệt thì người trực thấy nó mới, nhưng chuông không
    đếm thành mười.
    """
    if loai not in LOAI:
        raise ValueError(f"Loại thông báo lạ: {loai!r}")
    ids = list(dict.fromkeys(_uuid(x) for x in nguoi_nhan))
    if not ids:
        return 0
    rows = await conn.fetch(
        """
        INSERT INTO thong_bao (nguoi_nhan_id, loai, tieu_de, noi_dung,
                               conversation_id, cong_viec_id, order_id,
                               de_xuat_id, account_id, contact_id, outbox_job_id,
                               chu_ky_nghiep_vu, nguon_chi_tiet, khoa_chong_trung)
        SELECT u, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        FROM unnest($1::uuid[]) AS u
        ON CONFLICT (nguoi_nhan_id, khoa_chong_trung)
            WHERE da_doc_luc IS NULL AND khoa_chong_trung IS NOT NULL
        DO UPDATE SET tao_luc = now(), tieu_de = EXCLUDED.tieu_de,
                      noi_dung = EXCLUDED.noi_dung,
                      da_xu_ly_luc = NULL,
                      chu_ky_nghiep_vu = coalesce(EXCLUDED.chu_ky_nghiep_vu, thong_bao.chu_ky_nghiep_vu),
                      nguon_chi_tiet = coalesce(EXCLUDED.nguon_chi_tiet, thong_bao.nguon_chi_tiet)
        RETURNING (xmax = 0) AS moi
        """,
        ids, loai, _ngan(tieu_de, 200), _ngan(noi_dung, 500),
        conversation_id, cong_viec_id, order_id,
        de_xuat_id, account_id, contact_id, outbox_job_id,
        chu_ky_nghiep_vu, nguon_chi_tiet, khoa[:300] if khoa else None,
    )
    return sum(1 for r in rows if r["moi"])


def _loi(viec: str, ref: Any, exc: BaseException) -> None:
    log.error("KHÔNG tạo được thông báo %s (%s): %s: %s",
              viec, ref, type(exc).__name__, exc)


def _khong_ai_nhan(viec: str, ref: Any) -> None:
    log.warning("Thông báo %s (%s) không có ai nhận: không người được giao, "
                "không thành viên kênh có quyền, không người quản lý.", viec, ref)


# ---------------------------------------------------------------------------
#  Nguồn sinh thông báo. MỌI hàm dưới đây không ném.
# ---------------------------------------------------------------------------

async def bao_ai_chuyen_giao(
    conversation_id: UUID | str, *, ly_do: str, conn: Any = None,
) -> int:
    """
    AI (hoặc hệ thống thay AI: agent tắt, lỗi kỹ thuật, quy tắc tự động,
    tin nhóm) vừa chuyển hội thoại cho người.

    Thay cho việc tự sinh "Khách cần người trả lời" (mục 14.2). Cùng với
    thông báo, giữ tin báo NGOÀI dashboard (`canh_gac.bao_nhan_vien_nen`)
    như trước — nhưng chỉ khi có ít nhất một thông báo MỚI. Trước đây chốt
    "một việc mỗi hội thoại" làm việc chống dội cho tin báo ngoài; nay chốt
    "một thông báo chưa đọc mỗi người" làm thay: khách nhắn thêm mười tin
    vào hội thoại đã chuyển người không thành mười tin Telegram.
    """
    try:
        async with _ket_noi(conn) as c:
            nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="hoi_thoai.nhan")
            moi = await _ghi(
                c, nhan, loai="ai_chuyen_giao",
                tieu_de="AI chuyển hội thoại cho nhân viên",
                noi_dung=chuan_hoa_noi_dung_thong_bao("ai_chuyen_giao", ly_do),
                conversation_id=_uuid(conversation_id),
                khoa=f"ai_chuyen_giao:{_uuid(conversation_id)}",
            )
            kenh = await c.fetchval(
                "SELECT ca.channel FROM conversations cv "
                "LEFT JOIN channel_accounts ca ON ca.id = cv.account_id WHERE cv.id = $1",
                _uuid(conversation_id))
        if not nhan:
            _khong_ai_nhan("ai_chuyen_giao", conversation_id)
        if moi or not nhan:
            _bao_ngoai(kenh or "")
        return moi
    except Exception as exc:  # noqa: BLE001 — không làm chết lượt trả lời khách
        _loi("ai_chuyen_giao", conversation_id, exc)
        # Thông báo hỏng thì tin báo ngoài là đường DUY NHẤT còn lại để có
        # người biết — gửi, dù có thể trùng.
        _bao_ngoai("")
        return 0


def _bao_ngoai(kenh: str) -> None:
    """
    Tin báo NGOÀI dashboard (n8n / Telegram / Zalo bot). Chỉ nói KÊNH, không
    nói lý do hay lời khách: lý do chuyển người có thể là "mang thai", "bệnh
    da" — dữ liệu sức khoẻ theo Luật 91/2025, không đi sang bên thứ ba chỉ để
    báo "có việc".
    """
    try:
        from agent import canh_gac

        canh_gac.bao_nhan_vien_nen(
            "Khách cần người trả lời",
            f"Kênh {TEN_KENH.get(kenh, kenh or 'không rõ')}: agent đã chuyển hội thoại "
            "cho người. Mở dashboard → chuông thông báo hoặc Công việc → Tổng quan ca trực để nhận.")
    except Exception as exc:  # noqa: BLE001
        _loi("bao_ngoai", kenh, exc)


async def bao_duoc_giao_hoi_thoai(
    conversation_id: UUID | str, nguoi_nhan_id: UUID | str, *,
    boi: UUID | str | None = None, tu_dong: bool = False, conn: Any = None,
) -> int:
    """
    Hội thoại vừa được giao cho một người. Tự nhận (người giao = người nhận)
    thì KHÔNG báo: báo người ta về việc họ vừa tự bấm là tiếng ồn.
    """
    if boi is not None and str(boi) == str(nguoi_nhan_id):
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(nguoi_nhan_id)], loai="duoc_giao_hoi_thoai",
                tieu_de="Bạn được giao một hội thoại",
                noi_dung="Định tuyến tự động" if tu_dong else "Người điều phối giao",
                conversation_id=_uuid(conversation_id),
                khoa=f"duoc_giao:{_uuid(conversation_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("duoc_giao_hoi_thoai", conversation_id, exc)
        return 0


async def bao_can_duyet_nhap(conversation_id: UUID | str, *, conn: Any = None) -> int:
    """
    Chế độ Gợi ý: AI vừa soạn một bản nháp chờ người duyệt. Một thông báo
    CHƯA ĐỌC mỗi hội thoại mỗi người — AI soạn nháp cho từng tin khách.
    """
    try:
        async with _ket_noi(conn) as c:
            # `ai.duyet`, không `hoi_thoai.tra_loi`: chuông "cần duyệt" gửi
            # cho người KHÔNG bấm được nút Duyệt là chuông họ học cách bỏ qua.
            nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="ai.duyet")
            if not nhan:
                _khong_ai_nhan("can_duyet", conversation_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de="Bản nháp AI chờ duyệt",
                noi_dung="AI đã soạn câu trả lời, cần người duyệt trước khi gửi.",
                conversation_id=_uuid(conversation_id),
                khoa=f"can_duyet:{_uuid(conversation_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet", conversation_id, exc)
        return 0


async def bao_can_duyet_don(
    order_id: UUID | str, *, conversation_id: UUID | str | None, ma_don: str,
    conn: Any = None,
) -> int:
    """
    AI vừa lên một đơn vượt ngưỡng tự chốt — đơn nằm ở `cho_duyet` tới khi
    có người duyệt. Mã đơn là mã nội bộ của cửa hàng, không phải dữ liệu
    của khách.
    """
    try:
        async with _ket_noi(conn) as c:
            if conversation_id is not None:
                nhan = await nguoi_nhan_hoi_thoai(c, conversation_id, quyen="don.sua")
            else:
                nhan = await _nguoi_co_quyen(c, "don.sua")
            if not nhan:
                _khong_ai_nhan("can_duyet_don", order_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de=f"Đơn {ma_don} chờ duyệt",
                noi_dung="AI đã lên đơn vượt ngưỡng tự chốt — cần người duyệt.",
                conversation_id=_uuid(conversation_id) if conversation_id else None,
                order_id=_uuid(order_id),
                khoa=f"can_duyet_don:{_uuid(order_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet_don", order_id, exc)
        return 0


async def nguoi_duyet_de_xuat(
    conn: Any, conversation_id: UUID | str, quyen: Iterable[str],
) -> list[UUID]:
    """
    Ai được báo về một đề xuất hành động của AI: người có ĐỦ các quyền duyệt
    (`ai.duyet` + quyền nghiệp vụ của hành động) và THẤY được hội thoại.

    Khác `nguoi_nhan_hoi_thoai`: người đang cầm hội thoại chưa chắc duyệt
    được (nhân viên mới trả lời được nhưng chưa được huỷ đơn). Báo người
    không bấm được Duyệt là dạy họ phớt lờ chuông — nên lọc theo quyền ở
    MỌI nhánh, kể cả nhánh người được giao.
    """
    cid = _uuid(conversation_id)
    co_du: set[UUID] | None = None
    for q in quyen:
        bo = set(await _nguoi_co_quyen(conn, q))
        co_du = bo if co_du is None else co_du & bo
    if not co_du:
        return []
    c = await conn.fetchrow(
        "SELECT account_id, assigned_to FROM conversations WHERE id = $1", cid)
    if c is None:
        return []
    thanh_vien = {r["user_id"] for r in await conn.fetch(
        "SELECT user_id FROM account_memberships WHERE account_id = $1", c["account_id"])}
    chinh = co_du & thanh_vien
    if c["assigned_to"] in co_du:
        chinh.add(c["assigned_to"])
    if not chinh:
        chinh = co_du & set(await _nguoi_co_quyen(conn, QUYEN_QUAN_LY))
    return sorted(chinh, key=str)


async def bao_can_duyet_de_xuat(
    conversation_id: UUID | str, de_xuat_id: UUID | str, *, tieu_de: str,
    quyen_thi_hanh: str | None, conn: Any = None,
) -> int:
    """
    AI vừa chuẩn bị một hành động cần duyệt (mục 17). Chỉ gắn HỘI THOẠI, không
    gắn đơn: bấm vào phải mở đúng hội thoại có thẻ đề xuất, không phải màn Đơn
    hàng (`_lien_ket` ưu tiên đơn nếu có).
    """
    try:
        dx_id = _uuid(de_xuat_id)
        async with _ket_noi(conn) as c:
            quyen = ["ai.duyet", *([quyen_thi_hanh] if quyen_thi_hanh else [])]
            nhan = await nguoi_duyet_de_xuat(c, conversation_id, quyen)
            if not nhan:
                _khong_ai_nhan("can_duyet_de_xuat", de_xuat_id)
            return await _ghi(
                c, nhan, loai="can_duyet",
                tieu_de=f"AI đề xuất: {tieu_de}",
                noi_dung="AI đã chuẩn bị một hành động, cần người có thẩm quyền duyệt.",
                conversation_id=_uuid(conversation_id),
                de_xuat_id=dx_id,
                khoa=f"can_duyet_de_xuat:{dx_id}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("can_duyet_de_xuat", de_xuat_id, exc)
        return 0


async def bao_duoc_giao_viec(
    cong_viec_id: UUID | str, nguoi_nhan_id: UUID | str, *,
    boi: UUID | str | None, tieu_de_viec: str, conn: Any = None,
    chuyen: bool = False, tu_dong: bool = False,
) -> int:
    """
    Một việc vừa được giao (hoặc CHUYỂN từ người khác) cho người này. Tự giao
    cho mình thì không báo. Chuyển và giao mới cùng một loại chuông — với
    người nhận đều là "có việc mới của tôi" — chỉ khác tiêu đề, để họ biết
    việc này đã có người làm dở.
    """
    if boi is not None and str(boi) == str(nguoi_nhan_id):
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(nguoi_nhan_id)], loai="duoc_giao_viec",
                tieu_de="Bạn được chuyển một việc" if chuyen else "Bạn được giao một việc",
                noi_dung=tieu_de_viec + (" (phân công tự động)" if tu_dong else ""),
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"duoc_giao_viec:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("duoc_giao_viec", cong_viec_id, exc)
        return 0


async def nguoi_dieu_phoi_viec(conn: Any, cong_viec_id: UUID | str) -> list[UUID]:
    """
    Ai được báo về một việc CHƯA AI NHẬN: người có `cong_viec.giao` (hoặc
    Quản trị) THẤY được việc ấy — việc gắn hội thoại thì phải thuộc kênh hoặc
    thấy mọi kênh. Báo người không mở được việc là một dòng bấm vào ra 404,
    và tệ hơn là đưa tên khách kênh khác cho họ đọc.
    """
    from agent.core import cong_viec as cv

    rows = await conn.fetch(
        cv.SQL_VIEC_VA_QUYEN
        + f"SELECT q.id FROM quyen q, viec WHERE q.giao AND {cv.SQL_CUNG_KENH} ORDER BY q.id",
        _uuid(cong_viec_id))
    return [r["id"] for r in rows]


async def bao_viec_chua_giao(
    cong_viec_id: UUID | str, *, tieu_de_viec: str, ly_do: str = "",
    tru: UUID | str | None = None, conn: Any = None,
) -> int:
    """
    Việc ra đời (hoặc bị thu hồi người nhận) mà không ai nhận — "Chưa phân
    công" là danh sách không ai mở nếu không có chuông. `tru` = người vừa
    thao tác: họ biết rồi.
    """
    try:
        async with _ket_noi(conn) as c:
            nhan = [u for u in await nguoi_dieu_phoi_viec(c, cong_viec_id)
                    if tru is None or str(u) != str(tru)]
            if not nhan and tru is None:
                _khong_ai_nhan("viec_chua_giao", cong_viec_id)
            return await _ghi(
                c, nhan, loai="viec_chua_giao",
                tieu_de="Việc chưa phân công",
                noi_dung=tieu_de_viec + (f" — {ly_do}" if ly_do else ""),
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"viec_chua_giao:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_chua_giao", cong_viec_id, exc)
        return 0


async def bao_viec_huy(
    cong_viec_id: UUID | str, *, nguoi_nhan: Iterable[UUID | str | None],
    boi: UUID | str | None, tieu_de_viec: str, conn: Any = None,
) -> int:
    """
    Việc bị hủy: báo người đang làm và người đã tạo — trừ chính người hủy.
    Không báo thì người nhận tiếp tục gọi khách cho một việc đã bỏ.
    """
    ids = [x for x in nguoi_nhan if x is not None and (boi is None or str(x) != str(boi))]
    if not ids:
        return 0
    try:
        async with _ket_noi(conn) as c:
            return await _ghi(
                c, [_uuid(x) for x in ids], loai="viec_huy",
                tieu_de="Việc đã bị hủy", noi_dung=tieu_de_viec,
                cong_viec_id=_uuid(cong_viec_id),
                khoa=f"viec_huy:{_uuid(cong_viec_id)}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_huy", cong_viec_id, exc)
        return 0


async def bao_viec_qua_han(
    cong_viec_id: UUID | str, *, nguoi_nhan_id: UUID | str | None,
    tieu_de_viec: str, conn: Any = None,
) -> int:
    """
    Việc chưa xong đã qua hạn: báo người đang làm; chưa ai làm thì báo
    người điều phối — việc quá hạn mà không có chủ là việc dễ rơi nhất.
    """
    try:
        async with _ket_noi(conn) as c:
            vid = _uuid(cong_viec_id)
            nhan = ([_uuid(nguoi_nhan_id)] if nguoi_nhan_id is not None
                    else await nguoi_dieu_phoi_viec(c, vid))
            if not nhan:
                _khong_ai_nhan("viec_qua_han", cong_viec_id)
            return await _ghi(
                c, nhan, loai="viec_qua_han",
                tieu_de="Việc đã quá hạn" if nguoi_nhan_id else "Việc quá hạn chưa ai nhận",
                noi_dung=tieu_de_viec,
                cong_viec_id=vid,
                nguon_chi_tiet="nguoi_nhan" if nguoi_nhan_id is not None else "chua_phan_cong",
                khoa=f"viec_qua_han:{vid}:{nguoi_nhan_id or 'chung'}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("viec_qua_han", cong_viec_id, exc)
        return 0


async def dong_bo_doi_nguoi_viec(
    cong_viec_id: UUID | str, nguoi_nhan_moi: UUID | str | None, *,
    tieu_de_viec: str = "", conn: Any = None,
) -> None:
    """
    BUG-TB-05: khi công việc đổi người nhận, đóng các thông báo `viec_qua_han`
    của người nhận cũ / người điều phối trước đó và phát lại cho người nhận mới
    nếu việc vẫn còn mở và đã quá hạn.
    """
    if conn is None and getattr(db, "_pool", None) is None:
        return
    try:
        vid = _uuid(cong_viec_id)
        moi_u = _uuid(nguoi_nhan_moi) if nguoi_nhan_moi is not None else None
        async with _ket_noi(conn) as c:
            v = await c.fetchrow(
                "SELECT tieu_de, trang_thai, han, nguoi_nhan, bao_qua_han_luc "
                "FROM cong_viec WHERE id = $1",
                vid,
            )
            if v is None:
                return
            if moi_u is not None:
                await c.execute(
                    "UPDATE thong_bao SET da_xu_ly_luc = coalesce(da_xu_ly_luc, now()), "
                    "khoa_chong_trung = NULL "
                    "WHERE cong_viec_id = $1 AND loai IN ('viec_qua_han', 'duoc_giao_viec') "
                    "AND nguoi_nhan_id <> $2",
                    vid, moi_u,
                )
            else:
                await c.execute(
                    "UPDATE thong_bao SET da_xu_ly_luc = coalesce(da_xu_ly_luc, now()), "
                    "khoa_chong_trung = NULL "
                    "WHERE cong_viec_id = $1 AND loai IN ('viec_qua_han', 'duoc_giao_viec')",
                    vid,
                )
            qua_han = bool(
                v["trang_thai"] in ("moi", "dang_lam")
                and v["han"] is not None
                and v["han"] <= datetime.now(timezone.utc)
            )
            if qua_han:
                tieu_de = tieu_de_viec.strip() or (v["tieu_de"] or "")
                await c.execute(
                    "UPDATE cong_viec SET bao_qua_han_luc = coalesce(bao_qua_han_luc, now()) WHERE id = $1",
                    vid,
                )
                await bao_viec_qua_han(
                    vid, nguoi_nhan_id=moi_u, tieu_de_viec=tieu_de, conn=c,
                )
    except Exception as exc:  # noqa: BLE001
        _loi("dong_bo_doi_nguoi_viec", cong_viec_id, exc)


_SLA = {
    "first_response_warning": ("sla_sap_tre", "SLA sắp trễ: khách chưa được trả lời"),
    "first_response_breached": ("sla_tre", "SLA đã trễ: quá hạn phản hồi đầu"),
    # Cảnh báo hạn giải quyết (migration 0054) — cùng loại "sắp trễ".
    "resolution_warning": ("sla_sap_tre", "SLA sắp trễ: gần hạn giải quyết"),
    "resolution_breached": ("sla_tre", "SLA đã trễ: quá hạn giải quyết"),
    # Hạn phản hồi sau chuyển giao (migration 0062) — cùng hai loại, cùng
    # người nhận: người đang cầm (hoặc thành viên kênh) CỘNG người quản lý.
    # Khoá chống dội theo hội thoại như các mục tiêu khác: lượt chuyển giao
    # sau mà thông báo lượt trước còn chưa đọc thì dòng ấy được đẩy lên đầu
    # với nội dung mới, không thành hai dòng.
    "handover_response_warning": (
        "sla_sap_tre", "SLA sắp trễ: chưa nhân viên nào nhắn sau khi AI chuyển giao"),
    "handover_response_breached": (
        "sla_tre", "SLA đã trễ: quá hạn phản hồi sau chuyển giao"),
}


async def bao_sla(conn: Any, su_kien: Iterable[tuple[UUID, str]]) -> int:
    """
    Gọi SAU khi bộ canh SLA đã chèn sự kiện (mỗi sự kiện chỉ chèn được một
    lần nhờ khoá (hội thoại, chu kỳ, loại) — nên đây cũng chỉ một lần).

    Người nhận: người đang cầm hoặc thành viên kênh, CỘNG người quản lý.
    Gắn `chu_ky_nghiep_vu` và `nguon_chi_tiet` để khi nhân viên phản hồi hoặc
    mở chu kỳ mới, trạng thái Cần xử lý / Đã xử lý phản ánh đúng lượt đó.
    """
    tong = 0
    for cid, kind in su_kien:
        if kind not in _SLA:
            continue
        loai, tieu_de = _SLA[kind]
        cid_u = _uuid(cid)
        try:
            nhan = await nguoi_nhan_hoi_thoai(
                conn, cid_u, quyen="hoi_thoai.nhan", them_quan_ly=True)
            if not nhan:
                _khong_ai_nhan(loai, cid)
            if kind.startswith("handover_response_"):
                chu_ky = int(await conn.fetchval(
                    "SELECT coalesce(max(lan), 1) FROM sla_chuyen_giao "
                    "WHERE conversation_id = $1 AND ket_thuc_luc IS NULL", cid_u) or 1)
                khoa = f"sla:{kind}:{cid_u}:lan{chu_ky}"
            else:
                chu_ky = int(await conn.fetchval(
                    "SELECT coalesce(sla_chu_ky, 1) FROM conversations WHERE id = $1", cid_u) or 1)
                khoa = f"sla:{kind}:{cid_u}:ck{chu_ky}"
            tong += await _ghi(
                conn, nhan, loai=loai, tieu_de=tieu_de,
                conversation_id=cid_u, chu_ky_nghiep_vu=chu_ky,
                nguon_chi_tiet=kind, khoa=khoa,
            )
        except Exception as exc:  # noqa: BLE001 — vòng SLA không được chết vì chuông
            _loi(loai, cid, exc)
    return tong


async def nguoi_nhan_kenh(conn: Any, account_id: UUID | str) -> list[UUID]:
    """
    Người nhận cảnh báo mất kết nối kênh cần xác thực lại: thành viên kênh có
    quyền `kenh.noi` hoặc `kenh.sua`; kênh chưa có thành viên có quyền thì báo
    quản lý (`hoi_thoai.xem_tat_ca`) có quyền nối/sửa kênh.
    """
    aid = _uuid(account_id)
    co_quyen = set(await _nguoi_co_quyen(conn, "kenh.noi")) | set(await _nguoi_co_quyen(conn, "kenh.sua"))
    if not co_quyen:
        return []
    thanh_vien = {
        r["user_id"] for r in await conn.fetch(
            "SELECT user_id FROM account_memberships WHERE account_id = $1", aid)
    }
    chinh = sorted(co_quyen & thanh_vien, key=str)
    if chinh:
        return chinh
    quan_ly = set(await _nguoi_co_quyen(conn, QUYEN_QUAN_LY))
    return sorted(co_quyen & quan_ly, key=str)


async def bao_kenh_can_xac_thuc(
    account_id: UUID | str, *, ten_tai_khoan: str, kenh: str,
    ly_do: str = "", conn: Any = None,
) -> int:
    """GAP-TB-01: kênh chuyển sang cần xác thực lại / quét QR / đăng nhập lại."""
    try:
        aid = _uuid(account_id)
        kenh_nhan = TEN_KENH.get(kenh, kenh or "kênh")
        ten = (ten_tai_khoan or str(aid))[:80]
        nd = ly_do.strip() or f"Kênh {kenh_nhan} «{ten}» cần xác thực lại để tiếp tục nhận và gửi tin."
        async with _ket_noi(conn) as c:
            # BUG-TB-08: sự cố token Meta đã tạo cong_viec đang mở thì không phát trùng kenh_can_xac_thuc.
            if (kenh or "").lower() in ("facebook", "instagram"):
                da_co_viec = await c.fetchval(
                    "SELECT 1 FROM cong_viec "
                    "WHERE khoa_chong_trung LIKE 'kenh:token_meta:' || $1 || ':%' "
                    "  AND trang_thai IN ('moi', 'dang_lam') LIMIT 1",
                    str(aid),
                )
                if da_co_viec:
                    return 0
            nhan = await nguoi_nhan_kenh(c, aid)
            if not nhan:
                _khong_ai_nhan("kenh_can_xac_thuc", aid)
            return await _ghi(
                c, nhan, loai="kenh_can_xac_thuc",
                tieu_de=f"Kênh {kenh_nhan} «{ten}» cần xác thực lại",
                noi_dung=nd, account_id=aid,
                khoa=f"kenh_can_xac_thuc:{aid}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("kenh_can_xac_thuc", account_id, exc)
        return 0


async def ket_thuc_kenh_xac_thuc(conn: Any, account_id: UUID | str) -> None:
    """Kênh đã kết nối/xác thực lại thành công: đóng chu kỳ thông báo cũ (giữ da_doc)."""
    if conn is None and getattr(db, "_pool", None) is None:
        return
    aid = _uuid(account_id)
    async with _ket_noi(conn) as c:
        await c.execute(
            "UPDATE thong_bao SET da_xu_ly_luc = coalesce(da_xu_ly_luc, now()), "
            "khoa_chong_trung = NULL "
            "WHERE account_id = $1 AND loai = 'kenh_can_xac_thuc' AND da_xu_ly_luc IS NULL",
            aid)


async def ket_thuc_duyet_nhap(conn: Any, conversation_id: UUID | str) -> None:
    """Khi hội thoại không còn bản nháp chờ duyệt, chốt thông báo `can_duyet` nháp."""
    if conn is None and getattr(db, "_pool", None) is None:
        return
    cid = _uuid(conversation_id)
    async with _ket_noi(conn) as c:
        con_nhap = await c.fetchval(
            "SELECT 1 FROM messages WHERE conversation_id = $1 "
            "AND role = 'agent' AND delivery_status = 'draft' LIMIT 1", cid)
        if con_nhap:
            return
        await c.execute(
            "UPDATE thong_bao SET khoa_chong_trung = NULL, "
            "da_xu_ly_luc = coalesce(da_xu_ly_luc, now()) "
            "WHERE conversation_id = $1 AND loai = 'can_duyet' "
            "AND order_id IS NULL AND de_xuat_id IS NULL "
            "AND coalesce(khoa_chong_trung, '') NOT LIKE 'can_duyet_de_xuat:%'",
            cid)


async def ket_thuc_duyet_de_xuat(conn: Any, de_xuat_id: UUID | str) -> None:
    """Đề xuất AI đã được duyệt/từ chối/hết hạn: chốt thông báo `can_duyet` tương ứng."""
    if conn is None and getattr(db, "_pool", None) is None:
        return
    dx_id = _uuid(de_xuat_id)
    async with _ket_noi(conn) as c:
        await c.execute(
            "UPDATE thong_bao SET khoa_chong_trung = NULL, "
            "da_xu_ly_luc = coalesce(da_xu_ly_luc, now()) "
            "WHERE loai = 'can_duyet' AND ("
            "  de_xuat_id = $1 OR khoa_chong_trung = 'can_duyet_de_xuat:' || $1::text"
            ")",
            dx_id)


async def ket_thuc_duyet_don(conn: Any, order_id: UUID | str) -> None:
    """Đơn đã rời trạng thái `cho_duyet`: chốt thông báo `can_duyet` của đơn."""
    if conn is None and getattr(db, "_pool", None) is None:
        return
    oid = _uuid(order_id)
    async with _ket_noi(conn) as c:
        await c.execute(
            "UPDATE thong_bao SET khoa_chong_trung = NULL, "
            "da_xu_ly_luc = coalesce(da_xu_ly_luc, now()) "
            "WHERE order_id = $1 AND loai = 'can_duyet'",
            oid)


async def ket_thuc_tin_nhan_that_bai(conn: Any, outbox_job_id: UUID | str) -> None:
    """BUG-TB-03: khi outbox retry/cancel thành công, đóng chu kỳ lỗi cũ và giữ da_doc."""
    if conn is None and getattr(db, "_pool", None) is None:
        return
    jid = _uuid(outbox_job_id)
    async with _ket_noi(conn) as c:
        await c.execute(
            "UPDATE thong_bao SET da_xu_ly_luc = coalesce(da_xu_ly_luc, now()), "
            "khoa_chong_trung = NULL "
            "WHERE outbox_job_id = $1 AND loai = 'tin_nhan_that_bai' "
            "  AND (da_xu_ly_luc IS NULL OR khoa_chong_trung IS NOT NULL)",
            jid,
        )


async def bao_tin_nhan_that_bai(
    outbox_job_id: UUID | str, *, conversation_id: UUID | str | None,
    account_id: UUID | str | None = None, gui_boi: UUID | str | None = None,
    loi: str = "", conn: Any = None,
) -> int:
    """GAP-TB-03: tin gửi ra thất bại vĩnh viễn (`outbox_jobs.status = 'dead'`)."""
    try:
        jid = _uuid(outbox_job_id)
        async with _ket_noi(conn) as c:
            nhan: list[UUID] = []
            cid = _uuid(conversation_id) if conversation_id else None
            aid = _uuid(account_id) if account_id else None
            if cid is not None:
                nhan = await nguoi_nhan_hoi_thoai(
                    c, cid, quyen="hoi_thoai.tra_loi", them_quan_ly=True)
                if gui_boi is not None:
                    gid = _uuid(gui_boi)
                    co_quyen_gui = gid in set(await _nguoi_co_quyen(c, "hoi_thoai.tra_loi"))
                    cung_kenh = bool(await c.fetchval(
                        "SELECT 1 FROM account_memberships m JOIN conversations cv ON cv.account_id = m.account_id "
                        "WHERE cv.id = $1 AND m.user_id = $2", cid, gid)) or (
                        gid in set(await _nguoi_co_quyen(c, QUYEN_QUAN_LY)))
                    if co_quyen_gui and cung_kenh and gid not in nhan:
                        nhan.append(gid)
            elif aid is not None:
                co_outbox = set(await _nguoi_co_quyen(c, "outbox.doc"))
                quan_ly = set(await _nguoi_co_quyen(c, QUYEN_QUAN_LY))
                nhan = sorted(co_outbox & quan_ly, key=str) or sorted(quan_ly, key=str)
            if not nhan:
                _khong_ai_nhan("tin_nhan_that_bai", jid)
            mo_ta = f"Tin nhắn gửi khách thất bại sau nhiều lần thử. {loi.strip()}".strip()
            return await _ghi(
                c, nhan, loai="tin_nhan_that_bai",
                tieu_de="Tin nhắn gửi khách thất bại",
                noi_dung=mo_ta, conversation_id=cid, account_id=aid,
                outbox_job_id=jid, khoa=f"tin_nhan_that_bai:{jid}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("tin_nhan_that_bai", outbox_job_id, exc)
        return 0


async def bao_duoc_giao_khach(
    contact_id: UUID | str | None, nguoi_nhan_id: UUID | str, *,
    boi: UUID | str | None = None, ten_khach: str = "", ly_do: str = "",
    so_luong: int = 1, contact_ids: Iterable[UUID | str] | None = None,
    conn: Any = None,
) -> int:
    """GAP-TB-04: được giao phụ trách 1 khách hoặc giao hàng loạt (gom 1 dòng)."""
    if boi is not None and str(boi) == str(nguoi_nhan_id):
        return 0
    try:
        uid = _uuid(nguoi_nhan_id)
        async with _ket_noi(conn) as c:
            song = await c.fetchval("SELECT 1 FROM nguoi_dung WHERE id = $1 AND NOT khoa", uid)
            if not song:
                return 0
            if so_luong > 1 or contact_id is None:
                ds_id = list(dict.fromkeys(str(_uuid(x)) for x in (contact_ids or [])))
                nguon_ct = ("hang_loat:" + ",".join(ds_id)) if ds_id else "hang_loat"
                return await _ghi(
                    c, [uid], loai="duoc_giao_khach",
                    tieu_de=f"Bạn được giao phụ trách {max(1, int(so_luong))} khách hàng",
                    noi_dung=ly_do.strip() or "Mở danh sách Khách hàng để theo dõi.",
                    nguon_chi_tiet=nguon_ct,
                    khoa=f"duoc_giao_khach:hang_loat:{uid}",
                )
            ct_id = _uuid(contact_id)
            ten = (ten_khach or "").strip()
            tieu_de = f"Bạn được giao phụ trách khách {ten}" if ten else "Bạn được giao phụ trách một khách hàng"
            return await _ghi(
                c, [uid], loai="duoc_giao_khach",
                tieu_de=tieu_de,
                noi_dung=ly_do.strip() or "Mở hồ sơ khách hàng để theo dõi.",
                contact_id=ct_id,
                khoa=f"duoc_giao_khach:{ct_id}",
            )
    except Exception as exc:  # noqa: BLE001
        _loi("duoc_giao_khach", contact_id or nguoi_nhan_id, exc)
        return 0


async def dong_bo_chuyen_nguoi_hoi_thoai(
    conversation_id: UUID | str, nguoi_nhan_moi: UUID | str | None, *,
    conn: Any = None,
) -> None:
    """
    BUG-TB-05: khi hội thoại đổi người phụ trách, đảm bảo người nhận mới được
    nhận các cảnh báo còn hiệu lực (SLA chưa xử lý, nháp/đề xuất/đơn chờ duyệt,
    tin outbox dead) nếu họ có quyền tương ứng.
    """
    if nguoi_nhan_moi is None or (conn is None and getattr(db, "_pool", None) is None):
        return
    try:
        cid = _uuid(conversation_id)
        uid = _uuid(nguoi_nhan_moi)
        async with _ket_noi(conn) as c:
            co = set()
            rows_q = await c.fetch(
                "SELECT DISTINCT vq.quyen FROM nguoi_dung_vai_tro x "
                "JOIN vai_tro vt ON vt.id = x.vai_tro_id AND vt.dang_dung "
                "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = vt.id "
                "WHERE x.nguoi_dung_id = $1",
                uid,
            )
            qt = bool(await c.fetchval(
                "SELECT 1 FROM nguoi_dung_vai_tro x JOIN vai_tro vt ON vt.id = x.vai_tro_id AND vt.dang_dung "
                "WHERE x.nguoi_dung_id = $1 AND vt.he_thong AND vt.ten = 'Quản trị'", uid))
            co = {r["quyen"] for r in rows_q if r["quyen"]}

            cv = await c.fetchrow(
                "SELECT state, mode, first_responded_at, resolved_at, sla_chu_ky "
                "FROM conversations WHERE id = $1", cid)
            if cv is None or cv["state"] not in ("open", "pending"):
                return

            # 1) SLA còn hiệu lực của chu kỳ hiện tại
            if qt or "hoi_thoai.nhan" in co:
                sla_rows = await c.fetch(
                    "SELECT kind FROM sla_events "
                    "WHERE conversation_id = $1 AND chu_ky = $2",
                    cid, cv["sla_chu_ky"],
                )
                kinds = {r["kind"] for r in sla_rows}
                sla_can_bao: list[tuple[UUID, str]] = []
                if cv["first_responded_at"] is None:
                    if "first_response_breached" in kinds:
                        sla_can_bao.append((cid, "first_response_breached"))
                    elif "first_response_warning" in kinds:
                        sla_can_bao.append((cid, "first_response_warning"))
                if cv["resolved_at"] is None:
                    if "resolution_breached" in kinds:
                        sla_can_bao.append((cid, "resolution_breached"))
                    elif "resolution_warning" in kinds:
                        sla_can_bao.append((cid, "resolution_warning"))
                if cv["mode"] == "human":
                    cg = await c.fetchrow(
                        "SELECT lan, canh_bao_luc, vi_pham_luc FROM sla_chuyen_giao "
                        "WHERE conversation_id = $1 AND ket_thuc_luc IS NULL", cid)
                    if cg is not None:
                        if cg["vi_pham_luc"] is not None:
                            sla_can_bao.append((cid, "handover_response_breached"))
                        elif cg["canh_bao_luc"] is not None:
                            sla_can_bao.append((cid, "handover_response_warning"))
                for _, k in sla_can_bao:
                    loai, tieu_de = _SLA[k]
                    ck = (await c.fetchval(
                        "SELECT coalesce(max(lan), 1) FROM sla_chuyen_giao "
                        "WHERE conversation_id = $1 AND ket_thuc_luc IS NULL", cid)
                        if k.startswith("handover_response_") else cv["sla_chu_ky"])
                    suffix = f"lan{ck}" if k.startswith("handover_response_") else f"ck{ck}"
                    await _ghi(
                        c, [uid], loai=loai, tieu_de=tieu_de,
                        conversation_id=cid, chu_ky_nghiep_vu=int(ck or 1),
                        nguon_chi_tiet=k, khoa=f"sla:{k}:{cid}:{suffix}",
                    )

            # 2) Nháp AI / đề xuất AI chờ duyệt
            if qt or "ai.duyet" in co:
                if await c.fetchval(
                    "SELECT 1 FROM messages WHERE conversation_id = $1 "
                    "AND role = 'agent' AND delivery_status = 'draft' LIMIT 1", cid
                ):
                    await _ghi(
                        c, [uid], loai="can_duyet",
                        tieu_de="Bản nháp AI chờ duyệt",
                        noi_dung="AI đã soạn câu trả lời, cần người duyệt trước khi gửi.",
                        conversation_id=cid, khoa=f"can_duyet:{cid}",
                    )
                dx_rows = await c.fetch(
                    "SELECT id, de_xuat, hanh_dong FROM ai_de_xuat "
                    "WHERE conversation_id = $1 AND trang_thai = 'cho_duyet' AND het_han_luc > now()",
                    cid,
                )
                for dx in dx_rows:
                    td = (dx["de_xuat"] or {}).get("tieu_de") if isinstance(dx["de_xuat"], dict) else ""
                    await _ghi(
                        c, [uid], loai="can_duyet",
                        tieu_de=f"Cần duyệt: {td or dx['hanh_dong']}",
                        noi_dung="AI đề xuất hành động cần bạn duyệt trước khi thực thi.",
                        conversation_id=cid, de_xuat_id=dx["id"],
                        khoa=f"can_duyet_de_xuat:{dx['id']}",
                    )

            # 3) Tin gửi lỗi outbox dead
            if qt or "hoi_thoai.tra_loi" in co:
                dead_rows = await c.fetch(
                    "SELECT id, account_id, last_error FROM outbox_jobs "
                    "WHERE conversation_id = $1 AND status = 'dead'", cid)
                for ob in dead_rows:
                    mo_ta = f"Tin nhắn gửi khách thất bại sau nhiều lần thử. {str(ob['last_error'] or '').strip()}".strip()
                    await _ghi(
                        c, [uid], loai="tin_nhan_that_bai",
                        tieu_de="Tin nhắn gửi khách thất bại",
                        noi_dung=mo_ta, conversation_id=cid, account_id=ob["account_id"],
                        outbox_job_id=ob["id"], khoa=f"tin_nhan_that_bai:{ob['id']}",
                    )
    except Exception as exc:  # noqa: BLE001
        _loi("dong_bo_chuyen_nguoi_hoi_thoai", conversation_id, exc)


async def ket_thuc_luot_chuyen_giao(
    conn: Any, conversation_id: UUID | str, *, danh_dau_da_xu_ly: bool = False,
) -> None:
    """
    Lượt chuyển giao đã kết thúc (tiếp quản, giải quyết, hoặc trả lại AI):
    gỡ khoá chống dội khỏi thông báo chuyển giao để lần chuyển giao sau không
    bị nuốt. Nếu `danh_dau_da_xu_ly=True` (ví dụ lúc tiếp quản), chốt `da_xu_ly_luc`
    mà KHÔNG chạm `da_doc_luc` (đọc != xử lý).
    """
    cid = _uuid(conversation_id)
    if danh_dau_da_xu_ly:
        await conn.execute(
            "UPDATE thong_bao SET khoa_chong_trung = NULL, "
            "da_xu_ly_luc = coalesce(da_xu_ly_luc, now()) "
            "WHERE conversation_id = $1 AND loai = 'ai_chuyen_giao' "
            "AND (khoa_chong_trung = 'ai_chuyen_giao:' || $1::text OR da_xu_ly_luc IS NULL)",
            cid)
    else:
        await conn.execute(
            "UPDATE thong_bao SET khoa_chong_trung = NULL "
            "WHERE conversation_id = $1 AND da_doc_luc IS NULL "
            "AND khoa_chong_trung = 'ai_chuyen_giao:' || $1::text",
            cid)


# ---------------------------------------------------------------------------
#  Đọc — luôn theo ĐÚNG người đang đăng nhập.
# ---------------------------------------------------------------------------

def _lien_ket(r: dict) -> dict | None:
    """Bấm vào thì đi đâu. Việc trước, rồi đơn, rồi hội thoại, rồi khách/kênh."""
    if r.get("cong_viec_id"):
        return {"loai": "cong_viec", "id": str(r["cong_viec_id"])}
    if r.get("order_id"):
        return {"loai": "don_hang", "id": str(r["order_id"]),
                "hoi_thoai_id": str(r["conversation_id"]) if r.get("conversation_id") else None}
    if r.get("conversation_id"):
        return {"loai": "hoi_thoai", "id": str(r["conversation_id"])}
    if r.get("contact_id"):
        return {"loai": "khach_hang", "id": str(r["contact_id"])}
    if r.get("loai") == "duoc_giao_khach":
        return {"loai": "khach_hang", "id": None}
    if r.get("account_id"):
        return {"loai": "tai_khoan_kenh", "id": str(r["account_id"])}
    return None


def nhom_thong_bao(loai: str, can_xu_ly: bool) -> str:
    """`can_xu_ly` | `da_xu_ly` (loại hành động nhưng thứ ấy đã xong) | `thong_tin`."""
    if loai in LOAI_THONG_TIN or loai not in LOAI_HANH_DONG:
        return "thong_tin"
    return "can_xu_ly" if can_xu_ly else "da_xu_ly"


def _ket_qua_va_nhan_trang_thai(
    r: Any, *, nhom: str, can_xu_ly: bool,
) -> tuple[str | None, str | None]:
    """
    BUG-TB-07: phân biệt trạng thái hoàn tất của thông báo (`nhom`) với kết quả
    nghiệp vụ thực tế để không gán nhầm nhãn 'Đã xử lý' cho đề xuất/đơn hết hạn,
    từ chối hoặc thực thi lỗi.
    """
    if nhom == "thong_tin":
        return "thong_tin", "Thông tin"
    if can_xu_ly:
        return "can_xu_ly", "Cần xử lý"
    loai = r["loai"]
    if loai == "can_duyet":
        dx_tt = r["dx_trang_thai"]
        dx_hh = r["dx_het_han_luc"]
        if dx_tt is not None:
            if dx_tt == "het_han" or (
                dx_tt == "cho_duyet" and dx_hh is not None
                and dx_hh <= datetime.now(timezone.utc)
            ):
                return "het_han", "Đã hết hạn"
            if dx_tt == "tu_choi":
                return "tu_choi", "Đã từ chối"
            if dx_tt == "loi":
                return "loi", "Thực thi lỗi"
            if dx_tt == "cho_xu_ly_thu_cong":
                return "cho_xu_ly_thu_cong", "Chờ xử lý thủ công"
            return dx_tt, "Đã xử lý"
        don_tt = r["don_trang_thai"]
        if don_tt is not None:
            if don_tt == "da_huy":
                return "da_huy", "Đã hủy"
            return don_tt, "Đã xử lý"
        if r["nhap_trang_thai"] == "cancelled":
            return "tu_choi", "Đã từ chối"
    elif loai == "tin_nhan_that_bai":
        ob_tt = r["outbox_trang_thai"]
        if ob_tt == "cancelled":
            return "da_huy", "Đã hủy gửi"
    return "da_xu_ly", "Đã xử lý"


async def liet_ke(nguoi_id: UUID, *, chi_chua_doc: bool = False,
                  chi_can_xu_ly: bool = False,
                  gioi_han: int = 20, bo_qua: int = 0) -> list[dict]:
    """
    Tên khách đọc qua hội thoại/khách hàng lúc hiển thị, không chép vào bảng — xem
    migration 0055. Kiểm soát quyền và phạm vi kênh ngay tại câu SQL đọc.

    `chi_can_xu_ly` lọc ở SQL chứ không ở trình duyệt: danh sách phân trang
    20 dòng một, lọc sau khi cắt trang thì "Xem thêm" ra trang rỗng dù còn
    việc cần xử lý ở trang sau.
    """
    rows = await db.fetch(
        f"{_CTE_PHAM_VI}"
        "SELECT t.id, t.loai, t.tieu_de, t.noi_dung, t.conversation_id, "
        "       t.cong_viec_id, t.order_id, t.contact_id, t.account_id, "
        "       t.tao_luc, t.da_doc_luc, "
        "       coalesce(c.customer_name, ct_tb.display_name) AS ten_khach, "
        "       coalesce(ca.channel, ca_tb.channel) AS kenh, "
        "       coalesce(dx.trang_thai, dx_k.trang_thai) AS dx_trang_thai, "
        "       coalesce(dx.het_han_luc, dx_k.het_han_luc) AS dx_het_han_luc, "
        "       o.trang_thai AS don_trang_thai, "
        "       ob_tb.status AS outbox_trang_thai, "
        "       (SELECT m_l.delivery_status FROM messages m_l "
        "        WHERE t.loai = 'can_duyet' AND t.order_id IS NULL "
        "          AND t.de_xuat_id IS NULL AND coalesce(t.khoa_chong_trung, '') NOT LIKE 'can_duyet_de_xuat:%' "
        "          AND m_l.conversation_id = t.conversation_id AND m_l.role = 'agent' "
        "        ORDER BY m_l.created_at DESC, m_l.id DESC LIMIT 1) AS nhap_trang_thai, "
        f"      {_SQL_MO_DUOC} AS mo_duoc, "
        f"      {_SQL_CAN_XU_LY} AS can_xu_ly "
        "FROM thong_bao t "
        f"{_JOIN_TINH_TRANG}"
        "LEFT JOIN channel_accounts ca ON ca.id = c.account_id "
        "WHERE t.nguoi_nhan_id = $1 AND ($2::bool IS FALSE OR t.da_doc_luc IS NULL) "
        f"  AND ($5::bool IS FALSE OR {_SQL_CAN_XU_LY}) "
        "ORDER BY t.tao_luc DESC, t.id DESC LIMIT $3 OFFSET $4",
        nguoi_id, chi_chua_doc, gioi_han, bo_qua, chi_can_xu_ly)
    ra = []
    for r in rows:
        mo_duoc = bool(r["mo_duoc"])
        can_xu_ly = bool(r["can_xu_ly"]) and mo_duoc
        nhom = nhom_thong_bao(r["loai"], can_xu_ly)
        if mo_duoc:
            ket_qua, nhan_trang_thai = _ket_qua_va_nhan_trang_thai(
                r, nhom=nhom, can_xu_ly=can_xu_ly)
        else:
            ket_qua, nhan_trang_thai = None, None
        ra.append({
            "can_xu_ly": can_xu_ly,
            "nhom": nhom,
            "ket_qua_nghiep_vu": ket_qua,
            "nhan_trang_thai": nhan_trang_thai,
            "mo_duoc": mo_duoc,
            "ly_do_khong_mo": None if mo_duoc else "Đối tượng đã bị xóa hoặc bạn không còn quyền truy cập.",
            "id": str(r["id"]),
            "loai": r["loai"],
            "nhan_loai": LOAI.get(r["loai"], r["loai"]),
            "tieu_de": r["tieu_de"] if mo_duoc else LOAI.get(r["loai"], "Thông báo nội bộ"),
            "noi_dung": (chuan_hoa_noi_dung_thong_bao(r["loai"], r["noi_dung"])
                         if mo_duoc
                         else "Thông báo thuộc đối tượng đã xóa hoặc bạn không còn quyền truy cập."),
            "huong_dan": _HUONG_DAN.get(r["loai"], "") if mo_duoc else "",
            "ten_khach": r["ten_khach"] if mo_duoc else None,
            "kenh": TEN_KENH.get(r["kenh"] or "", r["kenh"]) if mo_duoc else None,
            "tao_luc": r["tao_luc"].isoformat(),
            "da_doc": r["da_doc_luc"] is not None,
            "lien_ket": _lien_ket(r) if mo_duoc else None,
        })
    return ra


async def dem_chua_doc(nguoi_id: UUID) -> int:
    """BUG-TB-09: chỉ đếm thông báo còn nằm trong phạm vi quyền/đối tượng hiện tại."""
    return int(await db.pool().fetchval(
        f"{_CTE_PHAM_VI} SELECT count(*) FROM thong_bao t {_JOIN_TINH_TRANG} "  # noqa: S608
        f"WHERE t.nguoi_nhan_id = $1 AND t.da_doc_luc IS NULL AND ({_SQL_MO_DUOC})",
        nguoi_id) or 0)


async def dem_can_xu_ly(nguoi_id: UUID) -> int:
    """Số thông báo CÒN cần hành động, đọc hay chưa — đọc không phải làm xong."""
    return int(await db.pool().fetchval(
        f"{_CTE_PHAM_VI} SELECT count(*) FROM thong_bao t {_JOIN_TINH_TRANG}"  # noqa: S608
        f"WHERE t.nguoi_nhan_id = $1 AND {_SQL_CAN_XU_LY}", nguoi_id) or 0)


async def danh_dau_da_doc(nguoi_id: UUID, thong_bao_id: UUID) -> bool:
    """
    Trả False khi không có thông báo ấy CỦA người này — thông báo của người
    khác là 404, không phải 403: không xác nhận id ấy tồn tại.

    Chỉ đổi `da_doc_luc`. Không đụng hội thoại, công việc hay bản nháp nào.
    """
    r = await db.fetchrow(
        "UPDATE thong_bao SET da_doc_luc = coalesce(da_doc_luc, now()) "
        "WHERE id = $1 AND nguoi_nhan_id = $2 RETURNING id",
        thong_bao_id, nguoi_id)
    return r is not None


async def danh_dau_tat_ca(nguoi_id: UUID) -> int:
    kq = await db.execute(
        f"{_CTE_PHAM_VI} UPDATE thong_bao AS u SET da_doc_luc = now() "  # noqa: S608
        "FROM thong_bao t "
        f"{_JOIN_TINH_TRANG} "
        "WHERE u.id = t.id AND t.nguoi_nhan_id = $1 AND t.da_doc_luc IS NULL "
        f"  AND ({_SQL_MO_DUOC})",
        nguoi_id)
    phan = kq.split()
    return int(phan[-1]) if phan and phan[-1].isdigit() else 0
