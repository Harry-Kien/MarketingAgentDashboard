"""
Khung ngành ĐỒ THỂ THAO.

KHUNG NÀY CHƯA CÓ BẰNG CHỨNG THỰC NGHIỆM — PHẢI NÓI RÕ
------------------------------------------------------
Khung mỹ phẩm rút ra từ 19 tài liệu đã chạy qua bộ 56 câu vàng. Khung này
thì chưa: nó dựng từ suy luận về ngành, chưa ca vàng nào kiểm.

Nói rõ điều đó ở đây thay vì để người dùng tự phát hiện, vì nhầm lẫn giữa
"đã kiểm" và "chưa kiểm" chính là xanh giả.

RANH GIỚI Y TẾ CHUYỂN ĐƯỢC TỪ MỸ PHẨM SANG — GẦN NHƯ NGUYÊN VẸN
---------------------------------------------------------------
Thoạt nhìn thì đồ thể thao không dính y tế. Thực tế dính hai đường:

  CHẤN THƯƠNG   "chạy bộ bị đau gối nên mua giày gì" là câu hỏi y tế đội
                lốt câu hỏi hàng hoá. Khuyên giày cho một cái gối đang đau
                là tư vấn ngoài thẩm quyền, y hệt khuyên kem cho vùng da
                đang viêm.
  THỰC PHẨM BỔ SUNG
                whey, creatine, BCAA chịu quản lý an toàn thực phẩm, và
                quảng cáo công dụng bị siết như mỹ phẩm.

Nên nhóm từ khoá bắt buộc chuyển người giữ nguyên phần "bác sĩ · đang điều
trị · trẻ em · đòi cam kết", chỉ thay nhóm bệnh da bằng nhóm chấn thương.
"""
from __future__ import annotations

from agent.tri_thuc.hop_dong import KhungNganh, Muc, TaiLieu

KHUNG = KhungNganh(
    ma="the_thao",
    ten="Đồ thể thao và dinh dưỡng vận động",
    mo_ta=(
        "Bán hàng có tư vấn kỹ thuật (size, mặt sân, cường độ tập) và chạm "
        "ranh giới y tế qua chấn thương lẫn thực phẩm bổ sung."
    ),
    van_ban_phap_ly=(
        "Nghị định 15/2018/NĐ-CP — an toàn thực phẩm, áp cho thực phẩm bổ sung",
        "Nghị định 181/2013/NĐ-CP — hướng dẫn thi hành Luật Quảng cáo",
        "Nghị định 13/2023/NĐ-CP — bảo vệ dữ liệu cá nhân",
    ),
    cum_cam_goi_y=(
        "chữa chấn thương", "trị đau khớp", "phục hồi hoàn toàn",
        "tăng cơ cấp tốc", "giảm mỡ cấp tốc", "thay thế thuốc",
        "cam kết tăng", "hiệu quả 100%", "không cần tập",
        "tốt nhất thị trường", "số 1 Việt Nam",
    ),
    tai_lieu=(
        TaiLieu(
            ten_tep="an-toan-va-gioi-han-tu-van.md",
            tieu_de="An toàn và giới hạn tư vấn",
            vi_sao=(
                "Đối ứng của 'an toàn và chống chỉ định' bên mỹ phẩm, và "
                "cũng là tài liệu quan trọng nhất. Khách hỏi về cơn đau là "
                "hỏi câu y tế, dù họ diễn đạt bằng tên sản phẩm."
            ),
            muc=(
                Muc("Khi khách nhắc tới đau hoặc chấn thương", (
                    "Những dấu hiệu nào khiến cửa hàng dừng tư vấn và khuyên đi khám?",
                    "Câu trả lời chuẩn khi khách nói mình chạy bị đau gối là gì?",
                    "Cửa hàng có tư vấn cho người đang hồi phục chấn thương không?",
                )),
                Muc("Thực phẩm bổ sung", (
                    "Cửa hàng có bán thực phẩm bổ sung không, nhóm nào?",
                    "Nhóm khách nào không được tư vấn (dưới 18 tuổi, mang thai, bệnh nền)?",
                    "Được nói gì và không được nói gì về công dụng?",
                )),
                Muc("Câu tuyệt đối không được nói", (
                    "Những cụm nào bị cấm khi tư vấn, và dựa trên văn bản nào?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="chon-size-va-do-vua.md",
            tieu_de="Chọn size và độ vừa",
            vi_sao=(
                "Nguyên nhân đổi trả số một của ngành. Mỗi lần tư vấn size "
                "đúng là một đơn không bị trả về, và một khách không thất vọng."
            ),
            muc=(
                Muc("Cách đo", (
                    "Hướng dẫn khách tự đo tại nhà thế nào?",
                    "Đo vào thời điểm nào trong ngày thì chuẩn nhất?",
                )),
                Muc("Quy đổi bảng size", (
                    "Các hãng cửa hàng bán có lệch size với nhau không, lệch bao nhiêu?",
                    "Khi số đo nằm giữa hai size thì khuyên lấy size nào?",
                )),
                Muc("Độ vừa theo môn", (
                    "Giày chạy, giày sân, giày tập nên vừa khác nhau thế nào?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="chon-do-theo-mon-va-mat-san.md",
            tieu_de="Chọn đồ theo môn và mặt sân",
            vi_sao=(
                "Đây là chất tư vấn của ngành này — thứ ERP không cấp. Không "
                "có nó, agent chỉ đọc được tên hàng, giá và tồn kho."
            ),
            muc=(
                Muc("Phân nhóm theo môn", (
                    "Cửa hàng phục vụ những môn nào?",
                    "Mỗi môn cần nhóm sản phẩm nào là tối thiểu?",
                )),
                Muc("Mặt sân và điều kiện", (
                    "Cỏ tự nhiên, cỏ nhân tạo, sân cứng, đường nhựa khác nhau chỗ nào khi chọn đồ?",
                    "Thời tiết nóng ẩm Việt Nam ảnh hưởng gì tới lựa chọn chất liệu?",
                )),
                Muc("Theo trình độ và tần suất", (
                    "Người mới tập nên bắt đầu với gì?",
                    "Bao lâu thì nên thay giày, tính theo quãng đường hay thời gian?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="chinh-sach-thuong-mai.md",
            tieu_de="Chính sách thương mại",
            vi_sao=(
                "Mỗi con số ở đây là một cam kết pháp lý với khách. Ngành "
                "này có thêm một điểm riêng: hàng đã dùng ngoài trời thường "
                "không đổi được, và khách cần biết trước khi mua."
            ),
            muc=(
                Muc("Đổi trả", (
                    "Đổi size trong bao nhiêu ngày, điều kiện gì?",
                    "Hàng đã đi ngoài trời, đã bung tem, đã giặt có đổi được không?",
                    "Ai chịu phí vận chuyển chiều đổi?",
                )),
                Muc("Bảo hành", (
                    "Những lỗi nào được bảo hành, những hư hỏng nào không?",
                    "Thời hạn bảo hành từng nhóm hàng là bao lâu?",
                )),
                Muc("Vận chuyển và thanh toán", (
                    "Phí ship từng khu vực và mức miễn phí?",
                    "Nhận những hình thức thanh toán nào?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="hang-that-va-bao-quan.md",
            tieu_de="Hàng thật và bảo quản",
            vi_sao=(
                "Ngành này bị hàng giả nhiều nên khách hỏi rất thường. Trả "
                "lời có căn cứ là một lợi thế bán hàng; trả lời mơ hồ là mất đơn."
            ),
            muc=(
                Muc("Nguồn hàng", (
                    "Cửa hàng nhập hàng từ đâu, có giấy tờ gì chứng minh?",
                    "Khách tự kiểm tra hàng thật bằng cách nào?",
                )),
                Muc("Bảo quản và vệ sinh", (
                    "Hướng dẫn giặt và bảo quản từng nhóm chất liệu?",
                    "Điều gì làm hỏng sản phẩm nhanh nhất mà khách hay mắc?",
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
                Muc("Hàng lỗi hoặc không như mô tả", (
                    "Khách cần cung cấp bằng chứng gì?",
                    "Trong bao lâu cửa hàng xử lý xong?",
                )),
                Muc("Khách nói sản phẩm gây đau hoặc khó chịu", (
                    "Đây là lỗi sản phẩm hay vấn đề cơ thể — cửa hàng phân biệt thế nào?",
                    "Khi nào bắt buộc chuyển cho người thật?",
                )),
            ),
        ),
        TaiLieu(
            ten_tep="du-lieu-ca-nhan-va-quyen-cua-khach.md",
            tieu_de="Dữ liệu cá nhân và quyền của khách",
            vi_sao=(
                "Nghị định 13/2023 áp cho mọi ngành, không riêng mỹ phẩm. "
                "Agent phải trả lời đúng khi khách hỏi, và chuyển cho người "
                "khi khách yêu cầu thực hiện quyền."
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
