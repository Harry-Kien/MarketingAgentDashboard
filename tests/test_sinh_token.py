"""
Kiểm thử bộ sinh bí mật. Không gọi API, không cần CSDL.

VÌ SAO CÓ SCRIPT NÀY, VÀ VÌ SAO PHẢI CANH NÓ
--------------------------------------------
Cách thường dùng — `python -c "import secrets; print(...)"` — in bí mật ra
màn hình. Nghe vô hại, nhưng nó tạo một chuỗi rò rỉ không ai để ý: lịch sử
cuộn terminal, lịch sử lệnh ghi ra đĩa, và — đã xảy ra HAI LẦN trong chính
dự án này — lọt vào ảnh chụp màn hình rồi gửi đi.

Bí mật lộ rồi không rút lại được. Cách chắc chắn duy nhất là đừng bao giờ
hiện nó ra.

Script này lại chạm vào đúng file nhạy cảm nhất của hệ thống, nên nó phải
được canh kỹ hơn mã thường.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import sinh_token as st  # noqa: E402


def _env_gia(tmp_path, noi_dung: str) -> Path:
    p = tmp_path / ".env"
    p.write_text(noi_dung, encoding="utf-8")
    return p


# =====================================================================
#  Không bao giờ in bí mật ra
# =====================================================================

def test_khong_in_gia_tri_ra_thong_bao(monkeypatch, tmp_path):
    """Lý do cả script tồn tại."""
    env = _env_gia(tmp_path, "MCP_TOKEN=cu\n")
    monkeypatch.setattr(st, "ENV", env)
    tb = st.dat("MCP_TOKEN")
    moi = dict(
        d.split("=", 1) for d in env.read_text(encoding="utf-8").splitlines() if "=" in d
    )["MCP_TOKEN"]
    assert moi not in tb, "ĐANG IN BÍ MẬT RA THÔNG BÁO"
    assert len(moi) > 20


def test_ham_dat_khong_tra_ve_gia_tri(monkeypatch, tmp_path):
    """Trả về giá trị là mời gọi người gọi in nó ra."""
    src = inspect.getsource(st.dat)
    assert "return gia_tri" not in src


# =====================================================================
#  Chỉ sửa đúng một dòng
# =====================================================================

def test_giu_nguyen_cac_khoa_khac(monkeypatch, tmp_path):
    """Ghi đè cả .env là mất mọi khoá kết nối của hệ thống."""
    env = _env_gia(tmp_path, "GCP_PROJECT_ID=abc\nMCP_TOKEN=cu\nTTS_VOICE=x\n")
    monkeypatch.setattr(st, "ENV", env)
    st.dat("MCP_TOKEN")
    s = env.read_text(encoding="utf-8")
    assert "GCP_PROJECT_ID=abc" in s
    assert "TTS_VOICE=x" in s
    assert "MCP_TOKEN=cu" not in s


def test_khoa_chua_co_thi_them_vao(monkeypatch, tmp_path):
    env = _env_gia(tmp_path, "GCP_PROJECT_ID=abc\n")
    monkeypatch.setattr(st, "ENV", env)
    st.dat("MCP_TOKEN")
    assert "MCP_TOKEN=" in env.read_text(encoding="utf-8")


def test_co_sao_luu_truoc_khi_sua(monkeypatch, tmp_path):
    env = _env_gia(tmp_path, "MCP_TOKEN=cu\n")
    monkeypatch.setattr(st, "ENV", env)
    st.dat("MCP_TOKEN")
    assert (tmp_path / ".env.bak").exists()


def test_ban_sao_luu_bi_gitignore_chan():
    """
    Bản sao lưu chứa bí mật CŨ — vẫn là bí mật, vì nó có thể còn hiệu lực ở
    nơi khác. Không chặn thì một lần `git add -A` là đẩy nó lên repo công
    khai. Đã suýt xảy ra thật ở lần chạy đầu của script này.
    """
    ig = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env.bak" in ig


# =====================================================================
#  Danh sách trắng
# =====================================================================

def test_khong_dat_khoa_la(monkeypatch, tmp_path):
    """
    Gõ nhầm tên khoá mà script vẫn ghi thì nó ghi đè GCP_PROJECT_ID bằng
    chuỗi ngẫu nhiên — và lỗi đó rất khó lần ra.
    """
    env = _env_gia(tmp_path, "GCP_PROJECT_ID=abc\n")
    monkeypatch.setattr(st, "ENV", env)
    tb = st.dat("GCP_PROJECT_ID")
    assert "Không đặt được" in tb
    assert env.read_text(encoding="utf-8") == "GCP_PROJECT_ID=abc\n"


def test_khong_co_env_thi_bao_ro(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "ENV", tmp_path / "khong-co")
    assert "cp .env.example" in st.dat("MCP_TOKEN")


def test_moi_khoa_tai_lieu_bao_sinh_deu_dat_duoc():
    """
    Ca này canh một lỗi đã xảy ra thật: `.env.example` bảo người dùng chạy
    `python -m scripts.sinh_token MESSENGER_VERIFY_TOKEN`, nhưng khoá ấy
    không có trong danh sách cho phép — lệnh trả về "Không đặt được", và
    người đang cài dừng lại giữa chừng không hiểu vì sao.

    Tài liệu hướng dẫn một lệnh thì lệnh đó phải chạy được. Quét ngược từ
    `.env.example` để lần sau thêm hướng dẫn mà quên mở khoá là đỏ ngay.
    """
    import re
    mau = re.compile(r"scripts\.sinh_token\s+([A-Z0-9_]+)")
    khai = set(mau.findall((ROOT / ".env.example").read_text(encoding="utf-8")))
    khai |= set(mau.findall((ROOT / "CLAUDE.md").read_text(encoding="utf-8")))
    thieu = sorted(k for k in khai if k not in st.CHO_PHEP)
    assert not thieu, f"tài liệu bảo sinh {thieu} nhưng script từ chối"


def test_khoa_la_van_bi_tu_choi():
    """Nới danh sách mà nới quá tay thì một lần gõ nhầm ghi đè
    GCP_PROJECT_ID bằng chuỗi ngẫu nhiên."""
    assert "Không đặt được" in st.dat("GCP_PROJECT_ID")


def test_secret_chatwoot_duoc_dong_bo_ma_khong_lo(monkeypatch, tmp_path):
    """Hai tiến trình dùng hai tên biến; giá trị phải giống tuyệt đối."""
    env = _env_gia(tmp_path, "CHATWOOT_WEBHOOK_SECRET=cu\n")
    env_cw = tmp_path / ".env.chatwoot"
    env_cw.write_text(
        "CW_WEBHOOK_URL=http://agent/webhook/chatwoot?token=lo\n"
        "CW_WEBHOOK_SECRET=cu-khac\n", encoding="utf-8"
    )
    monkeypatch.setattr(st, "ENV", env)
    monkeypatch.setattr(st, "CHATWOOT_ENV", env_cw)

    thong_bao = st.dat("CHATWOOT_WEBHOOK_SECRET")
    agent_secret = env.read_text(encoding="utf-8").split("=", 1)[1].strip()
    cw_values = dict(
        line.split("=", 1)
        for line in env_cw.read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    chatwoot_secret = cw_values["CW_WEBHOOK_SECRET"]

    assert agent_secret == chatwoot_secret
    assert agent_secret not in thong_bao
    assert (tmp_path / ".env.chatwoot.bak").exists()
    assert "đồng bộ" in thong_bao
    assert cw_values["CW_WEBHOOK_URL"] == "http://agent/webhook/chatwoot"
