"""
Che SĐT / email / CCCD trước khi gửi model ở nước ngoài, đổi lại khi gọi
công cụ và khi trả lời khách (agent/core/che_du_lieu.py).

Ba chiều phải canh cùng lúc:
  · thứ GỬI ĐI không còn số thật (giảm dữ liệu ra nước ngoài);
  · công cụ NHẬN số thật (lên đơn mà nhận "[SĐT_1]" là đơn hỏng);
  · khách NHẬN số thật (thấy "[SĐT_1]" là lỗi lộ ra);
và không che nhầm mã đơn, mã vận đơn, giá tiền.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from agent.core import agent as brain
from agent.core.che_du_lieu import MatNa
from agent.core.llm import LLMResult


@pytest.mark.parametrize("vao,ra", [
    ("số em 0912 345 678 nha", "số em [SĐT_1] nha"),
    ("+84912345678", "[SĐT_1]"),
    ("84 912 345 678", "[SĐT_1]"),
    ("bàn 028 3823 4567", "bàn [SĐT_1]"),
    ("mail Lan.Nguyen@Gmail.com ạ", "mail [EMAIL_1] ạ"),
    ("CCCD 001203004567", "CCCD [CCCD_1]"),
])
def test_che(vao, ra):
    assert MatNa().che(vao) == ra


@pytest.mark.parametrize("giu", [
    "mã đơn AS260819235000", "vận đơn S1.A1.2001297581", "giá 150.000đ", "giá 1.290.000 đồng",
    "ngày 05/11/2026", "lọ 50ml", "SKU SR0912345678", "mã giảm GIAM0912345678",
])
def test_khong_che_nham(giu):
    assert MatNa().che(giu) == giu


def test_cung_so_cung_ma_khac_so_khac_ma():
    m = MatNa()
    assert m.che("0912 345 678") == m.che("+84912345678") == "[SĐT_1]"
    assert m.che("0987654321") == "[SĐT_2]"


@pytest.mark.parametrize("model_viet", ["[SĐT_1]", "SĐT_1", "[SDT 1]", "[ sđt_1 ]", "sdt_1"])
def test_mo_chiu_model_viet_lech(model_viet):
    m = MatNa()
    m.che("0912345678")
    assert m.mo(f"số {model_viet} đúng không ạ") == "số 0912345678 đúng không ạ"


def test_ma_bia_khong_doi_va_bi_phat_hien():
    m = MatNa()
    m.che("0912345678")
    assert m.mo("[SĐT_7]") == "[SĐT_7]"
    assert m.ma_con_sot("số [SĐT_1] và [SĐT_7]") == ["[SĐT_7]"]


# ------------------------------------------------------------------ trọn respond()

@pytest.fixture
def san(monkeypatch):
    hop: dict = {"gui": [], "cong_cu": []}

    async def fetchrow(sql, *a): return {"cost_usd": 0.0}
    async def con_ngan_sach(): return True, 0.0, 0.0
    async def retrieve(q, k=5): return []
    async def cong_cu_dang_bat(tat_ca): return tat_ca
    async def log_event(kind, **k): hop.setdefault("su_kien", []).append(kind)

    lan = {"n": 0}

    async def complete(**kw):
        hop["gui"].append(json.dumps({"system": kw["system"], "messages": kw["messages"]},
                                     ensure_ascii=False, default=str))
        lan["n"] += 1
        if lan["n"] == 1:
            return LLMResult(text="", model="m", tool_calls=[{
                "id": "c1", "name": "tra_cuu_don", "input": {"so_dien_thoai": "[SĐT_1]"}}])
        return LLMResult(text="Dạ đơn của số [SĐT_1] đang giao, mail [EMAIL_1] em đã ghi nhận ạ.",
                         model="m")

    async def run_tool(name, args, conversation_id=None):
        hop["cong_cu"].append(args)
        return {"tim_thay": True, "don": [{"ma_don": "AS260819235000", "khach_sdt": "0912345678",
                                           "trang_thai": "dang_giao"}]}

    monkeypatch.setattr(brain.db, "fetchrow", fetchrow)
    monkeypatch.setattr(brain.db, "log_event", log_event)
    monkeypatch.setattr(brain.ngan_sach, "con_ngan_sach", con_ngan_sach)
    monkeypatch.setattr(brain.ngan_sach, "ghi_nhan", lambda c: None)
    monkeypatch.setattr(brain.rag, "retrieve", retrieve)
    monkeypatch.setattr(brain.rag, "as_context", lambda p: "NGU CANH")
    monkeypatch.setattr(brain.kho_ky_nang, "cong_cu_dang_bat", cong_cu_dang_bat)
    monkeypatch.setattr(brain.llm, "complete", complete)
    monkeypatch.setattr(brain.tools, "run_tool", run_tool)
    return hop


def test_tron_luot_khong_gui_so_that_ma_van_dung_so_that(san):
    r = asyncio.run(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[{"role": "user", "content": "lần trước em để số 0912 345 678"}],
        question="đơn của em tới đâu rồi, mail em là lan@gmail.com"))
    gui = "\n".join(san["gui"])
    for that in ("0912345678", "0912 345 678", "lan@gmail.com"):
        assert that not in gui, f"{that} bị gửi sang model"
    assert "[SĐT_1]" in gui and "LƯU Ý HỆ THỐNG" in gui
    # Kết quả công cụ đi ngược về model cũng phải che.
    assert "AS260819235000" in gui                       # mã đơn KHÔNG bị che
    assert san["cong_cu"] == [{"so_dien_thoai": "0912345678"}]
    assert r.text == "Dạ đơn của số 0912345678 đang giao, mail lan@gmail.com em đã ghi nhận ạ."
    assert r.cong_cu[0]["tham_so"] == {"so_dien_thoai": "0912345678"}


def test_tat_thi_gui_nguyen_van(san, monkeypatch):
    monkeypatch.setattr(brain.settings, "che_du_lieu_gui_model", False)
    asyncio.run(brain.respond(conversation_id=uuid.uuid4(), history=[], question="số em 0912345678"))
    assert "0912345678" in san["gui"][0] and "LƯU Ý HỆ THỐNG" not in san["gui"][0]


def test_khong_co_gi_de_che_thi_khong_them_ghi_chu(san):
    asyncio.run(brain.respond(conversation_id=uuid.uuid4(), history=[], question="kem này giá bao nhiêu"))
    assert "LƯU Ý HỆ THỐNG" not in san["gui"][0]


def test_mac_dinh_bat():
    from agent.config import Settings

    assert Settings.model_fields["che_du_lieu_gui_model"].default is True


def test_ho_so_khai_dung_pham_vi_che(monkeypatch):
    from scripts import sinh_ho_so_bvdlcn as h

    monkeypatch.setattr(h.settings, "che_du_lieu_gui_model", True)
    t = h.sinh()
    assert "số điện thoại, email, số CCCD được thay bằng mã" in t
    assert "tên, địa chỉ, nội dung tin và ảnh vẫn gửi nguyên văn" in t
    monkeypatch.setattr(h.settings, "che_du_lieu_gui_model", False)
    assert "chưa che" in h.sinh()


def test_chi_agent_gui_chu_khach_sang_model():
    """Đường mới gọi model bằng chữ khách mà không qua MatNa là lỗ thủng — test này nổ để người thêm phải nghĩ."""
    import re
    from pathlib import Path

    goc = Path(__file__).resolve().parent.parent / "agent"
    goi = sorted(str(p.relative_to(goc)).replace("\\", "/") for p in goc.rglob("*.py")
                 if p.name != "llm.py" and re.search(r"llm\.complete\(", p.read_text(encoding="utf-8")))
    assert goi == ["core/agent.py", "publish/copywriter.py", "video/pipeline.py", "video/vision.py"], goi
