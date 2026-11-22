/* ---------------- Nhật ký kiểm toán (phiếu việc mục 18) ----------------
 *
 * Cài đặt & Quản trị → Hệ thống & Nhật ký → tab "Nhật ký". Thay danh sách
 * 50 dòng thô (`/events`) bằng màn TRA CỨU: lọc theo thời gian, hội thoại,
 * loại tác nhân / người, nhóm hành động, trạng thái; phân trang; bảng chi
 * tiết có cấu trúc, và với việc của AI — cả LƯỢT xử lý (tin khách → tài
 * liệu → công cụ → lưới → trả lời).
 *
 * Mọi chữ hiện ở đây đã được máy chủ làm sạch (`lam_sach`): token, khoá,
 * số điện thoại, email, suy luận model không bao giờ tới trình duyệt.
 *
 * Ghi (đánh dấu sự cố, bước can thiệp, kết thúc, giải trình) cần quyền
 * `nhat_ky.su_co` và LUÔN là dòng mới — máy chủ chặn sửa/xoá nhật ký.
 *
 * Cuối tệp: mục "Nhật ký hội thoại" trong panel Chi tiết của MỘT hội thoại
 * (`veNhatKyHoiThoai`, gọi từ 19-trach-nhiem.js) cho nhân viên không có
 * quyền xem toàn bộ nhật ký.
 */

const NK_TONE = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "auto" };
const NK_TAG = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "plain" };

const nk = { loc: {}, conTro: [], trangNay: null, danhMuc: null, moId: null, xem: "su_kien", el: null };

function nkCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function nkGio(iso) { return iso ? (typeof gioTin === "function" ? gioTin(iso) : clock(iso)) : ""; }

function nkNgan(id) { return id ? String(id).slice(0, 8) : ""; }

function nkTacNhan(b) {
  const t = b.tac_nhan || {};
  if (t.loai === "nhan_vien") return t.ten ? `Nhân viên · ${t.ten}` : "Nhân viên";
  if (t.loai === "ai") return t.ten ? `AI · ${t.ten}` : "AI";
  return "Hệ thống";
}

/* Chuyển giá trị ô datetime-local (giờ máy người xem) sang ISO có múi giờ:
 * máy chủ hiểu giờ không múi là giờ Việt Nam, còn người xem có thể ở nơi khác. */
function nkIso(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? "" : d.toISOString();
}

function nkChuoiLoc(them = {}) {
  const p = new URLSearchParams();
  const l = { ...nk.loc, ...them };
  for (const [k, v] of Object.entries(l)) if (v !== "" && v != null) p.set(k, v);
  return p.toString();
}

function nkVeKhung(el) {
  const dm = nk.danhMuc || { nhom: [], loai_tac_nhan: [], trang_thai: [], nguoi: [] };
  const chon = (name, nhan, ds, giaTri) => `<label class="field"><span>${nhan}</span>
    <select name="${name}"><option value="">Tất cả</option>${ds.map((x) =>
      `<option value="${esc(x.ma ?? x.id)}"${String(giaTri || "") === String(x.ma ?? x.id) ? " selected" : ""}>${
        esc(x.nhan ?? x.ten)}</option>`).join("")}</select></label>`;
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Nhật ký kiểm toán
      <span class="panel__note">AI, nhân viên và hệ thống · chỉ thêm, không sửa được</span></h2>
    <div class="tabs" role="tablist">
      <button type="button" class="tabbar__nut" data-nk-xem="su_kien" aria-selected="${nk.xem === "su_kien"}">Sự kiện</button>
      <button type="button" class="tabbar__nut" data-nk-xem="de_xuat" aria-selected="${nk.xem === "de_xuat"}">Đề xuất của AI &amp; phê duyệt</button>
    </div>
    <form class="form" data-nk-loc ${nk.xem === "su_kien" ? "" : "hidden"}>
      <div class="form__row">
        <label class="field"><span>Từ</span><input type="datetime-local" name="tu" value="${esc(nk.loc.tu_o || "")}"></label>
        <label class="field"><span>Đến</span><input type="datetime-local" name="den" value="${esc(nk.loc.den_o || "")}"></label>
        ${chon("loai_tac_nhan", "Tác nhân", dm.loai_tac_nhan, nk.loc.loai_tac_nhan)}
        ${chon("nguoi_id", "Người", dm.nguoi, nk.loc.nguoi_id)}
        ${chon("nhom", "Loại hành động", dm.nhom, nk.loc.nhom)}
        ${chon("trang_thai", "Trạng thái", dm.trang_thai, nk.loc.trang_thai)}
        <label class="field"><span>Hội thoại (mã)</span><input name="hoi_thoai_id" value="${esc(nk.loc.hoi_thoai_id || "")}" placeholder="dán mã hội thoại" autocomplete="off"></label>
        <label class="field"><span>Lượt AI (mã)</span><input name="luot_id" value="${esc(nk.loc.luot_id || "")}" autocomplete="off"></label>
      </div>
      <div class="rowbtns">
        <button type="submit" class="btn btn--sm btn--primary">Lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-xoa-loc>Xoá lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-csv>Xuất CSV</button>
      </div>
    </form>
    <div class="rows" data-nk-ds><p class="empty">Đang tải…</p></div>
    <div class="rowbtns" data-nk-trang></div>
  </section>
  <section class="panel" data-nk-chi-tiet hidden></section>`;
}

function nkDong(b) {
  const tt = b.trang_thai || {};
  return `<div class="row${nk.moId === b.id ? " is-mo" : ""}" data-nk-dong="${b.id}" role="button" tabindex="0">
    <span class="row__flag row__flag--${NK_TONE[tt.ma] || "plain"}"></span>
    <span class="row__body">
      <span class="row__title">${esc(b.hanh_dong)}
        <span class="tag tag--plain">${esc((b.nhom || {}).nhan || "")}</span>
        <span class="tag tag--${NK_TAG[tt.ma] || "plain"}">${esc(tt.nhan || "")}</span></span>
      <span class="row__sub">${esc(nkTacNhan(b))}${b.che_do_ai ? " · chế độ " + esc(b.che_do_ai) : ""}${
        b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span>
    </span>
    <span class="row__side">
      ${b.hoi_thoai_id ? `<button type="button" class="row__nut" data-nk-loc-ht="${esc(b.hoi_thoai_id)}" title="Lọc theo hội thoại này">HT ${esc(nkNgan(b.hoi_thoai_id))}</button>` : ""}
      <span class="row__time">${esc(nkGio(b.luc))}</span>
    </span>
  </div>`;
}

async function nkTai() {
  const el = nk.el;
  if (!el) return;
  const ds = el.querySelector("[data-nk-ds]");
  const trang = el.querySelector("[data-nk-trang]");
  try {
    let kq;
    if (nk.xem === "de_xuat") {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky/de-xuat?" + new URLSearchParams(truoc ? { truoc } : {}).toString());
      ds.innerHTML = kq.items.length ? kq.items.map(nkDongDeXuat).join("")
        : '<p class="empty">Chưa có đề xuất nào của AI.</p>';
    } else {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky?" + nkChuoiLoc(truoc ? { truoc } : {}));
      ds.innerHTML = kq.items.length ? kq.items.map(nkDong).join("")
        : '<p class="empty">Không có sự kiện nào khớp bộ lọc.</p>';
    }
    nk.trangNay = kq;
    trang.innerHTML = `${nk.conTro.length ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-truoc>← Mới hơn</button>' : ""}
      <span class="hint">Trang ${nk.conTro.length + 1}</span>
      ${kq.next_cursor ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-sau>Cũ hơn →</button>' : ""}`;
  } catch (e) {
    ds.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
    trang.innerHTML = "";
  }
}

function nkDongDeXuat(d) {
  const tt = d.trang_thai || {};
  const tone = tt.ma === "cho_duyet" ? "assist" : tt.ma === "tu_choi" ? "halt" : "auto";
  const quyet = d.nguoi_quyet ? `duyệt bởi ${d.nguoi_quyet}${d.luc_quyet ? " lúc " + nkGio(d.luc_quyet) : ""}` : "";
  const sua = d.nguoi_sua ? `sửa bởi ${d.nguoi_sua}` : "";
  return `<div class="row">
    <span class="row__flag row__flag--${tone}"></span>
    <span class="row__body">
      <span class="row__title">${esc((d.de_xuat_boi || {}).ten || "AI")} đề xuất trả lời
        <span class="tag tag--${tone === "auto" ? "plain" : tone}">${esc(tt.nhan || "")}</span></span>
      <span class="row__sub">${esc(d.tom_tat || "")}</span>
      <span class="row__sub">${esc([sua, quyet].filter(Boolean).join(" · ") || "chưa ai quyết")}</span>
    </span>
    <span class="row__side">
      ${d.luot_id && nkCo("nhat_ky.doc") ? `<button type="button" class="row__nut" data-nk-mo-luot="${esc(d.luot_id)}">Xem lượt AI</button>` : ""}
      <span class="row__time">${esc(nkGio(d.luc_de_xuat))}</span>
    </span>
  </div>`;
}

function nkCT(tieu, chi) {
  return typeof dongCT === "function" ? dongCT(esc(tieu), chi)
    : `<div class="ctt__dong"><b>${esc(tieu)}</b><span>${chi}</span></div>`;
}

/* Một lượt AI theo thứ tự: tin khách → các bước → câu trả lời (kèm căn cứ). */
function nkVeLuot(l) {
  if (!l) return "";
  const buoc = (l.buoc || []).map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc((b.trang_thai || {}).nhan || "")}${
        b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span></div>`).join("");
  const traLoi = (l.tra_loi || []).map((t) => {
    const dv = t.dau_vet || {};
    const tl = (dv.tri_thuc || []).map((x) => `<li><b>${esc(x.title || "(không tên)")}</b>${
      x.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(x.version)}</span>` : ""}${
      x.trich ? `<blockquote class="ctt__trich">${esc(x.trich)}</blockquote>` : ""}</li>`).join("");
    const cc = (dv.cong_cu || []).map((c) => `<li><b>${esc(c.ten)}</b>
      <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></li>`).join("");
    return `<div class="lichsu__dong">
      <b>Câu trả lời · ${esc(t.trang_thai || "")}</b>
      <span class="msg__meta">${esc(nkGio(t.luc))}${t.sua_boi ? " · sửa bởi " + esc(t.sua_boi) : ""}${
        t.duyet_boi ? " · duyệt bởi " + esc(t.duyet_boi) : ""}</span>
      <p>${esc(t.noi_dung || "")}</p>
      ${dv.luoi ? nkCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma || "")) : ""}
      ${dv.chuyen_nguoi && dv.chuyen_nguoi.co ? nkCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : ""}
      <h4 class="ctt__dau">Tài liệu đã dùng (ảnh chụp lúc xử lý)</h4>
      ${tl ? `<ul class="ctt__ds">${tl}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
      <h4 class="ctt__dau">Dữ liệu công cụ trả về (ảnh chụp lúc xử lý)</h4>
      ${cc ? `<ul class="ctt__ds">${cc}</ul>` : '<p class="hint">Không gọi công cụ nào.</p>'}
    </div>`;
  }).join("");
  return `<section class="lichsu" aria-label="Lượt AI">
    <h4 class="ctt__dau">Lượt AI ${esc(nkNgan(l.luot_id))}</h4>
    ${l.tin_khach ? `<div class="lichsu__dong"><b>Tin khách</b>
      <span class="msg__meta">${esc(nkGio(l.tin_khach.luc))}</span>
      <p>${esc(l.tin_khach.noi_dung || "(không đọc được nội dung)")}</p></div>` : ""}
    ${buoc || '<p class="hint">Lượt này không để lại dòng nhật ký nào.</p>'}
    ${traLoi}
  </section>`;
}

function nkVeChiTiet(b) {
  const tt = b.trang_thai || {};
  const ghi = nkCo("nhat_ky.su_co");
  const laSuCo = b.kind === "su_co.danh_dau";
  const nut = [
    ghi && !b.kind.startsWith("su_co.") && b.kind !== "nhat_ky.giai_trinh" && tt.ma !== "su_co"
      ? `<button type="button" class="btn btn--sm btn--halt" data-nk-su-co="${b.id}">Đánh dấu sự cố</button>` : "",
    ghi && laSuCo ? `<button type="button" class="btn btn--sm" data-nk-buoc="${b.id}">Thêm bước can thiệp</button>
      <button type="button" class="btn btn--sm" data-nk-ket-thuc="${b.id}">Kết thúc sự cố</button>` : "",
    ghi ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-giai-trinh="${b.id}">Giải trình / đính chính</button>` : "",
    b.su_kien_goc ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-mo="${b.su_kien_goc}">Mở dòng gốc #${esc(b.su_kien_goc)}</button>` : "",
    `<button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button>`,
  ].join("");
  const lien = (b.lien_quan || []).map((x) => `<div class="lichsu__dong">
      <b>${esc(x.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(x.luc))} · ${esc(nkTacNhan(x))}</span>
      ${x.chi_tiet && x.chi_tiet.ghi_chu ? `<p>${esc(x.chi_tiet.ghi_chu)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.ket_qua ? `<p><b>Kết quả:</b> ${esc(x.chi_tiet.ket_qua)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.nhan ? `<p>${esc(x.chi_tiet.nhan)}</p>` : ""}
    </div>`).join("");
  return `<h2 class="panel__head">#${b.id} · ${esc(b.hanh_dong)}
      <span class="panel__note">${esc(b.kind)}</span></h2>
    <div class="ctt">
      ${nkCT("Thời gian", esc(new Date(b.luc).toLocaleString("vi-VN")))}
      ${nkCT("Tác nhân", esc(nkTacNhan(b)))}
      ${nkCT("Loại hành động", esc((b.nhom || {}).nhan || ""))}
      ${nkCT("Hội thoại", b.hoi_thoai_id ? `<span class="mono">${esc(b.hoi_thoai_id)}</span>` : "—")}
      ${nkCT("Chế độ AI", esc(b.che_do_ai || "—"))}
      ${nkCT("Mức uỷ quyền", esc(b.muc_uy_quyen || "chưa áp dụng"))}
      ${nkCT("Trạng thái", esc(tt.nhan || ""))}
      ${nkCT("Kết quả", esc(b.ket_qua || "—"))}
      ${b.luot_id ? nkCT("Lượt AI", `<span class="mono">${esc(b.luot_id)}</span>`) : ""}
      <details class="ctt__kt"><summary>Dữ liệu ghi nhận (đã che thông tin nhạy cảm)</summary>
        <pre class="pre">${esc(JSON.stringify(b.chi_tiet || {}, null, 2))}</pre></details>
      ${lien ? `<h4 class="ctt__dau">Sự cố &amp; giải trình</h4><section class="lichsu">${lien}</section>` : ""}
      ${b.luot ? nkVeLuot(b.luot) : ""}
    </div>
    <div class="rowbtns">${nut}</div>`;
}

async function nkMo(id) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  nk.moId = Number(id);
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeChiTiet(await api(`/nhat-ky/${id}`));
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
  khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function nkMoLuot(luotId) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeLuot(await api(`/nhat-ky/luot/${encodeURIComponent(luotId)}`))
      + '<div class="rowbtns"><button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button></div>';
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
}

/* Ghi một dòng mới (sự cố, bước, kết thúc, giải trình) rồi mở lại dòng gốc. */
async function nkGhi(duong, hop, moLai) {
  const d = await hoiHop(hop);
  if (!d) return;
  try {
    await api(duong, { method: "POST", body: JSON.stringify(d) });
    toast("Đã ghi vào nhật ký.");
    await nkTai();
    if (moLai) await nkMo(moLai);
  } catch (e) { toast(e.message, true); }
}

async function nkXuLyClick(e) {
  const tim = (k) => e.target.closest(`[${k}]`);
  let o;
  if ((o = tim("data-nk-xem"))) {
    nk.xem = o.dataset.nkXem; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-loc-ht"))) {
    e.stopPropagation();
    nk.loc = { hoi_thoai_id: o.dataset.nkLocHt }; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-mo-luot"))) {
    await nkMoLuot(o.dataset.nkMoLuot);
  } else if ((o = tim("data-nk-mo"))) {
    await nkMo(o.dataset.nkMo);
  } else if ((o = tim("data-nk-dong"))) {
    await nkMo(o.dataset.nkDong);
  } else if (tim("data-nk-dong-ct")) {
    nk.moId = null;
    const k = nk.el.querySelector("[data-nk-chi-tiet]"); k.hidden = true; k.innerHTML = "";
  } else if (tim("data-nk-sau")) {
    if (nk.trangNay && nk.trangNay.next_cursor) { nk.conTro.push(nk.trangNay.next_cursor); await nkTai(); }
  } else if (tim("data-nk-truoc")) {
    nk.conTro.pop(); await nkTai();
  } else if (tim("data-nk-xoa-loc")) {
    nk.loc = {}; nk.conTro = []; nkVeKhung(nk.el); await nkTai();
  } else if (tim("data-nk-csv")) {
    /* CSV theo đúng bộ lọc đang xem (trừ lượt AI — xuất một lượt thì
       xem ngay trên màn này là đủ). `*_o` là giá trị ô nhập, không phải lọc. */
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(nk.loc)) {
      if (v && k !== "luot_id" && !k.endsWith("_o")) p.set(k, v);
    }
    window.open("/api/nhat-ky/xuat.csv?" + p.toString(), "_blank");
  } else if ((o = tim("data-nk-su-co"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkSuCo}/su-co`, {
      tieu_de: "Đánh dấu sự cố", nut: "Đánh dấu", nguy_hiem: true,
      phu: "Ghi thành một dòng MỚI trỏ về hành động này; dòng gốc giữ nguyên.",
      truong: [{ name: "ghi_chu", label: "Vì sao đây là sự cố", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkSuCo);
  } else if ((o = tim("data-nk-buoc"))) {
    const dm = (nk.danhMuc && nk.danhMuc.buoc_can_thiep) || [];
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkBuoc}/buoc`, {
      tieu_de: "Bước can thiệp", nut: "Ghi bước",
      truong: [
        { name: "loai", label: "Đã làm gì", type: "select", required: true,
          options: dm.map((x) => ({ value: x.ma, label: x.nhan })) },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkBuoc);
  } else if ((o = tim("data-nk-ket-thuc"))) {
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkKetThuc}/ket-thuc`, {
      tieu_de: "Kết thúc sự cố", nut: "Kết thúc",
      truong: [
        { name: "ket_qua", label: "Kết quả", required: true, maxlength: 500 },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkKetThuc);
  } else if ((o = tim("data-nk-giai-trinh"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkGiaiTrinh}/giai-trinh`, {
      tieu_de: "Giải trình / đính chính", nut: "Ghi",
      phu: "Nhật ký không sửa được. Lời giải trình là một dòng mới đi kèm dòng này.",
      truong: [{ name: "ghi_chu", label: "Nội dung", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkGiaiTrinh);
  }
}

window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["ht-nhat-ky"] = async (el) => {
  nk.el = el;
  if (!nkCo("nhat_ky.doc")) {
    el.innerHTML = '<section class="panel"><p class="empty">Cần quyền "Xem nhật ký kiểm toán" để xem mục này.</p></section>';
    return;
  }
  nkVeKhung(el);
  el.addEventListener("click", (e) => { nkXuLyClick(e); });
  el.addEventListener("keydown", (e) => {
    const d = e.target.closest("[data-nk-dong]");
    if (d && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); nkMo(d.dataset.nkDong); }
  });
  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-nk-loc]");
    if (!f) return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    nk.loc = {
      tu: nkIso(d.tu), den: nkIso(d.den), tu_o: d.tu, den_o: d.den,
      loai_tac_nhan: d.loai_tac_nhan, nguoi_id: d.nguoi_id, nhom: d.nhom,
      trang_thai: d.trang_thai, hoi_thoai_id: (d.hoi_thoai_id || "").trim(),
      luot_id: (d.luot_id || "").trim(),
    };
    nk.conTro = [];
    await nkTai();
  });
  /* Làm mới trang ĐẦU mỗi lần tab hiện lại — trang sau giữ nguyên, kẻo
   * người đang đọc trang 3 bị kéo về trang 1. */
  el.closest("[data-gan]")?.addEventListener("tab:hien", () => { if (!nk.conTro.length) nkTai(); });
  try {
    nk.danhMuc = await api("/nhat-ky/danh-muc");
    nkVeKhung(el);
  } catch (e) { toast(e.message, true); }
  await nkTai();
};

/* ---------------- Nhật ký của MỘT hội thoại ----------------
 * Trong panel "Chi tiết" của hội thoại. Chỉ cần `hoi_thoai.doc` và hội
 * thoại thuộc kênh của người xem (máy chủ chặn) — nhân viên trực thấy "AI
 * đã làm gì với khách mình đang giữ" mà không thấy nhật ký cả cửa hàng.
 * Tải khi BẤM, không tải theo vòng 6 giây. */
function veNhatKyHoiThoai(c) {
  const id = String(c.id);
  const bo = (state.nkHT || {})[id];
  if (!bo) {
    return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
      <button type="button" class="btn btn--sm btn--ghost" data-nk-ht="${esc(id)}">Xem việc AI và nhân viên đã làm</button>`;
  }
  if (bo.dangTai) return '<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Đang tải…</p>';
  if (bo.loi) return `<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  const dong = bo.items.map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc(nkTacNhan(b))} · ${esc((b.trang_thai || {}).nhan || "")}</span>
      ${b.ket_qua ? `<p>${esc(b.ket_qua)}</p>` : ""}
      ${b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? `<button type="button" class="msg__goc-nut" data-nk-ht-luot="${esc(id)}|${esc(b.luot_id)}">${
          bo.luot && bo.luot.luot_id === b.luot_id ? "Ẩn lượt AI" : "Xem lượt AI"}</button>` : ""}
      ${bo.luot && bo.luot.luot_id === b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? nkVeLuot(bo.luot) : ""}
    </div>`).join("");
  return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
    ${dong || '<p class="hint">Chưa có sự kiện nào.</p>'}`;
}

document.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-nk-ht], [data-nk-ht-luot]");
  if (!nut) return;
  state.nkHT = state.nkHT || {};
  if (nut.dataset.nkHt) {
    const id = nut.dataset.nkHt;
    state.nkHT[id] = { dangTai: true };
    if (state.openConv === id && typeof loadThread === "function") loadThread(id);
    try {
      const r = await api(`/nhat-ky/hoi-thoai/${id}?limit=50`);
      state.nkHT[id] = { items: r.items || [] };
    } catch (err) {
      state.nkHT[id] = { loi: err.message };
    }
  } else {
    const [id, luot] = nut.dataset.nkHtLuot.split("|");
    const bo = state.nkHT[id];
    if (!bo) return;
    if (bo.luot && bo.luot.luot_id === luot) { bo.luot = null; }
    else {
      try { bo.luot = await api(`/nhat-ky/hoi-thoai/${id}/luot/${encodeURIComponent(luot)}`); }
      catch (err) { toast(err.message, true); }
    }
  }
  const id = nut.dataset.nkHt || nut.dataset.nkHtLuot.split("|")[0];
  if (state.openConv === id && typeof loadThread === "function") loadThread(id);
});
