/* ---------------- Kho hàng & Sổ biến động (tách từ 05-don-kho.js) ---------------- */

const khoState = {
  tab: "ton_kho",
  status: "all",
  q: "",
  category: "all",
  page: 1,
  pageSize: 20,
  sanPham: [],
  meta: null,
  listRequest: 0,
  bdQ: "",
  bdLyDo: "all",
  bdChieu: "all",
  bdTu: "",
  bdDen: "",
  bdPage: 1,
  bdPageSize: 20,
  bdRequest: 0,
  bdTimer: null,
};

function khoCoLoc() {
  return Boolean(
    (khoState.status && khoState.status !== "all")
    || khoState.q
    || (khoState.category && khoState.category !== "all")
  );
}

function khoBdCoLoc() {
  return Boolean(
    khoState.bdQ
    || (khoState.bdLyDo && khoState.bdLyDo !== "all")
    || (khoState.bdChieu && khoState.bdChieu !== "all")
    || khoState.bdTu
    || khoState.bdDen
  );
}

function khoCapNhatChieuCaoToolbar() {
  for (const [tbSel, panelSel] of [
    ["#khoToolbar", "#khoTabTon"],
    ["#khoBdToolbar", "#khoTabBienDong"],
  ]) {
    const tb = $(tbSel);
    const panel = $(panelSel);
    if (tb && panel && !panel.hidden) {
      panel.style.setProperty("--dh-toolbar-h", tb.offsetHeight + "px");
    }
  }
}

function khoChuyenTab(tab) {
  khoState.tab = tab === "bien_dong" ? "bien_dong" : "ton_kho";
  const view = $('.view[data-view="kho"]');
  $$("[data-ktab]", view).forEach((b) => {
    const on = b.dataset.ktab === khoState.tab;
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  const ton = $("#khoTabTon", view);
  const bd = $("#khoTabBienDong", view);
  if (ton) ton.hidden = khoState.tab !== "ton_kho";
  if (bd) bd.hidden = khoState.tab !== "bien_dong";
  khoCapNhatChieuCaoToolbar();
  loadKho();
}

function khoVeKpi(k) {
  const giaNote = k.so_ma_chua_biet_gia
    ? `theo giá bán · ${k.so_ma_chua_biet_gia} mã chưa có giá`
    : "tính theo giá bán hiện tại";
  const muc = [
    { id: "all", nhan: "Mã hàng", val: num(k.tong_ma), sub: "đang theo dõi trong kho" },
    { id: "het", nhan: "Hết hàng", val: num(k.het_hang), sub: "tồn khả dụng = 0" },
    { id: "sap_het", nhan: "Sắp hết", val: num(k.sap_het), sub: `từ 1 đến ≤ ${k.nguong_sap_het}` },
  ];
  const cards = muc.map((m) => `
    <button type="button" class="readout__cell${khoState.status === m.id ? " is-on" : ""}" data-kkpi="${m.id}" aria-pressed="${khoState.status === m.id}">
      <span class="readout__label">${esc(m.nhan)}</span>
      <span class="readout__value">${m.val}</span>
      <span class="readout__unit">${esc(m.sub)}</span>
    </button>`).join("");
  const valCard = `
    <div class="readout__cell readout__cell--tinh">
      <span class="readout__label">Giá trị tồn (giá bán)</span>
      <span class="readout__value">${vnd(k.gia_tri_ton)}</span>
      <span class="readout__unit">${esc(giaNote)}</span>
    </div>`;
  $("#khoCards").innerHTML = cards + valCard;
}

function khoCapNhatChip(k) {
  const counts = {
    all: k.tong_ma || 0,
    sap_het: k.sap_het || 0,
    het: k.het_hang || 0,
  };
  $$("#khofilter .chip").forEach((c) => {
    c.classList.toggle("is-on", c.dataset.kstatus === (khoState.status || "all"));
  });
  $$("#khofilter [data-kcnt]").forEach((el) => {
    const n = counts[el.dataset.kcnt];
    el.textContent = n != null ? `(${n})` : "";
  });
  const sel = $("#khoStatus");
  if (sel && [...sel.options].some((o) => o.value === khoState.status)) {
    sel.value = khoState.status;
  }
}

function khoLocSanPham(ds) {
  const q = (khoState.q || "").trim().toLowerCase();
  const cat = khoState.category || "all";
  const st = khoState.status || "all";
  return ds.filter((x) => {
    if (st === "het" && x.so_luong !== 0) return false;
    if (st === "sap_het" && !(x.so_luong > 0 && x.so_luong <= (khoState.meta?.nguong_sap_het ?? 10))) return false;
    if (st === "con_hang" && x.so_luong === 0) return false;
    if (cat !== "all" && (x.loai || "") !== cat) return false;
    if (q) {
      const hit = String(x.ma || "").toLowerCase().includes(q)
        || String(x.ten || "").toLowerCase().includes(q);
      if (!hit) return false;
    }
    return true;
  });
}

function khoTrangThai(x) {
  if (x.so_luong === 0) return { label: "Hết hàng", tag: "tag--huy", row: "is-alert" };
  if (x.sap_het) return { label: "Sắp hết", tag: "tag--duyet", row: "is-warn" };
  return { label: "Còn hàng", tag: "tag--auto", row: "" };
}

function khoAnh(x) {
  /* Ảnh sản phẩm trên bảng và thẻ kho. `loading="lazy"` tránh mở hàng trăm kết nối cùng lúc. */
  return x.co_anh
    ? `<img class="kho__anh" src="/api/san-pham/${encodeURIComponent(x.ma)}/anh" alt="" loading="lazy" data-xemanh="${esc(x.ma)}">`
    : '<span class="kho__anh kho__anh--trong">—</span>';
}

function khoVePhanTrang(boxId, pageAttr, total, page, totalPages, pageSize, unitLabel) {
  const el = $(boxId);
  if (!el) return;
  if (!total || (totalPages <= 1 && total <= pageSize)) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  const tu = (page - 1) * pageSize + 1;
  const den = Math.min(total, page * pageSize);
  el.hidden = false;
  el.innerHTML = `
    <span>Hiển thị <b>${tu}–${den}</b> / ${total} ${unitLabel}</span>
    <span class="dh-pager__nav">
      <button type="button" class="btn btn--sm btn--ghost" ${pageAttr}="${page - 1}" ${page <= 1 ? "disabled" : ""}>← Trước</button>
      <span>Trang ${page}/${totalPages}</span>
      <button type="button" class="btn btn--sm btn--ghost" ${pageAttr}="${page + 1}" ${page >= totalPages ? "disabled" : ""}>Sau →</button>
    </span>`;
}

function khoVeTon() {
  const dsLoc = khoLocSanPham(khoState.sanPham);
  const total = dsLoc.length;
  const ps = khoState.pageSize || 20;
  const totalPages = Math.max(1, Math.ceil(total / ps));
  khoState.page = Math.min(Math.max(1, khoState.page || 1), totalPages);
  const start = (khoState.page - 1) * ps;
  const pageItems = dsLoc.slice(start, start + ps);
  const coSua = typeof coQuyen !== "function" || coQuyen("kho.sua");

  const resetBtn = $("#khoReset");
  if (resetBtn) resetBtn.hidden = !khoCoLoc();

  if (!pageItems.length) {
    $("#khoRows").innerHTML = '<p class="empty">Không có sản phẩm nào khớp bộ lọc.</p>';
    khoVePhanTrang("#khoPager", "data-kpage", 0, 1, 1, ps, "mã hàng");
    return;
  }

  const rowsHtml = pageItems.map((x) => {
    const st = khoTrangThai(x);
    const them = [x.dung_tich, ...(x.da_phu_hop || []).slice(0, 2)].filter(Boolean).join(" · ");
    const nuts = coSua ? `
      <span class="dh-act-grp">
        <button type="button" class="btn btn--sm" data-knhap="${esc(x.ma)}" data-kten="${esc(x.ten)}" data-kton="${x.so_luong}">Nhập</button>
        <button type="button" class="btn btn--sm" data-kkiemke="${esc(x.ma)}" data-kten="${esc(x.ten)}" data-kton="${x.so_luong}">Kiểm kê</button>
      </span>` : '<span class="kho-sku">Chỉ xem</span>';
    return `
      <tr class="dh-tr ${st.row}">
        <td>
          <div class="kho-sp">
            ${khoAnh(x)}
            <div class="kho-sp__info">
              <div class="kho-ten">${esc(x.ten)}</div>
              <div class="kho-sku mono">SKU: ${esc(x.ma)}</div>
              ${them ? `<div class="kho-meta">${esc(them)}</div>` : ""}
            </div>
          </div>
        </td>
        <td>${esc(x.loai || "—")}</td>
        <td class="is-num mono">${x.gia != null ? vnd(x.gia) : '<span class="kho-sku">Chưa rõ giá</span>'}</td>
        <td class="is-num mono"><b>${num(x.so_luong)}</b></td>
        <td><span class="tag ${st.tag}">${st.label}</span></td>
        <td class="is-act kho-act-col">${nuts}</td>
      </tr>`;
  }).join("");

  const cardsHtml = pageItems.map((x) => {
    const st = khoTrangThai(x);
    const nuts = coSua ? `
      <button type="button" class="btn btn--sm" data-knhap="${esc(x.ma)}" data-kten="${esc(x.ten)}" data-kton="${x.so_luong}">Nhập</button>
      <button type="button" class="btn btn--sm" data-kkiemke="${esc(x.ma)}" data-kten="${esc(x.ten)}" data-kton="${x.so_luong}">Kiểm kê</button>` : "";
    return `
      <article class="dh-card ${st.row}">
        <div class="dh-card__top">
          <div class="kho-card__sp">
            ${khoAnh(x)}
            <div class="kho-sp__info">
              <div class="kho-ten">${esc(x.ten)}</div>
              <div class="kho-sku mono">SKU: ${esc(x.ma)}</div>
            </div>
          </div>
          <span class="tag ${st.tag}">${st.label}</span>
        </div>
        <div class="dh-card__mid">
          <span class="kho-card__meta">${esc(x.loai || "Chưa phân loại")} · ${x.gia != null ? vnd(x.gia) : "Chưa rõ giá"}</span>
          <span class="mono">Tồn: <b>${num(x.so_luong)}</b></span>
        </div>
        ${nuts ? `<div class="dh-card__bot kho-card__bot">${nuts}</div>` : ""}
      </article>`;
  }).join("");

  $("#khoRows").innerHTML = `
    <div class="dh-table-wrap">
      <table class="dh-table kho-table">
        <thead>
          <tr>
            <th>Sản phẩm</th>
            <th>Danh mục</th>
            <th class="is-num">Giá bán</th>
            <th class="is-num">Tồn khả dụng</th>
            <th>Trạng thái</th>
            <th class="is-act kho-act-col">Thao tác</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
    <div class="dh-cards">${cardsHtml}</div>`;

  khoVePhanTrang("#khoPager", "data-kpage", total, khoState.page, totalPages, ps, "mã hàng");
  khoGanNutDong();
}

function khoVeHopNhap(form, ctx, ma, ten, tonHienTai) {
  const info = document.createElement("div");
  info.className = "kho-modal-info";
  info.innerHTML = `
    <div class="kho-modal-info__sp"><b>${esc(ten || ma)}</b><span class="kho-sku mono">SKU: ${esc(ma)}</span></div>
    <div class="kho-modal-info__cell"><span>Tồn hiện tại</span><b class="mono">${num(tonHienTai)}</b></div>
    <div class="kho-modal-info__cell"><span>Tồn dự kiến</span><b class="mono" data-kdu-kien>${num(tonHienTai)}</b></div>`;
  const hoanBox = document.createElement("div");
  hoanBox.className = "kho-hoan-box";
  hoanBox.hidden = true;
  ctx.khoi.innerHTML = "";
  ctx.khoi.append(info, hoanBox);
  ctx.khoi.hidden = false;

  const loaiEl = form.elements.loai;
  const maDonEl = form.elements.ma_don;
  const slEl = form.elements.so_luong;
  const maDonField = maDonEl?.closest(".field");
  let timer = null;
  let reqId = 0;
  let hoanState = null;

  const capNhat = () => {
    const isHoan = loaiEl.value === "hoan_hang";
    if (maDonField) maDonField.hidden = !isHoan;
    if (maDonEl) maDonEl.required = isHoan;
    hoanBox.hidden = !isHoan;
    const q = parseInt(slEl.value, 10);
    const dkEl = info.querySelector("[data-kdu-kien]");
    if (dkEl) dkEl.textContent = num(tonHienTai + (Number.isFinite(q) && q > 0 ? q : 0));

    let loi = "";
    if (isHoan) {
      const md = (maDonEl.value || "").trim();
      if (!md) {
        hoanBox.classList.remove("is-err");
        hoanBox.innerHTML = '<span class="kho-sku">Nhập mã đơn hàng để kiểm tra điều kiện và số lượng còn được hoàn.</span>';
      } else if (hoanState && hoanState.loading) {
        hoanBox.classList.remove("is-err");
        hoanBox.innerHTML = `<span class="kho-sku">Đang kiểm tra đơn ${esc(md)}…</span>`;
      } else if (hoanState && hoanState.ma_don === md) {
        const vuot = Number.isFinite(q) && hoanState.du_dieu_kien && q > hoanState.con_lai;
        if (!hoanState.du_dieu_kien) loi = hoanState.thong_bao || "Đơn chưa đủ điều kiện nhập hoàn.";
        else if (vuot) loi = `Số lượng nhập (${q}) vượt quá số còn được nhập (${hoanState.con_lai}).`;
        hoanBox.classList.toggle("is-err", Boolean(loi));
        hoanBox.innerHTML = `
          <div>Mã đơn: <b class="mono">${esc(md)}</b></div>
          <div class="kho-hoan-box__grid">
            <div><span>Đã bán</span><b class="mono">${num(hoanState.da_ban)}</b></div>
            <div><span>Đã hoàn</span><b class="mono">${num(hoanState.da_hoan)}</b></div>
            <div><span>Còn được nhập</span><b class="mono">${num(hoanState.con_lai)}</b></div>
          </div>
          ${loi ? `<div class="kho-hoan-box__loi">${esc(loi)}</div>` : ""}`;
      }
    }
    ctx.loiEl.textContent = loi;
    ctx.nutGui.disabled = Boolean(isHoan && hoanState && hoanState.ma_don === (maDonEl.value || "").trim() && loi);
  };

  const traDonHoan = () => {
    const md = (maDonEl.value || "").trim();
    if (loaiEl.value !== "hoan_hang" || !md) { hoanState = null; capNhat(); return; }
    const myReq = ++reqId;
    hoanState = { loading: true, ma_don: md };
    capNhat();
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try {
        const res = await api(`/kho/${encodeURIComponent(ma)}/hoan-hang-info?ma_don=${encodeURIComponent(md)}`);
        if (myReq !== reqId) return;
        hoanState = { ...res, ma_don: md, loading: false };
      } catch (err) {
        if (myReq !== reqId) return;
        hoanState = { ma_don: md, du_dieu_kien: false, da_ban: 0, da_hoan: 0, con_lai: 0, thong_bao: err.message, loading: false };
      }
      capNhat();
    }, 200);
  };

  loaiEl.addEventListener("change", traDonHoan);
  maDonEl.addEventListener("input", traDonHoan);
  slEl.addEventListener("input", capNhat);
  capNhat();
  return () => clearTimeout(timer);
}

function khoVeHopKiemKe(form, ctx, ma, ten, tonHeThong) {
  const info = document.createElement("div");
  info.className = "kho-modal-info kho-modal-info--3";
  info.innerHTML = `
    <div class="kho-modal-info__sp"><b>${esc(ten || ma)}</b><span class="kho-sku mono">SKU: ${esc(ma)}</span></div>
    <div class="kho-modal-info__cell"><span>Tồn hệ thống</span><b class="mono">${num(tonHeThong)}</b></div>
    <div class="kho-modal-info__cell"><span>Thực tế</span><b class="mono" data-kthuc-te>${num(tonHeThong)}</b></div>
    <div class="kho-modal-info__cell"><span>Chênh lệch</span><b class="mono" data-klech>0 (khớp)</b></div>`;
  ctx.khoi.innerHTML = "";
  ctx.khoi.append(info);
  ctx.khoi.hidden = false;

  const slEl = form.elements.so_luong_moi;
  const capNhat = () => {
    const val = slEl.value === "" ? NaN : parseInt(slEl.value, 10);
    const ttEl = info.querySelector("[data-kthuc-te]");
    const lechEl = info.querySelector("[data-klech]");
    if (!Number.isFinite(val)) {
      ttEl.textContent = "—";
      lechEl.textContent = "—";
      lechEl.className = "mono";
      return;
    }
    const lech = val - tonHeThong;
    ttEl.textContent = num(val);
    lechEl.textContent = lech > 0 ? `+${num(lech)}` : lech < 0 ? num(lech) : "0 (khớp)";
    lechEl.className = `mono ${lech > 0 ? "kho-delta--in" : lech < 0 ? "kho-delta--out" : ""}`;
  };
  slEl.addEventListener("input", capNhat);
  capNhat();
}

function khoGanNutDong() {
  $$("[data-knhap]").forEach((b) => b.addEventListener("click", async () => {
    if (typeof coQuyen === "function" && !coQuyen("kho.sua")) { toast("Không có quyền nhập kho.", true); return; }
    const ma = b.dataset.knhap, ten = b.dataset.kten || ma, ton = parseInt(b.dataset.kton || "0", 10) || 0;
    const d = await hoiHop({
      tieu_de: `Nhập kho · ${ma}`,
      phu: "Chọn nhập thông thường hoặc nhập hàng hoàn từ đơn đã hoàn về kho.",
      modal_kho: true,
      truong: [
        { name: "loai", label: "Loại nhập kho", type: "select", value: "nhap", options: KHO_NHAP_LOAI },
        { name: "ma_don", label: "Mã đơn hàng", hint: "bắt buộc khi nhập hàng hoàn", placeholder: "VD: AS261126...", maxlength: 64, hidden: true },
        { name: "so_luong", label: "Số lượng nhập", type: "number", value: "", placeholder: "Nhập số lượng thực tế…", min: 1, max: 100000, step: 1, required: true },
        { name: "ghi_chu", label: "Ghi chú", hint: "số lô, tình trạng hàng hoàn…", maxlength: 300 },
      ],
      nut: "Xác nhận nhập kho",
      onRender: (form, ctx) => khoVeHopNhap(form, ctx, ma, ten, ton),
    });
    if (!d) return;
    if (d.loai === "hoan_hang" && !d.ma_don) { toast("Nhập hàng hoàn bắt buộc phải nhập mã đơn hàng.", true); return; }
    const khoa = (typeof crypto !== "undefined" && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    try {
      const r = await api(`/kho/${encodeURIComponent(ma)}/nhap`, {
        method: "POST",
        body: JSON.stringify({
          loai: d.loai || "nhap", ma_don: d.loai === "hoan_hang" ? d.ma_don : null,
          so_luong: parseInt(d.so_luong, 10), ghi_chu: d.ghi_chu || "", khoa_chong_trung: khoa,
        }),
      });
      toast(r.ly_do === "hoan_hang"
        ? `${r.ma}: nhập hàng hoàn đơn ${r.ma_don} (${r.da_hoan}/${r.da_ban}) · tồn mới ${r.ton_moi}`
        : `${r.ma}: tồn mới ${r.ton_moi}`);
      loadKho();
    } catch (e) { toast(e.message, true); }
  }));

  // Kiểm kê bắt buộc có lý do và tính chênh lệch ngay khi nhập.
  $$("[data-kkiemke]").forEach((b) => b.addEventListener("click", async () => {
    if (typeof coQuyen === "function" && !coQuyen("kho.sua")) { toast("Không có quyền kiểm kê kho.", true); return; }
    const ma = b.dataset.kkiemke, ten = b.dataset.kten || ma, ton = parseInt(b.dataset.kton || "0", 10) || 0;
    const d = await hoiHop({
      tieu_de: `Kiểm kê · ${ma}`,
      phu: "Nhập số đếm thực tế và lý do chênh lệch (bắt buộc để truy vết sổ kho).",
      modal_kho: true,
      truong: [
        { name: "so_luong_moi", label: "Số lượng thực tế", type: "number", value: ton, min: 0, max: 100000, step: 1, required: true },
        { name: "ly_do", label: "Lý do kiểm kê", placeholder: "Vỡ, mất, đếm sai…", required: true, minlength: 3, maxlength: 300 },
      ],
      nut: "Ghi kiểm kê",
      onRender: (form, ctx) => khoVeHopKiemKe(form, ctx, ma, ten, ton),
    });
    if (!d) return;
    try {
      const r = await api(`/kho/${encodeURIComponent(ma)}/kiem-ke`, {
        method: "POST",
        body: JSON.stringify({ so_luong_moi: parseInt(d.so_luong_moi, 10), ly_do: d.ly_do }),
      });
      toast(`${r.ma}: ${r.cu} → ${r.moi} (lệch ${r.lech > 0 ? "+" : ""}${r.lech})`);
      loadKho();
    } catch (e) { toast(e.message, true); }
  }));
}

function khoVeBienDong(data) {
  const items = data.items || [];
  const ps = data.page_size || khoState.bdPageSize || 20;
  const resetBtn = $("#khoBdReset");
  if (resetBtn) resetBtn.hidden = !khoBdCoLoc();

  if (!items.length) {
    $("#khoSo").innerHTML = '<p class="empty">Không có biến động kho nào khớp bộ lọc.</p>';
    khoVePhanTrang("#khoBdPager", "data-kbdpage", 0, 1, 1, ps, "biến động");
    return;
  }

  const coGhiChu = items.some((b) => Boolean(b.ghi_chu));
  const rowsHtml = items.map((b) => {
    const tang = b.thay_doi > 0;
    const giam = b.thay_doi < 0;
    const tdCls = tang ? "kho-delta--in" : giam ? "kho-delta--out" : "";
    const tdTxt = tang ? `+${num(b.thay_doi)}` : num(b.thay_doi);
    const lyDo = dhCapFirst(KHO_LY_DO[b.ly_do] || b.ly_do);
    const lyDoTag = giam ? "tag--huy" : b.ly_do === "hoan_hang" || b.ly_do === "nhap" ? "tag--auto" : "tag--plain";
    const donHtml = b.ma_don ? `<button type="button" class="dh-code mono" data-kbd-don="${esc(b.ma_don)}">${esc(b.ma_don)}</button>` : "—";
    const thieuCanCu = b.do_tin_cay_ton === "thieu_can_cu";
    const tonSauHtml = b.ton_sau != null
      ? `${num(b.ton_sau)}${thieuCanCu ? `<div class="kho-sku" title="${esc(b.ly_do_tin_cay)}">Thiếu mốc đầu kỳ</div>` : ""}`
      : "—";
    const duyetHtml = b.nguoi_phe_duyet && b.nguoi_phe_duyet !== b.nguoi_thuc_hien
      ? `<div class="kho-sku">Duyệt: ${esc(b.nguoi_phe_duyet)}</div>` : "";
    return `
      <tr class="dh-tr">
        <td class="dh-col-time" title="${esc(dhFullTime(b.luc))}">${esc(clock(b.luc))} · ${esc(hhmm(b.luc))}</td>
        <td>
          <div class="kho-sp__info">
            <div class="kho-ten">${esc(b.ten || b.ma)}</div>
            <div class="kho-sku mono">${esc(b.ma)}</div>
          </div>
        </td>
        <td><span class="tag ${lyDoTag}">${esc(lyDo)}</span></td>
        <td class="is-num mono ${tdCls}">${tdTxt}</td>
        <td class="is-num mono" title="${thieuCanCu ? esc(b.ly_do_tin_cay) : ""}">${tonSauHtml}</td>
        <td>${donHtml}</td>
        <td>${esc(b.nguoi_thuc_hien || "—")}${duyetHtml}</td>
        ${coGhiChu ? `<td class="kho-note">${esc(b.ghi_chu || "—")}</td>` : ""}
      </tr>`;
  }).join("");

  const cardsHtml = items.map((b) => {
    const tang = b.thay_doi > 0;
    const giam = b.thay_doi < 0;
    const tdCls = tang ? "kho-delta--in" : giam ? "kho-delta--out" : "";
    const tdTxt = tang ? `+${num(b.thay_doi)}` : num(b.thay_doi);
    const lyDo = dhCapFirst(KHO_LY_DO[b.ly_do] || b.ly_do);
    const thieuCanCu = b.do_tin_cay_ton === "thieu_can_cu";
    return `
      <article class="dh-card ${giam ? "is-alert" : ""}">
        <div class="dh-card__top">
          <div class="kho-sp__info">
            <div class="kho-ten">${esc(b.ten || b.ma)}</div>
            <div class="kho-sku mono">${esc(b.ma)} · ${esc(dhFullTime(b.luc))}</div>
          </div>
          <span class="mono ${tdCls}">${tdTxt}</span>
        </div>
        <div class="dh-card__mid">
          <span class="tag ${giam ? "tag--huy" : "tag--auto"}">${esc(lyDo)}</span>
          <span class="mono" title="${thieuCanCu ? esc(b.ly_do_tin_cay) : ""}">Tồn sau: <b>${b.ton_sau != null ? num(b.ton_sau) : "—"}</b>${thieuCanCu ? " <small>(thiếu mốc đầu kỳ)</small>" : ""}</span>
        </div>
        <div class="dh-card__bot kho-card__meta">
          <span>${b.ma_don ? `Đơn: <b class="mono">${esc(b.ma_don)}</b>` : "Không gắn đơn"}</span>
          <span>${esc(b.nguoi_thuc_hien || "—")}${b.nguoi_phe_duyet && b.nguoi_phe_duyet !== b.nguoi_thuc_hien ? ` · Duyệt: ${esc(b.nguoi_phe_duyet)}` : ""}</span>
        </div>
        ${b.ghi_chu ? `<div class="kho-note">${esc(b.ghi_chu)}</div>` : ""}
      </article>`;
  }).join("");

  $("#khoSo").innerHTML = `
    <div class="dh-table-wrap">
      <table class="dh-table kho-bd-table">
        <thead>
          <tr>
            <th>Thời gian</th>
            <th>Sản phẩm / SKU</th>
            <th>Loại biến động</th>
            <th class="is-num">Thay đổi</th>
            <th class="is-num">Tồn sau</th>
            <th>Mã đơn</th>
            <th>Người thực hiện</th>
            ${coGhiChu ? "<th>Ghi chú</th>" : ""}
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
    <div class="dh-cards">${cardsHtml}</div>`;

  khoVePhanTrang("#khoBdPager", "data-kbdpage", data.total || 0, data.page || 1, data.total_pages || 1, ps, "biến động");
}

async function loadKhoBienDong() {
  const req = ++khoState.bdRequest;
  $("#khoSo")?.setAttribute("aria-busy", "true");
  try {
    const p = new URLSearchParams({
      q: khoState.bdQ || "",
      ly_do: khoState.bdLyDo || "all",
      chieu: khoState.bdChieu || "all",
      tu_ngay: khoState.bdTu || "",
      den_ngay: khoState.bdDen || "",
      page: String(khoState.bdPage || 1),
      page_size: String(khoState.bdPageSize || 20),
    });
    const data = await api("/kho/bien-dong/bang?" + p.toString());
    if (req !== khoState.bdRequest) return;
    khoState.bdPage = data.page || 1;
    khoVeBienDong(data);
    khoCapNhatChieuCaoToolbar();
  } catch (e) {
    if (req !== khoState.bdRequest) return;
    $("#khoSo").innerHTML = `<p class="empty" role="alert">${esc(e.message)}</p>`;
    $("#khoBdPager").hidden = true;
  } finally {
    if (req === khoState.bdRequest) $("#khoSo")?.setAttribute("aria-busy", "false");
  }
}

function khoGanSuKien() {
  const view = $('.view[data-view="kho"]');
  if (!view || view.dataset.khoBound) return;
  view.dataset.khoBound = "1";

  if (!window._slaTipDocBound) {
    window._slaTipDocBound = true;
    const dongHetTip = (tru = null) => {
      $$(".sla-tip-boc.is-open").forEach((b) => {
        if (b !== tru) {
          b.classList.remove("is-open");
          b.querySelector("[data-sla-tip]")?.setAttribute("aria-expanded", "false");
        }
      });
    };
    document.addEventListener("click", (ev) => {
      const nut = ev.target.closest("[data-sla-tip]");
      if (nut) {
        ev.preventDefault();
        const boc = nut.closest(".sla-tip-boc");
        const dangMo = boc.classList.contains("is-open");
        dongHetTip(boc);
        boc.classList.toggle("is-open", !dangMo);
        nut.setAttribute("aria-expanded", dangMo ? "false" : "true");
        return;
      }
      if (!ev.target.closest(".sla-tip-boc")) dongHetTip();
    });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") dongHetTip(); });
  }

  if (typeof ResizeObserver !== "undefined") {
    const ro = new ResizeObserver(() => khoCapNhatChieuCaoToolbar());
    $("#khoToolbar", view) && ro.observe($("#khoToolbar", view));
    $("#khoBdToolbar", view) && ro.observe($("#khoBdToolbar", view));
  }

  $$("[data-ktab]", view).forEach((btn) =>
    btn.addEventListener("click", () => khoChuyenTab(btn.dataset.ktab))
  );

  $$("#khofilter .chip", view).forEach((chip) =>
    chip.addEventListener("click", () => {
      khoState.status = chip.dataset.kstatus;
      state.khoFilter = khoState.status;
      khoState.page = 1;
      khoCapNhatChip(khoState.meta || {});
      khoVeTon();
    })
  );

  $("#khoSearch", view)?.addEventListener("input", (e) => {
    khoState.q = e.target.value;
    khoState.page = 1;
    khoVeTon();
  });

  $("#khoCategory", view)?.addEventListener("change", (e) => {
    khoState.category = e.target.value;
    khoState.page = 1;
    khoVeTon();
  });

  $("#khoStatus", view)?.addEventListener("change", (e) => {
    khoState.status = e.target.value;
    state.khoFilter = khoState.status;
    khoState.page = 1;
    khoCapNhatChip(khoState.meta || {});
    khoVeTon();
  });

  $("#khoReset", view)?.addEventListener("click", () => {
    khoState.status = "all";
    state.khoFilter = "all";
    khoState.q = "";
    khoState.category = "all";
    khoState.page = 1;
    if ($("#khoSearch", view)) $("#khoSearch", view).value = "";
    if ($("#khoCategory", view)) $("#khoCategory", view).value = "all";
    if ($("#khoStatus", view)) $("#khoStatus", view).value = "all";
    khoCapNhatChip(khoState.meta || {});
    khoVeTon();
  });

  $("#khoBdSearch", view)?.addEventListener("input", (e) => {
    khoState.bdQ = e.target.value.trim();
    khoState.bdPage = 1;
    clearTimeout(khoState.bdTimer);
    khoState.bdTimer = setTimeout(() => loadKhoBienDong(), 220);
  });

  const bindBd = (sel, key) => $(sel, view)?.addEventListener("change", (e) => {
    khoState[key] = e.target.value;
    khoState.bdPage = 1;
    loadKhoBienDong();
  });
  bindBd("#khoBdReason", "bdLyDo");
  bindBd("#khoBdDir", "bdChieu");
  bindBd("#khoBdFrom", "bdTu");
  bindBd("#khoBdTo", "bdDen");

  $("#khoBdReset", view)?.addEventListener("click", () => {
    khoState.bdQ = "";
    khoState.bdLyDo = "all";
    khoState.bdChieu = "all";
    khoState.bdTu = "";
    khoState.bdDen = "";
    khoState.bdPage = 1;
    if ($("#khoBdSearch", view)) $("#khoBdSearch", view).value = "";
    if ($("#khoBdReason", view)) $("#khoBdReason", view).value = "all";
    if ($("#khoBdDir", view)) $("#khoBdDir", view).value = "all";
    if ($("#khoBdFrom", view)) $("#khoBdFrom", view).value = "";
    if ($("#khoBdTo", view)) $("#khoBdTo", view).value = "";
    loadKhoBienDong();
  });

  view.addEventListener("click", (e) => {
    const kpi = e.target.closest("[data-kkpi]");
    if (kpi) {
      khoState.status = kpi.dataset.kkpi;
      state.khoFilter = khoState.status;
      khoState.page = 1;
      if (khoState.tab !== "ton_kho") khoChuyenTab("ton_kho");
      else { khoVeKpi(khoState.meta || {}); khoCapNhatChip(khoState.meta || {}); khoVeTon(); }
      return;
    }
    const kpg = e.target.closest("[data-kpage]");
    if (kpg && !kpg.disabled) {
      khoState.page = Math.max(1, parseInt(kpg.dataset.kpage, 10) || 1);
      khoVeTon();
      return;
    }
    const bpg = e.target.closest("[data-kbdpage]");
    if (bpg && !bpg.disabled) {
      khoState.bdPage = Math.max(1, parseInt(bpg.dataset.kbdpage, 10) || 1);
      loadKhoBienDong();
      return;
    }
    const donBtn = e.target.closest("[data-kbd-don]");
    if (donBtn) {
      const maDon = donBtn.dataset.kbdDon;
      dhState.q = maDon;
      dhState.status = "all";
      dhState.page = 1;
      if ($("#orderSearch")) $("#orderSearch").value = maDon;
      if (typeof doiMan === "function") doiMan("donhang");
      else $('[data-view="donhang"]')?.click();
    }
  });
}

/* ---------------- kết nối kho / ERP ---------------- */

/* Mức của bộ kiểm khác mức của bộ sức khoẻ: ở đây "chan" nghĩa là CHƯA DÙNG
   ĐƯỢC, không phải "đang hỏng". Dùng chung bảng màu nhưng đổi tên cho khớp. */
const ERP_TONE = { tot: "auto", canh_bao: "assist", chan: "halt" };
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
      <span class="tag tag--${chuaNoi ? "assist" : d.song ? "auto" : "halt"}">${chuaNoi ? "chưa nối" : d.song ? "sống" : "không gọi được"}</span>
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
      <span class="row__sub">ERP_LOAI=${esc(d.erp_loai)} · đẩy đơn ${d.ghi_don ? "BẬT" : "tắt"}${d.ma_kho ? " · kho " + esc(d.ma_kho) : ""}</span></div></div>`;
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
        ? `<button type="button" class="btn btn--sm" data-bg-xacnhan="${m.trang_thai === "tot" ? "go" : "ghi"}">${m.trang_thai === "tot" ? "Gỡ xác nhận" : "Tôi đã kiểm"}</button>`
        : ""}
          <span class="tag tag--${ERP_TONE[m.trang_thai] || "plain"}">${ERP_LABEL[m.trang_thai] || m.trang_thai}</span>
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
  khoGanSuKien();
  loadErpCauHinh();
  const req = ++khoState.listRequest;
  const k = await api("/kho");
  if (req !== khoState.listRequest) return;
  khoState.meta = k;
  khoState.sanPham = k.san_pham || [];
  khoState.status = state.khoFilter || khoState.status || "all";
  $("#c-kho").textContent = (k.het_hang + k.sap_het) || "";

  const cats = [...new Set(khoState.sanPham.map((x) => x.loai).filter(Boolean))].sort((a, b) => a.localeCompare(b, "vi"));
  ganLuaChon($("#khoCategory"), '<option value="all">Mọi danh mục</option>' + cats.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join(""));

  khoVeKpi(k);
  khoCapNhatChip(k);
  khoVeTon();
  if (khoState.tab === "bien_dong") {
    await loadKhoBienDong();
  }
  khoCapNhatChieuCaoToolbar();
}

