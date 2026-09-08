"""
Nhập một gói viết theo chuẩn Agent Skills: thư mục hoặc zip có `SKILL.md`.

VÌ SAO CÓ ĐƯỜNG NÀY

Định dạng `goi.json` của repo không sai, nhưng nó là định dạng RIÊNG. Chuẩn
Agent Skills là một thư mục có `SKILL.md`, YAML frontmatter hai trường bắt
buộc `name` và `description`, thân file là hướng dẫn markdown, kèm các `.md`
khác và thư mục `scripts/`. Ai đã quen chuẩn ấy, hoặc muốn lấy skill từ kho
mở, hiện phải viết lại từ đầu — và "phải viết lại từ đầu" là lý do người ta
không dùng.

NHẬP CHỨ KHÔNG THAY

`goi.json` giữ nguyên và vẫn là định dạng đầy đủ nhất. Nó mang ba thứ chuẩn
kia không có mà repo này cần:

  * `tu_khoa`  — kích hoạt TẤT ĐỊNH. Chuẩn kia để mô hình đọc `description`
                 rồi tự quyết; ở đây một lượt gọi model để chọn gói là thêm
                 tiền và thêm chỗ trượt.
  * `cong_cu`  — bản mô tả plugin đã qua `doc_ban_mo_ta`.
  * `phien_ban`— cho lịch sử và khôi phục.

Tệp này chỉ DỊCH sang `goi.json` rồi giao lại cho `doc_goi`, nên mọi phép
kiểm của gói vẫn chạy nguyên vẹn: quét injection, từ cấm quảng cáo, trần
tài liệu. Một gói đi vào bằng SKILL.md không được lỏng hơn gói gõ tay.

VÌ SAO `scripts/` BỊ TỪ CHỐI CHỨ KHÔNG BỎ QUA

Chuẩn kia cho phép skill mang mã chạy được. Repo này cấm, và đó là ràng
buộc gốc: mã chạy trong tiến trình agent nằm CÙNG PHÍA với sáu lớp lưới —
đọc được biến môi trường, gọi được CSDL, sửa được chính hàm canh nó.

Bỏ qua thư mục ấy trong im lặng thì gói vẫn cài được, nhưng chạy với ít
năng lực hơn người viết tưởng; skill dựa vào script sẽ hỏng giữa chừng và
không ai biết vì sao. Từ chối và nói thẳng thì họ đọc được lý do trong một
câu, ngay lúc bấm Kiểm.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import yaml

# Ràng buộc của chuẩn, giữ nguyên chứ không nới: chữ thường, số, gạch ngang,
# tối đa 64 ký tự, không mang tên nhà cung cấp.
_TEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TU_DANH_RIENG = ("anthropic", "claude")
MO_TA_DAI_TOI_DA = 1024
ZIP_TOI_DA = 2 * 1024 * 1024
TEP_TOI_DA = 40

# Từ quá chung để làm từ khoá kích hoạt: gói nào cũng khớp thì không gói nào
# được chọn đúng, và trần hai gói mỗi lượt bị chiếm bởi thứ ngẫu nhiên.
_TU_BO = {
    "tu", "van", "cho", "va", "cua", "khi", "nao", "gi", "la", "cac", "mot",
    "khach", "hang", "dung", "shop", "skill", "agent", "help", "with", "the",
    "for", "and", "use", "when", "user", "this", "that",
}


class LoiSkillMd(ValueError):
    """SKILL.md không đọc được. Thông điệp nói rõ sửa gì."""


def _tach_frontmatter(van_ban: str) -> tuple[dict, str]:
    """
    Frontmatter YAML giữa hai dòng `---`, phần còn lại là hướng dẫn.

    Lỗi YAML được gói lại thành `LoiSkillMd`: người vận hành đọc được
    "SKILL.md: frontmatter hỏng", không đọc được vết ngăn xếp của thư viện.
    """
    if not van_ban.lstrip().startswith("---"):
        raise LoiSkillMd(
            "SKILL.md thiếu frontmatter. Chuẩn Agent Skills đòi ba gạch ngang "
            "ở dòng đầu, rồi `name:` và `description:`, rồi ba gạch ngang nữa."
        )
    phan = van_ban.lstrip().split("---", 2)
    if len(phan) < 3:
        raise LoiSkillMd("SKILL.md: frontmatter chưa được đóng bằng dòng `---`.")
    try:
        dau = yaml.safe_load(phan[1]) or {}
    except yaml.YAMLError as exc:
        raise LoiSkillMd(f"SKILL.md: frontmatter hỏng — {str(exc)[:160]}") from exc
    if not isinstance(dau, dict):
        raise LoiSkillMd("SKILL.md: frontmatter phải là các cặp `khoá: giá trị`.")
    return dau, phan[2].strip()


def _tu_khoa_tu(ten: str, mo_ta: str) -> list[str]:
    """
    Từ khoá kích hoạt, khi frontmatter không khai.

    Chuẩn kia không có trường này vì mô hình tự đọc `description`. Ở đây so
    khớp là tất định, nên KHÔNG sinh gì thì gói cài xong sẽ không bao giờ
    tới lượt — mà dashboard vẫn hiện "đang bật". Đúng kiểu hỏng im lặng.

    Lấy từ `name` chứ không từ `description`: tên là cụm người viết đã cô
    lại, còn mô tả dài và đầy từ nối. Ghép cả cụm tên rồi mới tới từng từ,
    để "chống nắng" đứng trước "nắng".
    """
    tho = [p for p in ten.split("-") if p and p.lower() not in _TU_BO]
    ra: list[str] = []
    if len(tho) >= 2:
        ra.append(" ".join(tho))
    ra.extend(t for t in tho if len(t) >= 3)
    # Vẫn rỗng thì lấy cụm ba từ đầu của mô tả — thà một từ khoá hẹp còn
    # hơn không có từ khoá nào.
    if not ra and mo_ta:
        ra.append(" ".join(mo_ta.split()[:3]))
    return ra[:10]


def _doc_tep(z: zipfile.ZipFile, ten: str) -> str:
    try:
        return z.read(ten).decode("utf-8")
    except UnicodeDecodeError as exc:
        # Cùng lý do với `goi.tu_zip`: decode "replace" nuốt lỗi bảng mã
        # thành ô vuông rồi đưa thẳng vào prompt, không lỗi, không nhật ký.
        raise LoiSkillMd(f"{ten} không phải UTF-8: {exc}") from exc


def tu_skill_md(du_lieu: bytes) -> dict:
    """
    Zip theo chuẩn Agent Skills → dict mà `goi.doc_goi` nhận.

    Không tự gọi `doc_goi`: tách dịch khỏi kiểm để nút Kiểm trên dashboard
    chạy đúng một đường với nút Cài, và để thông điệp lỗi nói rõ lỗi nằm ở
    khâu đọc SKILL.md hay ở khâu kiểm nội dung.
    """
    if len(du_lieu) > ZIP_TOI_DA:
        raise LoiSkillMd(f"Zip lớn hơn {ZIP_TOI_DA // 1024 // 1024} MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(du_lieu))
    except zipfile.BadZipFile as exc:
        raise LoiSkillMd("Tệp không phải zip hợp lệ.") from exc

    ten_tep = [n for n in z.namelist() if not n.endswith("/")]
    for n in ten_tep:
        # Zip slip, cùng phép kiểm với `goi.tu_zip`.
        if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/"):
            raise LoiSkillMd(f"Đường dẫn {n!r} trong zip không được phép.")
    if len(ten_tep) > TEP_TOI_DA:
        raise LoiSkillMd(f"Zip có hơn {TEP_TOI_DA} tệp.")

    duong = next((n for n in ten_tep if Path(n).name == "SKILL.md"), None)
    if duong is None:
        raise LoiSkillMd(
            "Không thấy SKILL.md. Chuẩn Agent Skills đòi một tệp tên đúng "
            "`SKILL.md` ở gốc gói (nén cả thư mục cũng được)."
        )
    goc = duong[: -len("SKILL.md")]

    co_script = [n for n in ten_tep if n[len(goc):].startswith("scripts/")]
    if co_script:
        raise LoiSkillMd(
            "Gói có thư mục `scripts/`, và kỹ năng ở hệ thống này KHÔNG chạy "
            "mã: mã chạy trong tiến trình agent thì nằm cùng phía với các lớp "
            "lưới an toàn — đọc được biến môi trường, gọi được cơ sở dữ liệu. "
            "Bỏ thư mục ấy đi, hoặc chuyển việc nó làm thành một công cụ "
            "`goi_api_doc` trỏ vào máy chủ của bạn."
        )

    dau, than = _tach_frontmatter(_doc_tep(z, duong))

    ten = str(dau.get("name") or "").strip()
    if not _TEN_RE.match(ten):
        raise LoiSkillMd(
            f"`name: {ten}` không hợp lệ. Chuẩn đòi chữ thường, số và gạch "
            "ngang, tối đa 64 ký tự — ví dụ `tu-van-chong-nang`."
        )
    if any(t in ten for t in _TU_DANH_RIENG):
        raise LoiSkillMd(
            f"`name` không được chứa {' hay '.join(_TU_DANH_RIENG)} — chuẩn "
            "giữ riêng những từ ấy."
        )

    mo_ta = " ".join(str(dau.get("description") or "").split())
    if not mo_ta:
        raise LoiSkillMd(
            "`description` bắt buộc, và phải nói CẢ việc kỹ năng làm gì LẪN "
            "khi nào dùng nó."
        )
    if len(mo_ta) > MO_TA_DAI_TOI_DA:
        raise LoiSkillMd(f"`description` dài quá {MO_TA_DAI_TOI_DA} ký tự.")

    tu_khoa = dau.get("keywords") or dau.get("tu_khoa")
    if isinstance(tu_khoa, str):
        tu_khoa = [t.strip() for t in tu_khoa.split(",") if t.strip()]
    if not isinstance(tu_khoa, list) or not tu_khoa:
        tu_khoa = _tu_khoa_tu(ten, mo_ta)

    tai_lieu = []
    for n in sorted(ten_tep):
        con = n[len(goc):]
        if n == duong or not con.endswith(".md") or "/" in con.rstrip("/"):
            continue
        van_ban = _doc_tep(z, n)
        dong_dau = van_ban.strip().splitlines()[0] if van_ban.strip() else ""
        tieu_de = (dong_dau.lstrip("# ").strip() if dong_dau.startswith("#")
                   else Path(con).stem)
        noi_dung = (van_ban.split("\n", 1)[1] if dong_dau.startswith("#") and "\n" in van_ban
                    else van_ban)
        tai_lieu.append({"tieu_de": tieu_de, "noi_dung": noi_dung.strip()})

    return {
        "ten": ten,
        # Chuẩn không có phiên bản. Gói ở đây thì có, cho lịch sử và khôi
        # phục — bắt đầu từ 1.0.0 và người vận hành tăng khi cài lại.
        "phien_ban": str(dau.get("version") or "1.0.0"),
        "mo_ta": mo_ta[:300],
        "tu_khoa": tu_khoa,
        "huong_dan": than,
        "cong_cu": [],
        "tai_lieu": tai_lieu,
    }
