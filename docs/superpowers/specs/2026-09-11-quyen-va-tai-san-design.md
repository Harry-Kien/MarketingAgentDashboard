# Quyền và tài sản — thiết kế

Khối A trong chương trình sáu yêu cầu (đa kênh tự phục vụ, multi-agent,
agent tuỳ chọn, trường khách tuỳ biến, phân quyền theo tài sản, task).

Khối này đứng đầu vì nó là thứ duy nhất **không vá vào sau được**: điều
kiện "nhân viên chỉ thấy khách của mình" nằm trong câu truy vấn. Xây các
khối khác trước rồi mới siết quyền nghĩa là mổ lại mọi endpoint đã viết,
và chỗ nào sót thì lặng lẽ trả dữ liệu khách của người khác.

---

## 1. Bài toán

Hệ thống hiện có **ba trục quyền rời nhau**, không trục nào cấu hình được:

| Trục | Ở đâu | Phạm vi | Ai dùng |
|---|---|---|---|
| Vai trò toàn cục nhị phân | `nguoi_dung.vai_tro` ∈ (`quan_tri`, `nhan_vien`) | toàn hệ thống | ~70 chỗ `Depends(bat_buoc_quan_tri)` trên 12 file, cộng 5 chỗ so `== "quan_tri"` |
| Thành viên tài khoản kênh | `account_memberships.role` ∈ (`owner`, `manager`, `agent`, `viewer`) | một tài khoản kênh | 6 file, lọc trong SQL |
| Người phụ trách hội thoại | `conversation_assignments` | một hội thoại | routing, inbox |

Nền dưới ba trục ấy là một chốt đăng nhập **hỏng-đóng** ở
`agent/main.py:688`: middleware chặn mọi `/api/*` và `/tich-hop/*` trừ danh
sách `_MO` khai tường minh. Chú thích tại chỗ nêu rõ lý do không gắn
`Depends` vào từng endpoint — *"gắn từng endpoint là cơ chế HỎNG-MỞ: hơn bốn
mươi endpoint, quên một cái là cái đó phơi ra, và không có gì báo"*.

Lớp quyền mới **phải theo đúng lý lẽ đó**, không được đi ngược. Xem mục 2.8.

Đo trên mã: **164 route** dưới các router `/api`.

| Nhóm | Số route | Nghĩa |
|---|---|---|
| Miễn trừ thật — webhook (chữ ký), webchat (khách dùng), đăng nhập/đăng xuất/`toi`, xác minh tên miền, health | ~19 | Không cần quyền |
| Đang canh `bat_buoc_quan_tri` | ~70 | Đổi máy móc sang quyền tương ứng |
| **Chỉ canh đăng nhập** — `Depends(bat_buoc_dang_nhap)` hoặc rơi vào middleware | **~75** | Nhân viên nào cũng làm được: duyệt đơn, huỷ đơn, nhập kho, kiểm kê, duyệt bài đăng công khai, sửa kho tri thức, tra cứu dữ liệu cá nhân theo số điện thoại, xem chi phí. **Đây mới là phần việc thật của A1.** |

Nhóm thứ ba là lý do khối này đáng làm. Không có lỗ hổng nào với người
ngoài — chốt đăng nhập kín. Nhưng bên trong thì mọi nhân viên ngang quyền
nhau ở những việc lẽ ra không ngang.

Ba hệ quả đo được từ mã:

1. **Không trả lời được câu "người này được làm gì".** Quyền của một nhân
   viên là hợp của ba nguồn, mỗi nguồn nằm một chỗ, không màn nào tổng hợp.

2. **Không có khái niệm "khách này của nhân viên này".** Đơn vị tài sản nhỏ
   nhất hiện nay là *tài khoản kênh*: là thành viên của một Fanpage thì thấy
   **toàn bộ** khách nhắn vào Fanpage đó. Yêu cầu của chủ dự án là giao theo
   **từng khách**.

3. **Bề mặt không được canh.** Chỉ 6 file dùng `account_memberships`. Những
   endpoint còn lại hoặc kiểm nhị phân `quan_tri`, hoặc không kiểm gì. Thêm
   endpoint mới mà quên canh là chuyện không ai phát hiện — không lỗi,
   không nhật ký, đúng loại hỏng im lặng mà `CLAUDE.md` liệt kê.

**Không thuộc bài toán này:** trường khách tuỳ biến (khối B), task (khối C),
agent theo phạm vi (khối D, E), nối kênh tự phục vụ (khối F).

---

## 2. Quyết định kiến trúc

### 2.1. Hợp nhất, không thêm trục thứ tư

Thêm "chủ sở hữu khách" như một hệ độc lập sẽ thành **bốn** hệ song song.
Thay vào đó: một lớp quyền duy nhất, ba trục cũ trở thành dữ liệu đầu vào.

- `account_memberships` **giữ nguyên** — đã chạy, đã có test, đã lọc đúng chỗ
  trong SQL. Nó trả lời "được vào kênh nào".
- `conversation_assignments` **giữ nguyên** — nó trả lời "ai đang cầm hội
  thoại này", là chuyện ngắn hạn, khác với sở hữu khách là chuyện dài hạn.
- `nguoi_dung.vai_tro` **thôi làm nguồn sự thật về quyền**.

### 2.2. Danh mục quyền là HẰNG TRONG MÃ; vai trò là dữ liệu

Vai trò do người tạo. Nhưng *tập quyền có thể tồn tại* thì mã quyết định.

Nếu danh mục quyền là dữ liệu tự do, người thêm endpoint mới sẽ gõ một chuỗi
quyền chưa từng tồn tại — hoặc quên gõ. Endpoint ấy thành **không ai canh**,
và không có gì phát hiện. Danh mục hằng trong mã cho phép một test quét mọi
route và bắt route nào chưa khai quyền.

Đây là đúng nguyên tắc của repo: *ràng buộc nằm trong MÃ, không nằm trong
cấu hình*. Cấu hình chỉ được **siết** (gán ít quyền hơn), không được **nới**
(tạo ra quyền mã không biết).

### 2.3. Quyền nạp theo từng request, không theo phiên

`doc_phien()` trả về người kèm `quyen: frozenset[str]`, nạp bằng JOIN ngay
trong truy vấn phiên đang có — không thêm vòng gọi CSDL.

Vì sao không cache vào phiên: thu quyền của một người lúc 9 giờ sáng mà họ
vẫn dùng được tới lúc hết phiên là đúng thứ bảng `phien` sinh ra để tránh
(xem chú thích `agent/schema.sql`, mục "Phiên nằm trong CSDL chứ không phải
JWT"). Cache quyền vào phiên là đưa lỗi ấy quay lại qua cửa sau.

### 2.4. Chủ sở hữu khách là CỘT trên `contacts`, lịch sử để bảng riêng

`conversation_assignments` dùng bảng riêng vì hội thoại đổi người liên tục
và lịch sử là dữ liệu chính. Sở hữu khách thì ngược lại: đọc ở **mọi** truy
vấn danh sách khách, đổi thì hiếm. JOIN thêm một bảng ở mọi truy vấn là chi
phí thường trực để phục vụ một cột.

`ON DELETE SET NULL` khi nhân viên bị xoá: khách thành vô chủ và **hiện ngay**
trên chỉ số khách vô chủ. Không im lặng.

### 2.5. Tầm nhìn là bốn mức, mặc định `tat`

Chủ dự án chọn: quản trị chọn mức. Ba mức đã bàn, cộng một mức thứ tư:

| Mức | Nhân viên B thấy gì về khách của A |
|---|---|
| `tat` | Không áp dụng sở hữu khách. **Mặc định.** |
| `an_noi_dung` | Thấy tên và biết A phụ trách; không đọc tin nhắn, không thấy PII |
| `chi_doc` | Thấy và đọc đủ; nút gửi bị khoá |
| `an` | Không thấy trong danh sách, không mở được, tìm không ra |

`tat` là mặc định **có chủ ý**. Bật một tính năng phân quyền mà đổi ngay
quyền của mọi người đang làm việc là cách tạo sự cố: sáng hôm sau nhân viên
mở dashboard thấy trống, không ai hiểu vì sao. Quản trị bật khi đã giao khách
xong.

Lưu ở `cau_hinh_agent` (khoá `tam_nhin_khach_nguoi_khac`) — bảng đã có, đã
bền qua khởi động lại, không cần migration.

### 2.6. Khách chưa giao là của chung

Chủ dự án chọn: mọi người thấy, không tự gán chủ.

Hệ quả đã biết trước: phần lớn khách sẽ ở mãi trạng thái vô chủ. Chặn bằng
**mã**, không bằng lời nhắc: chỉ số `khách chưa có chủ: N` thường trực trên
dashboard, kèm tuổi của khách vô chủ lâu nhất. Một con số đứng im ở 400 thì
người ta còn thấy; một hàng chờ không ai đếm thì không.

### 2.7. Một chỗ duy nhất sinh điều kiện phạm vi

Bốn mức tầm nhìn nghĩa là bốn nhánh lọc. Chép bốn bản vào bốn truy vấn là
bảo đảm có bản sai, và bản sai không nổ — nó chỉ trả thừa hoặc thiếu vài
dòng.

Một hàm `dieu_kien_khach()` sinh mệnh đề `WHERE` và tham số; mọi truy vấn
gọi nó. Có test canh: `FROM contacts` chỉ được xuất hiện trong repository.

### 2.8. Hỏng-đóng lúc KHỞI ĐỘNG, không phải lúc chạy

Middleware ở `main.py:688` hỏng-đóng vì nó chặn theo *tiền tố đường dẫn* —
không cần biết endpoint nào tồn tại. Quyền thì không làm thế được: mỗi
endpoint cần một quyền **khác nhau**, nên phải khai ở đâu đó.

Ba cách, và vì sao chọn cách thứ ba:

1. **`Depends(can_quyen(...))` từng endpoint.** Đọc dễ, ở ngay cạnh hàm.
   Nhưng hỏng-mở — đúng thứ chú thích ở `main.py` đã bác bỏ.
2. **Bảng ánh xạ tập trung `(phương thức, đường dẫn) → quyền`, middleware tra.**
   Hỏng-đóng, nhưng bảng nằm xa endpoint nên đổi đường dẫn là bảng lệch âm
   thầm, và chẳng ai đọc 145 dòng bảng.
3. **Khai bằng `Depends`, KIỂM ĐỦ lúc khởi động.** ✓

Cách 3: `can_quyen()` gắn thuộc tính `quyen_yeu_cau` lên hàm dependency nó
trả về. Sau khi `include_router` xong, `kiem_moi_route_co_quyen(app)` duyệt
`app.routes`, đọc `route.dependant.dependencies`, và **ném `RuntimeError`
liệt kê mọi route chưa khai quyền** — máy chủ không khởi động được.

Đây vẫn là hỏng-đóng, chỉ là chốt dời từ lúc chạy sang lúc khởi động: thêm
endpoint mà quên khai quyền thì **máy chủ không lên**, không phải một
endpoint phơi ra lặng lẽ. Và vì cùng hàm ấy chạy trong test, CI bắt trước khi
kịp triển khai.

Đổi lại được cái mà cách 2 không có: quyền nằm ngay cạnh endpoint, đổi đường
dẫn không làm lệch gì, và OpenAPI hiện đúng.

`MIEN_TRU` là danh sách khai tường minh từng `(phương thức, đường dẫn)`, không
phải mẫu tiền tố. Mẫu `/webhook*` là chỗ để endpoint mới lọt vào mà không ai
để ý — đúng loại lỗ mà `_MO` trong `main.py` đã cẩn thận tránh.

---

## 3. Giao làm hai đợt

**A1 — Lớp quyền.** Vai trò tự tạo, màn quản lý vai trò, khai quyền cho
**~145 route** (19 route còn lại khai miễn trừ), kiểm đủ lúc khởi động.

A1 **đổi hành vi có chủ ý ở nhóm 2**: nhân viên thôi duyệt được đơn, thôi
nhập kho, thôi duyệt bài đăng công khai, thôi sửa kho tri thức. Đó chính là
thứ chủ dự án yêu cầu, và nó phải xảy ra ở A1 chứ không để lại — mỗi ngày
chờ là một ngày cả shop ngang quyền nhau ở những việc không hoàn tác được.

A1 **không đổi** cách lọc dữ liệu khách: ai đang thấy khách nào vẫn thấy
nguyên vậy. Đó là việc của A2.

Ranh giới này kiểm chứng được: test cũ nào đụng nhóm 2 sẽ đỏ và phải sửa có
chủ ý (khai vai trò cho người dùng thử); test lọc dữ liệu thì **không được
sửa dòng nào** — sửa là dấu hiệu A1 đã lấn sang A2.

**A2 — Chủ sở hữu khách.** Giao khách, bốn mức tầm nhìn, chỉ số khách vô chủ,
giao lại khi nhân viên nghỉ.

Chia đôi vì A1 chạm 12 file và A2 chạm tầng truy vấn. Gộp một đợt thì lúc test
đỏ không biết đỏ vì đâu.

---

## 4. Thành phần

### 4.1. `agent/core/quyen.py` — danh mục quyền

```python
QUYEN: dict[str, str] = {          # mã quyền -> nhãn tiếng Việt cho dashboard
    "hoi_thoai.doc":      "Đọc hội thoại",
    "hoi_thoai.tra_loi":  "Trả lời khách",
    "hoi_thoai.nhan":     "Nhận và chuyển hội thoại",
    "khach.doc":          "Xem danh sách khách",
    "khach.sua":          "Sửa thông tin khách",
    "khach.pii":          "Xem số điện thoại, email, địa chỉ",
    "khach.giao":         "Giao khách cho nhân viên",
    "khach.gop":          "Gộp hai hồ sơ khách",
    "khach.xoa":          "Xoá vĩnh viễn dữ liệu cá nhân",
    "kenh.doc":           "Xem tài khoản kênh",
    "kenh.sua":           "Sửa, bật tắt tài khoản kênh",
    "kenh.noi":           "Nối kênh mới (OAuth, quét QR)",
    "dinh_tuyen.doc":     "Xem luật định tuyến và SLA",
    "dinh_tuyen.sua":     "Sửa luật định tuyến và SLA",
    "outbox.doc":         "Xem hàng chờ gửi",
    "outbox.sua":         "Gửi lại, huỷ tin trong hàng chờ",
    "agent.doc":          "Xem trạng thái agent",
    "agent.dieu_khien":   "Bật tắt agent, đổi chế độ và ngưỡng",
    "phong_thu.dung":     "Dùng phòng thử agent",
    "ky_nang.doc":        "Xem kỹ năng và plugin",
    "ky_nang.sua":        "Cài, gỡ, bật tắt kỹ năng và plugin",
    "mcp.doc":            "Xem máy chủ MCP",
    "mcp.sua":            "Nối, đồng bộ, gỡ máy chủ MCP",
    "tich_hop.doc":       "Xem ứng dụng đã nối",
    "tich_hop.sua":       "Nối và gỡ ứng dụng",
    "cau_hinh.doc":       "Xem cấu hình hệ thống",
    "cau_hinh.sua":       "Sửa cấu hình hệ thống",
    "catalog.duyet":      "Xác nhận bảng giá",
    "don.doc":            "Xem đơn hàng",
    "don.sua":            "Sửa và huỷ đơn hàng",
    "noi_dung.doc":       "Xem video và bài đăng",
    "noi_dung.duyet":     "Duyệt đăng nội dung công khai",
    "bao_cao.doc":        "Xem báo cáo và số đo",
    "nguoi_dung.doc":     "Xem danh sách nhân viên",
    "nguoi_dung.sua":     "Tạo, khoá nhân viên; sửa vai trò và quyền",
}

MIEN_TRU: frozenset[str]   # route không cần quyền, khai tường minh:
                           # đăng nhập, đăng xuất, đổi mật khẩu của chính
                           # mình, webhook (xác thực bằng chữ ký), health
```

`MIEN_TRU` phải khai từng route một. Một danh sách mở kiểu "mọi route bắt đầu
bằng `/webhook`" là chỗ để lọt endpoint mới vào mà không ai để ý.

### 4.2. Bảng — `0019_quyen_va_vai_tro.sql`

```sql
CREATE TABLE IF NOT EXISTS vai_tro (
    id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ten      TEXT UNIQUE NOT NULL CHECK (length(ten) BETWEEN 1 AND 80),
    mo_ta    TEXT NOT NULL DEFAULT '',
    he_thong BOOLEAN NOT NULL DEFAULT false,   -- dựng sẵn, không xoá được
    tao_luc  TIMESTAMPTZ NOT NULL DEFAULT now(),
    sua_luc  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vai_tro_quyen (
    vai_tro_id UUID NOT NULL REFERENCES vai_tro(id) ON DELETE CASCADE,
    quyen      TEXT NOT NULL,
    PRIMARY KEY (vai_tro_id, quyen)
);

CREATE TABLE IF NOT EXISTS nguoi_dung_vai_tro (
    nguoi_dung_id UUID NOT NULL REFERENCES nguoi_dung(id) ON DELETE CASCADE,
    vai_tro_id    UUID NOT NULL REFERENCES vai_tro(id)    ON DELETE CASCADE,
    gan_boi       UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    gan_luc       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (nguoi_dung_id, vai_tro_id)
);
CREATE INDEX IF NOT EXISTS idx_ndvt_vai_tro ON nguoi_dung_vai_tro (vai_tro_id);
```

`vai_tro_quyen.quyen` **không** có khoá ngoại — danh mục quyền ở trong mã,
không trong CSDL. Đổi lại, lúc nạp phải lọc bỏ quyền không còn trong `QUYEN`
(quyền bị xoá khỏi mã ở bản sau), và có test canh không còn quyền mồ côi.

**Nạp sẵn trong migration:** hai vai trò `he_thong = true`:

- `Quản trị` — toàn bộ `QUYEN`
- `Nhân viên` — `hoi_thoai.*`, `khach.doc`, `khach.sua`, `khach.pii`,
  `khach.gop`, `don.doc`, `kenh.doc`, `bao_cao.doc`, `noi_dung.doc`,
  `outbox.doc`

Tập của `Nhân viên` chọn để **bằng đúng** những gì nhân viên làm được hôm
nay, không hơn không kém. `khach.pii` có trong tập vì hôm nay nhân viên xem
được PII khi là `owner`/`manager` của tài khoản kênh — trục `account_memberships`
vẫn siết tiếp phía sau, nên để quyền này ở đây không nới thêm gì.

**Backfill:** mỗi `nguoi_dung` nhận vai trò tương ứng `vai_tro` cũ.

### 4.3. Cột `nguoi_dung.vai_tro` — giữ, nhưng thôi quyết định

Không xoá cột: `agent/omnichannel/account_service.py:45` và tầng dashboard
còn đọc, và xoá cột trong cùng một đợt với thay 70 điểm kiểm là quá nhiều thứ
động một lúc.

Nó trở thành **nhãn hiển thị**, không phải nguồn sự thật. Canh bằng test quét
mã: không chỗ nào ngoài `xac_thuc.py` được so `vai_tro == "quan_tri"` để
quyết định cho phép hay không.

### 4.4. `agent/core/xac_thuc.py` — thay `duoc_phep`

`CHI_QUAN_TRI` và nhánh `vai_tro == "quan_tri"` trong `duoc_phep()` bỏ đi.
Thay bằng:

```python
def duoc_phep(nguoi: dict | None, quyen: str) -> bool:
    if not nguoi:
        return False
    if quyen not in QUYEN:
        raise KeyError(f"Quyền không có trong danh mục: {quyen}")
    return quyen in nguoi.get("quyen", frozenset())
```

Ném khi quyền lạ, không trả `False`. Trả `False` nghĩa là gõ sai tên quyền
thì endpoint **khoá với tất cả mọi người** — một lỗi chính tả thành sự cố
vận hành mà không ai hiểu vì sao. Ném thì nó nổ lúc khởi động.

`doc_phien()` bổ sung `quyen` vào truy vấn đang có:

```sql
SELECT n.id, n.ten_dang_nhap, n.ho_ten, n.vai_tro, n.khoa,
       COALESCE(array_agg(DISTINCT vq.quyen) FILTER (WHERE vq.quyen IS NOT NULL),
                '{}') AS quyen
FROM phien p
JOIN nguoi_dung n ON n.id = p.nguoi_dung_id
LEFT JOIN nguoi_dung_vai_tro ndvt ON ndvt.nguoi_dung_id = n.id
LEFT JOIN vai_tro_quyen vq ON vq.vai_tro_id = ndvt.vai_tro_id
WHERE p.token = $1 AND p.het_han > now()
GROUP BY n.id
```

Không thêm vòng gọi CSDL nào.

### 4.5. `agent/api/routes.py` — `can_quyen()` thay `bat_buoc_quan_tri`

```python
def can_quyen(*quyen: str):
    """Dependency factory. Nhiều quyền = phải có ĐỦ, không phải một trong số."""
    for q in quyen:
        if q not in QUYEN:
            raise KeyError(f"Quyền không có trong danh mục: {q}")   # lúc import

    async def kiem(request: Request) -> dict:
        nguoi = await bat_buoc_dang_nhap(request)
        thieu = [q for q in quyen if q not in nguoi["quyen"]]
        if thieu:
            raise HTTPException(403, f"Thiếu quyền: {', '.join(thieu)}")
        return nguoi
    return kiem
```

Kiểm danh mục ở thân factory, không trong `kiem`: nó chạy lúc import module,
nên gõ sai tên quyền làm máy chủ **không khởi động được**, thay vì một 403
bí ẩn lúc 2 giờ sáng.

`bat_buoc_quan_tri` **xoá hẳn**, không giữ làm bí danh.

Giữ nó là sai về nghĩa: nó đang canh ~70 endpoint với bảy nhóm quyền khác
nhau, nên bí danh trỏ vào bất cứ quyền đơn lẻ nào cũng cấp sai hoặc chặn sai
ở phần lớn chỗ còn lại — và sai theo kiểu chạy được, không nổ.

Xoá hẳn còn là hỏng-đóng: sót một điểm gọi thì `NameError` lúc import, máy
chủ không lên. Bí danh thì điểm sót ấy chạy tiếp với quyền sai, im lặng.

Và hàm kiểm lúc khởi động, gọi ngay sau khối `include_router` trong `main.py`:

```python
def kiem_moi_route_co_quyen(app) -> None:
    """
    Ném nếu có route chưa khai quyền. Gọi lúc khởi động, KHÔNG lúc chạy.

    Hỏng-đóng: endpoint mới mà quên khai thì máy chủ không lên, thay vì
    phơi ra lặng lẽ. Cùng hàm này chạy trong test nên CI bắt trước.
    """
    thieu = []
    for route in app.routes:
        khoa = (sorted(getattr(route, "methods", []) or []), getattr(route, "path", ""))
        if not khoa[1].startswith(("/api", "/tich-hop")):
            continue
        if any((pt, khoa[1]) in MIEN_TRU for pt in khoa[0]):
            continue
        phu_thuoc = getattr(getattr(route, "dependant", None), "dependencies", ())
        if not any(getattr(x.call, "quyen_yeu_cau", None) for x in phu_thuoc):
            thieu.append(f"{','.join(khoa[0])} {khoa[1]}")
    if thieu:
        raise RuntimeError(
            "Route chưa khai quyền (thêm can_quyen(...) hoặc MIEN_TRU):\n  "
            + "\n  ".join(sorted(thieu))
        )
```

**Nhóm 1 — ~70 điểm đang canh quản trị.** Đổi máy móc:

| File | Số điểm | Quyền |
|---|---|---|
| `channel_accounts.py` | ~12 | `kenh.doc` / `kenh.sua` / `kenh.noi` |
| `goi_ky_nang.py` | 9 | `ky_nang.doc` / `ky_nang.sua` |
| `mcp_may_chu.py` | 7 | `mcp.doc` / `mcp.sua` |
| `phong_thu_agent.py` | 6 | `phong_thu.dung` |
| `routing_admin.py` | 5 | `dinh_tuyen.doc` / `dinh_tuyen.sua` |
| `retention.py` | 4 | `khach.xoa` |
| `outbox.py` | 3 | `outbox.doc` / `outbox.sua` |
| `cai_dat_api.py` | 3 | `cau_hinh.doc` / `cau_hinh.sua` |
| `oauth_meta.py` | 2 | `kenh.noi` |
| `routes.py` | ~20 | runtime → `agent.dieu_khien`; kỹ năng, plugin → `ky_nang.*`; ứng dụng → `tich_hop.*`; cấu hình → `cau_hinh.*`; xác nhận bảng giá → `catalog.duyet`; `pdpd/{sdt}/xoa` → `khach.xoa`; người dùng → `nguoi_dung.*` |

**Nhóm 2 — ~75 route mới chỉ canh đăng nhập.** Đây là phần cần quyết định,
không phải đổi máy móc. Nguyên tắc: thứ nhân viên làm hằng ngày giữ trong tập
`Nhân viên`; thứ **không hoàn tác được** hoặc **ra ngoài công ty** thì không:

| Nhóm route | Quyền | Vào tập `Nhân viên`? |
|---|---|---|
| `/conversations*`, `/overview`, `/events` | `hoi_thoai.doc` | Có |
| `POST /conversations/{id}/send` | `hoi_thoai.tra_loi` | Có |
| `POST /conversations/{id}/account` | `hoi_thoai.nhan` | Có |
| `GET /orders`, `/kho`, `/kho/bien-dong`, `/catalog/products` | `don.doc` | Có |
| `POST /orders/{id}/approve`, `/cancel` | `don.sua` | **Không** — tiền của shop |
| `POST /kho/{ma}/nhap`, `/kiem-ke` | `don.sua` | **Không** — sửa tồn kho là sửa sổ sách |
| `GET /videos*`, `/posts`, `/publish/channels`, `/posts/{id}/kit`, `/video`, `/metrics` | `noi_dung.doc` | Có |
| `POST /videos`, `/upload`, `/retry`, `/posts/draft`, `/posts` | `noi_dung.doc` | Có — soạn nháp là việc hằng ngày |
| `POST /videos/{id}/approve`, `/posts/{id}/approve`, `/approve-all`, `/cancel`, `/mark-posted`, `/campaigns` | `noi_dung.duyet` | **Không** — ra ngoài công ty, không rút lại được |
| `GET /knowledge`, `POST /knowledge/probe` | `cau_hinh.doc` | Có |
| `POST /knowledge`, `DELETE /knowledge/{id}` | `cau_hinh.sua` | **Không** — sửa kho tri thức là sửa điều agent nói với mọi khách |
| `GET /pdpd`, `/pdpd/{sdt}`, `POST /pdpd/don-theo-han` | `khach.pii` | Có — nhưng trục `account_memberships` vẫn siết tiếp |
| `GET /analytics`, `/analytics/khach`, `/cost` | `bao_cao.doc` | Có |
| `GET /zalo/accounts`, `/channels`, `POST /zalo/account` | `kenh.doc` / `kenh.sua` | `.doc` có, `.sua` không |
| `GET /he-thong`, `/suc-khoe` | — | Miễn trừ (giám sát) |
| `POST /posts/{id}/callback`, `/metrics` | — | Miễn trừ: n8n gọi vào, xác thực bằng khoá riêng |

Hai dòng cuối là quyết định cần nhìn kỹ: `/posts/{id}/callback` và
`POST /posts/{id}/metrics` do **máy** gọi (n8n sau khi đăng xong), không phải
người. Chúng đang nằm dưới chốt đăng nhập, nghĩa là n8n phải cầm cookie phiên
— kiểm lại lúc thực thi; nếu đúng vậy thì đây là bí mật dài hạn nằm sai chỗ,
và phải chuyển sang khoá riêng như `WEBHOOK_SECRET` trước khi khai miễn trừ.
### 4.6. API vai trò — `agent/api/quyen.py`, prefix `/api/vai-tro`

| Phương thức | Đường dẫn | Quyền | Việc |
|---|---|---|---|
| GET | `/api/quyen` | `nguoi_dung.doc` | Danh mục quyền kèm nhãn, nhóm theo tiền tố |
| GET | `/api/vai-tro` | `nguoi_dung.doc` | Danh sách vai trò, số người mỗi vai trò |
| POST | `/api/vai-tro` | `nguoi_dung.sua` | Tạo vai trò |
| PUT | `/api/vai-tro/{id}` | `nguoi_dung.sua` | Sửa tên, mô tả, tập quyền |
| DELETE | `/api/vai-tro/{id}` | `nguoi_dung.sua` | Xoá (chặn nếu `he_thong`) |
| PUT | `/api/nguoi-dung/{id}/vai-tro` | `nguoi_dung.sua` | Gán tập vai trò cho một người |
| GET | `/api/nguoi-dung/{id}/quyen` | `nguoi_dung.doc` | Quyền thực tế, kèm vai trò nào cấp |

Endpoint cuối là màn "giải thích quyền" — không có nó thì khi đông vai trò,
không ai trả lời được vì sao người này vào được màn kia.

### 4.7. `agent/core/pham_vi.py` — chủ sở hữu khách (A2)

Migration `0020_chu_so_huu_khach.sql`:

```sql
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS owner_user_id UUID
    REFERENCES nguoi_dung(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_owner
    ON contacts (owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_vo_chu
    ON contacts (first_seen) WHERE owner_user_id IS NULL AND status = 'active';

CREATE TABLE IF NOT EXISTS contact_owner_history (
    id            BIGSERIAL PRIMARY KEY,
    contact_id    UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    owner_user_id UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,  -- NULL = thu hồi
    actor_id      UUID REFERENCES nguoi_dung(id) ON DELETE SET NULL,
    ly_do         TEXT NOT NULL CHECK (length(ly_do) BETWEEN 3 AND 500),
    luc           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_coh_contact ON contact_owner_history (contact_id, luc DESC);
```

Hàm sinh phạm vi:

```python
def dieu_kien_khach(*, nguoi: dict, muc: str, so_tham_so: int
                    ) -> tuple[str, list[Any]]:
    """
    Mệnh đề WHERE lọc `contacts` theo phạm vi của người này, kèm tham số.

    `so_tham_so` là số tham số đã dùng trong truy vấn gọi tới — trả về
    `$n` tiếp theo đúng chỗ. Không tự đếm được vì mỗi truy vấn khác nhau.
    """
```

Trả về thêm cờ `duoc_tra_loi` và `duoc_xem_noi_dung` để tầng trên khoá nút
gửi và ẩn nội dung ở mức `chi_doc` / `an_noi_dung`.

### 4.8. Dashboard

- Màn **Nhân viên** mở rộng: cột Vai trò, nút "Quyền của người này".
- Màn **Vai trò** mới: danh sách, trình sửa với danh mục quyền nhóm theo
  tiền tố, đánh dấu vai trò hệ thống không xoá được.
- Màn **Khách**: cột "Phụ trách", nút Giao, bộ lọc "Khách của tôi / Chưa có chủ /
  Tất cả".
- **Chỉ số khách vô chủ** trên trang tổng quan: `N khách chưa có chủ · lâu nhất
  đã M ngày`.
- Thiết lập **Tầm nhìn** trong màn Cấu hình, bốn mức, nói rõ hệ quả mỗi mức.

---

## 5. Luồng

**Đăng nhập → mọi request:** `doc_phien()` trả người kèm `quyen` (một truy vấn).
`can_quyen(...)` so với danh sách. Thiếu → 403 nói rõ thiếu quyền nào.

**Quản trị thu quyền của một người:** xoá dòng `nguoi_dung_vai_tro` → request
kế tiếp của người đó đã mất quyền. Không chờ hết phiên.

**Giao khách:** `khach.giao` → ghi `contacts.owner_user_id` + một dòng
`contact_owner_history` + `db.log_event`. Ba thứ trong một giao dịch.

**Nhân viên nghỉ việc:** xoá `nguoi_dung` → `ON DELETE SET NULL` → khách thành
vô chủ → chỉ số khách vô chủ tăng ngay trên dashboard.

---

## 6. Xử lý lỗi

| Tình huống | Cách xử |
|---|---|
| Quyền lạ trong mã | `KeyError` lúc **import** — máy chủ không khởi động. Không phải 403 lúc chạy. |
| Quyền mồ côi trong CSDL (quyền bị xoá khỏi mã) | Lọc bỏ lúc nạp; test canh không còn dòng mồ côi |
| Xoá vai trò hệ thống | 409, chặn ở cả API lẫn `CHECK` lúc xoá |
| Thu mất người cuối cùng có `nguoi_dung.sua` | **409, chặn.** Đây là khoá cứng ngoài hệ thống: không còn ai vào được màn nhân viên để sửa lại. Kiểm trong cùng giao dịch với lệnh ghi, không kiểm trước rồi ghi sau. |
| Xoá vai trò đang gán cho người | `ON DELETE CASCADE` — người mất quyền đó. Cảnh báo số người bị ảnh hưởng trước khi xoá. |
| Giao khách cho người không có `hoi_thoai.tra_loi` | 422 — giao cho người không trả lời được là khách chết câm |
| Người dùng có 0 vai trò | Vào được, thấy màn trống kèm dòng "Chưa được cấp quyền nào — liên hệ quản trị". Không phải 403 trắng trang. |

---

## 7. Kiểm thử

Không gọi API thật, không gọi model. CSDL thật cho các test lọc (đã có
hạ tầng trong `tests/`).

**Canh ràng buộc — những test này là lý do khối A tồn tại:**

1. **Mọi route dưới `/api` và `/tich-hop` phải khai một quyền.** Gọi thẳng
   `kiem_moi_route_co_quyen(app)` — cùng hàm máy chủ chạy lúc khởi động, nên
   test và thực tế không thể lệch nhau. Đây là test bắt endpoint không được
   canh, loại lỗi im lặng nguy hiểm nhất ở đây.
2. **`MIEN_TRU` không chứa đường dẫn đã biến mất.** Miễn trừ trỏ vào route
   không còn tồn tại là rác vô hại hôm nay, nhưng ngày mai có người thêm lại
   đúng đường dẫn ấy và nó **ra đời không được canh**, im lặng.
3. **Không chỗ nào ngoài `xac_thuc.py` quyết định quyền bằng `vai_tro`.**
   Quét mã tìm `"quan_tri"`.
4. **Mọi quyền trong danh mục có ít nhất một chỗ dùng.** Bắt quyền chết —
   quyền chết làm màn quản lý vai trò hiện thứ không có tác dụng, và người
   tick vào tưởng mình đã cấp gì đó. Bốn quyền của A2 (`khach.giao`,
   `khach.xoa`, `hoi_thoai.nhan`, `hoi_thoai.tra_loi`) nằm trong danh sách
   hoãn tường minh trong A1, và danh sách ấy phải **rỗng** khi A2 xong —
   có test canh chính danh sách đó.
5. **`FROM contacts` chỉ xuất hiện trong repository.** Bắt truy vấn đi tắt
   qua lớp phạm vi.
6. Không xoá được vai trò hệ thống.
7. Không thu được quyền `nguoi_dung.sua` cuối cùng (thử đủ ba đường: xoá vai
   trò, bỏ quyền khỏi vai trò, gỡ vai trò khỏi người).
8. Bốn mức tầm nhìn, mỗi mức một test lọc thật: dựng 3 người, 5 khách, kiểm
   đúng tập trả về **và** đúng cờ `duoc_tra_loi`.
9. Thu quyền có hiệu lực ở request kế tiếp, không chờ hết phiên.
10. Nhân viên bị xoá → khách vô chủ → có trong chỉ số.
11. **A1 không lấn sang A2:** test lọc dữ liệu khách xanh mà không sửa dòng
    nào. Test đụng nhóm 2 thì đỏ có chủ ý — sửa bằng cách cấp vai trò cho
    người dùng thử, không bằng cách nới quyền.

---

## 8. Ngoài phạm vi

- Trường khách tuỳ biến (khối B) — dùng lại `khach.sua` và lớp phạm vi này.
- Task (khối C) — sẽ có `task.*` trong danh mục quyền, và chủ sở hữu task
  dùng lại đúng mẫu `owner_user_id` này.
- Quyền theo đội (`teams`) — `team_members` đã có; gán vai trò theo đội là
  bản sau, không cần cho yêu cầu hiện tại.
- Quyền theo trường dữ liệu (ai xem được cột nào) — chỉ có `khach.pii` tách
  riêng, vì đó là ranh giới pháp lý (Nghị định 13/2023/NĐ-CP). Phần còn lại
  không tách.
- Nhật ký kiểm toán riêng cho quyền — dùng `db.log_event` đang có.
