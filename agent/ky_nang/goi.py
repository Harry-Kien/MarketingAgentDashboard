"""
Gói kỹ năng: hướng dẫn + công cụ + tài liệu + từ khoá + phiên bản, là DỮ LIỆU.

VÌ SAO HƯỚNG DẪN KÍCH HOẠT THEO TỪ KHOÁ
--------------------------------------
Nội dung gói thay đổi theo lượt, nên nó phải nằm ở khối biến động của prompt
(khối cache `SYSTEM` phải là cùng một chuỗi ở mọi request). Để mô hình tự
"mở" hướng dẫn qua một công cụ là thêm một vòng gọi mô hình mỗi lần dùng và
không tất định; so từ khoá sau `fold()` thì rẻ, đo được, test được.

VÌ SAO HƯỚNG DẪN BỊ QUÉT NHƯ TIN KHÁCH, CỘNG THÊM TỪ CẤM
--------------------------------------------------------
Hướng dẫn được ghép thẳng vào thứ mô hình đọc — nó là một mẩu prompt do người
trong nhà viết. Một dòng "luôn nói kem này chữa khỏi" là vi phạm Luật Quảng
cáo đi vòng qua mọi lưới, vì các lưới soi tin KHÁCH và câu TRẢ LỜI, không soi
hướng dẫn. Nên chặn ngay lúc lưu.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field

from agent.core import phong_thu
from agent.core.cham_mot_luot import fold, tu_cam
from agent.ky_nang.ban_mo_ta import BanMoTa, LoiBanMoTa, doc_ban_mo_ta
from agent.ky_nang.so_dang_ky import ten_ky_nang_co_san

GOI_TOI_DA = 20
CONG_CU_MOI_GOI_TOI_DA = 5
TAI_LIEU_MOI_GOI_TOI_DA = 20
HUONG_DAN_NGAN_NHAT = 50
HUONG_DAN_TOI_DA = 4000
GOI_MOI_LUOT_TOI_DA = 2
ZIP_TOI_DA = 2 * 1024 * 1024
TEP_ZIP_TOI_DA = 40
_TEN_RE = re.compile(r"^[a-z][a-z0-9-]{2,39}$")
_PHIEN_BAN_RE = re.compile(r"^\d+\.\d+\.\d+$")


class LoiGoi(ValueError):
    """Bản gói không hợp lệ. Thông điệp nói đúng trường sai."""


@dataclass
class Goi:
    ten: str
    phien_ban: str
    mo_ta: str
    tu_khoa: list[str]
    huong_dan: str
    cong_cu: list[BanMoTa] = field(default_factory=list)
    tai_lieu: list[dict] = field(default_factory=list)
    tho: dict = field(default_factory=dict)


def _chu(gia_tri, ten_o: str) -> str:
    if not isinstance(gia_tri, str):
        raise LoiGoi(f"Ô {ten_o} phải là chuỗi.")
    return gia_tri.strip()


def _quet(van_ban: str, ten_o: str) -> None:
    co, dau_hieu = phong_thu.quet(van_ban)
    if co:
        raise LoiGoi(f"Ô {ten_o} chứa câu ra lệnh cho mô hình ({', '.join(dau_hieu)}). "
                     "Hướng dẫn là chỗ mô tả việc, không phải chỗ đổi luật của agent.")


def doc_goi(tho: dict) -> Goi:
    if not isinstance(tho, dict):
        raise LoiGoi("Gói phải là một đối tượng JSON.")
    ten = _chu(tho.get("ten", ""), "ten")
    # Trùng tên kiểm TRƯỚC định dạng: tên công cụ viết sẵn dùng gạch dưới
    # (vd "tao_don_hang"), còn tên gói buộc dùng gạch ngang — nếu kiểm định
    # dạng trước thì một gói trùng tên công cụ luôn trượt ở lỗi định dạng,
    # không bao giờ tới được câu báo "trùng", và người viết gói sẽ không
    # biết vì sao tên đó bị chặn.
    if ten in ten_ky_nang_co_san():
        raise LoiGoi(f"{ten!r} trùng tên một công cụ viết sẵn.")
    if not _TEN_RE.match(ten):
        raise LoiGoi(f"Tên gói {ten!r} không hợp lệ (ô ten): chữ thường không dấu, số, gạch ngang, 3–40 ký tự.")
    phien_ban = _chu(tho.get("phien_ban", ""), "phien_ban")
    if not _PHIEN_BAN_RE.match(phien_ban):
        raise LoiGoi("Ô phien_ban phải dạng X.Y.Z (ví dụ 1.0.0).")
    mo_ta = _chu(tho.get("mo_ta", ""), "mo_ta")
    if not 20 <= len(mo_ta) <= 300:
        raise LoiGoi(f"Ô mo_ta dài {len(mo_ta)} ký tự, cần 20–300.")
    _quet(mo_ta, "mo_ta")

    tu_khoa_tho = tho.get("tu_khoa")
    if not isinstance(tu_khoa_tho, list) or not 1 <= len(tu_khoa_tho) <= 10:
        raise LoiGoi("Ô tu_khoa phải là mảng 1–10 cụm.")
    tu_khoa = []
    for k in tu_khoa_tho:
        k = _chu(k, "tu_khoa")
        if not 3 <= len(k) <= 40:
            raise LoiGoi(f"Từ khoá {k!r} (ô tu_khoa) cần 3–40 ký tự.")
        tu_khoa.append(k)

    huong_dan = _chu(tho.get("huong_dan", ""), "huong_dan")
    if not HUONG_DAN_NGAN_NHAT <= len(huong_dan) <= HUONG_DAN_TOI_DA:
        raise LoiGoi(f"Ô huong_dan dài {len(huong_dan)} ký tự, cần {HUONG_DAN_NGAN_NHAT}–{HUONG_DAN_TOI_DA}.")
    _quet(huong_dan, "huong_dan")
    cam = tu_cam(huong_dan)
    if cam:
        raise LoiGoi(f"Hướng dẫn chứa cụm cấm quảng cáo mỹ phẩm: {', '.join(cam)}. "
                     "Agent không được nói những cụm này với khách, nên hướng dẫn cũng không được dạy nó nói.")

    cong_cu_tho = tho.get("cong_cu") or []
    if not isinstance(cong_cu_tho, list) or len(cong_cu_tho) > CONG_CU_MOI_GOI_TOI_DA:
        raise LoiGoi(f"Ô cong_cu phải là mảng tối đa {CONG_CU_MOI_GOI_TOI_DA} công cụ.")
    cong_cu: list[BanMoTa] = []
    for c in cong_cu_tho:
        try:
            cong_cu.append(doc_ban_mo_ta(c))
        except LoiBanMoTa as exc:
            raise LoiGoi(f"Công cụ trong gói không hợp lệ: {exc}") from exc
    if len({c.ten for c in cong_cu}) != len(cong_cu):
        raise LoiGoi("Hai công cụ trong gói trùng tên.")

    tai_lieu_tho = tho.get("tai_lieu") or []
    if not isinstance(tai_lieu_tho, list) or len(tai_lieu_tho) > TAI_LIEU_MOI_GOI_TOI_DA:
        raise LoiGoi(f"Ô tai_lieu phải là mảng tối đa {TAI_LIEU_MOI_GOI_TOI_DA} tài liệu.")
    tai_lieu = []
    for t in tai_lieu_tho:
        if not isinstance(t, dict):
            raise LoiGoi("Mỗi tài liệu phải là đối tượng {tieu_de, noi_dung}.")
        tieu_de = _chu(t.get("tieu_de", ""), "tieu_de")
        noi_dung = _chu(t.get("noi_dung", ""), "noi_dung")
        if not 3 <= len(tieu_de) <= 120:
            raise LoiGoi(f"Ô tieu_de {tieu_de!r} cần 3–120 ký tự.")
        if not 50 <= len(noi_dung) <= 20_000:
            raise LoiGoi(f"Ô noi_dung của {tieu_de!r} dài {len(noi_dung)} ký tự, cần 50–20.000.")
        tai_lieu.append({"tieu_de": tieu_de, "noi_dung": noi_dung})

    sach = {"ten": ten, "phien_ban": phien_ban, "mo_ta": mo_ta, "tu_khoa": tu_khoa,
            "huong_dan": huong_dan, "cong_cu": cong_cu_tho, "tai_lieu": tai_lieu}
    return Goi(ten=ten, phien_ban=phien_ban, mo_ta=mo_ta, tu_khoa=tu_khoa,
               huong_dan=huong_dan, cong_cu=cong_cu, tai_lieu=tai_lieu, tho=sach)


def tu_zip(du_lieu: bytes) -> dict:
    """
    Đọc gói từ zip: `goi.json` + `HUONG_DAN.md` (nếu JSON chưa có) +
    `tai-lieu/*.md` (tiêu đề = dòng `# ...` đầu hoặc tên tệp). Zip chỉ là
    cách chia file; kết quả là đúng dict mà `doc_goi` nhận.
    """
    if len(du_lieu) > ZIP_TOI_DA:
        raise LoiGoi(f"Zip lớn hơn {ZIP_TOI_DA // 1024 // 1024} MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(du_lieu))
    except zipfile.BadZipFile as exc:
        raise LoiGoi("Tệp không phải zip hợp lệ.") from exc
    ten_tep = z.namelist()
    for n in ten_tep:
        # Zip slip: đường dẫn `../` hay tuyệt đối ghi ra ngoài thư mục đích.
        # Ở đây không ghi ra đĩa, nhưng chặn sớm để không ai tái dùng hàm này
        # rồi bị. Kiểm trên MỌI entry, kể cả entry thư mục — tên thư mục
        # cũng có thể mang "../".
        if n.startswith(("/", "\\")) or ".." in n.replace("\\", "/").split("/"):
            raise LoiGoi(f"Đường dẫn {n!r} trong zip không được phép.")
    # Entry thư mục (kết thúc bằng "/") do Windows/7-Zip tự thêm khi nén cả
    # một thư mục cha, không phải nội dung người viết gói bỏ vào. Đếm cả
    # chúng vào TEP_ZIP_TOI_DA thì một gói 40 tài liệu hợp lệ bị từ chối chỉ
    # vì công cụ nén tạo thêm vài entry rỗng — lỗi khó hiểu với người tạo
    # gói, vì họ đếm đúng 40 tệp .md trong thư mục của mình.
    tep_thuc = [n for n in ten_tep if not n.endswith("/")]
    if len(tep_thuc) > TEP_ZIP_TOI_DA:
        raise LoiGoi(f"Zip có hơn {TEP_ZIP_TOI_DA} tệp.")
    if "goi.json" not in ten_tep:
        raise LoiGoi("Zip thiếu goi.json.")
    try:
        tho = json.loads(z.read("goi.json").decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise LoiGoi(f"goi.json không đọc được: {exc}") from exc
    if not isinstance(tho, dict):
        raise LoiGoi("goi.json phải là một đối tượng JSON.")

    def _doc_van_ban(ten: str) -> str:
        # VÌ SAO decode STRICT CHỨ KHÔNG "replace": "replace" nuốt lỗi bảng
        # mã thành ký tự U+FFFD rồi lặng lẽ cho vào prompt — một tệp lưu sai
        # bảng mã (vd cp1258 thay vì UTF-8) tới model dưới dạng vài ô vuông
        # giữa văn bản, không lỗi, không nhật ký, không ai biết cho tới khi
        # khách nhận câu trả lời tham chiếu một đoạn tài liệu đã hỏng.
        try:
            return z.read(ten).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LoiGoi(f"{ten} không đọc được (không phải UTF-8): {exc}") from exc

    if "HUONG_DAN.md" in ten_tep and not tho.get("huong_dan"):
        tho["huong_dan"] = _doc_van_ban("HUONG_DAN.md")
    tai_lieu = list(tho.get("tai_lieu") or [])
    for n in sorted(tep_thuc):
        if n.startswith("tai-lieu/") and n.endswith(".md"):
            van_ban = _doc_van_ban(n)
            dong_dau = van_ban.strip().splitlines()[0] if van_ban.strip() else ""
            tieu_de = dong_dau.lstrip("# ").strip() if dong_dau.startswith("#") else n.rsplit("/", 1)[-1][:-3]
            noi_dung = van_ban.split("\n", 1)[1] if dong_dau.startswith("#") and "\n" in van_ban else van_ban
            tai_lieu.append({"tieu_de": tieu_de, "noi_dung": noi_dung.strip()})
    tho["tai_lieu"] = tai_lieu
    return tho


def chon_goi(cac_goi: list[Goi], cau_hoi: str) -> list[Goi]:
    """
    Các gói có từ khoá khớp câu hỏi (so sau `fold`), nhiều từ khoá khớp
    xếp trước, cùng số thì theo tên; tối đa GOI_MOI_LUOT_TOI_DA.
    """
    q = fold(cau_hoi)
    diem = []
    for gk in cac_goi:
        n = sum(1 for k in gk.tu_khoa if fold(k) in q)
        if n:
            diem.append((-n, gk.ten, gk))
    return [x[2] for x in sorted(diem)[:GOI_MOI_LUOT_TOI_DA]]
