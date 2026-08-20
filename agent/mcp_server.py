"""
Máy chủ MCP — mở hệ thống này ra cho ứng dụng ngoài.

Ý NGHĨA
-------
Từ trước tới giờ, luồng đi một chiều: agent gọi công cụ nghiệp vụ. Lớp này
đảo chiều — biến chính hệ thống thành công cụ mà ứng dụng khác gọi vào.

Nghĩa là Claude Desktop, Claude Code, hay bất cứ ứng dụng nào nói được
Model Context Protocol đều có thể:

    "Aurora Skin còn bao nhiêu sữa rửa mặt cho da dầu?"
    "Tuần này bài nào chạy tốt nhất?"
    "Soạn cho tôi một bài TikTok về serum niacinamide."

mà không cần biết gì về FastAPI, Postgres hay Vertex bên trong.

Với doanh nghiệp, đây là điểm khác biệt giữa MỘT CÔNG CỤ và MỘT NỀN TẢNG:
phòng marketing dùng dashboard, phòng kinh doanh hỏi qua Claude Desktop,
mà cả hai nhìn cùng một kho dữ liệu, cùng một luật tuân thủ.

RANH GIỚI AN TOÀN
-----------------
Công cụ ở đây chia hai loại và KHÔNG được lẫn:

  ĐỌC   — tra sản phẩm, tra đơn, xem số liệu, tìm trong kho tri thức.
          An toàn, cho gọi thoải mái.
  GHI   — soạn bài, tạo bài nháp.
          Luôn dừng ở trạng thái `cho_duyet`. Máy chủ MCP KHÔNG có công cụ
          nào đăng bài, chốt đơn hay gửi tin cho khách.

Lý do: MCP client là một model khác, chạy ngoài tầm kiểm soát của hệ thống
này. Nó không đi qua chốt tuân thủ trong `agent/core/agent.py`, không có
trần chi phí, không có lưới an toàn chuyển người. Cho nó quyền nhắn tin
cho khách hay đăng bài lên fanpage là giao chìa khoá cho một người lạ.

CHẠY
----
    python -m agent.mcp_server              # stdio, cho Claude Desktop
    python -m agent.mcp_server --http       # HTTP, cho client từ xa

Cấu hình Claude Desktop: xem docs/mcp.md
"""
from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer

from agent import db
from agent.config import ROOT
from agent.core import rag, tools
from agent.publish import analytics, copywriter
from agent.publish import service as post_service

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
        "Khi viết nội dung quảng cáo, tuyệt đối không dùng cách nói mang "
        "tính điều trị (trị mụn, đặc trị, chữa, trị nám, xoá nhăn, hết mụn, "
        "cam kết khỏi) — mỹ phẩm không phải thuốc, theo Thông tư "
        "06/2011/TT-BYT và Nghị định 181/2013.\n\n"
        "Công cụ ở đây không đăng bài và không nhắn tin cho khách. Bài soạn "
        "ra luôn nằm ở hàng chờ duyệt."
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
            {"tai_lieu": p.doc_title, "diem": round(p.score, 3), "noi_dung": p.content}
            for p in passages
        ],
    }


@mcp.tool()
async def hieu_qua_bai_dang(so_ngay: int = 30) -> dict:
    """
    Số liệu bài đăng mạng xã hội: lượt xem, tương tác theo từng nền tảng,
    và các bài chạy tốt nhất.

    Tỷ lệ tương tác là chỉ số so sánh được giữa các bài; lượt xem tuyệt đối
    thì không, vì phụ thuộc nền tảng và thời điểm.
    """
    await _bao_dam_db()
    tq = await analytics.tong_quan(so_ngay)
    tq["bai_tot_nhat"] = await analytics.bai_tot_nhat()
    return tq


@mcp.tool()
async def danh_sach_bai_dang(trang_thai: str = "", so_luong: int = 20) -> dict:
    """
    Liệt kê bài đăng trong hàng đợi.

    trang_thai: cho_duyet / da_len_lich / dang_dang / da_dang / loi / da_huy
                (để trống là lấy tất cả)
    """
    await _bao_dam_db()
    sql = "SELECT id, tieu_de, noi_dung, kenh, trang_thai, lich_dang, created_at FROM posts "
    args: list[Any] = []
    if trang_thai:
        sql += "WHERE trang_thai = $1 "
        args.append(trang_thai)
    sql += f"ORDER BY created_at DESC LIMIT ${len(args) + 1}"
    args.append(max(1, min(so_luong, 100)))
    rows = await db.fetch(sql, *args)
    for r in rows:
        r["id"] = str(r["id"])
        for k in ("lich_dang", "created_at"):
            if r.get(k):
                r[k] = r[k].isoformat()
    return {"so_bai": len(rows), "bai": rows}


# =====================================================================
#  GHI — chỉ tới mức bản nháp chờ duyệt
# =====================================================================

@mcp.tool()
async def soan_bai_dang(
    kenh: str = "facebook", san_pham: str = "", y_tuong: str = ""
) -> dict:
    """
    Soạn nội dung bài đăng cho một nền tảng. KHÔNG lưu, KHÔNG đăng.

    Nội dung bám vào dữ liệu sản phẩm thật trong danh mục và tự động kiểm
    tuân thủ quảng cáo mỹ phẩm — vi phạm thì viết lại, tối đa 3 lần.

    kenh: facebook / instagram / tiktok / youtube
    san_pham: mã hoặc tên sản phẩm, để trống nếu viết chung
    """
    await _bao_dam_db()
    return await copywriter.soan(kenh=kenh, san_pham=san_pham, y_tuong=y_tuong)


@mcp.tool()
async def dua_bai_vao_hang_doi(
    tieu_de: str, noi_dung: str, kenh: list[str], hashtags: list[str] | None = None
) -> dict:
    """
    Lưu một bài vào hàng đợi ở trạng thái CHỜ DUYỆT.

    Bài KHÔNG được đăng từ đây. Phải có người vào dashboard bấm duyệt thì
    nội dung mới ra công chúng — đây là chốt an toàn, không phải bước thừa:
    theo Nghị định 181/2013, doanh nghiệp chịu trách nhiệm về nội dung
    quảng cáo, không phải công cụ tạo ra nó.
    """
    await _bao_dam_db()
    row = await post_service.tao_bai(
        tieu_de=tieu_de, noi_dung=noi_dung, kenh=kenh,
        hashtags=hashtags, tao_boi="mcp",
    )
    row["id"] = str(row["id"])
    for k in ("lich_dang", "created_at", "updated_at"):
        if row.get(k):
            row[k] = row[k].isoformat()
    row["ghi_chu"] = "Đã vào hàng đợi, trạng thái chờ duyệt. Vào dashboard mục Đăng bài để duyệt."
    return row


@mcp.tool()
async def kiem_tra_tuan_thu_quang_cao(noi_dung: str) -> dict:
    """
    Soi một đoạn nội dung xem có vi phạm quy định quảng cáo mỹ phẩm không.

    Dùng được cho nội dung do người viết tay, không chỉ nội dung máy soạn.
    Trả về danh sách cụm vi phạm; rỗng nghĩa là sạch.
    """
    vi_pham = post_service.kiem_tra_tuan_thu(noi_dung)
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
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = 8765
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
