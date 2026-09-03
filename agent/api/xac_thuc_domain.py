"""
Phục vụ file xác thực quyền sở hữu domain cho Zalo, Meta, Google.

VÌ SAO CẦN
----------
Zalo từ chối webhook cho tới khi domain được xác thực:

    "Đường dẫn webhook chưa được xác thực domain. Vui lòng truy cập
     https://developers.zalo.me/app/<app_id>/verify-domain"

Cách xác thực là ĐẶT MỘT FILE ở gốc domain, rồi Zalo tự tải về đối chiếu
nội dung. Họ không tra WHOIS, không đòi DNS — chỉ tải một URL.

Nghĩa là một tên miền tạm kiểu `trycloudflare.com` VẪN xác thực được, miễn
ứng dụng phục vụ đúng file ở đúng đường. Đó là điều đáng nói, vì thoạt nghe
"xác thực quyền sở hữu domain" ai cũng tưởng phải có tên miền riêng.

VÌ SAO LÀ MỘT THƯ MỤC, KHÔNG PHẢI HAI BIẾN MÔI TRƯỜNG
-----------------------------------------------------
Zalo, Meta và Google đều dùng cùng một cách, chỉ khác tên file. Khai từng
cặp tên–nội dung vào `.env` là mỗi nền tảng thêm hai biến, và người vận
hành phải chép nội dung file vào một dòng `.env` — thứ hay hỏng vì xuống
dòng và dấu nháy.

Thả nguyên file vào thư mục thì đúng bằng thao tác nhà cung cấp hướng dẫn:
"tải file này về và đặt ở gốc website".

RÀNG BUỘC AN TOÀN
-----------------
Thư mục này phơi ra Internet KHÔNG CẦN ĐĂNG NHẬP — bắt buộc, vì Zalo tải
file khi chưa có phiên nào. Nên nó phải hẹp hết mức:

  · chỉ tên file khớp mẫu xác thực đã biết, không phải mọi tệp
  · chỉ đọc thẳng trong thư mục, không đi vào thư mục con
  · chặn `..` và dấu gạch chéo trước khi chạm đĩa

Không có ba chốt đó thì đây là một lỗ đọc file tuỳ ý, phơi công khai.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from agent.config import ROOT

router = APIRouter(tags=["xac-thuc-domain"])

THU_MUC = ROOT / "data" / "xac_thuc_domain"

# Tên file xác thực của từng nền tảng. Danh sách ĐÓNG — thêm nền tảng là
# phải sửa mã và viết test, đúng như ý đồ.
#
# Mở rộng thành "mọi tệp .html" là biến thư mục này thành nơi phục vụ tệp
# tuỳ ý ở gốc domain, không đăng nhập. Ai ghi được vào thư mục là đăng được
# một trang mang tên miền của cửa hàng.
_MAU_TEN = re.compile(
    r"^(?:"
    r"zalo_verifier[A-Za-z0-9_-]{4,64}\.html"           # Zalo
    r"|google[0-9a-f]{16}\.html"                        # Google Search Console
    r"|[A-Za-z0-9_-]{1,64}\.txt"                        # Meta / xác thực dạng txt
    r")$"
)


def hop_le(ten: str) -> bool:
    """
    Tên file có phải file xác thực hợp lệ không.

    Tách riêng để test được mà không cần dựng request, và để mọi chốt nằm ở
    MỘT chỗ — hai chỗ kiểm thì cái lỏng hơn quyết định.
    """
    if not ten or len(ten) > 128:
        return False
    # Chặn TRƯỚC khi regex chạy: `..` và gạch chéo không bao giờ hợp lệ, và
    # dựa vào regex một mình là dựa vào việc mình viết regex không sót.
    if "/" in ten or "\\" in ten or ".." in ten:
        return False
    return bool(_MAU_TEN.match(ten))


def _tra(ten_file: str) -> PlainTextResponse:
    """
    Trả file xác thực domain, KHÔNG cần đăng nhập.

    KHÔNG DÙNG MẪU BẮT-TẤT `/{ten_file}`.

    Bản đầu làm vậy và đăng ký router ở cuối, tưởng là đủ. Nhưng những route
    khai bằng `@app.get` TRONG `main.py` nằm SAU mọi `include_router`, nên
    mẫu bắt-tất vẫn khớp trước chúng: `/healthz` và `/app.css` cùng trả 404
    ngay lần chạy thử đầu tiên — dashboard mất sạch CSS.

    Ba đường tường minh dưới đây không thể va vào đường nào khác, và thứ tự
    đăng ký thôi là chuyện phải nhớ.
    """
    if not hop_le(ten_file):
        raise HTTPException(404, "Không tìm thấy")

    tep = THU_MUC / ten_file
    # `resolve()` rồi đối chiếu cha: chốt cuối chống đường dẫn vượt thư mục,
    # phòng khi ba chốt trên có kẽ hở nào chưa nghĩ ra.
    try:
        that = tep.resolve()
        if that.parent != THU_MUC.resolve() or not that.is_file():
            raise HTTPException(404, "Không tìm thấy")
    except OSError:
        raise HTTPException(404, "Không tìm thấy") from None

    return PlainTextResponse(that.read_text(encoding="utf-8", errors="replace"))


# Ba đường TƯỜNG MINH, mỗi nền tảng một mẫu. Không đường nào khớp được
# `/healthz`, `/app.css` hay `/` — nên đăng ký ở đâu cũng đúng.

@router.get("/zalo_verifier{ma}.html", include_in_schema=False)
async def zalo(ma: str) -> PlainTextResponse:
    return _tra(f"zalo_verifier{ma}.html")


@router.get("/google{ma}.html", include_in_schema=False)
async def google(ma: str) -> PlainTextResponse:
    return _tra(f"google{ma}.html")


@router.get("/{ten}.txt", include_in_schema=False)
async def dang_txt(ten: str) -> PlainTextResponse:
    """
    Meta và vài nền tảng khác dùng tệp `.txt`.

    Đuôi `.txt` cố định trong mẫu nên đường này KHÔNG bắt-tất: nó không
    khớp `/healthz`, `/app.css` hay `/`. Vẫn đi qua `hop_le()` như hai
    đường trên.
    """
    return _tra(f"{ten}.txt")
