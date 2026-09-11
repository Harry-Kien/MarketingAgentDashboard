"""
API vai trò — chạy trên Postgres thật.

VÌ SAO KHÔNG DÙNG KHO GIẢ
--------------------------
Ràng buộc quan trọng nhất ở đây là "không thu mất người cuối cùng có
`nguoi_dung.sua`", và nó phải đúng khi HAI quản trị bấm gỡ cùng lúc. Một kho
giả bằng dict luôn tuần tự, nên nó xanh với cả bản kiểm-trước-ghi-sau — tức
là xanh với đúng bản lỗi.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import nguoi_thu, toan_quyen  # noqa: E402

LUOC_DO = ROOT / "agent" / "schema.sql"


def _app_thu(url: str, nguoi: dict) -> FastAPI:
    """
    App trỏ `agent.db` vào CSDL kiểm thử, dựng lược đồ lúc KHỞI ĐỘNG.

    Phải dựng pool trong sự kiện khởi động chứ không trước khi tạo
    `TestClient`: pool asyncpg gắn với đúng event loop đã tạo ra nó, còn
    TestClient chạy app trong một loop khác. Tạo trước thì mọi truy vấn ném
    `RuntimeError: got Future attached to a different loop` — và thông báo
    ấy không hề gợi ý rằng vấn đề nằm ở chỗ tạo pool.
    """
    import asyncpg

    from agent import db
    from agent.api import quyen as api_quyen
    from agent.api.routes import nguoi_da_dang_nhap
    from agent.migrations.runner import apply_all

    app = FastAPI()
    app.include_router(api_quyen.router)
    app.dependency_overrides[nguoi_da_dang_nhap] = lambda: nguoi

    async def _codec(conn):
        await conn.set_type_codec(
            "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
        )

    @app.on_event("startup")
    async def _mo():
        db._pool = await asyncpg.create_pool(
            url, min_size=1, max_size=3, init=_codec)
        async with db._pool.acquire() as conn:
            await conn.execute(LUOC_DO.read_text(encoding="utf-8"))

            # Người thao tác phải TỒN TẠI THẬT, và phải tồn tại TRƯỚC khi
            # migration chạy.
            #
            # Hai lý do, cả hai đều là ràng buộc thật chứ không phải tiểu
            # tiết của test:
            #
            #   `nguoi_dung_vai_tro.gan_boi` có khoá ngoại tới `nguoi_dung`.
            #   Actor giả thì `gan_vai_tro` ném ForeignKeyViolation. Nới khoá
            #   ngoại cho test chạy là đánh đổi sai chiều — cột ấy là dấu vết
            #   kiểm toán "ai đã cấp quyền này", và dấu vết trỏ vào hư không
            #   thì không phải dấu vết.
            #
            #   Backfill của migration 0019 chỉ cấp vai trò cho người ĐANG
            #   CÓ. Chèn actor sau migration là actor không vai trò nào, và
            #   mọi thao tác ghi sẽ bị chốt "khoá cứng ngoài hệ thống" chặn
            #   ở 409 — đúng như nó phải chặn.
            #
            # Thứ tự ở đây (lược đồ -> người -> migration) đúng bằng thứ tự
            # của một lần nâng cấp thật trên máy đang chạy.
            await conn.execute(
                "INSERT INTO nguoi_dung (id, ten_dang_nhap, mat_khau_bam, "
                "ho_ten, vai_tro) VALUES ($1, $2, 'x', $2, $3) "
                "ON CONFLICT (id) DO NOTHING",
                UUID(str(nguoi["id"])), nguoi["ten_dang_nhap"],
                nguoi.get("vai_tro", "nhan_vien"),
            )
            await apply_all(conn)

    @app.on_event("shutdown")
    async def _dong():
        if db._pool is not None:
            await db._pool.close()
            db._pool = None

    return app


async def _chay_sql(url: str, sql: str, *args):
    """Truy vấn phụ trợ ngoài app — mở và đóng một kết nối riêng."""
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        return await conn.fetchval(sql, *args)
    finally:
        await conn.close()


def test_danh_muc_quyen_nhom_theo_tien_to(csdl_kiem_thu):
    from agent.core.quyen import QUYEN

    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        r = khach.get("/api/quyen")
        assert r.status_code == 200
        d = r.json()
        assert sum(len(v) for v in d["nhom"].values()) == len(QUYEN)
        # Nhãn phải đi kèm: màn cấp quyền hiện nhãn, không hiện mã.
        mot = next(iter(d["nhom"].values()))[0]
        assert mot["ma"] in QUYEN and mot["nhan"] == QUYEN[mot["ma"]]


def test_liet_ke_hai_vai_tro_nap_san_va_dem_nguoi(csdl_kiem_thu):
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        d = khach.get("/api/vai-tro").json()
        ten = {v["ten"] for v in d["vai_tro"]}
        assert ten == {"Quản trị", "Nhân viên"}
        assert all(v["he_thong"] for v in d["vai_tro"])
        assert all("so_nguoi" in v for v in d["vai_tro"])


def test_tao_sua_xoa_vai_tro_tu_dat(csdl_kiem_thu):
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        r = khach.post("/api/vai-tro", json={
            "ten": "Trưởng nhóm CSKH",
            "mo_ta": "Trả lời và giao việc",
            "quyen": ["hoi_thoai.doc", "hoi_thoai.tra_loi"],
        })
        assert r.status_code == 201, r.text
        vid = r.json()["id"]

        r = khach.put(f"/api/vai-tro/{vid}", json={
            "ten": "Trưởng nhóm CSKH",
            "mo_ta": "Trả lời, giao việc, xem báo cáo",
            "quyen": ["hoi_thoai.doc", "hoi_thoai.tra_loi", "bao_cao.doc"],
        })
        assert r.status_code == 200, r.text
        assert set(r.json()["quyen"]) == {
            "hoi_thoai.doc", "hoi_thoai.tra_loi", "bao_cao.doc"}

        assert khach.delete(f"/api/vai-tro/{vid}").status_code == 204


def test_quyen_la_thi_422_chu_khong_luu_am_tham(csdl_kiem_thu):
    """
    Gõ sai tên quyền mà vẫn lưu được thì vai trò cấp một thứ không tồn tại —
    ô tick hiện đã bật, và người quản trị tin là đã cấp.
    """
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        r = khach.post("/api/vai-tro", json={
            "ten": "Sai", "mo_ta": "", "quyen": ["khach.khong_co_that"]})
        assert r.status_code == 422
        assert "khach.khong_co_that" in r.text


def test_khong_xoa_duoc_vai_tro_he_thong(csdl_kiem_thu):
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        d = khach.get("/api/vai-tro").json()["vai_tro"]
        qt = next(v for v in d if v["ten"] == "Quản trị")
        r = khach.delete(f"/api/vai-tro/{qt['id']}")
        assert r.status_code == 409


def test_khong_sua_duoc_tap_quyen_cua_vai_tro_quan_tri(csdl_kiem_thu):
    """
    Vai trò `Quản trị` lấy quyền TỪ MÃ, không từ `vai_tro_quyen`.

    Cho sửa là để người quản trị bỏ tick, bấm Lưu, thấy báo thành công, và
    không có gì thay đổi. Một thao tác không tác dụng mà vẫn báo thành công
    còn tệ hơn một nút bị khoá: người ta tin là đã siết quyền rồi.
    """
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        d = khach.get("/api/vai-tro").json()["vai_tro"]
        qt = next(v for v in d if v["ten"] == "Quản trị")
        assert qt["toan_quyen"] is True

        r = khach.put(f"/api/vai-tro/{qt['id']}", json={
            "ten": "Quản trị", "mo_ta": "", "quyen": ["hoi_thoai.doc"]})
        assert r.status_code == 409, r.text
        assert "toàn bộ quyền" in r.text


def test_quan_tri_cuoi_cung_khong_tu_go_duoc_vai_tro_cua_minh(csdl_kiem_thu):
    """
    KHOÁ CỨNG NGOÀI HỆ THỐNG.

    Quản trị cuối cùng tự gỡ vai trò của mình thì không còn ai vào được màn
    Nhân viên để sửa lại. Đường vào duy nhất còn lại là mở CSDL ra gõ SQL —
    và đó không phải một đường, đó là một sự cố lúc 2 giờ sáng.

    Phép kiểm nằm TRONG giao dịch, sau lệnh ghi: đọc trước rồi ghi sau thì
    hai quản trị bấm cùng lúc đều thấy "vẫn còn người khác", cả hai lệnh ghi
    đều chạy, và kết quả là không còn ai.
    """
    sep = toan_quyen()
    with TestClient(_app_thu(csdl_kiem_thu, sep)) as khach:
        r = khach.put(f"/api/nguoi-dung/{sep['id']}/vai-tro",
                      json={"vai_tro": []})
        assert r.status_code == 409, r.text
        assert "nguoi_dung.sua" in r.text

        # Và vai trò PHẢI CÒN NGUYÊN — giao dịch đã rollback, không phải chỉ
        # trả lỗi rồi để lại một CSDL nửa vời.
        d = khach.get(f"/api/nguoi-dung/{sep['id']}/quyen").json()
        assert d["vai_tro"] == ["Quản trị"]


def test_go_duoc_vai_tro_khi_van_con_quan_tri_khac(csdl_kiem_thu):
    """
    Vế còn lại: chốt trên phải CHẶN ĐÚNG LÚC, không phải chặn mọi lúc.

    Một chốt luôn từ chối cũng làm mọi test ở trên xanh — và biến màn quản
    lý nhân viên thành màn chỉ đọc mà không ai hiểu vì sao.
    """
    sep = toan_quyen()
    with TestClient(_app_thu(csdl_kiem_thu, sep)) as khach:
        qt = next(v for v in khach.get("/api/vai-tro").json()["vai_tro"]
                  if v["ten"] == "Quản trị")
        uid = asyncio.run(_chay_sql(
            csdl_kiem_thu,
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('kt_sep_hai', 'x', 'Sếp hai') RETURNING id"))

        # Cấp Quản trị cho người thứ hai, rồi sếp một tự gỡ — giờ hợp lệ.
        assert khach.put(f"/api/nguoi-dung/{uid}/vai-tro",
                         json={"vai_tro": [qt["id"]]}).status_code == 200
        r = khach.put(f"/api/nguoi-dung/{sep['id']}/vai-tro",
                      json={"vai_tro": []})
        assert r.status_code == 200, r.text


def test_gan_vai_tro_cho_nguoi_va_giai_thich_quyen(csdl_kiem_thu):
    """
    `GET /api/nguoi-dung/{id}/quyen` nói rõ VAI TRÒ NÀO cấp quyền nào.

    Không có màn này thì khi đông vai trò, không ai trả lời được vì sao
    người này vào được màn kia — và câu trả lời duy nhất còn lại là đọc
    CSDL.
    """
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        uid = asyncio.run(_chay_sql(
            csdl_kiem_thu,
            "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten) "
            "VALUES ('kt_moi', 'x', 'Người mới') RETURNING id"))

        d = khach.get("/api/vai-tro").json()["vai_tro"]
        nv = next(v for v in d if v["ten"] == "Nhân viên")

        r = khach.put(f"/api/nguoi-dung/{uid}/vai-tro",
                      json={"vai_tro": [nv["id"]]})
        assert r.status_code == 200, r.text

        r = khach.get(f"/api/nguoi-dung/{uid}/quyen")
        assert r.status_code == 200, r.text
        giai_thich = r.json()
        assert giai_thich["quyen"]["hoi_thoai.doc"] == ["Nhân viên"]
        assert "khach.xoa" not in giai_thich["quyen"]


def test_nguoi_khong_du_quyen_bi_403(csdl_kiem_thu):
    with TestClient(_app_thu(csdl_kiem_thu, nguoi_thu("nguoi_dung.doc"))) as khach:
        assert khach.get("/api/vai-tro").status_code == 200     # chỉ đọc: qua
        r = khach.post("/api/vai-tro", json={
            "ten": "X", "mo_ta": "", "quyen": []})
        assert r.status_code == 403
        assert "nguoi_dung.sua" in r.json()["detail"]


def test_khong_tao_trung_ten_vai_tro(csdl_kiem_thu):
    """
    Hai vai trò cùng tên là màn cấp quyền hiện hai dòng giống hệt nhau, và
    người quản trị sửa nhầm dòng — sửa xong thấy không có tác dụng gì.
    """
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        than = {"ten": "Kế toán", "mo_ta": "", "quyen": ["don.doc"]}
        assert khach.post("/api/vai-tro", json=than).status_code == 201
        assert khach.post("/api/vai-tro", json=than).status_code == 409


def test_uuid_khong_ton_tai_thi_404(csdl_kiem_thu):
    with TestClient(_app_thu(csdl_kiem_thu, toan_quyen())) as khach:
        la = UUID("00000000-0000-0000-0000-0000000000ff")
        assert khach.delete(f"/api/vai-tro/{la}").status_code == 404
        assert khach.put(f"/api/vai-tro/{la}", json={
            "ten": "X", "mo_ta": "", "quyen": []}).status_code == 404
