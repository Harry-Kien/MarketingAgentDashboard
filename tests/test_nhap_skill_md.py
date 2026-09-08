"""
Nhập gói theo chuẩn Agent Skills: thư mục hoặc zip có `SKILL.md`.

VÌ SAO THÊM ĐƯỜNG NÀY
---------------------
Định dạng `goi.json` của repo không sai, nhưng nó là định dạng RIÊNG. Chuẩn
Agent Skills (platform.claude.com/docs/en/agents-and-tools/agent-skills) là
một thư mục có `SKILL.md`, YAML frontmatter hai trường bắt buộc `name` và
`description`, thân file là hướng dẫn markdown, kèm các `.md` khác và thư
mục `scripts/`. Ai đã quen chuẩn ấy, hoặc muốn lấy skill từ kho mở của
Anthropic, hiện phải viết lại từ đầu.

Nhập chứ không THAY: `goi.json` giữ nguyên. Nó mang những thứ chuẩn kia
không có và repo này cần — `tu_khoa` để kích hoạt tất định, `cong_cu` là
bản mô tả plugin đã qua bộ kiểm, và `phien_ban` cho lịch sử/khôi phục.

VÌ SAO `scripts/` BỊ TỪ CHỐI, KHÔNG PHẢI BỎ QUA
-----------------------------------------------
Chuẩn kia cho phép skill mang mã chạy được; repo này cấm, và đó là ràng
buộc gốc chứ không phải thiếu sót — xem CLAUDE.md và `ban_mo_ta.py`. Bỏ
qua thư mục ấy trong im lặng là nhận một gói rồi chạy nó với ít năng lực
hơn người viết tưởng: skill dựa vào script sẽ hỏng giữa chừng, không ai
biết vì sao. Từ chối và nói thẳng thì họ đọc được lý do.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.ky_nang.goi import doc_goi  # noqa: E402
from agent.ky_nang.nhap_skill_md import LoiSkillMd, tu_skill_md  # noqa: E402

SKILL = """---
name: tu-van-chong-nang
description: Tư vấn chọn và dùng kem chống nắng theo hoàn cảnh của khách. Dùng khi khách hỏi về chống nắng, SPF, hoặc đi biển.
---

# Tư vấn chống nắng

Khi khách hỏi về kem chống nắng, hỏi hoàn cảnh dùng trước rồi mới gợi ý.
Chỉ nêu chỉ số có trong tài liệu. Không nhận xét về tình trạng da của khách.
"""

NHAN = """# Cách đọc nhãn

SPF là mức bảo vệ trước tia UVB. PA với số dấu cộng là mức bảo vệ trước UVA.
Lượng dùng đủ cho mặt và cổ tương đương hai đốt ngón tay.
"""


def _zip(files: dict[str, str]) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for ten, noi_dung in files.items():
            z.writestr(ten, noi_dung)
    return b.getvalue()


# --- Đọc đúng chuẩn ---------------------------------------------------

def test_doc_duoc_skill_md_toi_thieu():
    g = tu_skill_md(_zip({"SKILL.md": SKILL}))
    assert g["ten"] == "tu-van-chong-nang"
    assert "kem chống nắng" in g["huong_dan"]
    assert g["mo_ta"].startswith("Tư vấn chọn")


def test_ket_qua_nap_duoc_bang_doc_goi():
    """Thứ trả về phải là thứ `doc_goi` nhận, không phải một hình gần đúng."""
    g = doc_goi(tu_skill_md(_zip({"SKILL.md": SKILL})))
    assert g.ten == "tu-van-chong-nang"
    assert g.tu_khoa


def test_md_khac_thanh_tai_lieu():
    g = tu_skill_md(_zip({"SKILL.md": SKILL, "NHAN.md": NHAN}))
    assert len(g["tai_lieu"]) == 1
    assert g["tai_lieu"][0]["tieu_de"] == "Cách đọc nhãn"
    assert "SPF" in g["tai_lieu"][0]["noi_dung"]


def test_thu_muc_long_cung_doc_duoc():
    """Nén cả thư mục thì mọi đường dẫn có một tầng cha — đó là cách người
    ta nén, và bắt họ nén lại là bắt sai chỗ."""
    g = tu_skill_md(_zip({"tu-van/SKILL.md": SKILL, "tu-van/NHAN.md": NHAN}))
    assert g["ten"] == "tu-van-chong-nang" and len(g["tai_lieu"]) == 1


# --- Từ khoá: chỗ hai chuẩn khác nhau ---------------------------------

def test_khong_khai_tu_khoa_thi_sinh_tu_ten():
    """
    Chuẩn kia để MÔ HÌNH đọc `description` rồi tự quyết; repo này so từ
    khoá tất định. Không sinh gì thì gói cài xong không bao giờ kích hoạt,
    và dashboard vẫn hiện "đang bật" — đúng kiểu hỏng im lặng.
    """
    g = tu_skill_md(_zip({"SKILL.md": SKILL}))
    assert g["tu_khoa"], "không có từ khoá thì gói cài xong không bao giờ kích hoạt"
    assert any("nang" in t.lower() for t in g["tu_khoa"]), g["tu_khoa"]


def test_khai_keywords_thi_dung_dung_no():
    s = SKILL.replace("---\nname:", "---\nkeywords: [chống nắng, SPF, đi biển]\nname:")
    g = tu_skill_md(_zip({"SKILL.md": s}))
    assert g["tu_khoa"] == ["chống nắng", "SPF", "đi biển"]


# --- Từ chối rõ ràng --------------------------------------------------

def test_co_scripts_thi_tu_choi_va_noi_ly_do():
    with pytest.raises(LoiSkillMd) as e:
        tu_skill_md(_zip({"SKILL.md": SKILL, "scripts/lam.py": "print(1)"}))
    assert "scripts" in str(e.value)


def test_thieu_SKILL_md():
    with pytest.raises(LoiSkillMd) as e:
        tu_skill_md(_zip({"README.md": "xin chào"}))
    assert "SKILL.md" in str(e.value)


def test_thieu_frontmatter():
    with pytest.raises(LoiSkillMd):
        tu_skill_md(_zip({"SKILL.md": "# Không có frontmatter\n\nnội dung"}))


def test_thieu_name_hoac_description():
    with pytest.raises(LoiSkillMd):
        tu_skill_md(_zip({"SKILL.md": "---\nname: a-b-c\n---\n\nnội dung dài hơn năm mươi ký tự cho đủ hướng dẫn."}))


def test_frontmatter_hong_bao_ro_chu_khong_nem_yaml():
    """Người vận hành đọc được "YAML hỏng ở dòng 3", không đọc được một
    vết ngăn xếp của thư viện."""
    with pytest.raises(LoiSkillMd) as e:
        tu_skill_md(_zip({"SKILL.md": "---\nname: [a\ndescription: x\n---\n\nnội dung"}))
    assert "SKILL.md" in str(e.value)


# --- Ràng buộc của chuẩn được giữ -------------------------------------

def test_ten_sai_dang_bi_tu_choi():
    """`name`: chỉ chữ thường, số, gạch ngang, tối đa 64 ký tự."""
    s = SKILL.replace("tu-van-chong-nang", "Tư Vấn Chống Nắng")
    with pytest.raises(LoiSkillMd):
        tu_skill_md(_zip({"SKILL.md": s}))


def test_ten_chua_tu_danh_rieng_bi_tu_choi():
    for cam in ("claude-abc", "anthropic-abc"):
        with pytest.raises(LoiSkillMd):
            tu_skill_md(_zip({"SKILL.md": SKILL.replace("tu-van-chong-nang", cam)}))
