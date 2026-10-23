"""
API tài khoản: đăng nhập, đăng xuất, đổi mật khẩu, 2FA, quản lý nhân viên.
"""
from __future__ import annotations

import uuid

from fastapi import (APIRouter, Depends, HTTPException, Request, Response)
from pydantic import BaseModel, Field

from agent import db
from agent.config import settings
from agent.core import xac_thuc

from .phu_thuoc import (
    TEN_COOKIE,
    bat_buoc_dang_nhap,
    can_quyen,
    nguoi_hien_tai,
)

router = APIRouter(prefix="/api")


class DangNhapIn(BaseModel):
    ten_dang_nhap: str = Field(min_length=1, max_length=64)
    mat_khau: str = Field(min_length=1, max_length=200)
    # Mã 6 số từ app xác thực, hoặc mã dự phòng. Chỉ cần khi tài khoản bật 2FA.
    ma_2fa: str = Field("", max_length=20)


class DoiMatKhauIn(BaseModel):
    mat_khau_moi: str = Field(min_length=8, max_length=200)


class TaoNguoiDungIn(BaseModel):
    ten_dang_nhap: str = Field(min_length=3, max_length=64)
    mat_khau: str = Field(min_length=8, max_length=200)
    ho_ten: str = Field("", max_length=120)
    vai_tro: str = Field("nhan_vien")


# ---------------------------------------------------------------
#  Đăng nhập
#
#  Dashboard đọc PII khách hàng, gửi tin nhân danh doanh nghiệp, và xoá
#  vĩnh viễn dữ liệu. Trước lớp này, ai chạm được cổng 8000 đều làm được
#  tất cả — chỉ an toàn nhờ nghe ở 127.0.0.1, tức an toàn cho tới đúng ngày
#  ai đó đưa lên server.
# ---------------------------------------------------------------

@router.post("/dang-nhap")
async def dang_nhap(body: DangNhapIn, response: Response, request: Request) -> dict:
    # IP thật đã được uvicorn --proxy-headers lấy từ X-Forwarded-For (Caddy).
    ip = request.client.host if request.client else ""
    try:
        token = await xac_thuc.dang_nhap(body.ten_dang_nhap, body.mat_khau,
                                         body.ma_2fa, ip=ip)
    except xac_thuc.CanMaHaiBuoc:
        raise HTTPException(401, {"can_ma_2fa": True,
                                  "detail": "Nhập mã 6 số trong ứng dụng xác thực."}) from None
    except xac_thuc.MaHaiBuocSai:
        raise HTTPException(401, {"can_ma_2fa": True,
                                  "detail": "Mã xác thực không đúng hoặc đã dùng."}) from None
    if token is None:
        # Đang bị khoá tạm thì PHẢI nói ra, kèm thời gian chờ. Giấu đi
        # không làm người dò khó hơn chút nào — họ tự thấy mình bị chặn
        # qua việc thử mãi không được — nhưng lại làm nhân viên thật ngồi
        # gõ lại mật khẩu đúng và không hiểu vì sao hệ thống nói mình sai.
        #
        # Câu này không lộ tên nào có thật, vì tên KHÔNG tồn tại cũng bị
        # đếm và cũng bị khoá y hệt.
        con = max(xac_thuc.bi_khoa_tam(body.ten_dang_nhap),
                  xac_thuc.bi_khoa_tam(f"ip:{ip}", toi_da=xac_thuc.DANG_NHAP_TOI_DA_IP)
                  if ip else 0)
        if con > 0:
            raise HTTPException(
                429,
                f"Sai quá nhiều lần. Thử lại sau {max(1, con // 60)} phút.",
            )
        # KHÔNG nói sai tên hay sai mật khẩu. Nói rõ là chỉ ra tên nào có
        # tồn tại, và đó là nửa đầu của việc dò tài khoản.
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")

    response.set_cookie(
        TEN_COOKIE, token,
        httponly=True,       # JavaScript không đọc được -> XSS không lấy được phiên
        samesite="lax",      # chặn gửi cookie kèm request từ trang khác
        max_age=xac_thuc.PHIEN_NGAY * 86400,
        # secure=True khi chạy sau HTTPS. Bật cứng ở đây thì đăng nhập trên
        # http://localhost hỏng, nên suy từ địa chỉ công khai — xem
        # `Settings.cookie_can_secure`.
        secure=settings.cookie_can_secure,
    )
    nguoi = await xac_thuc.doc_phien(token)
    return {"ok": True, "nguoi": nguoi}


@router.post("/dang-xuat")
async def dang_xuat(request: Request, response: Response) -> dict:
    await xac_thuc.dang_xuat(request.cookies.get(TEN_COOKIE, ""))
    # Cùng thuộc tính với lúc đặt: trình duyệt chỉ xoá cookie khớp đủ bộ
    # path/secure/samesite, lệch một cờ là "đăng xuất" mà cookie vẫn còn.
    response.delete_cookie(TEN_COOKIE, httponly=True, samesite="lax",
                           secure=settings.cookie_can_secure)
    return {"ok": True}


@router.get("/toi")
async def toi(request: Request) -> dict:
    """Ai đang đăng nhập. Dashboard gọi lúc tải để biết có cần vào trang đăng nhập không."""
    nguoi = await nguoi_hien_tai(request)
    if nguoi is None:
        raise HTTPException(401, "Chưa đăng nhập")
    return nguoi


@router.post("/toi/doi-mat-khau")
async def doi_mat_khau(body: DoiMatKhauIn,
                       nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Đổi mật khẩu của chính mình. Mọi phiên đang mở bị đá ra."""
    await xac_thuc.doi_mat_khau(nguoi["ten_dang_nhap"], body.mat_khau_moi)
    await db.log_event("auth.doi_mat_khau", actor=nguoi["ten_dang_nhap"])
    return {"ok": True, "ghi_chu": "Đã đổi. Mọi thiết bị phải đăng nhập lại."}


class MaHaiBuocIn(BaseModel):
    ma: str = Field(min_length=6, max_length=20)


class TatHaiBuocIn(BaseModel):
    mat_khau: str = Field(min_length=1, max_length=200)


@router.get("/toi/hai-buoc")
async def hai_buoc_trang_thai(nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    r = await db.fetchrow(
        "SELECT hai_buoc_bat, cardinality(ma_du_phong) AS con FROM nguoi_dung WHERE id = $1",
        uuid.UUID(str(nguoi["id"])))
    return {"bat": bool(r and r["hai_buoc_bat"]), "ma_du_phong_con": r["con"] if r else 0}


@router.post("/toi/hai-buoc/bat-dau")
async def hai_buoc_bat_dau(nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Sinh bí mật mới (CHƯA bật) và trả QR để quét bằng app xác thực."""
    import segno

    from agent.core import hai_buoc
    uri = await hai_buoc.bat_dau(uuid.UUID(str(nguoi["id"])), nguoi["ten_dang_nhap"])
    import io
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=5, border=2)
    # Trả cả URI: điện thoại không quét được thì nhập tay khoá trong URI.
    return {"uri": uri, "svg": buf.getvalue().decode("utf-8")}


@router.post("/toi/hai-buoc/xac-nhan")
async def hai_buoc_xac_nhan(body: MaHaiBuocIn,
                            nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Mã đầu tiên đúng thì BẬT. Mã dự phòng chỉ hiện MỘT lần, ở đây."""
    from agent.core import hai_buoc
    ma_du_phong = await hai_buoc.xac_nhan(uuid.UUID(str(nguoi["id"])), body.ma)
    if ma_du_phong is None:
        raise HTTPException(422, "Mã không đúng. Kiểm giờ trên điện thoại rồi thử mã mới.")
    return {"ok": True, "ma_du_phong": ma_du_phong}


@router.post("/toi/hai-buoc/tat")
async def hai_buoc_tat(body: TatHaiBuocIn,
                       nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Tắt 2FA đòi gõ lại mật khẩu: phiên bị chiếm không được tự gỡ lớp bảo vệ."""
    from agent.core import hai_buoc
    r = await db.fetchrow("SELECT mat_khau_bam FROM nguoi_dung WHERE id = $1",
                          uuid.UUID(str(nguoi["id"])))
    if r is None or not xac_thuc.kiem_mat_khau(body.mat_khau, r["mat_khau_bam"]):
        raise HTTPException(403, "Mật khẩu không đúng.")
    await hai_buoc.tat(uuid.UUID(str(nguoi["id"])))
    return {"ok": True}


@router.get("/nguoi-dung")
async def danh_sach_nguoi_dung(_: dict = Depends(can_quyen("nguoi_dung.doc"))) -> dict:
    # Kèm TÊN VAI TRÒ, không chỉ cột `vai_tro` cũ.
    #
    # Cột ấy giờ là nhãn hiển thị, không còn quyết định quyền — xem
    # `agent/core/xac_thuc.py`. Màn Nhân sự hiện nó thay cho vai trò thật là
    # nói dối người vận hành ở đúng chỗ họ cần sự thật nhất.
    rows = await db.fetch(
        "SELECT nd.id, nd.ten_dang_nhap, nd.ho_ten, nd.vai_tro, nd.khoa, "
        "       nd.tao_luc, nd.dang_nhap_cuoi, "
        "       COALESCE(array_agg(vt.ten ORDER BY vt.ten) "
        "                FILTER (WHERE vt.ten IS NOT NULL), "
        "                ARRAY[]::text[]) AS vai_tro_ten, "
        # Số kênh người này là thành viên. 0 kênh + không phải Quản trị =
        # đăng nhập được mà không thấy hội thoại nào, khách nào — kể cả khách
        # đã giao cho chính họ. Phải hiện ngay trên dòng, không đợi ai hỏi.
        "       (SELECT count(*) FROM account_memberships am "
        "         WHERE am.user_id = nd.id)::int AS so_kenh, "
        # Số kênh người này đọc được SỐ ĐIỆN THOẠI và EMAIL của khách.
        # Đây là con số quan trọng nhất của màn Nhân sự về mặt bảo mật, và
        # trước đây không ở đâu nhìn thấy được: quản trị muốn biết "ai đang
        # đọc được PII" thì phải tự đọc bảng account_memberships.
        "       (SELECT count(*) FROM account_memberships am "
        "         WHERE am.user_id = nd.id "
        "           AND am.role IN ('owner', 'manager'))::int AS so_kenh_pii "
        "FROM nguoi_dung nd "
        "LEFT JOIN nguoi_dung_vai_tro ndvt ON ndvt.nguoi_dung_id = nd.id "
        "LEFT JOIN vai_tro vt ON vt.id = ndvt.vai_tro_id "
        "GROUP BY nd.id ORDER BY nd.tao_luc"
    )
    for r in rows:
        r["id"] = str(r["id"])
        for k in ("tao_luc", "dang_nhap_cuoi"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {"nguoi_dung": rows}


@router.post("/nguoi-dung")
async def them_nguoi_dung(body: TaoNguoiDungIn,
                          nguoi: dict = Depends(can_quyen("nguoi_dung.sua"))) -> dict:
    try:
        r = await xac_thuc.tao_nguoi_dung(
            body.ten_dang_nhap, body.mat_khau, body.ho_ten, body.vai_tro
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.log_event("auth.tao_nguoi_dung", actor=nguoi["ten_dang_nhap"],
                       ten_moi=body.ten_dang_nhap, vai_tro=body.vai_tro)
    return r


@router.post("/nguoi-dung/{ten}/khoa")
async def khoa_nguoi_dung(ten: str, khoa: bool = True,
                          nguoi: dict = Depends(can_quyen("nguoi_dung.sua"))) -> dict:
    """
    Khoá tài khoản và ĐÁ MỌI PHIÊN ĐANG MỞ.

    Khoá mà không xoá phiên thì người vừa bị khoá vẫn ngồi trong hệ thống
    tới lúc phiên hết hạn — với hệ thống nắm dữ liệu khách hàng, đó là bảy
    ngày quá nhiều.
    """
    if ten.strip().lower() == nguoi["ten_dang_nhap"]:
        raise HTTPException(422, "Không tự khoá tài khoản của mình được")
    r = await db.fetchrow(
        "UPDATE nguoi_dung SET khoa = $2 WHERE ten_dang_nhap = $1 RETURNING id",
        ten.strip().lower(), khoa,
    )
    if r is None:
        raise HTTPException(404, "Không có tài khoản này")
    if khoa:
        await db.execute("DELETE FROM phien WHERE nguoi_dung_id = $1", r["id"])
    await db.log_event("auth.khoa_nguoi_dung", actor=nguoi["ten_dang_nhap"],
                       ten=ten, khoa=khoa)
    return {"ok": True, "ten_dang_nhap": ten, "khoa": khoa}
