"""
`schema.sql` không được tham chiếu cột do migration thêm vào.

CÁI BẪY
-------
`agent/db.py::init_db` chạy `schema.sql` TRƯỚC rồi mới `apply_all()`, và nó
chạy như vậy MỖI LẦN KHỞI ĐỘNG.

Trên một CSDL đã có bảng, `CREATE TABLE IF NOT EXISTS` là lệnh rỗng — nó
KHÔNG thêm cột nào. Nên nếu `schema.sql` có thêm một `CREATE INDEX` (hay
bất cứ câu nào) chạm vào cột mà chỉ migration mới thêm, thứ tự sẽ là:

    schema.sql  ->  đụng cột chưa tồn tại  ->  NỔ
    apply_all() ->  không bao giờ chạy tới

Và hậu quả là ứng dụng KHÔNG KHỞI ĐỘNG ĐƯỢC. Trên máy của người dùng, ở
lần khởi động lại kế tiếp, không báo trước.

Bẫy này khó thấy vì trên CSDL TRẮNG mọi thứ chạy hoàn hảo: `schema.sql` tự
tạo cột trong `CREATE TABLE`, rồi chỉ mục tạo được. Test chạy trên CSDL
trắng nên xanh. Chỉ máy đang chạy thật mới hỏng.

Đã xảy ra thật với `posts.callback_token` (migration 0025).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SCHEMA = (ROOT / "agent" / "schema.sql").read_text(encoding="utf-8")
MIGRATIONS = sorted((ROOT / "agent" / "migrations" / "versions").glob("*.sql"))


def _cot_do_migration_them() -> dict[str, str]:
    """`{tên cột: file migration}` cho mọi `ALTER TABLE ... ADD COLUMN`."""
    mau = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?\w+\s+"
        r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
        re.IGNORECASE)
    ra: dict[str, str] = {}
    for f in MIGRATIONS:
        for ten in mau.findall(f.read_text(encoding="utf-8")):
            ra.setdefault(ten.lower(), f.name)
    return ra


def _schema_ngoai_create_table() -> str:
    """
    `schema.sql` sau khi BỎ thân mọi `CREATE TABLE (...)` và bỏ chú thích.

    Trong thân `CREATE TABLE`, nhắc tên cột là bình thường và vô hại — đó
    là định nghĩa cho CSDL trắng. Nguy hiểm nằm ở mọi câu NGOÀI nó.
    """
    khong_chu_thich = "\n".join(
        d for d in SCHEMA.splitlines() if not d.strip().startswith("--"))
    # Cắt từ `CREATE TABLE ... (` tới dấu `)` đóng ở đầu dòng + `;`
    return re.sub(
        r"CREATE\s+TABLE[^(]*\(.*?^\);",
        "",
        khong_chu_thich,
        flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )


def test_schema_khong_cham_cot_do_migration_them():
    them = _cot_do_migration_them()
    assert them, "không đọc được ALTER TABLE nào — bộ đọc hỏng, và bộ đọc hỏng luôn xanh"

    ngoai = _schema_ngoai_create_table()
    pham = []
    for cot, tep in them.items():
        # Tên cột quá chung (`id`, `status`…) sẽ khớp bừa. Chỉ xét tên đủ
        # đặc thù để phép so có nghĩa.
        if len(cot) < 8:
            continue
        if re.search(rf"\b{re.escape(cot)}\b", ngoai, re.IGNORECASE):
            pham.append(f"{cot} (thêm ở {tep})")
    assert not pham, (
        "schema.sql chạm vào cột chỉ migration mới thêm. Nó chạy TRƯỚC "
        "migration mỗi lần khởi động, nên trên CSDL đang chạy thật câu ấy "
        "sẽ nổ và ỨNG DỤNG KHÔNG LÊN ĐƯỢC:\n  " + "\n  ".join(pham))


def test_bo_cat_create_table_that_su_cat_duoc():
    """
    Canh chính bộ cắt ở trên. Cắt hụt thì nó giữ nguyên cả file và test
    trên báo đỏ oan; cắt quá tay thì nó xoá sạch và test trên luôn xanh —
    vế sau nguy hiểm hơn.
    """
    ngoai = _schema_ngoai_create_table()
    assert "CREATE INDEX" in ngoai, "cắt quá tay, mất cả phần ngoài bảng"
    assert "CREATE TABLE" not in ngoai, "cắt hụt, còn nguyên thân bảng"


def test_thu_tu_trong_init_db_van_la_schema_truoc_migration():
    """
    Cả nhóm test này chỉ có nghĩa khi `schema.sql` chạy TRƯỚC migration.
    Đổi thứ tự ấy thì cái bẫy biến mất — nhưng lúc đó phải xoá nhóm test
    này một cách có ý thức, không để nó canh một thứ không còn tồn tại.
    """
    ma = (ROOT / "agent" / "db.py").read_text(encoding="utf-8")
    i_schema = ma.index("conn.execute(schema)")
    i_mig = ma.index("apply_all(conn)")
    assert i_schema < i_mig
