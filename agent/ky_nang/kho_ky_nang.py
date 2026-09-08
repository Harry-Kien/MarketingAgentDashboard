"""
Đọc/ghi cài đặt kỹ năng, và dựng danh sách công cụ agent được dùng lúc này.

Có một bộ nhớ đệm, vì hàm `cong_cu_dang_bat()` chạy ở MỌI lượt trả lời
khách và một lượt hỏi CSDL thêm cho mỗi tin nhắn là lãng phí. Đệm được xoá
ngay khi ghi, nên không có chuyện tắt một kỹ năng rồi nó vẫn chạy thêm vài
phút — đó đúng là kiểu hỏng im lặng mà cả bảng này sinh ra để tránh.
"""
# ĐỌC: ══ TRẠM B4 + C3 · HAI CÂU HỎI KHÁC NHAU, HAI THỜI ĐIỂM KHÁC NHAU ══
# ĐỌC: Bản đồ đầy đủ ba chặng: agent/ky_nang/__init__.py
# ĐỌC:
# ĐỌC:   B4  cong_cu_dang_bat()  "CÔNG BỐ những gì?"  — một lần mỗi lượt
# ĐỌC:   C3  dang_tat()          "CÓ ĐƯỢC LÀM không?" — mỗi lần mô hình gọi
# ĐỌC:
# ĐỌC: Hai hàm ấy trông như hỏi cùng một chuyện, và đó là lý do có người sẽ
# ĐỌC: muốn gộp chúng lại. ĐỪNG. Chúng chạy ở hai thời điểm cách nhau vài
# ĐỌC: giây tới vài ngày, và khoảng cách ấy chính là chỗ hỏng:
# ĐỌC:
# ĐỌC:   10:00  khách hỏi giá → mô hình gọi công cụ → lược đồ VÀO lịch sử
# ĐỌC:   10:01  quản trị TẮT công cụ đó trên dashboard
# ĐỌC:   10:02  khách hỏi tiếp → B4 đã bỏ công cụ khỏi lược đồ MỚI, nhưng
# ĐỌC:          mô hình vẫn thấy nó trong LỊCH SỬ của lượt 10:00 và gọi lại
# ĐỌC:
# ĐỌC: B4 không với tới lượt 10:00 được nữa. Chỉ C3 chặn được, vì nó kiểm
# ĐỌC: lúc THI HÀNH. Xem chốt thứ hai trong `agent/core/tools.py`.
# ĐỌC:
# ĐỌC: BA ĐƯỜNG GHI VÀO CÙNG BẢNG `ky_nang_cai_dat`, và cả ba phải qua cùng
# ĐỌC: một chốt trần plugin — nếu không thì "vượt trần" chỉ đúng cho đường
# ĐỌC: có kiểm, hai đường kia lặng lẽ đẩy CSDL qua trần:
# ĐỌC:
# ĐỌC:   luu_plugin()           ở tệp này          — thêm plugin rời
# ĐỌC:   goi.cai()              cài một gói mới
# ĐỌC:   goi.bat_tat(bat=True)  bật lại gói đã tắt — chỉ UPDATE, dễ quên nhất
# ĐỌC:
# ĐỌC: `_DEM` ở đây là đệm CÔNG CỤ; `goi._DEM` là đệm GÓI. Hai thứ khác
# ĐỌC: nhau, phải xoá cả hai sau mỗi lần ghi.
from __future__ import annotations

import json

from agent import db
from agent.ky_nang.ban_mo_ta import (
    PLUGIN_TOI_DA,
    BanMoTa,
    LoiBanMoTa,
    doc_ban_mo_ta,
    thanh_cong_cu,
)
from agent.ky_nang.so_dang_ky import KHONG_TAT_DUOC, SO_DANG_KY, ten_ky_nang_co_san

# Đệm: (tên đang tắt, plugin đang bật, gói sở hữu từng plugin).
# None = chưa đọc lần nào.
#
# VÌ SAO GIỮ "gói sở hữu" NGAY Ở ĐÂY chứ không tra qua bảng số đo: nhãn gói
# từng lấy từ `dem_goi_7_ngay()` (đếm sự kiện 7 ngày), nên một plugin của gói
# CHƯA ai gọi lần nào trong tuần hiện ra như plugin rời — dashboard cho nút
# "Xoá" và người vận hành xoá được một mảnh của gói đang bật. Cột `goi` trong
# `ky_nang_cai_dat` mới là sự thật; số đo chỉ để đếm.
_DEM: tuple[frozenset[str], tuple[BanMoTa, ...], dict[str, str]] | None = None


class KhoDay(RuntimeError):
    """Vượt một trần: plugin đang bật, gói, hay máy chủ MCP."""


async def kiem_tran_them(chu: str | None, so_them: int, hanh_dong: str) -> None:
    """
    Trần plugin đang bật, dùng CHUNG cho mọi đường ghi vào `ky_nang_cai_dat`:
    plugin rời, gói (cài/bật lại), máy chủ MCP (đồng bộ/bật công cụ). Một
    bảng, một chốt — xem chú thích ở `goi._kiem_tran_plugin` vì sao.

    Ở ĐÂY chứ không ở `goi.py`: đường MCP không được nhập khẩu `goi` (vòng
    nhập khẩu), nên chốt nằm bên ấy thì đường thứ ba lặng lẽ không qua chốt
    nào — đúng kiểu hỏng mà chính chú thích kia sinh ra để chặn.

    `chu` là chủ sở hữu đang được tính lại (tên gói, hay `mcp:<máy chủ>`).
    Công cụ của chính chủ ấy KHÔNG đếm vào "đang bật ngoài", vì `so_them` đã
    là con số cuối cùng của chủ ấy sau thao tác; đếm cả hai đầu là tính hai
    lần và trần đầy sớm hơn thật.
    """
    if so_them <= 0:
        return
    ngoai = await db.fetch(
        "SELECT ten FROM ky_nang_cai_dat "
        "WHERE ban_mo_ta IS NOT NULL AND bat AND (goi IS NULL OR goi <> $1)",
        chu or "",
    )
    tong = len(ngoai) + so_them
    if tong > PLUGIN_TOI_DA:
        raise KhoDay(
            f"{hanh_dong} thành {tong} plugin đang bật, quá trần {PLUGIN_TOI_DA}: đang bật "
            f"ngoài {chu!r} là {len(ngoai)}, thêm {so_them}. Tắt bớt plugin không dùng rồi thử lại."
        )


def xoa_dem() -> None:
    """Gọi sau MỌI lần ghi. Cũng dùng trong test để tách các ca khỏi nhau."""
    global _DEM
    _DEM = None


async def _doc() -> tuple[frozenset[str], tuple[BanMoTa, ...], dict[str, str]]:
    global _DEM
    if _DEM is not None:
        return _DEM

    try:
        rows = await db.fetch("SELECT ten, bat, ban_mo_ta, goi FROM ky_nang_cai_dat")
    except Exception:
        # CSDL chưa migrate, hoặc đang chạy test không có CSDL. Rơi về "mọi
        # kỹ năng có sẵn đều bật, không có plugin" — đúng trạng thái trước
        # khi có tính năng này, nên hệ thống cũ vẫn chạy y như cũ.
        _DEM = (frozenset(), (), {})
        return _DEM

    tat: set[str] = set()
    plugin: list[BanMoTa] = []
    goi_cua: dict[str, str] = {}
    for r in rows:
        ten = r["ten"]
        bat = bool(r["bat"])
        tho = r["ban_mo_ta"]
        if r["goi"]:
            goi_cua[ten] = r["goi"]
        if tho is None:
            if not bat:
                tat.add(ten)
            continue
        if not bat:
            continue
        if isinstance(tho, str):
            # Codec ở agent/db.py trả JSONB thẳng thành dict — đường thường.
            # Nhánh này chỉ còn cần cho dòng ghi TRƯỚC ngày sửa lỗi mã hoá
            # hai lần ở luu_plugin() (cột khi đó thật sự chứa chuỗi JSON).
            tho = json.loads(tho)
        # `tu_dong_bo` mở khoá loại `mcp`, vốn không tạo tay được. CSDL là
        # đường TIN CẬY ở đúng chỗ này và chỉ ở đây: cột `goi` dạng
        # "mcp:<máy chủ>" chỉ `kho_mcp.dong_bo()` mới ghi được — `luu_plugin`
        # để trống cột ấy, `goi.cai` ghi tên gói. Đọc lại một dòng đã đồng bộ
        # rồi từ chối nó thì công cụ MCP biến mất ngay sau lần xoá đệm kế
        # tiếp, và biến mất gần như im lặng: chỗ bắt lỗi chỉ ghi một sự kiện.
        tu_dong_bo = str(r["goi"] or "").startswith("mcp:")
        try:
            plugin.append(doc_ban_mo_ta(tho, tu_dong_bo=tu_dong_bo))
        except LoiBanMoTa:
            # Một bản mô tả hỏng KHÔNG được làm chết cả agent. Bỏ qua đúng
            # plugin đó và đi tiếp — nhưng bỏ qua trong im lặng thì không ai
            # biết công cụ đã biến mất, nên ghi nhật ký thành sự kiện.
            await _ghi_nhat_ky_plugin_hong(ten)

    _DEM = (frozenset(tat), tuple(plugin), goi_cua)
    return _DEM


async def _ghi_nhat_ky_plugin_hong(ten: str) -> None:
    try:
        await db.log_event("ky_nang.ban_mo_ta_hong", actor="system", ten=ten)
    except Exception:
        pass


async def cong_cu_dang_bat(tat_ca: list[dict]) -> list[dict]:
    """
    Lọc `TOOLS` theo cài đặt, rồi ghép thêm lược đồ của plugin đang bật.

    `tat_ca` truyền vào thay vì nhập khẩu `tools.TOOLS` để tránh vòng nhập
    khẩu: `tools.py` gọi ngược lại module này.
    """
    tat, plugin, _ = await _doc()
    ra = [t for t in tat_ca if t["name"] not in tat]
    ra.extend(thanh_cong_cu(bm) for bm in plugin)
    return ra


async def dang_tat(ten: str) -> bool:
    """Kỹ năng này đang bị tắt? Dùng ở chốt thứ hai trong `run_tool`."""
    if ten in KHONG_TAT_DUOC:
        return False
    tat, plugin, _ = await _doc()
    if ten in tat:
        return True
    # Một plugin đã xoá hoặc đã tắt vẫn có thể bị model gọi, vì lược đồ của
    # nó còn nằm trong lịch sử hội thoại của lượt trước.
    if ten not in ten_ky_nang_co_san():
        return not any(bm.ten == ten for bm in plugin)
    return False


async def tim_plugin(ten: str) -> BanMoTa | None:
    _, plugin, _ = await _doc()
    for bm in plugin:
        if bm.ten == ten:
            return bm
    return None


async def dat_bat_tat(ten: str, bat: bool, *, boi: str = "staff") -> None:
    """
    Bật/tắt một kỹ năng có sẵn.

    Ném `LoiBanMoTa` khi ai đó cố tắt `chuyen_nhan_vien`. Chốt này lặp lại
    chốt ở tầng API — cố ý: tầng API chặn được người bấm nhầm trên dashboard,
    chốt này chặn được cả script chạy thẳng vào hàm.
    """
    if ten not in ten_ky_nang_co_san():
        raise LoiBanMoTa(f"{ten!r} không phải kỹ năng có sẵn.")
    if not bat and ten in KHONG_TAT_DUOC:
        raise LoiBanMoTa(
            f"{ten!r} không tắt được: bốn trong sáu lớp lưới an toàn kết thúc "
            "bằng việc gọi nó. Tắt nó là để các lớp ấy phán đúng rồi không "
            "còn chỗ nào giao việc."
        )
    await db.execute(
        """
        INSERT INTO ky_nang_cai_dat (ten, bat, tao_boi)
        VALUES ($1, $2, $3)
        ON CONFLICT (ten) DO UPDATE SET bat = EXCLUDED.bat, sua_luc = now()
        """,
        ten, bat, boi,
    )
    await db.log_event("ky_nang.bat_tat", actor=boi, ten=ten, bat=str(bat))
    xoa_dem()


LICH_SU_GIU = 10


class BanCuKhongCo(LookupError):
    """Không có bản cũ mang số ấy cho plugin này."""


async def _ghi_lich_su(ten: str, boi: str) -> None:
    """
    Cất bản ĐANG CHẠY trước khi đè lên nó.

    Ghi bản CŨ chứ không phải bản mới: ghi bản mới thì lịch sử trùng lặp
    với `ky_nang_cai_dat` và không lùi được bước nào.

    Chưa có gì để đè thì không ghi — tạo mới không đè lên cái gì, và một
    hàng rỗng ở đó là mời người ta "khôi phục" về trạng thái không tồn tại.

    Ghi hỏng KHÔNG được chặn việc lưu: người vận hành đang sửa một bảng giá
    và mất đường lùi thì tệ, nhưng mất luôn cả lần sửa thì tệ hơn.
    """
    try:
        cu = await db.fetchrow(
            "SELECT ban_mo_ta, goi FROM ky_nang_cai_dat WHERE ten = $1", ten)
        if cu is None or cu["ban_mo_ta"] is None or cu["goi"]:
            return
        tho = cu["ban_mo_ta"]
        if isinstance(tho, str):
            tho = json.loads(tho)
        await db.execute(
            "INSERT INTO ky_nang_lich_su (ten, noi_dung, thay_boi) "
            "VALUES ($1, $2::jsonb, $3)", ten, tho, boi)
        # Cắt ngay tại chỗ ghi. Dọn theo lịch riêng thì bảng phình giữa hai
        # lần dọn, mà mỗi cú bấm "thêm khoá khách hay hỏi" là một bản nữa.
        await db.execute(
            "DELETE FROM ky_nang_lich_su WHERE ten = $1 AND id NOT IN "
            "(SELECT id FROM ky_nang_lich_su WHERE ten = $1 ORDER BY id DESC LIMIT $2)",
            ten, LICH_SU_GIU)
    except Exception:  # noqa: BLE001 — mất đường lùi còn hơn mất lần sửa
        pass


async def lich_su_plugin(ten: str) -> list[dict]:
    """
    Các bản cũ, mới nhất trước. KHÔNG trả `noi_dung`.

    Danh sách này chỉ để CHỌN; cấu hình đầy đủ của mười bản là một khối
    chữ lớn đi qua mạng mỗi lần mở màn Kỹ năng, và màn ấy tự làm mới.
    """
    rows = await db.fetch(
        "SELECT id, thay_luc, thay_boi FROM ky_nang_lich_su "
        "WHERE ten = $1 ORDER BY id DESC LIMIT $2", ten, LICH_SU_GIU)
    return [dict(r) for r in rows]


async def khoi_phuc_plugin(ten: str, id_ban: int, *, boi: str = "staff") -> BanMoTa:
    """
    Đưa một bản cũ trở lại, ĐI QUA `luu_plugin` như mọi đường ghi khác.

    Không ghi thẳng vào bảng: một bản cũ có thể không còn hợp lệ theo luật
    thêm sau này — khoá lồng nhau chẳng hạn, cấm từ ngày có
    `khoa_long_nhau`. Cài đè nó lặng lẽ là mở lại đúng lỗ hổng mà luật ấy
    sinh ra để bịt. Đi qua `luu_plugin` cũng có nghĩa bản ĐANG chạy vào
    lịch sử, nên lùi được cả cú lùi.
    """
    r = await db.fetchrow(
        "SELECT noi_dung FROM ky_nang_lich_su WHERE id = $1 AND ten = $2", id_ban, ten)
    if r is None:
        raise BanCuKhongCo(f"{ten}#{id_ban}")
    tho = r["noi_dung"]
    if isinstance(tho, str):
        tho = json.loads(tho)
    return await luu_plugin(dict(tho, ten=ten), boi=boi)


async def luu_plugin(tho: dict, *, boi: str = "staff") -> BanMoTa:
    """Kiểm rồi lưu một plugin. Bản mô tả sai thì không có gì được ghi."""
    bm = doc_ban_mo_ta(tho)

    # Công cụ của một GÓI không sửa được bằng đường plugin rời: gói là nguồn
    # sự thật, và lần cài lại gói sau đó dựng lại y bản cũ — sửa ở đây là một
    # thay đổi lặng lẽ biến mất, đúng kiểu hỏng không ai biết. Hỏi thẳng CSDL
    # chứ không hỏi bộ đệm: dòng của gói đang TẮT không nằm trong bộ đệm,
    # nhưng cái tên vẫn là của gói đó.
    chu = await db.fetchrow("SELECT goi FROM ky_nang_cai_dat WHERE ten = $1", bm.ten)
    if chu is not None and chu["goi"]:
        raise LoiBanMoTa(
            f"{bm.ten!r} là công cụ thuộc gói {chu['goi']!r} — sửa trong bản "
            "gói rồi cài lại gói, đừng sửa riêng ở đây."
        )

    # Trần số plugin kiểm ở đây chứ không ở `doc_ban_mo_ta`: bộ kiểm ấy là
    # hàm thuần, không biết trong CSDL đang có bao nhiêu dòng.
    _, dang_co, _ = await _doc()
    if bm.ten not in {p.ten for p in dang_co} and len(dang_co) >= PLUGIN_TOI_DA:
        raise LoiBanMoTa(
            f"Đã đủ {PLUGIN_TOI_DA} plugin đang bật. Mỗi công cụ thêm vào là "
            "thêm lược đồ trong MỌI lời gọi model — tắt bớt cái không dùng."
        )

    await _ghi_lich_su(bm.ten, boi)

    await db.execute(
        """
        INSERT INTO ky_nang_cai_dat (ten, bat, ban_mo_ta, tao_boi)
        VALUES ($1, TRUE, $2::jsonb, $3)
        ON CONFLICT (ten) DO UPDATE
            SET ban_mo_ta = EXCLUDED.ban_mo_ta, bat = TRUE, sua_luc = now()
        """,
        bm.ten,
        # $2::jsonb nhận thẳng dict — codec ở agent/db.py (set_type_codec
        # encoder=json.dumps) tự mã hoá. json.dumps() thêm ở đây từng làm
        # cột chứa một CHUỖI JSON thay vì object (mã hoá hai lần), nên
        # "ban_mo_ta->>'mo_ta'" trả NULL và tiếng Việt hoá thành \uXXXX.
        {
            "ten": bm.ten, "mo_ta": bm.mo_ta, "loai": bm.loai,
            "tham_so": [
                {"ten": t.ten, "mo_ta": t.mo_ta, "bat_buoc": t.bat_buoc}
                for t in bm.tham_so
            ],
            "cau_hinh": bm.cau_hinh,
            # Không lưu thì câu thử biến mất ngay sau lần Lưu đầu tiên —
            # người vận hành gõ xong, thấy nó chạy, rồi lần sau mở lại thì
            # trống trơn và không hiểu vì sao.
            "cau_thu": [{"hoi": c.hoi, "mong_doi": c.mong_doi} for c in bm.cau_thu],
        },
        boi,
    )
    await db.log_event("ky_nang.plugin_luu", actor=boi, ten=bm.ten, loai=bm.loai)
    xoa_dem()
    return bm


async def xoa_plugin(ten: str, *, boi: str = "staff") -> bool:
    """Xoá hẳn một plugin. Kỹ năng có sẵn thì tắt, không xoá được."""
    if ten in ten_ky_nang_co_san():
        raise LoiBanMoTa(f"{ten!r} là kỹ năng viết sẵn — tắt được, không xoá được.")
    # `db.execute` trả về CHUỖI trạng thái kiểu "DELETE 0", không phải số
    # dòng. `bool("DELETE 0")` là True — nên trả thẳng nó ra thì xoá một tên
    # không tồn tại vẫn báo thành công, và dashboard hiện "đã xoá" cho một
    # việc chưa từng xảy ra.
    # `AND goi IS NULL`: xoá riêng một công cụ CỦA GÓI để lại một gói đang
    # bật thiếu mảnh — agent mất công cụ, hướng dẫn vẫn dạy nó gọi, và
    # dashboard vẫn hiện gói "đang bật". Không nổ, không nhật ký. Muốn bỏ
    # thì tắt hoặc xoá cả gói.
    trang_thai = await db.execute(
        "DELETE FROM ky_nang_cai_dat WHERE ten = $1 AND ban_mo_ta IS NOT NULL AND goi IS NULL", ten
    )
    so_dong = int(str(trang_thai).rsplit(" ", 1)[-1] or 0)
    if not so_dong:
        # Không xoá được: hoặc chưa từng có tên này (trả False như cũ), hoặc
        # nó thuộc một gói — hai chuyện rất khác nhau, phải nói ra chuyện thứ hai.
        chu = await db.fetchrow("SELECT goi FROM ky_nang_cai_dat WHERE ten = $1", ten)
        if chu is not None and chu["goi"]:
            goi_chu = str(chu["goi"])
            # Cột `goi` mang HAI loại chủ: tên gói kỹ năng thật, và
            # `mcp:<tên máy chủ>`. Nói "thuộc gói 'mcp:kho_erp'" là chỉ người
            # vận hành đi tìm một gói không tồn tại ở panel Gói kỹ năng; chỗ
            # gỡ nó nằm ở panel khác hẳn. Chuỗi `mcp:` sinh ra để KHÔNG phải
            # hiện ra ngoài — dashboard đã tránh nó ở huy hiệu, câu lỗi này
            # là chỗ cuối cùng còn để lọt.
            if goi_chu.startswith("mcp:"):
                raise LoiBanMoTa(
                    f"{ten!r} là công cụ thuộc máy chủ MCP {goi_chu[4:]!r} — tắt "
                    "hoặc xoá máy chủ ở panel Máy chủ MCP, không xoá riêng công "
                    "cụ của nó."
                )
            raise LoiBanMoTa(
                f"{ten!r} là công cụ thuộc gói {goi_chu!r} — tắt hoặc xoá "
                "gói đó, không xoá riêng công cụ của nó."
            )
    if so_dong:
        await db.log_event("ky_nang.plugin_xoa", actor=boi, ten=ten)
        xoa_dem()
    return so_dong > 0


async def khong_khop_7_ngay(toi_da: int = 5) -> dict[str, list[dict]]:
    """
    Khoá khách hỏi mà bảng chưa có, gộp theo công cụ, 7 ngày, nhiều nhất
    trước.

    Bỏ lượt phòng thử cùng lý do `dem_goi_7_ngay`: thử mười lần một khoá
    không có trong bảng thì đó là bạn đang thử chứ không phải nhu cầu của
    khách, và nó sẽ đứng đầu bảng xếp hạng, tức bảng chỉ về chính nó.

    CSDL hỏng thì trả rỗng. Đây là gợi ý cải thiện, không phải thứ được
    phép làm chết bảng kỹ năng — cùng lối rơi của `dem_goi_7_ngay`.
    """
    try:
        rows = await db.fetch(
            """
            SELECT detail->>'ten' AS ten, detail->>'khong_khop' AS gia_tri,
                   count(*) AS so_lan
            FROM events
            WHERE kind = 'cong_cu.goi'
              AND created_at > now() - interval '7 days'
              AND detail->>'khong_khop' IS NOT NULL
              AND coalesce(detail->>'thu_nghiem', 'false') <> 'true'
            GROUP BY 1, 2
            ORDER BY 1, 3 DESC
            """
        )
    except Exception:  # noqa: BLE001 — gợi ý mất thì thôi, bảng vẫn phải vẽ
        return {}
    ra: dict[str, list[dict]] = {}
    for r in rows:
        # Bỏ qua hàng không đúng hình dạng thay vì ném. Hàm này chạy TRONG
        # `liet_ke()`, nên một KeyError ở đây làm chết cả bảng kỹ năng —
        # mất danh sách công cụ chỉ vì một cột gợi ý. Cùng lối rơi với
        # nhánh `except` bên trên: tầng gợi ý không được mạnh hơn thứ nó
        # phục vụ.
        ten, gia_tri, so_lan = r.get("ten"), r.get("gia_tri"), r.get("so_lan")
        if not ten or gia_tri is None or so_lan is None:
            continue
        muc = ra.setdefault(ten, [])
        if len(muc) < toi_da:
            muc.append({"gia_tri": gia_tri, "so_lan": int(so_lan)})
    return ra


async def liet_ke(dem: dict[str, dict] | None = None) -> dict:
    """
    Toàn cảnh cho dashboard: kỹ năng có sẵn + plugin, kèm trạng thái.

    `dem` nhận từ ngoài để một màn hình gọi CẢ hai bảng (kỹ năng và gói)
    chỉ quét bảng `events` một lần; không truyền thì tự đếm.
    """
    tat, plugin, goi_cua = await _doc()

    # Nhập khẩu TRONG hàm, không ở đầu file: `goi.py` nhập khẩu ngược lại
    # module này ở mức module (để test monkeypatch được `kho_ky_nang.xoa_dem`
    # qua tên module) — nhập khẩu `goi` ở đầu file này sẽ thành vòng.
    from agent.ky_nang import goi as _goi

    if dem is None:
        dem = await _goi.dem_an_toan()
    truot = await khong_khop_7_ngay()

    return {
        "co_san": [
            {
                "ten": k.ten,
                "nhom": k.nhom,
                "muc_rui_ro": k.muc_rui_ro,
                "tom_tat": k.tom_tat,
                "tat_thi_mat_gi": k.tat_thi_mat_gi,
                "can_erp": k.can_erp,
                "can_kho_tri_thuc": k.can_kho_tri_thuc,
                "tat_duoc": k.tat_duoc,
                "bat": k.ten not in tat,
                "so_lan_7_ngay": dem.get(k.ten, {}).get("so_lan", 0),
                "so_loi_7_ngay": dem.get(k.ten, {}).get("so_loi", 0),
            }
            for k in SO_DANG_KY
        ],
        "plugin": [
            {
                "ten": p.ten,
                "loai": p.loai,
                "mo_ta": p.mo_ta,
                # Danh sách tên, KHÔNG phải object: cột phụ trên dashboard
                # nối mảng này bằng dấu phẩy, đổi kiểu là in ra [object
                # Object]. Hình dạng đầy đủ nằm ở `ban_mo_ta` bên dưới.
                "tham_so": [t.ten for t in p.tham_so],
                "bat": True,
                "so_lan_7_ngay": dem.get(p.ten, {}).get("so_lan", 0),
                "so_loi_7_ngay": dem.get(p.ten, {}).get("so_loi", 0),
                "goi": goi_cua.get(p.ten),
                # Huy hiệu "MCP · <máy chủ>" thay cho "gói". Cùng cột `goi`
                # mang hai loại chủ (tên gói không bao giờ chứa dấu hai
                # chấm), nên tách ngay ở đây: để dashboard tự cắt chuỗi là
                # luật nằm ở hai nơi, và nơi thứ hai viết bằng JavaScript
                # không có test nào canh.
                "mcp": (
                    goi_cua[p.ten][4:]
                    if str(goi_cua.get(p.ten) or "").startswith("mcp:")
                    else None
                ),
                # Khoá khách hỏi mà bảng chưa có — thứ đáng thêm vào bảng
                # nhất, xếp theo số lần thật. Không có ô này thì bảng nằm im
                # ở đúng kích cỡ ngày nó được tạo.
                "khong_khop": truot.get(p.ten, []),
                # Đủ để nạp NGƯỢC vào form sửa — thiếu `cau_hinh` thì đổi
                # một dòng phí ship là gõ lại cả bảng, và người vận hành bỏ
                # sau lần thứ hai.
                #
                # None cho công cụ THUỘC GÓI: `luu_plugin` đã từ chối sửa
                # chúng (gói là nguồn sự thật, cài lại gói dựng đè bản sửa).
                # Nói cùng một luật ở cả hai đầu để dashboard khỏi hiện một
                # nút chỉ để báo lỗi khi bấm.
                "ban_mo_ta": None if goi_cua.get(p.ten) else {
                    "loai": p.loai,
                    "mo_ta": p.mo_ta,
                    "tham_so": [
                        {"ten": t.ten, "mo_ta": t.mo_ta, "bat_buoc": t.bat_buoc}
                        for t in p.tham_so
                    ],
                    "cau_hinh": p.cau_hinh,
                    # Không trả thì mở form Sửa xong bấm Lưu là câu thử bị
                    # xoá sạch — người vận hành không đụng vào nó lần nào.
                    "cau_thu": [
                        {"hoi": c.hoi, "mong_doi": c.mong_doi} for c in p.cau_thu
                    ],
                },
            }
            for p in plugin
        ],
        "plugin_toi_da": PLUGIN_TOI_DA,
    }
