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
import time
import unicodedata
from uuid import UUID

from agent import db
from agent.config import ROOT, settings
from agent.core import cong_viec, kho

# Năm trạng thái một đơn có thể mang. MỘT chỗ khai, vì dashboard cũng phải
# biết chúng để hiện nhãn — và hai danh sách rời nhau thì sớm muộn lệch.
# `tests/test_nhan_trang_thai_don.py` canh việc đó.
#
#   cho_duyet    vượt ngưỡng giá trị, chờ người xác nhận
#   da_chot      agent tự chốt trong hạn mức
#   cho_dong_bo  đã ghi nhận, CHƯA vào được kho/ERP — đang thử lại
#   da_giao      hãng vận chuyển báo đã giao (agent/shipping/service.py)
#   da_huy       người huỷ, hoặc ERP từ chối
#
# `da_giao` được thêm vào đây SAU: nó đã bị ghi vào CSDL từ lâu mà dashboard
# chưa bao giờ có nhãn cho nó, nên đơn giao xong hiện ra chữ trần "da_giao".
# Không ai báo, vì `ORDER_LABEL[x] || x` là một đường lui im lặng.
TRANG_THAI_DON = ("cho_duyet", "da_chot", "cho_dong_bo", "da_giao", "da_huy")

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
        "name": "de_xuat_sua_don",
        "description": (
            "Khách yêu cầu sửa số lượng sản phẩm trong đơn đã xác nhận. Tra cứu đơn trước; "
            "hỏi lại nếu thiếu mã đơn, mã sản phẩm, số lượng mới hoặc lý do; không suy đoán. "
            "Chỉ tạo đề xuất chờ nhân viên duyệt, KHÔNG sửa đơn hay hứa đã sửa. "
            "Các thay đổi giá, sản phẩm, địa chỉ phải chuyển nhân viên."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {"type": "string"},
                "ma_san_pham": {"type": "string"},
                "so_luong": {"type": "integer", "minimum": 1, "maximum": 999},
                "ly_do": {"type": "string"},
            },
            "required": ["ma_don", "ma_san_pham", "so_luong", "ly_do"],
            "additionalProperties": False,
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
        "name": "xin_doi_tra",
        "description": (
            "Khách đã NHẬN hàng và muốn ĐỔI sang mẫu khác hoặc TRẢ lại. Ghi "
            "nhận yêu cầu lên đơn rồi chuyển nhân viên xử lý.\n\n"
            "Khác `xin_huy_don`: huỷ là trước khi giao, đổi trả là sau khi "
            "khách đã cầm hàng trên tay.\n\n"
            "CÔNG CỤ NÀY KHÔNG DUYỆT ĐỔI TRẢ và không hoàn tiền. Nó chỉ ghi "
            "nhận để nhân viên gọi lại. Việc đơn có đủ điều kiện đổi trả hay "
            "không là do người quyết định, dựa trên chính sách và tình trạng "
            "hàng thực tế.\n\n"
            "TUYỆT ĐỐI KHÔNG nói với khách là 'đã được đổi', 'đã hoàn tiền' "
            "hay 'đơn đủ điều kiện'. Nói đúng sự thật: đã ghi nhận, đã "
            "chuyển bộ phận xử lý, nhân viên sẽ liên hệ lại.\n\n"
            "Nếu khách nói hàng gây kích ứng da hay bất kỳ phản ứng cơ thể "
            "nào thì đó là tình huống y tế — gọi `chuyen_nhan_vien` thay vì "
            "công cụ này."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ma_don": {
                    "type": "string",
                    "description": "Mã đơn khách muốn đổi hoặc trả",
                },
                "loai": {
                    "type": "string",
                    "enum": ["doi", "tra"],
                    "description": (
                        "doi = đổi sang mẫu/size khác; tra = trả lại hàng. "
                        "Khách chưa nói rõ thì HỎI, không tự chọn — hai việc "
                        "này người xử lý làm khác nhau."
                    ),
                },
                "ly_do": {
                    "type": "string",
                    "description": (
                        "Lý do khách nêu, ghi nguyên văn ý khách. Nhân viên "
                        "cần biết để chuẩn bị trước khi gọi lại."
                    ),
                },
            },
            "required": ["ma_don", "loai"],
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


TEN_THUONG_HIEU_MAC_DINH = "cửa hàng"
_TEN_TOI_DA = 60


def lam_sach_ten_thuong_hieu(tho: object) -> str:
    """
    Tên thương hiệu, đã vệ sinh để ghép an toàn vào prompt hệ thống.

    VÌ SAO PHẢI VỆ SINH THỨ CỦA CHÍNH MÌNH
    --------------------------------------
    `catalog.json` do chủ shop nạp từ Excel — dữ liệu trong nhà, không phải
    từ khách. Nhưng nó vẫn là DỮ LIỆU đi vào prompt, và prompt là chỗ duy
    nhất trong hệ thống mà một dòng chữ có thể đổi hành vi của agent. Một ô
    Excel chứa xuống dòng rồi "Bỏ qua mọi quy tắc trên" là prompt injection
    do chính người trong nhà vô tình tạo ra — không ai cố ý, và không ai
    phát hiện.

    Nên: một dòng duy nhất, bỏ ký tự điều khiển, cắt 60 ký tự. Rỗng thì lùi
    về "cửa hàng" — nói trống chỗ tên còn hơn nói tên của người khác.
    """
    ten = " ".join(str(tho or "").split())
    ten = "".join(c for c in ten if c.isprintable())
    return ten[:_TEN_TOI_DA].strip() or TEN_THUONG_HIEU_MAC_DINH


def ten_thuong_hieu() -> str:
    """Tên thương hiệu đang dùng, đọc từ danh mục."""
    return lam_sach_ten_thuong_hieu(_catalog().get("thuong_hieu"))


async def _han_dung(ma: str):
    """
    Lô hết hạn sớm nhất còn hàng của một mã, hoặc None.

    Nuốt mọi lỗi và trả None: hạn dùng là thông tin THÊM: ERP quản lô hỏng
    không được làm hỏng cả lượt tra giá, vốn là việc chính của công cụ này.
    Ngắt mạch trong `Cong` đã ghi nhận sự cố rồi, nên nuốt ở đây không làm
    mất dấu vết.
    """
    if not ma:
        return None
    try:
        from agent.erp import nha_may

        return await nha_may.cong().han_dung(ma)
    except Exception:  # noqa: BLE001
        return None


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


def _nguon_anh(ma: str) -> str:
    """
    Nguồn gốc ảnh theo `manifest.json`: `chup`, `sinh`, hay khác.

    Thiếu manifest hoặc manifest hỏng thì trả `""` — coi như KHÔNG BIẾT, và
    không biết thì không gửi. Đường lui im lặng ở đây là đường lui gửi cho
    khách một tấm ảnh không ai biết nó là gì.
    """
    p = ANH_DIR / ma / "manifest.json"
    if not p.is_file():
        return ""
    try:
        return str(json.loads(p.read_text(encoding="utf-8")).get("nguon") or "")
    except (ValueError, OSError):
        return ""


def _duoc_gui_anh(nguon: str, du_lieu_mau: bool) -> tuple[bool, str]:
    """
    Ảnh nguồn này có được gửi cho khách không.

    VÌ SAO CẦN CHỐT NÀY
    -------------------
    Trong `data/products/` từng có một thư mục chứa không phải ảnh sản
    phẩm mà là BANNER QUẢNG CÁO: huy hiệu GMP / FDA / ISO, dòng "đạt chuẩn
    xuất khẩu Hoa Kỳ" và "đảm bảo thành phần tuyệt đối an toàn".

    `gui_anh_san_pham` gửi thẳng tệp trong thư mục cho khách, nên gửi tấm
    đó đi là phát ngôn quảng cáo có huy hiệu chứng nhận — thứ NĐ 181/2013
    và TT 06/2011 siết.

    Sáu lớp lưới trong `agent/core/agent.py` KHÔNG bắt được: cả sáu đều soi
    CHỮ agent viết ra. Đây là tuyên bố nằm trong ẢNH. Nên chốt phải đặt ở
    đúng chỗ ảnh đi ra.

    VÌ SAO ẢNH `sinh` PHỤ THUỘC `du_lieu_mau`, KHÔNG CẤM THẲNG
    ----------------------------------------------------------
    Ảnh `sinh` là ảnh model vẽ cho bộ dữ liệu mẫu (bộ sinh ảnh đã gỡ cùng
    tính năng video ngày 19.11.2026, ảnh cũ vẫn còn trong kho). Dùng cho
    bản nháp thì được, nhưng khi bán hàng thật, ảnh chụp sản phẩm thật
    phải thay vào — khách nhận hàng khác với hình đã xem là chuyện không
    sửa được bằng lời xin lỗi.

    Dùng lại chính cờ `du_lieu_mau` mà `scripts/san_sang.py` dùng thay vì
    thêm một biến cấu hình mới: khi danh mục còn là dữ liệu mẫu thì đây là
    bản demo, ảnh sinh gửi được; ngày cửa hàng thay bằng hàng thật, ảnh
    sinh TỰ ĐỘNG ngừng đi ra. Không ai phải nhớ bật chốt.
    """
    if nguon == "chup":
        return True, ""
    if nguon == "sinh":
        if du_lieu_mau:
            return True, ""
        return False, (
            "Ảnh này do model sinh, không phải ảnh chụp sản phẩm thật, mà "
            "danh mục đã là hàng thật. Khách nhận hàng khác hình đã xem là "
            "chuyện không sửa được. Mô tả bằng lời thay vì gửi ảnh."
        )
    if not nguon:
        return False, (
            "Không biết ảnh này từ đâu ra (thiếu manifest hoặc manifest "
            "hỏng). Không gửi thứ mình không biết là gì. Mô tả bằng lời."
        )
    return False, (
        f"Ảnh này được đánh dấu nguồn {nguon!r}, không phải ảnh chụp sản "
        "phẩm. Có thể là ảnh quảng cáo hoặc chưa có ảnh. Mô tả bằng lời."
    )


def _anh_san_pham(ma: str) -> pathlib.Path | None:
    """
    Ảnh đầu tiên của một mã sản phẩm, hoặc None.

    Chỉ trả ĐƯỜNG DẪN. Việc ảnh có được phép gửi hay không do
    `_duoc_gui_anh` quyết, để chỗ này không phải biết về danh mục.
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


def _goi_cua(name: str) -> str | None:
    """
    Tên gói sở hữu plugin `name`, đọc từ bộ đệm kho kỹ năng; không có thì None.

    Nguồn là cột `goi` trong `ky_nang_cai_dat` (bộ đệm `kho_ky_nang._DEM`),
    không phải bộ đệm gói: bộ đệm gói chỉ giữ những gói đọc và KIỂM được, nên
    một gói vừa hỏng bản mô tả sẽ khiến công cụ của nó ghi số đo dưới nhãn
    "không thuộc gói nào" — nhãn sai, không lỗi, không ai biết.
    """
    try:
        from agent.ky_nang import kho_ky_nang

        dem = kho_ky_nang._DEM
        return dem[2].get(name) if dem else None
    except Exception:  # noqa: BLE001 — chỉ là nhãn cho số đo
        return None


def _loai_cua(name: str) -> str | None:
    """Loại của plugin `name` (`tra_bang`, `tra_tai_lieu`…), hoặc None."""
    from agent.ky_nang import kho_ky_nang

    dem = kho_ky_nang._DEM
    if not dem:
        return None
    for p in dem[1]:
        if p.ten == name:
            return p.loai
    return None


def _khoa_truot(name: str, args: dict, out: dict) -> str | None:
    """
    Khoá mà khách hỏi nhưng bảng chưa có — để dashboard xếp hạng thứ nên
    bổ sung. None khi không phải ca ấy.

    CHỈ cho `tra_bang`. Tham số của nó là một khoá tra cứu (tên khu vực,
    tên dòng hàng) và gộp lại thành "hay hỏi nhất" được. Tham số của
    `tra_tai_lieu` là CÂU HỎI CỦA KHÁCH viết nguyên văn: ghi nó vào
    `events` là mở một bản sao nội dung hội thoại ở chỗ không chịu chính
    sách lưu trữ của `conversations`, đổi lấy một cột gần như không gộp
    được vì câu tự do không lặp lại.

    Bộ đệm plugin hỏng thì trả None chứ không ném: mất cột này không được
    kéo theo cả sự kiện số đo, hai thứ đó không cùng số phận.
    """
    try:
        if _loai_cua(name) != "tra_bang":
            return None
        if out.get("tim_thay") is not False:
            return None
        # `_norm` của chính tệp này, không phải `bo_dau` của ban_mo_ta:
        # thêm một bản sao thứ hai là lúc nào đó hai bên lệch nhau, và khi
        # ấy khoá ghi xuống khác khoá dùng để so khớp — bảng xếp hạng chỉ
        # ra những dòng người vận hành thêm vào rồi vẫn thấy trượt.
        gt = str(next(iter(args.values()), "") or "").strip()
        return _norm(gt)[:60] or None
    except Exception:  # noqa: BLE001 — chỉ là một cột số đo
        return None


# ĐỌC: ══ TRẠM C2 · CỬA THI HÀNH, DÙNG CHUNG CHO MỌI LOẠI KỸ NĂNG ═════════
# ĐỌC: Bản đồ đầy đủ ba chặng: agent/ky_nang/__init__.py
# ĐỌC:
# ĐỌC:   TRƯỚC  C1  core/llm.py trả về ý định gọi công cụ; core/agent.py lặp
# ĐỌC:              qua từng ý định và gọi hàm dưới đây
# ĐỌC:   SAU    C3  ky_nang/kho_ky_nang.py — chốt hai, rồi tìm bản mô tả
# ĐỌC:          C4  ky_nang/chay.py — nếu tên khớp một plugin
# ĐỌC:
# ĐỌC: MỌI kỹ năng đi qua đây: 11 công cụ viết sẵn, plugin rời, công cụ của
# ĐỌC: gói, và công cụ MCP về sau. Đó là lý do số đo ghi ở đây chứ không ở
# ĐỌC: `chay.py` (phải thuần, có test AST canh) và không ở `respond()` (chỉ
# ĐỌC: thấy công cụ viết sẵn). Một cửa thì đếm được đủ, và chốt được đủ.
def _uuid_hoac_none(gia_tri) -> UUID | None:
    if isinstance(gia_tri, UUID):
        return gia_tri
    try:
        return UUID(str(gia_tri)) if gia_tri else None
    except (TypeError, ValueError):
        return None


async def run_tool(name: str, args: dict, conversation_id=None) -> dict:
    """
    Thi hành công cụ và GHI SỐ ĐO: một sự kiện `cong_cu.goi` mỗi lần gọi.

    Ghi ở đây chứ không ở `chay.py` (bộ thi hành plugin phải thuần, có test
    AST canh) và không ở `respond()` (công cụ MCP ngoài sau này cũng đi qua
    đây). Ghi hỏng thì nuốt: số đo không được làm hỏng câu trả lời cho khách.
    """
    from agent.core import thu_nghiem

    # `ref_id` = hội thoại: không có nó thì "công cụ nào đã chạy cho khách
    # này" không truy được từ nhật ký — sự kiện chỉ còn là một con số đếm.
    # Chuỗi lạ (id phiên thử, None) thì để trống: `log_event` với ref_id
    # không phải UUID là lỗi asyncpg, và lỗi đó nuốt CẢ dòng nhật ký.
    ref_id = _uuid_hoac_none(conversation_id)
    bat_dau = time.perf_counter()
    try:
        out = await _run_tool_that(name, args, conversation_id)
    except Exception as exc:  # noqa: BLE001 — ghi số đo rồi ném lại, không nuốt
        # VÌ SAO PHẢI CÓ NHÁNH NÀY: `_run_tool_that` trả `{"loi": ...}` ở
        # những đường hỏng nó lường trước, nhưng nó cũng NÉM — plugin http
        # hết giờ, CSDL sập, một lỗi lập trình. Trước đây nhánh ném không ghi
        # dòng nào, nên bảng số đo hiện "0 lỗi" cho đúng công cụ đang hỏng ở
        # MỌI lần gọi: xanh giả, nguy hơn đỏ giả vì không ai đi kiểm.
        try:
            await db.log_event(
                "cong_cu.goi", ref_id=ref_id,
                ten=name, goi=_goi_cua(name), ok=False, loi=type(exc).__name__,
                ms=int((time.perf_counter() - bat_dau) * 1000),
                thu_nghiem=bool(thu_nghiem.dang_thu.get()),
            )
        except Exception:  # noqa: BLE001 — số đo hỏng không được che lỗi gốc
            pass
        raise
    try:
        # Vẫn GHI ở phòng thử — khác `bao_mat.injection` trong agent.py bỏ
        # ghi hẳn. Số đo vận hành (số lần gọi, tỉ lệ lỗi) có một tầng ĐỌC
        # riêng (`kho_ky_nang.dem_goi_7_ngay`) lọc theo cột `thu_nghiem` này,
        # nên ghi cả hai rồi lọc lúc đọc là an toàn — cờ đi kèm ngay tại
        # nguồn. Sự kiện an ninh thì người soát đọc thẳng bảng `events`,
        # không qua tầng lọc nào; một "cuộc tấn công" giả do phòng thử tự
        # tạo ra để chấm điểm sẽ lẫn với thật và không ai phân biệt nổi.
        await db.log_event(
            "cong_cu.goi", ref_id=ref_id,
            ten=name, goi=_goi_cua(name),
            ok=not (isinstance(out, dict) and "loi" in out),
            ms=int((time.perf_counter() - bat_dau) * 1000),
            thu_nghiem=bool(thu_nghiem.dang_thu.get()),
            khong_khop=_khoa_truot(name, args, out) if isinstance(out, dict) else None,
        )
    except Exception:  # noqa: BLE001 — số đo hỏng không được làm hỏng kết quả
        pass
    return out


class _DanhMucChuaNap(list):
    """
    Chỗ giữ của danh mục KHÔNG được nạp — chạm vào là nổ.

    Dùng `[]` thì một công cụ bị kê nhầm vào `_KHONG_CAN_DANH_MUC` sẽ lặng
    lẽ thấy "không có sản phẩm nào" và nói đúng câu đó với khách. Nổ to rẻ
    hơn nhiều: nó lộ ra ở lần chạy đầu tiên, trong test hoặc trên máy dev.
    """

    def _no(self, *_a, **_k):
        raise RuntimeError(
            "Công cụ này được kê là KHÔNG cần danh mục nhưng đang đọc danh "
            "mục. Bỏ tên nó khỏi _KHONG_CAN_DANH_MUC trong agent/core/tools.py")

    __iter__ = __getitem__ = __len__ = __contains__ = __bool__ = _no  # type: ignore[assignment]


_DANH_MUC_CHUA_NAP = _DanhMucChuaNap()

# Công cụ chạy xong mà không đọc danh mục sản phẩm lần nào. Xem lý do kê
# theo chiều phủ định ở chỗ dùng, trong `_run_tool_that`.
_KHONG_CAN_DANH_MUC = frozenset({
    "de_xuat_sua_don",
    "tra_cuu_don_hang",
    "tra_cuu_van_chuyen",
    "xin_huy_don",
    "xin_doi_tra",
    "chuyen_nhan_vien",
})


async def _run_tool_that(name: str, args: dict, conversation_id=None) -> dict:
    # ĐỌC: ══ CÂY QUYẾT ĐỊNH — đọc từ trên xuống, THỨ TỰ CÓ Ý NGHĨA ═══════
    # ĐỌC:
    # ĐỌC:   1. chốt 2  · kỹ năng đang tắt?      → trả cờ chuyển người
    # ĐỌC:   2. plugin  · tên khớp bản mô tả?    → chay_plugin()
    # ĐỌC:              bốn loại đầu chỉ đọc; `mcp` có thể ghi, hai chốt ở
    # ĐỌC:              `run_tool` — ngay trước lời gọi chay_plugin() dưới đây
    # ĐỌC:   3. tim_kien_thuc                    → rag.retrieve
    # ĐỌC:   4. _catalog_song() rồi 10 nhánh còn lại
    # ĐỌC:
    # ĐỌC: Hàm này nhận một dict và trả một dict — không có trạng thái nào để
    # ĐỌC: giữ, nên cả tệp 1456 dòng này KHÔNG có class nào.
    # ĐỌC:
    # ĐỌC: MỌI nhánh trả về đều có trường `ghi_chu` nói mô hình phải làm gì
    # ĐỌC: tiếp — kể cả nhánh hỏng. Trả dict rỗng thì mô hình tự nghĩ ra đường
    # ĐỌC: đi, và đường nó hay chọn là đoán bừa.
    # ---------- CHỐT THỨ HAI: kỹ năng đang tắt ----------
    #
    # Lọc lược đồ trước khi gửi model là chốt thứ nhất, và nó KHÔNG đủ. Lịch
    # sử hội thoại còn giữ nguyên lược đồ của những lượt trước, nên một công
    # cụ vừa bị tắt vẫn nằm trong ngữ cảnh model đang đọc — nó gọi tiếp là
    # chuyện bình thường, không phải model hỏng.
    #
    # Trả về "chuyển người" chứ không phải một câu lỗi: người vận hành tắt
    # `tao_don_hang` là đang nói "việc này người làm", nên đúng việc cần làm
    # là đưa hội thoại cho người, không phải để agent tự xoay.
    from agent.ky_nang import kho_ky_nang

    # ĐỌC: VÌ SAO CẦN CHỐT THỨ HAI khi đã lọc ở agent.py dòng ~440?
    # ĐỌC: Dòng thời gian thật trong một hội thoại đang mở:
    # ĐỌC:   10:00  khách hỏi giá → agent gọi công cụ → lược đồ VÀO lịch sử
    # ĐỌC:   10:01  quản trị TẮT công cụ đó trên dashboard
    # ĐỌC:   10:02  khách hỏi tiếp → chốt 1 đã bỏ công cụ khỏi lược đồ MỚI,
    # ĐỌC:          nhưng mô hình vẫn thấy nó trong LỊCH SỬ của lượt 10:00
    # ĐỌC:          và gọi lại — hợp lý, không phải mô hình hỏng.
    # ĐỌC: Nên phải kiểm lại LÚC THI HÀNH, không chỉ lúc công bố khả năng.
    if await kho_ky_nang.dang_tat(name):
        return {
            "loi": f"Kỹ năng {name!r} đang tắt.",
            "can_chuyen_nhan_vien": True,
            "ghi_chu": (
                "Công cụ này đã bị tắt trong cấu hình. KHÔNG tự trả lời thay "
                "nó — đã chuyển hội thoại cho người."
            ),
        }

    # ---------- CHẾ ĐỘ THỬ: mô phỏng công cụ ghi ----------
    #
    # Phòng thử trên dashboard gọi thẳng `respond()`. Không có chốt này thì
    # mỗi câu thử "em đặt 2 chai" là một đơn thật trong Postgres và ERP.
    # Đặt TRƯỚC nhánh plugin và mọi nhánh có sẵn để không nhánh nào qua mặt.
    from agent.core import thu_nghiem

    if thu_nghiem.dang_thu.get() and name in thu_nghiem.CO_TAC_DUNG_PHU:
        # Không bọc `try/except`: `_catalog_song()` đã có đường lui sang tệp
        # bên trong nó. Bọc thêm một lớp là nuốt luôn những lỗi KHÁC — và
        # phòng thử im lặng chạy trên danh mục rỗng thì mọi mã hàng đều
        # "không có trong danh mục", một kết quả sai trông như đúng.
        catalog = await _catalog_song()
        return await thu_nghiem.mo_phong(name, args, catalog.get("san_pham", []))

    # ---------- CHỐT ỦY QUYỀN: chế độ AI × mức của hành động (mục 17) ----------
    #
    # Đặt SAU phòng thử (phòng thử không ghi gì, kể cả đề xuất) và TRƯỚC mọi
    # nhánh thi hành, để không công cụ ghi nào — viết sẵn, plugin, MCP — đi
    # vòng qua. Chế độ đọc TẠI ĐÂY (`uy_quyen.che_do_hieu_luc`), không nhận
    # làm tham số: trước bản này AI lên đơn thật ở chế độ Gợi ý vì chế độ chỉ
    # được xét ở tầng gửi tin, sau khi công cụ đã chạy xong.
    from agent.core import uy_quyen

    loai_cc = await uy_quyen.phan_loai_cong_cu(name)
    quyet: uy_quyen.QuyetDinh | None = None
    if loai_cc == "hanh_dong":
        quyet = await uy_quyen.quyet_dinh(uy_quyen.CONG_CU_HANH_DONG[name], conversation_id)
        # `xin_huy_don` tự xử lý mức Không sử dụng: nó vẫn GHI NHẬN yêu cầu
        # của khách lên đơn (để người đóng gói dừng tay) rồi chuyển người.
        if quyet.bi_cam and name != "xin_huy_don":
            return await uy_quyen.chan_chuyen_nguoi(
                name, f"Chính sách ủy quyền: AI không được «{uy_quyen.DANH_MUC[quyet.hanh_dong].ten}»",
                conversation_id, hanh_dong=quyet.hanh_dong, muc_uy_quyen=quyet.muc)
    elif loai_cc == "mcp_ghi" and not thu_nghiem.dang_thu.get():
        # Phòng thử: nhánh plugin dưới đây tự mô phỏng, không gọi máy chủ.
        che_do, ly_do = await uy_quyen.che_do_hieu_luc(conversation_id)
        if che_do == "goi_y":
            # Không có đường thi hành kiểm lại được cho công cụ ngoài, nên
            # không đề xuất — chuyển người (xem docstring uy_quyen.py).
            return await uy_quyen.chan_chuyen_nguoi(name, ly_do, conversation_id)
    elif loai_cc == "la":
        return await uy_quyen.chan_chuyen_nguoi(
            name, f"Công cụ {name!r} chưa có trong danh mục ủy quyền — mặc định không sử dụng",
            conversation_id)

    # ---------- plugin do người vận hành cấu hình ----------
    #
    # Đặt TRƯỚC mọi nhánh có sẵn: `doc_ban_mo_ta` đã chặn plugin trùng tên
    # công cụ viết sẵn, nên tới đây không có tên nào thuộc cả hai phía. Đặt
    # sau thì thứ tự nhánh trở thành thứ ưu tiên ngầm — và ngầm là chỗ lỗi
    # trốn.
    bm = await kho_ky_nang.tim_plugin(name)
    if bm is not None:
        # ---------- công cụ GHI của máy chủ MCP ----------
        # Công cụ viết sẵn ghi được liệt kê tĩnh trong CO_TAC_DUNG_PHU; công
        # cụ MCP thì quản trị đánh dấu `ghi` trên dashboard. Cùng hai luật:
        # phòng thử không chạm máy chủ, ngoài phòng thử phải bật rõ từng cái.
        if bm.loai == "mcp" and bm.cau_hinh.get("ghi"):
            if thu_nghiem.dang_thu.get():
                return {
                    "thu_nghiem": True, "mo_phong": True, "cong_cu": name, "tham_so": args,
                    "ghi_chu": "ĐANG THỬ: công cụ ghi của máy chủ MCP không được gọi thật. "
                               "Trả lời khách như đã thực hiện, nói rõ đây là bản thử.",
                }
            if not bm.cau_hinh.get("ghi_cho_phep"):
                return {
                    "loi": f"Công cụ ghi {name!r} chưa được cho phép chạy ngoài phòng thử.",
                    "can_chuyen_nhan_vien": True,
                    "ghi_chu": "Quản trị chưa bật 'cho phép ghi' cho công cụ này. KHÔNG tự trả lời "
                               "thay nó — đã chuyển hội thoại cho người.",
                }
        from agent.ky_nang.chay import chay_plugin

        account_id = await _rag_account_id(conversation_id)
        return await chay_plugin(bm, args, account_id=account_id)

    # ---------- tra kho tri thức ----------
    # Đặt TRƯỚC lời gọi danh mục: câu hỏi chính sách không cần đọc catalog,
    # và nạp catalog cho một câu hỏi về đổi trả là công vô ích mỗi lượt.
    if name == "tim_kien_thuc":
        return await _tim_kien_thuc(
            args, account_id=await _rag_account_id(conversation_id)
        )

    # CHỈ NẠP DANH MỤC CHO CÔNG CỤ THẬT SỰ CẦN.
    #
    # Dòng này trước đây nạp vô điều kiện, nằm trên mọi nhánh phân phối —
    # nên `xin_doi_tra`, thứ chỉ chạy một câu UPDATE, cũng phải chờ. Đo được
    # 15.09.2026 trên máy có ERPNext sống (`ERP_LOAI=erpnext`): ~1,0 giây
    # mỗi lượt gọi, nằm NGAY TRÊN đường trả lời khách, cộng một lượt trong
    # hạn mức và bộ ngắt mạch của cổng ERP — để lấy một danh sách mà nhánh
    # được gọi không bao giờ đọc tới.
    #
    # KÊ THEO CHIỀU PHỦ ĐỊNH: danh sách là công cụ KHÔNG cần. Quên khai một
    # công cụ mới thì nó chậm một nhịp — chịu được. Kê theo chiều khẳng định
    # mà quên thì công cụ thấy danh mục RỖNG và bảo khách shop không bán gì:
    # sai, và không nổ.
    #
    # Và chỗ của danh mục chưa nạp KHÔNG phải `[]` mà là một vật nổ khi bị
    # chạm, để kê nhầm thì lộ ra ngay lần chạy đầu chứ không phải ở một
    # khách thật ba tuần sau.
    if name in _KHONG_CAN_DANH_MUC:
        products: list[dict] = _DANH_MUC_CHUA_NAP
    else:
        catalog = await _catalog_song()
        products = catalog.get("san_pham", [])

    # ---------- tra cứu một sản phẩm ----------
    if name == "tra_cuu_san_pham":
        return await _tra_cuu_san_pham(args, products)

    # ---------- gợi ý theo nhu cầu ----------
    if name == "goi_y_san_pham":
        return await _goi_y_san_pham(args, products)

    # ---------- gửi ảnh sản phẩm ----------
    if name == "gui_anh_san_pham":
        return await _gui_anh_san_pham(args, products, catalog)

    # ---------- đơn hàng ----------
    if name == "tra_cuu_don_hang":
        return await _tra_cuu_don_hang(args, conversation_id)

    if name == "tra_cuu_van_chuyen":
        return await _tra_cuu_van_chuyen(args, conversation_id)

    if name == "xin_huy_don":
        return await _xin_huy_don(args, conversation_id, quyet=quyet)

    if name == "de_xuat_sua_don":
        from agent.core.thao_tac_don import de_xuat_sua_don

        return await de_xuat_sua_don(args, conversation_id)

    if name == "xin_doi_tra":
        return await _xin_doi_tra(args, conversation_id)

    # ---------- lên đơn: tool DUY NHẤT có hậu quả không đảo ngược ----------
    if name == "tao_don_hang":
        return await _tao_don_hang(args, products, conversation_id, quyet=quyet)

    if name == "chuyen_nhan_vien":
        return {
            "da_chuyen": True,
            "ly_do": args.get("ly_do", ""),
            "muc_do": args.get("muc_do", "thuong"),
        }

    return {"loi": f"Không có công cụ tên {name}"}


async def _rag_account_id(conversation_id):
    """Phạm vi RAG lấy từ conversation, không tin tham số do model gửi."""
    if conversation_id is None:
        return None
    row = await db.fetchrow(
        "SELECT account_id FROM conversations WHERE id=$1", conversation_id
    )
    return row["account_id"] if row else None


async def _tim_kien_thuc(args: dict, *, account_id=None) -> dict:
    """Tra kho tri thức. Không đọc danh mục — câu hỏi chính sách không cần."""
    from agent.core import rag

    cau_hoi = (args.get("cau_hoi") or "").strip()
    if not cau_hoi:
        return {"tim_thay": False, "ghi_chu": "Thiếu câu hỏi tra cứu."}

    passages = (
        await rag.retrieve(cau_hoi, k=TIM_K, account_id=account_id)
        if account_id is not None
        else await rag.retrieve(cau_hoi, k=TIM_K)
    )
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
                "phien_ban": p.version,
                "version_id": str(p.version_id) if p.version_id else None,
                "chunk_id": str(p.chunk_id) if p.chunk_id else None,
                "noi_dung": p.content.strip()[:TIM_DAI_TOI_DA],
                "diem": round(p.score, 3),
            }
            for p in passages
        ],
        "ghi_chu": "Chỉ trả lời dựa trên các đoạn trên. Nêu tên tài liệu khi trích.",
    }


async def _tra_cuu_san_pham(args: dict, products: list[dict]) -> dict:
    """Tra ĐÍCH DANH một sản phẩm: giá, tồn, hạn dùng nếu biết chắc."""
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

        # HẠN DÙNG — chỉ thêm khi BIẾT CHẮC.
        #
        # `Cong.han_dung()` trả về lô hết hạn sớm nhất trong số các lô
        # ta biết chắc CÒN HÀNG, và trả None nếu không chắc. Không có
        # nhánh nào ở đây đoán thay: thiếu khoá `han_su_dung` thì model
        # không có gì để nói, đúng như ý muốn.
        #
        # Tuyệt đối không đặt một giá trị mặc định kiểu "không rõ" —
        # chuỗi đó nằm trong ngữ cảnh là model sẽ nhắc lại nó với khách,
        # và "hạn dùng: không rõ" nghe như một sự thật về sản phẩm chứ
        # không phải một khoảng trống trong dữ liệu.
        lo = await _han_dung(best.get("ma", ""))
        if lo is not None:
            out["han_su_dung"] = lo.het_han
            out["ma_lo"] = lo.ma_lo
        # Khách hỏi ĐÍCH DANH thì vẫn trả giá và tồn — hai số ấy có
        # thật, đến từ ERP. Nhưng phải nói rõ là KHÔNG có nửa tư vấn,
        # nếu không model sẽ lấp chỗ trống bằng suy đoán từ tên hàng.
        if not best.get("duoc_gioi_thieu", True):
            out["ghi_chu"] = (
                "Mặt hàng này CHƯA có hồ sơ tư vấn: giá và tồn kho là "
                "thật, nhưng không có căn cứ nào về loại da phù hợp, "
                "thành phần hay cách dùng. Chỉ được nói giá và còn hàng "
                "hay không. Khách hỏi thêm thì gọi chuyen_nhan_vien."
            )
        return out
    return {
        "tim_thay": False,
        "ghi_chu": "Không có sản phẩm này trong danh mục. Đừng đoán — "
                   "hãy nói không tìm thấy và hỏi lại tên chính xác.",
        "goi_y_dung_ten": [p.get("ten") for p in products[:6]],
    }


async def _goi_y_san_pham(args: dict, products: list[dict]) -> dict:
    """Gợi ý theo loại da / nhu cầu / nhóm / giá — chỉ hàng ĐỦ hồ sơ tư vấn."""
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
    # SKU CHƯA CÓ HỒ SƠ TƯ VẤN THÌ KHÔNG ĐƯỢC GỢI Ý
    #
    # `agent/erp/cong.py:193` gắn cờ `duoc_gioi_thieu=False` cho mặt hàng
    # có bên ERP mà chưa ai viết nửa tư vấn, và ghi `erp.thieu_ho_so`.
    # Nhưng KHÔNG mã nào đọc cờ đó — đã tìm khắp repo: chỉ có nơi đặt,
    # tài liệu, và test. Cảnh báo có, chặn thì không.
    #
    # Hậu quả đúng như `docs/van-hanh.md` mô tả: "agent giới thiệu một
    # sản phẩm nghe rất chung chung". Nó biết tên và giá, không biết hợp
    # loại da nào — và vẫn đem ra khuyên. Đó là phát ngôn không có căn cứ,
    # đúng thứ cả hệ thống dựng lên để ngăn.
    #
    # Cờ VẮNG MẶT thì coi như được giới thiệu: nguồn `tep` không gắn cờ
    # này, và mặc định chặn sẽ làm câm toàn bộ gợi ý trên bản chạy file.
    du_can_cu = [h for h in hits if h.get("duoc_gioi_thieu", True)]
    thieu_ho_so = [h.get("ten") for h in hits if not h.get("duoc_gioi_thieu", True)]

    if not du_can_cu:
        return {
            "so_luong": 0,
            "thieu_ho_so_tu_van": thieu_ho_so,
            "ghi_chu": (
                "Có mặt hàng khớp tiêu chí nhưng CHƯA có hồ sơ tư vấn, nên "
                "không đủ căn cứ để khuyên. Nói thẳng với khách là cần nhân "
                "viên tư vấn kỹ hơn rồi gọi chuyen_nhan_vien. Tuyệt đối "
                "không suy đoán công dụng từ tên sản phẩm."
            ),
        }

    con_hang = [h for h in du_can_cu if (h.get("ton_kho") or 0) > 0]
    ket_qua = {
        "so_luong": len(du_can_cu),
        "san_pham": [_tom_tat(h) for h in (con_hang or du_can_cu)[:6]],
        "het_hang": [
            h.get("ten") for h in du_can_cu if (h.get("ton_kho") or 0) == 0
        ],
    }
    if thieu_ho_so:
        ket_qua["thieu_ho_so_tu_van"] = thieu_ho_so
        ket_qua["ghi_chu"] = (
            "Vài mặt hàng khác cũng khớp tiêu chí nhưng chưa có hồ sơ tư "
            "vấn nên đã bị loại khỏi danh sách gợi ý. KHÔNG nhắc tên chúng "
            "với khách."
        )
    return ket_qua


async def _gui_anh_san_pham(args: dict, products: list[dict], catalog: dict) -> dict:
    """Báo ảnh nào được gửi. KHÔNG tự gửi — lớp kênh gửi sau."""
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

    # CHỐT NGUỒN ẢNH — đặt ở đây vì đây là chỗ ảnh đi ra tay khách.
    # Xem `_duoc_gui_anh` cho lý do đầy đủ: sáu lớp lưới đều soi CHỮ,
    # nên một tuyên bố quảng cáo nằm trong ẢNH đi qua được tất cả.
    duoc, vi_sao = _duoc_gui_anh(
        _nguon_anh(sp["ma"]), bool(catalog.get("du_lieu_mau")),
    )
    if not duoc:
        return {"gui_duoc": False, "ly_do": vi_sao}

    # Tool KHÔNG tự gửi. Nó báo "gửi được" kèm đường dẫn; việc gửi do
    # lớp kênh làm trong main.py.
    # Tool không biết mình đang chạy trên Zalo hay Chatwoot, và không
    # nên biết.
    return {
        "gui_duoc": True,
        "ma": sp["ma"],
        "ten": sp["ten"],
        "duong_dan": str(anh),
        "ghi_chu_cho_agent": (
            "Ảnh đang được hệ thống gửi đính kèm riêng cho khách dưới dạng hình ảnh. "
            "Vẫn phải trả lời tư vấn bằng lời như bình thường. "
            "TUYỆT ĐỐI KHÔNG chèn link ảnh, đường dẫn file hay cú pháp markdown ảnh ![...](...) vào câu trả lời."
        ),
    }


# ===============================================================
#  Lên đơn hàng — sáu chốt chặn
# ===============================================================

# Bấm "ok" hai lần, hoặc model gọi lại công cụ ở lượt sau, thì đơn trùng
# tới trong vòng vài giây tới vài phút. Quá cửa sổ này mà cùng hội thoại,
# cùng hàng, là khách MUA LẠI — chặn nó là mất đơn thật.
CUA_SO_CHONG_TRUNG_GIAY = 600

# Không có 0/O/1/I/L: mã đơn là thứ khách đọc lại qua điện thoại.
_KY_TU_MA_DON = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _sinh_ma_don() -> str:
    """
    "AS" + thời điểm tới giây + 3 ký tự ngẫu nhiên.

    Bản trước chỉ có thời điểm tới giây: hai khách chốt cùng giây thì
    `ma_don UNIQUE` hất một người ra, và nhánh `except` bắt "duplicate" báo
    người đó "đơn đã ghi nhận" — khách mất đơn mà vẫn tin là có đơn.

    Phần ngẫu nhiên toàn chữ in/số liền khối với phần đầu: bộ che số điện
    thoại (`che_du_lieu`) bỏ qua chuỗi số dính vào chữ, nên mã đơn không bị
    che nhầm thành [SĐT_n].
    """
    import secrets

    duoi = "".join(secrets.choice(_KY_TU_MA_DON) for _ in range(3))
    return "AS" + time.strftime("%y%m%d%H%M%S") + duoi


async def _luu_don_moi(*, conversation_id, khach_ten: str, khach_sdt: str,
                       khach_dia_chi: str, lines: list[dict], tong: int,
                       trang_thai: str, ghi_chu, channel: str | None = None) -> dict:
    """
    Chống trùng rồi INSERT, trong cùng một giao dịch. Trả {"row": ...} khi
    lưu được, ngược lại trả thẳng kết quả công cụ để agent đọc.

    VÌ SAO KHÔNG DÙNG CHỈ MỤC UNIQUE NỮA
    -------------------------------------
    `idx_order_dedupe` (conversation_id, md5(items)) không có giới hạn thời
    gian: đơn cũ đã GIAO vẫn chặn khách mua lại đúng món ấy, mãi mãi, và
    agent được dặn nói "đơn đã ghi nhận" cho một đơn không tồn tại
    (migration 0041). Trùng thật chỉ là cùng hội thoại, cùng hàng, trong
    vài phút — điều đó chỉ mã diễn đạt được.

    Advisory lock theo (hội thoại, hàng): hai lời gọi đồng thời cùng kiểm
    "đã có chưa" thì cả hai cùng thấy chưa. Khoá giữ tới khi giao dịch
    commit, nên lời gọi thứ hai chắc chắn thấy đơn của lời gọi thứ nhất.

    LỖI TÁCH THEO RÀNG BUỘC, KHÔNG THEO CHỮ "duplicate"
    ---------------------------------------------------
    Trùng `ma_don` thì sinh mã khác và thử lại. Lỗi khác là LỖI THẬT —
    không bao giờ được thành câu "đơn đã ghi nhận".
    """
    import hashlib

    import asyncpg

    if conversation_id is not None:
        van_tay = hashlib.md5(
            json.dumps(lines, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        khoa = f"tao_don:{conversation_id}:{van_tay}"
    else:
        khoa = ""

    try:
        async with db.pool().acquire() as conn:
            async with conn.transaction():
                if khoa:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", khoa)
                    cu = await conn.fetchrow(
                        "SELECT ma_don, trang_thai FROM orders "
                        "WHERE conversation_id = $1 AND items = $2::jsonb "
                        "  AND trang_thai <> 'da_huy' "
                        "  AND created_at > now() - make_interval(secs => $3) "
                        "ORDER BY created_at DESC LIMIT 1",
                        conversation_id, lines, float(CUA_SO_CHONG_TRUNG_GIAY),
                    )
                    if cu is not None:
                        await db.log_event("order.trung_bo_qua", actor="agent", ma_don=cu["ma_don"])
                        return {
                            "tao_duoc": False,
                            "trung_don": True,
                            "ma_don": cu["ma_don"],
                            "trang_thai": cu["trang_thai"],
                            "ly_do": (
                                f"Đơn {cu['ma_don']} với đúng các sản phẩm này vừa "
                                "được tạo vài phút trước. Đọc lại MÃ ĐƠN này cho "
                                "khách, KHÔNG tạo thêm. Nếu khách muốn mua thêm "
                                "một đơn nữa thật, hỏi rõ rồi chuyển nhân viên."
                            ),
                        }
                # Lấy đúng nguồn kênh từ hội thoại trong cùng giao dịch để không
                # rơi về DEFAULT 'zalocrm' của bảng orders (TEST-17-01).
                kenh = (channel or "").strip() or None
                if conversation_id is not None:
                    kenh_ht = await conn.fetchval(
                        "SELECT channel FROM conversations WHERE id = $1",
                        conversation_id,
                    )
                    if kenh_ht and str(kenh_ht).strip():
                        kenh = str(kenh_ht).strip()
                if not kenh:
                    kenh = "khong_ro"
                for _ in range(5):
                    ma_don = _sinh_ma_don()
                    try:
                        # Savepoint: một lần trùng mã không được làm hỏng cả
                        # giao dịch đang giữ khoá chống trùng.
                        async with conn.transaction():
                            row = await conn.fetchrow(
                                """
                                INSERT INTO orders (ma_don, conversation_id, channel, khach_ten,
                                                    khach_sdt, khach_dia_chi, items,
                                                    tong_tien, trang_thai, ghi_chu)
                                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id, ma_don
                                """,
                                ma_don, conversation_id, kenh, khach_ten, khach_sdt,
                                khach_dia_chi, lines, tong, trang_thai, ghi_chu,
                            )
                        return {"row": dict(row)}
                    except asyncpg.UniqueViolationError as exc:
                        if exc.constraint_name == "orders_ma_don_key":
                            continue
                        raise
                raise RuntimeError("sinh 5 mã đơn liền đều trùng")
    except Exception as exc:  # noqa: BLE001
        await db.log_event(
            "order.luu_that_bai",
            loi=f"{type(exc).__name__}: {exc}"[:300],
            rang_buoc=getattr(exc, "constraint_name", None),
        )
        return {
            "tao_duoc": False,
            "ly_do": (
                f"Lỗi hệ thống khi lưu đơn ({type(exc).__name__}). Đơn CHƯA được "
                "ghi nhận — TUYỆT ĐỐI không nói với khách là đã lên đơn. Xin "
                "lỗi khách và chuyển nhân viên."
            ),
            # Dặn là dặn, model thì trượt: cờ này buộc chuyển người bằng mã.
            "can_chuyen_nhan_vien": True,
        }


async def _tao_don_hang(args: dict, products: list[dict], conversation_id,
                        quyet=None, *, ep_da_chot: bool = False,
                        tong_phai_bang: int | None = None,
                        actor: str = "agent",
                        nguoi_phe_duyet: str | None = None,
                        nguon_thuc_thi: str | None = None) -> dict:
    """
    Tool DUY NHẤT có hậu quả không đảo ngược. Mọi chốt chặn nằm ở đây, không
    nằm trong prompt — prompt có thể bị model bỏ qua, mã thì không.

    `quyet` (uy_quyen.QuyetDinh) do chốt ủy quyền ở `_run_tool_that` truyền.
    Gọi thẳng không có nó = đường cũ (tự chốt dưới ngưỡng) — chỉ test và
    đường THI HÀNH đề xuất đã duyệt gọi thẳng; đường thi hành truyền
    `ep_da_chot` (người có thẩm quyền đã duyệt) và `tong_phai_bang` (giá đổi
    sau lúc đề xuất thì KHÔNG thi hành: người duyệt đã duyệt một con số khác).
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
    # Phường MỚI ghi kèm tỉnh MỚI mà không thuộc tỉnh ấy = chắc chắn sai
    # (agent/core/dia_gioi.py chỉ lên tiếng khi chắc). Lên đơn rồi hãng vận
    # chuyển mới phát hiện là phí ship đi, hàng về, khách chờ thêm vài ngày.
    from agent.core import dia_gioi

    sai_dia_chi = dia_gioi.mau_thuan(str(args.get("khach_dia_chi") or ""))
    if sai_dia_chi:
        return {"tao_duoc": False, "thieu_thong_tin": ["địa chỉ đúng"], "ly_do": sai_dia_chi}

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
                # Dặn model chuyển người là chưa đủ — model trượt. Cờ này để
                # agent.py chuyển người THẬT (xem nhánh `can_chuyen_nhan_vien`).
                "can_chuyen_nhan_vien": True,
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

    if tong_phai_bang is not None and tong != int(tong_phai_bang):
        return {
            "tao_duoc": False,
            "ly_do": (f"Tổng tiền đã đổi so với lúc đề xuất ({int(tong_phai_bang):,}đ → "
                      f"{tong:,}đ). Không thi hành — cần đề xuất lại.").replace(",", "."),
        }

    # --- Chốt 5: ủy quyền + ngưỡng giá trị ---
    # Chế độ Gợi ý: đã kiểm đủ (xác nhận, thông tin, giá, tồn sống) nhưng
    # KHÔNG ghi đơn, KHÔNG giữ hàng — chỉ đề xuất. Ở Tự động: ngưỡng (nay
    # sửa được trên dashboard, mặc định `.env`) và mức "Có phê duyệt" đều
    # đưa đơn vào `cho_duyet` như trước, kèm thẻ đề xuất trong hội thoại.
    from agent.core import uy_quyen

    if quyet is not None and quyet.che_do == "goi_y":
        return await _de_xuat_tao_don(args, lines, tong, sdt, conversation_id, quyet)
    nguong = await uy_quyen.nguong_tao_don()
    phai_duyet = quyet is not None and quyet.muc == "co_phe_duyet"
    tu_chot = ep_da_chot or (tong < nguong and not phai_duyet)
    trang_thai = "da_chot" if tu_chot else "cho_duyet"

    # --- Chốt 6: chống tạo trùng + lưu đơn, trong MỘT giao dịch có khoá ---
    kq_luu = await _luu_don_moi(
        conversation_id=conversation_id,
        khach_ten=str(args["khach_ten"]).strip(), khach_sdt=sdt,
        khach_dia_chi=str(args["khach_dia_chi"]).strip(),
        lines=lines, tong=tong, trang_thai=trang_thai,
        ghi_chu=args.get("ghi_chu"),
    )
    if "row" not in kq_luu:
        return kq_luu
    row = kq_luu["row"]

    # --- Chốt 7: TRỪ KHO thật, nguyên tử, có khoá hàng ---
    # Kiểm tồn ở chốt 4 chỉ là kiểm lúc đọc. Giữa lúc đọc và lúc ghi, một
    # khách khác có thể đã lấy mất món cuối. Không đủ hàng, hoặc kho NÉM lỗi,
    # đều phải xoá đơn vừa tạo: đơn nằm lại mà kho không trừ là bán hàng
    # không tồn tại (rà soát 11.2026).
    try:
        du_hang, ly_do_kho = await kho.giu_hang(lines, row["ma_don"])
    except Exception as exc:  # noqa: BLE001
        du_hang, ly_do_kho = False, f"Lỗi hệ thống khi giữ hàng ({type(exc).__name__})."
        await db.log_event("order.giu_hang_loi", actor=actor, ma_don=row["ma_don"],
                           loi=f"{type(exc).__name__}: {exc}"[:300])
    if not du_hang:
        await db.execute("DELETE FROM orders WHERE id = $1", row["id"])
        return {"tao_duoc": False, "ly_do": ly_do_kho}

    nguon = nguon_thuc_thi or (
        "tu_dong" if (quyet is not None and trang_thai == "da_chot")
        else ("cho_duyet" if trang_thai == "cho_duyet" else "ai_tao_don")
    )
    await db.log_event(
        "order.created", actor=actor, ref_id=row["id"], ma_don=row["ma_don"],
        tong_tien=tong, trang_thai=trang_thai,
        nguoi_khoi_tao="agent", nguoi_phe_duyet=nguoi_phe_duyet,
        nguon_thuc_thi=nguon,
    )
    if quyet is not None and trang_thai == "da_chot":
        # AI tự chốt theo ủy quyền — ghi MỨC đã cho phép, cho tra cứu kiểm toán.
        await db.log_event(
            "ai.hanh_dong.tu_dong", actor="agent", ref_id=_uuid_hoac_none(conversation_id),
            hanh_dong="tao_don", muc_uy_quyen=quyet.muc, conversation_id=str(conversation_id),
            order_id=str(row["id"]), ma_don=row["ma_don"], tong_tien=tong, nguong_vnd=nguong)
    if trang_thai == "cho_duyet":
        # Đơn chờ duyệt thành THẺ ĐỀ XUẤT trong hội thoại (mục 17) — người
        # duyệt thấy căn cứ ngay cạnh lời khách. Không tạo được thẻ (không
        # có hội thoại, CSDL lỗi) thì lui về chuông "đơn chờ duyệt" cũ: đơn
        # nằm chờ mà không ai được báo là khách tưởng đã đặt xong.
        de_xuat_id = await _de_xuat_duyet_don_cho(
            row, lines, tong, nguong, conversation_id, quyet,
            khach=(str(args["khach_ten"]).strip(), sdt, str(args["khach_dia_chi"]).strip()))
        if de_xuat_id is None:
            from agent.core import thong_bao_noi_bo

            await thong_bao_noi_bo.bao_can_duyet_don(
                row["id"], conversation_id=conversation_id, ma_don=row["ma_don"])

    # --- Chốt 8: đẩy sang ERP (chỉ khi ERP_GHI_DON bật) ---
    # Đặt SAU chốt 7 có chủ ý: hàng phải được giữ trước đã. Đẩy sang ERP
    # rồi mới phát hiện không đủ hàng là tạo một đơn bên ERP phải đi huỷ tay.
    #
    # Chỉ chạy cho đơn đã chốt. Đơn `cho_duyet` chưa phải là đơn — người còn
    # chưa duyệt, đẩy sang ERP là ghi nhận một thứ có thể bị bỏ.
    if trang_thai == "da_chot":
        from agent.erp import day_don as _day_don

        kq_erp = await _day_don.day_don_da_luu(
            row["id"],
            ma_don=row["ma_don"],
            khach_ten=str(args["khach_ten"]).strip(),
            khach_sdt=sdt,
            khach_dia_chi=str(args["khach_dia_chi"]).strip(),
            items=lines,
            ghi_chu=str(args.get("ghi_chu") or ""),
        )
        if kq_erp.ket_cuc == "tu_choi":
            return {
                "tao_duoc": False,
                "ly_do": f"Kho từ chối đơn: {kq_erp.ly_do}. Báo khách là chưa "
                         "lên đơn được và chuyển cho nhân viên.",
                "can_chuyen_nhan_vien": True,
            }
        if kq_erp.ket_cuc == "cho_lai":
            trang_thai = "cho_dong_bo"

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
            "Đơn đang CHỜ NHÂN VIÊN DUYỆT. Báo khách là đã ghi "
            "nhận và sẽ có người gọi xác nhận, KHÔNG nói là đã chốt xong."
        ),
    }


def _khoa_van_tay(*phan) -> str:
    import hashlib

    return hashlib.md5(json.dumps(phan, sort_keys=True, ensure_ascii=False,
                                  default=str).encode("utf-8")).hexdigest()


def _ruiro_tao_don() -> list[str]:
    return [
        "Khách xác nhận đặt đơn là do AI nhận định từ hội thoại — đọc lại tin "
        "khách ngay trên thẻ này trước khi duyệt.",
        "Tồn kho và giá có thể đổi trước lúc duyệt — hệ thống kiểm lại lúc thi "
        "hành và KHÔNG thi hành nếu tổng tiền khác.",
    ]


def _nguon_tao_don(lines: list[dict]) -> list[dict]:
    return [
        *({"ten": "Danh mục sản phẩm", "chi_tiet": f"{ln['ten']}: {ln['don_gia']:,}đ".replace(",", ".")}
          for ln in lines),
        {"ten": "Tồn kho đọc sống (bỏ qua bộ đệm)",
         "chi_tiet": "đủ hàng cho " + ", ".join(f"{ln['so_luong']} × {ln['ten']}" for ln in lines)},
        {"ten": "Kiểm địa giới hành chính", "chi_tiet": "không phát hiện mâu thuẫn phường/tỉnh"},
        {"ten": "Thông tin giao hàng", "chi_tiet": "đủ họ tên, số điện thoại hợp lệ, địa chỉ đầy đủ"},
    ]


async def _de_xuat_tao_don(args: dict, lines: list[dict], tong: int, sdt: str,
                           conversation_id, quyet) -> dict:
    """
    Chế độ Gợi ý: mọi điều kiện đã kiểm, nhưng đơn CHƯA ghi và hàng CHƯA giữ.
    Thi hành lúc duyệt chạy lại toàn bộ `_tao_don_hang` từ đầu.
    """
    from agent.core import uy_quyen

    if conversation_id is None:
        return {
            "tao_duoc": False, "can_chuyen_nhan_vien": True,
            "ly_do": f"{quyet.ly_do_che_do}. Không có hội thoại để gửi đề xuất — chuyển nhân viên.",
        }
    ten, dia_chi = str(args["khach_ten"]).strip(), str(args["khach_dia_chi"]).strip()
    tham_so = {
        "items": [{"ten_san_pham": ln["ten"], "so_luong": ln["so_luong"]} for ln in lines],
        "khach_ten": ten, "khach_sdt": sdt, "khach_dia_chi": dia_chi,
        "khach_da_xac_nhan": True, "ghi_chu": str(args.get("ghi_chu") or "")[:500],
        "tong_tien": tong,
    }
    try:
        de_xuat_id, _moi = await uy_quyen.tao_de_xuat(
            conversation_id=conversation_id, quyet=quyet,
            ly_do_can_duyet=quyet.ly_do_duyet(), tham_so=tham_so,
            de_xuat={
                "tieu_de": f"Tạo đơn {tong:,}đ".replace(",", "."),
                "ly_do": "Khách đã xác nhận đặt đơn với các sản phẩm dưới đây.",
                "truoc": None,
                "sau": {"items": lines, "tong_tien": tong, "nguoi_nhan": ten,
                        "sdt": sdt, "dia_chi": dia_chi,
                        "ghi_chu": tham_so["ghi_chu"], "trang_thai": "Đã chốt (sau khi duyệt)"},
            },
            can_cu={"nguon": _nguon_tao_don(lines), "rui_ro": _ruiro_tao_don(), "thieu": []},
            khoa_trung=f"tao_don:{conversation_id}:{_khoa_van_tay(lines, sdt, dia_chi)}",
        )
    except Exception as exc:  # noqa: BLE001 — không tạo được đề xuất: chuyển người, không im
        await db.log_event("ai.de_xuat.loi_tao", ref_id=_uuid_hoac_none(conversation_id),
                           hanh_dong="tao_don", ly_do=f"{type(exc).__name__}: {exc}"[:200])
        return {
            "tao_duoc": False, "can_chuyen_nhan_vien": True,
            "ly_do": "Chưa gửi được đề xuất lên đơn cho nhân viên — đã chuyển người.",
        }
    return {
        "tao_duoc": False,
        "da_de_xuat": True,
        "de_xuat_id": str(de_xuat_id),
        "items": lines,
        "tong_tien": tong,
        "ghi_chu_cho_agent": (
            "Đơn CHƯA được tạo: đã gửi ĐỀ XUẤT lên đơn cho nhân viên duyệt. Báo "
            "khách là đã ghi nhận đủ thông tin và nhân viên sẽ xác nhận đơn. "
            "TUYỆT ĐỐI KHÔNG nói đã lên đơn, đã chốt, hay đọc mã đơn."
        ),
    }


async def _de_xuat_duyet_don_cho(row: dict, lines: list[dict], tong: int, nguong: int,
                                 conversation_id, quyet, *, khach: tuple) -> UUID | None:
    """Thẻ đề xuất cho đơn đã ghi ở `cho_duyet`. None = không tạo được."""
    from agent.core import uy_quyen

    oid = row.get("id")
    if conversation_id is None or not isinstance(oid, UUID):
        return None
    if quyet is None:
        quyet = uy_quyen.QuyetDinh("tao_don", "tu_dong", await uy_quyen.muc_cua("tao_don"))
    ly_do = (quyet.ly_do_duyet() if quyet.muc == "co_phe_duyet" else
             f"Đơn {tong:,}đ từ ngưỡng {nguong:,}đ trở lên phải duyệt".replace(",", "."))
    ten, sdt, dia_chi = khach
    try:
        de_xuat_id, _moi = await uy_quyen.tao_de_xuat(
            conversation_id=conversation_id, quyet=quyet, ly_do_can_duyet=ly_do,
            tham_so={"order_id": str(oid), "ma_don": row.get("ma_don"), "tong_tien": tong},
            de_xuat={
                "tieu_de": f"Duyệt đơn {row.get('ma_don')} — {tong:,}đ".replace(",", "."),
                "ly_do": "Khách đã xác nhận đặt đơn; đơn đã ghi và đã giữ hàng, chờ duyệt.",
                "truoc": {"trang_thai": "Chờ duyệt"},
                "sau": {"trang_thai": "Đã chốt (đẩy sang ERP nếu bật)", "items": lines,
                        "tong_tien": tong, "nguoi_nhan": ten, "sdt": sdt, "dia_chi": dia_chi},
            },
            can_cu={"nguon": _nguon_tao_don(lines),
                    "rui_ro": _ruiro_tao_don()[:1]
                    + ["Hàng đã được giữ cho đơn này. Từ chối = huỷ đơn chờ duyệt và trả hàng về kho."],
                    "thieu": []},
            khoa_trung=f"tao_don:don:{oid}", order_id=oid,
        )
        return de_xuat_id
    except Exception as exc:  # noqa: BLE001
        await db.log_event("ai.de_xuat.loi_tao", ref_id=_uuid_hoac_none(conversation_id),
                           hanh_dong="tao_don", ly_do=f"{type(exc).__name__}: {exc}"[:200])
        return None


# Lời lẽ cho từng trạng thái giao hàng. Đặt ở đây, MỘT chỗ, để agent không
# tự nghĩ ra cách diễn đạt khác nhau mỗi lượt — và để người vận hành sửa
# được câu chữ mà không phải đụng vào prompt.
# Khoá khớp `models.InternalShippingStatus` — đó là bộ trạng thái nội bộ duy
# nhất. Hai bộ tên cho cùng một thứ là hai nguồn sự thật, và sớm muộn chúng
# lệch nhau.
_LOI_TRANG_THAI_GIAO = {
    "ready_to_pick": "Đơn đã có mã vận đơn và đang chờ đơn vị vận chuyển đến lấy hàng tại kho.",
    "delivering": "Đơn đã bàn giao đơn vị vận chuyển và đang trên đường giao.",
    "delivered": "Đơn đã giao thành công.",
    "delivery_failed": "Đơn giao không thành công — cần người kiểm tra lại.",
    "returning": "Đơn đang được hãng vận chuyển hoàn về kho.",
    "returned": "Đơn đã được hãng vận chuyển hoàn về kho, đang chờ nhân viên kiểm tra hàng hoàn.",
    "cancelled": "Vận đơn của đơn hàng này đã bị huỷ trên hãng vận chuyển.",
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
                "can_chuyen_nhan_vien": True,
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


async def _danh_dau_xin_huy(
    ma_don: str, conversation_id, ly_do: str
) -> UUID | bool | None:
    """
    Gắn cờ xin huỷ lên đơn. Trả id đơn nếu có đúng một dòng được sửa.

    KHÔNG đụng tới `trang_thai`: huỷ là việc của người, và trộn hai thứ vào
    một câu SQL là sớm muộn có người sửa nhầm thành huỷ thật.

    Chặn theo `conversation_id` vì mã đơn đoán được — không chặn thì bất kỳ
    ai cũng gắn cờ lên đơn của người lạ, tức phá hoại được từ xa.

    Loại đơn `da_huy` để không dựng lại cờ trên đơn đã đóng, và đơn
    `da_giao`: hàng đã ở nhà khách thì "huỷ" là ĐỔI TRẢ. Cờ xin huỷ trên đơn
    đã giao làm người xử lý bấm Huỷ — cộng kho món đang nằm ở nhà khách.
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
           AND trang_thai <> 'da_giao'
        RETURNING id, ma_don
        """,
        ma_don, conversation_id, (ly_do or "")[:500],
    )
    # Mock cũ trong unit test trả dict tối giản không có `id` (chỉ có `ma_don`).
    # Trả `True` để không gãy `KeyError`, còn dòng 1558 chỉ nối Pending Action
    # khi kết quả là UUID thật từ PostgreSQL.
    return (row.get("id") or True) if row is not None else False


_NHAN_TRANG_THAI_DON = {
    "cho_duyet": "Chờ duyệt", "da_chot": "Đã chốt", "cho_dong_bo": "Chờ đồng bộ kho",
    "da_giao": "Đã giao", "da_huy": "Đã huỷ",
}


async def bang_chung_huy_don(order_id: UUID, ly_do: str = "") -> dict:
    """
    Căn cứ cho đề xuất huỷ: đọc từ SỔ CỦA CỬA HÀNG, không từ lời model.
    Trả {truoc, sau, nguon, rui_ro, thieu, ma_don, huy_duoc}.

    Thống nhất hoàn toàn với chốt chặn ở `thao_tac_don.huy_don` (BUG-17-04):
    không đánh dấu `huy_duoc=True` hay dự kiến `sau.tra_kho` khi đơn đang đối
    soát vận đơn, đang có vận đơn hoạt động, hoặc cần kiểm kho thủ công.
    """
    don = await db.fetchrow(
        "SELECT ma_don, trang_thai, tong_tien, items, trang_thai_giao_hang, "
        "ma_van_don, don_vi_van_chuyen, van_don_da_lay_hang, "
        "erp_ma_don, so_tien_da_thu, conversation_id "
        "FROM orders WHERE id = $1", order_id)
    if don is None:
        return {"huy_duoc": False, "thieu": ["Không còn thấy đơn trong sổ"]}
    yc_vd = await db.fetchrow(
        "SELECT trang_thai, ma_van_don FROM shipping_waybill_requests WHERE order_id = $1",
        order_id,
    )
    items = don.get("items") or []
    if isinstance(items, str):
        items = json.loads(items)
    tt = str(don["trang_thai"] or "")
    tt_yc = str((yc_vd or {}).get("trang_thai") or "")
    ma_vd = str(don.get("ma_van_don") or (yc_vd or {}).get("ma_van_don") or "").strip()
    tt_giao = str(don.get("trang_thai_giao_hang") or "").strip()
    da_lay = don.get("van_don_da_lay_hang")

    rui_ro, thieu = [], []
    if don.get("erp_ma_don"):
        rui_ro.append(f"Đơn đã có bên ERP ({don['erp_ma_don']}) — huỷ ở đây KHÔNG huỷ bên ERP, cần huỷ tay.")
    elif tt == "cho_dong_bo":
        rui_ro.append("Đơn đang chờ đồng bộ — có thể đã tới ERP; tra ERP theo mã đơn.")
    if int(don.get("so_tien_da_thu") or 0) > 0:
        rui_ro.append(f"Khách đã trả trước {int(don['so_tien_da_thu']):,}đ — cần hoàn tiền "
                      "(AI không hoàn tiền).".replace(",", "."))
    if not ly_do:
        thieu.append("Khách chưa nêu lý do huỷ")

    huy_duoc = tt not in ("da_giao", "da_huy")
    if not huy_duoc:
        thieu.append(f"Đơn đang «{_NHAN_TRANG_THAI_DON.get(tt, tt)}» — không huỷ được")

    if tt_yc in ("sending", "unknown_timeout", "reconciling", "manual_required"):
        huy_duoc = False
        thieu.append(f"Đơn đang đối soát tạo vận đơn ({tt_yc}) — phải hoàn tất đối soát trước khi huỷ.")

    if ma_vd:
        hang = don.get("don_vi_van_chuyen") or "hãng vận chuyển"
        if tt_giao == "delivered":
            huy_duoc = False
            thieu.append(f"Vận đơn {ma_vd} ({hang}) đã giao thành công — không huỷ được, xử lý như đổi trả.")
        elif tt_giao == "ready_to_pick":
            huy_duoc = False
            rui_ro.append(f"Đã có vận đơn {ma_vd} ({hang}) đang chờ lấy hàng — cần huỷ vận đơn trên cổng hãng trước.")
            thieu.append(f"Chưa thể huỷ đơn nội bộ khi vận đơn {ma_vd} chưa được hãng xác nhận huỷ.")
        elif tt_giao in ("delivering", "delivery_failed", "returning"):
            huy_duoc = False
            nhan_giao = {
                "delivering": "đang giao hàng",
                "delivery_failed": "giao thất bại",
                "returning": "đang hoàn hàng về kho",
            }[tt_giao]
            rui_ro.append(f"Vận đơn {ma_vd} ({hang}) đang ở trạng thái {nhan_giao} — hàng đã rời kho.")
            thieu.append(f"Không huỷ trực tiếp khi vận đơn {ma_vd} đang {nhan_giao}; liên hệ hãng hoàn hàng về kho.")
        elif tt_giao not in ("cancelled", "returned"):
            huy_duoc = False
            thieu.append(f"Vận đơn {ma_vd} chưa rõ trạng thái lấy hàng/hoàn hàng — chặn huỷ tự động để tránh lệch tồn kho.")
        elif tt_giao == "returned":
            rui_ro.append(f"Vận đơn {ma_vd} đã hoàn về kho — hệ thống KHÔNG tự động cộng tồn kho; nhân viên kiểm tra hàng hoàn rồi nhập qua Kho → Nhập.")
        elif tt_giao == "cancelled" and da_lay is not False:
            rui_ro.append(f"Vận đơn {ma_vd} đã huỷ nhưng chưa đủ bằng chứng hàng chưa rời kho — KHÔNG tự động cộng tồn kho, cần kiểm kho thực tế.")

    se_tra_kho = huy_duoc and (
        not ma_vd or (tt_giao == "cancelled" and da_lay is False)
    )
    tra_kho_du_kien = (
        [f"{it.get('so_luong')} × {it.get('ten')}" for it in items if isinstance(it, dict)]
        if se_tra_kho else []
    )
    return {
        "ma_don": don["ma_don"], "huy_duoc": huy_duoc,
        "truoc": {"trang_thai": _NHAN_TRANG_THAI_DON.get(tt, tt),
                  "trang_thai_giao_hang": tt_giao or None,
                  "tong_tien": int(don.get("tong_tien") or 0), "items": items},
        "sau": {"trang_thai": "Đã huỷ" if huy_duoc else _NHAN_TRANG_THAI_DON.get(tt, tt),
                "tra_kho": tra_kho_du_kien},
        "nguon": [{"ten": "Sổ đơn của cửa hàng",
                   "chi_tiet": f"đơn {don['ma_don']} thuộc đúng hội thoại này, trạng thái "
                               f"«{_NHAN_TRANG_THAI_DON.get(tt, tt)}»"}],
        "rui_ro": rui_ro, "thieu": thieu,
    }


async def _huy_don_theo_uy_quyen(order_id: UUID, ma: str, ly_do: str,
                                 conversation_id, quyet) -> dict | None:
    """Đề xuất huỷ (cần duyệt) hoặc huỷ thật (Tự động). None = rơi về chuyển người."""
    from agent.core import thao_tac_don, uy_quyen

    try:
        bc = await bang_chung_huy_don(order_id, ly_do)
        if not bc.get("huy_duoc"):
            return None
        if quyet.can_duyet:
            de_xuat_id, _moi = await uy_quyen.tao_de_xuat(
                conversation_id=conversation_id, quyet=quyet,
                ly_do_can_duyet=quyet.ly_do_duyet(),
                tham_so={"order_id": str(order_id), "ma_don": bc["ma_don"]},
                de_xuat={"tieu_de": f"Huỷ đơn {bc['ma_don']}",
                         "ly_do": f"Khách xin huỷ: {ly_do}" if ly_do else "Khách xin huỷ đơn.",
                         "truoc": bc["truoc"], "sau": bc["sau"]},
                can_cu={"nguon": bc["nguon"], "rui_ro": bc["rui_ro"], "thieu": bc["thieu"]},
                khoa_trung=f"huy_don:{order_id}", order_id=order_id,
            )
            return {
                "da_ghi_nhan": True, "da_huy": False, "da_de_xuat": True,
                "de_xuat_id": str(de_xuat_id), "can_chuyen_nhan_vien": False,
                "ghi_chu": (
                    "Đã ghi nhận yêu cầu huỷ lên đơn và gửi ĐỀ XUẤT HUỶ cho nhân viên "
                    "có thẩm quyền duyệt. TUYỆT ĐỐI KHÔNG nói với khách là đơn 'đã huỷ' "
                    "— đơn CHƯA huỷ. Nói đúng: đã ghi nhận, nhân viên sẽ xác nhận việc "
                    "huỷ và báo lại sớm."
                ),
            }
        # Tự động: thi hành ngay, cùng luật với nút Huỷ của người.
        kq = await thao_tac_don.huy_don(order_id, actor="agent", conversation_id=conversation_id)
    except thao_tac_don.LoiThaoTacDon as exc:
        await db.log_event("ai.hanh_dong.loi", actor="agent",
                           ref_id=_uuid_hoac_none(conversation_id),
                           hanh_dong="huy_don", ly_do=exc.thong_diep[:300])
        return None
    except Exception as exc:  # noqa: BLE001 — không làm được: chuyển người, không im
        await db.log_event("ai.de_xuat.loi_tao", ref_id=_uuid_hoac_none(conversation_id),
                           hanh_dong="huy_don", ly_do=f"{type(exc).__name__}: {exc}"[:200])
        return None
    if kq.get("da_huy_tu_truoc"):
        return None
    await db.log_event("ai.hanh_dong.tu_dong", actor="agent",
                       ref_id=_uuid_hoac_none(conversation_id), hanh_dong="huy_don",
                       muc_uy_quyen=quyet.muc, conversation_id=str(conversation_id),
                       order_id=str(order_id), ma_don=ma, ket_qua=kq)
    con_viec_tay = [x for x in (kq.get("can_huy_tay"), kq.get("can_hoan_tien")) if x]
    return {
        "da_ghi_nhan": True, "da_huy": True,
        # Còn phần phải làm tay (ERP, hãng, hoàn tiền) thì vẫn cần người.
        "can_chuyen_nhan_vien": bool(con_viec_tay),
        "ghi_chu": (
            f"Đơn {ma} ĐÃ HUỶ và hàng đã trả về kho. Báo khách đúng như vậy."
            + (" Phần còn lại cần nhân viên làm tay: " + " ".join(con_viec_tay)
               + " — KHÔNG hứa hoàn tiền thay nhân viên." if con_viec_tay else "")
        ),
    }


async def _xin_huy_don(args: dict, conversation_id, quyet=None) -> dict:
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
        order_id = await _danh_dau_xin_huy(ma, conversation_id, ly_do)
        da_ghi = bool(order_id)
        if da_ghi:
            await db.log_event(
                "order.xin_huy", actor="agent", ma_don=ma, ly_do=ly_do[:200],
            )
            # ỦY QUYỀN (mục 17): mức "Có phê duyệt" (mặc định) hoặc chế độ
            # Gợi ý -> thẻ đề xuất huỷ; "Tự động" -> huỷ thật khi đủ điều kiện.
            # Không làm được (mock trả bool, CSDL lỗi, đơn không huỷ được)
            # thì rơi xuống đường cũ: việc xử lý đơn + chuyển người.
            if isinstance(order_id, UUID) and quyet is not None and not quyet.bi_cam:
                kq_uq = await _huy_don_theo_uy_quyen(order_id, ma, ly_do, conversation_id, quyet)
                if kq_uq is not None:
                    return kq_uq
            # Mock cũ trong unit test trả bool; production trả UUID. Chỉ dữ
            # liệu thật mới được dùng để liên kết Pending Action với đơn.
            if isinstance(order_id, UUID):
                await cong_viec.tao_tu_yeu_cau_xu_ly_don(
                    order_id=order_id,
                    conversation_id=conversation_id,
                    loai="huy",
                    tieu_de=f"Xử lý yêu cầu hủy đơn {ma}",
                    mo_ta=ly_do,
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
            "KHÔNG ghi nhận được yêu cầu huỷ cho đơn này trong hội thoại "
            "(không thấy đơn, hoặc đơn đã đóng). Không nói đơn 'đã huỷ' và "
            "không đọc thông tin đơn nào ra. Nếu khách nói đã NHẬN hàng thì "
            "đó là đổi/trả, dùng xin_doi_tra. Còn lại xin lỗi khách, hỏi lại "
            "mã đơn hoặc số điện thoại đã đặt, và cho biết nhân viên sẽ "
            "kiểm tra giúp."
        )

    return {
        "da_ghi_nhan": da_ghi,
        "da_huy": False,
        "can_chuyen_nhan_vien": True,
        "ghi_chu": ghi_chu,
    }


async def _danh_dau_xin_doi_tra(
    ma_don: str, conversation_id, loai: str, ly_do: str
) -> bool:
    """
    Gắn cờ xin đổi/trả lên đơn. Trả True nếu có đúng một dòng được sửa.

    Cùng khuôn `_danh_dau_xin_huy`, và cùng lý do cho từng ràng buộc:

    - KHÔNG đụng `trang_thai`: duyệt đổi trả là việc của người.
    - Chặn theo `conversation_id`: mã đơn đoán được, không chặn thì ai cũng
      gắn cờ lên đơn của người lạ — phá hoại được từ xa.
    - Loại đơn `da_huy`: đơn đã đóng thì không dựng cờ mới lên.

    KHÔNG dùng `COALESCE` để giữ mốc thời gian đầu tiên như bên xin huỷ.
    Khách đổi ý từ "đổi" sang "trả" là chuyện thường, và người xử lý cần
    thấy yêu cầu MỚI NHẤT, không phải yêu cầu đầu tiên.
    """
    row = await db.fetchrow(
        """
        UPDATE orders
           SET yeu_cau_doi_tra_luc   = now(),
               yeu_cau_doi_tra_loai  = $3,
               yeu_cau_doi_tra_ly_do = $4,
               updated_at            = now()
         WHERE ma_don = $1
           AND conversation_id = $2
           AND trang_thai <> 'da_huy'
        RETURNING ma_don
        """,
        ma_don, conversation_id, loai, (ly_do or "")[:500],
    )
    return row is not None


async def _xin_doi_tra(args: dict, conversation_id) -> dict:
    """
    Ghi nhận yêu cầu đổi/trả rồi chuyển người — không bao giờ tự duyệt.

    VÌ SAO CẦN, KHI ĐÃ CÓ `chuyen_nhan_vien`
    ----------------------------------------
    Chuyển hội thoại là chưa đủ, đúng như với xin huỷ. Yêu cầu khi đó chỉ
    nằm trong đoạn chat và trong một dòng lý do văn xuôi — không đếm được,
    không truy được, không hiện lên màn hình Đơn hàng.

    Với đổi trả thì hậu quả còn cụ thể hơn: chính sách có hạn số ngày. Yêu
    cầu nằm im ba hôm trong hộp thư rồi mới có người đọc là khách hết hạn
    đổi trả vì lý do không phải của họ.

    VẪN CHUYỂN NGƯỜI KỂ CẢ KHI KHÔNG GẮN ĐƯỢC CỜ
    ---------------------------------------------
    Không tra được đơn thì khách vẫn đang muốn đổi trả một cái gì đó. Im
    lặng bỏ qua là bỏ rơi khách ở đúng lúc họ đã không hài lòng sẵn.
    """
    ma = str(args.get("ma_don", "") or "").strip()
    loai = str(args.get("loai", "") or "").strip().lower()
    ly_do = str(args.get("ly_do", "") or "").strip()

    # Giá trị lạ thì HỎI LẠI, không tự đoán. Đoán sai giữa đổi và trả là
    # gửi người xử lý đi làm nhầm việc — bên cần kiểm tồn kho, bên cần
    # duyệt hoàn tiền.
    if loai not in ("doi", "tra"):
        return {
            "da_ghi_nhan": False,
            "can_chuyen_nhan_vien": False,
            "ghi_chu": (
                "Chưa rõ khách muốn ĐỔI sang mẫu khác hay TRẢ lại lấy tiền. "
                "Hỏi khách cho rõ rồi gọi lại công cụ này, đừng tự chọn."
            ),
        }

    da_ghi = False
    if ma and conversation_id is not None:
        da_ghi = await _danh_dau_xin_doi_tra(ma, conversation_id, loai, ly_do)
        if da_ghi:
            await db.log_event(
                "order.xin_doi_tra", actor="agent", ma_don=ma,
                loai=loai, ly_do=ly_do[:200],
            )

    if da_ghi:
        viec = "đổi sang mẫu khác" if loai == "doi" else "trả lại hàng"
        ghi_chu = (
            f"Đã ghi nhận yêu cầu {viec} lên đơn và chuyển nhân viên. "
            "TUYỆT ĐỐI KHÔNG nói với khách là 'đã được đổi', 'đã hoàn tiền' "
            "hay 'đơn đủ điều kiện' — chưa ai duyệt cả. Nói đúng: đã ghi "
            "nhận, đã chuyển bộ phận xử lý, nhân viên sẽ liên hệ lại sớm. "
            "Được phép nói lại CHÍNH SÁCH đổi trả nếu khách hỏi, nhưng "
            "không được kết luận đơn này có thuộc diện đó hay không."
        )
    else:
        ghi_chu = (
            "KHÔNG tìm thấy đơn này trong hội thoại. Không đọc thông tin đơn "
            "nào ra và không hứa gì về đổi trả. Xin lỗi khách, hỏi lại mã "
            "đơn hoặc số điện thoại đã đặt, và cho biết nhân viên sẽ kiểm "
            "tra giúp."
        )

    return {
        "da_ghi_nhan": da_ghi,
        "da_duyet": False,
        "loai": loai,
        "can_chuyen_nhan_vien": True,
        "ghi_chu": ghi_chu,
    }


async def _tra_cuu_van_chuyen(args: dict, conversation_id=None) -> dict:
    """
    Tình trạng giao hàng của một đơn, đọc từ SỔ CỦA CỬA HÀNG.

    VÌ SAO KHÔNG GỌI THẲNG API HÃNG Ở ĐÂY
    -------------------------------------
    Lời gọi mạng nằm trong đường trả lời khách là thêm một chỗ để treo: hãng
    chậm 20 giây thì khách chờ 20 giây, và nếu hãng chết thì agent im luôn.
    Webhook của hãng cập nhật `orders.trang_thai_giao_hang`; tool này chỉ đọc.

    Đổi lại, số liệu có thể trễ vài phút — và đó là đánh đổi đúng: trả lời
    chậm vài phút tốt hơn không trả lời.

    CHỈ ĐƠN CỦA HỘI THOẠI NÀY
    --------------------------
    Bản trước tra theo mã đơn mà không lọc hội thoại: người lạ đoán mã đơn
    là đọc được mã vận đơn của khách khác — và mã vận đơn tra trên trang
    hãng ra tên, số điện thoại, địa chỉ người nhận (rà soát 11.2026). Cùng
    khuôn `_tra_cuu_don_hang`: mã của hội thoại khác, mã không tồn tại, hay
    thiếu hội thoại đều nhận CÙNG một câu — khác câu là để lộ mã nào có thật.
    """
    ma = str(args.get("ma_don", "")).strip()
    if not ma:
        return {"tim_thay": False, "ghi_chu": "Chưa có mã đơn để tra."}
    can_xac_minh = {
        "tim_thay": False,
        "can_xac_minh": True,
        "ghi_chu": (
            "Không tra được đơn này trong hội thoại đang nói chuyện. TUYỆT "
            "ĐỐI không đọc thông tin vận chuyển nào ra. Xin lỗi khách, nói "
            "cần xác minh và hỏi số điện thoại đã đặt đơn, rồi gọi "
            "chuyen_nhan_vien để người thật kiểm tra."
        ),
        # Cùng lý do với `_tra_cuu_don_hang`: dặn là dặn, model thì trượt —
        # cờ buộc chuyển người bằng mã.
        "can_chuyen_nhan_vien": True,
    }
    if conversation_id is None:
        return can_xac_minh
    try:
        row = await db.fetchrow(
            "SELECT ma_don, trang_thai, trang_thai_giao_hang, ma_van_don, "
            "       don_vi_van_chuyen, ngay_du_kien_giao, "
            "       cap_nhat_van_chuyen_luc "
            "FROM orders WHERE upper(ma_don) = upper($1) AND conversation_id = $2",
            ma, conversation_id,
        )
    except Exception:  # noqa: BLE001 — CSDL chết thì agent vẫn phải nói được gì đó
        return {
            "tim_thay": False,
            "ghi_chu": "Chưa tra được lúc này. Cần chuyển người hỗ trợ.",
            "can_chuyen_nhan_vien": True,
        }
    if row is None:
        return can_xac_minh

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
