"""
Trường thông tin khách do người vận hành tự thêm.

VÌ SAO KIỂM KIỂU Ở ĐÂY CHỨ KHÔNG CHỈ Ở GIAO DIỆN
-------------------------------------------------
Dashboard vẽ ô nhập theo kiểu: `so` ra ô số, `chon` ra danh sách. Nếu chỉ
dựa vào đó thì mọi thứ trông đúng — cho tới khi có ai gọi API trực tiếp,
hoặc dashboard được sửa, hoặc một bản cũ còn mở trong tab nào đó.

Khi ấy `so` nhận một chuỗi, `chon` nhận một giá trị không có trong danh
sách, và nó LƯU ĐƯỢC. Không lỗi. Màn hình sau đó hiện một ô rỗng, hoặc một
giá trị lạ, và không ai truy được nó vào từ đâu.

Đây đúng nguyên tắc của repo: ràng buộc nằm trong MÃ, không nằm trong giao
diện — cùng lý lẽ với sáu lớp lưới trong `agent/core/agent.py`.

VÌ SAO `bat_buoc` CHỈ ÉP LÚC GHI
---------------------------------
Thêm một trường bắt buộc hôm nay không làm cho 400 hồ sơ khách cũ trở nên
sai. Ép lúc ĐỌC là màn Khách hàng vỡ với toàn bộ dữ liệu có sẵn; ép lúc ghi
là từ nay ai sửa hồ sơ thì phải điền nốt.
"""
from __future__ import annotations

from datetime import date
from typing import Any

KIEU = ("chu", "so", "ngay", "chon", "nhieu_chon", "dung_sai")

NHAN_KIEU = {
    "chu": "Chữ",
    "so": "Số",
    "ngay": "Ngày",
    "chon": "Chọn một",
    "nhieu_chon": "Chọn nhiều",
    "dung_sai": "Đúng / sai",
}

MA_TOI_DA = 40
SO_TRUONG_TOI_DA = 40


class TruongHong(ValueError):
    """Giá trị không hợp với định nghĩa trường."""


def kiem_ma(ma: str) -> str:
    """
    `ma` là KHOÁ trong `contacts.profile`, nên nó phải là định danh an toàn.

    Không chấp nhận dấu tiếng Việt, khoảng trắng, dấu chấm: khoá JSONB có
    dấu chấm làm mọi truy vấn đường dẫn (`profile -> 'a.b'`) trở nên mơ hồ,
    và người viết truy vấn sau này sẽ không đoán ra vì sao nó không khớp.
    """
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]{0,%d}" % (MA_TOI_DA - 1), ma or ""):
        raise TruongHong(
            f"Mã trường không hợp lệ: {ma!r}. Chỉ dùng chữ thường không dấu, "
            f"số và gạch dưới; bắt đầu bằng chữ; tối đa {MA_TOI_DA} ký tự."
        )
    return ma


def _kiem_ngay(gia_tri: Any, nhan: str) -> str:
    if not isinstance(gia_tri, str):
        raise TruongHong(f"“{nhan}” phải là ngày dạng YYYY-MM-DD.")
    try:
        date.fromisoformat(gia_tri)
    except ValueError as exc:
        raise TruongHong(
            f"“{nhan}” không phải ngày hợp lệ: {gia_tri!r}. Dùng YYYY-MM-DD."
        ) from exc
    return gia_tri


def kiem_gia_tri(dinh_nghia: dict, gia_tri: Any) -> Any:
    """
    Ép một giá trị về đúng kiểu của trường, hoặc NÉM.

    Trả về giá trị đã chuẩn hoá — không trả `None` khi hỏng: trả `None` là
    lưu một ô rỗng thay cho dữ liệu người dùng vừa gõ, và họ không biết.
    """
    kieu = dinh_nghia["kieu"]
    nhan = dinh_nghia.get("nhan") or dinh_nghia["ma"]

    if gia_tri is None or gia_tri == "":
        if dinh_nghia.get("bat_buoc"):
            raise TruongHong(f"“{nhan}” là trường bắt buộc.")
        return None

    if kieu == "chu":
        if not isinstance(gia_tri, str):
            raise TruongHong(f"“{nhan}” phải là chữ.")
        if len(gia_tri) > 2000:
            raise TruongHong(f"“{nhan}” dài quá 2000 ký tự.")
        return gia_tri.strip()

    if kieu == "so":
        # `bool` là con của `int` trong Python, nên `isinstance(True, int)`
        # là True. Không loại nó ra thì `True` lặng lẽ lưu thành 1 — sai
        # kiểu mà không nổ, và sáu tháng sau có một cột "Tuổi" toàn số 1.
        #
        # Loại ra rồi nó rơi xuống nhánh ép chuỗi, `float("True")` ném, và
        # người gửi nhận 422 nói rõ trường nào. Đó mới là thứ đáng có.
        if isinstance(gia_tri, bool) or not isinstance(gia_tri, (int, float)):
            try:
                return float(str(gia_tri).replace(",", "."))
            except (TypeError, ValueError) as exc:
                raise TruongHong(f"“{nhan}” phải là số.") from exc
        return float(gia_tri)

    if kieu == "ngay":
        return _kiem_ngay(gia_tri, nhan)

    if kieu == "dung_sai":
        if isinstance(gia_tri, bool):
            return gia_tri
        if str(gia_tri).lower() in ("true", "1", "co", "có"):
            return True
        if str(gia_tri).lower() in ("false", "0", "khong", "không"):
            return False
        raise TruongHong(f"“{nhan}” phải là đúng hoặc sai.")

    cho_phep = list(dinh_nghia.get("lua_chon") or [])

    if kieu == "chon":
        if gia_tri not in cho_phep:
            raise TruongHong(
                f"“{nhan}” chỉ nhận: {', '.join(map(str, cho_phep))}. "
                f"Nhận được: {gia_tri!r}")
        return gia_tri

    if kieu == "nhieu_chon":
        if not isinstance(gia_tri, list):
            raise TruongHong(f"“{nhan}” phải là danh sách lựa chọn.")
        la = [g for g in gia_tri if g not in cho_phep]
        if la:
            raise TruongHong(
                f"“{nhan}” có lựa chọn không hợp lệ: "
                f"{', '.join(map(str, la))}")
        # Bỏ trùng nhưng GIỮ THỨ TỰ người dùng chọn: `set` làm thứ tự nhảy
        # mỗi lần tải trang, và người ta tưởng dữ liệu bị đổi.
        da_thay: list[Any] = []
        for g in gia_tri:
            if g not in da_thay:
                da_thay.append(g)
        return da_thay

    raise TruongHong(f"Kiểu trường không biết: {kieu!r}")


def kiem_ho_so(dinh_nghia: list[dict], gui_len: dict[str, Any]) -> dict[str, Any]:
    """
    Kiểm cả cụm giá trị gửi lên, trả về bản đã chuẩn hoá.

    Khoá LẠ thì NÉM chứ không bỏ qua.

    Bỏ qua im lặng là kịch bản tệ nhất ở đây: người vận hành vừa xoá một
    trường, dashboard cũ trong tab kia vẫn gửi khoá cũ lên, máy chủ nuốt, và
    họ thấy "đã lưu" trong khi dữ liệu vừa gõ không đi đâu cả.
    """
    theo_ma = {d["ma"]: d for d in dinh_nghia}
    la = sorted(set(gui_len) - set(theo_ma))
    if la:
        raise TruongHong(
            f"Không có trường: {', '.join(la)}. "
            "Có thể trường vừa bị xoá — tải lại trang.")

    ra: dict[str, Any] = {}
    for ma, d in theo_ma.items():
        if ma not in gui_len:
            continue
        sach = kiem_gia_tri(d, gui_len[ma])
        if sach is not None:
            ra[ma] = sach
    return ra
