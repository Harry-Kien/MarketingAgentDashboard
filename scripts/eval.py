"""
Chạy bộ câu hỏi vàng và chấm điểm agent.

    python -m scripts.eval                 chạy tất cả
    python -m scripts.eval tuan_thu        chỉ chạy một nhóm

Chỉ số quan trọng nhất KHÔNG phải độ chính xác, mà là BỎ SÓT CHUYỂN NGƯỜI:
ca lẽ ra phải chuyển cho người mà agent lại tự trả lời. Với mỹ phẩm, mỗi ca
bỏ sót là một lần agent tư vấn y tế không có thẩm quyền.

Kết quả ghi ra data/eval/ket-qua-<timestamp>.json để so sánh giữa các lần.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unicodedata
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db  # noqa: E402
from agent.core import agent as brain  # noqa: E402
from agent.core import tu_nhien  # noqa: E402

GOLDEN = ROOT / "data" / "eval" / "golden.jsonl"
OUT_DIR = ROOT / "data" / "eval"


def fold(s: str) -> str:
    """Bỏ dấu + thường hoá để so khớp chuỗi cho công bằng."""
    t = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")


# Dấu phủ định. Cụm cấm nằm sau một trong những từ này TRONG CÙNG MỆNH ĐỀ
# thì đó là agent đang TỪ CHỐI, không phải đang quảng cáo.
_PHU_DINH = ("khong", "chua", "chang", "dau co")


def _pham(text: str, cum: str) -> bool:
    """
    Cụm cấm có thật sự xuất hiện như một LỜI KHẲNG ĐỊNH không?

    So khớp chuỗi thô phạt agent vì đã làm đúng. Ba câu dưới đây đều là
    hành vi CHUẨN mà từng bị chấm là vi phạm:

        "em không thể tư vấn sản phẩm điều trị nám được"   <- "trị nám"
        "bên em không có sản phẩm đặc trị nám ạ"           <- "trị nám"
        "mỹ phẩm không phải thuốc nên không thể cam kết
         thời gian cụ thể"                                 <- "cam kết"

    Hai luật, cả hai đều xét trong phạm vi MỘT MỆNH ĐỀ:

      1. "điều trị" là danh từ y khoa trung tính — bỏ qua khớp ngay sau
         chữ "điều".
      2. Có dấu phủ định đứng trước trong cùng mệnh đề — bỏ qua.

    Giới hạn đã biết: câu kiểu "không chỉ dưỡng ẩm mà còn trị nám" sẽ lọt.
    Chấp nhận được, vì hướng sai này chỉ bỏ sót vài cách nói hiếm, còn
    hướng ngược lại làm hỏng cả chỉ số tuân thủ.
    """
    i = text.find(cum)
    while i != -1:
        if not _la_phu_dinh(text, i):
            return True
        i = text.find(cum, i + 1)
    return False


def _la_phu_dinh(text: str, i: int) -> bool:
    """Vị trí i có nằm trong một mệnh đề phủ định không?"""
    if text[max(0, i - 6):i].endswith("dieu "):
        return True
    # Lùi về đầu mệnh đề — dấu câu là ranh giới.
    dau = max(text.rfind(k, 0, i) for k in ".,!?;:\n")
    menh_de = text[dau + 1:i]
    return any(t in menh_de for t in _PHU_DINH)


async def run_case(case: dict, conv_id) -> dict:
    started = time.perf_counter()
    try:
        r = await brain.respond(
            conversation_id=conv_id, history=[], question=case["hoi"]
        )
        text, err = r.text, None
    except Exception as exc:  # noqa: BLE001
        return {
            **case, "loi": f"{type(exc).__name__}: {exc}"[:200], "dat": False,
            "tra_loi": "", "chuyen_nguoi_thuc": None, "chi_phi": 0.0,
            "dau_hieu_bot": [], "dau_hieu_sau_xu_ly": [],
            "so_tin_gui": 0, "so_ky_tu": 0,
            "ms": int((time.perf_counter() - started) * 1000),
        }

    low = fold(text)
    thieu = [k for k in case.get("phai_co", []) if fold(k) not in low]
    # "phai_co_mot_trong": chỉ cần khớp MỘT biến thể — agent được phép
    # diễn đạt bằng từ đồng nghĩa, không bắt phải nhắc đúng chữ.
    mot_trong = case.get("phai_co_mot_trong") or []
    if mot_trong and not any(fold(k) in low for k in mot_trong):
        thieu.append("một trong " + str(mot_trong))
    cam = [k for k in case.get("khong_duoc_co", []) if _pham(low, fold(k))]
    dung_escalate = bool(r.escalate) == bool(case["chuyen_nguoi"])

    # Đo dấu hiệu lộ bot ở HAI mốc — cả hai đều cần, và chúng nói hai
    # chuyện khác nhau:
    #
    #   THÔ        văn bản model vừa sinh ra. Đo prompt hiệu quả tới đâu.
    #   SAU XỬ LÝ  thứ khách THẬT SỰ nhận, sau khi lam_tu_nhien() bỏ
    #              markdown, cắt câu sáo rỗng và tách thành 2-3 tin.
    #
    # Chỉ báo con số thô là tự bôi xấu mình (phần lớn "tin quá dài" đã được
    # tách trước khi gửi). Chỉ báo con số sau xử lý là giấu đi việc prompt
    # còn yếu. Nên báo cả hai.
    #
    # lan_dau=True vì mỗi ca eval là một hội thoại mới — chào ở đây là đúng.
    dau_hieu_bot = tu_nhien.cham_diem(text, lan_dau=True)
    tins = tu_nhien.lam_tu_nhien(text, lan_dau=True)
    dau_hieu_sau = [d for t in tins for d in tu_nhien.cham_diem(t, lan_dau=True)]

    return {
        **case,
        "tra_loi": text,
        "dau_hieu_bot": dau_hieu_bot,
        "dau_hieu_sau_xu_ly": dau_hieu_sau,
        "so_tin_gui": len(tins),
        "so_ky_tu": len(text),
        "chuyen_nguoi_thuc": bool(r.escalate),
        "dung_escalate": dung_escalate,
        "thieu_tu_khoa": thieu,
        "dung_tu_cam": cam,
        "dat": dung_escalate and not thieu and not cam,
        "co_can_cu": r.grounded,
        "tin_cay": r.confidence,
        "chi_phi": r.cost_usd,
        "ms": r.latency_ms,
        "loi": err,
    }


async def main(loc: str | None = None) -> int:
    cases = [
        json.loads(line)
        for line in GOLDEN.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if loc:
        cases = [c for c in cases if c["nhom"] == loc]
    if not cases:
        print(f"Không có ca nào thuộc nhóm {loc!r}")
        return 1

    await db.init_db()
    conv = await db.fetchrow(
        "INSERT INTO conversations (channel, external_id, customer_name, customer_ref) "
        "VALUES ('eval','eval-run','Bo cau hoi vang','eval') "
        "ON CONFLICT (channel, external_id) DO UPDATE SET updated_at = now() RETURNING id"
    )
    cid = conv["id"]

    print(f"Chạy {len(cases)} ca...\n")
    results = []
    for i, case in enumerate(cases, 1):
        # Trần chi phí hội thoại sẽ chặn nếu chạy dồn -> reset trước mỗi ca.
        await db.execute("UPDATE conversations SET cost_usd = 0 WHERE id = $1", cid)
        if i > 1:
            await asyncio.sleep(2.5)   # giãn cách tránh 429 của Vertex
        res = await run_case(case, cid)
        results.append(res)
        mark = "dat " if res["dat"] else "SAI "
        print(f"  [{i:2}/{len(cases)}] {mark} {res['id']:14} {res['hoi'][:52]}")
        if not res["dat"]:
            if res.get("loi"):
                print(f"           loi: {res['loi'][:110]}")
            if not res.get("dung_escalate", True):
                muon = "PHAI chuyen nguoi" if res["chuyen_nguoi"] else "KHONG duoc chuyen"
                print(f"           escalate sai: {muon}, thuc te={res['chuyen_nguoi_thuc']}")
            if res.get("thieu_tu_khoa"):
                print(f"           thieu: {res['thieu_tu_khoa']}")
            if res.get("dung_tu_cam"):
                print(f"           DUNG TU CAM: {res['dung_tu_cam']}")

    await db.execute("DELETE FROM conversations WHERE external_id = 'eval-run'")

    # ---------------- tổng kết ----------------
    n = len(results)
    dat = sum(1 for r in results if r["dat"])
    can_chuyen = [r for r in results if r["chuyen_nguoi"]]
    khong_chuyen = [r for r in results if not r["chuyen_nguoi"]]
    bo_sot = [r for r in can_chuyen if r["chuyen_nguoi_thuc"] is False]
    chuyen_thua = [r for r in khong_chuyen if r["chuyen_nguoi_thuc"] is True]
    tu_cam = [r for r in results if r.get("dung_tu_cam")]

    # --- chỉ số TỰ NHIÊN ---
    # Chỉ tính trên ca có trả lời thật; ca lỗi hạ tầng không nói lên điều gì
    # về giọng văn.
    co_loi = [r for r in results if r["tra_loi"]]
    tong_dau_hieu = sum(len(r.get("dau_hieu_bot") or []) for r in co_loi)
    sach = [r for r in co_loi if not r.get("dau_hieu_bot")]
    tong_sau = sum(len(r.get("dau_hieu_sau_xu_ly") or []) for r in co_loi)
    sach_sau = [r for r in co_loi if not r.get("dau_hieu_sau_xu_ly")]
    tin_tb = (sum(r.get("so_tin_gui", 0) for r in co_loi) / len(co_loi)) if co_loi else 0
    dai_tb = (sum(r.get("so_ky_tu", 0) for r in co_loi) / len(co_loi)) if co_loi else 0
    # Dấu hiệu nào hay gặp nhất — biết sửa chỗ nào cho đáng.
    pho_bien: dict[str, int] = {}
    for r in co_loi:
        for d in r.get("dau_hieu_bot") or []:
            khoa = d.split(" (")[0]          # gộp "tin quá dài (410 ký tự)"
            pho_bien[khoa] = pho_bien.get(khoa, 0) + 1
    tong_chi_phi = sum(r["chi_phi"] for r in results)
    tre = sorted(r["ms"] for r in results)

    print("\n" + "=" * 62)
    print(f"  Tổng            {n} ca")
    print(f"  Đạt             {dat}/{n}  ({dat / n:.0%})")
    print(f"  BỎ SÓT CHUYỂN NGƯỜI  {len(bo_sot)}/{len(can_chuyen)}"
          f"   <-- chỉ số quan trọng nhất")
    print(f"  Chuyển người thừa    {len(chuyen_thua)}/{len(khong_chuyen)}")
    print(f"  Dùng từ cấm          {len(tu_cam)}")
    print(f"  Chi phí         ${tong_chi_phi:.4f}  (~{tong_chi_phi * 25000:,.0f} VND)"
          f"  |  ${tong_chi_phi / n:.5f}/ca")
    if tre:
        print(f"  Độ trễ          trung vị {tre[len(tre) // 2] / 1000:.1f}s"
              f"  |  p90 {tre[int(len(tre) * 0.9)] / 1000:.1f}s")

    if co_loi:
        n_loi = len(co_loi)
        print(f"\n  --- Giọng văn ---")
        print(f"  Văn bản model sinh ra:")
        print(f"    dấu hiệu lộ bot   {tong_dau_hieu / n_loi:.2f} / câu"
              f"   |  sạch {len(sach)}/{n_loi} ({len(sach) / n_loi:.0%})")
        print(f"    độ dài trung bình {dai_tb:.0f} ký tự"
              f"   (ngưỡng tin nhắn: {tu_nhien.DAI_TOI_DA})")
        print(f"  KHÁCH THẬT SỰ NHẬN (sau khi tách tin, bỏ markdown):")
        print(f"    dấu hiệu lộ bot   {tong_sau / n_loi:.2f} / câu"
              f"   |  sạch {len(sach_sau)}/{n_loi} ({len(sach_sau) / n_loi:.0%})"
              f"   <-- con số thật")
        print(f"    số tin mỗi lượt   {tin_tb:.1f}")
        if pho_bien:
            print("  Hay gặp nhất (trong văn bản thô):")
            for ten, n in sorted(pho_bien.items(), key=lambda x: -x[1]):
                print(f"    {ten:24} {n} lần")

    if bo_sot:
        print("\n  CÁC CA BỎ SÓT CHUYỂN NGƯỜI:")
        for r in bo_sot:
            print(f"    {r['id']}: {r['hoi']}")
            print(f"       -> {r['tra_loi'][:100]}")
    if tu_cam:
        print("\n  CÁC CA DÙNG TỪ CẤM:")
        for r in tu_cam:
            print(f"    {r['id']}: {r['dung_tu_cam']} | {r['tra_loi'][:80]}")

    # ---------------- theo nhóm ----------------
    nhoms: dict[str, list] = {}
    for r in results:
        nhoms.setdefault(r["nhom"], []).append(r)
    print("\n  Theo nhóm:")
    for nhom, rs in sorted(nhoms.items()):
        ok = sum(1 for r in rs if r["dat"])
        print(f"    {nhom:18} {ok}/{len(rs)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"ket-qua-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(
        json.dumps(
            {
                "tong": n, "dat": dat,
                "dau_hieu_bot_moi_cau": round(tong_dau_hieu / len(co_loi), 3) if co_loi else 0,
                "dau_hieu_sau_xu_ly_moi_cau": round(tong_sau / len(co_loi), 3) if co_loi else 0,
                "cau_tra_loi_sach": len(sach),
                "cau_tra_loi_sach_sau_xu_ly": len(sach_sau),
                "so_tin_moi_luot": round(tin_tb, 2),
                "do_dai_tb": round(dai_tb),
                "dau_hieu_pho_bien": pho_bien,
                "bo_sot_chuyen_nguoi": len(bo_sot),
                "chuyen_nguoi_thua": len(chuyen_thua),
                "dung_tu_cam": len(tu_cam),
                "chi_phi_usd": round(tong_chi_phi, 6),
                "ket_qua": results,
            },
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n  Đã lưu: {out.name}")

    await db.close_db()
    return 0 if not bo_sot and not tu_cam else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
