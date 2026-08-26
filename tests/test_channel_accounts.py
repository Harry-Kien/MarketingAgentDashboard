"""Hợp đồng domain của tài khoản kênh."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from agent.omnichannel.accounts import AccountStatus, Channel, ChannelAccount


def test_public_view_khong_bao_gio_chua_bi_mat():
    """Thêm trạng thái credential không được biến response thành nơi lộ token."""
    account = ChannelAccount(
        id=uuid4(),
        channel=Channel.ZALO_OA,
        display_name="OA Hà Nội",
        external_account_id="oa-1",
        status=AccountStatus.ACTIVE,
        capabilities={"send_text": True},
        metadata={"province": "Hà Nội"},
        is_legacy=False,
    )

    public = account.to_public(has_credentials=True)

    assert public["has_credentials"] is True
    assert public["channel"] == "zalo_oa"
    assert public["display_name"] == "OA Hà Nội"
    serialized = json.dumps(public)
    assert "credentials" not in public
    assert "access_token" not in serialized.lower()
    assert "refresh_token" not in serialized.lower()


def test_channel_la_bi_tu_choi_ro_rang():
    """Sai chính tả tên kênh không được âm thầm tạo account không có adapter."""
    with pytest.raises(ValueError):
        Channel("facebooke")


def test_domain_ho_tro_du_sau_kenh_native_v1():
    assert {
        Channel.ZALO_PERSONAL,
        Channel.ZALO_OA,
        Channel.FACEBOOK,
        Channel.INSTAGRAM,
        Channel.WHATSAPP,
        Channel.WEBCHAT,
    } <= set(Channel)

