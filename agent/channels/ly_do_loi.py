"""
Đưa LÝ DO thật của provider vào sự kiện sức khoẻ, sau khi che bí mật.

LỖI THẬT, NGƯỜI DÙNG BÁO (03.09.2026)
-------------------------------------
Người dùng điền đủ bốn ô Zalo OA, bấm Lưu, và tài khoản chuyển sang
`degraded`. Dashboard không nói vì sao. Nhật ký ghi:

    {"error_type": "RuntimeError"}

Trong khi Zalo đã trả lời rõ ràng:

    Invalid secret key

Hệ thống BIẾT câu trả lời và ném nó đi. Người dùng ngồi đoán, rồi hỏi lại
— và phải chạy tay adapter mới moi được ra.

Bốn adapter cùng mắc một lỗi ấy, cùng một dòng mã chép qua chép lại.

VÌ SAO PHẢI CHE
---------------
Thông điệp lỗi của thư viện HTTP thường kèm URL ĐẦY ĐỦ. Với Meta, URL ấy
là `debug_token?input_token=…&access_token=…` — đúng hai bí mật mà bộ lọc
nhật ký vừa được dựng để chặn.

Sự kiện sức khoẻ đi vào cơ sở dữ liệu và hiện lên dashboard, tức là nó tồn
tại LÂU HƠN một dòng log. Không che ở đây thì bí mật nằm trong bảng
`account_health_events` vĩnh viễn.

Dùng lại đúng bộ che của `agent/nhat_ky.py`, không viết bộ thứ hai: hai bộ
che thì cái yếu hơn quyết định.
"""
from __future__ import annotations

from agent import nhat_ky

# Trần độ dài. Thông điệp lỗi của httpx có thể kèm cả traceback nội bộ;
# nhét nguyên vào JSONB rồi hiện lên dashboard là một bức tường chữ mà
# người vận hành không đọc.
DAI_TOI_DA = 300


def chi_tiet_loi(exc: BaseException) -> dict:
    """
    Dựng `detail` cho `ConnectionCheck` — có loại VÀ có lý do.

    Loại ngoại lệ một mình không hành động được: `RuntimeError` đúng cho cả
    "sai secret key" lẫn "mạng chết". Lý do mới là thứ nói cho người vận
    hành phải sửa ô nào.
    """
    thong_diep = nhat_ky.che(str(exc) or "", nhat_ky.LocBiMat().bi_mat)
    ra: dict[str, str] = {"error_type": type(exc).__name__}
    if thong_diep:
        ra["ly_do"] = thong_diep[:DAI_TOI_DA]
    return ra
