"""
RAG trên pgvector + Vertex embeddings.

Chỗ để cắm lại RAG pháp lý sẵn có: chỉ cần thay hai hàm `embed()` và
`retrieve()` bằng bản của bạn, giữ nguyên chữ ký. Phần còn lại của hệ thống
chỉ phụ thuộc vào kiểu trả về `Passage`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from agent import db
from agent.config import settings

EMBED_MODEL = "text-multilingual-embedding-002"   # 768 chiều, tốt cho tiếng Việt
EMBED_DIM = 768


@dataclass(slots=True)
class Passage:
    doc_title: str
    content: str
    score: float

    def cite(self) -> str:
        return f"[{self.doc_title}]"


def _embed_sync(texts: list[str], task: str) -> list[list[float]]:
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
    import vertexai

    region = settings.gcp_region if settings.gcp_region != "global" else "us-central1"
    vertexai.init(project=settings.gcp_project_id, location=region)
    model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)
    inputs = [TextEmbeddingInput(t, task) for t in texts]
    return [e.values for e in model.get_embeddings(inputs)]


async def embed(texts: list[str], *, query: bool = False) -> list[list[float]]:
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    return await asyncio.to_thread(_embed_sync, texts, task)


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


async def retrieve(question: str, k: int = 5, min_score: float = 0.35) -> list[Passage]:
    """Lấy các đoạn liên quan. Rỗng = agent KHÔNG được phát ngôn có căn cứ."""
    try:
        qvec = (await embed([question], query=True))[0]
    except Exception:  # noqa: BLE001 — thiếu quyền Vertex thì degrade, đừng sập
        return []

    rows = await db.fetch(
        """
        SELECT d.title AS doc_title,
               c.content,
               1 - (c.embedding <=> $1::vector) AS score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.embedding IS NOT NULL
        ORDER BY c.embedding <=> $1::vector
        LIMIT $2
        """,
        _vec(qvec),
        k,
    )
    return [
        Passage(r["doc_title"], r["content"], float(r["score"]))
        for r in rows
        if float(r["score"]) >= min_score
    ]


def as_context(passages: list[Passage]) -> str:
    """Định dạng ngữ cảnh. Phần này BIẾN ĐỘNG -> phải nằm SAU điểm cache."""
    if not passages:
        return "KHÔNG TÌM THẤY TÀI LIỆU LIÊN QUAN."
    out = ["TÀI LIỆU THAM CHIẾU (chỉ được trả lời dựa trên đây):", ""]
    for i, p in enumerate(passages, 1):
        out.append(f"--- Nguồn {i}: {p.doc_title} (độ khớp {p.score:.2f}) ---")
        out.append(p.content.strip())
        out.append("")
    return "\n".join(out)


# ---------------- Nạp tài liệu ----------------

def chunk_text(text: str, size: int = 900, overlap: int = 150) -> list[str]:
    """Cắt theo đoạn văn, gộp tới ngưỡng size. Giữ ranh giới ngữ nghĩa."""
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= size:
            cur = f"{cur}\n\n{p}" if cur else p
        else:
            if cur:
                chunks.append(cur)
            cur = (cur[-overlap:] + "\n\n" + p) if cur and overlap else p
    if cur:
        chunks.append(cur)
    return chunks or [text[:size]]


async def ingest(title: str, source: str, text: str) -> int:
    """Nạp một tài liệu vào cơ sở tri thức. Trả về số chunk."""
    pieces = chunk_text(text)
    vectors = await embed(pieces)

    doc = await db.fetchrow(
        "INSERT INTO documents (title, source, chunk_count) VALUES ($1,$2,$3) "
        "RETURNING id",
        title,
        source,
        len(pieces),
    )
    doc_id = doc["id"]
    async with db.pool().acquire() as conn:
        await conn.executemany(
            "INSERT INTO chunks (document_id, ord, content, embedding) "
            "VALUES ($1,$2,$3,$4::vector)",
            [(doc_id, i, c, _vec(v)) for i, (c, v) in enumerate(zip(pieces, vectors))],
        )
    return len(pieces)
