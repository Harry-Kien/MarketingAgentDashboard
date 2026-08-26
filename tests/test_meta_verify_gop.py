"""
Meta xác minh webhook bằng GET — đường gộp phải trả lời được.

LỖI SẼ XẢY RA NẾU THIẾU
-----------------------
Meta chỉ cho khai MỘT URL webhook cho mỗi ứng dụng. Nhiều Trang trên cùng
một app đều đi qua URL đó, và hệ thống tự phân về đúng tài khoản dựa vào
định danh trong payload — đó là việc của `POST /webhook/native/meta`.

Nhưng lúc bấm "Xác minh và lưu", Meta gửi một **GET** kèm `hub.mode`,
`hub.verify_token`, `hub.challenge`. Không có route GET cho đường gộp thì
Meta nhận 405 và từ chối lưu — người dùng kẹt ngay tại màn hình cấu hình,
với thông báo lỗi không nói gì về nguyên nhân thật.

Đường `/meta/{account_id}` đã có GET, nhưng nó đòi biết account_id — mà
lúc khai webhook trong Meta thì URL phải là một, dùng chung cho mọi Trang.
"""
from __future__ import annotations

import pytest


def test_duong_gop_co_ca_GET_lan_POST():
    from agent.api.native_webhooks import router

    theo_duong: dict[str, set[str]] = {}
    for r in router.routes:
        duong = getattr(r, "path", "")
        theo_duong.setdefault(duong, set()).update(getattr(r, "methods", set()))

    assert "/webhook/native/meta" in theo_duong, "thiếu đường gộp"
    cach = theo_duong["/webhook/native/meta"]
    assert "POST" in cach, "thiếu POST để nhận tin"
    assert "GET" in cach, "thiếu GET — Meta không xác minh được webhook"


@pytest.mark.parametrize("thieu", ["hub.mode", "hub.verify_token", "hub.challenge"])
def test_thieu_tham_so_thi_tu_choi(thieu):
    """Yêu cầu không đủ tham số không được coi là xác minh hợp lệ."""
    from agent.api.native_webhooks import doc_thach_thuc

    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "dung-token",
        "hub.challenge": "12345",
    }
    params.pop(thieu)
    assert doc_thach_thuc(params, {"dung-token"}) is None


def test_verify_token_sai_thi_tu_choi():
    from agent.api.native_webhooks import doc_thach_thuc

    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "token-tu-dau-ra",
        "hub.challenge": "12345",
    }
    assert doc_thach_thuc(params, {"dung-token"}) is None


def test_verify_token_dung_thi_doi_lai_challenge():
    from agent.api.native_webhooks import doc_thach_thuc

    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "dung-token",
        "hub.challenge": "12345",
    }
    assert doc_thach_thuc(params, {"dung-token", "token-khac"}) == "12345"


def test_khong_co_token_nao_duoc_cau_hinh_thi_tu_choi():
    """
    Tập token rỗng KHÔNG được coi là 'chấp nhận tất cả'.

    Đó là fail-open: chưa nối tài khoản nào mà ai gõ đúng URL cũng xác minh
    được webhook, rồi Meta bắt đầu đẩy tin vào một hệ thống chưa sẵn sàng.
    """
    from agent.api.native_webhooks import doc_thach_thuc

    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "bat_ky",
        "hub.challenge": "1",
    }
    assert doc_thach_thuc(params, set()) is None
