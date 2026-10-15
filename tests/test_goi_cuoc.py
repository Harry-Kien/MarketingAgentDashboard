"""
Gói cước và hạn mức — vượt gói phải NÓI RA, không được im lặng.

- 0 = không giới hạn: bản chạy một cửa hàng như hiện nay không đổi gì.
- Thêm kênh / nhân viên vượt gói: lỗi nói rõ gói cho tối đa bao nhiêu.
- Hết lượt AI tháng: hội thoại MỚI chuyển người; hội thoại đã có AI trả lời
  trong tháng KHÔNG bị cắt giữa chừng.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from agent import goi_cuoc


@pytest.fixture
def goi(monkeypatch):
    hop = {"kenh": 0, "nhan_vien": 0, "ai": 0, "da_co": False}

    async def fetchrow(sql, *a):
        if "da_co" in sql:
            return {"da_co": hop["da_co"], "da_dung": hop["ai"]}
        return {"kenh": hop["kenh"], "nhan_vien": hop["nhan_vien"], "hoi_thoai_ai_thang": hop["ai"]}

    monkeypatch.setattr(goi_cuoc.db, "fetchrow", fetchrow)

    def dat(ten="co_ban", kenh=0, nv=0, ai=0):
        monkeypatch.setattr(goi_cuoc.settings, "goi_cuoc", ten)
        monkeypatch.setattr(goi_cuoc.settings, "gioi_han_kenh", kenh)
        monkeypatch.setattr(goi_cuoc.settings, "gioi_han_nhan_vien", nv)
        monkeypatch.setattr(goi_cuoc.settings, "gioi_han_hoi_thoai_ai_thang", ai)
    hop["dat"] = dat
    return hop


def test_khong_dat_gi_la_khong_gioi_han(goi):
    goi["dat"]("khong_gioi_han")
    goi.update(kenh=999, nhan_vien=999, ai=99999)
    asyncio.run(goi_cuoc.kiem_them_kenh())
    asyncio.run(goi_cuoc.kiem_them_nhan_vien())
    assert asyncio.run(goi_cuoc.con_luot_ai(uuid.uuid4())) is True


def test_vuot_kenh_va_nhan_vien_noi_ro(goi):
    goi["dat"]("co_ban", kenh=3, nv=5)
    goi.update(kenh=3, nhan_vien=5)
    with pytest.raises(goi_cuoc.VuotHanMuc, match="tối đa 3 tài khoản kênh"):
        asyncio.run(goi_cuoc.kiem_them_kenh())
    with pytest.raises(goi_cuoc.VuotHanMuc, match="tối đa 5 nhân viên"):
        asyncio.run(goi_cuoc.kiem_them_nhan_vien())
    goi.update(kenh=2, nhan_vien=4)
    asyncio.run(goi_cuoc.kiem_them_kenh())
    asyncio.run(goi_cuoc.kiem_them_nhan_vien())


def test_het_luot_ai_khong_cat_hoi_thoai_dang_do(goi):
    goi["dat"]("dung_thu", ai=200)
    goi.update(ai=200, da_co=False)
    assert asyncio.run(goi_cuoc.con_luot_ai(uuid.uuid4())) is False
    goi["da_co"] = True
    assert asyncio.run(goi_cuoc.con_luot_ai(uuid.uuid4())) is True


def test_agent_bat_chuyen_nguoi_khi_het_luot(goi, monkeypatch):
    from agent.core import agent_bat
    monkeypatch.setattr(agent_bat.runtime, "enabled", lambda: True)
    goi["dat"]("dung_thu", ai=1)
    goi.update(ai=1, da_co=False)
    kq = asyncio.run(agent_bat.agent_duoc_tra_loi(None, {"id": uuid.uuid4(), "status": "auto",
                                                          "mode": "auto"}))
    assert not kq.duoc and "Hết lượt hội thoại AI" in kq.ly_do


def test_tao_kenh_vuot_goi_la_402():
    import inspect

    from agent.api import channel_accounts
    src = inspect.getsource(channel_accounts._raise_public)
    assert "VuotHanMuc" in src and "402" in src


# ---------------- mặt phẳng điều khiển ----------------

def test_doi_goi_chi_sua_dong_goi_giu_phan_con_lai():
    from scripts import cua_hang as ch
    env = "DATABASE_URL=x\nGOI_CUOC=dung_thu\nGIOI_HAN_KENH=2\nWEBHOOK_SECRET=bi-mat\n"
    moi = ch.dat_goi_env(env, "chuyen_nghiep")
    assert "DATABASE_URL=x" in moi and "WEBHOOK_SECRET=bi-mat" in moi
    assert "GOI_CUOC=chuyen_nghiep" in moi and "GIOI_HAN_KENH=10" in moi
    assert "GIOI_HAN_NHAN_VIEN=20" in moi and "GIOI_HAN_HOI_THOAI_AI_THANG=8000" in moi
    assert moi.count("GIOI_HAN_KENH=") == 1
    with pytest.raises(ch.LoiCuaHang):
        ch.dat_goi_env(env, "kim_cuong")


def test_cua_hang_moi_bat_dau_o_goi_dung_thu():
    from scripts import cua_hang as ch
    env = ch.sinh_tep("shopa", "shopa.vi-du.vn", ch.sinh_bi_mat())[".env"]
    k, nv, ai = ch.GOI["dung_thu"]
    assert "GOI_CUOC=dung_thu" in env
    assert f"GIOI_HAN_KENH={k}" in env and f"GIOI_HAN_HOI_THOAI_AI_THANG={ai}" in env
