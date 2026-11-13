# Từ Điển Biến & Thuật Ngữ Trong Marketing AI Agent

> **Mục đích tài liệu:** Bản tra cứu toàn diện về mọi biến số, trường dữ liệu, cờ logic và hằng số được sử dụng trong toàn bộ hệ thống Marketing AI Agent. Dành cho lập trình viên, kỹ sư AI và người vận hành đọc hiểu mã nguồn một cách nhanh chóng và chính xác.

---

## Mục lục

1. [Nguyên Tắc & Quy Ước Đặt Tên Biến](#1-nguyên-tắc--quy-ước-đặt-tên-biến)
2. [Bảng Tra Cứu Nhanh Các Biến Dễ Gây Nhầm Lẫn](#2-bảng-tra-cứu-nhanh-các-biến-dễ-gây-nhầm-lẫn)
3. [Cấu Hình Hệ Thống & Biến Môi Trường (`agent/config.py` & `.env`)](#3-cấu-hình-hệ-thống--biến-môi-trường-agentconfigpy--env)
4. [Lõi Agent & Điều Phối Hội Thoại (`agent/core/agent.py`)](#4-lõi-agent--điều-phối-hội-thoại-agentcoreagentpy)
5. [Mô Hình Ngôn Ngữ & LLM Interface (`agent/core/llm.py`)](#5-mô-hình-ngôn-ngữ--llm-interface-agentcorellmpy)
6. [Cơ Sở Tri Thức & RAG (`agent/core/rag.py`)](#6-cơ-sở-tri-thức--rag-agentcoreragpy)
7. [Công Cụ Nghiệp Vụ & Tham Số Tool (`agent/core/tools.py`)](#7-công-cụ-nghiệp-vụ--tham-số-tool-agentcoretoolspy)
8. [Kho Hàng & Biến Động Tồn Kho (`agent/core/kho.py`)](#8-kho-hàng--biến-động-tồn-kho-agentcorekhopy)
9. [Cổng Tích Hợp Kho & ERP (`agent/erp/`)](#9-cổng-tích-hợp-kho--erp-agenterp)
10. [Vận Chuyển & Giao Hàng (`agent/shipping/`)](#10-vận-chuyển--giao-hàng-agentshipping)
11. [Trí Nhớ Khách Hàng & Bảo Vệ Dữ Liệu (`agent/core/ho_so_khach.py`, `du_lieu_ca_nhan.py`)](#11-trí-nhớ-khách-hàng--bảo-vệ-dữ-liệu-agentcoreho_so_khachpy-du_lieu_ca_nhanpy)
12. [An Ninh, Phòng Thủ & Tự Nhiên Hoá (`phong_thu.py`, `tu_nhien.py`, `gio_lam_viec.py`)](#12-an-ninh-phòng-thủ--tự-nhiên-hoá-phong_thupy-tu_nhienpy-gio_lam_viecpy)
13. [Kênh Tiếp Nhận & Đa Kênh (`agent/channels/`, `agent/omnichannel/`)](#13-kênh-tiếp-nhận--đa-kênh-agentchannels-agentomnichannel)
14. [Canh Gác & Sức Khoẻ Hệ Thống (`agent/canh_gac.py`, `agent/suc_khoe.py`)](#14-canh-gác--sức-khoẻ-hệ-thống-agentcanh_gacpy-agentsuc_khoepy)
15. [Lược Đồ Cơ Sở Dữ Liệu PostgreSQL (`agent/schema.sql`)](#15-lược-đồ-cơ-sở-dữ-liệu-postgresql-agentschemasql)
16. [Sản Xuất Video & Đăng Bài Tự Động (`agent/video/`, `agent/publish/`)](#16-sản-xuất-video--đăng-bài-tự-động-agentvideo-agentpublish)

---

## 1. Nguyên Tắc & Quy Ước Đặt Tên Biến

Dự án tuân theo các quy tắc nhất quán phản ánh kiến trúc và miền nghiệp vụ:

* **Biến Tiếng Việt không dấu (`snake_case`):** Dành riêng cho **logic nghiệp vụ đặc thù của cửa hàng mỹ phẩm tại Việt Nam** (sản phẩm, kho hàng, đơn hàng, trạng thái duyệt, hồ sơ khách, canh gác, giờ làm việc, luật tuân thủ Bộ Y Tế, Nghị định 13/2023). Ví dụ: `ton_kho`, `khach_ten`, `thanh_tien`, `tu_chot`, `cho_duyet`, `ban_duoc`.
* **Biến Tiếng Anh (`snake_case` / `camelCase`):** Dành cho **hạ tầng công nghệ và giao thức chuẩn quốc tế** (LLM, RAG, pgvector, HTTP, FastAPI, Docker, OAuth, database drivers). Ví dụ: `conversation_id`, `tokens_in`, `latency_ms`, `cost_usd`, `idempotency_key`, `embedding`.
* **Hằng số viết hoa (`UPPER_SNAKE_CASE`):** Cấu hình cố định, ngưỡng giới hạn an toàn hoặc regex chốt chặn. Ví dụ: `_BUOC_CHUYEN`, `MAX_TOOL_ROUNDS`, `NGUONG_SAP_HET`, `TRANG_THAI_DON`.
* **Tiền tố gạch dưới (`_ten_bien`, `_ten_ham`):** Biến hoặc hàm nội bộ trong module, không xuất khẩu ra bên ngoài.

---

## 2. Bảng Tra Cứu Nhanh Các Biến Dễ Gây Nhầm Lẫn

| Tên biến A | Tên biến B | Sự khác biệt cốt lõi |
|---|---|---|
| `channel` | `nen_tang` | `channel` là adapter kỹ thuật tiếp nhận (`zalocrm`, `chatwoot`, `messenger`).<br>`nen_tang` là mạng xã hội gốc của khách (`facebook`, `instagram`, `whatsapp`, `zalo`). Chatwoot gộp nhiều nền tảng về một kênh duy nhất. |
| `customer_ref` | `khach_ten` / `customer_name` | `customer_ref` là ID duy nhất của khách trên kênh nhắn tin (ví dụ Zalo ID, PSID của FB).<br>`khach_ten` / `customer_name` là tên hiển thị hoặc họ tên thật khách cung cấp khi chốt đơn. |
| `ton_kho` | `ban_duoc` | `ton_kho` là tổng số lượng vật lý còn trong kho.<br>`ban_duoc` (`free_qty`) = `ton_kho` - số lượng đã bị đơn hàng khác giữ chỗ. Agent **chỉ được phép bán theo `ban_duoc`**. |
| `da_chot` | `cho_duyet` | `da_chot`: Agent tự chốt đơn thành công vì tổng tiền < `nguong_tu_chot_vnd`.<br>`cho_duyet`: Đơn hàng vượt hạn mức tiền hoặc cần người thật vào bấm xác nhận. |
| `cho_dong_bo` | `da_giao` | `cho_dong_bo`: Đơn đã chốt nội bộ nhưng chưa đẩy được sang phần mềm ERP/kho bên ngoài (đang thử lại).<br>`da_giao`: Đơn hàng đã được đơn vị vận chuyển giao tận tay khách. |
| `tu_chot` | `tu_dong_dang_khong_can_duyet` | `tu_chot`: Cho phép agent tự xác nhận đơn hàng nhỏ lẻ.<br>`tu_dong_dang_khong_can_duyet`: Cờ nguy hiểm cho phép tự đăng bài lên Fanpage/TikTok không cần con người duyệt trước (mặc định luôn `False`). |
| `external_id` | `conversation_id` | `external_id` là mã hội thoại phía Zalo/Chatwoot.<br>`conversation_id` là mã UUID nội bộ trong CSDL PostgreSQL của Marketing Agent. |
| `ma_don` | `ma_van_don` | `ma_don` là mã đơn hàng nội bộ (ví dụ `AS260904120000`).<br>`ma_van_don` là mã theo dõi của hãng vận chuyển (ví dụ `GHN12345678`). |
| `Gia.gia_ban` | `sp["gia"]` | `Gia.gia_ban` là đối tượng chứa giá kèm xuất xứ pricelist từ ERP thật.<br>`sp["gia"]` là giá niêm yết trong file tĩnh `catalog.json`. |

---

## 3. Cấu Hình Hệ Thống & Biến Môi Trường (`agent/config.py` & `.env`)

Mọi thiết lập tập trung trong class `Settings(BaseSettings)`. Không hardcode giá trị ở bất cứ file nào khác.

### 3.1. Nhà Cung Cấp Mô Hình & AI (LLM / Embeddings)

* **`llm_provider`** (`str`, mặc định `"gemini"`): Chọn nhà cung cấp LLM chính. Nhận một trong các giá trị: `"gemini"` (Vertex AI), `"vertex"` (Claude trên Vertex AI), `"anthropic"` (Claude API trực tiếp), `"openai"` (OpenAI API).
* **`anthropic_api_key`** (`str`): Khóa API bí mật của Anthropic nếu dùng trực tiếp.
* **`openai_api_key`** (`str`): Khóa API OpenAI khi dùng GPT hoặc embedding OpenAI.
* **`openai_base_url`** (`str`, mặc định `"https://api.openai.com/v1"`): Đường dẫn gốc tới API OpenAI (có thể trỏ proxy hoặc Azure OpenAI).
* **`gcp_project_id`** (`str`): ID dự án Google Cloud Platform chứa quota Vertex AI.
* **`gcp_region`** (`str`, mặc định `"global"`): Vùng chạy mô hình Claude trên Vertex AI.
* **`gemini_region`** (`str`, mặc định `"us-central1"`): Vùng chạy mô hình Gemini và Text Embedding trên Vertex AI.
* **`model_chat`** (`str`, mặc định `"gemini-2.5-flash"`): Tên mô hình đảm nhiệm việc trò chuyện, gọi công cụ tư vấn khách hàng.
* **`model_hard`** (`str`, mặc định `"gemini-2.5-pro"`): Mô hình mạnh, thông minh hơn để xử lý tác vụ phức tạp (soạn bài viết dài, lập luận kịch bản video).
* **`model_cheap`** (`str`, mặc định `"gemini-2.5-flash-lite"`): Mô hình siêu nhẹ và rẻ để chạy kiểm tra sức khoẻ (health check) hoặc phân loại tin nhắn nhanh.
* **`confidence_floor`** (`float`, mặc định `0.55`): Ngưỡng độ tin cậy tối thiểu. Nếu điểm khớp RAG dưới mức này và không có dữ liệu từ tool, agent buộc phải chuyển cho nhân viên thật xử lý.
* **`max_cost_per_conversation`** (`float`, mặc định `0.25` USD): Trần chi phí gọi API tối đa cho một hội thoại. Vượt quá trần này, agent tự động chuyển người trực để chống bùng nổ ngân sách.

### 3.2. Tiến Trình & Vận Hành (Process & Role)

* **`vai_tro_tien_trinh`** (`str`, mặc định `"tat_ca"`): Phân chia vai trò khi chạy scale cụm máy chủ:
  * `"tat_ca"`: Chạy cả Web API và tất cả các worker nền (thích hợp cho máy đơn).
  * `"api"`: Chỉ xử lý HTTP request/webhook, không chạy worker nền.
  * `"worker"`: Chỉ chạy các tác vụ nền (outbox worker, video worker, canh gác, sao lưu, auto-routing).
* **`agent_enabled`** (`bool`, mặc định `True`): Công tắc bật/tắt toàn bộ AI agent. Nếu `False`, mọi tin nhắn đến sẽ đứng chờ người trực.
* **`agent_mode`** (`str`, mặc định `"assist"`):
  * `"assist"`: Agent soạn sẵn câu trả lời vào dashboard nhưng **chưa gửi**, nhân viên phải bấm nút duyệt gửi.
  * `"auto"`: Agent tự động gửi câu trả lời thẳng cho khách hàng nếu đủ điều kiện an toàn.
* **`nhip_nguoi_that`** (`bool`, mặc định `True`): Tự động chia nhỏ câu trả lời dài thành 2-3 tin nhắn ngắn và chèn độ trễ mô phỏng tốc độ gõ phím của con người.
* **`nguong_tu_chot_vnd`** (`int`, mặc định `1_000_000` VND): Hạn mức tối đa agent được phép tự chốt đơn. Đơn hàng từ giá trị này trở lên bắt buộc phải chuyển sang trạng thái `cho_duyet` để quản trị viên xác nhận.

### 3.3. Giờ Làm Việc (Business Hours)

* **`gio_lam_viec_bat`** (`bool`, mặc định `True`): Bật/tắt chế độ phân biệt trong giờ và ngoài giờ làm việc.
* **`gio_lam_viec_bat_dau`** (`int`, mặc định `8`): Giờ mở cửa hàng (8h sáng theo giờ Việt Nam UTC+7).
* **`gio_lam_viec_ket_thuc`** (`int`, mặc định `21`): Giờ đóng cửa (21h tối, tức 20:59 còn làm, 21:00 là hết giờ).
* **`tin_chuyen_nguoi`** (`str`): Câu thông báo gửi khách khi chuyển nhân viên trong giờ làm việc ("Shop sẽ kiểm tra và hỗ trợ mình sớm nhé!").
* **`tin_chuyen_nguoi_ngoai_gio`** (`str`): Câu thông báo gửi khách khi chuyển nhân viên ngoài giờ làm việc ("Giờ này bên em ngoài giờ làm việc rồi, bạn ấy sẽ nhắn lại cho mình từ {gio_mo} sáng mai nhé.").

### 3.4. Kho Hàng & Tích Hợp ERP

* **`erp_loai`** (`str`, mặc định `"tep"`): Nguồn dữ liệu kho và sản phẩm. Nhận: `"tep"` (đọc file tĩnh `catalog.json`), `"erpnext"` (kết nối ERPNext qua REST API), `"odoo"` (kết nối Odoo qua XML-RPC).
* **`erp_ttl_gia`** (`float`, mặc định `900.0` giây = 15 phút): Thời gian lưu cache giá bán từ ERP. Quá thời gian này bắt buộc phải gọi lại ERP.
* **`erp_ttl_ton`** (`float`, mặc định `60.0` giây = 1 phút): Thời gian lưu cache tồn kho bán được.
* **`erp_ngat_mach_so_lan`** (`int`, mặc định `5`): Số lần gọi lỗi liên tiếp tới ERP trước khi kích hoạt bộ ngắt mạch (Circuit Breaker).
* **`erp_ngat_mach_giay`** (`float`, mặc định `30.0` giây): Thời gian ngắt mạch dừng gọi ERP khi đang có sự cố.
* **`erp_ma_kho`** (`str`): Mã kho hàng cần kiểm tra tồn kho (bắt buộc khi dùng ERPNext/Odoo).
* **`erp_pricelist`** (`str`): Tên bảng giá áp dụng trong ERP.
* **`erp_ghi_don`** (`bool`, mặc định `False`): Cho phép tự động đẩy đơn hàng sang ERP. Mặc định tắt để tránh phát sinh dữ liệu không thể hoàn tác khi thử nghiệm.
* **`erpnext_url`**, **`erpnext_api_key`**, **`erpnext_api_secret`** (`str`): Thông tin kết nối máy chủ ERPNext.
* **`odoo_url`**, **`odoo_db`**, **`odoo_dang_nhap`**, **`odoo_api_key`** (`str`): Thông tin kết nối máy chủ Odoo.

### 3.5. Kênh Giao Tiếp Khách Hàng (Channels & Connectors)

* **`database_url`** (`str`): Chuỗi kết nối CSDL PostgreSQL (`postgresql://user:pass@host:port/db`).
* **`zalocrm_base_url`**, **`zalocrm_api_key`**, **`zalocrm_account_id`** (`str`): Cấu hình ZaloCRM di sản.
* **`legacy_polling_bat`** (`bool`, mặc định `False`): Bật/tắt cơ chế polling tin cũ của ZaloCRM.
* **`chatwoot_base_url`**, **`chatwoot_api_token`**, **`chatwoot_account_id`**, **`chatwoot_webhook_secret`** (`str`): Cấu hình kết nối hộp thư Chatwoot.
* **`zalo_oa_app_id`**, **`zalo_oa_secret_key`**, **`zalo_oa_refresh_token`** (`str`): Khóa định danh Zalo Official Account.
* **`zalo_oa_cua_so_gio`** (`float`, mặc định `168.0` giờ = 7 ngày): Cửa sổ thời gian được phép nhắn tin tự do cho khách qua Zalo OA kể từ tin nhắn cuối của khách.
* **`messenger_page_id`**, **`messenger_app_id`**, **`messenger_page_token`**, **`messenger_app_secret`**, **`messenger_verify_token`** (`str`): Cấu hình kết nối trực tiếp Facebook Messenger Graph API.
* **`messenger_cua_so_gio`** (`float`, mặc định `24.0` giờ): Cửa sổ 24 giờ tiêu chuẩn của Meta cho phép nhắn tin miễn phí với khách hàng.
* **`graph_version`** (`str`, mặc định `"v23.0"`): Phiên bản Meta Graph API dùng thống nhất toàn hệ thống.
* **`zalo_sidecar_url`**, **`zalo_sidecar_secret`** (`str`): Kết nối máy chủ sidecar xử lý Zalo cá nhân native.

### 3.6. Vận Chuyển (Shipping)

* **`shipping_provider`** (`str`, mặc định `"mock"`): Nhà cung cấp vận chuyển (`"mock"` hoặc `"ghn"` - Giao Hàng Nhanh).
* **`ghn_api_url`** (`str`, mặc định sandbox): URL API của GHN.
* **`ghn_token`**, **`ghn_shop_id`** (`str`): Token xác thực và ID cửa hàng trên hệ thống GHN.
* **`shipping_webhook_secret`** (`str`): Bí mật ký xác thực webhook thông báo trạng thái vận đơn từ hãng vận chuyển.
* **`shipping_tu_dong_tao`** (`bool`, mặc định `False`): Tự động tạo vận đơn ngay khi đơn chốt thành công.

### 3.7. Giám Sát, Bảo Mật & Quyền Riêng Tư

* **`canh_gac_bat`** (`bool`, mặc định `True`): Bật vòng lặp giám sát sức khoẻ định kỳ.
* **`canh_gac_moi_giay`** (`int`, mặc định `300` giây = 5 phút): Tần suất chạy kiểm tra sức khoẻ.
* **`canh_gac_webhook`** (`str`): URL webhook nhận thông báo khẩn cấp (như Telegram, Slack, Lark).
* **`canh_gac_goi_tin`** (`str`): Mẫu payload JSON gửi webhook báo động (hỗ trợ `{muc_do}`, `{tieu_de}`, `{chi_tiet}`, `{trang_thai}`).
* **`cho_nguoi_toi_da_phut`** (`int`, mặc định `30` phút): Thời gian tối đa khách chờ nhân viên trực sau khi agent chuyển giao trước khi hệ thống báo động.
* **`luu_hoi_thoai_ngay`** (`int`, mặc định `180` ngày): Thời hạn tối đa lưu trữ nội dung chat và dữ liệu nhạy cảm theo Nghị định 13/2023.
* **`tu_dong_don_du_lieu`** (`bool`, mặc định `True`): Tự động chạy lệnh quét và dọn dẹp các hội thoại quá hạn lưu trữ.
* **`mcp_token`** (`str`): Khóa bảo vệ máy chủ Model Context Protocol (MCP) qua HTTP. Nếu để trống là tắt tính năng MCP.
* **`cookie_bao_mat`** (`bool`, mặc định `False` trên dev, bật `True` trên production): Chỉ gửi cookie phiên qua kết nối bảo mật HTTPS.
* **`sse_poll_seconds`** (`float`, mặc định `0.25` giây): Nhịp quét CSDL của Server-Sent Events trên Dashboard trực tin.

### 3.8. Sản Xuất Video & Đăng Bài

* **`video_studio_dir`** (`str`, mặc định `"./video-studio"`): Thư mục chứa dự án HyperFrames / Remotion.
* **`video_output_dir`** (`str`, mặc định `"./data/videos"`): Thư mục lưu file video MP4 đã xuất.
* **`ffprobe_bin`** (`str`, mặc định `"ffprobe"`): Đường dẫn thực thi binary ffprobe.
* **`veo_model`** (`str`): Tên mô hình Google Veo (ví dụ `"veo-3.1-generate-preview"`). Nếu để trống là tắt dựng video AI bằng Veo.
* **`hyperframes_bat`** (`bool`, mặc định `False`): Bật/tắt renderer HyperFrames.
* **`video_workers`** (`int`, mặc định `1`): Số lượng luồng render video đồng thời.
* **`tts_provider`** (`str`, mặc định `"auto"`): Nhà cung cấp đọc giọng Text-to-Speech (`"viettts"` hoặc `"google"`).
* **`tts_voice`** (`str`, mặc định `"nu-nhe-nhang"`): Giọng đọc tiếng Việt của VietTTS.
* **`google_tts_voice`** (`str`, mặc định `"vi-VN-Neural2-A"`): Giọng đọc Neural của Google Cloud TTS.
* **`n8n_webhook_url`**, **`n8n_auth_header`** (`str`): Cấu hình gửi bài đăng sang n8n tự động đăng lên MXH.
* **`tu_dong_dang_khong_can_duyet`** (`bool`, mặc định `False`): Cho phép tự động đăng bài lên mạng xã hội không cần con người duyệt qua dashboard.

---

## 4. Lõi Agent & Điều Phối Hội Thoại (`agent/core/agent.py`)

### 4.1. Lớp Dữ Liệu `Reply` (Kết Quả Lượt Trả Lời)

Khi hàm `respond()` hoàn tất, nó trả về một instance của `Reply` với các trường:

* **`text`** (`str`): Nội dung câu trả lời hoàn chỉnh sẽ gửi cho khách (hoặc trình nhân viên duyệt).
* **`escalate`** (`bool`): Cờ báo hiệu có cần **chuyển giao hội thoại cho nhân viên thật** xử lý hay không. `True` khi gặp tình huống y tế, khiếu nại, khách xin huỷ đơn, vượt trần chi phí, phát hiện injection, v.v.
* **`escalate_reason`** (`str`): Lý do giải thích vì sao cần chuyển người (hiển thị trên dashboard để nhân viên nắm ngữ cảnh).
* **`grounded`** (`bool`): Cờ xác nhận câu trả lời **có căn cứ xác thực** (từ tài liệu RAG hoặc từ dữ liệu sống của công cụ nghiệp vụ).
* **`confidence`** (`float`): Điểm độ tin cậy ước tính (từ `0.0` đến `1.0`), tính dựa trên điểm tương đồng RAG và thưởng thêm nếu gọi tool có dữ liệu thật.
* **`sources`** (`list[str]`): Danh sách tên tài liệu được trích dẫn làm căn cứ trả lời (ví dụ `["chinh-sach-doi-tra.md"]`).
* **`cost_usd`** (`float`): Tổng chi phí tính bằng USD cho các lời gọi mô hình trong lượt này.
* **`tokens_in`** (`int`): Tổng số token đầu vào (prompt tokens).
* **`tokens_out`** (`int`): Tổng số token đầu ra (completion tokens).
* **`cache_read`** (`int`): Số token đọc từ Prompt Cache (tiết kiệm chi phí đáng kể).
* **`latency_ms`** (`int`): Tổng độ trễ tính bằng mili-giây từ lúc gửi request đến khi nhận câu trả lời.
* **`model`** (`str`): Tên định danh mô hình AI đã phục vụ lượt chat này.
* **`video_id`** (`str | None`): ID của video marketing vừa được khởi tạo nếu lượt chat có gọi công cụ `tao_video`.
* **`anh_can_gui`** (`list[dict]`): Danh sách ảnh sản phẩm agent quyết định gửi kèm cho khách (mỗi phần tử gồm `duong_dan` và `ten`).

### 4.2. Tham Số Đầu Vào Của Hàm `respond()`

* **`conversation_id`** (`uuid.UUID`): Mã định danh duy nhất của phiên hội thoại trong CSDL.
* **`history`** (`list[dict]`): Lịch sử các lượt chat trước đã được chuẩn hoá theo định dạng chuẩn (`{"role": "user"|"assistant", "content": ...}`).
* **`question`** (`str`): Tin nhắn mới nhất của khách hàng.
* **`customer_ref`** (`str`): Mã định danh khách hàng phía kênh (dùng để tra cứu và cập nhật hồ sơ khách).
* **`channel`** (`str`): Tên kênh nhận tin (ví dụ `"zalo"`, `"chatwoot"`, `"messenger"`).
* **`anh`** (`list[dict] | None`): Danh sách khối ảnh khách gửi kèm (đã tải và chuyển sang base64 hợp lệ).

### 4.3. Các Biến Trạng Thái & Lưới An Toàn Nội Bộ

* **`_BUOC_CHUYEN`** (`tuple[str, ...]`): Bộ từ khóa chốt chặn cứng (Hard Guardrails). Bất kỳ câu hỏi nào của khách chạm vào các chủ đề này (mang thai, con nhỏ, mụn viêm, thuốc kê đơn, cam kết khỏi bệnh 100%) đều bị buộc chuyển giao nhân viên ngay lập tức, không để model tự xử lý.
* **`_CHAN_DOAN_RE`** (`re.Pattern`): Regex lưới thứ sáu soi đầu ra câu trả lời của model, phát hiện và ngăn chặn hành vi tự ý chẩn đoán tên bệnh da liễu cho khách.
* **`_STALL_RE`** (`re.Pattern`): Regex bắt lỗi "hứa suông mà không làm" (model viết "để em kiểm tra giá nha" rồi dừng lại mà không gọi tool).
* **`_HANDOFF_RE`**, **`_HANDOFF_HINTS`**: Regex và từ khoá bắt lỗi "hứa chuyển người nhưng quên gọi tool".
* **`used_tool`** (`bool`): Cờ đánh dấu model đã thực hiện ít nhất một lời gọi công cụ trong lượt hay chưa.
* **`co_du_lieu`** (`bool`): Cờ đánh dấu công cụ có **thực sự trả về dữ liệu nghiệp vụ có ý nghĩa** hay không (khác với việc gọi tool nhưng trả về rỗng).
* **`da_thuc`** (`bool`): Cờ ngăn chặn vòng lặp vô tận khi ép model gọi công cụ (chỉ nhắc nhở model tối đa 1 lần).
* **`MAX_TOOL_ROUNDS`** (`int`, mặc định `4`): Số vòng lặp tối đa giữa agent và các công cụ trong một lượt tương tác.

---

## 5. Mô Hình Ngôn Ngữ & LLM Interface (`agent/core/llm.py`)

* **`LLMResult`** (`dataclass`): Đối tượng đóng gói kết quả gọi LLM độc lập với nhà cung cấp:
  * `text`: Nội dung văn bản model sinh ra.
  * `model`: Tên mô hình đã thực thi.
  * `tokens_in`, `tokens_out`: Số lượng token tiêu thụ.
  * `cache_read`, `cache_write`: Thống kê đọc/ghi bộ nhớ đệm prompt.
  * `cost_usd`: Chi phí ước tính theo bảng giá niêm yết.
  * `latency_ms`: Thời gian xử lý mạng và sinh token.
  * `tool_calls`: Danh sách công cụ model yêu cầu gọi (`[{"id": ..., "name": ..., "input": ...}]`).
  * `stop_reason`: Lý do dừng sinh (`"end_turn"`, `"tool_use"`, `"max_tokens"`).
* **`PRICING`** (`dict`): Bảng giá niêm yết (USD trên 1 triệu token) cho từng model.
* **`MAX_RETRIES`** (`int`, `4`): Số lần thử lại khi gặp mã lỗi tạm thời (`429`, `500`, `502`, `503`, `504`).
* **`CACHE_READ_RATE`** (`0.10`), **`CACHE_WRITE_RATE`** (`1.25`): Tỷ lệ nhân đơn giá cho token bộ nhớ đệm prompt của Claude.

---

## 6. Cơ Sở Tri Thức & RAG (`agent/core/rag.py`)

* **`EMBED_MODEL`** (`str`, `"text-multilingual-embedding-002"`): Tên mô hình tạo vector nhúng đa ngôn ngữ 768 chiều của Google Vertex AI.
* **`EMBED_DIM`** (`int`, `768`): Số chiều của vector nhúng, khớp với kiểu `vector(768)` trong PostgreSQL pgvector.
* **`Passage`** (`dataclass`): Một đoạn tri thức tìm được từ kho tài liệu:
  * `doc_title` (`str`): Tên file tài liệu gốc (ví dụ `chinh-sach-doi-tra.md`).
  * `content` (`str`): Nội dung đoạn văn bản được trích xuất.
  * `score` (`float`): Điểm số khớp tương đồng (từ tìm kiếm vector hoặc xếp hạng kết hợp RRF).
  * `cite()`: Hàm tạo chuỗi trích dẫn chuẩn hóa `[tên_tài_liệu]`.
* **`_LAN_THU_EMBED`** (`5`), **`_CHO_DAU_GIAY`** (`15.0`): Tham số hàm mũ chờ (exponential backoff) khi Vertex AI Embedding bị dính hạn mức rate limit 429.

---

## 7. Công Cụ Nghiệp Vụ & Tham Số Tool (`agent/core/tools.py`)

Mọi thông tin về giá bán, tồn kho, thành phần sản phẩm và đơn hàng **bắt buộc phải lấy từ đây**, model tuyệt đối không được tự bịa.

### 7.1. Danh Sách Các Công Cụ & Tham Số Đầu Vào

#### 1. `tim_kien_thuc`
* Tra cứu chính sách, bảo hành, thành phần, cách chăm sóc da trong kho tài liệu.
* **`cau_hoi`** (`str`): Câu hỏi tra cứu ngắn gọn, đã được diễn đạt lại (ví dụ: `"đổi trả hàng đã mở nắp"`).

#### 2. `tra_cuu_san_pham`
* Tra cứu giá tiền, dung tích, tồn kho và công dụng của một sản phẩm.
* **`ten_san_pham`** (`str`): Tên hoặc mã của sản phẩm khách nhắc tới (ví dụ: `"Serum B5"`, `"AS-SR01"`).

#### 3. `goi_y_san_pham`
* Lọc danh mục sản phẩm theo nhu cầu của khách hàng.
* **`loai_da`** (`str`, tuỳ chọn): Loại da (`"da dầu"`, `"da khô"`, `"da hỗn hợp"`, `"da nhạy cảm"`, `"da thường"`).
* **`nhu_cau`** (`str`, tuỳ chọn): Nhu cầu điều trị (`"cấp ẩm"`, `"kiềm dầu"`, `"đều màu da"`, `"chống lão hoá"`).
* **`nhom`** (`str`, tuỳ chọn): Nhóm sản phẩm (`"Làm sạch"`, `"Dưỡng ẩm"`, `"Chống nắng"`...).
* **`gia_toi_da`** (`int`, tuỳ chọn): Ngân sách tối đa cho một sản phẩm (VND).

#### 4. `gui_anh_san_pham`
* Gửi hình ảnh thực tế của sản phẩm cho khách.
* **`ten_san_pham`** (`str`): Tên hoặc mã sản phẩm cần gửi ảnh.

#### 5. `tra_cuu_don_hang`
* Tra cứu tiến độ đơn hàng.
* **`ma_don`** (`str`, tuỳ chọn): Mã đơn hàng cần tra. Nếu để trống, hệ thống tự động tìm đơn gần nhất của khách trong cuộc trò chuyện.

#### 6. `tra_cuu_van_chuyen`
* Tra cứu hành trình giao nhận thực tế từ hãng vận chuyển.
* **`ma_don`** (`str`, tuỳ chọn): Mã đơn hàng cần kiểm tra vận đơn.

#### 7. `xin_huy_don`
* Tiếp nhận yêu cầu muốn huỷ đơn của khách và chuyển cho nhân viên xử lý (không trực tiếp huỷ ngay).
* **`ma_don`** (`str`): Mã đơn hàng muốn huỷ.
* **`ly_do`** (`str`): Lý do khách muốn huỷ hàng.

#### 8. `xin_doi_tra`
* Tiếp nhận yêu cầu đổi hoặc trả hàng sau khi khách đã nhận bưu phẩm.
* **`ma_don`** (`str`): Mã đơn hàng.
* **`loai`** (`str`): `"doi"` (đổi mẫu/size khác) hoặc `"tra"` (trả hàng hoàn tiền).
* **`ly_do`** (`str`): Lý do đổi trả khách cung cấp.

#### 9. `tao_video`
* Đặt hàng hệ thống tạo video marketing cho sản phẩm.
* **`tieu_de`** (`str`): Tiêu đề ngắn gọn cho video.
* **`yeu_cau`** (`str`): Mô tả kịch bản nội dung cần làm.
* **`loai`** (`str`): `"explainer"` (giải thích chuyên sâu) hoặc `"product"` (giới thiệu sản phẩm).
* **`thoi_luong_giay`** (`int`, tuỳ chọn): Độ dài video mong muốn.
* **`ma_san_pham`** (`str`, tuỳ chọn): Mã sản phẩm để hệ thống tự lấy ảnh trong kho.

#### 10. `tao_don_hang`
* Lên đơn hàng mới cho khách (công cụ duy nhất có hiệu ứng không thể đảo ngược).
* **`items`** (`list[dict]`): Danh sách sản phẩm, mỗi phần tử gồm:
  * `ten_san_pham` (`str`): Tên hoặc mã hàng.
  * `so_luong` (`int`): Số lượng đặt mua (>= 1).
* **`khach_ten`** (`str`): Họ tên người nhận hàng.
* **`khach_sdt`** (`str`): Số điện thoại liên hệ giao hàng (tối thiểu 9 chữ số).
* **`khach_dia_chi`** (`str`): Địa chỉ giao hàng đầy đủ (tối thiểu 12 ký tự).
* **`khach_da_xac_nhan`** (`bool`): Chỉ được đặt `True` khi khách đã nói rõ lời xác nhận đồng ý đặt mua đơn hàng.
* **`ghi_chu`** (`str`, tuỳ chọn): Ghi chú dặn dò khi đóng gói hoặc giao hàng.

#### 11. `chuyen_nhan_vien`
* Chủ động bàn giao cuộc trò chuyện cho nhân viên chăm sóc khách hàng trực tiếp.
* **`ly_do`** (`str`): Lý do chi tiết cần người hỗ trợ.
* **`muc_do`** (`str`, `"thuong"` hoặc `"gap"`): Mức độ khẩn cấp của yêu cầu.

### 7.2. Các Biến Nội Bộ Quan Trọng Khi Lên Đơn Hàng (`_tao_don_hang`)

* **`thieu`** (`list[str]`): Danh sách các trường giao hàng còn thiếu (nếu có trường thiếu, hàm dừng ngay và yêu cầu hỏi khách).
* **`ranked`** (`list[tuple[float, dict]]`): Danh sách sản phẩm trong kho được chấm điểm tương đồng với tên khách gõ.
* **`ton_song`** (`TonKho | None`): Tồn kho đọc trực tiếp từ nguồn ERP/CSDL, bỏ qua cache để đảm bảo không bị bán khống món vừa hết.
* **`ton`** (`int`): Số lượng thực tế bán được (`ton_song.ban_duoc`).
* **`thanh_tien`** (`int`): Giá trị của một dòng hàng = đơn giá danh mục × số lượng.
* **`tong`** (`int`): Tổng giá trị toàn bộ đơn hàng (VND).
* **`tu_chot`** (`bool`): Cờ boolean kiểm tra đơn có đủ điều kiện tự động chốt hay không (`tong < settings.nguong_tu_chot_vnd`).
* **`trang_thai`** (`str`): Trạng thái gán cho đơn (`"da_chot"` nếu `tu_chot` là True, ngược lại là `"cho_duyet"`).
* **`ma_don`** (`str`): Mã đơn hàng được sinh tự động theo định dạng `"AS" + YYMMDDHHMMSS` (ví dụ `"AS260904123000"`).
* **`TRANG_THAI_DON`** (`tuple[str, ...]`): Tập hợp 5 trạng thái duy nhất của một đơn hàng:
  * `"cho_duyet"`: Đơn hàng vượt ngưỡng tiền, đang chờ quản lý bấm xác nhận.
  * `"da_chot"`: Đơn hàng trong hạn mức đã được agent xác nhận thành công.
  * `"cho_dong_bo"`: Đơn đã lưu ở CSDL nội bộ nhưng chưa đẩy thành công vào ERP.
  * `"da_giao"`: Hãng vận chuyển xác nhận đã phát hàng thành công tới khách.
  * `"da_huy"`: Đơn bị nhân viên huỷ hoặc ERP từ chối.

---

## 8. Kho Hàng & Biến Động Tồn Kho (`agent/core/kho.py`)

* **`NGUONG_SAP_HET`** (`int`, `10`): Ngưỡng số lượng tồn kho tối thiểu; dưới mức này hệ thống sẽ hiển thị cảnh báo sắp hết hàng trên dashboard.
* **`ma`** (`str`): Mã định danh duy nhất của sản phẩm (SKU, ví dụ `"AS-SR01"`).
* **`so_luong`** (`int`): Số lượng sản phẩm hiện vật đang còn trong kho.
* **`thay_doi`** (`int`): Số lượng tăng hoặc giảm trong sổ biến động kho (âm là xuất kho, dương là nhập kho).
* **`ly_do`** (`str`): Nguyên nhân phát sinh biến động kho (`"ban"`, `"huy_don"`, `"nhap"`, `"kiem_ke"`).
* **`giu_hang(items, ma_don)`**: Hàm trừ kho nguyên tử (atomic transaction) có khóa `SELECT ... FOR UPDATE` để ngăn chặn hai khách cùng chốt đơn món hàng cuối cùng trong cùng một giây.

---

## 9. Cổng Tích Hợp Kho & ERP (`agent/erp/`)

Định nghĩa hợp đồng dữ liệu cách ly logic agent khỏi phần mềm ERP cụ thể (Odoo, ERPNext, KiotViet).

* **`Gia`** (`dataclass`):
  * `gia_ban` (`int`): Đơn giá bán của sản phẩm.
  * `don_vi` (`str`, mặc định `"VND"`): Đơn vị tiền tệ.
  * `nguon` (`str`): Tên bảng giá hoặc xuất xứ giá để phục vụ truy vết.
  * `hieu_luc_den` (`str | None`): Hạn sử dụng của mức giá ưu đãi.
* **`TonKho`** (`dataclass`):
  * `ban_duoc` (`int`): Số lượng hàng **khả dụng thực tế để bán** (`free_qty`), đã trừ hàng bị giữ chân bởi các đơn chưa giao.
  * `ma_kho` (`str`): Mã định danh kho chứa hàng.
* **`SanPhamERP`** (`dataclass`):
  * `ma` (`str`): Mã SKU sản phẩm trên ERP.
  * `ten` (`str`): Tên gọi sản phẩm.
  * `dung_tich` (`str`): Dung tích đóng gói (ví dụ `"30ml"`).
  * `ban_duoc_phep` (`bool`): Cờ cho biết sản phẩm có đang được phép kinh doanh hay không.
* **`DongDon`** (`dataclass`): Một dòng chi tiết hàng hóa gửi sang ERP (`ma`, `so_luong`, `don_gia`).
* **`KetQuaDon`** (`dataclass`):
  * `thanh_cong` (`bool`): Trạng thái ghi đơn vào ERP có hoàn tất hay không.
  * `erp_ma_don` (`str`): Mã đơn hàng sinh ra trên hệ thống ERP (ví dụ `"SO-2026-0001"`).
  * `ly_do` (`str`): Thông điệp phản hồi hoặc nguyên nhân nếu ERP từ chối nhận đơn.
* **`_cong`** (`Cong | None`): Đối tượng Singleton của cổng ERP Gate, bao bọc cơ chế bộ nhớ đệm (cache) và bộ ngắt mạch (Circuit Breaker).
* **`LoiERP`**, **`TuChoiERP`**: Hai lớp ngoại lệ phân biệt lỗi kỹ thuật tạm thời (mất mạng, 500 -> cần thử lại) và lỗi nghiệp vụ bị từ chối thẳng thừng (hết hàng, khoá mã -> không thử lại).

---

## 10. Vận Chuyển & Giao Hàng (`agent/shipping/`)

* **`ma_van_don`** (`str`): Mã theo dõi của bưu phẩm do hãng vận chuyển cấp (Waybill Code / Tracking Code).
* **`don_vi_van_chuyen`** (`str`): Tên đối tác vận chuyển (`"ghn"`, `"ghtk"`, `"mock"`).
* **`trang_thai_giao_hang`** (`str`): Trạng thái chuẩn hóa của đơn giao nhận:
  * `"pending_pickup"`: Đang chờ hãng vận chuyển tới lấy hàng.
  * `"delivering"`: Hàng đang trên đường giao tới tay khách.
  * `"delivered"`: Đã giao hàng thành công.
  * `"delivery_failed"`: Giao hàng không thành công.
  * `"returned"`: Hàng đã chuyển hoàn trả về kho shop.
  * `"cancelled"`: Vận đơn đã bị huỷ.
* **`phi_van_chuyen`** (`int`): Tiền cước vận chuyển (VND).
* **`lich_su_giao_hang`** (`list[dict]`): Mảng các mốc thời gian và địa điểm hành trình bưu phẩm.
* **`ngay_du_kien_giao`** (`datetime`): Ngày dự kiến khách sẽ nhận được bưu phẩm.
* **`CreateWaybillRequest`** (`dataclass`): Gói dữ liệu yêu cầu tạo vận đơn gửi sang bưu cục (chứa `order_code`, `recipient_name`, `recipient_phone`, `recipient_address`, `cod_amount`, `weight_grams`, `items`).

---

## 11. Trí Nhớ Khách Hàng & Bảo Vệ Dữ Liệu (`agent/core/ho_so_khach.py`, `du_lieu_ca_nhan.py`)

### 11.1. Hồ Sơ Khách Hàng (`ho_so_khach`)

* **`customer_ref`** (`str`): ID duy nhất đại diện cho khách hàng trên kênh nhắn tin.
* **`ghi_nho`** (`list[dict]`): Danh sách các mẩu thông tin đã ghi nhớ về khách. Mỗi mẩu có cấu trúc:
  * `kieu`: Loại mẩu nhớ (ví dụ `"loai_da"`, `"da_mua"`, `"di_ung"`).
  * `gia_tri`: Nội dung chi tiết (ví dụ `"da dầu thiếu nước"`, `"AS-SR01"`).
  * `nguon`: Nguồn gốc xuất xứ của thông tin:
    * `"hanh_dong"`: Rút ra từ việc agent gọi tool thành công (cực kỳ đáng tin).
    * `"don_hang"`: Rút ra từ đơn hàng khách đã mua.
    * `"khach_noi"`: Quét trực tiếp từ văn bản khách gõ (khách tự nhận).
    * `"agent_ghi"`: Agent tự ghi chép (ít chắc chắn hơn).
  * `luc`: Thời điểm ghi nhận thông tin.
* **`SO_GHI_NHO_TOI_DA`** (`int`, `8`): Số lượng mẩu ghi nhớ tối đa được chèn vào ngữ cảnh để tránh làm loãng prompt.
* **`_TU_KHOA_DA`** (`tuple[str, ...]`): Bộ từ điển nhận diện loại da được trích xuất tự động từ file danh mục sản phẩm.

### 11.2. Bảo Vệ Dữ Liệu Cá Nhân (Nghị Định 13/2023/NĐ-CP)

* **`AN_DANH`** (`str`, `"[đã ẩn danh theo yêu cầu]"`): Chuỗi thay thế tên, số điện thoại, địa chỉ trên đơn hàng khi khách hàng yêu cầu thực hiện quyền được xoá dữ liệu cá nhân (đơn hàng vẫn phải lưu để tuân thủ Luật Kế toán).
* **`_dau_van_tay`** (`str`): Chuỗi băm SHA-256 (16 ký tự đầu) của số điện thoại, dùng để ghi log chứng minh đã thực thi quyền xoá dữ liệu mà không làm lộ lại số điện thoại thật vào log.
* **`chuan_hoa_sdt`** (`str`): Hàm chuyển đổi mọi định dạng số điện thoại (`+84`, `84.`, có dấu cách) về dạng chuẩn số `0...` thống nhất.

---

## 12. An Ninh, Phòng Thủ & Tự Nhiên Hoá (`phong_thu.py`, `tu_nhien.py`, `gio_lam_viec.py`)

### 12.1. Phòng Thủ Prompt Injection (`phong_thu.py`)

* **`RAO_MO`** (`"<<<TIN_NHAN_KHACH>>>"`), **`RAO_DONG`** (`"<<<HET_TIN_NHAN_KHACH>>>"`): Cặp thẻ rào cách ly tin nhắn của khách trước khi đưa vào mô hình AI.
* **`NHAC`** (`str`): Đoạn chỉ dẫn đi kèm thẻ rào, nhắc model coi nội dung bên trong là **dữ liệu thuần túy**, không phải là mệnh lệnh điều khiển hệ thống.
* **`_MAU`** / **`_DA_DICH`**: Danh sách các biểu thức chính quy (regex) nhận diện các câu lệnh tấn công điển hình (bỏ qua hướng dẫn, đòi in system prompt, đổi vai, jailbreak, giả danh admin).

### 12.2. Tự Nhiên Hóa Câu Trả Lời (`tu_nhien.py`)

* **`DAI_TOI_DA`** (`int`, `180` ký tự): Độ dài tối đa của một tin nhắn đơn lẻ. Dài hơn sẽ tự động tách đoạn.
* **`NGAN_TOI_THIEU`** (`int`, `40` ký tự): Độ dài tối thiểu; đoạn quá ngắn sẽ được gộp lại để tránh nhắn tin nhát gừng.
* **`SO_TIN_TOI_DA`** (`int`, `3` tin): Số tin nhắn tối đa được tách ra từ một câu trả lời của agent.
* **`_CHAO`**, **`_KET_SAO_RONG`**, **`_MO_SAO_RONG`**, **`_GACH_DAU_DONG`**, **`_DAM_MD`**: Các mẫu regex tìm và lọc bỏ những dấu hiệu làm "lộ máy" (chào lại lần 2, câu kết sáo rỗng, gạch đầu dòng markdown trong chat Zalo).
* **`nhip_go(text)`**: Hàm tính toán số giây delay hợp lý trước khi gửi tin để tạo cảm giác người thật đang gõ máy tính.

---

## 13. Kênh Tiếp Nhận & Đa Kênh (`agent/channels/`, `agent/omnichannel/`)

### 13.1. Đối Tượng Tin Nhắn Đến `InboundMessage`

* **`account_id`** (`uuid.UUID`): ID tài khoản kênh phụ trách nhận/gửi (để khi reply sẽ đi ra đúng nick Zalo/Fanpage mà khách đã nhắn vào).
* **`channel`** (`str`): Tên kênh tiếp nhận (`"zalocrm"`, `"chatwoot"`, `"messenger"`, `"zalo_oa"`).
* **`conversation_ref`** (`str`): Mã định danh phòng chat phía kênh gốc.
* **`customer_ref`** (`str`): Mã định danh khách hàng phía kênh gốc.
* **`customer_name`** (`str`): Tên hiển thị của khách.
* **`text`** (`str`): Nội dung chữ của tin nhắn.
* **`dedupe_key`** (`str`): Khóa chống trùng lặp tin nhắn (idempotency key), ngăn việc một tin nhắn webhook bị xử lý hai lần.
* **`received_at`** (`datetime`): Thời điểm nhận được tin nhắn.
* **`attachments`** (`list[dict]`): Danh sách tệp đính kèm (ảnh, video, audio).
* **`meta`** (`dict`): Dữ liệu bổ sung riêng của từng kênh (ví dụ nền tảng gốc `nen_tang`).

### 13.2. Hàng Đợi Gửi Tin (Outbox Pattern) & Định Tuyến (Routing)

* **`outbox_messages`**: Bảng lưu trữ tạm thời các tin nhắn cần gửi ra ngoài cho khách:
  * `id`: UUID tin gửi.
  * `idempotency_key`: Khóa chống gửi trùng tin nhắn.
  * `retry_count`: Số lần đã thử gửi lại khi gặp lỗi mạng.
  * `next_retry_at`: Thời điểm được phép thử gửi tiếp theo.
  * `dead_letter_reason`: Lý do tin bị đưa vào hàng đợi chết (nếu gửi hỏng quá số lần cho phép).
* **`routing_rules`**: Quy tắc tự động phân công hội thoại cho nhân viên trực theo kênh, từ khóa hoặc kỹ năng.
* **`sla_policies`**: Chính sách cam kết thời gian phản hồi tin nhắn của khách (SLA).

---

## 14. Canh Gác & Sức Khoẻ Hệ Thống (`agent/canh_gac.py`, `agent/suc_khoe.py`)

* **`TOT`** (`"tot"`), **`CANH_BAO`** (`"canh_bao"`), **`HONG`** (`"hong"`): Ba mức đánh giá sức khoẻ cho từng thành phần (CSDL, LLM, kênh nhắn tin, giọng đọc, sao lưu, ERP, vận chuyển).
* **`_truoc`** (`str | None`): Trạng thái sức khoẻ của toàn hệ thống ở lần kiểm tra trước đó (chỉ phát chuông báo động khi trạng thái chuyển từ `tot` sang `hong`, hoặc phục hồi từ `hong` về `tot`).
* **`_cho_truoc`** (`bool`): Cờ riêng theo dõi trạng thái "có khách đang bị bỏ quên" (chờ nhân viên quá `cho_nguoi_toi_da_phut`).
* **`MUC_KHACH_CHO`** (`str`, `"Khách chờ người"`): Tên chỉ mục kiểm tra thời gian chờ của khách hàng.
* **`dung_goi_bao_dong(truong, mau)`**: Hàm định dạng gói tin gửi tới webhook báo động (hỗ trợ chuyển đổi sang template Telegram, Lark, Slack).

---

## 15. Lược Đồ Cơ Sở Dữ Liệu PostgreSQL (`agent/schema.sql`)

Dưới đây là các cột quan trọng nhất trong các bảng CSDL cốt lõi:

### 15.1. Bảng `conversations` (Hội thoại)
* `id` (`UUID`): Khóa chính của cuộc hội thoại.
* `channel` (`TEXT`): Kênh tiếp nhận (`"zalocrm"`, `"chatwoot"`...).
* `nen_tang` (`TEXT`): Nền tảng gốc (`"facebook"`, `"instagram"`, `"whatsapp"`, `"zalo"`).
* `external_id` (`TEXT`): ID hội thoại phía kênh đối tác.
* `customer_name` (`TEXT`): Tên khách hàng.
* `customer_ref` (`TEXT`): Mã định danh khách hàng.
* `status` (`TEXT`): Trạng thái xử lý (`"auto"`: agent tự chạy, `"assist"`: chờ người duyệt, `"escalated"`: đã chuyển người trực, `"closed"`: đã đóng).
* `cost_usd` (`NUMERIC`): Tổng chi phí LLM tích luỹ của hội thoại.
* `msg_count` (`INT`): Tổng số tin nhắn trong cuộc hội thoại.

### 15.2. Bảng `messages` (Tin nhắn)
* `id` (`UUID`): Khóa chính tin nhắn.
* `conversation_id` (`UUID`): ID hội thoại chứa tin nhắn này.
* `role` (`TEXT`): Vai trò người gửi (`"customer"`, `"agent"`, `"staff"`, `"system"`).
* `content` (`TEXT`): Nội dung tin nhắn.
* `delivered` (`BOOLEAN`): Đã thực sự gửi tới khách hay chưa (ở chế độ assist, tin soạn sẵn sẽ có `delivered = false`).
* `grounded` (`BOOLEAN`): Câu trả lời có nguồn xác thực hay không.
* `confidence` (`REAL`): Điểm tin cậy của câu trả lời.
* `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms`: Thông số kỹ thuật của lời gọi AI.
* `attachments` (`JSONB`): Danh sách tệp, hình ảnh đính kèm tin nhắn.

### 15.3. Bảng `orders` (Đơn hàng)
* `id` (`UUID`): Khóa chính đơn hàng.
* `ma_don` (`TEXT UNIQUE`): Mã đơn hàng nội bộ (ví dụ `"AS2609041000"`).
* `khach_ten`, `khach_sdt`, `khach_dia_chi` (`TEXT`): Thông tin giao hàng nhận từ khách.
* `items` (`JSONB`): Mảng chi tiết các mặt hàng mua, số lượng, đơn giá, thành tiền.
* `tong_tien` (`BIGINT`): Tổng số tiền thanh toán (VND).
* `trang_thai` (`TEXT`): Trạng thái đơn (`"cho_duyet"`, `"da_chot"`, `"cho_dong_bo"`, `"da_giao"`, `"da_huy"`).
* `tao_boi` (`TEXT`): Ai lên đơn (`"agent"` hoặc `"staff"`).
* `yeu_cau_huy_luc`, `yeu_cau_huy_ly_do`: Cờ và lý do khi khách gửi yêu cầu muốn huỷ đơn.
* `ma_van_don`, `don_vi_van_chuyen`, `trang_thai_giao_hang`: Thông tin theo dõi bưu kiện vận chuyển.
* `erp_order_id`, `erp_provider`: Mã đơn và tên hệ thống ERP đồng bộ phía sau.

### 15.4. Bảng `ton_kho` & `kho_bien_dong`
* `ton_kho.ma` (`TEXT PRIMARY KEY`): Mã SKU sản phẩm.
* `ton_kho.so_luong` (`INT`): Số lượng tồn thực tế trong kho.
* `kho_bien_dong.thay_doi` (`INT`): Số lượng biến động (âm: xuất kho, dương: nhập kho).
* `kho_bien_dong.ly_do` (`TEXT`): Lý do biến động (`"ban"`, `"huy_don"`, `"nhap"`).
* `kho_bien_dong.ma_don` (`TEXT`): Mã đơn hàng liên quan đến biến động này.

### 15.5. Bảng `ho_so_khach` (Trí nhớ khách hàng)
* `customer_ref`, `channel`: Cặp khóa xác định khách hàng.
* `ten`, `sdt`: Thông tin liên hệ cơ bản.
* `ghi_nho` (`JSONB`): Mảng các mẩu sự thật đã ghi nhớ về khách.
* `lan_dau`, `lan_cuoi` (`TIMESTAMPTZ`): Thời điểm trò chuyện đầu tiên và gần nhất.

### 15.6. Bảng `nguoi_dung` & `phien` (Tài khoản dashboard)
* `ten_dang_nhap`, `mat_khau_bam`: Tên đăng nhập và mật khẩu băm chuẩn scrypt.
* `vai_tro` (`TEXT`): Quyền hạn tài khoản (`"quan_tri"` hoặc `"nhan_vien"`).
* `phien.token`: Token phiên đăng nhập lưu trong database (có thể thu hồi ngay lập tức).

---

## 16. Sản Xuất Video & Đăng Bài Tự Động (`agent/video/`, `agent/publish/`)

* **`videos.status`**: Vòng đời của video marketing trong pipeline:
  * `"queued"` -> `"claimed"` -> `"looking"` (phân tích ảnh sản phẩm) -> `"scripting"` (soạn kịch bản) -> `"voicing"` (thu âm giọng đọc TTS) -> `"rendering"` (dựng khung hình) -> `"pending_review"` (chờ người duyệt) -> `"ready"` (sẵn sàng đăng).
* **`posts.trang_thai`**: Vòng đời của bài đăng mạng xã hội:
  * `"nhap"` -> `"cho_duyet"` -> `"da_len_lich"` -> `"dang_dang"` -> `"da_dang"` -> `"loi"` / `"da_huy"`.
* **`post_metrics`**: Bảng thống kê hiệu quả của bài đăng phục vụ vòng lặp phản hồi cải thiện nội dung (`luot_xem`, `luot_thich`, `binh_luan`, `chia_se`, `luot_click`).

---

## Lời Khuyên Khi Đọc Mã Nguồn

1. **Bắt đầu từ `agent/core/agent.py`:** Đây là trung tâm điều phối. Đọc hàm `respond()` để nắm cách một tin nhắn đi qua các bộ lọc phòng thủ, tra RAG, chạy vòng lặp gọi tool và đi qua 6 lớp lưới kiểm duyệt an toàn.
2. **Khi gặp biến lạ về nghiệp vụ:** Tra cứu tại **Mục 2** (Bảng đối chiếu nhanh) hoặc **Mục 7** (Công cụ nghiệp vụ).
3. **Khi cần kiểm tra cấu hình hoặc cờ an toàn:** Tra cứu tại **Mục 3** (`agent/config.py`).
4. **Khi cần tra cứu trường CSDL:** Tra cứu tại **Mục 15** (`agent/schema.sql`).
