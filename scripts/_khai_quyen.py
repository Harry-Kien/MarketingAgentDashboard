"""
Vá `Depends(bat_buoc_*)` thành `Depends(can_quyen(...))`. TỆP TẠM — xoá ở Việc 10.

Mỗi phép vá khai SỐ LẦN khớp mong đợi và ném nếu lệch. Vá mù bằng
`str.replace` là cách bỏ sót một endpoint mà không ai biết — đúng loại lỗi
cả khối này sinh ra để bịt.

Chạy: python -m scripts._khai_quyen <ten-nhom>
"""
from __future__ import annotations

import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent

# nhóm -> [(đường dẫn tệp, chuỗi cũ, chuỗi mới, số lần khớp mong đợi)]
NHOM: dict[str, list[tuple[str, str, str, int]]] = {
    "nho": [
        # --- cai_dat_api.py ---
        ("agent/api/cai_dat_api.py",
         "from .routes import bat_buoc_dang_nhap, bat_buoc_quan_tri",
         "from .routes import can_quyen", 1),
        ("agent/api/cai_dat_api.py",
         "async def liet_ke(_: dict = Depends(bat_buoc_dang_nhap))",
         'async def liet_ke(_: dict = Depends(can_quyen("cau_hinh.doc")))', 1),
        ("agent/api/cai_dat_api.py",
         "user: dict = Depends(bat_buoc_quan_tri)",
         'user: dict = Depends(can_quyen("cau_hinh.sua"))', 2),
        ("agent/api/cai_dat_api.py",
         "_: dict = Depends(bat_buoc_quan_tri)",
         '_: dict = Depends(can_quyen("cau_hinh.sua"))', 1),

        # --- outbox.py ---
        ("agent/api/outbox.py",
         "from .routes import bat_buoc_quan_tri",
         "from .routes import can_quyen", 1),
        ("agent/api/outbox.py",
         "    _: dict = Depends(bat_buoc_quan_tri),",
         '    _: dict = Depends(can_quyen("outbox.doc")),', 1),
        ("agent/api/outbox.py",
         "    user: dict = Depends(bat_buoc_quan_tri),",
         '    user: dict = Depends(can_quyen("outbox.sua")),', 2),

        # --- retention.py ---
        # Cả bốn dùng `khach.xoa`: hàng chờ xoá dữ liệu chứa số điện thoại
        # khách, và ai thấy được hàng chờ ấy thì cũng nên là người được xoá.
        ("agent/api/retention.py",
         "from .routes import bat_buoc_quan_tri",
         "from .routes import can_quyen", 1),
        ("agent/api/retention.py",
         "    _: dict = Depends(bat_buoc_quan_tri),",
         '    _: dict = Depends(can_quyen("khach.xoa")),', 1),
        ("agent/api/retention.py",
         "    user: dict = Depends(bat_buoc_quan_tri),",
         '    user: dict = Depends(can_quyen("khach.xoa")),', 3),

        # --- routing_admin.py ---
        ("agent/api/routing_admin.py",
         "from .routes import bat_buoc_quan_tri",
         "from .routes import can_quyen", 1),
        ("agent/api/routing_admin.py",
         "    _: dict = Depends(bat_buoc_quan_tri),",
         '    _: dict = Depends(can_quyen("dinh_tuyen.doc")),', 1),
        ("agent/api/routing_admin.py",
         "    user: dict = Depends(bat_buoc_quan_tri),",
         '    user: dict = Depends(can_quyen("dinh_tuyen.sua")),', 4),

        # --- phong_thu_agent.py ---
        ("agent/api/phong_thu_agent.py",
         "from agent.api.routes import bat_buoc_quan_tri",
         "from agent.api.routes import can_quyen", 1),
        ("agent/api/phong_thu_agent.py",
         "Depends(bat_buoc_quan_tri)",
         'Depends(can_quyen("phong_thu.dung"))', 6),

        # --- mcp_may_chu.py ---
        ("agent/api/mcp_may_chu.py",
         "from agent.api.routes import bat_buoc_quan_tri",
         "from agent.api.routes import can_quyen", 1),
        ("agent/api/mcp_may_chu.py",
         "async def liet_ke(_: dict = Depends(bat_buoc_quan_tri))",
         'async def liet_ke(_: dict = Depends(can_quyen("mcp.doc")))', 1),
        ("agent/api/mcp_may_chu.py",
         "Depends(bat_buoc_quan_tri)",
         'Depends(can_quyen("mcp.sua"))', 6),
    ],
}


def main() -> int:
    ten = sys.argv[1] if len(sys.argv) > 1 else ""
    if ten not in NHOM:
        print(f"Nhóm phải là một trong: {', '.join(NHOM)}", file=sys.stderr)
        return 1

    for duong, cu, moi, cho in NHOM[ten]:
        tep = GOC / duong
        noi_dung = tep.read_text(encoding="utf-8")
        that = noi_dung.count(cu)
        if that != cho:
            print(f"LỆCH {duong}: chờ {cho} lần, thấy {that} lần\n  {cu!r}",
                  file=sys.stderr)
            return 1
        tep.write_text(noi_dung.replace(cu, moi), encoding="utf-8")
        print(f"  {duong}: {that} chỗ")

    print(f"Xong nhóm {ten}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
