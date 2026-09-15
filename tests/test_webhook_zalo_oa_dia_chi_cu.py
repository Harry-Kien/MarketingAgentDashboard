"""
Canh địa chỉ webhook đã khai ở Zalo Console có còn trỏ đúng chỗ không.

VÌ SAO CẦN, VÀ VÌ SAO NÓ KHÓ
----------------------------
Zalo KHÔNG có API để đọc hay đăng ký địa chỉ webhook — người phải vào
Console dán tay. Trong khi đó `PUBLIC_BASE_URL` của hệ thống này là một tên
miền `trycloudflare` **đổi mỗi lần chạy `scripts.khoi_dong`**.

Nên mỗi lần khởi động lại mà quên dán lại URL là kênh chết: OA gửi đi được,
tin khách không vào, dashboard vẫn xanh vì chẳng có gì hỏng. `san_sang` cũ
chỉ kiểm "PUBLIC_BASE_URL có phải https" — điều đó luôn đúng, kể cả khi
Zalo đang gọi vào một tên miền đã chết.

Không hỏi được Zalo thì hỏi chính lịch sử: **Zalo đã gọi vào tên miền nào,
lần gần nhất?** Đó là sự thật mặt đất — Zalo gọi tới được nghĩa là URL ấy
đúng. So nó với tên miền hiện tại là phát hiện được đúng cái hỏng trên.

Ba trạng thái, và cả ba đều phải nói thật:
  · chưa có tin nào đi qua  -> CHƯA CHỨNG MINH được (không phải "đủ")
  · tên miền khớp           -> đủ
  · tên miền lệch           -> HỎNG, kèm tên miền cũ để người biết dán gì
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.omnichannel.webhook_da_toi import (TRANG_CHUA_RO,  # noqa: E402
                                              TRANG_KHOP, TRANG_LECH,
                                              doc_host, so_dia_chi)


# ---------------------------------------------------------------
#  Rút host khỏi một URL
# ---------------------------------------------------------------

def test_doc_host_bo_giao_thuc_va_duong_dan():
    assert doc_host("https://abc-def.trycloudflare.com/") == "abc-def.trycloudflare.com"
    assert doc_host("https://abc.example.com/webhook/x") == "abc.example.com"


def test_doc_host_khong_hoa_thuong_lan_nhau():
    """Host không phân biệt hoa thường; so chuỗi thô là báo lệch oan."""
    assert doc_host("https://ABC.Example.COM") == doc_host("https://abc.example.com")


def test_doc_host_rong_thi_tra_rong():
    assert doc_host("") == ""
    assert doc_host("khong-phai-url") == ""


# ---------------------------------------------------------------
#  Ba trạng thái
# ---------------------------------------------------------------

def test_chua_tung_nhan_webhook_thi_CHUA_RO_chu_khong_phai_dat():
    """
    Khẳng định quan trọng nhất tệp này.

    "Chưa ai nhắn" và "URL khai sai nên từ chối hết" nhìn từ phía ta giống
    hệt nhau. Gọi trạng thái đó là "đủ" chính là xanh giả — và CLAUDE.md
    xếp xanh giả nguy hiểm hơn đỏ giả, vì đỏ giả thì người ta đi kiểm.
    """
    trang, _ = so_dia_chi({}, "https://moi.trycloudflare.com")
    assert trang == TRANG_CHUA_RO


def test_ten_mien_khop_thi_DAT():
    meta = {"webhook_da_toi": {"host": "cu.trycloudflare.com",
                               "luc": "2026-09-14T10:00:00+00:00"}}
    trang, _ = so_dia_chi(meta, "https://cu.trycloudflare.com")
    assert trang == TRANG_KHOP


def test_ten_mien_lech_thi_HONG_va_noi_ro_ten_mien_cu():
    meta = {"webhook_da_toi": {"host": "cu.trycloudflare.com",
                               "luc": "2026-09-14T10:00:00+00:00"}}
    trang, ly_do = so_dia_chi(meta, "https://moi.trycloudflare.com")
    assert trang == TRANG_LECH
    # Người đọc phải biết Zalo đang gọi vào đâu để hiểu vì sao im lặng.
    assert "cu.trycloudflare.com" in ly_do


def test_chua_cau_hinh_dia_chi_cong_khai_thi_CHUA_RO():
    meta = {"webhook_da_toi": {"host": "cu.trycloudflare.com", "luc": "x"}}
    trang, _ = so_dia_chi(meta, "")
    assert trang == TRANG_CHUA_RO


def test_metadata_hinh_dang_la_khong_lam_no():
    """Metadata là JSONB người sửa được; hình dạng lạ không được làm sập."""
    for meta in [None, {"webhook_da_toi": "chuoi"}, {"webhook_da_toi": {}},
                 {"webhook_da_toi": {"host": ""}}, {"webhook_da_toi": []}]:
        trang, _ = so_dia_chi(meta, "https://x.example.com")
        assert trang == TRANG_CHUA_RO, meta


# ---------------------------------------------------------------
#  Đường webhook phải THỰC SỰ ghi lại — lưới không mắc vào thì bằng không
# ---------------------------------------------------------------

def _dung_app(monkeypatch, ghi_lai: list):
    import hashlib
    from uuid import uuid4

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent.api import zalo_oa_webhook as mod
    from agent.omnichannel.accounts import (AccountStatus, Channel,
                                            ChannelAccount)

    app_id, secret, aid = "2109757420003470723", "s" * 32, uuid4()
    account = ChannelAccount(
        id=aid, channel=Channel.ZALO_OA, display_name="OA thử",
        external_account_id="oa-1", status=AccountStatus.ACTIVE,
        capabilities={}, metadata={}, is_legacy=False)

    class _Repo:
        async def get(self, account_id):
            return account if account_id == aid else None

    class _Loader:
        async def load(self, account_id):
            return {"app_id": app_id, "secret_key": secret, "refresh_token": "r"}

    class _Adapter:
        def parse_nhieu(self, payload):
            return []

        async def aclose(self):
            return None

    class _Factory:
        def __init__(self, *a, **k):
            pass

        async def create(self, account_id):
            return _Adapter()

    async def _ghi_nhan(account_id, host):
        ghi_lai.append((account_id, host))

    monkeypatch.setattr(mod, "_kho", lambda: (_Repo(), _Loader()))
    monkeypatch.setattr(mod, "AccountAdapterFactory", _Factory)
    monkeypatch.setattr(mod, "ghi_nhan_webhook_da_toi", _ghi_nhan)

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    def goi(*, ky_dung=True, host="pcs-abc.trycloudflare.com"):
        than = (b'{"app_id":"x","event_name":"follow",'
                b'"timestamp":"1725350400000"}')
        mac = hashlib.sha256(
            (app_id + than.decode() + "1725350400000" + secret).encode()
        ).hexdigest() if ky_dung else "0" * 64
        return client.post(f"/webhook/native/zalo-oa/{aid}", content=than,
                           headers={"Content-Type": "application/json",
                                    "X-ZEvent-Signature": f"mac={mac}",
                                    "Host": host})

    return goi, aid


def test_webhook_qua_chu_ky_thi_ghi_lai_ten_mien(monkeypatch):
    ghi_lai: list = []
    goi, aid = _dung_app(monkeypatch, ghi_lai)

    r = goi()

    assert r.status_code == 200, r.text
    assert ghi_lai == [(aid, "pcs-abc.trycloudflare.com")]


def test_chu_ky_sai_thi_KHONG_ghi_gi(monkeypatch):
    """
    Ghi trước khi kiểm chữ ký là để người lạ tự khai tên miền vào hồ sơ tài
    khoản — rồi cảnh báo "địa chỉ đã cũ" nổ oan, hoặc tệ hơn là im đi đúng
    lúc địa chỉ thật đã cũ.
    """
    ghi_lai: list = []
    goi, _ = _dung_app(monkeypatch, ghi_lai)

    r = goi(ky_dung=False)

    assert r.status_code == 401
    assert ghi_lai == []
