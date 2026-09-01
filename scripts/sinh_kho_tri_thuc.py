"""
Sinh khung kho tri thức cho một ngành hàng.

    python -m scripts.sinh_kho_tri_thuc --nganh the_thao
    python -m scripts.sinh_kho_tri_thuc --nganh my_pham --ra data/knowledge
    python -m scripts.sinh_kho_tri_thuc --liet-ke

Lệnh này KHÔNG gọi model và KHÔNG tốn tiền. Nó cũng không ghi đè tệp nào
đã có: chạy lại nhiều lần là an toàn.

Sau khi sinh, mở từng tệp và trả lời các dòng `[CẦN NGƯỜI ĐIỀN: ...]`.
Còn dòng nào chưa xoá thì `python -m scripts.ingest` sẽ từ chối nạp tệp
đó — xem `agent/tri_thuc/chot.py` để biết vì sao.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Console Windows mac dinh cp1258 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tri_thuc import sinh as sinh_khung  # noqa: E402
from agent.tri_thuc.nganh import KHUNG_THEO_MA, lay  # noqa: E402


def _liet_ke() -> int:
    print("Khung ngành có sẵn:\n")
    for ma, k in sorted(KHUNG_THEO_MA.items()):
        print(f"  {ma:<10} {k.ten}")
        print(f"  {'':<10} {k.mo_ta}")
        print(f"  {'':<10} {len(k.tai_lieu)} tài liệu · {k.tong_cau_hoi()} câu hỏi\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Sinh khung kho tri thức theo ngành")
    p.add_argument("--nganh", help="mã ngành, ví dụ my_pham hoặc the_thao")
    p.add_argument("--ra", default="data/knowledge",
                   help="thư mục đích (mặc định data/knowledge)")
    p.add_argument("--liet-ke", action="store_true", dest="liet_ke",
                   help="chỉ liệt kê các khung ngành có sẵn")
    a = p.parse_args(argv)

    if a.liet_ke or not a.nganh:
        return _liet_ke() if a.liet_ke else (_liet_ke() or 1)

    try:
        khung = lay(a.nganh)
    except ValueError as exc:
        print(f"LỖI: {exc}")
        return 1

    kq = sinh_khung(khung, Path(a.ra))

    print(f"Ngành: {khung.ten}")
    print(f"Thư mục: {a.ra}\n")
    for p_ in kq.da_tao:
        print(f"  tạo mới   {p_.name}")
    for p_ in kq.bo_qua:
        print(f"  đã có     {p_.name}  (không đụng tới)")

    print(f"\n{len(kq.da_tao)} tệp mới · {kq.tong_cau_hoi} câu hỏi cần người trả lời.")
    if kq.da_tao:
        print(
            "\nBƯỚC TIẾP THEO — không bỏ qua được:\n"
            "  1. Mở từng tệp, trả lời các dòng [CẦN NGƯỜI ĐIỀN: ...]\n"
            "  2. Xoá dòng đánh dấu sau khi đã viết câu trả lời thật\n"
            "  3. python -m scripts.ingest " + a.ra + "\n"
            "\nBước 3 sẽ TỪ CHỐI mọi tệp còn dòng chưa điền. Kho tri thức là\n"
            "căn cứ agent dùng để trả lời khách, nên khung rỗng vào kho còn\n"
            "tệ hơn không có tài liệu nào."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
