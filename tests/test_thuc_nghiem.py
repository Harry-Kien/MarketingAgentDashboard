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

import pytest  # noqa: E402

from scripts import sinh_thuc_nghiem as stn  # noqa: E402

# `data/eval/ket-qua-*.json` là dữ liệu VẬN HÀNH, bị .gitignore chặn — máy
# vừa clone repo không có file nào.
#
# Hai test dưới kiểm NỘI DUNG tài liệu sinh ra từ dữ liệu đó. Không có dữ
# liệu thì chúng không kiểm được gì: bắt chúng đỏ là CI đỏ trên mọi máy mới
# vì một lý do không phải lỗi, và người ta sẽ ngừng đọc CI.
#
# Bỏ qua CÓ ĐIỀU KIỆN, không nới lỏng phép kiểm. Trên máy đã chạy eval —
# tức là máy của người thật sự sửa tài liệu này — chúng vẫn chạy đủ.
CAN_DU_LIEU = pytest.mark.skipif(
    not stn._lan_chay_day_du(),
    reason="chưa chạy eval trên máy này (data/eval/ không đi theo repo)",
)


def test_chi_lay_lan_chay_day_du():
    """
    `data/eval/` có cả lần chạy lọc một nhóm nhỏ. Gộp một lần chạy 11 ca
    với một lần chạy đủ bộ là so quả táo với quả cam, và điểm trung bình
    tụt xuống vì một lý do không liên quan gì tới chất lượng agent.
    """
    for _, d in stn._lan_chay_day_du():
        if d.get("meta"):
            assert d["meta"].get("nhom") is None
        else:
            assert len(d["ket_qua"]) == stn.TONG_CA_CU


def test_thieu_truong_thi_bo_qua_chu_khong_dien_khong():
    """
    Bộ eval tiến hoá theo thời gian nên lần chạy cũ thiếu vài chỉ số. Điền
    0 thay thế là BỊA RA một phép đo chưa từng thực hiện, và nó kéo thống
    kê xuống theo hướng không ai kiểm chứng được.
    """
    day = stn._lan_chay_day_du()
    if not day:
        return
    gia = [*day, ("gia-lap", {"ket_qua": [None] * stn.TONG_CA_CU, "dat": 55,
                              "bo_sot_chuyen_nguoi": 0, "chuyen_nguoi_thua": 0,
                              "dung_tu_cam": 0, "chi_phi_usd": 0.07})]
    bang = stn._bang_mot_luot(gia)
    # Lần giả lập thiếu `cau_tra_loi_sach_sau_xu_ly` -> phải ghi rõ mẫu nhỏ
    assert "trên" in bang and "lần)" in bang


@CAN_DU_LIEU
def test_tach_lich_su_khoi_so_do_lap_lai():
    """
    Lần chạy không có `meta` là các PHIÊN BẢN khác nhau, không phải các lần
    lặp. Báo chúng như số đo là đúng lỗi phản biện bắt được ở đợt rà
    14.10.2026: trung vị của bốn hệ thống khác nhau gọi là một con số.
    """
    md = stn.dung()
    assert "Wilson" in md
    assert "không dùng để kết luận" in md
    assert "mức sàn" not in md


def test_wilson_dung_so_sach():
    lo, hi = stn.wilson(0, 56)
    assert lo == 0.0 and 0.06 < hi < 0.07          # 0/56 → cận trên ≈ 6,4%
    lo, hi = stn.wilson(28, 56)
    assert 0.37 < lo < 0.38 and 0.62 < hi < 0.63
    assert stn.wilson(0, 0) == (0.0, 0.0)


def test_nhom_lan_chay_theo_cau_hinh():
    a = {"meta": {"commit": "x", "luoi_tat": []}}
    b = {"meta": {"commit": "x", "luoi_tat": ["injection"]}}
    c = {}                                          # lần chạy cũ, chưa có meta
    g = stn.nhom_theo_cau_hinh([("a", a), ("b", b), ("c", c)])
    assert set(g) == {("x", ()), ("x", ("injection",)), ("?", ())}


def test_ma_sua_do_khong_thanh_so_do_chinh_thuc():
    """Commit không mô tả đúng mã đã chạy khi agent/ có sửa chưa commit."""
    def lan(commit, sua):
        return {"meta": {"commit": commit, "luoi_tat": [], "ban_sua_do": sua},
                "ket_qua": []}
    g = stn.nhom_theo_cau_hinh([("1", lan("a", True)), ("2", lan("a", True)),
                                ("3", lan("b", False))])
    assert stn._commit_chinh(g) == "b"


def test_bang_bo_sot_doc_tu_file_khong_go_tay():
    src = (ROOT / "scripts" / "sinh_thuc_nghiem.py").read_text(encoding="utf-8")
    assert "TUAN_THU_14" not in src and "G38" not in src
    gia = [("lan-1", {"ket_qua": [
        {"id": "CA_A", "hoi": "hỏi | có gạch", "tra_loi": "đáp\nxuống dòng",
         "chuyen_nguoi": True, "chuyen_nguoi_thuc": False},
        {"id": "CA_B", "hoi": "x", "tra_loi": "y",
         "chuyen_nguoi": True, "chuyen_nguoi_thuc": True},
    ]})]
    bang = stn._bang_bo_sot(gia)
    assert "`CA_A`" in bang and "CA_B" not in bang
    assert "\n" not in bang.split("`CA_A`")[1].split("|")[2], "xuống dòng phá bảng"


def test_so_ca_va_kich_ban_dem_tu_file():
    """Bộ vàng hiện có 54 ca; tài liệu từng ghi "56" ở chín chỗ."""
    src = (ROOT / "scripts" / "sinh_thuc_nghiem.py").read_text(encoding="utf-8")
    assert "Bộ 56" not in src and "12 kịch bản" not in src and "dưới 2 giây" not in src
    assert stn._so_ca_bo_vang() > 0
    so_kb, so_luot = stn._dem_kich_ban()
    assert so_kb > 0 and so_luot >= so_kb


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


@CAN_DU_LIEU
def test_file_tai_lieu_da_duoc_sinh_lai():
    """Lệch nghĩa là có lần chạy mới mà quên sinh lại — đúng kiểu tài liệu
    bắt đầu nói dối."""
    ra = ROOT / "docs" / "thuc-nghiem.md"
    assert ra.exists(), "chưa chạy: python -m scripts.sinh_thuc_nghiem --ghi"
    assert ra.read_text(encoding="utf-8") == stn.dung(), \
        "docs/thuc-nghiem.md đã cũ — chạy lại: python -m scripts.sinh_thuc_nghiem --ghi"


def test_khong_co_du_lieu_thi_noi_ro_chua_chay(monkeypatch):
    """
    Máy vừa clone repo phải sinh được tài liệu, và tài liệu phải NÓI RÕ là
    chưa có số — không được để trống cho người đọc tưởng đã đo và kết quả
    rỗng.

    Bản trước ném `ValueError: min() iterable argument is empty` — bộ sinh
    chết trên MỌI máy mới. Đây là lần thứ hai cùng một lỗi trong repo này:
    giả định dữ liệu không đi theo repo vẫn có mặt.
    """
    monkeypatch.setattr(stn, "_lan_chay_day_du", list)
    md = stn.dung()
    assert "Chưa chạy lần nào" in md
