"""
Xoá dữ liệu cá nhân phải có PHIẾU DUYỆT của người thứ hai.

VÌ SAO
------
`data_retention_jobs` có `requested_by` / `approved_by` và chốt "người tạo
không tự duyệt được" từ lâu, dashboard có hẳn một khối cho nó. Nhưng nút
xoá thật (`POST /api/pdpd/{sdt}/xoa`) chưa bao giờ hỏi tới bảng ấy: nó chỉ
đòi quyền `khach.xoa` và bắt gõ lại số điện thoại.

Nghĩa là quy trình duyệt chỉ canh việc ĐẾM, còn việc KHÔNG HOÀN TÁC ĐƯỢC
thì một người bấm là xong. Một chốt trông như chốt mà không khoá gì — tệ
hơn không có chốt, vì người vận hành đọc tiêu đề panel rồi tin rằng đã có
người thứ hai canh.

Bốn thứ được canh ở đây:

  1. Không có phiếu -> KHÔNG một câu lệnh xoá nào được chạy.
  2. Có phiếu -> chạy, và phiếu bị tiêu ngay (dùng một lần).
  3. Hỏng giữa chừng -> phiếu được trả lại, không bắt xin duyệt lại.
  4. Giành phiếu phải là MỘT câu lệnh — hai câu là hai người bấm cùng lúc
     cùng đi tiếp được.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from agent.core import du_lieu_ca_nhan as pdpd
from tests.erp_gia import chay


class DbGia:
    """Đủ để `tra_cuu` thấy có dữ liệu và `xoa` chạy hết các bước."""

    def __init__(self, *, phieu: dict | None, hong_o_buoc: str | None = None):
        self.phieu = phieu
        self.hong_o_buoc = hong_o_buoc
        self.cau: list[tuple[str, tuple]] = []
        self.nhat_ky: list[tuple[str, dict]] = []

    async def fetch(self, sql, *args):
        self.cau.append((sql, args))
        if "FROM orders" in sql:
            return [{"ma_don": "DH1", "khach_ten": "Khách", "khach_dia_chi": "HN",
                     "tong_tien": 100, "trang_thai": "moi",
                     "created_at": datetime.now(timezone.utc), "conversation_id": None}]
        return [{"id": uuid4(), "channel": "zalo", "customer_name": "Khách",
                 "msg_count": 3, "updated_at": datetime.now(timezone.utc)}]

    async def fetchrow(self, sql, *args):
        self.cau.append((sql, args))
        if "xoa_thuc_hien_luc = now()" in sql:
            return self.phieu
        if "INSERT INTO data_retention_jobs" in sql:
            return {"id": uuid4(), "status": "pending_approval"}
        return None

    async def execute(self, sql, *args):
        self.cau.append((sql, args))
        if self.hong_o_buoc and self.hong_o_buoc in sql:
            raise RuntimeError("CSDL rụng giữa chừng")
        return "DELETE 1"

    async def log_event(self, kind, **kw):
        self.nhat_ky.append((kind, kw))

    def sql_co(self, mau: str) -> bool:
        return any(mau in sql for sql, _ in self.cau)


PHIEU = {"id": uuid4(), "requested_by": uuid4(), "approved_by": uuid4()}


@pytest.fixture
def db_gia(monkeypatch):
    def dung(**kw):
        d = DbGia(**kw)
        monkeypatch.setattr(pdpd, "db", d)

        async def _ho_so(sdt):
            return 0

        monkeypatch.setattr(pdpd.ho_so_khach, "xoa", _ho_so)
        return d

    return dung


# =====================================================================
#  1. Không có phiếu thì không xoá được gì
# =====================================================================

def test_khong_co_phieu_thi_nem_va_khong_xoa_gi(db_gia):
    d = db_gia(phieu=None)

    with pytest.raises(pdpd.ChuaDuyet):
        chay(pdpd.xoa("0967627336"))

    assert not d.sql_co("DELETE FROM conversations"), "đã xoá hội thoại khi chưa ai duyệt"
    assert not d.sql_co("UPDATE orders SET"), "đã đụng vào đơn hàng khi chưa ai duyệt"
    assert d.nhat_ky == [], "ghi nhật ký 'đã xoá' cho một lần xoá không xảy ra"


def test_loi_chua_duyet_chi_duong_di_tiep(db_gia):
    """Báo lỗi mà không nói phải làm gì thì người ta đi tìm đường vòng."""
    db_gia(phieu=None)
    with pytest.raises(pdpd.ChuaDuyet) as loi:
        chay(pdpd.xoa("0967627336"))
    assert "Xin duyệt xoá" in str(loi.value)


def test_chua_duyet_khong_phai_valueerror():
    """
    Route đổi `ValueError` thành 422 "nhập sai". Người vận hành gõ đúng hết,
    chỉ là chưa có người duyệt — 422 đẩy họ đi soi lại ô nhập.
    """
    assert not issubclass(pdpd.ChuaDuyet, ValueError)


# =====================================================================
#  2. Có phiếu thì chạy, và phiếu bị tiêu
# =====================================================================

def test_co_phieu_thi_xoa_va_tieu_phieu(db_gia):
    d = db_gia(phieu=PHIEU)

    kq = chay(pdpd.xoa("0967627336", ly_do="khách yêu cầu"))

    assert d.sql_co("DELETE FROM conversations")
    assert d.sql_co("UPDATE orders SET")
    # Phiếu bị đánh dấu đã dùng NGAY trong câu giành, không phải câu riêng
    # chạy sau khi xoá xong — xoá xong mới đánh dấu thì một lần hỏng ở giữa
    # để lại phiếu còn hiệu lực cho một lần xoá nữa.
    assert d.sql_co("xoa_thuc_hien_luc = now()")
    assert kq["phieu_duyet"] == str(PHIEU["id"])


def test_nhat_ky_ghi_ai_xin_ai_duyet(db_gia):
    """
    Bằng chứng "đã xoá" mà không kèm "có người thứ hai đồng ý" thì không
    trả lời được đúng câu hỏi được đặt ra khi có tranh chấp.
    """
    d = db_gia(phieu=PHIEU)
    chay(pdpd.xoa("0967627336"))

    kind, chi_tiet = next(x for x in d.nhat_ky if x[0] == "pdpd.xoa_du_lieu")
    assert chi_tiet["phieu_duyet"] == str(PHIEU["id"])
    assert chi_tiet["nguoi_xin"] == str(PHIEU["requested_by"])
    assert chi_tiet["nguoi_duyet"] == str(PHIEU["approved_by"])
    # Và vẫn không được ghi số thật vào nhật ký.
    assert "0967627336" not in str(chi_tiet)


# =====================================================================
#  3. Hỏng giữa chừng thì trả phiếu
# =====================================================================

def test_hong_giua_chung_thi_tra_phieu(db_gia):
    d = db_gia(phieu=PHIEU, hong_o_buoc="DELETE FROM conversations")

    with pytest.raises(RuntimeError):
        chay(pdpd.xoa("0967627336"))

    assert d.sql_co("SET xoa_thuc_hien_luc = NULL"), (
        "phiếu bị tiêu mất vì máy hỏng — người vận hành phải đi xin duyệt "
        "lại cho đúng việc vừa được duyệt xong"
    )


# =====================================================================
#  4. Giành phiếu phải chống được hai người bấm cùng lúc
# =====================================================================

def test_gianh_phieu_la_mot_cau_lenh_nguyen_tu():
    src = inspect.getsource(pdpd._gianh_phieu_duyet)
    assert "FOR UPDATE" in src and "SKIP LOCKED" in src, (
        "tìm phiếu rồi mới cập nhật ở câu thứ hai thì hai người bấm Xoá cùng "
        "lúc sẽ cùng tìm thấy MỘT phiếu và cùng được đi tiếp"
    )
    assert src.count("await db.") == 1, "giành phiếu phải gọn trong một lời gọi CSDL"


def test_chot_nam_trong_loi_khong_nam_o_route():
    """
    Chốt đặt trên đường đi thì mỗi đường mới lại là một lần phải nhớ. Quên
    một lần là phơi ra, không ai báo.
    """
    assert "_gianh_phieu_duyet" in inspect.getsource(pdpd.xoa)


# =====================================================================
#  5. Phiếu không được giữ lại chính số vừa hứa xoá
# =====================================================================

def test_phieu_luu_van_tay_chu_khong_luu_so(db_gia):
    d = db_gia(phieu=None)
    chay(pdpd.xin_duyet_xoa("0967627336", ly_do="khách yêu cầu", nguoi_id=uuid4()))

    sql, tham_so = next((s, a) for s, a in d.cau if "INSERT INTO data_retention_jobs" in s)
    # Hai ô THẬT SỰ được ghi xuống cột: dấu vân tay và dạng che. Tham số còn
    # lại chỉ để tra contact, không vào dòng nào.
    van_tay, che = tham_so[3], tham_so[4]
    assert sql.count("$") == 5, "đổi số tham số thì phải soi lại ô nào được ghi"
    for o in (van_tay, che):
        assert "967627336" not in o, (
            "phiếu ở lại bảng vĩnh viễn làm bằng chứng — lưu số thật vào đó "
            "là sau khi 'đã xoá', số vừa hứa xoá vẫn nằm nguyên trong CSDL"
        )
    assert van_tay == pdpd._van_tay_phieu("0967627336")


def test_hai_nhat_ky_dung_cung_mot_dau_van_tay(db_gia):
    """
    Người đi soát nối "ai xin xoá" với "đã xoá" bằng dấu vân tay. Hai dấu
    khác nhau cho cùng một người là nhật ký không trả lời được đúng câu hỏi
    nó sinh ra để trả lời — mà lại trông như đầy đủ.
    """
    d = db_gia(phieu=PHIEU)
    chay(pdpd.xin_duyet_xoa("0967627336", ly_do="khách yêu cầu", nguoi_id=uuid4()))
    chay(pdpd.xoa("0967627336"))

    dau = {k: v["dau_van_tay"] for k, v in d.nhat_ky}
    assert dau["pdpd.xin_duyet_xoa"] == dau["pdpd.xoa_du_lieu"]


def test_van_tay_khong_doi_theo_cach_viet_so():
    a = pdpd._van_tay_phieu("0967627336")
    for cach in ("+84967627336", "84.967.627.336", "0967 627 336", "967627336"):
        assert pdpd._van_tay_phieu(cach) == a, (
            f"{cach!r} ra dấu vân tay khác — phiếu duyệt cho số này sẽ không "
            "khớp lúc xoá số kia, dù là một người"
        )


def test_so_che_van_du_de_nguoi_duyet_biet_duyet_cho_ai():
    che = pdpd.che_sdt("0967627336")
    assert "0967627336" != che and "***" in che
    assert che.startswith("0967") and che.endswith("36")


# =====================================================================
#  6. Hồ sơ CRM — nơi lưu bị bỏ quên lâu nhất
# =====================================================================
#
# `xoa()` từng chạm đơn hàng, hội thoại, hồ sơ ghi nhớ và ERP — KHÔNG chạm
# `contacts`. Sau khi hệ thống báo "đã xoá" và ghi nhật ký tuân thủ, tên
# khách, số, email, ghi chú nhân viên viết về họ, nhãn và danh tính từng
# kênh vẫn còn nguyên. Và "Chạy đếm" của phiếu duyệt lại đếm ĐÚNG những
# bảng ấy — đếm thứ sẽ không bị xoá.

def test_xoa_cham_toi_ho_so_crm(db_gia):
    d = db_gia(phieu=PHIEU)
    chay(pdpd.xoa("0967627336"))

    assert d.sql_co("DELETE FROM contact_notes"), "ghi chú nhân viên viết về khách vẫn còn"
    assert d.sql_co("DELETE FROM contact_tags"), "nhãn gắn cho khách vẫn còn"
    assert d.sql_co("UPDATE contact_points SET"), "danh tính trên từng kênh vẫn còn"
    assert d.sql_co("UPDATE contacts SET"), "hồ sơ khách vẫn giữ tên và số"


def test_don_dong_y_giu_dong_bo_noi_dung():
    """
    Dòng đồng ý là bằng chứng đã từng được phép nhắn — xoá đi là tự bỏ căn
    cứ pháp lý của mình. Nhưng `evidence` có thể chứa chính số vừa hứa xoá.
    """
    src = inspect.getsource(pdpd._xoa_ho_so_crm)
    assert "DELETE FROM contact_consents" not in src
    assert "UPDATE contact_consents SET evidence" in src


def test_khong_giu_lai_khoa_nhan_ra_nguoi_cu():
    """
    Giữ `external_user_id` là giữ đúng thứ dùng để nhận ra người ấy ở lần
    nhắn sau — xoá mà vẫn nhận ra nhau thì không phải đã quên.
    """
    src = inspect.getsource(pdpd._xoa_ho_so_crm)
    assert "external_user_id = 'an-danh:'" in src


def test_ho_so_da_gop_khong_lam_gay_ca_lan_xoa():
    """
    `contacts_check` bắt trạng thái khác 'merged' phải có `merged_into` rỗng.
    Quên ô ấy thì câu UPDATE ném, và ném ở đây là hỏng giữa chừng một việc
    không hoàn tác được.
    """
    assert "merged_into = NULL" in inspect.getsource(pdpd._xoa_ho_so_crm)


def test_tra_cuu_noi_ca_ho_so_crm(db_gia):
    """
    Điều 9.1.c hỏi "hệ thống giữ gì". Trả lời thiếu hồ sơ CRM là trả lời sai,
    và người vận hành duyệt một lần xoá mà không biết những gì sẽ đi theo.
    """
    d = db_gia(phieu=None)
    kq = chay(pdpd.tra_cuu("0967627336"))
    assert "ho_so_khach" in kq and "so_ho_so" in kq
    assert d.sql_co("FROM contacts c")


# =====================================================================
#  7. Một người có quyền = phiếu treo vĩnh viễn, và phải nói ra
# =====================================================================

def test_dem_nguoi_duyet_tinh_ca_vai_tro_quan_tri():
    """
    Vai trò `Quản trị` nhận toàn bộ danh mục quyền tính từ MÃ chứ không từ
    `vai_tro_quyen`. Đếm theo bảng ấy thôi thì ra 0 ở đúng hệ thống đang có
    quản trị viên — một cảnh báo sai, và cảnh báo sai thì người ta tắt đi.
    """
    src = inspect.getsource(pdpd.so_nguoi_duyet_duoc)
    assert "Quản trị" in src and "he_thong" in src
    assert "NOT n.khoa" in src, "tài khoản đã khoá thì duyệt gì được"


def test_trang_thai_phieu_luon_kem_so_nguoi_duyet(db_gia):
    d = db_gia(phieu=None)
    kq = chay(pdpd.trang_thai_phieu("0967627336"))
    assert "so_nguoi_duyet_duoc" in kq, (
        "không kèm thì giao diện không cảnh báo được, và phiếu treo im lặng"
    )
    assert d.sql_co("khach.xoa")
