/* ================= NHÂN SỰ & PHÂN QUYỀN (phiếu việc mục 12–13) =================
 *
 * Hai tab gắn vào khung tab của dashboard:
 *
 *   GAN_TAB["ns-nhan-vien"](el)  tài khoản, thông tin, trạng thái, vai trò,
 *                                khoá kèm chuyển việc
 *   GAN_TAB["ns-vai-tro"](el)    vai trò: tạo, sửa, ngừng dùng, cấp quyền
 *                                theo nhóm chức năng; lịch sử đổi quyền
 *
 * Màn "Nhân sự" cũ (09-nhan-su.js) dùng CHUNG các hàm ở đây cho ba việc
 * khó làm đúng hai lần: bảng tick quyền theo nhóm, khoá kèm chuyển việc,
 * và lịch sử. Hai bản chép là hai chỗ để một luật lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ. Ẩn nút theo quyền chỉ để màn hình
 * không mời một 403 mỗi lần bấm — không phải để bảo vệ gì.
 */
window.GAN_TAB = window.GAN_TAB || {};

const nsv = { nguoi: [], vaiTro: [], nhom: [] };

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

/* ---------------- dùng chung: bảng tick quyền theo nhóm ---------------- */

/* Nhóm theo CHỨC NĂNG dashboard (máy chủ trả `nhom_hien_thi`, đúng thứ tự
   phiếu việc), không theo tiền tố mã. `khoa` cho vai trò Quản trị: nó lấy
   quyền từ mã, tick/bỏ tick ở đó không có tác dụng gì. */
function nsvBangQuyen(dangCo, khoa = false) {
  const co = new Set(dangCo || []);
  if (!nsv.nhom.length) return '<p class="empty">Chưa tải được danh mục quyền.</p>';
  return nsv.nhom.map((g) => `
    <fieldset class="quyen__nhom">
      <legend>${esc(g.ten)}${khoa ? "" : ` <button type="button" class="btn btn--sm btn--ghost"
        data-nsv-ca-nhom="${esc(g.ma)}">chọn / bỏ cả nhóm</button>`}</legend>
      ${g.quyen.map((q) => `<label class="quyen__o">
        <input type="checkbox" name="quyen" value="${esc(q.ma)}"${co.has(q.ma) ? " checked" : ""}${khoa ? " disabled" : ""}>
        <span>${esc(q.nhan)}</span><code>${esc(q.ma)}</code>
      </label>`).join("")}
    </fieldset>`).join("");
}

document.addEventListener("click", (e) => {
  const nut = e.target.closest("[data-nsv-ca-nhom]");
  if (!nut) return;
  const o = $$('input[name="quyen"]:not(:disabled)', nut.closest("fieldset"));
  const batHet = o.some((i) => !i.checked);
  o.forEach((i) => { i.checked = batHet; });
});

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
      + (ct.de_lai_viec ? ` <span class="pill pill--warn">để lại ${ct.de_lai_viec.so_hoi_thoai} hội thoại, ${ct.de_lai_viec.so_cong_viec} việc</span>` : "");
  } else if (d.loai === "nguoi_dung.chuyen_viec") {
    them = `<span class="pill">${ct.so_hoi_thoai || 0} hội thoại, ${ct.so_cong_viec || 0} việc → ${esc(sau.nguoi || "")}</span>`
      + (ct.khong_chuyen_duoc ? ` <span class="pill pill--warn">${ct.khong_chuyen_duoc} hội thoại không chuyển được</span>` : "");
  } else {
    if (truoc.ten && sau.ten && truoc.ten !== sau.ten) {
      them += `<span class="pill">Tên: ${esc(truoc.ten)} → ${esc(sau.ten)}</span> `;
    }
    them += [nsvPill(ct.them, "+", ""), nsvPill(ct.bot, "−", "pill--warn")].filter(Boolean).join(" ");
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

async function nsvVeLichSu(el, loai = "tat_ca") {
  if (!el) return;
  try {
    const d = await api(`/nhan-su/lich-su?loai=${encodeURIComponent(loai)}&limit=60`);
    el.innerHTML = d.lich_su.length
      ? d.lich_su.map(nsvDongLichSu).join("")
      : '<p class="empty">Chưa có thay đổi nào về nhân sự hay phân quyền.</p>';
  } catch (err) {
    el.innerHTML = `<p class="empty">Không tải được lịch sử: ${esc(err.message)}</p>`;
  }
}

/* ---------------- dùng chung: khoá kèm chuyển việc (mục 13.8) ---------------- */

/* Hỏi chuyển việc cho AI. Trả null nếu người dùng thôi, `{deLai: true}` nếu
   chọn để lại việc (chỉ khi đang khoá), hoặc kết quả của máy chủ. */
async function nsvHoiChuyenViec(n, viec, khiKhoa) {
  if (!nsv.nguoi.length) await nsvTaiDuLieu();
  const ten = n.ho_ten || n.ten_dang_nhap;
  const nguoiNhan = nsv.nguoi.filter((x) => !x.khoa && x.id !== n.id);
  const lietKe = [
    ...viec.hoi_thoai.slice(0, 3).map((h) => `hội thoại với ${h.khach || "khách"}`),
    ...viec.cong_viec.slice(0, 3).map((v) => `việc “${v.tieu_de}”`),
  ].join("; ");
  const d = await hoiHop({
    tieu_de: khiKhoa ? `Khoá ${ten}: chuyển việc trước` : `Chuyển việc của ${ten}`,
    phu: `${ten} đang giữ ${viec.so_hoi_thoai} hội thoại và ${viec.so_cong_viec} việc chưa xong`
      + (lietKe ? ` (${lietKe}${viec.tong > 6 ? "…" : ""})` : "")
      + ". Khoá mà không chuyển là khách của họ chờ mà không ai trả lời.",
    truong: [{
      name: "nguoi_nhan", label: "Chuyển cho", type: "select", required: true,
      value: nguoiNhan.length ? nguoiNhan[0].id : "",
      options: [
        ...nguoiNhan.map((x) => ({ value: x.id, label: `${x.ho_ten || x.ten_dang_nhap} (${x.ten_dang_nhap})` })),
        ...(khiKhoa ? [{ value: "__de_lai__", label: "Không chuyển — khoá và để lại việc (khách có thể phải chờ)" }] : []),
      ],
    }],
    nut: khiKhoa ? "Chuyển rồi khoá" : "Chuyển việc",
    nguy_hiem: !!khiKhoa,
  });
  if (!d || !d.nguoi_nhan) return null;
  if (d.nguoi_nhan === "__de_lai__") return { deLai: true };
  try {
    const kq = await api(`/nguoi-dung/${n.id}/chuyen-viec`, {
      method: "POST",
      body: JSON.stringify({
        nguoi_nhan: d.nguoi_nhan,
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

/* Khoá / mở khoá. Khoá thì HỎI VỀ VIỆC ĐANG GIỮ trước — máy chủ cũng chặn
   (409 `can_chuyen_viec`) nên gọi thẳng API hay màn cũ đều gặp cùng câu hỏi.
   Lời xác nhận nói điều sẽ xảy ra: phiên đang mở bị đá ra ngay. */
async function nsvKhoa(n, xong) {
  const ten = n.ten_dang_nhap;
  const goi = (khoa, boQua) => api(
    `/nguoi-dung/${encodeURIComponent(ten)}/khoa?khoa=${khoa}${boQua ? "&bo_qua_viec=true" : ""}`,
    { method: "POST" });
  if (n.khoa) {
    if (!confirm(`Mở khoá “${ten}”? Họ đăng nhập lại được ngay.`)) return;
    try { await goi(false); toast(`Đã mở khoá ${ten}.`); } catch (err) { toast(err.message, true); }
    if (xong) await xong();
    return;
  }
  let viec;
  try { viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`); } catch (err) { toast(err.message, true); return; }
  let boQua = false;
  if (viec.tong) {
    const kq = await nsvHoiChuyenViec(n, viec, true);
    if (!kq) return;
    if (kq.deLai) {
      boQua = true;
    } else if (kq.khong_chuyen_duoc && kq.khong_chuyen_duoc.length) {
      const lyDo = kq.khong_chuyen_duoc.map((x) => `${x.khach || "khách"}: ${x.ly_do}`).join("; ");
      if (!confirm(`${kq.khong_chuyen_duoc.length} hội thoại KHÔNG chuyển được (${lyDo}). `
        + `Vẫn khoá “${ten}” và để lại các hội thoại ấy?`)) { if (xong) await xong(); return; }
      boQua = true;
    }
    if (!confirm(`Khoá “${ten}”? Mọi phiên đang mở của họ bị đá ra ngay lập tức.`)) { if (xong) await xong(); return; }
  } else if (!confirm(`Khoá “${ten}”? Mọi phiên đang mở của họ bị đá ra ngay lập tức.`)) {
    return;
  }
  try {
    await goi(true, boQua);
    toast(`Đã khoá ${ten} và đá mọi phiên.`);
  } catch (err) {
    toast(err.message, true);
    // Ai đó vừa giao thêm việc cho người này giữa lúc đang hỏi: hỏi lại.
    if (err.chi_tiet && err.chi_tiet.can_chuyen_viec) return nsvKhoa(n, xong);
  }
  if (xong) await xong();
}

/* ======================== TAB "NHÂN VIÊN" ======================== */

function nsvDongNguoi(n) {
  const sua = nsvCo("nguoi_dung.sua");
  const vai = (n.vai_tro_ten || []).map((t) => `<span class="pill">${esc(t)}</span>`).join(" ")
    + (n.vai_tro_ngung || []).map((t) =>
      ` <span class="pill pill--warn" title="Vai trò đã ngừng dùng — không cấp quyền nào">${esc(t)} · ngừng dùng</span>`).join("")
    || '<span class="pill pill--warn">chưa có vai trò nào</span>';
  const giu = Number(n.so_hoi_thoai_giu || 0);
  const viec = Number(n.so_viec_chua_xong || 0);
  const ganViec = giu || viec
    ? ` <span class="pill${n.khoa ? " pill--warn" : ""}">giữ ${giu} hội thoại · ${viec} việc</span>` : "";
  return `<div class="row">
    <span class="row__flag row__flag--${n.khoa ? "halt" : (n.vai_tro_ten || []).length ? "auto" : "assist"}"></span>
    <div class="row__main">
      <b>${esc(n.ho_ten || n.ten_dang_nhap)}</b>
      <span class="tag tag--${n.khoa ? "halt" : "auto"}">${n.khoa ? "Đã khoá" : "Đang làm"}</span>
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.email ? " · " + esc(n.email) : ""}
        · tạo ${nsvNgay(n.tao_luc)}
        · ${n.dang_nhap_cuoi ? "vào lần cuối " + nsvNgay(n.dang_nhap_cuoi) : "chưa đăng nhập lần nào"}</span>
    </div>
    <div class="row__side">
      <span>${vai}${ganViec}</span>
      <span class="row__nut">
        <button type="button" class="btn btn--sm btn--ghost" data-nsv-quyen="${esc(n.id)}">Quyền</button>
        ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-sua="${esc(n.id)}">Sửa</button>
        ${giu || viec ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-chuyen="${esc(n.id)}">Chuyển việc</button>` : ""}
        <button type="button" class="btn btn--sm ${n.khoa ? "btn--ghost" : "btn--halt"}" data-nsv-khoa="${esc(n.id)}">${n.khoa ? "Mở khoá" : "Khoá"}</button>` : ""}
      </span>
    </div>
  </div>`;
}

/* Form thêm/sửa — MỘT form cho cả hai, vai trò là ô TICK (một người nhiều
   vai trò). Vai trò đã ngừng dùng: người đang mang thì vẫn hiện đã tick
   (gỡ được), người chưa mang thì khoá — máy chủ cũng từ chối gán mới. */
function nsvFormNguoi(n) {
  const moi = !n;
  const dangCo = new Set(n ? n.vai_tro_id || [] : []);
  return `<form class="form" data-nsv-form-nguoi="${moi ? "" : esc(n.id)}">
    <h3 class="panel__head">${moi ? "Thêm nhân viên" : `Sửa ${esc(n.ho_ten || n.ten_dang_nhap)}`}</h3>
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
    <fieldset class="quyen__nhom"><legend>Vai trò <em class="hint">quyền = hợp quyền mọi vai trò đang dùng</em></legend>
      ${nsv.vaiTro.map((v) => `<label class="quyen__o">
        <input type="checkbox" name="vai_tro" value="${esc(v.id)}"${dangCo.has(v.id) ? " checked" : ""}${
          !v.dang_dung && !dangCo.has(v.id) ? " disabled" : ""}>
        <span>${esc(v.ten)}${v.dang_dung ? "" : " · ngừng dùng"}</span>
        <small>${esc(v.mo_ta || "")}</small></label>`).join("")}
    </fieldset>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">${moi ? "Tạo tài khoản" : "Lưu"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-huy-form>Huỷ</button>
    </div>
  </form>`;
}

async function nsvLuuNguoi(f) {
  const id = f.dataset.nsvFormNguoi;
  const d = Object.fromEntries(new FormData(f).entries());
  const vai = $$('input[name="vai_tro"]:checked', f).map((i) => i.value);
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    if (!id) {
      await api("/nguoi-dung", {
        method: "POST",
        body: JSON.stringify({
          ten_dang_nhap: String(d.ten_dang_nhap || "").trim(),
          mat_khau: d.mat_khau, ho_ten: String(d.ho_ten || "").trim(),
          email: String(d.email || "").trim() || null, vai_tro_ids: vai,
        }),
      });
      toast(vai.length ? "Đã tạo tài khoản và cấp vai trò. Báo họ đổi mật khẩu ở mục Tôi."
        : "Đã tạo. Chưa có vai trò nên họ vào được mà mọi màn đều trống.");
    } else {
      await api(`/nguoi-dung/${id}`, {
        method: "PUT",
        body: JSON.stringify({ ho_ten: String(d.ho_ten || "").trim(),
                               email: String(d.email || "").trim() || null }),
      });
      const cu = (nsv.nguoi.find((x) => x.id === id) || {}).vai_tro_id || [];
      if ([...cu].sort().join() !== [...vai].sort().join()) {
        await api(`/nguoi-dung/${id}/vai-tro`, { method: "PUT", body: JSON.stringify({ vai_tro: vai }) });
      }
      toast("Đã lưu.");
    }
    return true;
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
    return false;
  }
}

/* Quyền THỰC TẾ của một người, theo nhóm chức năng, kèm vai trò nào cấp. */
function nsvVeQuyenNguoi(d) {
  const co = d.quyen || {};
  const nhom = nsv.nhom.map((g) => {
    const dong = g.quyen.filter((q) => co[q.ma]);
    return dong.length ? `<fieldset class="quyen__nhom"><legend>${esc(g.ten)}</legend>${
      dong.map((q) => `<div class="quyen__o"><span>${esc(q.nhan)}</span>
        <small>cấp bởi: ${esc(co[q.ma].join(", "))}</small></div>`).join("")}</fieldset>` : "";
  }).join("");
  return `<div class="ns-vaitro" data-nsv-xem-quyen>
    ${nhom || '<p class="empty">Chưa được cấp quyền nào. Người này đăng nhập được nhưng mọi màn đều trống.</p>'}
    ${(d.vai_tro_ngung || []).length ? `<p class="panel__note">Vai trò đã ngừng dùng (không cấp gì): ${esc(d.vai_tro_ngung.join(", "))}</p>` : ""}
    <div class="row__nut"><button type="button" class="btn btn--sm btn--ghost" data-nsv-dong>Đóng</button></div>
  </div>`;
}

async function nsvVeNhanVien(el) {
  await nsvTaiDuLieu();
  const ds = nsv.nguoi;
  const dangLam = ds.filter((n) => !n.khoa).length;
  const chuaVai = ds.filter((n) => !(n.vai_tro_ten || []).length).length;
  const dem = el.querySelector("[data-nsv-dem]");
  if (dem) {
    dem.textContent = [`${ds.length} tài khoản`, `${dangLam} đang làm`,
      ds.length - dangLam ? `${ds.length - dangLam} đã khoá` : "",
      chuaVai ? `${chuaVai} chưa có vai trò` : ""].filter(Boolean).join(" · ");
  }
  el.querySelector("[data-nsv-ds]").innerHTML = ds.length
    ? ds.map(nsvDongNguoi).join("") : '<p class="empty">Chưa có nhân viên nào.</p>';
}

GAN_TAB["ns-nhan-vien"] = async (el) => {
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Nhân viên <span class="panel__note" data-nsv-dem>đang tải…</span>
      ${nsvCo("nguoi_dung.sua") ? '<button type="button" class="btn btn--sm" data-nsv-them>Thêm nhân viên</button>' : ""}</h2>
    <div data-nsv-khung-form></div>
    <div class="rows" data-nsv-ds><p class="empty">Đang tải…</p></div>
  </section>`;
  if (!el.dataset.nsvGan) {
    el.dataset.nsvGan = "1";
    el.addEventListener("click", async (e) => {
      const tim = (k) => e.target.closest(`[${k}]`);
      const nguoiTheoId = (id) => nsv.nguoi.find((x) => x.id === id);
      const khung = el.querySelector("[data-nsv-khung-form]");
      if (tim("data-nsv-them")) {
        khung.innerHTML = nsvFormNguoi(null);
        khung.querySelector("input").focus();
      } else if (tim("data-nsv-sua")) {
        khung.innerHTML = nsvFormNguoi(nguoiTheoId(tim("data-nsv-sua").dataset.nsvSua));
        khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (tim("data-nsv-huy-form")) {
        khung.innerHTML = "";
      } else if (tim("data-nsv-khoa")) {
        await nsvKhoa(nguoiTheoId(tim("data-nsv-khoa").dataset.nsvKhoa), () => nsvVeNhanVien(el));
      } else if (tim("data-nsv-chuyen")) {
        const n = nguoiTheoId(tim("data-nsv-chuyen").dataset.nsvChuyen);
        try {
          const viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`);
          if (!viec.tong) { toast("Người này không còn giữ việc nào."); return; }
          await nsvHoiChuyenViec(n, viec, false);
        } catch (err) { toast(err.message, true); }
        await nsvVeNhanVien(el);
      } else if (tim("data-nsv-quyen")) {
        $$("[data-nsv-xem-quyen]", el).forEach((b) => b.remove());
        const nut = tim("data-nsv-quyen");
        try {
          const d = await api(`/nguoi-dung/${nut.dataset.nsvQuyen}/quyen`);
          nut.closest(".row").insertAdjacentHTML("afterend", nsvVeQuyenNguoi(d));
        } catch (err) { toast(err.message, true); }
      } else if (tim("data-nsv-dong")) {
        tim("data-nsv-dong").closest("[data-nsv-xem-quyen]").remove();
      }
    });
    el.addEventListener("submit", async (e) => {
      const f = e.target.closest("[data-nsv-form-nguoi]");
      if (!f) return;
      e.preventDefault();
      if (await nsvLuuNguoi(f)) {
        el.querySelector("[data-nsv-khung-form]").innerHTML = "";
        await nsvVeNhanVien(el);
      }
    });
  }
  try { await nsvVeNhanVien(el); } catch (err) {
    el.querySelector("[data-nsv-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};

/* ======================== TAB "VAI TRÒ & QUYỀN" ======================== */

function nsvDongVaiTro(v) {
  const sua = nsvCo("nguoi_dung.sua");
  const soQuyen = v.toan_quyen ? "toàn bộ quyền (lấy từ mã)" : `${v.quyen.length} quyền`;
  /* Nút Xoá chỉ hiện khi máy chủ sẽ cho xoá (`xoa_duoc`): vai trò từng có
     người mang chỉ NGỪNG DÙNG được — nút bấm vào rồi mới báo 409 dạy người
     ta rằng lỗi là chuyện bình thường. */
  const nut = !sua ? "" : [
    v.toan_quyen ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-nsv-sua-vai="${esc(v.id)}">Sửa quyền</button>`,
    v.he_thong ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-nsv-trang-thai="${esc(v.id)}">${v.dang_dung ? "Ngừng dùng" : "Dùng lại"}</button>`,
    v.xoa_duoc ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-xoa-vai="${esc(v.id)}">Xoá</button>` : "",
  ].join("");
  return `<div class="row">
    <span class="row__flag row__flag--${!v.dang_dung ? "plain" : v.toan_quyen ? "halt" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(v.ten)}${v.he_thong ? ' <span class="pill">dựng sẵn</span>' : ""}${
        v.dang_dung ? "" : ' <span class="tag tag--plain">ngừng dùng</span>'}</b>
      <span class="row__sub">${esc(v.mo_ta || "—")}</span>
    </div>
    <div class="row__side">
      <span><span class="pill">${soQuyen}</span> <span class="pill">${v.so_nguoi} người</span></span>
      ${nut ? `<span class="row__nut">${nut}</span>` : ""}
    </div>
  </div>`;
}

function nsvFormVaiTro(v) {
  return `<form class="form" data-nsv-form-vai="${v ? esc(v.id) : ""}">
    <h3 class="panel__head">${v ? `Sửa vai trò “${esc(v.ten)}”` : "Tạo vai trò mới"}</h3>
    <label class="field"><span>Tên vai trò</span>
      <input name="ten" required maxlength="80" value="${esc(v ? v.ten : "")}" placeholder="Trưởng nhóm CSKH" autocomplete="off"></label>
    <label class="field"><span>Mô tả <em class="hint">để người sau hiểu vai trò này dành cho ai</em></span>
      <input name="mo_ta" maxlength="500" value="${esc(v ? v.mo_ta : "")}" autocomplete="off"></label>
    ${v && v.so_nguoi ? `<p class="panel__note">Lưu là ${v.so_nguoi} người đang mang vai trò này đổi quyền NGAY ở thao tác kế tiếp của họ.</p>` : ""}
    <div class="quyen">${nsvBangQuyen(v ? v.quyen : [])}</div>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">Lưu vai trò</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-huy-vai>Huỷ</button>
    </div>
  </form>`;
}

async function nsvVeVaiTro(el) {
  await nsvTaiDuLieu();
  el.querySelector("[data-nsv-vai-ds]").innerHTML = nsv.vaiTro.map(nsvDongVaiTro).join("");
  await nsvVeLichSu(el.querySelector("[data-nsv-lich-su]"),
                    el.querySelector("[data-nsv-loc-lich-su]")?.value || "tat_ca");
}

/* Ngừng dùng / dùng lại — nói SỐ NGƯỜI bị ảnh hưởng, không hỏi "có chắc
   không": câu ấy không mang thông tin, người ta bấm OK theo phản xạ. */
async function nsvDoiTrangThaiVai(v) {
  const loi = v.dang_dung
    ? `Ngừng dùng “${v.ten}”? ${v.so_nguoi} người đang mang nó mất các quyền này NGAY `
      + "(trừ quyền vai trò khác của họ cũng cấp). Vai trò vẫn nằm trong lịch sử và dùng lại được."
    : `Dùng lại “${v.ten}”? ${v.so_nguoi} người đang mang nó có lại các quyền này ngay.`;
  if (!confirm(loi)) return false;
  try {
    await api(`/vai-tro/${v.id}/trang-thai`, { method: "POST", body: JSON.stringify({ dang_dung: !v.dang_dung }) });
    toast(v.dang_dung ? "Đã ngừng dùng vai trò." : "Đã dùng lại vai trò.");
    return true;
  } catch (err) { toast(err.message, true); return false; }
}

GAN_TAB["ns-vai-tro"] = async (el) => {
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Vai trò &amp; Quyền
      <span class="panel__note">quyền của một người = hợp quyền mọi vai trò ĐANG DÙNG họ mang · sửa vai trò là mọi người mang nó đổi theo ngay</span>
      ${nsvCo("nguoi_dung.sua") ? '<button type="button" class="btn btn--sm" data-nsv-tao-vai>Tạo vai trò</button>' : ""}</h2>
    <div data-nsv-khung-vai></div>
    <div class="rows" data-nsv-vai-ds><p class="empty">Đang tải…</p></div>
  </section>
  <section class="panel">
    <h2 class="panel__head">Lịch sử nhân sự &amp; phân quyền
      <span class="panel__note">ai đổi gì, lúc nào — trước và sau</span>
      <select data-nsv-loc-lich-su>
        <option value="tat_ca">Tất cả</option>
        <option value="vai_tro">Vai trò &amp; quyền</option>
        <option value="nguoi_dung">Tài khoản nhân viên</option>
      </select></h2>
    <div class="rows" data-nsv-lich-su><p class="empty">Đang tải…</p></div>
  </section>`;
  if (!el.dataset.nsvGan) {
    el.dataset.nsvGan = "1";
    el.addEventListener("click", async (e) => {
      const tim = (k) => e.target.closest(`[${k}]`);
      const vaiTheoId = (id) => nsv.vaiTro.find((x) => x.id === id);
      const khung = el.querySelector("[data-nsv-khung-vai]");
      if (tim("data-nsv-tao-vai")) {
        khung.innerHTML = nsvFormVaiTro(null);
      } else if (tim("data-nsv-sua-vai")) {
        khung.innerHTML = nsvFormVaiTro(vaiTheoId(tim("data-nsv-sua-vai").dataset.nsvSuaVai));
        khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (tim("data-nsv-huy-vai")) {
        khung.innerHTML = "";
      } else if (tim("data-nsv-trang-thai")) {
        if (await nsvDoiTrangThaiVai(vaiTheoId(tim("data-nsv-trang-thai").dataset.nsvTrangThai))) {
          await nsvVeVaiTro(el);
        }
      } else if (tim("data-nsv-xoa-vai")) {
        const v = vaiTheoId(tim("data-nsv-xoa-vai").dataset.nsvXoaVai);
        if (!confirm(`Xoá hẳn vai trò “${v.ten}”? Chưa ai từng được gán vai trò này nên không mất lịch sử nào.`)) return;
        try {
          await api(`/vai-tro/${v.id}`, { method: "DELETE" });
          toast("Đã xoá vai trò.");
          await nsvVeVaiTro(el);
        } catch (err) { toast(err.message, true); }
      }
    });
    el.addEventListener("change", (e) => {
      if (e.target.closest("[data-nsv-loc-lich-su]")) {
        nsvVeLichSu(el.querySelector("[data-nsv-lich-su]"), e.target.value);
      }
    });
    el.addEventListener("submit", async (e) => {
      const f = e.target.closest("[data-nsv-form-vai]");
      if (!f) return;
      e.preventDefault();
      const id = f.dataset.nsvFormVai;
      const than = {
        ten: f.ten.value.trim(), mo_ta: f.mo_ta.value.trim(),
        quyen: $$('input[name="quyen"]:checked', f).map((i) => i.value),
      };
      try {
        await api(id ? `/vai-tro/${id}` : "/vai-tro",
                  { method: id ? "PUT" : "POST", body: JSON.stringify(than) });
        toast(id ? "Đã lưu vai trò." : "Đã tạo vai trò.");
        el.querySelector("[data-nsv-khung-vai]").innerHTML = "";
        await nsvVeVaiTro(el);
      } catch (err) { toast(err.message, true); }
    });
  }
  try { await nsvVeVaiTro(el); } catch (err) {
    el.querySelector("[data-nsv-vai-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};
