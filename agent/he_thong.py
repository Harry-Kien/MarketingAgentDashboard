"""
Cổng vào duy nhất — mọi hệ thống con nhìn từ một chỗ.

PROXY: TỪNG KẾT LUẬN LÀ KHÔNG LÀM ĐƯỢC, NAY LÀM ĐƯỢC
----------------------------------------------------
Bản đầu của file này viết rằng proxy "đã kiểm và KHÔNG làm được một cách
vững", vì các app dùng đường dẫn TUYỆT ĐỐI:

    ZaloCRM  ->  href="/brand/zalocrm.ico"
    n8n      ->  src="/static/base-path.js"

Kết luận ấy đúng với cách làm hồi đó: viết lại HTML/CSS/JS đang bay qua để
thêm tiền tố. Cách đó thật sự vỡ sau mỗi lần thượng nguồn nâng cấp.

`agent/api/tich_hop.py` giải bằng đường khác: không viết lại gì cả, mà bám
`Referer` để biết một request vào đường tuyệt đối thuộc về app nào. Thượng
nguồn đổi đường dẫn thì vẫn chạy, vì lớp proxy không hề biết đường dẫn nào
là hợp lệ.

Nên nay có HAI cách mở, và mỗi dịch vụ khai rõ mình theo cách nào qua
`nhung_duoc`: mở ngay trong dashboard, hoặc mở tab mới. Dịch vụ nào chưa
kiểm được thì để `False` — mặc định thận trọng, vì một iframe trắng khó
lần ra hơn một tab mới.

VÌ SAO KHÔNG GỘP MÃ NGUỒN
-------------------------
ZaloCRM là AGPL-3.0: chép mã vào đây là cả dự án thành tác phẩm phái sinh
và phải mang cùng giấy phép, mất quyền đóng gói thương mại. Chatwoot là MIT
nên không vướng luật, nhưng gộp một ứng dụng Rails vào đây nghĩa là fork và
tự bảo trì nó, mất đường nhận bản vá bảo mật từ thượng nguồn.

CÁCH LÀM
--------
Một địa chỉ để NHỚ, không phải một tiến trình để chạy. Trang này hỏi thật
từng dịch vụ, cho biết cái nào sống, và mở được bằng một cú bấm.
"""
from __future__ import annotations

import asyncio

import httpx

from agent.config import settings


# `can_dang_nhap`: mở ra là gặp màn hình đăng nhập của chính nó, không phải
# lỗi. Ghi rõ để người vận hành không tưởng là hỏng.
DICH_VU = [
    {
        "ma": "dashboard",
        "ten": "Trạm điều độ",
        "mo_ta": "Hội thoại, đơn hàng, video, bài đăng, sức khoẻ hệ thống",
        "url": "http://localhost:8000",
        "kiem": "http://127.0.0.1:8000/healthz",
        "chinh": True,
        "can_dang_nhap": True,
    },
    {
        "ma": "zalocrm",
        "ten": "ZaloCRM",
        "mo_ta": "Quét QR thêm nick Zalo, xem danh bạ và lịch hẹn",
        "url": "http://localhost:3080",
        "kiem": "http://localhost:3080/",
        "can_dang_nhap": True,
        "nhung_duoc": True,
    },
    {
        "ma": "chatwoot",
        "ten": "Chatwoot",
        "mo_ta": "Nối Facebook, Instagram, WhatsApp, chat web, email",
        "url": "http://localhost:3200",
        "kiem": "http://localhost:3200/",
        "can_dang_nhap": True,
        "nhung_duoc": True,
    },
    {
        "ma": "n8n",
        "ten": "n8n",
        "mo_ta": "Định tuyến đăng bài và cảnh báo ra ngoài",
        "url": "http://localhost:5678",
        "kiem": "http://localhost:5678/",
        "can_dang_nhap": True,
        "nhung_duoc": True,
    },
    {
        "ma": "minio",
        "ten": "MinIO",
        "mo_ta": "Kho file đính kèm của ZaloCRM",
        "url": "http://localhost:9001",
        "kiem": "http://localhost:9000/minio/health/live",
        "can_dang_nhap": True,
        "nhung_duoc": True,
    },
]


def muc_erp() -> dict:
    """Mục Kho/ERP, dựng theo cấu hình thay vì gõ cứng.

    VÌ SAO KHÔNG NẰM THẲNG TRONG `DICH_VU`
    --------------------------------------
    Bốn dịch vụ kia chạy trên localhost với cổng cố định. ERP thì ở MÁY
    KHÁC, địa chỉ khác nhau ở từng cửa hàng — gõ cứng một URL là bảo đảm nó
    sai với mọi người trừ người viết ra nó.

    VÌ SAO KHÔNG `nhung_duoc`
    -------------------------
    Odoo và ERPNext đều gửi `X-Frame-Options`. Bật nhúng thì người dùng bấm
    "Mở" và nhận một khung trắng — hỏng câm, không lỗi nào được ném.
    """
    loai = (settings.erp_loai or "tep").strip().lower()
    goc = {
        "erpnext": settings.erpnext_url,
        "odoo": settings.odoo_url,
    }.get(loai, "")

    if loai == "tep" or not goc:
        return {
            "ma": "erp",
            "ten": "Kho / ERP",
            "mo_ta": ("CHƯA nối ERP — agent đang đọc giá và tồn kho từ tệp "
                      "data/catalog.json trên đĩa"),
            # Chưa có ERP để mở. Bản đầu trỏ `url` về chính dashboard với lý
            # do "liên kết gãy còn tệ hơn không có liên kết" — nhưng bấm vào
            # thì trang quay về trang chính, không lời giải thích, nhìn như
            # nút hỏng. Đó là lựa chọn TỆ NHẤT trong ba.
            #
            # Lựa chọn đúng: đưa người dùng sang màn Kho, nơi có panel Kết
            # nối kho/ERP và nút Thử kết nối. Nút chỉ có nghĩa khi bấm xong
            # người dùng ở GẦN VIỆC hơn trước.
            "di_toi_man": "kho",
            "url": "",
            "kiem": "http://127.0.0.1:8000/healthz",
            "can_dang_nhap": False,
        }

    goc = goc.rstrip("/")
    return {
        "ma": "erp",
        "ten": "Kho / ERP",
        "mo_ta": f"Giá và tồn kho thật — nguồn {loai}",
        "url": goc,
        "kiem": goc,
        "can_dang_nhap": True,
    }


async def _song(url: str) -> tuple[bool, str]:
    """
    Dịch vụ có trả lời không.

    Coi MỌI mã HTTP đều là sống, kể cả 401 và 403: dịch vụ đòi đăng nhập
    tức là nó đang chạy. Chỉ khi không nối được mới là chết.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as c:
            r = await c.get(url)
        return True, f"HTTP {r.status_code}"
    except httpx.HTTPError as exc:
        return False, type(exc).__name__


async def kiem_tat_ca() -> dict:
    """Trạng thái mọi hệ thống con, hỏi song song."""
    # `muc_erp()` dựng theo cấu hình nên phải gọi mỗi lần, không cache vào
    # DICH_VU — đổi ERP_LOAI mà bảng vẫn hiện cái cũ là nói dối người xem.
    dich_vu = [*DICH_VU, muc_erp()]
    ket = await asyncio.gather(*(_song(d["kiem"]) for d in dich_vu))

    ra = []
    for d, (song, ghi_chu) in zip(dich_vu, ket, strict=True):
        ra.append({**{k: v for k, v in d.items() if k != "kiem"},
                   "song": song, "ghi_chu": ghi_chu})

    return {
        "dich_vu": ra,
        "dang_chay": sum(1 for x in ra if x["song"]),
        "tong": len(ra),
        # Nhắc lại ngay trong dữ liệu, để người đọc API cũng thấy: mỗi thứ
        # chạy riêng là CHỦ Ý, không phải chưa làm xong.
        "vi_sao_tach": (
            "Mỗi dịch vụ chạy tiến trình riêng có chủ ý: ZaloCRM mang giấy "
            "phép AGPL nên phải cô lập, còn Chatwoot là ứng dụng Rails cần "
            "nhận bản vá từ thượng nguồn. Trang này là một cổng vào duy nhất "
            "để nhớ, không phải một tiến trình duy nhất để chạy."
        ),
    }
