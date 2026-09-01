"""
Khung ngành MỸ PHẨM — rút ra từ kho tri thức đang chạy thật.

Đây không phải khung nghĩ ra trên giấy: 19 tài liệu trong `data/knowledge/`
đã qua bộ 56 câu vàng, và các mục dưới đây là những mục bộ đó thật sự chạm
tới. Ngành nào cũng nên bắt đầu bằng một khung có bằng chứng như vậy.
"""
from __future__ import annotations

from agent.tri_thuc.hop_dong import KhungNganh, Muc, TaiLieu

KHUNG = KhungNganh(
    ma="my_pham",
    ten="Mỹ phẩm chăm sóc da",
    mo_ta=(
        "Bán hàng có tư vấn, chạm ranh giới y tế và luật quảng cáo. "
        "Rủi ro lớn nhất không phải mất đơn — là nói một câu vượt thẩm quyền."
    ),
    van_ban_phap_ly=(
        "Thông tư 06/2011/TT-BYT — quản lý mỹ phẩm",
        "Nghị định 181/2013/NĐ-CP — hướng dẫn thi hành Luật Quảng cáo",
        "Nghị định 13/2023/NĐ-CP — bảo vệ dữ liệu cá nhân",
    ),
    cum_cam_goi_y=(
        "trị mụn", "đặc trị", "chữa khỏi", "trị nám", "xoá nhăn",
        "hết mụn", "tái tạo da", "thay thế thuốc", "cam kết khỏi",
        "hiệu quả 100%", "số 1 Việt Nam", "tốt nhất thị trường",
    ),
    tai_lieu=(
        TaiLieu(
            ten_tep="an-toan-va-chong-chi-dinh.md",
            tieu_de="An toàn và chống chỉ định",
            vi_sao=(
                "Tài liệu quan trọng nhất trong kho. Nó là căn cứ cho ranh "
                "giới y tế — chỗ agent phải dừng lại và gọi người. Thiếu nó "
                "thì agent vẫn chặn được bằng từ khoá, nhưng mất khả năng "
                "giải thích đúng cho khách vì sao phải chờ nhân viên."
            ),
            muc=(
                Muc("Ai không nên tự dùng", (
                    "Nhóm khách nào cửa hàng KHÔNG tự tư vấn mà luôn chuyển người?",
                    "Với khách đang mang thai hoặc cho con bú, câu trả lời chuẩn là gì?",
                    "Trẻ em từ bao nhiêu tuổi thì cửa hàng mới tư vấn?",
                )),
                Muc("Tình trạng da phải chuyển chuyên môn", (
                    "Những biểu hiện nào trên da là dấu hiệu phải đi khám, không phải mua mỹ phẩm?",
                    "Khách đang dùng thuốc theo toa thì xử lý thế nào?",
                )),
                Muc("Câu tuyệt đối không được nói", (
                    "Cửa hàng cấm nhân viên nói những cụm nào khi tư vấn?",
                    "Vì sao mỗi cụm đó bị cấm — dựa trên văn bản nào?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="chinh-sach-thuong-mai.md",
            tieu_de="Chính sách thương mại",
            vi_sao=(
                "Phần khách hỏi nhiều nhất và cũng là phần agent dễ hứa sai "
                "nhất. Mỗi con số ở đây là một cam kết pháp lý với khách."
            ),
            muc=(
                Muc("Đổi trả", (
                    "Được đổi trả trong bao nhiêu ngày, tính từ mốc nào?",
                    "Hàng đã mở nắp có được trả không?",
                    "Ai chịu phí vận chuyển chiều trả?",
                )),
                Muc("Vận chuyển và thanh toán", (
                    "Phí ship từng khu vực là bao nhiêu?",
                    "Đơn từ bao nhiêu tiền thì miễn phí ship?",
                    "Nhận những hình thức thanh toán nào?",
                )),
                Muc("Hoá đơn và bảo hành", (
                    "Xuất hoá đơn VAT cần khách cung cấp gì?",
                    "Cam kết chất lượng của cửa hàng là gì, khác gì với 'cam kết khỏi bệnh'?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="chon-san-pham-theo-loai-da.md",
            tieu_de="Chọn sản phẩm theo loại da",
            vi_sao=(
                "Đây là chất tư vấn — thứ ERP không bao giờ cấp được. Không "
                "có nó, agent chỉ đọc được giá và tồn kho."
            ),
            muc=(
                Muc("Nhận biết loại da", (
                    "Cửa hàng phân loại da thành mấy nhóm, gọi tên thế nào?",
                    "Hỏi khách câu nào để biết họ thuộc nhóm nào mà không cần nhìn da?",
                )),
                Muc("Ưu tiên theo từng nhóm", (
                    "Mỗi loại da nên bắt đầu bằng nhóm sản phẩm nào?",
                    "Loại da nào cần tránh thành phần gì?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="ket-hop-hoat-chat.md",
            tieu_de="Kết hợp hoạt chất",
            vi_sao=(
                "Khách tự phối sai hoạt chất là nguyên nhân phổ biến nhất "
                "gây kích ứng — tức là một khiếu nại và một khách mất niềm tin."
            ),
            muc=(
                Muc("Cặp không dùng chung", (
                    "Những hoạt chất nào cửa hàng khuyên không dùng cùng lúc?",
                    "Nếu khách vẫn muốn dùng cả hai thì hướng dẫn thế nào?",
                )),
                Muc("Thứ tự và tần suất", (
                    "Thứ tự thoa các bước là gì?",
                    "Hoạt chất mạnh nên bắt đầu với tần suất nào?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="khieu-nai-va-su-co-sau-ban.md",
            tieu_de="Khiếu nại và sự cố sau bán",
            vi_sao=(
                "Lúc khách bức xúc là lúc dễ nói sai nhất. Có kịch bản sẵn "
                "thì agent không phải ứng biến ở đúng chỗ không nên ứng biến."
            ),
            muc=(
                Muc("Khách phản ứng với sản phẩm", (
                    "Khách báo da bị kích ứng thì bước đầu tiên là gì?",
                    "Trường hợp nào cửa hàng hoàn tiền, trường hợp nào đổi hàng?",
                )),
                Muc("Giao sai, thiếu, vỡ", (
                    "Khách cần cung cấp bằng chứng gì?",
                    "Trong bao lâu cửa hàng xử lý xong?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="du-lieu-ca-nhan-va-quyen-cua-khach.md",
            tieu_de="Dữ liệu cá nhân và quyền của khách",
            vi_sao=(
                "Nghị định 13/2023 cho khách quyền yêu cầu xoá dữ liệu. "
                "Agent phải biết trả lời đúng khi khách hỏi, và biết chuyển "
                "cho người khi khách yêu cầu thực hiện quyền đó."
            ),
            muc=(
                Muc("Cửa hàng lưu gì", (
                    "Những thông tin nào của khách được lưu, và để làm gì?",
                    "Lưu trong bao lâu?",
                )),
                Muc("Khách yêu cầu xoá", (
                    "Khách liên hệ đường nào để yêu cầu xoá dữ liệu?",
                    "Cửa hàng phản hồi trong bao lâu?",
                )),
            ),
        ),
    ),
)
