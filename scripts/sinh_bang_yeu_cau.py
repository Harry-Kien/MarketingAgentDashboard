"""
Sinh `docs/yeu-cau-chuc-nang.md` — bảng đối chiếu yêu cầu (mục 21 bảng
"Check list công việc" của chủ dự án).

    python -m scripts.sinh_bang_yeu_cau          # in ra, không ghi
    python -m scripts.sinh_bang_yeu_cau --ghi    # ghi vào docs/

PHẦN NÀO VIẾT TAY, PHẦN NÀO SINH RA
----------------------------------
Viết tay (dữ liệu ở cuối tệp này): yêu cầu nào hiện thực ở đâu, test nào
canh, trạng thái, chỗ lệch bảng và câu hỏi mở. Đó là PHÁN ĐOÁN — máy không
tự biết "thanh thông tin hội thoại" là tệp nào.

Sinh ra, và KIỂM mỗi lần sinh:
  - mọi đường dẫn mã nêu tên phải tồn tại;
  - mọi test nêu tên (`tệp::hàm`) phải có trong tệp ấy — đọc bằng `ast`;
  - mọi route API nêu tên phải có trên `agent.main.app` thật, và quyền in
    cạnh route lấy từ chính `Depends(can_quyen(...))` của nó;
  - mọi màn/tab nêu tên phải có `data-view`/`data-tab` trong index.html;
  - mọi kịch bản nghiệm thu nêu tên phải có trong `docs/nghiem-thu.md`, và
    kết quả in ra lấy từ bảng ấy (bảng ấy lại sinh từ lượt chạy thật);
  - mọi con số (số quyền, số migration, số test, số kênh...) đếm từ mã.

Một tham chiếu chết là bảng NÓI DỐI: ghi "Đạt, test X canh" trong khi X đã
bị đổi tên hay xoá từ lâu. Đó là xanh giả — loại hỏng repo này sợ nhất —
nên bộ sinh NỔ thay vì in bảng thiếu (`LoiThamChieu`).

Trạng thái MỤC suy từ trạng thái các yêu cầu con, không gõ tay: gõ tay là
chỗ người ta ghi "Đạt" cho cả mục khi một yêu cầu con còn dở. Kịch bản
nghiệm thu liên quan mà không "đạt" thì mục không thể "Đạt".

Bảng không in ngày giờ hay mã commit: cùng mã thì cùng tài liệu, để test
so được từng byte (`tests/test_bang_yeu_cau.py`).
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

for _luong in (sys.stdout, sys.stderr):
    if hasattr(_luong, "reconfigure"):
        _luong.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TEP_DOC = ROOT / "docs" / "yeu-cau-chuc-nang.md"
TEP_NGHIEM_THU = ROOT / "docs" / "nghiem-thu.md"
TEP_TEST_NGHIEM_THU = "tests/test_nghiem_thu_saas.py"
TEP_INDEX = ROOT / "dashboard" / "index.html"

DAT, MOT_PHAN, CHUA, NGOAI = "dat", "mot_phan", "chua", "ngoai"
NHAN_TRANG_THAI = {
    DAT: "Đạt",
    MOT_PHAN: "Đạt một phần",
    CHUA: "Chưa làm",
    NGOAI: "Ngoài phạm vi theo bảng",
}


class LoiThamChieu(RuntimeError):
    """Bảng nêu tên một thứ không có thật — không sinh tài liệu."""


# =====================================================================
#  Kiểu dữ liệu
# =====================================================================

@dataclass(frozen=True)
class YeuCau:
    """Một yêu cầu con. `bang` là số mục con trên bảng của chủ dự án, nếu
    bảng có đánh số và ta biết chắc số ấy — không đoán."""
    mo_ta: str
    trang_thai: str
    test: tuple[str, ...] = ()
    ghi_chu: str = ""
    bang: str = ""


@dataclass(frozen=True)
class Muc:
    so: int
    ten: str
    yeu_cau: tuple[YeuCau, ...]
    ma: tuple[str, ...] = ()
    api: tuple[str, ...] = ()
    giao_dien: tuple[str, ...] = ()
    nghiem_thu: tuple[str, ...] = ()
    lech: tuple[str, ...] = ()
    hoi: tuple[str, ...] = ()
    them: Callable[[], list[str]] | None = field(default=None, compare=False)


@dataclass(frozen=True)
class PhiChucNang:
    nhom: str
    yeu_cau: str
    dap_ung: str
    trang_thai: str
    test: tuple[str, ...] = ()
    ma: tuple[str, ...] = ()


@dataclass(frozen=True)
class HanChe:
    """`con_dung` (nếu có) đọc mã để xác nhận hạn chế VẪN còn — sửa xong mà
    quên gỡ khỏi bảng là bảng chê oan hệ thống, bộ sinh nổ."""
    ten: str
    mo_ta: str
    bang_chung: tuple[str, ...] = ()
    con_dung: Callable[[], bool] | None = field(default=None, compare=False)


# =====================================================================
#  Đọc sự thật từ repo
# =====================================================================

@lru_cache(maxsize=None)
def ham_test(tep: str) -> frozenset[str]:
    """Tên test trong một tệp: `ham` ở mức module, `Lop::ham` trong lớp."""
    p = ROOT / tep
    if not p.exists():
        return frozenset()
    with warnings.catch_warnings():
        # Vài tệp test có chuỗi regex thiếu tiền tố r — cảnh báo cú pháp của
        # CHÍNH tệp ấy, không phải việc của bộ đếm.
        warnings.simplefilter("ignore", SyntaxWarning)
        cay = ast.parse(p.read_text(encoding="utf-8"))
    ra: set[str] = set()
    for nut in cay.body:
        if isinstance(nut, (ast.FunctionDef, ast.AsyncFunctionDef)) and nut.name.startswith("test_"):
            ra.add(nut.name)
        elif isinstance(nut, ast.ClassDef) and nut.name.startswith("Test"):
            for con in nut.body:
                if isinstance(con, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and con.name.startswith("test_"):
                    ra.add(f"{nut.name}::{con.name}")
    return frozenset(ra)


def tach_test(ref: str) -> tuple[str, str]:
    tep, _, ten = ref.partition("::")
    return tep, ten


@lru_cache(maxsize=None)
def _route_quyen() -> dict[tuple[str, str], str]:
    """(PHƯƠNG THỨC, đường) -> quyền đọc từ dependency thật của route."""
    from agent.core.quyen import MIEN_TRU, moi_route
    from agent.main import app

    ra: dict[tuple[str, str], str] = {}
    for r in moi_route(app.routes):
        duong = getattr(r, "path", "")
        phu = getattr(getattr(r, "dependant", None), "dependencies", ())
        quyen: tuple[str, ...] = ()
        for x in phu:
            q = getattr(x.call, "quyen_yeu_cau", None)
            if q:
                quyen += tuple(q)
        for pt in sorted(getattr(r, "methods", None) or ()):
            if pt in {"HEAD", "OPTIONS"}:
                continue
            if quyen:
                ra[(pt, duong)] = " + ".join(f"`{q}`" for q in quyen)
            elif (pt, duong) in MIEN_TRU:
                ra[(pt, duong)] = "miễn trừ (đăng nhập hoặc chữ ký riêng)"
            else:
                ra[(pt, duong)] = "—"
    return ra


@lru_cache(maxsize=None)
def _html() -> str:
    return TEP_INDEX.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def ket_qua_nghiem_thu() -> dict[str, tuple[int, str, str]]:
    """tên test kịch bản -> (số, tiêu đề, kết quả) đọc từ docs/nghiem-thu.md."""
    if not TEP_NGHIEM_THU.exists():
        return {}
    md = TEP_NGHIEM_THU.read_text(encoding="utf-8")
    ra = {}
    for m in re.finditer(r"^## (\d+)\. (.+)\n\nKết quả: \*\*(.+?)\*\* · `(test_\w+)`", md, re.M):
        ra[m.group(4)] = (int(m.group(1)), m.group(2).strip(), m.group(3))
    return ra


def kiem_mot_test(ref: str) -> str | None:
    tep, ten = tach_test(ref)
    if not tep.startswith("tests/") or not ten:
        return f"test phải viết `tests/tep.py::ten`: {ref}"
    if not (ROOT / tep).exists():
        return f"tệp test không có: {tep}"
    if ten not in ham_test(tep):
        return f"test không có trong {tep}: {ten}"
    return None


def kiem_giao_dien(ref: str) -> str | None:
    loai, _, ten = ref.partition(":")
    if loai not in ("view", "tab"):
        return f"giao diện phải viết view:… hoặc tab:…: {ref}"
    if f'data-{loai}="{ten}"' not in _html():
        return f"index.html không có data-{loai}=\"{ten}\""
    return None


def kiem_api(ref: str) -> str | None:
    pt, _, duong = ref.partition(" ")
    if (pt, duong) not in _route_quyen():
        return f"route không có trên app thật: {ref}"
    return None


def kiem_muc(cac_muc: tuple[Muc, ...] | list[Muc]) -> list[str]:
    """Mọi lỗi tham chiếu của các mục chức năng. Rỗng = bảng nói thật."""
    loi: list[str] = []
    nt = ket_qua_nghiem_thu()
    for m in cac_muc:
        dau = f"mục {m.so}"
        for p in m.ma:
            if not (ROOT / p).exists():
                loi.append(f"{dau}: đường dẫn không có: {p}")
        for a in m.api:
            if (e := kiem_api(a)):
                loi.append(f"{dau}: {e}")
        for g in m.giao_dien:
            if (e := kiem_giao_dien(g)):
                loi.append(f"{dau}: {e}")
        for k in m.nghiem_thu:
            if k not in ham_test(TEP_TEST_NGHIEM_THU):
                loi.append(f"{dau}: kịch bản không có trong {TEP_TEST_NGHIEM_THU}: {k}")
            elif k not in nt:
                loi.append(f"{dau}: kịch bản chưa vào docs/nghiem-thu.md — "
                           f"sinh lại bằng scripts.sinh_nghiem_thu --ghi: {k}")
        if not m.yeu_cau:
            loi.append(f"{dau}: không có yêu cầu con nào")
        for y in m.yeu_cau:
            if y.trang_thai not in NHAN_TRANG_THAI:
                loi.append(f"{dau}: trạng thái lạ «{y.trang_thai}»: {y.mo_ta[:40]}")
            if y.trang_thai in (DAT, MOT_PHAN) and not y.test:
                # "Đạt" không có test canh là lời hứa — CLAUDE.md: ràng buộc
                # không có test thì sẽ bị gỡ trong một lần dọn dẹp.
                loi.append(f"{dau}: «{y.mo_ta[:50]}» ghi {NHAN_TRANG_THAI[y.trang_thai]} "
                           "mà không nêu test canh nào")
            for t in y.test:
                if (e := kiem_mot_test(t)):
                    loi.append(f"{dau}: {e}")
    return loi


def kiem_phi_chuc_nang(dong: tuple[PhiChucNang, ...] | list[PhiChucNang]) -> list[str]:
    loi: list[str] = []
    for d in dong:
        dau = f"phi chức năng «{d.yeu_cau[:40]}»"
        if d.trang_thai not in NHAN_TRANG_THAI:
            loi.append(f"{dau}: trạng thái lạ «{d.trang_thai}»")
        if d.trang_thai in (DAT, MOT_PHAN) and not d.test:
            loi.append(f"{dau}: ghi {NHAN_TRANG_THAI[d.trang_thai]} mà không nêu test canh nào")
        for t in d.test:
            if (e := kiem_mot_test(t)):
                loi.append(f"{dau}: {e}")
        for p in d.ma:
            if not (ROOT / p).exists():
                loi.append(f"{dau}: đường dẫn không có: {p}")
    return loi


def kiem_han_che(ds: tuple[HanChe, ...] | list[HanChe]) -> list[str]:
    loi = [f"hạn chế «{h.ten}»: đường dẫn không có: {p}"
           for h in ds for p in h.bang_chung if not (ROOT / p).exists()]
    loi += [f"hạn chế «{h.ten}» không còn đúng theo mã — gỡ khỏi bảng và sửa trạng thái liên quan"
            for h in ds if h.con_dung is not None and not h.con_dung()]
    return loi


def kiem_khong_co_route(cam: tuple[tuple[str, str], ...]) -> list[str]:
    """Route KHÔNG được tồn tại (vd. xoá nhân viên — bảng ghi: không xoá)."""
    return [f"route bị cấm theo bảng lại tồn tại: {pt} {duong}"
            for (pt, duong) in _route_quyen() for (pt_cam, dau) in cam
            if pt == pt_cam and duong.startswith(dau)]


# =====================================================================
#  Suy trạng thái
# =====================================================================

def trang_thai_muc(m: Muc) -> str:
    """
    Suy từ yêu cầu con (bỏ qua yêu cầu ngoài phạm vi), rồi hạ xuống "một
    phần" nếu có kịch bản nghiệm thu liên quan không đạt.
    """
    tinh = [y.trang_thai for y in m.yeu_cau if y.trang_thai != NGOAI]
    if not tinh:
        return NGOAI
    if all(t == DAT for t in tinh):
        tt = DAT
    elif all(t == CHUA for t in tinh):
        tt = CHUA
    else:
        tt = MOT_PHAN
    nt = ket_qua_nghiem_thu()
    if tt == DAT and any(nt.get(k, (0, "", "?"))[2] != "đạt" for k in m.nghiem_thu):
        tt = MOT_PHAN
    return tt


def _test_ngan(ref: str) -> str:
    tep, ten = tach_test(ref)
    return f"`{Path(tep).stem}::{ten}`"


def tep_test_cua(m: Muc) -> list[str]:
    tep = {tach_test(t)[0] for y in m.yeu_cau for t in y.test}
    return sorted(tep)


def dem_test(tep: list[str]) -> int:
    return sum(len(ham_test(t)) for t in tep)


@lru_cache(maxsize=None)
def tat_ca_tep_test() -> tuple[str, ...]:
    return tuple(sorted(p.relative_to(ROOT).as_posix()
                        for p in (ROOT / "tests").glob("test_*.py")))


# =====================================================================
#  Khối sinh từ mã (đính vào từng mục)
# =====================================================================

def _cay_menu() -> list[str]:
    html = _html()
    rail = html[html.index('id="rail"'):]
    rail = rail[:rail.index("</nav>")]
    chinh = re.findall(r'class="rail__item(?: is-active)?" data-view="(\w+)">.*?<span>([^<]+)</span>',
                       rail, re.S)
    con = re.findall(r'rail__item--con" data-view="(\w+)">.*?<span>([^<]+)</span>', rail, re.S)
    dong = ["**Cây menu đọc từ `dashboard/index.html`:**", ""]
    for i, (v, ten) in enumerate(chinh, 1):
        dong.append(f"{i}. {_bo_html(ten)} (`{v}`){_tab_cua(v)}")
    dong.append(f"{len(chinh) + 1}. Cài đặt & Quản trị (thu gọn được)")
    for v, ten in con:
        dong.append(f"    - {_bo_html(ten)} (`{v}`){_tab_cua(v)}")
    dong.append("")
    return dong


def _bo_html(s: str) -> str:
    return s.replace("&amp;", "&").strip()


def _tab_cua(view: str) -> str:
    html = _html()
    i = html.find(f'<section class="view" data-view="{view}"')
    if i < 0:
        return ""
    khoi = html[i:]
    j = khoi.find("</div>")
    tab = re.findall(r'data-tab="([\w-]+)"[^>]*>([^<]+)<', khoi[:j])
    if not tab:
        return ""
    return " — tab: " + ", ".join(f"{_bo_html(t)} (`{m}`)" for m, t in tab)


def _bang_quyen() -> list[str]:
    from agent.core.quyen import NHOM_QUYEN, QUYEN, QUYEN_DA_GO

    dong = [f"**Danh mục quyền đọc từ `agent/core/quyen.py`:** {len(QUYEN)} quyền trong "
            f"{len(NHOM_QUYEN)} nhóm chức năng; {len(QUYEN_DA_GO)} tên đã gỡ, không "
            "bao giờ dùng lại.", "",
            "| Nhóm | Số quyền | Quyền |", "|---|---|---|"]
    for _ma, nhan, ds in NHOM_QUYEN:
        dong.append(f"| {nhan} | {len(ds)} | " + ", ".join(f"`{q}`" for q in ds) + " |")
    dong.append("")
    return dong


def _bang_hanh_dong_ai() -> list[str]:
    from agent.core.uy_quyen import DANH_MUC, NHAN_MUC

    ho_tro = [h for h in DANH_MUC.values() if h.ho_tro]
    dong = [f"**Danh mục hành động AI đọc từ `agent/core/uy_quyen.py`:** {len(DANH_MUC)} "
            f"hành động, {len(ho_tro)} có đường thi hành; còn lại hiện "
            "\"Chưa hỗ trợ — chuyển nhân viên\".", "",
            "| Hành động | Có đường thi hành | Mức mặc định | Đặt mức được |",
            "|---|---|---|---|"]
    for h in DANH_MUC.values():
        dat_duoc = "có" if (h.ho_tro and h.cau_hinh_duoc) else "không"
        dong.append(f"| {h.ten} | {'có' if h.ho_tro else 'không'} | "
                    f"{NHAN_MUC.get(h.mac_dinh, h.mac_dinh)} | {dat_duoc} |")
    dong.append("")
    return dong


def _loai_thong_bao() -> list[str]:
    from agent.core.thong_bao_noi_bo import LOAI

    return [f"**Loại thông báo đọc từ `agent/core/thong_bao_noi_bo.py`** ({len(LOAI)}): "
            + ", ".join(LOAI.values()) + ".", ""]


def _bang_kha_nang() -> list[str]:
    from agent.api.ket_noi_tich_hop import PLUGIN_MO_TA, _adapter_theo_kenh
    from agent.channels.base import KHA_NANG

    kenh = _adapter_theo_kenh()
    khoa = list(KHA_NANG)
    dong = [f"**Khả năng từng plugin kênh, đọc từ `KHA_NANG_KENH` của adapter** "
            f"({len(kenh)} plugin, {len(khoa)} khả năng):", "",
            "| Plugin | " + " | ".join(KHA_NANG[k] for k in khoa) + " |",
            "|---|" + "---|" * len(khoa)]
    for ma, (lop, _cu) in kenh.items():
        o = ["✓" if lop.KHA_NANG_KENH.get(k) else "—" for k in khoa]
        dong.append(f"| {PLUGIN_MO_TA[ma]['ten']} | " + " | ".join(o) + " |")
    dong.append("")
    return dong


def so_kenh_co_bien_nhan() -> int:
    from agent.api.ket_noi_tich_hop import _adapter_theo_kenh

    return sum(1 for lop, _ in _adapter_theo_kenh().values()
               if lop.KHA_NANG_KENH.get("da_nhan") or lop.KHA_NANG_KENH.get("da_xem"))


def _bien_nhan() -> list[str]:
    return [f"Số plugin kênh khai đọc được biên nhận \"Đã nhận\"/\"Đã đọc\": "
            f"**{so_kenh_co_bien_nhan()}** (đếm từ `KHA_NANG_KENH`).", ""]


def _mac_dinh(ten: str):
    from agent.config import Settings

    return Settings.model_fields[ten].default


def _mac_dinh_sla() -> list[str]:
    return [f"Ngưỡng cảnh báo mặc định (`Settings.sla_nguong_canh_bao`): "
            f"**{_mac_dinh('sla_nguong_canh_bao')}%** thời hạn.", ""]


def _mac_dinh_media() -> list[str]:
    return [f"Mặc định đọc từ `agent/config.py`: giữ **{_mac_dinh('media_luu_ngay')} ngày** "
            f"kể từ lần gửi gần nhất, trần **{_mac_dinh('media_toi_da_mb')} MB** mỗi tệp.", ""]


def so_lan_thu_outbox() -> int:
    sql = (ROOT / "agent/migrations/versions/0002_native_inbox_outbox.sql").read_text(encoding="utf-8")
    m = re.search(r"max_attempts\s+INT\s+NOT NULL DEFAULT (\d+)", sql)
    if not m:
        raise LoiThamChieu("không đọc được max_attempts mặc định của outbox_jobs")
    return int(m.group(1))


def so_migration() -> int:
    return len(list((ROOT / "agent/migrations/versions").glob("[0-9][0-9][0-9][0-9]_*.sql")))


def thong_ke_route() -> tuple[int, int, int]:
    """(số route /api|/tich-hop, đã khai quyền, miễn trừ)."""
    rq = {k: v for k, v in _route_quyen().items() if k[1].startswith(("/api", "/tich-hop"))}
    khai = sum(1 for v in rq.values() if v.startswith("`"))
    mien = sum(1 for v in rq.values() if v.startswith("miễn trừ"))
    return len(rq), khai, mien


# =====================================================================
#  Dựng markdown
# =====================================================================

TAI_LIEU_SINH = (
    ("docs/kien-truc.md", "scripts.sinh_so_do"),
    ("docs/thuc-nghiem.md", "scripts.sinh_thuc_nghiem"),
    ("docs/ky-nang.md", "scripts.sinh_ky_nang"),
    ("docs/nghiem-thu.md", "scripts.sinh_nghiem_thu"),
    ("docs/yeu-cau-chuc-nang.md", "scripts.sinh_bang_yeu_cau"),
)


def _dong_muc(m: Muc) -> list[str]:
    nt = ket_qua_nghiem_thu()
    tt = trang_thai_muc(m)
    dong = [f"## Mục {m.so}. {m.ten}", "", f"**Trạng thái: {NHAN_TRANG_THAI[tt]}**", ""]
    if m.nghiem_thu:
        ks = []
        for k in m.nghiem_thu:
            so, ten, kq = nt[k]
            ks.append(f"kịch bản {so} — {ten} (**{kq}**)")
        dong += ["Nghiệm thu trên app đầy đủ + Postgres thật: " + "; ".join(ks) + ".", ""]
    dong += ["| # | Yêu cầu | Trạng thái | Test canh |", "|---|---|---|---|"]
    for i, y in enumerate(m.yeu_cau, 1):
        so = f"{m.so}.{i}" + (f" (bảng {y.bang})" if y.bang else "")
        mo_ta = y.mo_ta + (f" *{y.ghi_chu}*" if y.ghi_chu else "")
        test = "<br>".join(_test_ngan(t) for t in y.test) or "—"
        dong.append(f"| {so} | {mo_ta} | {NHAN_TRANG_THAI[y.trang_thai]} | {test} |")
    dong.append("")
    tep = tep_test_cua(m)
    dong += [f"Test canh nêu tên: **{sum(len(y.test) for y in m.yeu_cau)}**; các tệp test "
             f"ấy ({len(tep)} tệp) có tổng **{dem_test(tep)}** hàm test.", ""]
    if m.them:
        dong += m.them()
    dong += ["**Nơi hiện thực**", ""]
    if m.ma:
        dong.append("- Mã: " + ", ".join(f"`{p}`" for p in m.ma))
    if m.api:
        rq = _route_quyen()
        dong.append("- API (quyền đọc từ route thật):")
        for a in m.api:
            pt, _, duong = a.partition(" ")
            dong.append(f"    - `{a}` — {rq[(pt, duong)]}")
    if m.giao_dien:
        dong.append("- Giao diện: " + ", ".join(
            f"{'màn' if g.startswith('view:') else 'tab'} `{g.partition(':')[2]}`"
            for g in m.giao_dien))
    dong.append("")
    if m.lech:
        dong += ["**Lệch so với bảng / ghi chú**", ""] + [f"- {x}" for x in m.lech] + [""]
    if m.hoi:
        dong += ["**Câu hỏi mở — cần chủ dự án xác nhận**", ""] + [f"- {x}" for x in m.hoi] + [""]
    return dong


def dung_tai_lieu(
    cac_muc: tuple[Muc, ...] | None = None,
    phi: tuple[PhiChucNang, ...] | None = None,
    han_che: tuple[HanChe, ...] | None = None,
) -> str:
    cac_muc = MUC if cac_muc is None else cac_muc
    phi = PHI_CHUC_NANG if phi is None else phi
    han_che = HAN_CHE if han_che is None else han_che
    loi = (kiem_muc(cac_muc) + kiem_phi_chuc_nang(phi) + kiem_han_che(han_che)
           + kiem_khong_co_route(ROUTE_CAM))
    if loi:
        raise LoiThamChieu("Bảng yêu cầu nêu tên thứ không có thật:\n  " + "\n  ".join(loi))

    nt = ket_qua_nghiem_thu()
    dat_nt = sum(1 for _, _, k in nt.values() if k == "đạt")
    dong = [
        "# Bảng yêu cầu chức năng và phi chức năng",
        "",
        "<!-- SINH TỰ ĐỘNG bởi scripts/sinh_bang_yeu_cau.py — đừng sửa tay. -->",
        "",
        "Đối chiếu từng mục của bảng \"Check list công việc\" (21.11.2026, mục 1–21; "
        "bảng không có mục 11) với mã nguồn, test canh và kịch bản nghiệm thu. "
        "Phạm vi ràng buộc và các khác biệt đã chốt: `docs/nang-cap/ke-hoach-check-list.md`.",
        "",
        "**Cách đọc.** Phần ánh xạ (yêu cầu → mã → test) do người viết, nhưng mỗi "
        "lần sinh, bộ sinh kiểm từng đường dẫn, từng tên test, từng route API "
        "(trên app thật), từng tab giao diện và từng kịch bản nghiệm thu — thiếu một "
        "thứ là không sinh được bảng. Mọi con số đếm từ mã. Trạng thái của MỤC suy "
        "từ yêu cầu con, không gõ tay. Sinh lại: `python -m scripts.sinh_bang_yeu_cau --ghi`.",
        "",
        "Trạng thái: **Đạt** — có mã và test canh; **Đạt một phần** — làm được phần "
        "chính, phần còn lại ghi rõ ở cột yêu cầu; **Chưa làm**; **Ngoài phạm vi theo "
        "bảng** — bảng ghi tạm hoãn/ẩn/hướng sau, không tính vào trạng thái mục.",
        "",
        f"Nghiệm thu (`docs/nghiem-thu.md`, sinh từ lượt chạy thật): **{dat_nt}/{len(nt)}** "
        "kịch bản đạt.",
        "",
        "## Tổng quan",
        "",
        "| Mục | Yêu cầu | Trạng thái | Yêu cầu con đạt | Test canh nêu tên | Nghiệm thu |",
        "|---|---|---|---|---|---|",
    ]
    for m in cac_muc:
        tinh = [y for y in m.yeu_cau if y.trang_thai != NGOAI]
        dat = sum(1 for y in tinh if y.trang_thai == DAT)
        ngoai = len(m.yeu_cau) - len(tinh)
        o_dat = f"{dat}/{len(tinh)}" + (f" (+{ngoai} ngoài phạm vi)" if ngoai else "")
        ks = ", ".join(str(nt[k][0]) for k in m.nghiem_thu) or "—"
        dong.append(f"| {m.so} | {m.ten} | {NHAN_TRANG_THAI[trang_thai_muc(m)]} | {o_dat} | "
                    f"{sum(len(y.test) for y in m.yeu_cau)} | {ks} |")
    dem = {k: sum(1 for m in cac_muc if trang_thai_muc(m) == k) for k in NHAN_TRANG_THAI}
    dong += ["", "Tổng: " + ", ".join(f"{NHAN_TRANG_THAI[k]} {v}" for k, v in dem.items() if v)
             + f" (trên {len(cac_muc)} mục).", "", "---", "", "# Phần A — Yêu cầu chức năng", ""]
    for m in cac_muc:
        dong += _dong_muc(m)

    # ---- Phi chức năng
    so_route, khai, mien = thong_ke_route()
    dong += ["---", "", "# Phần B — Yêu cầu phi chức năng", "",
             "Số liệu đếm từ mã lúc sinh:", "",
             f"- Route `/api` và `/tich-hop` trên app thật: **{so_route}** — **{khai}** khai "
             f"quyền bằng `can_quyen`, **{mien}** nằm trong `MIEN_TRU` có lý do; còn lại "
             f"**{so_route - khai - mien}** (phải bằng 0, nếu không máy chủ không khởi động).",
             f"- Outbox thử tối đa **{so_lan_thu_outbox()}** lần (mặc định cột `max_attempts`, "
             "migration 0002) rồi vào dead-letter và kêu người.",
             f"- Migration SQL đã chốt checksum: **{so_migration()}** tệp.",
             f"- Hạn lưu hội thoại mặc định: **{_mac_dinh('luu_hoi_thoai_ngay')} ngày**; "
             f"media khách gửi: **{_mac_dinh('media_luu_ngay')} ngày**.",
             ""]
    nhom_truoc = None
    for d in phi:
        if d.nhom != nhom_truoc:
            dong += [f"## {d.nhom}", "", "| Yêu cầu | Cách đáp ứng | Trạng thái | Bằng chứng |",
                     "|---|---|---|---|"]
            nhom_truoc = d.nhom
        bc = [_test_ngan(t) for t in d.test] + [f"`{p}`" for p in d.ma]
        dong.append(f"| {d.yeu_cau} | {d.dap_ung} | {NHAN_TRANG_THAI[d.trang_thai]} | "
                    + ("<br>".join(bc) or "—") + " |")
        if d is phi[-1] or phi[phi.index(d) + 1].nhom != d.nhom:
            dong.append("")

    # ---- Bảo trì: số test theo mục + tài liệu sinh
    tat_ca = tat_ca_tep_test()
    tong = dem_test(list(tat_ca))
    dong += ["## Số test theo vùng", "",
             f"Toàn repo: **{len(tat_ca) // 10 * 10}+** tệp test, **{tong // 100 * 100}+** hàm "
             "test (đếm `def test_` bằng `ast`, làm tròn xuống để bảng không cũ mỗi lần thêm "
             "một test ở chỗ không liên quan; một hàm `parametrize` sinh nhiều ca, nên số ca "
             "pytest chạy lớn hơn).", "",
             "| Mục | Tệp test canh | Hàm test trong các tệp ấy |", "|---|---|---|"]
    for m in cac_muc:
        tep = tep_test_cua(m)
        dong.append(f"| {m.so}. {m.ten} | {len(tep)} | {dem_test(tep)} |")
    tep_pcn = sorted({tach_test(t)[0] for d in phi for t in d.test})
    dong += [f"| Phi chức năng (Phần B) | {len(tep_pcn)} | {dem_test(tep_pcn)} |", "",
             "## Tài liệu sinh ra và test canh tài liệu cũ", "",
             "| Tài liệu | Lệnh sinh lại |", "|---|---|"]
    for tep_doc, lenh in TAI_LIEU_SINH:
        dong.append(f"| `{tep_doc}` | `python -m {lenh} --ghi` |")
    dong.append("")

    # ---- Hạn chế
    dong += ["---", "", "# Phần C — Hạn chế đã biết", ""]
    for i, h in enumerate(han_che, 1):
        bc = (" Bằng chứng: " + ", ".join(f"`{p}`" for p in h.bang_chung) + ".") \
            if h.bang_chung else ""
        dong += [f"{i}. **{h.ten}.** {h.mo_ta}{bc}", ""]
    return "\n".join(dong).rstrip() + "\n"


# =====================================================================
#  DỮ LIỆU VIẾT TAY — ánh xạ yêu cầu → mã → test
# =====================================================================

T = "tests/"

MUC: tuple[Muc, ...] = (
    Muc(1, "Nút \"← Quay lại\" ở màn hai lớp (xác thực hai bước)", (
        YeuCau("Hộp hỏi hai lớp (`#congHoi` — bật/tắt xác thực hai bước và các hộp xác "
               "nhận khác) dùng chữ \"← Quay lại\", không còn \"Thôi, quay lại\"", DAT,
               (T + "test_cay_menu.py::test_nut_quay_lai_hai_buoc",)),
        YeuCau("Các hộp phụ khác (giao khách, đổi mật khẩu) dùng cùng chữ \"← Quay lại\"", DAT,
               (T + "test_cay_menu.py::test_nut_quay_lai_hai_buoc",),
               ghi_chu="Test soi `#congHoi`; hai hộp còn lại cùng chữ trong index.html."),
        YeuCau("Xác thực hai bước chạy thật: hỏi mã, mã sai tính lần sai, không lộ tài khoản "
               "có bật hai bước", DAT,
               (T + "test_hai_buoc.py::test_vong_doi_2fa_tren_csdl_that",
                T + "test_hai_buoc.py::test_thieu_ma_thi_hoi_ma_khong_tao_phien",
                T + "test_hai_buoc.py::test_sai_mat_khau_khong_lo_la_co_2fa")),
    ),
        ma=("dashboard/index.html", "dashboard/src/07-noi-dung.js", "dashboard/src/14-cskh.js",
            "agent/core/hai_buoc.py"),
        api=("GET /api/toi/hai-buoc", "POST /api/toi/hai-buoc/bat-dau",
             "POST /api/toi/hai-buoc/xac-nhan", "POST /api/toi/hai-buoc/tat"),
        nghiem_thu=("test_01_dang_nhap_that_bang_mat_khau",),
        hoi=("Màn ĐĂNG NHẬP khi máy chủ đòi mã hai bước hiện ô mã ngay trong biểu mẫu, "
             "không có nút \"← Quay lại\" riêng (người dùng sửa thẳng tên/mật khẩu). Nếu bảng "
             "muốn cả chỗ này thì còn thiếu.",),
    ),
    Muc(2, "Dòng \"Thời gian · Người gửi · Trạng thái\" dưới mỗi tin", (
        YeuCau("Đúng MỘT dòng meta dưới mỗi tin theo thứ tự Thời gian · Người gửi · Trạng thái",
               DAT, (T + "test_trach_nhiem_giao_dien.py::test_mot_dong_meta_thoi_gian_nguoi_gui_trang_thai",)),
        YeuCau("Người gửi theo quy ước: AI Agent / Nhân viên (tên) / Khách hàng (tên) / Hệ "
               "thống; người sửa, người duyệt ghi tên", DAT,
               (T + "test_trach_nhiem_hoi_thoai.py::test_chi_tiet_hoi_thoai_noi_ten_nguoi_gui_nguoi_sua_nguoi_duyet",
                T + "test_tin_nhom_zalo.py::test_api_chi_tiet_tra_ten_nguoi_gui_tung_tin")),
        YeuCau("Thông tin kỹ thuật (độ tin cậy, nguồn, model, chi phí, thời gian xử lý) chỉ "
               "nằm trong \"Chi tiết\" của từng tin", DAT,
               (T + "test_trach_nhiem_giao_dien.py::test_khong_hien_ky_thuat_mac_dinh_va_khong_phan_tram_tin_cay",
                T + "test_trach_nhiem_giao_dien.py::test_xem_can_cu_tren_ban_nhap_va_chi_tiet_tung_tin")),
        YeuCau("Trạng thái lấy từ `delivery_status` thật, không bịa (Đang gửi / Đã gửi / Lỗi)",
               DAT, (T + "test_outbox_trang_thai_tin.py::test_moi_trang_thai_job_deu_anh_xa_ra_gia_tri_hop_le",
                     T + "test_outbox_trang_thai_tin.py::test_retry_khong_bao_gio_ro_ri_ra_cot_tin_nhan")),
        YeuCau("Trạng thái \"Đã nhận\" / \"Đã đọc\" hiện được", MOT_PHAN,
               (T + "test_kha_nang_kenh.py::test_khong_khai_bien_nhan_khi_chua_co_ma_doc_bien_nhan",),
               ghi_chu="Giao diện có nhãn, nhưng chưa kênh nào đọc biên nhận từ webhook — "
                       "xem số đếm bên dưới."),
    ),
        ma=("dashboard/src/03-hoi-thoai.js", "dashboard/src/19-trach-nhiem.js",
            "agent/api/inbox.py"),
        api=("GET /api/inbox/conversations/{conversation_id}",),
        giao_dien=("view:hoithoai",),
        them=_bien_nhan,
    ),
    Muc(3, "Nhãn động cho khách hàng và hội thoại, danh mục chung", (
        YeuCau("Danh mục nhãn: tên duy nhất (không phân biệt hoa thường, kể cả nhãn đã ngừng), "
               "màu, mô tả, thứ tự; ngừng dùng thay vì xoá khi đang gắn", DAT,
               (T + "test_nhan_dong.py::test_danh_muc_tao_sua_trung_ten_ngung_xoa",
                T + "test_nhan_dong.py::test_chuan_ten_gop_khoang_trang_va_NFC",
                T + "test_nhan_dong.py::test_chuan_mau",
                T + "test_nhan_dong.py::test_quyen_danh_muc")),
        YeuCau("Hai loại độc lập — nhãn khách, nhãn hội thoại; CSDL chặn gắn nhầm loại và xoá "
               "nhãn đang gắn", DAT,
               (T + "test_nhan_dong.py::test_csdl_chan_sai_loai_va_xoa_nhan_dang_gan",
                T + "test_nhan_dong.py::test_migration_khoa_ngoai_dung_chieu")),
        YeuCau("Gắn/gỡ đúng màn: nhãn hội thoại ở đầu hội thoại, nhãn khách ở Customer 360; theo "
               "quyền và phạm vi kênh; lọc hộp thư và danh sách khách theo nhãn", DAT,
               (T + "test_nhan_dong.py::test_nhan_hoi_thoai_gan_go_loc_quyen_va_pham_vi",
                T + "test_nhan_dong.py::test_nhan_khach_gan_go_loc_quyen_va_pham_vi",
                T + "test_nhan_dong.py::test_dau_hoi_thoai_chi_co_nhan_hoi_thoai",
                T + "test_nhan_dong.py::test_o_chon_chi_lay_nhan_dang_dung_va_chip_nhan_da_ngung_hien_xam")),
        YeuCau("Nhãn chữ tự do cũ chuyển sang danh mục; không còn đường ghi chữ tự do", DAT,
               (T + "test_nhan_dong.py::test_migration_chuyen_du_lieu_cu",
                T + "test_nhan_dong.py::test_khong_ma_nao_con_ghi_bang_chu_tu_do_cu",
                T + "test_nhan_dong.py::test_khong_con_o_go_nhan_chu_tu_do")),
        YeuCau("Quy tắc tự động tách điều kiện/hành động theo nhãn khách và nhãn hội thoại (theo id)",
               DAT, (T + "test_nhan_dong.py::test_quy_tac_tach_nhan_khach_va_nhan_hoi_thoai",
                     T + "test_nhan_dong.py::test_bieu_mau_quy_tac_tach_hai_loai_nhan")),
        YeuCau("Gộp khách gộp nhãn (hoàn tác gỡ đúng phần đã chép); PDPD tra cứu kể tên nhãn và "
               "xoá liên kết", DAT,
               (T + "test_nhan_dong.py::test_gop_khach_gop_nhan_va_hoan_tac_go_dung_phan_chep",
                T + "test_nhan_dong.py::test_pdpd_tra_cuu_ke_ten_nhan_va_xoa_lien_ket")),
    ),
        ma=("agent/core/nhan.py", "agent/api/nhan.py", "agent/api/hoi_thoai_nhan.py",
            "agent/migrations/versions/0056_danh_muc_nhan.sql", "dashboard/src/21-nhan.js"),
        api=("GET /api/nhan", "POST /api/nhan", "PUT /api/nhan/{nhan_id}",
             "POST /api/nhan/{nhan_id}/ngung", "GET /api/nhan/hoi-thoai", "GET /api/nhan/khach",
             "POST /api/inbox/conversations/{conversation_id}/nhan"),
        giao_dien=("tab:cc-nhan",),
        nghiem_thu=("test_20_quan_ly_nhan_va_gan_nhan_hai_loai",),
        lech=("Bảng cũ `contact_tags`, `hoi_thoai_nhan` giữ nguyên trong CSDL (dữ liệu thật, "
              "migration đã chốt) nhưng không mã nào ghi vào nữa — có test canh.",),
    ),
    Muc(4, "Tái cấu trúc menu: 6 menu chính + \"Cài đặt & Quản trị\", chuông thông báo", (
        YeuCau("Sáu màn nghiệp vụ đúng thứ tự: Hội thoại, Khách hàng, Đơn hàng, Kho, Công việc, "
               "Phân tích", DAT, (T + "test_cay_menu.py::test_dung_sau_man_nghiep_vu_dung_thu_tu",
                                   T + "test_cay_menu.py::test_moi_muc_thanh_ben_co_dung_mot_man")),
        YeuCau("Nhóm \"Cài đặt & Quản trị\" thu gọn được, đúng bốn mục con chia tab", DAT,
               (T + "test_cay_menu.py::test_nhom_cai_dat_thu_gon_duoc_va_dung_bon_con",
                T + "test_cay_menu.py::test_tab_dung_id_hop_dong_va_nam_dung_man")),
        YeuCau("Phân tích thay chỗ \"Số hiệu\": hiệu quả CSKH, AI Agent, nhân viên, SLA, tin "
               "nhắn; lọc ngày, nền tảng, tài khoản kênh, nhân viên, hồ sơ AI; tôn trọng phạm vi kênh",
               DAT, (T + "test_phan_tich_va_sla.py::test_phan_tich_ai_theo_ho_so_dem_theo_su_kien",
                     T + "test_phan_tich_va_sla.py::test_phan_tich_chi_thay_kenh_duoc_giao",
                     T + "test_phan_tich_va_sla.py::test_dashboard_co_man_phan_tich_doi_uu_tien_va_nghe_moi_su_kien_sla"),
               bang="4.3"),
        YeuCau("Công việc gộp Ca trực: tab Tổng quan ca trực + Danh sách công việc", DAT,
               (T + "test_cay_menu.py::test_noi_dung_cu_nam_dung_tab",
                T + "test_he_thong_giao_viec.py::test_man_danh_sach_cong_viec_gan_vao_tab")),
        YeuCau("Chuông thông báo ở thanh trên, không là mục điều hướng; thanh bên không còn "
               "Video / Đăng bài / Thông báo", DAT,
               (T + "test_thong_bao_noi_bo.py::test_chuong_nam_o_thanh_tren_khong_co_muc_dieu_huong",
                T + "test_cay_menu.py::test_khong_con_video_dang_bai_hay_thong_bao_tren_thanh_ben")),
        YeuCau("Mục menu và tab ẩn theo quyền (máy chủ vẫn là chốt thật); tên màn cũ vẫn dẫn "
               "tới đúng tab", DAT,
               (T + "test_cay_menu.py::test_menu_an_theo_quyen_sau_khi_dang_nhap",
                T + "test_cay_menu.py::test_moi_tab_co_quyen_va_quyen_co_that",
                T + "test_cay_menu.py::test_ten_man_cu_van_dan_toi_dung_tab")),
        YeuCau("Sức khoẻ hệ thống chỉ còn ở Hệ thống & Nhật ký (trước ở ba nơi)", DAT,
               (T + "test_cay_menu.py::test_suc_khoe_he_thong_chi_o_he_thong_va_nhat_ky",)),
        YeuCau("Mô-đun gắn vào tab theo id cố định (GAN_TAB); mô-đun hỏng thì nội dung gốc hiện "
               "lại và có thông báo", DAT,
               (T + "test_cay_menu.py::test_gan_khe_an_noi_dung_goc_va_lui_lai_khi_mo_dun_hong",
                T + "test_cay_menu.py::test_gan_khe_chay_that_trong_node")),
        YeuCau("Khổ hẹp: thanh bên thu gọn, mở bằng ☰", DAT,
               (T + "test_cay_menu.py::test_thanh_ben_thu_gon_o_kho_hep",)),
        YeuCau("Ẩn CSAT và cấu hình VietQR khỏi giao diện, giữ mã nguồn và API", NGOAI,
               (T + "test_cay_menu.py::test_csat_va_vietqr_khong_hien_nhung_ma_con",
                T + "test_cay_menu.py::test_csat_mac_dinh_tat"),
               ghi_chu="Bảng ghi tạm hoãn — đã ẩn đúng như bảng, có test canh.", bang="4.8"),
    ),
        ma=("dashboard/index.html", "dashboard/src/00-gan-tab.js", "dashboard/src/01b-dieu-huong.js",
            "dashboard/src/10-vong-lam-moi.js", "dashboard/src/19-phan-tich.js", "agent/api/phan_tich.py"),
        api=("GET /api/phan-tich", "GET /api/phan-tich/bo-loc"),
        giao_dien=("view:hoithoai", "view:khachhang", "view:donhang", "view:kho", "view:congviec",
                   "view:sohieu", "view:cauhinhchung", "view:cauhinhai", "view:nhansu", "view:hethong"),
        nghiem_thu=("test_19_doi_uu_tien_rut_han_sla_va_man_phan_tich",),
        lech=("Màn Phân tích giữ id cũ `sohieu` (chỉ đổi nhãn) để đường dẫn và quyền cũ không gãy.",
              "Bảng \"Khách đến từ đâu\" (đếm theo trạng thái, sai nghĩa) đã gỡ khỏi Phân tích."),
        them=_cay_menu,
    ),
    Muc(5, "Cấu hình AI Agent: 5 tab, bật/tắt AI, chế độ chung mọi kênh", (
        YeuCau("Năm tab: Cấu hình cơ bản, Tri thức (RAG), Kỹ năng & Công cụ, Chính sách & Ủy "
               "quyền, Phòng thử; ba màn cũ chuyển vào nguyên vẹn", DAT,
               (T + "test_cay_menu.py::test_tab_dung_id_hop_dong_va_nam_dung_man",
                T + "test_cay_menu.py::test_noi_dung_cu_nam_dung_tab")),
        YeuCau("Công tắc bật/tắt AI Agent toàn cục: bền qua khởi động lại, ghi nhật ký, máy chủ "
               "từ chối thì công tắc trả về", DAT,
               (T + "test_cay_menu.py::test_cong_tac_ai_ghi_dung_duong_runtime",
                T + "test_cong_tac_ai_toan_cuc.py::test_ai_TAT_khong_tra_loi_khong_nhap_va_vao_hang_cho_nguoi")),
        YeuCau("Hội thoại nhân viên đã tiếp quản thì AI không chen vào, dù công tắc đang bật; "
               "bật lại không giành hội thoại", DAT,
               (T + "test_cong_tac_ai_toan_cuc.py::test_nhan_vien_da_tiep_quan_thi_AI_khong_tra_loi_du_dang_BAT",
                T + "test_cong_tac_ai_toan_cuc.py::test_bat_lai_AI_khong_gianh_hoi_thoai_nhan_vien_dang_cam",
                T + "test_cong_tac_ai_toan_cuc.py::test_agent_bat_xet_nguoi_tiep_quan_TRUOC_cong_tac")),
        YeuCau("Chế độ Gợi ý / Tự động rời thanh trên vào Cấu hình cơ bản (ngắt khẩn cấp ở lại "
               "thanh trên)", DAT,
               (T + "test_cay_menu.py::test_bo_chon_che_do_roi_thanh_tren_vao_cau_hinh_co_ban",)),
        YeuCau("Một cấu hình AI chung cho mọi kênh", MOT_PHAN,
               (T + "test_cay_menu.py::test_khe_nha_cung_cap_nam_trong_ai_co_ban",
                T + "test_agent_bat_theo_kenh.py::test_tat_theo_kenh_thi_chan_va_NOI_RO_LY_DO",
                T + "test_ho_so_agent.py::test_main_truyen_ho_so_theo_kenh"),
               ghi_chu="Luồng chính là một cấu hình; hồ sơ agent theo kênh và công tắc agent "
                       "theo kênh vẫn còn, gói trong mục \"Nâng cao\".", bang="5.4"),
        YeuCau("Nhà cung cấp AI, khoá, model chỉnh ở Cấu hình cơ bản và có hiệu lực ngay", DAT,
               (T + "test_ket_noi_tich_hop.py::test_model_chat_tren_dashboard_co_hieu_luc",
                T + "test_ket_noi_tich_hop.py::test_kiem_ai_dung_model_chat_va_endpoint_vua_go")),
        YeuCau("Phòng thử mô phỏng công cụ ghi (không gọi thật); công cụ ghi đã cho phép chỉ gọi "
               "thật ở chế độ Tự động", DAT,
               (T + "test_thu_nghiem_mcp.py::test_ghi_trong_sandbox_khong_goi_that",
                T + "test_thu_nghiem_mcp.py::test_ghi_da_cho_phep_thi_goi_that")),
    ),
        ma=("agent/runtime.py", "agent/core/agent_bat.py", "agent/api/ho_so_agent.py",
            "dashboard/src/23-ai-co-ban.js", "dashboard/src/11-ky-nang.js"),
        api=("POST /api/runtime", "GET /api/ket-noi/ai"),
        giao_dien=("view:cauhinhai", "tab:ai-co-ban", "tab:ai-tri-thuc", "tab:ai-ky-nang",
                   "tab:ai-chinh-sach", "tab:ai-phong-thu"),
        nghiem_thu=("test_04_noi_kenh_va_tat_agent_theo_kenh", "test_09_ho_so_agent_va_dinh_tuyen_cau_hinh_duoc"),
        hoi=("Giữ hay gỡ hồ sơ agent theo kênh và công tắc agent theo kênh (đang ở \"Nâng cao\")? "
             "Bảng 5.4 chỉ nói một cấu hình chung.",),
    ),
    Muc(6, "Thanh thông tin hội thoại gọn; ghi chú nội bộ trong ô soạn tin", (
        YeuCau("Thứ tự: Tên khách · Nhãn hội thoại (ngay dưới tên) · Customer 360 · Hành động "
               "xử lý · Chi tiết", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_thu_tu_ten_nhan_c360_hanh_dong_chi_tiet",)),
        YeuCau("Gỡ trạng thái, kênh, Mode, SLA khỏi thanh; ưu tiên (kèm Đổi), version, chế độ AI "
               "vào panel Chi tiết", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_load_thread_khong_ve_lai_nhung_thu_da_go",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_chi_tiet_hoi_thoai_co_uu_tien_version_che_do_khong_co_sla")),
        YeuCau("Nút xử lý: một nút chính + menu \"⋯\", theo trạng thái × quyền (hàm thuần, test "
               "chạy bằng node)", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_bang_nut_theo_trang_thai_va_quyen",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_khong_bao_gio_qua_nhieu_nut_mot_luc",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_tu_gui_moi_duyet_truoc_va_nguoc_lai")),
        YeuCau("Ô soạn hai kiểu \"Trả lời khách\" / \"Ghi chú nội bộ\"; kiểu ghi chú không bao "
               "giờ gọi đường gửi; bản nháp tách theo kiểu", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_o_soan_kieu_ghi_chu_khong_bao_gio_goi_duong_gui",
                T + "test_nhom_khong_phai_khach.py::test_route_ghi_chu_khong_cham_toi_duong_gui",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_ban_nhap_tach_theo_kieu_soan",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_nop_form_doc_kieu_soan_truoc_khi_cho_mang")),
        YeuCau("Ghi chú xen trong luồng tin theo thời gian, kèm tên nhân viên và giờ; chỉ người có "
               "quyền ghi chú mới thấy kiểu ghi chú", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_ghi_chu_xen_trong_luong_theo_thoi_gian",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_che_do_soan_chi_cho_nguoi_co_quyen_ghi_chu")),
        YeuCau("Mở lại hội thoại đã giải quyết (cần quyền nhận hội thoại)", DAT,
               (T + "test_nhom_khong_phai_khach.py::test_mo_lai_tay_hoi_thoai_da_giai_quyet",
                T + "test_nhom_khong_phai_khach.py::test_mo_lai_tay_can_quyen_nhan")),
    ),
        ma=("dashboard/src/03b-thanh-hoi-thoai.js", "dashboard/src/03-hoi-thoai.js",
            "agent/api/hoi_thoai_nhan.py"),
        api=("GET /api/inbox/conversations/{conversation_id}/ghi-chu",
             "POST /api/inbox/conversations/{conversation_id}/ghi-chu",
             "POST /api/inbox/conversations/{conversation_id}/giai-quyet",
             "POST /api/inbox/conversations/{conversation_id}/mo-lai"),
        giao_dien=("view:hoithoai",),
    ),
    Muc(7, "Mẫu trả lời và quy tắc tự động: ưu tiên, xung đột, chống trùng với AI", (
        YeuCau("Mẫu trả lời nhanh: tạo/tìm/sửa/xoá, mã tắt; nhân viên dùng được, không sửa được",
               DAT, (T + "test_api_tra_loi_nhanh.py::test_tao_tim_sua_xoa",
                     T + "test_api_tra_loi_nhanh.py::test_ma_trung_la_409",
                     T + "test_api_tra_loi_nhanh.py::test_nhan_vien_dung_duoc_khong_sua_duoc")),
        YeuCau("Cụm cấm của luật quảng cáo mỹ phẩm bị chặn cả lúc tạo lẫn lúc sửa mẫu; mẫu bị sửa "
               "thành câu cấm thì quy tắc không gửi", DAT,
               (T + "test_api_tra_loi_nhanh.py::test_cum_cam_quang_cao_khong_luu_duoc",
                T + "test_api_tra_loi_nhanh.py::test_sua_mau_thanh_cau_cam_cung_bi_chan",
                T + "test_tu_dong.py::test_mau_bi_sua_thanh_cau_cam_thi_khong_gui")),
        YeuCau("Chèn mẫu bằng \"/\" trong ô soạn", DAT,
               (T + "test_tu_dong_giao_dien.py::test_go_gach_cheo_chen_mau_tra_loi_nhanh",
                T + "test_tu_dong_giao_dien.py::test_o_nhan_tin_gan_khung_mau")),
        YeuCau("Thứ tự ưu tiên ổn định (thứ tự → lúc tạo → id); \"dừng xét quy tắc sau\"", DAT,
               (T + "test_tu_dong.py::test_thu_tu_on_dinh_cung_so_uu_tien",
                T + "test_tu_dong.py::test_dung_xet_quy_tac_sau")),
        YeuCau("Xung đột: tối đa MỘT tin tự động mỗi tin khách; nhãn/việc gộp; chuyển người "
               "quy tắc đầu thắng; mẫu của quy tắc chuyển người thay câu báo cố định", DAT,
               (T + "test_tu_dong.py::test_nhieu_quy_tac_khop_khach_nhan_mot_tin_nhan_gop",
                T + "test_tu_dong.py::test_chuyen_nguoi_uu_tien_hon_thi_mau_sau_nhuong",
                T + "test_tu_dong.py::test_mau_cua_quy_tac_chuyen_nguoi_la_cau_bao",
                T + "test_tu_dong.py::test_viec_cung_tieu_de_chi_tao_mot")),
        YeuCau("Kiểm lúc lưu chặn quy tắc mâu thuẫn; \"một lần\" tính theo từng loại hành động", DAT,
               (T + "test_tu_dong.py::test_kiem_luc_luu_chan_mau_thuan",
                T + "test_tu_dong.py::test_mot_lan_tinh_theo_tung_loai_hanh_dong")),
        YeuCau("Chống trùng với AI: AI nhường đúng tin quy tắc đã gửi mẫu (trừ khi bật \"cho AI "
               "trả lời\"); nhường đặt sau các nhánh giao người", DAT,
               (T + "test_tu_dong.py::test_cho_ai_tra_loi_thi_ai_khong_nhuong",
                T + "test_tu_dong.py::test_ai_nhuong_dat_sau_cac_nhanh_chuyen_nguoi")),
        YeuCau("Không gửi mẫu khi nhân viên đang tiếp, đang duyệt trước khi gửi, khách đòi gặp "
               "người, hội thoại nhóm — gắn nhãn/tạo việc vẫn chạy", DAT,
               (T + "test_tu_dong.py::test_nguoi_dang_tiep_thi_khong_gui_mau",
                T + "test_tu_dong.py::test_khong_gui_mau_nhung_van_gan_nhan")),
        YeuCau("Mẫu đang được quy tắc bật dùng thì không đổi mã / xoá được (409)", DAT,
               (T + "test_api_tra_loi_nhanh.py::test_doi_ma_hoac_xoa_mau_quy_tac_dang_dung_la_409",)),
        YeuCau("Biểu mẫu ba nhóm Thông tin · Nếu · Thì; câu chính sách; lần chạy cuối, lỗi cuối, "
               "nhật ký từng quy tắc", DAT,
               (T + "test_tu_dong_giao_dien.py::test_bieu_mau_quy_tac_ba_nhom_dung_thu_tu_va_du_o",
                T + "test_tu_dong_giao_dien.py::test_chinh_sach_hien_cho_nguoi_van_hanh",
                T + "test_tu_dong_giao_dien.py::test_dong_quy_tac_hien_dau_vet_chay")),
        YeuCau("Quy tắc cấu hình trên dashboard chạy đúng trên luồng tin vào thật (đầu–cuối)", DAT,
               (T + "test_tu_dong_dau_cuoi.py::test_quy_tac_cau_hinh_tren_dashboard_chay_dung_tren_luong_tin_vao",)),
    ),
        ma=("agent/omnichannel/tu_dong.py", "agent/api/tu_dong_api.py", "agent/api/tra_loi_nhanh.py",
            "agent/migrations/versions/0060_quy_tac_uu_tien_va_xung_dot.sql",
            "dashboard/src/15-tu-dong.js"),
        api=("GET /api/tu-dong", "POST /api/tu-dong", "PUT /api/tu-dong/{quy_tac_id}",
             "GET /api/tu-dong/lan-chay", "GET /api/tra-loi-nhanh", "POST /api/tra-loi-nhanh"),
        giao_dien=("tab:cc-tu-dong",),
        nghiem_thu=("test_13_quy_tac_tu_dong_chan_agent_va_chuyen_nguoi",),
    ),
    Muc(8, "Kết nối & Tích hợp: kênh, ERPNext, GHN, GHTK, webhook, nhà cung cấp AI, "
           "thông báo minh bạch AI", (
        YeuCau("ERPNext, GHN, GHTK mỗi dịch vụ một thẻ, bốn trạng thái; nhập/sửa trên dashboard; "
               "đổi khoá thì kết quả kiểm cũ về \"chưa kiểm tra\"", DAT,
               (T + "test_ket_noi_tich_hop.py::test_bon_trang_thai_va_doi_khoa_thi_ve_chua_kiem_tra",
                T + "test_ket_noi_tich_hop.py::test_chua_cau_hinh_khi_thieu_truong_bat_buoc",
                T + "test_ket_noi_tich_hop.py::test_luu_tu_choi_truong_cua_dich_vu_khac",
                T + "test_ket_noi_tich_hop_pg.py::test_so_kiem_va_trang_thai")),
        YeuCau("\"Kiểm tra kết nối\" chỉ gọi hàm ĐỌC của dịch vụ; báo rõ lỗi (vd. 401)", DAT,
               (T + "test_ket_noi_tich_hop.py::test_kiem_ghn_va_ghtk_goi_dung_ham_chi_doc_va_che_token",
                T + "test_ket_noi_tich_hop.py::test_kiem_erpnext_bao_ro_401",
                T + "test_ket_noi_tich_hop.py::test_kiem_bang_gia_tri_vua_go_thi_khong_ghi")),
        YeuCau("Che bí mật: không trả giá trị khoá về giao diện; xem cũng cần quyền sửa cấu hình",
               DAT, (T + "test_ket_noi_tich_hop.py::test_tong_quan_khong_lo_bi_mat",
                     T + "test_ket_noi_tich_hop.py::test_xem_cung_can_quyen_sua_cau_hinh")),
        YeuCau("Lịch sử thay đổi: ai, lúc nào, trường nào — không lưu giá trị", DAT,
               (T + "test_ket_noi_tich_hop.py::test_lich_su_ghi_ten_truong_khong_ghi_gia_tri",
                T + "test_ket_noi_tich_hop_pg.py::test_lich_su_ghi_that_khong_co_gia_tri")),
        YeuCau("Sổ webhook vào: mọi lời gọi `/webhook/*` kể cả lời bị từ chối, thống kê, lỗi gần "
               "nhất; không ghi token", DAT,
               (T + "test_ket_noi_tich_hop.py::test_middleware_ghi_webhook_bi_tu_choi_va_khong_ghi_token",
                T + "test_ket_noi_tich_hop_pg.py::test_so_webhook_ghi_thong_ke_va_lich_su")),
        YeuCau("Đổi cấu hình trên dashboard có hiệu lực không cần khởi động lại (token GHN, khoá "
               "ERPNext, MODEL_CHAT)", DAT,
               (T + "test_ket_noi_tich_hop.py::test_token_ghn_doi_tren_dashboard_khong_can_khoi_dong_lai",
                T + "test_ket_noi_tich_hop.py::test_doi_khoa_erpnext_bo_cong_cu",
                T + "test_ket_noi_tich_hop.py::test_model_chat_tren_dashboard_co_hieu_luc")),
        YeuCau("Nhà cung cấp AI: nhà cung cấp, khoá, endpoint (OpenAI), model; chỉ khai nhà cung "
               "cấp gọi được thật; cảnh báo model khác họ", DAT,
               (T + "test_ket_noi_tich_hop.py::test_ai_chi_khai_nha_cung_cap_llm_that_su_goi_duoc",
                T + "test_ket_noi_tich_hop.py::test_canh_bao_model_khac_ho_nha_cung_cap")),
        YeuCau("Thông báo minh bạch AI sửa được, bốn luật giữ lời hứa \"gặp nhân viên\"; một lần "
               "mỗi hội thoại", DAT,
               (T + "test_ket_noi_tich_hop.py::test_noi_dung_sai_bi_chan",
                T + "test_ket_noi_tich_hop.py::test_luu_noi_dung_sai_bi_422_va_dung_thi_khach_nhan_cau_moi",
                T + "test_ket_noi_tich_hop.py::test_noi_dung_env_hong_thi_lui_ve_mac_dinh_khong_im",
                T + "test_ket_noi_tich_hop_pg.py::test_hai_tin_toi_cung_luc_chi_mot_thong_bao")),
        YeuCau("Kênh: danh sách plugin kênh, nhiều tài khoản mỗi nền tảng, trạng thái từng tài "
               "khoản (chi tiết ở mục 20)", DAT,
               (T + "test_ket_noi_tich_hop_pg.py::test_tuy_chon_an_binh_luan_theo_trang_va_danh_sach_plugin",)),
        YeuCau("Mỗi tài khoản kênh MỘT trạng thái suy từ sức khoẻ thật (Chưa kết nối / Hoạt động / "
               "Tạm ngắt / Cần xác thực lại / Lỗi); mã kỹ thuật dịch thành nguyên nhân + cách sửa", DAT,
               (T + "test_ket_noi_hop_nhat.py::test_trang_thai_hop_nhat",
                T + "test_ket_noi_hop_nhat.py::test_moi_trang_thai_tai_khoan_deu_co_loi_giai_thich",
                T + "test_ket_noi_hop_nhat_pg.py::test_suc_khoe_tong_tra_mot_trang_thai_va_giai_thich")),
        YeuCau("Dòng thời gian từng tài khoản kênh (sức khoẻ, sự kiện, cấu hình) và lịch sử cấu hình "
               "lọc theo dịch vụ, thời gian; theo quyền và phạm vi kênh", DAT,
               (T + "test_ket_noi_hop_nhat_pg.py::test_dong_thoi_gian_gop_ba_so_va_bo_nhip_tim",
                T + "test_ket_noi_hop_nhat.py::test_dong_thoi_gian_ngoai_pham_vi_kenh_la_404",
                T + "test_ket_noi_hop_nhat_pg.py::test_lich_su_cau_hinh_loc_thoi_gian_o_may_chu")),
        YeuCau("Ẩn bình luận có SĐT: tuỳ chọn riêng từng Trang thắng cấu hình chung", DAT,
               (T + "test_ket_noi_tich_hop.py::test_tuy_chon_rieng_cua_trang_thang_cau_hinh_chung",
                T + "test_ket_noi_tich_hop.py::test_tuy_chon_trang_can_quyen_kenh_sua")),
        YeuCau("Cấu hình VietQR không hiện trên giao diện (mã giữ nguyên)", NGOAI,
               (T + "test_cay_menu.py::test_csat_va_vietqr_khong_hien_nhung_ma_con",),
               bang="8.10–8.11"),
        YeuCau("CSAT tạm hoãn, mặc định tắt", NGOAI, (T + "test_cay_menu.py::test_csat_mac_dinh_tat",),
               bang="8.10–8.11"),
    ),
        ma=("agent/ket_noi_tich_hop.py", "agent/api/ket_noi_tich_hop.py", "agent/omnichannel/thong_bao_ai.py",
            "agent/migrations/versions/0057_ket_noi_tich_hop.sql",
            "dashboard/src/22-ket-noi-tich-hop.js", "dashboard/src/23-ai-co-ban.js",
            "agent/omnichannel/giai_thich_loi_kenh.py", "dashboard/src/18a-ket-noi-tai-khoan.js",
            "dashboard/src/22b-ket-noi-lich-su.js"),
        api=("GET /api/ket-noi", "GET /api/ket-noi/ai", "PUT /api/ket-noi/dich-vu/{ma}",
             "POST /api/ket-noi/dich-vu/{ma}/kiem-tra", "GET /api/ket-noi/webhook",
             "GET /api/ket-noi/lich-su", "PUT /api/ket-noi/kenh/{account_id}/tuy-chon",
             "GET /api/ket-noi/kenh/{account_id}/dong-thoi-gian"),
        giao_dien=("tab:cc-ket-noi", "tab:ai-co-ban"),
        nghiem_thu=("test_04_noi_kenh_va_tat_agent_theo_kenh",
                    "test_16_khach_doi_gap_nhan_vien_thi_chuyen_nguoi_that",
                    "test_17_webhook_ghtk_dang_form_cap_nhat_don"),
        lech=("Bản này sửa hai lỗi hỏng im lặng: MODEL_CHAT đổi trên dashboard trước đây không có "
              "hiệu lực; token GHN và khoá ERPNext đổi trên dashboard trước đây cần khởi động lại.",),
    ),
    Muc(9, "Phân biệt hội thoại nhóm và cá nhân", (
        YeuCau("Hội thoại nhóm mang danh tính NHÓM; người gửi tách riêng từng tin; thiếu tên nhóm "
               "thì tên dự phòng, không lấy tên người gửi", DAT,
               (T + "test_tin_nhom_zalo.py::test_tin_nhom_danh_tinh_la_nhom_nguoi_gui_tach_rieng",
                T + "test_tin_nhom_zalo.py::test_ingest_nhom_hai_nguoi_gui_khong_doi_danh_tinh",
                T + "test_tin_nhom_zalo.py::test_thieu_ten_nhom_thi_ten_du_phong_khong_lay_ten_nguoi_gui")),
        YeuCau("Huy hiệu Nhóm và tên người gửi trên giao diện; lọc nhóm / riêng ở hộp thư", DAT,
               (T + "test_tin_nhom_zalo.py::test_dashboard_gan_nhan_nhom_va_ten_nguoi_gui",
                T + "test_trach_nhiem_hoi_thoai.py::test_bo_loc_chua_giao_nhom_va_qua_han_sla")),
        YeuCau("Danh sách hội thoại: tin cuối của nhóm kèm tên người gửi", DAT,
               (T + "test_thanh_thong_tin_hoi_thoai.py::test_tin_cuoi_trong_nhom_kem_ten_nguoi_gui",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_api_danh_sach_tra_vai_va_ten_nguoi_gui_tin_cuoi")),
        YeuCau("Trí nhớ khách riêng không đọc, không ghi cho nhóm (chống lộ dữ liệu cá nhân)", DAT,
               (T + "test_tin_nhom_zalo.py::test_tri_nho_khach_khong_doc_khong_ghi_cho_nhom",)),
        YeuCau("Trả lời vào nhóm đúng loại thread", DAT,
               (T + "test_tin_nhom_zalo.py::test_tra_loi_nhom_thread_type_rong_van_gui_dung_loai",)),
        YeuCau("Hệ thống không tự nói vào nhóm: AI không chạy, CSAT không hỏi, tin hệ thống bị "
               "chặn ở outbox; nhóm được giao cho người", DAT,
               (T + "test_tin_nhom_zalo.py::test_handle_inbound_nhom_AI_khong_chay_khong_nhap_giao_nguoi",
                T + "test_tin_nhom_zalo.py::test_outbox_that_chan_he_thong_noi_vao_nhom_cho_nhan_vien_gui",
                T + "test_tin_nhom_zalo.py::test_csat_khong_hoi_trong_nhom")),
        YeuCau("Nhóm Zalo KHÔNG là khách hàng trong Customer 360: không vào danh sách, tìm kiếm, "
               "đếm khách vô chủ/khách mới; không gộp được; không có nút Customer 360", DAT,
               (T + "test_nhom_khong_phai_khach.py::test_danh_sach_va_tim_khach_khong_co_nhom",
                T + "test_nhom_khong_phai_khach.py::test_khach_vo_chu_va_khach_moi_khong_dem_nhom",
                T + "test_nhom_khong_phai_khach.py::test_khong_gop_duoc_nhom_vao_mot_nguoi",
                T + "test_nhom_khong_phai_khach.py::test_dich_vu_gop_tu_chan_nhom_khong_chi_route",
                T + "test_thanh_thong_tin_hoi_thoai.py::test_nhom_khong_co_nut_customer_360"),
               bang="9.7"),
        YeuCau("AI tham gia trả lời trong nhóm", NGOAI,
               ghi_chu="Bảng ghi là hướng phát triển sau; hiện AI không chạy trong nhóm (test ở "
                       "yêu cầu 9.6).", bang="9.10"),
    ),
        ma=("agent/channels/zalo_personal.py", "agent/omnichannel/inbox_service.py",
            "agent/omnichannel/identity.py", "agent/core/lien_he_nhom.py",
            "agent/migrations/versions/0051_tin_nhom_nguoi_gui.sql"),
        api=("GET /api/inbox/conversations",),
        giao_dien=("view:hoithoai", "view:khachhang"),
    ),
    Muc(10, "Media khách gửi", (
        YeuCau("Tải ảnh/video/tệp khách gửi về máy chủ SAU khi tin đã lưu (không chặn luồng tin); "
               "vòng tải bật lúc khởi động", DAT,
               (T + "test_media_khach_gui.py::test_tin_vao_danh_dau_cho_tai",
                T + "test_media_khach_gui.py::test_vong_tai_duoc_dung_luc_khoi_dong",
                T + "test_media_khach_gui.py::test_whatsapp_hoi_kenh_lay_link")),
        YeuCau("Chống trùng theo sha256 (một tệp mỗi nội dung)", DAT,
               (T + "test_media_khach_gui.py::test_tai_ve_chong_trung_va_phuc_vu",
                T + "test_media_khach_gui.py::test_duong_luu_theo_nam_thang_va_sha")),
        YeuCau("Thời hạn lưu tính từ lần gửi GẦN NHẤT, đổi được trên dashboard; dọn tệp mồ côi; "
               "xem trước rồi mới xoá; không bao giờ xoá ngoài thư mục media/uploads", DAT,
               (T + "test_media_khach_gui.py::test_mac_dinh_180_ngay_theo_quyet_dinh_chu_du_an",
                T + "test_media_khach_gui.py::test_cau_hinh_thoi_han_kiem_gia_tri",
                T + "test_media_khach_gui.py::test_don_theo_thoi_han_tinh_lan_gui_gan_nhat",
                T + "test_media_khach_gui.py::test_don_mo_coi_va_danh_dau_mat_tep",
                T + "test_media_khach_gui.py::test_khong_bao_gio_xoa_anh_san_pham_hay_tai_lieu")),
        YeuCau("Trần dung lượng mỗi tệp, đọc theo luồng; nhận dạng kiểu theo chữ ký đầu tệp, không "
               "tin header", DAT,
               (T + "test_media_khach_gui.py::test_vuot_tran_thi_dung_doc_ngay_khong_doc_tron",
                T + "test_media_khach_gui.py::test_content_length_vuot_tran_thi_khong_tai",
                T + "test_media_khach_gui.py::test_nhan_dang_theo_chu_ky_dau_tep",
                T + "test_media_khach_gui.py::test_html_gia_anh_bi_bo_va_khong_de_lai_tep")),
        YeuCau("Thử lại có giãn cách, có trần; link chết thành \"hết hạn\"; lỗi mạng không ném", DAT,
               (T + "test_media_khach_gui.py::test_gian_cach_thu_lai_tang_dan_co_tran",
                T + "test_media_khach_gui.py::test_hong_tam_thi_hen_thu_lai_roi_bao_loi",
                T + "test_media_khach_gui.py::test_ma_http_ra_trang_thai",
                T + "test_media_khach_gui.py::test_mang_hong_la_hong_tam_khong_nem")),
        YeuCau("Phục vụ bản trên máy với kiểu máy chủ nhận dạng (nosniff); hộp thư và AI ưu tiên "
               "bản trên máy", DAT,
               (T + "test_media_khach_gui.py::test_duong_phuc_vu_tep_dung_kieu_may_chu_nhan_dang",
                T + "test_media_khach_gui.py::test_hop_thu_dashboard_uu_tien_ban_tren_may",
                T + "test_media_khach_gui.py::test_agent_hoi_ban_tren_may_truoc")),
        YeuCau("Xoá dữ liệu khách (PDPD) xoá ngay media của khách, trừ nội dung người khác còn giữ; "
               "sao lưu gồm media", DAT,
               (T + "test_media_khach_gui.py::test_pdpd_xoa_media_cua_khach_tru_noi_dung_nguoi_khac_con_giu",
                T + "test_media_khach_gui.py::test_pdpd_ghi_tham_chieu_TRUOC_khi_xoa_hoi_thoai",
                T + "test_media_khach_gui.py::test_sao_luu_gom_media_bo_tep_tam_va_khong_de_ban_ro")),
        YeuCau("Khung \"Media khách gửi\" ở Hệ thống > Sao lưu & Bảo trì; mọi route media khai quyền",
               DAT, (T + "test_media_khach_gui.py::test_dashboard_gan_khung_media",
                     T + "test_media_khach_gui.py::test_route_media_deu_khai_quyen")),
    ),
        ma=("agent/omnichannel/media.py", "agent/omnichannel/media_don.py", "agent/api/media_api.py",
            "agent/core/anh_khach.py", "agent/migrations/versions/0063_media_khach_gui.sql",
            "dashboard/src/25-media.js"),
        api=("GET /api/media/tong-quan", "POST /api/media/don", "POST /api/media/thu-lai"),
        giao_dien=("tab:ht-sao-luu",),
        lech=("Bảng ghi mục này \"cần làm rõ\"; hiện thực theo quyết định đã chốt khi rà soát "
              "20.11.2026: tải về máy chủ, giữ theo thời hạn, chống trùng.",
              "Trước bản này media khách gửi KHÔNG được lưu: `attachments.url` chỉ giữ link CDN của "
              "hãng, hết hạn là mất hẳn."),
        hoi=("Chưa có trần TỔNG dung lượng cho thư mục media (chỉ trần từng tệp và thời hạn lưu). "
             "Có cần trần tổng / cảnh báo đầy đĩa không?",),
        them=_mac_dinh_media,
    ),
    Muc(12, "Phân quyền RBAC theo chức năng", (
        YeuCau("Danh mục quyền nhóm theo chức năng của dashboard, mỗi quyền đúng một nhóm, đúng thứ "
               "tự phiếu việc", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_moi_quyen_nam_trong_dung_mot_nhom_hien_thi",
                T + "test_nhan_su_phan_quyen.py::test_nhom_dung_thu_tu_phieu_viec",
                T + "test_nhan_su_phan_quyen.py::test_quyen_tach_rieng_theo_phieu_viec",
                T + "test_quyen_danh_muc.py::test_moi_quyen_co_nhan_tieng_viet")),
        YeuCau("Hỏng-đóng: route `/api` chưa khai quyền thì máy chủ không khởi động; tên quyền lạ "
               "nổ lúc import", DAT,
               (T + "test_quyen_danh_muc.py::test_moi_route_deu_da_khai_quyen",
                T + "test_quyen_danh_muc.py::test_chot_that_su_chan_route_quen_khai_quyen",
                T + "test_quyen_danh_muc.py::test_khoi_dong_that_su_goi_chot",
                T + "test_can_quyen.py::test_nem_ngay_luc_goi_neu_quyen_khong_co_trong_danh_muc")),
        YeuCau("Thiếu quyền thì 403 nói rõ thiếu gì; chưa đăng nhập thì 401; nhiều quyền là phải "
               "đủ tất cả", DAT,
               (T + "test_can_quyen.py::test_thieu_quyen_thi_403_va_noi_ro_thieu_gi",
                T + "test_can_quyen.py::test_chua_dang_nhap_thi_401_chu_khong_403",
                T + "test_can_quyen.py::test_nhieu_quyen_la_phai_co_du_khong_phai_mot_trong_so")),
        YeuCau("Chống leo thang: không tự gán Quản trị, không tạo/sửa vai trò mạnh hơn mình, không "
               "hạ cấp hay khoá cấp trên", DAT,
               (T + "test_chan_leo_thang_quyen.py::test_khong_tu_gan_quan_tri_cho_minh",
                T + "test_chan_leo_thang_quyen.py::test_khong_tao_vai_tro_co_quyen_minh_khong_co",
                T + "test_chan_leo_thang_quyen.py::test_khong_sua_hay_xoa_vai_tro_manh_hon_minh",
                T + "test_chan_leo_thang_quyen.py::test_khong_ha_cap_hay_khoa_cap_tren")),
        YeuCau("Lịch sử đổi quyền có trước/sau, ghi trong cùng giao dịch; xem cần quyền nhân sự", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_lich_su_doi_quyen_ghi_truoc_sau",
                T + "test_nhan_su_phan_quyen.py::test_lich_su_can_quyen_doc_nhan_su",
                T + "test_nhan_su_phan_quyen.py::test_moi_loai_lich_su_deu_hien_tren_man_lich_su")),
        YeuCau("Đổi vai trò có hiệu lực ngay với người đang đăng nhập", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_doi_vai_tro_co_hieu_luc_ngay_voi_nguoi_dang_dang_nhap",)),
        YeuCau("Quyền tách theo việc: duyệt nháp AI cần `ai.duyet`, Kho có quyền riêng; tên quyền "
               "đã gỡ không bao giờ dùng lại", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_duyet_ban_nhap_can_ai_duyet_khong_phai_tra_loi",
                T + "test_nhan_su_phan_quyen.py::test_kho_co_quyen_rieng",
                T + "test_quyen_danh_muc.py::test_quyen_da_go_khong_bao_gio_dung_lai_ten")),
        YeuCau("Quyền riêng từng người, ABAC, phạm vi Cá nhân/Nhóm/Tất cả", NGOAI,
               ghi_chu="Bảng chốt chỉ RBAC qua vai trò."),
    ),
        ma=("agent/core/quyen.py", "agent/api/quyen.py", "agent/api/phu_thuoc.py",
            "agent/core/xac_thuc.py"),
        api=("GET /api/quyen", "GET /api/vai-tro", "POST /api/vai-tro", "PUT /api/vai-tro/{vai_tro_id}",
             "PUT /api/nguoi-dung/{nguoi_dung_id}/vai-tro", "GET /api/nhan-su/lich-su"),
        giao_dien=("tab:ns-vai-tro",),
        nghiem_thu=("test_02_phan_quyen_hong_dong_theo_vai_tro",),
        lech=("Phạm vi theo KÊNH (thành viên kênh — người chỉ thấy hội thoại/khách của kênh mình "
              "được giao) có từ trước bảng và vẫn giữ; nó không phải quyền riêng từng người mà là "
              "phạm vi dữ liệu.",),
        hoi=("Giữ phạm vi theo kênh (thành viên kênh) như hiện nay — có mâu thuẫn với câu \"không "
             "phạm vi Cá nhân/Nhóm/Tất cả\" của bảng không?",),
        them=_bang_quyen,
    ),
    Muc(13, "Vai trò động và quản lý nhân viên", (
        YeuCau("Hai tab Nhân viên / Vai trò trong Nhân sự & Phân quyền", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_hai_tab_nhan_su_gan_vao_khung_tab",
                T + "test_nhan_su_phan_quyen.py::test_giao_dien_goi_dung_cac_duong_moi")),
        YeuCau("Vai trò động tạo/sửa không cần sửa mã; ngừng dùng / dùng lại; xoá hẳn chỉ khi "
               "chưa từng gán; vai trò dựng sẵn luôn dùng", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_vai_tro_ngung_dung_khong_gan_moi_duoc_va_khong_xoa_duoc",
                T + "test_nhan_su_phan_quyen.py::test_csdl_chan_gan_vai_tro_ngung_dung_va_ngung_vai_tro_he_thong",
                T + "test_nhan_su_phan_quyen.py::test_khong_ngung_dung_hay_dung_lai_vai_tro_manh_hon_minh")),
        YeuCau("Vai trò ngừng dùng không cấp quyền ở BẤT KỲ chỗ tính quyền nào (phiên, chuông, "
               "PDPD, giao khách...)", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_moi_cho_tinh_quyen_deu_loc_vai_tro_ngung_dung",
                T + "test_nhan_su_phan_quyen.py::test_phep_quet_tren_that_su_bat_duoc_cho_quen")),
        YeuCau("Nhân viên: tạo kèm email + vai trò một lượt; sửa họ tên/email; email duy nhất", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_sua_thong_tin_nhan_vien_va_email_duy_nhat",)),
        YeuCau("Khoá nhân viên: cảnh báo việc đang giữ, chuyển việc hàng loạt qua đúng luật giao; "
               "bỏ qua phải nói rõ và được ghi lại; khoá là mất phiên ngay", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_khoa_nguoi_dang_giu_viec_thi_canh_bao_roi_chuyen_viec",
                T + "test_nhan_su_phan_quyen.py::test_khoa_de_lai_viec_phai_noi_ro_va_duoc_ghi_lai",
                T + "test_nhan_su_phan_quyen.py::test_chuyen_viec_can_dung_quyen_va_khong_lay_viec_cap_tren",
                T + "test_nhan_su_phan_quyen.py::test_khoa_tren_man_hinh_hoi_ve_viec_dang_giu",
                T + "test_nghiem_thu_saas.py::test_03_khoa_nhan_vien_da_moi_phien")),
        YeuCau("Không xoá nhân viên (chỉ khoá) — bộ sinh bảng kiểm không có route DELETE nào dưới "
               "`/api/nguoi-dung`", DAT,
               (T + "test_bang_yeu_cau.py::test_khong_co_route_bi_cam",)),
        YeuCau("Nâng cấp CSDL giữ nguyên ai làm được gì (cấp quyền mới cho đúng vai trò đang làm "
               "được việc ấy)", DAT,
               (T + "test_nhan_su_phan_quyen.py::test_migration_0058_giu_nguyen_ai_lam_duoc_gi",)),
    ),
        ma=("agent/api/tai_khoan.py", "agent/api/nhan_su.py", "agent/api/quyen.py",
            "agent/migrations/versions/0058_nhan_su_phan_quyen.sql", "dashboard/src/24-nhan-su.js"),
        api=("GET /api/nguoi-dung", "POST /api/nguoi-dung", "PUT /api/nguoi-dung/{nguoi_dung_id}",
             "POST /api/nguoi-dung/{ten}/khoa", "GET /api/nguoi-dung/{nguoi_dung_id}/viec-dang-giu",
             "POST /api/nguoi-dung/{nguoi_dung_id}/chuyen-viec",
             "POST /api/vai-tro/{vai_tro_id}/trang-thai", "DELETE /api/vai-tro/{vai_tro_id}"),
        giao_dien=("view:nhansu", "tab:ns-nhan-vien", "tab:ns-vai-tro"),
        nghiem_thu=("test_03_khoa_nhan_vien_da_moi_phien",),
    ),
    Muc(14, "Phân công công việc", (
        YeuCau("Trạng thái chuẩn: Chờ xử lý, Đang thực hiện, Hoàn thành, Đã hủy; \"Chưa phân "
               "công\" là bộ lọc, không phải trạng thái", DAT,
               (T + "test_he_thong_giao_viec.py::test_nhan_trang_thai_theo_phieu_viec_ma_giu_nguyen",)),
        YeuCau("AI chuyển giao KHÔNG tự tạo công việc — báo qua chuông thông báo", DAT,
               (T + "test_thong_bao_noi_bo.py::test_ai_chuyen_giao_sinh_THONG_BAO_khong_sinh_CONG_VIEC",
                T + "test_thong_bao_noi_bo.py::test_khong_con_duong_tu_sinh_viec_khi_chuyen_giao"),
               bang="14.2"),
        YeuCau("Tự phân công xoay vòng: người trong ca CÓ lịch, sẵn sàng, đúng kênh, lâu nhất chưa "
               "được giao; không ai thì Chưa phân công và báo người điều phối", DAT,
               (T + "test_he_thong_giao_viec.py::test_tu_dong_xoay_vong_nguoi_trong_ca_lau_nhat_chua_duoc_giao",
                T + "test_he_thong_giao_viec.py::test_tu_dong_loai_nguoi_ngoai_ca_chua_co_lich_tat_san_sang",
                T + "test_he_thong_giao_viec.py::test_khong_ai_du_dieu_kien_thi_chua_phan_cong_va_bao_dieu_phoi",
                T + "test_he_thong_giao_viec.py::test_tu_dong_chi_giao_nguoi_thuoc_kenh_cua_hoi_thoai")),
        YeuCau("Lịch sử mọi đường đổi người nhận / trạng thái / kết quả (trigger CSDL, kể cả đường "
               "không qua API công việc)", DAT,
               (T + "test_he_thong_giao_viec.py::test_lich_su_ghi_tao_giao_chuyen_trang_thai_ket_qua_tien_do",
                T + "test_he_thong_giao_viec.py::test_lich_su_ghi_ca_duong_khong_qua_api_cong_viec",
                T + "test_he_thong_giao_viec.py::test_chuyen_viec_o_man_nhan_su_ghi_lich_su_dung_nguoi")),
        YeuCau("Liên kết hội thoại / khách / đơn bấm được; tạo việc từ hội thoại; chặn gắn hội thoại "
               "kênh khác; không giao cho người không xem được việc", DAT,
               (T + "test_he_thong_giao_viec.py::test_lien_ket_hoi_thoai_khach_don_bam_duoc",
                T + "test_he_thong_giao_viec.py::test_tao_cong_viec_tu_hoi_thoai",
                T + "test_he_thong_giao_viec.py::test_tao_tu_hoi_thoai_kenh_khac_thi_404",
                T + "test_he_thong_giao_viec.py::test_giao_cho_nguoi_khong_xem_duoc_viec_thi_422")),
        YeuCau("Chuông cho việc chưa giao, bị huỷ, quá hạn (báo một lần, báo lại khi đổi hạn)", DAT,
               (T + "test_he_thong_giao_viec.py::test_qua_han_bao_mot_lan_va_bao_lai_khi_doi_han",
                T + "test_he_thong_giao_viec.py::test_huy_viec_bao_nguoi_dang_lam",
                T + "test_he_thong_giao_viec.py::test_chuong_cong_viec_mo_chi_tiet_viec")),
        YeuCau("Tổng quan ca trực theo phạm vi: ai trong ca, hội thoại chưa ai nhận, cảnh báo SLA; "
               "nhân viên thường không thấy tải của đồng nghiệp", DAT,
               (T + "test_he_thong_giao_viec.py::test_tong_quan_dem_theo_pham_vi_va_nguoi_trong_ca",
                T + "test_he_thong_giao_viec.py::test_tong_quan_nhan_vien_thuong_khong_thay_tai_dong_nghiep")),
        YeuCau("Lịch ca trực và lịch nghỉ; bộ định tuyến chỉ giao cho người đang trong ca", DAT,
               (T + "test_lich_ca.py::test_bo_dinh_tuyen_bo_qua_nguoi_het_ca",
                T + "test_lich_ca.py::test_lich_nghi_thang_ca_truc",
                T + "test_lich_ca.py::test_bo_dinh_tuyen_khong_giao_cho_nguoi_bi_khoa")),
        YeuCau("Quy tắc tự động tạo việc có tuỳ chọn tự phân công", DAT,
               (T + "test_he_thong_giao_viec.py::test_quy_tac_tao_viec_nhan_giao_tu_dong_va_chan_gia_tri_la",)),
    ),
        ma=("agent/core/cong_viec.py", "agent/core/giao_viec.py", "agent/api/cong_viec.py",
            "agent/api/lich_ca.py", "agent/migrations/versions/0061_he_thong_giao_viec.sql",
            "dashboard/src/25-cong-viec.js", "dashboard/src/16-lich-ca.js"),
        api=("GET /api/cong-viec", "POST /api/cong-viec", "GET /api/cong-viec/tong-quan",
             "GET /api/cong-viec/{cong_viec_id}", "PUT /api/cong-viec/{cong_viec_id}",
             "POST /api/cong-viec/{cong_viec_id}/tien-do", "POST /api/cong-viec/{cong_viec_id}/tu-dong-giao"),
        giao_dien=("view:congviec", "tab:cv-ca-truc", "tab:cv-danh-sach"),
        nghiem_thu=("test_07_chuyen_giao_bao_nguoi_va_giao_viec", "test_14_lich_ca_va_lich_nghi",
                    "test_21_he_thong_giao_viec_theo_ca_chuyen_viec_va_lich_su"),
        lech=("Việc do AI đề xuất (yêu cầu huỷ đơn chuyển cho người) giữ nguồn agent, chưa phân "
              "công và báo người điều phối — AI không tự tạo việc rời.",),
    ),
    Muc(15, "SLA", (
        YeuCau("Ba mục tiêu: phản hồi đầu, phản hồi sau chuyển giao, giải quyết; mỗi mục tiêu chế "
               "độ riêng (theo giờ làm việc / 24-7) và ngưỡng cảnh báo riêng", DAT,
               (T + "test_sla_muc_tieu_lich.py::test_che_do_va_nguong_theo_muc_tieu",
                T + "test_sla_muc_tieu_lich.py::test_chuan_hoa_muc_tieu_chan_luc_luu",
                T + "test_sla_muc_tieu_lich.py::test_luu_chinh_sach_khong_gui_o_nao_thi_giu_o_ay")),
        YeuCau("Một lịch làm việc chung (giờ từng thứ, ngày nghỉ, ngày lễ) là nguồn duy nhất cho "
               "hạn SLA, câu báo ngoài giờ và điều kiện ngoài giờ của quy tắc", DAT,
               (T + "test_sla_muc_tieu_lich.py::test_lich_tuan_ngay_nghi_ngay_le_va_cau_bao_ngoai_gio",
                T + "test_sla_muc_tieu_lich.py::test_moi_noi_doc_gio_lam_viec_deu_qua_lich_chung",
                T + "test_sla_muc_tieu_lich.py::test_sla_han_lich_trong_sql_khop_python",
                T + "test_sla_muc_tieu_lich.py::test_tinh_tay_qua_ngay_nghi_va_ngay_le")),
        YeuCau("Hạn phản hồi sau chuyển giao: mỗi lượt chuyển một hạn; cảnh báo, vi phạm, chuông, "
               "chốt khi nhân viên trả lời", DAT,
               (T + "test_sla_muc_tieu_lich.py::test_chuyen_giao_mo_luot_canh_bao_vi_pham_chuong_va_chot",
                T + "test_sla_muc_tieu_lich.py::test_nhan_vien_nhan_truoc_khi_vong_quet_mo_luot_thi_dat",
                T + "test_sla_muc_tieu_lich.py::test_moc_chuyen_giao_tra_dung_ten_migration")),
        YeuCau("Xác nhận tự động (tin hệ thống) không tính là phản hồi đầu", DAT,
               (T + "test_sla_muc_tieu_lich.py::test_xac_nhan_tu_dong_khong_dat_phan_hoi_dau",
                T + "test_sla_muc_tieu_lich.py::test_moi_nguon_xac_nhan_tu_dong_xep_hang_vai_system")),
        YeuCau("Ngưỡng cảnh báo cấu hình được, áp cho cả phản hồi đầu và giải quyết", DAT,
               (T + "test_phan_tich_va_sla.py::test_canh_bao_han_giai_quyet_o_nguong_mac_dinh_80",
                T + "test_phan_tich_va_sla.py::test_nguong_canh_bao_cau_hinh_duoc_va_ap_ca_phan_hoi_dau")),
        YeuCau("Trễ SLA báo chuông người phụ trách và quản lý; KHÔNG sinh công việc", DAT,
               (T + "test_phan_tich_va_sla.py::test_tre_sla_ghi_su_kien_du_thong_tin_va_khong_sinh_cong_viec",
                T + "test_thong_bao_noi_bo.py::test_sla_tre_bao_nguoi_phu_trach_va_quan_ly")),
        YeuCau("Đổi ưu tiên bắt buộc lý do, ghi nhật ký; nâng ưu tiên rút hạn từ bây giờ, hạ ưu "
               "tiên giữ hạn (trigger CSDL chỉ cho rút ngắn)", DAT,
               (T + "test_phan_tich_va_sla.py::test_nang_uu_tien_rut_han_tu_bay_gio_ha_uu_tien_giu_han",
                T + "test_phan_tich_va_sla.py::test_trigger_chi_cho_rut_ngan_han_con_o_tuong_lai",
                T + "test_phan_tich_va_sla.py::test_doi_uu_tien_ngoai_kenh_la_404_va_can_quyen")),
        YeuCau("Chỉ số SLA ở Phân tích: đúng hạn, vi phạm, xu hướng; mục tiêu sau chuyển giao; "
               "giải quyết AI / nhân viên", DAT,
               (T + "test_sla_muc_tieu_lich.py::test_phan_tich_muc_tieu_chuyen_giao_va_giai_quyet_ai_nhan_vien",)),
        YeuCau("Tab SLA & Giờ làm việc; lịch và mục tiêu lưu trên dashboard có hiệu lực ở mọi nơi",
               DAT, (T + "test_sla_muc_tieu_lich.py::test_giao_dien_sla_gan_tab_va_khong_trung_o_cau_hinh",
                     T + "test_sla_muc_tieu_lich.py::test_api_lich_va_muc_tieu_co_hieu_luc_o_moi_noi")),
    ),
        ma=("agent/omnichannel/sla.py", "agent/omnichannel/sla_muc_tieu.py",
            "agent/omnichannel/sla_chuyen_giao.py", "agent/omnichannel/phan_hoi_that.py",
            "agent/core/lich_lam_viec.py", "agent/api/sla_cau_hinh.py", "agent/api/uu_tien.py",
            "agent/migrations/versions/0054_phan_tich_va_sla.sql",
            "agent/migrations/versions/0062_sla_muc_tieu_va_lich_lam_viec.sql", "dashboard/src/26-sla.js"),
        api=("GET /api/sla/cau-hinh", "PUT /api/sla/lich-lam-viec", "PUT /api/sla/muc-tieu",
             "PUT /api/conversations/{cid}/uu-tien"),
        giao_dien=("tab:cc-sla",),
        nghiem_thu=("test_19_doi_uu_tien_rut_han_sla_va_man_phan_tich",),
        lech=("Chưa ai lưu lịch/mục tiêu trên dashboard thì hệ thống lui về `.env` như trước "
              "(`SLA_THEO_GIO_LAM_VIEC` áp cho MỌI mục tiêu).",),
        hoi=("\"Leo thang khi quá hạn\" hiện là báo chuông thêm người quản lý (và tuỳ chọn "
             "`SLA_KHI_TRE` nâng ưu tiên, không rút hạn) — không có chuỗi leo thang nhiều bậc. Đủ "
             "chưa?",),
        them=_mac_dinh_sla,
    ),
    Muc(16, "Gợi ý có căn cứ và \"Xem căn cứ\"", (
        YeuCau("Bản nháp AI được phân loại căn cứ ở MÁY CHỦ: đủ / chưa đầy đủ (nói rõ thiếu gì) / "
               "không có / mâu thuẫn", DAT,
               (T + "test_can_cu_ban_nhap.py::test_du_can_cu",
                T + "test_can_cu_ban_nhap.py::test_chua_day_du_noi_ro_thieu_gi",
                T + "test_can_cu_ban_nhap.py::test_khong_co_can_cu_kem_cau_cho_trung_lap",
                T + "test_can_cu_ban_nhap.py::test_mau_thuan_cung_cong_cu_hai_ket_qua",
                T + "test_can_cu_ban_nhap.py::test_mau_thuan_gia_danh_muc_va_tai_lieu",
                T + "test_can_cu_ban_nhap.py::test_mau_thuan_trang_thai_don_giua_hai_cong_cu",
                T + "test_can_cu_ban_nhap.py::test_tai_lieu_cung_gia_thi_khong_mau_thuan")),
        YeuCau("\"Xem căn cứ\": tài liệu kèm trích đoạn, dữ liệu công cụ trả về, quy tắc và lớp "
               "lưới đã áp", DAT,
               (T + "test_trach_nhiem_giao_dien.py::test_xem_can_cu_tren_ban_nhap_va_chi_tiet_tung_tin",
                T + "test_dau_vet_ai.py::test_tri_thuc_kem_trich_doan_cat_ngan_cho_nut_xem_can_cu")),
        YeuCau("Không hiển thị độ tin cậy dạng % ở bất kỳ đâu (kể cả Phòng thử)", DAT,
               (T + "test_can_cu_ban_nhap.py::test_nhan_khong_co_phan_tram",
                T + "test_trach_nhiem_giao_dien.py::test_khong_hien_ky_thuat_mac_dinh_va_khong_phan_tram_tin_cay",
                T + "test_uy_quyen_ai.py::test_mo_ta_khong_co_phan_tram"),
               bang="16.8"),
        YeuCau("Không có căn cứ thì lưới tin cậy thấp chuyển người; tin chuyển người không bao giờ "
               "tự gửi", DAT,
               (T + "test_can_cu_ban_nhap.py::test_khong_tai_lieu_khong_du_lieu_thi_luoi_tin_cay_thap_chuyen_nguoi",
                T + "test_can_cu_ban_nhap.py::test_tin_chuyen_nguoi_khong_bao_gio_tu_gui")),
        YeuCau("Phân loại hỏng không làm mất dấu vết, và nói là hỏng", DAT,
               (T + "test_can_cu_ban_nhap.py::test_dau_vet_mang_phan_loai_va_khong_lam_vo_dau_vet_khi_hong",)),
    ),
        ma=("agent/core/dau_vet_ai.py", "agent/core/agent.py", "dashboard/src/19-trach-nhiem.js"),
        giao_dien=("view:hoithoai",),
        lech=("\"Mâu thuẫn\" phát hiện theo LUẬT, ba loại: cùng công cụ cùng tham số trả hai giá trị "
              "khác nhau; trạng thái đơn ở sổ đơn khác tra vận chuyển; giá danh mục khác giá ghi "
              "trong tài liệu về chính sản phẩm ấy. Mâu thuẫn ngữ nghĩa giữa hai đoạn văn xuôi "
              "KHÔNG được phát hiện.",),
    ),
    Muc(17, "Ba cấp ủy quyền hành động của AI", (
        YeuCau("Chính sách theo từng hành động: Không sử dụng / Có phê duyệt / Tự động; mặc định "
               "đúng phiếu việc; ngưỡng tự chốt đơn là chính sách của \"tạo đơn\"", DAT,
               (T + "test_uy_quyen_ai.py::test_mac_dinh_dung_phieu_viec",
                T + "test_uy_quyen_ai.py::test_tu_dong_theo_muc_va_nguong",
                T + "test_uy_quyen_ai.py::test_moi_cong_cu_viet_san_deu_duoc_xep_loai",
                T + "test_uy_quyen_ai.py::test_cong_cu_hanh_dong_tro_vao_hanh_dong_co_duong_thi_hanh")),
        YeuCau("Chốt ở cửa thi hành công cụ (backend), không ở prompt: hành động lạ = Không sử "
               "dụng; mức rác trong CSDL về mặc định, không về Tự động; plugin loại lạ bị chặn", DAT,
               (T + "test_uy_quyen_ai.py::test_hanh_dong_la_la_khong_su_dung",
                T + "test_uy_quyen_ai.py::test_muc_rac_trong_csdl_ve_mac_dinh_khong_ve_tu_dong",
                T + "test_uy_quyen_ai.py::test_plugin_loai_la_bi_chan",
                T + "test_uy_quyen_ai.py::test_ba_tap_cong_cu_khong_giao_nhau")),
        YeuCau("Chế độ Gợi ý (và hội thoại \"Duyệt trước khi gửi\") biến mọi hành động ghi thành "
               "đề xuất — kể cả công cụ ghi MCP", DAT,
               (T + "test_uy_quyen_ai.py::test_goi_y_KHONG_ghi_don_chi_de_xuat",
                T + "test_uy_quyen_ai.py::test_duyet_rieng_cua_hoi_thoai_tinh_nhu_goi_y",
                T + "test_uy_quyen_ai.py::test_khong_doc_duoc_co_rieng_thi_xu_ly_nhu_goi_y",
                T + "test_uy_quyen_ai.py::test_mcp_ghi_bi_chan_o_che_do_goi_y")),
        YeuCau("Thẻ phê duyệt trong hội thoại; duyệt chạy lại đúng hàm của người làm tay và KIỂM "
               "LẠI điều kiện (giá đổi thì từ chối); một đề xuất mở mỗi việc; hết hạn", DAT,
               (T + "test_uy_quyen_ai.py::test_thi_hanh_de_xuat_tu_choi_khi_gia_doi",
                T + "test_uy_quyen_ai.py::test_mot_de_xuat_dang_mo_cho_moi_viec",
                T + "test_uy_quyen_ai_csdl.py::test_huy_don_de_xuat_duyet_mot_lan_va_thi_hanh_kiem_lai",
                T + "test_uy_quyen_ai_csdl.py::test_goi_y_khong_ghi_don_duyet_thi_len_don_kiem_lai",
                T + "test_uy_quyen_ai_csdl.py::test_tu_choi_don_cho_duyet_tra_kho_va_het_han_khong_thi_hanh")),
        YeuCau("Người duyệt cần `ai.duyet` + quyền nghiệp vụ của hành động + phạm vi kênh; duyệt ở "
               "màn Đơn hàng đóng thẻ đề xuất", DAT,
               (T + "test_uy_quyen_ai_csdl.py::test_quyen_va_pham_vi_kenh_khi_duyet",
                T + "test_uy_quyen_ai_csdl.py::test_duyet_o_man_don_hang_dong_the_de_xuat")),
        YeuCau("AI không có đường ghi chính sách; sửa chính sách cần `agent.dieu_khien`, kiểm hết "
               "trước khi ghi; đổi sang Không sử dụng thì đề xuất cũ không chạy", DAT,
               (T + "test_uy_quyen_ai.py::test_ai_khong_co_duong_ghi_chinh_sach",
                T + "test_uy_quyen_ai.py::test_api_sua_chinh_sach_doi_agent_dieu_khien",
                T + "test_uy_quyen_ai_csdl.py::test_api_chinh_sach_quyen_va_kiem_het_truoc_khi_ghi",
                T + "test_uy_quyen_ai_csdl.py::test_chinh_sach_doi_sang_khong_su_dung_thi_de_xuat_cu_khong_chay")),
        YeuCau("\"Chuyển nhân viên\" luôn bật (bốn trong sáu lớp lưới kết thúc bằng chuyển người)",
               DAT, (T + "test_uy_quyen_ai.py::test_chuyen_nhan_vien_khong_tat_duoc",)),
        YeuCau("Từ chối bản nháp AI: bản nháp thành huỷ, không gửi được nữa", DAT,
               (T + "test_uy_quyen_ai_csdl.py::test_tu_choi_ban_nhap_ai_khong_gui_duoc_nua",)),
        YeuCau("Mọi hành động trong danh mục áp được ba mức", MOT_PHAN,
               (T + "test_uy_quyen_ai.py::test_hanh_dong_chua_ho_tro_khong_bao_gio_tu_dong",),
               ghi_chu="Hành động chưa có đường thi hành hiện \"Chưa hỗ trợ — chuyển nhân viên\", "
                       "không đặt mức được — xem bảng bên dưới."),
    ),
        ma=("agent/core/uy_quyen.py", "agent/core/tools.py", "agent/core/thao_tac_don.py",
            "agent/api/uy_quyen_ai.py", "agent/migrations/versions/0065_uy_quyen_ai.sql",
            "dashboard/src/28-uy-quyen-ai.js"),
        api=("GET /api/ai-uy-quyen", "PUT /api/ai-uy-quyen", "GET /api/ai-de-xuat",
             "POST /api/ai-de-xuat/{de_xuat_id}/duyet", "POST /api/ai-de-xuat/{de_xuat_id}/tu-choi",
             "POST /api/messages/{message_id}/tu-choi"),
        giao_dien=("tab:ai-chinh-sach",),
        nghiem_thu=("test_22_uy_quyen_ai_de_xuat_va_phe_duyet",),
        lech=("Huỷ đơn qua AI chỉ huỷ trong hệ thống và trả hàng về kho — KHÔNG huỷ bên ERP hay hãng "
              "vận chuyển; kết quả thi hành nói rõ phần cần huỷ tay.",),
        hoi=("Thứ tự làm tiếp cho các hành động \"Chưa hỗ trợ\" (sửa đơn, hoàn tiền, giảm giá, đổi "
             "trả, tạo vận đơn, tạo công việc) — làm hành động nào trước?",),
        them=_bang_hanh_dong_ai,
    ),
    Muc(18, "Trách nhiệm giải trình của AI", (
        YeuCau("Dấu vết từng tin AI: hồ sơ agent, chế độ, ngưỡng, lưới đã bắt, công cụ (tham số đã "
               "che), tri thức, model, chi phí; có trần dung lượng; không chứa dữ liệu cá nhân", DAT,
               (T + "test_dau_vet_ai.py::test_ghi_ho_so_nguong_luoi_va_tri_thuc",
                T + "test_dau_vet_ai.py::test_ket_qua_khong_lo_van_vuot_tran_thi_rut_gon_ma_van_la_json",
                T + "test_dau_vet_ai.py::test_che_so_dien_thoai_va_an_danh_tinh_ca_khi_tat_che_du_lieu",
                T + "test_trach_nhiem_hoi_thoai.py::test_dau_vet_ai_ghi_vao_ban_nhap_va_khong_chua_du_lieu_ca_nhan",
                T + "test_trach_nhiem_hoi_thoai.py::test_dau_vet_ai_ghi_vao_tin_tu_gui")),
        YeuCau("Mã lượt AI nối mọi dòng nhật ký của một lượt; lượt đóng ở mọi lối ra", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_gan_vao_chi_trong_luot_va_khong_de_khoa",
                T + "test_nhat_ky_kiem_toan.py::test_pham_vi_luot_dong_luot_o_moi_loi_ra",
                T + "test_nhat_ky_kiem_toan.py::test_handle_inbound_mo_luot_dung_cho",
                T + "test_nhat_ky_kiem_toan.py::test_luot_ai_noi_moi_dong_va_tra_ca_luot")),
        YeuCau("Nhật ký chỉ thêm: CSDL chặn UPDATE/DELETE/TRUNCATE trên `events`", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_events_chi_them_va_loi_ra_chi_cho_delete",
                T + "test_nhat_ky_kiem_toan.py::test_han_luu_tru_van_chay_khi_nhat_ky_chi_them")),
        YeuCau("Tra cứu lọc + phân trang con trỏ, chi tiết, theo lượt, theo hội thoại; xuất CSV "
               "(việc xuất cũng được ghi lại)", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_quyen_va_che_tren_app_that",
                T + "test_nhat_ky_kiem_toan.py::test_mo_hinh_doc_chuan_hoa_tac_nhan_hoi_thoai_trang_thai")),
        YeuCau("Làm sạch lúc đọc: khoá bí mật, token theo hình dạng, giá trị bí mật đang cấu hình, "
               "SĐT/email, danh tính, suy luận model", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_lam_sach_che_bi_mat_danh_tinh_va_suy_luan",
                T + "test_nhat_ky_kiem_toan.py::test_lam_sach_che_gia_tri_bi_mat_dang_cau_hinh",
                T + "test_nhat_ky_kiem_toan.py::test_lam_sach_co_tran_va_khong_nem")),
        YeuCau("Sự cố, bước can thiệp, kết thúc, giải trình là DÒNG MỚI; dòng gốc không đổi", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_su_co_la_dong_moi_dong_goc_khong_doi",
                T + "test_nhat_ky_kiem_toan.py::test_ghi_can_quyen_su_co_doc_can_nhat_ky_hoac_hoi_thoai")),
        YeuCau("Lịch sử đề xuất / phê duyệt cùng một hình dạng", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_de_xuat_co_hinh_dang_on_dinh",
                T + "test_nhat_ky_kiem_toan.py::test_de_xuat_gom_ca_hanh_dong_ai_cung_hinh_dang")),
        YeuCau("Giao diện: tab Nhật ký ở Hệ thống & Nhật ký; \"Nhật ký hội thoại\" trong panel Chi "
               "tiết hội thoại; người sửa/duyệt ghi tên", DAT,
               (T + "test_nhat_ky_kiem_toan.py::test_dashboard_gan_tab_nhat_ky_va_nhat_ky_hoi_thoai",
                T + "test_trach_nhiem_hoi_thoai.py::test_chi_tiet_hoi_thoai_noi_ten_nguoi_gui_nguoi_sua_nguoi_duyet")),
    ),
        ma=("agent/core/nhat_ky_kiem_toan.py", "agent/core/luot_ai.py", "agent/core/dau_vet_ai.py",
            "agent/api/nhat_ky_api.py", "agent/migrations/versions/0053_dau_vet_ai_tung_tin.sql",
            "agent/migrations/versions/0064_nhat_ky_chi_them.sql", "dashboard/src/27-nhat-ky.js"),
        api=("GET /api/nhat-ky", "GET /api/nhat-ky/xuat.csv", "GET /api/nhat-ky/luot/{luot_id}",
             "GET /api/nhat-ky/hoi-thoai/{cid}", "GET /api/nhat-ky/de-xuat",
             "POST /api/nhat-ky/{event_id}/su-co", "POST /api/nhat-ky/{event_id}/giai-trinh"),
        giao_dien=("tab:ht-nhat-ky",),
        hoi=("Bảng `events` hiện không có đường xoá nào (hạn lưu trữ và PDPD không đụng bảng này), "
             "nên nhật ký lớn dần mãi. Có cần hạn lưu cho nhật ký kiểm toán không, và bao lâu?",),
    ),
    Muc(19, "Thông báo nội bộ (chuông)", (
        YeuCau("Chuông + số chưa đọc ở thanh trên; danh sách phân trang; bấm đi tới hội thoại / "
               "việc / đơn; đọc / đọc hết", DAT,
               (T + "test_thong_bao_noi_bo.py::test_chuong_nam_o_thanh_tren_khong_co_muc_dieu_huong",
                T + "test_thong_bao_noi_bo.py::test_phan_trang",
                T + "test_he_thong_giao_viec.py::test_chuong_cong_viec_mo_chi_tiet_viec")),
        YeuCau("Nguồn sự kiện: AI chuyển giao, giao hội thoại (tay và định tuyến tự động), bản "
               "nháp chờ duyệt, đơn chờ duyệt, giao việc, SLA sắp trễ / đã trễ, việc", DAT,
               (T + "test_thong_bao_noi_bo.py::test_loai_trong_ma_khop_check_cua_migration",
                T + "test_thong_bao_noi_bo.py::test_giao_hoi_thoai_cho_nguoi_khac_thi_bao",
                T + "test_thong_bao_noi_bo.py::test_dinh_tuyen_tu_dong_giao_xong_thi_bao",
                T + "test_thong_bao_noi_bo.py::test_ban_nhap_cho_duyet_thi_bao",
                T + "test_thong_bao_noi_bo.py::test_giao_viec_cho_nguoi_khac_thi_bao_tu_giao_thi_khong")),
        YeuCau("Luật người nhận: người được giao → thành viên kênh có quyền → người quản lý; SLA "
               "báo thêm quản lý", DAT,
               (T + "test_thong_bao_noi_bo.py::test_nguoi_nhan_thanh_vien_kenh_co_quyen_khong_phai_nguoi_ngoai",
                T + "test_thong_bao_noi_bo.py::test_kenh_khong_ai_phu_trach_thi_bao_nguoi_quan_ly",
                T + "test_thong_bao_noi_bo.py::test_hoi_thoai_da_giao_thi_chi_bao_nguoi_dang_cam_sla_bao_them_quan_ly")),
        YeuCau("Chống dội: khách nhắn thêm không đổ chuông lại; một thông báo chờ duyệt mỗi hội thoại",
               DAT, (T + "test_thong_bao_noi_bo.py::test_khach_nhan_them_khong_doi_chuong_va_khong_doi_tin_bao",
                     T + "test_thong_bao_noi_bo.py::test_che_do_goi_y_ban_nhap_cho_duyet_thi_bao_mot_lan_moi_hoi_thoai")),
        YeuCau("API chỉ trả thông báo của chính người đăng nhập; đánh dấu đã đọc không làm xong việc gì",
               DAT, (T + "test_thong_bao_noi_bo.py::test_api_chi_thay_cua_minh_doc_khong_lam_xong_viec_gi",
                     T + "test_thong_bao_noi_bo.py::test_api_doi_dang_nhap",
                     T + "test_thong_bao_noi_bo.py::test_moi_duong_thong_bao_duoc_khai_mien_tru_tung_cai")),
        YeuCau("Sinh thông báo hỏng không bao giờ làm hỏng lượt trả lời khách, nhưng ghi lỗi", DAT,
               (T + "test_thong_bao_noi_bo.py::test_hong_CSDL_khong_nem_vao_luot_tra_loi_nhung_ghi_loi_va_van_bao_ngoai",)),
    ),
        ma=("agent/core/thong_bao_noi_bo.py", "agent/api/thong_bao_noi_bo.py",
            "agent/migrations/versions/0055_thong_bao_noi_bo.sql", "dashboard/src/19-thong-bao.js"),
        api=("GET /api/toi/thong-bao", "GET /api/toi/thong-bao/so-chua-doc",
             "POST /api/toi/thong-bao/da-doc-het", "POST /api/toi/thong-bao/{thong_bao_id}/da-doc"),
        nghiem_thu=("test_07_chuyen_giao_bao_nguoi_va_giao_viec",
                    "test_21_he_thong_giao_viec_theo_ca_chuyen_viec_va_lich_su"),
        lech=("Thông báo nội bộ chỉ hiện trong ứng dụng (chuông). Báo động vận hành (hệ thống hỏng, "
              "khách chờ) là kênh khác — đi qua webhook của người canh gác.",),
        hoi=("Có cần đẩy thông báo nội bộ ra ngoài ứng dụng (email, Zalo, thông báo trình duyệt) "
             "cho người không mở dashboard không?",),
        them=_loai_thong_bao,
    ),
    Muc(20, "Kênh theo kiến trúc plugin", (
        YeuCau("Hợp đồng adapter chung (`ChannelAdapter`); bộ quét ra đúng các adapter; móc chưa "
               "cài đặt phải khai báo", DAT,
               (T + "test_hop_dong_kenh.py::test_quet_ra_dung_cac_adapter_da_biet",
                T + "test_hop_dong_kenh.py::test_moc_chua_cai_dat_phai_duoc_khai_bao",
                T + "test_hop_dong_kenh.py::test_moc_tuy_chon_khop_voi_base")),
        YeuCau("Mỗi plugin khai khả năng; khoá lạ nổ ngay lúc import; không khai biên nhận khi "
               "chưa có mã đọc biên nhận", DAT,
               (T + "test_kha_nang_kenh.py::test_moi_adapter_khai_du_moi_kha_nang",
                T + "test_kha_nang_kenh.py::test_khoa_kha_nang_la_thi_no_ngay",
                T + "test_kha_nang_kenh.py::test_khong_khai_bien_nhan_khi_chua_co_ma_doc_bien_nhan",
                T + "test_kha_nang_kenh.py::test_chi_kenh_co_ham_an_binh_luan_moi_khai_an_binh_luan")),
        YeuCau("Danh sách plugin + khả năng + tài khoản + webhook ở Kết nối & Tích hợp", DAT,
               (T + "test_kha_nang_kenh.py::test_moi_kenh_co_mo_ta_tren_man_ket_noi",
                T + "test_ket_noi_tich_hop_pg.py::test_tuy_chon_an_binh_luan_theo_trang_va_danh_sach_plugin")),
        YeuCau("Nhiều tài khoản mỗi nền tảng; kênh thêm bằng cấu hình; bật/tắt agent theo kênh", DAT,
               (T + "test_nghiem_thu_saas.py::test_04_noi_kenh_va_tat_agent_theo_kenh",
                T + "test_xoa_tai_khoan_kenh.py::test_co_duong_xem_truoc_rieng")),
        YeuCau("Nạp mã plugin kênh từ bên ngoài lúc chạy", NGOAI,
               ghi_chu="Không làm, có chủ ý: mã tuỳ ý chạy trong tiến trình agent nằm cùng phía với "
                       "sáu lớp lưới. Plugin KỸ NĂNG là dữ liệu chỉ đọc (docs/ky-nang.md)."),
    ),
        ma=("agent/channels/base.py", "agent/channels/factory.py", "agent/channels/registry.py",
            "agent/api/ket_noi_tich_hop.py", "agent/api/channel_accounts.py",
            "dashboard/src/22-ket-noi-tich-hop.js"),
        api=("GET /api/ket-noi",),
        giao_dien=("tab:cc-ket-noi",),
        nghiem_thu=("test_04_noi_kenh_va_tat_agent_theo_kenh",),
        lech=("Thêm một NỀN TẢNG mới vẫn cần viết một lớp adapter Python trong `agent/channels/` và "
              "đăng ký vào `factory`; thêm TÀI KHOẢN mới cho nền tảng đã có thì chỉ cần cấu hình.",
              "Telegram trong repo là kênh BÁO ĐỘNG cho người vận hành (`scripts/noi_telegram.py`), "
              "không phải kênh chăm sóc khách."),
        hoi=("Mức \"plugin\" hiện nay (hợp đồng + đăng ký + khai khả năng, thêm nền tảng cần mã) có "
             "đúng ý bảng không?",),
        them=_bang_kha_nang,
    ),
    Muc(21, "Bảng yêu cầu chức năng và phi chức năng", (
        YeuCau("Bảng sinh từ mã và kết quả kiểm thử; mọi tham chiếu kiểm mỗi lần sinh; test canh "
               "bảng cũ", DAT,
               (T + "test_bang_yeu_cau.py::test_tai_lieu_khop_ban_sinh",
                T + "test_bang_yeu_cau.py::test_moi_tham_chieu_ton_tai",
                T + "test_bang_yeu_cau.py::test_bo_kiem_bat_duoc_tham_chieu_chet")),
        YeuCau("Trạng thái mục suy từ yêu cầu con; nghiệm thu không đạt thì mục không thể \"Đạt\"",
               DAT, (T + "test_bang_yeu_cau.py::test_trang_thai_muc_suy_tu_yeu_cau_con",
                     T + "test_bang_yeu_cau.py::test_nghiem_thu_khong_dat_thi_muc_khong_dat")),
        YeuCau("Phần phi chức năng và hạn chế đã biết", DAT,
               (T + "test_bang_yeu_cau.py::test_moi_tham_chieu_ton_tai",)),
    ),
        ma=("scripts/sinh_bang_yeu_cau.py", "tests/test_bang_yeu_cau.py",
            "docs/nang-cap/ke-hoach-check-list.md"),
    ),
)

# Route mà bảng nói KHÔNG được có. Có lại là bảng sai — bộ sinh nổ.
ROUTE_CAM: tuple[tuple[str, str], ...] = (
    ("DELETE", "/api/nguoi-dung"),
)


# =====================================================================
#  PHI CHỨC NĂNG
# =====================================================================

BM, TC, HN, RT, BT, VH, BD = (
    "Bảo mật", "Độ tin cậy", "Hiệu năng", "Quyền riêng tư (Luật BVDLCN 91/2025)",
    "Bảo trì", "Vận hành", "Bản địa hoá",
)

PHI_CHUC_NANG: tuple[PhiChucNang, ...] = (
    PhiChucNang(BM, "Phân quyền hỏng-đóng",
                "Chốt lúc khởi động duyệt ĐỆ QUY mọi route; route `/api` thiếu `can_quyen` và "
                "không ở `MIEN_TRU` thì máy chủ không lên", DAT,
                (T + "test_quyen_danh_muc.py::test_moi_route_deu_da_khai_quyen",
                 T + "test_quyen_danh_muc.py::test_duyet_route_phai_di_de_quy",
                 T + "test_quyen_danh_muc.py::test_khong_con_duong_lui_bo_qua_tam"),
                ("agent/core/quyen.py",)),
    PhiChucNang(BM, "Chống leo thang quyền",
                "Không cấp được quyền mình không có; không động tới vai trò/người mạnh hơn mình",
                DAT, (T + "test_chan_leo_thang_quyen.py::test_khong_tu_gan_quan_tri_cho_minh",
                      T + "test_chan_leo_thang_quyen.py::test_khong_ha_cap_hay_khoa_cap_tren"),
                ("agent/api/quyen.py",)),
    PhiChucNang(BM, "Xác thực",
                "Mật khẩu + xác thực hai bước; chặn dò theo IP kể cả khi đổi tên; cookie tự bật "
                "Secure khi HTTPS", DAT,
                (T + "test_hai_buoc.py::test_do_doi_ten_moi_luot_van_bi_chan_theo_ip",
                 T + "test_bao_mat_giai_doan_0.py::test_cookie_tu_bat_secure_khi_https",
                 T + "test_bao_mat_giai_doan_0.py::test_token_mcp_so_hang_thoi_gian"),
                ("agent/core/xac_thuc.py", "agent/core/hai_buoc.py")),
    PhiChucNang(BM, "Che bí mật",
                "Bộ lọc nhật ký che tham số/URL/header bí mật; `httpx` không ghi URL ở mức INFO; "
                "API Kết nối không trả giá trị khoá; khoá kênh mã hoá trong vault; metadata từ chối "
                "khoá trông như bí mật", DAT,
                (T + "test_nhat_ky_che_bi_mat.py::test_che_moi_tham_so_bi_mat",
                 T + "test_nhat_ky_che_bi_mat.py::test_httpx_khong_con_ghi_o_muc_INFO",
                 T + "test_ket_noi_tich_hop.py::test_tong_quan_khong_lo_bi_mat",
                 T + "test_metadata_khong_chua_bi_mat.py::test_tu_choi_khoa_nghe_giong_bi_mat",
                 T + "test_san_sang.py::test_co_credential_ma_thieu_master_key_thi_chan"),
                ("agent/nhat_ky.py", "agent/security/credential_vault.py")),
    PhiChucNang(BM, "Webhook không cho qua khi chưa cấu hình bí mật",
                "Thiếu secret là từ chối; so sánh không thoát sớm", DAT,
                (T + "test_webhook_khong_cho_qua_khi_chua_cau_hinh.py::test_khong_co_bi_mat_thi_tu_choi",
                 T + "test_webhook_khong_cho_qua_khi_chua_cau_hinh.py::test_so_sanh_khong_thoat_som")),
    PhiChucNang(BM, "Nhật ký kiểm toán chỉ thêm",
                "Trigger CSDL chặn UPDATE/DELETE/TRUNCATE trên `events`", DAT,
                (T + "test_nhat_ky_kiem_toan.py::test_events_chi_them_va_loi_ra_chi_cho_delete",),
                ("agent/migrations/versions/0064_nhat_ky_chi_them.sql",)),
    PhiChucNang(BM, "Chống SSRF",
                "Tải media và plugin `goi_api_doc` chặn địa chỉ nội bộ, kể cả tên miền phân giải "
                "về nội bộ và sau chuyển hướng", DAT,
                (T + "test_media_khach_gui.py::test_chan_dia_chi_noi_bo",
                 T + "test_media_khach_gui.py::test_ten_may_phan_giai_ra_dia_chi_noi_bo_cung_bi_chan",
                 T + "test_media_khach_gui.py::test_chuyen_huong_vao_noi_bo_bi_chan",
                 T + "test_ky_nang_plugin.py::test_dia_chi_noi_bo_bi_chan",
                 T + "test_ky_nang_plugin.py::test_khong_di_theo_redirect")),
    PhiChucNang(BM, "Che dữ liệu cá nhân trước khi gửi model",
                "SĐT, email... thay bằng mã trước khi tới nhà cung cấp model, mặc định bật", DAT,
                (T + "test_che_du_lieu.py::test_che", T + "test_che_du_lieu.py::test_mac_dinh_bat",
                 T + "test_che_du_lieu.py::test_chi_agent_gui_chu_khach_sang_model"),
                ("agent/core/che_du_lieu.py",)),
    PhiChucNang(TC, "Hàng đợi gửi (outbox) có thử lại và dead-letter",
                "Giãn cách lũy tiến có trần; đủ lượt thì `dead` và KÊU người (không im lặng); claim "
                "bằng SKIP LOCKED, nhặt lại job treo", DAT,
                (T + "test_outbox.py::test_retry_backoff_co_gioi_han_va_den_max_thi_dead",
                 T + "test_outbox.py::test_postgres_claim_dung_skip_locked_va_nhat_lai_stale_job",
                 T + "test_tin_chet_phai_keu.py::test_tin_chet_bat_ra_canh_bao_NGHIEM_TRONG",
                 T + "test_tin_chet_phai_keu.py::test_canh_bao_hong_KHONG_lam_chet_worker"),
                ("agent/omnichannel/outbox.py", "agent/workers/outbox_worker.py")),
    PhiChucNang(TC, "Worker và nhịp tim",
                "Worker ghi heartbeat; `san_sang` chặn khi có hàng chờ mà worker không đập; tách "
                "vai api / worker", DAT,
                (T + "test_outbox.py::test_postgres_worker_heartbeat_upsert_theo_ten_worker",
                 T + "test_san_sang.py::test_outbox_co_queue_ma_worker_khong_heartbeat_thi_chan",
                 T + "test_tach_worker.py::test_vai_worker_chay_vong_nen")),
    PhiChucNang(TC, "Canh gác",
                "Canh gác trong app báo khi trạng thái ĐỔI (không báo mỗi lần kiểm); người canh "
                "ngoài (task Windows 5 phút) tự dựng lại app/sidecar, tối đa ba lần mỗi giờ", DAT,
                (T + "test_canh_gac.py::test_bao_khi_doi_trang_thai_khong_bao_moi_lan_kiem",
                 T + "test_canh_gac.py::test_vong_canh_gac_khong_bao_gio_chet",
                 T + "test_canh_gac_ngoai.py::test_hong_lan_hai_lien_tiep_thi_dung_lai",
                 T + "test_canh_gac_ngoai.py::test_toi_da_ba_lan_moi_gio_roi_bo_cuoc"),
                ("agent/canh_gac.py", "scripts/canh_gac_ngoai.py")),
    PhiChucNang(TC, "Sao lưu",
                "Mã hoá khi có mật khẩu; không chép bản chưa mã hoá ra ngoài máy; thử phục hồi "
                "thật; gồm tệp (sản phẩm, uploads, media)", DAT,
                (T + "test_sao_luu_ma_hoa.py::test_co_mat_khau_thi_khong_con_ban_thuong",
                 T + "test_sao_luu_ma_hoa.py::test_chep_ra_ngoai_chi_ban_ma_hoa",
                 T + "test_sao_luu_ma_hoa.py::test_khong_mat_khau_thi_noi_ro_la_chua_ma_hoa",
                 T + "test_sao_luu_thu_phuc_hoi.py::test_thieu_bang_so_voi_csdl_that_thi_hong",
                 T + "test_sao_luu_tep.py::test_goi_ca_products_va_uploads"),
                ("scripts/sao_luu.py",)),
    PhiChucNang(TC, "Lỗi phụ không làm chết luồng tin",
                "Quy tắc tự động, chuông thông báo hỏng thì ghi lỗi, không ném vào lượt trả lời", DAT,
                (T + "test_tu_dong.py::test_csdl_hong_khong_nem",
                 T + "test_tu_dong.py::test_mot_quy_tac_hong_khong_chan_quy_tac_sau",
                 T + "test_thong_bao_noi_bo.py::test_hong_CSDL_khong_nem_vao_luot_tra_loi_nhung_ghi_loi_va_van_bao_ngoai")),
    PhiChucNang(HN, "Hàng đợi và tải tệp không nghẽn",
                "Outbox claim SKIP LOCKED (nhiều worker không giành nhau); media đọc theo luồng "
                "có trần, không đọc trọn tệp vào RAM; sao lưu ghi theo luồng ra đĩa", DAT,
                (T + "test_outbox.py::test_postgres_claim_dung_skip_locked_va_nhat_lai_stale_job",
                 T + "test_media_khach_gui.py::test_vuot_tran_thi_dung_doc_ngay_khong_doc_tron")),
    PhiChucNang(HN, "Đo hiệu năng",
                "Nhật ký kiểm toán có chỉ mục theo hội thoại/lượt và phân trang con trỏ. CHƯA có "
                "phép đo tải sinh tự động; số đo thời gian truy vấn trong báo cáo mục 18 không tái "
                "lập được bằng script nên không chép vào đây. Độ trễ và chi phí model: "
                "`docs/thuc-nghiem.md` (sinh từ eval)", MOT_PHAN,
                (T + "test_nhat_ky_kiem_toan.py::test_quyen_va_che_tren_app_that",),
                ("agent/migrations/versions/0064_nhat_ky_chi_them.sql", "docs/thuc-nghiem.md")),
    PhiChucNang(RT, "Hạn lưu dữ liệu",
                "Hội thoại quá hạn tự dọn (đơn hàng không bị đụng — chứng từ kế toán); dọn có "
                "chạy thử và phê duyệt", DAT,
                (T + "test_du_lieu_ca_nhan.py::test_don_theo_han_khong_dung_toi_don_hang",
                 T + "test_retention_api.py::test_retention_can_admin_approve_va_dry_run_co_audit_actor"),
                ("agent/core/du_lieu_ca_nhan.py", "agent/api/retention.py")),
    PhiChucNang(RT, "Xoá theo từng khách",
                "Cần người thứ hai duyệt (phiếu); đơn hàng ẩn danh chứ không xoá; nhật ký chỉ ghi "
                "dấu vân tay SĐT", DAT,
                (T + "test_pdpd_bon_mat.py::test_khong_co_phieu_thi_nem_va_khong_xoa_gi",
                 T + "test_pdpd_bon_mat.py::test_gianh_phieu_la_mot_cau_lenh_nguyen_tu",
                 T + "test_du_lieu_ca_nhan.py::test_don_hang_duoc_an_danh_chu_khong_xoa",
                 T + "test_du_lieu_ca_nhan.py::test_nhat_ky_chi_ghi_dau_van_tay_khong_ghi_so_that"),
                ("agent/api/pdpd_api.py",)),
    PhiChucNang(RT, "Truy cập / xuất dữ liệu của khách",
                "Tra cứu toàn bộ dữ liệu theo SĐT (kể cả hồ sơ CRM, nhãn) để trả lời yêu cầu truy "
                "cập. Chưa có tệp xuất máy-đọc-được riêng cho chủ thể dữ liệu", MOT_PHAN,
                (T + "test_pdpd_bon_mat.py::test_tra_cuu_noi_ca_ho_so_crm",
                 T + "test_nhan_dong.py::test_pdpd_tra_cuu_ke_ten_nhan_va_xoa_lien_ket")),
    PhiChucNang(RT, "Sổ yêu cầu của chủ thể dữ liệu",
                "Hạn xử lý theo NĐ 356/2025 Điều 5, tính theo giờ Việt Nam; quá hạn thì `san_sang` "
                "chặn; hồ sơ BVDLCN sinh từ cấu hình thật", DAT,
                (T + "test_yeu_cau_chu_the.py::test_han_xu_ly_theo_nd_356_dieu_5",
                 T + "test_yeu_cau_chu_the.py::test_san_sang_qua_han_la_chan",
                 T + "test_yeu_cau_chu_the.py::test_ho_so_doc_cau_hinh_that"),
                ("agent/core/yeu_cau_chu_the.py", "scripts/sinh_ho_so_bvdlcn.py")),
    PhiChucNang(BT, "Tài liệu sinh ra, có test canh cũ",
                "Sơ đồ kiến trúc, thực nghiệm, kỹ năng, nghiệm thu, bảng này — sửa tay là lần sau "
                "bị ghi đè", DAT,
                (T + "test_so_do.py::test_file_tai_lieu_da_duoc_sinh_lai",
                 T + "test_thuc_nghiem.py::test_file_tai_lieu_da_duoc_sinh_lai",
                 T + "test_ky_nang.py::test_tai_lieu_ky_nang_khong_cu",
                 T + "test_bang_nghiem_thu.py::test_moi_kich_ban_deu_co_trong_bang",
                 T + "test_bang_yeu_cau.py::test_tai_lieu_khop_ban_sinh")),
    PhiChucNang(BT, "Migration chốt checksum",
                "Sửa migration đã áp thì app không lên; CRLF/LF cho cùng checksum (`.gitattributes`)",
                DAT, (T + "test_migrations.py::test_apply_migrations_chan_file_da_bi_sua",
                      T + "test_migration_xuong_dong.py::test_crlf_va_lf_cho_cung_checksum",
                      T + "test_migration_xuong_dong.py::test_co_gitattributes_ep_sql_giu_LF"),
                ("agent/migrations/runner.py",)),
    PhiChucNang(BT, "Dashboard đóng gói từ nguồn",
                "`dashboard/app.js` sinh từ `dashboard/src/*.js`; lệch là đỏ", DAT,
                (T + "test_dong_goi_dashboard.py::test_app_js_khop_voi_src",),
                ("scripts/dong_goi_dashboard.py",)),
    PhiChucNang(BT, "Kiểm tĩnh và CI",
                "`ruff` (chỉ bắt lỗi) và `mypy` cho `agent/` phải sạch; CI chạy toàn bộ test",
                DAT, (T + "test_claude_md.py::test_co_muc_kiem_truoc_khi_bao_xong",),
                (".github/workflows/kiem-thu.yml", "pyproject.toml")),
    PhiChucNang(VH, "Một lệnh kiểm sẵn sàng",
                "`scripts.san_sang` kiểm từng tầng, chỉ in tên khoá không in giá trị", DAT,
                (T + "test_san_sang.py::test_chi_in_ten_khoa_khong_in_gia_tri",
                 T + "test_san_sang.py::test_dich_vu_tat_thi_khong_ket_luan_an_toan"),
                ("scripts/san_sang.py",)),
    PhiChucNang(VH, "Một lệnh dựng cả hệ thống",
                "`scripts.khoi_dong` dựng năm tiến trình, mã thoát khác 0 khi còn tầng hỏng; chạy "
                "được không tunnel", DAT,
                (T + "test_khoi_dong.py::test_con_gi_hong_thi_ma_thoat_KHAC_khong",
                 T + "test_khoi_dong.py::test_co_duong_chay_khong_tunnel"),
                ("scripts/khoi_dong.py",)),
    PhiChucNang(VH, "Chuyển nhà lên VPS",
                "Đóng gói cửa hàng (mã hoá) và dựng lại trên VPS; đã diễn tập", DAT,
                (T + "test_sao_luu_silo.py::test_huong_dan_vps_noi_cat_khoa_ngoai_may",),
                ("scripts/chuyen_nha.py", "docs/len-vps.md")),
    PhiChucNang(BD, "Tiếng Việt",
                "Giao diện, thông báo lỗi, nhãn quyền, tên plugin, tài liệu tiếng Việt; hạn pháp lý "
                "tính theo giờ Việt Nam", DAT,
                (T + "test_quyen_danh_muc.py::test_moi_quyen_co_nhan_tieng_viet",
                 T + "test_dashboard_plugin_tieng_viet.py::test_danh_sach_plugin_hien_ten_loai_tieng_viet",
                 T + "test_yeu_cau_chu_the.py::test_phan_hoi_tinh_theo_GIO_VIET_NAM_khong_theo_UTC")),
)


# =====================================================================
#  HẠN CHẾ ĐÃ BIẾT
# =====================================================================

HAN_CHE: tuple[HanChe, ...] = (
    HanChe("Chạy trên máy cá nhân",
           "Tắt máy là cả hệ thống tắt — không lệnh nào cứu được lúc đó. Sau khi đăng nhập lại, "
           "người canh ngoài tự dựng lại app và sidecar trong vòng một chu kỳ canh, TRỪ tunnel.",
           ("scripts/canh_gac_ngoai.py", "scripts/khoi_dong.py")),
    HanChe("Tunnel tạm",
           "Tên miền tunnel đổi mỗi lần chạy; phải dán lại URL webhook. Không tunnel thì Zalo OA và "
           "Facebook mất chiều NHẬN (máy chủ của họ cần địa chỉ công khai); Zalo cá nhân không bị "
           "ảnh hưởng.", ("scripts/chay_tunnel.py",)),
    HanChe("Token Facebook / Meta hết hạn",
           "Token Trang hết hạn hoặc bị thu hồi thì kênh ngừng; canh gác báo, phải nối lại.",
           ("agent/channels/suc_khoe_token_meta.py", "scripts/noi_lai_facebook.py")),
    HanChe("Zalo cá nhân",
           "Đi qua sidecar không chính thức, chạy ngoài Docker; phiên hết hạn phải quét QR lại; "
           "sidecar tắt là tin nhân viên chết sau khi outbox thử hết lượt.",
           ("connectors/zalo-personal-sidecar", "scripts/chay_sidecar_zalo.py")),
    HanChe("Meta App Review",
           "Chưa qua duyệt ứng dụng của Meta thì chỉ Trang của người có vai trò trong app nối được.",
           ("docs/trien-khai-saas.md",)),
    HanChe("Mật khẩu sao lưu",
           "Chưa đặt `SAO_LUU_MAT_KHAU` thì bản sao lưu CSDL KHÔNG mã hoá và không được chép ra "
           "ngoài máy; `scripts.san_sang` báo mục này. Bảng này không đọc `.env` nên không khẳng "
           "định trạng thái trên máy đang chạy — chạy `san_sang` để biết.",
           ("scripts/sao_luu.py", "scripts/san_sang.py")),
    HanChe("Biên nhận Đã nhận / Đã đọc",
           "Chưa kênh nào đọc biên nhận từ webhook (mục 2.5, mục 20); bộ sinh đếm lại từ "
           "`KHA_NANG_KENH` mỗi lần.", ("agent/channels/base.py",),
           con_dung=lambda: so_kenh_co_bien_nhan() == 0),
    HanChe("AI không chạy trong hội thoại nhóm", "Theo bảng, đây là hướng sau (mục 9.8).", ()),
    HanChe("Nhật ký kiểm toán không có hạn lưu",
           "Bảng `events` chỉ thêm và chưa có đường xoá; dung lượng tăng dần (mục 18).",
           ("agent/migrations/versions/0064_nhat_ky_chi_them.sql",)),
    HanChe("Chưa có phép đo hiệu năng tái lập được", "Xem Phần B, nhóm Hiệu năng.", ()),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghi", action="store_true", help="ghi vào docs/yeu-cau-chuc-nang.md")
    args = ap.parse_args()
    try:
        md = dung_tai_lieu()
    except LoiThamChieu as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.ghi:
        TEP_DOC.write_text(md, encoding="utf-8", newline="\n")
        print(f"Đã ghi {TEP_DOC.relative_to(ROOT)}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
