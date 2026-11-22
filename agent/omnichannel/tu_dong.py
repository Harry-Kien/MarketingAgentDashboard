"""
Quy tắc tự động hoá: SỰ KIỆN → ĐIỀU KIỆN → HÀNH ĐỘNG (bảng `quy_tac_tu_dong`).

    khi khách nhắn tin  →  nếu [kênh, từ khoá, ngoài giờ, tin đầu,
                               nhãn HỘI THOẠI, nhãn KHÁCH]
                        →  gắn nhãn hội thoại · gắn nhãn khách · gửi mẫu trả
                           lời nhanh · tạo việc · chuyển người

NHÃN THEO ID, HAI LOẠI TÁCH BẠCH (mục 7.8)
------------------------------------------
Điều kiện và hành động về nhãn trỏ vào DANH MỤC nhãn (0056) bằng id, và
tên khoá nói rõ loại: `nhan_hoi_thoai_co` khác `nhan_khach_co`. Quy tắc cũ
viết bằng CHỮ (`nhan_co`, `nhan_khong`, `gan_nhan` + `nhan`) đã được
migration 0056 đổi sang id. Khoá cũ nào còn sót vẫn chạy như trước — so
theo TÊN nhãn hội thoại đang gắn; gắn nhãn chữ thì tra danh mục, không có
thì hành động ấy ghi "hỏng" kèm lý do (không tự tạo nhãn). API lưu quy tắc
đổi khoá cũ sang id hoặc từ chối 422 (agent/api/tu_dong_api.py).

DANH SÁCH ĐÓNG
--------------
Điều kiện và hành động chỉ chọn trong `DIEU_KIEN` / `HANH_DONG` dưới đây;
khoá lạ là lỗi ngay lúc lưu. Đây là điểm khác n8n, và là chủ ý: một quy tắc
không thể gọi URL tuỳ ý, không thể chạy mã, không thể đọc biến môi trường —
cùng lý do kỹ năng cắm thêm là DỮ LIỆU (CLAUDE.md).

BA CHỐT
-------
  1. Gửi tin chỉ bằng MẪU TRẢ LỜI NHANH, và mẫu được kiểm lại từ cấm quảng
     cáo LÚC GỬI (mẫu có thể đã bị sửa sau khi tạo quy tắc), đi qua outbox
     với kiểm cửa sổ gửi của kênh như mọi tin khác.
  2. Gửi tin / tạo việc tối đa MỘT lần mỗi hội thoại cho mỗi quy tắc —
     khách nhắn mười tin liền không nhận mười câu chào.
  3. Hỏng KHÔNG chặn tin của khách: ghi `quy_tac_lan_chay` (hong) và
     `events` (tu_dong.loi), rồi luồng thường chạy tiếp. Hỏng mà im lặng là
     quy tắc "đang bật" không bao giờ làm gì — không ai biết.

THỨ TỰ VÀ XUNG ĐỘT (mục 7.6–7.7, migration 0060)
-------------------------------------------------
Quy tắc chạy TRƯỚC agent (xu_ly_tin_vao.py), theo `thu_tu` tăng dần; cùng
số thì quy tắc tạo trước chạy trước, cùng lúc tạo thì theo `id` — một bộ
quy tắc luôn chạy đúng một thứ tự. Nhiều quy tắc cùng khớp một tin thì:

  a. KHÁCH NHẬN TỐI ĐA MỘT TIN TỰ ĐỘNG cho mỗi tin của khách. Tin ấy là
     của quy tắc khớp ĐẦU TIÊN có thứ gì để nói: mẫu nó gửi, hoặc câu báo
     chuyển người cố định nếu nó chuyển người mà không gửi mẫu. Mẫu của
     các quy tắc sau bị BỎ QUA, ghi rõ trong nhật ký lần chạy. Một quy tắc
     vừa gửi mẫu vừa chuyển người thì mẫu chính là câu báo — không gửi
     thêm câu báo cố định (thứ tự hai hành động trong quy tắc không đổi
     điều này).
  b. Nhãn GỘP: mọi nhãn của mọi quy tắc khớp đều được gắn (gắn lại là vô
     hại), và quy tắc sau THẤY nhãn quy tắc trước vừa gắn.
  c. Công việc GỘP theo tiêu đề: hai quy tắc tạo cùng một tiêu đề cho một
     tin thì chỉ một việc.
  d. Chuyển người: quy tắc đầu tiên thắng, các lần sau không ghi lại.
  e. "Dừng xét quy tắc sau" (`dung_xet_sau`): quy tắc có cờ này KHỚP thì
     các quy tắc xếp sau không được xét cho tin này.

QUY TẮC VÀ AI KHÔNG CÙNG TRẢ LỜI MỘT TIN
---------------------------------------
Quy tắc đã gửi mẫu cho tin này thì AI KHÔNG trả lời CHÍNH tin ấy (`ai_nhuong`)
— trừ khi quy tắc đã gửi bật `cho_ai_tra_loi`. Tin sau của khách AI vẫn trả
lời bình thường. Quy tắc chuyển người thì agent dừng hẳn (`dung_agent`).

KHI NÀO QUY TẮC KHÔNG ĐƯỢC NÓI VỚI KHÁCH
----------------------------------------
Gắn nhãn, tạo việc, chuyển người vẫn chạy; riêng GỬI MẪU thì bỏ qua (ghi lý
do) khi: agent tắt toàn hệ thống; nhân viên đang tiếp hoặc hội thoại đang
chờ người (`mode='human'` / `status='escalated'`); hội thoại bật "Duyệt
trước khi gửi"; khách đã đòi gặp nhân viên (NĐ 356/2025 Đ.10 k.3 — quyền
không bị xử lý tự động); hội thoại NHÓM. Tin nhóm thậm chí không tới đây —
`handle_inbound` giao người trước mọi nhánh; outbox chặn thêm lần nữa.
Ngoài cửa sổ gửi của kênh thì hành động ghi "hỏng" (chốt 1).
"""
from __future__ import annotations

import json
import logging
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

from agent.omnichannel.accounts import Channel

logger = logging.getLogger(__name__)

SU_KIEN = ("tin_khach",)
# Lấy từ Channel, không gõ tay: thêm kênh mới mà quên ở đây là quy tắc theo
# kênh ấy bị từ chối lúc lưu — dễ thấy, nhưng vẫn là một bước người ta quên.
KENH = tuple(c.value for c in Channel)
DIEU_KIEN = ("kenh", "chua_tu", "ngoai_gio", "lan_dau",
             "nhan_hoi_thoai_co", "nhan_hoi_thoai_khong",
             "nhan_khach_co", "nhan_khach_khong")
# Khoá chữ tự do trước 0056 — vẫn đọc được, không còn là đường chính.
DIEU_KIEN_CU = ("nhan_co", "nhan_khong")
HANH_DONG = ("gan_nhan_hoi_thoai", "gan_nhan_khach", "gui_mau", "tao_viec", "chuyen_nguoi")
HANH_DONG_CU = ("gan_nhan",)
# Điều kiện nhãn -> loại nhãn nó được phép trỏ tới. API kiểm loại theo bảng
# này; trộn nhầm loại là quy tắc không bao giờ khớp mà trông vẫn đúng.
DIEU_KIEN_NHAN = {"nhan_hoi_thoai_co": "hoi_thoai", "nhan_hoi_thoai_khong": "hoi_thoai",
                  "nhan_khach_co": "khach", "nhan_khach_khong": "khach"}
HANH_DONG_NHAN = {"gan_nhan_hoi_thoai": "hoi_thoai", "gan_nhan_khach": "khach"}
TOI_DA_NHAN = 10
# Làm tối đa một lần mỗi hội thoại (chốt 2). Gắn nhãn/chuyển người lặp lại vô hại.
MOT_LAN = frozenset({"gui_mau", "tao_viec"})
DUY_NHAT_MOI_QUY_TAC = ("gui_mau", "tao_viec", "chuyen_nguoi")
TOI_DA_HANH_DONG = 5
TOI_DA_TU_KHOA = 30


class QuyTacHong(ValueError):
    """Quy tắc không hợp lệ — thông báo đọc được cho người vận hành."""


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower()).replace("đ", "d")
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- kiểm (thuần)

def _ds_chu(gt: Any, ten: str, toi_da: int = TOI_DA_TU_KHOA) -> list[str]:
    if not isinstance(gt, list) or not all(isinstance(x, str) for x in gt):
        raise QuyTacHong(f"{ten} phải là danh sách chữ")
    ra = [x.strip() for x in gt if x.strip()]
    if not ra or len(ra) > toi_da:
        raise QuyTacHong(f"{ten} cần 1–{toi_da} mục")
    if any(len(x) > 60 for x in ra):
        raise QuyTacHong(f"mỗi mục trong {ten} tối đa 60 ký tự")
    return ra


def _ds_id(gt: Any, ten: str) -> list[str]:
    if not isinstance(gt, list) or not 1 <= len(gt) <= TOI_DA_NHAN:
        raise QuyTacHong(f"{ten} cần 1–{TOI_DA_NHAN} nhãn (id trong danh mục)")
    ra: list[str] = []
    for x in gt:
        try:
            ma = str(uuid.UUID(str(x)))
        except ValueError:
            raise QuyTacHong(f"{ten}: «{x}» không phải id nhãn — chọn nhãn trong danh mục") from None
        if ma not in ra:
            ra.append(ma)
    return ra


def kiem_dieu_kien(dk: Any) -> dict[str, Any]:
    if not isinstance(dk, dict):
        raise QuyTacHong("điều kiện phải là object")
    la = set(dk) - set(DIEU_KIEN) - set(DIEU_KIEN_CU)
    if la:
        raise QuyTacHong(f"điều kiện không có: {', '.join(sorted(la))}")
    ra: dict[str, Any] = {}
    if "kenh" in dk:
        kenh = _ds_chu(dk["kenh"], "kenh", len(KENH))
        if set(kenh) - set(KENH):
            raise QuyTacHong(f"kênh không có: {', '.join(sorted(set(kenh) - set(KENH)))}")
        ra["kenh"] = kenh
    if "chua_tu" in dk:
        ra["chua_tu"] = _ds_chu(dk["chua_tu"], "chua_tu")
    for k in ("ngoai_gio", "lan_dau"):
        if k in dk:
            if not isinstance(dk[k], bool):
                raise QuyTacHong(f"{k} phải là true/false")
            ra[k] = dk[k]
    for k in DIEU_KIEN_NHAN:
        if k in dk:
            ra[k] = _ds_id(dk[k], k)
    # "CÓ nhãn X" và "CHƯA có nhãn X" cùng lúc: quy tắc không bao giờ khớp mà
    # vẫn trông "đang bật" — loại hỏng im lặng phải chặn lúc bấm Lưu.
    for loai in ("hoi_thoai", "khach"):
        trung = set(ra.get(f"nhan_{loai}_co", [])) & set(ra.get(f"nhan_{loai}_khong", []))
        if trung:
            raise QuyTacHong(f"điều kiện mâu thuẫn: cùng một nhãn vừa phải CÓ vừa phải CHƯA có "
                             f"({'nhãn hội thoại' if loai == 'hoi_thoai' else 'nhãn khách'})")
    # Khoá cũ: giữ hình dạng để API đổi sang id (cần CSDL — hàm này thuần).
    for k in DIEU_KIEN_CU:
        if k in dk:
            if not isinstance(dk[k], str) or not 1 <= len(dk[k].strip()) <= 80:
                raise QuyTacHong(f"{k} phải là một nhãn 1–80 ký tự")
            ra[k] = " ".join(dk[k].split()).lower()
    return ra


def kiem_hanh_dong(ds: Any) -> list[dict[str, Any]]:
    if not isinstance(ds, list) or not 1 <= len(ds) <= TOI_DA_HANH_DONG:
        raise QuyTacHong(f"cần 1–{TOI_DA_HANH_DONG} hành động")
    ra = []
    for hd in ds:
        if not isinstance(hd, dict) or hd.get("loai") not in HANH_DONG + HANH_DONG_CU:
            raise QuyTacHong(f"hành động phải là một trong: {', '.join(HANH_DONG)}")
        loai = hd["loai"]
        la = set(hd) - {"loai", "nhan", "nhan_id", "ma_tat", "tieu_de", "ly_do", "giao_tu_dong"}
        if la:
            raise QuyTacHong(f"hành động {loai} có khoá lạ: {', '.join(sorted(la))}")
        if loai in HANH_DONG_NHAN:
            ra.append({"loai": loai, "nhan_id": _ds_id([hd.get("nhan_id")], loai)[0]})
        elif loai == "gan_nhan":
            n = " ".join(str(hd.get("nhan") or "").split()).lower()
            if not 1 <= len(n) <= 80:
                raise QuyTacHong("gan_nhan cần nhan 1–80 ký tự")
            ra.append({"loai": loai, "nhan": n})
        elif loai == "gui_mau":
            ma = str(hd.get("ma_tat") or "").strip().lower()
            if not ma:
                raise QuyTacHong("gui_mau cần ma_tat của một mẫu trả lời nhanh")
            ra.append({"loai": loai, "ma_tat": ma})
        elif loai == "tao_viec":
            td = str(hd.get("tieu_de") or "").strip()
            # 3–120: bảng cong_viec đòi tiêu đề ≥ 3 ký tự — cho lưu "ab" là
            # quy tắc hỏng ở lần chạy đầu tiên thay vì lúc bấm Lưu.
            if not 3 <= len(td) <= 120:
                raise QuyTacHong("tao_viec cần tieu_de 3–120 ký tự")
            tu_giao = hd.get("giao_tu_dong", False)
            if not isinstance(tu_giao, bool):
                raise QuyTacHong("tao_viec: giao_tu_dong phải là true/false")
            # Chỉ lưu khoá khi bật: quy tắc cũ đọc lại y nguyên như trước.
            ra.append({"loai": loai, "tieu_de": td, **({"giao_tu_dong": True} if tu_giao else {})})
        else:
            ra.append({"loai": loai, "ly_do": str(hd.get("ly_do") or "quy tắc tự động").strip()[:200]})
    # Hai mẫu trong một quy tắc là hai tin cho một tin khách — đúng thứ chính
    # sách "một tin tự động mỗi tin khách" cấm; mẫu thứ hai sẽ không bao giờ
    # được gửi, nên cho lưu là để người vận hành tin một điều sai.
    for loai in DUY_NHAT_MOI_QUY_TAC:
        if sum(1 for h in ra if h["loai"] == loai) > 1:
            raise QuyTacHong(f"mỗi quy tắc chỉ có MỘT hành động {loai}")
    nhan = [(h["loai"], h.get("nhan_id") or h.get("nhan")) for h in ra
            if h["loai"] in ("gan_nhan", *HANH_DONG_NHAN)]
    if len(nhan) != len(set(nhan)):
        raise QuyTacHong("một nhãn bị gắn hai lần trong cùng quy tắc")
    return ra


# ---------------------------------------------------------------- khớp (thuần)

@dataclass
class NguCanh:
    kenh: str
    van_ban: str
    ngoai_gio: bool
    lan_dau: bool
    # TÊN nhãn hội thoại (chữ thường) — chỉ để khoá cũ `nhan_co` còn khớp.
    nhan: set[str] = field(default_factory=set)
    nhan_hoi_thoai: set[str] = field(default_factory=set)    # id
    nhan_khach: set[str] = field(default_factory=set)        # id


def khop(dk: dict[str, Any], nc: NguCanh) -> bool:
    """MỌI điều kiện phải đúng (AND). Không điều kiện nào = khớp mọi tin."""
    if "kenh" in dk and nc.kenh not in dk["kenh"]:
        return False
    if "chua_tu" in dk:
        vb = bo_dau(nc.van_ban)
        if not any(bo_dau(t) in vb for t in dk["chua_tu"]):
            return False
    if "ngoai_gio" in dk and dk["ngoai_gio"] != nc.ngoai_gio:
        return False
    if "lan_dau" in dk and dk["lan_dau"] != nc.lan_dau:
        return False
    if "nhan_co" in dk and dk["nhan_co"] not in nc.nhan:
        return False
    if "nhan_khong" in dk and dk["nhan_khong"] in nc.nhan:
        return False
    # "_co": có ÍT NHẤT MỘT nhãn trong danh sách. "_khong": không có nhãn
    # NÀO trong danh sách.
    for k, co in (("nhan_hoi_thoai_co", nc.nhan_hoi_thoai), ("nhan_khach_co", nc.nhan_khach)):
        if k in dk and not set(dk[k]) & co:
            return False
    for k, co in (("nhan_hoi_thoai_khong", nc.nhan_hoi_thoai),
                  ("nhan_khach_khong", nc.nhan_khach)):
        if k in dk and set(dk[k]) & co:
            return False
    return True


# ---------------------------------------------------------------- chạy (IO)

@dataclass
class KetQua:
    dung_agent: bool = False          # có quy tắc chuyển người -> agent không trả lời
    da_lam: list[str] = field(default_factory=list)
    # Đã xếp hàng (hoặc đã thử gửi) MỘT tin cho khách ở tin này: mẫu, hoặc
    # câu báo chuyển người. Nhánh sau trong handle_inbound đọc cờ này để
    # không gửi câu thứ hai.
    da_gui_khach: bool = False
    # AI nhường CHÍNH tin này cho quy tắc (mục 7.7): quy tắc đã gửi mẫu và
    # không bật `cho_ai_tra_loi`.
    ai_nhuong: bool = False
    quy_tac_gui: str | None = None    # tên quy tắc đã nói với khách — cho nhật ký


def _jsonb(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else (v or {})


async def _mot_lan_da_lam(db, quy_tac_id, cid) -> set[str]:
    """
    Hành động MỘT-LẦN nào của quy tắc này đã làm trong hội thoại này.

    Theo TỪNG loại, không theo cả quy tắc: quy tắc "gửi mẫu + tạo việc" mà
    lần đầu mẫu bị bỏ qua (nhân viên đang tiếp, quy tắc khác đã gửi) thì lần
    sau mẫu vẫn còn quyền gửi. Dòng cũ trước 0060 chỉ có `mot_lan: true` —
    coi như mọi hành động một-lần đã làm, đúng nghĩa của nó lúc ghi.
    """
    rows = await db.fetch(
        "SELECT chi_tiet FROM quy_tac_lan_chay WHERE quy_tac_id = $1 AND conversation_id = $2 "
        "AND ket_qua = 'da_lam' AND chi_tiet ? 'mot_lan'", quy_tac_id, cid)
    da: set[str] = set()
    for r in rows:
        ct = _jsonb(r["chi_tiet"])
        da |= set(ct.get("mot_lan_loai") or MOT_LAN)
    return da


async def _gui_mau(db, msg, cid, ma_tat: str, khoa: str) -> str:
    from agent.channels import registry as channels
    from agent.core.cham_mot_luot import tu_cam_hai_dang
    from agent.omnichannel.outbound_service import OutboundService, PostgresOutboundRepository

    mau = await db.fetchrow("SELECT noi_dung FROM tra_loi_nhanh WHERE ma_tat = $1", ma_tat)
    if mau is None:
        raise QuyTacHong(f"không có mẫu trả lời nhanh /{ma_tat}")
    cum = tu_cam_hai_dang(mau["noi_dung"])
    if cum:
        # Chốt 1: mẫu bị sửa thành câu cấm sau khi tạo quy tắc.
        raise QuyTacHong(f"mẫu /{ma_tat} chứa cụm cấm quảng cáo: {', '.join(cum)}")
    adapter = await channels.get_for_account(msg.account_id)
    if not await adapter.can_send_now(msg.conversation_ref):
        raise QuyTacHong("kênh không cho gửi lúc này (ngoài cửa sổ)")
    await OutboundService(PostgresOutboundRepository()).queue_text(
        conversation_id=cid, role="system", text=mau["noi_dung"], idempotency_key=khoa,
        metadata={"tu_dong": True, "ma_tat": ma_tat})
    return f"gửi mẫu /{ma_tat}"


async def _tao_viec(db, cid: uuid.UUID, tieu_de: str, ten_quy_tac: str,
                    giao_tu_dong: bool = False) -> str:
    """
    Việc mang ĐÚNG tiêu đề người vận hành đặt trong quy tắc, nguồn `tu_dong`.

    Đây là việc THẬT do người vận hành chủ ý đặt trong quy tắc — khác với
    chuyển người, vốn chỉ sinh thông báo (mục 14.2). Không chèn được việc
    thì NỔ, để lần chạy ghi "hỏng": nuốt lỗi CSDL ở đây là quy tắc ghi "đã
    tạo việc" cho một việc không tồn tại.

    `giao_tu_dong` (mục 14.5): giao người đang trong ca theo
    `agent/core/giao_viec.py`; không ai đủ điều kiện thì việc ở Chưa phân
    công. Hai đường đều báo chuông — chuông hỏng không làm hỏng quy tắc.
    """
    r = await db.fetchrow(
        "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, conversation_id, contact_id) "
        "SELECT $1, $2, 'tu_dong', $3::uuid, c.contact_id "
        "FROM (SELECT 1) _ LEFT JOIN conversations c ON c.id = $3::uuid RETURNING id",
        tieu_de, f"Tạo bởi quy tắc tự động «{ten_quy_tac}»", str(cid))
    if r is None:
        raise RuntimeError("không tạo được công việc")
    from agent.core import giao_viec

    if giao_tu_dong:
        await giao_viec.giao_tu_dong_va_bao(r["id"])
    else:
        await giao_viec.bao_neu_chua_giao(r["id"], ly_do=f"quy tắc «{ten_quy_tac}»")
    return str(r["id"])


async def _bao_nhan_vien_chuyen(msg, cid: uuid.UUID, ten_quy_tac: str) -> None:
    """
    Nhân viên thấy ghi chú trong hộp thư kênh — như mọi nhánh chuyển người.
    Câu báo cho KHÁCH đi riêng (`_bao_khach_chuyen`), cuối quy tắc, và chỉ
    khi khách chưa nhận tin tự động nào cho tin này (chính sách a).
    """
    from agent.channels import registry as channels
    from agent.omnichannel import xu_ly_tin_vao

    ad = await channels.get_for_account(msg.account_id)
    await xu_ly_tin_vao.bao_nhan_vien_tiep_quan(
        ad, msg.conversation_ref, cid, f"quy tắc tự động «{ten_quy_tac}»")


async def _bao_khach_chuyen(msg, cid: uuid.UUID) -> None:
    """
    Thiếu câu này thì khách nhận im lặng — đúng thứ chuyển người sinh ra để
    tránh (rà soát 28.10.2026). Hàm dưới tự ghi nhật ký khi gửi hỏng.
    """
    from agent.channels import registry as channels
    from agent.omnichannel import xu_ly_tin_vao

    ad = await channels.get_for_account(msg.account_id)
    await xu_ly_tin_vao.bao_khach_dang_chuyen_nguoi(ad, msg.conversation_ref, cid)


async def _ly_do_khong_gui(db, msg, cid: uuid.UUID, nguoi_dang_tiep: bool) -> str | None:
    """
    Vì sao quy tắc KHÔNG được nói với khách ở tin này; None = được nói.

    Đọc trạng thái hội thoại từ CSDL chứ không chỉ tin cờ người gọi đưa:
    hội thoại `escalated` đang chờ người cũng là lúc một câu chào tự động
    chen ngang trước mặt nhân viên sắp vào.
    """
    from agent import runtime
    from agent.channels.base import THREAD_NHOM
    from agent.omnichannel import thong_bao_ai

    if not runtime.enabled():
        return "agent đang tắt toàn hệ thống"
    c = await db.fetchrow(
        "SELECT mode, status, thread_type, duyet_truoc_khi_gui FROM conversations WHERE id = $1",
        cid)
    c = dict(c) if c else {}
    if nguoi_dang_tiep or c.get("mode") == "human" or c.get("status") == "escalated":
        return "nhân viên đang tiếp hội thoại"
    if getattr(msg, "la_nhom", False) or c.get("thread_type") == THREAD_NHOM:
        return "hội thoại nhóm — máy không nói vào nhóm"
    if c.get("duyet_truoc_khi_gui"):
        return "hội thoại đang bật «Duyệt trước khi gửi»"
    if (thong_bao_ai.khach_doi_gap_nguoi(getattr(msg, "text", "") or "")
            or await thong_bao_ai.da_doi_gap_nguoi(cid)):
        return "khách đã đòi gặp nhân viên"
    return None


async def _ghi_loi_su_kien(db, cid, exc: BaseException) -> None:
    logger.exception("tu_dong: không đọc được quy tắc / ngữ cảnh hội thoại %s", cid)
    try:
        await db.log_event("tu_dong.loi", ref_id=cid, loi=f"{type(exc).__name__}: {exc}"[:200])
    except Exception:  # noqa: BLE001
        pass


async def chay_tin_khach(msg, cid: uuid.UUID, *, lan_dau: bool | None = None,
                         nguoi_dang_tiep: bool = False) -> KetQua:
    """
    Chạy mọi quy tắc đang bật cho một tin khách, theo chính sách ở đầu mô-đun.
    Không bao giờ ném.

    `nguoi_dang_tiep`: hội thoại đã ở chế độ người TRƯỚC tin này. Khi ấy
    (và mọi lý do trong `_ly_do_khong_gui`) KHÔNG gửi mẫu: nhân viên đang
    nói chuyện với khách, một câu tự động chen ngang là nói đè lên họ.
    """
    from agent import db
    from agent.core import gio_lam_viec, thong_bao_noi_bo

    kq = KetQua()
    try:
        ds = await db.fetch("SELECT * FROM quy_tac_tu_dong WHERE bat AND su_kien = 'tin_khach' "
                            "ORDER BY thu_tu, tao_luc, id")
    except Exception as exc:  # noqa: BLE001 — bảng chưa có / CSDL lỗi: báo, không chặn tin
        await _ghi_loi_su_kien(db, cid, exc)
        return kq
    if not ds:
        return kq
    try:
        if lan_dau is None:
            # Chỉ đếm khi CÓ quy tắc: cửa hàng không dùng tự động hoá thì
            # tin thường không tốn thêm truy vấn nào.
            r = await db.fetchrow("SELECT count(*) n FROM messages "
                                  "WHERE conversation_id = $1 AND role = 'customer'", cid)
            lan_dau = (r["n"] if r else 0) <= 1
        gan_ht = await db.fetch(
            "SELECT n.id::text AS id, lower(n.ten) AS ten FROM hoi_thoai_gan_nhan g "
            "JOIN nhan n ON n.id = g.nhan_id WHERE g.conversation_id = $1", cid)
        gan_kh = await db.fetch(
            "SELECT g.nhan_id::text AS id FROM conversations c "
            "JOIN khach_gan_nhan g ON g.contact_id = c.contact_id WHERE c.id = $1", cid)
        khong_gui = await _ly_do_khong_gui(db, msg, cid, nguoi_dang_tiep)
    except Exception as exc:  # noqa: BLE001
        await _ghi_loi_su_kien(db, cid, exc)
        return kq
    nc = NguCanh(kenh=str(msg.channel),
                 van_ban=msg.text or "", ngoai_gio=not gio_lam_viec.dang_trong_gio(),
                 lan_dau=lan_dau, nhan={r["ten"] for r in gan_ht},
                 nhan_hoi_thoai={r["id"] for r in gan_ht},
                 nhan_khach={r["id"] for r in gan_kh})
    viec_da_tao: set[str] = set()     # chính sách c — gộp việc cùng tiêu đề
    for qt in ds:
        try:
            if not khop(_jsonb(qt["dieu_kien"]), nc):
                continue
            da_mot_lan = await _mot_lan_da_lam(db, qt["id"], cid)
        except Exception as exc:  # noqa: BLE001
            await _ghi_hong(db, qt, cid, f"{type(exc).__name__}: {exc}"[:300])
            continue
        ten = str(qt["ten"])
        lam: list[str] = []
        loi: list[str] = []
        bo_qua: list[str] = []
        mot_lan_loai: list[str] = []
        chuyen_moi = False
        gui_mau_nay = False
        # MỖI HÀNH ĐỘNG HỎNG RIÊNG. Bản trước để một mẫu hỏng (bị xoá, dính
        # cụm cấm, ngoài cửa sổ gửi) huỷ cả quy tắc — "chuyển người" đứng sau
        # không chạy, và AGENT trả lời đúng người cửa hàng muốn giao cho
        # nhân viên (rà soát 28.10.2026).
        for hd in _jsonb(qt["hanh_dong"]) or []:
            loai = hd.get("loai")
            if loai in MOT_LAN and loai in da_mot_lan:
                continue
            try:
                if loai in ("gan_nhan", "gan_nhan_hoi_thoai", "gan_nhan_khach"):
                    lam.append(await _gan_nhan(db, cid, hd, nc))
                elif loai == "gui_mau":
                    if khong_gui:
                        bo_qua.append(f"không gửi mẫu: {khong_gui}")
                        continue
                    if kq.da_gui_khach:
                        bo_qua.append(f"không gửi mẫu /{hd['ma_tat']}: quy tắc «{kq.quy_tac_gui}» "
                                      "đã gửi tin cho tin này của khách")
                        continue
                    lam.append(await _gui_mau(db, msg, cid, hd["ma_tat"],
                                              f"tu_dong:{qt['id']}:{cid}"))
                    # Đánh dấu SAU khi xếp hàng được: mẫu hỏng (bị xoá, dính
                    # cụm cấm) mà đã giữ chỗ thì câu báo chuyển người phía sau
                    # bị bỏ — khách nhận im lặng đúng lúc cần được báo nhất.
                    kq.da_gui_khach, kq.quy_tac_gui = True, ten
                    mot_lan_loai.append("gui_mau")
                    gui_mau_nay = True
                elif loai == "tao_viec":
                    if hd["tieu_de"] in viec_da_tao:
                        bo_qua.append(f"việc «{hd['tieu_de']}» đã được quy tắc trước tạo cho tin này")
                        continue
                    await _tao_viec(db, cid, hd["tieu_de"], ten,
                                    giao_tu_dong=bool(hd.get("giao_tu_dong")))
                    viec_da_tao.add(hd["tieu_de"])
                    lam.append(f"tạo việc: {hd['tieu_de']}")
                    mot_lan_loai.append("tao_viec")
                elif loai == "chuyen_nguoi":
                    # Đã ở chế độ người thì không ghi lại: khách nhắn mười tin
                    # là mười sự kiện "chuyển người" giả trong báo cáo.
                    doi = await db.fetchrow(
                        "UPDATE conversations SET status = 'escalated', mode = 'human', "
                        "outcome = 'escalated', version = version + 1, updated_at = now() "
                        "WHERE id = $1 AND mode <> 'human' RETURNING id", cid)
                    kq.dung_agent = True
                    lam.append("chuyển người")
                    if doi is not None:
                        chuyen_moi = True
                        await db.log_event("conversation.escalated", ref_id=cid,
                                           reason=f"quy tắc: {ten} — {hd.get('ly_do', '')}")
                        # Chuyển người mà không báo ai là im lặng: hội thoại
                        # nằm ở chế độ người, không ai biết phải vào.
                        await thong_bao_noi_bo.bao_ai_chuyen_giao(
                            cid, ly_do=f"Quy tắc «{ten}»: {hd.get('ly_do', '')}")
                        await _bao_nhan_vien_chuyen(msg, cid, ten)
            except Exception as exc:  # noqa: BLE001 — hỏng một hành động không chặn hành động sau
                loi.append(f"{loai}: {type(exc).__name__}: {exc}"[:300])
        # Câu báo chuyển người cố định: CUỐI quy tắc, để mẫu của chính quy
        # tắc này (dù đứng trước hay sau "chuyển người") được làm câu báo.
        if chuyen_moi:
            if kq.da_gui_khach:
                bo_qua.append(f"không gửi câu báo chuyển người: khách đã nhận tin của "
                              f"quy tắc «{kq.quy_tac_gui}»")
            else:
                kq.da_gui_khach, kq.quy_tac_gui = True, ten
                try:
                    await _bao_khach_chuyen(msg, cid)
                except Exception as exc:  # noqa: BLE001
                    loi.append(f"báo khách chuyển người: {type(exc).__name__}: {exc}"[:300])
        if gui_mau_nay and not qt.get("cho_ai_tra_loi"):
            kq.ai_nhuong = True
        chi_tiet: dict[str, Any] = {"lam": lam}
        if mot_lan_loai:
            chi_tiet["mot_lan"] = True
            chi_tiet["mot_lan_loai"] = mot_lan_loai
        if gui_mau_nay:
            chi_tiet["ai_nhuong"] = not qt.get("cho_ai_tra_loi")
        if bo_qua:
            chi_tiet["bo_qua"] = bo_qua
        if loi:
            chi_tiet["loi"] = "; ".join(loi)[:500]
        if qt.get("dung_xet_sau"):
            chi_tiet["dung_xet_sau"] = True
        ket_qua = "da_lam" if lam else ("hong" if loi else "bo_qua")
        try:
            await db.execute(
                "INSERT INTO quy_tac_lan_chay (quy_tac_id, conversation_id, ket_qua, chi_tiet) "
                "VALUES ($1,$2,$3,$4::jsonb)", qt["id"], cid, ket_qua, chi_tiet)
        except Exception:  # noqa: BLE001
            logger.exception("tu_dong: không ghi được lần chạy của %s", ten)
        if loi:
            try:
                await db.log_event("tu_dong.loi", ref_id=cid, quy_tac=ten[:80],
                                   loi=chi_tiet["loi"])
            except Exception:  # noqa: BLE001
                logger.exception("tu_dong: không ghi được sự kiện lỗi của %s", ten)
        kq.da_lam += lam
        if qt.get("dung_xet_sau"):
            break
    return kq


async def _gan_nhan(db, cid: uuid.UUID, hd: dict[str, Any], nc: NguCanh) -> str:
    """
    Gắn nhãn qua CÙNG đường với nhân viên (`agent/core/nhan.py`): nhãn đã
    ngừng không gắn được, sai loại không gắn được, và mỗi lần gắn MỚI để
    lại một dòng `events` (actor `tu_dong`). Hỏng thì NỔ — lần chạy ghi
    "hỏng" kèm lý do, không im lặng như quy tắc "đang bật" mà không làm gì.
    """
    from agent.core import nhan as nhan_loi

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if hd["loai"] == "gan_nhan":
                # Khoá cũ còn sót: tra TÊN trong danh mục nhãn hội thoại.
                n = await nhan_loi.tim_theo_ten(conn, "hoi_thoai", hd["nhan"])
                if n is None:
                    raise QuyTacHong(f"nhãn «{hd['nhan']}» không có trong danh mục nhãn hội thoại")
                nid, loai = n["id"], "hoi_thoai"
            else:
                nid, loai = uuid.UUID(str(hd["nhan_id"])), HANH_DONG_NHAN[hd["loai"]]
            try:
                if loai == "hoi_thoai":
                    n, _ = await nhan_loi.gan_hoi_thoai(conn, conversation_id=cid, nhan_id=nid,
                                                        gan_boi=None, actor="tu_dong")
                    nc.nhan_hoi_thoai.add(str(nid))
                    nc.nhan.add(n["ten"].lower())
                    return f"gắn nhãn hội thoại {n['ten']}"
                contact_id = await conn.fetchval(
                    "SELECT contact_id FROM conversations WHERE id = $1", cid)
                if contact_id is None:
                    raise QuyTacHong("hội thoại chưa gắn hồ sơ khách — không gắn được nhãn khách")
                n, _ = await nhan_loi.gan_khach(conn, contact_id=contact_id, nhan_id=nid,
                                                gan_boi=None, actor="tu_dong")
                nc.nhan_khach.add(str(nid))
                return f"gắn nhãn khách {n['ten']}"
            except (nhan_loi.NhanHong, nhan_loi.NhanKhongThay) as exc:
                raise QuyTacHong(str(exc)) from exc


async def _ghi_hong(db, qt, cid, loi: str) -> None:
    # Ghi lỗi cũng có thể hỏng (CSDL vừa rớt). Hai đường ghi tách riêng, và
    # không đường nào được ném ra ngoài — ném ra là chặn chính tin của khách.
    try:
        await db.execute(
            "INSERT INTO quy_tac_lan_chay (quy_tac_id, conversation_id, ket_qua, chi_tiet) "
            "VALUES ($1,$2,'hong',$3::jsonb)", qt["id"], cid, {"loi": loi})
    except Exception:  # noqa: BLE001
        logger.exception("tu_dong: không ghi được lần chạy hỏng của %s", qt["ten"])
    try:
        await db.log_event("tu_dong.loi", ref_id=cid, quy_tac=str(qt["ten"])[:80], loi=loi)
    except Exception:  # noqa: BLE001
        logger.exception("tu_dong: không ghi được sự kiện lỗi của %s", qt["ten"])
