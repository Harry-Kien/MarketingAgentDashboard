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


# ------------------------------------------------------------------ 11. đếm trước khi xoá (bốn mắt)

def test_11_dem_truoc_khi_xoa_can_nguoi_thu_hai_duyet(app_that):
    """
    Đếm dữ liệu sẽ xoá, có người thứ hai duyệt.

    BƯỚC 1  Khách nhắn -> có hồ sơ. Quản trị A tạo yêu cầu đếm (dry-run) kèm lý do.
    BƯỚC 2  Danh sách ở màn Nhật ký hiện yêu cầu, trạng thái chờ duyệt.
    BƯỚC 3  Chính A bấm Duyệt -> 409: người tạo không tự duyệt được.
    BƯỚC 4  Quản trị B duyệt -> đã duyệt. Chạy đếm -> kết quả có số hội thoại, tin nhắn.
    BƯỚC 5  Sức khoẻ kênh đọc được qua API (chưa có lần kiểm nào -> null, không lỗi).
    """
    a = _quan_tri_vao(app_that, "sep_a")
    b = _quan_tri_vao(app_that, "sep_b")
    tk = _kenh_webchat(a)
    _khach_nhan(app_that, tk, "Chị Hoa", "xoá dữ liệu giúp em")
    cid = a.get("/api/contacts").json()[0]["id"]

    r = a.post(f"/api/contacts/{cid}/retention-jobs",
               json={"kind": "delete", "reason": "Khách yêu cầu qua Zalo", "dry_run": True})
    assert r.status_code == 202, r.text
    jid = r.json()["id"]

    ds = a.get("/api/data-retention/jobs").json()["jobs"]
    assert any(j["id"] == jid and j["status"] == "pending_approval" for j in ds)

    assert a.post(f"/api/data-retention/jobs/{jid}/approve").status_code == 409

    assert b.post(f"/api/data-retention/jobs/{jid}/approve").status_code == 200
    r = b.post(f"/api/data-retention/jobs/{jid}/execute-dry-run")
    assert r.status_code == 200, r.text
    kq = r.json()["result"]
    assert kq["conversations"] == 1 and kq["messages"] >= 1

    r = a.get(f"/api/channel-accounts/{tk}/health")
    assert r.status_code == 200 and "latest" in r.json()


# ------------------------------------------------------------------ 12. giao hàng loạt

def test_12_giao_nhieu_khach_mot_luot_va_thu_hoi(app_that):
    """
    Giao khách hàng loạt từ danh sách.

    BƯỚC 1  Ba khách web nhắn -> 3 hồ sơ, ô "Khách chưa có chủ" đếm 3.
    BƯỚC 2  Quản trị tick cả ba, giao cho "lan" một lượt -> 3 khách có chủ, vô chủ = 0.
    BƯỚC 3  Mỗi khách có đúng 1 dòng lịch sử giao, cùng lý do.
    BƯỚC 4  Giao cho người đã KHOÁ -> 422, không khách nào đổi chủ (một giao dịch).
    BƯỚC 5  Thu hồi hàng loạt (không chọn ai) -> cả ba về của chung.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, _ = _nhan_vien_moi(qt, "lan")
    minh_id, _ = _nhan_vien_moi(qt, "minh")
    for ten in ("Chị Hoa", "Anh Nam", "Cô Ba"):
        _khach_nhan(app_that, tk, ten, "xin chào")
    ids = [c["id"] for c in qt.get("/api/contacts").json()]
    assert len(ids) == 3
    assert qt.get("/api/khach-vo-chu").json()["so"] == 3

    r = qt.put("/api/contacts/chu-so-huu/hang-loat", json={
        "contact_ids": ids, "owner_user_id": lan_id, "ly_do": "Chia ca sáng"})
    assert r.status_code == 200, r.text
    assert r.json()["so_khach"] == 3
    assert qt.get("/api/khach-vo-chu").json()["so"] == 0
    for cid in ids:
        ls = qt.get(f"/api/contacts/{cid}/chu-so-huu/lich-su").json()["lich_su"]
        assert len(ls) == 1 and ls[0]["ly_do"] == "Chia ca sáng"

    assert qt.post("/api/nguoi-dung/minh/khoa?khoa=true").status_code == 200
    r = qt.put("/api/contacts/chu-so-huu/hang-loat", json={
        "contact_ids": ids, "owner_user_id": minh_id, "ly_do": "Thử giao cho người khoá"})
    assert r.status_code == 422
    assert all(c["owner_user_id"] == lan_id for c in qt.get("/api/contacts").json())

    r = qt.put("/api/contacts/chu-so-huu/hang-loat", json={
        "contact_ids": ids, "owner_user_id": None, "ly_do": "Hết ca"})
    assert r.status_code == 200 and r.json()["owner_ho_ten"] is None
    assert qt.get("/api/khach-vo-chu").json()["so"] == 3


# ------------------------------------------------------------------ 13. quy tắc tự động

def _hoi_thoai_dau(khach) -> dict:
    from agent import db

    async def doc():
        return dict(await db.fetchrow("SELECT id, status, mode FROM conversations "
                                      "ORDER BY created_at LIMIT 1"))
    return _sql(khach, doc)


def test_13_quy_tac_tu_dong_chan_agent_va_chuyen_nguoi(app_that):
    """
    Quy tắc tự động: khi khách nhắn → nếu … → thì ….

    BƯỚC 1  Quản trị tạo mẫu /doitra; quy tắc gửi mẫu KHÔNG tồn tại bị từ chối lúc lưu (422).
    BƯỚC 2  Tạo quy tắc «có từ đổi trả → gắn nhãn, gửi mẫu /doitra, chuyển người».
    BƯỚC 3  Kênh BẬT agent; khách nhắn "em muốn DOI TRA" (không dấu) → khớp, agent không chạy.
    BƯỚC 4  Hội thoại chuyển người, có nhãn "đổi trả", có MỘT việc, mẫu đã vào hàng gửi.
    BƯỚC 5  Nhật ký lần chạy ghi "đã làm"; khách nhắn tiếp không sinh mẫu thứ hai.
    BƯỚC 6  Nhân viên XEM được quy tắc nhưng không sửa được — thiếu quyền sửa định tuyến (403).
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")
    assert qt.post("/api/tra-loi-nhanh", json={
        "ma_tat": "doitra", "noi_dung": "Dạ shop hỗ trợ đổi trả trong 7 ngày ạ."}).status_code == 201
    quy_tac = {"ten": "Đổi trả", "dieu_kien": {"chua_tu": ["đổi trả"]},
               "hanh_dong": [{"loai": "gan_nhan", "nhan": "đổi trả"},
                             {"loai": "gui_mau", "ma_tat": "khongco"}]}
    assert qt.post("/api/tu-dong", json=quy_tac).status_code == 422
    quy_tac["hanh_dong"] = [{"loai": "gan_nhan", "nhan": "đổi trả"},
                            {"loai": "gui_mau", "ma_tat": "doitra"},
                            {"loai": "chuyen_nguoi", "ly_do": "khách hỏi đổi trả"}]
    assert qt.post("/api/tu-dong", json=quy_tac).status_code == 201

    tk = _kenh_webchat(qt, agent_bat=True)
    _khach_nhan(app_that, tk, "Chị Hoa", "em muốn DOI TRA hàng ạ")
    c = _hoi_thoai_dau(app_that)
    assert (c["status"], c["mode"]) == ("escalated", "human")

    async def dem(cid):
        return {
            "nhan": [r["nhan"] for r in await db.fetch(
                "SELECT nhan FROM hoi_thoai_nhan WHERE conversation_id = $1", cid)],
            "viec": (await db.fetchrow("SELECT count(*) n FROM cong_viec WHERE conversation_id = $1",
                                       cid))["n"],
            "mau": (await db.fetchrow("SELECT count(*) n FROM messages WHERE conversation_id = $1 "
                                      "AND content LIKE 'Dạ shop hỗ trợ đổi trả%'", cid))["n"],
        }
    assert _sql(app_that, dem, c["id"]) == {"nhan": ["đổi trả"], "viec": 1, "mau": 1}

    lc = qt.get("/api/tu-dong/lan-chay").json()["lan_chay"]
    assert lc and lc[0]["ket_qua"] == "da_lam" and "chuyển người" in lc[0]["chi_tiet"]["lam"]
    _khach_nhan(app_that, tk, "Chị Hoa", "đổi trả giúp em với")
    assert _sql(app_that, dem, c["id"])["mau"] == 1

    assert lan.get("/api/tu-dong").status_code == 200
    assert lan.post("/api/tu-dong", json=quy_tac).status_code == 403


# ------------------------------------------------------------------ 14. lịch ca

def test_14_lich_ca_va_lich_nghi(app_that):
    """
    Lịch ca trực: bộ định tuyến chỉ giao cho người đang trong ca.

    BƯỚC 1  Nhân viên mới chưa xếp ca → "luôn trực".
    BƯỚC 2  Quản trị xếp ca ở một khung giờ KHÔNG phủ lúc này → nhân viên ngoài ca.
    BƯỚC 3  Nhân viên tự xem "ca của tôi" → thấy mình ngoài ca và lịch tuần.
    BƯỚC 4  Ca chồng nhau (ca đêm Chủ nhật vắt sang sáng thứ Hai) bị từ chối (422).
    BƯỚC 5  Đội có luật định tuyến mà không ai trong ca → cảnh báo hiện ra.
    BƯỚC 6  Xoá hết ca → về "luôn trực"; thêm lịch nghỉ phủ lúc này → ngoài ca.
    """
    from datetime import datetime, timedelta, timezone

    qt = _quan_tri_vao(app_that)
    lan_id, lan = _nhan_vien_moi(qt, "lan")

    def toi():
        return next(n for n in qt.get("/api/lich-ca").json()["nguoi"] if n["id"] == lan_id)
    assert toi()["trong_ca"] is True and toi()["ca"] == []

    vn = datetime.now(timezone(timedelta(hours=7)))
    ngay_khac = (vn.isoweekday() + 2) % 7 + 1
    assert qt.put(f"/api/lich-ca/{lan_id}", json={"ca": [
        {"thu": ngay_khac, "bat_dau": "08:00", "ket_thuc": "09:00"}]}).status_code == 200
    assert toi()["trong_ca"] is False
    cua_toi = lan.get("/api/lich-ca/cua-toi").json()
    assert cua_toi["trong_ca"] is False and len(cua_toi["ca"]) == 1

    assert qt.put(f"/api/lich-ca/{lan_id}", json={"ca": [
        {"thu": 7, "bat_dau": "22:00", "ket_thuc": "06:00"},
        {"thu": 1, "bat_dau": "05:00", "ket_thuc": "09:00"}]}).status_code == 422

    r = qt.post("/api/routing/teams", json={"name": "Ca sáng"})
    assert r.status_code == 201, r.text
    doi = r.json()["id"]
    assert qt.put(f"/api/routing/teams/{doi}/members/{lan_id}", json={}).status_code == 200
    assert qt.post("/api/routing/rules", json={"team_id": doi}).status_code == 201
    assert any(c["doi"] == "Ca sáng" for c in qt.get("/api/lich-ca").json()["canh_bao"])

    assert qt.put(f"/api/lich-ca/{lan_id}", json={"ca": []}).json()["trong_ca"] is True
    r = qt.post("/api/lich-ca/nghi", json={
        "nguoi_dung_id": lan_id, "tu_luc": (vn - timedelta(hours=1)).isoformat(),
        "den_luc": (vn + timedelta(days=1)).isoformat(), "ly_do": "ốm"})
    assert r.status_code == 201, r.text
    assert toi()["trong_ca"] is False and toi()["dang_nghi"] is True


# ------------------------------------------------------------------ 15. sổ yêu cầu của khách

def test_15_so_yeu_cau_cua_khach_dem_han_luat_dinh(app_that):
    """
    Sổ yêu cầu của khách (Luật BVDLCN 91/2025, NĐ 356/2025 Điều 5).

    BƯỚC 1  Quản trị ghi yêu cầu xoá khách gửi hôm nay → "trong hạn".
    BƯỚC 2  Ghi yêu cầu xem dữ liệu khách gửi 25 ngày trước → vào sổ đã "QUÁ HẠN".
    BƯỚC 3  Sổ đếm 1 quá hạn; yêu cầu quá hạn KHÔNG gia hạn được (422).
    BƯỚC 4  Phản hồi ban đầu, gia hạn một lần; lần gia hạn thứ hai bị từ chối.
    BƯỚC 5  Từ chối phải nêu căn cứ; đóng xong yêu cầu biến khỏi danh sách đang mở.
    BƯỚC 6  Sổ không lưu số điện thoại thật; người không có quyền PII không xem được (403).
    """
    from datetime import datetime, timedelta, timezone

    from agent import db

    qt = _quan_tri_vao(app_that)
    _, la = _nhan_vien_moi(qt, "khach_moi", vai_tro=None)
    xoa = qt.post("/api/pdpd/yeu-cau", json={"loai": "xoa", "sdt": "0967 627 336"}).json()
    assert xoa["tinh_trang"] == "dung_han"
    cu = (datetime.now(timezone(timedelta(hours=7))) - timedelta(days=25)).isoformat()
    xem = qt.post("/api/pdpd/yeu-cau", json={"loai": "xem", "nhan_luc": cu}).json()
    assert xem["tinh_trang"] == "qua_han"
    assert qt.get("/api/pdpd/yeu-cau").json()["dem"]["qua_han"] == 1
    assert qt.post(f"/api/pdpd/yeu-cau/{xem['id']}/gia-han",
                   json={"so_ngay": 5, "ly_do": "chờ ERP"}).status_code == 422

    assert qt.post(f"/api/pdpd/yeu-cau/{xoa['id']}/phan-hoi").status_code == 200
    assert qt.post(f"/api/pdpd/yeu-cau/{xoa['id']}/gia-han",
                   json={"so_ngay": 10, "ly_do": "chờ ERP mở lại"}).status_code == 200
    assert qt.post(f"/api/pdpd/yeu-cau/{xoa['id']}/gia-han",
                   json={"so_ngay": 1, "ly_do": "lần hai"}).status_code == 422

    assert qt.post(f"/api/pdpd/yeu-cau/{xem['id']}/dong",
                   json={"tu_choi": True, "ket_qua": ""}).status_code == 422
    assert qt.post(f"/api/pdpd/yeu-cau/{xem['id']}/dong",
                   json={"ket_qua": "đã gửi bản sao dữ liệu cho khách"}).status_code == 200
    assert [y["id"] for y in qt.get("/api/pdpd/yeu-cau").json()["yeu_cau"]] == [xoa["id"]]

    async def tat_ca():
        return [dict(r) for r in await db.fetch("SELECT * FROM yeu_cau_chu_the")]
    assert not any("967627336" in str(v) for r in _sql(app_that, tat_ca) for v in r.values())
    assert la.get("/api/pdpd/yeu-cau").status_code == 403


# ------------------------------------------------------------------ 16. gặp nhân viên

def test_16_khach_doi_gap_nhan_vien_thi_chuyen_nguoi_that(app_that):
    """
    "Gặp nhân viên" — lời hứa trong câu thông báo AI được giữ bằng mã.

    BƯỚC 1  Kênh BẬT agent; khách nhắn "cho em gặp nhân viên!" → chuyển người NGAY, agent không chạy.
    BƯỚC 2  Hội thoại ở chế độ người, có MỘT việc "Khách đòi gặp nhân viên".
    BƯỚC 3  Khách KHÔNG nhận câu "em là trợ lý AI" — người đang tiếp, không phải máy.
    BƯỚC 4  Công tắc thông báo AI có trên Cấu hình (nhóm Bảo vệ dữ liệu cá nhân).
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt, agent_bat=True)
    _khach_nhan(app_that, tk, "Anh Nam", "cho em gặp nhân viên!")
    c = _hoi_thoai_dau(app_that)
    assert (c["status"], c["mode"]) == ("escalated", "human")

    async def doc(cid):
        viec = [r["mo_ta"] for r in await db.fetch(
            "SELECT mo_ta FROM cong_viec WHERE conversation_id = $1", cid)]
        tin = [r["content"] for r in await db.fetch(
            "SELECT content FROM messages WHERE conversation_id = $1 AND role = 'system'", cid)]
        return viec, tin
    viec, tin = _sql(app_that, doc, c["id"])
    assert viec == ["Khách đòi gặp nhân viên."]
    assert not any("trợ lý AI" in t for t in tin)

    muc = {m["khoa"]: m for m in qt.get("/api/cai-dat-api").json()["muc"]}
    assert muc["THONG_BAO_AI"]["nhom"] == "bvdlcn"


# ------------------------------------------------------------------ 17. webhook GHTK

def test_17_webhook_ghtk_dang_form_cap_nhat_don(app_that, monkeypatch):
    """
    Hãng vận chuyển GHTK báo trạng thái về (webhook DẠNG FORM).

    BƯỚC 1  Đơn đã có mã vận đơn GHTK; gọi webhook sai bí mật → 401, đơn không đổi.
    BƯỚC 2  GHTK báo "shipper báo đã giao" (45) — chỉ để tham khảo → đơn KHÔNG đổi.
    BƯỚC 3  GHTK báo "đã giao" (5) dạng form → đơn chuyển "đã giao".
    BƯỚC 4  Thân rác (không JSON, không form) → 400.
    """
    from agent import db
    from agent.config import settings

    monkeypatch.setattr(settings, "shipping_webhook_secret", "bi-mat-nghiem-thu")

    async def gieo():
        await db.execute(
            "INSERT INTO orders (ma_don, khach_ten, khach_sdt, khach_dia_chi, trang_thai, "
            "ma_van_don, don_vi_van_chuyen) VALUES ('NT1','Chị Lan','0912345678',"
            "'12 Lê Lợi, Phường Bến Thành, TP HCM','da_chot','S1.A1.99','ghtk')")

    async def don():
        return dict(await db.fetchrow("SELECT trang_thai, trang_thai_giao_hang FROM orders "
                                      "WHERE ma_don = 'NT1'"))
    _sql(app_that, gieo)
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    app_that.cookies.clear()
    r = app_that.post("/webhook/shipping/ghtk?token=sai", content="label_id=S1.A1.99&status_id=5",
                      headers=form)
    assert r.status_code == 401 and _sql(app_that, don)["trang_thai"] == "da_chot"

    r = app_that.post("/webhook/shipping/ghtk?token=bi-mat-nghiem-thu",
                      content="label_id=S1.A1.99&partner_id=NT1&status_id=45", headers=form)
    assert r.status_code == 200 and r.json().get("chi_thong_tin") is True
    assert _sql(app_that, don)["trang_thai"] == "da_chot"

    r = app_that.post("/webhook/shipping/ghtk?token=bi-mat-nghiem-thu",
                      content="label_id=S1.A1.99&partner_id=NT1&status_id=5", headers=form)
    assert r.status_code == 200, r.text
    d = _sql(app_that, don)
    assert (d["trang_thai"], d["trang_thai_giao_hang"]) == ("da_giao", "delivered")

    assert app_that.post("/webhook/shipping/ghtk?token=bi-mat-nghiem-thu", content="rac",
                         headers={"Content-Type": "text/plain"}).status_code == 400


# ------------------------------------------------------------------ 18. địa chỉ sau sáp nhập

def test_18_dia_chi_mau_thuan_khong_len_don(app_that):
    """
    Địa chỉ chắc chắn sai thì không lên đơn (danh mục hành chính sau sáp nhập 2025).

    BƯỚC 1  Công cụ lên đơn nhận "Phường Ba Đình, TP Hồ Chí Minh" → không lên đơn, bảo hỏi lại khách.
    BƯỚC 2  Không đơn nào được ghi vào CSDL.
    BƯỚC 3  Địa chỉ cũ ba cấp ("Phường Bến Nghé, Quận 1, TP HCM") không bị chặn vì lý do địa chỉ.
    """
    from agent import db
    from agent.core import tools

    async def thu(dia_chi):
        return await tools._tao_don_hang({
            "items": [{"ten_san_pham": "không có", "so_luong": 1}], "khach_ten": "Chị Lan",
            "khach_sdt": "0912345678", "khach_dia_chi": dia_chi, "khach_da_xac_nhan": True},
            products=[], conversation_id=None)

    async def dem():
        return (await db.fetchrow("SELECT count(*) n FROM orders"))["n"]
    kq = _sql(app_that, thu, "12 Lê Lợi, Phường Ba Đình, TP Hồ Chí Minh")
    assert kq["tao_duoc"] is False and "Hỏi lại khách" in kq["ly_do"]
    assert _sql(app_that, dem) == 0
    kq = _sql(app_that, thu, "5 Nguyễn Huệ, Phường Bến Nghé, Quận 1, TP HCM")
    assert "Hỏi lại khách" not in kq.get("ly_do", "")
