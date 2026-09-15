"""
Mốc thời gian dùng để ký phải lấy từ THÂN TIN, không phải từ header.

Tài liệu và mọi bản hiện thực công khai đều thống nhất:

    mac = sha256(app_id + raw_body + body["timestamp"] + oa_secret_key)

Zalo KHÔNG khai một header `X-ZEvent-Timestamp` nào. Bản trước đọc header
TRƯỚC rồi mới lui về thân tin — nên chỉ cần Zalo, một proxy, hay cái tunnel
ở giữa thêm một header tên như vậy với giá trị khác là **mọi webhook thật
bị từ chối 401**.

Và nó hỏng theo đúng kiểu tệ nhất: từ phía ta nhìn vào, "bị từ chối hết"
với "chưa ai nhắn" giống hệt nhau — hộp thư trống, không lỗi, không nhật
ký, dashboard xanh. Không có cách nào phân biệt nếu không đi hỏi Zalo.

Test dưới đây canh: ký theo thân tin thì QUA, kể cả khi header nói khác.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api.zalo_oa_webhook import (chu_ky_hop_le,  # noqa: E402
                                       moc_thoi_gian_co_the)

APP = "2109757420003470723"
SECRET = "s" * 32


def _than(ts) -> bytes:
    """Thân thô, giữ nguyên byte — ký trên bản dump lại là sai."""
    if isinstance(ts, str):
        return ('{"app_id":"x","event_name":"user_send_text",'
                f'"timestamp":"{ts}"}}').encode()
    return ('{"app_id":"x","event_name":"user_send_text",'
            f'"timestamp":{ts}}}').encode()


def _ky(raw: bytes, ts: str) -> str:
    return "mac=" + hashlib.sha256(
        (APP + raw.decode() + ts + SECRET).encode()).hexdigest()


def _qua(raw: bytes, sig: str, header_ts: str = "") -> bool:
    return any(
        chu_ky_hop_le(sig, APP, raw, ts, SECRET)
        for ts in moc_thoi_gian_co_the(raw, header_ts)
    )


def test_ky_theo_than_tin_thi_qua():
    raw = _than("1725350400000")
    assert _qua(raw, _ky(raw, "1725350400000")) is True


def test_header_la_troi_nhung_than_tin_moi_la_that():
    """
    Ca kiểm quan trọng nhất tệp này.

    Có một header mốc thời gian mang giá trị KHÁC — đúng tình huống một
    proxy chen vào. Chữ ký thật vẫn ký theo thân tin, nên vẫn phải QUA.
    """
    raw = _than("1725350400000")
    sig = _ky(raw, "1725350400000")
    assert _qua(raw, sig, header_ts="9999999999999") is True


def test_moc_thoi_gian_dang_SO_trong_than_van_ky_duoc():
    """Zalo có nơi gửi chuỗi, có nơi gửi số. Cả hai đều phải khớp."""
    raw = _than(1725350400000)
    assert _qua(raw, _ky(raw, "1725350400000")) is True


def test_khong_co_moc_nao_khop_thi_TU_CHOI():
    raw = _than("1725350400000")
    assert _qua(raw, _ky(raw, "1111111111111")) is False


def test_than_khong_phai_json_thi_khong_no_ma_TU_CHOI():
    """
    Thân hỏng phải thành 'từ chối', không thành 500.

    Bản trước gọi `json.loads` thẳng trong biểu thức kiểm chữ ký, nên một
    thân rác làm route nổ 500 kèm stack trace — và Zalo thấy 5xx thì gửi
    lại mãi.
    """
    rac = b"<html>khong phai json</html>"
    assert moc_thoi_gian_co_the(rac, "") == []
    assert _qua(rac, "mac=" + "0" * 64) is False


def test_van_chap_nhan_header_khi_than_khong_co_moc():
    """Lui về header chỉ khi thân tin không mang mốc nào."""
    raw = b'{"app_id":"x","event_name":"user_send_text"}'
    assert _qua(raw, _ky(raw, "1725350400000"),
                header_ts="1725350400000") is True
