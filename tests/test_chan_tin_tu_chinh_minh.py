"""
Tin do CHÍNH tài khoản gửi không bao giờ được ghi nhận như tin của khách.

VÌ SAO CẦN LỚP THỨ HAI
----------------------
Sidecar đã lọc rồi. Nhưng theo luật của repo, ràng buộc nào không được phép
sai thì phải hiện thực HAI lần — và ở đây lý do rất cụ thể:

  - sidecar là tiến trình RIÊNG, có thể bị thay, hạ cấp, hoặc chạy bản cũ
  - `own_id` bên sidecar nằm trong RAM; mất phiên là mất, khôi phục xong có
    lúc chưa kịp gán
  - hậu quả nếu lọt: agent trả lời chính nó, vòng lặp vô hạn ở chế độ auto

Control plane biết `own_id` bền hơn: nó nằm trong `channel_accounts.
external_account_id`, đã được ghim khi xác minh provider.
"""
from __future__ import annotations

from agent.api.zalo_personal_webhook import la_tin_tu_chinh_minh


def test_bo_tin_khi_nguoi_gui_la_chinh_tai_khoan():
    assert la_tin_tu_chinh_minh("own-123", "own-123") is True


def test_giu_tin_cua_khach():
    assert la_tin_tu_chinh_minh("khach-9", "own-123") is False


def test_chua_gan_own_id_thi_khong_chan_nham():
    """
    Account còn ở `pending:` thì KHÔNG được coi mọi tin là của chính mình.

    Chặn nhầm ở đây nghĩa là nuốt sạch tin khách trong giai đoạn chưa xác
    minh xong — im lặng và không ai biết.
    """
    assert la_tin_tu_chinh_minh("khach-9", "pending:abc-123") is False
    assert la_tin_tu_chinh_minh("khach-9", "") is False
    assert la_tin_tu_chinh_minh("khach-9", None) is False


def test_bo_qua_khoang_trang_thua():
    assert la_tin_tu_chinh_minh(" own-123 ", "own-123") is True
