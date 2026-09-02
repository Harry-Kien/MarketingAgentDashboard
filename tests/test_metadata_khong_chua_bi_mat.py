"""
`metadata` của channel account KHÔNG được chứa bí mật.

VÌ SAO CẦN LỚP NÀY
------------------
Trên form Connections Center, ô "metadata" và ô "credentials" nằm cạnh
nhau. Dán nhầm page token vào ô metadata là chuyện SẼ xảy ra, không phải
có thể xảy ra — và hậu quả không nhẹ:

  - credentials đi vào vault, mã hoá AES-256-GCM, có audit
  - metadata đi thẳng vào cột JSONB, KHÔNG mã hoá
  - rồi `ChannelAccount.to_public()` trả metadata nguyên vẹn cho mọi người
    có quyền xem danh sách tài khoản

Nghĩa là một lần dán nhầm đưa bí mật provider ra ngoài vault, ngoài audit,
và vào response API — mà không có gì báo.

Docstring cũ của `to_public()` viết "kiểu này không thể chứa raw
credential". Kiểu dữ liệu không ngăn được gì; chỉ có phép kiểm mới ngăn
được. Đây là phép kiểm đó.
"""
from __future__ import annotations

import pytest

from agent.omnichannel.accounts import MetadataChuaBiMat, kiem_metadata_khong_bi_mat


@pytest.mark.parametrize(
    "khoa",
    [
        "page_token",
        "access_token",
        "app_secret",
        "PASSWORD",
        "api_key",
        "refresh_token",
        "session_cookie",
        "privateKey",
    ],
)
def test_tu_choi_khoa_nghe_giong_bi_mat(khoa):
    with pytest.raises(MetadataChuaBiMat) as loi:
        kiem_metadata_khong_bi_mat({khoa: "gia-tri-bat-ky"})
    assert khoa in str(loi.value)


def test_bat_ca_khoa_long_nhau():
    """Lồng một tầng vẫn là lộ. Chỉ kiểm tầng ngoài là kiểm nửa vời."""
    with pytest.raises(MetadataChuaBiMat):
        kiem_metadata_khong_bi_mat({"meta": {"oauth": {"access_token": "x"}}})


def test_cho_qua_metadata_binh_thuong():
    metadata = {
        "ghi_chu": "Fanpage chi nhánh Quận 1",
        "mui_gio": "Asia/Ho_Chi_Minh",
        "nguoi_phu_trach": {"ten": "Lan", "ca": "sáng"},
        "so_thu_tu": 3,
    }
    assert kiem_metadata_khong_bi_mat(metadata) == metadata


def test_khong_chan_tu_vo_hai_chua_chuoi_con():
    """
    `tokenized`, `keyword` không phải bí mật.

    Chặn quá tay cũng là một kiểu hỏng: người vận hành sẽ học cách né phép
    kiểm, và lần sau họ né cả chỗ đáng chặn.
    """
    kiem_metadata_khong_bi_mat({"keyword": "serum", "tokenized": True})
