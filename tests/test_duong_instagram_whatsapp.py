"""
Đường Instagram và WhatsApp: đọc được tin, và KHÔNG đọc nhầm tin người khác.

VÌ SAO PHẢI CANH RIÊNG HAI KÊNH NÀY
------------------------------------
Meta gửi webhook của NHIỀU tài khoản vào CÙNG một địa chỉ, và bộ điều phối
đưa nguyên payload cho từng adapter tự lọc. Nghĩa là phép lọc trong adapter
là thứ DUY NHẤT ngăn tài khoản A đọc tin của tài khoản B.

Lọc sai kiểu "fail open" — thiếu định danh thì đọc tất — nghĩa là agent trả
lời khách của shop khác, từ tài khoản khác, và không có gì lệch để ai nhận
ra. Đó là rò rỉ dữ liệu, không phải lỗi hiển thị.

Ba đường phòng thủ dưới đây đều đã có trong mã. File này giữ chúng ở đó.
"""
from __future__ import annotations

import uuid

import pytest

IG_ID = "17841400000000000"
WA_PHONE_ID = "1088888888"


def _ig(text: str = "Serum nay con hang khong a?", **doi) -> dict:
    tin = {"mid": "mid-1", "text": text}
    tin.update(doi.pop("message", {}))
    return {
        "object": doi.pop("object", "instagram"),
        "entry": [{
            "id": doi.pop("entry_id", IG_ID),
            "messaging": [{
                "sender": {"id": "ig-user-1"},
                "recipient": {"id": IG_ID},
                "timestamp": 1787760000,
                "message": tin,
            }],
        }],
    }


def _wa(text: str = "Cho minh hoi gia", phone_id: str = WA_PHONE_ID,
        **doi) -> dict:
    return {
        "object": doi.pop("object", "whatsapp_business_account"),
        "entry": [{
            "id": "waba-1",
            "changes": [{
                "field": "messages",
                "value": {
                    "metadata": {"phone_number_id": phone_id},
                    "contacts": [{"wa_id": "84900000001",
                                  "profile": {"name": "Chị Lan"}}],
                    "messages": [{
                        "from": "84900000001", "id": "wamid-1",
                        "type": "text", "text": {"body": text},
                    }],
                },
            }],
        }],
    }


def _ig_adapter(dinh_danh: str | None = IG_ID):
    from agent.channels.meta_channels import InstagramAdapter

    creds = {"access_token": "T", "app_secret": "S"}
    if dinh_danh:
        creds["external_account_id"] = dinh_danh
    return InstagramAdapter(account_id=uuid.uuid4(), credentials=creds)


def _wa_adapter(dinh_danh: str | None = WA_PHONE_ID):
    from agent.channels.meta_channels import WhatsAppAdapter

    creds = {"access_token": "T", "app_secret": "S"}
    if dinh_danh:
        creds["phone_number_id"] = dinh_danh
    return WhatsAppAdapter(account_id=uuid.uuid4(), credentials=creds)


# --- Cả hai kênh phải nằm trong bộ dựng adapter ---

@pytest.mark.parametrize("kenh,lop", [
    ("INSTAGRAM", "InstagramAdapter"),
    ("WHATSAPP", "WhatsAppAdapter"),
    ("FACEBOOK", "FacebookAdapter"),
])
def test_kenh_duoc_dang_ky_trong_factory(kenh, lop):
    """
    Tạo được tài khoản mà factory không biết dựng adapter thì tin về tới nơi
    rồi rơi vào hư không — đúng kiểu "có khả năng nhưng không nối vào đường
    chạy" đã gặp nhiều lần trong dự án này.
    """
    from agent.channels.factory import _NATIVE_ADAPTERS
    from agent.omnichannel.accounts import Channel

    assert _NATIVE_ADAPTERS[getattr(Channel, kenh)].__name__ == lop


# --- Đọc được tin thật ---

def test_instagram_doc_duoc_tin():
    tin = _ig_adapter().parse_nhieu(_ig())
    assert len(tin) == 1
    assert tin[0].channel == "instagram"
    assert "Serum" in tin[0].text


def test_whatsapp_doc_duoc_tin_va_ten_khach():
    tin = _wa_adapter().parse_nhieu(_wa())
    assert len(tin) == 1
    assert tin[0].channel == "whatsapp"
    assert tin[0].customer_name == "Chị Lan", "WhatsApp CÓ tên khách sẵn trong webhook"


# --- Ba đường phòng thủ ---

def test_instagram_bo_qua_entry_cua_tai_khoan_khac():
    tin = _ig_adapter().parse_nhieu(_ig(entry_id="17841499999999999"))
    assert tin == [], "adapter đang nuốt tin của tài khoản Instagram khác"


def test_whatsapp_bo_qua_so_dien_thoai_khac():
    tin = _wa_adapter().parse_nhieu(_wa(phone_id="1099999999"))
    assert tin == [], "adapter đang nuốt tin của số WhatsApp khác"


@pytest.mark.parametrize("tao,goi", [
    (_ig_adapter, _ig),
    (_wa_adapter, _wa),
])
def test_thieu_dinh_danh_thi_KHONG_doc_gi(tao, goi):
    """
    FAIL CLOSED, không fail open.

    Thiếu định danh mà vẫn đọc nghĩa là đọc tin của MỌI tài khoản trong cùng
    webhook — rồi trả lời khách từ đúng tài khoản sai.
    """
    assert tao(None).parse_nhieu(goi()) == []


def test_instagram_bo_qua_tin_vong():
    """
    Meta đẩy lại chính tin tài khoản vừa gửi, kèm cờ `is_echo`.

    Không lọc thì agent đọc câu trả lời của mình rồi trả lời tiếp. Vòng lặp
    vọng này đã xảy ra thật ở kênh Zalo trong dự án này.
    """
    tin = _ig_adapter().parse_nhieu(_ig(message={"is_echo": True}))
    assert tin == []


@pytest.mark.parametrize("tao,goi,object_sai", [
    (_ig_adapter, _ig, "page"),
    (_wa_adapter, _wa, "instagram"),
])
def test_khong_doc_payload_cua_kenh_khac(tao, goi, object_sai):
    """Một địa chỉ webhook nhận cả ba kênh — đọc nhầm loại là đọc nhầm tin."""
    assert tao().parse_nhieu(goi(object=object_sai)) == []


# --- Bộ đọc webhook phải biết cả ba loại ---

@pytest.mark.parametrize("loai", [
    "page", "instagram", "whatsapp_business_account",
])
def test_webhook_nhan_du_ba_loai_object(loai):
    from pathlib import Path

    nguon = (Path(__file__).resolve().parents[1] / "agent" / "api"
             / "native_webhooks.py").read_text(encoding="utf-8")
    assert f'"{loai}"' in nguon, f"bộ đọc webhook chưa biết object {loai}"
