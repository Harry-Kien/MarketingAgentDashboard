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
