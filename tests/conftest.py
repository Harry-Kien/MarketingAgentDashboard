"""
Tiện ích dùng chung: soi tài liệu, và CSDL kiểm thử.

VÌ SAO NẰM Ở ĐÂY CHỨ KHÔNG CHÉP VÀO TỪNG FILE
---------------------------------------------
`test_claude_md.py` và `test_dua_vao_doanh_nghiep.py` cùng cần một phép
kiểm: "đường dẫn tài liệu này nhắc tới còn sống không". Chép hai bản là tạo
đúng thứ vừa gây ra lỗi trong `agent/main.py` — hai bản sao của một việc,
rồi bản ít người đọc hơn mục đi. Ở đây nó lộ ra ngay khi viết: bản đầu tiên
quên xét thư mục cha, và bản thứ hai thừa hưởng nguyên lỗi ấy.
"""
from __future__ import annotations

import asyncio
import functools
import os
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Đếm số test integration bị bỏ qua, để in một dòng TO ở cuối lượt chạy.
_DEM_BO_QUA = {"n": 0}

# Postgres của `docker compose up -d` trong repo này.
#
# CSDL riêng tên `kiemthu`, KHÔNG phải `marketing_agent` (dữ liệu khách
# thật) và cũng không phải `postgres` (CSDL quản trị, không có lược đồ).
# Cùng cách CI làm: workflow trỏ `TEST_DATABASE_URL` vào một CSDL riêng rồi
# chạy `scripts.dung_csdl_kiem_thu`.
#
# Từng trỏ nhầm vào `/postgres` ở bản đầu, và hậu quả đúng kiểu đỏ-vì-hạ-
# tầng: `relation "outbox_jobs" does not exist`. Test nào tạo CSDL mới qua
# fixture thì không sao (nó chỉ lấy phần máy chủ), nhưng test nào dùng
# THẲNG url thì gãy.
_POSTGRES_COMPOSE = "postgresql://agent:agent@127.0.0.1:5433/kiemthu"


def _co_mo_duoc(url: str, giay: float = 3.0) -> bool:
    """
    Có Postgres ĐĂNG NHẬP ĐƯỢC ở địa chỉ này không.

    Phải đăng nhập thật, không chỉ bắt tay TCP. Bắt tay TCP xanh với BẤT KỲ
    thứ gì đang nghe ở cổng 5433 — một Postgres khác của người dùng, hay
    một dịch vụ chẳng liên quan. Khi ấy lưới tự dò biến hơn trăm test từ
    "bỏ qua sạch" thành "lỗi xác thực hàng loạt", và người nhận là người
    vừa clone repo về. Đổi một lỗi im lặng lấy một trận đỏ vô nghĩa thì
    không phải là cải thiện.

    Chạy ĐÚNG MỘT LẦN mỗi lượt (`lru_cache` ở hàm gọi nó), nên vài chục
    mili-giây này không đáng kể.
    """
    try:
        import asyncpg
    except ImportError:
        return False

    async def thu() -> bool:
        try:
            conn = await asyncio.wait_for(asyncpg.connect(url), timeout=giay)
        except Exception:
            # Bắt rộng có chủ ý: máy chủ chưa lên, sai mật khẩu, sai CSDL,
            # hết giờ — mọi trường hợp đều dẫn tới cùng một kết luận là
            # "không dùng được", và không cái nào đáng làm đỏ lượt chạy.
            return False
        await conn.close()
        return True

    try:
        return asyncio.run(thu())
    except RuntimeError:
        # Đã có vòng lặp đang chạy (pytest-asyncio) — coi như không dò được
        # còn hơn là đâm vào vòng lặp của người khác.
        return False


@functools.lru_cache(maxsize=1)
def dia_chi_csdl_kiem_thu() -> str | None:
    """
    Địa chỉ Postgres cho test integration, hoặc None nếu không có.

    VÌ SAO TỰ DÒ CHỨ KHÔNG BẮT NGƯỜI TA ĐẶT BIẾN
    ---------------------------------------------
    ĐO ĐƯỢC 22.09.2026: chạy `pytest -q` ở máy phát triển cho
    `3150 passed, 124 skipped` — và 124 cái bị bỏ qua CHÍNH LÀ nhóm chạm
    Postgres thật: quyền, phiên, phạm vi tầm nhìn, khôi phục sao lưu. Đúng
    lúc ấy container Postgres VẪN ĐANG CHẠY ở cổng 5433. Thiếu mỗi một biến
    môi trường.

    CLAUDE.md dặn "trước khi báo là xong: pytest phải xanh hết". Dấu xanh
    ấy đang bỏ qua đúng nhóm test canh những ràng buộc đắt nhất, và dòng
    `124 skipped` thì trôi mất giữa 3150 dấu chấm.

    CI không dính vì workflow có sẵn `TEST_DATABASE_URL`
    (`test_ci_co_postgres.py` canh việc đó). Nên đây thuần tuý là lỗ ở vòng
    lặp tại máy — chỗ người ta chạy test nhiều nhất.

    Thứ tự ưu tiên giữ nguyên tính dự đoán được: biến môi trường luôn thắng,
    tự dò chỉ là lưới đỡ. Đặt `KHONG_DUNG_POSTGRES_LOCAL=1` để tắt lưới ấy.
    """
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        return url
    if os.getenv("KHONG_DUNG_POSTGRES_LOCAL"):
        return None

    # Dò MÁY CHỦ trước: đăng nhập vào CSDL quản trị `postgres`. CSDL
    # `kiemthu` có thể chưa tồn tại ở lần chạy đầu, nên dò thẳng nó sẽ luôn
    # trả False và lưới không bao giờ bật.
    goc = _POSTGRES_COMPOSE.rpartition("/")[0]
    if not _co_mo_duoc(f"{goc}/postgres"):
        return None

    # Dựng CSDL và lược đồ — đúng việc CI làm bằng một bước riêng
    # (`scripts.dung_csdl_kiem_thu`). Idempotent: migration có version nên
    # lần chạy sau không làm gì thêm.
    #
    # Tạo CSDL từ conftest nghe mạnh tay, nhưng fixture `csdl_kiem_thu`
    # vốn đã tạo và xoá CSDL `kt_<uuid>` trên đúng máy chủ này ở mỗi test.
    # Thêm một CSDL `kiemthu` cố định không phải là quyền mới.
    try:
        from scripts.dung_csdl_kiem_thu import dung

        asyncio.run(dung(_POSTGRES_COMPOSE))
    except Exception as e:
        # Không dựng được thì BÁO, đừng im: im lặng ở đây đưa người ta trở
        # lại đúng tình trạng cũ — hơn trăm test bỏ qua mà không rõ vì sao.
        print(f"\n[conftest] Không dựng được CSDL kiểm thử: {type(e).__name__}: {e}")
        return None
    return _POSTGRES_COMPOSE


def dem_bo_qua_integration() -> None:
    """
    Cho các file tự kiểm CSDL (không qua fixture `csdl_kiem_thu`) góp số vào
    cùng một bộ đếm — nếu không, dòng cảnh báo cuối lượt sẽ đếm thiếu và
    báo nhẹ hơn thực tế.
    """
    _DEM_BO_QUA["n"] += 1


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Bỏ qua bao nhiêu test thì phải NÓI TO bấy nhiêu.

    `124 skipped` nằm lẫn trong dòng tổng kết là thứ người ta đọc lướt qua.
    Mà nhóm bị bỏ chính là nhóm canh phân quyền và phạm vi dữ liệu — bỏ qua
    nó rồi báo "xanh hết" là đúng định nghĩa xanh giả.
    """
    n = _DEM_BO_QUA["n"]
    if not n:
        return
    terminalreporter.write_sep("=", "CẢNH BÁO: TEST POSTGRES KHÔNG CHẠY", red=True, bold=True)
    terminalreporter.write_line(
        f"{n} test integration bị bỏ qua — gồm quyền, phiên, phạm vi tầm nhìn "
        "và khôi phục sao lưu."
    )
    terminalreporter.write_line(
        "Lượt chạy này KHÔNG chứng minh được các ràng buộc ấy còn đúng."
    )
    terminalreporter.write_line("Bật lên:  docker compose up -d db")
    terminalreporter.write_line(
        f"Hoặc trỏ tay: TEST_DATABASE_URL={_POSTGRES_COMPOSE}"
    )


def nguoi_thu(*quyen: str, ten: str = "kt", **them) -> dict:
    """
    Dựng một người đăng nhập giả cho test API.

    Dùng với `app.dependency_overrides[routes.nguoi_da_dang_nhap]`. Đó là
    ĐIỂM GHI ĐÈ DUY NHẤT: `can_quyen()` trả closure mới mỗi lần gọi nên
    không ghi đè thẳng vào nó được.

    Gọi không đối số = người đã đăng nhập nhưng KHÔNG có quyền nào. Mặc
    định ấy có chủ ý: test muốn kiểm một endpoint thì phải nói ra endpoint
    ấy cần quyền gì, và câu nói ấy chính là tài liệu.

    `toan_quyen()` ở dưới dành cho test không quan tâm tới phân quyền.
    """
    nguoi = {
        "id": "00000000-0000-0000-0000-000000000001",
        "ten_dang_nhap": ten,
        "ho_ten": ten,
        "vai_tro": "nhan_vien",
        "khoa": False,
        "quyen": frozenset(quyen),
    }
    nguoi.update(them)
    return nguoi


def toan_quyen(ten: str = "qt", **them) -> dict:
    """Người có mọi quyền — tương đương vai trò `Quản trị`."""
    from agent.core.quyen import QUYEN

    return nguoi_thu(*QUYEN, ten=ten, vai_tro="quan_tri", **them)


@pytest.fixture
def csdl_kiem_thu():
    """
    Một CSDL RỖNG RIÊNG cho từng test, xoá sau khi xong.

    VÌ SAO KHÔNG DÙNG CHUNG MỘT CSDL
    --------------------------------
    Test migration phải chạy trên lược đồ trắng. Dùng chung thì test chạy
    trước để lại bảng và dữ liệu, và test sau xanh nhờ thứ nó không tự dựng —
    rồi đỏ khi có người chạy nó một mình. Đó là kiểu đỏ khiến người ta nghi
    ngờ bộ test thay vì nghi ngờ mã.

    Bỏ qua khi thiếu `TEST_DATABASE_URL`, nhưng CI LUÔN có nó — xem
    `tests/test_ci_co_postgres.py` và service postgres trong workflow. Nếu
    biến ấy biến mất khỏi CI thì test ở kia đỏ trước, nên việc bỏ qua ở đây
    không thể lặng lẽ thành vĩnh viễn.
    """
    url = dia_chi_csdl_kiem_thu()
    if not url:
        _DEM_BO_QUA["n"] += 1
        pytest.skip("chưa cấp TEST_DATABASE_URL cho integration PostgreSQL")

    import asyncpg

    goc = url.rpartition("/")[0]
    ten = f"kt_{uuid.uuid4().hex[:12]}"

    async def tao():
        conn = await asyncpg.connect(f"{goc}/postgres")
        try:
            await conn.execute(f'CREATE DATABASE "{ten}"')
        finally:
            await conn.close()

    async def xoa():
        conn = await asyncpg.connect(f"{goc}/postgres")
        try:
            await conn.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()", ten)
            await conn.execute(f'DROP DATABASE IF EXISTS "{ten}"')
        finally:
            await conn.close()

    asyncio.run(tao())
    try:
        yield f"{goc}/{ten}"
    finally:
        asyncio.run(xoa())


def duong_dan_con_song(duong: str) -> bool:
    """
    Đường dẫn còn sống: có thật, HOẶC có bản `.example` đi thay.

    Phải chấp nhận vế thứ hai vì repo cố ý không mang theo dữ liệu thật
    (`data/catalog.json`, `data/knowledge/`) — đòi chúng tồn tại là đòi
    đúng thứ đã quyết định không đưa lên, và test sẽ xanh trên máy đã cấu
    hình rồi đỏ trên mọi bản clone sạch.

    `.example` có thể nằm ở BẤT KỲ tầng nào của đường dẫn, không riêng tầng
    cuối. Cả hai dạng dưới đây đều hợp lệ và phải nhận cả hai:

        data/catalog.json                      -> data/catalog.example.json
        data/knowledge/chinh-sach.md           -> data/knowledge.example/chinh-sach.md

    Bỏ sót dạng thứ hai chính là cách bản đầu tiên của hàm này lọt lưới.
    """
    p = Path(duong.rstrip("/"))
    if (ROOT / p).exists():
        return True
    # Thử đổi từng tầng sang bản `.example`, từ tầng cuối ngược lên gốc.
    phan = list(p.parts)
    for i in range(len(phan) - 1, -1, -1):
        goc = Path(phan[i])
        thu = phan.copy()
        thu[i] = f"{goc.stem}.example{goc.suffix}"
        if (ROOT / Path(*thu)).exists():
            return True
    return False


# =====================================================================
#  App ĐẦY ĐỦ trên Postgres thật — cho test đầu-cuối và nghiệm thu
# =====================================================================
#
# Khác `csdl_kiem_thu` (chỉ cấp một CSDL trắng): fixture này dựng
# `agent.main.app` với lifespan thật — cùng thứ uvicorn dựng — để middleware,
# chốt đăng nhập, vault và mọi router đều có mặt. Hai lỗi từng lọt qua test
# router trần (callback Zalo OA chết ở middleware) và test kho giả
# (`merge_preview` nổ ở SQL) là lý do fixture này tồn tại.

import base64  # noqa: E402
import secrets  # noqa: E402
from uuid import UUID  # noqa: E402

GOC_WEB = "https://shop.test"


@pytest.fixture
def app_that(csdl_kiem_thu, monkeypatch):
    """
    `agent.main.app` trỏ vào CSDL kiểm thử, KHÔNG dựng vòng nền.

    Vòng nền (canh gác Meta, sao lưu, outbox worker…) gọi ra mạng và chạm
    những thứ ngoài phạm vi test này. `nen_chay_vong_nen` là chính cái khoá
    mà production dùng để chia vai tiến trình — dùng lại nó, không vá sâu.
    """
    from fastapi.testclient import TestClient

    from agent import db, runtime
    from agent.config import settings
    import agent.main as main

    khoa = base64.b64encode(secrets.token_bytes(32)).decode()
    monkeypatch.setattr(settings, "database_url", csdl_kiem_thu)
    monkeypatch.setattr(settings, "credential_master_keys", f"1:{khoa}")
    monkeypatch.setattr(settings, "credential_active_key_version", 1)
    monkeypatch.setattr(main, "nen_chay_vong_nen", lambda *a, **k: False)

    # Test khác có thể để lại pool trỏ CSDL khác. Lifespan chỉ tạo pool khi
    # `_pool is None`, nên phải xoá trước — nếu không test này chạy trên
    # CSDL của test trước và xanh nhờ dữ liệu không phải của mình.
    db._pool = None
    # Công tắc TOÀN CỤC bật, để thứ chặn agent là công tắc THEO KÊNH.
    runtime.STATE["enabled"] = True

    with TestClient(main.app) as khach:
        yield khach
    db._pool = None


async def _quan_tri(ten: str) -> tuple[UUID, str]:
    """Người thật + vai trò Quản trị + phiên. Trả (id, token)."""
    from agent import db

    nd = await db.fetchrow(
        "INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau_bam, ho_ten, vai_tro) "
        "VALUES ($1, 'x', $1, 'quan_tri') RETURNING id", ten)
    await db.execute(
        "INSERT INTO nguoi_dung_vai_tro (nguoi_dung_id, vai_tro_id) "
        "SELECT $1, id FROM vai_tro WHERE ten = 'Quản trị'", nd["id"])
    token = secrets.token_urlsafe(32)
    await db.execute(
        "INSERT INTO phien (token, nguoi_dung_id, het_han) "
        "VALUES ($1, $2, now() + interval '1 hour')", token, nd["id"])
    return nd["id"], token


