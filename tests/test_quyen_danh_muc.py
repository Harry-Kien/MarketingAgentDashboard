"""
Danh mục quyền, và chốt bắt route chưa khai quyền.

Chốt này là lý do khối A tồn tại: nó bắt endpoint ra đời mà không ai canh.
Đó là loại hỏng im lặng nguy hiểm nhất ở đây — không nổ, không ghi nhật ký,
và chỉ lộ ra vào đúng ngày có người dùng sai quyền.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.core import quyen  # noqa: E402


def test_ma_quyen_dung_dinh_dang():
    """`nhom.hanh_dong`, chữ thường, không dấu — để nhóm được trên dashboard."""
    for ma in quyen.QUYEN:
        assert ma == ma.lower(), ma
        assert ma.count(".") == 1, ma
        nhom, hanh_dong = ma.split(".")
        assert nhom and hanh_dong, ma
        assert ma.replace(".", "_").isidentifier(), ma


def test_moi_quyen_co_nhan_tieng_viet():
    """Nhãn hiện trên màn cấp quyền. Thiếu nhãn là một ô tick không ai hiểu."""
    for ma, nhan in quyen.QUYEN.items():
        assert nhan.strip(), ma
        assert nhan[0].isupper(), f"{ma}: nhãn nên bắt đầu bằng chữ hoa"


def test_duyet_route_phai_di_de_quy():
    """
    ĐÂY LÀ TEST QUAN TRỌNG NHẤT FILE NÀY.

    FastAPI bản đang dùng gói mỗi router đã `include_router` vào một
    `_IncludedRouter`; route thật nằm trong `.original_router`. Duyệt phẳng
    `app.routes` cho 7 route thay vì 166 — và chốt ở dưới sẽ báo "mọi route
    đã khai quyền" trong khi 159 route chưa khai.

    Xanh giả. Không ai đi kiểm lại một dấu xanh.
    """
    from agent.main import app

    assert len(list(quyen.moi_route(app.routes))) >= 160


def test_mien_tru_khong_tro_vao_route_da_chet():
    """
    Miễn trừ trỏ vào đường dẫn không còn tồn tại là rác vô hại HÔM NAY.
    Ngày mai có người thêm lại đúng đường dẫn ấy và nó ra đời không được
    canh — im lặng.
    """
    from agent.main import app

    that = {
        (pt, getattr(r, "path", ""))
        for r in quyen.moi_route(app.routes)
        for pt in (getattr(r, "methods", None) or set())
    }
    chet = {mt for mt in quyen.MIEN_TRU if mt not in that}
    assert not chet, f"Miễn trừ trỏ vào route đã chết: {sorted(chet)}"


def test_khong_con_duong_lui_bo_qua_tam():
    """
    Trong lúc dựng lớp quyền đã từng có `DANH_SACH_HOAN` để thu nhỏ dần.
    Giữ lại nó sau khi xong là giữ đúng cái lỗ mà cả lớp này sinh ra để bịt:
    một chỗ để nhét route mới vào cho khỏi phải nghĩ.
    """
    import inspect

    assert not hasattr(quyen, "DANH_SACH_HOAN")
    assert "hoan" not in inspect.signature(quyen.kiem_moi_route_co_quyen).parameters


def test_moi_route_deu_da_khai_quyen():
    """Chốt chính, và là lý do cả khối A tồn tại."""
    from agent.main import app

    quyen.kiem_moi_route_co_quyen(app)


def test_chot_that_su_chan_route_quen_khai_quyen():
    """
    Vế còn thiếu: test ở trên khẳng định app HIỆN TẠI qua được chốt. Nhưng
    một hàm kiểm luôn trả về "không thiếu gì" cũng qua được đúng như vậy.

    Ở đây thêm một route quên khai quyền và đòi chốt phải NÉM. Không có test
    này thì một lỗi trong `kiem_moi_route_co_quyen` biến cả lớp bảo vệ thành
    trang trí, và mọi dấu xanh ở trên vẫn xanh.
    """
    import pytest
    from fastapi import FastAPI

    app_thu = FastAPI()

    @app_thu.get("/api/_route_quen_khai_quyen")
    async def quen():
        return {}

    with pytest.raises(RuntimeError) as loi:
        quyen.kiem_moi_route_co_quyen(app_thu)
    assert "_route_quen_khai_quyen" in str(loi.value)


def test_khoi_dong_that_su_goi_chot():
    """
    Test ở trên gọi hàm kiểm THAY MẶT máy chủ. Nếu `main.py` không gọi nó
    thì test vẫn xanh trong khi máy chủ thật vẫn lên với route chưa canh —
    đúng nghĩa xanh giả.
    """
    noi_dung = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert "quyen.kiem_moi_route_co_quyen(app)" in noi_dung

    # Và phải gọi SAU dòng include_router cuối. Gọi trước là quét một app
    # chưa có route nào rồi báo xanh.
    vt_chot = noi_dung.index("quyen.kiem_moi_route_co_quyen(app)")
    vt_include = noi_dung.rindex("app.include_router(")
    assert vt_chot > vt_include, "chốt phải đứng sau mọi include_router"


def test_khong_con_bat_buoc_quan_tri():
    """
    Xoá hẳn, không giữ làm bí danh.

    Nó từng canh 73 endpoint với bảy nhóm quyền khác nhau, nên một bí danh
    trỏ vào bất cứ quyền đơn lẻ nào cũng cấp sai hoặc chặn sai ở phần lớn
    chỗ còn lại — và sai theo kiểu CHẠY ĐƯỢC.

    Xoá hẳn còn là hỏng-đóng: điểm gọi nào còn sót thì `NameError` lúc
    import, máy chủ không lên.
    """
    from agent.api import routes

    assert not hasattr(routes, "bat_buoc_quan_tri")


def test_khong_cho_nao_quyet_dinh_quyen_bang_cot_vai_tro():
    """
    Cột `nguoi_dung.vai_tro` giữ lại làm nhãn hiển thị, nhưng thôi quyết
    định quyền. Còn một chỗ so sánh nó là còn hai nguồn sự thật, và nguồn
    ít người đọc hơn sẽ mục đi.
    """
    import re

    vi_pham = []
    for tep in (ROOT / "agent").rglob("*.py"):
        if tep.name == "xac_thuc.py":       # nơi định nghĩa VAI_TRO hợp lệ
            continue
        for i, dong in enumerate(tep.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'vai_tro["\']?\]?\s*==\s*["\']quan_tri', dong):
                vi_pham.append(f"{tep.relative_to(ROOT)}:{i}")
    assert not vi_pham, f"Còn quyết định quyền bằng vai_tro: {vi_pham}"


# Quyền chưa có chỗ dùng.
#
# Trong A1 tập này có `khach.giao` — quyền ấy chỉ có endpoint khi A2 dựng
# xong việc giao khách. A2 đã xong, nên tập phải RỖNG.
#
# Giữ hằng lại thay vì xoá: lần sau có ai thêm một quyền "để dành cho bản
# sau", họ sẽ thấy đúng chỗ để khai nó — kèm áp lực phải dọn, vì tên hằng
# nói rõ đây là nợ chứ không phải chỗ đậu.
QUYEN_CHUA_DUNG: set[str] = set()


def test_moi_quyen_deu_co_it_nhat_mot_route_dung():
    """
    Bắt quyền chết.

    Quyền chết làm màn cấp quyền hiện một ô tick không có tác dụng gì —
    người quản trị tick vào, tin là đã cấp, và không có gì phản hồi rằng họ
    vừa làm một việc vô nghĩa.
    """
    from agent.main import app

    da_dung: set[str] = set()
    for r in quyen.moi_route(app.routes):
        phu_thuoc = getattr(getattr(r, "dependant", None), "dependencies", ())
        for x in phu_thuoc:
            da_dung.update(getattr(x.call, "quyen_yeu_cau", ()) or ())

    # Hai quyền `xem_tat_ca` không gắn vào endpoint: chúng được đọc trong
    # `_scope()` / `_user_scope()` để dựng mệnh đề WHERE, chứ không phải để
    # mở cửa một đường nào. Khai tường minh ở đây thay vì nới lỏng phép
    # kiểm — nới lỏng là bỏ luôn khả năng bắt quyền chết.
    doc_trong_truy_van = {"hoi_thoai.xem_tat_ca", "khach.xem_tat_ca",
                          "cong_viec.xem_tat_ca"}
    chet = set(quyen.QUYEN) - da_dung - doc_trong_truy_van - QUYEN_CHUA_DUNG
    assert not chet, f"Quyền không có chỗ dùng: {sorted(chet)}"


def test_quyen_doc_trong_truy_van_that_su_duoc_doc():
    """
    Vế còn lại của test trên: hai quyền `xem_tat_ca` được miễn khỏi phép
    kiểm "có endpoint dùng", nên phải có phép kiểm riêng — nếu không, miễn
    trừ ấy chính là chỗ để quyền chết nấp.
    """
    contacts = (ROOT / "agent" / "api" / "contacts.py").read_text(encoding="utf-8")
    inbox = (ROOT / "agent" / "api" / "inbox.py").read_text(encoding="utf-8")
    viec = (ROOT / "agent" / "core" / "cong_viec.py").read_text(encoding="utf-8")
    assert "khach.xem_tat_ca" in contacts
    assert "hoi_thoai.xem_tat_ca" in inbox
    assert "cong_viec.xem_tat_ca" in viec


def test_migration_khong_nhac_quyen_da_bien_mat():
    """
    Quyền bị xoá khỏi danh mục ở bản sau mà migration vẫn gõ tên nó thì vai
    trò nạp sẵn cấp một thứ không tồn tại — im lặng, và người quản trị không
    hiểu vì sao nhân viên mất đúng màn đó.
    """
    import re

    from agent.migrations.runner import VERSIONS_DIR

    for sql in VERSIONS_DIR.glob("*.sql"):
        noi_dung = sql.read_text(encoding="utf-8")
        # CHỈ soi migration thật sự ghi vào `vai_tro_quyen`. Soi hết mọi
        # migration là bắt nhầm: `0015` có chuỗi 'cong_cu.goi' — một LOẠI SỰ
        # KIỆN, trùng hình dạng `nhom.hanh_dong` nhưng không phải quyền.
        if "vai_tro_quyen" not in noi_dung:
            continue
        for ma in re.findall(r"'([a-z_]+\.[a-z_]+)'", noi_dung):
            assert ma in quyen.QUYEN, f"{sql.name} nhắc quyền đã biến mất: {ma}"
