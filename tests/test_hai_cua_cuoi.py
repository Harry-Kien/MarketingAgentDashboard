"""
Hai cửa cuối của đợt rà soát: đếm-trước-khi-xoá có duyệt, và sức khoẻ kênh.

Cả hai đều là endpoint đã có từ lâu mà không màn hình nào gọi — cùng lớp lỗi
đã tìm ra ở màn Nhân sự, Ca trực, Định tuyến. Test ở đây canh hai điều:
màn hình gọi ĐÚNG đường, và màn hình nói ĐÚNG SỰ THẬT về việc máy chủ làm.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_man_nhat_ky_co_danh_sach_yeu_cau_va_ba_hanh_dong():
    assert 'id="dsRetention"' in HTML
    assert '"/data-retention/jobs"' in JS
    for hanh_dong in ("approve", "execute-dry-run", "cancel"):
        assert hanh_dong in JS


def test_man_hinh_khong_hua_xoa_that():
    """
    Khối này CẤP PHIẾU, không xoá. Máy chủ vẫn không có bộ thực thi xoá cho
    luồng `data-retention/jobs` — việc xoá thật nằm ở khung PDPD phía trên,
    và từ migration 0026 nó đòi một phiếu đã duyệt.

    Màn hình mà ghi "xoá có duyệt" ngay tại khối này là hứa một việc không
    xảy ra ở đây, và người vận hành sẽ tin dữ liệu đã bị xoá trong khi nó
    vẫn còn nguyên.
    """
    khoi = HTML[HTML.index('id="dsRetention"') - 1500:HTML.index('id="dsRetention"')]
    assert "Phiếu duyệt xoá" in khoi
    assert "khung trên" in khoi, "phải chỉ ra chỗ việc xoá thật xảy ra"


def test_nut_xoa_that_bi_khoa_boi_phieu_duyet():
    """
    Chốt bốn mắt phải nằm ở CẢ hai phía, và phía máy chủ mới là phía tính.

    Giao diện ẩn nút để không có cú bấm chắc chắn thất bại; nếu chỉ có giao
    diện thì một lời gọi API thẳng vẫn xoá được, và đó đúng là tình trạng
    trước migration 0026.
    """
    from agent.core import du_lieu_ca_nhan

    assert "_gianh_phieu_duyet" in (ROOT / "agent" / "core" / "du_lieu_ca_nhan.py").read_text(
        encoding="utf-8")
    assert hasattr(du_lieu_ca_nhan, "ChuaDuyet")

    routes = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    assert "du_lieu_ca_nhan.ChuaDuyet" in routes, "route phải đổi lỗi chưa-duyệt thành 409"

    # Và giao diện vẽ khối xoá theo trạng thái phiếu, không vẽ sẵn nút đỏ.
    assert "function pdpdKhoiXoa" in JS
    assert "pd.xoa_duoc" in JS


def test_yeu_cau_tu_ho_so_khach_luon_la_dry_run():
    """
    dry_run=false tạo một yêu cầu mãi mãi "đã duyệt" mà không bao giờ chạy —
    vì không có gì chạy nó. Màn hình không được gửi giá trị ấy.
    """
    doan = JS[JS.index("async function rtYeuCauDem"):]
    doan = doan[:doan.index("\n}\n")]
    assert "dry_run: true" in doan
    assert "dry_run: false" not in doan
    assert 'data-contact-rt' in JS


def test_nguoi_tao_khong_thay_nut_duyet():
    """Máy chủ chặn tự duyệt (409). Ẩn nút với người tạo để không có cú bấm chắc chắn thất bại."""
    doan = JS[JS.index("async function loadRetention"):]
    doan = doan[:doan.index("\n}\n")]
    assert "cua_toi" in doan and "if (!cua_toi) nut.push" in doan


def test_the_kenh_co_nut_suc_khoe_goi_dung_duong():
    assert 'data-health="${account.id}"' in JS
    assert "/channel-accounts/${id}/health" in JS


def test_hai_duong_moi_khong_con_mo_coi():
    """
    Chạy lại phép quét "endpoint không màn hình nào gọi" cho đúng hai đường
    này. Đây là chốt có nghĩa nhất của file: nó nói cả hai cửa đã mở.
    """
    # Qua tiền tố `tests.` để chốt requirements nhận ra đây là mã nội bộ,
    # không phải một gói bên ngoài chưa khai.
    from tests.test_dashboard_goi_dung_duong import (DONG, _co_tren_may_chu,
                                                    duong_dashboard_goi)

    # Bộ so là MỘT CHIỀU: đối số đầu là đường JS (đoạn `DONG` khớp mọi
    # thứ), đối số sau là mẫu máy chủ (`{x}` khớp mọi thứ). Dashboard gọi
    # `jobs/${id}/${duong}` — đoạn hành động là ĐỘNG phía JS, nên phải để
    # đường JS ở vai JS. Đảo vai là "approve" bị so bằng với `DONG` và trượt.
    goi = [d.strip("/").split("/") for d in duong_dashboard_goi()]
    assert DONG  # bộ đọc phải còn đánh dấu đoạn động
    for mau in ("api/data-retention/jobs",
                "api/data-retention/jobs/{id}/approve",
                "api/channel-accounts/{id}/health",
                "api/contacts/{id}/retention-jobs"):
        assert any(_co_tren_may_chu(g, [mau.split("/")]) for g in goi), (
            f"dashboard chưa gọi {mau}")
