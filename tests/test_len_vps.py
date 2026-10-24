"""
Đường lên VPS: chuyển nhà, Vertex qua service account, ERPNext, cài máy chủ.

Diễn tập thật 24.10.2026 (Docker của máy cũ đóng vai VPS) đã chạy trọn:
gói nóng cửa hàng thật -> nhập -> 198/198 tin, ERP xác thực bằng khoá API
cũ, kho bí mật giải mã token kênh, sao lưu + thử phục hồi. Test ở đây canh
phần LOGIC của các bước ấy để lần sửa sau không âm thầm làm gãy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts import chuyen_nha as cn
from scripts import cua_hang as ch

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- khoá GCP

def _khoa(tmp_path, **d):
    goc = {"type": "service_account", "project_id": "du-an", "client_email": "a@du-an.iam",
           "private_key": "-----BEGIN PRIVATE KEY-----\nBI-MAT\n-----END PRIVATE KEY-----\n"}
    goc.update(d)
    p = tmp_path / "k.json"
    p.write_text(json.dumps(goc), encoding="utf-8")
    return p


def test_khoa_gcp_hop_le_khong_tra_private_key(tmp_path):
    kq = ch.doc_khoa_gcp(_khoa(tmp_path))
    assert kq == {"project_id": "du-an", "client_email": "a@du-an.iam"}
    assert "BI-MAT" not in json.dumps(kq)


@pytest.mark.parametrize("sua", [{"type": "authorized_user"}, {"private_key": ""}, {"project_id": ""}])
def test_khoa_gcp_sai_bi_chan(tmp_path, sua):
    with pytest.raises(ch.LoiCuaHang):
        ch.doc_khoa_gcp(_khoa(tmp_path, **sua))


def test_sinh_tep_co_gcp_mount_chi_doc_va_vertex():
    tep = ch.sinh_tep("shopa", "shopa.vi-du.vn", ch.sinh_bi_mat(),
                      gcp={"project_id": "du-an", "client_email": "a@du-an.iam"})
    assert "./gcp.json:/run/secrets/gcp.json:ro" in tep["compose.yml"]
    env = tep[".env"]
    assert "LLM_PROVIDER=gemini\n" in env and "GCP_PROJECT_ID=du-an" in env
    assert "GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp.json" in env
    assert "«" not in env and "«" not in tep["compose.yml"]


def test_sinh_tep_khong_gcp_thi_gemini_api_va_khong_mount():
    tep = ch.sinh_tep("shopa", "shopa.vi-du.vn", ch.sinh_bi_mat())
    assert "LLM_PROVIDER=gemini_api" in tep[".env"]
    assert "gcp.json" not in tep["compose.yml"]


# ---------------------------------------------------------------- chuyển nhà

def test_khong_mang_khoa_cua_may_nhung_mang_khoa_kho_bi_mat():
    env = {"CREDENTIAL_MASTER_KEYS": "1:k", "DATABASE_URL": "postgresql://x", "PUBLIC_BASE_URL": "u",
           "GIO_LAM_VIEC_BAT_DAU": "8", "ERPNEXT_URL": "http://localhost:8080", "META_APP_ID": "1"}
    kq = cn.cau_hinh_mang_theo(env)
    assert kq == {"CREDENTIAL_MASTER_KEYS": "1:k", "GIO_LAM_VIEC_BAT_DAU": "8", "META_APP_ID": "1"}


def test_thieu_khoa_kho_bi_mat_thi_khong_dong_goi():
    """Thiếu nó thì mọi token kênh trong CSDL thành rác trên VPS."""
    with pytest.raises(cn.LoiChuyen):
        cn.cau_hinh_mang_theo({"GIO_LAM_VIEC_BAT_DAU": "8"})


def test_du_lieu_bo_nhat_ky_va_sao_luu_cu(tmp_path):
    for t in ("catalog.json", "knowledge/a.md", "uploads/x.jpg", "backup/2026.dump",
              "uvicorn.log", "uvicorn.log.err", "tunnel.log", ".canh_gac_ngoai",
              "catalog.json.bak", "eval/ket-qua-1.json", "eval/golden.example.jsonl"):
        f = tmp_path / t
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x", encoding="utf-8")
    giu = {p.relative_to(tmp_path).as_posix() for p in cn.tep_du_lieu(tmp_path)}
    assert giu == {"catalog.json", "knowledge/a.md", "uploads/x.jpg", "eval/golden.example.jsonl"}


def test_gop_env_thay_tai_cho_va_them_khoi_rieng():
    env = "A=1\nCREDENTIAL_MASTER_KEYS=1:moi\n# chu thich\n"
    ra = ch.gop_env(env, {"CREDENTIAL_MASTER_KEYS": "1:cu", "B": "2"})
    assert "CREDENTIAL_MASTER_KEYS=1:cu" in ra and "1:moi" not in ra
    assert ra.index("B=2") > ra.index("Mang từ máy cũ")


def test_nhap_vertex_khong_khoa_thi_chan():
    with pytest.raises(ch.LoiCuaHang, match="gcp-khoa"):
        ch.cau_hinh_nhap({"LLM_PROVIDER": "gemini"}, co_gcp=False, co_erp_vps=False, dien_tap=False)


def test_nhap_co_khoa_thi_bo_cau_hinh_mo_hinh_cu():
    ra = ch.cau_hinh_nhap({"LLM_PROVIDER": "gemini", "GCP_PROJECT_ID": "du-an-cu", "X": "1"},
                          co_gcp=True, co_erp_vps=False, dien_tap=False)
    assert ra == {"X": "1"}


def test_nhap_erp_tro_vao_erp_cua_vps_hoac_chan():
    with pytest.raises(ch.LoiCuaHang, match="erp khoi_tao"):
        ch.cau_hinh_nhap({"ERP_LOAI": "erpnext"}, co_gcp=False, co_erp_vps=False, dien_tap=False)
    ra = ch.cau_hinh_nhap({"ERP_LOAI": "erpnext"}, co_gcp=False, co_erp_vps=True, dien_tap=False)
    assert ra["ERPNEXT_URL"] == ch.ERP_URL_NOI_BO


def test_dien_tap_tat_vong_nen_va_bao_dong():
    """Diễn tập cạnh cửa hàng thật: hai outbox là tin đôi, hai sidecar một phiên là Zalo đá văng."""
    ra = ch.cau_hinh_nhap({"CANH_GAC_WEBHOOK": "https://that"}, co_gcp=False, co_erp_vps=False,
                          dien_tap=True)
    assert ra["VAI_TRO_TIEN_TRINH"] == "api" and ra["CANH_GAC_WEBHOOK"] == ""


# ---------------------------------------------------------------- ERPNext + cổng

def _cong_publish(tep: Path) -> dict[str, list[str]]:
    """Dịch vụ -> danh sách cổng publish, đọc thô theo thụt lề (không cần PyYAML)."""
    ra: dict[str, list[str]] = {}
    dv = None
    trong_ports = False
    for d in tep.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^  ([a-z0-9_-]+):\s*$", d)
        if m:
            dv, trong_ports = m.group(1), False
            continue
        if re.match(r"^    ports:\s*$", d):
            trong_ports = True
            continue
        if trong_ports and re.match(r"^      - ", d):
            ra.setdefault(dv or "?", []).append(d.split("-", 1)[1].strip().strip('"'))
        elif not d.startswith("      "):
            trong_ports = False
    return ra


@pytest.mark.parametrize("tep", ["docker-compose.nen.yml", "docker-compose.erpnext.yml",
                                 "mau/compose.cua_hang.yml"])
def test_chi_caddy_publish_cong(tep):
    """Docker vượt ufw cho cổng nó publish — cổng nào lọt ra là ra thẳng Internet."""
    cong = _cong_publish(ROOT / "trien_khai" / tep)
    assert set(cong) <= {"caddy"}, f"{tep}: dịch vụ ngoài Caddy publish cổng: {cong}"
    if cong:
        assert sorted(cong["caddy"]) == ["443:443", "80:80"]


def test_erp_vps_ghim_dung_ban_dang_giu_du_lieu():
    """Khôi phục vào mã khác phiên bản là di trú CSDL không lùi được."""
    vps = (ROOT / "trien_khai" / "docker-compose.erpnext.yml").read_text(encoding="utf-8")
    may = (ROOT / "docker-compose.erpnext.yml").read_text(encoding="utf-8")
    dg = re.search(r"frappe/erpnext@(sha256:[0-9a-f]{64})", vps).group(1)
    assert dg in may, "ERPNext trên VPS và máy cũ phải cùng một digest"
    for dv in ("queue-short", "queue-long", "scheduler", "websocket", "frontend", "backend"):
        assert f"  {dv}:" in vps, f"thiếu dịch vụ {dv} — việc nền của ERPNext sẽ không chạy"


def test_erp_vps_khong_go_cung_mat_khau():
    vps = (ROOT / "trien_khai" / "docker-compose.erpnext.yml").read_text(encoding="utf-8")
    assert "erpnext_root_password" not in vps and "${ERP_DB_MAT_KHAU:?" in vps


def test_caddy_erp():
    c = ch.sinh_caddy_erp("erp.vi-du.vn")
    assert "reverse_proxy cskh-erp-frontend:8080" in c and "max_size 50MB" in c


# ---------------------------------------------------------------- cài VPS

def test_script_cai_vps_lf_va_lich_dung_lenh_co_that():
    sh = (ROOT / "trien_khai" / "cai_vps.sh").read_bytes()
    assert b"\r" not in sh, "CRLF trong .sh là bash trên VPS báo '\\r: command not found'"
    noi = sh.decode("utf-8")
    assert "python3-cryptography" in noi, "thiếu thì `cua_hang nhap` nổ trên python3 của máy"
    lenh = set(re.findall(r"scripts\.cua_hang (\w+)", noi))
    ap = (ROOT / "scripts" / "cua_hang.py").read_text(encoding="utf-8")
    for l in lenh:
        assert re.search(rf'add_parser\("{l}"|"{l}"', ap), f"cai_vps.sh gọi lệnh không có: {l}"
    for can in ("kiem --sua", "sao_luu --tat-ca", "thu_phuc_hoi --tat-ca"):
        assert can in noi, f"cron thiếu: {can}"


def test_huong_dan_len_vps_co_va_dan_dung_lenh():
    doc = (ROOT / "docs" / "len-vps.md").read_text(encoding="utf-8")
    for can in ("cai_vps.sh", "chuyen_nha dong_goi --dung-may-nay", "cua_hang nhap",
                "--gcp-khoa", "san_sang"):
        assert can in doc, can
