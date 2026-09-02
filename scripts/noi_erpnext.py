"""
Nối hệ thống vào ERPNext đang chạy: sinh khoá API, chọn kho và bảng giá,
ghi thẳng vào `.env`.

    python -m scripts.noi_erpnext                 dùng Administrator/admin
    python -m scripts.noi_erpnext --mat-khau X    nếu đã đổi mật khẩu
    python -m scripts.noi_erpnext --xem           chỉ xem, không ghi gì

BÍ MẬT KHÔNG BAO GIỜ IN RA MÀN HÌNH
-----------------------------------
Khoá API ghi thẳng vào `.env`, đúng quy ước `scripts/sinh_token.py`. In ra
là để lại bí mật trong lịch sử terminal và trong ảnh chụp màn hình — hai
chỗ không xoá được.

VÌ SAO CHỌN KHO VÀ BẢNG GIÁ Ở ĐÂY
---------------------------------
`agent/erp/erpnext.py` NÉM ngay lúc khởi động nếu thiếu `ERP_MA_KHO` hoặc
`ERP_PRICELIST`, với lý do đã ghi trong mã: thiếu mã kho thì `Bin` trả tồn
của MỌI kho cộng lại — một con số trông hợp lý và sai, không ai phát hiện
cho tới lúc giao hàng từ kho không có hàng.

Bắt người dùng tự đi tra hai cái tên đó trong giao diện ERPNext là bước dễ
làm sai nhất trong cả quy trình. Script hỏi thẳng ERPNext.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# Console Windows mac dinh cp1258 khong in duoc tieng Viet.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GOC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GOC))

import httpx  # noqa: E402

ENV = GOC / ".env"
MAC_DINH = "http://localhost:8080"


def _ghi_env(cap: dict[str, str]) -> None:
    """
    Thay từng dòng trong `.env`, không ghi đè cả tệp.

    Ghi đè cả tệp là mất mọi khoá kết nối khác — cùng lý do đã ghi trong
    `scripts/sinh_token.py`. Sao lưu trước khi sửa.
    """
    shutil.copyfile(ENV, ENV.with_name(".env.bak"))
    noi_dung = ENV.read_text(encoding="utf-8")
    for khoa, gia_tri in cap.items():
        mau = re.compile(rf"^{re.escape(khoa)}=.*$", re.M)
        if mau.search(noi_dung):
            noi_dung = mau.sub(f"{khoa}={gia_tri}", noi_dung, count=1)
        else:
            noi_dung = noi_dung.rstrip("\n") + f"\n{khoa}={gia_tri}\n"
    ENV.write_text(noi_dung, encoding="utf-8")


def _chon(ten_muc: str, ds: list[str], chi_dinh: str = "", co: str = "") -> str | None:
    """
    Có đúng một thì lấy luôn; nhiều thì bắt người chọn, KHÔNG tự đoán.

    `chi_dinh` là lựa chọn người dùng gõ ra — vẫn phải có thật bên ERPNext.
    Nhận bừa một cái tên gõ nhầm rồi ghi vào `.env` là dựng lại đúng cái bẫy
    script này sinh ra để tránh: cấu hình trông đúng, hệ thống chạy, và tồn
    kho sai mãi về sau.
    """
    if not ds:
        print(f"  [LỖI] ERPNext chưa có {ten_muc} nào. Tạo trong giao diện rồi chạy lại.")
        return None
    if chi_dinh:
        if chi_dinh in ds:
            print(f"  {ten_muc}: {chi_dinh}  (bạn chỉ định)")
            return chi_dinh
        print(f"  [LỖI] ERPNext không có {ten_muc} tên {chi_dinh!r}. Hiện có:")
        for t in ds:
            print(f"           {t}")
        return None
    if len(ds) == 1:
        print(f"  {ten_muc}: {ds[0]}")
        return ds[0]
    print(f"  [CHỌN] Có {len(ds)} {ten_muc}, không tự đoán được:")
    for t in ds:
        print(f"           {t}")
    print(f"         Chạy lại kèm {co} \"<tên>\" để chọn.")
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Nối hệ thống vào ERPNext")
    p.add_argument("--url", default=MAC_DINH)
    p.add_argument("--tai-khoan", default="Administrator", dest="tai_khoan")
    p.add_argument("--mat-khau", default="admin", dest="mat_khau")
    p.add_argument("--xem", action="store_true",
                   help="chỉ xem, KHÔNG sinh khoá và KHÔNG ghi .env")
    # Chọn TƯỜNG MINH khi có nhiều lựa chọn.
    #
    # Khác hẳn với để script tự đoán: ở đây người dùng gõ ra tên kho, tức
    # đã đọc danh sách và quyết. Script vẫn kiểm tên đó có thật bên ERPNext
    # — gõ nhầm mà vẫn ghi vào .env là dựng lại đúng cái bẫy "sai im lặng".
    p.add_argument("--kho", default="", help="tên kho, khi ERPNext có nhiều kho")
    p.add_argument("--bang-gia", default="", dest="bang_gia",
                   help="tên bảng giá, khi ERPNext có nhiều bảng giá")
    a = p.parse_args(argv)

    if not ENV.exists():
        print("[LỖI] Chưa có .env. Chạy: cp .env.example .env")
        return 1

    goc = a.url.rstrip("/")
    print(f"ERPNext: {goc}\n")

    with httpx.Client(base_url=goc, timeout=30, follow_redirects=True) as c:
        try:
            r = c.post("/api/method/login",
                       json={"usr": a.tai_khoan, "pwd": a.mat_khau})
        except httpx.HTTPError as exc:
            print(f"[LỖI] Không nối được {goc}: {type(exc).__name__}: {exc}")
            print("      ERPNext đã chạy chưa? "
                  "docker compose -f docker-compose.erpnext.yml ps")
            return 1
        if r.status_code != 200:
            print(f"[LỖI] Đăng nhập thất bại ({r.status_code}). "
                  "Sai mật khẩu? Dùng --mat-khau để đổi.")
            return 1
        print(f"Đã đăng nhập: {a.tai_khoan}")

        def ds(doctype: str, **loc) -> list[str]:
            r = c.get(f"/api/resource/{doctype}",
                      params={"limit_page_length": 0, **loc})
            if r.status_code != 200:
                return []
            return [x["name"] for x in r.json().get("data", [])]

        kho = _chon("kho", ds("Warehouse", filters='[["is_group","=",0]]'),
                    a.kho, "--kho")
        bang_gia = _chon("bảng giá", ds("Price List", filters='[["selling","=",1]]'),
                         a.bang_gia, "--bang-gia")

        if a.xem:
            print("\nChế độ xem — chưa sinh khoá, chưa ghi .env.")
            return 0
        if kho is None or bang_gia is None:
            print("\nThiếu kho hoặc bảng giá, dừng lại — không ghi .env.")
            return 1

        # Sinh khoá API cho tài khoản. `api_secret` CHỈ trả về đúng một lần.
        r = c.post(
            "/api/method/frappe.core.doctype.user.user.generate_keys",
            json={"user": a.tai_khoan},
        )
        if r.status_code != 200:
            print(f"[LỖI] Không sinh được khoá API ({r.status_code}): "
                  f"{r.text[:200]}")
            return 1
        bi_mat = r.json().get("message", {}).get("api_secret", "")

        r = c.get(f"/api/resource/User/{a.tai_khoan}",
                  params={"fields": '["api_key"]'})
        khoa = (r.json().get("data") or {}).get("api_key", "") if r.status_code == 200 else ""

        if not khoa or not bi_mat:
            print("[LỖI] ERPNext không trả về đủ api_key và api_secret.")
            return 1

    _ghi_env({
        "ERP_LOAI": "erpnext",
        "ERPNEXT_URL": goc,
        "ERPNEXT_API_KEY": khoa,
        "ERPNEXT_API_SECRET": bi_mat,
        "ERP_MA_KHO": kho,
        "ERP_PRICELIST": bang_gia,
    })

    print(
        "\nĐã ghi vào .env: ERP_LOAI, ERPNEXT_URL, ERPNEXT_API_KEY,\n"
        "ERPNEXT_API_SECRET, ERP_MA_KHO, ERP_PRICELIST.\n"
        "Giá trị khoá KHÔNG được in ra. Bản sao lưu: .env.bak\n"
        "\nKiểm lại:  python -m scripts.thu_erp"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
