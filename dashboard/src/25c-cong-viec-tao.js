/* ================= CÔNG VIỆC — ngăn "Việc mới" (UX-14-03, UX-14-04) =================
 *
 * Tạo việc trong một NGĂN KÉO bên phải (điện thoại: toàn màn), không trong
 * hộp hỏi chung `hoiHop`. Hộp ấy là lớp phủ của màn đăng nhập: một cột hẹp
 * giữa hai vùng trắng lớn, không chỗ cho thẻ liên kết hay danh sách gợi ý —
 * đo được 1366px: ô nhập rộng 320px, hai bên trống hơn 500px mỗi bên.
 *
 * Ngăn nằm ở <body>, không trong màn Công việc: nút "+ Tạo việc" của hội
 * thoại mở nó ngay trên hội thoại, người trực không phải rời khách đang chat.
 *
 * Ba thứ trước đây phải gõ tay hoặc không thấy:
 *   · liên kết (hội thoại, khách, đơn) hiện thành THẺ, không phải câu phụ;
 *   · mã đơn có GỢI Ý theo khách (`/cong-viec/goi-y-don`, quyền `don.doc`,
 *     phạm vi kênh) — gõ tay vẫn được, máy chủ kiểm cùng luật phạm vi;
 *   · tạo từ hội thoại thì mô tả điền sẵn vài tin khách gần nhất NGUYÊN
 *     VĂN (`/cong-viec/ngu-canh-tao`, không gọi mô hình), sửa được trước khi lưu.
 */

const cvxTao = {
  nguCanh: {}, khach: null, hoiThoai: null, don: null, goiY: [], chonGoiY: -1,
  ganDay: null, viecMo: [], quayVe: null, hen: null, dangGui: false, moTaGoiY: "",
};

function cvxTaoKhung() {
  let o = $("#cvxTao");
  if (o) return o;
  o = document.createElement("div");
  o.id = "cvxTao";
  o.className = "cvx-tao";
  o.hidden = true;
  o.innerHTML = `<div class="cvx-tao__nen" data-cvx-tao-dong></div>
    <section class="cvx-tao__ngan" role="dialog" aria-modal="true" aria-labelledby="cvxTaoTen">
      <form class="cvx-tao__form" id="cvxTaoForm" novalidate></form>
    </section>`;
  document.body.append(o);
  cvxTaoBatSuKien(o);
  return o;
}

function cvxTaoDong() {
  const o = $("#cvxTao");
  if (!o || o.hidden) return;
  o.hidden = true;
  document.body.classList.remove("cvx-khoa-cuon");
  clearTimeout(cvxTao.hen);
  const ve = cvxTao.quayVe;
  cvxTao.quayVe = null;
  if (ve && document.contains(ve)) ve.focus({ preventScroll: true });
}

/* ---------------- vẽ ---------------- */

function cvxTaoVeLienKet() {
  const the = [];
  if (cvxTao.hoiThoai) {
    the.push(`<span class="cvx-the"><span class="cvx-the__loai">Hội thoại</span>${
      esc(cvxTao.hoiThoai.kenh || "đang mở")}</span>`);
  }
  if (cvxTao.khach) {
    the.push(`<span class="cvx-the"><span class="cvx-the__loai">Khách</span>${esc(cvxTao.khach.ten)}</span>`);
  }
  if (cvxTao.don) {
    const nhan = (typeof ORDER_LABEL !== "undefined" && ORDER_LABEL[cvxTao.don.trang_thai]) || "";
    the.push(`<span class="cvx-the cvx-the--don"><span class="cvx-the__loai">Đơn</span>${esc(cvxTao.don.ma_don)}${
      nhan ? ` · ${esc(nhan)}` : ""}<button type="button" class="cvx-the__bo" data-cvx-tao-bo-don
      aria-label="Bỏ gắn đơn ${esc(cvxTao.don.ma_don)}">✕</button></span>`);
  }
  const o = $("#cvxTaoLienKet");
  if (!o) return;
  o.innerHTML = the.length ? the.join("")
    : '<span class="cvx-muc__trong">Việc độc lập — chưa gắn hội thoại hay khách. Gắn đơn ở ô bên dưới nếu có.</span>';
}

function cvxTaoVeGanDay() {
  const o = $("#cvxTaoGanDay");
  if (!o) return;
  const ds = cvxTao.ganDay;
  if (ds === null || !cvxTao.khach) { o.innerHTML = ""; return; }
  o.innerHTML = ds.length
    ? `<span class="cvx-tao__nho">Đơn gần đây của khách:</span>${ds.map((d, i) =>
        `<button type="button" class="chip" data-cvx-tao-gan-day="${i}">${esc(d.ma_don)}${
          ORDER_LABEL && ORDER_LABEL[d.trang_thai] ? ` · ${esc(ORDER_LABEL[d.trang_thai])}` : ""}</button>`).join("")}`
    : '<span class="cvx-tao__nho">Khách này chưa có đơn nào.</span>';
}

function cvxTaoVeGoiY() {
  const ds = $("#cvxTaoGoiY");
  const o = $("#cvxTaoDon");
  if (!ds || !o) return;
  const mo = cvxTao.goiY.length > 0 && document.activeElement === o;
  ds.hidden = !mo;
  o.setAttribute("aria-expanded", String(mo));
  ds.innerHTML = cvxTao.goiY.map((d, i) => `<li role="option" id="cvxGoiY${i}" class="cvx-goi-y${
      i === cvxTao.chonGoiY ? " is-on" : ""}" data-cvx-tao-goi-y="${i}" aria-selected="${i === cvxTao.chonGoiY}">
      <b>${esc(d.ma_don)}</b><span>${esc((ORDER_LABEL && ORDER_LABEL[d.trang_thai]) || d.trang_thai)} · ${
        num(d.tong_tien)}đ · ${esc(d.khach_ten || "")} · ${esc(clock(d.tao_luc))}</span></li>`).join("");
  if (cvxTao.chonGoiY >= 0) o.setAttribute("aria-activedescendant", `cvxGoiY${cvxTao.chonGoiY}`);
  else o.removeAttribute("aria-activedescendant");
}

function cvxTaoVeViecMo() {
  const o = $("#cvxTaoViecMo");
  if (!o) return;
  const ds = cvxTao.viecMo || [];
  o.hidden = !ds.length;
  o.innerHTML = ds.length ? `<b>Hội thoại này đang có ${ds.length} việc chưa xong</b> — kiểm tra trước khi tạo trùng:
    ${ds.map((v) => `<button type="button" class="btn btn--sm btn--ghost" data-cvx-tao-mo-viec="${esc(v.id)}">${
      esc(v.tieu_de)} · ${esc(v.nhan_trang_thai)}</button>`).join("")}` : "";
}

function cvxTaoVe(nguoi) {
  const giao = cvxCo("cong_viec.giao");
  const xemDon = cvxCo("don.doc");
  const ten = cvxTao.nguCanh.ten_khach;
  const uuTien = ((cvx.dm && cvx.dm.uu_tien) || [{ ma: "thap", nhan: "Thấp" }, { ma: "thuong", nhan: "Thường" },
    { ma: "cao", nhan: "Cao" }, { ma: "gap", nhan: "Gấp" }]);
  const dau = [["", "Chưa phân công", "người điều phối được báo"], ["__toi", "Tôi làm", ""]]
    .concat(giao ? [["__tu_dong", "Tự động", "người đang trong ca, lâu nhất chưa được giao"]] : []);
  $("#cvxTaoForm").innerHTML = `
    <div class="cvx-tao__dau">
      <h2 class="cvx-tao__ten" id="cvxTaoTen">Việc mới${ten ? ` — ${esc(ten)}` : ""}</h2>
      <button type="button" class="btn btn--sm btn--ghost" data-cvx-tao-dong aria-label="Đóng">✕</button>
    </div>
    <div class="cvx-tao__than">
      <div class="cvx-tao__lk" id="cvxTaoLienKet" aria-label="Liên kết của việc"></div>
      <div class="cvx-tao__canh" id="cvxTaoViecMo" role="status" hidden></div>
      <label class="field"><span>Việc cần làm</span>
        <input name="tieu_de" required maxlength="200" minlength="3" autocomplete="off"
          placeholder="Gọi lại chị Hoa xác nhận đơn"></label>
      <label class="field"><span>Mô tả <em class="hint" id="cvxTaoMoTaGoiY"></em></span>
        <textarea name="mo_ta" rows="5" maxlength="5000"
          placeholder="${cvxTao.nguCanh.conversation_id ? "Đang lấy tin khách gần nhất…" : "Chi tiết cần biết để làm việc này"}"></textarea></label>
      <div class="cvx-tao__hai">
        <fieldset class="cvx-tao__ut"><legend>Mức ưu tiên</legend>
          ${uuTien.map((u) => `<label class="cvx-ut-chon"><input type="radio" name="uu_tien" value="${esc(u.ma)}"${
            u.ma === "thuong" ? " checked" : ""}><span>${esc(u.nhan)}</span></label>`).join("")}
        </fieldset>
        <label class="field"><span>Hạn <em class="hint">để trống nếu không có</em></span>
          <input type="date" name="han"></label>
      </div>
      <div class="field cvx-tao__don"><span id="cvxTaoDonNhan">Đơn liên quan <em class="hint">${
        xemDon ? (cvxTao.khach ? "gợi ý theo khách này" : "gõ từ 2 ký tự mã đơn") : "gõ đúng mã đơn — không có quyền xem danh sách đơn"}</em></span>
        <div class="cvx-tao__hop">
          <input id="cvxTaoDon" maxlength="60" autocomplete="off" placeholder="ĐH-…" aria-labelledby="cvxTaoDonNhan"
            ${xemDon ? 'role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="cvxTaoGoiY"' : ""}>
          <ul class="cvx-goi-y-ds" id="cvxTaoGoiY" role="listbox" hidden></ul>
        </div>
        <div class="cvx-tao__gan-day" id="cvxTaoGanDay"></div>
      </div>
      <fieldset class="cvx-tao__pc"><legend>Phân công</legend>
        ${cvxVeDsNguoi("phan_cong", giao ? nguoi : [], giao ? "" : "__toi", dau)}
      </fieldset>
    </div>
    <div class="cvx-tao__chan">
      <p class="cvx-tao__loi" id="cvxTaoLoi" role="alert"></p>
      <button type="button" class="btn btn--ghost" data-cvx-tao-dong>Hủy</button>
      <button type="submit" class="btn btn--primary" id="cvxTaoGui">Tạo việc</button>
    </div>`;
  cvxTaoVeLienKet();
  cvxTaoVeGanDay();
  cvxTaoVeViecMo();
}

/* ---------------- dữ liệu ---------------- */

async function cvxTaoNapNguCanh() {
  const cid = cvxTao.nguCanh.conversation_id;
  if (!cid) return;
  const o = $("#cvxTaoForm [name=mo_ta]");
  try {
    const d = await api(`/cong-viec/ngu-canh-tao?conversation_id=${encodeURIComponent(cid)}`);
    if ($("#cvxTao").hidden || cvxTao.nguCanh.conversation_id !== cid) return;
    cvxTao.hoiThoai = d.hoi_thoai;
    if (d.khach) cvxTao.khach = d.khach;
    cvxTao.viecMo = d.viec_mo || [];
    cvxTao.ganDay = d.don_gan_day;   // null = không có quyền xem đơn
    cvxTao.moTaGoiY = d.mo_ta_goi_y || "";
    /* Chỉ điền khi ô còn trống: người ta gõ nhanh hơn mạng thì không đè. */
    if (o && !o.value.trim() && cvxTao.moTaGoiY) {
      o.value = cvxTao.moTaGoiY;
      $("#cvxTaoMoTaGoiY").innerHTML = `trích nguyên văn tin khách — sửa lại cho gọn
        <button type="button" class="cvx-tao__bo-trich" data-cvx-tao-bo-trich>Bỏ trích dẫn</button>`;
    }
    if (o) o.placeholder = "Chi tiết cần biết để làm việc này";
    cvxTaoVeLienKet();
    cvxTaoVeGanDay();
    cvxTaoVeViecMo();
  } catch (e) {
    /* Không lấy được ngữ cảnh thì vẫn tạo được việc — nhưng nói ra, không
       để ô mô tả trống như thể khách chưa nhắn gì. */
    if (o) o.placeholder = "Không lấy được tin khách gần nhất — gõ mô tả tay.";
    console.warn("Không tải được ngữ cảnh tạo việc", e);
  }
}

async function cvxTaoTimDon(q) {
  if (!cvxCo("don.doc")) return;
  const tham = new URLSearchParams({ q, limit: "8" });
  if (cvxTao.khach) tham.set("contact_id", cvxTao.khach.id);
  try {
    const d = await api(`/cong-viec/goi-y-don?${tham}`);
    cvxTao.goiY = d.don || [];
  } catch (e) { cvxTao.goiY = []; console.warn("Không tải được gợi ý đơn", e); }
  cvxTao.chonGoiY = cvxTao.goiY.length ? 0 : -1;
  cvxTaoVeGoiY();
}

function cvxTaoChonDon(d) {
  if (!d) return;
  cvxTao.don = { id: d.id, ma_don: d.ma_don, trang_thai: d.trang_thai };
  cvxTao.goiY = [];
  const o = $("#cvxTaoDon");
  if (o) o.value = "";
  cvxTaoVeGoiY();
  cvxTaoVeLienKet();
}

/* ---------------- mở / gửi ---------------- */

/* Tạo việc — từ màn Công việc, hoặc từ một hội thoại (`ngu_canh` mang sẵn
 * hội thoại + khách). Phân công: tự nhận, chưa phân công, tự động, hay
 * một người cụ thể — hai lựa chọn sau chỉ hiện khi có `cong_viec.giao`. */
async function cvxTaoViec(ngu_canh = {}) {
  const o = cvxTaoKhung();
  cvxTao.nguCanh = ngu_canh;
  cvxTao.khach = ngu_canh.contact_id ? { id: ngu_canh.contact_id, ten: ngu_canh.ten_khach || "Khách" } : null;
  cvxTao.hoiThoai = ngu_canh.conversation_id ? { id: ngu_canh.conversation_id, kenh: "" } : null;
  cvxTao.don = null; cvxTao.goiY = []; cvxTao.chonGoiY = -1;
  cvxTao.ganDay = null; cvxTao.viecMo = []; cvxTao.moTaGoiY = ""; cvxTao.dangGui = false;
  cvxTao.quayVe = document.activeElement;
  let nguoi = [];
  if (cvxCo("cong_viec.giao")) {
    try { nguoi = await cvxNguoiNhan(null); }
    catch (e) { console.warn("Không tải được danh sách người nhận", e); }
  }
  cvxTaoVe(nguoi);
  o.hidden = false;
  document.body.classList.add("cvx-khoa-cuon");
  setTimeout(() => $("#cvxTaoForm [name=tieu_de]")?.focus(), 0);
  cvxTaoNapNguCanh();
}

async function cvxTaoGui() {
  if (cvxTao.dangGui) return;
  const f = $("#cvxTaoForm");
  const loi = $("#cvxTaoLoi");
  const r = Object.fromEntries(new FormData(f).entries());
  for (const k of Object.keys(r)) if (typeof r[k] === "string") r[k] = r[k].trim();
  if (!r.tieu_de || r.tieu_de.length < 3) {
    loi.textContent = "Ghi việc cần làm (ít nhất 3 ký tự).";
    f.querySelector("[name=tieu_de]").focus();
    return;
  }
  const than = { tieu_de: r.tieu_de, mo_ta: r.mo_ta || "", uu_tien: r.uu_tien || "thuong",
                 han: cvxHan(r.han) };
  const maGo = ($("#cvxTaoDon")?.value || "").trim();
  if (cvxTao.don) than.order_id = cvxTao.don.id;
  else if (maGo) than.ma_don = maGo;
  if (cvxTao.nguCanh.conversation_id) than.conversation_id = cvxTao.nguCanh.conversation_id;
  if (cvxTao.khach) than.contact_id = cvxTao.khach.id;
  if (r.phan_cong === "__toi") than.nguoi_nhan = state.toiId;
  else if (r.phan_cong === "__tu_dong") than.giao_tu_dong = true;
  else if (r.phan_cong) than.nguoi_nhan = r.phan_cong;
  const nut = $("#cvxTaoGui");
  cvxTao.dangGui = true;
  nut.disabled = true;
  nut.textContent = "Đang tạo…";
  loi.textContent = "";
  try {
    const kq = await api("/cong-viec", { method: "POST", body: JSON.stringify(than) });
    if (than.giao_tu_dong && !kq.nguoi_nhan) toast(`Đã tạo, nhưng chưa phân công được: ${kq.ly_do_khong_giao}`, true);
    else toast("Đã tạo việc.");
    cvxTaoDong();
    if (cvx.el && tabDangHien("cv-danh-sach")) { await cvxLamMoi(); await cvxTaiChiTiet(kq.id); }
    return kq.id;
  } catch (e) {
    /* Lỗi nằm NGAY trong ngăn, cạnh nút: toast biến mất sau vài giây và
       người ta không biết phải sửa ô nào. */
    loi.textContent = e.message;
  } finally {
    cvxTao.dangGui = false;
    nut.disabled = false;
    nut.textContent = "Tạo việc";
  }
}

/* ---------------- sự kiện ---------------- */

function cvxTaoBatSuKien(o) {
  o.addEventListener("submit", (e) => { e.preventDefault(); cvxTaoGui(); });
  o.addEventListener("click", (e) => {
    if (e.target.closest("[data-cvx-tao-dong]")) { cvxTaoDong(); return; }
    if (e.target.closest("[data-cvx-tao-bo-don]")) {
      cvxTao.don = null; cvxTaoVeLienKet(); $("#cvxTaoDon")?.focus(); return;
    }
    if (e.target.closest("[data-cvx-tao-bo-trich]")) {
      const m = $("#cvxTaoForm [name=mo_ta]");
      if (m && m.value === cvxTao.moTaGoiY) m.value = "";
      $("#cvxTaoMoTaGoiY").textContent = "";
      m?.focus();
      return;
    }
    const gy = e.target.closest("[data-cvx-tao-goi-y]");
    if (gy) { cvxTaoChonDon(cvxTao.goiY[Number(gy.dataset.cvxTaoGoiY)]); return; }
    const gd = e.target.closest("[data-cvx-tao-gan-day]");
    if (gd) { cvxTaoChonDon((cvxTao.ganDay || [])[Number(gd.dataset.cvxTaoGanDay)]); return; }
    const mv = e.target.closest("[data-cvx-tao-mo-viec]");
    if (mv) { cvxTaoDong(); window.moCongViec(mv.dataset.cvxTaoMoViec); }
  });
  o.addEventListener("change", (e) => {
    if (e.target.matches("[name=phan_cong]")) {
      $$(".cvx-tao__pc .cvx-ng", o).forEach((l) => l.classList.toggle("is-on", l.contains(e.target)));
    }
  });
  o.addEventListener("input", (e) => {
    if (e.target.id !== "cvxTaoDon" || !cvxCo("don.doc")) return;
    clearTimeout(cvxTao.hen);
    const q = e.target.value.trim();
    if (q.length < 2 && !cvxTao.khach) { cvxTao.goiY = []; cvxTaoVeGoiY(); return; }
    cvxTao.hen = setTimeout(() => cvxTaoTimDon(q), 250);
  });
  o.addEventListener("focusin", (e) => {
    if (e.target.id === "cvxTaoDon" && cvxCo("don.doc") && cvxTao.khach && !cvxTao.goiY.length) {
      cvxTaoTimDon(e.target.value.trim());
    }
  });
  o.addEventListener("focusout", (e) => {
    if (e.target.id !== "cvxTaoDon") return;
    /* Trễ một nhịp: bấm chuột vào một gợi ý làm ô mất focus TRƯỚC khi sự
       kiện click tới — ẩn ngay là gợi ý biến mất dưới ngón tay. */
    setTimeout(() => { if (document.activeElement !== e.target) cvxTaoVeGoiY(); }, 150);
  });
  o.addEventListener("keydown", (e) => {
    if (e.target.id !== "cvxTaoDon" || !cvxTao.goiY.length) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const n = cvxTao.goiY.length;
      cvxTao.chonGoiY = (cvxTao.chonGoiY + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      cvxTaoVeGoiY();
    } else if (e.key === "Enter" && cvxTao.chonGoiY >= 0) {
      e.preventDefault();
      cvxTaoChonDon(cvxTao.goiY[cvxTao.chonGoiY]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      cvxTao.goiY = [];
      cvxTaoVeGoiY();
    }
  });
}

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || hoiDangMo) return;
  const o = $("#cvxTao");
  if (o && !o.hidden) cvxTaoDong();
});
