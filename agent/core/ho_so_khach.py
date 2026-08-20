"""
Trí nhớ về khách hàng — ranh giới giữa chatbot và agent.

VẤN ĐỀ
------
Trước lớp này, mỗi hội thoại bắt đầu từ con số không. Khách hôm qua đã nói
"em da dầu", hôm nay quay lại hỏi kem chống nắng thì agent hỏi lại loại da.
Khách mua serum tháng trước, agent không biết mà tư vấn trùng.

Một RAG chatbot cũng làm được đúng như vậy: tra tài liệu, trả lời, quên.
Cái làm nên agent là nó GIỮ LẠI hiểu biết về từng người và dùng ở lần sau.

CÁCH LẤY DỮ LIỆU — ĐÂY LÀ PHẦN QUAN TRỌNG
------------------------------------------
Cách thường thấy là gọi thêm một lượt model để "trích xuất thông tin khách
hàng" sau mỗi hội thoại. Cách đó tốn tiền mỗi lượt VÀ bịa được — model có
thể ghi "khách da nhạy cảm" trong khi khách chưa từng nói.

Ở đây làm ngược lại: hồ sơ dựng từ những gì ĐÃ XẢY RA, không từ suy đoán.

  agent gọi goi_y_san_pham(loai_da="da dầu")  ->  ghi: da dầu
  agent gọi tao_don_hang(...)                 ->  ghi: đã mua gì
  agent gọi chuyen_nhan_vien(ly_do=...)       ->  ghi: đã từng chuyển người
  khách gõ "em da dầu"                        ->  ghi: da dầu

Ba nguồn đầu suy từ hành động của agent. Nguồn thứ tư quét CHÍNH LỜI KHÁCH
bằng danh sách từ khoá lấy từ catalog — cũng không bịa được, vì mẩu ghi ra
đúng bằng chữ khách đã gõ.

Nguồn thứ tư cần thiết vì nguồn tool quá hẹp: khách nói rõ "em da dầu" mà
agent lại đi thẳng `tra_cuu_san_pham` thì không có tham số `loai_da` nào để
rút — thông tin rõ ràng nhất lại bị bỏ lỡ. Đã gặp đúng chuyện này khi thử.

RÀNG BUỘC BẢO VỆ DỮ LIỆU
------------------------
Hồ sơ là dữ liệu cá nhân theo Nghị định 13/2023/NĐ-CP. Nó phải biến mất khi
khách yêu cầu xoá — xem `agent/core/du_lieu_ca_nhan.py`. Xây trí nhớ mà
quên đường xoá là tạo ra một kho dữ liệu ngoài tầm kiểm soát.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .. import db

# Bao nhiêu mẩu ghi nhớ được nhét vào ngữ cảnh. Quá nhiều thì loãng và tốn
# token; quá ít thì quên mất điều khách vừa nói tuần trước.
SO_GHI_NHO_TOI_DA = 8

# Loại mẩu, xếp theo mức đáng tin. `hanh_dong` suy ra từ việc đã xảy ra nên
# chắc chắn; `agent_ghi` là điều agent nghe được, kém chắc hơn.
NGUON = ("hanh_dong", "don_hang", "khach_noi", "agent_ghi")

# Từ khoá lấy TỪ CATALOG, không gõ tay: thêm một loại da vào danh mục là
# agent nhận ra loại da đó ngay, không phải sửa hai chỗ.
_TU_KHOA_DA: tuple[str, ...] = ()


def _tu_khoa_loai_da() -> tuple[str, ...]:
    global _TU_KHOA_DA
    if _TU_KHOA_DA:
        return _TU_KHOA_DA
    import json

    from ..config import ROOT
    try:
        data = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    tu = set()
    for sp in data.get("san_pham", []):
        for d in sp.get("da_phu_hop") or []:
            d = d.strip().lower()
            # "mọi loại da" không nói gì về khách này; "trẻ em trên 6 tháng"
            # là nhóm người dùng, không phải loại da.
            if d.startswith("da ") and d not in ("da không nhạy cảm",):
                tu.add(d)
    # Dài trước ngắn: "da hỗn hợp thiên dầu" phải khớp trước "da hỗn hợp".
    _TU_KHOA_DA = tuple(sorted(tu, key=len, reverse=True))
    return _TU_KHOA_DA


# Người Việt hiếm khi viết "da khô" liền nhau — họ viết "da em khô", "da
# mình khô căng", "da của em nhạy cảm". So khớp chuỗi thô bỏ lỡ đúng cách
# nói phổ biến nhất. Bỏ đại từ nằm giữa trước khi khớp.
_DAI_TU = re.compile(
    r"\bda\s+(?:của\s+)?(?:em|mình|tôi|con|bạn|chị|anh|cháu)\b",
    re.IGNORECASE,
)


def _go_dai_tu(tin: str) -> str:
    return _DAI_TU.sub("da", tin)


# Điều khách nói mà hệ thống nên nhớ mãi, ngoài loại da.
_LUU_Y_LAU_DAI = (
    ("dị ứng", "Khách từng nói bị dị ứng"),
    ("kích ứng", "Khách từng nói da bị kích ứng"),
    ("mang thai", "Khách nói đang mang thai"),
    ("có bầu", "Khách nói đang mang thai"),
    ("cho con bú", "Khách nói đang cho con bú"),
)


async def lay(customer_ref: str, channel: str) -> dict | None:
    """Hồ sơ của một khách, hoặc None nếu chưa từng gặp."""
    if not customer_ref:
        return None
    return await db.fetchrow(
        "SELECT * FROM ho_so_khach WHERE customer_ref = $1 AND channel = $2",
        customer_ref, channel,
    )


async def _bao_dam(customer_ref: str, channel: str, ten: str = "") -> dict:
    return await db.fetchrow(
        """
        INSERT INTO ho_so_khach (customer_ref, channel, ten)
        VALUES ($1, $2, $3)
        ON CONFLICT (customer_ref, channel) DO UPDATE
            SET ten = coalesce(nullif(EXCLUDED.ten, ''), ho_so_khach.ten),
                lan_cuoi = now()
        RETURNING *
        """,
        customer_ref, channel, ten,
    )


async def ghi(
    customer_ref: str,
    channel: str,
    noi_dung: str,
    *,
    nguon: str = "agent_ghi",
    ten: str = "",
) -> None:
    """
    Thêm một mẩu ghi nhớ.

    Không ghi trùng: cùng nội dung thì chỉ cập nhật thời điểm. Khách nói
    "da dầu" mười lần thì hồ sơ vẫn chỉ có một dòng.
    """
    noi_dung = (noi_dung or "").strip()
    if not noi_dung or not customer_ref:
        return
    if nguon not in NGUON:
        nguon = "agent_ghi"

    ho_so = await _bao_dam(customer_ref, channel, ten)
    mau = list(ho_so.get("ghi_nho") or [])

    for m in mau:
        if m.get("noi_dung", "").lower() == noi_dung.lower():
            m["luc"] = datetime.now(timezone.utc).isoformat()
            m["so_lan"] = int(m.get("so_lan", 1)) + 1
            break
    else:
        mau.append({
            "noi_dung": noi_dung,
            "nguon": nguon,
            "luc": datetime.now(timezone.utc).isoformat(),
            "so_lan": 1,
        })

    # Giữ mẩu mới nhất, nhưng ưu tiên mẩu suy ra từ hành động thật: chúng
    # kiểm chứng được, còn `agent_ghi` chỉ là điều agent nghe được.
    # Xếp theo mức đáng tin rồi tới mới nhất. Mẩu suy từ hành động thật
    # đứng trước mẩu chỉ nghe được.
    _uu_tien = {"hanh_dong": 3, "don_hang": 3, "khach_noi": 2, "agent_ghi": 1}
    mau.sort(key=lambda m: (_uu_tien.get(m["nguon"], 0), m["luc"]), reverse=True)
    mau = mau[: SO_GHI_NHO_TOI_DA * 2]

    await db.execute(
        "UPDATE ho_so_khach SET ghi_nho = $3, lan_cuoi = now() "
        "WHERE customer_ref = $1 AND channel = $2",
        customer_ref, channel, mau,
    )


async def tu_tool(customer_ref: str, channel: str, ten_tool: str, args: dict) -> None:
    """
    Rút hiểu biết từ một lời gọi công cụ.

    Đây là nguồn dữ liệu chính, và là lý do hồ sơ không thể bịa: agent chỉ
    gọi `goi_y_san_pham(loai_da="da dầu")` khi khách đã nói điều đó.
    """
    if not customer_ref:
        return

    if ten_tool == "goi_y_san_pham":
        if (loai := (args.get("loai_da") or "").strip()):
            await ghi(customer_ref, channel, f"Loại da: {loai}", nguon="hanh_dong")
        if (nhu_cau := (args.get("nhu_cau") or "").strip()):
            await ghi(customer_ref, channel, f"Quan tâm: {nhu_cau}", nguon="hanh_dong")

    elif ten_tool == "chuyen_nhan_vien":
        if (ly_do := (args.get("ly_do") or "").strip()):
            await ghi(customer_ref, channel,
                      f"Đã từng chuyển nhân viên: {ly_do}"[:180], nguon="hanh_dong")

    elif ten_tool == "tao_don_hang":
        ten = (args.get("khach_ten") or "").strip()
        sp = ", ".join(
            str(i.get("ten") or i.get("ma") or "")
            for i in (args.get("items") or [])
        )[:180]
        if sp:
            await ghi(customer_ref, channel, f"Đã mua: {sp}",
                      nguon="don_hang", ten=ten)


async def tu_tin_nhan(customer_ref: str, channel: str, tin: str) -> None:
    """
    Rút hiểu biết từ chính lời khách nói.

    Chỉ khớp từ khoá có sẵn trong catalog và một danh sách ngắn điều đáng
    nhớ lâu dài. Không suy diễn, không gọi model — mẩu ghi ra đúng bằng chữ
    khách đã gõ, nên không thể bịa.

    Cố ý KHÔNG bắt những thứ nhất thời ("hôm nay da em hơi khô") — hồ sơ để
    nhớ điều bền, không phải nhật ký tâm trạng.
    """
    if not customer_ref or not tin:
        return
    low = _go_dai_tu(tin.lower())

    for tu in _tu_khoa_loai_da():
        if tu in low:
            await ghi(customer_ref, channel, f"Loại da: {tu}", nguon="khach_noi")
            break          # một loại da là đủ, khớp cái cụ thể nhất

    for khoa, ghi_chu in _LUU_Y_LAU_DAI:
        if khoa in low:
            await ghi(customer_ref, channel, ghi_chu, nguon="khach_noi")


async def lam_ngu_canh(customer_ref: str, channel: str) -> str:
    """
    Biến hồ sơ thành vài dòng chữ nhét vào system prompt.

    Trả RỖNG khi chưa biết gì — thà không có phần này còn hơn có một khối
    trống, vì khối trống vẫn tốn token và vẫn khiến model cố diễn giải.
    """
    ho_so = await lay(customer_ref, channel)
    if not ho_so:
        return ""

    mau = (ho_so.get("ghi_nho") or [])[:SO_GHI_NHO_TOI_DA]
    if not mau:
        return ""

    dong = [f"- {m['noi_dung']}" for m in mau]
    lan_dau = ho_so.get("lan_dau")
    quen = ""
    if lan_dau:
        ngay = (datetime.now(timezone.utc) - lan_dau).days
        if ngay >= 1:
            quen = f" (khách quen, lần đầu nhắn cách đây {ngay} ngày)"

    return (
        f"# Điều đã biết về khách này{quen}\n"
        + "\n".join(dong)
        + "\n\nDùng những điều này để KHỎI HỎI LẠI. Nhưng nếu khách nói khác "
          "đi thì tin lời khách lúc này, đừng cãi lại bằng ghi chú cũ."
    )


async def xoa(customer_ref: str = "", channel: str = "", *, sdt: str = "") -> int:
    """Xoá hồ sơ. Gọi từ luồng thực hiện quyền xoá dữ liệu cá nhân."""
    if sdt:
        r = await db.execute(
            "DELETE FROM ho_so_khach "
            "WHERE regexp_replace(coalesce(sdt,''), '\\D', '', 'g') LIKE $1",
            f"%{sdt[-9:]}",
        )
    elif customer_ref:
        r = await db.execute(
            "DELETE FROM ho_so_khach WHERE customer_ref = $1 AND channel = $2",
            customer_ref, channel,
        )
    else:
        return 0
    phan = r.split()
    return int(phan[-1]) if phan and phan[-1].isdigit() else 0
