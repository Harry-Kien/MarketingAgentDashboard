"""Plugin dsh: danh sách công cụ nó phơi ra phải khớp máy chủ MCP thật.

VÌ SAO TEST NÀY TỒN TẠI
-----------------------
Plugin viết bằng TypeScript, nằm ngoài bộ test Python, và gọi máy chủ MCP
qua HTTP. Nghĩa là khi ai đó đổi tên một công cụ trong `agent/mcp_server.py`,
plugin KHÔNG hỏng lúc build — nó hỏng lúc chạy, ở máy người dùng, với thông
báo "tool not found" mà không ai ở đây nhìn thấy.

Nên hai bên đọc chung MỘT tệp kê khai `plugins/dsh-erp/cong-cu.json`, và test
này đối chiếu tệp đó với danh sách công cụ thật. Đổi tên bên Python mà quên
sửa kê khai thì đỏ ngay tại đây.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agent import mcp_server  # noqa: E402

KE_KHAI = ROOT / "plugins" / "dsh-erp" / "cong-cu.json"


def _kê_khai() -> dict:
    return json.loads(KE_KHAI.read_text(encoding="utf-8"))


def _ten_cong_cu_that() -> set[str]:
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_ke_khai_ton_tai():
    assert KE_KHAI.exists(), f"Thiếu {KE_KHAI.relative_to(ROOT)}"


def test_moi_cong_cu_khai_bao_deu_co_that_ben_mcp():
    thieu = sorted(set(_kê_khai()["cong_cu"]) - _ten_cong_cu_that())
    assert not thieu, (
        "Plugin dsh khai công cụ không tồn tại bên máy chủ MCP: "
        f"{thieu}. Đổi tên bên agent/mcp_server.py thì phải sửa cả "
        "plugins/dsh-erp/cong-cu.json — nếu không plugin hỏng ở máy người "
        "dùng chứ không hỏng ở đây."
    )


def test_plugin_khong_khai_cong_cu_ghi():
    # Plugin chạy trong dsh — một agent runtime khác, không đi qua năm lớp
    # lưới tuân thủ trong agent/core/agent.py. Nó chỉ được đọc.
    cam = {
        "soan_bai_dang", "dua_bai_vao_hang_doi", "tao_don_hang",
        "chuyen_nhan_vien", "tao_video", "dieu_chinh_kho",
    }
    lo = sorted(set(_kê_khai()["cong_cu"]) & cam)
    assert not lo, f"Plugin dsh chỉ được ĐỌC, đang khai công cụ ghi: {lo}"


def test_ke_khai_noi_ro_dau_la_phan_chua_kiem_chung():
    # Khuôn plugin Cordis của dsh chưa xác minh được (trang tài liệu là SPA,
    # README trả 404). Tệp kê khai phải nói thẳng điều đó, để người cài không
    # tưởng đây là mã đã chạy thật.
    d = _kê_khai()
    assert d.get("da_kiem_chung") is False
    assert d.get("can_xac_minh"), "Phải liệt kê rõ những gì còn phải kiểm"


def test_plugin_khong_nam_trong_requirements():
    # dsh đang ở developer preview. Không cho nó thành phụ thuộc bắt buộc
    # của hệ thống chạy thật.
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "deepseek-harness" not in req
    assert "dsh" not in req.split()


def test_ma_typescript_cua_plugin_van_dung():
    """Chạy `plugins/dsh-erp/kiem.mjs` qua node.

    BỎ QUA khi máy không có node — CI Python không nên đỏ vì thiếu runtime
    JavaScript. Nhưng máy nào có node thì mã TypeScript vẫn được canh, thay
    vì mục dần trong im lặng vì nằm ngoài pytest.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("Không có node — bỏ qua phần kiểm mã TypeScript")

    thu_muc = ROOT / "plugins" / "dsh-erp"
    # `encoding="utf-8"` tường minh, KHÔNG để `text=True` tự chọn.
    # Trên Windows bảng mã hệ thống ở đây là cp1258; `kiem.mjs` in tiếng
    # Việt, nên mặc định sẽ nổ UnicodeDecodeError trong luồng đọc — đúng
    # vào lúc test đỏ và người ta cần đọc thông báo nhất.
    kq = subprocess.run(
        [node, "kiem.mjs"],
        cwd=thu_muc,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert kq.returncode == 0, (
        f"kiem.mjs đỏ:\n{kq.stdout}\n{kq.stderr}"
    )
