"""
Ba mức ủy quyền thực thi của AI (phiếu việc mục 17) — phần KHÔNG cần CSDL.

Mỗi ràng buộc ở đây là một cách AI có thể làm việc nó không được làm mà
KHÔNG ai biết: lên đơn thật ở chế độ Gợi ý (đo được trên CSDL đang chạy
22.11.2026), công cụ ghi mới thêm vào mà không ai xếp mức, mức lạ trong CSDL
được hiểu thành "tự động", AI tự sửa chính sách của chính nó.

Phần chạy trên Postgres thật (duyệt, từ chối, hết hạn, chống thi hành hai
lần, quyền, chuông): tests/test_uy_quyen_ai_csdl.py.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import uuid
from types import SimpleNamespace

import pytest

from agent import runtime
from agent.config import ROOT
from agent.core import tools, uy_quyen

SP = {"ma": "SP1", "ten": "Kem dưỡng ẩm Aurora", "gia": 100000, "ton_kho": 50}
DON = {
    "khach_da_xac_nhan": True, "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
    "khach_dia_chi": "12 Lê Lợi, Phường Bến Thành, TP Hồ Chí Minh",
    "items": [{"ten_san_pham": SP["ten"], "so_luong": 2}],
}


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture
def len_don(monkeypatch):
    """Danh mục + tồn sống giả; ghi đơn bị THAY bằng bộ đếm để thấy có ghi hay không."""
    from agent.erp import nha_may

    hop: dict = {"luu": [], "de_xuat": [], "viec": [], "su_kien": []}

    class Cong:
        async def ton_kho(self, ma, bo_qua_cache=False):
            return SimpleNamespace(ban_duoc=50)

    async def catalog():
        return {"san_pham": [SP]}

    async def luu(**kw):
        hop["luu"].append(kw)
        return {"tao_duoc": False, "ly_do": "dừng ở đây cho test"}

    async def tao_de_xuat(**kw):
        hop["de_xuat"].append(kw)
        return uuid.uuid4(), True

    async def log_event(kind, **kw):
        hop["su_kien"].append((kind, kw))

    async def chinh_sach():
        return hop.get("chinh_sach", {})

    monkeypatch.setattr(nha_may, "cong", lambda: Cong())
    monkeypatch.setattr(tools, "_catalog_song", catalog)
    monkeypatch.setattr(tools, "_luu_don_moi", luu)
    monkeypatch.setattr(uy_quyen, "tao_de_xuat", tao_de_xuat)
    monkeypatch.setattr(uy_quyen, "doc_chinh_sach", chinh_sach)
    monkeypatch.setattr(tools.db, "log_event", log_event)
    return hop


def _che_do(monkeypatch, che_do: str):
    async def gia(conversation_id):
        return che_do, ("Chế độ AI đang là Gợi ý" if che_do == "goi_y" else "")
    monkeypatch.setattr(uy_quyen, "che_do_hieu_luc", gia)


# ══ 1 · Danh mục: mọi công cụ đều được xếp chỗ ═══════════════════════════

def test_moi_cong_cu_viet_san_deu_duoc_xep_loai():
    """
    Công cụ ghi mới thêm vào TOOLS mà quên xếp loại thì bị chặn (hỏng-đóng) —
    test này đỏ để người thêm biết phải quyết nó thuộc loại nào.
    """
    for t in tools.TOOLS:
        loai = chay(uy_quyen.phan_loai_cong_cu(t["name"]))
        assert loai in ("doc", "chuyen_nguoi", "hanh_dong"), (t["name"], loai)


def test_cong_cu_hanh_dong_tro_vao_hanh_dong_co_duong_thi_hanh():
    for ten, ma in uy_quyen.CONG_CU_HANH_DONG.items():
        hd = uy_quyen.DANH_MUC[ma]
        assert hd.ho_tro and hd.cau_hinh_duoc, ten
        assert hd.quyen_thi_hanh, f"{ma}: duyệt phải đòi thêm quyền nghiệp vụ"


def test_ba_tap_cong_cu_khong_giao_nhau():
    a, b, c = uy_quyen.CONG_CU_DOC, uy_quyen.CONG_CU_CHUYEN_NGUOI, set(uy_quyen.CONG_CU_HANH_DONG)
    assert not (a & b) and not (a & c) and not (b & c)


def test_mac_dinh_dung_phieu_viec():
    """17.5 và 17.6: việc thường ngày Tự động, huỷ đơn Có phê duyệt."""
    assert uy_quyen.DANH_MUC["tao_don"].mac_dinh == "tu_dong"
    assert uy_quyen.DANH_MUC["huy_don"].mac_dinh == "co_phe_duyet"
    assert uy_quyen.DANH_MUC["chuyen_nhan_vien"].mac_dinh == "tu_dong"
    for ma in ("sua_don", "hoan_tien", "giam_gia", "doi_tra"):
        assert not uy_quyen.DANH_MUC[ma].ho_tro, f"{ma}: hệ thống chưa có đường thi hành"


def test_mo_ta_khong_co_phan_tram():
    for hd in uy_quyen.DANH_MUC.values():
        assert "%" not in hd.mo_ta + hd.ghi_chu


# ══ 2 · Mức hiệu lực: hỏng-đóng ═══════════════════════════════════════════

def test_hanh_dong_la_la_khong_su_dung(monkeypatch):
    async def bang():
        return {"xoa_khach": {"muc": "tu_dong"}}
    monkeypatch.setattr(uy_quyen, "doc_chinh_sach", bang)
    assert chay(uy_quyen.muc_cua("xoa_khach")) == "khong_su_dung"
    assert uy_quyen.MUC_HANH_DONG_LA == "khong_su_dung"


def test_hanh_dong_chua_ho_tro_khong_bao_gio_tu_dong(monkeypatch):
    async def bang():
        return {"hoan_tien": {"muc": "tu_dong"}}   # ai đó sửa tay CSDL
    monkeypatch.setattr(uy_quyen, "doc_chinh_sach", bang)
    assert chay(uy_quyen.muc_cua("hoan_tien")) == "khong_su_dung"


def test_chuyen_nhan_vien_khong_tat_duoc(monkeypatch):
    async def bang():
        return {"chuyen_nhan_vien": {"muc": "khong_su_dung"}}
    monkeypatch.setattr(uy_quyen, "doc_chinh_sach", bang)
    assert chay(uy_quyen.muc_cua("chuyen_nhan_vien")) == "tu_dong"
    with pytest.raises(ValueError):
        chay(uy_quyen.luu_chinh_sach("chuyen_nhan_vien", "khong_su_dung"))


def test_muc_rac_trong_csdl_ve_mac_dinh_khong_ve_tu_dong(monkeypatch):
    async def bang():
        return {"huy_don": {"muc": "TU_DONG"}}
    monkeypatch.setattr(uy_quyen, "doc_chinh_sach", bang)
    assert chay(uy_quyen.muc_cua("huy_don")) == "co_phe_duyet"


@pytest.mark.parametrize("ma,muc,nguong", [
    ("khong_co", "tu_dong", None), ("hoan_tien", "tu_dong", None),
    ("tao_don", "tat_ca", None), ("huy_don", "tu_dong", 5),
])
def test_luu_chinh_sach_tu_choi_truoc_khi_ghi(monkeypatch, ma, muc, nguong):
    async def khong_duoc_ghi(*a, **k):  # pragma: no cover
        raise AssertionError("không được chạm CSDL khi dữ liệu sai")
    monkeypatch.setattr(uy_quyen.db, "execute", khong_duoc_ghi)
    with pytest.raises(ValueError):
        chay(uy_quyen.luu_chinh_sach(ma, muc, nguong_vnd=nguong))


def test_doc_chinh_sach_hong_giu_dem_cu(monkeypatch):
    """CSDL chập chờn không được lặng lẽ đưa mọi hành động về mặc định (tạo đơn = Tự động)."""
    goi = {"n": 0}

    async def fetch(sql, *a):
        goi["n"] += 1
        if goi["n"] == 1:
            return [{"hanh_dong": "tao_don", "muc": "co_phe_duyet", "nguong_vnd": None,
                     "sua_boi": "x", "sua_luc": None}]
        raise ConnectionError("mất kết nối")

    monkeypatch.setattr(uy_quyen.db, "fetch", fetch)
    uy_quyen.xoa_dem()
    assert chay(uy_quyen.muc_cua("tao_don")) == "co_phe_duyet"
    monkeypatch.setattr(uy_quyen, "_DEM_GIAY", -1.0)   # đệm coi như hết hạn
    assert chay(uy_quyen.muc_cua("tao_don")) == "co_phe_duyet"
    uy_quyen.xoa_dem()


# ══ 3 · Chế độ hiệu lực ═══════════════════════════════════════════════════

def test_che_do_goi_y_khong_can_hoi_csdl(monkeypatch):
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    assert chay(uy_quyen.che_do_hieu_luc(uuid.uuid4()))[0] == "goi_y"


def test_duyet_rieng_cua_hoi_thoai_tinh_nhu_goi_y(monkeypatch):
    monkeypatch.setitem(runtime.STATE, "mode", "auto")

    async def fetchrow(sql, *a):
        return {"duyet_truoc_khi_gui": True}
    monkeypatch.setattr(uy_quyen.db, "fetchrow", fetchrow)
    che_do, ly_do = chay(uy_quyen.che_do_hieu_luc(uuid.uuid4()))
    assert che_do == "goi_y" and "Duyệt trước khi gửi" in ly_do


def test_khong_doc_duoc_co_rieng_thi_xu_ly_nhu_goi_y(monkeypatch):
    monkeypatch.setitem(runtime.STATE, "mode", "auto")

    async def hong(sql, *a):
        raise ConnectionError("x")
    monkeypatch.setattr(uy_quyen.db, "fetchrow", hong)
    assert chay(uy_quyen.che_do_hieu_luc(uuid.uuid4()))[0] == "goi_y"


# ══ 4 · Chốt ở cửa thi hành: tạo đơn ═══════════════════════════════════

def test_goi_y_KHONG_ghi_don_chi_de_xuat(monkeypatch, len_don):
    """Lỗi đo được trên CSDL đang chạy: chế độ Gợi ý mà AI vẫn lên đơn thật."""
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    cid = uuid.uuid4()
    kq = chay(tools.run_tool("tao_don_hang", dict(DON), cid))
    assert len_don["luu"] == [], "chế độ Gợi ý tuyệt đối không ghi đơn"
    assert kq["tao_duoc"] is False and kq["da_de_xuat"] is True
    assert "KHÔNG nói đã lên đơn" in kq["ghi_chu_cho_agent"]
    dx = len_don["de_xuat"][0]
    assert dx["quyet"].che_do == "goi_y"
    # Giá trong đề xuất lấy từ DANH MỤC, không từ lời model.
    assert dx["tham_so"]["tong_tien"] == 200000
    assert dx["de_xuat"]["sau"]["items"][0]["don_gia"] == SP["gia"]
    assert dx["can_cu"]["nguon"] and dx["can_cu"]["rui_ro"]


def test_goi_y_van_kiem_du_dieu_kien_truoc_khi_de_xuat(monkeypatch, len_don):
    """Đề xuất phải là việc ĐÃ KIỂM: khách chưa xác nhận thì không có gì để duyệt."""
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    kq = chay(tools.run_tool("tao_don_hang", {**DON, "khach_da_xac_nhan": False}, uuid.uuid4()))
    assert kq["tao_duoc"] is False and not kq.get("da_de_xuat")
    assert len_don["de_xuat"] == []


def test_tu_dong_muc_khong_su_dung_thi_chuyen_nguoi(monkeypatch, len_don):
    _che_do(monkeypatch, "tu_dong")
    len_don["chinh_sach"] = {"tao_don": {"muc": "khong_su_dung"}}
    kq = chay(tools.run_tool("tao_don_hang", dict(DON), uuid.uuid4()))
    assert kq["bi_chan"] and kq["can_chuyen_nhan_vien"] is True
    assert len_don["luu"] == [] and len_don["de_xuat"] == []
    assert any(k == "ai.hanh_dong.chan" for k, _ in len_don["su_kien"])


@pytest.mark.parametrize("muc,nguong,mong", [
    ("tu_dong", None, "da_chot"),            # 200.000đ < ngưỡng .env
    ("tu_dong", 150_000, "cho_duyet"),        # ngưỡng do quản trị đặt trên dashboard
    ("co_phe_duyet", None, "cho_duyet"),
])
def test_tu_dong_theo_muc_va_nguong(monkeypatch, len_don, muc, nguong, mong):
    from agent.config import settings

    monkeypatch.setattr(settings, "nguong_tu_chot_vnd", 1_000_000)
    _che_do(monkeypatch, "tu_dong")
    len_don["chinh_sach"] = {"tao_don": {"muc": muc, "nguong_vnd": nguong}}
    chay(tools.run_tool("tao_don_hang", dict(DON), uuid.uuid4()))
    assert [x["trang_thai"] for x in len_don["luu"]] == [mong]


def test_thi_hanh_de_xuat_tu_choi_khi_gia_doi(len_don):
    kq = chay(tools._tao_don_hang(dict(DON), [SP], uuid.uuid4(),
                                  ep_da_chot=True, tong_phai_bang=150000))
    assert kq["tao_duoc"] is False and "đã đổi" in kq["ly_do"]
    assert len_don["luu"] == []


def test_thi_hanh_de_xuat_da_duyet_thi_chot_luon(monkeypatch, len_don):
    from agent.config import settings

    monkeypatch.setattr(settings, "nguong_tu_chot_vnd", 1)   # mọi đơn đều "vượt ngưỡng"
    chay(tools._tao_don_hang(dict(DON), [SP], uuid.uuid4(), ep_da_chot=True,
                             tong_phai_bang=200000))
    assert [x["trang_thai"] for x in len_don["luu"]] == ["da_chot"]


# ══ 5 · Huỷ đơn ═══════════════════════════════════════════════════════════

@pytest.fixture
def xin_huy(monkeypatch, len_don):
    oid = uuid.uuid4()

    async def danh_dau(ma, cid, ly_do):
        return oid

    async def bang_chung(order_id, ly_do=""):
        return {"ma_don": "AS1", "huy_duoc": True, "truoc": {"trang_thai": "Đã chốt"},
                "sau": {"trang_thai": "Đã huỷ"}, "nguon": [{"ten": "Sổ đơn", "chi_tiet": "x"}],
                "rui_ro": [], "thieu": []}

    async def tao_viec(**kw):
        len_don["viec"].append(kw)
        return "v1"

    from agent.core import cong_viec

    monkeypatch.setattr(tools, "_danh_dau_xin_huy", danh_dau)
    monkeypatch.setattr(tools, "bang_chung_huy_don", bang_chung)
    monkeypatch.setattr(cong_viec, "tao_tu_yeu_cau_xu_ly_don", tao_viec)
    len_don["oid"] = oid
    return len_don


def test_huy_mac_dinh_co_phe_duyet_la_de_xuat_khong_phai_chuyen_nguoi(monkeypatch, xin_huy):
    """17.11: phê duyệt (AI đã chuẩn bị việc cụ thể) KHÁC chuyển người."""
    _che_do(monkeypatch, "tu_dong")
    kq = chay(tools.run_tool("xin_huy_don", {"ma_don": "AS1", "ly_do": "đổi ý"}, uuid.uuid4()))
    assert kq["da_de_xuat"] is True and kq["da_huy"] is False
    assert kq["can_chuyen_nhan_vien"] is False
    assert "đã huỷ" in kq["ghi_chu"]           # câu cấm vẫn được nhắc thẳng
    assert xin_huy["viec"] == [], "thẻ duyệt thay cho việc xử lý đơn — không đẻ hai việc"
    assert xin_huy["de_xuat"][0]["order_id"] == xin_huy["oid"]


def test_huy_muc_khong_su_dung_ghi_nhan_roi_chuyen_nguoi(monkeypatch, xin_huy):
    _che_do(monkeypatch, "tu_dong")
    xin_huy["chinh_sach"] = {"huy_don": {"muc": "khong_su_dung"}}
    kq = chay(tools.run_tool("xin_huy_don", {"ma_don": "AS1", "ly_do": "x"}, uuid.uuid4()))
    assert kq["da_ghi_nhan"] is True and kq["can_chuyen_nhan_vien"] is True
    assert xin_huy["de_xuat"] == [] and len(xin_huy["viec"]) == 1


def test_huy_khong_tao_duoc_de_xuat_thi_lui_ve_chuyen_nguoi(monkeypatch, xin_huy):
    """Hỏng ở đường duyệt không được thành im lặng: rơi về việc + chuyển người."""
    _che_do(monkeypatch, "goi_y")

    async def hong(**kw):
        raise ConnectionError("CSDL")
    monkeypatch.setattr(uy_quyen, "tao_de_xuat", hong)
    kq = chay(tools.run_tool("xin_huy_don", {"ma_don": "AS1", "ly_do": "x"}, uuid.uuid4()))
    assert kq["can_chuyen_nhan_vien"] is True and len(xin_huy["viec"]) == 1
    assert any(k == "ai.de_xuat.loi_tao" for k, _ in xin_huy["su_kien"])


# ══ 6 · Công cụ khác: MCP ghi, công cụ lạ ═════════════════════════════════

def _plugin(monkeypatch, loai: str, ghi: bool):
    from agent.ky_nang import kho_ky_nang

    bm = SimpleNamespace(ten="ghi_crm", loai=loai, cau_hinh={"ghi": ghi, "ghi_cho_phep": True})

    async def tim(ten):
        return bm if ten == "ghi_crm" else None

    async def tat(ten):
        return False

    monkeypatch.setattr(kho_ky_nang, "tim_plugin", tim)
    monkeypatch.setattr(kho_ky_nang, "dang_tat", tat)


def test_mcp_ghi_bi_chan_o_che_do_goi_y(monkeypatch, len_don):
    _plugin(monkeypatch, "mcp", True)
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    kq = chay(tools.run_tool("ghi_crm", {}, uuid.uuid4()))
    assert kq["bi_chan"] and kq["can_chuyen_nhan_vien"] is True


def test_plugin_loai_la_bi_chan(monkeypatch, len_don):
    _plugin(monkeypatch, "loai_moi_ghi_du_lieu", False)
    _che_do(monkeypatch, "tu_dong")
    assert chay(uy_quyen.phan_loai_cong_cu("ghi_crm")) == "la"
    kq = chay(tools.run_tool("ghi_crm", {}, uuid.uuid4()))
    assert kq["bi_chan"] and kq["can_chuyen_nhan_vien"] is True


# ══ 7 · AI không đổi được chính sách của chính nó ═══════════════════════

def test_ai_khong_co_duong_ghi_chinh_sach():
    nguon = inspect.getsource(tools)
    assert "luu_chinh_sach" not in nguon and "luu_han_gio" not in nguon
    assert "ai_uy_quyen" not in nguon
    assert not any("uy_quyen" in t["name"] or "chinh_sach" in t["name"] for t in tools.TOOLS)
    # Chỉ MỘT nơi ngoài lõi gọi hàm ghi chính sách: API có quyền agent.dieu_khien.
    goi = [p for p in (ROOT / "agent").rglob("*.py")
           if "luu_chinh_sach(" in p.read_text(encoding="utf-8")
           and p.name != "uy_quyen.py"]
    assert [p.name for p in goi] == ["uy_quyen_ai.py"]


def test_api_sua_chinh_sach_doi_agent_dieu_khien():
    from agent.api import uy_quyen_ai

    nguon = inspect.getsource(uy_quyen_ai.sua_chinh_sach)
    assert 'can_quyen("agent.dieu_khien")' in nguon
    for ham in (uy_quyen_ai.duyet_de_xuat, uy_quyen_ai.tu_choi_de_xuat):
        assert 'can_quyen("ai.duyet")' in inspect.getsource(ham)
        assert "_kiem_quyen_de_xuat" in inspect.getsource(ham)


# ══ 8 · Migration khớp mã ═════════════════════════════════════════════════

def _mig() -> str:
    return (ROOT / "agent" / "migrations" / "versions" / "0065_uy_quyen_ai.sql").read_text(
        encoding="utf-8")


def test_check_trang_thai_khop_ma():
    khoi = re.search(r"trang_thai\s+TEXT NOT NULL DEFAULT 'cho_duyet' CHECK \(trang_thai IN \((.*?)\)\)",
                     _mig(), re.S).group(1)
    assert set(re.findall(r"'(\w+)'", khoi)) == set(uy_quyen.TRANG_THAI)
    assert set(uy_quyen.TRANG_THAI) == set(uy_quyen.NHAN_TRANG_THAI)


def test_check_muc_khop_ma():
    for khoi in re.findall(r"CHECK \((?:muc|muc_uy_quyen) IN \((.*?)\)\)", _mig()):
        assert set(re.findall(r"'(\w+)'", khoi)) == set(uy_quyen.MUC)


def test_mot_de_xuat_dang_mo_cho_moi_viec():
    """Chỉ mục một-phần là chốt chống trùng ở tầng CSDL, không chỉ trong mã."""
    assert re.search(r"UNIQUE INDEX IF NOT EXISTS idx_ai_de_xuat_mot_dang_mo\s+ON ai_de_xuat "
                     r"\(khoa_trung\) WHERE trang_thai IN \('cho_duyet', 'da_duyet'\)", _mig())


def test_bang_moi_chi_nam_trong_migration():
    sql = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    assert "ai_de_xuat" not in sql and "ai_uy_quyen" not in sql
