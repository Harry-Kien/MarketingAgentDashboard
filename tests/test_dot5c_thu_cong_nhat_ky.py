"""
Bộ kiểm thử hồi quy ĐỢT 5C — Hoàn tất xử lý thủ công đề xuất sửa đơn & Đồng bộ
Nhật ký kiểm toán.

Chạy trên PostgreSQL `kiemthu` (schema cô lập) và ERPNext mock chỉ đọc (`doc_don`),
không chạm `marketing_agent`, không gọi ERPNext ghi thật, không gửi tin thật.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from agent import db
from agent.api import nhat_ky_api, phu_thuoc, uy_quyen_ai as api
from agent.config import ROOT
from agent.core import (
    nhat_ky_kiem_toan as nk,
    thao_tac_don,
    thong_bao_noi_bo,
    uy_quyen,
)
from agent.erp import nha_may


def test_dot5c_hoan_tat_thu_cong_va_dong_bo_nhat_ky_kiemthu(monkeypatch):
    url = os.getenv("KIEMTHU_URL", "postgresql://agent:agent@127.0.0.1:5433/kiemthu")
    assert urlparse(url).path == "/kiemthu", "Chỉ được dùng CSDL kiểm thử kiemthu"

    async def run():
        try:
            admin = await asyncpg.connect(url, timeout=3)
        except (OSError, asyncpg.PostgresError):
            pytest.skip("CSDL kiemthu chưa khả dụng")
        assert await admin.fetchval("SELECT current_database()") == "kiemthu"
        schema = "test_dot5c_" + uuid4().hex
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        pool = None
        try:
            async def setup(conn):
                await conn.set_type_codec(
                    "jsonb",
                    schema="pg_catalog",
                    encoder=json.dumps,
                    decoder=json.loads,
                )

            pool = await asyncpg.create_pool(
                url,
                min_size=1,
                max_size=5,
                server_settings={"search_path": schema},
                init=setup,
            )
            monkeypatch.setattr(db, "_pool", pool)
            await db.execute(
                """
                CREATE TABLE conversations(id uuid PRIMARY KEY, account_id uuid);
                CREATE TABLE channel_accounts(id uuid PRIMARY KEY, channel text, display_name text);
                CREATE TABLE messages(
                    id uuid PRIMARY KEY, conversation_id uuid, role text DEFAULT 'agent',
                    content text DEFAULT '', direction text DEFAULT 'outbound',
                    delivery_status text DEFAULT 'sent', created_at timestamptz DEFAULT now(),
                    dau_vet_ai jsonb, duyet_boi uuid, duyet_luc timestamptz,
                    sua_boi text, sua_luc timestamptz
                );
                CREATE TABLE nguoi_dung(id uuid PRIMARY KEY, ten_dang_nhap text, ho_ten text);
                CREATE TABLE orders(
                    id uuid PRIMARY KEY, conversation_id uuid, ma_don text,
                    trang_thai text, items jsonb, updated_at timestamptz DEFAULT now(),
                    erp_ma_don text, ma_van_don text, trang_thai_giao_hang text,
                    yeu_cau_huy_luc timestamptz
                );
                CREATE TABLE events(
                    id bigserial PRIMARY KEY, kind text, actor text,
                    ref_id uuid, detail jsonb DEFAULT '{}'::jsonb,
                    created_at timestamptz DEFAULT now()
                );
                -- Mô hình đọc nhật ký phân giải đối tượng (công việc) và quyền mở
                -- hội thoại theo kênh của người xem (UX-18-03).
                CREATE TABLE cong_viec(
                    id uuid PRIMARY KEY, tieu_de text, nguoi_nhan uuid, nguoi_giao uuid
                );
                CREATE TABLE account_memberships(account_id uuid, user_id uuid);
                """
            )
            mig_dir = Path(__file__).parents[1] / "agent/migrations/versions"
            await db.execute((mig_dir / "0065_uy_quyen_ai.sql").read_text())
            await db.execute((mig_dir / "0066_de_xuat_sua_don_thu_cong.sql").read_text())

            acc_id, cid, oid, uid = uuid4(), uuid4(), uuid4(), uuid4()
            await db.execute(
                "INSERT INTO channel_accounts VALUES ($1, 'webchat', 'Webshop Test')",
                acc_id,
            )
            await db.execute("INSERT INTO conversations VALUES ($1, $2)", cid, acc_id)
            await db.execute("INSERT INTO nguoi_dung VALUES ($1, 'nv_kho', 'Nhân viên Kho')", uid)
            await db.execute(
                "INSERT INTO orders (id, conversation_id, ma_don, trang_thai, items, erp_ma_don) "
                "VALUES ($1, $2, 'DH-5C', 'da_chot', $3, 'SO-5C')",
                oid,
                cid,
                [{"ma": "SP1", "ten": "Serum 5C", "so_luong": 1, "don_gia": 100000}],
            )
            # Tạo 1 đề xuất tự động hoàn tất (tao_don) để đối chiếu phân biệt với thủ công
            auto_did = uuid4()
            await db.execute(
                """
                INSERT INTO ai_de_xuat (id, conversation_id, hanh_dong, che_do_ai, muc_uy_quyen,
                    ly_do_can_duyet, trang_thai, order_id, de_xuat, khoa_trung, het_han_luc,
                    duyet_boi, duyet_luc, thuc_hien_luc, ket_qua)
                VALUES ($1, $2, 'tao_don', 'goi_y', 'co_phe_duyet', 'Gợi ý', 'da_thuc_hien',
                        $3, '{"tieu_de":"Lên đơn tự động"}'::jsonb, 'auto:1', now() + interval '1 day',
                        $4, now(), now(), '{"ma_don":"DH-AUTO","ok":true}'::jsonb)
                """,
                auto_did,
                cid,
                oid,
                uid,
            )

            monkeypatch.setattr(uy_quyen, "han_gio", AsyncMock(return_value=24))
            monkeypatch.setattr(thong_bao_noi_bo, "bao_can_duyet_de_xuat", AsyncMock())

            erp_state = {
                "name": "SO-5C",
                "docstatus": 1,
                "status": "To Deliver and Bill",
                "modified": "2026-11-25 10:00:00",
            }
            erp_read = AsyncMock(side_effect=lambda _name: dict(erp_state))
            # Cổng ERP giả lập CHỈ có doc_don — đảm bảo không bao giờ gọi ghi ERPNext
            monkeypatch.setattr(nha_may, "cong", lambda: type("ReadOnlyERP", (), {"doc_don": erp_read})())

            args = dict(ma_don="DH-5C", ma_san_pham="SP1", so_luong=2, ly_do="Khách đổi sang 2 chai")
            res_tao = await thao_tac_don.de_xuat_sua_don(args, cid)
            assert res_tao["da_de_xuat"] is True and res_tao["da_sua"] is False
            did = res_tao["de_xuat_id"]

            app = FastAPI()
            app.include_router(api.router)
            app.include_router(nhat_ky_api.router)
            user = dict(
                id=uid,
                ten_dang_nhap="nv_kho",
                quyen=["ai.duyet", "don.sua", "hoi_thoai.doc", "nhat_ky.doc"],
            )
            app.dependency_overrides[phu_thuoc.nguoi_da_dang_nhap] = lambda: user

            channel_guard = AsyncMock()
            monkeypatch.setattr(api, "chan_neu_ngoai_kenh", channel_guard)
            monkeypatch.setattr(nhat_ky_api, "chan_neu_ngoai_kenh", channel_guard)

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                duyet_path = f"/api/ai-de-xuat/{did}/duyet"
                thu_cong_path = f"/api/ai-de-xuat/{did}/hoan-tat-thu-cong"

                # 1. Không thể đóng thủ công khi đề xuất vẫn đang ở `cho_duyet`
                r_chua_duyet = await client.post(
                    thu_cong_path, json={"ghi_chu": "Đã kiểm tra đơn"}
                )
                assert r_chua_duyet.status_code == 409

                # 2. Duyệt -> chuyển sang `cho_xu_ly_thu_cong` (chưa sửa đơn)
                r_duyet = await client.post(duyet_path)
                assert r_duyet.status_code == 200
                assert r_duyet.json()["trang_thai"] == "cho_xu_ly_thu_cong"

                # 3. Kiểm tra phân quyền chặt: thiếu `ai.duyet` hoặc `don.sua` hoặc ngoài kênh -> 403
                for q in ("ai.duyet", "don.sua"):
                    user["quyen"].remove(q)
                    assert (
                        await client.post(thu_cong_path, json={"ghi_chu": "Đã sửa trên ERP"})
                    ).status_code == 403
                    user["quyen"].append(q)

                channel_guard.side_effect = api.HTTPException(403, "Ngoài phạm vi kênh")
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Đã sửa trên ERP"})
                ).status_code == 403
                channel_guard.side_effect = None

                # 4. Thiếu ghi chú / ghi chú quá ngắn -> 422
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "  "})
                ).status_code == 422

                # 5. Chưa có bằng chứng thay đổi trên đơn & ERP -> từ chối đóng (409), giữ khoá chống trùng
                r_no_evidence = await client.post(
                    thu_cong_path, json={"ghi_chu": "Bấm xác nhận thử khi chưa sửa"}
                )
                assert r_no_evidence.status_code == 409
                assert "bằng chứng" in r_no_evidence.json()["detail"].lower()

                # Trong khi đang `cho_xu_ly_thu_cong`, đề xuất giống hệt không tạo bản thứ 2
                res_dup = await thao_tac_don.de_xuat_sua_don(args, cid)
                assert res_dup["de_xuat_id"] == did

                # 6. Chỉ thay đổi `updated_at` hoặc trường không liên quan (`ma_van_don`), SL vẫn là 1 -> 409
                await db.execute(
                    "UPDATE orders SET updated_at = now() + interval '30 seconds', ma_van_don = 'VD-KHAC' WHERE id = $1",
                    oid,
                )
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Chỉ chạm updated_at"})
                ).status_code == 409

                # 6b. Thay đổi ERP `modified`, nhưng số lượng trên đơn vẫn là 1 -> 409
                erp_state["modified"] = "2026-11-25 10:15:00"
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "ERP modified đổi nhưng SP1 vẫn 1"})
                ).status_code == 409

                # 6c. Thay đổi sai sản phẩm (thêm/sửa SP2=2, SP1 vẫn là 1) -> 409
                await db.execute(
                    "UPDATE orders SET items = $2, ma_van_don = NULL WHERE id = $1",
                    oid,
                    [
                        {"ma": "SP1", "ten": "Serum 5C", "so_luong": 1, "don_gia": 100000},
                        {"ma": "SP2", "ten": "Kem dưỡng", "so_luong": 2, "don_gia": 200000},
                    ],
                )
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Sửa nhầm SP2"})
                ).status_code == 409

                # 6d. Thay đổi sai số lượng (SP1=5 thay vì 2 khách yêu cầu) -> 409
                await db.execute(
                    "UPDATE orders SET items = $2 WHERE id = $1",
                    oid,
                    [{"ma": "SP1", "ten": "Serum 5C", "so_luong": 5, "don_gia": 100000}],
                )
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Sửa nhầm sang 5"})
                ).status_code == 409

                # 6e. SP1 đúng = 2 nhưng ERPNext chưa ghi nhận thay đổi `modified` -> 409
                erp_state["modified"] = "2026-11-25 10:00:00"
                await db.execute(
                    "UPDATE orders SET items = $2 WHERE id = $1",
                    oid,
                    [{"ma": "SP1", "ten": "Serum 5C", "so_luong": 2, "don_gia": 100000}],
                )
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "ERP chưa đổi modified"})
                ).status_code == 409

                # 6f. Lỗi đọc ERP (timeout) -> 503 fail-closed, đề xuất vẫn `cho_xu_ly_thu_cong`
                erp_read.side_effect = TimeoutError("ERP timeout")
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Đã sửa trên ERP"})
                ).status_code == 503
                erp_read.side_effect = lambda _name: dict(erp_state)

                # Sau tất cả các ca không đủ bằng chứng trên, trạng thái VẪN phải là `cho_xu_ly_thu_cong`
                assert (
                    await db.fetchrow("SELECT trang_thai FROM ai_de_xuat WHERE id = $1", UUID(did))
                )["trang_thai"] == "cho_xu_ly_thu_cong"

                # 7. Nhân viên xử lý thực tế: cập nhật ERP (modified đổi) + số lượng đơn khớp 2
                erp_state["modified"] = "2026-11-25 10:15:00"
                await db.execute(
                    "UPDATE orders SET items = $2, updated_at = now() + interval '1 minute' WHERE id = $1",
                    oid,
                    [{"ma": "SP1", "ten": "Serum 5C", "so_luong": 2, "don_gia": 100000}],
                )

                # 8. Gọi xác nhận đồng thời -> chỉ 1 yêu cầu thành công (200), yêu cầu đua bị 409
                resps = await asyncio.gather(
                    client.post(
                        thu_cong_path,
                        json={"ghi_chu": "Đã cập nhật số lượng thành 2 trên ERPNext", "ma_tham_chieu": "SO-5C-UPD"},
                    ),
                    client.post(
                        thu_cong_path,
                        json={"ghi_chu": "Nhân viên thứ 2 bấm trùng", "ma_tham_chieu": "SO-5C-UPD"},
                    ),
                )
                assert sorted(r.status_code for r in resps) == [200, 409]
                ok_json = next(r.json() for r in resps if r.status_code == 200)
                assert ok_json["ok"] is True
                assert ok_json["trang_thai"] == "da_thuc_hien"
                assert ok_json["nhan_trang_thai"] == "Đã xử lý thủ công"
                assert ok_json["ket_qua"]["qua"] == "xu_ly_thu_cong"
                assert ok_json["ket_qua"]["tu_dong"] is False
                assert ok_json["ket_qua"]["xu_ly_thu_cong"] is True
                assert ok_json["ket_qua"]["bang_chung"]["thay_doi_erp"] is True
                assert ok_json["ket_qua"]["bang_chung"]["da_khop_so_luong_yeu_cau"] is True

                # Gọi lại lần 3 -> vẫn 409
                assert (
                    await client.post(thu_cong_path, json={"ghi_chu": "Xác nhận lại lần 3"})
                ).status_code == 409

                # 9. Danh sách đề xuất trên API phân biệt rõ `Đã xử lý thủ công` vs `Đã thực hiện` (tự động)
                r_ds = await client.get(f"/api/ai-de-xuat?hoi_thoai={cid}")
                assert r_ds.status_code == 200
                cards = {d["id"]: d for d in r_ds.json()["de_xuat"]}
                assert cards[str(did)]["nhan_trang_thai"] == "Đã xử lý thủ công"
                assert cards[str(did)]["duoc_hoan_tat_thu_cong"] is False
                assert cards[str(auto_did)]["nhan_trang_thai"] == "Đã thực hiện"

                # 10. Khóa chống trùng được giải phóng sau khi đóng hợp lệ -> tạo đề xuất mới thành công
                args_moi = dict(ma_don="DH-5C", ma_san_pham="SP1", so_luong=3, ly_do="Khách đổi tiếp lên 3")
                res_moi = await thao_tac_don.de_xuat_sua_don(args_moi, cid)
                assert res_moi["da_de_xuat"] is True and res_moi["de_xuat_id"] != did

                # 11. Đồng bộ Nhật ký kiểm toán: nhãn tiếng Việt, bộ lọc, phân biệt thủ công vs tự động, CSV
                r_nk = await client.get("/api/nhat-ky")
                assert r_nk.status_code == 200
                items_nk = r_nk.json()["items"]
                by_kind = {x["kind"]: x for x in items_nk}
                assert by_kind["ai.de_xuat.cho_xu_ly_thu_cong"]["hanh_dong"] == "Chờ xử lý thủ công đề xuất sửa đơn"
                assert by_kind["ai.de_xuat.xu_ly_thu_cong"]["hanh_dong"] == "Xác nhận đã xử lý thủ công đề xuất sửa đơn"
                assert "đã xử lý thủ công" in by_kind["ai.de_xuat.xu_ly_thu_cong"]["ket_qua"]

                # API `/api/nhat-ky/de-xuat` giữ đúng 14 khóa ổn định và lọc chính xác
                r_dx_all = await client.get(f"/api/nhat-ky/de-xuat?hoi_thoai_id={cid}")
                assert r_dx_all.status_code == 200
                dx_items = r_dx_all.json()["items"]
                assert all(
                    set(i) == {
                        "id", "nguon", "loai", "hoi_thoai_id", "luot_id", "de_xuat_boi",
                        "tom_tat", "luc_de_xuat", "trang_thai", "nguoi_quyet",
                        "luc_quyet", "nguoi_sua", "luc_sua", "muc_uy_quyen",
                    }
                    for i in dx_items
                )
                by_dx_id = {i["id"]: i for i in dx_items}
                assert by_dx_id[str(did)]["trang_thai"] == {
                    "ma": "da_xu_ly_thu_cong",
                    "nhan": "Đã xử lý thủ công",
                }
                assert by_dx_id[str(auto_did)]["trang_thai"] == {
                    "ma": "da_thuc_hien",
                    "nhan": "Đã thực hiện",
                }
                assert (
                    await client.get(f"/api/nhat-ky/de-xuat?hoi_thoai_id={cid}&trang_thai=da_xu_ly_thu_cong")
                ).json()["items"][0]["id"] == str(did)
                assert [
                    i["id"]
                    for i in (
                        await client.get(f"/api/nhat-ky/de-xuat?hoi_thoai_id={cid}&trang_thai=da_thuc_hien")
                    ).json()["items"]
                ] == [str(auto_did)]

                # Export CSV chứa nhãn tiếng Việt mới
                r_csv = await client.get("/api/nhat-ky/xuat.csv")
                assert r_csv.status_code == 200
                assert "Xác nhận đã xử lý thủ công đề xuất sửa đơn" in r_csv.text

                # 12. Kiểm tra render JS `28-uy-quyen-ai.js` & `27-nhat-ky.js` bằng Node.js
                js_28 = ROOT / "dashboard" / "src" / "28-uy-quyen-ai.js"
                js_27 = ROOT / "dashboard" / "src" / "27-nhat-ky.js"
                card_done = cards[str(did)]
                card_waiting = {
                    **card_done,
                    "trang_thai": "cho_xu_ly_thu_cong",
                    "nhan_trang_thai": "Chờ xử lý thủ công — chưa sửa đơn",
                    "duoc_hoan_tat_thu_cong": True,
                    "loi": "CHƯA sửa đơn.",
                    "ket_qua": {"can_xu_ly_thu_cong": True, "da_sua": False},
                }
                node_out = subprocess.check_output(
                    [
                        "node",
                        "-e",
                        """
                        const fs = require('fs');
                        const s28 = fs.readFileSync(process.argv[1], 'utf8');
                        const s27 = fs.readFileSync(process.argv[2], 'utf8');
                        const f28 = new Function('state','esc','gioTin','api','toast','hoiHop','$','$$','window','document',
                          s28 + '; return { veTheDeXuat };');
                        const m28 = f28({ toiQuyen: new Set(['ai.duyet','don.sua']) }, s => String(s ?? ''), () => '20:50',
                          async () => ({}), () => {}, async () => null, () => null, () => [], { GAN_TAB: {} }, { addEventListener() {} });
                        const f27 = new Function('state','esc','gioTin','clock','dongCT','api','toast','hoiHop','window','document','GAN_TAB',
                          s27 + '; return { nkDongDeXuat };');
                        const m27 = f27({ toiQuyen: new Set(['nhat_ky.doc']) }, s => String(s ?? ''), () => '20:50', () => '20:50',
                          () => '', async () => ({}), () => {}, async () => null, {}, { addEventListener() {} }, {});
                        const waitingHtml = m28.veTheDeXuat(JSON.parse(process.argv[3]));
                        const doneHtml = m28.veTheDeXuat(JSON.parse(process.argv[4]));
                        const nkManual = m27.nkDongDeXuat(JSON.parse(process.argv[5]));
                        const nkPending = m27.nkDongDeXuat(JSON.parse(process.argv[6]));
                        console.log(JSON.stringify({ waitingHtml, doneHtml, nkManual, nkPending }));
                        """,
                        str(js_28),
                        str(js_27),
                        json.dumps(card_waiting, ensure_ascii=False),
                        json.dumps(card_done, ensure_ascii=False),
                        json.dumps(by_dx_id[str(did)], ensure_ascii=False),
                        json.dumps({**by_dx_id[str(did)], "trang_thai": {"ma": "cho_xu_ly_thu_cong", "nhan": nk.TRANG_THAI_DE_XUAT["cho_xu_ly_thu_cong"]}}, ensure_ascii=False),
                    ],
                    text=True,
                )
                ui = json.loads(node_out)
                assert "data-dx-thu-cong=" in ui["waitingHtml"]
                assert "Xác nhận đã xử lý thủ công" in ui["waitingHtml"]
                assert "Đã xử lý thủ công bởi nv_kho" in ui["doneHtml"]
                assert "xử lý thủ công bởi" in ui["nkManual"]
                assert "row__flag--assist" in ui["nkPending"]
        finally:
            if pool:
                await pool.close()
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()

    asyncio.run(run())


def test_dot5c_nhan_nhat_ky_va_su_kien_khong_lien_quan_khong_doi():
    """Đảm bảo đồng bộ nhãn mới không làm sai lệch nhãn sự kiện kiểm toán sẵn có."""
    assert nk.TRANG_THAI_DE_XUAT["dang_thuc_thi"] == "Đang kiểm tra và xử lý yêu cầu"
    assert nk.TRANG_THAI_DE_XUAT["cho_xu_ly_thu_cong"] == "Chờ xử lý thủ công — chưa sửa đơn"
    assert nk.TRANG_THAI_DE_XUAT["da_xu_ly_thu_cong"] == "Đã xử lý thủ công"
    assert nk.NHAN_HANH_DONG["ai.de_xuat.cho_xu_ly_thu_cong"]
    assert nk.NHAN_HANH_DONG["ai.de_xuat.xu_ly_thu_cong"]
    # Sự kiện cũ không bị sửa đổi
    assert nk.NHAN_HANH_DONG["ai.tu_gui"] == "AI tự gửi trả lời"
    assert nk.NHAN_HANH_DONG["order.created"] == "Lên đơn"


def test_dot5c_kiem_tra_bang_chung_thu_cong_don_noi_bo_chat_che(monkeypatch):
    """Không cho đóng đề xuất chỉ vì đổi updated_at/trạng thái/sai sản phẩm/sai số lượng."""
    oid, cid = uuid4(), uuid4()
    truoc = {
        "order_id": str(oid),
        "ma_don": "DH-NB",
        "trang_thai": "da_chot",
        "items": [
            {"ma": "SP1", "ten": "Serum", "so_luong": 1},
            {"ma": "SP2", "ten": "Kem", "so_luong": 1},
        ],
        "updated_at": "2026-11-25 10:00:00+00",
        "erp": None,
    }
    dx = {
        "order_id": oid,
        "conversation_id": cid,
        "tham_so": {"ma_don": "DH-NB", "ma_san_pham": "SP1", "so_luong": 2},
        "de_xuat": {"truoc": truoc},
    }
    mock_don = {
        "id": oid,
        "ma_don": "DH-NB",
        "trang_thai": "da_chot",
        "items": list(truoc["items"]),
        "updated_at": "2026-11-25 10:05:00+00",  # Đổi updated_at nhưng chưa đổi SL
        "erp_ma_don": None,
        "ma_van_don": None,
        "trang_thai_giao_hang": None,
        "yeu_cau_huy_luc": None,
    }

    async def fake_fetchrow(sql, *args):
        return dict(mock_don)

    monkeypatch.setattr(thao_tac_don.db, "fetchrow", fake_fetchrow)

    # 1. Chỉ đổi updated_at -> từ chối 409
    with pytest.raises(thao_tac_don.LoiThaoTacDon) as e1:
        asyncio.run(thao_tac_don.kiem_tra_bang_chung_thu_cong(dx))
    assert e1.value.ma == 409

    # 2. Chỉ đổi trang_thai & ma_van_don -> từ chối 409
    mock_don["trang_thai"] = "cho_dong_bo"
    mock_don["ma_van_don"] = "GHN-99"
    with pytest.raises(thao_tac_don.LoiThaoTacDon) as e2:
        asyncio.run(thao_tac_don.kiem_tra_bang_chung_thu_cong(dx))
    assert e2.value.ma == 409

    # 3. Đổi sai sản phẩm (SP2 -> 2, SP1 vẫn 1) -> từ chối 409
    mock_don["trang_thai"] = "da_chot"
    mock_don["items"] = [{"ma": "SP1", "ten": "Serum", "so_luong": 1}, {"ma": "SP2", "ten": "Kem", "so_luong": 2}]
    with pytest.raises(thao_tac_don.LoiThaoTacDon) as e3:
        asyncio.run(thao_tac_don.kiem_tra_bang_chung_thu_cong(dx))
    assert e3.value.ma == 409

    # 4. Đổi sai số lượng (SP1 -> 4 thay vì 2) -> từ chối 409
    mock_don["items"] = [{"ma": "SP1", "ten": "Serum", "so_luong": 4}, {"ma": "SP2", "ten": "Kem", "so_luong": 1}]
    with pytest.raises(thao_tac_don.LoiThaoTacDon) as e4:
        asyncio.run(thao_tac_don.kiem_tra_bang_chung_thu_cong(dx))
    assert e4.value.ma == 409

    # 5. Đổi đúng SP1 -> 2 -> trả về bằng chứng hợp lệ
    mock_don["items"] = [{"ma": "SP1", "ten": "Serum", "so_luong": 2}, {"ma": "SP2", "ten": "Kem", "so_luong": 1}]
    bc = asyncio.run(thao_tac_don.kiem_tra_bang_chung_thu_cong(dx))
    assert bc["da_khop_so_luong_yeu_cau"] is True
    assert bc["so_luong_truoc"] == 1 and bc["so_luong_yeu_cau"] == 2 and bc["so_luong_thuc_te"] == 2
