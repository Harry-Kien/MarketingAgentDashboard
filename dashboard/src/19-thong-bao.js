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

const chuong = { mo: false, chiChuaDoc: false, ds: [], conNua: false, dangTai: false };

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

function dongThongBao(t) {
  const ai = [t.ten_khach, t.kenh].filter(Boolean).map(esc).join(" · ");
  const noiDung = tbLamSachNoiDung(t);
  const huongDan = (t.huong_dan || CHUONG_HUONG_DAN[t.loai] || "").trim();
  return `<button type="button" class="chuong__dong${t.da_doc ? "" : " is-moi"}" role="listitem"
      data-tb="${esc(t.id)}">
    <span class="chuong__loai chuong__loai--${esc(t.loai)}">${esc(t.nhan_loai)}</span>
    <b class="chuong__tieude">${esc(t.tieu_de)}</b>
    ${ai ? `<span class="chuong__phu">${ai}</span>` : ""}
    ${noiDung ? `<span class="chuong__phu">${esc(noiDung)}</span>` : ""}
    ${huongDan ? `<span class="chuong__huongdan">${esc(huongDan)}</span>` : ""}
    <time class="chuong__gio" datetime="${esc(t.tao_luc)}">${esc(clock(t.tao_luc))}${t.da_doc ? "" : " · chưa đọc"}</time>
  </button>`;
}

function veDanhSachChuong() {
  const ds = $("#chuongDs");
  if (!ds) return;
  ds.innerHTML = chuong.ds.length
    ? chuong.ds.map(dongThongBao).join("")
    : `<p class="empty">${chuong.chiChuaDoc ? "Không có thông báo chưa đọc." : "Chưa có thông báo nào."}</p>`;
  $("#chuongThem").hidden = !chuong.conNua;
}

async function taiDanhSachChuong(them = false) {
  if (chuong.dangTai) return;
  chuong.dangTai = true;
  try {
    const q = new URLSearchParams({ gioi_han: "20", bo_qua: String(them ? chuong.ds.length : 0) });
    if (chuong.chiChuaDoc) q.set("chua_doc", "true");
    const d = await api(`/toi/thong-bao?${q}`);
    chuong.ds = them ? chuong.ds.concat(d.thong_bao) : d.thong_bao;
    chuong.conNua = d.con_nua;
    veSoChuong(d.chua_doc);
    veDanhSachChuong();
  } catch (e) {
    $("#chuongDs").innerHTML = `<p class="empty">Không tải được thông báo: ${esc(e.message)}</p>`;
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

$("#chuongChuaDoc")?.addEventListener("change", (e) => {
  chuong.chiChuaDoc = e.target.checked;
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
