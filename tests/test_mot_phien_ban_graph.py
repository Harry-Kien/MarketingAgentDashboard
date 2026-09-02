"""
Toàn hệ thống nói chuyện với Meta bằng MỘT phiên bản Graph.

LỖI ĐO ĐƯỢC
-----------
Bốn chỗ tự khai phiên bản, và chúng LỆCH NHAU:

    agent/channels/meta_channels.py   v23.0   <- adapter gửi/nhận tin
    agent/config.py                   v21.0
    agent/publish/meta.py             v21.0
    agent/api/oauth_meta.py           v21.0   <- OAuth và đăng ký webhook

Nghĩa là một nửa hệ thống nói chuyện với Meta bằng một hợp đồng, nửa kia
bằng hợp đồng khác. Hai phiên bản Graph khác nhau ở tên trường và ở hành vi
— và loại lệch đó không nổ ngay, nó hỏng ở đúng một trường nào đó, vào một
ngày nào đó.

Meta ngừng hỗ trợ từng phiên bản theo lịch. Gom về một chỗ để nâng cấp là
sửa một dòng, không phải đi tìm bốn chỗ rồi bỏ sót một.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _id_docstring(cay: ast.Module) -> set[int]:
    """
    id() của mọi node docstring — module, lớp, hàm.

    Bản trước quét theo DÒNG và chỉ bỏ qua dòng bắt đầu bằng `#`. Docstring
    thì không bắt đầu bằng `#`, nên một tệp GIẢI THÍCH lỗi này bằng cách
    trích URL ví dụ lại bị chính ca kiểm ấy bắt — test đỏ trong khi mã hoàn
    toàn đúng.
    """
    ra: set[int] = set()
    for node in ast.walk(cay):
        if not isinstance(node, (ast.Module, ast.ClassDef,
                                 ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        than = getattr(node, "body", None)
        if (than and isinstance(than[0], ast.Expr)
                and isinstance(than[0].value, ast.Constant)
                and isinstance(than[0].value.value, str)):
            ra.add(id(than[0].value))
    return ra


def test_khong_con_phien_ban_gan_cung_trong_ma():
    """
    Canh cả cây `agent/`: chỗ mới thêm cũng phải đi qua cấu hình.

    Đọc AST chứ không quét dòng. Chú thích và docstring được phép nhắc tới
    `graph.facebook.com/v23.0` để giải thích — thứ bị cấm là một CHUỖI THẬT
    trong mã dựng URL từ phiên bản gán cứng.
    """
    xau = []
    for f in (ROOT / "agent").rglob("*.py"):
        cay = ast.parse(f.read_text(encoding="utf-8"))
        bo_qua = _id_docstring(cay)
        for node in ast.walk(cay):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and id(node) not in bo_qua
                    and re.search(r"graph\.facebook\.com/v\d", node.value)):
                xau.append(f"{f.relative_to(ROOT)}:{node.lineno}")
    assert not xau, "còn gán cứng phiên bản Graph tại: " + ", ".join(xau)


def test_ca_kiem_tren_that_su_bat_duoc_gan_cung(tmp_path):
    """
    Canh chính bộ canh. Nới AST tới mức không còn bắt được gì thì ca trên
    xanh vĩnh viễn và ràng buộc biến mất — xanh giả, đúng thứ tệ nhất.
    """
    tep = tmp_path / "xau.py"
    tep.write_text(
        '"""Docstring nhắc https://graph.facebook.com/v23.0 thì KHÔNG sao."""\n'
        'URL = "https://graph.facebook.com/v21.0/me"\n',
        encoding="utf-8",
    )
    cay = ast.parse(tep.read_text(encoding="utf-8"))
    bo_qua = _id_docstring(cay)
    dinh = [
        n.lineno for n in ast.walk(cay)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
        and id(n) not in bo_qua
        and re.search(r"graph\.facebook\.com/v\d", n.value)
    ]
    assert dinh == [2], "phải bắt dòng 2 (mã thật) và bỏ qua dòng 1 (docstring)"


def test_moi_noi_deu_lay_cung_mot_gia_tri():
    from agent.api.oauth_meta import GRAPH_VERSION
    from agent.channels.dang_ky_webhook_meta import GRAPH_BASE
    from agent.config import settings
    from agent.publish.meta import GRAPH

    assert GRAPH_VERSION == settings.graph_version
    assert GRAPH_BASE == settings.graph_base
    assert GRAPH == settings.graph_base


def test_doi_mot_dong_la_doi_toan_he_thong(monkeypatch):
    """
    Phép thử thật của "một nguồn": đổi cấu hình thì mọi chỗ đi theo.

    `GRAPH_VERSION` và `GRAPH` đọc giá trị lúc nạp module nên không đổi theo
    — nhưng `graph_base` là property, và đó là thứ các adapter dựng URL từ đó
    tại thời điểm gọi.
    """
    from agent.config import settings

    monkeypatch.setattr(settings, "graph_version", "v99.0")
    assert settings.graph_base == "https://graph.facebook.com/v99.0"


def test_adapter_dung_nguon_chung_khi_khong_khai_rieng():
    """
    Credential vẫn được phép ghim `api_base` cho MỘT tài khoản — có ca cần
    ghim để gỡ lỗi. Nhưng mặc định thì cả hệ thống đi cùng phiên bản.
    """
    import inspect

    from agent.channels import messenger, meta_channels

    for mod in (messenger, meta_channels):
        nguon = inspect.getsource(mod)
        assert "settings.graph_base" in nguon, (
            f"{mod.__name__} không rơi về nguồn chung"
        )
