"""
Kho máy chủ MCP: bảng `mcp_may_chu`, bí mật, đồng bộ công cụ vào
`ky_nang_cai_dat`, và đường gọi lúc chạy.

VÌ SAO CÔNG CỤ MCP LÀ MỘT DÒNG `ky_nang_cai_dat`, KHÔNG PHẢI BẢNG RIÊNG
----------------------------------------------------------------------
Một bảng riêng thì phải chép lại từng chốt đã có cho plugin: trần 12 công
cụ đang bật, chốt "công cụ có chủ" (không xoá lẻ, không sửa bằng form),
chốt tắt lúc thi hành, số đo `cong_cu.goi`, sandbox Phòng thử. Chép là sẽ
lệch, và lệch ở đây nghĩa là một công cụ NGOÀI đi vòng qua chốt mà công cụ
trong nhà phải qua. Dùng lại cột `goi` với giá trị `mcp:<tên>` thì mọi chốt
ấy áp dụng nguyên xi — tên gói không bao giờ chứa dấu hai chấm nên hai loại
chủ không lẫn.

VÌ SAO BÍ MẬT MÃ HOÁ THEO PHẠM VI
---------------------------------
Header xác thực (`Authorization: Bearer ...`) là khoá vào hệ thống của
người khác. Mã hoá kèm phạm vi `mcp:<tên>` nghĩa là bản mã của máy chủ này
không mở được dưới tên máy chủ khác: đổi tên trong CSDL không đổi được
quyền. API chỉ trả `co_bi_mat: true/false`, không bao giờ trả giá trị.

VÌ SAO ĐỒNG BỘ GIỮ CỜ NGƯỜI ĐẶT, VÀ HỎNG THÌ GIỮ CÔNG CỤ CŨ
-----------------------------------------------------------
Quản trị bật một công cụ ghi sau khi thử kỹ; lần đồng bộ sau ghi đè cờ ấy
là công việc kiểm duyệt bị xoá mà không ai báo. Và một lần mạng chập mà xoá
sạch công cụ thì cửa hàng mất năng lực giữa ngày, cũng không ai báo — nên
đồng bộ hỏng chỉ ghi `suc_khoe.ok = false`, không chạm dòng nào.

VÌ SAO CÔNG CỤ ĐỌC TỰ BẬT CÒN CÔNG CỤ GHI KHÔNG
-----------------------------------------------
Nối một máy chủ mà phải bật tay hai chục công cụ đọc thì người vận hành bỏ
giữa chừng. Công cụ GHI thì ngược lại: nó đổi dữ liệu ở hệ thống người
khác, nên nó phải là một quyết định có người bấm — hai lần, một lần bật
công cụ, một lần cho phép ghi ngoài Phòng thử.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from agent import cau_hinh_dong, db
from agent.cau_hinh_dong import VaultChuaSanSang
from agent.core import thu_nghiem
from agent.ky_nang import kho_ky_nang
from agent.ky_nang import mcp_khach as mk

# Xuất lại hai tên này để `agent/api/mcp_may_chu.py` không phải `import
# mcp_khach` trực tiếp — bài kiểm AST ở `test_ky_nang_plugin.py` chặn đúng
# việc đó (chỉ `kho_mcp.py` được nhập khẩu `mcp_khach`), vì mọi bí mật, hạn
# mức và nhật ký của máy chủ MCP phải đi qua lớp này, không có đường tắt.
from agent.ky_nang.mcp_khach import MCP_MAY_CHU_TOI_DA, LoiMCP  # noqa: F401
from agent.ky_nang.ban_mo_ta import _TEN_MAY_CHU_RE, LoiBanMoTa, doc_ban_mo_ta
from agent.ky_nang.kho_ky_nang import KhoDay
from agent.security.credential_vault import (
    CredentialVault,
    InvalidCredentialCiphertext,
    SealedCredential,
)

_log = logging.getLogger("agent.ky_nang.kho_mcp")

# Đệm địa chỉ + trạng thái máy chủ: `goi_cong_cu` chạy ở MỌI lời gọi công cụ
# MCP, và một lượt hỏi CSDL thêm cho mỗi lời gọi là lãng phí. 30 giây là hạn
# TRÊN của việc "tắt rồi mà công cụ còn chạy" — nhưng mọi đường ghi ở tệp
# này đều gọi `xoa_dem()`, nên trên thực tế tắt là có hiệu lực ngay.
_DEM: tuple[float, dict[str, dict]] | None = None
_DEM_GIAY = 30.0

NHAN_NGAN_NHAT = 3
NHAN_DAI_TOI_DA = 60
DIA_CHI_DAI_TOI_DA = 400
HEADER_TOI_DA = 5
HEADER_GIA_TRI_TOI_DA = 500
_TEN_HEADER_RE = re.compile(r"^[A-Za-z0-9-]{1,40}$")

# Một câu duy nhất cho mọi nhánh "không gọi được": mô hình phải nghe CÙNG
# một điều ở mọi kiểu hỏng — không có số liệu thì không được đoán số liệu.
_CHUYEN_NGUOI = "KHÔNG đoán kết quả thay công cụ — đã chuyển hội thoại cho người."


class MayChuKhongTonTai(LookupError):
    """Không có máy chủ MCP tên này (hoặc công cụ không thuộc máy chủ ấy)."""


class LoiMayChu(ValueError):
    """Tên, nhãn hay header không hợp lệ. Thông điệp nói rõ phải sửa gì."""


def xoa_dem() -> None:
    """Gọi sau MỌI lần ghi. Cũng dùng trong test để tách các ca khỏi nhau."""
    global _DEM
    _DEM = None


def _vault() -> CredentialVault:
    """
    Vault dùng chung với `cau_hinh_dong`, KHÔNG dựng lại ở đây.

    Dựng lại là hai chỗ đọc `CREDENTIAL_MASTER_KEYS` theo hai cách, và ngày
    chúng lệch nhau thì một nửa bí mật mở được, một nửa không — hỏng im lặng
    đúng ở chỗ tệ nhất. Là hàm mức module (không phải hằng) để test thay
    được, và để `.env` đổi có hiệu lực mà không phải khởi động lại.
    """
    return cau_hinh_dong._vault()


def _goi(ten: str) -> str:
    """Giá trị cột `goi` của mọi công cụ thuộc máy chủ này."""
    return f"mcp:{ten}"


def _pham_vi(ten: str) -> str:
    """
    Phạm vi mã hoá (AAD) của bí mật máy chủ.

    Trùng chuỗi với `_goi()` nhưng KHÔNG dùng chung hàm: đổi cách đặt tên
    cột `goi` là chuyện hiển thị, còn đổi phạm vi là mọi bản mã đã lưu
    không mở được nữa. Hai mục đích khác nhau thì hai hàm, để lần sửa sau
    không kéo theo cái kia.
    """
    return f"mcp:{ten}"


def _kiem_ten(ten: str) -> str:
    ten = (ten or "").strip().lower()
    if not _TEN_MAY_CHU_RE.match(ten):
        raise LoiMayChu(
            f"Tên máy chủ {ten!r} không hợp lệ: chữ thường không dấu, số và "
            "gạch dưới, bắt đầu bằng chữ, dài 2–20 ký tự. Ví dụ: kho_trung_tam."
        )
    return ten


def _kiem_nhan(nhan: str) -> str:
    nhan = (nhan or "").strip()
    if not NHAN_NGAN_NHAT <= len(nhan) <= NHAN_DAI_TOI_DA:
        raise LoiMayChu(f"Nhãn phải dài {NHAN_NGAN_NHAT}–{NHAN_DAI_TOI_DA} ký tự.")
    return nhan


def _kiem_headers(headers: dict | None) -> dict[str, str] | None:
    """
    Header xác thực: ít, tên đúng chuẩn, giá trị không quá dài.

    Trần ở đây không phải để tiết kiệm mà để ô này không thành chỗ nhét dữ
    liệu tuỳ ý vào một cột mã hoá — thứ đi ra mạng ở mọi lời gọi.
    """
    if not headers:
        return None
    if not isinstance(headers, dict):
        raise LoiMayChu("headers phải là object {tên: giá trị}.")
    if len(headers) > HEADER_TOI_DA:
        raise LoiMayChu(f"Quá {HEADER_TOI_DA} header.")
    ra: dict[str, str] = {}
    for k, v in headers.items():
        k = str(k).strip()
        if not _TEN_HEADER_RE.match(k):
            raise LoiMayChu(
                f"Tên header {k!r} không hợp lệ (chữ, số và gạch nối, ≤ 40 ký tự)."
            )
        gt = str(v)
        if len(gt) > HEADER_GIA_TRI_TOI_DA:
            raise LoiMayChu(f"Giá trị header {k!r} dài quá {HEADER_GIA_TRI_TOI_DA} ký tự.")
        ra[k] = gt
    return ra


def _tu_jsonb(x) -> dict:
    """
    Cột JSONB đọc qua codec (agent/db.py) về thẳng dict — đường thường.
    Nhánh chuỗi chỉ còn cần cho dòng ghi TRƯỚC ngày sửa lỗi mã hoá hai lần.
    """
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except (TypeError, ValueError):
            return {}
    return x if isinstance(x, dict) else {}


def _tho(bm) -> dict:
    """`BanMoTa` đã kiểm → dict để ghi thẳng vào cột JSONB (KHÔNG json.dumps)."""
    return {
        "ten": bm.ten,
        "loai": bm.loai,
        "mo_ta": bm.mo_ta,
        # Loại `mcp` không dùng `tham_so` — lược đồ nằm nguyên trong
        # `cau_hinh.luoc_do`. Vẫn ghi khoá rỗng để hình dạng dòng giống mọi
        # loại khác, khỏi phải phân nhánh ở nơi đọc.
        "tham_so": [],
        "cau_hinh": bm.cau_hinh,
    }


def _ban_mo_ta(ten: str, c, ten_cho_model: str, ghi: bool, ghi_cho_phep: bool) -> dict:
    return {
        "ten": ten_cho_model,
        "loai": "mcp",
        "mo_ta": c.mo_ta,
        "tham_so": [],
        "cau_hinh": {
            "may_chu": ten,
            "cong_cu_goc": c.ten,
            "luoc_do": c.luoc_do,
            "ghi": ghi,
            "ghi_cho_phep": ghi_cho_phep,
        },
    }


async def _doc_may_chu(ten: str) -> dict | None:
    return await db.fetchrow(
        "SELECT ten, nhan, dia_chi, bat, key_version, nonce, ciphertext, suc_khoe "
        "FROM mcp_may_chu WHERE ten = $1",
        ten,
    )


def _giai_ma_headers(row) -> dict[str, str] | None:
    """
    Bí mật ra khỏi CSDL đúng ở đây và không đi đâu khác — không vào nhật ký,
    không vào kết quả API, không vào đệm.
    """
    if row["key_version"] is None:
        return None
    d = _vault().decrypt_pham_vi(
        SealedCredential(int(row["key_version"]), row["nonce"], row["ciphertext"]),
        pham_vi=_pham_vi(row["ten"]),
    )
    h = d.get("headers")
    return {str(k): str(v) for k, v in h.items()} if isinstance(h, dict) else None


def _cat_cong_cu(cong_cu: list) -> tuple[list, list[dict]]:
    """Nhận tối đa CONG_CU_MOI_MAY_CHU_TOI_DA công cụ; phần dư báo ra `bo`."""
    if len(cong_cu) <= mk.CONG_CU_MOI_MAY_CHU_TOI_DA:
        return list(cong_cu), []
    # Sắp theo tên CHỈ khi phải cắt: đường thường giữ nguyên thứ tự máy chủ
    # khai, nhưng lúc cắt thì phải có một luật ổn định — cắt theo thứ tự
    # ngẫu nhiên là mỗi lần đồng bộ lại rơi mất một công cụ khác nhau.
    theo_ten = sorted(cong_cu, key=lambda c: c.ten)
    ly_do = (
        f"Máy chủ trả {len(cong_cu)} công cụ, quá trần "
        f"{mk.CONG_CU_MOI_MAY_CHU_TOI_DA} mỗi máy chủ."
    )
    bo = [
        {"ten": c.ten, "ly_do": ly_do}
        for c in theo_ten[mk.CONG_CU_MOI_MAY_CHU_TOI_DA:]
    ]
    return theo_ten[: mk.CONG_CU_MOI_MAY_CHU_TOI_DA], bo


def _luc() -> str:
    return datetime.now(timezone.utc).isoformat()


async def kiem_ket_noi(dia_chi: str, headers: dict | None = None) -> dict:
    """
    Xem trước: nối, liệt kê, chạy đủ bộ kiểm — nhưng KHÔNG ghi gì.

    Có nút này vì người vận hành cần thấy công cụ nào sẽ có VÀ công cụ nào
    bị bỏ vì lý do gì TRƯỚC khi tạo máy chủ; không có nó thì cách duy nhất
    để biết là tạo thật rồi đọc kết quả đồng bộ, và cái đã tạo thì phải xoá.
    """
    headers = _kiem_headers(headers)
    try:
        mk.kiem_dia_chi(dia_chi)
        cong_cu = await mk.liet_ke_cong_cu(dia_chi, headers)
    except mk.LoiMCP as exc:
        return {"ok": False, "so_cong_cu": 0, "cong_cu": [], "loi": str(exc)}

    nhan, bo = _cat_cong_cu(cong_cu)
    ra: list[dict] = [{"ten": b["ten"], "ly_do_bo": b["ly_do"]} for b in bo]
    da_dat: set[str] = set()
    so = 0
    for c in nhan:
        muc = {"ten": c.ten, "mo_ta": c.mo_ta, "ghi_goi_y": bool(c.goi_y_ghi)}
        try:
            # Tên máy chủ thật chưa có lúc bấm Kiểm; "kiem" chỉ để bộ kiểm
            # chạy được. Nó khớp `_TEN_MAY_CHU_RE` nên tên sinh ra cũng đúng
            # dạng thật — mô tả và lược đồ mới là thứ đang được soi ở đây.
            ten_model = mk.chuan_hoa_ten("kiem", c.ten, da_dat)
            doc_ban_mo_ta(
                _ban_mo_ta("kiem", c, ten_model, bool(c.goi_y_ghi), False), tu_dong_bo=True
            )
        except (mk.LoiMCP, LoiBanMoTa) as exc:
            muc["ly_do_bo"] = str(exc)
        else:
            da_dat.add(ten_model)
            so += 1
        ra.append(muc)
    return {"ok": True, "so_cong_cu": so, "cong_cu": ra, "loi": None}


async def them(
    ten: str, nhan: str, dia_chi: str, headers: dict | None, *, boi: str = "staff"
) -> dict:
    """Kiểm, mã hoá bí mật, ghi máy chủ, rồi đồng bộ ngay. Trả kết quả đồng bộ."""
    ten = _kiem_ten(ten)
    nhan = _kiem_nhan(nhan)
    dia_chi = (dia_chi or "").strip()
    if len(dia_chi) > DIA_CHI_DAI_TOI_DA:
        raise LoiMayChu(f"Địa chỉ dài quá {DIA_CHI_DAI_TOI_DA} ký tự.")
    mk.kiem_dia_chi(dia_chi)  # ném LoiMCP — câu lỗi nêu đúng biến .env cần sửa
    headers = _kiem_headers(headers)

    # Trùng tên và đủ 5 máy chủ đều là `KhoDay`, cùng một mã 409 ở API: cả
    # hai đều là "chỗ này đã có người", và người vận hành sửa bằng cùng một
    # thao tác — xoá bớt hoặc đặt tên khác.
    if await _doc_may_chu(ten) is not None:
        raise KhoDay(f"Đã có máy chủ tên {ten!r}. Xoá nó, hoặc đặt tên khác.")
    # Đếm bằng `fetch` rồi `len` chứ không `count(*)`: số dòng tối đa là 5,
    # và một câu trả về hàng thì CSDL giả trong test mô phỏng được đúng bộ
    # lọc, không phải đoán ra con số.
    dang_co = await db.fetch("SELECT ten FROM mcp_may_chu")
    if len(dang_co) >= mk.MCP_MAY_CHU_TOI_DA:
        raise KhoDay(
            f"Đã đủ {mk.MCP_MAY_CHU_TOI_DA} máy chủ MCP. Xoá bớt máy chủ "
            "không dùng rồi thử lại."
        )

    key_version = nonce = ciphertext = None
    if headers:
        # Vault chưa cấu hình thì ném `VaultChuaSanSang` (API dịch thành
        # 503) — TRƯỚC khi ghi dòng nào. Máy chủ không header vẫn thêm được
        # bình thường: không có gì để giữ thì không cần két.
        sealed = _vault().encrypt_pham_vi({"headers": headers}, pham_vi=_pham_vi(ten))
        key_version, nonce, ciphertext = sealed.key_version, sealed.nonce, sealed.ciphertext

    await db.execute(
        """
        INSERT INTO mcp_may_chu (ten, nhan, dia_chi, key_version, nonce, ciphertext, tao_boi)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        ten, nhan, dia_chi, key_version, nonce, ciphertext, boi,
    )
    await db.log_event("mcp.may_chu", actor=boi, ten=ten, viec="tao")
    xoa_dem()
    return await dong_bo(ten, boi=boi)


async def dong_bo(ten: str, *, boi: str = "staff") -> dict:
    """
    Hỏi máy chủ có công cụ nào, rồi khớp lại các dòng `ky_nang_cai_dat`.

    Đây là nơi DUY NHẤT dựng công cụ loại `mcp`, cũng là nơi duy nhất được
    truyền `tu_dong_bo=True` cho `doc_ban_mo_ta` — lược đồ ở đây đến từ
    chính máy chủ chứ không từ chữ người gõ. Thiếu cờ ấy thì mọi công cụ
    rơi vào nhánh "bỏ", và cột `goi` thiếu tiền tố `mcp:` thì `kho_ky_nang.
    _doc()` cũng từ chối chúng ở lần xoá đệm kế tiếp: hai vế, cùng một hậu
    quả là công cụ biến mất im lặng.
    """
    mc = await _doc_may_chu(ten)
    if mc is None:
        raise MayChuKhongTonTai(f"Không có máy chủ MCP tên {ten!r}.")
    goi_ten = _goi(ten)

    try:
        headers = _giai_ma_headers(mc)
        cong_cu = await mk.liet_ke_cong_cu(mc["dia_chi"], headers)
    except (mk.LoiMCP, VaultChuaSanSang, InvalidCredentialCiphertext) as exc:
        # KHÔNG chạm dòng nào: một lần mạng chập mà xoá sạch công cụ là cửa
        # hàng mất năng lực giữa ngày, và mất không ai báo.
        return await _ket_thuc(
            ten, boi,
            {"ok": False, "so_cong_cu": 0, "so_bat": 0, "so_bo": 0, "bo": [],
             "ghi_chu": None, "loi": str(exc), "luc": _luc()},
        )

    nhan, bo = _cat_cong_cu(cong_cu)

    hien = await db.fetch(
        "SELECT ten, bat, ban_mo_ta FROM ky_nang_cai_dat WHERE goi = $1", goi_ten
    )
    cu = {r["ten"]: r for r in hien}
    # Tên đụng công cụ VIẾT SẴN thì `doc_ban_mo_ta` đã chặn; ở đây chặn nốt
    # đụng plugin rời hay công cụ của gói khác. Ghi đè một dòng có chủ khác
    # là công cụ của người ta lặng lẽ đổi nghĩa.
    tat_ca = await db.fetch("SELECT ten, goi FROM ky_nang_cai_dat")
    ten_chu_khac = {r["ten"] for r in tat_ca if (r["goi"] or "") != goi_ten}

    ke_hoach: list[dict] = []
    da_dat: set[str] = set()
    for c in nhan:
        try:
            ten_model = mk.chuan_hoa_ten(ten, c.ten, da_dat)
        except mk.LoiMCP as exc:
            bo.append({"ten": c.ten, "ly_do": str(exc)})
            continue
        if ten_model in ten_chu_khac:
            bo.append({
                "ten": c.ten,
                "ly_do": f"Tên {ten_model!r} đã thuộc một plugin hoặc gói khác. "
                         "Đổi tên máy chủ, hoặc gỡ công cụ trùng tên.",
            })
            continue
        row_cu = cu.get(ten_model)
        ch_cu = (_tu_jsonb(row_cu["ban_mo_ta"]).get("cau_hinh") or {}) if row_cu else {}
        # Cờ do NGƯỜI đặt thắng gợi ý của máy chủ: quản trị đã đánh dấu một
        # công cụ là ghi (hoặc đã cho phép ghi sau khi thử) thì lần đồng bộ
        # sau không được xoá quyết định ấy.
        ghi = bool(ch_cu["ghi"]) if "ghi" in ch_cu else bool(c.goi_y_ghi)
        ghi_cho_phep = bool(ch_cu.get("ghi_cho_phep", False))
        try:
            bm = doc_ban_mo_ta(
                _ban_mo_ta(ten, c, ten_model, ghi, ghi_cho_phep), tu_dong_bo=True
            )
        except LoiBanMoTa as exc:
            # Mô tả có câu ra lệnh, lược đồ quá lớn, kiểu tham số lạ... — bỏ
            # ĐÚNG công cụ đó và NÓI RA. Bỏ im là dashboard hiện máy chủ
            # xanh, agent thì thiếu công cụ, và không ai nối được hai việc.
            bo.append({"ten": c.ten, "ly_do": str(exc)})
            continue
        da_dat.add(ten_model)
        ke_hoach.append({
            "bm": bm,
            "moi": row_cu is None,
            "bat": bool(row_cu["bat"]) if row_cu else False,
            "ghi": ghi,
        })

    # Trần 12: công cụ ĐỌC mới tự bật nếu còn chỗ, hết chỗ thì để tắt và nói
    # rõ ra — im lặng ở đây là người vận hành nối xong máy chủ, thấy nó
    # "xanh", rồi không hiểu vì sao agent không dùng công cụ nào.
    ghi_chu = None
    so_bat = sum(1 for k in ke_hoach if not k["moi"] and k["bat"])
    for k in ke_hoach:
        if not k["moi"] or k["ghi"]:
            continue
        try:
            # `so_bat + 1` là TỔNG số công cụ của máy chủ này sẽ bật, không
            # phải "thêm một": `kiem_tran_them` đã loại chủ này khỏi vế
            # "đang bật ngoài", nên truyền 1 là bỏ quên chính các công cụ
            # vừa bật ở vòng trước.
            await kho_ky_nang.kiem_tran_them(goi_ten, so_bat + 1, "Đồng bộ máy chủ MCP")
        except KhoDay as exc:
            k["bat"] = False
            ghi_chu = ghi_chu or f"{exc} Công cụ mới để TẮT; bật tay sau khi tắt bớt."
        else:
            k["bat"] = True
            so_bat += 1

    giu = [k["bm"].ten for k in ke_hoach]
    await db.execute(
        "DELETE FROM ky_nang_cai_dat WHERE goi = $1 AND ten <> ALL($2::text[])",
        goi_ten, giu,
    )
    for k in ke_hoach:
        await db.execute(
            """
            INSERT INTO ky_nang_cai_dat (ten, bat, ban_mo_ta, tao_boi, goi)
            VALUES ($1, $2, $3::jsonb, $4, $5)
            ON CONFLICT (ten) DO UPDATE
                SET ban_mo_ta = EXCLUDED.ban_mo_ta, sua_luc = now()
            """,
            # `bat` KHÔNG nằm trong DO UPDATE: dòng đã có giữ nguyên cờ người
            # đặt. `$3::jsonb` nhận thẳng dict — codec ở agent/db.py tự mã
            # hoá, thêm json.dumps ở đây là mã hoá HAI LẦN (cột thành chuỗi
            # JSON, tiếng Việt hoá \uXXXX).
            k["bm"].ten, k["bat"], _tho(k["bm"]), boi, goi_ten,
        )

    return await _ket_thuc(
        ten, boi,
        {"ok": True, "so_cong_cu": len(ke_hoach), "so_bat": so_bat, "so_bo": len(bo),
         "bo": bo, "ghi_chu": ghi_chu, "loi": None, "luc": _luc()},
    )


async def _ket_thuc(ten: str, boi: str, kq: dict) -> dict:
    """Ghi sức khoẻ + sự kiện + xoá đệm. Một chỗ, để không nhánh nào quên."""
    await db.execute(
        "UPDATE mcp_may_chu SET suc_khoe = $1::jsonb, sua_luc = now() WHERE ten = $2",
        kq, ten,  # dict thẳng vào $1::jsonb — xem chú thích mã hoá hai lần
    )
    await db.log_event(
        "mcp.dong_bo", actor=boi, ten=ten, ok=kq["ok"], so_cong_cu=kq["so_cong_cu"],
        so_bo=kq["so_bo"],
        # `bo` vào CẢ sự kiện, không chỉ vào kết quả trả về: kết quả chỉ
        # người đang bấm nút mới thấy, còn "công cụ nào bị bỏ vì mô tả có
        # câu ra lệnh" là thứ phải tra lại được sau nhiều ngày.
        bo=kq["bo"], loi=kq["loi"],
    )
    xoa_dem()
    kho_ky_nang.xoa_dem()
    return kq


async def bat_tat(ten: str, bat: bool, *, boi: str = "staff") -> None:
    """
    Tắt máy chủ = tắt MỌI công cụ của nó (chốt thứ hai ở `run_tool` chặn cả
    lược đồ còn sót trong lịch sử hội thoại). Bật lại = bật các công cụ ĐỌC
    còn chỗ dưới trần; công cụ GHI giữ tắt.

    Bật lại KHÔNG khôi phục đúng trạng thái trước khi tắt, có chủ ý: cờ
    "được ghi" là một quyết định có người bấm, và khôi phục tự động quyền
    ghi vào hệ thống người khác thì lần bấm ấy không bao giờ xảy ra.
    """
    if await _doc_may_chu(ten) is None:
        raise MayChuKhongTonTai(f"Không có máy chủ MCP tên {ten!r}.")
    goi_ten = _goi(ten)

    await db.execute("UPDATE mcp_may_chu SET bat = $1, sua_luc = now() WHERE ten = $2", bat, ten)
    if not bat:
        await db.execute("UPDATE ky_nang_cai_dat SET bat = $1 WHERE goi = $2", False, goi_ten)
    else:
        rows = await db.fetch(
            "SELECT ten, bat, ban_mo_ta FROM ky_nang_cai_dat WHERE goi = $1", goi_ten
        )
        so_bat = 0
        for r in rows:
            bm = _tu_jsonb(r["ban_mo_ta"])
            if (bm.get("cau_hinh") or {}).get("ghi"):
                continue
            try:
                await kho_ky_nang.kiem_tran_them(goi_ten, so_bat + 1, "Bật máy chủ MCP")
            except KhoDay as exc:
                # Không ném: máy chủ ĐÃ bật, và một ngoại lệ ở đây để lại
                # trạng thái nửa vời mà người bấm không biết đã tới đâu.
                # Nói ra bằng nhật ký thay vì im.
                _log.warning(
                    "máy chủ MCP %r: dừng bật công cụ ở cái thứ %d — %s",
                    ten, so_bat + 1, exc,
                )
                break
            so_bat += 1
            await db.execute(
                "UPDATE ky_nang_cai_dat SET bat = $1, ban_mo_ta = $2::jsonb, sua_luc = now() "
                "WHERE ten = $3",
                True, bm, r["ten"],
            )

    await db.log_event("mcp.may_chu", actor=boi, ten=ten, viec="bat" if bat else "tat")
    xoa_dem()
    kho_ky_nang.xoa_dem()


async def dat_cong_cu(
    ten: str,
    ten_cong_cu: str,
    *,
    bat: bool | None = None,
    ghi: bool | None = None,
    ghi_cho_phep: bool | None = None,
    boi: str = "staff",
) -> dict:
    """Đặt cờ cho MỘT công cụ. Chỉ đổi thứ được truyền vào, giữ nguyên phần còn lại."""
    if await _doc_may_chu(ten) is None:
        raise MayChuKhongTonTai(f"Không có máy chủ MCP tên {ten!r}.")
    goi_ten = _goi(ten)

    row = await db.fetchrow(
        "SELECT ten, bat, ban_mo_ta, goi FROM ky_nang_cai_dat WHERE ten = $1", ten_cong_cu
    )
    if row is None or (row["goi"] or "") != goi_ten:
        raise MayChuKhongTonTai(f"{ten_cong_cu!r} không phải công cụ của máy chủ {ten!r}.")

    bm_cu = _tu_jsonb(row["ban_mo_ta"])
    ch = dict(bm_cu.get("cau_hinh") or {})
    if ghi is not None:
        ch["ghi"] = bool(ghi)
    if ghi_cho_phep is not None:
        ch["ghi_cho_phep"] = bool(ghi_cho_phep)
    bat_moi = bool(row["bat"]) if bat is None else bool(bat)

    if bat_moi and not bool(row["bat"]):
        # Đếm TỔNG số công cụ của máy chủ này sẽ bật, không phải "thêm 1":
        # `kiem_tran_them` loại chủ này khỏi vế "đang bật ngoài", nên truyền
        # 1 là bỏ quên mọi công cụ khác của chính máy chủ ấy — trần 12 nới
        # ra âm thầm đúng bằng số công cụ nó đang bật.
        cua_goi = await db.fetch(
            "SELECT ten, bat FROM ky_nang_cai_dat WHERE goi = $1", goi_ten
        )
        dang_bat = sum(1 for r in cua_goi if bool(r["bat"]) and r["ten"] != ten_cong_cu)
        await kho_ky_nang.kiem_tran_them(goi_ten, dang_bat + 1, "Bật công cụ MCP")

    bm_cu["cau_hinh"] = ch
    # Chạy LẠI bộ kiểm: cấu hình vừa sửa cũng phải qua đúng cửa mà đường
    # đồng bộ đi qua — `ghi_cho_phep` chỉ có nghĩa với công cụ ghi, và luật
    # ấy sống ở `_kiem_cau_hinh` chứ không được chép lại ở đây.
    bm = doc_ban_mo_ta(bm_cu, tu_dong_bo=True)
    await db.execute(
        "UPDATE ky_nang_cai_dat SET bat = $1, ban_mo_ta = $2::jsonb, sua_luc = now() "
        "WHERE ten = $3",
        bat_moi, _tho(bm), ten_cong_cu,
    )
    await db.log_event(
        "mcp.may_chu", actor=boi, ten=ten, viec="cong_cu", cong_cu=ten_cong_cu,
        bat=bat_moi, ghi=bm.cau_hinh["ghi"], ghi_cho_phep=bm.cau_hinh["ghi_cho_phep"],
    )
    xoa_dem()
    kho_ky_nang.xoa_dem()
    return {"ten": ten_cong_cu, "bat": bat_moi, **bm.cau_hinh}


async def xoa(ten: str, *, boi: str = "staff") -> bool:
    """
    Xoá máy chủ và MỌI công cụ của nó.

    Xoá máy chủ mà bỏ lại công cụ là một dòng `ky_nang_cai_dat` trỏ vào hư
    không: mô hình vẫn thấy công cụ, gọi nó, và không ai trả lời.
    """
    if await _doc_may_chu(ten) is None:
        raise MayChuKhongTonTai(f"Không có máy chủ MCP tên {ten!r}.")
    goi_ten = _goi(ten)
    await db.execute("DELETE FROM ky_nang_cai_dat WHERE goi = $1", goi_ten)
    await db.execute("DELETE FROM mcp_may_chu WHERE ten = $1", ten)
    await db.log_event("mcp.may_chu", actor=boi, ten=ten, viec="xoa")
    xoa_dem()
    kho_ky_nang.xoa_dem()
    return True


async def liet_ke() -> list[dict]:
    """
    Toàn cảnh cho dashboard. KHÔNG bao giờ trả bí mật, và không trả cả địa
    chỉ đầy đủ: chuỗi truy vấn của một URL có thể chính là nơi đặt token
    (`?key=...`), nên chỉ host mới an toàn để hiện lên màn hình.
    """
    rows = await db.fetch(
        "SELECT ten, nhan, dia_chi, bat, key_version, suc_khoe, tao_boi "
        "FROM mcp_may_chu ORDER BY ten"
    )
    try:
        # Nhập khẩu TRONG hàm như `kho_ky_nang.liet_ke`: `goi` nhập khẩu
        # ngược lại `kho_ky_nang`, và số đo là thứ phụ — không đáng để một
        # vòng nhập khẩu ở mức module.
        from agent.ky_nang import goi as _goi_mod

        dem = await _goi_mod.dem_goi_7_ngay()
    except Exception as exc:  # noqa: BLE001 — số đo hỏng không được làm chết bảng
        _log.warning("không đếm được lượt gọi 7 ngày của công cụ MCP: %s", exc)
        dem = {}

    ra: list[dict] = []
    for r in rows:
        cong_cu_rows = await db.fetch(
            "SELECT ten, bat, ban_mo_ta FROM ky_nang_cai_dat WHERE goi = $1", _goi(r["ten"])
        )
        cong_cu = []
        for c in cong_cu_rows:
            bm = _tu_jsonb(c["ban_mo_ta"])
            ch = bm.get("cau_hinh") or {}
            cong_cu.append({
                "ten": c["ten"],
                "mo_ta": bm.get("mo_ta", ""),
                "cong_cu_goc": ch.get("cong_cu_goc", ""),
                "bat": bool(c["bat"]),
                "ghi": bool(ch.get("ghi", False)),
                "ghi_cho_phep": bool(ch.get("ghi_cho_phep", False)),
                "so_lan_7_ngay": dem.get(c["ten"], {}).get("so_lan", 0),
                "so_loi_7_ngay": dem.get(c["ten"], {}).get("so_loi", 0),
            })
        ra.append({
            "ten": r["ten"],
            "nhan": r["nhan"],
            "host": (urlparse(r["dia_chi"]).netloc or "").lower(),
            "bat": bool(r["bat"]),
            "co_bi_mat": r["key_version"] is not None,
            "suc_khoe": _tu_jsonb(r["suc_khoe"]),
            "tao_boi": r["tao_boi"],
            "so_cong_cu": len(cong_cu),
            "so_bat": sum(1 for c in cong_cu if c["bat"]),
            "cong_cu": cong_cu,
        })
    return ra


async def _may_chu_dem(ten: str) -> dict | None:
    global _DEM
    if _DEM is None or (time.monotonic() - _DEM[0]) > _DEM_GIAY:
        rows = await db.fetch(
            "SELECT ten, dia_chi, bat, key_version, nonce, ciphertext FROM mcp_may_chu"
        )
        _DEM = (time.monotonic(), {r["ten"]: dict(r) for r in rows})
    return _DEM[1].get(ten)


def _chuyen_nguoi(loi: str) -> dict:
    return {"loi": loi, "can_chuyen_nhan_vien": True, "ghi_chu": _CHUYEN_NGUOI}


async def goi_cong_cu(bm, args) -> dict:
    """
    Đường chạy của một công cụ MCP. Luôn trả dict, KHÔNG ném — cùng quy ước
    với `chay_plugin`: nhánh hỏng là "chuyển người", không phải nổ giữa lượt
    của khách.

    Hai chốt cho công cụ GHI (Phòng thử không gọi thật; ngoài Phòng thử phải
    có `ghi_cho_phep`) nằm cao hơn một tầng, trong `run_tool` — không lặp
    lại ở đây.
    """
    ten = str((bm.cau_hinh or {}).get("may_chu") or "")
    try:
        mc = await _may_chu_dem(ten)
    except Exception as exc:  # noqa: BLE001 — CSDL hỏng cũng chỉ là chuyển người
        _log.warning("máy chủ MCP %r: không đọc được cấu hình — %s", ten, exc)
        return _chuyen_nguoi(f"Không đọc được cấu hình máy chủ MCP {ten!r}.")
    if mc is None or not mc["bat"]:
        # Chốt thứ ba, sau `cong_cu_dang_bat` và `run_tool`: lược đồ còn nằm
        # trong lịch sử hội thoại của lượt trước thì mô hình vẫn gọi được,
        # và tới đây mới biết máy chủ đã tắt.
        return _chuyen_nguoi(
            f"Máy chủ MCP {ten!r} đang tắt hoặc đã bị xoá, không gọi công cụ được."
        )

    try:
        headers = _giai_ma_headers(mc)
    except (VaultChuaSanSang, InvalidCredentialCiphertext) as exc:
        _log.warning("máy chủ MCP %r: không mở được bí mật — %s", ten, exc)
        return _chuyen_nguoi(f"Không mở được bí mật của máy chủ MCP {ten!r}.")

    kq = await mk.goi(mc["dia_chi"], headers, str(bm.cau_hinh.get("cong_cu_goc") or ""), args)

    if kq.get("dau_hieu"):
        # Bỏ qua trong Phòng thử như `bao_mat.injection`: người đang thử tự
        # gõ câu đáng ngờ vào máy chủ giả thì đó là bài thử, không phải sự cố.
        if not thu_nghiem.dang_thu.get():
            await db.log_event(
                "bao_mat.mcp_injection", may_chu=ten, cong_cu=bm.ten,
                trich=str(kq.get("dau_hieu"))[:200],
            )
    elif kq.get("loi"):
        # VÌ SAO GHI NHẬT KÝ Ở ĐÂY. `.env` siết lại SAU khi máy chủ đã lưu
        # (bỏ một host khỏi KY_NANG_HOST_CHO_PHEP, hay DNS đổi) làm mọi công
        # cụ của nó chết — nhưng chết dưới dạng một dict "chuyển người"
        # giống hệt lúc máy chủ bận. Dashboard vẫn hiện máy chủ "đang bật",
        # công cụ "đang bật", và không có gì nói vì sao khách không bao giờ
        # được trả lời. Một dòng nêu TÊN MÁY CHỦ là cách rẻ nhất để việc ấy
        # nhìn thấy được.
        _log.warning(
            "máy chủ MCP %r: công cụ %r không gọi được — %s",
            ten, bm.ten, str(kq["loi"])[:200],
        )
    return kq
