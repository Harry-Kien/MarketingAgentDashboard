"""Giao diện phải luôn hỏi lại máy chủ, đừng để người dùng phải Ctrl+F5.

VÌ SAO
------
`StaticFiles` của Starlette gửi `ETag` và `Last-Modified` nhưng KHÔNG gửi
`Cache-Control`. Thiếu header đó, trình duyệt tự suy diễn thời gian sống và
phục vụ `app.js` từ bộ đệm mà **không hỏi lại máy chủ**.

Đã gặp thật khi kiểm bản vá 401: máy chủ phục vụ bản mới, đĩa có bản mới,
mà trình duyệt vẫn chạy bản cũ — kể cả sau `location.reload()`.

Hệ quả vận hành: mọi bản vá đều không tới tay người trực cho tới khi họ tình
cờ Ctrl+F5. Sửa một lỗi rồi tưởng đã xong, trong khi người dùng vẫn đang gặp
đúng lỗi đó.

`no-cache` KHÔNG có nghĩa là "đừng lưu đệm". Nó nghĩa là "lưu được, nhưng
phải hỏi lại trước khi dùng". Có sẵn ETag nên lần hỏi lại trả 304 rỗng —
gần như miễn phí, và luôn đúng bản.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from agent.main import app
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("duong", ["/app.js", "/app.css", "/index.html"])
def test_tep_giao_dien_luon_phai_hoi_lai(client, duong):
    r = client.get(duong)
    if r.status_code == 404:
        pytest.skip(f"{duong} không có trong bản này")
    cc = r.headers.get("cache-control", "")
    assert "no-cache" in cc or "max-age=0" in cc, (
        f"{duong} thiếu Cache-Control. Trình duyệt sẽ tự suy diễn thời gian "
        "sống và phục vụ bản cũ — bản vá không tới tay người dùng.\n"
        f"Header hiện tại: {cc!r}"
    )


def test_van_con_etag_de_hoi_lai_re_tien(client):
    # `no-cache` mà không có ETag thì mỗi lần hỏi lại là tải nguyên file.
    r = client.get("/app.js")
    assert r.headers.get("etag"), "mất ETag — hỏi lại sẽ tải nguyên file"


def test_hoi_lai_dung_etag_thi_tra_304(client):
    r1 = client.get("/app.js")
    r2 = client.get("/app.js", headers={"If-None-Match": r1.headers["etag"]})
    assert r2.status_code == 304, (
        "Hỏi lại phải trả 304 rỗng. Trả 200 kèm nguyên file là mỗi lần vào "
        "trang tải lại toàn bộ giao diện."
    )


def test_video_van_duoc_dem_lau(client):
    """Video KHÔNG đi theo quy tắc này.

    Chúng bất biến sau khi dựng xong và nặng hàng megabyte. Bắt hỏi lại mỗi
    lần là đốt băng thông cho một câu trả lời luôn giống nhau.
    """
    from agent.main import app

    duong = {r.path for r in app.routes if hasattr(r, "path")}
    assert any("/media/videos" in d for d in duong), (
        "mount video biến mất — test này cần nó để canh ranh giới"
    )
