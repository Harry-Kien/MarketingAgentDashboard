"""Danh sách công cụ MCP dành cho client ngoài phải khớp máy chủ thật.

VÌ SAO TEST NÀY TỒN TẠI
-----------------------
`plugins/dsh-erp/cong-cu.json` và `README.md` nói cho người cài biết nối vào
thì thấy công cụ gì. Đổi tên một công cụ trong `agent/mcp_server.py` mà quên
sửa hai file đó thì tài liệu nói dối, và người dùng chỉ phát hiện khi client
báo "tool not found" — ở máy họ, không ai ở đây nhìn thấy.

VÌ SAO KHÔNG CÒN TEST MÃ TYPESCRIPT
-----------------------------------
Bản đầu của thư mục này có một plugin tự viết (`src/index.ts`,
`src/mcp-client.ts`, `kiem.mjs`) và các test canh chúng. Đã xoá hết, vì đọc
gói `@deepseek-ai/dsh` thật thì thấy hai điều:

  1. `@deepseek-ai/dsh-mcp-client` là plugin MCP client CHÍNH THỨC. Plugin
     tự viết là thừa.
  2. Plugin Cordis của dsh được định nghĩa LÚC CHẠY qua `cordis_define` /
     `cordis_run`, không phải file tĩnh xuất `apply(ctx)` — mô hình mà bản
     đầu đoán sai.

Xoá mã thừa thì cũng xoá test canh mã đó. Giữ lại đúng phần còn canh một
thứ có thật: tài liệu không được trôi khỏi máy chủ MCP.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import mcp_server  # noqa: E402

THU_MUC = ROOT / "plugins" / "dsh-erp"
KE_KHAI = THU_MUC / "cong-cu.json"
DOC = THU_MUC / "README.md"


def _kê_khai() -> dict:
    return json.loads(KE_KHAI.read_text(encoding="utf-8"))


def _ten_cong_cu_that() -> set[str]:
    return {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_ke_khai_ton_tai():
    assert KE_KHAI.exists(), f"Thiếu {KE_KHAI.relative_to(ROOT)}"


def test_moi_cong_cu_khai_bao_deu_co_that_ben_mcp():
    thieu = sorted(set(_kê_khai()["cong_cu"]) - _ten_cong_cu_that())
    assert not thieu, (
        f"Kê khai nhắc công cụ không tồn tại bên máy chủ MCP: {thieu}. "
        "Đổi tên bên agent/mcp_server.py thì phải sửa cả cong-cu.json và "
        "README — nếu không tài liệu nói dối và người dùng chỉ phát hiện "
        "khi client báo 'tool not found'."
    )


def test_README_khong_nhac_cong_cu_khong_ton_tai():
    # README có bảng công cụ để người đọc biết nối vào thì thấy gì. Bảng đó
    # trôi khỏi máy chủ cũng là tài liệu nói dối.
    doc = DOC.read_text(encoding="utf-8")
    that = _ten_cong_cu_that()
    import re

    nhac = set(re.findall(r"`(\w+)`", doc)) & {
        t for t in re.findall(r"`(\w+)`", doc) if "_" in t
    }
    la = sorted(t for t in nhac
                if t not in that
                and t.islower()
                and t.startswith(("tra_", "goi_", "ton_", "suc_", "tim_",
                                  "soan_", "dua_", "kiem_", "hieu_", "danh_")))
    assert not la, f"README nhắc công cụ MCP không tồn tại: {la}"


def test_khong_khai_cong_cu_ghi():
    # dsh là một agent runtime KHÁC: không đi qua năm lớp lưới tuân thủ
    # trong agent/core/agent.py, không có trần chi phí, không có lưới chuyển
    # người. Cho nó quyền chốt đơn là giao chìa khoá cho một người lạ.
    cam = {"tao_don_hang", "chuyen_nhan_vien", "tao_video", "dieu_chinh_kho",
           "gui_tin_nhan", "dang_bai"}
    lo = sorted(set(_kê_khai()["cong_cu"]) & cam)
    assert not lo, f"Kê khai cho client ngoài chỉ được ĐỌC, thấy: {lo}"


def test_plugin_tu_viet_da_bi_xoa():
    """Không được viết lại plugin tự chế.

    `@deepseek-ai/dsh-mcp-client` làm đúng việc đó và là gói chính thức.
    Viết lại là dựng một bản sao kém hơn của thứ đã có, và phải nuôi nó.
    """
    for ten in ("src", "kiem.mjs", "package.json", "tsconfig.json"):
        assert not (THU_MUC / ten).exists(), (
            f"{ten} đã quay lại. dsh có plugin MCP client chính thức — "
            "xem phần đầu README của thư mục này."
        )


def test_README_chi_dung_goi_chinh_thuc():
    doc = DOC.read_text(encoding="utf-8")
    assert "@deepseek-ai/dsh-mcp-client" in doc, (
        "README phải chỉ người dùng tới plugin MCP client chính thức"
    )
    assert "release candidate" in doc.lower() or "rc" in doc, (
        "Phải nói rõ dsh đang ở bản rc — API còn đổi, đừng đặt vào đường "
        "chạy của khách thật"
    )


def test_plugin_khong_nam_trong_requirements():
    # dsh là công cụ NGƯỜI DÙNG chạy, không phải phụ thuộc của hệ thống.
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "deepseek-harness" not in req
    assert "dsh" not in req.split()
