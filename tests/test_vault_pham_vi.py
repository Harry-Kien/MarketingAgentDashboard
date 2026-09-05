"""
Vault phải tách PHẠM VI: bản mã của tài khoản kênh không mở được bằng
phạm vi cấu hình và ngược lại, dù cùng khoá chủ. Không có tách này thì một
lỗi tra nhầm bảng sẽ giải mã "đúng" ra một thứ sai — im lặng.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from agent.security.credential_vault import (
    CredentialVault, InvalidCredentialCiphertext,
)


def _vault():
    return CredentialVault({1: bytes.fromhex("01" * 32)}, active_version=1)


def test_ma_hoa_va_giai_ma_theo_pham_vi():
    v = _vault()
    sealed = v.encrypt_pham_vi({"gia_tri": "abc"}, pham_vi="cau-hinh:GEMINI_API_KEY")
    assert v.decrypt_pham_vi(sealed, pham_vi="cau-hinh:GEMINI_API_KEY") == {"gia_tri": "abc"}


def test_khac_pham_vi_thi_khong_mo_duoc():
    v = _vault()
    sealed = v.encrypt_pham_vi({"gia_tri": "abc"}, pham_vi="cau-hinh:A")
    with pytest.raises(InvalidCredentialCiphertext):
        v.decrypt_pham_vi(sealed, pham_vi="cau-hinh:B")


def test_ban_ma_tai_khoan_kenh_khong_mo_duoc_bang_pham_vi_cau_hinh():
    v = _vault()
    acc = uuid4()
    sealed = v.encrypt({"token": "t"}, account_id=acc)
    with pytest.raises(InvalidCredentialCiphertext):
        v.decrypt_pham_vi(sealed, pham_vi=f"channel-account:{acc}")
