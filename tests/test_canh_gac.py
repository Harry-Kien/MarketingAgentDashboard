"""
Kiểm thử canh gác. Không gọi API, không cần CSDL.

Canh gác hỏng theo hai kiểu, và cả hai đều dẫn tới cùng một kết cục: không
ai biết hệ thống đang chết.

  1. KHÔNG BÁO khi hỏng  — hiển nhiên
  2. BÁO QUÁ NHIỀU        — sau nửa tiếng nhận thông báo mỗi 5 phút, người
                            ta tắt nó đi, và lần hỏng thật tiếp theo không
                            ai đọc. Kết cục y hệt kiểu 1.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import canh_gac  # noqa: E402
from agent import main as app_main  # noqa: E402


def _bo_chu_thich(src: str) -> str:
    """
    Bỏ docstring và chú thích, chỉ giữ mã chạy được.

    Cần vì phần lớn test ở đây soi mã nguồn, mà chú thích trong dự án này
    thường giải thích VÌ SAO KHÔNG làm một điều — nên chúng chứa đúng những
    chữ mà test đang tìm để cấm.
    """
    import io
    import tokenize
    ra = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            ra.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        # Nguồn cắt từ giữa file có thể không tokenize được nguyên vẹn;
        # rơi về cách thô còn hơn làm đỏ test vì lý do không liên quan.
        return "\n".join(
            d for d in src.splitlines() if not d.strip().startswith("#")
        )
    return " ".join(ra)



# =====================================================================
#  Chỉ báo khi ĐỔI trạng thái
# =====================================================================

def test_bao_khi_doi_trang_thai_khong_bao_moi_lan_kiem():
    src = inspect.getsource(canh_gac.kiem_mot_lan)
    assert "hong_nay and not hong_truoc" in src, "đang báo mỗi lần kiểm"
    assert "hong_truoc and not hong_nay" in src, "thiếu báo phục hồi"


def test_co_bao_phuc_hoi():
    """
    Không có nó thì người trực không biết khi nào được đi ngủ — và lần sau
    họ sẽ không dậy nữa.
    """
    src = inspect.getsource(canh_gac.kiem_mot_lan)
    assert "phuc_hoi" in src


def test_canh_bao_nhe_khong_danh_thuc_ai():
    """"canh_bao" chưa phải hỏng. Đánh thức người lúc nửa đêm vì nó là lạm dụng."""
    src = inspect.getsource(canh_gac.kiem_mot_lan)
    assert 'nay == "hong"' in src
    assert 'nay == "canh_bao"' not in src


# =====================================================================
#  Canh gác không được chết vì thứ nó đang canh
# =====================================================================

def test_gui_bao_dong_hong_thi_khong_nem_len():
    """
    Vòng canh gác chết là mất luôn khả năng biết mọi thứ khác đang hỏng.
    """
    src = inspect.getsource(canh_gac._bao)
    assert "except httpx.HTTPError" in src
    assert "raise" not in src.split("except httpx.HTTPError")[1]


def test_vong_canh_gac_khong_bao_gio_chet():
    src = inspect.getsource(canh_gac.vong_canh_gac)
    assert "except Exception" in src
    assert "asyncio.CancelledError" in src, "phải cho tắt được khi app dừng"


def test_cho_mot_nhip_truoc_khi_kiem_lan_dau():
    """
    Lúc mới khởi động, kênh và hàng đợi chưa kịp ổn định — kiểm ngay là báo
    động giả, và báo động giả đầu tiên làm người ta mất tin vào cả hệ thống.
    """
    src = inspect.getsource(canh_gac.vong_canh_gac)
    assert "await asyncio.sleep(60)" in src


def test_khoang_kiem_co_san_toi_thieu():
    """Đặt nhầm 1 giây thì canh gác tự nó thành tải."""
    src = inspect.getsource(canh_gac.vong_canh_gac)
    assert "max(60," in src


# =====================================================================
#  Người canh bên ngoài
# =====================================================================

def test_co_nguoi_canh_ben_ngoai():
    """
    Vòng trong tiến trình KHÔNG phát hiện được chính tiến trình chết — lúc
    đó nó chết theo. Mà tiến trình chết là kiểu hỏng thường gặp nhất: hết
    bộ nhớ, máy khởi động lại sau cập nhật, đóng nhầm cửa sổ.
    """
    f = ROOT / "scripts" / "canh_gac_ngoai.py"
    assert f.exists()
    src = f.read_text(encoding="utf-8")
    assert "/healthz" in src


def test_nguoi_canh_ngoai_khong_dung_csdl():
    """
    Nó phải chạy được cả khi Postgres chết. Dùng CSDL ở đây là để người
    canh chết chung với thứ nó đang canh.
    """
    src = (ROOT / "scripts" / "canh_gac_ngoai.py").read_text(encoding="utf-8")
    for cam in ("import asyncpg", "from agent import db", "agent.db"):
        assert cam not in src, f"người canh ngoài đang phụ thuộc CSDL: {cam}"


def test_nguoi_canh_ngoai_nho_trang_thai_lan_truoc():
    """Không nhớ thì mỗi 5 phút lại báo một lần trong suốt lúc hỏng."""
    src = (ROOT / "scripts" / "canh_gac_ngoai.py").read_text(encoding="utf-8")
    assert "_doc_truoc" in src and "_ghi(" in src


def test_nguoi_canh_ngoai_tra_ma_thoat_khac_0_khi_hong():
    """Để Task Scheduler và cron cũng biết, không chỉ webhook."""
    src = (ROOT / "scripts" / "canh_gac_ngoai.py").read_text(encoding="utf-8")
    assert "return 0 if song else 1" in src


# =====================================================================
#  Nối vào vòng đời app
# =====================================================================

def test_vong_canh_gac_duoc_bat_khi_khoi_dong():
    src = inspect.getsource(app_main)
    assert "canh_gac.vong_canh_gac()" in src


def test_vong_canh_gac_duoc_tat_khi_dung_app():
    src = inspect.getsource(app_main)
    assert "(scheduler, don_du_lieu, canh)" in src, "task canh gác không được huỷ khi tắt"


def test_bao_dong_di_qua_webhook_khong_gan_cung_zalo():
    """
    Nơi nhận báo động là việc của doanh nghiệp. Nhốt nó vào mã là buộc mọi
    người dùng chung một cách nhận — cùng lý do với PublishAdapter.
    """
    src = inspect.getsource(canh_gac._bao)
    assert "canh_gac_webhook" in src

    # Soi MÃ, không soi chú thích: đoạn giải thích "vì sao không gửi thẳng
    # Zalo hay email" cũng chứa đúng những chữ đó. Test soi chú thích thì
    # đỏ vì lý do sai — đã mắc lỗi này ba lần trong dự án.
    ma = _bo_chu_thich(src)
    for gan_cung in ("zalo", "telegram", "smtp", "sendgrid"):
        assert gan_cung not in ma.lower(), f"đang gắn cứng {gan_cung}"


# =====================================================================
#  Khách bị bỏ quên — đường báo động riêng
# =====================================================================
# Tám phép kiểm kia hỏi "hệ thống có sống không". Phép này hỏi "có ai đang
# bị bỏ quên không". Hệ thống xanh toàn bộ mà bảy khách ngồi chờ từ tối
# hôm trước vẫn là hỏng — chỉ là hỏng ở phía không có mã nào đang chạy.

import asyncio  # noqa: E402

from agent import suc_khoe  # noqa: E402


def _kq(cho_lau: bool, tong: str = "tot") -> dict:
    """Kết quả chẩn đoán giả, chỉ đủ phần canh gác cần đọc."""
    return {
        "trang_thai": tong,
        "muc": [
            {"ten": "CSDL", "trang_thai": "tot", "ghi_chu": ""},
            {
                "ten": canh_gac.MUC_KHACH_CHO,
                "trang_thai": suc_khoe.CANH_BAO if cho_lau else suc_khoe.TOT,
                "ghi_chu": "3 khách chờ quá 30 phút" if cho_lau else "không ai chờ",
            },
        ],
    }


def _chay(monkeypatch, chuoi: list[dict]) -> list[str]:
    """Chạy canh gác qua một chuỗi kết quả, trả về các mức độ đã báo."""
    da_bao: list[str] = []

    async def bao_gia(muc_do, tieu_de, chi_tiet, kq):
        da_bao.append(muc_do)

    ket_qua = iter(chuoi)

    async def tong_kiem_gia():
        return next(ket_qua)

    monkeypatch.setattr(canh_gac, "_bao", bao_gia)
    monkeypatch.setattr(canh_gac.suc_khoe, "tong_kiem", tong_kiem_gia)
    monkeypatch.setattr(canh_gac, "_truoc", None)
    monkeypatch.setattr(canh_gac, "_cho_truoc", False)

    async def chay_het():
        for _ in chuoi:
            await canh_gac.kiem_mot_lan()

    asyncio.run(chay_het())
    return da_bao


def test_bao_khi_bat_dau_co_khach_cho(monkeypatch):
    assert _chay(monkeypatch, [_kq(cho_lau=True)]) == ["khach_cho"]


def test_khong_bao_khi_khong_ai_cho(monkeypatch):
    assert _chay(monkeypatch, [_kq(cho_lau=False)]) == []


def test_khong_bao_lai_khi_van_con_khach_cho(monkeypatch):
    """
    Đúng luật của cả module: chỉ báo khi ĐỔI. Báo mỗi 5 phút suốt buổi tối
    bận thì người trực tắt thông báo, và lần sau không ai đọc.
    """
    chuoi = [_kq(cho_lau=True), _kq(cho_lau=True), _kq(cho_lau=True)]
    assert _chay(monkeypatch, chuoi) == ["khach_cho"]


def test_bao_khi_da_xu_ly_het(monkeypatch):
    """Không có tin này thì người trực không biết mình đã làm xong."""
    chuoi = [_kq(cho_lau=True), _kq(cho_lau=False)]
    assert _chay(monkeypatch, chuoi) == ["khach_cho", "khach_cho_xong"]


def test_khach_cho_bao_duoc_ngay_ca_khi_he_thong_khoe(monkeypatch):
    """
    Đây là lý do phép kiểm này cần đường riêng. Trạng thái tổng là `tot`,
    nên nhánh báo động chính im lặng — mà khách thì vẫn đang chờ.
    """
    assert _chay(monkeypatch, [_kq(cho_lau=True, tong="tot")]) == ["khach_cho"]


def test_hai_duong_bao_doc_lap_nhau(monkeypatch):
    """
    Hệ thống hỏng VÀ có khách chờ là hai việc khác nhau, cần hai tin khác
    nhau: một cái gọi người sửa máy, một cái gọi người trả lời khách.
    """
    chuoi = [_kq(cho_lau=True, tong="hong")]
    assert sorted(_chay(monkeypatch, chuoi)) == ["hong", "khach_cho"]


def test_khach_cho_ra_canh_bao_chu_khong_phai_hong(monkeypatch):
    """
    Phải là `canh_bao`, không được là `hong`. `hong` kéo trạng thái tổng
    xuống và nghĩa là hệ thống không phục vụ được — khách chờ lúc 9 giờ tối
    là tiệm đã đóng cửa, không phải máy hỏng. Gắn nhãn "Hệ thống đang hỏng"
    cho chuyện bình thường của buổi tối là cách nhanh nhất khiến người ta
    tắt thông báo.
    """
    from datetime import datetime, timedelta, timezone

    async def fetchrow_gia(sql, *args):
        return {"so": 3,
                "lau_nhat": datetime.now(timezone.utc) - timedelta(minutes=95)}

    # GHIM giờ trực. Không ghim thì test đỏ sau 21 giờ — `_kiem_khach_cho_lau`
    # thoát sớm khi ngoài giờ, trước cả khi chạm CSDL. Test phụ thuộc
    # đồng hồ là test làm CI đỏ ngẫu nhiên, và người ta sẽ ngừng đọc CI.
    monkeypatch.setattr(suc_khoe.gio_lam_viec, "dang_trong_gio", lambda *_: True)
    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow_gia)
    muc = asyncio.run(suc_khoe._kiem_khach_cho_lau())
    assert muc["trang_thai"] == suc_khoe.CANH_BAO
    assert muc["so_khach"] == 3
    assert muc["lau_nhat_phut"] >= 95


def test_khong_ai_cho_thi_bao_tot(monkeypatch):
    async def fetchrow_gia(sql, *args):
        return {"so": 0, "lau_nhat": None}

    # GHIM giờ trực. Không ghim thì test đỏ sau 21 giờ — `_kiem_khach_cho_lau`
    # thoát sớm khi ngoài giờ, trước cả khi chạm CSDL. Test phụ thuộc
    # đồng hồ là test làm CI đỏ ngẫu nhiên, và người ta sẽ ngừng đọc CI.
    monkeypatch.setattr(suc_khoe.gio_lam_viec, "dang_trong_gio", lambda *_: True)
    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow_gia)
    assert asyncio.run(suc_khoe._kiem_khach_cho_lau())["trang_thai"] == suc_khoe.TOT


def test_csdl_hong_thi_bao_hong_chu_khong_no(monkeypatch):
    """Một phép kiểm ném lỗi sẽ làm hỏng cả trang chẩn đoán."""
    async def fetchrow_gia(sql, *args):
        raise RuntimeError("mat ket noi")

    # GHIM giờ trực. Không ghim thì test đỏ sau 21 giờ — `_kiem_khach_cho_lau`
    # thoát sớm khi ngoài giờ, trước cả khi chạm CSDL. Test phụ thuộc
    # đồng hồ là test làm CI đỏ ngẫu nhiên, và người ta sẽ ngừng đọc CI.
    monkeypatch.setattr(suc_khoe.gio_lam_viec, "dang_trong_gio", lambda *_: True)
    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow_gia)
    assert asyncio.run(suc_khoe._kiem_khach_cho_lau())["trang_thai"] == suc_khoe.HONG


def test_muc_khop_bang_ten_khong_theo_thu_tu():
    """Thêm một phép kiểm nữa vào giữa là thứ tự đổi. Một chốt báo động
    không được phép hỏng vì lý do đó."""
    src = inspect.getsource(canh_gac._muc_khach_cho)
    assert 'm.get("ten")' in src


def test_ngoai_gio_truc_thi_khong_bao_khach_cho(monkeypatch):
    """
    Không phải vì khách chờ ban đêm không quan trọng, mà vì báo động lúc 2
    giờ sáng cho một việc không ai làm được tới 8 giờ sáng là cách nhanh
    nhất khiến người ta tắt thông báo — rồi lần hỏng thật tiếp theo không
    ai đọc. Đúng 8 giờ, phép kiểm sống lại và báo ngay.
    """
    from agent.config import settings

    async def fetchrow_khong_duoc_goi(sql, *args):
        raise AssertionError("ngoài giờ thì không được đụng tới CSDL")

    monkeypatch.setattr(settings, "gio_lam_viec_bat", True)
    monkeypatch.setattr(suc_khoe.gio_lam_viec, "dang_trong_gio", lambda *_: False)
    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow_khong_duoc_goi)
    muc = asyncio.run(suc_khoe._kiem_khach_cho_lau())
    assert muc["trang_thai"] == suc_khoe.TOT
    assert "ngoài giờ" in muc["ghi_chu"]


def test_trong_gio_thi_van_bao_binh_thuong(monkeypatch):
    from datetime import datetime, timedelta, timezone

    async def fetchrow_gia(sql, *args):
        return {"so": 2,
                "lau_nhat": datetime.now(timezone.utc) - timedelta(minutes=40)}

    monkeypatch.setattr(suc_khoe.gio_lam_viec, "dang_trong_gio", lambda *_: True)
    monkeypatch.setattr(suc_khoe.db, "fetchrow", fetchrow_gia)
    assert asyncio.run(suc_khoe._kiem_khach_cho_lau())["trang_thai"] == suc_khoe.CANH_BAO
