"""
Xác thực và phân quyền cho dashboard.

VÌ SAO PHẢI CÓ TRƯỚC KHI ĐƯA VÀO DOANH NGHIỆP
---------------------------------------------
Dashboard cho phép: đọc tên, số điện thoại và địa chỉ khách hàng; đọc toàn
bộ nội dung hội thoại; gửi tin nhắn nhân danh doanh nghiệp; XOÁ VĨNH VIỄN
dữ liệu khách; sửa tồn kho; duyệt bài đăng lên fanpage.

Trước lớp này, bất kỳ ai chạm tới cổng 8000 đều làm được tất cả. Nó chỉ an
toàn nhờ nghe ở 127.0.0.1 — nghĩa là an toàn cho tới đúng ngày ai đó đưa
lên server.

Theo Nghị định 13/2023/NĐ-CP, dữ liệu cá nhân phải có biện pháp bảo vệ.
"Không ai biết địa chỉ IP" không phải một biện pháp.

CHỌN CÁCH ĐƠN GIẢN NHẤT ĐỦ DÙNG
-------------------------------
Không dùng OAuth, không JWT, không thư viện ngoài. Một tiệm mỹ phẩm có 2-5
nhân viên; thứ họ cần là mỗi người một tài khoản để biết AI ĐÃ LÀM GÌ, chứ
không phải một hệ thống định danh liên thông.

  mật khẩu   scrypt trong thư viện chuẩn — chậm có chủ đích, chống dò
  phiên      token ngẫu nhiên trong CSDL, cookie HttpOnly
  quyền      hai vai: quản trị và nhân viên

VÌ SAO PHIÊN NẰM TRONG CSDL CHỨ KHÔNG PHẢI JWT
----------------------------------------------
JWT không thu hồi được. Nhân viên nghỉ việc lúc 9 giờ sáng thì token của họ
vẫn dùng được tới lúc hết hạn. Phiên trong CSDL thì xoá một dòng là xong —
và với hệ thống nắm dữ liệu khách hàng, thu hồi ngay là điều bắt buộc.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from .. import db

# scrypt: chậm và tốn bộ nhớ có chủ đích. Tham số theo khuyến nghị OWASP
# cho ứng dụng tương tác — đủ chậm để dò mật khẩu không kinh tế, đủ nhanh
# để đăng nhập không thấy trễ.
_N, _R, _P = 2 ** 14, 8, 1
_DAI_KHOA = 32

PHIEN_NGAY = 7          # phiên sống bao lâu
VAI_TRO = ("quan_tri", "nhan_vien")

# Việc chỉ quản trị được làm. Nhân viên đọc và xử lý hội thoại bình thường,
# nhưng không được xoá dữ liệu khách hay đổi cách agent vận hành.
CHI_QUAN_TRI = (
    "pdpd.xoa",           # xoá vĩnh viễn dữ liệu cá nhân
    "runtime",            # bật/tắt agent, đổi chế độ, đổi ngưỡng
    "nguoi_dung",         # tạo/xoá tài khoản
)


def bam_mat_khau(mat_khau: str) -> str:
    """
    Băm mật khẩu kèm muối ngẫu nhiên. Trả chuỗi tự chứa đủ để kiểm lại.

    Muối riêng cho từng người: hai người đặt cùng mật khẩu vẫn ra hai bản
    băm khác nhau, nên lộ một bản không suy ra được bản kia.
    """
    muoi = secrets.token_bytes(16)
    khoa = hashlib.scrypt(mat_khau.encode(), salt=muoi, n=_N, r=_R, p=_P,
                          dklen=_DAI_KHOA)
    return f"scrypt${_N}${_R}${_P}${muoi.hex()}${khoa.hex()}"


def kiem_mat_khau(mat_khau: str, bam: str) -> bool:
    """
    So sánh bằng compare_digest — thời gian không phụ thuộc nội dung.

    So bằng `==` để lộ độ dài tiền tố đúng qua thời gian phản hồi; với đủ
    lần thử, đó là một đường dò mật khẩu.
    """
    try:
        thuat, n, r, p, muoi_hex, khoa_hex = bam.split("$")
        if thuat != "scrypt":
            return False
        khoa = hashlib.scrypt(
            mat_khau.encode(), salt=bytes.fromhex(muoi_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(khoa_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(khoa.hex(), khoa_hex)


# ---------------------------------------------------------------
#  Tài khoản
# ---------------------------------------------------------------

async def tao_nguoi_dung(
    ten_dang_nhap: str, mat_khau: str, ho_ten: str = "",
    vai_tro: str = "nhan_vien",
) -> dict:
    ten_dang_nhap = ten_dang_nhap.strip().lower()
    if len(ten_dang_nhap) < 3:
        raise ValueError("Tên đăng nhập phải từ 3 ký tự")
    if len(mat_khau) < 8:
        raise ValueError("Mật khẩu phải từ 8 ký tự")
    if vai_tro not in VAI_TRO:
        raise ValueError(f"Vai trò không hợp lệ. Chỉ nhận: {VAI_TRO}")

    row = await db.fetchrow(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
        "VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (ten_dang_nhap) DO NOTHING "
        "RETURNING id, ten_dang_nhap, ho_ten, vai_tro",
        ten_dang_nhap, bam_mat_khau(mat_khau), ho_ten or ten_dang_nhap, vai_tro,
    )
    if row is None:
        raise ValueError(f"Tên đăng nhập {ten_dang_nhap!r} đã tồn tại")
    row["id"] = str(row["id"])
    await db.log_event("auth.tao_nguoi_dung", actor="he_thong",
                       ten_dang_nhap=ten_dang_nhap, vai_tro=vai_tro)
    return row


async def co_nguoi_dung_nao_chua() -> bool:
    r = await db.fetchrow("SELECT 1 FROM nguoi_dung LIMIT 1")
    return r is not None


async def doi_mat_khau(ten_dang_nhap: str, mat_khau_moi: str) -> bool:
    if len(mat_khau_moi) < 8:
        raise ValueError("Mật khẩu phải từ 8 ký tự")
    r = await db.fetchrow(
        "UPDATE nguoi_dung SET mat_khau_bam = $2 WHERE ten_dang_nhap = $1 "
        "RETURNING id", ten_dang_nhap.strip().lower(), bam_mat_khau(mat_khau_moi),
    )
    if r:
        # Đổi mật khẩu phải ĐÁ MỌI PHIÊN ĐANG MỞ. Không làm thế thì người
        # chiếm được tài khoản vẫn ngồi trong đó sau khi chủ đã đổi mật khẩu.
        await db.execute("DELETE FROM phien WHERE nguoi_dung_id = $1", r["id"])
    return r is not None


# ---------------------------------------------------------------
#  Phiên
# ---------------------------------------------------------------

# ---------------------------------------------------------------
#  Giới hạn tần suất đăng nhập
# ---------------------------------------------------------------
# VẤN ĐỀ
# ------
# scrypt làm mỗi lần thử tốn khoảng 100ms. Đó là LÀM CHẬM, không phải
# CHẶN: một tiến trình dò chạy liên tục vẫn thử được ~860.000 lần mỗi
# ngày, và mật khẩu do người tự đặt thì rất nhiều cái nằm trong khoảng
# đó. Không có lớp này thì người dò có thời gian vô hạn.
#
# ĐẾM TRONG BỘ NHỚ, KHÔNG ĐẾM TRONG CSDL
# --------------------------------------
# Nhật ký `auth.that_bai` đã nằm trong bảng `events`, nên đếm từ đó là
# cách gọn nhất về mặt mã. Nhưng nó bắt mỗi lần đăng nhập phải quét một
# bảng đang lớn dần theo ngày, và biến chốt bảo mật thành thứ hỏng theo
# khi bảng phình. Đếm trong bộ nhớ thì hằng số, không phụ thuộc CSDL, và
# kiểm thử được mà không cần Postgres.
#
# GIỚI HẠN PHẢI NÓI RÕ: khởi động lại tiến trình là xoá sạch bộ đếm, và
# nếu sau này chạy nhiều worker thì mỗi worker đếm riêng. Với triển khai
# hiện tại — một máy, một tiến trình — điều đó chấp nhận được. Ngày nào
# chạy nhiều tiến trình thì bộ đếm này phải chuyển sang Redis.
#
# KHOÁ THEO TÊN ĐĂNG NHẬP — VÀ CÁI GIÁ CỦA NÓ
# -------------------------------------------
# Khoá theo tên nghĩa là kẻ xấu gõ sai 8 lần vào tài khoản `admin` sẽ
# khoá luôn `admin` thật trong 15 phút. Đó là một dạng quấy rối, và ta
# chấp nhận có chủ đích: 15 phút chờ khó chịu hơn nhiều so với mất toàn
# bộ dữ liệu khách hàng. Cửa sổ ngắn để cái giá đó không quá đắt.
#
# Đếm CẢ tên không tồn tại. Bỏ qua tên lạ thì người dò chỉ cần đổi tên
# mỗi lượt là thoát — và tệ hơn, việc "tên này bị khoá, tên kia không"
# lại chỉ ra đúng tên nào có thật.

DANG_NHAP_TOI_DA = 8        # số lần sai cho phép trong một cửa sổ
DANG_NHAP_CUA_SO = 15 * 60  # độ dài cửa sổ, tính bằng giây

# ten_dang_nhap -> các mốc thời gian thất bại còn trong cửa sổ
_that_bai: dict[str, list[float]] = {}


def _bay_gio(t: float | None = None) -> float:
    return time.monotonic() if t is None else t


def _con_trong_cua_so(ten: str, t: float) -> list[float]:
    """Bỏ các lần sai đã quá cũ, trả về phần còn lại."""
    moc = [m for m in _that_bai.get(ten, []) if t - m < DANG_NHAP_CUA_SO]
    if moc:
        _that_bai[ten] = moc
    else:
        _that_bai.pop(ten, None)
    return moc


# Bộ đếm chỉ tự dọn khi CHÍNH tên đó bị chạm lại. Người dò đổi tên mỗi
# lượt thì không tên nào bị chạm lần hai, và cái dict này phình mãi — chốt
# chống dò tự biến thành đường làm cạn bộ nhớ. Quá mức này thì quét dọn
# một lượt toàn bộ.
_TOI_DA_TEN_THEO_DOI = 4096


def _don_toan_bo(t: float) -> None:
    """
    Dọn về dưới mức trần. Hai bước, và bước hai là bước bắt buộc.

    Chỉ bỏ mục hết hạn là KHÔNG đủ: người dò bắn 5.000 tên khác nhau trong
    vòng một phút thì chẳng mục nào hết hạn cả, và dict vẫn phình. Nên khi
    dọn xong mà vẫn quá trần thì bỏ tiếp các mục CŨ NHẤT cho tới khi vừa.

    Bỏ mục cũ nhất có làm mất bộ đếm của ai đó không? Có — nhưng không mất
    của người đang bị nhắm. Kẻ dò `admin` khiến `admin` liên tục được chạm,
    nên `admin` luôn nằm trong nhóm mới nhất và không bị bỏ. Thứ bị bỏ là
    các tên rác họ vừa bắn ra, tức đúng thứ nên bỏ.
    """
    for ten in [k for k, v in _that_bai.items()
                if all(t - m >= DANG_NHAP_CUA_SO for m in v)]:
        _that_bai.pop(ten, None)

    if len(_that_bai) < _TOI_DA_TEN_THEO_DOI:
        return
    theo_tuoi = sorted(_that_bai.items(), key=lambda kv: kv[1][-1])
    for ten, _ in theo_tuoi[: len(_that_bai) - _TOI_DA_TEN_THEO_DOI + 1]:
        _that_bai.pop(ten, None)


def ghi_that_bai(ten_dang_nhap: str, t: float | None = None) -> None:
    """Ghi một lần đăng nhập sai."""
    ten = (ten_dang_nhap or "").strip().lower()
    t = _bay_gio(t)
    if len(_that_bai) >= _TOI_DA_TEN_THEO_DOI:
        _don_toan_bo(t)
    moc = _con_trong_cua_so(ten, t)
    _that_bai[ten] = [*moc, t]


def xoa_that_bai(ten_dang_nhap: str) -> None:
    """Đăng nhập đúng thì xoá lịch sử sai — người thật gõ nhầm vài lần
    rồi nhớ ra không đáng bị tính tiếp vào lần sau."""
    _that_bai.pop((ten_dang_nhap or "").strip().lower(), None)


def bi_khoa_tam(ten_dang_nhap: str, t: float | None = None) -> int:
    """
    Còn phải chờ bao nhiêu GIÂY nữa mới được thử lại. 0 nghĩa là được thử.
    """
    ten = (ten_dang_nhap or "").strip().lower()
    t = _bay_gio(t)
    moc = _con_trong_cua_so(ten, t)
    if len(moc) < DANG_NHAP_TOI_DA:
        return 0
    # Mở khoá khi lần sai thứ (n - TOI_DA + 1) tính từ cuối trôi khỏi cửa sổ.
    som_nhat = moc[-DANG_NHAP_TOI_DA]
    return max(1, int(DANG_NHAP_CUA_SO - (t - som_nhat)) + 1)


async def dang_nhap(ten_dang_nhap: str, mat_khau: str) -> str | None:
    """Trả token phiên, hoặc None nếu sai. KHÔNG nói sai ở đâu."""
    ten_dang_nhap = (ten_dang_nhap or "").strip().lower()

    # Chốt tần suất đứng TRƯỚC cả truy vấn CSDL: đang bị khoá thì không
    # tốn một lần đọc bảng nào, và cũng không tốn 100ms băm scrypt. Nếu
    # đặt sau, chính chốt chống dò lại trở thành đường làm nghẽn máy chủ.
    if (con := bi_khoa_tam(ten_dang_nhap)) > 0:
        await db.log_event("auth.khoa_tam", actor=ten_dang_nhap[:40],
                           ly_do=f"quá {DANG_NHAP_TOI_DA} lần sai",
                           con_giay=con)
        return None

    nd = await db.fetchrow(
        "SELECT id, mat_khau_bam, vai_tro, khoa FROM nguoi_dung "
        "WHERE ten_dang_nhap = $1", ten_dang_nhap,
    )

    # Vẫn băm một lần dù không có tài khoản: trả lời ngay lập tức cho tên
    # không tồn tại là chỉ ra tên nào CÓ tồn tại.
    if nd is None:
        kiem_mat_khau(mat_khau, bam_mat_khau("khong-co-that"))
        await db.log_event("auth.that_bai", actor=ten_dang_nhap[:40],
                           ly_do="không có tài khoản")
        ghi_that_bai(ten_dang_nhap)
        return None

    if nd["khoa"]:
        await db.log_event("auth.that_bai", actor=ten_dang_nhap[:40],
                           ly_do="tài khoản bị khoá")
        ghi_that_bai(ten_dang_nhap)
        return None

    if not kiem_mat_khau(mat_khau, nd["mat_khau_bam"]):
        await db.log_event("auth.that_bai", actor=ten_dang_nhap[:40],
                           ly_do="sai mật khẩu")
        ghi_that_bai(ten_dang_nhap)
        return None

    xoa_that_bai(ten_dang_nhap)
    token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO phien (token, nguoi_dung_id, het_han) VALUES ($1,$2,$3)",
        token, nd["id"], datetime.now(timezone.utc) + timedelta(days=PHIEN_NGAY),
    )
    await db.execute(
        "UPDATE nguoi_dung SET dang_nhap_cuoi = now() WHERE id = $1", nd["id"]
    )
    await db.log_event("auth.dang_nhap", actor=ten_dang_nhap)
    return token


async def doc_phien(token: str) -> dict | None:
    """Người đứng sau token này, hoặc None nếu phiên hỏng/hết hạn."""
    if not token:
        return None
    r = await db.fetchrow(
        "SELECT n.id, n.ten_dang_nhap, n.ho_ten, n.vai_tro, n.khoa "
        "FROM phien p JOIN nguoi_dung n ON n.id = p.nguoi_dung_id "
        "WHERE p.token = $1 AND p.het_han > now()",
        token,
    )
    if r is None or r["khoa"]:
        return None
    r["id"] = str(r["id"])
    return r


async def dang_xuat(token: str) -> None:
    if token:
        await db.execute("DELETE FROM phien WHERE token = $1", token)


async def don_phien_het_han() -> int:
    r = await db.execute("DELETE FROM phien WHERE het_han <= now()")
    phan = r.split()
    return int(phan[-1]) if phan and phan[-1].isdigit() else 0


def duoc_phep(nguoi: dict | None, viec: str) -> bool:
    """Người này có được làm việc này không."""
    if not nguoi:
        return False
    if viec in CHI_QUAN_TRI:
        return nguoi.get("vai_tro") == "quan_tri"
    return True
