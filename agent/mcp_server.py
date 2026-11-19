"""
Máy chủ MCP — mở hệ thống này ra cho ứng dụng ngoài.

Ý NGHĨA
-------
Từ trước tới giờ, luồng đi một chiều: agent gọi công cụ nghiệp vụ. Lớp này
đảo chiều — biến chính hệ thống thành công cụ mà ứng dụng khác gọi vào.

Nghĩa là Claude Desktop, Claude Code, hay bất cứ ứng dụng nào nói được
Model Context Protocol đều có thể:

    "Còn bao nhiêu sữa rửa mặt cho da dầu?"
    "Đơn AS20260818 đang tới đâu rồi?"
    "Câu trả lời này có dính cụm cấm quảng cáo mỹ phẩm không?"

mà không cần biết gì về FastAPI, Postgres hay Vertex bên trong.

Với doanh nghiệp, đây là điểm khác biệt giữa MỘT CÔNG CỤ và MỘT NỀN TẢNG:
nhân viên chăm sóc khách dùng dashboard, quản lý hỏi qua Claude Desktop,
mà cả hai nhìn cùng một kho dữ liệu, cùng một luật tuân thủ.

Công cụ soạn bài, xếp hàng bài đăng và xem hiệu quả bài đã GỠ ngày
19.11.2026 cùng tính năng đăng bài — hệ thống chỉ còn làm chăm sóc khách.

RANH GIỚI AN TOÀN
-----------------
Công cụ ở đây chia hai loại và KHÔNG được lẫn:

  ĐỌC   — tra sản phẩm, tra đơn, tra tồn kho, tìm trong kho tri thức,
          soi cụm cấm quảng cáo. An toàn, cho gọi thoải mái.
  GHI   — KHÔNG CÓ. Máy chủ MCP không có công cụ nào chốt đơn hay gửi
          tin cho khách.

Lý do: MCP client là một model khác, chạy ngoài tầm kiểm soát của hệ thống
này. Nó không đi qua chốt tuân thủ trong `agent/core/agent.py`, không có
trần chi phí, không có lưới an toàn chuyển người. Cho nó quyền nhắn tin
cho khách hay chốt đơn là giao chìa khoá cho một người lạ.

CHẠY
----
    python -m agent.mcp_server              # stdio, cho Claude Desktop
    python -m agent.mcp_server --http       # HTTP, cho client từ xa

Cấu hình Claude Desktop: xem docs/mcp.md
"""
from __future__ import annotations

import json
import sys

from mcp.server.mcpserver import MCPServer

from agent import db
from agent.config import ROOT
from agent.core import rag, tools
from agent.core.cham_mot_luot import tu_cam_hai_dang

mcp = MCPServer(
    name="aurora-marketing-agent",
    title="Marketing Agent — Aurora Skin",
    version="1.0.0",
    instructions=(
        "Công cụ nghiệp vụ của hệ thống Marketing Agent cho thương hiệu mỹ "
        "phẩm Aurora Skin.\n\n"
        "QUAN TRỌNG: giá, tồn kho, thành phần và tình trạng đơn hàng CHỈ "
        "được nói theo đúng thứ công cụ trả về. Không suy đoán, không ước "
        "lượng.\n\n"
        "Khi soạn câu trả lời cho khách, tuyệt đối không dùng cách nói mang "
        "tính điều trị (trị mụn, đặc trị, chữa, trị nám, xoá nhăn, hết mụn, "
        "cam kết khỏi) — mỹ phẩm không phải thuốc, theo Thông tư "
        "06/2011/TT-BYT và Nghị định 181/2013.\n\n"
        "Công cụ ở đây chỉ ĐỌC: không chốt đơn, không nhắn tin cho khách."
    ),
)

_da_mo_db = False


async def _bao_dam_db() -> None:
    """Mở kết nối CSDL lần đầu cần tới. Client MCP không có vòng đời app."""
    global _da_mo_db
    if not _da_mo_db:
        await db.init_db()
        _da_mo_db = True


# =====================================================================
#  ĐỌC
# =====================================================================

@mcp.tool()
async def tra_cuu_san_pham(ten_san_pham: str) -> dict:
    """
    Tra giá, dung tích, tồn kho, thành phần của MỘT sản phẩm Aurora Skin.

    Dùng khi đã biết tên hoặc mã sản phẩm. Chưa biết mua gì thì dùng
    `goi_y_san_pham`.

    Tên mơ hồ khớp nhiều sản phẩm thì trả `tim_thay: false` kèm danh sách
    ứng viên — hỏi lại cho rõ, tuyệt đối không đoán.
    """
    return await tools.run_tool("tra_cuu_san_pham", {"ten_san_pham": ten_san_pham})


@mcp.tool()
async def goi_y_san_pham(
    loai_da: str = "", nhu_cau: str = "", nhom: str = "", gia_toi_da: int = 0
) -> dict:
    """
    Gợi ý sản phẩm theo loại da, vấn đề da, nhóm hàng hoặc ngân sách.

    loai_da: da dầu / da khô / da hỗn hợp / da nhạy cảm / da thường
    nhu_cau: điều khách bận tâm, ví dụ "kiềm dầu", "lỗ chân lông to"
    nhom:    Làm sạch / Cân bằng / Tinh chất chuyên sâu / Dưỡng ẩm /
             Chống nắng / Mặt nạ / Combo
    gia_toi_da: giới hạn giá tính bằng đồng, 0 là không giới hạn

    Tên tham số phải khớp ĐÚNG với `agent/core/tools.py`. Đặt sai tên thì
    bộ lọc bỏ qua trong im lặng và trả về cả danh mục hoặc rỗng — sai mà
    không có lỗi nào báo, loại lỗi khó thấy nhất.
    """
    return await tools.run_tool("goi_y_san_pham", {
        "loai_da": loai_da, "nhu_cau": nhu_cau,
        "nhom": nhom, "gia_toi_da": gia_toi_da,
    })


@mcp.tool()
async def tra_cuu_don_hang(ma_don: str) -> dict:
    """Tra tình trạng một đơn hàng theo mã, ví dụ AS20260818."""
    return await tools.run_tool("tra_cuu_don_hang", {"ma_don": ma_don})


@mcp.tool()
async def tim_trong_kho_tri_thuc(cau_hoi: str, so_doan: int = 4) -> dict:
    """
    Tìm trong tài liệu nội bộ: chính sách vận chuyển, đổi trả, thanh toán,
    hướng dẫn chọn sản phẩm theo loại da, routine, cách phân biệt hàng thật.

    Trả về các đoạn kèm điểm khớp và tên tài liệu để trích nguồn. Không tìm
    thấy đoạn nào là tài liệu chưa có thông tin đó — nói thẳng ra, đừng suy
    đoán thay.
    """
    await _bao_dam_db()
    passages = await rag.retrieve(cau_hoi, k=max(1, min(so_doan, 8)))
    return {
        "so_doan": len(passages),
        "doan": [
            {
                "tai_lieu": p.doc_title,
                "diem": round(p.score, 3),
                "noi_dung": p.content,
                "phien_ban": p.version,
                "version_id": str(p.version_id) if p.version_id else None,
                "chunk_id": str(p.chunk_id) if p.chunk_id else None,
            }
            for p in passages
        ],
    }


@mcp.tool()
async def ton_kho_realtime(ma_san_pham: str) -> dict:
    """
    Số lượng BÁN ĐƯỢC của một mã sản phẩm, hỏi thẳng kho/ERP ngay lúc này.

    Khác `tra_cuu_san_pham`: hàm kia đọc danh mục đã cache, đủ dùng để tư
    vấn. Hàm này bỏ qua cache, dùng khi sắp quyết định có bán hay không.

    `ban_duoc` là hàng CÒN BÁN ĐƯỢC, đã trừ phần các đơn khác giữ chỗ —
    không phải tổng tồn trong kho.

    Chưa tra được thì trả `tra_duoc: false` và KHÔNG có `ban_duoc`. Đừng
    hiểu đó là hết hàng, và đừng nói với ai một con số nào.
    """
    from agent.erp import nha_may as _nha_may

    cong = _nha_may.cong()
    t = await cong.ton_kho(ma_san_pham, bo_qua_cache=True)
    if t is None:
        # Trả 0 ở đây nghĩa là HẾT HÀNG — một câu trả lời sai khác hẳn
        # "chưa tra được", mà client không có cách nào phân biệt.
        return {
            "tra_duoc": False,
            "ma": ma_san_pham,
            "ghi_chu": (
                "Chưa tra được tồn kho. KHÔNG được hiểu là hết hàng, và "
                "không được nói bất kỳ con số nào cho khách."
            ),
        }
    return {
        "tra_duoc": True,
        "ma": ma_san_pham,
        "ban_duoc": t.ban_duoc,
        "ma_kho": t.ma_kho,
    }


@mcp.tool()
async def suc_khoe_erp() -> dict:
    """
    Kho/ERP đang nối tới là nguồn nào, còn sống không, mạch có đang mở không.

    `mach_mo: true` nghĩa là cổng đã ngắt mạch sau nhiều lần gọi hỏng — mọi
    câu hỏi về giá và tồn kho sẽ trả "không biết" cho tới khi mạch đóng lại.
    """
    from agent.erp import nha_may as _nha_may

    cong = _nha_may.cong()
    return {**cong.trang_thai(), "song": await cong.suc_khoe()}


@mcp.tool()
async def kiem_tra_tuan_thu_quang_cao(noi_dung: str) -> dict:
    """
    Soi một đoạn nội dung xem có vi phạm quy định quảng cáo mỹ phẩm không.

    Dùng được cho câu trả lời do người viết tay, không chỉ câu agent soạn.
    Trả về danh sách cụm vi phạm; rỗng nghĩa là sạch.

    Đi qua ĐÚNG bộ soi mà mẫu trả lời nhanh và bản nháp người sửa dùng
    (`cham_mot_luot.tu_cam_hai_dang`). Trước 19.11.2026 công cụ này mượn bộ
    soi của tính năng đăng bài; gỡ tính năng ấy thì quy về một bộ soi, vì
    hai danh sách cụm cấm sớm muộn lệch — một đường chặn, đường kia lọt.
    """
    vi_pham = tu_cam_hai_dang(noi_dung)
    return {
        "hop_le": not vi_pham,
        "cum_vi_pham": vi_pham,
        "can_cu": "Thông tư 06/2011/TT-BYT, Nghị định 181/2013",
        "goi_y": (
            "Thay cách nói điều trị bằng cách nói hỗ trợ: 'hỗ trợ giảm dầu', "
            "'giúp da mềm mại hơn', 'hỗ trợ làm đều màu da'."
        ) if vi_pham else "",
    }


# =====================================================================
#  Tài nguyên — dữ liệu tĩnh client đọc trực tiếp
# =====================================================================

@mcp.resource("aurora://danh-muc")
def danh_muc() -> str:
    """Toàn bộ danh mục sản phẩm Aurora Skin dưới dạng JSON."""
    return (ROOT / "data" / "catalog.json").read_text(encoding="utf-8")


@mcp.resource("aurora://huong-dan-viet")
def huong_dan_viet() -> str:
    """Giới hạn pháp lý khi viết nội dung quảng cáo mỹ phẩm tại Việt Nam."""
    return json.dumps({
        "can_cu": ["Thông tư 06/2011/TT-BYT", "Nghị định 181/2013/NĐ-CP"],
        "cam": ["trị mụn", "đặc trị", "chữa", "trị nám", "xoá nhăn",
                "hết mụn", "tái tạo da", "trắng da cấp tốc", "thay thế thuốc",
                "cam kết khỏi", "hiệu quả 100%", "số 1 Việt Nam"],
        "duoc": ["hỗ trợ giảm dầu", "giúp da mềm mại hơn",
                 "hỗ trợ làm đều màu da", "cấp ẩm", "làm dịu da",
                 "hỗ trợ cải thiện kết cấu da"],
        "nguyen_tac": [
            "Không hứa kết quả theo mốc thời gian.",
            "Không cam kết hiệu quả cho từng cá nhân.",
            "Không so sánh với thuốc hoặc với thương hiệu khác.",
        ],
    }, ensure_ascii=False, indent=1)


def main() -> None:
    if "--http" in sys.argv:
        # HTTP cho client từ xa. Chỉ nghe 127.0.0.1: máy chủ này KHÔNG có
        # xác thực, mở ra mạng là mở luôn dữ liệu khách hàng.
        #
        # mcp 2.0: host/port là tham số của `run()`, không còn ở `settings`
        # — gán vào `settings` là ValueError ngay lúc khởi động.
        mcp.run(transport="streamable-http", host="127.0.0.1", port=8765)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
