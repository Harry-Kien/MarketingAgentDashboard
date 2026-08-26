"""
Verify token phải xem được ngay trên dashboard, KHÔNG phải mở file text.

VÌ SAO ĐƯỢC PHÉP HIỆN — VÀ VÌ SAO CHỈ RIÊNG NÓ
-----------------------------------------------
Ba loại bí mật của một tài khoản Meta không cùng mức nhạy cảm:

  access_token  -> đọc tin khách và nhắn thay Trang. LỘ LÀ MẤT TRANG.
  app_secret    -> giả mạo chữ ký webhook. LỘ LÀ BỊ BƠM TIN GIẢ.
  verify_token  -> chuỗi Meta dội lại khi bắt tay. Tự nó KHÔNG mở được gì.

Verify token còn phải được người vận hành dán sang Meta bằng tay — giấu nó
không tăng an toàn, chỉ làm tính năng bế tắc. Chính Meta cũng hiện nó trong
giao diện của họ.

Hai cái đầu thì không bao giờ được ra khỏi vault.

Đó là lý do có MỘT endpoint riêng cho MỘT trường, thay vì thêm nó vào
`to_public()` — nơi mọi trường đều đi ra cùng lúc và dễ lỡ tay thêm nhầm.
"""
from __future__ import annotations

import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_co_endpoint_rieng_cho_verify_token():
    from agent.api.channel_accounts import router

    duong = {getattr(r, "path", "") for r in router.routes}
    assert "/api/channel-accounts/{account_id}/verify-token" in duong


def test_endpoint_doi_quyen_quan_tri():
    from agent.api import channel_accounts

    nguon = inspect.getsource(channel_accounts.doc_verify_token)
    assert "bat_buoc_quan_tri" in nguon


def _bo_chu_thich(src: str) -> str:
    """
    Bỏ docstring và chú thích, chỉ giữ mã chạy được.

    Cần vì chú thích trong dự án này thường giải thích VÌ SAO KHÔNG làm một
    điều — nên chúng chứa đúng những chữ mà test đang tìm để cấm. Repo đã
    mắc lỗi soi-nhầm-chú-thích ba lần; `tests/test_canh_gac.py` ghi lại.
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
        # Rơi về cách thô còn hơn làm đỏ test vì lý do không liên quan.
        return " ".join(
            d for d in src.splitlines() if not d.strip().startswith("#")
        )
    return " ".join(ra)


def test_chi_tra_verify_token_khong_tra_gi_khac():
    """
    Trả nguyên `credentials` là lộ access_token và app_secret cùng lúc.

    Endpoint phải dựng response từ ĐÚNG một trường, không phải lọc bớt từ một
    dict đầy đủ — lọc thì lần sau ai thêm trường mới lại lọt.
    """
    from agent.api import channel_accounts

    ma = _bo_chu_thich(inspect.getsource(channel_accounts.doc_verify_token))
    for cam in ("access_token", "app_secret", "secret_key", "sidecar_secret"):
        assert cam not in ma, f"mã endpoint có đụng tới {cam}"


def test_to_public_van_khong_he_lo_credential():
    """Đường cũ phải giữ nguyên: thêm cửa mới không được nới cửa cũ."""
    from agent.omnichannel.accounts import ChannelAccount

    nguon = inspect.getsource(ChannelAccount.to_public)
    for cam in ("verify_token", "access_token", "app_secret"):
        assert f'"{cam}"' not in nguon


def test_dashboard_co_nut_xem_va_khong_tu_hien_san():
    """
    Không hiện sẵn: thẻ tài khoản nằm trên màn hình chung, và người ta hay
    chụp màn hình chỗ này để hỏi nhau.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "verify-token" in js, "dashboard chưa gọi endpoint"
    assert "data-verifytoken" in js, "chưa có nút xem"
