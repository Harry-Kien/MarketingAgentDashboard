"""
Kiểm thử bộ kịch bản nhiều lượt. Không gọi API, không cần CSDL.

Bộ đo cũng là mã, và mã nào cũng hỏng được. Một bộ đo hỏng thì tệ hơn không
có bộ đo: nó in ra con số đẹp và làm người ta tin nhầm rằng agent đang tốt.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import eval_nhieu_luot as ev  # noqa: E402

# Đọc qua `ev.KICH_BAN` chứ không tự dựng đường dẫn: bản thật không lên
# repo, nên trên CI chỉ có bản mẫu. Tự dựng đường dẫn ở đây là test đỏ trên
# mọi máy vừa clone — và một bộ test không chạy được sau khi clone thì
# không canh được gì.
KB = [
    json.loads(l)
    for l in ev.KICH_BAN.read_text(encoding="utf-8").splitlines()
    if l.strip()
]


# =====================================================================
#  Bộ kịch bản
# =====================================================================

def test_co_kich_ban_va_doc_duoc():
    assert len(KB) >= 10


def test_moi_kich_ban_du_khoa_bat_buoc():
    for k in KB:
        for khoa in ("id", "nhom", "mo_ta", "luot"):
            assert khoa in k, (k.get("id"), khoa)


def test_id_khong_trung():
    ids = [k["id"] for k in KB]
    assert len(ids) == len(set(ids))


def test_moi_kich_ban_phai_nhieu_hon_mot_luot():
    """
    Một lượt thì đã có bộ 56 câu vàng lo. Kịch bản một lượt lọt vào đây là
    tốn tiền API để đo lại thứ đã đo rồi.
    """
    for k in KB:
        assert len(k["luot"]) >= 2, k["id"]


def test_moi_luot_deu_co_loi_khach():
    for k in KB:
        for i, l in enumerate(k["luot"]):
            assert l.get("khach", "").strip(), (k["id"], i)


def test_co_ca_tuan_thu_xuat_hien_o_luot_sau():
    """
    Đây là lý do quan trọng nhất khiến bộ này tồn tại: bộ vàng chỉ hỏi ở
    lượt đầu, nên nó mù hoàn toàn với chuyện khách nói "em đang bầu" ở lượt
    thứ tư. Mất ca đó là mất chính điều bộ này sinh ra để đo.
    """
    co = [
        k for k in KB
        if any(l.get("chuyen_nguoi") for l in k["luot"][1:])
    ]
    assert co, "không có kịch bản nào bắt buộc chuyển người ở lượt sau lượt đầu"


def test_co_ca_do_tri_nho():
    assert any(k["nhom"] == "tri_nho_trong_hoi_thoai" for k in KB)


# =====================================================================
#  Bộ chạy
# =====================================================================

def _chay_kho(kb: dict) -> dict:
    return asyncio.run(ev.chay_kich_ban(kb, None, kho=True))


def test_chay_kho_khong_goi_model_va_khong_can_csdl():
    """Chế độ khô phải chạy được trên máy chưa dựng Postgres."""
    kq = _chay_kho(KB[0])
    assert kq["id"] == KB[0]["id"]
    assert len(kq["luot"]) == len(KB[0]["luot"])
    assert kq["chi_phi"] == 0.0


def test_moi_kich_ban_chay_kho_deu_khong_no():
    for k in KB:
        _chay_kho(k)


def test_history_xen_ke_user_assistant():
    """
    History phải dựng ĐÚNG như `agent/main.py:_history()` — user/assistant
    xen kẽ, lượt đầu là user. Dựng khác đi thì bộ đo không còn đo cái đang
    chạy thật, và mọi con số nó in ra đều nói về một hệ thống khác.
    """
    src = inspect.getsource(ev.chay_kich_ban)
    i_user = src.index('"role": "user"')
    i_asst = src.index('"role": "assistant"')
    assert i_user < i_asst, "phải nối lượt khách trước lượt agent"


def test_truyen_customer_ref_de_bat_tri_nho():
    """
    Khác biệt cốt lõi với bộ vàng. Bỏ `customer_ref` đi thì `ho_so_khach`
    tắt, và bộ này quay về đo đúng thứ bộ vàng đã đo.
    """
    src = inspect.getsource(ev.chay_kich_ban)
    assert "customer_ref=ref" in src


def test_dung_kich_ban_khi_da_chuyen_nguoi_dung_y_muon():
    """
    Chuyển người xong là hội thoại sang tay người thật. Chạy tiếp là đo một
    thứ không tồn tại ngoài đời.
    """
    src = inspect.getsource(ev.chay_kich_ban)
    assert "if r.escalate and mong:" in src
    assert "break" in src.split("if r.escalate and mong:")[1][:40]


def test_cham_ca_hoi_thoai_chu_khong_chi_tung_luot():
    kq = _chay_kho(KB[0])
    assert "hoi_thoai" in kq
    for khoa in ("chao_lai", "hoi_lai_da_biet", "hoi_don_dap", "hoi_thoai_chet"):
        assert khoa in kq["hoi_thoai"], khoa
