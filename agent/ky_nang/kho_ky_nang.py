"""
Đọc/ghi cài đặt kỹ năng, và dựng danh sách công cụ agent được dùng lúc này.

Có một bộ nhớ đệm, vì hàm `cong_cu_dang_bat()` chạy ở MỌI lượt trả lời
khách và một lượt hỏi CSDL thêm cho mỗi tin nhắn là lãng phí. Đệm được xoá
ngay khi ghi, nên không có chuyện tắt một kỹ năng rồi nó vẫn chạy thêm vài
phút — đó đúng là kiểu hỏng im lặng mà cả bảng này sinh ra để tránh.
"""
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

# Đệm: (tên đang tắt, plugin đang bật). None = chưa đọc lần nào.
_DEM: tuple[frozenset[str], tuple[BanMoTa, ...]] | None = None


def xoa_dem() -> None:
    """Gọi sau MỌI lần ghi. Cũng dùng trong test để tách các ca khỏi nhau."""
    global _DEM
    _DEM = None


async def _doc() -> tuple[frozenset[str], tuple[BanMoTa, ...]]:
    global _DEM
    if _DEM is not None:
        return _DEM

    try:
        rows = await db.fetch("SELECT ten, bat, ban_mo_ta FROM ky_nang_cai_dat")
    except Exception:
        # CSDL chưa migrate, hoặc đang chạy test không có CSDL. Rơi về "mọi
        # kỹ năng có sẵn đều bật, không có plugin" — đúng trạng thái trước
        # khi có tính năng này, nên hệ thống cũ vẫn chạy y như cũ.
        _DEM = (frozenset(), ())
        return _DEM

    tat: set[str] = set()
    plugin: list[BanMoTa] = []
    for r in rows:
        ten = r["ten"]
        bat = bool(r["bat"])
        tho = r["ban_mo_ta"]
        if tho is None:
            if not bat:
                tat.add(ten)
            continue
        if not bat:
            continue
        if isinstance(tho, str):
            tho = json.loads(tho)
        try:
            plugin.append(doc_ban_mo_ta(tho))
        except LoiBanMoTa:
            # Một bản mô tả hỏng KHÔNG được làm chết cả agent. Bỏ qua đúng
            # plugin đó và đi tiếp — nhưng bỏ qua trong im lặng thì không ai
            # biết công cụ đã biến mất, nên ghi nhật ký thành sự kiện.
            await _ghi_nhat_ky_plugin_hong(ten)

    _DEM = (frozenset(tat), tuple(plugin))
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
    tat, plugin = await _doc()
    ra = [t for t in tat_ca if t["name"] not in tat]
    ra.extend(thanh_cong_cu(bm) for bm in plugin)
    return ra


async def dang_tat(ten: str) -> bool:
    """Kỹ năng này đang bị tắt? Dùng ở chốt thứ hai trong `run_tool`."""
    if ten in KHONG_TAT_DUOC:
        return False
    tat, plugin = await _doc()
    if ten in tat:
        return True
    # Một plugin đã xoá hoặc đã tắt vẫn có thể bị model gọi, vì lược đồ của
    # nó còn nằm trong lịch sử hội thoại của lượt trước.
    if ten not in ten_ky_nang_co_san():
        return not any(bm.ten == ten for bm in plugin)
    return False


async def tim_plugin(ten: str) -> BanMoTa | None:
    _, plugin = await _doc()
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


async def luu_plugin(tho: dict, *, boi: str = "staff") -> BanMoTa:
    """Kiểm rồi lưu một plugin. Bản mô tả sai thì không có gì được ghi."""
    bm = doc_ban_mo_ta(tho)

    # Trần số plugin kiểm ở đây chứ không ở `doc_ban_mo_ta`: bộ kiểm ấy là
    # hàm thuần, không biết trong CSDL đang có bao nhiêu dòng.
    _, dang_co = await _doc()
    if bm.ten not in {p.ten for p in dang_co} and len(dang_co) >= PLUGIN_TOI_DA:
        raise LoiBanMoTa(
            f"Đã đủ {PLUGIN_TOI_DA} plugin đang bật. Mỗi công cụ thêm vào là "
            "thêm lược đồ trong MỌI lời gọi model — tắt bớt cái không dùng."
        )

    await db.execute(
        """
        INSERT INTO ky_nang_cai_dat (ten, bat, ban_mo_ta, tao_boi)
        VALUES ($1, TRUE, $2::jsonb, $3)
        ON CONFLICT (ten) DO UPDATE
            SET ban_mo_ta = EXCLUDED.ban_mo_ta, bat = TRUE, sua_luc = now()
        """,
        bm.ten,
        json.dumps(
            {
                "ten": bm.ten, "mo_ta": bm.mo_ta, "loai": bm.loai,
                "tham_so": [
                    {"ten": t.ten, "mo_ta": t.mo_ta, "bat_buoc": t.bat_buoc}
                    for t in bm.tham_so
                ],
                "cau_hinh": bm.cau_hinh,
            },
            ensure_ascii=False,
        ),
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
    trang_thai = await db.execute(
        "DELETE FROM ky_nang_cai_dat WHERE ten = $1 AND ban_mo_ta IS NOT NULL", ten
    )
    so_dong = int(str(trang_thai).rsplit(" ", 1)[-1] or 0)
    if so_dong:
        await db.log_event("ky_nang.plugin_xoa", actor=boi, ten=ten)
        xoa_dem()
    return so_dong > 0


async def liet_ke() -> dict:
    """Toàn cảnh cho dashboard: kỹ năng có sẵn + plugin, kèm trạng thái."""
    tat, plugin = await _doc()
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
            }
            for k in SO_DANG_KY
        ],
        "plugin": [
            {
                "ten": p.ten,
                "loai": p.loai,
                "mo_ta": p.mo_ta,
                "tham_so": [t.ten for t in p.tham_so],
                "bat": True,
            }
            for p in plugin
        ],
        "plugin_toi_da": PLUGIN_TOI_DA,
    }
