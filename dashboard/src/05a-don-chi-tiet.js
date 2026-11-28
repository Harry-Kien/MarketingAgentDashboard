/* ---------------- side panel chi tiết đơn hàng (3 tab) ---------------- */

function dhMoNgan() {
  const panel = $("#orderDetail");
  const layout = $("#orderLayout");
  if (!panel || !layout) return;
  if (panel.hidden) dhState.quayVe = document.activeElement;
  panel.hidden = false;
  panel.setAttribute("role", dhNganHep() ? "dialog" : "complementary");
  panel.setAttribute("aria-modal", String(dhNganHep()));
  layout.classList.add("is-ngan");
  document.body.classList.toggle("dh-khoa-cuon", dhNganHep());
}

function dhDongNgan() {
  dhState.detailRequest++;
  const panel = $("#orderDetail");
  const layout = $("#orderLayout");
  dhState.openId = null;
  dhState.detail = null;
  if (panel) { panel.hidden = true; panel.innerHTML = ""; }
  layout?.classList.remove("is-ngan");
  document.body.classList.remove("dh-khoa-cuon");
  $$("#orders [data-orow]").forEach((r) => r.classList.remove("is-on"));
  const ve = dhState.quayVe;
  dhState.quayVe = null;
  if (ve && document.contains(ve)) ve.focus({ preventScroll: true });
}

/* Vùng cảnh báo chung gọn ở đầu panel (chỉ 1 dòng/vấn đề + nút nhảy tab). */
function dhVeCanhBaoChung(o, st, curTab) {
  const items = [];
  if (st.xin_huy) items.push({ halt: true, text: `Khách xin huỷ (${dhFullTime(o.yeu_cau_huy_luc)})`, tab: "tong_quan" });
  if (st.doi_tra) items.push({ halt: false, text: "Khách yêu cầu đổi/trả hàng", tab: "tong_quan" });
  if (st.cho_dong_bo) items.push({ halt: false, text: "Đơn chưa vào kho/ERP", tab: "tong_quan" });
  if (st.cho_doi_soat_vd) {
    items.push({
      halt: st.tt_yc_vd === "manual_required",
      text: VAN_DON_YEU_CAU_LABEL[st.tt_yc_vd] || st.tt_yc_vd,
      tab: "van_chuyen",
    });
  }
  if (o.trang_thai_giao_hang === "delivery_failed") items.push({ halt: true, text: "Giao hàng thất bại — hàng đang ở hãng", tab: "van_chuyen" });
  else if (o.trang_thai_giao_hang === "returning") items.push({ halt: false, text: "Đơn đang hoàn về kho", tab: "van_chuyen" });
  else if (o.trang_thai_giao_hang === "returned") items.push({ halt: false, text: "Đã hoàn về — cần kiểm tra nhập kho", tab: "van_chuyen" });
  if (o.erp_van_chuyen_trang_thai === "dead") items.push({ halt: true, text: "Lỗi đồng bộ vận đơn sang ERPNext", tab: "erp" });
  if (!items.length) return "";
  const anyHalt = items.some((x) => x.halt);
  return `<div class="dh-alert-bar${anyHalt ? " is-halt" : ""}">${items.map((x) =>
    `<div class="dh-alert-bar__item${x.halt ? " dh-alert-bar__item--halt" : ""}">`
    + `<span><b>${esc(x.text)}</b></span>`
    + (curTab !== x.tab
      ? `<button type="button" class="dh-alert-bar__go" data-omo-tab="${x.tab}">Xem xử lý →</button>`
      : "")
    + `</div>`
  ).join("")}</div>`;
}

/* Chi tiết cảnh báo riêng từng tab để tránh lặp lại ở cả 3 tab. */
function dhVeCanhBaoTab(o, st, tab) {
  const list = [];
  if (tab === "tong_quan") {
    if (st.xin_huy) {
      list.push(`<div class="dh-alert dh-alert--halt"><b>Khách xin huỷ — ${esc(dhFullTime(o.yeu_cau_huy_luc))}</b>`
        + `${o.yeu_cau_huy_ly_do ? esc(o.yeu_cau_huy_ly_do) + "<br>" : ""}`
        + `Dừng đóng gói và gọi lại cho khách trước khi quyết định.</div>`);
    }
    if (st.doi_tra) {
      const loai = ({ doi: "đổi hàng", tra: "trả hàng" })[o.yeu_cau_doi_tra_loai] || "đổi/trả";
      list.push(`<div class="dh-alert"><b>Khách xin ${loai} — ${esc(dhFullTime(o.yeu_cau_doi_tra_luc))}</b>`
        + `${o.yeu_cau_doi_tra_ly_do ? esc(o.yeu_cau_doi_tra_ly_do) + "<br>" : ""}`
        + `Liên hệ khách kiểm tra tình trạng sản phẩm trước khi nhập hàng hoàn tại Kho → Nhập.</div>`);
    }
    if (st.cho_dong_bo) {
      list.push(`<div class="dh-alert"><b>Chưa vào được kho/ERP</b>`
        + `${o.erp_loi ? esc(o.erp_loi) : "Đang chờ đẩy Sales Order sang ERPNext."}`
        + `${o.erp_so_lan_thu ? ` (đã thử ${o.erp_so_lan_thu} lần)` : ""}`
        + `<br>Khách đã được hứa sẽ có người gọi xác nhận; máy đang tự thử lại.</div>`);
    }
  } else if (tab === "van_chuyen") {
    if (st.cho_doi_soat_vd) {
      list.push(`<div class="dh-alert${st.tt_yc_vd === "manual_required" ? " dh-alert--halt" : ""}">`
        + `<b>${esc(VAN_DON_YEU_CAU_LABEL[st.tt_yc_vd] || st.tt_yc_vd)}</b>`
        + `Mã tham chiếu <b>${esc(o.van_don_client_order_code || o.ma_don)}</b>`
        + `${o.van_don_so_lan_doi_soat ? ` · đã đối soát ${o.van_don_so_lan_doi_soat} lần` : ""}.<br>`
        + `${esc(o.van_don_ly_do_chan || o.van_don_loi_cuoi || "Đã tạm khoá tạo lại để tránh tạo trùng vận đơn GHN.")}</div>`);
    }
    if (o.trang_thai_giao_hang === "delivery_failed") {
      list.push(`<div class="dh-alert dh-alert--halt"><b>Giao hàng thất bại</b>`
        + `Hàng vẫn đang ở phía hãng vận chuyển — hệ thống chặn huỷ/tự cộng kho. Gọi khách hẹn giao lại hoặc làm việc với hãng hoàn hàng.</div>`);
    } else if (o.trang_thai_giao_hang === "returning") {
      list.push(`<div class="dh-alert"><b>Hàng đang hoàn về kho</b>`
        + `Hàng chưa quay về kệ — hệ thống chặn huỷ/hoàn kho cho tới khi hãng xác nhận đã trả hàng về shop.</div>`);
    } else if (o.trang_thai_giao_hang === "returned") {
      list.push(`<div class="dh-alert"><b>Hãng đã hoàn hàng về kho</b>`
        + `Hệ thống KHÔNG tự động cộng tồn kho. Kiểm tra số lượng &amp; nguyên seal rồi nhập lại qua <b>Kho → Nhập (Nhập hàng hoàn)</b>.</div>`);
    }
  } else if (tab === "erp") {
    if (o.erp_van_chuyen_trang_thai === "dead") {
      list.push(`<div class="dh-alert dh-alert--halt"><b>Lỗi đồng bộ vận đơn sang ERPNext</b>`
        + `${esc(o.erp_van_chuyen_loi || "Đồng bộ thất bại sau nhiều lần thử.")} Kiểm tra Sales Order và bấm <b>Thử lại đồng bộ vận đơn ERP</b> bên dưới.</div>`);
    }
  }
  return list.join("");
}

function dhVeTabTongQuan(ct) {
  const items = Array.isArray(ct.items) ? ct.items : [];
  const daThu = Number(ct.so_tien_da_thu || 0);
  const phiShip = Number(ct.phi_van_chuyen || 0);
  const tong = Number(ct.tong_tien || 0);
  const cod = Math.max(0, tong - daThu);
  const itemsHtml = items.length
    ? `<table class="dh-items-tbl">
        <thead><tr><th>Sản phẩm</th><th>SL</th><th>Thành tiền</th></tr></thead>
        <tbody>${items.map((it) => `<tr>
          <td>${esc(it.ten || it.ma || "Sản phẩm")}${it.ma ? `<span class="dh-sub">${esc(it.ma)} · ${vnd(it.don_gia)}</span>` : ""}</td>
          <td>&times;${Number(it.so_luong || 1)}</td>
          <td>${vnd(it.thanh_tien)}</td>
        </tr>`).join("")}</tbody>
      </table>`
    : '<p class="cvx-muc__trong">Không có danh sách sản phẩm.</p>';

  const convBtn = ct.conversation_id && coQuyen("hoi_thoai.doc")
    ? `<button type="button" class="cvx-lk" data-omo-ht="${esc(ct.conversation_id)}">
         <span class="cvx-lk__loai">Hội thoại gốc</span>
         <span class="cvx-lk__ten">Mở cuộc trò chuyện →</span>
       </button>`
    : "";
  const cvList = Array.isArray(ct.cong_viec) ? ct.cong_viec : [];
  const cvHtml = cvList.length
    ? `<section class="cvx-muc">
        <h4 class="cvx-muc__tieu">Công việc liên quan (${cvList.length})</h4>
        <ul class="dh-timeline">${cvList.map((v) => `<li>
          <b>${esc(v.tieu_de)}</b> · <span class="tag tag--plain">${esc(({moi: "Chờ xử lý", dang_lam: "Đang làm", xong: "Hoàn thành", huy: "Đã hủy"})[v.trang_thai] || "Chưa rõ")}</span>
          ${v.ket_qua ? `<div style="margin-top:2px">${esc(v.ket_qua)}</div>` : ""}
          <time>${esc(dhFullTime(v.tao_luc))}</time>
        </li>`).join("")}</ul>
      </section>`
    : "";

  return `<section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Khách hàng &amp; giao nhận</h4>
      <dl class="cvx-tq">
        <div><dt>Khách hàng</dt><dd>${esc(ct.khach_ten || "—")}</dd></div>
        <div><dt>Số điện thoại</dt><dd>${esc(ct.khach_sdt || "—")}</dd></div>
        <div style="grid-column:1 / -1"><dt>Địa chỉ giao hàng</dt><dd>${esc(ct.khach_dia_chi || "—")}</dd></div>
        ${ct.ghi_chu ? `<div style="grid-column:1 / -1"><dt>Ghi chú</dt><dd>${esc(ct.ghi_chu)}</dd></div>` : ""}
      </dl>
      ${convBtn ? `<div class="cvx-lk-ds" style="margin-top:10px">${convBtn}</div>` : ""}
    </section>
    <section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Sản phẩm &amp; thanh toán</h4>
      ${itemsHtml}
      <div class="dh-sum-list">
        <div class="dh-sum-row"><span>Tiền hàng</span><span>${vnd(tong)}</span></div>
        ${phiShip > 0 ? `<div class="dh-sum-row"><span>Phí vận chuyển</span><span>${vnd(phiShip)}</span></div>` : ""}
        <div class="dh-sum-row"><span>Đã thanh toán trước</span><span>${vnd(daThu)}</span></div>
        <div class="dh-sum-row dh-sum-cod"><span>Còn thu hộ (COD)</span><span>${vnd(cod)}</span></div>
      </div>
    </section>
    ${cvHtml}`;
}

function dhVeTabVanChuyen(ct, st) {
  const g = ct.trang_thai_giao_hang || "";
  const layHang = ct.van_don_da_lay_hang === true
    ? "Đã bàn giao hãng"
    : ct.van_don_da_lay_hang === false
    ? "Chưa lấy hàng (tại kho)"
    : (ct.ma_van_don ? "Chưa rõ (đơn cũ — chặn hoàn tự động)" : "—");
  const rec = ct.reconciliation || {};
  const ls = Array.isArray(ct.lich_su_giao_hang) ? [...ct.lich_su_giao_hang].reverse() : [];
  const bd = Array.isArray(ct.bien_dong_kho) ? ct.bien_dong_kho : [];
  const lyDoMap = {
    ban: "Xuất bán", huy_don: "Huỷ đơn", hoan_hang: "Nhập hàng hoàn",
    erp_tu_choi: "ERP từ chối", nhap: "Nhập kho", kiem_ke: "Kiểm kê",
  };
  return `<section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Thông tin vận đơn</h4>
      <dl class="cvx-tq">
        <div><dt>Hãng vận chuyển</dt><dd>${ct.don_vi_van_chuyen ? esc(ct.don_vi_van_chuyen.toUpperCase()) : "Chưa gán"}</dd></div>
        <div><dt>Mã vận đơn</dt><dd>${ct.ma_van_don ? `<b>${esc(ct.ma_van_don)}</b>` : "Chưa tạo"}</dd></div>
        <div><dt>Trạng thái giao</dt><dd>${g ? esc(dhCapFirst(NHAN_GIAO[g] || g)) : "Chưa có"}</dd></div>
        <div><dt>Phí vận chuyển</dt><dd>${Number(ct.phi_van_chuyen || 0) > 0 ? vnd(ct.phi_van_chuyen) : "—"}</dd></div>
        <div><dt>Bằng chứng lấy hàng</dt><dd>${esc(layHang)}</dd></div>
        <div><dt>Cập nhật cuối</dt><dd>${esc(dhFullTime(ct.cap_nhat_van_chuyen_luc))}</dd></div>
      </dl>
    </section>
    <section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Đối soát tạo vận đơn</h4>
      <dl class="cvx-tq">
        <div><dt>Trạng thái yêu cầu</dt><dd>${esc(VAN_DON_YEU_CAU_LABEL[rec.trang_thai] || rec.trang_thai || "Chưa gửi hãng")}</dd></div>
        <div><dt>Mã tham chiếu</dt><dd>${esc(rec.client_order_code || ct.ma_don)}</dd></div>
        <div><dt>Số lần đối soát</dt><dd>${Number(rec.so_lan_doi_soat || 0)}</dd></div>
        <div><dt>Xác nhận bởi</dt><dd>${esc(rec.xac_nhan_boi || "—")}</dd></div>
        ${rec.ly_do_chan || rec.loi_cuoi ? `<div style="grid-column:1 / -1"><dt>Chi tiết</dt><dd>${esc(rec.ly_do_chan || rec.loi_cuoi)}</dd></div>` : ""}
      </dl>
      ${st.cho_doi_soat_vd && dhCoSua() ? `<div class="cvx-muc__nut">
        <button type="button" class="btn btn--sm btn--primary" data-odoisoat="${ct.id}">Kiểm tra GHN</button>
        <button type="button" class="btn btn--sm btn--halt" data-oxnvandon="${ct.id}" data-omadon="${esc(ct.ma_don)}" data-oref="${esc(rec.client_order_code || ct.ma_don)}">Xác nhận GHN</button>
      </div>` : ""}
    </section>
    <section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Tiến trình giao hàng (${ls.length})</h4>
      ${ls.length ? `<ul class="dh-timeline">${ls.map((e) => `<li>
        <b>${esc(dhCapFirst(NHAN_GIAO[e.status] || e.status || "Cập nhật"))}</b>
        ${e.carrier ? ` · ${esc(String(e.carrier).toUpperCase())}` : ""}
        ${e.description ? `<div>${esc(e.description)}</div>` : ""}
        <time>${esc(dhFullTime(e.time))}</time>
      </li>`).join("")}</ul>` : '<p class="cvx-muc__trong">Chưa có cập nhật hành trình từ hãng vận chuyển.</p>'}
    </section>
    <section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Biến động kho của đơn (${bd.length})</h4>
      ${bd.length ? `<ul class="dh-timeline">${bd.map((b) => `<li>
        <b>${esc(b.ma)}</b> · ${b.thay_doi > 0 ? "+" : ""}${b.thay_doi} (${esc(lyDoMap[b.ly_do] || b.ly_do)})
        ${b.ghi_chu ? `<div>${esc(b.ghi_chu)}</div>` : ""}
        <time>#${b.id} · ${esc(dhFullTime(b.luc))}</time>
      </li>`).join("")}</ul>` : '<p class="cvx-muc__trong">Chưa ghi nhận biến động kho cho đơn này.</p>'}
    </section>`;
}

function dhVeTabErp(ct, st) {
  const ttShip = ct.erp_van_chuyen_trang_thai || "not_required";
  const erpOrderState = ct.erp_ma_don
    ? "Đã tạo Sales Order"
    : ct.trang_thai === "cho_dong_bo"
    ? "Đang chờ đồng bộ đơn"
    : "Chưa đẩy sang ERPNext";
  return `<section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Liên kết đơn hàng ERPNext</h4>
      <dl class="cvx-tq">
        <div><dt>Mã Sales Order</dt><dd>${ct.erp_ma_don ? `<b>${esc(ct.erp_ma_don)}</b>` : "Chưa liên kết"}</dd></div>
        <div><dt>Trạng thái đơn ERP</dt><dd>${esc(erpOrderState)}</dd></div>
        <div><dt>Số lần thử đơn</dt><dd>${Number(ct.erp_so_lan_thu || 0)}</dd></div>
        <div><dt>Lỗi tạo đơn ERP</dt><dd>${esc(ct.erp_loi || "Không có")}</dd></div>
      </dl>
    </section>
    <section class="cvx-muc">
      <h4 class="cvx-muc__tieu">Đồng bộ vận đơn sang ERPNext</h4>
      <dl class="cvx-tq">
        <div><dt>Trạng thái đồng bộ</dt><dd><span class="tag tag--${ERP_SHIP_TONE[ttShip] || "plain"}">${esc(ERP_SHIP_LABEL[ttShip] || ttShip)}</span></dd></div>
        <div><dt>Số lần thử</dt><dd>${Number(ct.erp_van_chuyen_so_lan_thu || 0)}</dd></div>
        <div><dt>Đồng bộ gần nhất</dt><dd>${esc(dhFullTime(ct.erp_van_chuyen_dong_bo_luc))}</dd></div>
        <div><dt>Lịch thử lại</dt><dd>${esc(dhFullTime(ct.erp_van_chuyen_thu_lai_luc))}</dd></div>
        ${ct.erp_van_chuyen_loi ? `<div style="grid-column:1 / -1"><dt>Chi tiết / Lỗi</dt><dd>${esc(ct.erp_van_chuyen_loi)}</dd></div>` : ""}
      </dl>
      ${ttShip === "skipped_cancelled"
        ? '<p class="cvx-muc__trong" style="margin-top:8px">Sales Order trên ERPNext đã bị huỷ nên hệ thống tự động bỏ qua đồng bộ vận đơn (không sinh lỗi lặp).</p>'
        : ""}
      ${st.erp_retry_duoc && dhCoSua() ? `<div class="cvx-muc__nut">
        <button type="button" class="btn btn--sm btn--primary" data-oerpretry="${ct.id}">Thử lại đồng bộ vận đơn ERP</button>
      </div>` : ""}
    </section>`;
}

function dhVeChiTiet() {
  const panel = $("#orderDetail");
  const ct = dhState.detail;
  if (!panel || !ct) return;
  const st = dhTinhTrang(ct);
  const tab = dhState.tab || "tong_quan";
  const bodyHtml = tab === "van_chuyen"
    ? dhVeTabVanChuyen(ct, st)
    : tab === "erp"
    ? dhVeTabErp(ct, st)
    : dhVeTabTongQuan(ct);

  panel.innerHTML = `<header class="cvx-ngan__dau">
      <div class="cvx-ngan__hang">
        <span class="tag tag--${ORDER_TONE[ct.trang_thai] || "plain"}">${esc(ORDER_LABEL[ct.trang_thai] || ct.trang_thai)}</span>
        ${srcBadge(ct.channel, ct.nen_tang)}
        <button type="button" class="btn btn--sm btn--ghost cvx-ngan__dong" data-odong aria-label="Đóng chi tiết">✕</button>
      </div>
      <h3 class="cvx-ngan__ten" id="orderDetailTitle" tabindex="-1">${esc(ct.ma_don)}</h3>
      <div class="dh-head-meta">
        <span>${esc(dhFullTime(ct.created_at))}</span>
        <span class="dh-head-total">${vnd(ct.tong_tien)}</span>
      </div>
      <div class="cvx-ngan__hang cvx-ngan__hd">${dhVeNutNhom(ct, true)}</div>
    </header>
    <div class="dh-tabs" role="tablist" aria-label="Chi tiết đơn hàng">
      <button type="button" role="tab" class="dh-tab${tab === "tong_quan" ? " is-on" : ""}" data-otab="tong_quan" aria-selected="${tab === "tong_quan"}">Tổng quan</button>
      <button type="button" role="tab" class="dh-tab${tab === "van_chuyen" ? " is-on" : ""}" data-otab="van_chuyen" aria-selected="${tab === "van_chuyen"}">Vận chuyển</button>
      <button type="button" role="tab" class="dh-tab${tab === "erp" ? " is-on" : ""}" data-otab="erp" aria-selected="${tab === "erp"}">Đồng bộ ERP</button>
    </div>
    ${dhVeCanhBaoChung(ct, st, tab)}
    <div class="cvx-ngan__than">
      ${dhVeCanhBaoTab(ct, st, tab)}
      ${bodyHtml}
    </div>`;
}

async function dhTaiChiTiet(id, cuon = true) {
  if (!id) return;
  const request = ++dhState.detailRequest;
  const doiDon = dhState.openId !== id;
  if (cuon) {
    dhState.openId = id;
    dhMoNgan();
    if (doiDon) {
      dhState.detail = null;
      $("#orderDetail").innerHTML = '<button type="button" class="btn btn--sm" data-odong>Đóng chi tiết</button><p class="empty" role="status">Đang tải chi tiết…</p>';
    }
  }
  try {
    const d = await api(`/orders/${encodeURIComponent(id)}`);
    if (request !== dhState.detailRequest) return;
    dhState.openId = id;
    dhState.detail = d;
    if (doiDon) dhState.tab = "tong_quan";
    dhMoNgan();
    dhVeChiTiet();
    $$("#orders [data-orow]").forEach((r) => r.classList.toggle("is-on", r.dataset.orow === id));
    if (cuon) {
      $("#orderDetailTitle")?.focus({ preventScroll: true });
    }
  } catch (e) {
    if (request !== dhState.detailRequest) return;
    if (dhState.openId === id || cuon) dhDongNgan();
    toast(e.message, true);
  }
}
