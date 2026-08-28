"""
Gọi thật vào ERP và in ra thứ nó tìm thấy — không đoán, không suy diễn.

    python -m scripts.thu_erp

VÌ SAO CẦN LỆNH NÀY
-------------------
`agent/erp/erpnext.py` được dựng theo tài liệu Frappe, chưa từng gọi vào một
instance thật nào. Bốn thứ dưới đây KHÔNG thể biết được nếu không gọi thử,
và cả bốn đều hỏng theo kiểu im lặng:

  1. Tên trường ở bản ERPNext của bạn có đúng như tài liệu không.
  2. Mã sản phẩm nội bộ có khớp `item_code` bên ERP không. Không khớp thì
     việc hợp nhất hai nửa dữ liệu lặng lẽ trả rỗng.
  3. `ERP_PRICELIST` có đúng là bảng giá bán lẻ đang dùng không. Sai bảng
     giá thì agent báo giá sỉ cho khách lẻ, rất tự tin.
  4. Độ trễ thật — quyết định `ERP_TTL_TON` và `ERP_NGAT_MACH_GIAY` nên đặt
     bao nhiêu. Con số mặc định trong `config.py` là chỗ bắt đầu, không phải
     kết luận.

Lệnh này CHỈ ĐỌC. Nó không tạo, không sửa, không xoá gì bên ERP.

BÍ MẬT KHÔNG BAO GIỜ IN RA
--------------------------
API key và secret không xuất hiện trong đầu ra, kể cả dạng rút gọn. Đầu ra
của lệnh này hay bị dán vào chat để nhờ xem hộ.
"""
from __future__ import annotations

import asyncio
import sys
import time

from agent.config import settings
from agent.erp.hop_dong import LoiERP

# Lấy bao nhiêu mã đem đi đối chiếu với danh mục nội bộ. Đủ để thấy xu
# hướng, không đủ để làm nghẽn một instance đang phục vụ khách.
SO_MA_DOI_CHIEU = 200

_XANH, _VANG, _DO, _TAT = "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def _in(muc: str, ten: str, noi_dung: str, goi_y: str = "") -> None:
    mau = {"đủ": _XANH, "cảnh báo": _VANG, "chặn": _DO}.get(muc, "")
    print(f"{mau}[{muc}]{_TAT} {ten:<26} {noi_dung}")
    if goi_y:
        print(f"             └─ {goi_y}")


async def _do_do_tre(ham, *args) -> tuple[object, float]:
    t0 = time.perf_counter()
    kq = await ham(*args)
    return kq, (time.perf_counter() - t0) * 1000


async def chay() -> int:
    loai = (settings.erp_loai or "tep").strip().lower()
    print("─" * 62)
    print(f"Thử kết nối ERP — ERP_LOAI={loai}")
    print("─" * 62)

    if loai == "tep":
        _in("chặn", "Cấu hình", "ERP_LOAI vẫn là 'tep' (đọc file trên đĩa)",
            "Đặt ERP_LOAI=erpnext hoặc odoo trong .env rồi chạy lại")
        return 1

    from agent.erp import nha_may

    co_chan = False

    try:
        nguon = nha_may.tao_nguon()
    except ValueError as exc:
        # Adapter tự kiểm cấu hình lúc dựng. Thông báo của nó đã nói rõ
        # thiếu biến nào và vì sao biến đó quan trọng.
        _in("chặn", "Cấu hình", str(exc))
        return 1

    goc = {"erpnext": settings.erpnext_url, "odoo": settings.odoo_url}.get(loai, "")
    _in("đủ", "Nguồn", f"{nguon.ten} → {goc or '(chưa đặt)'}")

    # --- 1. Nối được không -------------------------------------------
    song, tre = await _do_do_tre(nguon.suc_khoe)
    if not song:
        _in("chặn", "Kết nối", f"không xác thực được ({tre:.0f}ms)",
            "ERPNext: kiểm ERPNEXT_URL/API_KEY/API_SECRET · "
            "Odoo: kiểm ODOO_URL/DB/DANG_NHAP/API_KEY")
        return 1
    _in("đủ", "Kết nối", f"xác thực OK, {tre:.0f}ms")

    # --- 2. Đọc được danh mục không ----------------------------------
    try:
        ds, tre_ds = await _do_do_tre(nguon.danh_sach_san_pham)
    except LoiERP as exc:
        _in("chặn", "Danh mục", str(exc),
            "Tài khoản API cần quyền đọc Item (ERPNext) / "
            "product.product (Odoo)")
        return 1

    if not ds:
        _in("chặn", "Danh mục", "đọc được nhưng RỖNG",
            "ERPNext: không Item nào thoả disabled=0 và is_sales_item=1 · "
            "Odoo: không product.product nào thoả active và sale_ok")
        return 1
    _in("đủ", "Danh mục", f"{len(ds)} sản phẩm bán được, {tre_ds:.0f}ms")

    # Cắt cụt do phân trang trông y hệt cửa hàng nhỏ. Con số tròn trịa của
    # Frappe là dấu hiệu đáng ngờ nhất.
    if len(ds) in (20, 80, 100, 500):
        _in("cảnh báo", "Phân trang",
            f"đúng {len(ds)} — trùng một mức phân trang mặc định",
            "Kiểm xem cửa hàng có đúng chừng ấy SKU không")

    mau = ds[0]
    print(f"             ví dụ: {mau.ma} · {mau.ten} · nhóm {mau.loai or '—'}")

    # --- 3. Giá lấy đúng bảng nào ------------------------------------
    g, tre_gia = await _do_do_tre(nguon.gia, mau.ma)
    if g is None:
        _in("chặn", "Giá", f"{mau.ma} không tra được giá",
            "ERPNext: ERP_PRICELIST có thể trỏ sai bảng giá · "
            "Odoo: sản phẩm chưa đặt list_price")
        return 1
    _in("đủ", "Giá", f"{g.gia_ban:,} {g.don_vi} từ '{g.nguon}', {tre_gia:.0f}ms")
    _in("cảnh báo", "Bảng giá",
        f"NGƯỜI phải xác nhận '{g.nguon}' đúng là giá BÁN LẺ",
        "Sai bảng giá thì agent báo giá sỉ cho khách lẻ, rất tự tin. "
        "Với Odoo đây là list_price, CHƯA qua pricelist.")

    # --- 4. Tồn kho lấy đúng kho nào ---------------------------------
    t, tre_ton = await _do_do_tre(nguon.ton_kho, mau.ma)
    if t is None:
        _in("cảnh báo", "Tồn kho",
            f"{mau.ma} không có bản ghi Bin ở kho '{settings.erp_ma_kho}'",
            "Đúng nếu món này chưa từng nhập kho đó; sai nếu ERP_MA_KHO lệch")
    else:
        _in("đủ", "Tồn kho",
            f"{t.ban_duoc} bán được tại {t.ma_kho}, {tre_ton:.0f}ms")

    # --- 5. Mã có khớp danh mục nội bộ không -------------------------
    from agent.erp.anh_xa import doc_anh_xa, kiem
    from agent.erp.tep import NguonTep

    noi_bo = [sp.ma for sp in await NguonTep().danh_sach_san_pham()]
    kq = await kiem([m for m in noi_bo][:SO_MA_DOI_CHIEU],
                    [sp.ma for sp in ds], doc_anh_xa())
    if kq["tong"] == 0:
        _in("cảnh báo", "Ánh xạ mã", "danh mục nội bộ rỗng, chưa đối chiếu được")
    elif kq["ty_le"] >= 0.9:
        _in("đủ", "Ánh xạ mã",
            f"{kq['khop']}/{kq['tong']} mã nội bộ khớp ERP")
    else:
        # Có in `[chặn]` thì PHẢI thoát khác 0. In cảnh báo đỏ rồi trả 0 là
        # đúng thứ hỏng im lặng mà cả repo này chống: ai gói lệnh vào script
        # tự động sẽ đọc mã thoát, không đọc màu chữ.
        co_chan = True
        _in("chặn", "Ánh xạ mã",
            f"chỉ {kq['khop']}/{kq['tong']} mã khớp "
            f"({kq['ty_le']:.0%})",
            "Thiếu: " + ", ".join(kq["thieu"][:8]) +
            " — lập data/anh_xa_ma.json")

    # --- 6. Độ trễ quyết định TTL ------------------------------------
    print("─" * 62)
    cham_nhat = max(tre, tre_ds, tre_gia)
    print(f"Độ trễ chậm nhất đo được: {cham_nhat:.0f}ms")
    if cham_nhat > 2000:
        _in("cảnh báo", "Độ trễ",
            "trên 2 giây — chốt đơn đọc tồn SỐNG nên khách sẽ thấy chờ",
            "Cân nhắc nới ERP_NGAT_MACH_GIAY, và đo lại vào giờ cao điểm")
    else:
        _in("đủ", "Độ trễ", "đủ nhanh cho việc đọc tồn sống lúc chốt đơn")
    print("Con số mặc định ERP_TTL_TON=60, ERP_NGAT_MACH_GIAY=30 là chỗ BẮT")
    print("ĐẦU. Đo lại vào giờ cao điểm rồi chỉnh, đừng để nguyên vì nó tròn.")
    print("─" * 62)
    if co_chan:
        print("CHƯA DÙNG ĐƯỢC: còn việc CHẶN ở trên.")
    return 1 if co_chan else 0


def main() -> None:
    sys.exit(asyncio.run(chay()))


if __name__ == "__main__":
    main()
