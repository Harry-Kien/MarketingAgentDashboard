"""
`san_sang` phải bắt được địa chỉ webhook Zalo OA đã cũ. Không cần CSDL.

Mục “Callback provider” cũ chỉ hỏi "PUBLIC_BASE_URL có phải https không".
Câu đó gần như luôn đúng — kể cả khi Zalo đang gọi vào một tên miền
`trycloudflare` đã chết từ lần khởi động trước. Nên nó là một mục xanh
không mang thông tin gì về việc tin khách có vào được không.

Mục mới đọc tên miền Zalo THẬT SỰ đã gọi vào (webhook qua được chữ ký) và
so với tên miền hiện tại. Xem agent/omnichannel/webhook_da_toi.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import san_sang  # noqa: E402

MOI = "https://moi.trycloudflare.com"


def _oa(host=None, ten="OA CSKH"):
    meta = {}
    if host:
        meta["webhook_da_toi"] = {"host": host, "luc": "2026-09-14T10:00:00+00:00"}
    return {"display_name": ten, "metadata": meta}


def test_khong_co_tai_khoan_OA_thi_DU_va_khong_lam_phien():
    """Cửa hàng chưa nối OA không được bị bắt sửa một thứ họ không dùng."""
    assert san_sang.doc_webhook_zalo_oa([], MOI)["muc"] == san_sang.DU


def test_ten_mien_lech_thi_CHAN():
    """
    Đây là cái hỏng thật: tunnel đổi tên miền, người quên dán lại vào Zalo
    Console, và tin khách ngừng vào mà không có gì báo.
    """
    kq = san_sang.doc_webhook_zalo_oa([_oa("cu.trycloudflare.com")], MOI)
    assert kq["muc"] == san_sang.CHAN
    assert "cu.trycloudflare.com" in kq["ghi"]
    # Phải nói ra ĐỊA CHỈ CẦN DÁN, không chỉ nói là sai.
    assert "webhook/native/zalo-oa/" in kq["sua"]


def test_ten_mien_khop_thi_DU():
    kq = san_sang.doc_webhook_zalo_oa([_oa("moi.trycloudflare.com")], MOI)
    assert kq["muc"] == san_sang.DU


def test_chua_tung_nhan_webhook_thi_CANH_BAO_chu_khong_phai_DU():
    """
    Xanh giả nguy hiểm hơn đỏ giả. "Chưa ai nhắn" và "URL sai nên từ chối
    hết" nhìn từ đây giống hệt nhau, nên không được gọi là đủ.
    """
    kq = san_sang.doc_webhook_zalo_oa([_oa(None)], MOI)
    assert kq["muc"] == san_sang.CANH_BAO
    assert "chưa" in kq["ghi"].lower()


def test_mot_OA_lech_giua_nhieu_OA_van_CHAN():
    """Kết luận lấy theo mục TỆ NHẤT, không lấy theo đa số."""
    kq = san_sang.doc_webhook_zalo_oa(
        [_oa("moi.trycloudflare.com", "OA A"), _oa("cu.trycloudflare.com", "OA B")],
        MOI)
    assert kq["muc"] == san_sang.CHAN
    assert "OA B" in kq["ghi"]


def test_muc_da_duoc_gan_vao_bang_ket_qua():
    """Viết phép kiểm mà quên đưa vào danh sách chạy thì nó không canh gì."""
    nguon = (ROOT / "scripts" / "san_sang.py").read_text(encoding="utf-8")
    assert "kiem_webhook_zalo_oa()" in nguon
