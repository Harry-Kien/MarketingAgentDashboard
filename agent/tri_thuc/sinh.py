"""
Sinh khung tài liệu cho một ngành hàng.

MÁY SINH CÂU HỎI, NGƯỜI VIẾT CÂU TRẢ LỜI
----------------------------------------
Mỗi mục trong tệp sinh ra là một hoặc vài dòng `[CẦN NGƯỜI ĐIỀN: ...]`.
Không dòng nào chứa số liệu, mốc thời gian, tên sản phẩm hay câu trích
luật — vì máy không biết những thứ đó, và đoán thì thành lời hứa giả mà
cửa hàng phải chịu trách nhiệm.

Giá trị máy đóng góp nằm ở chỗ khác, và nó thật: biết cửa hàng ngành này
CẦN trả lời được những câu nào, và giải thích vì sao từng tài liệu đáng
viết. Chủ cửa hàng biết chính sách của mình; thứ họ hay thiếu là danh sách
đầy đủ những câu khách sẽ hỏi.

KHÔNG BAO GIỜ GHI ĐÈ
--------------------
Tệp đã tồn tại thì bỏ qua, không hỏi, không sửa. Ghi đè một tài liệu người
ta đã ngồi viết là mất công sức thật, và một lệnh sinh khung không được
phép có hậu quả đó — kể cả khi người dùng gõ nhầm lần thứ hai.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent.tri_thuc.hop_dong import DAU_CHUA_DIEN, KhungNganh, TaiLieu


@dataclass(frozen=True)
class KetQuaSinh:
    da_tao: list[Path]
    bo_qua: list[Path]     # đã tồn tại — không đụng tới
    tong_cau_hoi: int


def _than_tai_lieu(khung: KhungNganh, tl: TaiLieu) -> str:
    dong: list[str] = [f"# {tl.tieu_de}", ""]

    # Khối ghi chú dùng cú pháp comment của Markdown: người đọc tệp thấy
    # nó, còn bản render thì không. Người điền cần lời dặn này trước mắt.
    dong += [
        "<!--",
        f"KHUNG DO HỆ THỐNG SINH — NGÀNH: {khung.ten}",
        "",
        "Máy sinh CÂU HỎI. Câu trả lời phải do người của cửa hàng viết, vì",
        "kho tri thức này là CĂN CỨ để agent trả lời khách — không phải bản",
        "nháp. Mỗi con số ở đây là một cam kết với khách.",
        "",
        # KHÔNG viết nguyên văn dấu đánh dấu ở đây.
        #
        # Bản đầu viết đủ cả ngoặc và dấu hai chấm, nên `chot.thieu_o_dau`
        # bắt luôn chính dòng hướng dẫn này. Hậu quả: người điền hết mọi
        # câu hỏi mà tệp VẪN bị từ chối, và thông báo chỉ vào một câu hỏi
        # tên là "..." — không nói được gì cho ai.
        #
        # Tức là chốt không bao giờ mở. Bắt được lúc chạy thử đầu tiên;
        # `test_dien_het_thi_qua_duoc_chot` canh để không tái diễn.
        "Còn dòng đánh dấu CẦN NGƯỜI ĐIỀN nào chưa xoá thì",
        "`python -m scripts.ingest` TỪ CHỐI nạp tệp này. Cố ý như vậy.",
        "",
        f"VÌ SAO TÀI LIỆU NÀY ĐÁNG VIẾT: {tl.vi_sao}",
        "-->",
        "",
    ]

    for muc in tl.muc:
        dong += [f"## {muc.tieu_de}", ""]
        for ch in muc.cau_hoi:
            dong += [f"{DAU_CHUA_DIEN} {ch}]", ""]

    return "\n".join(dong).rstrip() + "\n"


def _tep_phap_ly(khung: KhungNganh) -> str:
    """
    Tệp con trỏ pháp lý — CỐ Ý không tóm tắt nội dung luật.

    Máy tóm tắt luật cho doanh nghiệp dựa vào là đúng thứ nguy hiểm nhất
    nó có thể làm ở đây: tóm sai một câu thì cửa hàng quảng cáo sai, và
    theo NĐ 181/2013 thì doanh nghiệp chịu trách nhiệm, không phải công cụ.

    Nên tệp này chỉ liệt kê TÊN văn bản cần tra, và bắt người xác nhận đã
    tra. Danh sách cụm cấm cũng vậy: điểm khởi đầu để rà, không phải kết
    luận đã thẩm định.
    """
    dong = [
        "# Ranh giới pháp lý cần tự tra cứu",
        "",
        "<!--",
        "TỆP NÀY CHỈ LÀ CON TRỎ. Hệ thống KHÔNG tóm tắt nội dung luật —",
        "tóm sai một câu là cửa hàng quảng cáo sai, và trách nhiệm thuộc về",
        "doanh nghiệp chứ không thuộc về công cụ.",
        "-->",
        "",
        "## Văn bản cần tra cứu",
        "",
    ]
    for vb in khung.van_ban_phap_ly:
        dong += [f"- {vb}"]
    dong += [
        "",
        f"{DAU_CHUA_DIEN} Đã tra cứu những văn bản trên chưa, và điều nào áp "
        "vào cửa hàng mình? Ghi lại kết luận ở đây.]",
        "",
        "## Cụm từ không được dùng khi quảng cáo",
        "",
        "<!--",
        "Danh sách dưới đây là ĐIỂM KHỞI ĐẦU do hệ thống gợi ý cho ngành này,",
        "chưa qua thẩm định pháp lý. Rà lại, bỏ cụm không đúng với mặt hàng",
        "của bạn, và thêm cụm mà ngành bạn còn bị siết.",
        "-->",
        "",
    ]
    for cum in khung.cum_cam_goi_y:
        dong += [f"- {cum}"]
    dong += [
        "",
        f"{DAU_CHUA_DIEN} Đã rà danh sách trên chưa? Ghi những cụm đã thêm "
        "hoặc đã bỏ, kèm lý do.]",
        "",
    ]
    return "\n".join(dong).rstrip() + "\n"


def sinh(khung: KhungNganh, thu_muc: Path) -> KetQuaSinh:
    """Ghi khung ra thư mục. Tệp đã có thì BỎ QUA, không ghi đè."""
    thu_muc.mkdir(parents=True, exist_ok=True)
    da_tao: list[Path] = []
    bo_qua: list[Path] = []

    for tl in khung.tai_lieu:
        dich = thu_muc / tl.ten_tep
        if dich.exists():
            bo_qua.append(dich)
            continue
        dich.write_text(_than_tai_lieu(khung, tl), encoding="utf-8")
        da_tao.append(dich)

    phap_ly = thu_muc / "ranh-gioi-phap-ly.md"
    if phap_ly.exists():
        bo_qua.append(phap_ly)
    else:
        phap_ly.write_text(_tep_phap_ly(khung), encoding="utf-8")
        da_tao.append(phap_ly)

    return KetQuaSinh(da_tao=da_tao, bo_qua=bo_qua,
                      tong_cau_hoi=khung.tong_cau_hoi())
