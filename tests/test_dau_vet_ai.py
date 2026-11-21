"""
`agent/core/dau_vet_ai.py` — dấu vết AI của từng tin: không chứa dữ liệu cá
nhân thô, có trần kích thước, và sự kiện `cong_cu.goi` mang id hội thoại.
Thuần, không cần CSDL.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from agent.core import agent as brain
from agent.core import agent_ho_so, dau_vet_ai, tools


def _dung(reply, **them):
    kw = dict(ho_so=agent_ho_so.mac_dinh(), che_do_chung="assist",
              duyet_rieng=False, tu_gui=False)
    kw.update(them)
    return dau_vet_ai.dung(reply, **kw)


def test_che_so_dien_thoai_va_an_danh_tinh_ca_khi_tat_che_du_lieu(monkeypatch):
    """Che LUÔN, bất kể công tắc gửi model: dấu vết sống lâu hơn câu trả lời."""
    from agent.config import settings

    monkeypatch.setattr(settings, "che_du_lieu_gui_model", False)
    r = brain.Reply(
        text="x", escalate=True,
        escalate_reason="Khách để lại số 0912345678 nhờ gọi",
        cong_cu=[{"ten": "len_don", "vong": 1, "ms": 3,
                  "tham_so": {"khach_ten": "Trần Văn Bình", "khach_dia_chi": "5 Hai Bà Trưng",
                              "khach_sdt": "0912345678", "items": [{"ma": "SR01", "so_luong": 2}]},
                  "ket_qua": {"ma_don": "AS2611", "khach_email": "binh@vidu.vn",
                              "ghi_chu": "liên hệ 0987654321"}}],
    )
    dv = _dung(r)
    chu = json.dumps(dv, ensure_ascii=False)
    for pii in ("0912345678", "0987654321", "Trần Văn Bình", "Hai Bà Trưng", "binh@vidu.vn"):
        assert pii not in chu
    # Thứ CẦN đọc thì vẫn còn: mã hàng, mã đơn, số lượng.
    assert "SR01" in chu and "AS2611" in chu
    assert dv["cong_cu"][0]["tham_so"]["khach_ten"] == dau_vet_ai.AN


def test_ket_qua_khong_lo_van_vuot_tran_thi_rut_gon_ma_van_la_json(monkeypatch):
    to = {"doan": [{"noi_dung": "x" * 5000, "tai_lieu": f"tl{i}"} for i in range(40)]}
    r = brain.Reply(text="x", cong_cu=[
        {"ten": "tim_kien_thuc", "vong": i, "ms": 1, "tham_so": {"cau": "y" * 5000},
         "ket_qua": to} for i in range(20)])
    dv = _dung(r)
    assert len(json.dumps(dv, ensure_ascii=False).encode()) <= dau_vet_ai.TRAN_BYTE
    # Nói RÕ đã bỏ gì: cắt im lặng là người đọc tưởng chỉ có tám lần gọi.
    assert dv["cong_cu_bo_bot"] == 12 and dv.get("da_rut_gon")
    assert all(c["ten"] == "tim_kien_thuc" for c in dv["cong_cu"])


def test_ghi_ho_so_nguong_luoi_va_tri_thuc():
    hs = agent_ho_so.HoSo(id=str(uuid.uuid4()), ten="Tư vấn da", huong_dan="",
                          nguong_tu_tin=0.7, tran_chi_phi=0.2)
    r = brain.Reply(text="x", escalate=True, luoi_bat="bat_buoc_chuyen", confidence=0.81,
                    goi_ky_nang=["goi-da"], tri_thuc=[{"title": "Bảng giá", "version": 2,
                                                        "chunk_id": "c1", "khac": "bỏ"}])
    dv = _dung(r, ho_so=hs, che_do_chung="auto", duyet_rieng=True)
    assert dv["ho_so"] == {"id": hs.id, "ten": "Tư vấn da"}
    assert dv["tin_cay"]["nguong"] == 0.7 and dv["tin_cay"]["diem"] == 0.81
    assert dv["luoi"]["ma"] == "bat_buoc_chuyen" and dv["luoi"]["la_luoi"] is True
    assert dv["che_do"] == {"chung": "auto", "duyet_rieng": True, "tu_gui": False}
    assert dv["tri_thuc"][0]["title"] == "Bảng giá" and "khac" not in dv["tri_thuc"][0]
    assert dv["goi_ky_nang"] == ["goi-da"]
    # Mã chuyển KHÔNG phải lớp lưới thì nói đúng như vậy.
    dv2 = _dung(brain.Reply(text="x", escalate=True, luoi_bat="cong_cu_chuyen_nguoi"))
    assert dv2["luoi"]["la_luoi"] is False


def test_tri_thuc_kem_trich_doan_cat_ngan_cho_nut_xem_can_cu():
    """Người duyệt bản nháp phải đọc được CHÍNH câu tài liệu AI dựa vào."""
    from agent.core import rag

    doan = [rag.Passage(doc_title="Đổi trả", content="Đổi trong   7 ngày. " + "x" * 900,
                        score=0.71, version=4),
            rag.Passage(doc_title="Đổi trả", content="Đổi trong   7 ngày. " + "x" * 900,
                        score=0.71, version=4)]          # trùng: chỉ một
    tt = brain._tri_thuc_cho_dau_vet(doan)
    assert len(tt) == 1 and tt[0]["title"] == "Đổi trả" and tt[0]["version"] == 4
    assert tt[0]["trich"].startswith("Đổi trong 7 ngày.") and len(tt[0]["trich"]) <= 301
    dv = _dung(brain.Reply(text="x", tri_thuc=tt))
    assert dv["tri_thuc"][0]["trich"].startswith("Đổi trong 7 ngày.")
    assert dv["tri_thuc"][0]["diem"] == 0.71


def test_su_kien_cong_cu_goi_mang_id_hoi_thoai(monkeypatch):
    ghi = []

    async def log_event(kind, **kw): ghi.append(kw)
    async def that(name, args, conversation_id=None): return {"tim_thay": True}

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: None)
    cid = uuid.uuid4()
    asyncio.run(tools.run_tool("tra_cuu_san_pham", {}, cid))
    asyncio.run(tools.run_tool("tra_cuu_san_pham", {}, str(cid)))
    asyncio.run(tools.run_tool("tra_cuu_san_pham", {}, "khong-phai-uuid"))
    assert [k["ref_id"] for k in ghi] == [cid, cid, None]
