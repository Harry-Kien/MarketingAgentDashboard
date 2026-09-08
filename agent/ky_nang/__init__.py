"""
Sổ đăng ký kỹ năng (skill) của agent, và cơ chế thêm kỹ năng KHÔNG cần sửa mã.

Tám module:

  so_dang_ky.py   khai báo 11 công cụ viết sẵn: nhóm, mức rủi ro, tắt được không
  ban_mo_ta.py    kiểm bản mô tả plugin do người vận hành viết
  chay.py         thi hành plugin — năm loại; bốn loại đầu CHỈ ĐỌC, loại `mcp`
                  giao việc cho kho_mcp.py qua một nhánh riêng
  mang.py         gọi HTTP cho loại `goi_api_doc`, có bốn rào SSRF — đường ra
                  mạng THỨ NHẤT
  kho_ky_nang.py  đọc/ghi cài đặt bật-tắt, dựng lược đồ công cụ cho mỗi lượt
  goi.py          gói kỹ năng: hướng dẫn + công cụ + tài liệu + phiên bản
  kho_mcp.py      CSDL của loại `mcp`: máy chủ, bí mật, đồng bộ công cụ —
                  điểm neo DUY NHẤT gọi sang mcp_khach.py (Task 4 hoàn thiện)
  mcp_khach.py    gọi máy chủ MCP ngoài qua HTTP — đường ra mạng THỨ HAI, chỉ
                  được gọi TỪ kho_mcp.py, không nơi nào khác trong repo

Vì sao có lớp này: `TOOLS` trong `agent/core/tools.py` là một danh sách
phẳng, mô tả cho MODEL đọc. Nó không nói cho NGƯỜI biết công cụ nào nguy
hiểm, công cụ nào cần ERP, công cụ nào không được phép tắt. Người vận hành
cần biết những điều đó mới bật/tắt có trách nhiệm được.


BẢN ĐỒ LUỒNG — ĐỊA CHỈ DÙNG CHUNG CHO CẢ REPO
═════════════════════════════════════════════

Mỗi file trong chuỗi mở đầu bằng một khối `# ĐỌC:` nói nó là trạm nào. Địa
chỉ ấy quy về đúng bảng dưới đây, nên đọc một file bất kỳ là biết mình đang
đứng ở đâu, ai gọi tới và mình gọi đi đâu.

  CHẶNG A · CÀI — chạy MỘT LẦN, lúc người vận hành bấm Cài
    A1  dashboard/app.js                panel Gói kỹ năng, form Plugin
    A2  agent/api/goi_ky_nang.py        chặn quyền, chặn kích thước, dịch lỗi HTTP
    A3  goi.py  tu_zip → doc_goi        kiểm bản gói. Hàm THUẦN: không CSDL, không mạng
    A4  ban_mo_ta.py  doc_ban_mo_ta     kiểm từng công cụ trong gói
    A5  core/phong_thu.py + core/cham_mot_luot.py   quét injection, quét cụm cấm
    A6  goi.py  cai()                   sáu câu SQL theo thứ tự bất biến
    A7  core/rag.py  ingest             bước DUY NHẤT tốn tiền trong chặng này
    A8  kho_ky_nang.xoa_dem + goi.xoa_dem

  CHẶNG B · DỰNG NGỮ CẢNH — chạy ở MỌI tin nhắn của khách
    B1  agent/main.py  handle_inbound   lưu tin, COMMIT, rồi mới gọi lõi agent
    B2  core/agent.py  respond()        chặng 1–3: trần chi phí, quét, ngữ cảnh
    B3  goi.py  huong_dan_cho_luot      hướng dẫn — vào theo TỪ KHOÁ
    B4  kho_ky_nang.py  cong_cu_dang_bat  lược đồ — vào KHÔNG cần từ khoá
    B5  ban_mo_ta.py  thanh_cong_cu     bản mô tả → JSON Schema gửi mô hình

  CHẶNG C · VÒNG LẶP — tối đa MAX_TOOL_ROUNDS vòng
    C1  core/llm.py  complete()         dịch sang định dạng nhà cung cấp, gọi HTTP
    C2  core/tools.py  run_tool()       ghi số đo, rồi CHỐT THỨ HAI
    C3  kho_ky_nang.py  dang_tat / tim_plugin
    C4  chay.py  chay_plugin()          năm loại; bốn loại đầu CHỈ ĐỌC
    C5  mang.py  lay()                  chỉ với `goi_api_doc` — đường ra mạng THỨ NHẤT
    C6  kho_mcp.py  goi_cong_cu()       chỉ với `mcp`, tự gọi mcp_khach.py —
                                        đường ra mạng THỨ HAI. Nhánh mcp của
                                        chay_plugin() là cửa DUY NHẤT dẫn tới C6

MỘT GÓI ĐI VÀO MỘT LƯỢT BẰNG BA ĐƯỜNG RỜI NHAU, ĐÂY LÀ CHỖ HAY HIỂU NHẦM
NHẤT: hướng dẫn qua B3 (cần từ khoá khớp), công cụ qua B4 (chỉ cần gói đang
bật), tài liệu qua kho tri thức CHUNG ở B2 (mọi câu hỏi khớp ngữ nghĩa, kể
cả lượt không kích hoạt gói nào). Ba đường ấy hỏng theo ba kiểu khác nhau —
`python -m scripts.kiem_goi <ten-goi>` đi qua cả ba.

CHẶNG A KHÔNG NỐI VỚI CHẶNG B–C BẰNG MỘT LỜI GỌI HÀM NÀO. Cài xong không có
tiến trình nào khởi động lại, không mô-đun nào được nhập thêm: nó chỉ ghi ba
nơi rồi xoá hai bộ đệm, và lượt trả lời kế tiếp đọc lại từ CSDL. Ai đi tìm
"chỗ nạp plugin vào agent" sẽ không tìm thấy, vì không có chỗ ấy.
"""
from __future__ import annotations

from agent.ky_nang.ban_mo_ta import (
    LOAI_PLUGIN,
    LoiBanMoTa,
    BanMoTa,
    doc_ban_mo_ta,
    thanh_cong_cu,
)
from agent.ky_nang.so_dang_ky import (
    KHONG_TAT_DUOC,
    SO_DANG_KY,
    KyNang,
    khai_bao,
    ten_ky_nang_co_san,
)

__all__ = [
    "BanMoTa",
    "KHONG_TAT_DUOC",
    "KyNang",
    "LOAI_PLUGIN",
    "LoiBanMoTa",
    "SO_DANG_KY",
    "doc_ban_mo_ta",
    "khai_bao",
    "ten_ky_nang_co_san",
    "thanh_cong_cu",
]
