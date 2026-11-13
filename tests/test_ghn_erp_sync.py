"""DEV-02: đồng bộ vận đơn GHN sang ERPNext, retry và chống ghi trùng."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from agent.erp.erpnext import NguonErpNext
from agent.erp.hop_dong import LoiERP, TuChoiERP
from agent.shipping.ghn import GHNShippingProvider
from tests.erp_gia import chay


def _nguon(xu_ly) -> NguonErpNext:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(xu_ly), base_url="https://erp.thu"
    )
    return NguonErpNext(
        goc="https://erp.thu",
        api_key="k",
        api_secret="s",
        ma_kho="KHO-HN",
        pricelist="Bán lẻ",
        client=client,
    )


def test_tc01_ghi_du_ma_van_don_ghn_vao_sales_order():
    reqs: list[httpx.Request] = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        reqs.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"data": {
                "name": "SAL-ORD-1",
                "custom_shipping_tracking_number": "",
                "custom_shipping_carrier": "",
                "custom_shipping_status": "",
                "custom_shipping_synced_at": None,
                "custom_shipping_reference": "",
            }})
        return httpx.Response(200, json={"data": {"name": "SAL-ORD-1"}})

    luc = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)
    da_ghi = chay(_nguon(xu_ly).dong_bo_van_don(
        erp_ma_don="SAL-ORD-1",
        ma_van_don="GHN123",
        don_vi="ghn",
        trang_thai="delivering",
        dong_bo_luc=luc,
        tham_chieu="AS261112001",
    ))

    assert da_ghi is True
    puts = [r for r in reqs if r.method == "PUT"]
    assert len(puts) == 1
    assert puts[0].url.path.endswith("/Sales Order/SAL-ORD-1")
    assert json.loads(puts[0].content) == {
        "custom_shipping_tracking_number": "GHN123",
        "custom_shipping_carrier": "GHN",
        "custom_shipping_status": "delivering",
        "custom_shipping_synced_at": "2026-11-12 03:00:00",
        "custom_shipping_reference": "AS261112001",
    }


def test_tc04_tc06_erp_da_co_du_lieu_thi_khong_put_lai():
    reqs: list[httpx.Request] = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        reqs.append(req)
        return httpx.Response(200, json={"data": {
            "name": "SAL-ORD-1",
            "custom_shipping_tracking_number": "GHN123",
            "custom_shipping_carrier": "GHN",
            "custom_shipping_status": "delivered",
            "custom_shipping_synced_at": "2026-11-12 03:00:00",
            "custom_shipping_reference": "AS261112001",
        }})

    da_ghi = chay(_nguon(xu_ly).dong_bo_van_don(
        erp_ma_don="SAL-ORD-1",
        ma_van_don="GHN123",
        don_vi="ghn",
        trang_thai="delivered",
        dong_bo_luc=datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc),
        tham_chieu="AS261112001",
    ))

    assert da_ghi is False
    assert [r.method for r in reqs] == ["GET"]


def test_tc02_timeout_erp_la_loi_tam_thoi_de_worker_retry():
    def xu_ly(_req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("ERPNext quá hạn")

    with pytest.raises(LoiERP):
        chay(_nguon(xu_ly).dong_bo_van_don(
            erp_ma_don="SAL-ORD-1",
            ma_van_don="GHN123",
            don_vi="ghn",
            trang_thai="delivering",
            dong_bo_luc=datetime.now(timezone.utc),
            tham_chieu="AS261112001",
        ))


def test_tc09_webhook_ghn_giu_dung_thoi_gian_su_kien():
    event = GHNShippingProvider(token="T", shop_id="1").parse_webhook({
        "OrderCode": "GHN123",
        "ClientOrderCode": "AS261112001",
        "Status": "delivering",
        "Time": "2026-11-12T10:15:30+07:00",
    }, {})

    assert event.thoi_gian.isoformat() == "2026-11-12T10:15:30+07:00"


def test_migration_co_hang_doi_retry_rieng_cho_van_don_erp():
    from pathlib import Path

    migration = (
        Path(__file__).parents[1]
        / "agent/migrations/versions/0044_shipping_erp_sync.sql"
    ).read_text(encoding="utf-8")
    for cot in (
        "erp_van_chuyen_trang_thai",
        "erp_van_chuyen_so_lan_thu",
        "erp_van_chuyen_thu_lai_luc",
        "erp_van_chuyen_loi",
        "erp_van_chuyen_dong_bo_luc",
    ):
        assert cot in migration
    assert "pending" in migration
    assert "synced" in migration
    assert "dead" in migration


def test_tc02_tc03_tc05_postgres_retry_va_hai_worker(csdl_kiem_thu):
    import asyncio
    import asyncpg

    from agent import db
    from agent.erp.dong_bo_van_don import dong_bo_ngay
    from scripts.dung_csdl_kiem_thu import dung

    async def scenario():
        await dung(csdl_kiem_thu)
        async def codec(conn):
            await conn.set_type_codec(
                "jsonb", encoder=json.dumps, decoder=json.loads,
                schema="pg_catalog",
            )

        pool = await asyncpg.create_pool(
            csdl_kiem_thu, min_size=1, max_size=4, init=codec
        )
        old = db._pool
        db._pool = pool
        try:
            oid = await pool.fetchval(
                """
                INSERT INTO orders
                    (ma_don, khach_ten, khach_sdt, khach_dia_chi, trang_thai,
                     erp_ma_don, ma_van_don, don_vi_van_chuyen,
                     trang_thai_giao_hang, cap_nhat_van_chuyen_luc,
                     erp_van_chuyen_trang_thai, erp_van_chuyen_thu_lai_luc)
                VALUES
                    ('AS-RETRY', 'A', '0900000000', 'Hà Nội', 'da_chot',
                     'SO-1', 'GHN-KEEP', 'ghn', 'delivering', now(),
                     'pending', now())
                RETURNING id
                """
            )

            class Cham:
                def __init__(self):
                    self.dem = 0

                async def dong_bo_van_don(self, **_kw):
                    self.dem += 1
                    await asyncio.sleep(0.05)
                    if self.dem == 1:
                        raise LoiERP("ERP timeout")
                    return True

            nguon = Cham()
            first = await dong_bo_ngay("AS-RETRY", nguon)
            assert first["trang_thai"] == "retry"
            row = await pool.fetchrow(
                "SELECT ma_van_don, erp_van_chuyen_trang_thai "
                "FROM orders WHERE id=$1", oid,
            )
            assert row["ma_van_don"] == "GHN-KEEP", "timeout ERP không được mất mã GHN"
            await pool.execute(
                "UPDATE orders SET erp_van_chuyen_thu_lai_luc=now() WHERE id=$1",
                oid,
            )

            ket_qua = await asyncio.gather(
                dong_bo_ngay("AS-RETRY", nguon),
                dong_bo_ngay("AS-RETRY", nguon),
            )
            assert any(kq["trang_thai"] == "synced" for kq in ket_qua)
            assert nguon.dem == 2, "hai worker chỉ được gọi ERP một lần cho cùng snapshot"
            assert await pool.fetchval(
                "SELECT erp_van_chuyen_trang_thai FROM orders WHERE id=$1", oid
            ) == "synced"
        finally:
            await pool.close()
            db._pool = old

    asyncio.run(scenario())


def test_tc08_tc09_webhook_trung_va_cu_khong_ghi_de(csdl_kiem_thu, monkeypatch):
    import asyncio
    import asyncpg

    from agent import db
    from agent.config import settings
    from agent.shipping.service import xu_ly_webhook_van_chuyen
    from scripts.dung_csdl_kiem_thu import dung

    monkeypatch.setattr(settings, "shipping_webhook_secret", "secret")

    async def scenario():
        await dung(csdl_kiem_thu)
        async def codec(conn):
            await conn.set_type_codec(
                "jsonb", encoder=json.dumps, decoder=json.loads,
                schema="pg_catalog",
            )

        pool = await asyncpg.create_pool(
            csdl_kiem_thu, min_size=1, max_size=3, init=codec
        )
        old = db._pool
        db._pool = pool
        try:
            await pool.execute(
                """
                INSERT INTO orders
                    (ma_don, khach_ten, khach_sdt, khach_dia_chi, trang_thai,
                     erp_ma_don, ma_van_don, don_vi_van_chuyen,
                     trang_thai_giao_hang, cap_nhat_van_chuyen_luc)
                VALUES
                    ('AS-WEBHOOK', 'A', '0900000000', 'Hà Nội', 'da_chot',
                     'SO-1', 'GHN-W', 'ghn', 'delivering',
                     '2026-11-12T03:00:00Z')
                """
            )
            moi = {
                "OrderCode": "GHN-W", "ClientOrderCode": "AS-WEBHOOK",
                "Status": "delivered", "Time": "2026-11-12T11:00:00+07:00",
            }
            assert (await xu_ly_webhook_van_chuyen("ghn", moi, {}, "secret"))["ok"]
            assert (await xu_ly_webhook_van_chuyen("ghn", moi, {}, "secret"))["ignored"]
            cu = dict(moi, Status="delivery_fail", Time="2026-11-12T10:30:00+07:00")
            assert (await xu_ly_webhook_van_chuyen("ghn", cu, {}, "secret"))["ignored"]
            row = await pool.fetchrow(
                "SELECT trang_thai_giao_hang, "
                "jsonb_array_length(lich_su_giao_hang) n, "
                "erp_van_chuyen_trang_thai "
                "FROM orders WHERE ma_don='AS-WEBHOOK'"
            )
            assert row["trang_thai_giao_hang"] == "delivered"
            assert row["n"] == 1
            assert row["erp_van_chuyen_trang_thai"] == "pending"
        finally:
            await pool.close()
            db._pool = old

    asyncio.run(scenario())


def test_frappe_get_omits_empty_custom_fields_va_put_xac_minh_du_lieu():
    reqs: list[httpx.Request] = []

    def xu_ly(req: httpx.Request) -> httpx.Response:
        reqs.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"data": {
                "name": "SAL-ORD-2",
                "doctype": "Sales Order",
                "docstatus": 0,
            }})
        body = json.loads(req.content)
        return httpx.Response(200, json={"data": {
            "name": "SAL-ORD-2",
            "doctype": "Sales Order",
            "docstatus": 0,
            "modified": "2026-11-12 03:00:01",
            **body,
        }})

    da_ghi = chay(_nguon(xu_ly).dong_bo_van_don(
        erp_ma_don="SAL-ORD-2",
        ma_van_don="GHN999",
        don_vi="ghn",
        trang_thai="delivering",
        dong_bo_luc=datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc),
        tham_chieu="AS261112002",
    ))
    assert da_ghi is True
    assert [r.method for r in reqs] == ["GET", "PUT"]


def test_frappe_put_200_bo_qua_field_thieu_la_loi_vinh_vien():
    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            return httpx.Response(200, json={"data": {
                "name": "SAL-ORD-3",
                "doctype": "Sales Order",
                "docstatus": 1,
            }})
        # Frappe trả 200 nhưng không lưu custom_shipping_* vì thiếu schema/allow_on_submit
        return httpx.Response(200, json={"data": {
            "name": "SAL-ORD-3",
            "doctype": "Sales Order",
            "docstatus": 1,
            "modified": "2026-11-12 03:00:01",
        }})

    with pytest.raises(TuChoiERP, match="không lưu được trường vận đơn"):
        chay(_nguon(xu_ly).dong_bo_van_don(
            erp_ma_don="SAL-ORD-3",
            ma_van_don="GHN404",
            don_vi="ghn",
            trang_thai="delivering",
            dong_bo_luc=datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc),
            tham_chieu="AS261112003",
        ))


@pytest.mark.parametrize(
    ("status_code", "expected_exc"),
    [
        (404, TuChoiERP),
        (403, TuChoiERP),
        (417, TuChoiERP),
        (429, LoiERP),
        (503, LoiERP),
    ],
)
def test_phan_loai_loi_erp_tam_thoi_hay_vinh_vien(status_code: int, expected_exc):
    def xu_ly(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and status_code == 404:
            return httpx.Response(404, json={"exception": "NotFound"})
        if req.method == "GET":
            return httpx.Response(200, json={"data": {"name": "SAL-ORD-4"}})
        return httpx.Response(status_code, json={"exception": f"HTTP {status_code}"})

    with pytest.raises(expected_exc):
        chay(_nguon(xu_ly).dong_bo_van_don(
            erp_ma_don="SAL-ORD-4",
            ma_van_don="GHN500",
            don_vi="ghn",
            trang_thai="delivering",
            dong_bo_luc=datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc),
            tham_chieu="AS261112004",
        ))


def test_e2e_ghn_luu_postgres_lost_response_retry_khong_tao_lai_ghn(
    csdl_kiem_thu, monkeypatch
):
    import asyncio
    import asyncpg

    from agent import db
    from agent.erp.dong_bo_van_don import cho_thu_lai, dong_bo_ngay, quet_dong_bo_van_don
    from agent.shipping.models import CreateWaybillResult
    from agent.shipping import service
    from scripts.dung_csdl_kiem_thu import dung

    async def scenario():
        await dung(csdl_kiem_thu)

        async def codec(conn):
            await conn.set_type_codec(
                "jsonb", encoder=json.dumps, decoder=json.loads,
                schema="pg_catalog",
            )

        pool = await asyncpg.create_pool(
            csdl_kiem_thu, min_size=1, max_size=3, init=codec
        )
        old = db._pool
        db._pool = pool
        ghn_calls = 0
        saved_on_erp: dict[str, str] = {}
        methods: list[str] = []

        class FakeGhn:
            code = "ghn"
            name = "GHN"

            async def tao_van_don(self, req):
                nonlocal ghn_calls
                ghn_calls += 1
                return CreateWaybillResult(
                    ok=True,
                    ma_van_don="GHN-E2E-1",
                    don_vi="ghn",
                    phi_van_chuyen=25000,
                )

        def erp_handler(req: httpx.Request) -> httpx.Response:
            methods.append(req.method)
            if req.method == "GET":
                return httpx.Response(200, json={"data": {
                    "name": "SAL-ORD-E2E",
                    "doctype": "Sales Order",
                    "docstatus": 0,
                    **saved_on_erp,
                }})
            # Giả lập ERPNext đã lưu xong nhưng phản hồi HTTP bị rớt mạng (timeout)
            if not saved_on_erp:
                saved_on_erp.update(json.loads(req.content))
                raise httpx.ReadTimeout("Mất phản hồi sau khi PUT")
            return httpx.Response(200, json={"data": {"name": "SAL-ORD-E2E"}})

        monkeypatch.setattr(service, "get_provider", lambda _name=None: FakeGhn())
        monkeypatch.setattr(
            "agent.erp.dong_bo_van_don._nguon_mac_dinh",
            lambda: _nguon(erp_handler),
        )
        nguon = _nguon(erp_handler)

        try:
            await pool.execute(
                """
                INSERT INTO orders
                    (ma_don, khach_ten, khach_sdt, khach_dia_chi, items,
                     tong_tien, trang_thai, erp_ma_don)
                VALUES
                    ('AS-E2E', 'Khach Test', '0901234567',
                     '123 Duong Nguyen Hue, Q1', '[{"ma":"SP1","so_luong":1,"don_gia":100000}]'::jsonb,
                     100000, 'da_chot', 'SAL-ORD-E2E')
                """
            )
            await pool.execute(
                "INSERT INTO kho_bien_dong (ma, thay_doi, ly_do, ma_don) "
                "VALUES ('SP1', -1, 'ban', 'AS-E2E')"
            )

            res1 = await service.tao_van_don_cho_don("AS-E2E", "ghn")
            assert res1.ok and res1.ma_van_don == "GHN-E2E-1"
            assert ghn_calls == 1
            assert res1.thong_tin_them["erp_sync"]["trang_thai"] == "retry"
            assert methods == ["GET", "PUT"]

            # Gọi retry hoặc worker quét lại -> GET phát hiện đã khớp, không PUT lại, không gọi GHN
            assert await cho_thu_lai("AS-E2E") is True
            scan = await quet_dong_bo_van_don(nguon)
            assert scan["dong_bo"] == 1
            assert ghn_calls == 1
            assert methods == ["GET", "PUT", "GET"]

            row = await pool.fetchrow(
                "SELECT ma_van_don, erp_van_chuyen_trang_thai FROM orders WHERE ma_don='AS-E2E'"
            )
            assert row["ma_van_don"] == "GHN-E2E-1"
            assert row["erp_van_chuyen_trang_thai"] == "synced"

            # Gọi dong_bo_ngay khi đã synced -> không làm gì thêm
            res2 = await dong_bo_ngay("AS-E2E", nguon)
            assert res2["ok"] and res2["trang_thai"] == "synced"
            assert methods == ["GET", "PUT", "GET"]
        finally:
            await pool.close()
            db._pool = old

    asyncio.run(scenario())
