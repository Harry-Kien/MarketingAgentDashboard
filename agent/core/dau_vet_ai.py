"""
Dấu vết AI của MỘT tin nhắn — trả lời được câu "vì sao AI nói câu này?".

Ghi vào `messages.dau_vet_ai` (migration 0053) ở cả hai đường: tin AI tự
gửi và bản nháp chờ duyệt. Dashboard vẽ nó thành nút "Vì sao?" dưới tin.

VÌ SAO CẦN
----------
Phòng thử có dấu vết đầy đủ, khách thật thì không. Khi khách khiếu nại "AI
bảo tôi dùng được khi mang thai", câu hỏi đầu tiên là: hồ sơ agent nào,
ngưỡng bao nhiêu, đã tra tài liệu phiên bản nào, lưới nào im lặng. Trước bản
này không câu nào trả lời được từ dữ liệu — chỉ đoán.

HAI RÀNG BUỘC, CẢ HAI CANH BẰNG TEST
-----------------------------------
1. KHÔNG thêm dữ liệu cá nhân thô. Tham số công cụ trong `Reply.cong_cu` là
   bản đã MỞ che (số điện thoại thật để lên đơn), không phải bản model thấy.
   Ở đây che LẠI bằng một `MatNa` mới — luôn che, bất kể công tắc
   `CHE_DU_LIEU_GUI_MODEL` — rồi ẩn hẳn các trường mang danh tính theo tên
   khoá (họ tên, địa chỉ: `MatNa` cố ý không che địa chỉ vì không có khuôn).
   Dấu vết sống lâu và được đọc bởi nhiều người hơn câu trả lời; nó không
   được là một bản sao thứ hai của hồ sơ khách.
2. KÍCH THƯỚC CÓ TRẦN. `tim_kien_thuc` trả tám đoạn tài liệu, `goi_y_san_pham`
   trả cả danh mục; ghi nguyên vào mỗi tin là mỗi tin vài chục KB nhân với
   mọi tin AI từng gửi. Trần nằm ở `TRAN_BYTE`, và vượt trần thì bỏ dần phần
   ít quan trọng nhất (kết quả công cụ, rồi tham số) chứ không cắt JSON giữa
   chừng — dấu vết hỏng cú pháp là dấu vết không đọc được.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from agent.core import che_du_lieu

PHIEN_BAN = 1
TRAN_BYTE = 12_000
_TOI_DA_CONG_CU = 8
_TOI_DA_TRI_THUC = 10
_CAT_CHUOI = 300

# Trường mang DANH TÍNH, ẩn theo tên khoá. Danh sách đóng, không đoán: thêm
# khoá mơ hồ ("ten") là ẩn luôn tên sản phẩm — dấu vết mất đúng thứ cần đọc.
_KHOA_DANH_TINH = frozenset({
    "khach_ten", "khach_sdt", "khach_dia_chi", "khach_email",
    "ten_khach", "ho_ten", "dia_chi", "sdt", "so_dien_thoai", "email",
    "cccd", "nguoi_nhan", "ten_nguoi_nhan",
})
AN = "[đã ẩn]"


def _cat(x: Any, mat_na: che_du_lieu.MatNa) -> Any:
    """Che + ẩn danh tính + cắt ngắn, đệ quy. Nói RÕ chỗ đã cắt."""
    if isinstance(x, str):
        s = mat_na.che(x)
        return s if len(s) <= _CAT_CHUOI else s[:_CAT_CHUOI] + "…"
    if isinstance(x, dict):
        return {str(k): (AN if str(k).lower() in _KHOA_DANH_TINH and v not in (None, "")
                         else _cat(v, mat_na))
                for k, v in list(x.items())[:30]}
    if isinstance(x, (list, tuple)):
        ra = [_cat(v, mat_na) for v in list(x)[:10]]
        if len(x) > 10:
            ra.append(f"… ({len(x) - 10} mục nữa)")
        return ra
    if isinstance(x, (int, float, bool)) or x is None:
        return x
    return _cat(str(x), mat_na)


def _nhan_luoi(ma: str | None) -> tuple[str, bool]:
    """(nhãn cho người đọc, có phải LỚP LƯỚI không). Import muộn: tránh vòng."""
    if not ma:
        return "", False
    from agent.core.agent import LOP_LUOI, MA_CHUYEN_KHAC

    if ma in LOP_LUOI:
        return LOP_LUOI[ma], True
    return MA_CHUYEN_KHAC.get(ma, ma), False


# ══ PHÂN LOẠI CĂN CỨ CỦA MỘT BẢN NHÁP (phiếu việc mục 16) ══════════════
#
# Bốn trạng thái, tính TỪ KẾT QUẢ TRA CỨU THẬT của lượt (đoạn tài liệu lấy
# được, kết quả công cụ) — KHÔNG từ lời tự đánh giá của model, và KHÔNG hiện
# phần trăm: "87%" đọc như xác suất câu trả lời đúng, mà nó chỉ là điểm khớp.
#
#   mau_thuan  hai nguồn nói khác nhau về cùng một thứ — KHÔNG chọn giùm,
#              người trực phải kiểm. Đứng đầu: thấy mâu thuẫn mà vẫn gắn "đủ
#              căn cứ" là xanh giả nguy hiểm nhất.
#   khong_co   không tài liệu, không dữ liệu hệ thống nào — không được khẳng
#              định nghiệp vụ; chỉ gợi ý một câu chờ trung lập, ghi rõ là thế.
#   chua_du    có căn cứ nhưng hở chỗ nào thì nói chỗ ấy.
#   du         còn lại.
#
# Chặn trả lời thiếu căn cứ KHÔNG nằm ở đây: lưới ③ `tin_cay_thap` trong
# agent.py chuyển người khi căn cứ yếu, và tin bị chuyển người không bao giờ
# tự gửi. Đây là NHÃN cho người duyệt — để họ không phải mở "Xem căn cứ" mới
# biết bản nháp đứng trên cái gì.
TRANG_THAI_CAN_CU = {
    "du": "Đủ căn cứ",
    "chua_du": "Căn cứ chưa đầy đủ",
    "khong_co": "Không có căn cứ",
    "mau_thuan": "Nguồn mâu thuẫn",
    "khong_can": "Không yêu cầu căn cứ",
}
CAU_CHO_TRUNG_LAP = (
    "Dạ em đã nhận được câu hỏi của anh/chị. Em kiểm tra lại thông tin chính "
    "xác rồi phản hồi mình ngay ạ."
)
# Công cụ TRA CỨU: tra hụt là căn cứ hở. Công cụ ghi/chuyển người không tính.
_CONG_CU_TRA = frozenset({
    "tim_kien_thuc", "tra_cuu_san_pham", "goi_y_san_pham",
    "tra_cuu_don_hang", "tra_cuu_van_chuyen",
})
_NHAN_CONG_CU = {
    "tim_kien_thuc": "tài liệu cửa hàng", "tra_cuu_san_pham": "sản phẩm",
    "goi_y_san_pham": "gợi ý sản phẩm", "tra_cuu_don_hang": "đơn hàng",
    "tra_cuu_van_chuyen": "vận chuyển",
}
_KHOA_SO_SANH = ("gia", "con_hang", "ton_kho", "trang_thai", "tong_tien")
_SO_TIEN = re.compile(
    r"(\d{1,3}(?:[.,]\d{3})+|\d{4,})\s*(?:đ|₫|vnđ|vnd|đồng|k\b|nghìn|ngàn)", re.IGNORECASE)
_SO_THOI_HAN = re.compile(
    r"\b(\d+)\s*(ngày|tháng|tuần|giờ|năm|%)\b", re.IGNORECASE)
_DON_VI_KHANG_DINH = re.compile(
    r"\b\d+\s*(?:ngày|tháng|tuần|giờ|năm|%|đ|₫|vnđ|vnd|đồng|k|nghìn|ngàn|ml|mg|kg|g|hộp|chai|lọ|cái|chiếc)\b",
    re.IGNORECASE,
)

# Cụm giao tiếp / làm rõ / chào hỏi không phải khẳng định nghiệp vụ.
_CUM_GIAO_TIEP = (
    "em chua ro y",
    "chua ro y",
    "noi them giup",
    "noi ro hon giup",
    "chia se them giup",
    "cho em hoi them",
    "cho em xin them thong tin",
    "cho em xin ma don",
    "cho em xin so dien thoai",
    "anh chi can ho tro gi",
    "anh/chi can ho tro gi",
    "anh chi dang quan tam",
    "ban can ho tro gi",
    "can tim san pham nao",
    "vui long cung cap",
    "xin chao",
    "chao anh",
    "chao chi",
    "chao ban",
    "chao quy khach",
    "em chao",
    "shop chao",
    "cam on",
    "rat vui duoc ho tro",
    "hen gap lai",
    "chuc anh",
    "chuc chi",
    "chuc ban",
    "em da nhan duoc cau hoi",
    "em kiem tra lai thong tin",
)
_TU_NGHIEP_VU_KHANG_DINH = (
    "chinh sach", "bao hanh", "doi tra", "hoan tien", "ton kho",
    "con hang", "het hang", "phi ship", "mien phi", "giao hang",
    "thanh phan", "cong dung", "cach dung", "huong dan su dung",
    "duoc doi", "khong duoc", "ma don", "trang thai don", "tong tien",
    "dang giao", "da giao", "da huy", "gia ban", "khuyen mai",
    "giam gia", "chi nhanh", "dia chi",
)
_TU_CHAO_HOI_DON_THUAN = frozenset({
    "xin", "chao", "hi", "hello", "hey", "alo", "cam", "on", "thanks", "thank",
    "ok", "oke", "okay", "vang", "da", "a", "em", "anh", "chi", "ban", "shop",
    "ad", "admin", "nha", "nhe", "hen", "gap", "lai", "chuc", "ngu", "ngon",
    "buoi", "sang", "trua", "chieu", "toi",
})
_TU_DEM_CAN_CU = frozenset({
    "da", "vang", "a", "nha", "nhe", "em", "anh", "chi", "ban", "shop", "ben",
    "minh", "khach", "hang", "quy", "vui", "long", "giup", "xin", "chao", "cam",
    "on", "duoc", "co", "khong", "chua", "ro", "y", "noi", "them", "bi", "gio",
    "se", "la", "cua", "cho", "voi", "va", "hoac", "thi", "ma", "nhung", "de",
    "trong", "ngoai", "tren", "duoi", "khi", "neu", "theo", "ve", "tu", "den",
    "sau", "truoc", "lai", "nua", "nhieu", "it", "tot", "lam", "rat", "hoi",
    "thong", "tin", "ho", "tro", "van", "kiem", "tra", "nhat", "hien", "tai", "nay", "kia", "ay", "do", "day", "the", "nao", "sao",
    "vi", "nen", "cung", "qua", "moi", "cu", "dang", "phai", "can", "muon", "biet", "xem", "gui", "nhan", "san", "pham",
})


def _fold_vi(chuoi: str) -> str:
    """Bỏ dấu tiếng Việt và chuẩn hoá khoảng trắng để so khớp deterministic."""
    s = unicodedata.normalize("NFD", str(chuoi or "").lower().replace("đ", "d").replace("Đ", "d"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def _trich_tu_khoa_nghia(chuoi: str) -> list[str]:
    """Tách các từ nội dung (bỏ từ đệm giao tiếp) theo thứ tự xuất hiện."""
    folded = _fold_vi(chuoi)
    tokens = re.findall(r"[a-z0-9]{2,}", folded)
    return [t for t in tokens if t not in _TU_DEM_CAN_CU]


_TU_MO_DAU_GIAO_TIEP = frozenset({"chao", "hi", "hello", "hey", "cam", "thanks", "thank", "hen", "chuc"})


def la_cau_giao_tiep(van_ban: str) -> bool:
    """
    Trả True khi câu trả lời thuần giao tiếp / chào hỏi / làm rõ ý khách,
    không đưa ra khẳng định nghiệp vụ về giá, đơn hàng, chính sách hay công dụng.
    """
    raw = str(van_ban or "").strip()
    if not raw:
        return False
    if _SO_TIEN.search(raw) or _DON_VI_KHANG_DINH.search(raw):
        return False
    folded = _fold_vi(raw)
    if any(k in folded for k in _TU_NGHIEP_VU_KHANG_DINH):
        return False
    if any(c in folded for c in _CUM_GIAO_TIEP):
        return True
    tokens = re.findall(r"[a-z0-9]+", folded)
    return (
        bool(tokens)
        and len(tokens) <= 10
        and any(t in _TU_MO_DAU_GIAO_TIEP for t in tokens)
        and all(t in _TU_CHAO_HOI_DON_THUAN for t in tokens)
    )


def la_cau_hoi_nghiep_vu(cau_hoi: str) -> bool:
    """
    Trả True khi câu hỏi khách KHÔNG chỉ là chào hỏi/cảm ơn đơn thuần mà là
    câu hỏi sản phẩm, giá, đơn hàng, vận chuyển hoặc chính sách.
    """
    raw = str(cau_hoi or "").strip()
    if not raw:
        return False
    folded = _fold_vi(raw)
    tokens = re.findall(r"[a-z0-9]+", folded)
    if not tokens:
        return False
    if all(t in _TU_CHAO_HOI_DON_THUAN for t in tokens):
        return False
    return True


def can_cu_ho_tro_cau_tra_loi(
    van_ban: str,
    tri_thuc: list[dict],
    cong_cu: list[dict],
    *,
    co_du_lieu: bool = False,
) -> tuple[bool, list[str]]:
    """
    Kiểm tra xem `tri_thuc` / dữ liệu công cụ có THỰC SỰ hỗ trợ nội dung
    trong `van_ban` hay không — tránh gắn `Đủ căn cứ` chỉ vì `bool(passages)`.
    """
    du_lieu_that = co_du_lieu or any(
        c.get("ten") != "tim_kien_thuc" and _co_du_lieu(c.get("ket_qua"))
        for c in cong_cu
    )
    if du_lieu_that:
        return True, []
    if not tri_thuc:
        return False, ["Không có đoạn tài liệu hoặc dữ liệu công cụ nào"]

    kho_tai_lieu = " ".join(
        f"{t.get('title') or ''} {t.get('trich') or t.get('content') or ''}"
        for t in tri_thuc
    )
    kho_folded = _fold_vi(kho_tai_lieu)
    kho_tokens = set(_trich_tu_khoa_nghia(kho_tai_lieu))

    # 1) Kiểm số liệu thời hạn / tỷ lệ (VD: 7 ngày, 30 ngày, 10%) nêu trong câu trả lời
    for so_luong, don_vi in _SO_THOI_HAN.findall(str(van_ban or "")):
        dv_fold = _fold_vi(don_vi)
        if f"{so_luong} {dv_fold}" not in kho_folded and so_luong not in kho_folded:
            return False, [
                f"Số liệu «{so_luong} {don_vi}» trong câu trả lời không có trong tài liệu truy xuất"
            ]

    # 2) So khớp từ nội dung giữa câu trả lời và đoạn tài liệu đã truy xuất
    tu_tra_loi = list(dict.fromkeys(_trich_tu_khoa_nghia(van_ban)))
    if not tu_tra_loi:
        # Câu khẳng định quá chung ("Dạ được ạ", "Dạ có ạ") không tự chứng minh được bằng từ khoá
        return False, ["Câu trả lời ngắn/khẳng định chung chưa thể hiện đối chiếu với tài liệu"]

    khop = [t for t in tu_tra_loi if t in kho_tokens]
    ty_le = len(khop) / len(tu_tra_loi)
    if len(tu_tra_loi) >= 3 and (len(khop) < 2 or ty_le < 0.25):
        return False, ["Nội dung tài liệu truy xuất không liên quan hoặc không đủ hỗ trợ câu trả lời"]
    if len(tu_tra_loi) < 3 and len(khop) < 1:
        return False, ["Nội dung tài liệu truy xuất không hỗ trợ trực tiếp câu trả lời"]
    return True, []


def _so(chuoi: str) -> int:
    return int(re.sub(r"\D", "", chuoi) or 0)


def _co_du_lieu(kq: Any) -> bool:
    from agent.core.agent import _co_du_lieu_that

    return _co_du_lieu_that(kq)


def _mau_thuan(cong_cu: list[dict], tri_thuc: list[dict]) -> list[str]:
    ra: list[str] = []
    # (a) Cùng công cụ, cùng tham số, hai kết quả khác nhau trong MỘT lượt.
    da_thay: dict[str, dict] = {}
    for c in cong_cu:
        kq = c.get("ket_qua")
        if not isinstance(kq, dict) or not _co_du_lieu(kq):
            continue
        khoa = f"{c.get('ten')}|{json.dumps(c.get('tham_so'), sort_keys=True, default=str)}"
        cu = da_thay.get(khoa)
        if cu is not None:
            for k in _KHOA_SO_SANH:
                if k in cu and k in kq and cu[k] != kq[k]:
                    ra.append(f"«{_NHAN_CONG_CU.get(str(c.get('ten')), c.get('ten'))}» trả hai giá "
                              f"trị khác nhau cho «{k}» ({cu[k]} / {kq[k]})")
        da_thay[khoa] = kq
    # (b) Đơn: trạng thái ở tra đơn khác trạng thái ở tra vận chuyển.
    don = {str(c["ket_qua"].get("ma_don")): c["ket_qua"].get("trang_thai")
           for c in cong_cu if c.get("ten") == "tra_cuu_don_hang"
           and isinstance(c.get("ket_qua"), dict) and c["ket_qua"].get("tim_thay")}
    for c in cong_cu:
        kq = c.get("ket_qua")
        if c.get("ten") == "tra_cuu_van_chuyen" and isinstance(kq, dict) and kq.get("tim_thay"):
            tt = don.get(str(kq.get("ma_don")))
            if tt is not None and kq.get("trang_thai_don") not in (None, tt):
                ra.append(f"Đơn {kq.get('ma_don')}: sổ đơn ghi «{tt}», tra vận chuyển "
                          f"ghi «{kq.get('trang_thai_don')}»")
    # (c) Giá danh mục khác giá trong tài liệu nói về CHÍNH sản phẩm ấy.
    for c in cong_cu:
        kq = c.get("ket_qua")
        if c.get("ten") != "tra_cuu_san_pham" or not isinstance(kq, dict) or not kq.get("tim_thay"):
            continue
        ten, gia = str(kq.get("ten") or "").strip().lower(), kq.get("gia")
        if not ten or not isinstance(gia, (int, float)):
            continue
        for t in tri_thuc:
            trich = str(t.get("trich") or "").lower()
            vt = trich.find(ten)
            if vt < 0:
                continue
            so = [_so(m.group(1)) for m in _SO_TIEN.finditer(trich[vt:vt + len(ten) + 80])]
            so = [s for s in so if s >= 1000]
            if so and int(gia) not in so:
                ra.append(f"Giá «{kq.get('ten')}»: danh mục {int(gia):,}đ, tài liệu "
                          f"«{t.get('title') or 'không tên'}» ghi {so[0]:,}đ".replace(",", "."))
    return list(dict.fromkeys(ra))


def phan_loai_can_cu(reply: Any, *, nguong: float) -> dict[str, Any]:
    """
    Trạng thái căn cứ của một câu AI soạn. Hàm THUẦN — kiểm bằng Reply dựng tay.
    """
    cong_cu = [c for c in (getattr(reply, "cong_cu", None) or []) if isinstance(c, dict)]
    tri_thuc = [t for t in (getattr(reply, "tri_thuc", None) or []) if isinstance(t, dict)]
    van_ban = str(getattr(reply, "text", "") or "")
    du_lieu = [c for c in cong_cu
               if c.get("ten") != "tim_kien_thuc" and _co_du_lieu(c.get("ket_qua"))]
    mt = _mau_thuan(cong_cu, tri_thuc)
    if mt:
        return {"ma": "mau_thuan", "nhan": TRANG_THAI_CAN_CU["mau_thuan"], "mau_thuan": mt,
                "thieu": [], "huong_dan": "Không chọn giùm nguồn nào — kiểm lại hai nguồn "
                                           "rồi mới trả lời khách."}
    if not du_lieu and la_cau_giao_tiep(van_ban):
        return {"ma": "khong_can", "nhan": TRANG_THAI_CAN_CU["khong_can"], "mau_thuan": [],
                "thieu": [], "huong_dan": "Câu chào hỏi hoặc làm rõ ý khách — không yêu cầu trích căn cứ."}
    if not tri_thuc and not du_lieu:
        return {"ma": "khong_co", "nhan": TRANG_THAI_CAN_CU["khong_co"], "mau_thuan": [],
                "thieu": ["Không có đoạn tài liệu nào và không công cụ nào trả dữ liệu"],
                "huong_dan": "Không gửi như một câu trả lời nghiệp vụ. Có thể dùng câu chờ "
                             "trung lập dưới đây rồi tự kiểm.",
                "cau_cho": CAU_CHO_TRUNG_LAP}
    thieu: list[str] = []
    diem = float(getattr(reply, "confidence", 0.0) or 0.0)
    if tri_thuc and not du_lieu:
        if diem < nguong:
            thieu.append("Đoạn tài liệu tìm được khớp yếu với câu hỏi")
        ho_tro_du, ly_do_ho_tro = can_cu_ho_tro_cau_tra_loi(
            van_ban, tri_thuc, cong_cu, co_du_lieu=False
        )
        if not ho_tro_du:
            thieu.extend(ly_do_ho_tro)
    for c in cong_cu:
        if c.get("ten") in _CONG_CU_TRA and not _co_du_lieu(c.get("ket_qua")):
            thieu.append(f"Tra «{_NHAN_CONG_CU[c['ten']]}» không ra dữ liệu")
    co_tra_gia = any(c.get("ten") in ("tra_cuu_san_pham", "goi_y_san_pham",
                                      "tra_cuu_don_hang", "tao_don_hang")
                     and _co_du_lieu(c.get("ket_qua")) for c in cong_cu)
    if _SO_TIEN.search(van_ban) and not co_tra_gia:
        thieu.append("Câu trả lời nêu số tiền nhưng lượt này không tra danh mục hay đơn hàng")
    thieu = list(dict.fromkeys(thieu))
    if thieu:
        return {"ma": "chua_du", "nhan": TRANG_THAI_CAN_CU["chua_du"], "mau_thuan": [],
                "thieu": thieu, "huong_dan": "Kiểm phần còn thiếu trước khi gửi."}
    return {"ma": "du", "nhan": TRANG_THAI_CAN_CU["du"], "mau_thuan": [], "thieu": [],
            "huong_dan": ""}


def _phan_loai_an_toan(reply: Any, ho_so: Any) -> dict[str, Any]:
    """Phân loại hỏng không được làm mất CẢ dấu vết — nhưng phải nói là hỏng."""
    try:
        return phan_loai_can_cu(
            reply, nguong=float(getattr(ho_so, "nguong_tu_tin", 0.0) or 0.0))
    except Exception as exc:  # noqa: BLE001
        return {"ma": None, "nhan": "Chưa phân loại được căn cứ", "mau_thuan": [],
                "thieu": [], "loi": f"{type(exc).__name__}: {exc}"[:200]}


def dung(reply: Any, *, ho_so: Any, che_do_chung: str, duyet_rieng: bool,
         tu_gui: bool, luot: dict[str, str] | None = None) -> dict[str, Any]:
    """
    Dựng dấu vết từ `Reply` + những gì chỉ tầng kênh biết (hồ sơ, chế độ).

    Hàm THUẦN: không CSDL, không mạng — kiểm được bằng một Reply dựng tay.
    """
    mat_na = che_du_lieu.MatNa()
    nhan, la_luoi = _nhan_luoi(getattr(reply, "luoi_bat", None))
    cong_cu = list(getattr(reply, "cong_cu", None) or [])
    tri_thuc = list(getattr(reply, "tri_thuc", None) or [])
    dv: dict[str, Any] = {
        "phien_ban": PHIEN_BAN,
        "ho_so": {"id": getattr(ho_so, "id", None),
                  "ten": getattr(ho_so, "ten", "") or "Mặc định"},
        "che_do": {"chung": che_do_chung, "duyet_rieng": bool(duyet_rieng),
                   "tu_gui": bool(tu_gui)},
        "tin_cay": {"diem": float(getattr(reply, "confidence", 0.0) or 0.0),
                    "nguong": float(getattr(ho_so, "nguong_tu_tin", 0.0) or 0.0),
                    "co_can_cu": bool(getattr(reply, "grounded", False))},
        "luoi": ({"ma": reply.luoi_bat, "nhan": nhan, "la_luoi": la_luoi}
                 if getattr(reply, "luoi_bat", None) else None),
        "chuyen_nguoi": {"co": bool(getattr(reply, "escalate", False)),
                         "ly_do": _cat(getattr(reply, "escalate_reason", "") or "", mat_na)},
        "cong_cu": [
            {"ten": str(c.get("ten", "")), "vong": c.get("vong"), "ms": c.get("ms"),
             "tham_so": _cat(c.get("tham_so"), mat_na),
             "ket_qua": _cat(c.get("ket_qua"), mat_na)}
            for c in cong_cu[:_TOI_DA_CONG_CU]
        ],
        "cong_cu_bo_bot": max(0, len(cong_cu) - _TOI_DA_CONG_CU),
        # Trích đoạn tài liệu CỬA HÀNG (không phải dữ liệu khách) để người
        # duyệt đọc được câu AI dựa vào — nút "Xem căn cứ". Vẫn đi qua `_cat`
        # để cắt ngắn và phòng tài liệu lỡ chứa số điện thoại của ai đó.
        "tri_thuc": [
            {**{k: r.get(k) for k in ("document_id", "version_id", "version",
                                      "chunk_id", "title", "published_at", "diem")},
             "trich": _cat(r.get("trich") or "", mat_na)}
            for r in tri_thuc[:_TOI_DA_TRI_THUC]
        ],
        "nguon": list(getattr(reply, "sources", None) or [])[:_TOI_DA_TRI_THUC],
        "goi_ky_nang": list(getattr(reply, "goi_ky_nang", None) or [])[:10],
        "model": getattr(reply, "model", "") or "",
        "cost_usd": float(getattr(reply, "cost_usd", 0.0) or 0.0),
        "tokens_in": int(getattr(reply, "tokens_in", 0) or 0),
        "tokens_out": int(getattr(reply, "tokens_out", 0) or 0),
        "latency_ms": int(getattr(reply, "latency_ms", 0) or 0),
        "so_vong": len(getattr(reply, "vong", None) or []),
        # Tính TRƯỚC khi cắt: phân loại đọc kết quả công cụ đầy đủ của lượt.
        "can_cu": _phan_loai_an_toan(reply, ho_so),
        # Đề xuất hành động lượt này sinh ra — thẻ trong hội thoại trỏ về đây.
        "de_xuat": [str(c["ket_qua"]["de_xuat_id"]) for c in cong_cu
                    if isinstance(c.get("ket_qua"), dict) and c["ket_qua"].get("de_xuat_id")][:5],
    }
    # Mã lượt (agent/core/luot_ai.py): nối tin này với MỌI dòng nhật ký của
    # cùng lượt — tin khách, tra tài liệu, công cụ, đơn đã lên — để màn Nhật
    # ký mở được cả lượt từ một tin, và ngược lại.
    if luot:
        dv["luot_id"] = luot.get("luot_id")
        if luot.get("tin_vao_id"):
            dv["tin_vao_id"] = luot["tin_vao_id"]
    return gioi_han(dv)


def _co(dv: dict) -> int:
    return len(json.dumps(dv, ensure_ascii=False, default=str).encode("utf-8"))


def gioi_han(dv: dict[str, Any]) -> dict[str, Any]:
    """Ép dưới `TRAN_BYTE` bằng cách bỏ dần phần ít quan trọng, ghi lại đã bỏ gì."""
    if _co(dv) <= TRAN_BYTE:
        return dv
    for khoa in ("ket_qua", "tham_so"):
        for c in dv.get("cong_cu", []):
            c[khoa] = AN if c.get(khoa) not in (None, AN) else c.get(khoa)
        dv["da_rut_gon"] = [*dv.get("da_rut_gon", []), khoa]
        if _co(dv) <= TRAN_BYTE:
            return dv
    # Nấc cuối: chỉ còn TÊN — vẫn trả lời được "đã gọi gì, đã đọc gì".
    dv["cong_cu"] = [{"ten": c.get("ten", "")} for c in dv.get("cong_cu", [])]
    dv["tri_thuc"] = [{"title": str(r.get("title") or "")[:_CAT_CHUOI]}
                      for r in dv.get("tri_thuc", [])]
    dv["nguon"] = [str(n)[:_CAT_CHUOI] for n in dv.get("nguon", [])]
    dv["da_rut_gon"] = [*dv.get("da_rut_gon", []), "chi_con_ten"]
    return dv
