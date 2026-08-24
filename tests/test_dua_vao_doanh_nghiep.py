"""
Kiểm thử `docs/dua-vao-doanh-nghiep.md`. Không gọi API, không cần CSDL.

VÌ SAO FILE NÀY TỒN TẠI
-----------------------
`docs/thuc-nghiem.md` và `docs/kien-truc.md` được SINH RA từ mã và dữ liệu,
và có test canh chúng đã cũ chưa. `CLAUDE.md` có `test_claude_md.py` canh.

`dua-vao-doanh-nghiep.md` thì không có gì canh — và nó là tài liệu người ta
đọc để quyết định CÓ CHẠY VỚI KHÁCH THẬT HAY KHÔNG. Hậu quả đã xảy ra: nó
ghi "Bộ đo nhiều lượt đã có, nhưng CHƯA CHẠY LẦN NÀO" trong khi `data/eval/`
đã có hai file kết quả và tài liệu sinh ra báo 11/12. Không ai biết, vì
không có gì kiểm.

Văn xuôi thì người ta đọc một lần rồi tin là mình đã làm. Chính tài liệu
này viết ra câu đó — rồi tự nó mắc đúng lỗi đó.
"""
from __future__ import annotations

import glob
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conftest import duong_dan_con_song  # noqa: E402

MD = (ROOT / "docs" / "dua-vao-doanh-nghiep.md").read_text(encoding="utf-8")



def test_moi_duong_dan_duoc_dan_deu_ton_tai():
    chet = [d for d in set(re.findall(r"`((?:agent|docs|data|scripts)/[\w./-]+)`", MD))
            if not duong_dan_con_song(d)]
    assert not chet, f"đường dẫn không tồn tại: {chet}"


def test_moi_script_duoc_dan_deu_ton_tai():
    chet = [m for m in set(re.findall(r"scripts\.(\w+)", MD))
            if not (ROOT / "scripts" / f"{m}.py").exists()]
    assert not chet, f"script không tồn tại: {chet}"


def test_khong_gia_vo_bo_nhieu_luot_chua_chay():
    """
    Đây là ca canh đúng lỗi đã xảy ra.

    Chạy trên bản clone sạch thì `data/eval/` không có gì, và lúc đó câu
    "chưa chạy" là SỰ THẬT — nên ca này chỉ cắn khi thật sự có kết quả nằm
    đó mà tài liệu vẫn nói ngược lại.
    """
    da_chay = bool(glob.glob(str(ROOT / "data" / "eval" / "nhieu-luot-*.json")))
    if not da_chay:
        return
    thap = MD.lower()
    for cau in ("chưa chạy lần nào", "chưa có con số nào"):
        assert cau not in thap, (
            f"tài liệu nói {cau!r} nhưng data/eval/ đã có kết quả nhiều lượt"
        )


def test_khong_go_tay_diem_bo_vang():
    """
    Con số gõ tay là con số sẽ lệch — và ở đây nó lệch theo hướng nguy hiểm
    nhất: đẹp hơn sự thật. Bảng này từng ghi "51–55/56" trong khi bản sinh
    ra ghi "50–56, trung vị 54".

    Số thuộc về `thuc-nghiem.md`, nơi nó được sinh từ `data/eval/`. Ở đây
    chỉ được trỏ sang.
    """
    go_tay = re.findall(r"\b\d{1,2}\s*[-–]?\s*\d{0,2}\s*/\s*56\b", MD)
    assert not go_tay, f"điểm bộ vàng gõ tay trong văn xuôi: {go_tay}"


def test_van_tro_sang_tai_lieu_sinh_ra():
    """Bỏ số gõ tay đi mà không trỏ sang đâu thì người đọc mất luôn bằng
    chứng, và đó là bước lùi chứ không phải bước tiến."""
    assert "thuc-nghiem.md" in MD


def test_van_noi_that_ve_phan_chua_xong():
    """
    Giá trị lớn nhất của tài liệu này là mục "Còn hở, chưa làm". Ai đó dọn
    dẹp cho tài liệu "gọn hơn" mà xoá mục ấy thì nó thành tờ quảng cáo.
    """
    assert "Còn hở, chưa làm" in MD
    for muc in ("Zalo cá nhân", "chăm sóc chủ động", "Một máy"):
        assert muc in MD, f"mục cảnh báo {muc!r} đã biến mất"


def test_van_bao_nguoi_doc_kiem_bang_may():
    """Bảy việc trước khi chạy thật là văn xuôi, và văn xuôi thì người ta
    tin là mình đã làm. Lệnh kiểm phải nằm ngay trong tài liệu."""
    assert "scripts.san_sang" in MD
