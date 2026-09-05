"""
RAG trên pgvector + Vertex embeddings.

Chỗ để cắm lại RAG pháp lý sẵn có: chỉ cần thay hai hàm `embed()` và
`retrieve()` bằng bản của bạn, giữ nguyên chữ ký. Phần còn lại của hệ thống
chỉ phụ thuộc vào kiểu trả về `Passage`.
"""
from __future__ import annotations

import re

import asyncio
from dataclasses import dataclass

from agent import db
from agent.config import settings

EMBED_MODEL = "text-multilingual-embedding-002"   # 768 chiều, tốt cho tiếng Việt
EMBED_DIM = 768

# Gemini API (Google AI Studio) không có text-multilingual-embedding-002.
# gemini-embedding-001 mặc định 3072 chiều, nhưng nhận `outputDimensionality`
# — ép về 768 để khớp cột `vector(768)`. Vector của hai model KHÔNG so được
# với nhau: đổi provider là phải nạp lại kho, và `suc_khoe` canh việc đó.
EMBED_MODEL_API = "gemini-embedding-001"
_da_ghi_model: str | None = None


def embed_model_hien_hanh() -> str:
    from agent.core import llm

    return EMBED_MODEL_API if llm.provider() == "gemini_api" else EMBED_MODEL


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
    cho = _CHO_DAU_GIAY
    for lan in range(_LAN_THU_EMBED):
        try:
            model = embed_model_hien_hanh()
            if model == EMBED_MODEL_API:
                vec = await _embed_gemini_api(texts, task)
            else:
                vec = await asyncio.to_thread(_embed_sync, texts, task)
            if not query:
                await _ghi_model_dang_dung(model)
            return vec
        except Exception as exc:  # noqa: BLE001
            tam_thoi = "429" in str(exc) or "exhaust" in str(exc).lower()
            if not tam_thoi or lan == _LAN_THU_EMBED - 1:
                raise
            await asyncio.sleep(cho)
            cho *= 2


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


async def retrieve(question: str, k: int = 5, min_score: float = 0.35) -> list[Passage]:
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
        WITH theo_vector AS (
            SELECT c.id,
                   row_number() OVER (ORDER BY c.embedding <=> $1::vector) AS hang,
                   1 - (c.embedding <=> $1::vector) AS diem_cosine
            FROM chunks c
            WHERE c.embedding IS NOT NULL AND $1::vector IS NOT NULL
            ORDER BY c.embedding <=> $1::vector
            LIMIT {LAY_MOI_BEN}
        ),
        theo_tu_khoa AS (
            SELECT c.id,
                   row_number() OVER (
                       ORDER BY ts_rank(c.tim_kiem, to_tsquery('simple', bo_dau($2))) DESC
                   ) AS hang
            FROM chunks c
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
        SELECT d.title AS doc_title, c.content,
               g.diem_cosine AS score, g.hang_tu_khoa
        FROM gop g
        JOIN chunks c ON c.id = g.id
        JOIN documents d ON d.id = c.document_id
        ORDER BY g.diem_gop DESC
        LIMIT $3
        """,
        _vec(qvec) if qvec is not None else None,
        tq,
        k,
    )

    # Giữ đoạn nếu vector thấy nó ĐỦ GIỐNG, HOẶC từ khoá xếp nó vào top 3.
    #
    # Chỉ lọc theo cosine là vứt mất đúng thứ vừa sửa được: đoạn trúng từ
    # khoá chính xác thường có cosine thấp vì diễn đạt khác hẳn câu khách hỏi.
    return [
        Passage(r["doc_title"], r["content"], float(r["score"]))
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


async def ingest(title: str, source: str, text: str) -> int:
    """
    Nạp một tài liệu vào cơ sở tri thức. Trả về số chunk.

    Nạp lại cùng một `source` thì THAY bản cũ, không thêm bản thứ hai.
    Trước đây chạy `scripts.ingest` hai lần tạo ra hai bản ghi documents và
    nhân đôi số đoạn — RAG trả về cùng một đoạn hai lần, vừa tốn ngữ cảnh
    vừa làm lệch điểm khớp. Ba tài liệu đã bị trùng đúng như vậy.
    """
    pieces = chunk_text(text)
    vectors = await embed(pieces)

    # Xoá trước khi ghi. `chunks` có ON DELETE CASCADE nên đoạn cũ đi theo.
    await db.execute("DELETE FROM documents WHERE source = $1", source)

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
            # strict=True: `zip` mặc định CẮT NGẦM về danh sách ngắn hơn.
            # Ở đây hai danh sách là đoạn văn bản và vector của chính
            # chúng — lệch nhau nghĩa là API nhúng trả thiếu, và cắt ngầm
            # thì vài đoạn tri thức lặng lẽ không vào kho. Agent sau đó
            # trả lời "chưa có thông tin" cho câu mà tài liệu CÓ nói, và
            # không có gì trong hệ thống chỉ ra vì sao.
            [(doc_id, i, c, _vec(v))
             for i, (c, v) in enumerate(zip(pieces, vectors, strict=True))],
        )
    return len(pieces)
