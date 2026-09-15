"""
Resolver nội bộ mù KHÔNG được đọc thành "tunnel chết".

ĐO ĐƯỢC (15.09.2026, mạng VNPT)
-------------------------------
`chay_tunnel` mở tunnel thành công — cloudflared ghi `Registered tunnel
connection ... location=hkg11` — rồi `_thong()` gọi thử và trượt sạch:

    nslookup courier-...trycloudflare.com   -> Non-existent domain
                                              (server: static.vnpt.vn)
    nslookup ... 1.1.1.1                   -> 104.16.231.132, ...
    curl --resolve ...:443:104.16.231.132  -> HTTP 200

Tức là tên miền SỐNG và phục vụ được từ Internet; chỉ máy này không phân
giải nổi. Zalo và Meta dùng resolver của họ nên gọi vào bình thường.

Bản cũ kết luận "Tunnel lên nhưng KHÔNG thông từ ngoài" rồi `return 1`
TRƯỚC khi ghi `.env`. Hậu quả nặng hơn một dòng chữ sai: `.env` giữ nguyên
tên miền CŨ ĐÃ CHẾT, nên dashboard vẫn dựng URL webhook trỏ vào hư không —
và người vận hành vừa được báo "tunnel không thông" nên đi tìm bệnh ở chỗ
khác.

Đỏ giả cũng là một kiểu hỏng: CLAUDE.md nói một bảng luôn đỏ là bảng người
ta thôi đọc. Nên phải phân biệt được HAI ca khác nhau:

  · không phân giải được TỪ MÁY NÀY  -> hỏi DNS công cộng rồi gọi qua IP
  · phân giải được mà gọi vẫn trượt  -> tunnel hỏng thật
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.chay_tunnel import KET_QUA_DNS_NOI_BO_MU, doc_ket_qua_thong  # noqa: E402


def test_goi_duoc_bang_dns_noi_bo_thi_DAT():
    trang, _ = doc_ket_qua_thong(so_lan_ok=2, dns_noi_bo_mu=False, ok_qua_ip=0)
    assert trang == "thong"


def test_dns_noi_bo_mu_ma_goi_qua_IP_duoc_thi_VAN_DAT():
    """
    Ca đã cắn. Tunnel sống, chỉ máy này mù — phải coi là thông và GHI .env.
    """
    trang, ly_do = doc_ket_qua_thong(so_lan_ok=0, dns_noi_bo_mu=True, ok_qua_ip=1)
    assert trang == KET_QUA_DNS_NOI_BO_MU
    # Phải nói rõ bệnh nằm ở resolver của máy, không phải ở tunnel.
    assert "DNS" in ly_do or "phân giải" in ly_do


def test_dns_noi_bo_mu_va_qua_IP_cung_truot_thi_HONG():
    trang, _ = doc_ket_qua_thong(so_lan_ok=0, dns_noi_bo_mu=True, ok_qua_ip=0)
    assert trang == "hong"


def test_phan_giai_duoc_ma_goi_van_truot_thi_HONG():
    """Không được lấy cớ DNS để bỏ qua một tunnel hỏng thật."""
    trang, _ = doc_ket_qua_thong(so_lan_ok=0, dns_noi_bo_mu=False, ok_qua_ip=0)
    assert trang == "hong"


def test_dns_mu_van_GHI_env_va_van_bao_thanh_cong(monkeypatch, tmp_path):
    """
    Khẳng định quan trọng nhất tệp này: hậu quả thật của bản cũ không phải
    một dòng chữ sai, mà là `.env` GIỮ NGUYÊN tên miền đã chết.

    Chạy `main()` với mọi chặng mạng được thay bằng đồ giả, chỉ để xem nó có
    ghi `.env` hay không.
    """
    from scripts import chay_tunnel as ct

    da_ghi: list[str] = []
    monkeypatch.setattr(ct, "_cloudflared", lambda: "cloudflared")
    monkeypatch.setattr(ct, "_app_song", lambda: True)
    monkeypatch.setattr(ct, "_giet_tunnel_cu", lambda **_k: 0)
    monkeypatch.setattr(ct, "mo_nhat_ky",
                        lambda d, **k: (open(tmp_path / "t.log", "w"), d))
    monkeypatch.setattr(ct.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(ct, "_cho_domain",
                        lambda *a, **k: "https://x.trycloudflare.com")
    monkeypatch.setattr(ct, "kiem_thong",
                        lambda *a, **k: (KET_QUA_DNS_NOI_BO_MU,
                                         "máy này không phân giải được", 1))
    monkeypatch.setattr(ct, "_doi_env", lambda d: da_ghi.append(d))

    ma = ct.main()

    assert da_ghi == ["https://x.trycloudflare.com"], "KHÔNG ghi .env"
    assert ma == 0, "báo thất bại cho một tunnel đang phục vụ được"


def test_tunnel_hong_that_thi_KHONG_ghi_env(monkeypatch, tmp_path):
    """Vế còn lại: đừng ghi một tên miền không ai gọi tới được vào .env."""
    from scripts import chay_tunnel as ct

    da_ghi: list[str] = []
    monkeypatch.setattr(ct, "_cloudflared", lambda: "cloudflared")
    monkeypatch.setattr(ct, "_app_song", lambda: True)
    monkeypatch.setattr(ct, "_giet_tunnel_cu", lambda **_k: 0)
    monkeypatch.setattr(ct, "mo_nhat_ky",
                        lambda d, **k: (open(tmp_path / "t.log", "w"), d))
    monkeypatch.setattr(ct.subprocess, "Popen", lambda *a, **k: None)
    monkeypatch.setattr(ct, "_cho_domain",
                        lambda *a, **k: "https://x.trycloudflare.com")
    monkeypatch.setattr(ct, "kiem_thong",
                        lambda *a, **k: ("hong", "không gọi tới được", 0))
    monkeypatch.setattr(ct, "_doi_env", lambda d: da_ghi.append(d))

    assert ct.main() == 1
    assert da_ghi == []
