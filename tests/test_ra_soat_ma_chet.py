"""
Quét cả repo tìm những khuôn lỗi đã LẶP LẠI, không đi mò từng chỗ.

Hai ngày qua, năm lỗi nghiêm trọng nhất đều thuộc đúng ba khuôn:

  1. KHẢ NĂNG CÓ SẴN NHƯNG KHÔNG NỐI VÀO ĐƯỜNG CHẠY
     hàm nạp tồn kho, lưới chặn mã lạ, thị giác của mô hình, Instagram
     trong OAuth, `queue_file` cho nhân viên — cả năm đều viết xong rồi
     không ai gọi.

  2. CHO QUA KHI CHƯA CẤU HÌNH
     `doc_thach_thuc`, `kiem_bi_mat_webhook`, `/webhook/{kenh}` — cả ba
     từng mở toang khi bí mật để trống.

  3. NUỐT LỖI IM LẶNG
     `except Exception: pass` — không nổ, không nhật ký, không ai biết.

Test từng chỗ thì lần sau lỗi mọc ở chỗ mới. Quét theo KHUÔN thì không.
"""
from __future__ import annotations

import io
import pathlib
import re
import tokenize

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _chi_ma(src: str) -> str:
    ra = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            ra.append(t.string)
    except (tokenize.TokenError, IndentationError):
        return " ".join(d for d in src.splitlines()
                        if not d.strip().startswith("#"))
    return " ".join(ra)


# ---------------------------------------------------------------
#  Khuôn 3: nuốt lỗi im lặng
# ---------------------------------------------------------------

def test_khong_con_nuot_loi_im_lang_o_bat_ky_dau():
    xau = []
    for f in sorted((ROOT / "agent").rglob("*.py")):
        gon = _chi_ma(f.read_text(encoding="utf-8")).replace(" ", "")
        if "exceptException:pass" in gon or "except:pass" in gon:
            xau.append(str(f.relative_to(ROOT)))
    assert not xau, "nuốt lỗi im lặng tại: " + ", ".join(xau)


# ---------------------------------------------------------------
#  Khuôn 1: khai rồi không nối
# ---------------------------------------------------------------

def test_moi_vong_nen_deu_duoc_dung_luc_khoi_dong():
    """
    Viết một vòng nền mà quên dựng nó là mã chết — và mã chết ở đây nghĩa là
    một việc bảo trì KHÔNG BAO GIỜ chạy: tồn kho không nạp, phiên không dọn,
    token không được canh hạn.
    """
    import inspect

    from agent import main

    than_lifespan = inspect.getsource(main.lifespan)
    for ten in dir(main):
        if not ten.endswith("_loop"):
            continue
        # Tìm `ten(` chứ không `ten()`: vòng nhận tham số được gọi trên
        # nhiều dòng. Bản đầu của test này soi `ten()` nên báo nhầm ba vòng
        assert f"{ten}(" in than_lifespan, (
            f"`{ten}` được khai nhưng không ai dựng lúc khởi động"
        )


def test_moi_cau_hinh_deu_co_noi_doc():
    """
    Cấu hình khai rồi không ai đọc là một CÔNG TẮC NÓI DỐI: người vận hành
    đặt nó, không có gì xảy ra, rồi đi tìm nguyên nhân ở chỗ khác.

    `NHIP_NGUOI_THAT` từng như vậy — chú thích ghi "tắt đi thì gửi một cục",
    mà tắt cũng không có tác dụng gì.
    """
    cfg = (ROOT / "agent" / "config.py").read_text(encoding="utf-8")
    ten = re.findall(r"^\s{4}([a-z_]+):\s", cfg, re.M)

    tat = " ".join(
        p.read_text(encoding="utf-8")
        for thu_muc in ("agent", "scripts")
        for p in (ROOT / thu_muc).rglob("*.py")
    )
    # Ba biến dưới đây được cấu hình cho công cụ NGOÀI đọc, hoặc giữ cho
    # tương thích ngược; chúng không phải công tắc điều khiển hành vi.
    MIEN = {"model_hard", "messenger_page_id", "langfuse_host"}

    thua = [t for t in ten
            if t not in MIEN and len(re.findall(r"\b" + t + r"\b", tat)) <= 1]
    assert not thua, "cấu hình không ai đọc: " + ", ".join(thua)


# ---------------------------------------------------------------
#  Giao diện: class dùng mà không có kiểu
# ---------------------------------------------------------------

def test_moi_class_dung_trong_giao_dien_deu_co_CSS():
    """
    Class không có kiểu thì phần tử rơi về mặc định — và mặc định trong một
    lưới CSS thường là SAI CHỖ. Đó đúng là lỗi `.msg--system` hiện bên trái
    như tin của khách.
    """
    js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "app.css").read_text(encoding="utf-8")

    dung = set()
    for m in re.finditer(r'class="([^"$]*)"', js + html):
        dung.update(c for c in m.group(1).split() if c and not c.startswith("${"))
    for m in re.finditer(r'classList\.(?:add|toggle|remove)\("([a-z0-9_-]+)"', js):
        dung.add(m.group(1))

    co = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
    # `is-*` là cờ trạng thái, luôn đi kèm một class gốc đã có kiểu.
    thieu = sorted(c for c in dung - co if not c.startswith("is-"))
    assert not thieu, "class dùng nhưng không có CSS: " + ", ".join(thieu)
