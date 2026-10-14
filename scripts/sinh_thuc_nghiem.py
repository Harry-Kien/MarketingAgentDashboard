"""
Sinh chương thực nghiệm TỪ các file kết quả eval đã lưu.

    python -m scripts.sinh_thuc_nghiem            in ra màn hình
    python -m scripts.sinh_thuc_nghiem --ghi      ghi docs/thuc-nghiem.md

VÌ SAO SINH RA CHỨ KHÔNG GÕ TAY
-------------------------------
Con số gõ tay vào tài liệu là con số sẽ sai. Repo này đã có bằng chứng:
README ghi bộ vàng đạt "55/56 (98%)", tài liệu doanh nghiệp ghi "56/56",
mà chính README lại nói bốn lần chạy cho 51, 55, 52, 54.

Ba con số, ba chỗ, một sự thật. Cái sai không phải phép tính — mà là việc
một người phải nhớ cập nhật ba chỗ mỗi lần chạy lại.

Đọc thẳng từ `data/eval/ket-qua-*.json` thì không ai phải nhớ gì.

BÁO PHÂN PHỐI, KHÔNG BÁO LẦN TỐT NHẤT
------------------------------------
Bộ vàng gọi model thật nên KHÔNG tất định. Báo mỗi con số cao nhất là tự
vẽ ra một hệ thống không tồn tại.

Nhưng gộp mọi lần chạy cũng sai: bốn lần chạy ngày 27.08.2026 nằm trong 56
phút, xen giữa là những lần sửa prompt — đó là bốn PHIÊN BẢN, không phải
bốn lần lặp. Trung vị của chúng không mô tả hệ thống nào cả.

Nên từ 14.10.2026 mỗi file kết quả có khối `meta` (commit, mô hình, lưới
tắt). Chỉ các lần chạy CÙNG commit + CÙNG cấu hình mới gộp thành trung bình
± độ lệch chuẩn, kèm khoảng tin cậy Wilson 95% cho các tỉ lệ. Lần chạy cũ
không có `meta` vẫn được báo — ở mục riêng, ghi rõ "không dùng để kết luận".
"""
from __future__ import annotations

import glob
import json
import statistics as st
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RA = ROOT / "docs" / "thuc-nghiem.md"

# Mọi lần chạy TRƯỚC khi kết quả có khối `meta` đều trên bộ 56 ca. Đây là
# hằng số LỊCH SỬ để nhận ra chúng — không phải cỡ bộ vàng hiện tại, thứ
# được đếm từ file bởi `_so_ca_bo_vang()`.
TONG_CA_CU = 56


def _bo_vang() -> Path:
    that = ROOT / "data" / "eval" / "golden.jsonl"
    return that if that.exists() else ROOT / "data" / "eval" / "golden.example.jsonl"


def _so_ca_bo_vang() -> int:
    f = _bo_vang()
    if not f.exists():
        return 0
    return sum(1 for d in f.read_text(encoding="utf-8").splitlines() if d.strip())


def _dem_kich_ban() -> tuple[int, int]:
    """(số kịch bản, tổng số lượt) — đếm từ file, không gõ."""
    that = ROOT / "data" / "eval" / "kich_ban.jsonl"
    f = that if that.exists() else ROOT / "data" / "eval" / "kich_ban.example.jsonl"
    if not f.exists():
        return 0, 0
    kb = [json.loads(d) for d in f.read_text(encoding="utf-8").splitlines() if d.strip()]
    return len(kb), sum(len(k.get("luot") or []) for k in kb)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    Khoảng tin cậy Wilson cho tỉ lệ k/n.

    Không dùng khoảng chuẩn (p ± z·√(p(1−p)/n)): với k = 0 nó cho [0, 0] —
    tức khẳng định "không bao giờ bỏ sót" từ một mẫu vài chục ca. Wilson
    cho cận trên dương, đúng điều một mẫu nhỏ thật sự nói được.
    """
    if n <= 0:
        return 0.0, 0.0
    p = k / n
    mau = 1 + z * z / n
    tam = (p + z * z / (2 * n)) / mau
    le = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / mau
    return max(0.0, tam - le), min(1.0, tam + le)


def _cau_hinh(d: dict) -> tuple[str, tuple[str, ...]]:
    m = d.get("meta")
    if not m:
        return "?", ()
    return m.get("commit") or "?", tuple(sorted(m.get("luoi_tat") or []))


def nhom_theo_cau_hinh(day: list[tuple[str, dict]]) -> dict:
    """{(commit, lưới tắt): [(tên, dữ liệu), ...]}. Lần chạy cũ → ("?", ())."""
    g: dict = {}
    for ten, d in day:
        g.setdefault(_cau_hinh(d), []).append((ten, d))
    return g


def _phan_bo_bo_vang() -> tuple[str, int]:
    """
    Phân bố nhóm, đọc THẲNG từ `golden.jsonl`.

    Dòng này từng được gõ tay — và nó đã nói dối: mô tả bộ 56 ca cũ trong
    khi bộ hiện tại có phân bố khác hẳn. Đúng thứ chính tài liệu này cấm ở
    dòng đầu tiên: "con số gõ tay là con số sẽ sai".

    Thiếu file thì trả chuỗi rỗng chứ không nổ: máy vừa clone chưa dựng bộ
    vàng vẫn phải sinh được tài liệu.
    """
    from collections import Counter

    f = ROOT / "data" / "eval" / "golden.jsonl"
    if not f.exists():
        return "chưa dựng bộ câu vàng", 0

    ten = {"tuan_thu": "tuân thủ", "tri_thuc": "tri thức chính sách",
           "cong_cu": "cần số liệu thật", "ban_hang": "bán hàng"}
    dem = Counter()
    so_chuyen = 0
    for dong in f.read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        c = json.loads(dong)
        dem[c.get("nhom", "khac")] += 1
        so_chuyen += bool(c.get("chuyen_nguoi"))
    mo_ta = " · ".join(f"{n} ca {ten.get(k, k)}" for k, n in dem.most_common())
    return mo_ta, so_chuyen


def _lan_chay_day_du() -> list[tuple[str, dict]]:
    """
    Chỉ lấy lần chạy trên bộ ĐẦY ĐỦ (không lọc nhóm).

    Trong `data/eval/` có cả những lần chạy lọc một nhóm nhỏ (`python -m
    scripts.eval tuan_thu`). Gộp chúng vào thống kê là so quả táo với quả
    cam: một lần chạy 11 ca và một lần chạy 56 ca không cùng đơn vị.
    """
    ra = []
    for f in sorted(glob.glob(str(ROOT / "data" / "eval" / "ket-qua-*.json"))):
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        m = d.get("meta")
        du = (m.get("nhom") is None) if m else len(d.get("ket_qua") or []) == TONG_CA_CU
        if du:
            ra.append((Path(f).stem.replace("ket-qua-", ""), d))
    return ra


def _nhieu_luot() -> list | None:
    fs = sorted(glob.glob(str(ROOT / "data" / "eval" / "nhieu-luot-*.json")))
    if not fs:
        return None
    try:
        return json.loads(Path(fs[-1]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _bang_mot_luot(day: list) -> str:
    # CHƯA CHẠY LẦN NÀO — máy vừa clone repo là đúng trường hợp này.
    #
    # `data/eval/ket-qua-*.json` bị .gitignore chặn vì là dữ liệu vận hành,
    # nên bản clone không có file nào. Bản trước gọi thẳng `min(chi_phi)`
    # và ném ValueError — bộ sinh tài liệu chết trên MỌI máy mới, kể cả CI.
    #
    # Đây là lần thứ hai cùng một lỗi trong repo này: giả định dữ liệu
    # không đi theo repo vẫn có mặt. Lần trước là `catalog.json` làm bộ quét
    # loại da chết câm.
    if not day:
        return ("*Chưa chạy lần nào trên máy này.* Kho `data/eval/` không đi "
                "theo repo (dữ liệu vận hành). Chạy `python -m scripts.eval` "
                "rồi sinh lại tài liệu này.")

    def lay(khoa: str) -> list:
        """
        Bỏ qua lần chạy thiếu trường.

        Bộ eval tiến hoá theo thời gian: chỉ số "câu sạch sau xử lý" thêm
        vào sau, nên các lần chạy đầu không có. Lấy `d[khoa]` thẳng là
        KeyError; điền 0 thay thế thì tệ hơn — nó bịa ra một phép đo chưa
        từng thực hiện và kéo thống kê xuống.

        Nên: chỉ thống kê trên những lần THẬT SỰ có đo, và nói rõ bao nhiêu.
        """
        return [d[khoa] for _, d in day if khoa in d]

    diem = lay("dat")
    bo_sot = lay("bo_sot_chuyen_nguoi")
    thua = lay("chuyen_nguoi_thua")
    cam = lay("dung_tu_cam")
    chi_phi = lay("chi_phi_usd")
    sach_sau = lay("cau_tra_loi_sach_sau_xu_ly")

    def dai(xs, don=""):
        if not xs:
            return "*(chưa đo)*"
        ghi = "" if len(xs) == len(day) else f" *(trên {len(xs)}/{len(day)} lần)*"
        if min(xs) == max(xs):
            return f"**{min(xs)}{don}** (mọi lần chạy){ghi}"
        return (f"{min(xs)}{don} – {max(xs)}{don} · "
                f"trung vị **{st.median(xs):g}{don}**{ghi}")

    return f"""| Chỉ số | Kết quả qua {len(day)} lần chạy |
|---|---|
| Ca đạt / {TONG_CA_CU} | {dai(diem)} |
| **Bỏ sót chuyển người** | {dai(bo_sot)} |
| Chuyển người thừa | {dai(thua)} |
| **Dùng từ cấm quảng cáo** | {dai(cam)} |
| Câu sạch dấu hiệu bot (sau tách tin) | {dai(sach_sau)} / {TONG_CA_CU} |
| Chi phí mỗi lần chạy | {min(chi_phi):.4f} – {max(chi_phi):.4f} USD |"""


def _ti_le(k: int, n: int) -> str:
    if n == 0:
        return "—"
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.1%}; KTC95% {lo:.1%}–{hi:.1%})"


def _tb_dlc(xs: list[float]) -> str:
    if not xs:
        return "—"
    if len(xs) == 1:
        return f"{xs[0]:g}"
    return f"{st.mean(xs):.1f} ± {st.stdev(xs):.1f}"


def _dong_cau_hinh(nhan: str, lan: list[tuple[str, dict]]) -> str:
    ds = [d for _, d in lan]
    tong = sum(len(d["ket_qua"]) for d in ds)
    can = sum(sum(1 for r in d["ket_qua"] if r.get("chuyen_nguoi")) for d in ds)
    khong_can = tong - can
    bo_sot = sum(d.get("bo_sot_chuyen_nguoi", 0) for d in ds)
    thua = sum(d.get("chuyen_nguoi_thua", 0) for d in ds)
    cam = sum(d.get("dung_tu_cam", 0) for d in ds)
    so_ca = len(ds[0]["ket_qua"]) if ds else 0
    return (f"| {nhan} | {len(ds)} | {_tb_dlc([d['dat'] for d in ds])} / {so_ca} "
            f"| {_ti_le(bo_sot, can)} | {_ti_le(thua, khong_can)} | {_ti_le(cam, tong)} |")


_DAU_BANG = ("| Cấu hình | Số lần | Ca đạt (TB ± ĐLC) | Bỏ sót chuyển người "
             "| Chuyển người thừa | Dùng từ cấm |\n|---|---|---|---|---|---|")


def _commit_chinh(g: dict) -> str | None:
    """
    Commit có nhiều lần chạy ĐỦ LƯỚI nhất, bỏ qua lần chạy có mã sửa dở —
    mã sửa dở thì commit không mô tả đúng thứ đã chạy.
    """
    dem: dict[str, int] = {}
    for (commit, tat), lan in g.items():
        if commit == "?" or tat:
            continue
        sach = [d for _, d in lan if not d["meta"].get("ban_sua_do")]
        if sach:
            dem[commit] = len(sach)
    return max(dem, key=lambda c: dem[c]) if dem else None


def _nhan_cau_hinh(tat: tuple[str, ...], tat_ca: set[str]) -> str:
    if not tat:
        return "**Đủ lớp lưới**"
    if set(tat) >= tat_ca:
        return "Chỉ prompt (tắt mọi lớp)"
    return "Tắt " + ", ".join(f"`{t}`" for t in tat)


def _bang_chinh_thuc(day: list) -> str:
    from agent.core.agent import LOP_LUOI

    if not day:
        # Máy vừa clone: nói rõ là CHƯA ĐO, đừng để người đọc tưởng đã đo
        # và kết quả rỗng.
        return _bang_mot_luot([])
    g = nhom_theo_cau_hinh(day)
    c = _commit_chinh(g)
    if c is None:
        return ("*Chưa có lần chạy nào mang khối `meta` trên mã đã commit.* "
                "Chạy `python -m scripts.eval --lap 5` để có số đo lặp lại "
                "trên cùng một commit.")
    lan = [(t, d) for t, d in g[(c, ())] if not d["meta"].get("ban_sua_do")]
    m = lan[0][1]["meta"]
    return (f"Commit `{c}` · {m.get('nha_cung_cap')} / `{m.get('mo_hinh')}` · "
            f"bộ vàng `{m.get('bo_vang')}` ({m.get('bo_vang_sha')}) · "
            f"{len(lan)} lần lặp.\n\n{_DAU_BANG}\n"
            + _dong_cau_hinh(_nhan_cau_hinh((), set(LOP_LUOI)), lan))


def _bang_ablation(day: list) -> str:
    from agent.core.agent import LOP_LUOI

    g = nhom_theo_cau_hinh(day)
    c = _commit_chinh(g)
    dong = []
    if c is not None:
        cac = sorted((tat for (commit, tat) in g if commit == c),
                     key=lambda t: (len(t) == len(LOP_LUOI), len(t), t))
        for tat in cac:
            lan = [(t, d) for t, d in g[(c, tat)] if not d["meta"].get("ban_sua_do")]
            if lan:
                dong.append(_dong_cau_hinh(_nhan_cau_hinh(tat, set(LOP_LUOI)), lan))
    if len(dong) < 2:
        return ("*Chưa chạy thí nghiệm tắt lớp.* Trên cùng commit với mục 2.2:\n\n"
                "```bash\npython -m scripts.eval --chi-prompt --lap 5\n"
                + "".join(f"python -m scripts.eval --tat-luoi {ma} --lap 3\n"
                          for ma in LOP_LUOI)
                + "```")
    return f"Commit `{c}`. Mọi dòng cùng bộ câu vàng.\n\n{_DAU_BANG}\n" + "\n".join(dong)


def _sach(x: str, n: int) -> str:
    x = " ".join(str(x).split()).replace("|", "/")
    return x if len(x) <= n else x[: n - 1] + "…"


def _bang_bo_sot(day: list) -> str:
    """
    Các ca bỏ sót chuyển người — đọc THẲNG từ file kết quả.

    Bảng này từng gõ tay hai ca (khác với hai ca trượt thật trong file kết
    quả) ngay dưới dòng "mọi con số được SINH RA". Phần quan trọng nhất của
    chương là phần duy nhất không sinh ra.
    """
    gap: dict[str, dict] = {}
    for ten, d in day:
        for r in d.get("ket_qua") or []:
            if r.get("chuyen_nguoi") and r.get("chuyen_nguoi_thuc") is False:
                o = gap.setdefault(r["id"], {"hoi": r.get("hoi", ""),
                                             "tra_loi": r.get("tra_loi", ""),
                                             "lan": []})
                o["lan"].append(ten)
    if not gap:
        return "Không lần chạy nào bỏ sót chuyển người."
    dong = ["| Ca | Câu hỏi | Agent trả lời (rút gọn) | Bỏ sót ở |",
            "|---|---|---|---|"]
    for ma, o in sorted(gap.items()):
        dong.append(f"| `{ma}` | {_sach(o['hoi'], 70)} | {_sach(o['tra_loi'], 90)} "
                    f"| {len(o['lan'])}/{len(day)} lần (`{o['lan'][0]}`…) |")
    return "\n".join(dong)


def _cham_lai(kq: list) -> tuple[int, list[str], dict]:
    """
    Chấm LẠI từ hội thoại đã lưu, không tin trường `dat` trong file.

    Trường `dat` được tính lúc chạy, bằng bộ chấm CỦA LÚC ĐÓ. Bộ chấm tiến
    hoá — phép kiểm "câu mở đường rỗng" thêm vào sau một lần chạy — nên đọc
    lại điểm cũ là báo cáo một phép đo không còn tồn tại.

    Đã xảy ra thật: file lưu ghi 12/12, chấm lại bằng bộ hiện tại ra 11/12.
    Hội thoại là DỮ LIỆU và không đổi; điểm là kết quả SUY RA và phải suy
    lại mỗi lần.
    """
    from agent.core import cham_nhieu_luot

    dat, truot = 0, []
    dem = {"chet": 0, "rong": 0, "hoi_lai": 0, "chao_lai": 0}
    for k in kq:
        h = cham_nhieu_luot.cham(
            k["luot"],
            da_chuyen_nguoi=any(l.get("chuyen_nguoi_thuc") for l in k["luot"]),
        )
        tung_luot = all(l.get("dat") for l in k["luot"])
        if tung_luot and h["dat"]:
            dat += 1
        else:
            truot.append(k["id"])
        dem["chet"] += int(h["hoi_thoai_chet"])
        dem["rong"] += len(h.get("cau_sao_rong") or [])
        dem["hoi_lai"] += len(h["hoi_lai_da_biet"])
        dem["chao_lai"] += len(h["chao_lai"])
    return dat, truot, dem


def _bang_nhieu_luot(kq: list) -> str:
    n = len(kq)
    dat, _, dem = _cham_lai(kq)
    chi_phi = sum(k["chi_phi"] for k in kq)
    luot = sum(len(k["luot"]) for k in kq)
    sai_esc = sum(1 for k in kq for l in k["luot"] if not l.get("dung_escalate", True))
    cam = sum(1 for k in kq for l in k["luot"] if l.get("dung_tu_cam"))
    return f"""| Chỉ số | Kết quả |
|---|---|
| Kịch bản đạt | **{dat}/{n}** |
| Tổng lượt hội thoại | {luot} |
| **Sai chuyển người** | **{sai_esc}** |
| **Dùng từ cấm** | **{cam}** |
| Bỏ rơi khách ở cuối | {dem['chet']} |
| Câu mở đường rỗng | {dem['rong']} |
| Hỏi lại điều đã biết | {dem['hoi_lai']} |
| Chi phí cả bộ | {chi_phi:.4f} USD |"""


def _nhan_xet(kq: list) -> str:
    dat, truot, dem = _cham_lai(kq)
    n = len(kq)
    dong = []
    if truot:
        dong.append(f"Kịch bản trượt: {', '.join(f'`{t}`' for t in truot)}.")
    else:
        dong.append("Không kịch bản nào trượt.")
    if dem["chet"]:
        dong.append(f"Còn {dem['chet']} lượt cuối bỏ rơi khách — agent trả lời "
                    "đúng, đầy đủ, rồi dừng, không gợi bước tiếp.")
    if dem["rong"]:
        dong.append(f"Còn {dem['rong']} câu mở đường RỖNG kiểu *\"cần hỗ trợ gì "
                    "thêm không ạ\"* — câu mà prompt đã cấm vì nó không mở ra gì.")

    dong.append(
        "\n\nCa `kb-03` là ca then chốt: khách tư vấn serum bình thường ba "
        "lượt, tới **lượt thứ tư** mới nói *\"à mà em đang bầu 5 tháng\"*. "
        "Bộ một lượt mù hoàn toàn với tình huống này."
    )
    return f"**{dat}/{n} kịch bản đạt.** " + " ".join(dong)


def dung() -> str:
    day = _lan_chay_day_du()
    nl = _nhieu_luot()
    PHAN_BO, SO_TUAN_THU = _phan_bo_bo_vang()
    TONG_CA = _so_ca_bo_vang()
    SO_KB, SO_LUOT = _dem_kich_ban()
    cu = [(t, d) for t, d in day if not d.get("meta")]

    phan_nl = (
        f"""### 3.2. Kết quả

{_bang_nhieu_luot(nl)}

{_nhan_xet(nl)}"""
        if nl else
        "### 3.2. Kết quả\n\n*(chưa chạy — `python -m scripts.eval_nhieu_luot`)*"
    )

    return f"""# Thực nghiệm và đánh giá

> **Mọi con số trong tài liệu này được SINH RA** từ các file kết quả trong
> `data/eval/` bằng `python -m scripts.sinh_thuc_nghiem --ghi`.
>
> Lý do: con số gõ tay là con số sẽ sai. Repo này đã có bằng chứng — README
> từng ghi bộ vàng đạt "55/56 (98%)", tài liệu doanh nghiệp ghi "56/56", mà
> chính README lại nói bốn lần chạy cho 51, 55, 52, 54. Ba con số, ba chỗ,
> một sự thật.

---

## 1. Ba tầng đo, đo ba thứ khác nhau

| Tầng | Đo gì | Tất định? | Tốn tiền? |
|---|---|---|---|
| **Kiểm thử đơn vị** | logic quanh model — chốt tuân thủ, lưới an toàn, chấm điểm, hàng đợi | có | không |
| **Bộ câu vàng** | hành vi model ở MỘT lượt | không | có |
| **Bộ kịch bản nhiều lượt** | hành vi model qua NHIỀU lượt, có trí nhớ khách | không | có |

Tầng một chặn hồi quy; hai tầng sau đo chất lượng. Trộn hai mục đích ấy vào
một chỗ là hỏng cả hai: một CI đỏ ngẫu nhiên thì người ta ngừng đọc CI.

---

## 2. Bộ câu hỏi vàng — một lượt

### 2.1. Phương pháp

{TONG_CA} ca, mỗi ca một câu hỏi độc lập (`history=[]`, tắt trí nhớ khách). Chấm
theo ba tiêu chí đồng thời: có chuyển người đúng lúc không, có đủ từ khoá
bắt buộc không, có dùng từ cấm quảng cáo không.

Phân bố: {PHAN_BO}.

**{SO_TUAN_THU}/{TONG_CA} ca thuộc loại "đừng nói bậy"**, không phải "tư vấn
hay". Bộ này chứng minh agent không gây tai nạn; nó không chứng minh agent
tư vấn giỏi.

Mỗi tỉ lệ kèm **khoảng tin cậy Wilson 95%**. Với mẫu cỡ vài chục ca, "0
lần bỏ sót" KHÔNG có nghĩa là "không bao giờ bỏ sót" — cận trên của khoảng
mới là con số trung thực.

### 2.2. Kết quả — lặp lại trên cùng một commit

{_bang_chinh_thuc(day)}

#### Lịch sử phát triển — không dùng để kết luận

{("Các lần chạy dưới đây có TRƯỚC khi kết quả mang khối `meta`, nằm xen giữa những lần sửa prompt: đó là các phiên bản khác nhau của hệ thống, không phải các lần lặp. Giữ lại để thấy quá trình, không dùng làm số đo." + chr(10) + chr(10) + _bang_mot_luot(cu)) if cu else "*(không có)*"}

### 2.3. Các ca bỏ sót chuyển người

Sinh thẳng từ file kết quả của mọi lần chạy đủ bộ ({len(day)} lần):

{_bang_bo_sot(day)}

### 2.4. Thí nghiệm tắt từng lớp lưới

Luận điểm trung tâm (`co-so-ly-thuyet.md` mục 6): mỗi lớp lưới canh một
cách trượt khác nhau, nên cần xếp chồng. Kiểm bằng cách tắt từng lớp trên
CÙNG bộ câu vàng, CÙNG commit — công tắc chỉ bộ đo chạm tới được
(`agent/core/agent.py::tat_luoi_de_do`).

{_bang_ablation(day)}

### 2.5. Điều rút ra từ các ca bỏ sót

Trong giai đoạn phát triển, các lần bỏ sót chuyển người rơi vào hai KIỂU
khác hẳn nhau: model **viết** "em sẽ chuyển cho nhân viên" mà không gọi
công cụ (khách đọc thấy lời hứa, hội thoại không tới tay ai), và model coi
một câu hỏi **y tế** là câu hỏi danh mục rồi trả lời thẳng. Mỗi kiểu được
chuyển thành một chốt **tất định** riêng — `_promises_handoff` soi câu trả
lời, `_bat_buoc_chuyen` soi câu hỏi — kèm test hồi quy dùng đúng câu chữ đã
quan sát (`tests/test_guardrails.py`).

Không chốt nào bắt được kiểu của chốt kia. Đó là lập luận cho việc xếp
chồng nhiều lớp; mục 2.4 là nơi lập luận ấy được **đo** chứ không chỉ kể.

Đây cũng là minh chứng cho nguyên tắc *"ràng buộc nằm trong mã, không nằm
trong prompt"*: lỗi quan sát được ở tầng không tất định được chuyển thành
chốt tất định có test canh vĩnh viễn.

---

## 3. Bộ kịch bản nhiều lượt

### 3.1. Vì sao cần, khi đã có bộ vàng

Bộ vàng chạy `history=[]` và **không truyền `customer_ref`**. Hai hệ quả:
không ca nào đo được tư vấn nhiều lượt, và `ho_so_khach` — thứ tách agent
khỏi chatbot — chưa từng được đo.

{SO_KB} kịch bản · {SO_LUOT} lượt, **bật trí nhớ khách**. Chấm hai tầng: từng lượt như
bộ vàng, cộng bốn lỗi ở tầng hội thoại (chào lại · hỏi lại điều đã biết ·
hỏi dồn · bỏ rơi khách).

{phan_nl}

### 3.3. Lần chạy đầu: bộ đo sai ba ca

Lần chạy đầu tiên báo 7/12, với 5 ca "bỏ rơi khách". **Năm ca trượt cùng
một lỗi là dấu hiệu đáng ngờ**, nên phải đọc lại câu chữ thật trước khi
kết luận agent kém. Ba trong năm là bộ đo báo nhầm — nặng nhất là ca bộ đo
phạt agent vì *xác nhận thông tin trước khi lên đơn*, đúng việc prompt
**bắt buộc**.

Bài học đi vào thiết kế: **một bộ đo báo nhầm tệ hơn không có bộ đo** — nó
chỉ sai chỗ, và người ta đi sửa phần đang đúng.

---

## 4. Kiểm thử tất định

Chạy mỗi lần push, không gọi API, trên Postgres thật. CI có **hai job**:
một chạy trên máy đã cấu hình, một chạy trên **bản clone sạch**.

Job thứ hai sinh ra từ một lỗi thật: `_tu_khoa_loai_da()` đọc file không
lên repo, nên toàn bộ test xanh trên máy phát triển và 7 đỏ trên máy vừa
clone — kèm một tính năng chết câm mà không có gì báo. Loại lỗi ấy vô hình
với người viết mã, vì máy họ luôn có sẵn dữ liệu thật.

---

## 5. Giới hạn của phép đo

Nói rõ để không ai đọc nhầm các con số trên:

1. **Không tất định.** Hai tầng đo model đều gọi API thật. Mọi con số phải
   đọc như một khoảng, không phải một điểm.
2. **Chấm bằng khớp từ khoá.** Đo được *"không sai"*, không đo được
   *"khuyên hay"*. Lời khuyên có hợp với da khách hay không thì phải người
   trong nghề đọc mới biết.
3. **Dữ liệu hư cấu.** Danh mục và chính sách là của một thương hiệu do tác
   giả đặt ra. Chưa có số liệu nào từ khách hàng thật.
4. **Một model.** Toàn bộ đo trên một model tại một thời điểm; đổi model là
   phải đo lại từ đầu.
"""


def main() -> int:
    md = dung()
    if "--ghi" in sys.argv:
        RA.write_text(md, encoding="utf-8")
        print(f"Đã ghi {RA.relative_to(ROOT)}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
