/* ---------------- dữ liệu cá nhân (Luật 91/2025, NĐ 356/2025) ---------------- */

// Xoá dữ liệu KHÔNG hoàn tác được. Nên luồng bắt buộc là: tra cứu để nhìn
// thấy sẽ mất gì -> gõ lại số điện thoại -> mới xoá được. Không có nút xoá
// nào bấm được bằng một cú lỡ tay.
async function loadPdpdPolicy() {
  const p = await api("/pdpd");
  $("#pdpdPolicy").innerHTML =
    `Hội thoại lưu tối đa <b>${p.thoi_han_ngay} ngày</b>`
    + ` · ${p.tu_dong_don ? "tự dọn hằng ngày" : "dọn thủ công"}`
    + ` · ${p.so_hoi_thoai_qua_han} hội thoại quá hạn`
    + `<br>Đơn hàng KHÔNG bị xoá theo thời hạn — chứng từ kế toán phải lưu`
    + ` tối thiểu 10 năm (Luật Kế toán 2015, Điều 41).`;
}

/* Khối xoá vẽ theo TRẠNG THÁI PHIẾU, không vẽ sẵn rồi để máy chủ từ chối.
 *
 * Máy chủ chặn xoá khi chưa có phiếu duyệt (409). Nếu giao diện vẫn hiện ô
 * nhập và nút Xoá đỏ chót thì cú bấm ấy chắc chắn thất bại — và một nút
 * "đôi khi không làm gì" dạy người vận hành rằng lỗi là chuyện bình thường,
 * đúng thói quen khiến người ta bấm qua cả những cảnh báo thật. */
function pdpdKhoiXoa(d) {
  const pd = d.phieu_duyet || {};
  /* Cả hệ thống chỉ có một người mang quyền `khach.xoa` thì phiếu nào cũng
     treo vĩnh viễn, vì người tạo không tự duyệt được. Không nói ra thì nó
     treo im lặng — dashboard chỉ hiện "chờ người khác duyệt" mãi mãi, trong
     khi thời hạn đáp ứng yêu cầu xoá là do luật đặt. */
  const ket = pd.so_nguoi_duyet_duoc < 2
    ? `<div class="kit__note kit__note--halt">⚠ Cả hệ thống chỉ có
        <b>${esc(String(pd.so_nguoi_duyet_duoc ?? 0))}</b> người dùng được quyền
        <code>khach.xoa</code>. Người tạo phiếu không tự duyệt được, nên phiếu sẽ
        <b>treo mãi</b> và yêu cầu xoá của khách không bao giờ được đáp ứng.
        Cấp quyền ấy cho ít nhất một người nữa ở màn <b>Nhân sự</b>.</div>`
    : "";
  if (pd.xoa_duoc) {
    return `<div class="kit__note">Đã có phiếu duyệt của người khác — phiếu này
        <b>dùng một lần</b>, xoá xong là hết hiệu lực.</div>
      <div class="danger__row">
        <input id="pdpdConfirm" placeholder="Gõ lại ${esc(d.so_dien_thoai)}" autocomplete="off">
        <input id="pdpdReason" placeholder="Lý do (khách yêu cầu qua Zalo…)" autocomplete="off">
        <button type="button" class="btn btn--sm btn--halt" id="pdpdDelete">Xoá dữ liệu</button>
      </div>`;
  }
  if (pd.co_phieu) {
    return ket + `<div class="kit__note">Đã có phiếu xin xoá, <b>đang chờ người khác duyệt</b>
      ở khối “Phiếu duyệt xoá” bên dưới. Người tạo phiếu không tự duyệt được —
      đó là chỗ con mắt thứ hai nằm.</div>`;
  }
  return ket + `<div class="kit__note">Xoá dữ liệu cá nhân cần <b>hai người</b>: xin phiếu ở đây,
      một người khác duyệt ở khối “Phiếu duyệt xoá” bên dưới.</div>
    <div class="danger__row">
      <button type="button" class="btn btn--sm" id="pdpdXinDuyet">Xin duyệt xoá</button>
    </div>`;
}

$("#pdpdform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const sdt = new FormData(e.target).get("sdt");
  $("#pdpdOut").innerHTML = "";
  let d;
  try { d = await api("/pdpd/" + encodeURIComponent(sdt)); }
  catch (err) { toast(err.message, true); return; }

  if (!d.co_du_lieu) {
    $("#pdpdOut").innerHTML =
      `<p class="empty">Không tìm thấy dữ liệu nào của số ${esc(d.so_dien_thoai)}.</p>`;
    return;
  }

  const don = d.don_hang.map((o) => `
    <div class="row">
      <span class="row__flag row__flag--spend"></span>
      <span class="row__body">
        <span class="row__title">${esc(o.ma_don)} · ${esc(o.khach_ten)}</span>
        <span class="row__sub">${esc(o.khach_dia_chi)}</span>
      </span>
      <span class="row__side"><span class="row__num">${vnd(o.tong_tien)}</span>
        <span class="row__time">${clock(o.created_at)}</span></span>
    </div>`).join("");

  const hoi = d.hoi_thoai.map((h) => `
    <div class="row">
      <span class="row__flag row__flag--assist"></span>
      <span class="row__body">
        <span class="row__title">${esc(h.customer_name || "Khách")} ${srcBadge(h.channel)}</span>
        <span class="row__sub">${h.msg_count} tin nhắn</span>
      </span>
      <span class="row__side"><span class="row__time">${clock(h.updated_at)}</span></span>
    </div>`).join("");

  /* Hồ sơ CRM: nơi lưu bị bỏ quên lâu nhất. Không hiện ở đây thì người
     vận hành duyệt một lần xoá mà không biết ghi chú và nhãn cũng đi theo. */
  const hs = (d.ho_so_khach || []).map((h) => `
    <div class="row">
      <span class="row__flag row__flag--assist"></span>
      <span class="row__body">
        <span class="row__title">${esc(h.display_name || "Khách")}</span>
        <span class="row__sub">${h.danh_tinh} danh tính kênh · ${h.ghi_chu} ghi chú ·
          ${h.nhan} nhãn · ${h.dong_y} dòng đồng ý${h.co_sdt ? " · có số điện thoại" : ""}${
            h.co_email ? " · có email" : ""}</span>
      </span>
    </div>`).join("");

  $("#pdpdOut").innerHTML = `
    <h3 class="subhead">Đơn hàng (${d.so_don_hang}) — sẽ được ẩn danh, không xoá</h3>
    <div class="rows">${don || '<p class="empty">Không có.</p>'}</div>
    <h3 class="subhead">Hội thoại (${d.so_hoi_thoai}) — sẽ bị xoá hẳn cùng mọi tin nhắn</h3>
    <div class="rows">${hoi || '<p class="empty">Không có.</p>'}</div>
    <h3 class="subhead">Hồ sơ khách (${d.so_ho_so || 0}) — ẩn danh; ghi chú, nhãn xoá hẳn;
      danh tính từng kênh thay bằng khoá ẩn danh</h3>
    <div class="rows">${hs || '<p class="empty">Không có.</p>'}</div>
    <div class="danger">
      <div class="danger__head">Thực hiện yêu cầu xoá — không hoàn tác được</div>
      <div class="kit__note">Đơn hàng giữ lại mã đơn, sản phẩm và số tiền cho sổ sách;
        tên, số điện thoại và địa chỉ bị thay bằng dấu ẩn danh. Hội thoại và tin nhắn
        xoá hẳn. Mọi lần xoá đều được ghi vào nhật ký kèm căn cứ pháp lý.</div>
      ${pdpdKhoiXoa(d)}
    </div>`;

  /* Xin phiếu duyệt. Nút này CHỈ hiện khi chưa có phiếu — có phiếu rồi mà
     vẫn cho bấm là mỗi cú bấm lỡ tay thành một phiếu treo, và người duyệt
     không biết phiếu nào mới là phiếu đang có hiệu lực. */
  $("#pdpdXinDuyet")?.addEventListener("click", async () => {
    const t = await hoiHop({
      tieu_de: "Xin duyệt xoá dữ liệu",
      phu: `Số ${d.so_dien_thoai}. Chưa xoá gì cả — một người KHÁC phải duyệt phiếu này `
         + "ở khối “Phiếu duyệt xoá” bên dưới. Lý do đi vào nhật ký kiểm toán.",
      truong: [{ name: "ly_do", label: "Lý do", value: "Khách yêu cầu xoá dữ liệu",
                 required: true, maxlength: 300 }],
      nut: "Xin duyệt",
    });
    if (!t || !t.ly_do) return;
    try {
      const r = await api(`/pdpd/${encodeURIComponent(d.so_dien_thoai)}/xin-duyet`, {
        method: "POST", body: JSON.stringify({ ly_do: t.ly_do }),
      });
      toast(r.da_co_san ? "Số này đã có phiếu đang chờ duyệt."
        : "Đã tạo phiếu. Một người khác cần duyệt ở khối bên dưới.");
      loadRetention();
      $("#pdpdform").requestSubmit();     // vẽ lại khối xoá theo trạng thái mới
    } catch (err) { toast(err.message, true); }
  });

  $("#pdpdDelete")?.addEventListener("click", async () => {
    const btn = $("#pdpdDelete");
    btn.disabled = true;
    try {
      const r = await api(`/pdpd/${encodeURIComponent(d.so_dien_thoai)}/xoa`, {
        method: "POST",
        body: JSON.stringify({
          xac_nhan_sdt: $("#pdpdConfirm").value,
          ly_do: $("#pdpdReason").value || "khách yêu cầu",
        }),
      });
      $("#pdpdOut").innerHTML = `<p class="kit__note">${esc(r.ghi_chu)}</p>`;
      toast("Đã thực hiện yêu cầu xoá.");
      loadPdpdPolicy(); loadEvents();
    } catch (err) {
      toast(err.message, true); btn.disabled = false;
    }
  });
});

/* ---------------- cổng đăng nhập ---------------- */

// Dashboard đọc PII khách hàng và gửi tin nhân danh doanh nghiệp. Không
// vẽ gì cho tới khi biết chắc có phiên hợp lệ.
async function kiemPhien() {
  try {
    const nguoi = await api("/toi");
    // Bộ lọc "Khách của tôi" so `owner_user_id` với id này. Không nhớ lại
    // đây thì bộ lọc ấy luôn rỗng — và rỗng trông hệt như "chưa ai giao
    // khách cho bạn", nên không ai nhận ra là nó hỏng.
    state.toiId = nguoi.id;
    state.toiQuyen = new Set(nguoi.quyen || []);
    $("#cong").classList.add("is-off");
    const nhan = $("#rail-nguoi");
    if (nhan) nhan.innerHTML =
      `${esc(nguoi.ho_ten || nguoi.ten_dang_nhap)}`
      + ` · <a href="#" id="doimk" style="color:inherit">đổi mật khẩu</a>`
      + ` · <a href="#" id="haibuoc" style="color:inherit">bảo mật 2 bước</a>`
      + ` · <a href="#" id="logout" style="color:inherit">thoát</a>`;
    const doi = $("#doimk");
    if (doi) doi.addEventListener("click", (e) => {
      e.preventDefault();
      $("#mkerr").textContent = "";
      $("#congMk").classList.remove("is-off");
      $("#mkform").mat_khau_moi.focus();
    });
    const out = $("#logout");
    if (out) out.addEventListener("click", async (e) => {
      e.preventDefault();
      await api("/dang-xuat", { method: "POST" });
      location.reload();
    });
    return true;
  } catch {
    $("#cong").classList.remove("is-off");
    return false;
  }
}

$("#mkhuy")?.addEventListener("click", (e) => {
  e.preventDefault();
  $("#mkform").reset();
  $("#congMk").classList.add("is-off");
});

/*
 * Đổi mật khẩu của chính mình.
 *
 * Ô "gõ lại" kiểm ở đây chứ không gửi lên máy chủ: gõ nhầm mật khẩu mới
 * rồi bị đá ra khỏi mọi thiết bị là một tình huống không lối thoát cho
 * người không phải quản trị — họ không tự mở lại được.
 *
 * Đổi xong máy chủ xoá mọi phiên, kể cả phiên đang dùng. Nên tải lại trang
 * để về màn đăng nhập, thay vì để người dùng bấm tiếp rồi gặp 401 ở một
 * thao tác ngẫu nhiên nào đó và tưởng hệ thống hỏng.
 */
$("#mkform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const d = Object.fromEntries(new FormData(f).entries());
  if (d.mat_khau_moi !== d.nhac_lai) {
    $("#mkerr").textContent = "Hai ô không giống nhau.";
    return;
  }
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    await api("/toi/doi-mat-khau", {
      method: "POST",
      body: JSON.stringify({ mat_khau_moi: d.mat_khau_moi }),
    });
    // Không alert(): hộp của trình duyệt chặn cả trang và trông như lỗi.
    // Toast rồi tải lại sau một nhịp — đủ để đọc, không đủ để bấm tiếp.
    toast("Đã đổi mật khẩu. Đăng nhập lại bằng mật khẩu mới.");
    setTimeout(() => location.reload(), 1400);
  } catch (err) {
    $("#mkerr").textContent = err.message;
    nut.disabled = false;
  }
});

$("#loginform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  $("#loginerr").textContent = "";
  try {
    await api("/dang-nhap", { method: "POST", body: JSON.stringify(f) });
    location.reload();
  } catch (err) {
    // Thông báo giữ nguyên như máy chủ trả về — không tách "sai tên" khỏi
    // "sai mật khẩu", vì tách ra là chỉ cho người dò biết tên nào có thật.
    $("#loginerr").textContent = err.message || "Đăng nhập không thành công";
    // Mật khẩu đúng, tài khoản bật 2FA: hiện ô mã và giữ nguyên chữ đã gõ.
    if (err.chi_tiet && err.chi_tiet.can_ma_2fa) {
      $("#loginMa").hidden = false;
      e.target.ma_2fa.focus();
    }
    btn.disabled = false;
  }
});

/* ---------------- tầm nhìn khách của người khác ---------------- */

async function loadTamNhin() {
  const d = await api("/tam-nhin-khach");
  /* Mỗi mức hiện kèm HỆ QUẢ, không chỉ tên.
   *
   * Một ô chọn bốn giá trị mà không giải thích thì người ta chọn bừa rồi
   * không hiểu vì sao nhân viên kêu mất khách — và người bị gọi đầu tiên
   * là người vừa triển khai. */
  $("#tamnhin").innerHTML = d.cac_muc.map((m) => `
    <label class="row tamnhin__o">
      <span class="row__flag row__flag--${m.ma === d.muc ? "auto" : "assist"}"></span>
      <span class="row__main">
        <b><input type="radio" name="tamnhin" value="${esc(m.ma)}"${
          m.ma === d.muc ? " checked" : ""}> ${esc(m.nhan)}${
          m.ma === d.mac_dinh ? ' <span class="pill">mặc định</span>' : ""}</b>
        <span class="row__sub">${esc(m.he_qua)}</span>
      </span>
    </label>`).join("");
}

$("#tamnhin")?.addEventListener("change", async (e) => {
  const o = e.target.closest('input[name="tamnhin"]');
  if (!o) return;
  try {
    await api("/tam-nhin-khach", {
      method: "PUT", body: JSON.stringify({ muc: o.value }),
    });
    toast("Đã đổi. Áp dụng từ lần tải màn Khách hàng kế tiếp.");
    await loadTamNhin();
  } catch (err) { toast(err.message, true); await loadTamNhin(); }
});

/* ---------------- công việc ---------------- */

const congViec = { trangThai: [], uuTien: [] };

function cvCoTrangThai(v) {
  /* Cờ màu theo TÌNH TRẠNG THẬT, không theo trạng thái danh nghĩa.
     Một việc "đang làm" nhưng đã quá hạn ba ngày thì không phải màu xanh. */
  if (v.qua_han) return "halt";
  if (v.trang_thai === "xong") return "auto";
  if (v.trang_thai === "huy") return "assist";
  return v.uu_tien === "gap" || v.uu_tien === "cao" ? "assist" : "auto";
}

function cvDong(v, nhanTT, nhanUT) {
  const chu = v.nguoi_nhan_ten
    ? `<span class="pill">${esc(v.nguoi_nhan_ten)}</span>`
    : '<span class="pill pill--warn">chưa giao</span>';
  const han = v.han
    ? `<span class="pill${v.qua_han ? " pill--warn" : ""}">${
        v.qua_han ? "quá hạn " : "hạn "}${hanDoc(v.han)}</span>`
    : "";
  return `<div class="row" data-cv="${esc(v.id)}">
    <span class="row__flag row__flag--${cvCoTrangThai(v)}"></span>
    <div class="row__main">
      <b>${esc(v.tieu_de)}${v.nguon === "agent"
        ? ' <span class="pill">agent chuyển</span>' : ""}</b>
      <span class="row__sub">${esc(nhanTT[v.trang_thai] || v.trang_thai)} · ${
        esc(nhanUT[v.uu_tien] || v.uu_tien)}${
        v.khach_ten ? " · " + esc(v.khach_ten) : ""}${
        v.mo_ta ? " · " + esc(v.mo_ta.slice(0, 90)) : ""}</span>
    </div>
    <div class="row__side">
      <span>${chu} ${han}</span>
      <span class="row__nut">
        ${v.trang_thai !== "xong"
          ? `<button type="button" class="btn btn--sm btn--ghost" data-cvxong="${esc(v.id)}">Xong</button>`
          : `<button type="button" class="btn btn--sm btn--ghost" data-cvmolai="${esc(v.id)}">Mở lại</button>`}
        <button type="button" class="btn btn--sm btn--ghost" data-cvnhan="${esc(v.id)}">Nhận</button>
        <button type="button" class="btn btn--sm btn--ghost" data-cvsua="${esc(v.id)}">Sửa</button>
      </span>
    </div>
  </div>`;
}

/* GIAO VIỆC, ĐỔI ƯU TIÊN, ĐỔI HẠN, HUỶ — bốn việc API đã làm được từ lâu
 * mà màn hình không có đường nào gọi tới.
 *
 * Hệ quả đo được 15.09.2026: quyền `cong_viec.giao` nằm trong danh mục,
 * cấp được cho vai trò, nhưng KHÔNG cách nào dùng — người trực chỉ tự nhận
 * việc về mình được, không đẩy sang đồng nghiệp được. Trưởng ca muốn phân
 * việc thì phải gọi điện bảo nhau, và màn Công việc thành một danh sách
 * chỉ để đọc. Cùng lớp lỗi với `manager` kênh ở màn Nhân sự: quyền có,
 * cửa không.
 *
 * Một nút "Sửa" mở một hộp cho cả bốn, thay vì bốn nút trên mỗi dòng —
 * dòng việc đã có ba nút rồi, thêm bốn nữa là không ai tìm thấy gì.
 */
async function cvMoSua(id) {
  const v = (congViec.ds || []).find((x) => x.id === id);
  if (!v) return;
  const giaoDuoc = state.toiQuyen.has("cong_viec.giao");

  /* Danh sách người chỉ tải khi CÓ quyền giao và CÓ quyền đọc người dùng.
     Thiếu quyền đọc mà vẫn gọi là một toast lỗi đỏ mỗi lần bấm Sửa. */
  let nguoiChon = null;
  if (giaoDuoc && state.toiQuyen.has("nguoi_dung.doc")) {
    try {
      const ds = (await api("/nguoi-dung")).nguoi_dung || [];
      nguoiChon = [{ value: "", label: "— chưa giao cho ai —" }].concat(
        ds.filter((n) => !n.khoa).map((n) => ({
          value: n.id, label: n.ho_ten || n.ten_dang_nhap })));
    } catch { nguoiChon = null; }
  }

  const truong = [
    { name: "uu_tien", label: "Mức ưu tiên", type: "select",
      value: v.uu_tien,
      options: congViec.uuTien.map((u) => ({ value: u.ma, label: u.nhan })) },
    { name: "han", label: "Hạn", type: "date",
      hint: "để trống là bỏ hạn",
      value: v.han ? String(v.han).slice(0, 10) : "" },
    { name: "trang_thai", label: "Trạng thái", type: "select",
      value: v.trang_thai,
      options: congViec.trangThai.map((t) => ({ value: t.ma, label: t.nhan })) },
  ];
  if (nguoiChon) {
    truong.splice(2, 0, { name: "nguoi_nhan", label: "Người phụ trách",
                          type: "select", value: v.nguoi_nhan || "",
                          options: nguoiChon });
  }

  const d = await hoiHop({
    tieu_de: v.tieu_de,
    phu: giaoDuoc ? "" : "Bạn không có quyền giao việc cho người khác — "
                         + "đổi được ưu tiên, hạn và trạng thái.",
    truong, nut: "Lưu",
  });
  if (!d) return;

  const than = { uu_tien: d.uu_tien, trang_thai: d.trang_thai };
  // Phân biệt "không gửi" với "gửi rỗng": máy chủ cần cờ riêng mới xoá được
  // hạn và thu hồi được người nhận (xem SuaIn trong agent/api/cong_viec.py).
  if (d.han) than.han = new Date(d.han + "T23:59:59").toISOString();
  else than.xoa_han = true;
  if (nguoiChon) {
    if (d.nguoi_nhan) than.nguoi_nhan = d.nguoi_nhan;
    else than.xoa_nguoi_nhan = true;
  }
  try {
    await api(`/cong-viec/${id}`, { method: "PUT", body: JSON.stringify(than) });
    toast("Đã lưu việc.");
    await loadCongViec();
  } catch (e) { toast(e.message, true); }
}

async function loadCongViec() {
  const q = new URLSearchParams();
  if (state.cvTrangThai) q.set("trang_thai", state.cvTrangThai);
  if (state.cvCuaToi) q.set("cua_toi", "true");
  const d = await api(`/cong-viec?${q}`);
  congViec.trangThai = d.trang_thai;
  congViec.uuTien = d.uu_tien;
  congViec.ds = d.cong_viec;
  const nhanTT = Object.fromEntries(d.trang_thai.map((t) => [t.ma, t.nhan]));
  const nhanUT = Object.fromEntries(d.uu_tien.map((t) => [t.ma, t.nhan]));

  /* Chỉ số trên thanh điều hướng đếm việc CHƯA XONG, không đếm tổng.
     Tổng thì chỉ tăng, và một con số chỉ tăng là con số không ai nhìn. */
  const chuaXong = d.cong_viec.filter(
    (v) => v.trang_thai === "moi" || v.trang_thai === "dang_lam").length;
  $("#c-congviec").textContent = chuaXong || "";
  $("#cv-ds").innerHTML = d.cong_viec.length
    ? d.cong_viec.map((v) => cvDong(v, nhanTT, nhanUT)).join("")
    : '<p class="empty">Không có việc nào trong bộ lọc này.</p>';
}

$("#cv-loc")?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-cvloc], [data-cvtoi]");
  if (!chip) return;
  if (chip.dataset.cvtoi) {
    state.cvCuaToi = !state.cvCuaToi;
    chip.classList.toggle("is-on", state.cvCuaToi);
  } else {
    state.cvTrangThai = chip.dataset.cvloc;
    $$("#cv-loc [data-cvloc]").forEach((c) => c.classList.toggle("is-on", c === chip));
  }
  loadCongViec();
});

$("#cv-them")?.addEventListener("click", async () => {
  const d = await hoiHop({
    tieu_de: "Việc mới",
    truong: [
      { name: "tieu_de", label: "Việc cần làm", required: true, maxlength: 200,
        placeholder: "Gọi lại chị Hoa xác nhận đơn" },
      { name: "han", label: "Hạn", type: "date", hint: "để trống nếu không có" },
    ],
    nut: "Thêm việc",
  });
  if (!d || !d.tieu_de) return;
  try {
    await api("/cong-viec", {
      method: "POST",
      body: JSON.stringify({
        tieu_de: d.tieu_de,
        // Hạn "ngày X" nghĩa là hết ngày X theo giờ máy người dùng, không
        // phải 0h UTC (= 7h sáng VN): việc hạn hôm nay mà báo quá hạn từ
        // sáng là báo sai.
        han: d.han ? new Date(d.han + "T23:59:59").toISOString() : null,
      }),
    });
    toast("Đã thêm việc.");
    await loadCongViec();
  } catch (e) { toast(e.message, true); }
});

$("#cv-ds")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-cvsua]");
  if (sua) { await cvMoSua(sua.dataset.cvsua); return; }
  const xong = e.target.closest("[data-cvxong]");
  const molai = e.target.closest("[data-cvmolai]");
  const nhan = e.target.closest("[data-cvnhan]");
  const than = xong ? { trang_thai: "xong" }
    : molai ? { trang_thai: "dang_lam" }
    : nhan ? { nguoi_nhan: state.toiId, trang_thai: "dang_lam" } : null;
  if (!than) return;
  const id = (xong || molai || nhan).dataset.cvxong
    || (xong || molai || nhan).dataset.cvmolai
    || (xong || molai || nhan).dataset.cvnhan;
  try {
    await api(`/cong-viec/${id}`, { method: "PUT", body: JSON.stringify(than) });
    toast(xong ? "Đã đánh dấu xong." : molai ? "Đã mở lại." : "Bạn đã nhận việc này.");
    await loadCongViec();
  } catch (err) { toast(err.message, true); }
});

/* ---------------- hồ sơ agent ---------------- */

const hoSoAgent = { ds: [], toanCuc: null };

async function loadHoSoAgent() {
  const d = await api("/ho-so-agent");
  hoSoAgent.ds = d.ho_so;
  hoSoAgent.toanCuc = d.toan_cuc;
  $("#hsa-toancuc").textContent =
    `toàn cục: ngưỡng ${d.toan_cuc.nguong_tu_tin} · trần ${usd(d.toan_cuc.tran_chi_phi)}`;

  $("#hsa-ds").innerHTML = d.ho_so.length ? d.ho_so.map((h) => {
    /* Hiện cả giá trị ĐÃ LƯU lẫn giá trị CÓ HIỆU LỰC khi chúng khác nhau.
     *
     * Chỉ hiện giá trị đã lưu là màn hình nói dối: người dùng gõ 0.3, màn
     * hình hiện 0.3, hệ thống chạy bằng 0.55, và không gì nói cho họ biết
     * vì sao agent vẫn chuyển người sớm như trước. */
    const bi_siet = (h.nguong_tu_tin !== null && h.nguong_tu_tin !== h.nguong_hieu_luc)
      || (h.tran_chi_phi !== null && h.tran_chi_phi !== h.tran_hieu_luc);
    return `<div class="row">
      <span class="row__flag row__flag--${h.bat ? "auto" : "assist"}"></span>
      <div class="row__main">
        <b>${esc(h.ten)}${h.bat ? "" : ' <span class="pill">đang tắt</span>'}${
          bi_siet ? ' <span class="pill pill--warn">đã siết về ngưỡng toàn cục</span>' : ""}</b>
        <span class="row__sub">${esc(h.mo_ta || "—")}${
          h.huong_dan ? " · có hướng dẫn riêng" : ""}</span>
      </div>
      <div class="row__side">
        <span><span class="pill">ngưỡng ${h.nguong_hieu_luc}</span>
          <span class="pill">trần ${usd(h.tran_hieu_luc)}</span>
          <span class="pill">${h.so_kenh} kênh</span></span>
        <span class="row__nut">
          <button type="button" class="btn btn--sm btn--ghost" data-hsasua="${esc(h.id)}">Sửa</button>
          <button type="button" class="btn btn--sm btn--ghost" data-hsaxoa="${esc(h.id)}">Xoá</button>
        </span>
      </div>
    </div>`;
  }).join("")
    : '<p class="empty">Chưa có hồ sơ nào. Mọi kênh đang chạy bằng cấu hình mặc định.</p>';
}

/* Form thay cho năm hộp prompt() nối nhau — hướng dẫn 4000 ký tự không
 * viết được trong một ô một dòng, và bấm Huỷ ở hộp thứ tư là mất sạch ba
 * hộp trước. Form là phần tử tĩnh trong index.html, nên vòng làm mới 6 giây
 * dựng lại `#hsa-ds` không đụng tới thứ người ta đang gõ. */
function hsaMoForm(cu) {
  const f = $("#hsaForm");
  f.reset();
  f.ho_so_id.value = cu ? cu.id : "";
  f.ten.value = cu ? cu.ten : "";
  f.mo_ta.value = cu ? cu.mo_ta || "" : "";
  f.huong_dan.value = cu ? cu.huong_dan || "" : "";
  f.nguong_tu_tin.value = cu && cu.nguong_tu_tin !== null ? String(cu.nguong_tu_tin) : "";
  f.tran_chi_phi.value = cu && cu.tran_chi_phi !== null ? String(cu.tran_chi_phi) : "";
  f.bat.checked = cu ? !!cu.bat : true;
  $("#hsaGhiChu").textContent = `Toàn cục đang là ngưỡng ${hoSoAgent.toanCuc.nguong_tu_tin} · trần ${
    usd(hoSoAgent.toanCuc.tran_chi_phi)}. Ở đây chỉ siết thêm được: đặt lỏng hơn thì hệ thống vẫn chạy bằng toàn cục.`;
  f.classList.remove("is-hidden");
  f.ten.focus();
}

$("#hsa-them")?.addEventListener("click", () => hsaMoForm(null));
$("#hsaHuy")?.addEventListener("click", () => $("#hsaForm").classList.add("is-hidden"));

$("#hsaForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const than = {
    ten: f.ten.value.trim(), mo_ta: f.mo_ta.value.trim(),
    huong_dan: f.huong_dan.value.trim(),
    nguong_tu_tin: f.nguong_tu_tin.value.trim() ? Number(f.nguong_tu_tin.value) : null,
    tran_chi_phi: f.tran_chi_phi.value.trim() ? Number(f.tran_chi_phi.value) : null,
    bat: f.bat.checked,
  };
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    const d = f.ho_so_id.value
      ? await api(`/ho-so-agent/${f.ho_so_id.value}`, { method: "PUT", body: JSON.stringify(than) })
      : await api("/ho-so-agent", { method: "POST", body: JSON.stringify(than) });
    toast(d.nguong_hieu_luc !== d.nguong_tu_tin && d.nguong_tu_tin !== null
      ? `Đã lưu. Ngưỡng bị siết về ${d.nguong_hieu_luc} (mức toàn cục).`
      : "Đã lưu hồ sơ.");
    f.classList.add("is-hidden");
    await loadHoSoAgent();
  } catch (err) { toast(err.message, true); } finally { nut.disabled = false; }
});

$("#hsa-ds")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-hsasua]");
  if (sua) {
    hsaMoForm(hoSoAgent.ds.find((h) => h.id === sua.dataset.hsasua));
    $("#hsaForm").scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }
  const xoa = e.target.closest("[data-hsaxoa]");
  if (!xoa) return;
  const h = hoSoAgent.ds.find((x) => x.id === xoa.dataset.hsaxoa);
  /* Nói SỐ KÊNH bị ảnh hưởng và điều gì xảy ra với chúng — không hỏi "bạn
     có chắc không". Kênh không ngừng trả lời, chúng rơi về mặc định, và
     đó chính là thứ người bấm cần biết trước khi bấm. */
  if (!confirm(h.so_kenh
    ? `Xoá hồ sơ “${h.ten}”? ${h.so_kenh} kênh đang dùng sẽ quay về cấu hình mặc định — chúng KHÔNG ngừng trả lời.`
    : `Xoá hồ sơ “${h.ten}”? Chưa kênh nào dùng.`)) return;
  try {
    await api(`/ho-so-agent/${h.id}`, { method: "DELETE" });
    toast("Đã xoá hồ sơ.");
    await loadHoSoAgent();
  } catch (err) { toast(err.message, true); }
});

/* ---------------- trường thông tin khách tuỳ biến ---------------- */

const truongKhach = { ds: [], kieu: [] };

async function loadTruongKhach() {
  const d = await api("/truong-khach");
  truongKhach.ds = d.truong;
  truongKhach.kieu = d.kieu;
  const nhanKieu = Object.fromEntries(d.kieu.map((k) => [k.ma, k.nhan]));
  $("#truong-dem").textContent = `${d.truong.length}/${d.toi_da} trường`;
  $("#truong-ds").innerHTML = d.truong.length ? d.truong.map((t) => `
    <div class="row">
      <span class="row__flag row__flag--${t.bat_buoc ? "assist" : "auto"}"></span>
      <div class="row__main">
        <b>${esc(t.nhan)}${t.bat_buoc ? ' <span class="pill pill--warn">bắt buộc</span>' : ""}</b>
        <span class="row__sub"><code>${esc(t.ma)}</code> · ${esc(nhanKieu[t.kieu] || t.kieu)}${
          (t.lua_chon || []).length ? " · " + t.lua_chon.map(esc).join(" / ") : ""}${
          t.hien_danh_sach ? " · hiện ở danh sách" : ""}</span>
      </div>
      <div class="row__side">
        <span class="row__nut">
          <button type="button" class="btn btn--sm btn--ghost" data-truongsua="${esc(t.ma)}">Sửa</button>
          <button type="button" class="btn btn--sm btn--ghost" data-truongxoa="${esc(t.ma)}">Xoá</button>
        </span>
      </div>
    </div>`).join("")
    : '<p class="empty">Chưa có trường nào. Bấm <b>Thêm trường</b> để hỏi khách thêm thông tin.</p>';
}

/* Form thay cho chuỗi prompt()/confirm(). Kiểu là ô CHỌN dựng từ danh mục
 * máy chủ trả về, nên không gõ sai được; khi sửa, mã và kiểu bị khoá đúng
 * như máy chủ từ chối (xem TruongSuaIn). */
function truongMoForm(t) {
  const f = $("#truongForm");
  f.reset();
  $("#truongKieu").innerHTML = truongKhach.kieu
    .map((k) => `<option value="${esc(k.ma)}">${esc(k.nhan)}</option>`).join("");
  f.ma.value = t ? t.ma : "";
  f.ma.disabled = !!t;
  f.nhan.value = t ? t.nhan : "";
  f.kieu.value = t ? t.kieu : (truongKhach.kieu[0] || {}).ma || "";
  f.kieu.disabled = !!t;
  f.lua_chon.value = t ? (t.lua_chon || []).join(", ") : "";
  f.goi_y.value = t ? t.goi_y || "" : "";
  f.thu_tu.value = t ? t.thu_tu : 100;
  f.bat_buoc.checked = t ? !!t.bat_buoc : false;
  f.hien_danh_sach.checked = t ? !!t.hien_danh_sach : false;
  f.dataset.sua = t ? t.ma : "";
  f.classList.remove("is-hidden");
  (t ? f.nhan : f.ma).focus();
}

$("#truong-them")?.addEventListener("click", () => truongMoForm(null));
$("#truongHuy")?.addEventListener("click", () => $("#truongForm").classList.add("is-hidden"));

$("#truongForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const kieu = f.kieu.value;
  const lua_chon = (kieu === "chon" || kieu === "nhieu_chon")
    ? f.lua_chon.value.split(",").map((s) => s.trim()).filter(Boolean) : [];
  const chung = {
    nhan: f.nhan.value.trim(), goi_y: f.goi_y.value.trim(),
    bat_buoc: f.bat_buoc.checked, lua_chon,
    hien_danh_sach: f.hien_danh_sach.checked,
    thu_tu: Number(f.thu_tu.value) || 100,
  };
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    if (f.dataset.sua) {
      await api(`/truong-khach/${f.dataset.sua}`, { method: "PUT", body: JSON.stringify(chung) });
      toast("Đã lưu trường.");
    } else {
      await api("/truong-khach", {
        method: "POST", body: JSON.stringify({ ma: f.ma.value.trim(), kieu, ...chung }),
      });
      toast("Đã thêm. Ô nhập hiện ngay trong hồ sơ mọi khách.");
    }
    f.classList.add("is-hidden");
    await loadTruongKhach();
  } catch (err) { toast(err.message, true); } finally { nut.disabled = false; }
});

$("#truong-ds")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-truongsua]");
  if (sua) {
    truongMoForm(truongKhach.ds.find((x) => x.ma === sua.dataset.truongsua));
    $("#truongForm").scrollIntoView({ behavior: "smooth", block: "nearest" });
    return;
  }

  const xoa = e.target.closest("[data-truongxoa]");
  if (!xoa) return;
  const ma = xoa.dataset.truongxoa;
  try {
    await api(`/truong-khach/${ma}`, { method: "DELETE" });
    toast("Đã xoá trường.");
    await loadTruongKhach();
  } catch (err) {
    /* Máy chủ trả 409 kèm SỐ hồ sơ sắp mất giá trị. Hỏi lại bằng đúng con
       số ấy, không hỏi "bạn có chắc không" — câu ấy không mang thông tin
       nào và người ta bấm OK theo phản xạ. */
    if (err.ma === 409 && confirm(`${err.message}\n\nXoá luôn các giá trị ấy?`)) {
      try {
        const d = await api(`/truong-khach/${ma}?xoa_ca_gia_tri=true`,
                            { method: "DELETE" });
        toast(`Đã xoá trường và ${d.so_ho_so_da_xoa_gia_tri} giá trị.`);
        await loadTruongKhach();
      } catch (e2) { toast(e2.message, true); }
    } else if (err.ma !== 409) {
      toast(err.message, true);
    }
  }
});

