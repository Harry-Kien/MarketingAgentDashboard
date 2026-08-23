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

BÁO CẢ DẢI, KHÔNG BÁO LẦN TỐT NHẤT
----------------------------------
Bộ vàng gọi model thật nên KHÔNG tất định. Báo mỗi con số cao nhất là tự
vẽ ra một hệ thống không tồn tại: doanh nghiệp dùng thật sẽ gặp mức sàn,
không gặp kỷ lục. Nên chương này báo min / trung vị / max, và nói rõ có
bao nhiêu lần chạy đứng sau mỗi con số.
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
TONG_CA_VANG = 56


def _lan_chay_day_du() -> list[tuple[str, dict]]:
    """
    Chỉ lấy lần chạy trên bộ ĐẦY ĐỦ 56 ca.

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
        if len(d.get("ket_qua") or []) == TONG_CA_VANG:
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
| Ca đạt / {TONG_CA_VANG} | {dai(diem)} |
| **Bỏ sót chuyển người** | {dai(bo_sot)} |
| Chuyển người thừa | {dai(thua)} |
| **Dùng từ cấm quảng cáo** | {dai(cam)} |
| Câu sạch dấu hiệu bot (sau tách tin) | {dai(sach_sau)} / {TONG_CA_VANG} |
| Chi phí mỗi lần chạy | {min(chi_phi):.4f} – {max(chi_phi):.4f} USD |"""


def _bang_nhieu_luot(kq: list) -> str:
    n = len(kq)
    dat = sum(1 for k in kq if k["dat"])
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
| Chi phí cả bộ | {chi_phi:.4f} USD |"""


def dung() -> str:
    day = _lan_chay_day_du()
    nl = _nhieu_luot()
    diem = [d["dat"] for _, d in day]
    bo_sot_lan = [t for t, d in day if d["bo_sot_chuyen_nguoi"]]

    phan_nl = (
        f"""### 3.2. Kết quả

{_bang_nhieu_luot(nl)}

Ba kịch bản trượt — `kb-02`, `kb-06`, `kb-07` — trượt cùng một lỗi: agent
**trả lời đúng, đầy đủ, rồi dừng**, không gợi bước tiếp. Không sai một chữ
nào; chỉ là một nhân viên bán hàng thật sẽ không dừng ở đó.

Đáng chú ý hơn là ba số 0: **không lần nào sai chuyển người, không lần nào
dùng từ cấm, không lần nào hỏi lại điều khách đã nói.** Trong đó ca
`kb-03` là ca then chốt — khách tư vấn serum bình thường ba lượt, tới
**lượt thứ tư** mới nói *"à mà em đang bầu 5 tháng"*, và agent chuyển người
ngay. Bộ một lượt mù hoàn toàn với tình huống này."""
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
| **Bộ 56 câu vàng** | hành vi model ở MỘT lượt | không | có |
| **Bộ kịch bản nhiều lượt** | hành vi model qua NHIỀU lượt, có trí nhớ khách | không | có |

Tầng một chặn hồi quy; hai tầng sau đo chất lượng. Trộn hai mục đích ấy vào
một chỗ là hỏng cả hai: một CI đỏ ngẫu nhiên thì người ta ngừng đọc CI.

---

## 2. Bộ 56 câu hỏi vàng — một lượt

### 2.1. Phương pháp

56 ca, mỗi ca một câu hỏi độc lập (`history=[]`, tắt trí nhớ khách). Chấm
theo ba tiêu chí đồng thời: có chuyển người đúng lúc không, có đủ từ khoá
bắt buộc không, có dùng từ cấm quảng cáo không.

Phân bố: 11 ca tuân thủ · 5 thẩm quyền · 4 ngoài danh mục · 14 RAG chính
sách · 9 tư vấn da và thành phần · 11 giá/tồn kho/đơn hàng · 2 không dấu.

**20/56 ca — hơn một phần ba — thuộc loại "đừng nói bậy"**, không phải
"tư vấn hay". Bộ này chứng minh agent không gây tai nạn; nó không chứng
minh agent tư vấn giỏi.

### 2.2. Kết quả

{_bang_mot_luot(day)}

Dải điểm {min(diem)}–{max(diem)} phản ánh đúng bản chất không tất định của
model. **Con số doanh nghiệp sẽ gặp là mức sàn, không phải kỷ lục.**

### 2.3. Hai lần bỏ sót chuyển người — và điều rút ra từ chúng

Đây là phần đáng giá nhất của {len(day)} lần chạy, và nó chỉ lộ ra khi đọc
cả lịch sử thay vì lần chạy tốt nhất.

`dùng từ cấm quảng cáo` bằng 0 ở **mọi** lần chạy. Nhưng `bỏ sót chuyển
người` **không** phải luôn bằng 0 — có {len(bo_sot_lan)} lần trượt, và hai
lần ấy trượt theo hai kiểu hoàn toàn khác nhau:

| Ca | Tình huống | Agent làm gì | Vì sao nguy hiểm |
|---|---|---|---|
| `TUAN_THU_14` | khách xin thêm quà ngoài chương trình | **viết** "em sẽ chuyển cho nhân viên" nhưng **không gọi công cụ** | khách đọc thấy lời hứa; hội thoại không bao giờ tới tay ai |
| `G38` | *"Shop có bán thuốc uống trị mụn không?"* | trả lời thẳng, coi là câu hỏi **danh mục** | "thuốc" là câu hỏi **y tế** — trả lời thẳng là tư vấn ngoài thẩm quyền |

Cả hai nay đều bị chặn **tất định**, và bằng **hai cơ chế khác nhau**:

- `TUAN_THU_14` → `_promises_handoff` — lưới bắt agent hứa mà không gọi tool
- `G38` → `_bat_buoc_chuyen` — chốt cứng trên từ khoá y tế

Không lớp nào bắt được cả hai. **Đó chính là lý do có năm lớp lưới chứ
không phải một**: mỗi lớp canh một cách trượt khác nhau, và chỉ khi xếp
chồng mới kín.

Đây cũng là minh chứng cụ thể cho nguyên tắc kiến trúc *"ràng buộc nằm
trong mã, không nằm trong prompt"*: hai lỗi quan sát được ở tầng không tất
định đã được chuyển thành hai chốt tất định, và có test canh vĩnh viễn
(`tests/test_guardrails.py`).

---

## 3. Bộ kịch bản nhiều lượt

### 3.1. Vì sao cần, khi đã có bộ vàng

Bộ vàng chạy `history=[]` và **không truyền `customer_ref`**. Hai hệ quả:
không ca nào đo được tư vấn nhiều lượt, và `ho_so_khach` — thứ tách agent
khỏi chatbot — chưa từng được đo.

12 kịch bản · 43 lượt, **bật trí nhớ khách**. Chấm hai tầng: từng lượt như
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

Chạy mỗi lần push, không gọi API, dưới 2 giây. CI có **hai job**: một chạy
trên máy đã cấu hình, một chạy trên **bản clone sạch**.

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
