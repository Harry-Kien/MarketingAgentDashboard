# Giai đoạn 0 — Khóa luận và bảo mật: kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gỡ mọi chỗ hội đồng phản biện bắt được (mâu thuẫn số liệu, thiếu đối chứng, thống kê sai) và vá bốn lỗ bảo mật đã xác minh — trước khi thêm bất kỳ tính năng nào.

**Architecture:** Không đổi kiến trúc. Thêm một công tắc *chỉ-dành-cho-đo* vào `agent/core/agent.py` (ContextVar, không đọc từ env/API), để `scripts/eval.py` chạy được thí nghiệm tắt từng lớp lưới. Kết quả eval mang thêm khối `meta` (commit, mô hình, lưới tắt) để `scripts/sinh_thuc_nghiem.py` nhóm đúng các lần chạy và tính khoảng tin cậy.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, pytest, pytest-cov, GitHub Actions.

**Spec:** `docs/superpowers/plans/2026-10-14-lo-trinh-saas-va-khoa-luan.md` (Giai đoạn 0)

## Global Constraints

- Mã, chú thích, tài liệu: tiếng Việt. Chú thích nói VÌ SAO.
- Mỗi ràng buộc mới có test canh.
- Không gõ số vào tài liệu sinh tự động; sửa bộ sinh rồi chạy `--ghi`.
- Không chạy `scripts.eval*` (tốn tiền) khi chưa có đồng ý của chủ dự án.
- Làm trong worktree `.claude/worktrees/giai-doan-0`, nhánh `giai-doan-0`;
  gộp về `main` bằng `git push . giai-doan-0:main` khi xong và xanh hết.
- Trước khi báo xong: `python -m pytest -q` xanh (Postgres bật), `ruff check .` sạch.

---

### Task 1: Bốn lỗ bảo mật nhỏ + vệ sinh repo

**Files:**
- Modify: `agent/main.py:754` (so token MCP), `agent/main.py:98-100` (Chatwoot hỏng-đóng)
- Modify: `agent/config.py:300` (cookie Secure tự bật khi URL công khai là https)
- Modify: `docker-compose.yml:141-167` (bí mật Langfuse ra `.env`), `.env.example`
- Modify: `.gitignore` (thêm `.claude/worktrees/`), `agent/nhat_ky.py:10-11` (chuỗi token giả)
- Untrack: `data/sidecar.log`, `data/sidecar.err.log`
- Test: `tests/test_bao_mat_giai_doan_0.py`

- [ ] **Step 1: Viết test hỏng trước**

```python
# tests/test_bao_mat_giai_doan_0.py
"""Bốn lỗ tìm ra ở đợt rà 14.10.2026 — mỗi lỗ một test canh."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_chatwoot_thieu_secret_la_tu_choi(monkeypatch):
    from agent import main
    monkeypatch.setattr(main.settings, "chatwoot_webhook_secret", "")
    assert main._chatwoot_signature_hop_le(b"{}", {}) is False


def test_token_mcp_so_hang_thoi_gian():
    src = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert '== f"Bearer {khoa}"' not in src
    assert "compare_digest" in src.split('if duong.startswith("/mcp")')[1][:900]


def test_cookie_tu_bat_secure_khi_https():
    from agent.config import Settings
    s = Settings(public_base_url="https://cskh.example.vn", cookie_bao_mat=False)
    assert s.cookie_can_secure is True
    s2 = Settings(public_base_url="http://host.docker.internal:8000", cookie_bao_mat=False)
    assert s2.cookie_can_secure is False


def test_compose_khong_chua_bi_mat_cung():
    yml = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for khoa in ("NEXTAUTH_SECRET:", "SALT:", "ENCRYPTION_KEY:"):
        dong = next(d for d in yml.splitlines() if d.strip().startswith(khoa))
        assert "${" in dong, f"{khoa} còn giá trị gõ cứng"


def test_worktree_bi_ignore():
    assert ".claude/worktrees/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
```

(Chữ ký thật của `_chatwoot_signature_hop_le` đọc ở `agent/main.py:~85` trước khi viết; chỉnh lời gọi cho khớp.)

- [ ] **Step 2:** `python -m pytest tests/test_bao_mat_giai_doan_0.py -q` → FAIL cả 5.
- [ ] **Step 3: Sửa**
  - `main.py`: `cho_phep = secrets.compare_digest(request.headers.get("authorization", "").encode(), f"Bearer {khoa}".encode())`
  - `_chatwoot_signature_hop_le`: `if not secret: return False` + chú thích vì sao hỏng-đóng.
  - `config.py`: thêm property `cookie_can_secure = self.cookie_bao_mat or self.public_base_url.startswith("https://")`; `routes.py` dùng `settings.cookie_can_secure` ở mọi `set_cookie`/`delete_cookie`.
  - Compose: `NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET:-}` (tương tự SALT, ENCRYPTION_KEY, mật khẩu langfuse_db); thêm bốn biến trống vào `.env.example` kèm lệnh `python -m scripts.sinh_token`.
  - `.gitignore`: `.claude/worktrees/`; `git rm --cached data/sidecar.log data/sidecar.err.log`.
  - `nhat_ky.py`: thay tiền tố token/App ID thật trong chú thích bằng `EAAxxxx…`/`1234567890`.
- [ ] **Step 4:** test file xanh; `docker compose config -q` không lỗi.
- [ ] **Step 5:** commit "Bốn lỗ bảo mật từ đợt rà 14.10: MCP so hằng thời gian, Chatwoot hỏng-đóng, cookie Secure theo https, bí mật compose ra .env"

### Task 2: Phiên lưu dạng băm

**Files:**
- Modify: `agent/core/xac_thuc.py:307-370`, `agent/api/routes.py` (chỗ đọc cookie → `doc_phien`, không đổi)
- Modify: 9 test chèn thẳng vào `phien` (`grep -rln "INTO phien" tests`)
- Test: `tests/test_phien_luu_bam.py`

- [ ] **Step 1: Test hỏng**

```python
# tests/test_phien_luu_bam.py
"""Lộ bản sao lưu CSDL không được thành chiếm phiên."""
import pytest
from agent.core import xac_thuc


def test_bam_token_tat_dinh_va_khac_goc():
    t = "abc"
    assert xac_thuc.bam_token(t) == xac_thuc.bam_token(t)
    assert xac_thuc.bam_token(t) != t
    assert len(xac_thuc.bam_token(t)) == 64


@pytest.mark.asyncio
async def test_bang_phien_khong_chua_token_goc(db_that, nguoi_dung_mau):
    token = await xac_thuc.dang_nhap(nguoi_dung_mau.ten, nguoi_dung_mau.mat_khau)
    hang = await db_that.fetch("SELECT token FROM phien")
    assert all(h["token"] != token for h in hang)
    assert await xac_thuc.doc_phien(token) is not None
```

(Tên fixture Postgres thật đọc ở `tests/conftest.py` trước khi viết; dùng đúng fixture đang có.)

- [ ] **Step 2:** chạy → FAIL (`bam_token` chưa có).
- [ ] **Step 3:** thêm `def bam_token(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()`; INSERT lưu `bam_token(token)`, `doc_phien`/`dang_xuat` so `p.token = bam_token(token)`. Không cần migration: phiên cũ (token gốc) không còn khớp → người dùng đăng nhập lại một lần; `don_phien_het_han` dọn dần. Chú thích ghi rõ điều này.
- [ ] **Step 4:** sửa 9 test: giá trị chèn vào `phien.token` bọc `xac_thuc.bam_token(...)`; cookie vẫn là token gốc.
- [ ] **Step 5:** `pytest tests/test_phien_luu_bam.py tests/test_xac_thuc.py tests/test_quyen_phien_that.py tests/test_api_vai_tro.py -q` xanh; commit.

### Task 3: Kết quả eval mang `meta` + công tắc tắt lưới chỉ-dành-cho-đo

**Files:**
- Modify: `agent/core/agent.py` (ContextVar `_LUOI_TAT`, sáu điểm kiểm)
- Modify: `scripts/eval.py` (cờ `--tat-luoi`, `--chi-prompt`, `--lap N`, khối `meta`)
- Test: `tests/test_cong_tac_tat_luoi.py`

- [ ] **Step 1: Test hỏng**

```python
# tests/test_cong_tac_tat_luoi.py
"""
Công tắc tắt lưới tồn tại để ĐO luận điểm trung tâm (ablation), và chỉ để đo.
Ràng buộc: mặc định rỗng; chỉ scripts/eval*.py được gọi; mã lạ → nổ.
"""
from pathlib import Path
import pytest
from agent.core import agent as A

ROOT = Path(__file__).resolve().parent.parent


def test_mac_dinh_khong_tat_luoi_nao():
    assert A.luoi_dang_tat() == frozenset()


def test_ma_la_thi_no():
    with pytest.raises(KeyError):
        with A.tat_luoi_de_do({"khong_ton_tai"}):
            pass


def test_ra_khoi_khoi_thi_bat_lai():
    with A.tat_luoi_de_do({"injection"}):
        assert A.luoi_dang_tat() == {"injection"}
    assert A.luoi_dang_tat() == frozenset()


def test_chi_bo_do_duoc_goi():
    goi = [p for p in ROOT.rglob("*.py")
           if "tat_luoi_de_do(" in p.read_text(encoding="utf-8", errors="ignore")
           and ".venv" not in p.parts and ".claude" not in p.parts]
    cho_phep = {"agent.py", "eval.py", "eval_nhieu_luot.py", "test_cong_tac_tat_luoi.py"}
    assert {p.name for p in goi} <= cho_phep, goi


@pytest.mark.parametrize("ma", sorted(A.LOP_LUOI))
def test_moi_lop_luoi_deu_tat_duoc(ma):
    src = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    assert f'_bat("{ma}")' in src, f"lưới {ma} không đi qua cổng _bat()"
```

- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3:** trong `agent.py` ngay dưới `so_lop_luoi()`:

```python
_LUOI_TAT: ContextVar[frozenset[str]] = ContextVar("_LUOI_TAT", default=frozenset())


def luoi_dang_tat() -> frozenset[str]:
    return _LUOI_TAT.get()


@contextmanager
def tat_luoi_de_do(ma: set[str]):
    """CHỈ cho scripts/eval*. Xem tests/test_cong_tac_tat_luoi.py."""
    la = set(ma) - set(LOP_LUOI)
    if la:
        raise KeyError(f"không có lớp lưới {sorted(la)}")
    moc = _LUOI_TAT.set(frozenset(ma))
    try:
        yield
    finally:
        _LUOI_TAT.reset(moc)


def _bat(ma: str) -> bool:
    return ma not in _LUOI_TAT.get()
```

  Rồi bọc sáu điểm kiểm: `if spent >= hs.tran_chi_phi and _bat("tran_hoi_thoai")`, `if co_tan_cong and _bat("injection")`, `if confidence < … and not co_du_lieu and _bat("tin_cay_thap")`, `if not escalate and _bat("bat_buoc_chuyen")`, `if not escalate and _bat("hua_khong_goi") and _promises_handoff(...)`, `if not escalate and _bat("chan_doan_y_te")`. Chú thích: ContextVar chứ không env/config — không đường nào từ webhook hay dashboard chạm tới được.
- [ ] **Step 4:** `eval.py`: argparse với `nhom` (vị trí, tuỳ chọn), `--tat-luoi a,b`, `--chi-prompt` (= tắt cả sáu), `--lap N` (mặc định 1). Mỗi lần lặp ghi một file kết quả có thêm:

```python
"meta": {
    "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
    "ban_sua_do": bool(subprocess.run(["git", "status", "--porcelain", "agent"], capture_output=True, text=True).stdout.strip()),
    "mo_hinh": settings.<tên trường model đang dùng — đọc agent/config.py>,
    "luoi_tat": sorted(tat),
    "bo_vang_sha": hashlib.sha256(GOLDEN.read_bytes()).hexdigest()[:12],
    "lan": k, "tong_lan": N,
}
```

  và bọc vòng chạy ca bằng `with tat_luoi_de_do(tat):`.
- [ ] **Step 5:** test xanh + `pytest tests -q -k "agent or guard or luoi"` xanh; commit.

### Task 4: Thống kê đúng trong chương thực nghiệm

**Files:**
- Modify: `scripts/sinh_thuc_nghiem.py`
- Modify: `tests/test_thuc_nghiem.py`

- [ ] **Step 1: Test hỏng**

```python
def test_wilson_dung_so_sach():
    from scripts.sinh_thuc_nghiem import wilson
    lo, hi = wilson(0, 56)
    assert lo == 0.0 and 0.06 < hi < 0.07       # 0/56 → cận trên ≈ 6,4%
    lo, hi = wilson(28, 56)
    assert 0.37 < lo < 0.38 and 0.62 < hi < 0.63


def test_khong_con_ca_minh_hoa_go_cung():
    src = Path("scripts/sinh_thuc_nghiem.py").read_text(encoding="utf-8")
    assert "TUAN_THU_14" not in src and "G38" not in src


def test_nhom_lan_chay_theo_cau_hinh():
    from scripts.sinh_thuc_nghiem import nhom_theo_cau_hinh
    a = {"meta": {"commit": "x", "luoi_tat": []}}
    b = {"meta": {"commit": "x", "luoi_tat": ["injection"]}}
    c = {}                                        # lần chạy cũ, chưa có meta
    g = nhom_theo_cau_hinh([("a", a), ("b", b), ("c", c)])
    assert set(g) == {("x", ()), ("x", ("injection",)), ("?", ())}
```

- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3:** thêm `wilson(k, n, z=1.96)`, `nhom_theo_cau_hinh(...)`; bảng 2.2 báo `trung bình ± độ lệch chuẩn` khi ≥2 lần cùng commit+cấu hình, kèm Wilson 95% cho tỉ lệ bỏ sót chuyển người. Lần chạy không có `meta` gom thành nhóm "lịch sử phát triển — không dùng để kết luận". Bảng mục 2.3 sinh từ các ca `bo_sot_chuyen_nguoi` THẬT trong file kết quả (id, câu hỏi, câu trả lời rút gọn); bỏ bảng gõ cứng. Thêm mục "2.4. Thí nghiệm tắt từng lớp" — một dòng mỗi cấu hình `luoi_tat`, cột: số lần, tỉ lệ đạt, bỏ sót chuyển người (Wilson), dùng từ cấm; chưa có dữ liệu thì in lệnh cần chạy. Bỏ câu "mức sàn" (min của 4 lần không phải mức sàn). `TONG_CA_VANG` đếm từ `golden.jsonl`, không hằng số.
- [ ] **Step 4:** `python -m scripts.sinh_thuc_nghiem --ghi`; `pytest tests/test_thuc_nghiem.py -q` xanh; commit.

### Task 5: Hết mâu thuẫn số liệu ngoài chương thực nghiệm

**Files:**
- Modify: `docs/co-so-ly-thuyet.md` (:94 "tám công cụ", :182 "13 lần chạy", :294-297 ghi chú trích dẫn)
- Modify: `docs/dua-vao-doanh-nghiep.md` (:22 "13 lần", :29 mô tả kênh cũ)
- Modify: `README.md:151` (số test cũ)
- Test: `tests/test_tai_lieu_khong_go_so.py`

- [ ] **Step 1: Test hỏng**

```python
# tests/test_tai_lieu_khong_go_so.py
"""Số lần chạy eval và số test không được gõ tay ngoài tài liệu sinh tự động."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAY = ["README.md", "docs/co-so-ly-thuyet.md", "docs/dua-vao-doanh-nghiep.md"]


def test_khong_go_so_lan_chay():
    for f in TAY:
        t = (ROOT / f).read_text(encoding="utf-8")
        assert not re.search(r"\b\d+ lần chạy", t), f


def test_khong_go_so_test():
    for f in TAY:
        t = (ROOT / f).read_text(encoding="utf-8")
        assert not re.search(r"\b\d{3,} test (pass|đạt)", t), f
```

- [ ] **Step 2:** chạy → FAIL.
- [ ] **Step 3:** viết lại các câu thành tham chiếu tới `docs/thuc-nghiem.md` ("xem mục 2.2 — số lần chạy sinh từ dữ liệu"); số công cụ thay bằng "các công cụ còn lại" hoặc sinh; mô tả kênh khớp README; xoá ghi chú "bạn phải tự kiểm tra lại thông tin xuất bản" sau khi chuẩn hoá chín mục tham khảo theo IEEE (tác giả, tên, nơi xuất bản, năm, URL/DOI) — mục nào không xác minh được thì ghi rõ "[chưa xác minh]" chứ không bịa.
- [ ] **Step 4:** test xanh + `pytest tests/test_claude_md.py tests/test_thuc_nghiem.py -q`; commit.

### Task 6: Coverage và CI

**Files:**
- Modify: `requirements-dev.txt` (+`pytest-cov`), `pytest.ini` hoặc `.coveragerc`
- Modify: `.github/workflows/kiem-thu.yml` (bước coverage, job test sidecar Node, danh sách import tự dò, bỏ số "2760 ca")

- [ ] **Step 1:** cài `pytest-cov` vào venv, chạy `python -m pytest -q --cov=agent --cov-report=term:skip-covered` (Postgres bật) → ghi số phần trăm thật.
- [ ] **Step 2:** CI: `pytest --cov=agent --cov-report=xml --cov-fail-under=<số đo − 2>`; thêm job `sidecar` (`actions/setup-node@v4`, node 22, `npm ci && npm test` trong `connectors/zalo-personal-sidecar` — kiểm `package.json` có script `test` trước); bước import thay danh sách gõ tay bằng `pkgutil.walk_packages(agent.__path__, "agent.")`.
- [ ] **Step 3:** test canh: `tests/test_ci_co_coverage.py` đọc YAML, assert có `--cov-fail-under` và job `sidecar`.
- [ ] **Step 4:** commit.

### Task 7: Khung khóa luận ánh xạ tới bằng chứng

**Files:**
- Create: `docs/khoa-luan/khung.md`

Không viết văn khóa luận thay tác giả. Tệp này là **dàn ý + bản đồ bằng chứng**: mỗi chương liệt kê câu hỏi nó trả lời, file mã/tài liệu/số đo làm căn cứ, và chỗ còn trống.

- [ ] **Step 1:** dàn ý: Mở đầu (bài toán, câu hỏi nghiên cứu CH1–CH3, mục tiêu, phạm vi, đóng góp) · Ch.1 Tổng quan & công trình liên quan (guardrails: NeMo Guardrails, Llama Guard; đánh giá LLM: RAGAS, LLM-as-judge; chatbot CSKH; SaaS VN: Pancake, Haravan, Sapo) · Ch.2 Cơ sở lý thuyết (→ `co-so-ly-thuyet.md`) · Ch.3 Phân tích thiết kế (→ `kien-truc.md`) · Ch.4 Hiện thực · Ch.5 Thực nghiệm (→ `thuc-nghiem.md`, ablation) · Ch.6 Kết luận, hạn chế, hướng phát triển (→ lộ trình SaaS) · Phụ lục (nghiệm thu, kết quả eval ẩn danh).
- [ ] **Step 2:** commit.

### Task 8: Gộp và đo lại

- [ ] `python -m scripts.sinh_so_do --ghi`, `python -m scripts.sinh_thuc_nghiem --ghi`
- [ ] `python -m pytest -q` (Postgres bật) xanh, `ruff check .` sạch
- [ ] `git push . giai-doan-0:main`
- [ ] Hỏi chủ dự án: chạy đo thật — `python -m scripts.eval --lap 5` (đủ lưới) và `--chi-prompt --lap 5`, cộng sáu lần `--tat-luoi <ma> --lap 3`; ước tính chi phí từ `chi_phi_usd` của lần chạy gần nhất × số lượt.
