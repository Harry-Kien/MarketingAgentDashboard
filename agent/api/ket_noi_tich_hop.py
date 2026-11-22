"""
API màn "Kết nối & Tích hợp" và "Cấu hình AI cơ bản".

LUẬT CỦA CẢ TỆP
---------------
1. Không đường nào trả bí mật rõ. Trường bí mật chỉ ra bốn ký tự cuối (qua
   `cau_hinh_dong.liet_ke`), URL webhook vận chuyển chỉ ra `?token=···abcd`.
   Verify token Meta vẫn đi đường riêng sẵn có (`/api/channel-accounts/{id}/
   verify-token`, quyền `kenh.sua`) — không nhân bản ở đây.
2. Xem cũng cần `cau_hinh.sua`, không chỉ sửa: chủ dự án chốt "chỉ quản trị
   viên mới xem hoặc đổi" cấu hình kết nối. Màn Cài đặt API cũ vẫn cho
   `cau_hinh.doc` xem trạng thái — hai màn hai mục đích.
3. "Kiểm tra kết nối" chạy bằng giá trị người vừa gõ đè lên giá trị đang
   lưu, KHÔNG lưu gì; chỉ khi lần kiểm chạy đúng bộ giá trị đang lưu thì
   kết quả mới được ghi làm trạng thái của dịch vụ.
"""
from __future__ import annotations

import json
import time
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agent import cau_hinh_dong, db
from agent import ket_noi_tich_hop as kn
from agent.api.cai_dat_api import _che
from agent.channels import factory
from agent.channels.base import KHA_NANG, ChannelAdapter
from agent.config import Settings, settings
from agent.core import llm
from agent.omnichannel.accounts import Channel
from agent.shipping import ghn, ghtk

from .routes import can_quyen

router = APIRouter(prefix="/api/ket-noi", tags=["ket-noi-tich-hop"])

DICH_VU_TICH_HOP = ("erpnext", "ghn", "ghtk")


def _actor(user: dict) -> str:
    return str(user.get("ten_dang_nhap") or user.get("id") or "quan_tri")


# ------------------------------------------------------------------ kiểm

def _hh(khoa: str, ghi_de: dict[str, str]) -> str:
    v = str(ghi_de.get(khoa) or "").strip()
    return v or cau_hinh_dong.lay(khoa)


async def _kiem_erpnext(ghi_de: dict[str, str]) -> tuple[bool, str, int]:
    goc = _hh("ERPNEXT_URL", ghi_de).rstrip("/")
    khoa, bi_mat = _hh("ERPNEXT_API_KEY", ghi_de), _hh("ERPNEXT_API_SECRET", ghi_de)
    if not (goc and khoa and bi_mat):
        return False, "Thiếu URL, API Key hoặc API Secret", 0
    t0 = time.perf_counter()
    try:
        # Lời gọi CHỈ ĐỌC rẻ nhất cần xác thực. Tự gọi thay vì
        # `NguonErpNext.suc_khoe()` vì hàm ấy nuốt mã HTTP thành True/False —
        # người vận hành cần biết 401 (sai khoá) khác 404 (sai URL).
        async with httpx.AsyncClient(base_url=goc, timeout=10.0) as c:
            r = await c.get("/api/method/frappe.auth.get_logged_user",
                            headers={"Authorization": f"token {khoa}:{bi_mat}"})
    except httpx.HTTPError as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        return False, _che(f"Không tới được ERPNext: {type(exc).__name__}: {exc}"[:200],
                           khoa, bi_mat), ms
    ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code == 200:
        return True, f"ERPNext xác thực được · {ms}ms", ms
    if r.status_code in (401, 403):
        return False, f"ERPNext từ chối khoá (HTTP {r.status_code}) — kiểm API Key/Secret", ms
    return False, f"ERPNext trả HTTP {r.status_code} — kiểm lại URL", ms


async def kiem_dich_vu(ma: str, ghi_de: dict[str, str]) -> tuple[bool, str, int]:
    """Một lần kiểm THẬT (chỉ đọc) tới dịch vụ. Test vá hàm này, không gọi mạng."""
    if ma == "ai":
        p = (_hh("LLM_PROVIDER", ghi_de) or "gemini").strip().lower()
        khoa_ten = kn.KHOA_THEO_NHA_CUNG_CAP.get(p)
        khoa = _hh(khoa_ten, ghi_de) if khoa_ten else ""
        them: dict[str, Any] = {}
        if p == "openai":
            them["base_url"] = _hh("OPENAI_BASE_URL", ghi_de)
        # Kiểm bằng MODEL_CHAT — model khách thật sự gặp. Kiểm bằng model rẻ
        # thì xanh cả khi MODEL_CHAT là model của nhà cung cấp khác.
        ok, ct, ms = await llm.kiem_khoa(provider_name=p, api_key=khoa,
                                         model=_hh("MODEL_CHAT", ghi_de), **them)
        return ok, _che(ct, khoa), ms
    if ma == "erpnext":
        return await _kiem_erpnext(ghi_de)
    if ma == "ghn":
        token = _hh("GHN_TOKEN", ghi_de)
        ok, ct, ms = await ghn.kiem_ket_noi(token=token, shop_id=_hh("GHN_SHOP_ID", ghi_de))
        return ok, _che(ct, token), ms
    if ma == "ghtk":
        token = _hh("GHTK_TOKEN", ghi_de)
        ok, ct, ms = await ghtk.kiem_ket_noi(token=token,
                                             ma_doi_tac=_hh("GHTK_MA_DOI_TAC", ghi_de))
        return ok, _che(ct, token), ms
    raise HTTPException(422, f"dịch vụ {ma!r} không có phép kiểm kết nối")


# ------------------------------------------------------------------ thẻ dịch vụ

def _ghi_chu(ma: str) -> list[str]:
    """Điều người vận hành phải biết mà ô nhập không nói ra."""
    ra: list[str] = []
    if ma == "erpnext" and (settings.erp_loai or "tep").strip().lower() != "erpnext":
        ra.append(f"ERP_LOAI trong .env đang là '{settings.erp_loai}': kết nối lưu và kiểm "
                  "được, nhưng hệ thống CHƯA dùng ERPNext. Bật ERPNext theo các bước trong "
                  "docs/van-hanh.md rồi khởi động lại.")
    if ma in ("ghn", "ghtk"):
        hang = (settings.shipping_provider or "").strip().lower()
        if hang != ma:
            ra.append(f"SHIPPING_PROVIDER trong .env đang là '{hang}': vận đơn chưa tạo qua "
                      f"{ma.upper()}. Đổi ở .env rồi khởi động lại — có chủ ý không đổi được "
                      "trên dashboard vì vận đơn thật không xoá được.")
        url = settings.ghn_api_url if ma == "ghn" else settings.ghtk_api_url
        if "dev-online" in url or "staging" in url:
            ra.append("Đang trỏ máy chủ THỬ NGHIỆM của hãng — token thật của cửa hàng sẽ báo lỗi.")
    if ma in kn.DICH_VU and ma != "thong_bao_ai":
        ra.append("Đổi khoá/URL có hiệu lực ngay, không cần khởi động lại.")
    return ra


def _kiem_cong_khai(ma: str, kiem: dict | None) -> dict | None:
    if not kiem:
        return None
    return {
        "ok": kiem["ok"], "chi_tiet": kiem["chi_tiet"], "ms": kiem["ms"],
        "luc": kiem["kiem_luc"].isoformat() if kiem.get("kiem_luc") else None,
        "boi": kiem.get("kiem_boi"),
        # Lần kiểm đã cũ (giá trị đổi sau đó) vẫn hiện, nhưng có cờ để giao
        # diện nói rõ "kết quả này cho bộ khoá TRƯỚC".
        "con_hieu_luc": kiem.get("dau_van_tay") == kn.dau_van_tay(ma),
    }


def the_dich_vu(ma: str, kiem: dict[str, dict], tk_webhook: dict[str, dict]) -> dict[str, Any]:
    d = kn.lay_dich_vu(ma)
    tt = kn.trang_thai(ma, kiem.get(ma)) if d.kiem_duoc else ""
    the: dict[str, Any] = {
        "ma": d.ma, "ten": d.ten, "mo_ta": d.mo_ta, "kiem_duoc": d.kiem_duoc,
        "truong": kn.mo_ta_truong(ma), "thieu": kn.thieu(ma),
        "trang_thai": tt, "nhan_trang_thai": kn.NHAN_TRANG_THAI.get(tt, ""),
        "kiem": _kiem_cong_khai(ma, kiem.get(ma)), "ghi_chu": _ghi_chu(ma), "webhook": None,
    }
    if d.webhook:
        bm = kn.bi_mat_webhook_van_chuyen() if d.webhook.bi_mat_url else None
        url = kn.url_cong_khai(d.webhook.duong)
        if bm is not None:
            url += "?token=" + (bm["hien"] or "<chưa đặt SHIPPING_WEBHOOK_SECRET>")
        the["webhook"] = {
            "url": url, "xac_minh": d.webhook.xac_minh, "su_kien": list(d.webhook.su_kien),
            "bi_mat": bm, "thong_ke": tk_webhook.get(ma, {}),
            "lay_bi_mat": ("Bí mật đầy đủ không hiện trên dashboard. Lấy trong .env "
                           "(SHIPPING_WEBHOOK_SECRET) hoặc sinh mới bằng: "
                           "python -m scripts.sinh_token SHIPPING_WEBHOOK_SECRET"),
        }
    return the


# ------------------------------------------------------------------ plugin kênh

def _meta_webhook() -> dict[str, Any]:
    from agent.channels.webhook_app_meta import TRUONG_CAN

    return {"duong": "/webhook/native/meta", "so": "meta", "theo_tai_khoan": False,
            "xac_minh": ("Chữ ký X-Hub-Signature-256 bằng App Secret. Lúc khai trên Meta "
                         "cần verify token — nút 'Verify token' ở từng Trang (quyền kenh.sua)."),
            "su_kien": list(TRUONG_CAN)}


def _zalo_oa_webhook() -> dict[str, Any]:
    from agent.channels.zalo_oa import SU_KIEN_KHACH

    return {"duong": "/webhook/native/zalo-oa/{id}", "so": "zalo_oa", "theo_tai_khoan": True,
            "xac_minh": "Chữ ký X-ZEvent-Signature bằng OA Secret Key riêng của từng OA.",
            "su_kien": sorted(SU_KIEN_KHACH)}


# Mô tả hiển thị cho từng kênh. Danh sách KÊNH lấy từ `factory` (nơi adapter
# thật được chọn); bảng này chỉ thêm chữ — test bắt kênh mới quên mô tả.
PLUGIN_MO_TA: dict[str, dict[str, Any]] = {
    "facebook": {"ten": "Facebook Messenger", "cach_noi": "Đăng nhập Facebook, chọn Trang",
                 "webhook": _meta_webhook},
    "instagram": {"ten": "Instagram", "cach_noi": "Nối cùng Trang Facebook đã liên kết",
                  "webhook": _meta_webhook},
    "whatsapp": {"ten": "WhatsApp", "cach_noi": "Nhập Phone number ID và token từ Meta",
                 "webhook": _meta_webhook},
    "zalo_oa": {"ten": "Zalo OA", "cach_noi": "Đăng nhập Zalo, chọn OA",
                "webhook": _zalo_oa_webhook},
    "zalo_personal": {"ten": "Zalo cá nhân", "cach_noi": "Quét QR bằng app Zalo",
                      "webhook": lambda: {
                          "duong": "/webhook/native/zalo-personal/{id}", "so": "zalo_personal",
                          "theo_tai_khoan": True, "noi_bo": True,
                          "xac_minh": ("Sidecar gọi NỘI BỘ (127.0.0.1), không dán ở đâu. Chữ ký "
                                       "HMAC bằng ZALO_SIDECAR_SECRET — bí mật của máy chủ trong "
                                       ".env; lệch thì khởi động lại sidecar."),
                          "su_kien": ["Tin nhắn mới (riêng và nhóm)"]}},
    "webchat": {"ten": "Chat trên website", "cach_noi": "Dán đoạn mã vào website",
                "webhook": lambda: None},
    "zalocrm": {"ten": "ZaloCRM (kênh cũ)", "cach_noi": "Khoá API trong .env",
                "webhook": lambda: None},
    "chatwoot": {"ten": "Chatwoot (kênh cũ)", "cach_noi": "Khoá API trong .env",
                 "webhook": lambda: {"duong": "/webhook/chatwoot", "so": "chatwoot",
                                     "theo_tai_khoan": False,
                                     "xac_minh": "Bí mật WEBHOOK_SECRET trong .env.",
                                     "su_kien": ["message_created"]}},
    "messenger": {"ten": "Messenger (kênh cũ, token trong .env)",
                  "cach_noi": "Token Trang trong .env",
                  "webhook": lambda: {"duong": "/webhook/messenger", "so": "messenger",
                                      "theo_tai_khoan": False,
                                      "xac_minh": "Chữ ký X-Hub-Signature-256 bằng App Secret.",
                                      "su_kien": ["messages"]}},
}


def _adapter_theo_kenh() -> dict[str, tuple[type[ChannelAdapter], bool]]:
    ra: dict[str, tuple[type[ChannelAdapter], bool]] = {}
    for kenh, lop in factory._NATIVE_ADAPTERS.items():
        ra[kenh.value] = (lop, False)
    for kenh, lop in factory._LEGACY_ADAPTERS.items():
        ra[kenh.value] = (lop, True)
    return ra


def _doi_tuong_json(v: Any) -> dict:
    """JSONB đọc ra: dict như thường, nhưng dòng cũ từng bị mã hoá JSON hai lần
    vẫn còn trong CSDL đang chạy dưới dạng CHUỖI."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return {}
    return v if isinstance(v, dict) else {}


def _trang_thai_tai_khoan(status: str, co_khoa: bool, la_cu: bool) -> str:
    if status == "disabled":
        return "tat"
    if not co_khoa and not la_cu:
        return kn.CHUA_CAU_HINH
    if status == "active":
        return kn.THANH_CONG
    if status in ("degraded", "reauth_required"):
        return kn.LOI
    return kn.CHUA_KIEM_TRA


async def plugin_kenh() -> list[dict[str, Any]]:
    rows = await db.fetch(
        """
        SELECT a.id, a.channel, a.display_name, a.status, a.is_legacy, a.metadata,
               EXISTS (SELECT 1 FROM credential_secrets c WHERE c.account_id = a.id) AS co_khoa,
               h.code AS h_code, h.detail AS h_detail, h.observed_at AS h_luc
        FROM channel_accounts a
        LEFT JOIN LATERAL (
            SELECT code, detail, observed_at FROM account_health_events
            WHERE account_id = a.id ORDER BY observed_at DESC LIMIT 1
        ) h ON true
        ORDER BY a.channel, a.display_name
        """)
    try:
        tk = await kn.thong_ke_webhook_tai_khoan([r["id"] for r in rows])
    except Exception:  # noqa: BLE001 — bảng chưa migrate: mất phần số liệu, còn danh sách
        tk = {}
    an_chung = cau_hinh_dong.lay("AN_BINH_LUAN_CO_SDT")
    theo_kenh: dict[str, list[dict]] = {}
    for r in rows:
        meta, ct = _doi_tuong_json(r["metadata"]), _doi_tuong_json(r["h_detail"])
        tt = _trang_thai_tai_khoan(r["status"], r["co_khoa"], r["is_legacy"])
        tai_khoan: dict[str, Any] = {
            "id": str(r["id"]), "display_name": r["display_name"], "status": r["status"],
            "bat": r["status"] != "disabled", "co_credential": r["co_khoa"],
            "trang_thai": tt, "nhan_trang_thai": kn.NHAN_TRANG_THAI.get(tt, "Đang tắt"),
            "kiem": ({"code": r["h_code"], "ly_do": str(ct.get("ly_do") or "")[:200] or None,
                      "luc": r["h_luc"].isoformat()} if r["h_luc"] else None),
            "webhook": tk.get(str(r["id"]), {}),
        }
        if r["channel"] in ("facebook", "messenger"):
            from agent.omnichannel.xu_ly_tin_vao import TUY_CHON_AN_BINH_LUAN

            rieng = str(meta.get(TUY_CHON_AN_BINH_LUAN) or "")
            tai_khoan["an_binh_luan_co_sdt"] = {
                "rieng": rieng if rieng in ("bat", "tat") else None, "chung": an_chung}
        theo_kenh.setdefault(r["channel"], []).append(tai_khoan)

    so_webhook = [m["webhook"]()["so"] for m in PLUGIN_MO_TA.values() if m["webhook"]()]
    try:
        tk_dv = await kn.thong_ke_webhook(sorted(set(so_webhook)))
    except Exception:  # noqa: BLE001
        tk_dv = {}
    ra = []
    for kenh, (lop, la_cu) in _adapter_theo_kenh().items():
        if la_cu and not theo_kenh.get(kenh):
            continue          # kênh cũ không còn tài khoản nào: không làm rối màn hình
        mo_ta = PLUGIN_MO_TA[kenh]
        wh = mo_ta["webhook"]()
        if wh:
            # Đường nội bộ (sidecar) chỉ hiện ĐƯỜNG DẪN: ghép với tên miền công
            # khai là mời người ta đi dán nó vào một chỗ không cần.
            wh = {**wh, "url": wh["duong"] if wh.get("noi_bo") else kn.url_cong_khai(wh["duong"]),
                  "thong_ke": tk_dv.get(wh["so"], {})}
            if wh["theo_tai_khoan"]:
                for t in theo_kenh.get(kenh, []):
                    t["url_webhook"] = wh["url"].replace("{id}", t["id"])
        ra.append({
            "ma": kenh, "ten": mo_ta["ten"], "cach_noi": mo_ta["cach_noi"], "ke_thua": la_cu,
            "kha_nang": [{"ma": k, "nhan": KHA_NANG[k], "co": bool(lop.KHA_NANG_KENH.get(k))}
                         for k in KHA_NANG],
            "webhook": wh, "tai_khoan": theo_kenh.get(kenh, []),
        })
    return ra


# ------------------------------------------------------------------ endpoint

@router.get("")
async def tong_quan(_: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    kiem = await kn.doc_ket_qua_kiem()
    try:
        tk = await kn.thong_ke_webhook([m for m in DICH_VU_TICH_HOP
                                        if kn.DICH_VU[m].webhook])
    except Exception:  # noqa: BLE001
        tk = {}
    return {
        "dich_vu": [the_dich_vu(m, kiem, tk) for m in DICH_VU_TICH_HOP],
        "kenh": await plugin_kenh(),
        "vault_san_sang": cau_hinh_dong.vault_san_sang(),
        "dia_chi_cong_khai": settings.public_base_url,
    }


# Nhà cung cấp AI mà `llm.complete` THẬT SỰ có nhánh gọi. `ho` là họ model
# chạy được trên nó; `endpoint` = có cho đổi địa chỉ máy chủ hay không. Test
# bắt bảng này lệch với `cau_hinh_dong.PROVIDER_HOP_LE`.
NHA_CUNG_CAP_AI: tuple[dict[str, Any], ...] = (
    {"ma": "gemini_api", "ten": "Google Gemini — API key", "ho": "gemini",
     "khoa": "GEMINI_API_KEY", "ho_tro": True, "endpoint": False,
     "ghi_chu": "Khoá lấy ở Google AI Studio. Endpoint cố định của Google, không đổi được."},
    {"ma": "gemini", "ten": "Google Gemini — Vertex AI (gcloud)", "ho": "gemini",
     "khoa": None, "ho_tro": True, "endpoint": False,
     "ghi_chu": "Xác thực bằng gcloud trên máy chủ + GCP_PROJECT_ID trong .env — không có "
                "khoá nào để nhập ở đây."},
    {"ma": "anthropic", "ten": "Anthropic Claude — API key", "ho": "claude",
     "khoa": "ANTHROPIC_API_KEY", "ho_tro": True, "endpoint": False,
     "ghi_chu": "Endpoint cố định của Anthropic — hệ thống chưa hỗ trợ đổi endpoint."},
    {"ma": "vertex", "ten": "Anthropic Claude — Vertex AI (gcloud)", "ho": "claude",
     "khoa": None, "ho_tro": True, "endpoint": False,
     "ghi_chu": "Xác thực bằng gcloud + GCP_PROJECT_ID, GCP_REGION trong .env."},
    {"ma": "openai", "ten": "OpenAI — API key", "ho": "gpt",
     "khoa": "OPENAI_API_KEY", "ho_tro": True, "endpoint": True,
     "ghi_chu": "Đổi endpoint (OPENAI_BASE_URL) để dùng dịch vụ tương thích OpenAI."},
)

MODEL_DUNG_CHO = {
    "MODEL_CHAT": "Trả lời khách — mọi lượt agent. Nút Kiểm tra kết nối gọi đúng model này.",
    "MODEL_HARD": "Dành cho việc khó. HIỆN CHƯA có tác vụ nào dùng — lưu được nhưng "
                  "chưa đổi hành vi nào.",
    "MODEL_CHEAP": "Phép kiểm sức khoẻ hệ thống định kỳ (một câu 8 token).",
}


def ho_model(model: str) -> str:
    m = (model or "").lower()
    for tien_to, ho in (("claude", "claude"), ("gemini", "gemini"), ("gpt", "gpt")):
        if m.startswith(tien_to):
            return ho
    return ""


def canh_bao_ai() -> list[str]:
    p = (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").strip().lower()
    ncc = next((n for n in NHA_CUNG_CAP_AI if n["ma"] == p), None)
    if ncc is None:
        return [f"LLM_PROVIDER = {p!r} không có trong danh sách hỗ trợ — agent sẽ không trả lời."]
    ra = []
    for khoa in ("MODEL_CHAT", "MODEL_CHEAP"):
        m = cau_hinh_dong.lay(khoa)
        if m and ho_model(m) != ncc["ho"]:
            ra.append(f"{khoa} = {m} không chạy được trên {ncc['ten']} — chọn một model "
                      f"họ {ncc['ho']}.")
    return ra


@router.get("/ai")
async def cau_hinh_ai(_: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    from agent.omnichannel import thong_bao_ai

    kiem = await kn.doc_ket_qua_kiem()
    model_theo_ho: dict[str, list[str]] = {}
    for m in sorted(llm.PRICING):
        model_theo_ho.setdefault(ho_model(m), []).append(m)
    try:
        xem_truoc = thong_bao_ai.cau_thong_bao()
    except Exception as exc:  # noqa: BLE001 — danh mục hỏng không được làm sập màn
        xem_truoc = f"(không dựng được xem trước: {type(exc).__name__})"
    return {
        "nha_cung_cap": list(NHA_CUNG_CAP_AI),
        "dang_chon": (cau_hinh_dong.lay("LLM_PROVIDER") or "gemini").strip().lower(),
        "the": the_dich_vu("ai", kiem, {}),
        "model_theo_ho": model_theo_ho,
        "model_dung_cho": MODEL_DUNG_CHO,
        "canh_bao": canh_bao_ai(),
        "gcp_san_sang": kn._gcp_san_sang(),
        "thong_bao_ai": {
            "the": the_dich_vu("thong_bao_ai", kiem, {}),
            "mac_dinh": str(Settings.model_fields["tin_thong_bao_ai"].default),
            "xem_truoc": xem_truoc,
            "chong_lap": ("Mỗi hội thoại nhận câu này ĐÚNG MỘT LẦN, ở tin đầu agent trả lời. "
                          "Sửa nội dung không gửi lại cho hội thoại đã được báo; hội thoại "
                          "mới nhận câu mới."),
        },
        "vault_san_sang": cau_hinh_dong.vault_san_sang(),
    }


class LuuIn(BaseModel):
    gia_tri: dict[str, str] = Field(default_factory=dict)


@router.put("/dich-vu/{ma}")
async def luu_dich_vu(ma: str, body: LuuIn,
                      user: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    d = kn.DICH_VU.get(ma)
    if d is None:
        raise HTTPException(404, f"không có dịch vụ {ma!r}")
    la = sorted(set(body.gia_tri) - set(d.khoa))
    if la:
        # Từ chối CẢ yêu cầu: lưu một nửa rồi báo lỗi nửa kia là để người ta
        # tưởng chưa lưu gì.
        raise HTTPException(422, f"trường không thuộc {d.ten}: {', '.join(la)}")
    da_luu: list[str] = []
    hong: list[dict[str, str]] = []
    for khoa, v in body.gia_tri.items():
        if not str(v or "").strip():
            continue          # ô trống = giữ giá trị đang lưu
        try:
            await cau_hinh_dong.dat(khoa, v, sua_boi=_actor(user))
            da_luu.append(khoa)
        except cau_hinh_dong.KhoaKhongHopLe as exc:
            hong.append({"khoa": khoa, "loi": str(exc)})
        except cau_hinh_dong.VaultChuaSanSang as exc:
            raise HTTPException(503, str(exc)) from exc
    return {"da_luu": da_luu, "hong": hong}


@router.delete("/dich-vu/{ma}/{khoa}")
async def xoa_truong(ma: str, khoa: str,
                     user: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    d = kn.DICH_VU.get(ma)
    if d is None or khoa not in d.khoa:
        raise HTTPException(404, "không có trường này")
    await cau_hinh_dong.xoa(khoa, sua_boi=_actor(user))
    return {"da_xoa": khoa, "nguon_moi": cau_hinh_dong.nguon(khoa)}


class KiemIn(BaseModel):
    gia_tri: dict[str, str] = Field(default_factory=dict)


@router.post("/dich-vu/{ma}/kiem-tra")
async def kiem_tra(ma: str, body: KiemIn,
                   user: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict[str, Any]:
    d = kn.DICH_VU.get(ma)
    if d is None or not d.kiem_duoc:
        raise HTTPException(404, f"dịch vụ {ma!r} không có phép kiểm kết nối")
    la = sorted(set(body.gia_tri) - set(d.khoa))
    if la:
        raise HTTPException(422, f"trường không thuộc {d.ten}: {', '.join(la)}")
    ok, chi_tiet, ms = await kiem_dich_vu(ma, body.gia_tri)
    # Chỉ đóng dấu trạng thái khi lần kiểm chạy ĐÚNG bộ giá trị đang lưu.
    # Dán một khoá khác vào ô rồi thấy xanh, mà màn hình ghi xanh cho khoá
    # đang lưu, là nói dối.
    dung_gia_tri_luu = all(not str(v or "").strip() or str(v).strip() == cau_hinh_dong.lay(k)
                           for k, v in body.gia_tri.items())
    da_ghi = False
    if dung_gia_tri_luu:
        try:
            await kn.ghi_ket_qua_kiem(ma, ok=ok, chi_tiet=chi_tiet, ms=ms,
                                      van_tay=kn.dau_van_tay(ma), boi=_actor(user))
            da_ghi = True
        except Exception as exc:  # noqa: BLE001 — kết quả vẫn trả về cho người bấm
            await db.log_event("ket_noi.ghi_kiem_loi", dich_vu=ma,
                               loi=f"{type(exc).__name__}: {exc}"[:200])
    tt = (kn.THANH_CONG if ok else kn.LOI) if dung_gia_tri_luu else kn.trang_thai(
        ma, (await kn.doc_ket_qua_kiem()).get(ma))
    return {"ok": ok, "chi_tiet": chi_tiet, "ms": ms, "da_ghi": da_ghi,
            "dung_gia_tri_luu": dung_gia_tri_luu, "trang_thai": tt,
            "nhan_trang_thai": kn.NHAN_TRANG_THAI.get(tt, "")}


@router.get("/webhook")
async def lich_su_webhook(
    dich_vu: str | None = None, account_id: UUID | None = None, gioi_han: int = 50,
    _: dict = Depends(can_quyen("cau_hinh.sua")),
) -> dict[str, Any]:
    if not dich_vu and account_id is None:
        raise HTTPException(422, "cần dich_vu hoặc account_id")
    return await kn.lich_su_webhook(dich_vu=dich_vu, account_id=account_id, gioi_han=gioi_han)


@router.get("/lich-su")
async def lich_su(dich_vu: str | None = None, gioi_han: int = 50,
                  _: dict = Depends(can_quyen("cau_hinh.sua"))) -> list[dict[str, Any]]:
    return await kn.doc_lich_su(dich_vu=dich_vu, gioi_han=gioi_han)


class TuyChonKenhIn(BaseModel):
    # "chung" = bỏ tuỳ chọn riêng, Trang theo cấu hình chung AN_BINH_LUAN_CO_SDT.
    an_binh_luan_co_sdt: Literal["bat", "tat", "chung"]


@router.put("/kenh/{account_id}/tuy-chon")
async def tuy_chon_kenh(account_id: UUID, body: TuyChonKenhIn,
                        user: dict = Depends(can_quyen("kenh.sua"))) -> dict[str, Any]:
    from agent.omnichannel.xu_ly_tin_vao import TUY_CHON_AN_BINH_LUAN

    r = await db.fetchrow("SELECT channel, display_name FROM channel_accounts WHERE id = $1",
                          account_id)
    if r is None:
        raise HTTPException(404, "Không tìm thấy tài khoản kênh")
    if r["channel"] not in (Channel.FACEBOOK.value, Channel.LEGACY_MESSENGER.value):
        # Chỉ Trang Facebook có bình luận dưới bài đăng đi vào hộp thư.
        raise HTTPException(422, "Chỉ Trang Facebook có tuỳ chọn ẩn bình luận")
    if body.an_binh_luan_co_sdt == "chung":
        await db.execute("UPDATE channel_accounts SET metadata = metadata - $2, "
                         "updated_at = now() WHERE id = $1", account_id, TUY_CHON_AN_BINH_LUAN)
    else:
        await db.execute(
            "UPDATE channel_accounts SET metadata = metadata || jsonb_build_object($2::text, "
            "$3::text), updated_at = now() WHERE id = $1",
            account_id, TUY_CHON_AN_BINH_LUAN, body.an_binh_luan_co_sdt)
    await kn.ghi_lich_su(dich_vu=r["channel"], truong=TUY_CHON_AN_BINH_LUAN,
                         hanh_dong="doi_tuy_chon", sua_boi=_actor(user),
                         account_id=account_id, doi_tuong=r["display_name"])
    await db.log_event("kenh.tuy_chon", actor=_actor(user), ref_id=account_id,
                       truong=TUY_CHON_AN_BINH_LUAN, gia_tri=body.an_binh_luan_co_sdt)
    return {"account_id": str(account_id), "an_binh_luan_co_sdt": body.an_binh_luan_co_sdt}
