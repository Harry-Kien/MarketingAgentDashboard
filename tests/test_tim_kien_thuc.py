"""
Kiểm thử công cụ tra kho tri thức. Không gọi API, không cần CSDL.

VÌ SAO CÔNG CỤ NÀY TỒN TẠI
--------------------------
Trước nó, RAG chạy đúng MỘT lần, trước khi model nói câu đầu tiên:

    passages = await rag.retrieve(question, k=5)   # một lần, hết
    for _ in range(MAX_TOOL_ROUNDS): ...

Nghĩa là tài liệu tham chiếu được chọn theo câu hỏi ĐẦU lượt và đóng băng ở
đó. Khách hỏi serum ba câu rồi lượt thứ tư quay sang "shop đổi trả mấy
ngày ạ" — agent vẫn đang cầm mấy đoạn nói về serum, và không có cách nào đi
tìm đoạn nói về đổi trả. Nó chỉ còn hai lối: đoán, hoặc chuyển người cho
một câu mà tài liệu công ty trả lời được.

CHỖ NGUY HIỂM NHẤT CỦA THAY ĐỔI NÀY
-----------------------------------
`_confidence()` cộng thưởng lên 0.8 khi đã gọi tool. Nếu `tim_kien_thuc`
cũng được cộng thưởng ấy, thì một lần tra KHÔNG TÌM THẤY GÌ sẽ đẩy độ tin
cậy từ 0 lên 0.8 — và chốt chuyển người vì tin cậy thấp không bao giờ nổ
nữa. Agent tra hụt lại trông tự tin hơn agent không thèm tra.

Đó đúng là xanh giả: thưởng cho hành vi mình muốn ngăn. Nửa số ca dưới đây
canh riêng chuyện đó.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core import agent as ag  # noqa: E402
from agent.core import rag, tools  # noqa: E402


def _doan(ten="Chính sách thương mại", diem=0.71):
    return rag.Passage(doc_title=ten, content="Đổi trả trong 7 ngày.", score=diem)


# =====================================================================
#  Hợp đồng công cụ
# =====================================================================

def test_tool_co_trong_danh_sach_gui_cho_model():
    ten = [t["name"] for t in tools.TOOLS]
    assert "tim_kien_thuc" in ten


def test_mo_ta_noi_ro_khong_duoc_doan():
    """Model đọc mô tả này nhiều hơn đọc prompt. Câu cấm đoán phải nằm ngay
    trong đó, không chỉ nằm ở system.md."""
    t = next(t for t in tools.TOOLS if t["name"] == "tim_kien_thuc")
    mo_ta = t["description"].lower()
    assert "không đoán" in mo_ta or "không được đoán" in mo_ta
    # Và nói rõ nó KHÔNG phải nơi tra giá — nếu không, model sẽ thử tra giá
    # ở đây và nhận về tài liệu marketing thay vì con số thật.
    assert "giá" in mo_ta


def test_thieu_cau_hoi_thi_khong_no(monkeypatch):
    kq = asyncio.run(tools.run_tool("tim_kien_thuc", {}))
    assert kq["tim_thay"] is False


def test_khong_tim_thay_thi_noi_ro_phai_lam_gi(monkeypatch):
    """
    Trả về dict rỗng thì model tự nghĩ ra đường đi, và đường nó hay chọn là
    đoán bừa. Kết quả rỗng phải kèm chỉ dẫn.
    """
    async def rong(_q, k=5, min_score=0.35):
        return []
    monkeypatch.setattr(rag, "retrieve", rong)

    kq = asyncio.run(tools.run_tool("tim_kien_thuc", {"cau_hoi": "bảo hành mấy năm"}))
    assert kq["tim_thay"] is False
    ghi = kq["ghi_chu"].lower()
    assert "không được đoán" in ghi
    assert "chuyen_nhan_vien" in ghi
    assert "đừng tra lại" in ghi, "thiếu câu này thì model tra vòng tới hết trần chi phí"


def test_tim_thay_thi_tra_ve_doan_kem_ten_tai_lieu(monkeypatch):
    async def co(_q, k=5, min_score=0.35):
        return [_doan()]
    monkeypatch.setattr(rag, "retrieve", co)

    kq = asyncio.run(tools.run_tool("tim_kien_thuc", {"cau_hoi": "đổi trả"}))
    assert kq["tim_thay"] is True
    assert kq["doan"][0]["tai_lieu"] == "Chính sách thương mại"
    assert "7 ngày" in kq["doan"][0]["noi_dung"]


def test_doan_dai_bi_cat(monkeypatch):
    """Mỗi vòng lặp thêm đều tính tiền. Đoạn không giới hạn là hoá đơn không
    giới hạn."""
    async def dai(_q, k=5, min_score=0.35):
        return [rag.Passage(doc_title="X", content="a" * 5000, score=0.7)]
    monkeypatch.setattr(rag, "retrieve", dai)

    kq = asyncio.run(tools.run_tool("tim_kien_thuc", {"cau_hoi": "x"}))
    assert len(kq["doan"][0]["noi_dung"]) <= tools.TIM_DAI_TOI_DA


def test_khong_doc_catalog_khi_chi_hoi_chinh_sach(monkeypatch):
    """
    Câu hỏi chính sách không cần danh mục. Nạp catalog cho mỗi lần tra là
    công vô ích, và trên máy chưa có `data/catalog.json` thì nó còn là một
    đường hỏng không cần thiết.
    """
    async def no(*_a, **_k):
        raise AssertionError("không được đọc catalog cho tim_kien_thuc")
    monkeypatch.setattr(tools, "_catalog_song", no)

    async def co(_q, k=5, min_score=0.35):
        return [_doan()]
    monkeypatch.setattr(rag, "retrieve", co)

    kq = asyncio.run(tools.run_tool("tim_kien_thuc", {"cau_hoi": "đổi trả"}))
    assert kq["tim_thay"] is True


# =====================================================================
#  XANH GIẢ: tra hụt không được làm agent tự tin hơn
# =====================================================================

def test_tra_tai_lieu_KHONG_duoc_cong_thuong_do_tin_cay():
    """
    Ca quan trọng nhất file này.

    `tim_kien_thuc` nằm trong `_TOOL_TRA_TAI_LIEU`, nên nó không bật cờ
    `co_du_lieu`. Đoạn nó tìm được tự nâng độ tin cậy qua điểm khớp của
    chính chúng — đúng như lượt tra sẵn đầu lượt. Tra hụt thì không nâng gì.
    """
    assert "tim_kien_thuc" in ag._TOOL_TRA_TAI_LIEU


def test_tra_hut_thi_do_tin_cay_van_bang_khong():
    """Không tìm thấy gì mà độ tin cậy vẫn 0.8 thì chốt chuyển người vì tin
    cậy thấp không bao giờ nổ nữa."""
    assert ag._confidence([], co_du_lieu=False) == 0.0


def test_tool_du_lieu_that_van_duoc_cong_thuong():
    """Vế còn lại: siết quá tay thì `tra_cuu_san_pham` cũng mất thưởng, và
    agent chuyển người cả những câu nó vừa tra ra số thật."""
    assert ag._confidence([], co_du_lieu=True) == 0.8


def test_doan_tim_them_nang_do_tin_cay_dung_bang_diem_khop():
    """Tìm ra đúng tài liệu thì phải được ghi nhận — không thì agent tra
    xong lại bị phạt, và lần sau nó học được cách đừng tra."""
    assert ag._confidence([_doan(diem=0.71)], co_du_lieu=False) == 0.71


def test_moi_tool_khac_deu_la_tool_du_lieu():
    """
    `_TOOL_TRA_TAI_LIEU` là danh sách LOẠI TRỪ. Thêm một tool tra tài liệu
    nữa mà quên ghi vào đây thì nó lặng lẽ được cộng thưởng — không nổ,
    không nhật ký. Ca này bắt người thêm tool phải nghĩ tới việc đó.
    """
    ten = {t["name"] for t in tools.TOOLS}
    assert ag._TOOL_TRA_TAI_LIEU <= ten, "có tên trong danh sách loại trừ mà không phải tool"
    du_lieu = ten - ag._TOOL_TRA_TAI_LIEU
    assert du_lieu == {
        "tra_cuu_san_pham", "goi_y_san_pham", "gui_anh_san_pham",
        "tra_cuu_don_hang", "tra_cuu_van_chuyen", "tao_video", "tao_don_hang",
        "chuyen_nhan_vien",
        # xin_huy_don: `da_ghi_nhan` phản ánh một dòng CSDL THẬT bị sửa —
        # False nghĩa là không có đơn nào khớp, chứ không phải "chưa thử".
        # Nên nó là tool dữ liệu, đúng như phân loại mặc định ở đây.
        "xin_huy_don",
    }, "danh sách tool đổi — hãy xác nhận tool mới có trả về DỮ LIỆU THẬT không"


# =====================================================================
#  Nhập đoạn tìm thêm vào cùng rổ căn cứ
# =====================================================================

def test_vong_lap_nhap_doan_tim_duoc_vao_passages():
    src = __import__("inspect").getsource(ag.respond)
    assert "passages.append" in src, (
        "đoạn agent tự tra không vào rổ căn cứ thì sources thiếu trích dẫn "
        "và grounded sai"
    )


def test_sources_khong_lap_ten_tai_lieu():
    """Tra sẵn và tra thêm có thể ra cùng một tài liệu. Trích dẫn hiện hai
    lần cùng một tên trông như lỗi."""
    src = __import__("inspect").getsource(ag.respond)
    assert "dict.fromkeys" in src
