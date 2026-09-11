"""
Mọi đường dashboard gọi phải TỒN TẠI trên máy chủ.

VÌ SAO CẦN
----------
Gõ sai một đường trong `app.js` không làm gì đỏ cả. Máy chủ trả 404 — một
câu trả lời hoàn toàn hợp lệ, không phải lỗi — và người dùng chỉ thấy một
nút bấm vào không có gì xảy ra, kèm toast "Not Found" giữa giao diện tiếng
Việt.

Đổi tên một endpoint mà quên sửa màn hình cũng cho đúng kết quả ấy. Không
test nào ở hai phía bắt được: test API gọi đường mới và xanh, test màn hình
đọc DOM và cũng xanh.

CHỈ CANH MỘT CHIỀU
------------------
Chiều ngược lại — "endpoint nào không màn hình nào gọi" — KHÔNG làm chốt.
Nhiều endpoint có người gọi hợp lệ mà không phải dashboard: OAuth callback
do Meta/Zalo gọi, `/api/posts/{id}/callback` do n8n gọi, `/api/erp/*` do
công cụ của agent gọi. Biến nó thành chốt là tạo ra một test đỏ vì những lý
do không sai, và test đỏ vặt là test người ta tắt.

Chiều đó vẫn đáng quét TAY khi rà soát — nó vừa tìm ra ba tính năng có
endpoint mà không có màn hình ở mục Nhân sự, và hai ô báo động là ngõ cụt ở
trang Ca trực.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core.quyen import moi_route  # noqa: E402
from agent.main import app  # noqa: E402

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")

# Dấu cho "đoạn này do JS tính lúc chạy, không biết trước".
DONG = "<js>"


def _doc_doi_so(s: str, i: int) -> str:
    """Nguyên văn đối số đầu tiên của lời gọi bắt đầu ngay sau dấu `(`."""
    sau, dau = 0, i
    while i < len(s):
        c = s[i]
        if c in "([{":
            sau += 1
        elif c in ")]}":
            if sau == 0:
                break
            sau -= 1
        elif c == "," and sau == 0:
            break
        i += 1
    return s[dau:i]


def _thanh_duong(bieu_thuc: str) -> str | None:
    """
    Biểu thức JS -> đường dẫn, mọi phần động thành `DONG`.

    Phải đọc được CẢ BA cách dựng đường trong repo này. Bản quét đầu chỉ đọc
    chuỗi nguyên khối nên báo nhầm `api("/messages/" + id + "/approve")`
    thành một đường `/api/messages` không tồn tại — và một test báo đỏ nhầm
    là một test sẽ bị tắt.

        api("/x")                chuỗi nguyên
        api(`/x/${id}/y`)        nội suy
        api("/x/" + id + "/y")   nối chuỗi
    """
    b = re.sub(r"\$\{[^{}]*\}", DONG, bieu_thuc.strip())
    ra = []
    for phan in re.split(r"\s*\+\s*", b):
        phan = phan.strip()
        if len(phan) >= 2 and phan[0] in "\"'`" and phan[-1] == phan[0]:
            ra.append(phan[1:-1])
        else:
            ra.append(DONG)
    duong = "".join(ra)
    if not duong.startswith("/"):
        return None
    return duong.split("?")[0].split("#")[0]


def duong_dashboard_goi() -> set[str]:
    ra: set[str] = set()
    for m in re.finditer(r"\bapi\(", JS):
        d = _thanh_duong(_doc_doi_so(JS, m.end()))
        if d:
            ra.add("/api" + d)
    for m in re.finditer(r"\b(?:fetch|EventSource)\(", JS):
        d = _thanh_duong(_doc_doi_so(JS, m.end()))
        if d and d.startswith("/api"):
            ra.add(d)
    return {d.rstrip("/") or "/" for d in ra}


def duong_may_chu_co() -> list[list[str]]:
    """Đường máy chủ, tách sẵn thành đoạn."""
    ra = []
    for r in moi_route(app.routes):
        d = getattr(r, "path", "")
        if d:
            ra.append(d.strip("/").split("/"))
    return ra


def _khop_doan(js: str, may_chu: str) -> bool:
    """
    Một đoạn của JS khớp một đoạn của máy chủ.

    Ba cách khớp, và cách thứ ba là chỗ bản đầu sai:

        giống hệt nhau
        đoạn máy chủ là tham số `{id}`   -> nhận mọi thứ
        đoạn JS là ĐỘNG                  -> nhận mọi thứ, KỂ CẢ đoạn tĩnh

    Thiếu cách thứ ba thì `${taken ? "release" : "takeover"}` bị coi là
    đường không tồn tại, dù cả hai nhánh đều có thật.
    """
    if DONG in js:
        return True
    if may_chu.startswith("{") and may_chu.endswith("}"):
        return True
    return js == may_chu


def _co_tren_may_chu(js_doan: list[str], mau: list[list[str]]) -> bool:
    # `strict=True` dù đã so độ dài ngay trước đó: `zip()` cắt ngầm về danh
    # sách ngắn hơn là một trong những lỗi nghiêm trọng nhất repo này từng
    # có (xem CLAUDE.md). Để phép so độ dài là chốt duy nhất thì ngày ai đó
    # sửa điều kiện ấy, bộ so này im lặng khớp mọi thứ — và một bộ canh
    # khớp mọi thứ là một bộ canh luôn báo xanh.
    return any(
        len(js_doan) == len(mc)
        and all(_khop_doan(a, b) for a, b in zip(js_doan, mc, strict=True))
        for mc in mau
    )


def test_moi_duong_dashboard_goi_deu_ton_tai():
    mau = duong_may_chu_co()
    goi = duong_dashboard_goi()
    assert len(goi) > 80, (
        "Quét được quá ít đường — bộ đọc app.js hỏng, và một bộ đọc hỏng "
        "thì luôn báo xanh")

    hong = []
    for d in goi:
        doan = d.strip("/").split("/")
        # Đường TOÀN ĐỘNG là chính hàm `api()` (`fetch("/api" + path)`),
        # không phải một chỗ gọi. Không có gì để đối chiếu.
        if all(DONG in x for x in doan[1:]):
            continue
        ung_vien = [doan]
        # Đoạn cuối dạng `<chữ><động>` thường là nối query: `"/posts" + q`.
        # Thử cả cách hiểu không có phần động ấy.
        if DONG in doan[-1] and not doan[-1].startswith(DONG):
            ung_vien.append(doan[:-1] + [doan[-1].split(DONG)[0]])
        if not any(_co_tren_may_chu(u, mau) for u in ung_vien):
            hong.append(d.replace(DONG, "${...}"))

    assert not hong, (
        "Dashboard gọi những đường máy chủ KHÔNG CÓ. Người dùng bấm nút và "
        "không có gì xảy ra:\n  " + "\n  ".join(sorted(hong)))


def test_bo_doc_js_hieu_ca_ba_cach_dung_duong():
    """
    Canh chính bộ đọc ở trên.

    Nếu nó ngừng hiểu nối chuỗi, `test_moi_duong_dashboard_goi_deu_ton_tai`
    sẽ bỏ sót thay vì báo đỏ — xanh giả, đúng loại nguy hiểm hơn đỏ giả.
    """
    assert _thanh_duong('"/a/b"') == "/a/b"
    assert _thanh_duong("`/a/${id}/c`") == f"/a/{DONG}/c"
    assert _thanh_duong('"/a/" + id + "/c"') == f"/a/{DONG}/c"
    assert _thanh_duong('"/a" + q') == f"/a{DONG}"
    assert _thanh_duong("khongPhaiDuong") is None


def test_bo_so_nhan_doan_dong_khop_doan_tinh():
    """
    `${taken ? "release" : "takeover"}` là MỘT đoạn động khớp một đoạn TĨNH
    của máy chủ. Bản đầu của bộ so không nhận, và báo đỏ nhầm ba đường đang
    chạy tốt.
    """
    mau = [["api", "inbox", "conversations", "{id}", "release"]]
    assert _co_tren_may_chu(["api", "inbox", "conversations", DONG, DONG], mau)
    assert not _co_tren_may_chu(
        ["api", "inbox", "conversations", DONG, "xxx"], mau)
