"""
Vòng làm mới 6 giây không được xoá chữ nhân viên đang gõ, và chỉ có MỘT
chỗ đổi màn.

Hai ràng buộc khác nhau, cùng một gốc: `setInterval(refresh, 6000)` gọi lại
hàm nạp của màn đang mở, và hàm nạp thường dựng lại DOM bằng `innerHTML`.

ĐO ĐƯỢC 22.09.2026 — `loadContactDetail` dựng lại cả panel Customer 360 mỗi
6 giây, trong đó có ô ghi chú bàn giao `maxlength="5000"`. Người trực gõ dở,
sáu giây sau ô trống trơn: không lỗi, không toast, không nhật ký. Đúng loại
hỏng im lặng mà CLAUDE.md xếp nguy hiểm nhất.

Điều đáng nói là repo đã giải đúng bài này ở ba chỗ khác — ô sửa tin nhắn
(`state.suaText`), ô Sức khoẻ kênh (`state.sucKhoeKenh`), ô tick chọn khách
(`state.khachDaChon`) — và bỏ sót đúng cái panel có ô dài nhất. Nên test này
canh TOÀN BỘ các hàm chạy định kỳ, không chỉ cái vừa vá: chỗ tiếp theo sẽ
đỏ ngay lúc viết, không phải lúc khách mất bàn giao ca.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parent.parent
APP_JS = GOC / "dashboard" / "app.js"
JS = APP_JS.read_text(encoding="utf-8")
DONG = JS.splitlines()

O_NHAP = re.compile(r"<(input|textarea|select)\b", re.I)

# Dấu hiệu hàm CÓ giữ trạng thái người dùng qua lần vẽ lại.
DAU_HIEU_GIU = (
    "_luuDangGo",
    "_traDangGo",
    "state.suaText",
    "state.sucKhoeKenh",
    "state.khachDaChon",
    "document.activeElement",
)

# Hàm dựng lại ô nhập nhưng KHÔNG cần giữ, kèm lý do. Thêm vào đây là một
# quyết định phải giải thích được, không phải chỗ để dập tắt test.
MIEN_TRU: dict[str, str] = {
    "loadTamNhin":
        "chỉ vẽ radio lấy trạng thái từ máy chủ; đổi là lưu ngay, và "
        "listener gắn trên #tamnhin nên sống ngoài khối bị dựng lại",
}


def _bo_chu_thich(src: str) -> str:
    """
    Gỡ chú thích trước khi soi.

    ĐO ĐƯỢC ngay khi viết test này: thử phá mã bằng cách comment dòng
    `_traDangGo(oGoc, dangGo);` thì TEST VẪN XANH — chuỗi vẫn nằm đó, chỉ
    là sau dấu `//`. Một bộ đo khớp cả mã đã tắt là bộ đo xanh giả, và xanh
    giả thì không ai đi kiểm lại.
    """
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"(?m)//.*$", " ", src)


def _than_ham(ten: str) -> str | None:
    """Cắt thân một hàm khai ở cột 0 (mã này viết hàm ở cấp ngoài cùng)."""
    bien = [
        (i, m.group(1))
        for i, l in enumerate(DONG)
        if (m := re.match(r"(?:async )?function ([A-Za-z0-9_]+)\(", l))
    ]
    for k, (i, t) in enumerate(bien):
        if t == ten:
            het = bien[k + 1][0] if k + 1 < len(bien) else len(DONG)
            return _bo_chu_thich("\n".join(DONG[i:het]))
    return None


def _ham_chay_dinh_ky() -> set[str]:
    """Hàm nào bị `refresh()` gọi lại mỗi 6 giây."""
    m = re.search(r"async function refresh\(\)\s*\{(.*?)\n\}", JS, re.S)
    assert m, "không tìm thấy refresh() — bộ kiểm này bám vào nó"
    ten = set(re.findall(r"\b(load[A-Za-z0-9_]+|fill[A-Za-z0-9_]+)\(", m.group(1)))
    # loadContacts() gọi tiếp loadContactDetail() nên cái sau cũng định kỳ.
    ten.add("loadContactDetail")
    return ten


def test_refresh_van_la_vong_sau_giay():
    """Neo của cả file: đổi chu kỳ thì đọc lại test này, đừng sửa số cho xanh."""
    assert re.search(r"setInterval\(refresh,\s*6000\)", JS), (
        "không còn vòng làm mới 6 giây — nếu cố ý bỏ, sửa cả tài liệu và "
        "test này; nếu vô ý, panel sẽ ngừng tự cập nhật"
    )


def test_moi_ham_chay_dinh_ky_deu_giu_chu_dang_go():
    hong = []
    for ten in sorted(_ham_chay_dinh_ky()):
        than = _than_ham(ten)
        if than is None or ".innerHTML" not in than or not O_NHAP.search(than):
            continue
        if ten in MIEN_TRU or any(d in than for d in DAU_HIEU_GIU):
            continue
        hong.append(ten)

    assert not hong, (
        "Hàm chạy lại mỗi 6 giây mà dựng lại ô nhập, không giữ chữ đang gõ: "
        + ", ".join(hong)
        + ".\nGọi _luuDangGo() trước khi gán innerHTML và _traDangGo() ngay "
        "sau, như loadContactDetail; hoặc khai vào MIEN_TRU KÈM LÝ DO."
    )


def test_panel_khach_giu_chu_dung_thu_tu():
    """
    Có gọi thôi chưa đủ — phải lưu TRƯỚC và trả SAU.
    Gọi ngược thứ tự thì vẫn xanh ở test trên mà chữ vẫn mất.
    """
    than = _than_ham("loadContactDetail")
    assert than, "không tìm thấy loadContactDetail"
    luu = than.find("_luuDangGo(")
    # Phải là chỗ vẽ CHÍNH. Nhánh lỗi ở đầu hàm cũng gán innerHTML
    # ($("#contactdetail").innerHTML = "<p …lỗi…>") và bắt nhầm vào đó thì
    # test so sai thứ tự rồi đỏ oan.
    ve = than.find("oGoc.innerHTML =")
    tra = than.find("_traDangGo(")
    assert -1 not in (luu, ve, tra), (
        "thiếu một trong ba mốc lưu/vẽ/trả — chỗ vẽ chính phải gán qua "
        "biến `oGoc` để phân biệt với nhánh lỗi ở đầu hàm"
    )
    assert luu < ve < tra, (
        "phải theo đúng thứ tự: _luuDangGo() -> gán innerHTML -> _traDangGo()"
    )


def test_chi_giu_lai_o_nguoi_dung_da_sua():
    """
    Giữ TẤT CẢ các ô là chữa lỗi im lặng bằng lỗi im lặng tệ hơn: đồng
    nghiệp vừa đổi trường tuỳ biến ở máy khác sẽ bị giá trị cũ trên màn này
    đè ngược lại, và không ai biết.
    """
    than = _than_ham("_luuDangGo")
    assert than, "không tìm thấy _luuDangGo"
    assert "_oDaSua(" in than, (
        "_luuDangGo phải lọc qua _oDaSua, nếu không nó đè dữ liệu mới của "
        "máy chủ bằng giá trị cũ đang hiện trên màn"
    )
    sua = _than_ham("_oDaSua")
    assert sua and "defaultValue" in sua and "defaultChecked" in sua, (
        "_oDaSua phải so với defaultValue/defaultChecked — đó chính là bản "
        "máy chủ vừa dựng, nên lệch nghĩa là người dùng đã gõ"
    )


def test_chi_mot_cho_doi_man():
    """
    ĐO ĐƯỢC 22.09.2026: `doiMan()` tự ghi là "MỘT chỗ đổi màn", nhưng đúng
    logic ấy bị chép ở BỐN chỗ khác, và mỗi bản chép gọi một hàm nạp khác
    nhau — `refresh()`, `loadContacts()`, `loadConversations()`. Hệ quả đo
    được: mở hồ sơ khách từ hội thoại thì thiếu `loadTruongKhach()`, nên
    `oTruongKhach()` thấy danh sách rỗng và `return ""` — toàn bộ trường
    tuỳ biến biến mất không một lời báo.

    Nguy hiểm dài hạn lớn hơn: thêm bất kỳ chốt nào vào `doiMan` (quyền,
    mức tầm nhìn, nhật ký) thì các bản chép đi vòng qua chốt ấy.
    """
    cho = [
        i + 1
        for i, l in enumerate(DONG)
        if 'rail__item").forEach' in l and "classList.toggle" in l
    ]
    assert len(cho) == 1, (
        f"logic đổi màn xuất hiện ở {len(cho)} chỗ (dòng {cho}) — phải gọi "
        "doiMan(ten) thay vì chép lại, nếu không mọi chốt thêm vào doiMan "
        "đều bị đi vòng"
    )
    trong_doi_man = _than_ham("doiMan")
    assert trong_doi_man and 'rail__item").forEach' in trong_doi_man, (
        "chỗ duy nhất ấy phải nằm trong doiMan()"
    )


@pytest.mark.parametrize("ten", ["_khoaO", "_oDaSua", "_luuDangGo", "_traDangGo"])
def test_ham_giu_chu_van_con(ten: str):
    """Xoá một trong bốn hàm này là mở lại lỗ, nên đỏ ngay chứ không âm thầm."""
    assert _than_ham(ten), f"thiếu {ten}() — cơ chế giữ chữ đang gõ đã bị gỡ"
