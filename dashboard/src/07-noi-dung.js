/* ==================== Hộp thoại nhập chung ====================
 *
 * Thay cho prompt() của trình duyệt. prompt() có đúng một ô chữ: không
 * nhãn, không ô số, không ô ngày, không kiểm gì; hỏi hai thứ là hai hộp
 * nối nhau, bấm Huỷ ở hộp sau là mất hộp trước — đo được ở Tạo việc, Nhập
 * kho, Kiểm kê, Gộp khách, Đo bài đăng. Một hộp cho cả app, dựng ô theo mô
 * tả; dùng lại lớp phủ `.cong` của màn đăng nhập nên chỉ có MỘT kiểu hộp
 * thoại. Trả Promise<obj|null>: null là người dùng thôi.
 *
 *   hoiHop({ tieu_de, phu, truong: [{ name, label, type, value, required,
 *            placeholder, hint, min, max, step, maxlength, options, rows }],
 *            nut, nguy_hiem })
 */
let hoiDangMo = null;

function hoiHop({ tieu_de, phu = "", truong = [], nut = "Lưu", nguy_hiem = false }) {
  if (hoiDangMo) hoiDong(null);           // hộp mới thay hộp cũ, không chồng
  $("#hoiTen").textContent = tieu_de;
  $("#hoiPhu").textContent = phu;
  $("#hoiPhu").hidden = !phu;
  $("#hoiLoi").textContent = "";
  $("#hoiTruong").innerHTML = truong.map((t) => {
    const chung = `name="${esc(t.name)}"${t.required ? " required" : ""}`
      + (t.placeholder ? ` placeholder="${esc(t.placeholder)}"` : "")
      + (t.maxlength ? ` maxlength="${t.maxlength}"` : "");
    let o;
    if (t.type === "textarea") {
      o = `<textarea ${chung} rows="${t.rows || 3}">${esc(t.value ?? "")}</textarea>`;
    } else if (t.type === "select") {
      o = `<select ${chung}>${(t.options || []).map((c) =>
        `<option value="${esc(c.value)}"${String(c.value) === String(t.value ?? "") ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select>`;
    } else {
      o = `<input type="${esc(t.type || "text")}" ${chung} value="${esc(t.value ?? "")}"`
        + (t.min != null ? ` min="${t.min}"` : "") + (t.max != null ? ` max="${t.max}"` : "")
        + (t.step != null ? ` step="${t.step}"` : "") + ` autocomplete="off">`;
    }
    return `<label class="field"><span>${esc(t.label)}${
      t.hint ? ` <em class="hint">${esc(t.hint)}</em>` : ""}</span>${o}</label>`;
  }).join("");
  const nutGui = $("#hoiNut");
  nutGui.textContent = nut;
  nutGui.classList.toggle("btn--halt", nguy_hiem);
  nutGui.classList.toggle("btn--primary", !nguy_hiem);
  $("#congHoi").classList.remove("is-off");
  const dau = $("#hoiTruong").querySelector("input, textarea, select");
  if (dau) setTimeout(() => dau.focus(), 0);
  return new Promise((resolve) => { hoiDangMo = resolve; });
}

function hoiDong(gia_tri) {
  $("#congHoi").classList.add("is-off");
  const tra = hoiDangMo;
  hoiDangMo = null;
  if (tra) tra(gia_tri);
}

$("#hoiform")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.currentTarget).entries());
  for (const k of Object.keys(d)) if (typeof d[k] === "string") d[k] = d[k].trim();
  hoiDong(d);
});
$("#hoiHuy")?.addEventListener("click", (e) => { e.preventDefault(); hoiDong(null); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && hoiDangMo) hoiDong(null);
});

/* ---------------- nhật ký ---------------- */

/* Chi tiết sự kiện cho NGƯỜI đọc, không phải JSON thô.
 *
 * `{"muc_do":"hong","tieu_de":"Hệ thống đang hỏng","chi_tiet":...}` dài
 * 2.600 ký tự bị cắt sau 90 — người trực thấy đúng phần vô nghĩa nhất.
 * Báo động thì hiện tiêu đề và chi tiết; lỗi thì hiện lỗi; còn lại là
 * `khoá: giá trị`. JSON đầy đủ vẫn còn trong `title` để rê chuột xem. */
function moTaChiTiet(d) {
  if (d == null) return "";
  if (typeof d !== "object") return String(d);
  if (d.tieu_de) return [d.tieu_de, d.chi_tiet].filter(Boolean).join(" — ");
  if (d.error) return String(d.error);
  return Object.entries(d).map(([k, v]) =>
    `${k}: ${v !== null && typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
}

async function loadEvents() {
  const evs = await api("/events");
  $("#events").innerHTML = evs.length ? evs.map((e) => {
    const tone = e.kind.includes("error") || e.kind.includes("failed") ? "halt"
      : e.kind.includes("escalat") ? "assist" : "auto";
    // Tác nhân là "system" hay UUID toàn số 0 đều là hệ thống tự làm —
    // in chuỗi 36 ký tự ấy ra chỉ tốn chỗ và không ai đọc.
    const ai = !e.actor || e.actor === "system" || /^0{8}-/.test(e.actor) ? "hệ thống" : e.actor;
    return `<div class="row">
      <span class="row__flag row__flag--${tone}"></span>
      <span class="row__body">
        <span class="row__title">${esc(e.kind)}</span>
        <span class="row__sub" title="${esc(JSON.stringify(e.detail))}">${esc(moTaChiTiet(e.detail))}</span>
      </span>
      <span class="row__side">
        <span class="row__num">${esc(ai)}</span>
        <span class="row__time">${clock(e.at)}</span>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có sự kiện nào.</p>';
}


/* Định dạng số kiểu Việt Nam — màn Kho và Chi phí dùng chung. */
const num = (n) => Number(n || 0).toLocaleString("vi-VN");


/* ---------------- chi phí và hiệu năng ---------------- */

// Thay cho Langfuse. Mọi số này đã nằm sẵn trong bảng messages từ ngày đầu.
// Dựng từ dữ liệu của chính mình thì không phải cài thêm hệ thống nào, và
// không có container nào chạy nền mà không ai dùng.
const vnd0 = (n) => Math.round(Number(n || 0)).toLocaleString("vi-VN") + "đ";

async function loadCost() {
  const c = await api("/cost");
  const t = c.tong;
  const maxNgay = Math.max(1e-9, ...c.theo_ngay.map((d) => d.chi_phi));

  $("#costCards").innerHTML =
      cell("Chi phí 7 ngày", vnd0(t.chi_phi_vnd), "", 1, "spend")
    + cell("Mỗi tin nhắn", usd(t.trung_binh_moi_tin), "", null, "spend")
    + cell("Tin agent đã gửi", num(t.so_tin), "", null, "auto")
    + cell("Token vào", num(t.token_vao), "", null, "auto")
    + cell("Đọc từ cache", t.ty_le_cache, "%", Math.min(1, t.ty_le_cache / 100), "auto");

  $("#costDays").innerHTML = c.theo_ngay.length ? c.theo_ngay.map((d) => `
    <div class="row">
      <span class="row__flag row__flag--spend" style="width:3px"></span>
      <span class="row__body">
        <span class="row__title">${esc(d.ngay)}
          <span class="tag tag--plain">${d.so_tin} tin</span></span>
        <span class="row__sub">${num(d.token_vao)} vào · ${num(d.token_ra)} ra · ${num(d.token_cache)} cache</span>
        <span class="readout__bar" style="margin-top:5px"><span class="readout__fill readout__fill--spend"
          style="width:${Math.max(2, d.chi_phi / maxNgay * 100)}%"></span></span>
      </span>
      <span class="row__side"><span class="row__num">${vnd0(d.chi_phi * 25000)}</span>
        <span class="row__time">${usd(d.chi_phi)}</span></span>
    </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';

  $("#costModels").innerHTML = c.theo_model.length ? c.theo_model.map((m) => `
    <div class="row">
      <span class="row__flag row__flag--auto" style="width:3px"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.model)}
          <span class="tag tag--plain">${m.so_tin} tin</span></span>
        <span class="row__sub">độ trễ trung bình ${(m.tre_tb / 1000).toFixed(1)}s</span>
      </span>
      <span class="row__side"><span class="row__num">${usd(m.chi_phi)}</span></span>
    </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';

  $("#costTop").innerHTML = c.hoi_thoai_dat_nhat.length
    ? c.hoi_thoai_dat_nhat.map((h) => `
      <div class="row">
        <span class="row__flag row__flag--spend"></span>
        <span class="row__body">
          <span class="row__title">${esc(h.customer_name || "Khách")} ${srcBadge(h.channel)}</span>
          <span class="row__sub">${h.msg_count} tin</span>
        </span>
        <span class="row__side"><span class="row__num">${usd(h.chi_phi)}</span>
          <span class="row__time">${vnd0(h.chi_phi * 25000)}</span></span>
      </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';
}

