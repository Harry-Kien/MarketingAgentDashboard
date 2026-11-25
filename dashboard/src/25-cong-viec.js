/* ================= CÔNG VIỆC (phiếu việc mục 14) =================
 *
 * Ba tệp, một màn (mỗi tệp một phần, để không tệp nào vượt 1000 dòng):
 *
 *   25-cong-viec.js        danh sách: dòng việc, bộ lọc nhanh có số đếm,
 *                          dải cảnh báo quá hạn, gắn tab, khối Tổng quan ca.
 *   25b-cong-viec-chi-tiet.js  ngăn chi tiết bên phải (điện thoại: tấm phủ
 *                          toàn màn): hành động theo trạng thái, hoàn thành
 *                          nhanh, chọn người nhận kèm ca/tải, lịch sử có lọc.
 *   25c-cong-viec-tao.js   ngăn "Việc mới": liên kết dạng thẻ, gợi ý mã đơn
 *                          theo khách, mô tả trích tin khách gần nhất.
 *
 * Hai điểm gắn vào khung tab (01b-dieu-huong.js `ganKhe`):
 *   GAN_TAB["cv-danh-sach"]     Danh sách công việc.
 *   GAN_TAB["cv-ca-truc-viec"]  Khối "Công việc" trong Tổng quan ca trực.
 *
 * Danh sách cũ (08-tai-khoan.js) vẫn nằm trong `.tab__goc`: mô-đun này hỏng
 * thì ganKhe trả nó lại — màn không trắng. Hộp xác nhận kết quả ĐƠN (đối
 * soát ERPNext) dùng lại nguyên `cvMoKetQua` của tệp ấy, không chép lại:
 * hai bản luồng đối soát là hai chỗ để một chốt an toàn lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ (agent/api/cong_viec.py). Ẩn nút theo
 * quyền chỉ để màn hình không mời một 403 mỗi lần bấm.
 */
window.GAN_TAB = window.GAN_TAB || {};

const cvx = {
  el: null, ds: [], dm: null, moId: null, chiTiet: null,
  loc: { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
         chua_phan_cong: false, qua_han: false },
  nhanh: "", dem: null, tong: 0, quaHan: 0,
  // Việc mở từ chuông mà bộ lọc đang chọn giấu đi (UX-19-01) — ghim lên đầu.
  ghim: null,
  nguoiNhan: null, dangTai: false, hen: null,
};

function cvxCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function cvxNgay(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
}

/* Hạn "ngày X" là HẾT ngày X theo giờ máy người dùng (cùng luật màn cũ). */
function cvxHan(ngay) { return ngay ? new Date(ngay + "T23:59:59").toISOString() : null; }

function cvxNhan(ma, ds) {
  const x = (ds || []).find((t) => t.ma === ma);
  return x ? x.nhan : ma;
}

/* Cờ màu theo TÌNH TRẠNG THẬT: quá hạn đỏ dù đang "Đang thực hiện". */
function cvxCo_mau(v) {
  if (v.qua_han) return "halt";
  if (v.trang_thai === "xong") return "auto";
  if (v.trang_thai === "huy") return "spend";
  if (v.chua_phan_cong || v.uu_tien === "gap" || v.uu_tien === "cao") return "assist";
  return "auto";
}

/* Nhãn trạng thái NGẮN cho thẻ (UX-14-01). Quá hạn thắng mọi trạng thái mở:
   "Đang làm" mà quá hạn hai ngày thì điều cần thấy là quá hạn. */
function cvxTrangThai(v) {
  if (v.qua_han) return `<span class="cvx-tt cvx-tt--qua">Quá hạn</span>`;
  const nhan = { moi: "Chờ xử lý", dang_lam: "Đang làm", xong: "Hoàn thành", huy: "Đã hủy" };
  return `<span class="cvx-tt cvx-tt--${esc(v.trang_thai)}">${esc(nhan[v.trang_thai] || v.nhan_trang_thai)}</span>`;
}

function cvxUuTienTag(v) {
  if (v.uu_tien !== "gap" && v.uu_tien !== "cao") return "";
  return `<span class="cvx-ut cvx-ut--${esc(v.uu_tien)}">${esc(cvxNhan(v.uu_tien, cvx.dm && cvx.dm.uu_tien))}</span>`;
}

/* Chữ cái đầu của tên — avatar chữ, không ảnh (dashboard không giữ ảnh nhân viên). */
function cvxChuDau(ten) {
  const p = String(ten || "?").trim().split(/\s+/);
  return ((p.length > 1 ? p[p.length - 2][0] : "") + (p[p.length - 1][0] || "?")).toUpperCase();
}

function cvxNguoiPhuTrach(v) {
  if (v.chua_phan_cong) {
    return `<span class="cvx-nguoi cvx-nguoi--trong">${esc((cvx.dm && cvx.dm.nhan_chua_phan_cong) || "Chưa phân công")}</span>`;
  }
  if (!v.nguoi_nhan_ten) return `<span class="cvx-nguoi cvx-nguoi--trong">Không có người nhận</span>`;
  return `<span class="cvx-nguoi"><span class="cvx-avatar" aria-hidden="true">${esc(cvxChuDau(v.nguoi_nhan_ten))}</span>${esc(v.nguoi_nhan_ten)}</span>`;
}

/* "Quá hạn 2 ngày", không "Quá hạn 24-11": `clock()` đổi sang ngày tháng sau
   một ngày, và "quá hạn 24-11" đọc như một mã chứ không như một khoảng trễ. */
function cvxTre(iso) {
  const giay = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  if (giay < 3600) return Math.max(1, Math.floor(giay / 60)) + " phút";
  if (giay < 86400) return Math.floor(giay / 3600) + " giờ";
  return Math.floor(giay / 86400) + " ngày";
}

/* Hạn đọc được: "trong 3 giờ", "quá hạn 2 ngày" — không phải ISO. */
function cvxHanChu(v) {
  if (!v.han) return `<span class="cvx-han cvx-han--khong">Không hạn</span>`;
  if (v.qua_han) return `<span class="cvx-han cvx-han--qua">Quá hạn ${esc(cvxTre(v.han))}</span>`;
  if (v.trang_thai === "xong" || v.trang_thai === "huy") {
    return `<span class="cvx-han">Hạn ${esc(cvxNgay(v.han))}</span>`;
  }
  const gap = new Date(v.han) - Date.now() < 86400000;
  return `<span class="cvx-han${gap ? " cvx-han--gan" : ""}">Hạn ${esc(hanDoc(v.han))}</span>`;
}

/* Tiến độ THẬT: bước trạng thái + số lần cập nhật tiến độ + dòng mới nhất.
   Không có ô "phần trăm" — một con số người ta tự điền không phải tiến độ. */
function cvxTienDo(v) {
  const buoc = { moi: 1, dang_lam: 2, xong: 3 }[v.trang_thai] || 0;
  const thanh = [1, 2, 3].map((i) => `<i class="${i <= buoc ? "is-xong" : ""}"></i>`).join("");
  const so = Number(v.so_tien_do || 0);
  const cuoi = v.tien_do_cuoi ? String(v.tien_do_cuoi) : "";
  const chu = so
    ? `${so} cập nhật · ${esc(clock(v.tien_do_luc))}: ${esc(cuoi.length > 80 ? cuoi.slice(0, 79) + "…" : cuoi)}`
    : (v.trang_thai === "huy" ? "Đã hủy" : "Chưa cập nhật tiến độ");
  return `<span class="cvx-tien" title="${esc(cuoi)}">
    <span class="cvx-tien__thanh cvx-tien__thanh--${esc(v.trang_thai)}" aria-hidden="true">${thanh}</span>
    <span class="cvx-tien__chu">${chu}</span></span>`;
}

function cvxDong(v, ghim = false) {
  const nhanDuoc = v.chua_phan_cong && cvxCo("cong_viec.sua");
  const ngu = [
    v.khach_ten ? "Khách: " + esc(v.khach_ten) : "",
    v.ma_don ? "Đơn " + esc(v.ma_don) : "",
    esc(v.nhan_nguon),
  ].filter(Boolean).join(" · ");
  return `<div class="row cvx-dong${cvx.moId === v.id ? " is-on" : ""}${ghim ? " cvx-dong--ghim" : ""}"
      data-cv="${esc(v.id)}" data-cvx-mo="${esc(v.id)}" role="button" tabindex="0"
      aria-label="${esc(v.tieu_de)} — mở chi tiết">
    <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
    <div class="cvx-dong__chinh">
      ${ghim ? `<span class="cvx-ghim">Mở từ thông báo — không khớp bộ lọc đang chọn</span>` : ""}
      <div class="cvx-dong__dau"><b class="cvx-dong__ten">${esc(v.tieu_de)}</b>${cvxTrangThai(v)}${cvxUuTienTag(v)}</div>
      <div class="cvx-dong__meta">${cvxNguoiPhuTrach(v)}${cvxHanChu(v)}<span class="cvx-dong__ngu">${ngu}</span></div>
      ${cvxTienDo(v)}
    </div>
    <div class="row__side">
      ${nhanDuoc ? `<button type="button" class="btn btn--sm" data-cvx-nhan="${esc(v.id)}">Nhận</button>` : ""}
      <span class="cvx-dong__tao">tạo ${esc(clock(v.tao_luc))}</span>
    </div>
  </div>`;
}

/* ---------------- bộ lọc nhanh ---------------- */

/* [mã chip, nhãn, khoá trong `dem` của máy chủ]. Một chip một lúc: "Quá hạn"
   VÀ "Hoàn thành" cùng bật là một bộ lọc luôn rỗng. */
const CVX_NHANH = [
  ["", "Tất cả", "tat_ca"],
  ["moi", "Chờ xử lý", "cho_xu_ly"],
  ["dang_lam", "Đang làm", "dang_lam"],
  ["qua_han", "Quá hạn", "qua_han"],
  ["chua_phan_cong", "Chưa phân công", "chua_phan_cong"],
  ["xong", "Hoàn thành", "hoan_thanh"],
  ["huy", "Đã hủy", "da_huy"],
];

function cvxDatNhanh(k) {
  cvx.nhanh = k;
  cvx.loc.trang_thai = ["moi", "dang_lam", "xong", "huy"].includes(k) ? k : "";
  cvx.loc.qua_han = k === "qua_han";
  cvx.loc.chua_phan_cong = k === "chua_phan_cong";
}

function cvxXoaLoc() {
  cvx.loc = { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
              chua_phan_cong: false, qua_han: false };
  cvx.nhanh = "";
  if (!cvx.el) return;
  $("#cvxTim", cvx.el).value = "";
  $("#cvxUuTien", cvx.el).value = "";
  $("#cvxNguon", cvx.el).value = "";
}

function cvxVeChip() {
  const o = cvx.el && $("#cvxNhanh", cvx.el);
  if (!o) return;
  const dem = cvx.dem || {};
  o.innerHTML = CVX_NHANH.map(([k, nhan, khoa]) => {
    const so = dem[khoa];
    const bat = cvx.nhanh === k;
    const canh = (k === "qua_han" && so) ? " cvx-chip--qua" : "";
    return `<button type="button" class="chip cvx-chip${bat ? " is-on" : ""}${canh}" data-cvx-nhanh="${k}"
      aria-pressed="${bat}">${esc(nhan)}${so != null ? ` <span class="cvx-chip__so">${so}</span>` : ""}</button>`;
  }).join("");
}

/* Điều kiện đang lọc, nói thành chữ (UX-14-02): người ta phải biết VÌ SAO
   danh sách chỉ còn 3 dòng trước khi kết luận "mất việc". */
function cvxVeTomTat() {
  const o = cvx.el && $("#cvxTomTat", cvx.el);
  if (!o) return;
  const l = cvx.loc;
  const dk = [];
  const chip = CVX_NHANH.find(([k]) => k === cvx.nhanh);
  if (cvx.nhanh && chip) dk.push(chip[1]);
  if (l.cua_toi) dk.push("Việc của tôi");
  if (l.uu_tien) dk.push("Ưu tiên " + cvxNhan(l.uu_tien, cvx.dm && cvx.dm.uu_tien));
  if (l.nguon) dk.push("Nguồn: " + cvxNhan(l.nguon, cvx.dm && cvx.dm.nguon));
  if (l.q) dk.push(`Tìm “${l.q}”`);
  const hien = cvx.ds.length;
  const tong = cvx.tong;
  o.innerHTML = `<span class="cvx-tomtat__so"><b>${tong}</b> việc${hien < tong ? ` · hiện ${hien} đầu tiên` : ""}</span>
    ${dk.length ? `<span class="cvx-tomtat__dk">Đang lọc: ${dk.map((x) => `<span class="cvx-tomtat__the">${esc(x)}</span>`).join("")}</span>
      <button type="button" class="btn btn--sm btn--ghost" data-cvx-xoa-loc>Xoá bộ lọc</button>` : ""}`;
}

/* Dải cảnh báo quá hạn (MD-UX-14-07): đếm trên TOÀN phạm vi người xem, không
   trên bộ lọc đang chọn — đang lọc "Hoàn thành" thì càng phải biết còn việc
   quá hạn ở chỗ khác. */
function cvxVeCanhBao() {
  const o = cvx.el && $("#cvxCanhBao", cvx.el);
  if (!o) return;
  const n = cvx.quaHan;
  o.hidden = !n || cvx.nhanh === "qua_han";
  o.innerHTML = n ? `<span class="cvx-canh-bao__chu"><b>${n} việc đã quá hạn</b> — cần ưu tiên xử lý hoặc cập nhật hạn.</span>
    <button type="button" class="btn btn--sm btn--halt" data-cvx-xem-qua-han>Xem ngay</button>` : "";
}

/* ---------------- tải ---------------- */

async function cvxTaiDs() {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(cvx.loc)) {
    if (v === true) q.set(k, "true");
    else if (v) q.set(k, v);
  }
  const d = await api(`/cong-viec?${q}`);
  cvx.dm = { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon,
             nhan_chua_phan_cong: d.nhan_chua_phan_cong };
  cvx.ds = d.cong_viec;
  cvx.dem = d.dem || null;
  cvx.tong = d.tong != null ? d.tong : d.cong_viec.length;
  /* Việc ghim đã hiện trong danh sách (người ta đổi bộ lọc) thì thôi ghim. */
  if (cvx.ghim && cvx.ds.some((x) => x.id === cvx.ghim.id)) cvx.ghim = null;
  /* Hộp xác nhận kết quả ĐƠN của 08-tai-khoan.js tìm việc trong
     `congViec.ds` — giữ cùng danh sách để nó mở được từ màn này. */
  congViec.ds = d.cong_viec;
  congViec.trangThai = d.trang_thai;
  congViec.uuTien = d.uu_tien;
}

async function cvxTaiDem() {
  if (!cvxCo("cong_viec.doc")) return null;
  try {
    const t = await api("/cong-viec/tong-quan");
    $("#c-congviec").textContent = (t.dem.cho_xu_ly + t.dem.dang_thuc_hien) || "";
    cvx.quaHan = t.dem.qua_han || 0;
    cvxVeCanhBao();
    return t;
  } catch (e) { console.warn("Không tải được tổng quan công việc", e); return null; }
}

/* `ep` = vừa thao tác trong ngăn chi tiết, PHẢI vẽ lại ngăn dù focus đang ở
   trong đó (nút vừa bấm giữ focus — bỏ qua là toast "Đã giao" hiện ra mà
   ngăn vẫn ghi người cũ). */
async function cvxLamMoi(ep = false) {
  if (!cvx.el || cvx.dangTai || !cvxCo("cong_viec.doc")) return;
  cvx.dangTai = true;
  try {
    await cvxTaiDs();
    cvxVeDs();
    /* Không vẽ lại ngăn chi tiết khi người ta đang GÕ trong đó: vẽ lại là
       mất chỗ con trỏ, và vòng 20 giây sẽ cắt ngang câu kết quả đang viết. */
    const o = document.activeElement;
    const dangGo = o && o.matches && o.matches("#cvxCt input, #cvxCt textarea, #cvxCt select");
    if (cvx.moId && (ep || !dangGo)) await cvxTaiChiTiet(cvx.moId, false);
    cvxTaiDem();
  } catch (e) {
    $("#cvxDs", cvx.el).innerHTML = `<p class="empty">Không tải được công việc: ${esc(e.message)}</p>`;
  } finally { cvx.dangTai = false; }
}

function cvxVeDs() {
  const o = $("#cvxDs", cvx.el);
  const ghim = cvx.ghim ? cvxDong(cvx.ghim, true) : "";
  o.innerHTML = ghim + (cvx.ds.length ? cvx.ds.map((v) => cvxDong(v)).join("")
    : `<div class="empty">Không có việc nào khớp bộ lọc này.${
        cvx.nhanh || cvx.loc.q || cvx.loc.uu_tien || cvx.loc.nguon || cvx.loc.cua_toi
          ? ` <button type="button" class="btn btn--sm btn--ghost" data-cvx-xoa-loc>Xoá bộ lọc</button>` : ""}</div>`);
  cvxVeChip();
  cvxVeTomTat();
  cvxVeCanhBao();
}

/* Mở ngữ cảnh của việc (mục 14.8). */
function cvxDiToiDon(ma) {
  state.orderFilter = "all";
  doiMan("donhang");
  if (!ma) return;
  setTimeout(() => {
    const dong = [...$$("#orders > *")].find((x) => x.textContent.includes(ma));
    if (dong) { dong.scrollIntoView({ behavior: "smooth", block: "center" }); dong.classList.add("is-chuong");
      setTimeout(() => dong.classList.remove("is-chuong"), 2400); }
  }, 900);
}

function cvxBatSuKienLienKet(o) {
  o.addEventListener("click", (e) => {
    const ht = e.target.closest("[data-cvx-ht]");
    if (ht) { state.openConv = ht.dataset.cvxHt; state.cuonToiChiTiet = true; doiMan("hoithoai"); return; }
    const kh = e.target.closest("[data-cvx-kh]");
    if (kh) { openCustomer(kh.dataset.cvxKh); return; }
    const don = e.target.closest("[data-cvx-don]");
    if (don) cvxDiToiDon(don.dataset.cvxDon);
  });
}

/* ---------------- gắn: Danh sách công việc ---------------- */

GAN_TAB["cv-danh-sach"] = (el) => {
  cvx.el = el;
  if (!cvxCo("cong_viec.doc")) {
    el.innerHTML = '<section class="panel"><p class="empty">Bạn không có quyền xem công việc.</p></section>';
    return;
  }
  const opt = (ds) => ds.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  el.innerHTML = `
    <div class="cvx-bo">
      <section class="panel cvx-khung">
        <h2 class="panel__head cvx-khung__dau">Công việc
          <span class="panel__note">việc nội bộ cần người theo dõi — chuyển hội thoại cho người KHÔNG sinh việc</span>
          ${cvxCo("cong_viec.sua") ? '<button type="button" class="btn btn--sm btn--primary" id="cvxThem">+ Tạo việc</button>' : ""}</h2>
        <div class="cvx-canh-bao" id="cvxCanhBao" role="status" hidden></div>
        <div class="filterbar cvx__loc" role="group" aria-label="Lọc công việc">
          <input type="search" id="cvxTim" class="cvx__tim" placeholder="Tìm tiêu đề, khách, mã đơn…" maxlength="100" aria-label="Tìm công việc">
          <select id="cvxUuTien" aria-label="Ưu tiên">${opt([["", "Mọi ưu tiên"], ["gap", "Gấp"],
            ["cao", "Cao"], ["thuong", "Thường"], ["thap", "Thấp"]])}</select>
          <select id="cvxNguon" aria-label="Nguồn">${opt([["", "Mọi nguồn"], ["nguoi", "Nhân viên tạo"],
            ["agent", "AI đề xuất"], ["tu_dong", "Tự động"], ["van_chuyen", "Vận chuyển"], ["don_hang", "Đơn hàng"]])}</select>
          <button type="button" class="chip" data-cvx-loc="cua_toi" aria-pressed="false">Việc của tôi</button>
        </div>
        <div class="cvx-nhanh" id="cvxNhanh" role="group" aria-label="Lọc nhanh theo tình trạng"></div>
        <div class="cvx-tomtat" id="cvxTomTat" aria-live="polite"></div>
        <div id="cvxDs" class="rows"><p class="empty">Đang tải…</p></div>
      </section>
      <aside id="cvxCt" class="cvx-ngan" aria-label="Chi tiết công việc" hidden></aside>
    </div>`;

  $("#cvxThem", el)?.addEventListener("click", () => cvxTaoViec());
  let hoan = null;
  $("#cvxTim", el).addEventListener("input", (e) => {
    clearTimeout(hoan);
    hoan = setTimeout(() => { cvx.loc.q = e.target.value.trim(); cvxLamMoi(); }, 300);
  });
  for (const [sel, k] of [["#cvxUuTien", "uu_tien"], ["#cvxNguon", "nguon"]]) {
    $(sel, el).addEventListener("change", (e) => { cvx.loc[k] = e.target.value; cvxLamMoi(); });
  }
  el.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches && e.target.matches(".cvx-dong")) {
      e.preventDefault();
      cvxTaiChiTiet(e.target.dataset.cvxMo);
    }
  });
  el.addEventListener("click", async (e) => {
    const loc = e.target.closest("[data-cvx-loc]");
    if (loc) {
      const k = loc.dataset.cvxLoc;
      cvx.loc[k] = !cvx.loc[k];
      loc.classList.toggle("is-on", cvx.loc[k]);
      loc.setAttribute("aria-pressed", String(cvx.loc[k]));
      cvxLamMoi();
      return;
    }
    const nhanh = e.target.closest("[data-cvx-nhanh]");
    if (nhanh) { cvxDatNhanh(nhanh.dataset.cvxNhanh); cvxVeChip(); cvxLamMoi(); return; }
    if (e.target.closest("[data-cvx-xem-qua-han]")) {
      cvxDatNhanh("qua_han"); cvxVeChip(); cvxLamMoi(); return;
    }
    if (e.target.closest("[data-cvx-xoa-loc]")) {
      cvxXoaLoc();
      $$("[data-cvx-loc]", el).forEach((c) => { c.classList.remove("is-on"); c.setAttribute("aria-pressed", "false"); });
      cvxLamMoi();
      return;
    }
    const nhan = e.target.closest("[data-cvx-nhan]");
    if (nhan) {
      await cvxPut(nhan.dataset.cvxNhan, { nguoi_nhan: state.toiId, trang_thai: "dang_lam" }, "Bạn đã nhận việc này.");
      return;
    }
    /* Bấm trong ngăn chi tiết do 25b lo; ở đây chỉ bắt dòng danh sách. */
    if (e.target.closest("#cvxCt")) return;
    const mo = e.target.closest("[data-cvx-mo]");
    if (mo) await cvxTaiChiTiet(mo.dataset.cvxMo);
  });
  cvxBatSuKienLienKet(el);
  cvxBatSuKienNgan(el);
  el.addEventListener("tab:hien", () => cvxLamMoi());
  cvxVeChip();
  cvxLamMoi();
};

/* Vòng làm mới chung (10-vong-lam-moi) KHÔNG nạp tab đã gắn mô-đun — mô-đun
 * tự lo: làm mới khi tab đang hiện, và khi hộp xác nhận đơn của 08 vừa đổi
 * dữ liệu (nó gọi loadCongViec, phát `congviec:doi`). */
setInterval(() => {
  if (document.hidden) return;
  if (cvx.el && tabDangHien("cv-danh-sach")) cvxLamMoi();
  if (cvxCa.el && tabDangHien("cv-ca-truc")) cvxCaTai();
}, 20000);
document.addEventListener("congviec:doi", () => { if (cvx.el) cvxLamMoi(); });

/* Chuông "việc" và mọi lối khác mở thẳng chi tiết một việc. Việc không nằm
 * trong bộ lọc đang chọn thì GHIM lên đầu danh sách kèm lý do (UX-19-01) —
 * không âm thầm xoá bộ lọc người ta vừa chọn, cũng không để chi tiết mở ra
 * cho một việc không thấy đâu trong danh sách. */
window.moCongViec = async (id) => {
  if (!cvxCo("cong_viec.doc")) return false;
  if (doiMan("cv-danh-sach") === false) return false;
  if (!cvx.el) return false;
  await cvxTaiChiTiet(id);
  if (cvx.moId !== id) return false;
  const dong = $(`#cvxDs [data-cv="${CSS.escape(id)}"]`, cvx.el);
  if (dong) {
    dong.scrollIntoView({ behavior: "smooth", block: "nearest" });
    dong.classList.add("is-chuong");
    setTimeout(() => dong.classList.remove("is-chuong"), 2400);
  }
  return true;
};

/* Nút "+ Tạo công việc" trong hội thoại (03-hoi-thoai.js vẽ lại khung mỗi
 * nhịp, nên bắt ở document). Gắn sẵn hội thoại + khách (mục 14.3). */
document.addEventListener("click", (e) => {
  if (!e.target.closest("#btn-tao-viec-ht")) return;
  const c = state.convDangMo;
  if (!c) return;
  cvxTaoViec({ conversation_id: c.id, contact_id: c.contact_id, ten_khach: c.customer_name });
});

/* ---------------- gắn: khối Công việc trong Tổng quan ca trực ---------------- */

const cvxCa = { el: null };

function cvxO(nhan, so, loc, mau) {
  return `<button type="button" class="readout__cell cvx__o" data-cvx-di="${loc}">
    <span class="readout__label">${esc(nhan)}</span>
    <span class="readout__line"><span class="readout__value">${so}</span></span>
    <span class="readout__bar"><span class="readout__fill readout__fill--${mau}" style="width:${so ? 100 : 0}%"></span></span>
  </button>`;
}

async function cvxCaTai() {
  const o = cvxCa.el;
  if (!o) return;
  if (!cvxCo("cong_viec.doc")) { o.innerHTML = ""; return; }
  const t = await cvxTaiDem();
  if (!t) { o.innerHTML = '<p class="empty">Không tải được tổng quan công việc.</p>'; return; }
  const d = t.dem;
  const giao = cvxCo("cong_viec.giao");
  const nv = t.nhan_vien;
  o.innerHTML = `<section class="panel">
    <h2 class="panel__head">Công việc
      <span class="panel__note">${t.tu_dong_duoc == null ? "trong phạm vi bạn thấy"
        : t.tu_dong_duoc ? `${t.tu_dong_duoc} người đang nhận được phân công tự động`
        : "LÚC NÀY không ai trong ca để phân công tự động — việc mới sẽ ở Chưa phân công"}</span></h2>
    <div class="readout">
      ${cvxO("Chưa phân công", d.chua_phan_cong, "chua_phan_cong", d.chua_phan_cong ? "assist" : "auto")}
      ${cvxO("Chờ xử lý", d.cho_xu_ly, "moi", "spend")}
      ${cvxO("Đang thực hiện", d.dang_thuc_hien, "dang_lam", "auto")}
      ${cvxO("Quá hạn", d.qua_han, "qua_han", d.qua_han ? "halt" : "auto")}
      ${cvxO("Hoàn thành hôm nay", d.xong_hom_nay, "xong", "auto")}
    </div>
    <div class="split">
      <div>
        <h3 class="cvx__ls-tieu">Việc chưa phân công</h3>
        <div class="rows">${t.chua_phan_cong.length ? t.chua_phan_cong.map((v) => `<div class="row">
          <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
          <div class="row__main"><b>${esc(v.tieu_de)}</b>
            <span class="row__sub">${esc(v.nhan_nguon)} · ${esc(cvxNhan(v.uu_tien, t.uu_tien))}${
              v.han ? " · hạn " + esc(hanDoc(v.han)) : ""}${v.khach_ten ? " · " + esc(v.khach_ten) : ""}</span></div>
          <div class="row__side"><span class="row__nut">
            ${cvxCo("cong_viec.sua") ? `<button type="button" class="btn btn--sm" data-cvx-ca-nhan="${esc(v.id)}">Nhận</button>` : ""}
            ${giao ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-tu-dong="${esc(v.id)}">Tự phân công</button>` : ""}
            <button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-mo="${esc(v.id)}">Mở</button>
          </span></div></div>`).join("") : '<p class="empty">Không có việc nào chờ phân công.</p>'}</div>
      </div>
      ${nv ? `<div>
        <h3 class="cvx__ls-tieu">Nhân viên và việc đang giữ</h3>
        <div class="rows">${nv.length ? nv.map((n) => `<div class="row">
          <span class="row__flag row__flag--${n.trong_ca_that && n.san_sang ? "auto" : "assist"}"></span>
          <div class="row__main"><b>${esc(n.ten)}</b>
            <span class="row__sub">${n.dang_nghi ? "đang nghỉ" : n.trong_ca_that ? "đang trong ca" : n.co_lich ? "ngoài ca" : "chưa xếp ca"}${
              n.san_sang ? "" : " · tắt sẵn sàng"}</span></div>
          <div class="row__side"><span><span class="pill">${n.so_mo} việc mở</span>${
            n.so_qua_han ? ` <span class="pill pill--warn">${n.so_qua_han} quá hạn</span>` : ""}</span></div>
        </div>`).join("") : '<p class="empty">Chưa có nhân viên nào làm được công việc.</p>'}</div>
      </div>` : ""}
    </div>
  </section>`;
}

GAN_TAB["cv-ca-truc-viec"] = (el) => {
  cvxCa.el = el;
  el.addEventListener("click", async (e) => {
    const di = e.target.closest("[data-cvx-di]");
    if (di) {
      cvxXoaLoc();
      cvxDatNhanh(di.dataset.cvxDi);
      doiMan("cv-danh-sach");
      if (cvx.el) {
        $$("[data-cvx-loc]", cvx.el).forEach((c) => { c.classList.remove("is-on"); c.setAttribute("aria-pressed", "false"); });
        cvxVeChip();
        cvxLamMoi();
      }
      return;
    }
    const mo = e.target.closest("[data-cvx-ca-mo]");
    if (mo) { await window.moCongViec(mo.dataset.cvxCaMo); return; }
    const nhan = e.target.closest("[data-cvx-ca-nhan]");
    const tuDong = e.target.closest("[data-cvx-ca-tu-dong]");
    try {
      if (nhan) {
        await api(`/cong-viec/${encodeURIComponent(nhan.dataset.cvxCaNhan)}`, { method: "PUT",
          body: JSON.stringify({ nguoi_nhan: state.toiId, trang_thai: "dang_lam" }) });
        toast("Bạn đã nhận việc này.");
      } else if (tuDong) {
        const r = await api(`/cong-viec/${encodeURIComponent(tuDong.dataset.cvxCaTuDong)}/tu-dong-giao`, { method: "POST" });
        toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      } else return;
    } catch (err) { toast(err.message, true); }
    cvxCaTai();
  });
  el.addEventListener("tab:hien", () => cvxCaTai());
  cvxCaTai();
};
