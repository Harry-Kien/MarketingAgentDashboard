"""
Bộ kiểm thử hồi quy ĐỢT 2 — BUG-16-01 (đánh giá căn cứ RAG) & BUG-16-02
(xử lý finish_reason="tool_calls" và an toàn vòng lặp công cụ).

Tất cả LLM, RAG, ERP và công cụ có tác dụng phụ đều được mock / sandboxed
hoàn toàn — không gọi API AI trả phí, không gửi tin nhắn thật, không chạm
CSDL sản xuất `marketing_agent`.
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from types import SimpleNamespace

import pytest

from agent import db, ngan_sach
from agent.api import phong_thu_agent
from agent.config import ROOT
from agent.core import (
    agent as brain,
    agent_ho_so,
    dau_vet_ai,
    ho_so_khach,
    llm,
    rag,
    tools,
    uy_quyen,
)
from agent.ky_nang import goi as goi_ky_nang_mod, kho_ky_nang

_REAL_RUN_TOOL = tools.run_tool


def _chay(coro):
    return asyncio.run(coro)


def _passage(
    title: str,
    content: str,
    *,
    score: float = 0.85,
    version: int = 2,
) -> rag.Passage:
    return rag.Passage(
        doc_title=title,
        content=content,
        score=score,
        document_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        version=version,
        chunk_id=uuid.uuid4(),
        source="tai-lieu-thu.md",
    )


def _llm_text(text: str, *, stop_reason: str = "stop", cost: float = 0.004) -> llm.LLMResult:
    return llm.LLMResult(
        text=text,
        model="gpt-4o-mini-mock",
        tokens_in=20,
        tokens_out=15,
        cost_usd=cost,
        stop_reason=stop_reason,
    )


def _llm_tools(
    calls: list[dict],
    *,
    stop_reason: str = "tool_calls",
    text: str = "",
    cost: float = 0.005,
) -> llm.LLMResult:
    return llm.LLMResult(
        text=text,
        model="gpt-4o-mini-mock",
        tokens_in=25,
        tokens_out=15,
        cost_usd=cost,
        tool_calls=calls,
        stop_reason=stop_reason,
    )


@pytest.fixture
def san_agent(monkeypatch):
    """Dựng môi trường `brain.respond` giả lập sạch, kiểm soát RAG/LLM/tool."""
    hop: dict = {
        "kich_ban": [],
        "passages": [],
        "goi_tool": [],
        "ket_qua_tool": {},
        "su_kien": [],
        "ngan_sach": [],
        "nguong": 0.55,
    }

    async def fetchrow(sql, *a):
        return {"cost_usd": 0.0}

    async def con_ngan_sach():
        return True, 0.0, 0.0

    async def retrieve(q, k=5):
        return list(hop["passages"])

    async def cong_cu_dang_bat(tat_ca):
        return tat_ca

    async def huong_dan_cho_luot(q):
        return []

    async def ho_so_luot(*a, **kw):
        return agent_ho_so.HoSo(
            id=None,
            ten="Mặc định",
            huong_dan="",
            nguong_tu_tin=hop["nguong"],
            luoi_tat=frozenset(),
        )

    async def doc_ho_so_khach(*a, **kw):
        return None

    async def log_event(kind, **kw):
        hop["su_kien"].append((kind, kw))

    async def complete(**kw):
        buoc = hop["kich_ban"].pop(0)
        if isinstance(buoc, BaseException):
            raise buoc
        return buoc

    async def run_tool(name, args, conversation_id=None):
        hop["goi_tool"].append((name, args))
        kq = hop["ket_qua_tool"]
        if callable(kq):
            val = kq(name, args, conversation_id)
            if asyncio.iscoroutine(val):
                val = await val
            return val
        if isinstance(kq, BaseException):
            raise kq
        if isinstance(kq, dict) and name in kq and isinstance(kq[name], (dict, BaseException)):
            val = kq[name]
            if isinstance(val, BaseException):
                raise val
            return val
        return kq

    monkeypatch.setattr(db, "fetchrow", fetchrow)
    monkeypatch.setattr(db, "log_event", log_event)
    monkeypatch.setattr(ngan_sach, "con_ngan_sach", con_ngan_sach)
    monkeypatch.setattr(ngan_sach, "ghi_nhan", lambda c: hop["ngan_sach"].append(c))
    monkeypatch.setattr(rag, "retrieve", retrieve)
    monkeypatch.setattr(rag, "as_context", lambda p: "Chưa có tài liệu.")
    monkeypatch.setattr(kho_ky_nang, "cong_cu_dang_bat", cong_cu_dang_bat)
    monkeypatch.setattr(tools, "run_tool", run_tool)
    monkeypatch.setattr(llm, "complete", complete)
    return hop


# ══════════════════════════════════════════════════════════════════════════════
# A · BUG-16-01 — Đánh giá căn cứ RAG trung thực (3 trạng thái rõ ràng)
# ══════════════════════════════════════════════════════════════════════════════


def test_bug16_01_rag_lien_quan_va_ho_tro_du_can_cu(san_agent):
    """Kịch bản 1: RAG thực sự liên quan & hỗ trợ khẳng định -> Đủ căn cứ."""
    san_agent["passages"] = [
        _passage(
            "Chính sách đổi trả v2",
            "Khách hàng được đổi trả sản phẩm nguyên seal trong vòng 7 ngày kể từ khi nhận hàng.",
            score=0.88,
        )
    ]
    san_agent["kich_ban"] = [
        _llm_text("Dạ sản phẩm nguyên seal bên em được đổi trả trong 7 ngày kể từ khi nhận hàng ạ.")
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Bên shop đổi trả trong bao nhiêu ngày ạ?",
    ))
    assert r.grounded is True
    assert r.escalate is False
    assert r.sources == ["Chính sách đổi trả v2"]
    cc = dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)
    assert cc["ma"] == "du"
    assert cc["nhan"] == "Đủ căn cứ"


def test_bug16_01_rag_khong_lien_quan_du_diem_cao_khong_duoc_du_can_cu(san_agent):
    """
    Kịch bản 2: RAG score cao (0.85) nhưng nội dung KHÔNG liên quan câu trả lời ->
    KHÔNG được đánh dấu Đủ căn cứ, phải rơi vào Căn cứ chưa đầy đủ & lưới an toàn xử lý.
    """
    san_agent["passages"] = [
        _passage(
            "Chính sách bảo mật dữ liệu",
            "Hệ thống mã hóa thông tin thanh toán theo chuẩn SSL 256-bit và lưu trữ an toàn.",
            score=0.85,
        )
    ]
    san_agent["kich_ban"] = [
        _llm_text("Dạ serum vitamin C dưỡng trắng da rất dịu nhẹ cho da nhạy cảm ạ.")
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Serum vitamin C có hợp da nhạy cảm không ạ?",
    ))
    assert r.grounded is False
    assert r.sources == []
    assert r.escalate is True
    assert r.luoi_bat == "tin_cay_thap"
    cc = dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)
    assert cc["ma"] == "chua_du"
    assert cc["nhan"] == "Căn cứ chưa đầy đủ"
    assert any("không liên quan" in ly_do or "không hỗ trợ" in ly_do for ly_do in cc["thieu"])


def test_bug16_01_sai_so_lieu_thoi_han_voi_tai_lieu_bi_chan(san_agent):
    """RAG nói 7 ngày nhưng model tự bịa 30 ngày -> không được gắn Đủ căn cứ."""
    san_agent["passages"] = [
        _passage("Chính sách đổi trả", "Khách được đổi trả sản phẩm trong 7 ngày.", score=0.90)
    ]
    san_agent["kich_ban"] = [
        _llm_text("Dạ bên em hỗ trợ đổi trả sản phẩm thoải mái trong 30 ngày ạ.")
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Đổi trả trong mấy ngày?",
    ))
    assert r.grounded is False
    assert r.escalate is True
    cc = dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)
    assert cc["ma"] == "chua_du"
    assert any("30 ngày" in ly_do for ly_do in cc["thieu"])


@pytest.mark.parametrize(
    "cau_hoi,passages,tra_loi",
    [
        (
            "Alo shop",
            [_passage("Chính sách đổi trả", "Đổi trả 7 ngày nếu lỗi nhà sản xuất.", score=0.85)],
            "Em chưa rõ ý anh/chị, anh/chị nói thêm giúp em nhé.",
        ),
        (
            "Xin chào shop",
            [],
            "Xin chào anh/chị, em có thể hỗ trợ thông tin gì cho mình ạ?",
        ),
    ],
)
def test_bug16_01_cau_lam_ro_va_chao_hoi_trung_tinh_khong_can_can_cu(
    san_agent, cau_hoi, passages, tra_loi
):
    """
    Kịch bản 3 (TC-16-001): Câu trả lời làm rõ ý khách hoặc chào hỏi giao tiếp
    hiển thị trạng thái trung tính 'Không yêu cầu căn cứ' (`khong_can`),
    `grounded=False`, không trích dẫn giả và không chuyển người oan.
    """
    san_agent["passages"] = passages
    san_agent["kich_ban"] = [_llm_text(tra_loi)]
    r = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question=cau_hoi))
    assert r.grounded is False
    assert r.sources == []
    assert r.escalate is False
    assert r.luoi_bat is None
    cc = dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)
    assert cc["ma"] == "khong_can"
    assert cc["nhan"] == "Không yêu cầu căn cứ"
    assert cc["thieu"] == []


def test_bug16_01_khong_co_nguon_rag_cho_cau_hoi_nghiep_vu(san_agent):
    """
    Kịch bản 4: Không có nguồn RAG & không tra được dữ liệu cho câu khẳng định
    sản phẩm/chính sách -> grounded=False, escalate=True (`tin_cay_thap`), `khong_co`.
    """
    san_agent["passages"] = []
    san_agent["kich_ban"] = [
        _llm_text("Dạ kem chống nắng Blanica có chỉ số SPF50+ và chống nước tốt ạ.")
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Kem chống nắng Blanica chống nước không ạ?",
    ))
    assert r.grounded is False
    assert r.sources == []
    assert r.escalate is True
    assert r.luoi_bat == "tin_cay_thap"
    cc = dau_vet_ai.phan_loai_can_cu(r, nguong=0.55)
    assert cc["ma"] == "khong_co"
    assert cc["nhan"] == "Không có căn cứ"


def test_bug16_01_dong_bo_dau_vet_phong_thu_va_js_dashboard(san_agent):
    """
    Kịch bản 5: Dữ liệu `dau_vet_ai.dung`, API Phòng thử `reply_thanh_dict`,
    và logic JS `19-trach-nhiem.js` / `13-cau-hinh.js` đồng nhất cả 3 trạng thái.
    """
    hs = agent_ho_so.mac_dinh()

    # 1. Làm rõ ý (TC-16-001)
    san_agent["passages"] = [_passage("TL", "Nội dung không liên quan.", score=0.9)]
    san_agent["kich_ban"] = [_llm_text("Em chưa rõ ý anh/chị, anh/chị nói thêm giúp em nhé.")]
    r_lam_ro = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="?"))

    dv_lam_ro = dau_vet_ai.dung(
        r_lam_ro, ho_so=hs, che_do_chung="tu_dong", duyet_rieng=False, tu_gui=True
    )
    pt_lam_ro = phong_thu_agent.reply_thanh_dict(r_lam_ro)
    assert dv_lam_ro["can_cu"]["ma"] == "khong_can"
    assert dv_lam_ro["tin_cay"]["co_can_cu"] is False
    assert pt_lam_ro["can_cu"]["ma"] == "khong_can"
    assert pt_lam_ro["can_cu"]["nhan"] == "Không yêu cầu căn cứ"

    # Kiểm tra thực thi hàm JS thực tế trong dashboard/src/19-trach-nhiem.js & 13-cau-hinh.js
    js_path = ROOT / "dashboard" / "src" / "19-trach-nhiem.js"
    js_src = js_path.read_text(encoding="utf-8")
    cau_hinh_src = (ROOT / "dashboard" / "src" / "13-cau-hinh.js").read_text(encoding="utf-8")
    assert "khong_can" in js_src
    assert "d.can_cu && d.can_cu.nhan" in cau_hinh_src

    node_script = """
    const fs = require('fs');
    const src = fs.readFileSync(process.argv[1], 'utf8');
    const start = src.indexOf('function nhanCanCu(');
    const end = src.indexOf('document.addEventListener');
    const snippet = src.slice(start, end);
    const fn = new Function('esc', snippet + '; return { nhanCanCu, tagCanCu, veCanCuPhanLoai };');
    const api = fn((s) => String(s || ''));
    const msg = JSON.parse(process.argv[2]);
    console.log(JSON.stringify({
      nhan: api.nhanCanCu(msg),
      tag: api.tagCanCu(msg),
      panel: api.veCanCuPhanLoai(msg)
    }));
    """
    out = subprocess.check_output(
        [
            "node",
            "-e",
            node_script,
            str(js_path),
            json.dumps({"grounded": r_lam_ro.grounded, "dau_vet_ai": dv_lam_ro}, ensure_ascii=False),
        ],
        text=True,
    )
    parsed = json.loads(out)
    assert parsed["nhan"] == "Không yêu cầu căn cứ"
    assert parsed["tag"] == "plain"
    assert parsed["panel"] == ""


# ══════════════════════════════════════════════════════════════════════════════
# B · BUG-16-02 — Xử lý `finish_reason="tool_calls"` và vòng lặp an toàn
# ══════════════════════════════════════════════════════════════════════════════


def test_bug16_02_finish_reason_tool_calls_mot_tool_hop_le(san_agent):
    """Kịch bản 1: OpenAI-compatible `stop_reason='tool_calls'` thực thi tool và trả lời bình thường."""
    san_agent["ket_qua_tool"] = {
        "tra_cuu_san_pham": {"tim_thay": True, "ten": "Serum Vitamin C", "gia": 250000, "ton_kho": 12}
    }
    san_agent["kich_ban"] = [
        _llm_tools(
            [{"id": "call_1", "name": "tra_cuu_san_pham", "input": {"ten": "Serum Vitamin C"}}],
            stop_reason="tool_calls",
        ),
        _llm_text("Dạ Serum Vitamin C hiện còn 12 chai, giá 250.000đ ạ.", stop_reason="stop"),
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Serum Vitamin C giá bao nhiêu ạ?",
    ))
    assert r.escalate is False
    assert r.luoi_bat is None
    assert r.grounded is True
    assert san_agent["goi_tool"] == [("tra_cuu_san_pham", {"ten": "Serum Vitamin C"})]
    assert len(r.cong_cu) == 1
    assert "250.000đ" in r.text


def test_bug16_02_mot_luot_nhieu_tool_calls_hop_le(san_agent):
    """Kịch bản 2: Một lượt `stop_reason='tool_calls'` gọi nhiều tool hợp lệ cùng lúc."""
    san_agent["ket_qua_tool"] = {
        "tra_cuu_san_pham": {"tim_thay": True, "ten": "Sữa rửa mặt", "gia": 180000},
        "tra_cuu_don_hang": {"tim_thay": True, "ma_don": "DH-001", "trang_thai": "Đang giao"},
    }
    san_agent["kich_ban"] = [
        _llm_tools(
            [
                {"id": "c1", "name": "tra_cuu_san_pham", "input": {"ten": "Sữa rửa mặt"}},
                {"id": "c2", "name": "tra_cuu_don_hang", "input": {"ma_don": "DH-001"}},
            ],
            stop_reason="tool_calls",
        ),
        _llm_text("Đơn DH-001 đang giao và Sữa rửa mặt giá 180.000đ ạ.", stop_reason="stop"),
    ]
    r = _chay(brain.respond(
        conversation_id=uuid.uuid4(),
        history=[],
        question="Kiểm tra đơn DH-001 và giá sữa rửa mặt",
    ))
    assert r.escalate is False
    assert [t[0] for t in san_agent["goi_tool"]] == ["tra_cuu_san_pham", "tra_cuu_don_hang"]
    assert [c["ten"] for c in r.cong_cu] == ["tra_cuu_san_pham", "tra_cuu_don_hang"]


def test_bug16_02_tool_tra_loi_hoac_nem_exception(san_agent):
    """
    Kịch bản 3:
    (a) Tool trả `{"loi": ...}` -> không crash, không nâng sai `grounded`, chuyển người an toàn.
    (b) Tool ném Exception -> vẫn ghi nhận chi phí đã tiêu vào `chi_phi_da_tieu` và ném sạch cho tầng kênh xử lý.
    """
    # (a) Tool trả lỗi có cấu trúc
    san_agent["ket_qua_tool"] = {"loi": "ERPNext tạm thời quá tải"}
    san_agent["kich_ban"] = [
        _llm_tools(
            [{"id": "c1", "name": "tra_cuu_san_pham", "input": {"ten": "Serum C"}}],
            stop_reason="tool_calls",
        ),
        _llm_text("Dạ Serum C giá 250.000đ ạ.", stop_reason="stop"),
    ]
    r = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Serum C giá bao nhiêu?"))
    assert r.grounded is False
    assert r.escalate is True
    assert r.luoi_bat == "tin_cay_thap"

    # (b) Tool ném RuntimeError -> chi phí không mất và không nuốt nhầm kết quả thành công
    san_agent["ngan_sach"].clear()
    san_agent["ket_qua_tool"] = RuntimeError("Mất kết nối kho ERP")
    san_agent["kich_ban"] = [
        _llm_tools(
            [{"id": "c2", "name": "tra_cuu_san_pham", "input": {"ten": "Serum C"}}],
            stop_reason="tool_calls",
            cost=0.009,
        )
    ]
    with pytest.raises(RuntimeError) as exc_info:
        _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Giá Serum C?"))
    assert getattr(exc_info.value, "chi_phi_da_tieu", None) == pytest.approx(0.009)
    assert san_agent["ngan_sach"] == [pytest.approx(0.009)]


def test_bug16_02_tool_bi_tu_choi_theo_uy_quyen_chinh_sach(san_agent, monkeypatch):
    """
    Kịch bản 4: Dùng `tools.run_tool` thật với chính sách `uy_quyen.quyet_dinh` trả `khong_su_dung` ->
    công cụ ghi bị chặn bởi `uy_quyen.chan_chuyen_nguoi`, không thực thi ERP và agent chuyển người sạch sẽ.
    """
    thuc_thi_erp: list = []

    async def quyet_dinh_cam(hanh_dong, conversation_id):
        return uy_quyen.QuyetDinh(
            hanh_dong=hanh_dong,
            che_do="tu_dong",
            muc="khong_su_dung",
        )

    async def kho_khong_tat(ten):
        return False

    monkeypatch.setattr(tools, "run_tool", _REAL_RUN_TOOL)
    monkeypatch.setattr(uy_quyen, "quyet_dinh", quyet_dinh_cam)
    monkeypatch.setattr(kho_ky_nang, "dang_tat", kho_khong_tat)
    monkeypatch.setattr(tools, "_catalog_song", lambda *a, **kw: thuc_thi_erp.append("catalog"))

    san_agent["kich_ban"] = [
        _llm_tools(
            [
                {
                    "id": "c_don",
                    "name": "tao_don_hang",
                    "input": {
                        "khach_da_xac_nhan": True,
                        "khach_ten": "Chị Lan",
                        "khach_sdt": "0912345678",
                        "khach_dia_chi": "12 Lê Lợi, Q1",
                        "items": [{"ten_san_pham": "Serum C", "so_luong": 1}],
                    },
                }
            ],
            stop_reason="tool_calls",
        ),
        _llm_text("Dạ yêu cầu lên đơn cần nhân viên xác nhận giúp anh/chị ạ."),
    ]
    r = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Đặt giúp mình 1 Serum C"))
    assert thuc_thi_erp == []
    assert r.escalate is True
    assert r.luoi_bat == "cong_cu_yeu_cau"
    assert r.cong_cu[0]["ket_qua"].get("bi_chan") is True
    assert r.cong_cu[0]["ket_qua"].get("can_chuyen_nhan_vien") is True
    assert any(k == "ai.hanh_dong.chan" for k, _ in san_agent["su_kien"])


def test_bug16_02_chan_vong_lap_tool_vo_han_va_vuot_nguong(san_agent):
    """Kịch bản 5: Chặn lặp công cụ giống nhau liên tiếp VÀ chặn khi vượt `MAX_TOOL_ROUNDS`."""
    # (a) Gọi lặp y hệt ở vòng 1 và vòng 2 -> dừng sớm ở vòng 2, không đốt hết vòng 3-4
    san_agent["ket_qua_tool"] = {"tim_thay": True, "gia": 100000}
    san_agent["kich_ban"] = [
        _llm_tools([{"id": "c1", "name": "tra_cuu_san_pham", "input": {"ten": "A"}}], stop_reason="tool_calls"),
        _llm_tools([{"id": "c2", "name": "tra_cuu_san_pham", "input": {"ten": "A"}}], stop_reason="tool_calls"),
        _llm_tools([{"id": "c3", "name": "tra_cuu_san_pham", "input": {"ten": "A"}}], stop_reason="tool_calls"),
    ]
    r_lap = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Giá A?"))
    assert r_lap.escalate is True
    assert r_lap.luoi_bat == "het_vong"
    assert len(san_agent["goi_tool"]) == 1

    # (b) Các tham số khác nhau ở mỗi vòng vượt MAX_TOOL_ROUNDS -> vẫn dừng an toàn ở MAX_TOOL_ROUNDS
    san_agent["goi_tool"].clear()
    san_agent["kich_ban"] = [
        _llm_tools([{"id": f"c{i}", "name": "tra_cuu_san_pham", "input": {"ten": f"SP-{i}"}}], stop_reason="tool_calls")
        for i in range(brain.MAX_TOOL_ROUNDS + 1)
    ]
    r_vuot = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Xem nhiều SP"))
    assert r_vuot.escalate is True
    assert r_vuot.luoi_bat == "het_vong"
    assert len(san_agent["goi_tool"]) == brain.MAX_TOOL_ROUNDS


@pytest.mark.parametrize(
    "stop_reason,tool_calls",
    [
        ("tool_calls", []),
        ("tool_use", []),
        ("SAFETY", []),
        ("MAX_TOKENS", []),
    ],
)
def test_bug16_02_dung_bat_thuong_thuc_su_chuyen_nguoi(san_agent, stop_reason, tool_calls):
    """
    Kịch bản 6: `finish_reason='tool_calls'` nhưng `tool_calls=[]` (rỗng/hỏng),
    hoặc `SAFETY` / `MAX_TOKENS` -> vẫn kích hoạt `dung_bat_thuong` và chuyển người.
    """
    san_agent["kich_ban"] = [_llm_tools(tool_calls, stop_reason=stop_reason, text="...")]
    r = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Tư vấn sản phẩm"))
    assert r.escalate is True
    assert r.luoi_bat == "dung_bat_thuong"
    assert stop_reason in r.escalate_reason


def test_bug16_02_khong_chay_trung_lap_side_effect_tool_trong_cung_luot(san_agent):
    """
    Kịch bản 7: Tool có tác dụng phụ (`tao_don_hang`) nếu bị gọi lặp với cùng tham số
    trong cùng lượt/retry không được thực thi trùng lặp sang hệ thống đích.
    """
    san_agent["ket_qua_tool"] = {
        "tao_don_hang": {"tao_duoc": True, "ma_don": "SO-2026-01"}
    }
    don_args = {
        "khach_da_xac_nhan": True,
        "khach_ten": "Chị Lan",
        "khach_sdt": "0912345678",
        "khach_dia_chi": "12 Lê Lợi, Q1",
        "items": [{"ten_san_pham": "Serum C", "so_luong": 1}],
    }
    san_agent["kich_ban"] = [
        # Model lỡ phát 2 lời gọi `tao_don_hang` giống hệt nhau trong cùng 1 lượt
        _llm_tools(
            [
                {"id": "ord_1", "name": "tao_don_hang", "input": don_args},
                {"id": "ord_2", "name": "tao_don_hang", "input": dict(don_args)},
            ],
            stop_reason="tool_calls",
        ),
        _llm_text("Dạ em đã tạo đơn hàng SO-2026-01 thành công cho chị Lan ạ."),
    ]
    r = _chay(brain.respond(conversation_id=uuid.uuid4(), history=[], question="Đặt giúp chị 1 Serum C"))
    assert r.escalate is False
    # `tools.run_tool` chỉ được gọi ĐÚNG 1 LẦN; lần 2 bị chặn lặp
    assert len(san_agent["goi_tool"]) == 1
    assert len(r.cong_cu) == 2
    assert r.cong_cu[0]["ket_qua"]["ma_don"] == "SO-2026-01"
    assert r.cong_cu[1]["ket_qua"].get("da_chan_lap") is True


# ══════════════════════════════════════════════════════════════════════════════
# C · BUG-16-03 — Regex nhận diện giá tiền `_SO_TIEN` không nhận nhầm từ bắt đầu bằng "đ"
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "van_ban",
    [
        "Giá sản phẩm là 100đ.",
        "Phí phụ thu 100 đ cho mỗi lượt.",
        "Serum C giá 100.000đ đang còn hàng.",
        "Tổng đơn là 100.000 VNĐ ạ.",
        "Giá ưu đãi 100 nghìn đồng.",
        "Phí ship 30 ngàn đồng toàn quốc.",
        "Combo giá 250k nhé anh.",
        "Giá niêm yết 1.250.000₫.",
        "Giá bán 200,000 VND.",
        "Gói bảo dưỡng 1,5 triệu đồng.",
    ],
)
def test_bug16_03_nhan_dien_dung_cac_dinh_dang_gia_tien_hop_le(van_ban):
    """BUG-16-03: `_SO_TIEN` phải nhận diện đúng các định dạng giá tiền hợp lệ."""
    assert dau_vet_ai._SO_TIEN.search(van_ban) is not None, f"Phải nhận diện là giá tiền: {van_ban}"


@pytest.mark.parametrize(
    "van_ban",
    [
        "Chính sách đổi mới 1 đổi 1 trong 45 ngày đầu.",
        "Hỗ trợ 1 đổi 1 nếu lỗi nhà sản xuất.",
        "Sản phẩm mẫu E2E-2026 được bảo hành chính hãng 36 tháng.",
        "Khách hàng được tích lũy 100 điểm thưởng.",
        "Đơn hàng gồm 2 đơn riêng biệt và 3 ngày đầu miễn phí.",
        "Trọng lượng 2kg, phạm vi giao 5km.",
        "Thiết lập 1 đồng hồ tính SLA theo giờ làm việc.",
        "Khách đã xác nhận 100% đồng ý nhận hàng.",
    ],
)
def test_bug16_03_khong_nhan_nham_cum_khong_phai_gia_tien(van_ban):
    """BUG-16-03: không bắt nhầm '1 đổi 1', '2026 được', '100 điểm', '2kg', '1 đồng hồ'... thành số tiền."""
    assert dau_vet_ai._SO_TIEN.search(van_ban) is None, f"Không được nhận nhầm là giá tiền: {van_ban}"


def test_bug16_03_phan_loai_can_cu_du_khi_rag_co_cum_1_doi_1():
    """
    BUG-16-03 + TC-16-001: câu trả lời dựa trên tài liệu RAG có chứa 'E2E-2026 được bảo hành'
    và 'đổi mới 1 đổi 1' phải đạt trạng thái căn cứ `du` (không bị hạ xuống `chua_du` vì báo nhầm nêu số tiền).
    """
    reply = SimpleNamespace(
        text=(
            "Sản phẩm mẫu E2E-2026 được bảo hành chính hãng 36 tháng "
            "và có thể đổi mới 1 đổi 1 trong 45 ngày đầu nếu có lỗi nhà sản xuất."
        ),
        confidence=0.85,
        cong_cu=[],
        tri_thuc=[
            {
                "title": "Chính sách bảo hành Đợt 6 E2E",
                "trich": (
                    "Sản phẩm mẫu E2E-2026 được bảo hành chính hãng 36 tháng tại Trung tâm Quận 1 "
                    "và được đổi mới 1 đổi 1 trong 45 ngày đầu nếu có lỗi nhà sản xuất."
                ),
            }
        ],
    )
    cc = dau_vet_ai.phan_loai_can_cu(reply, nguong=0.55)
    assert cc["ma"] == "du"
    assert cc["thieu"] == []

    # Ngược lại: nếu câu trả lời thực sự nêu số tiền (vd '100 nghìn đồng') mà không tra danh mục/đơn -> vẫn báo `chua_du`
    reply_gia = SimpleNamespace(
        text="Sản phẩm này có giá 100 nghìn đồng và bảo hành 36 tháng.",
        confidence=0.85,
        cong_cu=[],
        tri_thuc=reply.tri_thuc,
    )
    cc_gia = dau_vet_ai.phan_loai_can_cu(reply_gia, nguong=0.55)
    assert cc_gia["ma"] == "chua_du"
    assert any("nêu số tiền" in x for x in cc_gia["thieu"])
