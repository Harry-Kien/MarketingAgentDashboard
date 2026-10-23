/* ---------------- nhân sự: vai trò và quyền ---------------- */
/*
 * VÌ SAO MÀN NÀY HIỆN "QUYỀN THẬT" CHỨ KHÔNG CHỈ HIỆN VAI TRÒ
 *
 * Một người có thể mang nhiều vai trò, và vai trò `Quản trị` lấy quyền
 * thẳng từ mã chứ không từ CSDL. Nhìn danh sách vai trò thì không suy ra
 * được người ấy làm được gì — và khi có ai đó vào được màn lẽ ra không
 * được, câu hỏi đầu tiên luôn là "vì sao".
 *
 * `GET /api/nguoi-dung/{id}/quyen` trả lời đúng câu ấy: từng quyền, kèm
 * tên vai trò đã cấp nó.
 */

const nhanSu = { vaiTro: [], danhMuc: {}, dangSua: null };

function nsDongNguoi(n) {
  const vai = (n.vai_tro_ten || []).map((t) => `<span class="pill">${esc(t)}</span>`).join(" ")
    || '<span class="pill pill--warn">chưa có vai trò nào</span>';
  const coVai = (n.vai_tro_ten || []).length > 0;
  /* Số KÊNH người này được vào — trục lọc thứ hai, và là trục hay bị quên.
     Quản trị thấy mọi kênh nhờ quyền `*.xem_tat_ca`, nên với họ con số này
     không phải cảnh báo. Với người khác, 0 kênh = đăng nhập được mà không
     thấy hội thoại nào, khách nào — kể cả khách đã giao cho chính họ. */
  const laQuanTri = (n.vai_tro_ten || []).includes("Quản trị");
  const soKenh = Number(n.so_kenh || 0);
  const kenh = laQuanTri
    ? '<span class="pill">mọi kênh</span>'
    : `<span class="pill${soKenh ? "" : " pill--warn"}">${soKenh ? `${soKenh} kênh` : "chưa vào kênh nào"}</span>`;
  /* AI ĐỌC ĐƯỢC SỐ ĐIỆN THOẠI KHÁCH — con số quan trọng nhất của màn này về
     mặt bảo mật. Trước đây muốn biết phải tự đọc bảng trong CSDL, nên trên
     thực tế không ai biết. Quản trị thì hiển nhiên đọc được, không cần nhắc. */
  const soPii = Number(n.so_kenh_pii || 0);
  const pii = laQuanTri || !soPii ? ""
    : ` <span class="pill pill--warn" title="Trưởng nhóm của ${soPii} kênh: đọc được số điện thoại và email của khách trong những kênh ấy">đọc được SĐT · ${soPii} kênh</span>`;
  return `<div class="row" data-nguoi="${esc(n.id)}">
    <span class="row__flag row__flag--${n.khoa ? "halt" : coVai && (soKenh || laQuanTri) ? "auto" : "assist"}"></span>
    <div class="row__main">
      <b>${esc(n.ho_ten || n.ten_dang_nhap)}</b>
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.khoa ? " · đã khoá" : ""}${
        n.dang_nhap_cuoi ? " · vào lần cuối " + clock(n.dang_nhap_cuoi) : " · chưa đăng nhập lần nào"}</span>
    </div>
    <div class="row__side">
      <span>${vai} ${kenh}${pii}</span>
      <span class="row__nut">
        <button type="button" class="btn btn--sm btn--ghost" data-xemquyen="${esc(n.id)}">Xem quyền</button>
        <button type="button" class="btn btn--sm btn--ghost" data-ganvai="${esc(n.id)}">Gán vai trò</button>
        <button type="button" class="btn btn--sm btn--ghost" data-gankenh="${esc(n.id)}">Kênh</button>
        <button type="button" class="btn btn--sm btn--ghost" data-khoa="${esc(n.ten_dang_nhap)}"
          data-dangkhoa="${n.khoa ? "1" : ""}">${n.khoa ? "Mở khoá" : "Khoá"}</button>
      </span>
    </div>
  </div>`;
}

function nsDongVaiTro(v) {
  /* Vai trò hệ thống hiện khoá và KHÔNG có nút xoá.
   *
   * Nút xoá bấm vào rồi báo 409 cũng "an toàn", nhưng nó dạy người dùng
   * rằng thông báo lỗi là chuyện bình thường — và lần sau họ bấm qua một
   * cảnh báo thật. */
  const soQuyen = v.toan_quyen
    ? "toàn bộ quyền (lấy từ mã)"
    : `${v.quyen.length} quyền`;
  const nut = v.toan_quyen
    ? ""
    : `<button type="button" class="btn btn--sm btn--ghost" data-suavai="${esc(v.id)}">Sửa</button>`
      + (v.he_thong ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-xoavai="${esc(v.id)}">Xoá</button>`);
  return `<div class="row">
    <span class="row__flag row__flag--${v.toan_quyen ? "halt" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(v.ten)}${v.he_thong ? ' <span class="pill">dựng sẵn</span>' : ""}</b>
      <span class="row__sub">${esc(v.mo_ta || "—")}</span>
    </div>
    <div class="row__side">
      <span><span class="pill">${soQuyen}</span> <span class="pill">${v.so_nguoi} người</span></span>
      ${nut ? `<span class="row__nut">${nut}</span>` : ""}
    </div>
  </div>`;
}

async function loadNhanSu() {
  const [nguoi, vt, dm] = await Promise.all([
    api("/nguoi-dung"), api("/vai-tro"), api("/quyen"),
  ]);
  nhanSu.vaiTro = vt.vai_tro;
  nhanSu.danhMuc = dm.nhom;

  const ds = nguoi.nguoi_dung || nguoi.items || nguoi;
  /* Vòng làm mới 6 giây gọi lại hàm này. Dựng lại danh sách khi một bảng
     tick (vai trò, kênh) đang mở là XOÁ bảng ấy giữa lúc người ta đang tick
     — đo được trên hệ thống thật: bảng biến mất trước khi kịp bấm Lưu.
     Đang mở thì giữ nguyên danh sách; số đếm bên trên vẫn cập nhật. */
  const dangTick = $("#nsNguoi [data-vtbang], #nsNguoi [data-kenhbang]");
  if (!dangTick) {
    $("#nsNguoi").innerHTML = ds.length
      ? ds.map(nsDongNguoi).join("")
      : '<p class="empty">Chưa có nhân viên nào.</p>';
  }
  $("#nsVaiTro").innerHTML = nhanSu.vaiTro.map(nsDongVaiTro).join("");
  const chuaVai = ds.filter((n) => !(n.vai_tro_ten || []).length).length;
  $("#c-nhansu").textContent = chuaVai ? String(chuaVai) : "";
  $("#c-nhansu").title = chuaVai
    ? `${chuaVai} nhân viên chưa được cấp vai trò nào` : "";

  // TỔNG SỐ phải hiện ra. Huy hiệu trên thanh bên đếm số người CHƯA có vai
  // trò — một con số cảnh báo, không phải con số tồn kho. Người vận hành
  // hỏi "có bao nhiêu nhân viên" thì trước đây phải tự đếm bằng mắt.
  const dangLam = ds.filter((n) => !n.khoa).length;
  const daKhoa = ds.length - dangLam;
  $("#nsDem").textContent = [
    `${ds.length} tài khoản`,
    `${dangLam} đang làm`,
    daKhoa ? `${daKhoa} đã khoá` : "",
    chuaVai ? `${chuaVai} chưa có vai trò` : "",
  ].filter(Boolean).join(" · ");

  // Ô vai trò trong form thêm người: dựng lại mỗi lần tải để vai trò vừa
  // tạo xuất hiện ngay, không phải tải lại trang.
  const oVai = $("#nsVaiTroMoi");
  if (oVai) {
    oVai.innerHTML = '<option value="">— chưa gán, cấp sau —</option>'
      + nhanSu.vaiTro.map((v) => `<option value="${esc(v.id)}">${esc(v.ten)}</option>`).join("");
  }
}

function nsVeBangQuyen(dangCo) {
  const co = new Set(dangCo || []);
  return Object.entries(nhanSu.danhMuc).map(([nhom, ds]) => `
    <fieldset class="quyen__nhom">
      <legend>${esc(nhom)}</legend>
      ${ds.map((q) => `<label class="quyen__o">
        <input type="checkbox" name="quyen" value="${esc(q.ma)}"${co.has(q.ma) ? " checked" : ""}>
        <span>${esc(q.nhan)}</span><code>${esc(q.ma)}</code>
      </label>`).join("")}
    </fieldset>`).join("");
}

function nsMoSua(v) {
  nhanSu.dangSua = v;
  $("#nsSuaTieuDe").textContent = v ? `Sửa vai trò “${v.ten}”` : "Tạo vai trò mới";
  const f = $("#nsFormVaiTro");
  f.ten.value = v ? v.ten : "";
  f.mo_ta.value = v ? v.mo_ta : "";
  $("#nsQuyen").innerHTML = nsVeBangQuyen(v ? v.quyen : []);
  $("#nsPanelSua").hidden = false;
  $("#nsPanelSua").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#nsThemVaiTro")?.addEventListener("click", () => nsMoSua(null));
$("#nsHuySua")?.addEventListener("click", () => { $("#nsPanelSua").hidden = true; });

$("#nsFormVaiTro")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const than = {
    ten: f.ten.value.trim(),
    mo_ta: f.mo_ta.value.trim(),
    quyen: $$('input[name="quyen"]:checked', f).map((i) => i.value),
  };
  try {
    if (nhanSu.dangSua) {
      await api(`/vai-tro/${nhanSu.dangSua.id}`, { method: "PUT", body: JSON.stringify(than) });
      toast("Đã lưu vai trò.");
    } else {
      await api("/vai-tro", { method: "POST", body: JSON.stringify(than) });
      toast("Đã tạo vai trò.");
    }
    $("#nsPanelSua").hidden = true;
    await loadNhanSu();
  } catch (err) { toast(err.message, true); }
});

$("#nsVaiTro")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-suavai]");
  if (sua) {
    nsMoSua(nhanSu.vaiTro.find((v) => v.id === sua.dataset.suavai));
    return;
  }
  const xoa = e.target.closest("[data-xoavai]");
  if (!xoa) return;
  const v = nhanSu.vaiTro.find((x) => x.id === xoa.dataset.xoavai);
  /* Nói SỐ NGƯỜI bị ảnh hưởng, không hỏi "bạn có chắc không".
   * "Có chắc không" là câu hỏi không mang thông tin nào — người ta bấm OK
   * theo phản xạ. "3 người sẽ mất các quyền này" thì họ dừng lại. */
  const loi = v.so_nguoi
    ? `Xoá vai trò “${v.ten}”? ${v.so_nguoi} người đang mang nó sẽ mất các quyền này.`
    : `Xoá vai trò “${v.ten}”? Chưa ai được gán vai trò này.`;
  if (!confirm(loi)) return;
  try {
    await api(`/vai-tro/${v.id}`, { method: "DELETE" });
    toast("Đã xoá vai trò.");
    await loadNhanSu();
  } catch (err) { toast(err.message, true); }
});

$("#nsNguoi")?.addEventListener("click", async (e) => {
  /*
   * Khoá / mở khoá ngay trên dòng. API đã có từ lâu nhưng không màn hình
   * nào gọi tới — nghĩa là nhân viên nghỉ việc chỉ chặn được bằng cách vào
   * psql gõ tay, và việc phải gõ tay là việc người ta hoãn lại.
   *
   * Lời xác nhận nói ĐIỀU SẼ XẢY RA (phiên đang mở bị đá ra ngay), không
   * hỏi "có chắc không" — câu ấy không mang thông tin nào.
   */
  const kh = e.target.closest("[data-khoa]");
  if (kh) {
    const ten = kh.dataset.khoa;
    const dangKhoa = !!kh.dataset.dangkhoa;
    const loi = dangKhoa
      ? `Mở khoá “${ten}”? Họ đăng nhập lại được ngay.`
      : `Khoá “${ten}”? Mọi phiên đang mở của họ bị đá ra ngay lập tức.`;
    if (!confirm(loi)) return;
    try {
      await api(`/nguoi-dung/${encodeURIComponent(ten)}/khoa?khoa=${!dangKhoa}`,
                { method: "POST" });
      toast(dangKhoa ? `Đã mở khoá ${ten}.` : `Đã khoá ${ten} và đá mọi phiên.`);
      await loadNhanSu();
    } catch (err) { toast(err.message, true); }
    return;
  }

  const xem = e.target.closest("[data-xemquyen]");
  if (xem) {
    try {
      const d = await api(`/nguoi-dung/${xem.dataset.xemquyen}/quyen`);
      $("#nsGiaiThichTieuDe").textContent =
        `Quyền của ${d.nguoi_dung.ho_ten || d.nguoi_dung.ten_dang_nhap}`;
      const dong = Object.entries(d.quyen);
      $("#nsGiaiThich").innerHTML = dong.length
        ? dong.map(([ma, tuVai]) => `<div class="row">
            <span class="row__flag row__flag--auto"></span>
            <div class="row__main"><b>${esc(ma)}</b>
              <span class="row__sub">cấp bởi: ${esc(tuVai.join(", "))}</span></div>
          </div>`).join("")
        : '<p class="empty">Chưa được cấp quyền nào. Người này đăng nhập được nhưng mọi màn đều trống.</p>';
      $("#nsPanelGiaiThich").hidden = false;
      $("#nsPanelGiaiThich").scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (err) { toast(err.message, true); }
    return;
  }

  const luu = e.target.closest("[data-vtluu]");
  if (luu) {
    const id = luu.dataset.vtluu;
    const ids = $$(`[data-vtbang="${id}"] input:checked`).map((c) => c.value);
    luu.disabled = true;
    try {
      await api(`/nguoi-dung/${id}/vai-tro`, {
        method: "PUT", body: JSON.stringify({ vai_tro: ids }),
      });
      toast(ids.length ? "Đã gán vai trò." : "Đã gỡ hết vai trò — người này vào được nhưng mọi màn đều trống.");
      await loadNhanSu();
    } catch (err) { toast(err.message, true); luu.disabled = false; }
    return;
  }
  const huy = e.target.closest("[data-vthuy]");
  if (huy) { $(`[data-vtbang="${huy.dataset.vthuy}"]`)?.remove(); return; }

  const gan = e.target.closest("[data-ganvai]");
  if (!gan) return;
  const id = gan.dataset.ganvai;
  /* Bảng TICK ngay dưới dòng, không phải hộp thoại bắt gõ tên vai trò cách
     nhau bằng dấu phẩy. Một người có thể mang nhiều vai trò, nên là ô tick
     chứ không phải ô chọn một. Mở bảng thứ hai thì đóng bảng thứ nhất. */
  $$("[data-vtbang]").forEach((b) => b.remove());
  try {
    const hien = await api(`/nguoi-dung/${id}/quyen`);
    const dangCo = new Set(hien.vai_tro);
    const bang = document.createElement("div");
    bang.className = "ns-vaitro";
    bang.dataset.vtbang = id;
    bang.innerHTML = `<fieldset class="quyen__nhom"><legend>Vai trò của ${
        esc(hien.nguoi_dung.ho_ten || hien.nguoi_dung.ten_dang_nhap)}</legend>${
      nhanSu.vaiTro.map((v) => `<label class="quyen__o">
        <input type="checkbox" value="${esc(v.id)}"${dangCo.has(v.ten) ? " checked" : ""}>
        <span>${esc(v.ten)}</span>
        <small>${esc(v.mo_ta || "")}</small></label>`).join("")}
      </fieldset>
      <div class="row__nut">
        <button type="button" class="btn btn--sm btn--primary" data-vtluu="${esc(id)}">Lưu</button>
        <button type="button" class="btn btn--sm btn--ghost" data-vthuy="${esc(id)}">Huỷ</button>
      </div>`;
    gan.closest(".row").insertAdjacentElement("afterend", bang);
  } catch (err) { toast(err.message, true); }
});

$("#nsThemNguoi")?.addEventListener("click", () => {
  $("#nsFormNguoi").classList.toggle("is-hidden");
  if (!$("#nsFormNguoi").classList.contains("is-hidden")) {
    $("#nsFormNguoi").ten_dang_nhap.focus();
  }
});

$("#nsHuyNguoi")?.addEventListener("click", () => {
  $("#nsFormNguoi").reset();
  $("#nsFormNguoi").classList.add("is-hidden");
});

/*
 * Tạo nhân viên và gán vai trò trong MỘT thao tác.
 *
 * Tách hai bước là để lại một khoảng người vừa tạo chưa có quyền gì: họ
 * đăng nhập được, thấy dashboard trống trơn, và không có gì nói cho họ biết
 * vì sao. Người tạo thì tưởng đã xong.
 *
 * Gán vai trò hỏng KHÔNG được nuốt: tài khoản đã tạo rồi, nên phải nói rõ
 * tạo xong nhưng chưa cấp quyền, chứ không phải báo lỗi chung chung khiến
 * người ta bấm tạo lại và gặp "tên đã tồn tại".
 */
$("#nsFormNguoi")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const d = Object.fromEntries(new FormData(f).entries());
  const ten = String(d.ten_dang_nhap || "").trim();
  if (!ten) return;
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    const moi = await api("/nguoi-dung", {
      method: "POST",
      body: JSON.stringify({
        ten_dang_nhap: ten,
        mat_khau: d.mat_khau,
        ho_ten: String(d.ho_ten || "").trim() || ten,
      }),
    });
    if (d.vai_tro_id) {
      try {
        await api(`/nguoi-dung/${moi.id}/vai-tro`, {
          method: "PUT", body: JSON.stringify({ vai_tro: [d.vai_tro_id] }),
        });
        toast(`Đã tạo ${ten} và cấp vai trò. Báo họ đổi mật khẩu ở mục Tôi.`);
      } catch (err) {
        toast(`Đã tạo ${ten} nhưng CHƯA cấp được vai trò: ${err.message}`
          + " — bấm Gán vai trò trên dòng của họ.", true);
      }
    } else {
      toast(`Đã tạo ${ten}. Chưa có vai trò nên họ vào được mà mọi màn đều trống.`);
    }
    /* Vào kênh là bước thứ ba của cùng một thao tác. Hỏng thì nói ra bằng
       đúng hậu quả, không nuốt: tài khoản và vai trò đã có rồi, thứ còn
       thiếu là họ sẽ không thấy hội thoại nào. */
    if (d.moi_kenh) {
      try {
        const ds = await api("/channel-accounts");
        const ids = (Array.isArray(ds) ? ds : []).filter((k) => k.status === "active").map((k) => k.id);
        if (ids.length) {
          await api(`/nguoi-dung/${moi.id}/kenh`, {
            method: "PUT", body: JSON.stringify({ kenh: ids, role: "agent" }),
          });
        } else {
          toast(`Chưa có kênh nào đang hoạt động để cho ${ten} vào — nối kênh xong nhớ bấm Kênh trên dòng của họ.`, true);
        }
      } catch (err) {
        toast(`Đã tạo ${ten} nhưng CHƯA cho vào kênh nào: ${err.message}`
          + " — họ sẽ không thấy hội thoại nào. Bấm Kênh trên dòng của họ.", true);
      }
    }
    f.reset();
    f.classList.add("is-hidden");
    await loadNhanSu();
  } catch (err) {
    toast(err.message, true);
  } finally {
    nut.disabled = false;
  }
});

/* ---------------- nhân sự: kênh được vào ----------------
 *
 * `account_memberships` là trục lọc mà mọi truy vấn hội thoại, khách và bộ
 * định tuyến đều siết qua — và trước đây chỉ được ghi khi ai đó bấm nối
 * kênh. Người được tạo ở màn này là thành viên của 0 kênh: vào được, thấy
 * trống, và không có gì nói vì sao. Bảng tick ngay dưới dòng, hệt bảng vai
 * trò; `owner` (người đã nối kênh) hiện khoá vì đường này không gỡ họ. */
$("#nsNguoi")?.addEventListener("click", async (e) => {
  const luu = e.target.closest("[data-kenhluu]");
  if (luu) {
    const id = luu.dataset.kenhluu;
    const ids = $$(`[data-kenhbang="${id}"] input:checked:not(:disabled)`).map((c) => c.value);
    /* MỨC TRONG KÊNH quyết định người này có đọc được SỐ ĐIỆN THOẠI và
       EMAIL của khách hay không — `manager` thì có, `agent` thì thấy
       `*******456`. Không có ô chọn này thì quản trị KHÔNG có đường nào
       cấp quyền ấy cho một trưởng nhóm, ngoài việc cấp `khach.xem_tat_ca`
       — thứ mở toang danh bạ của MỌI kênh. Đo được 14.09.2026. */
    const role = $(`[data-kenhbang="${id}"] [name=kenhrole]`)?.value || "agent";
    luu.disabled = true;
    try {
      const r = await api(`/nguoi-dung/${id}/kenh`, {
        method: "PUT", body: JSON.stringify({ kenh: ids, role }),
      });
      toast(r.so_thanh_vien
        ? `Đã lưu: vào ${r.so_thanh_vien} kênh.`
        : "Đã gỡ khỏi mọi kênh — người này sẽ không thấy hội thoại nào.");
      await loadNhanSu();
    } catch (err) { toast(err.message, true); luu.disabled = false; }
    return;
  }
  const huy = e.target.closest("[data-kenhhuy]");
  if (huy) { $(`[data-kenhbang="${huy.dataset.kenhhuy}"]`)?.remove(); return; }

  const gan = e.target.closest("[data-gankenh]");
  if (!gan) return;
  const id = gan.dataset.gankenh;
  $$("[data-kenhbang]").forEach((b) => b.remove());
  $$("[data-vtbang]").forEach((b) => b.remove());
  try {
    const d = await api(`/nguoi-dung/${id}/kenh`);
    const TT = { active: "đang hoạt động", pending: "chờ xác minh", degraded: "gián đoạn",
                 reauth_required: "cần nối lại", disabled: "đã tắt" };
    // Mức hiện tại: `owner` (người đã nối kênh) coi như `manager` — cả hai
    // đều đọc được PII, và ô chọn không hạ được owner xuống (máy chủ chặn).
    const mucHienTai = d.kenh.some((k) => k.role === "manager" || k.role === "owner")
      ? "manager" : "agent";
    const bang = document.createElement("div");
    bang.className = "ns-vaitro";
    bang.dataset.kenhbang = id;
    bang.innerHTML = `<fieldset class="quyen__nhom"><legend>Kênh ${
        esc(d.nguoi_dung.ho_ten || d.nguoi_dung.ten_dang_nhap)} được vào</legend>
      <label class="field" style="margin-bottom:10px">
        <span>Mức trong kênh <em class="hint">quyết định có đọc được số điện thoại và email của khách không</em></span>
        <select name="kenhrole">
          <option value="agent"${mucHienTai === "agent" ? " selected" : ""}>Nhân viên — thấy tên khách, số điện thoại bị che (*******456)</option>
          <option value="manager"${mucHienTai === "manager" ? " selected" : ""}>Trưởng nhóm — đọc được đầy đủ số điện thoại và email</option>
        </select>
      </label>${
      d.kenh.length ? d.kenh.map((k) => `<label class="quyen__o">
        <input type="checkbox" value="${esc(k.id)}"${k.thanh_vien ? " checked" : ""}${
          k.role === "owner" ? " disabled" : ""}>
        <span>${esc(k.display_name)}</span>
        <small>${esc(k.channel)} · ${esc(TT[k.status] || k.status)}${
          k.role === "owner" ? " · đã nối kênh này, không gỡ ở đây" : ""}</small></label>`).join("")
      : '<p class="empty">Chưa nối kênh nào. Nối ở màn Kết nối rồi quay lại.</p>'}
      </fieldset>
      <div class="row__nut">
        <button type="button" class="btn btn--sm btn--primary" data-kenhluu="${esc(id)}">Lưu</button>
        <button type="button" class="btn btn--sm btn--ghost" data-kenhhuy="${esc(id)}">Huỷ</button>
      </div>`;
    gan.closest(".row").insertAdjacentElement("afterend", bang);
  } catch (err) { toast(err.message, true); }
});

