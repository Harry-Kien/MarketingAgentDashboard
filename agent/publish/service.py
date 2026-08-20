"""
Nghiệp vụ bài đăng: soạn -> duyệt -> phân phối -> đo hiệu quả.

QUY TẮC AN TOÀN QUAN TRỌNG NHẤT
-------------------------------
Agent được soạn bài nhưng KHÔNG được tự đăng. Một câu quảng cáo mỹ phẩm
sai luật đăng lên fanpage thật thì không gỡ lại được ấn tượng, và theo
Nghị định 181/2013 thì doanh nghiệp chịu trách nhiệm chứ không phải công
cụ. Nên mọi bài dừng ở `cho_duyet` cho tới khi có người bấm duyệt.

Cờ `tu_dong_dang_khong_can_duyet` tồn tại để chứng minh hệ thống làm được
luồng tự động đầy đủ, nhưng mặc định TẮT và không nên bật trên trang thật.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import db
from ..config import settings
from . import registry
from .base import PublishTarget

# Cùng danh sách cấm với prompt tư vấn — nhưng kiểm ở ĐÂY, trong mã, vì
# caption đi ra công chúng thì không có cơ hội sửa như tin nhắn 1-1.
_TU_CAM = (
    "trị mụn", "tri mun", "đặc trị", "dac tri", "chữa", "chua khoi",
    "trị nám", "tri nam", "xoá nhăn", "xoa nhan", "xóa nhăn",
    "hết mụn", "het mun", "tái tạo da", "tai tao da", "trắng da cấp tốc",
    "thay thế thuốc", "cam kết khỏi", "hiệu quả 100", "khỏi hẳn",
    "số 1 việt nam", "tốt nhất thị trường",
)


def kiem_tra_tuan_thu(noi_dung: str) -> list[str]:
    """Trả về danh sách cụm từ vi phạm quảng cáo mỹ phẩm, rỗng là sạch."""
    low = noi_dung.lower()
    return [t for t in _TU_CAM if t in low]


def _tach_hashtag(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"#[\wÀ-ỹ]+", text)))


async def tao_bai(
    *, tieu_de: str, noi_dung: str, kenh: list[str],
    hashtags: list[str] | None = None, video_id: str | None = None,
    lich_dang=None, tao_boi: str = "agent",
) -> dict:
    kenh = [k for k in kenh if k in registry.KENH_HO_TRO]
    if not kenh:
        raise ValueError(f"Kênh không hợp lệ. Chỉ nhận: {registry.KENH_HO_TRO}")

    tags = hashtags if hashtags is not None else _tach_hashtag(noi_dung)
    vi_pham = kiem_tra_tuan_thu(f"{tieu_de} {noi_dung} {' '.join(tags)}")

    row = await db.fetchrow(
        "INSERT INTO posts (video_id, tieu_de, noi_dung, hashtags, kenh, "
        "                   trang_thai, lich_dang, tao_boi) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING *",
        video_id, tieu_de, noi_dung, tags, kenh,
        "cho_duyet", lich_dang, tao_boi,
    )
    await db.log_event(
        "post.created", actor=tao_boi, ref_id=row["id"],
        kenh=kenh, vi_pham=vi_pham,
    )
    return {**row, "vi_pham_quang_cao": vi_pham}


async def _duong_dan_video(video_id) -> Path | None:
    if not video_id:
        return None
    v = await db.fetchrow("SELECT file_path FROM videos WHERE id = $1", video_id)
    if not v or not v.get("file_path"):
        return None
    p = Path(v["file_path"])
    return p if p.exists() else None


async def dang_bai(post_id: str, *, boi: str = "nguoi") -> dict:
    """
    Phân phối một bài đã duyệt. Mỗi kênh đi riêng, một kênh hỏng không
    kéo theo kênh khác — ket_qua ghi từng kênh một.
    """
    post = await db.fetchrow("SELECT * FROM posts WHERE id = $1", post_id)
    if not post:
        raise LookupError("Không tìm thấy bài đăng")
    if post["trang_thai"] in ("da_dang", "dang_dang"):
        return post

    vi_pham = kiem_tra_tuan_thu(f"{post['tieu_de']} {post['noi_dung']}")
    if vi_pham:
        await db.execute(
            "UPDATE posts SET trang_thai='loi', ket_qua=$2, updated_at=now() "
            "WHERE id=$1",
            post_id, {"chan": f"Nội dung vi phạm quảng cáo mỹ phẩm: {vi_pham}"},
        )
        await db.log_event("post.blocked", actor="compliance",
                           ref_id=post_id, vi_pham=vi_pham)
        raise ValueError(f"Nội dung vi phạm quảng cáo mỹ phẩm: {vi_pham}")

    await db.execute(
        "UPDATE posts SET trang_thai='dang_dang', updated_at=now() WHERE id=$1",
        post_id,
    )
    video = await _duong_dan_video(post["video_id"])

    ket_qua: dict[str, dict] = dict(post.get("ket_qua") or {})
    for kenh in post["kenh"]:
        adapter = await registry.chon(kenh)
        res = await adapter.publish(PublishTarget(
            post_id=str(post_id), kenh=kenh,
            tieu_de=post["tieu_de"], noi_dung=post["noi_dung"],
            hashtags=list(post["hashtags"] or []), video_path=video,
        ))
        ket_qua[kenh] = {
            "ok": res.ok, "url": res.url, "detail": res.detail,
            "adapter": adapter.name, "cho_xu_ly": res.da_nhan_chua_dang,
        }

    xong = [v for v in ket_qua.values() if v["ok"]]
    cho = [v for v in ket_qua.values() if v["ok"] and v["cho_xu_ly"]]
    if not xong:
        trang_thai = "loi"
    elif cho:
        trang_thai = "dang_dang"      # chờ callback báo về
    else:
        trang_thai = "da_dang"

    row = await db.fetchrow(
        "UPDATE posts SET trang_thai=$2, ket_qua=$3, updated_at=now() "
        "WHERE id=$1 RETURNING *",
        post_id, trang_thai, ket_qua,
    )
    await db.log_event("post.published", actor=boi, ref_id=post_id,
                       trang_thai=trang_thai, ket_qua=ket_qua)
    return row


async def duyet(post_id: str, *, boi: str = "nguoi") -> dict:
    post = await db.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
    if not post:
        raise LookupError("Không tìm thấy bài đăng")
    # Có lịch hẹn ở tương lai thì xếp lịch, tới giờ scheduler mới đăng.
    if post["lich_dang"]:
        from datetime import datetime, timezone
        hen = post["lich_dang"]
        # Client gửi giờ không kèm múi thì coi là UTC. So sánh một datetime
        # có múi với một cái không có sẽ ném TypeError giữa lúc duyệt bài.
        if hen.tzinfo is None:
            hen = hen.replace(tzinfo=timezone.utc)
        if hen > datetime.now(timezone.utc):
            row = await db.fetchrow(
                "UPDATE posts SET trang_thai='da_len_lich', updated_at=now() "
                "WHERE id=$1 RETURNING *", post_id,
            )
            await db.log_event("post.scheduled", actor=boi, ref_id=post_id)
            return row
    return await dang_bai(post_id, boi=boi)


async def ghi_nhan_callback(post_id: str, kenh: str, ok: bool,
                            url: str = "", detail: str = "") -> dict | None:
    """n8n / nền tảng gọi về báo kết quả thật sau khi xử lý nền."""
    post = await db.fetchrow("SELECT * FROM posts WHERE id=$1", post_id)
    if not post:
        return None
    ket_qua = dict(post.get("ket_qua") or {})
    ket_qua[kenh] = {**ket_qua.get(kenh, {}), "ok": ok, "url": url,
                     "detail": detail, "cho_xu_ly": False}
    con_cho = any(v.get("cho_xu_ly") for v in ket_qua.values())
    co_ok = any(v.get("ok") for v in ket_qua.values())
    trang_thai = "dang_dang" if con_cho else ("da_dang" if co_ok else "loi")
    row = await db.fetchrow(
        "UPDATE posts SET trang_thai=$2, ket_qua=$3, updated_at=now() "
        "WHERE id=$1 RETURNING *", post_id, trang_thai, ket_qua,
    )
    if ok and url:
        await db.execute(
            "INSERT INTO post_metrics (post_id, kenh, url) VALUES ($1,$2,$3)",
            post_id, kenh, url,
        )
    await db.log_event("post.callback", actor=kenh, ref_id=post_id, ok=ok)
    return row


async def den_gio_dang() -> list[dict]:
    """Bài đã duyệt và đã tới giờ hẹn. Scheduler trong main.py gọi hàm này."""
    return await db.fetch(
        "SELECT id FROM posts WHERE trang_thai='da_len_lich' "
        "AND lich_dang <= now() ORDER BY lich_dang LIMIT 5"
    )
