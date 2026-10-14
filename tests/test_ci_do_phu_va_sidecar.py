"""
CI đo độ phủ, chạy test sidecar, và tự dò module — ba lỗ của đợt rà 14.10.2026.

1. Không đo độ phủ: ba nghìn test xanh không nói được phần nào của `agent/`
   chưa từng chạy. Ngưỡng `--cov-fail-under` là SÀN chống tụt.
2. Không chạy test Node của sidecar Zalo cá nhân — đường nhận phần lớn tin
   khách đo được.
3. Danh sách module import gõ tay: thiếu `zalo_personal` một thời gian dài.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI = (ROOT / ".github" / "workflows" / "kiem-thu.yml").read_text(encoding="utf-8")


def test_ci_do_phu_co_nguong():
    m = re.search(r"--cov-fail-under=(\d+)", CI)
    assert m, "CI phải có --cov-fail-under"
    assert int(m.group(1)) >= 50, "ngưỡng độ phủ không được hạ dưới mức đã đo"
    assert "--cov=agent" in CI


def test_pytest_cov_trong_requirements_dev():
    assert "pytest-cov" in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")


def test_ci_chay_test_sidecar():
    assert "zalo-personal-sidecar" in CI and "npm test" in CI


def test_ci_tu_do_module_khong_go_tay():
    assert "pkgutil.walk_packages" in CI
    assert '"agent.channels.zalo_personal",' not in CI, "còn danh sách gõ tay"


def test_ci_khong_ghi_so_ca_test():
    assert not re.search(r"khoảng \d{3,} ca", CI)
