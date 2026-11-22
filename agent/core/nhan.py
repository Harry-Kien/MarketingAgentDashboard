"""
Nhãn động — lõi dùng chung cho API danh mục, màn hội thoại, Customer 360 và
quy tắc tự động. Lược đồ và lý do: migration 0056_danh_muc_nhan.sql.

HAI LOẠI ĐỘC LẬP
----------------
  khach       mô tả CON NGƯỜI, gắn ở Customer 360, đi theo hồ sơ khách (gộp
              khách thì gộp nhãn, xoá dữ liệu cá nhân thì xoá theo).
  hoi_thoai   mô tả MỘT VỤ VIỆC, gắn trên hội thoại. Không thay trạng thái
              xử lý — hội thoại "đã giải quyết" vẫn giữ nhãn "khiếu nại ship".

VÌ SAO GẮN/GỠ ĐI QUA ĐÂY
------------------------
Ba đường cùng gắn nhãn: nhân viên trên dashboard, API cũ nhận tên nhãn, và
quy tắc tự động. Viết ba lần là ba chỗ quên một trong hai chốt — nhãn đã
ngừng dùng thì không gắn mới, và mọi lần gắn/gỡ phải để lại dấu ở `events`
TRONG CÙNG giao dịch. Ghi nhật ký sau giao dịch là có lúc nhãn đã gắn mà
nhật ký không có dòng nào, và không ai biết dòng nào thiếu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any
from uuid import UUID

LOAI = ("khach", "hoi_thoai")
TEN_LOAI = {"khach": "Nhãn khách hàng", "hoi_thoai": "Nhãn hội thoại"}

# Tám màu mặc định, chia vòng cho nhãn mới và nhãn chuyển từ chữ tự do.
# Migration 0056 chép nguyên dãy này — tests/test_nhan_dong.py canh hai nơi
# khớp nhau và mọi màu đủ tương phản với chữ trắng (WCAG AA, ≥ 4.5:1).
BANG_MAU = ("#1d4ed8", "#15803d", "#b45309", "#b91c1c",
            "#6d28d9", "#0e7490", "#be185d", "#4b5563")
TEN_TOI_DA = 80
MO_TA_TOI_DA = 300

_MAU = re.compile(r"^#[0-9a-f]{6}$")


class NhanHong(ValueError):
    """Dữ liệu nhãn không hợp lệ hoặc không gắn được — thông báo đọc được."""


class NhanKhongThay(LookupError):
    """Không có nhãn ấy trong danh mục."""


def chuan_ten(ten: Any) -> str:
    """
    NFC + gộp khoảng trắng. KHÔNG hạ chữ thường: tên hiển thị giữ nguyên
    "VIP"; trùng tên được xét không phân biệt hoa thường ở chỉ mục
    `uq_nhan_loai_ten`.

    NFC vì bàn phím tiếng Việt gõ ra cả hai dạng dựng sẵn và tổ hợp: "đổi
    trả" hai dạng trông y hệt nhau mà so chuỗi thì khác — thành hai nhãn.
    """
    if not isinstance(ten, str):
        raise NhanHong("Tên nhãn phải là chữ.")
    s = " ".join(unicodedata.normalize("NFC", ten).split())
    if not 1 <= len(s) <= TEN_TOI_DA:
        raise NhanHong(f"Tên nhãn cần 1–{TEN_TOI_DA} ký tự.")
    return s


def chuan_mau(mau: Any) -> str:
    s = str(mau or "").strip().lower()
    if not _MAU.match(s):
        raise NhanHong("Màu phải dạng #rrggbb, ví dụ #1d4ed8.")
    return s


def _do_sang(mau: str) -> float:
    """Độ chói tương đối theo WCAG 2.x."""
    kenh = []
    for i in (1, 3, 5):
        c = int(mau[i:i + 2], 16) / 255
        kenh.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = kenh
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ti_le_tuong_phan(a: str, b: str) -> float:
    sa, sb = sorted((_do_sang(a), _do_sang(b)), reverse=True)
    return (sa + 0.05) / (sb + 0.05)


def mau_chu(nen: str) -> str:
    """
    Chữ trắng hay chữ đậm trên nền màu nhãn — chọn cái tương phản hơn.

    Người quản trị chọn màu tuỳ ý; nhãn vàng nhạt chữ trắng là nhãn không ai
    đọc được. Dashboard tính lại đúng công thức này (21-nhan.js).
    """
    trang = ti_le_tuong_phan(nen, "#ffffff")
    dam = ti_le_tuong_phan(nen, "#111827")
    return "#ffffff" if trang >= dam else "#111827"


def sql_nhan_da_gan(bang: str, cot: str, bieu_thuc: str) -> str:
    """
    Biểu thức SQL trả mảng JSON các nhãn đã gắn, kể cả nhãn đã ngừng (hiện
    xám): ngừng dùng là thôi gắn MỚI, không phải xoá khỏi nơi đã gắn.

    `bang`/`cot` là hằng trong mã gọi, không bao giờ từ người dùng.
    """
    if bang not in ("hoi_thoai_gan_nhan", "khach_gan_nhan") or cot not in (
            "conversation_id", "contact_id"):
        raise ValueError(f"bảng gắn nhãn lạ: {bang}.{cot}")
    return (
        "(SELECT coalesce(jsonb_agg(jsonb_build_object("
        "'id', n.id, 'ten', n.ten, 'mau', n.mau, 'dang_dung', n.dang_dung) "
        "ORDER BY n.thu_tu, lower(n.ten)), '[]'::jsonb) "
        f"FROM {bang} g JOIN nhan n ON n.id = g.nhan_id WHERE g.{cot} = {bieu_thuc})"
    )


def dong(r: Any) -> dict[str, Any]:
    """Một nhãn trong danh mục, dạng gửi ra API."""
    d = dict(r)
    d["id"] = str(d["id"])
    d["mau_chu"] = mau_chu(d["mau"])
    for k in ("tao_luc", "sua_luc"):
        if d.get(k) is not None and hasattr(d[k], "isoformat"):
            d[k] = d[k].isoformat()
    if d.get("tao_boi") is not None:
        d["tao_boi"] = str(d["tao_boi"])
    return d


async def lay(conn, nhan_id: UUID) -> dict[str, Any] | None:
    r = await conn.fetchrow("SELECT * FROM nhan WHERE id = $1", nhan_id)
    return dict(r) if r else None


async def tim_theo_ten(conn, loai: str, ten: str) -> dict[str, Any] | None:
    r = await conn.fetchrow(
        "SELECT * FROM nhan WHERE loai = $1 AND lower(ten) = lower($2)",
        loai, chuan_ten(ten))
    return dict(r) if r else None


async def _lay_de_gan(conn, nhan_id: UUID, loai: str) -> dict[str, Any]:
    n = await lay(conn, nhan_id)
    if n is None:
        raise NhanKhongThay("Không có nhãn này trong danh mục.")
    if n["loai"] != loai:
        # Nói rõ là loại nào: "nhãn không hợp lệ" thì người ta không biết
        # phải đi đâu tìm nhãn đúng.
        raise NhanHong(
            f"«{n['ten']}» là {TEN_LOAI[n['loai']].lower()}, không gắn được ở "
            f"đây — chỗ này chỉ nhận {TEN_LOAI[loai].lower()}.")
    if not n["dang_dung"]:
        raise NhanHong(f"Nhãn «{n['ten']}» đã ngừng sử dụng — bật lại trong "
                       "Quản lý nhãn nếu vẫn cần.")
    return n


async def ghi_su_kien(conn, kind: str, actor: str, ref_id: UUID | None,
                       detail: dict[str, Any]) -> None:
    await conn.execute(
        "INSERT INTO events (kind, actor, ref_id, detail) VALUES ($1,$2,$3,$4)",
        kind, actor, ref_id, detail)


async def gan_hoi_thoai(conn, *, conversation_id: UUID, nhan_id: UUID,
                        gan_boi: UUID | None, actor: str) -> tuple[dict[str, Any], bool]:
    """Gắn nhãn hội thoại. Trả (nhãn, có gắn MỚI không). Gọi trong giao dịch."""
    n = await _lay_de_gan(conn, nhan_id, "hoi_thoai")
    moi = await conn.fetchval(
        "INSERT INTO hoi_thoai_gan_nhan (conversation_id, nhan_id, gan_boi) "
        "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING RETURNING true",
        conversation_id, nhan_id, gan_boi)
    # Gắn lại nhãn đã có thì không ghi: khách nhắn mười tin, quy tắc chạy
    # mười lần — mười dòng "gắn nhãn" giả trong nhật ký.
    if moi:
        await ghi_su_kien(conn, "nhan.gan_hoi_thoai", actor, conversation_id,
                           {"nhan_id": str(nhan_id), "ten": n["ten"]})
    return n, bool(moi)


async def go_hoi_thoai(conn, *, conversation_id: UUID, nhan_id: UUID,
                       actor: str) -> bool:
    """Gỡ được cả nhãn đã ngừng — dọn chỗ cũ là việc nên làm, không chặn."""
    ten = await conn.fetchval(
        "DELETE FROM hoi_thoai_gan_nhan g USING nhan n "
        "WHERE g.conversation_id = $1 AND g.nhan_id = $2 AND n.id = g.nhan_id "
        "RETURNING n.ten", conversation_id, nhan_id)
    if ten is not None:
        await ghi_su_kien(conn, "nhan.go_hoi_thoai", actor, conversation_id,
                           {"nhan_id": str(nhan_id), "ten": ten})
    return ten is not None


async def gan_khach(conn, *, contact_id: UUID, nhan_id: UUID,
                    gan_boi: UUID | None, actor: str) -> tuple[dict[str, Any], bool]:
    n = await _lay_de_gan(conn, nhan_id, "khach")
    moi = await conn.fetchval(
        "INSERT INTO khach_gan_nhan (contact_id, nhan_id, gan_boi) "
        "VALUES ($1,$2,$3) ON CONFLICT DO NOTHING RETURNING true",
        contact_id, nhan_id, gan_boi)
    if moi:
        await ghi_su_kien(conn, "nhan.gan_khach", actor, contact_id,
                           {"nhan_id": str(nhan_id), "ten": n["ten"]})
    return n, bool(moi)


async def go_khach(conn, *, contact_id: UUID, nhan_id: UUID, actor: str) -> bool:
    ten = await conn.fetchval(
        "DELETE FROM khach_gan_nhan g USING nhan n "
        "WHERE g.contact_id = $1 AND g.nhan_id = $2 AND n.id = g.nhan_id "
        "RETURNING n.ten", contact_id, nhan_id)
    if ten is not None:
        await ghi_su_kien(conn, "nhan.go_khach", actor, contact_id,
                           {"nhan_id": str(nhan_id), "ten": ten})
    return ten is not None
