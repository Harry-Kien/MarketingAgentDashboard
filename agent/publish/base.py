"""
Ranh giới phân phối nội dung — cùng khuôn mẫu với ChannelAdapter.

VÌ SAO CẦN LỚP NÀY
------------------
Đăng bài lên Facebook / Instagram / TikTok bị chặn bởi QUY TRÌNH DUYỆT của
nền tảng, không phải bởi mã nguồn:

  Facebook / Instagram : cần Business Verification + App Review cho quyền
                         pages_manage_posts và instagram_content_publish.
                         Mất 1-4 tuần, có thể bị từ chối.
  TikTok               : Content Posting API phải qua audit. Chưa audit thì
                         bài đăng bị ép về chế độ riêng tư.

Nếu viết thẳng lời gọi Graph API vào mã nghiệp vụ thì hệ thống đứng im cho
tới ngày được duyệt. Với lớp này, phần trên chỉ biết "đăng bài đi" — còn
đăng bằng đường nào là chuyện của adapter:

  n8n     : đẩy qua webhook n8n (n8n có sẵn node Facebook/TikTok/Instagram)
            -> CHẠY ĐƯỢC NGAY, không cần chờ duyệt gì
  manual  : chỉ đưa vào hàng đợi, người tải video xuống và tự đăng
            -> luôn dùng được, là lưới an toàn cuối cùng
  facebook, tiktok : gọi thẳng API chính thức
            -> mã đã sẵn sàng, bật khi có quyền

Đổi đường phân phối = đổi một biến trong .env, không sửa agent.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PublishTarget:
    """Một bài cần đăng lên một kênh cụ thể."""

    post_id: str
    kenh: str                      # facebook | instagram | tiktok | youtube
    tieu_de: str
    noi_dung: str
    hashtags: list[str] = field(default_factory=list)
    video_path: Path | None = None
    anh_paths: list[Path] = field(default_factory=list)

    def video_url(self) -> str:
        """
        URL công khai của video, hoặc rỗng nếu không có.

        VÌ SAO KHÔNG DÙNG `video_path.name`
        -----------------------------------
        Dây chuyền dựng video đặt mỗi video trong một thư mục riêng theo id:

            data/videos/<id-video>/video.mp4

        Nên `.name` của MỌI video đều là "video.mp4". Dựng URL từ nó ra
        `/media/videos/video.mp4` — vừa không tồn tại, vừa GIỐNG HỆT NHAU
        cho mọi video. Instagram sẽ nhận 404, hoặc tệ hơn, nếu tình cờ có
        một file tên đó thì mọi bài đăng đều dùng chung một video.

        Lỗi này im lặng cho tới đúng ngày ai đó bật đăng tự động.

        Phải là đường TƯƠNG ĐỐI so với thư mục được mount, và phải dùng dấu
        gạch chéo xuôi — Windows trả về dấu ngược, mà dấu ngược trong URL
        thì máy chủ không hiểu.
        """
        if not self.video_path:
            return ""
        from ..config import settings
        goc = settings.video_out_path
        try:
            tuong_doi = self.video_path.resolve().relative_to(goc.resolve())
        except (ValueError, OSError):
            # File nằm ngoài thư mục được mount -> không có URL công khai.
            # Trả rỗng để bên gọi biết mà dùng đường khác, thay vì dựng ra
            # một URL trông đúng nhưng luôn 404.
            return ""
        duong = "/".join(tuong_doi.parts)
        return f"{settings.public_base_url}/media/videos/{duong}"

    def caption(self) -> str:
        """Nội dung kèm hashtag, đúng cách người Việt viết caption."""
        tags = " ".join(
            t if t.startswith("#") else f"#{t}" for t in self.hashtags if t
        )
        return f"{self.noi_dung}\n\n{tags}".strip() if tags else self.noi_dung


@dataclass(slots=True)
class PublishResult:
    ok: bool
    kenh: str
    url: str = ""
    detail: str = ""
    # Adapter không đăng được ngay mà chỉ nhận việc (n8n chạy bất đồng bộ,
    # hoặc hàng đợi thủ công) -> đánh dấu để dashboard hiển thị đúng.
    da_nhan_chua_dang: bool = False


class PublishAdapter(ABC):
    """Hợp đồng mà mọi đường phân phối phải tuân thủ."""

    name: str = "base"

    @abstractmethod
    async def publish(self, target: PublishTarget) -> PublishResult: ...

    async def san_sang(self) -> tuple[bool, str]:
        """
        Kênh này dùng được chưa? Trả (được/không, lý do).

        Dashboard hiển thị lý do để người vận hành biết vì sao một kênh
        đang tắt — thà nói rõ còn hơn im lặng thất bại.
        """
        return True, ""

    async def aclose(self) -> None:
        return None
