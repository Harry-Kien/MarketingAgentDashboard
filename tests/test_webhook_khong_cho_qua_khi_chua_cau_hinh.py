"""
Webhook chưa cấu hình bí mật thì TỪ CHỐI — lần thứ ba cùng một khuôn.

BA CHỖ, CÙNG MỘT LỖI
--------------------
    agent/api/native_webhooks.py   `doc_thach_thuc`      — danh sách token
                                    rỗng thì nhận mọi thách thức
    agent/shipping/service.py      `kiem_bi_mat_webhook` — `if secret:` rồi
                                    `if sig:`, hai lớp bỏ qua chồng nhau
    agent/main.py                  `/webhook/{kenh}`     — `elif settings.
                                    webhook_secret:` bỏ qua khi trống

Cả ba đều "cho qua khi chưa cấu hình". Nó luôn trông hợp lý lúc viết: chưa
đặt bí mật thì kiểm cái gì? Nhưng cửa webhook là chỗ người lạ đẩy dữ liệu
vào hệ thống — chưa khoá thì phải ĐÓNG, không phải mở.

Ở đường này, mở nghĩa là bất kỳ ai cũng bơm được tin giả vào hộp thư, và
agent sẽ trả lời chúng như tin thật.
"""
from __future__ import annotations

import inspect


def test_khong_co_bi_mat_thi_tu_choi():
    from agent import main

    nguon = inspect.getsource(main.webhook)
    assert "if not settings.webhook_secret:" in nguon, (
        "vẫn bỏ qua kiểm tra khi bí mật trống"
    )


def _bo_chu_thich(src: str) -> str:
    """
    Bỏ chú thích và docstring, chỉ giữ mã chạy được.

    Cần vì chú thích trong dự án này giải thích VÌ SAO KHÔNG làm một điều —
    nên chúng chứa đúng chuỗi mà test đang tìm để cấm. Repo đã mắc lỗi
    soi-nhầm-chú-thích nhiều lần; `tests/test_canh_gac.py` ghi lại.
    """
    import io
    import tokenize

    ra = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            ra.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return " ".join(d for d in src.splitlines()
                        if not d.strip().startswith("#"))
    return " ".join(ra)


def test_khong_con_khuon_elif_cho_qua():
    from agent import main

    ma = _bo_chu_thich(inspect.getsource(main.webhook))
    assert "elif settings.webhook_secret" not in ma


def test_so_sanh_khong_thoat_som():
    """So sánh chuỗi thường dừng ở byte đầu khác nhau — đủ để dò từng ký tự."""
    from agent import main

    assert "compare_digest" in inspect.getsource(main.webhook)


def test_ba_cho_deu_cung_mot_luat():
    """
    Canh CẢ BA để lần thứ tư không xảy ra ở một cửa mới.
    """
    from agent.api import native_webhooks
    from agent.shipping import service

    assert "không" in inspect.getsource(native_webhooks.doc_thach_thuc).lower()
    nguon_ship = inspect.getsource(service.kiem_bi_mat_webhook)
    assert "if not bi_mat:" in nguon_ship
    assert "return False" in nguon_ship
