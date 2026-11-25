/* ================= NHÂN SỰ & PHÂN QUYỀN (phiếu việc mục 12–13) =================
 *
 * Bốn tab gắn vào khung tab của dashboard (UX-13-08 — trước đây danh sách
 * người, lịch ca, lịch sử và vai trò dồn trên hai trang dài):
 *
 *   GAN_TAB["ns-nhan-vien"]  24b — tài khoản: tìm, lọc, xem chi tiết, sửa,
 *                            đặt lại mật khẩu, khoá kèm chuyển việc
 *   GAN_TAB["ns-vai-tro"]    24c — vai trò và bảng cấp quyền
 *   GAN_TAB["ns-lich-su"]    24c — lịch sử nhân sự & phân quyền
 *   tab "ns-lich-ca"         lịch ca (16-lich-ca.js, nội dung sẵn trong HTML)
 *
 * Tệp này giữ phần DÙNG CHUNG: dữ liệu, bảng tick quyền, khung xem quyền một
 * người, ngăn kéo chi tiết, lịch sử, khoá / mở khoá / chuyển việc / đặt lại
 * mật khẩu. Màn "Nhân sự" cũ (09-nhan-su.js) cũng gọi các hàm ở đây: hai bản
 * chép của một luật là hai chỗ để luật ấy lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ. Ẩn nút theo quyền chỉ để màn hình
 * không mời một 403 mỗi lần bấm — không phải để bảo vệ gì.
 */
window.GAN_TAB = window.GAN_TAB || {};

const nsv = { nguoi: [], vaiTro: [], nhom: [], nhayCam: {}, xemQuyen: null };

function nsvCo(quyen) {
  return !!(state.toiQuyen && state.toiQuyen.has(quyen));
}

async function nsvTaiDuLieu() {
  const [nd, vt, dm] = await Promise.all([
    api("/nguoi-dung"), api("/vai-tro"), api("/quyen"),
  ]);
  nsv.nguoi = nd.nguoi_dung || [];
  nsv.vaiTro = vt.vai_tro || [];
  nsv.nhom = dm.nhom_hien_thi || [];
  nsv.nhayCam = dm.nhay_cam || {};
}

/* Nhãn tiếng Việt của một mã quyền — lịch sử lưu MÃ (bền qua các lần đổi
   nhãn), màn hình hiện NHÃN (người đọc không thuộc mã). */
function nsvNhanQuyen(ma) {
  for (const g of nsv.nhom) {
    const q = g.quyen.find((x) => x.ma === ma);
    if (q) return q.nhan;
  }
  return ma;
}

function nsvNgay(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }) : "—";
}

/* Bỏ dấu để tìm: người gõ "xoa" phải thấy "Xoá vĩnh viễn…". Gõ tiếng Việt có
   dấu trên điện thoại chậm, và một ô tìm bắt gõ đúng dấu là ô tìm hỏng. */
function nsvBoDau(s) {
  return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d").replace(/Đ/g, "d").toLowerCase();
}

/* ---------------- quyền nhạy cảm (danh sách ở máy chủ: QUYEN_NHAY_CAM) ---------------- */

function nsvLaNhayCam(ma) {
  return Object.prototype.hasOwnProperty.call(nsv.nhayCam, ma);
}

function nsvTheNhayCam(ma) {
  return nsvLaNhayCam(ma)
    ? `<span class="pill pill--halt" title="${esc(nsv.nhayCam[ma])}">nhạy cảm</span>` : "";
}

function nsvTatCaMa() {
  return nsv.nhom.flatMap((g) => g.quyen.map((q) => q.ma));
}

/* Quyền một vai trò THẬT SỰ cấp. Ngừng dùng thì không cấp gì — cùng luật với
   `doc_phien` ở máy chủ; tính khác là màn hình nói một người có quyền mà
   thật ra không có. */
function nsvQuyenCuaVai(v) {
  if (!v || v.dang_dung === false) return [];
  return v.toan_quyen ? nsvTatCaMa() : (v.quyen || []);
}

function nsvVaiCuaNguoi(n) {
  return (n.vai_tro_id || []).map((id) => nsv.vaiTro.find((v) => v.id === id)).filter(Boolean);
}

/* Vai trò đang dùng của một người -> quyền nhạy cảm nó cấp. Cùng hình với
   `vai_tro_nhay_cam_cua` ở máy chủ (SEC-13-01). */
function nsvVaiNhayCam(n) {
  const ra = {};
  for (const v of nsvVaiCuaNguoi(n)) {
    const nc = nsvQuyenCuaVai(v).filter(nsvLaNhayCam);
    if (nc.length) ra[v.ten] = nc;
  }
  return ra;
}

/* Quyền người này có mà NGƯỜI ĐANG THAO TÁC không có. Khác rỗng thì máy chủ
   sẽ từ chối sửa/khoá/đặt lại mật khẩu (`chan_cap_vuot`) — khoá nút trước,
   kèm lý do, thay vì để người ta bấm rồi đọc 403. */
function nsvVuotQuyen(n) {
  if (!state.toiQuyen) return [];
  const co = new Set(nsvVaiCuaNguoi(n).flatMap(nsvQuyenCuaVai));
  return [...co].filter((q) => !state.toiQuyen.has(q));
}

/* ---------------- dùng chung: bảng tick quyền theo nhóm (UX-12-03) ---------------- */

/* Nhóm theo CHỨC NĂNG dashboard (máy chủ trả `nhom_hien_thi`, đúng thứ tự
 * phiếu việc), không theo tiền tố mã. Mỗi nhóm THU GỌN được và nói sẵn
 * "đã chọn 3/5" — 46 ô tick phẳng là thứ người ta tick theo linh cảm.
 *
 * Mã quyền (`khach.xoa`) chỉ còn trong `title`: người quản trị đọc nhãn;
 * mã chỉ cần khi đối chiếu thông báo 403 ("Thiếu quyền: khach.xoa"), và rê
 * chuột / ô tìm (tìm được cả theo mã) là đủ cho việc đó.
 *
 * `khoa` = chỉ xem (vai trò Quản trị lấy quyền từ mã, tick ở đó vô tác dụng). */
function nsvBangQuyen(dangCo, khoa = false) {
  const co = new Set(dangCo || []);
  if (!nsv.nhom.length) return '<p class="empty">Chưa tải được danh mục quyền.</p>';
  const tong = nsv.nhom.reduce((n, g) => n + g.quyen.length, 0);
  const nhom = nsv.nhom.map((g) => {
    const chon = g.quyen.filter((q) => co.has(q.ma)).length;
    const nc = g.quyen.filter((q) => nsvLaNhayCam(q.ma)).length;
    return `<details class="quyen__nhom nsv-nhom" data-nsv-nhom="${esc(g.ma)}">
      <summary><span class="nsv-nhom__ten">${esc(g.ten)}</span>
        <span class="nsv-nhom__dem" data-nsv-dem-nhom>${chon}/${g.quyen.length}</span>
        ${nc ? `<span class="pill pill--halt">${nc} nhạy cảm</span>` : ""}
        ${khoa ? "" : `<button type="button" class="btn btn--sm btn--ghost nsv-nhom__ca"
          data-nsv-ca-nhom="${esc(g.ma)}">chọn / bỏ cả nhóm</button>`}</summary>
      ${g.quyen.map((q) => `<label class="quyen__o${nsvLaNhayCam(q.ma) ? " is-nhay-cam" : ""}"
          title="Mã: ${esc(q.ma)}" data-nsv-tim="${esc(nsvBoDau(`${q.nhan} ${q.ma} ${g.ten}`))}">
        <input type="checkbox" name="quyen" value="${esc(q.ma)}"${co.has(q.ma) ? " checked" : ""}${khoa ? " disabled" : ""}>
        <span>${esc(q.nhan)}</span>${nsvTheNhayCam(q.ma)}</label>`).join("")}
    </details>`;
  }).join("");
  return `<div class="nsv-mt" data-nsv-ma-tran>
    <div class="nsv-mt__cong-cu">
      <input type="search" class="nsv-tim" data-nsv-tim-quyen autocomplete="off"
             placeholder="Tìm quyền: xoá, cấu hình, khach.pii…" aria-label="Tìm quyền">
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-mo-nhom="1">Mở hết</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-mo-nhom="0">Thu gọn</button>
      <span class="nsv-mt__dem" data-nsv-dem-chon>${co.size}/${tong} quyền</span>
    </div>
    ${nhom}
    <p class="empty" data-nsv-khong-thay hidden>Không có quyền nào khớp.</p>
  </div>`;
}

function nsvDemLai(mt) {
  if (!mt) return;
  $$("[data-nsv-nhom]", mt).forEach((g) => {
    const o = $$('input[name="quyen"]', g);
    const d = g.querySelector("[data-nsv-dem-nhom]");
    if (d) d.textContent = `${o.filter((i) => i.checked).length}/${o.length}`;
  });
  const tong = $$('input[name="quyen"]', mt);
  const d = mt.querySelector("[data-nsv-dem-chon]");
  if (d) d.textContent = `${tong.filter((i) => i.checked).length}/${tong.length} quyền`;
}

function nsvLocQuyen(mt, chu) {
  const k = nsvBoDau(chu).trim();
  let thay = 0;
  $$("[data-nsv-nhom]", mt).forEach((g) => {
    let co = 0;
    $$("[data-nsv-tim]", g).forEach((o) => {
      const hop = !k || o.dataset.nsvTim.includes(k);
      o.hidden = !hop;
      if (hop) co += 1;
    });
    g.hidden = !co;
    if (k) g.open = co > 0;
    thay += co;
  });
  const kt = mt.querySelector("[data-nsv-khong-thay]");
  if (kt) kt.hidden = thay > 0;
}

/* Lắng nghe ở `document`: bảng tick vẽ ở cả màn cũ (#nsQuyen) lẫn ngăn kéo
   của tab Vai trò — một bộ bắt cho mọi chỗ, không gắn lại mỗi lần vẽ. */
document.addEventListener("click", (e) => {
  const ca = e.target.closest("[data-nsv-ca-nhom]");
  if (ca) {
    e.preventDefault();                       // nút nằm trong <summary>: đừng gập nhóm
    const o = $$('input[name="quyen"]:not(:disabled)', ca.closest("[data-nsv-nhom]"));
    const batHet = o.some((i) => !i.checked);
    o.forEach((i) => { i.checked = batHet; });
    nsvDemLai(ca.closest("[data-nsv-ma-tran]"));
    return;
  }
  const mo = e.target.closest("[data-nsv-mo-nhom]");
  if (mo) {
    $$("[data-nsv-nhom]", mo.closest("[data-nsv-ma-tran]"))
      .forEach((g) => { g.open = mo.dataset.nsvMoNhom === "1"; });
  }
});
document.addEventListener("input", (e) => {
  if (e.target.matches("[data-nsv-tim-quyen]")) {
    nsvLocQuyen(e.target.closest("[data-nsv-ma-tran]"), e.target.value);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.name === "quyen") nsvDemLai(e.target.closest("[data-nsv-ma-tran]"));
  if (e.target.matches("[data-nsv-hien-ca]") && nsv.xemQuyen) {
    const khung = e.target.closest("[data-nsv-xem-quyen]");
    if (khung) khung.outerHTML = nsvVeQuyenNguoi(nsv.xemQuyen, e.target.checked);
  }
});

/* ---------------- dùng chung: quyền THỰC TẾ của một người (UX-13-02, MD-UX-13-04) ---------------- */

/* Tóm tắt theo nhóm ("Hội thoại 3/5"), mở từng nhóm để xem chi tiết và vai
 * trò nào cấp. "Hiển thị cả quyền chưa cấp" để đối chiếu — câu hỏi người ta
 * mang tới màn này thường là "vì sao người này KHÔNG vào được màn X". */
function nsvVeQuyenNguoi(d, hienCa = false) {
  nsv.xemQuyen = d;
  const co = d.quyen || {};
  const tong = Object.keys(co).length;
  const nhom = nsv.nhom.map((g) => {
    const coNhom = g.quyen.filter((q) => co[q.ma]);
    const dong = hienCa ? g.quyen : coNhom;
    if (!dong.length) return "";
    const nc = coNhom.filter((q) => nsvLaNhayCam(q.ma)).length;
    return `<details class="quyen__nhom nsv-nhom">
      <summary><span class="nsv-nhom__ten">${esc(g.ten)}</span>
        <span class="nsv-nhom__dem">${coNhom.length}/${g.quyen.length}</span>
        ${nc ? `<span class="pill pill--halt">${nc} nhạy cảm</span>` : ""}</summary>
      ${dong.map((q) => co[q.ma]
        ? `<div class="quyen__o" title="Mã: ${esc(q.ma)}"><span class="nsv-ky nsv-ky--co">✓</span>
            <span>${esc(q.nhan)}</span>${nsvTheNhayCam(q.ma)}<small>${esc(co[q.ma].join(", "))}</small></div>`
        : `<div class="quyen__o is-chua" title="Mã: ${esc(q.ma)}"><span class="nsv-ky">–</span>
            <span>${esc(q.nhan)}</span><small>chưa cấp</small></div>`).join("")}
    </details>`;
  }).join("");
  return `<div class="nsv-xq" data-nsv-xem-quyen>
    <div class="nsv-xq__dau">
      <span><b>${tong}</b> quyền hiệu lực${(d.vai_tro || []).length ? ` · từ ${esc(d.vai_tro.join(", "))}` : ""}</span>
      <label class="nsv-bat"><input type="checkbox" data-nsv-hien-ca${hienCa ? " checked" : ""}>
        Hiển thị cả quyền chưa cấp</label>
    </div>
    ${nhom || '<p class="empty">Chưa được cấp quyền nào. Người này đăng nhập được nhưng mọi màn đều trống.</p>'}
    ${(d.vai_tro_ngung || []).length ? `<p class="panel__note">Vai trò đã ngừng dùng (không cấp gì): ${esc(d.vai_tro_ngung.join(", "))}</p>` : ""}
  </div>`;
}

/* ---------------- dùng chung: ngăn kéo chi tiết (UX-13-01) ---------------- */

/* Sửa người, sửa vai trò, xem chi tiết mở trong NGĂN KÉO bên phải thay vì
 * chèn form vào giữa danh sách: chèn giữa danh sách là cả trang nhảy, và
 * form dài đẩy danh sách đi mất — người ta sửa mà không còn thấy mình đang
 * sửa ai. Ngăn kéo nằm TRONG tab (bộ bắt sự kiện của tab bắt được nút
 * trong nó), `position: fixed` nên vẫn phủ cả màn hình. */
function nsvKhungNgan() {
  return `<div class="nsv-ngan" data-nsv-ngan hidden role="dialog" aria-modal="true">
    <div class="nsv-ngan__nen" data-nsv-ngan-dong></div>
    <aside class="nsv-ngan__than">
      <header class="nsv-ngan__dau"><h2 data-nsv-ngan-ten></h2>
        <button type="button" class="btn btn--sm btn--ghost" data-nsv-ngan-dong aria-label="Đóng">Đóng</button></header>
      <div class="nsv-ngan__noi" data-nsv-ngan-noi></div>
    </aside>
  </div>`;
}

function nsvMoNgan(el, tieuDe, html) {
  const n = el.querySelector("[data-nsv-ngan]");
  n.querySelector("[data-nsv-ngan-ten]").textContent = tieuDe;
  n.querySelector("[data-nsv-ngan-noi]").innerHTML = html;
  n.hidden = false;
  document.body.classList.add("is-ngan-mo");
  setTimeout(() => {
    const dau = n.querySelector("[data-nsv-ngan-noi] input:not([disabled]), [data-nsv-ngan-noi] select");
    (dau || n.querySelector("[data-nsv-ngan-dong].btn")).focus();
  }, 0);
}

function nsvDongNgan(n) {
  if (!n || n.hidden) return;
  n.hidden = true;
  n.querySelector("[data-nsv-ngan-noi]").innerHTML = "";
  if (!$$("[data-nsv-ngan]").some((x) => !x.hidden)) document.body.classList.remove("is-ngan-mo");
}

document.addEventListener("click", (e) => {
  const d = e.target.closest("[data-nsv-ngan-dong]");
  if (d) nsvDongNgan(d.closest("[data-nsv-ngan]"));
});
// Bắt ở pha CAPTURE: hộp hỏi (hoiHop) đang mở thì Esc là của nó — chạy sau
// nó là Esc đóng cả hộp lẫn ngăn kéo, mất form đang sửa dở.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || hoiDangMo) return;
  $$("[data-nsv-ngan]").filter((x) => !x.hidden).forEach(nsvDongNgan);
}, true);

/* ---------------- dùng chung: lịch sử ---------------- */

function nsvPill(ds, dau, lop) {
  return (ds || []).map((x) =>
    `<span class="pill${lop ? " " + lop : ""}">${dau} ${esc(nsvNhanQuyen(x))}</span>`).join(" ");
}

function nsvDongLichSu(d) {
  const ct = d.chi_tiet || {};
  const doiTuong = ct.ten || ct.ten_dang_nhap || ct.ten_moi || "";
  const truoc = ct.truoc || {};
  const sau = ct.sau || {};
  let them = "";
  if (d.loai === "nguoi_dung.vai_tro") {
    // Vai trò thêm/bớt, rồi QUYỀN HIỆU LỰC được/mất — vai trò khác cũng cấp
    // thì không tính là mất (mục 13.6).
    them = [nsvPill(ct.them, "+ vai trò", ""), nsvPill(ct.bot, "− vai trò", "pill--warn"),
            nsvPill(ct.quyen_them, "+", ""), nsvPill(ct.quyen_bot, "−", "pill--warn")]
      .filter(Boolean).join(" ");
  } else if (d.loai === "nguoi_dung.sua") {
    them = ["ho_ten", "email"].filter((k) => truoc[k] !== sau[k]).map((k) =>
      `<span class="pill">${k === "ho_ten" ? "Họ tên" : "Email"}: ${esc(truoc[k] || "—")} → ${esc(sau[k] || "—")}</span>`).join(" ");
  } else if (d.loai === "auth.khoa_nguoi_dung") {
    them = `<span class="pill${sau.khoa ? " pill--warn" : ""}">${sau.khoa ? "Khoá" : "Mở khoá"}</span>`
      + (ct.de_lai_viec ? ` <span class="pill pill--warn">để lại ${ct.de_lai_viec.so_hoi_thoai} hội thoại, ${ct.de_lai_viec.so_cong_viec} việc</span>` : "")
      + (ct.vai_tro_nhay_cam ? ` <span class="pill pill--halt">mở kèm quyền nhạy cảm: ${esc(Object.keys(ct.vai_tro_nhay_cam).join(", "))}</span>` : "");
  } else if (d.loai === "nguoi_dung.chuyen_viec") {
    them = `<span class="pill">${ct.so_hoi_thoai || 0} hội thoại, ${ct.so_cong_viec || 0} việc → ${esc(sau.nguoi || "")}</span>`
      + (ct.khong_chuyen_duoc ? ` <span class="pill pill--warn">${ct.khong_chuyen_duoc} hội thoại không chuyển được</span>` : "");
  } else if (d.loai === "nguoi_dung.dat_lai_mat_khau") {
    // Không bao giờ có mật khẩu ở đây — máy chủ không ghi nó (có test canh).
    them = `<span class="pill pill--warn">${ct.tu_sinh ? "hệ thống tạo mật khẩu tạm" : "quản trị tự đặt mật khẩu tạm"}</span>`
      + ` <span class="pill">đăng xuất ${ct.so_phien_thu_hoi || 0} phiên</span>`
      + ' <span class="pill">phải đổi ở lần đăng nhập tới</span>';
  } else {
    if (truoc.ten && sau.ten && truoc.ten !== sau.ten) {
      them += `<span class="pill">Tên: ${esc(truoc.ten)} → ${esc(sau.ten)}</span> `;
    }
    them += [nsvPill(ct.them, "+", ""), nsvPill(ct.bot, "−", "pill--warn")].filter(Boolean).join(" ");
    if (sau.phai_doi_mat_khau) them += ' <span class="pill">phải đổi mật khẩu lần đầu</span>';
    if (ct.nguoi_anh_huong && ct.nguoi_anh_huong.length) {
      them += ` <span class="pill">ảnh hưởng: ${esc(ct.nguoi_anh_huong.join(", "))}</span>`;
    } else if (ct.so_nguoi_anh_huong) {
      them += ` <span class="pill">${ct.so_nguoi_anh_huong} người đang mang</span>`;
    }
  }
  return `<div class="row">
    <span class="row__flag row__flag--${(ct.bot || []).length || sau.khoa ? "assist" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(d.nhan)}${doiTuong ? ": " + esc(doiTuong) : ""}</b>
      <span class="row__sub">bởi ${esc(d.nguoi_lam)} · ${nsvNgay(d.luc)}</span>
      ${them ? `<div class="nsv-doi">${them}</div>` : ""}
    </div>
  </div>`;
}

async function nsvVeLichSu(el, loai = "tat_ca", refId = "", gioiHan = 60) {
  if (!el) return;
  try {
    const d = await api(`/nhan-su/lich-su?loai=${encodeURIComponent(loai)}&limit=${gioiHan}`
      + (refId ? `&ref_id=${encodeURIComponent(refId)}` : ""));
    el.innerHTML = d.lich_su.length
      ? d.lich_su.map(nsvDongLichSu).join("")
      : '<p class="empty">Chưa có thay đổi nào về nhân sự hay phân quyền.</p>';
  } catch (err) {
    el.innerHTML = `<p class="empty">Không tải được lịch sử: ${esc(err.message)}</p>`;
  }
}

/* ---------------- dùng chung: chuyển việc, khoá, mở khoá (mục 13.8, UX-13-05) ---------------- */

function nsvLietKeViec(viec) {
  const ht = viec.hoi_thoai.slice(0, 5).map((h) => `Hội thoại với ${h.khach || "khách"}${h.kenh ? " · " + h.kenh : ""}`);
  const cv = viec.cong_viec.slice(0, 5).map((v) => `Việc “${v.tieu_de}”${v.han ? " · hạn " + nsvNgay(v.han) : ""}`);
  const con = viec.tong - ht.length - cv.length;
  return [...ht, ...cv, ...(con > 0 ? [`… và ${con} mục khác`] : [])];
}

function nsvNguoiNhanViec(n) {
  return nsv.nguoi.filter((x) => !x.khoa && x.id !== n.id).map((x) => ({
    value: x.id, label: `Chuyển cho ${x.ho_ten || x.ten_dang_nhap} (${x.ten_dang_nhap})` }));
}

async function nsvChuyenViecThat(n, viec, nguoiNhan) {
  try {
    const kq = await api(`/nguoi-dung/${n.id}/chuyen-viec`, {
      method: "POST",
      body: JSON.stringify({
        nguoi_nhan: nguoiNhan,
        hoi_thoai: viec.so_hoi_thoai > 0,
        cong_viec: viec.so_cong_viec > 0,
      }),
    });
    toast(`Đã chuyển ${kq.so_hoi_thoai} hội thoại và ${kq.so_cong_viec} việc cho ${kq.nguoi_nhan}.`);
    return kq;
  } catch (err) {
    toast(err.message, true);
    return null;
  }
}

/* Chuyển việc KHÔNG kèm khoá (nút "Chuyển việc"). Khi khoá thì nsvKhoa tự hỏi
   chuyển việc trong CÙNG hộp xác nhận khoá — không còn hai hộp nối nhau. */
async function nsvHoiChuyenViec(n, viec) {
  if (!nsv.nguoi.length) await nsvTaiDuLieu();
  const ten = n.ho_ten || n.ten_dang_nhap;
  const nhan = nsvNguoiNhanViec(n);
  if (!nhan.length) { toast("Không còn ai đang làm để nhận việc.", true); return null; }
  const d = await hoiHop({
    tieu_de: `Chuyển việc của ${ten}`,
    phu: `${ten} đang giữ ${viec.so_hoi_thoai} hội thoại và ${viec.so_cong_viec} việc chưa xong.`,
    canh_bao: { tieu_de: "Sẽ chuyển:", muc: nsvLietKeViec(viec) },
    truong: [{ name: "nguoi_nhan", label: "Chuyển cho", type: "select", required: true,
               value: nhan[0].value, options: nhan }],
    nut: "Chuyển việc",
  });
  if (!d || !d.nguoi_nhan) return null;
  return nsvChuyenViecThat(n, viec, d.nguoi_nhan);
}

/* Khoá / mở khoá. Khoá thì hỏi về VIỆC ĐANG GIỮ ngay trong hộp xác nhận —
 * máy chủ cũng chặn (409 `can_chuyen_viec`) nên gọi thẳng API hay màn cũ
 * đều gặp cùng câu hỏi. Một hộp nói đủ: điều sẽ xảy ra, việc nào đang treo,
 * chuyển cho ai. Trước đây là hộp chuyển việc rồi thêm một confirm() nữa. */
async function nsvKhoa(n, xong) {
  if (n.khoa) return nsvMoKhoa(n, xong);
  const ten = n.ten_dang_nhap;
  const hoTen = n.ho_ten || ten;
  if (!nsv.nguoi.length) await nsvTaiDuLieu();
  let viec;
  try { viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`); } catch (err) { toast(err.message, true); return; }
  const nhan = nsvNguoiNhanViec(n);
  const d = await hoiHop({
    tieu_de: `Khoá tài khoản ${hoTen}?`,
    phu: `${ten}${n.email ? " · " + n.email : ""}`,
    anh_huong: ["Mọi phiên đang mở của họ bị đăng xuất ngay lập tức.",
                "Họ không đăng nhập được cho tới khi được mở khoá.",
                "Tài khoản, vai trò và lịch sử giữ nguyên — không xoá gì."],
    canh_bao: viec.tong ? {
      tieu_de: `${hoTen} đang giữ ${viec.so_hoi_thoai} hội thoại và ${viec.so_cong_viec} việc chưa xong — `
        + "khoá mà không chuyển là khách của họ chờ mà không ai trả lời:",
      muc: nsvLietKeViec(viec) } : null,
    truong: viec.tong ? [{
      name: "nguoi_nhan", label: "Việc đang giữ", type: "select", required: true,
      value: nhan.length ? nhan[0].value : "__de_lai__",
      options: [...nhan, { value: "__de_lai__", label: "Không chuyển — khoá và để lại việc (khách có thể phải chờ)" }],
    }] : [],
    nut: viec.tong ? "Xác nhận khoá" : "Khoá tài khoản",
    nguy_hiem: true,
  });
  if (!d) return;
  let boQua = false;
  if (viec.tong && d.nguoi_nhan === "__de_lai__") {
    boQua = true;
  } else if (viec.tong) {
    const kq = await nsvChuyenViecThat(n, viec, d.nguoi_nhan);
    if (!kq) { if (xong) await xong(); return; }
    if (kq.khong_chuyen_duoc && kq.khong_chuyen_duoc.length) {
      // Kết quả MỚI từ máy chủ (luật giao từ chối vài hội thoại) — chỉ hỏi
      // lại khi thật sự có chuyện, và nói rõ từng hội thoại vì sao.
      const tiep = await hoiHop({
        tieu_de: `${kq.khong_chuyen_duoc.length} hội thoại KHÔNG chuyển được`,
        canh_bao: { tieu_de: `Các hội thoại này vẫn nằm ở ${hoTen}:`,
                    muc: kq.khong_chuyen_duoc.map((x) => `${x.khach || "khách"}: ${x.ly_do}`) },
        anh_huong: ["Khoá ngay và để lại các hội thoại ấy — giao lại bằng tay ở màn Hội thoại."],
        nut: "Vẫn khoá", nguy_hiem: true,
      });
      if (!tiep) { if (xong) await xong(); return; }
      boQua = true;
    }
  }
  try {
    await api(`/nguoi-dung/${encodeURIComponent(ten)}/khoa?khoa=true${boQua ? "&bo_qua_viec=true" : ""}`,
              { method: "POST" });
    toast(`Đã khoá ${ten} và đăng xuất mọi phiên.`);
  } catch (err) {
    toast(err.message, true);
    // Ai đó vừa giao thêm việc cho người này giữa lúc đang hỏi: hỏi lại.
    if (err.chi_tiet && err.chi_tiet.can_chuyen_viec) return nsvKhoa(n, xong);
  }
  if (xong) await xong();
}

/* Mở khoá (SEC-13-01). Tài khoản mang vai trò có quyền nhạy cảm — "Quản trị"
 * là ví dụ đo được trên dữ liệu thật — thì hộp nói rõ VAI TRÒ NÀO, QUYỀN
 * GÌ, và bắt gõ lại tên đăng nhập: mở khoá như thế là trao lại các quyền ấy
 * ngay lập tức. Máy chủ cũng chặn (409 `can_xac_nhan_nhay_cam`). */
function nsvHoiMoKhoa(n, nc) {
  const hoTen = n.ho_ten || n.ten_dang_nhap;
  const ds = Object.entries(nc || {});
  const soNc = Object.keys(nsv.nhayCam).length;
  return hoiHop({
    tieu_de: `Mở khoá ${hoTen}?`,
    phu: `${n.ten_dang_nhap}${(n.vai_tro_ten || []).length ? " · vai trò: " + n.vai_tro_ten.join(", ") : ""}`,
    anh_huong: ["Họ đăng nhập lại được ngay bằng mật khẩu hiện có.",
                "Mọi quyền của các vai trò họ đang mang có hiệu lực lại ngay."],
    canh_bao: ds.length ? {
      tieu_de: "Tài khoản này đang mang vai trò có QUYỀN NHẠY CẢM — mở khoá là trao lại các quyền ấy ngay:",
      muc: [...ds.map(([v, q]) => `${v}: ${soNc && q.length >= soNc
        ? "toàn bộ quyền nhạy cảm (cấp quyền, cấu hình AI, xoá dữ liệu khách…)"
        : q.map(nsvNhanQuyen).join("; ")}`),
            "Tài khoản chỉ cần xem? Bấm Quay lại, Sửa và gỡ vai trò thừa TRƯỚC khi mở khoá."],
    } : null,
    go_xac_nhan: ds.length ? n.ten_dang_nhap : "",
    nut: ds.length ? "Vẫn mở khoá" : "Mở khoá",
    nguy_hiem: ds.length > 0,
  });
}

async function nsvMoKhoa(n, xong) {
  const ten = n.ten_dang_nhap;
  const goi = (xacNhan) => api(`/nguoi-dung/${encodeURIComponent(ten)}/khoa?khoa=false`
    + (xacNhan ? "&xac_nhan_nhay_cam=true" : ""), { method: "POST" });
  const nc = nsvVaiNhayCam(n);
  if (!(await nsvHoiMoKhoa(n, nc))) return;
  try {
    await goi(Object.keys(nc).length > 0);
    toast(`Đã mở khoá ${ten}.`);
  } catch (err) {
    // Máy chủ thấy vai trò nhạy cảm mà danh sách trên màn hình chưa có (ai
    // đó vừa gán): hỏi lại theo danh sách CỦA MÁY CHỦ, không tự xác nhận hộ.
    if (err.chi_tiet && err.chi_tiet.can_xac_nhan_nhay_cam) {
      if (await nsvHoiMoKhoa(n, err.chi_tiet.vai_tro || {})) {
        try { await goi(true); toast(`Đã mở khoá ${ten}.`); } catch (e2) { toast(e2.message, true); }
      }
    } else {
      toast(err.message, true);
    }
  }
  if (xong) await xong();
}

/* ---------------- dùng chung: đặt lại mật khẩu (UX-13-07) ---------------- */

/* Quản trị KHÔNG cần biết mật khẩu mới: để trống thì máy chủ tạo, hiện MỘT
 * lần trong hộp này rồi xoá khỏi trang (hoiDong dọn #hoiKhoi). Người nhận
 * bị bắt đổi ngay lần đăng nhập tới — mật khẩu tạm là thứ người khác biết. */
async function nsvDatLaiMatKhau(n, xong) {
  const ten = n.ten_dang_nhap;
  const d = await hoiHop({
    tieu_de: `Đặt lại mật khẩu cho ${n.ho_ten || ten}?`,
    phu: ten,
    anh_huong: ["Mật khẩu hiện tại của họ thôi dùng được ngay.",
                "Mọi thiết bị đang đăng nhập bằng tài khoản này bị đăng xuất.",
                "Lần đăng nhập tới, họ phải đặt mật khẩu mới trước khi dùng dashboard.",
                "Lịch sử ghi ai đặt lại và lúc nào — không ghi mật khẩu."],
    truong: [{ name: "mat_khau_tam", type: "password", label: "Mật khẩu tạm",
               hint: "để trống để hệ thống tự tạo (khuyên dùng)", minlength: 8, maxlength: 200 }],
    nut: "Đặt lại mật khẩu", nguy_hiem: true,
  });
  if (!d) return;
  let kq;
  try {
    kq = await api(`/nguoi-dung/${n.id}/dat-lai-mat-khau`, {
      method: "POST", body: JSON.stringify({ mat_khau_tam: d.mat_khau_tam || null }),
    });
  } catch (err) { toast(err.message, true); return; }
  await hoiHop({
    tieu_de: kq.mat_khau_tam ? `Mật khẩu tạm của ${ten}` : `Đã đặt lại mật khẩu cho ${ten}`,
    phu: kq.mat_khau_tam ? "Chỉ hiện MỘT lần ở đây, không lưu ở đâu khác — chép lại ngay."
      : "Mật khẩu tạm là mật khẩu bạn vừa gõ.",
    bi_mat: kq.mat_khau_tam || "",
    anh_huong: [`Đã đăng xuất ${kq.so_phien_thu_hoi} phiên đang mở.`,
                "Báo mật khẩu cho họ qua kênh riêng (gặp trực tiếp, gọi điện) — không gửi vào nhóm chat chung.",
                `Họ đăng nhập bằng “${ten}” và mật khẩu tạm, rồi đặt mật khẩu mới ngay.`],
    nut: "Tôi đã ghi lại", an_huy: true,
  });
  if (xong) await xong();
}
