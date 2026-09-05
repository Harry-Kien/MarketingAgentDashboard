"""
Che bí mật trong MỌI dòng nhật ký, bất kể ai ghi ra nó.

LỖI THẬT ĐÃ GẶP (03.09.2026)
----------------------------
`httpx` ghi URL ĐẦY ĐỦ kèm query string ở mức INFO, và không ai tắt nó.
Bộ kiểm sức khoẻ token Meta gọi:

    GET https://graph.facebook.com/v23.0/debug_token
        ?input_token=EAAR0uVcY6D…        ← token trang của khách
        &access_token=1254239285864497|… ← token ứng dụng

Cả hai đi thẳng vào log. Mỗi lần canh gác chạy là một lần nữa. Không lỗi,
không cảnh báo — đúng kiểu hỏng im lặng repo này ghét nhất, và lần này thứ
rò ra là bí mật.

Log không nằm yên một chỗ: nó được chụp màn hình, dán vào issue, gửi kèm
khi nhờ người khác xem giúp, và gom về máy chủ log tập trung. Một token
trong log phải coi như đã lộ.

HAI LỚP, VÌ MỘT LỚP SẼ HỎNG
---------------------------
1. `httpx` hạ xuống WARNING — bịt đúng đường đang rò. Lời gọi ERP đã có
   nhật ký riêng của `Cong`, nên không mất gì.

2. Bộ lọc che, gắn vào mọi handler — bắt cả những đường CHƯA BIẾT. Thư
   viện mới thêm vào ngày mai cũng ghi URL, và lúc đó không ai nhớ tệp này
   tồn tại. Lớp 2 làm việc mà không cần ai nhớ.

VÌ SAO CHE CẢ GIÁ TRỊ, KHÔNG CHỈ CHE THEO TÊN THAM SỐ
-----------------------------------------------------
Che theo tên (`access_token=…`) chỉ bắt được bí mật nằm trong query string.
Bí mật còn lọt ra qua thân JSON, qua header in trong traceback, qua một
`print(cfg)` nào đó. Nên lớp thứ hai quét CHÍNH GIÁ TRỊ bí mật đang cấu
hình: chuỗi ấy xuất hiện ở đâu trong dòng log cũng bị thay.

HAI NGUỒN BÍ MẬT
----------------
Danh sách giá trị cần che lấy từ `settings` (thêm khoá vào settings với tên
mang "token"/"key"/"secret"… là nó tự vào danh sách) VÀ từ `cau_hinh_dong`
(khoá người nhập trên dashboard, nằm trong CSDL chứ không có trong
`settings`). Bỏ nguồn thứ hai là khoá mới dán không được che dòng nào.
Danh sách được nhớ lại, nên `cau_hinh_dong` gọi `quen_bi_mat()` mỗi lần đổi.
"""
from __future__ import annotations

import logging
import re

# Tham số query mang bí mật. Danh sách CÓ CHỌN LỌC, không quét mọi thứ có
# chữ "key": `?fields=["item_code"]` của ERPNext chứa "code", và che nhầm
# nó thì nhật ký gỡ lỗi mất hết giá trị.
_THAM_SO_BI_MAT = (
    "access_token", "input_token", "refresh_token", "id_token",
    "api_key", "api_secret", "client_secret", "app_secret",
    "password", "passwd", "pwd", "secret", "token",
    "signature", "sig", "auth", "credential",
)

_QUERY_RE = re.compile(
    r"(?i)\b(" + "|".join(_THAM_SO_BI_MAT) + r")=([^&\s\"'|]+)"
)

# Bí mật nhét trong URL kiểu `https://user:matkhau@host`. Chỉ che phần mật
# khẩu — giữ tên người dùng lại thì dòng log còn nói được nó đi đâu.
_URL_AUTH_RE = re.compile(r"(?i)(://[^:/\s]+):([^@/\s]+)@")

# `Authorization: Bearer …` và họ hàng.
_HEADER_RE = re.compile(
    r"(?i)\b(bearer|basic|token)\s+([A-Za-z0-9._\-+/=]{8,})"
)

CHE = "<đã che>"

# Giá trị bí mật ngắn hơn ngần này thì không quét: chuỗi 6 ký tự dễ trùng
# với một từ bình thường trong dòng log, và che nhầm còn tệ hơn không che.
_DAI_TOI_THIEU = 8

# Dòng log dài hơn ngần này thì bỏ qua bước quét theo giá trị. Traceback
# nhiều nghìn ký tự nhân với chục bí mật là công vô ích trên đường nóng;
# bước che theo TÊN THAM SỐ ở trên vẫn chạy cho mọi độ dài.
_DAI_TOI_DA_QUET_GIA_TRI = 20_000


def che(van_ban: str, gia_tri_bi_mat: tuple[str, ...] = ()) -> str:
    """Che bí mật trong một chuỗi. Tách riêng để test được mà không cần log."""
    if not van_ban:
        return van_ban
    ra = _QUERY_RE.sub(lambda m: f"{m.group(1)}={CHE}", van_ban)
    ra = _URL_AUTH_RE.sub(lambda m: f"{m.group(1)}:{CHE}@", ra)
    ra = _HEADER_RE.sub(lambda m: f"{m.group(1)} {CHE}", ra)
    if gia_tri_bi_mat and len(ra) <= _DAI_TOI_DA_QUET_GIA_TRI:
        for bm in gia_tri_bi_mat:
            if bm in ra:
                ra = ra.replace(bm, CHE)
    return ra


def _gia_tri_bi_mat() -> tuple[str, ...]:
    """
    Các giá trị bí mật đang cấu hình, đủ dài để quét an toàn.

    HAI NGUỒN, vì bí mật giờ vào hệ thống bằng hai đường.

    1. `settings` — đọc qua `getattr` chứ không liệt kê cứng: thêm một khoá
       vào `settings` mà quên thêm vào đây là bí mật đó không được che, và
       không ai biết. Duyệt theo TÊN TRƯỜNG thì khoá mới tự vào danh sách
       nếu tên nó mang một trong các từ khoá.

    2. `cau_hinh_dong` — khoá người nhập trên dashboard KHÔNG có trong
       `settings` (nó nằm trong CSDL, `.env` chỉ là đường lui). Bỏ nguồn này
       là đúng những khoá mới nhất — thứ vừa được dán vào và đang được gọi
       nhiều nhất — không được che dòng nào. `bi_mat` lấy từ `DANH_MUC` chứ
       không đoán theo tên: URL ERPNext cũng có chữ "key" trong khoá kề bên,
       và che nhầm một URL là mất khả năng gỡ lỗi.

    Nhập trễ và nuốt mọi lỗi: hàm này chạy trên đường ghi log, nên nó không
    bao giờ được phép làm hỏng chính việc ghi log.
    """
    ra: set[str] = set()

    try:
        from agent.config import settings

        for ten in dir(settings):
            if ten.startswith("_"):
                continue
            if not any(t in ten.lower() for t in
                       ("secret", "token", "key", "password", "mat_khau")):
                continue
            try:
                gt = getattr(settings, ten)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(gt, str) and len(gt) >= _DAI_TOI_THIEU:
                ra.add(gt)
    except Exception:  # noqa: BLE001
        pass

    try:
        from agent import cau_hinh_dong

        for khoa, gt in cau_hinh_dong._gia_tri.items():
            mo_ta = cau_hinh_dong.DANH_MUC.get(khoa)
            if mo_ta is None or not mo_ta.bi_mat:
                continue
            if isinstance(gt, str) and len(gt) >= _DAI_TOI_THIEU:
                ra.add(gt)
    except Exception:  # noqa: BLE001
        pass

    return tuple(ra)


class LocBiMat(logging.Filter):
    """
    Bộ lọc che bí mật, gắn vào HANDLER chứ không gắn vào logger.

    Bộ lọc gắn trên một logger CHỈ thấy bản ghi log thẳng vào logger đó —
    bản ghi từ logger con đi lên handler mà không qua nó. Gắn vào handler
    thì mọi bản ghi chạm tới handler ấy đều bị soi, kể cả của thư viện
    chưa ai nghĩ tới.
    """

    # Bộ nhớ đệm nằm ở LỚP chứ không ở thể hiện: `dung_nhat_ky()` dựng một
    # `LocBiMat` mới mỗi lần gọi và gắn nó vào nhiều handler, nên xoá theo
    # thể hiện thì `quen_bi_mat()` phải đi tìm lại từng bộ lọc đã gắn ở đâu.
    # Một chỗ để đặt lại là một chỗ không quên được.
    _bi_mat: tuple[str, ...] | None = None

    @property
    def bi_mat(self) -> tuple[str, ...]:
        # Đọc trễ: bộ lọc được dựng lúc khởi động, có thể TRƯỚC khi .env
        # nạp xong. Đọc ngay lúc dựng thì danh sách rỗng vĩnh viễn.
        if LocBiMat._bi_mat is None:
            LocBiMat._bi_mat = _gia_tri_bi_mat()
        return LocBiMat._bi_mat

    def filter(self, record: logging.LogRecord) -> bool:
        bm = self.bi_mat
        try:
            # Dựng chuỗi cuối rồi che MỘT LẦN, thay vì che riêng `msg` và
            # từng phần tử `args`. Bí mật có thể bị cắt đôi giữa mẫu định
            # dạng và tham số — che từng mảnh thì không mảnh nào khớp.
            noi_dung = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        sach = che(noi_dung, bm)
        if sach != noi_dung:
            record.msg = sach
            record.args = ()
        # Traceback cũng chứa URL đầy đủ khi httpx ném lỗi.
        if record.exc_text:
            record.exc_text = che(record.exc_text, bm)
        return True


def quen_bi_mat() -> None:
    """
    Quên danh sách bí mật đã ghi nhớ; lần ghi log kế tiếp đọc lại.

    Gọi khi cấu hình động đổi. Danh sách được nhớ một lần rồi dùng mãi (đọc
    lại mỗi dòng log là quá đắt trên đường nóng), nên khoá vừa dán trên
    dashboard sẽ KHÔNG được che cho tới lần khởi động lại — đúng lúc nó bị
    gọi nhiều nhất, và không có gì báo cho ai biết.
    """
    LocBiMat._bi_mat = None


_DA_CAI = False


def dung_nhat_ky() -> None:
    """
    Cài bộ lọc và hạ mức ồn. Gọi MỘT LẦN lúc khởi động ứng dụng.

    An toàn khi gọi lại: uvicorn dựng handler của nó sau khi ứng dụng khởi
    động, nên hàm này còn được gọi lại từ `main.py` để quét lượt nữa.
    """
    global _DA_CAI

    # `httpx` ghi URL đầy đủ ở INFO — đúng đường đã rò token Meta. Lời gọi
    # ERP đã có nhật ký riêng trong `Cong`, nên hạ xuống WARNING không mất
    # thông tin nào đang được dùng.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    loc = LocBiMat()
    for logger in [logging.getLogger()] + [
        logging.getLogger(t) for t in list(logging.root.manager.loggerDict)
    ]:
        for h in getattr(logger, "handlers", []):
            if not any(isinstance(f, LocBiMat) for f in h.filters):
                h.addFilter(loc)
    _DA_CAI = True


def da_cai() -> bool:
    return _DA_CAI
