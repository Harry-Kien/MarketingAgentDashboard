"""
Checksum migration không được phụ thuộc vào cách xuống dòng.

LỖI THẬT ĐÃ GẶP (02.09.2026). Git trên Windows mặc định `core.autocrlf=
true`. Repo lúc đó chưa có `.gitattributes`, nên một lệnh `git checkout`
bình thường viết lại mọi tệp .sql từ LF sang CRLF. Nội dung SQL không đổi
một ký tự, nhưng sha256 đổi hoàn toàn.

Hệ quả: ứng dụng KHÔNG KHỞI ĐỘNG ĐƯỢC, kèm thông báo "checksum migration đã
áp dụng không khớp" — nghe như có người sửa một migration đã chạy, tức là
chỉ đúng hướng điều tra sai. Người mới clone repo trên Windows đâm thẳng
vào bức tường này ngay lần chạy đầu.

Hai lớp bảo vệ, và tệp này canh cả hai:
  1. `runner._chuan_hoa` bỏ CR trước khi băm
  2. `.gitattributes` ép .sql giữ LF
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.migrations.runner import (  # noqa: E402
    VERSIONS_DIR,
    _chuan_hoa,
    discover_migrations,
)


def test_crlf_va_lf_cho_cung_checksum():
    """Khẳng định trung tâm của cả tệp này."""
    lf = b"CREATE TABLE a (\n  id INT\n);\n"
    crlf = b"CREATE TABLE a (\r\n  id INT\r\n);\r\n"
    assert _chuan_hoa(lf) == _chuan_hoa(crlf)
    assert (
        hashlib.sha256(_chuan_hoa(lf)).hexdigest()
        == hashlib.sha256(_chuan_hoa(crlf)).hexdigest()
    )


def test_cr_don_cung_duoc_chuan_hoa():
    """Kiểu xuống dòng của macOS đời cũ. Hiếm, nhưng chuẩn hoá thì làm cho trót."""
    assert _chuan_hoa(b"a\rb") == _chuan_hoa(b"a\nb") == b"a\nb"


def test_tuong_thich_nguoc_voi_tep_von_dung_LF():
    """
    Tệp vốn dùng LF phải băm ra ĐÚNG giá trị cũ, nếu không mọi CSDL đang
    chạy sẽ bị chặn ngay lần khởi động kế tiếp — biến một bản vá thành một
    sự cố.
    """
    lf = b"SELECT 1;\n"
    assert _chuan_hoa(lf) == lf


def test_doi_noi_dung_SQL_thi_checksum_VAN_phai_lech():
    """
    Chốt vẫn phải còn tác dụng. Nới lỏng tới mức mọi thay đổi đều lọt thì
    checksum thành đồ trang trí — và sửa một migration đã chạy sẽ không ai
    biết.
    """
    a = hashlib.sha256(_chuan_hoa(b"CREATE TABLE a (id INT);\n")).hexdigest()
    b = hashlib.sha256(_chuan_hoa(b"CREATE TABLE a (id BIGINT);\n")).hexdigest()
    assert a != b


def test_moi_migration_tren_dia_deu_bam_duoc():
    ds = discover_migrations()
    assert ds, "không tìm thấy migration nào"
    for m in ds:
        assert len(m.checksum) == 64


def test_checksum_khong_doi_khi_tep_bi_doi_sang_CRLF(tmp_path):
    """
    Mô phỏng đúng thứ đã xảy ra: cùng một migration, hai cách xuống dòng,
    phải ra cùng checksum.
    """
    goc = sorted(VERSIONS_DIR.glob("*.sql"))[0]
    than = goc.read_bytes()

    thu_muc = tmp_path / "versions"
    thu_muc.mkdir()
    ten = goc.name

    (thu_muc / ten).write_bytes(than.replace(b"\r\n", b"\n"))
    dang_lf = discover_migrations(thu_muc)[0].checksum

    (thu_muc / ten).write_bytes(than.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    dang_crlf = discover_migrations(thu_muc)[0].checksum

    assert dang_lf == dang_crlf, (
        "Cùng một migration, đổi cách xuống dòng ra checksum khác — ứng dụng "
        "sẽ không khởi động được sau một lệnh git checkout trên Windows."
    )


def test_co_gitattributes_ep_sql_giu_LF():
    """
    Lớp bảo vệ thứ hai. `_chuan_hoa` cứu được máy đã dính; `.gitattributes`
    ngăn việc dính ngay từ đầu.
    """
    tep = ROOT / ".gitattributes"
    assert tep.exists(), "Thiếu .gitattributes — xem docstring đầu tệp này"
    noi_dung = tep.read_text(encoding="utf-8")
    assert "*.sql" in noi_dung and "eol=lf" in noi_dung, (
        ".gitattributes phải ép *.sql giữ LF"
    )
