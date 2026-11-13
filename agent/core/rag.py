"""
RAG trên pgvector + Vertex embeddings.

Chỗ để cắm lại RAG pháp lý sẵn có: chỉ cần thay hai hàm `embed()` và
`retrieve()` bằng bản của bạn, giữ nguyên chữ ký. Phần còn lại của hệ thống
chỉ phụ thuộc vào kiểu trả về `Passage`.
"""
from __future__ import annotations

import logging
import re

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from agent import db
from agent.config import settings

EMBED_MODEL = "text-multilingual-embedding-002"   # 768 chiều, tốt cho tiếng Việt
EMBED_DIM = 768

# Gemini API (Google AI Studio) không có text-multilingual-embedding-002.
# gemini-embedding-001 mặc định 3072 chiều, nhưng nhận `outputDimensionality`
# — ép về 768 để khớp cột `vector(768)`. Vector của hai model KHÔNG so được
# với nhau: đổi provider là phải nạp lại kho, và `suc_khoe` canh việc đó.
EMBED_MODEL_API = "gemini-embedding-001"
EMBED_MODEL_OPENAI = "text-embedding-3-small"
_da_ghi_model: str | None = None


def embed_model_hien_hanh() -> str:
    from agent.core import llm

    p = llm.provider()
    if p == "openai":
        return EMBED_MODEL_OPENAI
    if p == "gemini_api":
        return EMBED_MODEL_API
    return EMBED_MODEL


async def _embed_openai(texts: list[str]) -> list[list[float]]:
    import httpx

    from agent.core.llm import _openai_key, _openai_url

    key = _openai_key()
    url = _openai_url("/embeddings")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": EMBED_MODEL_OPENAI,
        "input": texts,
        "dimensions": EMBED_DIM,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, headers=headers, json=body)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI embedding {r.status_code}: {r.text[:200]}")
    data = r.json().get("data", [])
    data_sorted = sorted(data, key=lambda item: item.get("index", 0))
    return [item["embedding"] for item in data_sorted]


async def _embed_gemini_api(texts: list[str], task: str) -> list[list[float]]:
    import httpx

    from agent import cau_hinh_dong
    from agent.core.llm import GEMINI_API_GOC

    key = cau_hinh_dong.lay("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "Chưa có GEMINI_API_KEY cho embedding. Nhập ở dashboard → Cấu hình → Cài đặt API"
        )
    body = {
        "requests": [
            {
                "model": f"models/{EMBED_MODEL_API}",
                "content": {"parts": [{"text": t}]},
                "taskType": task,
                "outputDimensionality": EMBED_DIM,
            }
            for t in texts
        ]
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{GEMINI_API_GOC}/models/{EMBED_MODEL_API}:batchEmbedContents",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
        )
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini embedding {r.status_code}: {r.text[:200]}")
    return [e["values"] for e in r.json().get("embeddings", [])]


async def _ghi_model_dang_dung(model: str) -> None:
    """Ghi một lần mỗi tiến trình vào cau_hinh_agent để suc_khoe đối chiếu."""
    global _da_ghi_model
    if _da_ghi_model == model:
        return
    await db.execute(
        "INSERT INTO cau_hinh_agent (khoa, gia_tri, sua_boi) "
        "VALUES ('embed_model_dang_dung', $1, 'system') "
        "ON CONFLICT (khoa) DO UPDATE SET gia_tri = EXCLUDED.gia_tri, sua_luc = now()",
        model,   # codec JSONB của pool tự mã hoá chuỗi
    )
    _da_ghi_model = model


def _kiem_so_vector(vec: list[list[float]], texts: list[str], model: str) -> None:
    """
    Chặn kiểu lỗi im lặng nặng nhất trong repo này: `zip()` cắt ngầm về danh
    sách ngắn hơn (xem CLAUDE.md — bảng "hỏng im lặng"). Nếu API nhúng trả
    thiếu vector, `zip(pieces, vectors, strict=True)` ở `ingest()` sẽ NỔ —
    nhưng đó là chỗ QUÁ TRỄ để chẩn đoán, và hàm `retrieve()` (đường hỏi,
    không phải nạp) không đi qua `ingest()` nên không có lưới nào khác canh
    số lượng. Kiểm ngay tại nguồn, cho cả hai nhánh dispatch.
    """
    if len(vec) != len(texts):
        raise RuntimeError(
            f"embedding {model}: nhận {len(vec)} vector cho {len(texts)} văn bản"
        )


@dataclass(slots=True)
class Passage:
    doc_title: str
    content: str
    score: float
    document_id: UUID | None = None
    version_id: UUID | None = None
    version: int | None = None
    chunk_id: UUID | None = None
    source: str | None = None
    published_at: datetime | None = None

    def cite(self) -> str:
        return f"[{self.doc_title}]"


def _embed_sync(texts: list[str], task: str) -> list[list[float]]:
    from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
    import vertexai

    region = settings.gcp_region if settings.gcp_region != "global" else "us-central1"
    vertexai.init(project=settings.gcp_project_id, location=region)
    model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)
    inputs: list[str | TextEmbeddingInput] = [TextEmbeddingInput(t, task) for t in texts]
    return [e.values for e in model.get_embeddings(inputs)]


# Vertex có hạn mức riêng cho embedding. Nạp cả kho tri thức một lượt là
# đủ chạm trần, và khi đó lỗi 429 làm kho nạp DỞ trong im lặng: vài tài liệu
# vào được, vài tài liệu không, không ai biết cho tới lúc agent trả lời
# thiếu. Đã xảy ra thật khi mở rộng kho từ 6 lên 12 tài liệu.
# Hạn mức của Vertex tính theo PHÚT, nên backoff phải phủ được một phút.
# Bản đầu chờ 4+8+16 = 28 giây và vẫn thua — chưa qua hết cửa sổ hạn mức.
_LAN_THU_EMBED = 5
_CHO_DAU_GIAY = 15.0


async def embed(texts: list[str], *, query: bool = False) -> list[list[float]]:
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    model = embed_model_hien_hanh()
    cho = _CHO_DAU_GIAY
    for lan in range(_LAN_THU_EMBED):
        try:
            if model == EMBED_MODEL_OPENAI:
                vec = await _embed_openai(texts)
            elif model == EMBED_MODEL_API:
                vec = await _embed_gemini_api(texts, task)
            else:
                vec = await asyncio.to_thread(_embed_sync, texts, task)
            _kiem_so_vector(vec, texts, model)
            break
        except Exception as exc:  # noqa: BLE001
            tam_thoi = "429" in str(exc) or "exhaust" in str(exc).lower()
            if not tam_thoi or lan == _LAN_THU_EMBED - 1:
                raise
            await asyncio.sleep(cho)
            cho *= 2

    # Ghi nhận "kho nạp bằng model nào" là việc CHẨN ĐOÁN — chỉ `suc_khoe`
    # đọc lại để đối chiếu, không phải một bước bắt buộc của việc nạp tri
    # thức. Tách khỏi try/except phía trên: nếu để chung, một lần CSDL sập
    # đúng lúc ghi bookkeeping sẽ làm MẤT LUÔN vector vừa nhúng thành công
    # (tốn tiền + thời gian gọi API) và làm sập cả `embed()` — trong khi lẽ
    # ra vector đó vẫn dùng được. Không re-raise ở đây, nhưng cũng không
    # được nuốt lặng lẽ: log ERROR là thứ ồn ào nhất mà không phá được luồng
    # nạp kho tri thức.
    if not query:
        try:
            await _ghi_model_dang_dung(model)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("agent.rag").error(
                "embed_model_dang_dung: ghi thất bại (%s), model=%s — "
                "vector vẫn nạp bình thường nhưng suc_khoe không đối chiếu "
                "được lần nạp này",
                type(exc).__name__,
                model,
            )

    return vec


def _vec(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


# Hợp nhất hai bảng xếp hạng bằng Reciprocal Rank Fusion.
#
# RRF cộng 1/(K + thứ hạng) từ mỗi bảng. Ưu điểm quyết định: KHÔNG cần chuẩn
# hoá điểm. Cosine chạy 0..1 còn ts_rank chạy 0..vô hạn và phụ thuộc độ dài
# đoạn — cộng thẳng hai thứ đó lại thì bảng nào có thang lớn hơn sẽ nuốt bảng
# kia. RRF chỉ nhìn THỨ HẠNG nên tránh được hẳn chuyện đó.
#
# K = 5, KHÔNG phải 60 như mặc định thường thấy — và đây là chỗ đo thật sự
# quan trọng hơn việc chép giá trị từ bài báo.
#
# K=60 hợp lý khi mỗi bảng có hàng nghìn ứng viên. Ở đây mỗi bảng chỉ 20:
# 1/(60+1) so với 1/(60+20) chỉ chênh 30%, nên "có mặt ở CẢ HAI bảng" át hết
# "xếp hạng CAO ở một bảng". Hậu quả cụ thể: đoạn `van-chuyen-doi-tra` đứng
# hạng 2 ở bộ từ khoá vẫn bị đẩy khỏi top 5.
#
# Với K=5 thì 1/(5+1) so với 1/(5+20) chênh 4 lần, thứ hạng lấy lại trọng
# lượng. Quét thử K = 5, 10, 20, 40, 60 trên 8 câu hỏi thật: K=5 cho 8/8,
# mọi giá trị còn lại 6/8. So với vector thuần (6/8) thì đây là +2 câu.
#
# Lưu ý cho người sửa sau: 8 câu là mẫu NHỎ. Nếu đổi cách chia đoạn hay nạp
# kho tài liệu lớn hơn nhiều, hãy quét lại K thay vì tin con số này.
RRF_K = 5
LAY_MOI_BEN = 20


# Từ ĐỆM tiếng Việt — viết ở dạng đã bỏ dấu vì bộ tìm cũng làm việc ở dạng đó.
#
# Đây không phải chuyện làm cho đẹp. Đo trực tiếp trên kho thật:
#
#   "chinh | sach | doi | tra | bao | nhieu | ngay"  -> xu-ly-tinh-huong-ban-hang (SAI)
#   "doi | tra"                                       -> van-chuyen-doi-tra      (ĐÚNG)
#
# `ts_rank` xếp theo tần suất khớp chứ KHÔNG có IDF, nên từ đệm xuất hiện
# khắp nơi sẽ át hết từ mang nghĩa. Bỏ chúng đi là bộ tìm từ khoá mới trỏ
# đúng chỗ.
#
# Chỉ liệt kê từ CHỨC NĂNG — thứ không bao giờ là câu trả lời. Cố ý GIỮ LẠI
# "ngay", "tien", "gia", "thang": chúng trông phổ thông nhưng lại chính là
# nội dung khách hỏi ("giao mấy ngày", "bao nhiêu tiền").
TU_DEM = frozenset("""
a ah ak la va voi cho cua o tai tu den nhu thi ma nen neu con nhung
co khong chua duoc dang se da roi lam bi boi
the nao sao gi day do kia nay ây vay
bao nhieu may moi cac nhung tat ca
em anh chi minh ban shop toi ho no
xin vui long a nhe nha oi ui
can muon hoi biet cho xem giup toi
""".split())


def _tsquery(cau: str) -> str:
    """
    Câu hỏi -> biểu thức tìm kiếm, các từ nối bằng HOẶC.

    Nối bằng VÀ (mặc định của plainto_tsquery) là quá chặt: khách hỏi "chính
    sách đổi trả bao nhiêu ngày" mà tài liệu viết "đổi trả trong 7 ngày" thì
    thiếu chữ "chính sách" là trượt sạch. Nối HOẶC rồi để RRF xếp hạng.

    Không bỏ dấu ở đây — hàm `bo_dau()` trong CSDL lo việc đó cho CẢ hai
    phía, nên chỉ có MỘT nơi định nghĩa thế nào là "bỏ dấu". Tách ra hai chỗ
    là sớm muộn cũng lệch nhau.
    """
    tu = re.findall(r"[0-9A-Za-zÀ-ỹ]+", str(cau or ""))
    giu = [t for t in tu if len(t) > 1 and _fold(t) not in TU_DEM]
    # Câu toàn từ đệm ("cho mình hỏi với ạ") thì đừng bỏ sạch — thà tìm bằng
    # tất cả còn hơn không tìm gì, vector vẫn gánh phần còn lại.
    return " | ".join(giu or [t for t in tu if len(t) > 1])


def _fold(t: str) -> str:
    """Bỏ dấu một từ, khớp cách `bo_dau()` trong CSDL đang làm."""
    import unicodedata

    x = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in x if unicodedata.category(c) != "Mn").replace("đ", "d")


async def retrieve(
    question: str,
    k: int = 5,
    min_score: float = 0.35,
    *,
    account_id: UUID | None = None,
) -> list[Passage]:
    """
    Lấy các đoạn liên quan, trộn tìm kiếm VECTOR và TỪ KHOÁ.

    Vector thuần bắt được ý gần giống nhưng bỏ lỡ từ chính xác. Đo trên kho
    thật trước khi sửa: "chính sách đổi trả bao nhiêu ngày" trả về đoạn nói
    chuyện phiếm, "đơn bao nhiêu tiền miễn phí ship" trả về đoạn quà tặng
    kèm — trong khi những từ đó nằm nguyên văn trong tài liệu.

    Rỗng = agent KHÔNG được phát ngôn có căn cứ.
    """
    try:
        qvec = (await embed([question], query=True))[0]
    except Exception:  # noqa: BLE001 — thiếu quyền Vertex thì degrade, đừng sập
        qvec = None

    tq = _tsquery(question)
    if qvec is None and not tq:
        return []

    # Một câu SQL, hai nhánh xếp hạng, hợp nhất bằng RRF. Làm trong CSDL để
    # không kéo 40 đoạn văn qua mạng rồi mới loại bỏ.
    rows = await db.fetch(
        f"""
        WITH hop_le AS (
            SELECT c.id, c.embedding, c.tim_kiem
            FROM chunks c
            JOIN document_versions v ON v.id = c.document_version_id
            JOIN documents d ON d.id = c.document_id
            WHERE v.status = 'published'
              AND v.index_status = 'ready'
              AND d.lifecycle_status = 'published'
              AND d.current_published_version_id = v.id
              AND (
                    ($4::uuid IS NULL AND d.account_id IS NULL)
                 OR ($4::uuid IS NOT NULL AND (
                        d.account_id = $4::uuid OR d.account_id IS NULL
                    ))
              )
        ),
        theo_vector AS (
            SELECT c.id,
                   row_number() OVER (ORDER BY c.embedding <=> $1::vector) AS hang,
                   1 - (c.embedding <=> $1::vector) AS diem_cosine
            FROM hop_le c
            WHERE c.embedding IS NOT NULL AND $1::vector IS NOT NULL
            ORDER BY c.embedding <=> $1::vector
            LIMIT {LAY_MOI_BEN}
        ),
        theo_tu_khoa AS (
            SELECT c.id,
                   row_number() OVER (
                       ORDER BY ts_rank(c.tim_kiem, to_tsquery('simple', bo_dau($2))) DESC
                   ) AS hang
            FROM hop_le c
            WHERE $2 <> '' AND c.tim_kiem @@ to_tsquery('simple', bo_dau($2))
            ORDER BY ts_rank(c.tim_kiem, to_tsquery('simple', bo_dau($2))) DESC
            LIMIT {LAY_MOI_BEN}
        ),
        gop AS (
            SELECT coalesce(v.id, t.id) AS id,
                   coalesce(v.diem_cosine, 0)                     AS diem_cosine,
                   coalesce(1.0 / ({RRF_K} + v.hang), 0)
                     + coalesce(1.0 / ({RRF_K} + t.hang), 0)      AS diem_gop,
                   t.hang                                          AS hang_tu_khoa
            FROM theo_vector v
            FULL OUTER JOIN theo_tu_khoa t ON t.id = v.id
        )
        SELECT d.title AS doc_title, d.id AS document_id, d.source,
               v.id AS version_id, v.version, v.published_at,
               c.id AS chunk_id, c.content,
               g.diem_cosine AS score, g.hang_tu_khoa
        FROM gop g
        JOIN chunks c ON c.id = g.id
        JOIN documents d ON d.id = c.document_id
        JOIN document_versions v ON v.id = c.document_version_id
        ORDER BY g.diem_gop DESC
        LIMIT $3
        """,
        _vec(qvec) if qvec is not None else None,
        tq,
        k,
        account_id,
    )

    # Giữ đoạn nếu vector thấy nó ĐỦ GIỐNG, HOẶC từ khoá xếp nó vào top 3.
    #
    # Chỉ lọc theo cosine là vứt mất đúng thứ vừa sửa được: đoạn trúng từ
    # khoá chính xác thường có cosine thấp vì diễn đạt khác hẳn câu khách hỏi.
    return [
        Passage(
            doc_title=r["doc_title"],
            content=r["content"],
            score=float(r["score"]),
            document_id=r["document_id"],
            version_id=r["version_id"],
            version=int(r["version"]),
            chunk_id=r["chunk_id"],
            source=r["source"],
            published_at=r["published_at"],
        )
        for r in rows
        if float(r["score"]) >= min_score
        or (r["hang_tu_khoa"] is not None and int(r["hang_tu_khoa"]) <= 3)
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


class KnowledgeConflict(RuntimeError):
    """Tài liệu/phiên bản đã đổi trong lúc thao tác đang chạy."""


class KnowledgeNotReady(RuntimeError):
    """Draft chưa có index hợp lệ nên không thể Publish."""


async def save_draft(
    *,
    title: str,
    source: str,
    text: str,
    account_id: UUID | None,
    actor: str,
    actor_id: UUID | None = None,
    document_id: UUID | None = None,
) -> dict[str, Any]:
    """Tạo/cập nhật draft, lập index nhưng tuyệt đối chưa cho RAG đọc."""
    title = title.strip()
    text = text.strip()
    if not title or not source.strip() or not text:
        raise ValueError("Tiêu đề, nguồn và nội dung tài liệu không được trống")

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if document_id is not None:
                document = await conn.fetchrow(
                    """
                    SELECT * FROM documents
                    WHERE id=$1 AND account_id IS NOT DISTINCT FROM $2
                    FOR UPDATE
                    """,
                    document_id,
                    account_id,
                )
                if document is None:
                    raise LookupError("Không tìm thấy tài liệu trong phạm vi tài khoản")
            else:
                document = await conn.fetchrow(
                    """
                    SELECT * FROM documents
                    WHERE account_id IS NOT DISTINCT FROM $1 AND source=$2
                    ORDER BY updated_at DESC LIMIT 1 FOR UPDATE
                    """,
                    account_id,
                    source,
                )
                if document is None:
                    document = await conn.fetchrow(
                        """
                        INSERT INTO documents (
                            title, source, chunk_count, account_id,
                            lifecycle_status, updated_at
                        ) VALUES ($1,$2,0,$3,'draft',now())
                        RETURNING *
                        """,
                        title,
                        source,
                        account_id,
                    )

            draft = None
            if document["current_draft_version_id"] is not None:
                draft = await conn.fetchrow(
                    """
                    UPDATE document_versions
                    SET content=$2, index_status='indexing', index_error=NULL,
                        chunk_count=0, revision=revision+1, updated_at=now(),
                        created_by=coalesce($3, created_by)
                    WHERE id=$1 AND status='draft'
                    RETURNING id, version, revision
                    """,
                    document["current_draft_version_id"],
                    text,
                    actor_id,
                )
                if draft is not None:
                    await conn.execute(
                        "DELETE FROM chunks WHERE document_version_id=$1", draft["id"]
                    )
            if draft is None:
                next_version = await conn.fetchval(
                    """
                    SELECT coalesce(max(version),0)+1
                    FROM document_versions WHERE document_id=$1
                    """,
                    document["id"],
                )
                draft = await conn.fetchrow(
                    """
                    INSERT INTO document_versions (
                        document_id, version, status, content, index_status,
                        created_by
                    ) VALUES ($1,$2,'draft',$3,'indexing',$4)
                    RETURNING id, version, revision
                    """,
                    document["id"],
                    next_version,
                    text,
                    actor_id,
                )

            await conn.execute(
                """
                UPDATE documents
                SET title=$2, source=$3, current_draft_version_id=$4,
                    lifecycle_status=CASE
                        WHEN current_published_version_id IS NULL THEN 'draft'
                        ELSE 'published'
                    END,
                    updated_at=now()
                WHERE id=$1
                """,
                document["id"],
                title,
                source,
                draft["id"],
            )
            await conn.execute(
                """
                INSERT INTO events (kind, actor, ref_id, detail)
                VALUES ('knowledge.draft_saved',$1,$2,$3)
                """,
                actor,
                document["id"],
                {"version": int(draft["version"])},
            )

    pieces = chunk_text(text)
    try:
        vectors = await embed(pieces)
    except Exception as exc:
        async with db.pool().acquire() as conn:
            await conn.execute(
                """
                UPDATE document_versions
                SET index_status='failed', index_error=$3, updated_at=now()
                WHERE id=$1 AND revision=$2 AND status='draft'
                """,
                draft["id"],
                draft["revision"],
                f"{type(exc).__name__}: {exc}"[:500],
            )
        raise

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            current = await conn.fetchrow(
                """
                SELECT id FROM document_versions
                WHERE id=$1 AND revision=$2 AND status='draft'
                FOR UPDATE
                """,
                draft["id"],
                draft["revision"],
            )
            if current is None:
                raise KnowledgeConflict("Draft đã đổi trong lúc tạo embedding")
            await conn.executemany(
                """
                INSERT INTO chunks (
                    document_id, document_version_id, ord, content, embedding
                ) VALUES ($1,$2,$3,$4,$5::vector)
                """,
                [
                    (document["id"], draft["id"], i, piece, _vec(vector))
                    for i, (piece, vector) in enumerate(
                        zip(pieces, vectors, strict=True)
                    )
                ],
            )
            await conn.execute(
                """
                UPDATE document_versions
                SET index_status='ready', index_error=NULL, chunk_count=$2,
                    updated_at=now()
                WHERE id=$1
                """,
                draft["id"],
                len(pieces),
            )
            await conn.execute(
                "UPDATE documents SET chunk_count=$2, updated_at=now() WHERE id=$1",
                document["id"],
                len(pieces),
            )

    return {
        "document_id": document["id"],
        "version_id": draft["id"],
        "version": int(draft["version"]),
        "index_status": "ready",
        "chunks": len(pieces),
    }


async def publish_version(
    *,
    document_id: UUID,
    version_id: UUID,
    account_id: UUID | None,
    actor: str,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    """Publish một draft đã index; khoá document để hai người không đua nhau."""
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            document = await conn.fetchrow(
                """
                SELECT * FROM documents
                WHERE id=$1 AND account_id IS NOT DISTINCT FROM $2
                FOR UPDATE
                """,
                document_id,
                account_id,
            )
            if document is None:
                raise LookupError("Không tìm thấy tài liệu trong phạm vi tài khoản")
            version = await conn.fetchrow(
                """
                SELECT * FROM document_versions
                WHERE id=$1 AND document_id=$2
                """,
                version_id,
                document_id,
            )
            if version is None:
                raise LookupError("Phiên bản không thuộc tài liệu")
            if (
                version["status"] == "published"
                and document["current_published_version_id"] == version_id
            ):
                return {
                    "document_id": document_id,
                    "version_id": version_id,
                    "version": int(version["version"]),
                    "published": True,
                    "already_published": True,
                }
            if document["current_draft_version_id"] != version_id:
                raise KnowledgeConflict("Phiên bản không còn là draft hiện hành")
            if version["status"] != "draft" or version["index_status"] != "ready":
                raise KnowledgeNotReady("Draft chưa lập chỉ mục thành công")
            chunk_count = await conn.fetchval(
                "SELECT count(*) FROM chunks WHERE document_version_id=$1",
                version_id,
            )
            if not chunk_count or chunk_count != version["chunk_count"]:
                raise KnowledgeNotReady("Số chunk/index của draft không nhất quán")

            previous_id = document["current_published_version_id"]
            if previous_id is not None:
                await conn.execute(
                    """
                    UPDATE document_versions SET status='superseded', updated_at=now()
                    WHERE id=$1 AND status='published'
                    """,
                    previous_id,
                )
            await conn.execute(
                """
                UPDATE document_versions
                SET status='published', published_by=$2,
                    published_at=now(), updated_at=now()
                WHERE id=$1
                """,
                version_id,
                actor_id,
            )
            await conn.execute(
                """
                UPDATE documents
                SET lifecycle_status='published',
                    current_published_version_id=$2,
                    current_draft_version_id=NULL,
                    chunk_count=$3, updated_at=now()
                WHERE id=$1
                """,
                document_id,
                version_id,
                chunk_count,
            )
            await conn.execute(
                """
                INSERT INTO events (kind, actor, ref_id, detail)
                VALUES ('knowledge.published',$1,$2,$3)
                """,
                actor,
                document_id,
                {
                    "version": int(version["version"]),
                    "version_id": str(version_id),
                    "previous_version_id": str(previous_id) if previous_id else None,
                },
            )
    return {
        "document_id": document_id,
        "version_id": version_id,
        "version": int(version["version"]),
        "published": True,
        "already_published": False,
    }


async def rollback_version(
    *,
    document_id: UUID,
    source_version_id: UUID,
    account_id: UUID | None,
    actor: str,
    actor_id: UUID | None = None,
) -> dict[str, Any]:
    """Khôi phục nội dung cũ thành version MỚI rồi Publish an toàn."""
    async with db.pool().acquire() as conn:
        source = await conn.fetchrow(
            """
            SELECT d.title, d.source, v.version, v.content
            FROM documents d
            JOIN document_versions v ON v.document_id=d.id
            WHERE d.id=$1 AND v.id=$2
              AND d.account_id IS NOT DISTINCT FROM $3
              AND v.status IN ('published','superseded')
            """,
            document_id,
            source_version_id,
            account_id,
        )
    if source is None:
        raise LookupError("Không tìm thấy phiên bản Published để rollback")
    draft = await save_draft(
        document_id=document_id,
        title=source["title"],
        source=source["source"],
        text=source["content"],
        account_id=account_id,
        actor=actor,
        actor_id=actor_id,
    )
    published = await publish_version(
        document_id=document_id,
        version_id=draft["version_id"],
        account_id=account_id,
        actor=actor,
        actor_id=actor_id,
    )
    async with db.pool().acquire() as conn:
        await conn.execute(
            """
            INSERT INTO events (kind, actor, ref_id, detail)
            VALUES ('knowledge.rolled_back',$1,$2,$3)
            """,
            actor,
            document_id,
            {
                "from_version": int(source["version"]),
                "to_version": int(published["version"]),
                "source_version_id": str(source_version_id),
            },
        )
    return published


async def ingest(
    title: str,
    source: str,
    text: str,
    *,
    account_id: UUID | None = None,
    actor: str = "system",
    publish: bool = True,
) -> int:
    """
    Nạp một tài liệu vào cơ sở tri thức. Trả về số chunk.

    Nạp lại cùng một `source` thì tạo phiên bản mới trên cùng logical
    document, không thêm bản trùng và không ghi đè lịch sử Published.
    Trước đây chạy `scripts.ingest` hai lần tạo ra hai bản ghi documents và
    nhân đôi số đoạn — RAG trả về cùng một đoạn hai lần, vừa tốn ngữ cảnh
    vừa làm lệch điểm khớp. Ba tài liệu đã bị trùng đúng như vậy.
    """
    draft = await save_draft(
        title=title,
        source=source,
        text=text,
        account_id=account_id,
        actor=actor,
    )
    if publish:
        await publish_version(
            document_id=draft["document_id"],
            version_id=draft["version_id"],
            account_id=account_id,
            actor=actor,
        )
    return int(draft["chunks"])


async def xoa_nguon(prefix: str) -> int:
    """
    Lưu trữ mọi tài liệu có `source` bắt đầu bằng `prefix`. Trả về số tài liệu.

    Dùng cho gói kỹ năng: tài liệu của gói mang nguồn `goi:<ten>:<slug>`,
    tắt gói là gỡ khỏi retrieval bằng một tiền tố thay vì nhớ từng id. Các
    version/chunk vẫn còn để audit và khôi phục.
    """
    trang_thai = await db.execute(
        """
        UPDATE documents
        SET lifecycle_status='archived', updated_at=now()
        WHERE source LIKE $1 AND lifecycle_status <> 'archived'
        """,
        prefix + "%",
    )
    return int(str(trang_thai).rsplit(" ", 1)[-1] or 0)
