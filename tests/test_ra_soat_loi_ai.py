"""
Canh mười lỗ của lõi AI tìm ra khi rà soát 16.11.2026.

Mỗi lỗ đều là kiểu HỎNG IM LẶNG: câu y tế đi lọt lưới vì khách gõ không dấu,
câu chẩn đoán rào đón lọt lưới đầu ra, công cụ tra hụt vẫn nâng độ tin cậy,
lượt agent ném lỗi không ai được giao việc, chi phí suy nghĩ của Gemini
không vào sổ, model bị chặn vì an toàn mà khách nhận câu chung chung… Không
lỗi nào nổ. Test ở đây dùng ĐÚNG câu chữ đã lọt, để lần dọn dẹp sau không
âm thầm mở lại.

Không gọi API model, không cần Postgres.
"""
from __future__ import annotations

import asyncio
import json
import threading
import unicodedata
import uuid
from types import SimpleNamespace

import httpx
import pytest

from agent.core import agent as brain
from agent.core import llm, tools
from agent.core.che_du_lieu import MatNa
from agent.core.llm import LLMResult
from agent.omnichannel import thong_bao_ai as tb


def chay(coro):
    return asyncio.run(coro)


# ══ 1 · `_bat_buoc_chuyen`: không dấu, NFD, từ còn thiếu ══════════════════

@pytest.mark.parametrize("cau", [
    "em dang co bau dung retinol duoc khong",
    unicodedata.normalize("NFD", "em đang có bầu dùng retinol được không"),
    unicodedata.normalize("NFD", "da em bị dị ứng"),
    "em có thai 2 tháng dùng serum này được không",
    "em đang trong thai kỳ thì dùng được không",
    "da em bị vảy nến",
    "bác sỹ kê cho em thuốc bôi, dùng chung được không",
    "em đang uống roaccutane",
    "da bị mề đay mấy hôm nay",
    "da em bi di ung",
    "em dang cho con bu",
    "da em bi viem da co dia",
    "bac sy bao em dung",
    "em co thai thi dung duoc khong",
    "em mang bau 3 thang",
    "em có bau",                       # gõ THIẾU dấu cũng phải khớp
    "em dang c" + chr(0x200B) + "o bau",   # ký tự vô hình không cắt được cụm
])
def test_bat_buoc_chuyen_bat_bien_the_tung_lot(cau):
    assert brain._bat_buoc_chuyen(cau), cau


@pytest.mark.parametrize("cau", [
    "chăm sóc da dầu thế nào ạ",
    "nam giới dùng được không",
    "cham soc da dau the nao",
    "shop có thái độ tốt quá",
    "shop co thai do tot qua",          # "có thái độ" gõ không dấu
    "mặt nạ này có thải độc không",
    "mat na co thai doc khong",
    "kem này hết hạn chưa",
    "kem nay het han chua",             # "hết hạn", không phải "hết hẳn"
    "kem này có độ rất mỏng",
    "giá bao nhiêu ạ",
])
def test_bat_buoc_chuyen_khong_chan_nham(cau):
    assert brain._bat_buoc_chuyen(cau) is None, cau


def test_danh_sach_bo_dau_khong_chua_tu_mot_am_tiet_mo_ho():
    """
    "nám"→"nam" khớp "nam giới", "chàm"→"cham" khớp "chăm sóc": cụm một âm
    tiết bỏ dấu là chặn nhầm hàng loạt. Danh sách bỏ dấu chỉ nhận cụm nhiều
    âm tiết.
    """
    don = [c for c in brain._BUOC_CHUYEN_BO_DAU if len(c.split()) < 2]
    assert not don, f"cụm một âm tiết trong danh sách bỏ dấu: {don}"


# ══ 2 · `_chan_doan_y_te`: câu rào đón ════════════════════════════════════

@pytest.mark.parametrize("cau", [
    "Đây có thể là mụn nội tiết ạ",
    "Đó là nám mạch máu chị nhé",
    "Mấy nốt này là mụn viêm ạ",
    "Nhìn vậy thì nhiều khả năng là viêm da tiếp xúc ạ",
    "Vết đỏ trên má là dấu hiệu của rosacea",
    unicodedata.normalize("NFD", "Đây có thể là mụn nội tiết ạ"),
])
def test_chan_doan_rao_don_bi_bat(cau):
    assert brain._chan_doan_y_te(cau), cau


@pytest.mark.parametrize("cau", [
    "Sản phẩm này là kem chống nắng ạ",
    "Khi có dấu hiệu dị ứng thì chị ngưng dùng ngay nhé",
    "Bên em đổi trả nếu khách bị dị ứng trong 7 ngày ạ",
    "Dạ serum này có thể là lựa chọn hợp với da dầu ạ",
])
def test_chan_doan_khong_chan_nham(cau):
    assert brain._chan_doan_y_te(cau) is None, cau


# ══ respond() với phụ thuộc giả ══════════════════════════════════════════

@pytest.fixture
def san(monkeypatch):
    hop: dict = {"kich_ban": [], "goi_tool": [], "ngan_sach": [], "gui": [],
                 "su_kien": [], "ket_qua": None, "kw": []}

    async def fetchrow(sql, *a):
        return {"cost_usd": 0.0}

    async def con_ngan_sach():
        return True, 0.0, 0.0

    async def retrieve(q, k=5):
        return []

    async def cong_cu_dang_bat(tat_ca):
        return tat_ca

    async def log_event(kind, **k):
        hop["su_kien"].append((kind, k))

    async def complete(**kw):
        hop["kw"].append(kw)
        hop["gui"].append(json.dumps(kw["messages"], ensure_ascii=False, default=str))
        buoc = hop["kich_ban"].pop(0)
        if isinstance(buoc, BaseException):
            raise buoc
        return buoc

    async def run_tool(name, args, conversation_id=None):
        hop["goi_tool"].append((name, args))
        kq = hop["ket_qua"]
        if isinstance(kq, BaseException):
            raise kq
        return kq

    monkeypatch.setattr(brain.db, "fetchrow", fetchrow)
    monkeypatch.setattr(brain.db, "log_event", log_event)
    monkeypatch.setattr(brain.ngan_sach, "con_ngan_sach", con_ngan_sach)
    monkeypatch.setattr(brain.ngan_sach, "ghi_nhan", lambda c: hop["ngan_sach"].append(c))
    monkeypatch.setattr(brain.rag, "retrieve", retrieve)
    monkeypatch.setattr(brain.rag, "as_context", lambda p: "")
    monkeypatch.setattr(brain.kho_ky_nang, "cong_cu_dang_bat", cong_cu_dang_bat)
    monkeypatch.setattr(brain.llm, "complete", complete)
    monkeypatch.setattr(brain.tools, "run_tool", run_tool)
    return hop


def _goi(ten, args, cost=0.01):
    return LLMResult(text="", model="m", cost_usd=cost,
                     tool_calls=[{"id": "c1", "name": ten, "input": args}])


def _chot(text, stop="STOP", cost=0.02):
    return LLMResult(text=text, model="m", cost_usd=cost, stop_reason=stop)


# ══ 3 · co_du_lieu theo KẾT QUẢ, không theo tên ══════════════════════════

@pytest.mark.parametrize("ten,ket_qua", [
    ("tra_cuu_san_pham", {"tim_thay": False, "ghi_chu": "không có"}),
    ("goi_y_san_pham", {"so_luong": 0, "san_pham": []}),
    ("tra_cuu_san_pham", {"loi": "CSDL hỏng"}),
])
def test_cong_cu_tra_hut_khong_nang_do_tin_cay(san, ten, ket_qua):
    san["ket_qua"] = ket_qua
    san["kich_ban"] = [_goi(ten, {"ten": "x"}), _chot("Dạ có ạ, giá tốt lắm.")]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="kem x giá sao?"))
    assert r.escalate and r.luoi_bat == "tin_cay_thap", (ten, ket_qua)
    assert r.grounded is False


def test_cong_cu_co_du_lieu_van_duoc_tin(san):
    san["ket_qua"] = {"tim_thay": True, "ma": "AS-CL01", "gia": 245000}
    san["kich_ban"] = [_goi("tra_cuu_san_pham", {"ten": "x"}), _chot("Dạ giá 245.000đ ạ.")]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="giá kem x?"))
    assert not r.escalate and r.confidence >= 0.8


def test_plugin_tra_tai_lieu_doi_xu_nhu_tim_kien_thuc(san, monkeypatch):
    """
    Ba chỗ: tham số KHÔNG mở che (SĐT thật không ra API embedding), kết quả
    KHÔNG bị che (hotline của shop giữ nguyên), đoạn tìm được VÀO `sources`.
    """
    monkeypatch.setattr(brain.settings, "che_du_lieu_gui_model", True)
    monkeypatch.setattr(brain.tools, "_loai_cua",
                        lambda n: "tra_tai_lieu" if n == "tra_chinh_sach" else None)
    san["ket_qua"] = {"tim_thay": True, "doan": [{
        "tai_lieu": "Chính sách đổi trả", "noi_dung": "Gọi hotline 0281234567 để đổi trả.",
        "diem": 0.9}]}
    san["kich_ban"] = [_goi("tra_chinh_sach", {"cau_hoi": "đổi trả cho số [SĐT_1]"}),
                       _chot("Dạ chị gọi hotline 0281234567 giúp em ạ.")]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[],
                           question="số em 0912345678, đổi trả thế nào"))
    assert san["goi_tool"] == [("tra_chinh_sach", {"cau_hoi": "đổi trả cho số [SĐT_1]"})]
    assert "0281234567" in san["gui"][1], "tài liệu của shop bị che như dữ liệu khách"
    assert "0912345678" not in "".join(san["gui"])
    assert "Chính sách đổi trả" in r.sources
    assert not r.escalate


# ══ 6 · công cụ dặn "chuyển nhân viên" phải đặt CỜ ════════════════════════

def test_tra_van_chuyen_csdl_chet_dat_co(monkeypatch):
    async def hong(*a, **k):
        raise RuntimeError("CSDL sập")

    monkeypatch.setattr(tools.db, "fetchrow", hong)
    kq = chay(tools._tra_cuu_van_chuyen({"ma_don": "AS1"}))
    assert kq["can_chuyen_nhan_vien"] is True


def test_tra_don_cua_nguoi_khac_dat_co(monkeypatch):
    async def doc(ma, cid):
        return {"ma_don": ma, "cua_hoi_thoai_nay": False}

    monkeypatch.setattr(tools, "_doc_don_trong_csdl", doc)
    kq = chay(tools._tra_cuu_don_hang({"ma_don": "AS1"}, uuid.uuid4()))
    assert kq["tim_thay"] is False and kq["can_chuyen_nhan_vien"] is True


_SP = [{"ma": "AS-CL01", "ten": "Sữa rửa mặt dịu nhẹ", "gia": 245000}]
_DON = {"items": [{"ten_san_pham": "Sữa rửa mặt dịu nhẹ", "so_luong": 1}],
        "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
        "khach_dia_chi": "giao ở cổng chợ Bến Thành", "khach_da_xac_nhan": True}


def _cong_erp(monkeypatch, ton):
    from agent.erp import nha_may

    class Cong:
        async def ton_kho(self, ma, bo_qua_cache=False):
            return ton

    monkeypatch.setattr(nha_may, "cong", lambda: Cong())


def test_len_don_khong_tra_duoc_ton_dat_co(monkeypatch):
    _cong_erp(monkeypatch, None)
    kq = chay(tools._tao_don_hang(dict(_DON), _SP, None))
    assert kq["tao_duoc"] is False and kq["can_chuyen_nhan_vien"] is True


def test_len_don_luu_hong_dat_co(monkeypatch):
    _cong_erp(monkeypatch, SimpleNamespace(ban_duoc=10))

    async def hong(*a, **k):
        raise RuntimeError("mất kết nối")

    monkeypatch.setattr(tools.db, "fetchrow_chac", hong)
    kq = chay(tools._tao_don_hang(dict(_DON), _SP, None))
    assert kq["tao_duoc"] is False and kq["can_chuyen_nhan_vien"] is True


def test_len_don_kho_tu_choi_dat_co(monkeypatch):
    from agent.erp import day_don

    _cong_erp(monkeypatch, SimpleNamespace(ban_duoc=10))

    async def luu(*a, **k):
        return {"id": 1, "ma_don": "AS1"}

    async def giu(lines, ma):
        return True, ""

    async def ghi(*a, **k):
        return None

    async def day(*a, **k):
        return SimpleNamespace(ket_cuc="tu_choi", ly_do="sai mã kho")

    monkeypatch.setattr(tools.db, "fetchrow_chac", luu)
    monkeypatch.setattr(tools.db, "log_event", ghi)
    monkeypatch.setattr(tools.kho, "giu_hang", giu)
    monkeypatch.setattr(day_don, "day_don_da_luu", day)
    monkeypatch.setattr(tools.settings, "nguong_tu_chot_vnd", 10**12)
    kq = chay(tools._tao_don_hang(dict(_DON), _SP, None))
    assert kq["tao_duoc"] is False and kq["can_chuyen_nhan_vien"] is True


def test_co_cua_cong_cu_lam_agent_chuyen_nguoi_that(san):
    san["ket_qua"] = {"tim_thay": False, "can_chuyen_nhan_vien": True,
                      "ghi_chu": "Cần chuyển người hỗ trợ."}
    san["kich_ban"] = [_goi("tra_cuu_van_chuyen", {"ma_don": "AS1"}),
                       _chot("Dạ em kiểm tra chưa được ạ.")]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="đơn AS1 tới đâu?"))
    assert r.escalate and r.luoi_bat == "cong_cu_yeu_cau"


# ══ 7 · stop_reason bất thường ═══════════════════════════════════════════

@pytest.mark.parametrize("stop,text", [
    ("SAFETY", ""),
    ("MALFORMED_FUNCTION_CALL", ""),
    ("MAX_TOKENS", "Dạ sản phẩm này phù hợp với da dầu vì nó có thành phần"),
    ("refusal", ""),
    ("max_tokens", "Dạ chị dùng"),
])
def test_dung_bat_thuong_thi_chuyen_nguoi(san, stop, text):
    san["kich_ban"] = [_chot(text, stop=stop)]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="kem x dùng sao?"))
    assert r.escalate and r.luoi_bat == "dung_bat_thuong"
    assert stop in r.escalate_reason
    # Có DẤU VẾT: dashboard nhìn một lượt bị chặn an toàn như lượt thường.
    assert any(k == "agent.dung_bat_thuong" and v["ly_do"] == stop for k, v in san["su_kien"])


def test_dung_binh_thuong_khong_chuyen(san):
    san["ket_qua"] = {"tim_thay": True, "gia": 1}
    san["kich_ban"] = [_goi("tra_cuu_san_pham", {"ten": "x"}), _chot("Dạ giá 1đ ạ.", stop="STOP")]
    r = chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="giá?"))
    assert r.luoi_bat != "dung_bat_thuong" and not r.escalate


def test_tran_token_chua_du_cho_cau_tra_loi_ngoai_phan_suy_nghi(san):
    """Token suy nghĩ đếm VÀO trần; phần còn lại phải đủ cho câu trả lời thật."""
    san["kich_ban"] = [_chot("Dạ.")]
    chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="chào shop"))
    kw = san["kw"][0]
    con_lai = kw["max_tokens"] - llm.THINKING_BUDGET[kw["effort"]]
    assert con_lai >= 2000, f"chỉ còn {con_lai} token cho câu trả lời"


# ══ 4 · chi phí đã tiêu vẫn vào sổ khi lượt ném lỗi ════════════════════════

def test_cong_cu_nem_loi_van_ghi_chi_phi(san):
    san["ket_qua"] = RuntimeError("plugin hết giờ")
    san["kich_ban"] = [_goi("tra_cuu_san_pham", {"ten": "x"}, cost=0.013)]
    with pytest.raises(RuntimeError) as e:
        chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="giá?"))
    assert san["ngan_sach"] == [pytest.approx(0.013)]
    assert e.value.chi_phi_da_tieu == pytest.approx(0.013)


def test_model_nem_loi_vong_hai_van_ghi_vong_mot(san):
    san["ket_qua"] = {"tim_thay": True, "gia": 1}
    san["kich_ban"] = [_goi("tra_cuu_san_pham", {"ten": "x"}, cost=0.02),
                       RuntimeError("Gemini 403: API key invalid")]
    with pytest.raises(RuntimeError):
        chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="giá?"))
    assert san["ngan_sach"] == [pytest.approx(0.02)]


def test_luot_binh_thuong_ghi_dung_mot_lan(san):
    san["kich_ban"] = [_chot("Dạ chào chị ạ.", cost=0.02)]
    chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="chào shop"))
    assert san["ngan_sach"] == [pytest.approx(0.02)]


# ── nhánh except ở tầng kênh ───────────────────────────────────────────

@pytest.fixture
def kenh(monkeypatch):
    from agent import canh_gac, db, runtime
    from agent.core import thong_bao_noi_bo
    from agent.omnichannel import agent_loi, xu_ly_tin_vao

    hop: dict = {"sql": [], "su_kien": [], "viec": [], "bao_nv": [], "bao_khach": [], "bao_dong": []}

    async def execute(sql, *a):
        hop["sql"].append((sql, a))

    async def log_event(kind, **k):
        hop["su_kien"].append(kind)

    async def tao(cid, ly_do=""):
        hop["viec"].append(ly_do)

    async def bao_nv(adapter, ref, cid, ly_do, tom_tat=""):
        hop["bao_nv"].append(ly_do)

    async def bao_khach(adapter, ref, cid):
        hop["bao_khach"].append(cid)

    async def bao_dong(chi_tiet, **k):
        hop["bao_dong"].append(chi_tiet)

    monkeypatch.setattr(db, "execute", execute)
    monkeypatch.setattr(db, "log_event", log_event)
    monkeypatch.setattr(thong_bao_noi_bo, "bao_ai_chuyen_giao", tao)
    monkeypatch.setattr(xu_ly_tin_vao, "bao_nhan_vien_tiep_quan", bao_nv)
    monkeypatch.setattr(xu_ly_tin_vao, "bao_khach_dang_chuyen_nguoi", bao_khach)
    monkeypatch.setattr(canh_gac, "bao_dong", bao_dong)
    monkeypatch.setattr(runtime, "mode", lambda: "auto")
    monkeypatch.setattr(agent_loi, "_trang_thai", agent_loi._TrangThai())
    return hop


def _msg():
    return SimpleNamespace(conversation_ref="ref-1", text="kem này giá sao", account_id=uuid.uuid4())


def test_agent_loi_chuyen_nguoi_du_bon_viec(kenh):
    from agent.omnichannel import agent_loi

    loi = RuntimeError("Gemini 403: API key invalid")
    loi.chi_phi_da_tieu = 0.015  # type: ignore[attr-defined]
    chay(agent_loi.chuyen_nguoi_vi_agent_loi(_msg(), uuid.uuid4(), object(), loi))
    assert kenh["viec"], "agent lỗi mà không báo nhân viên (thông báo chuyển giao)"
    assert kenh["bao_nv"] and kenh["bao_khach"], "không báo nhân viên/khách"
    assert {"agent.error", "conversation.escalated"} <= set(kenh["su_kien"])
    sql, tham_so = kenh["sql"][0]
    assert "escalated" in sql and "cost_usd = cost_usd + $2" in sql
    assert tham_so[1] == pytest.approx(0.015)
    assert len(kenh["bao_dong"]) == 1


def test_bao_dong_toi_da_mot_lan_moi_cua_so(kenh, monkeypatch):
    from agent.omnichannel import agent_loi

    gio = {"t": 1000.0}
    monkeypatch.setattr(agent_loi.time, "monotonic", lambda: gio["t"])
    for _ in range(5):
        chay(agent_loi.chuyen_nguoi_vi_agent_loi(_msg(), uuid.uuid4(), object(), RuntimeError("x")))
    assert len(kenh["bao_dong"]) == 1
    assert len(kenh["viec"]) == 5, "giới hạn báo động không được nuốt thông báo của từng khách"
    gio["t"] += agent_loi.CUA_SO_BAO_DONG_GIAY + 1
    chay(agent_loi.chuyen_nguoi_vi_agent_loi(_msg(), uuid.uuid4(), object(), RuntimeError("x")))
    assert len(kenh["bao_dong"]) == 2
    assert "5 lỗi" in kenh["bao_dong"][1], "lần báo sau phải nói số lỗi dồn lại"


def test_che_do_goi_y_khong_tu_gui_cau_cho_khach(kenh, monkeypatch):
    from agent import runtime
    from agent.omnichannel import agent_loi

    monkeypatch.setattr(runtime, "mode", lambda: "assist")
    chay(agent_loi.chuyen_nguoi_vi_agent_loi(_msg(), uuid.uuid4(), object(), RuntimeError("x")))
    assert kenh["bao_khach"] == [] and kenh["viec"]


def test_nhanh_except_cua_luong_tin_vao_goi_agent_loi():
    import inspect

    from agent.omnichannel import xu_ly_tin_vao

    src = inspect.getsource(xu_ly_tin_vao.handle_inbound)
    khoi = src[src.index("except Exception as exc:  # noqa: BLE001 — suy giảm êm"):][:900]
    assert "agent_loi.chuyen_nguoi_vi_agent_loi(" in khoi


# ══ 5 · token suy nghĩ của Gemini vào chi phí ═════════════════════════════

def test_chi_phi_gemini_tinh_ca_token_suy_nghi(monkeypatch):
    from agent import cau_hinh_dong as cd

    cd._gia_tri.clear()
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    monkeypatch.setattr(llm.settings, "llm_provider", "gemini_api")

    async def post(self, url, headers=None, json=None):
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 10,
                              "thoughtsTokenCount": 900},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    try:
        r = chay(llm.complete(system=llm.cached_system("x"),
                              messages=[{"role": "user", "content": "?"}],
                              model="gemini-2.5-flash", max_tokens=2000))
    finally:
        cd._gia_tri.clear()
    assert r.tokens_out == 910
    assert r.cost_usd == pytest.approx(llm.price("gemini-2.5-flash", 100, 910))


# ══ 8 · Claude không chặn vòng lặp sự kiện ═══════════════════════════════

def test_claude_goi_messages_create_ngoai_luong_su_kien():
    luong: dict = {}

    class Messages:
        def create(self, **kw):
            luong["goi"] = threading.get_ident()
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="ok")],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
                stop_reason="end_turn")

    async def chinh():
        luong["vong_lap"] = threading.get_ident()
        return await llm._complete_claude(
            system=llm.cached_system("x"), messages=[{"role": "user", "content": "?"}],
            model="claude-haiku-4-5", max_tokens=8, tools=None, effort="low",
            client=SimpleNamespace(messages=Messages()))

    r = chay(chinh())
    assert r.text == "ok"
    assert luong["goi"] != luong["vong_lap"], "messages.create chạy trên luồng vòng lặp sự kiện"


# ══ 9 · che SĐT dính chữ và đọc theo cặp ════════════════════════════════

@pytest.mark.parametrize("vao,ra", [
    ("sdt0912345678", "sdt[SĐT_1]"),
    ("SĐT0912345678 ạ", "SĐT[SĐT_1] ạ"),
    ("zalo0912345678", "zalo[SĐT_1]"),
    ("số em 0912 34 56 78 nha", "số em [SĐT_1] nha"),
    ("0912.34.56.78", "[SĐT_1]"),
    ("0912345678 12 hộp", "[SĐT_1] 12 hộp"),
])
def test_che_bien_the_sdt_tung_lot(vao, ra):
    m = MatNa()
    assert m.che(vao) == ra
    assert m.mo(m.che(vao)) == vao, "khách phải nhận lại đúng chữ đã viết"


@pytest.mark.parametrize("giu", [
    "SKU SR0912345678", "mã giảm GIAM0912345678", "ngày 05.09.2026", "giá 1.290.000 đồng",
    "mã đơn AS260819235000", "lọ 50ml",
])
def test_che_khong_nham_sau_khi_noi_long(giu):
    assert MatNa().che(giu) == giu


# ══ 10 · khách đòi gặp người ═════════════════════════════════════════════

@pytest.mark.parametrize("cau", [
    "chuyển nhân viên giúp em", "cho em gặp nv", "gặp tư vấn viên được không",
    "chuyen nv giup em", "cho chị nói chuyện với tư vấn viên",
])
def test_doi_gap_nguoi_bien_the_moi(cau):
    assert tb.khach_doi_gap_nguoi(cau), cau


@pytest.mark.parametrize("cau", [
    "tư vấn viên bên shop nhiệt tình quá", "nhân viên chuyển hàng chậm quá",
    "nv giao hàng chưa tới", "bên mình có tư vấn viên da liễu không",
])
def test_doi_gap_nguoi_khong_nham(cau):
    assert not tb.khach_doi_gap_nguoi(cau), cau
