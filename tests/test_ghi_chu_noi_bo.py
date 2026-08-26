"""
Ghi chú nội bộ KHÔNG BAO GIỜ được đi vào câu trả lời cho khách.

VÌ SAO ĐÂY LÀ RÀNG BUỘC PHẢI CANH BẰNG TEST
--------------------------------------------
Người trực ghi những câu chỉ dành cho nhau: "khách này khó tính, đừng giảm
giá", "đang nợ tiền đơn trước", "gọi ba lần không nghe máy". Đó là lý do
tính năng này tồn tại — và cũng là lý do nó nguy hiểm.

Hôm nay agent KHÔNG đọc bảng `contact_notes`, nên chưa có rò rỉ nào. Nhưng
đó là sự thật của hiện tại, không phải một ràng buộc.

Một ngày nào đó sẽ có người nghĩ: "cho agent đọc ghi chú thì nó tư vấn sát
hơn". Nghe rất hợp lý. Rồi agent nhắn cho khách: "Dạ em thấy ghi chú bên
em có nói mình khó tính ạ."

Không có gì trong hệ thống ngăn được điều đó, trừ file này.

VÌ SAO KHÔNG PHẢI "CỨ CHO ĐỌC RỒI DẶN ĐỪNG NÓI RA"
---------------------------------------------------
Nguyên tắc số một của dự án: ràng buộc nằm trong MÃ, không nằm trong prompt.
Dặn mô hình "đừng nhắc tới ghi chú" là một yêu cầu; mô hình sinh xác suất
nên vẫn trượt. Không đưa vào ngữ cảnh thì nó KHÔNG THỂ nói ra.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ma_khong_chu_thich(nguon: str) -> str:
    """
    Bỏ chú thích và docstring, chỉ giữ mã chạy được.

    Cần vì chú thích trong dự án này thường giải thích VÌ SAO KHÔNG làm một
    điều — nên chúng chứa đúng những chữ mà test đang tìm để cấm. Repo đã mắc
    lỗi soi-nhầm-chú-thích nhiều lần; `tests/test_canh_gac.py` ghi lại.
    """
    import io
    import tokenize

    ra = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(nguon).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            ra.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return " ".join(
            d for d in nguon.splitlines() if not d.strip().startswith("#")
        )
    return " ".join(ra)


def test_agent_KHONG_doc_bang_ghi_chu():
    """Đường sinh câu trả lời không được chạm tới `contact_notes`."""
    from agent.core import agent as brain

    ma = _ma_khong_chu_thich(inspect.getsource(brain))
    assert "contact_notes" not in ma, (
        "agent đang đọc ghi chú nội bộ — nó sẽ nói ra với khách"
    )


def test_tri_nho_khach_cung_KHONG_doc_ghi_chu():
    """
    `ho_so_khach` nhét ngữ cảnh vào prompt. Đây là cửa hậu dễ lọt nhất.
    """
    from agent.core import ho_so_khach

    ma = _ma_khong_chu_thich(inspect.getsource(ho_so_khach))
    assert "contact_notes" not in ma


def test_khong_cong_cu_nao_tra_ve_ghi_chu():
    """
    Agent gọi công cụ để lấy dữ liệu thật. Một công cụ trả ghi chú về là
    ghi chú vào thẳng ngữ cảnh, đường vòng nhưng hậu quả y hệt.
    """
    from agent.core import tools

    ma = _ma_khong_chu_thich(inspect.getsource(tools))
    assert "contact_notes" not in ma


def test_ghi_chu_co_nguoi_viet_va_moc_thoi_gian():
    """
    Ghi chú không biết ai viết là ghi chú không dùng được khi có tranh cãi.

    "Ai bảo khách này được nợ?" — không trả lời được thì tính năng chỉ là
    một ô chữ.
    """
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0004_customer_360.sql").read_text(encoding="utf-8")
    khoi = sql.split("CREATE TABLE IF NOT EXISTS contact_notes", 1)[1].split(");", 1)[0]
    assert "created_by" in khoi
    assert "created_at" in khoi


def test_ghi_chu_bi_xoa_theo_khach():
    """
    Khách yêu cầu xoá dữ liệu thì ghi chú về họ phải đi theo.

    Giữ lại ghi chú sau khi đã xoá hồ sơ là vẫn còn lưu dữ liệu cá nhân —
    Nghị định 13 không quan tâm ta gọi nó là "ghi chú nội bộ".
    """
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0004_customer_360.sql").read_text(encoding="utf-8")
    khoi = sql.split("CREATE TABLE IF NOT EXISTS contact_notes", 1)[1].split(");", 1)[0]
    assert "ON DELETE CASCADE" in khoi


def test_ghi_chu_co_gioi_han_do_dai():
    """Không chặn thì một lần dán nhầm cả trang web vào là hỏng màn hình."""
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0004_customer_360.sql").read_text(encoding="utf-8")
    khoi = sql.split("CREATE TABLE IF NOT EXISTS contact_notes", 1)[1].split(");", 1)[0]
    assert "length(body)" in khoi


def test_ghi_chu_phan_muc_nguoi_xem():
    """`manager` cho việc nhạy cảm, `team` cho phần cả nhóm cần biết."""
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0004_customer_360.sql").read_text(encoding="utf-8")
    khoi = sql.split("CREATE TABLE IF NOT EXISTS contact_notes", 1)[1].split(");", 1)[0]
    assert "visibility" in khoi
    assert "'manager'" in khoi
