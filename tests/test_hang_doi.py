"""
Kiểm thử hàng đợi trực. Không gọi API, không cần CSDL.

VÌ SAO CÓ FILE NÀY
------------------
Cả hệ thống được xây quanh một ý: agent biết dừng đúng lúc và giao lại cho
người. Năm lớp lưới trong `agent/core/agent.py` tồn tại chỉ để đảm bảo việc
đó xảy ra.

Nhưng cả năm lớp đó đổ về ĐÚNG MỘT khung màn hình. Khung đó xếp sai thứ tự
hoặc cắt sớm thì toàn bộ công sức phía trước rò hết ra ngoài ở bước cuối —
agent chuyển người hoàn hảo, và không ai nhìn thấy.

Chuyện này đã xảy ra một lần rồi, ghi trong chú thích ở `routes.py`: khung
trực lọc thiếu trạng thái, "2 cái hiện, 7 cái không — bảy khách ngồi đợi mà
không ai thấy". Test ở đây canh để nó không xảy ra lần thứ hai bằng một
nguyên nhân khác.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api import routes  # noqa: E402
from agent.config import settings  # noqa: E402


def _dong(phut_truoc: int, status: str = "escalated") -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "channel": "chatwoot",
        "nen_tang": "facebookpage",
        "customer_name": "Khách",
        "status": status,
        "outcome": None,
        "cost_usd": 0.01,
        "msg_count": 3,
        "updated_at": datetime.now(timezone.utc) - timedelta(minutes=phut_truoc),
        "last_message": "cho em hỏi",
    }


def _goi(monkeypatch, status, rows, limit=60):
    """Gọi endpoint với CSDL giả, trả về (SQL đã dựng, kết quả)."""
    da_chay = {}

    async def fetch_gia(sql, *args):
        da_chay["sql"] = sql
        return rows

    monkeypatch.setattr(routes.db, "fetch", fetch_gia)
    monkeypatch.setattr(routes.runtime, "is_busy", lambda _: False)
    kq = asyncio.run(routes.list_conversations(status=status, limit=limit))
    return da_chay["sql"], kq


# =====================================================================
#  Thứ tự: hàng đợi xếp NGƯỢC với mọi màn hình khác
# =====================================================================

def test_hang_doi_xep_cho_lau_nhat_len_dau(monkeypatch):
    """
    Mọi màn hình khác là dòng thời gian — mới nhất lên đầu. Khung này không
    phải dòng thời gian, nó là hàng đợi: ai đợi lâu nhất phải được phục vụ
    trước, nếu không thì người đợi lâu nhất bị đẩy xuống đáy và rơi khỏi
    danh sách khi đông khách.
    """
    sql, _ = _goi(monkeypatch, "can_nguoi", [_dong(5)])
    assert "ORDER BY c.updated_at ASC" in sql


def test_man_hinh_khac_van_moi_nhat_truoc(monkeypatch):
    """Chỉ hàng đợi mới đảo. Đảo cả dòng thời gian là làm hỏng chỗ khác."""
    for st in (None, "all", "auto"):
        sql, _ = _goi(monkeypatch, st, [_dong(5)])
        assert "ORDER BY c.updated_at DESC" in sql, st


def test_hang_doi_gom_ca_assist_lan_escalated(monkeypatch):
    """
    Hai trạng thái khác nhau nhưng CÙNG một việc phải làm: một người phải
    vào trả lời khách. Lọc thiếu một cái là lỗi đã từng xảy ra thật.
    """
    sql, _ = _goi(monkeypatch, "can_nguoi", [_dong(5)])
    assert "'assist'" in sql and "'escalated'" in sql


# =====================================================================
#  Thời gian chờ
# =====================================================================

def test_co_tra_ve_da_cho_bao_lau(monkeypatch):
    _, kq = _goi(monkeypatch, "can_nguoi", [_dong(47)])
    assert kq[0]["cho_bao_lau_phut"] in (46, 47, 48)


def test_thoi_gian_cho_khong_bao_gio_am(monkeypatch):
    """
    Đồng hồ máy chủ lệch về sau là `updated_at` nằm ở tương lai. Một hàng
    đợi hiện "chờ -3 phút" thì người trực ngừng tin cả cột số đó.
    """
    _, kq = _goi(monkeypatch, "can_nguoi", [_dong(-10)])
    assert kq[0]["cho_bao_lau_phut"] == 0


def test_tinh_o_may_chu_khong_de_trinh_duyet_tu_tru():
    """Máy của người trực có thể lệch giờ. Một con số chờ sai còn tệ hơn
    không có con số nào."""
    src = inspect.getsource(routes.list_conversations)
    assert "cho_bao_lau_phut" in src
    assert "datetime.now(timezone.utc)" in src


# =====================================================================
#  Không giấu ai
# =====================================================================

def test_dashboard_khong_cat_hang_doi_o_muc_thap():
    """
    Trước đây khung trực gọi `limit=12`. Hơn 12 khách chờ thì phần dư biến
    mất — và sau khi đảo thứ tự, phần biến mất chính là người mới nhắn.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "status=can_nguoi&limit=12" not in js, "hàng đợi vẫn đang cắt ở 12"
    assert "status=can_nguoi&limit=200" in js


def test_nguong_mau_tren_dashboard_khop_voi_nguong_canh_gac():
    """
    Con số người trực NHÌN THẤY chuyển màu và con số canh gác NHẮN cho họ
    phải là một. Lệch nhau thì hệ thống báo động vì một chuyện mà màn hình
    vẫn hiện bình thường, và người ta tin màn hình.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert f"CHO_LAU_PHUT = {settings.cho_nguoi_toi_da_phut}" in js
