# MCP — mở hệ thống ra cho ứng dụng ngoài

## Ý nghĩa

Từ trước tới giờ luồng đi một chiều: agent gọi công cụ nghiệp vụ. Lớp MCP
đảo chiều — biến chính hệ thống thành công cụ mà **ứng dụng khác gọi vào**.

Nghĩa là Claude Desktop, Claude Code, hay bất cứ ứng dụng nào nói được
Model Context Protocol đều hỏi được:

> *"Aurora Skin còn bao nhiêu sữa rửa mặt cho da dầu?"*
> *"Tuần này bài nào chạy tốt nhất?"*
> *"Soạn giúp tôi một bài TikTok về serum niacinamide."*

mà không cần biết gì về FastAPI, Postgres hay Vertex bên trong.

Với doanh nghiệp, đây là khác biệt giữa **một công cụ** và **một nền tảng**:
phòng marketing dùng dashboard, phòng kinh doanh hỏi qua Claude Desktop,
mà cả hai nhìn cùng một kho dữ liệu và cùng một luật tuân thủ.

---

## Ranh giới an toàn — phần quan trọng nhất

Công cụ chia hai loại và **không được lẫn**:

| Loại | Có gì | Vì sao |
|---|---|---|
| **Đọc** | tra sản phẩm, tra đơn, tìm tài liệu, xem số liệu | An toàn, cho gọi thoải mái |
| **Ghi** | soạn bài, đưa bài vào hàng đợi | Luôn dừng ở `cho_duyet` |

Máy chủ MCP **không có** công cụ nào đăng bài, chốt đơn, hay nhắn tin cho
khách. Lý do:

> MCP client là **một model khác**, chạy ngoài tầm kiểm soát của hệ thống
> này. Nó không đi qua chốt tuân thủ trong `agent/core/agent.py`, không có
> trần chi phí, không có lưới an toàn chuyển người. Cho nó quyền nhắn tin
> cho khách hay đăng bài lên fanpage là giao chìa khoá cho một người lạ.

Ràng buộc này được canh bằng test (`tests/test_mcp.py`), không phải bằng
lời hứa: bất cứ ai thêm một công cụ có hậu quả ra ngoài sẽ làm đỏ CI.

---

## Chín công cụ

| Công cụ | Việc | Loại |
|---|---|---|
| `tra_cuu_san_pham` | giá, dung tích, tồn kho, thành phần một sản phẩm | đọc |
| `goi_y_san_pham` | lọc theo loại da, nhu cầu, nhóm hàng, ngân sách | đọc |
| `tra_cuu_don_hang` | tình trạng đơn theo mã | đọc |
| `tim_trong_kho_tri_thuc` | tìm trong tài liệu nội bộ, có điểm khớp và nguồn | đọc |
| `hieu_qua_bai_dang` | số liệu mạng xã hội, bài chạy tốt nhất | đọc |
| `danh_sach_bai_dang` | hàng đợi bài đăng | đọc |
| `soan_bai_dang` | agent viết nội dung, tự kiểm tuân thủ | ghi (không lưu) |
| `dua_bai_vao_hang_doi` | lưu bài ở trạng thái chờ duyệt | ghi |
| `kiem_tra_tuan_thu_quang_cao` | soi nội dung theo TT 06/2011 và NĐ 181/2013 | đọc |

Và hai tài nguyên: `aurora://danh-muc` (toàn bộ danh mục sản phẩm),
`aurora://huong-dan-viet` (giới hạn pháp lý khi viết quảng cáo mỹ phẩm).

---

## Nối vào Claude Desktop

Mở file cấu hình:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Thêm:

```json
{
  "mcpServers": {
    "aurora-marketing": {
      "command": "C:\\Users\\PC\\Downloads\\Marketing\\.venv\\Scripts\\python.exe",
      "args": ["-m", "agent.mcp_server"],
      "cwd": "C:\\Users\\PC\\Downloads\\Marketing"
    }
  }
}
```

Khởi động lại Claude Desktop. Biểu tượng công cụ hiện lên là xong.

**Phải dùng Python trong `.venv`**, không phải Python hệ thống — thư viện
nằm ở đó. Và `cwd` phải trỏ đúng thư mục dự án để `.env` được đọc.

## Nối vào Claude Code

```bash
claude mcp add aurora-marketing --scope project -- .venv/Scripts/python.exe -m agent.mcp_server
```

## Kiểm tra không cần client nào

```bash
.venv/Scripts/python.exe -m scripts.mcp_thu
```

Script này khởi động máy chủ như một tiến trình con, bắt tay theo **đúng
giao thức thật** rồi gọi từng công cụ — không giả lập lời gọi hàm. Chạy
được ở đây thì Claude Desktop cũng chạy được.

---

## Chế độ HTTP

```bash
.venv/Scripts/python.exe -m agent.mcp_server --http
```

Nghe ở `127.0.0.1:8765`. **Chỉ loopback, có chủ ý**: máy chủ này chưa có
xác thực, mở ra mạng là mở luôn dữ liệu khách hàng. Muốn dùng từ xa thì
phải đặt sau một lớp proxy có xác thực trước.

---

## Một lỗi đáng ghi lại

Lớp bọc MCP gọi lại `tools.run_tool` bằng dict. Bản đầu đặt sai tên khoá —
`van_de` thay vì `nhu_cau`, `ngan_sach` thay vì `gia_toi_da`.

Hậu quả: bộ lọc **bỏ qua trong im lặng**. Không lỗi, không cảnh báo, chỉ
có kết quả sai. Loại lỗi khó thấy nhất, vì mọi thứ trông như đang chạy.

Giờ có test soi thẳng mã nguồn: mọi khoá truyền vào `run_tool` phải nằm
trong `input_schema` của công cụ thật.

---

## Bước mở rộng tiếp theo

Chiều ngược lại — cho **agent tiêu thụ** MCP server bên ngoài (Google
Sheets, HubSpot, kho hàng của doanh nghiệp) — là phần mở rộng tự nhiên,
nhưng cần cân nhắc kỹ: công cụ ngoài chưa qua kiểm duyệt mà đưa thẳng vào
tay agent đang nói chuyện với khách thật là mở một lối vào không kiểm soát
được. Nếu làm, nên có danh sách cho phép và một lớp bọc kiểm tra kết quả
trước khi agent dùng.
