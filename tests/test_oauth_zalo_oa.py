"""
Canh luồng nối Zalo OA bằng OAuth.

Mỗi test ở đây canh một cách hỏng CỤ THỂ đã cân nhắc lúc viết, không phải
canh "hàm có chạy không". Đọc tên test là biết mất cái gì khi nó đỏ.
"""
from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException

from agent.api import oauth_zalo_oa as oz
from agent.core import quyen


# ---------------- PKCE ----------------

def test_thach_thuc_dung_cong_thuc_pkce():
    """
    Sai công thức thì Zalo từ chối ở bước ĐỔI TOKEN — cách chỗ sai hai
    request và một lần chuyển trang, nên rất khó lần ngược.
    """
    verifier = "abc123-_xyz"
    mong = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert oz.thach_thuc_tu(verifier) == mong


def test_thach_thuc_khong_co_dau_bang_dem():
    """
    RFC 7636 đòi base64url KHÔNG đệm. Còn dấu `=` là `=` bị mã hoá trong
    query string thành `%3D` và chuỗi không còn khớp nữa.
    """
    assert "=" not in oz.thach_thuc_tu("x" * 40)


def test_moi_luot_mot_verifier_khac_nhau():
    """Dùng lại verifier là biến bí mật một lần thành bí mật dùng mãi."""
    kho = oz.KhoPKCE()
    a, tha = kho.tao("u1")
    b, thb = kho.tao("u1")
    assert a != b and tha != thb


# ---------------- state ----------------

def test_state_dung_mot_lan():
    """
    Callback phát lại lần hai không được nối thêm gì. Không có tính chất
    này, một link callback bị ghi lại (log proxy, lịch sử trình duyệt) trở
    thành một nút "nối lại" bấm được mãi.
    """
    kho = oz.KhoPKCE()
    state, _ = kho.tao("u1")
    assert kho.nhan(state)[0] == "u1"
    with pytest.raises(HTTPException):
        kho.nhan(state)


def test_state_la_khong_nhan():
    kho = oz.KhoPKCE()
    with pytest.raises(HTTPException):
        kho.nhan("khong-he-ton-tai")


def test_state_het_han_bi_tu_choi(monkeypatch):
    """
    `oz.time` LÀ module `time` toàn cục, không phải bản sao. Nên phải chốt
    mốc thời gian thật TRƯỚC khi vá — gọi `time.time()` bên trong bản vá là
    gọi lại chính nó, và RecursionError không hề giống một test hỏng vì mã.
    """
    that = oz.time.time()
    kho = oz.KhoPKCE()
    state, _ = kho.tao("u1")
    monkeypatch.setattr(oz.time, "time",
                        lambda: that + oz.STATE_SONG_GIAY + 1)
    with pytest.raises(HTTPException):
        kho.nhan(state)


def test_kho_nho_dung_nguoi_bam():
    """
    `user_id` đi từ `/start` sang `/callback` qua kho này. Mất nó là tạo
    tài khoản với một actor bịa, và `account_memberships.user_id` có khoá
    ngoại — mọi lượt nối chết vì ForeignKeyViolation.
    """
    kho = oz.KhoPKCE()
    s1, _ = kho.tao("nguoi-a")
    s2, _ = kho.tao("nguoi-b")
    assert kho.nhan(s2)[0] == "nguoi-b"
    assert kho.nhan(s1)[0] == "nguoi-a"


# ---------------- URL cấp quyền ----------------

def test_url_cap_quyen_du_bon_tham_so():
    url = oz.dung_url_cap_quyen(
        app_id="app", redirect_uri="https://x.vn/cb",
        state="st", code_challenge="ch")
    q = parse_qs(urlparse(url).query)
    assert urlparse(url).netloc == "oauth.zaloapp.com"
    assert q["app_id"] == ["app"]
    assert q["redirect_uri"] == ["https://x.vn/cb"]
    assert q["state"] == ["st"]
    assert q["code_challenge"] == ["ch"]


def test_url_cap_quyen_khong_bao_gio_mang_secret():
    """
    `secret_key` đi trong HEADER lúc đổi token, KHÔNG đi trong URL. URL nằm
    trong lịch sử trình duyệt, log proxy và Referer — ba chỗ không phải kho
    bí mật.
    """
    url = oz.dung_url_cap_quyen(
        app_id="app", redirect_uri="https://x.vn/cb",
        state="st", code_challenge="ch")
    assert "secret" not in url.lower()


# ---------------- địa chỉ quay về ----------------

def test_dia_chi_quay_ve_tu_choi_http(monkeypatch):
    """
    Zalo chỉ nhận HTTPS. Để lọt `http://` là người dùng bấm nút, đi hết
    màn hình cấp quyền, rồi mới bị Zalo từ chối — thất bại ở nơi xa chỗ sai.
    """
    monkeypatch.setattr(oz.settings, "public_base_url", "http://localhost:8000")
    with pytest.raises(HTTPException):
        oz._dia_chi_quay_ve()


def test_dia_chi_quay_ve_tu_choi_khi_rong(monkeypatch):
    monkeypatch.setattr(oz.settings, "public_base_url", "")
    with pytest.raises(HTTPException):
        oz._dia_chi_quay_ve()


def test_dia_chi_quay_ve_khop_duong_callback(monkeypatch):
    """
    Địa chỉ dán vào Zalo Developers phải trỏ đúng route đang tồn tại. Lệch
    một ký tự là 404 sau khi người dùng đã cấp quyền xong.
    """
    monkeypatch.setattr(oz.settings, "public_base_url", "https://x.vn/")
    assert oz._dia_chi_quay_ve() == "https://x.vn" + oz.router.prefix + "/callback"


# ---------------- quyền ----------------

def test_callback_nam_trong_mien_tru():
    """
    Zalo gọi callback mà không mang cookie phiên. Thiếu miễn trừ này thì
    máy chủ KHÔNG KHỞI ĐỘNG được (chốt `kiem_moi_route_co_quyen`) — đỏ to,
    đúng như mong muốn, nhưng phải có test nói vì sao nó được miễn.
    """
    assert ("GET", "/api/connect/zalo-oa/callback") in quyen.MIEN_TRU


def test_start_khong_nam_trong_mien_tru():
    """
    `/start` là nơi DUY NHẤT còn kiểm quyền của luồng này. Miễn trừ nó là
    cho bất kỳ ai ngoài internet sinh state hợp lệ, và cái chốt của
    `/callback` rỗng ruột.
    """
    assert ("GET", "/api/connect/zalo-oa/start") not in quyen.MIEN_TRU


def test_start_doi_quyen_kenh_noi():
    from agent.main import app

    for r in quyen.moi_route(app.routes):
        if getattr(r, "path", "") == "/api/connect/zalo-oa/start":
            khai: set[str] = set()
            for phu in getattr(r, "dependencies", []):
                khai |= set(getattr(phu.dependency, "quyen_yeu_cau", ()))
            for phu in getattr(r.dependant, "dependencies", []):
                khai |= set(getattr(phu.call, "quyen_yeu_cau", ()))
            assert "kenh.noi" in khai
            return
    pytest.fail("không tìm thấy route /api/connect/zalo-oa/start")


# ---------------- không rò bí mật ----------------

def test_trang_ket_qua_khong_in_token():
    """
    Người dùng hay chụp màn hình trang này để hỏi, và ảnh chụp đi khắp nơi.
    """
    html = oz._trang("Xong", "<p>ok</p>").body.decode()
    assert "refresh_token" not in html and "access_token" not in html


def test_khong_lenh_goi_trang_nao_mang_token():
    """
    Canh bằng AST, không bằng cắt chuỗi: đọc ĐÚNG phạm vi mỗi lệnh gọi
    `_trang(...)` và bắt mọi tên biến chứa token xuất hiện trong đó.

    Cắt chuỗi thì cửa sổ tràn sang đoạn mã bên cạnh và báo đỏ nhầm — đã
    xảy ra ngay lần chạy đầu. Một test hay báo đỏ nhầm là một test người
    ta sẽ xoá, và xoá rồi thì cái nó canh cũng mất.
    """
    import ast
    from pathlib import Path

    cay = ast.parse(Path(oz.__file__).read_text(encoding="utf-8"))
    cam = {"token", "access_token", "refresh_token", "verifier", "secret"}
    so_goi = 0
    for nut in ast.walk(cay):
        if not (isinstance(nut, ast.Call)
                and getattr(nut.func, "id", "") == "_trang"):
            continue
        so_goi += 1
        for con in ast.walk(nut):
            ten = getattr(con, "id", None) or getattr(con, "attr", None)
            assert ten not in cam, f"_trang() đang mang `{ten}` ra màn hình"
    assert so_goi >= 3, "không thấy lệnh gọi _trang nào — test đã mất đối tượng"


# ---------------- nguồn sự thật của khoá ----------------

def test_khong_ghi_vao_bang_zalo_oa_token():
    """
    Bảng `zalo_oa_token` là chỗ cất của OA cấu hình bằng `.env` — một app,
    một token, toàn cục. Tài khoản tạo từ OAuth có credential riêng trong
    vault và xoay vòng ở đó.

    Ghi cả hai nơi là hai nguồn sự thật cho một khoá tự đổi mỗi giờ: bản
    trong vault xoay, bản trong bảng đứng yên, và thứ đọc nhầm bản đứng yên
    cầm một token đã chết — ngừng gửi được TRONG IM LẶNG.
    """
    from pathlib import Path

    ma = Path(oz.__file__).read_text(encoding="utf-8")
    ma_khong_chu_thich = "\n".join(
        d for d in ma.splitlines()
        if not d.strip().startswith("#")
    ).split('"""')
    # bỏ docstring (phần tử lẻ), chỉ giữ mã thật
    chi_ma = "".join(ma_khong_chu_thich[::2])
    assert "zalo_oa_token" not in chi_ma


def test_noi_lai_la_thay_khoa_chu_khong_tao_ban_sao():
    """
    Mỗi OA có một đường webhook riêng theo `account_id`. Nối lại mà đẻ tài
    khoản thứ hai nghĩa là địa chỉ webhook đang khai ở Zalo trỏ vào bản CŨ —
    bản có khoá đã bị vô hiệu. Gửi được, nhận không được, không ai báo.
    """
    import inspect

    ma = inspect.getsource(oz._luu_tai_khoan)
    assert "find_by_external" in ma
    assert "rotate_credentials" in ma


# ---------------- chạy trên HTTP thật ----------------

def _client(nguoi: dict):
    """
    App chỉ có router OAuth Zalo OA. Không dựng CSDL: mọi thứ chạm CSDL đều
    được thay ở từng test, nên phần đo được ở đây là HTTP và phân quyền.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agent.api import routes

    app = FastAPI()
    app.include_router(oz.router)
    app.dependency_overrides[routes.nguoi_da_dang_nhap] = lambda: nguoi
    return TestClient(app, raise_server_exceptions=False)


def _cau_hinh_du(monkeypatch):
    monkeypatch.setattr(oz.settings, "zalo_oa_app_id", "app")
    monkeypatch.setattr(oz.settings, "zalo_oa_secret_key", "sec")
    monkeypatch.setattr(oz.settings, "public_base_url", "https://x.vn")


def test_start_tu_choi_nguoi_thieu_quyen(monkeypatch):
    from conftest import nguoi_thu

    _cau_hinh_du(monkeypatch)
    tra = _client(nguoi_thu("kenh.doc")).get("/api/connect/zalo-oa/start")
    assert tra.status_code == 403


def test_start_tra_ve_url_cho_nguoi_du_quyen(monkeypatch):
    from conftest import nguoi_thu

    _cau_hinh_du(monkeypatch)
    tra = _client(nguoi_thu("kenh.noi")).get("/api/connect/zalo-oa/start")
    assert tra.status_code == 200
    url = tra.json()["url"]
    assert url.startswith(oz.URL_CAP_QUYEN)
    assert "sec" not in url


def test_start_noi_ro_thieu_cau_hinh_gi(monkeypatch):
    """
    503 kèm TÊN biến còn thiếu. "Chưa cấu hình" trống không là bắt người
    vận hành đi đoán giữa bốn biến ZALO_OA_*.
    """
    from conftest import nguoi_thu

    _cau_hinh_du(monkeypatch)
    monkeypatch.setattr(oz.settings, "zalo_oa_app_id", "")
    tra = _client(nguoi_thu("kenh.noi")).get("/api/connect/zalo-oa/start")
    assert tra.status_code == 503
    assert "ZALO_OA_APP_ID" in tra.json()["detail"]


def test_callback_tu_choi_state_bia():
    """Không có state hợp lệ thì callback không làm gì — đó là cả cái chốt."""
    tra = _client({}).get(
        "/api/connect/zalo-oa/callback", params={"code": "c", "state": "bia"})
    assert tra.status_code == 400


def _gia_lap_zalo(monkeypatch, *, moi: bool, ma_tk):
    """Thay ba chỗ ra mạng và chạm CSDL bằng bản giả."""
    async def _token(code, verifier):
        return {"access_token": "at", "refresh_token": "rt-bi-mat"}

    async def _hs(token):
        return {"oa_id": "1234", "name": "Shop Mỹ Phẩm"}

    async def _luu(**kw):
        return ma_tk, moi

    async def _log(*a, **k):
        return None

    monkeypatch.setattr(oz, "_doi_token", _token)
    monkeypatch.setattr(oz, "_ho_so_oa", _hs)
    monkeypatch.setattr(oz, "_luu_tai_khoan", _luu)
    monkeypatch.setattr(oz.db, "log_event", _log)


def test_callback_hien_dia_chi_webhook_day_du(monkeypatch):
    """
    Zalo KHÔNG có API đăng ký webhook. Địa chỉ này là bước làm tay duy nhất
    còn lại, và thiếu nó thì OA gửi đi được mà tin khách không vào — không
    lỗi, không nhật ký. Nên nó phải hiện ra, đầy đủ, đúng account_id.
    """
    from uuid import uuid4

    ma_tk = uuid4()
    _cau_hinh_du(monkeypatch)
    _gia_lap_zalo(monkeypatch, moi=True, ma_tk=ma_tk)

    state, _ = oz._KHO.tao("00000000-0000-0000-0000-000000000001")
    tra = _client({}).get(
        "/api/connect/zalo-oa/callback", params={"code": "c", "state": state})

    assert tra.status_code == 200
    assert f"https://x.vn/webhook/native/zalo-oa/{ma_tk}" in tra.text
    assert "Shop Mỹ Phẩm" in tra.text
    assert "rt-bi-mat" not in tra.text


def test_callback_bao_ro_khi_la_noi_lai(monkeypatch):
    """
    Nối lại một OA đã có không được hiện "Đã nối" như lần đầu: người vận
    hành cần biết mình vừa THAY KHOÁ chứ không tạo thêm tài khoản, vì
    webhook cũ vẫn dùng được và họ không phải dán lại.
    """
    from uuid import uuid4

    _cau_hinh_du(monkeypatch)
    _gia_lap_zalo(monkeypatch, moi=False, ma_tk=uuid4())

    state, _ = oz._KHO.tao("00000000-0000-0000-0000-000000000001")
    tra = _client({}).get(
        "/api/connect/zalo-oa/callback", params={"code": "c", "state": state})
    assert "cấp lại khoá" in tra.text


# ---------------- dashboard ----------------

def test_dashboard_co_nut_va_nut_goi_dung_duong():
    from pathlib import Path

    goc = Path(oz.__file__).resolve().parents[2] / "dashboard"
    html = (goc / "index.html").read_text(encoding="utf-8")
    js = (goc / "app.js").read_text(encoding="utf-8")
    assert 'id="btn-oauth-zalo-oa"' in html
    assert "#btn-oauth-zalo-oa" in js
    assert '"/connect/zalo-oa/start"' in js


def test_cua_so_oauth_zalo_khong_tu_dong_dong():
    """
    Cửa sổ con còn hiện địa chỉ webhook người dùng phải copy sang Zalo
    Developers. Tự đóng là lấy mất thứ duy nhất làm chiều NHẬN tin chạy
    được — và cái mất ấy im lặng: OA vẫn gửi đi được bình thường.
    """
    from pathlib import Path

    ma = Path(oz.__file__).read_text(encoding="utf-8")
    assert "window.close()},22" not in ma      # không hẹn giờ đóng
    assert "onclick='window.close()'" in ma    # người tự đóng khi xong
