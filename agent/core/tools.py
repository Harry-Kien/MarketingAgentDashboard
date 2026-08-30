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
            "Tra cứu tình trạng đơn hàng và lộ trình giao hàng thời gian thực từ hãng "
            "vận chuyển (GHN/GHTK). Nếu khách không nói mã đơn cụ thể mà chỉ hỏi chung chung "
            "('cập nhật đơn cho tôi', 'đơn anh tới đâu rồi', 'kiểm tra đơn hàng'), "
            "hãy để trống ma_don (hoặc không truyền), công cụ sẽ TỰ ĐỘNG tra cứu đơn hàng "
            "gần nhất của khách này trong hệ thống!"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {
                    "type": "string",
                    "description": "Mã đơn hàng hoặc mã vận đơn (tuỳ chọn, để trống nếu khách hỏi chung)",
                }
            },
            "required": [],
        },
    },
    {
        "name": "tao_van_don",
        "description": (
            "Tạo vận đơn giao hàng với hãng vận chuyển (GHN) cho một đơn hàng đã chốt. "
            "Tự động chạy qua 4 chốt kiểm duyệt: đơn hợp lệ, đủ thông tin giao nhận, "
            "đã trừ tồn kho, và chống tạo trùng."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {
                    "type": "string",
                    "description": "Mã đơn hàng nội bộ cần tạo vận đơn",
                }
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
            "Lên đơn hàng cho khách. BẮT BUỘC gọi công cụ này khi khách đồng ý chốt mua "
            "hoặc đã cung cấp thông tin nhận hàng (họ tên, số điện thoại, địa chỉ cụ thể). "
            "Công cụ sẽ lưu đơn vào CSDL, trừ tồn kho và tự động tạo mã vận đơn để gửi cho khách."
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
    data = _catalog()
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

    # ---------- đơn hàng & vận chuyển ----------
    if name == "tra_cuu_don_hang":
        from agent.shipping import tra_cuu_van_don
        ma = str(args.get("ma_tra_cuu") or args.get("ma_don") or args.get("ma_van_don") or "").strip()
        db_order = None
        if ma:
            db_order = await db.fetchrow(
                "SELECT * FROM orders WHERE ma_don = $1 OR ma_van_don = $1", ma
            )
        else:
            # Tự động tìm đơn hàng gần nhất của khách trong cuộc trò chuyện này
            if conversation_id:
                conv = await db.fetchrow("SELECT customer_ref FROM conversations WHERE id = $1", conversation_id)
                db_order = await db.fetchrow(
                    "SELECT * FROM orders WHERE conversation_id = $1 ORDER BY created_at DESC LIMIT 1",
                    conversation_id
                )
                if not db_order and conv and conv.get("customer_ref"):
                    db_order = await db.fetchrow(
                        "SELECT * FROM orders WHERE customer_ref = $1 ORDER BY created_at DESC LIMIT 1",
                        conv["customer_ref"]
                    )
            if not db_order:
                # Tìm đơn gần nhất trong toàn bộ hệ thống
                db_order = await db.fetchrow("SELECT * FROM orders ORDER BY created_at DESC LIMIT 1")

        if db_order:
            ma_tim = db_order.get("ma_van_don") or db_order["ma_don"]
            track = await tra_cuu_van_don(ma_tim)
            st_giao = track.trang_thai_noi_bo.value if track else "delivering"
            st_don = db_order.get("trang_thai")
            if st_giao == "returned":
                st_don = "da_huy"
                mo_ta_trang_thai = "Đơn hàng đã bị huỷ / hoàn trả trên hệ thống vận chuyển."
            elif st_giao == "delivered":
                st_don = "da_giao"
                mo_ta_trang_thai = "Đơn hàng đã giao thành công đến người nhận."
            elif st_giao == "delivery_failed":
                mo_ta_trang_thai = "Giao hàng không thành công (shipper đang hẹn lại khách)."
            else:
                mo_ta_trang_thai = "Đơn hàng đang trong quá trình vận chuyển."

            return {
                "tim_thay": True,
                "ma_don": db_order["ma_don"],
                "ma_van_don": db_order.get("ma_van_don") or "",
                "khach_ten": db_order.get("khach_ten"),
                "tong_tien": int(db_order.get("tong_tien") or 0),
                "trang_thai_don": st_don,
                "trang_thai_giao_hang": st_giao,
                "mo_ta_trang_thai": mo_ta_trang_thai,
                "vi_tri_hien_tai": track.vi_tri_hien_tai if track else "Kho hàng",
                "ngay_du_kien_giao": track.ngay_du_kien_giao.strftime("%d/%m/%Y") if track and track.ngay_du_kien_giao else None,
                "lich_su": [
                    {"thoi_gian": str(it.thoi_gian), "mo_ta": it.mo_ta, "dia_diem": it.dia_diem}
                    for it in (track.lich_su if track else [])
                ],
            }

        for dh in catalog.get("don_hang", []):
            if _norm(dh.get("ma", "")) == _norm(ma):
                return {"tim_thay": True, **dh}
        return {"tim_thay": False, "ghi_chu": f"Không có mã đơn '{ma}' trong hệ thống."}

    if name == "tao_van_don":
        from agent.shipping import tao_van_don_cho_don
        ma_don = str(args.get("ma_don", "")).strip()
        res = await tao_van_don_cho_don(ma_don)
        if res.ok:
            return {
                "tao_duoc": True,
                "ma_don": ma_don,
                "ma_van_don": res.ma_van_don,
                "don_vi": res.don_vi,
                "phi_van_chuyen": res.phi_van_chuyen,
                "trang_thai": res.trang_thai_noi_bo.value,
                "ngay_du_kien_giao": res.ngay_du_kien_giao.strftime("%d/%m/%Y") if res.ngay_du_kien_giao else None,
            }
        return {"tao_duoc": False, "ly_do": res.loi}

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

        # --- Chốt 4: kiểm tồn kho ngay trước khi chốt ---
        ton = int(sp.get("ton_kho") or 0)
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

    # --- Tính phí vận chuyển theo chính sách (Freeship từ 500k) ---
    phi_ship = 30000 if tong < 500000 else 0
    tong_thanh_toan = tong + phi_ship

    # --- Chốt 5: vượt ngưỡng thì KHÔNG tự chốt, đưa vào hàng chờ duyệt ---
    tu_chot = tong < settings.nguong_tu_chot_vnd
    trang_thai = "da_chot" if tu_chot else "cho_duyet"

    ma_don = "AS" + __import__("time").strftime("%y%m%d%H%M%S")

    # --- Khởi tạo Sales Order trên ERP (NextERP / MockERP) ---
    from agent.erp import cap_nhat_ma_van_don_erp, tao_sales_order_erp
    so_erp = None
    try:
        so_erp = await tao_sales_order_erp(
            khach_ten=str(args["khach_ten"]).strip(),
            khach_sdt=sdt,
            khach_dia_chi=str(args["khach_dia_chi"]).strip(),
            items=[{"item_code": l["ma"], "qty": l["so_luong"], "rate": l["don_gia"]} for l in lines],
            shipping_fee=phi_ship,
            notes=f"Đơn hàng tự động qua AI Agent #{ma_don}",
        )
    except Exception:
        pass

    erp_id = so_erp.name if so_erp else None
    erp_prov = settings.erp_provider

    # --- Chốt 6: chống tạo trùng (unique index trên conversation + items) ---
    try:
        row = await db.fetchrow(
            """
            INSERT INTO orders (ma_don, conversation_id, khach_ten, khach_sdt,
                                khach_dia_chi, items, tong_tien, phi_van_chuyen,
                                erp_order_id, erp_provider, trang_thai, ghi_chu)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) RETURNING id, ma_don
            """,
            ma_don, conversation_id,
            str(args["khach_ten"]).strip(), sdt,
            str(args["khach_dia_chi"]).strip(),
            lines, tong_thanh_toan, phi_ship,
            erp_id, erp_prov, trang_thai, args.get("ghi_chu"),
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
    du_hang, ly_do_kho = await kho.giu_hang(lines, row["ma_don"])
    if not du_hang:
        await db.execute("DELETE FROM orders WHERE id = $1", row["id"])
        return {"tao_duoc": False, "ly_do": ly_do_kho}

    await db.log_event(
        "order.created", ref_id=row["id"], ma_don=row["ma_don"],
        tong_tien=tong_thanh_toan, phi_ship=phi_ship,
        erp_order_id=erp_id, trang_thai=trang_thai,
    )

    # --- Chốt 8: Tự động đẩy sang Hãng Vận Chuyển khi đơn đã chốt ---
    ma_van_don = None
    if tu_chot:
        from agent.shipping import tao_van_don_cho_don
        wb_res = await tao_van_don_cho_don(row["ma_don"])
        if wb_res.ok and wb_res.ma_van_don:
            ma_van_don = wb_res.ma_van_don
            if so_erp:
                try:
                    await cap_nhat_ma_van_don_erp(so_erp.name, ma_van_don, settings.shipping_provider)
                except Exception:
                    pass

    return {
        "tao_duoc": True,
        "ma_don": row["ma_don"],
        "erp_order_id": erp_id,
        "ma_van_don": ma_van_don,
        "items": lines,
        "tien_hang": tong,
        "phi_ship": phi_ship,
        "tong_tien": tong_thanh_toan,
        "trang_thai": trang_thai,
        "ghi_chu_cho_agent": (
            (
                f"Đơn đã chốt. Báo mã đơn #{row['ma_don']}"
                + (f" và mã vận đơn {ma_van_don}" if ma_van_don else "")
                + (f", tiền hàng {tong:,}đ + phí ship {phi_ship:,}đ" if phi_ship > 0 else f", tiền hàng {tong:,}đ (Freeship)")
                + f" = Tổng thanh toán COD: {tong_thanh_toan:,}đ cho khách."
            )
            if tu_chot else
            "Đơn giá trị lớn nên đang CHỜ NHÂN VIÊN DUYỆT. Báo khách là đã ghi "
            "nhận và sẽ có người gọi xác nhận, KHÔNG nói là đã chốt xong."
        ),
    }


# Bí danh tương thích
execute = run_tool

