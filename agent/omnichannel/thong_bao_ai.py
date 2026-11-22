"""
Báo khách đang nói chuyện với AI, và giữ lời hứa "nhắn gặp nhân viên".

CĂN CỨ
------
Nghị định 356/2025/NĐ-CP Điều 10 khoản 3: thông báo cho chủ thể việc xử lý
tự động, và cho họ lựa chọn không bị xử lý tự động. Điều 6 khoản 4: báo cho
chủ thể biết dữ liệu là dữ liệu nhạy cảm. Ảnh vùng da, mô tả mụn, kích ứng
là "tình trạng sức khoẻ" — NĐ 356 Điều 4 khoản 1 điểm d.

HAI NỬA, KHÔNG TÁCH ĐƯỢC
------------------------
Câu thông báo hứa: nhắn "gặp nhân viên" là gặp người. Lời hứa ấy phải được
giữ bằng MÃ — `khach_doi_gap_nguoi()` chạy TRƯỚC agent và chuyển người ngay.
Để model tự hiểu là để nó có lúc trả lời "dạ em hỗ trợ mình luôn ạ" cho
một người vừa nói rõ không muốn nói chuyện với máy.

CHỈ GỬI KHI AGENT THẬT SỰ TRẢ LỜI
---------------------------------
Hàm này được gọi SAU chốt `agent_bat` trong xu_ly_tin_vao. Agent tắt, nhân
viên đang tiếp khách, mà vẫn gửi "em là trợ lý AI" là nói sai sự thật.

Ở chế độ Gợi ý VẪN gửi — có chủ ý. Câu khách nhận khi ấy vẫn do AI soạn,
nhân viên chỉ duyệt trước khi gửi; nói "đang nói với trợ lý AI" là đúng sự
thật, và im đi vì có người duyệt là giấu khách việc máy viết câu họ đọc.

MỘT LẦN MỖI HỘI THOẠI
---------------------
Khoá chống trùng của outbox (`thong_bao_ai:<hội thoại>`), kiểm trên bảng
`messages`. Hội thoại bị dọn theo thời hạn lưu trữ thì lần sau khách nhắn
là hội thoại mới — và được báo lại, đúng như phải thế.
"""
from __future__ import annotations

import logging
import re
import unicodedata
import uuid

logger = logging.getLogger(__name__)

# So khớp trên chữ đã bỏ dấu, chữ thường. Cụm NHIỀU từ: "người" trần hay
# "nhân viên" trần quá phổ biến ("nhân viên giao hàng chưa tới").
#
# MỌI cụm phải có ĐỘNG TỪ Ý ĐỊNH (gặp, nói chuyện với, chuyển, gọi). Cụm trần
# như "người thật", "nhân viên thật", "không phải bot" khớp nhầm sau khi bỏ
# dấu: "có ảnh feedback người thật không", "nhân viên thật nhiệt tình",
# "không phải bột đúng không" (bột → bot) — mỗi câu là một khách bị đẩy sang
# người vĩnh viễn giữa lúc đang hỏi mua (rà soát 28.10.2026).
CUM_GAP_NGUOI = (
    "gap nhan vien", "gap nguoi", "gap admin", "gap chu shop", "gap quan ly",
    "noi chuyen voi nhan vien", "noi chuyen voi nguoi", "noi chuyen truc tiep voi",
    "chuyen cho nhan vien", "chuyen sang nhan vien", "goi nhan vien",
    "khong muon noi chuyen voi bot", "khong muon chat voi bot",
    # Rà soát 16.11.2026: ba cách nói thật này không khớp cụm nào ở trên —
    # "chuyển nhân viên giúp em" (không có "cho"/"sang"), "gặp nv" (viết
    # tắt), "gặp tư vấn viên". Vẫn giữ đủ động từ ý định: "nv" trần hay "tư
    # vấn viên" trần thì "tư vấn viên bên shop nhiệt tình" bị chuyển nhầm.
    "chuyen nhan vien", "chuyen nv", "chuyen cho nv", "chuyen sang nv",
    "gap nv", "goi nv", "noi chuyen voi nv",
    "gap tu van vien", "chuyen tu van vien", "noi chuyen voi tu van vien",
)
_KHONG_MUON_MAY = re.compile(
    r"(?i:không|ko|k|hông)\s+(?i:muốn|thích)\s+(?i:nói chuyện|chat|nhắn)\s+(?i:với|vs)\s+"
    r"(?:AI|(?i:máy|bot|robot|trợ lý ảo))\b")
SU_KIEN_DOI_GAP_NGUOI = "khach.doi_gap_nguoi"
# Lựa chọn của khách được NHỚ chừng này: hội thoại đã giải quyết rồi mở lại
# thì agent không tự trả lời lại người vừa nói không muốn nói chuyện với máy.
NHO_NGAY = 30


def _chuan(s: str) -> str:
    """Bỏ dấu, chữ thường, mọi ký tự không phải chữ/số thành khoảng trắng."""
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    s = "".join(c if c.isalnum() else " " for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.split())


def khach_doi_gap_nguoi(van_ban: str) -> bool:
    # So theo RANH GIỚI TỪ: "gặp người" khớp, "gặp người yêu" cũng khớp (cụm
    # đứng đầu) — chấp nhận được, chuyển người thừa còn hơn giữ khách lại
    # với máy khi họ đã đòi gặp người.
    t = f" {_chuan(van_ban)} "
    if any(f" {c} " in t for c in CUM_GAP_NGUOI):
        return True
    # "nói chuyện với AI / máy / bot" — so trên câu GỐC: bỏ dấu thì "AI" trùng
    # "ai" (= ai đó), nên chỉ nhận AI VIẾT HOA.
    return bool(_KHONG_MUON_MAY.search(van_ban or ""))


async def da_doi_gap_nguoi(cid: uuid.UUID) -> bool:
    """Khách đã đòi gặp người trong hội thoại này, trong NHO_NGAY ngày qua."""
    from agent import db

    r = await db.fetchrow(
        "SELECT 1 FROM events WHERE kind = $1 AND ref_id = $2 "
        "AND created_at > now() - make_interval(days => $3) LIMIT 1",
        SU_KIEN_DOI_GAP_NGUOI, cid, NHO_NGAY)
    return r is not None


def khoa(cid: uuid.UUID) -> str:
    return f"thong_bao_ai:{cid}"


DO_DAI_TOI_DA = 600
_NGOAC_KEP = re.compile(r"[\"“”«»]([^\"“”«»]{2,60})[\"“”«»]")
# "AI" phân biệt hoa thường: "ai" thường là đại từ ("ai cũng được") — khớp
# nó là cho qua một câu không hề nói tới trí tuệ nhân tạo.
_NOI_AI = re.compile(r"\bAI\b|(?i:trợ lý ảo|chatbot)")


def kiem_noi_dung(van_ban: str) -> str:
    """Lỗi của một câu thông báo do quản trị viên soạn; chuỗi rỗng = hợp lệ.

    Bốn luật, mỗi luật canh một cách hỏng IM LẶNG:

    1. `{ten}` là chỗ giữ chỗ DUY NHẤT. `{ten_shop}` hay `{` lẻ làm
       `str.format` nổ — trong `gui_neu_chua`, nơi lỗi bị nuốt để không chặn
       câu trả lời, tức là khách không bao giờ được báo và chẳng ai biết.
    2. Phải nói là AI — đó là mục đích của câu (NĐ 356 Điều 10 khoản 3).
    3. Cụm gọi người đặt trong ngoặc kép phải là cụm MÃ nhận ra
       (`khach_doi_gap_nguoi`). Viết `nhắn "gặp người thật"` thì khách làm
       đúng hướng dẫn mà vẫn nói chuyện với máy.
    4. Phải nhắc dữ liệu nhạy cảm (NĐ 356 Điều 6 khoản 4), và không hứa
       "24/7" — ở chế độ Gợi ý ban đêm không ai duyệt.
    """
    s = (van_ban or "").strip()
    if not s:
        return "nội dung trống"
    if len(s) > DO_DAI_TOI_DA:
        return f"dài quá {DO_DAI_TOI_DA} ký tự — khách đọc trên điện thoại"
    try:
        s.format(ten="BLANICA")
    except (KeyError, IndexError, ValueError):
        return "chỉ được dùng {ten} (tên thương hiệu); muốn viết dấu ngoặc nhọn thì gõ {{ }}"
    if not _NOI_AI.search(s):
        return "phải nói rõ khách đang nói chuyện với trợ lý AI (có chữ \"AI\")"
    cum = [c for c in _NGOAC_KEP.findall(s) if khach_doi_gap_nguoi(c)]
    if not cum:
        return ("phải hướng dẫn cách gặp người bằng một cụm trong ngoặc kép mà hệ thống "
                "nhận ra, ví dụ \"gặp nhân viên\" hoặc \"chuyển nhân viên\"")
    if "nhạy cảm" not in s.lower():
        return "phải nhắc ảnh/thông tin về da là dữ liệu nhạy cảm (NĐ 356 Điều 6 khoản 4)"
    if "24/7" in s:
        return "không hứa \"24/7\" — ở chế độ Gợi ý, ban đêm không ai duyệt câu trả lời"
    return ""


def cau_thong_bao() -> str:
    from agent import cau_hinh_dong
    from agent.config import Settings
    from agent.core import tools

    ten = (tools.ten_thuong_hieu() or "").strip() or "shop"
    # Qua cấu hình động: quản trị viên sửa câu trên dashboard thì hội thoại
    # MỚI nhận câu mới. Hội thoại đã được báo thì không báo lại — khoá chống
    # trùng là theo hội thoại, không theo nội dung.
    mau = cau_hinh_dong.lay("TIN_THONG_BAO_AI")
    try:
        return mau.format(ten=ten)
    except (KeyError, IndexError, ValueError):
        # Chỉ tới được đây nếu `.env` mang câu hỏng (dashboard đã chặn qua
        # `kiem_noi_dung`). Lui về câu mặc định thay vì không báo gì — im
        # lặng ở đây là vi phạm nghĩa vụ báo khách.
        logger.error("thong_bao_ai: TIN_THONG_BAO_AI hỏng định dạng, dùng câu mặc định")
        mac_dinh = str(Settings.model_fields["tin_thong_bao_ai"].default)
        return mac_dinh.format(ten=ten)


async def gui_neu_chua(msg, cid: uuid.UUID) -> bool:
    """
    Gửi câu thông báo nếu hội thoại này chưa nhận. Trả True nếu vừa xếp hàng.

    Hỏng KHÔNG chặn câu trả lời của agent — nhưng không im lặng: ghi
    `thong_bao_ai.loi` để `san_sang`/nhật ký thấy được.
    """
    from agent import cau_hinh_dong, db

    try:
        if (cau_hinh_dong.lay("THONG_BAO_AI") or "bat") != "bat":
            return False
        if await db.fetchrow("SELECT 1 FROM messages WHERE conversation_id = $1 "
                             "AND client_idempotency_key = $2 LIMIT 1", cid, khoa(cid)):
            return False
        from agent.channels import registry as channels
        from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository

        adapter = await channels.get_for_account(msg.account_id)
        if not await adapter.can_send_now(msg.conversation_ref):
            return False
        await OutboundService(PostgresOutboundRepository()).queue_text(
            conversation_id=cid, role="system", text=cau_thong_bao(), idempotency_key=khoa(cid),
            metadata={"thong_bao_ai": True},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — không chặn lượt trả lời của khách
        logger.exception("thong_bao_ai: không gửi được cho %s", cid)
        try:
            await db.log_event("thong_bao_ai.loi", ref_id=cid, loi=f"{type(exc).__name__}: {exc}"[:200])
        except Exception:  # noqa: BLE001
            pass
        return False
