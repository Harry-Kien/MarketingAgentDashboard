"""
Kiểm thử trí nhớ về khách hàng. Không gọi API model.

Trí nhớ là ranh giới giữa chatbot và agent, nhưng nó cũng là chỗ dễ tạo ra
hai loại hỏng nghiêm trọng:

  1. BỊA — ghi vào hồ sơ điều khách chưa từng nói, rồi lần sau tư vấn dựa
     trên đó. Tệ hơn quên, vì khách không biết hệ thống đang tin điều gì.
  2. KHO DỮ LIỆU NGOÀI TẦM KIỂM SOÁT — xây trí nhớ mà quên đường xoá thì
     yêu cầu xoá theo Nghị định 13/2023 chỉ dọn được một nửa.

Bộ này canh cả hai.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import du_lieu_ca_nhan  # noqa: E402
from agent.core import ho_so_khach as hs  # noqa: E402


# =====================================================================
#  Không được bịa
# =====================================================================

def test_khong_goi_model_de_trich_xuat():
    """
    Cách thường thấy là gọi thêm một lượt model "trích xuất thông tin khách
    hàng". Cách đó tốn tiền mỗi lượt VÀ bịa được. Ở đây mọi mẩu phải suy ra
    từ việc đã xảy ra hoặc từ chính chữ khách gõ.
    """
    src = inspect.getsource(hs)
    for cam in ("llm.complete", "import llm", "from .llm", "from ..core import llm"):
        assert cam not in src, f"trí nhớ đang gọi model: {cam!r} — nguồn bịa"


def test_moi_mau_deu_co_nguon_goc():
    """Không có mẩu nào được phép vô danh — phải truy được nó từ đâu ra."""
    src = inspect.getsource(hs.ghi)
    assert '"nguon": nguon' in src
    assert "if nguon not in NGUON" in src, "nguồn lạ phải bị quy về mặc định"


def test_tu_khoa_loai_da_lay_tu_catalog_khong_go_tay():
    """
    Gõ tay danh sách loại da ở đây thì thêm một loại vào danh mục phải sửa
    hai chỗ, và chỗ thứ hai sẽ bị quên.
    """
    src = inspect.getsource(hs._tu_khoa_loai_da)
    assert "catalog.json" in src
    tu = hs._tu_khoa_loai_da()
    assert "da dầu" in tu and "da nhạy cảm" in tu
    assert "mọi loại da" not in tu, "'mọi loại da' không nói gì về khách này"


def test_tu_khoa_dai_khop_truoc_tu_khoa_ngan():
    """"da hỗn hợp thiên dầu" phải thắng "da hỗn hợp" khi cả hai cùng khớp."""
    tu = hs._tu_khoa_loai_da()
    if "da hỗn hợp thiên dầu" in tu and "da hỗn hợp" in tu:
        assert tu.index("da hỗn hợp thiên dầu") < tu.index("da hỗn hợp")


# =====================================================================
#  Xếp hạng độ tin cậy
# =====================================================================

def test_mau_suy_tu_hanh_dong_duoc_uu_tien():
    """
    Chỗ ngồi trong ngữ cảnh có hạn. Khi phải bỏ bớt, mẩu suy từ hành động
    thật phải ở lại trước mẩu chỉ nghe được.
    """
    src = inspect.getsource(hs.ghi)
    assert '"hanh_dong": 3' in src and '"agent_ghi": 1' in src
    assert '"khach_noi": 2' in src


def test_gioi_han_so_mau_trong_ngu_canh():
    """Quá nhiều mẩu thì loãng và tốn token."""
    assert 1 <= hs.SO_GHI_NHO_TOI_DA <= 15
    assert "[:SO_GHI_NHO_TOI_DA]" in inspect.getsource(hs.lam_ngu_canh)


# =====================================================================
#  Ngữ cảnh
# =====================================================================

def test_ngu_canh_rong_khi_chua_biet_gi():
    """
    Khối trống vẫn tốn token và vẫn khiến model cố diễn giải. Chưa biết gì
    thì đừng chèn gì.
    """
    src = inspect.getsource(hs.lam_ngu_canh)
    assert 'return ""' in src


def test_ngu_canh_dan_model_uu_tien_loi_khach_lue_nay():
    """
    Ghi chú cũ có thể sai — khách đổi sản phẩm, da đổi tình trạng. Model
    phải tin lời khách lúc này hơn hồ sơ.
    """
    src = inspect.getsource(hs.lam_ngu_canh)
    assert "tin lời khách lúc này" in src


# =====================================================================
#  Ràng buộc bảo vệ dữ liệu cá nhân
# =====================================================================

def test_ho_so_bi_xoa_khi_khach_yeu_cau():
    """
    Xây trí nhớ mà quên đường xoá là tạo ra một kho dữ liệu cá nhân ngoài
    tầm kiểm soát — yêu cầu xoá chỉ dọn được một nửa.
    """
    src = inspect.getsource(du_lieu_ca_nhan.xoa)
    assert "ho_so_khach.xoa" in src, "luồng xoá đang bỏ sót hồ sơ ghi nhớ"
    assert "so_ho_so_xoa" in src, "phải báo cáo số hồ sơ đã xoá"


def test_xoa_theo_sdt_chuan_hoa_duoc():
    src = inspect.getsource(hs.xoa)
    assert "regexp_replace" in src, (
        "phải chuẩn hoá số trước khi tìm, nếu không yêu cầu xoá sẽ trượt"
    )


def test_xoa_khong_co_dinh_danh_thi_khong_lam_gi():
    """Gọi nhầm không được xoá sạch bảng."""
    import asyncio
    assert asyncio.run(hs.xoa()) == 0


# =====================================================================
#  Ghi trùng
# =====================================================================

def test_khong_ghi_trung_cung_mot_dieu():
    """Khách nói "da dầu" mười lần thì hồ sơ vẫn chỉ có một dòng."""
    src = inspect.getsource(hs.ghi)
    assert 'm.get("noi_dung", "").lower() == noi_dung.lower()' in src
    assert '"so_lan"' in src


@pytest.mark.parametrize("tin, mong_doi", [
    ("Em da dầu, hay bị bóng vùng chữ T", "da dầu"),
    ("Em da nhạy cảm nên hay bị đỏ", "da nhạy cảm"),
    # Cách người Việt hay viết nhất — "da khô" KHÔNG liền nhau. So khớp
    # chuỗi thô bỏ lỡ đúng những câu này.
    ("da em khô lắm ạ", "da khô"),
    ("da mình khô căng sau khi rửa", "da khô"),
    ("da của em nhạy cảm lắm", "da nhạy cảm"),
    ("da tôi hỗn hợp thiên dầu", "da hỗn hợp thiên dầu"),
])
def test_quet_duoc_loai_da_tu_loi_khach(tin, mong_doi):
    """Khớp chính chữ khách gõ, không suy diễn."""
    low = hs._go_dai_tu(tin.lower())
    khop = [t for t in hs._tu_khoa_loai_da() if t in low]
    assert khop and khop[0] == mong_doi, f"{tin!r} -> {khop}"


def test_go_dai_tu_khong_lam_hong_cau_khac():
    """Chỉ đụng cụm "da <đại từ>", không đụng chữ 'da' ở chỗ khác."""
    assert hs._go_dai_tu("da em khô") == "da khô"
    assert hs._go_dai_tu("em muốn mua kem dưỡng da") == "em muốn mua kem dưỡng da"
    assert hs._go_dai_tu("da dầu") == "da dầu"


# =====================================================================
#  Máy vừa clone repo — chỉ có catalog.example.json
# =====================================================================

def test_quet_loai_da_van_chay_khi_chi_co_ban_mau(monkeypatch, tmp_path):
    """
    LỖI NÀY ĐÃ XẢY RA THẬT, và chỉ lộ ra khi clone repo về thư mục trắng
    rồi chạy test: 7 ca đỏ trên bản clone, xanh trên máy phát triển.

    `_tu_khoa_loai_da` tự đọc thẳng `data/catalog.json`, không có đường lui
    sang bản mẫu. Máy vừa cài chỉ có `catalog.example.json` nên hàm trả về
    RỖNG — và cả nguồn "quét chính lời khách" của hồ sơ ngừng hoạt động
    trong im lặng. Khách gõ "em da dầu", hồ sơ không ghi gì, lượt sau agent
    hỏi lại đúng câu đó.

    Không có gì nổ. Không dòng nhật ký nào. Chỉ là hồ sơ trống hơn lẽ ra.
    """
    from agent.core import tools

    # Giả lập đúng máy vừa clone: catalog.json KHÔNG tồn tại.
    monkeypatch.setattr(tools, "CATALOG_PATH", tmp_path / "khong-co.json")
    monkeypatch.setattr(hs, "_TU_KHOA_DA", ())

    tu = hs._tu_khoa_loai_da()
    assert tu, "máy chỉ có bản mẫu thì bộ quét loại da chết câm"
    assert "da dầu" in tu


def test_doc_danh_muc_dung_chung_mot_cho_voi_tools():
    """
    Hai chỗ đọc cùng một file theo hai cách khác nhau thì sớm muộn cũng
    lệch — và cái lệch đó chính là lỗi ở trên.
    """
    src = inspect.getsource(hs._tu_khoa_loai_da)
    assert "tools._catalog()" in src
    # Bỏ chú thích trước khi soi: chú thích trong file này giải thích VÌ SAO
    # không tự mở `catalog.json`, nên chính nó chứa chuỗi đang bị cấm.
    ma = chr(10).join(d for d in src.splitlines() if not d.strip().startswith("#"))
    assert "read_text" not in ma, "vẫn đang tự mở file"
