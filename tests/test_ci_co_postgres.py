"""
CI phải chạy được test chạm Postgres thật.

ĐO ĐƯỢC 11.09.2026: workflow không đặt `TEST_DATABASE_URL`, nên mọi test mở
đầu bằng

    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

không bao giờ chạy — và bảng kết quả vẫn xanh. Lần chạy nền trước A1:
2718 passed, 8 skipped.

Vì sao việc này thuộc A1 chứ không A2: ràng buộc trung tâm của A2 ("nhân
viên chỉ thấy khách của mình") sống trong một mệnh đề WHERE. Viết test cho
nó theo khuôn hiện tại là viết một test không bao giờ chạy — tức là dựng
xong cả lớp phân quyền rồi tin vào một dấu xanh không kiểm gì.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "kiem-thu.yml"


def test_workflow_co_service_postgres():
    noi_dung = WORKFLOW.read_text(encoding="utf-8")
    assert "TEST_DATABASE_URL" in noi_dung, (
        "CI chưa cấp TEST_DATABASE_URL — mọi test chạm Postgres sẽ bị skip "
        "và bảng kết quả vẫn xanh"
    )
    assert "pgvector/pgvector" in noi_dung, (
        "Lược đồ có CREATE EXTENSION vector; ảnh postgres thường thiếu "
        "extension và migration sẽ ném"
    )


def test_ca_hai_job_chay_pytest_deu_co_csdl():
    """
    `clone-sach` cũng chạy `pytest tests/`. Thiếu CSDL ở đó thì cùng bộ test
    cho hai kết quả khác nhau giữa hai job — và job yếu hơn vẫn xanh, nên
    không ai để ý bên nào đang thật sự kiểm.
    """
    noi_dung = WORKFLOW.read_text(encoding="utf-8")
    assert noi_dung.count("TEST_DATABASE_URL:") >= 2, (
        "Cả job `pytest` lẫn job `clone-sach` đều phải có TEST_DATABASE_URL"
    )


def test_workflow_dung_luoc_do_truoc_khi_chay_test():
    """
    Cấp URL thôi chưa đủ: test tích hợp truy vấn bảng có thật, nên lược đồ
    phải được dựng trước. Thiếu bước này thì test đổi từ `skipped` sang
    `UndefinedTableError` — đỏ, nhưng đỏ vì hạ tầng, và người ta sẽ chữa
    bằng cách bỏ `TEST_DATABASE_URL` đi cho xanh lại.
    """
    noi_dung = WORKFLOW.read_text(encoding="utf-8")
    assert "dung_csdl_kiem_thu" in noi_dung


@pytest.mark.skipif(not os.getenv("CI"), reason="chỉ bắt buộc khi chạy trong CI")
def test_trong_ci_thi_phai_co_that_database_url():
    """
    Chốt thứ hai, ở tầng CHẠY chứ không tầng đọc file.

    Một lần sửa workflow vô ý có thể giữ nguyên chuỗi "TEST_DATABASE_URL"
    trong file mà vẫn không truyền nó tới pytest — ba test trên vẫn xanh.
    Test này thì không.
    """
    assert os.getenv("TEST_DATABASE_URL"), (
        "Đang chạy trong CI nhưng pytest không thấy TEST_DATABASE_URL"
    )
