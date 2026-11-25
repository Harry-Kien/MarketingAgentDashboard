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
  // Hướng dẫn "bấm để làm gì" chỉ có nghĩa khi CÒN việc để làm.
  const huongDan = nhom === "can_xu_ly" ? (t.huong_dan || CHUONG_HUONG_DAN[t.loai] || "").trim() : "";
  return `<button type="button" class="chuong__dong chuong__dong--${esc(nhom)}${t.da_doc ? "" : " is-moi"}" role="listitem"
      data-tb="${esc(t.id)}" title="${esc(noiDung)}">
    <span class="chuong__hang">
      <span class="chuong__loai chuong__loai--${esc(t.loai)}">${esc(t.nhan_loai)}</span>
      <span class="chuong__nhom chuong__nhom--${esc(nhom)}">${esc(CHUONG_NHOM[nhom] || "")}</span>
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

/* Đi tới chỗ thông báo trỏ vào. Dùng đúng đường điều hướng sẵn có
 * (`doiMan`, `state.openConv`) — một lối thứ hai là một chỗ nữa để lệch. */
async function diToiLienKet(lk) {
  if (!lk) return;
  if (lk.loai === "hoi_thoai") {
    state.openConv = lk.id;
    state.mobileViewingChat = true;
    state.cuonToiChiTiet = true;
    doiMan("hoithoai");
    return;
  }
  if (lk.loai === "don_hang") { doiMan("donhang"); return; }
  if (lk.loai === "cong_viec") {
    /* Màn Công việc mới (25-cong-viec.js) mở thẳng chi tiết + lịch sử, bất
       kể bộ lọc đang chọn. Mô-đun ấy hỏng thì lui về danh sách cũ. */
    if (typeof window.moCongViec === "function" && await window.moCongViec(lk.id)) return;
    doiMan("cv-danh-sach");
    try { await loadCongViec(); } catch { /* vòng làm mới sẽ thử lại */ }
    const dong = $(`#cv-ds [data-cv="${CSS.escape(lk.id)}"]`);
    if (!dong) { toast("Việc này không nằm trong bộ lọc đang chọn ở màn Công việc."); return; }
    dong.scrollIntoView({ behavior: "smooth", block: "center" });
    dong.classList.add("is-chuong");
    setTimeout(() => dong.classList.remove("is-chuong"), 2400);
  }
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
  await diToiLienKet(t.lien_ket);
});

/* Bấm ra ngoài hoặc Esc thì đóng — khung nổi che mất nội dung bên dưới. */
document.addEventListener("click", (e) => {
  if (chuong.mo && !e.target.closest("#chuong")) moDongChuong(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && chuong.mo) { moDongChuong(false); $("#chuongNut")?.focus(); }
});
