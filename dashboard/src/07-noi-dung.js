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
 *            placeholder, hint, min, max, step, maxlength, minlength,
 *            options, rows }],
 *            nut, nguy_hiem,
 *            // --- hộp XÁC NHẬN (thêm 25.11.2026, UX-12-04 / UX-13-05) ---
 *            anh_huong,     // [chuỗi] — "Điều sẽ xảy ra", liệt kê từng dòng
 *            canh_bao,      // chuỗi | { tieu_de, muc: [chuỗi] } — khung đỏ nổi bật
 *            go_xac_nhan,   // chuỗi phải GÕ LẠI đúng mới bấm được nút chính
 *            bi_mat,        // chuỗi hiện MỘT lần (mật khẩu tạm) kèm nút Chép
 *            nut_huy,       // chữ nút thôi (mặc định "← Quay lại")
 *            an_huy })      // không có lối thôi (hộp chỉ để đọc bí mật)
 *
 * Mọi tham số mới đều tuỳ chọn: lời gọi cũ (30+ chỗ) giữ đúng hành vi cũ.
 *
 * VÌ SAO CÓ "ĐIỀU SẼ XẢY RA" THAY CHO "BẠN CÓ CHẮC KHÔNG": câu hỏi có/không
 * không mang thông tin, người ta bấm OK theo phản xạ. "3 người mất các quyền
 * này ngay" thì họ dừng lại. Gõ lại tên chỉ dành cho việc rất khó đảo
 * ngược — dùng ở mọi nơi là thành nghi thức gõ cho xong.
 *
 * Chuỗi nào cũng qua esc(): nội dung cảnh báo hay mang tên người, tên vai
 * trò — thứ người dùng tự đặt.
 */
let hoiDangMo = null;

function hoiVeKhoi({ anh_huong, canh_bao, bi_mat }) {
  const ds = (xs) => `<ul class="cong__ds">${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  let h = "";
  if (canh_bao) {
    const cb = typeof canh_bao === "string" ? { tieu_de: canh_bao } : canh_bao;
    h += `<div class="cong__canh-bao" role="alert"><b>${esc(cb.tieu_de || "")}</b>${
      (cb.muc || []).length ? ds(cb.muc) : ""}</div>`;
  }
  if ((anh_huong || []).length) {
    h += `<div class="cong__anh-huong"><span>Điều sẽ xảy ra</span>${ds(anh_huong)}</div>`;
  }
  if (bi_mat) {
    h += `<div class="cong__bi-mat"><code>${esc(bi_mat)}</code>
      <button type="button" class="btn btn--sm btn--ghost" data-hoi-chep>Chép</button></div>`;
  }
  return h;
}

function hoiHop({ tieu_de, phu = "", truong = [], nut = "Lưu", nguy_hiem = false,
                  anh_huong = null, canh_bao = null, go_xac_nhan = "", bi_mat = "",
                  nut_huy = "← Quay lại", an_huy = false, modal_kho = false, onRender = null }) {
  if (hoiDangMo) hoiDong(null);           // hộp mới thay hộp cũ, không chồng
  const form = $("#hoiform");
  if (form && typeof form._hoiCleanup === "function") {
    form._hoiCleanup();
    form._hoiCleanup = null;
  }
  $("#hoiTen").textContent = tieu_de;
  $("#hoiPhu").textContent = phu;
  $("#hoiPhu").hidden = !phu;
  $("#hoiLoi").textContent = "";
  const khoi = $("#hoiKhoi");
  if (khoi) {
    khoi.innerHTML = hoiVeKhoi({ anh_huong, canh_bao, bi_mat });
    khoi.hidden = !khoi.innerHTML;
  }
  const cacO = [...truong];
  if (go_xac_nhan) {
    cacO.push({ name: "_go_xac_nhan", label: `Gõ “${go_xac_nhan}” để xác nhận`,
             required: true, placeholder: go_xac_nhan });
  }
  $("#hoiTruong").innerHTML = cacO.map((t) => {
    const chung = `name="${esc(t.name)}"${t.required ? " required" : ""}`
      + (t.placeholder ? ` placeholder="${esc(t.placeholder)}"` : "")
      + (t.maxlength ? ` maxlength="${t.maxlength}"` : "")
      + (t.minlength ? ` minlength="${t.minlength}"` : "");
    let o;
    if (t.type === "textarea") {
      o = `<textarea ${chung} rows="${t.rows || 3}">${esc(t.value ?? "")}</textarea>`;
    } else if (t.type === "select") {
      o = `<select ${chung}>${(t.options || []).map((c) =>
        `<option value="${esc(c.value)}"${String(c.value) === String(t.value ?? "") ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select>`;
    } else {
      o = `<input type="${esc(t.type || "text")}" ${chung} value="${esc(t.value ?? "")}"`
        + (t.min != null ? ` min="${t.min}"` : "") + (t.max != null ? ` max="${t.max}"` : "")
        + (t.step != null ? ` step="${t.step}"` : "")
        + ` autocomplete="${t.type === "password" ? "new-password" : "off"}">`;
    }
    return `<label class="field"${t.hidden ? " hidden" : ""}><span>${esc(t.label)}${
      t.hint ? ` <em class="hint">${esc(t.hint)}</em>` : ""}</span>${o}</label>`;
  }).join("");
  const nutGui = $("#hoiNut");
  nutGui.textContent = nut;
  nutGui.classList.toggle("btn--halt", nguy_hiem);
  nutGui.classList.toggle("btn--primary", !nguy_hiem);
  // Nút chính KHOÁ tới khi gõ đúng — khoá ở đây chứ không chỉ kiểm lúc gửi:
  // nút trông bấm được mà bấm không ăn là nút dạy người ta bấm nhiều lần.
  nutGui.disabled = !!go_xac_nhan;
  $("#hoiform").dataset.goXacNhan = go_xac_nhan || "";
  $("#hoiform").classList.toggle("is-nguy", !!nguy_hiem);
  $("#hoiform").classList.toggle("is-modal-kho", !!modal_kho);
  const dongBtn = $("#hoiDongBtn");
  if (dongBtn) dongBtn.hidden = !modal_kho;
  const huyBtn = $("#hoiHuyBtn");
  if (huyBtn) huyBtn.hidden = !modal_kho;
  const huy = $("#hoiHuy");
  if (huy) { huy.textContent = nut_huy; huy.closest(".cong__note").hidden = !!an_huy || !!modal_kho; }
  if (typeof onRender === "function" && form) {
    const cleanup = onRender(form, { khoi, truongBox: $("#hoiTruong"), nutGui, loiEl: $("#hoiLoi") });
    if (typeof cleanup === "function") form._hoiCleanup = cleanup;
  }
  $("#congHoi").classList.remove("is-off");
  const dau = $("#hoiTruong").querySelector("input:not([hidden]), textarea, select") || nutGui;
  if (dau) setTimeout(() => dau.focus(), 0);
  return new Promise((resolve) => { hoiDangMo = resolve; });
}

function hoiDong(gia_tri) {
  const form = $("#hoiform");
  if (form && typeof form._hoiCleanup === "function") {
    form._hoiCleanup();
    form._hoiCleanup = null;
  }
  $("#congHoi").classList.add("is-off");
  // Bí mật (mật khẩu tạm) không được nằm lại trong DOM sau khi đóng hộp.
  if ($("#hoiKhoi")) $("#hoiKhoi").innerHTML = "";
  $("#hoiNut").disabled = false;
  const tra = hoiDangMo;
  hoiDangMo = null;
  if (tra) tra(gia_tri);
}

$("#hoiform")?.addEventListener("input", (e) => {
  const can = e.currentTarget.dataset.goXacNhan;
  if (can && e.target.name === "_go_xac_nhan") {
    $("#hoiNut").disabled = e.target.value.trim() !== can;
  }
});
$("#hoiform")?.addEventListener("click", async (e) => {
  if (!e.target.closest("[data-hoi-chep]")) return;
  const ma = $("#hoiKhoi code");
  try {
    await navigator.clipboard.writeText(ma ? ma.textContent : "");
    toast("Đã chép.");
  } catch { toast("Trình duyệt không cho chép — bôi đen rồi chép tay.", true); }
});
$("#hoiform")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.currentTarget).entries());
  for (const k of Object.keys(d)) if (typeof d[k] === "string") d[k] = d[k].trim();
  const can = e.currentTarget.dataset.goXacNhan;
  if (can && d._go_xac_nhan !== can) {
    $("#hoiLoi").textContent = `Gõ đúng “${can}” để xác nhận.`;
    return;
  }
  delete d._go_xac_nhan;
  hoiDong(d);
});
$("#hoiHuy")?.addEventListener("click", (e) => { e.preventDefault(); hoiDong(null); });
$("#hoiDongBtn")?.addEventListener("click", () => hoiDong(null));
$("#hoiHuyBtn")?.addEventListener("click", () => hoiDong(null));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && hoiDangMo) hoiDong(null);
});

/* ---------------- nhật ký ---------------- */

/* Màn Nhật ký cũ (`loadEvents` gọi `/api/events`) đã được thay thế hoàn toàn
 * bằng mô-đun Nhật ký kiểm toán tại `27-nhat-ky.js` (`/api/nhat-ky`). */


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

