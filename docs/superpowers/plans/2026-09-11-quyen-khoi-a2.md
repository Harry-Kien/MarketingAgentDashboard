# Khối A2 — Giao khách cho nhân viên: kế hoạch thực thi

> **Cho người/agent thực thi:** dùng skill `superpowers:executing-plans`.
> Các bước dùng ô đánh dấu (`- [ ]`).

**Mục tiêu:** Mỗi khách có thể được giao cho một nhân viên; quản trị chọn
nhân viên khác thấy gì về khách không phải của mình; và khách chưa có chủ
không lặng lẽ tích lại.

**Kiến trúc:** Một cột `owner_user_id` trên `contacts` cộng bảng lịch sử
riêng. Một hàm duy nhất sinh mệnh đề `WHERE` cho mọi truy vấn khách. Bốn
mức tầm nhìn là một thiết lập trong `cau_hinh_agent`, mặc định `tat`.

**Spec:** `docs/superpowers/specs/2026-09-11-quyen-va-tai-san-design.md`
mục 2.4 – 2.7, 4.7, 4.8.

## Ràng buộc toàn cục

- Tiếng Việt. Chú thích giải thích VÌ SAO.
- Mỗi ràng buộc một test canh. `ruff check .` sạch.
- Chạy test: `PATH="/d/Marketing Dasbhboard CSKH/.venv/Scripts:$PATH" TEST_DATABASE_URL="postgresql://agent:agent@127.0.0.1:5433/kiemthu_quyen" python -m pytest tests -q`
- Mốc sau A1: **2773 passed, 5 skipped**.
- **Mặc định `tat`.** A2 lên mà không ai bật thì hành vi giữ nguyên hệt A1.
  Bật một tính năng phân quyền mà đổi ngay quyền của mọi người đang làm
  việc là cách tạo sự cố: sáng hôm sau nhân viên mở dashboard thấy trống.

---

### Việc 1: Migration chủ sở hữu khách

**Tệp:** `agent/migrations/versions/0020_chu_so_huu_khach.sql`,
`agent/schema.sql`, `tests/test_migration_chu_so_huu.py`

- [ ] **Bước 1: test đỏ** — cột `owner_user_id` tồn tại, `ON DELETE SET NULL`,
  bảng `contact_owner_history`, hai chỉ mục (chủ, và vô chủ theo `first_seen`).
- [ ] **Bước 2: viết migration**

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_user_id UUID
    REFERENCES nguoi_dung(id) ON DELETE SET NULL;
```

`ON DELETE SET NULL` chứ không `RESTRICT`: nhân viên nghỉ việc thì khách của
họ thành vô chủ và **hiện ngay** trên chỉ số vô chủ. `RESTRICT` thì không
xoá nổi tài khoản người đã nghỉ, và người ta sẽ đi khoá tài khoản thay vì
xoá — khách vẫn "có chủ" là một người không còn đi làm.

- [ ] **Bước 3: thêm vào `schema.sql`** cho bản clone sạch.
- [ ] **Bước 4:** test xanh, `ruff`, commit.

---

### Việc 2: `agent/core/pham_vi.py` — một chỗ duy nhất sinh mệnh đề WHERE

**Tệp:** tạo `agent/core/pham_vi.py`, `tests/test_pham_vi.py`

**Giao diện:**
- `MUC_TAM_NHIN = ("tat", "an_noi_dung", "chi_doc", "an")`
- `doc_muc() -> str` — đọc `cau_hinh_agent`, mặc định `tat`
- `dieu_kien_khach(*, nguoi, muc, so_tham_so) -> tuple[str, list]`
- `duoc_tra_loi(nguoi, khach) -> bool`, `duoc_xem_noi_dung(nguoi, khach) -> bool`

- [ ] **Bước 1: test đơn vị (LUÔN CHẠY, không cần CSDL)** — khẳng định trên
  chuỗi SQL sinh ra:

```python
def test_muc_tat_khong_them_dieu_kien_nao():
    """Mặc định `tat` phải sinh mệnh đề LUÔN ĐÚNG — không lọc gì.

    Đây là ràng buộc "A2 lên mà không ai bật thì không đổi gì". Sai ở đây
    là mọi nhân viên mất sạch khách ngay khi triển khai, và triệu chứng là
    "dashboard trống", không phải một lỗi."""
    sql, ts = pham_vi.dieu_kien_khach(nguoi=NV, muc="tat", so_tham_so=0)
    assert sql.strip() == "TRUE"
    assert ts == []


def test_muc_an_loc_theo_chu_so_huu_va_van_cho_khach_vo_chu():
    """Khách chưa giao là của chung — chủ dự án đã chọn.

    Bỏ vế `owner_user_id IS NULL` là khách mới nhắn tới thành VÔ HÌNH với
    tất cả mọi người: không lỗi, không nhật ký, khách ngồi chờ."""
    sql, ts = pham_vi.dieu_kien_khach(nguoi=NV, muc="an", so_tham_so=2)
    assert "owner_user_id IS NULL" in sql
    assert "$3" in sql            # tiếp đúng số tham số đã dùng
    assert ts == [NV_ID]


def test_nguoi_co_khach_xem_tat_ca_thi_moi_muc_deu_khong_loc():
    for muc in pham_vi.MUC_TAM_NHIN:
        sql, _ = pham_vi.dieu_kien_khach(nguoi=SEP, muc=muc, so_tham_so=0)
        assert sql.strip() == "TRUE", muc


def test_muc_la_thi_nem():
    """Mức lạ trả `TRUE` là mở toang danh bạ vì một lỗi gõ trong cấu hình."""
    with pytest.raises(ValueError):
        pham_vi.dieu_kien_khach(nguoi=NV, muc="khong_co_that", so_tham_so=0)
```

- [ ] **Bước 2: viết `pham_vi.py`.** `chi_doc` và `an_noi_dung` KHÔNG lọc
  danh sách (vẫn thấy khách) — chúng chỉ đổi hai cờ. Chỉ `an` mới lọc.
- [ ] **Bước 3: test tích hợp trên Postgres thật** — dựng 3 người, 5 khách,
  chạy đủ bốn mức, khẳng định cả tập trả về LẪN hai cờ.
- [ ] **Bước 4:** `ruff`, commit.

---

### Việc 3: Nối lớp phạm vi vào truy vấn khách

**Tệp:** `agent/api/contacts.py`, `tests/test_contacts_api.py`

- [ ] **Bước 1: test canh** — `FROM contacts` chỉ xuất hiện trong
  `PostgresContactRepository`. Quét mã `agent/`.
- [ ] **Bước 2:** `list_visible` và `get_visible` nhận thêm `muc` và gọi
  `dieu_kien_khach()`; trả thêm `owner_user_id`, `owner_ten`, `duoc_tra_loi`.
- [ ] **Bước 3:** mọi mức chạy thật trên Postgres.
- [ ] **Bước 4:** `ruff`, commit.

---

### Việc 4: API giao khách

**Tệp:** `agent/api/contacts.py`, `tests/test_giao_khach.py`

| Phương thức | Đường dẫn | Quyền |
|---|---|---|
| PUT | `/api/contacts/{id}/chu-so-huu` | `khach.giao` |
| DELETE | `/api/contacts/{id}/chu-so-huu` | `khach.giao` |
| GET | `/api/contacts/{id}/chu-so-huu/lich-su` | `khach.doc` |
| GET | `/api/khach-vo-chu` | `khach.doc` |

- [ ] **Bước 1: test đỏ**, gồm ba ràng buộc:

```python
def test_giao_cho_nguoi_khong_tra_loi_duoc_thi_422():
    """Giao khách cho người không có `hoi_thoai.tra_loi` là khách chết câm:
    có chủ nên người khác không đụng vào, mà chủ thì không trả lời được."""


def test_giao_khach_ghi_du_ba_thu_trong_mot_giao_dich():
    """Cột chủ, dòng lịch sử, và `db.log_event` — một giao dịch.

    Ghi cột mà mất lịch sử thì sáu tháng sau không ai trả lời được "ai giao
    khách này cho Thảo, và lúc nào"."""


def test_xoa_nhan_vien_thi_khach_thanh_vo_chu_va_vao_chi_so():
    """`ON DELETE SET NULL` + chỉ số phải khớp nhau. Chạy thật trên Postgres:
    đây là loại ràng buộc chỉ CSDL mới nói được đúng sai."""
```

- [ ] **Bước 2–4:** viết, xanh, `ruff`, commit.

---

### Việc 5: Chỉ số khách vô chủ

**Tệp:** `agent/api/routes.py` (`overview`), `dashboard/`, `tests/`

Chủ dự án chọn "mọi người thấy, không tự gán chủ". Hệ quả đã biết trước:
phần lớn khách sẽ ở mãi trạng thái vô chủ. Chặn bằng **mã**, không bằng lời
nhắc.

- [ ] `overview` trả thêm `khach_vo_chu: {so, ngay_lau_nhat}`.
- [ ] Dashboard: một ô trên trang Ca trực — `N khách chưa có chủ · lâu nhất
      đã M ngày`, bấm vào mở màn Khách đã lọc sẵn.
- [ ] Test: có khách vô chủ thì `so > 0` và `ngay_lau_nhat` đúng.
- [ ] Test: **chỉ số phải dùng CÙNG định nghĩa "vô chủ" với bộ lọc.** Hai
      định nghĩa lệch nhau là con số nói một đằng, danh sách hiện một nẻo,
      và người ta thôi tin cả hai.
- [ ] `ruff`, commit.

---

### Việc 6: Dashboard — giao khách và chọn mức tầm nhìn

**Tệp:** `dashboard/index.html`, `app.js`, `app.css`

- [ ] Màn **Khách hàng**: cột "Phụ trách", nút Giao, bộ lọc
      `Khách của tôi / Chưa có chủ / Tất cả`.
- [ ] Màn **Cấu hình**: chọn một trong bốn mức, **nói rõ hệ quả từng mức**
      ngay cạnh ô chọn. Một ô chọn bốn giá trị mà không giải thích thì người
      ta chọn bừa rồi không hiểu vì sao nhân viên kêu mất khách.
- [ ] Nút gửi bị khoá khi `duoc_tra_loi` là false, kèm lý do hiện ra — khoá
      im lặng thì người trực tưởng giao diện hỏng.
- [ ] Nhìn thật trên trình duyệt, đủ bốn mức.
- [ ] `ruff`, chốt canh giao diện, commit.

---

### Việc 7: Dọn và tài liệu

- [ ] `QUYEN_HOAN_SANG_A2` trong `tests/test_quyen_danh_muc.py` phải **rỗng**.
- [ ] `docs/van-hanh.md`: mục giao khách và bốn mức tầm nhìn.
- [ ] `python -m scripts.sinh_so_do --ghi`.
- [ ] Toàn bộ test xanh, `ruff` sạch, commit.
