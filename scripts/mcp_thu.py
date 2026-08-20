"""
Thử máy chủ MCP bằng client THẬT qua stdio — đúng đường Claude Desktop đi.

    python -m scripts.mcp_thu

Không giả lập lời gọi hàm: script này khởi động `python -m agent.mcp_server`
như một tiến trình con, bắt tay theo đúng giao thức, rồi gọi công cụ. Nếu
nó chạy được ở đây thì Claude Desktop cũng chạy được.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


def _text(kq) -> str:
    for c in kq.content:
        if getattr(c, "type", "") == "text":
            return c.text
    return str(kq.content)


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent.mcp_server"],
        cwd=str(ROOT),
    )

    async with stdio_client(params) as (doc, ghi):
        async with ClientSession(doc, ghi) as s:
            info = await s.initialize()
            print(f"Đã nối: {info.server_info.name} v{info.server_info.version}\n")

            ts = await s.list_tools()
            print(f"{len(ts.tools)} công cụ:")
            for t in ts.tools:
                dong_dau = (t.description or "").strip().splitlines()[0]
                print(f"  {t.name:28} {dong_dau[:60]}")

            rs = await s.list_resources()
            print(f"\n{len(rs.resources)} tài nguyên: "
                  f"{', '.join(str(r.uri) for r in rs.resources)}")

            print("\n--- 1. tra giá một sản phẩm ---")
            r = await s.call_tool("tra_cuu_san_pham",
                                  {"ten_san_pham": "serum niacinamide"})
            d = json.loads(_text(r))
            print(f"  {d.get('ten')} — {d.get('gia'):,}đ — tồn {d.get('ton_kho')}"
                  if d.get("tim_thay") else f"  {d}")

            print("\n--- 2. gợi ý theo loại da ---")
            r = await s.call_tool("goi_y_san_pham",
                                  {"loai_da": "da dầu", "nhom": "Làm sạch"})
            d = json.loads(_text(r))
            for sp in d.get("san_pham", [])[:3]:
                print(f"  {sp['ma']}  {sp['ten'][:46]}  {sp['gia']:,}đ")

            print("\n--- 3. tìm trong kho tri thức ---")
            r = await s.call_tool("tim_trong_kho_tri_thuc",
                                  {"cau_hoi": "chính sách đổi trả bao nhiêu ngày"})
            d = json.loads(_text(r))
            for doan in d.get("doan", [])[:2]:
                print(f"  [{doan['diem']}] {doan['tai_lieu']}: {doan['noi_dung'][:70]}...")

            print("\n--- 4. kiểm tuân thủ quảng cáo ---")
            for cau in ["Kem đặc trị mụn, hết mụn sau 7 ngày!",
                        "Gel rửa mặt hỗ trợ giảm dầu thừa, giúp da thông thoáng."]:
                r = await s.call_tool("kiem_tra_tuan_thu_quang_cao", {"noi_dung": cau})
                d = json.loads(_text(r))
                dau = "HỢP LỆ  " if d["hop_le"] else "VI PHẠM "
                print(f"  {dau} {cau[:48]}  {d['cum_vi_pham']}")

            print("\n--- 5. đọc tài nguyên ---")
            r = await s.read_resource("aurora://huong-dan-viet")
            d = json.loads(r.contents[0].text)
            print(f"  căn cứ: {d['can_cu']}")
            print(f"  {len(d['cam'])} cụm cấm, {len(d['duoc'])} cách nói thay thế")

            print("\n--- 6. ranh giới an toàn ---")
            ten = {t.name for t in ts.tools}
            cam = {"dang_bai", "duyet_bai", "gui_tin_nhan", "tao_don_hang",
                   "chot_don", "publish_post"}
            lot = ten & cam
            print(f"  công cụ đăng bài / chốt đơn / nhắn khách bị lộ ra: "
                  f"{sorted(lot) if lot else 'không có — đúng thiết kế'}")
            assert not lot, "MCP KHÔNG được có quyền đăng bài hay nhắn khách"

    print("\nXONG — máy chủ MCP chạy đúng qua giao thức thật.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
