# Nối DeepSeek Harness (dsh) vào hệ thống

**Không cần viết plugin.** dsh có sẵn plugin MCP client chính thức, và hệ
thống này đã là một máy chủ MCP.

---

## Vì sao thư mục này gần như trống

Bản đầu ở đây có một plugin tự viết: `src/index.ts` (khớp khuôn Cordis),
`src/mcp-client.ts` (tự nói JSON-RPC), `kiem.mjs`, `package.json`,
`tsconfig.json`. Tất cả đã bị **xoá**, và đây là lý do — ghi lại để không ai
viết lại chúng.

**Thứ nhất: nó thừa.** `@deepseek-ai/dsh-mcp-client` là plugin CHÍNH THỨC
của DeepSeek, mô tả nguyên văn: *"MCP client bridge: connects to MCP servers
and registers their tools on ctx.tools"*. Nó làm đúng việc mà `mcp-client.ts`
tự viết ra để làm.

**Thứ hai: `index.ts` sai mô hình.** Tôi đoán plugin dsh là một FILE tĩnh
xuất hàm `apply(ctx, config)`. Đọc gói thật thì không phải: plugin Cordis
của dsh được **định nghĩa lúc chạy** qua các công cụ `cordis_define`,
`cordis_run`, `cordis_inspect_list` — mã đi vào dưới dạng chuỗi `code.host`
/ `code.client`, không phải file trong repo.

Chính tài liệu của dsh nói thẳng điều tôi đã vi phạm:

> *"Never infer a complete API from a Service name, Event payload, Slot
> props, theme token, or example."*

README bản trước đã ghi sẵn điều kiện xoá: *"Nếu dsh đã có sẵn plugin MCP
client thì bỏ hẳn `src/index.ts`."* Điều kiện đó nay đúng, nên xoá.

---

## Cách nối thật — ba bước

### 1. Bật MCP ở hệ thống này

```bash
python -m scripts.sinh_token MCP_TOKEN
```

Lệnh này ghi token vào `.env` và **không in ra màn hình** — cố ý, để bí mật
không nằm lại trong lịch sử terminal hay ảnh chụp màn hình. Đừng thay bằng
`python -c "...print(token)"`.

Khởi động lại máy chủ. Không có `MCP_TOKEN` thì `/mcp/` trả 404 kèm
`{"error": "MCP chưa bật"}` — đó là thiết kế, không phải lỗi.

### 2. Cài dsh và plugin MCP client

```bash
npm install -g @deepseek-ai/dsh
```

```bash
dsh plugin add @deepseek-ai/dsh-mcp-client
```

**Cả hai đang ở bản release candidate** (`dsh` 0.1.1-rc.2, `dsh-mcp-client`
0.0.1-rc.1). API còn đổi. Đừng đặt chúng vào đường chạy của khách thật.

### 3. Trỏ nó vào đây

| | |
|---|---|
| Địa chỉ | `http://127.0.0.1:8000/mcp/` |
| Xác thực | `Authorization: Bearer <MCP_TOKEN>` |

Chỗ khai báo nằm trong cấu hình của `dsh-mcp-client` — đọc README của chính
gói đó, vì nó là gói của người khác và tôi không đoán thay.

---

## Nối được thì thấy gì

11 công cụ. Danh sách nguồn sự thật là `agent/mcp_server.py`; bảng dưới chỉ
để đọc, và `tests/test_plugin_dsh_erp.py` canh hai bên không trôi.

| Nhóm | Công cụ |
|---|---|
| Kho / sản phẩm | `tra_cuu_san_pham` · `goi_y_san_pham` · `ton_kho_realtime` · `suc_khoe_erp` |
| Đơn hàng | `tra_cuu_don_hang` |
| Tri thức | `tim_trong_kho_tri_thuc` |
| Nội dung | `hieu_qua_bai_dang` · `danh_sach_bai_dang` · `soan_bai_dang` · `dua_bai_vao_hang_doi` · `kiem_tra_tuan_thu_quang_cao` |

### Không có công cụ nào chốt đơn, và đó là ràng buộc

dsh là **một agent runtime khác**. Nó không đi qua năm lớp lưới tuân thủ
trong `agent/core/agent.py`, không có trần chi phí, không có lưới an toàn
chuyển người.

Cho nó quyền chốt đơn hay nhắn tin cho khách là giao chìa khoá cho một người
lạ. `soan_bai_dang` có ghi, nhưng bài luôn dừng ở `cho_duyet` — người duyệt.

Muốn lên đơn thì đi qua agent, hoặc qua dashboard nơi có người thật bấm nút.

---

## Hai câu trả lời dễ hiểu nhầm

**`ton_kho_realtime` trả `tra_duoc: false`** — nghĩa là *chưa tra được*,
**không phải hết hàng**. Không có `ban_duoc` trong phản hồi là có chủ ý: trả
`0` sẽ bị hiểu thành hết hàng. Gặp trường hợp này thì đừng nói con số nào.

**`suc_khoe_erp` trả `mach_mo: true`** — cổng đã ngắt mạch sau nhiều lần gọi
hỏng. Mọi câu hỏi về giá và tồn kho sẽ trả "không biết" cho tới khi mạch
đóng lại. Đây là hành vi đúng, không phải lỗi.

---

## dsh không nằm trong `requirements.txt`

Có chủ ý, và có test canh. Nó là công cụ **bạn chạy**, không phải phụ thuộc
của hệ thống. Bản rc không được đứng trong đường chạy của khách thật.
