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

    "nhom2": [
        # --- goi_ky_nang.py ---
        # `/kiem` dùng `ky_nang.sua` dù không ghi gì: nó tải gói từ một địa
        # chỉ do người gọi đưa vào, tức là một bề mặt SSRF. Ai chưa được
        # phép cài gói thì cũng chưa nên bắt máy chủ đi tải gói.
        ("agent/api/goi_ky_nang.py",
         "from agent.api.routes import bat_buoc_quan_tri",
         "from agent.api.routes import can_quyen", 1),
        ("agent/api/goi_ky_nang.py",
         "async def liet_ke(_: dict = Depends(bat_buoc_quan_tri))",
         'async def liet_ke(_: dict = Depends(can_quyen("ky_nang.doc")))', 1),
        ("agent/api/goi_ky_nang.py",
         "async def xuat(ten: str, _: dict = Depends(bat_buoc_quan_tri))",
         'async def xuat(ten: str, _: dict = Depends(can_quyen("ky_nang.doc")))', 1),
        ("agent/api/goi_ky_nang.py",
         "async def lich_su(ten: str, _: dict = Depends(bat_buoc_quan_tri))",
         'async def lich_su(ten: str, _: dict = Depends(can_quyen("ky_nang.doc")))', 1),
        ("agent/api/goi_ky_nang.py",
         "async def kiem(body: dict, _: dict = Depends(bat_buoc_quan_tri))",
         'async def kiem(body: dict, _: dict = Depends(can_quyen("ky_nang.sua")))', 1),
        ("agent/api/goi_ky_nang.py",
         "nguoi: dict = Depends(bat_buoc_quan_tri)",
         'nguoi: dict = Depends(can_quyen("ky_nang.sua"))', 5),

        # --- oauth_meta.py ---
        ("agent/api/oauth_meta.py",
         "from .routes import bat_buoc_quan_tri  # noqa: E402",
         "from .routes import can_quyen  # noqa: E402", 1),
        ("agent/api/oauth_meta.py",
         "async def meta_start(user: dict = Depends(bat_buoc_quan_tri))",
         'async def meta_start(user: dict = Depends(can_quyen("kenh.noi")))', 1),
        ("agent/api/oauth_meta.py",
         "    _nguoi: dict = Depends(bat_buoc_quan_tri),",
         '    _nguoi: dict = Depends(can_quyen("kenh.noi")),', 1),

        # --- erp.py ---
        # Bốn đường ĐỌC danh mục và tồn kho -> `don.doc`; `kiem-ket-noi` gọi
        # ra máy chủ ERP bằng khoá đã lưu, nên nó thuộc phía cấu hình.
        ("agent/api/erp.py",
         "from .routes import bat_buoc_dang_nhap",
         "from .routes import can_quyen", 1),
        ("agent/api/erp.py",
         "_nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:",
         '_nguoi: dict = Depends(can_quyen("don.doc"))) -> dict:', 3),
        ("agent/api/erp.py",
         "    ma: str, _nguoi: dict = Depends(bat_buoc_dang_nhap)",
         '    ma: str, _nguoi: dict = Depends(can_quyen("don.doc"))', 1),
        ("agent/api/erp.py",
         "    _nguoi: dict = Depends(bat_buoc_dang_nhap),",
         '    _nguoi: dict = Depends(can_quyen("cau_hinh.doc")),', 1),
    ],

    "kenh": [
        ("agent/api/channel_accounts.py",
         "from .routes import bat_buoc_dang_nhap, bat_buoc_quan_tri",
         "from .routes import can_quyen", 1),
        # Ba đường ĐỌC: danh sách, chi tiết, sức khoẻ.
        ("agent/api/channel_accounts.py",
         "    user: dict = Depends(bat_buoc_dang_nhap),",
         '    user: dict = Depends(can_quyen("kenh.doc")),', 3),
        # Sáu đường SỬA: tạo, credentials, bật, tắt, xoá, verify.
        ("agent/api/channel_accounts.py",
         "    user: dict = Depends(bat_buoc_quan_tri),",
         '    user: dict = Depends(can_quyen("kenh.sua")),', 6),
        ("agent/api/channel_accounts.py",
         "    _user: dict = Depends(bat_buoc_quan_tri),",
         '    _user: dict = Depends(can_quyen("kenh.sua")),', 1),
        # Năm đường `_:` chia hai ngả, nên vá theo TÊN HÀM chứ không theo
        # chuỗi tham số — ba đường đọc và hai đường nối kênh trông giống hệt
        # nhau ở dòng tham số.
        ("agent/api/channel_accounts.py",
         "async def kiem_xoa_duoc(\n    account_id: UUID,\n    _: dict = Depends(bat_buoc_quan_tri),",
         'async def kiem_xoa_duoc(\n    account_id: UUID,\n    _: dict = Depends(can_quyen("kenh.doc")),', 1),
        ("agent/api/channel_accounts.py",
         "async def zalo_personal_status(\n    account_id: UUID,\n    _: dict = Depends(bat_buoc_quan_tri),",
         'async def zalo_personal_status(\n    account_id: UUID,\n    _: dict = Depends(can_quyen("kenh.doc")),', 1),
        ("agent/api/channel_accounts.py",
         "async def doc_verify_token(\n    account_id: UUID,\n    _: dict = Depends(bat_buoc_quan_tri),",
         'async def doc_verify_token(\n    account_id: UUID,\n    _: dict = Depends(can_quyen("kenh.doc")),', 1),
        ("agent/api/channel_accounts.py",
         "async def start_zalo_personal_qr(\n    account_id: UUID,\n    _: dict = Depends(bat_buoc_quan_tri),",
         'async def start_zalo_personal_qr(\n    account_id: UUID,\n    _: dict = Depends(can_quyen("kenh.noi")),', 1),
        ("agent/api/channel_accounts.py",
         "async def restore_zalo_personal_session(\n    account_id: UUID,\n    _: dict = Depends(bat_buoc_quan_tri),",
         'async def restore_zalo_personal_session(\n    account_id: UUID,\n    _: dict = Depends(can_quyen("kenh.noi")),', 1),
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
