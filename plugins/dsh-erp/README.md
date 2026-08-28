# dsh-erp — hỏi kho/ERP từ trong DeepSeek Harness

Plugin **chỉ đọc**, nối DeepSeek Harness (`dsh`) tới máy chủ MCP của hệ thống
Marketing Agent.

---

## Đọc phần này trước

Thư mục này có **hai nửa, mức tin cậy khác hẳn nhau**:

| Tệp | Trạng thái |
|---|---|
| `src/mcp-client.ts` | ✅ Nói JSON-RPC 2.0 qua HTTP tới `/mcp/`. Giao thức đã chốt, đúng bất kể dsh đổi thế nào. |
| `cong-cu.json` | ✅ Có test Python canh: `tests/test_plugin_dsh_erp.py` đối chiếu danh sách này với công cụ thật của `agent/mcp_server.py`. Đổi tên bên Python mà quên sửa đây thì đỏ. |
| `src/index.ts` | ⚠️ **Chưa xác minh.** Viết theo mô tả chung về plugin Cordis, chưa đối chiếu với bản dsh nào. |

Lý do `index.ts` chưa xác minh: trang tài liệu `deepseek-harness.github.io`
là SPA nên fetch không ra nội dung, raw README trả 404, và dsh đang ở
**developer preview** nên API còn đổi.

**Trước khi chạy thật, đối chiếu ba thứ** với bản dsh bạn cài:

1. Chữ ký hàm plugin — `apply(ctx, config)` có đúng không.
2. Tên service đăng ký công cụ — mã đang gọi `ctx.tool?.(...)`, gần như chắc
   chắn không phải tên thật.
3. `ctx.logger?.warn?.(...)` — tên logger.

Cả ba đều viết dạng optional-call (`?.`) nên **plugin không nổ** nếu tên sai
— nó chỉ lặng lẽ không đăng ký công cụ nào. Đó là đánh đổi có chủ ý để plugin
không làm sập dsh của bạn, nhưng nghĩa là **bạn phải tự kiểm** rằng công cụ
thật sự xuất hiện.

**Nếu dsh đã có sẵn plugin MCP client:** bỏ hẳn `src/index.ts` và chỉ khai
báo máy chủ MCP trong cấu hình dsh. Ít mã hơn thì ít thứ hỏng hơn.

---

## Cần gì để chạy

Máy chủ Marketing Agent đang chạy, và **MCP đã bật**. MCP chỉ bật khi có
`MCP_TOKEN`; không có thì `/mcp/` trả 404 kèm `{"error": "MCP chưa bật"}`.

```bash
python -m scripts.sinh_token MCP_TOKEN
```

Lệnh này ghi thẳng token vào `.env`, **không in ra màn hình** — cố ý, để bí
mật không nằm lại trong lịch sử terminal hay trong ảnh chụp màn hình. Đừng
thay bằng `python -c "...print(token)"`.

Rồi khởi động lại máy chủ:

```bash
python -m uvicorn agent.main:app --reload --port 8000
```

---

## Cấu hình plugin

Hai biến môi trường:

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `MARKETING_AGENT_URL` | `http://127.0.0.1:8000` | Gốc máy chủ |
| `MCP_TOKEN` | — | Bắt buộc. Cùng giá trị với `.env` của máy chủ |

---

## Công cụ nó phơi ra

Nguồn sự thật là `cong-cu.json`, không phải bảng này — bảng này chỉ để đọc.

| Công cụ | Việc |
|---|---|
| `tra_cuu_san_pham` | Giá, dung tích, tồn kho, thành phần của một sản phẩm |
| `goi_y_san_pham` | Gợi ý theo loại da, nhu cầu, nhóm hàng, ngân sách |
| `ton_kho_realtime` | Số hàng **bán được**, hỏi thẳng kho, bỏ qua cache |
| `suc_khoe_erp` | Đang nối nguồn nào, còn sống không, mạch có đang mở không |
| `tra_cuu_don_hang` | Tình trạng một đơn theo mã |
| `tim_trong_kho_tri_thuc` | Tra chính sách, hướng dẫn trong kho tài liệu |

### Không có công cụ nào ghi, và đó là ràng buộc chứ không phải thiếu sót

Plugin chạy trong dsh — **một agent runtime khác**. Nó không đi qua năm lớp
lưới tuân thủ trong `agent/core/agent.py`, không có trần chi phí, không có
lưới an toàn chuyển người.

Cho nó quyền chốt đơn, trừ kho hay nhắn tin cho khách là giao chìa khoá cho
một người lạ. `tests/test_plugin_dsh_erp.py::test_plugin_khong_khai_cong_cu_ghi`
canh đúng việc này.

Muốn lên đơn thì đi qua agent, hoặc qua dashboard nơi có người thật bấm nút.

---

## Hai câu trả lời dễ hiểu nhầm

**`ton_kho_realtime` trả `tra_duoc: false`** — nghĩa là *chưa tra được*,
**không phải hết hàng**. Không có `ban_duoc` trong phản hồi là có chủ ý: trả
`0` sẽ bị hiểu thành hết hàng, và đó là câu trả lời sai khác hẳn. Gặp trường
hợp này thì đừng nói với ai con số nào.

**`suc_khoe_erp` trả `mach_mo: true`** — cổng đã ngắt mạch sau nhiều lần gọi
hỏng liên tiếp. Mọi câu hỏi về giá và tồn kho sẽ trả "không biết" cho tới khi
mạch đóng lại. Đây là hành vi đúng, không phải lỗi.

---

## Không nằm trong `requirements.txt`

Có chủ ý. dsh đang ở developer preview; không cho nó thành phụ thuộc bắt buộc
của hệ thống chạy thật. Có test canh (`test_plugin_khong_nam_trong_requirements`).
