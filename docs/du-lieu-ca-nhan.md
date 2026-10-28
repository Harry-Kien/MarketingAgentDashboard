# Bảo vệ dữ liệu cá nhân — Luật 91/2025/QH15, Nghị định 356/2025/NĐ-CP

## Vì sao phần này tồn tại

Hệ thống lưu họ tên, số điện thoại, địa chỉ giao hàng và toàn bộ nội dung
hội thoại của khách hàng thật. **Luật Bảo vệ dữ liệu cá nhân số
91/2025/QH15** có hiệu lực từ 01/01/2026, thay Nghị định 13/2023/NĐ-CP;
**Nghị định 356/2025/NĐ-CP** hướng dẫn thi hành (danh mục dữ liệu nhạy cảm,
thời hạn, mẫu hồ sơ).

| Căn cứ | Nghĩa vụ | Đáp ứng bằng |
|---|---|---|
| Luật Điều 4 khoản 1 | Khách được xem hệ thống giữ gì | `GET /api/pdpd/{sdt}` |
| Luật Điều 4 khoản 1, Điều 14 | Khách yêu cầu xoá | `POST /api/pdpd/{sdt}/xoa` (hai người duyệt) |
| Luật Điều 3 khoản 3 | Chỉ lưu trong thời hạn phù hợp mục đích | Vòng dọn hằng ngày, mặc định 180 ngày |
| Luật Điều 9; NĐ 356 Điều 6 | Đồng ý theo từng mục đích, chứng minh được | `contact_consents` (có `evidence`), chốt trong outbox |
| Luật Điều 4 khoản 5; NĐ 356 Điều 5 | **Thời hạn** đáp ứng yêu cầu | Sổ `yeu_cau_chu_the`, báo đỏ khi quá hạn |
| Luật Điều 20, 21 | Hồ sơ đánh giá tác động, chuyển ra nước ngoài | `python -m scripts.sinh_ho_so_bvdlcn --ghi` (bản nháp) |

Thao tác trên dashboard: mục **Nhật ký**.

---

## Thời hạn đáp ứng yêu cầu — NĐ 356/2025 Điều 5

| Yêu cầu | Phản hồi ban đầu | Xử lý xong | Nhờ bên thứ ba | Gia hạn (1 lần) |
|---|---|---|---|---|
| xem, sửa, cung cấp | 2 ngày làm việc | 10 ngày | 15 ngày | ≤ 10 ngày |
| rút đồng ý, hạn chế, phản đối | 2 ngày làm việc | 15 ngày | 20 ngày | ≤ 15 ngày |
| xoá | 2 ngày làm việc | 20 ngày | 30 ngày | ≤ 20 ngày |
| áp biện pháp bảo vệ | 2 ngày làm việc | 15 ngày | 15 ngày | ≤ 15 ngày |

Bốn quyết định trong `agent/core/yeu_cau_chu_the.py`, đều theo hướng an toàn:

- **"Ngày làm việc" chỉ bỏ thứ Bảy, Chủ nhật, không trừ ngày lễ.** Sai thì
  hạn đến SỚM hơn luật, không bao giờ muộn hơn.
- **Hạn tính từ lúc khách GỬI, không phải lúc vào sổ.** Ô "Khách gửi lúc"
  cho ghi lùi; khách nhắn từ 25 ngày trước thì vào sổ đã quá hạn.
- **Quá hạn rồi thì không gia hạn được** — gia hạn lúc ấy là hợp thức hoá
  một vi phạm đã xảy ra.
- **Sổ không lưu số điện thoại**, chỉ lưu dấu băm: sổ phải sống sót qua
  chính việc xoá mà nó theo dõi. Xoá trọn qua trang PDPD thì yêu cầu xoá
  của số ấy tự đóng; xoá dở (ERP còn dữ liệu) thì KHÔNG đóng.

`python -m scripts.san_sang` báo **CHẶN** khi có yêu cầu quá hạn — quá hạn
là vi phạm đã xảy ra, không còn là rủi ro.

---

## Xoá hay ẩn danh — hai cách cho hai loại dữ liệu

Đây là phần dễ làm sai nhất. Không phải cứ yêu cầu xoá là xoá sạch mọi thứ.

Đơn hàng là **chứng từ kế toán**: Luật Kế toán 2015 Điều 41 buộc lưu tối
thiểu 10 năm. Xoá thẳng bản ghi đơn để thoả luật dữ liệu cá nhân là vi phạm
một luật khác — Luật 91/2025 Điều 14 khoản 2 cho phép từ chối xoá trong
những trường hợp như vậy.

```
   hội thoại + tin nhắn  ──>  XOÁ HẲN
                              chứa số điện thoại, địa chỉ, đôi khi cả tình
                              trạng da; không có nghĩa vụ lưu giữ nào

   đơn hàng              ──>  ẨN DANH
                              giữ mã đơn, sản phẩm, số tiền, ngày cho sổ sách
                              thay tên / sđt / địa chỉ bằng dấu ẩn danh

   khách bên KHO/ERP     ──>  ẨN DANH
                              Customer (ERPNext) / res.partner (Odoo)
                              cùng lý do: ERP chặn xoá bản ghi đã có chứng từ
```

Cách này thoả cả hai luật cùng lúc, và là cách các hệ thống quốc tế xử lý
xung đột giữa "quyền được xoá" và "nghĩa vụ lưu chứng từ".

### Nơi lưu THỨ BA: kho/ERP

Từ khi bật `ERP_GHI_DON=true`, tên — số điện thoại — địa chỉ khách được tạo
thành `Customer` (ERPNext) hoặc `res.partner` (Odoo) và nằm đó **vĩnh viễn**.

Đó là nơi lưu thứ ba, ngoài Postgres và hồ sơ ghi nhớ. `du_lieu_ca_nhan.xoa()`
gọi `an_danh_ben_erp()` để với tới nó.

**ERP không với tới được thì `da_xoa` trả `False`.** Đây là chỗ dễ làm sai
nhất và hậu quả nặng nhất: báo "đã xoá" trong khi ERP còn nguyên dữ liệu là
ghi một bản nhật ký `pdpd.xoa_du_lieu` **sai sự thật** — một bằng chứng tuân
thủ cho việc chưa làm. Nhật ký ghi cả `erp_da_lam` và `erp_ly_do` để phần
còn thiếu không biến mất.

Khi đó người vận hành phải vào ERP ẩn danh tay, vì **thời hạn đáp ứng yêu
cầu xoá là do luật đặt, không phải do hệ thống đặt**.

`ERP_GHI_DON` đang tắt thì mục này không áp dụng — ERP chưa từng nhận dữ
liệu khách nào.

---

## Ba chốt an toàn — vì xoá không hoàn tác được

**1. Chuẩn hoá số điện thoại trước khi tìm.**
`0967 627 336`, `+84967627336`, `(096) 762-7336` đều là một người. Không
chuẩn hoá thì yêu cầu xoá **trượt** trong khi hệ thống báo "đã xoá" — tệ
hơn là báo lỗi, vì khách tin là dữ liệu đã biến mất.

**2. Bắt gõ lại số một lần nữa.**
Không có nút xoá nào bấm được bằng một cú lỡ tay. Luồng bắt buộc là tra
cứu để **nhìn thấy sẽ mất gì** trước, rồi mới xoá được.

**3. Nhật ký ghi dấu vân tay, không ghi số thật.**
```python
"dau_van_tay": "17756315ebd47b71"   # SHA-256 rút gọn
```
Ghi số thật vào nhật ký thì việc xoá thành vô nghĩa — dữ liệu chỉ chuyển
từ bảng này sang bảng khác. Băm cho phép chứng minh "đã xử lý yêu cầu của
số này" mà không giữ lại chính số đó.

---

## Đã kiểm bằng luồng thật

```
1. Tra bằng "0987 654 321"  ->  chuẩn hoá thành 0987654321, tìm ra 1 đơn
2. Xoá với số xác nhận sai  ->  HTTP 422, bị chặn
3. Xoá với số đúng          ->  ẩn danh 1 đơn, xoá 0 hội thoại
4. Tra lại bằng số cũ       ->  không còn gì

   bảng orders sau khi xoá:
     AS260819235000 | [đã ẩn danh theo yêu cầu] | 1.290.000đ | items giữ: True
```

Số tiền và mã đơn nguyên vẹn cho sổ sách, PII đã biến mất.

---

## Thời hạn lưu trữ

`LUU_HOI_THOAI_NGAY=180` trong `.env`. Vòng `don_du_lieu_loop` chạy mỗi 24
giờ, chỉ đụng **hội thoại**, không đụng đơn hàng.

Đặt 180 ngày vì nó đủ dài để tra lại lịch sử tư vấn và đủ ngắn để không giữ
vô thời hạn. Luật không ấn định con số cụ thể; nó yêu cầu thời hạn
**phù hợp với mục đích đã thông báo**, nên con số này phải khớp với điều
doanh nghiệp nói với khách khi thu thập.

Tắt tự động: `TU_DONG_DON_DU_LIEU=false`, rồi bấm tay trên dashboard.

---

## Còn thiếu cho production thật

Ghi rõ để không ai tưởng phần này đã đầy đủ:

- **Dữ liệu nhạy cảm chưa có câu thông báo riêng.** Ảnh vùng da và mô tả
  tình trạng da là "tình trạng sức khoẻ" — dữ liệu nhạy cảm (NĐ 356/2025
  Điều 4 khoản 1 điểm d). Phải báo khách đây là dữ liệu nhạy cảm và xin
  đồng ý (NĐ 356 Điều 6 khoản 4). Câu thông báo là quyết định của cửa hàng.
- **Chưa thông báo việc xử lý tự động bằng AI** và quyền chọn nói chuyện
  với người (NĐ 356/2025 Điều 10 khoản 3).
- **Hồ sơ đánh giá tác động và hồ sơ chuyển dữ liệu ra nước ngoài chưa
  nộp.** Hệ thống gửi hội thoại tới máy chủ model ngoài Việt Nam, và xử lý
  dữ liệu nhạy cảm nên miễn trừ doanh nghiệp nhỏ không áp dụng (NĐ 356
  Điều 41). Hạn 60 ngày kể từ lần xử lý đầu. Bản nháp: `sinh_ho_so_bvdlcn`.
- **Chưa có quy trình báo sự cố 72 giờ** (Luật Điều 23; mẫu NĐ 356 Điều 28).
- **Chưa mã hoá dữ liệu khi lưu, và bản sao lưu hằng ngày chưa mã hoá.**
