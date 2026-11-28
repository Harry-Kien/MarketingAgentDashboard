"""
Giữ phiên Zalo cá nhân sống qua mọi lần khởi động lại.

VẤN ĐỀ LỚP NÀY GIẢI
-------------------
Phiên Zalo sống trong RAM của sidecar. Khởi động lại sidecar, khởi động lại
máy chủ, hay deploy một bản mới — phiên biến mất.

Vault vẫn giữ `session` đã mã hoá, và sidecar vẫn có endpoint
`restore-session`. Thứ thiếu là một chỗ GỌI nó.

Không có lớp này thì kênh Zalo chết câm sau mỗi lần restart: sidecar vẫn
`healthz` xanh, app vẫn xanh, thẻ tài khoản trên dashboard vẫn "Sẵn sàng" —
chỉ có tin khách là rơi vào hư không. Đây là kiểu hỏng tệ nhất trong hệ
thống này: mọi đèn đều xanh trong khi khách nhắn mà không ai nhận.

VÌ SAO KHÔNG KHÔI PHỤC VÔ ĐIỀU KIỆN
-----------------------------------
Gọi `restore-session` lên một phiên đang chạy là tự tay ngắt kết nối đang
tốt: `restore` dựng lại listener từ đầu, và khoảng giữa lúc ngắt và lúc nối
lại là khoảng tin khách rơi mất. Nên phải hỏi trạng thái trước.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any

# Trạng thái sidecar coi là còn sống. Mọi giá trị khác đều đáng khôi phục,
# kể cả giá trị lạ: thà dựng lại một phiên còn tốt (mất vài giây) còn hơn để
# một phiên chết nằm im (mất mọi tin khách cho tới khi ai đó phát hiện).
CON_SONG = frozenset({"connected"})

# Đầu chuỗi lý do khi sidecar từ chối CHỮ KÝ. Đây không phải "hết phiên":
# quét QR lại không chữa được, chỉ đồng bộ lại bí mật mới chữa được. Đo
# được 04.09.2026: 1866 sự kiện "cần quét QR lại" với đúng lý do này.
DAU_LECH_BI_MAT = "LỆCH BÍ MẬT SIDECAR"

# Đầu chuỗi lý do khi KHÔNG VỚI TỚI sidecar (hoặc sidecar không với tới
# Zalo). Cũng KHÔNG phải "hết phiên": phiên vẫn nằm nguyên trong vault, chỉ
# là chưa gọi được. Đo trên CSDL thật: 2015 sự kiện `ConnectError: sidecar
# không phản hồi` bị ghi `can_quet_lai` — tài khoản bị đổi sang
# REAUTH_REQUIRED và việc khôi phục bị hoãn 30 phút, nên khi sidecar sống
# lại, kênh vẫn nằm chết thêm nửa giờ và dashboard bảo người đi quét QR vô
# ích.
DAU_SIDECAR_KHONG_TOI = "SIDECAR KHÔNG TỚI"
BAO_KHONG_TOI_MOI_GIAY = 3600

# Dấu hiệu lỗi MẠNG (httpx phía app, fetch/undici phía sidecar). Đối chiếu
# chuỗi vì lỗi tới đây đã qua `RuntimeError(delivery.detail)` của adapter —
# kiểu ngoại lệ gốc đã mất.
_DAU_LOI_MANG = (
    "sidecar không phản hồi",       # ZaloPersonalAdapter._request bắt httpx.HTTPError
    "ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout",
    "PoolTimeout", "RemoteProtocolError", "ReadError", "NetworkError",
    "fetch failed", "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENOTFOUND",
    "EAI_AGAIN", "socket hang up", "sidecar HTTP 5",
)


def la_loi_mang(ly_do: str) -> bool:
    """Lỗi là do KHÔNG VỚI TỚI (sidecar/Zalo), không phải do mất đăng nhập."""
    s = str(ly_do)
    return s.startswith(DAU_SIDECAR_KHONG_TOI) or any(d in s for d in _DAU_LOI_MANG)


def den_luot_thu(row, lan_thu_cuoi: dict, *, khoang_giay: float, bay_gio: float | None = None) -> bool:
    """
    Tài khoản này có tới lượt thử khôi phục chưa.

    Tài khoản đã biết là cần quét QR (`reauth_required`) chỉ được thử THƯA:
    mỗi lần thử là một lần đăng nhập hỏng bằng phiên Zalo đã huỷ, sáu mươi
    lần một giờ trông như máy dò mật khẩu. Vẫn thử — có lúc Zalo trả phiên
    lại — chỉ không dồn dập. Tài khoản khác: lượt nào cũng thử.
    """
    import time

    if row["status"] != "reauth_required":
        return True
    nay = time.monotonic() if bay_gio is None else bay_gio
    truoc = lan_thu_cuoi.get(row["id"])
    if truoc is not None and nay - truoc < khoang_giay:
        return False
    lan_thu_cuoi[row["id"]] = nay
    return True


async def bao_phien_hong(
    repository, account_id, ly_do: str, *,
    da_bao_lech: set,
    bao_dong: Callable[..., Awaitable[None]],
    ghi_nhat_ky: Callable[..., Awaitable[None]],
    da_bao_khong_toi: dict | None = None,
    bay_gio: float | None = None,
) -> bool:
    """
    Cần NGƯỜI làm gì đó cho một nick Zalo — máy không tự làm được. Trả đã
    báo lần này chưa (False = đã báo từ trước, im lặng).

    Hai bệnh khác nhau mang hai tên: đo được 04.09.2026, 1866 sự kiện
    `can_quet_lai` mà bệnh thật là bí mật HMAC lệch với `.env` — quét QR
    bao nhiêu lần cũng không chữa được.

    BÁO MỘT LẦN, ĐỔI TRẠNG THÁI KÊNH (rà soát 29.10.2026)
    ------------------------------------------------------
    Bản trước chỉ ghi một dòng nhật ký MỖI PHÚT. Đo trên máy thật: cả hai
    nick Zalo mất phiên từ ít nhất 22.10, 542 dòng "cần quét QR" mỗi ngày,
    không một tin báo nào ra ngoài, tài khoản vẫn hiện `active` — Zalo chết
    cả tháng mà dashboard, bảng sẵn sàng, canh gác đều xanh.

    Nay: lần ĐẦU phát hiện thì chuyển tài khoản sang `reauth_required`
    (dashboard hiện "cần nối lại", màn sức khoẻ đếm "cần xử lý"), ghi một
    dòng nhật ký, gửi một báo động. Những lượt sau im lặng — tới khi quét QR
    xong (sidecar báo `connected` → webhook đặt lại `active`).

    Lệch bí mật KHÔNG đổi trạng thái tài khoản: phiên Zalo vẫn tốt, chỉ
    sidecar cần khởi động lại; nhớ trong bộ nhớ (`da_bao_lech`) là đủ.

    KHÔNG VỚI TỚI sidecar (lỗi mạng, sidecar đang khởi động lại) cũng KHÔNG
    đổi trạng thái và KHÔNG hoãn lượt thử: nhịp sau thử lại như thường.
    Ghi sự kiện riêng `zalo_personal.sidecar_khong_toi` và báo động — tối
    đa một lần mỗi giờ mỗi nick (`da_bao_khong_toi`), vì sidecar chết lâu
    thì vẫn phải có người biết, nhưng không phải sáu mươi lần một giờ.
    """
    import time

    from agent.omnichannel.accounts import AccountStatus
    from agent.omnichannel.credential_loader import SYSTEM_ACTOR_ID

    tk = await repository.get(account_id)
    ten = getattr(tk, "display_name", None) or str(account_id)
    if la_loi_mang(ly_do):
        nho = da_bao_khong_toi if da_bao_khong_toi is not None else {}
        nay = time.monotonic() if bay_gio is None else bay_gio
        truoc = nho.get(account_id)
        if truoc is not None and nay - truoc < BAO_KHONG_TOI_MOI_GIAY:
            return False
        nho[account_id] = nay
        await ghi_nhat_ky("zalo_personal.sidecar_khong_toi", actor="system",
                          ref_id=account_id, ly_do=str(ly_do)[:200])
        await bao_dong(
            f"Zalo cá nhân «{ten}»: app KHÔNG gọi được sidecar ({str(ly_do)[:120]}). "
            "Phiên vẫn còn — KHÔNG cần quét QR. Kiểm sidecar: "
            "python -m scripts.chay_sidecar_zalo",
            tieu_de="Sidecar Zalo không phản hồi", muc_do="hong")
        return True

    lech = str(ly_do).startswith(DAU_LECH_BI_MAT)
    if lech:
        if account_id in da_bao_lech:
            return False
        da_bao_lech.add(account_id)
    else:
        if tk is None or tk.status == AccountStatus.REAUTH_REQUIRED:
            return False
        await repository.record_health(
            account_id, status=AccountStatus.REAUTH_REQUIRED,
            code="zalo_personal.can_quet_lai", detail={"ly_do": str(ly_do)[:200]})
        await repository.update_status(
            account_id, AccountStatus.REAUTH_REQUIRED, actor_id=SYSTEM_ACTOR_ID)
        from agent import db as _db
        if getattr(_db, "_pool", None) is not None:
            from agent.core import thong_bao_noi_bo

            await thong_bao_noi_bo.bao_kenh_can_xac_thuc(
                account_id,
                ten_tai_khoan=ten,
                kenh="zalo_personal",
                ly_do=f"Zalo cá nhân «{ten}» mất phiên đăng nhập — cần quét QR lại.",
            )
    await ghi_nhat_ky(
        "zalo_personal.lech_bi_mat_sidecar" if lech else "zalo_personal.can_quet_lai",
        actor="system", ref_id=account_id, ly_do=str(ly_do)[:200])
    await bao_dong(
        (f"Zalo cá nhân «{ten}»: sidecar chạy với bí mật khác .env — khởi động lại "
         "sidecar (python -m scripts.chay_sidecar_zalo), KHÔNG cần quét QR.")
        if lech else
        (f"Zalo cá nhân «{ten}» đã mất phiên đăng nhập — tin khách KHÔNG vào và "
         "KHÔNG gửi được. Vào dashboard → Kết nối → Quét QR lại."),
        tieu_de="Zalo cá nhân cần xử lý", muc_do="hong")
    return True


async def khoi_phuc_phien_dut(
    account_ids: Sequence[Any] | Iterable[Any],
    mo_adapter: Callable[[Any], Awaitable[tuple[Any, dict]]],
    *,
    canh_bao: Callable[[Any, str], Any] = lambda _account, _ly_do: None,
) -> dict[str, list]:
    """
    Duyệt các tài khoản, khôi phục cái nào đang đứt.

    `mo_adapter(account_id)` trả `(adapter, credentials)`.
    `canh_bao(account_id, ly_do)` được gọi khi cần NGƯỜI quét QR lại — đó là
    việc máy không tự làm được, nên phải báo ra ngoài chứ không ghi nhật ký
    rồi thôi.

    Trả về hai danh sách để chỗ gọi ghi nhật ký và bảng điều khiển dùng.
    """
    da_khoi_phuc: list = []
    can_quet_lai: list = []
    lech_bi_mat: list = []
    sidecar_khong_toi: list = []

    for account_id in account_ids:
        adapter = None
        try:
            adapter, credentials = await mo_adapter(account_id)
            trang_thai = str((await adapter.status()).get("status") or "")
            if trang_thai in CON_SONG:
                continue

            session = (credentials or {}).get("session")
            if not isinstance(session, dict) or not session:
                # Chưa từng quét QR, hoặc session đã bị xoá. Máy không dựng
                # lại được — chỉ người cầm điện thoại mới làm được.
                can_quet_lai.append(account_id)
                canh_bao(account_id, "chưa có session đã lưu, cần quét QR lại")
                continue

            await adapter.restore_session(session)
            da_khoi_phuc.append(account_id)
        except Exception as exc:  # noqa: BLE001
            # Một tài khoản hỏng KHÔNG được kéo cả cụm: nhiều tài khoản Zalo
            # dùng chung một sidecar, và cụm chết vì một cái là mất tất.
            ly_do = f"{type(exc).__name__}: {exc}"[:200]
            if "Chữ ký sidecar" in str(exc):
                lech_bi_mat.append(account_id)
                canh_bao(
                    account_id,
                    f"{DAU_LECH_BI_MAT}: sidecar đang chạy với "
                    f"ZALO_SIDECAR_SECRET khác .env của ứng dụng. Khởi động "
                    f"lại sidecar: python -m scripts.chay_sidecar_zalo "
                    f"({ly_do})"[:200],
                )
                continue
            if la_loi_mang(ly_do):
                # Không với tới ≠ mất phiên. Gọi nó là "cần quét QR" từng
                # đẩy tài khoản sang REAUTH_REQUIRED và hoãn khôi phục 30
                # phút mỗi lần sidecar khởi động lại.
                sidecar_khong_toi.append(account_id)
                canh_bao(account_id, f"{DAU_SIDECAR_KHONG_TOI}: {ly_do}"[:200])
                continue
            can_quet_lai.append(account_id)
            canh_bao(account_id, ly_do)
        finally:
            if adapter is not None:
                try:
                    await adapter.aclose()
                except Exception:  # noqa: BLE001 — dọn dẹp không được làm hỏng vòng
                    pass

    return {
        "da_khoi_phuc": da_khoi_phuc,
        "can_quet_lai": can_quet_lai,
        "lech_bi_mat": lech_bi_mat,
        "sidecar_khong_toi": sidecar_khong_toi,
    }
