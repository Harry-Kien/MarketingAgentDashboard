"""
Nối Meta: người dùng CHỌN Trang, không nối tất cả những gì Meta trả về.

VẤN ĐỀ ĐO ĐƯỢC
--------------
Một tài khoản Facebook quản lý 26 Trang. Bản trước nối THẲNG cả 26 vào hệ
thống, không hỏi gì. Nhưng phần lớn trong số đó là Trang dịch vụ pháp lý,
trong khi agent được nạp kho tri thức mỹ phẩm.

Khách nhắn vào một Trang luật sẽ được tư vấn bằng kiến thức mỹ phẩm — sai
ngành, và không có gì trong hệ thống biết là đang sai.

Kèm theo đó: 26 dòng trên màn hình Kết nối, 26 lượt gọi Graph mỗi lần đăng
ký webhook, và 26 Trang phải giải trình khi Meta xét duyệt app.

Chọn Trang cũng là cách mọi công cụ chăm sóc khách hàng chuyên nghiệp làm.
Không phải vì đẹp — vì nối một Trang là nhận trách nhiệm trả lời khách trên
Trang đó.

TOKEN KHÔNG BAO GIỜ RA TRÌNH DUYỆT
-----------------------------------
Danh sách Trang kèm Page access token của từng Trang. Cho người dùng chọn
nghĩa là phải hiện danh sách ra — nhưng chỉ hiện TÊN. Token nằm lại phía máy
chủ, gắn với một phiếu dùng một lần; trình duyệt gửi về đúng những id đã
chọn, không gửi lại token nào.

Đưa token ra HTML là nó đi vào lịch sử trình duyệt, vào ảnh chụp màn hình,
và vào mọi tiện ích mở rộng đang chạy trên tab đó.
"""
from __future__ import annotations

import inspect


def test_co_kho_giu_danh_sach_trang_phia_may_chu():
    from agent.api.oauth_meta import KhoChonTrang

    kho = KhoChonTrang()
    phieu = kho.tao("user-1", [{"id": "1", "name": "A", "access_token": "T"}])
    assert isinstance(phieu, str) and len(phieu) > 20


def test_phieu_dung_MOT_lan():
    """Phát lại phiếu lần hai không được nối thêm tài khoản nữa."""
    from agent.api.oauth_meta import KhoChonTrang

    kho = KhoChonTrang()
    phieu = kho.tao("user-1", [{"id": "1", "name": "A", "access_token": "T"}])
    assert kho.dung(phieu) is not None
    assert kho.dung(phieu) is None


def test_phieu_bia_khong_dung_duoc():
    from agent.api.oauth_meta import KhoChonTrang

    assert KhoChonTrang().dung("phieu-bia-dat") is None


def test_phieu_het_han_thi_tu_choi():
    """Bỏ dở giữa chừng rồi quay lại sau một giờ thì phải bấm lại từ đầu."""
    from agent.api import oauth_meta

    kho = oauth_meta.KhoChonTrang()
    phieu = kho.tao("user-1", [{"id": "1", "name": "A", "access_token": "T"}])
    kho._cho[phieu] = (0.0, "user-1", [{"id": "1"}])
    assert kho.dung(phieu) is None


def test_trang_chon_KHONG_lo_access_token():
    """
    Màn hình chọn Trang chỉ được hiện TÊN.

    Token trong HTML là token trong lịch sử trình duyệt, trong ảnh chụp màn
    hình, và trong mọi tiện ích mở rộng đang chạy trên tab đó.
    """
    from agent.api.oauth_meta import dung_trang_chon

    html = dung_trang_chon("phieu-abc", [
        {"id": "111", "name": "Shop mỹ phẩm", "access_token": "TOKEN-BI-MAT",
         "instagram_id": "ig-1", "instagram_username": "shop"},
    ])

    assert "Shop mỹ phẩm" in html
    assert "TOKEN-BI-MAT" not in html, "token lọt ra HTML"


def test_trang_chon_bao_ro_trang_nao_co_instagram():
    """Người chọn cần biết chọn Trang này thì được thêm gì."""
    from agent.api.oauth_meta import dung_trang_chon

    html = dung_trang_chon("p", [
        {"id": "1", "name": "Co IG", "access_token": "T",
         "instagram_id": "ig-1", "instagram_username": "shopa"},
        {"id": "2", "name": "Khong IG", "access_token": "T",
         "instagram_id": "", "instagram_username": ""},
    ])
    assert "shopa" in html or "Instagram" in html


def test_ten_trang_duoc_thoat_ky_tu_html():
    """
    Tên Trang do người ngoài đặt. Không thoát thì nó chạy được mã trong
    trình duyệt của quản trị viên đang đăng nhập.
    """
    from agent.api.oauth_meta import dung_trang_chon

    html = dung_trang_chon("p", [
        {"id": "1", "name": "<script>alert(1)</script>", "access_token": "T",
         "instagram_id": "", "instagram_username": ""},
    ])
    assert "<script>alert(1)</script>" not in html


def test_co_duong_nhan_lua_chon():
    from agent.api.oauth_meta import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/connect/meta/chon" in duong


def test_duong_nhan_lua_chon_doi_quyen_quan_tri():
    """
    Khác với callback, đường này do CHÍNH trình duyệt người dùng gọi trên
    origin của ta — nên cookie phiên có mặt và phải kiểm.
    """
    from agent.api import oauth_meta

    assert "bat_buoc_quan_tri" in inspect.getsource(oauth_meta.meta_chon)


def test_chi_tao_dung_nhung_trang_da_chon():
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta.meta_chon)
    assert "chon" in nguon
    assert "_tao_tai_khoan_tu_danh_sach" in nguon


def test_callback_khong_con_tao_thang_tai_khoan():
    """
    Callback chỉ còn hiện danh sách để chọn. Tạo thẳng ở đó là bỏ qua bước
    chọn — đúng hành vi vừa gỡ bỏ.
    """
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta.meta_callback)
    assert "_tao_tai_khoan_tu_danh_sach" not in nguon
