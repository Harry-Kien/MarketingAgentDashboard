"""
Kiểm thử URL video công khai và điều kiện duyệt video. Không gọi API.

Hai lỗi ở đây thuộc loại nguy hiểm nhất: chúng IM LẶNG cho tới đúng ngày
ai đó bật đăng tự động hoặc bấm tải video, và lúc đó thì đã ở trước mặt
khách rồi.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api import routes  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.publish.base import PublishTarget  # noqa: E402


def _muc_tieu(duong: Path | None) -> PublishTarget:
    return PublishTarget(post_id="p1", kenh="instagram", tieu_de="t",
                         noi_dung="n", video_path=duong)


# =====================================================================
#  URL video
# =====================================================================

def test_hai_video_khac_nhau_ra_hai_url_khac_nhau():
    """
    Lỗi đã xảy ra thật: dây chuyền đặt mỗi video ở `data/videos/<id>/
    video.mp4`, nên `.name` của MỌI video đều là "video.mp4". Dựng URL từ
    nó ra cùng một đường cho tất cả — Instagram nhận 404, hoặc tệ hơn, mọi
    bài đăng dùng chung một video.
    """
    goc = settings.video_out_path
    a = _muc_tieu(goc / "id-mot" / "video.mp4").video_url()
    b = _muc_tieu(goc / "id-hai" / "video.mp4").video_url()
    assert a and b
    assert a != b, "hai video khác nhau đang ra CÙNG một URL"
    assert "id-mot" in a and "id-hai" in b


def test_url_dung_dau_gach_xuoi():
    """Windows trả dấu ngược, mà dấu ngược trong URL thì máy chủ không hiểu."""
    goc = settings.video_out_path
    url = _muc_tieu(goc / "abc" / "video.mp4").video_url()
    assert "\\" not in url, f"URL còn dấu gạch ngược: {url}"
    assert "/media/videos/abc/video.mp4" in url


def test_khong_co_video_thi_url_rong():
    assert _muc_tieu(None).video_url() == ""


def test_file_ngoai_thu_muc_cong_khai_thi_url_rong():
    """
    Trả rỗng để bên gọi biết mà xử lý, thay vì dựng ra một URL trông đúng
    nhưng luôn 404.
    """
    assert _muc_tieu(Path("C:/o/khac/video.mp4")).video_url() == ""


def test_cac_publisher_dung_chung_mot_ham():
    """
    Dựng URL ở hai chỗ thì sớm muộn hai chỗ lệch nhau.

    Chỉ soi những dòng dựng URL. `video_path.name` vẫn hợp lệ ở chỗ khác —
    Facebook upload multipart cần một TÊN FILE, và ở đó "video.mp4" là
    đúng chứ không phải lỗi.
    """
    from agent.publish import meta, n8n
    for mod in (meta, n8n):
        src = inspect.getsource(mod)
        assert "video_url()" in src, f"{mod.__name__} chưa dùng hàm chung"
        for dong in src.splitlines():
            if "media/videos" in dong:
                assert "video_path.name" not in dong, (
                    f"{mod.__name__} còn dựng URL từ tên file: {dong.strip()}"
                )


def test_instagram_bao_loi_ro_khi_khong_dung_duoc_url():
    """Im lặng gửi URL rỗng cho Meta thì lỗi trả về là của Meta, khó lần."""
    from agent.publish.meta import MetaPublisher
    src = inspect.getsource(MetaPublisher._instagram)
    assert "nằm ngoài thư mục công khai" in src


# =====================================================================
#  Duyệt video
# =====================================================================

def test_khong_duyet_duoc_video_chua_co_file():
    """
    Trước đây endpoint đặt thẳng `ready` mà không kiểm gì. Kết quả: video
    "đã duyệt" với file_path NULL — dashboard hiện là xong, gắn vào bài
    đăng được, và nút tải trả 404. Hai bản ghi đã ở đúng tình trạng đó.
    """
    src = inspect.getsource(routes.approve_video)
    assert "Path(fp).exists()" in src
    assert "422" in src


def test_duyet_video_khong_co_thi_404():
    src = inspect.getsource(routes.approve_video)
    assert "404" in src
