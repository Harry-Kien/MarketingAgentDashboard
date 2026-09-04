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
    }
