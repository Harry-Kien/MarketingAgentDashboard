"""
Webhook Zalo OA — xác thực bằng chữ ký của Zalo, không bằng secret dùng chung.

BỐI CẢNH

Trước bản này Zalo OA KHÔNG có đường webhook riêng. Chỉ có `/webhook/{kenh}`
chung, và nó đòi `WEBHOOK_SECRET` qua header `x-webhook-secret` hoặc query
`?token=`. Với Zalo OA cả hai đều sai:

  · Zalo OA Console KHÔNG cho thêm header vào webhook.
  · Nhét secret vào query là ghi một bí mật DÙNG CHUNG cho mọi kênh vào ô
    cấu hình của bên thứ ba, ở dạng chữ thường.

Và `?token=` chỉ chứng minh "người gửi biết secret", không chứng minh "tin
này từ Zalo".

KHẲNG ĐỊNH QUAN TRỌNG NHẤT: `test_ky_tren_than_THO_khong_phai_json_dump`

`json.dumps` đổi khoảng trắng và thứ tự khoá, nên ký trên bản đã parse rồi
dump lại sẽ ra chữ ký khác. Đây là chỗ mọi bản hiện thực chữ ký webhook đều
hỏng lần đầu, và nó hỏng theo kiểu tệ nhất: chạy được với payload mình tự
dựng trong test, chết với payload thật.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api.zalo_oa_webhook import chu_ky_hop_le, tinh_mac  # noqa: E402

APP = "2109757420003470723"
SECRET = "a" * 32
TS = "1725350400000"
THAN = b'{"app_id":"x","event_name":"user_send_text","timestamp":"1725350400000"}'


def _ky(raw=THAN, app=APP, ts=TS, secret=SECRET) -> str:
    return "mac=" + tinh_mac(app, raw, ts, secret)


# ---------------------------------------------------------------
#  Công thức đúng
# ---------------------------------------------------------------

def test_cong_thuc_khop_tai_lieu_zalo():
    """mac = sha256(app_id + raw_body + timestamp + oa_secret_key)."""
    mong_doi = hashlib.sha256(
        (APP + THAN.decode() + TS + SECRET).encode()
    ).hexdigest()
    assert tinh_mac(APP, THAN, TS, SECRET) == mong_doi


def test_chu_ky_dung_thi_qua():
    assert chu_ky_hop_le(_ky(), APP, THAN, TS, SECRET) is True


def test_chap_nhan_ca_khi_header_khong_co_tien_to_mac():
    """Zalo gửi `mac=<hex>`; đừng vỡ nếu một ngày họ gửi hex trần."""
    hex_tran = tinh_mac(APP, THAN, TS, SECRET)
    assert chu_ky_hop_le(hex_tran, APP, THAN, TS, SECRET) is True


# ---------------------------------------------------------------
#  Ký trên THÂN THÔ
# ---------------------------------------------------------------

def test_ky_tren_than_THO_khong_phai_json_dump():
    """
    Khẳng định quan trọng nhất tệp này.

    `json.dumps` đổi khoảng trắng và thứ tự khoá. Ký trên bản dump lại sẽ ra
    chữ ký KHÁC — và lỗi ấy chạy được với payload tự dựng trong test, chết
    với payload thật của Zalo.
    """
    tho = b'{"b": 2,   "a": 1}'
    dump_lai = json.dumps(json.loads(tho)).encode()
    assert tho != dump_lai, "ca kiểm này vô nghĩa nếu hai bản trùng nhau"
    assert tinh_mac(APP, tho, TS, SECRET) != tinh_mac(APP, dump_lai, TS, SECRET)


def test_doi_mot_byte_trong_than_la_chu_ky_lech():
    hong = THAN.replace(b"user_send_text", b"user_send_imagE")
    assert chu_ky_hop_le(_ky(), APP, hong, TS, SECRET) is False


# ---------------------------------------------------------------
#  Fail closed — lần thứ tư cùng một khuôn trong repo này
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "app,ts,secret",
    [("", TS, SECRET), (APP, "", SECRET), (APP, TS, ""), ("", "", "")],
)
def test_thieu_manh_nao_cung_TU_CHOI(app, ts, secret):
    """
    `doc_thach_thuc` của Meta, `kiem_bi_mat_webhook` của vận chuyển, và
    nhánh `webhook_secret` trong main.py đều từng fail-open. Rỗng nghĩa là
    TỪ CHỐI, không phải "bỏ qua kiểm tra".
    """
    assert chu_ky_hop_le(_ky(), app, THAN, ts, secret) is False


def test_khong_co_header_thi_TU_CHOI():
    assert chu_ky_hop_le("", APP, THAN, TS, SECRET) is False


def test_chu_ky_cua_OA_KHAC_khong_dung_duoc():
    """
    Mỗi OA có secret riêng. Chữ ký ký bằng khoá của OA khác phải bị từ chối,
    nếu không thì nối hai OA là một OA giả được cả hai.
    """
    khac = "b" * 32
    assert chu_ky_hop_le(_ky(secret=khac), APP, THAN, TS, SECRET) is False


def test_timestamp_khac_la_chu_ky_lech():
    """Chống phát lại: chữ ký gắn với thời điểm."""
    assert chu_ky_hop_le(_ky(ts="1"), APP, THAN, TS, SECRET) is False


# ---------------------------------------------------------------
#  Chi tiết hiện thực
# ---------------------------------------------------------------

def test_so_sanh_bang_compare_digest():
    """
    So chuỗi thường thoát ra ở byte đầu khác nhau, và thời gian thoát ra rò
    rỉ từng byte của chữ ký đúng.
    """
    nguon = (ROOT / "agent" / "api" / "zalo_oa_webhook.py").read_text(encoding="utf-8")
    assert "compare_digest" in nguon
    assert "nhan_duoc == mong_doi" not in nguon


def test_duong_mang_account_id():
    """
    Mỗi OA có secret riêng, nên phải biết OA nào TRƯỚC khi kiểm được chữ ký.
    Đoán OA từ thân tin rồi mới kiểm là để kẻ gửi tự chọn khoá dùng để kiểm
    chính nó.
    """
    from agent.api.zalo_oa_webhook import router

    duong = [r.path for r in router.routes]
    assert any("{account_id}" in d for d in duong), duong


def test_dashboard_hien_URL_kem_account_id():
    """
    Trước bản này dashboard trả chuỗi RỖNG cho zalo_oa, nên thẻ Zalo OA
    không có URL nào — người dùng không biết dán gì vào Zalo Console.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "webhook/native/zalo-oa/" in js
    assert "${account.id}" in js


def test_route_da_duoc_gan_vao_app():
    """
    Viết route mà quên `include_router` thì nó 404 và không ai biết.

    Kiểm qua OpenAPI chứ không duyệt `app.routes`: bản FastAPI này bọc
    router đã include trong `_IncludedRouter`, một đối tượng KHÔNG có
    `.path`. Duyệt `app.routes` rồi đọc `.path` chỉ thấy những route khai
    trực tiếp trong `main.py` — và ca kiểm sẽ đỏ oan cho mọi router.

    OpenAPI cũng đúng hơn về mặt ý nghĩa: nó là thứ client nhìn thấy.
    """
    from fastapi.openapi.utils import get_openapi

    import agent.main as m

    spec = get_openapi(title="x", version="1", routes=m.app.routes)
    assert "/webhook/native/zalo-oa/{account_id}" in spec["paths"]
