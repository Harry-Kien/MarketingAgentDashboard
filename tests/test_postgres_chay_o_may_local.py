"""
Test chạm Postgres phải CHẠY ở máy phát triển, hoặc phải KÊU TO khi không.

ĐO ĐƯỢC 22.09.2026 — `pytest -q` ở máy cho `3150 passed, 124 skipped`, và
124 cái bị bỏ qua chính là nhóm chạm CSDL thật: quyền, phiên, phạm vi tầm
nhìn, khôi phục sao lưu. Container Postgres lúc ấy VẪN ĐANG CHẠY ở cổng
5433. Thiếu đúng một biến môi trường.

Vì sao đáng viết test riêng: CLAUDE.md dặn "trước khi báo là xong, pytest
phải xanh hết". Dấu xanh ấy đang bỏ qua nhóm test canh những ràng buộc đắt
nhất, còn dòng `124 skipped` thì trôi mất giữa 3150 dấu chấm. Đó là xanh
giả — và CLAUDE.md xếp xanh giả nguy hiểm hơn đỏ giả, vì đỏ giả thì người
ta đi kiểm, xanh giả thì không.

CI không dính lỗ này (`test_ci_co_postgres.py` canh workflow). Đây là lỗ ở
vòng lặp tại máy — chỗ test được chạy nhiều nhất.
"""
from __future__ import annotations

import re
from pathlib import Path

import conftest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


def test_bien_moi_truong_luon_thang(monkeypatch):
    """
    Tự dò chỉ là lưới đỡ. Ai đã trỏ tay một CSDL thì phải được tôn trọng,
    nếu không thì test im lặng chạy trên CSDL khác với CSDL người ta định.
    """
    conftest.dia_chi_csdl_kiem_thu.cache_clear()
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://a:b@1.2.3.4:9999/x")
    try:
        assert conftest.dia_chi_csdl_kiem_thu() == "postgresql://a:b@1.2.3.4:9999/x"
    finally:
        conftest.dia_chi_csdl_kiem_thu.cache_clear()


def test_tat_duoc_luoi_tu_do(monkeypatch):
    """Phải có đường tắt: máy nào không muốn test đụng Postgres thì tắt được."""
    conftest.dia_chi_csdl_kiem_thu.cache_clear()
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("KHONG_DUNG_POSTGRES_LOCAL", "1")
    try:
        assert conftest.dia_chi_csdl_kiem_thu() is None
    finally:
        conftest.dia_chi_csdl_kiem_thu.cache_clear()


def test_do_cong_dong_khong_treo():
    """
    Phép dò phải RẺ. Dò bằng cách mở kết nối asyncpg đầy đủ thì mỗi lượt
    chạy test tốn thêm vài giây, và người ta sẽ tắt nó đi.
    """
    assert conftest._co_mo_duoc("postgresql://x@127.0.0.1:1/y", giay=0.2) is False


def test_co_dong_canh_bao_to_khi_bo_qua():
    """
    Bỏ qua thì phải nói to. Không có hook này thì `124 skipped` lại chìm
    xuống một dòng tổng kết mà không ai đọc.
    """
    src = (TESTS / "conftest.py").read_text(encoding="utf-8")
    assert "def pytest_terminal_summary" in src
    assert "TEST POSTGRES KHÔNG CHẠY" in src, (
        "cảnh báo phải nêu rõ chuyện gì không chạy, không chỉ là một con số"
    )
    assert "docker compose up -d db" in src, (
        "cảnh báo phải kèm cách sửa; cảnh báo không có lối ra là cảnh báo "
        "người ta học cách phớt lờ"
    )


def test_khong_con_file_nao_tu_doc_bien_moi_truong():
    """
    Chốt chống tái phát.

    Mẫu cũ `os.getenv("TEST_DATABASE_URL")` rồi `pytest.skip` nằm rải rác ở
    bốn file. Mỗi bản sao là một chỗ KHÔNG hưởng lưới tự dò và KHÔNG góp số
    vào dòng cảnh báo — tức là một phần lỗ cũ vẫn mở, lặng lẽ.
    """
    cho_phep = {"conftest.py", "test_ci_co_postgres.py", "test_postgres_chay_o_may_local.py"}
    pham = []
    for p in sorted(TESTS.glob("*.py")):
        if p.name in cho_phep:
            continue
        s = p.read_text(encoding="utf-8")
        s = re.sub(r'""".*?"""', " ", s, flags=re.S)   # bỏ docstring
        if re.search(r'os\.getenv\(\s*"TEST_DATABASE_URL"', s):
            pham.append(p.name)

    assert not pham, (
        "còn file tự đọc TEST_DATABASE_URL: " + ", ".join(pham)
        + ".\nDùng `from conftest import dia_chi_csdl_kiem_thu, "
        "dem_bo_qua_integration` để hưởng lưới tự dò và được đếm vào cảnh báo."
    )


def test_cac_file_da_chuyen_deu_dem_vao_canh_bao():
    """Gọi `dia_chi_csdl_kiem_thu()` mà quên đếm thì cảnh báo báo thiếu."""
    thieu = []
    for p in sorted(TESTS.glob("*.py")):
        if p.name in {"conftest.py", "test_postgres_chay_o_may_local.py"}:
            continue
        s = p.read_text(encoding="utf-8")
        if "dia_chi_csdl_kiem_thu()" in s and "dem_bo_qua_integration()" not in s:
            thieu.append(p.name)
    assert not thieu, "gọi dia_chi_csdl_kiem_thu nhưng không đếm: " + ", ".join(thieu)
