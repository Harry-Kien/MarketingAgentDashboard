"""
"Duyệt trước khi gửi" của RIÊNG hội thoại, và người duyệt bản nháp AI.

Rà soát 20.11.2026: luật gửi chỉ xét chế độ CHUNG, nên khi chế độ chung là
Tự động thì lựa chọn "Duyệt trước khi gửi" nhân viên đặt cho một hội thoại bị
bỏ qua — AI vẫn gửi thẳng. Và bấm "Duyệt và gửi" không sửa chữ nào thì không
ghi ai đã duyệt. Xem migration 0052.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.test_gui_tin_va_dieu_phoi import (  # noqa: E402
    _hoi_thoai_cua, _kenh_agent_bat, _khach, _mot, _nhieu, _tin,
)
from tests.test_nghiem_thu_saas import _khach_nhan, _kenh_webchat, _quan_tri_vao  # noqa: E402


def _tra_loi_ai(monkeypatch):
    from agent.core import agent as brain

    async def tra_loi(**kw):
        return brain.Reply(text="Dạ kem này giá 250.000đ ạ", cost_usd=0.001)
    monkeypatch.setattr(brain, "respond", tra_loi)


def _dat_che_do(qt, cid, che_do):
    v = _mot(qt.khach, "SELECT version FROM conversations WHERE id = $1::uuid", cid)["version"]
    r = qt.post(f"/api/inbox/conversations/{cid}/che-do",
                json={"che_do": che_do, "expected_version": v, "reason": "kiểm duyệt riêng"})
    assert r.status_code == 200, r.text


def test_co_rieng_cua_hoi_thoai_thang_che_do_chung_tu_dong(app_that, monkeypatch):
    _tra_loi_ai(monkeypatch)
    qt, tk = _kenh_agent_bat(app_that, monkeypatch)      # chế độ CHUNG = auto
    gui = _khach(app_that, tk, "Chị Mai")                # một khách, một hội thoại
    gui("alo shop")
    cid = _hoi_thoai_cua(app_that, tk)
    _dat_che_do(qt, cid, "assist")
    assert _mot(app_that, "SELECT duyet_truoc_khi_gui d FROM conversations WHERE id = $1::uuid",
                cid)["d"] is True

    _mot(app_that, "DELETE FROM messages WHERE conversation_id = $1::uuid AND role = 'agent' "
                   "RETURNING 1", cid)
    gui("kem chống nắng giá bao nhiêu?")
    sau = _mot(app_that, "SELECT count(*) FILTER (WHERE delivery_status = 'draft') nhap, "
                         "count(*) FILTER (WHERE delivery_status IN ('queued','sending','sent')) gui "
                         "FROM messages WHERE conversation_id = $1::uuid AND role = 'agent' "
                         "AND content LIKE '%250.000%'", cid)
    tat_ca = [dict(r) for r in _nhieu(app_that, "SELECT role, delivery_status, left(content, 40) c "
                                    "FROM messages WHERE conversation_id = $1::uuid ORDER BY created_at", cid)]
    assert sau["nhap"] >= 1 and sau["gui"] == 0, f"nhân viên bắt duyệt mà AI vẫn gửi thẳng: {tat_ca}"


def test_che_do_chung_tu_dong_van_tu_gui_khi_khong_co_co(app_that, monkeypatch):
    """Không được 'khoá nhầm': hội thoại máy tự để `mode=assist` vẫn tự gửi khi bật auto."""
    _tra_loi_ai(monkeypatch)
    _, tk = _kenh_agent_bat(app_that, monkeypatch)
    gui = _khach(app_that, tk, "Chị Lan")
    gui("alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _mot(app_that, "UPDATE conversations SET mode = 'assist', status = 'assist' "
                   "WHERE id = $1::uuid RETURNING 1", cid)
    _mot(app_that, "DELETE FROM messages WHERE conversation_id = $1::uuid AND role = 'agent' "
                   "RETURNING 1", cid)
    gui("kem chống nắng giá bao nhiêu?")
    assert _mot(app_that, "SELECT count(*) n FROM messages WHERE conversation_id = $1::uuid "
                          "AND role = 'agent' AND content LIKE '%250.000%' "
                          "AND delivery_status <> 'draft'", cid)["n"] >= 1


def test_tra_ve_tu_dong_hoac_ket_thuc_tiep_quan_go_co(app_that, monkeypatch):
    _tra_loi_ai(monkeypatch)
    qt, tk = _kenh_agent_bat(app_that, monkeypatch)
    _khach_nhan(app_that, tk, "Chị Hà", "alo")
    cid = _hoi_thoai_cua(app_that, tk)
    _dat_che_do(qt, cid, "assist")
    _dat_che_do(qt, cid, "auto")
    assert _mot(app_that, "SELECT duyet_truoc_khi_gui d FROM conversations WHERE id = $1::uuid",
                cid)["d"] is False


def test_duyet_khong_sua_van_ghi_nguoi_duyet(app_that):
    qt = _quan_tri_vao(app_that, ten="nguoiduyet")
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)
    nhap = _tin(app_that, cid, "agent", "draft")
    assert qt.post(f"/api/messages/{nhap}/approve").status_code == 200
    d = _mot(app_that, "SELECT m.duyet_luc, nd.ten_dang_nhap FROM messages m "
                       "JOIN nguoi_dung nd ON nd.id = m.duyet_boi WHERE m.id = $1::uuid", nhap)
    assert d and d["ten_dang_nhap"] == "nguoiduyet" and d["duyet_luc"] is not None
    assert _mot(app_that, "SELECT count(*) n FROM events WHERE kind = 'tin_nhan.duyet' "
                          "AND ref_id = $1::uuid", nhap)["n"] == 1
