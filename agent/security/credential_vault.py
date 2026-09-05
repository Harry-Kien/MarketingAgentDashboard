"""Mã hóa credential theo tài khoản bằng AES-256-GCM."""
from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class InvalidMasterKeyConfiguration(ValueError):
    """Cấu hình master key không đủ an toàn để mở vault."""


class InvalidCredentialCiphertext(ValueError):
    """Ciphertext sai, bị sửa hoặc không thuộc tài khoản đang yêu cầu."""


@dataclass(frozen=True, slots=True)
class SealedCredential:
    key_version: int
    nonce: bytes
    ciphertext: bytes


def parse_master_keys(raw: str) -> dict[int, bytes]:
    """Đọc `version:base64` phân cách bằng dấu phẩy và kiểm key AES-256."""
    if not raw.strip():
        raise InvalidMasterKeyConfiguration("chưa cấu hình credential master key")

    parsed: dict[int, bytes] = {}
    for item in raw.split(","):
        try:
            version_text, encoded = item.strip().split(":", 1)
            version = int(version_text)
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise InvalidMasterKeyConfiguration(
                "credential master key sai định dạng"
            ) from exc
        if version <= 0 or len(key) != 32:
            raise InvalidMasterKeyConfiguration(
                "credential master key phải có version dương và đúng 32 byte"
            )
        if version in parsed:
            raise InvalidMasterKeyConfiguration(
                f"credential master key trùng version: {version}"
            )
        parsed[version] = key
    return parsed


class CredentialVault:
    """Vault hỗ trợ giải mã key cũ và luôn mã hóa bằng active key mới nhất."""

    def __init__(self, keys: Mapping[int, bytes], *, active_version: int):
        copied = dict(keys)
        if active_version not in copied:
            raise InvalidMasterKeyConfiguration(
                "active credential key version không tồn tại"
            )
        if any(version <= 0 or len(key) != 32 for version, key in copied.items()):
            raise InvalidMasterKeyConfiguration(
                "mọi credential master key phải là AES-256 và có version dương"
            )
        self._keys = copied
        self._active_version = active_version

    @staticmethod
    def _aad(account_id: UUID) -> bytes:
        return f"channel-account:{account_id}".encode()

    @staticmethod
    def _aad_pham_vi(pham_vi: str) -> bytes:
        # Tiền tố khác `channel-account:` để hai phạm vi không bao giờ trùng
        # AAD, kể cả khi người gọi truyền đúng chuỗi "channel-account:<id>".
        return f"pham-vi:{pham_vi}".encode()

    def encrypt_pham_vi(
        self, payload: Mapping[str, Any], *, pham_vi: str
    ) -> SealedCredential:
        """Mã hoá cho một phạm vi chuỗi (khoá hệ thống), không gắn tài khoản."""
        nonce = os.urandom(12)
        plaintext = json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        ).encode("utf-8")
        ciphertext = AESGCM(self._keys[self._active_version]).encrypt(
            nonce, plaintext, self._aad_pham_vi(pham_vi),
        )
        return SealedCredential(self._active_version, nonce, ciphertext)

    def decrypt_pham_vi(
        self, sealed: SealedCredential, *, pham_vi: str
    ) -> dict[str, Any]:
        key = self._keys.get(sealed.key_version)
        if key is None:
            raise InvalidCredentialCiphertext("không thể mở giá trị đã mã hóa")
        try:
            plaintext = AESGCM(key).decrypt(
                sealed.nonce, sealed.ciphertext, self._aad_pham_vi(pham_vi),
            )
            decoded = json.loads(plaintext)
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidCredentialCiphertext("không thể mở giá trị đã mã hóa") from exc
        if not isinstance(decoded, dict):
            raise InvalidCredentialCiphertext("giá trị đã mã hóa sai cấu trúc")
        return decoded

    def encrypt(
        self,
        payload: Mapping[str, Any],
        *,
        account_id: UUID,
    ) -> SealedCredential:
        nonce = os.urandom(12)
        plaintext = json.dumps(
            dict(payload),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ciphertext = AESGCM(self._keys[self._active_version]).encrypt(
            nonce,
            plaintext,
            self._aad(account_id),
        )
        return SealedCredential(self._active_version, nonce, ciphertext)

    def decrypt(
        self,
        sealed: SealedCredential,
        *,
        account_id: UUID,
    ) -> dict[str, Any]:
        key = self._keys.get(sealed.key_version)
        if key is None:
            raise InvalidCredentialCiphertext("không thể mở credential đã mã hóa")
        try:
            plaintext = AESGCM(key).decrypt(
                sealed.nonce,
                sealed.ciphertext,
                self._aad(account_id),
            )
            decoded = json.loads(plaintext)
        except (InvalidTag, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidCredentialCiphertext(
                "không thể mở credential đã mã hóa"
            ) from exc
        if not isinstance(decoded, dict):
            raise InvalidCredentialCiphertext("credential đã mã hóa sai cấu trúc")
        return decoded

