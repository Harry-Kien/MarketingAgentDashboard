"""
Mọi việc trong một hội thoại phải QUY ĐƯỢC về người (hoặc AI) đã làm nó.

Rà soát 20.11.2026: tin AI không lưu hồ sơ agent, lưới đã bắt, công cụ đã
gọi, đoạn tri thức đã đọc; dashboard hiện "Nhân viên" không tên, không hiện
ai duyệt; lịch sử phân công có trong CSDL nhưng không đường nào đọc; nhân
viên thường giành được hội thoại đồng nghiệp đang giữ; hội thoại AI chuyển
người không bao giờ được tự giao. Chạy trên `app_that` — app đầy đủ,
Postgres thật.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from tests.test_gui_tin_va_dieu_phoi import (  # noqa: E402
    _hoi_thoai_cua, _kenh_agent_bat, _khach, _mot, _nhieu, _phien_ban,
    _quan_tri_co_id, _tin,
)
from tests.test_nghiem_thu_saas import (  # noqa: E402
    _kenh_webchat, _khach_nhan, _nhan_vien_moi, _sql, _them_thanh_vien,
)

PII = ("0912345678", "0987654321", "Nguyễn Thị Hoa", "Lê Lợi", "hoa@vidu.vn")


def _reply_co_dau_vet(**them):
    from agent.core import agent as brain

    goc = dict(
        text="Dạ em chuyển chị sang nhân viên ạ", escalate=True,
        escalate_reason="Độ tin cậy thấp (0.30)", confidence=0.3,
        luoi_bat="tin_cay_thap", cost_usd=0.001, model="m-thu", grounded=True,
        cong_cu=[{
            "ten": "len_don", "ms": 5, "vong": 1,
            # Bản trong Reply là bản ĐÃ MỞ che — số thật, tên thật.
            "tham_so": {"khach_ten": "Nguyễn Thị Hoa", "khach_sdt": "0912345678",
                        "khach_dia_chi": "12 Lê Lợi, Q1",
                        "ghi_chu": "gọi 0987654321 hoặc mail hoa@vidu.vn"},
            "ket_qua": {"tim_thay": True, "so_luong": 1},
        }],
        tri_thuc=[{"document_id": str(uuid4()), "version_id": str(uuid4()),
                   "version": 3, "chunk_id": str(uuid4()),
                   "title": "Chính sách đổi trả", "source": "doi-tra.md",
                   "published_at": None}],
        sources=["Chính sách đổi trả"],
    )
    goc.update(them)
    return brain.Reply(**goc)


def _gia_lap_ai(monkeypatch, reply):
    from agent.core import agent as brain

    async def tra_loi(**kw):
        return reply
    monkeypatch.setattr(brain, "respond", tra_loi)


# ------------------------------------------------------------------ 1. dấu vết AI

def test_dau_vet_ai_ghi_vao_ban_nhap_va_khong_chua_du_lieu_ca_nhan(app_that, monkeypatch):
    _gia_lap_ai(monkeypatch, _reply_co_dau_vet())
    qt, tk = _kenh_agent_bat(app_that, monkeypatch)
    _khach(app_that, tk, "Chị Hoa")("cho chị hỏi đổi trả")
    cid = _hoi_thoai_cua(app_that, tk)

    dong = _mot(app_that, "SELECT id, dau_vet_ai FROM messages WHERE conversation_id = $1::uuid "
                          "AND role = 'agent' AND delivery_status = 'draft'", cid)
    assert dong is not None and dong["dau_vet_ai"], "bản nháp AI phải mang dấu vết"
    dv = dong["dau_vet_ai"]
    assert dv["ho_so"]["ten"] == "Mặc định"
    assert dv["tin_cay"]["diem"] == 0.3 and dv["tin_cay"]["nguong"] > 0
    assert dv["luoi"] == {"ma": "tin_cay_thap", "nhan": dv["luoi"]["nhan"], "la_luoi": True}
    assert dv["chuyen_nguoi"]["co"] is True
    assert dv["che_do"]["chung"] == "auto" and dv["che_do"]["tu_gui"] is False
    assert dv["tri_thuc"][0]["title"] == "Chính sách đổi trả" and dv["tri_thuc"][0]["version"] == 3
    assert dv["cong_cu"][0]["ten"] == "len_don"
    chu = json.dumps(dv, ensure_ascii=False)
    for pii in PII:
        assert pii not in chu, f"dấu vết chứa dữ liệu cá nhân thô: {pii}"

    # API chi tiết trả dấu vết và tác giả cho dashboard.
    chi_tiet = qt.get(f"/api/inbox/conversations/{cid}").json()
    tin_ai = next(m for m in chi_tiet["messages"] if str(m["id"]) == str(dong["id"]))
    assert tin_ai["tac_gia"]["loai"] == "ai" and tin_ai["tac_gia"]["ten"] == "Mặc định"
    assert tin_ai["dau_vet_ai"]["luoi"]["ma"] == "tin_cay_thap"

    # Lịch sử phân công thấy lần AI chuyển người, kèm lý do.
    ls = qt.get(f"/api/inbox/conversations/{cid}/lich-su-phan-cong").json()["items"]
    chuyen = [m for m in ls if m["loai"] == "chuyen_nguoi"]
    assert chuyen and chuyen[-1]["nguoi_lam"] == "AI"
    assert "Độ tin cậy thấp" in chuyen[-1]["chi_tiet"]


def test_dau_vet_ai_ghi_vao_tin_tu_gui(app_that, monkeypatch):
    _gia_lap_ai(monkeypatch, _reply_co_dau_vet(
        text="Dạ kem này giá 250.000đ ạ", escalate=False, escalate_reason="",
        luoi_bat=None, confidence=0.9))
    _, tk = _kenh_agent_bat(app_that, monkeypatch)
    _khach(app_that, tk, "Chị Mai")("kem chống nắng giá bao nhiêu?")
    cid = _hoi_thoai_cua(app_that, tk)
    dong = _mot(app_that, "SELECT dau_vet_ai, delivery_status FROM messages "
                          "WHERE conversation_id = $1::uuid AND role = 'agent' "
                          "AND content LIKE '%250.000%'", cid)
    assert dong is not None and dong["delivery_status"] != "draft"
    assert dong["dau_vet_ai"]["che_do"]["tu_gui"] is True
    assert dong["dau_vet_ai"]["luoi"] is None


# ------------------------------------------------------------------ 2. tên người trên từng tin

def test_chi_tiet_hoi_thoai_noi_ten_nguoi_gui_nguoi_sua_nguoi_duyet(app_that):
    sep_id, qt = _quan_tri_co_id(app_that, "sep")
    _mot(app_that, "UPDATE nguoi_dung SET ho_ten = 'Chị Sếp' WHERE id = $1::uuid "
                   "RETURNING 1", sep_id)
    tk = _kenh_webchat(qt)
    lan_id, lan = _nhan_vien_moi(qt, "lan")
    _them_thanh_vien(app_that, tk, lan_id)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo shop")
    cid = _hoi_thoai_cua(app_that, tk)

    assert lan.post(f"/api/conversations/{cid}/send", json={"text": "Dạ em Lan đây ạ"}).status_code == 200
    nhap = _tin(app_that, cid, "agent", "draft")
    r = qt.post(f"/api/messages/{nhap}/approve", json={"noi_dung": "Dạ bản đã sửa ạ"})
    assert r.status_code == 200, r.text

    msgs = {str(m["id"]): m for m in qt.get(f"/api/inbox/conversations/{cid}").json()["messages"]}
    tin_lan = next(m for m in msgs.values() if m["role"] == "staff")
    assert tin_lan["tac_gia"] == {**tin_lan["tac_gia"], "loai": "nhan_vien", "ten": "Lan"}
    tg = msgs[nhap]["tac_gia"]
    assert tg["sua_boi"] == "Chị Sếp", "người sửa phải hiện TÊN, không phải tên đăng nhập"
    assert tg["duyet_boi"] == "Chị Sếp" and tg["duyet_luc"] is not None
    assert msgs[nhap]["dau_vet_ai"] is None      # tin AI cũ/thủ công: không bịa dấu vết


# ------------------------------------------------------------------ 3. ai được lấy hội thoại của ai

def _hai_nhan_vien_va_quan_ly(app):
    _, qt = _quan_tri_co_id(app, "sep")
    tk = _kenh_webchat(qt)       # agent TẮT: tin khách chuyển người ngay
    ids = {}
    nguoi = {}
    for ten, vai in (("lan", "agent"), ("minh", "agent"), ("quanly", "manager")):
        uid, nv = _nhan_vien_moi(qt, ten)
        _them_thanh_vien(app, tk, uid, vai)
        ids[ten], nguoi[ten] = uid, nv
    return qt, tk, ids, nguoi


def _nhan(nv, cid, app, **them):
    return nv.post(f"/api/inbox/conversations/{cid}/takeover", json={
        "expected_version": _phien_ban(app, cid), "reason": "nhận xử lý", **them})


def test_nhan_vien_khong_gianh_duoc_hoi_thoai_dong_nghiep_dang_giu(app_that):
    """
    Lỗi cũ: `can_assign` cho mọi thành viên kênh tự nhận — kể cả hội thoại
    đồng nghiệp đang giữ. Dashboard ẩn nút, nhưng gọi thẳng API là qua.
    """
    _, tk, ids, nv = _hai_nhan_vien_va_quan_ly(app_that)
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)

    assert _nhan(nv["lan"], cid, app_that).status_code == 200
    assert _nhan(nv["minh"], cid, app_that).status_code == 403
    assert str(_mot(app_that, "SELECT assigned_to FROM conversations WHERE id = $1::uuid",
                    cid)["assigned_to"]) == ids["lan"]
    # Nhân viên thường cũng không giao được cho người khác (luật có sẵn).
    assert _nhan(nv["minh"], cid, app_that, assignee_id=ids["minh"]).status_code == 403
    # Quản lý kênh thì lấy được — đó là đường bàn giao có chủ đích.
    assert _nhan(nv["quanly"], cid, app_that).status_code == 200


def test_giao_cho_nguoi_khac_kem_nhom_va_lich_su_ghi_ten(app_that):
    qt, tk, ids, nv = _hai_nhan_vien_va_quan_ly(app_that)
    nhom = _mot(app_that, "INSERT INTO teams (name) VALUES ('Nhóm Da') RETURNING id")["id"]
    _mot(app_that, "INSERT INTO team_members (team_id, user_id) VALUES ($1, $2::uuid) "
                   "RETURNING 1", nhom, ids["lan"])
    _khach_nhan(app_that, tk, "Chị Hoa", "alo")
    cid = _hoi_thoai_cua(app_that, tk)

    # Danh sách người nhận được: quản trị thấy nút giao, nhân viên thường không.
    ds = qt.get(f"/api/inbox/conversations/{cid}/nguoi-nhan-duoc").json()
    assert {"Lan", "Minh"} <= {n["ten"] for n in ds["nguoi"]} and ds["co_the_giao_khac"] is True
    assert {"id": str(nhom), "ten": "Nhóm Da"} in ds["nhom"]
    assert nv["minh"].get(f"/api/inbox/conversations/{cid}/nguoi-nhan-duoc").json()[
        "co_the_giao_khac"] is False

    # Người nhận KHÔNG thuộc nhóm đã chọn -> từ chối, kể cả quản trị.
    assert _nhan(qt, cid, app_that, assignee_id=ids["minh"], team_id=str(nhom)).status_code == 403
    assert _nhan(qt, cid, app_that, assignee_id=ids["lan"], team_id=str(nhom)).status_code == 200

    ct = qt.get(f"/api/inbox/conversations/{cid}").json()
    assert ct["assigned_to_ten"] == "Lan" and ct["assigned_team_ten"] == "Nhóm Da"
    ls = qt.get(f"/api/inbox/conversations/{cid}/lich-su-phan-cong").json()["items"]
    giao = [m for m in ls if m["loai"] == "giao"]
    assert giao and "giao cho Lan" in giao[-1]["tieu_de"] and giao[-1]["nhom"] == "Nhóm Da"

    v = _phien_ban(app_that, cid)
    assert nv["lan"].post(f"/api/inbox/conversations/{cid}/release", json={
        "expected_version": v, "reason": "xong việc"}).status_code == 200
    ls = qt.get(f"/api/inbox/conversations/{cid}/lich-su-phan-cong").json()["items"]
    assert ls[-1]["loai"] == "tra_ai" and ls[-1]["nguoi_lam"] == "Lan"
    assert [m for m in ls if m["loai"] == "giao"][-1]["ket_thuc"] is not None
    # Người ngoài kênh: 404, không xác nhận hội thoại tồn tại.
    _, ngoai = _nhan_vien_moi(qt, "ngoai")
    assert ngoai.get(f"/api/inbox/conversations/{cid}/lich-su-phan-cong").status_code == 404


# ------------------------------------------------------------------ 4. bộ lọc hộp thư

def test_bo_loc_chua_giao_nhom_va_qua_han_sla(app_that):
    qt, tk, ids, nv = _hai_nhan_vien_va_quan_ly(app_that)
    for ten in ("Khách A", "Nhóm B", "Khách C"):
        _khach_nhan(app_that, tk, ten, "alo")
    hang = {r["customer_name"]: str(r["id"]) for r in _nhieu(
        app_that, "SELECT id, customer_name FROM conversations WHERE account_id = $1::uuid", tk)}
    a, b, c = hang["Khách A"], hang["Nhóm B"], hang["Khách C"]
    _mot(app_that, "UPDATE conversations SET thread_type = 1 WHERE id = $1::uuid RETURNING 1", b)
    assert _nhan(nv["lan"], a, app_that).status_code == 200
    han = _mot(app_that, "UPDATE conversations SET first_responded_at = NULL, "
                         "first_response_due_at = coalesce(first_response_due_at, "
                         "now() - interval '1 hour') WHERE id = $1::uuid "
                         "RETURNING first_response_due_at, sla_chu_ky", c)
    _mot(app_that, "INSERT INTO sla_events (conversation_id, kind, due_at, chu_ky) "
                   "VALUES ($1::uuid, 'first_response_breached', $2, $3) "
                   "ON CONFLICT DO NOTHING RETURNING 1",
         c, han["first_response_due_at"], han["sla_chu_ky"])

    def ids_loc(q: str) -> set[str]:
        r = qt.get(f"/api/inbox/conversations?account_id={tk}&{q}")
        assert r.status_code == 200, r.text
        return {str(i["id"]) for i in r.json()["items"]}

    assert ids_loc("loai=nhom") == {b}
    assert ids_loc("loai=rieng") == {a, c}
    assert a not in ids_loc("chua_giao=true") and {b, c} <= ids_loc("chua_giao=true")
    assert ids_loc(f"assignee_id={ids['lan']}") == {a}
    assert ids_loc("qua_han_sla=true") == {c}
    # Lọc ra thì huy hiệu phải khớp: cùng một định nghĩa.
    assert all(i["sla_breached"] for i in qt.get(
        f"/api/inbox/conversations?account_id={tk}&qua_han_sla=true").json()["items"])
    assert qt.get(f"/api/inbox/conversations?chua_giao=true&assignee_id={ids['lan']}"
                  ).status_code == 422
    bl = qt.get("/api/inbox/bo-loc").json()
    assert tk in {str(k["id"]) for k in bl["kenh"]} and "Lan" in {n["ten"] for n in bl["nguoi"]}


# ------------------------------------------------------------------ 5. tự giao hội thoại AI chuyển người

def _quet_dinh_tuyen(app) -> dict:
    from agent.omnichannel.auto_routing import (
        AutoRoutingService, AutoRoutingWorker, PostgresAutoRoutingRepository,
    )

    async def quet():
        repo = PostgresAutoRoutingRepository()
        return await AutoRoutingWorker(repo, AutoRoutingService(repo)).scan_once("kt")
    return _sql(app, quet)


def test_hoi_thoai_chuyen_nguoi_chua_ai_giu_duoc_tu_giao_kem_cong_viec(app_that):
    qt, tk, ids, nv = _hai_nhan_vien_va_quan_ly(app_that)
    nhom = _mot(app_that, "INSERT INTO teams (name) VALUES ('Trực') RETURNING id")["id"]
    _mot(app_that, "INSERT INTO team_members (team_id, user_id) VALUES ($1, $2::uuid) "
                   "RETURNING 1", nhom, ids["lan"])
    _mot(app_that, "INSERT INTO routing_rules (account_id, team_id) VALUES ($1::uuid, $2) "
                   "RETURNING 1", tk, nhom)

    _khach_nhan(app_that, tk, "Khách chờ", "alo")             # agent tắt -> chuyển người
    cho = _hoi_thoai_cua(app_that, tk)
    _khach_nhan(app_that, tk, "Khách đã có người", "alo")
    co_nguoi = _hoi_thoai_cua(app_that, tk)
    # Minh trả lời mà không bấm "Tôi tiếp quản": đã có người cầm trên thực tế.
    assert nv["minh"].post(f"/api/conversations/{co_nguoi}/send",
                           json={"text": "Dạ em Minh đây"}).status_code == 200
    for cid in (cho, co_nguoi):
        hk = _mot(app_that, "SELECT mode, assigned_to FROM conversations WHERE id = $1::uuid", cid)
        assert hk["mode"] == "human" and hk["assigned_to"] is None

    _quet_dinh_tuyen(app_that)

    hk = _mot(app_that, "SELECT mode, assigned_to, assigned_team_id FROM conversations "
                        "WHERE id = $1::uuid", cho)
    assert str(hk["assigned_to"]) == ids["lan"] and hk["assigned_team_id"] == nhom
    assert hk["mode"] == "human", "giao người không được bật lại AI"
    viec = _mot(app_that, "SELECT nguoi_nhan FROM cong_viec WHERE conversation_id = $1::uuid "
                          "AND nguon = 'agent'", cho)
    assert viec and str(viec["nguoi_nhan"]) == ids["lan"]
    assert _mot(app_that, "SELECT assigned_to FROM conversations WHERE id = $1::uuid",
                co_nguoi)["assigned_to"] is None, "đã có nhân viên trả lời thì không giao lại"
    ls = qt.get(f"/api/inbox/conversations/{cho}/lich-su-phan-cong").json()["items"]
    assert any(m["loai"] == "tu_giao" and m["nguoi_nhan"] == "Lan" for m in ls)

    # Người đang giữ thì lượt quét sau không đụng tới.
    _quet_dinh_tuyen(app_that)
    assert _mot(app_that, "SELECT count(*) n FROM conversation_assignments "
                          "WHERE conversation_id = $1::uuid", cho)["n"] == 1
