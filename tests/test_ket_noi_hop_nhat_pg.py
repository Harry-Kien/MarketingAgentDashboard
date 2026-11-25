"""
Kết nối hợp nhất trên Postgres THẬT: trạng thái hợp nhất + lời giải thích ở
`/suc-khoe-tong`, dòng thời gian một tài khoản gộp ba sổ, lịch sử cấu hình
lọc theo thời gian ở máy chủ.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4


def _ghi_suc_khoe(app_that, tk: str, *ds: tuple[str, str, dict]):
    from agent.omnichannel.account_repository import PostgresAccountRepository
    from agent.omnichannel.accounts import AccountStatus
    from tests.test_nghiem_thu_saas import _sql

    async def ghi():
        repo = PostgresAccountRepository()
        for status, code, detail in ds:
            await repo.record_health(UUID(tk), status=AccountStatus(status), code=code, detail=detail)
        cuoi = AccountStatus(ds[-1][0])
        await repo.update_status(UUID(tk), cuoi, actor_id=UUID(int=0))
    _sql(app_that, ghi)


def test_suc_khoe_tong_tra_mot_trang_thai_va_giai_thich(app_that):
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao

    qt = _quan_tri_vao(app_that)
    tot = _kenh_webchat(qt, ten="Web tốt")
    hong = _kenh_webchat(qt, ten="Web hỏng")
    _ghi_suc_khoe(app_that, hong, ("degraded", "provider.unreachable", {"ly_do": "ECONNREFUSED 3210"}))

    d = qt.get("/api/channel-accounts/suc-khoe-tong").json()
    a = next(k for k in d["kenh"] if k["id"] == tot)
    b = next(k for k in d["kenh"] if k["id"] == hong)
    assert (a["trang_thai"], a["nhan_trang_thai"], a["giai_thich"]) == ("hoat_dong", "Hoạt động", None)
    assert (b["trang_thai"], b["nhan_trang_thai"]) == ("loi", "Lỗi")
    g = b["giai_thich"]
    assert g["ma"] == "provider.unreachable" and g["ly_do_goc"] == "ECONNREFUSED 3210"
    assert g["tieu_de"] and g["cach_sua"] and "provider." not in g["tieu_de"]
    assert d["dem_trang_thai"]["loi"] >= 1 and d["dem_trang_thai"]["hoat_dong"] >= 1
    assert d["nhan_trang_thai"]["can_xac_thuc"] == "Cần xác thực lại"


def test_dong_thoi_gian_gop_ba_so_va_bo_nhip_tim(app_that):
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, ten="Web dòng thời gian")
    # Ba nhịp "đã kết nối" liền nhau + một lần mất: chỉ hai lần ĐỔI được hiện.
    _ghi_suc_khoe(app_that, tk,
                  ("active", "provider.ok", {}), ("active", "provider.ok", {}),
                  ("active", "provider.ok", {}),
                  ("degraded", "provider.unreachable", {"ly_do": "mất mạng"}))
    r = qt.get(f"/api/ket-noi/kenh/{tk}/dong-thoi-gian")
    assert r.status_code == 200, r.text
    d = r.json()
    sk = [x for x in d["su_kien"] if x["loai"] == "suc_khoe"]
    assert [x["tieu_de"] for x in sk] == ["Lỗi", "Hoạt động"]
    assert sk[0]["mo_ta"] and sk[0]["ky_thuat"]["code"] == "provider.unreachable"
    loai = {x["loai"] for x in d["su_kien"]}
    assert {"suc_khoe", "su_kien", "cau_hinh"} <= loai, loai
    # Sự kiện mang nhãn tiếng Việt, không phải kind thô.
    ev = [x for x in d["su_kien"] if x["loai"] == "su_kien"]
    assert all("." not in x["tieu_de"] for x in ev), [x["tieu_de"] for x in ev]
    # Mới nhất trước.
    luc = [x["luc"] for x in d["su_kien"]]
    assert luc == sorted(luc, reverse=True)
    # Lọc theo loại.
    chi = qt.get(f"/api/ket-noi/kenh/{tk}/dong-thoi-gian?loai=cau_hinh").json()["su_kien"]
    assert chi and {x["loai"] for x in chi} == {"cau_hinh"}
    # Ngoài phạm vi: 404.
    assert qt.get(f"/api/ket-noi/kenh/{uuid4()}/dong-thoi-gian").status_code == 404


def test_dong_thoi_gian_khong_quyen_cau_hinh_thi_khong_co_so_cau_hinh(app_that):
    from agent import ket_noi_tich_hop as kn
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao, _sql

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, ten="Web không quyền cấu hình")

    async def doc():
        return await kn.dong_thoi_gian(UUID(tk), xem_cau_hinh=False)
    assert all(x["loai"] != "cau_hinh" for x in _sql(app_that, doc))


def test_lich_su_cau_hinh_loc_thoi_gian_o_may_chu(app_that):
    from tests.test_nghiem_thu_saas import _kenh_webchat, _quan_tri_vao

    qt = _quan_tri_vao(app_that)
    _kenh_webchat(qt, ten="Web lịch sử")
    co = qt.get("/api/ket-noi/lich-su", params={"dich_vu": "webchat", "gioi_han": 200}).json()
    assert any(x["hanh_dong"] == "tao" for x in co)
    # Tên trường kỹ thuật của thao tác kênh có nhãn đọc được.
    assert any(x["nhan_truong"] == "tài khoản kênh" for x in co)
    tuong_lai = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert qt.get("/api/ket-noi/lich-su", params={"tu": tuong_lai}).json() == []
    qua_khu = datetime.now(timezone.utc) - timedelta(days=1)
    cu = qt.get("/api/ket-noi/lich-su", params={"den": qua_khu.isoformat(), "dich_vu": "webchat"}).json()
    assert all(datetime.fromisoformat(x["sua_luc"]) < qua_khu for x in cu)
