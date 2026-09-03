"""
Xoá tài khoản kênh — và KHÔNG BAO GIỜ xoá lịch sử khách theo.

BỐI CẢNH

Người dùng có 26 tài khoản Facebook (25 ở trạng thái chờ), một Zalo OA
hỏng, và không có cách nào dọn. Nhưng một nút "Xoá" viết ẩu sẽ kéo theo
hội thoại của khách — thứ không dựng lại được.

Lược đồ đã canh sẵn:

    conversations       ON DELETE RESTRICT   <- hội thoại đã diễn ra
    contact_points      ON DELETE RESTRICT   <- danh tính khách trên kênh
    outbox_jobs         ON DELETE RESTRICT   <- tin đang chờ gửi
    webhook_deliveries  ON DELETE RESTRICT   <- webhook đã nhận
    credential_secrets  ON DELETE CASCADE    <- bí mật, PHẢI đi theo

Ca kiểm ở đây canh lược đồ ấy không bị nới lỏng, vì đổi một chữ RESTRICT
thành CASCADE là biến nút dọn giao diện thành nút xoá bằng chứng.

HAI LỖI THẬT TRONG CHÍNH ĐOẠN MÃ NÀY, cả hai đều IM LẶNG

  1. `ref_id=str(account_id)` vào cột uuid -> asyncpg từ chối.
  2. `actor=_actor(user)` trả về AccountActor vào cột TEXT -> từ chối.

Cả hai đều bị `db.log_event` nuốt bằng `except: pass`, nên thao tác XOÁ —
không đảo ngược được — không để lại dấu vết nào. Phát hiện ra chỉ vì tình
cờ đi đếm bảng `events` sau khi thử tay.

Lỗi thứ hai chép khuôn từ dòng `service.disable_account(actor=_actor(user))`
ngay bên trên: đúng cho service, sai cho log_event.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NGUON = (ROOT / "agent" / "api" / "channel_accounts.py").read_text(encoding="utf-8")
SCHEMA = "\n".join(
    p.read_text(encoding="utf-8")
    for p in [ROOT / "agent" / "schema.sql",
              *sorted((ROOT / "agent" / "migrations" / "versions").glob("*.sql"))]
)


# ---------------------------------------------------------------
#  Lịch sử khách được lược đồ bảo vệ
# ---------------------------------------------------------------

@pytest.mark.parametrize(
    "bang", ["conversations", "contact_points", "outbox_jobs", "webhook_deliveries"]
)
def test_bang_giu_lich_su_khong_duoc_CASCADE(bang):
    """
    Đổi RESTRICT thành CASCADE ở bốn bảng này là biến nút dọn giao diện
    thành nút xoá bằng chứng của cửa hàng — và nó xoá trong im lặng.
    """
    import re

    khoi = re.search(
        rf"CREATE TABLE IF NOT EXISTS {bang}\s*\((.*?)\n\);", SCHEMA, re.S
    )
    assert khoi, f"không tìm thấy định nghĩa bảng {bang}"
    than = khoi.group(1)
    for dong in than.split("\n"):
        if "channel_accounts" not in dong or "REFERENCES" not in dong:
            continue
        assert "ON DELETE CASCADE" not in dong, (
            f"{bang} tham chiếu channel_accounts với CASCADE — xoá tài khoản "
            "sẽ xoá theo lịch sử khách"
        )
        return
    # Không có khoá ngoại trong CREATE TABLE thì nó nằm ở migration; ca
    # `test_moi_bang_giu_deu_duoc_kiem` bên dưới vẫn canh phía ứng dụng.


def test_moi_bang_giu_deu_duoc_kiem_truoc_khi_xoa():
    """
    Ứng dụng hỏi TRƯỚC thay vì để Postgres ném lỗi ràng buộc: thông điệp
    của Postgres nói tên constraint, không nói "còn 12 hội thoại". Người
    vận hành cần con số để chọn giữa xoá và tạm ngắt.
    """
    from agent.api.channel_accounts import _BANG_GIU

    ten = {b for b, _, _ in _BANG_GIU}
    assert ten == {"conversations", "contact_points", "outbox_jobs",
                   "webhook_deliveries"}
    for _, _, nhan in _BANG_GIU:
        assert nhan and not nhan.startswith("_"), "nhãn phải viết bằng tiếng người"


def test_co_duong_xem_truoc_rieng():
    """
    Bấm Xoá rồi mới nhận lỗi là bắt người dùng thử để biết, trong khi máy
    chủ biết câu trả lời từ trước.
    """
    assert '"/{account_id}/co-xoa-duoc"' in NGUON


# ---------------------------------------------------------------
#  Nhật ký kiểm toán phải GHI ĐƯỢC
# ---------------------------------------------------------------

def _ham(ten: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(ast.parse(NGUON)):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == ten:
            return node
    raise AssertionError(f"không tìm thấy {ten}")


def test_ghi_nhat_ky_TRUOC_khi_xoa():
    """
    Ghi sau thì lần xoá thành công cuối cùng có thể không để lại dấu vết
    nếu tiến trình chết giữa chừng — và đúng lúc ấy là lúc người ta cần
    biết ai đã xoá cái gì.
    """
    than = _ham("xoa_tai_khoan")
    dong_log = dong_xoa = None
    for n in ast.walk(than):
        if isinstance(n, ast.Call):
            t = ast.unparse(n.func)
            if "log_event" in t and dong_log is None:
                dong_log = n.lineno
            if "db.execute" in t and dong_xoa is None:
                dong_xoa = n.lineno
    assert dong_log and dong_xoa, "thiếu log_event hoặc DELETE"
    assert dong_log < dong_xoa, "ghi nhật ký phải nằm TRƯỚC lệnh xoá"


def test_actor_la_CHUOI_khong_phai_AccountActor():
    """
    LỖI THẬT. `_actor()` trả về AccountActor — đúng cho `service.*`, SAI
    cho `db.log_event`: cột `events.actor` là TEXT và asyncpg từ chối một
    đối tượng. `log_event` nuốt lỗi, nên nhật ký của một thao tác KHÔNG
    ĐẢO NGƯỢC lặng lẽ không tồn tại.
    """
    than = ast.unparse(_ham("xoa_tai_khoan"))
    assert "actor=_actor(user)" not in than, (
        "log_event nhận AccountActor — cột events.actor là TEXT, asyncpg sẽ "
        "từ chối và nhật ký kiểm toán biến mất trong im lặng"
    )
    assert "ten_dang_nhap" in than


def test_ref_id_khong_bi_boc_str():
    """LỖI THẬT thứ hai: `events.ref_id` là cột uuid, `str()` bị từ chối."""
    than = ast.unparse(_ham("xoa_tai_khoan"))
    assert "ref_id=str(" not in than, "events.ref_id là uuid, đừng bọc str()"


# ---------------------------------------------------------------
#  `log_event` không được im lặng nữa
# ---------------------------------------------------------------

def test_log_event_khong_con_nuot_loi_hoan_toan():
    """
    Nhật ký kiểm toán hỏng thì luồng chính vẫn phải chạy — nhưng nếu hỏng
    mà không ai biết thì nó hỏng MÃI MÃI.

    Hai lỗi ở trên tồn tại được chính vì `except Exception: pass`.
    """
    db_py = (ROOT / "agent" / "db.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(db_py)):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "log_event"):
            continue
        than = ast.unparse(node)
        assert "logging" in than, (
            "log_event vẫn nuốt lỗi trong im lặng — phải ghi ra logger"
        )
        # Thân except không được CHỈ có `pass`.
        for x in ast.walk(node):
            if isinstance(x, ast.ExceptHandler):
                assert not (len(x.body) == 1 and isinstance(x.body[0], ast.Pass)), (
                    "except vẫn chỉ có `pass`"
                )
        return
    raise AssertionError("không tìm thấy log_event trong db.py")


def test_log_event_ghi_ra_logger_da_co_bo_che():
    """
    Ghi qua `logging` chứ không qua CSDL — chính CSDL vừa là thứ hỏng. Và
    logger ấy đã có bộ lọc che bí mật của `agent/nhat_ky.py`.
    """
    db_py = (ROOT / "agent" / "db.py").read_text(encoding="utf-8")
    assert "getLogger" in db_py
