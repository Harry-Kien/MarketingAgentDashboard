"""
Công cụ nghiệp vụ mà agent được phép gọi.

NGUYÊN TẮC BẤT DI BẤT DỊCH: giá, tồn kho, thành phần, tình trạng đơn CHỈ
đến từ đây. Model không bao giờ được nói những con số đó từ trí nhớ.

MVP đọc từ data/catalog.json. Khi lên production, thay phần thân hàm bằng
lời gọi ERP/KiotViet/Haravan — chữ ký và schema giữ nguyên, agent không đổi.
"""
from __future__ import annotations

import json
import unicodedata

from agent.config import ROOT, settings

CATALOG_PATH = ROOT / "data" / "catalog.json"

TOOLS: list[dict] = [
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
    catalog = _catalog()
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

    # ---------- đơn hàng ----------
    if name == "tra_cuu_don_hang":
        ma = _norm(args.get("ma_don", ""))
        for dh in catalog.get("don_hang", []):
            if _norm(dh.get("ma", "")) == ma:
                return {"tim_thay": True, **dh}
        return {"tim_thay": False, "ghi_chu": "Không có mã đơn này trong hệ thống."}

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

    await db.log_event(
        "order.created", ref_id=row["id"], ma_don=row["ma_don"],
        tong_tien=tong, trang_thai=trang_thai,
    )
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
