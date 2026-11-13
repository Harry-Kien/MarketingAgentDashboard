"""
Giới hạn tần suất trong bộ nhớ — cửa sổ trượt theo khoá (IP, phiên webchat).

VÌ SAO CẦN
----------
Webchat là cửa CÔNG KHAI duy nhất ai cũng gọi được, và mỗi tin vào là một
lượt gọi model trả tiền. Không có giới hạn thì một vòng lặp vài dòng là đốt
hết trần chi phí ngày — agent ngưng trả lời MỌI khách thật cho tới hôm sau.

VÌ SAO TRONG BỘ NHỚ, KHÔNG REDIS, KHÔNG THƯ VIỆN
------------------------------------------------
App chạy MỘT tiến trình phục vụ (Dockerfile, `--workers 1`), nên bộ đếm
trong bộ nhớ là đủ và đúng. Thêm Redis là thêm một dịch vụ phải trông; thêm
thư viện là thêm một thứ phải cập nhật — cho đúng việc đếm vài con số. Khi
nào tăng số tiến trình thì phải đổi sang bộ đếm dùng chung (có test canh
giả định một tiến trình).
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable


class GioiHanTanSuat:
    def __init__(self, so_lan: int, trong_giay: float,
                 *, dong_ho: Callable[[], float] = time.monotonic) -> None:
        self.so_lan = so_lan
        self.trong_giay = trong_giay
        self._dong_ho = dong_ho
        self._dem: dict[str, deque[float]] = {}

    def cho_phep(self, khoa: str) -> bool:
        """Ghi một lượt cho `khoa`; False khi đã chạm trần trong cửa sổ."""
        nay = self._dong_ho()
        q = self._dem.setdefault(khoa, deque())
        while q and nay - q[0] >= self.trong_giay:
            q.popleft()
        if len(q) >= self.so_lan:
            return False
        q.append(nay)
        if len(self._dem) > 20_000:
            self._don(nay)
        return True

    def con_cho(self, khoa: str) -> int:
        """Số giây tới khi `khoa` được gọi tiếp — cho header Retry-After."""
        q = self._dem.get(khoa)
        if not q:
            return 0
        return max(1, int(self.trong_giay - (self._dong_ho() - q[0])) + 1)

    def _don(self, nay: float) -> None:
        """Bỏ khoá đã hết hạn — không để bộ nhớ phình theo số IP từng ghé."""
        for k in [k for k, q in self._dem.items() if not q or nay - q[-1] >= self.trong_giay]:
            del self._dem[k]

