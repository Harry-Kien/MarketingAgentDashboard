"""
Image Docker chỉ được mang những gì git theo dõi trong data/.

24.10.2026: `.dockerignore` là danh sách CẤM, chặn `data/backups/` trong khi
sao lưu thật nằm ở `data/backup/` — dựng image trên máy đang chạy là đóng
gói luôn bản sao lưu CSDL khách hàng vào image. Nay data/ là danh sách CHO
PHÉP. Canh hai chiều:
  · mục git theo dõi mà không được cho phép -> image thiếu dữ liệu mặc định
    (entrypoint chép sang volume), app lên nhưng thiếu — hỏng im lặng;
  · mục được cho phép mà git bỏ qua -> dữ liệu riêng của máy lọt vào image.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DONG = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()


def _cho_phep() -> set[str]:
    return {d[len("!data/"):].strip("/") for d in DONG if d.startswith("!data/")}


def test_data_mac_dinh_bi_chan_het():
    assert "data/*" in DONG, "data/ phải chặn mặc định — danh sách cho phép, không phải cấm"


def test_moi_muc_git_theo_doi_trong_data_deu_duoc_cho_phep():
    tep = subprocess.run(["git", "ls-files", "data"], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout.split()
    assert tep, "git ls-files data rỗng — test chạy sai chỗ?"
    muc = {Path(t).parts[1] for t in tep}
    thieu = muc - _cho_phep()
    assert not thieu, f"git theo dõi nhưng .dockerignore chặn (image sẽ thiếu): {sorted(thieu)}"


def test_khong_cho_phep_thu_git_bo_qua():
    lot = []
    for m in _cho_phep():
        r = subprocess.run(["git", "check-ignore", "-q", f"data/{m}"], cwd=ROOT)
        if r.returncode == 0:
            lot.append(m)
    assert not lot, f".dockerignore cho phép thứ git bỏ qua (dữ liệu riêng lọt vào image): {lot}"


def test_ket_qua_eval_va_bi_mat_van_bi_chan():
    for mau in ("data/eval/ket-qua-*.json", "data/eval/golden.jsonl", ".env", "*.log"):
        assert mau in DONG, mau
