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
    # Mật khẩu HIỆN TẠI: phiên bị chiếm (cookie lộ, máy quên khoá) không được
    # tự đổi mật khẩu rồi đá chủ thật ra khỏi mọi thiết bị.
    mat_khau_cu: str = Field(min_length=1, max_length=200)
    mat_khau_moi: str = Field(min_length=8, max_length=200)


class TaoNguoiDungIn(BaseModel):
    ten_dang_nhap: str = Field(min_length=3, max_length=64)
    mat_khau: str = Field(min_length=8, max_length=200)
    ho_ten: str = Field("", max_length=120)
    # Nhãn hiển thị cũ (`quan_tri`/`nhan_vien`), KHÔNG cấp quyền gì — quyền
    # đến từ `vai_tro_ids`.
    vai_tro: str = Field("nhan_vien")
    email: str | None = Field(None, max_length=200)
    vai_tro_ids: list[uuid.UUID] = Field(default_factory=list)


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


async def _kiem_lai_mat_khau(nguoi: dict, mat_khau: str) -> None:
    """
    Gõ lại mật khẩu cho việc nhạy cảm của CHÍNH MÌNH (đổi mật khẩu, bật/đổi/
    tắt 2FA). Phiên chứng minh "ai đó đang cầm cookie", không chứng minh
    "đó là chủ tài khoản".

    Dùng CHUNG bộ đếm sai với đăng nhập (theo tên): không thì phiên bị chiếm
    biến các route này thành máy dò mật khẩu không giới hạn — scrypt chỉ
    làm chậm, không chặn.
    """
    ten = nguoi["ten_dang_nhap"]
    if (con := xac_thuc.bi_khoa_tam(ten)) > 0:
        raise HTTPException(429, f"Sai mật khẩu quá nhiều lần — thử lại sau {con} giây.")
    r = await db.fetchrow("SELECT mat_khau_bam FROM nguoi_dung WHERE id = $1",
                          uuid.UUID(str(nguoi["id"])))
    if r is None or not xac_thuc.kiem_mat_khau(mat_khau or "", r["mat_khau_bam"]):
        xac_thuc.ghi_that_bai(ten)
        await db.log_event("auth.go_lai_mat_khau_sai", actor=ten)
        raise HTTPException(403, "Mật khẩu hiện tại không đúng.")


@router.post("/toi/doi-mat-khau")
async def doi_mat_khau(body: DoiMatKhauIn,
                       nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """Đổi mật khẩu của chính mình. Mọi phiên đang mở bị đá ra."""
    await _kiem_lai_mat_khau(nguoi, body.mat_khau_cu)
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


class BatDauHaiBuocIn(BaseModel):
    mat_khau: str = Field("", max_length=200)
    # Chỉ cần khi 2FA ĐANG bật (đổi điện thoại / đăng ký lại).
    ma: str = Field("", max_length=20)


@router.post("/toi/hai-buoc/bat-dau")
async def hai_buoc_bat_dau(body: BatDauHaiBuocIn | None = None,
                           nguoi: dict = Depends(bat_buoc_dang_nhap)) -> dict:
    """
    Sinh bí mật mới (CHỜ, chưa thay bí mật đang dùng) và trả QR để quét.

    Đòi gõ lại mật khẩu — và nếu 2FA đang bật thì đòi cả mã hiện tại. Trước
    16.11.2026 route này không hỏi gì và tắt 2FA ngay khi gọi: phiên bị
    chiếm gỡ được lớp bảo vệ mà chính lớp ấy sinh ra để chặn.
    """
    import segno

    from agent.core import hai_buoc
    body = body or BatDauHaiBuocIn(mat_khau="", ma="")
    uid = uuid.UUID(str(nguoi["id"]))
    await _kiem_lai_mat_khau(nguoi, body.mat_khau)
    tt = await db.fetchrow("SELECT hai_buoc_bat FROM nguoi_dung WHERE id = $1", uid)
    if tt and tt["hai_buoc_bat"]:
        if not body.ma or not await hai_buoc.kiem(uid, body.ma):
            xac_thuc.ghi_that_bai(nguoi["ten_dang_nhap"])
            raise HTTPException(403, "2FA đang bật — nhập mã 6 số hiện tại (hoặc mã dự phòng) "
                                     "để đăng ký điện thoại mới.")
    uri = await hai_buoc.bat_dau(uid, nguoi["ten_dang_nhap"])
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
    await _kiem_lai_mat_khau(nguoi, body.mat_khau)
    await hai_buoc.tat(uuid.UUID(str(nguoi["id"])))
    return {"ok": True}


@router.get("/nguoi-dung")
async def danh_sach_nguoi_dung(_: dict = Depends(can_quyen("nguoi_dung.doc"))) -> dict:
    # Kèm TÊN VAI TRÒ, không chỉ cột `vai_tro` cũ.
    #
    # Cột ấy giờ là nhãn hiển thị, không còn quyết định quyền — xem
    # `agent/core/xac_thuc.py`. Màn Nhân sự hiện nó thay cho vai trò thật là
    # nói dối người vận hành ở đúng chỗ họ cần sự thật nhất.
    #
    # `vai_tro_ten` chỉ gồm vai trò ĐANG DÙNG — thứ thật sự cấp quyền. Vai
    # trò đã ngừng dùng mà người này còn mang nằm riêng ở `vai_tro_ngung`.
    rows = await db.fetch(
        "SELECT nd.id, nd.ten_dang_nhap, nd.ho_ten, nd.email, nd.vai_tro, nd.khoa, "
        "       nd.tao_luc, nd.dang_nhap_cuoi, "
        "       COALESCE(array_agg(vt.ten ORDER BY vt.ten) "
        "                FILTER (WHERE vt.ten IS NOT NULL AND vt.dang_dung), "
        "                ARRAY[]::text[]) AS vai_tro_ten, "
        "       COALESCE(array_agg(vt.ten ORDER BY vt.ten) "
        "                FILTER (WHERE vt.ten IS NOT NULL AND NOT vt.dang_dung), "
        "                ARRAY[]::text[]) AS vai_tro_ngung, "
        "       COALESCE(array_agg(vt.id::text ORDER BY vt.ten) "
        "                FILTER (WHERE vt.id IS NOT NULL), "
        "                ARRAY[]::text[]) AS vai_tro_id, "
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
        "           AND am.role IN ('owner', 'manager'))::int AS so_kenh_pii, "
        # Việc đang giữ — để nút Khoá cảnh báo TRƯỚC khi bấm, và để quản lý
        # thấy ai đang ôm nhiều việc (mục 13.8).
        "       (SELECT count(*) FROM conversations c "
        "         WHERE c.assigned_to = nd.id AND c.mode = 'human' "
        "           AND c.state NOT IN ('resolved', 'closed'))::int AS so_hoi_thoai_giu, "
        "       (SELECT count(*) FROM cong_viec cv "
        "         WHERE cv.nguoi_nhan = nd.id "
        "           AND cv.trang_thai IN ('moi', 'dang_lam'))::int AS so_viec_chua_xong "
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
    """
    Tạo tài khoản, kèm email và vai trò trong CÙNG một lời gọi (mục 13.3).

    Vai trò được kiểm (tồn tại, đang dùng, không vượt quyền người tạo) TRƯỚC
    khi tạo tài khoản: kiểm sau thì lỗi ở bước gán để lại một tài khoản không
    quyền gì — đăng nhập được, mọi màn trống, và người tạo bấm tạo lại thì
    gặp "tên đã tồn tại".
    """
    from agent.api.nhan_su import chuan_email
    from agent.api.quyen import chan_cap_vuot, ghi_lich_su, quyen_cua_vai_tro

    email = chuan_email(body.email)
    vai = sorted({uuid.UUID(str(v)) for v in body.vai_tro_ids}, key=str)
    async with db.pool().acquire() as conn:
        if email and await conn.fetchval(
                "SELECT 1 FROM nguoi_dung WHERE lower(email) = $1", email):
            raise HTTPException(409, f"Email {email} đã dùng cho tài khoản khác.")
        ten_vai: list[str] = []
        if vai:
            ds = await conn.fetch(
                "SELECT id, ten, dang_dung FROM vai_tro WHERE id = ANY($1::uuid[])", vai)
            if len(ds) != len(vai):
                raise HTTPException(422, "Có vai trò không tồn tại")
            ngung = sorted(r["ten"] for r in ds if not r["dang_dung"])
            if ngung:
                raise HTTPException(422, f"Vai trò đã ngừng dùng: {', '.join(ngung)}")
            chan_cap_vuot(nguoi, await quyen_cua_vai_tro(conn, vai), "gán các vai trò này")
            ten_vai = sorted(r["ten"] for r in ds)
    try:
        r = await xac_thuc.tao_nguoi_dung(
            body.ten_dang_nhap, body.mat_khau, body.ho_ten, body.vai_tro,
            ghi_nhat_ky=False,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    uid = uuid.UUID(str(r["id"]))
    try:
        async with db.pool().acquire() as conn:
            async with conn.transaction():
                if email:
                    await conn.execute(
                        "UPDATE nguoi_dung SET email = $2 WHERE id = $1", uid, email)
                for vid in vai:
                    await conn.execute(
                        "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id, gan_boi) "
                        "VALUES ($1, $2, $3)", uid, vid,
                        uuid.UUID(str(nguoi["id"])) if nguoi.get("id") else None)
                await ghi_lich_su(
                    conn, "auth.tao_nguoi_dung", nguoi=nguoi, ref_id=uid,
                    ten_dang_nhap=r["ten_dang_nhap"], ten_moi=r["ten_dang_nhap"],
                    truoc=None,
                    sau={"ho_ten": r["ho_ten"], "email": email, "vai_tro": ten_vai,
                         "khoa": False},
                    them=ten_vai, bot=[])
    except Exception as exc:
        # Tài khoản ĐÃ tạo. Nói đúng điều ấy — không thì người ta bấm tạo lại
        # và gặp "tên đã tồn tại" mà không hiểu vì sao.
        raise HTTPException(409, (
            f"Đã tạo {r['ten_dang_nhap']} nhưng CHƯA cấp được vai trò/email "
            f"({type(exc).__name__}). Sửa trên dòng của họ ở tab Nhân viên.")) from exc
    return {**r, "email": email, "vai_tro_ten": ten_vai}


@router.post("/nguoi-dung/{ten}/khoa")
async def khoa_nguoi_dung(ten: str, khoa: bool = True, bo_qua_viec: bool = False,
                          nguoi: dict = Depends(can_quyen("nguoi_dung.sua"))) -> dict:
    """
    Khoá tài khoản và ĐÁ MỌI PHIÊN ĐANG MỞ.

    Khoá mà không xoá phiên thì người vừa bị khoá vẫn ngồi trong hệ thống
    tới lúc phiên hết hạn — với hệ thống nắm dữ liệu khách hàng, đó là bảy
    ngày quá nhiều.

    Còn giữ hội thoại hoặc việc chưa xong thì 409 kèm danh sách (mục 13.8),
    trừ khi `bo_qua_viec=true` — xem đầu `agent/api/nhan_su.py`. Chặn ở MÁY
    CHỦ chứ không chỉ ở hộp thoại: gọi thẳng API hay màn hình cũ đều phải
    gặp cùng một câu hỏi.

    Không bao giờ XOÁ tài khoản: người đã nghỉ vẫn là tác giả của tin đã
    gửi, người duyệt của bản nháp, người giao của việc — khoá là đủ.
    """
    if ten.strip().lower() == nguoi["ten_dang_nhap"]:
        raise HTTPException(422, "Không tự khoá tài khoản của mình được")
    from agent.api.nhan_su import viec_dang_giu
    from agent.api.quyen import (
        KhoaCungNgoaiHeThong,
        _con_nguoi_giu_quyen_song_con,
        chan_cap_vuot,
        ghi_lich_su,
        quyen_cua_nguoi,
    )

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT id, khoa FROM nguoi_dung WHERE ten_dang_nhap = $1 FOR UPDATE",
                ten.strip().lower())
            if cu is None:
                raise HTTPException(404, "Không có tài khoản này")
            # Khoá cấp trên = đá cấp trên ra khỏi hệ thống: cùng luật với gán vai trò.
            chan_cap_vuot(nguoi, await quyen_cua_nguoi(conn, cu["id"]), "khoá người này")
            viec: dict = {}
            if khoa and not cu["khoa"]:
                viec = await viec_dang_giu(conn, cu["id"])
                if viec["tong"] and not bo_qua_viec:
                    raise HTTPException(409, {
                        "can_chuyen_viec": True, "viec": viec,
                        "detail": (
                            f"{ten} đang giữ {viec['so_hoi_thoai']} hội thoại và "
                            f"{viec['so_cong_viec']} việc chưa xong. Khoá bây giờ là "
                            "khách của họ chờ mà không ai trả lời — chuyển việc "
                            "sang người khác trước, hoặc xác nhận để lại việc."),
                    })
            await conn.execute(
                "UPDATE nguoi_dung SET khoa = $2 WHERE id = $1", cu["id"], khoa)
            if khoa:
                await conn.execute("DELETE FROM phien WHERE nguoi_dung_id = $1", cu["id"])
                # Khoá cũng lấy đi một người giữ `nguoi_dung.sua`.
                if not await _con_nguoi_giu_quyen_song_con(conn):
                    raise KhoaCungNgoaiHeThong()
            if cu["khoa"] != khoa:
                await ghi_lich_su(
                    conn, "auth.khoa_nguoi_dung", nguoi=nguoi, ref_id=cu["id"],
                    ten=ten, ten_dang_nhap=ten, khoa=khoa,
                    truoc={"khoa": cu["khoa"]}, sau={"khoa": khoa},
                    de_lai_viec=({"so_hoi_thoai": viec["so_hoi_thoai"],
                                  "so_cong_viec": viec["so_cong_viec"]}
                                 if viec.get("tong") else None))
    return {"ok": True, "ten_dang_nhap": ten, "khoa": khoa}
