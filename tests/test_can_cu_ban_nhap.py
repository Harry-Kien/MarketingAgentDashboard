"""
Trạng thái căn cứ của bản nháp AI (phiếu việc mục 16, phần còn lại).

Bốn trạng thái — đủ / chưa đầy đủ / không có / mâu thuẫn — do MÁY CHỦ phân
loại từ kết quả tra cứu thật của lượt, không từ lời tự đánh giá của model.
Xanh giả ở đây (gắn "đủ căn cứ" lên câu đứng trên hai nguồn trái nhau) nguy
hơn đỏ giả: người duyệt tin nhãn và bấm gửi.

Và ràng buộc gốc "AI không được khẳng định nghiệp vụ khi thiếu căn cứ" có
lưới trong MÃ canh — test cuối tệp chạy đúng đường ấy.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from agent.core import agent as brain
from agent.core import dau_vet_ai
from agent.core.llm import LLMResult


def _reply(text="Dạ ạ", cong_cu=(), tri_thuc=(), confidence=0.9, **k):
    return SimpleNamespace(text=text, cong_cu=list(cong_cu), tri_thuc=list(tri_thuc),
                           confidence=confidence, **k)


def _cc(ten, ket_qua, tham_so=None):
    return {"ten": ten, "tham_so": tham_so or {}, "ket_qua": ket_qua}


def _pl(r, nguong=0.55):
    return dau_vet_ai.phan_loai_can_cu(r, nguong=nguong)


SP_CO = _cc("tra_cuu_san_pham", {"tim_thay": True, "ten": "Kem dưỡng ẩm Aurora", "gia": 245000},
            {"ten_san_pham": "kem dưỡng"})
TL = {"title": "Chính sách đổi trả", "trich": "Đổi trả trong 7 ngày kể từ khi nhận hàng."}


def test_du_can_cu():
    kq = _pl(_reply("Kem giá 245.000đ ạ", cong_cu=[SP_CO], tri_thuc=[TL]))
    assert kq["ma"] == "du" and kq["thieu"] == [] and kq["mau_thuan"] == []


def test_khong_co_can_cu_kem_cau_cho_trung_lap():
    kq = _pl(_reply("Dạ có ạ", cong_cu=[_cc("tim_kien_thuc", {"tim_thay": False})]))
    assert kq["ma"] == "khong_co"
    assert kq["cau_cho"] == dau_vet_ai.CAU_CHO_TRUNG_LAP
    assert "KHÔNG" in kq["huong_dan"] or "Không" in kq["huong_dan"]


@pytest.mark.parametrize("r,chua", [
    # tài liệu khớp yếu, không dữ liệu hệ thống
    (_reply("Dạ được ạ", tri_thuc=[TL], confidence=0.2), "khớp yếu"),
    # một lần tra hụt giữa các lần tra trúng
    (_reply("Dạ ạ", cong_cu=[SP_CO, _cc("tra_cuu_don_hang", {"tim_thay": False})], tri_thuc=[TL]),
     "đơn hàng"),
    # câu trả lời nói số tiền mà lượt này không tra giá
    (_reply("Bên em giá 300.000đ ạ", tri_thuc=[TL], confidence=0.9), "số tiền"),
])
def test_chua_day_du_noi_ro_thieu_gi(r, chua):
    kq = _pl(r)
    assert kq["ma"] == "chua_du"
    assert any(chua in t for t in kq["thieu"]), kq["thieu"]


def test_mau_thuan_cung_cong_cu_hai_ket_qua():
    lan2 = _cc("tra_cuu_san_pham", {"tim_thay": True, "ten": "Kem dưỡng ẩm Aurora", "gia": 199000},
               {"ten_san_pham": "kem dưỡng"})
    kq = _pl(_reply("Giá 245.000đ", cong_cu=[SP_CO, lan2], tri_thuc=[TL]))
    assert kq["ma"] == "mau_thuan" and "gia" in kq["mau_thuan"][0]
    assert "Không chọn" in kq["huong_dan"]


def test_mau_thuan_gia_danh_muc_va_tai_lieu():
    tl = {"title": "Bảng giá tháng 10", "trich": "Kem dưỡng ẩm Aurora 199.000đ — ưu đãi."}
    kq = _pl(_reply("Giá 245.000đ", cong_cu=[SP_CO], tri_thuc=[tl]))
    assert kq["ma"] == "mau_thuan" and "199.000" in kq["mau_thuan"][0]


def test_tai_lieu_cung_gia_thi_khong_mau_thuan():
    tl = {"title": "Bảng giá", "trich": "Kem dưỡng ẩm Aurora 245.000đ."}
    assert _pl(_reply("Giá 245.000đ", cong_cu=[SP_CO], tri_thuc=[tl]))["ma"] == "du"


def test_mau_thuan_trang_thai_don_giua_hai_cong_cu():
    don = _cc("tra_cuu_don_hang", {"tim_thay": True, "ma_don": "AS1", "trang_thai": "da_chot"})
    vc = _cc("tra_cuu_van_chuyen", {"tim_thay": True, "ma_don": "AS1", "trang_thai_don": "da_huy"})
    assert _pl(_reply("Đơn đang giao ạ", cong_cu=[don, vc]))["ma"] == "mau_thuan"


def test_nhan_khong_co_phan_tram():
    for nhan in dau_vet_ai.TRANG_THAI_CAN_CU.values():
        assert "%" not in nhan
    kq = _pl(_reply("x", tri_thuc=[TL], confidence=0.2))
    assert "%" not in json.dumps(kq, ensure_ascii=False)


def test_dau_vet_mang_phan_loai_va_khong_lam_vo_dau_vet_khi_hong(monkeypatch):
    r = SimpleNamespace(text="x", cong_cu=[SP_CO], tri_thuc=[TL], confidence=0.9,
                        grounded=True, luoi_bat=None, escalate=False, escalate_reason="",
                        sources=[], goi_ky_nang=[], model="m", cost_usd=0.0,
                        tokens_in=0, tokens_out=0, latency_ms=0, vong=[])
    hs = SimpleNamespace(id=None, ten="", nguong_tu_tin=0.55)
    dv = dau_vet_ai.dung(r, ho_so=hs, che_do_chung="assist", duyet_rieng=False, tu_gui=False)
    assert dv["can_cu"]["ma"] == "du"

    def hong(*a, **k):
        raise RuntimeError("lỗi phân loại")
    monkeypatch.setattr(dau_vet_ai, "phan_loai_can_cu", hong)
    dv = dau_vet_ai.dung(r, ho_so=hs, che_do_chung="assist", duyet_rieng=False, tu_gui=False)
    assert dv["can_cu"]["ma"] is None and "lỗi phân loại" in dv["can_cu"]["loi"]
    assert dv["cong_cu"], "phân loại hỏng không được làm mất cả dấu vết"


# ══ Lưới trong MÃ: thiếu căn cứ thì không tự trả lời ═══════════════════════

def test_khong_tai_lieu_khong_du_lieu_thi_luoi_tin_cay_thap_chuyen_nguoi(monkeypatch):
    """
    Model trả lời trơn tru một câu nghiệp vụ ("được đổi trong 30 ngày") mà
    không có đoạn tài liệu nào, không công cụ nào trả dữ liệu. Lưới ③ phải
    chuyển người — và tin bị chuyển người không bao giờ tự gửi cho khách
    (xu_ly_tin_vao: `auto_send` đòi `not reply.escalate`).
    """
    async def fetchrow(sql, *a):
        return {"cost_usd": 0.0}

    async def con_ngan_sach():
        return True, 0.0, 0.0

    async def retrieve(q, k=5, **kw):
        return []

    async def cong_cu_dang_bat(tat_ca):
        return tat_ca

    async def complete(**kw):
        return LLMResult(text="Dạ bên em được đổi trả trong 30 ngày ạ.", model="m",
                         cost_usd=0.0, stop_reason="STOP")

    async def log_event(*a, **k):
        return None

    monkeypatch.setattr(brain.db, "fetchrow", fetchrow)
    monkeypatch.setattr(brain.db, "log_event", log_event)
    monkeypatch.setattr(brain.ngan_sach, "con_ngan_sach", con_ngan_sach)
    monkeypatch.setattr(brain.ngan_sach, "ghi_nhan", lambda c: None)
    monkeypatch.setattr(brain.rag, "retrieve", retrieve)
    monkeypatch.setattr(brain.rag, "as_context", lambda p: "")
    monkeypatch.setattr(brain.kho_ky_nang, "cong_cu_dang_bat", cong_cu_dang_bat)
    monkeypatch.setattr(brain.llm, "complete", complete)

    r = asyncio.run(brain.respond(conversation_id=uuid.uuid4(), history=[],
                                  question="hàng mua rồi đổi trả được bao lâu?"))
    assert r.escalate is True and r.luoi_bat == "tin_cay_thap"
    assert r.grounded is False
    assert dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)["ma"] == "khong_co"


def test_tin_chuyen_nguoi_khong_bao_gio_tu_gui():
    import inspect

    from agent.omnichannel import xu_ly_tin_vao

    nguon = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    assert 'auto_send = (che_do_chung == "auto" and not reply.escalate' in nguon
