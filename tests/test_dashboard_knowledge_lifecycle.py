"""Dashboard DEV-11 dùng đúng contract Draft/Publish/Rollback của Backend."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "dashboard" / "src" / "06-tong-quan.js").read_text(encoding="utf-8")
HTML = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
BUNDLE = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")


def test_form_tao_draft_co_account_va_khong_tu_publish():
    assert 'id="knowledge-account"' in HTML
    assert 'name="document_id"' in HTML
    assert "Lưu Draft" in HTML
    submit = SRC.split('$("#docform").addEventListener("submit"', 1)[1]
    submit = submit.split('$("#probeform")', 1)[0]
    assert 'account_id: f.get("account_id")' in submit
    assert 'method: documentId ? "PUT" : "POST"' in submit
    assert "/publish" not in submit


def test_ui_co_publish_history_rollback_va_index_error():
    for marker in (
        "data-doc-publish",
        "data-doc-history",
        "data-doc-rollback",
        "index_error",
        "published_version",
        "draft_version",
    ):
        assert marker in SRC
    assert 'state.toiQuyen.has("cau_hinh.sua")' in SRC


def test_probe_hien_nguon_version_va_chunk_backend_tra_ve():
    assert "h.version" in SRC
    assert "h.chunk_id" in SRC
    assert "account_id: state.knowledgeAccount" in SRC


def test_bundle_da_duoc_dong_goi_tu_source_moi():
    for marker in (
        "Đã lưu Draft v",
        "Đã rollback thành Published v",
        "/knowledge/accounts",
        "data-doc-publish",
    ):
        assert marker in BUNDLE
