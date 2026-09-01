"""
Chốt chặn: khung chưa có người điền thì KHÔNG được vào kho tri thức.

VÌ SAO PHẢI LÀ MÃ, KHÔNG PHẢI LỜI DẶN
-------------------------------------
Tệp khung sinh ra trông y như một tài liệu thật: có tiêu đề, có mục, có
cấu trúc. Chạy `scripts.ingest` lên cả thư mục là nó vào pgvector cùng mọi
tài liệu khác, và từ đó `tim_kien_thuc` trả về những dòng như

    "[CẦN NGƯỜI ĐIỀN: Được đổi trả trong bao nhiêu ngày?]"

kèm điểm khớp cao, vì câu hỏi của khách và câu hỏi trong khung dùng chung
từ vựng. Agent đọc đoạn đó như CĂN CỨ.

Nó sẽ không trả lời "7 ngày" — nhưng nó cũng không nói "tôi chưa biết".
Nó nói một câu lấp lửng dựa trên một tài liệu rỗng, và độ tin cậy được
nâng lên bởi chính đoạn rỗng đó. Chốt chuyển người vì độ tin cậy thấp
không nổ nữa.

Đó là xanh giả: khung rỗng làm agent trông tự tin hơn agent không có gì.

KHÔNG chạy `kiem_tra_tuan_thu` lên tài liệu tri thức
----------------------------------------------------
Cám dỗ là dùng lại bộ lọc cụm cấm của `agent/publish/service.py`. Sai:
tài liệu "an toàn và chống chỉ định" BẮT BUỘC phải nhắc tới "trị mụn",
"cam kết khỏi" — vì nhiệm vụ của nó là liệt kê những cụm bị cấm.

Chặn nó là chặn đúng tài liệu quan trọng nhất trong kho.
"""
from __future__ import annotations

import re
from pathlib import Path

from agent.tri_thuc.hop_dong import DAU_CHUA_DIEN

# Bắt cả dòng để báo lại cho người dùng biết CÂU NÀO chưa trả lời — báo
# "còn 7 chỗ trống" mà không nói ở đâu là bắt người ta tự đi dò.
_MAU = re.compile(
    re.escape(DAU_CHUA_DIEN) + r"\s*(.*?)\s*\]",
    re.DOTALL,
)


def thieu_o_dau(noi_dung: str) -> list[str]:
    """Trả về danh sách câu hỏi CHƯA được trả lời. Rỗng nghĩa là đã điền đủ."""
    return [m.group(1).strip() for m in _MAU.finditer(noi_dung or "")]


def da_dien_du(noi_dung: str) -> bool:
    return not thieu_o_dau(noi_dung)


def loc_tep_nap_duoc(
    duong_dan: list[Path],
) -> tuple[list[Path], dict[Path, list[str]]]:
    """
    Chia danh sách tệp thành (nạp được, bị chặn kèm lý do).

    Trả về CẢ HAI thay vì lặng lẽ bỏ phần bị chặn: người chạy lệnh phải
    thấy tệp nào bị giữ lại và còn thiếu câu nào, nếu không họ nạp xong,
    thấy "thành công", và không biết một nửa kho vẫn rỗng.
    """
    nap_duoc: list[Path] = []
    bi_chan: dict[Path, list[str]] = {}
    for p in duong_dan:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # Đọc không được thì để `ingest` xử lý theo đường của nó — chốt
            # này chỉ có một việc, và ôm thêm việc là ôm thêm cách hỏng.
            nap_duoc.append(p)
            continue
        thieu = thieu_o_dau(text)
        if thieu:
            bi_chan[p] = thieu
        else:
            nap_duoc.append(p)
    return nap_duoc, bi_chan
