"""
Công cụ nghiệp vụ mà agent được phép gọi.

NGUYÊN TẮC BẤT DI BẤT DỊCH: giá, tồn kho, thành phần, tình trạng đơn CHỈ
đến từ đây. Model không bao giờ được nói những con số đó từ trí nhớ.

MVP đọc từ data/catalog.json. Khi lên production, thay phần thân hàm bằng
lời gọi ERP/KiotViet/Haravan — chữ ký và schema giữ nguyên, agent không đổi.
"""
from __future__ import annotations

import json
import pathlib
import unicodedata

from agent import db
from agent.config import ROOT, settings
from agent.core import kho

CATALOG_PATH = ROOT / "data" / "catalog.json"

# Số đoạn và độ dài mỗi đoạn khi agent TỰ đi tra. Nhỏ hơn lượt tra sẵn đầu
# lượt (k=5, nguyên văn) vì đây là lần tra THÊM: nó cộng vào ngữ cảnh đã có
# chứ không thay thế, và mỗi vòng lặp thêm đều tính tiền.
TIM_K = 4
TIM_DAI_TOI_DA = 700

TOOLS: list[dict] = [
    {
        "name": "tim_kien_thuc",
        "description": (
            "Tìm trong kho tài liệu công ty: chính sách đổi trả, bảo hành, vận "
            "chuyển, chống chỉ định, cách phối hoạt chất, hướng dẫn dùng, quy "
            "trình chăm sóc da. "
            "DÙNG KHI ngữ cảnh có sẵn đầu lượt KHÔNG đủ để trả lời — ví dụ "
            "khách hỏi sang một chuyện khác giữa chừng, hoặc câu hỏi cần một "
            "khía cạnh mà đoạn tài liệu đang có chưa nói tới. "
            "Đặt câu hỏi tra cứu NGẮN và CỤ THỂ, không chép nguyên lời khách: "
            "khách hỏi 'em mở nắp rồi thấy không hợp thì trả lại được không "
            "ạ' thì tra 'đổi trả hàng đã mở nắp'. "
            "Không tìm thấy thì NÓI KHÔNG BIẾT hoặc chuyển nhân viên — tuyệt "
            "đối không đoán. Đây KHÔNG phải nơi tra giá, tồn kho hay đơn hàng."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cau_hoi": {
                    "type": "string",
                    "description": "Câu hỏi tra cứu ngắn gọn, đã được diễn đạt lại",
                }
            },
            "required": ["cau_hoi"],
        },
    },
    {
        "name": "tra_cuu_san_pham",
        "description": (
            "Tra giá, dung tích, tồn kho, thành phần và cách dùng của một sản "
            "phẩm cụ thể. BẮT BUỘC gọi trước khi nói bất kỳ con số nào về giá, "
            "dung tích, tồn kho hoặc nồng độ hoạt chất."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ten_san_pham": {
                    "type": "string",
                    "description": "Tên hoặc mã sản phẩm khách nhắc tới",
                }
            },
            "required": ["ten_san_pham"],
        },
    },
    {
        "name": "goi_y_san_pham",
        "description": (
            "Lọc danh mục theo loại da, nhu cầu chăm sóc, nhóm sản phẩm hoặc "
            "khoảng giá. Dùng khi khách chưa biết mua gì, ví dụ 'da dầu nên "
            "dùng gì', 'có gì cho da nhạy cảm', 'kem chống nắng loại nào'. "
            "Chỉ trả về sản phẩm có thật trong danh mục."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "loai_da": {
                    "type": "string",
                    "description": "da dầu, da khô, da hỗn hợp, da nhạy cảm, da thường",
                },
                "nhu_cau": {
                    "type": "string",
                    "description": "Nhu cầu chăm sóc khách nêu, ví dụ cấp ẩm, kiềm dầu, đều màu da",
                },
                "nhom": {
                    "type": "string",
                    "description": "Làm sạch, Cân bằng, Tinh chất chuyên sâu, Dưỡng ẩm, Chống nắng, Mặt nạ, Combo",
                },
                "gia_toi_da": {
                    "type": "integer",
                    "description": "Ngân sách tối đa cho một sản phẩm, đơn vị VND",
                },
            },
        },
    },
    {
        "name": "gui_anh_san_pham",
        "description": (
            "Gửi ảnh sản phẩm cho khách. Dùng khi khách hỏi 'cho xem ảnh', "
            "'sản phẩm trông thế nào', hoặc khi đang tư vấn một sản phẩm cụ "
            "thể mà ảnh giúp khách quyết định nhanh hơn. Gọi CÙNG LÚC với "
            "câu trả lời chứ không thay cho nó — khách cần cả ảnh lẫn lời."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ten_san_pham": {
                    "type": "string",
                    "description": "Tên hoặc mã sản phẩm cần gửi ảnh",
                }
            },
            "required": ["ten_san_pham"],
        },
    },
    {
        "name": "tra_cuu_don_hang",
        "description": (
            "Tra tình trạng đơn hàng theo mã đơn. Gọi khi khách hỏi đơn của họ "
            "tới đâu rồi, bao giờ nhận được."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {"type": "string", "description": "Mã đơn hàng"}
            },
            "required": ["ma_don"],
        },
    },
    {
        "name": "tra_cuu_van_chuyen",
        "description": (
            "Tra tình trạng GIAO HÀNG của một đơn: đã bàn giao vận chuyển "
            "chưa, mã vận đơn là gì, hãng nào. Dùng khi khách hỏi 'đơn tới "
            "đâu rồi', 'bao giờ nhận được', 'sao lâu thế'.\n\n"
            "GIỚI HẠN PHẢI NHỚ: công cụ này đọc SỔ CỦA CỬA HÀNG, KHÔNG đọc "
            "vị trí kiện hàng theo thời gian thực từ hãng vận chuyển. Tuyệt "
            "đối KHÔNG đoán ngày giao, KHÔNG hứa 'mai hàng tới'. Có mã vận "
            "đơn thì đưa mã cho khách tự tra trên ứng dụng của hãng — đó là "
            "thông tin chính xác hơn bất cứ điều gì suy ra từ đây."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {
                    "type": "string",
                    "description": "Mã đơn hàng khách cung cấp",
                }
            },
            "required": ["ma_don"],
        },
    },
    {
        "name": "xin_huy_don",
        "description": (
            "Khách muốn HUỶ một đơn đã đặt. Ghi nhận yêu cầu lên đơn rồi "
            "chuyển cho nhân viên xử lý.\n\n"
            "CÔNG CỤ NÀY KHÔNG HUỶ ĐƠN. Nó chỉ đánh dấu để người đóng gói "
            "biết mà dừng tay, và để nhân viên gọi lại cho khách. Người mới "
            "là bên quyết định huỷ — vì xin huỷ thường là lúc khách đang "
            "không hài lòng, và đó là lúc còn cứu được đơn.\n\n"
            "TUYỆT ĐỐI KHÔNG nói với khách là 'đã huỷ' hay 'đơn đã được huỷ'. "
            "Đơn CHƯA huỷ. Nói đúng sự thật: đã ghi nhận, đã chuyển bộ phận "
            "xử lý, và nhân viên sẽ liên hệ lại."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {
                    "type": "string",
                    "description": "Mã đơn khách muốn huỷ",
                },
                "ly_do": {
                    "type": "string",
                    "description": (
                        "Lý do khách nêu, ghi nguyên văn ý khách. Nhân viên "
                        "gọi lại cần biết vì sao mới cứu được đơn."
                    ),
                },
            },
            "required": ["ma_don"],
        },
    },
    {
        "name": "tao_video",
        "description": (
            "Đặt hàng sản xuất một video marketing. Gọi khi khách hoặc nhân "
            "viên yêu cầu làm video giới thiệu sản phẩm."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tieu_de": {"type": "string", "description": "Tiêu đề ngắn"},
                "yeu_cau": {
                    "type": "string",
                    "description": "Mô tả đầy đủ nội dung video cần làm",
                },
                "loai": {
                    "type": "string",
                    "enum": ["explainer", "product"],
                },
                "thoi_luong_giay": {"type": "integer"},
                "ma_san_pham": {
                    "type": "string",
                    "description": (
                        "Mã sản phẩm (ví dụ AS-SR01) nếu video nói về một sản "
                        "phẩm cụ thể. Có mã thì hệ thống tự lấy ảnh sản phẩm "
                        "trong kho để dựng hình."
                    ),
                },
            },
            "required": ["tieu_de", "yeu_cau"],
        },
    },
    {
        "name": "tao_don_hang",
        "description": (
            "Lên đơn hàng cho khách. CHỈ gọi sau khi đã (1) tóm tắt đầy đủ đơn "
            "gồm tên sản phẩm, số lượng, tổng tiền, họ tên, số điện thoại, địa "
            "chỉ và (2) khách đã trả lời xác nhận rõ ràng bằng lời của họ. "
            "Nếu thiếu bất kỳ thông tin nào thì HỎI TIẾP, tuyệt đối không tự "
            "điền và không đoán. Nếu khách chưa xác nhận thì chưa được gọi."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Danh sách sản phẩm khách chốt mua",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ten_san_pham": {"type": "string"},
                            "so_luong": {"type": "integer"},
                        },
                        "required": ["ten_san_pham", "so_luong"],
                    },
                },
                "khach_ten": {"type": "string", "description": "Họ tên người nhận"},
                "khach_sdt": {"type": "string", "description": "Số điện thoại người nhận"},
                "khach_dia_chi": {
                    "type": "string",
                    "description": "Địa chỉ nhận hàng đầy đủ gồm số nhà, đường, phường, quận, tỉnh",
                },
                "khach_da_xac_nhan": {
                    "type": "boolean",
                    "description": "Đặt true CHỈ KHI khách đã nói rõ là xác nhận đặt đơn",
                },
                "ghi_chu": {"type": "string"},
            },
            "required": [
                "items", "khach_ten", "khach_sdt", "khach_dia_chi", "khach_da_xac_nhan",
            ],
        },
    },
    {
        "name": "chuyen_nhan_vien",
        "description": (
            "Chuyển hội thoại cho nhân viên thật. BẮT BUỘC gọi khi: khách hỏi "
            "về tình trạng da cần chẩn đoán (mụn viêm, nám, viêm da, dị ứng), "
            "khách đang mang thai hoặc cho con bú, khách đang điều trị da theo "
            "toa bác sĩ, da khách đang phản ứng sau khi dùng sản phẩm, khách "
            "khiếu nại, hoặc yêu cầu vượt thẩm quyền như giảm giá và hoàn tiền. "
            "Thà chuyển sớm còn hơn trả lời sai."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ly_do": {"type": "string", "description": "Vì sao cần người"},
                "muc_do": {"type": "string", "enum": ["thuong", "gap"]},
            },
            "required": ["ly_do"],
        },
    },
]


CATALOG_MAU = ROOT / "data" / "catalog.example.json"


def _catalog() -> dict:
    """
    Danh mục sản phẩm. Ưu tiên dữ liệu thật, không có thì dùng bản mẫu.

    Bản mẫu đi kèm repo để máy vừa clone về chạy được ngay: thiếu danh mục
    thì mọi tool tra cứu trả rỗng, agent không nói được giá nào và chuyển hết
    cho người — đúng thiết kế nhưng vô dụng, mà người mới cài thì tưởng hệ
    thống hỏng. Dữ liệu thật đặt ở `catalog.json`, file đó không lên repo.
    """
    duong_dan = CATALOG_PATH if CATALOG_PATH.exists() else CATALOG_MAU
    if not duong_dan.exists():
        return {"san_pham": [], "don_hang": []}
    return json.loads(duong_dan.read_text(encoding="utf-8"))


async def _catalog_song() -> dict:
    """
    Danh mục kèm TỒN KHO SỐNG từ bảng `ton_kho`.

    File JSON giữ dữ liệu tham chiếu (tên, giá, thành phần) vốn ít đổi.
    Số tồn thì đổi mỗi lần bán, nên nó nằm trong CSDL và được chồng lên ở
    đây. Không chồng thì agent đọc con số của ngày file được viết ra và
    xác nhận đơn cho món đã hết từ lâu.

    Hỏng đường CSDL thì rơi về số trong file — thà cũ còn hơn không có gì,
    và chốt tồn kho lúc chốt đơn vẫn chặn được bán quá.
    """
    from agent.erp import nha_may
    from agent.erp.hop_dong import LoiERP

    try:
        data = await nha_may.cong().danh_muc()
    except LoiERP:
        # Cổng hỏng hoàn toàn thì rơi về file. Ở ĐÂY thì được, vì đây là nửa
        # tham chiếu (tên, thành phần) — giá và tồn đã bị cổng chặn ở tầng
        # dưới nếu quá hạn mà gọi không được, nên không có số cũ nào lọt lên.
        data = _catalog()
    # CHỈ chồng tồn kho nội bộ khi nguồn là TỆP.
    #
    # Với nguồn `tep`, bảng `ton_kho` chính là số sống — file JSON chỉ giữ
    # con số của ngày ai đó sửa nó.
    #
    # Với ERP thật thì ngược hẳn: ERP là SỔ CÁI, và bảng nội bộ chỉ còn vai
    # giữ chỗ tạm (thiết kế mục 7.2). Chồng nó lên là xoá mất số vừa lấy về
    # từ ERP — và lỗi đó không nổ, nó LỆCH: agent tư vấn bằng số nội bộ rồi
    # chốt đơn bằng số ERP, nên khách xác nhận xong mới bị báo hết hàng.
    if (settings.erp_loai or "tep").strip().lower() != "tep":
        return data

    try:
        from agent.core import kho
        song = await kho.lay_tat_ca()
    except Exception:  # noqa: BLE001
        return data
    if song:
        for sp in data.get("san_pham", []):
            if sp.get("ma") in song:
                sp["ton_kho"] = song[sp["ma"]]
    return data


ANH_DIR = ROOT / "data" / "products"


def _anh_san_pham(ma: str) -> pathlib.Path | None:
    """
    Ảnh đầu tiên của một mã sản phẩm, hoặc None.

    Ảnh nằm ở `data/products/<mã>/img_00.jpg`, kèm `manifest.json` ghi rõ
    ảnh do model sinh hay chụp thật. Ở đây chỉ cần đường dẫn — phần cảnh
    báo "ảnh sinh, chưa phải ảnh chụp thật" là việc của người vận hành
    trước khi bán hàng, không phải việc agent nhắc khách mỗi lần gửi.
    """
    thu_muc = ANH_DIR / ma
    if not thu_muc.is_dir():
        return None
    for ten in sorted(thu_muc.glob("img_*.jpg")):
        if ten.is_file() and ten.stat().st_size > 0:
            return ten
    return None


def _norm(s: str) -> str:
    """
    Chuẩn hoá để so khớp: bỏ dấu tiếng Việt.

    Khách Việt rất hay gõ không dấu ("combo phuc hoi da yeu"). Nếu so khớp
    có phân biệt dấu thì agent sẽ báo "không tìm thấy" cho sản phẩm có thật
    — mất đơn vì lý do hoàn toàn kỹ thuật.
    """
    text = unicodedata.normalize("NFD", str(s).lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.replace("đ", "d").split())


# Từ có ở mọi sản phẩm nên không giúp phân biệt.
_STOPWORDS = {"aurora", "skin", "cua", "của", "cai", "cái", "loai", "loại", "san", "sản", "pham", "phẩm"}


def _score(query: str, product: dict) -> float:
    """
    Chấm độ khớp bằng tỉ lệ từ trùng, rồi chọn CAO NHẤT.

    Không được lấy cái đầu tiên khớp một phần: mọi sản phẩm đều chứa
    'Aurora' nên khớp lỏng sẽ trả nhầm sản phẩm — tức agent báo giá món
    khác. Đó là lỗi tệ hơn nhiều so với trả lời không tìm thấy.
    """
    # Tự chuẩn hoá thay vì tin người gọi đã làm. Trước đây hàm ngầm đòi
    # tham số đã qua _norm; gọi bằng chuỗi thô thì nó IM LẶNG trả điểm sai
    # chứ không báo lỗi — loại phụ thuộc ẩn dễ gây trả nhầm sản phẩm nhất.
    # _norm là luỹ đẳng nên gọi hai lần vô hại.
    query = _norm(query)
    hay = _norm(product.get("ten", "")) + " " + _norm(product.get("ma", ""))
    hay_words = set(hay.split())
    q_words = [w for w in query.split() if len(w) > 1 and w not in _STOPWORDS]
    if not q_words:
        return 0.0
    if query and query in hay:
        return 1.0
    return sum(1 for w in q_words if w in hay_words) / len(q_words)


def _tom_tat(sp: dict) -> dict:
    """Bản rút gọn để liệt kê — tránh nhồi cả danh mục vào ngữ cảnh."""
    return {
        "ma": sp.get("ma"),
        "ten": sp.get("ten"),
        "loai": sp.get("loai"),
        "gia": sp.get("gia"),
        "dung_tich": sp.get("dung_tich"),
        "con_hang": (sp.get("ton_kho") or 0) > 0,
        "da_phu_hop": sp.get("da_phu_hop"),
        "van_de_ho_tro": sp.get("van_de_ho_tro"),
    }


async def run_tool(name: str, args: dict, conversation_id=None) -> dict:
    # ---------- tra kho tri thức ----------
    # Đặt TRƯỚC lời gọi danh mục: câu hỏi chính sách không cần đọc catalog,
    # và nạp catalog cho một câu hỏi về đổi trả là công vô ích mỗi lượt.
    if name == "tim_kien_thuc":
        from agent.core import rag

        cau_hoi = (args.get("cau_hoi") or "").strip()
        if not cau_hoi:
            return {"tim_thay": False, "ghi_chu": "Thiếu câu hỏi tra cứu."}

        passages = await rag.retrieve(cau_hoi, k=TIM_K)
        if not passages:
            # Nói rõ phải làm gì tiếp. Trả về một dict rỗng thì model tự bịa
            # ra đường đi, và đường nó hay chọn là đoán bừa.
            return {
                "tim_thay": False,
                "ghi_chu": (
                    "Kho tài liệu không có căn cứ cho câu này. KHÔNG được đoán. "
                    "Hãy nói thẳng là mình chưa có thông tin, hoặc gọi "
                    "chuyen_nhan_vien nếu khách cần câu trả lời chắc chắn. "
                    "Đừng tra lại cùng một câu hỏi."
                ),
            }
        return {
            "tim_thay": True,
            "doan": [
                {
                    "tai_lieu": p.doc_title,
                    "noi_dung": p.content.strip()[:TIM_DAI_TOI_DA],
                    "diem": round(p.score, 3),
                }
                for p in passages
            ],
            "ghi_chu": "Chỉ trả lời dựa trên các đoạn trên. Nêu tên tài liệu khi trích.",
        }

    catalog = await _catalog_song()
    products = catalog.get("san_pham", [])

    # ---------- tra cứu một sản phẩm ----------
    if name == "tra_cuu_san_pham":
        q = _norm(args.get("ten_san_pham", ""))
        ranked = sorted(
            ((_score(q, sp), sp) for sp in products), key=lambda x: x[0], reverse=True
        )
        if ranked and ranked[0][0] >= 0.5:
            best_score, best = ranked[0]
            if len(ranked) > 1 and ranked[1][0] == best_score < 1.0:
                return {
                    "tim_thay": False,
                    "ghi_chu": "Tên mơ hồ, khớp nhiều sản phẩm. Hỏi lại khách "
                               "tên đầy đủ, tuyệt đối không đoán.",
                    "ung_vien": [p.get("ten") for s, p in ranked if s == best_score],
                }
            out = {"tim_thay": True, **best}
            out["con_hang"] = (best.get("ton_kho") or 0) > 0
            return out
        return {
            "tim_thay": False,
            "ghi_chu": "Không có sản phẩm này trong danh mục. Đừng đoán — "
                       "hãy nói không tìm thấy và hỏi lại tên chính xác.",
            "goi_y_dung_ten": [p.get("ten") for p in products[:6]],
        }

    # ---------- gợi ý theo nhu cầu ----------
    if name == "goi_y_san_pham":
        loai_da = _norm(args.get("loai_da", ""))
        nhu_cau = _norm(args.get("nhu_cau", ""))
        nhom = _norm(args.get("nhom", ""))
        gia_max = args.get("gia_toi_da")

        hits = []
        for sp in products:
            if nhom and nhom not in _norm(sp.get("loai", "")):
                continue
            if gia_max and (sp.get("gia") or 0) > int(gia_max):
                continue
            # Mọi vế so sánh PHẢI đi qua _norm — nó bỏ dấu tiếng Việt. Trộn
            # chuỗi đã bỏ dấu với chuỗi còn dấu là không bao giờ khớp.
            if loai_da:
                pool = _norm(" ".join(sp.get("da_phu_hop") or []))
                if _norm("mọi loại da") not in pool and not any(
                    w in pool for w in loai_da.split() if len(w) > 2
                ):
                    continue
            if nhu_cau:
                pool = _norm(
                    " ".join(sp.get("van_de_ho_tro") or [])
                    + " " + " ".join(sp.get("thanh_phan_chinh") or [])
                    + " " + str(sp.get("ten", ""))
                )
                if not any(w in pool for w in nhu_cau.split() if len(w) > 2):
                    continue
            hits.append(sp)

        if not hits:
            return {
                "so_luong": 0,
                "ghi_chu": "Không có sản phẩm nào khớp tiêu chí. Hỏi thêm khách "
                           "để thu hẹp, không được bịa sản phẩm.",
            }
        con_hang = [h for h in hits if (h.get("ton_kho") or 0) > 0]
        return {
            "so_luong": len(hits),
            "san_pham": [_tom_tat(h) for h in (con_hang or hits)[:6]],
            "het_hang": [h.get("ten") for h in hits if (h.get("ton_kho") or 0) == 0],
        }

    # ---------- gửi ảnh sản phẩm ----------
    if name == "gui_anh_san_pham":
        q = _norm(args.get("ten_san_pham", ""))
        ranked = sorted(
            ((_score(q, sp), sp) for sp in products), key=lambda x: x[0], reverse=True
        )
        if not ranked or ranked[0][0] < 0.5:
            return {"gui_duoc": False,
                    "ly_do": "Không rõ khách muốn xem ảnh sản phẩm nào. Hỏi lại tên."}
        sp = ranked[0][1]
        anh = _anh_san_pham(sp["ma"])
        if not anh:
            return {"gui_duoc": False,
                    "ly_do": f"Chưa có ảnh cho {sp['ten']}. Mô tả bằng lời thay vì hứa gửi ảnh."}
        # Tool KHÔNG tự gửi. Nó báo "gửi được" kèm đường dẫn; việc gửi do
        # lớp kênh làm trong main.py — cùng cách `tao_video` báo `da_nhan`.
        # Tool không biết mình đang chạy trên Zalo hay Chatwoot, và không
        # nên biết.
        return {
            "gui_duoc": True,
            "ma": sp["ma"],
            "ten": sp["ten"],
            "duong_dan": str(anh),
            "ghi_chu_cho_agent": (
                "Ảnh đang được gửi. Vẫn phải trả lời bằng lời như bình thường, "
                "đừng chỉ nói 'em gửi ảnh nhé' rồi dừng."
            ),
        }

    # ---------- đơn hàng ----------
    if name == "tra_cuu_don_hang":
        return await _tra_cuu_don_hang(args, conversation_id)

    if name == "tra_cuu_van_chuyen":
        return await _tra_cuu_van_chuyen(args)

    if name == "xin_huy_don":
        return await _xin_huy_don(args, conversation_id)

    # ---------- lên đơn: tool DUY NHẤT có hậu quả không đảo ngược ----------
    if name == "tao_don_hang":
        return await _tao_don_hang(args, products, conversation_id)

    if name == "chuyen_nhan_vien":
        return {
            "da_chuyen": True,
            "ly_do": args.get("ly_do", ""),
            "muc_do": args.get("muc_do", "thuong"),
        }

    if name == "tao_video":
        return await _tao_video(args, products, conversation_id)

    return {"loi": f"Không có công cụ tên {name}"}


# ===============================================================
#  Lên đơn hàng — sáu chốt chặn
# ===============================================================

async def _tao_video(args: dict, products: list[dict], conversation_id) -> dict:
    """
    Đặt video THẬT vào hàng đợi.

    Trước đây hàm này chỉ trả `{"da_nhan": True}` — agent nói với khách là đã
    đặt video xong, nhưng không có video nào được tạo. Đó là kiểu hỏng tệ
    nhất: hệ thống im lặng nói dối thay mặt doanh nghiệp.

    Video luôn dừng ở trạng thái CHỜ DUYỆT, không bao giờ tự gửi cho khách.
    """
    from agent.video import catalog_images, pipeline

    tieu_de = str(args.get("tieu_de", "")).strip()
    yeu_cau = str(args.get("yeu_cau", "")).strip()
    if not tieu_de or len(yeu_cau) < 10:
        return {"dat_duoc": False, "ly_do": "Thiếu tiêu đề hoặc mô tả quá ngắn."}

    # Mã sản phẩm phải có thật trong catalog. Model bịa mã thì dựng ra video
    # không có ảnh, im lặng — thà báo lại để nó tra cứu trước.
    ma = str(args.get("ma_san_pham", "")).strip().upper()
    if ma:
        biet = {str(p.get("ma", "")).upper() for p in products}
        if ma not in biet:
            return {
                "dat_duoc": False,
                "ly_do": f"Không có sản phẩm mã {ma}. Tra cứu sản phẩm trước.",
            }

    so_anh = len(catalog_images.anh_cua(ma)) if ma else 0

    video_id = await pipeline.request_video(
        title=tieu_de[:200],
        brief=yeu_cau[:4000],
        kind=str(args.get("loai") or ("product" if ma else "explainer")),
        conversation_id=conversation_id,
        ma_san_pham=ma or None,
    )

    return {
        "dat_duoc": True,
        "video_id": video_id,
        "so_anh_san_pham": so_anh,
        "trang_thai": "Đã vào hàng đợi sản xuất.",
        "nhac_agent": (
            "Nói với khách là video đang được làm và sẽ có sau vài phút. "
            "KHÔNG hứa thời điểm cụ thể. Video phải qua người duyệt trước "
            "khi gửi đi, nên đừng nói là sẽ gửi ngay."
            + ("" if so_anh else
               " Sản phẩm này chưa có ảnh trong kho nên video sẽ là thẻ chữ.")
        ),
    }


async def _tao_don_hang(args: dict, products: list[dict], conversation_id) -> dict:
    """
    Tool DUY NHẤT có hậu quả không đảo ngược. Mọi chốt chặn nằm ở đây, không
    nằm trong prompt — prompt có thể bị model bỏ qua, mã thì không.
    """
    from agent import db

    # --- Chốt 1: khách phải xác nhận rõ ràng ---
    if not args.get("khach_da_xac_nhan"):
        return {
            "tao_duoc": False,
            "ly_do": "Khách chưa xác nhận. Hãy tóm tắt đơn đầy đủ rồi hỏi "
                     "khách xác nhận trước, chưa được lên đơn.",
        }

    # --- Chốt 2: đủ trường bắt buộc, không tự điền ---
    thieu = [
        nhan for khoa, nhan in (
            ("khach_ten", "họ tên"), ("khach_sdt", "số điện thoại"),
            ("khach_dia_chi", "địa chỉ"),
        ) if not str(args.get(khoa) or "").strip()
    ]
    sdt = "".join(ch for ch in str(args.get("khach_sdt") or "") if ch.isdigit())
    if len(sdt) < 9:
        thieu.append("số điện thoại hợp lệ")
    if len(str(args.get("khach_dia_chi") or "").strip()) < 12:
        thieu.append("địa chỉ đầy đủ")
    if thieu:
        return {
            "tao_duoc": False,
            "thieu_thong_tin": thieu,
            "ly_do": "Thiếu thông tin giao hàng. Hỏi khách cho đủ, không tự điền.",
        }

    items_in = args.get("items") or []
    if not items_in:
        return {"tao_duoc": False, "ly_do": "Chưa có sản phẩm nào trong đơn."}

    # --- Chốt 3: giá và tồn kho lấy từ DANH MỤC, không lấy từ model ---
    lines, tong = [], 0
    for it in items_in:
        q = _norm(it.get("ten_san_pham", ""))
        ranked = sorted(
            ((_score(q, sp), sp) for sp in products), key=lambda x: x[0], reverse=True
        )
        if not ranked or ranked[0][0] < 0.5:
            return {
                "tao_duoc": False,
                "ly_do": f"Không có sản phẩm '{it.get('ten_san_pham')}' trong danh mục.",
            }
        sp = ranked[0][1]
        sl = max(1, int(it.get("so_luong") or 1))

        # --- Chốt 4: tồn kho đọc SỐNG, bỏ qua cache ---
        # Con số trong `products` đến từ danh mục đã cache tối đa ERP_TTL_TON
        # giây. Ở mọi chỗ khác thì đủ tốt; ở đúng khoảnh khắc chốt thì không,
        # vì giữa lúc tư vấn và lúc khách gật, món cuối có thể đã bán mất.
        from agent.erp import nha_may

        ton_song = await nha_may.cong().ton_kho(sp["ma"], bo_qua_cache=True)
        if ton_song is None:
            # Không biết còn bao nhiêu thì KHÔNG chốt. Chốt liều là bán món
            # có thể đã hết, và khách chỉ biết khi không nhận được hàng.
            return {
                "tao_duoc": False,
                "ly_do": f"Chưa tra được tồn kho của {sp['ten']}. "
                         "Hãy báo khách chờ một chút và chuyển cho nhân viên.",
            }
        ton = ton_song.ban_duoc
        if ton <= 0:
            return {
                "tao_duoc": False,
                "ly_do": f"{sp['ten']} đang hết hàng, không lên đơn được.",
            }
        if sl > ton:
            return {
                "tao_duoc": False,
                "ly_do": f"{sp['ten']} chỉ còn {ton} sản phẩm, không đủ {sl}.",
            }

        thanh_tien = int(sp["gia"]) * sl          # giá LUÔN từ danh mục
        tong += thanh_tien
        lines.append({
            "ma": sp["ma"], "ten": sp["ten"],
            "don_gia": int(sp["gia"]), "so_luong": sl, "thanh_tien": thanh_tien,
        })

    # --- Chốt 5: vượt ngưỡng thì KHÔNG tự chốt, đưa vào hàng chờ duyệt ---
    tu_chot = tong < settings.nguong_tu_chot_vnd
    trang_thai = "da_chot" if tu_chot else "cho_duyet"

    ma_don = "AS" + __import__("time").strftime("%y%m%d%H%M%S")

    # --- Chốt 6: chống tạo trùng (unique index trên conversation + items) ---
    try:
        row = await db.fetchrow(
            """
            INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt,
                                khach_dia_chi, items, tong_tien, trang_thai, ghi_chu)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id, ma_don
            """,
            ma_don, conversation_id,
            str(args["khach_ten"]).strip(), sdt,
            str(args["khach_dia_chi"]).strip(),
            lines, tong, trang_thai, args.get("ghi_chu"),
        )
    except Exception as exc:  # noqa: BLE001
        if "idx_order_dedupe" in str(exc) or "duplicate" in str(exc).lower():
            return {
                "tao_duoc": False,
                "trung_don": True,
                "ly_do": "Đơn với đúng các sản phẩm này đã được tạo trước đó. "
                         "Hãy báo khách là đơn đã ghi nhận, đừng tạo thêm.",
            }
        return {"tao_duoc": False, "ly_do": f"Lỗi hệ thống khi lưu đơn: {type(exc).__name__}"}

    # --- Chốt 7: TRỪ KHO thật, nguyên tử, có khoá hàng ---
    # Kiểm tồn ở chốt 4 chỉ là kiểm lúc đọc. Giữa lúc đọc và lúc ghi, một
    # khách khác có thể đã lấy mất món cuối. Chỉ khoá hàng lúc trừ mới
    # chặn được, và nếu không đủ thì phải huỷ luôn đơn vừa tạo — thà không
    # có đơn còn hơn có đơn cho hàng không tồn tại.
    du_hang, ly_do_kho = await kho.giu_hang(lines, row["ma_don"])
    if not du_hang:
        await db.execute("DELETE FROM orders WHERE id = $1", row["id"])
        return {"tao_duoc": False, "ly_do": ly_do_kho}

    await db.log_event(
        "order.created", ref_id=row["id"], ma_don=row["ma_don"],
        tong_tien=tong, trang_thai=trang_thai,
    )

    # --- Chốt 8: đẩy sang ERP (chỉ khi ERP_GHI_DON bật) ---
    # Đặt SAU chốt 7 có chủ ý: hàng phải được giữ trước đã. Đẩy sang ERP
    # rồi mới phát hiện không đủ hàng là tạo một đơn bên ERP phải đi huỷ tay.
    #
    # Chỉ chạy cho đơn đã chốt. Đơn `cho_duyet` chưa phải là đơn — người còn
    # chưa duyệt, đẩy sang ERP là ghi nhận một thứ có thể bị bỏ.
    if trang_thai == "da_chot":
        from agent.erp import day_don as _day_don

        kq_erp = await _day_don.day_don(
            ma_don=row["ma_don"],
            khach_ten=str(args["khach_ten"]).strip(),
            khach_sdt=sdt,
            khach_dia_chi=str(args["khach_dia_chi"]).strip(),
            items=lines,
            ghi_chu=str(args.get("ghi_chu") or ""),
        )
        if kq_erp.ket_cuc == "tu_choi":
            # ERP hiểu và không đồng ý. Trả hàng, huỷ đơn — thà không có đơn
            # còn hơn có đơn mà kho không bao giờ xuất.
            await kho.tra_hang(row["ma_don"], ly_do="erp_tu_choi")
            await db.execute(
                "UPDATE orders SET trang_thai='da_huy', erp_loi=$2 "
                "WHERE id = $1", row["id"], kq_erp.ly_do,
            )
            return {
                "tao_duoc": False,
                "ly_do": f"Kho từ chối đơn: {kq_erp.ly_do}. Báo khách là chưa "
                         "lên đơn được và chuyển cho nhân viên.",
            }
        if kq_erp.ket_cuc == "cho_lai":
            # KHÔNG BIẾT ERP đã ghi hay chưa. Giữ hàng, giữ đơn, đổi trạng
            # thái để vòng nền thử lại — và KHÔNG nói với khách là đã chốt.
            trang_thai = "cho_dong_bo"
            await db.execute(
                "UPDATE orders SET trang_thai='cho_dong_bo', erp_loi=$2, "
                "erp_so_lan_thu = erp_so_lan_thu + 1 WHERE id = $1",
                row["id"], kq_erp.ly_do,
            )
        elif kq_erp.erp_ma_don:
            await db.execute(
                "UPDATE orders SET erp_ma_don=$2, erp_dong_bo_luc=now() "
                "WHERE id = $1", row["id"], kq_erp.erp_ma_don,
            )

    if trang_thai == "cho_dong_bo":
        return {
            "tao_duoc": True,
            "ma_don": row["ma_don"],
            "items": lines,
            "tong_tien": tong,
            "trang_thai": trang_thai,
            "ghi_chu_cho_agent": (
                "Đơn ĐÃ GHI NHẬN nhưng chưa đồng bộ được sang kho. Báo khách "
                "là đã nhận thông tin và sẽ có người gọi xác nhận. TUYỆT ĐỐI "
                "KHÔNG nói là đã chốt xong."
            ),
        }

    return {
        "tao_duoc": True,
        "ma_don": row["ma_don"],
        "items": lines,
        "tong_tien": tong,
        "trang_thai": trang_thai,
        "ghi_chu_cho_agent": (
            "Đơn đã chốt. Báo mã đơn và tổng tiền cho khách."
            if tu_chot else
            "Đơn giá trị lớn nên đang CHỜ NHÂN VIÊN DUYỆT. Báo khách là đã ghi "
            "nhận và sẽ có người gọi xác nhận, KHÔNG nói là đã chốt xong."
        ),
    }


# Lời lẽ cho từng trạng thái giao hàng. Đặt ở đây, MỘT chỗ, để agent không
# tự nghĩ ra cách diễn đạt khác nhau mỗi lượt — và để người vận hành sửa
# được câu chữ mà không phải đụng vào prompt.
# Khoá khớp `models.InternalShippingStatus` — đó là bộ trạng thái nội bộ duy
# nhất. Hai bộ tên cho cùng một thứ là hai nguồn sự thật, và sớm muộn chúng
# lệch nhau.
_LOI_TRANG_THAI_GIAO = {
    "delivering": "Đơn đã bàn giao đơn vị vận chuyển và đang trên đường.",
    "delivered": "Đơn đã giao thành công.",
    "delivery_failed": "Đơn giao không thành công — cần người kiểm tra lại.",
    "returned": "Đơn đang được hoàn về kho.",
    "khong_ro": (
        "Hãng vận chuyển trả về một trạng thái hệ thống chưa nhận ra. "
        "Cần chuyển người kiểm tra, đừng đoán."
    ),
}


async def _doc_don_trong_csdl(ma_don: str, conversation_id) -> dict | None:
    """
    Đọc đơn THẬT từ bảng `orders`, kèm cờ đơn có thuộc hội thoại này không.

    Trả về cả đơn của người khác (không kèm chi tiết cá nhân ở chỗ gọi) là
    CỐ Ý: chỗ gọi cần phân biệt "mã không tồn tại" với "mã của người khác"
    để chọn câu trả lời, nhưng KHÔNG được nói ra sự khác biệt đó với khách.
    """
    row = await db.fetchrow(
        """
        SELECT ma_don, trang_thai, items, tong_tien, ghi_chu, created_at,
               (conversation_id = $2) AS cua_hoi_thoai_nay
        FROM orders WHERE ma_don = $1
        """,
        ma_don, conversation_id,
    )
    return dict(row) if row else None


async def _tra_cuu_don_hang(args: dict, conversation_id) -> dict:
    """
    Tra đơn cho khách đang nhắn — và CHỈ đơn của khách đó.

    VÌ SAO ĐỌC BẢNG `orders` CHỨ KHÔNG ĐỌC `catalog.json`
    -----------------------------------------------------
    `tao_don_hang` ghi vào bảng `orders`. Bản trước của hàm này lại tìm
    trong mảng `don_hang` của `catalog.json` — ba đơn mẫu bịa. Hai đường
    không gặp nhau, nên agent tạo đơn xong, khách hỏi lại năm phút sau thì
    chính agent trả lời "không có mã đơn này trong hệ thống".

    Không có lỗi nào bị ném và không có dòng nhật ký nào.

    VÌ SAO CHẶN THEO HỘI THOẠI
    --------------------------
    Mã đơn ngắn và đoán được. Không chặn thì bất kỳ ai nhắn vào Trang cũng
    đọc được tên, số điện thoại, địa chỉ của khách khác bằng cách đọc mã
    lên. Rò rỉ dữ liệu cá nhân, không phải bất tiện.

    Và khi mã thuộc về người khác thì cũng KHÔNG nói "không tìm thấy": câu
    đó phân biệt mã có thật với mã bịa, tức vẫn là một kênh rò rỉ.
    """
    ma = str(args.get("ma_don", "") or "").strip()
    if not ma:
        return {"tim_thay": False, "ghi_chu": "Khách chưa cho mã đơn."}

    if conversation_id is not None:
        don = await _doc_don_trong_csdl(ma, conversation_id)
        if don is not None:
            if don.get("cua_hoi_thoai_nay"):
                return {"tim_thay": True, **{
                    k: v for k, v in don.items() if k != "cua_hoi_thoai_nay"
                }}
            return {
                "tim_thay": False,
                "can_xac_minh": True,
                "ghi_chu": (
                    "Mã đơn này không thuộc hội thoại đang nói chuyện. TUYỆT "
                    "ĐỐI không đọc thông tin đơn ra. Xin lỗi khách, nói cần "
                    "xác minh và hỏi số điện thoại đã đặt đơn, rồi gọi "
                    "chuyen_nhan_vien để người thật kiểm tra."
                ),
            }

    # Đường lui cho bản demo, TỰ TẮT khi shop thay bằng dữ liệu thật.
    #
    # Để đơn mẫu sống sót sang dữ liệu thật là agent trả lời khách bằng đơn
    # bịa — tệ hơn hẳn việc nói không tìm thấy.
    catalog = _catalog()
    if catalog.get("du_lieu_mau"):
        for dh in catalog.get("don_hang", []):
            if _norm(dh.get("ma", "")) == _norm(ma):
                return {"tim_thay": True, "du_lieu_mau": True, **dh}

    return {
        "tim_thay": False,
        "ghi_chu": (
            "Không tìm thấy đơn trong hội thoại này. Hỏi khách xem có đặt "
            "bằng số điện thoại hoặc kênh khác không, rồi chuyển nhân viên."
        ),
    }


async def _danh_dau_xin_huy(ma_don: str, conversation_id, ly_do: str) -> bool:
    """
    Gắn cờ xin huỷ lên đơn. Trả True nếu có đúng một dòng được sửa.

    KHÔNG đụng tới `trang_thai`: huỷ là việc của người, và trộn hai thứ vào
    một câu SQL là sớm muộn có người sửa nhầm thành huỷ thật.

    Chặn theo `conversation_id` vì mã đơn đoán được — không chặn thì bất kỳ
    ai cũng gắn cờ lên đơn của người lạ, tức phá hoại được từ xa.

    Loại đơn `da_huy` để không dựng lại cờ trên đơn đã đóng.
    """
    row = await db.fetchrow(
        """
        UPDATE orders
           SET yeu_cau_huy_luc   = COALESCE(yeu_cau_huy_luc, now()),
               yeu_cau_huy_ly_do = $3,
               updated_at        = now()
         WHERE ma_don = $1
           AND conversation_id = $2
           AND trang_thai <> 'da_huy'
        RETURNING ma_don
        """,
        ma_don, conversation_id, (ly_do or "")[:500],
    )
    return row is not None


async def _xin_huy_don(args: dict, conversation_id) -> dict:
    """
    Ghi nhận yêu cầu huỷ rồi chuyển người — không bao giờ tự huỷ.

    VÌ SAO GHI LÊN CHÍNH ĐƠN
    ------------------------
    Chuyển hội thoại cho người là chưa đủ. Yêu cầu khi đó chỉ nằm trong đoạn
    chat, còn người đóng gói sáng hôm sau nhìn màn hình Đơn hàng và không
    thấy gì bất thường. Hàng vẫn lên đường, khách từ chối nhận, shop chịu
    phí hoàn COD — và không có lỗi nào bị ném ở đâu cả.

    VẪN CHUYỂN NGƯỜI KỂ CẢ KHI KHÔNG GẮN ĐƯỢC CỜ
    ---------------------------------------------
    Không tìm thấy đơn trong hội thoại này thì khách vẫn đang muốn huỷ một
    cái gì đó. Im lặng bỏ qua là bỏ rơi khách ở đúng lúc họ bực nhất.
    """
    ma = str(args.get("ma_don", "") or "").strip()
    ly_do = str(args.get("ly_do", "") or "").strip()

    da_ghi = False
    if ma and conversation_id is not None:
        da_ghi = await _danh_dau_xin_huy(ma, conversation_id, ly_do)
        if da_ghi:
            await db.log_event(
                "order.xin_huy", actor="agent", ma_don=ma, ly_do=ly_do[:200],
            )

    if da_ghi:
        ghi_chu = (
            "Đã ghi nhận yêu cầu huỷ lên đơn và chuyển nhân viên. "
            "TUYỆT ĐỐI KHÔNG nói với khách là đơn 'đã huỷ' — đơn CHƯA huỷ, "
            "người mới là bên quyết định. Nói đúng: đã ghi nhận, đã chuyển "
            "bộ phận xử lý, nhân viên sẽ liên hệ lại sớm."
        )
    else:
        ghi_chu = (
            "KHÔNG tìm thấy đơn này trong hội thoại. Không nói đơn 'đã huỷ' "
            "và không đọc thông tin đơn nào ra. Xin lỗi khách, hỏi lại mã "
            "đơn hoặc số điện thoại đã đặt, và cho biết nhân viên sẽ kiểm "
            "tra giúp."
        )

    return {
        "da_ghi_nhan": da_ghi,
        "da_huy": False,
        "can_chuyen_nhan_vien": True,
        "ghi_chu": ghi_chu,
    }


async def _tra_cuu_van_chuyen(args: dict) -> dict:
    """
    Tình trạng giao hàng của một đơn, đọc từ SỔ CỦA CỬA HÀNG.

    VÌ SAO KHÔNG GỌI THẲNG API HÃNG Ở ĐÂY
    -------------------------------------
    Lời gọi mạng nằm trong đường trả lời khách là thêm một chỗ để treo: hãng
    chậm 20 giây thì khách chờ 20 giây, và nếu hãng chết thì agent im luôn.
    Webhook của hãng cập nhật `orders.trang_thai_giao_hang`; tool này chỉ đọc.

    Đổi lại, số liệu có thể trễ vài phút — và đó là đánh đổi đúng: trả lời
    chậm vài phút tốt hơn không trả lời.
    """
    ma = str(args.get("ma_don", "")).strip()
    if not ma:
        return {"tim_thay": False, "ghi_chu": "Chưa có mã đơn để tra."}
    try:
        row = await db.fetchrow(
            "SELECT ma_don, trang_thai, trang_thai_giao_hang, ma_van_don, "
            "       don_vi_van_chuyen, ngay_du_kien_giao, "
            "       cap_nhat_van_chuyen_luc "
            "FROM orders WHERE upper(ma_don) = upper($1)",
            ma,
        )
    except Exception:  # noqa: BLE001 — CSDL chết thì agent vẫn phải nói được gì đó
        return {
            "tim_thay": False,
            "ghi_chu": "Chưa tra được lúc này. Cần chuyển người hỗ trợ.",
        }
    if row is None:
        return {
            "tim_thay": False,
            "ghi_chu": f"Không thấy đơn {ma} trong hệ thống.",
        }

    trang_thai_giao = row.get("trang_thai_giao_hang")
    if not trang_thai_giao:
        # Chưa bàn giao vận chuyển. NÓI THẬT điều đó, đừng suy ra ngày giao.
        return {
            "tim_thay": True,
            "ma_don": row["ma_don"],
            "trang_thai_don": row["trang_thai"],
            "da_ban_giao_van_chuyen": False,
            "ghi_chu": (
                "Đơn chưa bàn giao đơn vị vận chuyển. Không được đoán ngày "
                "giao; nếu khách sốt ruột thì chuyển người."
            ),
        }
    return {
        "tim_thay": True,
        "ma_don": row["ma_don"],
        "trang_thai_don": row["trang_thai"],
        "da_ban_giao_van_chuyen": True,
        "trang_thai_giao": trang_thai_giao,
        "ma_van_don": row.get("ma_van_don") or "",
        "hang_van_chuyen": row.get("don_vi_van_chuyen") or "",
        "cap_nhat_luc": (
            row["cap_nhat_van_chuyen_luc"].isoformat()
            if row.get("cap_nhat_van_chuyen_luc") else ""
        ),
        "loi_goi_y": _LOI_TRANG_THAI_GIAO.get(trang_thai_giao, ""),
        "ghi_chu": (
            "Có mã vận đơn thì đưa cho khách tự tra trên ứng dụng của hãng. "
            "KHÔNG đoán ngày giao."
        ),
    }
