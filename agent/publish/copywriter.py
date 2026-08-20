"""
Agent soạn nội dung bài đăng.

Ba ràng buộc làm nên khác biệt giữa cái này và một lời nhắc "viết caption
cho tôi":

1. CĂN CỨ. Tên, giá, dung tích, thành phần lấy từ catalog, không để model
   tự nghĩ. Bịa một thành phần trong tin nhắn 1-1 đã tệ; bịa nó trên
   fanpage là quảng cáo sai sự thật.
2. TUÂN THỦ. Kiểm bằng mã sau khi model trả lời, và thử lại một lần với
   phản hồi cụ thể. Prompt nhắc thôi thì không đủ — model vẫn trượt.
3. HỌC TỪ SỐ LIỆU. Chèn tóm tắt các bài chạy tốt vào prompt để lần sau
   viết theo hướng đã được chứng minh, thay vì viết lại từ đầu mỗi lần.

Mỗi nền tảng một giọng riêng: TikTok cần móc câu trong 3 giây đầu,
Facebook viết dài hơn được, Instagram sống bằng hashtag.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import ROOT
from ..core import llm
from . import analytics
from .service import kiem_tra_tuan_thu

_CATALOG = ROOT / "data" / "catalog.json"

_GIONG = {
    "facebook": (
        "Facebook: 3-5 câu. Mở bằng một tình huống khách hay gặp, không mở "
        "bằng tên sản phẩm. Được xuống dòng. 3-5 hashtag ở cuối."
    ),
    "instagram": (
        "Instagram: 2-3 câu ngắn, gợi cảm giác hơn là mô tả tính năng. "
        "8-12 hashtag, trộn hashtag rộng và hashtag ngách."
    ),
    "tiktok": (
        "TikTok: tối đa 2 câu, câu đầu phải là móc câu giữ người xem trong "
        "3 giây. Viết như đang nói. 3-5 hashtag."
    ),
    "youtube": (
        "YouTube Shorts: một câu tiêu đề dưới 60 ký tự và 2 câu mô tả. "
        "3-5 hashtag."
    ),
}

_HE_THONG = """Bạn viết nội dung mạng xã hội cho Aurora Skin — thương hiệu mỹ phẩm chăm sóc da tại Việt Nam.

# Giới hạn pháp lý — quan trọng hơn mọi thứ khác
Mỹ phẩm KHÔNG PHẢI thuốc. Theo Thông tư 06/2011/TT-BYT và Nghị định
181/2013, tuyệt đối không được viết: trị mụn, đặc trị, chữa, trị nám,
xoá nhăn, hết mụn, tái tạo da, trắng da cấp tốc, thay thế thuốc, cam kết
khỏi, hiệu quả 100%, số 1 Việt Nam, tốt nhất thị trường.

Được viết: hỗ trợ giảm dầu, giúp da mềm mại hơn, hỗ trợ làm đều màu da,
cấp ẩm, làm dịu da, hỗ trợ cải thiện kết cấu da.

Không hứa kết quả theo mốc thời gian. Không so sánh với thương hiệu khác.

# Căn cứ
Chỉ dùng tên, giá, dung tích, thành phần có trong dữ liệu sản phẩm được
cung cấp. Không bịa thêm thành phần, công dụng hay con số nào.

# Giọng văn
Viết như người Việt bán mỹ phẩm thật, không như bộ phận marketing. Câu
ngắn. Không sáo rỗng. Không dùng "Bạn có biết rằng".

Trả về DUY NHẤT một khối JSON:
{"tieu_de": "...", "noi_dung": "...", "hashtags": ["#..."]}"""


def _tim_san_pham(ma_hoac_ten: str) -> dict | None:
    data = json.loads(_CATALOG.read_text(encoding="utf-8"))
    sp = data.get("san_pham", data if isinstance(data, list) else [])
    key = ma_hoac_ten.lower().strip()
    for p in sp:
        if str(p.get("ma", "")).lower() == key:
            return p
    for p in sp:
        if key in str(p.get("ten", "")).lower():
            return p
    return None


def _mo_ta_san_pham(p: dict) -> str:
    return json.dumps({
        k: p.get(k) for k in
        ("ma", "ten", "loai", "gia", "dung_tich", "da_phu_hop",
         "van_de_ho_tro", "thanh_phan_chinh", "khong_chua", "cach_dung")
        if p.get(k)
    }, ensure_ascii=False, indent=1)


async def soan(
    *, kenh: str, san_pham: str = "", y_tuong: str = "",
    video_id: str | None = None,
) -> dict:
    """Trả {tieu_de, noi_dung, hashtags, vi_pham, so_lan_thu, chi_phi}."""
    kenh = kenh if kenh in _GIONG else "facebook"

    phan_can_cu = ""
    if san_pham:
        p = _tim_san_pham(san_pham)
        if p is None:
            raise LookupError(f"Không có sản phẩm nào khớp {san_pham!r} trong catalog")
        phan_can_cu = f"\n# Dữ liệu sản phẩm (nguồn duy nhất)\n{_mo_ta_san_pham(p)}\n"

    goi_y = await analytics.goi_y_cho_agent()
    phan_hoc = f"\n# Số liệu thực tế\n{goi_y}\n" if goi_y else ""

    yeu_cau = (
        f"{_GIONG[kenh]}\n{phan_can_cu}{phan_hoc}\n"
        f"Ý tưởng nội dung: {y_tuong or 'giới thiệu sản phẩm cho khách mới'}"
    )

    tong_chi_phi = 0.0
    lich_su = [{"role": "user", "content": yeu_cau}]
    ly_do_cuoi = "model không trả về JSON đọc được"

    for lan in range(1, 4):     # thử tối đa 3 lần
        # 4096 chứ không phải 1024: Gemini 2.5 tiêu ngân sách token vào phần
        # suy nghĩ nội bộ TRƯỚC khi viết. Đặt trần thấp thì thỉnh thoảng nó
        # nghĩ hết hạn mức và trả về rỗng — hỏng ngẫu nhiên, rất khó lần ra.
        r = await llm.complete(
            system=llm.cached_system(_HE_THONG),
            messages=lich_su, max_tokens=4096,
        )
        tong_chi_phi += r.cost_usd
        data = llm.parse_json(r.text)
        if not data or not data.get("noi_dung"):
            ly_do_cuoi = (
                f"model trả về không phải JSON dùng được: {r.text[:150]!r}"
                if r.text.strip() else "model trả về rỗng"
            )
            lich_su += [
                {"role": "assistant", "content": r.text},
                {"role": "user", "content": "Trả lại đúng một khối JSON như đã yêu cầu."},
            ]
            continue

        tags = [t if t.startswith("#") else f"#{t}"
                for t in (data.get("hashtags") or [])]
        vi_pham = kiem_tra_tuan_thu(
            f"{data.get('tieu_de','')} {data['noi_dung']} {' '.join(tags)}"
        )
        ly_do_cuoi = f"còn cụm vi phạm quảng cáo mỹ phẩm: {vi_pham}"
        if not vi_pham:
            return {
                "tieu_de": (data.get("tieu_de") or "").strip()[:200],
                "noi_dung": data["noi_dung"].strip(),
                "hashtags": tags, "kenh": kenh, "video_id": video_id,
                "vi_pham": [], "so_lan_thu": lan,
                "chi_phi_usd": round(tong_chi_phi, 6),
            }

        # Nói rõ sai ở đâu — phản hồi chung chung thì model sửa mò.
        lich_su += [
            {"role": "assistant", "content": r.text},
            {"role": "user", "content":
                f"Bản này vi phạm quảng cáo mỹ phẩm ở các cụm: {vi_pham}. "
                f"Viết lại, bỏ hẳn các cụm đó, thay bằng cách nói 'hỗ trợ'. "
                f"Trả lại đúng khối JSON."},
        ]

    # Nói đúng chuyện gì hỏng. Gộp "model trả JSON hỏng" vào "vi phạm quảng
    # cáo" thì người vận hành đi sửa nhầm chỗ.
    raise ValueError(f"Soạn 3 lần không ra bài dùng được — {ly_do_cuoi}.")
