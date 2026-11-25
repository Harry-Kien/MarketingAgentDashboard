"""
API Nhân sự: sửa thông tin nhân viên, việc đang giữ, chuyển việc, lịch sử.

Phiếu việc mục 13. Tạo/khoá tài khoản nằm ở `tai_khoan.py`, vai trò và gán
vai trò ở `quyen.py` — tệp này giữ phần còn lại của màn "Nhân sự & Phân
quyền", và dùng CHUNG luật chống leo thang (`chan_cap_vuot`) với hai tệp ấy.

VÌ SAO KHOÁ TÀI KHOẢN PHẢI HỎI VỀ VIỆC ĐANG GIỮ
-----------------------------------------------
Khoá một người đang giữ hội thoại là để khách của họ chờ trong im lặng: hội
thoại vẫn ở chế độ người (AI không trả lời), vẫn mang tên người đã khoá, và
không ai khác thấy nó trong "của tôi". Đó là hỏng im lặng đúng kiểu repo này
sợ nhất — không lỗi, không nhật ký, khách bỏ đi. Nên máy chủ (không chỉ màn
hình) từ chối khoá khi còn việc, trừ khi người khoá nói rõ "để lại việc".
"""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from agent import db
from agent.core import xac_thuc

from .quyen import chan_cap_vuot, ghi_lich_su, quyen_cua_nguoi
from .routes import can_quyen

router = APIRouter(prefix="/api", tags=["nhan_su"])

# Hội thoại một người ĐANG GIỮ: cùng định nghĩa với
# `routing.nguoi_dang_giu` — được giao VÀ đang ở tay người. Hội thoại AI
# đang tự xử lý mà `assigned_to` trỏ vào người này thì không bị gián đoạn
# khi họ bị khoá (AI vẫn trả lời, bộ định tuyến bỏ qua người đã khoá).
_SQL_HOI_THOAI_DANG_GIU = (
    "SELECT id, version, assigned_team_id, customer_name, channel, updated_at "
    "FROM conversations "
    "WHERE assigned_to = $1 AND mode = 'human' "
    "  AND state NOT IN ('resolved', 'closed') "
    "ORDER BY updated_at DESC"
)

_SQL_VIEC_CHUA_XONG = (
    "SELECT id, tieu_de, trang_thai, han FROM cong_viec "
    "WHERE nguoi_nhan = $1 AND trang_thai IN ('moi', 'dang_lam') "
    "ORDER BY han NULLS LAST, tao_luc"
)

# Các loại sự kiện màn Lịch sử nhân sự đọc, kèm nhãn hiện trên màn hình.
# Khai TƯỜNG MINH, không lọc theo tiền tố `vai_tro.%`: thêm một loại sự kiện
# mới mà quên khai ở đây thì nó vắng khỏi màn Lịch sử — có test bắt mọi
# `ghi_lich_su(` trong mã phải có loại nằm trong bảng này.
LOAI_LICH_SU: dict[str, str] = {
    "vai_tro.tao": "Tạo vai trò",
    "vai_tro.sua": "Sửa vai trò",
    "vai_tro.xoa": "Xoá vai trò",
    "vai_tro.ngung_dung": "Ngừng dùng vai trò",
    "vai_tro.dung_lai": "Dùng lại vai trò",
    "nguoi_dung.vai_tro": "Đổi vai trò của nhân viên",
    "auth.tao_nguoi_dung": "Tạo tài khoản",
    "nguoi_dung.sua": "Sửa thông tin nhân viên",
    "auth.khoa_nguoi_dung": "Khoá / mở khoá tài khoản",
    "nguoi_dung.chuyen_viec": "Chuyển việc sang người khác",
    "nguoi_dung.dat_lai_mat_khau": "Đặt lại mật khẩu",
}

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def chuan_email(email: str | None) -> str | None:
    """Rỗng -> None (không có email). Sai dạng -> 422, không lưu."""
    sach = (email or "").strip().lower()
    if not sach:
        return None
    if len(sach) > 200 or not _EMAIL.match(sach):
        raise HTTPException(422, f"Email không hợp lệ: {sach[:60]}")
    return sach


async def viec_dang_giu(conn, nguoi_dung_id: UUID) -> dict[str, Any]:
    """Hội thoại đang giữ + việc chưa xong của một người, kèm tổng."""
    hoi_thoai = await conn.fetch(_SQL_HOI_THOAI_DANG_GIU, nguoi_dung_id)
    viec = await conn.fetch(_SQL_VIEC_CHUA_XONG, nguoi_dung_id)
    return {
        "so_hoi_thoai": len(hoi_thoai),
        "so_cong_viec": len(viec),
        "tong": len(hoi_thoai) + len(viec),
        # Cắt 50 dòng cho màn hình; con số tổng ở trên luôn đúng.
        "hoi_thoai": [{"id": str(r["id"]), "khach": r["customer_name"] or "",
                       "kenh": r["channel"]} for r in hoi_thoai[:50]],
        "cong_viec": [{"id": str(r["id"]), "tieu_de": r["tieu_de"],
                       "trang_thai": r["trang_thai"],
                       "han": r["han"].isoformat() if r["han"] else None}
                      for r in viec[:50]],
    }


class SuaNguoiDungIn(BaseModel):
    ho_ten: str = Field(min_length=1, max_length=120)
    email: str | None = Field(None, max_length=200)


class DatLaiMatKhauIn(BaseModel):
    # Để trống (None) = máy chủ tự sinh và trả về MỘT lần trong phản hồi.
    mat_khau_tam: str | None = Field(None, min_length=8, max_length=200)


class ChuyenViecIn(BaseModel):
    nguoi_nhan: UUID
    hoi_thoai: bool = True
    cong_viec: bool = True


@router.put("/nguoi-dung/{nguoi_dung_id}")
async def sua_nguoi_dung(
    nguoi_dung_id: UUID,
    body: SuaNguoiDungIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Sửa họ tên, email. Tên đăng nhập KHÔNG đổi ở đây: nó là khoá của nút
    khoá, của `events.actor`, của mọi dòng nhật ký cũ — đổi nó là cắt đứt
    lịch sử của chính người này.
    """
    email = chuan_email(body.email)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten_dang_nhap, ho_ten, email FROM nguoi_dung "
                "WHERE id = $1 FOR UPDATE", nguoi_dung_id)
            if cu is None:
                raise HTTPException(404, "Không tìm thấy nhân viên")
            chan_cap_vuot(nguoi, await quyen_cua_nguoi(conn, nguoi_dung_id),
                          "sửa thông tin người này")
            try:
                await conn.execute(
                    "UPDATE nguoi_dung SET ho_ten = $2, email = $3 WHERE id = $1",
                    nguoi_dung_id, body.ho_ten.strip(), email)
            except asyncpg.UniqueViolationError as exc:
                raise HTTPException(409, f"Email {email} đã dùng cho tài khoản khác.") from exc
            truoc = {"ho_ten": cu["ho_ten"], "email": cu["email"]}
            sau = {"ho_ten": body.ho_ten.strip(), "email": email}
            if truoc != sau:
                await ghi_lich_su(conn, "nguoi_dung.sua", nguoi=nguoi,
                                  ref_id=nguoi_dung_id,
                                  ten_dang_nhap=cu["ten_dang_nhap"],
                                  truoc=truoc, sau=sau)
    return {"id": str(nguoi_dung_id), "ten_dang_nhap": cu["ten_dang_nhap"], **sau}


@router.post("/nguoi-dung/{nguoi_dung_id}/dat-lai-mat-khau")
async def dat_lai_mat_khau(
    nguoi_dung_id: UUID,
    body: DatLaiMatKhauIn,
    response: Response,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Quản trị đặt lại mật khẩu cho nhân viên quên mật khẩu (UX-13-07).

    Bốn việc, cùng một giao dịch, thiếu việc nào cũng là lỗ:
      - `chan_cap_vuot`: đặt lại mật khẩu của cấp trên = đăng nhập được
        bằng tài khoản cấp trên. Đó là leo thang quyền đi đường vòng, nên
        cùng luật với gán vai trò và khoá;
      - thu hồi MỌI phiên: ai đang ngồi trong tài khoản bằng mật khẩu cũ
        (người chiếm được nó — lý do hay gặp nhất của việc đặt lại) phải ra;
      - bật cờ `phai_doi_mat_khau`: mật khẩu tạm là thứ quản trị biết; máy
        chủ chặn mọi màn tới khi chủ tài khoản đổi;
      - lịch sử KHÔNG chứa mật khẩu, kể cả bản tự sinh: bảng `events` đọc
        được bởi mọi ai có `nhat_ky.doc`.

    Không tự đặt lại cho mình ở đây: đường đó bỏ qua bước gõ lại mật khẩu
    hiện tại của `/api/toi/doi-mat-khau` — phiên bị chiếm sẽ tự đổi mật khẩu
    rồi đá chủ thật ra.
    """
    if str(nguoi_dung_id) == str(nguoi.get("id")):
        raise HTTPException(422, (
            "Không đặt lại mật khẩu của chính mình ở đây — dùng “đổi mật khẩu” "
            "(cần mật khẩu hiện tại)."))
    tu_sinh = not body.mat_khau_tam
    mat_khau = body.mat_khau_tam or xac_thuc.sinh_mat_khau_tam()
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            cu = await conn.fetchrow(
                "SELECT ten_dang_nhap FROM nguoi_dung WHERE id = $1 FOR UPDATE",
                nguoi_dung_id)
            if cu is None:
                raise HTTPException(404, "Không tìm thấy nhân viên")
            chan_cap_vuot(nguoi, await quyen_cua_nguoi(conn, nguoi_dung_id),
                          "đặt lại mật khẩu của người này")
            await conn.execute(
                "UPDATE nguoi_dung SET mat_khau_bam = $2, phai_doi_mat_khau = true "
                "WHERE id = $1", nguoi_dung_id, xac_thuc.bam_mat_khau(mat_khau))
            so_phien = len(await conn.fetch(
                "DELETE FROM phien WHERE nguoi_dung_id = $1 RETURNING 1",
                nguoi_dung_id))
            await ghi_lich_su(
                conn, "nguoi_dung.dat_lai_mat_khau", nguoi=nguoi,
                ref_id=nguoi_dung_id, ten_dang_nhap=cu["ten_dang_nhap"],
                tu_sinh=tu_sinh, so_phien_thu_hoi=so_phien,
                phai_doi_mat_khau=True)
    # Người quên mật khẩu thường đã gõ sai vài lần: bộ đếm sai còn giữ thì
    # mật khẩu tạm đúng vẫn bị "Sai quá nhiều lần" — quản trị tưởng đặt lại
    # hỏng.
    xac_thuc.xoa_that_bai(cu["ten_dang_nhap"])
    # Phản hồi mang mật khẩu: không cho trình duyệt hay proxy nào giữ bản sao.
    response.headers["Cache-Control"] = "no-store"
    ra: dict[str, Any] = {
        "ok": True, "ten_dang_nhap": cu["ten_dang_nhap"],
        "so_phien_thu_hoi": so_phien, "phai_doi_mat_khau": True,
    }
    if tu_sinh:
        ra["mat_khau_tam"] = mat_khau
    return ra


@router.get("/nguoi-dung/{nguoi_dung_id}/viec-dang-giu")
async def xem_viec_dang_giu(
    nguoi_dung_id: UUID,
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    """Màn Nhân viên gọi trước khi khoá — để CẢNH BÁO, không đợi máy chủ từ chối."""
    async with db.pool().acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM nguoi_dung WHERE id = $1", nguoi_dung_id):
            raise HTTPException(404, "Không tìm thấy nhân viên")
        return await viec_dang_giu(conn, nguoi_dung_id)


@router.post("/nguoi-dung/{nguoi_dung_id}/chuyen-viec")
async def chuyen_viec(
    nguoi_dung_id: UUID,
    body: ChuyenViecIn,
    nguoi: dict = Depends(can_quyen("nguoi_dung.sua")),
) -> dict[str, Any]:
    """
    Chuyển HÀNG LOẠT hội thoại đang giữ và việc chưa xong sang người khác.

    Hội thoại đi qua ĐÚNG đường giao thường ngày (`ConversationRoutingService.
    takeover`), không UPDATE thẳng: luật giao — người nhận phải là thành viên
    kênh, phải thuộc nhóm nếu có nhóm, ai được giao cho người khác — là luật
    nghiệp vụ, đứng độc lập với phân quyền (mục 12.7). Hội thoại nào luật ấy
    từ chối thì báo lại trong `khong_chuyen_duoc`, không nuốt.

    Ba lớp quyền, mỗi lớp một lý do:
      - `nguoi_dung.sua`: đây là thao tác quản lý nhân sự;
      - `hoi_thoai.nhan` / `cong_viec.giao`: chính là quyền giao từng thứ ấy
        ở màn Hội thoại / Công việc — đi đường vòng qua màn Nhân sự không
        được rộng hơn đường chính;
      - `chan_cap_vuot`: không lấy việc của người mạnh hơn mình.
    """
    from agent.core import thong_bao_noi_bo
    from agent.omnichannel.routing import (
        AssignmentDenied,
        ConversationRoutingService,
        PostgresRoutingRepository,
        RoutingError,
    )

    if not (body.hoi_thoai or body.cong_viec):
        raise HTTPException(422, "Chọn ít nhất hội thoại hoặc công việc để chuyển.")
    thieu = [q for q, can in (("hoi_thoai.nhan", body.hoi_thoai),
                              ("cong_viec.giao", body.cong_viec))
             if can and not xac_thuc.duoc_phep(nguoi, q)]
    if thieu:
        raise HTTPException(403, f"Thiếu quyền: {', '.join(thieu)}")
    if body.nguoi_nhan == nguoi_dung_id:
        raise HTTPException(422, "Người nhận phải là người khác.")

    async with db.pool().acquire() as conn:
        tu = await conn.fetchrow(
            "SELECT ten_dang_nhap FROM nguoi_dung WHERE id = $1", nguoi_dung_id)
        if tu is None:
            raise HTTPException(404, "Không tìm thấy nhân viên")
        chan_cap_vuot(nguoi, await quyen_cua_nguoi(conn, nguoi_dung_id),
                      "chuyển việc của người này")
        den = await conn.fetchrow(
            "SELECT ten_dang_nhap, khoa FROM nguoi_dung WHERE id = $1", body.nguoi_nhan)
        if den is None:
            raise HTTPException(404, "Không tìm thấy người nhận")
        if den["khoa"]:
            raise HTTPException(422, "Người nhận đang bị khoá — chuyển sang là việc lại treo.")
        # Người nhận phải LÀM ĐƯỢC việc được chuyển. Chuyển hội thoại cho
        # người không trả lời khách được là đổi một kiểu treo lấy kiểu khác.
        quyen_nhan = await quyen_cua_nguoi(conn, body.nguoi_nhan)
        if body.hoi_thoai and "hoi_thoai.tra_loi" not in quyen_nhan:
            raise HTTPException(422, (
                f"{den['ten_dang_nhap']} không có quyền trả lời khách "
                "(hoi_thoai.tra_loi) — chọn người khác."))
        if body.cong_viec and "cong_viec.doc" not in quyen_nhan:
            raise HTTPException(422, (
                f"{den['ten_dang_nhap']} không có quyền xem công việc "
                "(cong_viec.doc) — chọn người khác."))
        hoi_thoai = (await conn.fetch(_SQL_HOI_THOAI_DANG_GIU, nguoi_dung_id)
                     if body.hoi_thoai else [])

    actor_id = UUID(str(nguoi["id"]))
    xem_tat_ca = xac_thuc.duoc_phep(nguoi, "hoi_thoai.xem_tat_ca")
    dich_vu = ConversationRoutingService(PostgresRoutingRepository())
    ly_do = f"Chuyển việc từ {tu['ten_dang_nhap']} sang {den['ten_dang_nhap']}"
    da_chuyen: list[str] = []
    khong_duoc: list[dict[str, str]] = []
    for c in hoi_thoai:
        # Giữ nhóm cũ nếu người nhận thuộc nhóm ấy; không thì giao không
        # kèm nhóm — một hội thoại có người giữ còn hơn một hội thoại kẹt
        # vì người nhận không ở nhóm Kho.
        doi_nhom = [c["assigned_team_id"], None] if c["assigned_team_id"] else [None]
        loi = ""
        for nhom in doi_nhom:
            try:
                ban = await _version_moi_nhat(c["id"])
                await dich_vu.takeover(
                    conversation_id=c["id"], actor_id=actor_id,
                    assignee_id=body.nguoi_nhan, expected_version=ban,
                    reason=ly_do, team_id=nhom, actor_is_admin=xem_tat_ca)
                da_chuyen.append(str(c["id"]))
                loi = ""
                break
            except AssignmentDenied as exc:
                loi = str(exc)
            except RoutingError as exc:
                loi = str(exc)
                break
        if loi:
            khong_duoc.append({"id": str(c["id"]), "khach": c["customer_name"] or "",
                               "ly_do": loi})

    viec: list[asyncpg.Record] = []
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if body.cong_viec:
                # Lịch sử từng việc (trigger 0061) ghi đúng người chuyển và lý
                # do — không thì mỗi dòng "chuyển việc" mang người thao tác
                # "Hệ thống" và không ai truy được vì sao việc đổi chủ.
                from agent.core import cong_viec as cv

                await cv.dat_ngu_canh(conn, nguoi_id=actor_id, ghi_chu=ly_do)
                viec = await conn.fetch(
                    "UPDATE cong_viec SET nguoi_nhan = $2, sua_luc = now() "
                    "WHERE nguoi_nhan = $1 AND trang_thai IN ('moi', 'dang_lam') "
                    "RETURNING id, tieu_de",
                    nguoi_dung_id, body.nguoi_nhan)
            await ghi_lich_su(
                conn, "nguoi_dung.chuyen_viec", nguoi=nguoi, ref_id=nguoi_dung_id,
                ten_dang_nhap=tu["ten_dang_nhap"],
                truoc={"nguoi": tu["ten_dang_nhap"]},
                sau={"nguoi": den["ten_dang_nhap"]},
                so_hoi_thoai=len(da_chuyen), so_cong_viec=len(viec),
                khong_chuyen_duoc=len(khong_duoc))

    # Báo người nhận SAU khi đã ghi xong: chuông hỏng không được làm hỏng lượt
    # chuyển (cùng thứ tự với route giao hội thoại thường ngày).
    for cid in da_chuyen:
        await thong_bao_noi_bo.bao_duoc_giao_hoi_thoai(
            UUID(cid), body.nguoi_nhan, boi=actor_id)
    for v in viec:
        await thong_bao_noi_bo.bao_duoc_giao_viec(
            v["id"], body.nguoi_nhan, boi=actor_id, tieu_de_viec=v["tieu_de"] or "",
            chuyen=True)

    return {
        "nguoi_nhan": den["ten_dang_nhap"],
        "so_hoi_thoai": len(da_chuyen),
        "so_cong_viec": len(viec),
        "khong_chuyen_duoc": khong_duoc,
    }


async def _version_moi_nhat(conversation_id: UUID) -> int:
    """
    `version` MỚI NHẤT ngay trước khi giao: danh sách đọc ở đầu lượt có thể
    đã cũ (khách vừa nhắn thêm), và takeover với version cũ là 409 oan.
    """
    r = await db.fetchrow(
        "SELECT version FROM conversations WHERE id = $1", conversation_id)
    return int(r["version"]) if r else 0


@router.get("/nhan-su/lich-su")
async def lich_su_nhan_su(
    ref_id: UUID | None = None,
    loai: str = Query("tat_ca", pattern="^(tat_ca|vai_tro|nguoi_dung)$"),
    limit: int = Query(100, ge=1, le=300),
    _q: dict = Depends(can_quyen("nguoi_dung.doc")),
) -> dict[str, Any]:
    """
    Lịch sử nhân sự và phân quyền: AI, LÚC NÀO, VAI TRÒ/NGƯỜI NÀO, ĐỔI GÌ
    (trước/sau). Mục 12.8 và 13.10.
    """
    loai_ds = [k for k in LOAI_LICH_SU
               if loai == "tat_ca"
               or (loai == "vai_tro" and k.startswith("vai_tro."))
               or (loai == "nguoi_dung" and not k.startswith("vai_tro."))]
    rows = await db.fetch(
        "SELECT id, kind, actor, ref_id, detail, created_at FROM events "
        "WHERE kind = ANY($1::text[]) AND ($2::uuid IS NULL OR ref_id = $2) "
        "ORDER BY created_at DESC, id DESC LIMIT $3",
        loai_ds, ref_id, limit)
    ra = []
    for r in rows:
        ct = r["detail"]
        # Dòng cũ có thể bị mã hoá hai lần (chuỗi JSON trong JSONB) — xem
        # ghi chú codec ở `agent/db.py`. Không giải thì màn Lịch sử hiện một
        # chuỗi `{"ten": ...}` thô ở đúng chỗ cần đọc.
        if isinstance(ct, str):
            try:
                ct = json.loads(ct)
            except ValueError:
                ct = {"ghi_chu": ct}
        ra.append({
            "id": r["id"], "loai": r["kind"], "nhan": LOAI_LICH_SU[r["kind"]],
            "nguoi_lam": r["actor"],
            "ref_id": str(r["ref_id"]) if r["ref_id"] else None,
            "luc": r["created_at"].isoformat(),
            "chi_tiet": ct if isinstance(ct, dict) else {"ghi_chu": ct},
        })
    return {"lich_su": ra}
