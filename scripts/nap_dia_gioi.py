"""
Nạp danh mục đơn vị hành chính (sau sáp nhập 01/07/2025) vào repo.

    python -m scripts.nap_dia_gioi <tệp vn_only_simplified_json_generated_data_vn_units.json> <phiên bản>

Nguồn: ThangLeQuoc/vietnamese-provinces-database (giấy phép MIT), tệp
`json/vn_only_simplified_json_generated_data_vn_units.json` của MỘT tag cố
định. Kết quả: `agent/du_lieu/dia_gioi_vn.json` (bản gọn) — đi theo repo,
vì địa chỉ phải kiểm được trên mọi máy, kể cả bản clone sạch.

Chỉ ĐỌC dữ liệu, không chạy SQL của bên thứ ba vào CSDL: tệp tải về là dữ
liệu chưa kiểm, và một tệp SQL thì làm được mọi thứ.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parent.parent
DICH = GOC / "agent" / "du_lieu" / "dia_gioi_vn.json"
NGUON = "https://github.com/ThangLeQuoc/vietnamese-provinces-database"

_MA = re.compile(r"^\d{2,5}$")


def chuyen(du_lieu: object, phien_ban: str) -> dict:
    """Kiểm CHẶT rồi rút gọn. Sai hình dạng là nổ — không nạp một nửa."""
    if not isinstance(du_lieu, list) or len(du_lieu) != 34:
        raise ValueError(f"cần đúng 34 tỉnh/thành sau sáp nhập, nhận {len(du_lieu) if isinstance(du_lieu, list) else type(du_lieu).__name__}")
    tinh = []
    so_phuong = 0
    for t in du_lieu:
        if not isinstance(t, dict) or not _MA.match(str(t.get("Code", ""))) or not str(t.get("FullName", "")).strip():
            raise ValueError(f"tỉnh sai hình dạng: {str(t)[:80]}")
        ds = t.get("Wards")
        if not isinstance(ds, list) or not ds:
            raise ValueError(f"{t['FullName']}: không có danh sách phường/xã")
        phuong = []
        for w in ds:
            if not isinstance(w, dict) or not _MA.match(str(w.get("Code", ""))) or not str(w.get("FullName", "")).strip():
                raise ValueError(f"phường sai hình dạng ở {t['FullName']}: {str(w)[:80]}")
            if str(w.get("ProvinceCode")) != str(t["Code"]):
                raise ValueError(f"{w['FullName']} ghi mã tỉnh {w.get('ProvinceCode')} nhưng nằm trong {t['FullName']}")
            phuong.append([str(w["Code"]), str(w["FullName"]).strip()])
        so_phuong += len(phuong)
        tinh.append({"ma": str(t["Code"]), "ten": str(t["FullName"]).strip(), "phuong": phuong})
    if so_phuong < 3000:
        raise ValueError(f"chỉ có {so_phuong} phường/xã — dữ liệu thiếu?")
    return {"phien_ban": phien_ban, "nguon": NGUON, "giay_phep": "MIT", "tinh": tinh}


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    goc = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    ra = chuyen(goc, argv[1])
    DICH.parent.mkdir(parents=True, exist_ok=True)
    DICH.write_text(json.dumps(ra, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    n = sum(len(t["phuong"]) for t in ra["tinh"])
    print(f"Đã ghi {DICH.relative_to(GOC)}: {len(ra['tinh'])} tỉnh/thành, {n} phường/xã ({argv[1]})")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv[1:]))
