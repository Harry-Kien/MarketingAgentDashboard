"""
Media khách gửi: tải về máy chủ, chống trùng, giữ 180 ngày, dọn mồ côi.

Rà soát 20.11.2026: ảnh, video, tệp khách gửi CHƯA BAO GIỜ được lưu —
`attachments.url` chỉ giữ link CDN của hãng, và link ấy hết hạn. Chủ dự án
quyết: tải về, giữ 180 ngày, chống trùng. File này canh từng ràng buộc của
quyết định ấy, và những chốt an toàn đi kèm (trần dung lượng, kiểu tệp, địa
chỉ nội bộ, không bao giờ xoá ảnh sản phẩm).

KHÔNG TEST NÀO RA MẠNG: mọi lời gọi HTTP đi qua `httpx.MockTransport`, mọi
lần phân giải tên máy đi qua một bộ phân giải giả.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import io
import json
import os
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest

from agent import duong_dan_du_lieu
from agent.omnichannel import media, media_don

ROOT = Path(__file__).resolve().parent.parent
LUOC_DO = ROOT / "agent" / "schema.sql"

JPG = b"\xff\xd8\xff\xe0" + b"anh-that" * 50
PNG = b"\x89PNG\r\n\x1a\n" + b"png" * 40
HTML = b"<html><script>alert(1)</script></html>"


async def _cong_khai(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.fixture
def goc(tmp_path, monkeypatch):
    """`data/` giả: mọi tệp test ghi vào đây, không chạm `data/` của repo."""
    g = (tmp_path / "data").resolve()
    g.mkdir()
    monkeypatch.setattr(duong_dan_du_lieu, "GOC_DU_LIEU", g)
    return g


def _client(bang: dict, goi: list | None = None) -> httpx.AsyncClient:
    def xu_ly(req: httpx.Request) -> httpx.Response:
        if goi is not None:
            goi.append(req)
        tra = bang[str(req.url)]
        return tra(req) if callable(tra) else tra
    return httpx.AsyncClient(transport=httpx.MockTransport(xu_ly))


def _tai(url, bang, **kw):
    async def chay():
        async with _client(bang, kw.pop("goi", None)) as c:
            return await media.tai_ve(url, client=c, phan_giai=kw.pop("phan_giai", _cong_khai), **kw)
    return asyncio.run(chay())


# =====================================================================
#  Phần thuần — không CSDL
# =====================================================================

def test_url_vao_nhat_ky_khong_mang_chu_ky():
    """URL CDN Facebook mang chữ ký trong query; URL có thể mang user:pass."""
    u = "https://user:mk@scontent.xx.fbcdn.net/v/t1/abc.jpg?oh=CHU_KY&oe=123#x"
    a = media.an_url(u)
    assert a == "https://scontent.xx.fbcdn.net/v/t1/abc.jpg"
    assert "CHU_KY" not in a and "mk" not in a


@pytest.mark.parametrize("dau,mime", [
    (JPG, "image/jpeg"), (PNG, "image/png"), (b"GIF89a....", "image/gif"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    (b"\x00\x00\x00\x18ftypmp42", "video/mp4"), (b"\x00\x00\x00\x18ftypqt  ", "video/quicktime"),
    (b"\x00\x00\x00\x18ftypheic", "image/heic"), (b"%PDF-1.7", "application/pdf"),
    (b"OggS\x00", "audio/ogg"), (b"#!AMR\n", "audio/amr"), (b"ID3\x03", "audio/mpeg"),
])
def test_nhan_dang_theo_chu_ky_dau_tep(dau, mime):
    assert media.nhan_dang(dau)[0] == mime


@pytest.mark.parametrize("dau,khai", [
    (HTML, "image/jpeg"), (HTML, "text/html"), (b"<svg onload=x>", "image/svg+xml"),
    (b"MZ\x90\x00", "application/octet-stream"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", ""),
])
def test_kieu_ngoai_danh_sach_bi_tu_choi_du_header_noi_gi(dau, khai):
    """
    Tệp được phục vụ lại từ origin của dashboard. Một trang HTML khai
    `image/jpeg` mà được giữ là XSS lưu trữ trong tab người trực.
    """
    assert media.nhan_dang(dau, khai) is None


def test_trang_thai_ban_dau():
    assert media.trang_thai_ban_dau({"url": "https://cdn/x.jpg"}) == "cho"
    # Chatwoot: `url` là đường proxy tương đối, bản thật ở `original_url`.
    assert media.trang_thai_ban_dau(
        {"url": "/tich-hop/chatwoot/a.jpg", "original_url": "http://localhost:3200/a.jpg"}) == "cho"
    # WhatsApp: chỉ có id.
    assert media.trang_thai_ban_dau({"metadata": {"provider_media_id": "123"}}) == "cho"
    assert media.trang_thai_ban_dau({"url": None, "metadata": {}}) == "bo_qua"
    assert media.nguon_url({"url": "/tich-hop/chatwoot/a.jpg",
                            "original_url": "http://cw/a.jpg"}) == "http://cw/a.jpg"


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/api/x", "http://10.0.0.5/a.jpg", "http://169.254.169.254/latest",
    "http://[::1]/a", "http://192.168.1.1/a.jpg", "ftp://cdn/a.jpg", "file:///etc/passwd",
])
def test_chan_dia_chi_noi_bo(url):
    """URL đến từ webhook; webchat là đường công khai."""
    assert asyncio.run(media.kiem_dich(url, _cong_khai)) is not None


def test_ten_may_phan_giai_ra_dia_chi_noi_bo_cung_bi_chan():
    async def noi_bo(host):
        return ["10.1.2.3"]
    assert asyncio.run(media.kiem_dich("https://cdn.tro-vao-noi-bo.test/a.jpg", noi_bo))


def test_chatwoot_da_cau_hinh_duoc_mo(monkeypatch):
    """Chatwoot trả link trỏ vào chính nó (localhost) — chặn là mất ảnh cả kênh."""
    from agent.config import settings

    monkeypatch.setattr(settings, "chatwoot_base_url", "http://localhost:3200")
    assert asyncio.run(media.kiem_dich("http://localhost:3200/rails/a.jpg", _cong_khai)) is None
    # Mở theo TÊN MÁY đã cấu hình, không mở cả localhost: cổng app vẫn đóng.
    assert asyncio.run(media.kiem_dich("http://127.0.0.1:8000/api", _cong_khai))


def test_tai_thanh_cong_ghi_tep_tam_va_bam(goc):
    kq = _tai("https://cdn.test/a.jpg", {"https://cdn.test/a.jpg": httpx.Response(200, content=JPG)})
    assert kq.trang_thai == "da_tai", kq.loi
    assert kq.sha256 == hashlib.sha256(JPG).hexdigest()
    assert kq.mime == "image/jpeg" and kq.duoi == ".jpg" and kq.so_byte == len(JPG)
    assert kq.tam is not None and kq.tam.read_bytes() == JPG
    assert goc / "media" / ".tam" in kq.tam.parents


def test_vuot_tran_thi_dung_doc_ngay_khong_doc_tron(goc):
    """
    Không có Content-Length (truyền khúc): phải dừng ngay khi vượt trần, không
    đọc trọn rồi mới so — video vài GB không được đi hết qua đường mạng.
    """
    da_phat = []

    async def vo_tan():
        for _ in range(10_000):
            da_phat.append(1)
            yield b"\xff\xd8\xff" + b"x" * 1021
    kq = _tai("https://cdn.test/v.mp4",
              {"https://cdn.test/v.mp4": lambda r: httpx.Response(200, content=vo_tan())},
              toi_da=10 * 1024)
    assert kq.trang_thai == "qua_lon"
    assert len(da_phat) < 100, "đọc gần hết luồng rồi mới từ chối"
    assert not any((goc / "media" / ".tam").iterdir()), "tệp tạm dở dang còn nằm lại"


def test_content_length_vuot_tran_thi_khong_tai(goc):
    kq = _tai("https://cdn.test/v.mp4", {"https://cdn.test/v.mp4": httpx.Response(
        200, content=b"x" * 2048, headers={"content-length": "2048"})}, toi_da=1024)
    assert kq.trang_thai == "qua_lon"


@pytest.mark.parametrize("ma,trang_thai", [
    (403, "het_han"), (404, "het_han"), (410, "het_han"),
    (500, "thu_lai"), (503, "thu_lai"), (429, "thu_lai"), (400, "loi"),
])
def test_ma_http_ra_trang_thai(goc, ma, trang_thai):
    kq = _tai("https://cdn.test/a.jpg", {"https://cdn.test/a.jpg": httpx.Response(ma)})
    assert kq.trang_thai == trang_thai


def test_html_gia_anh_bi_bo_va_khong_de_lai_tep(goc):
    kq = _tai("https://cdn.test/a.jpg", {"https://cdn.test/a.jpg": httpx.Response(
        200, content=HTML, headers={"content-type": "image/jpeg"})})
    assert kq.trang_thai == "bo_qua"
    assert not any((goc / "media" / ".tam").iterdir())


def test_chuyen_huong_vao_noi_bo_bi_chan(goc):
    """Chuyển hướng là đường vòng SSRF kinh điển: kiểm địa chỉ ở MỖI bước."""
    goi: list = []
    kq = _tai("https://cdn.test/a.jpg", {
        "https://cdn.test/a.jpg": httpx.Response(302, headers={"location": "http://127.0.0.1:5433/"}),
    }, goi=goi)
    assert kq.trang_thai == "bo_qua" and "nội bộ" in kq.loi
    assert [str(r.url) for r in goi] == ["https://cdn.test/a.jpg"]


def test_chuyen_huong_sang_may_khac_bo_token(goc):
    """Token WhatsApp chỉ dành cho máy đã cấp — không mang sang CDN khác."""
    goi: list = []
    kq = _tai("https://graph.test/m", {
        "https://graph.test/m": httpx.Response(302, headers={"location": "https://cdn2.test/f"}),
        "https://cdn2.test/f": httpx.Response(200, content=PNG),
    }, goi=goi, headers={"Authorization": "Bearer BI_MAT"})
    assert kq.trang_thai == "da_tai"
    assert goi[0].headers.get("authorization") == "Bearer BI_MAT"
    assert "authorization" not in goi[1].headers


def test_mang_hong_la_hong_tam_khong_nem(goc):
    def no(req):
        raise httpx.ConnectError("CDN chết")
    kq = _tai("https://cdn.test/a.jpg", {"https://cdn.test/a.jpg": no})
    assert kq.trang_thai == "thu_lai"


def test_gian_cach_thu_lai_tang_dan_co_tran():
    assert [media.tre_lan_sau(n) for n in (1, 2, 3, 4)] == [30, 120, 480, 1920]
    assert media.tre_lan_sau(9) == 3600


def test_duong_luu_theo_nam_thang_va_sha(goc):
    sha = "ab" + "0" * 62
    p, khoa = media.duong_dich(sha, ".jpg", datetime(2026, 11, 22, tzinfo=timezone.utc))
    assert khoa == f"data/media/2026/11/ab/{sha}.jpg"
    assert p == goc / "media" / "2026" / "11" / "ab" / f"{sha}.jpg"
    assert duong_dan_du_lieu.mo_khoa(khoa) == p


def test_khong_bao_gio_xoa_anh_san_pham_hay_tai_lieu(goc):
    for con in ("products", "knowledge"):
        p = goc / con / "SP1.jpg"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"anh")
        with pytest.raises(media_don.XoaNgoaiVung):
            media_don._xoa_an_toan(p)
        assert p.exists()
    ngoai = goc / "catalog.json"
    ngoai.write_text("{}")
    with pytest.raises(media_don.XoaNgoaiVung):
        media_don._xoa_an_toan(ngoai)
    # Đi vòng bằng `..` cũng không lọt.
    with pytest.raises(media_don.XoaNgoaiVung):
        media_don._xoa_an_toan(goc / "media" / ".." / "products" / "SP1.jpg")


def test_cau_hinh_thoi_han_kiem_gia_tri():
    from agent import cau_hinh_dong as cd

    assert cd.kiem_gia_tri("MEDIA_LUU_NGAY", "180") == "180"
    for xau in ("0", "-1", "abc", "4000"):
        with pytest.raises(cd.KhoaKhongHopLe):
            cd.kiem_gia_tri("MEDIA_LUU_NGAY", xau)
    with pytest.raises(cd.KhoaKhongHopLe):
        cd.kiem_gia_tri("MEDIA_TOI_DA_MB", "500")


def test_mac_dinh_180_ngay_theo_quyet_dinh_chu_du_an():
    from agent.config import Settings

    assert Settings.model_fields["media_luu_ngay"].default == 180
    assert media.luu_ngay() == 180


# ------------------------------------------------------------ anh_khach

def test_anh_khach_doc_theo_luong_dung_som():
    """Bản trước đọc trọn `r.content` rồi mới so 8MB."""
    from agent.core import anh_khach

    da_phat = []

    async def vo_tan():
        for _ in range(100_000):
            da_phat.append(1)
            yield b"\xff" * 1024
    c = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=vo_tan(), headers={"content-type": "image/jpeg"})))
    ra = asyncio.run(anh_khach.lay_khoi_anh([{"loai": "image", "url": "https://x/a.jpg"}], client=c))
    assert ra == []
    assert len(da_phat) < anh_khach.TOI_DA_BYTE // 1024 + 10


def test_anh_khach_uu_tien_ban_tren_may(tmp_path):
    from agent.core import anh_khach

    p = tmp_path / "a.png"
    p.write_bytes(PNG)
    goi = []
    c = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: goi.append(r) or httpx.Response(404)))

    async def ban_dia(url):
        return (p, "image/png")
    ra = asyncio.run(anh_khach.lay_khoi_anh(
        [{"loai": "image", "url": "https://x/het-han.png"}], client=c, ban_dia=ban_dia))
    assert len(ra) == 1 and ra[0]["media_type"] == "image/png"
    assert goi == [], "đã có bản trên máy mà vẫn ra mạng"


# ------------------------------------------------------------ nối dây

def test_vong_tai_duoc_dung_luc_khoi_dong():
    import agent.main as m
    assert "media_loop(" in inspect.getsource(m.lifespan)


def test_tin_vao_danh_dau_cho_tai():
    from agent.omnichannel.inbox_service import PostgresInboxTransaction

    src = inspect.getsource(PostgresInboxTransaction.insert_attachment)
    assert "media_trang_thai" in src and "trang_thai_ban_dau(" in src


def test_agent_hoi_ban_tren_may_truoc():
    src = (ROOT / "agent" / "omnichannel" / "xu_ly_tin_vao.py").read_text(encoding="utf-8")
    assert "ban_dia=media.ban_dia_theo_url" in src


def test_duong_phuc_vu_tep_dung_kieu_may_chu_nhan_dang():
    from agent.api import hoi_thoai_cu

    src = inspect.getsource(hoi_thoai_cu.attachment_file)
    assert "media_mime" in src and "nosniff" in src and "attachment; filename" in src


def test_hop_thu_dashboard_uu_tien_ban_tren_may():
    src = (ROOT / "agent" / "api" / "inbox.py").read_text(encoding="utf-8")
    assert "WHEN attachment.media_trang_thai = 'da_tai'" in src


def test_media_khong_len_github():
    assert "data/media/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_pdpd_ghi_tham_chieu_TRUOC_khi_xoa_hoi_thoai():
    """Xoá hội thoại xong thì đính kèm đã đi theo CASCADE — không còn đường biết."""
    from agent.core import du_lieu_ca_nhan

    src = inspect.getsource(du_lieu_ca_nhan.xoa)
    assert src.index("tham_chieu_cua(") < src.index("DELETE FROM conversations")
    assert src.index("DELETE FROM conversations") < src.index("xoa_sau_pdpd(")


def test_route_media_deu_khai_quyen():
    from agent.api import media_api

    for r in media_api.router.routes:
        assert "can_quyen" in inspect.getsource(r.endpoint), r.path


def test_dashboard_gan_khung_media():
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "dashboard" / "src" / "25-media.js").read_text(encoding="utf-8")
    assert 'data-gan="ht-sao-luu-media"' in html
    assert 'data-api-cac-nhom="media"' in html
    assert 'GAN_TAB["ht-sao-luu-media"]' in js
    # Dọn LUÔN xem trước rồi mới xoá.
    assert js.index("xem_truoc: true") < js.index("xem_truoc: false")


# ------------------------------------------------------------ sao lưu

def test_sao_luu_gom_media_bo_tep_tam_va_khong_de_ban_ro(tmp_path, monkeypatch):
    from scripts import goi_ma_hoa, sao_luu

    g = tmp_path / "repo"
    (g / "data" / "media" / "2026" / "11" / "ab").mkdir(parents=True)
    (g / "data" / "media" / "2026" / "11" / "ab" / "x.jpg").write_bytes(JPG)
    (g / "data" / "media" / ".tam").mkdir()
    (g / "data" / "media" / ".tam" / "dang-tai.part").write_bytes(b"do dang")
    monkeypatch.setattr(sao_luu, "ROOT", g)
    monkeypatch.setattr(sao_luu.settings, "sao_luu_mat_khau", "mat-khau-thu-dai")
    ok, ghi = sao_luu.sao_luu_tep(tmp_path / "out" / "tep-1.tar.gz")
    assert ok, ghi
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["tep-1.tar.gz.cskh"]
    buf = io.BytesIO()
    with (tmp_path / "out" / "tep-1.tar.gz.cskh").open("rb") as f:
        goi_ma_hoa.giai_ma(f, buf, "mat-khau-thu-dai")
    with tarfile.open(fileobj=io.BytesIO(buf.getvalue()), mode="r:gz") as t:
        ten = set(t.getnames())
    assert "media/2026/11/ab/x.jpg" in ten
    assert not any(".tam" in n for n in ten)


# =====================================================================
#  Postgres thật
# =====================================================================

async def _mo_pool(url: str):
    from agent import db
    from agent.migrations.runner import apply_all

    async def _codec(conn):
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads,
                                  schema="pg_catalog")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=3, init=_codec)
    async with pool.acquire() as conn:
        await conn.execute(LUOC_DO.read_text(encoding="utf-8"))
        await apply_all(conn)
    cu = db._pool
    db._pool = pool
    return pool, cu


def _voi_csdl(url: str, ham):
    from agent import db

    async def chay():
        pool, cu = await _mo_pool(url)
        try:
            return await ham()
        finally:
            db._pool = cu
            await pool.close()
    return asyncio.run(chay())


async def _tai_khoan_kenh() -> UUID:
    from agent import db

    r = await db.fetchrow(
        "INSERT INTO channel_accounts (channel, display_name, status, external_account_id) "
        "VALUES ('webchat','Web','active',$1) RETURNING id", f"web-{uuid4().hex[:8]}")
    return r["id"]


async def _khach_gui(tk: UUID, khach: str, *tep: dict, khoa: str | None = None):
    from agent.channels.base import InboundMessage
    from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository

    m = InboundMessage(
        account_id=tk, channel="webchat", conversation_ref=khach, customer_ref=khach,
        customer_name=khach, text="", dedupe_key=khoa or f"web:{uuid4().hex}",
        received_at=datetime.now(timezone.utc), attachments=list(tep))
    return await InboxService(PostgresInboxRepository()).ingest(m)


async def _chay_worker(bang: dict, n: int = 1):
    async with _client(bang) as c:
        tong: dict[str, int] = {}
        for _ in range(n):
            for k, v in (await media.tai_mot_luot(10, client=c, phan_giai=_cong_khai)).items():
                tong[k] = tong.get(k, 0) + v
        return tong


def test_tai_ve_chong_trung_va_phuc_vu(csdl_kiem_thu, goc):
    """
    Hai khách gửi CÙNG một tấm ảnh -> một tệp trên đĩa, hai đính kèm trỏ vào.
    HTML giả ảnh không được giữ. Tệp không có link được đếm, không biến mất.
    """
    from agent import db

    bang = {"https://cdn.test/a.jpg?oh=1": httpx.Response(200, content=JPG),
            "https://cdn.test/b.jpg?oh=2": httpx.Response(200, content=JPG),
            "https://cdn.test/x.jpg": httpx.Response(200, content=HTML,
                                                     headers={"content-type": "image/jpeg"})}

    async def ham():
        tk = await _tai_khoan_kenh()
        await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/a.jpg?oh=1"},
                         {"loai": "file"})
        await _khach_gui(tk, "hoa", {"loai": "image", "url": "https://cdn.test/b.jpg?oh=2"},
                         {"loai": "image", "url": "https://cdn.test/x.jpg"})
        cho = await db.fetch("SELECT media_trang_thai AS t FROM attachments ORDER BY created_at")
        assert sorted(r["t"] for r in cho) == ["bo_qua", "cho", "cho", "cho"]
        dem = await _chay_worker(bang)
        tep = await db.fetch("SELECT * FROM media_tep")
        dk = await db.fetch("SELECT media_trang_thai, media_sha256, media_loi FROM attachments")
        tq = await media_don.tong_quan()
        ev = await db.fetch("SELECT detail FROM events WHERE kind = 'media.khong_tai_duoc'")
        return dem, tep, dk, tq, ev

    dem, tep, dk, tq, ev = _voi_csdl(csdl_kiem_thu, ham)
    sha = hashlib.sha256(JPG).hexdigest()
    assert dem == {"da_tai": 2, "bo_qua": 1}
    assert len(tep) == 1 and tep[0]["sha256"] == sha and tep[0]["mime_type"] == "image/jpeg"
    assert tep[0]["storage_key"].startswith("data/media/") and tep[0]["storage_key"].endswith(f"/{sha[:2]}/{sha}.jpg")
    assert duong_dan_du_lieu.mo_khoa(tep[0]["storage_key"]).read_bytes() == JPG
    assert sum(1 for r in dk if r["media_sha256"] == sha and r["media_trang_thai"] == "da_tai") == 2
    assert tq["trung_lap"]["so_ban_khong_chep"] == 1 and tq["trung_lap"]["byte_tiet_kiem"] == len(JPG)
    assert tq["trang_thai"] == {"da_tai": 2, "bo_qua": 2}
    # Hỏng thì có ai biết: nhật ký có dòng, và KHÔNG mang query string.
    assert len(ev) == 1 and ev[0]["detail"]["nguon"] == "https://cdn.test/x.jpg"
    assert "oh=" not in json.dumps([e["detail"] for e in ev])
    # Không còn tệp tạm nào nằm lại.
    assert not any((goc / "media" / ".tam").iterdir())


def test_hong_tam_thi_hen_thu_lai_roi_bao_loi(csdl_kiem_thu, goc):
    from agent import db

    async def ham():
        tk = await _tai_khoan_kenh()
        await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/a.jpg"})
        bang = {"https://cdn.test/a.jpg": httpx.Response(503)}
        await _chay_worker(bang)
        r1 = await db.fetchrow("SELECT * FROM attachments")
        for _ in range(media.TOI_DA_LAN_THU):
            await db.execute("UPDATE attachments SET media_thu_lai_luc = now() - interval '1 second'")
            await _chay_worker(bang)
        r2 = await db.fetchrow("SELECT * FROM attachments")
        ev = await db.fetch("SELECT detail FROM events WHERE kind = 'media.khong_tai_duoc'")
        return r1, r2, ev

    r1, r2, ev = _voi_csdl(csdl_kiem_thu, ham)
    assert r1["media_trang_thai"] == "cho" and r1["media_so_lan_thu"] == 1
    assert r1["media_thu_lai_luc"] > datetime.now(timezone.utc)
    assert r2["media_trang_thai"] == "loi" and r2["media_so_lan_thu"] == media.TOI_DA_LAN_THU
    assert len(ev) == 1 and ev[0]["detail"]["trang_thai"] == "loi"


def test_whatsapp_hoi_kenh_lay_link(csdl_kiem_thu, goc):
    """WhatsApp chỉ gửi `provider_media_id`: worker hỏi adapter, tải kèm header."""
    from agent import db

    class _Kenh:
        async def nguon_tai_media(self, tep):
            assert tep["provider_media_id"] == "MID"
            return "https://wa.test/f", {"Authorization": "Bearer t"}

    async def ham():
        tk = await _tai_khoan_kenh()
        await _khach_gui(tk, "lan", {"loai": "image", "provider_media_id": "MID"})
        async with _client({"https://wa.test/f": lambda r: httpx.Response(
                200 if r.headers.get("authorization") == "Bearer t" else 401, content=PNG)}) as c:
            async def lay(_):
                return _Kenh()
            await media.tai_mot_luot(5, client=c, phan_giai=_cong_khai, lay_adapter=lay)
        return await db.fetchrow("SELECT media_trang_thai FROM attachments")

    assert _voi_csdl(csdl_kiem_thu, ham)["media_trang_thai"] == "da_tai"


def test_don_theo_thoi_han_tinh_lan_gui_gan_nhat(csdl_kiem_thu, goc):
    """
    Chống trùng nên "quá hạn" tính theo lần gửi GẦN NHẤT: khách gửi lại tấm
    ảnh cũ hôm nay thì nó sống thêm trọn thời hạn. Xem trước không xoá gì.
    """
    from agent import db

    bang = {"https://cdn.test/a.jpg": httpx.Response(200, content=JPG),
            "https://cdn.test/b.jpg": httpx.Response(200, content=JPG),
            "https://cdn.test/p.png": httpx.Response(200, content=PNG)}

    async def ham():
        tk = await _tai_khoan_kenh()
        await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/a.jpg"})
        await _khach_gui(tk, "hoa", {"loai": "image", "url": "https://cdn.test/b.jpg"})
        await _khach_gui(tk, "mai", {"loai": "image", "url": "https://cdn.test/p.png"})
        await _chay_worker(bang)
        # Ảnh JPG: một lần gửi cũ, một lần gửi mới. Ảnh PNG: chỉ lần cũ.
        await db.execute("UPDATE attachments SET created_at = now() - interval '200 days' "
                         "WHERE url IN ('https://cdn.test/a.jpg', 'https://cdn.test/p.png')")
        xem = await media_don.don(nguon="thu_cong", xem_truoc=True, boi="kt")
        con_sau_xem = (await db.fetchrow("SELECT count(*) AS n FROM media_tep"))["n"]
        that = await media_don.don(nguon="thu_cong", boi="kt")
        tep = await db.fetch("SELECT sha256 FROM media_tep")
        dk = await db.fetch("SELECT url, media_trang_thai, media_sha256 FROM attachments ORDER BY url")
        lan = await db.fetch("SELECT * FROM media_lan_don ORDER BY bat_dau")
        ev = await db.fetch("SELECT kind, detail FROM events WHERE kind LIKE 'media.%don'")
        return xem, con_sau_xem, that, tep, dk, lan, ev

    xem, con_sau_xem, that, tep, dk, lan, ev = _voi_csdl(csdl_kiem_thu, ham)
    assert xem["so_tep_xoa"] == 1 and xem["byte_giai_phong"] == len(PNG)
    assert con_sau_xem == 2, "xem trước đã xoá dữ liệu"
    assert that["so_tep_xoa"] == 1 and that["byte_giai_phong"] == len(PNG)
    assert [r["sha256"] for r in tep] == [hashlib.sha256(JPG).hexdigest()]
    assert {r["url"]: r["media_trang_thai"] for r in dk} == {
        "https://cdn.test/a.jpg": "da_tai", "https://cdn.test/b.jpg": "da_tai",
        "https://cdn.test/p.png": "da_don"}
    assert not list((goc / "media").rglob("*.png"))
    assert [(r["xem_truoc"], r["so_tep_xoa"]) for r in lan] == [(True, 1), (False, 1)]
    assert all(r["xong_luc"] is not None for r in lan)
    assert {e["kind"] for e in ev} == {"media.xem_truoc_don", "media.don"}


def test_don_mo_coi_va_danh_dau_mat_tep(csdl_kiem_thu, goc):
    """
    Tệp không dòng nào nhận -> xoá (khi đủ cũ). Dòng mất tệp -> ĐÁNH DẤU, không
    xoá dòng; chép tệp về lại thì tự hết đánh dấu. Ảnh sản phẩm không bao giờ
    bị đụng. Tệp nhân viên gửi sống cùng hội thoại.
    """
    from agent import db

    cu = time.time() - 3 * 24 * 3600

    def dat(p: Path, noi_dung: bytes, moi: bool = False) -> Path:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(noi_dung)
        if not moi:
            os.utime(p, (cu, cu))
        return p

    mo_coi = dat(goc / "media" / "2026" / "01" / "ff" / ("f" * 64 + ".jpg"), b"mo coi")
    mo_coi_moi = dat(goc / "media" / "2026" / "11" / "ee" / ("e" * 64 + ".jpg"), b"moi", moi=True)
    tam_cu = dat(goc / "media" / ".tam" / "x.part", b"do dang")
    san_pham = dat(goc / "products" / "SP1" / "a.jpg", b"anh san pham")
    up_dung = dat(goc / "uploads" / "dung.png", PNG)
    up_mo_coi = dat(goc / "uploads" / "mo-coi.png", PNG)

    async def ham():
        tk = await _tai_khoan_kenh()
        r = await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/a.jpg"})
        await _chay_worker({"https://cdn.test/a.jpg": httpx.Response(200, content=JPG)})
        await db.execute(
            "INSERT INTO attachments (message_id, ordinal, kind, storage_key) "
            "VALUES ($1, 9, 'image', 'data/uploads/dung.png')", r.message_id)
        tep = duong_dan_du_lieu.mo_khoa((await db.fetchrow("SELECT storage_key FROM media_tep"))["storage_key"])
        tep_bytes = tep.read_bytes()
        tep.unlink()
        kq1 = await media_don.don(nguon="thu_cong")
        d1 = await db.fetchrow("SELECT a.media_trang_thai, mt.mat_tep_luc FROM attachments a "
                               "JOIN media_tep mt ON mt.sha256 = a.media_sha256")
        tep.write_bytes(tep_bytes)
        kq2 = await media_don.don(nguon="thu_cong")
        d2 = await db.fetchrow("SELECT a.media_trang_thai, mt.mat_tep_luc FROM attachments a "
                               "JOIN media_tep mt ON mt.sha256 = a.media_sha256")
        return kq1, d1, kq2, d2

    kq1, d1, kq2, d2 = _voi_csdl(csdl_kiem_thu, ham)
    assert kq1["so_dong_mat_tep"] == 1
    assert d1["media_trang_thai"] == "mat_tep" and d1["mat_tep_luc"] is not None
    assert kq2["tim_lai_tep"] == 1 and d2["media_trang_thai"] == "da_tai" and d2["mat_tep_luc"] is None
    assert kq1["so_mo_coi"] == 3        # mồ côi cũ, tệp tạm cũ, upload mồ côi
    assert not mo_coi.exists() and not tam_cu.exists() and not up_mo_coi.exists()
    assert mo_coi_moi.exists(), "tệp mồ côi vừa ghi (giao dịch chưa xong) bị xoá"
    assert up_dung.exists(), "tệp nhân viên của hội thoại còn sống bị xoá"
    assert san_pham.read_bytes() == b"anh san pham"


def test_pdpd_xoa_media_cua_khach_tru_noi_dung_nguoi_khac_con_giu(csdl_kiem_thu, goc):
    from agent import db

    bang = {"https://cdn.test/chung.jpg": httpx.Response(200, content=JPG),
            "https://cdn.test/rieng.png": httpx.Response(200, content=PNG)}

    async def ham():
        tk = await _tai_khoan_kenh()
        a = await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/chung.jpg"},
                             {"loai": "image", "url": "https://cdn.test/rieng.png"})
        b = await _khach_gui(tk, "hoa", {"loai": "image", "url": "https://cdn.test/chung.jpg"})
        await _chay_worker(bang)
        tc = await media_don.tham_chieu_cua([a.conversation_id])
        await db.execute("DELETE FROM conversations WHERE id = $1", a.conversation_id)
        kq_a = await media_don.xoa_sau_pdpd(tc)
        con_a = await db.fetch("SELECT mime_type FROM media_tep")
        tc = await media_don.tham_chieu_cua([b.conversation_id])
        await db.execute("DELETE FROM conversations WHERE id = $1", b.conversation_id)
        kq_b = await media_don.xoa_sau_pdpd(tc)
        con_b = (await db.fetchrow("SELECT count(*) AS n FROM media_tep"))["n"]
        return kq_a, con_a, kq_b, con_b

    kq_a, con_a, kq_b, con_b = _voi_csdl(csdl_kiem_thu, ham)
    assert kq_a == {"so_tep": 1, "so_byte": len(PNG), "so_loi": 0}
    assert [r["mime_type"] for r in con_a] == ["image/jpeg"], "xoá mất ảnh khách khác còn giữ"
    assert kq_b["so_tep"] == 1 and con_b == 0
    assert not [p for p in (goc / "media").rglob("*") if p.is_file()]


def test_phuc_vu_ban_tren_may_qua_duong_tep_dinh_kem(csdl_kiem_thu, goc):
    """
    Dashboard thấy `url` rỗng khi đã có bản trên máy, và đường phục vụ tệp trả
    đúng byte với kiểu do máy chủ nhận dạng — không phải kiểu khai trong webhook.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent import db
    from agent.api import routes
    from agent.api.inbox import PostgresInboxQueryRepository
    from agent.api.phu_thuoc import bat_buoc_dang_nhap, nguoi_da_dang_nhap
    from tests.conftest import toan_quyen

    async def ham():
        tk = await _tai_khoan_kenh()
        r = await _khach_gui(tk, "lan", {"loai": "image", "url": "https://cdn.test/a.jpg",
                                         "mime_type": "text/html"})
        await _chay_worker({"https://cdn.test/a.jpg": httpx.Response(200, content=JPG)})
        ct = await PostgresInboxQueryRepository().get_conversation(
            conversation_id=r.conversation_id, user_id=uuid4(), is_admin=True)
        return ct["messages"][0]["attachments"][0]

    tep = _voi_csdl(csdl_kiem_thu, ham)
    assert tep["url"] is None and tep["url_goc"] == "https://cdn.test/a.jpg"
    assert tep["media_trang_thai"] == "da_tai"

    app = FastAPI()
    app.include_router(routes.router)
    nguoi = toan_quyen()
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi
    app.dependency_overrides[bat_buoc_dang_nhap] = lambda: nguoi

    @app.on_event("startup")
    async def _mo():
        await _mo_pool(csdl_kiem_thu)

    @app.on_event("shutdown")
    async def _dong():
        await db.close_db()

    with TestClient(app) as k:
        r = k.get(f"/api/attachments/{tep['id']}/file")
    assert r.status_code == 200, r.text
    assert r.content == JPG
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["x-content-type-options"] == "nosniff"
