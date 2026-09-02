"""
Adapter Meta chỉ được đọc phần webhook THUỘC VỀ tài khoản của nó.

VÌ SAO LÀ VẤN ĐỀ
----------------
Một webhook Meta có thể mang `entry[]` của nhiều tài khoản cùng lúc. Bộ
điều phối gọi `parse_nhieu(payload)` với TOÀN BỘ payload cho từng adapter,
nên mỗi adapter phải tự lọc lấy phần của mình.

Phép lọc cũ viết dạng `if self._external_account_id and ...` — tức là khi
adapter chưa gắn định danh thì **bỏ luôn phép lọc** và nuốt hết mọi entry.
Đó là fail-open: hỏng thì mở rộng quyền chứ không thu hẹp.

Hậu quả nếu trúng: tin của khách thuộc tài khoản B được ghi vào tài khoản
A, và câu trả lời đi ra từ đúng tài khoản sai — loại lỗi mà cả `account_id`
lẫn audit đều không phát hiện được, vì mọi thứ "khớp" theo dữ liệu đã sai.
"""
from __future__ import annotations

from uuid import uuid4

from agent.channels.meta_channels import InstagramAdapter, WhatsAppAdapter


def test_instagram_khong_doc_gi_khi_chua_gan_dinh_danh():
    adapter = InstagramAdapter(account_id=uuid4(), credentials={})
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "tai-khoan-cua-nguoi-khac",
                "messaging": [
                    {
                        "sender": {"id": "khach-1"},
                        "message": {"mid": "m1", "text": "xin chào"},
                    }
                ],
            }
        ],
    }

    assert adapter.parse_nhieu(payload) == []


def test_whatsapp_khong_doc_gi_khi_chua_gan_so_dien_thoai():
    adapter = WhatsAppAdapter(account_id=uuid4(), credentials={})
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "so-cua-nguoi-khac"},
                            "messages": [
                                {
                                    "from": "84900000000",
                                    "id": "wamid.1",
                                    "type": "text",
                                    "text": {"body": "xin chào"},
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }

    assert adapter.parse_nhieu(payload) == []
