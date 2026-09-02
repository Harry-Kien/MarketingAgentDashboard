"""
Hợp đồng dữ liệu giữa hệ thống và kho/ERP.

VÌ SAO CÓ LỚP NÀY
-----------------
Odoo nói XML-RPC và gọi sản phẩm là `product.product`. ERPNext nói REST và
gọi nó là `Item`. Nếu `tools.py` biết điều đó thì đổi ERP là viết lại agent.

Hợp đồng ở đây là thứ DUY NHẤT phần còn lại của hệ thống được biết. Mỗi
adapter tự lo phần bẩn của ERP nó phục vụ.

VÌ SAO `Gia` LÀ MỘT VẬT, KHÔNG PHẢI MỘT `int`
---------------------------------------------
Cả Odoo lẫn ERPNext đều có bảng giá: giá phụ thuộc nhóm khách, số lượng,
ngày, khuyến mãi. Trả về `int` trần là vứt mất `nguon` — và khi khách hỏi
"sao lại báo giá này" thì không ai truy được nó đến từ bảng giá nào.

VÌ SAO `TonKho.ban_duoc` CHỨ KHÔNG PHẢI `ton_kho`
-------------------------------------------------
Hàng có trong kho khác hàng bán được: một phần đã bị đơn khác giữ chỗ.
Odoo gọi phần bán được là `free_qty`; ERPNext là `actual_qty - reserved_qty`.
Lấy nhầm sang tổng tồn là hứa bán món đã có người đặt. Đặt tên trường theo
đúng ý nghĩa để không ai gán nhầm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LoiERP(RuntimeError):
    """Gọi ERP không thành. Cổng bắt lỗi này để quyết định trả `None`."""


class TuChoiERP(LoiERP):
    """ERP HIỂU yêu cầu và từ chối nó.

    Khác `LoiERP` ở một điểm quyết định cách xử lý: từ chối là một CÂU TRẢ
    LỜI, thử lại bao nhiêu lần cũng vẫn thế. Mất mạng hay 5xx thì ngược lại —
    ta không biết ERP đã ghi hay chưa, và phải thử lại.

    Gộp hai thứ này làm một là hoặc thử lại vô ích một đơn ERP sẽ luôn từ
    chối, hoặc bỏ mất một đơn chỉ vì mạng chớp.
    """


@dataclass(frozen=True)
class Gia:
    """Giá bán một sản phẩm, kèm nguồn để truy vết."""

    gia_ban: int
    don_vi: str = "VND"
    nguon: str = ""
    hieu_luc_den: str | None = None


@dataclass(frozen=True)
class TonKho:
    """Số lượng BÁN ĐƯỢC (đã trừ phần bị giữ chỗ), tại một kho."""

    ban_duoc: int
    ma_kho: str = ""


@dataclass(frozen=True)
class Lo:
    """
    Một lô hàng, kèm hạn dùng. Chỉ dùng cho ngành có hạn: mỹ phẩm, thực
    phẩm, dược.

    `so_luong = None` nghĩa là ERPNext KHÔNG trả về số lượng của lô này —
    không phải lô rỗng. Phân biệt hai thứ đó là bắt buộc: bản ERPNext v15
    chuyển số lượng lô sang `Serial and Batch Bundle`, nên trường
    `batch_qty` có bản có, bản không.

    Coi `None` là 0 thì mọi lô đều trông như đã bán hết và agent im lặng về
    hạn dùng. Coi `None` là "còn hàng" thì agent báo hạn của một lô đã hết
    sạch — khách nghe "hạn tới 2027" rồi nhận lọ hết hạn tháng sau. Cái
    thứ hai là thứ phải tránh, nên `None` được xử lý TƯỜNG MINH ở
    `Cong.han_dung()` chứ không rơi vào nhánh mặc định nào.
    """

    ma_lo: str
    het_han: str | None = None      # ISO yyyy-mm-dd; None = lô không quản hạn
    so_luong: int | None = None     # None = KHÔNG BIẾT, khác 0


@dataclass(frozen=True)
class SanPhamERP:
    """Nửa thương mại của một sản phẩm. Nửa tư vấn nằm ở kho nội bộ."""

    ma: str
    ten: str
    loai: str = ""
    dung_tich: str = ""
    ban_duoc_phep: bool = True


@dataclass(frozen=True)
class KetQuaDon:
    """Kết quả đẩy một đơn sang ERP. Dùng ở giai đoạn 4."""

    thanh_cong: bool
    erp_ma_don: str = ""
    ly_do: str = ""


@runtime_checkable
class NguonERP(Protocol):
    """Bốn việc mọi adapter phải làm được. Không hơn.

    Giữ hợp đồng nhỏ là cố ý: mỗi phương thức thêm vào là một phương thức
    phải hiện thực đúng bốn lần và test đúng bốn lần.
    """

    ten: str

    async def danh_sach_san_pham(
        self, chi_ban_duoc: bool = True
    ) -> list[SanPhamERP]: ...

    async def gia(self, ma: str) -> Gia | None: ...

    async def ton_kho(self, ma: str) -> TonKho | None: ...

    async def suc_khoe(self) -> bool: ...

    # `lo_hang(ma) -> list[Lo]` là NĂNG LỰC TUỲ CHỌN, cố ý không nằm trong
    # Protocol này.
    #
    # Không phải ngành nào cũng quản lô: cửa hàng đồ thể thao không có hạn
    # dùng, và bắt adapter của họ hiện thực một phương thức luôn trả rỗng
    # là thêm mã chết ở bốn nơi. `Cong` dò bằng `getattr` và bỏ qua nếu
    # adapter không có — xem `Cong.lo_hang()`.


@dataclass(frozen=True)
class DongDon:
    """Một dòng hàng trong đơn gửi sang ERP."""

    ma: str
    so_luong: int
    don_gia: int


@runtime_checkable
class NguonGhiERP(Protocol):
    """Ba việc thêm, CHỈ cho adapter được phép ghi vào ERP.

    VÌ SAO TÁCH KHỎI `NguonERP` CHỨ KHÔNG GỘP VÀO
    ---------------------------------------------
    Đọc và ghi có mức rủi ro khác hẳn nhau. Đọc sai thì agent trả lời sai —
    sửa được. Ghi sai thì đơn trùng và bản ghi khách rác nằm vĩnh viễn trong
    ERP của cửa hàng — không rút lại được.

    Tách ra thì `isinstance(nguon, NguonGhiERP)` là một câu hỏi có nghĩa, và
    adapter `tep` (đọc file trên đĩa) KHÔNG vô tình mang theo khả năng ghi
    chỉ vì nó nằm chung một hợp đồng.

    VÌ SAO CÓ `an_danh_khach`
    -------------------------
    Từ lúc đẩy đơn, tên — số điện thoại — địa chỉ khách nằm trong ERP VĨNH
    VIỄN. Khách có quyền yêu cầu xoá (Nghị định 13/2023), và không có đường
    này thì hệ thống báo "đã xoá" trong khi dữ liệu còn nguyên ở đó.

    ẨN DANH chứ không xoá hẳn: ERP không cho xoá bản ghi đã có chứng từ, và
    nghĩa vụ lưu sổ sách kế toán vẫn còn. Ẩn danh giữ được chứng từ mà không
    giữ người — cùng cách đơn hàng nội bộ đang làm.

    VÌ SAO CÓ `tim_don`
    -------------------
    ERP có thể đã nhận đơn nhưng mạng đứt trước khi ta thấy phản hồi. Lần
    thử lại sẽ tạo đơn thứ hai nếu không tra trước. Đây là lưới đầu tiên
    trong bốn lưới chống đơn trùng; lưới cuối là ràng buộc UNIQUE trên
    `orders.erp_ma_don`.
    """

    async def bao_dam_khach(
        self, ten: str, sdt: str, dia_chi: str
    ) -> str: ...

    async def tim_don(self, khoa: str) -> str | None: ...

    async def tao_don(
        self, khoa: str, khach_id: str, dong: list[DongDon], ghi_chu: str = ""
    ) -> KetQuaDon: ...

    async def an_danh_khach(self, sdt: str) -> int: ...

    async def trang_thai_giao(self, erp_ma_don: str) -> str | None: ...
