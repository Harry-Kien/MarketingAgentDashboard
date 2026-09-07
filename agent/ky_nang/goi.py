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
import logging
import re
import time
import zipfile
from dataclasses import dataclass, field

from agent import db
from agent.core import phong_thu, rag
from agent.core.cham_mot_luot import fold, tu_cam
from agent.ky_nang import kho_ky_nang
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


_log = logging.getLogger("agent.ky_nang.goi")
_DEM: tuple[float, tuple[Goi, ...]] | None = None
_DEM_GIAY = 30.0


class GoiKhongTonTai(LookupError):
    """Không có gói tên này."""


class KhoDay(RuntimeError):
    """Đã đủ GOI_TOI_DA gói."""


def xoa_dem() -> None:
    global _DEM
    _DEM = None


def _nguon(ten: str) -> str:
    return f"goi:{ten}:"


async def _nap_tai_lieu(g: Goi) -> None:
    await rag.xoa_nguon(_nguon(g.ten))
    for i, t in enumerate(g.tai_lieu):
        await rag.ingest(f"[{g.ten}] {t['tieu_de']}", f"{_nguon(g.ten)}{i:02d}", t["noi_dung"])


async def _ghi_plugin(g: Goi, bat: bool) -> None:
    await db.execute("DELETE FROM ky_nang_cai_dat WHERE goi = $1", g.ten)
    for bm, tho in zip(g.cong_cu, g.tho["cong_cu"], strict=True):
        await db.execute(
            """
            INSERT INTO ky_nang_cai_dat (ten, bat, ban_mo_ta, tao_boi, goi)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (ten) DO UPDATE
                SET ban_mo_ta = EXCLUDED.ban_mo_ta, bat = EXCLUDED.bat,
                    goi = EXCLUDED.goi, sua_luc = now()
            """,
            bm.ten, bat, json.dumps(tho, ensure_ascii=False), "goi", g.ten,
        )


async def _doc_hien_hanh(ten: str) -> dict | None:
    return await db.fetchrow("SELECT ten, phien_ban, bat, noi_dung FROM goi_ky_nang WHERE ten = $1", ten)


async def cai(tho: dict, *, boi: str) -> Goi:
    """
    Kiểm toàn bộ TRƯỚC khi chạm CSDL: sai một là không ghi gì.

    Thứ tự ghi: lịch sử → gói → plugin → tài liệu. Tài liệu đứng cuối vì
    nó gọi API nhúng (chậm, có thể hỏng); hỏng ở đó thì gói đã có nhưng bị
    tắt và người dùng được báo, thay vì một gói "đã cài" mà kho tri thức
    trống — kiểu hỏng im lặng.
    """
    g = doc_goi(tho)
    hien = await _doc_hien_hanh(g.ten)
    if hien is None:
        so = len(await db.fetch("SELECT ten FROM goi_ky_nang"))
        if so >= GOI_TOI_DA:
            raise KhoDay(f"Đã đủ {GOI_TOI_DA} gói. Xoá bớt gói không dùng.")
    elif hien["phien_ban"] != g.phien_ban:
        nd = hien["noi_dung"]
        await db.execute(
            "INSERT INTO goi_ky_nang_lich_su (ten, phien_ban, noi_dung, thay_boi) VALUES ($1, $2, $3::jsonb, $4)",
            g.ten, hien["phien_ban"], nd if isinstance(nd, str) else json.dumps(nd, ensure_ascii=False), boi,
        )
    await db.execute(
        """
        INSERT INTO goi_ky_nang (ten, phien_ban, noi_dung, tao_boi)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (ten) DO UPDATE
            SET phien_ban = EXCLUDED.phien_ban, noi_dung = EXCLUDED.noi_dung, bat = TRUE, sua_luc = now()
        """,
        g.ten, g.phien_ban, json.dumps(g.tho, ensure_ascii=False), boi,
    )
    await _ghi_plugin(g, True)
    try:
        await _nap_tai_lieu(g)
    except Exception as exc:  # noqa: BLE001 — gói đã ghi; báo rõ thay vì im
        await db.execute("UPDATE goi_ky_nang SET bat = $1, sua_luc = now() WHERE ten = $2", False, g.ten)
        await db.execute("UPDATE ky_nang_cai_dat SET bat = $1 WHERE goi = $2", False, g.ten)
        await db.log_event("ky_nang.goi_tai_lieu_hong", actor=boi, ten=g.ten, loi=f"{type(exc).__name__}: {exc}"[:200])
        xoa_dem(); kho_ky_nang.xoa_dem()
        raise RuntimeError(f"Gói đã lưu nhưng nạp tài liệu hỏng ({type(exc).__name__}); gói đang TẮT. "
                           "Sửa rồi bật lại.") from exc
    await db.log_event("ky_nang.goi_cai", actor=boi, ten=g.ten, phien_ban=g.phien_ban,
                       so_cong_cu=len(g.cong_cu), so_tai_lieu=len(g.tai_lieu))
    xoa_dem(); kho_ky_nang.xoa_dem()
    return g


async def bat_tat(ten: str, bat: bool, *, boi: str) -> None:
    hien = await _doc_hien_hanh(ten)
    if hien is None:
        raise GoiKhongTonTai(ten)
    g = doc_goi(hien["noi_dung"] if isinstance(hien["noi_dung"], dict) else json.loads(hien["noi_dung"]))
    await db.execute("UPDATE goi_ky_nang SET bat = $1, sua_luc = now() WHERE ten = $2", bat, ten)
    await db.execute("UPDATE ky_nang_cai_dat SET bat = $1 WHERE goi = $2", bat, ten)
    if bat:
        await _nap_tai_lieu(g)
    else:
        await rag.xoa_nguon(_nguon(ten))
    await db.log_event("ky_nang.goi_bat_tat", actor=boi, ten=ten, bat=str(bat))
    xoa_dem(); kho_ky_nang.xoa_dem()


async def xoa(ten: str, *, boi: str) -> bool:
    if await _doc_hien_hanh(ten) is None:
        raise GoiKhongTonTai(ten)
    await db.execute("DELETE FROM ky_nang_cai_dat WHERE goi = $1", ten)
    await rag.xoa_nguon(_nguon(ten))
    await db.execute("DELETE FROM goi_ky_nang WHERE ten = $1", ten)
    await db.log_event("ky_nang.goi_xoa", actor=boi, ten=ten)
    xoa_dem(); kho_ky_nang.xoa_dem()
    return True


async def lich_su(ten: str) -> list[dict]:
    rows = await db.fetch(
        "SELECT id, phien_ban, thay_luc, thay_boi FROM goi_ky_nang_lich_su WHERE ten = $1 ORDER BY thay_luc DESC LIMIT 10", ten)
    return [dict(r) for r in rows]


async def khoi_phuc(ten: str, id_lich_su: int, *, boi: str) -> Goi:
    r = await db.fetchrow("SELECT noi_dung FROM goi_ky_nang_lich_su WHERE id = $1 AND ten = $2", id_lich_su, ten)
    if r is None:
        raise GoiKhongTonTai(f"{ten}#{id_lich_su}")
    nd = r["noi_dung"]
    return await cai(nd if isinstance(nd, dict) else json.loads(nd), boi=boi)


async def xuat(ten: str) -> dict | None:
    hien = await _doc_hien_hanh(ten)
    if hien is None:
        return None
    nd = hien["noi_dung"]
    return nd if isinstance(nd, dict) else json.loads(nd)


async def dem_goi_7_ngay() -> dict[str, dict]:
    """
    Số lần gọi và số lỗi mỗi công cụ trong 7 ngày, trừ lượt phòng thử.

    `events.detail` là JSONB ghi qua codec (db.log_event), nên bool thành
    JSON true/false và `detail->>'ok'` là chuỗi 'true'/'false'.
    """
    rows = await db.fetch(
        """
        SELECT detail->>'ten' AS ten, detail->>'goi' AS goi,
               count(*) AS so_lan,
               count(*) FILTER (WHERE (detail->>'ok') = 'false') AS so_loi
        FROM events
        WHERE kind = 'cong_cu.goi' AND created_at > now() - interval '7 days'
          AND coalesce(detail->>'thu_nghiem', 'false') <> 'true'
        GROUP BY 1, 2
        """
    )
    return {r["ten"]: {"so_lan": int(r["so_lan"]), "so_loi": int(r["so_loi"]), "goi": r["goi"]} for r in rows}


async def liet_ke() -> list[dict]:
    rows = await db.fetch("SELECT ten, phien_ban, bat, noi_dung, tao_boi, sua_luc FROM goi_ky_nang ORDER BY ten")
    dem = await dem_goi_7_ngay()
    ra = []
    for r in rows:
        nd = r["noi_dung"] if isinstance(r["noi_dung"], dict) else json.loads(r["noi_dung"])
        ten_cc = [c.get("ten") for c in nd.get("cong_cu") or []]
        ra.append({
            "ten": r["ten"], "phien_ban": r["phien_ban"], "bat": bool(r["bat"]),
            "mo_ta": nd.get("mo_ta", ""), "tu_khoa": nd.get("tu_khoa", []),
            "so_cong_cu": len(ten_cc), "so_tai_lieu": len(nd.get("tai_lieu") or []),
            "so_lan_7_ngay": sum(dem.get(t, {}).get("so_lan", 0) for t in ten_cc),
            "so_loi_7_ngay": sum(dem.get(t, {}).get("so_loi", 0) for t in ten_cc),
            "sua_luc": dict(r).get("sua_luc"),
        })
    return ra


async def _cac_goi_dang_bat() -> tuple[Goi, ...]:
    global _DEM
    if _DEM is not None and time.monotonic() - _DEM[0] < _DEM_GIAY:
        return _DEM[1]
    rows = await db.fetch("SELECT ten, noi_dung FROM goi_ky_nang WHERE bat")
    ra: list[Goi] = []
    for r in rows:
        # "WHERE bat" ở CSDL thật đã lọc rồi, cột "bat" thậm chí không nằm
        # trong SELECT — `.get("bat", True)` mặc định True nên không đổi gì
        # ở đó. Lọc lại ở đây là lưới thứ hai cho CSDL giả trong test (nó so
        # khớp ĐẦU câu SQL, không diễn giải WHERE) và cho bất cứ nơi nào sau
        # này gọi hàm với một danh sách chưa lọc.
        if not r.get("bat", True):
            continue
        nd = r["noi_dung"] if isinstance(r["noi_dung"], dict) else json.loads(r["noi_dung"])
        try:
            ra.append(doc_goi(nd))
        except LoiGoi:
            # Một gói hỏng trong CSDL không được làm chết lượt trả lời — bỏ
            # qua gói đó và nói ra, đừng im.
            _log.warning("gói kỹ năng %r trong CSDL không hợp lệ, bỏ qua", r["ten"])
    _DEM = (time.monotonic(), tuple(ra))
    return _DEM[1]


async def huong_dan_cho_luot(cau_hoi: str) -> list[tuple[str, str]]:
    """Hướng dẫn của các gói đang bật khớp câu hỏi; CSDL hỏng thì rỗng và cảnh báo."""
    try:
        cac_goi = await _cac_goi_dang_bat()
    except Exception as exc:  # noqa: BLE001 — agent phải trả lời được dù kho gói hỏng
        _log.warning("không đọc được gói kỹ năng (%s: %s) — lượt này không có hướng dẫn", type(exc).__name__, exc)
        return []
    return [(g.ten, g.huong_dan) for g in chon_goi(list(cac_goi), cau_hoi)]
