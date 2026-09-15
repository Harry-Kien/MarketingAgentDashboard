"""
Sinh `docs/nghiem-thu.md` — bảng nghiệm thu từng chức năng, từ kết quả CHẠY THẬT.

    TEST_DATABASE_URL=postgresql://... python -m scripts.sinh_nghiem_thu --ghi
    python -m scripts.sinh_nghiem_thu            # chỉ in, không ghi

VÌ SAO SINH RA CHỨ KHÔNG VIẾT TAY
---------------------------------
Một bảng nghiệm thu viết tay là một bảng người ta điền "đạt" rồi tin là đã
đạt. Bảng này chỉ ghi "đạt" khi kịch bản ấy vừa chạy xanh trên app đầy đủ
và Postgres thật — cùng nguyên tắc với `scripts/san_sang.py`: danh sách
kiểm mà máy tự chạy được thì không nói dối.

Các BƯỚC của mỗi kịch bản lấy từ docstring của chính test, nên bảng không
bao giờ mô tả một luồng khác với luồng đã kiểm.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
TEP_TEST = ROOT / "tests" / "test_nghiem_thu_saas.py"
TEP_DOC = ROOT / "docs" / "nghiem-thu.md"


class _GomKetQua:
    """Plugin pytest: gom (tên test, docstring, kết quả)."""

    def __init__(self) -> None:
        self.ket_qua: list[tuple[str, str, str]] = []
        self._doc: dict[str, str] = {}

    def pytest_collection_modifyitems(self, items):
        for it in items:
            self._doc[it.nodeid] = (it.function.__doc__ or "").strip()

    def pytest_runtest_logreport(self, report):
        if report.when != "call" and not (report.when == "setup" and report.skipped):
            return
        if report.passed:
            kq = "đạt"
        elif report.skipped:
            kq = "bỏ qua"
        else:
            kq = "KHÔNG ĐẠT"
        self.ket_qua.append((report.nodeid.split("::")[-1], self._doc.get(report.nodeid, ""), kq))


def chay() -> list[tuple[str, str, str]]:
    import pytest

    gom = _GomKetQua()
    pytest.main(["-q", "-p", "no:cacheprovider", str(TEP_TEST)], plugins=[gom])
    return gom.ket_qua


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:  # noqa: BLE001
        return "?"


def dung_markdown(kq: list[tuple[str, str, str]]) -> str:
    """Phần thuần: kết quả -> markdown. Test được ở đây, không cần CSDL."""
    dat = sum(1 for _, _, k in kq if k == "đạt")
    dong = [
        "# Nghiệm thu từng chức năng",
        "",
        "<!-- SINH TỰ ĐỘNG bởi scripts/sinh_nghiem_thu.py — đừng sửa tay. -->",
        "",
        f"Chạy lúc {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} "
        f"trên commit `{_commit()}`. **{dat}/{len(kq)} kịch bản đạt.**",
        "",
        "Mỗi kịch bản chạy trên `agent.main.app` đầy đủ (middleware + lifespan) "
        "và Postgres thật, không kho giả, không gọi model. Các bước dưới đây là "
        "docstring của chính test — bảng không mô tả luồng nào khác luồng đã kiểm.",
        "",
        "| # | Chức năng | Kết quả |",
        "|---|---|---|",
    ]
    for i, (ten, doc, k) in enumerate(kq):
        tieu_de = doc.splitlines()[0].strip().rstrip(".") if doc else ten
        # Không đạt thì in ĐẬM: bảng mười dòng "đạt" mà một dòng lẫn vào
        # không nổi bật là bảng người ta đọc lướt qua.
        o = f"**{k}**" if k != "đạt" else k
        dong.append(f"| {i + 1} | {tieu_de} | {o} |")
    dong.append("")
    for i, (ten, doc, k) in enumerate(kq):
        cac_dong = doc.splitlines()
        tieu_de = cac_dong[0].strip().rstrip(".") if cac_dong else ten
        dong += [f"## {i + 1}. {tieu_de}", "", f"Kết quả: **{k}** · `{ten}`", ""]
        for d in cac_dong[1:]:
            d = d.strip()
            if d.startswith("BƯỚC"):
                so, _, phan = d[4:].strip().partition(" ")
                dong.append(f"{so}. {phan.strip()}")
        dong.append("")
    return "\n".join(dong)


def so_kich_ban_khai() -> int:
    """
    Đếm kịch bản KHAI trong file test, để so với số kết quả THU được.

    VÌ SAO PHẢI ĐẾM HAI ĐẦU
    -----------------------
    Plugin gom kết quả chỉ nhận được test đã CHẠY. Test hỏng lúc dựng
    (fixture ném — pytest gọi là ERROR chứ không phải FAILED) không sinh ra
    bản ghi nào, nên nó biến mất khỏi danh sách thay vì hiện ra là hỏng.

    Đã xảy ra thật 15.09.2026: `MCP_TOKEN` được điền, `_mcp_app` dựng một
    lần lúc import, còn `StreamableHTTPSessionManager.run()` của thư viện
    MCP chỉ cho gọi MỘT LẦN mỗi instance. Kịch bản 1 chạy xong là vòng đời
    đóng lại; kịch bản 2 dựng lại app và nổ. Mười một trong mười hai kịch
    bản không chạy được — mà bảng sinh ra ghi "1/1 kịch bản đạt", đọc ra là
    100%, và nếu chạy kèm `--ghi` thì nó đè mất bảng 12 mục có thật.

    Đếm hai đầu là cách duy nhất để "thiếu" khác với "đạt hết".
    """
    return sum(
        1 for d in TEP_TEST.read_text(encoding="utf-8").splitlines()
        if d.startswith("def test_")
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ghi", action="store_true", help="ghi vào docs/nghiem-thu.md")
    args = ap.parse_args()

    if not os.getenv("TEST_DATABASE_URL"):
        print("Thiếu TEST_DATABASE_URL — nghiệm thu cần Postgres thật, "
              "không sinh bảng từ trí nhớ.", file=sys.stderr)
        return 2

    kq = chay()
    khai = so_kich_ban_khai()
    if len(kq) != khai:
        print(
            f"CHỈ thu được {len(kq)}/{khai} kịch bản — {khai - len(kq)} cái KHÔNG CHẠY ĐƯỢC.\n"
            "Test hỏng ngay lúc dựng (ERROR, không phải FAILED) thì không sinh ra kết quả nào,\n"
            "nên nó lặng lẽ rơi khỏi danh sách: bảng còn lại toàn `đạt`, `all()` trả True, và\n"
            "mã thoát là 0. Tự động hoá nhìn thấy thành công.\n"
            "KHÔNG ghi tài liệu — bảng thiếu kịch bản sẽ ĐÈ LÊN bảng đầy đủ đã có, và nó đọc ra\n"
            "là đã nghiệm thu xong trong khi phần lớn chức năng chưa được kiểm lần nào.\n"
            "Chạy lại với -q để xem kịch bản nào hỏng và vì sao.",
            file=sys.stderr,
        )
        return 2

    md = dung_markdown(kq)
    if args.ghi:
        TEP_DOC.write_text(md, encoding="utf-8")
        print(f"Đã ghi {TEP_DOC.relative_to(ROOT)}")
    else:
        print(md)
    return 0 if all(k == "đạt" for _, _, k in kq) else 1


if __name__ == "__main__":
    raise SystemExit(main())
