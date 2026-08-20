# Bảo vệ dữ liệu cá nhân — Nghị định 13/2023/NĐ-CP

## Vì sao phần này tồn tại

Hệ thống lưu họ tên, số điện thoại, địa chỉ giao hàng và toàn bộ nội dung
hội thoại của khách hàng thật. **Nghị định 13/2023/NĐ-CP** — hiệu lực từ
01/07/2023, là bản tương đương GDPR của Việt Nam — đặt ra ba nghĩa vụ mà
trước đây hệ thống không đáp ứng được câu nào.

Bất kỳ ai xem xét hệ thống theo chuẩn quốc tế đều hỏi ba câu: thu thập
trên cơ sở nào, giữ bao lâu, và khách yêu cầu xoá thì làm thế nào.

| Điều | Quyền | Đáp ứng bằng |
|---|---|---|
| 9.1.c | Biết hệ thống giữ gì | `GET /api/pdpd/{sdt}` |
| 9.1.đ | Yêu cầu xoá | `POST /api/pdpd/{sdt}/xoa` |
| 16 | Thời hạn lưu trữ | Vòng dọn hằng ngày, mặc định 180 ngày |

Thao tác trên dashboard: mục **Nhật ký**.

---

## Xoá hay ẩn danh — hai cách cho hai loại dữ liệu

Đây là phần dễ làm sai nhất. Không phải cứ yêu cầu xoá là xoá sạch mọi thứ.

Đơn hàng là **chứng từ kế toán**: Luật Kế toán 2015 Điều 41 buộc lưu tối
thiểu 10 năm. Xoá thẳng bản ghi đơn để thoả Nghị định 13 là vi phạm một
luật khác.

```
   hội thoại + tin nhắn  ──>  XOÁ HẲN
                              chứa số điện thoại, địa chỉ, đôi khi cả tình
                              trạng da; không có nghĩa vụ lưu giữ nào

   đơn hàng              ──>  ẨN DANH
                              giữ mã đơn, sản phẩm, số tiền, ngày cho sổ sách
                              thay tên / sđt / địa chỉ bằng dấu ẩn danh
```

Cách này thoả cả hai luật cùng lúc, và là cách các hệ thống quốc tế xử lý
xung đột giữa "quyền được xoá" và "nghĩa vụ lưu chứng từ".

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
vô thời hạn. Nghị định 13 không ấn định con số cụ thể; nó yêu cầu thời hạn
**phù hợp với mục đích đã thông báo**, nên con số này phải khớp với điều
doanh nghiệp nói với khách khi thu thập.

Tắt tự động: `TU_DONG_DON_DU_LIEU=false`, rồi bấm tay trên dashboard.

---

## Còn thiếu cho production thật

Ghi rõ để không ai tưởng phần này đã đầy đủ:

- **Chưa có ghi nhận sự đồng ý.** Nghị định 13 Điều 11 yêu cầu sự đồng ý
  phải được thể hiện rõ ràng và có thể chứng minh. Hiện hệ thống không lưu
  thời điểm và nội dung khách đồng ý.
- **Chưa có thông báo vi phạm.** Điều 23 buộc báo Bộ Công an trong 72 giờ
  kể từ khi phát hiện lộ dữ liệu.
- **Chưa mã hoá dữ liệu khi lưu.** Postgres đang lưu ở dạng thường.
