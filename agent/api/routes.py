"""
API cho dashboard — điểm gộp.

Trước 23.10.2026 toàn bộ 92 route nằm trong tệp này (2800 dòng). Giờ mỗi miền
một module; tệp này chỉ còn GỘP router của chúng và XUẤT LẠI tên cũ, để mã và
test đang gọi `routes.X` không vỡ — và để `dependency_overrides[
routes.nguoi_da_dang_nhap]` vẫn trỏ đúng MỘT đối tượng (phu_thuoc.py).

THỨ TỰ GỘP giữ đúng thứ tự route cũ trong từng miền; các miền không có
đường dẫn chồng nhau, nên thứ tự giữa miền không đổi kết quả khớp route.
"""
from __future__ import annotations

from fastapi import APIRouter

from .phu_thuoc import (  # noqa: F401
    TEN_COOKIE,
    _nguoi_id,
    _num,
    _xem_tat_ca_kenh,
    _xet_cua_so_hoac_409,
    bat_buoc_dang_nhap,
    can_quyen,
    chan_neu_khong_duoc_tra_loi,
    chan_neu_ngoai_kenh,
    nguoi_da_dang_nhap,
    nguoi_hien_tai,
)
from . import tai_khoan as _tai_khoan
from .tai_khoan import (  # noqa: F401
    DangNhapIn,
    DoiMatKhauIn,
    TaoNguoiDungIn,
    dang_nhap,
    dang_xuat,
    toi,
    doi_mat_khau,
    MaHaiBuocIn,
    TatHaiBuocIn,
    hai_buoc_trang_thai,
    hai_buoc_bat_dau,
    hai_buoc_xac_nhan,
    hai_buoc_tat,
    danh_sach_nguoi_dung,
    them_nguoi_dung,
    khoa_nguoi_dung,
)
from . import tong_quan as _tong_quan
from .tong_quan import (  # noqa: F401
    he_thong,
    suc_khoe,
    overview,
    RuntimeBody,
    set_runtime,
    recent_events,
    list_channels,
    cost_report,
)
from . import hoi_thoai_cu as _hoi_thoai_cu
from .hoi_thoai_cu import (  # noqa: F401
    list_conversations,
    conversation_detail,
    SendBody,
    _queue_staff_reply,
    staff_send,
    DAI_TOI_DA_BAN_NHAP,
    LoiSuaNhap,
    CanXacNhanQuangCao,
    kiem_sua_nhap,
    _queue_approved_draft,
    DuyetBody,
    approve_draft,
    takeover,
    release,
    _MIME_THEO_DUOI,
    attachment_file,
    ChonNickIn,
    zalo_accounts,
    set_default_account,
    pin_conversation_account,
    MIME_GUI_DUOC,
    TOI_DA_BYTE_GUI,
    THU_MUC_TAI_LEN,
    _ten_file_an_toan,
    staff_send_file,
)
from . import video_api as _video_api
from .video_api import (  # noqa: F401
    list_videos,
    VideoBody,
    create_video,
    create_video_with_images,
    list_video_assets,
    video_asset_file,
    video_file,
    retry_video,
    approve_video,
)
from . import don_kho as _don_kho
from .don_kho import (  # noqa: F401
    anh_san_pham_file,
    list_orders,
    approve_order,
    cancel_order,
    NhapKhoIn,
    KiemKeIn,
    kho_tong_quan,
    kho_bien_dong,
    kho_nhap,
    kho_kiem_ke,
    catalog_products,
)
from . import tri_thuc_api as _tri_thuc_api
from .tri_thuc_api import (  # noqa: F401
    list_documents,
    DocBody,
    add_document,
    delete_document,
    ProbeBody,
    probe,
)
from . import ky_nang_api as _ky_nang_api
from .ky_nang_api import (  # noqa: F401
    liet_ke_ky_nang,
    BatTatBody,
    bat_tat_ky_nang,
    luu_ky_nang_plugin,
    xoa_ky_nang_plugin,
    lich_su_ky_nang_plugin,
    khoi_phuc_ky_nang_plugin,
    ThuPluginBody,
    thu_ky_nang_plugin,
    liet_ke_ung_dung,
    UngDungBody,
    luu_ung_dung,
    xoa_ung_dung,
    thu_ung_dung,
)
from . import cau_hinh_api as _cau_hinh_api
from .cau_hinh_api import (  # noqa: F401
    _MO_TA_CAU_HINH,
    doc_cau_hinh,
    lich_su_cau_hinh,
    dat_lai_cau_hinh,
    doc_xac_nhan_bang_gia,
    ghi_xac_nhan_bang_gia,
    go_xac_nhan_bang_gia,
)
from . import noi_dung_api as _noi_dung_api
from .noi_dung_api import (  # noqa: F401
    SoanBaiIn,
    TaoBaiIn,
    SoLieuIn,
    CallbackIn,
    publish_channels,
    draft_post,
    list_posts,
    create_post,
    approve_post,
    cancel_post,
    post_callback,
    add_metrics,
    get_metrics,
    analytics_khach,
    get_analytics,
    ChienDichIn,
    create_campaign,
    approve_all,
    post_kit,
    post_video,
    mark_posted,
)
from . import pdpd_api as _pdpd_api
from .pdpd_api import (  # noqa: F401
    XoaDuLieuIn,
    XinDuyetXoaIn,
    pdpd_tra_cuu,
    pdpd_xin_duyet,
    pdpd_xoa,
    pdpd_tong_quan,
    pdpd_don,
)

# Mã cũ vá `routes.db` trong test: giữ tên để monkeypatch trúng đúng module.
from agent import db  # noqa: E402,F401

router = APIRouter()
router.include_router(_tai_khoan.router)
router.include_router(_tong_quan.router)
router.include_router(_hoi_thoai_cu.router)
router.include_router(_video_api.router)
router.include_router(_don_kho.router)
router.include_router(_tri_thuc_api.router)
router.include_router(_ky_nang_api.router)
router.include_router(_cau_hinh_api.router)
router.include_router(_noi_dung_api.router)
router.include_router(_pdpd_api.router)
