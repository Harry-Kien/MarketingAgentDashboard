"""
Vận chuyển GHN: canh đúng những chỗ nhánh gốc đã sai.

Nhánh `shipping` của cộng sự thêm 1341 dòng mã và KHÔNG một test nào — đo
được: `origin/main` 568 test, `origin/shipping` cũng 568. File này lấp chỗ đó,
và mỗi test ở đây tương ứng một lỗi CÓ THẬT đã tìm ra khi review.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest


# ===============================================================
#  LỖI 1 — địa chỉ không khớp thì gửi về Quận 1 TP.HCM
# ===============================================================

@pytest.mark.parametrize("dia_chi,phai_con", [
    ("12 Tran Phu, Phuong Hong Ha, TP Ha Long, Quang Ninh", "quang ninh"),
    ("88 Le Loi, Phuong Tan An, TP Tam Ky, Quang Nam", "quang nam"),
    ("5 Ly Thuong Kiet, Phuong 1, TP Dong Hoi, Quang Binh", "quang binh"),
    ("7 Hung Vuong, Phuong 5, TP Dong Ha, Quang Tri", "quang tri"),
    ("9 Quang Trung, Phuong Tran Phu, TP Quang Ngai, Quang Ngai", "quang ngai"),
])
def test_khong_bam_nat_ten_tinh_Quang(dia_chi, phai_con):
    """
    `.replace("quan","")` cắt cả chữ "quan" NẰM GIỮA từ khác.

    Đo được trên bản cũ:
        "TP Ha Long, Quang Ninh"  ->  "ha long, g ninh"
        "TP Tam Ky, Quang Nam"    ->  "tam ky, g nam"

    Năm tỉnh Quảng bị băm nát nên không bao giờ khớp quận, rồi rơi vào mặc
    định "Quận 1 TP.HCM" — hàng đi sai tỉnh mà không ai biết.
    """
    from agent.shipping.ghn import _norm

    assert phai_con in _norm(dia_chi)


def test_van_bo_tien_to_khi_no_dung_mot_minh():
    """Bỏ nhầm thì hỏng, nhưng không bỏ gì thì cũng không khớp được."""
    from agent.shipping.ghn import _norm

    ra = _norm("So 5 Nguyen Trai, Phuong Ben Thanh, Quan 1, TP Ho Chi Minh")
    assert "phuong" not in ra.split()
    assert "quan" not in ra.split()
    assert "ben thanh" in ra
    assert "ho chi minh" in ra


def test_khong_con_gia_tri_mac_dinh_Quan_1_o_bat_ky_dau():
    """
    1442 = Quận 1 HCM, 20102 = một phường trong đó.

    GHN định tuyến theo `to_district_id`, KHÔNG theo chữ trong `to_address`.
    Còn một dòng gán mặc định nào là còn đường cho kiện hàng đi nhầm tỉnh.
    """
    from agent.shipping import ghn

    ma = "\n".join(
        dong for dong in inspect.getsource(ghn).splitlines()
        if not dong.strip().startswith("#")
    )
    assert "1442" not in ma, "vẫn còn mặc định Quận 1 TP.HCM"
    assert "20102" not in ma, "vẫn còn mặc định phường của Quận 1"


def test_khong_ro_dia_chi_thi_TU_CHOI_tao_van_don(monkeypatch):
    from agent.shipping.ghn import GHNShippingProvider
    from agent.shipping.models import CreateWaybillRequest

    nha_xe = GHNShippingProvider(token="T", shop_id="1")

    async def khong_ra_gi(_dia_chi):
        return None, None

    monkeypatch.setattr(nha_xe, "_resolve_address", khong_ra_gi)
    kq = asyncio.run(nha_xe.tao_van_don(CreateWaybillRequest(
        ma_don="AS1", khach_ten="A", khach_sdt="0912345678",
        khach_dia_chi="cho nao do",
    )))

    assert kq.ok is False
    assert kq.can_nguoi_xac_nhan is True, "phải là việc hỏi lại khách, không phải lỗi kỹ thuật"


# ===============================================================
#  LỖI 2 — webhook mở toang
# ===============================================================

def test_chua_cau_hinh_bi_mat_thi_TU_CHOI(monkeypatch):
    """
    Bản cũ: `if secret:` — chưa cấu hình thì bỏ qua kiểm tra luôn.

    Cùng nguyên tắc đã áp ở `native_webhooks.doc_thach_thuc`: danh sách token
    rỗng thì TỪ CHỐI, không phải chấp nhận tất cả.
    """
    from agent.config import settings
    from agent.shipping.service import kiem_bi_mat_webhook

    monkeypatch.setattr(settings, "shipping_webhook_secret", "")
    cho_qua, _ = kiem_bi_mat_webhook({}, "bat-ky-gi")
    assert cho_qua is False


def test_khong_gui_bi_mat_thi_TU_CHOI(monkeypatch):
    """
    Bản cũ: `if sig:` — kẻ gọi chỉ cần KHÔNG gửi header là đi thẳng qua.

    Lỗ hổng thật: ai biết mã đơn đều đánh dấu được đơn "đã giao" hoặc "hoàn
    về" — mà hoàn về sẽ CỘNG HÀNG LẠI VÀO KHO dù hàng chưa quay lại.
    """
    from agent.config import settings
    from agent.shipping.service import kiem_bi_mat_webhook

    monkeypatch.setattr(settings, "shipping_webhook_secret", "BI-MAT-THAT")
    cho_qua, _ = kiem_bi_mat_webhook({}, "")
    assert cho_qua is False


def test_bi_mat_sai_thi_TU_CHOI(monkeypatch):
    from agent.config import settings
    from agent.shipping.service import kiem_bi_mat_webhook

    monkeypatch.setattr(settings, "shipping_webhook_secret", "BI-MAT-THAT")
    assert kiem_bi_mat_webhook({}, "doan-bua")[0] is False


def test_bi_mat_dung_thi_cho_qua(monkeypatch):
    from agent.config import settings
    from agent.shipping.service import kiem_bi_mat_webhook

    monkeypatch.setattr(settings, "shipping_webhook_secret", "BI-MAT-THAT")
    assert kiem_bi_mat_webhook({}, "BI-MAT-THAT")[0] is True
    assert kiem_bi_mat_webhook({"x-shipping-token": "BI-MAT-THAT"}, "")[0] is True


def test_so_sanh_bi_mat_khong_thoat_som():
    """
    So sánh chuỗi thường dừng ở byte đầu khác nhau — đủ để dò từng ký tự
    bằng cách đo thời gian phản hồi.
    """
    from agent.shipping import service

    assert "compare_digest" in inspect.getsource(service.kiem_bi_mat_webhook)


def test_duong_webhook_co_that():
    """
    Hãng vận chuyển không có phiên đăng nhập của ta, nên đường này nằm ngoài
    `/api/` và không bị middleware chặn — chính vì thế nó phải TỰ canh.
    """
    from agent.main import app

    assert "/webhook/shipping/{hang}" in set(app.openapi()["paths"])


# ===============================================================
#  LỖI 3 — mã trạng thái lạ lặng lẽ thành "đang giao"
# ===============================================================

def test_ma_la_tra_None_chu_khong_doan_dang_giao():
    """
    Bản cũ trả `DELIVERING` cho mọi mã không nhận ra. Một kiện `lost` sẽ hiện
    "đang giao" mãi mãi, và agent trả lời khách đúng như vậy.
    """
    from agent.shipping.base import anh_xa_trang_thai

    trang_thai, goc = anh_xa_trang_thai("XYZ_STATUS_2027")
    assert trang_thai is None
    assert goc == "XYZ_STATUS_2027", "phải giữ mã gốc cho người đọc"


@pytest.mark.parametrize("ma,mong_doi", [
    ("delivered", "delivered"),
    ("delivery_fail", "delivery_failed"),
    ("returned", "returned"),
    ("delivering", "delivering"),
    ("ready_to_pick", "delivering"),
    ("sorting", "delivering"),
])
def test_anh_xa_ma_quen_thuoc(ma, mong_doi):
    from agent.shipping.base import anh_xa_trang_thai

    trang_thai, _ = anh_xa_trang_thai(ma)
    assert trang_thai is not None
    assert trang_thai.value == mong_doi


@pytest.mark.parametrize("ma", [
    "lost", "damage", "waiting_to_return", "returning",
    "return_transporting", "return_sorting", "return_fail",
])
def test_hang_CHUA_ve_kho_thi_KHONG_duoc_hoan_kho(ma):
    """
    RETURNED kích hoạt CỘNG HÀNG LẠI VÀO KHO. Chỉ mã nghĩa là hàng đã về tới
    kho mới được xếp vào đó.

    Bản của cộng sự xếp `damage` và `lost` vào RETURNED — hàng vỡ và hàng mất
    được cộng trở lại số tồn. Kho báo có hàng trong khi kệ trống, rồi shop bán
    tiếp cái không tồn tại và phải gọi điện xin lỗi khách thứ hai.

    `waiting_to_return` và `return_transporting` cũng vậy: hàng còn trên xe
    của hãng, chưa nằm trên kệ.
    """
    from agent.shipping.base import anh_xa_trang_thai
    from agent.shipping.models import InternalShippingStatus

    trang_thai, _ = anh_xa_trang_thai(ma)
    assert trang_thai != InternalShippingStatus.RETURNED, (
        f"`{ma}` sẽ bị hoàn kho dù hàng chưa về tới kho"
    )


def test_nha_xe_KHONG_duoc_tu_ghi_de_map_status():
    """
    Lưới chặn mã lạ nằm ở lớp cơ sở. Nhà xe ghi đè là lưới thành mã chết.

    Đã xảy ra: tôi sửa `base.py` nhưng cả `ghn.py` lẫn `mock.py` đều có bản
    riêng trả `DELIVERING` cho mọi mã lạ, nên bản sửa không bao giờ chạy. Chỉ
    lộ ra khi chạy thử trọn vòng trên CSDL thật, không phải qua test đơn vị.
    """
    from agent.shipping.ghn import GHNShippingProvider
    from agent.shipping.mock import MockShippingProvider

    for lop in (GHNShippingProvider, MockShippingProvider):
        assert "map_status" not in vars(lop), (
            f"{lop.__name__} tự ghi đè map_status — lưới chặn mã lạ bị vô hiệu"
        )


def test_webhook_ma_la_KHONG_doi_trang_thai_don():
    """Mã không nhận ra thì giữ nguyên trạng thái cũ, gọi người."""
    from agent.shipping import service

    nguon = inspect.getsource(service.xu_ly_webhook_van_chuyen)
    assert "st_noi_bo is None" in nguon
    assert "can_nguoi_xem" in nguon


def test_delivery_fail_khong_bi_doc_thanh_da_giao():
    """
    "delivery_fail" chứa cả "deliver" lẫn "fail". Xét nhóm "đã giao" trước là
    báo giao thành công cho một đơn giao hỏng — sai theo hướng tệ nhất.
    """
    from agent.shipping.base import anh_xa_trang_thai

    assert anh_xa_trang_thai("delivery_fail")[0].value == "delivery_failed"


# ===============================================================
#  LỖI 4 — đơn CHỜ DUYỆT vẫn xuất kho được
# ===============================================================

def test_don_cho_duyet_khong_duoc_tao_van_don():
    """
    `cho_duyet` nghĩa là đơn vượt ngưỡng và đang đợi NGƯỜI xác nhận.

    Tạo vận đơn là hàng rời kho — nó đi vòng qua đúng cái chốt vừa dựng lên.
    """
    from agent.shipping import service

    nguon = inspect.getsource(service.tao_van_don_cho_don)
    assert 'trang_thai == "cho_duyet"' in nguon, "không thấy chốt chặn đơn chờ duyệt"


# ===============================================================
#  Mặc định an toàn và tính toàn vẹn
# ===============================================================

def test_mac_dinh_la_mock_khong_goi_mang():
    """Đổi sang `ghn` là hành động tốn tiền thật — phải do người chọn."""
    from agent.config import Settings

    assert Settings().shipping_provider == "mock"


def test_khong_doi_bo_nao_AI_sang_openai():
    """
    Nhánh gốc đổi ngầm `llm_provider` mặc định sang `openai` và model sang
    `gpt-4o-mini`. Bản cài mới nào cũng dính, và `OPENAI_API_KEY` trống thì
    agent chết hẳn. Đó là thay đổi không liên quan gì tới vận chuyển.
    """
    from agent.config import Settings

    mac_dinh = Settings()
    assert mac_dinh.llm_provider == "gemini"
    assert mac_dinh.model_chat.startswith("gemini")


def test_khong_co_token_ghn_thi_khong_tao_van_don():
    from agent.shipping.ghn import GHNShippingProvider
    from agent.shipping.models import CreateWaybillRequest

    kq = asyncio.run(GHNShippingProvider(token="").tao_van_don(
        CreateWaybillRequest(ma_don="AS1", khach_ten="A",
                             khach_sdt="0912345678", khach_dia_chi="x")))
    assert kq.ok is False


def test_thieu_shop_id_thi_noi_ro_chu_khong_de_GHN_tu_choi():
    """
    `ShopId` là BẮT BUỘC khi tạo vận đơn — nó cho GHN biết lấy hàng ở kho nào.

    Bản trước viết `if self._shop_id:` rồi bỏ header đi khi trống. Lời gọi
    vẫn đi, GHN trả về một lỗi của họ, và người vận hành đọc được câu khó
    hiểu thay vì "bạn quên điền GHN_SHOP_ID".

    Sai cấu hình phải nói ra bằng lời của mình, ở chỗ gần chỗ gây lỗi nhất.
    """
    from agent.shipping.ghn import GHNShippingProvider
    from agent.shipping.models import CreateWaybillRequest

    kq = asyncio.run(GHNShippingProvider(token="T", shop_id="").tao_van_don(
        CreateWaybillRequest(ma_don="AS1", khach_ten="A",
                             khach_sdt="0912345678", khach_dia_chi="x")))
    assert kq.ok is False
    assert "GHN_SHOP_ID" in kq.loi, "phải chỉ đúng tên biến còn thiếu"


def test_tra_cuu_danh_muc_KHONG_doi_shop_id():
    """
    Danh mục quận/phường là dữ liệu công khai của GHN, không thuộc shop nào.

    Đòi ShopId ở đây là chặn nhầm bước so khớp địa chỉ khi người dùng mới chỉ
    có token.
    """
    import inspect

    from agent.shipping import ghn

    nguon = inspect.getsource(ghn.GHNShippingProvider._resolve_address)
    assert "shop_id" not in nguon


def test_env_example_khai_du_bien_van_chuyen():
    """Không khai thì người cài mới không biết cần gì, và san_sang không kiểm được."""
    from pathlib import Path

    env = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8")
    for bien in ("SHIPPING_PROVIDER", "GHN_TOKEN", "GHN_SHOP_ID",
                 "SHIPPING_WEBHOOK_SECRET"):
        assert bien in env, f"thiếu {bien}"


def test_cot_van_chuyen_deu_co_trong_schema():
    """
    Mã đọc cột mà KHÔNG DDL nào tạo ra -> máy vừa clone NỔ.

    PHẢI soi cả `schema.sql` LẪN `migrations/versions/*.sql`
    ---------------------------------------------------------
    `db.init_db()` chạy baseline rồi `apply_all()` chạy migrations. Một cột
    khai trong migration là hoàn toàn hợp lệ.

    Bản đầu của test này chỉ đọc `schema.sql`, và tôi đã dựa vào nó để kết
    luận nhầm rằng bốn cột đang thiếu — trong khi chúng nằm ở migration 0006.
    Test soi thiếu chỗ thì nó không bảo vệ, nó gây hiểu lầm.
    """
    from pathlib import Path

    goc = Path(__file__).resolve().parents[1]
    ddl = (goc / "agent" / "schema.sql").read_text(encoding="utf-8")
    for f in sorted((goc / "agent" / "migrations" / "versions").glob("*.sql")):
        ddl += "\n" + f.read_text(encoding="utf-8")

    nguon = (goc / "agent" / "core" / "tools.py").read_text(encoding="utf-8")

    for cot in ("ma_van_don", "don_vi_van_chuyen", "trang_thai_giao_hang",
                "phi_van_chuyen", "ngay_du_kien_giao",
                "cap_nhat_van_chuyen_luc", "lich_su_giao_hang"):
        assert f"ADD COLUMN IF NOT EXISTS {cot}" in ddl, (
            f"cột `{cot}` không có DDL nào tạo ra"
        )

    # Tên cột CŨ phải biến mất khỏi câu SQL: giữ hai bộ tên cho cùng một khái
    # niệm là hai nguồn sự thật, và sớm muộn một nửa mã ghi vào bộ này còn
    # một nửa đọc từ bộ kia.
    cau = nguon.split("SELECT ma_don, trang_thai, trang_thai_giao_hang", 1)
    assert len(cau) == 2, "truy vấn vận chuyển không dùng tên cột mới"
    than = cau[1].split("FROM orders", 1)[0]
    for cu_ky in ("giao_cap_nhat_luc", "hang_van_chuyen", "ma_trang_thai_hang"):
        assert cu_ky not in than, f"SQL còn đọc cột cũ `{cu_ky}`"


def test_cot_cu_da_bi_XOA_han_khoi_csdl():
    """Cột mồ côi kèm CHECK ràng giá trị tiếng Việt sẽ TỪ CHỐI giá trị mới."""
    from pathlib import Path

    goc = Path(__file__).resolve().parents[1]
    mig = (goc / "agent" / "migrations" / "versions"
           / "0007_van_chuyen_ghn.sql").read_text(encoding="utf-8")

    for cu_ky in ("trang_thai_giao", "hang_van_chuyen", "ma_trang_thai_hang",
                  "giao_cap_nhat_luc"):
        assert f"DROP COLUMN IF EXISTS {cu_ky}" in mig, f"chưa xoá cột cũ {cu_ky}"

    # CHECK phải bỏ TRƯỚC khi xoá cột nó ràng, nếu không Postgres từ chối.
    assert mig.index("DROP CONSTRAINT") < mig.index("DROP COLUMN")
