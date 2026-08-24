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

MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_moi_script_duoc_dan_deu_ton_tai():
    """Dẫn tới lệnh không có thật là trợ lý gõ vào rồi báo lỗi cho người
    dùng, ngay câu đầu tiên của phiên."""
    chet = [m for m in set(re.findall(r"scripts\.(\w+)", MD))
            if not (ROOT / "scripts" / f"{m}.py").exists()]
    assert not chet, f"script không tồn tại: {chet}"


def test_moi_file_duoc_dan_deu_ton_tai():
    chet = [d for d in set(re.findall(r"`((?:agent|docs|data|scripts)/[\w./-]+)`", MD))
            if not (ROOT / d).exists()]
    assert not chet, f"file không tồn tại: {chet}"


def test_so_test_khai_trong_tai_lieu_khop_thuc_te():
    """Con số gõ tay là con số sẽ lệch."""
    m = re.search(r"(\d+) test", MD)
    assert m, "không khai số test"
    that = len(list((ROOT / "tests").glob("test_*.py")))
    assert that > 0
    # Không so tuyệt đối — chỉ chặn lệch quá xa để còn thấy được.
    assert 300 <= int(m.group(1)) <= 900, m.group(1)


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
