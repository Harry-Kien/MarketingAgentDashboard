"""
Form plugin trên dashboard: người không kỹ thuật điền được, không gõ JSON.

BỐN THỨ ĐƯỢC CANH
-----------------
1. Không còn ô JSON. Mỗi loại plugin có ô cấu hình riêng bằng tiếng Việt,
   và danh sách ô ấy phải KHỚP `LOAI_PLUGIN` — thêm loại thứ năm mà quên
   form thì test đỏ, không phải người dùng phát hiện.
2. Tên gõ tiếng Việt có dấu, mã máy tự sinh và phải qua đúng biểu thức
   `_TEN_RE` mà máy chủ dùng. Sinh sai là lưu bị từ chối với một thông
   điệp về "chữ thường không dấu" — đúng thứ form này sinh ra để giấu đi.
3. Mẫu có sẵn phải qua `doc_ban_mo_ta` thật. Mẫu là thứ người vận hành SỬA
   chứ không VIẾT, nên mẫu sai là cái bẫy được nhân bản.
4. Chạy thử không dùng `prompt()` của trình duyệt, và kết quả hiện thành
   câu tiếng Việt qua `esc()` — dữ liệu bảng là do người vận hành gõ, vẫn
   là chuỗi đi vào innerHTML.

VÌ SAO CHẠY JS BẰNG NODE
------------------------
Hàm sinh mã và hàm đọc bảng dán là logic thuần, không chạm DOM. Cắt đúng
thân hàm ra rồi chạy bằng node thì test kiểm HÀNH VI thật thay vì đếm
chuỗi trong mã. Node là yêu cầu sẵn của dự án (sidecar Zalo), nên thiếu
node là môi trường hỏng, không phải lý do để bỏ qua test.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.ban_mo_ta import _TEN_RE, LOAI_PLUGIN, doc_ban_mo_ta  # noqa: E402

HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
JS = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def _form_plugin() -> str:
    m = re.search(r'<form id="pluginform".*?</form>', HTML, re.S)
    assert m, "không thấy form plugin"
    return m.group(0)


def _than_ham(ten: str) -> str:
    m = re.search(r"(?:async )?function " + ten + r"\(.*?\n\}\n", JS, re.S)
    assert m, f"không thấy hàm {ten}"
    return m.group(0)


def _hang_so(ten: str) -> str:
    m = re.search(r"const " + ten + r" = \{.*?\n\};\n", JS, re.S)
    assert m, f"không thấy hằng {ten}"
    return m.group(0)


def _node(ma: str) -> str:
    node = shutil.which("node")
    assert node, "cần node trên PATH — dự án đã yêu cầu Node 22+ cho sidecar"
    r = subprocess.run([node, "-e", ma], capture_output=True, text=True,
                       encoding="utf-8", timeout=20)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


# --- 1. Không còn JSON, mỗi loại một ô riêng ----------------------------

def test_form_khong_con_o_json():
    form = _form_plugin()
    assert 'name="cau_hinh"' not in form
    assert "JSON" not in form


def test_moi_loai_plugin_co_o_cau_hinh_rieng():
    form = _form_plugin()
    co = set(re.findall(r'data-cauhinh="([^"]+)"', form))
    assert co == set(LOAI_PLUGIN), (
        f"form có {sorted(co)}, máy chủ có {sorted(LOAI_PLUGIN)} — "
        "thêm loại plugin thì phải thêm ô cấu hình cho nó"
    )


def test_docFormPlugin_khong_parse_json():
    assert "JSON.parse" not in _than_ham("docFormPlugin")


# --- 2. Tên tiếng Việt → mã máy hợp lệ -----------------------------------

@pytest.mark.parametrize("nhan, mong", [
    ("Tra bảo hành theo dòng", "tra_bao_hanh_theo_dong"),
    ("Đổi trả 30 ngày", "doi_tra_30_ngay"),
    ("  Địa chỉ & giờ mở cửa  ", "dia_chi_gio_mo_cua"),
])
def test_sinh_ma_tu_tieng_viet(nhan, mong):
    ra = _node(_than_ham("sinhMaPlugin")
               + f"process.stdout.write(sinhMaPlugin({json.dumps(nhan)}))")
    assert ra == mong
    assert _TEN_RE.match(ra)


def test_o_ten_rong_thi_khong_hien_ma_bia():
    """
    Lỗi thấy khi chụp màn hình: ô tên còn trống mà dòng dưới đã hiện
    "Mã máy: kn_x". `sinhMaPlugin("")` phải trả một mã hợp lệ vì máy chủ
    đòi thế, nhưng đem mã ấy hiện ra thì người vận hành đọc được một cái
    tên họ chưa hề đặt, và tưởng hệ thống đã quyết hộ.
    """
    src = _than_ham("capNhatMaPlugin")
    assert "—" in src or "trim()" in src,         "mã máy hiện vô điều kiện, kể cả khi ô tên còn trống"


@pytest.mark.parametrize("nhan", ["123 lý do", "", "!!!", "x" * 80])
def test_ma_sinh_ra_luon_qua_bo_kiem_may_chu(nhan):
    ra = _node(_than_ham("sinhMaPlugin")
               + f"process.stdout.write(sinhMaPlugin({json.dumps(nhan)}))")
    assert _TEN_RE.match(ra), f"{nhan!r} → {ra!r} không qua _TEN_RE"


# --- 3. Mẫu có sẵn phải qua bộ kiểm thật ---------------------------------

def _mau() -> dict:
    ra = _node(_hang_so("PLUGIN_MAU") + "process.stdout.write(JSON.stringify(PLUGIN_MAU))")
    return json.loads(ra)


def test_co_it_nhat_ba_mau():
    assert len(_mau()) >= 3


def test_moi_mau_qua_doc_ban_mo_ta():
    for ma, m in _mau().items():
        assert m.get("nhan"), f"mẫu {ma} thiếu nhãn tiếng Việt"
        bm = doc_ban_mo_ta({k: v for k, v in m.items() if k != "nhan"})
        assert bm.loai in LOAI_PLUGIN


# --- 4. Chạy thử và kết quả -------------------------------------------------

def test_chay_thu_khong_dung_prompt_trinh_duyet():
    i = JS.index("kỹ năng (skill) và plugin")
    j = JS.find("\n/* ----------------", i + 1)
    doan = JS[i:j if j > 0 else len(JS)]
    assert "prompt(" not in doan


def test_ket_qua_thu_hien_tieng_viet_qua_esc():
    src = _than_ham("hienKetQuaThu")
    assert "esc(" in src
    assert "${r." not in src, "chuỗi máy chủ nội suy trần vào innerHTML"
    assert "Tìm thấy" in src or "tìm thấy" in src


def test_bang_dan_tu_excel():
    ma = _than_ham("docBangDan") + (
        'process.stdout.write(JSON.stringify(docBangDan('
        '"Kem chống nắng\\t12 tháng\\nSữa rửa mặt: 6 tháng\\n\\n   \\nToner | 9 tháng")))'
    )
    assert json.loads(_node(ma)) == [
        ["Kem chống nắng", "12 tháng"],
        ["Sữa rửa mặt", "6 tháng"],
        ["Toner", "9 tháng"],
    ]


def test_danh_sach_plugin_hien_ten_loai_tieng_viet():
    src = _than_ham("gopKyNang")
    assert "esc(p.loai)" not in src, "loại hiện mã máy (tra_bang) thay vì tên tiếng Việt"
    assert "PLUGIN_LOAI[" in src
