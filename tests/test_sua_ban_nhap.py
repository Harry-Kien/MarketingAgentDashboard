"""
Sửa bản nháp AI trước khi gửi cho khách.

VÌ SAO GIỮ BẢN GỐC

Cột `confidence` và `grounded` trên một dòng `messages` là số đo của bản AI
viết. Nếu người sửa ghi đè `content` mà không giữ lại gì, những con số ấy
gắn vào câu do NGƯỜI viết — bộ đo chất lượng agent khi ấy chấm điểm cho văn
của người, và điểm càng đẹp khi agent càng viết dở. Đúng kiểu XANH GIẢ.

VÌ SAO SOI CỤM CẤM QUẢNG CÁO Ở ĐÂY

`respond()` chặn agent nói "chữa khỏi", "trị dứt điểm". Người trong nhà gõ
tay thì không đi qua chốt nào — cùng đúng lỗ hổng mà ô mô tả plugin đã phải
bịt. Ở đây CẢNH BÁO chứ không chặn: người bấm là người chịu trách nhiệm,
nhưng phải thấy trước khi tin rời đi, và phải để lại dấu vết.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def chay(coro):
    return asyncio.run(coro)


def _nhap(**doi):
    """Một dòng `messages` là bản nháp hợp lệ; `doi` để bẻ từng trường."""
    hang = {
        "id": uuid.uuid4(),
        "conversation_id": uuid.uuid4(),
        "role": "agent",
        "content": "Dạ bên em có ạ.",
        "delivered": False,
        "delivery_status": "draft",
        "noi_dung_goc": None,
    }
    hang.update(doi)
    return hang


# ---------------------------------------------------------------
#  1. Phép kiểm thuần — không CSDL, không mạng
# ---------------------------------------------------------------

def test_nhap_hop_le_thi_tra_ve_noi_dung_da_cat_khoang_trang():
    from agent.api.routes import kiem_sua_nhap

    assert kiem_sua_nhap(_nhap(), "  Dạ chi nhánh mở 8h ạ.  ") == "Dạ chi nhánh mở 8h ạ."


def test_tin_da_gui_thi_khong_sua_duoc():
    """Sửa một tin đã tới tay khách là sửa quá khứ — khách vẫn đọc bản cũ."""
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="đã gửi"):
        kiem_sua_nhap(_nhap(delivered=True, delivery_status="sent"), "nội dung mới hợp lệ")


def test_tin_cua_khach_khong_sua_duoc():
    """Đường này chỉ dành cho bản nháp của AI, không phải mọi dòng messages."""
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="bản nháp"):
        kiem_sua_nhap(_nhap(role="customer"), "nội dung mới hợp lệ")


def test_tin_nhan_vien_khong_sua_duoc():
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="bản nháp"):
        kiem_sua_nhap(_nhap(role="staff"), "nội dung mới hợp lệ")


def test_khong_co_dong_nao_thi_bao_khong_tim_thay():
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="[Kk]hông tìm thấy"):
        kiem_sua_nhap(None, "nội dung mới hợp lệ")


def test_noi_dung_chi_co_khoang_trang_bi_tu_choi():
    """Gửi một tin trắng cho khách là im lặng có hình dạng một câu trả lời."""
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="trống"):
        kiem_sua_nhap(_nhap(), "   \n\t  ")


def test_noi_dung_qua_dai_bi_tu_choi():
    """Bằng đúng trần của ô nhân viên gõ tay — cùng một đường ra, cùng một trần."""
    from agent.api.routes import LoiSuaNhap, kiem_sua_nhap

    with pytest.raises(LoiSuaNhap, match="4000"):
        kiem_sua_nhap(_nhap(), "a" * 4001)


# ---------------------------------------------------------------
#  2. Cụm cấm quảng cáo — cảnh báo, không chặn
# ---------------------------------------------------------------

def test_cum_cam_bi_bat_ke_ca_khi_xuong_dong_cat_doi():
    """
    Người gõ xuống dòng giữa cụm cấm thì bản gốc không khớp gì cả; gộp hết
    khoảng trắng lại thì một mệnh đề phủ định nuốt mất cụm ở vế sau. Soi
    một dạng là chấp nhận một kiểu lọt im lặng — phải soi cả hai.
    """
    from agent.core.cham_mot_luot import tu_cam_hai_dang

    assert tu_cam_hai_dang("Kem này chữa\nkhỏi mụn nhé") != []
    assert tu_cam_hai_dang("Kem này chữa khỏi mụn nhé") != []


def test_cau_binh_thuong_khong_bi_bao_dong_gia():
    from agent.core.cham_mot_luot import tu_cam_hai_dang

    assert tu_cam_hai_dang("Dạ chi nhánh Thủ Đức mở cửa 9h đến 20h ạ.") == []


def test_goi_ky_nang_dung_chung_mot_bo_soi_cum_cam():
    """
    Hai bản sao của phép soi này thì sớm muộn lệch nhau, và khi ấy hướng dẫn
    gói bị chặn một kiểu, tin người sửa lọt một kiểu.
    """
    nguon = (ROOT / "agent" / "ky_nang" / "goi.py").read_text(encoding="utf-8")
    assert "tu_cam_hai_dang" in nguon, "goi.py phải dùng chung hàm, không tự gộp khoảng trắng"


# ---------------------------------------------------------------
#  3. Ghi xuống CSDL — CSDL giả ghi lại SQL
# ---------------------------------------------------------------

class _CSDL:
    def __init__(self, hang):
        self.hang = hang
        self.sql: list[tuple[str, tuple]] = []
        self.su_kien: list[dict] = []

    async def fetchrow(self, sql, *a):
        return self.hang

    async def execute(self, sql, *a):
        self.sql.append((" ".join(sql.split()), a))
        return "UPDATE 1"

    async def log_event(self, kind, **chi_tiet):
        self.su_kien.append({"kind": kind, **chi_tiet})


class _Queued:
    job_id = uuid.uuid4()
    message_id = uuid.uuid4()
    duplicate = False


class _Outbound:
    """Bắt lấy ĐÚNG chuỗi chữ được đẩy ra outbox."""

    da_gui: list[str] = []

    def __init__(self, *a, **k):
        pass

    async def queue_existing_text(self, *, conversation_id, message_id, text, idempotency_key):
        _Outbound.da_gui.append(text)
        return _Queued()


def _dung_csdl(monkeypatch, hang):
    from agent.api import routes

    gia = _CSDL(hang)
    monkeypatch.setattr(routes.db, "fetchrow", gia.fetchrow)
    monkeypatch.setattr(routes.db, "execute", gia.execute)
    monkeypatch.setattr(routes.db, "log_event", gia.log_event)
    monkeypatch.setattr(routes, "OutboundService", _Outbound)
    _Outbound.da_gui = []
    return gia


def test_sua_roi_duyet_thi_outbox_nhan_noi_dung_MOI(monkeypatch):
    from agent.api import routes

    _dung_csdl(monkeypatch, _nhap(content="Bản AI viết."))
    chay(routes._queue_approved_draft(uuid.uuid4(), noi_dung="Bản người sửa.", boi="kien"))

    assert _Outbound.da_gui == ["Bản người sửa."], "outbox phải nhận bản đã sửa, không phải bản AI"


def test_ban_goc_duoc_giu_lai_va_ghi_ten_nguoi_sua(monkeypatch):
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap(content="Bản AI viết."))
    chay(routes._queue_approved_draft(uuid.uuid4(), noi_dung="Bản người sửa.", boi="kien"))

    ghi = [s for s in gia.sql if "UPDATE messages" in s[0]]
    assert ghi, "phải có một câu UPDATE messages"
    sql, tham_so = ghi[0]
    assert "sua_boi" in sql and "sua_luc" in sql
    # Bản AI được cất bằng chính câu SQL (`noi_dung_goc = ... content`), không
    # phải bằng cách đọc lên rồi ghi xuống: đọc-rồi-ghi là hai lượt, và giữa
    # hai lượt ấy có chỗ cho một lần sửa khác chen vào ghi đè.
    assert "content" in sql.split("SET", 1)[1].split("WHERE")[0], (
        "noi_dung_goc phải lấy từ content ngay trong câu UPDATE"
    )
    assert "kien" in tham_so, "phải ghi ai sửa"


def test_sua_lan_hai_khong_ghi_de_ban_AI_dau_tien(monkeypatch):
    """
    `noi_dung_goc` là bản AI, không phải "bản trước đó". Ghi đè ở lần sửa thứ
    hai là mất bản AI vĩnh viễn mà không ai biết.
    """
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap(content="Bản sửa lần một.", noi_dung_goc="Bản AI viết."))
    chay(routes._queue_approved_draft(uuid.uuid4(), noi_dung="Bản sửa lần hai.", boi="kien"))

    sql = [s for s in gia.sql if "UPDATE messages" in s[0]][0][0]
    assert "coalesce(noi_dung_goc" in sql.lower(), (
        "phải giữ noi_dung_goc cũ nếu đã có, ví dụ bằng coalesce"
    )


def test_duyet_khong_kem_noi_dung_giu_nguyen_hanh_vi_cu(monkeypatch):
    """Nút 'Duyệt và gửi' cũ không gửi body — đường ấy phải chạy y như trước."""
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap(content="Bản AI viết."))
    chay(routes._queue_approved_draft(uuid.uuid4()))

    assert _Outbound.da_gui == ["Bản AI viết."]
    assert not [s for s in gia.sql if "UPDATE messages" in s[0]], (
        "không sửa thì không được đụng vào dòng messages"
    )


def test_noi_dung_sai_thi_KHONG_ghi_gi_va_KHONG_gui(monkeypatch):
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap())
    with pytest.raises(routes.LoiSuaNhap):
        chay(routes._queue_approved_draft(uuid.uuid4(), noi_dung="   ", boi="kien"))

    assert gia.sql == [] and _Outbound.da_gui == []


# ---------------------------------------------------------------
#  4. Cảnh báo trước khi gửi, và dấu vết khi người bấm bỏ qua
# ---------------------------------------------------------------

def test_cum_cam_thi_dung_lai_hoi_truoc_khi_gui(monkeypatch):
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap())
    with pytest.raises(routes.CanXacNhanQuangCao) as e:
        chay(routes._queue_approved_draft(
            uuid.uuid4(), noi_dung="Kem này chữa khỏi mụn nhé chị.", boi="kien"))

    assert e.value.cum, "phải nói rõ cụm nào bị bắt"
    assert _Outbound.da_gui == [], "chưa xác nhận thì tin KHÔNG được rời đi"
    assert gia.sql == []


def test_xac_nhan_roi_thi_gui_va_de_lai_dau_vet(monkeypatch):
    """Người có quyền bỏ qua cảnh báo — nhưng không được bỏ qua trong im lặng."""
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap())
    chay(routes._queue_approved_draft(
        uuid.uuid4(), noi_dung="Kem này chữa khỏi mụn nhé chị.", boi="kien", xac_nhan=True))

    assert _Outbound.da_gui == ["Kem này chữa khỏi mụn nhé chị."]
    loai = [s["kind"] for s in gia.su_kien]
    assert "tin_nhan.bo_qua_canh_bao_quang_cao" in loai, (
        "bỏ qua cảnh báo phải vào nhật ký kiểm toán"
    )


def test_nhat_ky_sua_khong_chep_noi_dung_tin(monkeypatch):
    """`events` không phải chỗ nhân bản chữ gửi cho khách — xem docs/du-lieu-ca-nhan.md."""
    from agent.api import routes

    gia = _dung_csdl(monkeypatch, _nhap(content="Bản AI viết."))
    chay(routes._queue_approved_draft(uuid.uuid4(), noi_dung="Bản người sửa.", boi="kien"))

    for su_kien in gia.su_kien:
        chuoi = " ".join(str(v) for v in su_kien.values())
        assert "Bản người sửa." not in chuoi and "Bản AI viết." not in chuoi


# ---------------------------------------------------------------
#  5. Migration
# ---------------------------------------------------------------

def test_migration_0016_them_du_ba_cot():
    sql = (ROOT / "agent" / "migrations" / "versions" / "0016_sua_ban_nhap.sql").read_text(
        encoding="utf-8")
    for cot in ("noi_dung_goc", "sua_boi", "sua_luc"):
        assert f"ADD COLUMN IF NOT EXISTS {cot}" in sql


# ---------------------------------------------------------------
#  6. Dashboard
# ---------------------------------------------------------------

JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_nut_sua_chi_hien_tren_ban_nhap():
    """
    Nút Sửa vẽ ra cho một tin ĐÃ GỬI là mời người trực làm một việc rồi máy
    chủ mới từ chối — dạy họ bỏ qua thông báo lỗi. Chốt ở máy chủ vẫn phải
    có, nhưng giao diện đừng bày ra cái nút ấy.
    """
    assert "data-edit=" in JS, "phải có nút Sửa trên bản nháp"
    # Điều kiện canh nút phải nằm ngay trước nó, trong cùng một biểu thức.
    truoc = JS.split("data-edit=")[0][-200:]
    assert "draft && !dangSua" in truoc, (
        "nút Sửa phải nằm trong nhánh chỉ vẽ khi là bản nháp và chưa mở ô sửa"
    )


def test_giu_chu_dang_go_qua_lan_ve_lai():
    """
    Panel dựng lại bằng innerHTML mỗi 6 giây và mỗi lần SSE báo tin. Không
    nhớ ô đang sửa thì quản lý gõ nửa chừng là mất trắng — và mất đúng lúc
    khách vừa nhắn thêm, tức là lúc hay sửa nhất.
    """
    assert "state.dangSua" in JS, "phải nhớ bản nháp nào đang sửa qua các lần vẽ lại"


def test_hien_dau_da_sua_va_cho_xem_lai_ban_AI():
    assert "sua_boi" in JS, "tin đã sửa phải hiện ai sửa"
    assert "noi_dung_goc" in JS, "phải cho xem lại bản AI đã viết"
