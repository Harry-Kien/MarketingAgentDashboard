"""
Che dữ liệu cá nhân TRƯỚC khi gửi sang máy chủ model ở nước ngoài.

VÌ SAO
------
Mọi lượt trả lời gửi câu khách hỏi, lịch sử hội thoại, hồ sơ khách và kết
quả công cụ tới máy chủ model ngoài Việt Nam — "chuyển dữ liệu ra nước
ngoài" theo Luật BVDLCN 91/2025 Điều 20. Model không cần biết số điện thoại
THẬT để tư vấn hay để gọi công cụ lên đơn: nó chỉ cần biết "có một số điện
thoại, là cái này". Nên số thật được thay bằng mã ([SĐT_1]) trước khi đi,
và mã được đổi lại thành số thật ở hai chỗ: tham số công cụ (lên đơn cần số
thật) và câu trả lời gửi khách.

CHE GÌ, KHÔNG CHE GÌ
--------------------
Chỉ ba loại có ĐỊNH DẠNG chắc chắn: số điện thoại Việt Nam, email, số CCCD
(12 số, bắt đầu bằng 0). KHÔNG che địa chỉ: địa chỉ không có khuôn — đoán
thì vừa che nhầm (tên sản phẩm, câu hỏi) vừa che sót, và một bộ che "trông
như che địa chỉ" là xanh giả. Hồ sơ BVDLCN ghi rõ địa chỉ vẫn đi nguyên văn.

Chuỗi số dính liền chữ cái (mã đơn AS2608..., mã vận đơn S1.A1...) không
bị che: ranh giới `\\w` hai đầu.

MỘT LƯỢT, MỘT BẢNG MÃ
---------------------
`MatNa` sống đúng một lượt `respond()`. Cùng một số (dù viết "0912 345 678"
hay "+84912345678") luôn ra cùng một mã trong lượt — model thấy khách nhắc
lại cùng một số thì hiểu là một số.
"""
from __future__ import annotations

import re
from typing import Any

# Thứ tự quan trọng: CCCD (12 số) trước số điện thoại (10–11 số).
_CCCD = re.compile(r"(?<![\w.,])0\d{11}(?![\w]|[.,]\d)")
# Ứng viên số điện thoại: một CHUỖI CỤM SỐ cách nhau bởi dấu cách/chấm/gạch,
# có thể có dấu +. Quyết định "có phải số điện thoại" nằm ở `_tach_sdt`, không
# ở regex: regex kiểu `(?:[ .-]?\d){9,10}` từng nuốt luôn số lượng đứng sau
# ("0912345678 1 hộp" → "09123456781", đo được khi rà soát 28.10.2026).
_UNG_VIEN_SDT = re.compile(r"(?<![\w.,+])\+?\d+(?:[ .\-]\d+)*(?![\w])")
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Đọc lại mã — chịu được model viết lệch: "SĐT_1", "[SDT 1]", "[ sđt_1 ]".
# Khoảng trắng chỉ được nuốt BÊN TRONG ngoặc: nuốt cả bên ngoài là "số SĐT_1
# và" thành "số0912345678và" (đo được khi viết mô-đun này).
_MA = re.compile(
    r"\[\s*(SĐT|SDT|EMAIL|CCCD)[ _](\d{1,3})\s*\]"
    r"|(?<!\w)(SĐT|SDT|EMAIL|CCCD)[ _](\d{1,3})(?!\w)",
    re.IGNORECASE,
)

GHI_CHU_CHO_MODEL = (
    "LƯU Ý HỆ THỐNG: số điện thoại, email, số CCCD do KHÁCH cung cấp đã được thay "
    "bằng mã như [SĐT_1], [EMAIL_1], [CCCD_1] để bảo vệ dữ liệu. Khi cần nhắc "
    "lại cho khách hoặc truyền vào công cụ (ví dụ khach_sdt), dùng NGUYÊN mã "
    "đó — hệ thống tự đổi lại số thật. Không hỏi lại khách số mà mã đã có."
)


def _hop_le(so: str) -> bool:
    """Di động 0[35789] + 8 số, máy bàn 02 + 9 số."""
    return (len(so) == 10 and so[0] == "0" and so[1] in "35789") or (
        len(so) == 11 and so.startswith("02"))


def _tach_sdt(ung_vien: str) -> tuple[int, str] | None:
    """
    Đầu chuỗi `ung_vien` có phải một số điện thoại không. Trả (số ký tự thuộc
    số điện thoại, số chuẩn hoá) hoặc None.

    Đi từng CỤM: cụm sau cụm đầu phải ≥ 3 chữ số (số viết "0912 345 678",
    "028 3823 4567"); dừng ngay khi đủ một số hợp lệ, phần còn lại để nguyên.
    Nhờ vậy "05.09.2026" (cụm 2 số) không phải số điện thoại, và "0912345678
    1 hộp" chỉ che đúng mười số đầu.
    """
    co_cong = ung_vien.startswith("+")
    cum = list(re.finditer(r"\d+", ung_vien))
    if not cum:
        return None
    dau = cum[0].group(0)
    if not (dau.startswith("0") and len(dau) >= 3) and not dau.startswith("84") and not co_cong:
        return None
    gom = ""
    for k, m in enumerate(cum):
        g = m.group(0)
        if k > 0 and len(g) < 3:
            return None
        gom += g
        so = gom
        if so.startswith("84"):
            so = so[2:]
            so = so if so.startswith("0") else "0" + so
        elif co_cong:
            return None
        if _hop_le(so):
            return m.end(), so
        if len(so) > 11:
            return None
    return None


def _chuan_sdt(s: str) -> str:
    kq = _tach_sdt(s)
    return kq[1] if kq else re.sub(r"\D", "", s)


class MatNa:
    """Bảng mã cho MỘT lượt: che trước khi gửi model, mở khi nhận về."""

    def __init__(self) -> None:
        self._xuoi: dict[tuple[str, str], str] = {}
        # mã -> (giá trị chuẩn hoá cho công cụ, chữ GỐC lần đầu khách viết)
        self._nguoc: dict[str, tuple[str, str]] = {}

    @property
    def co_che(self) -> bool:
        return bool(self._nguoc)

    def _ma(self, loai: str, chuan: str, goc: str) -> str:
        khoa = (loai, chuan)
        if khoa not in self._xuoi:
            n = sum(1 for (lo, _) in self._xuoi if lo == loai) + 1
            ma = f"[{loai}_{n}]"
            self._xuoi[khoa] = ma
            self._nguoc[f"{loai}_{n}"] = (chuan, goc)
        return self._xuoi[khoa]

    def _che_sdt(self, m: re.Match) -> str:
        kq = _tach_sdt(m.group(0))
        if kq is None:
            return m.group(0)
        dai, so = kq
        return self._ma("SĐT", so, m.group(0)[:dai]) + m.group(0)[dai:]

    def che(self, van_ban: str) -> str:
        if not van_ban:
            return van_ban
        t = _EMAIL.sub(lambda m: self._ma("EMAIL", m.group(0).lower(), m.group(0)), van_ban)
        t = _CCCD.sub(lambda m: self._ma("CCCD", m.group(0), m.group(0)), t)
        return _UNG_VIEN_SDT.sub(self._che_sdt, t)

    def mo(self, van_ban: str, *, cho_cong_cu: bool = False) -> str:
        """
        Đổi mã về giá trị thật. Câu gửi KHÁCH nhận chữ gốc khách đã viết
        ("+84 0912 345 678" vẫn là "+84 0912 345 678"); CÔNG CỤ nhận số chuẩn
        hoá ("0912345678") để kiểm và lưu thống nhất.
        """
        if not van_ban or not self._nguoc:
            return van_ban

        def doi(m: re.Match) -> str:
            loai = (m.group(1) or m.group(3)).upper().replace("SDT", "SĐT")
            so = int(m.group(2) or m.group(4))
            gia_tri = self._nguoc.get(f"{loai}_{so}")
            if gia_tri is None:
                return m.group(0)
            return gia_tri[0] if cho_cong_cu else gia_tri[1]
        return _MA.sub(doi, van_ban)

    def ma_con_sot(self, van_ban: str) -> list[str]:
        """Mã trông như mã che nhưng không có trong bảng — model bịa ra."""
        return [m.group(0) for m in _MA.finditer(self.mo(van_ban or ""))]

    def che_obj(self, x: Any) -> Any:
        if isinstance(x, str):
            return self.che(x)
        if isinstance(x, dict):
            return {k: self.che_obj(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self.che_obj(v) for v in x]
        return x

    def mo_obj(self, x: Any) -> Any:
        """Dành cho tham số CÔNG CỤ: giá trị chuẩn hoá."""
        if isinstance(x, str):
            return self.mo(x, cho_cong_cu=True)
        if isinstance(x, dict):
            return {k: self.mo_obj(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self.mo_obj(v) for v in x]
        return x

    def che_lich_su(self, history: list[dict]) -> list[dict]:
        """Bản sao lịch sử đã che — không sửa danh sách gốc của người gọi."""
        ra = []
        for h in history:
            c = h.get("content")
            if isinstance(c, str):
                ra.append({**h, "content": self.che(c)})
            elif isinstance(c, list):
                ra.append({**h, "content": [
                    {**p, "text": self.che(p["text"])} if isinstance(p, dict) and isinstance(p.get("text"), str) else p
                    for p in c]})
            else:
                ra.append(h)
        return ra
