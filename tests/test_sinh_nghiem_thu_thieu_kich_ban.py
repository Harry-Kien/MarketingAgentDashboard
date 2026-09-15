"""
`sinh_nghiem_thu` không được ghi tài liệu khi thiếu kịch bản. Không cần CSDL.

LỖI ĐÃ XẢY RA THẬT (15.09.2026)
-------------------------------
`MCP_TOKEN` được điền vào `.env`. `agent/main.py` dựng `_mcp_app` MỘT LẦN
lúc import, còn `StreamableHTTPSessionManager.run()` của thư viện MCP chỉ
cho gọi một lần mỗi instance. Kịch bản nghiệm thu 1 chạy xong thì vòng đời
đóng lại; kịch bản 2 dựng lại app và nổ `RuntimeError`.

Mười một trong mười hai kịch bản không chạy được. Nhưng chúng hỏng ở bước
DỰNG — pytest gọi đó là ERROR, không phải FAILED — nên plugin gom kết quả
không nhận được bản ghi nào cho chúng. Chúng không hiện ra là hỏng; chúng
biến mất.

Hậu quả dây chuyền, cả ba đều im lặng:

  1. Bảng sinh ra ghi "**1/1 kịch bản đạt**" — đọc ra là 100%.
  2. `all()` chạy trên danh sách một phần tử, trả True, mã thoát 0. Tự động
     hoá nhìn thấy THÀNH CÔNG.
  3. Kèm `--ghi` thì nó ĐÈ LÊN `docs/nghiem-thu.md` đang có 12 mục thật —
     xoá mất bằng chứng nghiệm thu, thay bằng một bảng trông còn đẹp hơn.

Đây đúng là họ với lỗi `zip()` cắt ngầm về danh sách ngắn hơn đã ghi trong
CLAUDE.md: hai đầu lệch nhau, bên ngắn thắng, không ai được báo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import sinh_nghiem_thu  # noqa: E402


def test_dem_dung_so_kich_ban_khai():
    """Đếm phải khớp số `def test_` thật trong file nghiệm thu."""
    that = sum(
        1 for d in sinh_nghiem_thu.TEP_TEST.read_text(encoding="utf-8").splitlines()
        if d.startswith("def test_")
    )
    assert sinh_nghiem_thu.so_kich_ban_khai() == that
    assert that >= 12, f"file nghiệm thu chỉ còn {that} kịch bản — có bị xoá bớt không?"


def test_thieu_kich_ban_thi_KHONG_ghi_va_thoat_khac_0(tmp_path, monkeypatch, capsys):
    """
    Thu được ít hơn số khai → trả 2 và KHÔNG chạm vào tài liệu.

    Đây là toàn bộ lý do file này tồn tại: bảng thiếu kịch bản không được
    phép đè lên bảng đầy đủ.
    """
    doc = tmp_path / "nghiem-thu.md"
    doc.write_text("BẢNG THẬT 12 MỤC", encoding="utf-8")

    monkeypatch.setattr(sinh_nghiem_thu, "TEP_DOC", doc)
    monkeypatch.setattr(sinh_nghiem_thu, "so_kich_ban_khai", lambda: 12)
    monkeypatch.setattr(sinh_nghiem_thu, "chay", lambda: [("test_01", "Đăng nhập.", "đạt")])
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(sys, "argv", ["sinh_nghiem_thu", "--ghi"])

    assert sinh_nghiem_thu.main() == 2
    assert doc.read_text(encoding="utf-8") == "BẢNG THẬT 12 MỤC", "tài liệu đã bị đè"

    loi = capsys.readouterr().err
    assert "1/12" in loi, "thông điệp phải nói RÕ thiếu bao nhiêu, không chỉ 'có lỗi'"


def test_du_kich_ban_thi_ghi_binh_thuong(tmp_path, monkeypatch):
    """Lưới mới không được chặn nhầm lần chạy đầy đủ."""
    doc = tmp_path / "nghiem-thu.md"
    kq = [(f"test_{i:02d}", f"Kịch bản {i}.", "đạt") for i in range(1, 13)]

    monkeypatch.setattr(sinh_nghiem_thu, "TEP_DOC", doc)
    # ROOT theo cùng, vì thông điệp thành công in đường dẫn TƯƠNG ĐỐI so với nó.
    monkeypatch.setattr(sinh_nghiem_thu, "ROOT", tmp_path)
    monkeypatch.setattr(sinh_nghiem_thu, "so_kich_ban_khai", lambda: 12)
    monkeypatch.setattr(sinh_nghiem_thu, "chay", lambda: kq)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(sys, "argv", ["sinh_nghiem_thu", "--ghi"])

    assert sinh_nghiem_thu.main() == 0
    assert "12/12" in doc.read_text(encoding="utf-8")


def test_co_kich_ban_hong_thi_van_ghi_nhung_thoat_khac_0(tmp_path, monkeypatch):
    """
    Hỏng KHÁC thiếu.

    Kịch bản chạy được mà không đạt thì phải vào bảng — đó là thông tin cần
    ghi lại. Chỉ "không chạy được" mới bị chặn ghi.
    """
    doc = tmp_path / "nghiem-thu.md"
    kq = [(f"test_{i:02d}", f"Kịch bản {i}.", "đạt") for i in range(1, 12)]
    kq.append(("test_12", "Kịch bản 12.", "hỏng"))

    monkeypatch.setattr(sinh_nghiem_thu, "TEP_DOC", doc)
    # ROOT theo cùng, vì thông điệp thành công in đường dẫn TƯƠNG ĐỐI so với nó.
    monkeypatch.setattr(sinh_nghiem_thu, "ROOT", tmp_path)
    monkeypatch.setattr(sinh_nghiem_thu, "so_kich_ban_khai", lambda: 12)
    monkeypatch.setattr(sinh_nghiem_thu, "chay", lambda: kq)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(sys, "argv", ["sinh_nghiem_thu", "--ghi"])

    assert sinh_nghiem_thu.main() == 1
    assert doc.exists()
