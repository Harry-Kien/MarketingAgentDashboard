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

GOLDEN = ROOT / "data" / "eval" / "golden.jsonl"
OUT_DIR = ROOT / "data" / "eval"


def fold(s: str) -> str:
    """Bỏ dấu + thường hoá để so khớp chuỗi cho công bằng."""
    t = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")


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
            "ms": int((time.perf_counter() - started) * 1000),
        }

    low = fold(text)
    thieu = [k for k in case.get("phai_co", []) if fold(k) not in low]
    # "phai_co_mot_trong": chỉ cần khớp MỘT biến thể — agent được phép
    # diễn đạt bằng từ đồng nghĩa, không bắt phải nhắc đúng chữ.
    mot_trong = case.get("phai_co_mot_trong") or []
    if mot_trong and not any(fold(k) in low for k in mot_trong):
        thieu.append("một trong " + str(mot_trong))
    cam = [k for k in case.get("khong_duoc_co", []) if fold(k) in low]
    dung_escalate = bool(r.escalate) == bool(case["chuyen_nguoi"])

    return {
        **case,
        "tra_loi": text,
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
