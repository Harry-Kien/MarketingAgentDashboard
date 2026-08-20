"""
Chiến dịch — một ý tưởng, nhiều nền tảng, mỗi nơi một giọng riêng.

VÌ SAO KHÔNG CHỈ COPY-PASTE MỘT BÀI RA BỐN CHỖ
----------------------------------------------
Đó là cách làm marketing đa nền tảng phổ biến nhất, và cũng là cách kém
hiệu quả nhất. Bốn nền tảng có bốn hành vi người dùng khác hẳn nhau:

  TikTok     3 giây đầu quyết định. Không có móc câu là lướt qua.
  Facebook   người đọc chịu khó hơn, kể được một tình huống.
  Instagram  sống bằng hashtag và cảm giác, không phải bằng mô tả tính năng.
  YouTube    tiêu đề dưới 60 ký tự vì bị cắt trong danh sách gợi ý.

Cùng một caption đăng cả bốn chỗ thì ít nhất ba chỗ sai định dạng. Nên lớp
này gọi `copywriter.soan()` RIÊNG cho từng kênh — cùng một ý tưởng, cùng
một dữ liệu sản phẩm, nhưng bốn bản viết khác nhau.

Chi phí: khoảng $0.0006/bài, tức một chiến dịch 4 kênh tốn chưa tới 60đ.
Rẻ hơn nhiều so với việc đăng sai định dạng ba nơi.

GIÃN GIỜ ĐĂNG
-------------
Đăng cả bốn nền tảng cùng một phút là dấu hiệu tự động rõ nhất, và nó cũng
tự cạnh tranh với chính mình trên bảng tin. Mặc định giãn 30 phút một bài.

MỌI BÀI VẪN DỪNG Ở CHỜ DUYỆT — chiến dịch không phải đường vòng qua khâu
duyệt. Nó chỉ soạn nhanh hơn, không quyết định thay người.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from .. import db
from . import copywriter
from . import service as post_service
from .registry import KENH_HO_TRO


async def _soan_mot(kenh: str, san_pham: str, y_tuong: str, video_id: str | None) -> dict:
    """Soạn cho một kênh. Hỏng một kênh không được kéo đổ cả chiến dịch."""
    try:
        return await copywriter.soan(
            kenh=kenh, san_pham=san_pham, y_tuong=y_tuong, video_id=video_id
        )
    except Exception as exc:  # noqa: BLE001
        return {"kenh": kenh, "loi": f"{type(exc).__name__}: {exc}"[:200]}


async def tao(
    *,
    ten: str,
    kenh: list[str],
    san_pham: str = "",
    y_tuong: str = "",
    video_id: str | None = None,
    bat_dau: datetime | None = None,
    gian_cach_phut: int = 30,
) -> dict:
    """
    Soạn một bài cho mỗi kênh và đưa tất cả vào hàng đợi chờ duyệt.

    Trả về danh sách bài đã tạo và danh sách kênh soạn hỏng — nói rõ cả
    hai, không im lặng bỏ qua kênh nào.
    """
    kenh = [k for k in dict.fromkeys(kenh) if k in KENH_HO_TRO]
    if not kenh:
        raise ValueError(f"Không có kênh hợp lệ. Chỉ nhận: {KENH_HO_TRO}")

    # Bốn kênh soạn song song — chúng độc lập, không việc gì phải chờ nhau.
    ban_nhap = await asyncio.gather(
        *(_soan_mot(k, san_pham, y_tuong, video_id) for k in kenh)
    )

    # Có giãn cách mà không có mốc bắt đầu thì ô "giãn cách" im lặng không
    # làm gì — người dùng điền 30 phút rồi thấy cả bốn bài đăng cùng lúc.
    # Mặc định lấy thời điểm hiện tại: bài đầu đi ngay khi duyệt, các bài
    # sau xếp lịch đúng khoảng cách.
    moc = bat_dau
    if moc is None and gian_cach_phut > 0 and len(kenh) > 1:
        moc = datetime.now(timezone.utc)
    if moc is not None and moc.tzinfo is None:
        moc = moc.replace(tzinfo=timezone.utc)

    bai, hong = [], []
    chi_phi = 0.0
    for i, nhap in enumerate(ban_nhap):
        if nhap.get("loi"):
            hong.append({"kenh": nhap["kenh"], "ly_do": nhap["loi"]})
            continue
        chi_phi += nhap.get("chi_phi_usd", 0.0)
        lich = moc + timedelta(minutes=gian_cach_phut * i) if moc else None
        row = await post_service.tao_bai(
            tieu_de=nhap["tieu_de"],
            noi_dung=nhap["noi_dung"],
            hashtags=nhap["hashtags"],
            kenh=[nhap["kenh"]],
            video_id=video_id,
            lich_dang=lich,
            tao_boi="chien_dich",
        )
        row["id"] = str(row["id"])
        for k in ("lich_dang", "created_at", "updated_at"):
            if row.get(k):
                row[k] = row[k].isoformat()
        row["so_lan_thu"] = nhap.get("so_lan_thu", 1)
        bai.append(row)

    await db.log_event(
        "campaign.created", actor="nguoi",
        ten=ten, kenh=kenh, so_bai=len(bai), hong=[h["kenh"] for h in hong],
        chi_phi_usd=round(chi_phi, 6),
    )
    return {
        "ten": ten,
        "so_bai": len(bai),
        "bai": bai,
        "kenh_hong": hong,
        "chi_phi_usd": round(chi_phi, 6),
        "ghi_chu": (
            f"{len(bai)} bài đang chờ duyệt. Vào mục Đăng bài để xem và duyệt "
            f"từng bài — chiến dịch không tự đăng."
        ),
    }
