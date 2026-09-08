"""
Khách hỏi gì mà bảng chưa có — ghi lại, đếm, và hiện lên dashboard.

VÌ SAO
------
Bảng tra không khớp thì agent nói "chưa có thông tin" rồi chuyển người.
Đúng — nhưng KHÔNG AI BIẾT khách đã hỏi "Đà Nẵng" mười hai lần tuần này.
Bảng nằm im ở đúng kích cỡ ngày nó được tạo, và mỗi lần trượt là một lần
người trực phải trả lời tay. Đây là kiểu hỏng im lặng nhẹ nhất và dai
nhất: không lỗi, không nhật ký, chỉ là việc không tự tốt lên.

VÌ SAO CHỈ GHI CHO `tra_bang`
-----------------------------
Tham số của `tra_bang` là một khoá tra cứu: tên khu vực, tên dòng hàng.
Tham số của `tra_tai_lieu` là CÂU HỎI CỦA KHÁCH, viết nguyên văn — ghi nó
vào bảng `events` là mở một bản sao nội dung hội thoại ở chỗ không chịu
chính sách lưu trữ của `conversations`. Giá trị vận hành thì gần như
không: câu hỏi tự do không gộp lại thành "hay hỏi nhất" được như một khoá.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import tools  # noqa: E402

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def chay(coro):
    return asyncio.run(coro)


def _bat_ghi(monkeypatch, ket_qua: dict, loai: str = "tra_bang") -> list[dict]:
    ghi: list[dict] = []

    async def log_event(kind, **kw):
        ghi.append(kw)

    async def that(name, args, conversation_id=None):
        return ket_qua

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_goi_cua", lambda name: None)
    monkeypatch.setattr(tools, "_loai_cua", lambda name: loai)
    return ghi


# --- Ghi ở run_tool ---------------------------------------------------

def test_tra_bang_truot_thi_ghi_khoa_da_hoi(monkeypatch):
    ghi = _bat_ghi(monkeypatch, {"tim_thay": False, "ghi_chu": "Không có dòng nào khớp."})
    chay(tools.run_tool("tra_phi_ship", {"khoa": "Đà Nẵng"}))
    assert ghi[0]["khong_khop"] == "da nang", \
        "không ghi thì không ai biết bảng đang thiếu dòng nào"


def test_tra_bang_khop_thi_khong_ghi_gi_them(monkeypatch):
    ghi = _bat_ghi(monkeypatch, {"tim_thay": True, "khoa": "Hà Nội", "gia_tri": "35.000đ"})
    chay(tools.run_tool("tra_phi_ship", {"khoa": "Hà Nội"}))
    assert ghi[0].get("khong_khop") is None


def test_tra_tai_lieu_truot_thi_khong_ghi_cau_hoi_khach(monkeypatch):
    """Câu hỏi nguyên văn của khách không được sang bảng `events`."""
    ghi = _bat_ghi(monkeypatch, {"tim_thay": False}, loai="tra_tai_lieu")
    chay(tools.run_tool("tra_chinh_sach", {"cau_hoi": "chị Lan số 0912345678 hỏi bảo hành"}))
    assert ghi[0].get("khong_khop") is None
    assert "0912345678" not in str(ghi[0])


def test_khoa_dai_bi_cat(monkeypatch):
    ghi = _bat_ghi(monkeypatch, {"tim_thay": False})
    chay(tools.run_tool("tra_phi_ship", {"khoa": "x" * 400}))
    assert len(ghi[0]["khong_khop"]) <= 60


def test_khoa_rong_thi_khong_ghi(monkeypatch):
    ghi = _bat_ghi(monkeypatch, {"tim_thay": False})
    chay(tools.run_tool("tra_phi_ship", {"khoa": "   "}))
    assert ghi[0].get("khong_khop") is None


def test_ghi_khong_khop_hong_thi_ket_qua_van_ve(monkeypatch):
    """Số đo hỏng không được làm hỏng câu trả lời cho khách."""
    async def log_event(kind, **kw):
        raise RuntimeError("CSDL sập")

    async def that(name, args, conversation_id=None):
        return {"tim_thay": False}

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_loai_cua", lambda name: "tra_bang")
    assert chay(tools.run_tool("tra_phi_ship", {"khoa": "x"})) == {"tim_thay": False}


def test_loai_cua_hong_thi_van_ghi_su_kien(monkeypatch):
    """Bộ đệm plugin hỏng chỉ được làm mất phần `khong_khop`, không mất cả
    số lần gọi — hai số đo khác nhau, không buộc chung số phận."""
    ghi: list[dict] = []

    async def log_event(kind, **kw):
        ghi.append(kw)

    async def that(name, args, conversation_id=None):
        return {"tim_thay": False}

    def no(name):
        raise RuntimeError("bộ đệm hỏng")

    monkeypatch.setattr(tools.db, "log_event", log_event)
    monkeypatch.setattr(tools, "_run_tool_that", that)
    monkeypatch.setattr(tools, "_loai_cua", no)
    chay(tools.run_tool("tra_phi_ship", {"khoa": "x"}))
    assert ghi and ghi[0]["ten"] == "tra_phi_ship"


# --- Đọc lại thành bảng xếp hạng -------------------------------------

def test_dem_khong_khop_bo_luot_phong_thu(monkeypatch):
    """
    Cùng lý do `dem_goi_7_ngay` lọc `thu_nghiem`: bạn vừa thử mười lần một
    khoá không có trong bảng thì nó không phải nhu cầu của khách.
    """
    from agent import db
    from agent.ky_nang import kho_ky_nang

    da_hoi: dict = {}

    async def fetch(sql, *a):
        da_hoi["sql"] = " ".join(sql.split())
        return [{"ten": "tra_phi_ship", "gia_tri": "da nang", "so_lan": 5}]

    monkeypatch.setattr(db, "fetch", fetch)
    ra = chay(kho_ky_nang.khong_khop_7_ngay())
    assert ra["tra_phi_ship"][0] == {"gia_tri": "da nang", "so_lan": 5}
    assert "thu_nghiem" in da_hoi["sql"], "quên lọc lượt phòng thử"
    assert "7 days" in da_hoi["sql"]


def test_hang_khong_dung_hinh_dang_thi_bo_qua_khong_keo_sap(monkeypatch):
    """
    LỖI THẬT, bắt được ngay bộ test đầy đủ đầu tiên.

    Hàm này nằm TRONG `liet_ke()`, nên `KeyError` ở đây làm chết cả bảng
    kỹ năng — mất luôn danh sách công cụ chỉ vì một cột gợi ý. Ca đỏ đến
    từ CSDL giả của một test khác: nó trả cùng một tập hàng cho MỌI câu
    SQL, và hàng ấy không có cột `gia_tri`.

    Bỏ qua hàng lạ là nhất quán với lối rơi "CSDL hỏng thì trả rỗng" ngay
    bên dưới: tầng gợi ý không được phép mạnh hơn thứ nó phục vụ.
    """
    from agent import db
    from agent.ky_nang import kho_ky_nang

    async def fetch(sql, *a):
        return [{"khong_co_cot_nao_dung": 1},
                {"ten": "tra_phi_ship", "gia_tri": "hue", "so_lan": 2}]

    monkeypatch.setattr(db, "fetch", fetch)
    assert chay(kho_ky_nang.khong_khop_7_ngay()) == {
        "tra_phi_ship": [{"gia_tri": "hue", "so_lan": 2}]
    }


def test_dem_khong_khop_hong_thi_tra_rong(monkeypatch):
    from agent import db
    from agent.ky_nang import kho_ky_nang

    async def fetch(sql, *a):
        raise RuntimeError("CSDL sập")

    monkeypatch.setattr(db, "fetch", fetch)
    assert chay(kho_ky_nang.khong_khop_7_ngay()) == {}


# --- Dashboard --------------------------------------------------------

def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_dashboard_hien_khoa_hay_truot():
    src = _than_ham("veDongKyNang")
    assert "khong_khop" in src, "đếm rồi mà không hiện thì cũng như không đếm"


def test_khoa_truot_qua_esc():
    """Khoá là chữ do model điền từ câu khách — chuỗi máy chủ vào innerHTML."""
    src = _than_ham("veDongKyNang")
    i = src.index("khong_khop")
    quanh = src[max(0, i - 400):i + 400]
    assert re.search(r"esc\(\s*\w+\.gia_tri", quanh), "gia_tri chưa qua esc()"
