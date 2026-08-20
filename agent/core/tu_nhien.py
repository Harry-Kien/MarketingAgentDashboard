"""
Làm câu trả lời giống người thật — và ĐO ĐƯỢC mức độ giống.

VÌ SAO KHÔNG CHỈ DẶN TRONG PROMPT
---------------------------------
`system.md` đã dặn rất kỹ: chào một lần, câu ngắn, không gạch đầu dòng,
không kết bằng "cần hỗ trợ gì thêm không ạ". Model vẫn trượt — đúng như
đã trượt với lời hứa chuyển người và lời hứa tra cứu. Cùng một bài học:
điều gì quan trọng thì phải kiểm bằng mã sau khi model trả lời.

Khác ở chỗ, ba dấu hiệu dưới đây không cần chuyển người mà chỉ cần SỬA:
gạch đầu dòng thì bỏ dấu gạch, chào lần hai thì cắt câu chào, tin quá dài
thì tách thành mấy tin ngắn. Sửa được thì sửa, không cần làm phiền ai.

BA THỨ LÀM LỘ BOT NHANH NHẤT TRONG TIN NHẮN VIỆT
------------------------------------------------
1. Chào lại ở tin thứ hai. Người thật chào đúng một lần.
2. Một khối văn bản dài. Người thật nhắn 2-3 tin ngắn liên tiếp.
3. Trả lời tức thì. Người thật cần vài giây để đọc và gõ.

Hai cái đầu sửa bằng văn bản. Cái thứ ba sửa bằng nhịp gửi — xem `nhip_go`.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------
#  Dấu hiệu lộ bot — mỗi mẫu kèm lý do, để chỉ số nói được vì sao
# ---------------------------------------------------------------

_CHAO = re.compile(
    r"^\s*(dạ\s+)?(em\s+)?(xin\s+)?chào\s+(anh|chị|mình|bạn|quý khách|anh/chị)",
    re.IGNORECASE,
)

_KET_SAO_RONG = re.compile(
    r"(anh/chị|mình|bạn|chị|anh)\s+(còn\s+)?cần\s+(hỗ trợ|tư vấn|giúp)\s*"
    r"(gì\s*)?(thêm)?\s*(không|nữa)",
    re.IGNORECASE,
)

_MO_SAO_RONG = re.compile(
    r"^\s*(cảm ơn|cám ơn)\s+(anh|chị|mình|bạn|anh/chị|quý khách)"
    r"[^.!?\n]{0,40}(quan tâm|liên hệ|nhắn tin)",
    re.IGNORECASE,
)

_GACH_DAU_DONG = re.compile(r"^\s*([-*•+]|\d+[.)])\s+", re.MULTILINE)
_TIEU_DE_MD = re.compile(r"^\s*#{1,6}\s+", re.MULTILINE)
_DAM_MD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)

# Chat Zalo không hiển thị markdown — nó hiện ra nguyên dấu sao, và đó là
# thứ không nhân viên nào gõ.
_DAU_HIEU = (
    (_GACH_DAU_DONG, "gạch đầu dòng"),
    (_TIEU_DE_MD, "tiêu đề markdown"),
    (_DAM_MD, "chữ đậm markdown"),
    (_KET_SAO_RONG, "câu kết sáo rỗng"),
    (_MO_SAO_RONG, "câu mở sáo rỗng"),
)

# Trên ngưỡng này thì một khối văn bản đọc như email chứ không như tin nhắn.
# 180 chứ không phải 320: đo lại tin nhắn thật của nhân viên bán mỹ phẩm
# trên Zalo thì hiếm khi vượt 3 câu. Một khối 260 ký tự tuy "chưa dài lắm"
# nhưng vẫn lộ ngay là máy soạn, vì người thật đã tách làm hai tin rồi.
DAI_TOI_DA = 180
# Tin lẻ ngắn hơn mức này thì nhập lại với tin trước, tránh kiểu nhắn
# nhát gừng từng mẩu ba chữ.
NGAN_TOI_THIEU = 40
SO_TIN_TOI_DA = 3


def cham_diem(text: str, *, lan_dau: bool) -> list[str]:
    """
    Liệt kê dấu hiệu lộ bot trong một câu trả lời. Rỗng là sạch.

    `lan_dau` = đây có phải tin đầu tiên của hội thoại không. Chào ở tin
    đầu là đúng; chào ở tin thứ hai trở đi là dấu hiệu rõ nhất.
    """
    ra: list[str] = []
    for mau, ly_do in _DAU_HIEU:
        if mau.search(text):
            ra.append(ly_do)
    if not lan_dau and _CHAO.search(text):
        ra.append("chào lại lần nữa")
    if len(text) > DAI_TOI_DA:
        ra.append(f"tin quá dài ({len(text)} ký tự)")
    return ra


# ---------------------------------------------------------------
#  Sửa
# ---------------------------------------------------------------

def _bo_markdown(text: str) -> str:
    text = _TIEU_DE_MD.sub("", text)
    text = _GACH_DAU_DONG.sub("", text)
    text = _DAM_MD.sub(lambda m: m.group(1) or m.group(2) or "", text)
    return text


def _bo_chao_lai(text: str) -> str:
    """Cắt câu chào ở đầu, giữ nguyên phần nội dung phía sau."""
    m = _CHAO.search(text)
    if not m:
        return text
    # Cắt tới hết câu chào, không cắt cả đoạn.
    sau = text[m.end():]
    dau_cau = re.search(r"[.!?,\n]", sau)
    con_lai = sau[dau_cau.end():] if dau_cau else sau
    con_lai = con_lai.lstrip()
    # Câu chào là toàn bộ nội dung -> giữ nguyên, thà chào thừa còn hơn
    # gửi tin rỗng.
    return con_lai or text


def _bo_ket_sao_rong(text: str) -> str:
    """
    Bỏ câu kết sáo rỗng ở cuối.

    Phải xét theo DÒNG chứ không chỉ theo dấu chấm: sau khi bỏ gạch đầu
    dòng, một danh sách trở thành nhiều dòng không có dấu chấm nào, nên
    tách theo câu sẽ coi cả khối là một câu và không thấy câu kết nằm ở
    dòng cuối.
    """
    dong = text.split("\n")
    while dong:
        cuoi = dong[-1].strip()
        if not cuoi:
            dong.pop()
            continue
        if not _KET_SAO_RONG.search(cuoi):
            break
        # Dòng cuối có thể lẫn cả nội dung thật lẫn câu kết — chỉ bỏ câu kết.
        cau = [c for c in re.split(r"(?<=[.!?])\s+", cuoi)
               if c.strip() and not _KET_SAO_RONG.search(c)]
        if cau:
            dong[-1] = " ".join(cau)
            break
        dong.pop()
    return "\n".join(dong).strip()


def _tach_tin(text: str) -> list[str]:
    """
    Tách một khối dài thành 2-3 tin ngắn, cắt ở ranh giới câu.

    Cắt giữa câu thì đọc như mạng lag chứ không như người nhắn, nên chỉ
    cắt sau dấu chấm. Đoạn xuống dòng sẵn có được tôn trọng trước.
    """
    text = text.strip()
    if len(text) <= DAI_TOI_DA:
        return [text] if text else []

    # Model tự xuống dòng thì đó đã là ý định tách tin của nó.
    doan = [d.strip() for d in re.split(r"\n{2,}|\n", text) if d.strip()]
    if len(doan) > 1:
        manh = doan
    else:
        manh = [c.strip() for c in re.split(r"(?<=[.!?])\s+", text) if c.strip()]

    tin: list[str] = []
    for m in manh:
        if tin and len(tin[-1]) < NGAN_TOI_THIEU:
            tin[-1] = f"{tin[-1]} {m}".strip()
        elif tin and len(tin[-1]) + len(m) + 1 <= DAI_TOI_DA and len(tin) >= SO_TIN_TOI_DA:
            tin[-1] = f"{tin[-1]} {m}".strip()
        else:
            tin.append(m)

    # Quá nhiều mẩu thì gộp phần đuôi — NHƯNG chỉ khi gộp xong vẫn dưới
    # ngưỡng. Không có điều kiện này, vòng gộp tạo ra đúng thứ nó đang
    # tránh: một lần chạy thật đã sinh ra tin 884 ký tự, gấp 5 lần ngưỡng.
    # Thà nhắn thừa một tin ngắn còn hơn dội cho khách một bức tường chữ.
    while len(tin) > SO_TIN_TOI_DA:
        if len(tin[-2]) + len(tin[-1]) + 1 > DAI_TOI_DA:
            break
        tin[-2] = f"{tin[-2]} {tin[-1]}".strip()
        tin.pop()
    return tin


def lam_tu_nhien(text: str, *, lan_dau: bool) -> list[str]:
    """
    Trả về danh sách tin nhắn sẵn sàng gửi, theo đúng thứ tự.

    Luôn trả ít nhất một phần tử nếu đầu vào có nội dung — không được im
    lặng nuốt câu trả lời chỉ vì bộ lọc quá tay.
    """
    if not text or not text.strip():
        return []
    goc = text
    text = _bo_markdown(text)
    if not lan_dau:
        text = _bo_chao_lai(text)
    text = _bo_ket_sao_rong(text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return _tach_tin(text) or [goc.strip()]


# ---------------------------------------------------------------
#  Nhịp gửi
# ---------------------------------------------------------------

def nhip_go(text: str, *, toi_da: float = 4.0) -> float:
    """
    Số giây một người thật cần để gõ đoạn này.

    Người Việt nhắn tin trên điện thoại khoảng 25-35 từ mỗi phút. Nhưng
    đây không phải bài mô phỏng: mục tiêu là tin thứ hai không nhảy ra
    cùng lúc với tin thứ nhất, chứ không phải bắt khách chờ đúng như gõ
    tay. Nên có trần, mặc định 4 giây.
    """
    tu = len(text.split())
    giay = 0.8 + tu / 5.0          # ~300 từ/phút, nhanh hơn người thật có chủ ý
    return round(min(giay, toi_da), 2)


def khong_dau(s: str) -> str:
    """Bỏ dấu — dùng khi so khớp, không dùng khi hiển thị."""
    t = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")
