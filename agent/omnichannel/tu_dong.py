"""
Quy tắc tự động hoá: SỰ KIỆN → ĐIỀU KIỆN → HÀNH ĐỘNG (bảng `quy_tac_tu_dong`).

    khi khách nhắn tin  →  nếu [kênh, từ khoá, ngoài giờ, tin đầu, nhãn]
                        →  gắn nhãn · gửi mẫu trả lời nhanh · tạo việc · chuyển người

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
DIEU_KIEN = ("kenh", "chua_tu", "ngoai_gio", "lan_dau", "nhan_co", "nhan_khong")
HANH_DONG = ("gan_nhan", "gui_mau", "tao_viec", "chuyen_nguoi")
# Làm tối đa một lần mỗi hội thoại (chốt 2). Gắn nhãn/chuyển người lặp lại vô hại.
MOT_LAN = frozenset({"gui_mau", "tao_viec"})
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


def kiem_dieu_kien(dk: Any) -> dict[str, Any]:
    if not isinstance(dk, dict):
        raise QuyTacHong("điều kiện phải là object")
    la = set(dk) - set(DIEU_KIEN)
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
    for k in ("nhan_co", "nhan_khong"):
        if k in dk:
            if not isinstance(dk[k], str) or not 1 <= len(dk[k].strip()) <= 40:
                raise QuyTacHong(f"{k} phải là một nhãn 1–40 ký tự")
            ra[k] = dk[k].strip().lower()
    return ra


def kiem_hanh_dong(ds: Any) -> list[dict[str, Any]]:
    if not isinstance(ds, list) or not 1 <= len(ds) <= TOI_DA_HANH_DONG:
        raise QuyTacHong(f"cần 1–{TOI_DA_HANH_DONG} hành động")
    ra = []
    for hd in ds:
        if not isinstance(hd, dict) or hd.get("loai") not in HANH_DONG:
            raise QuyTacHong(f"hành động phải là một trong: {', '.join(HANH_DONG)}")
        loai = hd["loai"]
        la = set(hd) - {"loai", "nhan", "ma_tat", "tieu_de", "ly_do"}
        if la:
            raise QuyTacHong(f"hành động {loai} có khoá lạ: {', '.join(sorted(la))}")
        if loai == "gan_nhan":
            n = str(hd.get("nhan") or "").strip().lower()
            if not 1 <= len(n) <= 40:
                raise QuyTacHong("gan_nhan cần nhan 1–40 ký tự")
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
            ra.append({"loai": loai, "tieu_de": td})
        else:
            ra.append({"loai": loai, "ly_do": str(hd.get("ly_do") or "quy tắc tự động").strip()[:200]})
    return ra


# ---------------------------------------------------------------- khớp (thuần)

@dataclass
class NguCanh:
    kenh: str
    van_ban: str
    ngoai_gio: bool
    lan_dau: bool
    nhan: set[str] = field(default_factory=set)


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
    return True


# ---------------------------------------------------------------- chạy (IO)

@dataclass
class KetQua:
    dung_agent: bool = False          # có quy tắc chuyển người -> agent không trả lời
    da_lam: list[str] = field(default_factory=list)


def _jsonb(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else (v or {})


async def _da_lam_mot_lan(db, quy_tac_id, cid) -> bool:
    r = await db.fetchrow(
        "SELECT 1 FROM quy_tac_lan_chay WHERE quy_tac_id = $1 AND conversation_id = $2 "
        "AND ket_qua = 'da_lam' AND chi_tiet ? 'mot_lan' LIMIT 1", quy_tac_id, cid)
    return r is not None


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


async def _tao_viec(db, cid: uuid.UUID, tieu_de: str, ten_quy_tac: str) -> str:
    """
    Việc mang ĐÚNG tiêu đề người vận hành đặt trong quy tắc, nguồn `tu_dong`.

    Không dùng `cong_viec.tao_tu_chuyen_nguoi`: hàm ấy đặt tiêu đề cố định
    "Khách cần người trả lời", đụng chốt "mỗi hội thoại một việc agent đang
    mở" (trả None khi đã có — vậy mà quy tắc vẫn ghi "đã tạo việc"), và nuốt
    lỗi CSDL. Ở đây không có việc thì NỔ, để lần chạy ghi "hỏng".
    """
    r = await db.fetchrow(
        "INSERT INTO cong_viec (tieu_de, mo_ta, nguon, conversation_id, contact_id) "
        "SELECT $1, $2, 'tu_dong', $3::uuid, c.contact_id "
        "FROM (SELECT 1) _ LEFT JOIN conversations c ON c.id = $3::uuid RETURNING id",
        tieu_de, f"Tạo bởi quy tắc tự động «{ten_quy_tac}»", str(cid))
    if r is None:
        raise RuntimeError("không tạo được công việc")
    return str(r["id"])


async def _bao_chuyen_nguoi(msg, cid: uuid.UUID, ten_quy_tac: str) -> None:
    """
    Báo CẢ HAI PHÍA như mọi nhánh chuyển người khác: khách nhận câu cố định,
    nhân viên thấy ghi chú trong hộp thư kênh. Thiếu bước này thì khách nhận
    im lặng — đúng thứ chuyển người sinh ra để tránh (rà soát 28.10.2026).
    """
    from agent.channels import registry as channels
    from agent.omnichannel import xu_ly_tin_vao

    ad = await channels.get_for_account(msg.account_id)
    try:
        await xu_ly_tin_vao.bao_nhan_vien_tiep_quan(
            ad, msg.conversation_ref, cid, f"quy tắc tự động «{ten_quy_tac}»")
    finally:
        await xu_ly_tin_vao.bao_khach_dang_chuyen_nguoi(ad, msg.conversation_ref, cid)


async def chay_tin_khach(msg, cid: uuid.UUID, *, lan_dau: bool | None = None,
                         nguoi_dang_tiep: bool = False) -> KetQua:
    """
    Chạy mọi quy tắc đang bật cho một tin khách. Không bao giờ ném.

    `nguoi_dang_tiep`: hội thoại đã ở chế độ người TRƯỚC tin này. Khi ấy, và
    khi công tắc agent toàn cục đang tắt, KHÔNG gửi mẫu: nhân viên đang nói
    chuyện với khách, một câu tự động chen ngang là nói đè lên họ.
    """
    from agent import db, runtime
    from agent.core import cong_viec, gio_lam_viec

    kq = KetQua()
    try:
        ds = await db.fetch("SELECT * FROM quy_tac_tu_dong WHERE bat AND su_kien = 'tin_khach' "
                            "ORDER BY thu_tu, tao_luc")
    except Exception as exc:  # noqa: BLE001 — bảng chưa có / CSDL lỗi: báo, không chặn tin
        logger.exception("tu_dong: không đọc được quy tắc")
        try:
            await db.log_event("tu_dong.loi", ref_id=cid, loi=f"{type(exc).__name__}: {exc}"[:200])
        except Exception:  # noqa: BLE001
            pass
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
        nhan = {r["nhan"] for r in await db.fetch(
            "SELECT nhan FROM hoi_thoai_nhan WHERE conversation_id = $1", cid)}
    except Exception as exc:  # noqa: BLE001
        logger.exception("tu_dong: không đọc được ngữ cảnh hội thoại %s", cid)
        try:
            await db.log_event("tu_dong.loi", ref_id=cid, loi=f"{type(exc).__name__}: {exc}"[:200])
        except Exception:  # noqa: BLE001
            pass
        return kq
    nc = NguCanh(kenh=str(msg.channel),
                 van_ban=msg.text or "", ngoai_gio=not gio_lam_viec.dang_trong_gio(),
                 lan_dau=lan_dau, nhan=nhan)
    duoc_gui = runtime.enabled() and not nguoi_dang_tiep
    for qt in ds:
        try:
            if not khop(_jsonb(qt["dieu_kien"]), nc):
                continue
            da_mot_lan = await _da_lam_mot_lan(db, qt["id"], cid)
        except Exception as exc:  # noqa: BLE001
            await _ghi_hong(db, qt, cid, f"{type(exc).__name__}: {exc}"[:300])
            continue
        lam: list[str] = []
        loi: list[str] = []
        bo_qua: list[str] = []
        mot_lan = False
        # MỖI HÀNH ĐỘNG HỎNG RIÊNG. Bản trước để một mẫu hỏng (bị xoá, dính
        # cụm cấm, ngoài cửa sổ gửi) huỷ cả quy tắc — "chuyển người" đứng sau
        # không chạy, và AGENT trả lời đúng người cửa hàng muốn giao cho
        # nhân viên (rà soát 28.10.2026).
        for hd in _jsonb(qt["hanh_dong"]) or []:
            loai = hd.get("loai")
            if loai in MOT_LAN and da_mot_lan:
                continue
            try:
                if loai == "gan_nhan":
                    await db.execute("INSERT INTO hoi_thoai_nhan (conversation_id, nhan) VALUES ($1,$2) "
                                     "ON CONFLICT DO NOTHING", cid, hd["nhan"])
                    nc.nhan.add(hd["nhan"])
                    lam.append(f"gắn nhãn {hd['nhan']}")
                elif loai == "gui_mau":
                    if not duoc_gui:
                        bo_qua.append("không gửi mẫu: nhân viên đang tiếp hoặc agent đang tắt toàn hệ thống")
                        continue
                    lam.append(await _gui_mau(db, msg, cid, hd["ma_tat"],
                                              f"tu_dong:{qt['id']}:{cid}"))
                    mot_lan = True
                elif loai == "tao_viec":
                    await _tao_viec(db, cid, hd["tieu_de"], str(qt["ten"]))
                    lam.append(f"tạo việc: {hd['tieu_de']}")
                    mot_lan = True
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
                        await db.log_event("conversation.escalated", ref_id=cid,
                                           reason=f"quy tắc: {qt['ten']} — {hd.get('ly_do', '')}")
                        # Chuyển người mà không sinh việc là im lặng: hội thoại
                        # nằm ở chế độ người, không ai biết phải vào.
                        await cong_viec.tao_tu_chuyen_nguoi(
                            cid, ly_do=f"Quy tắc «{qt['ten']}»: {hd.get('ly_do', '')}")
                        await _bao_chuyen_nguoi(msg, cid, str(qt["ten"]))
            except Exception as exc:  # noqa: BLE001 — hỏng một hành động không chặn hành động sau
                loi.append(f"{loai}: {type(exc).__name__}: {exc}"[:300])
        chi_tiet: dict[str, Any] = {"lam": lam}
        if mot_lan:
            chi_tiet["mot_lan"] = True
        if bo_qua:
            chi_tiet["bo_qua"] = bo_qua
        if loi:
            chi_tiet["loi"] = "; ".join(loi)[:500]
        ket_qua = "da_lam" if lam else ("hong" if loi else "bo_qua")
        try:
            await db.execute(
                "INSERT INTO quy_tac_lan_chay (quy_tac_id, conversation_id, ket_qua, chi_tiet) "
                "VALUES ($1,$2,$3,$4::jsonb)", qt["id"], cid, ket_qua, chi_tiet)
        except Exception:  # noqa: BLE001
            logger.exception("tu_dong: không ghi được lần chạy của %s", qt["ten"])
        if loi:
            try:
                await db.log_event("tu_dong.loi", ref_id=cid, quy_tac=str(qt["ten"])[:80],
                                   loi=chi_tiet["loi"])
            except Exception:  # noqa: BLE001
                logger.exception("tu_dong: không ghi được sự kiện lỗi của %s", qt["ten"])
        kq.da_lam += lam
    return kq


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
