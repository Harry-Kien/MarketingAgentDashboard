/* ---------------- Trả lời nhanh ---------------- */
/* Gõ "/" ở ĐẦU ô nhắn tin → khung gợi ý mẫu; ↑↓ chọn, Enter/Tab chèn, Esc đóng.
 *
 * Khung nằm NGOÀI #convdetail (gắn vào <body>): vòng làm mới 6 giây dựng lại
 * cả panel hội thoại, khung nằm trong đó thì cứ 6 giây biến mất một lần giữa
 * lúc người trực đang chọn. `ganMauNhanh` được gọi lại sau mỗi lần dựng nên
 * luôn bám đúng ô nhắn tin hiện tại. */
const mauNhanh = { ds: [], chon: 0, o: null, hen: null, lan: 0 };

function _khungMau() {
  let k = $("#mau-nhanh");
  if (!k) {
    k = document.createElement("div");
    k.id = "mau-nhanh";
    k.className = "mau-nhanh";
    k.setAttribute("role", "listbox");
    k.setAttribute("aria-label", "Mẫu trả lời nhanh");
    k.hidden = true;
    document.body.appendChild(k);
    // mousedown chứ không click: click tới SAU khi ô nhắn tin mất focus.
    k.addEventListener("mousedown", (ev) => {
      const d = ev.target.closest("[data-mau]");
      if (!d) return;
      ev.preventDefault();
      _chenMau(Number(d.dataset.mau));
    });
  }
  return k;
}

function _dongMau() {
  const k = $("#mau-nhanh");
  if (k) k.hidden = true;
  mauNhanh.ds = [];
}

function _veMau() {
  const k = _khungMau();
  const o = mauNhanh.o;
  if (!o || !document.body.contains(o) || !mauNhanh.ds.length) { _dongMau(); return; }
  k.innerHTML = mauNhanh.ds.map((m, i) => `
    <div class="mau-nhanh__dong${i === mauNhanh.chon ? " is-chon" : ""}" role="option"
         aria-selected="${i === mauNhanh.chon}" data-mau="${i}">
      <b>/${esc(m.ma_tat)}</b> <span>${esc(m.noi_dung)}</span>
    </div>`).join("");
  const r = o.getBoundingClientRect();
  k.style.left = `${Math.max(8, r.left)}px`;
  k.style.width = `${Math.min(r.width, window.innerWidth - 16)}px`;
  k.style.bottom = `${window.innerHeight - r.top + 6}px`;
  k.hidden = false;
}

function _chenMau(i) {
  const m = mauNhanh.ds[i];
  const o = mauNhanh.o;
  if (!m || !o) return;
  o.value = m.noi_dung;
  _dongMau();
  o.focus();
  o.setSelectionRange(o.value.length, o.value.length);
  // Báo cho trình giữ bản nháp biết chữ đã đổi.
  o.dispatchEvent(new Event("input", { bubbles: true }));
}

async function _timMau(q) {
  const lan = ++mauNhanh.lan;
  try {
    const r = await api(`/tra-loi-nhanh?q=${encodeURIComponent(q)}`);
    if (lan !== mauNhanh.lan) return;     // đã có lần gõ mới hơn
    mauNhanh.ds = r.mau.slice(0, 8);
    mauNhanh.chon = 0;
    _veMau();
  } catch { _dongMau(); }                  // thiếu quyền / lỗi mạng: im, không chặn gõ
}

function ganMauNhanh(o) {
  mauNhanh.o = o;
  if (mauNhanh.ds.length) _veMau();        // panel vừa dựng lại: bám ô mới
  o.addEventListener("input", () => {
    const v = o.value;
    const m = /^\/(\S{0,32})$/.exec(v);
    if (!m) { _dongMau(); return; }
    clearTimeout(mauNhanh.hen);
    mauNhanh.hen = setTimeout(() => _timMau(m[1]), 150);
  });
  o.addEventListener("keydown", (ev) => {
    const k = $("#mau-nhanh");
    if (!k || k.hidden || !mauNhanh.ds.length) return;
    if (ev.isComposing || ev.keyCode === 229) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      const n = mauNhanh.ds.length;
      mauNhanh.chon = (mauNhanh.chon + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
      _veMau();
    } else if (ev.key === "Enter" || ev.key === "Tab") {
      ev.preventDefault();
      ev.stopImmediatePropagation();       // không để Enter thành "Gửi"
      _chenMau(mauNhanh.chon);
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      _dongMau();
    }
  });
  // Chỉ đóng khi người dùng THẬT SỰ rời ô nhắn tin. Vòng làm mới 6 giây vứt
  // ô cũ (nó nhận `blur`) rồi trả focus cho ô mới — đóng vô điều kiện là
  // khung tự biến mất mỗi 6 giây giữa lúc đang chọn (đo được trên bản xem
  // trước 14.10.2026).
  o.addEventListener("blur", () => setTimeout(() => {
    if (document.activeElement !== mauNhanh.o) _dongMau();
  }, 120));
}

async function loadMauNhanh() {
  const ds = $("#mauNhanhDs");
  if (!ds) return;
  const sua = state.toiQuyen && state.toiQuyen.has("tra_loi_nhanh.sua");
  $("#mauNhanhForm").hidden = !sua;
  const r = await api("/tra-loi-nhanh");
  ds.innerHTML = r.mau.length ? r.mau.map((m) => `
    <div class="row">
      <span class="row__flag row__flag--plain"></span>
      <span class="row__body"><span class="row__title">/${esc(m.ma_tat)}</span>
        <span class="row__sub">${esc(m.noi_dung)}</span></span>
      ${sua ? `<span class="row__side">
        <button type="button" class="btn btn--sm" data-mau-sua="${esc(m.id)}">Sửa</button>
        <button type="button" class="btn btn--sm btn--halt" data-mau-xoa="${esc(m.id)}">Xoá</button>
      </span>` : ""}
    </div>`).join("")
    : '<p class="empty">Chưa có mẫu nào.</p>';
  ds.querySelectorAll("[data-mau-sua]").forEach((b) => b.addEventListener("click", () => {
    const m = r.mau.find((x) => x.id === b.dataset.mauSua);
    const f = $("#mauNhanhForm");
    f.mau_id.value = m.id; f.ma_tat.value = m.ma_tat; f.noi_dung.value = m.noi_dung;
    f.ma_tat.focus();
  }));
  ds.querySelectorAll("[data-mau-xoa]").forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/tra-loi-nhanh/${b.dataset.mauXoa}`, { method: "DELETE" });
      toast("Đã xoá mẫu.");
      loadMauNhanh();
    } catch (e) { toast(e.message, true); }
  }));
}

$("#mauNhanhForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const id = f.mau_id.value;
  const body = JSON.stringify({ ma_tat: f.ma_tat.value.trim().toLowerCase(),
                                noi_dung: f.noi_dung.value });
  try {
    await api(id ? `/tra-loi-nhanh/${id}` : "/tra-loi-nhanh",
              { method: id ? "PUT" : "POST", body });
    toast("Đã lưu mẫu.");
    f.reset(); f.mau_id.value = "";
    loadMauNhanh();
  } catch (e) { toast(e.message, true); }   // 422 cụm cấm: giữ chữ để sửa
});
$("#mauNhanhHuy")?.addEventListener("click", () => {
  const f = $("#mauNhanhForm");
  f.reset(); f.mau_id.value = "";
});

/* ---------------- Nhãn, ghi chú, tìm hội thoại ---------------- */
/* Nhãn mô tả MỘT VỤ VIỆC ("chờ hàng về"), khác nhãn của khách ở Customer
 * 360. Thêm nhãn và ghi chú bằng hộp hỏi (`hoiHop`) chứ không bằng ô trong
 * panel: vòng làm mới 6 giây dựng lại cả panel, chữ đang gõ trong đó sẽ mất. */

function veLocNhan(ds) {
  const k = $("#nhanfilter");
  if (!k) return;
  k.hidden = !ds.length && !state.convNhan;
  k.innerHTML = ds.map((n) => `<button type="button" class="chip ${state.convNhan === n.nhan ? "is-on" : ""}"
    data-loc-nhan="${esc(n.nhan)}">${esc(n.nhan)} <span class="chip__so">${n.so}</span></button>`).join("");
}

$("#nhanfilter")?.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-loc-nhan]");
  if (!b) return;
  state.convNhan = state.convNhan === b.dataset.locNhan ? "" : b.dataset.locNhan;
  loadConversations();
});

$("#convtim")?.addEventListener("input", (ev) => {
  clearTimeout(state.henTim);
  state.henTim = setTimeout(() => {
    const q = ev.target.value.trim();
    state.convTim = q.length >= 2 ? q : "";
    loadConversations();
  }, 300);
});

document.addEventListener("click", async (ev) => {
  const id = state.openConv;
  if (!id) return;
  if (ev.target.closest("#btn-them-nhan")) {
    const d = await hoiHop({
      tieu_de: "Gắn nhãn cho hội thoại",
      phu: "Nhãn mô tả vụ việc này, ví dụ: chờ hàng về, khiếu nại ship, đã báo giá.",
      truong: [{ name: "nhan", label: "Nhãn", required: true, maxlength: 40 }],
      nut: "Gắn nhãn",
    });
    if (!d || !d.nhan) return;
    try {
      await api(`/inbox/conversations/${id}/nhan`, { method: "POST", body: JSON.stringify({ nhan: d.nhan }) });
      toast("Đã gắn nhãn.");
      loadConversations();
    } catch (e) { toast(e.message, true); }
  } else if (ev.target.closest("[data-go-nhan]")) {
    const n = ev.target.closest("[data-go-nhan]").dataset.goNhan;
    try {
      await api(`/inbox/conversations/${id}/nhan/${encodeURIComponent(n)}`, { method: "DELETE" });
      loadConversations();
    } catch (e) { toast(e.message, true); }
  } else if (ev.target.closest("#btn-them-ghichu")) {
    const d = await hoiHop({
      tieu_de: "Ghi chú nội bộ",
      phu: "Chỉ người trong cửa hàng thấy — KHÔNG gửi cho khách. Dùng để bàn giao giữa ca.",
      truong: [{ name: "noi_dung", label: "Ghi chú", type: "textarea", rows: 4,
                 required: true, maxlength: 5000 }],
      nut: "Lưu ghi chú",
    });
    if (!d || !d.noi_dung) return;
    try {
      await api(`/inbox/conversations/${id}/ghi-chu`, { method: "POST", body: JSON.stringify({ noi_dung: d.noi_dung }) });
      state.moGhiChu = true;
      toast("Đã lưu ghi chú.");
      loadThread(id);
    } catch (e) { toast(e.message, true); }
  }
});
document.addEventListener("toggle", (ev) => {
  if (ev.target.classList && ev.target.classList.contains("ghichu")) state.moGhiChu = ev.target.open;
}, true);

/* ---------------- Hiệu suất nhân viên ---------------- */
function _ngayVN(d) {
  // YYYY-MM-DD theo giờ máy người xem — dashboard dùng ở VN.
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}

function _giay(g) {
  if (g == null) return "—";
  if (g < 60) return `${Math.round(g)} giây`;
  if (g < 3600) return `${Math.round(g / 60)} phút`;
  return `${(g / 3600).toFixed(1)} giờ`;
}

async function loadBaoCaoNhanVien() {
  const f = $("#bcnvForm");
  if (!f) return;
  if (!f.tu.value) {
    const nay = new Date();
    f.den.value = _ngayVN(nay);
    f.tu.value = _ngayVN(new Date(nay.getTime() - 6 * 86400000));
  }
  const qs = `tu=${f.tu.value}&den=${f.den.value}`;
  $("#bcnvExcel").href = `/api/bao-cao/nhan-vien.xlsx?${qs}`;
  state.bcnvDaTai = true;
  try {
    const r = await api(`/bao-cao/nhan-vien?${qs}`);
    const ds = r.nhan_vien || [];
    $("#bcnvBang").innerHTML = `<thead><tr>
      <th>Nhân viên</th><th>Hội thoại được giao</th><th>Tin đã gửi</th>
      <th>Phản hồi đầu (trung vị)</th><th>p90</th><th>Chưa phản hồi</th>
      <th>Đơn</th><th>Trễ SLA</th><th>CSAT</th></tr></thead><tbody>${ds.length ? ds.map((d) => `<tr>
      <td>${esc(d.ho_ten)}</td><td>${d.hoi_thoai}</td><td>${d.tin_gui}</td>
      <td>${_giay(d.phan_hoi_trung_vi_giay)}</td><td>${_giay(d.phan_hoi_p90_giay)}</td>
      <td class="${d.chua_phan_hoi ? "so--xau" : ""}">${d.chua_phan_hoi}</td>
      <td>${d.don}</td><td class="${d.tre_sla ? "so--xau" : ""}">${d.tre_sla}</td>
      <td>${d.csat_so ? `${d.csat_tb} <span class="msg__meta">(${d.csat_so})</span>` : "—"}</td></tr>`).join("")
      : '<tr><td colspan="9" class="empty">Chưa có nhân viên nào.</td></tr>'}</tbody>`;
  } catch (e) { toast(e.message, true); }
}

$("#bcnvForm")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  loadBaoCaoNhanVien();
});
$("#bcnvForm")?.addEventListener("change", () => {
  const f = $("#bcnvForm");
  if (f.tu.value && f.den.value) {
    $("#bcnvExcel").href = `/api/bao-cao/nhan-vien.xlsx?tu=${f.tu.value}&den=${f.den.value}`;
  }
});

/* ---------------- VietQR ---------------- */
/* Ủy quyền một trình nghe ở document: danh sách đơn dựng lại mỗi lần làm
 * mới, gắn vào từng nút là gắn lại mãi. */
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-oqr-gui]");
  if (!b) return;
  b.disabled = true;
  try {
    const r = await api(`/orders/${b.dataset.oqrGui}/vietqr/gui`, { method: "POST" });
    toast(r.duplicate ? "Mã QR này đã gửi trước đó." : "Đã xếp hàng gửi mã QR cho khách.");
  } catch (e) { toast(e.message, true); }
  finally { b.disabled = false; }
});

/* ---------------- Đã giải quyết ---------------- */
document.addEventListener("click", async (ev) => {
  if (!ev.target.closest("#btn-giai-quyet") || !state.openConv) return;
  try {
    const r = await api(`/inbox/conversations/${state.openConv}/giai-quyet`, { method: "POST" });
    toast(r.da_truoc ? "Hội thoại đã được giải quyết từ trước."
      : `Đã giải quyết${r.csat === "đã hỏi" ? " — đã hỏi khách chấm điểm" : ""}.`);
    loadConversations();
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Bảo mật hai bước (TOTP) ---------------- */
/* Bật là HAI bước: quét QR, rồi gõ một mã thật — bật ngay khi sinh bí mật
 * là khoá người dùng ra ngoài nếu họ quét hỏng. Mã dự phòng chỉ hiện MỘT
 * lần, ngay sau khi bật. */
document.addEventListener("click", async (ev) => {
  if (!ev.target.closest("#haibuoc")) return;
  ev.preventDefault();
  try {
    const tt = await api("/toi/hai-buoc");
    if (tt.bat) {
      const d = await hoiHop({
        tieu_de: "Tắt xác thực hai bước",
        phu: `Đang bật · còn ${tt.ma_du_phong_con} mã dự phòng. Tắt thì chỉ còn mật khẩu bảo vệ tài khoản.`,
        truong: [{ name: "mat_khau", label: "Gõ lại mật khẩu", type: "password", required: true }],
        nut: "Tắt", nguy_hiem: true,
      });
      if (!d || !d.mat_khau) return;
      await api("/toi/hai-buoc/tat", { method: "POST", body: JSON.stringify({ mat_khau: d.mat_khau }) });
      toast("Đã tắt xác thực hai bước.");
      return;
    }
    const moi = await api("/toi/hai-buoc/bat-dau", { method: "POST" });
    const cho = hoiHop({
      tieu_de: "Bật xác thực hai bước",
      phu: "Quét mã bằng Google Authenticator, Authy hoặc 1Password, rồi nhập mã 6 số đang hiện.",
      truong: [{ name: "ma", label: "Mã 6 số", required: true, maxlength: 6 }],
      nut: "Bật",
    });
    // Ảnh QR do MÁY CHỦ vẽ (segno) — chèn vào phần mô tả của hộp hỏi.
    const phu = $("#hoiPhu");
    phu.innerHTML = `${esc(phu.textContent)}<span class="qr-2fa">${moi.svg}</span>`
      + `<small>Không quét được: nhập tay khoá trong <code>${esc(moi.uri.split("secret=")[1]?.split("&")[0] || "")}</code></small>`;
    const d = await cho;
    if (!d || !d.ma) return;
    const r = await api("/toi/hai-buoc/xac-nhan", { method: "POST", body: JSON.stringify({ ma: d.ma }) });
    await hoiHop({
      tieu_de: "Đã bật — lưu mã dự phòng",
      phu: "Mỗi mã dùng MỘT lần khi mất điện thoại. Lưu ở nơi an toàn; trang này sẽ không hiện lại.\n\n"
        + r.ma_du_phong.join("   "),
      truong: [], nut: "Đã lưu",
    });
  } catch (e) { toast(e.message, true); }
});
