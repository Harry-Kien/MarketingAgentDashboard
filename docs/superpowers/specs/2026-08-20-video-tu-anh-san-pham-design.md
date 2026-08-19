# Video từ ảnh sản phẩm — thiết kế

Ngày 2026-08-20. Trạng thái: đã duyệt, đang triển khai.

## Vấn đề

Dây chuyền video hiện chỉ dựng được thẻ chữ trên nền màu. Người dùng có ảnh
sản phẩm thật nhưng không có đường nào đưa ảnh vào video.

## Nguyên tắc dẫn đường

Dự án đã có một nguyên tắc cho âm thanh: *đo bằng `ffprobe` rồi mới dựng,
không để model đoán thời lượng*. Thiết kế này áp đúng nguyên tắc đó cho hình:

> **Nhìn ảnh thật rồi mới quyết bố cục, không để model đoán chữ đặt ở đâu.**

Hệ quả kiến trúc: phải có một bước phân tích ảnh **tách rời**, sinh ra dữ liệu
kiểm chứng được, chạy trước bước viết kịch bản. Không gộp vào một lời gọi.

## Dây chuyền mới

    ảnh upload -> chuẩn hoá -> NHÌN ẢNH -> kịch bản (bám ảnh)
                                              |
                    giọng đọc -> ĐO ffprobe -> dựng hình -> MP4

Hai bước in hoa là hai chỗ hệ thống đo thực tế thay vì tin model.

## Thành phần

| Đơn vị | Trách nhiệm | Phụ thuộc |
|---|---|---|
| `agent/video/assets.py` | Nhận, kiểm, chuẩn hoá, lưu ảnh | Pillow |
| `agent/video/vision.py` | Nhìn ảnh -> JSON có cấu trúc | llm, prompt |
| `agent/video/renderers/ffmpeg.py` | Ken Burns + gradient + chữ + phụ đề | ffmpeg |
| `agent/video/renderers/hyperframes.py` | Bậc 2 | Node |
| `agent/video/renderers/veo.py` | Bậc 1 | quota Veo |
| `agent/video/renderers/subtitles.py` | Sinh `.ass` từ scenes | — |
| `agent/video/renderers/__init__.py` | Router 3 bậc | ba cái trên |

Ranh giới: `pipeline.py` không biết backend nào đang chạy; `renderers/*` không
biết ảnh từ đâu tới; `vision.py` không biết ảnh sẽ được dựng thế nào.

## Nhận ảnh

`POST /api/videos` nhận multipart. Chuẩn hoá trước khi ghi đĩa:

- Kiểm bằng magic bytes qua Pillow, không tin đuôi file
- Xoay theo EXIF Orientation rồi **xoá sạch EXIF** — ảnh điện thoại mang toạ
  độ GPS kho hàng, và ảnh này sẽ nằm trong video công khai
- Hạ cạnh dài về <= 2048px
- Chặn: <= 8 ảnh, <= 10 MB mỗi ảnh, chỉ jpg/png/webp

Bảng `video_assets` giữ đường dẫn, kích thước, kết quả phân tích, cờ `usable`.

## Nhìn ảnh

Mỗi ảnh một lời gọi `model_cheap`, song song. Trả JSON:

    mo_ta, mau_chu_dao, do_sang, huong, chat_luong,
    vung_trong, co_chu_san, phu_hop

`vung_trong` (tren|duoi|trai|phai|khong_co) lái toàn bộ bố cục chữ ở khâu dựng.
Ảnh mờ / quá tối / đã có chữ quảng cáo của người khác -> `usable = false`.

Tầng LLM phải mở rộng: `content` nhận danh sách khối `{type: text|image}`.
Dịch sang `inlineData` (Gemini) và khối `image` (Anthropic). Đường chuỗi thuần
giữ nguyên nên `agent.py` và `rag.py` không đổi.

## Kịch bản bám ảnh

Prompt nhận danh mục ảnh dạng chữ; mỗi cảnh trả thêm `anh_index`.

Kiểm ở code, không tin model: `anh_index` phải trỏ tới ảnh `usable`.

Ảnh là căn cứ về **hình thức** (màu, kiểu dáng, chất liệu). Ảnh **không** là
căn cứ về giá, bảo hành, tồn kho — vẫn chỉ từ brief và RAG.

## Dựng hình

Mỗi cảnh: ảnh `scale`+`crop` đầy 1080x1920 (ảnh ngang thì nền là chính nó
phóng to + `boxblur`, không bao giờ viền đen) -> `zoompan` Ken Burns đổi hướng
luân phiên -> gradient tối đặt đúng `vung_trong`, đậm nhạt theo `do_sang` ->
`drawtext` có xuống dòng -> nối bằng `xfade` 0,4s -> burn phụ đề `.ass`.

Lỗi tràn chữ hiện có được sửa ở đây: `textwrap.fill` theo bề rộng khung và tự
hạ `fontsize` khi vẫn dài.

## Suy giảm

| Mất mảnh | Hành vi |
|---|---|
| Không ảnh | Chạy như cũ, thẻ chữ nền màu |
| Vision lỗi/JSON sai | Mặc định `vung_trong=duoi`, chữ trắng. KHÔNG chặn |
| Một ảnh hỏng | Bỏ ảnh đó, cảnh dùng ảnh tốt nhất còn lại |
| TTS chết | Thời lượng ước lượng, video câm, phụ đề vẫn cháy vào hình |
| Veo/HyperFrames chưa sẵn sàng | Tụt về ffmpeg, ghi rõ backend trên thẻ video |

## Kiểm chứng

- `python -m scripts.test_render --images <thư mục>` — không cần DB/LLM
- `python -m scripts.test_vision <ảnh>` — soi riêng bước nhìn ảnh
- Ngưỡng: sai lệch thời lượng < 0,6s; hộp chữ nằm trọn trong khung an toàn

## Đã biết còn thiếu

- Bậc Veo viết theo tài liệu nhưng **chưa chạy thử được** (quota chưa bật).
  Không được báo cáo là đã kiểm chứng cho tới khi có quota thật.
- Render vẫn chạy trong tiến trình app (nợ cũ, chưa xử lý ở vòng này).
