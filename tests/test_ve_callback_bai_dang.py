"""
Vòng đời vé callback đăng bài, trên Postgres thật.

VẤN ĐỀ ĐANG CANH
----------------
`agent/publish/n8n.py` gửi `callback_url` cho n8n. Đường ấy nằm sau chốt
đăng nhập `/api/*`, mà n8n là một tiến trình — nó không có cookie phiên.
Mọi lần gọi về đều 401, từ trước tới nay.

Và nó hỏng IM LẶNG theo đúng nghĩa tệ nhất: bài VẪN được đăng thật lên nền
tảng, chỉ có kết quả là không bao giờ ghi lại. Dashboard hiện "đang đăng"
vĩnh viễn, `post_metrics` rỗng, vòng phản hồi "nội dung nào chạy tốt" chết
câm. Không có dòng lỗi nào ở phía ta vì phía ta không hề biết có ai gọi.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

LUOC_DO = ROOT / "agent" / "schema.sql"


async def _dung(url: str):
    import asyncpg

    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    db._pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with db._pool.acquire() as conn:
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)


async def _tao_bai() -> str:
    from agent import db

    r = await db.fetchrow(
        "INSERT INTO posts (tieu_de, noi_dung, kenh) "
        "VALUES ('thu', 'noi dung', $1::jsonb) RETURNING id",
        ["facebook", "tiktok"])
    return str(r["id"])


def _chay(url, viec):
    async def _m():
        from agent import db

        await _dung(url)
        try:
            return await viec()
        finally:
            await db._pool.close()
            db._pool = None
    return asyncio.run(_m())


def test_ve_cap_ra_thi_kiem_duoc(csdl_kiem_thu):
    from agent.publish import service

    async def viec():
        pid = await _tao_bai()
        ve = await service.cap_ve_callback(pid)
        assert await service.kiem_ve_callback(pid, ve) is True
    _chay(csdl_kiem_thu, viec)


def test_ve_sai_bi_tu_choi(csdl_kiem_thu):
    from agent.publish import service

    async def viec():
        pid = await _tao_bai()
        await service.cap_ve_callback(pid)
        assert await service.kiem_ve_callback(pid, "ve-bia") is False
    _chay(csdl_kiem_thu, viec)


def test_bai_chua_cap_ve_thi_khong_ai_goi_ve_duoc(csdl_kiem_thu):
    """
    Bài chưa đẩy đi lần nào thì `callback_token` là NULL. NULL không được
    khớp với chuỗi rỗng — nếu khớp thì mọi bài chưa đăng đều mở toang.
    """
    from agent.publish import service

    async def viec():
        pid = await _tao_bai()
        assert await service.kiem_ve_callback(pid, "") is False
        assert await service.kiem_ve_callback(pid, "bat-ky") is False
    _chay(csdl_kiem_thu, viec)


def test_ve_cua_bai_nay_khong_mo_duoc_bai_khac(csdl_kiem_thu):
    """Phạm vi của vé phải hẹp nhất có thể: đúng MỘT bài."""
    from agent.publish import service

    async def viec():
        a, b = await _tao_bai(), await _tao_bai()
        ve_a = await service.cap_ve_callback(a)
        await service.cap_ve_callback(b)
        assert await service.kiem_ve_callback(b, ve_a) is False
    _chay(csdl_kiem_thu, viec)


def test_cap_lai_thi_ve_cu_chet(csdl_kiem_thu):
    """
    Đẩy lại một bài nghĩa là lần trước có gì đó không xong, và vé của lần
    ấy có thể đã nằm trong log của một hệ thống khác.
    """
    from agent.publish import service

    async def viec():
        pid = await _tao_bai()
        cu = await service.cap_ve_callback(pid)
        moi = await service.cap_ve_callback(pid)
        assert cu != moi
        assert await service.kiem_ve_callback(pid, cu) is False
        assert await service.kiem_ve_callback(pid, moi) is True
    _chay(csdl_kiem_thu, viec)


def test_ve_song_qua_kenh_dau_va_chet_khi_het_kenh_cho(csdl_kiem_thu):
    """
    ĐÂY LÀ CHỖ DỄ SAI NHẤT.

    Một bài đăng lên NHIỀU kênh và n8n gọi về MỘT LẦN MỖI KÊNH. Xoá vé sau
    lần gọi đầu thì kết quả của các kênh còn lại rơi hết vào 401 — và rơi
    im lặng, đúng như lỗi đang sửa.

    Nhưng giữ vé mãi sau khi xong cũng sai: đó là một chìa khoá còn mở được
    một cánh cửa không còn gì sau nó, và chìa ấy nằm trong log của n8n.
    """
    from agent import db
    from agent.publish import service

    async def viec():
        pid = await _tao_bai()
        ve = await service.cap_ve_callback(pid)
        # Đánh dấu cả hai kênh là "đã nhận, đang xử lý" như lúc đẩy thật.
        await db.execute(
            "UPDATE posts SET ket_qua = $2::jsonb WHERE id = $1", pid,
            {"facebook": {"ok": True, "cho_xu_ly": True},
             "tiktok": {"ok": True, "cho_xu_ly": True}})

        await service.ghi_nhan_callback(pid, "facebook", True, "https://fb/1")
        assert await service.kiem_ve_callback(pid, ve) is True, (
            "vé chết sau kênh đầu — kênh thứ hai sẽ không báo về được")

        await service.ghi_nhan_callback(pid, "tiktok", True, "https://tt/1")
        assert await service.kiem_ve_callback(pid, ve) is False, (
            "xong hết rồi mà vé vẫn mở")

        r = await db.fetchrow("SELECT trang_thai FROM posts WHERE id=$1", pid)
        assert r["trang_thai"] == "da_dang"
    _chay(csdl_kiem_thu, viec)


def test_khong_co_ve_thi_n8n_khong_nhan_callback_url(csdl_kiem_thu):
    """
    Thà KHÔNG gửi còn hơn gửi một đường chắc chắn 401: n8n ghi lỗi vào log
    của nó, và không ai ở phía ta đọc log ấy.
    """
    from agent.publish.base import PublishTarget

    t = PublishTarget(post_id=str(uuid4()), kenh="facebook",
                      tieu_de="a", noi_dung="b")
    assert t.callback_token == ""


class _TraLoiGia:
    status_code = 200
    content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {}


class _HttpGia:
    """Bắt lấy thân yêu cầu thay vì gọi ra mạng."""

    def __init__(self):
        self.than = None

    async def post(self, url, json=None, headers=None):
        self.than = json
        return _TraLoiGia()


@pytest.mark.parametrize("co_ve,mong_doi", [(True, True), (False, False)])
def test_callback_url_chi_xuat_hien_khi_co_ve(co_ve, mong_doi, monkeypatch):
    """
    Đọc ĐÚNG thân yêu cầu n8n nhận được, không đọc mã nguồn.

    Đọc mã nguồn bằng chuỗi thì xanh với cả một bản đã gãy — chỉ cần ai đó
    đổi cách dựng chuỗi là phép so mất đối tượng mà test vẫn báo xanh.
    """
    from agent.config import settings
    from agent.publish import n8n
    from agent.publish.base import PublishTarget

    monkeypatch.setattr(settings, "n8n_webhook_url", "https://n8n.thu/hook")
    monkeypatch.setattr(settings, "public_base_url", "https://shop.vn")

    bo = n8n.N8nPublisher()
    gia = _HttpGia()
    bo._http = gia

    asyncio.run(bo.publish(PublishTarget(
        post_id="11111111-2222-3333-4444-555555555555",
        kenh="facebook", tieu_de="a", noi_dung="b",
        callback_token="ve-that" if co_ve else "",
    )))

    co_url = "callback_url" in (gia.than or {})
    assert co_url is mong_doi
    if mong_doi:
        url = gia.than["callback_url"]
        # Vé đi trong URL chứ không trong header: workflow n8n mẫu không có
        # chỗ nào đọc header ra, và bắt người dùng tự sửa workflow là bắt
        # họ làm một việc họ không biết là phải làm.
        assert "token=ve-that" in url
        assert url.startswith("https://shop.vn/api/posts/")
