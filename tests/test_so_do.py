"""
Kiểm thử bộ sinh sơ đồ. Không gọi API, không cần CSDL.

VÌ SAO CANH BỘ SINH SƠ ĐỒ
-------------------------
Sơ đồ vẽ tay đúng đúng một ngày: ngày người ta vẽ nó. Thêm một cột, đổi
một khoá ngoại, và tài liệu bắt đầu nói dối — im lặng, vì không có gì đối
chiếu sơ đồ với schema.

Repo này đã dính đúng chuyện đó hai lần trong một ngày: README liệt kê bốn
thiếu sót đã làm xong từ lâu, và `he_thong.py` viết rằng proxy "không làm
được" trong khi lớp proxy đang chạy.

Sinh từ `schema.sql` thì sơ đồ không thể sai — MIỄN LÀ bộ sinh còn đọc
được schema. Bộ đọc ở đây là regex, không phải bộ phân tích SQL đầy đủ,
nên nó im lặng bỏ sót khi lối viết SQL đổi. Các test dưới đây canh đúng
chỗ im lặng đó.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import sinh_so_do  # noqa: E402

SQL = sinh_so_do.doc_sql()
BANG, KHOA_NGOAI = sinh_so_do.doc_schema()


def test_doc_du_moi_bang_trong_schema():
    """
    Bộ đọc là regex. Đổi lối viết SQL — ví dụ đặt ràng buộc khoá ngoại
    tách riêng ở cuối bảng — thì nó bỏ sót mà KHÔNG báo, và sơ đồ thiếu
    bảng một cách lặng lẽ.
    """
    trong_sql = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", SQL))
    assert set(BANG) == trong_sql, f"lệch: {trong_sql ^ set(BANG)}"


def test_bo_sinh_doc_ca_bang_va_cot_tu_migration():
    """Đọc mỗi baseline sẽ làm tài liệu bỏ sót toàn bộ schema mới."""
    for table in (
        "channel_accounts",
        "credential_secrets",
        "account_memberships",
        "account_health_events",
    ):
        assert table in BANG
    assert ("account_id", "UUID") in BANG["conversations"]


def test_doc_du_moi_khoa_ngoai():
    so_trong_sql = len(re.findall(r"REFERENCES \w+", SQL))
    assert len(KHOA_NGOAI) == so_trong_sql


def test_moi_bang_deu_co_cot():
    """Bảng rỗng trên sơ đồ nghĩa là regex cột trượt, không phải bảng
    thật sự không có cột nào."""
    for ten, cot in BANG.items():
        assert cot, ten


def test_moi_bang_deu_duoc_xep_nhom():
    """
    ERD 16 bảng phẳng thì không ai đọc nổi; chia nhóm là thứ biến một mớ
    hộp thành một câu chuyện. Thêm bảng mới mà quên xếp nhóm thì nó rơi
    vào ô "(chưa xếp nhóm)" — test này bắt trước khi tài liệu ra đời.
    """
    da_xep = {b for ds in sinh_so_do.NHOM.values() for b in ds}
    thieu = set(BANG) - da_xep
    assert not thieu, f"chưa xếp nhóm: {sorted(thieu)}"


def test_khong_xep_nham_bang_khong_ton_tai():
    """Xoá một bảng khỏi schema mà quên xoá khỏi NHOM thì tài liệu vẽ ra
    một bảng không còn tồn tại."""
    da_xep = {b for ds in sinh_so_do.NHOM.values() for b in ds}
    thua = da_xep - set(BANG)
    assert not thua, f"xếp nhóm cho bảng không có thật: {sorted(thua)}"


def test_tai_lieu_sinh_ra_khong_rong_va_co_du_bon_so_do():
    md = sinh_so_do.dung_tai_lieu()
    assert md.count("```mermaid") == 4, "thiếu sơ đồ"
    for phan in ("Sơ đồ khối", "Luồng một tin nhắn",
                 "Trường hợp sử dụng", "Cơ sở dữ liệu"):
        assert phan in md, phan


def test_tai_lieu_noi_ro_phan_nao_sinh_ra():
    """
    Người đọc phải biết chỗ nào sửa tay được, chỗ nào sửa xong sẽ bị ghi
    đè ở lần sinh sau.
    """
    md = sinh_so_do.dung_tai_lieu()
    assert "SINH RA" in md
    assert "scripts.sinh_so_do" in md


def test_file_tai_lieu_da_duoc_sinh_lai():
    """
    File trong repo phải khớp với thứ bộ sinh tạo ra HÔM NAY. Lệch nghĩa
    là ai đó đổi schema mà quên chạy lại — đúng kiểu tài liệu bắt đầu nói
    dối.
    """
    ra = ROOT / "docs" / "kien-truc.md"
    assert ra.exists(), "chưa chạy: python -m scripts.sinh_so_do --ghi"
    assert ra.read_text(encoding="utf-8") == sinh_so_do.dung_tai_lieu(), \
        "docs/kien-truc.md đã cũ — chạy lại: python -m scripts.sinh_so_do --ghi"
