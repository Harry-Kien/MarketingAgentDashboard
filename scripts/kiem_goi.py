"""
Kiểm một gói kỹ năng đã cài — bốn lớp, KHÔNG gọi model sinh văn bản.

    python -m scripts.kiem_goi tu-van-chong-nang
    python -m scripts.kiem_goi tu-van-chong-nang --nhanh   # bỏ lớp tài liệu

VÌ SAO CẦN
----------
Cài gói xong, ba mảnh của nó nằm ở ba chỗ: hướng dẫn kích hoạt theo từ
khoá, công cụ trong bảng plugin, tài liệu trong kho tri thức. Mảnh nào
hỏng cũng KHÔNG nổ — agent chỉ lặng lẽ trả lời như chưa từng có gói, và
dashboard vẫn hiện gói "đang bật". Bấm thử tay từng câu trong Phòng thử
thì tốn tiền model và không ai làm lại sau mỗi lần sửa gói.

VÌ SAO KHÔNG GỌI MODEL
----------------------
Ba lớp đầu là hàm thuần và một truy vấn CSDL. Lớp tài liệu gọi embedding
để tra kho tri thức — rẻ hơn một lượt sinh văn bản khoảng hai bậc, nhưng
vẫn ra mạng, nên có cờ `--nhanh` để bỏ.

Thứ script này KHÔNG thay được: đọc câu trả lời thật xem giọng có đúng
không. Đó là việc của Phòng thử, và nó tốn tiền model.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db  # noqa: E402
from agent.core.cham_mot_luot import fold  # noqa: E402
from agent.ky_nang import goi as goi_mod  # noqa: E402
from agent.ky_nang.ban_mo_ta import bo_dau, doc_ban_mo_ta  # noqa: E402
from agent.ky_nang.chay import chay_plugin  # noqa: E402

TOT = "tot"
CANH_BAO = "canh_bao"
HONG = "hong"

_NHAN = {TOT: "[đủ]      ", CANH_BAO: "[cảnh báo]", HONG: "[HỎNG]    "}

# Câu nghiệp vụ cốt lõi của cửa hàng. Một gói TƯ VẤN chiếm được câu nào
# trong đây là từ khoá của nó quá rộng: hướng dẫn tư vấn sẽ chen vào một
# lượt tra đơn hoặc chốt giá, tốn prompt mỗi lượt và kéo agent lạc đề.
#
# Là CẢNH BÁO chứ không phải HỎNG, vì một ngày nào đó có thể có gói cố ý
# phụ trách đúng mảng ấy (gói "tư vấn vận chuyển" thì khớp câu ship là
# đúng). Bảng lúc nào cũng đỏ là bảng người ta thôi đọc.
CAU_DOI_CHUNG = (
    "đơn của mình tới đâu rồi ạ",
    "cho mình xin giá sữa rửa mặt",
    "mình muốn đổi trả sản phẩm này",
    "ship về Bình Dương bao nhiêu tiền",
    "shop còn hàng không ạ",
    "mình muốn đặt 2 hộp",
    "alo shop ơi",
)


@dataclass
class Muc:
    ten: str
    trang_thai: str
    chi_tiet: str
    goi_y: str = ""


def ma_thoat(mucs: list[Muc]) -> int:
    """0 nếu không có mục nào HỎNG. Cảnh báo không làm đỏ mã thoát."""
    return 1 if any(m.trang_thai == HONG for m in mucs) else 0


# ---------------------------------------------------------------------
#  Lớp 1: từ khoá — thuần, không I/O
# ---------------------------------------------------------------------

def kiem_tu_khoa(g: goi_mod.Goi, cac_goi_khac: list[goi_mod.Goi]) -> list[Muc]:
    """
    Từ khoá có kích hoạt đúng lúc, và có kích hoạt SAI lúc không.

    Cố ý KHÔNG kiểm "mỗi từ khoá tự kích hoạt gói của nó": `chon_goi` so
    `fold(k) in fold(cau_hoi)`, mà câu hỏi khi ấy chính là từ khoá, nên
    phép đó luôn xanh — nó thưởng cho cả gói hỏng.
    """
    ra: list[Muc] = []

    # 1a. Câu nghiệp vụ bị chiếm.
    chiem = []
    for cau in CAU_DOI_CHUNG:
        q = fold(cau)
        trung = [k for k in g.tu_khoa if fold(k) in q]
        if trung:
            chiem.append(f"{cau!r} (do từ khoá {', '.join(repr(t) for t in trung)})")
    if chiem:
        ra.append(Muc(
            "Từ khoá không lấn việc khác", CANH_BAO,
            f"{len(chiem)} câu nghiệp vụ cũng kích hoạt gói: " + " · ".join(chiem),
            "Thu hẹp từ khoá, hoặc bỏ qua nếu gói này CỐ Ý phụ trách mảng đó.",
        ))
    else:
        ra.append(Muc("Từ khoá không lấn việc khác", TOT,
                      f"{len(CAU_DOI_CHUNG)} câu nghiệp vụ đều không kích hoạt gói"))

    # 1b. Bị gói khác đẩy khỏi hai suất mỗi lượt.
    tat_ca = [g] + list(cac_goi_khac)
    mat_suat = []
    for k in g.tu_khoa:
        chon = goi_mod.chon_goi(tat_ca, k)
        if g.ten not in [x.ten for x in chon]:
            thang = ", ".join(x.ten for x in chon)
            mat_suat.append(f"{k!r} (thua: {thang})")
    if mat_suat:
        ra.append(Muc(
            "Còn suất trong mỗi lượt", HONG,
            f"{len(mat_suat)} từ khoá bị gói khác chiếm hết "
            f"{goi_mod.GOI_MOI_LUOT_TOI_DA} suất: " + " · ".join(mat_suat),
            "Gói vẫn hiện 'đang bật' nhưng KHÔNG BAO GIỜ tới lượt ở những "
            "câu ấy. Tắt bớt gói trùng chủ đề, hoặc đổi từ khoá cho riêng.",
        ))
    else:
        ra.append(Muc("Còn suất trong mỗi lượt", TOT,
                      f"{len(g.tu_khoa)} từ khoá đều đưa được gói vào lượt"))

    # 1c. Từ khoá thừa vì đã bị cụm ngắn hơn trùm.
    thua = []
    for a in g.tu_khoa:
        for b in g.tu_khoa:
            if a is not b and fold(b) in fold(a) and fold(a) != fold(b):
                thua.append(f"{a!r} đã nằm trong {b!r}")
                break
    if thua:
        ra.append(Muc(
            "Không có từ khoá thừa", CANH_BAO,
            " · ".join(thua),
            "Cụm dài không ăn thêm lượt nào so với cụm ngắn đã trùm nó — "
            "bỏ đi cho người đọc khỏi tưởng gói phủ rộng hơn thực tế.",
        ))
    else:
        ra.append(Muc("Không có từ khoá thừa", TOT, "không cụm nào trùm cụm nào"))

    return ra


# ---------------------------------------------------------------------
#  Lớp 2: bảng tra — chạy thật qua chay_plugin, không ra mạng
# ---------------------------------------------------------------------

async def kiem_bang(cong_cu_tho: dict) -> list[Muc]:
    """
    Bảng có trả lời được không, và trả lời có mập mờ không.

    KHÔNG kiểm "mỗi khoá tra lại ra chính nó": `_tra_bang` so bằng trước
    khi so chứa, và khoá lồng nhau đã bị `doc_ban_mo_ta` chặn từ lúc lưu —
    phép ấy luôn xanh với mọi bảng hợp lệ, tức là xanh giả.

    Hai phép còn lại đều có ca đỏ thật:

      * giá trị rỗng — `_kiem_cau_hinh` chỉ `strip()` chứ không chặn, nên
        một dòng giá trị toàn dấu cách lọt vào tận nơi và agent trả về một
        câu trắng cho đúng khách hỏi dòng ấy;
      * từ mở đầu chung — model điền tham số cụt ("đi" thay vì "đi biển")
        thì `_tra_bang` khớp nhiều dòng và agent hỏi lại thay vì trả lời.
    """
    bm = doc_ban_mo_ta(cong_cu_tho)
    ten_tham_so = bm.tham_so[0].ten if bm.tham_so else "khoa"
    bang = bm.cau_hinh["bang"]

    rong = [k for k, v in bang.items() if not str(v).strip()]
    if rong:
        return [Muc(f"Bảng của {bm.ten}", HONG,
                    f"{len(rong)} dòng có giá trị rỗng: " + ", ".join(repr(k) for k in rong),
                    "Agent sẽ trả về một câu trắng cho khách hỏi đúng dòng ấy.")]

    # Chạy thật qua `chay_plugin` chứ không suy từ cấu hình: nếu ai đó sửa
    # `_tra_bang` sau này thì chỗ hỏng hiện ra ở đây, không đợi tới khách.
    mo_ho = []
    for khoa in bang:
        dau = bo_dau(khoa).split()
        if not dau:
            continue
        kq = await chay_plugin(bm, {ten_tham_so: dau[0]})
        if kq.get("nhieu_ket_qua"):
            mo_ho.append(f"{dau[0]!r} khớp {', '.join(repr(x) for x in kq['nhieu_ket_qua'])}")

    if mo_ho:
        return [Muc(f"Bảng của {bm.ten}", CANH_BAO,
                    f"{len(set(mo_ho))} từ mở đầu khớp nhiều dòng: "
                    + " · ".join(sorted(set(mo_ho))),
                    "Model điền tham số cụt thì agent hỏi lại thay vì trả lời. "
                    "Cho mỗi dòng một từ mở đầu riêng nếu muốn chắc.")]
    return [Muc(f"Bảng của {bm.ten}", TOT,
                f"{len(bang)} dòng, không dòng nào khớp mập mờ")]


# ---------------------------------------------------------------------
#  Lớp 3: đã cài đủ ba mảnh — chạm CSDL
# ---------------------------------------------------------------------

async def kiem_da_cai(ten: str) -> tuple[list[Muc], dict | None]:
    ds = await goi_mod.liet_ke()
    hien = next((x for x in ds if x["ten"] == ten), None)
    if hien is None:
        co = ", ".join(x["ten"] for x in ds) or "(chưa cài gói nào)"
        return [Muc("Gói đã cài", HONG, f"không có gói {ten!r}. Đang có: {co}")], None

    ra = [Muc("Gói đã cài", TOT if hien.get("bat") else HONG,
              f"v{hien.get('phien_ban')} · "
              f"{'đang bật' if hien.get('bat') else 'ĐANG TẮT — agent không thấy gói này'}")]

    tho = await goi_mod.xuat(ten)
    if tho is None:
        ra.append(Muc("Nội dung gói", HONG, "không xuất được nội dung gói"))
        return ra, None

    from agent.ky_nang import kho_ky_nang

    ds_kn = await kho_ky_nang.liet_ke()
    ten_plugin = {p["ten"] for p in ds_kn.get("plugin", [])}
    thieu = [c["ten"] for c in (tho.get("cong_cu") or []) if c["ten"] not in ten_plugin]
    if thieu:
        ra.append(Muc("Công cụ của gói", HONG,
                      "không thấy trong bảng plugin: " + ", ".join(thieu),
                      "Cài lại gói. Công cụ thiếu thì agent không gọi được."))
    else:
        ra.append(Muc("Công cụ của gói", TOT,
                      f"{len(tho.get('cong_cu') or [])} công cụ đều có trong bảng plugin"))
    return ra, tho


# ---------------------------------------------------------------------
#  Lớp 4: tài liệu — CSDL trước, rồi một lượt embedding
# ---------------------------------------------------------------------

def truy_van_tra(t: dict) -> str:
    """
    Mẩu chữ dùng để thử tra một tài liệu — lấy từ NỘI DUNG, không phải
    tiêu đề.

    Tra bằng tiêu đề là đỏ giả: `retrieve` xếp theo ngữ nghĩa của nội dung
    đã nhúng, nên tiêu đề ngắn thua cả những tài liệu chỉ liên quan xa,
    trong khi chính tài liệu ấy vẫn đứng đầu với một câu hỏi thật. Đo được
    trên gói tu-van-chong-nang: tiêu đề trượt khỏi top 5, còn "SPF 50 chặn
    bao nhiêu phần trăm" cho nó 0.842 hạng nhất.

    Lấy câu đầu, và nối thêm nếu quá ngắn: một mẩu vài chữ thì tra ra gì
    cũng được, phép kiểm thành xanh giả.
    """
    noi_dung = " ".join(str(t.get("noi_dung", "")).split())
    cau = noi_dung.split(". ")
    q = cau[0]
    i = 1
    while len(q) < 40 and i < len(cau):
        q = f"{q}. {cau[i]}"
        i += 1
    return q[:300]


async def kiem_tai_lieu(ten_goi: str, tho: dict) -> list[Muc]:
    """
    Tài liệu của gói có vào kho, có đoạn để tra, và tra ra được không.

    Hai phép, tất định trước rồi mới tới phép chạm mạng:

      * bảng `documents` phải có đủ bản ghi mang nguồn `goi:<ten>:NN`, mỗi
        bản ghi ít nhất một đoạn — `cai()` nạp tài liệu ở bước CUỐI vì nó
        gọi API nhúng, nên đây đúng là chỗ một lần cài dở dang để lại kho
        thiếu mà gói vẫn hiện "đang bật";
      * tra thử bằng một mẩu nội dung thật của tài liệu.
    """
    tai_lieu = tho.get("tai_lieu") or []
    if not tai_lieu:
        return [Muc("Tài liệu tra được", TOT, "gói không mang tài liệu nào")]

    ra: list[Muc] = []
    rows = await db.fetch(
        "SELECT title, source, chunk_count FROM documents WHERE source LIKE $1",
        f"goi:{ten_goi}:%",
    )
    if len(rows) < len(tai_lieu):
        return [Muc("Tài liệu trong kho", HONG,
                    f"gói khai {len(tai_lieu)} tài liệu, kho chỉ có {len(rows)}",
                    "Một lần cài dở dang. Cài lại gói để nạp đủ.")]
    trong = [r["title"] for r in rows if not r["chunk_count"]]
    if trong:
        return [Muc("Tài liệu trong kho", HONG,
                    f"{len(trong)} tài liệu không có đoạn nào: " + ", ".join(trong),
                    "Có bản ghi nhưng không nhúng được — agent không tra ra gì.")]
    ra.append(Muc("Tài liệu trong kho", TOT,
                  f"{len(rows)} tài liệu, tổng {sum(r['chunk_count'] for r in rows)} đoạn"))

    from agent.core import rag

    truot = []
    for t in tai_lieu:
        try:
            doan = await rag.retrieve(truy_van_tra(t), k=5)
        except Exception as exc:  # noqa: BLE001
            ra.append(Muc("Tài liệu tra được", HONG,
                          f"không tra được kho tri thức: {type(exc).__name__}: {exc}"[:200]))
            return ra
        if not any(t["tieu_de"] in p.doc_title for p in doan):
            thay = ", ".join(p.doc_title for p in doan[:3]) or "(không có gì)"
            truot.append(f"{t['tieu_de']!r} thua: {thay}")

    if truot:
        ra.append(Muc("Tài liệu tra được", HONG,
                      f"{len(truot)} tài liệu không lọt 5 đoạn đầu dù tra bằng "
                      "chính nội dung của nó: " + " · ".join(truot),
                      "Kho có tài liệu khác lấn át. Agent sẽ trả lời bằng nguồn khác."))
    else:
        ra.append(Muc("Tài liệu tra được", TOT,
                      f"{len(tai_lieu)} tài liệu đều đứng trong 5 đoạn đầu"))
    return ra


# ---------------------------------------------------------------------

def _in(mucs: list[Muc]) -> None:
    for m in mucs:
        print(f"{_NHAN[m.trang_thai]}   {m.ten:<30} {m.chi_tiet}")
        if m.goi_y and m.trang_thai != TOT:
            print(f"             └─ {m.goi_y}")


async def chay(ten: str, nhanh: bool) -> int:
    await db.init_db()
    try:
        mucs, tho = await kiem_da_cai(ten)
        if tho is not None:
            g = goi_mod.doc_goi(tho)
            khac = [goi_mod.doc_goi(await goi_mod.xuat(x["ten"]))
                    for x in await goi_mod.liet_ke()
                    if x["ten"] != ten and x.get("bat")]
            mucs += kiem_tu_khoa(g, khac)
            for c in tho.get("cong_cu") or []:
                if c.get("loai") == "tra_bang":
                    mucs += await kiem_bang(c)
            if nhanh:
                mucs.append(Muc("Tài liệu tra được", CANH_BAO,
                                "bỏ qua vì --nhanh — lớp duy nhất chạm mạng"))
            else:
                mucs += await kiem_tai_lieu(ten, tho)
    finally:
        await db.close_db()

    print()
    print(f"KIỂM GÓI KỸ NĂNG: {ten}")
    print("─" * 78)
    _in(mucs)
    print("─" * 78)
    ma = ma_thoat(mucs)
    so_cb = sum(1 for m in mucs if m.trang_thai == CANH_BAO)
    if ma:
        print("Còn mảnh HỎNG — agent sẽ im lặng bỏ qua phần đó, không báo lỗi.")
    elif so_cb:
        print(f"Chạy được, còn {so_cb} cảnh báo.")
    else:
        print("Ba mảnh đều tới nơi. Còn giọng văn thì phải đọc ở Phòng thử.")
    return ma


def main() -> int:
    p = argparse.ArgumentParser(
        description="Kiểm một gói kỹ năng đã cài, không gọi model sinh văn bản.")
    p.add_argument("ten", help="tên gói, ví dụ tu-van-chong-nang")
    p.add_argument("--nhanh", action="store_true",
                   help="bỏ lớp tài liệu (lớp duy nhất ra mạng)")
    a = p.parse_args()
    return asyncio.run(chay(a.ten, a.nhanh))


if __name__ == "__main__":
    raise SystemExit(main())
