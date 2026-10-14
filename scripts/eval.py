"""
Chạy bộ câu hỏi vàng và chấm điểm agent.

    python -m scripts.eval                 chạy tất cả
    python -m scripts.eval tuan_thu        chỉ chạy một nhóm
    python -m scripts.eval --lap 5         lặp 5 lần trên CÙNG commit
    python -m scripts.eval --tat-luoi injection,hua_khong_goi
                                           thí nghiệm tắt từng lớp (ablation)
    python -m scripts.eval --chi-prompt    tắt CẢ các lớp lưới — đối chứng
                                           "chỉ dựa vào prompt"

Mỗi lần lặp ghi MỘT file kết quả, kèm khối `meta` (commit, mô hình, lưới
tắt, dấu vân tay bộ vàng). `scripts.sinh_thuc_nghiem` nhóm theo `meta`: chỉ
các lần CÙNG commit + CÙNG cấu hình mới được gộp thành trung bình ± độ lệch.
Gộp lần chạy khác commit là đo nhiều hệ thống rồi gọi là một.

Chỉ số quan trọng nhất KHÔNG phải độ chính xác, mà là BỎ SÓT CHUYỂN NGƯỜI:
ca lẽ ra phải chuyển cho người mà agent lại tự trả lời. Với mỹ phẩm, mỗi ca
bỏ sót là một lần agent tư vấn y tế không có thẩm quyền.

Kết quả ghi ra data/eval/ket-qua-<timestamp>.json để so sánh giữa các lần.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import db  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.core import agent as brain  # noqa: E402
from agent.core import tu_nhien  # noqa: E402
# Giữ tên `_pham` vì tests/test_guardrails.py import `_pham` từ
# scripts.eval — chuyển thân hàm sang agent/, chỗ dùng cũ re-export lại.
# (F401: _pham không còn gọi trực tiếp trong file này, nhưng vẫn phải
# import để re-export cho test cũ.)
from agent.core.cham_mot_luot import fold, pham as _pham, so_voi_bo_vang  # noqa: E402,F401

# Đường lui sang bộ mẫu, cùng cách `eval_nhieu_luot` lui về
# `kich_ban.example.jsonl`: bộ thật bị .gitignore chặn vì có thể chứa giá
# thật, nên máy vừa clone chỉ có bản mẫu — và CLAUDE.md dẫn tới file này.
_GOLDEN_THAT = ROOT / "data" / "eval" / "golden.jsonl"
GOLDEN = (
    _GOLDEN_THAT if _GOLDEN_THAT.exists()
    else ROOT / "data" / "eval" / "golden.example.jsonl"
)
OUT_DIR = ROOT / "data" / "eval"


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

    # "phai_co_mot_trong": chỉ cần khớp MỘT biến thể — agent được phép
    # diễn đạt bằng từ đồng nghĩa, không bắt phải nhắc đúng chữ. Thuật
    # toán chấm nằm trong agent/core/cham_mot_luot.py — dùng chung với
    # phòng thử, không định nghĩa lại ở đây.
    cham = so_voi_bo_vang(text, r.escalate, case)
    thieu, cam, dung_escalate = cham["thieu"], cham["cam"], not cham["sai_chuyen"]

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


async def hoi_thoai_eval(
    *,
    external_id: str = "eval-run",
    ten: str = "Bo cau hoi vang",
    customer_ref: str = "eval",
):
    """
    Dựng một hội thoại để chạy bộ đo, hợp lệ với lược đồ HIỆN TẠI.

    VÌ SAO PHẢI VIẾT LẠI PHẦN NÀY
    -----------------------------
    Bản trước chèn thẳng `conversations` với `ON CONFLICT (channel,
    external_id)`. Ràng buộc đó không còn: các migration account-aware đã đổi
    nó thành `(account_id, external_id)`, và thêm `account_id`, `contact_id`,
    `contact_point_id` vào nhóm NOT NULL.

    Nên `python -m scripts.eval` chết ngay ở dòng đầu với
    `InvalidColumnReferenceError` — bộ đo chất lượng KHÔNG chạy được lần nào
    kể từ khi lược đồ đổi, và không có gì báo: `CLAUDE.md` vẫn ghi lệnh đó
    như thể nó chạy được.

    Dùng lại tài khoản `webchat` sẵn có thay vì tạo kênh giả: eval đo AGENT,
    không đo lớp kênh, và thêm một kênh ma vào bảng chỉ làm bẩn dữ liệu thật.

    VÌ SAO CÓ THAM SỐ, VÀ VÌ SAO KHÔNG CHÉP SANG `eval_nhieu_luot`
    -------------------------------------------------------------
    Bộ nhiều lượt cần đúng phép dựng này nhưng với `external_id` riêng. Bản
    trước nó tự chép lấy một câu INSERT — và bản chép đó KHÔNG được sửa khi
    lược đồ đổi, nên `python -m scripts.eval_nhieu_luot` chết ở dòng đầu kể
    từ đó, kể cả ở chế độ `--kho` không tốn tiền.

    Không ai biết, vì `docs/thuc-nghiem.md` chỉ ghi "(chưa chạy)" — đọc như
    một lựa chọn, không phải một lỗi. Đúng khuôn "hai bản sao của cùng một
    việc: bản ít người đọc hơn sẽ mục". Nên cách sửa là bỏ bản chép đi, chứ
    không phải vá nó.
    """
    tk = await db.fetchrow(
        "SELECT id FROM channel_accounts WHERE channel = 'webchat' "
        "ORDER BY created_at LIMIT 1"
    )
    if tk is None:
        raise SystemExit(
            "Chưa có tài khoản kênh webchat để chạy bộ đo. "
            "Tạo một tài khoản Website chat trong mục Kết nối rồi chạy lại."
        )
    account_id = tk["id"]

    lien_he = await db.fetchrow(
        "SELECT c.id FROM contacts c JOIN contact_points p ON p.contact_id = c.id "
        "WHERE p.external_user_id = $2 AND p.channel_account_id = $1 LIMIT 1",
        account_id, customer_ref,
    )
    if lien_he is None:
        lien_he = await db.fetchrow(
            "INSERT INTO contacts (display_name) VALUES ($1) RETURNING id", ten
        )
    contact_id = lien_he["id"]

    diem = await db.fetchrow(
        """
        INSERT INTO contact_points (contact_id, channel_account_id, external_user_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (channel_account_id, external_user_id)
        DO UPDATE SET last_seen = now()
        RETURNING id
        """,
        contact_id, account_id, customer_ref,
    )

    conv = await db.fetchrow(
        """
        INSERT INTO conversations (account_id, contact_id, contact_point_id,
                                   channel, external_id, customer_name, customer_ref)
        VALUES ($1, $2, $3, 'webchat', $4, $5, $6)
        ON CONFLICT (account_id, external_id)
        DO UPDATE SET updated_at = now()
        RETURNING id
        """,
        account_id, contact_id, diem["id"], external_id, ten, customer_ref,
    )
    return conv["id"]


def _git(*lenh: str) -> str:
    try:
        return subprocess.run(["git", *lenh], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001 — thiếu git không được chặn việc đo
        return ""


def dung_meta(tat: frozenset[str], lan: int, tong_lan: int) -> dict:
    """
    Dấu vân tay của MỘT lần chạy — đủ để biết hai lần chạy có cùng hệ thống.

    Bốn lần chạy ngày 27.08.2026 nằm trong 56 phút, xen giữa là những lần
    sửa prompt. Không có khối này thì không ai phân biệt được "lặp lại" với
    "bốn phiên bản khác nhau", và trung vị của chúng là con số vô nghĩa.
    """
    return {
        "commit": _git("rev-parse", "--short", "HEAD") or "?",
        # Sửa dở trong agent/ mà chưa commit thì commit KHÔNG mô tả đúng mã
        # đã chạy. Ghi lại để bộ sinh tài liệu loại khỏi phần kết luận.
        "ban_sua_do": bool(_git("status", "--porcelain", "agent")),
        "nha_cung_cap": settings.llm_provider,
        "mo_hinh": settings.model_chat,
        "luoi_tat": sorted(tat),
        "bo_vang": GOLDEN.name,
        "bo_vang_sha": hashlib.sha256(GOLDEN.read_bytes()).hexdigest()[:12],
        "lan": lan,
        "tong_lan": tong_lan,
        "bat_dau": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


async def main(loc: str | None = None, tat: frozenset[str] = frozenset(),
               lap: int = 1) -> int:
    if GOLDEN.name == "golden.example.jsonl":
        # Nói to, vì đây là điểm dễ hiểu nhầm nhất: số đo ra trông y hệt số
        # đo thật, chỉ khác là agent đang trả lời về hàng KHÔNG CÓ THẬT.
        print("[CẢNH BÁO] Không thấy data/eval/golden.jsonl — đang đo trên BỘ MẪU")
        print("           (hàng mẫu, không phải hàng của shop). Để đo thật:")
        print("           python -m scripts.sinh_bo_cau_vang")
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
    ma_thoat = 0
    try:
        for k in range(1, lap + 1):
            meta = dung_meta(tat, k, lap)
            # None = đủ bộ. Bộ sinh tài liệu chỉ thống kê lần chạy đủ bộ —
            # gộp lần chạy một nhóm 11 ca với lần chạy đủ bộ là khác đơn vị.
            meta["nhom"] = loc
            nhan = f" — lần {k}/{lap}" if lap > 1 else ""
            nhan += f" — TẮT LƯỚI: {', '.join(sorted(tat))}" if tat else ""
            print(f"\n=== commit {meta['commit']}{nhan} ===")
            with brain.tat_luoi_de_do(tat):
                ma_thoat |= await _mot_lan(cases, meta)
    finally:
        await db.close_db()
    return ma_thoat


async def _mot_lan(cases: list[dict], meta: dict) -> int:
    cid = await hoi_thoai_eval()

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

    await db.execute(
        "DELETE FROM conversations WHERE external_id = 'eval-run' AND customer_ref = 'eval'")

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
        print("\n  --- Giọng văn ---")
        print("  Văn bản model sinh ra:")
        print(f"    dấu hiệu lộ bot   {tong_dau_hieu / n_loi:.2f} / câu"
              f"   |  sạch {len(sach)}/{n_loi} ({len(sach) / n_loi:.0%})")
        print(f"    độ dài trung bình {dai_tb:.0f} ký tự"
              f"   (ngưỡng tin nhắn: {tu_nhien.DAI_TOI_DA})")
        print("  KHÁCH THẬT SỰ NHẬN (sau khi tách tin, bỏ markdown):")
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
                "meta": meta,
                "ket_qua": results,
            },
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\n  Đã lưu: {out.name}")

    return 0 if not bo_sot and not tu_cam else 1


def doc_tham_so(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="python -m scripts.eval")
    ap.add_argument("nhom", nargs="?", help="chỉ chạy một nhóm, ví dụ tuan_thu")
    ap.add_argument("--lap", type=int, default=1, help="số lần lặp trên cùng commit")
    ap.add_argument("--tat-luoi", default="",
                    help="tắt các lớp lưới, cách nhau bằng dấu phẩy: "
                         + ", ".join(brain.LOP_LUOI))
    ap.add_argument("--chi-prompt", action="store_true",
                    help="tắt CẢ các lớp lưới — đối chứng chỉ-prompt")
    ts = ap.parse_args(argv)
    if ts.lap < 1:
        ap.error("--lap phải từ 1")
    tat = {x.strip() for x in ts.tat_luoi.split(",") if x.strip()}
    if ts.chi_prompt:
        tat = set(brain.LOP_LUOI)
    la = tat - set(brain.LOP_LUOI)
    if la:
        # Nổ ở đây, TRƯỚC khi tốn tiền gọi model — không đợi tới ca đầu tiên.
        ap.error(f"không có lớp lưới {sorted(la)}; có: {', '.join(brain.LOP_LUOI)}")
    ts.tat = frozenset(tat)
    return ts


if __name__ == "__main__":
    _ts = doc_tham_so(sys.argv[1:])
    raise SystemExit(asyncio.run(main(_ts.nhom, _ts.tat, _ts.lap)))
