"""
Hạn PHẢN HỒI SAU CHUYỂN GIAO: AI chuyển hội thoại cho người → bao lâu thì
có NHÂN VIÊN nhắn khách (mục 15 của phiếu việc chủ dự án, 22.11.2026).

Trước bản này con số ấy chỉ có ở màn Phân tích, đo sau sự việc. Không có
hạn thì không có cảnh báo: khách đã được AI hứa "bạn ấy sẽ nhắn lại sớm"
nằm chờ, và chuông chỉ reo cho hạn phản hồi ĐẦU — mà hạn ấy đã "đạt" từ lúc
AI chào. Đúng ca chờ lâu nhất là ca không ai được báo.

MỘT LƯỢT = MỘT DÒNG `sla_chuyen_giao` (migration 0062)
------------------------------------------------------
* MỞ: hội thoại đang ở tay người (`mode = 'human'`, còn mở) có sự kiện
  `conversation.escalated` mới hơn mọi lượt đã có. Vòng canh SLA mở lượt,
  không phải từng đường chuyển giao: chuyển giao có bảy tám đường (AI tự
  chuyển, khách đòi gặp người, ảnh không kèm chữ, tin nhóm, lỗi kỹ thuật,
  quy tắc tự động…) và đường thứ chín thêm sau sẽ quên gọi. Sự kiện thì
  đường nào cũng ghi — màn Phân tích đã đếm chuyển giao bằng nó.
  Hạn = lúc chuyển + `handover_response_minutes` của chính sách (kênh ×
  mức ưu tiên, cùng luật chọn với hai mục tiêu cũ), tính theo chế độ của
  mục tiêu `phan_hoi_sau_chuyen_giao`. Chính sách không đặt số phút → lượt
  vẫn được ghi và đo, kết cục `khong_han`.
* CHỐT bằng tin nhân viên: outbox gửi xong một tin vai `staff`
  (`ghi_phan_hoi_nhan_vien`, cùng giao dịch). Tin `system` (câu báo
  chuyển người, câu báo ngoài giờ) và tin AI KHÔNG chốt — xem
  `phan_hoi_that.py`.
* CHỐT không cần phản hồi: hội thoại đã giải quyết hoặc trả về AI trước
  khi ai nhắn → `huy` (đã trễ trước đó thì vẫn `tre`: trigger 0062 không
  cho xoá vi phạm).
* Lượt chuyển giao thứ hai, thứ ba… là dòng mới (`lan` tăng) — vi phạm của
  lần sau không bị khoá (hội thoại, chu kỳ, loại) của `sla_events` nuốt.

Hội thoại bị chuyển giao TRƯỚC khi migration 0062 chạy không được mở lượt:
mở lượt cho cả hàng chờ cũ là một trận chuông "đã trễ" cho những chuyện
từ tuần trước.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from agent.omnichannel import sla_muc_tieu

MUC_TIEU = "phan_hoi_sau_chuyen_giao"

# Lượt đang chờ: AI đã chuyển, chưa nhân viên nào nhắn.
_SQL_MO_LUOT = """
WITH moc AS (
    SELECT coalesce((SELECT applied_at FROM schema_migrations WHERE version = '0062'),
                    '-infinity'::timestamptz) AS tu
), ung_vien AS (
    SELECT c.id, c.sla_chu_ky, c.priority, c.account_id, e.bat_dau
    FROM conversations c
    CROSS JOIN moc
    CROSS JOIN LATERAL (
        SELECT max(ev.created_at) AS bat_dau FROM events ev
        WHERE ev.kind = 'conversation.escalated' AND ev.ref_id = c.id
    ) e
    WHERE c.mode = 'human' AND c.state IN ('open', 'pending')
      AND e.bat_dau IS NOT NULL AND e.bat_dau >= moc.tu AND e.bat_dau <= $1
      AND NOT EXISTS (
          SELECT 1 FROM sla_chuyen_giao g
          WHERE g.conversation_id = c.id
            AND (g.ket_thuc_luc IS NULL OR g.bat_dau >= e.bat_dau))
)
INSERT INTO sla_chuyen_giao (
    conversation_id, chu_ky, lan, bat_dau, due_at,
    phan_hoi_luc, phan_hoi_boi, message_id, ket_thuc_luc, ket_thuc_ly_do, ket_qua, detail)
SELECT u.id, u.sla_chu_ky,
       coalesce((SELECT max(g.lan) FROM sla_chuyen_giao g WHERE g.conversation_id = u.id), 0) + 1,
       u.bat_dau, h.han,
       ph.luc, ph.gui_boi, ph.id, ph.luc,
       CASE WHEN ph.luc IS NOT NULL THEN 'phan_hoi' END,
       CASE WHEN ph.luc IS NULL THEN 'dang_cho'
            WHEN h.han IS NULL THEN 'khong_han'
            WHEN ph.luc <= h.han THEN 'dat' ELSE 'tre' END,
       jsonb_build_object('phut', h.phut, 'che_do', $3::text)
FROM ung_vien u
LEFT JOIN LATERAL (
    SELECT sla_han_lich(u.bat_dau, policy.handover_response_minutes,
                        sla_lich_chinh_sach($2::text::jsonb, policy.business_hours)) AS han,
           policy.handover_response_minutes AS phut
    FROM sla_policies policy
    WHERE policy.active
      AND policy.priority IN (u.priority, 'normal')
      AND (policy.account_id = u.account_id OR policy.account_id IS NULL)
    ORDER BY (policy.account_id IS NOT NULL) DESC, (policy.priority = u.priority) DESC
    LIMIT 1
) h ON TRUE
-- Nhân viên đã nhắn trước khi vòng canh kịp mở lượt (vòng chạy 15 giây
-- một lần): mở lượt đã chốt luôn, không để nó "trễ" oan.
LEFT JOIN LATERAL (
    SELECT m.id, m.created_at AS luc, m.gui_boi FROM messages m
    WHERE m.conversation_id = u.id AND m.role = 'staff'
      AND m.created_at >= u.bat_dau AND m.delivery_status = 'sent'
    ORDER BY m.created_at LIMIT 1
) ph ON TRUE
ON CONFLICT DO NOTHING
RETURNING conversation_id, id
"""

# Lưới đỡ: tin nhân viên đã gửi mà lượt vẫn mở (đường gửi nào đó không đi
# qua `ghi_phan_hoi_nhan_vien`) — chốt bằng lúc tạo tin.
_SQL_CHOT_DA_PHAN_HOI = """
UPDATE sla_chuyen_giao g
SET phan_hoi_luc = ph.luc, phan_hoi_boi = ph.gui_boi, message_id = ph.id,
    ket_thuc_luc = ph.luc, ket_thuc_ly_do = 'phan_hoi',
    ket_qua = CASE WHEN g.due_at IS NULL THEN 'khong_han'
                   WHEN g.vi_pham_luc IS NULL AND ph.luc <= g.due_at THEN 'dat'
                   ELSE 'tre' END
FROM (
    SELECT DISTINCT ON (g2.id) g2.id AS gid, m.id, m.created_at AS luc, m.gui_boi
    FROM sla_chuyen_giao g2
    JOIN messages m ON m.conversation_id = g2.conversation_id
    WHERE g2.ket_thuc_luc IS NULL AND m.role = 'staff'
      AND m.created_at >= g2.bat_dau AND m.delivery_status = 'sent'
    ORDER BY g2.id, m.created_at
) ph
WHERE g.id = ph.gid AND g.ket_thuc_luc IS NULL
RETURNING g.id
"""

_SQL_CHOT_HET_CHO = """
UPDATE sla_chuyen_giao g
SET ket_thuc_luc = $1,
    ket_thuc_ly_do = CASE WHEN c.state IN ('resolved', 'closed') THEN 'giai_quyet'
                          ELSE 'tra_ai' END,
    ket_qua = CASE WHEN g.vi_pham_luc IS NOT NULL THEN 'tre' ELSE 'huy' END
FROM conversations c
WHERE c.id = g.conversation_id AND g.ket_thuc_luc IS NULL
  AND NOT (c.mode = 'human' AND c.state IN ('open', 'pending'))
RETURNING g.id
"""

_SQL_VI_PHAM = """
UPDATE sla_chuyen_giao
SET vi_pham_luc = $1
WHERE ket_thuc_luc IS NULL AND vi_pham_luc IS NULL
  AND due_at IS NOT NULL AND due_at < $1
RETURNING conversation_id, id
"""

# Sự kiện cho chuông và SSE: cùng các khoá với sự kiện `sla.*` cũ
# (`sla._SQL_SU_KIEN_SLA`), thêm `lan` — lượt chuyển giao thứ mấy.
_SQL_SU_KIEN = """
INSERT INTO inbox_events (account_id, topic, ref_id, payload)
SELECT c.account_id, $2, c.id,
       jsonb_build_object(
           'conversation_id', c.id, 'loai', $3::text, 'chu_ky', g.chu_ky,
           'lan', g.lan, 'nguoi_phu_trach', c.assigned_to, 'uu_tien', c.priority,
           'han', g.due_at)
FROM sla_chuyen_giao g JOIN conversations c ON c.id = g.conversation_id
WHERE g.id = ANY($1::uuid[])
"""


async def _canh_bao(conn: Any, scan_at: datetime) -> list[Any]:
    """
    Cảnh báo sớm: đã dùng `nguong` khoảng [lúc chuyển, hạn] — đo theo chế
    độ của mục tiêu này, cùng cách với cảnh báo hạn giải quyết (`sla.py`).
    """
    rows = await conn.fetch(
        "SELECT id, bat_dau, due_at FROM sla_chuyen_giao "
        "WHERE ket_thuc_luc IS NULL AND canh_bao_luc IS NULL AND vi_pham_luc IS NULL "
        "AND due_at IS NOT NULL AND due_at >= $1", scan_at)
    ty_le = sla_muc_tieu.nguong(MUC_TIEU)
    ids: list[Any] = []
    details: list[str] = []
    for r in rows:
        khoang = sla_muc_tieu.tieu_thu(r["bat_dau"], r["due_at"], MUC_TIEU)
        da_dung = sla_muc_tieu.tieu_thu(r["bat_dau"], scan_at, MUC_TIEU)
        nguong = khoang * ty_le
        if nguong > timedelta(0) and da_dung >= nguong:
            ids.append(r["id"])
            details.append(json.dumps({
                "threshold_ratio": ty_le,
                "threshold_minutes": round(nguong.total_seconds() / 60.0, 2),
                "elapsed_minutes": round(da_dung.total_seconds() / 60.0, 2),
            }))
    if not ids:
        return []
    return list(await conn.fetch(
        """
        UPDATE sla_chuyen_giao g SET canh_bao_luc = $1, detail = g.detail || d.detail::jsonb
        FROM unnest($2::uuid[], $3::text[]) AS d(id, detail)
        WHERE g.id = d.id AND g.ket_thuc_luc IS NULL AND g.canh_bao_luc IS NULL
        RETURNING g.conversation_id, g.id
        """, scan_at, ids, details))


async def quet(conn: Any, scan_at: datetime) -> dict[str, list[Any]]:
    """
    Một lượt canh, TRONG giao dịch của vòng SLA. Trả các dòng (hội thoại,
    lượt) vừa mở / vừa cảnh báo / vừa trễ — mỗi dòng xuất hiện đúng MỘT lần
    trong đời nó (các cột *_luc chỉ đặt khi đang NULL).
    """
    mo = await conn.fetch(_SQL_MO_LUOT, scan_at, sla_muc_tieu.lich_sql(MUC_TIEU),
                          sla_muc_tieu.che_do(MUC_TIEU))
    await conn.fetch(_SQL_CHOT_DA_PHAN_HOI)
    await conn.fetch(_SQL_CHOT_HET_CHO, scan_at)
    canh_bao = await _canh_bao(conn, scan_at)
    tre = list(await conn.fetch(_SQL_VI_PHAM, scan_at))
    for topic, rows in (("sla.handover_response_warning", canh_bao),
                        ("sla.handover_response_breached", tre)):
        if rows:
            await conn.execute(_SQL_SU_KIEN, [r["id"] for r in rows], topic,
                               topic.split(".", 1)[1])
    return {"mo": list(mo), "canh_bao": canh_bao, "tre": tre}


async def ghi_phan_hoi_nhan_vien(conn: Any, conversation_id: Any, message_id: Any) -> None:
    """
    Outbox vừa gửi xong một tin NHÂN VIÊN: chốt lượt chuyển giao đang chờ
    của hội thoại. Gọi trong giao dịch `mark_sent`, nên lúc phản hồi là lúc
    tin thật sự tới kênh — cùng mốc với phản hồi đầu.
    """
    await conn.execute(
        """
        UPDATE sla_chuyen_giao g
        SET phan_hoi_luc = now(), phan_hoi_boi = m.gui_boi, message_id = m.id,
            ket_thuc_luc = now(), ket_thuc_ly_do = 'phan_hoi',
            ket_qua = CASE WHEN g.due_at IS NULL THEN 'khong_han'
                           WHEN g.vi_pham_luc IS NULL AND now() <= g.due_at THEN 'dat'
                           ELSE 'tre' END
        FROM messages m
        WHERE m.id = $2 AND g.conversation_id = $1 AND g.ket_thuc_luc IS NULL
        """, conversation_id, message_id)
