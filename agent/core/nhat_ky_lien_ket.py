"""
Đối tượng bị tác động của một dòng nhật ký, và người XEM có mở được nó không.

UX-18-03: mỗi dòng nhật ký phải đọc thành "ai làm gì, với đối tượng nào,
kết quả gì" — và đối tượng bấm được để đi tới nó. Đối tượng được PHÂN GIẢI
ở mô hình đọc (`_SQL_GOC` nối sang `orders`, `cong_viec`, `nguoi_dung`,
`conversations`) chứ không đòi nơi ghi khai thêm: hơn trăm chỗ ghi `events`
mỗi chỗ đặt mã đơn/việc/người ở một khoá khác nhau, còn khoá chính UUID thì
chỉ khớp đúng một bảng.

VÌ SAO QUYẾT "MỞ ĐƯỢC" Ở MÁY CHỦ
-------------------------------
Người có `nhat_ky.doc` chưa chắc có quyền mở hội thoại của mọi kênh, hay
xem công việc của người khác. Liên kết mà bấm vào ra 404 là liên kết nói
dối; còn để trình duyệt tự đoán quyền thì phải gửi xuống danh sách kênh
của người xem — đúng thứ không cần lộ. Máy chủ biết cả hai phía nên quyết
ở đây, theo CÙNG luật với màn đích:
  · hội thoại  — `hoi_thoai.doc` + (`hoi_thoai.xem_tat_ca` hoặc là thành
                 viên kênh của hội thoại) — y hệt `chan_neu_ngoai_kenh`;
  · công việc  — `cong_viec.doc` + (`cong_viec.xem_tat_ca`, hoặc việc mình
                 nhận / mình giao / chưa giao ai) — y hệt `agent/api/cong_viec.py`;
  · đơn hàng   — `don.doc`;  · nhân viên — `nguoi_dung.doc`;
  · tài khoản kênh — `kenh.doc`, và tài khoản còn tồn tại.
Không biết người xem (gọi nội bộ, test) thì KHÔNG mở được gì — hỏng-đóng.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from agent import db


@dataclass(frozen=True)
class NguoiXem:
    id: str | None
    quyen: frozenset[str]
    kenh: frozenset[str]

    def co(self, q: str) -> bool:
        return q in self.quyen


async def nguoi_xem(nguoi: dict | None) -> NguoiXem | None:
    """Ngữ cảnh quyền của người đang xem — MỘT truy vấn cho cả trang."""
    if not nguoi:
        return None
    quyen = frozenset(nguoi.get("quyen") or ())
    uid: UUID | None
    try:
        uid = UUID(str(nguoi.get("id")))
    except (TypeError, ValueError):
        uid = None
    kenh: frozenset[str] = frozenset()
    if uid is not None and "hoi_thoai.xem_tat_ca" not in quyen:
        rows = await db.fetch(
            "SELECT account_id FROM account_memberships WHERE user_id = $1", uid)
        kenh = frozenset(str(r["account_id"]) for r in rows)
    return NguoiXem(id=str(uid) if uid else None, quyen=quyen, kenh=kenh)


def _s(x: Any) -> str | None:
    return str(x) if x not in (None, "") else None


def lien_ket(r: dict[str, Any], tai_khoan: dict[str, Any] | None,
             xem: NguoiXem | None) -> list[dict[str, Any]]:
    """
    Danh sách đối tượng của một dòng, đối tượng CHÍNH trước (đơn, việc,
    nhân viên), rồi hội thoại, rồi tài khoản kênh — một lần lên đơn thì
    đối tượng là đơn, hội thoại chỉ là nơi nó xảy ra.
    """
    ra: list[dict[str, Any]] = []

    def them(loai: str, id_: str, nhan: str, mo: bool) -> None:
        ra.append({"loai": loai, "id": id_, "nhan": nhan, "mo_duoc": bool(xem) and mo})

    if _s(r.get("dt_don_id")):
        them("don_hang", str(r["dt_don_id"]), f"Đơn {r.get('dt_don_ma') or ''}".strip(),
             bool(xem and xem.co("don.doc")))
    if _s(r.get("dt_cv_id")):
        tieu = str(r.get("dt_cv_tieu_de") or "")[:60]
        nhan_cv, giao_cv = _s(r.get("dt_cv_nguoi_nhan")), _s(r.get("dt_cv_nguoi_giao"))
        mo = bool(xem and xem.co("cong_viec.doc") and (
            xem.co("cong_viec.xem_tat_ca") or nhan_cv is None
            or xem.id in (nhan_cv, giao_cv)))
        them("cong_viec", str(r["dt_cv_id"]), f"Công việc “{tieu}”" if tieu else "Công việc", mo)
    # Người bị tác động — bỏ khi trùng chính người làm (đổi mật khẩu của
    # mình): "Chị Lan đổi mật khẩu · Chị Lan" là chữ thừa.
    if _s(r.get("dt_nv_id")) and str(r["dt_nv_id"]) != _s(r.get("nguoi_id")):
        them("nhan_vien", str(r["dt_nv_id"]), f"Nhân viên {r.get('dt_nv_ten') or ''}".strip(),
             bool(xem and xem.co("nguoi_dung.doc")))
    hid = _s(r.get("hoi_thoai_id"))
    if hid:
        con = _s(r.get("ht_account_id"))
        if con is None:
            # Hội thoại đã bị xoá theo hạn lưu dữ liệu — vẫn nói tên, không mở.
            them("hoi_thoai", hid, f"Hội thoại {hid[:8]} (đã xoá)", False)
        else:
            mo = bool(xem and xem.co("hoi_thoai.doc") and (
                xem.co("hoi_thoai.xem_tat_ca") or con in xem.kenh))
            them("hoi_thoai", hid, f"Hội thoại {hid[:8]}", mo)
    # Tài khoản kênh sau cùng: với việc trong một hội thoại nó chỉ là bối
    # cảnh ("ở kênh nào"); với việc của chính tài khoản thì nó đứng một mình.
    if tai_khoan and tai_khoan.get("id"):
        them("tai_khoan_kenh", str(tai_khoan["id"]), str(tai_khoan.get("ten") or "Tài khoản kênh"),
             bool(xem and xem.co("kenh.doc") and tai_khoan.get("ton_tai")))
    return ra
