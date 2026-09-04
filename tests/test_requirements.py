"""
Kiểm thử requirements.txt. Không gọi API, không cần CSDL.

VÌ SAO
------
CI đỏ liên tục từ 01/09 đến 04/09 — hơn bốn mươi lần chạy — vì đúng một
dòng: `openpyxl` được import trong ba script và một test, nhưng chưa bao
giờ được khai trong `requirements.txt`. Máy phát triển có sẵn nó (cài tay
lúc nào đó), nên `pytest` xanh; máy vừa clone thì `pytest` chết ngay ở
bước thu thập, và mọi test khác không được chạy.

Đây là kiểu hỏng khó nhìn nhất trong repo: mã đúng, test đúng, chỉ có
danh sách thư viện là nói dối — và nó chỉ nói dối trên máy KHÁC.

Phép kiểm dưới đây so từng `import` bên thứ ba trong `agent/`, `scripts/`,
`tests/` với tên gói trong requirements. Chỉ tính import trực tiếp: thư
viện đi kèm thư viện khác (starlette theo fastapi) vẫn phải khai nếu mã
import thẳng — "cái gì mình import thì mình khai", như chú thích về
`websockets` trong requirements.txt đã nói.
"""
from __future__ import annotations

import ast
import re
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Gói nội bộ của repo, và các cây không phải mã Python chạy trên máy chủ.
NOI_BO = {"agent", "scripts", "tests", "conftest", "connectors", "plugins"}


def _ten_goi_da_khai() -> set[str]:
    ra: set[str] = set()
    for tep in ("requirements.txt", "requirements-dev.txt"):
        for dong in (ROOT / tep).read_text(encoding="utf-8").splitlines():
            dong = dong.strip()
            if not dong or dong.startswith("#"):
                continue
            ra.add(re.split(r"[=<>\[ ;]", dong)[0].lower().replace("_", "-"))
    return ra


def _import_ben_thu_ba() -> dict[str, set[str]]:
    """Tên module cấp cao nhất -> các file import nó."""
    ket: dict[str, set[str]] = {}
    chuan = set(sys.stdlib_module_names) | NOI_BO
    for thu_muc in ("agent", "scripts", "tests"):
        for p in (ROOT / thu_muc).rglob("*.py"):
            cay = ast.parse(p.read_text(encoding="utf-8"))
            for nut in ast.walk(cay):
                if isinstance(nut, ast.Import):
                    ten = [a.name for a in nut.names]
                elif isinstance(nut, ast.ImportFrom) and nut.module and nut.level == 0:
                    ten = [nut.module]
                else:
                    continue
                for t in ten:
                    goc = t.split(".")[0]
                    if goc not in chuan:
                        ket.setdefault(goc, set()).add(p.relative_to(ROOT).as_posix())
    return ket


def test_moi_import_ben_thu_ba_deu_co_trong_requirements():
    """
    So theo TÊN GÓI PHÂN PHỐI (pyyaml), không phải tên module (yaml) — hai
    tên này khác nhau ở khá nhiều thư viện, và so nhầm là xanh giả.
    """
    da_khai = _ten_goi_da_khai()
    phan_phoi = packages_distributions()
    thieu = []
    for module, tep in sorted(_import_ben_thu_ba().items()):
        goi = [g.lower().replace("_", "-") for g in phan_phoi.get(module, [])]
        if not goi:
            # Import được (test khác đã chạy tới đây) nhưng không tra ra gói:
            # thư viện cài kiểu lạ. Không đoán — báo để người xem.
            thieu.append(f"{module} (không tra được gói) <- {sorted(tep)[:2]}")
        elif not any(g in da_khai for g in goi):
            thieu.append(f"{module} (gói {goi}) <- {sorted(tep)[:2]}")
    assert not thieu, (
        "import mà không khai trong requirements — máy vừa clone sẽ chết ở "
        "bước thu thập test:\n  " + "\n  ".join(thieu)
    )
