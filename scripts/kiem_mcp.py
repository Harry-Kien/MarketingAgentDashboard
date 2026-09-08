"""
Kiểm một máy chủ MCP đã lưu — KHÔNG tốn tiền model.

    python -m scripts.kiem_mcp kho

VÌ SAO CẦN
----------
Nối một máy chủ MCP xong, hai lỗi hay gặp không tự báo: (1) công cụ trên
máy chủ đã đổi (thêm/bớt/đổi tên) từ lần Đồng bộ trước — dashboard vẫn hiện
máy chủ "đang bật", cấu hình cũ vẫn còn nguyên, không ai biết nó đã lệch;
(2) một công cụ tưởng gọi được nhưng máy chủ thật sự từ chối (mạng, quyền,
lược đồ đổi) — cách duy nhất biết trước là bấm thử trong Phòng thử, và đó
là một lượt tốn tiền model chỉ để kiểm tra đường ống.

VÌ SAO KHÔNG NHẬP KHẨU `mcp_khach` TRỰC TIẾP
---------------------------------------------
Bài kiểm AST ở `tests/test_ky_nang_plugin.py` chặn mọi tệp ngoài
`agent/ky_nang/kho_mcp.py` nhập khẩu `mcp_khach` — bí mật (header xác
thực), hạn mức và nhật ký của máy chủ MCP chỉ sống ở lớp đó. Script này chỉ
gọi `kho_mcp.kiem_may_chu_da_luu` / `kho_mcp.goi_cong_cu_da_luu` rồi diễn
giải kết quả bằng hàm thuần ở dưới — không cần biết gì về giao thức MCP.

VÌ SAO CHỈ THỬ CÔNG CỤ ĐỌC
---------------------------
`chon_cong_cu_thu` chỉ chọn công cụ KHÔNG đánh dấu `ghi`: một lệnh kiểm
chạy không ai giám sát (cron, tay gõ giữa lúc bận việc khác) không được
phép đổi dữ liệu ở hệ thống người khác chỉ vì đang "kiểm cho chắc".
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db  # noqa: E402
from agent.ky_nang import kho_mcp  # noqa: E402

DAT = "dat"
HONG = "hong"
BO_QUA = "bo_qua"

_NHAN = {DAT: "[đạt]   ", HONG: "[hỏng]  ", BO_QUA: "[bỏ qua]"}


@dataclass
class Muc:
    ten: str
    trang_thai: str
    chi_tiet: str


def ma_thoat(mucs: list[Muc]) -> int:
    """0 nếu không có mục nào HỎNG. Bỏ qua không làm đỏ mã thoát."""
    return 1 if any(m.trang_thai == HONG for m in mucs) else 0


# ---------------------------------------------------------------------
#  Hàm thuần — không mạng, không CSDL, test trực tiếp bằng dict giả
# ---------------------------------------------------------------------

def thieu_thua(
    cong_cu_may_chu: list[str], cong_cu_da_luu: list[dict]
) -> tuple[list[str], list[str]]:
    """
    So công cụ máy chủ đang khai (tên GỐC) với công cụ đã lưu (`cong_cu_goc`
    trong mỗi mục của `cong_cu_da_luu`).

    thiếu = máy chủ có, CSDL chưa lưu — máy chủ vừa thêm công cụ mới mà
    chưa Đồng bộ lại, hoặc công cụ đó từng bị bộ kiểm bỏ (xem mục "bị bỏ"
    riêng, đây không phân biệt hai ca đó).
    thừa = đã lưu, máy chủ không còn khai — sẽ tự bị dọn ở lần Đồng bộ kế
    tiếp, không phải lỗi CSDL.
    """
    goc_may_chu = set(cong_cu_may_chu)
    goc_da_luu = {c["cong_cu_goc"] for c in cong_cu_da_luu}
    return sorted(goc_may_chu - goc_da_luu), sorted(goc_da_luu - goc_may_chu)


def chon_cong_cu_thu(cong_cu_da_luu: list[dict]) -> dict | None:
    """
    Chọn MỘT công cụ để gọi thử với `{}`: ĐỌC (`ghi` là False), đang BẬT,
    và không có tham số bắt buộc (`required` rỗng) — ba điều kiện để `{}`
    là một lời gọi hợp lệ mà không cần biết gì về nghiệp vụ của máy chủ.

    `None` nếu không công cụ nào đủ cả ba — không phải lỗi, chỉ là không
    có gì an toàn để tự thử.
    """
    return next(
        (c for c in cong_cu_da_luu if c["bat"] and not c["ghi"] and not c["required"]),
        None,
    )


def dien_giai(kq: dict, ket_qua_goi: dict | None) -> list[Muc]:
    """
    dict thuần từ `kho_mcp.kiem_may_chu_da_luu` (+ kết quả gọi thử, nếu có)
    → danh sách Muc. Thuần: không tự đi hỏi CSDL hay mạng, chỉ đọc lại.
    """
    ra: list[Muc] = []

    if kq["loi_dia_chi"]:
        ra.append(Muc("Địa chỉ qua rào", HONG, kq["loi_dia_chi"]))
        ra.append(Muc("Nối được máy chủ", BO_QUA, "địa chỉ đã bị rào chặn, không thử nối"))
        ra.append(Muc("Công cụ: máy chủ so với đã lưu", BO_QUA, "chưa nối được máy chủ"))
    else:
        ra.append(Muc("Địa chỉ qua rào", DAT, kq["dia_chi_host"] or ""))
        if not kq["noi_duoc"]:
            ra.append(Muc("Nối được máy chủ", HONG, kq["loi_ket_noi"] or "không rõ lý do"))
            ra.append(Muc("Công cụ: máy chủ so với đã lưu", BO_QUA, "chưa nối được máy chủ"))
        else:
            ra.append(Muc("Nối được máy chủ", DAT,
                          f"{len(kq['cong_cu_may_chu'])} công cụ đang khai"))
            thieu, thua = thieu_thua(kq["cong_cu_may_chu"], kq["cong_cu_da_luu"])
            if thieu or thua:
                phan = []
                if thieu:
                    phan.append("thiếu (máy chủ có, chưa lưu): " + ", ".join(thieu))
                if thua:
                    phan.append("thừa (đã lưu, máy chủ không còn khai): " + ", ".join(thua))
                ra.append(Muc(
                    "Công cụ: máy chủ so với đã lưu", HONG,
                    " · ".join(phan) + " — Đồng bộ lại từ dashboard.",
                ))
            else:
                ra.append(Muc(
                    "Công cụ: máy chủ so với đã lưu", DAT,
                    f"{len(kq['cong_cu_da_luu'])} công cụ khớp nguyên",
                ))

    bo = kq["bo_dong_bo_gan_nhat"]
    if bo:
        ra.append(Muc(
            "Công cụ bị bỏ ở lần Đồng bộ gần nhất", HONG,
            "; ".join(f"{b.get('ten')}: {b.get('ly_do')}" for b in bo),
        ))
    else:
        ra.append(Muc("Công cụ bị bỏ ở lần Đồng bộ gần nhất", DAT, "không công cụ nào bị bỏ"))

    ung_vien = chon_cong_cu_thu(kq["cong_cu_da_luu"])
    if ung_vien is None:
        ra.append(Muc(
            "Gọi thử một công cụ ĐỌC", BO_QUA,
            "không có công cụ nào ĐỌC, đang bật, không tham số bắt buộc để thử",
        ))
    elif ket_qua_goi is None:
        ra.append(Muc(
            f"Gọi thử {ung_vien['ten_model']}", BO_QUA, "chưa nối được máy chủ để gọi thử",
        ))
    elif ket_qua_goi.get("loi"):
        ra.append(Muc(f"Gọi thử {ung_vien['ten_model']}", HONG, str(ket_qua_goi["loi"])))
    else:
        ra.append(Muc(f"Gọi thử {ung_vien['ten_model']}", DAT, "gọi thành công"))
    return ra


# ---------------------------------------------------------------------

def _in(mucs: list[Muc]) -> None:
    for m in mucs:
        print(f"{_NHAN[m.trang_thai]}  {m.ten:<40} {m.chi_tiet}")


async def chay(ten: str) -> int:
    await db.init_db()
    try:
        kq = await kho_mcp.kiem_may_chu_da_luu(ten)
        ket_qua_goi = None
        if kq["noi_duoc"]:
            ung_vien = chon_cong_cu_thu(kq["cong_cu_da_luu"])
            if ung_vien is not None:
                ket_qua_goi = await kho_mcp.goi_cong_cu_da_luu(ten, ung_vien["ten_model"])
    except kho_mcp.MayChuKhongTonTai as exc:
        print(f"[hỏng]   {exc}")
        return 1
    finally:
        await db.close_db()

    mucs = dien_giai(kq, ket_qua_goi)
    print()
    print(f"KIỂM MÁY CHỦ MCP: {ten}")
    print("─" * 78)
    _in(mucs)
    print("─" * 78)
    ma = ma_thoat(mucs)
    if ma:
        print("Còn mục HỎNG — xem chi tiết ở trên.")
    else:
        print("Mọi mục đều đạt, hoặc bỏ qua có lý do.")
    return ma


def main() -> int:
    p = argparse.ArgumentParser(
        description="Kiểm một máy chủ MCP đã lưu, không tốn tiền model.")
    p.add_argument("ten", help="tên máy chủ MCP đã lưu, ví dụ kho")
    a = p.parse_args()
    return asyncio.run(chay(a.ten))


if __name__ == "__main__":
    raise SystemExit(main())
