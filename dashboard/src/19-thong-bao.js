/* ---------------- chuông thông báo nội bộ ----------------
 *
 * Chuông nằm ở thanh trên, KHÔNG có mục riêng trên thanh điều hướng: thông
 * báo là lối tắt tới hội thoại / việc / đơn, không phải một màn để làm việc.
 * Bấm một dòng = đánh dấu đã đọc + đi tới chỗ liên quan. Đọc KHÔNG làm xong
 * việc gì: duyệt nháp, nhận hội thoại, đóng việc vẫn làm ở màn của chúng.
 *
 * Số chưa đọc làm mới theo vòng 6 giây và theo luồng SSE (10-vong-lam-moi).
 * Hỏng thì KHÔNG toast — vòng 6 giây sẽ bắn toast mãi — mà giữ số cũ và ghi
 * console; danh sách mở ra thì báo lỗi ngay trong khung. */

/* `loc`: "" (tất cả) | "can_xu_ly" | "chua_doc" — UX-19-04. Lọc ở máy chủ,
   không ở đây: danh sách phân trang 20 dòng, lọc sau khi cắt trang thì "Xem
   thêm" ra trang rỗng dù trang sau còn việc cần xử lý. */
const chuong = { mo: false, loc: "", ds: [], conNua: false, dangTai: false,
                 soChuaDoc: 0, soCanXuLy: 0 };

function veSoChuong(n) {
  const o = $("#chuongSo");
  if (!o) return;
  o.textContent = n > 99 ? "99+" : String(n || "");
  o.hidden = !n;
  $("#chuongNut")?.setAttribute("aria-label", n ? `Thông báo — ${n} chưa đọc` : "Thông báo");
}

async function taiSoThongBao() {
  if (!$("#chuongNut")) return;
  try {
    const d = await api("/toi/thong-bao/so-chua-doc");
    veSoChuong(d.chua_doc);
  } catch (e) {
    console.warn("Không tải được số thông báo chưa đọc", e);
  }
}

const CHUONG_HUONG_DAN = {
  ai_chuyen_giao: "Bấm để mở hội thoại, tiếp quản và phản hồi khách.",
  duoc_giao_hoi_thoai: "Bấm để mở hội thoại và xử lý.",
  can_duyet: "Bấm để kiểm tra và duyệt trước khi gửi.",
  duoc_giao_viec: "Mở công việc để xem chi tiết và thực hiện.",
  sla_sap_tre: "Ưu tiên mở hội thoại phản hồi trước khi quá hạn.",
  sla_tre: "Đã quá hạn SLA — mở hội thoại xử lý ngay.",
  viec_chua_giao: "Mở công việc để phân công người phụ trách.",
  viec_huy: "Kiểm tra thông tin công việc đã hủy.",
  viec_qua_han: "Mở công việc quá hạn để xử lý ngay.",
  kenh_can_xac_thuc: "Mở Kết nối kênh để xác thực lại hoặc quét QR kết nối.",
  tin_nhan_that_bai: "Mở hội thoại hoặc Ca trực để kiểm tra và gửi lại tin.",
  duoc_giao_khach: "Mở hồ sơ khách hàng để theo dõi và chăm sóc.",
};

function tbLamSachNoiDung(t) {
  const goc = String((t && t.noi_dung) || "").trim();
  if (!goc) return "";
  if (t.loai !== "ai_chuyen_giao") return goc;
  const low = goc.toLowerCase();
  if (low.includes("tool_calls") || low.includes("tool_use") || low.includes("malformed_function_call")) {
    return "AI gặp lỗi kỹ thuật khi gọi công cụ hỗ trợ — chưa thể tự trả lời khách.";
  }
  if (low.includes("max_tokens") || low.includes("giới hạn độ dài")) {
    return "AI phản hồi bị gián đoạn do vượt giới hạn độ dài — cần nhân viên trả lời tiếp.";
  }
  if (low.includes("model dừng bất thường")) {
    return "AI gặp sự cố kỹ thuật khi xử lý câu trả lời — cần nhân viên tiếp quản.";
  }
  if (low.includes("độ tin cậy thấp") || low.includes("không đủ căn cứ")) {
    return "AI chưa đủ căn cứ rõ ràng từ tài liệu — cần nhân viên kiểm tra và phản hồi khách.";
  }
  return goc.replace(/\s*\((?:tool_calls|tool_use|\d+(?:\.\d+)?)\)\s*/gi, " ").trim();
}

/* Nhóm hiển thị (UX-19-04), do máy chủ tính từ TÌNH TRẠNG THẬT của thứ được
   trỏ tới (`agent/core/thong_bao_noi_bo.py::LOAI_HANH_DONG`): việc đã xong thì
   "Được giao việc" không còn là "cần xử lý". Thiếu trường (bản máy chủ cũ)
   thì coi là cần xử lý — giấu nhầm một việc cần làm tệ hơn hiện thừa. */
const CHUONG_NHOM = {
  can_xu_ly: "Cần xử lý",
  da_xu_ly: "Đã xử lý",
  thong_tin: "Thông tin",
};

/* Mô tả NGẮN: một câu, tối đa ~110 ký tự. Phần dài vẫn còn trong `title`
   để rê chuột đọc; danh sách là để quét, không phải để đọc từng dòng. */
function tbNgan(chu, toiDa = 110) {
  const s = String(chu || "").trim();
  return s.length > toiDa ? s.slice(0, toiDa - 1).trimEnd() + "…" : s;
}

function dongThongBao(t) {
  const ai = [t.ten_khach, t.kenh].filter(Boolean).map(esc).join(" · ");
  const noiDung = tbLamSachNoiDung(t);
  const nhom = t.nhom || (t.can_xu_ly === false ? "da_xu_ly" : "can_xu_ly");
  const khoa = t.mo_duoc === false;
  const ketQua = khoa ? nhom : (t.ket_qua_nghiep_vu || nhom);
  const nhanTrangThai = khoa
    ? (nhom === "thong_tin" ? "Thông tin" : "Ngoài phạm vi")
    : (t.nhan_trang_thai || CHUONG_NHOM[nhom] || "");
  // Hướng dẫn "bấm để làm gì" chỉ có nghĩa khi CÒN việc để làm và còn quyền mở.
  const huongDan = (!khoa && nhom === "can_xu_ly")
    ? (t.huong_dan || CHUONG_HUONG_DAN[t.loai] || "").trim() : "";
  return `<button type="button" class="chuong__dong chuong__dong--${esc(nhom)}${t.da_doc ? "" : " is-moi"}${khoa ? " chuong__dong--khoa" : ""}" role="listitem"
      data-tb="${esc(t.id)}" title="${esc(noiDung)}">
    <span class="chuong__hang">
      <span class="chuong__loai chuong__loai--${esc(t.loai)}">${esc(t.nhan_loai)}</span>
      <span class="chuong__nhom chuong__nhom--${esc(ketQua)}">${esc(nhanTrangThai)}</span>
      <time class="chuong__gio" datetime="${esc(t.tao_luc)}">${esc(clock(t.tao_luc))}${t.da_doc ? "" : " · chưa đọc"}</time>
    </span>
    <b class="chuong__tieude">${esc(t.tieu_de)}</b>
    ${noiDung ? `<span class="chuong__phu chuong__mota">${esc(tbNgan(noiDung))}</span>` : ""}
    ${ai ? `<span class="chuong__phu chuong__ai">${ai}</span>` : ""}
    ${huongDan ? `<span class="chuong__huongdan">${esc(huongDan)}</span>` : ""}
  </button>`;
}

const CHUONG_RONG = {
  "": "Chưa có thông báo nào.",
  can_xu_ly: "Không còn thông báo nào cần xử lý.",
  chua_doc: "Không có thông báo chưa đọc.",
};

function veLocChuong() {
  $$("[data-chuong-loc]").forEach((b) => {
    const bat = b.dataset.chuongLoc === chuong.loc;
    b.classList.toggle("is-on", bat);
    b.setAttribute("aria-pressed", String(bat));
  });
  const so = { can_xu_ly: chuong.soCanXuLy, chua_doc: chuong.soChuaDoc };
  $$("[data-chuong-so]").forEach((o) => {
    const n = so[o.dataset.chuongSo] || 0;
    o.textContent = n > 99 ? "99+" : String(n || "");
    o.hidden = !n;
  });
}

function veDanhSachChuong() {
  const ds = $("#chuongDs");
  if (!ds) return;
  ds.innerHTML = chuong.ds.length
    ? chuong.ds.map(dongThongBao).join("")
    : `<p class="empty">${CHUONG_RONG[chuong.loc] || CHUONG_RONG[""]}</p>`;
  $("#chuongThem").hidden = !chuong.conNua;
  veLocChuong();
}

/* "Xem thêm" (UX-19-02): khoá nút + chữ "Đang tải…" trong lúc gọi, rồi cuộn
   tới dòng MỚI đầu tiên và đưa focus vào nó. Trước đây 20 dòng mới nối vào
   bên dưới tầm nhìn, nút đứng im — người dùng tưởng nút chết và bấm lại. */
function nutThemChuong(dangTai) {
  const nut = $("#chuongThem");
  if (!nut) return;
  nut.disabled = dangTai;
  nut.setAttribute("aria-busy", String(dangTai));
  nut.innerHTML = dangTai
    ? '<span class="chuong__xoay" aria-hidden="true"></span>Đang tải…' : "Xem thêm";
}

async function taiDanhSachChuong(them = false) {
  if (chuong.dangTai) return;
  chuong.dangTai = true;
  const soCu = them ? chuong.ds.length : 0;
  if (them) nutThemChuong(true);
  try {
    const q = new URLSearchParams({ gioi_han: "20", bo_qua: String(soCu) });
    if (chuong.loc === "chua_doc") q.set("chua_doc", "true");
    if (chuong.loc === "can_xu_ly") q.set("can_xu_ly", "true");
    const d = await api(`/toi/thong-bao?${q}`);
    chuong.ds = them ? chuong.ds.concat(d.thong_bao) : d.thong_bao;
    chuong.conNua = d.con_nua;
    chuong.soChuaDoc = d.chua_doc || 0;
    chuong.soCanXuLy = d.can_xu_ly || 0;
    veSoChuong(d.chua_doc);
    nutThemChuong(false);
    veDanhSachChuong();
    if (them) {
      const moi = $$("#chuongDs [data-tb]")[soCu];
      if (moi) {
        moi.scrollIntoView({ behavior: "smooth", block: "nearest" });
        moi.focus({ preventScroll: true });
      }
    }
  } catch (e) {
    nutThemChuong(false);
    /* Hỏng lúc "Xem thêm" thì GIỮ những dòng đã có — xoá cả danh sách để
       báo một lỗi trang 2 là đổi một sự cố nhỏ lấy một màn trống. */
    if (them) toast(`Không tải thêm được thông báo: ${e.message}`, true);
    else $("#chuongDs").innerHTML = `<p class="empty">Không tải được thông báo: ${esc(e.message)}</p>`;
  } finally {
    chuong.dangTai = false;
  }
}

function moDongChuong(mo) {
  chuong.mo = mo;
  $("#chuongKhung").hidden = !mo;
  $("#chuongNut").setAttribute("aria-expanded", mo ? "true" : "false");
  if (mo) taiDanhSachChuong();
}

/* Đi tới chỗ thông báo trỏ vào. Dùng đúng một đường điều hướng chung cho cả
 * chuông thông báo và Nhật ký hệ thống (BUG-TB-02): mở thẳng side panel đơn
 * hàng, chi tiết hội thoại, chi tiết việc, hồ sơ khách hoặc kết nối kênh. */
async function diToiLienKet(lk, t = null) {
  if (t && t.mo_duoc === false) {
    toast(t.ly_do_khong_mo || "Đối tượng đã bị xóa hoặc bạn không còn quyền truy cập.", true);
    return false;
  }
  if (!lk) return false;
  if (lk.loai === "hoi_thoai") {
    state.openConv = lk.id;
    state.mobileViewingChat = true;
    state.cuonToiChiTiet = true;
    if (doiMan("hoithoai") === false) return false;
    return true;
  }
  if (lk.loai === "don_hang") {
    if (doiMan("donhang") === false) return false;
    if (typeof dhTaiChiTiet === "function") await dhTaiChiTiet(lk.id, true);
    return true;
  }
  if (lk.loai === "cong_viec") {
    if (typeof window.moCongViec === "function") return await window.moCongViec(lk.id);
    if (doiMan("cv-danh-sach") === false) return false;
    return true;
  }
  if (lk.loai === "khach_hang") {
    if (lk.id && typeof openCustomer === "function") {
      openCustomer(lk.id);
      return state.view === "khachhang";
    }
    return doiMan("khachhang") !== false;
  }
  if (lk.loai === "tai_khoan_kenh") {
    return doiMan("cc-ket-noi") !== false;
  }
  return false;
}

$("#chuongNut")?.addEventListener("click", (e) => {
  e.stopPropagation();
  moDongChuong(!chuong.mo);
});

$("#chuongLoc")?.addEventListener("click", (e) => {
  const nut = e.target.closest("[data-chuong-loc]");
  if (!nut || nut.dataset.chuongLoc === chuong.loc) return;
  chuong.loc = nut.dataset.chuongLoc;
  veLocChuong();
  taiDanhSachChuong();
});

$("#chuongThem")?.addEventListener("click", () => taiDanhSachChuong(true));

$("#chuongDocHet")?.addEventListener("click", async () => {
  try {
    await api("/toi/thong-bao/da-doc-het", { method: "POST" });
    await taiDanhSachChuong();
  } catch (e) { toast(e.message, true); }
});

$("#chuongDs")?.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-tb]");
  if (!nut) return;
  const t = chuong.ds.find((x) => x.id === nut.dataset.tb);
  if (!t) return;
  if (!t.da_doc) {
    try {
      await api(`/toi/thong-bao/${encodeURIComponent(t.id)}/da-doc`, { method: "POST" });
      t.da_doc = true;
      taiSoThongBao();
    } catch (err) { console.warn("Không đánh dấu đã đọc được", err); }
  }
  moDongChuong(false);
  await diToiLienKet(t.lien_ket, t);
});

/* Bấm ra ngoài hoặc Esc thì đóng — khung nổi che mất nội dung bên dưới. */
document.addEventListener("click", (e) => {
  if (chuong.mo && !e.target.closest("#chuong")) moDongChuong(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && chuong.mo) { moDongChuong(false); $("#chuongNut")?.focus(); }
});
