"""
Script nối Telegram: lấy chat id và ghi cấu hình, KHÔNG in token.

VÌ SAO CÓ SCRIPT NÀY
--------------------
Nối Telegram cần hai giá trị: token (bí mật) và chat id (không bí mật, chỉ
là một con số). Lấy chat id thì phải gọi Telegram bằng chính token đó.

Bắt người dùng tự làm cả chuỗi ấy — mở trình duyệt, đọc JSON thô, tìm đúng
con số trong đống dữ liệu, rồi tự ghép hai dòng cấu hình — là bốn chỗ có
thể sai, và sai nào cũng dẫn tới "báo động im lặng không hoạt động".

Script làm hộ phần máy làm được. Token chỉ đi từ file .env vào bộ nhớ tiến
trình rồi thôi: không in ra màn hình, không vào lịch sử lệnh.
"""
from __future__ import annotations

import pytest

from scripts.noi_telegram import chat_id_tu_getupdates, dung_hai_dong


def test_lay_chat_id_tu_phan_hoi_that():
    phan_hoi = {
        "ok": True,
        "result": [
            {"update_id": 1,
             "message": {"chat": {"id": 123456789, "type": "private"},
                         "text": "chào"}},
        ],
    }
    assert chat_id_tu_getupdates(phan_hoi) == "123456789"


def test_lay_cai_MOI_NHAT_khi_co_nhieu_cuoc_tro_chuyen():
    """
    Người dùng thường nhắn thử vài lần. Lấy cái cũ nhất là ghi nhầm vào một
    cuộc trò chuyện họ đã bỏ, rồi báo động đi vào chỗ không ai đọc.
    """
    phan_hoi = {"ok": True, "result": [
        {"update_id": 1, "message": {"chat": {"id": 111}}},
        {"update_id": 2, "message": {"chat": {"id": 222}}},
    ]}
    assert chat_id_tu_getupdates(phan_hoi) == "222"


def test_chua_nhan_gi_cho_bot_thi_bao_ro_phai_lam_gi():
    """
    Telegram KHÔNG cho bot nhắn trước. Chưa nhắn thì `result` rỗng — và đây
    là chỗ mọi người mắc kẹt. Lỗi phải nói ra việc cần làm, không chỉ nói
    'không tìm thấy'.
    """
    with pytest.raises(ValueError) as loi:
        chat_id_tu_getupdates({"ok": True, "result": []})
    assert "nhắn" in str(loi.value).lower()


def test_hai_dong_cau_hinh_dung_dinh_dang():
    webhook, goi_tin = dung_hai_dong("TOKEN-GIA", "999")
    assert webhook.endswith("/sendMessage")
    assert "TOKEN-GIA" in webhook
    assert '"chat_id":"999"' in goi_tin
    # Phải nằm TRỌN trên một dòng — .env không hiểu giá trị xuống dòng.
    assert "\n" not in goi_tin
