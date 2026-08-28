# Cổng kho/ERP — Giai đoạn 1: lõi và adapter tệp

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng lõi cổng ERP cắm được — hợp đồng dữ liệu, adapter đọc tệp, cache theo tuổi, ngắt mạch — để `_catalog_song()` không còn đọc thẳng file, mà mọi hành vi vẫn kiểm chứng được đầy đủ không cần một instance ERP nào.

**Architecture:** Một `Protocol NguonERP` với bốn phương thức. `Cong` bọc nguồn đó, thêm cache có tuổi và ngắt mạch, rồi hợp nhất nửa thương mại (từ nguồn) với nửa tư vấn (từ `catalog.json`). `tools._catalog()` giữ nguyên chữ ký `-> dict` nên agent, RAG, MCP và bảy chốt lên đơn không đổi một dòng.

**Tech Stack:** Python 3.12, `dataclass` + `typing.Protocol`, pydantic-settings (`agent/config.py`), pytest 9.1.1 (**không có pytest-asyncio**), ruff.

**Spec:** `docs/superpowers/specs/2026-08-28-cong-kho-erp-design.md`

## Global Constraints

- Mọi mã, chú thích, tên hàm, tên biến và tài liệu viết bằng **tiếng Việt**. Không đổi ngôn ngữ.
- Chú thích giải thích **VÌ SAO**, không giải thích LÀM GÌ — nhất là lý do không làm theo cách hiển nhiên hơn.
- **Mỗi ràng buộc phải có test canh.** Không có test thì nó sẽ bị gỡ trong một lần dọn dẹp nào đó.
- **Repo KHÔNG cài `pytest-asyncio`.** Viết `async def test_...` là hỏng ngay lúc chạy: *"Failed: async def functions are not natively supported"*. Mọi test bất đồng bộ phải là hàm **đồng bộ** gọi `asyncio.run(...)`, đúng như 117 file test hiện có. Helper `chay()` dựng ở Task 2 và dùng cho toàn bộ các task sau.
- Toàn bộ `pytest -q` phải chạy **dưới 4 giây và không gọi API nào**. Cấm `asyncio.sleep` trong test — thời gian tiêm vào bằng đồng hồ giả.
- `ruff check .` phải sạch sau mỗi commit.
- `ERP_LOAI` mặc định là `tep`. Máy vừa clone về, không có `.env`, không có `catalog.json` vẫn phải chạy được (rơi về `catalog.example.json`).
- `agent/core/tools.py::_catalog()` **giữ nguyên chữ ký `-> dict`** và giữ nguyên các khoá `san_pham` / `don_hang`.
- Test đặt phẳng trong `tests/`, tên `test_<tiếng_việt>.py`, theo đúng quy ước 117 file hiện có.
- Không sửa `agent/omnichannel/outbox.py` trong giai đoạn này.
- Trên máy này `python` trần không thấy pytest. Dùng `./.venv/Scripts/python.exe -m pytest`.

---

### Task 1: Hợp đồng dữ liệu

**Files:**
- Create: `agent/erp/__init__.py`
- Create: `agent/erp/hop_dong.py`
- Test: `tests/test_hop_dong_erp.py`

**Interfaces:**
- Consumes: không
- Produces:
  - `Gia(gia_ban: int, don_vi: str = "VND", nguon: str = "", hieu_luc_den: str | None = None)`
  - `TonKho(ban_duoc: int, ma_kho: str = "")`
  - `SanPhamERP(ma: str, ten: str, loai: str = "", dung_tich: str = "", ban_duoc_phep: bool = True)`
  - `KetQuaDon(thanh_cong: bool, erp_ma_don: str = "", ly_do: str = "")`
  - `class NguonERP(Protocol)` với `ten: str`, `async danh_sach_san_pham(chi_ban_duoc: bool = True) -> list[SanPhamERP]`, `async gia(ma: str) -> Gia | None`, `async ton_kho(ma: str) -> TonKho | None`, `async suc_khoe() -> bool`
  - `class LoiERP(RuntimeError)`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_hop_dong_erp.py`:

```python
"""Hợp đồng dữ liệu của cổng ERP.

Test canh hai điều dễ trượt nhất: `Gia` phải là một VẬT chứ không phải một
số nguyên (vì giá thật phụ thuộc bảng giá, và ta cần truy vết nguồn), và
`TonKho.ban_duoc` phải là hàng BÁN ĐƯỢC chứ không phải hàng có trong kho.
"""
import dataclasses

import pytest

from agent.erp.hop_dong import Gia, KetQuaDon, LoiERP, NguonERP, SanPhamERP, TonKho


def test_gia_la_vat_khong_phai_so():
    # Giá thật phụ thuộc bảng giá; trả về int trần là mất đường truy vết
    # khi khách thắc mắc "sao báo giá này".
    g = Gia(gia_ban=245_000, nguon="Bảng giá bán lẻ")
    assert g.gia_ban == 245_000
    assert g.don_vi == "VND"
    assert g.nguon == "Bảng giá bán lẻ"
    assert g.hieu_luc_den is None


def test_gia_bat_bien():
    # Bất biến để không ai lỡ tay sửa giá sau khi cổng đã trả ra.
    g = Gia(gia_ban=100)
    with pytest.raises(dataclasses.FrozenInstanceError):
        g.gia_ban = 1


def test_ton_kho_la_hang_ban_duoc():
    t = TonKho(ban_duoc=7, ma_kho="KHO-HN")
    assert t.ban_duoc == 7
    assert t.ma_kho == "KHO-HN"


def test_san_pham_mac_dinh_duoc_phep_ban():
    sp = SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt")
    assert sp.ban_duoc_phep is True


def test_ket_qua_don_that_bai_phai_co_ly_do():
    kq = KetQuaDon(thanh_cong=False, ly_do="ERP từ chối: hết hàng")
    assert kq.thanh_cong is False
    assert kq.erp_ma_don == ""
    assert "hết hàng" in kq.ly_do


def test_loi_erp_la_runtime_error():
    assert issubclass(LoiERP, RuntimeError)


class _NguonToiThieu:
    ten = "toi_thieu"

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        return []

    async def gia(self, ma: str):
        return None

    async def ton_kho(self, ma: str):
        return None

    async def suc_khoe(self) -> bool:
        return True


def test_protocol_nhan_dien_duoc_nguon_hop_le():
    # runtime_checkable để `san_sang.py` kiểm được adapter nạp từ .env có đủ
    # bốn phương thức hay không, TRƯỚC khi khách nhắn tin đầu tiên.
    assert isinstance(_NguonToiThieu(), NguonERP)


def test_protocol_tu_choi_nguon_thieu_phuong_thuc():
    class _Thieu:
        ten = "thieu"

        async def gia(self, ma: str):
            return None

    assert not isinstance(_Thieu(), NguonERP)
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_hop_dong_erp.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'agent.erp'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Tạo `agent/erp/__init__.py`:

```python
"""Cổng kết nối kho / ERP.

Xem thiết kế: docs/superpowers/specs/2026-08-28-cong-kho-erp-design.md
"""
```

Tạo `agent/erp/hop_dong.py`:

```python
"""
Hợp đồng dữ liệu giữa hệ thống và kho/ERP.

VÌ SAO CÓ LỚP NÀY
-----------------
Odoo nói XML-RPC và gọi sản phẩm là `product.product`. ERPNext nói REST và
gọi nó là `Item`. Nếu `tools.py` biết điều đó thì đổi ERP là viết lại agent.

Hợp đồng ở đây là thứ DUY NHẤT phần còn lại của hệ thống được biết. Mỗi
adapter tự lo phần bẩn của ERP nó phục vụ.

VÌ SAO `Gia` LÀ MỘT VẬT, KHÔNG PHẢI MỘT `int`
---------------------------------------------
Cả Odoo lẫn ERPNext đều có bảng giá: giá phụ thuộc nhóm khách, số lượng,
ngày, khuyến mãi. Trả về `int` trần là vứt mất `nguon` — và khi khách hỏi
"sao lại báo giá này" thì không ai truy được nó đến từ bảng giá nào.

VÌ SAO `TonKho.ban_duoc` CHỨ KHÔNG PHẢI `ton_kho`
-------------------------------------------------
Hàng có trong kho khác hàng bán được: một phần đã bị đơn khác giữ chỗ.
Odoo gọi phần bán được là `free_qty`; ERPNext là `actual_qty - reserved_qty`.
Lấy nhầm sang tổng tồn là hứa bán món đã có người đặt. Đặt tên trường theo
đúng ý nghĩa để không ai gán nhầm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LoiERP(RuntimeError):
    """Gọi ERP không thành. Cổng bắt lỗi này để quyết định trả `None`."""


@dataclass(frozen=True)
class Gia:
    """Giá bán một sản phẩm, kèm nguồn để truy vết."""

    gia_ban: int
    don_vi: str = "VND"
    nguon: str = ""
    hieu_luc_den: str | None = None


@dataclass(frozen=True)
class TonKho:
    """Số lượng BÁN ĐƯỢC (đã trừ phần bị giữ chỗ), tại một kho."""

    ban_duoc: int
    ma_kho: str = ""


@dataclass(frozen=True)
class SanPhamERP:
    """Nửa thương mại của một sản phẩm. Nửa tư vấn nằm ở kho nội bộ."""

    ma: str
    ten: str
    loai: str = ""
    dung_tich: str = ""
    ban_duoc_phep: bool = True


@dataclass(frozen=True)
class KetQuaDon:
    """Kết quả đẩy một đơn sang ERP. Dùng ở giai đoạn 4."""

    thanh_cong: bool
    erp_ma_don: str = ""
    ly_do: str = ""


@runtime_checkable
class NguonERP(Protocol):
    """Bốn việc mọi adapter phải làm được. Không hơn.

    Giữ hợp đồng nhỏ là cố ý: mỗi phương thức thêm vào là một phương thức
    phải hiện thực đúng bốn lần và test đúng bốn lần.
    """

    ten: str

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]: ...

    async def gia(self, ma: str) -> Gia | None: ...

    async def ton_kho(self, ma: str) -> TonKho | None: ...

    async def suc_khoe(self) -> bool: ...
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_hop_dong_erp.py -q`
Kỳ vọng: PASS, 8 test

Chạy: `ruff check agent/erp tests/test_hop_dong_erp.py`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/__init__.py agent/erp/hop_dong.py tests/test_hop_dong_erp.py
git commit -m "Hợp đồng dữ liệu ERP — giá là một vật, tồn kho là hàng bán được"
```

---

### Task 2: Adapter tệp, nguồn giả, và helper `chay()`

**Files:**
- Create: `agent/erp/tep.py`
- Create: `tests/erp_gia.py`
- Test: `tests/test_nguon_tep.py`

**Interfaces:**
- Consumes: `agent.erp.hop_dong.{Gia, TonKho, SanPhamERP, LoiERP, NguonERP}`
- Produces:
  - `agent.erp.tep.NguonTep(duong_dan: pathlib.Path | None = None)` — hiện thực `NguonERP`, `ten = "tep"`
  - `agent.erp.tep.CATALOG`, `agent.erp.tep.CATALOG_MAU` — hai `pathlib.Path`
  - `tests.erp_gia.chay(coro)` — chạy coroutine trong test đồng bộ
  - `tests.erp_gia.NguonGia(san_pham=None, gia=None, ton=None, hong=False)` với thuộc tính `san_pham`, `bang_gia`, `bang_ton`, `hong`, `so_lan_goi: dict[str, int]`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/erp_gia.py`:

```python
"""Nguồn ERP giả + helper chạy coroutine. Không gọi mạng, không ngủ.

VÌ SAO CÓ `chay()` THAY VÌ `async def test_...`
-----------------------------------------------
Repo này KHÔNG cài `pytest-asyncio` (xem requirements.txt). Viết
`async def test_...` là hỏng ngay lúc chạy:

    Failed: async def functions are not natively supported.

117 file test hiện có đều dùng `asyncio.run`. Giữ nguyên quy ước đó.

Độ trễ mô phỏng bằng ĐỒNG HỒ TIÊM VÀO chứ không bằng `asyncio.sleep`, vì
toàn bộ bộ test phải chạy dưới 4 giây.
"""
from __future__ import annotations

import asyncio

from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho


def chay(coro):
    """Chạy một coroutine trong hàm test đồng bộ."""
    return asyncio.run(coro)


class NguonGia:
    ten = "gia"

    def __init__(
        self,
        san_pham: list[SanPhamERP] | None = None,
        gia: dict[str, Gia] | None = None,
        ton: dict[str, TonKho] | None = None,
        hong: bool = False,
    ):
        self.san_pham = san_pham or []
        self.bang_gia = gia or {}
        self.bang_ton = ton or {}
        self.hong = hong
        self.so_lan_goi: dict[str, int] = {}

    def _dem(self, ten_ham: str) -> None:
        self.so_lan_goi[ten_ham] = self.so_lan_goi.get(ten_ham, 0) + 1
        if self.hong:
            raise LoiERP("ERP giả đang được đặt là hỏng")

    async def danh_sach_san_pham(self, chi_ban_duoc: bool = True):
        self._dem("danh_sach_san_pham")
        if chi_ban_duoc:
            return [sp for sp in self.san_pham if sp.ban_duoc_phep]
        return list(self.san_pham)

    async def gia(self, ma: str):
        self._dem("gia")
        return self.bang_gia.get(ma)

    async def ton_kho(self, ma: str):
        self._dem("ton_kho")
        return self.bang_ton.get(ma)

    async def suc_khoe(self) -> bool:
        try:
            self._dem("suc_khoe")
        except LoiERP:
            return False
        return True
```

Tạo `tests/test_nguon_tep.py`:

```python
"""Adapter đọc `catalog.json` — nguồn mặc định, giữ clone sạch chạy được."""
import json

import pytest

from agent.erp.hop_dong import LoiERP, NguonERP
from agent.erp.tep import NguonTep
from tests.erp_gia import chay


@pytest.fixture
def catalog(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {
                "san_pham": [
                    {"ma": "AS-CL01", "ten": "Sữa rửa mặt", "loai": "Làm sạch",
                     "gia": 245000, "dung_tich": "150ml", "ton_kho": 84},
                    {"ma": "AS-SR9", "ten": "Hàng ngừng bán", "loai": "Serum",
                     "gia": 500000, "ton_kho": 3, "ngung_ban": True},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def test_la_nguon_erp_hop_le(catalog):
    assert isinstance(NguonTep(catalog), NguonERP)


def test_doc_duoc_san_pham(catalog):
    ds = chay(NguonTep(catalog).danh_sach_san_pham())
    assert [sp.ma for sp in ds] == ["AS-CL01"]
    assert ds[0].ten == "Sữa rửa mặt"
    assert ds[0].dung_tich == "150ml"


def test_mac_dinh_loai_hang_khong_duoc_ban(catalog):
    # ERP chứa cả hàng ngừng kinh doanh, hàng mẫu, vật tư nội bộ. Không lọc
    # thì agent nhiệt tình tư vấn lọ sample không bán.
    ds = chay(NguonTep(catalog).danh_sach_san_pham())
    assert "AS-SR9" not in [sp.ma for sp in ds]


def test_xin_ca_hang_khong_ban_thi_van_tra(catalog):
    ds = chay(NguonTep(catalog).danh_sach_san_pham(chi_ban_duoc=False))
    assert {sp.ma for sp in ds} == {"AS-CL01", "AS-SR9"}
    assert [sp.ban_duoc_phep for sp in ds if sp.ma == "AS-SR9"] == [False]


def test_gia_va_ton_kho(catalog):
    n = NguonTep(catalog)
    g = chay(n.gia("AS-CL01"))
    assert g.gia_ban == 245000
    assert g.nguon == "catalog.json"
    t = chay(n.ton_kho("AS-CL01"))
    assert t.ban_duoc == 84


def test_ma_khong_co_thi_tra_none(catalog):
    n = NguonTep(catalog)
    assert chay(n.gia("KHONG-CO")) is None
    assert chay(n.ton_kho("KHONG-CO")) is None


def test_file_that_khong_co_thi_roi_ve_ban_mau(tmp_path):
    # Đường lui bắt buộc: `catalog.json` nằm trong .gitignore nên không đi
    # theo repo. Thiếu đường lui này là máy vừa clone về chạy ra rỗng, agent
    # không nói được giá nào, và người cài tưởng hệ thống hỏng.
    ds = chay(NguonTep(tmp_path / "khong-ton-tai.json").danh_sach_san_pham())
    assert len(ds) > 0


def test_file_hong_thi_nem_loi_erp_khong_tra_rong(tmp_path):
    # Trả rỗng là hỏng IM LẶNG: agent tưởng cửa hàng không có sản phẩm nào
    # và chuyển hết cho người, không ai biết vì sao.
    xau = tmp_path / "catalog.json"
    xau.write_text("{ dữ liệu hỏng", encoding="utf-8")
    with pytest.raises(LoiERP):
        chay(NguonTep(xau).danh_sach_san_pham())


def test_suc_khoe(catalog, tmp_path):
    assert chay(NguonTep(catalog).suc_khoe()) is True
    xau = tmp_path / "hong.json"
    xau.write_text("{ hỏng", encoding="utf-8")
    assert chay(NguonTep(xau).suc_khoe()) is False
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_nguon_tep.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'agent.erp.tep'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Tạo `agent/erp/tep.py`:

```python
"""
Adapter đọc `data/catalog.json` — nguồn MẶC ĐỊNH.

VÌ SAO NÓ TỒN TẠI KHI ĐÃ CÓ ADAPTER ERP THẬT
--------------------------------------------
`catalog.json` nằm trong .gitignore nên không đi theo repo. Không có adapter
này làm mặc định thì máy vừa clone về phải dựng xong Odoo mới chạy được một
dòng — và CI job `clone-sach` chết.

Nó cũng là bản đối chiếu: test hợp đồng chạy chung cho cả bốn adapter, và
adapter này là cái rẻ nhất để chạy chúng.

VÌ SAO FILE HỎNG THÌ NÉM CHỨ KHÔNG TRẢ RỖNG
-------------------------------------------
Trả rỗng nghĩa là "cửa hàng không có sản phẩm nào". Agent tin, chuyển hết
cho người, và không có dòng log nào nói vì sao. Đó đúng là khuôn hỏng im
lặng đã cắn repo này bốn lần.
"""
from __future__ import annotations

import json
import pathlib

from agent.config import ROOT
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho

CATALOG = ROOT / "data" / "catalog.json"
CATALOG_MAU = ROOT / "data" / "catalog.example.json"


class NguonTep:
    ten = "tep"

    def __init__(self, duong_dan: pathlib.Path | None = None):
        self._duong_dan = duong_dan

    def _duong(self) -> pathlib.Path:
        dd = self._duong_dan
        if dd is not None and dd.exists():
            return dd
        return CATALOG if CATALOG.exists() else CATALOG_MAU

    def _doc(self) -> dict:
        dd = self._duong()
        try:
            return json.loads(dd.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise LoiERP(f"Không đọc được danh mục {dd.name}: {exc}") from exc

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]:
        ds = [
            SanPhamERP(
                ma=str(sp.get("ma", "")),
                ten=str(sp.get("ten", "")),
                loai=str(sp.get("loai") or ""),
                dung_tich=str(sp.get("dung_tich") or ""),
                ban_duoc_phep=not sp.get("ngung_ban", False),
            )
            for sp in self._doc().get("san_pham", [])
        ]
        return [sp for sp in ds if sp.ban_duoc_phep] if chi_ban_duoc else ds

    async def gia(self, ma: str) -> Gia | None:
        for sp in self._doc().get("san_pham", []):
            if sp.get("ma") == ma and sp.get("gia") is not None:
                return Gia(gia_ban=int(sp["gia"]), nguon="catalog.json")
        return None

    async def ton_kho(self, ma: str) -> TonKho | None:
        for sp in self._doc().get("san_pham", []):
            if sp.get("ma") == ma and sp.get("ton_kho") is not None:
                return TonKho(ban_duoc=int(sp["ton_kho"]))
        return None

    async def suc_khoe(self) -> bool:
        try:
            self._doc()
        except LoiERP:
            return False
        return True
```

**Chú ý:** `_duong()` cố ý bỏ qua `duong_dan` khi file đó **không tồn tại** — đó là điều kiện để `test_file_that_khong_co_thi_roi_ve_ban_mau` xanh. Nhưng file **tồn tại mà hỏng** thì vẫn ném, vì `test_file_hong_thi_nem_loi_erp_khong_tra_rong` canh đúng chỗ đó.

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_nguon_tep.py -q`
Kỳ vọng: PASS, 9 test

Chạy: `ruff check agent/erp tests/`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/tep.py tests/erp_gia.py tests/test_nguon_tep.py
git commit -m "Adapter tệp — mặc định, và file hỏng thì nổ chứ không trả rỗng"
```

---

### Task 3: Cổng — cache theo tuổi, và "không biết thì nói không biết"

**Files:**
- Create: `agent/erp/cong.py`
- Test: `tests/test_cong_erp_cache.py`

**Interfaces:**
- Consumes: `agent.erp.hop_dong.{Gia, TonKho, NguonERP}`, `tests.erp_gia.{chay, NguonGia}`
- Produces:
  - `agent.erp.cong.Cong(nguon, ttl_gia=900.0, ttl_ton=60.0, ngat_mach_so_lan=5, ngat_mach_giay=30.0, dong_ho=time.monotonic)`
  - `async Cong.gia(ma: str, bo_qua_cache: bool = False) -> Gia | None`
  - `async Cong.ton_kho(ma: str, bo_qua_cache: bool = False) -> TonKho | None`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_cong_erp_cache.py`:

```python
"""Cache theo tuổi, và quy tắc trung tâm: KHÔNG BAO GIỜ trả số cũ.

Đồng hồ tiêm vào thay cho `asyncio.sleep` — bộ test phải chạy dưới 4 giây.
"""
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, TonKho
from tests.erp_gia import NguonGia, chay


class DongHo:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tien(self, giay: float) -> None:
        self.t += giay


def _nguon():
    return NguonGia(
        gia={"AS-CL01": Gia(gia_ban=245000, nguon="thử")},
        ton={"AS-CL01": TonKho(ban_duoc=84)},
    )


def test_trong_han_thi_khong_goi_erp_lan_hai():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84
    dh.tien(59)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84
    assert n.so_lan_goi["ton_kho"] == 1


def test_qua_han_thi_goi_lai():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    dh.tien(61)
    chay(c.ton_kho("AS-CL01"))
    assert n.so_lan_goi["ton_kho"] == 2


def test_qua_han_ma_erp_hong_thi_tra_none_khong_tra_so_cu():
    # ĐÂY LÀ RÀNG BUỘC TRUNG TÂM CỦA CẢ CỔNG.
    # Trả số cũ là báo giá sai / báo còn hàng cho món đã hết, một cách tự
    # tin, và không ai biết. Thà im một phút.
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    assert chay(c.ton_kho("AS-CL01")).ban_duoc == 84

    dh.tien(61)
    n.hong = True
    assert chay(c.ton_kho("AS-CL01")) is None


def test_gia_cung_khong_bao_gio_tra_so_cu():
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_gia=900.0, dong_ho=dh)
    assert chay(c.gia("AS-CL01")).gia_ban == 245000

    dh.tien(901)
    n.hong = True
    assert chay(c.gia("AS-CL01")) is None


def test_bo_qua_cache_thi_luon_goi_erp():
    # Chốt đơn phải đọc tồn SỐNG. Đọc cache 60 giây ở đúng khoảnh khắc chốt
    # là để khách xác nhận xong mới báo hết hàng.
    n, dh = _nguon(), DongHo()
    c = Cong(n, ttl_ton=60.0, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    chay(c.ton_kho("AS-CL01", bo_qua_cache=True))
    assert n.so_lan_goi["ton_kho"] == 2


def test_bo_qua_cache_ma_erp_hong_thi_tra_none():
    n, dh = _nguon(), DongHo()
    c = Cong(n, dong_ho=dh)
    chay(c.ton_kho("AS-CL01"))
    n.hong = True
    assert chay(c.ton_kho("AS-CL01", bo_qua_cache=True)) is None


def test_ma_khong_ton_tai_tra_none_khong_nem():
    c = Cong(_nguon(), dong_ho=DongHo())
    assert chay(c.gia("KHONG-CO")) is None
    assert chay(c.ton_kho("KHONG-CO")) is None


def test_cache_tach_theo_ma():
    n = NguonGia(ton={"A": TonKho(ban_duoc=1), "B": TonKho(ban_duoc=2)})
    c = Cong(n, dong_ho=DongHo())
    assert chay(c.ton_kho("A")).ban_duoc == 1
    assert chay(c.ton_kho("B")).ban_duoc == 2
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_cache.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'agent.erp.cong'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Tạo `agent/erp/cong.py`:

```python
"""
Cổng: bọc một `NguonERP`, thêm cache có tuổi và ngắt mạch.

QUY TẮC TRUNG TÂM
-----------------
Giá và tồn kho quá hạn mà gọi ERP không được thì cổng trả `None`.
KHÔNG BAO GIỜ trả số cũ.

Cám dỗ ở đây rất lớn: đã có số trong tay, trả ra thì agent chạy mượt, không
ai thấy gì. Đó chính là vấn đề — nó chạy mượt trong khi nói sai. Báo giá sai
rồi mới phát hiện đắt hơn nhiều so với im lặng một phút, và im lặng thì lưới
an toàn đẩy sang người thật.

Tham chiếu (tên, mô tả) thì ngược lại — bản cũ dùng được, vì tên sản phẩm
không đổi trong một buổi chiều.

VÌ SAO ĐỒNG HỒ TIÊM VÀO
-----------------------
Để test TTL không phải ngủ. Toàn bộ bộ test phải chạy dưới 4 giây.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.erp.hop_dong import Gia, NguonERP, TonKho


@dataclass
class _O:
    """Một ô cache: giá trị và thời điểm ghi."""

    gia_tri: Any
    luc: float


class Cong:
    def __init__(
        self,
        nguon: NguonERP,
        ttl_gia: float = 900.0,
        ttl_ton: float = 60.0,
        ngat_mach_so_lan: int = 5,
        ngat_mach_giay: float = 30.0,
        dong_ho: Callable[[], float] = time.monotonic,
    ):
        self._nguon = nguon
        self._ttl_gia = ttl_gia
        self._ttl_ton = ttl_ton
        self._ngat_mach_so_lan = ngat_mach_so_lan
        self._ngat_mach_giay = ngat_mach_giay
        self._dong_ho = dong_ho
        self._cache_gia: dict[str, _O] = {}
        self._cache_ton: dict[str, _O] = {}
        self._hong_lien_tiep = 0
        self._mo_mach_den = 0.0

    async def gia(self, ma: str, bo_qua_cache: bool = False) -> Gia | None:
        return await self._lay(
            self._cache_gia, self._ttl_gia, ma, bo_qua_cache, self._nguon.gia
        )

    async def ton_kho(self, ma: str, bo_qua_cache: bool = False) -> TonKho | None:
        return await self._lay(
            self._cache_ton, self._ttl_ton, ma, bo_qua_cache, self._nguon.ton_kho
        )

    async def _lay(self, cache, ttl, ma, bo_qua_cache, ham):
        bay_gio = self._dong_ho()
        if not bo_qua_cache:
            o = cache.get(ma)
            if o is not None and bay_gio - o.luc < ttl:
                return o.gia_tri
        try:
            gia_tri = await ham(ma)
        except Exception:  # noqa: BLE001
            # Không trả ô cache cũ ở đây. Xem QUY TẮC TRUNG TÂM ở đầu file.
            return None
        cache[ma] = _O(gia_tri, bay_gio)
        return gia_tri
```

Hai trường `_hong_lien_tiep` và `_mo_mach_den` khai báo sẵn ở đây tuy chưa dùng, để Task 4 chỉ phải sửa đúng một hàm.

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_cache.py -q`
Kỳ vọng: PASS, 8 test

Chạy: `ruff check agent/erp tests/`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/cong.py tests/test_cong_erp_cache.py
git commit -m "Cổng ERP: cache theo tuổi, quá hạn mà hỏng thì trả None chứ không trả số cũ"
```

---

### Task 4: Ngắt mạch

**Files:**
- Modify: `agent/erp/cong.py` (thay thân `_lay`, thêm `_bao_ngat_mach` và `trang_thai`)
- Test: `tests/test_cong_erp_ngat_mach.py`

**Interfaces:**
- Consumes: `agent.erp.cong.Cong` từ Task 3
- Produces: `Cong.trang_thai() -> dict` với các khoá `nguon: str`, `mach_mo: bool`, `hong_lien_tiep: int`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_cong_erp_ngat_mach.py`:

```python
"""Ngắt mạch: ERP chậm không được kéo cả contact center chậm theo.

Ở contact center, mỗi lời gọi treo là hàng chục khách chờ cùng lúc.
"""
from agent.erp.cong import Cong
from agent.erp.hop_dong import TonKho
from tests.erp_gia import NguonGia, chay


class DongHo:
    def __init__(self):
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def tien(self, giay: float) -> None:
        self.t += giay


def _bo(dh):
    """Nguồn luôn hỏng, TTL = 0 nên lần nào cũng phải gọi ERP thật."""
    n = NguonGia(ton={"A": TonKho(ban_duoc=5)}, hong=True)
    return n, Cong(
        n, ttl_ton=0.0, ngat_mach_so_lan=3, ngat_mach_giay=30.0, dong_ho=dh
    )


def test_mach_dong_luc_dau():
    _, c = _bo(DongHo())
    assert c.trang_thai()["mach_mo"] is False


def test_du_so_lan_hong_thi_mo_mach():
    _, c = _bo(DongHo())
    for _ in range(3):
        assert chay(c.ton_kho("A")) is None
    assert c.trang_thai()["mach_mo"] is True
    assert c.trang_thai()["hong_lien_tiep"] == 3


def test_mach_mo_thi_khong_goi_erp_nua():
    n, c = _bo(DongHo())
    for _ in range(3):
        chay(c.ton_kho("A"))
    truoc = n.so_lan_goi["ton_kho"]
    for _ in range(10):
        assert chay(c.ton_kho("A")) is None
    assert n.so_lan_goi["ton_kho"] == truoc


def test_het_thoi_gian_mo_mach_thi_thu_lai():
    dh = DongHo()
    n, c = _bo(dh)
    for _ in range(3):
        chay(c.ton_kho("A"))
    truoc = n.so_lan_goi["ton_kho"]
    dh.tien(31)
    chay(c.ton_kho("A"))
    assert n.so_lan_goi["ton_kho"] == truoc + 1


def test_goi_thanh_cong_thi_dat_lai_bo_dem():
    n, c = _bo(DongHo())
    chay(c.ton_kho("A"))
    chay(c.ton_kho("A"))
    assert c.trang_thai()["hong_lien_tiep"] == 2
    n.hong = False
    assert chay(c.ton_kho("A")).ban_duoc == 5
    assert c.trang_thai()["hong_lien_tiep"] == 0
    assert c.trang_thai()["mach_mo"] is False


def test_trang_thai_noi_ro_nguon_nao():
    _, c = _bo(DongHo())
    assert c.trang_thai()["nguon"] == "gia"
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_ngat_mach.py -q`
Kỳ vọng: FAIL — `AttributeError: 'Cong' object has no attribute 'trang_thai'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Trong `agent/erp/cong.py`, thay toàn bộ phương thức `_lay` bằng đoạn dưới, rồi thêm hai phương thức mới ngay sau nó:

```python
    async def _lay(self, cache, ttl, ma, bo_qua_cache, ham):
        bay_gio = self._dong_ho()
        if not bo_qua_cache:
            o = cache.get(ma)
            if o is not None and bay_gio - o.luc < ttl:
                return o.gia_tri

        # Mạch đang mở: không gọi, trả `None` ngay. Gọi tiếp là bắt mỗi khách
        # đang chờ phải ăn trọn thời gian timeout của ERP.
        if bay_gio < self._mo_mach_den:
            return None

        try:
            gia_tri = await ham(ma)
        except Exception:  # noqa: BLE001
            self._hong_lien_tiep += 1
            if self._hong_lien_tiep >= self._ngat_mach_so_lan:
                self._mo_mach_den = bay_gio + self._ngat_mach_giay
                await self._bao_ngat_mach()
            # Không trả ô cache cũ. Xem QUY TẮC TRUNG TÂM ở đầu file.
            return None

        self._hong_lien_tiep = 0
        self._mo_mach_den = 0.0
        cache[ma] = _O(gia_tri, bay_gio)
        return gia_tri

    async def _bao_ngat_mach(self) -> None:
        """Ngắt mạch phải để lại dấu vết.

        Không có nhật ký thì ERP hỏng cả buổi mà biểu hiện duy nhất ra ngoài
        là 'hôm nay agent chuyển người nhiều hơn mọi khi'.
        """
        try:
            from agent import db

            await db.log_event(
                "erp.ngat_mach",
                nguon=getattr(self._nguon, "ten", "?"),
                hong_lien_tiep=self._hong_lien_tiep,
            )
        except Exception:  # noqa: BLE001
            pass

    def trang_thai(self) -> dict:
        return {
            "nguon": getattr(self._nguon, "ten", "?"),
            "mach_mo": self._dong_ho() < self._mo_mach_den,
            "hong_lien_tiep": self._hong_lien_tiep,
        }
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_ngat_mach.py tests/test_cong_erp_cache.py -q`
Kỳ vọng: PASS, 14 test

Chạy: `ruff check agent/erp tests/`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/cong.py tests/test_cong_erp_ngat_mach.py
git commit -m "Ngắt mạch: ERP chậm không kéo cả contact center chậm theo"
```

---

### Task 5: Ánh xạ mã sản phẩm và phép kiểm khởi động

**Files:**
- Create: `agent/erp/anh_xa.py`
- Test: `tests/test_anh_xa_ma_erp.py`

**Interfaces:**
- Consumes: `agent.config.ROOT`
- Produces:
  - `agent.erp.anh_xa.AnhXa(bang: dict[str, str] | None = None)` với `sang_erp(ma: str) -> str`, `ve_noi_bo(ma_erp: str) -> str`
  - `agent.erp.anh_xa.doc_anh_xa(duong_dan: pathlib.Path | None = None) -> AnhXa`
  - `async agent.erp.anh_xa.kiem(ma_noi_bo: list[str], ma_erp: list[str], anh_xa: AnhXa) -> dict` trả `{"tong": int, "khop": int, "ty_le": float, "thieu": list[str]}`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_anh_xa_ma_erp.py`:

```python
"""Ánh xạ mã nội bộ <-> mã ERP.

Giả định "mã nội bộ trùng item_code bên ERP" là giả định không ai kiểm, và
khi nó sai thì việc hợp nhất hai nửa dữ liệu IM LẶNG TRẢ RỖNG: agent thấy
sản phẩm nhưng không có thông tin tư vấn nào, không lỗi nào được ném.
"""
import json

import pytest

from agent.erp.anh_xa import AnhXa, doc_anh_xa, kiem
from tests.erp_gia import chay


def test_khong_co_bang_thi_coi_la_dong_nhat():
    a = AnhXa()
    assert a.sang_erp("AS-CL01") == "AS-CL01"
    assert a.ve_noi_bo("AS-CL01") == "AS-CL01"


def test_co_bang_thi_dich_hai_chieu():
    a = AnhXa({"AS-CL01": "ITEM-0001"})
    assert a.sang_erp("AS-CL01") == "ITEM-0001"
    assert a.ve_noi_bo("ITEM-0001") == "AS-CL01"


def test_ma_ngoai_bang_thi_giu_nguyen():
    a = AnhXa({"AS-CL01": "ITEM-0001"})
    assert a.sang_erp("AS-XX99") == "AS-XX99"


def test_doc_file_khong_co_thi_tra_anh_xa_dong_nhat(tmp_path):
    a = doc_anh_xa(tmp_path / "khong-co.json")
    assert a.sang_erp("AS-CL01") == "AS-CL01"


def test_doc_file_co_that(tmp_path):
    p = tmp_path / "anh_xa_ma.json"
    p.write_text(json.dumps({"AS-CL01": "ITEM-1"}), encoding="utf-8")
    assert doc_anh_xa(p).sang_erp("AS-CL01") == "ITEM-1"


def test_kiem_bao_ty_le_khop():
    kq = chay(kiem(
        ma_noi_bo=["A", "B", "C", "D"],
        ma_erp=["A", "B", "C", "Z"],
        anh_xa=AnhXa(),
    ))
    assert kq["tong"] == 4
    assert kq["khop"] == 3
    assert kq["ty_le"] == pytest.approx(0.75)
    assert kq["thieu"] == ["D"]


def test_kiem_dung_anh_xa_chu_khong_so_sanh_tho():
    kq = chay(kiem(
        ma_noi_bo=["AS-CL01"],
        ma_erp=["ITEM-1"],
        anh_xa=AnhXa({"AS-CL01": "ITEM-1"}),
    ))
    assert kq["ty_le"] == pytest.approx(1.0)


def test_kiem_danh_muc_rong_khong_chia_cho_khong():
    kq = chay(kiem(ma_noi_bo=[], ma_erp=[], anh_xa=AnhXa()))
    assert kq["tong"] == 0
    assert kq["ty_le"] == 0.0
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_anh_xa_ma_erp.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'agent.erp.anh_xa'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Tạo `agent/erp/anh_xa.py`:

```python
"""
Ánh xạ mã sản phẩm nội bộ <-> mã bên ERP.

VÌ SAO KHÔNG GIẢ ĐỊNH CHÚNG TRÙNG NHAU
--------------------------------------
Danh mục nội bộ dùng `AS-CL01`; ERP có thể dùng `ITEM-0001`, hoặc mã vạch,
hoặc mã do kế toán đặt từ đời trước. Giả định chúng trùng là giả định không
ai kiểm — và khi sai thì việc hợp nhất hai nửa dữ liệu lặng lẽ trả rỗng:
agent thấy sản phẩm mà không có thông tin tư vấn nào, không lỗi, không log.

Nên có `kiem()`: chạy lúc khởi động, đếm tỷ lệ khớp, và kêu khi thấp.
"""
from __future__ import annotations

import json
import pathlib

from agent.config import ROOT

ANH_XA_PATH = ROOT / "data" / "anh_xa_ma.json"

# Dưới ngưỡng này thì gần như chắc chắn là cấu hình sai chứ không phải vài
# SKU mới chưa nhập. Kêu to còn hơn để im.
NGUONG_BAO_DONG = 0.9


class AnhXa:
    def __init__(self, bang: dict[str, str] | None = None):
        self._sang = dict(bang or {})
        self._ve = {v: k for k, v in self._sang.items()}

    def sang_erp(self, ma: str) -> str:
        return self._sang.get(ma, ma)

    def ve_noi_bo(self, ma_erp: str) -> str:
        return self._ve.get(ma_erp, ma_erp)


def doc_anh_xa(duong_dan: pathlib.Path | None = None) -> AnhXa:
    dd = duong_dan if duong_dan is not None else ANH_XA_PATH
    if not dd.exists():
        return AnhXa()
    try:
        return AnhXa(json.loads(dd.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        # Ánh xạ hỏng thì coi như đồng nhất, nhưng `kiem()` sẽ thấy tỷ lệ
        # khớp tụt và kêu — không cần nổ ở đây.
        return AnhXa()


async def kiem(ma_noi_bo: list[str], ma_erp: list[str], anh_xa: AnhXa) -> dict:
    """Đếm bao nhiêu mã nội bộ tìm được đối ứng bên ERP."""
    tap_erp = set(ma_erp)
    thieu = [m for m in ma_noi_bo if anh_xa.sang_erp(m) not in tap_erp]
    tong = len(ma_noi_bo)
    khop = tong - len(thieu)
    ty_le = (khop / tong) if tong else 0.0

    if tong and ty_le < NGUONG_BAO_DONG:
        try:
            from agent import db

            await db.log_event(
                "erp.anh_xa_lech",
                tong=tong,
                khop=khop,
                ty_le=round(ty_le, 3),
                thieu=thieu[:20],
            )
        except Exception:  # noqa: BLE001
            pass

    return {"tong": tong, "khop": khop, "ty_le": ty_le, "thieu": thieu}
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_anh_xa_ma_erp.py -q`
Kỳ vọng: PASS, 8 test

Chạy: `ruff check agent/erp tests/`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/anh_xa.py tests/test_anh_xa_ma_erp.py
git commit -m "Ánh xạ mã sản phẩm — và phép kiểm để nó lệch thì có người biết"
```

---

### Task 6: Hợp nhất hai nửa dữ liệu

**Files:**
- Modify: `agent/erp/cong.py` (thêm hai tham số `__init__`, thêm `_ho_so_tu_van` và `danh_muc`)
- Test: `tests/test_hop_nhat_hai_nua.py`

**Interfaces:**
- Consumes: `Cong` (Task 3, 4), `AnhXa` + `doc_anh_xa` (Task 5), `CATALOG` + `CATALOG_MAU` (Task 2)
- Produces:
  - `Cong.__init__` nhận thêm `duong_dan_tu_van: pathlib.Path | None = None`, `anh_xa: AnhXa | None = None`
  - `async Cong.danh_muc() -> dict` — hình dạng `{"san_pham": [...], "don_hang": [...]}`, mỗi sản phẩm có thêm khoá `duoc_gioi_thieu: bool`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_hop_nhat_hai_nua.py`:

```python
"""Hợp nhất nửa thương mại (ERP) với nửa tư vấn (kho nội bộ).

ERP biết bán cái gì giá bao nhiêu. Nó KHÔNG biết serum này hợp da dầu hay
da khô. Chín trên mười bốn trường của bản ghi sản phẩm không tồn tại trong
Odoo hay ERPNext — và chín trường đó chính là toàn bộ chất tư vấn.
"""
import json

import pytest

from agent.erp.anh_xa import AnhXa
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, LoiERP, SanPhamERP, TonKho
from tests.erp_gia import NguonGia, chay


@pytest.fixture
def nua_tu_van(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {
                "san_pham": [
                    {
                        "ma": "AS-CL01",
                        "ten": "Tên cũ trong file",
                        "gia": 999,
                        "ton_kho": 999,
                        "da_phu_hop": ["da dầu"],
                        "thanh_phan_chinh": ["Cica"],
                        "so_cong_bo": "12345/22/CBMP-HN",
                    }
                ],
                "don_hang": [{"ma": "AS001"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return p


def _nguon():
    return NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Tên thật từ ERP", loai="Làm sạch")],
        gia={"AS-CL01": Gia(gia_ban=245000)},
        ton={"AS-CL01": TonKho(ban_duoc=7)},
    )


def test_giu_dung_hinh_dang_ma_tools_dang_cho(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    assert set(d) >= {"san_pham", "don_hang"}
    assert isinstance(d["san_pham"], list)


def test_erp_thang_o_nua_thuong_mai(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    sp = d["san_pham"][0]
    assert sp["ten"] == "Tên thật từ ERP"
    assert sp["gia"] == 245000
    assert sp["ton_kho"] == 7


def test_kho_noi_bo_thang_o_nua_tu_van(nua_tu_van):
    d = chay(Cong(_nguon(), duong_dan_tu_van=nua_tu_van).danh_muc())
    sp = d["san_pham"][0]
    assert sp["da_phu_hop"] == ["da dầu"]
    assert sp["thanh_phan_chinh"] == ["Cica"]
    assert sp["so_cong_bo"] == "12345/22/CBMP-HN"


def test_thieu_ho_so_tu_van_thi_khong_duoc_gioi_thieu(nua_tu_van):
    # ERP thêm 50 SKU mới, không ai viết hồ sơ tư vấn cho chúng. Không có cờ
    # này thì agent tư vấn chúng bằng tưởng tượng và không ai biết.
    n = _nguon()
    n.san_pham.append(SanPhamERP(ma="AS-MOI", ten="SKU mới toanh"))
    n.bang_gia["AS-MOI"] = Gia(gia_ban=100000)
    n.bang_ton["AS-MOI"] = TonKho(ban_duoc=3)

    d = chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())
    moi = [sp for sp in d["san_pham"] if sp["ma"] == "AS-MOI"][0]
    cu = [sp for sp in d["san_pham"] if sp["ma"] == "AS-CL01"][0]
    assert moi["duoc_gioi_thieu"] is False
    assert cu["duoc_gioi_thieu"] is True


def test_erp_hong_hoan_toan_thi_nem_chu_khong_tra_rong(nua_tu_van):
    n = _nguon()
    n.hong = True
    with pytest.raises(LoiERP):
        chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())


def test_dung_anh_xa_ma(tmp_path):
    p = tmp_path / "catalog.json"
    p.write_text(
        json.dumps(
            {"san_pham": [{"ma": "AS-CL01", "da_phu_hop": ["da khô"]}]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    n = NguonGia(
        san_pham=[SanPhamERP(ma="ITEM-1", ten="Từ ERP")],
        gia={"ITEM-1": Gia(gia_ban=1000)},
        ton={"ITEM-1": TonKho(ban_duoc=1)},
    )
    c = Cong(n, duong_dan_tu_van=p, anh_xa=AnhXa({"AS-CL01": "ITEM-1"}))
    sp = chay(c.danh_muc())["san_pham"][0]
    assert sp["ma"] == "AS-CL01"
    assert sp["da_phu_hop"] == ["da khô"]
    assert sp["duoc_gioi_thieu"] is True


def test_gia_khong_tra_duoc_thi_bo_qua_san_pham_do(nua_tu_van):
    # Sản phẩm không có giá thì agent không được nói về nó — nói mà không
    # kèm giá là mời khách hỏi giá rồi trả lời bằng số bịa.
    n = _nguon()
    n.bang_gia.clear()
    d = chay(Cong(n, duong_dan_tu_van=nua_tu_van).danh_muc())
    assert d["san_pham"] == []
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_hop_nhat_hai_nua.py -q`
Kỳ vọng: FAIL — `TypeError: Cong.__init__() got an unexpected keyword argument 'duong_dan_tu_van'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Trong `agent/erp/cong.py`, đổi khối import đầu file thành:

```python
from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agent.erp.anh_xa import AnhXa, doc_anh_xa
from agent.erp.hop_dong import Gia, LoiERP, NguonERP, TonKho
```

Thêm hai tham số vào chữ ký `__init__`, ngay sau `ngat_mach_giay: float = 30.0,`:

```python
        duong_dan_tu_van: pathlib.Path | None = None,
        anh_xa: AnhXa | None = None,
```

và hai dòng vào cuối thân `__init__`:

```python
        self._duong_dan_tu_van = duong_dan_tu_van
        self._anh_xa = anh_xa if anh_xa is not None else doc_anh_xa()
```

Thêm hai phương thức vào cuối lớp `Cong`:

```python
    def _ho_so_tu_van(self) -> tuple[dict[str, dict], list]:
        """Nửa tư vấn: đọc từ kho nội bộ, KHÔNG từ ERP.

        Chín trên mười bốn trường của bản ghi sản phẩm (da_phu_hop,
        thanh_phan_chinh, so_cong_bo...) không tồn tại trong Odoo hay ERPNext.
        Nhét chúng vào ERP là dùng sai công cụ, và mất sạch khi đổi ERP.
        """
        from agent.erp.tep import CATALOG, CATALOG_MAU

        dd = self._duong_dan_tu_van
        if dd is None or not dd.exists():
            dd = CATALOG if CATALOG.exists() else CATALOG_MAU
        if not dd.exists():
            return {}, []
        try:
            data = json.loads(dd.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}, []
        return (
            {sp["ma"]: sp for sp in data.get("san_pham", []) if sp.get("ma")},
            data.get("don_hang", []),
        )

    async def danh_muc(self) -> dict:
        """Danh mục hợp nhất, đúng hình dạng `tools._catalog()` đang trả."""
        try:
            ds = await self._nguon.danh_sach_san_pham()
        except Exception as exc:  # noqa: BLE001
            # Ném chứ không trả rỗng: rỗng nghĩa là "cửa hàng không có hàng
            # nào", agent tin, chuyển hết cho người, và không ai biết vì sao.
            raise LoiERP(
                f"Không lấy được danh mục từ nguồn {getattr(self._nguon, 'ten', '?')}"
            ) from exc

        ho_so, don_hang = self._ho_so_tu_van()
        thieu: list[str] = []
        ket_qua: list[dict] = []

        for sp in ds:
            ma_noi_bo = self._anh_xa.ve_noi_bo(sp.ma)
            g = await self.gia(sp.ma)
            t = await self.ton_kho(sp.ma)
            if g is None or t is None:
                # Không có giá hoặc không biết tồn thì đừng đưa ra. Đưa ra là
                # mời khách hỏi rồi trả lời bằng số bịa.
                continue
            ban_ghi = dict(ho_so.get(ma_noi_bo, {}))
            if ma_noi_bo not in ho_so:
                thieu.append(ma_noi_bo)
            ban_ghi.update(
                ma=ma_noi_bo,
                ten=sp.ten,
                loai=sp.loai or ban_ghi.get("loai", ""),
                dung_tich=sp.dung_tich or ban_ghi.get("dung_tich", ""),
                gia=g.gia_ban,
                ton_kho=t.ban_duoc,
                duoc_gioi_thieu=ma_noi_bo in ho_so,
            )
            ket_qua.append(ban_ghi)

        if thieu:
            try:
                from agent import db

                await db.log_event(
                    "erp.thieu_ho_so", so_luong=len(thieu), ma=thieu[:20]
                )
            except Exception:  # noqa: BLE001
                pass

        return {"san_pham": ket_qua, "don_hang": don_hang}
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_hop_nhat_hai_nua.py -q`
Kỳ vọng: PASS, 7 test

Chạy: `./.venv/Scripts/python.exe -m pytest -q`
Kỳ vọng: PASS toàn bộ, dưới 4 giây

Chạy: `ruff check .`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/erp/cong.py tests/test_hop_nhat_hai_nua.py
git commit -m "Hợp nhất hai nửa: ERP giữ giá và tồn, kho nội bộ giữ chất tư vấn"
```

---

### Task 7: Cấu hình, nhà máy dựng cổng, và nối vào `_catalog_song()`

**Files:**
- Modify: `agent/config.py` (chèn khối `--- Kho / ERP ---` ngay trước `nguong_tu_chot_vnd`)
- Create: `agent/erp/nha_may.py`
- Modify: `agent/core/tools.py` (thân `_catalog_song`, khoảng dòng 302-325)
- Modify: `.env.example`
- Test: `tests/test_cong_erp_noi_vao_tools.py`

**Interfaces:**
- Consumes: `Cong` (Task 3, 4, 6), `NguonTep` (Task 2)
- Produces:
  - `agent.erp.nha_may.tao_nguon() -> NguonERP`
  - `agent.erp.nha_may.cong() -> Cong` (nhớ kết quả, dựng một lần)
  - `agent.erp.nha_may.dat_lai() -> None` (chỉ cho test)
  - Trường `Settings`: `erp_loai: str = "tep"`, `erp_ttl_gia: float = 900.0`, `erp_ttl_ton: float = 60.0`, `erp_ngat_mach_so_lan: int = 5`, `erp_ngat_mach_giay: float = 30.0`, `erp_ma_kho: str = ""`, `erp_pricelist: str = ""`

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_cong_erp_noi_vao_tools.py`:

```python
"""Nối cổng vào `tools._catalog_song()` mà không đổi chữ ký của `_catalog()`.

Giữ chữ ký `-> dict` là điều kiện để 440 test hiện có vẫn là lưới an toàn
thật, chứ không phải lưới đã bị tháo trong lúc thay nguồn dữ liệu.
"""
import inspect

import pytest

from agent.config import settings
from agent.core import tools
from agent.erp import nha_may
from agent.erp.hop_dong import NguonERP
from agent.erp.tep import NguonTep
from tests.erp_gia import chay


@pytest.fixture(autouse=True)
def _sach():
    nha_may.dat_lai()
    yield
    nha_may.dat_lai()


def test_mac_dinh_la_nguon_tep():
    # Máy vừa clone về, không .env, không ERP: vẫn phải chạy được.
    assert settings.erp_loai == "tep"
    assert isinstance(nha_may.tao_nguon(), NguonTep)


def test_nguon_nao_cung_phai_hop_le_voi_protocol():
    assert isinstance(nha_may.tao_nguon(), NguonERP)


def test_erp_loai_la_rac_thi_no_chu_khong_im_lang(monkeypatch):
    # Gõ sai `ERP_LOAI=odooo` rồi lặng lẽ rơi về tệp là chạy suốt tháng với
    # giá trong file mà tưởng đang nối ERP.
    monkeypatch.setattr(settings, "erp_loai", "odooo")
    with pytest.raises(ValueError, match="odooo"):
        nha_may.tao_nguon()


def test_cong_dung_lai_mot_lan():
    assert nha_may.cong() is nha_may.cong()


def test_chu_ky_catalog_khong_doi():
    assert inspect.signature(tools._catalog).return_annotation is dict


def test_catalog_van_tra_ve_san_pham():
    d = tools._catalog()
    assert isinstance(d, dict)
    assert len(d.get("san_pham", [])) > 0


def test_catalog_song_van_tra_ve_san_pham():
    d = chay(tools._catalog_song())
    assert isinstance(d, dict)
    assert len(d.get("san_pham", [])) > 0
    assert all("gia" in sp for sp in d["san_pham"])
```

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_noi_vao_tools.py -q`
Kỳ vọng: FAIL — `ModuleNotFoundError: No module named 'agent.erp.nha_may'`

- [ ] **Step 3: Viết hiện thực tối thiểu**

Trong `agent/config.py`, chèn ngay TRƯỚC dòng `nguong_tu_chot_vnd: int = 1_000_000`:

```python
    # --- Kho / ERP ---
    # tep = đọc data/catalog.json (MẶC ĐỊNH — giữ clone sạch chạy được).
    # Đổi giá trị này là đổi nguồn dữ liệu sản phẩm, không đụng agent.
    erp_loai: str = "tep"
    # Tuổi thọ của số liệu. Quá hạn mà gọi ERP hỏng thì cổng trả None chứ
    # KHÔNG trả số cũ — xem agent/erp/cong.py.
    erp_ttl_gia: float = 900.0
    erp_ttl_ton: float = 60.0
    erp_ngat_mach_so_lan: int = 5
    erp_ngat_mach_giay: float = 30.0
    # Bắt buộc khi erp_loai != "tep": Bin của ERPNext và stock.quant của Odoo
    # đều theo từng kho, nên "còn bao nhiêu" là câu hỏi không có đáp án nếu
    # không nói kho nào. `scripts/san_sang.py` kiểm ở giai đoạn 2.
    erp_ma_kho: str = ""
    erp_pricelist: str = ""
```

Tạo `agent/erp/nha_may.py`:

```python
"""
Dựng cổng theo cấu hình. Một chỗ duy nhất biết `ERP_LOAI` nghĩa là gì.

VÌ SAO NÉM KHI `ERP_LOAI` LẠ
----------------------------
Cám dỗ là rơi về `tep` cho "an toàn". Nhưng gõ sai `ERP_LOAI=odooo` rồi lặng
lẽ đọc file là chạy suốt tháng với giá cũ mà tưởng đang nối ERP — hỏng im
lặng, đúng khuôn đã cắn repo này bốn lần. Nổ to lúc khởi động rẻ hơn nhiều.
"""
from __future__ import annotations

from agent.config import settings
from agent.erp.cong import Cong
from agent.erp.hop_dong import NguonERP

# Thêm "erpnext", "odoo", "mcp" ở giai đoạn 2-3.
_LOAI_HOP_LE = ("tep",)

_cong: Cong | None = None


def tao_nguon() -> NguonERP:
    loai = (settings.erp_loai or "tep").strip().lower()
    if loai == "tep":
        from agent.erp.tep import NguonTep

        return NguonTep()
    raise ValueError(
        f"ERP_LOAI={loai!r} không nhận ra. Hợp lệ: {', '.join(_LOAI_HOP_LE)}"
    )


def cong() -> Cong:
    global _cong
    if _cong is None:
        _cong = Cong(
            tao_nguon(),
            ttl_gia=settings.erp_ttl_gia,
            ttl_ton=settings.erp_ttl_ton,
            ngat_mach_so_lan=settings.erp_ngat_mach_so_lan,
            ngat_mach_giay=settings.erp_ngat_mach_giay,
        )
    return _cong


def dat_lai() -> None:
    """Chỉ dùng trong test."""
    global _cong
    _cong = None
```

Trong `agent/core/tools.py`, trong `_catalog_song`, thay dòng `data = _catalog()` bằng:

```python
    from agent.erp import nha_may
    from agent.erp.hop_dong import LoiERP

    try:
        data = await nha_may.cong().danh_muc()
    except LoiERP:
        # Cổng hỏng hoàn toàn thì rơi về file. Ở ĐÂY thì được, vì đây là nửa
        # tham chiếu (tên, thành phần) — giá và tồn đã bị cổng chặn ở tầng
        # dưới nếu quá hạn mà gọi không được, nên không có số cũ nào lọt lên.
        data = _catalog()
```

Giữ nguyên `_catalog()` và toàn bộ phần chồng tồn kho sống phía dưới.

Thêm vào `.env.example`:

```
# --- Kho / ERP ---
# tep = đọc data/catalog.json (mặc định, chạy được ngay sau khi clone)
ERP_LOAI=tep
ERP_TTL_GIA=900
ERP_TTL_TON=60
ERP_NGAT_MACH_SO_LAN=5
ERP_NGAT_MACH_GIAY=30
# Bắt buộc khi ERP_LOAI khác "tep"
ERP_MA_KHO=
ERP_PRICELIST=
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_cong_erp_noi_vao_tools.py -q`
Kỳ vọng: PASS, 7 test

Chạy: `./.venv/Scripts/python.exe -m pytest -q`
Kỳ vọng: PASS toàn bộ (440+ test), dưới 4 giây

Chạy: `ruff check .`
Kỳ vọng: không có lỗi

Chạy: `./.venv/Scripts/python.exe -m scripts.san_sang`
Kỳ vọng: chạy xong không nổ

- [ ] **Step 5: Commit**

```bash
git add agent/config.py agent/erp/nha_may.py agent/core/tools.py .env.example tests/test_cong_erp_noi_vao_tools.py
git commit -m "Nối cổng vào _catalog_song() — giữ nguyên chữ ký, ERP_LOAI lạ thì nổ"
```

---

### Task 8: Chốt đơn đọc tồn sống

**Files:**
- Modify: `agent/core/tools.py` (khối "Chốt 4" trong `_tao_don_hang`, khoảng dòng 676-690)
- Test: `tests/test_chot_don_doc_ton_song.py`

**Interfaces:**
- Consumes: `agent.erp.nha_may.cong()`, `Cong.ton_kho(ma, bo_qua_cache=True)`
- Produces: không có API mới — chỉ đổi hành vi chốt 4

- [ ] **Step 1: Viết test hỏng trước**

Tạo `tests/test_chot_don_doc_ton_song.py`:

```python
"""Chốt đơn phải đọc tồn kho SỐNG, không đọc cache 60 giây.

Đọc cache ở đúng khoảnh khắc chốt là để khách xác nhận xong mới bị báo hết
hàng — bắt được, nhưng bắt muộn và mất khách.
"""
import pytest

from agent.core import tools
from agent.erp import nha_may
from agent.erp.cong import Cong
from agent.erp.hop_dong import Gia, SanPhamERP, TonKho
from tests.erp_gia import NguonGia, chay


@pytest.fixture
def nguon(monkeypatch):
    n = NguonGia(
        san_pham=[SanPhamERP(ma="AS-CL01", ten="Sữa rửa mặt dịu nhẹ")],
        gia={"AS-CL01": Gia(gia_ban=245000)},
        ton={"AS-CL01": TonKho(ban_duoc=5)},
    )
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: n)
    yield n
    nha_may.dat_lai()


def test_bo_qua_cache_thi_goi_erp_that(nguon):
    c = Cong(nguon, ttl_ton=3600.0)
    chay(c.ton_kho("AS-CL01"))
    truoc = nguon.so_lan_goi["ton_kho"]
    chay(c.ton_kho("AS-CL01", bo_qua_cache=True))
    assert nguon.so_lan_goi["ton_kho"] == truoc + 1


def test_ton_song_khong_tra_duoc_thi_khong_chot_don(nguon):
    # Không biết còn bao nhiêu thì KHÔNG được chốt. Chốt liều là bán món có
    # thể đã hết, và khách chỉ biết khi không nhận được hàng.
    nguon.hong = True
    kq = chay(
        tools.run_tool(
            "tao_don_hang",
            {
                "khach_da_xac_nhan": True,
                "khach_ten": "Nguyễn Văn A",
                "khach_sdt": "0901234567",
                "khach_dia_chi": "12 Nguyễn Trãi, Thanh Xuân, Hà Nội",
                "items": [{"ten_san_pham": "sữa rửa mặt", "so_luong": 1}],
            },
            conversation_id=None,
        )
    )
    assert kq.get("tao_duoc") is False
    ly_do = kq.get("ly_do", "").lower()
    assert "tồn kho" in ly_do or "chưa tra được" in ly_do
```

**Lưu ý cho người thi công:** test thứ hai dựa vào việc `_catalog_song()` rơi về `catalog.example.json` khi cổng ném `LoiERP` (nguồn giả đang `hong=True`), nên `products` vẫn có "Sữa rửa mặt dịu nhẹ Aurora Gentle Cleanser" để chốt 3 khớp tên. Nếu chốt 3 không khớp, test sẽ đỏ với `ly_do` khác — khi đó sửa chuỗi `ten_san_pham` cho khớp danh mục mẫu, **đừng nới điều kiện assert**.

- [ ] **Step 2: Chạy test cho chắc là nó hỏng**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_chot_don_doc_ton_song.py -q`
Kỳ vọng: `test_ton_song_khong_tra_duoc_thi_khong_chot_don` FAIL — chốt 4 vẫn đọc `sp["ton_kho"]` từ danh mục nên không trả về lý do "chưa tra được tồn kho"

- [ ] **Step 3: Viết hiện thực tối thiểu**

Trong `agent/core/tools.py`, trong `_tao_don_hang`, thay hai dòng:

```python
        # --- Chốt 4: kiểm tồn kho ngay trước khi chốt ---
        ton = int(sp.get("ton_kho") or 0)
```

bằng:

```python
        # --- Chốt 4: tồn kho đọc SỐNG, bỏ qua cache ---
        # Con số trong `products` đến từ danh mục đã cache tối đa ERP_TTL_TON
        # giây. Ở mọi chỗ khác thì đủ tốt; ở đúng khoảnh khắc chốt thì không,
        # vì giữa lúc tư vấn và lúc khách gật, món cuối có thể đã bán mất.
        from agent.erp import nha_may

        ton_song = await nha_may.cong().ton_kho(sp["ma"], bo_qua_cache=True)
        if ton_song is None:
            # Không biết còn bao nhiêu thì KHÔNG chốt. Chốt liều là bán món
            # có thể đã hết, và khách chỉ biết khi không nhận được hàng.
            return {
                "tao_duoc": False,
                "ly_do": f"Chưa tra được tồn kho của {sp['ten']}. "
                         "Hãy báo khách chờ một chút và chuyển cho nhân viên.",
            }
        ton = ton_song.ban_duoc
```

- [ ] **Step 4: Chạy test cho chắc là nó xanh**

Chạy: `./.venv/Scripts/python.exe -m pytest tests/test_chot_don_doc_ton_song.py -q`
Kỳ vọng: PASS, 2 test

Chạy: `./.venv/Scripts/python.exe -m pytest -q`
Kỳ vọng: PASS toàn bộ, dưới 4 giây

Chạy: `ruff check .`
Kỳ vọng: không có lỗi

- [ ] **Step 5: Commit**

```bash
git add agent/core/tools.py tests/test_chot_don_doc_ton_song.py
git commit -m "Chốt đơn đọc tồn sống — không biết còn bao nhiêu thì không chốt"
```

---

## Sau khi xong giai đoạn 1

Chạy đủ bộ trước khi báo xong — đừng nói "đã xong" khi chưa nhìn kết quả:

```bash
./.venv/Scripts/python.exe -m pytest -q
```

```bash
ruff check .
```

```bash
./.venv/Scripts/python.exe -m scripts.san_sang
```

Sinh lại tài liệu nếu sơ đồ kiến trúc đổi:

```bash
./.venv/Scripts/python.exe -m scripts.sinh_so_do --ghi
```

Giai đoạn 2 (`erpnext.py`) và 3 (`odoo.py`) cần một instance ERP thật để xác
minh bốn giả định ở mục 12 của spec. Không có instance thì dừng ở đây — lõi
đã đứng và kiểm chứng được đầy đủ.
