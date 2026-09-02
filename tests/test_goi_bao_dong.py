"""
Dạng gói tin báo động phải KHAI ĐƯỢC, không gắn cứng vào mã.

VẤN ĐỀ
------
`canh_gac` POST một dạng cố định: {muc_do, tieu_de, chi_tiet, ...}. Nhưng
mỗi nơi nhận đòi một dạng khác — Telegram cần {chat_id, text}, Slack cần
{text}, Discord cần {content}.

Gắn cứng Telegram vào mã là nhốt một quyết định VẬN HÀNH vào mã nguồn, và
có test cấm đúng điều đó (test_bao_dong_di_qua_webhook_khong_gan_cung_zalo).
Bắt người dùng dựng n8n chỉ để đổi tên ba trường cũng là bắt họ nuôi thêm
một tiến trình có thể chết.

Đường giữa: một mẫu chuỗi trong cấu hình. Trung lập với mọi nhà cung cấp,
không thêm tiến trình nào.

AN TOÀN
-------
Giá trị chèn vào mẫu phải được thoát theo chuẩn JSON. Chi tiết báo động có
thể chứa dấu nháy, xuống dòng, tiếng Việt — chèn thô là gói tin vỡ, và nơi
nhận từ chối đúng lúc hệ thống đang hỏng.
"""
from __future__ import annotations

import json

from agent.canh_gac import dung_goi_bao_dong

TRUONG = {
    "muc_do": "hong",
    "tieu_de": "Agent KHÔNG PHẢN HỒI",
    "chi_tiet": 'Cổng 8000 im lặng — "timeout" sau 15 giây',
    "trang_thai": "hong",
}


def test_khong_khai_mau_thi_giu_nguyen_dang_cu():
    """Không được làm vỡ cấu hình đang chạy của ai đó."""
    goi = dung_goi_bao_dong(TRUONG, mau="")
    assert goi["muc_do"] == "hong"
    assert goi["tieu_de"] == "Agent KHÔNG PHẢN HỒI"


def test_khai_mau_thi_theo_mau():
    mau = '{"chat_id":"123","text":"[{muc_do}] {tieu_de}"}'
    goi = dung_goi_bao_dong(TRUONG, mau=mau)
    assert goi == {"chat_id": "123", "text": "[hong] Agent KHÔNG PHẢN HỒI"}


def test_thoat_ky_tu_dac_biet_de_goi_tin_khong_vo():
    """Chi tiết có dấu nháy kép — chèn thô là JSON vỡ."""
    mau = '{"text":"{chi_tiet}"}'
    goi = dung_goi_bao_dong(TRUONG, mau=mau)
    assert goi["text"] == TRUONG["chi_tiet"]
    json.dumps(goi)


def test_mau_hong_thi_khong_lam_chet_canh_gac():
    """
    Mẫu gõ sai KHÔNG được làm mất báo động.

    Nếu mẫu hỏng mà ta ném lỗi, thì đúng lúc hệ thống chết cũng là lúc báo
    động chết theo — và không ai biết gì cả. Rơi về dạng cũ còn hơn im.
    """
    goi = dung_goi_bao_dong(TRUONG, mau='{"text": khong-phai-json}')
    assert goi["muc_do"] == "hong"


def test_khoa_la_trong_mau_khong_lam_vo():
    """Người dùng gõ {khong_ton_tai} thì để nguyên, đừng ném lỗi."""
    goi = dung_goi_bao_dong(TRUONG, mau='{"text":"{khong_ton_tai}"}')
    assert isinstance(goi, dict)
