"""
Phiên Zalo cá nhân phải TỰ khôi phục, không đợi người bấm.

LỖI ĐÃ XẢY RA THẬT
------------------
Phiên sống trong RAM của sidecar. Khởi động lại sidecar — hoặc máy chủ, hoặc
deploy bản mới — là phiên biến mất. Vault vẫn giữ session đã mã hoá và đã có
sẵn endpoint `restore-session`, nhưng KHÔNG có gì gọi nó.

Kết quả: kênh Zalo chết câm. Sidecar vẫn `healthz` xanh, app vẫn xanh, tài
khoản trên dashboard vẫn hiện "Sẵn sàng" — chỉ có tin khách là không tới
nữa. Không một dòng lỗi nào.

Đúng loại hỏng im lặng nguy hiểm nhất: mọi đèn đều xanh trong khi khách
nhắn vào hư không.
"""
from __future__ import annotations

import asyncio

from agent.omnichannel.zalo_session_keeper import khoi_phuc_phien_dut


class _Adapter:
    def __init__(self, trang_thai: str, khoi_phuc_duoc: bool = True):
        self._trang_thai = trang_thai
        self._khoi_phuc_duoc = khoi_phuc_duoc
        self.da_goi_status = 0
        self.da_goi_restore = 0

    async def status(self):
        self.da_goi_status += 1
        return {"status": self._trang_thai}

    async def restore_session(self, session):
        self.da_goi_restore += 1
        if not self._khoi_phuc_duoc:
            raise RuntimeError("session hết hạn")
        self._trang_thai = "connected"
        return {"status": "connected", "own_id": "own-1"}

    async def aclose(self):
        return None


def _chay(accounts, adapters, sessions, canh_bao=None):
    async def mo(account_id):
        return adapters[account_id], {"session": sessions.get(account_id)}

    return asyncio.run(
        khoi_phuc_phien_dut(accounts, mo, canh_bao=canh_bao or (lambda *_: None))
    )


def test_khoi_phuc_dung_phien_dang_dut():
    adapters = {"a": _Adapter("disconnected")}
    ket_qua = _chay(["a"], adapters, {"a": {"cookie": {}}})

    assert adapters["a"].da_goi_restore == 1
    assert ket_qua["da_khoi_phuc"] == ["a"]


def test_khong_dung_toi_phien_dang_song():
    """Gọi restore lên phiên đang chạy là tự tay ngắt kết nối đang tốt."""
    adapters = {"a": _Adapter("connected")}
    ket_qua = _chay(["a"], adapters, {"a": {"cookie": {}}})

    assert adapters["a"].da_goi_restore == 0
    assert ket_qua["da_khoi_phuc"] == []


def test_khong_co_session_luu_thi_bao_chu_khong_im_lang():
    """Chưa từng quét QR thì không khôi phục được — nhưng phải nói ra."""
    adapters = {"a": _Adapter("disconnected")}
    da_bao = []
    ket_qua = _chay(["a"], adapters, {}, canh_bao=lambda acc, ly_do: da_bao.append((acc, ly_do)))

    assert adapters["a"].da_goi_restore == 0
    assert ket_qua["can_quet_lai"] == ["a"]
    assert da_bao and da_bao[0][0] == "a"


def test_khoi_phuc_that_bai_thi_bao_de_nguoi_quet_lai():
    adapters = {"a": _Adapter("disconnected", khoi_phuc_duoc=False)}
    da_bao = []
    ket_qua = _chay(["a"], adapters, {"a": {"cookie": {}}},
                    canh_bao=lambda acc, ly_do: da_bao.append((acc, ly_do)))

    assert ket_qua["can_quet_lai"] == ["a"]
    assert da_bao and "hết hạn" in da_bao[0][1]


def test_mot_account_hong_khong_lam_chet_ca_vong():
    """Nhiều tài khoản Zalo dùng chung một sidecar; một cái lỗi không được kéo cả cụm."""
    adapters = {
        "a": _Adapter("disconnected", khoi_phuc_duoc=False),
        "b": _Adapter("disconnected"),
    }
    ket_qua = _chay(["a", "b"], adapters, {"a": {"cookie": {}}, "b": {"cookie": {}}})

    assert ket_qua["da_khoi_phuc"] == ["b"]
    assert ket_qua["can_quet_lai"] == ["a"]
