"""
Script bật tunnel phải tránh đúng ba cái bẫy đã dính thật.

BA CHUYỆN ĐÃ XẢY RA TRÊN MÁY ĐANG CHẠY (03.09.2026)

1. Hai `cloudflared` cùng sống. Mỗi lần `tunnel --url` cấp một tên miền
   NGẪU NHIÊN MỚI, nên bật hai lần là có hai tên miền. `.env` giữ một cái,
   Zalo gọi vào cái kia. Đo được: `.env` trỏ `rap-effect-...` đã chết trong
   khi `olive-pty-...` mới là cái đang chạy.

2. `ERR failed to serve tunnel connection ... ip=2606:4700:a8::8` lặp mãi.
   Đó là IPv6 của Cloudflare; nhiều mạng ở Việt Nam không đi IPv6 ổn định.

3. Tên miền đổi mà `.env` giữ cái cũ. Dashboard vẫn dựng URL webhook, Zalo
   vẫn nhận URL ấy — chỉ là không bao giờ gọi tới được. Không lỗi, không
   nhật ký, không ai biết. Đúng kiểu hỏng im lặng.

VÌ SAO SOI BẰNG AST CHỨ KHÔNG `in` CHUỖI

Chính đoạn docstring ở trên có đủ chữ "edge-ip-version", "taskkill",
"PUBLIC_BASE_URL". Quét cả tệp thì test xanh nhờ đọc trúng lời giải thích
của chính nó — xanh giả, đúng cái bẫy đã dính bốn lần trong repo này.
"""
from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NGUON = (ROOT / "scripts" / "chay_tunnel.py").read_text(encoding="utf-8")
CAY = ast.parse(NGUON)


def _ham(ten: str) -> ast.FunctionDef:
    for node in ast.walk(CAY):
        if isinstance(node, ast.FunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


def _than(ten: str) -> str:
    """Thân hàm, ĐÃ BỎ docstring — xem lý do ở cuối phần mô tả tệp."""
    node = _ham(ten)
    lenh = node.body
    if (lenh and isinstance(lenh[0], ast.Expr)
            and isinstance(lenh[0].value, ast.Constant)
            and isinstance(lenh[0].value.value, str)):
        lenh = lenh[1:]
    return "\n".join(ast.unparse(x) for x in lenh)


# ---------------------------------------------------------------
#  Bẫy 1 — không để hai tunnel cùng sống
# ---------------------------------------------------------------

def test_giet_tunnel_cu_TRUOC_khi_bat_cai_moi():
    than = _than("main")
    i_giet = than.find("_giet_tunnel_cu")
    i_bat = than.find("Popen")
    assert i_giet != -1, "main không tắt tunnel cũ"
    assert i_bat != -1, "main không bật tunnel nào"
    assert i_giet < i_bat, "tắt tunnel cũ SAU khi bật cái mới là tắt luôn cái mới"


def test_giet_ca_hai_he_dieu_hanh():
    than = _than("_giet_tunnel_cu")
    assert "taskkill" in than, "thiếu nhánh Windows"
    assert "pkill" in than, "thiếu nhánh Linux/macOS"


# ---------------------------------------------------------------
#  Bẫy 2 — ép IPv4
# ---------------------------------------------------------------

def test_ep_IPv4_khi_goi_cloudflared():
    """
    Bỏ cờ này là log lại đầy `ERR ... ip=2606:4700:...` và tunnel rớt liên
    tục — người dùng đã gửi ảnh chụp đúng màn hình đó.
    """
    than = _than("main")
    assert "'--edge-ip-version'" in than and "'4'" in than, (
        "không ép IPv4 — tunnel sẽ rớt trên mạng không đi được IPv6"
    )


# ---------------------------------------------------------------
#  Bẫy 3 — .env phải theo kịp tên miền mới
# ---------------------------------------------------------------

def test_cap_nhat_ca_HAI_bien_moi_truong():
    """
    Sửa một quên một thì dashboard dựng nửa URL đúng nửa URL sai, và cái
    sai không kêu lên bao giờ.
    """
    than = _than("_doi_env")
    for bien in ("PUBLIC_BASE_URL", "WEBHOOK_PUBLIC_URL"):
        assert bien in than, f"_doi_env không cập nhật {bien}"


def test_chi_ghi_env_KHI_da_thong_that():
    """
    Ghi `.env` trước khi kiểm là ghi vào đó một tên miền có thể chết ngay —
    tức tự tay tạo lại đúng cái bẫy số 3.
    """
    than = _than("main")
    i_do = than.find("_thong(")
    i_ghi = than.find("_doi_env(")
    assert i_do != -1 and i_ghi != -1
    assert i_do < i_ghi, "ghi .env trước khi đo được là thông"


# ---------------------------------------------------------------
#  Phép đo phải KIÊN NHẪN
# ---------------------------------------------------------------

def test_do_theo_CUA_SO_THOI_GIAN_chu_khong_theo_so_lan():
    """
    Bản đầu thử 4 lượt cách nhau 2 giây, bắt đầu ngay khi có tên miền. Mạng
    biên Cloudflare cần thêm 20–30 giây nữa mới định tuyến tới, nên lượt nào
    cũng trượt và script kết luận "không thông" cho một tunnel khoẻ mạnh —
    rồi BỎ QUA bước ghi `.env`, để lại đúng cái bẫy số 3.

    Đo được: lượt 1 trượt, lượt 2–4 đều 200.
    """
    node = _ham("_thong")
    mac_dinh = {
        a.arg: d for a, d in zip(
            node.args.args[-len(node.args.defaults):], node.args.defaults,
            strict=True,  # dung do dai theo dinh nghia cua lat cat
        )
    } if node.args.defaults else {}
    assert "han_giay" in mac_dinh, (
        "_thong phải nhận hạn THỜI GIAN, không phải số lần thử"
    )
    han = mac_dinh["han_giay"].value
    assert han >= 45, (
        f"hạn {han}s quá ngắn — tunnel cần 20–30 giây mới định tuyến được"
    )


def test_XOA_DEM_DNS_trong_moi_luot_do():
    """
    Kiên nhẫn thôi KHÔNG cứu được, và đây là chỗ bản thứ hai vẫn sai.

    Tên miền `trycloudflare` vừa cấp xong nên lượt hỏi DNS đầu trả về
    "không có tên miền này", và Windows GHI NHỚ câu trả lời phủ định đó.
    Mọi lượt sau đọc lại bộ nhớ đệm chứ không hỏi ra ngoài nữa — chờ 60
    giây hay 600 giây đều y hệt.

    Đo được: `curl` trượt ở 0,003 giây với mã 6 ("không phân giải được"),
    trong khi `nslookup` cùng lúc trả về đủ bốn địa chỉ. Xoá đệm xong thì
    4/4 lượt đều 200.
    """
    than = _than("_thong")
    assert "_xoa_dem_dns()" in than, (
        "không xoá đệm DNS — mọi lượt đo sau lượt đầu chỉ đọc lại câu trả "
        "lời phủ định đã lưu, và kiên nhẫn thành vô nghĩa"
    )


def test_xoa_dem_DNS_hong_thi_KHONG_lam_chet_script():
    """
    `ipconfig /flushdns` là lệnh phụ trợ. Để nó ném ra là đánh đổi một phép
    đo kém nhạy lấy việc hỏng cả bước bật tunnel.
    """
    than = _than("_xoa_dem_dns")
    assert "except" in than, "không bọc lỗi — lệnh phụ trợ hỏng sẽ giết script"


def test_bao_hong_thi_KHONG_ghi_env():
    """
    Nếu thật sự không thông, ghi `.env` là ghi một tên miền chết đè lên một
    tên miền có thể vẫn đang sống.
    """
    than = _than("main")
    i_do = than.find("_thong(")
    khuc = than[i_do:than.find("_doi_env(")]
    assert "return 1" in khuc, "không có đường thoát khi tunnel không thông"


# ---------------------------------------------------------------
#  Không được im lặng về việc tên miền sẽ đổi lại
# ---------------------------------------------------------------

def test_nhac_dan_lai_webhook():
    """
    `trycloudflare` cấp tên miền mới mỗi lần chạy. Không nhắc thì lần sau
    người ta bật tunnel, thấy "xong", và không hiểu vì sao Zalo im bặt —
    vì không nền tảng nào báo rằng nó đã ngừng gọi được.
    """
    than = _than("main")
    assert "webhook" in than.lower() and "Console" in than, (
        "không nhắc dán lại URL webhook sau khi tên miền đổi"
    )
