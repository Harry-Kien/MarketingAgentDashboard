/* ======================== TAB "NHÂN VIÊN" (24-nhan-su.js giữ phần dùng chung) ========================
 *
 * Danh sách TÁCH khỏi việc tạo/sửa (UX-13-01): trang chỉ còn ô tìm + bộ lọc
 * + các dòng ngắn; thêm, sửa, xem chi tiết và quyền mở trong ngăn kéo bên
 * phải. Mỗi dòng: thông tin người ở trên, vai trò ở dưới, MỘT nút chính
 * (Chi tiết) và các thao tác còn lại trong menu "⋯" — 4 nút cùng 3 nhãn vai
 * trò trên một hàng là thứ đã đo được rớt dòng ở 375px (UX-13-06).
 */

const nsvLoc = { chu: "", vai: "", tt: "" };

/* Nhãn vai trò: vai trò cấp quyền nhạy cảm tô đỏ ngay trên dòng — quản trị
   lướt danh sách là thấy ai đang cầm chìa khoá gì, không phải mở từng người. */
function nsvNhanVai(n) {
  const nc = nsvVaiNhayCam(n);
  return (n.vai_tro_ten || []).map((t) => nc[t]
    ? `<span class="pill pill--halt" title="Cấp quyền nhạy cảm: ${esc(nc[t].map(nsvNhanQuyen).join("; "))}">${esc(t)}</span>`
    : `<span class="pill">${esc(t)}</span>`).join(" ")
    + (n.vai_tro_ngung || []).map((t) =>
      ` <span class="pill pill--warn" title="Vai trò đã ngừng dùng — không cấp quyền nào">${esc(t)} · ngừng dùng</span>`).join("")
    || '<span class="pill pill--warn">chưa có vai trò nào</span>';
}

/* Các thao tác trên một người — dùng cho cả menu "⋯" trên dòng lẫn hàng nút
   trong ngăn kéo chi tiết. `lop` là class của từng nút, `lopNguy` cho Khoá. */
function nsvNutThaoTac(n, lop, lopNguy) {
  if (!nsvCo("nguoi_dung.sua")) return "";
  const vuot = nsvVuotQuyen(n);
  const khoa = vuot.length ? ` disabled title="Người này có quyền bạn không có (${esc(vuot.slice(0, 4).map(nsvNhanQuyen).join("; "))}${vuot.length > 4 ? "…" : ""}) — chỉ người có đủ các quyền ấy mới làm được."` : "";
  const giu = Number(n.so_hoi_thoai_giu || 0) + Number(n.so_viec_chua_xong || 0);
  const minh = n.id === state.toiId;
  return `<button type="button" class="${lop}" data-nsv-sua="${esc(n.id)}"${khoa}>Sửa thông tin &amp; vai trò</button>
    ${giu ? `<button type="button" class="${lop}" data-nsv-chuyen="${esc(n.id)}"${khoa}>Chuyển việc đang giữ</button>` : ""}
    ${minh ? "" : `<button type="button" class="${lop}" data-nsv-dat-lai-mk="${esc(n.id)}"${khoa}>Đặt lại mật khẩu</button>`}
    ${minh ? "" : `<button type="button" class="${lopNguy}" data-nsv-khoa="${esc(n.id)}"${khoa}>${n.khoa ? "Mở khoá tài khoản" : "Khoá tài khoản"}</button>`}`;
}

function nsvMenuNguoi(n) {
  const nut = nsvNutThaoTac(n, "nsv-menu__muc", "nsv-menu__muc is-nguy");
  return nut ? `<details class="nsv-menu">
    <summary class="btn btn--sm btn--ghost" aria-label="Thao tác khác với ${esc(n.ten_dang_nhap)}">⋯</summary>
    <div class="nsv-menu__ds">${nut}</div>
  </details>` : "";
}

function nsvDongNguoi(n) {
  const giu = Number(n.so_hoi_thoai_giu || 0);
  const viec = Number(n.so_viec_chua_xong || 0);
  const ganViec = giu || viec
    ? ` <span class="pill${n.khoa ? " pill--warn" : ""}">giữ ${giu} hội thoại · ${viec} việc</span>` : "";
  return `<div class="row nsv-dong">
    <span class="row__flag row__flag--${n.khoa ? "halt" : (n.vai_tro_ten || []).length ? "auto" : "assist"}"></span>
    <div class="row__main">
      <div class="nsv-ten"><b>${esc(n.ho_ten || n.ten_dang_nhap)}</b>
        <span class="tag tag--${n.khoa ? "halt" : "auto"}">${n.khoa ? "Đã khoá" : "Đang làm"}</span></div>
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.email ? " · " + esc(n.email) : ""}
        · ${n.dang_nhap_cuoi ? "vào lần cuối " + nsvNgay(n.dang_nhap_cuoi) : "chưa đăng nhập lần nào"}</span>
      <div class="nsv-vai">${nsvNhanVai(n)}${ganViec}</div>
    </div>
    <div class="row__side">
      <span class="row__nut">
        <button type="button" class="btn btn--sm" data-nsv-chi-tiet="${esc(n.id)}">Chi tiết</button>
        ${nsvMenuNguoi(n)}
      </span>
    </div>
  </div>`;
}

/* ---------------- tìm và lọc (UX-13-03) ---------------- */

function nsvHopLoc(n) {
  if (nsvLoc.chu) {
    const k = nsvBoDau(nsvLoc.chu).trim();
    const chu = nsvBoDau([n.ho_ten, n.ten_dang_nhap, n.email, ...(n.vai_tro_ten || [])].join(" "));
    if (!chu.includes(k)) return false;
  }
  if (nsvLoc.vai === "__chua__" && (n.vai_tro_ten || []).length) return false;
  if (nsvLoc.vai && nsvLoc.vai !== "__chua__" && !(n.vai_tro_id || []).includes(nsvLoc.vai)) return false;
  if (nsvLoc.tt === "dang_lam" && n.khoa) return false;
  if (nsvLoc.tt === "khoa" && !n.khoa) return false;
  if (nsvLoc.tt === "giu_viec" && !(Number(n.so_hoi_thoai_giu || 0) + Number(n.so_viec_chua_xong || 0))) return false;
  if (nsvLoc.tt === "nhay_cam" && !Object.keys(nsvVaiNhayCam(n)).length) return false;
  return true;
}

function nsvVeDs(el) {
  const ds = nsv.nguoi.filter(nsvHopLoc);
  const loc = nsvLoc.chu || nsvLoc.vai || nsvLoc.tt;
  el.querySelector("[data-nsv-ket-qua]").textContent = loc ? `${ds.length}/${nsv.nguoi.length} người` : "";
  el.querySelector("[data-nsv-ds]").innerHTML = ds.length ? ds.map(nsvDongNguoi).join("")
    : nsv.nguoi.length ? '<p class="empty">Không ai khớp bộ lọc.</p>' : '<p class="empty">Chưa có nhân viên nào.</p>';
}

/* ---------------- form thêm / sửa (UX-13-04) ---------------- */

/* Tóm tắt QUYỀN HIỆU LỰC của các vai trò đang tick, vẽ lại mỗi lần tick.
 * Trước đây chỉ có ô tick tên vai trò: tick nhầm "Quản trị" là trao toàn
 * quyền mà màn hình không nói gì. */
function nsvTomTatVai(ids) {
  const vai = ids.map((id) => nsv.vaiTro.find((v) => v.id === id)).filter(Boolean);
  if (!vai.length) {
    return `<div class="nsv-tt-quyen is-trong"><b>Chưa chọn vai trò nào</b> — tài khoản đăng nhập
      được nhưng mọi màn đều trống.</div>`;
  }
  const dung = vai.filter((v) => v.dang_dung !== false);
  const co = new Set(dung.flatMap(nsvQuyenCuaVai));
  const nc = [...co].filter(nsvLaNhayCam);
  const qt = dung.filter((v) => v.toan_quyen);
  const nhom = nsv.nhom.map((g) => {
    const k = g.quyen.filter((q) => co.has(q.ma)).length;
    return k ? `<span class="nsv-chip">${esc(g.ten)} <b>${k}/${g.quyen.length}</b></span>` : "";
  }).join("");
  return `<div class="nsv-tt-quyen">
    <div><b>Quyền hiệu lực: ${co.size}</b> · từ ${dung.map((v) => esc(v.ten)).join(" + ") || "—"}</div>
    ${qt.length ? `<div class="nsv-canh" role="alert"><b>“${esc(qt[0].ten)}” cấp TOÀN BỘ quyền</b> — kể
      cả cấp quyền cho người khác, đổi cấu hình AI và xoá vĩnh viễn dữ liệu khách. Chỉ gán cho
      người chịu trách nhiệm cả hệ thống.</div>`
    : nc.length ? `<div class="nsv-canh" role="alert"><b>${nc.length} quyền nhạy cảm:</b><ul>${
      nc.map((m) => `<li>${esc(nsvNhanQuyen(m))} — ${esc(nsv.nhayCam[m])}</li>`).join("")}</ul></div>` : ""}
    <div class="nsv-tt-quyen__nhom">${nhom}</div>
  </div>`;
}

/* MỘT form cho cả thêm và sửa, vai trò là ô TICK (một người nhiều vai trò).
   Vai trò đã ngừng dùng: người đang mang thì vẫn hiện đã tick (gỡ được),
   người chưa mang thì khoá — máy chủ cũng từ chối gán mới. Vai trò mạnh hơn
   người thao tác cũng khoá sẵn, kèm lý do (`chan_cap_vuot`). */
function nsvFormNguoi(n) {
  const moi = !n;
  const dangCo = new Set(n ? n.vai_tro_id || [] : []);
  const vaiO = nsv.vaiTro.map((v) => {
    const vuot = state.toiQuyen ? nsvQuyenCuaVai(v).filter((q) => !state.toiQuyen.has(q)) : [];
    const khoa = !dangCo.has(v.id) && (v.dang_dung === false || vuot.length);
    const nc = nsvQuyenCuaVai(v).filter(nsvLaNhayCam).length;
    return `<label class="quyen__o${nc ? " is-nhay-cam" : ""}">
      <input type="checkbox" name="vai_tro" value="${esc(v.id)}"${dangCo.has(v.id) ? " checked" : ""}${khoa ? " disabled" : ""}>
      <span>${esc(v.ten)}${v.dang_dung === false ? " · ngừng dùng" : ""}</span>
      ${v.toan_quyen ? '<span class="pill pill--halt">toàn quyền</span>' : nc ? `<span class="pill pill--halt">${nc} nhạy cảm</span>` : ""}
      <small>${vuot.length && !dangCo.has(v.id) ? "vượt quyền của bạn — không gán được" : esc(v.mo_ta || "")}</small></label>`;
  }).join("");
  return `<form class="form nsv-form" data-nsv-form-nguoi="${moi ? "" : esc(n.id)}">
    <div class="form__row">
      ${moi ? `<label class="field"><span>Tên đăng nhập</span>
        <input name="ten_dang_nhap" required minlength="3" maxlength="64" autocomplete="off" placeholder="lan.nv"></label>`
        : `<label class="field"><span>Tên đăng nhập <em class="hint">không đổi được — nhật ký cũ trỏ vào nó</em></span>
        <input value="${esc(n.ten_dang_nhap)}" disabled></label>`}
      <label class="field"><span>Họ tên</span>
        <input name="ho_ten" required maxlength="120" value="${esc(n ? n.ho_ten : "")}" autocomplete="off"></label>
    </div>
    <div class="form__row">
      <label class="field"><span>Email <em class="hint">không bắt buộc</em></span>
        <input name="email" type="email" maxlength="200" value="${esc(n ? n.email || "" : "")}" autocomplete="off"></label>
      ${moi ? `<label class="field"><span>Mật khẩu ban đầu</span>
        <input name="mat_khau" type="password" autocomplete="new-password" minlength="8" required></label>` : ""}
    </div>
    ${moi ? `<label class="quyen__o"><input type="checkbox" name="phai_doi_mat_khau" value="1" checked>
      <span>Bắt đổi mật khẩu ở lần đăng nhập đầu</span>
      <small>mật khẩu ban đầu là thứ bạn biết — bỏ tick chỉ khi họ tự gõ nó ngay trước mặt bạn</small></label>` : ""}
    <fieldset class="quyen__nhom"><legend>Vai trò <em class="hint">quyền = hợp quyền mọi vai trò đang dùng</em></legend>
      ${vaiO}
    </fieldset>
    <div data-nsv-tom-tat>${nsvTomTatVai([...dangCo])}</div>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">${moi ? "Tạo tài khoản" : "Lưu"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-ngan-dong>Huỷ</button>
    </div>
  </form>`;
}

/* Lưu mà THÊM vai trò cấp quyền nhạy cảm (so với trước) thì hỏi một lần nữa,
   nói rõ quyền gì. Bản tóm tắt ở trên là để đọc; hộp này là để dừng tay. */
async function nsvXacNhanVaiNhayCam(cu, moi, ten) {
  const quyenCu = new Set(cu.map((id) => nsv.vaiTro.find((v) => v.id === id)).flatMap(nsvQuyenCuaVai));
  const them = moi.map((id) => nsv.vaiTro.find((v) => v.id === id)).filter((v) => v && !cu.includes(v.id));
  const muc = them.map((v) => [v, nsvQuyenCuaVai(v).filter((q) => nsvLaNhayCam(q) && !quyenCu.has(q))])
    .filter(([, q]) => q.length)
    .map(([v, q]) => `${v.ten}: ${v.toan_quyen ? "TOÀN BỘ quyền của hệ thống" : q.map(nsvNhanQuyen).join("; ")}`);
  if (!muc.length) return true;
  return !!(await hoiHop({
    tieu_de: `Cấp quyền nhạy cảm cho ${ten}?`,
    canh_bao: { tieu_de: "Vai trò vừa thêm cấp các quyền nhạy cảm sau, có hiệu lực ngay ở thao tác kế tiếp của họ:", muc },
    anh_huong: ["Thay đổi được ghi vào Lịch sử nhân sự & phân quyền, kèm tên bạn."],
    nut: "Vẫn cấp", nguy_hiem: true,
  }));
}

async function nsvLuuNguoi(f) {
  const id = f.dataset.nsvFormNguoi;
  const d = Object.fromEntries(new FormData(f).entries());
  const vai = $$('input[name="vai_tro"]:checked', f).map((i) => i.value);
  const cu = id ? (nsv.nguoi.find((x) => x.id === id) || {}).vai_tro_id || [] : [];
  const ten = String(d.ho_ten || d.ten_dang_nhap || "người này").trim();
  if (!(await nsvXacNhanVaiNhayCam(cu, vai, ten))) return null;
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    if (!id) {
      const kq = await api("/nguoi-dung", {
        method: "POST",
        body: JSON.stringify({
          ten_dang_nhap: String(d.ten_dang_nhap || "").trim(),
          mat_khau: d.mat_khau, ho_ten: String(d.ho_ten || "").trim(),
          email: String(d.email || "").trim() || null, vai_tro_ids: vai,
          phai_doi_mat_khau: !!d.phai_doi_mat_khau,
        }),
      });
      toast(`Đã tạo tài khoản ${kq.ten_dang_nhap}.`);
      return { taoMoi: kq };
    }
    await api(`/nguoi-dung/${id}`, {
      method: "PUT",
      body: JSON.stringify({ ho_ten: String(d.ho_ten || "").trim(),
                             email: String(d.email || "").trim() || null }),
    });
    if ([...cu].sort().join() !== [...vai].sort().join()) {
      await api(`/nguoi-dung/${id}/vai-tro`, { method: "PUT", body: JSON.stringify({ vai_tro: vai }) });
    }
    toast("Đã lưu.");
    return {};
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
    return null;
  }
}

/* Hướng dẫn bàn giao sau khi tạo (UX-13-07, MD-UX-13-05): nằm YÊN tới khi
   người tạo bấm Đóng. Toast 4 giây cũ biến mất trước khi kịp đọc — và
   "chưa có vai trò nên mọi màn đều trống" là câu không được phép lỡ. */
function nsvBanGiao(kq) {
  const vai = kq.vai_tro_ten || [];
  return `<div class="nsv-ban-giao" role="status">
    <div class="nsv-ban-giao__dau"><b>Đã tạo tài khoản ${esc(kq.ten_dang_nhap)} — việc cần làm để bàn giao</b>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-dong-ban-giao>Đóng</button></div>
    <ol>
      <li>Báo tên đăng nhập <code>${esc(kq.ten_dang_nhap)}</code> và mật khẩu ban đầu cho
        ${esc(kq.ho_ten || kq.ten_dang_nhap)} qua kênh riêng (gặp trực tiếp, gọi điện) — không gửi vào nhóm chat chung.</li>
      <li>${kq.phai_doi_mat_khau ? "Lần đăng nhập đầu, họ sẽ phải đặt mật khẩu mới trước khi dùng dashboard."
        : "Nhắc họ đổi mật khẩu ngay lần đầu vào (mục “đổi mật khẩu” dưới tên họ ở thanh bên)."}</li>
      <li>${vai.length ? `Vai trò: <b>${esc(vai.join(", "))}</b>.`
        : "<b>Chưa có vai trò</b>: họ đăng nhập được nhưng mọi màn đều trống — mở Sửa để gán."}</li>
      <li>Cần trả lời khách thì họ phải là thành viên kênh — kiểm ở Cấu hình chung → Kết nối.</li>
    </ol>
  </div>`;
}

/* ---------------- chi tiết một người (UX-13-01/02) ---------------- */

async function nsvChiTiet(el, n) {
  let q;
  try { q = await api(`/nguoi-dung/${n.id}/quyen`); } catch (err) { toast(err.message, true); return; }
  const tt = [
    ["Tên đăng nhập", n.ten_dang_nhap], ["Email", n.email || "—"],
    ["Trạng thái", n.khoa ? "Đã khoá" : "Đang làm"], ["Tạo lúc", nsvNgay(n.tao_luc)],
    ["Vào lần cuối", n.dang_nhap_cuoi ? nsvNgay(n.dang_nhap_cuoi) : "chưa đăng nhập lần nào"],
    ["Kênh", `${n.so_kenh || 0} kênh · đọc SĐT/email khách ở ${n.so_kenh_pii || 0} kênh`],
    ["Đang giữ", `${n.so_hoi_thoai_giu || 0} hội thoại · ${n.so_viec_chua_xong || 0} việc chưa xong`],
  ];
  nsvMoNgan(el, n.ho_ten || n.ten_dang_nhap, `<div class="nsv-ct">
    <dl class="nsv-tt">${tt.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
    <h3 class="nsv-ct__muc">Vai trò</h3>
    <div class="nsv-vai">${nsvNhanVai(n)}</div>
    ${nsvCo("nguoi_dung.sua") ? `<div class="row__nut nsv-ct__nut">${
      nsvNutThaoTac(n, "btn btn--sm btn--ghost", "btn btn--sm btn--halt")}</div>` : ""}
    <h3 class="nsv-ct__muc">Quyền hiệu lực</h3>
    ${nsvVeQuyenNguoi(q)}
    <h3 class="nsv-ct__muc">Lịch sử gần đây</h3>
    <div class="rows" data-nsv-ls-nguoi><p class="empty">Đang tải…</p></div>
  </div>`);
  nsvVeLichSu(el.querySelector("[data-nsv-ls-nguoi]"), "tat_ca", n.id, 10);
}

async function nsvVeNhanVien(el) {
  await nsvTaiDuLieu();
  // Hiện nút theo quyền ở MỖI lần vẽ, không lúc gắn: tab mở thẳng từ địa chỉ
  // có thể gắn trước khi biết quyền, và nút ẩn từ lúc ấy thì ẩn mãi.
  el.querySelector("[data-nsv-them]").hidden = !nsvCo("nguoi_dung.sua");
  const ds = nsv.nguoi;
  const dangLam = ds.filter((n) => !n.khoa).length;
  const chuaVai = ds.filter((n) => !(n.vai_tro_ten || []).length).length;
  el.querySelector("[data-nsv-dem]").textContent = [`${ds.length} tài khoản`, `${dangLam} đang làm`,
    ds.length - dangLam ? `${ds.length - dangLam} đã khoá` : "",
    chuaVai ? `${chuaVai} chưa có vai trò` : ""].filter(Boolean).join(" · ");
  const sel = el.querySelector("[data-nsv-loc-vai]");
  sel.innerHTML = '<option value="">Mọi vai trò</option>'
    + nsv.vaiTro.map((v) => `<option value="${esc(v.id)}">${esc(v.ten)}${v.dang_dung === false ? " (ngừng dùng)" : ""}</option>`).join("")
    + '<option value="__chua__">Chưa có vai trò</option>';
  sel.value = nsvLoc.vai;
  if (sel.value !== nsvLoc.vai) nsvLoc.vai = "";
  nsvVeDs(el);
}

GAN_TAB["ns-nhan-vien"] = async (el) => {
  el.innerHTML = `<section class="panel nsv-panel">
    <div class="nsv-dau">
      <h2 class="panel__head">Nhân viên</h2>
      <button type="button" class="btn btn--sm btn--primary" data-nsv-them hidden>Thêm nhân viên</button>
    </div>
    <p class="panel__note nsv-ghi" data-nsv-dem>đang tải…</p>
    <div data-nsv-ban-giao></div>
    <div class="nsv-loc" role="search">
      <input type="search" class="nsv-tim" data-nsv-tim-nguoi autocomplete="off"
             placeholder="Tìm tên, email, tên đăng nhập, vai trò…" aria-label="Tìm nhân viên">
      <select data-nsv-loc-vai aria-label="Lọc theo vai trò"></select>
      <select data-nsv-loc-tt aria-label="Lọc theo trạng thái">
        <option value="">Mọi trạng thái</option><option value="dang_lam">Đang làm</option>
        <option value="khoa">Đã khoá</option><option value="giu_viec">Đang giữ việc</option>
        <option value="nhay_cam">Có quyền nhạy cảm</option>
      </select>
      <span class="nsv-loc__dem" data-nsv-ket-qua></span>
    </div>
    <div class="rows" data-nsv-ds><p class="empty">Đang tải…</p></div>
  </section>${nsvKhungNgan()}`;
  const veLai = () => nsvVeNhanVien(el).catch((err) => toast(err.message, true));
  const theoId = (id) => nsv.nguoi.find((x) => x.id === id);
  const ngan = el.querySelector("[data-nsv-ngan]");
  el.addEventListener("click", async (e) => {
    const tim = (k) => e.target.closest(`[${k}]`);
    // Bấm bất cứ đâu NGOÀI nút "⋯" của một menu (kể cả chọn một mục trong
    // nó) là đóng menu ấy; bấm đúng nút "⋯" thì để <details> tự bật/tắt.
    $$("details.nsv-menu[open]", el).forEach((m) => {
      if (!m.querySelector("summary").contains(e.target)) m.open = false;
    });
    if (tim("data-nsv-them")) {
      nsvMoNgan(el, "Thêm nhân viên", nsvFormNguoi(null));
    } else if (tim("data-nsv-chi-tiet")) {
      await nsvChiTiet(el, theoId(tim("data-nsv-chi-tiet").dataset.nsvChiTiet));
    } else if (tim("data-nsv-sua")) {
      const n = theoId(tim("data-nsv-sua").dataset.nsvSua);
      nsvMoNgan(el, `Sửa ${n.ho_ten || n.ten_dang_nhap}`, nsvFormNguoi(n));
    } else if (tim("data-nsv-khoa")) {
      nsvDongNgan(ngan);
      await nsvKhoa(theoId(tim("data-nsv-khoa").dataset.nsvKhoa), veLai);
    } else if (tim("data-nsv-dat-lai-mk")) {
      await nsvDatLaiMatKhau(theoId(tim("data-nsv-dat-lai-mk").dataset.nsvDatLaiMk), veLai);
    } else if (tim("data-nsv-chuyen")) {
      const n = theoId(tim("data-nsv-chuyen").dataset.nsvChuyen);
      try {
        const viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`);
        if (!viec.tong) { toast("Người này không còn giữ việc nào."); return; }
        await nsvHoiChuyenViec(n, viec);
      } catch (err) { toast(err.message, true); }
      nsvDongNgan(ngan);
      await veLai();
    } else if (tim("data-nsv-dong-ban-giao")) {
      el.querySelector("[data-nsv-ban-giao]").innerHTML = "";
    }
  });
  // Đóng menu "⋯" khi bấm ra ngoài tab — <details> tự nó không làm việc này.
  document.addEventListener("click", (e) => {
    if (!el.contains(e.target)) $$("details.nsv-menu[open]", el).forEach((m) => { m.open = false; });
  });
  el.addEventListener("input", (e) => {
    if (e.target.matches("[data-nsv-tim-nguoi]")) { nsvLoc.chu = e.target.value; nsvVeDs(el); }
  });
  el.addEventListener("change", (e) => {
    if (e.target.matches("[data-nsv-loc-vai]")) { nsvLoc.vai = e.target.value; nsvVeDs(el); }
    if (e.target.matches("[data-nsv-loc-tt]")) { nsvLoc.tt = e.target.value; nsvVeDs(el); }
    const f = e.target.closest("[data-nsv-form-nguoi]");
    if (f && e.target.name === "vai_tro") {
      f.querySelector("[data-nsv-tom-tat]").innerHTML =
        nsvTomTatVai($$('input[name="vai_tro"]:checked', f).map((i) => i.value));
    }
  });
  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-nsv-form-nguoi]");
    if (!f) return;
    e.preventDefault();
    const kq = await nsvLuuNguoi(f);
    if (!kq) return;
    nsvDongNgan(ngan);
    if (kq.taoMoi) el.querySelector("[data-nsv-ban-giao]").innerHTML = nsvBanGiao(kq.taoMoi);
    await veLai();
  });
  // Quay lại tab: nạp lại — người khác có thể vừa khoá, vừa gán vai trò.
  // Đang mở ngăn kéo thì thôi: vẽ lại là mất form đang sửa dở.
  el.addEventListener("tab:hien", () => { if (ngan.hidden) veLai(); });
  try { await nsvVeNhanVien(el); } catch (err) {
    el.querySelector("[data-nsv-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};
