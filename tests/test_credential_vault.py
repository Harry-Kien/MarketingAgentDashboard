"""Bảo vệ credential của từng tài khoản kênh."""
from __future__ import annotations

import base64
from dataclasses import replace
from uuid import uuid4

import pytest

from agent.security.credential_vault import (
    CredentialVault,
    InvalidCredentialCiphertext,
    InvalidMasterKeyConfiguration,
    parse_master_keys,
)


def _vault() -> CredentialVault:
    return CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=1)


def test_ma_hoa_va_giai_ma_round_trip():
    account_id = uuid4()
    payload = {"access_token": "secret", "refresh_token": "rotate"}

    sealed = _vault().encrypt(payload, account_id=account_id)

    assert _vault().decrypt(sealed, account_id=account_id) == payload
    assert b"secret" not in sealed.ciphertext
    assert b"rotate" not in sealed.ciphertext
    assert len(sealed.nonce) == 12
    assert sealed.key_version == 1


def test_ciphertext_khong_the_giai_ma_bang_account_khac():
    sealed = _vault().encrypt({"token": "secret"}, account_id=uuid4())

    with pytest.raises(InvalidCredentialCiphertext):
        _vault().decrypt(sealed, account_id=uuid4())


def test_ciphertext_bi_sua_phai_fail_closed():
    account_id = uuid4()
    sealed = _vault().encrypt({"token": "secret"}, account_id=account_id)
    # LẬT MỘT BIT, không gán một giá trị cố định.
    #
    # Bản trước gán byte cuối bằng b"0" (0x30). Ciphertext là dữ liệu ngẫu
    # nhiên, nên cứ 256 lần chạy lại có một lần byte cuối VỐN ĐÃ là 0x30 —
    # "sửa" xong mà không sửa gì, giải mã thành công, và test này đỏ.
    #
    # Bắt gặp thật khi chạy cả bộ. Một test canh tính chất BẢO MẬT mà đỏ
    # ngẫu nhiên là loại tệ nhất: người ta học được cách chạy lại cho xanh,
    # rồi lần nó đỏ THẬT cũng bị chạy lại y như vậy.
    #
    # XOR 0x01 thì luôn đổi, bất kể giá trị gốc.
    sealed = replace(
        sealed,
        ciphertext=sealed.ciphertext[:-1] + bytes([sealed.ciphertext[-1] ^ 0x01]),
    )

    with pytest.raises(InvalidCredentialCiphertext):
        _vault().decrypt(sealed, account_id=account_id)


def test_parse_master_keys_ho_tro_xoay_vong_phien_ban():
    key_1 = base64.b64encode(bytes.fromhex("01" * 32)).decode()
    key_2 = base64.b64encode(bytes.fromhex("02" * 32)).decode()

    parsed = parse_master_keys(f"1:{key_1},2:{key_2}")

    assert parsed == {1: bytes.fromhex("01" * 32), 2: bytes.fromhex("02" * 32)}


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "khong-co-version",
        "0:YWJj",
        "1:YWJj",
        "1:not-base64!",
    ],
)
def test_master_key_sai_hinh_dang_bi_tu_choi(raw: str):
    with pytest.raises(InvalidMasterKeyConfiguration):
        parse_master_keys(raw)


def test_active_key_version_bat_buoc_ton_tai():
    with pytest.raises(InvalidMasterKeyConfiguration, match="active"):
        CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=2)
