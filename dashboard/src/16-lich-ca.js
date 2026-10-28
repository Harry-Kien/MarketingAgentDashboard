/* ---------------- Lịch ca trực ---------------- */
/* Ai đang trong ca là câu hỏi của MÁY CHỦ (hàm SQL dang_trong_ca) — ở đây
 * chỉ hiện. Tính lại bằng JS là hai bản sự thật, và sớm muộn màn hình nói
 * "đang trong ca" trong khi bộ định tuyến bỏ qua người đó. */

const THU = ["", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];

function _tomTatCa(ca) {
  if (!ca.length) return "chưa xếp ca — luôn được giao hội thoại";
  const theo = {};
  ca.forEach((c) => { (theo[c.thu] = theo[c.thu] || []).push(`${c.bat_dau}–${c.ket_thuc}`); });
  return Object.keys(theo).map((t) => `${THU[t]} ${theo[t].join(", ")}`).join(" · ");
}

async function loadCaCuaToi() {
  const o = $("#caCuaToi");
  if (!o) return;
  let r;
  try { r = await api("/lich-ca/cua-toi"); } catch { o.hidden = true; return; }
  // Chưa xếp ca và không nghỉ: luôn trực, không có gì để nói.
  if (!r.ca.length && !r.nghi.length) { o.hidden = true; return; }
  o.hidden = false;
  o.classList.toggle("is-ngoai", !r.trong_ca);
  o.textContent = (r.trong_ca ? "Bạn đang trong ca. "
    : "Bạn đang NGOÀI ca — bộ định tuyến không giao hội thoại mới cho bạn lúc này. ")
    + "Lịch: " + _tomTatCa(r.ca)
    + (r.nghi.length ? ` · nghỉ từ ${new Date(r.nghi[0].tu_luc).toLocaleString("vi-VN")}` : "");
}

async function loadLichCa() {
  const pn = $("#lcPanel");
  if (!pn) return;
  const doc = state.toiQuyen && state.toiQuyen.has("dinh_tuyen.doc");
  pn.hidden = !doc;
  if (!doc) return;
  const sua = state.toiQuyen.has("dinh_tuyen.sua");
  let r;
  try { r = await api("/lich-ca"); } catch (e) { toast(e.message, true); return; }
  state.lichCa = r;
  $("#lcCanhBao").innerHTML = r.canh_bao.map((c) => `
    <div class="row"><span class="row__flag row__flag--halt"></span>
      <span class="row__body"><span class="row__title">${esc(c.ghi)}</span>
        <span class="row__sub">Xếp thêm người vào ca, hoặc tạm tắt luật định tuyến của đội ở trang Cấu hình.</span></span>
    </div>`).join("");
  $("#lcNguoi").innerHTML = r.nguoi.length ? r.nguoi.map((n) => {
    const tt = n.dang_nghi ? "đang nghỉ" : !n.ca.length ? "luôn trực" : n.trong_ca ? "đang trong ca" : "ngoài ca";
    const co = n.dang_nghi || (n.ca.length && !n.trong_ca) ? "row__flag--plain" : "row__flag--auto";
    return `<div class="row">
      <span class="row__flag ${co}"></span>
      <span class="row__body"><span class="row__title">${esc(n.ten)} <em>· ${esc(tt)}</em></span>
        <span class="row__sub">${esc(_tomTatCa(n.ca))}</span></span>
      ${sua ? `<span class="row__side">
        <button type="button" class="btn btn--sm" data-lc-ca="${esc(n.id)}">Xếp ca</button>
        <button type="button" class="btn btn--sm" data-lc-nghi="${esc(n.id)}">Thêm nghỉ</button>
      </span>` : ""}
    </div>`;
  }).join("") : '<p class="empty">Chưa có nhân viên.</p>';
  const ten = Object.fromEntries(r.nguoi.map((n) => [n.id, n.ten]));
  $("#lcNghi").innerHTML = r.nghi.length ? r.nghi.map((n) => `
    <div class="row"><span class="row__flag row__flag--plain"></span>
      <span class="row__body"><span class="row__title">${esc(ten[n.nguoi_dung_id] || "?")}</span>
        <span class="row__sub">${esc(new Date(n.tu_luc).toLocaleString("vi-VN"))} → ${
          esc(new Date(n.den_luc).toLocaleString("vi-VN"))}${n.ly_do ? " · " + esc(n.ly_do) : ""}</span></span>
      ${sua ? `<span class="row__side"><button type="button" class="btn btn--sm btn--halt" data-lc-xoa-nghi="${esc(n.id)}">Xoá</button></span>` : ""}
    </div>`).join("") : '<p class="empty">Không ai nghỉ sắp tới.</p>';
}

/* "08:00-14:00, 18:00-22:00" → [{bat_dau, ket_thuc}]. Gõ sai thì báo, không
 * đoán: "8-14" có thể là 8:00–14:00, cũng có thể là gõ dở. */
function _docKhoang(chu, thu) {
  return chu.split(",").map((x) => x.trim()).filter(Boolean).map((x) => {
    const m = x.match(/^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$/);
    if (!m) throw new Error(`${THU[thu]}: «${x}» phải dạng 08:00-14:00`);
    return { thu, bat_dau: m[1], ket_thuc: m[2] };
  });
}

$("#lcNguoi")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-lc-ca], [data-lc-nghi]");
  if (!b) return;
  const n = (state.lichCa?.nguoi || []).find((x) => x.id === (b.dataset.lcCa || b.dataset.lcNghi));
  if (!n) return;
  try {
    if (b.dataset.lcCa) {
      const d = await hoiHop({
        tieu_de: `Xếp ca hằng tuần cho ${n.ten}`,
        phu: "Mỗi ngày một hoặc vài khoảng, cách nhau bằng dấu phẩy. Ca qua đêm ghi 22:00-06:00 ở ngày bắt đầu. Để trống cả tuần = luôn trực.",
        truong: THU.slice(1).map((t, i) => ({
          name: `t${i + 1}`, label: t, placeholder: "08:00-14:00, 18:00-22:00",
          value: n.ca.filter((c) => c.thu === i + 1).map((c) => `${c.bat_dau}-${c.ket_thuc}`).join(", "),
        })),
      });
      if (!d) return;
      const ca = [];
      for (let t = 1; t <= 7; t++) ca.push(..._docKhoang(d[`t${t}`] || "", t));
      await api(`/lich-ca/${n.id}`, { method: "PUT", body: JSON.stringify({ ca }) });
      toast(ca.length ? `Đã xếp ${ca.length} ca cho ${n.ten}.` : `${n.ten} về chế độ luôn trực.`);
    } else {
      const d = await hoiHop({
        tieu_de: `Thêm lịch nghỉ cho ${n.ten}`,
        phu: "Trong lúc nghỉ, bộ định tuyến không giao hội thoại mới cho người này. Giờ Việt Nam.",
        truong: [
          { name: "tu_luc", label: "Từ", type: "datetime-local", required: true },
          { name: "den_luc", label: "Đến", type: "datetime-local", required: true },
          { name: "ly_do", label: "Lý do", maxlength: 200, placeholder: "nghỉ phép" },
        ],
      });
      if (!d) return;
      // Ghi múi giờ TƯỜNG MINH: máy chủ từ chối giờ không múi giờ thay vì đoán.
      const vn = (v) => (v.length === 16 ? v + ":00" : v) + "+07:00";
      await api("/lich-ca/nghi", { method: "POST", body: JSON.stringify({
        nguoi_dung_id: n.id, tu_luc: vn(d.tu_luc), den_luc: vn(d.den_luc), ly_do: d.ly_do || "" }) });
      toast("Đã thêm lịch nghỉ.");
    }
    loadLichCa();
  } catch (e) { toast(e.message, true); }
});

$("#lcNghi")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-lc-xoa-nghi]");
  if (!b) return;
  try {
    await api(`/lich-ca/nghi/${b.dataset.lcXoaNghi}`, { method: "DELETE" });
    toast("Đã xoá lịch nghỉ.");
    loadLichCa();
  } catch (e) { toast(e.message, true); }
});
