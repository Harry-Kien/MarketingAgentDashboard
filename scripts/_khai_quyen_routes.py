"""
Khai quyền cho các endpoint trong `agent/api/routes.py`. TỆP TẠM — xoá ở Việc 10.

77 endpoint, mỗi cái một chữ ký khác nhau, và phần lớn KHÔNG có tham số
`Depends` nào để thay — phải chèn mới. Chèn bằng regex trên chuỗi là cách
làm hỏng một chữ ký có ngoặc lồng (`Query(default_factory=...)`), nên ở đây
quét ngoặc cân bằng để tìm đúng dấu đóng của danh sách tham số.

Chạy: python -m scripts._khai_quyen_routes
"""
from __future__ import annotations

from pathlib import Path

DICH = Path(__file__).resolve().parent.parent / "agent" / "api" / "routes.py"

# tên hàm -> quyền
QUYEN_THEO_HAM: dict[str, str] = {
    # --- Hội thoại -------------------------------------------------
    "overview": "hoi_thoai.doc",
    "list_conversations": "hoi_thoai.doc",
    "conversation_detail": "hoi_thoai.doc",
    "recent_events": "hoi_thoai.doc",
    "attachment_file": "hoi_thoai.doc",
    "staff_send": "hoi_thoai.tra_loi",
    "staff_send_file": "hoi_thoai.tra_loi",
    "approve_draft": "hoi_thoai.tra_loi",
    "takeover": "hoi_thoai.nhan",
    "release": "hoi_thoai.nhan",
    "pin_conversation_account": "hoi_thoai.nhan",

    # --- Dữ liệu cá nhân -------------------------------------------
    # Tra cứu giữ ở `khach.pii` (vai trò Nhân viên có) để không đổi hành vi
    # hôm nay; XOÁ thì không — nó không hoàn tác được.
    "pdpd_tong_quan": "khach.pii",
    "pdpd_tra_cuu": "khach.pii",
    "pdpd_don": "khach.pii",
    "pdpd_xoa": "khach.xoa",

    # --- Đơn hàng và kho -------------------------------------------
    "list_orders": "don.doc",
    "kho_tong_quan": "don.doc",
    "kho_bien_dong": "don.doc",
    "catalog_products": "don.doc",
    "anh_san_pham_file": "don.doc",
    "approve_order": "don.sua",
    "cancel_order": "don.sua",
    "kho_nhap": "don.sua",
    "kho_kiem_ke": "don.sua",
    "doc_xac_nhan_bang_gia": "catalog.duyet",
    "ghi_xac_nhan_bang_gia": "catalog.duyet",
    "go_xac_nhan_bang_gia": "catalog.duyet",

    # --- Nội dung ---------------------------------------------------
    # Soạn nháp là việc hằng ngày -> `.doc`. Thứ RA NGOÀI công ty và không
    # rút lại được -> `.duyet`.
    "list_videos": "noi_dung.doc",
    "list_video_assets": "noi_dung.doc",
    "video_asset_file": "noi_dung.doc",
    "video_file": "noi_dung.doc",
    "create_video": "noi_dung.doc",
    "create_video_with_images": "noi_dung.doc",
    "retry_video": "noi_dung.doc",
    "list_posts": "noi_dung.doc",
    "create_post": "noi_dung.doc",
    "draft_post": "noi_dung.doc",
    "post_kit": "noi_dung.doc",
    "post_video": "noi_dung.doc",
    "get_metrics": "noi_dung.doc",
    "publish_channels": "noi_dung.doc",
    "approve_video": "noi_dung.duyet",
    "approve_post": "noi_dung.duyet",
    "approve_all": "noi_dung.duyet",
    "cancel_post": "noi_dung.duyet",
    "mark_posted": "noi_dung.duyet",
    "create_campaign": "noi_dung.duyet",
    # Hai đường n8n gọi về. Chúng ĐANG CHẾT IM LẶNG từ trước bản này:
    # `callback_url` không mang khoá nào, mà đường ấy nằm sau chốt đăng
    # nhập, nên n8n nhận 401 và kết quả đăng bài không bao giờ được ghi.
    # Để `noi_dung.duyet` làm chỗ đậu tạm — KHÔNG khai miễn trừ, vì miễn
    # trừ một đường chưa có cách xác thực nào là mở cửa rồi quên đóng.
    "post_callback": "noi_dung.duyet",
    "add_metrics": "noi_dung.duyet",

    # --- Cấu hình và tri thức --------------------------------------
    "doc_cau_hinh": "cau_hinh.doc",
    "lich_su_cau_hinh": "cau_hinh.doc",
    "list_documents": "cau_hinh.doc",
    "probe": "cau_hinh.doc",
    "dat_lai_cau_hinh": "cau_hinh.sua",
    "add_document": "cau_hinh.sua",
    "delete_document": "cau_hinh.sua",

    # --- Kỹ năng và plugin -----------------------------------------
    "liet_ke_ky_nang": "ky_nang.doc",
    "lich_su_ky_nang_plugin": "ky_nang.doc",
    "bat_tat_ky_nang": "ky_nang.sua",
    "luu_ky_nang_plugin": "ky_nang.sua",
    "thu_ky_nang_plugin": "ky_nang.sua",
    "xoa_ky_nang_plugin": "ky_nang.sua",
    "khoi_phuc_ky_nang_plugin": "ky_nang.sua",

    # --- Ứng dụng nối ngoài ----------------------------------------
    "liet_ke_ung_dung": "tich_hop.doc",
    "luu_ung_dung": "tich_hop.sua",
    "thu_ung_dung": "tich_hop.sua",
    "xoa_ung_dung": "tich_hop.sua",

    # --- Kênh -------------------------------------------------------
    "list_channels": "kenh.doc",
    "zalo_accounts": "kenh.doc",
    "set_default_account": "kenh.sua",

    # --- Vận hành ---------------------------------------------------
    "set_runtime": "agent.dieu_khien",
    "get_analytics": "bao_cao.doc",
    "analytics_khach": "bao_cao.doc",
    "cost_report": "bao_cao.doc",
    "danh_sach_nguoi_dung": "nguoi_dung.doc",
    "them_nguoi_dung": "nguoi_dung.sua",
    "khoa_nguoi_dung": "nguoi_dung.sua",
}


def _dong_ngoac(src: str, mo: int) -> int:
    """Chỉ số dấu `)` khớp với dấu `(` ở vị trí `mo`."""
    sau = 0
    i = mo
    trong_chuoi = ""
    while i < len(src):
        c = src[i]
        if trong_chuoi:
            if c == "\\":
                i += 2
                continue
            if c == trong_chuoi:
                trong_chuoi = ""
        elif c in "\"'":
            trong_chuoi = c
        elif c == "(":
            sau += 1
        elif c == ")":
            sau -= 1
            if sau == 0:
                return i
        i += 1
    raise ValueError("không tìm thấy dấu đóng ngoặc")


def main() -> int:
    src = DICH.read_text(encoding="utf-8")
    da_thay, da_chen, thieu = 0, 0, []

    for ten, quyen in QUYEN_THEO_HAM.items():
        moc = f"async def {ten}("
        vt = src.find(moc)
        if vt < 0:
            thieu.append(ten)
            continue
        mo = vt + len(moc) - 1
        dong = _dong_ngoac(src, mo)
        chu_ky = src[mo + 1:dong]

        if "bat_buoc_quan_tri" in chu_ky:
            # Đã có tham số canh quyền: THAY, không chèn thêm.
            moi = chu_ky.replace("bat_buoc_quan_tri", f'can_quyen("{quyen}")')
            da_thay += 1
        else:
            tham_so = f'_quyen: dict = Depends(can_quyen("{quyen}"))'
            if chu_ky.strip():
                # Giữ nguyên cách xuống dòng sẵn có: chữ ký nhiều dòng thì
                # thêm một dòng, chữ ký một dòng thì nối tiếp.
                if "\n" in chu_ky:
                    thut = " " * 4
                    duoi = chu_ky.rstrip()
                    phay = "" if duoi.endswith(",") else ","
                    moi = f"{duoi}{phay}\n{thut}{tham_so},\n"
                else:
                    moi = f"{chu_ky}, {tham_so}"
            else:
                moi = tham_so
            da_chen += 1

        src = src[:mo + 1] + moi + src[dong:]

    if thieu:
        print("KHÔNG TÌM THẤY HÀM:", ", ".join(thieu))
        return 1

    DICH.write_text(src, encoding="utf-8")
    print(f"Thay {da_thay} chữ ký, chèn {da_chen} chữ ký. "
          f"Tổng {da_thay + da_chen}/{len(QUYEN_THEO_HAM)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
