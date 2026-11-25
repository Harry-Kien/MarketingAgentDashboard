"""
Kết nối & Tích hợp: một chỗ biết hệ thống đang nối ra những dịch vụ nào.

VÌ SAO TỔ CHỨC THEO DỊCH VỤ, KHÔNG THEO "API" VÀ "WEBHOOK"
-----------------------------------------------------------
Người vận hành hỏi "GHN có chạy không", không hỏi "webhook có chạy không".
Token, shop id, URL webhook, lần kiểm cuối và lần GHN gọi vào cuối cùng là
MỘT câu trả lời — tách hai màn là bắt người ta tự ghép.

GIÁ TRỊ Ở ĐÂU
-------------
Không có kho mới. Khoá và tham số vẫn ở `cau_hinh_dong` (CSDL mã hoá trước,
`.env` sau), credential kênh vẫn ở vault của `channel_accounts`. Lớp này chỉ
gom, đánh giá trạng thái, và ghi ba sổ của migration 0057:

    ket_noi_kiem_tra   kết quả "Kiểm tra kết nối" lần cuối + dấu vân tay
    lich_su_ket_noi    ai đổi trường nào lúc nào — KHÔNG có giá trị
    webhook_nhan       mọi lời gọi vào /webhook/*, cả lời bị từ chối

BỐN TRẠNG THÁI, VÀ VÌ SAO "CHƯA KIỂM TRA" QUAY LẠI
---------------------------------------------------
`chua_cau_hinh` → thiếu trường bắt buộc; `chua_kiem_tra` → đủ trường nhưng
chưa kiểm, HOẶC đã đổi giá trị sau lần kiểm cuối; `thanh_cong` / `loi` →
kết quả lần kiểm khớp đúng bộ giá trị đang chạy. Giữ màu xanh sau khi đổi
token là xanh giả — thứ không ai đi kiểm lại.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from agent import cau_hinh_dong, db
from agent.config import settings

_log = logging.getLogger("agent.ket_noi_tich_hop")

CHUA_CAU_HINH = "chua_cau_hinh"
CHUA_KIEM_TRA = "chua_kiem_tra"
THANH_CONG = "thanh_cong"
LOI = "loi"
NHAN_TRANG_THAI = {
    CHUA_CAU_HINH: "Chưa cấu hình",
    CHUA_KIEM_TRA: "Chưa kiểm tra",
    THANH_CONG: "Kết nối thành công",
    LOI: "Kết nối lỗi",
}


@dataclass(frozen=True, slots=True)
class WebhookVao:
    """Webhook mà dịch vụ ngoài GỌI VÀO hệ thống này."""

    duong: str                       # đường dẫn, KHÔNG kèm bí mật
    xac_minh: str                    # cách hệ thống biết lời gọi là thật
    su_kien: tuple[str, ...]
    bi_mat_url: bool = False         # URL phải mang ?token=<bí mật>


@dataclass(frozen=True, slots=True)
class DichVu:
    ma: str
    ten: str
    mo_ta: str
    khoa: tuple[str, ...]            # khoá trong cau_hinh_dong.DANH_MUC
    kiem_duoc: bool = True
    webhook: WebhookVao | None = None
    # Giá trị `.env` ngoài DANH_MUC mà phép kiểm phụ thuộc: đổi chúng cũng
    # làm kết quả kiểm cũ hết giá trị, nên phải vào dấu vân tay.
    env_lien_quan: tuple[str, ...] = field(default_factory=tuple)


_SU_KIEN_VAN_CHUYEN = ("Cập nhật trạng thái vận đơn",)
_XAC_MINH_VAN_CHUYEN = ("Bí mật trong URL (?token=SHIPPING_WEBHOOK_SECRET). Hãng không ký "
                        "webhook nên bí mật trong URL là cách duy nhất; chưa đặt thì mọi "
                        "lời gọi bị từ chối.")

DICH_VU: dict[str, DichVu] = {d.ma: d for d in (
    DichVu("ai", "Nhà cung cấp AI",
           "Model trả lời khách. Đổi có hiệu lực từ tin nhắn kế tiếp.",
           ("LLM_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "OPENAI_BASE_URL", "MODEL_CHAT", "MODEL_HARD", "MODEL_CHEAP"),
           env_lien_quan=("gcp_project_id", "gcp_region")),
    DichVu("erpnext", "ERPNext",
           "Giá, tồn kho, đơn hàng. Đổi URL/khoá có hiệu lực ngay, không cần khởi động lại.",
           ("ERPNEXT_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET"),
           env_lien_quan=("erp_ma_kho", "erp_pricelist")),
    DichVu("ghn", "Giao Hàng Nhanh (GHN)",
           "Tạo vận đơn, tra phí, nhận trạng thái giao.",
           ("GHN_TOKEN", "GHN_SHOP_ID"),
           webhook=WebhookVao("/webhook/shipping/ghn", _XAC_MINH_VAN_CHUYEN,
                              _SU_KIEN_VAN_CHUYEN, bi_mat_url=True),
           env_lien_quan=("ghn_api_url",)),
    DichVu("ghtk", "Giao Hàng Tiết Kiệm (GHTK)",
           "Tạo vận đơn, nhận trạng thái giao. Cần mã kho HOẶC đủ địa chỉ lấy hàng.",
           ("GHTK_TOKEN", "GHTK_MA_DOI_TAC", "GHTK_KHO_ID", "GHTK_LAY_TEN", "GHTK_LAY_SDT",
            "GHTK_LAY_DIA_CHI", "GHTK_LAY_TINH", "GHTK_LAY_HUYEN", "GHTK_LAY_PHUONG"),
           webhook=WebhookVao("/webhook/shipping/ghtk", _XAC_MINH_VAN_CHUYEN,
                              _SU_KIEN_VAN_CHUYEN, bi_mat_url=True),
           env_lien_quan=("ghtk_api_url",)),
    DichVu("thong_bao_ai", "Thông báo minh bạch AI",
           "Câu báo khách đang nói với trợ lý AI và cách gặp nhân viên.",
           ("THONG_BAO_AI", "TIN_THONG_BAO_AI"), kiem_duoc=False),
)}


def dich_vu_cua_khoa(khoa: str) -> str:
    """Khoá thuộc dịch vụ nào; khoá lẻ (CSAT, SLA...) thì theo nhóm của nó."""
    for d in DICH_VU.values():
        if khoa in d.khoa:
            return d.ma
    mo_ta = cau_hinh_dong.DANH_MUC.get(khoa)
    return mo_ta.nhom if mo_ta else "khac"


def lay_dich_vu(ma: str) -> DichVu:
    d = DICH_VU.get(ma)
    if d is None:
        raise KeyError(f"dịch vụ không có: {ma!r}")
    return d


def _gcp_san_sang() -> bool:
    p = str(settings.gcp_project_id or "").strip()
    return bool(p) and not p.startswith("your-")


# Nhà cung cấp -> khoá API nó cần. gemini/vertex xác thực bằng gcloud trên
# máy chủ, không có khoá nào nhập được trên dashboard.
KHOA_THEO_NHA_CUNG_CAP = {
    "gemini_api": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
}


def thieu(ma: str) -> list[str]:
    """Trường bắt buộc còn trống, viết để người đọc biết phải điền gì."""
    d = lay_dich_vu(ma)
    lay = cau_hinh_dong.lay
    if ma == "ai":
        p = (lay("LLM_PROVIDER") or "gemini").strip().lower()
        k = KHOA_THEO_NHA_CUNG_CAP.get(p)
        ra = []
        if k and not lay(k):
            ra.append(k)
        if not k and not _gcp_san_sang():
            ra.append("GCP_PROJECT_ID (.env, cho xác thực gcloud)")
        if not lay("MODEL_CHAT"):
            ra.append("MODEL_CHAT")
        return ra
    if ma == "erpnext":
        ra = [k for k in d.khoa if not lay(k)]
        # Hai trường này chỉ ở .env (adapter đòi chúng lúc dựng). Không nói ra
        # ở đây thì "Kiểm tra" đỏ với lý do mà màn hình không có ô nào để sửa.
        if not settings.erp_ma_kho:
            ra.append("ERP_MA_KHO (.env)")
        if not settings.erp_pricelist:
            ra.append("ERP_PRICELIST (.env)")
        return ra
    if ma == "ghn":
        return [k for k in d.khoa if not lay(k)]
    if ma == "ghtk":
        # Luật "đủ chỗ lấy hàng" ở MỘT nơi: provider GHTK. Chép lại ở đây là
        # hai bản luật, rồi bản ít người đọc hơn mục đi.
        from agent.shipping.ghtk import GHTKShippingProvider

        ly_do = GHTKShippingProvider()._thieu_cau_hinh()
        return [ly_do] if ly_do else []
    if ma == "thong_bao_ai":
        return []
    return [k for k in d.khoa if not lay(k)]


def dau_van_tay(ma: str) -> str:
    """Băm bộ giá trị ĐANG CHẠY của dịch vụ — để biết lần kiểm cũ còn đúng không.

    Cắt còn 16 ký tự hex: đủ để phân biệt hai bộ cấu hình, và một mẩu băm
    ngắn của khoá entropy cao không cho kẻ đọc CSDL đoán ngược ra khoá.
    """
    d = lay_dich_vu(ma)
    h = hashlib.sha256()
    for k in sorted(d.khoa):
        h.update(f"{k}={cau_hinh_dong.lay(k)}\n".encode())
    for ten in sorted(d.env_lien_quan):
        h.update(f"env:{ten}={getattr(settings, ten, '')}\n".encode())
    return h.hexdigest()[:16]


def trang_thai(ma: str, kiem: dict | None) -> str:
    if thieu(ma):
        return CHUA_CAU_HINH
    if not kiem or kiem.get("dau_van_tay") != dau_van_tay(ma):
        return CHUA_KIEM_TRA
    return THANH_CONG if kiem.get("ok") else LOI


def mo_ta_truong(ma: str) -> list[dict[str, Any]]:
    """Trường của một dịch vụ, ĐÃ CHE: bí mật chỉ còn bốn ký tự cuối."""
    d = lay_dich_vu(ma)
    theo_khoa = {m["khoa"]: m for m in cau_hinh_dong.liet_ke()}
    return [theo_khoa[k] for k in d.khoa if k in theo_khoa]


# ------------------------------------------------------------------ sổ kiểm

async def doc_ket_qua_kiem() -> dict[str, dict]:
    try:
        rows = await db.fetch(
            "SELECT dich_vu, ok, chi_tiet, ms, dau_van_tay, kiem_boi, kiem_luc "
            "FROM ket_noi_kiem_tra")
    except Exception as exc:  # noqa: BLE001 — bảng chưa migrate: màn vẫn hiện
        _log.warning("ket_noi: không đọc được ket_noi_kiem_tra (%s: %s)",
                     type(exc).__name__, exc)
        return {}
    return {r["dich_vu"]: r for r in rows}


async def ghi_ket_qua_kiem(ma: str, *, ok: bool, chi_tiet: str, ms: int,
                           van_tay: str, boi: str) -> None:
    await db.execute(
        """
        INSERT INTO ket_noi_kiem_tra (dich_vu, ok, chi_tiet, ms, dau_van_tay, kiem_boi, kiem_luc)
        VALUES ($1, $2, $3, $4, $5, $6, now())
        ON CONFLICT (dich_vu) DO UPDATE SET
            ok = EXCLUDED.ok, chi_tiet = EXCLUDED.chi_tiet, ms = EXCLUDED.ms,
            dau_van_tay = EXCLUDED.dau_van_tay, kiem_boi = EXCLUDED.kiem_boi,
            kiem_luc = now()
        """,
        ma, ok, chi_tiet[:300], max(0, int(ms)), van_tay, boi[:120],
    )


# ------------------------------------------------------------------ lịch sử

HANH_DONG = frozenset({"dat", "xoa", "doi_credential", "bat", "tat", "doi_tuy_chon",
                       "tao", "xoa_tai_khoan"})


async def ghi_lich_su(*, dich_vu: str, truong: str, hanh_dong: str, sua_boi: str,
                      bi_mat: bool = False, account_id: UUID | None = None,
                      doi_tuong: str | None = None) -> None:
    """Ghi MỘT dòng lịch sử. Không bao giờ nhận giá trị — chữ ký hàm không có chỗ.

    Hỏng thì KHÔNG chặn thao tác (khoá đã lưu xong rồi), nhưng cũng không im:
    ghi lỗi qua logging — đúng cách `db.log_event` làm.
    """
    if hanh_dong not in HANH_DONG:
        raise ValueError(f"hành động lịch sử lạ: {hanh_dong!r}")
    if db._pool is None:
        # Chỉ xảy ra trong test đơn vị không có CSDL; tiến trình thật luôn có
        # pool trước khi nhận request.
        return
    try:
        await db.execute(
            "INSERT INTO lich_su_ket_noi (dich_vu, truong, hanh_dong, bi_mat, account_id, "
            "doi_tuong, sua_boi) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            dich_vu[:40], truong[:300], hanh_dong, bi_mat, account_id,
            (doi_tuong or None) and str(doi_tuong)[:120], (sua_boi or "?")[:120],
        )
    except Exception as exc:  # noqa: BLE001
        _log.error("KHÔNG ghi được lịch sử kết nối %s/%s: %s: %s",
                   dich_vu, truong, type(exc).__name__, exc)


async def doc_lich_su(*, dich_vu: str | None = None, gioi_han: int = 50,
                      tu: datetime | None = None, den: datetime | None = None,
                      account_id: UUID | None = None) -> list[dict]:
    """Lịch sử đổi cấu hình, lọc theo dịch vụ / khoảng thời gian / tài khoản.

    Lọc ở MÁY CHỦ chứ không lọc 30 dòng mới nhất ở trình duyệt: lọc "GHN tháng
    trước" trên 30 dòng mới nhất là trả rỗng trong khi sổ có dữ liệu — một
    câu trả lời sai mà trông như đúng (UX-08-08).
    """
    gioi_han = max(1, min(int(gioi_han), 200))
    dk: list[str] = []
    ts: list[Any] = []
    for cot, v in (("dich_vu = ${}", dich_vu or None), ("sua_luc >= ${}", tu),
                   ("sua_luc < ${}", den), ("account_id = ${}", account_id)):
        if v is not None:
            ts.append(v)
            dk.append(cot.format(len(ts)))
    ts.append(gioi_han)
    rows = await db.fetch(
        "SELECT dich_vu, truong, hanh_dong, bi_mat, account_id, doi_tuong, sua_boi, sua_luc "
        f"FROM lich_su_ket_noi {('WHERE ' + ' AND '.join(dk)) if dk else ''} "
        f"ORDER BY sua_luc DESC, id DESC LIMIT ${len(ts)}", *ts)
    return [{**r, "account_id": str(r["account_id"]) if r["account_id"] else None,
             "nhan_truong": _NHAN_TRUONG.get(r["truong"], r["truong"]),
             "sua_luc": r["sua_luc"].isoformat()} for r in rows]


# ------------------------------------------------------------------ dòng thời gian

# Ba sổ, một trục thời gian (UX-08-09). Trước đây "Zalo này rớt lúc nào, ai
# bật lại" phải ghép tay từ ba chỗ: sức khoẻ (account_health_events, chỉ dùng
# nội bộ), nhật ký (events, màn khác) và lịch sử cấu hình (cuối một trang dài).
LOAI_DONG_THOI_GIAN = {
    "suc_khoe": "Trạng thái kết nối",
    "su_kien": "Sự kiện hệ thống",
    "cau_hinh": "Thay đổi cấu hình",
}
_NHAN_LICH_SU = {"dat": "đặt", "xoa": "bỏ (về .env)", "doi_credential": "đổi thông tin đăng nhập",
                 "bat": "bật", "tat": "tạm ngắt", "doi_tuy_chon": "đổi tuỳ chọn", "tao": "tạo",
                 "xoa_tai_khoan": "xoá tài khoản"}
# Tên trường kỹ thuật mà thao tác KÊNH ghi (khoá cấu hình như GHN_TOKEN giữ
# nguyên — đó là tên người vận hành thấy trong .env và trên ô nhập).
_NHAN_TRUONG = {"tai_khoan": "tài khoản kênh", "trang_thai": "tài khoản kênh",
                "credentials": "thông tin đăng nhập",
                "an_binh_luan_co_sdt": "tuỳ chọn ẩn bình luận có SĐT"}
# Sự kiện riêng của màn Kết nối mà nhãn nhật ký chung chưa có. Thiếu nhãn thì
# dòng thời gian hiện mã `kenh.agent_bat_tat` thô — đúng thứ UX-20-05 muốn bỏ.
_NHAN_SU_KIEN_KENH = {
    "kenh.agent_bat_tat": "Bật/tắt AI cho tài khoản",
    "kenh.ho_so_agent": "Đổi hồ sơ AI của tài khoản",
    "kenh.tuy_chon": "Đổi tuỳ chọn Trang",
    "kenh.xoa_tai_khoan": "Xoá tài khoản kênh",
}
_UUID_TRAN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_MUC_STATUS = {"active": "xanh", "pending": "vang", "degraded": "do",
               "reauth_required": "do", "disabled": "tat"}


async def dong_thoi_gian(account_id: UUID, *, loai: set[str] | None = None,
                         tu: datetime | None = None, den: datetime | None = None,
                         gioi_han: int = 100, xem_cau_hinh: bool = True) -> list[dict[str, Any]]:
    """Sự kiện của MỘT tài khoản kênh, mới nhất trước.

    Sức khoẻ chỉ lấy những lần ĐỔI trạng thái hoặc đổi mã: sidecar Zalo gửi
    nhịp tim vài phút một lần, đổ hết ra là hàng trăm dòng "đã kết nối" che
    mất đúng một dòng "mất kết nối" người ta đang tìm.

    `xem_cau_hinh=False`: người không có quyền cấu hình không thấy sổ cấu hình
    (luật số 2 của agent/api/ket_noi_tich_hop.py) — bỏ hẳn, không trả rỗng giả.
    """
    from agent.core.nhat_ky_kiem_toan import NHAN_HANH_DONG
    from agent.omnichannel.giai_thich_loi_kenh import tra
    from agent.omnichannel.suc_khoe_kenh import NHAN_TRANG_THAI_KET_NOI

    gioi_han = max(1, min(int(gioi_han), 300))
    loai = set(loai or LOAI_DONG_THOI_GIAN) & set(LOAI_DONG_THOI_GIAN)
    if not xem_cau_hinh:
        loai.discard("cau_hinh")
    nhan_status = {"active": NHAN_TRANG_THAI_KET_NOI["hoat_dong"],
                   "pending": NHAN_TRANG_THAI_KET_NOI["chua_ket_noi"],
                   "degraded": NHAN_TRANG_THAI_KET_NOI["loi"],
                   "reauth_required": NHAN_TRANG_THAI_KET_NOI["can_xac_thuc"],
                   "disabled": NHAN_TRANG_THAI_KET_NOI["tam_ngat"]}
    ra: list[dict[str, Any]] = []

    if "suc_khoe" in loai:
        rows = await db.fetch(
            """
            SELECT status, code, detail, observed_at FROM (
                SELECT status, code, detail, observed_at,
                       lag(status) OVER w AS status_truoc, lag(code) OVER w AS code_truoc
                FROM account_health_events
                WHERE account_id = $1
                  AND ($2::timestamptz IS NULL OR observed_at >= $2)
                  AND ($3::timestamptz IS NULL OR observed_at < $3)
                WINDOW w AS (ORDER BY observed_at)
            ) t
            WHERE status_truoc IS DISTINCT FROM status OR code_truoc IS DISTINCT FROM code
            ORDER BY observed_at DESC LIMIT $4
            """, account_id, tu, den, gioi_han)
        for r in rows:
            ct = r["detail"]
            if isinstance(ct, str):
                try:
                    ct = json.loads(ct)
                except ValueError:
                    ct = {}
            gt = tra(r["code"])
            ra.append({
                "luc": r["observed_at"].isoformat(), "loai": "suc_khoe",
                "muc": _MUC_STATUS.get(r["status"], "vang"),
                "tieu_de": nhan_status.get(r["status"], r["status"]),
                "mo_ta": gt.tieu_de if gt and r["status"] != "active" else "",
                "boi": "Hệ thống",
                "ky_thuat": {"status": r["status"], "code": r["code"],
                             "ly_do": str((ct or {}).get("ly_do") or "")[:300] or None},
            })

    if "su_kien" in loai:
        rows = await db.fetch(
            """
            SELECT e.kind, e.actor, e.detail, e.created_at,
                   COALESCE(NULLIF(nd.ho_ten, ''), nd.ten_dang_nhap) AS nguoi
            FROM events e
            -- actor là tên đăng nhập HOẶC id người dùng tuỳ nơi ghi; so chuỗi
            -- để không phải ép kiểu UUID (actor 'system' ép là nổ).
            LEFT JOIN nguoi_dung nd ON nd.ten_dang_nhap = e.actor OR nd.id::text = e.actor
            WHERE e.ref_id = $1
              AND ($2::timestamptz IS NULL OR e.created_at >= $2)
              AND ($3::timestamptz IS NULL OR e.created_at < $3)
            ORDER BY e.created_at DESC LIMIT $4
            """, account_id, tu, den, gioi_han)
        for r in rows:
            ct = r["detail"]
            if isinstance(ct, str):
                try:
                    ct = json.loads(ct)
                except ValueError:
                    ct = {}
            ct = ct if isinstance(ct, dict) else {}
            st = str(ct.get("status") or "")
            ra.append({
                "luc": r["created_at"].isoformat(), "loai": "su_kien",
                "muc": _MUC_STATUS.get(st, "xanh" if "loi" not in r["kind"] else "do"),
                "tieu_de": (_NHAN_SU_KIEN_KENH.get(r["kind"]) or NHAN_HANH_DONG.get(r["kind"])
                            or r["kind"]),
                "mo_ta": f"→ {nhan_status[st]}" if st in nhan_status else "",
                # actor không khớp người dùng nào (system, UUID 0 của tiến trình
                # nền, người đã xoá) thì nói "Hệ thống", không in UUID thô.
                "boi": r["nguoi"] or ("Hệ thống" if _UUID_TRAN.match(str(r["actor"] or ""))
                                      or r["actor"] in ("system", "", None)
                                      else str(r["actor"])[:60]),
                # Chỉ mã sự kiện — detail có thể mang số điện thoại, tên khách.
                "ky_thuat": {"kind": r["kind"]},
            })

    if "cau_hinh" in loai:
        for r in await doc_lich_su(account_id=account_id, tu=tu, den=den, gioi_han=gioi_han):
            ra.append({
                "luc": r["sua_luc"], "loai": "cau_hinh",
                "muc": "tat" if r["hanh_dong"] in ("tat", "xoa_tai_khoan") else "xanh",
                "tieu_de": f"{_NHAN_LICH_SU.get(r['hanh_dong'], r['hanh_dong'])} "
                           f"{_NHAN_TRUONG.get(r['truong'], r['truong'])}"
                           f"{' (bí mật)' if r['bi_mat'] else ''}".strip().capitalize(),
                "mo_ta": "", "boi": r["sua_boi"],
                "ky_thuat": {"hanh_dong": r["hanh_dong"], "truong": r["truong"]},
            })

    ra.sort(key=lambda x: x["luc"], reverse=True)
    return ra[:gioi_han]


# ------------------------------------------------------------------ webhook

GIU_NGAY_WEBHOOK = 30
_DON_MOI_GIAY = 3600.0
_lan_don_cuoi = 0.0

_NATIVE = {"meta": "meta", "zalo-oa": "zalo_oa", "zalo-personal": "zalo_personal"}
_KENH_CU = {"messenger", "chatwoot", "zalocrm", "zalo_oa"}


def _uuid(s: str) -> UUID | None:
    try:
        return UUID(s)
    except (ValueError, TypeError):
        return None


def phan_loai_webhook(duong: str) -> tuple[str, UUID | None]:
    """Đường `/webhook/...` -> (dịch vụ, tài khoản kênh nếu đường mang id)."""
    phan = [p for p in duong.split("/") if p]
    if not phan or phan[0] != "webhook":
        return "khac", None
    if len(phan) == 1:
        return "zalocrm", None           # `/webhook` trần: cấu hình ZaloCRM cũ
    if phan[1] == "shipping":
        hang = phan[2] if len(phan) > 2 else ""
        return (hang if hang in ("ghn", "ghtk", "mock") else "khac"), None
    if phan[1] == "native" and len(phan) > 2:
        return _NATIVE.get(phan[2], "khac"), (_uuid(phan[3]) if len(phan) > 3 else None)
    if len(phan) == 2 and phan[1] in _KENH_CU:
        return phan[1], None
    return "khac", None


def _loi_tu_than(than: bytes) -> str:
    try:
        d = json.loads(than)
    except (ValueError, UnicodeDecodeError):
        return than[:200].decode("utf-8", "replace").strip()
    if isinstance(d, dict):
        for k in ("error", "detail", "note", "loi"):
            if d.get(k):
                v = d[k]
                return (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))[:300]
    return ""


async def ghi_webhook_nhan(*, phuong_thuc: str, duong: str, ma_http: int, ms: int,
                           loi: str | None) -> None:
    """Một dòng sổ. Hỏng KHÔNG được làm hỏng webhook — chỉ ghi log cảnh báo."""
    global _lan_don_cuoi
    if db._pool is None:
        return
    dich_vu, tai_khoan = phan_loai_webhook(duong)
    try:
        await asyncio.wait_for(db.execute(
            "INSERT INTO webhook_nhan (dich_vu, account_id, phuong_thuc, duong, ma_http, "
            "thoi_gian_ms, loi) VALUES ($1,$2,$3,$4,$5,$6,$7)",
            dich_vu, tai_khoan, phuong_thuc[:10], duong[:300], int(ma_http), max(0, int(ms)),
            (loi or None) and loi[:300]), timeout=2.0)
        # Dọn theo nhịp, không theo lịch riêng: sổ này chỉ để chẩn đoán gần
        # đây, và một tác vụ nền nữa là một thứ nữa có thể chết im lặng.
        bay_gio = time.monotonic()
        if bay_gio - _lan_don_cuoi > _DON_MOI_GIAY:
            _lan_don_cuoi = bay_gio
            await db.execute(
                "DELETE FROM webhook_nhan WHERE nhan_luc < now() - make_interval(days => $1)",
                GIU_NGAY_WEBHOOK)
    except Exception as exc:  # noqa: BLE001
        _log.warning("ket_noi: không ghi được sổ webhook %s (%s: %s)",
                     dich_vu, type(exc).__name__, exc)


async def so_webhook(request, call_next):
    """Thân của middleware: đo và ghi MỌI lời gọi vào `/webhook/*`.

    Đọc thân phản hồi CHỈ khi mã >= 400, để lấy câu lỗi người đọc hiểu được
    ("Bí mật webhook không đúng") thay vì một con số. Endpoint trả 200 kèm
    `ok=false` thì tự gắn `request.state.loi_webhook`.
    """
    from starlette.responses import Response

    duong = request.url.path
    if not duong.startswith("/webhook"):
        return await call_next(request)
    t0 = time.perf_counter()
    try:
        phan_hoi = await call_next(request)
    except Exception as exc:
        await ghi_webhook_nhan(phuong_thuc=request.method, duong=duong, ma_http=500,
                               ms=int((time.perf_counter() - t0) * 1000),
                               loi=f"{type(exc).__name__}: {exc}"[:300])
        raise
    ms = int((time.perf_counter() - t0) * 1000)
    loi = getattr(request.state, "loi_webhook", None)
    if phan_hoi.status_code >= 400 and not loi:
        than = b""
        async for manh in phan_hoi.body_iterator:
            than += manh if isinstance(manh, bytes) else str(manh).encode()
        dau = {k: v for k, v in phan_hoi.headers.items() if k.lower() != "content-length"}
        phan_hoi = Response(content=than, status_code=phan_hoi.status_code, headers=dau)
        loi = _loi_tu_than(than) or f"HTTP {phan_hoi.status_code}"
    await ghi_webhook_nhan(phuong_thuc=request.method, duong=duong,
                           ma_http=phan_hoi.status_code, ms=ms, loi=loi)
    return phan_hoi


def _iso(v) -> str | None:
    return v.isoformat() if v is not None else None


async def thong_ke_webhook(dich_vu: list[str]) -> dict[str, dict]:
    """Mỗi dịch vụ: lần gọi cuối, số gọi/lỗi 24 giờ, thời gian xử lý TB, lỗi cuối."""
    if not dich_vu:
        return {}
    ra: dict[str, dict] = {d: {} for d in dich_vu}
    for r in await db.fetch(
        """
        SELECT dich_vu, max(nhan_luc) AS lan_cuoi,
               count(*) FILTER (WHERE nhan_luc > now() - interval '24 hours') AS dem_24h,
               count(*) FILTER (WHERE ma_http >= 400
                                  AND nhan_luc > now() - interval '24 hours') AS loi_24h,
               avg(thoi_gian_ms) FILTER (WHERE nhan_luc > now() - interval '24 hours') AS tb_ms
        FROM webhook_nhan WHERE dich_vu = ANY($1) GROUP BY dich_vu
        """, dich_vu):
        ra[r["dich_vu"]].update(
            lan_cuoi=_iso(r["lan_cuoi"]), dem_24h=int(r["dem_24h"]), loi_24h=int(r["loi_24h"]),
            tb_ms=round(float(r["tb_ms"])) if r["tb_ms"] is not None else None)
    for r in await db.fetch(
        """
        SELECT DISTINCT ON (dich_vu) dich_vu, ma_http, loi, nhan_luc FROM webhook_nhan
        WHERE dich_vu = ANY($1) AND ma_http >= 400 ORDER BY dich_vu, nhan_luc DESC
        """, dich_vu):
        ra[r["dich_vu"]]["loi_cuoi"] = {"ma_http": r["ma_http"], "loi": r["loi"],
                                        "luc": _iso(r["nhan_luc"])}
    return ra


async def thong_ke_webhook_tai_khoan(ids: list[UUID]) -> dict[str, dict]:
    """Mỗi tài khoản kênh: gộp sổ chống trùng (tin đã vào) với sổ lời gọi."""
    if not ids:
        return {}
    ra: dict[str, dict] = {str(i): {} for i in ids}
    for r in await db.fetch(
        """
        SELECT account_id, max(received_at) AS lan_cuoi,
               count(*) FILTER (WHERE received_at > now() - interval '24 hours') AS dem_24h,
               count(*) FILTER (WHERE status IN ('failed', 'rejected')
                                  AND received_at > now() - interval '24 hours') AS loi_24h,
               avg(extract(epoch FROM processed_at - received_at) * 1000)
                   FILTER (WHERE processed_at IS NOT NULL
                             AND received_at > now() - interval '24 hours') AS tb_ms
        FROM webhook_deliveries WHERE account_id = ANY($1) GROUP BY account_id
        """, ids):
        ra[str(r["account_id"])].update(
            lan_cuoi=_iso(r["lan_cuoi"]), dem_24h=int(r["dem_24h"]), loi_24h=int(r["loi_24h"]),
            tb_ms=round(float(r["tb_ms"])) if r["tb_ms"] is not None else None)
    loi: dict[str, dict] = {}
    for r in await db.fetch(
        """
        SELECT DISTINCT ON (account_id) account_id, last_error, updated_at
        FROM webhook_deliveries WHERE account_id = ANY($1) AND last_error IS NOT NULL
        ORDER BY account_id, updated_at DESC
        """, ids):
        loi[str(r["account_id"])] = {"ma_http": None, "loi": r["last_error"][:300],
                                     "luc": _iso(r["updated_at"])}
    for r in await db.fetch(
        """
        SELECT DISTINCT ON (account_id) account_id, ma_http, loi, nhan_luc FROM webhook_nhan
        WHERE account_id = ANY($1) AND ma_http >= 400 ORDER BY account_id, nhan_luc DESC
        """, ids):
        aid = str(r["account_id"])
        moi = {"ma_http": r["ma_http"], "loi": r["loi"], "luc": _iso(r["nhan_luc"])}
        if aid not in loi or (moi["luc"] or "") > (loi[aid]["luc"] or ""):
            loi[aid] = moi
    for aid, v in loi.items():
        ra.setdefault(aid, {})["loi_cuoi"] = v
    return ra


async def lich_su_webhook(*, dich_vu: str | None = None, account_id: UUID | None = None,
                          gioi_han: int = 50) -> dict[str, list[dict]]:
    gioi_han = max(1, min(int(gioi_han), 200))
    if account_id is not None:
        goi = await db.fetch(
            "SELECT dich_vu, phuong_thuc, duong, ma_http, thoi_gian_ms, loi, nhan_luc "
            "FROM webhook_nhan WHERE account_id = $1 ORDER BY nhan_luc DESC LIMIT $2",
            account_id, gioi_han)
        # `dedupe_key` và `metadata` cố ý không trả: chúng mang id tin của khách,
        # thứ màn chẩn đoán kết nối không cần.
        tin = await db.fetch(
            "SELECT status, attempts, last_error, received_at, processed_at "
            "FROM webhook_deliveries WHERE account_id = $1 ORDER BY received_at DESC LIMIT $2",
            account_id, gioi_han)
    else:
        goi = await db.fetch(
            "SELECT dich_vu, phuong_thuc, duong, ma_http, thoi_gian_ms, loi, nhan_luc "
            "FROM webhook_nhan WHERE dich_vu = $1 ORDER BY nhan_luc DESC LIMIT $2",
            dich_vu or "khac", gioi_han)
        tin = []
    return {
        "goi_vao": [{**r, "nhan_luc": _iso(r["nhan_luc"])} for r in goi],
        "tin_da_nhan": [{
            "status": r["status"], "attempts": r["attempts"], "last_error": r["last_error"],
            "received_at": _iso(r["received_at"]), "processed_at": _iso(r["processed_at"]),
            "xu_ly_ms": (int((r["processed_at"] - r["received_at"]).total_seconds() * 1000)
                         if r["processed_at"] else None),
        } for r in tin],
    }


def url_cong_khai(duong: str) -> str:
    return str(settings.public_base_url or "").rstrip("/") + duong


def bi_mat_webhook_van_chuyen() -> dict[str, Any]:
    """Trạng thái bí mật webhook vận chuyển — chỉ bốn ký tự cuối, không hơn."""
    v = str(settings.shipping_webhook_secret or "").strip()
    return {"da_dat": bool(v), "hien": cau_hinh_dong.duoi(v) if v else ""}
