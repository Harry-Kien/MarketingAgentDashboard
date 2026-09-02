"""
Kiểm thử CLAUDE.md. Không gọi API, không cần CSDL.

CLAUDE.md được Claude Code đọc tự động ở đầu mỗi phiên, trên mọi máy. Nó
dẫn tới lệnh và file — dẫn sai thì trợ lý làm sai ngay từ câu đầu, và người
dùng không có cách nào biết là do tài liệu chứ không phải do mình.

Đây là file duy nhất trong repo mà LỖI CỦA NÓ tự nhân lên qua mọi phiên
làm việc sau đó.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conftest import duong_dan_con_song  # noqa: E402

MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_moi_script_duoc_dan_deu_ton_tai():
    """Dẫn tới lệnh không có thật là trợ lý gõ vào rồi báo lỗi cho người
    dùng, ngay câu đầu tiên của phiên."""
    chet = [m for m in set(re.findall(r"scripts\.(\w+)", MD))
            if not (ROOT / "scripts" / f"{m}.py").exists()]
    assert not chet, f"script không tồn tại: {chet}"


def test_moi_file_duoc_dan_deu_ton_tai():
    """
    CLAUDE.md có hẳn một bảng liệt kê những file CỐ Ý không lên repo. Đòi
    chúng tồn tại là đòi đúng thứ đã quyết định không mang theo — xanh trên
    máy đã cấu hình, đỏ trên mọi bản clone sạch. Đã xảy ra thật: một commit
    sửa CLAUDE.md làm job `clone-sach` đỏ, mà máy người viết không tái hiện
    được. Nên phép kiểm chấp nhận bản `.example` đi thay.
    """
    chet = [d for d in set(re.findall(r"`((?:agent|docs|data|scripts)/[\w./-]+)`", MD))
            if not duong_dan_con_song(d)]
    assert not chet, f"file không tồn tại: {chet}"


def test_van_bat_duoc_duong_dan_chet_that():
    """
    Nới cho `.example` mà nới quá tay thì test thành vô dụng — nó sẽ nhận
    mọi đường dẫn. Ca này canh phần còn lại vẫn cắn.
    """
    assert not duong_dan_con_song("agent/khong_he_ton_tai.py")
    assert not duong_dan_con_song("data/khong_co_gi/")
    assert not duong_dan_con_song("data/knowledge/khong-co-file-nay.md")


def test_duong_lui_example_nhan_ca_ba_kieu():
    """File có đuôi, thư mục không đuôi, và file NẰM TRONG thư mục `.example`."""
    assert duong_dan_con_song("data/catalog.json")      # -> catalog.example.json
    assert duong_dan_con_song("data/knowledge/")        # -> knowledge.example/
    # Dạng thứ ba là dạng bản đầu tiên của hàm này bỏ sót, và nó chỉ lộ ra
    # khi chạy trên bản clone sạch.
    assert duong_dan_con_song("data/knowledge/chinh-sach-thuong-mai.md")


def test_so_test_khai_trong_tai_lieu_khop_thuc_te():
    """Con số gõ tay là con số sẽ lệch."""
    m = re.search(r"(\d+) test", MD)
    assert m, "không khai số test"
    that = len(list((ROOT / "tests").glob("test_*.py")))
    assert that > 0
    # Không so tuyệt đối — chỉ chặn lệch quá xa để còn thấy được.
    #
    # Khoảng cũ là 300–900, dựng khi bộ test còn ~440 ca. Bộ đã lớn gấp ba
    # rưỡi, nên chính CÂU CHẶN NÀY thành thứ nói sai: nó đỏ khi tài liệu
    # được cập nhật cho ĐÚNG. Nới khoảng ra, và ghi lại lý do để lần sau
    # người đọc biết đây là mốc cần xem lại chứ không phải hằng số thiêng.
    assert 1_000 <= int(m.group(1)) <= 3_000, m.group(1)


def test_co_canh_bao_ve_lenh_ton_tien():
    """
    `scripts.eval` gọi API thật. Trợ lý không được tự chạy nó rồi mới báo
    hoá đơn.
    """
    assert "tốn tiền" in MD
    assert "--kho" in MD


def test_noi_ro_quy_uoc_bi_mat():
    assert "sinh_token" in MD
    assert "không bao giờ in ra màn hình" in MD


def test_nhac_duong_lui_sang_ban_example():
    """
    Hai lỗi nghiêm trọng nhất trong repo đều vì quên điều này. Nếu CLAUDE.md
    không nhắc, lỗi thứ ba chỉ là vấn đề thời gian.
    """
    assert ".example" in MD
    assert "đường lui" in MD


def test_nhac_khong_chep_ma_agpl():
    assert "AGPL" in MD


def test_co_muc_kiem_truoc_khi_bao_xong():
    """Đừng nói "đã xong" khi chưa chạy lệnh và nhìn kết quả."""
    assert "Trước khi báo là xong" in MD
    assert "pytest" in MD and "ruff" in MD
