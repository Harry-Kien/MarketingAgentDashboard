/* ---------------- đơn hàng ---------------- */

/* Khớp `agent/core/tools.py::TRANG_THAI_DON`. Có test canh hai bên không
   trôi xa nhau — thiếu một nhãn ở đây thì dòng đơn hiện ra chữ kỹ thuật
   trần, thẻ xám, và người trực không hiểu đang nhìn cái gì. */
const ORDER_LABEL = {
  cho_duyet: "Chờ duyệt", da_chot: "Đã chốt", da_huy: "Đã huỷ",
  cho_dong_bo: "Chờ đồng bộ kho", da_giao: "Đã giao",
};
const ORDER_TONE  = {
  cho_duyet: "duyet", da_chot: "chot", da_huy: "huy",
  cho_dong_bo: "duyet", da_giao: "chot",
};
/* Khớp `agent/shipping/models.InternalShippingStatus`. */
const NHAN_GIAO = {
  delivering: "đang giao", delivered: "đã giao",
  delivery_failed: "giao thất bại", returned: "đã hoàn về",
};
const vnd = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

$$("#orderfilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.orderFilter = chip.dataset.ostatus;
    $$("#orderfilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadOrders();
  })
);

/* Hãng vận chuyển thật đã nối chưa — hỏi MỘT lần mỗi lần tải trang. Chưa
   nối thì nút "Tạo vận đơn" không hiện: một nút bấm lần nào cũng báo lỗi là
   nút người ta học cách lờ đi, kể cả khi đã nối xong. */
let VAN_CHUYEN = null;

async function loadOrders() {
  if (VAN_CHUYEN === null) {
    try { VAN_CHUYEN = await api("/van-chuyen/cau-hinh"); }
    catch { VAN_CHUYEN = { that: false }; }
  }
  const list = await api("/orders?status=" + (state.orderFilter || "all"));
  const cho = list.filter((o) => o.trang_thai === "cho_duyet").length;
  $("#c-donhang").textContent = cho || "";

  $("#orders").innerHTML = list.length ? list.map((o) => {
    const items = (Array.isArray(o.items) ? o.items : [])
      .map((i) => `<span class="order__line">${esc(i.ten)} &times;${i.so_luong} — ${vnd(i.thanh_tien)}</span>`)
      .join("");
    const cho_duyet = o.trang_thai === "cho_duyet";
    /*
     * Đơn `cho_dong_bo`: đã ghi nhận nhưng CHƯA vào được kho/ERP.
     *
     * Khách đã được agent hứa "sẽ có người gọi xác nhận". Máy đang tự thử
     * lại, nhưng nếu nó bỏ cuộc thì lời hứa đó rơi vào khoảng không. Nên
     * dòng này phải NHÌN THẤY ĐƯỢC, không được lẫn vào đám đơn đã xong.
     */
    const cho_dong_bo = o.trang_thai === "cho_dong_bo";

    /*
     * Khách xin huỷ: phải NHÌN THẤY NGAY trên dòng đơn.
     *
     * Agent ghi nhận yêu cầu rồi chuyển hội thoại cho người. Nhưng người
     * đóng gói làm việc ở MÀN HÌNH NÀY, không đọc từng đoạn chat. Không
     * hiện ở đây thì hàng vẫn gói và gửi đi, khách từ chối nhận, shop chịu
     * phí hoàn COD — mà không có lỗi nào bị ném ở đâu cả.
     *
     * Đơn đã huỷ rồi thì thôi, cờ hết nghĩa.
     */
    const xin_huy = o.yeu_cau_huy_luc && o.trang_thai !== "da_huy";
    /* Đơn đã chốt, chưa có vận đơn: nút tạo vận đơn ngay trên dòng. Hàm tạo
       vận đơn có bốn chốt từ lâu, nhưng trước 29.10.2026 không có nút nào
       gọi tới nó — đơn chốt xong rồi nằm im, phải lên trang hãng gõ tay. */
    const tao_van_don = VAN_CHUYEN && VAN_CHUYEN.that && o.trang_thai === "da_chot"
      && !o.ma_van_don && !xin_huy;
    const doi_tra = o.yeu_cau_doi_tra_luc && o.trang_thai !== "da_huy";
    const bang_xin_huy = xin_huy
      ? `<span class="order__xinhuy"><b>Khách xin huỷ</b> — ${clock(o.yeu_cau_huy_luc)}${
          o.yeu_cau_huy_ly_do ? " · " + esc(o.yeu_cau_huy_ly_do) : ""
        }<br>Dừng đóng gói và gọi lại cho khách trước khi quyết định.</span>`
      : "";

    return `<div class="row${xin_huy ? " row--xinhuy" : ""}">
      <span class="row__flag row__flag--${xin_huy ? "halt" : (cho_duyet || cho_dong_bo) ? "assist" : o.trang_thai === "da_huy" ? "halt" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(o.ma_don)} · ${esc(o.khach_ten)}
          <span class="tag tag--${ORDER_TONE[o.trang_thai] || "plain"}">${ORDER_LABEL[o.trang_thai] || o.trang_thai}</span>
          ${xin_huy ? '<span class="tag tag--halt">Khách xin huỷ</span>' : ""}
          ${srcBadge(o.channel, o.nen_tang)}</span>
        ${bang_xin_huy}
        ${doi_tra ? `<span class="order__xinhuy"><b>Khách xin ${({ doi: "đổi hàng", tra: "trả hàng" })[o.yeu_cau_doi_tra_loai] || "đổi/trả"}</b> — ${
            clock(o.yeu_cau_doi_tra_luc)}${o.yeu_cau_doi_tra_ly_do ? " · " + esc(o.yeu_cau_doi_tra_ly_do) : ""
          }<br>Gọi lại cho khách để thống nhất cách đổi/trả.</span>` : ""}
        ${o.ma_van_don ? `<span class="order__ship">Vận đơn <b>${esc(o.ma_van_don)}</b>${
            o.don_vi_van_chuyen ? " · " + esc(o.don_vi_van_chuyen.toUpperCase()) : ""}${
            o.trang_thai_giao_hang ? " · " + esc(NHAN_GIAO[o.trang_thai_giao_hang] || o.trang_thai_giao_hang) : ""
          }</span>` : ""}
        ${cho_dong_bo ? `<span class="order__xinhuy"><b>Chưa vào được kho/ERP</b>${
            o.erp_loi ? " — " + esc(o.erp_loi) : ""
          }${o.erp_so_lan_thu ? " · đã thử " + o.erp_so_lan_thu + " lần" : ""
          }<br>Khách đã được hứa sẽ có người gọi xác nhận. Máy đang tự thử lại.</span>` : ""}
        <span class="order__items">${items}</span>
        <span class="order__ship">${esc(o.khach_sdt)} · ${esc(o.khach_dia_chi)}</span>
      </span>
      <span class="row__side">
        <span class="order__total">${vnd(o.tong_tien)}</span>
        <span class="row__time">${clock(o.created_at)}</span>
        ${o.trang_thai !== "da_huy" ? `<span class="order__qr">
            <a class="btn btn--sm btn--ghost" href="/api/orders/${o.id}/vietqr.svg" target="_blank"
               rel="noopener" title="Mở mã VietQR (tổng hàng + phí ship)">QR</a>
            ${o.conversation_id ? `<button type="button" class="btn btn--sm" data-oqr-gui="${o.id}"
               title="Gửi mã QR thanh toán vào hội thoại của đơn">Gửi QR</button>` : ""}
          </span>` : ""}
        ${cho_duyet ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--go" data-oapprove="${o.id}">Duyệt</button>
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ</button>
          </span>` : xin_huy ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ đơn</button>
          </span>` : tao_van_don ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--go" data-ovandon="${o.id}"
              title="Tạo vận đơn ${esc((VAN_CHUYEN.hang || "").toUpperCase())} và nhắn mã cho khách">Tạo vận đơn</button>
          </span>` : ""}
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có đơn hàng nào.</p>';

  /* Mọi nút đơn hàng báo ĐÚNG kết quả máy chủ trả về. Bản trước báo "Đã
     duyệt đơn." vô điều kiện — kể cả khi ERP từ chối và đơn vừa bị huỷ. */
  const bam = (b, viec) => b.addEventListener("click", async () => {
    b.disabled = true;
    try { await viec(); } catch (e) { toast(e.message, true); }
    finally { b.disabled = false; loadOrders(); }
  });
  $$("[data-oapprove]").forEach((b) => bam(b, async () => {
    const r = await api("/orders/" + b.dataset.oapprove + "/approve", { method: "POST" });
    if (r.erp === "tu_choi") toast("ERP từ chối đơn " + r.ma_don + " — đơn đã huỷ, hàng trả về kho. " + (r.erp_loi || ""), true);
    else if (r.erp === "cho_lai") toast("Đã duyệt " + r.ma_don + ", nhưng chưa vào được ERP — máy tự thử lại.", true);
    else toast(r.erp_ma_don ? "Đã duyệt " + r.ma_don + " · ERP " + r.erp_ma_don + "." : "Đã duyệt đơn " + r.ma_don + ".");
  }));
  $$("[data-ocancel]").forEach((b) => bam(b, async () => {
    const r = await api("/orders/" + b.dataset.ocancel + "/cancel", { method: "POST" });
    if (r.can_huy_tay) toast("Đã huỷ " + r.ma_don + ". " + r.can_huy_tay, true);
    else toast("Đã huỷ đơn.");
  }));
  $$("[data-ovandon]").forEach((b) => bam(b, async () => {
    const r = await api("/orders/" + b.dataset.ovandon + "/van-don", { method: "POST", body: "{}" });
    toast(r.da_co_san ? "Đơn đã có vận đơn " + r.ma_van_don + "."
      : "Đã tạo vận đơn " + r.ma_van_don + " và nhắn mã cho khách.");
  }));
}

/* ---------------- kho hàng ---------------- */

// Tồn kho là số SỐNG: trừ khi chốt đơn, trả khi huỷ. Trước đây nó là một
// con số tĩnh trong file JSON — bán trăm đơn vẫn báo y nguyên.
const KHO_LY_DO = {
  ban: "bán", huy_don: "huỷ đơn", nhap: "nhập hàng", kiem_ke: "kiểm kê",
};

$$("#khofilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.khoFilter = chip.dataset.kstatus;
    $$("#khofilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadKho();
  })
);

/* ---------------- kết nối kho / ERP ---------------- */

/* Mức của bộ kiểm khác mức của bộ sức khoẻ: ở đây "chan" nghĩa là CHƯA DÙNG
   ĐƯỢC, không phải "đang hỏng". Dùng chung bảng màu nhưng đổi tên cho khớp. */
const ERP_TONE  = { tot: "auto", canh_bao: "assist", chan: "halt" };
const ERP_LABEL = { tot: "Đủ", canh_bao: "Cảnh báo", chan: "CHẶN" };

/* Dòng cấu hình ERP gần như không đổi, nhưng đọc nó thì CHẠM VÀO ERP THẬT.
   `loadKho()` nằm trong vòng làm mới 6 giây, nên không có phanh thì mở tab
   Kho rồi đi ăn trưa là 600 lượt gọi ERP mỗi giờ.

   `ep = true` cho lúc người vừa bấm Thử kết nối — họ cần thấy ngay. */
const ERP_CAUHINH_MOI_MS = 60000;
let erpCauHinhLuc = 0;

async function loadErpCauHinh(ep = false) {
  const box = $("#erpcauhinh");
  if (!box) return;
  if (!ep && box.innerHTML.trim()
      && Date.now() - erpCauHinhLuc < ERP_CAUHINH_MOI_MS) return;
  erpCauHinhLuc = Date.now();
  try {
    const d = await api("/erp/suc-khoe");
    const chuaNoi = d.nguon === "tep";
    box.innerHTML = `<div class="row">
      <span class="row__flag row__flag--${chuaNoi ? "assist" : d.mach_mo ? "halt" : "auto"}"></span>
      <div class="row__main">
        <b>Nguồn: ${esc(d.nguon)}</b>
        <span class="row__sub">${chuaNoi
          ? "Đang đọc tệp data/catalog.json trên đĩa — CHƯA nối ERP thật. Đặt ERP_LOAI=erpnext hoặc odoo trong .env rồi khởi động lại."
          : (d.mach_mo
              ? "NGẮT MẠCH đang mở — giá và tồn kho đang trả “không biết”"
              : "đang trả lời bình thường")}</span>
      </div>
      <span class="tag tag--${chuaNoi ? "assist" : d.song ? "auto" : "halt"}">${
        chuaNoi ? "chưa nối" : d.song ? "sống" : "không gọi được"}</span>
    </div>`;
  } catch (e) {
    box.innerHTML = `<p class="empty">Không đọc được cấu hình: ${esc(e.message)}</p>`;
  }
}

$("#erpthu")?.addEventListener("click", async () => {
  const box = $("#erpketqua");
  const btn = $("#erpthu");
  btn.disabled = true;
  /* Nói rõ nó GỌI THẬT. Người bấm cần biết mình đang tiêu hạn mức API của
     cửa hàng, không phải đọc một con số đã lưu sẵn. */
  box.innerHTML = '<p class="empty">Đang gọi thật vào ERP…</p>';
  try {
    const d = await api("/erp/kiem-ket-noi", { method: "POST" });
    const dau = `<div class="row"><span class="row__flag row__flag--${ERP_TONE[d.trang_thai]}"></span>
      <div class="row__main"><b>${d.san_sang ? "SẴN SÀNG đọc" : "CHƯA DÙNG ĐƯỢC"}</b>
      <span class="row__sub">ERP_LOAI=${esc(d.erp_loai)} · đẩy đơn ${
        d.ghi_don ? "BẬT" : "tắt"}${d.ma_kho ? " · kho " + esc(d.ma_kho) : ""}</span></div></div>`;
    box.innerHTML = dau + d.muc.map((m) => `<div class="row">
        <span class="row__flag row__flag--${ERP_TONE[m.trang_thai] || "plain"}"></span>
        <div class="row__main"><b>${esc(m.ten)}</b>
          <span class="row__sub">${esc(m.ghi_chu)}</span>
          ${m.goi_y ? `<span class="row__sub">└─ ${esc(m.goi_y)}</span>` : ""}</div>
        <span class="row__side">
          ${m.ten === "Bảng giá"
            /* Mục DUY NHẤT máy không tự quyết được. Nút nằm ngay cạnh nó,
               không nằm trong một màn cài đặt nào khác: người vừa đọc dòng
               cảnh báo là người đang có đủ ngữ cảnh để bấm. */
            ? `<button type="button" class="btn btn--sm" data-bg-xacnhan="${
                 m.trang_thai === "tot" ? "go" : "ghi"}">${
                 m.trang_thai === "tot" ? "Gỡ xác nhận" : "Tôi đã kiểm"}</button>`
            : ""}
          <span class="tag tag--${ERP_TONE[m.trang_thai] || "plain"}">${
            ERP_LABEL[m.trang_thai] || m.trang_thai}</span>
        </span>
      </div>`).join("");
    loadErpCauHinh(true);
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
});

async function loadKho() {
  loadErpCauHinh();
  const k = await api("/kho");
  $("#c-kho").textContent = (k.het_hang + k.sap_het) || "";

  $("#khoCards").innerHTML =
      cell("Mã hàng", num(k.tong_ma), "", null, "auto")
    + cell("Hết hàng", num(k.het_hang), "", null, k.het_hang ? "halt" : "auto")
    + cell("Sắp hết", num(k.sap_het), "\u2264" + k.nguong_sap_het, null,
           k.sap_het ? "assist" : "auto")
    + cell("Giá trị tồn", vnd(k.gia_tri_ton), "", 1, "spend");

  const loc = state.khoFilter || "all";
  const ds = k.san_pham.filter((x) =>
    loc === "het" ? x.so_luong === 0
    : loc === "sap_het" ? x.sap_het
    : true);

  $("#khoRows").innerHTML = ds.length ? ds.map((x) => {
    const tone = x.so_luong === 0 ? "halt" : x.sap_het ? "assist" : "auto";
    /* Ảnh sản phẩm ngay trên dòng kho.
     *
     * Người trực cần đối chiếu khi khách mô tả bằng lời — "cái chai xanh
     * xanh ấy" — thay vì mở thư mục ảnh ra tìm. Và cùng tấm ảnh đó là thứ
     * agent gửi cho khách, nên nhìn thấy nó ở đây là biết khách sẽ thấy gì.
     *
     * `loading="lazy"`: màn hình có thể hàng trăm mã, tải hết cùng lúc là
     * mở hàng trăm kết nối cho một lần cuộn. */
    const anh = x.co_anh
      ? `<img class="kho__anh" src="/api/san-pham/${encodeURIComponent(x.ma)}/anh"
             alt="" loading="lazy" data-xemanh="${esc(x.ma)}">`
      : '<span class="kho__anh kho__anh--trong">—</span>';
    const them = [x.dung_tich, ...(x.da_phu_hop || []).slice(0, 2)]
      .filter(Boolean).join(" · ");
    return `<div class="row row--kho">
      <span class="row__flag row__flag--${tone}"></span>
      ${anh}
      <span class="row__body">
        <span class="row__title">${esc(x.ma)} · ${esc(x.ten)}
          ${x.so_luong === 0 ? '<span class="tag tag--huy">Hết hàng</span>'
            : x.sap_het ? '<span class="tag tag--duyet">Sắp hết</span>' : ""}</span>
        <span class="row__sub">${esc(x.loai)} · ${vnd(x.gia)}${them ? " · " + esc(them) : ""}</span>
      </span>
      <span class="row__side">
        <span class="row__num">${num(x.so_luong)}</span>
        <span style="display:flex;gap:6px;margin-top:4px">
          <button type="button" class="btn btn--sm" data-knhap="${esc(x.ma)}">Nhập</button>
          <button type="button" class="btn btn--sm" data-kkiemke="${esc(x.ma)}"
            data-kton="${x.so_luong}">Kiểm kê</button>
        </span>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Không có mã nào khớp bộ lọc.</p>';

  $$("[data-knhap]").forEach((b) => b.addEventListener("click", async () => {
    const d = await hoiHop({
      tieu_de: `Nhập kho ${b.dataset.knhap}`,
      truong: [
        { name: "so_luong", label: "Nhập thêm bao nhiêu", type: "number", value: 50,
          min: 1, max: 1000000, step: 1, required: true },
        { name: "ghi_chu", label: "Ghi chú", hint: "số lô, nhà cung cấp…", maxlength: 300 },
      ],
      nut: "Nhập kho",
    });
    if (!d) return;
    try {
      const r = await api(`/kho/${encodeURIComponent(b.dataset.knhap)}/nhap`, {
        method: "POST",
        body: JSON.stringify({ so_luong: parseInt(d.so_luong, 10), ghi_chu: d.ghi_chu || "" }),
      });
      toast(`${r.ma}: tồn mới ${r.ton_moi}`);
      loadKho();
    } catch (e) { toast(e.message, true); }
  }));

  // Kiểm kê bắt buộc có lý do — kho LUÔN lệch, và không ghi vì sao thì
  // sau này không ai truy được lệch từ đâu.
  $$("[data-kkiemke]").forEach((b) => b.addEventListener("click", async () => {
    const d = await hoiHop({
      tieu_de: `Kiểm kê ${b.dataset.kkiemke}`,
      phu: `Hệ thống đang ghi ${b.dataset.kton}. Lý do là bắt buộc — không ghi thì sau này không ai truy được lệch từ đâu.`,
      truong: [
        { name: "so_luong_moi", label: "Đếm thực tế được", type: "number",
          value: b.dataset.kton, min: 0, max: 1000000, step: 1, required: true },
        { name: "ly_do", label: "Lý do lệch", placeholder: "vỡ, mất, đếm sai…",
          required: true, maxlength: 300 },
      ],
      nut: "Ghi kiểm kê",
    });
    if (!d) return;
    try {
      const r = await api(`/kho/${encodeURIComponent(b.dataset.kkiemke)}/kiem-ke`, {
        method: "POST",
        body: JSON.stringify({ so_luong_moi: parseInt(d.so_luong_moi, 10), ly_do: d.ly_do }),
      });
      toast(`${r.ma}: ${r.cu} → ${r.moi} (lệch ${r.lech > 0 ? "+" : ""}${r.lech})`);
      loadKho();
    } catch (e) { toast(e.message, true); }
  }));

  const { bien_dong } = await api("/kho/bien-dong?limit=25");
  $("#khoSo").innerHTML = bien_dong.length ? bien_dong.map((b) => `
    <div class="row">
      <span class="row__flag row__flag--${b.thay_doi < 0 ? "halt" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(b.ma)}
          <span class="tag tag--plain">${esc(KHO_LY_DO[b.ly_do] || b.ly_do)}</span></span>
        <span class="row__sub">${esc(b.ma_don || b.ghi_chu || "")}</span>
      </span>
      <span class="row__side">
        <span class="row__num">${b.thay_doi > 0 ? "+" : ""}${b.thay_doi}</span>
        <span class="row__time">${clock(b.luc)}</span>
      </span>
    </div>`).join("") : '<p class="empty">Chưa có biến động nào.</p>';
}

