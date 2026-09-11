# Khối A1 — Lớp quyền theo hành động: kế hoạch thực thi

> **Cho người/agent thực thi:** BẮT BUỘC dùng skill
> `superpowers:subagent-driven-development` (khuyến nghị) hoặc
> `superpowers:executing-plans` để làm từng việc một. Các bước dùng ô đánh
> dấu (`- [ ]`) để theo dõi.

**Mục tiêu:** Thay hệ quyền nhị phân `quan_tri|nhan_vien` bằng vai trò tự
tạo gồm các quyền theo hành động, khai quyền cho cả 158 route cần canh, và
đặt chốt kiểm ở lúc khởi động để route mới quên khai thì máy chủ không lên.

**Kiến trúc:** Danh mục quyền là hằng trong mã (`agent/core/quyen.py`); vai
trò và phép gán là dữ liệu trong CSDL. `doc_phien()` trả người kèm tập quyền
trong cùng một truy vấn. `can_quyen(...)` là dependency gắn cạnh endpoint;
`kiem_moi_route_co_quyen(app)` chạy lúc khởi động và ném nếu còn route chưa
khai. Ba trục quyền cũ (`account_memberships`, `conversation_assignments`,
middleware đăng nhập) giữ nguyên.

**Tech Stack:** Python 3.12, FastAPI, asyncpg, PostgreSQL 16 + pgvector,
pytest. Không thêm thư viện ngoài.

**Spec:** `docs/superpowers/specs/2026-09-11-quyen-va-tai-san-design.md`

## Ràng buộc toàn cục

- Mã, chú thích, tài liệu, thông báo lỗi: **tiếng Việt**.
- Chú thích giải thích **VÌ SAO**, không giải thích **LÀM GÌ**.
- Mỗi ràng buộc phải có test canh, nếu không nó sẽ bị gỡ trong một lần dọn dẹp.
- `ruff check .` phải sạch sau mỗi việc.
- Chạy test: từ worktree, `PATH="/d/Marketing Dasbhboard CSKH/.venv/Scripts:$PATH" python -m pytest tests -q`
  (worktree không có `.venv` riêng — nó bị `.gitignore`).
- Bộ test nền lúc bắt đầu: **2718 passed, 8 skipped, 419s**. Con số này là
  mốc so sánh cho mọi việc phía sau.
- Migration mới phải dùng `IF NOT EXISTS` và không sửa migration đã áp dụng
  (checksum lệch làm ứng dụng không khởi động được).
- A1 **không** đổi cách lọc dữ liệu khách. Đó là việc của A2.

---

### Việc 1: Danh mục quyền và hàm kiểm route

**Tệp:**
- Tạo: `agent/core/quyen.py`
- Tạo: `tests/test_quyen_danh_muc.py`

**Giao diện:**
- Cung cấp: `QUYEN: dict[str, str]`, `MIEN_TRU: frozenset[tuple[str, str]]`,
  `DANH_SACH_HOAN: frozenset[tuple[str, str]]`, `moi_route(gom) -> Iterator`,
  `kiem_moi_route_co_quyen(app) -> None`.

- [ ] **Bước 1: Viết test thất bại**

```python
"""
Danh mục quyền và chốt kiểm route.

Chốt này là lý do khối A tồn tại: nó bắt endpoint ra đời mà không ai canh —
loại hỏng im lặng nguy hiểm nhất ở đây, vì nó không nổ, không ghi nhật ký,
và chỉ lộ ra khi có người dùng sai quyền.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import quyen  # noqa: E402


def test_ma_quyen_dung_dinh_dang():
    """`nhom.hanh_dong`, chữ thường, không dấu — để nhóm được trên dashboard."""
    for ma in quyen.QUYEN:
        assert ma == ma.lower(), ma
        assert ma.count(".") == 1, ma
        nhom, hanh_dong = ma.split(".")
        assert nhom and hanh_dong, ma
        assert ma.replace(".", "_").replace("-", "_").isidentifier(), ma


def test_moi_quyen_co_nhan_tieng_viet():
    """Nhãn hiện trên màn cấp quyền. Thiếu nhãn là ô tick không ai hiểu."""
    for ma, nhan in quyen.QUYEN.items():
        assert nhan.strip(), ma
        assert nhan[0].isupper(), f"{ma}: nhãn nên bắt đầu bằng chữ hoa"


def test_duyet_route_phai_di_de_quy():
    """
    ĐÂY LÀ TEST QUAN TRỌNG NHẤT FILE NÀY.

    FastAPI bản đang dùng gói mỗi router đã `include_router` vào một
    `_IncludedRouter`; route thật nằm trong `.original_router`. Duyệt phẳng
    `app.routes` cho 7 route thay vì 166 — và hàm kiểm sẽ báo "mọi route đã
    khai quyền" trong khi 159 route chưa khai.

    Xanh giả. Không ai đi kiểm lại một dấu xanh.
    """
    from agent.main import app

    assert len(list(quyen.moi_route(app.routes))) >= 160


def test_mien_tru_khong_tro_vao_route_da_chet():
    """
    Miễn trừ trỏ vào đường dẫn không còn tồn tại là rác vô hại HÔM NAY.
    Ngày mai có người thêm lại đúng đường dẫn ấy và nó ra đời không được
    canh — im lặng.
    """
    from agent.main import app

    that = {
        (pt, r.path)
        for r in quyen.moi_route(app.routes)
        for pt in getattr(r, "methods", set()) or set()
    }
    chet = {mt for mt in quyen.MIEN_TRU if mt not in that}
    assert not chet, f"Miễn trừ trỏ vào route đã chết: {sorted(chet)}"


def test_danh_sach_hoan_khong_giao_voi_mien_tru():
    """Một route hoặc được miễn trừ, hoặc đang chờ khai quyền — không cả hai."""
    assert not (quyen.DANH_SACH_HOAN & quyen.MIEN_TRU)


def test_moi_route_da_khai_quyen_hoac_duoc_hoan():
    """Chốt chính. Khi DANH_SACH_HOAN rỗng, đây là chốt thật sự."""
    from agent.main import app

    quyen.kiem_moi_route_co_quyen(app)
```

- [ ] **Bước 2: Chạy test để chắc nó đỏ**

Chạy: `python -m pytest tests/test_quyen_danh_muc.py -q`
Chờ: FAIL — `ModuleNotFoundError: No module named 'agent.core.quyen'`

- [ ] **Bước 3: Viết `agent/core/quyen.py`**

Danh mục đầy đủ lấy từ spec mục 4.1. Phần khung:

```python
"""
Danh mục quyền, và chốt bắt route chưa khai quyền.

VÌ SAO DANH MỤC NẰM TRONG MÃ CHỨ KHÔNG TRONG CSDL
--------------------------------------------------
Vai trò do người tạo. Nhưng *tập quyền có thể tồn tại* thì mã quyết định.

Nếu danh mục là dữ liệu tự do, người thêm endpoint tháng sau sẽ gõ một chuỗi
quyền chưa từng tồn tại — hoặc quên gõ. Endpoint ấy thành không ai canh, và
không có gì phát hiện. Hằng trong mã cho phép chốt ở dưới quét mọi route và
bắt route nào chưa khai.

Đúng nguyên tắc của repo: ràng buộc nằm trong MÃ, không nằm trong cấu hình.
Cấu hình chỉ được SIẾT (gán ít quyền hơn), không được NỚI.
"""
from __future__ import annotations

from collections.abc import Iterator

QUYEN: dict[str, str] = {
    "hoi_thoai.doc": "Đọc hội thoại",
    # ... (đủ 36 mục theo spec 4.1)
}

# Route không cần quyền. Khai TỪNG CÁI, không dùng mẫu tiền tố.
#
# Mẫu kiểu "/webhook*" là chỗ để endpoint mới lọt vào mà không ai để ý —
# đúng loại lỗ mà `_MO` trong main.py đã cẩn thận tránh.
MIEN_TRU: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/dang-nhap"),
    ("POST", "/api/dang-xuat"),
    ("GET", "/api/toi"),
    ("GET", "/api/suc-khoe"),
    ("GET", "/api/he-thong"),
    ("GET", "/api/connect/meta/callback"),   # xác thực bằng state token
})

# Route CHƯA khai quyền, được hoãn tạm trong lúc A1 đang chạy.
#
# Danh sách này chỉ được PHÉP NHỎ ĐI. Việc cuối của A1 là xoá hẳn nó cùng
# tham số `hoan` — để lại một danh sách hoãn sau khi xong là để lại đúng cái
# lỗ mà cả khối này sinh ra để bịt.
DANH_SACH_HOAN: frozenset[tuple[str, str]] = frozenset({
    # sinh bằng scripts/_sinh_danh_sach_hoan.py ở Bước 4
})


def moi_route(gom) -> Iterator:
    """
    Duyệt ĐỆ QUY mọi route của app.

    Bản FastAPI đang dùng gói router đã `include_router` vào một
    `_IncludedRouter`; route thật nằm trong `.original_router`. Duyệt phẳng
    cho 7 route thay vì 166, và chốt dưới sẽ báo xanh trong khi 159 route
    chưa khai quyền.
    """
    for r in gom:
        goc = getattr(r, "original_router", None)
        if goc is not None:
            yield from moi_route(goc.routes)
        else:
            yield r


def kiem_moi_route_co_quyen(app, *, hoan: frozenset = DANH_SACH_HOAN) -> None:
    """
    Ném nếu còn route chưa khai quyền. Gọi lúc KHỞI ĐỘNG, không lúc chạy.

    Hỏng-đóng: endpoint mới mà quên khai thì máy chủ không lên, thay vì phơi
    ra lặng lẽ. Cùng hàm này chạy trong test nên CI bắt trước khi triển khai.

    Vì sao không tra bảng ánh xạ tập trung trong middleware: bảng nằm xa
    endpoint, đổi đường dẫn là bảng lệch âm thầm. Khai cạnh endpoint rồi kiểm
    đủ lúc khởi động giữ được cả hai.
    """
    thieu = []
    for route in moi_route(app.routes):
        duong = getattr(route, "path", "")
        if not duong.startswith(("/api", "/tich-hop")):
            continue
        phu_thuoc = getattr(getattr(route, "dependant", None), "dependencies", ())
        da_khai = any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc)
        for pt in sorted(getattr(route, "methods", set()) or set()):
            if pt in {"HEAD", "OPTIONS"}:
                continue
            if da_khai or (pt, duong) in MIEN_TRU or (pt, duong) in hoan:
                continue
            thieu.append(f"{pt} {duong}")
    if thieu:
        raise RuntimeError(
            "Route chưa khai quyền — thêm Depends(can_quyen(...)) hoặc "
            "khai vào MIEN_TRU:\n  " + "\n  ".join(sorted(thieu))
        )
```

- [ ] **Bước 4: Sinh `DANH_SACH_HOAN` từ mã đang chạy**

Không gõ tay 158 dòng — gõ tay là sai sót. Viết script tạm rồi dán kết quả:

```python
# scripts/_sinh_danh_sach_hoan.py — XOÁ ở Việc 10
import os
os.environ.setdefault("GCP_PROJECT_ID", "test")
from agent.core.quyen import MIEN_TRU, moi_route
from agent.main import app

ds = set()
for r in moi_route(app.routes):
    duong = getattr(r, "path", "")
    if not duong.startswith(("/api", "/tich-hop")):
        continue
    for pt in sorted(getattr(r, "methods", set()) or set()):
        if pt in {"HEAD", "OPTIONS"} or (pt, duong) in MIEN_TRU:
            continue
        ds.add((pt, duong))
for pt, duong in sorted(ds, key=lambda x: (x[1], x[0])):
    print(f'    ("{pt}", "{duong}"),')
print(f"# tổng: {len(ds)}")
```

Chờ: đúng **158** dòng. Lệch nhiều là dấu hiệu `moi_route` hoặc `MIEN_TRU` sai.

- [ ] **Bước 5: Chạy test để chắc nó xanh**

Chạy: `python -m pytest tests/test_quyen_danh_muc.py -q`
Chờ: PASS, 6 test.

- [ ] **Bước 6: `ruff check .`** — phải sạch.

- [ ] **Bước 7: Commit**

```bash
git add agent/core/quyen.py tests/test_quyen_danh_muc.py scripts/_sinh_danh_sach_hoan.py
git commit -m "Danh mục quyền và chốt bắt route chưa khai quyền"
```

---

### Việc 2: CI có Postgres, và test canh chính việc đó

Làm sớm, trước khi có test nào cần CSDL — nếu không A2 sẽ xanh giả.

**Tệp:**
- Sửa: `.github/workflows/kiem-thu.yml`
- Tạo: `tests/test_ci_co_postgres.py`

- [ ] **Bước 1: Viết test thất bại**

```python
"""
CI phải chạy được test chạm Postgres thật.

ĐO ĐƯỢC 11.09.2026: workflow không đặt TEST_DATABASE_URL, nên 8 test mở đầu
bằng `pytest.skip("chưa cấp TEST_DATABASE_URL...")` không bao giờ chạy — và
bảng kết quả vẫn xanh.

Ràng buộc trung tâm của A2 ("nhân viên chỉ thấy khách của mình") sống trong
một mệnh đề WHERE. Viết test cho nó theo khuôn hiện tại là viết một test
không bao giờ chạy.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "kiem-thu.yml"


def test_workflow_co_service_postgres_va_bien_moi_truong():
    noi_dung = WORKFLOW.read_text(encoding="utf-8")
    assert "TEST_DATABASE_URL" in noi_dung, (
        "CI chưa cấp TEST_DATABASE_URL — mọi test chạm Postgres sẽ bị skip "
        "và bảng kết quả vẫn xanh"
    )
    assert "pgvector" in noi_dung or "postgres" in noi_dung


@pytest.mark.skipif(not os.getenv("CI"), reason="chỉ bắt buộc khi chạy trong CI")
def test_trong_ci_thi_phai_co_that_database_url():
    """
    Chốt thứ hai, ở tầng chạy chứ không tầng đọc file: một lần sửa workflow
    vô ý có thể giữ nguyên chuỗi "TEST_DATABASE_URL" mà vẫn không truyền nó
    tới pytest. Test trên vẫn xanh; test này thì không.
    """
    assert os.getenv("TEST_DATABASE_URL"), (
        "Đang chạy trong CI nhưng thiếu TEST_DATABASE_URL"
    )
```

- [ ] **Bước 2: Chạy để chắc nó đỏ**

Chạy: `python -m pytest tests/test_ci_co_postgres.py -q`
Chờ: FAIL ở test đầu — "CI chưa cấp TEST_DATABASE_URL".

- [ ] **Bước 3: Thêm service vào workflow**

Trong job chạy pytest của `.github/workflows/kiem-thu.yml`:

```yaml
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_PASSWORD: kiemthu
          POSTGRES_DB: kiemthu
        options: >-
          --health-cmd "pg_isready -U postgres"
          --health-interval 5s --health-timeout 5s --health-retries 10
        ports:
          - 5433:5432
    env:
      TEST_DATABASE_URL: postgresql://postgres:kiemthu@localhost:5433/kiemthu
```

Dùng ảnh `pgvector/pgvector:pg16` chứ không `postgres:16` vì lược đồ có
`CREATE EXTENSION vector` — ảnh thường thiếu extension và migration ném.

- [ ] **Bước 4: Chạy lại** — `python -m pytest tests/test_ci_co_postgres.py -q` → PASS.

- [ ] **Bước 5: Commit**

```bash
git add .github/workflows/kiem-thu.yml tests/test_ci_co_postgres.py
git commit -m "CI có Postgres thật, và test canh chính việc đó"
```

---

### Việc 3: Migration vai trò, nạp sẵn và backfill

**Tệp:**
- Tạo: `agent/migrations/versions/0019_quyen_va_vai_tro.sql`
- Sửa: `agent/schema.sql` (thêm ba bảng cho bản clone sạch)
- Tạo: `tests/test_migration_vai_tro.py`

**Giao diện:**
- Cung cấp: bảng `vai_tro`, `vai_tro_quyen`, `nguoi_dung_vai_tro`; hai vai trò
  `he_thong`: `Quản trị` và `Nhân viên`.

- [ ] **Bước 1: Viết test thất bại**

```python
"""Migration 0019: vai trò tự tạo thay hai vai trò cứng."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "agent" / "migrations" / "versions" / "0019_quyen_va_vai_tro.sql"


def test_migration_ton_tai_va_dung_if_not_exists():
    noi_dung = SQL.read_text(encoding="utf-8")
    for bang in ("vai_tro", "vai_tro_quyen", "nguoi_dung_vai_tro"):
        assert f"CREATE TABLE IF NOT EXISTS {bang}" in noi_dung, bang


def test_nap_san_hai_vai_tro_he_thong():
    noi_dung = SQL.read_text(encoding="utf-8")
    assert "Quản trị" in noi_dung and "Nhân viên" in noi_dung
    assert "he_thong" in noi_dung


def test_backfill_moi_nguoi_dung_deu_co_vai_tro():
    """
    Không backfill là mọi người mất sạch quyền sau khi migration chạy —
    kể cả quản trị, tức KHOÁ CỨNG ngoài hệ thống.
    """
    noi_dung = SQL.read_text(encoding="utf-8")
    assert "INSERT INTO nguoi_dung_vai_tro" in noi_dung
    assert "FROM nguoi_dung" in noi_dung


def test_moi_quyen_nap_san_co_that_trong_danh_muc():
    """
    Migration gõ chuỗi quyền bằng tay. Gõ sai thì vai trò nạp sẵn cấp một
    quyền không tồn tại — im lặng, và người quản trị mất đúng màn đó.
    """
    from agent.core.quyen import QUYEN

    noi_dung = SQL.read_text(encoding="utf-8")
    ma_trong_sql = set(re.findall(r"'([a-z_]+\.[a-z_]+)'", noi_dung))
    la = ma_trong_sql - set(QUYEN)
    assert not la, f"Migration nhắc quyền không có trong danh mục: {sorted(la)}"
```

- [ ] **Bước 2: Chạy để chắc nó đỏ** — `python -m pytest tests/test_migration_vai_tro.py -q` → FAIL (thiếu file).

- [ ] **Bước 3: Viết migration**

Lược đồ ba bảng theo spec 4.2. Phần nạp sẵn và backfill:

```sql
-- Hai vai trò dựng sẵn. `he_thong = true` để API từ chối xoá chúng: xoá vai
-- trò Quản trị khi nó là vai trò duy nhất có `nguoi_dung.sua` là tự khoá
-- mình ra ngoài, và không có đường nào vào lại ngoài sửa tay trong CSDL.
INSERT INTO vai_tro (ten, mo_ta, he_thong) VALUES
    ('Quản trị', 'Toàn quyền. Vai trò dựng sẵn, không xoá được.', true),
    ('Nhân viên', 'Trả lời khách và xem đơn. Vai trò dựng sẵn, không xoá được.', true)
ON CONFLICT (ten) DO NOTHING;

-- Tập quyền của `Nhân viên` chọn để BẰNG ĐÚNG những gì nhân viên làm được
-- trước migration này — không hơn không kém. Migration không được là chỗ
-- lặng lẽ đổi quyền của người đang làm việc.
--
-- `khach.pii` có trong tập vì hôm nay nhân viên xem được PII khi là
-- owner/manager của tài khoản kênh; trục `account_memberships` vẫn siết
-- tiếp phía sau, nên để quyền này ở đây không nới thêm gì.
INSERT INTO vai_tro_quyen (vai_tro_id, quyen)
SELECT vt.id, q.ma
FROM vai_tro vt
CROSS JOIN (VALUES
    ('hoi_thoai.doc'), ('hoi_thoai.tra_loi'), ('hoi_thoai.nhan'),
    ('khach.doc'), ('khach.sua'), ('khach.pii'), ('khach.gop'),
    ('don.doc'), ('kenh.doc'), ('bao_cao.doc'),
    ('noi_dung.doc'), ('outbox.doc')
) AS q(ma)
WHERE vt.ten = 'Nhân viên'
ON CONFLICT DO NOTHING;

-- Backfill: mỗi người nhận vai trò tương ứng cột `vai_tro` cũ.
--
-- Không có bước này thì sau migration KHÔNG AI có quyền gì — kể cả quản
-- trị. Đó là khoá cứng ngoài hệ thống, và nó không nổ: đăng nhập vẫn được,
-- chỉ là mọi màn đều 403.
INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id)
SELECT nd.id, vt.id
FROM nguoi_dung nd
JOIN vai_tro vt
  ON vt.ten = CASE WHEN nd.vai_tro = 'quan_tri' THEN 'Quản trị'
                   ELSE 'Nhân viên' END
ON CONFLICT DO NOTHING;
```

Quyền của `Quản trị` **không** gõ trong SQL: nó là *toàn bộ danh mục*, và
danh mục ở trong mã. Gõ lại trong SQL là tạo bản sao thứ hai sẽ lệch ở bản
sau. Xử lý ở Việc 4: người có vai trò `he_thong` tên `Quản trị` nhận
`frozenset(QUYEN)`.

- [ ] **Bước 4: Thêm ba bảng vào `agent/schema.sql`** — bản clone sạch dựng
  lược đồ từ đây, không chạy migration.

- [ ] **Bước 5: Chạy test** → PASS, 4 test. Và `python -m pytest tests/test_migrations.py -q` → PASS.

- [ ] **Bước 6: `ruff check .`**

- [ ] **Bước 7: Commit**

```bash
git add agent/migrations/versions/0019_quyen_va_vai_tro.sql agent/schema.sql tests/test_migration_vai_tro.py
git commit -m "Bảng vai trò tự tạo, nạp sẵn hai vai trò và backfill người đang có"
```

---

### Việc 4: `doc_phien` trả kèm quyền; `duoc_phep` viết lại

**Tệp:**
- Sửa: `agent/core/xac_thuc.py:50-58` (bỏ `CHI_QUAN_TRI`), `:316-329` (`doc_phien`), `:343-348` (`duoc_phep`)
- Sửa: `tests/test_xac_thuc.py`

**Giao diện:**
- Tiêu thụ: `agent.core.quyen.QUYEN`
- Cung cấp: `doc_phien(token) -> dict | None` với khoá thêm `quyen: frozenset[str]`;
  `duoc_phep(nguoi, quyen: str) -> bool` ném `KeyError` nếu quyền không có
  trong danh mục.

- [ ] **Bước 1: Viết test thất bại**

```python
def test_duoc_phep_nem_khi_quyen_khong_co_trong_danh_muc():
    """
    Ném chứ không trả False.

    Trả False nghĩa là gõ sai tên quyền thì endpoint khoá với TẤT CẢ mọi
    người — một lỗi chính tả thành sự cố vận hành mà không ai hiểu vì sao.
    Ném thì nó nổ lúc khởi động, ngay trước mặt người vừa gõ sai.
    """
    nguoi = {"id": "x", "quyen": frozenset({"khach.doc"})}
    with pytest.raises(KeyError):
        xac_thuc.duoc_phep(nguoi, "khach.khong_co_that")


def test_duoc_phep_doc_tap_quyen_chu_khong_doc_vai_tro():
    nguoi = {"id": "x", "vai_tro": "nhan_vien", "quyen": frozenset({"khach.doc"})}
    assert xac_thuc.duoc_phep(nguoi, "khach.doc")
    assert not xac_thuc.duoc_phep(nguoi, "khach.xoa")


def test_vai_tro_quan_tri_khong_con_tu_dong_cho_qua():
    """
    Cột `vai_tro` thôi làm nguồn sự thật. Người mang nhãn quan_tri mà không
    được gán vai trò nào thì không có quyền nào — nếu không, cột cũ vẫn âm
    thầm cấp quyền và cả lớp mới thành trang trí.
    """
    nguoi = {"id": "x", "vai_tro": "quan_tri", "quyen": frozenset()}
    assert not xac_thuc.duoc_phep(nguoi, "khach.xoa")


def test_khong_con_hang_chi_quan_tri():
    assert not hasattr(xac_thuc, "CHI_QUAN_TRI")
```

- [ ] **Bước 2: Chạy để chắc nó đỏ** — `python -m pytest tests/test_xac_thuc.py -q`

- [ ] **Bước 3: Sửa `doc_phien`**

```python
async def doc_phien(token: str) -> dict | None:
    """
    Người đứng sau token này, hoặc None nếu phiên hỏng/hết hạn.

    Quyền nạp CÙNG truy vấn này, không cache vào phiên. Cache vào phiên
    nghĩa là thu quyền lúc 9 giờ sáng mà người đó vẫn dùng được tới lúc hết
    hạn — đúng thứ bảng `phien` sinh ra để tránh (xem schema.sql, mục "Phiên
    nằm trong CSDL chứ không phải JWT"). Cache là đưa lỗi ấy vào qua cửa sau.

    Không thêm vòng gọi CSDL nào: hai LEFT JOIN trên khoá chính.
    """
    if not token:
        return None
    r = await db.fetchrow(
        "SELECT n.id, n.ten_dang_nhap, n.ho_ten, n.vai_tro, n.khoa, "
        "       COALESCE(array_agg(DISTINCT vq.quyen) "
        "                FILTER (WHERE vq.quyen IS NOT NULL), '{}') AS quyen, "
        "       bool_or(vt.he_thong AND vt.ten = 'Quản trị') AS la_quan_tri "
        "FROM phien p "
        "JOIN nguoi_dung n ON n.id = p.nguoi_dung_id "
        "LEFT JOIN nguoi_dung_vai_tro ndvt ON ndvt.nguoi_dung_id = n.id "
        "LEFT JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
        "LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = ndvt.vai_tro_id "
        "WHERE p.token = $1 AND p.het_han > now() "
        "GROUP BY n.id",
        token,
    )
    if r is None or r["khoa"]:
        return None
    nguoi = dict(r)
    nguoi["id"] = str(nguoi["id"])
    # Vai trò `Quản trị` nhận TOÀN BỘ danh mục, tính từ mã chứ không từ CSDL.
    # Gõ lại danh mục trong migration là tạo bản sao thứ hai, và bản sao sẽ
    # lệch ở phiên bản sau: thêm quyền mới vào mã thì quản trị không có nó.
    nguoi["quyen"] = (frozenset(QUYEN) if nguoi.pop("la_quan_tri", False)
                      else frozenset(nguoi["quyen"]))
    return nguoi
```

- [ ] **Bước 4: Viết lại `duoc_phep`, xoá `CHI_QUAN_TRI`**

```python
def duoc_phep(nguoi: dict | None, quyen: str) -> bool:
    """Người này có quyền này không. Quyền lạ thì NÉM, không đoán."""
    if quyen not in QUYEN:
        raise KeyError(f"Quyền không có trong danh mục: {quyen}")
    if not nguoi:
        return False
    return quyen in nguoi.get("quyen", frozenset())
```

- [ ] **Bước 5: Chạy test** — `python -m pytest tests/test_xac_thuc.py -q` → PASS.

- [ ] **Bước 6: `ruff check .`**

- [ ] **Bước 7: Commit**

```bash
git add agent/core/xac_thuc.py tests/test_xac_thuc.py
git commit -m "Phiên trả kèm tập quyền; duoc_phep đọc quyền thay vì đọc vai trò"
```

---

### Việc 5: `can_quyen()` — dependency khai quyền cạnh endpoint

**Tệp:**
- Sửa: `agent/api/routes.py:80-84` (cạnh `bat_buoc_quan_tri`)
- Tạo: `tests/test_can_quyen.py`

**Giao diện:**
- Cung cấp: `can_quyen(*quyen: str)` trả dependency có thuộc tính
  `quyen_yeu_cau: tuple[str, ...]`.

- [ ] **Bước 1: Viết test thất bại**

```python
def test_can_quyen_nem_ngay_luc_goi_neu_quyen_la():
    """
    Kiểm ở THÂN factory, không trong hàm con — nó chạy lúc import module,
    nên gõ sai tên quyền làm máy chủ KHÔNG KHỞI ĐỘNG ĐƯỢC, thay vì một 403
    bí ẩn lúc 2 giờ sáng.
    """
    with pytest.raises(KeyError):
        routes.can_quyen("khong.ton_tai")


def test_dependency_mang_nhan_quyen_yeu_cau():
    """Chốt lúc khởi động nhận ra endpoint đã khai quyền nhờ nhãn này."""
    d = routes.can_quyen("khach.doc", "khach.sua")
    assert d.quyen_yeu_cau == ("khach.doc", "khach.sua")


def _request_gia(quyen_co):
    """Request tối thiểu đủ cho dependency: chỉ cần cookie phiên."""
    from starlette.datastructures import Headers
    from starlette.requests import Request

    r = Request({"type": "http", "headers": Headers({}).raw, "method": "GET",
                 "path": "/", "query_string": b""})
    r.scope["_nguoi_gia"] = {"id": "u1", "quyen": frozenset(quyen_co)}
    return r


@pytest.mark.asyncio
async def test_thieu_quyen_thi_403_va_noi_ro_thieu_gi(monkeypatch):
    """
    Thông báo phải NÓI TÊN quyền còn thiếu.

    "Không có quyền" chung chung buộc người quản trị đoán, và họ sẽ đoán
    bằng cách cấp thêm cả cụm quyền cho chắc — tức là nới quyền vì thông
    báo lỗi kém.
    """
    monkeypatch.setattr(routes, "bat_buoc_dang_nhap",
                        lambda req: req.scope["_nguoi_gia"])
    kiem = routes.can_quyen("khach.xoa")
    with pytest.raises(HTTPException) as loi:
        await kiem(_request_gia({"khach.doc"}))
    assert loi.value.status_code == 403
    assert "khach.xoa" in loi.value.detail


@pytest.mark.asyncio
async def test_nhieu_quyen_la_phai_co_du_khong_phai_mot_trong_so(monkeypatch):
    """
    `can_quyen("a", "b")` đòi CẢ HAI. Hiểu nhầm thành "một trong hai" là nới
    quyền ở mọi chỗ dùng nhiều quyền — và nới thì không ai phát hiện, vì
    không có gì hỏng.
    """
    monkeypatch.setattr(routes, "bat_buoc_dang_nhap",
                        lambda req: req.scope["_nguoi_gia"])
    kiem = routes.can_quyen("khach.doc", "khach.sua")
    with pytest.raises(HTTPException):
        await kiem(_request_gia({"khach.doc"}))          # có một -> vẫn chặn
    nguoi = await kiem(_request_gia({"khach.doc", "khach.sua"}))
    assert nguoi["id"] == "u1"                            # có đủ -> qua
```

- [ ] **Bước 2: Chạy để chắc nó đỏ**

- [ ] **Bước 3: Viết `can_quyen`** — theo spec 4.5.

- [ ] **Bước 4: Chạy test** → PASS.

- [ ] **Bước 5: Commit**

```bash
git add agent/api/routes.py tests/test_can_quyen.py
git commit -m "can_quyen(): khai quyền cạnh endpoint, kiểm danh mục lúc import"
```

---

### Việc 6–9: Khai quyền cho 158 route

Bốn việc cùng khuôn. Mỗi việc: đổi `Depends(bat_buoc_quan_tri)` hoặc
`Depends(bat_buoc_dang_nhap)` thành `Depends(can_quyen("..."))`, **xoá đúng
những cặp đó khỏi `DANH_SACH_HOAN`**, chạy `tests/test_quyen_danh_muc.py` và
bộ test của file liên quan.

Sau mỗi việc, `DANH_SACH_HOAN` phải nhỏ đi đúng bằng số route vừa khai —
kiểm bằng cách chạy lại `scripts/_sinh_danh_sach_hoan.py` và so.

#### Việc 6 — Cấu hình, kênh, tích hợp (35 route)

| Route | Quyền |
|---|---|
| `GET /api/cai-dat-api`, `GET /api/cau-hinh`, `GET /api/cau-hinh/lich-su` | `cau_hinh.doc` |
| `PUT|DELETE /api/cai-dat-api/{khoa}`, `POST /api/cai-dat-api/kiem-tra`, `POST /api/cau-hinh/mac-dinh` | `cau_hinh.sua` |
| `GET /api/channel-accounts`, `GET /api/channel-accounts/{id}`, `/health`, `/co-xoa-duoc`, `/verify-token`, `/zalo-personal/status`, `GET /api/channels`, `GET /api/zalo/accounts` | `kenh.doc` |
| `POST|DELETE /api/channel-accounts`, `{id}`, `/credentials`, `/enable`, `/disable`, `/verify`, `/dang-ky-webhook`, `/zalo-personal/restore`, `POST /api/zalo/account` | `kenh.sua` |
| `GET /api/connect/meta/start`, `POST /api/connect/meta/chon`, `POST /api/channel-accounts/{id}/zalo-personal/qr` | `kenh.noi` |
| `GET /api/tich-hop/ung-dung` | `tich_hop.doc` |
| `POST|DELETE /api/tich-hop/ung-dung*`, `/thu` | `tich_hop.sua` |
| `GET|POST|PUT|PATCH|DELETE /tich-hop/{ten}`, `/tich-hop/{ten}/{duong:path}` | `tich_hop.doc` |

`/tich-hop/{ten}/{duong:path}` là proxy thẳng vào ZaloCRM và Chatwoot, và
lớp proxy XOÁ header chống nhúng của chúng (xem chú thích `main.py:739`).
Để nó ở `tich_hop.doc` — không phải `.sua` — vì đây là đường xem, nhưng nó
**phải** có quyền: không có thì cổng 8000 là cửa sau vào cả hai hệ thống với
bất kỳ nhân viên nào.

#### Việc 7 — Kỹ năng, plugin, MCP, phòng thử (29 route)

| Route | Quyền |
|---|---|
| `GET /api/ky-nang`, `GET /api/goi-ky-nang`, `GET /api/goi-ky-nang/{ten}/lich-su`, `/xuat`, `GET /api/ky-nang/plugin/{ten}/lich-su` | `ky_nang.doc` |
| `POST /api/ky-nang/bat-tat`, `/plugin`, `/plugin/thu`, `DELETE /plugin/{ten}`, `POST /plugin/{ten}/khoi-phuc/{id_ban}`, `POST|DELETE /api/goi-ky-nang*`, `/kiem`, `/tep`, `/{ten}/bat-tat`, `/{ten}/khoi-phuc/{id}` | `ky_nang.sua` |
| `GET /api/mcp` | `mcp.doc` |
| `POST|DELETE /api/mcp*`, `/kiem`, `/{ten}/bat-tat`, `/{ten}/dong-bo`, `/{ten}/cong-cu/{ten_cong_cu}` | `mcp.sua` |
| Mọi `/api/phong-thu/*` | `phong_thu.dung` |

#### Việc 8 — Hội thoại, khách, inbox, ERP đọc (44 route)

| Route | Quyền |
|---|---|
| `GET /api/conversations`, `/{id}`, `GET /api/inbox/conversations`, `/{id}`, `GET /api/inbox/events`, `GET /api/events`, `GET /api/overview`, `GET /api/attachments/{id}/file` | `hoi_thoai.doc` |
| `POST /api/conversations/{id}/send`, `/send-file`, `POST /api/messages/{id}/approve` | `hoi_thoai.tra_loi` |
| `POST .../takeover`, `/release`, `/che-do`, `/read`, `POST /api/conversations/{id}/account` | `hoi_thoai.nhan` |
| `GET /api/contacts`, `/{id}`, `GET /api/contacts/merge/preview` | `khach.doc` |
| `POST /api/contacts/{id}/tags`, `/notes`, `PUT .../consents/{purpose}` | `khach.sua` |
| `POST /api/contacts/merge`, `POST /api/contacts/merges/{id}/undo` | `khach.gop` |
| `GET /api/pdpd`, `/{sdt}`, `POST /api/pdpd/don-theo-han` | `khach.pii` |
| `POST /api/pdpd/{sdt}/xoa`, `POST /api/contacts/{id}/retention-jobs`, mọi `/api/data-retention/jobs*` | `khach.xoa` |
| `GET /api/erp/san-pham`, `/{ma}`, `/ton-kho/{ma}`, `/suc-khoe`, `POST /api/erp/kiem-ket-noi`, `GET /api/san-pham/{ma}/anh`, `GET /api/catalog/products` | `don.doc` |
| `GET|POST|DELETE /api/erp/xac-nhan-bang-gia` | `catalog.duyet` |
| `GET /api/routing` | `dinh_tuyen.doc` |
| `POST /api/routing/rules`, `/teams`, `PUT /api/routing/sla-policies`, `/teams/{id}/members/{uid}` | `dinh_tuyen.sua` |
| `GET /api/outbox/jobs` | `outbox.doc` |
| `POST /api/outbox/jobs/{id}/retry`, `/cancel` | `outbox.sua` |
| `POST /api/runtime` | `agent.dieu_khien` |
| `GET /api/nguoi-dung` | `nguoi_dung.doc` |
| `POST /api/nguoi-dung`, `/{ten}/khoa`, `POST /api/toi/doi-mat-khau` | `nguoi_dung.sua` |

`POST /api/toi/doi-mat-khau` đổi mật khẩu của **chính mình** — nó không thuộc
`nguoi_dung.sua`. Khai nó vào `MIEN_TRU` thay vì gán quyền: bắt buộc quyền ở
đây nghĩa là người bị thu hết quyền cũng không đổi được mật khẩu của mình.

#### Việc 9 — Đơn, kho, nội dung, báo cáo (50 route)

| Route | Quyền |
|---|---|
| `GET /api/orders`, `/api/kho`, `/api/kho/bien-dong` | `don.doc` |
| `POST /api/orders/{id}/approve`, `/cancel`, `POST /api/kho/{ma}/nhap`, `/kiem-ke` | `don.sua` |
| `GET /api/videos`, `/{id}/assets`, `/{id}/assets/{ord}/file`, `/{id}/file`, `GET /api/posts`, `/{id}/kit`, `/{id}/video`, `/{id}/metrics`, `GET /api/publish/channels` | `noi_dung.doc` |
| `POST /api/videos`, `/upload`, `/{id}/retry`, `POST /api/posts`, `/posts/draft` | `noi_dung.doc` |
| `POST /api/videos/{id}/approve`, `POST /api/posts/{id}/approve`, `/cancel`, `/mark-posted`, `POST /api/posts/approve-all`, `POST /api/campaigns` | `noi_dung.duyet` |
| `GET /api/knowledge`, `POST /api/knowledge/probe` | `cau_hinh.doc` |
| `POST /api/knowledge`, `DELETE /api/knowledge/{doc_id}` | `cau_hinh.sua` |
| `GET /api/analytics`, `/analytics/khach`, `/api/cost` | `bao_cao.doc` |
| `POST /api/posts/{id}/callback`, `POST /api/posts/{id}/metrics` | **xem cảnh báo dưới** |

**Cảnh báo phải xử lý, không được bỏ qua.** Hai route cuối do **máy** gọi
(n8n gọi về sau khi đăng xong), không phải người. Chúng đang nằm sau chốt
đăng nhập, nghĩa là n8n phải cầm cookie phiên của một người thật — một bí
mật dài hạn nằm sai chỗ.

Kiểm `docs/n8n-dang-bai.json` xem workflow đang xác thực bằng gì:

- Nếu nó gửi cookie phiên → **không** khai miễn trừ. Chuyển sang khoá riêng
  như `WEBHOOK_SECRET`, rồi mới miễn trừ. Ghi việc này ra một dòng trong
  phần "Còn lại" ở cuối kế hoạch nếu phải tách thành đợt riêng.
- Nếu nó đã dùng khoá riêng → khai `MIEN_TRU` kèm chú thích nói rõ đường
  nào xác thực nó.

Đừng khai miễn trừ trước rồi tính sau: miễn trừ là mở cửa, và cửa mở tạm
thì không ai đóng lại.

---

### Việc 10: Xoá danh sách hoãn, gắn chốt vào khởi động

**Tệp:**
- Sửa: `agent/core/quyen.py` (xoá `DANH_SACH_HOAN` và tham số `hoan`)
- Sửa: `agent/main.py` (sau khối `include_router`)
- Sửa: `agent/api/routes.py` (xoá `bat_buoc_quan_tri`)
- Xoá: `scripts/_sinh_danh_sach_hoan.py`

- [ ] **Bước 1: Viết test thất bại**

```python
def test_khong_con_danh_sach_hoan():
    """
    Để lại một danh sách hoãn sau khi A1 xong là để lại đúng cái lỗ mà cả
    khối này sinh ra để bịt.
    """
    from agent.core import quyen

    assert not hasattr(quyen, "DANH_SACH_HOAN")


def test_khong_con_bat_buoc_quan_tri():
    """
    Xoá hẳn, không giữ làm bí danh. Nó đang canh 73 endpoint với bảy nhóm
    quyền khác nhau; bí danh trỏ vào bất cứ quyền đơn lẻ nào cũng cấp sai
    hoặc chặn sai ở phần lớn chỗ còn lại — và sai theo kiểu chạy được.

    Xoá hẳn còn là hỏng-đóng: sót một điểm gọi thì NameError lúc import,
    máy chủ không lên.
    """
    from agent.api import routes

    assert not hasattr(routes, "bat_buoc_quan_tri")


def test_khoi_dong_goi_chot_kiem_route():
    noi_dung = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert "kiem_moi_route_co_quyen(app)" in noi_dung


def test_khong_con_cho_nao_quyet_dinh_quyen_bang_vai_tro():
    """
    Quét mã: cột `vai_tro` thôi làm nguồn sự thật về quyền.

    Ba chỗ đã biết phải dọn, tìm bằng grep trước khi bắt đầu Việc 6:
      agent/omnichannel/account_service.py:45   `self.role == "quan_tri"`
      agent/api/channel_accounts.py:110,130,234,417
      agent/api/contacts.py:513, agent/api/inbox.py:306
    Bốn chỗ sau truyền `is_admin` xuống SQL lọc — ĐỔI SANG `khach.pii` hoặc
    `kenh.sua` tuỳ chỗ, KHÔNG đổi ngữ nghĩa lọc. Đổi ngữ nghĩa lọc là lấn
    sang A2.
    """
    import re

    vi_pham = []
    for tep in (ROOT / "agent").rglob("*.py"):
        if tep.name == "xac_thuc.py":
            continue
        for i, dong in enumerate(tep.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'vai_tro["\']?\]?\s*==\s*["\']quan_tri', dong):
                vi_pham.append(f"{tep.relative_to(ROOT)}:{i}")
    assert not vi_pham, f"Còn quyết định quyền bằng vai_tro: {vi_pham}"


# Quyền chưa có chỗ dùng trong A1. Danh sách này phải RỖNG khi A2 xong.
QUYEN_HOAN_SANG_A2 = {"khach.giao"}


def test_moi_quyen_deu_co_it_nhat_mot_route_dung():
    """
    Bắt quyền chết.

    Quyền chết làm màn cấp quyền hiện một ô tick không có tác dụng gì —
    người quản trị tick vào, tin là đã cấp, và không có gì phản hồi rằng họ
    vừa làm một việc vô nghĩa.
    """
    from agent.core.quyen import QUYEN, moi_route
    from agent.main import app

    da_dung = set()
    for r in moi_route(app.routes):
        for x in getattr(getattr(r, "dependant", None), "dependencies", ()):
            da_dung.update(getattr(x.call, "quyen_yeu_cau", ()) or ())
    chet = set(QUYEN) - da_dung - QUYEN_HOAN_SANG_A2
    assert not chet, f"Quyền không có chỗ dùng: {sorted(chet)}"


def test_khong_co_quyen_mo_coi_trong_csdl():
    """
    Quyền bị xoá khỏi danh mục ở bản sau mà vẫn còn dòng trong
    `vai_tro_quyen` là rác im lặng: màn cấp quyền không hiện nó, nên không
    ai gỡ được, và nó ở lại mãi.

    `doc_phien` đã lọc bỏ lúc nạp nên nó vô hại về mặt quyền — test này canh
    việc DỌN, không canh việc chặn.
    """
    from agent.core.quyen import QUYEN
    from agent.migrations.runner import VERSIONS_DIR

    import re
    for sql in VERSIONS_DIR.glob("*.sql"):
        for ma in re.findall(r"'([a-z_]+\.[a-z_]+)'", sql.read_text(encoding="utf-8")):
            assert ma in QUYEN, f"{sql.name} nhắc quyền đã biến mất: {ma}"
```

- [ ] **Bước 2: Chạy để chắc nó đỏ**

- [ ] **Bước 3: Gắn chốt vào `main.py`**, ngay sau dòng `include_router` cuối:

```python
# Chốt hỏng-đóng: route chưa khai quyền thì máy chủ KHÔNG LÊN.
#
# Đặt ở đây chứ không trong middleware vì mỗi endpoint cần một quyền khác
# nhau — không chặn theo tiền tố đường dẫn được như chốt đăng nhập ở dưới.
# Dời chốt sang lúc khởi động giữ nguyên tính hỏng-đóng: quên khai thì nổ
# ngay, không phải một endpoint phơi ra lặng lẽ.
quyen.kiem_moi_route_co_quyen(app)
```

- [ ] **Bước 4: Xoá `DANH_SACH_HOAN`, tham số `hoan`, `bat_buoc_quan_tri`, script tạm**

- [ ] **Bước 5: Chạy TOÀN BỘ test** — `python -m pytest tests -q`

Chờ: 2718+ passed, **0 failed**, và số skipped ≤ 8. Bất kỳ test nào đỏ ở
nhóm 2 thì sửa bằng cách **cấp vai trò cho người dùng thử**, không bằng cách
nới quyền.

- [ ] **Bước 6: Khởi động thật để chắc chốt không chặn nhầm**

```bash
python -m uvicorn agent.main:app --port 8001
```

Chờ: lên được, không `RuntimeError`. Tắt ngay sau khi thấy dòng
"Application startup complete".

- [ ] **Bước 7: `ruff check .`** và commit.

---

### Việc 11: API vai trò

**Tệp:**
- Tạo: `agent/api/quyen.py` (prefix `/api`), `tests/test_api_vai_tro.py`
- Sửa: `agent/main.py` (include router)

**Giao diện:** bảy endpoint theo spec 4.6.

- [ ] **Bước 1: Viết test thất bại** — bốn test canh, quan trọng nhất:

```python
def test_khong_thu_duoc_quyen_nguoi_dung_sua_cuoi_cung():
    """
    KHOÁ CỨNG NGOÀI HỆ THỐNG.

    Thu mất người cuối cùng có `nguoi_dung.sua` thì không còn ai vào được màn
    nhân viên để sửa lại. Đường vào duy nhất còn lại là sửa tay trong CSDL.

    Chặn đủ BA đường, vì chỉ chặn một đường là để hở hai:
      - xoá vai trò đang giữ quyền ấy
      - bỏ quyền ấy khỏi vai trò
      - gỡ vai trò ấy khỏi người cuối cùng

    Kiểm trong CÙNG GIAO DỊCH với lệnh ghi, không kiểm trước rồi ghi sau:
    hai quản trị bấm gỡ cùng lúc thì kiểm-rồi-ghi cho qua cả hai.
    """


def test_khong_xoa_duoc_vai_tro_he_thong():
    ...  # 409


def test_nguoi_khong_co_vai_tro_nao_van_vao_duoc_va_thay_loi_ro():
    """
    Màn trống kèm "Chưa được cấp quyền nào — liên hệ quản trị", không phải
    403 trắng trang. 403 trắng trang làm người ta tưởng hệ thống hỏng và đi
    khởi động lại máy chủ.
    """


def test_giai_thich_quyen_noi_ro_vai_tro_nao_cap():
    """
    `GET /api/nguoi-dung/{id}/quyen` trả từng quyền kèm vai trò cấp nó.
    Không có màn này thì khi đông vai trò, không ai trả lời được vì sao
    người này vào được màn kia.
    """
```

- [ ] **Bước 2–5:** chạy đỏ → viết router → chạy xanh → `ruff` → commit.

---

### Việc 12: Dashboard — màn Vai trò

**Tệp:** `dashboard/index.html`, `dashboard/app.js`, `dashboard/app.css`

- [ ] Màn **Vai trò**: danh sách (tên, mô tả, số người), trình sửa với danh
  mục quyền nhóm theo tiền tố, vai trò hệ thống hiện khoá và không có nút xoá.
- [ ] Màn **Nhân viên**: thêm cột Vai trò và nút "Quyền của người này".
- [ ] Cảnh báo trước khi xoá vai trò: "N người sẽ mất các quyền này".
- [ ] Ẩn mục menu mà người dùng không có quyền — **chỉ để đỡ rối mắt, không
      phải để bảo vệ**. Lọc thật nằm ở API; ẩn ở giao diện mà không chặn ở
      API là đúng loại hỏng im lặng khối này sinh ra để bịt.
- [ ] Commit.

---

### Việc 13: Tài liệu

**Tệp:** `CLAUDE.md`, `docs/kien-truc.md`, `docs/van-hanh.md`

- [ ] Sinh lại sơ đồ: `python -m scripts.sinh_so_do --ghi`
- [ ] `CLAUDE.md`: sửa "~1575 test, khoảng 1 phút" → số thật sau A1 (nền đo
      được trước A1 là **2718 test, 7 phút**). Con số sai trong tài liệu làm
      người ta tưởng bộ test treo và bấm huỷ.
- [ ] `docs/van-hanh.md`: thêm mục quản lý vai trò, và **cách vào lại khi
      lỡ tự khoá mình ra ngoài** (câu SQL gán lại vai trò Quản trị). Không
      có mục này thì sự cố ấy là sự cố không lối thoát.
- [ ] Chạy `python -m pytest tests -q` lần cuối; `ruff check .`; commit.

---

## Còn lại sau A1

- **A2** — chủ sở hữu khách, bốn mức tầm nhìn, chỉ số khách vô chủ. Kế hoạch
  riêng, viết sau khi A1 xong để dựa trên mã thật.
- Bốn quyền `khach.giao`, `hoi_thoai.nhan`, `khach.xoa`, `hoi_thoai.tra_loi`
  đã dùng trong A1; `khach.giao` là quyền duy nhất của A2 chưa có chỗ dùng —
  giữ trong danh sách hoãn tường minh của test số 4, và danh sách ấy phải
  rỗng khi A2 xong.
