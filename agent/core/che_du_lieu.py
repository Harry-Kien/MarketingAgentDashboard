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
_CCCD = re.compile(r"(?<!\w)0\d{11}(?!\w)")
_SDT = re.compile(r"(?<!\w)(?:\+84|84|0)(?:[ .\-]?\d){9,10}(?!\w)")
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
    "LƯU Ý HỆ THỐNG: số điện thoại, email, số CCCD của khách đã được thay "
    "bằng mã như [SĐT_1], [EMAIL_1], [CCCD_1] để bảo vệ dữ liệu. Khi cần nhắc "
    "lại cho khách hoặc truyền vào công cụ (ví dụ khach_sdt), dùng NGUYÊN mã "
    "đó — hệ thống tự đổi lại số thật. Không hỏi lại khách số mà mã đã có."
)


def _chuan_sdt(s: str) -> str:
    so = re.sub(r"\D", "", s)
    return "0" + so[2:] if so.startswith("84") else so


class MatNa:
    """Bảng mã cho MỘT lượt: che trước khi gửi model, mở khi nhận về."""

    def __init__(self) -> None:
        self._xuoi: dict[tuple[str, str], str] = {}
        self._nguoc: dict[str, str] = {}

    @property
    def co_che(self) -> bool:
        return bool(self._nguoc)

    def _ma(self, loai: str, gia_tri: str) -> str:
        khoa = (loai, gia_tri)
        if khoa not in self._xuoi:
            n = sum(1 for (lo, _) in self._xuoi if lo == loai) + 1
            ma = f"[{loai}_{n}]"
            self._xuoi[khoa] = ma
            self._nguoc[f"{loai}_{n}"] = gia_tri
        return self._xuoi[khoa]

    def che(self, van_ban: str) -> str:
        if not van_ban:
            return van_ban
        t = _EMAIL.sub(lambda m: self._ma("EMAIL", m.group(0).lower()), van_ban)
        t = _CCCD.sub(lambda m: self._ma("CCCD", m.group(0)), t)
        return _SDT.sub(lambda m: self._ma("SĐT", _chuan_sdt(m.group(0))), t)

    def mo(self, van_ban: str) -> str:
        if not van_ban or not self._nguoc:
            return van_ban

        def doi(m: re.Match) -> str:
            loai = (m.group(1) or m.group(3)).upper().replace("SDT", "SĐT")
            so = int(m.group(2) or m.group(4))
            return self._nguoc.get(f"{loai}_{so}", m.group(0))
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
        if isinstance(x, str):
            return self.mo(x)
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
