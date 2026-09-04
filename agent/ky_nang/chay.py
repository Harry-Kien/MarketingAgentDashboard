"""
Thi hành plugin. Bốn loại, tất cả CHỈ ĐỌC.

Không hàm nào trong tệp này ghi cơ sở dữ liệu, gọi model, tiêu tiền, hay gửi
gì cho khách. Chúng nhận tham số model điền, trả về một dict dữ liệu, và
agent quyết định nói gì — sau khi đi qua đủ sáu lớp lưới.

Ràng buộc "chỉ đọc" được canh bằng test đọc AST của chính tệp này, không
phải bằng lời hứa trong đoạn chú thích này: `tests/test_ky_nang_plugin.py`
bắt mọi lời gọi `db.execute`/`db.fetch`/`llm.` xuất hiện ở đây là đỏ.
"""
from __future__ import annotations


from agent.ky_nang.ban_mo_ta import BanMoTa, bo_dau
from agent.ky_nang.mang import LoiMang, lay


async def chay_plugin(bm: BanMoTa, args: dict) -> dict:
    """
    Chạy một plugin và trả về dict cho agent đọc.

    Mọi nhánh trả về đều có `ghi_chu` nói model phải làm gì tiếp — kể cả
    nhánh hỏng. Trả về dict rỗng thì model tự nghĩ ra đường đi, và đường nó
    hay chọn là đoán bừa. Đây là bài học từ `tim_kien_thuc`.
    """
    if bm.loai == "tra_tai_lieu":
        return await _tra_tai_lieu(bm, args)
    if bm.loai == "tra_bang":
        return _tra_bang(bm, args)
    if bm.loai == "chuyen_chuyen_biet":
        return {
            "can_chuyen_nhan_vien": True,
            "ly_do": bm.cau_hinh["ly_do"],
            "ghi_chu": (
                "Đã chuyển hội thoại cho người. Báo khách là sẽ có người "
                "nhắn lại, KHÔNG tự trả lời tiếp câu vừa rồi."
            ),
        }
    if bm.loai == "goi_api_doc":
        return await _goi_api_doc(bm, args)

    # Không tới được nếu `doc_ban_mo_ta` làm đúng việc. Vẫn để nhánh này,
    # vì thêm loại thứ năm mà quên viết nhánh chạy thì đây là chỗ nó hiện
    # ra — thành câu chuyển người, không thành câu trả lời bịa.
    return {
        "loi": f"Loại plugin {bm.loai!r} chưa có bộ thi hành.",
        "can_chuyen_nhan_vien": True,
    }


def _tham_so_dau(bm: BanMoTa, args: dict) -> str:
    """Giá trị của tham số đầu tiên — hai loại tra cứu đều chỉ dùng một."""
    if not bm.tham_so:
        return ""
    return str(args.get(bm.tham_so[0].ten, "") or "").strip()


async def _tra_tai_lieu(bm: BanMoTa, args: dict) -> dict:
    # Nhập khẩu tại chỗ: `rag` kéo theo thư viện Vertex, và các loại plugin
    # khác không cần tới nó.
    from agent.core import rag

    cau_hoi = _tham_so_dau(bm, args)
    if not cau_hoi:
        return {"tim_thay": False, "ghi_chu": "Thiếu nội dung cần tra."}

    nhom = bo_dau(bm.cau_hinh["nhom_tai_lieu"])
    k = int(bm.cau_hinh.get("k", 4))

    # Lọc SAU khi truy hồi, không lọc trong SQL.
    #
    # Lọc trong SQL thì hai xếp hạng của tìm kiếm lai (vector và từ khoá)
    # được tính trên tập đã cắt, nên điểm RRF lệch so với `tim_kien_thuc`
    # — cùng một câu hỏi, hai công cụ, hai thứ tự khác nhau. Lấy dư rồi cắt
    # thì thứ tự giữ nguyên. Đổi lại là tốn hơn một chút, chấp nhận được.
    doan = await rag.retrieve(cau_hoi, k=k * 3)
    hop = [p for p in doan if nhom in bo_dau(p.doc_title)][:k]

    if not hop:
        return {
            "tim_thay": False,
            "ghi_chu": (
                f"Không có căn cứ trong nhóm tài liệu {bm.cau_hinh['nhom_tai_lieu']!r}. "
                "KHÔNG được đoán. Nói thẳng là chưa có thông tin, hoặc gọi "
                "chuyen_nhan_vien. Đừng tra lại cùng câu hỏi."
            ),
        }
    return {
        "tim_thay": True,
        "doan": [
            {"tai_lieu": p.doc_title, "noi_dung": p.content.strip()[:700],
             "diem": round(p.score, 3)}
            for p in hop
        ],
        "ghi_chu": "Chỉ trả lời dựa trên các đoạn trên. Nêu tên tài liệu khi trích.",
    }


def _tra_bang(bm: BanMoTa, args: dict) -> dict:
    khoa = _tham_so_dau(bm, args)
    if not khoa:
        return {"tim_thay": False, "ghi_chu": "Thiếu khoá cần tra."}

    bang = bm.cau_hinh["bang"]
    can = bo_dau(khoa)

    # Khớp đúng trước, khớp chứa sau. Khách gõ "hà nội" hay "Hà Nội" hay
    # "cửa hàng hà nội" đều phải ra một dòng.
    for k_, v_ in bang.items():
        if bo_dau(k_) == can:
            return {"tim_thay": True, "khoa": k_, "gia_tri": v_}

    gan = [(k_, v_) for k_, v_ in bang.items() if can in bo_dau(k_) or bo_dau(k_) in can]
    if len(gan) == 1:
        return {"tim_thay": True, "khoa": gan[0][0], "gia_tri": gan[0][1]}
    if len(gan) > 1:
        # Nhiều dòng khớp thì HỎI LẠI, không chọn hộ. Chọn dòng đầu là kiểu
        # hỏng im lặng: khách hỏi "chi nhánh Nguyễn Trãi" mà có hai chi
        # nhánh cùng tên đường thì đưa nhầm địa chỉ, và không ai biết.
        return {
            "tim_thay": False,
            "nhieu_ket_qua": [k_ for k_, _ in gan[:5]],
            "ghi_chu": "Khớp nhiều dòng. HỎI LẠI khách muốn dòng nào, đừng tự chọn.",
        }
    return {
        "tim_thay": False,
        "ghi_chu": (
            "Không có dòng nào khớp. KHÔNG được đoán giá trị. Nói là chưa có "
            "thông tin, hoặc gọi chuyen_nhan_vien."
        ),
    }


async def _goi_api_doc(bm: BanMoTa, args: dict) -> dict:
    url = bm.cau_hinh["url"]
    for t in bm.tham_so:
        gt = str(args.get(t.ten, "") or "").strip()
        if not gt and t.bat_buoc:
            return {"tim_thay": False, "ghi_chu": f"Thiếu tham số {t.ten}."}
        # Mã hoá phần trăm mọi giá trị model điền. Không mã hoá thì một giá
        # trị chứa `?` hay `#` viết lại cấu trúc URL — model điền được cả
        # query string mà người vận hành không hề khai.
        from urllib.parse import quote

        url = url.replace("{" + t.ten + "}", quote(gt, safe=""))

    try:
        noi_dung = await lay(url, float(bm.cau_hinh.get("han_giay", 5.0)))
    except LoiMang as exc:
        # Hỏng thì CHUYỂN NGƯỜI, không im lặng bỏ qua. Một API nội bộ chết
        # mà agent vẫn trả lời trơn tru là đúng kiểu xanh giả: khách nhận
        # câu trả lời tự tin dựa trên không có gì.
        return {
            "tim_thay": False,
            "loi": str(exc),
            "can_chuyen_nhan_vien": True,
            "ghi_chu": "Không gọi được hệ thống ngoài. Đã chuyển cho người.",
        }
    return {
        "tim_thay": True,
        "noi_dung": noi_dung,
        "ghi_chu": (
            "Đây là dữ liệu thô từ hệ thống ngoài. Chỉ đọc ra những gì có "
            "trong đó, không suy diễn thêm."
        ),
    }
