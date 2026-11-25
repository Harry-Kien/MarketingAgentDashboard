"""
Mọi loại sự kiện ghi vào `events` đều có tên tiếng Việt và mức quan trọng
(UX-18-01, UX-18-02).

VÌ SAO QUÉT MÃ NGUỒN, KHÔNG LIỆT KÊ TAY
--------------------------------------
Danh sách tay là danh sách người ta quên cập nhật. Bộ quét dưới đây đọc AST
của `agent/` và `scripts/` (cùng các migration SQL), tìm MỌI chỗ ghi
`events` — `db.log_event(...)`, `INSERT INTO events ...` — và lần ngược kind
qua biến cục bộ, biểu thức điều kiện, hằng mức module, và qua các hàm bọc
(`_su_kien(kind, …)`, `ghi_lich_su(conn, loai, …)`, `_ghi_ket_qua_luot(…)`).

Bộ quét tự kiểm chính nó, kẻo "xanh giả": nó phải TÌM RA những kind chỉ đi
qua hàm bọc/biến (ai.tu_gui, ai.de_xuat.thuc_hien, nguoi_dung.vai_tro…), và
chỗ ghi nào nó không lần ra kind thì test ĐỎ chứ không bỏ qua.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_INSERT_EVENTS = re.compile(r"INSERT\s+INTO\s+events\s*\(", re.I)
_KIND_SQL = re.compile(
    r"INSERT\s+INTO\s+events\s*\([^)]*\)\s*(?:VALUES\s*\(|SELECT)\s*'([^']+)'", re.I)
_HAM = (ast.FunctionDef, ast.AsyncFunctionDef)


def _ten_goi(f: ast.expr) -> str:
    if isinstance(f, ast.Attribute):
        return f.attr
    return f.id if isinstance(f, ast.Name) else ""


def quet_kind(goc: Path = ROOT) -> tuple[dict[str, set[str]], set[str], list[str]]:
    """
    -> (kind -> nơi ghi, tiền tố của kind ghép động bằng f-string, chỗ ghi
    không lần ra kind).
    """
    cay = {p: ast.parse(p.read_text(encoding="utf-8"))
           for p in sorted([*goc.glob("agent/**/*.py"), *goc.glob("scripts/**/*.py")])}
    hang: dict[str, set[str]] = {}
    for t in cay.values():
        for n in t.body:
            if (isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
                    and isinstance(n.value.value, str)):
                for d in n.targets:
                    if isinstance(d, ast.Name):
                        hang.setdefault(d.id, set()).add(n.value.value)

    def ham_bao(t: ast.AST) -> dict[int, ast.AST | None]:
        m: dict[int, ast.AST | None] = {}

        def di(n: ast.AST, f: ast.AST | None) -> None:
            for c in ast.iter_child_nodes(n):
                m[id(c)] = f
                di(c, c if isinstance(c, _HAM) else f)
        di(t, None)
        return m

    def tham_so(f) -> list[str]:
        return [a.arg for a in f.args.posonlyargs + f.args.args]

    def giai(e, f, sau=0):
        """-> (kind cố định, tiền tố, chưa giải được, tham số (hàm, tên))."""
        if sau > 6:
            return set(), set(), [ast.unparse(e)], []
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            return {e.value}, set(), [], []
        if isinstance(e, ast.IfExp):
            a, b = giai(e.body, f, sau + 1), giai(e.orelse, f, sau + 1)
            return a[0] | b[0], a[1] | b[1], a[2] + b[2], a[3] + b[3]
        if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Add):
            a, b = giai(e.left, f, sau + 1), giai(e.right, f, sau + 1)
            if a[1] or b[1] or a[2] or b[2] or a[3] or b[3]:
                return set(), (a[0] | a[1]) or {""}, [], []
            return {x + y for x in a[0] for y in b[0]}, set(), [], []
        if isinstance(e, ast.JoinedStr):
            dau = ""
            for v in e.values:
                if not isinstance(v, ast.Constant):
                    break
                dau += str(v.value)
            return set(), {dau}, [], []
        if isinstance(e, ast.Attribute) and e.attr in hang:
            return set(hang[e.attr]), set(), [], []
        if isinstance(e, ast.Name):
            if f is not None:
                gan = [n for n in ast.walk(f) if isinstance(n, ast.Assign) and any(
                    isinstance(d, ast.Name) and d.id == e.id for d in n.targets)]
                if gan:
                    kq: tuple = (set(), set(), [], [])
                    for g in gan:
                        r = giai(g.value, f, sau + 1)
                        kq = (kq[0] | r[0], kq[1] | r[1], kq[2] + r[2], kq[3] + r[3])
                    return kq
                if e.id in tham_so(f) or e.id in [a.arg for a in f.args.kwonlyargs]:
                    return set(), set(), [], [(f, e.id)]
            if e.id in hang:
                return set(hang[e.id]), set(), [], []
        return set(), set(), [ast.unparse(e)], []

    def bieu_thuc_ghi(n: ast.Call):
        if _ten_goi(n.func) == "log_event" and n.args:
            return n.args[0]
        if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            sql = n.args[0].value
            if _INSERT_EVENTS.search(sql):
                m = _KIND_SQL.search(sql)
                if m:
                    return ast.Constant(m.group(1))
                return n.args[1] if len(n.args) > 1 else ast.Constant(None)
        return None

    # Hàm bọc: (tệp nếu tên riêng `_x`, tên) -> (vị trí tham số kind, tên tham số).
    # Tên riêng chỉ khớp trong CÙNG tệp — `_ghi` của nhật ký và `_ghi` của
    # thông báo nội bộ là hai hàm khác nhau.
    boc: dict[tuple[str, str], tuple[int | None, str]] = {}

    def khoa_boc(p: Path, ten: str) -> tuple[str, str]:
        return (str(p) if ten.startswith("_") else "*", ten)

    for _ in range(8):
        kinds: dict[str, set[str]] = {}
        tien_to: set[str] = set()
        chua: list[str] = []
        moi = False
        for p, t in cay.items():
            bao = ham_bao(t)
            for n in ast.walk(t):
                if not isinstance(n, ast.Call):
                    continue
                e = bieu_thuc_ghi(n)
                if e is None:
                    b = boc.get(khoa_boc(p, _ten_goi(n.func)))
                    if b is None:
                        continue
                    vt, ten = b
                    kw = [k.value for k in n.keywords if k.arg == ten]
                    if kw:
                        e = kw[0]
                    elif vt is not None and len(n.args) > vt:
                        e = n.args[vt]
                    else:
                        continue
                f = bao.get(id(n))
                co_dinh, dau, khong, ts = giai(e, f)
                noi = f"{p.relative_to(goc).as_posix()}:{n.lineno}"
                for k in co_dinh:
                    kinds.setdefault(k, set()).add(noi)
                tien_to |= dau
                chua += [f"{noi}: {x}" for x in khong]
                for ham, ten in ts:
                    ds = tham_so(ham)
                    vt2 = ds.index(ten) if ten in ds else None
                    if vt2 is not None and ds and ds[0] in ("self", "cls"):
                        vt2 -= 1
                    k = khoa_boc(p, ham.name)
                    if k not in boc:
                        boc[k] = (vt2, ten)
                        moi = True
        if not moi:
            for sql in sorted(goc.glob("agent/migrations/versions/*.sql")):
                for m in _KIND_SQL.finditer(sql.read_text(encoding="utf-8")):
                    kinds.setdefault(m.group(1), set()).add(sql.name)
            return kinds, tien_to, chua
    raise AssertionError("bộ quét kind không hội tụ — hàm bọc lồng nhau quá sâu?")


def test_bo_quet_tim_duoc_kind_di_qua_ham_boc():
    """Canh XANH GIẢ: bộ quét mà mù thì 'mọi kind đều có nhãn' là vô nghĩa."""
    kinds, _, chua = quet_kind()
    assert not chua, "chỗ ghi events mà bộ quét không lần ra kind:\n" + "\n".join(chua)
    for k in (
        "erp.ngat_mach", "zalo_personal.tin_bo_qua",       # log_event trực tiếp
        "ai.tu_gui", "ai.soan_nhap",                        # _ghi_ket_qua_luot(kind)
        "ai.de_xuat.thuc_hien", "ai.de_xuat.loi",           # "ai.de_xuat." + bien
        "nguoi_dung.vai_tro", "auth.tao_nguoi_dung",        # ghi_lich_su(conn, loai)
        "backup.done", "backup.failed",                     # biểu thức điều kiện
        "khach.doi_gap_nguoi",                              # hằng module
        "su_co.danh_dau",                                   # _ghi(kind) của nhật ký
        "nhan.chuyen_doi",                                  # migration SQL
        "knowledge.published",                              # INSERT INTO events trong SQL
    ):
        assert k in kinds, k
    assert len(kinds) >= 250


def test_moi_kind_ghi_events_deu_co_nhan_va_muc_do():
    """
    UX-18-01: thêm một `log_event("x.y")` mới mà quên nhãn thì ĐỎ ở đây, chứ
    không phải người vận hành thấy `x.y` trên màn Nhật ký.
    """
    from agent.core import nhat_ky_nhan as nn

    kinds, tien_to, _ = quet_kind()
    thieu = sorted(f"{k}  ({sorted(kinds[k])[0]})" for k in kinds if k not in nn.SU_KIEN)
    assert not thieu, (
        "kind chưa có tên tiếng Việt trong agent/core/nhat_ky_nhan.py:\n" + "\n".join(thieu))
    # Kind ghép động (f-string) thì ít nhất tiền tố phải có nhãn nhóm.
    for dau in tien_to:
        assert dau.split(".", 1)[0] in nn.TIEN_TO, f"kind động tiền tố '{dau}' chưa có nhãn"
    for k, (nhan, muc) in nn.SU_KIEN.items():
        assert muc in nn.MUC_DO, k
        assert nhan and nhan != k and "_" not in nhan, (k, nhan)


def test_nhan_khong_bao_gio_la_ma_tho():
    from agent.core import nhat_ky_nhan as nn

    assert nn.nhan("erp.ngat_mach") == "ERP lỗi liên tiếp — tạm ngừng gọi"
    assert nn.nhan("shipping.cai_gi_moi") == "Sự kiện khác · Vận chuyển"
    assert nn.nhan("la_hoan_toan.x") == "Sự kiện hệ thống chưa phân loại"
    assert nn.muc_do("la_hoan_toan.x") == nn.KY_THUAT
    assert nn.muc_do("ai.tu_gui") == nn.NGHIEP_VU
    assert nn.muc_do("knowledge.retrieved") == nn.KY_THUAT
    # Mã lý do dịch ở khoá MÃ, không dịch lời người gõ ở khoá tự do.
    assert nn.gia_tri("ly_do", "khong_co_chu_va_khong_co_tep") == \
        "tin không có chữ cũng không có tệp"
    assert nn.gia_tri("ghi_chu", "auto") == "auto"


def test_ket_qua_khong_hien_khoa_tho():
    from agent.core import nhat_ky_kiem_toan as nk

    kq = nk.ket_qua("zalo_personal.tin_bo_qua", {"ly_do": "khong_co_chu_va_khong_co_tep"})
    assert kq == "lý do: tin không có chữ cũng không có tệp"
    assert "ly_do" not in kq
    # Nhãn cũ mà nơi khác tra theo tên bảng vẫn còn.
    assert nk.NHAN_HANH_DONG["ai.tu_gui"] == "AI tự gửi trả lời"


def test_sql_muc_do_dung_duoc_moi_kind():
    """Mọi kind đi qua `_sql_chuoi` — ký tự lạ trong một kind là nổ lúc import."""
    from agent.core import nhat_ky_kiem_toan as nk

    sql = nk._sql_muc_do()
    assert "'ai.tu_gui'" in sql and "ELSE 'ky_thuat'" in sql
