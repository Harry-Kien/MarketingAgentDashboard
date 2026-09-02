"""
Kết nối Facebook/Instagram bằng ĐĂNG NHẬP, không phải dán token.

VẤN ĐỀ CỦA CÁCH DÁN TOKEN
-------------------------
Người vận hành phải: mở Meta Dashboard, tìm App Secret, tìm đúng Trang,
bấm Generate Token, copy chuỗi 200 ký tự, quay lại dashboard, dán vào đúng
ô — rồi lặp lại cho từng Trang.

Mỗi Trang là sáu thao tác và bốn chỗ có thể sai. Sai không nổ: credential
vẫn được mã hoá và lưu, tài khoản vẫn hiện trên dashboard, chỉ có tin khách
là không bao giờ tới.

OAuth đổi toàn bộ chuyện đó thành: bấm một nút, chọn Trang, xong. Token đi
thẳng từ Meta vào vault, KHÔNG bao giờ hiện trên màn hình.

BA CHỐT AN TOÀN, MỖI CÁI CÓ TEST
--------------------------------
1. `state` chống CSRF — không có nó thì kẻ khác dụ được admin nối một Trang
   của chúng vào hệ thống của bạn
2. `state` dùng MỘT LẦN — chặn phát lại
3. App secret không bao giờ đi qua trình duyệt
"""
from __future__ import annotations

import pytest

from agent.api.oauth_meta import (
    KhoState,
    doc_trang_tu_me_accounts,
    dung_url_dang_nhap,
)


def test_url_dang_nhap_co_du_tham_so_bat_buoc():
    url = dung_url_dang_nhap(
        app_id="123", redirect_uri="https://x.test/cb", state="abc",
    )
    for phai_co in ("client_id=123", "state=abc", "response_type=code", "scope="):
        assert phai_co in url, phai_co
    assert url.startswith("https://www.facebook.com/")


def test_url_xin_dung_quyen_can_de_nhan_tin():
    """
    Thiếu `pages_messaging` là nối xong nhưng không nhắn được — và lỗi chỉ
    lộ ra lúc khách nhắn tới.
    """
    url = dung_url_dang_nhap(app_id="1", redirect_uri="https://x.test/cb", state="s")
    for quyen in ("pages_show_list", "pages_messaging", "pages_manage_metadata"):
        assert quyen in url, f"thiếu quyền {quyen}"


def test_app_secret_khong_bao_gio_di_qua_trinh_duyet():
    """URL này người dùng nhìn thấy được — app secret lọt vào là lộ vĩnh viễn."""
    url = dung_url_dang_nhap(app_id="1", redirect_uri="https://x.test/cb", state="s")
    assert "secret" not in url.lower()


def test_state_dung_mot_lan_roi_het_hieu_luc():
    """Phát lại một callback cũ không được nối thêm tài khoản lần nữa."""
    from uuid import uuid4

    kho = KhoState()
    ai = uuid4()
    s = kho.tao(ai)
    assert kho.dung(s) == ai
    assert kho.dung(s) is None, "state phải hết hiệu lực sau lần dùng đầu"


def test_state_la_bi_tu_choi():
    kho = KhoState()
    assert kho.dung("state-tu-dau-ra") is None


def test_state_nho_AI_da_bam_nut():
    """
    Callback không có phiên đăng nhập — Meta gọi vào và không mang cookie.

    Nhưng tài khoản tạo ra vẫn phải ghi ĐÚNG người đã bấm: `account_
    memberships.user_id` có khoá ngoại tới `nguoi_dung`, nên một id bịa
    (ví dụ UUID toàn số 0) làm cả lượt tạo thất bại — và nhật ký kiểm toán
    cũng mất nghĩa.

    LỖI ĐÃ XẢY RA: dùng UUID(int=0) làm actor, cả 6 Trang đều hỏng vì
    ForeignKeyViolation, người dùng chỉ thấy "Đã nối 0 Trang".
    """
    from uuid import uuid4

    kho = KhoState()
    ai = uuid4()
    assert kho.dung(kho.tao(ai)) == ai


def test_doc_danh_sach_trang_tu_phan_hoi_meta():
    phan_hoi = {"data": [
        {"id": "111", "name": "Cửa hàng A", "access_token": "TOKEN-A",
         "tasks": ["MESSAGING", "MANAGE"]},
        {"id": "222", "name": "Cửa hàng B", "access_token": "TOKEN-B",
         "tasks": ["MESSAGING"]},
    ]}
    trang = doc_trang_tu_me_accounts(phan_hoi)
    assert [t["id"] for t in trang] == ["111", "222"]
    assert trang[0]["name"] == "Cửa hàng A"
    assert trang[0]["access_token"] == "TOKEN-A"


def test_bo_trang_khong_co_quyen_nhan_tin():
    """
    Trang không có quyền MESSAGING thì nối vào cũng không nhận được tin.

    Hiện nó trong danh sách chọn là mời người dùng phạm sai lầm, rồi phải tự
    hỏi vì sao Trang đó im lặng.
    """
    phan_hoi = {"data": [
        {"id": "111", "name": "Có quyền", "access_token": "A", "tasks": ["MESSAGING"]},
        {"id": "222", "name": "Chỉ xem", "access_token": "B", "tasks": ["ANALYZE"]},
    ]}
    trang = doc_trang_tu_me_accounts(phan_hoi)
    assert [t["id"] for t in trang] == ["111"]


def test_thieu_access_token_thi_bo_qua():
    phan_hoi = {"data": [{"id": "333", "name": "Thiếu token", "tasks": ["MESSAGING"]}]}
    assert doc_trang_tu_me_accounts(phan_hoi) == []


def test_phan_hoi_rong_khong_lam_vo():
    assert doc_trang_tu_me_accounts({}) == []
    assert doc_trang_tu_me_accounts({"data": []}) == []


# ---------------------------------------------------------------
#  Nối vào HTTP
# ---------------------------------------------------------------

def test_co_hai_endpoint_bat_dau_va_quay_ve():
    from agent.api.oauth_meta import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/connect/meta/start" in duong, "thiếu endpoint bắt đầu đăng nhập"
    assert "/api/connect/meta/callback" in duong, "thiếu endpoint Meta quay về"


def test_endpoint_bat_dau_doi_quyen_quan_tri():
    """Nối tài khoản kênh là việc quản trị — nhân viên trực không được tự nối."""
    import inspect

    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta)
    assert "bat_buoc_quan_tri" in nguon


def test_callback_KHONG_doi_dang_nhap_dashboard():
    """
    Meta gọi vào callback, và Meta không mang cookie phiên của bạn.

    Bắt đăng nhập ở đây là luồng không bao giờ chạy được. Chốt an toàn của
    bước này là `state`, không phải cookie.
    """
    import inspect

    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta.meta_callback)
    assert "bat_buoc_quan_tri" not in nguon
    assert "state" in nguon


def test_dashboard_co_nut_ket_noi_bang_dang_nhap():
    """
    Nút phải nằm NGAY cạnh form dán token, không giấu trong menu.

    Người dùng gặp form trước; nếu không thấy đường dễ hơn ngay tại đó, họ
    sẽ dán token bằng tay — và đó chính là cách sai mà lớp này sinh ra để
    thay thế.
    """
    from pathlib import Path

    goc = Path(__file__).resolve().parents[1]
    html = (goc / "dashboard" / "index.html").read_text(encoding="utf-8")
    js = (goc / "dashboard" / "app.js").read_text(encoding="utf-8")

    assert 'id="btn-oauth-meta"' in html, "thiếu nút kết nối bằng đăng nhập"
    assert "connect/meta/start" in js, "nút chưa nối vào endpoint bắt đầu"


def test_callback_duoc_mo_o_middleware_va_chi_rieng_no():
    """
    Meta gọi callback mà KHÔNG mang cookie phiên. Không mở đường này ở
    middleware thì luồng đăng nhập không bao giờ chạy được — nó trả 401 cho
    chính Meta.

    Nhưng chỉ mở ĐÚNG callback: `/start` vẫn phải đòi quyền quản trị, vì nó
    là nơi khởi động luồng và chỉ người trong nhà mới được bấm.
    """
    from agent.main import _MO

    assert "/api/connect/meta/callback" in _MO
    assert "/api/connect/meta/start" not in _MO, "start phải đòi đăng nhập"


def test_mo_duong_nao_deu_phai_co_chot_khac_thay_the():
    """
    Danh sách `_MO` là chỗ dễ nới lỏng nhất trong cả hệ thống.

    Mỗi đường mở ra phải có một chốt khác gánh thay. Với callback đó là
    `state` dùng một lần — test này neo việc ấy lại.
    """
    import inspect

    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta.meta_callback)
    assert "_KHO_STATE.dung(state)" in nguon, "callback phải kiểm state"


def test_goi_dung_API_that_cua_account_service():
    """
    Bắt lỗi gọi sai tên lớp / sai chữ ký — thứ chỉ nổ khi chạy thật.

    LỖI ĐÃ XẢY RA: hàm tạo tài khoản `import CreateChannelAccount` và gọi
    `service.create(...)`. Cả hai tên đều KHÔNG tồn tại — tên thật là
    `CreateAccountCommand` và `create_account()`.

    Không test nào bắt được, vì đường đó chỉ chạy khi có CSDL thật VÀ Meta
    trả về danh sách Trang thật. Người dùng gặp "Internal Server Error"
    trắng trang, sau khi đã làm xong toàn bộ phần khó ở phía Meta.

    Test này rẻ và neo lại đúng ba tên đó.
    """
    import inspect

    from agent.omnichannel.account_service import (
        AccountActor,
        ChannelAccountService,
        CreateAccountCommand,
    )
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta._tao_tai_khoan_tu_danh_sach)
    assert "CreateAccountCommand" in nguon
    assert "create_account(" in nguon
    assert "AccountActor(" in nguon, "phải dùng dataclass thật, không tự chế lớp giả"

    # Chữ ký phải khớp: thiếu tham số nào là 500 lúc chạy thật.
    truong = set(CreateAccountCommand.__dataclass_fields__)
    assert {"channel", "display_name", "external_account_id", "credentials"} <= truong
    tham_so = set(
        inspect.signature(ChannelAccountService.create_account).parameters
    )
    assert {"command", "actor"} <= tham_so

    # AccountActor cần `role`, không phải `is_admin` — `is_admin` là property
    # suy ra từ role. Đặt nhầm là actor luôn bị coi là không phải quản trị.
    assert "role" in AccountActor.__dataclass_fields__
