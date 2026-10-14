"""
Vòng làm mới 6 giây không được kéo dữ liệu mà màn đang mở không dùng.

ĐO ĐƯỢC 22.09.2026 trên dashboard đang chạy (đếm bằng cách vá `fetch`):
đứng ở màn Nhân sự, mỗi nhịp làm mới vẫn phát

    GET /api/conversations?status=can_nguoi&limit=200
    GET /api/videos?limit=30

Hai khối chúng nuôi — `#queue` và `#videoqueue` — nằm TRONG màn Ca trực,
nên lúc ấy dữ liệu đổ vào DOM bị ẩn. Mỗi tab là 30 request/phút, hai phần
ba trong đó kéo tới 200 hội thoại và 30 video mà không ai nhìn. Nhân với
số người trực thì đó là tải thật trên máy chủ, đổi lấy không gì cả.

Đây không phải lỗi gây sai kết quả, nên không test chức năng nào bắt được —
và cũng vì thế nó sống lâu. Với một SaaS, chi phí mỗi tab mỗi phút là con
số phải giữ, không phải con số để mặc.

`/api/overview` thì CỐ Ý vẫn chạy mọi lúc: nó nuôi các con số trên thanh
điều hướng, và người trực cần thấy "Ca trực" nhảy số kể cả khi đang đứng ở
màn khác — đó chính là cách họ biết có việc mới.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
DONG = JS.splitlines()


def _than_ham(ten: str) -> str:
    bien = [
        (i, m.group(1))
        for i, l in enumerate(DONG)
        if (m := re.match(r"(?:async )?function ([A-Za-z0-9_]+)\(", l))
    ]
    for k, (i, t) in enumerate(bien):
        if t == ten:
            het = bien[k + 1][0] if k + 1 < len(bien) else len(DONG)
            return "\n".join(DONG[i:het])
    raise AssertionError(f"không tìm thấy {ten}()")


def _man_chua(oid: str) -> str:
    """Khối `id=oid` nằm trong màn nào."""
    i = HTML.find(f'id="{oid}"')
    assert i != -1, f"không còn #{oid}"
    j = HTML.rfind('<section class="view', 0, i)
    assert j != -1, f"#{oid} không nằm trong màn nào"
    return HTML[j: j + 120].split('data-view="')[1].split('"')[0]


def test_hai_khoi_nang_van_thuoc_man_ca_truc():
    """
    Neo của test dưới. Nếu `#queue` được chuyển sang màn khác thì chốt
    `state.view !== "ca"` thành sai, và test dưới phải được đọc lại chứ
    không phải sửa cho xanh.
    """
    assert _man_chua("queue") == "ca"
    assert _man_chua("videoqueue") == "ca"


def test_load_overview_dung_som_khi_khong_o_man_ca_truc():
    than = _than_ham("loadOverview")

    i_chot = than.find('state.view !== "ca"')
    assert i_chot != -1, (
        "loadOverview() không còn chốt `state.view !== \"ca\"` — nó sẽ lại "
        "kéo 200 hội thoại và 30 video mỗi 6 giây ở cả 16 màn còn lại"
    )

    for duong in ("/conversations?status=can_nguoi", "/videos?limit=30"):
        i = than.find(duong)
        assert i != -1, f"không còn gọi {duong} — đọc lại test này"
        assert i > i_chot, (
            f"`{duong}` đang gọi TRƯỚC chốt `state.view !== \"ca\"`, nên "
            "chốt không chặn được gì"
        )


def test_overview_van_chay_o_moi_man():
    """
    Chốt chiều ngược: đừng tối ưu quá tay. `/overview` nuôi các con số trên
    thanh điều hướng — cắt nó là người trực đứng ở màn khác không còn thấy
    "Ca trực" nhảy số, tức là mất đúng tín hiệu báo có việc mới.
    """
    than = _than_ham("loadOverview")
    i_overview = than.find('api("/overview")')
    i_chot = than.find('state.view !== "ca"')
    assert i_overview != -1, "loadOverview() không còn gọi /overview"
    assert i_overview < i_chot, (
        "`/overview` đang nằm SAU chốt, nên nó ngừng chạy ở 16 màn còn lại "
        "— các con số trên thanh điều hướng sẽ đứng im"
    )
