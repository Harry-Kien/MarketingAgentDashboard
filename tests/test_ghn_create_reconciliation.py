"""
DEV-08: Kiểm thử GHN Create Timeout Reconciliation, stable client_order_code,
chống tạo trùng khi đồng thời/timeout, đối soát nền, xác nhận thủ công và DEV-02.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg
import httpx
import pytest

from agent import db
from agent.shipping import doi_soat, ghn as ghn_mod, service
from agent.shipping.ghn import GHNShippingProvider


@asynccontextmanager
async def _pool_kiem_thu(csdl_url: str):
    from scripts.dung_csdl_kiem_thu import dung

    await dung(csdl_url)

    async def codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    pool = await asyncpg.create_pool(csdl_url, min_size=1, max_size=6, init=codec)
    old = db._pool
    db._pool = pool
    try:
        yield pool
    finally:
        await pool.close()
        db._pool = old


async def _tao_don_chot(
    pool: asyncpg.Pool,
    ma_don: str,
    *,
    erp_ma_don: str | None = "SAL-ORD-TEST",
    sku: str = "SRM-C",
) -> uuid.UUID:
    await pool.execute(
        """
        INSERT INTO ton_kho (ma, so_luong)
        VALUES ($1, 100)
        ON CONFLICT (ma) DO UPDATE SET so_luong = 100
        """,
        sku,
    )
    items = json.dumps(
        [{"ma": sku, "ten": "Serum C", "so_luong": 1, "don_gia": 320000}],
        ensure_ascii=False,
    )
    oid = await pool.fetchval(
        """
        INSERT INTO orders (
            ma_don, khach_ten, khach_sdt, khach_dia_chi, items,
            tong_tien, trang_thai, erp_ma_don, erp_van_chuyen_trang_thai
        )
        VALUES ($1, 'Nguyễn Thu Hà', '0912345678',
                '12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh',
                $2::jsonb, 320000, 'da_chot', $3, 'not_required')
        RETURNING id
        """,
        ma_don,
        items,
        erp_ma_don,
    )
    return oid


def _cai_mock_ghn(
    monkeypatch,
    *,
    handler,
) -> GHNShippingProvider:
    goc_client = httpx.AsyncClient

    def tao_client(**kw):
        return goc_client(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(ghn_mod.httpx, "AsyncClient", tao_client)
    monkeypatch.setattr(ghn_mod, "_DISTRICTS_CACHE", [{"DistrictID": 1442, "DistrictName": "Quận 1"}])
    monkeypatch.setattr(
        ghn_mod,
        "_WARDS_CACHE",
        {1442: [{"WardCode": "20101", "WardName": "Phường Bến Nghé"}]},
    )
    prov = GHNShippingProvider(
        api_url="https://dev-online-gateway.ghn.vn/shiip/public-api/v2",
        token="tok-test",
        shop_id="196560",
    )
    monkeypatch.setitem(service._PROVIDERS, "ghn", prov)
    return prov


def test_tc01_timeout_khi_tao_giu_nguyen_client_code_va_chan_tao_lai(csdl_kiem_thu, monkeypatch):
    create_calls: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            body = json.loads(req.content)
            create_calls.append(body)
            raise httpx.ReadTimeout("GHN timed out after server created waybill", request=req)
        raise AssertionError(f"Unexpected path: {req.url}")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC01")
            _cai_mock_ghn(monkeypatch, handler=handler)

            kq1 = await service.tao_van_don_cho_don("AS-TC01", "ghn")
            assert kq1.ok is False
            assert kq1.khong_ro_ket_qua is True
            assert kq1.client_order_code == "AS-TC01"
            assert len(create_calls) == 1
            assert create_calls[0]["client_order_code"] == "AS-TC01"

            order_row = await pool.fetchrow(
                "SELECT ma_van_don, erp_van_chuyen_trang_thai FROM orders WHERE id = $1", oid
            )
            assert order_row["ma_van_don"] is None

            req_row = await pool.fetchrow(
                "SELECT trang_thai, client_order_code, so_lan_gui "
                "FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert req_row["trang_thai"] == "unknown_timeout"
            assert req_row["client_order_code"] == "AS-TC01"
            assert req_row["so_lan_gui"] == 1

            # Gọi tạo lại khi đang unknown_timeout -> bị CHẶN, không gọi GHN lần 2.
            kq2 = await service.tao_van_don_cho_don("AS-TC01", "ghn")
            assert kq2.ok is False
            assert kq2.khong_ro_ket_qua is True
            assert kq2.client_order_code == "AS-TC01"
            assert len(create_calls) == 1

    asyncio.run(run())


def test_tc02_tc11_timeout_roi_doi_soat_tim_thay_khoi_phuc_va_dong_bo_erp(csdl_kiem_thu, monkeypatch):
    create_calls: list[dict[str, Any]] = []
    lookup_calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            create_calls.append(json.loads(req.content))
            raise httpx.ReadTimeout("timeout after create", request=req)
        if req.url.path.endswith("/shipping-order/detail-by-client-code"):
            lookup_calls.append(req)
            code = req.url.params.get("client_order_code")
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "Success",
                    "data": {
                        "order_code": "GHN-RECOVER-02",
                        "client_order_code": code,
                        "status": "ready_to_pick",
                        "total_fee": 27000,
                    },
                },
            )
        raise AssertionError(f"Unexpected path: {req.url}")

    class FakeErp:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def dong_bo_van_don(self, **kw) -> bool:
            self.calls.append((kw["erp_ma_don"], kw["ma_van_don"]))
            return True

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC02", erp_ma_don="SAL-ORD-02")
            await pool.execute("UPDATE orders SET conversation_id = NULL WHERE id = $1", oid)
            _cai_mock_ghn(monkeypatch, handler=handler)

            fake_erp = FakeErp()
            monkeypatch.setattr("agent.erp.dong_bo_van_don._nguon_mac_dinh", lambda: fake_erp)

            kq1 = await service.tao_van_don_cho_don("AS-TC02", "ghn")
            assert kq1.khong_ro_ket_qua is True
            assert len(create_calls) == 1

            summary = await doi_soat.quet_doi_soat_van_don(limit=5)
            assert summary["da_khoi_phuc"] == 1
            assert len(lookup_calls) == 1
            assert lookup_calls[0].method == "GET"
            assert lookup_calls[0].url.params["client_order_code"] == "AS-TC02"
            assert lookup_calls[0].headers["Token"] == "tok-test"
            assert lookup_calls[0].headers["ShopId"] == "196560"

            order_row = await pool.fetchrow(
                "SELECT ma_van_don, don_vi_van_chuyen, phi_van_chuyen, "
                "erp_van_chuyen_trang_thai FROM orders WHERE id = $1",
                oid,
            )
            assert order_row["ma_van_don"] == "GHN-RECOVER-02"
            assert order_row["don_vi_van_chuyen"] == "ghn"
            assert order_row["phi_van_chuyen"] == 27000
            assert order_row["erp_van_chuyen_trang_thai"] == "synced"
            assert fake_erp.calls == [("SAL-ORD-02", "GHN-RECOVER-02")]

            req_row = await pool.fetchrow(
                "SELECT trang_thai, ma_van_don FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert req_row["trang_thai"] == "reconciled"
            assert req_row["ma_van_don"] == "GHN-RECOVER-02"
            assert len(create_calls) == 1

    asyncio.run(run())


def test_tc03_tc07_not_found_khong_tu_tao_lai_va_giu_nguyen_client_code_sau_xac_nhan(csdl_kiem_thu, monkeypatch):
    create_calls: list[dict[str, Any]] = []
    mode = {"allow_create": False}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            body = json.loads(req.content)
            create_calls.append(body)
            if not mode["allow_create"]:
                raise httpx.ConnectTimeout("timeout on first create", request=req)
            return httpx.Response(
                200,
                json={"code": 200, "data": {"order_code": "GHN-RETRY-03", "total_fee": 22000}},
            )
        if req.url.path.endswith("/shipping-order/detail-by-client-code"):
            return httpx.Response(
                400,
                json={"code": 400, "code_message_value": "ORDER_NOT_FOUND", "message": "Order not found"},
            )
        raise AssertionError(f"Unexpected path: {req.url}")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC03", erp_ma_don=None)
            _cai_mock_ghn(monkeypatch, handler=handler)

            kq1 = await service.tao_van_don_cho_don("AS-TC03", "ghn")
            assert kq1.khong_ro_ket_qua is True

            # Chạy đủ SO_LAN_DOI_SOAT_TOI_DA lượt với not_found -> KHÔNG tự tạo lại, chuyển manual_required.
            for _ in range(doi_soat.SO_LAN_DOI_SOAT_TOI_DA):
                await pool.execute(
                    "UPDATE shipping_waybill_requests SET doi_soat_tiep_luc = now() WHERE order_id = $1",
                    oid,
                )
                await doi_soat.quet_doi_soat_van_don(limit=5)

            req_row = await pool.fetchrow(
                "SELECT trang_thai, client_order_code, ly_do_chan "
                "FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert req_row["trang_thai"] == "manual_required"
            assert req_row["client_order_code"] == "AS-TC03"
            assert len(create_calls) == 1

            # Vẫn bị chặn nếu gọi tao_van_don_cho_don khi chưa xác nhận thủ công.
            kq_blocked = await service.tao_van_don_cho_don("AS-TC03", "ghn")
            assert kq_blocked.ok is False and kq_blocked.can_nguoi_xac_nhan is True
            assert len(create_calls) == 1

            # Nhân viên xác nhận GHN chưa tạo đơn kèm bằng chứng.
            conf = await doi_soat.xac_nhan_thu_cong(
                oid,
                ket_qua="chua_tao_tren_ghn",
                ghi_chu="Đã kiểm tra cổng GHN, không có đơn AS-TC03",
                actor="quanly_kho",
            )
            assert conf["ok"] is True and conf["trang_thai"] == "rejected"

            # Bây giờ mới tạo lại được, và PHẢI dùng đúng client_order_code ban đầu.
            mode["allow_create"] = True
            kq_ok = await service.tao_van_don_cho_don("AS-TC03", "ghn")
            assert kq_ok.ok is True and kq_ok.ma_van_don == "GHN-RETRY-03"
            assert len(create_calls) == 2
            assert create_calls[0]["client_order_code"] == create_calls[1]["client_order_code"] == "AS-TC03"

    asyncio.run(run())


def test_tc04_lookup_500_va_da_van_don_trung_la_indeterminate_va_escalate(csdl_kiem_thu, monkeypatch):
    responses = iter([
        httpx.Response(502, text="Bad Gateway"),
        httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {"order_code": "GHN-DUP-1", "client_order_code": "AS-TC04"},
                    {"order_code": "GHN-DUP-2", "client_order_code": "AS-TC04"},
                ],
            },
        ),
    ])

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            return httpx.Response(504, json={"code": 504, "message": "Gateway Timeout"})
        if req.url.path.endswith("/shipping-order/detail-by-client-code"):
            return next(responses, httpx.Response(503, json={"message": "Service Unavailable"}))
        raise AssertionError(f"Unexpected path: {req.url}")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC04", erp_ma_don=None)
            _cai_mock_ghn(monkeypatch, handler=handler)

            kq = await service.tao_van_don_cho_don("AS-TC04", "ghn")
            assert kq.khong_ro_ket_qua is True

            # Lần 1 (HTTP 502) -> lên lịch retry + backoff.
            await doi_soat.quet_doi_soat_van_don(limit=5)
            row1 = await pool.fetchrow(
                "SELECT trang_thai, so_lan_doi_soat, doi_soat_tiep_luc "
                "FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert row1["trang_thai"] == "unknown_timeout"
            assert row1["so_lan_doi_soat"] == 1
            assert row1["doi_soat_tiep_luc"] > datetime.now(timezone.utc)

            # Quét ngay trước hẹn -> không chạy spam.
            dem_som = await doi_soat.quet_doi_soat_van_don(limit=5)
            assert dem_som["da_xu_ly"] == 0

            # Hết hạn retry tối đa (kể cả gặp 2 mã trùng trên cùng client_order_code) -> manual_required.
            for _ in range(doi_soat.SO_LAN_DOI_SOAT_TOI_DA):
                await pool.execute(
                    "UPDATE shipping_waybill_requests SET doi_soat_tiep_luc = now() WHERE order_id = $1",
                    oid,
                )
                await doi_soat.quet_doi_soat_van_don(limit=5)

            row_cuoi = await pool.fetchrow(
                "SELECT trang_thai, so_lan_doi_soat FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert row_cuoi["trang_thai"] == "manual_required"
            assert row_cuoi["so_lan_doi_soat"] == doi_soat.SO_LAN_DOI_SOAT_TOI_DA

    asyncio.run(run())


def test_tc05_double_click_song_song_chi_goi_ghn_mot_lan(csdl_kiem_thu, monkeypatch):
    create_calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("Sẽ được xử lý bằng provider giả bất đồng bộ bên dưới")

    class SlowGHNProvider(GHNShippingProvider):
        async def tao_van_don(self, req):
            nonlocal create_calls
            create_calls += 1
            await asyncio.sleep(0.15)
            from agent.shipping.models import CreateWaybillResult

            return CreateWaybillResult(
                ok=True,
                ma_van_don="GHN-CONC-05",
                don_vi="ghn",
                phi_van_chuyen=25000,
                client_order_code=req.client_order_code,
            )

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            await _tao_don_chot(pool, "AS-TC05", erp_ma_don=None)
            _cai_mock_ghn(monkeypatch, handler=handler)
            monkeypatch.setitem(
                service._PROVIDERS,
                "ghn",
                SlowGHNProvider(api_url="https://ghn.test", token="t", shop_id="1"),
            )

            r1, r2 = await asyncio.gather(
                service.tao_van_don_cho_don("AS-TC05", "ghn"),
                service.tao_van_don_cho_don("AS-TC05", "ghn"),
            )
            assert create_calls == 1
            assert sorted([r1.ok, r2.ok]) == [False, True]
            ok_res = r1 if r1.ok else r2
            blocked_res = r2 if r1.ok else r1
            assert ok_res.ma_van_don == "GHN-CONC-05"
            assert blocked_res.khong_ro_ket_qua is True

    asyncio.run(run())


def test_tc12_concurrent_reconciliation_workers_skip_locked(csdl_kiem_thu, monkeypatch):
    lookup_count = 0

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("Dùng FakeSlowProvider bên dưới")

    class FakeSlowLookupProvider(GHNShippingProvider):
        async def tra_cuu_theo_ma_tham_chieu(self, client_order_code: str):
            nonlocal lookup_count
            lookup_count += 1
            await asyncio.sleep(0.1)
            from agent.shipping.models import ClientCodeLookupResult

            return ClientCodeLookupResult(
                trang_thai="found",
                ma_van_don="GHN-LOCKED-12",
                client_order_code=client_order_code,
                don_vi="ghn",
                phi_van_chuyen=24000,
            )

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC12", erp_ma_don=None)
            _cai_mock_ghn(monkeypatch, handler=handler)
            monkeypatch.setitem(
                service._PROVIDERS,
                "ghn",
                FakeSlowLookupProvider(api_url="https://ghn.test", token="t", shop_id="1"),
            )
            await pool.execute(
                """
                INSERT INTO shipping_waybill_requests (
                    order_id, ma_don, provider, client_order_code, trang_thai, doi_soat_tiep_luc
                )
                VALUES ($1, 'AS-TC12', 'ghn', 'AS-TC12', 'unknown_timeout', now())
                """,
                oid,
            )

            s1, s2 = await asyncio.gather(
                doi_soat.quet_doi_soat_van_don(limit=5),
                doi_soat.quet_doi_soat_van_don(limit=5),
            )
            assert lookup_count == 1
            assert s1["da_khoi_phuc"] + s2["da_khoi_phuc"] == 1

    asyncio.run(run())


def test_tc13_ghn_tu_choi_400_cho_phep_thu_lai_voi_cung_client_code(csdl_kiem_thu, monkeypatch):
    create_calls: list[dict[str, Any]] = []
    attempt = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            attempt["n"] += 1
            body = json.loads(req.content)
            create_calls.append(body)
            if attempt["n"] == 1:
                return httpx.Response(
                    400, json={"code": 400, "message": "COD exceeds shop limit"}
                )
            return httpx.Response(
                200, json={"code": 200, "data": {"order_code": "GHN-AFTER-400", "total_fee": 20000}}
            )
        raise AssertionError(f"Unexpected path: {req.url}")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC13", erp_ma_don=None)
            _cai_mock_ghn(monkeypatch, handler=handler)

            r1 = await service.tao_van_don_cho_don("AS-TC13", "ghn")
            assert r1.ok is False
            assert r1.khong_ro_ket_qua is False

            st1 = await pool.fetchval(
                "SELECT trang_thai FROM shipping_waybill_requests WHERE order_id = $1", oid
            )
            assert st1 == "rejected"

            r2 = await service.tao_van_don_cho_don("AS-TC13", "ghn")
            assert r2.ok is True and r2.ma_van_don == "GHN-AFTER-400"
            assert create_calls[0]["client_order_code"] == create_calls[1]["client_order_code"] == "AS-TC13"

    asyncio.run(run())


def test_tc14_loi_luu_db_sau_khi_ghn_tao_van_don_khong_tao_trung_va_tu_khoi_phuc(csdl_kiem_thu, monkeypatch):
    create_calls: list[dict[str, Any]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            create_calls.append(json.loads(req.content))
            return httpx.Response(
                200,
                json={"code": 200, "data": {"order_code": "GHN-DB-RECOVER", "total_fee": 26000}},
            )
        raise AssertionError("Không cần gọi lookup khi ma_van_don đã được ghi dự phòng")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-TC14", erp_ma_don="SAL-ORD-14")
            _cai_mock_ghn(monkeypatch, handler=handler)

            goc_chot = doi_soat.chot_luu_van_don_thanh_cong

            async def gia_loi_db(**kw):
                raise RuntimeError("Simulated DB connection drop during final commit")

            monkeypatch.setattr(doi_soat, "chot_luu_van_don_thanh_cong", gia_loi_db)
            kq1 = await service.tao_van_don_cho_don("AS-TC14", "ghn")
            assert kq1.ok is False and kq1.khong_ro_ket_qua is True
            assert len(create_calls) == 1
            assert await pool.fetchval("SELECT ma_van_don FROM orders WHERE id = $1", oid) is None

            # Khôi phục hàm DB; gọi tao_van_don_cho_don lần 2 KHÔNG được gọi lại GHN.
            monkeypatch.setattr(doi_soat, "chot_luu_van_don_thanh_cong", goc_chot)
            kq2 = await service.tao_van_don_cho_don("AS-TC14", "ghn")
            assert kq2.ok is False and kq2.khong_ro_ket_qua is True
            assert len(create_calls) == 1

            # Worker đối soát chạy -> khôi phục vào orders + bật chờ DEV-02 ERP sync.
            summary = await doi_soat.quet_doi_soat_van_don(limit=5)
            assert summary["da_khoi_phuc"] == 1
            row = await pool.fetchrow(
                "SELECT ma_van_don, erp_van_chuyen_trang_thai FROM orders WHERE id = $1", oid
            )
            assert row["ma_van_don"] == "GHN-DB-RECOVER"
            assert row["erp_van_chuyen_trang_thai"] == "retry" or row["erp_van_chuyen_trang_thai"] in ("pending", "retry", "synced")
            assert len(create_calls) == 1

    asyncio.run(run())


def test_tc08_tc09_api_nhan_vien_quyen_xac_nhan_thu_cong_va_chan_ghi_de(app_that, monkeypatch):
    from agent.config import settings
    from tests.test_nghiem_thu_saas import _nhan_vien_moi
    from tests.test_hoan_thien_luong import _don, _quan_tri_vao, _sql

    monkeypatch.setattr(settings, "shipping_provider", "ghn")
    qt = _quan_tri_vao(app_that)
    _, nguoi_thuong = _nhan_vien_moi(qt, "nhanvien_chixem", vai_tro=None)
    oid_s, ma_don = _don(
        app_that,
        "da_chot",
        khach_dia_chi="12 Lê Lợi, Phường Bến Nghé, Quận 1, TP Hồ Chí Minh",
    )
    oid = uuid.UUID(oid_s)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            raise httpx.ReadTimeout("timeout", request=req)
        if req.url.path.endswith("/shipping-order/detail-by-client-code"):
            return httpx.Response(503, json={"message": "GHN maintenance"})
        raise AssertionError(f"Unexpected path: {req.url}")

    _cai_mock_ghn(monkeypatch, handler=handler)

    # Nhân viên xác nhận GHN chưa tạo đơn -> đổi về rejected... (test API flow below)
    async def _prep():
        await db.execute(
            "INSERT INTO ton_kho (ma, so_luong) VALUES ('SP1', 50) "
            "ON CONFLICT (ma) DO UPDATE SET so_luong = 50"
        )

    _sql(app_that, _prep)

    # Tạo đơn -> rơi vào unknown_timeout -> HTTP 409 Conflict (không phải 200).
    r_create = qt.post(f"/api/orders/{oid_s}/van-don", json={})
    assert r_create.status_code == 409
    assert ma_don in r_create.json()["detail"]

    # Người không có quyền không được kích đối soát hoặc xác nhận thủ công.
    assert nguoi_thuong.post(f"/api/orders/{oid_s}/shipping-reconcile").status_code == 403
    assert nguoi_thuong.post(
        f"/api/orders/{oid_s}/shipping-manual-confirm",
        json={"ket_qua": "da_co_van_don", "ma_van_don": "GHN-MAN-1", "ghi_chu": "Kiểm tra GHN"},
    ).status_code == 403

    # API đọc trạng thái đối soát
    r_info = qt.get(f"/api/orders/{oid_s}/shipping-reconciliation")
    assert r_info.status_code == 200
    assert r_info.json()["reconciliation"]["trang_thai"] == "unknown_timeout"
    assert r_info.json()["reconciliation"]["client_order_code"] == ma_don

    # List orders cũng trả trạng thái đối soát
    r_list = qt.get("/api/orders")
    assert r_list.status_code == 200
    dong_don = next(o for o in r_list.json() if o["id"] == oid_s)
    assert dong_don["van_don_trang_thai_yeucau"] == "unknown_timeout"
    assert dong_don["van_don_client_order_code"] == ma_don

    # Thiếu ma_van_don khi xác nhận đã có -> 422
    r_bad = qt.post(
        f"/api/orders/{oid_s}/shipping-manual-confirm",
        json={"ket_qua": "da_co_van_don", "ma_van_don": "", "ghi_chu": "Kiểm tra GHN"},
    )
    assert r_bad.status_code == 422

    # Bấm re-check khi GHN trả 503 -> không cho tạo lại
    r_re = qt.post(f"/api/orders/{oid_s}/shipping-reconcile")
    assert r_re.status_code == 200 and r_re.json()["ok"] is False

    # Nhân viên xác nhận thủ công GHN đã có mã GHN-MAN-08
    async def _gan_erp():
        await db.execute("UPDATE orders SET erp_ma_don = 'SAL-MAN-08' WHERE id = $1", oid)

    _sql(app_that, _gan_erp)
    r_ok = qt.post(
        f"/api/orders/{oid_s}/shipping-manual-confirm",
        json={
            "ket_qua": "da_co_van_don",
            "ma_van_don": "GHN-MAN-08",
            "ghi_chu": "Đã đối chiếu cổng GHN Shop 196560",
        },
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["ma_van_don"] == "GHN-MAN-08"

    # TC-09: Đã có mã vận đơn khác -> chặn ghi đè bằng mã mới hoặc mở khóa giả.
    r_overwrite = qt.post(
        f"/api/orders/{oid_s}/shipping-manual-confirm",
        json={
            "ket_qua": "da_co_van_don",
            "ma_van_don": "GHN-KHAC-999",
            "ghi_chu": "Thử ghi đè mã vận đơn khác",
        },
    )
    assert r_overwrite.status_code == 409

    # Kiểm tra audit log ghi đầy đủ
    async def _doc_logs():
        return await db.fetch("SELECT kind FROM events WHERE ref_id = $1 ORDER BY created_at", oid)

    logs = _sql(app_that, _doc_logs)
    kinds = [r["kind"] for r in logs]
    assert "shipping.manual_confirm_found" in kinds


def test_tc10_ai_agent_khong_duoc_tu_tao_hoac_xac_nhan_van_don():
    from pathlib import Path
    from agent.core import tools

    ten_tools = [t.get("name") or t.get("function", {}).get("name") for t in tools.TOOLS]
    for cam in ("tao_van_don", "shipping_manual_confirm", "xac_nhan_van_don", "doi_soat_van_don"):
        assert cam not in ten_tools
    src = Path("agent/core/tools.py").read_text(encoding="utf-8")
    assert "def _tool_tao_van_don" not in src
    assert "provider.tao_van_don" not in src


def test_webhook_den_trong_luc_unknown_timeout_se_tu_doi_soat(csdl_kiem_thu, monkeypatch):
    from agent.config import settings

    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/shipping-order/create"):
            raise httpx.ReadTimeout("timeout before receiving tracking", request=req)
        raise AssertionError(f"Unexpected path: {req.url}")

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            oid = await _tao_don_chot(pool, "AS-WH-REC", erp_ma_don="SAL-WH-REC")
            _cai_mock_ghn(monkeypatch, handler=handler)

            kq = await service.tao_van_don_cho_don("AS-WH-REC", "ghn")
            assert kq.khong_ro_ket_qua is True

            wh = await service.xu_ly_webhook_van_chuyen(
                "ghn",
                {
                    "OrderCode": "GHN-WH-99",
                    "ClientOrderCode": "AS-WH-REC",
                    "Status": "picking",
                    "Time": "2026-11-12T09:30:00+00:00",
                },
                {},
                query_token="bi-mat",
            )
            assert wh["ok"] is True

            req_row = await pool.fetchrow(
                "SELECT trang_thai, ma_van_don, xac_nhan_boi "
                "FROM shipping_waybill_requests WHERE order_id = $1",
                oid,
            )
            assert req_row["trang_thai"] == "reconciled"
            assert req_row["ma_van_don"] == "GHN-WH-99"
            assert req_row["xac_nhan_boi"] == "webhook"

    asyncio.run(run())


def test_tc14_db_connection_never_held_during_ghn_http_call(csdl_kiem_thu, monkeypatch):
    """Đảm bảo không giữ transaction PostgreSQL mở trong lúc gọi HTTP GHN."""
    pool_stats: dict[str, int] = {}

    class InspectPoolGHN(GHNShippingProvider):
        async def tao_van_don(self, req):
            pool = db.pool()
            # Lúc đang ở trong HTTP client, số connection đang acquire phải là 0!
            pool_stats["idle"] = pool.get_idle_size()
            pool_stats["size"] = pool.get_size()
            from agent.shipping.models import CreateWaybillResult

            return CreateWaybillResult(
                ok=True,
                ma_van_don="GHN-NO-LONG-TX",
                don_vi="ghn",
                phi_van_chuyen=19000,
                client_order_code=req.client_order_code,
            )

    async def run():
        async with _pool_kiem_thu(csdl_kiem_thu) as pool:
            await _tao_don_chot(pool, "AS-NOTX", erp_ma_don=None)
            monkeypatch.setitem(
                service._PROVIDERS,
                "ghn",
                InspectPoolGHN(api_url="https://ghn.test", token="t", shop_id="1"),
            )
            kq = await service.tao_van_don_cho_don("AS-NOTX", "ghn")
            assert kq.ok is True
            assert pool_stats["idle"] == pool_stats["size"]

    asyncio.run(run())
