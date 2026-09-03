"""
Tin không gửi được cho khách phải KÊU, không được chết trong im lặng.

LỖI THẬT, ĐO ĐƯỢC TRÊN HỆ THỐNG ĐANG CHẠY (03.09.2026)

Ba tin của NHÂN VIÊN chết rải suốt hơn một tuần:

    03/09 08:44  staff  "oke"
    25/08 14:33  staff  "xin chào"
    25/08 14:25  staff  "Dạ mình cần Linh hỗ trợ gì ạ?"

Người trực gõ, thấy tin hiện lên khung chat, tưởng đã gửi. Khách không
nhận được gì. Không thông báo, không dấu hiệu nào trên giao diện.

Outbox thử tám lần rồi bỏ cuộc — ĐÚNG THIẾT KẾ. Chỗ hỏng là: bỏ cuộc xong
thì không ai được báo. `mark_failed` có ghi `inbox_events` topic
`outbox.dead`, nhưng dòng đó chỉ có nghĩa khi ai đó đi đọc bảng ấy, và
không ai đọc.

Đây là kiểu tốn khách thật: hệ thống trông bình thường, chỉ có khách là
ngồi chờ mãi không thấy trả lời.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import sys
from datetime import datetime, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.omnichannel.outbox import (  # noqa: E402
    OutboxStatus,
    _keu_tin_chet,
    retry_decision,
)

NGUON = (ROOT / "agent" / "omnichannel" / "outbox.py").read_text(encoding="utf-8")


class _Job:
    """Job tối thiểu — `_keu_tin_chet` chỉ đọc bốn trường."""

    def __init__(self, attempts=8, kind="text"):
        self.id = "job-1"
        self.conversation_id = None
        self.kind = kind
        self.attempts = attempts


def chay(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------
#  Chết thì phải kêu
# ---------------------------------------------------------------

def test_tin_chet_bat_ra_canh_bao_NGHIEM_TRONG(monkeypatch):
    """Ca trung tâm: tái hiện đúng chuyện đã xảy ra ba lần."""
    su_kien: list[str] = []
    bao: list[tuple] = []

    async def log_event(kind, **kw):
        su_kien.append(kind)

    async def _bao(muc_do, tieu_de, chi_tiet, kq):
        bao.append((muc_do, tieu_de, chi_tiet))

    from agent import canh_gac, db

    monkeypatch.setattr(db, "log_event", log_event)
    monkeypatch.setattr(canh_gac, "_bao", _bao)

    chay(_keu_tin_chet(_Job(), "ConnectError: sidecar không phản hồi"))

    assert "outbox.tin_chet" in su_kien
    assert bao, "không bắn cảnh báo nào"
    assert bao[0][0] == "nghiem_trong"
    assert "khách" in bao[0][2].lower(), "phải nói rõ hậu quả với KHÁCH"
    assert "sidecar" in bao[0][2], "phải giữ lý do gốc để biết đường sửa"


def test_canh_bao_hong_KHONG_lam_chet_worker(monkeypatch):
    """
    Tin đã chết rồi; làm chết luôn cả hàng đợi là biến MỘT tin mất thành
    MỌI tin mất.
    """
    async def no(*a, **k):
        raise RuntimeError("webhook cảnh báo sập")

    from agent import canh_gac, db

    monkeypatch.setattr(db, "log_event", no)
    monkeypatch.setattr(canh_gac, "_bao", no)
    chay(_keu_tin_chet(_Job(), "loi gi do"))   # không được ném


# ---------------------------------------------------------------
#  Chỉ kêu khi CHẾT HẲN, không kêu mỗi lần thử lại
# ---------------------------------------------------------------

def test_con_thu_lai_thi_CHUA_chet():
    d = retry_decision(attempts=3, max_attempts=8,
                       now=datetime.now(timezone.utc))
    assert d.status is OutboxStatus.RETRY


def test_du_lan_thu_thi_chet():
    d = retry_decision(attempts=8, max_attempts=8,
                       now=datetime.now(timezone.utc))
    assert d.status is OutboxStatus.DEAD


def test_chi_keu_o_nhanh_DEAD():
    """
    Kêu ở mỗi lần thử lại thì tám cảnh báo cho một tin, và người trực tắt
    thông báo. Lúc đó lần sau có sự cố thật cũng không ai thấy.
    """
    for node in ast.walk(ast.parse(NGUON)):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "mark_failed"):
            continue
        than = ast.unparse(node)
        assert "_keu_tin_chet" in than, "mark_failed không kêu khi tin chết"
        assert "OutboxStatus.DEAD" in than, (
            "phải kêu CÓ ĐIỀU KIỆN, chỉ ở nhánh DEAD"
        )
        return
    raise AssertionError("không tìm thấy mark_failed")


def test_keu_SAU_khi_giao_dich_xong():
    """
    Cảnh báo là một lời gọi HTTP ra ngoài. Gọi khi đang giữ giao dịch là
    giữ khoá hàng trên `outbox_jobs` suốt thời gian webhook phản hồi — và
    webhook treo thì worker treo theo.
    """
    for node in ast.walk(ast.parse(NGUON)):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "mark_failed"):
            continue
        dong_tx = dong_keu = None
        for con in ast.walk(node):
            if isinstance(con, ast.AsyncWith) and dong_tx is None:
                dong_tx = con.lineno
            if (isinstance(con, ast.Call)
                    and "_keu_tin_chet" in ast.unparse(con.func)):
                dong_keu = con.lineno
        assert dong_keu, "không thấy lời gọi _keu_tin_chet"
        if dong_tx:
            assert dong_keu > dong_tx, "kêu bên trong giao dịch — giữ khoá quá lâu"
        return
    raise AssertionError("không tìm thấy mark_failed")


# ---------------------------------------------------------------
#  Phải NHÌN THẤY trên dashboard, không chỉ nằm trong nhật ký
# ---------------------------------------------------------------

def test_overview_dem_tin_chet():
    routes = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "tin_chet" in routes
    assert "status = 'dead'" in routes


def test_dem_tin_chet_KHONG_gioi_han_24_gio():
    """
    Cắt theo 24 giờ là để tin chết tự biến mất khỏi màn hình sau một đêm —
    đúng cái đã xảy ra suốt hơn một tuần.
    """
    routes = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    # Chỉ soi CHÍNH CÂU SQL, không soi vùng chữ quanh nó.
    #
    # Bản đầu quét 200 ký tự phía trước và bắt phải chữ "24 giờ" trong
    # đoạn chú thích GIẢI THÍCH vì sao không cắt theo 24 giờ. Test đỏ oan
    # — đúng cái bẫy đã gặp ba lần trong repo này.
    i = routes.find("FROM outbox_jobs WHERE status = 'dead'")
    assert i != -1, "không tìm thấy truy vấn đếm tin chết"
    cau = routes[i:i + 90]
    assert "since" not in cau and "created_at" not in cau, (
        f"truy vấn tin chết đang bị cắt theo thời gian: {cau[:80]}"
    )


def test_dashboard_hien_o_tin_chet():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "Tin KHÔNG gửi được" in js
    assert "o.tin_chet" in js


def test_o_chi_hien_khi_CO_tin_chet():
    """
    Một ô luôn hiện "0" là một ô người ta thôi nhìn sau tuần đầu. Ô chỉ
    xuất hiện khi có chuyện thì sự xuất hiện của nó chính là tín hiệu.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    i = js.find("Tin KHÔNG gửi được")
    truoc = js[max(0, i - 260):i]
    assert "o.tin_chet.so" in truoc and "?" in truoc, (
        "ô tin chết phải render CÓ ĐIỀU KIỆN"
    )


@pytest.mark.parametrize("tone", ["halt"])
def test_o_tin_chet_to_mau_canh_bao(tone):
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    i = js.find("Tin KHÔNG gửi được")
    assert tone in js[i:i + 200], "ô này phải đỏ, không phải màu trung tính"
