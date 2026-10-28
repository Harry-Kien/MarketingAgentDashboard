"""
Sinh BẢN NHÁP hồ sơ đánh giá tác động xử lý dữ liệu cá nhân — từ cấu hình
thật của hệ thống, không phải từ trí nhớ của người điền.

    python -m scripts.sinh_ho_so_bvdlcn          in ra màn hình
    python -m scripts.sinh_ho_so_bvdlcn --ghi    ghi data/ho_so_bvdlcn/<ngày>.md

VÌ SAO CÓ LỆNH NÀY
------------------
Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 buộc lập hồ sơ đánh giá tác động
xử lý (Điều 21) và hồ sơ chuyển dữ liệu ra nước ngoài (Điều 20), gửi cơ quan
chuyên trách trong 60 ngày kể từ lần xử lý / chuyển đầu tiên. Hệ thống này
chạm cả hai:

  · khách gửi ảnh vùng da, kể tình trạng da — "tình trạng sức khoẻ" là dữ
    liệu NHẠY CẢM (Nghị định 356/2025/NĐ-CP Điều 4 khoản 1 điểm d). Vì thế
    miễn trừ cho doanh nghiệp nhỏ/siêu nhỏ (NĐ 356 Điều 41) KHÔNG áp dụng;
  · nội dung hội thoại được gửi tới máy chủ model đặt ngoài Việt Nam để sinh
    câu trả lời — đúng trường hợp "xử lý trên nền tảng ở ngoài lãnh thổ".

Hồ sơ điền tay thì mô tả hệ thống người điền NGHĨ là đang chạy. Lệnh này
đọc cấu hình đang chạy: đổi nhà cung cấp model là bản nháp đổi theo.

KHÔNG PHẢI TƯ VẤN PHÁP LÝ. Bản nháp này giúp người phụ trách khỏi bắt đầu
từ trang trắng; mẫu chính thức là Mẫu số 09 kèm Nghị định 356/2025/NĐ-CP.
Không in bí mật nào — chỉ tên nhà cung cấp và vùng.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent.config import settings

GOC = Path(__file__).resolve().parent.parent
VN = timezone(timedelta(hours=7))

_NOI_MODEL = {
    "gemini_api": ("Google (Gemini API)", "máy chủ Google ngoài Việt Nam"),
    "gemini": ("Google Cloud (Vertex AI — Gemini)", "vùng {gemini_region}"),
    "vertex": ("Google Cloud (Vertex AI — Claude)", "vùng {gcp_region}"),
    "anthropic": ("Anthropic", "máy chủ Anthropic ngoài Việt Nam"),
}


def _noi_model() -> tuple[str, str]:
    p = (settings.llm_provider or "").strip().lower()
    ten, noi = _NOI_MODEL.get(p, (f"nhà cung cấp {p!r}", "chưa xác định — kiểm lại"))
    return ten, noi.format(gemini_region=settings.gemini_region, gcp_region=settings.gcp_region)


def sinh(bay_gio: datetime | None = None) -> str:
    t = (bay_gio or datetime.now(VN)).astimezone(VN)
    ten_model, noi_model = _noi_model()
    van_chuyen = (settings.shipping_provider or "").strip().lower()
    hang = {"ghn": "Giao Hàng Nhanh", "ghtk": "Giao Hàng Tiết Kiệm"}.get(van_chuyen)
    erp = (settings.erp_loai or "").strip().lower()
    dong = [
        "# BẢN NHÁP — Hồ sơ đánh giá tác động xử lý dữ liệu cá nhân",
        "",
        f"> Sinh tự động lúc {t:%H:%M %d/%m/%Y} từ cấu hình đang chạy "
        "(`python -m scripts.sinh_ho_so_bvdlcn`). **Không phải tư vấn pháp lý.** "
        "Người phụ trách bảo vệ dữ liệu phải rà, bổ sung phần [ĐIỀN TAY] và lập "
        "theo **Mẫu số 09** kèm Nghị định 356/2025/NĐ-CP trước khi nộp.",
        "",
        "## 1. Căn cứ và thời hạn nộp",
        "",
        "- Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15 (hiệu lực 01/01/2026): Điều 21 "
        "(đánh giá tác động xử lý), Điều 20 (chuyển dữ liệu ra nước ngoài), Điều 22 (cập nhật).",
        "- Nghị định 356/2025/NĐ-CP: Điều 4 (danh mục dữ liệu nhạy cảm), Điều 17–18 "
        "(hồ sơ chuyển dữ liệu ra nước ngoài), Điều 41 (miễn trừ doanh nghiệp nhỏ).",
        "- Gửi **01 bản chính** tới cơ quan chuyên trách bảo vệ dữ liệu cá nhân trong "
        "**60 ngày** kể từ lần xử lý / lần chuyển đầu tiên.",
        "- **Miễn trừ doanh nghiệp nhỏ KHÔNG áp dụng**: hệ thống trực tiếp xử lý dữ liệu "
        "nhạy cảm (tình trạng sức khoẻ — xem mục 3).",
        "",
        "## 2. Bên kiểm soát dữ liệu",
        "",
        "- Tên doanh nghiệp / hộ kinh doanh: [ĐIỀN TAY]",
        "- Người phụ trách bảo vệ dữ liệu, liên hệ: [ĐIỀN TAY]",
        "",
        "## 3. Loại dữ liệu xử lý",
        "",
        "| Loại | Dữ liệu | Nguồn |",
        "|---|---|---|",
        "| Cơ bản | họ tên, số điện thoại, địa chỉ giao hàng, mã định danh trên kênh nhắn tin | khách tự cung cấp khi nhắn tin, đặt hàng |",
        "| Cơ bản | nội dung hội thoại, lịch sử đơn hàng | phát sinh khi tư vấn, bán hàng |",
        "| **Nhạy cảm** | **tình trạng da** (ảnh vùng da, mô tả mụn, kích ứng, dị ứng) — "
        "\"tình trạng sức khoẻ\", NĐ 356/2025 Điều 4 khoản 1 điểm d | khách tự gửi khi hỏi tư vấn |",
        "",
        "## 4. Mục đích xử lý",
        "",
        "- Tư vấn sản phẩm, trả lời câu hỏi của khách (có căn cứ từ tài liệu cửa hàng).",
        "- Lên đơn, giao hàng, chăm sóc sau bán.",
        "- Gửi tin quảng cáo: **chỉ khi khách đồng ý riêng cho mục đích này** "
        "(bảng `contact_consents`, chốt chặn trong outbox).",
        "",
        "## 5. Luồng dữ liệu",
        "",
        "```",
        "khách ──(Zalo / Facebook / Instagram / web)──> máy chủ cửa hàng (Postgres, Việt Nam: [ĐIỀN TAY nơi đặt máy chủ])",
        f"                                              ├──> model ngôn ngữ: {ten_model} — {noi_model}",
        (f"                                              ├──> hãng vận chuyển: {hang} (trong nước) — tên, SĐT, địa chỉ"
         if hang else "                                              ├──> vận chuyển: chưa nối hãng nào"),
        (f"                                              └──> ERP: {erp} (máy chủ của cửa hàng)"
         if erp and erp != "tep" else "                                              └──> ERP: tệp nội bộ, không ra ngoài"),
        "```",
        "",
        "## 6. Chuyển dữ liệu ra nước ngoài",
        "",
        f"- **CÓ.** Nội dung hội thoại (có thể gồm dữ liệu nhạy cảm ở mục 3) được gửi tới "
        f"**{ten_model}** ({noi_model}) để sinh câu trả lời — trường hợp xử lý trên nền tảng "
        "đặt ngoài lãnh thổ (Luật 91/2025 Điều 20 khoản 1; NĐ 356/2025 Điều 17 khoản 1).",
        "- Hồ sơ chuyển dữ liệu ra nước ngoài gồm: báo cáo đánh giá tác động (Mẫu số 09), "
        "bản sao hợp đồng / điều khoản với bên nhận, chính sách bảo vệ dữ liệu của các bên "
        "(NĐ 356/2025 Điều 18 khoản 2). [ĐIỀN TAY: đính kèm điều khoản dịch vụ và điều khoản "
        "xử lý dữ liệu của nhà cung cấp model].",
        "",
        "## 7. Thời hạn lưu trữ",
        "",
        f"- Hội thoại, tin nhắn: **{int(settings.luu_hoi_thoai_ngay)} ngày** rồi tự xoá "
        f"({'đang bật tự dọn hằng ngày' if settings.tu_dong_don_du_lieu else 'ĐANG TẮT tự dọn — dọn tay'}).",
        "- Đơn hàng: tối thiểu 10 năm (chứng từ kế toán, Luật Kế toán 2015 Điều 41); khi khách "
        "yêu cầu xoá thì ẩn danh, giữ số liệu kế toán.",
        "",
        "## 8. Biện pháp bảo vệ đang áp dụng",
        "",
        "- Phân quyền theo vai trò, mặc định từ chối; mỗi API khai quyền, thiếu là máy chủ không khởi động.",
        "- Xác thực hai bước cho nhân viên; token phiên lưu dạng băm.",
        "- Khoá truy cập dịch vụ ngoài mã hoá trong kho bí mật.",
        "- Xoá dữ liệu cần hai người (người xin, người duyệt); mọi lần xoá ghi nhật ký kèm căn cứ.",
        "- Sổ yêu cầu của khách đếm hạn theo NĐ 356/2025 Điều 5; quá hạn thì báo đỏ.",
        # KHÔNG ghi "sao lưu mã hoá": bản sao lưu hằng ngày (scripts/sao_luu.py)
        # là pg_dump nén, chưa mã hoá — chỉ gói chuyển nhà mới mã hoá. Hồ sơ
        # khai một biện pháp không có là khai sai với cơ quan nhà nước.
        "- Sao lưu hằng ngày, được thử phục hồi mỗi tuần. **Bản sao lưu chưa mã hoá** — "
        "[ĐIỀN TAY: nơi cất, ai truy cập được; hoặc bổ sung mã hoá].",
        "- [ĐIỀN TAY: biện pháp vật lý, đào tạo nhân viên, quy trình xử lý sự cố 72 giờ — Luật Điều 23].",
        "",
        "## 9. Việc còn phải làm ngoài hệ thống",
        "",
        "- Thông báo cho khách, **trước khi** xử lý dữ liệu nhạy cảm, rằng ảnh và mô tả tình trạng "
        "da là dữ liệu nhạy cảm, và xin đồng ý (NĐ 356/2025 Điều 6 khoản 4). [ĐIỀN TAY: câu thông báo đã dùng]",
        "- Thông báo việc xử lý tự động bằng AI và cho khách lựa chọn nói chuyện với người "
        "(NĐ 356/2025 Điều 10 khoản 3).",
        "- Nộp hồ sơ này và hồ sơ chuyển dữ liệu ra nước ngoài trong 60 ngày; cập nhật khi đổi "
        "nhà cung cấp model hoặc hãng vận chuyển (Luật 91/2025 Điều 22).",
        "",
    ]
    return "\n".join(dong)


def main(argv: list[str]) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    van_ban = sinh()
    if "--ghi" in argv:
        thu_muc = GOC / "data" / "ho_so_bvdlcn"
        thu_muc.mkdir(parents=True, exist_ok=True)
        dich = thu_muc / f"{datetime.now(VN):%Y-%m-%d}.md"
        dich.write_text(van_ban, encoding="utf-8")
        print(f"Đã ghi {dich.relative_to(GOC)} — BẢN NHÁP, rà và điền phần [ĐIỀN TAY] trước khi nộp.")
    else:
        print(van_ban)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
