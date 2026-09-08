"""
Plugin rời có lịch sử và khôi phục — như gói kỹ năng vốn đã có.

VÌ SAO CHỖ NÀY MỚI ĐAU
----------------------
Gói kỹ năng giữ mười bản cũ và lùi được bằng một nút. Plugin rời thì
không: sửa bảng phí ship, phát hiện sai, bản cũ đã mất, gõ lại từ đầu.

Bất đối xứng ấy ngược với thực tế dùng. Gói viết một lần rồi để đó; plugin
rời là thứ người vận hành sửa hằng tuần — và từ đợt trước còn có nút "thêm
khoá khách hay hỏi" mời họ sửa thường xuyên hơn nữa. Càng dễ sửa thì càng
cần đường lùi.

VÌ SAO GHI BẢN CŨ CHỨ KHÔNG GHI BẢN MỚI
---------------------------------------
Ghi vào lịch sử ngay TRƯỚC khi đè, nên hàng cuối cùng của lịch sử là bản
vừa bị thay, không phải bản đang chạy. Ghi bản mới thì lịch sử trùng lặp
với `ky_nang_cai_dat` và không lùi được một bước nào cả.

VÌ SAO KHÔNG GHI KHI TẠO MỚI
----------------------------
Tạo mới không đè lên gì. Ghi một hàng rỗng ở đó là mời người ta "khôi
phục" về trạng thái không tồn tại.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.ban_mo_ta import LoiBanMoTa  # noqa: E402


def chay(coro):
    return asyncio.run(coro)


BANG_CU = {"Hà Nội": "Phí 35.000đ"}
BANG_MOI = {"Hà Nội": "Phí 30.000đ", "Đà Nẵng": "Phí 28.000đ"}


def _tho(bang: dict) -> dict:
    return {
        "ten": "tra_phi_ship",
        "loai": "tra_bang",
        "mo_ta": "Tra phí giao hàng theo tỉnh thành. Không dùng cho câu hỏi tình trạng đơn.",
        "tham_so": [{"ten": "khoa", "mo_ta": "Tỉnh hoặc thành phố khách ở"}],
        "cau_hinh": {"bang": bang},
    }


@pytest.fixture
def kho(monkeypatch):
    """CSDL giả: một bảng cài đặt và một bảng lịch sử, đủ cho cả hai đường."""
    from agent import db
    from agent.ky_nang import goi as g, kho_ky_nang

    cai_dat: dict[str, dict] = {}
    lich_su: list[dict] = []
    dem_id = {"n": 0}

    async def execute(sql, *a):
        s = " ".join(sql.split())
        if s.startswith("INSERT INTO ky_nang_lich_su"):
            dem_id["n"] += 1
            lich_su.append({"id": dem_id["n"], "ten": a[0], "noi_dung": a[1],
                            "thay_boi": a[2], "thay_luc": f"t{dem_id['n']}"})
        elif s.startswith("INSERT INTO ky_nang_cai_dat"):
            cai_dat[a[0]] = {"ten": a[0], "ban_mo_ta": a[1], "goi": None, "bat": True}
        elif s.startswith("DELETE FROM ky_nang_lich_su"):
            giu = {x["id"] for x in sorted(
                [y for y in lich_su if y["ten"] == a[0]],
                key=lambda y: y["id"], reverse=True)[:10]}
            lich_su[:] = [x for x in lich_su if x["ten"] != a[0] or x["id"] in giu]
        return "OK"

    async def fetchrow(sql, *a):
        s = " ".join(sql.split())
        if "FROM ky_nang_lich_su" in s:
            return next((x for x in lich_su if x["id"] == a[0] and x["ten"] == a[1]), None)
        if "SELECT goi FROM ky_nang_cai_dat" in s or "ban_mo_ta, goi FROM ky_nang_cai_dat" in s:
            return cai_dat.get(a[0])
        return None

    async def fetch(sql, *a):
        s = " ".join(sql.split())
        if "FROM ky_nang_lich_su" in s:
            hang = sorted([x for x in lich_su if x["ten"] == a[0]],
                          key=lambda y: y["id"], reverse=True)[:10]
            # Trả ĐÚNG những cột câu SQL xin. CSDL giả rộng tay hơn CSDL
            # thật là chỗ test xanh trên thứ Postgres sẽ không bao giờ đưa
            # về — và cũng là chỗ nó bỏ lỡ việc mã đang xin dư cột.
            cot = [c.strip() for c in s[s.index("SELECT") + 6:s.index(" FROM")].split(",")]
            return [{c: x[c] for c in cot if c in x} for x in hang]
        if "ky_nang_cai_dat" in s:
            return list(cai_dat.values())
        return []

    monkeypatch.setattr(db, "execute", execute)
    monkeypatch.setattr(db, "fetchrow", fetchrow)
    monkeypatch.setattr(db, "fetch", fetch)
    monkeypatch.setattr(db, "log_event", lambda *a, **k: asyncio.sleep(0))

    async def khong_dem():
        return {}

    monkeypatch.setattr(g, "dem_goi_7_ngay", khong_dem)
    kho_ky_nang.xoa_dem()
    yield kho_ky_nang, cai_dat, lich_su
    kho_ky_nang.xoa_dem()


# --- Ghi lịch sử ------------------------------------------------------

def test_tao_moi_khong_ghi_lich_su(kho):
    """Tạo mới không đè lên gì. Một hàng rỗng ở đây là mời người ta khôi
    phục về trạng thái không tồn tại."""
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    assert lich_su == []


def test_sua_thi_ghi_BAN_CU_vao_lich_su(kho):
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="admin"))
    assert len(lich_su) == 1
    assert lich_su[0]["noi_dung"]["cau_hinh"]["bang"] == BANG_CU, \
        "lịch sử giữ bản MỚI thì không lùi được bước nào"


def test_lich_su_ghi_ai_sua(kho):
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="nhan_vien_a"))
    assert lich_su[0]["thay_boi"] == "nhan_vien_a"


def test_giu_toi_da_muoi_ban(kho):
    """Cùng trần với gói. Không cắt thì bảng phình mãi vì mỗi lần bấm nút
    'thêm khoá khách hay hỏi' là một bản nữa."""
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    for i in range(12):
        kn.xoa_dem()
        chay(kn.luu_plugin(_tho({"Hà Nội": f"Phí {i}đ"}), boi="admin"))
    assert len([x for x in lich_su if x["ten"] == "tra_phi_ship"]) <= 10


# --- Đọc và khôi phục -------------------------------------------------

def test_lich_su_moi_nhat_dung_dau(kho):
    kn, _, _ = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho({"Huế": "Phí 30.000đ"}), boi="admin"))
    ds = chay(kn.lich_su_plugin("tra_phi_ship"))
    assert len(ds) == 2
    assert ds[0]["id"] > ds[1]["id"]
    # Không trả cả `noi_dung`: danh sách chỉ để chọn, và cấu hình đầy đủ
    # của mười bản cũ là một khối chữ lớn đi qua mạng mỗi lần mở màn.
    assert "noi_dung" not in ds[0]


def test_khoi_phuc_dua_ban_cu_tro_lai(kho):
    kn, cai_dat, _ = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="admin"))
    kn.xoa_dem()
    ds = chay(kn.lich_su_plugin("tra_phi_ship"))
    chay(kn.khoi_phuc_plugin("tra_phi_ship", ds[0]["id"], boi="admin"))
    assert cai_dat["tra_phi_ship"]["ban_mo_ta"]["cau_hinh"]["bang"] == BANG_CU


def test_khoi_phuc_cung_di_qua_bo_kiem(kho):
    """
    Khôi phục KHÔNG được là đường vòng qua `doc_ban_mo_ta`. Một bản cũ có
    thể không còn hợp lệ theo luật thêm sau này — ví dụ khoá lồng nhau, cấm
    từ ngày có `khoa_long_nhau`. Cài đè nó lặng lẽ là mở lại đúng lỗ hổng
    mà luật ấy sinh ra để bịt.
    """
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="admin"))
    # Bẻ bản cũ thành thứ bộ kiểm phải từ chối.
    lich_su[0]["noi_dung"]["cau_hinh"]["bang"] = {"serum": "A", "serum dưỡng tóc": "B"}
    kn.xoa_dem()
    with pytest.raises(LoiBanMoTa):
        chay(kn.khoi_phuc_plugin("tra_phi_ship", lich_su[0]["id"], boi="admin"))


def test_khoi_phuc_ban_khong_co_thi_bao_ro(kho):
    kn, _, _ = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    with pytest.raises(LookupError):
        chay(kn.khoi_phuc_plugin("tra_phi_ship", 9999, boi="admin"))


def test_khoi_phuc_chinh_no_ghi_lich_su_them_mot_ban(kho):
    """Khôi phục cũng là một lần đè — bản đang chạy phải vào lịch sử, để
    lùi được cả cú lùi."""
    kn, _, lich_su = kho
    chay(kn.luu_plugin(_tho(BANG_CU), boi="admin"))
    kn.xoa_dem()
    chay(kn.luu_plugin(_tho(BANG_MOI), boi="admin"))
    kn.xoa_dem()
    truoc = len(lich_su)
    ds = chay(kn.lich_su_plugin("tra_phi_ship"))
    chay(kn.khoi_phuc_plugin("tra_phi_ship", ds[0]["id"], boi="admin"))
    assert len(lich_su) == truoc + 1
    assert lich_su[-1]["noi_dung"]["cau_hinh"]["bang"] == BANG_MOI


# --- Giao diện --------------------------------------------------------

def test_dashboard_co_nut_lich_su():
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    assert "data-plugin-lichsu" in js, "không có nút Lịch sử"
    assert "data-plugin-khoiphuc" in js, "không có nút Khôi phục"


def test_nhanh_khoi_phuc_dung_dung_bien_cua_no():
    """
    LỖI THẬT, và một lỗi mà `node --check` không thấy.

    Đổi tên biến bằng thay-chuỗi để lại `if (bk)` trong khối `bkp`. `bk` là
    biến của nhánh TRƯỚC (nút "thêm khoá khách hay hỏi"), luôn null tại đó,
    nên nút Khôi phục bấm không ăn gì — không lỗi, không dấu vết, đúng kiểu
    hỏng im lặng. Cú pháp vẫn hợp lệ vì `bk` có thật trong scope.

    Phép kiểm: trong thân mỗi nhánh, mọi tham chiếu `.dataset` phải dùng
    ĐÚNG biến vừa khai ở đầu nhánh ấy.
    """
    import re

    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    for bien, thuoc_tinh in (("bkp", "data-plugin-khoiphuc"),
                             ("bl", "data-plugin-lichsu"),
                             ("bs", "data-plugin-sua")):
        khai = f'const {bien} = e.target.closest("[{thuoc_tinh}]");'
        i = js.index(khai) + len(khai)
        than = js[i:js.index("\n  }\n", i)]
        m = re.match(r"\s*if \((\w+)\) \{", than)
        assert m, f"không thấy nhánh {bien}"
        assert m.group(1) == bien, (
            f"nhánh {bien} kiểm biến {m.group(1)!r} — biến của nhánh khác, "
            "luôn rỗng ở đây nên nút bấm không ăn gì"
        )
        khac = set(re.findall(r"(b[a-z]{1,3})\.dataset", than)) - {bien}
        assert not khac, f"nhánh {bien} còn đọc dataset của {khac}"


def test_nut_lich_su_chi_cho_plugin_sua_duoc():
    """Công cụ của gói và của MCP sửa ở nguồn của nó; nút Lịch sử ở đây chỉ
    dẫn tới một API luôn trả rỗng."""
    import re

    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    m = re.search(r"function veDongKyNang\(.*?\n\}\n", js, re.S)
    assert m
    src = m.group(0)
    assert src.index('nguon === "tu_tao"') < src.index("data-plugin-lichsu")
