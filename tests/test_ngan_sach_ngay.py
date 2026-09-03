"""
Trần chi phí toàn cục theo ngày.

VÌ SAO CẦN, dù đã có trần mỗi hội thoại:

    0,25 USD × 10.000 hội thoại = 2.500 USD

Trần mỗi hội thoại chặn được MỘT hội thoại chạy loạn. Nó không chặn được
nhiều hội thoại cùng chạy ĐÚNG LUẬT. Ba đường tới con số ấy, không đường
nào cần kẻ xấu: một bài viral, một vòng lặp trong adapter kênh, hay một
người nhắn từ nhiều tài khoản.

Ca quan trọng nhất tệp này: `test_cham_tran_thi_chuyen_nguoi_VA_keu` — im
lặng ngừng trả lời là kiểu hỏng tệ nhất, vì khách vẫn nhắn và không ai biết.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import ngan_sach, runtime  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _sach():
    ngan_sach.xoa_dem()
    goc = runtime.STATE.get("tran_chi_phi_ngay_usd")
    yield
    runtime.STATE["tran_chi_phi_ngay_usd"] = goc
    ngan_sach.xoa_dem()


def _tieu(monkeypatch, tong: float):
    """Giả lập CSDL đã ghi `tong` USD hôm nay."""
    async def fetchrow(sql, *a):
        return {"tong": tong}

    monkeypatch.setattr(ngan_sach.db, "fetchrow", fetchrow)


# ---------------------------------------------------------------
#  Còn / hết ngân sách
# ---------------------------------------------------------------

def test_duoi_tran_thi_con_ngan_sach(monkeypatch):
    _tieu(monkeypatch, 3.0)
    runtime.STATE["tran_chi_phi_ngay_usd"] = 25.0
    con, da, t = chay(ngan_sach.con_ngan_sach())
    assert con is True and da == 3.0 and t == 25.0


def test_bang_tran_la_HET(monkeypatch):
    """`>=` chứ không phải `>`: đúng bằng trần là đã tiêu hết phần cho phép."""
    _tieu(monkeypatch, 25.0)
    runtime.STATE["tran_chi_phi_ngay_usd"] = 25.0
    con, _, _ = chay(ngan_sach.con_ngan_sach())
    assert con is False


def test_tran_bang_0_la_TAT_han(monkeypatch):
    """Người vận hành phải tắt được hẳn, không bị ép một con số nào."""
    _tieu(monkeypatch, 9_999.0)
    runtime.STATE["tran_chi_phi_ngay_usd"] = 0
    con, _, t = chay(ngan_sach.con_ngan_sach())
    assert con is True and t == 0


# ---------------------------------------------------------------
#  Đọc trần từ RUNTIME, không từ settings
# ---------------------------------------------------------------

def test_tran_doc_tu_runtime_khong_doc_settings():
    """
    Đọc `settings` thì ô nhập trên dashboard thành đồ trang trí: bấm được,
    ghi được xuống CSDL, hiện đúng giá trị mới — mà lưới vẫn chặn theo con
    số trong `.env`.
    """
    runtime.STATE["tran_chi_phi_ngay_usd"] = 7.5
    assert ngan_sach.tran() == 7.5
    runtime.STATE["tran_chi_phi_ngay_usd"] = 99.0
    assert ngan_sach.tran() == 99.0


def test_tran_hong_kieu_thi_ve_0_chu_khong_no():
    """Giá trị rác trong CSDL không được làm chết đường trả lời khách."""
    runtime.STATE["tran_chi_phi_ngay_usd"] = "khong-phai-so"
    assert ngan_sach.tran() == 0.0


# ---------------------------------------------------------------
#  Đệm và bộ đếm trong tiến trình
# ---------------------------------------------------------------

def test_dem_khong_hoi_csdl_moi_lan(monkeypatch):
    dem = {"n": 0}

    async def fetchrow(sql, *a):
        dem["n"] += 1
        return {"tong": 1.0}

    monkeypatch.setattr(ngan_sach.db, "fetchrow", fetchrow)
    for _ in range(5):
        chay(ngan_sach.da_tieu_hom_nay())
    assert dem["n"] == 1, "mỗi tin nhắn một lượt SUM là lãng phí"


def test_chi_phi_trong_cua_so_dem_van_duoc_cong(monkeypatch):
    """
    Không cộng thì suốt 30 giây hệ thống tin rằng mình chưa tiêu thêm đồng
    nào — và ở đúng lúc đang chạm trần, 30 giây là quãng nguy hiểm nhất.
    """
    _tieu(monkeypatch, 10.0)
    assert chay(ngan_sach.da_tieu_hom_nay()) == 10.0
    ngan_sach.ghi_nhan(2.5)
    assert chay(ngan_sach.da_tieu_hom_nay()) == 12.5


def test_ghi_nhan_bo_qua_so_am_va_0():
    ngan_sach.ghi_nhan(0)
    ngan_sach.ghi_nhan(-5)
    assert ngan_sach._cong_them == 0


def test_csdl_hong_thi_KHONG_chan_agent(monkeypatch):
    """
    Trần chi phí là hàng rào phòng xa. Biến một sự cố CSDL thành "cửa hàng
    ngừng trả lời khách" là đổi một vấn đề nhỏ lấy một vấn đề lớn hơn.
    """
    async def no(*a, **k):
        raise RuntimeError("CSDL sập")

    monkeypatch.setattr(ngan_sach.db, "fetchrow", no)
    runtime.STATE["tran_chi_phi_ngay_usd"] = 25.0
    con, _, _ = chay(ngan_sach.con_ngan_sach())
    assert con is True


# ---------------------------------------------------------------
#  Chạm trần phải KÊU
# ---------------------------------------------------------------

def test_cham_tran_thi_chuyen_nguoi_VA_keu(monkeypatch):
    """
    Ca quan trọng nhất tệp này.

    Im lặng ngừng trả lời là kiểu hỏng tệ nhất: khách vẫn nhắn, tin vẫn vào
    cơ sở dữ liệu, không ai trả lời, và không có gì báo.
    """
    su_kien: list[str] = []
    bao: list[tuple] = []

    async def log_event(kind, **kw):
        su_kien.append(kind)

    async def _bao(muc_do, tieu_de, chi_tiet, kq):
        bao.append((muc_do, tieu_de))

    monkeypatch.setattr(ngan_sach.db, "log_event", log_event)
    from agent import canh_gac

    monkeypatch.setattr(canh_gac, "_bao", _bao)

    chay(ngan_sach.keu_neu_cham_tran(30.0, 25.0))
    assert "ngan_sach.cham_tran" in su_kien
    assert bao and bao[0][0] == "nghiem_trong"


def test_chi_keu_MOT_LAN_moi_ngay(monkeypatch):
    """
    Một cảnh báo mỗi giây thì người trực tắt thông báo, và lần sau có sự cố
    thật cũng không ai thấy.
    """
    bao: list = []

    async def log_event(kind, **kw):
        pass

    async def _bao(*a, **k):
        bao.append(1)

    monkeypatch.setattr(ngan_sach.db, "log_event", log_event)
    from agent import canh_gac

    monkeypatch.setattr(canh_gac, "_bao", _bao)

    for _ in range(20):
        chay(ngan_sach.keu_neu_cham_tran(30.0, 25.0))
    assert len(bao) == 1


def test_canh_bao_hong_khong_lam_hong_duong_tra_loi(monkeypatch):
    """Cảnh báo là việc phụ. Nó hỏng thì khách vẫn phải được phục vụ."""
    async def no(*a, **k):
        raise RuntimeError("webhook cảnh báo chết")

    monkeypatch.setattr(ngan_sach.db, "log_event", no)
    from agent import canh_gac

    monkeypatch.setattr(canh_gac, "_bao", no)
    chay(ngan_sach.keu_neu_cham_tran(30.0, 25.0))  # không được ném


# ---------------------------------------------------------------
#  Nối vào lớp lưới số 1
# ---------------------------------------------------------------

def test_agent_goi_tran_ngay_TRUOC_khi_goi_model():
    """
    Chốt phải nằm trước vòng lặp công cụ. Đặt sau thì lượt gọi model đắt
    nhất đã xảy ra rồi mới phát hiện hết tiền.
    """
    import ast

    nguon = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    cay = ast.parse(nguon)
    for node in ast.walk(cay):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "respond"):
            continue
        dong_ngan_sach = dong_model = None
        for con in ast.walk(node):
            if isinstance(con, ast.Call):
                ten = ast.unparse(con.func)
                if "con_ngan_sach" in ten and dong_ngan_sach is None:
                    dong_ngan_sach = con.lineno
                if "llm.complete" in ten and dong_model is None:
                    dong_model = con.lineno
        assert dong_ngan_sach is not None, "respond() không kiểm trần ngày"
        assert dong_model is not None
        assert dong_ngan_sach < dong_model, (
            "kiểm trần ngày nằm SAU lời gọi model — tiền đã tiêu rồi"
        )
        return
    raise AssertionError("không tìm thấy respond()")


def test_agent_ghi_nhan_chi_phi_sau_moi_luot():
    """
    Không ghi nhận thì con số chỉ đúng tới lần làm mới đệm gần nhất, và
    trần ngày trễ mất tới 30 giây ở đúng lúc quan trọng.
    """
    nguon = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    assert "ngan_sach.ghi_nhan(" in nguon


def test_tran_ngay_chinh_duoc_tu_dashboard():
    """Khoá phải nằm trong `KHOA_BEN_VUNG`, nếu không nó mất sau restart."""
    assert "tran_chi_phi_ngay_usd" in runtime.KHOA_BEN_VUNG


# ---------------------------------------------------------------
#  Không được BÁO ÍT hơn thực tế
# ---------------------------------------------------------------

def test_chi_phi_ghi_nhan_truoc_luot_doc_KHONG_bi_mat(monkeypatch):
    """
    LỖI THẬT, bắt được khi chạy tay chính mã này.

    `ghi_nhan()` được gọi ngay khi `respond()` xong, còn dòng `messages` do
    lớp gọi ghi vào SAU đó. Lượt đọc CSDL rơi đúng vào khoảng giữa thì con
    số trả về THIẾU phần vừa tiêu — và bản đầu lấy thẳng nó, tức xoá mất
    phần ấy vĩnh viễn.

    Với một hàng rào chi phí, sai theo hướng báo ÍT hơn thực tế là sai
    nguy hiểm: nó cho tiêu tiếp.
    """
    _tieu(monkeypatch, 0.0)          # CSDL chưa thấy gì
    ngan_sach.ghi_nhan(0.5)          # nhưng ta vừa tiêu 0,5
    assert chay(ngan_sach.da_tieu_hom_nay()) == 0.5, (
        "chi phí vừa ghi nhận bị xoá mất khi đệm làm mới"
    )


def test_csdl_lon_hon_thi_lay_csdl(monkeypatch):
    """
    Tiến trình khác cũng tiêu tiền. CSDL là bức tranh toàn cục, nên khi nó
    lớn hơn thì nó đúng hơn.
    """
    _tieu(monkeypatch, 12.0)
    ngan_sach.ghi_nhan(0.5)
    assert chay(ngan_sach.da_tieu_hom_nay()) == 12.0


def test_sang_ngay_moi_thi_bo_het_so_cu(monkeypatch):
    """
    Không có mốc ngày thì phép `max()` giữ lại tổng của hôm qua, và trần
    hôm nay chạm ngay từ tin nhắn đầu tiên — cửa hàng mở cửa là agent đã
    ngừng trả lời.
    """
    _tieu(monkeypatch, 20.0)
    assert chay(ngan_sach.da_tieu_hom_nay()) == 20.0

    monkeypatch.setattr(ngan_sach, "_hom_nay", lambda: "2099-01-01")
    _tieu(monkeypatch, 0.0)
    assert chay(ngan_sach.da_tieu_hom_nay()) == 0.0, (
        "tổng của hôm qua còn dính sang hôm nay"
    )
