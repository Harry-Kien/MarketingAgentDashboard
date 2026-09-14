"""
MA TRẬN "AI THẤY GÌ VỀ KHÁCH" — đo trên app thật, Postgres thật.

Đây là câu hỏi sống còn của một CRM doanh nghiệp: ai được thấy TÊN khách,
ai được thấy SỐ ĐIỆN THOẠI và EMAIL, ai không được thấy gì cả.

Hệ thống có BA TRỤC chặn độc lập, và chúng dễ bị nhầm là một:

  1. KÊNH   `account_memberships` — không là thành viên kênh thì không thấy
            khách của kênh ấy. Trục cứng nhất, luôn áp dụng.
  2. QUYỀN  `khach.doc` để xem danh sách; `khach.xem_tat_ca` để vượt trục 1;
            `khach.pii` cho ba route tra cứu PDPD (KHÔNG phải cho danh sách).
  3. TẦM NHÌN  bốn mức, chỉ áp dụng cho khách ĐÃ GIAO cho ai đó.

Còn PII trong danh sách khách lại do một thứ thứ tư quyết định: VAI TRÒ
TRONG KÊNH (`account_memberships.role` = owner/manager). Ba tên gọi khác
nhau cho ba thứ khác nhau, và bộ test này ghim từng cái xuống bằng số liệu
thật thay vì bằng cách đọc mã.

Mỗi test là một hàng của ma trận. Hỏng một hàng là một cách rò dữ liệu
khách hàng — hoặc một cách khoá nhân viên khỏi việc của họ.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _nhan_vien_moi, _quan_tri_vao, _sql, _them_thanh_vien,
)

SDT = "0909123456"
EMAIL = "chihoa@example.com"


def _khach_co_pii(app, qt, tk: str, ten: str = "Chị Hoa") -> str:
    """
    Một khách có SĐT và email thật để đo việc che.

    Đặt thẳng vào CSDL: không có endpoint sửa PII của khách, và dựng dữ liệu
    qua đúng con đường agent ghi vào (webhook -> contacts) rồi bổ sung hai
    cột là cách gần thực tế nhất mà không phải gọi model.
    """
    from agent import db

    _khach_nhan(app, tk, ten, "Shop còn hàng không?")
    cid = next(c["id"] for c in qt.get("/api/contacts").json() if c["display_name"] == ten)

    async def dat(cid_: str):
        await db.execute(
            "UPDATE contacts SET phone = $2, email = $3 WHERE id = $1::uuid",
            cid_, SDT, EMAIL)
    _sql(app, dat, cid)
    return cid


def _thay(nguoi, cid: str) -> dict | None:
    return next((c for c in nguoi.get("/api/contacts").json() if c["id"] == cid), None)


# ---------------------------------------------------------------- trục 1: KÊNH

def test_khong_la_thanh_vien_kenh_thi_khong_thay_ten_khach(app_that):
    """
    Trục cứng nhất. Nhân viên có đủ quyền `khach.doc` nhưng không được vào
    kênh thì không thấy khách của kênh ấy — kể cả tên.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    _, ngoai = _nhan_vien_moi(qt, "ngoai")          # không cho vào kênh nào

    assert ngoai.get("/api/contacts").json() == []
    # Và mở thẳng bằng id cũng không được: chặn ở máy chủ, không phải ẩn nút.
    assert ngoai.get(f"/api/contacts/{cid}").status_code == 404


def test_vao_kenh_roi_thi_thay_ten(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    uid, nv = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, uid)

    k = _thay(nv, cid)
    assert k is not None and k["display_name"] == "Chị Hoa"


# ---------------------------------------------------------------- trục PII

def test_thanh_vien_thuong_KHONG_thay_sdt_va_email(app_that):
    """
    `role='agent'` thấy tên khách nhưng SĐT/email bị che. Đây là mặc định
    an toàn: nhân viên trả lời khách không cần số điện thoại của họ.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    uid, nv = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, uid, role="agent")

    k = _thay(nv, cid)
    assert k["pii_masked"] is True
    # Che GIỮ BA SỐ CUỐI (`*******456`) có chủ ý: nhân viên đối chiếu được
    # "đúng chị Hoa số đuôi 456" khi khách đọc số qua điện thoại, mà không
    # cầm được số đầy đủ để mang đi. Che sạch thành `***` thì họ phải hỏi
    # quản trị mỗi lần — và đường đi vòng ấy mới là chỗ dữ liệu rò ra.
    assert k["phone"].startswith("*") and k["phone"] != SDT
    assert SDT[:6] not in k["phone"]
    assert k["email"] != EMAIL and EMAIL.split("@")[0] not in k["email"]


def test_manager_kenh_THI_thay_sdt_va_email(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    uid, nv = _nhan_vien_moi(qt, "truong")
    _them_thanh_vien(app_that, tk, uid, role="manager")

    k = _thay(nv, cid)
    assert k["pii_masked"] is False
    assert k["phone"] == SDT and k["email"] == EMAIL


def test_quyen_khach_pii_KHONG_mo_sdt_trong_danh_sach(app_that):
    """
    ĐIỂM DỄ HIỂU NHẦM NHẤT, ghim lại bằng số liệu.

    Nhãn của quyền `khach.pii` là "Xem số điện thoại, email, địa chỉ", nên
    người quản trị tick nó và tin rằng nhân viên ấy giờ đọc được SĐT trong
    màn Khách hàng. KHÔNG: danh sách che PII theo VAI TRÒ TRONG KÊNH, còn
    `khach.pii` mở ba route tra cứu PDPD (tìm theo số điện thoại).

    Hai thứ khác nhau, và nếu ngày nào đó chúng được gộp thì phải gộp có
    chủ ý — không phải vì ai đó đọc nhãn rồi sửa cho "khớp".
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    uid, nv = _nhan_vien_moi(qt, "lan")             # vai trò Nhân viên CÓ khach.pii
    _them_thanh_vien(app_that, tk, uid, role="agent")

    assert "khach.pii" in nv.get("/api/toi").json()["quyen"]
    assert _thay(nv, cid)["pii_masked"] is True     # vẫn che
    # …nhưng route PDPD thì mở, và đó mới là chỗ quyền ấy có tác dụng.
    assert nv.get(f"/api/pdpd/{SDT}").status_code == 200


def test_khong_co_khach_pii_thi_route_pdpd_bi_chan(app_that):
    qt = _quan_tri_vao(app_that)
    vt = qt.post("/api/vai-tro", json={
        "ten": "Chỉ xem khách", "mo_ta": "", "quyen": ["khach.doc"]}).json()
    uid, nv = _nhan_vien_moi(qt, "hep", vai_tro=None)
    assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro",
                  json={"vai_tro": [vt["id"]]}).status_code == 200

    assert nv.get(f"/api/pdpd/{SDT}").status_code == 403


# ---------------------------------------------------------------- trục QUYỀN

def test_khong_co_khach_doc_thi_khong_vao_duoc_danh_sach(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_co_pii(app_that, qt, tk)
    vt = qt.post("/api/vai-tro", json={
        "ten": "Chỉ hội thoại", "mo_ta": "", "quyen": ["hoi_thoai.doc"]}).json()
    uid, nv = _nhan_vien_moi(qt, "chihoithoai", vai_tro=None)
    qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [vt["id"]]})
    _them_thanh_vien(app_that, tk, uid)

    assert nv.get("/api/contacts").status_code == 403


def test_khong_co_vai_tro_nao_thi_dang_nhap_duoc_ma_khong_thay_gi(app_that):
    """Hỏng-đóng: không được cấp thì không thấy, chứ không phải thấy rồi bị chặn."""
    qt = _quan_tri_vao(app_that)
    _, nv = _nhan_vien_moi(qt, "trong", vai_tro=None)

    assert nv.get("/api/toi").status_code == 200        # vẫn đăng nhập được
    assert nv.get("/api/contacts").status_code == 403
    assert nv.get("/api/inbox/conversations").status_code == 403


def test_xem_tat_ca_vuot_duoc_truc_kenh_va_thay_pii(app_that):
    """Quyền dành cho trưởng nhóm: thấy khách mọi kênh, và thấy PII."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    vt = qt.post("/api/vai-tro", json={
        "ten": "Trưởng nhóm", "mo_ta": "",
        "quyen": ["khach.doc", "khach.xem_tat_ca"]}).json()
    uid, nv = _nhan_vien_moi(qt, "sep2", vai_tro=None)
    qt.put(f"/api/nguoi-dung/{uid}/vai-tro", json={"vai_tro": [vt["id"]]})
    # KHÔNG cho vào kênh nào — `xem_tat_ca` phải tự vượt được trục kênh.

    k = _thay(nv, cid)
    assert k is not None and k["pii_masked"] is False and k["phone"] == SDT


# ---------------------------------------------------------------- trục TẦM NHÌN

def test_muc_an_thi_khach_cua_nguoi_khac_bien_mat_khoi_danh_sach(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app_that, tk, lan_id)
    _them_thanh_vien(app_that, tk, minh_id)
    qt.put(f"/api/contacts/{cid}/chu-so-huu",
           json={"owner_user_id": lan_id, "ly_do": "Phân công"})

    assert qt.put("/api/tam-nhin-khach", json={"muc": "an"}).status_code == 200
    assert _thay(minh, cid) is None          # người khác: biến mất
    assert _thay(lan, cid) is not None       # chủ: vẫn thấy


def test_muc_an_noi_dung_thi_thay_ten_nhung_khong_thay_pii(app_that):
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    lan_id, _ = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app_that, tk, lan_id)
    # `manager` để chứng minh mức tầm nhìn SIẾT ĐƯỢC cả người vốn xem được PII.
    _them_thanh_vien(app_that, tk, minh_id, role="manager")
    qt.put(f"/api/contacts/{cid}/chu-so-huu",
           json={"owner_user_id": lan_id, "ly_do": "Phân công"})

    assert qt.put("/api/tam-nhin-khach", json={"muc": "an_noi_dung"}).status_code == 200
    k = _thay(minh, cid)
    assert k is not None and k["display_name"] == "Chị Hoa"   # vẫn thấy TÊN
    assert k["pii_masked"] is True and k["phone"] != SDT      # nhưng mất PII
    assert k["an_noi_dung"] is True


def test_mau_nhan_su_noi_ra_ai_doc_duoc_sdt(app_that):
    """
    Quản trị phải BIẾT ai đang đọc được số điện thoại khách, không phải tự
    đi đọc bảng trong CSDL. `so_kenh_pii` là con số ấy.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    thuong_id, _ = _nhan_vien_moi(qt, "lan")
    truong_id, _ = _nhan_vien_moi(qt, "truong")
    _them_thanh_vien(app_that, tk, thuong_id, role="agent")
    _them_thanh_vien(app_that, tk, truong_id, role="manager")

    ds = {n["id"]: n for n in qt.get("/api/nguoi-dung").json()["nguoi_dung"]}
    assert ds[thuong_id]["so_kenh"] == 1 and ds[thuong_id]["so_kenh_pii"] == 0
    assert ds[truong_id]["so_kenh"] == 1 and ds[truong_id]["so_kenh_pii"] == 1


def test_dat_muc_trong_kenh_qua_api_nhan_su(app_that):
    """
    Đường DUY NHẤT trên giao diện để cấp quyền đọc PII cho một kênh cụ thể.
    Không có nó, quản trị chỉ còn cách cấp `khach.xem_tat_ca` — thứ mở toang
    danh bạ của MỌI kênh.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)
    uid, nv = _nhan_vien_moi(qt, "truong")

    assert qt.put(f"/api/nguoi-dung/{uid}/kenh",
                  json={"kenh": [tk], "role": "agent"}).status_code == 200
    assert _thay(nv, cid)["pii_masked"] is True

    assert qt.put(f"/api/nguoi-dung/{uid}/kenh",
                  json={"kenh": [tk], "role": "manager"}).status_code == 200
    k = _thay(nv, cid)
    assert k["pii_masked"] is False and k["phone"] == SDT


def test_khach_chua_giao_luon_la_cua_chung(app_that):
    """Bỏ vế này là khách mới nhắn tới thành vô hình với tất cả mọi người."""
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    cid = _khach_co_pii(app_that, qt, tk)                  # chưa giao cho ai
    uid, nv = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, uid)

    assert qt.put("/api/tam-nhin-khach", json={"muc": "an"}).status_code == 200
    assert _thay(nv, cid) is not None
