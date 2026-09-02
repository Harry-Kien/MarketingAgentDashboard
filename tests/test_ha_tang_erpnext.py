"""
Hạ tầng ERPNext tự dựng: compose, nginx, script nạp danh mục, tài liệu.

Ba tệp này chuyển sang từ nhánh `shipping`, nơi chúng được viết cho một
kiến trúc ERP KHÁC (`ERP_PROVIDER`/`NEXTERP_*`). Những test dưới đây canh
đúng các chỗ đã phải sửa khi chuyển — vì lần sau ai đó chép lại từ nhánh cũ
thì sẽ chép lại nguyên cả ba lỗi.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.erpnext.yml"
NGINX = ROOT / "nginx.erpnext.conf"
TAI_LIEU = ROOT / "docs" / "huong-dan-thiet-lap-erp.md"
SCRIPT = ROOT / "scripts" / "nap_san_pham_erp.py"


# =====================================================================
#  Docker compose
# =====================================================================

def test_ba_tep_ha_tang_deu_co():
    for p in (COMPOSE, NGINX, TAI_LIEU, SCRIPT):
        assert p.exists(), p.name


def test_compose_doc_duoc_va_du_service():
    d = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert set(d["services"]) == {
        "erpnext-db", "erpnext-redis-cache", "erpnext-redis-queue",
        "erpnext-web", "erpnext-proxy",
    }


def test_khong_cong_nao_mo_ra_mang_lan():
    """
    Docker bind `0.0.0.0` theo mặc định — mở ra CẢ MẠNG LAN, và đi vòng qua
    Windows Firewall nên không hộp thoại nào hỏi.

    ERPNext giữ danh mục, giá vốn, đơn hàng và thông tin khách. Bản trên
    nhánh `shipping` để `"8080:80"`; `docker-compose.yml` của repo này buộc
    mọi dịch vụ về 127.0.0.1 kèm chú thích dài giải thích vì sao. File mới
    phải theo cùng quy ước.
    """
    d = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    for ten, dv in d["services"].items():
        for cong in dv.get("ports") or []:
            assert str(cong).startswith("127.0.0.1:"), f"{ten}: {cong}"


def test_khong_dat_mat_khau_that_trong_compose():
    """Compose đi theo repo, nên mọi giá trị trong đó là công khai."""
    text = COMPOSE.read_text(encoding="utf-8").lower()
    for dau in ("api_key", "api_secret", "token "):
        assert dau not in text, dau


# =====================================================================
#  Tài liệu — ba lỗi đã phải sửa khi chuyển nhánh
# =====================================================================

def test_khong_con_duong_dan_ca_nhan_cua_may_nguoi_viet():
    """
    Bản gốc trỏ `file:///Users/huynhlehoaibao/Documents/AIAgent_mar/...` —
    đường dẫn trên máy một người. Với mọi người khác nó vừa vô nghĩa vừa
    gây hiểu nhầm là repo nằm ở đó.
    """
    text = TAI_LIEU.read_text(encoding="utf-8")
    assert "huynhlehoaibao" not in text
    assert "file:///" not in text


def test_tai_lieu_dung_bien_moi_truong_cua_repo_nay():
    """
    Nhánh `shipping` dùng `ERP_PROVIDER` + `NEXTERP_*`. Repo này dùng
    `ERP_LOAI` + `ERPNEXT_*`. Chép nhầm thì người làm theo sẽ điền vào
    những biến không ai đọc, và không có gì báo — cấu hình đúng cú pháp,
    sai tên, im lặng.
    """
    text = TAI_LIEU.read_text(encoding="utf-8")
    assert "ERP_LOAI=erpnext" in text
    assert "ERPNEXT_URL=" in text
    assert "ERP_PROVIDER" not in text
    assert "NEXTERP_BASE_URL" not in text


def test_tai_lieu_nhac_hai_truong_bat_buoc_cua_repo_nay():
    """
    `ERP_MA_KHO` và `ERP_PRICELIST` không có trong hướng dẫn gốc, nhưng
    adapter của repo này NÉM ngay lúc khởi động nếu thiếu. Hướng dẫn không
    nhắc là người làm theo sẽ dựng xong rồi mới thấy app không lên.
    """
    text = TAI_LIEU.read_text(encoding="utf-8")
    assert "ERP_MA_KHO=" in text
    assert "ERP_PRICELIST=" in text


def test_tai_lieu_canh_bao_erp_chi_cap_nua_du_lieu():
    """
    Điểm dễ hiểu nhầm nhất: nối ERP xong tưởng là đủ. Chín trường tư vấn
    không có bên ERP, và SKU thiếu hồ sơ sẽ bị loại khỏi gợi ý — nếu tài
    liệu không nói, người dùng sẽ tưởng agent hỏng.
    """
    text = TAI_LIEU.read_text(encoding="utf-8")
    assert "nửa" in text.lower()
    assert "goi_y_san_pham" in text
    assert "erp.thieu_ho_so" in text


def test_tai_lieu_khong_tro_toi_test_khong_ton_tai():
    """Bản gốc bảo chạy `tests/test_erp_integration.py` — tệp đó không sang."""
    text = TAI_LIEU.read_text(encoding="utf-8")
    assert "test_erp_integration" not in text
    assert not (ROOT / "tests" / "test_erp_integration.py").exists()


# =====================================================================
#  Script nạp danh mục
# =====================================================================

def _chay(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "scripts.nap_san_pham_erp", *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
    )


def test_script_dung_bien_cau_hinh_cua_repo_nay():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "settings.erpnext_url" in src
    assert "nexterp_base_url" not in src


def test_script_khong_nuot_loi_im_lang():
    """
    Bản gốc có `except Exception: pass` khi tạo nhóm hàng, và KHÔNG báo gì
    khi cập nhật sản phẩm thất bại — mã lặng lẽ giữ giá cũ trong khi bản
    tổng kết vẫn in "Hoàn tất!".

    Đây đúng loại lỗi `CLAUDE.md` xếp là nguy hiểm nhất trong repo này.

    ĐỌC BẰNG AST, KHÔNG SO CHUỖI
    ----------------------------
    Bản đầu của chính test này so chuỗi, và nó đỏ vì bắt nhầm đoạn chú
    thích đang GIẢI THÍCH vì sao không dùng mẫu đó. Một phép kiểm bắt nhầm
    lời giải thích về chính nó là phép kiểm sẽ bị gỡ.
    """
    import ast

    cay = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    nuot = [
        n.lineno
        for n in ast.walk(cay)
        if isinstance(n, ast.ExceptHandler)
        and len(n.body) == 1
        and isinstance(n.body[0], ast.Pass)
    ]
    assert not nuot, f"có except...pass rỗng ở dòng {nuot}"


@pytest.mark.skipif(
    not (ROOT / "data" / "catalog.json").exists(),
    reason="chưa có catalog.json",
)
def test_chan_day_du_lieu_mau_len_erp_that():
    """
    Đẩy danh mục mẫu lên ERP thật là đưa hàng không có thật vào hệ thống
    bán hàng, rồi có người lên đơn từ đó. Cùng lý do `scripts/san_sang.py`
    coi cờ `du_lieu_mau` là việc CHẶN.
    """
    catalog = json.loads(
        (ROOT / "data" / "catalog.json").read_text(encoding="utf-8")
    )
    if catalog.get("du_lieu_mau") is not True:
        pytest.skip("catalog.json đã là dữ liệu thật")

    kq = _chay("--thu")

    assert kq.returncode == 1
    assert "du_lieu_mau" in kq.stdout


def test_che_do_thu_chay_duoc_khi_chua_cau_hinh_gi():
    """
    `--thu` không kết nối đi đâu cả. Bắt phải có API key mới xem được payload
    là chặn đúng lúc người ta cần xem nhất: TRƯỚC khi dựng ERP.
    """
    kq = _chay("--thu", "--du-lieu-mau")

    assert kq.returncode == 0, kq.stdout + kq.stderr
    assert "CHẾ ĐỘ THỬ" in kq.stdout
    assert "chưa ghi gì lên ERP" in kq.stdout
