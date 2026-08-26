"""Domain model của một kết nối tài khoản kênh."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID


class Channel(StrEnum):
    ZALO_PERSONAL = "zalo_personal"
    ZALO_OA = "zalo_oa"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    WHATSAPP = "whatsapp"
    WEBCHAT = "webchat"

    # Chỉ dùng trong giai đoạn strangler migration. Account mới không được
    # tạo bằng các giá trị này sau khi connector native đạt parity.
    LEGACY_ZALOCRM = "zalocrm"
    LEGACY_CHATWOOT = "chatwoot"
    LEGACY_MESSENGER = "messenger"


class AccountStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    REAUTH_REQUIRED = "reauth_required"
    DISABLED = "disabled"


class MetadataChuaBiMat(ValueError):
    """Metadata công khai đang mang thứ trông như bí mật."""


# Khớp theo TỪ, không khớp theo chuỗi con. `token` phải chặn, `tokenized`
# thì không — chặn quá tay khiến người vận hành học cách né phép kiểm, và
# lần sau họ né cả chỗ đáng chặn.
_TU_BI_MAT = frozenset({
    "token", "secret", "password", "passwd", "pwd", "key", "credential",
    "credentials", "cookie", "session", "signature", "auth", "authorization",
    "bearer", "otp",
})


def _tach_tu(khoa: str) -> set[str]:
    """`accessToken`, `access_token`, `ACCESS-TOKEN` -> {"access", "token"}."""
    ra: list[str] = []
    dem = ""
    for ky_tu in khoa:
        if ky_tu in "_-. ":
            ra.append(dem)
            dem = ""
        elif ky_tu.isupper() and dem and not dem[-1].isupper():
            ra.append(dem)
            dem = ky_tu
        else:
            dem += ky_tu
    ra.append(dem)
    return {t.lower() for t in ra if t}


def kiem_metadata_khong_bi_mat(metadata: Mapping[str, Any], _duong: str = "") -> Mapping[str, Any]:
    """
    Chặn bí mật lọt vào cột metadata KHÔNG mã hoá.

    VÌ SAO CHẶN Ở ĐÂY CHỨ KHÔNG PHẢI Ở PYDANTIC
    --------------------------------------------
    Validator trên một model API chỉ khoá một cửa. Script nhập liệu, lệnh
    quản trị, hay một route thêm sau này đều đi vòng qua nó. Đặt phép kiểm ở
    tầng domain thì mọi đường tạo tài khoản đều phải qua.

    Trả lại chính metadata để chỗ gọi dùng được như một biểu thức.
    """
    for khoa, gia_tri in metadata.items():
        duong = f"{_duong}.{khoa}" if _duong else str(khoa)
        if _tach_tu(str(khoa)) & _TU_BI_MAT:
            raise MetadataChuaBiMat(
                f"metadata không được chứa bí mật: '{duong}'. "
                f"Thông tin đăng nhập phải đi qua trường credentials để được "
                f"mã hoá trong vault."
            )
        if isinstance(gia_tri, Mapping):
            kiem_metadata_khong_bi_mat(gia_tri, duong)
    return metadata


@dataclass(frozen=True, slots=True)
class ChannelAccount:
    """Thông tin không bí mật của một tài khoản đã kết nối."""

    id: UUID
    channel: Channel
    display_name: str
    external_account_id: str | None
    status: AccountStatus
    capabilities: Mapping[str, Any]
    metadata: Mapping[str, Any]
    is_legacy: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_public(self, *, has_credentials: bool) -> dict[str, Any]:
        """
        Response công khai: chỉ báo CÓ credential hay không, không trả giá trị.

        CẢNH BÁO CHO NGƯỜI SỬA SAU
        --------------------------
        `metadata` được trả nguyên vẹn ra đây. Kiểu dữ liệu KHÔNG ngăn được
        bí mật lọt vào nó — chỉ `kiem_metadata_khong_bi_mat()` ở đường tạo
        tài khoản mới ngăn được. Thêm một đường ghi metadata mà quên gọi
        phép kiểm đó là mở lại đúng lỗ hổng này.

        (Chú thích cũ ở đây khẳng định "kiểu này không thể chứa raw
        credential". Câu đó sai, và một chú thích sai còn nguy hiểm hơn
        không có chú thích: nó khiến người đọc thôi kiểm tra.)
        """
        return {
            "id": str(self.id),
            "channel": self.channel.value,
            "display_name": self.display_name,
            "external_account_id": self.external_account_id,
            "status": self.status.value,
            "capabilities": dict(self.capabilities),
            "metadata": dict(self.metadata),
            "is_legacy": self.is_legacy,
            "has_credentials": has_credentials,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

