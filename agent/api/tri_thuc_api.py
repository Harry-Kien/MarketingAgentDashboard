"""
API kho tri thức: liệt kê, thêm, xoá, thử truy vấn.
"""
from __future__ import annotations

import uuid

from fastapi import (APIRouter, Depends)
from pydantic import BaseModel, Field

from agent import db
from agent.core import rag

from .phu_thuoc import (
    can_quyen,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------
#  Cơ sở tri thức
# ---------------------------------------------------------------

@router.get("/knowledge")
async def list_documents(_quyen: dict = Depends(can_quyen("cau_hinh.doc"))) -> list[dict]:
    rows = await db.fetch(
        "SELECT id, title, source, chunk_count, created_at "
        "FROM documents ORDER BY created_at DESC"
    )
    return [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "source": r["source"],
            "chunks": r["chunk_count"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


class DocBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=20)


@router.post("/knowledge")
async def add_document(body: DocBody, _quyen: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict:
    """
    Nạp một tài liệu từ ô "Nạp tài liệu" trên dashboard.

    `source` PHẢI DUY NHẤT THEO TỪNG TÀI LIỆU
    -----------------------------------------
    Bản trước truyền cứng `"dashboard"` cho mọi tài liệu. `rag.ingest` xoá
    bản cũ THEO `source` trước khi ghi — đúng, vì nạp lại cùng một tệp
    không được tạo bản thứ hai.

    Nhưng khi mọi tài liệu chung một `source`, quy tắc ấy nghĩa là: nạp tài
    liệu thứ hai XOÁ MẤT tài liệu thứ nhất. Nhân viên dán năm chính sách
    vào ô này, bấm năm lần, và kho còn đúng một cái — cái cuối.

    Không có lỗi, không dòng nhật ký nào. Chỉ là agent trả lời "chưa có
    thông tin" cho bốn chính sách mà người ta tin là đã nạp rồi. Đo được
    bằng hai lời gọi liên tiếp.

    Lấy tiêu đề làm `source` giữ được cả hai tính chất: tài liệu khác tên
    thì cùng tồn tại, còn nạp lại CÙNG một tên thì vẫn thay bản cũ.
    """
    n = await rag.ingest(body.title, f"dashboard:{body.title}", body.text)
    return {"ok": True, "chunks": n}


@router.delete("/knowledge/{doc_id}")
async def delete_document(doc_id: str, _quyen: dict = Depends(can_quyen("cau_hinh.sua"))) -> dict:
    await db.execute("DELETE FROM documents WHERE id = $1", uuid.UUID(doc_id))
    return {"ok": True}


class ProbeBody(BaseModel):
    question: str = Field(min_length=2)


@router.post("/knowledge/probe")
async def probe(body: ProbeBody, _quyen: dict = Depends(can_quyen("cau_hinh.doc"))) -> dict:
    """Thử truy vấn RAG mà không tốn một lượt gọi model."""
    hits = await rag.retrieve(body.question, k=5)
    return {
        "hits": [
            {"doc": h.doc_title, "score": round(h.score, 4), "excerpt": h.content[:280]}
            for h in hits
        ]
    }
