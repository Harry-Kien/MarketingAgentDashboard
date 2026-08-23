"""
Kiểm thử bộ sinh chương thực nghiệm. Không gọi API, không cần CSDL.

Con số gõ tay vào tài liệu là con số sẽ sai. Repo này đã có bằng chứng:
README từng ghi bộ vàng đạt "55/56 (98%)", tài liệu doanh nghiệp ghi
"56/56", mà chính README lại nói bốn lần chạy cho 51, 55, 52, 54.

Ba con số, ba chỗ, một sự thật. Cái sai không nằm ở phép tính — mà ở việc
một người phải NHỚ cập nhật ba chỗ mỗi lần chạy lại.

File này canh bộ sinh đọc đúng và không âm thầm bịa số.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import sinh_thuc_nghiem as stn  # noqa: E402


def test_chi_lay_lan_chay_day_du_56_ca():
    """
    `data/eval/` có cả lần chạy lọc một nhóm nhỏ. Gộp một lần chạy 11 ca
    với một lần 56 ca là so quả táo với quả cam, và điểm trung bình tụt
    xuống vì một lý do không liên quan gì tới chất lượng agent.
    """
    for _, d in stn._lan_chay_day_du():
        assert len(d["ket_qua"]) == stn.TONG_CA_VANG


def test_thieu_truong_thi_bo_qua_chu_khong_dien_khong():
    """
    Bộ eval tiến hoá theo thời gian nên lần chạy cũ thiếu vài chỉ số. Điền
    0 thay thế là BỊA RA một phép đo chưa từng thực hiện, và nó kéo thống
    kê xuống theo hướng không ai kiểm chứng được.
    """
    day = stn._lan_chay_day_du()
    if not day:
        return
    gia = [*day, ("gia-lap", {"ket_qua": [None] * stn.TONG_CA_VANG, "dat": 55,
                              "bo_sot_chuyen_nguoi": 0, "chuyen_nguoi_thua": 0,
                              "dung_tu_cam": 0, "chi_phi_usd": 0.07})]
    bang = stn._bang_mot_luot(gia)
    # Lần giả lập thiếu `cau_tra_loi_sach_sau_xu_ly` -> phải ghi rõ mẫu nhỏ
    assert "trên" in bang and "lần)" in bang


def test_bao_ca_dai_khong_bao_moi_lan_tot_nhat():
    """
    Doanh nghiệp dùng thật gặp mức SÀN, không gặp kỷ lục. Một tài liệu chỉ
    ghi kỷ lục sẽ làm người đọc thất vọng đúng vào ngày họ đo lại.
    """
    md = stn.dung()
    assert "mức sàn" in md
    assert "trung vị" in md


def test_noi_ro_gioi_han_cua_phep_do():
    """Một chương thực nghiệm không nói giới hạn thì là quảng cáo."""
    md = stn.dung()
    for y in ("Không tất định", "khớp từ khoá", "hư cấu"):
        assert y in md, y


def test_khong_gia_vo_da_chay_bo_nhieu_luot():
    """Chưa chạy thì phải nói chưa chạy, không được để trống cho người đọc
    tự hiểu là đã chạy và kết quả rỗng."""
    import inspect
    src = inspect.getsource(stn.dung)
    assert "chưa chạy" in src


def test_file_tai_lieu_da_duoc_sinh_lai():
    """Lệch nghĩa là có lần chạy mới mà quên sinh lại — đúng kiểu tài liệu
    bắt đầu nói dối."""
    ra = ROOT / "docs" / "thuc-nghiem.md"
    assert ra.exists(), "chưa chạy: python -m scripts.sinh_thuc_nghiem --ghi"
    assert ra.read_text(encoding="utf-8") == stn.dung(), \
        "docs/thuc-nghiem.md đã cũ — chạy lại: python -m scripts.sinh_thuc_nghiem --ghi"
