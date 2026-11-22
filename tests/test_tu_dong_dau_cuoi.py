"""
Quy tắc tự động ĐẦU-CUỐI: cấu hình trên dashboard → tin khách thật → đúng
những gì đã cấu hình, trên `agent.main.app` đầy đủ và Postgres thật.

Mục 7.10 của bảng "Check list công việc": lưu, sửa, bật/tắt và CHẠY quy
tắc phải đúng như cấu hình. Test từng mảnh (tests/test_tu_dong.py) gọi
thẳng `chay_tin_khach`; test này đi đúng đường khách đi — webchat →
`handle_inbound` → quy tắc → (AI hoặc không) — để thấy các mảnh nối nhau,
đặc biệt chỗ giao giữa quy tắc và AI: một tin khách không được nhận hai câu
trả lời, và AI không được im ở tin sau.

Model KHÔNG được gọi: `brain.respond` được thay bằng hàm đếm lượt, trả một
câu cố định. Thứ cần kiểm là AI CÓ được gọi hay không ở từng tin.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT_ID", "test")

from conftest import GOC_WEB  # noqa: E402
from test_nghiem_thu_saas import _hoi_thoai_dau, _kenh_webchat, _quan_tri_vao, _sql  # noqa: E402

CHAO = "Dạ shop chào chị, chị cần em tư vấn gì ạ?"
GIA = "Dạ bảng giá sỉ em gửi chị ngay ạ."
SHIP = "Dạ shop giao toàn quốc, phí ship 30.000đ ạ."


def _mo_phien(khach, tk: str) -> str:
    """MỘT phiên webchat cho cả kịch bản: cùng khách, cùng hội thoại."""
    khach.cookies.clear()
    r = khach.post(f"/webchat/{tk}/session", json={}, headers={"Origin": GOC_WEB})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _nhan(khach, tk: str, ve: str, text: str) -> None:
    khach.cookies.clear()
    r = khach.post(f"/webchat/{tk}/messages",
                   json={"client_message_id": str(uuid4()), "text": text,
                         "visitor_name": "Chị Hoa"},
                   headers={"Origin": GOC_WEB, "Authorization": f"Bearer {ve}"})
    assert r.status_code == 202, r.text


def _trang_thai(khach, cid) -> dict:
    from agent import db

    async def doc(cid_):
        mau = [r["content"] for r in await db.fetch(
            "SELECT content FROM messages WHERE conversation_id = $1 AND content = ANY($2::text[]) "
            "ORDER BY created_at", cid_, [CHAO, GIA, SHIP])]
        ai = (await db.fetchrow("SELECT count(*) n FROM messages WHERE conversation_id = $1 "
                                "AND role = 'agent'", cid_))["n"]
        viec = [r["tieu_de"] for r in await db.fetch(
            "SELECT tieu_de FROM cong_viec WHERE conversation_id = $1", cid_)]
        nhan = [r["ten"] for r in await db.fetch(
            "SELECT n.ten FROM hoi_thoai_gan_nhan g JOIN nhan n ON n.id = g.nhan_id "
            "WHERE g.conversation_id = $1", cid_)]
        nhuong = (await db.fetchrow("SELECT count(*) n FROM events WHERE kind = 'tu_dong.ai_nhuong' "
                                    "AND ref_id = $1", cid_))["n"]
        c = await db.fetchrow("SELECT status, mode FROM conversations WHERE id = $1", cid_)
        return {"mau": mau, "ai": ai, "viec": viec, "nhan": nhan, "nhuong": nhuong,
                "status": c["status"], "mode": c["mode"]}
    return _sql(khach, doc, cid)


def test_quy_tac_cau_hinh_tren_dashboard_chay_dung_tren_luong_tin_vao(app_that, monkeypatch):
    """
    BƯỚC 1  Quản trị tạo 3 mẫu, 1 nhãn hội thoại và 3 quy tắc qua API dashboard (ưu tiên 10/20/30).
    BƯỚC 2  Tin 1 khớp HAI quy tắc: khách nhận MỘT tin (quy tắc ưu tiên hơn), nhãn + việc của cả hai được làm, AI KHÔNG trả lời tin này.
    BƯỚC 3  Tin 2 không khớp quy tắc nào: AI trả lời bình thường.
    BƯỚC 4  Tin 3 khớp quy tắc đã nhường ở tin 1: mẫu của nó giờ mới gửi; việc không tạo lại; AI nhường.
    BƯỚC 5  Tắt quy tắc trên dashboard: tin khớp điều kiện không còn kích hoạt, AI trả lời; hai cờ của quy tắc giữ nguyên.
    BƯỚC 6  Nhân viên tiếp quản: quy tắc vẫn khớp nhưng KHÔNG gửi mẫu chen ngang, nhật ký ghi lý do.
    BƯỚC 7  Danh sách quy tắc hiện lần chạy cuối của từng quy tắc; nhật ký lọc được theo quy tắc.
    """
    from agent import db, runtime
    from agent.core.agent import Reply
    from agent.omnichannel import xu_ly_tin_vao

    monkeypatch.setitem(runtime.STATE, "mode", "auto")
    goi_ai: list[str] = []

    async def respond(**k):
        goi_ai.append(k["question"])
        return Reply(text="Dạ serum bên em còn hàng ạ.", grounded=True)
    monkeypatch.setattr(xu_ly_tin_vao.brain, "respond", respond)

    # BƯỚC 1
    qt = _quan_tri_vao(app_that)
    for ma, nd in (("chao", CHAO), ("gia", GIA), ("ship", SHIP)):
        assert qt.post("/api/tra-loi-nhanh", json={"ma_tat": ma, "noi_dung": nd}).status_code == 201
    r = qt.post("/api/nhan", json={"loai": "hoi_thoai", "ten": "khách mới"})
    assert r.status_code == 201, r.text
    nhan_moi = r.json()["id"]
    r1 = {"ten": "Chào khách mới", "thu_tu": 10, "dieu_kien": {"lan_dau": True},
          "hanh_dong": [{"loai": "gan_nhan_hoi_thoai", "nhan_id": nhan_moi},
                        {"loai": "gui_mau", "ma_tat": "chao"}]}
    r2 = {"ten": "Hỏi giá sỉ", "thu_tu": 20, "dieu_kien": {"chua_tu": ["giá sỉ"]},
          "hanh_dong": [{"loai": "gui_mau", "ma_tat": "gia"},
                        {"loai": "tao_viec", "tieu_de": "Gửi bảng giá sỉ"}],
          "dung_xet_sau": True}
    r3 = {"ten": "Hỏi ship", "thu_tu": 30, "dieu_kien": {"chua_tu": ["ship"]},
          "hanh_dong": [{"loai": "gui_mau", "ma_tat": "ship"}]}
    id_ = {}
    for body in (r1, r2, r3):
        r = qt.post("/api/tu-dong", json=body)
        assert r.status_code == 201, r.text
        id_[body["ten"]] = r.json()["id"]
    tk = _kenh_webchat(qt, agent_bat=True)
    ve = _mo_phien(app_that, tk)

    # BƯỚC 2
    _nhan(app_that, tk, ve, "shop ơi cho em xin giá sỉ")
    cid = _hoi_thoai_dau(app_that)["id"]
    s = _trang_thai(app_that, cid)
    assert s["mau"] == [CHAO], "hai quy tắc cùng khớp mà khách nhận hai câu"
    assert s["nhan"] == ["khách mới"] and s["viec"] == ["Gửi bảng giá sỉ"]
    assert goi_ai == [] and s["ai"] == 0, "quy tắc đã gửi mẫu mà AI vẫn trả lời chính tin đó"
    assert s["nhuong"] == 1 and (s["status"], s["mode"]) != ("escalated", "human")

    # BƯỚC 3
    _nhan(app_that, tk, ve, "serum còn hàng không")
    s = _trang_thai(app_that, cid)
    assert goi_ai == ["serum còn hàng không"] and s["ai"] >= 1, "AI im ở tin sau"
    assert s["mau"] == [CHAO]

    # BƯỚC 4
    _nhan(app_that, tk, ve, "giá sỉ serum thế nào ạ")
    s = _trang_thai(app_that, cid)
    assert s["mau"] == [CHAO, GIA]
    assert s["viec"] == ["Gửi bảng giá sỉ"], "việc một-lần bị tạo lại"
    assert len(goi_ai) == 1 and s["nhuong"] == 2

    # BƯỚC 5 — đúng thân request nút Bật/Tắt cũ gửi: KHÔNG kèm hai cờ.
    r = qt.put(f"/api/tu-dong/{id_['Hỏi giá sỉ']}", json={
        k: v for k, v in r2.items() if k != "dung_xet_sau"} | {"bat": False})
    assert r.status_code == 200 and r.json()["bat"] is False
    assert r.json()["dung_xet_sau"] is True, "bấm Tắt làm mất cờ «dừng xét quy tắc sau»"
    _nhan(app_that, tk, ve, "giá sỉ thì sao")
    assert len(goi_ai) == 2

    # BƯỚC 6
    async def tiep_quan(cid_):
        await db.execute("UPDATE conversations SET mode = 'human', status = 'escalated' "
                         "WHERE id = $1", cid_)
    _sql(app_that, tiep_quan, cid)
    _nhan(app_that, tk, ve, "phí ship bao nhiêu")
    s = _trang_thai(app_that, cid)
    assert s["mau"] == [CHAO, GIA], "quy tắc gửi mẫu chen vào lúc nhân viên đang tiếp"
    assert len(goi_ai) == 2

    # BƯỚC 7
    ds = {q["ten"]: q for q in qt.get("/api/tu-dong").json()["quy_tac"]}
    assert [q["ten"] for q in qt.get("/api/tu-dong").json()["quy_tac"]] == [
        "Chào khách mới", "Hỏi giá sỉ", "Hỏi ship"]
    assert ds["Hỏi ship"]["lan_chay_cuoi"]["ket_qua"] == "bo_qua"
    assert "nhân viên đang tiếp" in ds["Hỏi ship"]["lan_chay_cuoi"]["tom_tat"]
    assert ds["Hỏi giá sỉ"]["bay_ngay"]["da_lam"] == 2
    lc = qt.get(f"/api/tu-dong/lan-chay?quy_tac_id={id_['Hỏi giá sỉ']}").json()["lan_chay"]
    assert len(lc) == 2 and all(x["quy_tac"] == "Hỏi giá sỉ" for x in lc)
    assert "Chào khách mới" in lc[-1]["chi_tiet"]["bo_qua"][0]
