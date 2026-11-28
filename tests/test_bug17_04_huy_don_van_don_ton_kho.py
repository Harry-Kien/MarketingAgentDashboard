"""
Regression tests cho BUG-17-04: tính nhất quán giữa trạng thái đơn hàng,
vận đơn, tồn kho, công việc kiểm tra hàng hoàn và đồng bộ ERPNext.

Bao phủ toàn bộ ma trận nghiệp vụ:
  1. Chưa tạo vận đơn (không treo đối soát) -> huỷ được, hoàn tồn 1 lần, nhắc + tạo việc huỷ ERPNext.
  2. Đang treo đối soát tạo vận đơn (sending / unknown_timeout / reconciling / manual_required) -> chặn 409.
  3. Chờ lấy hàng (ready_to_pick) -> chặn 409; không cộng kho.
  4. Đang giao (delivering) -> chặn 409; không cộng kho.
  5. Giao thất bại (delivery_failed) -> chặn 409; không cộng kho.
  6. Đang hoàn hàng (returning) -> chặn 409; không cộng kho.
  7. Đã hoàn hàng (returned): webhook KHÔNG tự cộng tồn kho, tạo đúng 1 việc kiểm tra hàng hoàn;
     chống lặp webhook; nhập kho thủ công qua kho.nhap_hang() hoạt động đúng.
  8. Đã giao thành công (delivered / da_giao) -> chặn 409.
  9. Đã huỷ vận đơn (cancelled):
     - Đơn mới (van_don_da_lay_hang=False) -> hoàn tồn 1 lần, chống lặp.
     - Đơn cũ (van_don_da_lay_hang IS NULL) -> an toàn, KHÔNG tự hoàn tồn, tạo việc kiểm kho.
     - Đơn đã qua bước lấy hàng (van_don_da_lay_hang=True) -> KHÔNG tự hoàn tồn, tạo việc kiểm kho.
 10. Tranh chấp đồng thời: huy_don() vs tao_van_don_cho_don(), và webhook lặp đồng thời.
 11. Đồng bộ ERPNext khi Sales Order đã huỷ (docstatus=2) -> skipped_cancelled, không dead, không tạo việc giả.
 12. GAP-17-03 giữ ngoài phạm vi: không có API huỷ vận đơn GHN/GHTK trên FastAPI.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import httpx
import pytest

from agent import db
from agent.core import kho, thao_tac_don
from agent.erp import dong_bo_van_don
from agent.erp.erpnext import NguonErpNext
from agent.erp.hop_dong import DonERPDaHuy
from agent.shipping import service
from agent.shipping.base import anh_xa_trang_thai
from agent.shipping.ghtk import GHTKShippingProvider
from agent.shipping.models import (
    CreateWaybillRequest,
    CreateWaybillResult,
    InternalShippingStatus,
    TRANG_THAI_DA_LAY_HANG,
)


def _chay(coro):
    return asyncio.run(coro)


async def _mo_pool(dsn: str):
    async def codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog",
        )

    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=6, init=codec)
    db._pool = pool
    return pool


async def _tao_don_thu(
    *,
    sku: str = "SKU-BUG1704",
    ton_ban_dau: int = 20,
    so_luong: int = 2,
    trang_thai: str = "da_chot",
    erp_ma_don: str | None = None,
    ma_van_don: str | None = None,
    don_vi_van_chuyen: str | None = None,
    trang_thai_giao_hang: str | None = None,
    van_don_da_lay_hang: bool | None = None,
    req_trang_thai: str | None = None,
) -> tuple[uuid.UUID, str]:
    await db.execute(
        "INSERT INTO ton_kho (ma, so_luong) VALUES ($1, $2) "
        "ON CONFLICT (ma) DO UPDATE SET so_luong = $2",
        sku,
        ton_ban_dau,
    )
    oid = uuid.uuid4()
    ma_don = f"B1704-{oid.hex[:8].upper()}"
    items = [{
        "ma": sku,
        "ten": "Serum Test BUG-17-04",
        "don_gia": 150000,
        "so_luong": so_luong,
        "thanh_tien": 150000 * so_luong,
    }]
    await db.execute(
        """
        INSERT INTO orders (
            id, ma_don, channel, khach_ten, khach_sdt, khach_dia_chi,
            items, tong_tien, trang_thai, erp_ma_don, ma_van_don,
            don_vi_van_chuyen, trang_thai_giao_hang, van_don_da_lay_hang,
            erp_van_chuyen_trang_thai
        )
        VALUES ($1,$2,'webchat','Khách BUG1704','0909123456',
                '12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh',
                $3::jsonb,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        oid,
        ma_don,
        items,
        150000 * so_luong,
        trang_thai,
        erp_ma_don,
        ma_van_don,
        don_vi_van_chuyen,
        trang_thai_giao_hang,
        van_don_da_lay_hang,
        "pending" if (erp_ma_don and ma_van_don) else "not_required",
    )
    # Giữ hàng (trừ kho thật)
    ok_kho, ly_do = await kho.giu_hang(items, ma_don)
    assert ok_kho, ly_do
    if req_trang_thai is not None:
        await db.execute(
            """
            INSERT INTO shipping_waybill_requests (
                order_id, ma_don, provider, client_order_code, trang_thai, ma_van_don
            )
            VALUES ($1, $2, 'ghn', $2, $3, $4)
            """,
            oid,
            ma_don,
            req_trang_thai,
            ma_van_don,
        )
    return oid, ma_don


async def _dem_viec(khoa: str) -> int:
    r = await db.fetchrow(
        "SELECT COUNT(*) AS n FROM cong_viec WHERE khoa_chong_trung = $1", khoa,
    )
    return int(r["n"]) if r else 0


async def _don_dep_don(oid: uuid.UUID, ma_don: str, sku: str = "SKU-BUG1704"):
    await db.execute("DELETE FROM cong_viec WHERE tieu_de LIKE $1 OR khoa_chong_trung LIKE $1", f"%{ma_don}%")
    await db.execute("DELETE FROM shipping_waybill_requests WHERE order_id = $1", oid)
    await db.execute("DELETE FROM kho_bien_dong WHERE ma_don = $1 OR ma = $2", ma_don, sku)
    await db.execute("DELETE FROM orders WHERE id = $1", oid)
    await db.execute("DELETE FROM ton_kho WHERE ma = $1", sku)


# ------------------------------------------------------------------ 1. Unit: phân tách 7 trạng thái & ERPNext cancelled

def test_phan_tach_bay_trang_thai_van_chuyen_ghn_va_ghtk():
    assert anh_xa_trang_thai("ready_to_pick")[0] == InternalShippingStatus.READY_TO_PICK
    assert anh_xa_trang_thai("picking")[0] == InternalShippingStatus.READY_TO_PICK
    assert anh_xa_trang_thai("picked")[0] == InternalShippingStatus.DELIVERING
    assert anh_xa_trang_thai("delivering")[0] == InternalShippingStatus.DELIVERING
    assert anh_xa_trang_thai("delivery_fail")[0] == InternalShippingStatus.DELIVERY_FAILED
    assert anh_xa_trang_thai("waiting_to_return")[0] == InternalShippingStatus.RETURNING
    assert anh_xa_trang_thai("return_transporting")[0] == InternalShippingStatus.RETURNING
    assert anh_xa_trang_thai("returned")[0] == InternalShippingStatus.RETURNED
    assert anh_xa_trang_thai("cancel")[0] == InternalShippingStatus.CANCELLED
    assert anh_xa_trang_thai("delivered")[0] == InternalShippingStatus.DELIVERED

    ghtk = GHTKShippingProvider()
    assert ghtk.map_status("1") == InternalShippingStatus.READY_TO_PICK
    assert ghtk.map_status("2") == InternalShippingStatus.READY_TO_PICK
    assert ghtk.map_status("12") == InternalShippingStatus.READY_TO_PICK
    assert ghtk.map_status("3") == InternalShippingStatus.DELIVERING
    assert ghtk.map_status("20") == InternalShippingStatus.RETURNING
    assert ghtk.map_status("26") == InternalShippingStatus.RETURNING
    assert ghtk.map_status("21") == InternalShippingStatus.RETURNED
    assert ghtk.map_status("-1") == InternalShippingStatus.CANCELLED
    assert ghtk.map_status("5") == InternalShippingStatus.DELIVERED

    # Chỉ trạng thái đã lấy hàng mới nằm trong TRANG_THAI_DA_LAY_HANG
    assert InternalShippingStatus.READY_TO_PICK not in TRANG_THAI_DA_LAY_HANG
    assert InternalShippingStatus.CANCELLED not in TRANG_THAI_DA_LAY_HANG
    assert InternalShippingStatus.DELIVERING in TRANG_THAI_DA_LAY_HANG
    assert InternalShippingStatus.RETURNING in TRANG_THAI_DA_LAY_HANG
    assert InternalShippingStatus.RETURNED in TRANG_THAI_DA_LAY_HANG


def test_erpnext_dong_bo_van_don_bo_qua_khi_sales_order_da_huy():
    reqs: list[httpx.Request] = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        reqs.append(req)
        return httpx.Response(200, json={"data": {
            "name": "SAL-CANCELLED-1",
            "docstatus": 2,
            "status": "Cancelled",
        }})

    client = httpx.AsyncClient(transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu")
    nguon = NguonErpNext(
        goc="https://erp.thu", api_key="k", api_secret="s",
        ma_kho="KHO-HN", pricelist="Bán lẻ", client=client,
    )
    with pytest.raises(DonERPDaHuy):
        _chay(nguon.dong_bo_van_don(
            erp_ma_don="SAL-CANCELLED-1",
            ma_van_don="GHN999",
            don_vi="ghn",
            trang_thai="cancelled",
            dong_bo_luc=datetime.now(timezone.utc),
            tham_chieu="B1704-ERP",
        ))
    # Chỉ GET để kiểm tra docstatus=2, tuyệt đối KHÔNG PUT
    assert [r.method for r in reqs] == ["GET"]


def test_gap_17_03_khong_mo_api_huy_van_don_hang():
    from agent.main import app

    paths = [getattr(r, "path", "") for r in app.routes]
    assert not any("van-don" in p and ("huy" in p or "cancel" in p) for p in paths)


# ------------------------------------------------------------------ 2. Postgres: ma trận huỷ đơn, webhook, hoàn tồn, đồng thời, ERPNext

def test_ma_tran_huy_don_va_chan_hoan_ton_som(csdl_kiem_thu):
    from scripts.dung_csdl_kiem_thu import dung

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        created: list[tuple[uuid.UUID, str, str]] = []
        try:
            # 1a. Chưa tạo vận đơn + có ERP -> huỷ OK, hoàn tồn 1 lần, sinh đúng 1 việc huỷ ERP
            sku1 = "SKU-B1704-1A"
            oid1, ma1 = await _tao_don_thu(sku=sku1, ton_ban_dau=20, so_luong=2, erp_ma_don="SAL-B1704-1")
            created.append((oid1, ma1, sku1))
            assert await kho.lay(sku1) == 18

            kq1 = await thao_tac_don.huy_don(oid1, actor="staff")
            assert kq1["ok"] is True and kq1["da_tra_kho"] == 1
            assert "SAL-B1704-1" in kq1["can_huy_tay"]
            assert await kho.lay(sku1) == 20
            # Huỷ lặp lần 2 -> idempotent, không hoàn kho lần 2, không tạo việc thứ 2
            kq1_dup = await thao_tac_don.huy_don(oid1, actor="staff")
            assert kq1_dup.get("da_huy_tu_truoc") is True
            assert await kho.lay(sku1) == 20
            cnt_erp_task = await _dem_viec(f"don_hang:erp_huy_tay:{ma1}")
            assert cnt_erp_task == 1

            # 1b. Đang treo đối soát tạo vận đơn -> CHẶN 409 cho cả 4 trạng thái treo
            for idx, st_yc in enumerate(("sending", "unknown_timeout", "reconciling", "manual_required")):
                sku_yc = f"SKU-B1704-YC{idx}"
                oid_yc, ma_yc = await _tao_don_thu(sku=sku_yc, ton_ban_dau=10, so_luong=1, req_trang_thai=st_yc)
                created.append((oid_yc, ma_yc, sku_yc))
                with pytest.raises(thao_tac_don.LoiThaoTacDon) as exc_info:
                    await thao_tac_don.huy_don(oid_yc, actor="staff")
                assert exc_info.value.ma == 409
                assert await kho.lay(sku_yc) == 9  # không hoàn tồn

            # 2..5 + 7 + đơn cũ không rõ trạng thái -> đều CHẶN 409, tồn kho giữ nguyên
            blocked_cases = [
                ("ready_to_pick", False),
                ("delivering", True),
                ("delivery_failed", True),
                ("returning", True),
                ("delivered", True),
                (None, None),  # đơn cũ có mã vận đơn nhưng không rõ trạng thái
            ]
            for idx, (st_giao, da_lay) in enumerate(blocked_cases):
                sku_b = f"SKU-B1704-BLK{idx}"
                oid_b, ma_b = await _tao_don_thu(
                    sku=sku_b,
                    ton_ban_dau=15,
                    so_luong=3,
                    ma_van_don=f"GHN-BLK-{idx}",
                    don_vi_van_chuyen="ghn",
                    trang_thai_giao_hang=st_giao,
                    van_don_da_lay_hang=da_lay,
                )
                created.append((oid_b, ma_b, sku_b))
                with pytest.raises(thao_tac_don.LoiThaoTacDon) as exc_info:
                    await thao_tac_don.huy_don(oid_b, actor="staff")
                assert exc_info.value.ma == 409
                assert await kho.lay(sku_b) == 12  # không hoàn tồn
        finally:
            for oid, ma, sku in created:
                await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_webhook_returned_khong_tu_hoan_ton_va_sinh_viec_kiem_hang_hoan(csdl_kiem_thu, monkeypatch):
    from agent.config import settings
    from scripts.dung_csdl_kiem_thu import dung

    monkeypatch.setattr(settings, "shipping_webhook_secret", "b1704_secret")

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        sku = "SKU-B1704-RET"
        oid, ma = await _tao_don_thu(
            sku=sku,
            ton_ban_dau=10,
            so_luong=2,
            erp_ma_don="SAL-RET-1",
            ma_van_don="GHN-RET-001",
            don_vi_van_chuyen="ghn",
            trang_thai_giao_hang="returning",
            van_don_da_lay_hang=True,
        )
        try:
            assert await kho.lay(sku) == 8
            t1 = datetime.now(timezone.utc) + timedelta(minutes=1)
            wh1 = await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {
                    "OrderCode": "GHN-RET-001",
                    "ClientOrderCode": ma,
                    "Status": "returned",
                    "Description": "Đã trả hàng về shop",
                    "Time": t1.isoformat(),
                },
                {},
                query_token="b1704_secret",
            )
            assert wh1["ok"] is True and not wh1.get("ignored")
            # Đơn chuyển da_huy + trang_thai_giao_hang=returned nhưng TỒN KHO KHÔNG TỰ CỘNG!
            row = await db.fetchrow("SELECT trang_thai, trang_thai_giao_hang FROM orders WHERE id=$1", oid)
            assert row["trang_thai"] == "da_huy"
            assert row["trang_thai_giao_hang"] == "returned"
            assert await kho.lay(sku) == 8
            hoan_rows = await db.fetch(
                "SELECT * FROM kho_bien_dong WHERE ma_don = $1 AND ly_do IN ('hoan_hang', 'huy_don')",
                ma,
            )
            assert len(hoan_rows) == 0

            # Đã sinh đúng 1 công việc kiểm tra hàng hoàn
            tasks = await db.fetch(
                "SELECT tieu_de, mo_ta, trang_thai FROM cong_viec WHERE khoa_chong_trung = $1",
                f"don_hang:kiem_hang_hoan:{ma}",
            )
            assert len(tasks) == 1
            assert "Kiểm tra hàng hoàn" in tasks[0]["tieu_de"]
            assert "SAL-RET-1" in tasks[0]["mo_ta"]

            # Gửi lặp webhook returned -> ignored, vẫn chỉ 1 công việc, tồn kho vẫn 8
            wh_dup = await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {
                    "OrderCode": "GHN-RET-001",
                    "ClientOrderCode": ma,
                    "Status": "returned",
                    "Description": "Đã trả hàng về shop",
                    "Time": (t1 + timedelta(seconds=5)).isoformat(),
                },
                {},
                query_token="b1704_secret",
            )
            assert wh_dup.get("ignored") is True
            assert await kho.lay(sku) == 8
            assert await _dem_viec(f"don_hang:kiem_hang_hoan:{ma}") == 1

            # Nhân viên kiểm tra hàng hoàn thực tế (ví dụ 1/2 hộp còn nguyên seal) rồi nhập kho thủ công
            nhap = await kho.nhap_hang(sku, 1, ghi_chu=f"Nhập hàng hoàn nguyên seal đơn {ma}")
            assert nhap["ton_moi"] == 9
            assert await kho.lay(sku) == 9
        finally:
            await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_webhook_cancelled_don_moi_vs_don_cu_vs_da_lay_hang(csdl_kiem_thu, monkeypatch):
    from agent.config import settings
    from scripts.dung_csdl_kiem_thu import dung

    monkeypatch.setattr(settings, "shipping_webhook_secret", "b1704_secret")

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        created: list[tuple[uuid.UUID, str, str]] = []
        try:
            now = datetime.now(timezone.utc)

            # A. Đơn mới chưa lấy hàng (van_don_da_lay_hang=False) + có ERP -> webhook cancel tự hoàn tồn đúng 1 lần + tạo việc huỷ ERP
            sku_a = "SKU-B1704-CANA"
            oid_a, ma_a = await _tao_don_thu(
                sku=sku_a, ton_ban_dau=10, so_luong=2, erp_ma_don="SAL-CANA-1",
                ma_van_don="GHN-CANA", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="ready_to_pick", van_don_da_lay_hang=False,
            )
            created.append((oid_a, ma_a, sku_a))
            assert await kho.lay(sku_a) == 8
            # Gửi đồng thời 2 webhook cancel giống nhau -> chỉ 1 webhook thắng, hoàn tồn đúng 1 lần
            r_a1, r_a2 = await asyncio.gather(
                service.xu_ly_webhook_van_chuyen(
                    "ghn",
                    {"OrderCode": "GHN-CANA", "ClientOrderCode": ma_a, "Status": "cancel", "Time": (now + timedelta(minutes=1)).isoformat()},
                    {},
                    query_token="b1704_secret",
                ),
                service.xu_ly_webhook_van_chuyen(
                    "ghn",
                    {"OrderCode": "GHN-CANA", "ClientOrderCode": ma_a, "Status": "cancel", "Time": (now + timedelta(minutes=1)).isoformat()},
                    {},
                    query_token="b1704_secret",
                ),
            )
            assert r_a1["ok"] is True and r_a2["ok"] is True
            assert await kho.lay(sku_a) == 10  # hoàn tồn 1 lần an toàn
            assert (await db.fetchrow("SELECT trang_thai FROM orders WHERE id=$1", oid_a))["trang_thai"] == "da_huy"
            # Gọi lặp webhook + gọi thêm huy_don -> không hoàn tồn lần 2, không tạo việc ERP lần 2
            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CANA", "ClientOrderCode": ma_a, "Status": "cancel", "Time": (now + timedelta(minutes=2)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            await thao_tac_don.huy_don(oid_a, actor="staff")
            assert await kho.lay(sku_a) == 10
            assert await _dem_viec(f"don_hang:erp_huy_tay:{ma_a}") == 1

            # B. Đơn cũ (van_don_da_lay_hang IS NULL) -> webhook cancel KHÔNG tự hoàn tồn, tạo việc kiểm kho
            sku_b = "SKU-B1704-CANB"
            oid_b, ma_b = await _tao_don_thu(
                sku=sku_b, ton_ban_dau=10, so_luong=2,
                ma_van_don="GHN-CANB", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="delivering", van_don_da_lay_hang=None,
            )
            created.append((oid_b, ma_b, sku_b))
            assert await kho.lay(sku_b) == 8
            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CANB", "ClientOrderCode": ma_b, "Status": "cancel", "Time": (now + timedelta(minutes=1)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            assert await kho.lay(sku_b) == 8  # KHÔNG cộng kho cho đơn cũ
            assert await _dem_viec(f"don_hang:kiem_kho_huy_vd:{ma_b}") == 1

            # C. Đơn mới đã chuyển sang delivering (van_don_da_lay_hang tự bật True) rồi nhận cancel -> KHÔNG tự hoàn tồn
            sku_c = "SKU-B1704-CANC"
            oid_c, ma_c = await _tao_don_thu(
                sku=sku_c, ton_ban_dau=10, so_luong=2,
                ma_van_don="GHN-CANC", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="ready_to_pick", van_don_da_lay_hang=False,
            )
            created.append((oid_c, ma_c, sku_c))
            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CANC", "ClientOrderCode": ma_c, "Status": "picked", "Time": (now + timedelta(minutes=1)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            row_c = await db.fetchrow("SELECT trang_thai_giao_hang, van_don_da_lay_hang FROM orders WHERE id=$1", oid_c)
            assert row_c["trang_thai_giao_hang"] == "delivering" and row_c["van_don_da_lay_hang"] is True

            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CANC", "ClientOrderCode": ma_c, "Status": "cancel", "Time": (now + timedelta(minutes=2)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            assert await kho.lay(sku_c) == 8  # Đã lấy hàng -> tuyệt đối không tự cộng kho
            assert await _dem_viec(f"don_hang:kiem_kho_huy_vd:{ma_c}") == 1
        finally:
            for oid, ma, sku in created:
                await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_dong_thoi_huy_don_va_tao_van_don_khong_gay_lech_trang_thai(csdl_kiem_thu, monkeypatch):
    from scripts.dung_csdl_kiem_thu import dung

    class SlowStubProvider:
        code = "ghn"
        name = "GHN Slow Stub"
        calls = 0

        async def tao_van_don(self, req: CreateWaybillRequest) -> CreateWaybillResult:
            self.calls += 1
            await asyncio.sleep(0.15)
            return CreateWaybillResult(
                ok=True,
                ma_van_don=f"GHN-RACE-{self.calls}",
                don_vi="ghn",
                phi_van_chuyen=30000,
                trang_thai_noi_bo=InternalShippingStatus.READY_TO_PICK,
                client_order_code=req.client_order_code,
            )

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        sku = "SKU-B1704-RACE"
        oid, ma = await _tao_don_thu(sku=sku, ton_ban_dau=10, so_luong=2)
        stub = SlowStubProvider()
        monkeypatch.setattr(service, "get_provider", lambda name=None: stub)
        try:
            async def run_cancel():
                try:
                    return ("cancel_ok", await thao_tac_don.huy_don(oid, actor="staff"))
                except thao_tac_don.LoiThaoTacDon as exc:
                    return ("cancel_blocked", exc.ma)

            async def run_create():
                return ("create", await service.tao_van_don_cho_don(ma, "ghn"))

            r_a, r_b = await asyncio.gather(run_create(), run_cancel())
            row = await db.fetchrow(
                "SELECT trang_thai, ma_van_don, trang_thai_giao_hang, van_don_da_lay_hang FROM orders WHERE id=$1",
                oid,
            )
            ton = await kho.lay(sku)

            # Bất biến: KHÔNG BAO GIỜ vừa có mã vận đơn vừa ở trạng thái da_huy/hoàn kho!
            if row["trang_thai"] == "da_huy":
                assert not row["ma_van_don"]
                assert stub.calls == 0
                assert ton == 10
                assert r_a[1].ok is False
            else:
                assert row["trang_thai"] == "da_chot"
                assert row["ma_van_don"] == "GHN-RACE-1"
                assert row["trang_thai_giao_hang"] == "ready_to_pick"
                assert row["van_don_da_lay_hang"] is False
                assert ton == 8  # không bị hoàn kho
                assert r_b == ("cancel_blocked", 409)
        finally:
            await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_erp_sync_skipped_cancelled_khong_tao_viec_dead(csdl_kiem_thu):
    from scripts.dung_csdl_kiem_thu import dung

    class CancelledErpAdapter:
        async def dong_bo_van_don(self, **kwargs):
            raise DonERPDaHuy("Sales Order SAL-CANC-9 đã bị huỷ (docstatus=2)")

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        sku = "SKU-B1704-ERPC"
        oid, ma = await _tao_don_thu(
            sku=sku,
            ton_ban_dau=10,
            so_luong=1,
            erp_ma_don="SAL-CANC-9",
            ma_van_don="GHN-ERPC-1",
            don_vi_van_chuyen="ghn",
            trang_thai_giao_hang="cancelled",
            van_don_da_lay_hang=False,
        )
        try:
            kq = await dong_bo_van_don.dong_bo_ngay(ma, nguon=CancelledErpAdapter())
            assert kq["ok"] is True
            assert kq["trang_thai"] == "skipped_cancelled"
            row = await db.fetchrow(
                "SELECT erp_van_chuyen_trang_thai, erp_van_chuyen_thu_lai_luc FROM orders WHERE id=$1",
                oid,
            )
            assert row["erp_van_chuyen_trang_thai"] == "skipped_cancelled"
            assert row["erp_van_chuyen_thu_lai_luc"] is None
            # Không tạo công việc dead-letter giả "Ghi tay mã vận đơn..."
            dead_tasks = await _dem_viec(f"erp_van_don:dead:{ma}:GHN-ERPC-1")
            assert dead_tasks == 0
        finally:
            await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


# ------------------------------------------------------------------ 3. Hoàn thiện BUG-17-04: nhập hàng hoàn, liên kết công việc, 3 điểm lệch

def test_nhap_hang_hoan_mot_phan_vuot_so_luong_trung_va_dong_thoi(csdl_kiem_thu):
    from scripts.dung_csdl_kiem_thu import dung

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        created: list[tuple[uuid.UUID, str, str]] = []
        try:
            # A. Đơn không đủ điều kiện nhập hoàn -> CHẶN 409
            sku_bad = "SKU-B1704-ELIG"
            oid_bad, ma_bad = await _tao_don_thu(
                sku=sku_bad, ton_ban_dau=10, so_luong=2,
                ma_van_don="GHN-ELIG-1", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="delivering", van_don_da_lay_hang=True,
            )
            created.append((oid_bad, ma_bad, sku_bad))
            with pytest.raises(kho.LoiNhapHangHoan) as exc_bad:
                await kho.nhap_hang_hoan(sku_bad, 1, ma_bad, "thử nhập đơn đang giao")
            assert exc_bad.value.ma == 409
            assert await kho.lay(sku_bad) == 8

            # B. Hoàn một phần + chống lặp retry (khoa_chong_trung) + vượt số lượng + tổng hợp biến động cũ
            sku_p = "SKU-B1704-PART"
            oid_p, ma_p = await _tao_don_thu(
                sku=sku_p, ton_ban_dau=20, so_luong=3,
                trang_thai="da_huy", ma_van_don="GHN-PART-1",
                don_vi_van_chuyen="ghn", trang_thai_giao_hang="returned",
                van_don_da_lay_hang=True,
            )
            created.append((oid_p, ma_p, sku_p))
            assert await kho.lay(sku_p) == 17

            # Hoàn lần 1: 1/3 hộp nguyên seal
            r1 = await kho.nhap_hang_hoan(
                sku_p, 1, ma_p, "Hộp 1 nguyên seal", khoa_chong_trung="retry-key-part-1",
            )
            assert r1["ly_do"] == "hoan_hang" and r1["ma_don"] == ma_p
            assert (r1["da_ban"], r1["da_hoan"], r1["con_lai"]) == (3, 1, 2)
            assert r1["ton_moi"] == 18 and r1["da_nhap_tu_truoc"] is False

            # Retry cùng khoa_chong_trung -> KHÔNG cộng kho lần 2 dù con_lai vẫn còn 2
            r1_dup = await kho.nhap_hang_hoan(
                sku_p, 1, ma_p, "Hộp 1 nguyên seal", khoa_chong_trung="retry-key-part-1",
            )
            assert r1_dup["da_nhap_tu_truoc"] is True
            assert r1_dup["bien_dong_id"] == r1["bien_dong_id"]
            assert await kho.lay(sku_p) == 18

            # Hoàn lần 2: vượt số còn lại (nhập 3 trong khi còn 2) -> CHẶN 409
            with pytest.raises(kho.LoiNhapHangHoan) as exc_over:
                await kho.nhap_hang_hoan(sku_p, 3, ma_p, "nhập thừa")
            assert exc_over.value.ma == 409
            assert await kho.lay(sku_p) == 18

            # Hoàn lần 2 hợp lệ: 2/2 còn lại -> tổng 3/3
            r2 = await kho.nhap_hang_hoan(sku_p, 2, ma_p, "2 hộp còn lại nguyên seal")
            assert (r2["da_hoan"], r2["con_lai"], r2["ton_moi"]) == (3, 0, 20)

            # Đã hoàn đủ 3/3 -> nhập thêm 1 bị CHẶN 409
            with pytest.raises(kho.LoiNhapHangHoan) as exc_full:
                await kho.nhap_hang_hoan(sku_p, 1, ma_p, "nhập dư sau khi đủ")
            assert exc_full.value.ma == 409
            assert await kho.lay(sku_p) == 20

            # Sản phẩm không thuộc đơn -> CHẶN 409
            await db.execute(
                "INSERT INTO ton_kho (ma, so_luong) VALUES ('SKU-KHAC', 5) ON CONFLICT (ma) DO NOTHING"
            )
            with pytest.raises(kho.LoiNhapHangHoan) as exc_sku:
                await kho.nhap_hang_hoan("SKU-KHAC", 1, ma_p, "sai sản phẩm")
            assert exc_sku.value.ma == 409
            await db.execute("DELETE FROM ton_kho WHERE ma = 'SKU-KHAC'")

            # C. Nhập hoàn ĐỒNG THỜI (2 yêu cầu song song đều đòi nhập 2/2) -> chỉ 1 thành công
            sku_c = "SKU-B1704-CONC"
            oid_c, ma_c = await _tao_don_thu(
                sku=sku_c, ton_ban_dau=10, so_luong=2,
                trang_thai="da_huy", ma_van_don="GHN-CONC-1",
                don_vi_van_chuyen="ghn", trang_thai_giao_hang="returned",
                van_don_da_lay_hang=True,
            )
            created.append((oid_c, ma_c, sku_c))
            assert await kho.lay(sku_c) == 8

            async def _thu_nhap(tag: str):
                try:
                    return ("ok", await kho.nhap_hang_hoan(sku_c, 2, ma_c, f"tab {tag}", khoa_chong_trung=f"k-{tag}"))
                except kho.LoiNhapHangHoan as exc:
                    return ("blocked", exc.ma)

            res_c1, res_c2 = await asyncio.gather(_thu_nhap("1"), _thu_nhap("2"))
            outcomes = sorted([res_c1[0], res_c2[0]])
            assert outcomes == ["blocked", "ok"]
            assert await kho.lay(sku_c) == 10  # chỉ cộng đúng +2 một lần

            # D. Đơn đã giao có yêu cầu đổi/trả -> ĐỦ điều kiện nhập hoàn; đơn đã giao không có đổi trả -> CHẶN 409
            sku_dt = "SKU-B1704-DT"
            oid_dt, ma_dt = await _tao_don_thu(
                sku=sku_dt, ton_ban_dau=10, so_luong=1,
                trang_thai="da_giao", ma_van_don="GHN-DT-1",
                don_vi_van_chuyen="ghn", trang_thai_giao_hang="delivered",
                van_don_da_lay_hang=True,
            )
            created.append((oid_dt, ma_dt, sku_dt))
            with pytest.raises(kho.LoiNhapHangHoan) as exc_nodt:
                await kho.nhap_hang_hoan(sku_dt, 1, ma_dt, "chưa có đổi trả")
            assert exc_nodt.value.ma == 409
            await db.execute(
                "UPDATE orders SET yeu_cau_doi_tra_luc = now(), yeu_cau_doi_tra_loai = 'tra' WHERE id = $1",
                oid_dt,
            )
            r_dt = await kho.nhap_hang_hoan(sku_dt, 1, ma_dt, "Khách gửi trả nguyên seal")
            assert r_dt["ton_moi"] == 10 and r_dt["ly_do"] == "hoan_hang"
        finally:
            for oid, ma, sku in created:
                await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_cong_viec_kiem_hang_hoan_gan_order_id_va_hang_khong_du_dieu_kien_nhap_kho(csdl_kiem_thu, monkeypatch):
    from agent.config import settings
    from scripts.dung_csdl_kiem_thu import dung

    monkeypatch.setattr(settings, "shipping_webhook_secret", "b1704_secret")

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        created: list[tuple[uuid.UUID, str, str]] = []
        try:
            now = datetime.now(timezone.utc)

            # 1. Hàng hoàn đạt điều kiện 1/2 hộp: cong_viec có order_id, ghi tiến độ biến động kho
            sku1 = "SKU-B1704-CV1"
            oid1, ma1 = await _tao_don_thu(
                sku=sku1, ton_ban_dau=10, so_luong=2,
                ma_van_don="GHN-CV1", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="returning", van_don_da_lay_hang=True,
            )
            created.append((oid1, ma1, sku1))
            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CV1", "ClientOrderCode": ma1, "Status": "returned", "Time": (now + timedelta(minutes=1)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            viec1 = await db.fetchrow(
                "SELECT id, order_id, trang_thai FROM cong_viec WHERE khoa_chong_trung = $1",
                f"don_hang:kiem_hang_hoan:{ma1}",
            )
            assert viec1 is not None and viec1["order_id"] == oid1

            r_nhap = await kho.nhap_hang_hoan(sku1, 1, ma1, "1 hộp nguyên seal, 1 hộp vỡ")
            assert r_nhap["cong_viec_id"] == str(viec1["id"])
            ls1 = await db.fetch(
                "SELECT loai, ghi_chu FROM cong_viec_lich_su WHERE cong_viec_id = $1 AND loai = 'tien_do'",
                viec1["id"],
            )
            assert len(ls1) == 1
            assert f"#{r_nhap['bien_dong_id']}" in ls1[0]["ghi_chu"]
            assert "+1" in ls1[0]["ghi_chu"]

            # 2. Hàng hoàn KHÔNG đủ điều kiện nhập lại kho (vỡ toàn bộ): đóng công việc kèm ket_qua mà KHÔNG cộng tồn kho
            sku2 = "SKU-B1704-CV2"
            oid2, ma2 = await _tao_don_thu(
                sku=sku2, ton_ban_dau=10, so_luong=2,
                ma_van_don="GHN-CV2", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="returning", van_don_da_lay_hang=True,
            )
            created.append((oid2, ma2, sku2))
            assert await kho.lay(sku2) == 8
            await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {"OrderCode": "GHN-CV2", "ClientOrderCode": ma2, "Status": "returned", "Time": (now + timedelta(minutes=1)).isoformat()},
                {},
                query_token="b1704_secret",
            )
            viec2 = await db.fetchrow(
                "SELECT id, order_id FROM cong_viec WHERE khoa_chong_trung = $1",
                f"don_hang:kiem_hang_hoan:{ma2}",
            )
            assert viec2 is not None and viec2["order_id"] == oid2

            # Ghi nhận kết quả kiểm hàng không đạt và đánh dấu Xong -> tồn kho giữ nguyên 8
            await db.execute(
                "UPDATE cong_viec SET trang_thai = 'xong', xong_luc = now(), "
                "ket_qua = $2, sua_luc = now() WHERE id = $1",
                viec2["id"],
                "Hàng hoàn bị vỡ/rách seal 2/2 hộp — không đủ điều kiện nhập lại kho, chuyển tiêu huỷ.",
            )
            viec2_done = await db.fetchrow("SELECT trang_thai, ket_qua FROM cong_viec WHERE id = $1", viec2["id"])
            assert viec2_done["trang_thai"] == "xong"
            assert "không đủ điều kiện nhập lại kho" in viec2_done["ket_qua"]
            assert await kho.lay(sku2) == 8
            bd2 = await db.fetch(
                "SELECT * FROM kho_bien_dong WHERE ma_don = $1 AND ly_do = 'hoan_hang'",
                ma2,
            )
            assert len(bd2) == 0
        finally:
            for oid, ma, sku in created:
                await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())


def test_ba_diem_lech_bang_chung_huy_don_skipped_cancelled_va_ui(csdl_kiem_thu):
    from pathlib import Path
    from agent.core import tools
    from scripts.dung_csdl_kiem_thu import dung

    async def scenario():
        await dung(csdl_kiem_thu)
        pool = await _mo_pool(csdl_kiem_thu)
        created: list[tuple[uuid.UUID, str, str]] = []
        try:
            # 3a. bang_chung_huy_don phải thống nhất với huy_don()
            # - Chưa có vận đơn -> huy_duoc=True, sau.tra_kho có món
            sku0 = "SKU-B1704-BC0"
            oid0, ma0 = await _tao_don_thu(sku=sku0, ton_ban_dau=10, so_luong=1)
            created.append((oid0, ma0, sku0))
            bc0 = await tools.bang_chung_huy_don(oid0, "đổi ý")
            assert bc0["huy_duoc"] is True and len(bc0["sau"]["tra_kho"]) == 1

            # - Đang chờ lấy hàng / đang giao / đang hoàn -> huy_duoc=False, sau.tra_kho=[]
            for idx, st in enumerate(("ready_to_pick", "delivering", "returning")):
                sku_x = f"SKU-B1704-BC{idx+1}"
                oid_x, ma_x = await _tao_don_thu(
                    sku=sku_x, ton_ban_dau=10, so_luong=1,
                    ma_van_don=f"GHN-BC-{idx}", don_vi_van_chuyen="ghn",
                    trang_thai_giao_hang=st, van_don_da_lay_hang=(st != "ready_to_pick"),
                )
                created.append((oid_x, ma_x, sku_x))
                bc_x = await tools.bang_chung_huy_don(oid_x, "đổi ý")
                assert bc_x["huy_duoc"] is False
                assert bc_x["sau"]["tra_kho"] == []

            # - Đang đối soát tạo vận đơn -> huy_duoc=False, sau.tra_kho=[]
            sku_yc = "SKU-B1704-BCYC"
            oid_yc, ma_yc = await _tao_don_thu(sku=sku_yc, ton_ban_dau=10, so_luong=1, req_trang_thai="unknown_timeout")
            created.append((oid_yc, ma_yc, sku_yc))
            bc_yc = await tools.bang_chung_huy_don(oid_yc, "đổi ý")
            assert bc_yc["huy_duoc"] is False and bc_yc["sau"]["tra_kho"] == []

            # - Vận đơn đã returned -> huy_duoc=True nhưng sau.tra_kho=[] (KHÔNG dự kiến hoàn kho tự động)
            sku_r = "SKU-B1704-BCR"
            oid_r, ma_r = await _tao_don_thu(
                sku=sku_r, ton_ban_dau=10, so_luong=1,
                ma_van_don="GHN-BCR", don_vi_van_chuyen="ghn",
                trang_thai_giao_hang="returned", van_don_da_lay_hang=True,
            )
            created.append((oid_r, ma_r, sku_r))
            bc_r = await tools.bang_chung_huy_don(oid_r, "hoàn về")
            assert bc_r["huy_duoc"] is True and bc_r["sau"]["tra_kho"] == []

            # 3b. tao_van_don_cho_don trên đơn đã có vận đơn + erp skipped_cancelled:
            # KHÔNG đẩy lại pending và trả ĐÚNG trạng thái giao hàng thực tế (delivery_failed)
            sku_s = "SKU-B1704-SKIP"
            oid_s, ma_s = await _tao_don_thu(
                sku=sku_s, ton_ban_dau=10, so_luong=1,
                erp_ma_don="SAL-SKIP-1", ma_van_don="GHN-SKIP-1",
                don_vi_van_chuyen="ghn", trang_thai_giao_hang="delivery_failed",
                van_don_da_lay_hang=True,
            )
            created.append((oid_s, ma_s, sku_s))
            await db.execute(
                "UPDATE orders SET erp_van_chuyen_trang_thai = 'skipped_cancelled', "
                "erp_van_chuyen_loi = 'Sales Order đã huỷ' WHERE id = $1",
                oid_s,
            )
            res_s = await service.tao_van_don_cho_don(ma_s, "ghn")
            assert res_s.ok is True and res_s.thong_tin_them.get("da_co_san") is True
            assert res_s.trang_thai_noi_bo == InternalShippingStatus.DELIVERY_FAILED
            assert res_s.thong_tin_them["erp_sync"]["trang_thai"] == "skipped_cancelled"
            st_db = await db.fetchrow("SELECT erp_van_chuyen_trang_thai FROM orders WHERE id = $1", oid_s)
            assert st_db["erp_van_chuyen_trang_thai"] == "skipped_cancelled"
        finally:
            for oid, ma, sku in created:
                await _don_dep_don(oid, ma, sku)
            await pool.close()
            db._pool = None

    _chay(scenario())

    # 3c. Kiểm tra UI JS: nhãn hoan_hang & erp_tu_choi, bỏ mặc định value: 50, có chọn loại nhập
    js_src = (Path(__file__).parents[1] / "dashboard/src/05-don-kho.js").read_text(encoding="utf-8")
    js_bundle = (Path(__file__).parents[1] / "dashboard/app.js").read_text(encoding="utf-8")
    for js in (js_src, js_bundle):
        assert 'hoan_hang: "nhập hàng hoàn"' in js
        assert 'erp_tu_choi: "ERP từ chối"' in js
        assert 'value: "hoan_hang"' in js
        assert "value: 50" not in js
