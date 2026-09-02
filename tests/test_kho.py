"""
Kiểm thử kho hàng và công cụ gửi ảnh. Không gọi API model.

Kho là chỗ sai thì khách chịu hậu quả trực tiếp: được xác nhận đơn cho món
đã hết, rồi nhận một cuộc gọi xin lỗi. Bốn thứ được canh:

  1. Trừ kho phải NGUYÊN TỬ và có khoá hàng — hai khách cùng chốt món cuối
     trong một giây là chuyện có thật.
  2. Trừ được HẾT hoặc KHÔNG TRỪ GÌ — trừ nửa lô rồi hết hàng ở món thứ ba
     để lại một đơn dở dang và một kho sai số.
  3. Huỷ đơn phải TRẢ HÀNG VỀ, và không trả trùng.
  4. Mọi thay đổi phải vào sổ — kho LUÔN lệch, không có sổ thì không truy
     được lệch từ đâu.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api import routes  # noqa: E402
from agent.core import kho, tools  # noqa: E402


# =====================================================================
#  Trừ kho: nguyên tử, có khoá, hết-hoặc-không
# =====================================================================

def test_tru_kho_co_khoa_hang():
    """
    Không khoá thì hai khách cùng chốt món cuối đều được xác nhận, và một
    người sẽ nhận cuộc gọi xin lỗi.
    """
    src = inspect.getsource(kho.giu_hang)
    assert "FOR UPDATE" in src, "thiếu khoá hàng — bán quá tồn khi có hai đơn cùng lúc"
    assert "conn.transaction()" in src


def test_kiem_du_ca_lo_truoc_khi_tru_bat_ky_mon_nao():
    """Trừ nửa lô rồi hết hàng ở món sau là để lại đơn dở dang và kho sai."""
    src = inspect.getsource(kho.giu_hang)
    vi_tri_kiem = src.index("return False")
    vi_tri_tru = src.index("so_luong = so_luong - ")
    assert vi_tri_kiem < vi_tri_tru, "đang trừ trước khi kiểm đủ cả lô"


def test_don_hang_bi_xoa_neu_khong_du_kho():
    """
    Kiểm tồn lúc đọc không đủ: giữa lúc đọc và lúc ghi, khách khác có thể
    đã lấy mất món cuối. Không đủ thì phải huỷ luôn đơn vừa tạo — thà không
    có đơn còn hơn có đơn cho hàng không tồn tại.
    """
    src = inspect.getsource(tools._tao_don_hang)
    khoi = src[src.index("kho.giu_hang"):][:400]
    assert "DELETE FROM orders" in khoi


def test_cot_so_luong_khong_bao_gio_am():
    schema = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
    assert "so_luong     INT NOT NULL DEFAULT 0 CHECK (so_luong >= 0)" in schema


# =====================================================================
#  Trả hàng khi huỷ đơn
# =====================================================================

def test_huy_don_tra_hang_ve_kho():
    """
    Không trả lại thì mỗi đơn huỷ ăn mất tồn kho vĩnh viễn — bán mười đơn
    huỷ chín đơn là kho báo hết trong khi hàng nằm nguyên trên kệ.
    """
    src = inspect.getsource(routes.cancel_order)
    assert "kho.tra_hang" in src


def test_khong_tra_trung():
    src = inspect.getsource(kho.tra_hang)
    assert "da_hoan" in src and "return 0" in src


def test_tra_hang_doc_tu_so_khong_doc_tu_don():
    """
    Sổ ghi CHÍNH XÁC đã trừ bao nhiêu. Đơn có thể đã bị sửa, sổ thì không.
    """
    src = inspect.getsource(kho.tra_hang)
    assert "FROM kho_bien_dong" in src
    assert "FROM orders" not in src


def test_huy_don_hai_lan_khong_tra_kho_hai_lan():
    src = inspect.getsource(routes.cancel_order)
    assert "trang_thai <> 'da_huy'" in src, (
        "huỷ lại đơn đã huỷ sẽ trả kho lần nữa và thổi phồng tồn kho"
    )


# =====================================================================
#  Sổ biến động
# =====================================================================

@pytest.mark.parametrize("ham", [kho.giu_hang, kho.tra_hang,
                                 kho.nhap_hang, kho.dieu_chinh])
def test_moi_thay_doi_deu_vao_so(ham):
    assert "kho_bien_dong" in inspect.getsource(ham), (
        f"{ham.__name__} đổi tồn kho mà không ghi sổ — không truy được"
    )


def test_kiem_ke_bat_buoc_co_ly_do():
    """Kho LUÔN lệch. Cần đường sửa hợp lệ, nhưng phải nói được vì sao."""
    src = inspect.getsource(kho.dieu_chinh)
    assert "bắt buộc phải có lý do" in src


# =====================================================================
#  Tồn kho sống chồng lên danh mục
# =====================================================================

def test_danh_muc_song_dung_so_tu_csdl():
    src = inspect.getsource(tools._catalog_song)
    assert "kho.lay_tat_ca" in src
    assert 'sp["ton_kho"] = song[sp["ma"]]' in src


def test_run_tool_doc_danh_muc_song():
    """
    Đọc file tĩnh thì agent trả lời bằng con số của ngày file được viết ra,
    và xác nhận đơn cho món đã hết từ lâu.
    """
    src = inspect.getsource(tools.run_tool)
    assert "await _catalog_song()" in src


def test_hong_csdl_thi_roi_ve_so_trong_file():
    """Thà số cũ còn hơn không có gì — chốt tồn lúc chốt đơn vẫn chặn được."""
    src = inspect.getsource(tools._catalog_song)
    assert "except Exception" in src and "return data" in src


# =====================================================================
#  Công cụ gửi ảnh
# =====================================================================

def test_co_cong_cu_gui_anh():
    assert any(t["name"] == "gui_anh_san_pham" for t in tools.TOOLS)


def test_tool_khong_tu_gui_anh():
    """
    Tool không biết mình đang chạy trên Zalo hay Chatwoot, và không nên
    biết. Nó chỉ báo đường dẫn; lớp kênh mới gửi.
    """
    src = inspect.getsource(tools.run_tool)
    khoi = src[src.index('if name == "gui_anh_san_pham"'):][:900]
    assert "send_file" not in khoi and "adapter" not in khoi


def test_ma_thieu_anh_phai_KHAI_ra_ly_do():
    """
    Hứa gửi ảnh rồi báo không có ảnh là tệ hơn không nhắc tới ảnh.

    PHÂN BIỆT "QUÊN" VỚI "ĐÃ KHAI LÀ CHƯA CÓ"
    -----------------------------------------
    Bản trước đòi MỌI mã phải có ảnh. Nhưng có mã thiếu ảnh một cách CÓ CHỦ
    Ý: `BLA-FACE-SCRUB-120G` từng chứa một banner quảng cáo mang huy hiệu
    GMP/FDA — tôi giữ nó lại thay vì gửi cho khách, và ghi lý do vào
    `manifest.json` với `nguon: "chua_co"`.

    Bắt ca đó phải đỏ là ép người ta hoặc nhét đại một tấm ảnh vào, hoặc gỡ
    phép kiểm. Cả hai đều tệ hơn hiện trạng.

    Nên ràng buộc đúng không phải "mã nào cũng có ảnh", mà là "mã nào thiếu
    ảnh thì phải khai ra trong manifest". Quên vẫn đỏ; biết và ghi lại thì
    không.
    """
    catalog = tools._catalog()
    khong_khai = []
    for p in catalog.get("san_pham", []):
        ma = p["ma"]
        if tools._anh_san_pham(ma) is not None:
            continue
        if tools._nguon_anh(ma) == "chua_co":
            continue          # đã khai, có lý do ghi trong manifest
        khong_khai.append(ma)
    assert not khong_khai, (
        f"thiếu ảnh mà KHÔNG khai lý do: {khong_khai} — "
        'thêm manifest.json với nguon: "chua_co" và ghi_chu nói rõ vì sao'
    )


def test_khong_co_anh_thi_noi_that():
    src = inspect.getsource(tools.run_tool)
    khoi = src[src.index('if name == "gui_anh_san_pham"'):][:900]
    assert "Chưa có ảnh" in khoi and '"gui_duoc": False' in khoi


def test_ten_mo_ho_thi_hoi_lai_khong_doan():
    """Gửi nhầm ảnh sản phẩm khác còn tệ hơn không gửi."""
    src = inspect.getsource(tools.run_tool)
    khoi = src[src.index('if name == "gui_anh_san_pham"'):][:900]
    assert "< 0.5" in khoi and "Hỏi lại tên" in khoi


def test_anh_di_sau_loi():
    """
    Nhận ảnh trước khi biết đó là gì thì khách phải tự đoán. Nhận lời trước
    rồi thấy ảnh mới là thứ tự tự nhiên của người bán hàng.
    """
    from agent import main as app_main
    src = inspect.getsource(app_main.handle_inbound)
    assert src.index("_gui_nhu_nguoi") < src.index("reply.anh_can_gui")


def test_manifest_ghi_ro_anh_do_model_sinh():
    """
    Ảnh hiện tại do model sinh, chưa phải ảnh chụp thật. Manifest phải nói
    rõ để không ai đem đi bán hàng mà tưởng là ảnh sản phẩm thật.
    """
    mf = ROOT / "data" / "products" / "AS-SR01" / "manifest.json"
    if not mf.exists():
        pytest.skip("chưa có manifest")
    d = json.loads(mf.read_text(encoding="utf-8"))
    assert "KHÔNG phải ảnh chụp sản phẩm thật" in d.get("ghi_chu", "")
