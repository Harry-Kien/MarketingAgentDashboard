"""
Zalo OA dùng HAI phiên bản API cùng lúc, và Zalo không gộp chúng.

ĐO ĐƯỢC TRÊN OA THẬT (03.09.2026), cùng một access token:

    v3.0/oa/message/cs      hoạt động   <- gửi tin
    v3.0/oa/getoa           error 404 "empty or invalid API"
    v2.0/oa/getoa           hoạt động   <- thông tin OA
    v3.0/oa/upload/image    error 404 "empty or invalid API"
    v2.0/oa/upload/image    hoạt động   (error -201 "File not exist"
                                        = đường CÓ, chỉ thiếu file)

Adapter để `api_base = v3.0` cho mọi thứ, nên `verify_connection` luôn trả
`provider.rejected` với `provider_code: 404` — người dùng thấy "Gián đoạn"
và không có cách nào biết vì sao. Họ đi kiểm lại credential ba lần, trong
khi credential đã đúng ngay từ lần thứ hai.

`upload/image` cũng hỏng y hệt, chỉ chưa ai gặp vì kênh chưa từng kết nối
được — gửi ảnh qua Zalo OA sẽ hỏng vào đúng ngày kênh chạy.

VÌ SAO LỖI NÀY SỐNG ĐƯỢC LÂU

`error` nằm trong THÂN JSON, không nằm ở mã HTTP: cả hai lượt gọi đều trả
HTTP 200. Mọi phép kiểm nhìn `status_code` đều thấy xanh.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.channels.zalo_oa import ZaloOAAdapter  # noqa: E402


def _adapter(api_base: str | None = None) -> ZaloOAAdapter:
    cred = {"app_id": "1", "secret_key": "s", "refresh_token": "r"}
    if api_base:
        cred["api_base"] = api_base
    return ZaloOAAdapter(credentials=cred)


# ---------------------------------------------------------------
#  Đường nào ở phiên bản nào
# ---------------------------------------------------------------

@pytest.mark.parametrize("duong", ["getoa", "upload/image"])
def test_duong_chi_co_tren_v2_thi_dung_v2(duong):
    ad = _adapter()
    url = ad._url_v2(duong)
    assert "/v2.0/" in url, f"{duong} phải gọi v2.0, đang gọi: {url}"
    assert url.endswith(duong)


def test_khong_ha_ca_api_base_xuong_v2():
    """
    Hạ cả `api_base` là chữa hai đường và PHÁ đường gửi tin — đổi một lỗi
    chưa ai gặp lấy một lỗi ai cũng gặp.
    """
    ad = _adapter()
    assert "/v3.0" in ad._api_base, (
        "api_base phải giữ v3.0 cho /message/cs"
    )


def test_url_v2_dung_dau_gach_cheo_dau():
    """`getoa` và `/getoa` phải ra cùng một URL."""
    ad = _adapter()
    assert ad._url_v2("getoa") == ad._url_v2("/getoa")


@pytest.mark.parametrize(
    "goc,mong_doi",
    [
        ("https://openapi.zalo.me/v3.0/oa", "https://openapi.zalo.me/v2.0/oa/getoa"),
        ("https://openapi.zalo.me/v3.0/oa/", "https://openapi.zalo.me/v2.0/oa/getoa"),
        # Đã là v2.0 thì giữ nguyên, không đổi thành v1.
        ("https://openapi.zalo.me/v2.0/oa", "https://openapi.zalo.me/v2.0/oa/getoa"),
    ],
)
def test_doi_phien_ban_dung_voi_moi_dang_api_base(goc, mong_doi):
    assert _adapter(goc)._url_v2("getoa") == mong_doi


def test_api_base_ghim_rieng_van_duoc_ton_trong():
    """
    Credential được phép ghim `api_base` để gỡ lỗi hoặc trỏ vào máy giả.
    Nếu `_url_v2` viết cứng tên miền Zalo thì test tích hợp không chặn được
    lời gọi ra Internet thật.
    """
    ad = _adapter("http://127.0.0.1:9999/v3.0/oa")
    assert ad._url_v2("getoa") == "http://127.0.0.1:9999/v2.0/oa/getoa"


# ---------------------------------------------------------------
#  Mã nguồn không được quay lại đường tương đối
# ---------------------------------------------------------------

NGUON = (ROOT / "agent" / "channels" / "zalo_oa.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("duong", ['"/getoa"', '"/upload/image"'])
def test_khong_con_goi_bang_duong_tuong_doi(duong):
    """
    Đường tương đối ghép vào `base_url` v3.0, và đó chính là lỗi cũ. Nó trả
    HTTP 200 nên không phép kiểm nào nhìn `status_code` bắt được.
    """
    assert duong not in NGUON, (
        f"{duong} gọi bằng đường tương đối — sẽ ghép vào base_url v3.0 và "
        "Zalo trả error 404 trong thân JSON với HTTP 200"
    )


def test_message_cs_van_dung_duong_tuong_doi():
    """
    Chiều ngược lại: `/message/cs` PHẢI ở v3.0. Đổi nó sang `_url_v2` là
    phá đường gửi tin — thứ duy nhất kênh này thật sự làm.
    """
    assert '"/message/cs"' in NGUON, "/message/cs phải giữ base_url v3.0"
    assert '_url_v2("message/cs")' not in NGUON
