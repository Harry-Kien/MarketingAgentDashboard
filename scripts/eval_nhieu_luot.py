"""
Chạy bộ kịch bản NHIỀU LƯỢT và chấm agent như chấm một nhân viên tư vấn.

    python -m scripts.eval_nhieu_luot                    chạy tất cả
    python -m scripts.eval_nhieu_luot tri_nho_trong_hoi_thoai   chỉ một nhóm
    python -m scripts.eval_nhieu_luot --kho              không gọi model

VÌ SAO CẦN, KHI ĐÃ CÓ BỘ 56 CÂU VÀNG
------------------------------------
Bộ vàng gọi `respond(history=[], ...)` — mỗi ca một câu hỏi, một câu trả
lời, rồi quên. Nó đo rất kỹ chuyện agent có nói bậy không, và đó là phép đo
đúng cho câu hỏi "agent có gây tai nạn không".

Nó KHÔNG trả lời được câu "agent tư vấn giỏi tới đâu". Tư vấn là việc nhiều
lượt: hỏi lại đúng một câu trước khi khuyên, nhớ điều khách vừa nói, theo
được khi khách đổi ý, và dẫn tới lúc chốt đơn. Bộ này đo đúng phần đó.

HAI TẦNG CHẤM
-------------
  TỪNG LƯỢT    như bộ vàng — phải có gì, cấm gì, có chuyển người không.
               Ràng buộc tuân thủ phải đúng ở MỌI lượt, không chỉ lượt đầu:
               khách nói "em đang bầu" ở lượt 4 cũng phải chuyển người y như
               nói ở lượt 1. Đây là chỗ bộ vàng mù hoàn toàn.
  CẢ HỘI THOẠI `agent/core/cham_nhieu_luot.py` — chào lại, hỏi lại điều đã
               biết, hỏi dồn, bỏ rơi khách. Bốn lỗi nhân viên thật không mắc.

BẬT TRÍ NHỚ KHÁCH — KHÁC HẲN BỘ VÀNG
------------------------------------
Bộ vàng cố ý KHÔNG truyền `customer_ref` để các ca độc lập nhau. Hệ quả là
`ho_so_khach` — thứ được gọi là ranh giới giữa chatbot và agent — chưa từng
được đo. Ở đây bật lên, mỗi kịch bản một `customer_ref` riêng, nên hồ sơ
được dựng và dùng thật.

CHI PHÍ
-------
43 lượt, mỗi lượt một lời gọi model. Tốn tiền thật, mất khoảng 8-12 phút, và
KHÔNG tất định — y như bộ vàng. Dùng `--kho` để kiểm bộ khung chạy đúng mà
không gọi model lần nào.
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
from agent.core import cham_nhieu_luot  # noqa: E402


def _kich_ban() -> Path:
    """
    Bộ kịch bản thật nếu có, không thì bản mẫu — y như `tools._catalog()`
    làm với `catalog.json`.

    Bản thật KHÔNG lên repo: khi bạn viết kịch bản theo đúng khách hàng và
    danh mục của mình, nó thành dữ liệu doanh nghiệp. Bản mẫu thì lên, vì
    thiếu nó là máy vừa clone không chạy được bộ đo, và test đọc nó sẽ vỡ
    ngay ở bước thu thập.
    """
    thuc = ROOT / "data" / "eval" / "kich_ban.jsonl"
    return thuc if thuc.exists() else ROOT / "data" / "eval" / "kich_ban.example.jsonl"


KICH_BAN = _kich_ban()
OUT_DIR = ROOT / "data" / "eval"


def fold(s: str) -> str:
    """Bỏ dấu + thường hoá để so khớp chuỗi cho công bằng."""
    t = unicodedata.normalize("NFD", str(s).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("đ", "d")


class _KetQuaKho:
    """Kết quả giả cho chế độ --kho: kiểm bộ khung mà không gọi model."""
    text = "Dạ vâng ạ, mình muốn em tư vấn thêm không ạ?"
    escalate = False
    escalate_reason = ""
    cost_usd = 0.0
    latency_ms = 0


async def chay_kich_ban(kb: dict, cid, *, kho: bool = False) -> dict:
    """
    Chạy hết một kịch bản, giữ history tích luỹ qua các lượt.

    History dựng đúng như `agent/main.py:_history()` — vai `user`/`assistant`
    xen kẽ, lượt đầu là `user`. Dựng khác đi thì bộ đo không còn đo cái đang
    chạy thật, và một bộ đo như vậy tệ hơn không có.
    """
    history: list[dict] = []
    luot_ra: list[dict] = []
    tong_chi_phi = 0.0
    tong_ms = 0
    ref = f"eval-nl-{kb['id']}"

    for i, luot in enumerate(kb["luot"]):
        hoi = luot["khach"]
        t0 = time.perf_counter()
        if kho:
            r, loi = _KetQuaKho(), None
        else:
            try:
                r = await brain.respond(
                    conversation_id=cid, history=history, question=hoi,
                    customer_ref=ref, channel="eval",
                )
                loi = None
            except Exception as exc:  # noqa: BLE001
                r, loi = None, f"{type(exc).__name__}: {exc}"[:200]

        ms = int((time.perf_counter() - t0) * 1000)
        if r is None:
            luot_ra.append({"khach": hoi, "agent": "", "loi": loi, "dat": False})
            break

        text = r.text
        low = fold(text)
        thieu = [k for k in luot.get("phai_co", []) if fold(k) not in low]
        mot_trong = luot.get("phai_co_mot_trong") or []
        if mot_trong and not any(fold(k) in low for k in mot_trong):
            thieu.append("một trong " + str(mot_trong))
        cam = [k for k in luot.get("khong_duoc_co", []) if fold(k) in low]

        # `chuyen_nguoi` chỉ kiểm khi kịch bản NÓI RÕ. Phần lớn lượt giữa
        # chừng không quan tâm chuyện đó, và bắt mọi lượt phải khai thì kịch
        # bản đầy giá trị vô nghĩa mà không ai đọc.
        mong = luot.get("chuyen_nguoi")
        dung_escalate = True if mong is None else (bool(r.escalate) == bool(mong))

        luot_ra.append({
            "khach": hoi, "agent": text,
            "chuyen_nguoi_thuc": bool(r.escalate),
            "chuyen_nguoi_mong": mong,
            "dung_escalate": dung_escalate,
            "thieu_tu_khoa": thieu, "dung_tu_cam": cam,
            "dat": dung_escalate and not thieu and not cam,
            "ms": ms,
        })
        tong_chi_phi += r.cost_usd
        tong_ms += r.latency_ms or ms

        history.append({"role": "user", "content": hoi})
        history.append({"role": "assistant", "content": text})

        # Agent đã chuyển người đúng như kịch bản mong đợi thì hội thoại sang
        # tay người thật. Chạy tiếp là đo một thứ không tồn tại ngoài đời.
        if r.escalate and mong:
            break

        if i < len(kb["luot"]) - 1 and not kho:
            await asyncio.sleep(2.5)   # giãn cách tránh 429 của Vertex

    da_chuyen = any(l.get("chuyen_nguoi_thuc") for l in luot_ra)
    hoi_thoai = cham_nhieu_luot.cham(luot_ra, da_chuyen_nguoi=da_chuyen)
    return {
        "id": kb["id"], "nhom": kb["nhom"], "mo_ta": kb["mo_ta"],
        "luot": luot_ra, "hoi_thoai": hoi_thoai,
        "dat": all(l.get("dat") for l in luot_ra) and hoi_thoai["dat"],
        "chi_phi": tong_chi_phi, "ms": tong_ms,
    }


def _in_loi(kq: dict) -> None:
    """In rõ hỏng ở lượt nào — một dòng 'SAI' không nói được phải sửa gì."""
    for i, l in enumerate(kq["luot"]):
        if l.get("loi"):
            print(f"           lượt {i}: LỖI {l['loi'][:100]}")
        if not l.get("dung_escalate", True):
            muon = "PHẢI chuyển người" if l["chuyen_nguoi_mong"] else "KHÔNG được chuyển"
            print(f"           lượt {i}: {muon}, thực tế={l['chuyen_nguoi_thuc']}")
        if l.get("dung_tu_cam"):
            print(f"           lượt {i}: DÙNG TỪ CẤM {l['dung_tu_cam']}")
        if l.get("thieu_tu_khoa"):
            print(f"           lượt {i}: thiếu {l['thieu_tu_khoa']}")
    h = kq["hoi_thoai"]
    if h["chao_lai"]:
        print(f"           chào lại ở lượt {h['chao_lai']}")
    for i, ten in h["hoi_lai_da_biet"]:
        print(f"           lượt {i}: HỎI LẠI điều khách đã nói — {ten}")
    for i, n in h["hoi_don_dap"]:
        print(f"           lượt {i}: hỏi dồn {n} câu một lúc")
    if h["hoi_thoai_chet"]:
        print("           lượt cuối bỏ rơi khách, không gợi bước tiếp")


async def main(loc: str | None = None, kho: bool = False) -> int:
    kbs = [
        json.loads(l) for l in KICH_BAN.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if loc:
        kbs = [k for k in kbs if k["nhom"] == loc]
    if not kbs:
        print(f"Không có kịch bản nào thuộc nhóm {loc!r}")
        return 1

    await db.init_db()
    conv = await db.fetchrow(
        "INSERT INTO conversations (channel, external_id, customer_name, customer_ref) "
        "VALUES ('eval','eval-nhieu-luot','Bo kich ban nhieu luot','eval-nl') "
        "ON CONFLICT (channel, external_id) DO UPDATE SET updated_at = now() RETURNING id"
    )
    cid = conv["id"]

    tong_luot = sum(len(k["luot"]) for k in kbs)
    print(f"Chạy {len(kbs)} kịch bản · {tong_luot} lượt"
          f"{' (KHÔ — không gọi model)' if kho else ''}\n")

    ket_qua = []
    for i, kb in enumerate(kbs, 1):
        # Trần chi phí tính theo hội thoại; chạy dồn nhiều kịch bản trên cùng
        # một bản ghi sẽ chạm trần, và mọi kịch bản sau đều "chuyển người vì
        # vượt trần" — một kết quả sai mà trông y như thật.
        await db.execute("UPDATE conversations SET cost_usd = 0 WHERE id = $1", cid)
        kq = await chay_kich_ban(kb, cid, kho=kho)
        ket_qua.append(kq)
        dau = "đạt" if kq["dat"] else "SAI"
        print(f"  [{i:2}/{len(kbs)}] {dau} {kq['id']:7} {kq['mo_ta'][:56]}")
        if not kq["dat"]:
            _in_loi(kq)

    await db.execute("DELETE FROM conversations WHERE external_id = 'eval-nhieu-luot'")

    n = len(ket_qua)
    dat = sum(1 for k in ket_qua if k["dat"])
    sach = sum(1 for k in ket_qua if k["hoi_thoai"]["dat"])
    hoi_lai = sum(len(k["hoi_thoai"]["hoi_lai_da_biet"]) for k in ket_qua)
    chao_lai = sum(len(k["hoi_thoai"]["chao_lai"]) for k in ket_qua)
    chet = sum(1 for k in ket_qua if k["hoi_thoai"]["hoi_thoai_chet"])
    sai_escalate = sum(
        1 for k in ket_qua for l in k["luot"] if not l.get("dung_escalate", True)
    )
    tu_cam = sum(1 for k in ket_qua for l in k["luot"] if l.get("dung_tu_cam"))
    chi_phi = sum(k["chi_phi"] for k in ket_qua)

    print()
    print("  " + "-" * 43)
    print(f"  Kịch bản đạt          {dat}/{n}")
    print(f"  Hội thoại sạch lỗi    {sach}/{n}")
    print()
    print(f"  Sai chuyển người      {sai_escalate}   <- nghiêm trọng nhất")
    print(f"  Dùng từ cấm           {tu_cam}")
    print(f"  Hỏi lại điều đã biết  {hoi_lai}   <- đo trực tiếp ho_so_khach")
    print(f"  Chào lại giữa chừng   {chao_lai}")
    print(f"  Bỏ rơi khách ở cuối   {chet}")
    print()
    print(f"  Chi phí               {chi_phi:.4f} USD")
    print("  " + "-" * 43)

    if not kho:
        ra = OUT_DIR / f"nhieu-luot-{int(time.time())}.json"
        ra.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        print(f"\nChi tiết: {ra.relative_to(ROOT)}")

    await db.close_db()
    return 0 if dat == n else 1


if __name__ == "__main__":
    _args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(asyncio.run(main(_args[0] if _args else None, "--kho" in sys.argv)))
