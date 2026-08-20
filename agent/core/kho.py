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

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            for it in items:
                ma, sl = it.get("ma"), int(it.get("so_luong") or 1)
                if not ma:
                    continue
                # FOR UPDATE khoá đúng dòng này tới hết giao dịch.
                row = await conn.fetchrow(
                    "SELECT so_luong FROM ton_kho WHERE ma = $1 FOR UPDATE", ma
                )
                if row is None:
                    return False, f"Mã {ma} không có trong kho."
                con = int(row["so_luong"])
                if con < sl:
                    ten = it.get("ten") or ma
                    return False, (
                        f"{ten} chỉ còn {con} sản phẩm, không đủ {sl}."
                        if con else f"{ten} đã hết hàng."
                    )

            # Tới đây là chắc chắn đủ cả lô -> mới trừ.
            for it in items:
                ma, sl = it.get("ma"), int(it.get("so_luong") or 1)
                if not ma:
                    continue
                await conn.execute(
                    "UPDATE ton_kho SET so_luong = so_luong - $2, cap_nhat_luc = now() "
                    "WHERE ma = $1", ma, sl,
                )
                await conn.execute(
                    "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don) "
                    "VALUES ($1, $2, 'ban', $3)", ma, -sl, ma_don,
                )
    return True, ""


async def tra_hang(ma_don: str, ly_do: str = "huy_don") -> int:
    """
    Trả lại kho khi đơn bị huỷ.

    Đọc từ sổ biến động chứ không đọc từ đơn: sổ là thứ ghi CHÍNH XÁC đã
    trừ bao nhiêu. Đơn có thể đã bị sửa, sổ thì không.

    Không trả trùng: mỗi lần bán chỉ được hoàn đúng một lần.
    """
    da_hoan = await db.fetchrow(
        "SELECT 1 FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = $2 LIMIT 1",
        ma_don, ly_do,
    )
    if da_hoan:
        return 0

    ban = await db.fetch(
        "SELECT ma, thay_doi FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = 'ban'",
        ma_don,
    )
    if not ban:
        return 0

    async with db.pool().acquire() as conn:
        async with conn.transaction():
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


async def nhap_hang(ma: str, so_luong: int, ghi_chu: str = "") -> dict:
    """Nhập thêm hàng. Người vận hành bấm trên dashboard."""
    so_luong = int(so_luong)
    if so_luong <= 0:
        raise ValueError("Số lượng nhập phải lớn hơn 0")

    row = await db.fetchrow(
        "UPDATE ton_kho SET so_luong = so_luong + $2, cap_nhat_luc = now() "
        "WHERE ma = $1 RETURNING ma, so_luong", ma, so_luong,
    )
    if row is None:
        raise LookupError(f"Không có mã {ma} trong kho")

    await db.execute(
        "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu) "
        "VALUES ($1, $2, 'nhap', $3)", ma, so_luong, ghi_chu,
    )
    return {"ma": row["ma"], "ton_moi": int(row["so_luong"])}


async def dieu_chinh(ma: str, so_luong_moi: int, ly_do: str) -> dict:
    """
    Kiểm kê: đặt lại số tồn về đúng thực tế đếm được.

    Kho LUÔN lệch — vỡ, mất, đếm sai. Cần một đường sửa hợp lệ, và đường
    đó phải ghi sổ như mọi thay đổi khác, kèm lý do bắt buộc.
    """
    if not ly_do.strip():
        raise ValueError("Điều chỉnh kho bắt buộc phải có lý do")

    cu = await lay(ma)
    if cu is None:
        raise LookupError(f"Không có mã {ma} trong kho")

    lech = int(so_luong_moi) - cu
    await db.execute(
        "UPDATE ton_kho SET so_luong = $2, cap_nhat_luc = now() WHERE ma = $1",
        ma, int(so_luong_moi),
    )
    await db.execute(
        "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ghi_chu) "
        "VALUES ($1, $2, 'kiem_ke', $3)", ma, lech, ly_do,
    )
    return {"ma": ma, "cu": cu, "moi": int(so_luong_moi), "lech": lech}


async def sap_het(nguong: int = NGUONG_SAP_HET) -> list[dict]:
    return await db.fetch(
        "SELECT ma, so_luong FROM ton_kho WHERE so_luong <= $1 ORDER BY so_luong",
        nguong,
    )


async def so_bien_dong(ma: str = "", limit: int = 50) -> list[dict]:
    sql = "SELECT ma, thay_doi, ly_do, ma_don, ghi_chu, luc FROM kho_bien_dong "
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
