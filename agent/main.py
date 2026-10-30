"""
Điểm vào duy nhất: webhook kênh + API dashboard + phục vụ giao diện tĩnh.

Chạy:  uvicorn agent.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager, suppress
from typing import cast

from fastapi import BackgroundTasks, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from agent import cau_hinh_dong, db, nhat_ky, runtime
from agent.api.routes import TEN_COOKIE
from agent.api.routes import router as api_router
from agent.api.cai_dat_api import router as cai_dat_api_router
from agent.api.phong_thu_agent import router as phong_thu_router
from agent.api.goi_ky_nang import router as goi_ky_nang_router
from agent.api.mcp_may_chu import router as mcp_may_chu_router
from agent.api.quyen import router as quyen_router
from agent.api.tra_loi_nhanh import router as tra_loi_nhanh_router
from agent.api.tu_dong_api import router as tu_dong_router
from agent.api.lich_ca import router as lich_ca_router
from agent.api.hoi_thoai_nhan import router as hoi_thoai_nhan_router
from agent.api.bao_cao_nhan_vien import router as bao_cao_nhan_vien_router
from agent.api.thanh_toan import router as thanh_toan_router
from agent.api.thanh_vien_kenh import router as thanh_vien_kenh_router
from agent.api.channel_accounts import router as channel_accounts_router
from agent.api.contacts import router as contacts_router
from agent.api.contacts import router_vo_chu as khach_vo_chu_router
from agent.api.cong_viec import router as cong_viec_router
from agent.api.ho_so_agent import router as ho_so_agent_router
from agent.api.erp import router as erp_router
from agent.api.routing_admin import router as routing_admin_router
from agent.api.retention import router as retention_router
from agent.api.inbox import router as inbox_router
from agent.api.outbox import router as outbox_router
from agent.api.native_webhooks import router as native_webhooks_router
from agent.api.zalo_personal_webhook import router as zalo_personal_webhook_router

from agent.api.zalo_oa_webhook import router as zalo_oa_webhook_router
from agent.api.xac_thuc_domain import router as xac_thuc_domain_router
from agent.api.webchat import router as webchat_router
from agent.api.oauth_meta import router as oauth_meta_router
from agent.api.oauth_zalo_oa import router as oauth_zalo_oa_router
from agent.api import tich_hop
from agent.channels import chatwoot, messenger
from agent.channels import registry as channels
from agent.omnichannel import xu_ly_tin_vao
from agent.channels import zalocrm_accounts as zalo_acc
from agent.config import ROOT, settings
from agent import canh_gac
from agent import quan_sat
from agent.core import (du_lieu_ca_nhan, quyen, xac_thuc)
from agent.publish import registry as pub_registry
from agent.publish import service as post_service
from agent.omnichannel.outbox import PostgresOutboxRepository
from agent.omnichannel.sla import PostgresSlaRepository, SlaMonitor, sla_loop
from agent.omnichannel.auto_routing import (
    AutoRoutingService,
    AutoRoutingWorker,
    PostgresAutoRoutingRepository,
    auto_routing_loop,
)
from agent.video import worker as video_worker
from agent.workers.outbox_worker import OutboxProcessor, outbox_loop

DASHBOARD_DIR = ROOT / "dashboard"

CHATWOOT_SIGNATURE_MAX_AGE_S = 300


def _chatwoot_signature_hop_le(
    raw_body: bytes, headers, *, now: int | None = None
) -> bool:
    """
    Xác minh chữ ký webhook do chính Chatwoot tạo.

    Secret trong query string lọt vào access log, lịch sử trình duyệt và ảnh
    chụp cấu hình. HMAC giữ secret ở hai đầu, đồng thời timestamp chặn việc
    phát lại một webhook cũ sau khi kẻ khác lấy được payload.
    """
    secret = settings.chatwoot_webhook_secret
    if not secret:
        # Hỏng-ĐÓNG tự thân. Chỗ gọi hiện tại đã kiểm secret trước, nhưng
        # một hàm tên "hợp lệ" mà trả True cho webhook chưa xác minh là bẫy
        # cho người gọi kế tiếp — họ sẽ tin cái tên.
        return False

    timestamp = headers.get("x-chatwoot-timestamp", "")
    supplied = headers.get("x-chatwoot-signature", "")
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    hien_tai = int(time.time()) if now is None else now
    if abs(hien_tai - ts) > CHATWOOT_SIGNATURE_MAX_AGE_S:
        return False

    signed = timestamp.encode() + b"." + raw_body
    expected = "sha256=" + hmac.new(
        secret.encode(), signed, hashlib.sha256
    ).hexdigest()
    return secrets.compare_digest(supplied, expected)


# Vai của tiến trình này. `tat_ca` là mặc định để một máy một tiến trình —
# cách chạy phổ biến nhất — không phải cấu hình thêm gì.
VAI_CO_VONG_NEN = frozenset({"tat_ca", "worker"})


def nen_chay_vong_nen(cau_hinh=settings) -> bool:
    """
    Tiến trình này có được chạy các vòng lặp nền không.

    VÌ SAO CẦN CHIA VAI
    -------------------
    `lifespan` dựng outbox worker, SLA monitor, auto-routing, scheduler,
    dọn dữ liệu, canh gác và backup. Chạy `uvicorn --workers 4` là có bốn
    bộ đầy đủ chạy song song.

    Outbox worker chịu được vì nó claim bằng `FOR UPDATE SKIP LOCKED`.
    Backup loop thì không: nhiều `pg_dump` cùng lúc vừa tốn I/O vừa có thể
    sinh bản sao lưu cắt dở — và bản sao lưu hỏng chỉ lộ ra đúng lúc cần
    phục hồi, tức lúc không sửa được nữa.

    Vai lạ thì trả False: thà một tiến trình không chạy vòng nền (dễ nhận
    ra vì hàng đợi ứ) còn hơn bốn tiến trình cùng chạy (không ai nhận ra).
    """
    return str(getattr(cau_hinh, "vai_tro_tien_trinh", "tat_ca")) in VAI_CO_VONG_NEN


def nen_chay_poller_legacy(cau_hinh=settings) -> bool:
    """
    Có được bật đường nạp tin CŨ không — đòi hỏi ý định tường minh.

    VÌ SAO KHÔNG DÙNG `if settings.zalocrm_api_key` NHƯ TRƯỚC
    ---------------------------------------------------------
    `.env` không đi theo repo, nên không ai dọn nó khi kiến trúc đổi. Một
    khoá cũ còn sót lại là chuyện bình thường; nó KHÔNG có nghĩa người vận
    hành muốn chạy đường cũ.

    Suy ra ý định từ sự tồn tại của cấu hình là cách hệ thống tự bật một
    tính năng mà không ai yêu cầu — ở đây là chạy song song hai đường nạp
    tin, sinh hội thoại trùng, và không có gì báo.

    Tách thành hàm riêng thay vì viết thẳng trong `lifespan` để test được:
    lifespan cần cả vòng đời app mới chạy, nên điều kiện nằm trong đó là
    điều kiện không ai canh.
    """
    return bool(
        getattr(cau_hinh, "legacy_polling_bat", False)
        and cau_hinh.zalocrm_api_key
    )


async def poll_loop() -> None:
    """
    Hỏi ZaloCRM có tin mới không, mỗi vài giây.

    Phải làm thế này vì ZaloCRM chạy webhook qua một chốt chặn SSRF từ chối
    HTTP và mọi địa chỉ loopback/private — tức là không bao giờ gọi được về
    máy local. Giai đoạn 2 (Zalo OA) sẽ là webhook thật; lớp ChannelAdapter
    khiến việc đổi ấy không ảnh hưởng phần còn lại.
    """
    while True:
        try:
            if nen_chay_poller_legacy() and runtime.enabled():
                for msg in await channels.keo_tin_moi():
                    await xu_ly_tin_vao.handle_inbound(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event("poll.error", error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(settings.zalocrm_poll_seconds)


# Chu kỳ kiểm phiên Zalo cá nhân. Đủ thưa để không quấy sidecar, đủ dày để
# một lần restart không làm kênh chết quá lâu.
# Hỏi Meta về hạn token mỗi ngày một lần.
#
# Dày hơn là phí: hạn token đo bằng tuần, không đo bằng phút. Thưa hơn là có
# ngày mất cả một cửa sổ cảnh báo.
KIEM_TOKEN_META_MOI_GIAY = 24 * 3600


async def canh_han_token_meta_loop() -> None:
    """
    Báo TRƯỚC khi Page token hết hạn, thay vì phát hiện sau khi tin ngừng về.

    VÌ SAO KHÔNG THỂ BIẾT NẾU KHÔNG HỎI
    -----------------------------------
    Đo trên tài khoản thật: token dài hạn nên `expires_at = 0` — vĩnh viễn.
    Nhưng `data_access_expires_at` thì CÓ hạn, và sau mốc đó app mất quyền
    đọc dữ liệu trừ khi chủ Trang cấp quyền lại.

    Khi tới hạn, Trang vẫn hiện xanh trên dashboard, webhook vẫn đăng ký —
    chỉ có Graph bắt đầu trả `OAuthException`, tin khách không về nữa, và tin
    gửi đi thì hỏng. Tất cả cùng lúc, không báo trước.

    VÌ SAO CHẠY NGAY LẦN ĐẦU RỒI MỚI NGỦ
    -------------------------------------
    Khởi động lại app là lúc người vận hành đang nhìn màn hình. Ngủ 24 giờ
    trước lần kiểm đầu tiên nghĩa là một token sắp chết vẫn im lặng suốt một
    ngày nữa.
    """
    from agent.channels.suc_khoe_token_meta import NGAY_BAO_TRUOC, hoi_meta
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.accounts import Channel
    from agent.omnichannel.credential_loader import VaultCredentialLoader
    from agent.security.credential_vault import CredentialVault, parse_master_keys

    while True:
        try:
            repo = PostgresAccountRepository()
            vault = CredentialVault(
                parse_master_keys(settings.credential_master_keys),
                active_version=settings.credential_active_key_version,
            )
            loader = VaultCredentialLoader(repo, vault)
            app_id = settings.meta_app_id or settings.messenger_app_id

            for kenh in (Channel.FACEBOOK, Channel.INSTAGRAM):
                for acc in await repo.list_active_by_channel(kenh):
                    creds = await loader.load(acc.id) or {}
                    kq = await hoi_meta(
                        token=str(creds.get("access_token") or ""),
                        app_id=app_id,
                        app_secret=str(creds.get("app_secret") or ""),
                    )
                    # None = không hỏi được. Im lặng có chủ ý: mạng hỏng biến
                    # thành báo động giả thì lần sau người ta bỏ qua cảnh báo
                    # thật.
                    if kq is None or kq["muc"] == "on":
                        continue

                    con = kq.get("ngay_con_lai")
                    await db.log_event(
                        "meta.token_sap_het" if kq["muc"] == "sap_het"
                        else "meta.token_chet",
                        actor="system",
                        tai_khoan=acc.display_name[:80],
                        kenh=kenh.value,
                        ngay_con_lai=round(con, 1) if con is not None else None,
                    )
                    await canh_gac.bao_dong(
                        tieu_de="Token Meta sắp hết hạn",
                        muc_do="chan" if kq["muc"] != "sap_het" else "canh_bao",
                        chi_tiet=f"Token Meta của '{acc.display_name[:60]}' "
                        + (f"còn {con:.0f} ngày — chủ Trang cần cấp quyền lại "
                           f"(báo trước {NGAY_BAO_TRUOC} ngày)"
                           if kq["muc"] == "sap_het"
                           else "ĐÃ HẾT HẠN — Trang này không nhận/gửi tin được nữa"),
                    )
        except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
            await db.log_event("meta.canh_han_token_loi", actor="system",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(KIEM_TOKEN_META_MOI_GIAY)


# Dọn phiên đăng nhập hết hạn mỗi sáu giờ.
#
# `xac_thuc.don_phien_het_han` đã có từ trước và KHÔNG AI GỌI. Phiên hết hạn
# vẫn bị chặn ở SQL (`WHERE het_han > now()`) nên đó không phải lỗ hổng —
# nhưng bảng `phien` phình mãi, và những dòng ấy là chứng chỉ cũ nằm lại
# trong CSDL mà không còn lý do gì để tồn tại.
DON_PHIEN_MOI_GIAY = 6 * 3600


async def don_phien_loop() -> None:
    """Xoá phiên đã hết hạn. Chạy ngay lần đầu rồi mới ngủ."""
    from agent.core import xac_thuc

    while True:
        try:
            n = await xac_thuc.don_phien_het_han()
            if n:
                await db.log_event("phien.don_het_han", actor="system", so_dong=n)
        except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
            await db.log_event("phien.don_loi", actor="system",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(DON_PHIEN_MOI_GIAY)


GIU_PHIEN_ZALO_MOI_GIAY = 60
THU_LAI_KHI_CAN_QUET_GIAY = 1800


async def giu_phien_zalo_loop() -> None:
    """
    Khôi phục phiên Zalo cá nhân bị đứt, mãi mãi.

    VÌ SAO PHẢI LÀ VÒNG LẶP, KHÔNG CHỈ CHẠY MỘT LẦN LÚC KHỞI ĐỘNG
    -------------------------------------------------------------
    Phiên đứt vì nhiều lý do ngoài tầm app: sidecar restart riêng, mạng rớt,
    Zalo tự ngắt thiết bị. Chạy một lần lúc khởi động chỉ vá được một trong
    số đó.

    Không có vòng này thì kênh Zalo chết câm mà mọi đèn vẫn xanh — sidecar
    healthz OK, app OK, thẻ tài khoản vẫn "Sẵn sàng", chỉ tin khách là không
    tới nữa.
    """
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.accounts import Channel
    from agent import canh_gac
    from agent.omnichannel.zalo_session_keeper import (bao_phien_hong, den_luot_thu,
                                                       khoi_phuc_phien_dut)

    # Tài khoản đã báo "lệch bí mật" trong lần chạy này — xem bao_phien_hong.
    da_bao_lech: set = set()

    async def _bao(account_id, ly_do) -> None:
        await bao_phien_hong(
            repository, account_id, ly_do, da_bao_lech=da_bao_lech,
            bao_dong=canh_gac.bao_dong, ghi_nhat_ky=db.log_event)

    # Dựng MỘT lần ngoài vòng lặp: repository không giữ trạng thái, nó chỉ
    # bọc pool dùng chung. Dựng lại mỗi nhịp còn khiến closure `_mo` bắt biến
    # của vòng lặp — thứ ruff bắt đúng (B023) và là mầm lỗi khi mã đổi sau này.
    repository = PostgresAccountRepository()

    async def _mo(account_id):
        from agent.api.channel_accounts import _zalo_personal_adapter
        return await _zalo_personal_adapter(account_id, repository)

    # Thời điểm thử khôi phục gần nhất của tài khoản đã biết là cần quét QR.
    lan_thu_cuoi: dict = {}

    while True:
        try:
            rows = [r for r in await db.fetch(
                "SELECT id, status FROM channel_accounts "
                "WHERE channel = $1 AND status <> 'disabled'",
                Channel.ZALO_PERSONAL.value,
            ) if den_luot_thu(r, lan_thu_cuoi, khoang_giay=THU_LAI_KHI_CAN_QUET_GIAY)]
            if rows:
                ket_qua = await khoi_phuc_phien_dut(
                    [r["id"] for r in rows],
                    _mo,
                    canh_bao=lambda acc, ly_do: asyncio.create_task(_bao(acc, ly_do)),
                )
                if ket_qua["da_khoi_phuc"]:
                    await db.log_event(
                        "zalo_personal.da_khoi_phuc",
                        actor="system",
                        so_tai_khoan=len(ket_qua["da_khoi_phuc"]),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng nền không được chết
            await db.log_event(
                "zalo_personal.giu_phien.error",
                error=f"{type(exc).__name__}: {exc}"[:200],
            )
        await asyncio.sleep(GIU_PHIEN_ZALO_MOI_GIAY)


async def schedule_loop() -> None:
    """
    Đăng những bài ĐÃ DUYỆT và đã tới giờ hẹn.

    Chỉ đụng tới trạng thái `da_len_lich` — bài chưa duyệt không bao giờ
    lọt vào đây, dù có lịch hẹn hay không. Hẹn giờ là tiện lợi, không phải
    đường vòng qua khâu duyệt.
    """
    while True:
        try:
            for row in await post_service.den_gio_dang():
                await post_service.dang_bai(str(row["id"]), boi="lich_hen")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await db.log_event("schedule.error",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(30)


async def backup_loop() -> None:
    """
    Sao lưu CSDL mỗi ngày một lần.

    Đặt trong app chứ không giao cho Task Scheduler của Windows vì lý do rất
    thực tế: việc gì phải nhớ mới làm thì sẽ có ngày không ai nhớ. Sao lưu
    là thứ chỉ có giá trị khi nó chạy đều, và mất dữ liệu là loại hỏng duy
    nhất trong hệ thống này KHÔNG sửa được sau.

    Chạy trong luồng riêng vì `pg_dump` là lời gọi đồng bộ và có thể mất vài
    giây — đủ lâu để làm nghẽn việc trả lời khách nếu chạy thẳng.
    """
    while True:
        try:
            from scripts import sao_luu as bk

            if settings.sao_luu_moi_ngay and await asyncio.to_thread(bk.ban_moi_con_tuoi):
                await asyncio.sleep(3600)   # có bản mới rồi: hẹn kiểm lại sau một giờ
                continue
            if settings.sao_luu_moi_ngay:

                dau = __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).strftime("%Y%m%d-%H%M%S")
                ok, ghi_chu = await asyncio.to_thread(
                    bk.sao_luu_db, bk.KHO / f"db-{dau}.sql.gz"
                )
                await asyncio.to_thread(bk.sao_luu_tai_lieu,
                                        bk.KHO / f"knowledge-{dau}.tar.gz")
                await asyncio.to_thread(bk.don_ban_cu, settings.sao_luu_giu_lai)
                await db.log_event(
                    "backup.done" if ok else "backup.failed", ghi_chu=ghi_chu[:200]
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — vòng lặp nền không được chết
            await db.log_event("backup.error",
                               error=f"{type(exc).__name__}: {exc}"[:200])
        await asyncio.sleep(24 * 3600)


async def don_du_lieu_loop() -> None:
    """
    Dọn hội thoại quá thời hạn lưu trữ, mỗi ngày một lần.

    Luật BVDLCN 91/2025/QH15 Điều 3 khoản 3: dữ liệu chỉ được lưu trong thời hạn
    phù hợp với mục đích đã thông báo. Không có vòng này thì "chính sách
    lưu 180 ngày" chỉ là một dòng trong tài liệu, còn dữ liệu thì nằm đó
    mãi mãi.

    Chạy một lần lúc khởi động rồi cứ 24 giờ một lần. Chỉ đụng hội thoại,
    KHÔNG đụng đơn hàng — chứng từ kế toán có thời hạn riêng dài hơn nhiều.
    """
    while True:
        try:
            if settings.tu_dong_don_du_lieu:
                kq = await du_lieu_ca_nhan.don_theo_thoi_han()
                if kq["da_xoa"]:
                    await db.log_event(
                        "pdpd.auto", so_hoi_thoai=kq["da_xoa"],
                        thoi_han_ngay=kq["thoi_han_ngay"],
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            await db.log_event(
                "pdpd.error", error=f"{type(exc).__name__}: {exc}"[:200]
            )
        await asyncio.sleep(24 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DÒNG ĐẦU TIÊN, trước cả khi nối cơ sở dữ liệu.
    #
    # `httpx` ghi URL đầy đủ kèm query string ở mức INFO, và bộ kiểm sức
    # khoẻ token Meta gọi `debug_token?input_token=…&access_token=…` — hai
    # bí mật vào log mỗi lần canh gác chạy. Cài bộ lọc sau khi có lời gọi
    # đầu tiên là đã muộn.
    nhat_ky.dung_nhat_ky()
    # Sau bộ lọc nhật ký: Sentry dùng cùng bộ che bí mật.
    quan_sat.bat_sentry()

    await db.init_db()

    # NẠP CẤU HÌNH ĐÃ LƯU trước khi ghi nhật ký khởi động.
    #
    # Ghi trước khi nạp thì dòng `app.start` báo mode/enabled MẶC ĐỊNH
    # trong khi vài mili giây sau agent chạy bằng cấu hình đã lưu — và
    # người đọc nhật ký để dựng lại sự cố sẽ tin dòng ấy.
    await runtime.nap()

    # Khoá API nhập từ dashboard. Nạp SAU runtime và TRƯỚC dòng app.start,
    # cùng lý do với runtime: nhật ký khởi động phải nói đúng provider đang chạy.
    await cau_hinh_dong.nap()

    await db.log_event("app.start", mode=runtime.mode(), enabled=runtime.enabled())

    # Nạp tồn kho từ danh mục cho những mã CHƯA có dòng nào.
    #
    # Hàm này đã tồn tại từ lâu với chú thích "chạy một lần khi khởi động",
    # và KHÔNG CÓ GÌ GỌI NÓ. Bảng `ton_kho` trống trong khi danh mục có 22
    # sản phẩm, nên `giu_hang` trả "Mã X không có trong kho" và MỌI đơn agent
    # lên đều hỏng — chức năng chính của hệ thống, hỏng 100%, không một dòng
    # lỗi nào ở đâu.
    #
    # Không ghi đè số đang có (ON CONFLICT DO NOTHING): danh mục là ảnh chụp
    # lúc viết ra, bảng này là số sống. Nhờ vậy chạy mỗi lần khởi động là an
    # toàn, và sản phẩm thêm vào danh mục sau cũng được nạp ở lần khởi động
    # kế tiếp.
    try:
        from agent.core import kho as _kho
        from agent.core import tools as _tools

        _them = await _kho.dong_bo_tu_danh_muc(_tools._catalog().get("san_pham", []))
        if _them:
            await db.log_event("kho.nap_tu_danh_muc", so_ma_moi=_them)
    except Exception as _exc:  # noqa: BLE001 — danh mục hỏng không được chết app
        # Nhưng KHÔNG nuốt im: không có dòng này thì ta quay lại đúng lỗi
        # vừa sửa, chỉ khác nguyên nhân.
        await db.log_event(
            "kho.nap_tu_danh_muc_loi",
            error=f"{type(_exc).__name__}: {_exc}"[:200],
        )

    # Tiến trình chỉ giữ vai "api" thì KHÔNG dựng vòng nền nào — xem
    # `nen_chay_vong_nen`. Gom mọi task nền vào một danh sách để lúc tắt
    # không phải nhớ huỷ từng cái: quên một cái là một vòng lặp sống sót
    # qua shutdown, và không có gì báo.
    # ĐỌC: ══ 12 VÒNG NỀN ĐƯỢC DỰNG Ở ĐÂY ═════════════════════════════════
    # ĐỌC: Hệ thống có ba NHỊP hoạt động khác nhau, và đây là nơi nhịp thứ hai
    # ĐỌC: và thứ ba được khởi động:
    # ĐỌC:
    # ĐỌC:   nhịp 1 · đồng bộ, trước mặt khách  → agent/omnichannel/xu_ly_tin_vao.py:handle_inbound
    # ĐỌC:   nhịp 2 · hàng đợi bền vững         → outbox_loop, video_worker
    # ĐỌC:   nhịp 3 · định kỳ, quan sát         → canh_gac, backup, don_du_lieu
    # ĐỌC:
    # ĐỌC: `chay_nen` là lý do quan trọng: chạy nhiều bản app sau bộ cân bằng
    # ĐỌC: tải thì CHỈ MỘT bản giữ vai chạy vòng nền. Các bản còn lại chỉ phục
    # ĐỌC: vụ HTTP — nếu không thì 5 bản app sẽ cùng nhặt một job outbox.
    tasks_nen: list[asyncio.Task] = []
    chay_nen = nen_chay_vong_nen()

    def _nen(coro):
        """Dựng task nếu tiến trình này giữ vai chạy vòng nền."""
        if not chay_nen:
            # Đóng coroutine chưa chạy, nếu không Python cảnh báo
            # "coroutine was never awaited" ở mọi tiến trình api.
            coro.close()
            return None
        task = asyncio.create_task(coro)
        tasks_nen.append(task)
        return task

    async def log_outbox_error(error: str) -> None:
        await db.log_event("outbox.error", error=error)

    outbox_processor = OutboxProcessor(
        PostgresOutboxRepository(), channels.get_for_account
    )
    _nen(
        outbox_loop(
            outbox_processor,
            worker_id=f"app-{uuid.uuid4()}",
            log_error=log_outbox_error,
        )
    )

    async def log_sla_error(error: str) -> None:
        await db.log_event("sla.error", error=error)

    _nen(
        sla_loop(
            SlaMonitor(PostgresSlaRepository()),
            worker_id=f"sla-{uuid.uuid4()}",
            log_error=log_sla_error,
        )
    )

    async def log_routing_error(error: str) -> None:
        await db.log_event("auto_routing.error", error=error)

    routing_repository = PostgresAutoRoutingRepository()
    _nen(
        auto_routing_loop(
            AutoRoutingWorker(
                routing_repository,
                AutoRoutingService(routing_repository),
            ),
            worker_id=f"routing-{uuid.uuid4()}",
            log_error=log_routing_error,
        )
    )

    poller = None
    if nen_chay_poller_legacy():
        # Nói TO khi chạy đường cũ. Một tính năng di sản chạy im lặng là
        # tính năng không ai nhớ là đang bật, cho tới lúc nó sinh hội thoại
        # trùng và không ai hiểu vì sao.
        await db.log_event(
            "legacy.polling.bat",
            actor="system",
            canh_bao="Đường nạp tin ZaloCRM cũ ĐANG CHẠY song song với "
                     "connector native — chỉ nên bật khi đang migration",
        )
        poller = _nen(poll_loop())
    _nen(schedule_loop())
    _nen(don_du_lieu_loop())
    # Canh gác: phát hiện SUY GIẢM (model chết, kênh mất kết nối, sao
    # lưu cũ). KHÔNG phát hiện được chính tiến trình này chết — lúc đó
    # nó chết theo. Xem scripts/canh_gac_ngoai.py cho trường hợp ấy.
    _nen(canh_gac.vong_canh_gac())
    _nen(canh_han_token_meta_loop())
    _nen(don_phien_loop())
    # Giữ kênh Zalo sống qua mọi lần restart — xem giu_phien_zalo_loop.
    _nen(giu_phien_zalo_loop())
    # Thử lại đơn kẹt `cho_dong_bo`. Vòng này tự bỏ qua khi ERP_GHI_DON tắt,
    # nên dựng nó vô điều kiện là an toàn — và có nó ngay từ đầu nghĩa là
    # ngày bật ghi đơn không phải nhớ bật thêm thứ gì.
    from agent.erp.vong_dong_bo import vong_dong_bo_loop

    _nen(vong_dong_bo_loop())
    # Thợ dựng video: nhặt lại việc dở dang của lần chạy trước rồi chạy tiếp.
    # Không có bước này thì app tắt giữa chừng là video chết cứng ở trạng
    # thái dở, không ai nhặt lại và không dòng lỗi nào.
    video_workers = await video_worker.start() if chay_nen else []
    tasks_nen.extend(video_workers)
    _nen(backup_loop())

    # Vòng đời của MCP phải chạy TRONG vòng đời app, không tự chạy được.
    # Bỏ bước này thì mount xong vẫn ném "Task group is not initialized" ở
    # request đầu tiên — mà lỗi đó chỉ hiện khi có client thật gọi tới, tức
    # là hỏng im lặng cho tới đúng lúc cần dùng.
    mcp_ctx = None
    if settings.mcp_token and (_tao := getattr(app.state, "tao_mcp_app", None)):
        # Bản MỚI cho mỗi lần chạy — xem `tao_mcp_app` về vì sao dùng lại
        # một bản là hỏng từ app thứ hai trở đi trong cùng tiến trình.
        _m = _tao()
        app.state.mcp_app = _m
        mcp_ctx = _m.router.lifespan_context(_m)
        await mcp_ctx.__aenter__()
    if poller:
        await db.log_event("poll.start", every_s=settings.zalocrm_poll_seconds)

    yield

    if mcp_ctx is not None:
        with suppress(Exception):
            await mcp_ctx.__aexit__(None, None, None)
        # Gỡ tham chiếu: app đã tắt thì request tới /mcp phải nổ rõ ràng,
        # không phục vụ bằng một session manager đã đóng.
        app.state.mcp_app = None

    for task in tasks_nen:
        task.cancel()
    for task in tasks_nen:
        with suppress(asyncio.CancelledError):
            await task

    await pub_registry.dong_tat_ca()
    await zalo_acc.aclose()
    await channels.dong_tat_ca()
    await db.close_db()


app = FastAPI(title="Marketing Agent", version="0.1.0", lifespan=lifespan)


# Đường KHÔNG cần đăng nhập. Danh sách ngắn có chủ đích — mỗi mục là một
# quyết định cân nhắc riêng, không phải một tiện lợi.
_MO = (
    "/api/dang-nhap",     # phải vào được mới đăng nhập được
    "/api/dang-xuat",     # đăng xuất luôn phải chạy, kể cả phiên đã hỏng
    # Meta gọi vào đây sau khi người dùng cấp quyền, và Meta KHÔNG mang
    # cookie phiên của ta. Đòi đăng nhập ở đây là luồng OAuth không bao giờ
    # chạy được — nó trả 401 cho chính Meta.
    #
    # Chốt thay thế: `state` dùng một lần, sinh ra ở `/start` (nơi VẪN đòi
    # quyền quản trị). Không có state hợp lệ thì callback từ chối, nên mở
    # đường này không mở thêm quyền gì.
    #
    # Chỉ mở ĐÚNG callback — `/start` không nằm trong danh sách này.
    "/api/connect/meta/callback",
    # Zalo OA, cùng lý lẽ y hệt. Chốt thay thế mạnh hơn một bậc: `state`
    # dùng một lần CỘNG `code_verifier` của PKCE.
    #
    # Thiếu dòng này là luồng nối Zalo OA chết ở 401 — và nó ĐÃ chết như
    # vậy một lần, vì khai miễn trừ ở `quyen.MIEN_TRU` mà quên chốt đăng
    # nhập ở đây. Hai danh sách, hai chốt khác nhau, cùng một đường.
    # `tests/test_chot_ngoai_goi_vao.py` giờ canh cả hai cùng lúc.
    "/api/connect/zalo-oa/callback",
)

# n8n gọi về báo kết quả đăng bài. Đường có THAM SỐ trong path nên không so
# bằng `in _MO` được — phải khớp mẫu.
#
# Bên gọi là một tiến trình, không phải người, nên nó không có cookie phiên.
# Chốt thay thế là vé một lần kiểm NGAY TRONG endpoint — xem
# `agent/publish/service.py::kiem_ve_callback`.
_MO_MAU = (
    re.compile(r"^/api/posts/[0-9a-fA-F-]{36}/callback$"),
)


HANG_VAN_CHUYEN = ("ghn", "ghtk", "mock")


def doc_than_webhook_van_chuyen(raw: bytes, content_type: str) -> dict | None:
    """
    JSON (GHN) hoặc form urlencoded (GHTK). Không đọc được thì None.

    GHTK gửi webhook dạng `application/x-www-form-urlencoded` — tài liệu ghi
    rõ, dù ví dụ thân lại vẽ bằng JSON. Chỉ nhận JSON là trả 400 cho MỌI cập
    nhật trạng thái GHTK, và GHTK chỉ gửi lại một lần rồi bỏ: đơn kẹt ở
    "đang giao" mãi, hoàn kho không bao giờ chạy, không ai biết.
    """
    from urllib.parse import parse_qsl

    if "x-www-form-urlencoded" in content_type.lower():
        try:
            return dict(parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
        except UnicodeDecodeError:
            return None
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


@app.post("/webhook/shipping/{hang}")
async def webhook_shipping(
    request: Request, hang: str = "ghn", token: str = "",
) -> JSONResponse:
    """
    Hãng vận chuyển báo trạng thái vận đơn về đây.

    KHÔNG nằm dưới `/api/` nên không bị middleware đăng nhập chặn — đúng
    thiết kế: hãng vận chuyển không có phiên đăng nhập của ta. Chốt thay
    thế là bí mật trong URL, kiểm ở `shipping.kiem_bi_mat_webhook`, và chưa
    cấu hình thì TỪ CHỐI chứ không cho qua.

    URL khai với hãng có dạng:
        https://<tên miền>/webhook/shipping/ghn?token=<SHIPPING_WEBHOOK_SECRET>
    """
    from agent.shipping import xu_ly_webhook_van_chuyen

    # Hãng LẠ: `get_provider` dựng một provider giả cho mọi tên — để lọt là
    # "/webhook/shipping/abc" đi trọn đường xử lý trên dữ liệu thật.
    if hang not in HANG_VAN_CHUYEN:
        await db.log_event("shipping.webhook_hang_la", hang=hang[:40])
        return JSONResponse({"ok": False, "error": "hãng vận chuyển không có"}, status_code=404)
    raw = await request.body()
    loai_than = request.headers.get("content-type", "")
    payload = doc_than_webhook_van_chuyen(raw, loai_than)
    if payload is None:
        # 400 mà không ghi gì là cập nhật trạng thái mất câm: GHTK chỉ gửi lại
        # MỘT lần rồi bỏ (rà soát 28.10.2026).
        await db.log_event("shipping.webhook_khong_doc_duoc", hang=hang,
                           content_type=loai_than[:80], kich_thuoc=len(raw))
        return JSONResponse({"ok": False, "error": "payload không phải JSON hay form"},
                            status_code=400)

    ket_qua = await xu_ly_webhook_van_chuyen(
        hang, payload, dict(request.headers), query_token=token,
    )
    # Bí mật sai phải trả 401 THẬT, không phải 200 kèm cờ false: hãng vận
    # chuyển và người vận hành đều đọc mã HTTP, và 200 nghĩa là "đã nhận".
    ma_http = int(ket_qua.pop("http_status", 200))
    return JSONResponse(ket_qua, status_code=ma_http)


@app.middleware("http")
async def chan_neu_chua_dang_nhap(request: Request, call_next):
    """
    Chặn mọi /api/* nếu chưa đăng nhập.

    LÀM Ở MIDDLEWARE CHỨ KHÔNG GẮN Depends VÀO TỪNG ENDPOINT — đây là điểm
    quan trọng nhất của cả lớp bảo vệ này.

    Gắn từng endpoint là cơ chế HỎNG-MỞ: hơn bốn mươi endpoint, quên một
    cái là cái đó phơi ra, và không có gì báo. Người thêm endpoint mới tháng
    sau cũng không biết là phải nhớ.

    Middleware là cơ chế HỎNG-ĐÓNG: endpoint mới được bảo vệ theo mặc định,
    và muốn mở thì phải cố ý thêm vào danh sách trên — một việc nhìn thấy
    được khi đọc lại mã.

    `/webhook*` không đi qua đây vì nó không nằm dưới `/api` — nó tự xác
    thực bằng `WEBHOOK_SECRET`, do bên gọi là Chatwoot chứ không phải người.
    `/healthz` để mở để công cụ giám sát hỏi được mà không cần tài khoản.
    """
    duong = request.url.path
    # `/tich-hop/*` chuyển thẳng vào ZaloCRM và Chatwoot, và lớp proxy đó
    # XOÁ header chống nhúng của chúng. Để nó ngoài chốt đăng nhập là biến
    # cổng 8000 thành cửa sau vào cả hai hệ thống — nên nó phải nằm TRONG,
    # cùng một danh sách với /api.
    # MCP: nhận HOẶC phiên dashboard HOẶC bearer token. Client MCP là một
    # ứng dụng khác (Claude Desktop), nó không đăng nhập bằng form được —
    # nhưng để nó vào tự do thì cổng 8000 phát toàn bộ danh mục, đơn hàng
    # và kho tri thức cho bất cứ ai gọi tới.
    if duong.startswith("/mcp"):
        khoa = settings.mcp_token
        if not khoa:
            return JSONResponse({"error": "MCP chưa bật"}, status_code=404)
        # compare_digest chứ không `==`: `==` dừng ở ký tự sai đầu tiên, nên
        # đo thời gian phản hồi là đoán dần được token. Mọi webhook khác
        # trong repo đã so kiểu này; đây là chỗ duy nhất còn sót.
        cho_phep = secrets.compare_digest(
            request.headers.get("authorization", "").encode(),
            f"Bearer {khoa}".encode(),
        )
        if not cho_phep:
            cho_phep = await xac_thuc.doc_phien(
                request.cookies.get(TEN_COOKIE, "")) is not None
        if not cho_phep:
            return JSONResponse({"error": "Cần token MCP"}, status_code=401)
        return await call_next(request)

    if ((duong.startswith("/api/") or duong.startswith("/tich-hop"))
            and duong not in _MO
            and not any(m.match(duong) for m in _MO_MAU)):
        nguoi = await xac_thuc.doc_phien(request.cookies.get(TEN_COOKIE, ""))
        if nguoi is None:
            return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
        # Gắn vào request để endpoint biết AI đang thao tác — nhật ký ghi
        # tên thật thay vì "nguoi" hay "staff" chung chung.
        request.state.nguoi = nguoi
    return await call_next(request)


@app.middleware("http")
async def bat_duong_tuyet_doi(request: Request, call_next):
    """
    SPA nhúng xin asset bằng đường dẫn TUYỆT ĐỐI — chỗ mọi proxy SPA chết.

    Trang Chatwoot tải từ `/tich-hop/chatwoot/` nhưng bên trong nó xin
    `/packs/js/app.js`, đập thẳng vào gốc cổng 8000 nơi `StaticFiles` của
    dashboard đang đợi. Kết quả: 404 hàng loạt, iframe trắng.

    Bám theo `Referer` để biết request lạc thuộc về app nào. Chỉ nhận khi
    Referer trỏ ĐÚNG vào `/tich-hop/<app>/` — không thì đây là request của
    chính dashboard và tuyệt đối không được chuyển đi đâu.

    Đường của hệ thống này (`/api`, `/webhook`, `/healthz`, `/media`) luôn
    được ưu tiên, kể cả khi Referer trỏ vào proxy: dashboard nằm ngoài
    iframe vẫn phải gọi API của chính nó trong lúc iframe đang mở.
    """
    duong = request.url.path
    cua_minh = (duong.startswith(("/api", "/webhook", "/healthz", "/media",
                                  "/tich-hop"))
                or duong == "/" or duong.startswith("/app."))
    if not cua_minh:
        ten = await tich_hop.ung_dung_tu_referer(request.headers.get("referer", ""))
        if ten:
            nguoi = await xac_thuc.doc_phien(request.cookies.get(TEN_COOKIE, ""))
            if nguoi is None:
                return JSONResponse({"error": "Chưa đăng nhập"}, status_code=401)
            return await tich_hop.chuyen_tiep(request, ten, duong)
    return await call_next(request)


@app.websocket("/tich-hop/{ten}/{duong:path}")
async def ws_tich_hop(ws: WebSocket, ten: str, duong: str):
    await tich_hop.cau_websocket(ws, ten, duong)


@app.websocket("/cable")
async def ws_cable(ws: WebSocket):
    """
    Hộp thư Chatwoot sống nhờ ActionCable ở `/cable` — và nó mở WebSocket
    bằng đường TUYỆT ĐỐI, y như asset. Không có đường này thì giao diện vẫn
    mở, vẫn đăng nhập được, nhưng tin nhắn mới KHÔNG bao giờ tự hiện: người
    trực phải bấm F5. Đó là kiểu hỏng tệ nhất — trông như đang chạy.
    """
    await tich_hop.cau_websocket(ws, "chatwoot", "cable")


app.include_router(api_router)
app.include_router(channel_accounts_router)
app.include_router(contacts_router)
app.include_router(khach_vo_chu_router)
app.include_router(cong_viec_router)
app.include_router(ho_so_agent_router)
app.include_router(erp_router)
app.include_router(routing_admin_router)
app.include_router(retention_router)
app.include_router(inbox_router)
app.include_router(outbox_router)
app.include_router(native_webhooks_router)
app.include_router(zalo_personal_webhook_router)
app.include_router(cai_dat_api_router)
app.include_router(phong_thu_router)
app.include_router(goi_ky_nang_router)
app.include_router(mcp_may_chu_router)
app.include_router(quyen_router)
app.include_router(thanh_vien_kenh_router)
app.include_router(zalo_oa_webhook_router)
app.include_router(webchat_router)
app.include_router(oauth_meta_router)
app.include_router(oauth_zalo_oa_router)
app.include_router(tich_hop.router)
app.include_router(tra_loi_nhanh_router)
app.include_router(tu_dong_router)
app.include_router(lich_ca_router)
app.include_router(hoi_thoai_nhan_router)
app.include_router(bao_cao_nhan_vien_router)
app.include_router(thanh_toan_router)
app.include_router(quan_sat.router)

# ĐĂNG KÝ CUỐI CÙNG, có chủ ý: mẫu `/{ten_file}` khớp MỌI đường một
# đoạn. Đặt sớm hơn là nó nuốt cả /healthz, /mcp và trang dashboard.
app.include_router(xac_thuc_domain_router)

# Chốt hỏng-đóng: route chưa khai quyền thì MÁY CHỦ KHÔNG LÊN.
#
# Đặt ở đây chứ không trong middleware vì mỗi endpoint cần một quyền khác
# nhau — không chặn theo tiền tố đường dẫn được như chốt đăng nhập ở dưới.
# Dời chốt sang lúc khởi động giữ nguyên tính hỏng-đóng: quên khai thì nó
# nổ ngay trước mặt người vừa thêm endpoint, không phải một endpoint phơi
# ra lặng lẽ cho tới ngày có người dùng sai quyền.
#
# Phải đặt SAU dòng include_router cuối cùng. Đặt trước là nó quét một app
# chưa có route nào và báo xanh — xanh giả, đúng thứ nó sinh ra để chặn.
quyen.kiem_moi_route_co_quyen(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "runtime": dict(runtime.STATE)}


# ---------------------------------------------------------------
#  Webhook — cửa vào của mọi tin nhắn khách
# ---------------------------------------------------------------

@app.get("/webhook/messenger")
async def webhook_messenger_xac_minh(request: Request):
    """
    Bắt tay lần đầu của Meta: GET kèm `hub.challenge`, chờ dội lại nguyên văn.

    Đường RIÊNG cho Messenger vì Meta không cho thêm header tuỳ ý, nên chốt
    `WEBHOOK_SECRET` chung của repo không áp được. Thay vào đó Meta dùng hai
    cơ chế của riêng họ: verify token cho GET, và chữ ký HMAC cho POST.
    """
    thu_thach = messenger.tra_loi_xac_minh(request.query_params)
    if thu_thach is None:
        # Không dội lại thì Meta báo lỗi cấu hình ngay trên màn hình của họ.
        # Hỏng ỒN ÀO là đúng thứ ta muốn ở bước bắt tay.
        return JSONResponse({"ok": False, "error": "verify token sai"}, status_code=403)
    return PlainTextResponse(thu_thach)


@app.post("/webhook/messenger")
async def webhook_messenger(request: Request, tasks: BackgroundTasks) -> JSONResponse:
    """
    Tin từ Messenger. Xác thực bằng chữ ký HMAC của Meta, không bằng secret chung.

    Chữ ký tính trên THÂN THÔ — `json.dumps()` lại cho ra chuỗi khác về
    khoảng trắng và thứ tự khoá, và HMAC sẽ không bao giờ khớp.
    """
    than = await request.body()
    if not messenger.kiem_chu_ky(than, request.headers.get("x-hub-signature-256", "")):
        # Thiếu app secret cũng rơi vào đây. Cố ý: bỏ qua phép kiểm nghĩa là
        # bất kỳ ai biết địa chỉ này đều bơm được tin giả vào hộp thư cửa
        # hàng, và agent sẽ trả lời chúng như tin thật.
        return JSONResponse({"ok": False, "error": "sai chữ ký"}, status_code=401)

    try:
        payload = json.loads(than)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "payload không phải JSON"}, 400)

    ad = cast(messenger.MessengerAdapter, channels.get("messenger"))

    # Đổi quyền hội thoại. Xử lý TRƯỚC tin nhắn: nếu cùng một lô vừa báo
    # "quyền về tay ta" vừa mang tin mới, thì tin ấy phải được agent trả lời
    # chứ không rơi vào nhánh `escalated` của trạng thái cũ.
    for bg in ad.doc_ban_giao(payload):
        tasks.add_task(_ban_giao_messenger, bg, ad.account_id)

    inbound = ad.parse_nhieu(payload)
    for m in inbound:
        tasks.add_task(xu_ly_tin_vao.handle_inbound, m)
    # Luôn 200: Meta thử lại khi nhận mã khác, và thử lại một payload ta cố
    # ý bỏ qua (tin vọng, sự kiện đã đọc) là vòng lặp không lối ra.
    return JSONResponse({"ok": True, "queued": len(inbound)})


async def _ban_giao_messenger(bg: dict, account_id=None) -> None:
    """
    Quyền hội thoại vừa đổi chủ phía Meta — đồng bộ lại trạng thái bên mình.

    Chiều quan trọng nhất là NHẬN LẠI: nhân viên bấm "Xong" trong Page Inbox
    thì Meta trả quyền về app này. Không nghe sự kiện ấy thì hội thoại nằm
    `escalated` vĩnh viễn — khách nhắn tiếp không ai trả lời, vì nhân viên
    tưởng đã xong còn agent thì tưởng vẫn có người phụ trách. Cả hai bên đều
    tin là bên kia đang lo, và đó là cách khách bị bỏ rơi mà không ai sai.
    """
    conv = await db.fetchrow(
        "SELECT id, status FROM conversations WHERE account_id = $1 "
        "AND external_id = $2",
        account_id or channels.get("messenger").account_id,
        bg["khach"],
    )
    if conv is None:
        return
    if bg["ve_tay_ta"]:
        await db.execute(
            "UPDATE conversations SET status = 'auto', updated_at = now() "
            "WHERE id = $1", conv["id"],
        )
        await db.log_event("banGiao.nhan_lai", ref_id=conv["id"], boi="messenger")
    else:
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1", conv["id"],
        )
        await db.log_event("banGiao.trao_di", ref_id=conv["id"],
                           loai=bg["loai"])


@app.post("/webhook")
@app.post("/webhook/{kenh}")
async def webhook(
    request: Request, tasks: BackgroundTasks, kenh: str = "zalocrm"
) -> JSONResponse:
    """
    Cửa vào chung cho mọi kênh đẩy webhook.

    `/webhook` không có tên kênh vẫn về ZaloCRM để cấu hình cũ không hỏng.
    Chatwoot trỏ về `/webhook/chatwoot`.
    """
    raw_body = await request.body()

    # Bản Chatwoot hiện tại ký HMAC trên timestamp + raw body. Khi cấu hình
    # secret riêng, bắt buộc chữ ký hợp lệ; query token cũ chỉ còn là đường
    # tương thích trong lúc chưa chuyển cấu hình.
    if kenh == "chatwoot" and settings.chatwoot_webhook_secret:
        if not _chatwoot_signature_hop_le(raw_body, request.headers):
            return JSONResponse(
                {"ok": False, "error": "chữ ký Chatwoot không hợp lệ"},
                status_code=401,
            )
    else:
        # CHƯA CẤU HÌNH THÌ TỪ CHỐI, KHÔNG PHẢI CHO QUA.
        #
        # Bản trước viết `elif settings.webhook_secret:` — bí mật trống thì
        # bỏ qua kiểm tra hoàn toàn, và cửa này mở toang cho mọi người trên
        # Internet đẩy tin giả vào hộp thư.
        #
        # Đây là lần thứ BA cùng một khuôn trong repo này: `doc_thach_thuc`
        # của webhook Meta và `kiem_bi_mat_webhook` của vận chuyển đều từng
        # như vậy. Cả ba giờ cùng một luật: danh sách rỗng nghĩa là TỪ CHỐI.
        if not settings.webhook_secret:
            return JSONResponse(
                {"ok": False,
                 "error": "WEBHOOK_SECRET chưa cấu hình — từ chối mọi webhook. "
                          "Sinh bằng: python -m scripts.sinh_token WEBHOOK_SECRET"},
                status_code=503,
            )
        supplied = (
            request.headers.get("x-webhook-secret")
            or request.query_params.get("token", "")
            or ""
        )
        if not secrets.compare_digest(supplied, settings.webhook_secret or ""):
            return JSONResponse({"ok": False, "error": "sai secret"}, status_code=401)

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "payload không phải JSON"}, 400)

    # Hai sự kiện không phải tin khách nhưng quyết định ai đang chịu trách
    # nhiệm: nhân viên vừa trả lời, hoặc hội thoại được mở/giải quyết.
    if kenh == "chatwoot":
        event = payload.get("event")
        if chatwoot.la_tin_nhan_vien(payload) or event == "conversation_status_changed":
            tasks.add_task(
                _xu_ly_su_kien_chatwoot,
                payload,
                channels.get("chatwoot").account_id,
            )
            return JSONResponse({"ok": True, "queued": event})

    # `parse_nhieu` chứ không `parse`: MỘT payload có thể mang NHIỀU tin.
    # Messenger gói `entry[].messaging[]`, khách gõ ba tin liên tiếp thì cả
    # ba về cùng một request. Lấy đúng một tin nghĩa là hai tin sau biến mất
    # trong im lặng. Hai kênh cũ vẫn trả về danh sách một phần tử.
    try:
        adapter = channels.get(kenh)
    except channels.KenhKhongTonTai:
        # Sau khi đã kiểm secret, nên đây là người có quyền nhưng gõ sai tên
        # kênh — trả 404 rõ ràng thay vì lặng lẽ parse bằng adapter khác.
        return JSONResponse(
            {"ok": False, "error": f"kênh {kenh!r} không tồn tại"}, status_code=404
        )
    inbound = adapter.parse_nhieu(payload)
    if not inbound:
        return JSONResponse({"ok": True, "skipped": "không phải tin văn bản đến"})

    # Trả 200 ngay để kênh không retry; xử lý ở nền.
    for m in inbound:
        tasks.add_task(xu_ly_tin_vao.handle_inbound, m)
    return JSONResponse({"ok": True, "queued": len(inbound)})


async def _xu_ly_su_kien_chatwoot(payload: dict, account_id=None) -> None:
    """
    Đồng bộ nửa còn lại của bàn giao người–Agent.

    Agent chuyển việc sang Chatwoot đã có từ trước. Hàm này làm chiều ngược:
    lưu lời nhân viên để lịch sử không đứt, khoá Agent ngay khi người thật
    lên tiếng, và chỉ mở lại khi hội thoại đã resolved rồi được mở lần nữa.
    """
    conversation_ref = chatwoot.ma_hoi_thoai(payload)
    if not conversation_ref:
        await db.log_event("chatwoot.webhook_thieu_hoi_thoai")
        return

    event = payload.get("event")
    if chatwoot.la_tin_nhan_vien(payload):
        message_id = str(payload.get("id") or "")
        if await db.seen_webhook(f"chatwoot:staff:{message_id}"):
            return
        conv = await db.fetchrow(
            "SELECT id FROM conversations WHERE account_id = $1 "
            "AND external_id = $2",
            account_id or channels.get("chatwoot").account_id,
            conversation_ref,
        )
        if conv is None:
            await db.log_event(
                "chatwoot.staff_khong_co_hoi_thoai",
                external_id=conversation_ref,
                message_id=message_id,
            )
            return

        content = str(payload.get("content") or "").strip()
        if not content and payload.get("attachments"):
            content = f"[Nhân viên gửi {len(payload['attachments'])} tệp]"
        if content:
            await db.execute(
                "INSERT INTO messages (conversation_id, role, content, delivered) "
                "VALUES ($1,'staff',$2,TRUE)",
                conv["id"],
                content,
            )
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, "
            "outcome = 'escalated', msg_count = msg_count + $2, "
            "updated_at = now() WHERE id = $1",
            conv["id"],
            1 if content else 0,
        )
        sender = payload.get("sender") or {}
        await db.log_event(
            "chatwoot.staff_takeover",
            actor="staff",
            ref_id=conv["id"],
            ten=str(sender.get("name") or "")[:100],
        )
        return

    if event != "conversation_status_changed":
        return
    status = str(payload.get("status") or "")
    marker = payload.get("updated_at") or payload.get("timestamp") or ""
    if await db.seen_webhook(
        f"chatwoot:status:{conversation_ref}:{status}:{marker}"
    ):
        return

    if status == "resolved":
        conv = await db.fetchrow(
            "UPDATE conversations SET status = 'closed', outcome = 'resolved', "
            "updated_at = now() WHERE account_id = $1 AND external_id = $2 "
            "RETURNING id",
            account_id or channels.get("chatwoot").account_id,
            conversation_ref,
        )
        if conv:
            await db.log_event(
                "chatwoot.resolved", actor="staff", ref_id=conv["id"]
            )
    elif status == "open":
        # Chỉ hội thoại do người trực ĐÃ giải quyết mới tự trả về Agent.
        # Một hội thoại đang escalated mà nhân viên chỉ mở ra xem vẫn phải
        # nằm trong tay người; mở khoá ở đó sẽ tạo hai giọng nói cùng lúc.
        conv = await db.fetchrow(
            "UPDATE conversations SET status = 'auto', outcome = NULL, "
            "updated_at = now() WHERE account_id = $1 AND external_id = $2 "
            "AND status = 'closed' RETURNING id",
            account_id or channels.get("chatwoot").account_id,
            conversation_ref,
        )
        if conv:
            await db.log_event(
                "chatwoot.agent_nhan_lai", ref_id=conv["id"]
            )




# ---------------------------------------------------------------
#  Giao diện
# ---------------------------------------------------------------

# Video tĩnh — n8n và Instagram Graph API cần TẢI ĐƯỢC file qua HTTP,
# không nhận đường dẫn ổ đĩa. Phải mount TRƯỚC "/" vì mount "/" nuốt hết.
_VIDEO_DIR = settings.video_out_path
if _VIDEO_DIR.exists():
    app.mount("/media/videos",
              StaticFiles(directory=str(_VIDEO_DIR)), name="media-videos")

@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def _mcp_them_gach_cheo(request: Request):
    """
    `/mcp` và `/mcp/` phải chạy như nhau.

    Mount ASGI chỉ nhận đúng đường có gạch chéo cuối; POST vào `/mcp` trả
    405 Method Not Allowed. Người cấu hình Claude Desktop gõ thiếu một ký
    tự sẽ nhận đúng lỗi đó, và 405 không gợi ra được là thiếu gạch chéo.

    307 chứ không phải 302: chỉ 307 mới giữ nguyên method và thân request.
    302 biến POST thành GET và mọi lời gọi công cụ mất sạch tham số.
    """
    from fastapi.responses import RedirectResponse

    duoi = f"?{request.url.query}" if request.url.query else ""
    return RedirectResponse(f"/mcp/{duoi}", status_code=307)


# MCP trên CHÍNH cổng 8000 — không còn tiến trình riêng ở 8765.
#
# `agent/mcp_server.py` vẫn chạy độc lập được bằng stdio cho Claude Desktop;
# lối này là cho client HTTP, và nó đi qua đúng lớp bảo vệ của dashboard
# thay vì tự phơi ra một cổng không có xác thực nào.
#
# Mount TRƯỚC "/" vì mount "/" nuốt hết.
if settings.mcp_token:
    from agent.mcp_server import mcp as _mcp

    def tao_mcp_app():
        """
        Dựng MỘT app MCP MỚI. Gọi lại mỗi lần lifespan khởi động.

        VÌ SAO KHÔNG DÙNG LẠI MỘT BẢN DUY NHẤT
        --------------------------------------
        `StreamableHTTPSessionManager.run()` chỉ chạy được ĐÚNG MỘT LẦN cho
        mỗi thể hiện; lần thứ hai nó ném
        "run() can only be called once per instance".

        Sản xuất không thấy lỗi này vì lifespan chỉ chạy một lần rồi tiến
        trình sống mãi. Nhưng bộ test thì dựng app nhiều lần trong CÙNG một
        tiến trình, nên từ app thứ hai trở đi mọi test dùng lifespan đều
        ERROR.

        ĐO ĐƯỢC 22.09.2026 trên `HEAD` chưa sửa gì: `pytest
        tests/test_thanh_vien_kenh.py` với Postgres thật cho 9 passed,
        4 errors — toàn bộ là lỗi này. Nó ẩn suốt vì ở máy phát triển các
        test ấy bị bỏ qua do thiếu `TEST_DATABASE_URL`.

        Dựng mới mỗi lần là đúng cả hai phía: sản xuất vẫn một lần, test
        được bao nhiêu lần cũng sạch.
        """
        return _mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)

    class _McpChuyenTiep:
        """
        Chuyển tiếp sang app MCP ĐANG hiệu lực.

        Mount giữ tham chiếu cố định tới đối tượng lúc mount, nên nếu mount
        thẳng app MCP thì việc dựng bản mới ở lifespan vô nghĩa — mount vẫn
        phục vụ bản cũ. Lớp mỏng này đọc `app.state.mcp_app` tại thời điểm
        có request, nên luôn trỏ đúng bản vừa dựng.
        """

        async def __call__(self, scope, receive, send):
            con = getattr(app.state, "mcp_app", None)
            if con is None:
                # Nổ to chứ không trả 404 im lặng: 404 ở đây trông y hệt
                # "sai đường dẫn", và người ta sẽ đi sửa URL thay vì sửa
                # vòng đời.
                raise RuntimeError(
                    "MCP chưa khởi động: lifespan của app chưa chạy, hoặc "
                    "đã tắt. Đây là lỗi vòng đời, không phải sai đường dẫn."
                )
            await con(scope, receive, send)

    app.mount("/mcp", _McpChuyenTiep(), name="mcp")
    # Chưa dựng app con ở đây — `lifespan` dựng, vì mỗi lần chạy cần một bản
    # riêng. Mount không tự chạy lifespan của app con; đó là chỗ mọi lần
    # mount ASGI lồng nhau bị vấp.
    app.state.mcp_app = None
    app.state.tao_mcp_app = tao_mcp_app

class _GiaoDienLuonHoiLai(StaticFiles):
    """`StaticFiles` nhưng bắt trình duyệt hỏi lại trước khi dùng bản đệm.

    VÌ SAO CẦN
    ----------
    `StaticFiles` gửi `ETag` và `Last-Modified` nhưng KHÔNG gửi
    `Cache-Control`. Thiếu header đó, trình duyệt tự suy diễn thời gian sống
    (thường là 10% khoảng cách từ `Last-Modified`) và phục vụ `app.js` từ bộ
    đệm mà không hỏi lại máy chủ.

    Đã gặp thật: máy chủ phục vụ bản mới, đĩa có bản mới, mà trình duyệt vẫn
    chạy bản cũ kể cả sau `location.reload()`. Nghĩa là mọi bản vá đều không
    tới tay người trực cho tới khi họ tình cờ Ctrl+F5 — sửa xong một lỗi rồi
    tưởng đã xong, trong khi người dùng vẫn đang gặp đúng lỗi đó.

    `no-cache` KHÔNG phải "đừng lưu đệm". Nó là "lưu được, nhưng phải hỏi lại
    trước khi dùng". ETag vẫn còn nên lần hỏi lại trả 304 rỗng — gần như
    miễn phí, và luôn đúng bản.

    Video KHÔNG đi qua lớp này: chúng bất biến sau khi dựng và nặng hàng
    megabyte, bắt hỏi lại mỗi lần là đốt băng thông cho một câu trả lời luôn
    giống nhau.
    """

    def file_response(self, *args, **kwargs):  # noqa: D102
        res = super().file_response(*args, **kwargs)
        res.headers["Cache-Control"] = "no-cache"
        return res


if DASHBOARD_DIR.exists():
    app.mount("/", _GiaoDienLuonHoiLai(directory=str(DASHBOARD_DIR), html=True),
              name="dashboard")
