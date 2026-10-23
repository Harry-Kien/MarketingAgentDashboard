"""
Phụ thuộc dùng chung của API: phiên, quyền, phạm vi kênh, cửa sổ gửi tin.

Tách khỏi routes.py để các module route import được mà không vòng:
routes.py gộp router của chúng, nên chúng không được import ngược routes.
"""
from __future__ import annotations

import uuid

from fastapi import (Depends, HTTPException, Request)

from agent import db
from agent.core import pham_vi, xac_thuc
from agent.core.quyen import QUYEN
from agent.omnichannel.cua_so_gui import xet_tin_nhan_vien



# --- Xác thực: đặt NGAY ĐÂY, trước mọi endpoint ---------------
# Python đánh giá tham số mặc định lúc ĐỊNH NGHĨA hàm, nên
# `Depends(can_quyen(...))` ở endpoint dòng 500 cần hàm này đã tồn tại
# từ trước. Để cuối file thì NameError lúc import — và lỗi đó chỉ nổ
# khi khởi động, không phải khi chạy test.
TEN_COOKIE = "phien_marketing_agent"


async def nguoi_hien_tai(request: Request) -> dict | None:
    """Người đứng sau phiên hiện tại, hoặc None."""
    return await xac_thuc.doc_phien(request.cookies.get(TEN_COOKIE, ""))


async def bat_buoc_dang_nhap(request: Request) -> dict:
    nguoi = await nguoi_hien_tai(request)
    if nguoi is None:
        raise HTTPException(401, "Chưa đăng nhập")
    return nguoi


async def nguoi_da_dang_nhap(request: Request) -> dict:
    """
    Người đang đăng nhập — ưu tiên bản middleware đã đọc.

    Middleware `chan_neu_chua_dang_nhap` đã đọc phiên và gắn vào
    `request.state.nguoi`. Đọc lại là gọi CSDL hai lần mỗi request, và truy
    vấn phiên giờ có thêm ba LEFT JOIN nên nó không còn rẻ như trước.

    VÌ SAO TÁCH RA THÀNH HÀM RIÊNG THAY VÌ VIẾT THẲNG TRONG `can_quyen`
    -------------------------------------------------------------------
    `can_quyen()` trả về một closure MỚI mỗi lần gọi, nên
    `app.dependency_overrides[...]` không nhắm vào nó được — mà đó là cách
    toàn bộ test API giả lập người đăng nhập. Hàm này là một đối tượng duy
    nhất, ổn định, nên test ghi đè đúng một chỗ:

        app.dependency_overrides[routes.nguoi_da_dang_nhap] = lambda: nguoi
    """
    nguoi = getattr(request.state, "nguoi", None)
    if nguoi is None:
        nguoi = await bat_buoc_dang_nhap(request)
    return nguoi


def can_quyen(*quyen: str):
    """
    Dependency đòi ĐỦ các quyền được nêu. Nhiều quyền = PHẢI CÓ TẤT CẢ.

    VÌ SAO KIỂM DANH MỤC Ở ĐÂY, NGOÀI HÀM CON
    ------------------------------------------
    Thân factory chạy lúc IMPORT module. Gõ sai tên quyền thì máy chủ không
    khởi động được, ngay trước mặt người vừa gõ sai — thay vì một 403 bí ẩn
    vào lúc có người thật sự cần dùng endpoint ấy, khi không còn ai nhớ đã
    sửa gì.
    """
    for q in quyen:
        if q not in QUYEN:
            raise KeyError(f"Quyền không có trong danh mục: {q}")

    async def kiem(nguoi: dict = Depends(nguoi_da_dang_nhap)) -> dict:
        thieu = [q for q in quyen if not xac_thuc.duoc_phep(nguoi, q)]
        if thieu:
            raise HTTPException(403, f"Thiếu quyền: {', '.join(thieu)}")
        return nguoi

    # Nhãn để `kiem_moi_route_co_quyen()` nhận ra endpoint đã khai quyền.
    # Không có nhãn thì chốt lúc khởi động coi như chưa khai, và máy chủ
    # không lên — hỏng-đóng, đúng ý.
    kiem.quyen_yeu_cau = quyen  # type: ignore[attr-defined]  # nhãn gắn lên hàm
    return kiem




def _num(v) -> float:
    return float(v or 0)


async def _xet_cua_so_hoac_409(cid: uuid.UUID, loai: str = "chu") -> str | None:
    """
    Tin của người ngoài cửa sổ nhắn tin: 409 có lý do, KHÔNG xếp hàng.
    Trả thẻ (HUMAN_AGENT) nếu được gửi kèm thẻ. Xem cua_so_gui.py.
    """
    qd = await xet_tin_nhan_vien(cid, loai)
    if not qd.duoc:
        raise HTTPException(409, qd.ly_do)
    return qd.the


def _nguoi_id(nguoi: dict) -> uuid.UUID | None:
    """Id người đăng nhập, hoặc None nếu không đọc được (test gọi thẳng hàm)."""
    try:
        return uuid.UUID(str(nguoi["id"]))
    except (KeyError, ValueError):
        return None


def _xem_tat_ca_kenh(nguoi: dict) -> bool:
    return "hoi_thoai.xem_tat_ca" in (nguoi.get("quyen") or ())


async def chan_neu_ngoai_kenh(cid: uuid.UUID, nguoi: dict) -> None:
    """
    Hội thoại phải thuộc tài khoản kênh mà người này là thành viên.

    LỖ ĐO ĐƯỢC 14.10.2026: màn inbox mới lọc theo `account_memberships`,
    nhưng các route cũ trong file này thì không — `GET /conversations/{id}`
    trả toàn bộ tin nhắn của MỌI kênh cho ai có `hoi_thoai.doc`. Bộ lọc ở
    màn mới chỉ còn là lớp sơn.

    404 chứ không 403: 403 xác nhận hội thoại tồn tại, và mã hội thoại nằm
    trong URL, trong log, trong ảnh chụp màn hình người ta gửi nhau.
    """
    if _xem_tat_ca_kenh(nguoi):
        return
    thuoc = await db.fetchrow(
        "SELECT EXISTS (SELECT 1 FROM conversations cv "
        "JOIN account_memberships am ON am.account_id = cv.account_id "
        "WHERE cv.id = $1 AND am.user_id = $2) AS co",
        cid, uuid.UUID(str(nguoi["id"])))
    if not (thuoc and thuoc["co"]):
        raise HTTPException(404, "Không thấy hội thoại")


async def chan_neu_khong_duoc_tra_loi(cid: uuid.UUID, nguoi: dict) -> None:
    """
    Mức tầm nhìn phải chặn Ở MÁY CHỦ, không chỉ khoá nút trên màn hình.

    LỖ HỔNG ĐÃ ĐO (15.09.2026)
    --------------------------
    `pham_vi.duoc_tra_loi()` có từ lâu, nhưng chỉ được gọi ở MỘT chỗ duy
    nhất: `contacts.py` — để vẽ một cái cờ cho giao diện biết nên khoá nút
    Gửi hay không. Không đường gửi tin nào hỏi tới nó.

    Nghĩa là mức `chi_doc` ("đọc được, không trả lời được") và
    `an_noi_dung` chỉ là một lớp sơn: ai gọi thẳng `POST /api/conversations/
    {id}/send` vẫn nhắn được cho khách của người khác. Tài liệu vận hành thì
    hứa "nút gửi bị khoá", nên chủ shop tin rằng khách đã giao được bảo vệ.

    Đó là đúng loại xanh giả tệ nhất: không ai thấy gì hỏng, và điều sai chỉ
    lộ ra khi đã có tranh chấp về việc ai nhắn cho khách của ai.

    Chốt đặt ở đây — nơi CẢ BA đường gửi tin của người đi qua — thay vì nhắc
    từng route nhớ gọi. Quản trị và ai có `khach.xem_tat_ca` không bị chặn;
    khách chưa giao cho ai vẫn là của chung.
    """
    # Phạm vi kênh TRƯỚC mức tầm nhìn: ngoài kênh thì 404, không được để
    # thông điệp 403 bên dưới xác nhận hội thoại tồn tại.
    await chan_neu_ngoai_kenh(cid, nguoi)
    khach = await db.fetchrow(
        "SELECT ct.owner_user_id FROM conversations cv "
        "LEFT JOIN contacts ct ON ct.id = cv.contact_id WHERE cv.id = $1", cid)
    if khach is None:
        return                      # hội thoại không có: để route sau trả 404
    muc = await pham_vi.doc_muc()
    if not pham_vi.duoc_tra_loi(nguoi, dict(khach), muc=muc):
        raise HTTPException(403, (
            "Khách này đã giao cho người khác — bạn đọc được nhưng không trả "
            "lời được. Đổi ở Cấu hình → Nhân viên thấy khách của nhau tới đâu."))
