"""
Kho hàng — tồn kho thật, thay đổi theo giao dịch.

VẤN ĐỀ TRƯỚC LỚP NÀY
--------------------
`ton_kho` là một con số nằm trong `data/catalog.json`. Agent ĐỌC nó để trả
lời "còn hàng không", nhưng chốt đơn xong thì con số không đổi. Bán một
trăm đơn của sản phẩm còn 19 cái thì nó vẫn báo 19.

Với khách, hậu quả là được xác nhận đơn cho món đã hết. Với doanh nghiệp,
là một cuộc gọi xin lỗi và một đơn huỷ.

TÁCH DỮ LIỆU THAM CHIẾU KHỎI DỮ LIỆU GIAO DỊCH
----------------------------------------------
Tên, giá, thành phần, cách dùng ít đổi và nên nằm trong file — dễ đọc, dễ
sửa, vào được git. Tồn kho thì đổi mỗi lần bán, nên phải nằm trong CSDL nơi
có giao dịch và khoá hàng.

Nên `data/catalog.json` vẫn là nguồn của thông tin sản phẩm, còn số tồn
sống nằm ở bảng `ton_kho` và được chồng lên khi đọc danh mục.

MỌI THAY ĐỔI ĐỀU ĐƯỢC GHI LẠI
-----------------------------
Bảng `kho_bien_dong` ghi từng lần cộng trừ kèm lý do và mã đơn. Không có
sổ này thì khi tồn kho lệch với thực tế, không ai truy được lệch từ đâu —
và tồn kho LUÔN lệch, đó là chuyện thường ngày của mọi kho hàng.
"""
from __future__ import annotations

from typing import Any

from .. import db

# Dưới mức này thì cảnh báo trên dashboard. Không phải con số khoa học —
# nó là "đủ để kịp nhập thêm trước khi hết", và mỗi ngành một khác.
NGUONG_SAP_HET = 10


async def dong_bo_tu_danh_muc(san_pham: list[dict]) -> int:
    """
    Nạp tồn kho ban đầu từ danh mục. Chạy một lần khi khởi động.

    KHÔNG ghi đè số đang có: file danh mục là ảnh chụp lúc viết ra, còn
    bảng này là số sống. Ghi đè là xoá sạch lịch sử bán hàng.
    """
    them = 0
    for sp in san_pham:
        ma = sp.get("ma")
        if not ma:
            continue
        r = await db.fetchrow(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ($1, $2) "
            "ON CONFLICT (ma) DO NOTHING RETURNING ma",
            ma, int(sp.get("ton_kho") or 0),
        )
        if r:
            them += 1
    return them


async def lay_tat_ca() -> dict[str, int]:
    """Số tồn sống của mọi mã, để chồng lên danh mục khi đọc."""
    rows = await db.fetch("SELECT ma, so_luong FROM ton_kho")
    return {r["ma"]: int(r["so_luong"]) for r in rows}


async def lay(ma: str) -> int | None:
    r = await db.fetchrow("SELECT so_luong FROM ton_kho WHERE ma = $1", ma)
    return int(r["so_luong"]) if r else None


async def giu_hang(items: list[dict], ma_don: str) -> tuple[bool, str]:
    """
    Trừ kho cho một đơn. Trả (thành công, lý do nếu hỏng).

    NGUYÊN TỬ VÀ CÓ KHOÁ HÀNG. Hai khách cùng chốt món cuối cùng trong một
    giây là chuyện có thật; không khoá thì cả hai đều được xác nhận và một
    người sẽ nhận cuộc gọi xin lỗi.

    Trừ được HẾT hoặc KHÔNG TRỪ GÌ. Trừ một nửa rồi hết hàng ở món thứ ba
    là để lại một đơn dở dang và một kho sai số.
    """
    if not items:
        return True, ""

    # GỘP THEO MÃ trước khi kiểm và trừ. Hai dòng cùng mã (khách gọi một
    # món hai lần, hoặc hai tên gần nhau khớp cùng một sản phẩm) mà kiểm
    # riêng từng dòng thì dòng nào cũng "đủ", rồi UPDATE thứ hai đâm vào
    # CHECK so_luong >= 0 và NÉM LỖI — đơn đã INSERT nằm lại mà kho không
    # trừ (rà soát 11.2026). Gộp lại thì "không đủ" là một câu trả lời
    # bình thường, không phải một ngoại lệ.
    gop: dict[str, int] = {}
    ten_cua: dict[str, str] = {}
    for it in items:
        ma, sl = it.get("ma"), int(it.get("so_luong") or 1)
        if not ma:
            continue
        gop[ma] = gop.get(ma, 0) + sl
        ten_cua.setdefault(ma, str(it.get("ten") or ma))

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            # Khoá theo thứ tự mã cố định: hai đơn cùng chứa A và B mà khoá
            # ngược thứ tự nhau là deadlock.
            for ma in sorted(gop):
                sl = gop[ma]
                # FOR UPDATE khoá đúng dòng này tới hết giao dịch.
                row = await conn.fetchrow(
                    "SELECT so_luong FROM ton_kho WHERE ma = $1 FOR UPDATE", ma
                )
                if row is None:
                    return False, f"Mã {ma} không có trong kho."
                con = int(row["so_luong"])
                if con < sl:
                    ten = ten_cua[ma]
                    return False, (
                        f"{ten} chỉ còn {con} sản phẩm, không đủ {sl}."
                        if con else f"{ten} đã hết hàng."
                    )

            # Tới đây là chắc chắn đủ cả lô -> mới trừ.
            for ma in sorted(gop):
                sl = gop[ma]
                await conn.execute(
                    "UPDATE ton_kho SET so_luong = so_luong - $2, cap_nhat_luc = now() "
                    "WHERE ma = $1", ma, sl,
                )
                await conn.execute(
                    "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don) "
                    "VALUES ($1, $2, 'ban', $3)", ma, -sl, ma_don,
                )
    return True, ""


# Mọi lý do CỘNG HÀNG LẠI vào kho. Thêm lý do mới mà quên khai ở đây vẫn an
# toàn: `tra_hang` luôn gộp thêm `ly_do` của chính lời gọi vào tập này.
LY_DO_HOAN = frozenset({"huy_don", "hoan_hang", "erp_tu_choi"})


async def tra_hang(ma_don: str, ly_do: str = "huy_don") -> int:
    """
    Trả lại kho khi đơn bị huỷ.

    Đọc từ sổ biến động chứ không đọc từ đơn: sổ là thứ ghi CHÍNH XÁC đã
    trừ bao nhiêu. Đơn có thể đã bị sửa, sổ thì không.

    Không trả trùng: mỗi lần bán chỉ được hoàn đúng một lần — với MỌI lý do
    hoàn cộng lại, không phải mỗi lý do một lần. Bản trước chặn trùng theo
    từng `ly_do`: shop huỷ đơn (huy_don) rồi GHTK báo hàng về (hoan_hang) là
    cộng kho HAI lần, kho báo có hàng trong khi kệ trống (rà soát 28.10.2026).
    Kiểm trong giao dịch, có khoá theo mã đơn: hai webhook tới cùng lúc không
    được cùng thấy "chưa hoàn".
    """
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('tra_hang:' || $1))", ma_don)
            da_hoan = await conn.fetchrow(
                "SELECT 1 FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = ANY($2::text[]) LIMIT 1",
                ma_don, sorted(LY_DO_HOAN | {ly_do}),
            )
            if da_hoan:
                return 0
            ban = await conn.fetch(
                "SELECT ma, thay_doi FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = 'ban'",
                ma_don,
            )
            if not ban:
                return 0
            for b in ban:
                sl = abs(int(b["thay_doi"]))
                await conn.execute(
                    "UPDATE ton_kho SET so_luong = so_luong + $2, cap_nhat_luc = now() "
                    "WHERE ma = $1", b["ma"], sl,
                )
                await conn.execute(
                    "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don) "
                    "VALUES ($1, $2, $3, $4)", b["ma"], sl, ly_do, ma_don,
                )
    return len(ban)


class LoiNhapHangHoan(ValueError):
    """Từ chối nhập hàng hoàn do không đủ điều kiện đơn hoặc vượt số lượng."""

    def __init__(self, ma: int, thong_diep: str) -> None:
        super().__init__(thong_diep)
        self.ma = ma
        self.thong_diep = thong_diep


async def nhap_hang(ma: str, so_luong: int, ghi_chu: str = "", *, khoa_chong_trung: str = "") -> dict:
    """Nhập thêm hàng thông thường (từ nhà cung cấp). Người vận hành bấm trên dashboard."""
    # pyrefly: ignore[unnecessary-type-conversion]
    so_luong = int(so_luong)
    if so_luong <= 0:
        raise ValueError("Số lượng nhập phải lớn hơn 0")
    khoa = (khoa_chong_trung or "").strip() or None

    # Cộng kho và ghi sổ trong CÙNG giao dịch. Tách hai câu thì lỗi ở câu
    # thứ hai để lại kho đã cộng mà sổ không có dòng nào — đúng loại lệch
    # mà sổ biến động sinh ra để truy.
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if khoa:
                cu = await conn.fetchrow(
                    "SELECT id, ma, thay_doi FROM kho_bien_dong WHERE khoa_chong_trung = $1",
                    khoa,
                )
                if cu is not None:
                    ton = await conn.fetchrow("SELECT ma, so_luong FROM ton_kho WHERE ma = $1", ma)
                    return {
                        "ma": ma,
                        "ton_moi": int(ton["so_luong"]) if ton else 0,
                        "ly_do": "nhap",
                        "bien_dong_id": int(cu["id"]),
                        "da_nhap_tu_truoc": True,
                    }
            row = await conn.fetchrow(
                "UPDATE ton_kho SET so_luong = so_luong + $2, cap_nhat_luc = now() "
                "WHERE ma = $1 RETURNING ma, so_luong", ma, so_luong,
            )
            if row is None:
                raise LookupError(f"Không có mã {ma} trong kho")
            bd = await conn.fetchrow(
                "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu, khoa_chong_trung) "
                "VALUES ($1, $2, 'nhap', $3, $4) RETURNING id",
                ma, so_luong, ghi_chu, khoa,
            )
    return {
        "ma": row["ma"],
        "ton_moi": int(row["so_luong"]),
        "ly_do": "nhap",
        "bien_dong_id": int(bd["id"]),
        "da_nhap_tu_truoc": False,
    }


def _don_du_dieu_kien_nhap_hoan(don: dict) -> tuple[bool, str]:
    """
    Chỉ cho nhập hàng hoàn từ đơn thực sự đủ điều kiện hoàn về kho:
      1. Vận đơn đã được hãng xác nhận hoàn về shop (`trang_thai_giao_hang = 'returned'`).
      2. Vận đơn đã huỷ (`cancelled`) nhưng đơn cũ/đã lấy hàng (`van_don_da_lay_hang IS NOT FALSE`)
         đang chờ kiểm tra hàng thực tế tại kho.
      3. Đơn đã giao (`da_giao`) có ghi nhận yêu cầu đổi/trả (`yeu_cau_doi_tra_luc IS NOT NULL`).
    """
    tt_don = str(don.get("trang_thai") or "")
    tt_giao = str(don.get("trang_thai_giao_hang") or "")
    da_lay = don.get("van_don_da_lay_hang")

    if tt_giao == "returned":
        return True, ""
    if tt_giao == "cancelled" and da_lay is not False:
        return True, ""
    if tt_don == "da_giao" and don.get("yeu_cau_doi_tra_luc") is not None:
        return True, ""
    return (
        False,
        f"Đơn {don.get('ma_don')} (trạng thái '{tt_don}', giao hàng '{tt_giao or 'chưa có'}') "
        "chưa đủ điều kiện nhập hàng hoàn. Chỉ nhập hàng hoàn cho đơn đã hoàn về kho "
        "(returned), đơn huỷ vận đơn chờ kiểm kho hoặc đơn đã giao có yêu cầu đổi/trả.",
    )


async def nhap_hang_hoan(
    ma: str,
    so_luong: int,
    ma_don: str,
    ghi_chu: str = "",
    *,
    khoa_chong_trung: str = "",
    actor_id=None,
) -> dict:
    """
    Nhập hàng hoàn từ một đơn hàng cụ thể (`ly_do = 'hoan_hang'`, gắn `ma_don`).

    Bảo toàn 4 bất biến:
      - Khóa `pg_advisory_xact_lock('tra_hang:' || ma_don)` cùng khoá với
        `tra_hang()` để tuần tự hoá mọi thao tác hoàn tồn đồng thời.
      - Chống nhập lặp khi retry theo `khoa_chong_trung` (cả hoàn một phần).
      - Chỉ cho nhập từ đơn đủ điều kiện hoàn hàng và sản phẩm có xuất bán trên đơn.
      - Tổng hoàn (`huy_don` + `hoan_hang` + `erp_tu_choi`) không vượt quá tổng đã bán.
      - Ghi nhận tiến độ kèm `bien_dong_id` vào công việc kiểm tra hàng hoàn nếu có.
    """
    # pyrefly: ignore[unnecessary-type-conversion]
    so_luong = int(so_luong)
    if so_luong <= 0:
        raise ValueError("Số lượng nhập hoàn phải lớn hơn 0")
    # pyrefly: ignore[unnecessary-type-conversion]
    ma_don_sach = str(ma_don or "").strip()
    if not ma_don_sach:
        raise ValueError("Nhập hàng hoàn bắt buộc phải nhập mã đơn hàng")
    khoa = (khoa_chong_trung or "").strip() or None
    ly_do_tinh = sorted(LY_DO_HOAN)

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtext('tra_hang:' || $1))",
                ma_don_sach,
            )

            # 1. Chống trùng theo khoa_chong_trung (retry / double-click)
            if khoa:
                cu = await conn.fetchrow(
                    "SELECT id, ma, ma_don, thay_doi FROM kho_bien_dong "
                    "WHERE khoa_chong_trung = $1",
                    khoa,
                )
                if cu is not None:
                    if str(cu["ma"]) != ma or str(cu["ma_don"] or "") != ma_don_sach:
                        raise LoiNhapHangHoan(
                            409,
                            "Khoá chống trùng đã được dùng cho sản phẩm hoặc đơn hàng khác.",
                        )
                    ton_cu = await conn.fetchrow("SELECT so_luong FROM ton_kho WHERE ma = $1", ma)
                    da_ban_cu = await conn.fetchrow(
                        "SELECT COALESCE(SUM(ABS(thay_doi)), 0) AS n FROM kho_bien_dong "
                        "WHERE ma_don = $1 AND ma = $2 AND ly_do = 'ban'",
                        ma_don_sach, ma,
                    )
                    da_hoan_cu = await conn.fetchrow(
                        "SELECT COALESCE(SUM(thay_doi), 0) AS n FROM kho_bien_dong "
                        "WHERE ma_don = $1 AND ma = $2 AND ly_do = ANY($3::text[])",
                        ma_don_sach, ma, ly_do_tinh,
                    )
                    ban_n = int((da_ban_cu or {}).get("n") or 0)
                    hoan_n = int((da_hoan_cu or {}).get("n") or 0)
                    return {
                        "ma": ma,
                        "ton_moi": int(ton_cu["so_luong"]) if ton_cu else 0,
                        "ma_don": ma_don_sach,
                        "ly_do": "hoan_hang",
                        "bien_dong_id": int(cu["id"]),
                        "da_ban": ban_n,
                        "da_hoan": hoan_n,
                        "con_lai": max(0, ban_n - hoan_n),
                        "da_nhap_tu_truoc": True,
                    }

            # 2. Kiểm tra đơn hàng và điều kiện hoàn
            don = await conn.fetchrow(
                """
                SELECT id, ma_don, trang_thai, trang_thai_giao_hang,
                       van_don_da_lay_hang, yeu_cau_doi_tra_luc
                FROM orders WHERE ma_don = $1 FOR UPDATE
                """,
                ma_don_sach,
            )
            if don is None:
                raise LoiNhapHangHoan(404, f"Không tìm thấy đơn hàng {ma_don_sach}.")
            hop_le, ly_do_tu_choi = _don_du_dieu_kien_nhap_hoan(dict(don))
            if not hop_le:
                raise LoiNhapHangHoan(409, ly_do_tu_choi)

            # 3. Kiểm tra giới hạn số lượng theo sổ biến động của đơn
            ban_row = await conn.fetchrow(
                "SELECT COALESCE(SUM(ABS(thay_doi)), 0) AS n FROM kho_bien_dong "
                "WHERE ma_don = $1 AND ma = $2 AND ly_do = 'ban'",
                ma_don_sach, ma,
            )
            da_ban = int((ban_row or {}).get("n") or 0)
            if da_ban <= 0:
                raise LoiNhapHangHoan(
                    409,
                    f"Đơn {ma_don_sach} không có biến động xuất bán cho mã hàng {ma}.",
                )

            hoan_row = await conn.fetchrow(
                "SELECT COALESCE(SUM(thay_doi), 0) AS n FROM kho_bien_dong "
                "WHERE ma_don = $1 AND ma = $2 AND ly_do = ANY($3::text[])",
                ma_don_sach, ma, ly_do_tinh,
            )
            da_hoan = int((hoan_row or {}).get("n") or 0)
            con_lai = da_ban - da_hoan
            if con_lai <= 0:
                raise LoiNhapHangHoan(
                    409,
                    f"Mã {ma} của đơn {ma_don_sach} đã hoàn đủ {da_hoan}/{da_ban} sản phẩm — "
                    "không thể nhập hoàn thêm.",
                )
            if so_luong > con_lai:
                raise LoiNhapHangHoan(
                    409,
                    f"Số lượng nhập hoàn ({so_luong}) vượt quá số còn lại có thể hoàn "
                    f"({con_lai}/{da_ban}, đã hoàn trước đó {da_hoan}) cho mã {ma} của đơn {ma_don_sach}.",
                )

            # 4. Cộng tồn kho & ghi sổ biến động gắn ma_don + ly_do='hoan_hang'
            row = await conn.fetchrow(
                "UPDATE ton_kho SET so_luong = so_luong + $2, cap_nhat_luc = now() "
                "WHERE ma = $1 RETURNING ma, so_luong",
                ma, so_luong,
            )
            if row is None:
                raise LookupError(f"Không có mã {ma} trong kho")
            bd = await conn.fetchrow(
                "INSERT INTO kho_bien_dong "
                "(ma, thay_doi, ly_do, ma_don, ghi_chu, khoa_chong_trung) "
                "VALUES ($1, $2, 'hoan_hang', $3, $4, $5) RETURNING id",
                ma, so_luong, ma_don_sach, ghi_chu, khoa,
            )
            bd_id = int(bd["id"])
            da_hoan_moi = da_hoan + so_luong
            con_lai_moi = da_ban - da_hoan_moi

            # 5. Ghi nhận biến động kho vào công việc kiểm tra hàng hoàn liên quan (nếu có)
            viec = await conn.fetchrow(
                """
                SELECT id, order_id FROM cong_viec
                WHERE order_id = $1
                   OR khoa_chong_trung IN ($2, $3)
                ORDER BY CASE WHEN trang_thai IN ('moi', 'dang_lam') THEN 0 ELSE 1 END,
                         tao_luc DESC
                LIMIT 1
                """,
                don["id"],
                f"don_hang:kiem_hang_hoan:{ma_don_sach}",
                f"don_hang:kiem_kho_huy_vd:{ma_don_sach}",
            )
            viec_id = None
            if viec is not None:
                viec_id = viec["id"]
                if viec["order_id"] is None:
                    await conn.execute(
                        "UPDATE cong_viec SET order_id = $2, sua_luc = now() WHERE id = $1",
                        viec_id, don["id"],
                    )
                else:
                    await conn.execute(
                        "UPDATE cong_viec SET sua_luc = now() WHERE id = $1",
                        viec_id,
                    )
                chi_tiet = (
                    f"Nhập hàng hoàn (biến động #{bd_id}): {ma} +{so_luong} "
                    f"(đã hoàn {da_hoan_moi}/{da_ban})"
                    + (f" — {ghi_chu}" if ghi_chu else "")
                )
                await conn.execute(
                    "INSERT INTO cong_viec_lich_su (cong_viec_id, loai, nguoi_id, ghi_chu) "
                    "VALUES ($1, 'tien_do', $2, $3)",
                    viec_id, actor_id, chi_tiet[:500],
                )

    return {
        "ma": row["ma"],
        "ton_moi": int(row["so_luong"]),
        "ma_don": ma_don_sach,
        "ly_do": "hoan_hang",
        "bien_dong_id": bd_id,
        "da_ban": da_ban,
        "da_hoan": da_hoan_moi,
        "con_lai": con_lai_moi,
        "da_nhap_tu_truoc": False,
        "cong_viec_id": str(viec_id) if viec_id else None,
    }


async def dieu_chinh(ma: str, so_luong_moi: int, ly_do: str) -> dict:
    """
    Kiểm kê: đặt lại số tồn về đúng thực tế đếm được.

    Kho LUÔN lệch — vỡ, mất, đếm sai. Cần một đường sửa hợp lệ, và đường
    đó phải ghi sổ như mọi thay đổi khác, kèm lý do bắt buộc.
    """
    if not ly_do.strip():
        raise ValueError("Điều chỉnh kho bắt buộc phải có lý do")

    # Đọc số cũ VÀ ghi số mới dưới cùng một khoá dòng. Bản trước đọc rồi
    # mới ghi, ngoài giao dịch: một đơn bán chen vào giữa thì `lech` ghi sổ
    # sai đúng bằng số vừa bán, và sổ không còn cộng ra số tồn.
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow(
                "SELECT so_luong FROM ton_kho WHERE ma = $1 FOR UPDATE", ma
            )
            if r is None:
                raise LookupError(f"Không có mã {ma} trong kho")
            cu = int(r["so_luong"])
            # pyrefly: ignore[unnecessary-type-conversion]
            lech = int(so_luong_moi) - cu
            await conn.execute(
                "UPDATE ton_kho SET so_luong = $2, cap_nhat_luc = now() WHERE ma = $1",
                # pyrefly: ignore[unnecessary-type-conversion]
                ma, int(so_luong_moi),
            )
            await conn.execute(
                "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu) "
                "VALUES ($1, $2, 'kiem_ke', $3)", ma, lech, ly_do,
            )
    # pyrefly: ignore[unnecessary-type-conversion]
    return {"ma": ma, "cu": cu, "moi": int(so_luong_moi), "lech": lech}


async def sap_het(nguong: int = NGUONG_SAP_HET) -> list[dict]:
    return await db.fetch(
        "SELECT ma, so_luong FROM ton_kho WHERE so_luong <= $1 ORDER BY so_luong",
        nguong,
    )


async def thong_tin_nhap_hoan(ma: str, ma_don: str) -> dict:
    """
    Đọc thông tin kiểm tra điều kiện và hạn mức nhập hàng hoàn cho (ma, ma_don).
    Chỉ ĐỌC, không sửa tồn kho hay giữ khoá ghi.
    """
    # pyrefly: ignore[unnecessary-type-conversion]
    ma_sach = str(ma or "").strip()
    # pyrefly: ignore[unnecessary-type-conversion]
    ma_don_sach = str(ma_don or "").strip()
    if not ma_don_sach:
        return {
            "ma": ma_sach,
            "ma_don": "",
            "du_dieu_kien": False,
            "da_ban": 0,
            "da_hoan": 0,
            "con_lai": 0,
            "thong_bao": "Nhập mã đơn hàng để kiểm tra điều kiện hàng hoàn.",
        }

    don = await db.fetchrow(
        """
        SELECT id, ma_don, trang_thai, trang_thai_giao_hang,
               van_don_da_lay_hang, yeu_cau_doi_tra_luc
        FROM orders WHERE ma_don = $1
        """,
        ma_don_sach,
    )
    if don is None:
        return {
            "ma": ma_sach,
            "ma_don": ma_don_sach,
            "du_dieu_kien": False,
            "da_ban": 0,
            "da_hoan": 0,
            "con_lai": 0,
            "thong_bao": f"Không tìm thấy đơn hàng {ma_don_sach}.",
        }

    hop_le, ly_do_tu_choi = _don_du_dieu_kien_nhap_hoan(dict(don))
    ban_row = await db.fetchrow(
        "SELECT COALESCE(SUM(ABS(thay_doi)), 0) AS n FROM kho_bien_dong "
        "WHERE ma_don = $1 AND ma = $2 AND ly_do = 'ban'",
        ma_don_sach, ma_sach,
    )
    hoan_row = await db.fetchrow(
        "SELECT COALESCE(SUM(thay_doi), 0) AS n FROM kho_bien_dong "
        "WHERE ma_don = $1 AND ma = $2 AND ly_do = ANY($3::text[])",
        ma_don_sach, ma_sach, sorted(LY_DO_HOAN),
    )
    da_ban = int((ban_row or {}).get("n") or 0)
    da_hoan = int((hoan_row or {}).get("n") or 0)
    con_lai = max(0, da_ban - da_hoan)

    if not hop_le:
        return {
            "ma": ma_sach,
            "ma_don": ma_don_sach,
            "trang_thai": don.get("trang_thai"),
            "trang_thai_giao_hang": don.get("trang_thai_giao_hang"),
            "du_dieu_kien": False,
            "da_ban": da_ban,
            "da_hoan": da_hoan,
            "con_lai": 0,
            "thong_bao": ly_do_tu_choi,
        }
    if da_ban <= 0:
        return {
            "ma": ma_sach,
            "ma_don": ma_don_sach,
            "trang_thai": don.get("trang_thai"),
            "trang_thai_giao_hang": don.get("trang_thai_giao_hang"),
            "du_dieu_kien": False,
            "da_ban": 0,
            "da_hoan": da_hoan,
            "con_lai": 0,
            "thong_bao": f"Đơn {ma_don_sach} không có biến động xuất bán cho mã hàng {ma_sach}.",
        }
    if con_lai <= 0:
        return {
            "ma": ma_sach,
            "ma_don": ma_don_sach,
            "trang_thai": don.get("trang_thai"),
            "trang_thai_giao_hang": don.get("trang_thai_giao_hang"),
            "du_dieu_kien": False,
            "da_ban": da_ban,
            "da_hoan": da_hoan,
            "con_lai": 0,
            "thong_bao": f"Mã {ma_sach} của đơn {ma_don_sach} đã hoàn đủ {da_hoan}/{da_ban} — không thể nhập thêm.",
        }
    return {
        "ma": ma_sach,
        "ma_don": ma_don_sach,
        "trang_thai": don.get("trang_thai"),
        "trang_thai_giao_hang": don.get("trang_thai_giao_hang"),
        "du_dieu_kien": True,
        "da_ban": da_ban,
        "da_hoan": da_hoan,
        "con_lai": con_lai,
        "thong_bao": "",
    }


async def so_bien_dong(ma: str = "", limit: int = 50) -> list[dict]:
    sql = "SELECT id, ma, thay_doi, ly_do, ma_don, ghi_chu, luc FROM kho_bien_dong "
    args: list = []
    if ma:
        sql += "WHERE ma = $1 "
        args.append(ma)
    sql += f"ORDER BY luc DESC LIMIT ${len(args) + 1}"
    args.append(min(limit, 200))
    rows = await db.fetch(sql, *args)
    for r in rows:
        r["luc"] = r["luc"].isoformat()
        r["thay_doi"] = int(r["thay_doi"])
    return rows


async def so_bien_dong_bang(
    *,
    q: str = "",
    ly_do: str = "all",
    chieu: str = "all",
    d_tu=None,
    d_den_exclusive=None,
    page: int = 1,
    page_size: int = 20,
    ten_theo_ma: dict[str, str] | None = None,
) -> dict:
    """Truy vấn sổ biến động kho dạng bảng: lọc, phân trang và tính tồn sau tại thời điểm biến động."""
    ten_map = ten_theo_ma or {}
    where = ["TRUE"]
    args: list = []

    q_sach = (q or "").strip()
    if q_sach:
        q_low = q_sach.lower()
        ma_khop_ten = [ma for ma, ten in ten_map.items() if q_low in ten.lower()]
        args.append(f"%{q_sach}%")
        p_like = f"${len(args)}"
        if ma_khop_ten:
            args.append(ma_khop_ten)
            where.append(
                f"(ma ILIKE {p_like} OR COALESCE(ma_don, '') ILIKE {p_like} "
                f"OR COALESCE(ghi_chu, '') ILIKE {p_like} OR ma = ANY(${len(args)}::text[]))"
            )
        else:
            where.append(
                f"(ma ILIKE {p_like} OR COALESCE(ma_don, '') ILIKE {p_like} "
                f"OR COALESCE(ghi_chu, '') ILIKE {p_like})"
            )

    ld = (ly_do or "all").strip()
    if ld and ld != "all":
        args.append(ld)
        where.append(f"ly_do = ${len(args)}")

    ch = (chieu or "all").strip()
    if ch == "tang":
        where.append("thay_doi > 0")
    elif ch == "giam":
        where.append("thay_doi < 0")

    if d_tu is not None:
        args.append(d_tu)
        where.append(f"luc >= ${len(args)}")
    if d_den_exclusive is not None:
        args.append(d_den_exclusive)
        where.append(f"luc < ${len(args)}")

    where_sql = " AND ".join(where)
    cte = """
        WITH tinh_ton AS (
            SELECT k.id, k.ma, k.thay_doi, k.ly_do, k.ma_don, k.ghi_chu, k.luc,
                   (tk.so_luong - COALESCE(
                       SUM(k.thay_doi) OVER (
                           PARTITION BY k.ma
                           ORDER BY k.luc DESC, k.id DESC
                           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                       ), 0
                   ))::INT AS ton_sau,
                   (tk.so_luong - COALESCE(
                       SUM(k.thay_doi) OVER (PARTITION BY k.ma), 0
                   ))::INT AS ton_dau_suy_dien
            FROM kho_bien_dong k
            LEFT JOIN ton_kho tk ON tk.ma = k.ma
        )
    """
    total_row = await db.fetchrow(f"{cte} SELECT COUNT(*)::int AS n FROM tinh_ton WHERE {where_sql}", *args)
    total = int((total_row or {}).get("n") or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    page_thuc = min(page, total_pages)
    offset = (page_thuc - 1) * page_size

    rows = await db.fetch(
        f"""
        {cte}
        SELECT id, ma, thay_doi, ton_sau, ton_dau_suy_dien, ly_do, ma_don, ghi_chu, luc
        FROM tinh_ton
        WHERE {where_sql}
        ORDER BY luc DESC, id DESC
        LIMIT ${len(args) + 1} OFFSET ${len(args) + 2}
        """,
        *args, page_size, offset,
    )

    dem_rows = await db.fetch(
        "SELECT ly_do, COUNT(*)::int AS n FROM kho_bien_dong GROUP BY ly_do"
    )
    dem_ly_do = {r["ly_do"]: int(r["n"]) for r in dem_rows}

    tac_nhan_map = await _tra_tac_nhan_bien_dong(rows)
    items = []
    for r in rows:
        rid = int(r["id"])
        tn = tac_nhan_map.get(rid, {})
        ton_sau = int(r["ton_sau"]) if r.get("ton_sau") is not None else None
        ton_dau = int(r["ton_dau_suy_dien"]) if r.get("ton_dau_suy_dien") is not None else None
        thieu_can_cu = (ton_sau is not None and ton_sau < 0) or (ton_dau is not None and ton_dau < 0)
        items.append(
            {
                "id": rid,
                "ma": r["ma"],
                "ten": ten_map.get(r["ma"], ""),
                "thay_doi": int(r["thay_doi"]),
                "ton_sau": ton_sau,
                "do_tin_cay_ton": "thieu_can_cu" if thieu_can_cu else "khop",
                "ly_do_tin_cay": (
                    "Thiếu số dư đầu kỳ hoặc dữ liệu lịch sử chưa đủ để đối chiếu tồn trước đó"
                    if thieu_can_cu
                    else ""
                ),
                "ly_do": r["ly_do"],
                "ma_don": r.get("ma_don") or "",
                "ghi_chu": r.get("ghi_chu") or "",
                "nguoi_thuc_hien": tn.get("nguoi_thuc_hien", ""),
                "nguoi_khoi_tao": tn.get("nguoi_khoi_tao", ""),
                "nguoi_phe_duyet": tn.get("nguoi_phe_duyet", ""),
                "nguon_thuc_thi": tn.get("nguon_thuc_thi", ""),
                "luc": r["luc"].isoformat() if hasattr(r["luc"], "isoformat") else r["luc"],
            }
        )
    return {
        "items": items,
        "total": total,
        "page": page_thuc,
        "page_size": page_size,
        "total_pages": total_pages,
        "dem_ly_do": dem_ly_do,
    }


def _parse_ev_detail(raw: Any) -> dict:
    import json as _json

    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _ten_tac_nhan_ev(actor: str, detail: dict) -> str:
    act = (actor or "").strip()
    if act in ("agent", "ai"):
        return "AI Agent"
    if act in ("staff", "nguoi"):
        boi = str(detail.get("boi") or detail.get("nguoi_phe_duyet") or "").strip()
        return boi if boi not in ("staff", "nguoi", "system", "") else ""
    if act in ("system", "he_thong", ""):
        if detail.get("nguoi_khoi_tao") == "agent" or detail.get("luot_id"):
            return "AI Agent"
        return ""
    return act


async def _tra_tac_nhan_bien_dong(rows: list[dict]) -> dict[int, dict[str, str]]:
    """Đối chiếu tác nhân khởi tạo, phê duyệt và nguồn thực thi cho biến động kho (BUG-NK-02)."""
    if not rows:
        return {}

    bd_ids = [str(int(r["id"])) for r in rows]
    mas = sorted({str(r["ma"]) for r in rows if r.get("ma")})
    ma_dons = sorted({str(r["ma_don"]) for r in rows if r.get("ma_don")})
    min_luc = min(r["luc"] for r in rows if r.get("luc") is not None)
    max_luc = max(r["luc"] for r in rows if r.get("luc") is not None)

    ev_rows = await db.fetch(
        """
        SELECT kind, actor, detail, created_at
        FROM events
        WHERE kind IN ('kho.nhap', 'kho.nhap_hoan', 'kho.kiem_ke', 'order.cancel', 'order.cancel_can_huy_tay')
          AND (
                (detail->>'bien_dong_id') = ANY($1::text[])
             OR (
                    created_at BETWEEN ($2::timestamptz - interval '10 seconds')
                                   AND ($3::timestamptz + interval '10 seconds')
                AND ((detail->>'ma') = ANY($4::text[]) OR (detail->>'ma_don') = ANY($5::text[]))
             )
          )
        ORDER BY created_at DESC
        """,
        bd_ids, min_luc, max_luc, mas, ma_dons,
    )

    don_events: dict[str, list[tuple[str, str, dict, Any]]] = {}
    if ma_dons:
        ev_don_rows = await db.fetch(
            """
            SELECT kind, actor, detail, created_at
            FROM events
            WHERE kind IN (
                'order.created', 'order.approve', 'order.cancel',
                'order.cancel_can_huy_tay', 'ai.hanh_dong.tu_dong',
                'ai.de_xuat.thuc_hien', 'erp.don_bi_tu_choi'
            )
              AND (
                    (detail->>'ma_don') = ANY($1::text[])
                 OR (detail->'ket_qua'->>'ma_don') = ANY($1::text[])
              )
            ORDER BY created_at ASC, id ASC
            """,
            ma_dons,
        )
        for ev in ev_don_rows:
            d = _parse_ev_detail(ev.get("detail"))
            md = str(d.get("ma_don") or (d.get("ket_qua") or {}).get("ma_don") or "").strip()
            if md:
                actor = str(ev.get("actor") or "").strip()
                don_events.setdefault(md, []).append((ev["kind"], actor, d, ev["created_at"]))

    parsed = []
    by_bd_id: dict[str, tuple[str, dict]] = {}
    for ev in ev_rows:
        d = _parse_ev_detail(ev.get("detail"))
        actor = str(ev.get("actor") or "").strip()
        if d.get("bien_dong_id") is not None:
            ten = _ten_tac_nhan_ev(actor, d)
            if ten:
                by_bd_id[str(d["bien_dong_id"])] = (ten, d)
        parsed.append((ev["kind"], actor, d, ev["created_at"]))

    out: dict[int, dict[str, str]] = {}
    for r in rows:
        rid = int(r["id"])
        rec = {
            "nguoi_thuc_hien": "",
            "nguoi_khoi_tao": "",
            "nguoi_phe_duyet": "",
            "nguon_thuc_thi": "",
        }
        if str(rid) in by_bd_id:
            ten, _ = by_bd_id[str(rid)]
            rec["nguoi_thuc_hien"] = ten
            rec["nguoi_khoi_tao"] = ten
            rec["nguon_thuc_thi"] = "thu_cong"
            out[rid] = rec
            continue
        ly_do = str(r.get("ly_do") or "")
        luc = r.get("luc")
        ma = str(r.get("ma") or "")
        ma_don = str(r.get("ma_don") or "")
        if ly_do in ("nhap", "kiem_ke", "hoan_hang") and luc is not None:
            target_kind = {
                "nhap": "kho.nhap",
                "kiem_ke": "kho.kiem_ke",
                "hoan_hang": "kho.nhap_hoan",
            }[ly_do]
            for kind, actor, d, cat in parsed:
                if (
                    kind == target_kind
                    and str(d.get("ma") or "") == ma
                    and abs((cat - luc).total_seconds()) <= 5
                ):
                    ten = _ten_tac_nhan_ev(actor, d)
                    if ten:
                        rec["nguoi_thuc_hien"] = ten
                        rec["nguoi_khoi_tao"] = ten
                        rec["nguon_thuc_thi"] = "thu_cong"
                        break
        elif ly_do == "huy_don" and ma_don and luc is not None:
            huy_ev = [
                ev for ev in parsed
                if ev[0] in ("order.cancel", "order.cancel_can_huy_tay")
                and str(ev[2].get("ma_don") or "") == ma_don
                and abs((ev[3] - luc).total_seconds()) <= 5
            ] or [
                ev for ev in don_events.get(ma_don, [])
                if ev[0] in ("order.cancel", "order.cancel_can_huy_tay")
                and abs((ev[3] - luc).total_seconds()) <= 60
            ]
            if huy_ev:
                _, actor, d, _ = huy_ev[0]
                ten = str(d.get("boi") or "").strip()
                if not ten or ten in ("staff", "nguoi", "system"):
                    ten = _ten_tac_nhan_ev(actor, d)
                rec["nguoi_thuc_hien"] = ten
                rec["nguoi_khoi_tao"] = ten
                rec["nguon_thuc_thi"] = "thu_cong" if ten and ten != "AI Agent" else ("ai" if ten == "AI Agent" else "")
            dx_huy = [
                ev for ev in don_events.get(ma_don, [])
                if ev[0] == "ai.de_xuat.thuc_hien"
                and ev[2].get("hanh_dong") == "huy_don"
                and abs((ev[3] - luc).total_seconds()) <= 60
            ]
            if dx_huy:
                _, actor, d, _ = dx_huy[-1]
                duyet = _ten_tac_nhan_ev(actor, d)
                if duyet:
                    rec["nguoi_phe_duyet"] = duyet
                    rec["nguon_thuc_thi"] = "phe_duyet_de_xuat_ai"
        elif ly_do == "ban" and ma_don:
            evs = don_events.get(ma_don, [])
            tao_ev = [
                ev for ev in evs
                if ev[0] == "order.created"
                and (luc is None or ev[3] <= luc or abs((ev[3] - luc).total_seconds()) <= 15)
            ]
            tu_dong_ev = [ev for ev in evs if ev[0] == "ai.hanh_dong.tu_dong" and ev[2].get("hanh_dong") == "tao_don"]
            dx_tao_ev = [ev for ev in evs if ev[0] == "ai.de_xuat.thuc_hien" and ev[2].get("hanh_dong") == "tao_don"]
            duyet_ev = [ev for ev in evs if ev[0] == "order.approve"]

            khoi_tao = ""
            nguon = ""
            if tao_ev:
                _, actor, d, _ = tao_ev[-1]
                khoi_tao = _ten_tac_nhan_ev(actor, d)
                nguon = str(d.get("nguon_thuc_thi") or "").strip()
                if d.get("nguoi_phe_duyet") and not rec["nguoi_phe_duyet"]:
                    rec["nguoi_phe_duyet"] = str(d["nguoi_phe_duyet"]).strip()
            if not khoi_tao and tu_dong_ev:
                khoi_tao = _ten_tac_nhan_ev(tu_dong_ev[-1][1], tu_dong_ev[-1][2]) or "AI Agent"
                nguon = nguon or "tu_dong"
            if dx_tao_ev:
                _, actor, d, _ = dx_tao_ev[-1]
                khoi_tao = khoi_tao or "AI Agent"
                nguon = nguon or "phe_duyet_de_xuat_ai"
                if not rec["nguoi_phe_duyet"]:
                    rec["nguoi_phe_duyet"] = _ten_tac_nhan_ev(actor, d)
            if duyet_ev:
                _, actor, d, _ = duyet_ev[-1]
                duyet_ten = str(d.get("nguoi_phe_duyet") or d.get("boi") or "").strip()
                if not duyet_ten or duyet_ten in ("staff", "nguoi", "system"):
                    duyet_ten = _ten_tac_nhan_ev(actor, d)
                if duyet_ten and not rec["nguoi_phe_duyet"]:
                    # CHỈ ghi người phê duyệt ở cột phê duyệt; KHÔNG gán ngược làm người thực hiện giữ hàng trước đó.
                    rec["nguoi_phe_duyet"] = duyet_ten
            rec["nguoi_khoi_tao"] = khoi_tao
            rec["nguoi_thuc_hien"] = khoi_tao
            rec["nguon_thuc_thi"] = nguon
        elif ly_do == "erp_tu_choi" and ma_don:
            if any(ev[0] == "erp.don_bi_tu_choi" for ev in don_events.get(ma_don, [])):
                rec["nguoi_thuc_hien"] = "Hệ thống (ERP)"
                rec["nguon_thuc_thi"] = "erpnext"
        out[rid] = rec
    return out


async def _tra_nguoi_thuc_hien(rows: list[dict]) -> dict[int, str]:
    """Giữ chữ ký cũ trả map `bien_dong_id -> nguoi_thuc_hien`."""
    chi_tiet = await _tra_tac_nhan_bien_dong(rows)
    return {rid: v["nguoi_thuc_hien"] for rid, v in chi_tiet.items()}
