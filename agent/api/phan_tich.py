"""
Màn Phân tích: hội thoại, khách, nhân viên, AI theo hồ sơ, tin nhắn, SLA.

MỌI CON SỐ ĐẾM THEO SỰ KIỆN, KHÔNG THEO ẢNH CHỤP TRẠNG THÁI
-----------------------------------------------------------
Số "tự xử lý" cũ (`/api/overview`, `/api/analytics/khach`) đếm hội thoại có
`status = 'auto'` LÚC NÀY. Duyệt một bản nháp AI lật `assist` → `auto`
(outbox.py), nên hội thoại người phải đọc và bấm duyệt từng câu cũng thành
"AI tự xử lý" — con số tô hồng đúng thứ nó sinh ra để đo. Ở đây mỗi con số
đếm một SỰ KIỆN có thời điểm (tin nhắn, `events`, `sla_events`) rơi trong
khoảng ngày, nên hỏi lại tuần trước vẫn ra đúng số của tuần trước.

Ngoại lệ có ghi nhãn: "đang mở" và "quá hạn bây giờ" là ảnh chụp lúc hỏi.

KHOẢNG NGÀY: [0h ngày `tu`, 0h ngày sau `den`) giờ Việt Nam — cùng quy ước
với `bao_cao_nhan_vien.py`.

BỘ LỌC (áp cho MỌI phần, qua CTE `hp` — "hội thoại trong phạm vi")
-----------------------------------------------------------------
- Phạm vi tầm nhìn: không có `hoi_thoai.xem_tat_ca` thì chỉ hội thoại của
  kênh mình là thành viên (`account_memberships`) — cùng mệnh đề với
  `/api/overview`. Báo cáo không được là cửa sau của danh sách hội thoại.
- `account_id`: một tài khoản kênh. `kenh`: nền tảng gốc
  (`coalesce(nen_tang, channel)`, như `/api/analytics/khach`).
- `nhan_vien`: hội thoại người ấy được giao (lượt giao chồng lên khoảng
  ngày) hoặc đã gửi tin trong khoảng.
- `ho_so`: hội thoại có ít nhất một tin AI trong khoảng do hồ sơ ấy viết
  (`mac_dinh` = chạy hồ sơ Mặc định). Hồ sơ chụp lúc tin được ghi
  (migration 0054), không phải hồ sơ đang gán cho kênh.
- Phòng thử (`channel = 'phong_thu'`) không bao giờ tính.

ĐỊNH NGHĨA — xem thêm docs/phan-tich.md
---------------------------------------
Hội thoại
  moi            hội thoại TẠO trong khoảng.
  hoat_dong      hội thoại có ít nhất một tin (mọi vai) trong khoảng.
  giai_quyet     số LƯỢT giải quyết: sự kiện `conversation.resolved` trong
                 khoảng (một hội thoại giải quyết, mở lại, giải quyết lại = 2).
  tu_giai_quyet  phần trong số trên do worker tự đóng vì nhàn rỗi.
  ty_le_xu_ly    hội thoại (khác nhau) được giải quyết / hội thoại có hoạt động.
  mo_lai         sự kiện `conversation.reopened` (ghi từ 20.11.2026 — trước
                 đó không có dấu vết, nên khoảng cũ hơn ra 0 chứ không phải
                 "không ai mở lại").
  chuyen_nguoi   hội thoại có sự kiện `conversation.escalated` trong khoảng.
  tiep_quan      hội thoại có sự kiện `conversation.takeover` trong khoảng.
  dang_mo        ẢNH CHỤP: hội thoại open/pending lúc hỏi.

Khách: khách (contact) có ít nhất một tin KHÁCH gửi trong khoảng. `moi` =
  `contacts.first_seen` trong khoảng; `quay_lai` = thấy lần đầu trước khoảng.

"Có người can thiệp" (dùng cho AI và `/api/overview`): trong khoảng, hội
  thoại có sự kiện chuyển người hoặc tiếp quản, HOẶC có tin nhân viên gửi,
  HOẶC có bản nháp AI được người duyệt (`messages.duyet_luc`, 0052). Duyệt
  nháp là can thiệp: ở chế độ Gợi ý không câu nào tới khách mà không qua
  tay người, và gọi đó là "AI tự lo" là đúng lỗi của con số cũ.

AI theo hồ sơ — mỗi hội thoại có tin AI trong khoảng quy cho hồ sơ của tin
  AI ĐẦU TIÊN trong khoảng:
  hoi_thoai      hội thoại có tin AI (gửi hay nháp) trong khoảng.
  tu_giai_quyet  được giải quyết trong khoảng VÀ không có người can thiệp.
  can_nguoi      có người can thiệp (dù sau đó có giải quyết hay không).
  dang_do        chưa giải quyết, chưa ai can thiệp — chưa có kết cục.
  ty_le_thanh_cong = tu_giai_quyet / (tu_giai_quyet + can_nguoi): chỉ tính
                 hội thoại ĐÃ có kết cục. Chia cho mọi hội thoại thì hội
                 thoại đang dở kéo tỉ lệ xuống; bỏ hẳn chúng mà không nói thì
                 tỉ lệ đẹp hơn thực tế — nên `dang_do` trả kèm.
  ty_le_can_nguoi = can_nguoi / hoi_thoai.
  ai_tu_chuyen   hội thoại AI tự chuyển người (`conversation.escalated`).
  ty_le_co_can_cu / ty_le_khong_can_cu: trên tin AI DO MODEL SINH (`model`
                 khác rỗng) — câu cố định (báo chuyển người, câu chào AI)
                 không qua tra cứu, đếm vào là méo tỉ lệ. KHÔNG báo "độ tin
                 cậy" của model: con số ấy do chính model tự chấm, hiện thành
                 phần trăm là mời người đọc tin nó như xác suất đúng (phiếu
                 việc của chủ dự án 20.11.2026).
  chi_phi_usd    tổng `messages.cost_usd` của tin AI trong khoảng.
  tu_dong_hoa (tổng) = hội thoại AI tự giải quyết / hội thoại có hoạt động.

Tin nhắn — theo nền tảng × vai, tin TẠO trong khoảng:
  nhan           chiều vào (`direction = 'inbound'`).
  gui            chiều ra ĐÃ tới kênh (`delivery_status = 'sent'`).
  loi            chiều ra hỏng (`failed`, `dead`).
  chua_gui       chiều ra còn lại: nháp chờ duyệt, đang xếp hàng.
  Nháp được duyệt về sau vẫn mang thời điểm tạo nháp.

SLA
  ty_le_dung_han_* = đạt / (đạt + trễ), sự kiện `*_met` / `*_breached` ghi
                 trong khoảng. Chỉ tính mục tiêu CÓ hạn (`due_at` khác NULL):
                 outbox ghi `first_response_met` cả cho hội thoại không có
                 chính sách SLA, đếm vào là "đúng hạn" một hạn không tồn tại.
  canh_bao_*     sự kiện cảnh báo sớm (ngưỡng SLA_NGUONG_CANH_BAO) trong khoảng.
  qua_han_*      ẢNH CHỤP: hội thoại đang mở đã quá hạn, lúc hỏi.
  Ba thước đo THỜI GIAN — trung bình kèm trung vị (một ca bỏ quên qua đêm
  kéo trung bình lên vài tiếng), lọc theo lúc KẾT THÚC rơi trong khoảng:
  phan_hoi_dau   từ lúc bắt đầu chu kỳ SLA (`started`, lui về lúc tạo hội
                 thoại ở chu kỳ 1) tới lúc gửi xong tin đầu tiên của AI hoặc
                 nhân viên; tách AI / nhân viên / không rõ (sự kiện trước
                 20.11.2026 không ghi ai trả lời).
  phan_hoi_sau_chuyen_giao  từ sự kiện `conversation.escalated` (lần đầu
                 trong khoảng của mỗi hội thoại) tới tin NHÂN VIÊN đầu tiên
                 sau đó; `chua_phan_hoi` = chuyển rồi mà chưa ai nhắn.
  thoi_gian_giai_quyet  từ lúc bắt đầu lượt phục vụ (tạo hội thoại, hoặc
                 lần mở lại gần nhất) tới sự kiện `conversation.resolved`.
  Mỗi thước đo theo CHẾ ĐỘ của mục tiêu SLA tương ứng (`sla_muc_tieu`,
  mục 15 — 22.11.2026): giờ làm việc của lịch chung, hoặc 24/7 — cùng lịch
  với hạn của chính mục tiêu ấy. `che_do_muc_tieu` trả kèm để màn hình nói
  rõ con số đo theo cách nào.
  Phản hồi đầu chỉ tính PHẢN HỒI THẬT (tin AI hoặc nhân viên); tin `system`
  — thông báo AI, câu báo chuyển người/ngoài giờ, tin mẫu tự động — là xác
  nhận tự động, không bao giờ đạt hạn (`phan_hoi_that.py`). Tách AI khỏi
  nhân viên để câu trả lời AI 2 giây không che ca chờ người 40 phút.
  chuyen_giao   MỤC TIÊU phản hồi sau chuyển giao (`sla_chuyen_giao`, 0062):
                mỗi LƯỢT chuyển một hạn. dung_han / tre_han đếm lượt có hạn
                chốt trong khoảng (trễ tính ở lúc vi phạm được ghi, hoặc lúc
                nhân viên nhắn muộn); canh_bao theo lúc cảnh báo; khong_han =
                chính sách không đặt số phút; thoi_gian = lúc chuyển → tin
                nhân viên chốt lượt. Thước đo `phan_hoi_sau_chuyen_giao` cũ
                (theo sự kiện, có cả dữ liệu trước 0062) giữ nguyên bên cạnh.
  AI và nhân viên trong GIẢI QUYẾT: lượt giải quyết (và sự kiện đạt / trễ
                hạn giải quyết) quy cho nhân viên nếu trong lượt phục vụ có
                người can thiệp (`co_nguoi_can_thiep`), không thì cho AI.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from agent import db
from agent.core.lien_he_nhom import sql_khong_phai_nhom
from agent.omnichannel import sla_muc_tieu
from agent.omnichannel.sla import thoi_gian_sla_da_tieu_thu

from .bao_cao_nhan_vien import MUI_GIO, _khoang, dong_hieu_suat, sql_hieu_suat
from .phu_thuoc import _xem_tat_ca_kenh, can_quyen

router = APIRouter(prefix="/api/phan-tich", tags=["phan-tich"])


def co_nguoi_can_thiep(cot: str, tu: str, den: str) -> str:
    """
    Biểu thức SQL: hội thoại `cot` có người can thiệp trong [tu, den).

    MỘT định nghĩa cho màn Phân tích và ô "AI tự lo" của `/api/overview` —
    hai bản chép là hai con số lệch nhau ngay lần sửa đầu tiên.
    """
    return f"""(
        EXISTS (SELECT 1 FROM events e_nguoi
                WHERE e_nguoi.ref_id = {cot}
                  AND e_nguoi.kind IN ('conversation.escalated', 'conversation.takeover')
                  AND e_nguoi.created_at >= {tu} AND e_nguoi.created_at < {den})
        OR EXISTS (SELECT 1 FROM messages m_nguoi
                   WHERE m_nguoi.conversation_id = {cot}
                     AND ((m_nguoi.role = 'staff'
                           AND m_nguoi.created_at >= {tu} AND m_nguoi.created_at < {den})
                          OR (m_nguoi.duyet_luc >= {tu} AND m_nguoi.duyet_luc < {den}))))"""


# Tham số chung của mọi câu: $1 tu, $2 den, $3 xem mọi kênh, $4 người hỏi,
# $5 tài khoản kênh, $6 nền tảng, $7 nhân viên, $8 hồ sơ AI. Mọi câu đều
# nhắc đủ tám (qua `_HP`) — Postgres từ chối tham số không ai dùng tới.
_KHOANG = f"""khoang AS (
    SELECT ($1::date)::timestamp AT TIME ZONE '{MUI_GIO}' AS tu,
           ($2::date + 1)::timestamp AT TIME ZONE '{MUI_GIO}' AS den
)"""

_HP = """
    SELECT c.id FROM conversations c, khoang k
    WHERE c.channel <> 'phong_thu'
      AND c.created_at < k.den
      AND ($3::bool OR EXISTS (SELECT 1 FROM account_memberships am
                               WHERE am.account_id = c.account_id AND am.user_id = $4))
      AND ($5::uuid IS NULL OR c.account_id = $5)
      AND ($6::text IS NULL OR coalesce(c.nen_tang, c.channel) = $6)
      AND ($7::uuid IS NULL
           OR EXISTS (SELECT 1 FROM conversation_assignments ca
                      WHERE ca.conversation_id = c.id AND ca.assigned_user_id = $7
                        AND ca.started_at < k.den
                        AND (ca.ended_at IS NULL OR ca.ended_at >= k.tu))
           OR EXISTS (SELECT 1 FROM messages ms
                      WHERE ms.conversation_id = c.id AND ms.gui_boi = $7
                        AND ms.created_at >= k.tu AND ms.created_at < k.den))
      AND ($8::text IS NULL
           OR EXISTS (SELECT 1 FROM messages ma
                      WHERE ma.conversation_id = c.id AND ma.role = 'agent'
                        AND ma.ho_so_da_ghi
                        AND ma.created_at >= k.tu AND ma.created_at < k.den
                        AND CASE WHEN $8 = 'mac_dinh' THEN ma.agent_ho_so_id IS NULL
                                 ELSE ma.agent_ho_so_id::text = $8 END))
"""

_DAU = f"WITH {_KHOANG}, hp AS ({_HP})"

# Hồ sơ của một tin AI, dạng khoá: `khong_ro` (tin trước 0054), `mac_dinh`,
# hoặc id hồ sơ.
_KHOA_HO_SO = ("CASE WHEN NOT m.ho_so_da_ghi THEN 'khong_ro' "
               "WHEN m.agent_ho_so_id IS NULL THEN 'mac_dinh' "
               "ELSE m.agent_ho_so_id::text END")

_SQL_HOI_THOAI = _DAU + """
SELECT
  (SELECT count(*) FROM conversations c JOIN hp ON hp.id = c.id, khoang k
    WHERE c.created_at >= k.tu) AS moi,
  (SELECT count(DISTINCT m.conversation_id) FROM messages m JOIN hp ON hp.id = m.conversation_id,
          khoang k WHERE m.created_at >= k.tu AND m.created_at < k.den) AS hoat_dong,
  (SELECT count(*) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.resolved'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS giai_quyet,
  (SELECT count(DISTINCT e.ref_id) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.resolved'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS hoi_thoai_giai_quyet,
  (SELECT count(*) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.resolved' AND e.detail ->> 'tu_dong' = 'true'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS tu_giai_quyet,
  (SELECT count(*) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.reopened'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS mo_lai,
  (SELECT count(DISTINCT e.ref_id) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.escalated'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS chuyen_nguoi,
  (SELECT count(DISTINCT e.ref_id) FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.takeover'
      AND e.created_at >= k.tu AND e.created_at < k.den) AS tiep_quan,
  (SELECT count(*) FROM conversations c JOIN hp ON hp.id = c.id
    WHERE c.state IN ('open', 'pending')) AS dang_mo
"""

_SQL_THEO_NGAY = _DAU + f""",
ai_ngay AS (
    SELECT DISTINCT (m.created_at AT TIME ZONE '{MUI_GIO}')::date AS d, m.conversation_id
    FROM messages m JOIN hp ON hp.id = m.conversation_id, khoang k
    WHERE m.role = 'agent' AND m.created_at >= k.tu AND m.created_at < k.den
),
nguoi_ngay AS (
    SELECT DISTINCT d, conversation_id FROM (
        SELECT (e.created_at AT TIME ZONE '{MUI_GIO}')::date AS d, e.ref_id AS conversation_id
        FROM events e, khoang k
        WHERE e.kind IN ('conversation.escalated', 'conversation.takeover')
          AND e.created_at >= k.tu AND e.created_at < k.den
        UNION ALL
        SELECT (m.created_at AT TIME ZONE '{MUI_GIO}')::date, m.conversation_id
        FROM messages m, khoang k
        WHERE m.role = 'staff' AND m.created_at >= k.tu AND m.created_at < k.den
        UNION ALL
        SELECT (m.duyet_luc AT TIME ZONE '{MUI_GIO}')::date, m.conversation_id
        FROM messages m, khoang k
        WHERE m.duyet_luc >= k.tu AND m.duyet_luc < k.den
    ) x
),
moi_ngay AS (
    SELECT (c.created_at AT TIME ZONE '{MUI_GIO}')::date AS d, count(*) AS so
    FROM conversations c JOIN hp ON hp.id = c.id, khoang k
    WHERE c.created_at >= k.tu GROUP BY 1
),
xong_ngay AS (
    SELECT (e.created_at AT TIME ZONE '{MUI_GIO}')::date AS d, count(*) AS so
    FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.resolved'
      AND e.created_at >= k.tu AND e.created_at < k.den GROUP BY 1
),
ai_tong AS (
    SELECT a.d, count(*) AS ai,
           count(*) FILTER (WHERE n.conversation_id IS NOT NULL) AS can_nguoi
    FROM ai_ngay a LEFT JOIN nguoi_ngay n
      ON n.d = a.d AND n.conversation_id = a.conversation_id
    GROUP BY a.d
),
-- Xu hướng SLA: cùng định nghĩa "đạt/trễ" với ô tổng (chỉ mục tiêu có hạn).
sla_ngay AS (
    SELECT (s.created_at AT TIME ZONE '{MUI_GIO}')::date AS d,
           count(*) FILTER (WHERE s.kind = 'first_response_met' AND s.due_at IS NOT NULL) AS dau_dat,
           count(*) FILTER (WHERE s.kind = 'first_response_breached') AS dau_tre,
           count(*) FILTER (WHERE s.kind = 'resolution_met' AND s.due_at IS NOT NULL) AS xong_dat,
           count(*) FILTER (WHERE s.kind = 'resolution_breached') AS xong_tre
    FROM sla_events s JOIN hp ON hp.id = s.conversation_id, khoang k
    WHERE s.created_at >= k.tu AND s.created_at < k.den GROUP BY 1
),
phi_ngay AS (
    SELECT (m.created_at AT TIME ZONE '{MUI_GIO}')::date AS d,
           coalesce(sum(m.cost_usd), 0) AS chi_phi
    FROM messages m JOIN hp ON hp.id = m.conversation_id, khoang k
    WHERE m.role = 'agent' AND m.created_at >= k.tu AND m.created_at < k.den GROUP BY 1
)
SELECT g.d::date AS ngay,
       coalesce(moi_ngay.so, 0) AS moi, coalesce(xong_ngay.so, 0) AS giai_quyet,
       coalesce(ai_tong.ai, 0) AS ai, coalesce(ai_tong.can_nguoi, 0) AS can_nguoi,
       coalesce(sla_ngay.dau_dat, 0) AS dau_dat, coalesce(sla_ngay.dau_tre, 0) AS dau_tre,
       coalesce(sla_ngay.xong_dat, 0) AS xong_dat, coalesce(sla_ngay.xong_tre, 0) AS xong_tre,
       coalesce(phi_ngay.chi_phi, 0) AS chi_phi
FROM generate_series($1::date, $2::date, interval '1 day') AS g(d)
LEFT JOIN moi_ngay ON moi_ngay.d = g.d::date
LEFT JOIN xong_ngay ON xong_ngay.d = g.d::date
LEFT JOIN ai_tong ON ai_tong.d = g.d::date
LEFT JOIN sla_ngay ON sla_ngay.d = g.d::date
LEFT JOIN phi_ngay ON phi_ngay.d = g.d::date
ORDER BY 1
"""

_SQL_KHACH = _DAU + """,
kh AS (
    SELECT DISTINCT c.contact_id
    FROM messages m JOIN hp ON hp.id = m.conversation_id
    JOIN conversations c ON c.id = m.conversation_id, khoang k
    WHERE m.role = 'customer' AND c.contact_id IS NOT NULL
      AND m.created_at >= k.tu AND m.created_at < k.den
)
SELECT count(*) AS tong,
       count(*) FILTER (WHERE ct.first_seen >= k.tu) AS moi,
       count(*) FILTER (WHERE ct.first_seen < k.tu) AS quay_lai
FROM kh JOIN contacts ct ON ct.id = kh.contact_id, khoang k
-- Nhóm Zalo không phải "khách mới" hay "khách quay lại" (mục 9.7).
WHERE """ + sql_khong_phai_nhom("ct") + "\n"

_SQL_AI = _DAU + f""",
tin_ai AS (
    SELECT m.conversation_id, m.created_at, m.grounded, m.cost_usd,
           coalesce(m.model, '') <> '' AS do_model, {_KHOA_HO_SO} AS ho_so
    FROM messages m JOIN hp ON hp.id = m.conversation_id, khoang k
    WHERE m.role = 'agent' AND m.created_at >= k.tu AND m.created_at < k.den
),
ht AS (
    SELECT DISTINCT ON (conversation_id) conversation_id, ho_so
    FROM tin_ai ORDER BY conversation_id, created_at
),
ket AS (
    SELECT ht.ho_so, ht.conversation_id,
           EXISTS (SELECT 1 FROM events e WHERE e.ref_id = ht.conversation_id
                   AND e.kind = 'conversation.resolved'
                   AND e.created_at >= k.tu AND e.created_at < k.den) AS xong,
           EXISTS (SELECT 1 FROM events e WHERE e.ref_id = ht.conversation_id
                   AND e.kind = 'conversation.escalated'
                   AND e.created_at >= k.tu AND e.created_at < k.den) AS ai_chuyen,
           {co_nguoi_can_thiep('ht.conversation_id', 'k.tu', 'k.den')} AS can_nguoi
    FROM ht, khoang k
),
theo_ht AS (
    SELECT ho_so, count(*) AS hoi_thoai,
           count(*) FILTER (WHERE xong AND NOT can_nguoi) AS tu_giai_quyet,
           count(*) FILTER (WHERE can_nguoi) AS can_nguoi,
           count(*) FILTER (WHERE NOT xong AND NOT can_nguoi) AS dang_do,
           count(*) FILTER (WHERE ai_chuyen) AS ai_tu_chuyen
    FROM ket GROUP BY ho_so
),
theo_tin AS (
    SELECT ho_so, count(*) AS tin,
           count(*) FILTER (WHERE do_model) AS tin_model,
           count(*) FILTER (WHERE do_model AND grounded IS TRUE) AS co_can_cu,
           coalesce(sum(cost_usd), 0) AS chi_phi
    FROM tin_ai GROUP BY ho_so
)
SELECT t.ho_so, hs.ten, t.tin, t.tin_model, t.co_can_cu, t.chi_phi,
       coalesce(h.hoi_thoai, 0) AS hoi_thoai, coalesce(h.tu_giai_quyet, 0) AS tu_giai_quyet,
       coalesce(h.can_nguoi, 0) AS can_nguoi, coalesce(h.dang_do, 0) AS dang_do,
       coalesce(h.ai_tu_chuyen, 0) AS ai_tu_chuyen
FROM theo_tin t
LEFT JOIN theo_ht h ON h.ho_so = t.ho_so
LEFT JOIN agent_ho_so hs ON hs.id::text = t.ho_so
WHERE $8::text IS NULL OR t.ho_so = $8
ORDER BY t.tin DESC
"""

_SQL_TIN = _DAU + """
SELECT coalesce(c.nen_tang, c.channel) AS kenh, m.role AS vai,
       count(*) FILTER (WHERE m.direction = 'inbound') AS nhan,
       count(*) FILTER (WHERE m.direction <> 'inbound' AND m.delivery_status = 'sent') AS gui,
       count(*) FILTER (WHERE m.direction <> 'inbound'
                        AND m.delivery_status IN ('failed', 'dead')) AS loi,
       count(*) FILTER (WHERE m.direction <> 'inbound'
                        AND m.delivery_status NOT IN ('sent', 'failed', 'dead')) AS chua_gui
FROM messages m JOIN hp ON hp.id = m.conversation_id
JOIN conversations c ON c.id = m.conversation_id, khoang k
WHERE m.created_at >= k.tu AND m.created_at < k.den
GROUP BY 1, 2 ORDER BY 1, 2
"""

_SQL_SLA = _DAU + """,
ev AS (
    SELECT s.kind, s.due_at FROM sla_events s JOIN hp ON hp.id = s.conversation_id, khoang k
    WHERE s.created_at >= k.tu AND s.created_at < k.den
)
SELECT
  (SELECT count(*) FROM ev WHERE kind = 'first_response_met' AND due_at IS NOT NULL) AS dau_dat,
  (SELECT count(*) FROM ev WHERE kind = 'first_response_breached') AS dau_tre,
  (SELECT count(*) FROM ev WHERE kind = 'first_response_warning') AS dau_canh_bao,
  (SELECT count(*) FROM ev WHERE kind = 'resolution_met' AND due_at IS NOT NULL) AS xong_dat,
  (SELECT count(*) FROM ev WHERE kind = 'resolution_breached') AS xong_tre,
  (SELECT count(*) FROM ev WHERE kind = 'resolution_warning') AS xong_canh_bao,
  (SELECT count(*) FROM conversations c JOIN hp ON hp.id = c.id
    WHERE c.state IN ('open', 'pending') AND c.first_responded_at IS NULL
      AND c.first_response_due_at < now()) AS qua_han_dau,
  (SELECT count(*) FROM conversations c JOIN hp ON hp.id = c.id
    WHERE c.state IN ('open', 'pending') AND c.resolved_at IS NULL
      AND c.resolution_due_at < now()) AS qua_han_xong,
  (SELECT count(*) FROM conversations c JOIN hp ON hp.id = c.id
    WHERE c.state IN ('open', 'pending')
      AND ((c.first_responded_at IS NULL AND c.first_response_due_at < now())
        OR (c.resolved_at IS NULL AND c.resolution_due_at < now()))) AS qua_han
"""

_SQL_PHAN_HOI = _DAU + """,
ph AS (
    SELECT s.kind, s.due_at,
           coalesce((s.detail ->> 'phan_hoi_luc')::timestamptz,
                    CASE WHEN s.kind = 'first_response_met' THEN s.created_at END) AS luc,
           coalesce(s.detail ->> 'vai', 'khong_ro') AS vai,
           s.detail ->> 'gui_boi' AS gui_boi,
           s.detail ->> 'ho_so' AS ho_so,
           coalesce((SELECT min(st.created_at) FROM sla_events st
                     WHERE st.conversation_id = s.conversation_id
                       AND st.chu_ky = s.chu_ky AND st.kind = 'started'),
                    CASE WHEN s.chu_ky = 1 THEN c.created_at END) AS bat_dau
    FROM sla_events s JOIN hp ON hp.id = s.conversation_id
    JOIN conversations c ON c.id = s.conversation_id, khoang k
    WHERE s.kind IN ('first_response_met', 'first_response_breached')
      AND s.created_at < k.den
      AND jsonb_typeof(s.detail) = 'object'
)
SELECT ph.kind, ph.due_at, ph.luc, ph.bat_dau, ph.vai,
       CASE WHEN ph.vai = 'staff' THEN ph.gui_boi END AS nv,
       CASE WHEN ph.vai = 'agent' THEN coalesce(ph.ho_so, 'mac_dinh') END AS hs
FROM ph, khoang k
WHERE ph.luc >= k.tu AND ph.luc < k.den
  AND ph.bat_dau IS NOT NULL AND ph.luc >= ph.bat_dau
"""

# Phản hồi sau chuyển giao: lần chuyển người ĐẦU TIÊN trong khoảng của mỗi
# hội thoại → tin nhân viên đầu tiên sau đó. Lấy lần đầu, không mọi lần: AI
# chuyển hai lần trước khi ai kịp nhắn thì cùng một tin nhân viên bị đếm hai
# lượt, một lượt trong đó ngắn giả tạo.
_SQL_CHUYEN_GIAO = _DAU + """,
cg AS (
    SELECT DISTINCT ON (e.ref_id) e.ref_id AS cid, e.created_at AS bat_dau
    FROM events e JOIN hp ON hp.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.escalated'
      AND e.created_at >= k.tu AND e.created_at < k.den
    ORDER BY e.ref_id, e.created_at
)
SELECT cg.bat_dau, m.created_at AS luc, m.gui_boi::text AS nv
FROM cg LEFT JOIN LATERAL (
    SELECT created_at, gui_boi FROM messages
    WHERE conversation_id = cg.cid AND role = 'staff' AND created_at >= cg.bat_dau
    ORDER BY created_at LIMIT 1
) m ON TRUE
"""

# Thời gian giải quyết: lượt phục vụ bắt đầu ở lúc tạo hội thoại, hoặc lần
# mở lại gần nhất TRƯỚC lúc giải quyết — không thì hội thoại mở lại sau ba
# tuần mang "thời gian giải quyết" ba tuần.
# `co_nguoi`: ai lo lượt ấy — AI một mình, hay có người can thiệp (cùng
# định nghĩa với phần AI). Cận trên +1 giây: tin nhân viên ghi cùng giây với
# lúc giải quyết vẫn là can thiệp.
_CO_NGUOI_LUOT = co_nguoi_can_thiep("x.cid", "x.bat_dau", "x.luc + interval '1 second'")

_SQL_TG_GIAI_QUYET = _DAU + """
SELECT x.luc, x.bat_dau, """ + _CO_NGUOI_LUOT + """ AS co_nguoi
FROM (
    SELECT e.ref_id AS cid, e.created_at AS luc,
           greatest(c.created_at, coalesce(
               (SELECT max(r.created_at) FROM events r
                WHERE r.ref_id = e.ref_id AND r.kind = 'conversation.reopened'
                  AND r.created_at < e.created_at), c.created_at)) AS bat_dau
    FROM events e JOIN hp ON hp.id = e.ref_id
    JOIN conversations c ON c.id = e.ref_id, khoang k
    WHERE e.kind = 'conversation.resolved'
      AND e.created_at >= k.tu AND e.created_at < k.den
) x
"""

# Đạt / trễ hạn giải quyết theo AI hay nhân viên: cùng sự kiện với ô tổng
# (`_SQL_SLA`), quy theo có người can thiệp từ đầu chu kỳ tới lúc ghi sự kiện.
_SQL_XONG_THEO_VAI = _DAU + """
SELECT x.kind, """ + _CO_NGUOI_LUOT + """ AS co_nguoi
FROM (
    SELECT s.conversation_id AS cid, s.kind, s.created_at AS luc,
           coalesce((SELECT min(st.created_at) FROM sla_events st
                     WHERE st.conversation_id = s.conversation_id
                       AND st.chu_ky = s.chu_ky AND st.kind = 'started'),
                    c.created_at) AS bat_dau
    FROM sla_events s JOIN hp ON hp.id = s.conversation_id
    JOIN conversations c ON c.id = s.conversation_id, khoang k
    WHERE s.created_at >= k.tu AND s.created_at < k.den
      AND (s.kind = 'resolution_breached'
           OR (s.kind = 'resolution_met' AND s.due_at IS NOT NULL))
) x
"""

# Mục tiêu phản hồi sau chuyển giao — mỗi lượt một dòng (`sla_chuyen_giao`).
# Lượt đang chờ luôn được lấy (ảnh chụp "đang chờ / đang quá hạn").
_SQL_CG = _DAU + """,
g AS (
    SELECT g.*, coalesce(g.vi_pham_luc,
                         CASE WHEN g.ket_qua = 'tre' THEN g.ket_thuc_luc END) AS luc_tre
    FROM sla_chuyen_giao g JOIN hp ON hp.id = g.conversation_id
)
SELECT g.ket_qua, g.bat_dau, g.due_at, g.phan_hoi_luc, g.phan_hoi_boi::text AS nv,
       coalesce(g.ket_qua = 'dat' AND g.ket_thuc_luc >= k.tu AND g.ket_thuc_luc < k.den,
                false) AS dat,
       coalesce(g.luc_tre >= k.tu AND g.luc_tre < k.den, false) AS tre,
       coalesce(g.canh_bao_luc >= k.tu AND g.canh_bao_luc < k.den, false) AS canh_bao,
       coalesce(g.ket_qua = 'khong_han' AND g.ket_thuc_luc >= k.tu AND g.ket_thuc_luc < k.den,
                false) AS khong_han,
       coalesce(g.ket_thuc_ly_do = 'phan_hoi' AND g.phan_hoi_luc >= k.tu
                AND g.phan_hoi_luc < k.den, false) AS do_duoc,
       (g.ket_thuc_luc IS NULL) AS dang_cho,
       coalesce(g.ket_thuc_luc IS NULL AND g.due_at < now(), false) AS qua_han
FROM g, khoang k
WHERE g.ket_thuc_luc IS NULL
   OR (g.ket_thuc_luc >= k.tu AND g.ket_thuc_luc < k.den)
   OR (g.luc_tre >= k.tu AND g.luc_tre < k.den)
   OR (g.canh_bao_luc >= k.tu AND g.canh_bao_luc < k.den)
"""


def _ti_le(tu: int, mau: int) -> float | None:
    return round(tu / mau, 4) if mau else None


def _so(x) -> float | None:
    return None if x is None else round(float(x), 1)


def _kiem_ho_so(ho_so: str | None) -> str | None:
    if not ho_so:
        return None
    if ho_so == "mac_dinh":
        return ho_so
    try:
        return str(uuid.UUID(ho_so))
    except ValueError as exc:
        raise HTTPException(422, "Hồ sơ AI không hợp lệ.") from exc


def _ten_ho_so(khoa: str, ten: str | None) -> str:
    if khoa == "mac_dinh":
        return "Mặc định"
    if khoa == "khong_ro":
        return "Không rõ (tin trước khi ghi hồ sơ)"
    return ten or "Hồ sơ đã xoá"


def _thong_ke(cap: list[tuple[Any, Any]], muc_tieu: str = "phan_hoi_dau") -> dict[str, Any]:
    """
    Số lượt, trung bình, trung vị (giây) của các cặp (bắt đầu, kết thúc).

    Độ dài tính bằng `thoi_gian_sla_da_tieu_thu` theo CHẾ ĐỘ của mục tiêu
    (giờ làm việc / 24/7) — cùng lịch với hạn SLA của mục tiêu ấy: hạn đặt
    theo giờ làm việc mà thời gian phản hồi đo 24/7 thì một tin tối hôm
    trước trả lời lúc 8 giờ sáng bị tính "trễ 11 tiếng" trong khi hạn của nó
    vẫn còn.
    """
    giay = sorted(thoi_gian_sla_da_tieu_thu(a, b, muc_tieu).total_seconds() for a, b in cap)
    return {"so": len(giay),
            "tb_giay": _so(statistics.fmean(giay)) if giay else None,
            "trung_vi_giay": _so(statistics.median(giay)) if giay else None}


def _phan_hoi_dau(rows: list, ten_nv: dict[str, str], ten_hs: dict[str, str]) -> dict[str, Any]:
    """Thời gian phản hồi đầu theo vai, theo từng nhân viên, theo từng hồ sơ AI."""
    def _dong(nhom: list) -> dict[str, Any]:
        dung = sum(1 for r in nhom if r["kind"] == "first_response_met" and r["due_at"] is not None)
        tre = sum(1 for r in nhom if r["kind"] == "first_response_breached")
        return {**_thong_ke([(r["bat_dau"], r["luc"]) for r in nhom]),
                "dung_han": dung, "tre_han": tre, "ty_le_dung_han": _ti_le(dung, dung + tre)}

    def _gom(khoa: str) -> dict[str, list]:
        ra: dict[str, list] = {}
        for r in rows:
            if r[khoa] is not None:
                ra.setdefault(r[khoa], []).append(r)
        return ra

    theo_vai = {vai: _dong([r for r in rows if r["vai"] == vai])
                for vai in ("agent", "staff", "khong_ro")}
    nhan_vien = [{"id": k, "ten": ten_nv.get(k, "Nhân viên đã xoá"), **_dong(v)}
                 for k, v in _gom("nv").items()]
    ho_so = [{"ho_so": k, "ten": _ten_ho_so(k, ten_hs.get(k)), **_dong(v)}
             for k, v in _gom("hs").items()]
    return {"tat_ca": _dong(rows), "theo_vai": theo_vai,
            "nhan_vien": sorted(nhan_vien, key=lambda d: -d["so"]),
            "ho_so": sorted(ho_so, key=lambda d: -d["so"])}


def _sau_chuyen_giao(rows: list, ten_nv: dict[str, str]) -> dict[str, Any]:
    co = [r for r in rows if r["luc"] is not None]
    theo_nv: dict[str, list] = {}
    for r in co:
        if r["nv"]:
            theo_nv.setdefault(r["nv"], []).append((r["bat_dau"], r["luc"]))
    cg = "phan_hoi_sau_chuyen_giao"
    return {**_thong_ke([(r["bat_dau"], r["luc"]) for r in co], cg),
            "chua_phan_hoi": len(rows) - len(co),
            "nhan_vien": sorted(
                ({"id": k, "ten": ten_nv.get(k, "Nhân viên đã xoá"), **_thong_ke(v, cg)}
                 for k, v in theo_nv.items()), key=lambda d: -d["so"])}


def _muc_tieu_chuyen_giao(rows: list, ten_nv: dict[str, str]) -> dict[str, Any]:
    """Mục tiêu phản hồi sau chuyển giao: đạt / trễ / cảnh báo theo LƯỢT."""
    cg = "phan_hoi_sau_chuyen_giao"
    dat = sum(1 for r in rows if r["dat"])
    tre = sum(1 for r in rows if r["tre"])
    do = [r for r in rows if r["do_duoc"]]
    theo_nv: dict[str, list] = {}
    for r in do:
        if r["nv"]:
            theo_nv.setdefault(r["nv"], []).append(r)

    def _dong(nhom: list) -> dict[str, Any]:
        d = sum(1 for r in nhom if r["ket_qua"] == "dat")
        t = sum(1 for r in nhom if r["ket_qua"] == "tre")
        return {**_thong_ke([(r["bat_dau"], r["phan_hoi_luc"]) for r in nhom], cg),
                "dung_han": d, "tre_han": t, "ty_le_dung_han": _ti_le(d, d + t)}

    return {
        "che_do": sla_muc_tieu.che_do(cg),
        "dung_han": dat, "tre_han": tre, "ty_le_dung_han": _ti_le(dat, dat + tre),
        "canh_bao": sum(1 for r in rows if r["canh_bao"]),
        "khong_han": sum(1 for r in rows if r["khong_han"]),
        "dang_cho": sum(1 for r in rows if r["dang_cho"]),
        "qua_han": sum(1 for r in rows if r["qua_han"]),
        "thoi_gian": _thong_ke([(r["bat_dau"], r["phan_hoi_luc"]) for r in do], cg),
        "nhan_vien": sorted(
            ({"id": k, "ten": ten_nv.get(k, "Nhân viên đã xoá"), **_dong(v)}
             for k, v in theo_nv.items()), key=lambda d: -d["so"]),
    }


def _giai_quyet_theo_vai(gq: list, xv: list) -> dict[str, Any]:
    """Thời gian và đạt/trễ hạn giải quyết: AI một mình vs có nhân viên."""
    ra: dict[str, Any] = {}
    for vai, co in (("agent", False), ("staff", True)):
        dat = sum(1 for r in xv if bool(r["co_nguoi"]) is co and r["kind"] == "resolution_met")
        tre = sum(1 for r in xv if bool(r["co_nguoi"]) is co
                  and r["kind"] == "resolution_breached")
        ra[vai] = {**_thong_ke([(r["bat_dau"], r["luc"]) for r in gq
                                if bool(r["co_nguoi"]) is co], "giai_quyet"),
                   "dung_han": dat, "tre_han": tre, "ty_le_dung_han": _ti_le(dat, dat + tre)}
    return ra


async def tinh(tu: date, den: date, *, xem_het: bool, nguoi_id: uuid.UUID,
               account_id: uuid.UUID | None = None, kenh: str | None = None,
               nhan_vien: uuid.UUID | None = None, ho_so: str | None = None) -> dict[str, Any]:
    """Toàn bộ số liệu màn Phân tích. Tách khỏi route để test gọi thẳng."""
    ts = (tu, den, xem_het, nguoi_id, account_id, kenh or None, nhan_vien, ho_so)

    ht = await db.fetchrow(_SQL_HOI_THOAI, *ts) or {}
    theo_ngay = await db.fetch(_SQL_THEO_NGAY, *ts)
    kh = await db.fetchrow(_SQL_KHACH, *ts) or {}
    ai = await db.fetch(_SQL_AI, *ts)
    tin = await db.fetch(_SQL_TIN, *ts)
    sla = await db.fetchrow(_SQL_SLA, *ts) or {}
    ph = await db.fetch(_SQL_PHAN_HOI, *ts)
    cg = await db.fetch(_SQL_CHUYEN_GIAO, *ts)
    gq = await db.fetch(_SQL_TG_GIAI_QUYET, *ts)
    xv = await db.fetch(_SQL_XONG_THEO_VAI, *ts)
    cgm = await db.fetch(_SQL_CG, *ts)
    nv = await db.fetch(sql_hieu_suat(pham_vi=_HP, loc_nguoi="AND ($7::uuid IS NULL OR id = $7)"), *ts)

    ten_nv = {str(r["id"]): r["ho_ten"] or r["ten_dang_nhap"]
              for r in await db.fetch("SELECT id, ho_ten, ten_dang_nhap FROM nguoi_dung")}
    ten_hs = {str(r["id"]): r["ten"] for r in await db.fetch("SELECT id, ten FROM agent_ho_so")}

    def i(d, k) -> int:
        return int(d.get(k) or 0)

    muc_tieu_cg = _muc_tieu_chuyen_giao(cgm, ten_nv)

    dau_dat, dau_tre = i(sla, "dau_dat"), i(sla, "dau_tre")
    xong_dat, xong_tre = i(sla, "xong_dat"), i(sla, "xong_tre")
    hoi_thoai: dict[str, int | float | None] = {k: i(ht, k) for k in (
        "moi", "hoat_dong", "giai_quyet", "hoi_thoai_giai_quyet", "tu_giai_quyet",
        "mo_lai", "chuyen_nguoi", "tiep_quan", "dang_mo")}
    hoi_thoai["ty_le_xu_ly"] = _ti_le(i(ht, "hoi_thoai_giai_quyet"), i(ht, "hoat_dong"))
    ds_ai = [{
        "ho_so": r["ho_so"], "ten": _ten_ho_so(r["ho_so"], r["ten"]),
        "hoi_thoai": int(r["hoi_thoai"]), "tu_giai_quyet": int(r["tu_giai_quyet"]),
        "can_nguoi": int(r["can_nguoi"]), "dang_do": int(r["dang_do"]),
        "ai_tu_chuyen": int(r["ai_tu_chuyen"]),
        "ty_le_thanh_cong": _ti_le(int(r["tu_giai_quyet"]),
                                   int(r["tu_giai_quyet"]) + int(r["can_nguoi"])),
        "ty_le_can_nguoi": _ti_le(int(r["can_nguoi"]), int(r["hoi_thoai"])),
        "tin": int(r["tin"]), "tin_model": int(r["tin_model"]),
        "ty_le_co_can_cu": _ti_le(int(r["co_can_cu"]), int(r["tin_model"])),
        "ty_le_khong_can_cu": _ti_le(int(r["tin_model"]) - int(r["co_can_cu"]),
                                     int(r["tin_model"])),
        "chi_phi_usd": round(float(r["chi_phi"] or 0), 6),
    } for r in ai]
    ai_ht = sum(a["hoi_thoai"] for a in ds_ai)
    ai_tu = sum(a["tu_giai_quyet"] for a in ds_ai)
    ai_nguoi = sum(a["can_nguoi"] for a in ds_ai)
    return {
        "tu": tu.isoformat(), "den": den.isoformat(),
        "bo_loc": {"account_id": str(account_id) if account_id else None, "kenh": kenh or None,
                   "nhan_vien": str(nhan_vien) if nhan_vien else None, "ho_so": ho_so},
        # Giữ cho dashboard cũ: chế độ của mục tiêu phản hồi đầu.
        "theo_gio_lam_viec": sla_muc_tieu.lich_cho("phan_hoi_dau") is not None,
        "che_do_muc_tieu": {m: ("gio_lam_viec" if sla_muc_tieu.lich_cho(m) is not None
                                else "24_7") for m in sla_muc_tieu.MUC_TIEU},
        "hoi_thoai": hoi_thoai,
        "theo_ngay": [{
            "ngay": r["ngay"].isoformat(), "moi": int(r["moi"]), "giai_quyet": int(r["giai_quyet"]),
            "ai": int(r["ai"]), "can_nguoi": int(r["can_nguoi"]),
            "ty_le_can_nguoi": _ti_le(int(r["can_nguoi"]), int(r["ai"])),
            "dau_dat": int(r["dau_dat"]), "dau_tre": int(r["dau_tre"]),
            "xong_dat": int(r["xong_dat"]), "xong_tre": int(r["xong_tre"]),
            "vi_pham": int(r["dau_tre"]) + int(r["xong_tre"]),
            "ty_le_dung_han_dau": _ti_le(int(r["dau_dat"]), int(r["dau_dat"]) + int(r["dau_tre"])),
            # Biểu đồ xu hướng SLA (UX-15-06) vẽ cả hạn giải quyết — tính ở
            # đây cùng `_ti_le` với ô tổng, để màn hình không có phép chia riêng.
            "ty_le_dung_han_xong": _ti_le(int(r["xong_dat"]), int(r["xong_dat"]) + int(r["xong_tre"])),
            "chi_phi_ai_usd": round(float(r["chi_phi"] or 0), 6),
        } for r in theo_ngay],
        "khach": {k: i(kh, k) for k in ("tong", "moi", "quay_lai")},
        "nhan_vien": dong_hieu_suat(nv),
        "ai_tong": {
            "hoi_thoai": ai_ht, "tu_giai_quyet": ai_tu, "can_nguoi": ai_nguoi,
            "ty_le_chuyen_giao": _ti_le(ai_nguoi, ai_ht),
            "tu_dong_hoa": _ti_le(ai_tu, i(ht, "hoat_dong")),
            "chi_phi_usd": round(sum(a["chi_phi_usd"] for a in ds_ai), 6),
        },
        "ai": ds_ai,
        "tin_nhan": [{k: (r[k] if k in ("kenh", "vai") else int(r[k]))
                      for k in ("kenh", "vai", "nhan", "gui", "loi", "chua_gui")} for r in tin],
        "sla": {
            "dau_dat": dau_dat, "dau_tre": dau_tre, "dau_canh_bao": i(sla, "dau_canh_bao"),
            "ty_le_dung_han_dau": _ti_le(dau_dat, dau_dat + dau_tre),
            "xong_dat": xong_dat, "xong_tre": xong_tre, "xong_canh_bao": i(sla, "xong_canh_bao"),
            "ty_le_dung_han_xong": _ti_le(xong_dat, xong_dat + xong_tre),
            "vi_pham": dau_tre + xong_tre,
            "qua_han": i(sla, "qua_han"), "qua_han_dau": i(sla, "qua_han_dau"),
            "qua_han_xong": i(sla, "qua_han_xong"),
            "phan_hoi_dau": _phan_hoi_dau(ph, ten_nv, ten_hs),
            "phan_hoi_sau_chuyen_giao": _sau_chuyen_giao(cg, ten_nv),
            "chuyen_giao": muc_tieu_cg,
            "vi_pham_tat_ca": dau_tre + xong_tre + muc_tieu_cg["tre_han"],
            "thoi_gian_giai_quyet": {
                **_thong_ke([(r["bat_dau"], r["luc"]) for r in gq], "giai_quyet"),
                "theo_vai": _giai_quyet_theo_vai(gq, xv)},
        },
    }


@router.get("")
async def phan_tich(
    tu: date | None = Query(None), den: date | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    kenh: str | None = Query(None, max_length=40),
    nhan_vien: uuid.UUID | None = Query(None),
    ho_so: str | None = Query(None, max_length=40),
    nguoi: dict = Depends(can_quyen("bao_cao.doc")),
) -> dict[str, Any]:
    tu, den = _khoang(tu, den)
    return await tinh(tu, den, xem_het=_xem_tat_ca_kenh(nguoi),
                      nguoi_id=uuid.UUID(str(nguoi["id"])), account_id=account_id,
                      kenh=kenh, nhan_vien=nhan_vien, ho_so=_kiem_ho_so(ho_so))


@router.get("/bo-loc")
async def bo_loc(nguoi: dict = Depends(can_quyen("bao_cao.doc"))) -> dict[str, Any]:
    """Lựa chọn cho các ô lọc — kênh chỉ gồm kênh người hỏi được thấy."""
    xem_het = _xem_tat_ca_kenh(nguoi)
    nid = uuid.UUID(str(nguoi["id"]))
    tai_khoan = await db.fetch(
        "SELECT tk.id, tk.display_name, tk.channel FROM channel_accounts tk "
        "WHERE $1 OR EXISTS (SELECT 1 FROM account_memberships am "
        "                    WHERE am.account_id = tk.id AND am.user_id = $2) "
        "ORDER BY tk.display_name", xem_het, nid)
    nen_tang = await db.fetch(
        "SELECT DISTINCT coalesce(c.nen_tang, c.channel) AS kenh FROM conversations c "
        "WHERE c.channel <> 'phong_thu' AND ($1 OR EXISTS (SELECT 1 FROM account_memberships am "
        "      WHERE am.account_id = c.account_id AND am.user_id = $2)) ORDER BY 1", xem_het, nid)
    nhan_vien = await db.fetch(
        "SELECT id, coalesce(nullif(ho_ten, ''), ten_dang_nhap) AS ten, khoa FROM nguoi_dung "
        "ORDER BY khoa, 2")
    ho_so = await db.fetch("SELECT id, ten, bat FROM agent_ho_so ORDER BY ten")
    return {
        "tai_khoan": [{"id": str(r["id"]), "ten": r["display_name"], "kenh": r["channel"]}
                      for r in tai_khoan],
        "kenh": [r["kenh"] for r in nen_tang if r["kenh"]],
        "nhan_vien": [{"id": str(r["id"]), "ten": r["ten"], "khoa": r["khoa"]} for r in nhan_vien],
        "ho_so": [{"id": "mac_dinh", "ten": "Mặc định"}]
                 + [{"id": str(r["id"]), "ten": r["ten"], "bat": r["bat"]} for r in ho_so],
    }
