"""
Kiểm thử tài liệu. Không gọi API, không cần CSDL.

Tài liệu khoá luận dẫn tới file mã và tên hàm. Đổi tên một file rồi quên
sửa tài liệu thì hội đồng mở link ra gặp 404 — và đó là ấn tượng khó gỡ
hơn nhiều so với một lỗi kỹ thuật.

Repo này đã có tiền sử: README từng liệt kê bốn thiếu sót đã làm xong từ
lâu, và `he_thong.py` viết rằng proxy "không làm được" trong khi lớp proxy
đang chạy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TAI_LIEU = ROOT / "docs" / "co-so-ly-thuyet.md"
NOI_DUNG = TAI_LIEU.read_text(encoding="utf-8")


def test_moi_file_duoc_dan_deu_ton_tai():
    """
    Bắt đường dẫn dạng `(../agent/core/rag.py)`. Link chết trong tài liệu
    nộp là thứ hội đồng bấm vào đầu tiên.
    """
    chet = []
    for duong in re.findall(r"\]\(\.\./([^)#]+)\)", NOI_DUNG):
        if not (ROOT / duong).exists():
            chet.append(duong)
    assert not chet, f"link chết: {chet}"


def test_moi_tai_lieu_anh_em_deu_ton_tai():
    chet = [d for d in re.findall(r"\]\((?!\.\./|https?://)([^)#]+\.md)\)", NOI_DUNG)
            if not (TAI_LIEU.parent / d).exists()]
    assert not chet, f"link chết: {chet}"


def test_ten_ham_duoc_dan_co_that_trong_ma():
    """Dẫn tên hàm không tồn tại là mô tả một hệ thống khác."""
    src = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    for ten in ("_bat_buoc_chuyen", "_stalls", "_promises_handoff"):
        assert f"def {ten}" in src, ten
        assert ten in NOI_DUNG, f"{ten} không được nhắc trong tài liệu"
    assert "def cached_system" in (ROOT / "agent" / "core" / "llm.py").read_text(
        encoding="utf-8")


def test_so_cong_cu_khop_voi_ma():
    """Con số trong tài liệu phải khớp mã, nếu không nó sẽ lệch âm thầm."""
    src = (ROOT / "agent" / "core" / "tools.py").read_text(encoding="utf-8")
    that = src.count('"name":')
    m = re.search(r"\*\*Trong hệ thống này\.\*\* (\d+) công cụ", NOI_DUNG)
    assert m, "không tìm thấy câu khai số công cụ"
    assert int(m.group(1)) == that, f"tài liệu ghi {m.group(1)}, mã có {that}"


def test_cot_embedding_dung_ten():
    """Đã sai một lần: tài liệu ghi cột tên `vector`, thực tế là
    `embedding` kiểu `vector`."""
    schema = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    assert "embedding   vector" in schema or "embedding" in schema
    assert "chunks.embedding" in NOI_DUNG


def test_co_danh_muc_trich_dan():
    assert "Tài liệu tham khảo" in NOI_DUNG
    assert NOI_DUNG.count("\n1. ") >= 1


def test_noi_ro_phai_tu_kiem_tra_trich_dan():
    """
    Không được để người đọc tưởng danh mục đã kiểm chuẩn trường. Trích dẫn
    thứ mình chưa mở ra đọc là lỗi học thuật, không phải lỗi kỹ thuật.
    """
    assert "tự kiểm tra lại" in NOI_DUNG
