"""
Ứng dụng nhúng do người vận hành đăng ký.

RÀO ĐỊA CHỈ Ở ĐÂY LÀ ẢNH GƯƠNG CỦA RÀO TRONG `agent/ky_nang/mang.py`:

    Plugin `goi_api_doc`  MODEL chọn URL  → CHẶN dải mạng nội bộ
    Proxy nhúng           NGƯỜI chọn URL  → BẮT BUỘC dải mạng nội bộ

Cho phép địa chỉ CÔNG KHAI ở đây là biến dashboard thành máy chuyển tiếp
mở: ai có phiên đăng nhập đều gửi được request ra Internet mang danh máy
chủ này, và log của bên nhận chỉ thấy IP của cửa hàng.

Ca quan trọng nhất: `test_dia_chi_cong_khai_bi_chan` và
`test_ten_van_phai_tra_trong_danh_sach_trang`.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.api import tich_hop_kho as kho  # noqa: E402
from agent.api.tich_hop_kho import LoiUngDung, kiem_dia_chi, kiem_ten  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _sach():
    kho.xoa_dem()
    yield
    kho.xoa_dem()


# ---------------------------------------------------------------
#  Rào địa chỉ
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "dia_chi",
    ["http://127.0.0.1:3000", "http://localhost:9090", "http://10.0.0.5:8080",
     "http://192.168.1.20:3001", "https://172.16.5.5:8443"],
)
def test_dia_chi_noi_bo_duoc_chap_nhan(dia_chi):
    assert kiem_dia_chi(dia_chi) == dia_chi.rstrip("/")


def test_dia_chi_cong_khai_bi_chan(monkeypatch):
    """
    Ca quan trọng nhất tệp này. Cho phép địa chỉ công khai là biến dashboard
    thành máy chuyển tiếp mở.
    """
    monkeypatch.setattr(
        kho.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    with pytest.raises(LoiUngDung, match="CÔNG KHAI"):
        kiem_dia_chi("https://example.com")


def test_ten_mien_noi_bo_tro_ra_ip_cong_khai_van_bi_chan(monkeypatch):
    """
    Kiểm theo TÊN là kiểm nhầm chỗ: `noi-bo.cua-hang.vn` hoàn toàn có thể
    phân giải ra một IP công khai. Phải xét SAU khi tra DNS.
    """
    monkeypatch.setattr(
        kho.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("8.8.8.8", 80))],
    )
    with pytest.raises(LoiUngDung, match="CÔNG KHAI"):
        kiem_dia_chi("http://noi-bo.cua-hang.vn")


def test_mot_trong_nhieu_ban_ghi_DNS_la_cong_khai_thi_van_chan(monkeypatch):
    """
    Một host có thể phân giải ra nhiều IP. Chỉ cần MỘT cái công khai là đủ
    để lách — nên phải xét hết, không dừng ở cái đầu tiên hợp lệ.
    """
    monkeypatch.setattr(
        kho.socket, "getaddrinfo",
        lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 80)),
                         (2, 1, 6, "", ("93.184.216.34", 80))],
    )
    with pytest.raises(LoiUngDung, match="CÔNG KHAI"):
        kiem_dia_chi("http://hai-mat.test")


@pytest.mark.parametrize(
    "dia_chi",
    ["ftp://127.0.0.1", "file:///etc/passwd", "127.0.0.1:3000", "javascript:x"],
)
def test_giao_thuc_sai_bi_chan(dia_chi):
    with pytest.raises(LoiUngDung):
        kiem_dia_chi(dia_chi)


def test_dia_chi_kem_duong_dan_bi_chan():
    """
    Chỉ nhận địa chỉ GỐC. Cho kèm đường dẫn thì việc ghép URL trong proxy
    sinh ra `//` hoặc mất đoạn, và lỗi ấy chỉ lộ ra ở vài trang con.
    """
    with pytest.raises(LoiUngDung, match="GỐC"):
        kiem_dia_chi("http://127.0.0.1:3000/dashboard/abc")


def test_dia_chi_rong_bi_chan():
    with pytest.raises(LoiUngDung, match="Thiếu"):
        kiem_dia_chi("")


def test_dns_khong_tra_duoc_thi_bao_ro(monkeypatch):
    def no(*a, **k):
        raise OSError("Name or service not known")

    monkeypatch.setattr(kho.socket, "getaddrinfo", no)
    with pytest.raises(LoiUngDung, match="DNS"):
        kiem_dia_chi("http://khong-co-that.test")


# ---------------------------------------------------------------
#  Rào tên
# ---------------------------------------------------------------

@pytest.mark.parametrize("ten", ["grafana", "uptime-kuma", "metabase", "n8n-2"])
def test_ten_hop_le(ten):
    assert kiem_ten(ten) == ten


@pytest.mark.parametrize(
    "ten",
    ["", "a", "gra fana", "grafana/", "../etc", "gráfana",
     "1grafana", "-grafana", "x" * 32],
)
def test_ten_sai_bi_chan(ten):
    with pytest.raises(LoiUngDung):
        kiem_ten(ten)


def test_ten_duoc_ha_chu_thuong():
    """
    Nhận `Grafana` và chuẩn hoá thành `grafana` thay vì từ chối: tên đi vào
    đường dẫn nên phải một dạng duy nhất, nhưng bắt người vận hành tự nhớ
    gõ chữ thường là một lỗi họ sẽ mắc rồi không hiểu vì sao bị từ chối.
    """
    assert kiem_ten("Grafana") == "grafana"
    assert kiem_ten("  UPTIME-Kuma  ") == "uptime-kuma"


@pytest.mark.parametrize("ten", sorted(kho.MAC_DINH))
def test_khong_ghi_de_duoc_app_viet_san(ten):
    """
    Ghi đè `chatwoot` bằng một địa chỉ khác là chiếm luôn đường proxy của
    nó — mọi request của người đang dùng Chatwoot đi sang chỗ mới.
    """
    with pytest.raises(LoiUngDung, match="viết sẵn"):
        kiem_ten(ten)


def test_khong_xoa_duoc_app_viet_san():
    for ten in kho.MAC_DINH:
        with pytest.raises(LoiUngDung, match="viết sẵn"):
            chay(kho.xoa(ten))


# ---------------------------------------------------------------
#  Danh sách trắng vẫn còn tác dụng
# ---------------------------------------------------------------

def test_ten_van_phai_tra_trong_danh_sach_trang(monkeypatch):
    """
    Chuyển danh sách xuống CSDL KHÔNG được làm mất tính chất chống SSRF:
    tên lấy từ URL vẫn phải tra trong danh sách, không bao giờ ghép thẳng
    vào địa chỉ đích.
    """
    from agent.api import tich_hop

    async def khong_co_gi():
        return {}

    monkeypatch.setattr(kho, "_doc", khong_co_gi)
    hop_le = chay(kho.ten_hop_le())
    assert "evil.com" not in hop_le
    assert set(kho.MAC_DINH) <= hop_le

    # Và `_dich` phải 404 chứ không đoán.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        chay(tich_hop._dich("evil.com"))
    assert e.value.status_code == 404


def test_referer_tro_ra_ngoai_khong_duoc_proxy(monkeypatch):
    """
    `ung_dung_tu_referer` là đường đi VÒNG vào proxy. Referer của một trang
    lạ không được biến thành một lượt chuyển tiếp.
    """
    from agent.api import tich_hop

    async def khong_co_gi():
        return {}

    monkeypatch.setattr(kho, "_doc", khong_co_gi)
    for ref in ["", "https://evil.com/", "http://localhost:8000/",
                "http://localhost:8000/tich-hop/evil.com/x"]:
        assert chay(tich_hop.ung_dung_tu_referer(ref)) is None


def test_referer_dung_app_thi_nhan_ra(monkeypatch):
    from agent.api import tich_hop

    async def co_n8n():
        return {}

    monkeypatch.setattr(kho, "_doc", co_n8n)
    assert chay(
        tich_hop.ung_dung_tu_referer("http://localhost:8000/tich-hop/n8n/home")
    ) == "n8n"


def test_app_tu_them_duoc_proxy_nhan(monkeypatch):
    async def co_grafana():
        return {"grafana": {"nhan": "Grafana", "dia_chi": "http://127.0.0.1:3000"}}

    monkeypatch.setattr(kho, "_doc", co_grafana)
    assert "grafana" in chay(kho.ten_hop_le())
    assert chay(kho.dia_chi_cua("grafana")) == "http://127.0.0.1:3000"


def test_khong_co_csdl_thi_van_con_bon_app_viet_san(monkeypatch):
    """
    Máy vừa clone chưa migrate vẫn phải nhúng được n8n. Rơi về "chỉ có app
    viết sẵn" chứ không phải nổ.
    """
    async def no(*a, **k):
        raise RuntimeError("chưa có CSDL")

    monkeypatch.setattr(kho.db, "fetch", no)
    kho.xoa_dem()
    assert chay(kho.ten_hop_le()) == frozenset(kho.MAC_DINH)


def test_liet_ke_danh_dau_app_nao_xoa_duoc(monkeypatch):
    async def co():
        return {"grafana": {"nhan": "Grafana", "dia_chi": "http://127.0.0.1:3000"}}

    monkeypatch.setattr(kho, "_doc", co)
    d = chay(kho.liet_ke())
    assert all(x["xoa_duoc"] is False for x in d["mac_dinh"])
    assert all(x["xoa_duoc"] is True for x in d["tu_them"])
    assert len(d["mac_dinh"]) == len(kho.MAC_DINH)
