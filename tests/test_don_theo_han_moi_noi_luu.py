"""
Thời hạn lưu trữ phải áp cho MỌI nơi lưu dữ liệu cá nhân — Postgres thật.

Rà soát 16.11.2026: `don_theo_thoi_han` chỉ xoá `conversations`. Hồ sơ CRM
(tên, SĐT, email, ghi chú, nhãn, danh tính kênh), `ho_so_khach` và
`inbox_events.payload` (nguyên văn tin khách) còn MÃI — trái Luật 91/2025
Điều 3 khoản 3, và trái điều trang PDPD công bố ("lưu 180 ngày").

Canh cả hai chiều:
  · quá hạn và không còn gì mở -> ẩn danh / xoá, đếm riêng từng bảng;
  · khách còn đơn đang mở, hay mới nhắn -> GIỮ (quên nhầm khách đang chờ
    hàng là nhân viên không gọi giao được);
  · đơn hàng KHÔNG bị sửa (chứng từ kế toán 10 năm).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao, _sql  # noqa: E402

CU = "now() - interval '400 days'"


async def _dung_du_lieu(tk: str) -> dict:
    from agent import db

    async def khach(ten: str, sdt: str, cu: bool) -> str:
        luc = CU if cu else "now()"
        r = await db.fetchrow(
            f"INSERT INTO contacts (display_name, phone, email, last_seen, first_seen) "
            f"VALUES ($1, $2, $3, {luc}, {luc}) RETURNING id", ten, sdt, f"{sdt}@vi-du.vn")
        cid = r["id"]
        diem = await db.fetchrow(
            "INSERT INTO contact_points (contact_id, channel_account_id, external_user_id, handle) "
            "VALUES ($1, $2::uuid, $3, $4) RETURNING id", cid, tk, f"ext-{sdt}", ten)
        await db.execute("INSERT INTO contact_notes (contact_id, body) VALUES ($1, 'da dầu, hay nổi mụn')", cid)
        await db.execute("INSERT INTO contact_tags (contact_id, tag) VALUES ($1, 'vip')", cid)
        await db.execute(
            f"INSERT INTO conversations (channel, external_id, customer_name, contact_id, "
            f"contact_point_id, account_id, created_at, updated_at) "
            f"VALUES ('webchat', $1, $2, $3, $5, $4::uuid, {luc}, {luc})",
            f"cv-{sdt}", ten, cid, tk, diem["id"])
        return str(cid)

    quen = await khach("Chị Quên", "0911000001", cu=True)
    con_don = await khach("Chị Đang Chờ Hàng", "0911000002", cu=True)
    moi = await khach("Chị Mới", "0911000003", cu=False)
    # Đơn ĐÃ GIAO của khách bị quên: chứng từ, không được đụng.
    await db.execute(
        "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, tong_tien, trang_thai, "
        "created_at) VALUES ('DH-CU', 'Chị Quên', '0911000001', '1 Đường A', 100000, 'da_giao', "
        f"{CU})")
    # Đơn ĐANG MỞ của khách thứ hai: còn đơn thì chưa được quên.
    await db.execute(
        "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, tong_tien, trang_thai) "
        "VALUES ('DH-MO', 'Chị Đang Chờ Hàng', '0911000002', '2 Đường B', 200000, 'da_chot')")
    await db.execute(
        "INSERT INTO ho_so_khach (customer_ref, channel, ten, sdt, lan_dau, lan_cuoi) VALUES "
        f"('ref-cu', 'webchat', 'Chị Quên', '0911000001', {CU}, {CU}), "
        "('ref-moi', 'webchat', 'Chị Mới', '0911000003', now(), now())")
    await db.execute(
        "INSERT INTO inbox_events (account_id, topic, payload, created_at) VALUES "
        f"($1::uuid, 'message', '{{\"text\": \"số em 0911000001\"}}'::jsonb, {CU}), "
        "($1::uuid, 'message', '{\"text\": \"mới\"}'::jsonb, now())", tk)
    return {"quen": quen, "con_don": con_don, "moi": moi}


async def _doc(ids: dict) -> dict:
    from agent import db

    async def ho_so(cid):
        return dict(await db.fetchrow(
            "SELECT display_name, phone, email, status, "
            " (SELECT count(*) FROM contact_notes WHERE contact_id = c.id) AS ghi_chu, "
            " (SELECT count(*) FROM contact_tags WHERE contact_id = c.id) AS nhan, "
            " (SELECT string_agg(external_user_id, ',') FROM contact_points "
            "   WHERE contact_id = c.id) AS ext "
            "FROM contacts c WHERE id = $1::uuid", cid))

    return {
        **{k: await ho_so(v) for k, v in ids.items()},
        "don": {r["ma_don"]: dict(r) for r in await db.fetch(
            "SELECT ma_don, khach_ten, khach_sdt, khach_dia_chi FROM orders")},
        "ghi_nho": [r["customer_ref"] for r in await db.fetch("SELECT customer_ref FROM ho_so_khach")],
        "su_kien": int((await db.fetchrow("SELECT count(*) n FROM inbox_events"))["n"]),
        "hoi_thoai": int((await db.fetchrow(
            "SELECT count(*) n FROM conversations WHERE external_id LIKE 'cv-%'"))["n"]),
        "nhat_ky": [dict(r["detail"]) if isinstance(r["detail"], dict) else r["detail"]
                    for r in await db.fetch(
                        "SELECT detail FROM events WHERE kind = 'pdpd.don_theo_thoi_han'")],
    }


def test_het_han_thi_quen_khach_o_moi_noi_tru_don_hang(app_that, monkeypatch):
    from agent.config import settings
    from agent.core import du_lieu_ca_nhan

    monkeypatch.setattr(settings, "luu_hoi_thoai_ngay", 180)
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    ids = _sql(app_that, _dung_du_lieu, tk)

    xem = _sql(app_that, du_lieu_ca_nhan.don_theo_thoi_han, True)
    assert xem["so_ho_so_crm_qua_han"] == 1 and xem["so_ho_so_ghi_nho_qua_han"] == 1
    assert xem["so_su_kien_hop_thu_qua_han"] == 1 and xem["da_xoa"] == 0
    assert _sql(app_that, _doc, ids)["quen"]["phone"] == "0911000001", "chỉ đếm mà đã xoá"

    kq = _sql(app_that, du_lieu_ca_nhan.don_theo_thoi_han)
    sau = _sql(app_that, _doc, ids)

    # Khách quá hạn, không còn gì mở: ẩn danh hồ sơ, xoá ghi chú + nhãn, đổi danh tính kênh.
    q = sau["quen"]
    assert q["phone"] is None and q["email"] is None and q["status"] == "deleted"
    assert q["display_name"] == du_lieu_ca_nhan.AN_DANH
    assert q["ghi_chu"] == 0 and q["nhan"] == 0 and "ext-0911000001" not in q["ext"]
    # Khách còn đơn đang mở: GIỮ nguyên.
    assert sau["con_don"]["phone"] == "0911000002" and sau["con_don"]["ghi_chu"] == 1
    # Khách mới nhắn: GIỮ nguyên.
    assert sau["moi"]["phone"] == "0911000003" and sau["moi"]["nhan"] == 1
    # Hội thoại quá hạn xoá (2 cái cũ), cái mới còn.
    assert sau["hoi_thoai"] == 1 and kq["da_xoa"] == 2
    assert sau["ghi_nho"] == ["ref-moi"] and sau["su_kien"] == 1
    # Đơn hàng KHÔNG đổi một ký tự — chứng từ kế toán 10 năm.
    assert sau["don"]["DH-CU"]["khach_ten"] == "Chị Quên"
    assert sau["don"]["DH-CU"]["khach_sdt"] == "0911000001"
    assert sau["don"]["DH-MO"]["khach_dia_chi"] == "2 Đường B"

    # Nhật ký đếm RIÊNG từng bảng.
    nk = sau["nhat_ky"][-1]
    assert nk["so_hoi_thoai"] == 2 and nk["so_ho_so_ghi_nho"] == 1
    assert nk["so_su_kien_hop_thu"] == 1 and nk["crm_ho_so"] == 1
    assert nk["crm_ghi_chu"] == 1 and nk["crm_nhan"] == 1 and nk["crm_danh_tinh"] == 1
    assert "0911000001" not in str(nk), "nhật ký giữ lại thứ vừa hứa xoá"

    # Lượt sau: không còn gì quá hạn, không làm lại.
    lai = _sql(app_that, du_lieu_ca_nhan.don_theo_thoi_han)
    assert lai["da_xoa"] == 0 and lai["so_ho_so_crm_qua_han"] == 0
