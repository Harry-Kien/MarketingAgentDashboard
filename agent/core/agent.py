"""
Bộ điều phối agent — nơi một tin nhắn của khách trở thành một câu trả lời.

Luồng:
    tin nhắn -> RAG lấy ngữ cảnh -> Claude (vòng lặp tool) -> quyết định gửi

Ba cơ chế an toàn nằm ở đây, không nằm trong prompt:
    1. Trần chi phí mỗi hội thoại -> vượt thì chuyển người.
    2. Chế độ assist -> agent soạn, người bấm gửi.
    3. Cờ escalate từ tool -> khoá hội thoại lại cho người xử lý.
"""
from __future__ import annotations

import re
from contextlib import suppress

import uuid
from dataclasses import dataclass, field

from agent import db
from agent.config import ROOT, settings
from agent.core import llm, rag, tools
from agent.core import ho_so_khach, phong_thu

SYSTEM = (ROOT / "agent" / "prompts" / "system.md").read_text(encoding="utf-8")
MAX_TOOL_ROUNDS = 4


@dataclass(slots=True)
class Reply:
    text: str
    escalate: bool = False
    escalate_reason: str = ""
    grounded: bool = False
    confidence: float = 0.0
    sources: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    latency_ms: int = 0
    model: str = ""
    video_id: str | None = None
    # Ảnh agent muốn gửi kèm. Tool chỉ BÁO, lớp kênh trong main.py mới gửi
    # — tool không biết mình đang chạy trên Zalo hay Chatwoot, và không nên
    # biết. Cùng cách `video_id` được xử lý.
    anh_can_gui: list[dict] = field(default_factory=list)



# ---------------------------------------------------------------
#  Chốt chặn CỨNG cho luật tuân thủ
# ---------------------------------------------------------------
# Với quy định về quảng cáo mỹ phẩm và ranh giới tư vấn y tế, KHÔNG được
# phó mặc cho model tự nhớ gọi tool. Nếu câu hỏi của khách chạm vào các
# tình huống dưới đây thì buộc chuyển người, bất kể model làm gì.
_BUOC_CHUYEN = (
    # thai kỳ và cho con bú
    "mang thai", "bầu", "có bầu", "cho con bú", "đang bú",
    # đang điều trị y tế
    "bác sĩ", "bac si", "theo toa", "đơn thuốc", "bôi thuốc", "uống thuốc",
    "đang điều trị", "da liễu",
    # hỏi VỀ thuốc — là câu hỏi y tế, không phải câu hỏi danh mục hàng hoá
    "thuốc uống", "thuốc bôi", "thuốc trị", "kháng sinh", "isotretinoin",
    # bệnh lý da
    "viêm da", "mụn viêm", "mụn bọc", "mụn mủ", "nám", "chàm", "vẩy nến",
    "dị ứng", "kích ứng nặng",
    # da đang phản ứng
    "đỏ rát", "ngứa rát", "nổi sẩn", "sưng đỏ", "bong tróc", "phồng rộp",

    # TRẺ EM — bổ sung sau khi bộ 56 câu vàng bắt được ca trượt.
    #
    # `data/knowledge/an-toan-va-chong-chi-dinh.md` ghi rõ: "với trẻ nhỏ,
    # luôn chuyển cho nhân viên thay vì tự tư vấn". Nhưng không từ khoá nào
    # canh, nên câu "Con em 8 tuổi dùng kem chống nắng này được không?" đi
    # thẳng vào agent, và nó hỏi lại tên sản phẩm thay vì chuyển người.
    #
    # Dùng cụm HAI TỪ chứ không dùng "con" hay "bé" trần: hai chữ đó quá
    # phổ biến trong tiếng Việt và sẽ chuyển người cho hàng loạt câu vô hại.
    "con em", "con tôi", "con mình", "con gái", "con trai", "cho bé",
    "bé nhà", "em bé", "trẻ em", "trẻ nhỏ", "cháu nhà", "cho con",

    # ĐÒI CAM KẾT KHỎI BỆNH — cũng do bộ vàng bắt được.
    #
    # `an-toan-va-chong-chi-dinh.md` xếp "hết mụn sau N ngày" và "cam kết
    # khỏi" vào nhóm TUYỆT ĐỐI không được nói (Thông tư 06/2011/TT-BYT).
    # Khách hỏi thẳng "bao lâu thì hết mụn hẳn, shop cam kết đi" là đòi đúng
    # thứ đó — và agent trả lời vòng vo thay vì chuyển người.
    #
    # KHÔNG bắt "cam kết" trần: shop CÓ mục "bảo hành và cam kết chất
    # lượng", và chặn từ đó là agent chuyển người khi khách hỏi bảo hành.
    "cam kết hết", "cam kết khỏi", "cam kết trị", "đảm bảo hết",
    "đảm bảo khỏi", "bao lâu thì hết", "bao lâu hết", "hết mụn hẳn",
    "hết hẳn", "khỏi hẳn", "hết nám hẳn",
)


def _bat_buoc_chuyen(question: str) -> str | None:
    low = (question or "").lower()
    for key in _BUOC_CHUYEN:
        if key in low:
            return f"Câu hỏi chạm vào tình huống bắt buộc chuyển người: '{key}'"
    return None


# LƯỚI THỨ SÁU — sinh ra CÙNG LÚC với khả năng nhìn ảnh.
#
# VÌ SAO PHẢI CÓ TRƯỚC KHI BẬT THỊ GIÁC
# --------------------------------------
# `_bat_buoc_chuyen` chỉ đọc CHỮ. Khách gửi ảnh vùng da viêm mà không kèm
# chữ nào — hoặc chỉ viết "da em bị thế này" — thì không từ khoá nào nổ.
#
# Trước đây điều đó vô hại: agent không nhìn được ảnh nên không có gì để mà
# chẩn đoán. Bật thị giác lên là mở đúng cánh cửa đó: model NHÌN THẤY vùng
# da đỏ và câu trả lời tự nhiên nhất của nó là gọi tên bệnh.
#
# Gọi tên bệnh cho khách là hành nghề y không phép. Với một cửa hàng mỹ phẩm
# thì đó là ranh giới không được chạm, bất kể model tự tin đến đâu.
#
# Bắt theo CẤU TRÚC KHẲNG ĐỊNH, không bắt theo tên bệnh đơn lẻ: tài liệu
# chính sách của shop có quyền nhắc tới "nám" hay "dị ứng", và cấm cả từ đó
# là agent chuyển người mỗi lần đọc chính sách của mình.
# KHÔNG có "em" trong danh sách chủ ngữ.
#
# Trong lời ăn tiếng nói chăm sóc khách hàng của người Việt, "em" là CHÍNH
# NHÂN VIÊN, không phải khách: "bên em có chính sách...", "em gửi chị ảnh".
# Đưa "em" vào thì câu chính sách "bên em đổi trả nếu khách bị dị ứng" bị
# bắt nhầm — đo được ngay lần chạy thử đầu tiên.
_CHAN_DOAN_RE = re.compile(
    r"("
    r"(bạn|chị|anh|mình|da|vùng da|tình trạng|ảnh|hình)"
    r"[^.!?]{0,45}?(bị|đang bị|mắc|là|cho thấy|trông giống)"
    r"|(đây|cái này|kia) (là|có vẻ là|chính là)"
    r")"
    r"[^.!?]{0,25}?"
    r"(viêm da|viêm nang lông|mụn viêm|mụn bọc|mụn mủ|mụn nội tiết"
    r"|nám|tàn nhang|chàm|eczema|vẩy nến|vảy nến|rosacea|trứng cá đỏ"
    r"|nấm da|zona|herpes|thuỷ đậu|thủy đậu|u hắc tố|ung thư da"
    r"|dị ứng|viêm nhiễm|nhiễm trùng)",
    re.IGNORECASE,
)


# Câu ĐIỀU KIỆN không phải chẩn đoán.
#
# "Bên em đổi trả nếu khách bị dị ứng trong 7 ngày" là nói CHÍNH SÁCH cho
# một tình huống giả định. "Da chị bị dị ứng rồi ạ" mới là gọi tên bệnh cho
# một người cụ thể đang ngồi trước mặt.
#
# Chặn nhầm loại thứ nhất thì agent chuyển người mỗi lần đọc chính sách của
# chính shop — và người trực sẽ tắt lưới đi sau vài ngày.
_DIEU_KIEN = ("nếu", "neu ", "trường hợp", "truong hop", "khi nào", "giả sử",
              "trong trường hợp", "phòng khi")


def _chan_doan_y_te(text: str) -> str | None:
    """
    Agent có đang gọi tên bệnh cho MỘT KHÁCH CỤ THỂ không.

    Trả lý do để ghi vào nhật ký, hoặc None nếu câu trả lời sạch.
    """
    for m in _CHAN_DOAN_RE.finditer(text or ""):
        # Chỉ xét trong CÙNG MỘT CÂU: dấu chấm ở câu trước không liên quan.
        dau_cau = max(
            (text.rfind(d, 0, m.start()) for d in ".!?\n"), default=-1,
        )
        truoc = text[dau_cau + 1:m.start()].lower()
        if any(dk in truoc for dk in _DIEU_KIEN):
            continue
        return f"Agent chẩn đoán y tế cho khách: '{m.group(0)[:70].strip()}'"
    return None


# Câu chữ cho thấy agent đang hứa chuyển hội thoại cho người thật.
_HANDOFF_HINTS = (
    "chuyển thông tin",
    "chuyển cho nhân viên",
    "chuyển anh",
    "chuyển chị",
    "chuyển mình",
    "chuyển qua cho",
    "chuyên môn tư vấn",
    "nhân viên bên em sẽ",
    "bạn phụ trách",
    "liên hệ lại với",
    "hỏi ý kiến bác sĩ",
    "trao đổi với bác sĩ",
)


# Danh sách chuỗi cố định ở trên quá giòn: agent diễn đạt lời hứa chuyển
# người bằng vô số cách, và mỗi cách trượt là một lần khách bị bỏ rơi giữa
# chừng — agent nói "em chuyển cho nhân viên" rồi không ai nhận việc.
# Mẫu này bắt cấu trúc "chuyển ... cho <người có thẩm quyền>" trong cùng một
# câu, thay vì đoán trước từng cách nói.
_HANDOFF_RE = re.compile(
    r"(chuyển|nhờ|báo|gửi|kết nối)[^.!?]{0,60}?"
    r"(nhân viên|chuyên viên|chuyên môn|chuyên trách|phụ trách|bộ phận"
    r"|tư vấn viên|quản lý|người có chuyên môn)",
    re.IGNORECASE,
)


# Model đôi khi viết "để em kiểm tra giá nha" rồi DỪNG, không gọi công cụ.
# Khách nhận một lời hứa thay vì câu trả lời, và không có gì trong hệ thống
# biết là mình vừa bỏ dở. Prompt đã cấm rõ điều này mà model vẫn trượt —
# nên phải có lưới an toàn trong mã, đúng như với lời hứa chuyển người.
_STALL_RE = re.compile(
    r"(để em|em sẽ|em xin|cho em)[^.!?]{0,40}"
    r"(kiểm tra|tra cứu|xem lại|kiểm tra lại|check|hỏi lại|báo lại|xác nhận)",
    re.IGNORECASE,
)


def _stalls(text: str) -> bool:
    return bool(_STALL_RE.search(text or ""))


def _promises_handoff(text: str) -> bool:
    low = (text or "").lower()
    if any(hint in low for hint in _HANDOFF_HINTS):
        return True
    return bool(_HANDOFF_RE.search(text or ""))


def _confidence(passages: list[rag.Passage], co_du_lieu: bool) -> float:
    """
    Ước lượng độ tin cậy thô: điểm khớp RAG cao nhất, cộng thưởng nếu câu
    trả lời dựa trên dữ liệu hệ thống (tool) thay vì tài liệu.

    `co_du_lieu` KHÔNG phải "đã gọi tool" — nó là "tool đã trả về dữ liệu
    thật". Phân biệt này quan trọng từ khi có `tim_kien_thuc`: một lời gọi
    tra cứu KHÔNG TÌM THẤY GÌ mà vẫn được cộng thưởng thì agent tra hụt lại
    trông tự tin hơn agent không thèm tra — và chốt chuyển người vì độ tin
    cậy thấp sẽ không bao giờ nổ nữa.

    Đó đúng là xanh giả: thưởng cho hành vi mình muốn ngăn.
    """
    base = max((p.score for p in passages), default=0.0)
    if co_du_lieu:
        base = max(base, 0.8)
    return round(min(base, 0.99), 3)


# Tool trả về TÀI LIỆU, không trả về dữ liệu hệ thống. Đoạn tìm được đi
# thẳng vào `passages` và tự nâng độ tin cậy qua điểm khớp của chính nó —
# không cần, và không được, cộng thưởng thêm lần nữa.
_TOOL_TRA_TAI_LIEU = {"tim_kien_thuc"}


async def _ghi_ho_so(viec, conversation_id: uuid.UUID, buoc: str) -> None:
    """
    Cập nhật hồ sơ khách. Hỏng thì KHÔNG chặn câu trả lời, nhưng phải kêu.

    VÌ SAO KHÔNG DÙNG `suppress(Exception)` NHƯ TRƯỚC
    -------------------------------------------------
    Hồ sơ khách là thứ tách agent này khỏi một con chatbot: nó nhớ da dầu,
    nhớ đang mang thai, nhớ đã mua gì. Khi việc ghi hồ sơ hỏng — đổi lược
    đồ, CSDL kẹt, kiểu dữ liệu lạ — agent vẫn trả lời trơn tru, giọng vẫn
    tự nhiên, chỉ là nó bắt đầu hỏi lại những điều khách đã nói. Không ai
    nhìn màn hình mà đoán ra được.

    Đúng họ với `_tu_khoa_loai_da()`: một tính năng chết câm, không nổ,
    không nhật ký, không ai biết. Nuốt lỗi vẫn là lựa chọn đúng ở đây — trí
    nhớ hỏng không đáng để khách mất câu trả lời — nhưng nuốt IM LẶNG thì
    không.
    """
    try:
        await viec
    except Exception as exc:  # noqa: BLE001 — trí nhớ hỏng không được chặn câu trả lời
        # Nhật ký đi qua CSDL, mà CSDL có thể chính là thứ vừa hỏng. Bọc
        # thêm một lớp để việc BÁO lỗi không tự nó thành lỗi mới.
        with suppress(Exception):
            await db.log_event(
                "ho_so.loi", ref_id=conversation_id, buoc=buoc,
                ly_do=f"{type(exc).__name__}: {exc}"[:200],
            )


async def respond(
    *, conversation_id: uuid.UUID, history: list[dict], question: str,
    customer_ref: str = "", channel: str = "",
    anh: list[dict] | None = None,
) -> Reply:
    """
    Sinh câu trả lời cho một lượt. `history` là các lượt trước đã chuẩn hoá.

    `customer_ref` + `channel` mở trí nhớ về khách: những gì đã biết từ các
    lần trước được nhét vào ngữ cảnh, và những gì học được lượt này được ghi
    lại. Bỏ trống thì agent chạy như cũ, không nhớ gì — dùng cho bộ eval,
    nơi mỗi ca phải độc lập.
    """
    conv = await db.fetchrow(
        "SELECT cost_usd FROM conversations WHERE id = $1", conversation_id
    )
    spent = float(conv["cost_usd"]) if conv else 0.0
    if spent >= settings.max_cost_per_conversation:
        return Reply(
            text="Để em chuyển anh/chị sang nhân viên hỗ trợ trực tiếp nhé.",
            escalate=True,
            escalate_reason=f"Vượt trần chi phí hội thoại ({spent:.4f} USD)",
        )

    # Quét prompt injection TRƯỚC khi tốn một lời gọi model nào. Thấy dấu
    # hiệu thì chuyển người ngay — không chặn khách, vì người thật cũng có
    # thể gõ câu lạ, nhưng cũng không để model tự xoay xở với nó.
    co_tan_cong, dau_hieu = phong_thu.quet(question)
    if co_tan_cong:
        await db.log_event(
            "bao_mat.injection", ref_id=conversation_id, dau_hieu=dau_hieu,
            trich=str(question)[:200],
        )
        return Reply(
            text="Để em chuyển anh/chị sang nhân viên hỗ trợ trực tiếp nhé.",
            escalate=True,
            escalate_reason="Tin nhắn có dấu hiệu can thiệp hệ thống: "
                            + ", ".join(dau_hieu),
        )

    passages = await rag.retrieve(question, k=5)
    context = rag.as_context(passages)

    # Trí nhớ về khách đi CÙNG khối biến động với ngữ cảnh RAG, không đi
    # cùng khối ổn định — hồ sơ đổi theo từng khách, đặt nhầm vào khối
    # cached thì mỗi khách lại ghi một bản cache mới và không bao giờ đọc
    # lại được.
    if customer_ref:
        # Quét lời khách TRƯỚC khi dựng ngữ cảnh, để điều vừa nói có mặt
        # ngay trong lượt này chứ không phải chờ tới lượt sau.
        await _ghi_ho_so(
            ho_so_khach.tu_tin_nhan(customer_ref, channel, question),
            conversation_id, "tu_tin_nhan",
        )
        if (ngu_canh_khach := await ho_so_khach.lam_ngu_canh(customer_ref, channel)):
            context = f"{ngu_canh_khach}\n\n{context}" if context else ngu_canh_khach

    # Rào tin khách lại: model đọc phần bên trong như DỮ LIỆU, không phải
    # mệnh lệnh. Lớp thứ hai, phòng khi bộ quét ở trên bỏ sót cách nói mới.
    # Ảnh khách gửi đi CÙNG lượt hỏi, không thành một lượt riêng.
    #
    # Tách ra thì mô hình mất mối liên hệ giữa ảnh và câu hỏi: khách gửi ảnh
    # kèm "cái này còn hàng không ạ" mà hai thứ nằm ở hai lượt thì nó hỏi lại
    # "mình muốn hỏi sản phẩm nào ạ?" — đúng lỗi bản trước đã gặp.
    #
    # `phong_thu.boc` vẫn bọc phần CHỮ như cũ: ảnh không đi qua bộ quét tấn
    # công vì bộ quét đọc chữ, còn chữ chèn trong ảnh thì nó không thấy. Đó
    # là lý do lưới thứ sáu soi ĐẦU RA.
    chu_boc = phong_thu.boc(question)
    noi_dung = ([*anh, {"text": chu_boc}] if anh else chu_boc)
    messages = [*history, {"role": "user", "content": noi_dung}]
    total_cost = 0.0
    tok_in = tok_out = cache_read = latency = 0
    used_tool = False      # đã gọi tool nào chưa — dùng cho lưới "hứa mà không làm"
    co_du_lieu = False     # tool đã trả về DỮ LIỆU THẬT chưa — dùng cho độ tin cậy
    da_thuc = False   # đã nhắc model gọi công cụ chưa (chỉ nhắc một lần)
    escalate = False
    escalate_reason = ""
    video_id: str | None = None
    anh_can_gui: list[dict] = []
    final_text = ""

    for _ in range(MAX_TOOL_ROUNDS):
        result = await llm.complete(
            # Phần ổn định mang cache_control; ngữ cảnh RAG biến động nằm SAU.
            system=llm.cached_system(SYSTEM, context),
            messages=messages,
            model=settings.model_chat,
            tools=tools.TOOLS,
            max_tokens=1500,
            effort="medium",
        )
        total_cost += result.cost_usd
        tok_in += result.tokens_in
        tok_out += result.tokens_out
        cache_read += result.cache_read
        latency += result.latency_ms

        if not result.tool_calls:
            final_text = result.text
            # Hứa đi tra cứu mà chưa gọi công cụ lần nào -> ép thêm một vòng
            # thay vì gửi lời hứa suông cho khách. Chỉ ép ĐÚNG MỘT LẦN, nếu
            # không thì một model cứng đầu sẽ quay vòng tới hết trần chi phí.
            if _stalls(final_text) and not used_tool and not da_thuc:
                da_thuc = True
                messages.append({"role": "assistant", "content": final_text})
                messages.append({"role": "user", "content":
                    "Đừng hứa rồi dừng. Gọi công cụ tra cứu NGAY bây giờ và "
                    "trả lời khách bằng số liệu thật trong cùng lượt này."})
                continue
            break

        used_tool = True
        # Định dạng TRUNG LẬP — lớp llm dịch sang Gemini hay Claude tuỳ provider.
        messages.append(
            {
                "role": "assistant",
                "content": result.text or "",
                "tool_calls": result.tool_calls,
            }
        )

        tool_results: list[dict] = []
        for call in result.tool_calls:
            out = await tools.run_tool(call["name"], call["input"], conversation_id)

            # Hồ sơ dựng từ việc ĐÃ XẢY RA, không từ một lượt model riêng đi
            # "trích xuất thông tin khách hàng". Cách này không tốn thêm
            # đồng nào và quan trọng hơn: không bịa nổi, vì agent chỉ gọi
            # goi_y_san_pham(loai_da="da dầu") khi khách đã nói điều đó.
            if customer_ref:
                await _ghi_ho_so(
                    ho_so_khach.tu_tool(
                        customer_ref, channel, call["name"], call["input"]
                    ),
                    conversation_id, "tu_tool",
                )

            # Đoạn agent TỰ tra được phải nhập vào cùng một rổ căn cứ với
            # đoạn tra sẵn đầu lượt. Không nhập thì `sources` thiếu trích
            # dẫn, `grounded` sai, và độ tin cậy không phản ánh việc agent
            # vừa tìm ra đúng tài liệu cần — tức là nó tra xong rồi bị phạt.
            if call["name"] == "tim_kien_thuc" and out.get("tim_thay"):
                for d in out.get("doan") or []:
                    passages.append(rag.Passage(
                        doc_title=d.get("tai_lieu", ""),
                        content=d.get("noi_dung", ""),
                        score=float(d.get("diem") or 0.0),
                    ))
            elif call["name"] not in _TOOL_TRA_TAI_LIEU:
                co_du_lieu = True

            if call["name"] == "chuyen_nhan_vien":
                escalate = True
                escalate_reason = call["input"].get("ly_do", "")

            # TOOL NÓI CẦN NGƯỜI THÌ CHUYỂN NGƯỜI THẬT — không chờ model
            # nhớ gọi thêm `chuyen_nhan_vien`.
            #
            # `xin_huy_don` và `xin_doi_tra` đều trả `can_chuyen_nhan_vien:
            # True` rồi dặn model trong `ghi_chu`. Nhưng dặn là dặn, và model
            # thì trượt — đó chính là lý do lưới thứ năm tồn tại.
            #
            # Ở đây tệ hơn một lời hứa suông: khách vừa xin huỷ hoặc xin đổi
            # trả, cờ ĐÃ được ghi lên đơn, mà hội thoại không tới tay ai. Đơn
            # nằm im mang một yêu cầu chưa ai nhận, và chính sách đổi trả thì
            # có hạn số ngày.
            elif out.get("can_chuyen_nhan_vien"):
                escalate = True
                escalate_reason = escalate_reason or (
                    f"Công cụ {call['name']} yêu cầu người xử lý"
                )

            if call["name"] == "gui_anh_san_pham" and out.get("gui_duoc"):
                anh_can_gui.append(
                    {"duong_dan": out["duong_dan"], "ten": out["ten"]}
                )

            if call["name"] == "tao_video" and out.get("da_nhan"):
                from agent.video import pipeline

                video_id = await pipeline.request_video(
                    title=call["input"].get("tieu_de", "Video"),
                    brief=call["input"].get("yeu_cau", ""),
                    kind=call["input"].get("loai", "explainer"),
                    conversation_id=conversation_id,
                )
                out["video_id"] = video_id

            tool_results.append(
                {"id": call["id"], "name": call["name"], "output": out}
            )
        messages.append({"role": "tool", "results": tool_results})
        final_text = result.text or final_text
    else:
        final_text = final_text or "Em cần kiểm tra thêm, chuyển anh/chị cho nhân viên nhé."
        escalate = True
        escalate_reason = "Vượt số vòng gọi công cụ cho phép"

    confidence = _confidence(passages, co_du_lieu)
    if confidence < settings.confidence_floor and not co_du_lieu:
        escalate = True
        escalate_reason = escalate_reason or f"Độ tin cậy thấp ({confidence:.2f})"

    # Chốt chặn cứng: luật tuân thủ không được phụ thuộc vào việc model
    # có nhớ gọi tool hay không.
    if not escalate:
        buoc = _bat_buoc_chuyen(question)
        if buoc:
            escalate = True
            escalate_reason = buoc

    # LƯỚI AN TOÀN: model đôi khi VIẾT rằng sẽ chuyển người nhưng KHÔNG gọi
    # tool. Khách đọc thấy lời hứa, còn hội thoại thì không bao giờ tới tay
    # nhân viên. Không được để lời hứa với khách rơi vào khoảng không.
    if not escalate and _promises_handoff(final_text):
        escalate = True
        escalate_reason = "Agent nói sẽ chuyển người nhưng không gọi công cụ"

    # LƯỚI THỨ SÁU: chặn chẩn đoán y tế trong CHÍNH câu trả lời.
    #
    # Đặt sau cùng và soi ĐẦU RA, vì đây là chỗ duy nhất bắt được ca nguy
    # hiểm nhất: khách gửi ảnh da không kèm chữ, mọi lưới đọc-chữ đều im, và
    # model nhìn thấy vùng đỏ rồi tự gọi tên bệnh.
    if not escalate:
        chan_doan = _chan_doan_y_te(final_text)
        if chan_doan:
            escalate = True
            escalate_reason = chan_doan

    return Reply(
        text=final_text.strip() or "Em chưa rõ ý anh/chị, anh/chị nói thêm giúp em nhé.",
        escalate=escalate,
        escalate_reason=escalate_reason,
        anh_can_gui=anh_can_gui,
        grounded=bool(passages) or co_du_lieu,
        confidence=confidence,
        sources=list(dict.fromkeys(p.doc_title for p in passages)),
        cost_usd=total_cost,
        tokens_in=tok_in,
        tokens_out=tok_out,
        cache_read=cache_read,
        latency_ms=latency,
        model=settings.model_chat,
        video_id=video_id,
    )
