"""
Kiểm kết nối kho/ERP — MỘT bộ phép kiểm, hai nơi gọi.

`scripts/thu_erp.py` in nó ra terminal; `GET /api/erp/kiem-ket-noi` trả nó
cho dashboard. Viết hai lần là hai bộ sẽ lệch nhau, và người vận hành nhận
hai câu trả lời khác nhau cho cùng một câu hỏi.

CHỈ ĐỌC
-------
Không tạo, không sửa, không xoá gì bên ERP. Có test quét mã nguồn canh việc
này — xem `tests/test_kiem_ket_noi_erp.py`.

BÍ MẬT KHÔNG BAO GIỜ RA KHỎI ĐÂY
--------------------------------
API key và secret không xuất hiện trong kết quả, kể cả dạng rút gọn. Kết quả
này đi qua HTTP tới trình duyệt và hay bị chụp màn hình gửi đi nhờ xem hộ.
"""
from __future__ import annotations

import time

from agent.config import settings
from agent.erp.hop_dong import LoiERP

TOT, CANH_BAO, CHAN = "tot", "canh_bao", "chan"

# Lấy bao nhiêu mã đem đối chiếu với danh mục nội bộ. Đủ thấy xu hướng,
# không đủ làm nghẽn một instance đang phục vụ khách.
SO_MA_DOI_CHIEU = 200

# Dưới ngưỡng này thì việc hợp nhất hai nửa dữ liệu sẽ trả rỗng cho phần
# lớn danh mục — coi là CHẶN chứ không phải cảnh báo.
NGUONG_ANH_XA = 0.9

# Trên mức này thì chốt đơn (đọc tồn sống) sẽ để khách thấy chờ.
NGUONG_TRE_MS = 2000

# Frappe mặc định phân trang 20; các mức tròn khác cũng đáng ngờ.
MUC_PHAN_TRANG = (20, 80, 100, 500)


def _muc(ten: str, muc: str, ghi_chu: str, goi_y: str = "", **them) -> dict:
    return {"ten": ten, "trang_thai": muc, "ghi_chu": ghi_chu,
            "goi_y": goi_y, **them}


async def _do(ham, *args) -> tuple[object, float]:
    t0 = time.perf_counter()
    kq = await ham(*args)
    return kq, (time.perf_counter() - t0) * 1000


async def kiem_tat_ca() -> dict:
    """Chạy toàn bộ phép kiểm. Không bao giờ ném — luôn trả một báo cáo.

    Ném ra ngoài thì endpoint trả 500 và người vận hành nhận một trang lỗi
    thay vì biết mình cấu hình thiếu chỗ nào.
    """
    loai = (settings.erp_loai or "tep").strip().lower()
    muc: list[dict] = []

    if loai == "tep":
        muc.append(_muc(
            "Cấu hình", CHAN,
            "ERP_LOAI vẫn là 'tep' — agent đọc giá và tồn kho từ tệp trên đĩa",
            "Đặt ERP_LOAI=erpnext hoặc odoo trong .env rồi khởi động lại",
        ))
        return _bao_cao(loai, muc)

    from agent.erp import nha_may

    try:
        nguon = nha_may.tao_nguon()
    except ValueError as exc:
        # Adapter tự kiểm cấu hình lúc dựng, và thông báo của nó đã nói rõ
        # thiếu biến nào cùng lý do biến đó quan trọng.
        muc.append(_muc("Cấu hình", CHAN, str(exc)))
        return _bao_cao(loai, muc)
    except Exception as exc:  # noqa: BLE001
        muc.append(_muc("Cấu hình", CHAN, f"{type(exc).__name__}: {exc}"[:200]))
        return _bao_cao(loai, muc)

    goc = {"erpnext": settings.erpnext_url,
           "odoo": settings.odoo_url}.get(loai, "")
    muc.append(_muc("Nguồn", TOT, f"{nguon.ten} → {goc or '(chưa đặt URL)'}"))

    # --- 1. Nối và xác thực được không -------------------------------
    try:
        song, tre = await _do(nguon.suc_khoe)
    except Exception as exc:  # noqa: BLE001
        muc.append(_muc("Kết nối", CHAN, f"{type(exc).__name__}: {exc}"[:150]))
        return _bao_cao(loai, muc)

    if not song:
        muc.append(_muc(
            "Kết nối", CHAN, f"không xác thực được ({tre:.0f}ms)",
            "ERPNext: kiểm ERPNEXT_URL / API_KEY / API_SECRET · "
            "Odoo: kiểm ODOO_URL / DB / DANG_NHAP / API_KEY",
        ))
        return _bao_cao(loai, muc)
    muc.append(_muc("Kết nối", TOT, f"xác thực OK, {tre:.0f}ms", latency_ms=int(tre)))

    # --- 2. Đọc được danh mục không ----------------------------------
    try:
        ds, tre_ds = await _do(nguon.danh_sach_san_pham)
    except LoiERP as exc:
        muc.append(_muc(
            "Danh mục", CHAN, str(exc)[:150],
            "Tài khoản API cần quyền đọc Item (ERPNext) / product.product (Odoo)",
        ))
        return _bao_cao(loai, muc)
    except Exception as exc:  # noqa: BLE001
        muc.append(_muc("Danh mục", CHAN, f"{type(exc).__name__}: {exc}"[:150]))
        return _bao_cao(loai, muc)

    if not ds:
        muc.append(_muc(
            "Danh mục", CHAN, "đọc được nhưng RỖNG",
            "ERPNext: không Item nào thoả disabled=0 và is_sales_item=1 · "
            "Odoo: không product.product nào thoả active và sale_ok",
        ))
        return _bao_cao(loai, muc)

    mau = ds[0]
    muc.append(_muc(
        "Danh mục", TOT,
        f"{len(ds)} sản phẩm bán được, {tre_ds:.0f}ms · ví dụ "
        f"{mau.ma} — {mau.ten}", so_san_pham=len(ds),
    ))

    # Danh mục bị cắt cụt trông y hệt một cửa hàng nhỏ. Con số tròn trịa là
    # dấu hiệu duy nhất nhìn từ ngoài.
    if len(ds) in MUC_PHAN_TRANG:
        muc.append(_muc(
            "Phân trang", CANH_BAO,
            f"đúng {len(ds)} sản phẩm — trùng một mức phân trang mặc định",
            "Kiểm xem cửa hàng có đúng chừng ấy SKU không",
        ))

    # --- 3. Giá lấy từ bảng nào --------------------------------------
    try:
        g, tre_gia = await _do(nguon.gia, mau.ma)
    except Exception as exc:  # noqa: BLE001
        muc.append(_muc("Giá", CHAN, f"{type(exc).__name__}: {exc}"[:150]))
        return _bao_cao(loai, muc)

    if g is None:
        muc.append(_muc(
            "Giá", CHAN, f"{mau.ma} không tra được giá",
            "ERPNext: ERP_PRICELIST có thể trỏ sai bảng giá · "
            "Odoo: sản phẩm chưa đặt list_price",
        ))
        return _bao_cao(loai, muc)

    muc.append(_muc("Giá", TOT,
                    f"{g.gia_ban:,} {g.don_vi} từ '{g.nguon}', {tre_gia:.0f}ms"))
    # Máy KHÔNG tự biết bảng nào là bảng bán lẻ. Nó phải nói ra và bắt người
    # xác nhận, chứ không được im lặng coi như đúng.
    muc.append(_muc(
        "Bảng giá", CANH_BAO,
        f"NGƯỜI phải xác nhận '{g.nguon}' đúng là giá BÁN LẺ",
        "Sai bảng giá thì agent báo giá sỉ cho khách lẻ, rất tự tin. "
        "Với Odoo đây là list_price, CHƯA qua pricelist.",
    ))

    # --- 4. Tồn kho lấy từ kho nào -----------------------------------
    try:
        t, tre_ton = await _do(nguon.ton_kho, mau.ma)
    except Exception as exc:  # noqa: BLE001
        t, tre_ton = None, 0.0
        muc.append(_muc("Tồn kho", CANH_BAO,
                        f"{type(exc).__name__}: {exc}"[:150]))
    if t is None:
        muc.append(_muc(
            "Tồn kho", CANH_BAO,
            f"{mau.ma} không có tồn ở kho '{settings.erp_ma_kho}'",
            "Đúng nếu món này chưa từng nhập kho đó; sai nếu ERP_MA_KHO lệch",
        ))
    else:
        muc.append(_muc("Tồn kho", TOT,
                        f"{t.ban_duoc} bán được tại {t.ma_kho}, {tre_ton:.0f}ms"))

    # --- 5. Mã có khớp danh mục nội bộ không -------------------------
    from agent.erp.anh_xa import doc_anh_xa, kiem
    from agent.erp.tep import NguonTep

    try:
        noi_bo = [sp.ma for sp in await NguonTep().danh_sach_san_pham()]
        kq = await kiem(noi_bo[:SO_MA_DOI_CHIEU], [sp.ma for sp in ds],
                        doc_anh_xa())
    except Exception as exc:  # noqa: BLE001
        kq = None
        muc.append(_muc("Ánh xạ mã", CANH_BAO,
                        f"chưa đối chiếu được: {type(exc).__name__}"))

    if kq is not None:
        if kq["tong"] == 0:
            muc.append(_muc("Ánh xạ mã", CANH_BAO,
                            "danh mục nội bộ rỗng, chưa đối chiếu được"))
        elif kq["ty_le"] >= NGUONG_ANH_XA:
            muc.append(_muc("Ánh xạ mã", TOT,
                            f"{kq['khop']}/{kq['tong']} mã nội bộ khớp ERP"))
        else:
            muc.append(_muc(
                "Ánh xạ mã", CHAN,
                f"chỉ {kq['khop']}/{kq['tong']} mã khớp ({kq['ty_le']:.0%})",
                "Thiếu: " + ", ".join(kq["thieu"][:8]) +
                " — lập data/anh_xa_ma.json",
            ))

    # --- 6. Độ trễ quyết định TTL ------------------------------------
    cham = max(tre, tre_ds, tre_gia)
    if cham > NGUONG_TRE_MS:
        muc.append(_muc(
            "Độ trễ", CANH_BAO,
            f"chậm nhất {cham:.0f}ms — chốt đơn đọc tồn SỐNG nên khách sẽ chờ",
            "Cân nhắc nới ERP_NGAT_MACH_GIAY, và đo lại vào giờ cao điểm",
            latency_ms=int(cham),
        ))
    else:
        muc.append(_muc("Độ trễ", TOT,
                        f"chậm nhất {cham:.0f}ms — đủ nhanh cho tồn sống lúc "
                        "chốt đơn", latency_ms=int(cham)))

    return _bao_cao(loai, muc)


def _bao_cao(loai: str, muc: list[dict]) -> dict:
    co_chan = any(m["trang_thai"] == CHAN for m in muc)
    co_canh = any(m["trang_thai"] == CANH_BAO for m in muc)
    return {
        "erp_loai": loai,
        "ghi_don": bool(settings.erp_ghi_don),
        "ma_kho": settings.erp_ma_kho or "",
        "pricelist": settings.erp_pricelist or "",
        "trang_thai": CHAN if co_chan else (CANH_BAO if co_canh else TOT),
        "san_sang": not co_chan,
        "muc": muc,
    }
