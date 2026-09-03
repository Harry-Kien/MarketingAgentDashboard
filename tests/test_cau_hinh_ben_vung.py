"""
Cấu hình agent phải sống qua khởi động lại.

LỖI THẬT, ĐO ĐƯỢC (03.09.2026)

    POST /api/runtime {"confidence_floor": 0.9, "mode": "auto"}
    -> 0.9 / auto           đúng như vừa đặt
    khởi động lại máy chủ
    -> 0.55 / assist        về mặc định, KHÔNG một dòng cảnh báo nào

Tầng API vẫn gọi `db.log_event("runtime.update")`, nên nhật ký kiểm toán
ghi rằng người ta ĐÃ ĐỔI — trong khi giá trị không ở đâu cả. Nhật ký nói
một đằng, hệ thống chạy một nẻo, và không có gì đối chiếu hai thứ.

Ca quan trọng nhất tệp này: `test_nap_lai_duoc_gia_tri_da_luu`.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import runtime  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


class BangGia:
    """CSDL giả: giữ đúng những gì `luu()` ghi, trả lại cho `nap()`."""

    def __init__(self):
        self.dong: dict[str, str] = {}
        self.su_kien: list[tuple] = []

    async def execute(self, sql, *args):
        if "DELETE FROM cau_hinh_agent" in sql:
            self.dong.clear()
            return "DELETE 1"
        if "INSERT INTO cau_hinh_agent" in sql:
            self.dong[args[0]] = args[1]
            return "INSERT 0 1"
        return "OK"

    async def fetch(self, sql, *args):
        if "FROM cau_hinh_agent" in sql:
            return [{"khoa": k, "gia_tri": v} for k, v in self.dong.items()]
        return []

    async def log_event(self, kind, **kw):
        self.su_kien.append((kind, kw))


@pytest.fixture
def bang(monkeypatch):
    b = BangGia()
    monkeypatch.setattr(runtime.db, "execute", b.execute)
    monkeypatch.setattr(runtime.db, "fetch", b.fetch)
    monkeypatch.setattr(runtime.db, "log_event", b.log_event)
    goc = dict(runtime.STATE)
    yield b
    runtime.STATE.clear()
    runtime.STATE.update(goc)


# ---------------------------------------------------------------
#  Khẳng định trung tâm
# ---------------------------------------------------------------

def test_nap_lai_duoc_gia_tri_da_luu(bang):
    """
    Mô phỏng đúng chuỗi đã hỏng: đặt giá trị, "khởi động lại" (đưa STATE về
    mặc định), rồi nạp lên.
    """
    chay(runtime.luu({"confidence_floor": 0.9, "mode": "auto"}))
    assert runtime.STATE["confidence_floor"] == 0.9

    # Khởi động lại: tiến trình mới, STATE về mặc định.
    runtime.STATE.update(runtime.MAC_DINH)
    assert runtime.STATE["confidence_floor"] == runtime.MAC_DINH["confidence_floor"]

    chay(runtime.nap())
    assert runtime.STATE["confidence_floor"] == 0.9, (
        "cấu hình không sống qua khởi động lại — đúng lỗi đã đo được"
    )
    assert runtime.STATE["mode"] == "auto"


def test_giu_dung_KIEU_qua_mot_vong_luu_nap(bang):
    """
    Lưu hết thành TEXT thì lúc đọc lên phải đoán kiểu, và `bool("false")`
    trong Python là True — công tắc ngắt bật lại một mình.
    """
    chay(runtime.luu({"enabled": False, "confidence_floor": 0.75,
                      "mode": "auto", "max_cost_per_conversation": 0.4}))
    runtime.STATE.update(runtime.MAC_DINH)
    chay(runtime.nap())

    assert runtime.STATE["enabled"] is False
    assert isinstance(runtime.STATE["confidence_floor"], float)
    assert runtime.STATE["confidence_floor"] == 0.75
    assert isinstance(runtime.STATE["max_cost_per_conversation"], float)
    assert runtime.STATE["mode"] == "auto"


def test_cong_tac_ngat_song_qua_khoi_dong_lai(bang):
    """
    Ca đáng sợ nhất trong họ này: người vận hành TẮT agent vì nó đang trả
    lời sai, máy chủ khởi động lại, agent bật lại một mình và tiếp tục trả
    lời sai — trong khi người tắt tin là mình đã chặn được.
    """
    chay(runtime.luu({"enabled": False}))
    runtime.STATE.update(runtime.MAC_DINH)
    chay(runtime.nap())
    assert runtime.enabled() is False


# ---------------------------------------------------------------
#  Ghi CSDL rồi mới đổi bộ nhớ
# ---------------------------------------------------------------

def test_ghi_hong_thi_KHONG_doi_bo_nho(bang, monkeypatch):
    """
    Đổi bộ nhớ trước rồi ghi hỏng thì tiến trình chạy giá trị mới trong khi
    CSDL giữ giá trị cũ — và lần khởi động kế tiếp lặng lẽ quay về cái cũ,
    đúng lỗi mà cả tệp này sinh ra để sửa.
    """
    truoc = runtime.STATE["confidence_floor"]

    async def no(*a, **k):
        raise RuntimeError("CSDL sập")

    monkeypatch.setattr(runtime.db, "execute", no)
    with pytest.raises(RuntimeError):
        chay(runtime.luu({"confidence_floor": 0.99}))
    assert runtime.STATE["confidence_floor"] == truoc


# ---------------------------------------------------------------
#  Đường lui khi chưa có CSDL
# ---------------------------------------------------------------

def test_chua_migrate_thi_van_khoi_dong_duoc(monkeypatch):
    """
    Máy vừa clone chưa chạy migration phải khởi động được. Một bảng chưa có
    không phải lý do để agent không chạy.
    """
    async def no(*a, **k):
        raise RuntimeError("chưa có bảng")

    monkeypatch.setattr(runtime.db, "fetch", no)
    ra = chay(runtime.nap())
    assert ra["confidence_floor"] == runtime.MAC_DINH["confidence_floor"]


def test_khoa_la_trong_csdl_bi_bo_qua(bang):
    """
    Khoá đã gỡ khỏi mã nhưng còn dòng trong bảng không được nhét vào STATE
    — nó sẽ nằm đó mãi mà không ai đọc, và làm `liet_ke` hiện một thiết lập
    không điều khiển gì cả.
    """
    bang.dong["khoa_da_bo"] = json.dumps("gi do")
    chay(runtime.nap())
    assert "khoa_da_bo" not in runtime.STATE


def test_zalo_account_id_KHONG_ben_vung():
    """
    Con trỏ tới một tài khoản kênh có thể bị xoá giữa hai lần khởi động.
    Nạp lên một id đã chết thì agent gửi tin vào hư không — im lặng.
    """
    assert "zalo_account_id" not in runtime.KHOA_BEN_VUNG


def test_moi_khoa_ben_vung_deu_co_that():
    """`KHOA_BEN_VUNG` chứa tên ma thì `luu()` im lặng bỏ qua giá trị đó."""
    assert set(runtime.KHOA_BEN_VUNG) <= set(runtime.STATE)


def test_mac_dinh_duoc_chup_truoc_khi_nap(bang):
    """
    `MAC_DINH` phải là giá trị của `.env`, không phải giá trị đang chạy.
    Lẫn hai thứ thì nút "quay về mặc định" quay về đúng chỗ vừa rời đi.
    """
    goc = dict(runtime.MAC_DINH)
    chay(runtime.luu({"confidence_floor": 0.91}))
    chay(runtime.nap())
    assert runtime.MAC_DINH == goc


def test_dat_lai_mac_dinh_xoa_ca_trong_csdl(bang):
    """
    Chỉ đặt lại bộ nhớ mà không xoá bảng thì lần khởi động sau giá trị cũ
    quay lại — nút "quay về mặc định" trở thành nút "quay về tạm thời".
    """
    chay(runtime.luu({"confidence_floor": 0.9, "mode": "auto"}))
    chay(runtime.dat_lai_mac_dinh())
    assert bang.dong == {}
    chay(runtime.nap())
    assert runtime.STATE["confidence_floor"] == runtime.MAC_DINH["confidence_floor"]
    assert runtime.STATE["mode"] == runtime.MAC_DINH["mode"]


# ---------------------------------------------------------------
#  Đường API phải dùng `luu`, không dùng `update`
# ---------------------------------------------------------------

def test_endpoint_runtime_ghi_xuong_csdl():
    """
    `update()` chỉ đổi bộ nhớ. Endpoint quay lại dùng nó là lỗi cũ trở lại
    — nút trên dashboard vẫn bấm được, vẫn hiện giá trị mới, và vẫn mất sau
    lần khởi động kế tiếp.
    """
    import ast

    cay = ast.parse((ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8"))
    for node in ast.walk(cay):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "set_runtime"):
            continue
        nguon = ast.unparse(node)
        assert "runtime.luu" in nguon, "endpoint /runtime không ghi xuống CSDL"
        assert "runtime.update(" not in nguon, (
            "endpoint /runtime còn gọi update() — chỉ đổi bộ nhớ"
        )
        return
    raise AssertionError("không tìm thấy set_runtime trong routes.py")


def test_main_nap_cau_hinh_luc_khoi_dong():
    """Không nạp thì bảng có dữ liệu cũng vô nghĩa."""
    import ast

    cay = ast.parse((ROOT / "agent" / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(cay):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            assert "runtime.nap()" in ast.unparse(node), (
                "lifespan không gọi runtime.nap() — cấu hình đã lưu không "
                "bao giờ được đọc lên"
            )
            return
    raise AssertionError("không tìm thấy lifespan")
