"""
Công cụ xem trước không bao giờ được bật một bản app đầy đủ.

Đo được 14.10.2026: `.claude/launch.json` có cấu hình `dashboard` = uvicorn
đầy đủ trên cổng 8000. Một lần gọi công cụ xem trước, app production của
người canh mất cổng, và trong lúc ấy hai bộ vòng nền (outbox, sao lưu) chạy
song song — hai outbox là tin trùng gửi cho khách.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_launch_json_khong_co_cau_hinh_production():
    cfg = json.loads((ROOT / ".claude" / "launch.json").read_text(encoding="utf-8"))
    for c in cfg["configurations"]:
        assert c["port"] != 8000, f"{c['name']}: cổng 8000 là của production"
        assert "agent.main:app" not in " ".join(c.get("runtimeArgs", [])), (
            f"{c['name']}: chạy thẳng uvicorn là bản đầy đủ — dùng scripts.xem_truoc")


def test_xem_truoc_tat_vong_nen_va_dung_csdl_rieng(monkeypatch):
    from scripts import xem_truoc

    for k in ("VAI_TRO_TIEN_TRINH", "DATABASE_URL", "ZALOCRM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5433/marketing_agent")
    xem_truoc.dung_moi_truong()
    assert os.environ["VAI_TRO_TIEN_TRINH"] == "api"
    assert os.environ["DATABASE_URL"].endswith("/kt_xem_truoc")
    assert os.environ["ZALOCRM_API_KEY"] == ""

    from agent import main
    from agent.config import Settings
    assert not main.nen_chay_vong_nen(Settings(vai_tro_tien_trinh="api"))
