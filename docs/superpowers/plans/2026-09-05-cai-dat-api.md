# Cài đặt API trên dashboard — kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quản trị viên nhập, kiểm và lưu khoá model / ERP / GHN ngay trên dashboard; khoá mã hoá trong CSDL, có hiệu lực ngay, `.env` là đường lui.

**Architecture:** Module `agent/cau_hinh_dong.py` là chỗ duy nhất trả lời "giá trị khoá X là gì" (bộ nhớ nạp từ bảng `cau_hinh_bi_mat`, lui về `settings`). `llm.py`, `erpnext.py`, `ghn.py` đọc qua nó. Router `agent/api/cai_dat_api.py` cho dashboard liệt kê / lưu / xoá / kiểm; kiểm chạy bằng giá trị chưa lưu qua các hàm probe nhận tham số tường minh. Thêm provider `gemini_api` (Google AI Studio) cho cả trả lời lẫn embedding.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, `cryptography` AES-GCM (vault sẵn có), httpx, pytest; dashboard JS thuần.

**Spec:** `docs/superpowers/specs/2026-09-05-cai-dat-api-design.md`

## Global Constraints

- Mã, chú thích, test, tài liệu bằng **tiếng Việt**; chú thích giải thích VÌ SAO.
- **Mỗi ràng buộc có test canh**; test không gọi API thật, không cần Postgres (dùng CSDL giả / monkeypatch).
- **Không bao giờ in hay trả về giá trị bí mật**: nhật ký chỉ ghi tên khoá; API chỉ trả bốn ký tự cuối.
- Chỉ nhận khoá trong `DANH_MUC`; `ERP_LOAI` và `SHIPPING_PROVIDER` **không** vào danh mục.
- Trước khi báo xong mỗi task: `python -m pytest -q` xanh, `ruff check .` sạch.
- Vá file trong repo này bằng Edit/Write tool hoặc script Python (heredoc Bash làm hỏng `\n`); sau khi vá chạy `ruff check .`.
- Chạy lệnh bằng `.venv/Scripts/python.exe`; đặt `PYTHONUTF8=1` khi script in tiếng Việt.
- Commit sau mỗi task, thông điệp tiếng Việt kể chuyện vì sao, kết bằng `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## Cấu trúc file

| File | Trách nhiệm |
|---|---|
| `agent/security/credential_vault.py` | thêm `encrypt_pham_vi` / `decrypt_pham_vi` (AAD theo phạm vi chuỗi) |
| `agent/migrations/versions/0013_cau_hinh_bi_mat.sql` | bảng `cau_hinh_bi_mat` |
| `agent/cau_hinh_dong.py` (mới) | danh mục khoá, kho Postgres, bộ nhớ, `nap/lay/nguon/dat/xoa/liet_ke/ghi_ket_qua_kiem` |
| `agent/core/llm.py` | `provider()` qua cấu hình động; `_gemini_dich`; provider `gemini_api`; cache client Anthropic có xoá; `kiem_khoa` |
| `agent/core/rag.py` | embedding qua Gemini API khi `gemini_api`; ghi model embedding đang dùng |
| `agent/suc_khoe.py` | `_kiem_model` dùng `kiem_khoa`; thêm `_kiem_embedding_khop` |
| `agent/erp/erpnext.py`, `agent/shipping/ghn.py` | mặc định đọc qua cấu hình động; GHN thêm `kiem_ket_noi` |
| `agent/api/cai_dat_api.py` (mới) | 4 endpoint |
| `agent/main.py` | `cau_hinh_dong.nap()` trong lifespan; include router |
| `scripts/san_sang.py` | mục "Khoá API" |
| `dashboard/index.html`, `dashboard/app.js` | panel Cài đặt API |
| `docs/van-hanh.md`, `.env.example`, `docs/kien-truc.md` (sinh) | tài liệu |
| `tests/test_vault_pham_vi.py`, `tests/test_cau_hinh_dong.py`, `tests/test_llm_gemini_api.py`, `tests/test_rag_embedding_gemini_api.py`, `tests/test_ghn_kiem_ket_noi.py`, `tests/test_api_cai_dat_api.py`, `tests/test_dashboard_cai_dat_api.py`, `tests/test_san_sang_khoa_api.py` | test |

---

### Task 1: Vault theo phạm vi

**Files:**
- Modify: `agent/security/credential_vault.py:75-125`
- Test: `tests/test_vault_pham_vi.py`

**Interfaces:**
- Produces: `CredentialVault.encrypt_pham_vi(payload: Mapping, *, pham_vi: str) -> SealedCredential`, `CredentialVault.decrypt_pham_vi(sealed: SealedCredential, *, pham_vi: str) -> dict`. Chữ ký `encrypt/decrypt(..., account_id=)` giữ nguyên.

- [ ] **Step 1: Viết test hỏng**

```python
"""
Vault phải tách PHẠM VI: bản mã của tài khoản kênh không mở được bằng
phạm vi cấu hình và ngược lại, dù cùng khoá chủ. Không có tách này thì một
lỗi tra nhầm bảng sẽ giải mã "đúng" ra một thứ sai — im lặng.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from agent.security.credential_vault import (
    CredentialVault, InvalidCredentialCiphertext,
)


def _vault():
    return CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=1)


def test_ma_hoa_va_giai_ma_theo_pham_vi():
    v = _vault()
    sealed = v.encrypt_pham_vi({"gia_tri": "abc"}, pham_vi="cau-hinh:GEMINI_API_KEY")
    assert v.decrypt_pham_vi(sealed, pham_vi="cau-hinh:GEMINI_API_KEY") == {"gia_tri": "abc"}


def test_khac_pham_vi_thi_khong_mo_duoc():
    v = _vault()
    sealed = v.encrypt_pham_vi({"gia_tri": "abc"}, pham_vi="cau-hinh:A")
    with pytest.raises(InvalidCredentialCiphertext):
        v.decrypt_pham_vi(sealed, pham_vi="cau-hinh:B")


def test_ban_ma_tai_khoan_kenh_khong_mo_duoc_bang_pham_vi_cau_hinh():
    v = _vault()
    acc = uuid4()
    sealed = v.encrypt({"token": "t"}, account_id=acc)
    with pytest.raises(InvalidCredentialCiphertext):
        v.decrypt_pham_vi(sealed, pham_vi=f"channel-account:{acc}")
```

Ca thứ ba canh đúng điều nguy hiểm: chuỗi AAD của phạm vi phải KHÁC chuỗi AAD tài khoản dù người gọi cố tình ghép cùng tên.

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_vault_pham_vi.py -q`
Expected: FAIL `AttributeError: ... encrypt_pham_vi`

- [ ] **Step 3: Thêm hai phương thức**

Trong `CredentialVault`, sau `_aad`:

```python
    @staticmethod
    def _aad_pham_vi(pham_vi: str) -> bytes:
        # Tiền tố khác `channel-account:` để hai phạm vi không bao giờ trùng
        # AAD, kể cả khi người gọi truyền đúng chuỗi "channel-account:<id>".
        return f"pham-vi:{pham_vi}".encode()

    def encrypt_pham_vi(
        self, payload: Mapping[str, Any], *, pham_vi: str
    ) -> SealedCredential:
        """Mã hoá cho một phạm vi chuỗi (khoá hệ thống), không gắn tài khoản."""
        nonce = os.urandom(12)
        plaintext = json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        ciphertext = AESGCM(self._keys[self._active_version]).encrypt(
            nonce, plaintext, self._aad_pham_vi(pham_vi),
        )
        return SealedCredential(self._active_version, nonce, ciphertext)

    def decrypt_pham_vi(
        self, sealed: SealedCredential, *, pham_vi: str
    ) -> dict[str, Any]:
        key = self._keys.get(sealed.key_version)
        if key is None:
            raise InvalidCredentialCiphertext("không thể mở giá trị đã mã hóa")
        try:
            plaintext = AESGCM(key).decrypt(
                sealed.nonce, sealed.ciphertext, self._aad_pham_vi(pham_vi),
            )
            decoded = json.loads(plaintext)
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidCredentialCiphertext("không thể mở giá trị đã mã hóa") from exc
        if not isinstance(decoded, dict):
            raise InvalidCredentialCiphertext("giá trị đã mã hóa sai cấu trúc")
        return decoded
```

- [ ] **Step 4: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_vault_pham_vi.py tests/test_credential_vault*.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agent/security/credential_vault.py tests/test_vault_pham_vi.py
git commit -m "Vault mã hoá theo phạm vi: khoá hệ thống không dùng chung AAD với tài khoản kênh"
```

---

### Task 2: Bảng `cau_hinh_bi_mat`

**Files:**
- Create: `agent/migrations/versions/0013_cau_hinh_bi_mat.sql`
- Regenerate: `docs/kien-truc.md` bằng `python -m scripts.sinh_so_do --ghi`
- Test: `tests/test_so_do.py` (đã có, phải còn xanh); thêm vào `scripts/sinh_so_do.py` nhóm cho bảng mới

**Interfaces:**
- Produces: bảng `cau_hinh_bi_mat(khoa, key_version, nonce, ciphertext, sua_boi, sua_luc, kiem_luc, kiem_ket_qua)`.

- [ ] **Step 1: Viết migration**

```sql
-- Khoá API của nhà cung cấp model, ERP, vận chuyển — nhập từ dashboard.
--
-- VÌ SAO KHÔNG ĐỂ TRONG .env
-- Khoá trong .env đọc một lần lúc khởi động. Đổi khoá là mở file, sửa tay,
-- khởi động lại; gõ sai một ký tự thì agent im lặng ngừng trả lời. Người
-- vận hành cửa hàng không nên phải mở file cấu hình để đổi một API key.
--
-- VÌ SAO KHÔNG DÙNG cau_hinh_agent
-- Bảng đó lưu JSONB ở dạng THƯỜNG. Khoá API là bí mật: phải mã hoá bằng
-- đúng vault đang bảo vệ credential kênh (AES-256-GCM, AAD theo phạm vi),
-- nên cần cột nonce/ciphertext/key_version riêng.
--
-- .env vẫn là đường lui: bảng rỗng thì hệ thống chạy như trước.

CREATE TABLE IF NOT EXISTS cau_hinh_bi_mat (
    khoa          TEXT PRIMARY KEY,
    key_version   INTEGER NOT NULL,
    nonce         BYTEA NOT NULL,
    ciphertext    BYTEA NOT NULL,
    sua_boi       TEXT NOT NULL,
    sua_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    kiem_luc      TIMESTAMPTZ,
    kiem_ket_qua  TEXT
);
```

- [ ] **Step 2: Xếp nhóm trong sơ đồ**

Mở `scripts/sinh_so_do.py`, tìm dict `NHOM`; thêm `"cau_hinh_bi_mat"` vào nhóm chứa `cau_hinh_agent` (nhóm "Vận hành"). `tests/test_so_do.py::test_moi_bang_deu_duoc_xep_nhom` đỏ nếu quên.

- [ ] **Step 3: Sinh lại tài liệu và chạy test**

Run: `PYTHONUTF8=1 .venv/Scripts/python.exe -m scripts.sinh_so_do --ghi && .venv/Scripts/python.exe -m pytest tests/test_so_do.py -q -k "so_do or migration"`
Expected: PASS; `docs/kien-truc.md` có bảng mới.

- [ ] **Step 4: Commit**

```bash
git add agent/migrations/versions/0013_cau_hinh_bi_mat.sql scripts/sinh_so_do.py docs/kien-truc.md
git commit -m "Bảng cau_hinh_bi_mat: khoá API mã hoá trong CSDL, .env chỉ là đường lui"
```

---

### Task 3: Module `cau_hinh_dong`

**Files:**
- Create: `agent/cau_hinh_dong.py`
- Test: `tests/test_cau_hinh_dong.py`

**Interfaces:**
- Consumes: Task 1 (`encrypt_pham_vi/decrypt_pham_vi`), `agent.db.fetch/execute/log_event`, `agent.config.settings`.
- Produces:
  - `DANH_MUC: dict[str, MoTa]` với `MoTa(khoa, nhom, nhan, bi_mat, chon, y_nghia)`
  - `KhoaKhongHopLe(ValueError)`, `VaultChuaSanSang(RuntimeError)`
  - `async nap() -> None`
  - `lay(khoa: str) -> str`, `nguon(khoa) -> str` (`"csdl" | "env" | "trong"`)
  - `async dat(khoa, gia_tri, *, sua_boi) -> None`, `async xoa(khoa, *, sua_boi) -> None`
  - `async ghi_ket_qua_kiem(khoa, ok: bool, chi_tiet: str) -> None`
  - `liet_ke() -> list[dict]`, `vault_san_sang() -> bool`, `duoi(gia_tri) -> str`
  - `_kho` (module-level, thay được trong test), `_vault()`.

- [ ] **Step 1: Viết test hỏng**

```python
"""
Cấu hình động: CSDL trước, .env sau — và không bao giờ lộ giá trị.
Không cần Postgres: kho giả trong bộ nhớ, vault thật với khoá test.
"""
from __future__ import annotations

import asyncio

import pytest

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.security.credential_vault import CredentialVault


class _KhoGia:
    def __init__(self):
        self.dong: dict[str, dict] = {}
        self.kiem: list = []

    async def doc_tat_ca(self):
        return [dict(khoa=k, **v) for k, v in self.dong.items()]

    async def ghi(self, khoa, sealed, sua_boi):
        self.dong[khoa] = dict(
            key_version=sealed.key_version, nonce=sealed.nonce,
            ciphertext=sealed.ciphertext, sua_boi=sua_boi, sua_luc=None,
            kiem_luc=None, kiem_ket_qua=None,
        )

    async def xoa(self, khoa):
        self.dong.pop(khoa, None)

    async def ghi_kiem(self, khoa, ket_qua):
        self.kiem.append((khoa, ket_qua))


@pytest.fixture
def kho(monkeypatch):
    k = _KhoGia()
    monkeypatch.setattr(cd, "_kho", k)
    monkeypatch.setattr(
        cd, "_vault",
        lambda: CredentialVault({1: bytes.fromhex("02" * 32)}, active_version=1),
    )
    su_kien = []

    async def log_event(kind, **kw):
        su_kien.append((kind, kw))

    monkeypatch.setattr(cd.db, "log_event", log_event)
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    cd._gia_tri.clear(); cd._meta.clear()
    k.su_kien = su_kien
    return k


def test_chua_dat_thi_lui_ve_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.nap())
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-env"
    assert cd.nguon("ANTHROPIC_API_KEY") == "env"


def test_dat_roi_thi_csdl_thang_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.dat("ANTHROPIC_API_KEY", "tu-csdl", sua_boi="admin"))
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-csdl"
    assert cd.nguon("ANTHROPIC_API_KEY") == "csdl"
    # Sống qua khởi động lại: nạp lại từ kho phải ra đúng giá trị.
    cd._gia_tri.clear()
    asyncio.run(cd.nap())
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-csdl"


def test_xoa_thi_lui_ve_env(kho, monkeypatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "tu-env")
    asyncio.run(cd.dat("ANTHROPIC_API_KEY", "tu-csdl", sua_boi="admin"))
    asyncio.run(cd.xoa("ANTHROPIC_API_KEY", sua_boi="admin"))
    assert cd.lay("ANTHROPIC_API_KEY") == "tu-env"


def test_nhat_ky_ghi_ten_khoa_khong_ghi_gia_tri(kho):
    asyncio.run(cd.dat("GEMINI_API_KEY", "bi-mat-rat-dai-123", sua_boi="admin"))
    assert kho.su_kien and kho.su_kien[0][0] == "cau_hinh_api.doi"
    assert "bi-mat-rat-dai-123" not in repr(kho.su_kien)


def test_khoa_ngoai_danh_muc_bi_tu_choi(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("ERP_LOAI", "erpnext", sua_boi="admin"))
    with pytest.raises(cd.KhoaKhongHopLe):
        cd.lay("KHOA_LA")


def test_provider_ngoai_danh_sach_bi_tu_choi(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("LLM_PROVIDER", "openai", sua_boi="admin"))


def test_model_phai_co_trong_bang_gia(kho):
    with pytest.raises(cd.KhoaKhongHopLe):
        asyncio.run(cd.dat("MODEL_CHAT", "gpt-9", sua_boi="admin"))
    asyncio.run(cd.dat("MODEL_CHAT", "gemini-2.5-flash", sua_boi="admin"))


def test_liet_ke_khong_lo_bi_mat_chi_lo_duoi(kho):
    asyncio.run(cd.dat("GEMINI_API_KEY", "AIzaSyDUMMY-abcd", sua_boi="admin"))
    asyncio.run(cd.dat("ERPNEXT_URL", "https://erp.example", sua_boi="admin"))
    ds = {m["khoa"]: m for m in cd.liet_ke()}
    assert ds["GEMINI_API_KEY"]["hien"] == "···abcd"
    assert ds["GEMINI_API_KEY"]["da_dat"] is True
    assert ds["ERPNEXT_URL"]["hien"] == "https://erp.example"
    assert "AIzaSyDUMMY-abcd" not in repr(cd.liet_ke())


def test_vault_chua_san_sang_thi_dat_nem_ro_rang(kho, monkeypatch):
    def hong():
        raise cd.VaultChuaSanSang("chưa có CREDENTIAL_MASTER_KEYS")

    monkeypatch.setattr(cd, "_vault", hong)
    with pytest.raises(cd.VaultChuaSanSang):
        asyncio.run(cd.dat("GEMINI_API_KEY", "x", sua_boi="admin"))


def test_giai_ma_hong_thi_bao_va_bo_qua_khong_chet(kho, monkeypatch):
    asyncio.run(cd.dat("GEMINI_API_KEY", "x" * 20, sua_boi="admin"))
    # Đổi khoá chủ: bản mã cũ không mở được nữa.
    monkeypatch.setattr(
        cd, "_vault",
        lambda: CredentialVault({1: bytes.fromhex("03" * 32)}, active_version=1),
    )
    cd._gia_tri.clear()
    asyncio.run(cd.nap())
    assert cd.nguon("GEMINI_API_KEY") in ("env", "trong")
    assert any(k == "cau_hinh_api.giai_ma_hong" for k, _ in kho.su_kien)


def test_danh_muc_khong_chua_cong_tac_nguy_hiem():
    """ERP_LOAI và SHIPPING_PROVIDER cố ý ở .env: bật sai là dữ liệu không xoá được."""
    assert "ERP_LOAI" not in cd.DANH_MUC
    assert "SHIPPING_PROVIDER" not in cd.DANH_MUC
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cau_hinh_dong.py -q`
Expected: FAIL `ModuleNotFoundError: agent.cau_hinh_dong`

- [ ] **Step 3: Viết module**

```python
"""
Cấu hình động: giá trị khoá API lấy từ CSDL trước, `.env` sau.

VÌ SAO CÓ LỚP NÀY
-----------------
Khoá model, ERP, GHN từng chỉ đọc từ `.env` một lần lúc khởi động. Đổi khoá
là mở file, sửa tay, khởi động lại; gõ sai một ký tự thì agent im lặng
ngừng trả lời. Dashboard giờ là chỗ nhập khoá, và mọi chỗ cần khoá hỏi
đúng một hàm: `lay("GEMINI_API_KEY")`.

VÌ SAO `lay()` ĐỒNG BỘ
----------------------
Chỗ gọi nằm sâu trong `llm.py`, `erpnext.py`, `ghn.py` — nơi không có
`await` tiện tay. Nên bộ nhớ tiến trình được nạp một lần lúc khởi động
(`nap()`) và cập nhật ngay khi `dat()`/`xoa()`.

KHÔNG BAO GIỜ LỘ GIÁ TRỊ
------------------------
Nhật ký chỉ ghi TÊN khoá. `liet_ke()` trả bốn ký tự cuối cho khoá bí mật.
Giá trị đầy đủ không có đường nào ra khỏi tiến trình.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent import db
from agent.config import settings
from agent.security.credential_vault import (
    CredentialVault,
    InvalidCredentialCiphertext,
    InvalidMasterKeyConfiguration,
    SealedCredential,
    parse_master_keys,
)

PHAM_VI = "cau-hinh"
PROVIDER_HOP_LE = ("gemini_api", "gemini", "anthropic", "vertex")


@dataclass(frozen=True, slots=True)
class MoTa:
    khoa: str
    nhom: str
    nhan: str
    bi_mat: bool
    chon: tuple[str, ...] = ()
    y_nghia: str = ""


# ERP_LOAI và SHIPPING_PROVIDER cố ý VẮNG MẶT: bật ERP thật có thứ tự năm
# bước trong docs/van-hanh.md, và shipping rời "mock" là tạo vận đơn không
# xoá được. Hai công tắc đó ở .env, nơi người ta phải mở file và đọc chú thích.
DANH_MUC: dict[str, MoTa] = {m.khoa: m for m in (
    MoTa("LLM_PROVIDER", "model", "Nhà cung cấp model", False, PROVIDER_HOP_LE,
         "gemini_api: chỉ cần API key từ Google AI Studio. gemini / vertex: cần "
         "dự án GCP và gcloud trên máy. anthropic: Claude trực tiếp."),
    MoTa("GEMINI_API_KEY", "model", "Gemini API key", True,
         y_nghia="Google AI Studio → Get API key. Dùng khi provider là gemini_api."),
    MoTa("ANTHROPIC_API_KEY", "model", "Anthropic API key", True,
         y_nghia="Dùng khi provider là anthropic."),
    MoTa("MODEL_CHAT", "model", "Model trả lời khách", False),
    MoTa("MODEL_HARD", "model", "Model việc khó", False),
    MoTa("MODEL_CHEAP", "model", "Model việc rẻ", False),
    MoTa("ERPNEXT_URL", "erp", "ERPNext URL", False),
    MoTa("ERPNEXT_API_KEY", "erp", "ERPNext API key", True),
    MoTa("ERPNEXT_API_SECRET", "erp", "ERPNext API secret", True),
    MoTa("GHN_TOKEN", "van_chuyen", "GHN token", True),
    MoTa("GHN_SHOP_ID", "van_chuyen", "GHN shop id", False),
)}


class KhoaKhongHopLe(ValueError):
    """Khoá ngoài danh mục, hoặc giá trị không hợp lệ cho khoá đó."""


class VaultChuaSanSang(RuntimeError):
    """Máy chủ chưa có CREDENTIAL_MASTER_KEYS nên không mã hoá được."""


class KhoBiMat:
    """Bảng `cau_hinh_bi_mat`. Tách lớp để test thay bằng kho giả."""

    async def doc_tat_ca(self) -> list[dict]:
        return await db.fetch(
            "SELECT khoa, key_version, nonce, ciphertext, sua_boi, sua_luc, "
            "kiem_luc, kiem_ket_qua FROM cau_hinh_bi_mat"
        )

    async def ghi(self, khoa: str, sealed: SealedCredential, sua_boi: str) -> None:
        await db.execute(
            """
            INSERT INTO cau_hinh_bi_mat
                (khoa, key_version, nonce, ciphertext, sua_boi, sua_luc)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (khoa) DO UPDATE SET
                key_version = EXCLUDED.key_version, nonce = EXCLUDED.nonce,
                ciphertext = EXCLUDED.ciphertext, sua_boi = EXCLUDED.sua_boi,
                sua_luc = now(), kiem_luc = NULL, kiem_ket_qua = NULL
            """,
            khoa, sealed.key_version, sealed.nonce, sealed.ciphertext, sua_boi,
        )

    async def xoa(self, khoa: str) -> None:
        await db.execute("DELETE FROM cau_hinh_bi_mat WHERE khoa = $1", khoa)

    async def ghi_kiem(self, khoa: str, ket_qua: str) -> None:
        await db.execute(
            "UPDATE cau_hinh_bi_mat SET kiem_luc = now(), kiem_ket_qua = $2 "
            "WHERE khoa = $1",
            khoa, ket_qua,
        )


_kho: KhoBiMat = KhoBiMat()
_gia_tri: dict[str, str] = {}
_meta: dict[str, dict[str, Any]] = {}
_log = logging.getLogger("agent.cau_hinh_dong")


def _vault() -> CredentialVault:
    try:
        return CredentialVault(
            parse_master_keys(settings.credential_master_keys),
            active_version=settings.credential_active_key_version,
        )
    except InvalidMasterKeyConfiguration as exc:
        raise VaultChuaSanSang(
            "Máy chủ chưa cấu hình CREDENTIAL_MASTER_KEYS nên không lưu được "
            "khoá. Xem hướng dẫn trong .env.example"
        ) from exc


def vault_san_sang() -> bool:
    try:
        _vault()
        return True
    except VaultChuaSanSang:
        return False


def _pham_vi(khoa: str) -> str:
    return f"{PHAM_VI}:{khoa}"


async def nap() -> None:
    """Nạp toàn bộ bảng vào bộ nhớ. Không bao giờ chặn khởi động."""
    _gia_tri.clear()
    _meta.clear()
    try:
        rows = await _kho.doc_tat_ca()
    except Exception as exc:  # noqa: BLE001 — bảng chưa có thì chạy bằng .env
        _log.warning("cau_hinh_dong: không đọc được bảng (%s), dùng .env", type(exc).__name__)
        return
    if not rows:
        return
    try:
        vault = _vault()
    except VaultChuaSanSang:
        _log.warning("cau_hinh_dong: có %d khoá trong CSDL nhưng vault chưa cấu hình", len(rows))
        return
    for r in rows:
        try:
            d = vault.decrypt_pham_vi(
                SealedCredential(int(r["key_version"]), r["nonce"], r["ciphertext"]),
                pham_vi=_pham_vi(r["khoa"]),
            )
        except InvalidCredentialCiphertext:
            # Khoá chủ đổi hoặc bản mã hỏng. Không nuốt: san_sang đọc sự kiện
            # này. Nhưng cũng không chặn: các khoá khác vẫn phải nạp được.
            await db.log_event("cau_hinh_api.giai_ma_hong", khoa=r["khoa"])
            continue
        _gia_tri[r["khoa"]] = str(d.get("gia_tri") or "")
        _meta[r["khoa"]] = {
            "sua_boi": r.get("sua_boi"), "sua_luc": r.get("sua_luc"),
            "kiem_luc": r.get("kiem_luc"), "kiem_ket_qua": r.get("kiem_ket_qua"),
        }


def _mo_ta(khoa: str) -> MoTa:
    mo_ta = DANH_MUC.get(khoa)
    if mo_ta is None:
        raise KhoaKhongHopLe(f"khoá {khoa!r} không có trong danh mục")
    return mo_ta


def lay(khoa: str) -> str:
    """Giá trị hiện hành: CSDL trước, `.env` sau, rỗng nếu không đâu có."""
    _mo_ta(khoa)
    v = _gia_tri.get(khoa, "")
    if v:
        return v
    return str(getattr(settings, khoa.lower(), "") or "")


def nguon(khoa: str) -> str:
    _mo_ta(khoa)
    if _gia_tri.get(khoa):
        return "csdl"
    if str(getattr(settings, khoa.lower(), "") or ""):
        return "env"
    return "trong"


def kiem_gia_tri(khoa: str, gia_tri: str) -> str:
    mo_ta = _mo_ta(khoa)
    gia_tri = str(gia_tri or "").strip()
    if not gia_tri:
        raise KhoaKhongHopLe(f"{mo_ta.nhan}: giá trị trống")
    if mo_ta.chon and gia_tri not in mo_ta.chon:
        raise KhoaKhongHopLe(f"{mo_ta.nhan}: chỉ nhận {' | '.join(mo_ta.chon)}")
    if khoa.startswith("MODEL_"):
        from agent.core.llm import PRICING

        if gia_tri not in PRICING:
            raise KhoaKhongHopLe(
                f"{mo_ta.nhan}: model {gia_tri!r} không có trong bảng giá; "
                f"nhận {', '.join(sorted(PRICING))}"
            )
    return gia_tri


def _sau_khi_doi(khoa: str) -> None:
    # Client Anthropic được cache theo khoá; đổi khoá mà giữ client cũ là
    # dashboard báo "đã lưu" trong khi model vẫn chạy khoá cũ.
    from agent.core import llm

    llm.xoa_cache_client()


async def dat(khoa: str, gia_tri: str, *, sua_boi: str) -> None:
    gia_tri = kiem_gia_tri(khoa, gia_tri)
    vault = _vault()
    sealed = vault.encrypt_pham_vi({"gia_tri": gia_tri}, pham_vi=_pham_vi(khoa))
    await _kho.ghi(khoa, sealed, sua_boi)
    _gia_tri[khoa] = gia_tri
    _meta[khoa] = {
        "sua_boi": sua_boi, "sua_luc": datetime.now(timezone.utc),
        "kiem_luc": None, "kiem_ket_qua": None,
    }
    # KHÔNG ghi giá trị vào nhật ký, kể cả khoá không bí mật — một danh sách
    # trắng "khoá nào in được" là một chỗ để lần sau thêm nhầm.
    await db.log_event("cau_hinh_api.doi", actor=sua_boi, khoa=khoa)
    _sau_khi_doi(khoa)


async def xoa(khoa: str, *, sua_boi: str) -> None:
    _mo_ta(khoa)
    await _kho.xoa(khoa)
    _gia_tri.pop(khoa, None)
    _meta.pop(khoa, None)
    await db.log_event("cau_hinh_api.xoa", actor=sua_boi, khoa=khoa)
    _sau_khi_doi(khoa)


async def ghi_ket_qua_kiem(khoa: str, ok: bool, chi_tiet: str) -> None:
    _mo_ta(khoa)
    if khoa not in _gia_tri:
        return  # chỉ ghi cho khoá đang lưu trong CSDL
    ket_qua = ("đạt: " if ok else "hỏng: ") + chi_tiet[:200]
    await _kho.ghi_kiem(khoa, ket_qua)
    _meta.setdefault(khoa, {})
    _meta[khoa]["kiem_luc"] = datetime.now(timezone.utc)
    _meta[khoa]["kiem_ket_qua"] = ket_qua


def duoi(gia_tri: str) -> str:
    return "···" + gia_tri[-4:] if len(gia_tri) >= 8 else "···"


def liet_ke() -> list[dict]:
    ra = []
    for mo_ta in DANH_MUC.values():
        v = lay(mo_ta.khoa)
        meta = _meta.get(mo_ta.khoa, {})
        ra.append({
            "khoa": mo_ta.khoa, "nhom": mo_ta.nhom, "nhan": mo_ta.nhan,
            "bi_mat": mo_ta.bi_mat, "chon": list(mo_ta.chon), "y_nghia": mo_ta.y_nghia,
            "da_dat": bool(v), "nguon": nguon(mo_ta.khoa),
            "hien": (duoi(v) if mo_ta.bi_mat else v) if v else "",
            "sua_boi": meta.get("sua_boi"),
            "sua_luc": meta["sua_luc"].isoformat() if meta.get("sua_luc") else None,
            "kiem_luc": meta["kiem_luc"].isoformat() if meta.get("kiem_luc") else None,
            "kiem_ket_qua": meta.get("kiem_ket_qua"),
        })
    return ra
```

Lưu ý `_sau_khi_doi` gọi `llm.xoa_cache_client()` — hàm đó tạo ở Task 4. Trong task này test đã monkeypatch `_sau_khi_doi`, nên chưa cần Task 4 để xanh.

Cùng task này, thêm vào `agent/config.py` ngay dưới `anthropic_api_key: str = ""`:

```python
    # Gemini qua Google AI Studio (provider gemini_api). Nhập được trên
    # dashboard; ở đây chỉ là đường lui — xem agent/cau_hinh_dong.py.
    gemini_api_key: str = ""
```

Không có trường này, `lay("GEMINI_API_KEY")` vẫn chạy (getattr có mặc định) nhưng `.env` không còn là đường lui thật cho khoá Gemini.

- [ ] **Step 4: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_cau_hinh_dong.py -q && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS, ruff sạch.

- [ ] **Step 5: Commit**

```bash
git add agent/cau_hinh_dong.py tests/test_cau_hinh_dong.py
git commit -m "Cấu hình động: khoá API đọc từ CSDL trước, .env sau, không bao giờ lộ giá trị"
```

---

### Task 4: `llm.py` — provider `gemini_api`, cache client, `kiem_khoa`

**Files:**
- Modify: `agent/core/llm.py` (`provider()` ~79, `_gemini_url` ~168, `_complete_gemini` ~287-300 và vòng gọi ~320, `_anthropic_client` ~387, `_complete_claude` ~444, `complete()` ~506)
- Test: `tests/test_llm_gemini_api.py`

**Interfaces:**
- Consumes: `cau_hinh_dong.lay`.
- Produces:
  - `GEMINI_API_GOC = "https://generativelanguage.googleapis.com/v1beta"`
  - `async _gemini_dich(model, *, provider_name=None, api_key="", project="") -> tuple[str, dict]`
  - `_complete_gemini(..., dich: tuple[str, dict] | None = None)`
  - `_anthropic_client(*, provider_name=None, api_key="")`, `xoa_cache_client() -> None`
  - `_complete_claude(..., client=None)`
  - `async kiem_khoa(*, provider_name, api_key="", model="", project="", timeout=45.0) -> tuple[bool, str, int]`
  - `complete()` chấp nhận provider `gemini_api`.

- [ ] **Step 1: Viết test hỏng**

```python
"""
Provider `gemini_api`: chỉ cần API key, không cần GCP. Không gọi API thật.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.core import llm


@pytest.fixture(autouse=True)
def _sach(monkeypatch):
    cd._gia_tri.clear()
    llm.xoa_cache_client()
    monkeypatch.setattr(settings, "llm_provider", "gemini_api")
    monkeypatch.setattr(settings, "gcp_project_id", "your-gcp-project-id")


def test_dich_gemini_api_dung_url_va_header(monkeypatch):
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    url, headers = asyncio.run(llm._gemini_dich("gemini-2.5-flash"))
    assert url == f"{llm.GEMINI_API_GOC}/models/gemini-2.5-flash:generateContent"
    assert headers["x-goog-api-key"] == "AIzaTEST"
    assert "Authorization" not in headers


def test_thieu_khoa_thi_noi_ro_cho_nhap():
    with pytest.raises(RuntimeError) as e:
        asyncio.run(llm._gemini_dich("gemini-2.5-flash"))
    assert "GEMINI_API_KEY" in str(e.value)
    assert "Cài đặt API" in str(e.value)


def test_provider_doc_tu_cau_hinh_dong():
    cd._gia_tri["LLM_PROVIDER"] = "anthropic"
    assert llm.provider() == "anthropic"
    cd._gia_tri.clear()
    assert llm.provider() == "gemini_api"


def test_complete_gemini_api_khong_can_gcp(monkeypatch):
    """Điều kiện `GCP_PROJECT_ID` từng chặn ngay đầu hàm — với API key nó vô nghĩa."""
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["url"], goi["headers"] = url, headers
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    r = asyncio.run(llm.complete(
        system=llm.cached_system("x"), messages=[{"role": "user", "content": "ok?"}],
        model="gemini-2.5-flash-lite", max_tokens=8,
    ))
    assert r.text == "ok"
    assert goi["headers"]["x-goog-api-key"] == "AIzaTEST"


def test_kiem_khoa_dung_gia_tri_truyen_vao_khong_dung_cau_hinh(monkeypatch):
    cd._gia_tri["GEMINI_API_KEY"] = "KHOA-DANG-LUU"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["key"] = headers["x-goog-api-key"]
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 1},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    ok, chi_tiet, ms = asyncio.run(llm.kiem_khoa(
        provider_name="gemini_api", api_key="KHOA-MOI-CHUA-LUU", model="gemini-2.5-flash-lite",
    ))
    assert ok and goi["key"] == "KHOA-MOI-CHUA-LUU"
    assert "gemini-2.5-flash-lite" in chi_tiet


def test_kiem_khoa_het_han_muc_noi_ro(monkeypatch):
    async def post(self, url, headers=None, json=None):
        return httpx.Response(429, text="RESOURCE_EXHAUSTED", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    monkeypatch.setattr(llm, "MAX_RETRIES", 1)
    ok, chi_tiet, _ = asyncio.run(llm.kiem_khoa(
        provider_name="gemini_api", api_key="k", model="gemini-2.5-flash-lite",
    ))
    assert not ok and "HẾT HẠN MỨC" in chi_tiet


def test_xoa_cache_client_lam_dung_lai_client_anthropic(monkeypatch):
    dung = []

    class _Anthropic:
        def __init__(self, api_key):
            dung.append(api_key)

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _Anthropic)
    cd._gia_tri["LLM_PROVIDER"] = "anthropic"
    cd._gia_tri["ANTHROPIC_API_KEY"] = "k1"
    llm._anthropic_client()
    llm._anthropic_client()
    assert dung == ["k1"]
    cd._gia_tri["ANTHROPIC_API_KEY"] = "k2"
    llm.xoa_cache_client()
    llm._anthropic_client()
    assert dung == ["k1", "k2"]
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_llm_gemini_api.py -q`
Expected: FAIL (`GEMINI_API_GOC`, `_gemini_dich`, `xoa_cache_client` không tồn tại).

- [ ] **Step 3: Sửa `llm.py`**

(a) `provider()`:

```python
def provider() -> str:
    # Đọc qua cấu hình động để đổi provider trên dashboard có hiệu lực
    # ngay; `.env` vẫn là đường lui bên trong `lay()`.
    from agent import cau_hinh_dong

    return (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").strip().lower()
```

(b) Thêm hằng và hàm đích, ngay sau `_gemini_url`:

```python
GEMINI_API_GOC = "https://generativelanguage.googleapis.com/v1beta"


async def _gemini_dich(
    model: str, *, provider_name: str | None = None, api_key: str = "",
    project: str = "",
) -> tuple[str, dict[str, str]]:
    """
    URL và header cho một lượt gọi Gemini, theo provider.

    Hai đường tới cùng một model: Vertex (token ADC, cần dự án GCP) và
    Gemini API (chỉ cần API key). Body giống hệt nhau, nên chỉ tách phần
    này ra — và `kiem_khoa` truyền khoá CHƯA LƯU vào đây để thử.
    """
    from agent import cau_hinh_dong

    p = (provider_name or provider()).strip().lower()
    if p == "gemini_api":
        key = api_key or cau_hinh_dong.lay("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "Chưa có GEMINI_API_KEY. Nhập ở dashboard → Cấu hình → Cài đặt API, "
                "hoặc đặt trong .env"
            )
        return (
            f"{GEMINI_API_GOC}/models/{model}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json"},
        )
    project = project or settings.gcp_project_id
    if not project or project.startswith("your-"):
        raise RuntimeError("Chưa đặt GCP_PROJECT_ID trong .env")
    return (
        _gemini_url(model, project=project),
        {"Authorization": f"Bearer {await _token()}", "Content-Type": "application/json"},
    )
```

Sửa `_gemini_url` nhận `project`: `def _gemini_url(model: str, *, project: str | None = None) -> str:` và dùng `project or settings.gcp_project_id` thay `settings.gcp_project_id`.

(c) `_complete_gemini`: thêm tham số `dich: tuple[str, dict] | None = None`; **xoá** hai dòng kiểm `gcp_project_id` ở đầu hàm (đã chuyển vào `_gemini_dich`); trước `started = time.perf_counter()` thêm `url, headers = dich or await _gemini_dich(model)`; trong vòng gọi thay `_gemini_url(model)` bằng `url` và thay dict `headers={...}` bằng `headers=headers`.

(d) Client Anthropic:

```python
_ANTHROPIC_CACHE: dict[tuple, Any] = {}


def xoa_cache_client() -> None:
    """Gọi khi khoá đổi. Giữ client cũ là chạy khoá cũ sau khi đã báo 'đã lưu'."""
    _ANTHROPIC_CACHE.clear()


def _anthropic_client(*, provider_name: str | None = None, api_key: str = ""):
    from agent import cau_hinh_dong

    p = (provider_name or provider()).strip().lower()
    if p == "anthropic":
        key = api_key or cau_hinh_dong.lay("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic nhưng thiếu ANTHROPIC_API_KEY. Nhập ở "
                "dashboard → Cấu hình → Cài đặt API, hoặc đặt trong .env"
            )
        khoa_cache = ("anthropic", key)
        if khoa_cache not in _ANTHROPIC_CACHE:
            from anthropic import Anthropic

            _ANTHROPIC_CACHE[khoa_cache] = Anthropic(api_key=key)
        return _ANTHROPIC_CACHE[khoa_cache]

    from anthropic import AnthropicVertex

    if not settings.gcp_project_id or settings.gcp_project_id.startswith("your-"):
        raise RuntimeError("Chưa đặt GCP_PROJECT_ID trong .env")
    khoa_cache = ("vertex", settings.gcp_project_id, settings.gcp_region)
    if khoa_cache not in _ANTHROPIC_CACHE:
        _ANTHROPIC_CACHE[khoa_cache] = AnthropicVertex(
            project_id=settings.gcp_project_id, region=settings.gcp_region
        )
    return _ANTHROPIC_CACHE[khoa_cache]
```

Bỏ decorator `@lru_cache` cũ và hàm cũ.

(e) `_complete_claude`: thêm tham số `client=None` vào chữ ký; tìm dòng gọi `_anthropic_client()` trong thân (grep `_anthropic_client()`) và thay bằng `(client or _anthropic_client())`.

(f) `complete()`: đổi `if p == "gemini":` thành `if p in ("gemini", "gemini_api"):`, và thông điệp lỗi cuối thành `"Nhận: gemini_api | gemini | vertex | anthropic."`.

(g) Thêm cuối file:

```python
async def kiem_khoa(
    *, provider_name: str, api_key: str = "", model: str = "", project: str = "",
    timeout: float = 45.0,
) -> tuple[bool, str, int]:
    """
    Gọi một câu 8 token bằng ĐÚNG tham số truyền vào, không đụng cấu hình
    toàn cục. Đây là đường duy nhất để kiểm một khoá trước khi lưu — và
    cũng là đường `suc_khoe` dùng, để không có hai bản kiểm lệch nhau.
    """
    from agent import cau_hinh_dong

    p = provider_name.strip().lower()
    model = model or cau_hinh_dong.lay("MODEL_CHEAP") or settings.model_cheap
    system = cached_system("Trả lời đúng một chữ: ok")
    messages = [{"role": "user", "content": "ok?"}]
    t0 = time.perf_counter()
    try:
        if p in ("gemini", "gemini_api"):
            dich = await _gemini_dich(model, provider_name=p, api_key=api_key, project=project)
            r = await asyncio.wait_for(
                _complete_gemini(system=system, messages=messages, model=model,
                                 max_tokens=8, tools=None, effort="low", dich=dich),
                timeout,
            )
        elif p in ("anthropic", "vertex"):
            client = _anthropic_client(provider_name=p, api_key=api_key)
            r = await asyncio.wait_for(
                _complete_claude(system=system, messages=messages, model=model,
                                 max_tokens=8, tools=None, effort="low", client=client),
                timeout,
            )
        else:
            return False, f"provider không hợp lệ: {provider_name!r}", 0
    except asyncio.TimeoutError:
        return False, f"quá {int(timeout)} giây không trả lời", int((time.perf_counter() - t0) * 1000)
    except Exception as exc:  # noqa: BLE001
        ms = int((time.perf_counter() - t0) * 1000)
        loi = str(exc)
        if "429" in loi or "exhaust" in loi.lower():
            return False, "HẾT HẠN MỨC — khoá đúng nhưng nhà cung cấp từ chối phục vụ thêm", ms
        return False, f"{type(exc).__name__}: {loi}"[:200], ms
    return True, f"{r.model} · {r.latency_ms}ms", r.latency_ms
```

Đảm bảo `import asyncio` có ở đầu `llm.py` (đã có vì `_token()` dùng).

- [ ] **Step 4: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_llm_gemini_api.py tests/test_cau_hinh_dong.py -q && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS toàn bộ. Nếu test cũ nào tra `_anthropic_client.cache_clear` thì đổi sang `xoa_cache_client()`.

- [ ] **Step 5: Commit**

```bash
git add agent/core/llm.py tests/test_llm_gemini_api.py
git commit -m "Gemini bằng API key: không cần gcloud; kiểm khoá trước khi lưu bằng đúng khoá chưa lưu"
```

---

### Task 5: Embedding qua Gemini API và lưới "kho nạp bằng model khác"

**Files:**
- Modify: `agent/core/rag.py:17-60`
- Modify: `agent/suc_khoe.py` (`_kiem_model` ~52-80, `tong_kiem` ~502)
- Test: `tests/test_rag_embedding_gemini_api.py`

**Interfaces:**
- Consumes: `llm.provider()`, `llm.GEMINI_API_GOC`, `llm.kiem_khoa`, `cau_hinh_dong.lay`.
- Produces: `rag.EMBED_MODEL_API = "gemini-embedding-001"`, `rag.embed_model_hien_hanh() -> str`, `rag._embed_gemini_api(texts, task)`, `rag._ghi_model_dang_dung(model)`; `suc_khoe._kiem_embedding_khop()`.

- [ ] **Step 1: Viết test hỏng**

```python
"""
Đổi provider sang gemini_api thì embedding cũng phải đi bằng API key — và
kho tri thức nạp bằng model A mà hỏi bằng model B là tìm sai trong im lặng.
"""
from __future__ import annotations

import asyncio
import inspect

import httpx

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.core import rag


def test_model_embedding_theo_provider(monkeypatch):
    cd._gia_tri.clear()
    monkeypatch.setattr(settings, "llm_provider", "gemini_api")
    assert rag.embed_model_hien_hanh() == rag.EMBED_MODEL_API
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    assert rag.embed_model_hien_hanh() == rag.EMBED_MODEL


def test_embed_gemini_api_ep_768_chieu_va_dung_api_key(monkeypatch):
    cd._gia_tri.clear()
    cd._gia_tri["GEMINI_API_KEY"] = "AIzaTEST"
    goi = {}

    async def post(self, url, headers=None, json=None):
        goi["url"], goi["headers"], goi["body"] = url, headers, json
        return httpx.Response(200, json={"embeddings": [{"values": [0.1] * 768}]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", post)
    vec = asyncio.run(rag._embed_gemini_api(["xin chào"], "RETRIEVAL_QUERY"))
    assert len(vec) == 1 and len(vec[0]) == rag.EMBED_DIM
    assert goi["headers"]["x-goog-api-key"] == "AIzaTEST"
    assert ":batchEmbedContents" in goi["url"]
    yeu_cau = goi["body"]["requests"][0]
    assert yeu_cau["outputDimensionality"] == rag.EMBED_DIM
    assert yeu_cau["taskType"] == "RETRIEVAL_QUERY"


def test_embed_tai_lieu_ghi_model_dang_dung(monkeypatch):
    """Ghi lúc nạp tài liệu, không ghi lúc hỏi: hỏi thì không đổi kho."""
    ghi = []

    async def execute(sql, *args):
        ghi.append(args)

    async def gia(texts, task):
        return [[0.0] * rag.EMBED_DIM for _ in texts]

    monkeypatch.setattr(rag.db, "execute", execute)
    monkeypatch.setattr(rag, "_embed_sync", lambda texts, task: [[0.0] * rag.EMBED_DIM for _ in texts])
    monkeypatch.setattr(rag, "_embed_gemini_api", gia)
    rag._da_ghi_model = None
    asyncio.run(rag.embed(["a"], query=True))
    assert ghi == []
    asyncio.run(rag.embed(["a"]))
    assert ghi and ghi[0][0] == rag.embed_model_hien_hanh()
    asyncio.run(rag.embed(["b"]))
    assert len(ghi) == 1, "ghi lặp mỗi lô là tốn một lượt CSDL vô ích"


def test_suc_khoe_bao_do_khi_kho_nap_bang_model_khac(monkeypatch):
    from agent import suc_khoe

    async def fetchrow(sql, *args):
        return {"gia_tri": "model-cu"}

    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow)
    m = asyncio.run(suc_khoe._kiem_embedding_khop())
    assert m["trang_thai"] == suc_khoe.HONG
    assert "model-cu" in m["ghi_chu"] and "Nạp lại" in m["ghi_chu"]


def test_suc_khoe_kiem_model_di_qua_kiem_khoa():
    from agent import suc_khoe

    assert "kiem_khoa(" in inspect.getsource(suc_khoe._kiem_model)


def test_kiem_embedding_nam_trong_tong_kiem():
    from agent import suc_khoe

    assert "_kiem_embedding_khop()" in inspect.getsource(suc_khoe.tong_kiem)
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rag_embedding_gemini_api.py -q`
Expected: FAIL (`EMBED_MODEL_API`, `_embed_gemini_api` không tồn tại).

- [ ] **Step 3: Sửa `rag.py`**

Sau `EMBED_DIM = 768` thêm:

```python
# Gemini API (Google AI Studio) không có text-multilingual-embedding-002.
# gemini-embedding-001 mặc định 3072 chiều, nhưng nhận `outputDimensionality`
# — ép về 768 để khớp cột `vector(768)`. Vector của hai model KHÔNG so được
# với nhau: đổi provider là phải nạp lại kho, và `suc_khoe` canh việc đó.
EMBED_MODEL_API = "gemini-embedding-001"
_da_ghi_model: str | None = None


def embed_model_hien_hanh() -> str:
    from agent.core import llm

    return EMBED_MODEL_API if llm.provider() == "gemini_api" else EMBED_MODEL


async def _embed_gemini_api(texts: list[str], task: str) -> list[list[float]]:
    import httpx

    from agent import cau_hinh_dong
    from agent.core.llm import GEMINI_API_GOC

    key = cau_hinh_dong.lay("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Chưa có GEMINI_API_KEY cho embedding. Nhập ở dashboard → Cấu hình → Cài đặt API"
        )
    body = {
        "requests": [
            {
                "model": f"models/{EMBED_MODEL_API}",
                "content": {"parts": [{"text": t}]},
                "taskType": task,
                "outputDimensionality": EMBED_DIM,
            }
            for t in texts
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{GEMINI_API_GOC}/models/{EMBED_MODEL_API}:batchEmbedContents",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini embedding {r.status_code}: {r.text[:200]}")
    return [e["values"] for e in r.json().get("embeddings", [])]


async def _ghi_model_dang_dung(model: str) -> None:
    """Ghi một lần mỗi tiến trình vào cau_hinh_agent để suc_khoe đối chiếu."""
    global _da_ghi_model
    if _da_ghi_model == model:
        return
    await db.execute(
        "INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi) "
        "VALUES ('embed_model_dang_dung', $1, 'system') "
        "ON CONFLICT (khoa) DO UPDATE SET gia_tri = EXCLUDED.gia_tri, sua_luc = now()",
        model,   # codec JSONB của pool tự mã hoá chuỗi
    )
    _da_ghi_model = model
```

Trong `embed()`, thay dòng `return await asyncio.to_thread(_embed_sync, texts, task)` bằng:

```python
            model = embed_model_hien_hanh()
            if model == EMBED_MODEL_API:
                vec = await _embed_gemini_api(texts, task)
            else:
                vec = await asyncio.to_thread(_embed_sync, texts, task)
            if not query:
                await _ghi_model_dang_dung(model)
            return vec
```

- [ ] **Step 4: Sửa `suc_khoe.py`**

Thay thân `_kiem_model` (giữ docstring) bằng:

```python
    from agent import cau_hinh_dong
    from agent.core import llm

    p = llm.provider()
    ok, chi_tiet, ms = await llm.kiem_khoa(
        provider_name=p,
        model=cau_hinh_dong.lay("MODEL_CHEAP") or settings.model_cheap,
    )
    if ok:
        return _muc("Model ngôn ngữ", TOT, f"{chi_tiet} · {p}", latency_ms=ms)
    if "HẾT HẠN MỨC" in chi_tiet:
        return _muc("Model ngôn ngữ", HONG, "HẾT HẠN MỨC — agent không trả lời được khách")
    return _muc("Model ngôn ngữ", HONG, chi_tiet[:150])
```

Thêm hàm mới ngay sau `_kiem_model`:

```python
async def _kiem_embedding_khop() -> dict:
    """
    Kho tri thức có được nạp bằng đúng model embedding đang hỏi không.

    Hai model cho hai không gian vector khác nhau: kho nạp bằng A, hỏi bằng
    B thì tìm kiếm trả kết quả sai mà không một lỗi nào. Đổi provider trên
    dashboard là lúc chuyện này xảy ra.
    """
    from agent.core import rag

    hien = rag.embed_model_hien_hanh()
    row = await db.fetchrow(
        "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = 'embed_model_dang_dung'"
    )
    if not row:
        return _muc("Embedding kho tri thức", TOT, f"{hien} (chưa ghi nhận lần nạp nào)")
    da = str(row["gia_tri"])
    if da != hien:
        return _muc(
            "Embedding kho tri thức", HONG,
            f"kho nạp bằng {da}, đang hỏi bằng {hien} — tìm kiếm sai mà không lỗi. "
            "Nạp lại kho tri thức (Tri thức → Nạp lại)",
        )
    return _muc("Embedding kho tri thức", TOT, hien)
```

Trong `tong_kiem`, thêm `_kiem_embedding_khop(),` sau `_kiem_model(),`.

- [ ] **Step 5: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_rag_embedding_gemini_api.py -q && .venv/Scripts/python.exe -m pytest -q -k "suc_khoe or rag or tri_thuc" && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/core/rag.py agent/suc_khoe.py tests/test_rag_embedding_gemini_api.py
git commit -m "Embedding qua Gemini API, và lưới bắt kho tri thức nạp bằng model khác model đang hỏi"
```

---

### Task 6: ERPNext và GHN đọc qua cấu hình động; GHN có kiểm kết nối

**Files:**
- Modify: `agent/erp/erpnext.py:124-128`
- Modify: `agent/shipping/ghn.py:51-60` và thêm hàm cuối file
- Test: `tests/test_ghn_kiem_ket_noi.py`

**Interfaces:**
- Consumes: `cau_hinh_dong.lay`.
- Produces: `ghn.kiem_ket_noi(*, token, shop_id, api_url=None, client=None) -> tuple[bool, str, int]`.

- [ ] **Step 1: Viết test hỏng**

```python
"""GHN: kiểm token và shop id bằng một lời gọi chỉ đọc, không tạo vận đơn."""
from __future__ import annotations

import asyncio

import httpx

from agent import cau_hinh_dong as cd
from agent.config import settings
from agent.shipping import ghn


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_token_dung_shop_dung():
    def handler(req):
        assert req.headers["Token"] == "tok"
        assert req.url.path.endswith("/shop/all")
        return httpx.Response(200, json={"data": {"shops": [{"_id": 123, "name": "Shop"}]}})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="tok", shop_id="123", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert ok and "1 shop" in chi_tiet


def test_shop_id_khong_thuoc_tai_khoan_thi_noi_ro():
    def handler(req):
        return httpx.Response(200, json={"data": {"shops": [{"_id": 999}]}})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="tok", shop_id="123", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert not ok and "123" in chi_tiet


def test_token_sai_thi_khong_ok():
    def handler(req):
        return httpx.Response(401, json={"message": "Unauthorized"})

    ok, chi_tiet, _ = asyncio.run(ghn.kiem_ket_noi(
        token="sai", shop_id="1", api_url="https://ghn.test/v2", client=_client(handler),
    ))
    assert not ok and "token" in chi_tiet.lower()


def test_provider_ghn_doc_qua_cau_hinh_dong(monkeypatch):
    cd._gia_tri.clear()
    monkeypatch.setattr(settings, "ghn_token", "tu-env")
    assert ghn.GHNShippingProvider()._token == "tu-env"
    cd._gia_tri["GHN_TOKEN"] = "tu-csdl"
    assert ghn.GHNShippingProvider()._token == "tu-csdl"
    cd._gia_tri.clear()


def test_erpnext_doc_qua_cau_hinh_dong(monkeypatch):
    from agent.erp.erpnext import NguonErpNext

    cd._gia_tri.clear()
    cd._gia_tri["ERPNEXT_URL"] = "https://erp.csdl"
    cd._gia_tri["ERPNEXT_API_KEY"] = "k"
    cd._gia_tri["ERPNEXT_API_SECRET"] = "s"
    monkeypatch.setattr(settings, "erp_ma_kho", "KHO")
    monkeypatch.setattr(settings, "erp_pricelist", "Bán lẻ")
    assert NguonErpNext()._goc == "https://erp.csdl"
    cd._gia_tri.clear()
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ghn_kiem_ket_noi.py -q`
Expected: FAIL (`kiem_ket_noi` không tồn tại; `_token` vẫn từ env).

- [ ] **Step 3: Sửa `erpnext.py`**

Thay ba dòng mặc định trong `__init__`:

```python
        from agent import cau_hinh_dong

        # Mặc định đọc qua cấu hình động (dashboard → CSDL → .env). Tham số
        # tường minh vẫn thắng: `kiem-tra` trên dashboard truyền giá trị chưa lưu.
        self._goc = (goc if goc is not None else cau_hinh_dong.lay("ERPNEXT_URL")).rstrip("/")
        khoa = api_key if api_key is not None else cau_hinh_dong.lay("ERPNEXT_API_KEY")
        bi_mat = (
            api_secret if api_secret is not None else cau_hinh_dong.lay("ERPNEXT_API_SECRET")
        )
```

- [ ] **Step 4: Sửa `ghn.py`**

Trong `__init__`:

```python
        from agent import cau_hinh_dong

        self._api_url = (api_url or settings.ghn_api_url).rstrip("/")
        self._token = token or cau_hinh_dong.lay("GHN_TOKEN")
        self._shop_id = shop_id or cau_hinh_dong.lay("GHN_SHOP_ID")
```

Cuối file:

```python
async def kiem_ket_noi(
    *, token: str, shop_id: str, api_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str, int]:
    """
    Token có sống và shop id có thuộc tài khoản này không. CHỈ ĐỌC.

    `shop/all` là lời gọi rẻ nhất cần token mà không tạo gì. Tách riêng khỏi
    `GHNShippingProvider` để dashboard kiểm bằng giá trị CHƯA LƯU.
    """
    goc = (api_url or settings.ghn_api_url).rstrip("/")
    t0 = time.perf_counter()
    dong = client is None
    client = client or httpx.AsyncClient(timeout=15.0)
    try:
        r = await client.post(
            f"{goc}/shop/all",
            headers={"Token": token, "Content-Type": "application/json"},
            json={"offset": 0, "limit": 50},
        )
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: không nối được GHN", int((time.perf_counter() - t0) * 1000)
    finally:
        if dong:
            await client.aclose()
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code in (401, 403):
        return False, "GHN từ chối token", ms
    if r.status_code >= 400:
        return False, f"GHN {r.status_code}: {r.text[:120]}", ms
    shops = ((r.json().get("data") or {}).get("shops") or [])
    ids = {str(s.get("_id")) for s in shops}
    if shop_id and str(shop_id) not in ids:
        return False, f"token đúng nhưng shop id {shop_id} không thuộc tài khoản này", ms
    return True, f"{len(shops)} shop · {ms}ms", ms
```

Đảm bảo `import time` và `import httpx` có ở đầu `ghn.py`.

- [ ] **Step 5: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_ghn_kiem_ket_noi.py -q && .venv/Scripts/python.exe -m pytest -q -k "erp or van_chuyen or ghn" && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add agent/erp/erpnext.py agent/shipping/ghn.py tests/test_ghn_kiem_ket_noi.py
git commit -m "ERPNext và GHN đọc khoá qua cấu hình động; GHN kiểm được token bằng lời gọi chỉ đọc"
```

---

### Task 7: API `/api/cai-dat-api`

**Files:**
- Create: `agent/api/cai_dat_api.py`
- Test: `tests/test_api_cai_dat_api.py`

**Interfaces:**
- Consumes: `cau_hinh_dong` (Task 3), `llm.kiem_khoa` (Task 4), `NguonErpNext` (Task 6), `ghn.kiem_ket_noi` (Task 6), `bat_buoc_dang_nhap/bat_buoc_quan_tri` từ `agent/api/routes.py`.
- Produces: `router` (prefix `/api/cai-dat-api`), `async kiem_nhom(nhom: str, ghi_de: dict[str, str]) -> dict` (`{ok, chi_tiet, ms}`).

- [ ] **Step 1: Viết test hỏng**

```python
"""
API Cài đặt API: không lộ bí mật, kiểm không lưu, quản trị mới được ghi.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from agent import cau_hinh_dong as cd
from agent.api import cai_dat_api
from agent.api.routes import bat_buoc_dang_nhap, bat_buoc_quan_tri
from agent.security.credential_vault import CredentialVault


class _KhoGia:
    """Bản sao của kho giả trong test_cau_hinh_dong — thư mục tests không phải package."""

    def __init__(self):
        self.dong: dict[str, dict] = {}
        self.kiem: list = []

    async def doc_tat_ca(self):
        return [dict(khoa=k, **v) for k, v in self.dong.items()]

    async def ghi(self, khoa, sealed, sua_boi):
        self.dong[khoa] = dict(
            key_version=sealed.key_version, nonce=sealed.nonce,
            ciphertext=sealed.ciphertext, sua_boi=sua_boi, sua_luc=None,
            kiem_luc=None, kiem_ket_qua=None,
        )

    async def xoa(self, khoa):
        self.dong.pop(khoa, None)

    async def ghi_kiem(self, khoa, ket_qua):
        self.kiem.append((khoa, ket_qua))


@pytest.fixture
def kho(monkeypatch):
    k = _KhoGia()
    monkeypatch.setattr(cd, "_kho", k)
    monkeypatch.setattr(cd, "_vault", lambda: CredentialVault({1: bytes.fromhex("04" * 32)}, active_version=1))

    async def log_event(kind, **kw):
        pass

    monkeypatch.setattr(cd.db, "log_event", log_event)
    monkeypatch.setattr(cd, "_sau_khi_doi", lambda khoa: None)
    cd._gia_tri.clear(); cd._meta.clear()
    return k


def _app(*, admin: bool):
    app = FastAPI()
    app.include_router(cai_dat_api.router)
    user = {"id": uuid4(), "ten_dang_nhap": "a", "vai_tro": "quan_tri" if admin else "nhan_vien"}
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: user
    if admin:
        app.dependency_overrides[bat_buoc_quan_tri] = lambda: user
    else:
        def deny():
            raise HTTPException(403, "Việc này cần quyền quản trị")
        app.dependency_overrides[bat_buoc_quan_tri] = deny
    return TestClient(app)


def test_luu_roi_liet_ke_khong_lo_khoa(kho):
    c = _app(admin=True)
    r = c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "AIzaSyBIMAT-wxyz"})
    assert r.status_code == 204
    ds = c.get("/api/cai-dat-api")
    assert ds.status_code == 200
    assert "AIzaSyBIMAT-wxyz" not in ds.text
    muc = {m["khoa"]: m for m in ds.json()["muc"]}
    assert muc["GEMINI_API_KEY"]["hien"] == "···wxyz"
    assert muc["GEMINI_API_KEY"]["nguon"] == "csdl"


def test_nhan_vien_xem_duoc_nhung_khong_ghi_duoc(kho):
    c = _app(admin=False)
    assert c.get("/api/cai-dat-api").status_code == 200
    assert c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "x" * 20}).status_code == 403
    assert c.delete("/api/cai-dat-api/GEMINI_API_KEY").status_code == 403
    assert c.post("/api/cai-dat-api/kiem-tra", json={"nhom": "model"}).status_code == 403


def test_khoa_la_va_gia_tri_sai_bi_422(kho):
    c = _app(admin=True)
    assert c.put("/api/cai-dat-api/ERP_LOAI", json={"gia_tri": "erpnext"}).status_code == 422
    assert c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "openai"}).status_code == 422


def test_kiem_tra_dung_gia_tri_gui_len_va_khong_luu(kho, monkeypatch):
    nhan = {}

    async def kiem_khoa(*, provider_name, api_key="", model="", project="", timeout=45.0):
        nhan.update(provider_name=provider_name, api_key=api_key, model=model)
        return True, f"{model} · 12ms", 12

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    r = c.post("/api/cai-dat-api/kiem-tra", json={
        "nhom": "model",
        "gia_tri": {"LLM_PROVIDER": "gemini_api", "GEMINI_API_KEY": "CHUA-LUU", "MODEL_CHEAP": "gemini-2.5-flash-lite"},
    })
    assert r.status_code == 200 and r.json()["ok"] is True
    assert nhan["api_key"] == "CHUA-LUU" and nhan["provider_name"] == "gemini_api"
    assert kho.dong == {}, "kiểm tra không được lưu gì"


def test_kiem_tra_gia_tri_da_luu_thi_ghi_ket_qua(kho, monkeypatch):
    async def kiem_khoa(**kw):
        return False, "HẾT HẠN MỨC", 5

    monkeypatch.setattr(cai_dat_api.llm, "kiem_khoa", kiem_khoa)
    c = _app(admin=True)
    c.put("/api/cai-dat-api/LLM_PROVIDER", json={"gia_tri": "gemini_api"})
    c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "k" * 20})
    r = c.post("/api/cai-dat-api/kiem-tra", json={"nhom": "model"})
    assert r.json()["ok"] is False
    assert any(k == "GEMINI_API_KEY" and "HẾT HẠN MỨC" in kq for k, kq in kho.kiem)


def test_vault_chua_san_sang_thi_503_khi_ghi(kho, monkeypatch):
    def hong():
        raise cd.VaultChuaSanSang("chưa có CREDENTIAL_MASTER_KEYS")

    monkeypatch.setattr(cd, "_vault", hong)
    c = _app(admin=True)
    r = c.put("/api/cai-dat-api/GEMINI_API_KEY", json={"gia_tri": "x" * 20})
    assert r.status_code == 503 and "CREDENTIAL_MASTER_KEYS" in r.json()["detail"]
    assert c.get("/api/cai-dat-api").json()["vault_san_sang"] is False


def test_kiem_nhom_erp_dung_gia_tri_chua_luu(kho, monkeypatch):
    dung = {}

    class _Nguon:
        def __init__(self, **kw):
            dung.update(kw)

        async def suc_khoe(self):
            return True

    monkeypatch.setattr(cai_dat_api, "NguonErpNext", _Nguon)
    kq = asyncio.run(cai_dat_api.kiem_nhom("erp", {"ERPNEXT_URL": "https://e", "ERPNEXT_API_KEY": "k", "ERPNEXT_API_SECRET": "s"}))
    assert kq["ok"] and dung["goc"] == "https://e" and dung["api_secret"] == "s"
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_cai_dat_api.py -q`
Expected: FAIL `ModuleNotFoundError: agent.api.cai_dat_api`

- [ ] **Step 3: Viết router**

```python
"""
API cho mục Cài đặt API trên dashboard.

BA LUẬT
-------
1. Không có đường nào trả giá trị bí mật ra ngoài. `GET` chỉ trả bốn ký tự
   cuối; test đặt một khoá rồi tìm chuỗi ấy trong toàn bộ phản hồi.
2. `kiem-tra` chạy bằng giá trị NGƯỜI VỪA GÕ, gộp đè lên giá trị hiện hành,
   và KHÔNG lưu gì. Người dùng phải thấy khoá sống hay chết trước khi bấm Lưu.
3. Chỉ quản trị viên ghi; nhân viên xem được trạng thái để biết vì sao agent
   im lặng.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from agent import cau_hinh_dong
from agent.config import settings
from agent.core import llm
from agent.erp.erpnext import NguonErpNext
from agent.shipping import ghn

from .routes import bat_buoc_dang_nhap, bat_buoc_quan_tri

router = APIRouter(prefix="/api/cai-dat-api", tags=["cai-dat-api"])

NHOM_HOP_LE = ("model", "erp", "van_chuyen")


class GiaTriIn(BaseModel):
    gia_tri: str = Field(min_length=1, max_length=4000)


class KiemTraIn(BaseModel):
    nhom: str
    gia_tri: dict[str, str] = Field(default_factory=dict)


def _actor(user: dict) -> str:
    return str(user.get("ten_dang_nhap") or user.get("id") or "quan_tri")


def _hien_hanh(khoa: str, ghi_de: dict[str, str]) -> str:
    v = str(ghi_de.get(khoa) or "").strip()
    return v or cau_hinh_dong.lay(khoa)


async def kiem_nhom(nhom: str, ghi_de: dict[str, str]) -> dict[str, Any]:
    """Kiểm một nhóm bằng giá trị gửi lên đè lên hiện hành. Không lưu."""
    if nhom == "model":
        p = _hien_hanh("LLM_PROVIDER", ghi_de) or "gemini"
        khoa = _hien_hanh("GEMINI_API_KEY" if p == "gemini_api" else "ANTHROPIC_API_KEY", ghi_de)
        ok, chi_tiet, ms = await llm.kiem_khoa(
            provider_name=p,
            api_key=khoa if p in ("gemini_api", "anthropic") else "",
            model=_hien_hanh("MODEL_CHEAP", ghi_de) or settings.model_cheap,
        )
        return {"ok": ok, "chi_tiet": chi_tiet, "ms": ms}
    if nhom == "erp":
        try:
            nguon = NguonErpNext(
                goc=_hien_hanh("ERPNEXT_URL", ghi_de),
                api_key=_hien_hanh("ERPNEXT_API_KEY", ghi_de),
                api_secret=_hien_hanh("ERPNEXT_API_SECRET", ghi_de),
            )
            song = await nguon.suc_khoe()
        except ValueError as exc:
            # Adapter tự kiểm cấu hình lúc dựng và nói rõ thiếu gì.
            return {"ok": False, "chi_tiet": str(exc)[:200], "ms": 0}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "chi_tiet": f"{type(exc).__name__}: {exc}"[:200], "ms": 0}
        return {"ok": bool(song), "chi_tiet": "ERPNext xác thực được" if song else "ERPNext từ chối xác thực", "ms": 0}
    if nhom == "van_chuyen":
        ok, chi_tiet, ms = await ghn.kiem_ket_noi(
            token=_hien_hanh("GHN_TOKEN", ghi_de),
            shop_id=_hien_hanh("GHN_SHOP_ID", ghi_de),
        )
        return {"ok": ok, "chi_tiet": chi_tiet, "ms": ms}
    raise HTTPException(422, f"nhóm không hợp lệ: {nhom!r}")


@router.get("")
async def liet_ke(_: dict = Depends(bat_buoc_dang_nhap)) -> dict[str, Any]:
    return {"muc": cau_hinh_dong.liet_ke(), "vault_san_sang": cau_hinh_dong.vault_san_sang()}


@router.put("/{khoa}", status_code=status.HTTP_204_NO_CONTENT)
async def dat(khoa: str, body: GiaTriIn, user: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await cau_hinh_dong.dat(khoa, body.gia_tri, sua_boi=_actor(user))
    except cau_hinh_dong.KhoaKhongHopLe as exc:
        raise HTTPException(422, str(exc)) from exc
    except cau_hinh_dong.VaultChuaSanSang as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{khoa}", status_code=status.HTTP_204_NO_CONTENT)
async def xoa(khoa: str, user: dict = Depends(bat_buoc_quan_tri)) -> Response:
    try:
        await cau_hinh_dong.xoa(khoa, sua_boi=_actor(user))
    except cau_hinh_dong.KhoaKhongHopLe as exc:
        raise HTTPException(422, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/kiem-tra")
async def kiem_tra(body: KiemTraIn, _: dict = Depends(bat_buoc_quan_tri)) -> dict[str, Any]:
    if body.nhom not in NHOM_HOP_LE:
        raise HTTPException(422, f"nhóm không hợp lệ: {body.nhom!r}")
    ket = await kiem_nhom(body.nhom, body.gia_tri)
    # Chỉ ghi kết quả khi kiểm cấu hình ĐÃ LƯU: ghi "đạt" cho một khoá đang
    # lưu trong khi thứ vừa đạt là khoá chưa lưu là nói dối trên dashboard.
    if not body.gia_tri:
        for mo_ta in cau_hinh_dong.DANH_MUC.values():
            if mo_ta.nhom == body.nhom and mo_ta.bi_mat:
                await cau_hinh_dong.ghi_ket_qua_kiem(mo_ta.khoa, ket["ok"], ket["chi_tiet"])
    return ket
```

- [ ] **Step 4: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_cai_dat_api.py -q && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/api/cai_dat_api.py tests/test_api_cai_dat_api.py
git commit -m "API Cài đặt API: liệt kê không lộ khoá, kiểm bằng giá trị chưa lưu, quản trị mới được ghi"
```

---

### Task 8: Nối vào ứng dụng

**Files:**
- Modify: `agent/main.py` (import router gần dòng 36-62; `lifespan` sau `await runtime.nap()` ~462; `include_router` ~787)
- Test: `tests/test_api_cai_dat_api.py` (thêm 2 test)

- [ ] **Step 1: Thêm test hỏng**

Thêm vào cuối `tests/test_api_cai_dat_api.py`:

```python
def test_router_duoc_gan_vao_app():
    from agent.main import app

    duong = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/api/cai-dat-api" in duong
    assert "/api/cai-dat-api/kiem-tra" in duong


def test_lifespan_nap_cau_hinh_dong_sau_runtime():
    import inspect

    from agent import main

    than = inspect.getsource(main.lifespan)
    assert "cau_hinh_dong.nap()" in than
    assert than.index("runtime.nap()") < than.index("cau_hinh_dong.nap()")
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_cai_dat_api.py -q -k "router_duoc_gan or lifespan_nap"`
Expected: FAIL.

- [ ] **Step 3: Sửa `main.py`**

Import: `from agent import cau_hinh_dong` cạnh `from agent import db, nhat_ky, runtime`; và `from agent.api.cai_dat_api import router as cai_dat_api_router` cạnh các import router khác.

Trong `lifespan`, ngay sau `await runtime.nap()`:

```python
    # Khoá API nhập từ dashboard. Nạp SAU runtime và TRƯỚC dòng app.start,
    # cùng lý do với runtime: nhật ký khởi động phải nói đúng provider đang chạy.
    await cau_hinh_dong.nap()
```

Sau `app.include_router(zalo_personal_webhook_router)`: `app.include_router(cai_dat_api_router)`.

- [ ] **Step 4: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_cai_dat_api.py tests/test_dich_vu_khoi_dong_duoc.py -q && .venv/Scripts/python.exe -m ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/main.py tests/test_api_cai_dat_api.py
git commit -m "Nạp khoá API từ CSDL lúc khởi động và mở router Cài đặt API"
```

---

### Task 9: Dashboard — panel Cài đặt API

**Files:**
- Modify: `dashboard/index.html:450-452` (chèn panel đầu view `cauhinh`)
- Modify: `dashboard/app.js:1955` (loader) và thêm khối hàm sau `loadCauHinh` (~3062)
- Test: `tests/test_dashboard_cai_dat_api.py`

**Interfaces:**
- Consumes: `GET/PUT/DELETE /api/cai-dat-api`, `POST /api/cai-dat-api/kiem-tra` (Task 7).

- [ ] **Step 1: Viết test hỏng**

```python
"""
Panel Cài đặt API: ô bí mật không bao giờ mang giá trị, có Kiểm tra và Lưu.
Kiểm bằng đọc mã (regex), cùng cách với tests/test_dashboard_khong_nhap_nhay.py.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _than_ham(ten: str) -> str:
    m = re.search(rf"(?:async )?function {ten}\(.*?\n\}}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def test_panel_nam_trong_man_cau_hinh():
    assert 'id="api-panel"' in HTML
    assert HTML.index('id="api-panel"') > HTML.index('data-view="cauhinh"')
    assert HTML.index('id="api-panel"') < HTML.index('id="cauhinh-ds"')


def test_o_bi_mat_la_password_va_khong_co_value():
    than = _than_ham("oNhapApi")
    the_password = re.search(r'<input type="password"[^>]*>', than, re.S)
    assert the_password, "ô bí mật phải là input type=password"
    # Không dựng thuộc tính value cho ô bí mật: giá trị không có ở client để mà dựng.
    assert "value=" not in the_password.group(0)
    assert 'autocomplete="off"' in the_password.group(0)


def test_co_nut_kiem_tra_va_luu_theo_nhom():
    than = _than_ham("loadCaiDatApi")
    assert "data-api-kiem" in than and "data-api-luu" in than


def test_kiem_tra_gui_gia_tri_dang_go_chua_luu():
    # Kiểm phải gửi thứ đang gõ (giaTriApiDangGo), không gửi cấu hình đã lưu.
    assert re.search(r"/cai-dat-api/kiem-tra[\s\S]{0,300}giaTriApiDangGo\(", JS)


def test_loader_goi_khi_mo_man_cau_hinh():
    assert re.search(r'state\.view === "cauhinh"[\s\S]{0,120}loadCaiDatApi\(\)', JS)


def test_khong_tu_kiem_khi_mo_trang():
    """Mỗi lần kiểm là một lượt gọi tốn tiền; chỉ chạy khi người bấm."""
    than = _than_ham("loadCaiDatApi")
    assert "kiem-tra" not in than
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_cai_dat_api.py -q`
Expected: FAIL.

- [ ] **Step 3: `index.html`** — chèn ngay sau `<section class="view" data-view="cauhinh">`:

```html
      <section class="panel" id="api-panel">
        <h2 class="panel__head">Cài đặt API
          <span class="panel__note" id="api-vault"></span></h2>
        <p class="panel__note">
          Khoá dán ở đây được mã hoá trong cơ sở dữ liệu và có hiệu lực ngay,
          không cần khởi động lại. Khoá không bao giờ hiện lại — chỉ bốn ký tự
          cuối. Chưa đặt ở đây thì hệ thống dùng <code>.env</code>. Bấm
          <b>Kiểm tra</b> trước khi <b>Lưu</b>: kiểm chạy bằng đúng thứ bạn
          vừa gõ.
        </p>
        <div id="api-nhom" class="rows"><p class="empty">Đang tải…</p></div>
      </section>
```

- [ ] **Step 4: `app.js`**

Đổi dòng `if (state.view === "cauhinh") await loadCauHinh();` thành
`if (state.view === "cauhinh") { await loadCauHinh(); await loadCaiDatApi(); }`.

Thêm sau khối cấu hình agent:

```js
/* ---------------- cài đặt API ---------------- */

const API_NHOM = { model: "Model ngôn ngữ", erp: "ERP (ERPNext)", van_chuyen: "Vận chuyển (GHN)" };

/* Ô nhập cho một khoá. Ô BÍ MẬT là password và KHÔNG có value: giá trị
 * không có ở client để mà dựng — máy chủ chỉ gửi bốn ký tự cuối. */
function oNhapApi(m) {
  if (m.chon && m.chon.length) {
    return `<select data-api-khoa="${m.khoa}">${
      m.chon.map((c) => `<option value="${esc(c)}"${c === m.hien ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  if (m.bi_mat) {
    return `<input type="password" autocomplete="off" data-api-khoa="${m.khoa}"
      placeholder="${m.da_dat ? `đã đặt ${esc(m.hien)} — dán khoá mới để thay` : "chưa đặt — dán khoá vào đây"}">`;
  }
  return `<input type="text" data-api-khoa="${m.khoa}" value="${esc(m.hien || "")}"
    placeholder="${esc(m.nhan)}">`;
}

function trangThaiApi(m) {
  const nguon = { csdl: "từ dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  const kiem = m.kiem_ket_qua ? ` · kiểm ${new Date(m.kiem_luc).toLocaleString("vi-VN")}: ${esc(m.kiem_ket_qua)}` : "";
  return `<span class="row__sub">${nguon}${kiem}</span>`;
}

async function loadCaiDatApi() {
  const d = await api("/cai-dat-api");
  $("#api-vault").textContent = d.vault_san_sang ? "mã hoá AES-256 trong CSDL" : "vault chưa cấu hình — chỉ xem được";
  const nhom = {};
  for (const m of d.muc) (nhom[m.nhom] ||= []).push(m);
  $("#api-nhom").innerHTML = Object.entries(API_NHOM).map(([ma, ten]) => `
    <div class="row" data-api-nhom="${ma}">
      <span class="row__flag ${(nhom[ma] || []).some((m) => m.da_dat) ? "row__flag--auto" : ""}"></span>
      <span class="row__body">
        <span class="row__title">${esc(ten)}</span>
        ${(nhom[ma] || []).map((m) => `<div class="rows" style="margin:.35rem 0">
          <label class="row__sub">${esc(m.nhan)}${m.y_nghia ? ` — ${esc(m.y_nghia)}` : ""}</label>
          ${oNhapApi(m)} ${trangThaiApi(m)}
        </div>`).join("")}
        <div class="rowbtns">
          <button type="button" class="btn btn--sm" data-api-kiem="${ma}">Kiểm tra</button>
          <button type="button" class="btn btn--sm btn--auto" data-api-luu="${ma}">Lưu</button>
          <span class="row__sub" data-api-kq="${ma}"></span>
        </div>
      </span>
    </div>`).join("");
}

/* Gom giá trị đang gõ trong một nhóm; bỏ ô trống để không ghi đè khoá đã
 * lưu bằng chuỗi rỗng. */
function giaTriApiDangGo(ma) {
  const ra = {};
  document.querySelectorAll(`[data-api-nhom="${ma}"] [data-api-khoa]`).forEach((o) => {
    const v = (o.value || "").trim();
    if (v) ra[o.dataset.apiKhoa] = v;
  });
  return ra;
}

document.addEventListener("click", async (e) => {
  const kiem = e.target.closest("[data-api-kiem]");
  const luu = e.target.closest("[data-api-luu]");
  if (!kiem && !luu) return;
  const ma = (kiem || luu).dataset.apiKiem || (kiem || luu).dataset.apiLuu;
  const kq = $(`[data-api-kq="${ma}"]`);
  try {
    if (kiem) {
      kq.textContent = "đang kiểm…";
      const r = await api("/cai-dat-api/kiem-tra", {
        method: "POST", body: JSON.stringify({ nhom: ma, gia_tri: giaTriApiDangGo(ma) }),
      });
      kq.textContent = (r.ok ? "✓ " : "✗ ") + r.chi_tiet;
      return;
    }
    const gia_tri = giaTriApiDangGo(ma);
    for (const [khoa, v] of Object.entries(gia_tri)) {
      await api(`/cai-dat-api/${khoa}`, { method: "PUT", body: JSON.stringify({ gia_tri: v }) });
    }
    toast(`Đã lưu ${Object.keys(gia_tri).length} khoá — có hiệu lực ngay`);
    await loadCaiDatApi();
  } catch (err) {
    kq.textContent = "";
    toast(err.message, true);
  }
});
```

Kiểm `api()` trả gì với 204: nếu helper cố `res.json()` trên 204 và ném, thì bọc lời gọi PUT như các chỗ khác trong file đã làm với 204 (tìm `status === 204` trong `api()`); nếu chưa có, thêm vào `api()`: `if (res.status === 204) return null;` trước khi parse.

- [ ] **Step 5: Chạy test, xanh**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dashboard_cai_dat_api.py tests/test_javascript_chay_duoc.py tests/test_dashboard_khong_nhap_nhay.py -q`
Expected: PASS (đặc biệt `test_app_js_khong_hong_cu_phap`).

- [ ] **Step 6: Xem bằng mắt**

Chạy app (`python -m scripts.khoi_dong --khong-tunnel` nếu chưa chạy), mở dashboard → Cấu hình. Panel hiện ba thẻ; ô bí mật rỗng với placeholder "đã đặt ···abcd"; bấm Kiểm tra với ô trống kiểm cấu hình đang dùng. Chụp màn hình gửi chủ dự án.

- [ ] **Step 7: Commit**

```bash
git add dashboard/index.html dashboard/app.js tests/test_dashboard_cai_dat_api.py
git commit -m "Dashboard: panel Cài đặt API — kiểm trước, lưu sau, khoá không bao giờ hiện lại"
```

---

### Task 10: `san_sang` — mục Khoá API

**Files:**
- Modify: `scripts/san_sang.py` (thêm hàm trước `kiem_outbox`, thêm vào `chay()`)
- Test: `tests/test_san_sang_khoa_api.py`

**Interfaces:**
- Produces: `san_sang.doc_khoa_api(provider: str, nguon_khoa: str, co_khoa: bool, giai_ma_hong: int) -> dict`, `async kiem_khoa_api() -> dict`.

- [ ] **Step 1: Viết test hỏng**

```python
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402


def test_provider_can_khoa_ma_khong_co_thi_CHAN():
    kq = san_sang.doc_khoa_api("gemini_api", "trong", False, 0)
    assert kq["muc"] == san_sang.CHAN and "Cài đặt API" in kq["sua"]


def test_co_khoa_tu_csdl_thi_DU_va_noi_nguon():
    kq = san_sang.doc_khoa_api("anthropic", "csdl", True, 0)
    assert kq["muc"] == san_sang.DU and "dashboard" in kq["ghi"]


def test_vertex_khong_can_khoa():
    assert san_sang.doc_khoa_api("gemini", "trong", False, 0)["muc"] == san_sang.DU


def test_giai_ma_hong_thi_CHAN():
    kq = san_sang.doc_khoa_api("gemini_api", "csdl", True, 2)
    assert kq["muc"] == san_sang.CHAN and "khoá chủ" in kq["sua"]


def test_nam_trong_bang_tong():
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    assert "kiem_khoa_api()" in nguon.split("async def chay()", 1)[1]
```

- [ ] **Step 2: Chạy, xác nhận hỏng**

Run: `.venv/Scripts/python.exe -m pytest tests/test_san_sang_khoa_api.py -q`
Expected: FAIL.

- [ ] **Step 3: Thêm vào `san_sang.py`** (trước `async def kiem_outbox`):

```python
def doc_khoa_api(provider: str, nguon_khoa: str, co_khoa: bool, giai_ma_hong: int) -> dict:
    ten = "Khoá API"
    if giai_ma_hong:
        return _muc(
            ten, CHAN, f"{giai_ma_hong} khoá trong CSDL không giải mã được",
            "Khoá chủ vault đã đổi. Nhập lại khoá ở dashboard → Cấu hình → Cài đặt API, "
            "hoặc khôi phục CREDENTIAL_MASTER_KEYS cũ",
        )
    can_khoa = provider in ("gemini_api", "anthropic")
    if can_khoa and not co_khoa:
        return _muc(
            ten, CHAN, f"provider {provider} cần API key mà không có ở đâu cả",
            "Nhập ở dashboard → Cấu hình → Cài đặt API (hoặc .env). Không có thì agent "
            "không trả lời được một tin nào",
        )
    nguon = {"csdl": "khoá từ dashboard", "env": "khoá từ .env", "trong": "không cần khoá"}[nguon_khoa]
    return _muc(ten, DU, f"provider {provider} · {nguon}")


async def kiem_khoa_api() -> dict:
    """Provider hiện hành có khoá không, và khoá lấy từ đâu."""
    from agent import cau_hinh_dong, db

    try:
        await db.init_db()
        await cau_hinh_dong.nap()
        hong = await db.fetchrow(
            "SELECT count(*) AS n FROM events WHERE kind = 'cau_hinh_api.giai_ma_hong' "
            "AND created_at > now() - interval '10 minutes'"
        )
        giai_ma_hong = int(hong["n"]) if hong else 0
    except Exception:  # noqa: BLE001 — không có CSDL thì vẫn đọc được .env
        giai_ma_hong = 0
    provider = (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").lower()
    khoa = "GEMINI_API_KEY" if provider == "gemini_api" else "ANTHROPIC_API_KEY"
    if provider in ("gemini_api", "anthropic"):
        return doc_khoa_api(provider, cau_hinh_dong.nguon(khoa), bool(cau_hinh_dong.lay(khoa)), giai_ma_hong)
    return doc_khoa_api(provider, "trong", False, giai_ma_hong)
```

Trong `chay()`, thêm `await kiem_khoa_api(),` ngay sau `kiem_bi_mat(),`.

- [ ] **Step 4: Chạy test, xanh; chạy `san_sang` thật**

Run: `.venv/Scripts/python.exe -m pytest tests/test_san_sang_khoa_api.py tests/test_san_sang*.py -q && PYTHONUTF8=1 .venv/Scripts/python.exe -m scripts.san_sang | grep "Khoá API"`
Expected: PASS; dòng `Khoá API` hiện đúng provider.

- [ ] **Step 5: Commit**

```bash
git add scripts/san_sang.py tests/test_san_sang_khoa_api.py
git commit -m "san_sang biết provider đang chạy có khoá không và khoá lấy từ đâu"
```

---

### Task 11: Tài liệu, kiểm toàn bộ, đẩy lên

**Files:**
- Modify: `docs/van-hanh.md` (thêm mục sau "Bật cổng ERP"), `.env.example:5-13`
- Regenerate: `docs/kien-truc.md` (nếu chưa ở Task 2)

- [ ] **Step 1: `docs/van-hanh.md`** — thêm mục:

```markdown
## Nhập khoá API trên dashboard

Cấu hình → **Cài đặt API**. Ba thẻ: Model, ERP, Vận chuyển. Khoá được mã
hoá trong CSDL bằng vault của tài khoản kênh và có hiệu lực ngay. `.env`
vẫn là đường lui: chưa đặt ở dashboard thì hệ thống dùng `.env`.

Thứ tự đúng: **Kiểm tra → Lưu**. Kiểm chạy bằng đúng thứ bạn vừa gõ,
chưa lưu gì; "HẾT HẠN MỨC" nghĩa là khoá đúng nhưng nhà cung cấp từ chối.

**Đổi provider sang `gemini_api`** (chỉ cần API key, không cần gcloud): kho
tri thức phải **nạp lại** vì model embedding đổi. Màn Sức khoẻ có dòng
*Embedding kho tri thức* báo đỏ cho tới khi nạp lại — đừng bỏ qua, tìm
kiếm sẽ sai mà không lỗi.

Khoá chủ vault (`CREDENTIAL_MASTER_KEYS`) đổi thì mọi khoá đã lưu không
mở được: `san_sang` mục *Khoá API* chặn, nhật ký có
`cau_hinh_api.giai_ma_hong`. Nhập lại khoá là xong.
```

- [ ] **Step 2: `.env.example`** — thay khối Model:

```
# --- Model và Google Cloud ------------------------------------
# Các khoá dưới đây NHẬP ĐƯỢC trên dashboard (Cấu hình → Cài đặt API) và khi
# đó bản trong CSDL thắng .env. Ở đây chỉ là đường lui cho máy chưa vào dashboard.
# gemini_api: chỉ cần GEMINI_API_KEY (Google AI Studio), không cần GCP.
# gemini / vertex: cần GCP_PROJECT_ID và `gcloud auth application-default login`.
LLM_PROVIDER=gemini_api
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
GCP_PROJECT_ID=your-gcp-project-id
GCP_REGION=global
GEMINI_REGION=us-central1
MODEL_CHAT=gemini-2.5-flash
MODEL_HARD=gemini-2.5-pro
MODEL_CHEAP=gemini-2.5-flash-lite
```

Trường `gemini_api_key` trong `agent/config.py` đã thêm ở Task 3. Nếu có test canh `.env.example` khớp `Settings` thì chạy nó.

**Lưu ý:** đổi mặc định `LLM_PROVIDER` trong `.env.example` sang `gemini_api` chỉ ảnh hưởng máy clone mới; máy đang chạy giữ `.env` của mình.

- [ ] **Step 3: Toàn bộ kiểm**

Run:
```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
PYTHONUTF8=1 .venv/Scripts/python.exe -m scripts.sinh_so_do --ghi
```
Expected: xanh hết, sạch, tài liệu không đổi thêm (hoặc đổi thì commit).

- [ ] **Step 4: Clone sạch trong container Linux** (đúng như CI):

```bash
cd "$TMPDIR" && rm -rf clone-linux && git clone -q "/d/Marketing Dasbhboard CSKH" clone-linux && cd clone-linux && MSYS_NO_PATHCONV=1 docker run --rm -v "$(pwd -W):/w" -w /w -e PYTHONUTF8=1 python:3.12 bash -c "pip install -q -r requirements.txt && python -m pytest tests/ -q | tail -3"
```
Expected: `passed`, không `failed`/`error`.

- [ ] **Step 5: Commit và đẩy**

```bash
git add docs/van-hanh.md .env.example agent/config.py docs/kien-truc.md
git commit -m "Tài liệu Cài đặt API: thứ tự kiểm rồi lưu, đổi provider thì nạp lại kho tri thức"
git push origin main
```

Theo dõi CI qua API công khai (xem lệnh trong lịch sử phiên 04.09) tới khi cả `pytest` và `clone-sach` success.

- [ ] **Step 6: Bật lại app để nạp mã mới**

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from scripts import khoi_dong as k; print(k.buoc_app(bat_lai=True))"
```
Rồi mở dashboard → Cấu hình → Cài đặt API, bấm **Kiểm tra** nhóm Model với ô trống: phải ra kết quả của cấu hình đang dùng.
