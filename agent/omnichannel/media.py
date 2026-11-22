"""
Tải media khách gửi về máy chủ — nền, có trần, chống trùng theo sha256.

VÌ SAO CẦN
----------
Rà soát 20.11.2026: ảnh, video, tệp khách gửi CHƯA BAO GIỜ được lưu lại.
`attachments.url` giữ đường CDN của hãng; Facebook ký URL có hạn, Zalo xoá
tệp sau một thời gian. Hết hạn là ảnh vùng da, ảnh hàng vỡ, ảnh chuyển khoản
thành ô vỡ trên dashboard — đúng lúc người ta cần đối chiếu một khiếu nại.
Chủ dự án quyết: tải về, giữ 180 ngày, chống trùng.

KHÔNG BAO GIỜ CHẶN TIN KHÁCH
----------------------------
Tin được lưu TRƯỚC (`inbox_service` chỉ đánh dấu `media_trang_thai='cho'`),
việc tải chạy ở vòng nền riêng. Một CDN chậm hay chết không được làm webhook
chậm, càng không được làm mất tin: cùng nguyên tắc với `anh_khach`.

BỐN CHỐT, MỖI CHỐT MỘT KIỂU HỎNG
--------------------------------
  trần dung lượng  -> đọc theo luồng, dừng ngay khi vượt (video 2GB không
                      được nằm trọn trong RAM rồi mới bị từ chối)
  thời gian        -> hạn từng bước + hạn tổng cho cả lần tải
  kiểu tệp         -> nhận dạng bằng CHỮ KÝ ĐẦU TỆP, không tin header: tệp
                      được phục vụ lại từ chính origin của dashboard, và một
                      trang HTML khai `image/jpeg` là XSS lưu trữ
  địa chỉ đích     -> URL đến từ webhook (webchat là công khai): chặn địa
                      chỉ nội bộ, kể cả sau chuyển hướng, trừ máy Chatwoot đã
                      cấu hình — nếu không, một tin nhắn đủ để máy chủ tự gọi
                      vào 127.0.0.1 hay mạng nội bộ của chính nó

URL KHÔNG VÀO NHẬT KÝ NGUYÊN VĂN
--------------------------------
URL CDN của Facebook mang chữ ký trong query string, URL Graph của WhatsApp
đi kèm token. Mọi chỗ ghi nhật ký dùng `an_url()` (bỏ query, fragment, thông
tin đăng nhập).
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import socket
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from agent import db, duong_dan_du_lieu
from agent.config import settings

_log = logging.getLogger("agent.media")

WORKER = "media-tai"
# Khoá cố vấn của Postgres, không gian riêng cho media: lượt dọn và lượt ghi
# cùng một sha256 phải chạy NỐI TIẾP — xem `ghi_vao_kho` và `media_don`.
KHOA_MEDIA = 426_577_196   # int4: dạng hai khoá của pg_advisory_xact_lock

TOI_DA_LAN_THU = 5
# Dòng `dang_tai` quá ngần này coi như worker chết giữa chừng — nhặt lại.
KET_SAU_GIAY = 600
HAN_TUNG_BUOC = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
# Hạn cho CẢ lần tải: `read=30` là hạn giữa hai gói, một CDN nhỏ giọt mỗi
# 29 giây một gói thì không bao giờ chạm hạn ấy.
HAN_TONG_GIAY = 180.0
TOI_DA_CHUYEN_HUONG = 3
KHOI = 64 * 1024

TRANG_THAI_CUOI = ("da_tai", "loi", "qua_lon", "het_han", "bo_qua", "da_don", "mat_tep")


# ------------------------------------------------------------------ cấu hình

def thu_muc_media() -> Path:
    """Gốc `data/media` — đọc mỗi lần gọi để test đặt lại được `GOC_DU_LIEU`."""
    return duong_dan_du_lieu.GOC_DU_LIEU / "media"


def _so_cau_hinh(khoa: str, mac_dinh: int, thap: int, cao: int) -> int:
    from agent import cau_hinh_dong

    try:
        v = int(str(cau_hinh_dong.lay(khoa) or "").strip())
    except ValueError:
        v = mac_dinh
    return max(thap, min(cao, v))


def luu_ngay() -> int:
    """Thời hạn giữ media (ngày): dashboard trước, `.env` sau, mặc định 180."""
    return _so_cau_hinh("MEDIA_LUU_NGAY", settings.media_luu_ngay, 1, 3650)


def toi_da_byte() -> int:
    return _so_cau_hinh("MEDIA_TOI_DA_MB", settings.media_toi_da_mb, 1, 200) * 1024 * 1024


def an_url(url: str | None) -> str:
    """URL để GHI NHẬT KÝ: bỏ query (chữ ký Facebook), fragment, user:pass."""
    try:
        p = urlsplit(str(url or ""))
    except ValueError:
        return "(url hỏng)"
    host = p.hostname or ""
    if p.port:
        host = f"{host}:{p.port}"
    return urlunsplit((p.scheme, host, p.path, "", ""))[:200]


def _la_http(url: Any) -> bool:
    return str(url or "").lower().startswith(("http://", "https://"))


def nguon_url(tep: Mapping[str, Any]) -> str | None:
    """
    URL nên tải: bản GỐC trước (`original_url`), rồi `url`.

    Chatwoot đặt `url` là đường proxy tương đối `/tich-hop/chatwoot/...` cho
    dashboard, còn bản thật nằm ở `goc` — tải `url` ở đó là tải không được.
    """
    for k in ("original_url", "goc", "url"):
        if _la_http(tep.get(k)):
            return str(tep[k])
    return None


def trang_thai_ban_dau(tep: Mapping[str, Any]) -> str:
    """
    Trạng thái khi tin vừa vào: `cho` nếu có đường tải, `bo_qua` nếu không.

    `bo_qua` thay vì NULL: bảng quản trị phải đếm được "khách gửi tệp mà
    không có link nào để giữ lại", nếu không thì tệp ấy biến mất khỏi mọi
    con số — đúng kiểu hỏng im lặng.
    """
    meta = tep.get("metadata") if isinstance(tep.get("metadata"), Mapping) else {}
    if nguon_url(tep) or nguon_url(meta or {}):
        return "cho"
    if str((meta or {}).get("provider_media_id") or tep.get("provider_media_id") or ""):
        return "cho"
    return "bo_qua"


# ------------------------------------------------------------ nhận dạng tệp

# Kiểu được GIỮ. Danh sách cho phép, không phải danh sách cấm: tệp được phục
# vụ lại từ origin của dashboard, thứ lạ lọt vào là thứ chạy được trong tab
# của người trực.
_VAN_PHONG = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}
_OLE = {"application/msword": ".doc", "application/vnd.ms-excel": ".xls",
        "application/vnd.ms-powerpoint": ".ppt"}


def nhan_dang(dau: bytes, mime_khai: str = "") -> tuple[str, str] | None:
    """(mime, đuôi) theo chữ ký đầu tệp, hoặc None nếu không thuộc danh sách."""
    khai = (mime_khai or "").split(";")[0].strip().lower()
    if dau.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if dau.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if dau[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", ".gif"
    if dau[:4] == b"RIFF" and dau[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if dau[:4] == b"RIFF" and dau[8:12] == b"WAVE":
        return "audio/wav", ".wav"
    if dau[:4] == b"RIFF" and dau[8:12] == b"AVI ":
        return "video/x-msvideo", ".avi"
    if dau[4:8] == b"ftyp":
        nhan = dau[8:12]
        if nhan in (b"heic", b"heix", b"mif1", b"msf1", b"hevc"):
            return "image/heic", ".heic"
        if nhan.startswith(b"M4A"):
            return "audio/mp4", ".m4a"
        if nhan == b"qt  ":
            return "video/quicktime", ".mov"
        if nhan.startswith(b"3g"):
            return "video/3gpp", ".3gp"
        return "video/mp4", ".mp4"
    if dau.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if dau.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm", ".webm"
    if dau.startswith(b"OggS"):
        return "audio/ogg", ".ogg"
    if dau.startswith(b"#!AMR"):
        return "audio/amr", ".amr"
    if dau.startswith(b"ID3"):
        return "audio/mpeg", ".mp3"
    if len(dau) >= 2 and dau[0] == 0xFF and (dau[1] & 0xF6) == 0xF0:
        return "audio/aac", ".aac"
    if len(dau) >= 2 and dau[0] == 0xFF and (dau[1] & 0xE0) == 0xE0:
        return "audio/mpeg", ".mp3"
    if dau.startswith(b"PK\x03\x04"):
        # docx/xlsx/pptx đều là zip; tin kiểu khai nếu nó là văn phòng,
        # còn không thì giữ như zip (tải xuống, không mở trong trình duyệt).
        if khai in _VAN_PHONG:
            return khai, _VAN_PHONG[khai]
        return "application/zip", ".zip"
    if dau.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        if khai in _OLE:
            return khai, _OLE[khai]
        return None
    if khai in ("text/plain", "text/csv") and b"\x00" not in dau:
        return khai, ".txt" if khai == "text/plain" else ".csv"
    return None


# ------------------------------------------------------- chặn địa chỉ nội bộ

PhanGiai = Callable[[str], Awaitable[list[str]]]


async def _phan_giai_dns(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [str(i[4][0]) for i in infos]


def _may_noi_bo_duoc_phep() -> set[str]:
    """
    Máy NỘI BỘ duy nhất được tải: Chatwoot đã cấu hình.

    Chatwoot trả `data_url` trỏ vào chính nó (`http://localhost:3200/...`) —
    chặn cả nó là mất ảnh của cả kênh Chatwoot. Mở theo tên máy ĐÃ CẤU HÌNH,
    không theo dải địa chỉ: mở "localhost" chung chung là mở luôn cổng 8000
    của chính app và cổng 5433 của Postgres.
    """
    ra: set[str] = set()
    goc = str(settings.chatwoot_base_url or "").strip()
    if goc:
        h = urlsplit(goc).hostname
        if h:
            ra.add(h.lower())
    return ra


async def kiem_dich(url: str, phan_giai: PhanGiai | None = None) -> str | None:
    """Lý do KHÔNG được tải URL này, hoặc None nếu được."""
    try:
        p = urlsplit(url)
    except ValueError:
        return "URL hỏng"
    if p.scheme not in ("http", "https"):
        return f"giao thức không cho phép: {p.scheme or 'trống'}"
    host = (p.hostname or "").lower()
    if not host:
        return "URL thiếu tên máy"
    if host in _may_noi_bo_duoc_phep():
        return None
    try:
        dia_chi = [host] if _la_ip(host) else await (phan_giai or _phan_giai_dns)(host)
    except (OSError, UnicodeError) as exc:
        return f"không phân giải được tên máy ({type(exc).__name__})"
    if not dia_chi:
        return "không phân giải được tên máy"
    for a in dia_chi:
        try:
            ip = ipaddress.ip_address(a.split("%")[0])
        except ValueError:
            return "địa chỉ lạ"
        if not ip.is_global:
            return "địa chỉ nội bộ — không tải"
    return None


def _la_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


# ----------------------------------------------------------------- tải về

@dataclass
class KetQuaTai:
    # da_tai | qua_lon | het_han | bo_qua | loi (hỏng hẳn) | thu_lai (hỏng tạm)
    trang_thai: str
    loi: str = ""
    sha256: str = ""
    tam: Path | None = None
    so_byte: int = 0
    mime: str = ""
    duoi: str = ""


def _xoa_tam(p: Path | None) -> None:
    if p is None:
        return
    try:
        p.unlink(missing_ok=True)
    except OSError as exc:
        # Không nổ: lượt dọn quét `.tam` sẽ xoá sau. Nhưng phải ghi lại.
        _log.warning("không xoá được tệp tạm %s: %s", p.name, exc)


async def _tai_mot_dich(url: str, headers: Mapping[str, str], client: httpx.AsyncClient,
                        toi_da: int, phan_giai: PhanGiai | None, mime_khai: str) -> KetQuaTai:
    hien, hdr = url, dict(headers)
    for _ in range(TOI_DA_CHUYEN_HUONG + 1):
        ly_do = await kiem_dich(hien, phan_giai)
        if ly_do:
            return KetQuaTai("bo_qua", ly_do)
        async with client.stream("GET", hien, headers=hdr) as r:
            if r.status_code in (301, 302, 303, 307, 308):
                moi = r.headers.get("location")
                if not moi:
                    return KetQuaTai("loi", f"HTTP {r.status_code} không có Location")
                moi = urljoin(hien, moi)
                # Token WhatsApp chỉ dành cho máy đã cấp nó.
                if urlsplit(moi).hostname != urlsplit(hien).hostname:
                    hdr = {}
                hien = moi
                continue
            if r.status_code in (403, 404, 410):
                return KetQuaTai("het_han", f"HTTP {r.status_code}")
            if r.status_code in (401, 408, 429) or r.status_code >= 500:
                return KetQuaTai("thu_lai", f"HTTP {r.status_code}")
            if r.status_code >= 400:
                return KetQuaTai("loi", f"HTTP {r.status_code}")
            try:
                khai_bao = int(r.headers.get("content-length") or -1)
            except ValueError:
                khai_bao = -1
            if khai_bao > toi_da:
                return KetQuaTai("qua_lon", f"{khai_bao} byte > trần {toi_da}")
            return await _ghi_tam(r, toi_da, mime_khai or r.headers.get("content-type", ""))
    return KetQuaTai("loi", "chuyển hướng quá nhiều lần")


async def _ghi_tam(r: httpx.Response, toi_da: int, mime_khai: str) -> KetQuaTai:
    thu_muc_tam = thu_muc_media() / ".tam"
    thu_muc_tam.mkdir(parents=True, exist_ok=True)
    tam = thu_muc_tam / f"{uuid.uuid4().hex}.part"
    bam = hashlib.sha256()
    n = 0
    dau = b""
    xong = False
    try:
        with tam.open("wb") as f:
            async for khoi in r.aiter_bytes(KHOI):
                n += len(khoi)
                if n > toi_da:
                    return KetQuaTai("qua_lon", f"vượt trần {toi_da} byte khi đang tải")
                if len(dau) < 64:
                    dau += khoi[: 64 - len(dau)]
                bam.update(khoi)
                f.write(khoi)
        if n == 0:
            return KetQuaTai("thu_lai", "tệp rỗng")
        kieu = nhan_dang(dau, mime_khai)
        if kieu is None:
            return KetQuaTai("bo_qua", f"kiểu tệp không cho phép ({(mime_khai or 'không rõ')[:60]})")
        xong = True
        return KetQuaTai("da_tai", sha256=bam.hexdigest(), tam=tam, so_byte=n,
                         mime=kieu[0], duoi=kieu[1])
    finally:
        if not xong:
            _xoa_tam(tam)


async def tai_ve(url: str, *, headers: Mapping[str, str] | None = None,
                 client: httpx.AsyncClient | None = None, toi_da: int | None = None,
                 phan_giai: PhanGiai | None = None, mime_khai: str = "") -> KetQuaTai:
    """Tải một URL về tệp tạm. KHÔNG BAO GIỜ ném — lỗi nằm trong `KetQuaTai`."""
    tu_mo = client is None
    # follow_redirects=False có chủ ý: tự đi từng bước để kiểm địa chỉ đích
    # ở MỖI bước — chuyển hướng là đường vòng SSRF kinh điển.
    client = client or httpx.AsyncClient(timeout=HAN_TUNG_BUOC, follow_redirects=False)
    try:
        return await asyncio.wait_for(
            _tai_mot_dich(url, headers or {}, client, toi_da or toi_da_byte(),
                          phan_giai, mime_khai),
            timeout=HAN_TONG_GIAY)
    except asyncio.TimeoutError:
        return KetQuaTai("thu_lai", f"quá {HAN_TONG_GIAY:.0f} giây")
    except httpx.HTTPError as exc:
        return KetQuaTai("thu_lai", f"{type(exc).__name__}")
    except OSError as exc:
        # Đĩa đầy, không ghi được thư mục — hỏng TẠM, thử lại sau.
        return KetQuaTai("thu_lai", f"{type(exc).__name__}: {exc}"[:200])
    finally:
        if tu_mo:
            await client.aclose()


# ------------------------------------------------------------ ghi vào kho

def duong_dich(sha: str, duoi: str, luc: datetime | None = None) -> tuple[Path, str]:
    """(đường thật, khoá lưu) — `data/media/<yyyy>/<mm>/<sha[:2]>/<sha><đuôi>`."""
    luc = luc or datetime.now(timezone.utc)
    con = f"{luc:%Y}/{luc:%m}/{sha[:2]}/{sha}{duoi}"
    return thu_muc_media().joinpath(*con.split("/")), "data/media/" + con


async def ghi_vao_kho(attachment_id: Any, kq: KetQuaTai) -> bool:
    """
    Chuyển tệp tạm vào kho và gắn đính kèm vào nó. True = dùng lại tệp cũ.

    Dưới khoá cố vấn theo sha256 — CÙNG khoá với lượt dọn: lượt dọn vừa thấy
    "không ai dùng" và đang xoá, còn khách vừa gửi lại đúng tấm ảnh ấy. Không
    nối tiếp hai việc này là đính kèm mới trỏ vào một tệp vừa bị xoá.
    """
    assert kq.tam is not None and kq.sha256
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock($1, hashtext($2))",
                               KHOA_MEDIA, kq.sha256)
            cu = await conn.fetchrow(
                "SELECT storage_key FROM media_tep WHERE sha256 = $1", kq.sha256)
            dung_lai = False
            if cu is not None:
                p = duong_dan_du_lieu.mo_khoa(cu["storage_key"])
                dung_lai = bool(p and p.is_file())
            if dung_lai:
                _xoa_tam(kq.tam)
                await conn.execute(
                    "UPDATE media_tep SET mat_tep_luc = NULL WHERE sha256 = $1", kq.sha256)
            else:
                dich, khoa = duong_dich(kq.sha256, kq.duoi)
                dich.parent.mkdir(parents=True, exist_ok=True)
                os.replace(kq.tam, dich)
                await conn.execute(
                    """
                    INSERT INTO media_tep (sha256, storage_key, mime_type, size_bytes)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (sha256) DO UPDATE SET
                        storage_key = EXCLUDED.storage_key, mime_type = EXCLUDED.mime_type,
                        size_bytes = EXCLUDED.size_bytes, mat_tep_luc = NULL
                    """, kq.sha256, khoa, kq.mime, kq.so_byte)
            await conn.execute(
                """
                UPDATE attachments SET
                    media_trang_thai = 'da_tai', media_sha256 = $2, media_tai_luc = now(),
                    media_loi = NULL, media_thu_lai_luc = NULL,
                    size_bytes = coalesce(size_bytes, $3)
                WHERE id = $1
                """, attachment_id, kq.sha256, kq.so_byte)
    return dung_lai


# ----------------------------------------------------------------- worker

def tre_lan_sau(so_lan: int) -> int:
    """30 giây, 2 phút, 8 phút, 32 phút… trần 1 giờ."""
    return int(min(30 * 4 ** max(0, so_lan - 1), 3600))


_SQL_NHAT = """
WITH chon AS (
    SELECT a.id FROM attachments a
    WHERE (a.media_trang_thai = 'cho'
           AND (a.media_thu_lai_luc IS NULL OR a.media_thu_lai_luc <= now()))
       OR (a.media_trang_thai = 'dang_tai'
           AND a.media_thu_lai_luc < now() - make_interval(secs => $2))
    ORDER BY a.created_at
    LIMIT $1
    FOR UPDATE SKIP LOCKED
)
UPDATE attachments a SET
    media_trang_thai = 'dang_tai', media_thu_lai_luc = now(),
    media_so_lan_thu = a.media_so_lan_thu + 1
FROM chon WHERE a.id = chon.id
RETURNING a.id, a.url, a.original_url, a.mime_type, a.metadata, a.media_so_lan_thu,
    (SELECT c.account_id FROM messages m JOIN conversations c ON c.id = m.conversation_id
     WHERE m.id = a.message_id) AS account_id
"""


async def _ket_thuc(aid: Any, trang_thai: str, loi: str, *, nguon: str = "",
                    ghi_nhat_ky: bool = True) -> None:
    await db.execute(
        "UPDATE attachments SET media_trang_thai = $2, media_loi = $3, "
        "media_thu_lai_luc = NULL WHERE id = $1", aid, trang_thai, (loi or "")[:300] or None)
    if ghi_nhat_ky:
        # Hỏng thì có ai biết không? Có: một dòng nhật ký mỗi tệp KHÔNG giữ
        # được, và bảng quản trị đếm theo trạng thái.
        await db.log_event("media.khong_tai_duoc", trang_thai=trang_thai,
                           ly_do=(loi or "")[:200], nguon=an_url(nguon),
                           attachment_id=str(aid))


async def _hen_thu_lai(aid: Any, so_lan: int, loi: str, nguon: str) -> str:
    if so_lan >= TOI_DA_LAN_THU:
        await _ket_thuc(aid, "loi", f"sau {so_lan} lần: {loi}", nguon=nguon)
        return "loi"
    await db.execute(
        "UPDATE attachments SET media_trang_thai = 'cho', media_loi = $2, "
        "media_thu_lai_luc = now() + make_interval(secs => $3) WHERE id = $1",
        aid, (loi or "")[:300], tre_lan_sau(so_lan))
    return "thu_lai"


async def _lay_adapter(account_id: Any):
    from agent.channels import registry

    return await registry.get_for_account(account_id)


async def xu_ly_mot(dong: Mapping[str, Any], *, client: httpx.AsyncClient | None = None,
                    phan_giai: PhanGiai | None = None,
                    lay_adapter: Callable[[Any], Awaitable[Any]] | None = None) -> str:
    """Tải một đính kèm đã nhặt. Trả trạng thái kết thúc lượt này."""
    aid = dong["id"]
    so_lan = int(dong.get("media_so_lan_thu") or 1)
    meta: Any = dong.get("metadata") or {}
    if isinstance(meta, str):
        # Dòng cũ từng bị mã hoá JSON hai lần (codec db.py đã dumps) — vẫn
        # còn trong CSDL, nên vẫn phải đọc được.
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    if not isinstance(meta, Mapping):
        meta = {}
    url = nguon_url(dong) or nguon_url(meta)
    headers: dict[str, str] = {}
    if url is None:
        if not str(meta.get("provider_media_id") or ""):
            await _ket_thuc(aid, "bo_qua", "không có link tải")
            return "bo_qua"
        if dong.get("account_id") is None:
            await _ket_thuc(aid, "bo_qua", "không rõ tài khoản kênh")
            return "bo_qua"
        try:
            adapter = await (lay_adapter or _lay_adapter)(dong["account_id"])
            nguon = await adapter.nguon_tai_media(dict(meta))
        except Exception as exc:  # noqa: BLE001 — kênh hỏng là hỏng tạm, thử lại
            return await _hen_thu_lai(aid, so_lan, f"hỏi kênh lỗi: {type(exc).__name__}", "")
        if not nguon:
            return await _hen_thu_lai(aid, so_lan, "kênh không trả link tải", "")
        url, headers = nguon[0], dict(nguon[1])
    kq = await tai_ve(url, headers=headers, client=client, phan_giai=phan_giai,
                      mime_khai=str(dong.get("mime_type") or ""))
    if kq.trang_thai == "da_tai":
        try:
            await ghi_vao_kho(aid, kq)
        except Exception:
            _xoa_tam(kq.tam)
            raise
        return "da_tai"
    if kq.trang_thai == "thu_lai":
        return await _hen_thu_lai(aid, so_lan, kq.loi, url)
    await _ket_thuc(aid, kq.trang_thai, kq.loi, nguon=url)
    return kq.trang_thai


async def tai_mot_luot(gioi_han: int = 4, **kw) -> dict[str, int]:
    rows = await db.fetch(_SQL_NHAT, int(gioi_han), KET_SAU_GIAY)
    dem: dict[str, int] = {}
    for r in rows:
        try:
            kq = await xu_ly_mot(r, **kw)
        except Exception as exc:  # noqa: BLE001 — một tệp hỏng không chặn tệp khác
            kq = await _hen_thu_lai(r["id"], int(r.get("media_so_lan_thu") or 1),
                                    f"{type(exc).__name__}: {exc}"[:200], "")
        dem[kq] = dem.get(kq, 0) + 1
    return dem


async def _den_luot_don() -> bool:
    """Lượt dọn tự động gần nhất đã quá 23 giờ (hoặc chưa từng có)."""
    r = await db.fetchrow(
        "SELECT max(bat_dau) AS luc FROM media_lan_don "
        "WHERE nguon = 'tu_dong' AND NOT xem_truoc AND xong_luc IS NOT NULL")
    luc = r.get("luc") if r else None
    return luc is None or (datetime.now(timezone.utc) - luc).total_seconds() > 23 * 3600


async def media_loop(*, worker_id: str, moi_giay: float = 10.0, log_error=None) -> None:
    """
    Vòng nền: tải media đang chờ mỗi `moi_giay`; dọn theo thời hạn mỗi ngày.

    Hỏi "đến lượt dọn chưa" từ BẢNG `media_lan_don`, không từ đồng hồ tiến
    trình: người canh dựng lại app vài lần một ngày, đếm từ lúc khởi động
    thì lượt dọn có thể không bao giờ tới.
    """
    from agent.omnichannel import media_don

    lan = 0
    while True:
        try:
            await tai_mot_luot()
            if lan % 60 == 30 and await _den_luot_don():     # ~5 phút sau khi lên, rồi mỗi 10 phút hỏi lại
                await media_don.don(nguon="tu_dong")
            await db.execute(
                "INSERT INTO worker_heartbeats (worker_name, worker_id, last_seen_at, detail) "
                "VALUES ($2, $1, now(), '{}') ON CONFLICT (worker_name) DO UPDATE "
                "SET worker_id = excluded.worker_id, last_seen_at = excluded.last_seen_at",
                worker_id, WORKER)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng nền phải tự hồi phục
            if log_error is not None:
                await log_error(f"{type(exc).__name__}: {exc}"[:500])
        lan += 1
        await asyncio.sleep(moi_giay)


# ------------------------------------------------- bản trên máy cho agent

async def ban_dia_theo_url(url: str) -> tuple[Path, str] | None:
    """
    (đường tệp, mime) nếu ảnh có URL này ĐÃ có bản trên máy chủ.

    `anh_khach` hỏi trước khi ra mạng: tin được xử lý lại từ hộp thư bền
    sau khi app chết thì link CDN có khi đã chết, còn bản trên máy thì chưa.
    """
    if not url:
        return None
    r = await db.fetchrow(
        "SELECT mt.storage_key, mt.mime_type FROM attachments a "
        "JOIN media_tep mt ON mt.sha256 = a.media_sha256 "
        "WHERE a.media_trang_thai = 'da_tai' AND (a.url = $1 OR a.original_url = $1) "
        "ORDER BY a.created_at DESC LIMIT 1", url)
    if not r:
        return None
    p = duong_dan_du_lieu.mo_khoa(r["storage_key"])
    if p is None or not p.is_file():
        return None
    return p, str(r["mime_type"])
