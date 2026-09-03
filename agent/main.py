"""
Điểm vào duy nhất: webhook kênh + API dashboard + phục vụ giao diện tĩnh.

Chạy:  uvicorn agent.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from contextlib import asynccontextmanager, suppress

from fastapi import BackgroundTasks, FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from agent import db, nhat_ky, runtime
from agent.api.routes import TEN_COOKIE
from agent.api.routes import router as api_router
from agent.api.channel_accounts import router as channel_accounts_router
from agent.api.contacts import router as contacts_router
from agent.api.erp import router as erp_router
from agent.api.routing_admin import router as routing_admin_router
from agent.api.retention import router as retention_router
from agent.api.inbox import router as inbox_router
from agent.api.outbox import router as outbox_router
from agent.api.native_webhooks import router as native_webhooks_router
from agent.api.zalo_personal_webhook import router as zalo_personal_webhook_router
from agent.api.webchat import router as webchat_router
from agent.api.oauth_meta import router as oauth_meta_router
from agent.api import tich_hop
from agent.channels.base import InboundMessage
from agent.channels import chatwoot, messenger
from agent.channels import registry as channels
from agent.channels import zalocrm_accounts as zalo_acc
from agent.config import ROOT, settings
from agent.core import agent as brain
from agent.core import anh_khach
from agent import canh_gac
from agent.core import du_lieu_ca_nhan, gio_lam_viec, xac_thuc
from agent.core import tu_nhien
from agent.publish import registry as pub_registry
from agent.publish import service as post_service
from agent.omnichannel.inbox_service import InboxService, PostgresInboxRepository
from agent.omnichannel.outbox import PostgresOutboxRepository
from agent.omnichannel.outbound_service import (
    OutboundService,
    PostgresOutboundRepository,
    QueuedOutbound,
    handover_idempotency_key,
)
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

HISTORY_TURNS = 12

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
        return True

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
                    await handle_inbound(msg)
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
    from agent.omnichannel.zalo_session_keeper import khoi_phuc_phien_dut

    async def _bao(account_id, ly_do) -> None:
        # Cần NGƯỜI quét QR lại — máy không tự làm được, nên phải đi ra
        # ngoài chứ không chỉ nằm im trong nhật ký.
        await db.log_event(
            "zalo_personal.can_quet_lai",
            actor="system",
            ref_id=account_id,
            ly_do=str(ly_do)[:200],
        )

    # Dựng MỘT lần ngoài vòng lặp: repository không giữ trạng thái, nó chỉ
    # bọc pool dùng chung. Dựng lại mỗi nhịp còn khiến closure `_mo` bắt biến
    # của vòng lặp — thứ ruff bắt đúng (B023) và là mầm lỗi khi mã đổi sau này.
    repository = PostgresAccountRepository()

    async def _mo(account_id):
        from agent.api.channel_accounts import _zalo_personal_adapter
        return await _zalo_personal_adapter(account_id, repository)

    while True:
        try:
            rows = await db.fetch(
                "SELECT id FROM channel_accounts "
                "WHERE channel = $1 AND status <> 'disabled'",
                Channel.ZALO_PERSONAL.value,
            )
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
            if settings.sao_luu_moi_ngay:
                from scripts import sao_luu as bk

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

    Nghị định 13/2023/NĐ-CP Điều 16: dữ liệu chỉ được lưu trong thời hạn
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

    await db.init_db()

    # NẠP CẤU HÌNH ĐÃ LƯU trước khi ghi nhật ký khởi động.
    #
    # Ghi trước khi nạp thì dòng `app.start` báo mode/enabled MẶC ĐỊNH
    # trong khi vài mili giây sau agent chạy bằng cấu hình đã lưu — và
    # người đọc nhật ký để dựng lại sự cố sẽ tin dòng ấy.
    await runtime.nap()

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
    if settings.mcp_token and (_m := getattr(app.state, "mcp_app", None)):
        mcp_ctx = _m.router.lifespan_context(_m)
        await mcp_ctx.__aenter__()
    if poller:
        await db.log_event("poll.start", every_s=settings.zalocrm_poll_seconds)

    yield

    if mcp_ctx is not None:
        with suppress(Exception):
            await mcp_ctx.__aexit__(None, None, None)

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
)


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

    raw = await request.body()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return JSONResponse({"ok": False, "error": "payload không phải JSON"},
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
        cho_phep = request.headers.get("authorization", "") == f"Bearer {khoa}"
        if not cho_phep:
            cho_phep = await xac_thuc.doc_phien(
                request.cookies.get(TEN_COOKIE, "")) is not None
        if not cho_phep:
            return JSONResponse({"error": "Cần token MCP"}, status_code=401)
        return await call_next(request)

    if (duong.startswith("/api/") or duong.startswith("/tich-hop"))             and duong not in _MO:
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
app.include_router(erp_router)
app.include_router(routing_admin_router)
app.include_router(retention_router)
app.include_router(inbox_router)
app.include_router(outbox_router)
app.include_router(native_webhooks_router)
app.include_router(zalo_personal_webhook_router)
app.include_router(webchat_router)
app.include_router(oauth_meta_router)
app.include_router(tich_hop.router)


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

    ad = channels.get("messenger")

    # Đổi quyền hội thoại. Xử lý TRƯỚC tin nhắn: nếu cùng một lô vừa báo
    # "quyền về tay ta" vừa mang tin mới, thì tin ấy phải được agent trả lời
    # chứ không rơi vào nhánh `escalated` của trạng thái cũ.
    for bg in ad.doc_ban_giao(payload):
        tasks.add_task(_ban_giao_messenger, bg, ad.account_id)

    inbound = ad.parse_nhieu(payload)
    for m in inbound:
        tasks.add_task(handle_inbound, m)
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
        )
        if not secrets.compare_digest(supplied, settings.webhook_secret):
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
    inbound = channels.get(kenh).parse_nhieu(payload)
    if not inbound:
        return JSONResponse({"ok": True, "skipped": "không phải tin văn bản đến"})

    # Trả 200 ngay để kênh không retry; xử lý ở nền.
    for m in inbound:
        tasks.add_task(handle_inbound, m)
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


async def _queue_ai_text(
    cid: uuid.UUID,
    text: str,
    idempotency_key: str,
    metadata: dict | None = None,
) -> QueuedOutbound:
    return await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid,
        role="agent",
        text=text,
        idempotency_key=idempotency_key,
        metadata=metadata,
    )


async def _queue_ai_file(
    cid: uuid.UUID,
    path: str,
    caption: str,
    idempotency_key: str,
) -> QueuedOutbound:
    return await OutboundService(PostgresOutboundRepository()).queue_file(
        conversation_id=cid,
        role="agent",
        path=path,
        caption=caption,
        idempotency_key=idempotency_key,
    )


async def _gui_nhu_nguoi(
    _adapter,
    msg,
    cid,
    text: str,
    metadata: dict | None = None,
) -> list[QueuedOutbound]:
    """
    Gửi câu trả lời theo nhịp của một người thật đang nhắn tin.

    Ba việc, theo thứ tự:
      1. Dọn dấu hiệu lộ bot (markdown, chào lại, câu kết sáo rỗng) và tách
         khối dài thành 2-3 tin ngắn — xem agent/core/tu_nhien.py.
      2. Nghỉ giữa các tin đúng khoảng thời gian gõ chừng ấy chữ. Ba tin
         nhảy ra cùng một giây thì dù nội dung có tự nhiên đến mấy, khách
         vẫn biết ngay là máy.
      3. Giữ cờ "đang soạn tin" suốt quá trình để dashboard hiển thị đúng.

    Mỗi phần được ghi message + outbox trong cùng transaction. Provider chỉ
    được gọi bởi worker sau commit; vì thế kết quả ở đây là ``queued``, chưa
    phải ``delivered``.
    """
    lan_dau = await _la_tin_dau(cid)
    # Công tắc `NHIP_NGUOI_THAT` phải THẬT SỰ tắt được.
    #
    # Trước đây nó được khai trong `config.py` kèm chú thích "tắt đi thì gửi
    # một cục" — nhưng không ai đọc, nên tắt cũng không có tác dụng gì. Một
    # công tắc nói dối tệ hơn không có công tắc: người vận hành tưởng đã tắt
    # rồi đi tìm nguyên nhân ở chỗ khác.
    tins = (tu_nhien.lam_tu_nhien(text, lan_dau=lan_dau)
            if settings.nhip_nguoi_that else [text.strip()])
    tins = [t for t in tins if t]
    if not tins:
        return []

    queued: list[QueuedOutbound] = []
    for i, phan in enumerate(tins):
        queued.append(
            await _queue_ai_text(
                cid,
                phan,
                f"ai:{msg.dedupe_key}:part:{i}",
                metadata if i == 0 else None,
            )
        )
    runtime.clear_busy(cid)
    return queued


async def _la_tin_dau(cid) -> bool:
    """Agent đã nói câu nào trong hội thoại này chưa? Quyết định có chào không."""
    r = await db.fetchrow(
        "SELECT count(*) n FROM messages WHERE conversation_id = $1 AND role = 'agent'",
        cid,
    )
    return (r["n"] if r else 0) == 0


async def _ingest_inbound(msg: InboundMessage):
    """Commit inbox trước khi AI hoặc provider bên ngoài được gọi."""
    return await InboxService(PostgresInboxRepository()).ingest(msg)


async def handle_inbound(msg: InboundMessage) -> None:
    """Toàn bộ luồng xử lý một tin nhắn đến."""
    ingested = await _ingest_inbound(msg)
    if ingested.duplicate:
        return
    if ingested.conversation_id is None:
        raise RuntimeError("inbox ingest không trả conversation_id")
    cid: uuid.UUID = ingested.conversation_id
    conv = {
        "id": cid,
        "status": ingested.conversation_status or "auto",
        "mode": ingested.conversation_mode or "auto",
    }

    # TIN VỀ QUA `standby` — người thật đang phụ trách hội thoại này.
    #
    # Meta đã chuyển quyền cho Page Inbox, nghĩa là nhân viên đang trả lời
    # khách ở đó. Tin vẫn phải LƯU để hồ sơ khách không đứt một đoạn, nhưng
    # agent tuyệt đối không được nói chen vào.
    #
    # Đặt cờ `escalated` luôn: nếu hội thoại chưa được đánh dấu (ví dụ quyền
    # bị app khác giành, không đi qua đường chuyển người của ta) thì đây là
    # lần duy nhất hệ thống biết được điều đó.
    if (msg.meta or {}).get("standby"):
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1", cid,
        )
        return

    # Công tắc ngắt, hoặc hội thoại đã do người tiếp quản -> agent đứng ngoài.
    if (
        not runtime.enabled()
        or conv["status"] == "escalated"
        or conv["mode"] == "human"
    ):
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1",
            cid,
        )
        return

    # KHÁCH GỬI ẢNH KHÔNG KÈM CHỮ -> CHUYỂN NGƯỜI, KHÔNG ĐOÁN
    # -------------------------------------------------------
    # Model đang chạy nhìn được ảnh, nhưng đó không phải lý do để nó trả
    # lời. Người ta chụp chỗ da đang có vấn đề thay vì tả bằng lời — và
    # nhìn ảnh da rồi khuyên dùng gì chính là chẩn đoán, đúng việc mà
    # prompt đã cấm và `_bat_buoc_chuyen` đã chặn khi khách MÔ TẢ bằng chữ.
    # Chặn chữ mà bỏ lọt ảnh thì chốt tuân thủ chỉ là hình thức: khách nào
    # gửi ảnh là đi vòng qua được.
    #
    # Ảnh CÓ kèm chữ thì đi đường thường: câu chữ cho agent đủ căn cứ để
    # biết mình có đủ thẩm quyền hay không, và các lớp lưới cũ vẫn chạy.
    if msg.attachments and not msg.text.strip():
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, "
            "outcome = 'escalated', updated_at = now() WHERE id = $1", cid,
        )
        await db.log_event("conversation.escalated", ref_id=cid,
                           reason="khách gửi ảnh không kèm chữ")
        with suppress(Exception):
            await adapter_bao_nguoi(msg, cid)
        return

    history = await _history(cid)

    runtime.mark_busy(cid)          # dashboard vẽ bong bóng "đang soạn tin"
    # Và báo luôn cho kênh, để KHÁCH cũng thấy — không chỉ người vận hành.
    # Màn hình im lặng rồi bỗng hiện ra một đoạn dài là dấu hiệu máy trả
    # lời; thấy "đang soạn tin" thì cảm giác hoàn toàn khác.
    adapter = await channels.get_for_account(msg.account_id)
    with suppress(Exception):
        await adapter.bao_dang_go(msg.conversation_ref, True)
    try:
        # Agent phải BIẾT là có ảnh. Không nói thì nó trả lời câu chữ như
        # thể ảnh không tồn tại — khách gửi ảnh kèm "cái này còn hàng
        # không ạ?" mà nhận về câu hỏi lại "mình muốn hỏi sản phẩm nào ạ?".
        # Agent NHÌN ĐƯỢC ảnh khách gửi.
        #
        # Bản trước nói thẳng với model "[bạn KHÔNG xem được nội dung ảnh]" —
        # trung thực và đúng lúc đó, nhưng nghĩa là mọi ca khách gửi ảnh đều
        # phải chuyển người: ảnh sản phẩm muốn mua, ảnh hàng nhận được bị vỡ,
        # ảnh màn hình chuyển khoản.
        #
        # Tải ảnh hỏng thì rơi về đúng hành vi cũ, không làm đứt lượt trả
        # lời: tin nhắn của khách mới là việc chính.
        cau_hoi = msg.text
        khoi_anh: list[dict] = []
        if msg.attachments:
            async def _ghi_loi_anh(ly_do: str) -> None:
                await db.log_event("anh_khach.tai_that_bai", ref_id=cid,
                                   ly_do=ly_do)

            khoi_anh = await anh_khach.lay_khoi_anh(
                msg.attachments, ghi_loi=_ghi_loi_anh)
            if not khoi_anh:
                cau_hoi = (f"[khách gửi kèm {len(msg.attachments)} tệp nhưng "
                           f"hệ thống KHÔNG tải về xem được] {msg.text}")

        reply = await brain.respond(
            conversation_id=cid, history=history, question=cau_hoi,
            customer_ref=msg.customer_ref, channel=msg.channel,
            anh=khoi_anh or None,
        )
    except Exception as exc:  # noqa: BLE001 — suy giảm êm, không bao giờ im lặng
        await db.execute(
            "UPDATE conversations SET status = 'escalated', mode = 'human', "
            "version = version + 1, updated_at = now() "
            "WHERE id = $1",
            cid,
        )
        await db.log_event("agent.error", ref_id=cid, error=f"{type(exc).__name__}: {exc}")
        return
    finally:
        runtime.clear_busy(cid)
        with suppress(Exception):
            await adapter.bao_dang_go(msg.conversation_ref, False)

    # Chế độ assist: soạn nhưng KHÔNG gửi, chờ người duyệt.
    auto_send = runtime.mode() == "auto" and not reply.escalate
    queued_parts: list[QueuedOutbound] = []
    if auto_send and await adapter.can_send_now(msg.conversation_ref):
        metadata = {
            "grounded": reply.grounded,
            "confidence": reply.confidence,
            "sources": reply.sources,
            "model": reply.model,
            "tokens_in": reply.tokens_in,
            "tokens_out": reply.tokens_out,
            "cache_read": reply.cache_read,
            "cost_usd": reply.cost_usd,
            "latency_ms": reply.latency_ms,
        }
        try:
            queued_parts = await _gui_nhu_nguoi(
                adapter, msg, cid, reply.text, metadata
            )
        except Exception as exc:  # noqa: BLE001 — giữ draft để người gửi tay
            await db.log_event(
                "outbox.enqueue_error",
                ref_id=cid,
                error=f"{type(exc).__name__}: {exc}"[:500],
            )
            queued_parts = []

        # Ảnh đi SAU lời, không đi trước. Nhận ảnh trước khi biết đó là gì
        # thì khách phải tự đoán; nhận lời trước rồi thấy ảnh là đúng thứ
        # tự nhiên của một người bán hàng.
        for i, anh in enumerate(reply.anh_can_gui):
            try:
                await _queue_ai_file(
                    cid,
                    anh["duong_dan"],
                    anh["ten"],
                    f"ai:{msg.dedupe_key}:file:{i}",
                )
            except Exception as exc:  # noqa: BLE001 — một ảnh hỏng không chặn ảnh sau
                await db.log_event(
                    "anh.queue_that_bai", ref_id=cid, ten=anh.get("ten", ""),
                    ly_do=f"{type(exc).__name__}: {exc}"[:200],
                )

    # Chuyển người mà không nói gì với khách là để họ ngồi im không biết có
    # ai thấy tin của mình chưa. Nhân viên thì đã có việc trong hàng chờ,
    # còn khách thì chịu toàn bộ khoảng lặng đó.
    #
    # Gửi câu CỐ ĐỊNH trong cấu hình chứ không gửi lời model vừa sinh ra:
    # lúc chuyển người là lúc agent đã tự nhận không đủ thẩm quyền, nên đó
    # chính là lúc không nên để nó tự chọn chữ. Câu cố định không thể chứa
    # lời khuyên, không thể hứa gì, và không thể vi phạm quảng cáo.
    #
    # Chỉ ở chế độ auto. Chế độ assist thì người duyệt mọi thứ, tự gửi thêm
    # một câu là đi ngược ý nghĩa của chế độ đó.
    elif reply.escalate and runtime.mode() == "auto":
        await bao_khach_dang_chuyen_nguoi(adapter, msg.conversation_ref, cid)

    # Khi đã enqueue, OutboundService đã tạo message cùng transaction với job.
    # Chỉ lưu bản nháp ở đây cho assist/escalate hoặc khi enqueue hỏng.
    stored_draft = not queued_parts
    if stored_draft:
        await db.execute(
            """
            INSERT INTO messages
                (conversation_id, role, content, delivered, direction,
                 delivery_status, grounded, confidence, sources, model,
                 tokens_in, tokens_out, cache_read, cost_usd, latency_ms)
            VALUES (
                $1,'agent',$2,false,'outbound','draft',$3,$4,$5,$6,$7,$8,$9,$10,$11
            )
            """,
            cid,
            reply.text,
            reply.grounded,
            reply.confidence,
            reply.sources,
            reply.model,
            reply.tokens_in,
            reply.tokens_out,
            reply.cache_read,
            reply.cost_usd,
            reply.latency_ms,
        )

    status = (
        "escalated" if reply.escalate else ("auto" if queued_parts else "assist")
    )
    await db.execute(
        """
        UPDATE conversations
        SET cost_usd = cost_usd + $2,
            msg_count = msg_count + $4,
            status = $3,
            mode = CASE
                WHEN $3 = 'escalated' THEN 'human'
                WHEN $3 = 'assist' THEN 'assist'
                ELSE mode
            END,
            version = version + 1,
            outcome = CASE WHEN $3 = 'escalated' THEN 'escalated' ELSE outcome END,
            updated_at = now()
        WHERE id = $1
        """,
        cid,
        reply.cost_usd,
        status,
        1 if stored_draft else 0,
    )

    if reply.escalate:
        await db.log_event(
            "conversation.escalated", ref_id=cid, reason=reply.escalate_reason
        )
        await bao_nhan_vien_tiep_quan(
            adapter, msg.conversation_ref, cid,
            reply.escalate_reason or "agent không xử lý được",
            tom_tat=msg.text[:200],
        )


async def adapter_bao_nguoi(msg: InboundMessage, cid: uuid.UUID) -> None:
    """
    Báo cả hai phía khi chuyển người: khách nhận một câu, nhân viên nhận
    ghi chú trong hộp thư của kênh.

    Tách ra dùng chung vì nhánh "ảnh không kèm chữ" thoát sớm, không đi qua
    đoạn báo chuyển người ở cuối `handle_inbound`. Không gọi ở đây thì khách
    gửi ảnh xong nhận lại đúng sự im lặng — tức là vẫn bị bỏ rơi, chỉ khác
    là nay có bản ghi trong CSDL để sau này truy ra.
    """
    adapter = await channels.get_for_account(msg.account_id)
    await bao_nhan_vien_tiep_quan(
        adapter, msg.conversation_ref, cid, "khách gửi ảnh, cần người xem"
    )
    if runtime.mode() == "auto":
        await bao_khach_dang_chuyen_nguoi(adapter, msg.conversation_ref, cid)


async def bao_khach_dang_chuyen_nguoi(adapter, conversation_ref: str, cid) -> None:
    """
    Nói với KHÁCH rằng việc đang được chuyển cho người. MỘT bản, hai lối gọi.

    VÌ SAO GỘP LẠI THAY VÌ VÁ TỪNG CHỖ
    ----------------------------------
    Trước đây hai nhánh tự viết lấy đoạn này: nhánh tin có chữ, và nhánh tin
    CHỈ CÓ ẢNH. Nhánh có chữ từng gửi hỏng mà nuốt luôn — bắt gặp thật trên
    Chatwoot, hai hội thoại hỏi retinol khi mang thai, khách không nhận được
    dòng nào — nên nó được sửa để ghi nhật ký. Nhánh ảnh thì KHÔNG ai sửa,
    và nó nằm im với `suppress(Exception)` câm thêm một thời gian nữa.

    Đó không phải lỗi của người sửa. Đó là điều luôn xảy ra với hai bản sao
    của cùng một việc: bản ít người đọc hơn sẽ mục. Nên cách sửa đúng không
    phải vá bản thứ hai, mà là bỏ nó đi.

    Câu gửi đi là câu CỐ ĐỊNH trong cấu hình, không phải lời model vừa sinh:
    lúc chuyển người là lúc agent đã tự nhận không đủ thẩm quyền, nên đó
    chính là lúc không nên để nó tự chọn chữ. Câu cố định không thể chứa lời
    khuyên, không thể hứa gì, không thể vi phạm luật quảng cáo.

    Hỏng thì KHÔNG làm sập luồng, nhưng PHẢI để lại dấu vết — người trực còn
    biết mà nhắn tay. Im lặng ở đây nghĩa là khách ngồi chờ một câu trả lời
    không bao giờ tới, và không ai trong nhà biết điều đó đang xảy ra.
    """
    try:
        if not await adapter.can_send_now(conversation_ref):
            await db.log_event(
                "escalate.khong_gui_duoc", ref_id=cid,
                ly_do="kênh từ chối gửi lúc này (ngoài cửa sổ cho phép)",
            )
            return
        # Câu đổi theo giờ: trong giờ thì "sẽ nhắn lại sớm" là thật; ngoài
        # giờ phải nói rõ mấy giờ có người, vì lúc 2 giờ sáng chữ "sớm" là
        # một lời hứa không ai giữ được.
        await _queue_handover_notice(cid, gio_lam_viec.tin_chuyen_nguoi())
    except Exception as exc:  # noqa: BLE001 — không được làm sập luồng
        await db.log_event(
            "escalate.bao_that_bai", ref_id=cid,
            ly_do=f"{type(exc).__name__}: {exc}"[:200],
        )


async def _queue_handover_notice(cid: uuid.UUID, text: str) -> QueuedOutbound:
    conversation = await db.fetchrow(
        "SELECT version FROM conversations WHERE id = $1",
        cid,
    )
    version = int(conversation["version"]) if conversation else 1
    return await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid,
        role="system",
        text=text,
        idempotency_key=handover_idempotency_key(cid, version),
    )


async def bao_nhan_vien_tiep_quan(
    adapter, conversation_ref: str, cid, ly_do: str, tom_tat: str = ""
) -> None:
    """
    Bàn giao nhìn thấy được ở phía kênh — và biết được khi nó hỏng.

    Ghi 'escalated' vào CSDL của mình thôi thì nhân viên đang làm việc trong
    hộp thư của kênh không thấy gì: hội thoại trông như đã xử lý xong, khách
    ngồi chờ, không ai biết. Bàn giao chỉ là bàn giao khi bên nhận nhìn
    thấy — nên khi bước này hỏng, đó là hàng chờ đang rò rỉ, không phải một
    chi tiết trang trí.
    """
    try:
        await adapter.bao_chuyen_nguoi(conversation_ref, ly_do, tom_tat=tom_tat)
    except Exception as exc:  # noqa: BLE001 — không được làm sập luồng
        await db.log_event(
            "escalate.bao_kenh_that_bai", ref_id=cid,
            ly_do=f"{type(exc).__name__}: {exc}"[:200],
        )


async def _history(cid: uuid.UUID) -> list[dict]:
    """Lấy các lượt gần nhất, đã chuẩn hoá cho Messages API."""
    rows = await db.fetch(
        """
        SELECT role, content FROM messages
        WHERE conversation_id = $1 AND role IN ('customer','agent','staff')
        ORDER BY created_at DESC LIMIT $2
        """,
        cid,
        HISTORY_TURNS + 1,
    )
    turns = []
    for r in reversed(rows[1:]):  # bỏ tin vừa lưu, nó sẽ là `question`
        turns.append(
            {
                "role": "user" if r["role"] == "customer" else "assistant",
                "content": r["content"],
            }
        )
    # Messages API yêu cầu lượt đầu là user.
    while turns and turns[0]["role"] != "user":
        turns.pop(0)
    return turns


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

    _mcp_app = _mcp.streamable_http_app(streamable_http_path="/", stateless_http=True)
    app.mount("/mcp", _mcp_app, name="mcp")
    # Cất lại để `lifespan` khởi động được nó. Mount không tự chạy lifespan
    # của app con — đây là chỗ mọi lần mount ASGI lồng nhau bị vấp.
    app.state.mcp_app = _mcp_app

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
