"""
Ba mức ỦY QUYỀN THỰC THI của AI — theo từng HÀNH ĐỘNG nghiệp vụ (mục 17).

HAI TẦNG, KHÔNG PHẢI MỘT
------------------------
    chế độ AI (toàn cục, `runtime.mode()`)   Tắt · Gợi ý · Tự động
    mức của từng hành động (bảng ai_uy_quyen) Không sử dụng · Có phê duyệt · Tự động

Ở chế độ GỢI Ý, mọi hành động thay đổi dữ liệu thành ĐỀ XUẤT chờ người
duyệt, bất kể mức của hành động — AI gợi ý thì không tự làm. Ở chế độ TỰ
ĐỘNG, mức của từng hành động mới quyết định. Hội thoại nhân viên bật "Duyệt
trước khi gửi" được tính như Gợi ý: lời AI còn phải chờ người duyệt mà hành
động thì đã tự chạy là hai nửa của cùng một lượt nói hai chuyện khác nhau.

VÌ SAO CHỐT NẰM Ở `tools.run_tool`, KHÔNG Ở PROMPT
-------------------------------------------------
Đo được 22.11.2026 trên CSDL đang chạy: chế độ chung là `assist` (Gợi ý),
và trong bảng `orders` có đơn `da_chot` — AI vẫn lên đơn thật ở chế độ được
gọi là "AI gợi ý, người quyết". Chế độ chỉ chặn GỬI TIN (xu_ly_tin_vao), còn
công cụ thì chạy trong `respond()`, trước khi tầng kênh biết chế độ. Dặn
model "đừng lên đơn ở chế độ gợi ý" là đúng loại ràng buộc trượt được. Nên
chốt đặt ở cửa thi hành công cụ — cửa DUY NHẤT mọi công cụ đi qua — và đọc
chế độ ở đó, không nhận nó làm tham số từ ai.

AI KHÔNG ĐỔI ĐƯỢC CHÍNH SÁCH: không công cụ nào ghi bảng `ai_uy_quyen`; chỉ
API `PUT /api/ai-uy-quyen` (quyền `agent.dieu_khien`) ghi. Có test canh.

HÀNH ĐỘNG LẠ = KHÔNG SỬ DỤNG (hỏng-đóng)
---------------------------------------
Chọn "Không sử dụng" (chuyển nhân viên) chứ không "Có phê duyệt" cho hành
động mã chưa biết: phê duyệt chỉ có nghĩa khi hệ thống có một đường THI HÀNH
kiểm lại được điều kiện nghiệp vụ lúc duyệt. Hành động lạ không có đường ấy,
nên "Có phê duyệt" sẽ là một nút Duyệt hoặc không làm được gì, hoặc chạy lại
nguyên tham số model đưa — đúng thứ "AI khẳng định hợp lệ mà không có căn
cứ" chủ dự án cấm. Chuyển người thì luôn an toàn.

LỊCH SỬ: mọi bước ghi sự kiện `ai.de_xuat.*` / `ai.hanh_dong.*` với
`ref_id` = hội thoại và `de_xuat_id` trong chi tiết — màn tra cứu kiểm toán
(mục 18) đọc từ đó.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from agent import db, runtime
from agent.config import settings

log = logging.getLogger("agent.uy_quyen")

MUC = ("khong_su_dung", "co_phe_duyet", "tu_dong")
NHAN_MUC = {
    "khong_su_dung": "Không sử dụng",
    "co_phe_duyet": "Có phê duyệt",
    "tu_dong": "Tự động",
}
# 0066 bổ sung trạng thái; giữ da_duyet cho tạo/hủy đơn và lịch sử.
TRANG_THAI = ("cho_duyet", "da_duyet", "dang_thuc_thi", "da_thuc_hien",
              "cho_xu_ly_thu_cong", "loi", "tu_choi", "het_han")
NHAN_TRANG_THAI = {
    "cho_duyet": "Chờ duyệt",
    "da_duyet": "Đã duyệt — đang thực hiện",
    "dang_thuc_thi": "Đang kiểm tra và xử lý yêu cầu",
    "cho_xu_ly_thu_cong": "Chờ xử lý thủ công — chưa sửa đơn",
    "da_thuc_hien": "Đã thực hiện",
    "loi": "Duyệt nhưng không thực hiện được",
    "tu_choi": "Đã từ chối",
    "het_han": "Hết hạn",
}
CHE_DO = ("goi_y", "tu_dong")
MUC_HANH_DONG_LA = "khong_su_dung"

# Hạn chờ duyệt mặc định. Đơn vị GIỜ: đề xuất là việc trong ca, không phải
# việc trong tuần — để lâu thì tồn kho, giá, ý khách đều đã khác.
KHOA_HAN = "ai_de_xuat_han_gio"
HAN_MAC_DINH_GIO = 24
HAN_TOI_DA_GIO = 168


@dataclass(frozen=True)
class HanhDong:
    ma: str
    ten: str
    mo_ta: str
    # Hệ thống có đường THI HÀNH và KIỂM LẠI lúc thi hành không. False =
    # "Chưa hỗ trợ — chuyển nhân viên": hiện trong danh sách cho trung thực,
    # nhưng không đặt mức được.
    ho_tro: bool
    mac_dinh: str
    cau_hinh_duoc: bool = True
    # Quyền NGHIỆP VỤ người duyệt phải có thêm, ngoài `ai.duyet`: duyệt
    # không được là đường vòng để làm qua AI việc mình không được làm tay.
    quyen_thi_hanh: str | None = None
    co_nguong: bool = False
    ghi_chu: str = ""


DANH_MUC: dict[str, HanhDong] = {
    "tao_don": HanhDong(
        "tao_don", "Tạo đơn hàng",
        "Lên đơn từ thông tin khách đã xác nhận: giá lấy từ danh mục, tồn kho "
        "đọc sống, địa chỉ đã kiểm.",
        ho_tro=True, mac_dinh="tu_dong", quyen_thi_hanh="don.sua", co_nguong=True,
        ghi_chu="Ở mức Tự động, đơn từ ngưỡng giá trị trở lên vẫn chờ duyệt "
                "(đơn nằm ở trạng thái Chờ duyệt, đã giữ hàng)."),
    "huy_don": HanhDong(
        "huy_don", "Huỷ đơn hàng",
        "Huỷ đơn khách xin huỷ và trả hàng về kho. Không huỷ được đơn đã giao.",
        ho_tro=True, mac_dinh="co_phe_duyet", quyen_thi_hanh="don.sua",
        ghi_chu="Ở mức Không sử dụng, AI chỉ ghi nhận yêu cầu lên đơn rồi chuyển "
                "nhân viên. Huỷ ở đây KHÔNG huỷ bên ERP hay hãng vận chuyển — "
                "kết quả thi hành nói rõ phần cần huỷ tay."),
    "chuyen_nhan_vien": HanhDong(
        "chuyen_nhan_vien", "Chuyển nhân viên theo quy tắc",
        "Chuyển hội thoại cho người khi vượt thẩm quyền, thiếu căn cứ, hoặc "
        "khách yêu cầu.",
        ho_tro=True, mac_dinh="tu_dong", cau_hinh_duoc=False,
        ghi_chu="Luôn bật: bốn trong sáu lớp lưới an toàn kết thúc bằng chuyển "
                "người. Tắt nó là để các lớp ấy phán đúng rồi không còn chỗ giao việc."),
    "sua_don": HanhDong(
        "sua_don", "Sửa đơn đã xác nhận",
        "Đổi sản phẩm, số lượng, giá trị hay thông tin giao hàng quan trọng.",
        ho_tro=False, mac_dinh="co_phe_duyet", quyen_thi_hanh="don.sua",
        ghi_chu="AI chỉ đề xuất sửa số lượng để nhân viên duyệt. Chưa có API sửa "
                "Sales Order tương thích; sau duyệt vẫn cần xử lý thủ công."),
    "hoan_tien": HanhDong(
        "hoan_tien", "Hoàn tiền", "Trả lại tiền khách đã thanh toán.",
        ho_tro=False, mac_dinh="co_phe_duyet",
        ghi_chu="Hệ thống không đọc/ghi được tài khoản ngân hàng — chuyển nhân viên."),
    "giam_gia": HanhDong(
        "giam_gia", "Giảm giá ngoài chính sách", "Giá thấp hơn giá trong danh mục.",
        ho_tro=False, mac_dinh="co_phe_duyet",
        ghi_chu="Giá lên đơn LUÔN lấy từ danh mục — AI không đặt giá được; chuyển nhân viên."),
    "doi_tra": HanhDong(
        "doi_tra", "Đổi / trả hàng ngoài chính sách", "Duyệt đổi mẫu hoặc nhận trả hàng.",
        ho_tro=False, mac_dinh="co_phe_duyet",
        ghi_chu="AI chỉ ghi nhận yêu cầu lên đơn (xin_doi_tra) rồi chuyển nhân viên."),
    "tao_van_don": HanhDong(
        "tao_van_don", "Tạo vận đơn", "Gửi đơn sang hãng vận chuyển.",
        ho_tro=False, mac_dinh="tu_dong",
        ghi_chu="AI chưa có công cụ này — nhân viên tạo ở màn Đơn hàng."),
    "tao_cong_viec": HanhDong(
        "tao_cong_viec", "Tạo công việc", "Giao một việc cho nhân viên.",
        ho_tro=False, mac_dinh="tu_dong",
        ghi_chu="AI không tự tạo việc rời; việc xử lý đơn chỉ sinh kèm khi AI "
                "chuyển một yêu cầu huỷ cho nhân viên."),
}

# Công cụ AI -> hành động nó gây ra. Công cụ nào thay đổi dữ liệu nghiệp vụ
# mà KHÔNG có ở đây và cũng không ở hai tập dưới thì bị coi là hành động lạ.
CONG_CU_HANH_DONG: dict[str, str] = {
    "tao_don_hang": "tao_don",
    "xin_huy_don": "huy_don",
}
# Chỉ đọc. Không cần dòng chính sách nào (phiếu việc 17.5).
CONG_CU_DOC = frozenset({
    "tim_kien_thuc", "tra_cuu_san_pham", "goi_y_san_pham", "gui_anh_san_pham",
    "tra_cuu_don_hang", "tra_cuu_van_chuyen",
})
# Ghi nhận yêu cầu của khách rồi CHUYỂN NGƯỜI: là lối an toàn, chạy ở mọi
# chế độ. Chặn nó ở chế độ Gợi ý là chặn đúng đường đưa khách tới người.
CONG_CU_CHUYEN_NGUOI = frozenset({"chuyen_nhan_vien", "xin_doi_tra"})
# Loại plugin chỉ đọc (agent/ky_nang/ban_mo_ta.py). `mcp` xét riêng theo cờ ghi.
LOAI_PLUGIN_DOC = frozenset({"tra_tai_lieu", "tra_bang", "goi_api_doc"})
LOAI_PLUGIN_CHUYEN_NGUOI = frozenset({"chuyen_chuyen_biet"})


class LoiDeXuat(Exception):
    """Không làm được việc với đề xuất. `ma` là mã HTTP tầng API trả."""

    def __init__(self, ma: int, thong_diep: str) -> None:
        super().__init__(thong_diep)
        self.ma = ma
        self.thong_diep = thong_diep


# ---------------------------------------------------------------------------
#  Chính sách
# ---------------------------------------------------------------------------

# Đệm 30 giây: chốt chạy ở MỌI lời gọi công cụ ghi, không được hỏi CSDL mỗi
# lần; nhưng tiến trình nền và tiến trình API là hai tiến trình, nên không
# dựa vào xoá đệm lúc ghi được — 30 giây là độ trễ tối đa để đổi có hiệu lực.
_DEM_GIAY = 30.0
_dem: tuple[float, dict[str, dict]] | None = None


def xoa_dem() -> None:
    global _dem
    _dem = None


async def doc_chinh_sach() -> dict[str, dict]:
    """Những dòng quản trị đã ĐỔI. Không đọc được CSDL thì {} và kêu."""
    global _dem
    bay_gio = time.monotonic()
    if _dem is not None and bay_gio - _dem[0] < _DEM_GIAY:
        return _dem[1]
    try:
        rows = await db.fetch(
            "SELECT hanh_dong, muc, nguong_vnd, sua_boi, sua_luc FROM ai_uy_quyen")
    except Exception as exc:  # noqa: BLE001
        # Giữ đệm cũ nếu có: một lần CSDL chập chờn không được lặng lẽ đưa
        # mọi hành động về mặc định — mặc định của `tao_don` là Tự động,
        # tức đúng lúc hỏng lại nới ra. Không có đệm (máy mới, test không
        # CSDL) thì dùng mặc định của mã và KÊU.
        log.warning("Không đọc được chính sách ủy quyền AI: %s: %s",
                    type(exc).__name__, exc)
        return _dem[1] if _dem is not None else {}
    bang = {r["hanh_dong"]: dict(r) for r in rows}
    _dem = (bay_gio, bang)
    return bang


def muc_hop_le(hd: HanhDong, muc: str | None) -> str:
    """Mức hiệu lực của một hành động trong danh mục, từ giá trị đã lưu."""
    if not hd.ho_tro:
        return "khong_su_dung"
    if not hd.cau_hinh_duoc:
        return hd.mac_dinh
    return muc if muc in MUC else hd.mac_dinh


async def muc_cua(ma: str) -> str:
    """Mức hiệu lực. Hành động lạ = `khong_su_dung` (hỏng-đóng)."""
    hd = DANH_MUC.get(ma)
    if hd is None:
        return MUC_HANH_DONG_LA
    dong = (await doc_chinh_sach()).get(ma)
    return muc_hop_le(hd, dong.get("muc") if dong else None)


async def nguong_tao_don() -> int:
    """Ngưỡng giá trị đơn phải duyệt ở mức Tự động. Không đặt = `.env`."""
    dong = (await doc_chinh_sach()).get("tao_don")
    if dong and dong.get("nguong_vnd") is not None:
        return int(dong["nguong_vnd"])
    return int(settings.nguong_tu_chot_vnd)


async def han_gio() -> int:
    try:
        dong = await db.fetchrow(
            "SELECT gia_tri FROM cau_hinh_agent WHERE khoa = $1", KHOA_HAN)
    except Exception:  # noqa: BLE001 — bảng chưa có: dùng mặc định
        return HAN_MAC_DINH_GIO
    gt = dong["gia_tri"] if dong else None
    try:
        gio = int(str(gt).strip('"')) if gt is not None else HAN_MAC_DINH_GIO
    except ValueError:
        return HAN_MAC_DINH_GIO
    return gio if 1 <= gio <= HAN_TOI_DA_GIO else HAN_MAC_DINH_GIO


async def mo_ta_chinh_sach() -> dict[str, Any]:
    """Cho màn Cấu hình AI Agent → Chính sách & Ủy quyền."""
    bang = await doc_chinh_sach()
    ds = []
    for hd in DANH_MUC.values():
        dong = bang.get(hd.ma) or {}
        muc = muc_hop_le(hd, dong.get("muc"))
        ds.append({
            "ma": hd.ma, "ten": hd.ten, "mo_ta": hd.mo_ta, "ghi_chu": hd.ghi_chu,
            "ho_tro": hd.ho_tro, "cau_hinh_duoc": hd.ho_tro and hd.cau_hinh_duoc,
            "ho_tro_de_xuat": hd.ho_tro or hd.ma == "sua_don",
            "muc": muc, "nhan_muc": NHAN_MUC[muc],
            "mac_dinh": hd.mac_dinh if hd.ho_tro else "khong_su_dung",
            "da_doi": bool(dong) and hd.ho_tro and hd.cau_hinh_duoc,
            "quyen_thi_hanh": hd.quyen_thi_hanh,
            "co_nguong": hd.co_nguong,
            "nguong_vnd": (await nguong_tao_don()) if hd.co_nguong else None,
            "nguong_mac_dinh": int(settings.nguong_tu_chot_vnd) if hd.co_nguong else None,
            "sua_boi": dong.get("sua_boi"),
            "sua_luc": dong["sua_luc"].isoformat() if dong.get("sua_luc") else None,
        })
    return {
        "hanh_dong": ds,
        "muc": [{"ma": m, "nhan": NHAN_MUC[m]} for m in MUC],
        "che_do_chung": runtime.mode(),
        "han_gio": await han_gio(),
        "han_toi_da_gio": HAN_TOI_DA_GIO,
        "hanh_dong_la": NHAN_MUC[MUC_HANH_DONG_LA],
    }


async def luu_chinh_sach(ma: str, muc: str, *, nguong_vnd: int | None = None,
                         boi: str = "staff") -> dict:
    """Ghi mức của MỘT hành động. Ném ValueError khi không hợp lệ."""
    hd = DANH_MUC.get(ma)
    if hd is None:
        raise ValueError(f"Không có hành động {ma!r} trong danh mục.")
    if not hd.ho_tro:
        raise ValueError(f"«{hd.ten}» chưa được hệ thống hỗ trợ — AI luôn chuyển nhân viên.")
    if not hd.cau_hinh_duoc:
        raise ValueError(f"«{hd.ten}» không đổi được: {hd.ghi_chu}")
    if muc not in MUC:
        raise ValueError(f"Mức không hợp lệ: {muc!r}.")
    if nguong_vnd is not None and not hd.co_nguong:
        raise ValueError(f"«{hd.ten}» không có ngưỡng giá trị.")
    if nguong_vnd is not None and nguong_vnd < 0:
        raise ValueError("Ngưỡng không được âm.")
    truoc = (await doc_chinh_sach()).get(ma) or {}
    await db.execute(
        """
        INSERT INTO ai_uy_quyen (hanh_dong, muc, nguong_vnd, sua_boi)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (hanh_dong) DO UPDATE
            SET muc = EXCLUDED.muc, nguong_vnd = EXCLUDED.nguong_vnd,
                sua_boi = EXCLUDED.sua_boi, sua_luc = now()
        """, ma, muc, nguong_vnd, boi[:100])
    xoa_dem()
    await db.log_event(
        "ai.uy_quyen.sua", actor=boi, hanh_dong=ma,
        muc_truoc=truoc.get("muc") or muc_hop_le(hd, None), muc_sau=muc,
        nguong_truoc=truoc.get("nguong_vnd"), nguong_sau=nguong_vnd)
    return {"ma": ma, "muc": muc, "nguong_vnd": nguong_vnd}


async def luu_han_gio(gio: int, *, boi: str = "staff") -> int:
    if not 1 <= int(gio) <= HAN_TOI_DA_GIO:
        raise ValueError(f"Hạn chờ duyệt phải từ 1 tới {HAN_TOI_DA_GIO} giờ.")
    await db.execute(
        """
        INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi) VALUES ($1, $2::jsonb, $3)
        ON CONFLICT (khoa) DO UPDATE SET gia_tri = EXCLUDED.gia_tri,
            sua_boi = EXCLUDED.sua_boi, sua_luc = now()
        """, KHOA_HAN, int(gio), boi[:100])
    await db.log_event("ai.uy_quyen.sua_han", actor=boi, han_gio=int(gio))
    return int(gio)


# ---------------------------------------------------------------------------
#  Chốt ở cửa thi hành công cụ
# ---------------------------------------------------------------------------

async def che_do_hieu_luc(conversation_id: Any) -> tuple[str, str]:
    """
    (`goi_y` | `tu_dong`, lý do). Đọc tại chỗ, không nhận làm tham số: nơi
    gọi quên truyền thì không được thành "tự động".
    """
    if runtime.mode() != "auto":
        return "goi_y", "Chế độ AI đang là Gợi ý — AI không tự thực hiện hành động thay đổi dữ liệu"
    if conversation_id is None:
        return "tu_dong", ""
    try:
        dong = await db.fetchrow(
            "SELECT duyet_truoc_khi_gui FROM conversations WHERE id = $1", conversation_id)
    except Exception:  # noqa: BLE001
        # Không biết cờ riêng của hội thoại thì xử lý như Gợi ý: sai về phía
        # hỏi người, không sai về phía tự làm.
        return "goi_y", "Không đọc được cờ duyệt riêng của hội thoại — xử lý như Gợi ý"
    if dong and dong.get("duyet_truoc_khi_gui"):
        return "goi_y", "Hội thoại này bật «Duyệt trước khi gửi» — xử lý như Gợi ý"
    return "tu_dong", ""


async def phan_loai_cong_cu(ten: str) -> str:
    if ten == "de_xuat_sua_don":
        return "de_xuat_thu_cong"
    """`doc` | `chuyen_nguoi` | `hanh_dong` | `mcp_ghi` | `la`."""
    if ten in CONG_CU_DOC:
        return "doc"
    if ten in CONG_CU_CHUYEN_NGUOI:
        return "chuyen_nguoi"
    if ten in CONG_CU_HANH_DONG:
        return "hanh_dong"
    from agent.ky_nang import kho_ky_nang

    bm = await kho_ky_nang.tim_plugin(ten)
    if bm is not None:
        if bm.loai in LOAI_PLUGIN_DOC:
            return "doc"
        if bm.loai in LOAI_PLUGIN_CHUYEN_NGUOI:
            return "chuyen_nguoi"
        if bm.loai == "mcp":
            return "mcp_ghi" if bm.cau_hinh.get("ghi") else "doc"
    return "la"


@dataclass(frozen=True)
class QuyetDinh:
    hanh_dong: str
    che_do: str          # goi_y | tu_dong
    muc: str             # mức của hành động theo chính sách
    ly_do_che_do: str = ""

    @property
    def can_duyet(self) -> bool:
        return self.che_do == "goi_y" or self.muc == "co_phe_duyet"

    @property
    def bi_cam(self) -> bool:
        return self.muc == "khong_su_dung"

    def ly_do_duyet(self) -> str:
        if self.che_do == "goi_y":
            return self.ly_do_che_do
        ten = DANH_MUC[self.hanh_dong].ten if self.hanh_dong in DANH_MUC else self.hanh_dong
        return f"Chính sách: «{ten}» ở mức Có phê duyệt"


async def quyet_dinh(hanh_dong: str, conversation_id: Any) -> QuyetDinh:
    che_do, ly_do = await che_do_hieu_luc(conversation_id)
    return QuyetDinh(hanh_dong, che_do, await muc_cua(hanh_dong), ly_do)


async def chan_chuyen_nguoi(ten_cong_cu: str, ly_do: str, conversation_id: Any, *,
                            hanh_dong: str | None = None,
                            muc_uy_quyen: str | None = None) -> dict:
    """Kết quả công cụ khi chính sách KHÔNG cho AI làm — chuyển người thật."""
    cid = _uuid(conversation_id)
    await db.log_event("ai.hanh_dong.chan", actor="agent", ref_id=cid,
                       cong_cu=ten_cong_cu, hanh_dong=hanh_dong, muc_uy_quyen=muc_uy_quyen,
                       conversation_id=str(cid) if cid else None, ly_do=ly_do[:300])
    return {
        "bi_chan": True,
        "ly_do": ly_do,
        "can_chuyen_nhan_vien": True,
        "ghi_chu": (
            f"{ly_do}. KHÔNG tự làm việc này và KHÔNG nói là đã làm. Nói với "
            "khách là đã ghi nhận và nhân viên sẽ hỗ trợ tiếp — hội thoại đã "
            "được chuyển cho người."
        ),
    }


# ---------------------------------------------------------------------------
#  Đề xuất và vòng đời
# ---------------------------------------------------------------------------

def _uuid(x: Any) -> UUID | None:
    if isinstance(x, UUID):
        return x
    try:
        return UUID(str(x)) if x else None
    except (TypeError, ValueError):
        return None


async def _su_kien(kind: str, dong: Any, *, actor: str = "system", **them: Any) -> None:
    """
    MỘT khuôn cho mọi sự kiện vòng đời đề xuất — màn tra cứu kiểm toán (mục
    18) đọc đúng các khoá này: `ref_id` = hội thoại; chi tiết luôn có
    `de_xuat_id`, `hanh_dong`, `muc_uy_quyen`, `conversation_id`.
    """
    await db.log_event(
        kind, actor=actor, ref_id=dong["conversation_id"],
        de_xuat_id=str(dong["id"]), hanh_dong=dong["hanh_dong"],
        muc_uy_quyen=dong.get("muc_uy_quyen"),
        conversation_id=str(dong["conversation_id"]), **them)


async def tao_de_xuat(
    *, conversation_id: Any, quyet: QuyetDinh, ly_do_can_duyet: str,
    tham_so: dict, de_xuat: dict, can_cu: dict, khoa_trung: str,
    order_id: Any = None,
) -> tuple[UUID, bool]:
    """
    Ghi một yêu cầu phê duyệt. Trả (id, mới?) — trùng một đề xuất đang mở
    cho cùng việc thì trả id cũ, không đẻ thẻ thứ hai: khách nhắn "huỷ đơn"
    ba lần là MỘT việc cần duyệt.
    """
    cid = _uuid(conversation_id)
    if cid is None:
        raise ValueError("Đề xuất phải thuộc một hội thoại (phiếu việc 17.14).")
    hd = DANH_MUC.get(quyet.hanh_dong)
    chi_de_xuat = (quyet.hanh_dong == "sua_don" and quyet.muc == "co_phe_duyet"
                  and quyet.che_do == "goi_y")
    if hd is None or (not hd.ho_tro and not chi_de_xuat):
        # Ngoại lệ sửa đơn chỉ duyệt yêu cầu xử lý thủ công, không thi hành ERP.
        raise ValueError(f"Hành động {quyet.hanh_dong!r} không có đường thi hành.")
    gio = await han_gio()
    dong = await db.fetchrow(
        """
        INSERT INTO ai_de_xuat (conversation_id, hanh_dong, che_do_ai, muc_uy_quyen,
            ly_do_can_duyet, order_id, tham_so, de_xuat, can_cu, khoa_trung, het_han_luc)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now() + $11::interval)
        ON CONFLICT (khoa_trung) WHERE trang_thai IN
            ('cho_duyet', 'da_duyet', 'dang_thuc_thi', 'cho_xu_ly_thu_cong')
        DO NOTHING
        RETURNING id, conversation_id, hanh_dong, muc_uy_quyen
        """,
        cid, quyet.hanh_dong, quyet.che_do, quyet.muc, ly_do_can_duyet[:500],
        _uuid(order_id), tham_so, de_xuat, can_cu, khoa_trung[:300], timedelta(hours=gio),
    )
    if dong is None:
        cu = await db.fetchrow(
            "SELECT id, conversation_id, hanh_dong, muc_uy_quyen FROM ai_de_xuat WHERE khoa_trung = $1 "
            "AND trang_thai IN ('cho_duyet', 'da_duyet', 'dang_thuc_thi', 'cho_xu_ly_thu_cong')",
            khoa_trung[:300])
        if cu is None:   # vừa được xử lý giữa hai câu — thử lại một lần là đủ
            return await tao_de_xuat(
                conversation_id=cid, quyet=quyet, ly_do_can_duyet=ly_do_can_duyet,
                tham_so=tham_so, de_xuat=de_xuat, can_cu=can_cu,
                khoa_trung=khoa_trung, order_id=order_id)
        await _su_kien("ai.de_xuat.trung", cu, actor="agent")
        return cu["id"], False
    await _su_kien(
        "ai.de_xuat.tao", dong, actor="agent", che_do_ai=quyet.che_do,
        ly_do=ly_do_can_duyet[:300], order_id=str(order_id) if order_id else None,
        het_han_gio=gio, de_xuat=de_xuat, can_cu=can_cu)
    from agent.core import thong_bao_noi_bo

    await thong_bao_noi_bo.bao_can_duyet_de_xuat(
        cid, dong["id"], tieu_de=str(de_xuat.get("tieu_de") or hd.ten),
        quyen_thi_hanh=hd.quyen_thi_hanh)
    return dong["id"], True


async def het_han_qua_han(conversation_id: Any = None, *, chi_id: Any = None) -> int:
    """Đổi các đề xuất quá hạn sang `het_han` (lười: gọi lúc đọc/duyệt)."""
    rows = await db.fetch(
        """
        UPDATE ai_de_xuat SET trang_thai = 'het_han', cap_nhat_luc = now()
        WHERE trang_thai = 'cho_duyet' AND het_han_luc <= now()
          AND ($1::uuid IS NULL OR conversation_id = $1)
          AND ($2::uuid IS NULL OR id = $2)
        RETURNING id, conversation_id, hanh_dong, muc_uy_quyen
        """, _uuid(conversation_id), _uuid(chi_id))
    for r in rows:
        await _su_kien("ai.de_xuat.het_han", r)
    return len(rows)


async def nhan_duyet(de_xuat_id: UUID, nguoi: dict) -> dict:
    """
    `cho_duyet` -> `da_duyet`, trong MỘT giao dịch có khoá dòng.

    Đây là chốt chống thi hành hai lần: hai người bấm Duyệt cùng lúc thì
    người thứ hai chờ khoá, rồi thấy trạng thái không còn `cho_duyet`.
    """
    nguoi_id = _uuid(nguoi.get("id"))
    # Quá hạn: ghi `het_han` NGOÀI giao dịch dưới. Ghi bên trong rồi ném là
    # giao dịch cuộn lại — đề xuất nằm `cho_duyet` mãi dù đã quá hạn (bắt
    # được bằng test trên Postgres thật, giả lập `db` thì không thấy).
    if await het_han_qua_han(None, chi_id=de_xuat_id):
        raise LoiDeXuat(409, "Đề xuất đã hết hạn — không thi hành.")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            dong = await conn.fetchrow(
                "SELECT * FROM ai_de_xuat WHERE id = $1 FOR UPDATE", de_xuat_id)
            if dong is None:
                raise LoiDeXuat(404, "Không có đề xuất này")
            if dong["trang_thai"] == "cho_duyet" and dong["het_han_luc"] <= await conn.fetchval("SELECT now()"):
                # Vừa quá hạn trong tích tắc giữa hai câu: từ chối, lần đọc
                # kế tiếp (`liet_ke`) sẽ đổi trạng thái.
                raise LoiDeXuat(409, "Đề xuất đã hết hạn — không thi hành.")
            if dong["trang_thai"] != "cho_duyet":
                raise LoiDeXuat(409, "Đề xuất đã được xử lý: "
                                + NHAN_TRANG_THAI.get(dong["trang_thai"], dong["trang_thai"]))
            # Chính sách đổi SAU khi đề xuất ra đời: quản trị đã nói AI không
            # được làm việc này nữa, thì đề xuất cũ cũng không chạy.
            # Sửa đơn là duyệt yêu cầu thủ công; ho_tro=False vẫn khóa thực thi.
            if (dong["hanh_dong"] != "sua_don"
                    and await muc_cua(dong["hanh_dong"]) == "khong_su_dung"):
                raise LoiDeXuat(409, "Chính sách hiện tại không cho AI làm việc này "
                                     "(Không sử dụng) — đề xuất không còn hiệu lực.")
            dong = await conn.fetchrow(
                "UPDATE ai_de_xuat SET trang_thai=CASE WHEN hanh_dong='sua_don' "
                "THEN 'dang_thuc_thi' ELSE 'da_duyet' END, duyet_boi=$2, duyet_luc=now(), "
                "cap_nhat_luc=now() WHERE id=$1 RETURNING *", de_xuat_id, nguoi_id)
    await _su_kien("ai.de_xuat.duyet", dong, actor=str(nguoi.get("ten_dang_nhap") or "?"),
                   nguoi_duyet_id=str(nguoi_id) if nguoi_id else None)
    return dict(dong)


async def ghi_ket_qua(de_xuat_id: UUID, *, ok: bool, ket_qua: dict | None,
                      loi: str | None, actor: str) -> dict:
    """Finalize a claimed proposal; manual review is never execution success."""
    thu_cong = not ok and bool((ket_qua or {}).get("can_xu_ly_thu_cong"))
    trang_thai = "da_thuc_hien" if ok else "cho_xu_ly_thu_cong" if thu_cong else "loi"
    dong = await db.fetchrow(
        """
        UPDATE ai_de_xuat SET trang_thai = $2,
               thuc_hien_luc = CASE WHEN $2 = 'cho_xu_ly_thu_cong' THEN NULL ELSE now() END,
               ket_qua = $3,
               loi = $4, cap_nhat_luc = now()
        WHERE id = $1 AND trang_thai IN ('da_duyet', 'dang_thuc_thi') RETURNING *
        """, de_xuat_id, trang_thai, ket_qua, (loi or None))
    if dong is None:
        raise LoiDeXuat(409, "Đề xuất không ở trạng thái Đã duyệt.")
    su_kien = "thuc_hien" if ok else "cho_xu_ly_thu_cong" if thu_cong else "loi"
    await _su_kien("ai.de_xuat." + su_kien, dong, actor=actor,
                   ket_qua=ket_qua, loi=(loi or None))
    return dict(dong)


async def hoan_tat_thu_cong(
    de_xuat_id: UUID,
    *,
    nguoi: dict,
    ket_qua: dict,
    ghi_chu: str,
) -> dict:
    """Chốt đề xuất `cho_xu_ly_thu_cong` -> `da_thuc_hien` với khoá dòng chống xác nhận trùng."""
    nguoi_id = _uuid(nguoi.get("id"))
    actor = str(nguoi.get("ten_dang_nhap") or "?")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            hien = await conn.fetchrow(
                "SELECT * FROM ai_de_xuat WHERE id = $1 FOR UPDATE", de_xuat_id)
            if hien is None:
                raise LoiDeXuat(404, "Không có đề xuất này")
            if hien["hanh_dong"] != "sua_don":
                raise LoiDeXuat(409, "Chỉ đề xuất sửa đơn mới dùng xác nhận xử lý thủ công.")
            if hien["trang_thai"] != "cho_xu_ly_thu_cong":
                raise LoiDeXuat(
                    409,
                    "Đề xuất không ở trạng thái chờ xử lý thủ công: "
                    + NHAN_TRANG_THAI.get(hien["trang_thai"], hien["trang_thai"]),
                )
            dong = await conn.fetchrow(
                """
                UPDATE ai_de_xuat
                   SET trang_thai = 'da_thuc_hien',
                       thuc_hien_luc = now(),
                       ket_qua = $2,
                       loi = NULL,
                       cap_nhat_luc = now()
                 WHERE id = $1 AND trang_thai = 'cho_xu_ly_thu_cong'
                 RETURNING *
                """,
                de_xuat_id,
                ket_qua,
            )
    await _su_kien(
        "ai.de_xuat.xu_ly_thu_cong",
        dong,
        actor=actor,
        nguoi_xu_ly_id=str(nguoi_id) if nguoi_id else None,
        qua="xu_ly_thu_cong",
        order_id=str(dong["order_id"]) if dong.get("order_id") else None,
        ket_qua=ket_qua,
        ghi_chu=ghi_chu[:500],
    )
    return dict(dong)


async def tu_choi(de_xuat_id: UUID, nguoi: dict, ly_do: str = "") -> dict:
    dong = await db.fetchrow(
        """
        UPDATE ai_de_xuat SET trang_thai = 'tu_choi', tu_choi_boi = $2, tu_choi_luc = now(),
               ly_do_tu_choi = $3, cap_nhat_luc = now()
        WHERE id = $1 AND trang_thai = 'cho_duyet' RETURNING *
        """, de_xuat_id, _uuid(nguoi.get("id")), (ly_do or "").strip()[:500] or None)
    if dong is None:
        hien = await db.fetchrow("SELECT trang_thai FROM ai_de_xuat WHERE id = $1", de_xuat_id)
        if hien is None:
            raise LoiDeXuat(404, "Không có đề xuất này")
        raise LoiDeXuat(409, "Đề xuất đã được xử lý: "
                        + NHAN_TRANG_THAI.get(hien["trang_thai"], hien["trang_thai"]))
    await _su_kien("ai.de_xuat.tu_choi", dong, actor=str(nguoi.get("ten_dang_nhap") or "?"),
                   nguoi_tu_choi_id=str(_uuid(nguoi.get("id")) or "") or None,
                   ly_do=(ly_do or "")[:300])
    return dict(dong)


async def dong_theo_don(order_id: Any, su_kien: str, *, boi: str) -> int:
    """
    Đơn vừa được duyệt/huỷ ở màn Đơn hàng (không qua thẻ): đóng đề xuất
    ĐANG CHỜ của chính đơn ấy, kẻo thẻ còn nút Duyệt cho một việc đã xong —
    bấm vào chỉ ra 409, và lịch sử nói "chờ duyệt" mãi.

      duyet  -> đề xuất `tao_don` của đơn: đã thực hiện (qua màn Đơn hàng)
      huy    -> đề xuất `huy_don` của đơn: đã thực hiện; `tao_don`: từ chối
    """
    if su_kien not in ("duyet", "huy"):
        raise ValueError(su_kien)
    try:
        return await _dong_theo_don(order_id, su_kien, boi=boi)
    except Exception as exc:  # noqa: BLE001
        # Đơn ĐÃ duyệt/huỷ xong rồi; ném ở đây là trả 500 cho một thao tác
        # thành công. Nhưng không im: thẻ sẽ còn nút Duyệt (bấm ra 409), nên
        # phải để lại dấu cho người tra.
        log.error("Không đóng được đề xuất AI theo đơn %s: %s: %s",
                  order_id, type(exc).__name__, exc)
        await db.log_event("ai.de_xuat.loi_dong_theo_don", order_id=str(order_id),
                           su_kien=su_kien, ly_do=f"{type(exc).__name__}: {exc}"[:200])
        return 0


async def _dong_theo_don(order_id: Any, su_kien: str, *, boi: str) -> int:
    oid = _uuid(order_id)
    if oid is None:
        return 0
    if su_kien == "duyet":
        sql = ("UPDATE ai_de_xuat SET trang_thai='da_thuc_hien', thuc_hien_luc=now(), "
               "ket_qua=$2, cap_nhat_luc=now() WHERE order_id=$1 AND hanh_dong='tao_don' "
               "AND trang_thai='cho_duyet' RETURNING id, conversation_id, hanh_dong, "
               "muc_uy_quyen, trang_thai")
        rows = await db.fetch(sql, oid, {"qua": "man_don_hang", "boi": boi, "viec": "duyệt đơn"})
    elif su_kien == "huy":
        rows = await db.fetch(
            "UPDATE ai_de_xuat SET trang_thai = CASE WHEN hanh_dong='huy_don' "
            "THEN 'da_thuc_hien' ELSE 'tu_choi' END, "
            "thuc_hien_luc = CASE WHEN hanh_dong='huy_don' THEN now() END, "
            "ly_do_tu_choi = CASE WHEN hanh_dong='huy_don' THEN NULL "
            "ELSE 'Đơn đã bị huỷ ở màn Đơn hàng' END, "
            "ket_qua=$2, cap_nhat_luc=now() WHERE order_id=$1 AND trang_thai='cho_duyet' "
            "RETURNING id, conversation_id, hanh_dong, muc_uy_quyen, trang_thai",
            oid, {"qua": "man_don_hang", "boi": boi, "viec": "huỷ đơn"})
    else:
        raise ValueError(su_kien)
    for r in rows:
        # Cùng hai loại sự kiện như đi qua thẻ — chỉ khác `qua` — để lịch sử
        # đề xuất không có một trạng thái cuối mà không có sự kiện nào ghi.
        await _su_kien("ai.de_xuat.thuc_hien" if r["trang_thai"] == "da_thuc_hien"
                       else "ai.de_xuat.tu_choi", r, actor=boi, qua="man_don_hang",
                       su_kien_don=su_kien)
    return len(rows)


async def gan_tin_nhan(conversation_id: Any, de_xuat_ids: list) -> None:
    """Gắn tin AI vừa lưu của lượt này vào các đề xuất nó sinh ra (Xem căn cứ)."""
    ids = [u for u in (_uuid(x) for x in de_xuat_ids) if u is not None]
    if not ids:
        return
    try:
        await db.execute(
            """
            UPDATE ai_de_xuat SET message_id = (
                SELECT id FROM messages WHERE conversation_id = $1 AND role = 'agent'
                ORDER BY created_at DESC LIMIT 1)
            WHERE id = ANY($2::uuid[]) AND message_id IS NULL
            """, _uuid(conversation_id), ids)
    except Exception as exc:  # noqa: BLE001 — liên kết hỏng không chặn câu trả lời
        await db.log_event("ai.de_xuat.loi_gan_tin", ref_id=_uuid(conversation_id),
                           ly_do=f"{type(exc).__name__}: {exc}"[:200])


def _iso(x: Any) -> str | None:
    return x.isoformat() if x is not None else None


async def liet_ke(conversation_id: UUID, *, nguoi: dict | None = None) -> list[dict]:
    """Thẻ đề xuất của MỘT hội thoại, kèm người duyệt được không."""
    await het_han_qua_han(conversation_id)
    rows = await db.fetch(
        """
        SELECT d.*, nd1.ho_ten AS ten_duyet, nd2.ho_ten AS ten_tu_choi
        FROM ai_de_xuat d
        LEFT JOIN nguoi_dung nd1 ON nd1.id = d.duyet_boi
        LEFT JOIN nguoi_dung nd2 ON nd2.id = d.tu_choi_boi
        WHERE d.conversation_id = $1 ORDER BY d.tao_luc
        """, conversation_id)
    from agent.core import xac_thuc

    ra = []
    for r in rows:
        hd = DANH_MUC.get(r["hanh_dong"])
        can = ["ai.duyet", *([hd.quyen_thi_hanh] if hd and hd.quyen_thi_hanh else [])]
        thieu = [q for q in can if nguoi is None or not xac_thuc.duoc_phep(nguoi, q)]
        kq_obj = r["ket_qua"] if isinstance(r["ket_qua"], dict) else {}
        da_thu_cong = (
            r["trang_thai"] == "da_thuc_hien"
            and kq_obj.get("qua") == "xu_ly_thu_cong"
        )
        nhan_tt = (
            "Đã xử lý thủ công"
            if da_thu_cong
            else NHAN_TRANG_THAI.get(r["trang_thai"], r["trang_thai"])
        )
        ra.append({
            "id": str(r["id"]),
            "hanh_dong": r["hanh_dong"],
            "ten_hanh_dong": hd.ten if hd else r["hanh_dong"],
            "che_do_ai": r["che_do_ai"],
            "muc_uy_quyen": r["muc_uy_quyen"],
            "nhan_muc": NHAN_MUC.get(r["muc_uy_quyen"], r["muc_uy_quyen"]),
            "ly_do_can_duyet": r["ly_do_can_duyet"],
            "trang_thai": r["trang_thai"],
            "nhan_trang_thai": nhan_tt,
            "order_id": str(r["order_id"]) if r["order_id"] else None,
            "message_id": str(r["message_id"]) if r["message_id"] else None,
            "de_xuat": r["de_xuat"] or {},
            "can_cu": r["can_cu"] or {},
            "tao_luc": _iso(r["tao_luc"]),
            "het_han_luc": _iso(r["het_han_luc"]),
            "duyet_boi": r["ten_duyet"], "duyet_luc": _iso(r["duyet_luc"]),
            "tu_choi_boi": r["ten_tu_choi"], "tu_choi_luc": _iso(r["tu_choi_luc"]),
            "ly_do_tu_choi": r["ly_do_tu_choi"],
            "thuc_hien_luc": _iso(r["thuc_hien_luc"]),
            "ket_qua": r["ket_qua"], "loi": r["loi"],
            "duoc_duyet": r["trang_thai"] == "cho_duyet" and not thieu,
            "duoc_hoan_tat_thu_cong": (
                r["trang_thai"] == "cho_xu_ly_thu_cong"
                and r["hanh_dong"] == "sua_don"
                and not thieu
            ),
            "thieu_quyen": (
                thieu
                if r["trang_thai"] in ("cho_duyet", "cho_xu_ly_thu_cong")
                else []
            ),
        })
    return ra
