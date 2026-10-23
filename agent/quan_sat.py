"""
Quan sát khi đã host: lỗi về Sentry/GlitchTip, số đo về Prometheus.

VÌ SAO CẦN KHI ĐÃ CÓ CANH GÁC
-----------------------------
Canh gác (`agent/canh_gac.py`) báo khi MỘT cửa hàng hỏng hẳn. Khi chạy
nhiều cửa hàng trên một máy, người vận hành cần thấy XU HƯỚNG trên tất cả
cùng lúc: outbox ứ dần, job dead tăng, vòng nền ngừng đập. Những thứ ấy
không làm app chết — chúng làm khách chờ, và không ai thấy cho tới khi khách
phàn nàn.

/metrics ĐÓNG MẶC ĐỊNH
----------------------
Chưa đặt `METRICS_TOKEN` thì trả 404, như /mcp. Số đo nói ra quy mô kinh
doanh của cửa hàng (bao nhiêu tin, bao nhiêu đơn) — không phát cho ai gọi.

SENTRY KHÔNG GỬI DỮ LIỆU KHÁCH
------------------------------
`send_default_pii=False`, và sự kiện đi qua cùng bộ che bí mật của nhật ký
(`agent/nhat_ky.py`) trước khi rời tiến trình. Tin nhắn của khách nằm trong
biến cục bộ của stack trace — `include_local_variables=False`.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from agent import db
from agent.config import settings

log = logging.getLogger(__name__)
router = APIRouter(tags=["quan-sat"])


def bat_sentry() -> bool:
    """Bật Sentry nếu có DSN. Trả True nếu đã bật. Không có thư viện thì nói rõ."""
    dsn = (settings.sentry_dsn or "").strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        log.error("SENTRY_DSN có nhưng thiếu thư viện sentry-sdk — lỗi sẽ KHÔNG được gửi")
        return False
    from agent.nhat_ky import _gia_tri_bi_mat, che

    def che_bi_mat(s: str) -> str:
        return che(s, _gia_tri_bi_mat())

    def _loc(su_kien, _hint):
        # Che token/khoá trong thông điệp trước khi rời tiến trình.
        for ngoai_le in (su_kien.get("exception") or {}).get("values") or []:
            if isinstance(ngoai_le.get("value"), str):
                ngoai_le["value"] = che_bi_mat(ngoai_le["value"])
        if isinstance((su_kien.get("logentry") or {}).get("message"), str):
            su_kien["logentry"]["message"] = che_bi_mat(su_kien["logentry"]["message"])
        return su_kien

    sentry_sdk.init(dsn=dsn, send_default_pii=False, include_local_variables=False,
                    traces_sample_rate=0.0, before_send=_loc,
                    environment=settings.public_base_url or "local")
    return True


def _nhan(gia_tri: str) -> str:
    return gia_tri.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


async def _so_do() -> list[str]:
    dong = [
        "# HELP cskh_outbox_jobs Số job outbox theo trạng thái.",
        "# TYPE cskh_outbox_jobs gauge",
    ]
    for r in await db.fetch("SELECT status, count(*) AS n FROM outbox_jobs "
                            "WHERE status IN ('pending','processing','retry','dead') GROUP BY 1"):
        dong.append(f'cskh_outbox_jobs{{status="{_nhan(r["status"])}"}} {r["n"]}')

    r = await db.fetchrow_chac(
        "SELECT count(*) FILTER (WHERE role = 'customer') AS vao, "
        "count(*) FILTER (WHERE direction = 'outbound') AS ra "
        "FROM messages WHERE created_at > now() - interval '5 minutes'")
    dong += ["# HELP cskh_tin_5_phut Tin trong 5 phút gần nhất.", "# TYPE cskh_tin_5_phut gauge",
             f'cskh_tin_5_phut{{huong="vao"}} {r["vao"] if r else 0}',
             f'cskh_tin_5_phut{{huong="ra"}} {r["ra"] if r else 0}']

    r = await db.fetchrow_chac("SELECT count(*) AS n FROM conversations "
                          "WHERE status IN ('assist','escalated') AND state IN ('open','pending')")
    dong += ["# HELP cskh_hoi_thoai_cho_nguoi Hội thoại đang chờ người xử lý.",
             "# TYPE cskh_hoi_thoai_cho_nguoi gauge",
             f"cskh_hoi_thoai_cho_nguoi {r['n'] if r else 0}"]

    dong += ["# HELP cskh_vong_nen_tuoi_giay Giây kể từ lần đập cuối của mỗi vòng nền.",
             "# TYPE cskh_vong_nen_tuoi_giay gauge"]
    for r in await db.fetch("SELECT worker_name, extract(epoch FROM now() - last_seen_at) AS t "
                            "FROM worker_heartbeats"):
        dong.append(f'cskh_vong_nen_tuoi_giay{{vong="{_nhan(r["worker_name"])}"}} {float(r["t"]):.0f}')

    r = await db.fetchrow_chac("SELECT coalesce(sum(cost_usd), 0) AS c FROM messages "
                          "WHERE created_at >= date_trunc('day', now())")
    dong += ["# HELP cskh_chi_phi_model_hom_nay_usd Chi phí model từ 0h (UTC).",
             "# TYPE cskh_chi_phi_model_hom_nay_usd gauge",
             f"cskh_chi_phi_model_hom_nay_usd {float(r['c']) if r else 0:.6f}"]
    return dong


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request) -> Response:
    khoa = (settings.metrics_token or "").strip()
    if not khoa:
        return PlainTextResponse("not found", status_code=404)
    if not secrets.compare_digest(request.headers.get("authorization", "").encode(),
                                  f"Bearer {khoa}".encode()):
        return PlainTextResponse("unauthorized", status_code=401)
    try:
        dong = await _so_do()
    except Exception as exc:  # noqa: BLE001 — CSDL hỏng phải HIỆN trên số đo
        log.exception("không đọc được số đo")
        # Trả 200 với cskh_len=0: Prometheus vẫn cào được và cảnh báo "CSDL
        # không đọc được" bắn ra. Trả 500 thì nó chỉ thấy target down — một
        # nguyên nhân khác, sửa khác.
        dong = ["# HELP cskh_len 1 nếu đọc được CSDL.", "# TYPE cskh_len gauge", "cskh_len 0",
                f"# loi {_nhan(type(exc).__name__)}"]
        return PlainTextResponse("\n".join(dong) + "\n", media_type="text/plain; version=0.0.4")
    dong = ["# HELP cskh_len 1 nếu đọc được CSDL.", "# TYPE cskh_len gauge", "cskh_len 1", *dong]
    return PlainTextResponse("\n".join(dong) + "\n", media_type="text/plain; version=0.0.4")
