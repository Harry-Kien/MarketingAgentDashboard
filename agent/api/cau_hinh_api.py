"""
API cấu hình agent và xác nhận bảng giá ERP.
"""
from __future__ import annotations


from fastapi import (APIRouter, Depends, HTTPException)

from agent import db, runtime
from agent.config import settings

from .phu_thuoc import (
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Màn Cấu hình Agent
# ---------------------------------------------------------------

# Mô tả cho NGƯỜI VẬN HÀNH đọc trước khi kéo một thanh trượt.
#
# Con số trần trụi không nói được hậu quả: "0.55" không cho biết nâng lên
# thì gì xảy ra. Mỗi thiết lập vì thế đi kèm câu "cao hơn thì…" và "thấp
# hơn thì…" — hai hướng, vì cả hai hướng đều có giá.
_MO_TA_CAU_HINH = {
    "enabled": {
        "nhan": "Agent đang chạy",
        "kieu": "bool",
        "y_nghia": "Công tắc ngắt. Tắt là agent đứng ngoài mọi hội thoại.",
        "tat_thi": "Mọi tin nhắn vào thẳng hàng đợi người. Không mất tin nào.",
    },
    "mode": {
        "nhan": "Chế độ trả lời",
        "kieu": "chon",
        "chon": ["assist", "auto"],
        "y_nghia": "assist = agent soạn, người bấm gửi. auto = agent tự gửi.",
        "tat_thi": "Tuần đầu vận hành thật nên để assist — người đọc được "
                   "từng câu trước khi nó tới khách.",
    },
    "confidence_floor": {
        "nhan": "Ngưỡng độ tin cậy",
        "kieu": "so",
        "min": 0.0, "max": 1.0, "buoc": 0.05,
        "y_nghia": "Dưới ngưỡng này mà công cụ không trả về dữ liệu thật "
                   "thì agent không được phát ngôn — chuyển người.",
        "tat_thi": "Nâng lên: an toàn hơn, nhưng chuyển người nhiều hơn nên "
                   "ca trực nặng hơn. Hạ xuống: agent tự tin hơn, và sai "
                   "nhiều hơn ở đúng những câu nó vốn không chắc.",
    },
    "tran_chi_phi_ngay_usd": {
        "nhan": "Trần chi phí mỗi NGÀY",
        "kieu": "so",
        "min": 0.0, "max": 500.0, "buoc": 1.0,
        "don_vi": "USD · 0 = tắt",
        "y_nghia": "Chạm trần thì MỌI hội thoại chuyển sang người, và hệ "
                   "thống bắn cảnh báo. Đây là hàng rào cuối giữa một sự cố "
                   "kỹ thuật và một hoá đơn thật.",
        "tat_thi": "Trần mỗi hội thoại chỉ chặn được MỘT hội thoại chạy "
                   "loạn. 0,25 USD × 10.000 hội thoại vẫn là 2.500 USD, và "
                   "một bài viral hay một vòng lặp trong adapter kênh đều "
                   "tới đó được. Đặt 0 là bỏ hàng rào ấy.",
    },
    "max_cost_per_conversation": {
        "nhan": "Trần chi phí mỗi hội thoại",
        "kieu": "so",
        "min": 0.01, "max": 5.0, "buoc": 0.01,
        "don_vi": "USD",
        "y_nghia": "Vượt trần thì chuyển người, chưa tốn thêm lời gọi nào.",
        "tat_thi": "Hạ quá thấp thì hội thoại dài bị cắt giữa chừng và "
                   "chuyển người dù agent đang trả lời tốt.",
    },
    "phong_thu_tran_ngay_usd": {
        "nhan": "Trần chi phí phòng thử mỗi NGÀY",
        "kieu": "so",
        "min": 0.0, "max": 50.0, "buoc": 0.5,
        "don_vi": "USD · 0 = tắt",
        "y_nghia": "Chi phí các lượt nhắn thử trên màn Phòng thử. Sổ riêng, "
                   "không cộng vào trần chi phí ngày của khách thật.",
        "tat_thi": "Đặt 0 là một buổi thử có thể tiêu không giới hạn — vẫn bị "
                   "trần ngày chung chặn, nhưng lúc đó là MỌI khách bị chuyển người.",
    },
}


@router.get("/cau-hinh")
async def doc_cau_hinh(_: dict = Depends(can_quyen("cau_hinh.doc"))) -> dict:
    """Cấu hình đang chạy, kèm mặc định và mô tả cho người vận hành."""
    dang_dung = dict(runtime.STATE)
    return {
        "muc": [
            {
                "khoa": k,
                "gia_tri": dang_dung.get(k),
                "mac_dinh": runtime.MAC_DINH.get(k),
                "lech_mac_dinh": dang_dung.get(k) != runtime.MAC_DINH.get(k),
                **mo_ta,
            }
            for k, mo_ta in _MO_TA_CAU_HINH.items()
        ],
        "ben_vung": list(runtime.KHOA_BEN_VUNG),
    }


@router.get("/cau-hinh/lich-su")
async def lich_su_cau_hinh(
    limit: int = 20, _: dict = Depends(can_quyen("cau_hinh.doc"))
) -> list[dict]:
    """
    Ai đổi gì, lúc nào.

    Cấu hình đổi được mà không truy được ai đổi thì lúc có sự cố không dựng
    lại được chuyện gì đã xảy ra — và đó đúng là lúc người ta cần biết.
    """
    rows = await db.fetch(
        "SELECT actor, detail, created_at FROM events "
        "WHERE kind IN ('runtime.update', 'runtime.dat_lai_mac_dinh') "
        f"ORDER BY created_at DESC LIMIT {max(1, min(int(limit), 100))}"
    )
    return [
        {"boi": r["actor"], "chi_tiet": r["detail"],
         "luc": r["created_at"].isoformat()}
        for r in rows
    ]


@router.post("/cau-hinh/mac-dinh")
async def dat_lai_cau_hinh(nguoi: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict:
    """Quay về mặc định trong `.env`. Xoá hẳn phần đã lưu."""
    return await runtime.dat_lai_mac_dinh(boi=nguoi["ten_dang_nhap"])


# ---------------------------------------------------------------
#  Xác nhận bảng giá — việc chỉ con người làm được
# ---------------------------------------------------------------

@router.get("/erp/xac-nhan-bang-gia")
async def doc_xac_nhan_bang_gia(_: dict = Depends(can_quyen("catalog.duyet"))) -> dict:
    from agent.erp import xac_nhan

    return {"xac_nhan": await xac_nhan.doc(),
            "dang_dung": settings.erp_pricelist or ""}


@router.post("/erp/xac-nhan-bang-gia")
async def ghi_xac_nhan_bang_gia(nguoi: dict = Depends(can_quyen("catalog.duyet"))) -> dict:
    """
    Xác nhận bảng giá ĐANG DÙNG là giá bán lẻ.

    Không nhận tên bảng giá từ thân request. Lấy thẳng từ cấu hình đang
    chạy: cho gửi tên vào là mở đường xác nhận một bảng giá khác với bảng
    hệ thống thật sự đang dùng — và xác nhận ấy sẽ trông hợp lệ.
    """
    from agent.erp import xac_nhan

    try:
        return await xac_nhan.ghi(settings.erp_pricelist,
                                  boi=nguoi["ten_dang_nhap"])
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.delete("/erp/xac-nhan-bang-gia")
async def go_xac_nhan_bang_gia(nguoi: dict = Depends(can_quyen("catalog.duyet"))) -> dict:
    from agent.erp import xac_nhan

    return {"da_go": await xac_nhan.go(boi=nguoi["ten_dang_nhap"])}
