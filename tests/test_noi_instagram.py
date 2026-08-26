"""
Instagram phải TỰ nối theo Trang, không bắt người dùng làm lại từ đầu.

VÌ SAO
------
Trên Meta, một tài khoản Instagram Business luôn gắn với một Trang Facebook.
Người dùng đã cấp quyền cho Trang rồi thì tài khoản Instagram của Trang đó
dùng CHUNG luôn Page access token — không cần thêm một lần đăng nhập nào.

Trước file này, luồng OAuth XIN quyền `instagram_basic` và
`instagram_manage_messages` nhưng KHÔNG BAO GIỜ tạo một tài khoản Instagram
nào. Đo được trên CSDL: 26 tài khoản Facebook, 0 Instagram.

Đó là hai cái sai cùng lúc:

  1. Người dùng nối Facebook xong vẫn phải tự đi khai Instagram bằng tay,
     dán Instagram Business ID và access token — đúng việc mà luồng OAuth
     sinh ra để xoá bỏ.
  2. App Review của Meta bắt giải trình TỪNG quyền. Xin quyền rồi không dùng
     là lý do bị từ chối — và cũng là thu thập quyền truy cập không cần thiết
     vào tài khoản của người dùng.
"""
from __future__ import annotations

import inspect


def test_xin_luon_instagram_trong_cung_mot_loi_goi():
    """
    Hỏi `/me/accounts` một lần là có luôn Instagram của từng Trang.

    Gọi riêng cho mỗi Trang là 26 lời gọi mạng nữa, và người dùng ngồi nhìn
    màn hình trắng lâu gấp đôi.
    """
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta.meta_callback)
    assert "instagram_business_account" in nguon, (
        "chưa xin Instagram trong lời gọi /me/accounts"
    )


def test_doc_duoc_instagram_gan_voi_trang():
    from agent.api.oauth_meta import doc_trang_tu_me_accounts

    ra = doc_trang_tu_me_accounts({"data": [{
        "id": "111", "name": "Shop A", "access_token": "T1",
        "tasks": ["MESSAGING"],
        "instagram_business_account": {"id": "ig-1", "username": "shopa"},
    }]})

    assert len(ra) == 1
    assert ra[0]["instagram_id"] == "ig-1"
    assert ra[0]["instagram_username"] == "shopa"


def test_trang_khong_co_instagram_van_noi_binh_thuong():
    """Phần lớn Trang không gắn Instagram. Thiếu nó không được làm hỏng gì."""
    from agent.api.oauth_meta import doc_trang_tu_me_accounts

    ra = doc_trang_tu_me_accounts({"data": [{
        "id": "222", "name": "Shop B", "access_token": "T2",
        "tasks": ["MESSAGING"],
    }]})

    assert len(ra) == 1
    assert ra[0]["instagram_id"] == ""


def test_instagram_hong_dinh_dang_khong_lam_vo_ca_danh_sach():
    """
    Graph đôi khi trả `instagram_business_account` là null hoặc kiểu khác.

    Một Trang dữ liệu lạ không được làm hỏng 25 Trang còn lại.
    """
    from agent.api.oauth_meta import doc_trang_tu_me_accounts

    ra = doc_trang_tu_me_accounts({"data": [
        {"id": "1", "name": "A", "access_token": "T", "tasks": ["MESSAGING"],
         "instagram_business_account": None},
        {"id": "2", "name": "B", "access_token": "T", "tasks": ["MESSAGING"],
         "instagram_business_account": "chuoi la"},
        {"id": "3", "name": "C", "access_token": "T", "tasks": ["MESSAGING"],
         "instagram_business_account": {"id": "ig-3"}},
    ]})

    assert len(ra) == 3
    assert ra[0]["instagram_id"] == ""
    assert ra[1]["instagram_id"] == ""
    assert ra[2]["instagram_id"] == "ig-3"


def test_oauth_tao_ca_tai_khoan_instagram():
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta._tao_tai_khoan_tu_danh_sach)
    assert "Channel.INSTAGRAM" in nguon, "OAuth chưa tạo tài khoản Instagram nào"


def test_instagram_dung_CHUNG_page_token():
    """
    Instagram Business nhận tin qua chính Page access token của Trang liên
    kết. Đòi người dùng một token riêng là bắt họ đi tìm thứ không tồn tại.
    """
    from agent.api import oauth_meta

    nguon = inspect.getsource(oauth_meta._tao_tai_khoan_tu_danh_sach)
    khoi = nguon.split("Channel.INSTAGRAM", 1)[1][:900]
    assert 'trang["access_token"]' in khoi


def test_bao_ro_so_instagram_da_noi():
    """
    Gộp Instagram vào con số "đã nối N Trang" là người dùng không biết
    Instagram của mình đã vào hay chưa.
    """
    from agent.api import oauth_meta

    assert "instagram" in inspect.getsource(oauth_meta.meta_callback).lower()


def test_quyen_instagram_van_duoc_xin():
    """Bỏ quyền đi thì luồng trên không chạy được nữa."""
    from agent.api.oauth_meta import QUYEN

    assert "instagram_basic" in QUYEN
    assert "instagram_manage_messages" in QUYEN
