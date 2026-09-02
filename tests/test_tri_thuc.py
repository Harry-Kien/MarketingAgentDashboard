"""
Kiểm thử khung kho tri thức theo ngành. Không gọi API, không cần CSDL.

Ràng buộc quan trọng nhất được canh ở đây: MÁY KHÔNG ĐƯỢC SINH NỘI DUNG.
Nếu một ngày nào đó ai đó thấy khung rỗng "bất tiện" và cho model tự điền,
những test này phải đỏ — vì lúc đó kho tri thức thôi là căn cứ và trở
thành phỏng đoán có định dạng đẹp.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.tri_thuc import (  # noqa: E402
    DAU_CHUA_DIEN,
    da_dien_du,
    loc_tep_nap_duoc,
    sinh,
    thieu_o_dau,
)
from agent.tri_thuc.nganh import KHUNG_THEO_MA, lay  # noqa: E402


# =====================================================================
#  Khung ngành
# =====================================================================

def test_co_it_nhat_hai_nganh():
    """Một ngành thì không chứng minh được ranh giới ngành có hoạt động."""
    assert len(KHUNG_THEO_MA) >= 2


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_moi_khung_du_tai_lieu_va_cau_hoi(ma):
    k = lay(ma)
    assert len(k.tai_lieu) >= 5, ma
    assert k.tong_cau_hoi() >= 20, ma


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_moi_nganh_co_tai_lieu_ve_ranh_gioi_an_toan(ma):
    """
    Mọi ngành bán hàng có tư vấn đều chạm một ranh giới không được vượt.

    Mỹ phẩm chạm ranh giới y tế qua bệnh da; đồ thể thao chạm đúng ranh
    giới ấy qua chấn thương và thực phẩm bổ sung. Khung nào thiếu tài liệu
    này là khung sẽ đẻ ra một agent không biết lúc nào phải dừng lại.
    """
    k = lay(ma)
    assert any("an-toan" in t.ten_tep for t in k.tai_lieu), ma


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_moi_nganh_co_tai_lieu_du_lieu_ca_nhan(ma):
    """NĐ 13/2023 áp cho mọi ngành, không riêng mỹ phẩm."""
    k = lay(ma)
    assert any("du-lieu-ca-nhan" in t.ten_tep for t in k.tai_lieu), ma


def test_ma_nganh_la_thi_nem_chu_khong_roi_ve_mac_dinh():
    """
    Gõ nhầm `the_thaoo` mà rơi về mỹ phẩm là sinh cả một kho sai ngành
    trông như đúng. Nổ to lúc gõ lệnh rẻ hơn nhiều.
    """
    with pytest.raises(ValueError):
        lay("the_thaoo")


# =====================================================================
#  RÀNG BUỘC CỐT LÕI: máy sinh câu hỏi, không sinh câu trả lời
# =====================================================================

@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_moi_muc_sinh_ra_deu_la_cau_hoi_chua_dien(ma, tmp_path):
    """
    Mọi mục trong tệp sinh ra phải là chỗ trống, không phải nội dung.

    Đây là ràng buộc quan trọng nhất của cả module. Bỏ nó đi thì agent
    trích dẫn một tài liệu do máy viết và gọi đó là căn cứ.
    """
    khung = lay(ma)
    sinh(khung, tmp_path)
    for tep in tmp_path.glob("*.md"):
        noi_dung = tep.read_text(encoding="utf-8")
        assert DAU_CHUA_DIEN in noi_dung, tep.name
        assert not da_dien_du(noi_dung), tep.name


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_khung_khong_chua_dong_van_xuoi_nao(ma, tmp_path):
    """
    Không một dòng văn xuôi tự do nào được lọt vào khung.

    Đây là dạng chặt hơn của "máy không sinh nội dung", và chặt đúng chỗ:
    mọi dòng trong tệp sinh ra phải là TIÊU ĐỀ, phần trong khối chú thích,
    hoặc dòng [CẦN NGƯỜI ĐIỀN: ...]. Không có chỗ thứ tư.

    Bản đầu của test này cấm chữ số, và nó đỏ vì câu hỏi "nhóm khách nào
    không được tư vấn (dưới 18 tuổi...)" — một GỢI Ý trong câu hỏi, không
    phải một khẳng định về cửa hàng. Cấm chữ số là cấm nhầm mục tiêu; thứ
    phải cấm là câu khẳng định, và câu khẳng định thì nằm ở dòng văn xuôi.
    """
    khung = lay(ma)
    sinh(khung, tmp_path)
    for tep in tmp_path.glob("*.md"):
        trong_chu_thich = False
        for i, dong in enumerate(tep.read_text(encoding="utf-8").splitlines()):
            d = dong.strip()
            if not d:
                continue
            if d.startswith("<!--"):
                trong_chu_thich = True
            if trong_chu_thich:
                if d.endswith("-->"):
                    trong_chu_thich = False
                continue
            hop_le = (
                d.startswith("#")
                or d.startswith(DAU_CHUA_DIEN)
                # Danh sách gạch đầu dòng chỉ có ở `ranh-gioi-phap-ly.md`:
                # TÊN văn bản cần tra và cụm từ gợi ý để người rà. Không
                # dòng nào trong đó là câu khẳng định về cửa hàng.
                or d.startswith("- ")
            )
            assert hop_le, f"{tep.name}:{i + 1}: văn xuôi tự do: {d}"


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_tep_phap_ly_chi_tro_ten_van_ban_khong_tom_tat_luat(ma, tmp_path):
    """
    Máy tóm tắt luật cho doanh nghiệp dựa vào là thứ nguy hiểm nhất nó có
    thể làm ở đây. Tệp này chỉ được liệt kê TÊN văn bản cần tra.
    """
    khung = lay(ma)
    sinh(khung, tmp_path)
    noi_dung = (tmp_path / "ranh-gioi-phap-ly.md").read_text(encoding="utf-8")
    assert "KHÔNG tóm tắt nội dung luật" in noi_dung
    for vb in khung.van_ban_phap_ly:
        assert vb in noi_dung
    # Vẫn phải có chỗ trống bắt người xác nhận đã tra cứu.
    assert not da_dien_du(noi_dung)


# =====================================================================
#  Sinh tệp
# =====================================================================

def test_khong_bao_gio_ghi_de_tep_da_co(tmp_path):
    """Ghi đè tài liệu người ta đã ngồi viết là mất công sức thật."""
    khung = lay("my_pham")
    tep = tmp_path / khung.tai_lieu[0].ten_tep
    tmp_path.mkdir(exist_ok=True)
    tep.write_text("# Nội dung thật do người viết\n\nĐổi trả 7 ngày.\n",
                   encoding="utf-8")

    kq = sinh(khung, tmp_path)

    assert tep in kq.bo_qua
    assert tep not in kq.da_tao
    assert "Đổi trả 7 ngày" in tep.read_text(encoding="utf-8")


def test_chay_lai_lan_hai_khong_tao_them_gi(tmp_path):
    khung = lay("the_thao")
    lan_1 = sinh(khung, tmp_path)
    lan_2 = sinh(khung, tmp_path)
    assert lan_1.da_tao
    assert lan_2.da_tao == []
    assert len(lan_2.bo_qua) == len(lan_1.da_tao)


# =====================================================================
#  CHỐT: khung rỗng không được vào kho
# =====================================================================

def test_thieu_o_dau_bao_dung_cau_hoi():
    text = (
        "# T\n\n"
        f"{DAU_CHUA_DIEN} Đổi trả bao nhiêu ngày?]\n\n"
        "Nội dung người viết.\n\n"
        f"{DAU_CHUA_DIEN} Ai chịu phí ship?]\n"
    )
    thieu = thieu_o_dau(text)
    assert thieu == ["Đổi trả bao nhiêu ngày?", "Ai chịu phí ship?"]


def test_tai_lieu_da_dien_thi_qua_duoc():
    assert da_dien_du("# T\n\nĐổi trả trong 7 ngày kể từ khi nhận hàng.\n")


def test_loc_tep_chan_khung_va_cho_qua_tai_lieu_that(tmp_path):
    that = tmp_path / "that.md"
    that.write_text("# Thật\n\nĐổi trả 7 ngày.\n", encoding="utf-8")
    khung = tmp_path / "khung.md"
    khung.write_text(f"# Khung\n\n{DAU_CHUA_DIEN} Bao nhiêu ngày?]\n",
                     encoding="utf-8")

    nap_duoc, bi_chan = loc_tep_nap_duoc([that, khung])

    assert nap_duoc == [that]
    assert list(bi_chan) == [khung]
    assert bi_chan[khung] == ["Bao nhiêu ngày?"]


@pytest.mark.parametrize("ma", sorted(KHUNG_THEO_MA))
def test_dien_het_thi_qua_duoc_chot(ma, tmp_path):
    """
    CHỐT PHẢI MỞ ĐƯỢC. Đây là test quan trọng nhất của cả module.

    Bản đầu của `sinh.py` viết nguyên văn dấu đánh dấu vào khối hướng dẫn
    đầu tệp, nên `thieu_o_dau` bắt luôn dòng hướng dẫn ấy: người điền hết
    mọi câu hỏi mà tệp VẪN bị từ chối, và thông báo chỉ vào một câu hỏi
    tên là "...".

    Một chốt không bao giờ mở tệ hơn không có chốt: người vận hành sẽ gỡ
    nó đi, và gỡ luôn cả phần bảo vệ thật.
    """
    khung = lay(ma)
    sinh(khung, tmp_path)
    for tep in tmp_path.glob("*.md"):
        goc = tep.read_text(encoding="utf-8")
        # Giả lập người điền: thay mỗi dòng đánh dấu bằng một câu trả lời.
        da_dien = "\n".join(
            "Câu trả lời thật do người của cửa hàng viết."
            if d.strip().startswith(DAU_CHUA_DIEN) else d
            for d in goc.splitlines()
        )
        assert da_dien_du(da_dien), f"{tep.name}: điền hết rồi mà vẫn bị chặn"


def test_ingest_co_goi_chot():
    """
    Chốt phải nằm trên ĐƯỜNG NẠP THẬT, không chỉ tồn tại như một hàm.

    Một chốt không ai gọi là một chốt không tồn tại — và nó còn tệ hơn
    không có, vì người ta tưởng đã được bảo vệ.
    """
    src = (ROOT / "scripts" / "ingest.py").read_text(encoding="utf-8")
    assert "loc_tep_nap_duoc" in src


def test_khong_tai_lieu_that_nao_bi_chan_oan():
    """
    Kho tri thức đang chạy phải qua được chốt.

    Chọn dấu hiệu quá phổ biến (ví dụ "TODO") là sớm muộn có tài liệu thật
    bị chặn oan, rồi người ta tắt chốt đi. Test này canh đúng điều đó, và
    đọc bản `.example` để chạy được trên máy vừa clone.
    """
    for ten in ("knowledge", "knowledge.example"):
        thu_muc = ROOT / "data" / ten
        if not thu_muc.exists():
            continue
        tep = sorted(thu_muc.glob("*.md"))
        if not tep:
            continue
        _, bi_chan = loc_tep_nap_duoc(tep)
        assert bi_chan == {}, [p.name for p in bi_chan]


# =====================================================================
#  Nạp tri thức: gỡ tài liệu không còn tệp
# =====================================================================
#
# `rag.ingest` thay bản cũ theo `source` nhưng KHÔNG BAO GIỜ xoá tài liệu mà
# tệp đã biến mất. Gỡ một tệp khỏi thư mục thì nội dung nó vẫn sống trong
# pgvector, và agent vẫn trích dẫn — kèm tên tài liệu, từ một tệp không còn
# tồn tại.
#
# Đo được thật: chuyển 12 tài liệu Aurora ra thư mục lưu trữ, chạy lại
# `scripts.ingest`, pgvector vẫn giữ đủ 19 tài liệu / 92 đoạn.


def test_ingest_co_go_tai_lieu_mo_coi():
    src = (ROOT / "scripts" / "ingest.py").read_text(encoding="utf-8")
    assert "mo_coi" in src
    assert "DELETE FROM documents WHERE source = ANY" in src


def test_ingest_KHONG_dung_LIKE_tren_duong_dan():
    r"""
    PostgreSQL coi `\` là ký tự THOÁT trong LIKE. Trên Windows `source` là
    `data\knowledge\x.md`, nên mẫu `data\knowledge%` bị đọc thành
    `dataknowledge%` và khớp KHÔNG GÌ CẢ.

    Bản đầu của chính bản vá này dính đúng lỗi đó: lệnh chạy, in "Xong",
    không gỡ tài liệu nào — và không có gì báo là nó vừa không làm việc
    mình nói.

    ĐỌC BẰNG AST: chú thích trong `ingest.py` có nhắc `source LIKE` để giải
    thích lỗi cũ. So chuỗi thì bắt nhầm chính lời giải thích — lần thứ ba
    dính bẫy này trong cùng một dự án.
    """
    import ast

    cay = ast.parse((ROOT / "scripts" / "ingest.py").read_text(encoding="utf-8"))
    chuoi = [
        n.value for n in ast.walk(cay)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    pham = [s for s in chuoi if "source LIKE" in s]
    assert not pham, f"còn dùng LIKE trên đường dẫn: {pham}"


def test_gitignore_chan_thu_muc_luu_tru_nhung_giu_ban_example():
    """
    Thư mục lưu trữ là bản sao của kho tri thức — cùng nội dung, cùng lý do
    không lên repo. Nhưng `knowledge.example` thì PHẢI lên: CI có job chạy
    trên bản clone sạch và cần nó để agent có tài liệu mà trả lời.
    """
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/knowledge.*/" in ignore
    assert "!data/knowledge.example/" in ignore


# =====================================================================
#  Nạp tài liệu qua dashboard: mỗi tài liệu một `source` riêng
# =====================================================================

def test_moi_tai_lieu_dashboard_co_source_rieng():
    """
    rag.ingest xoá bản cũ THEO source trước khi ghi — đúng, vì nạp lại
    cùng một tệp không được tạo bản thứ hai.

    Nhưng bản trước truyền cứng `"dashboard"` cho MỌI tài liệu, nên quy tắc
    ấy thành: nạp tài liệu thứ hai XOÁ MẤT tài liệu thứ nhất. Nhân viên dán
    năm chính sách vào ô "Nạp tài liệu", bấm năm lần, kho còn đúng một cái.

    Không lỗi, không nhật ký. Chỉ là agent trả lời "chưa có thông tin" cho
    bốn chính sách mà người ta tin là đã nạp. Đo được bằng hai lời gọi liên
    tiếp.

    ĐỌC BẰNG AST: chú thích trong `routes.py` có nhắc chuỗi dashboard để
    giải thích lỗi cũ.
    """
    import ast

    src = (ROOT / "agent" / "api" / "routes.py").read_text(encoding="utf-8")
    cay = ast.parse(src)
    ham = next(
        n for n in ast.walk(cay)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "add_document"
    )
    goi = [
        n for n in ast.walk(ham)
        if isinstance(n, ast.Call) and ast.unparse(n.func) == "rag.ingest"
    ]
    assert goi, "add_document không còn gọi rag.ingest"
    nguon = ast.unparse(goi[0].args[1])
    assert nguon != '"dashboard"' and nguon != "'dashboard'", (
        "mọi tài liệu dùng chung một source — tài liệu sau xoá tài liệu trước"
    )
    assert "title" in nguon, f"source phải phân biệt theo tiêu đề, đang là {nguon}"
