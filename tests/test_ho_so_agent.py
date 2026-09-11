"""
Hồ sơ agent — nhiều "nhân sự số" theo cấu hình.

RÀNG BUỘC TRUNG TÂM: CẤU HÌNH CHỈ ĐƯỢC SIẾT, KHÔNG ĐƯỢC NỚI.

`CLAUDE.md` viết: ràng buộc nằm trong MÃ, không nằm trong prompt. Sáu lớp
lưới trong `agent/core/agent.py` canh luật quảng cáo mỹ phẩm và ranh giới
tư vấn y tế.

Nếu một hồ sơ agent hạ được ngưỡng tự tin, nâng được trần chi phí, hoặc
thay được `SYSTEM`, thì một ô nhập trên dashboard vừa trở thành đường đi
vòng qua sáu lớp lưới ấy — và người điền ô đó không hề biết mình đang làm
vậy. Không nổ, không nhật ký, và chỉ lộ ra bằng một câu trả lời sai luật
gửi cho khách thật.

File này canh đúng điều đó.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from agent.config import settings  # noqa: E402
from agent.core import agent_ho_so as hs  # noqa: E402


def _dong(**doi):
    d = {"id": "11111111-1111-1111-1111-111111111111", "ten": "Thử",
         "huong_dan": "", "nguong_tu_tin": None, "tran_chi_phi": None}
    d.update(doi)
    return d


# =====================================================================
#  Chỉ được SIẾT
# =====================================================================

def test_nguong_tu_tin_LONG_hon_toan_cuc_bi_ep_len():
    """
    Ngưỡng CAO = chuyển người SỚM. Hồ sơ đặt thấp hơn toàn cục là đòi agent
    tự trả lời ở những câu mà toàn cục đã bảo phải chuyển người.
    """
    thap = max(0.0, float(settings.confidence_floor) - 0.3)
    ket = hs.siet(_dong(nguong_tu_tin=thap))
    assert ket.nguong_tu_tin == float(settings.confidence_floor)


def test_nguong_tu_tin_CHAT_hon_toan_cuc_duoc_giu():
    """Siết thêm thì được — đó là lý do khối này tồn tại."""
    cao = min(1.0, float(settings.confidence_floor) + 0.2)
    ket = hs.siet(_dong(nguong_tu_tin=cao))
    assert ket.nguong_tu_tin == cao


def test_tran_chi_phi_CAO_hon_toan_cuc_bi_ep_xuong():
    """
    Trần THẤP = dừng SỚM. Hồ sơ đặt cao hơn toàn cục là cho một kênh tiêu
    quá mức trần mà người vận hành đã đặt cho cả hệ thống.
    """
    cao = float(settings.max_cost_per_conversation) * 10
    ket = hs.siet(_dong(tran_chi_phi=cao))
    assert ket.tran_chi_phi == float(settings.max_cost_per_conversation)


def test_tran_chi_phi_THAP_hon_toan_cuc_duoc_giu():
    thap = float(settings.max_cost_per_conversation) / 2
    ket = hs.siet(_dong(tran_chi_phi=thap))
    assert ket.tran_chi_phi == thap


def test_khong_dat_gi_thi_dung_nguong_toan_cuc():
    ket = hs.siet(_dong())
    assert ket.nguong_tu_tin == float(settings.confidence_floor)
    assert ket.tran_chi_phi == float(settings.max_cost_per_conversation)


def test_mac_dinh_mang_dung_nguong_toan_cuc():
    """
    Mặc định KHÔNG phải hồ sơ "rỗng" — nó mang đúng ngưỡng toàn cục, nên mã
    gọi không phải rẽ nhánh `if ho_so is None` ở mọi chỗ dùng. Rẽ nhánh ở
    nhiều chỗ là chỗ để một nhánh bị quên.
    """
    m = hs.mac_dinh()
    assert m.nguong_tu_tin == float(settings.confidence_floor)
    assert m.tran_chi_phi == float(settings.max_cost_per_conversation)
    assert m.huong_dan == ""


# =====================================================================
#  Hồ sơ KHÔNG được chạm vào SYSTEM
# =====================================================================

def test_ho_so_khong_co_o_nao_thay_duoc_SYSTEM():
    """
    `SYSTEM` chứa mọi câu cấm. Nếu hồ sơ có một trường nào ghi đè được nó
    thì một ô nhập trên dashboard gỡ được các câu ấy.
    """
    assert set(hs.HoSo._fields) == {
        "id", "ten", "huong_dan", "nguong_tu_tin", "tran_chi_phi"}
    nguon = (ROOT / "agent" / "core" / "agent_ho_so.py").read_text(encoding="utf-8")
    # Không được có chỗ nào GÁN cho SYSTEM.
    assert "SYSTEM =" not in nguon
    assert "SYSTEM=" not in nguon


def test_migration_khong_co_cot_thay_the_system():
    sql = (ROOT / "agent" / "migrations" / "versions"
           / "0024_ho_so_agent.sql").read_text(encoding="utf-8")
    for cam in ("system_prompt", "prompt_thay_the", "thay_system"):
        assert cam not in sql, f"bảng hồ sơ không được có cột {cam}"


def test_huong_dan_vao_KHOI_BIEN_DONG_khong_vao_SYSTEM():
    """
    Hai lý do, cả hai đều thật: an toàn (không gỡ được câu cấm) và tiền
    (mỗi hồ sơ một `SYSTEM` là mỗi kênh một điểm cache prefix riêng).
    """
    nguon = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    vt = nguon.index("agent_ho_so.khoi_huong_dan(")
    doan = nguon[vt - 200:vt + 260]
    assert "context = f\"{context}{khoi_hs}\"" in doan, (
        "hướng dẫn hồ sơ phải nối vào `context` (khối biến động), "
        "không vào SYSTEM")
    # Và `llm.cached_system(SYSTEM, ...)` vẫn nhận đúng hằng SYSTEM.
    assert "llm.cached_system(SYSTEM, context)" in nguon


def test_khoi_huong_dan_co_dong_phan_tach_va_nhan_noi_bo():
    """
    Ghép suông thì mô hình đọc cả khối như một tài liệu tra được và trích
    nguyên văn hướng dẫn cho khách — lộ cách vận hành, và câu trả lời nghe
    như đọc quy trình nội bộ. Cùng lý lẽ với hướng dẫn gói kỹ năng.
    """
    khoi = hs.khoi_huong_dan(hs.HoSo(
        id="x", ten="Bán hàng Zalo", huong_dan="Nói ngắn, chốt đơn nhanh.",
        nguong_tu_tin=0.6, tran_chi_phi=0.2))
    assert "---" in khoi
    assert "HƯỚNG DẪN NỘI BỘ" in khoi
    assert "không phải tài liệu để trích dẫn" in khoi
    assert "Bán hàng Zalo" in khoi


def test_huong_dan_rong_thi_khong_chen_gi():
    """Chèn một khối rỗng là thêm nhiễu vào prompt mà không mang tin gì."""
    assert hs.khoi_huong_dan(hs.mac_dinh()) == ""


# =====================================================================
#  Sáu lớp lưới vẫn chạy với MỌI hồ sơ
# =====================================================================

def test_buoc_chuyen_khong_phu_thuoc_ho_so():
    """
    `_bat_buoc_chuyen` đọc THẲNG câu hỏi, không đọc hồ sơ nào. Nếu nó nhận
    hồ sơ làm tham số thì sẽ có ngày một hồ sơ tắt được nó.
    """
    import inspect

    from agent.core import agent as brain

    ky = inspect.signature(brain._bat_buoc_chuyen).parameters
    assert set(ky) == {"question"}, (
        "_bat_buoc_chuyen chỉ được nhận câu hỏi — thêm tham số nào khác là "
        "mở đường cho cấu hình tắt lưới")


def test_respond_dung_nguong_cua_HO_SO_da_siet():
    """
    Nếu `respond` vẫn đọc `settings.confidence_floor` thì hồ sơ siết thêm
    cũng không có tác dụng — khối này thành trang trí.
    """
    nguon = (ROOT / "agent" / "core" / "agent.py").read_text(encoding="utf-8")
    assert "confidence < hs.nguong_tu_tin" in nguon
    assert "spent >= hs.tran_chi_phi" in nguon
    assert "confidence < settings.confidence_floor" not in nguon
    assert "spent >= settings.max_cost_per_conversation" not in nguon


def test_main_truyen_ho_so_theo_kenh():
    """
    Mã trong `agent.py` đúng mà `main.py` không truyền hồ sơ vào thì mọi
    kênh chạy bằng mặc định — và test ở trên vẫn xanh.
    """
    nguon = (ROOT / "agent" / "main.py").read_text(encoding="utf-8")
    assert "agent_ho_so.cho_kenh(msg.account_id)" in nguon
    assert "ho_so=ho_so" in nguon
