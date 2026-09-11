"""
Hồ sơ agent: nhiều "nhân sự số", thêm bằng cấu hình chứ không bằng mã.

RÀNG BUỘC TRUNG TÂM: CẤU HÌNH CHỈ ĐƯỢC SIẾT, KHÔNG ĐƯỢC NỚI
------------------------------------------------------------
`CLAUDE.md` viết: ràng buộc nằm trong MÃ, không nằm trong prompt. Sáu lớp
lưới trong `agent/core/agent.py` canh luật quảng cáo mỹ phẩm và ranh giới
tư vấn y tế — những thứ không được phép sai.

Nếu một hồ sơ agent hạ được ngưỡng tự tin, nâng được trần chi phí, hoặc
thay được `SYSTEM`, thì một ô nhập trên dashboard vừa trở thành đường đi
vòng qua sáu lớp lưới ấy — và người điền ô đó không hề biết mình đang làm
vậy. Đó là kiểu hỏng tệ nhất: không nổ, không ghi nhật ký, và chỉ lộ ra
bằng một câu trả lời sai luật gửi cho khách thật.

Nên mọi giá trị đi qua `siet()`:

    nguong_tu_tin  ->  max(hồ sơ, toàn cục)   chuyển người SỚM hơn, không muộn hơn
    tran_chi_phi   ->  min(hồ sơ, toàn cục)   dừng SỚM hơn, không muộn hơn
    huong_dan      ->  chỉ THÊM vào khối biến động

Và `SYSTEM` không bao giờ bị thay. Hồ sơ agent không có ô nào cho việc đó,
và có test canh rằng nó không có.

VÌ SAO HƯỚNG DẪN VÀO KHỐI BIẾN ĐỘNG CHỨ KHÔNG VÀO `SYSTEM`
-----------------------------------------------------------
Hai lý do, cả hai đều thật:

  An toàn — `SYSTEM` chứa mọi câu cấm. Cho hồ sơ ghi đè vào đó là cho nó
  gỡ các câu ấy.

  Tiền — `SYSTEM` là phần được cache theo prefix. Mỗi hồ sơ một `SYSTEM`
  khác nhau nghĩa là mỗi kênh một điểm cache riêng, và cache prefix chết
  với mọi request. Cùng lý lẽ đã ghi cho gói kỹ năng ở `agent.py` dòng ~456.
"""
from __future__ import annotations

from typing import Any, NamedTuple

from agent import db
from agent.config import settings


class HoSo(NamedTuple):
    id: str | None
    ten: str
    huong_dan: str
    nguong_tu_tin: float
    tran_chi_phi: float


def mac_dinh() -> HoSo:
    """
    Hồ sơ khi kênh chưa gán gì — đúng hành vi trước khi có khối này.

    Không phải một hồ sơ "rỗng": nó mang đúng ngưỡng toàn cục, nên mã gọi
    không cần rẽ nhánh `if ho_so is None` ở mọi chỗ dùng. Rẽ nhánh ở nhiều
    chỗ là chỗ để một nhánh bị quên.
    """
    return HoSo(
        id=None, ten="Mặc định", huong_dan="",
        nguong_tu_tin=float(settings.confidence_floor),
        tran_chi_phi=float(settings.max_cost_per_conversation),
    )


def siet(dong: dict[str, Any]) -> HoSo:
    """
    Ép một dòng `agent_ho_so` về giá trị KHÔNG LỎNG HƠN ngưỡng toàn cục.

    Đây là chỗ ràng buộc "chỉ được siết" thành mã. Đọc thẳng giá trị trong
    CSDL mà dùng là để một ô nhập trên dashboard nới được lưới an toàn.
    """
    toan_cuc_nguong = float(settings.confidence_floor)
    toan_cuc_tran = float(settings.max_cost_per_conversation)

    nguong = dong.get("nguong_tu_tin")
    tran = dong.get("tran_chi_phi")

    return HoSo(
        id=str(dong["id"]) if dong.get("id") else None,
        ten=dong.get("ten") or "Mặc định",
        huong_dan=(dong.get("huong_dan") or "").strip(),
        # CAO hơn = chuyển người SỚM hơn. Lấy max là không bao giờ muộn hơn
        # ngưỡng toàn cục.
        nguong_tu_tin=max(toan_cuc_nguong,
                          float(nguong) if nguong is not None else 0.0),
        # THẤP hơn = dừng SỚM hơn. Lấy min là không bao giờ tiêu quá trần
        # toàn cục.
        tran_chi_phi=min(toan_cuc_tran,
                         float(tran) if tran is not None else toan_cuc_tran),
    )


async def cho_kenh(account_id: Any) -> HoSo:
    """
    Hồ sơ agent của một tài khoản kênh.

    Chưa gán, hồ sơ đã tắt, hoặc không đọc được -> MẶC ĐỊNH. Không ném: hàm
    này chạy trên đường xử lý tin khách, và một ngoại lệ ở đây làm chết cả
    lượt trả lời — tức để cứu một dòng cấu hình, ta đánh mất câu trả lời cho
    khách.

    Rơi về mặc định là an toàn theo đúng nghĩa của khối này: mặc định mang
    ngưỡng toàn cục, tức nghiêm khắc ngang hoặc hơn mọi hồ sơ hợp lệ.
    """
    if account_id is None:
        return mac_dinh()
    try:
        dong = await db.fetchrow(
            "SELECT hs.id, hs.ten, hs.huong_dan, hs.nguong_tu_tin, "
            "       hs.tran_chi_phi "
            "FROM channel_accounts tk "
            "JOIN agent_ho_so hs ON hs.id = tk.agent_ho_so_id "
            "WHERE tk.id = $1 AND hs.bat = true", account_id)
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger("agent.ho_so").error(
            "KHÔNG đọc được hồ sơ agent cho kênh %s (%s: %s) — dùng mặc định",
            account_id, type(exc).__name__, exc)
        return mac_dinh()
    return siet(dict(dong)) if dong else mac_dinh()


def khoi_huong_dan(ho_so: HoSo) -> str:
    """
    Đoạn chèn vào khối biến động, hoặc chuỗi rỗng.

    Có dòng phân tách và nhãn "HƯỚNG DẪN NỘI BỘ" y như hướng dẫn gói kỹ
    năng: ghép suông thì mô hình đọc cả khối như một tài liệu tra được và
    trích nguyên văn cho khách — lộ cách vận hành, và câu trả lời nghe như
    đọc quy trình nội bộ.
    """
    if not ho_so.huong_dan:
        return ""
    return ("\n\n---\n"
            "HƯỚNG DẪN NỘI BỘ (không phải tài liệu để trích dẫn):\n"
            f"## Hồ sơ agent «{ho_so.ten}»\n{ho_so.huong_dan}")
