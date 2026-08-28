# Cổng kết nối kho / ERP

Ngày: 2026-08-28 · Trạng thái: đã duyệt thiết kế, chờ thi công

---

## 1. Vấn đề

Agent tư vấn và lên đơn dựa trên `data/catalog.json` — một file JSON nằm trên
đĩa. Nghĩa là giá và tồn kho agent nói với khách là **con số của ngày ai đó
sửa file lần cuối**. Bán món đã hết, báo giá đã đổi — và không có gì báo động.

Đơn chốt xong chỉ nằm trong Postgres nội bộ, không đi vào phần mềm quản lý
kho. Nhân viên kho phải nhập tay, và tồn kho hai nơi lệch nhau ngay từ đơn
đầu tiên.

## 2. Mục tiêu

1. Agent đọc **giá và tồn kho thật** từ ERP/kho, và khi không đọc được thì
   **nói là không biết** chứ không đọc số cũ.
2. Đơn agent chốt đi thẳng vào ERP, giữ chỗ hàng đúng cách của ERP.
3. Cắm được Odoo, ERPNext, hoặc hệ khác mà **không đụng vào agent, RAG, hay
   bảy chốt trong `_tao_don_hang`**.
4. Máy vừa clone về vẫn chạy được, không cần ERP.

## 3. Không làm (cố ý)

Đồng bộ công nợ · kế toán · đa tiền tệ · pricelist theo nhóm khách nâng cao ·
viết lại routing/SLA/inbox đang chạy tốt · dựng agent runtime thứ hai trên
`deepseek-harness`.

Lý do loại `deepseek-harness` làm nền: nó là agent harness TypeScript ở
developer preview, và một agent chạy trong nó sẽ đi vòng qua cả năm lớp lưới
tuân thủ trong `agent/core/agent.py`. Nó chỉ xuất hiện ở đây dưới dạng một
plugin **khách hàng** gọi vào MCP của hệ thống (mục 9.3).

---

## 4. Kiến trúc

```
agent/erp/
  hop_dong.py    Protocol NguonERP + dataclass SanPham / Gia / TonKho / KetQuaDon
  tep.py         adapter đọc catalog.json      <- MẶC ĐỊNH
  erpnext.py     REST /api/resource/{Item,Bin,Item Price,Sales Order}
  odoo.py        XML-RPC execute_kw
  mcp_client.py  cho ERP đã ship sẵn MCP server
  anh_xa.py      ánh xạ mã nội bộ <-> mã ERP + phép kiểm khởi động
  cong.py        chọn adapter, cache, ngắt mạch, hợp nhất nửa tư vấn
  day_don.py     xử lý job `erp.tao_don` của outbox có sẵn
```

Chọn adapter bằng `.env`: `ERP_LOAI=tep|erpnext|odoo|mcp`, **mặc định `tep`**.
Không mặc định về tệp thì máy vừa clone chết ngay dòng đầu — đúng cái bẫy mà
`catalog.example.json` sinh ra để tránh.

`agent/core/tools.py::_catalog()` **giữ nguyên chữ ký `-> dict`**. Đây là
điều kiện để 440 test hiện có vẫn là lưới an toàn thật.

### 4.1 Hàng đợi đồng bộ đơn — SỬA so với bản đầu

**Bản đầu của mục này SAI.** Nó viết: "dùng chính `agent/omnichannel/outbox.py`,
thêm loại job `erp.tao_don`" — kết luận rút ra từ tên file và docstring, chưa
đọc schema.

Đọc kỹ thì outbox đó gắn chặt `account_id`, `conversation_id`, `message_id`,
và ánh xạ trạng thái job sang `messages.delivery_status`. Nó là outbox **gửi
tin nhắn**, không phải hàng đợi việc tổng quát. Nhét việc ERP vào là bẻ nó,
và làm một đơn "tồn tại" ở hai nơi.

**Thiết kế đúng, đơn giản hơn: chính bảng `orders` là hàng đợi.** Đơn
`trang_thai='cho_dong_bo'` là việc chưa xong. Migration `0008` thêm
`erp_ma_don`, `erp_dong_bo_luc`, `erp_so_lan_thu`, `erp_loi`. Một nguồn sự
thật cho đơn, không hai.

---

## 5. Hợp đồng dữ liệu: hai nửa

ERP biết bán cái gì với giá bao nhiêu. Nó **không** biết serum này hợp da dầu
hay da khô. Đối chiếu 14 trường của bản ghi sản phẩm hiện tại với những gì
Odoo/ERPNext cho sẵn: **9 trường không tồn tại trong ERP** — và 9 trường đó
chính là toàn bộ chất tư vấn.

```
SanPham = NỬA THƯƠNG MẠI (ERP là sự thật)   +  NỬA TƯ VẤN (kho nội bộ là sự thật)
          ma, ten, loai, gia, ton_kho,          da_phu_hop, van_de_ho_tro,
          dung_tich, ban_duoc                   thanh_phan_chinh, khong_chua,
                                                do_pH, cach_dung, thoi_diem,
                                                so_cong_bo, hsd_thang
```

Nối bằng `ma`. Nửa tư vấn **ở lại `catalog.json` / `data/knowledge/`**, không
nhét vào ERP: ERP kế toán không phải chỗ chứa văn bản tư vấn, và đổi ERP thì
không mất gì.

`so_cong_bo` là số công bố mỹ phẩm — ràng buộc pháp lý khi nói về sản phẩm.
Mất nó là mất căn cứ.

### Phép kiểm chống hỏng im lặng

Mã có ở ERP mà **không có nửa tư vấn** → `log_event("erp.thieu_ho_so")`, và
agent **không được chủ động giới thiệu** món đó. Không có phép kiểm này thì
ERP thêm 50 SKU, agent tư vấn chúng bằng tưởng tượng, không ai biết.

---

## 6. Luồng đọc

### 6.1 Cache chia theo tần suất đổi, không theo nguồn

| Tầng | TTL | Hết hạn mà gọi ERP hỏng |
|---|---|---|
| Tham chiếu (tên, mô tả, ảnh) | 24h | Dùng bản cũ — tên sản phẩm không đổi |
| Giá | `ERP_TTL_GIA` (mặc định 900s) | **Trả `None`** |
| Tồn kho | `ERP_TTL_TON` (mặc định 60s) | **Trả `None`** |

### 6.2 Quy tắc trung tâm

> Giá hoặc tồn kho quá hạn mà gọi ERP không được → cổng trả `None`.
> **Không bao giờ trả số cũ.** `run_tool` thấy `None` thì trả
> `{"khong_biet": True, ...}`, lưới an toàn đẩy sang chuyển-người.

Ràng buộc này nằm trong mã, không nằm trong prompt. Báo sai giá cho khách rồi
mới phát hiện đắt hơn nhiều so với im lặng một phút.

### 6.3 Chốt đơn phải đọc tồn SỐNG

`_tao_don_hang` gọi `cong.ton_kho(ma, bo_qua_cache=True)`. Đọc cache 60 giây ở
đúng khoảnh khắc chốt là để khách xác nhận xong mới báo hết hàng.

### 6.4 Ngắt mạch

`ERP_NGAT_MACH_SO_LAN` lần hỏng liên tiếp → mở mạch `ERP_NGAT_MACH_GIAY`, ghi
`log_event("erp.ngat_mach")`. **Hai số này là tham số cấu hình, không phải
hằng số chọn cho tròn** — giá trị mặc định (5 lần / 30 giây) là chỗ bắt đầu,
phải đo lại bằng độ trễ thật của ERP ở bước thi công.

Không có ngắt mạch thì ERP chậm kéo cả hội thoại chậm — ở contact center nghĩa
là hàng chục khách chờ cùng lúc.

### 6.5 Chỉ đọc hàng được phép bán

Adapter **luôn** lọc: Odoo `sale_ok = True`; ERPNext `is_sales_item = 1` và
`disabled = 0`. ERP chứa cả hàng ngừng kinh doanh, hàng mẫu, vật tư nội bộ —
không lọc thì agent nhiệt tình tư vấn lọ sample không bán.

### 6.6 Kho nào

`ERP_MA_KHO` **bắt buộc** khi `ERP_LOAI != tep`. `Bin` của ERPNext là theo
từng kho, `stock.quant` của Odoo theo từng vị trí — hỏi "còn bao nhiêu" mà
không nói kho nào là câu hỏi không có đáp án. `scripts/san_sang.py` kiểm.

### 6.7 Giá không phải một con số

Cả Odoo lẫn ERPNext đều có pricelist: giá phụ thuộc nhóm khách, số lượng,
ngày, khuyến mãi. `list_price` **không** phải giá khách thực trả.

Hợp đồng trả về `Gia(gia_ban, don_vi, nguon, hieu_luc_den)` chứ không phải
`int`. Adapter chịu trách nhiệm hỏi đúng bảng giá theo `ERP_PRICELIST`. Nếu
ERP trả nhiều mức giá áp dụng được, adapter lấy mức ERP tự chọn cho đơn bán
lẻ — **không tự tính lại**, vì tính lại là dựng bộ máy giá thứ hai.

### 6.8 Ánh xạ mã sản phẩm

Không giả định `ma` nội bộ trùng `item_code` bên ERP. `data/anh_xa_ma.json`
(tuỳ chọn) ánh xạ tường minh; không có thì coi là đồng nhất.

Khởi động chạy `anh_xa.kiem()`: báo bao nhiêu mã khớp. Khớp dưới 90% →
`log_event("erp.anh_xa_lech")` + cảnh báo lên dashboard. Không có phép kiểm
này thì việc hợp nhất hai nửa dữ liệu **im lặng trả rỗng**.

---

## 7. Luồng ghi: lên đơn và trừ kho

### 7.1 ERP không cho "trừ số lượng"

Tồn kho trong Odoo và ERPNext là **hệ quả của chứng từ**, không phải một ô số
để ghi đè:

| | Tạo đơn bán | Tồn thực giảm khi |
|---|---|---|
| ERPNext | `Sales Order` submit → `Bin.reserved_qty` **tăng** | `Delivery Note` submit |
| Odoo | `sale.order` confirm → `stock.quant.reserved_quantity` **tăng** | validate `stock.picking` |

Nên "tự động trừ kho" thực chất là: **agent tạo đơn → ERP giữ chỗ; kho xuất
hàng → ERP mới trừ.** Ép trừ ngay lúc chốt đơn là ghi đè sổ kế toán bằng tay,
và sổ đó sai vĩnh viễn. **Không làm.**

Hệ quả: con số agent báo khách phải là **hàng bán được** = `on_hand −
reserved` (Odoo `free_qty`; ERPNext `actual_qty − reserved_qty`). Lấy
`qty_available` / `actual_qty` là hứa bán món đã có người đặt.

### 7.2 Một sổ cái, không hai

`agent/core/kho.py` hiện là **sổ cái** tồn kho trong Postgres. Cắm ERP vào mà
giữ nguyên là hai sổ, và chúng sẽ lệch.

**Đổi vai:** ERP là sổ cái duy nhất. Bảng `ton_kho` nội bộ thành **chỗ giữ
tạm có hạn** — chỉ giữ chỗ trong khoảng thời gian ERP chưa biết về đơn, rồi tự
tan. `ERP_GIU_CHO_GIAY` là tham số cấu hình, đo lại sau khi biết độ trễ thật.

### 7.3 Khách hàng phải có trước đơn

Sales Order bắt buộc có `Customer` (ERPNext) / `res.partner` (Odoo). Tạo mới
mỗi đơn → một người thành mười bản ghi, báo cáo bán hàng vô nghĩa.

`day_don.bao_dam_khach()`: chuẩn hoá số điện thoại → tra `erp_partner_id` đã
lưu trong bảng identity → không có thì tra ERP theo sđt → vẫn không có thì tạo
mới → **lưu `erp_partner_id` lại**. Idempotent theo sđt chuẩn hoá.

Nối vào `agent/omnichannel/identity.py` đã có, không dựng cơ chế nhận dạng
khách thứ hai.

### 7.4 Luồng chốt đơn

```
Chốt 1-6  GIỮ NGUYÊN (khách xác nhận · đủ thông tin · giá từ danh mục ·
          tồn >= số lượng · ngưỡng duyệt · chống trùng)
   |
Chốt 7'   giữ chỗ TẠM trong Postgres, nguyên tử, có hạn ERP_GIU_CHO_GIAY
   |
Chốt 8    đẩy Sales Order sang ERP, chờ tối đa ERP_CHO_DONG_BO_GIAY
   |
   +-- ERP nhận       -> trang_thai="da_chot", lưu erp_ma_don,
   |                     XOÁ giữ chỗ tạm (từ đây ERP giữ chỗ, hết hai sổ)
   +-- ERP từ chối    -> trả hàng, huỷ đơn, agent báo khách + chuyển người
   +-- ERP im lặng    -> trang_thai="cho_dong_bo", vào outbox retry
                         agent nói "đã ghi nhận, sẽ có người xác nhận"
                         KHÔNG nói "đã chốt xong"
```

Nhánh thứ ba dùng lại đúng khuôn `cho_duyet` đã có: **khi hệ thống chưa chắc,
nó nói với khách rằng nó chưa chắc.** Nói "đã chốt" rồi ERP từ chối là bán món
không có.

### 7.5 Chống đơn trùng

ERP có thể đã nhận nhưng mạng đứt trước khi ta thấy phản hồi; retry sẽ tạo đơn
thứ hai. Mỗi đơn mang khoá idempotency = `ma_don` nội bộ, ghi vào trường tham
chiếu của ERP (`po_no` ở ERPNext, `client_order_ref` ở Odoo).

**Trước khi tạo, outbox tra xem khoá đó đã tồn tại chưa.** Thiếu bước tra này
thì mỗi lần ERP chậm là khách bị lên hai đơn.

### 7.6 Trạng thái giao hàng đi ngược về

ERPNext có webhook sẵn cho Delivery Note; Odoo phải poll `stock.picking`. Ánh
xạ về đúng `models.InternalShippingStatus` — bộ trạng thái nội bộ **duy nhất**
mà `tools.py` đã cố ý dựng. Không đẻ bộ tên thứ hai.

### 7.7 Đối soát định kỳ

Mỗi 15 phút so tồn kho nội bộ với ERP. Lệch → `log_event("erp.lech_ton_kho")`
+ cảnh báo dashboard. Đơn `cho_dong_bo` quá 30 phút → cảnh báo.

Không có bộ đối soát thì lệch chỉ lộ ra khi khách phàn nàn.

---

## 8. Dữ liệu cá nhân

Tên, số điện thoại, địa chỉ khách sẽ nằm trong ERP **vĩnh viễn** sau đơn đầu
tiên. `agent/core/du_lieu_ca_nhan.py` và `agent/api/retention.py` phải coi ERP
là một **đích** nữa:

- Yêu cầu xoá dữ liệu → xoá cả ở ERP, hoặc ẩn danh hoá `res.partner` /
  `Customer` nếu ERP không cho xoá bản ghi có chứng từ (thường là vậy).
- `erp_partner_id` lưu lại chính là thứ làm việc xoá đó khả thi.
- Ghi rõ trong `docs/du-lieu-ca-nhan.md` rằng ERP là nơi lưu thứ ba.

---

## 9. Ba vỏ đi ra

### 9.1 REST — `agent/api/erp.py`
`GET /erp/san-pham` · `/erp/san-pham/{ma}` · `/erp/ton-kho/{ma}` ·
`/erp/suc-khoe`. **Chỉ đọc.** Dùng cơ chế xác thực đã có trong
`agent/core/xac_thuc.py`.

### 9.2 MCP — mở rộng `agent/mcp_server.py`
Thêm `ton_kho_realtime`, `suc_khoe_erp`. **Giữ nguyên ranh giới đọc/ghi đã
viết trong docstring của file đó: MCP không có công cụ tạo đơn.** Client MCP
là model khác, không đi qua năm lớp lưới, không có trần chi phí.

### 9.3 Plugin dsh — `plugins/dsh-erp/`
TypeScript, gọi vào MCP HTTP ở trên. Làm sau cùng. **Để ngoài
`requirements.txt`** — dsh đang developer preview, không cho nó thành phụ
thuộc bắt buộc của hệ thống chạy thật.

---

## 10. Kiểm thử — không gọi ERP thật

`FakeERP` hiện thực `NguonERP`, mô phỏng đủ kiểu hỏng: chậm · 500 · trả rỗng ·
giá âm · **timeout giữa chừng sau khi ERP đã nhận đơn**.

Mỗi ràng buộc một test:

- quá hạn mà hỏng → trả `khong_biet`, **không** trả số cũ
- ngắt mạch mở sau N lần hỏng liên tiếp
- giữ chỗ tạm hết hạn thì tự trả hàng
- retry **không** sinh đơn trùng
- thiếu nửa tư vấn thì agent không chủ động giới thiệu
- đơn `cho_dong_bo` **không** được nói "đã chốt"
- chốt đơn đọc tồn sống, không đọc cache
- adapter không trả hàng `sale_ok=False`
- ánh xạ mã lệch → có cảnh báo

**Test hợp đồng chạy chung cho cả bốn adapter** — cùng một bộ khẳng định, để
Odoo và ERPNext không âm thầm trả khác nhau.

`scripts/san_sang.py` kiểm cấu hình ERP. CI job `clone-sach` phải vẫn xanh với
`ERP_LOAI=tep`.

---

## 11. Quan sát được

Mọi lần rơi về đường lui, ngắt mạch, lệch tồn kho, đơn kẹt outbox, ánh xạ mã
lệch, thiếu hồ sơ tư vấn đều là `log_event` **có tên riêng**, hiện trên
dashboard.

Nguyên tắc của repo: *hỏng thì phải có người biết.* Xanh giả nguy hiểm hơn đỏ
giả.

---

## 12. Giả định phải xác minh khi có instance thật

Chưa có ERP thật để gọi, nên những điều sau là **giả định có chủ đích**, không
phải sự thật đã kiểm:

1. Tên trường và hành vi chứng từ khác nhau giữa Odoo 16/17/18 và giữa các bản
   ERPNext.
2. Độ trễ thật của một lời gọi — quyết định `ERP_TTL_TON`,
   `ERP_CHO_DONG_BO_GIAY`, `ERP_NGAT_MACH_*`.
3. Mã sản phẩm nội bộ có khớp `item_code` bên ERP không.
4. Bảng giá nào là bảng giá bán lẻ thật.

Bốn điều này giải quyết bằng một spike rẻ ngay khi có instance. Cho tới lúc
đó, thi công theo thứ tự ở mục 13 — giai đoạn 1 không cần instance nào.

---

## 13. Thứ tự thi công

| GĐ | Nội dung | Cần ERP thật? |
|---|---|---|
| 1 | `hop_dong.py`, `tep.py`, `cong.py`, `anh_xa.py`, `FakeERP`, toàn bộ test | Không |
| 2 | `erpnext.py` (REST, dễ dựng fixture) | Để xác minh |
| 3 | `odoo.py` (XML-RPC) | Để xác minh |
| 4 | `day_don.py` + job `erp.tao_don` + khách hàng + idempotency | Có |
| 5 | Đối soát, trạng thái giao ngược về, dữ liệu cá nhân | Có |
| 6 | Ba vỏ ra: REST, MCP, plugin dsh | Không |

Giai đoạn 1 làm được ngay và **kiểm chứng được đầy đủ** bằng `FakeERP`.
