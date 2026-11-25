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
    BƯỚC 4  Khách nhắn -> hội thoại chuyển người, chuông báo quản trị (không sinh việc), KHÔNG gọi model.
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
    assert so_viec == 0 and goi_model == 0
    assert qt.get("/api/toi/thong-bao/so-chua-doc").json()["chua_doc"] == 1

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

def test_07_chuyen_giao_bao_nguoi_va_giao_viec(app_that):
    """
    Phân task, quản lý task và thông báo nội bộ.

    BƯỚC 1  Agent tắt -> khách nhắn -> KHÔNG sinh công việc (mục 14.2); Ca trực đếm 0 việc chưa giao.
    BƯỚC 2  "lan" chưa thuộc kênh -> chuông không có gì (không lộ khách kênh khác).
    BƯỚC 3  "lan" vào kênh, khách khác nhắn -> chuông "AI chuyển giao" trỏ tới hội thoại.
    BƯỚC 4  "lan" bấm đã đọc -> hội thoại KHÔNG đổi (đọc không phải là nhận).
    BƯỚC 5  Quản trị tạo việc giao cho "minh" -> chuông của minh có "Được giao việc".
    BƯỚC 6  "lan" (không có cong_viec.giao) đẩy việc sang mình -> 403.
    BƯỚC 7  Quản trị đặt hạn, đánh dấu xong -> xong_luc có, qua_han=false.
    BƯỚC 8  Quản trị tạo việc tay với hạn đã qua -> qua_han=true.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")
    _khach_nhan(app_that, tk, "Chị Hoa", "cần tư vấn")

    assert qt.get("/api/cong-viec").json()["cong_viec"] == []
    assert qt.get("/api/overview").json()["cong_viec"]["chua_giao"] == 0
    assert lan.get("/api/toi/thong-bao").json()["thong_bao"] == []

    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Mai", "shop ơi")
    tb = lan.get("/api/toi/thong-bao").json()
    assert tb["chua_doc"] == 1
    t = tb["thong_bao"][0]
    assert t["loai"] == "ai_chuyen_giao" and t["ten_khach"] == "Chị Mai"
    assert t["lien_ket"]["loai"] == "hoi_thoai"
    cid = t["lien_ket"]["id"]
    assert lan.post(f"/api/toi/thong-bao/{t['id']}/da-doc").status_code == 200
    assert lan.get("/api/toi/thong-bao/so-chua-doc").json()["chua_doc"] == 0
    from agent import db

    async def doc_hk(c):
        return await db.fetchrow(
            "SELECT assigned_to, mode FROM conversations WHERE id = $1::uuid", c)
    hk = _sql(app_that, doc_hk, cid)
    assert hk["assigned_to"] is None and hk["mode"] == "human", (
        "đọc thông báo không được tự nhận hội thoại")

    r = qt.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Hoa", "nguoi_nhan": minh_id})
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    tm = minh.get("/api/toi/thong-bao").json()["thong_bao"]
    assert [x["loai"] for x in tm] == ["duoc_giao_viec"]
    assert tm[0]["lien_ket"] == {"loai": "cong_viec", "id": vid}
    assert lan.put(f"/api/cong-viec/{vid}", json={"nguoi_nhan": lan_id}).status_code in (403, 404)

    r = qt.put(f"/api/cong-viec/{vid}", json={
        "han": "2099-01-01T00:00:00+00:00", "trang_thai": "xong"})
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

    BƯỚC 1  Quản trị tạo mẫu /doitra và nhãn hội thoại «đổi trả»; quy tắc gửi mẫu KHÔNG tồn tại bị từ chối lúc lưu (422).
    BƯỚC 2  Tạo quy tắc «có từ đổi trả → gắn nhãn hội thoại, gửi mẫu /doitra, chuyển người».
    BƯỚC 3  Kênh BẬT agent; khách nhắn "em muốn DOI TRA" (không dấu) → khớp, agent không chạy.
    BƯỚC 4  Hội thoại chuyển người, có nhãn "đổi trả", MỘT thông báo chuyển giao (không sinh việc), mẫu đã vào hàng gửi.
    BƯỚC 5  Nhật ký lần chạy ghi "đã làm"; khách nhắn tiếp không sinh mẫu thứ hai.
    BƯỚC 6  Nhân viên XEM được quy tắc nhưng không sửa được — thiếu quyền sửa định tuyến (403).
    """
    from agent import db

    qt = _quan_tri_vao(app_that)
    _, lan = _nhan_vien_moi(qt, "lan")
    assert qt.post("/api/tra-loi-nhanh", json={
        "ma_tat": "doitra", "noi_dung": "Dạ shop hỗ trợ đổi trả trong 7 ngày ạ."}).status_code == 201
    r = qt.post("/api/nhan", json={"loai": "hoi_thoai", "ten": "đổi trả"})
    assert r.status_code == 201, r.text
    doi_tra = r.json()["id"]
    quy_tac = {"ten": "Đổi trả", "dieu_kien": {"chua_tu": ["đổi trả"]},
               "hanh_dong": [{"loai": "gan_nhan_hoi_thoai", "nhan_id": doi_tra},
                             {"loai": "gui_mau", "ma_tat": "khongco"}]}
    assert qt.post("/api/tu-dong", json=quy_tac).status_code == 422
    quy_tac["hanh_dong"] = [{"loai": "gan_nhan_hoi_thoai", "nhan_id": doi_tra},
                            {"loai": "gui_mau", "ma_tat": "doitra"},
                            {"loai": "chuyen_nguoi", "ly_do": "khách hỏi đổi trả"}]
    assert qt.post("/api/tu-dong", json=quy_tac).status_code == 201

    tk = _kenh_webchat(qt, agent_bat=True)
    _khach_nhan(app_that, tk, "Chị Hoa", "em muốn DOI TRA hàng ạ")
    c = _hoi_thoai_dau(app_that)
    assert (c["status"], c["mode"]) == ("escalated", "human")

    async def dem(cid):
        return {
            "nhan": [r["ten"] for r in await db.fetch(
                "SELECT n.ten FROM hoi_thoai_gan_nhan g JOIN nhan n ON n.id = g.nhan_id "
                "WHERE g.conversation_id = $1", cid)],
            "viec": (await db.fetchrow("SELECT count(*) n FROM cong_viec WHERE conversation_id = $1",
                                       cid))["n"],
            "bao": (await db.fetchrow("SELECT count(*) n FROM thong_bao WHERE conversation_id = $1 "
                                      "AND loai = 'ai_chuyen_giao'", cid))["n"],
            "mau": (await db.fetchrow("SELECT count(*) n FROM messages WHERE conversation_id = $1 "
                                      "AND content LIKE 'Dạ shop hỗ trợ đổi trả%'", cid))["n"],
        }
    assert _sql(app_that, dem, c["id"]) == {"nhan": ["đổi trả"], "viec": 0, "bao": 1, "mau": 1}

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
    BƯỚC 2  Hội thoại ở chế độ người, KHÔNG sinh việc, có MỘT thông báo "Khách đòi gặp nhân viên".
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
        viec = [r["noi_dung"] for r in await db.fetch(
            "SELECT noi_dung FROM thong_bao WHERE conversation_id = $1 "
            "AND loai = 'ai_chuyen_giao'", cid)]
        viec_that = (await db.fetchrow(
            "SELECT count(*) n FROM cong_viec WHERE conversation_id = $1", cid))["n"]
        assert viec_that == 0, "đòi gặp nhân viên vẫn sinh công việc (mục 14.2)"
        tin = [r["content"] for r in await db.fetch(
            "SELECT content FROM messages WHERE conversation_id = $1 AND role = 'system'", cid)]
        return viec, tin
    viec, tin = _sql(app_that, doc, c["id"])
    # Nội dung chuông đi qua `chuan_hoa_noi_dung_thong_bao` (UX-19-03): bỏ dấu
    # chấm cuối cho đồng bộ với các thông báo khác.
    assert viec == ["Khách đòi gặp nhân viên"]
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
    BƯỚC 4  Thân rác (không JSON, không form) → 400, có ghi nhật ký.
    BƯỚC 5  Hãng không có ("/webhook/shipping/abc") → 404, không đụng đơn.
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

    async def co_su_kien(kind):
        return (await db.fetchrow("SELECT count(*) n FROM events WHERE kind = $1", kind))["n"]
    assert _sql(app_that, co_su_kien, "shipping.webhook_khong_doc_duoc") == 1
    assert app_that.post("/webhook/shipping/abc?token=bi-mat-nghiem-thu",
                         content="label_id=S1.A1.99&status_id=21", headers=form).status_code == 404
    assert _sql(app_that, don)["trang_thai"] == "da_giao"


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


# ------------------------------------------------------------------ 19. ưu tiên, SLA, phân tích

def test_19_doi_uu_tien_rut_han_sla_va_man_phan_tich(app_that):
    """
    Đổi ưu tiên hội thoại và xem màn Phân tích.

    BƯỚC 1  Quản trị đặt SLA mức thường (60/1440 phút) và gấp (5/30 phút); khách web nhắn → hội thoại có hạn.
    BƯỚC 2  Nhân viên KHÔNG thuộc kênh đổi ưu tiên → 404, không lộ hội thoại tồn tại.
    BƯỚC 3  Quản trị nâng lên "gấp" kèm lý do → hạn phản hồi đầu rút còn tối đa 5 phút từ bây giờ.
    BƯỚC 4  Hạ về "thấp" → hạn KHÔNG kéo dài lại; cả hai lần đổi nằm trong nhật ký kiểm toán.
    BƯỚC 5  Màn Phân tích: quản trị thấy 1 hội thoại mới, 1 khách mới; nhân viên ngoài kênh thấy 0.
    """
    from datetime import datetime, timezone

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    for muc, dau, xong in (("normal", 60, 1440), ("urgent", 5, 30)):
        assert qt.put("/api/routing/sla-policies", json={
            "account_id": tk, "priority": muc, "first_response_minutes": dau,
            "resolution_minutes": xong, "business_hours": {}, "active": True}).status_code == 200
    _khach_nhan(app_that, tk, "Chị Thảo", "shop ơi tư vấn giúp em")
    cid = str(_hoi_thoai_dau(app_that)["id"])
    _, ngoai = _nhan_vien_moi(qt, "binh")

    assert ngoai.put(f"/api/conversations/{cid}/uu-tien",
                     json={"uu_tien": "urgent", "ly_do": "thử"}).status_code == 404

    r = qt.put(f"/api/conversations/{cid}/uu-tien",
               json={"uu_tien": "urgent", "ly_do": "khách khiếu nại giao chậm"})
    assert r.status_code == 200, r.text
    con = (datetime.fromisoformat(r.json()["han_dau_moi"])
           - datetime.now(timezone.utc)).total_seconds()
    assert 0 < con <= 5 * 60 + 5

    r = qt.put(f"/api/conversations/{cid}/uu-tien",
               json={"uu_tien": "low", "ly_do": "khách hẹn mai"})
    assert r.status_code == 200 and r.json()["han_dau_moi"] == r.json()["han_dau_cu"]
    nk = [e for e in qt.get("/api/events?limit=50").json()
          if e["kind"] == "conversation.priority_changed"]
    assert len(nk) == 2

    o = qt.get("/api/phan-tich").json()
    assert o["hoi_thoai"]["moi"] == 1 and o["khach"]["moi"] == 1
    r = ngoai.get("/api/phan-tich")
    assert r.status_code == 200 and r.json()["hoi_thoai"]["moi"] == 0


# ------------------------------------------------------------------ 20. nhãn động

def test_20_quan_ly_nhan_va_gan_nhan_hai_loai(app_that):
    """
    Quản lý nhãn: hai loại độc lập, gắn đúng màn, ngừng thay vì xoá.

    BƯỚC 1  Quản trị tạo nhãn khách «Khách sỉ» và nhãn hội thoại «Chờ hàng»; tạo trùng tên «khách sỉ» → 409.
    BƯỚC 2  Khách web nhắn. Nhân viên trong kênh gắn «Chờ hàng» lên hội thoại; gắn nhãn KHÁCH lên hội thoại → 422.
    BƯỚC 3  Hộp thư lọc theo nhãn «Chờ hàng» ra đúng hội thoại ấy; nhân viên NGOÀI kênh gắn nhãn → 404.
    BƯỚC 4  Customer 360: quản trị gắn «Khách sỉ» cho khách; danh sách khách lọc theo nhãn ra đúng khách ấy.
    BƯỚC 5  Xoá «Khách sỉ» đang dùng → 409; Ngừng sử dụng → biến khỏi ô chọn, khách vẫn mang nhãn (đã ngừng).
    BƯỚC 6  Nhân viên không có quyền cấu hình không sửa được danh mục (403); mọi thao tác nằm trong nhật ký.
    """
    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _, binh = _nhan_vien_moi(qt, "binh")

    r = qt.post("/api/nhan", json={"loai": "khach", "ten": "Khách sỉ"})
    assert r.status_code == 201, r.text
    si = r.json()["id"]
    cho = qt.post("/api/nhan", json={"loai": "hoi_thoai", "ten": "Chờ hàng"}).json()["id"]
    assert qt.post("/api/nhan", json={"loai": "khach", "ten": "khách sỉ"}).status_code == 409

    _khach_nhan(app_that, tk, "Chị Hoa", "bao giờ có hàng ạ")
    cid = str(_hoi_thoai_dau(app_that)["id"])
    r = lan.post(f"/api/inbox/conversations/{cid}/nhan", json={"nhan_id": cho})
    assert r.status_code == 201, r.text
    assert lan.post(f"/api/inbox/conversations/{cid}/nhan",
                    json={"nhan_id": si}).status_code == 422

    loc = lan.get(f"/api/inbox/conversations?nhan_id={cho}").json()["items"]
    assert [x["id"] for x in loc] == [cid]
    assert [x["ten"] for x in loc[0]["nhan_chi_tiet"]] == ["Chờ hàng"]
    assert binh.post(f"/api/inbox/conversations/{cid}/nhan",
                     json={"nhan_id": cho}).status_code == 404

    kh = qt.get("/api/contacts").json()[0]["id"]
    assert qt.post(f"/api/contacts/{kh}/nhan", json={"nhan_id": si}).status_code == 201
    assert [c["id"] for c in qt.get(f"/api/contacts?nhan_id={si}").json()] == [kh]

    assert qt.delete(f"/api/nhan/{si}").status_code == 409
    assert qt.post(f"/api/nhan/{si}/ngung").status_code == 200
    assert si not in [n["id"] for n in qt.get("/api/nhan/khach").json()["nhan"]]
    assert [(n["ten"], n["dang_dung"]) for n in qt.get(f"/api/contacts/{kh}").json()["nhan"]] == [
        ("Khách sỉ", False)]

    assert lan.post("/api/nhan", json={"loai": "khach", "ten": "x"}).status_code == 403
    nk = {e["kind"] for e in qt.get("/api/events?limit=100").json()}
    assert {"nhan.tao", "nhan.gan_hoi_thoai", "nhan.gan_khach", "nhan.ngung"} <= nk


# ------------------------------------------------------------------ 21. hệ thống giao việc

def test_21_he_thong_giao_viec_theo_ca_chuyen_viec_va_lich_su(app_that):
    """
    Hệ thống giao việc: phân công theo ca trực, chuyển việc, tiến độ, kết quả, lịch sử, chuông.

    BƯỚC 1  Chưa ai có lịch ca → tạo việc "phân công tự động" → Chưa phân công, kèm lý do (không đoán người).
    BƯỚC 2  Quản trị xếp ca 24/7 cho "lan" và "minh" → hai việc tự động chia lần lượt cho hai người; mỗi người có chuông "Được giao việc".
    BƯỚC 3  "lan" (không có cong_viec.giao) đẩy việc của mình sang "minh" → 403; quản trị chuyển kèm ghi chú → "minh" có chuông "Bạn được chuyển một việc".
    BƯỚC 4  "minh" ghi tiến độ rồi hoàn thành kèm kết quả → chi tiết việc có đủ lịch sử: tạo, phân công tự động, chuyển, tiến độ, đổi trạng thái, kết quả.
    BƯỚC 5  Quản trị hủy việc còn lại của "minh" → "minh" có chuông "Việc bị hủy".
    BƯỚC 6  Tổng quan ca trực đếm đúng (1 chưa phân công, 1 hoàn thành hôm nay); lọc "Chưa phân công" ra đúng việc ở bước 1.
    """
    qt = _quan_tri_vao(app_that)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    minh_id, minh = _nhan_vien_moi(qt, "minh")

    r = qt.post("/api/cong-viec", json={"tieu_de": "Gọi lại chị Hoa", "giao_tu_dong": True})
    assert r.status_code == 201, r.text
    v1 = r.json()
    assert v1["nguoi_nhan"] is None and "lịch ca" in v1["ly_do_khong_giao"]

    ca = [{"thu": t, "bat_dau": "00:00", "ket_thuc": "24:00"} for t in range(1, 8)]
    for uid in (lan_id, minh_id):
        assert qt.put(f"/api/lich-ca/{uid}", json={"ca": ca}).status_code == 200
    giao = {}
    for ten in ("Xác nhận địa chỉ đơn", "Gửi lại hướng dẫn dùng"):
        r = qt.post("/api/cong-viec", json={"tieu_de": ten, "giao_tu_dong": True})
        assert r.status_code == 201, r.text
        giao[r.json()["nguoi_nhan"]] = r.json()["id"]
    assert set(giao) == {lan_id, minh_id}, "phải chia lần lượt, không dồn cho một người"
    for nv in (lan, minh):
        assert [t["loai"] for t in nv.get("/api/toi/thong-bao").json()["thong_bao"]] == ["duoc_giao_viec"]

    v_lan, v_minh = giao[lan_id], giao[minh_id]
    assert lan.put(f"/api/cong-viec/{v_lan}", json={"nguoi_nhan": minh_id}).status_code == 403
    r = qt.put(f"/api/cong-viec/{v_lan}", json={"nguoi_nhan": minh_id, "ghi_chu": "Lan nghỉ chiều"})
    assert r.status_code == 200, r.text
    assert "Bạn được chuyển một việc" in [
        t["tieu_de"] for t in minh.get("/api/toi/thong-bao").json()["thong_bao"]]

    assert minh.post(f"/api/cong-viec/{v_lan}/tien-do",
                     json={"noi_dung": "Đã gọi, khách hẹn 15h"}).status_code == 201
    r = minh.put(f"/api/cong-viec/{v_lan}", json={"trang_thai": "xong", "ket_qua": "Khách xác nhận địa chỉ"})
    assert r.status_code == 200, r.text
    ct = qt.get(f"/api/cong-viec/{v_lan}").json()
    assert [x["loai"] for x in ct["lich_su"]] == [
        "tao", "tu_dong_giao", "chuyen", "tien_do", "trang_thai", "ket_qua"]
    assert ct["lich_su"][2]["ghi_chu"] == "Lan nghỉ chiều"
    assert ct["cong_viec"]["nhan_trang_thai"] == "Hoàn thành"

    assert qt.put(f"/api/cong-viec/{v_minh}", json={
        "trang_thai": "huy", "ghi_chu": "khách tự xử lý"}).status_code == 200
    assert "viec_huy" in [t["loai"] for t in minh.get("/api/toi/thong-bao").json()["thong_bao"]]

    d = qt.get("/api/cong-viec/tong-quan").json()
    assert d["dem"]["chua_phan_cong"] == 1 and d["dem"]["xong_hom_nay"] == 1
    ds = qt.get("/api/cong-viec?chua_phan_cong=true").json()["cong_viec"]
    assert [v["id"] for v in ds] == [v1["id"]]


# ------------------------------------------------------------------ 22. ủy quyền thực thi của AI

def test_22_uy_quyen_ai_de_xuat_va_phe_duyet(app_that, monkeypatch):
    """
    Ba mức ủy quyền thực thi của AI: chế độ Gợi ý không tự làm, phê duyệt có kiểm lại.

    BƯỚC 1  Cấu hình AI Agent → Chính sách & Ủy quyền: tạo đơn mặc định «Tự động», huỷ đơn «Có phê duyệt», hoàn tiền «Chưa hỗ trợ»; nhân viên không sửa được (403).
    BƯỚC 2  Chế độ Gợi ý: AI chốt đơn với khách → KHÔNG có đơn nào, kho không bị giữ; hội thoại có thẻ «Tạo đơn» chờ duyệt kèm căn cứ (giá danh mục, tồn sống) và rủi ro.
    BƯỚC 3  Quản trị có chuông «AI đề xuất», bấm vào mở đúng hội thoại.
    BƯỚC 4  Nhân viên thuộc kênh (có duyệt AI, KHÔNG có quyền sửa đơn) bấm Phê duyệt → 403.
    BƯỚC 5  Quản trị Phê duyệt → hệ thống lên đơn lại từ đầu → đơn «Đã chốt»; bấm lần hai → 409, không có đơn thứ hai.
    BƯỚC 6  Chế độ Tự động: khách xin huỷ → đơn KHÔNG bị huỷ, có thẻ «Huỷ đơn» chờ duyệt; quản trị Từ chối kèm lý do → đơn giữ nguyên.
    BƯỚC 7  Nhật ký kiểm toán có đủ ai.de_xuat.tao / duyet / thuc_hien / tu_choi gắn với hội thoại.
    """
    from agent import db, runtime
    from agent.config import settings
    from agent.core import tools, uy_quyen
    from agent.erp import nha_may
    from agent.erp.hop_dong import TonKho
    from tests.erp_gia import NguonGia

    sp = {"ma": "SP1", "ten": "Kem dưỡng ẩm Aurora", "gia": 100000}
    nha_may.dat_lai()
    monkeypatch.setattr(nha_may, "tao_nguon", lambda: NguonGia(ton={"SP1": TonKho(ban_duoc=100)}))
    monkeypatch.setattr(settings, "erp_ghi_don", False)

    async def catalog():
        return {"san_pham": [sp]}
    monkeypatch.setattr(tools, "_catalog_song", catalog)
    uy_quyen.xoa_dem()

    qt = _quan_tri_vao(app_that)
    tk = _kenh_webchat(qt)
    _khach_nhan(app_that, tk, "Chị Lan", "em lấy 1 kem dưỡng ẩm nhé")
    cid = _hoi_thoai_dau(app_that)["id"]
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)

    async def sql(cau, *a):
        return [dict(r) for r in await db.fetch(cau, *a)]
    _sql(app_that, sql, "INSERT INTO ton_kho (ma, so_luong) VALUES ('SP1', 100) "
                        "ON CONFLICT (ma) DO UPDATE SET so_luong = 100 RETURNING ma")

    cs = {h["ma"]: h for h in qt.get("/api/ai-uy-quyen").json()["hanh_dong"]}
    assert (cs["tao_don"]["muc"], cs["huy_don"]["muc"]) == ("tu_dong", "co_phe_duyet")
    assert cs["hoan_tien"]["ho_tro"] is False
    assert lan.put("/api/ai-uy-quyen", json={"hanh_dong": {"tao_don": {"muc": "tu_dong"}}}).status_code == 403

    async def cong_cu(ten, args):
        return await tools.run_tool(ten, args, cid)
    don = {"khach_da_xac_nhan": True, "khach_ten": "Chị Lan", "khach_sdt": "0912345678",
           "khach_dia_chi": "12 Lê Lợi, Phường Bến Thành, TP Hồ Chí Minh",
           "items": [{"ten_san_pham": sp["ten"], "so_luong": 1}]}
    monkeypatch.setitem(runtime.STATE, "mode", "assist")
    kq = _sql(app_that, cong_cu, "tao_don_hang", don)
    assert kq["da_de_xuat"] is True and kq["tao_duoc"] is False
    assert _sql(app_that, sql, "SELECT id FROM orders") == []
    assert _sql(app_that, sql, "SELECT so_luong FROM ton_kho WHERE ma = 'SP1'")[0]["so_luong"] == 100
    the = qt.get(f"/api/ai-de-xuat?hoi_thoai={cid}").json()["de_xuat"]
    assert len(the) == 1 and the[0]["nhan_trang_thai"] == "Chờ duyệt"
    assert the[0]["can_cu"]["nguon"] and the[0]["can_cu"]["rui_ro"]

    chuong = [t for t in qt.get("/api/toi/thong-bao").json()["thong_bao"]
              if t["tieu_de"].startswith("AI đề xuất")]
    assert chuong and chuong[0]["lien_ket"] == {"loai": "hoi_thoai", "id": str(cid)}

    did = the[0]["id"]
    assert lan.post(f"/api/ai-de-xuat/{did}/duyet").status_code == 403
    r = qt.post(f"/api/ai-de-xuat/{did}/duyet")
    assert r.status_code == 200 and r.json()["ok"] is True, r.text
    assert [d["trang_thai"] for d in _sql(app_that, sql, "SELECT trang_thai FROM orders")] == ["da_chot"]
    assert qt.post(f"/api/ai-de-xuat/{did}/duyet").status_code == 409
    assert len(_sql(app_that, sql, "SELECT id FROM orders")) == 1

    monkeypatch.setitem(runtime.STATE, "mode", "auto")
    ma = _sql(app_that, sql, "SELECT ma_don FROM orders")[0]["ma_don"]
    kq = _sql(app_that, cong_cu, "xin_huy_don", {"ma_don": ma, "ly_do": "đổi ý"})
    assert kq["da_de_xuat"] is True and kq["da_huy"] is False
    huy = [d for d in qt.get(f"/api/ai-de-xuat?hoi_thoai={cid}").json()["de_xuat"]
           if d["hanh_dong"] == "huy_don"][0]
    r = qt.post(f"/api/ai-de-xuat/{huy['id']}/tu-choi", json={"ly_do": "gọi lại giữ được đơn"})
    assert r.status_code == 200, r.text
    assert _sql(app_that, sql, "SELECT trang_thai FROM orders")[0]["trang_thai"] == "da_chot"

    kinds = {r["kind"] for r in _sql(app_that, sql,
                                     "SELECT kind FROM events WHERE ref_id = $1", cid)}
    assert {"ai.de_xuat.tao", "ai.de_xuat.duyet", "ai.de_xuat.thuc_hien",
            "ai.de_xuat.tu_choi"} <= kinds
    nha_may.dat_lai()
