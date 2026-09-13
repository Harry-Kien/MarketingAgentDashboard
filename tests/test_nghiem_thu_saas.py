"""
NGHIỆM THU TỪNG CHỨC NĂNG, TỪNG BƯỚC, TRÊN APP THẬT.

Mỗi test dưới đây là MỘT chức năng người dùng thấy, đi qua đúng các bước
người dùng đi — đăng nhập bằng mật khẩu thật, gọi đúng endpoint dashboard
gọi, trên `agent.main.app` đầy đủ (middleware + lifespan) và Postgres thật.

Không có kho giả, không có router trần, không gọi model (mọi kịch bản đi
đường agent tắt hoặc không chạm agent).

Docstring của từng test liệt kê các BƯỚC. `scripts/sinh_nghiem_thu.py` đọc
chúng cùng kết quả chạy để sinh `docs/nghiem-thu.md` — bảng nghiệm thu
người vận hành đọc được.

MỘT CLIENT, NHIỀU NGƯỜI
-----------------------
Mọi người dùng trong một kịch bản đi qua CÙNG MỘT `TestClient`, chỉ đổi
cookie. Dựng `TestClient` thứ hai (không `with`) là mỗi request chạy trên
một event loop mới, còn pool asyncpg thì gắn với loop của lifespan — request
treo vô hạn, không lỗi, không log. Bản đầu của file này treo đúng như vậy.
"""
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

# Dùng lại fixture app đầy đủ. pytest thấy fixture qua tên trong namespace.
from conftest import GOC_WEB, _quan_tri  # noqa: E402

MK = "mat-khau-nghiem-thu-1"


# ------------------------------------------------------------------ helpers

class Nguoi:
    """Một người dùng = một token phiên trên client chung."""

    def __init__(self, khach, token: str | None):
        self.khach, self.token = khach, token

    def _co(self):
        from agent.api.routes import TEN_COOKIE

        if self.token:
            self.khach.cookies.set(TEN_COOKIE, self.token)
        else:
            self.khach.cookies.clear()

    def get(self, *a, **k):
        self._co(); return self.khach.get(*a, **k)

    def post(self, *a, **k):
        self._co(); return self.khach.post(*a, **k)

    def put(self, *a, **k):
        self._co(); return self.khach.put(*a, **k)

    def delete(self, *a, **k):
        self._co(); return self.khach.delete(*a, **k)


def _sql(khach, coro_fn, *args):
    return khach.portal.call(coro_fn, *args)


def _quan_tri_vao(khach, ten="sep") -> Nguoi:
    _, token = _sql(khach, _quan_tri, ten)
    return Nguoi(khach, token)


def _dang_nhap(khach, ten: str, mk: str) -> tuple[int, Nguoi | None]:
    """ĐĂNG NHẬP THẬT qua /api/dang-nhap. Trả (mã HTTP, người nếu thành công)."""
    from agent.api.routes import TEN_COOKIE

    khach.cookies.clear()
    r = khach.post("/api/dang-nhap", json={"ten_dang_nhap": ten, "mat_khau": mk})
    if r.status_code != 200:
        return r.status_code, None
    return 200, Nguoi(khach, khach.cookies.get(TEN_COOKIE))


def _nhan_vien_moi(qt: Nguoi, ten: str, vai_tro: str | None = "Nhân viên") -> tuple[str, Nguoi]:
    """Quản trị tạo nhân viên + gán vai trò qua API; nhân viên đăng nhập thật."""
    r = qt.post("/api/nguoi-dung", json={
        "ten_dang_nhap": ten, "mat_khau": MK, "ho_ten": ten.title()})
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    if vai_tro:
        vt = next(v for v in qt.get("/api/vai-tro").json()["vai_tro"]
                  if v["ten"] == vai_tro)
        assert qt.put(f"/api/nguoi-dung/{uid}/vai-tro",
                      json={"vai_tro": [vt["id"]]}).status_code == 200
    ma, nv = _dang_nhap(qt.khach, ten, MK)
    assert ma == 200
    return uid, nv


def _kenh_webchat(qt: Nguoi, ten="Web shop", agent_bat=False) -> str:
    r = qt.post("/api/channel-accounts", json={
        "channel": "webchat", "display_name": ten,
        "capabilities": {"send_text": True, "receive_message": True},
        "credentials": {"widget_secret": secrets.token_urlsafe(24),
                        "allowed_origins": [GOC_WEB]},
    })
    assert r.status_code == 201, r.text
    tk = r.json()["id"]
    assert qt.post(f"/api/channel-accounts/{tk}/enable").status_code == 200
    if not agent_bat:
        assert qt.post(f"/api/channel-accounts/{tk}/agent",
                       json={"bat": False, "ly_do": "nghiệm thu"}).status_code == 200
    return tk


def _khach_nhan(khach, tk: str, ten: str, text: str) -> None:
    """Khách web — không cookie, không phiên dashboard."""
    khach.cookies.clear()
    ve = khach.post(f"/webchat/{tk}/session", json={},
                    headers={"Origin": GOC_WEB}).json()["token"]
    r = khach.post(f"/webchat/{tk}/messages",
                   json={"client_message_id": str(uuid4()), "text": text,
                         "visitor_name": ten},
                   headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ve}"})
    assert r.status_code == 202, r.text


def _them_thanh_vien(khach, tk: str, uid: str, role="agent"):
    from agent import db

    async def them(tk_, uid_, role_):
        await db.execute(
            "INSERT INTO account_memberships (account_id, user_id, role) "
            "VALUES ($1::uuid, $2::uuid, $3) ON CONFLICT DO NOTHING", tk_, uid_, role_)
    _sql(khach, them, tk, uid, role)


# ------------------------------------------------------------------ 1. đăng nhập

def test_01_dang_nhap_that_bang_mat_khau(app_that):
    """
    Đăng nhập và phiên.

    BƯỚC 1  Quản trị tạo nhân viên "lan" với mật khẩu ở màn Nhân sự.
    BƯỚC 2  "lan" đăng nhập bằng đúng mật khẩu -> nhận cookie phiên.
    BƯỚC 3  GET /api/toi trả về đúng tên và tập quyền của vai trò Nhân viên.
    BƯỚC 4  Sai mật khẩu -> 401, không có phiên.
    BƯỚC 5  Đăng xuất -> /api/toi trả 401.
    """
    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")

    toi = lan.get("/api/toi")
    assert toi.status_code == 200
    assert toi.json()["ten_dang_nhap"] == "lan"
    assert "hoi_thoai.doc" in toi.json()["quyen"]
    assert "nguoi_dung.sua" not in toi.json()["quyen"]

    ma, _ = _dang_nhap(app_that, "lan", "sai-roi-nhe")
    assert ma == 401

    assert lan.post("/api/dang-xuat").status_code == 200
    assert lan.get("/api/toi").status_code == 401


# ------------------------------------------------------------------ 2. phân quyền

def test_02_phan_quyen_hong_dong_theo_vai_tro(app_that):
    """
    Phân quyền: không được cấp thì không thấy.

    BƯỚC 1  Nhân viên vai trò "Nhân viên" đọc được hội thoại (200).
    BƯỚC 2  Cùng người đó tạo nhân viên mới -> 403 (thiếu nguoi_dung.sua).
    BƯỚC 3  Quản trị tạo vai trò "Chỉ xem khách" chỉ có khach.doc.
    BƯỚC 4  Gán cho nhân viên thứ hai: đọc khách 200, tạo công việc 403.
    BƯỚC 5  Nhân viên không có vai trò nào: đăng nhập được, mọi màn 403.
    """
    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")
    assert lan.get("/api/conversations").status_code == 200
    assert lan.post("/api/nguoi-dung", json={"ten_dang_nhap": "xxx",
                    "mat_khau": MK}).status_code == 403

    r = qt.post("/api/vai-tro", json={
        "ten": "Chỉ xem khách", "mo_ta": "nghiệm thu", "quyen": ["khach.doc"]})
    assert r.status_code == 201, r.text
    _, minh = _nhan_vien_moi(qt, "minh", vai_tro="Chỉ xem khách")
    assert minh.get("/api/contacts").status_code == 200
    assert minh.post("/api/cong-viec", json={"tieu_de": "thử việc"}).status_code == 403

    _, trong = _nhan_vien_moi(qt, "trong", vai_tro=None)
    assert trong.get("/api/toi").status_code == 200
    assert trong.get("/api/conversations").status_code == 403


# ------------------------------------------------------------------ 3. khoá

def test_03_khoa_nhan_vien_da_moi_phien(app_that):
    """
    Nhân viên nghỉ việc.

    BƯỚC 1  "lan" đang đăng nhập, /api/toi 200.
    BƯỚC 2  Quản trị bấm Khoá.
    BƯỚC 3  Ngay lập tức phiên cũ của "lan" -> 401; đăng nhập lại -> 401.
    BƯỚC 4  Danh sách nhân sự hiện khoa=true; tổng vẫn đếm người này.
    BƯỚC 5  Mở khoá -> đăng nhập lại được.
    """
    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")
    assert lan.get("/api/toi").status_code == 200

    assert qt.post("/api/nguoi-dung/lan/khoa?khoa=true").status_code == 200
    assert lan.get("/api/toi").status_code == 401
    assert _dang_nhap(app_that, "lan", MK)[0] == 401

    ds = qt.get("/api/nguoi-dung").json()["nguoi_dung"]
    assert next(n for n in ds if n["ten_dang_nhap"] == "lan")["khoa"] is True
    assert len(ds) == 2

    assert qt.post("/api/nguoi-dung/lan/khoa?khoa=false").status_code == 200
    assert _dang_nhap(app_that, "lan", MK)[0] == 200


# ------------------------------------------------------------------ 4. kênh + agent tuỳ chọn

def test_04_noi_kenh_va_tat_agent_theo_kenh(app_that):
    """
    Kênh thêm bằng cấu hình; agent là tuỳ chọn.

    BƯỚC 1  Quản trị tạo kênh webchat, credential vào vault, bật kênh.
    BƯỚC 2  Kênh hiện trong danh sách.
    BƯỚC 3  Tắt agent cho kênh, có lý do -> agent_bat=false.
    BƯỚC 4  Khách nhắn -> hội thoại chuyển người, sinh việc, KHÔNG gọi model.
    BƯỚC 5  Bật lại agent -> agent_bat=true.
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    assert any(a["id"] == tk for a in qt.get("/api/channel-accounts").json())

    r = qt.post(f"/api/channel-accounts/{tk}/agent",
                json={"bat": False, "ly_do": "Kênh mới, người trực trước"})
    assert r.json()["agent_bat"] is False

    _khach_nhan(app_that, tk, "Khách A", "Cho em hỏi giá kem dưỡng")

    async def doc():
        c = await db.fetchrow("SELECT status, mode FROM conversations LIMIT 1")
        v = await db.fetchrow("SELECT count(*) AS n FROM cong_viec")
        m = await db.fetchrow("SELECT count(*) AS n FROM messages WHERE cost_usd > 0")
        return c, v["n"], m["n"]
    c, so_viec, goi_model = _sql(app_that, doc)
    assert c["status"] == "escalated" and c["mode"] == "human"
    assert so_viec == 1 and goi_model == 0

    assert qt.post(f"/api/channel-accounts/{tk}/agent",
                   json={"bat": True}).json()["agent_bat"] is True


# ------------------------------------------------------------------ 5. giao khách + tầm nhìn

def test_05_giao_khach_va_tam_nhin(app_that):
    """
    Khách hàng và người chịu trách nhiệm.

    BƯỚC 1  Khách nhắn qua webchat -> có hồ sơ khách, chưa có chủ.
    BƯỚC 2  Ô "Khách chưa có chủ" đếm 1.
    BƯỚC 3  Quản trị giao khách cho "lan" (có lý do) -> hết vô chủ; lịch sử 1 dòng.
    BƯỚC 4  Mức tầm nhìn "an": "minh" (cùng kênh) KHÔNG thấy khách của lan; lan thấy.
    BƯỚC 5  Mức "tat": minh thấy lại. Thu hồi -> khách về của chung.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _them_thanh_vien(app_that, tk, lan_id)
    _them_thanh_vien(app_that, tk, minh_id)

    _khach_nhan(app_that, tk, "Chị Hoa", "Shop còn hàng không?")
    vo_chu = qt.get("/api/khach-vo-chu").json()
    assert vo_chu["so"] == 1
    cid = vo_chu["khach"][0]["id"]

    r = qt.put(f"/api/contacts/{cid}/chu-so-huu",
               json={"owner_user_id": lan_id, "ly_do": "Phân công ca sáng"})
    assert r.status_code == 200, r.text
    assert qt.get("/api/khach-vo-chu").json()["so"] == 0
    assert len(qt.get(f"/api/contacts/{cid}/chu-so-huu/lich-su").json()["lich_su"]) == 1

    assert qt.put("/api/tam-nhin-khach", json={"muc": "an"}).status_code == 200
    assert cid not in {c["id"] for c in minh.get("/api/contacts").json()}
    assert cid in {c["id"] for c in lan.get("/api/contacts").json()}

    assert qt.put("/api/tam-nhin-khach", json={"muc": "tat"}).status_code == 200
    assert cid in {c["id"] for c in minh.get("/api/contacts").json()}

    assert qt.delete(f"/api/contacts/{cid}/chu-so-huu?ly_do=Het%20ca").status_code == 200
    assert qt.get("/api/khach-vo-chu").json()["so"] == 1


# ------------------------------------------------------------------ 6. trường tuỳ biến

def test_06_truong_thong_tin_khach_them_tren_dashboard(app_that):
    """
    Trường thông tin khách thêm từ dashboard, kiểm kiểu ở máy chủ.

    BƯỚC 1  Quản trị thêm trường "tuoi" kiểu số và "loai_da" kiểu chọn.
    BƯỚC 2  Ghi tuoi=30, loai_da="dau" cho một khách -> 200, đọc lại đúng.
    BƯỚC 3  tuoi="ba mươi" -> 422; loai_da="xanh" (ngoài lựa chọn) -> 422.
    BƯỚC 4  Khoá lạ "chieu_cao" -> 422, không bị nuốt im.
    BƯỚC 5  Xoá trường -> máy chủ nói rõ bao nhiêu hồ sơ mất giá trị.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "xin chào")
    cid = qt.get("/api/contacts").json()[0]["id"]

    assert qt.post("/api/truong-khach", json={
        "ma": "tuoi", "nhan": "Tuổi", "kieu": "so"}).status_code == 201
    assert qt.post("/api/truong-khach", json={
        "ma": "loai_da", "nhan": "Loại da", "kieu": "chon",
        "lua_chon": ["dau", "kho", "hon_hop"]}).status_code == 201

    r = qt.put(f"/api/contacts/{cid}/truong",
               json={"gia_tri": {"tuoi": 30, "loai_da": "dau"}})
    assert r.status_code == 200, r.text
    ho_so = qt.get(f"/api/contacts/{cid}").json()["profile"]
    assert ho_so["tuoi"] == 30 and ho_so["loai_da"] == "dau"

    assert qt.put(f"/api/contacts/{cid}/truong",
                  json={"gia_tri": {"tuoi": "ba mươi"}}).status_code == 422
    assert qt.put(f"/api/contacts/{cid}/truong",
                  json={"gia_tri": {"loai_da": "xanh"}}).status_code == 422
    assert qt.put(f"/api/contacts/{cid}/truong",
                  json={"gia_tri": {"chieu_cao": 170}}).status_code == 422

    r = qt.delete("/api/truong-khach/tuoi?xoa_ca_gia_tri=true")
    assert r.status_code == 200, r.text
    assert r.json()["so_ho_so_da_xoa_gia_tri"] == 1


# ------------------------------------------------------------------ 7. công việc

def test_07_cong_viec_tu_sinh_nhan_va_hoan_thanh(app_that):
    """
    Phân task và quản lý task.

    BƯỚC 1  Agent tắt -> khách nhắn -> việc tự sinh (nguồn agent, chưa ai nhận).
    BƯỚC 2  Ca trực đếm 1 việc chưa giao.
    BƯỚC 3  "lan" (không có cong_viec.giao) tự nhận việc -> 200.
    BƯỚC 4  "lan" đẩy việc sang "minh" -> 403 (giao cần quyền).
    BƯỚC 5  Quản trị giao cho minh, đặt hạn, đánh dấu xong -> xong_luc có, qua_han=false.
    BƯỚC 6  Quản trị tạo việc tay với hạn đã qua -> qua_han=true.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, _ = _nhan_vien_moi(qt, "minh")
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")

    ds = qt.get("/api/cong-viec").json()["cong_viec"]
    assert len(ds) == 1 and ds[0]["nguon"] == "agent" and ds[0]["nguoi_nhan"] is None
    vid = ds[0]["id"]
    assert qt.get("/api/overview").json()["cong_viec"]["chua_giao"] == 1

    assert lan.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": lan_id}).status_code == 200
    assert lan.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": minh_id}).status_code == 403

    r = qt.put(f"/api/cong-viec/{vid}", json={
        "nguoi_nhan": minh_id, "han": "2099-01-01T00:00:00+00:00", "trang_thai": "xong"})
    assert r.status_code == 200, r.text
    v = next(x for x in qt.get("/api/cong-viec").json()["cong_viec"] if x["id"] == vid)
    assert v["trang_thai"] == "xong" and v["xong_luc"] and v["qua_han"] is False

    r = qt.post("/api/cong-viec", json={
        "tieu_de": "Gọi lại chị Hoa", "nguoi_nhan": lan_id,
        "han": "2020-01-01T00:00:00+00:00"})
    assert r.status_code == 201, r.text
    moi = next(x for x in qt.get("/api/cong-viec").json()["cong_viec"]
               if x["id"] == r.json()["id"])
    assert moi["qua_han"] is True


# ------------------------------------------------------------------ 8. outbox

def test_08_tin_khong_gui_duoc_xem_va_xu_ly(app_that):
    """
    Tin KHÔNG gửi được.

    BƯỚC 1  Một job outbox chết (8/8 lần) thuộc hội thoại đã chuyển người.
    BƯỚC 2  Ô Ca trực "Tin KHÔNG gửi được" đếm 1; danh sách hiện lỗi cuối.
    BƯỚC 3  Gửi lại bị TỪ CHỐI (409): người đã tiếp quản, gửi lại là khách nhận hai lần.
    BƯỚC 4  Bỏ qua -> trạng thái cancelled, ô đếm về 0.
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")

    async def gieo(tk_):
        c = await db.fetchrow("SELECT id FROM conversations LIMIT 1")
        r = await db.fetchrow(
            "INSERT INTO outbox_jobs (account_id, conversation_id, kind, "
            " idempotency_key, status, attempts, max_attempts, last_error) "
            "VALUES ($1::uuid, $2, 'text', $3, 'dead', 8, 8, "
            " 'ConnectError: sidecar không phản hồi') RETURNING id", tk_, c["id"], str(uuid4()))
        return str(r["id"])
    jid = _sql(app_that, gieo, tk)

    assert qt.get("/api/overview").json()["tin_chet"]["so"] == 1
    ds = qt.get("/api/outbox/jobs?status=dead").json()["items"]
    assert len(ds) == 1 and "sidecar" in ds[0]["last_error"]

    assert qt.post(f"/api/outbox/jobs/{jid}/retry").status_code == 409

    assert qt.post(f"/api/outbox/jobs/{jid}/cancel").status_code == 200
    assert qt.get("/api/overview").json()["tin_chet"]["so"] == 0


# ------------------------------------------------------------------ 9. hồ sơ agent + định tuyến

def test_09_ho_so_agent_va_dinh_tuyen_cau_hinh_duoc(app_that):
    """
    Nhiều agent theo cấu hình; định tuyến theo cấu hình.

    BƯỚC 1  Tạo hồ sơ agent "Tư vấn nhẹ" với ngưỡng LỎNG hơn toàn cục.
    BƯỚC 2  API trả cả giá trị đã lưu lẫn giá trị có hiệu lực (đã siết).
    BƯỚC 3  Gán hồ sơ cho kênh -> kênh hiện agent_ho_so_id.
    BƯỚC 4  Tạo đội, thêm thành viên, tạo luật, đặt SLA qua API.
    BƯỚC 5  GET /api/routing phản ánh 1 đội, 1 luật, 1 SLA.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, _ = _nhan_vien_moi(qt, "lan")

    r = qt.post("/api/ho-so-agent", json={
        "ten": "Tư vấn nhẹ", "huong_dan": "Ưu tiên hỏi lại.",
        "nguong_tu_tin": 0.05, "tran_chi_phi": 99})
    assert r.status_code == 201, r.text
    hs = r.json()
    assert hs["nguong_hieu_luc"] >= hs["nguong_tu_tin"]   # 0.05 bị siết lên
    assert hs["tran_hieu_luc"] <= hs["tran_chi_phi"]       # 99 bị siết xuống

    assert qt.put(f"/api/channel-accounts/{tk}/ho-so-agent",
                  json={"ho_so_id": hs["id"]}).status_code == 200
    assert qt.get(f"/api/channel-accounts/{tk}").json().get("agent_ho_so_id") == hs["id"]

    doi = qt.post("/api/routing/teams", json={"name": "Ca sáng"}).json()
    assert qt.put(f"/api/routing/teams/{doi['id']}/members/{lan_id}",
                  json={"role": "agent", "skills": [], "max_active": 5,
                        "is_available": True}).status_code == 200
    assert qt.post("/api/routing/rules", json={
        "account_id": tk, "team_id": doi["id"], "priority": None,
        "required_skills": [], "weight": 100, "active": True}).status_code == 201
    assert qt.put("/api/routing/sla-policies", json={
        "account_id": tk, "priority": "normal", "first_response_minutes": 15,
        "resolution_minutes": 1440, "business_hours": {}, "active": True}).status_code == 200

    cfg = qt.get("/api/routing").json()
    assert len(cfg["teams"]) == 1 and len(cfg["rules"]) == 1 and len(cfg["sla_policies"]) == 1


# ------------------------------------------------------------------ 10. gộp khách

def test_10_gop_hai_khach_lam_mot(app_that):
    """
    Gộp khách trùng.

    BƯỚC 1  Hai khách web khác nhau nhắn -> 2 hồ sơ.
    BƯỚC 2  Xem trước gộp: đủ số hội thoại, danh tính, can_manage=true (quản trị).
    BƯỚC 3  Gộp với version đúng -> 200, danh sách còn 1 khách.
    BƯỚC 4  Khách giữ lại có 2 danh tính.
    BƯỚC 5  Hoàn tác -> lại 2 khách.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Lan Zalo", "hi")
    _khach_nhan(app_that, tk, "Chị Lan FB", "hello")
    ds = qt.get("/api/contacts").json()
    assert len(ds) == 2
    a, b = ds[0]["id"], ds[1]["id"]

    p = qt.get(f"/api/contacts/merge/preview?source_id={a}&target_id={b}")
    assert p.status_code == 200, p.text
    p = p.json()
    assert p["can_manage"] is True and p["source"]["point_count"] == 1

    r = qt.post("/api/contacts/merge", json={
        "source_id": a, "target_id": b, "reason": "cùng một người",
        "expected_source_version": p["source"]["version"],
        "expected_target_version": p["target"]["version"]})
    assert r.status_code == 200, r.text
    mid = r.json()["merge_id"]

    con = qt.get("/api/contacts").json()
    assert [c["id"] for c in con] == [b]
    assert con[0]["contact_point_count"] == 2

    assert qt.post(f"/api/contacts/merges/{mid}/undo",
                   json={"reason": "gộp nhầm"}).status_code == 200
    assert len(qt.get("/api/contacts").json()) == 2
