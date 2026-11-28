/* ---------------- đơn hàng ---------------- */

/* Khớp `agent/core/tools.py::TRANG_THAI_DON`. Có test canh hai bên không
   trôi xa nhau — thiếu một nhãn ở đây thì dòng đơn hiện ra chữ kỹ thuật
   trần, thẻ xám, và người trực không hiểu đang nhìn cái gì. */
const ORDER_LABEL = {
  cho_duyet: "Chờ duyệt", da_chot: "Đã chốt", da_huy: "Đã huỷ",
  cho_dong_bo: "Chờ đồng bộ kho", da_giao: "Đã giao",
};
const ORDER_TONE = {
  cho_duyet: "duyet", da_chot: "chot", da_huy: "huy",
  cho_dong_bo: "duyet", da_giao: "chot",
};
/* Khớp `agent/shipping/models.InternalShippingStatus`. */
const NHAN_GIAO = {
  ready_to_pick: "chờ lấy hàng",
  delivering: "đang giao",
  delivered: "đã giao",
  delivery_failed: "giao thất bại",
  returning: "đang hoàn hàng",
  returned: "đã hoàn về",
  cancelled: "đã huỷ vận đơn",
};
const VAN_DON_DOI_SOAT_CHAN = new Set([
  "sending", "unknown_timeout", "reconciling", "manual_required",
]);
const VAN_DON_YEU_CAU_LABEL = {
  not_sent: "Chưa gửi hãng",
  sending: "Đang gửi GHN",
  confirmed: "Đã xác nhận",
  rejected: "Hãng từ chối",
  unknown_timeout: "Chờ đối soát GHN",
  reconciling: "Đang đối soát GHN",
  reconciled: "Đã đối soát",
  manual_required: "Cần xác nhận GHN thủ công",
};
const ERP_SHIP_LABEL = {
  not_required: "Chưa cần đồng bộ",
  pending: "Chờ đồng bộ ERP",
  processing: "Đang đồng bộ ERP",
  retry: "Đang thử lại ERP",
  synced: "Đã đồng bộ ERP",
  dead: "Lỗi đồng bộ ERP",
  skipped_cancelled: "Bỏ qua (ERP đã huỷ)",
};
const ERP_SHIP_TONE = {
  not_required: "plain",
  pending: "duyet",
  processing: "duyet",
  retry: "duyet",
  synced: "chot",
  dead: "huy",
  skipped_cancelled: "plain",
};
const vnd = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

/* Thanh toán VietQR ẨN khỏi giao diện theo phiếu việc của chủ dự án
   (20.11.2026): giữ nguyên mã & API. */
const HIEN_VIETQR = false;

/* Trạng thái lọc, phân trang và ngăn chi tiết của module Đơn hàng. */
const dhState = {
  status: "all",
  q: "",
  channel: "all",
  thanh_toan: "all",
  van_chuyen: "all",
  tu_ngay: "",
  den_ngay: "",
  page: 1,
  pageSize: 20,
  items: [],
  openId: null,
  detail: null,
  tab: "tong_quan",
  quayVe: null,
  searchTimer: null,
  listRequest: 0,
  detailRequest: 0,
};

let VAN_CHUYEN = null;

function dhCoSua() {
  return !!(state.toiQuyen && state.toiQuyen.has("don.sua"));
}

function dhNganHep() {
  return window.matchMedia("(max-width: 1180px)").matches;
}

function dhFullTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("vi-VN", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return String(iso); }
}

function dhCapFirst(s) {
  const t = String(s || "");
  return t ? t.charAt(0).toUpperCase() + t.slice(1) : "";
}

function dhTinhTrang(o) {
  const cho_duyet = o.trang_thai === "cho_duyet";
  const cho_dong_bo = o.trang_thai === "cho_dong_bo";
  const xin_huy = !!(o.yeu_cau_huy_luc && o.trang_thai !== "da_huy" && o.trang_thai !== "da_giao");
  const doi_tra = !!(o.yeu_cau_doi_tra_luc && o.trang_thai !== "da_huy");
  const da_thu = Number(o.so_tien_da_thu || 0);
  const tong = Number(o.tong_tien || 0);
  const con_mo = o.trang_thai === "da_chot" || o.trang_thai === "cho_dong_bo";
  const tt_yc_vd = o.van_don_trang_thai_yeucau || "not_sent";
  const cho_doi_soat_vd = !o.ma_van_don && VAN_DON_DOI_SOAT_CHAN.has(tt_yc_vd);
  const tao_van_don = !!(VAN_CHUYEN && VAN_CHUYEN.that && o.trang_thai === "da_chot"
    && !o.ma_van_don && !xin_huy && !cho_doi_soat_vd);
  const erp_loi_vd = o.erp_van_chuyen_trang_thai === "dead" || o.erp_van_chuyen_trang_thai === "retry";
  const erp_retry_duoc = !!(o.erp_ma_don && o.ma_van_don
    && ["pending", "retry", "dead"].includes(o.erp_van_chuyen_trang_thai || ""));
  const ship_su_co = o.trang_thai_giao_hang === "delivery_failed" || o.trang_thai_giao_hang === "returning";
  const canh_bao_do = xin_huy || tt_yc_vd === "manual_required" || o.erp_van_chuyen_trang_thai === "dead"
    || o.trang_thai_giao_hang === "delivery_failed";
  const canh_bao_vang = cho_duyet || cho_dong_bo || cho_doi_soat_vd || doi_tra || ship_su_co || erp_loi_vd;
  return {
    cho_duyet, cho_dong_bo, xin_huy, doi_tra, da_thu, tong, con_mo,
    tt_yc_vd, cho_doi_soat_vd, tao_van_don, erp_loi_vd, erp_retry_duoc,
    ship_su_co, canh_bao_do, canh_bao_vang,
  };
}

function dhThanhToanBadge(o) {
  const da = Number(o.so_tien_da_thu || 0);
  const tong = Number(o.tong_tien || 0);
  if (da <= 0) return '<span class="tag tag--plain">Chưa thu</span>';
  if (tong > 0 && da >= tong) {
    return `<span class="tag tag--chot" title="${o.da_thu_luc ? "Ghi lúc " + esc(dhFullTime(o.da_thu_luc)) : ""}">Đã thu đủ</span>`;
  }
  return `<span class="tag tag--duyet" title="Đã thu ${esc(vnd(da))}">Thu ${esc(vnd(da))}</span>`;
}

function dhVanChuyenCell(o, st) {
  if (st.cho_doi_soat_vd) {
    const tone = st.tt_yc_vd === "manual_required" ? "huy" : "duyet";
    return `<span class="dh-stack"><span class="tag tag--${tone}">${esc(VAN_DON_YEU_CAU_LABEL[st.tt_yc_vd] || st.tt_yc_vd)}</span>`
      + `<span class="dh-sub">${esc(o.van_don_client_order_code || o.ma_don)}</span></span>`;
  }
  if (!o.ma_van_don) {
    return '<span class="dh-sub" style="margin-top:0">Chưa tạo vận đơn</span>';
  }
  const g = o.trang_thai_giao_hang || "";
  const nhan = g ? dhCapFirst(NHAN_GIAO[g] || g) : "Chưa rõ trạng thái";
  const tone = g === "delivered" ? "chot"
    : (g === "delivery_failed" || g === "cancelled") ? "huy"
      : (g === "returning" || g === "returned" || g === "ready_to_pick") ? "duyet"
        : "plain";
  const hang = o.don_vi_van_chuyen ? o.don_vi_van_chuyen.toUpperCase() + " · " : "";
  return `<span class="dh-stack"><span class="tag tag--${tone}">${esc(nhan)}</span>`
    + `<span class="dh-sub">${esc(hang + o.ma_van_don)}</span></span>`;
}

/* Hành động theo trạng thái & quyền: 1 nút chính + menu "⋯" cho thao tác phụ. */
function dhHanhDong(o) {
  const st = dhTinhTrang(o);
  const sua = dhCoSua();
  let chinh = null;
  const them = [];
  if (sua) {
    if (st.cho_duyet) {
      chinh = { attr: `data-oapprove="${o.id}"`, nhan: "Duyệt", lop: "btn--go" };
    } else if (st.cho_doi_soat_vd) {
      chinh = { attr: `data-odoisoat="${o.id}"`, nhan: "Kiểm tra GHN", lop: "btn--primary" };
    } else if (st.tao_van_don) {
      chinh = { attr: `data-ovandon="${o.id}"`, nhan: "Tạo vận đơn", lop: "btn--go" };
    } else if (st.con_mo) {
      chinh = {
        attr: `data-odathu="${o.id}" data-ma="${esc(o.ma_don)}" data-goi-y="${Number(o.tong_tien || 0) + Number(o.phi_van_chuyen || 0)}" data-da-thu="${st.da_thu}"`,
        nhan: "Xác nhận đã nhận tiền",
        lop: "btn--ghost",
      };
    }

    if (st.con_mo && !(chinh && chinh.attr.includes("data-odathu"))) {
      them.push({
        attr: `data-odathu="${o.id}" data-ma="${esc(o.ma_don)}" data-goi-y="${Number(o.tong_tien || 0) + Number(o.phi_van_chuyen || 0)}" data-da-thu="${st.da_thu}"`,
        nhan: "Xác nhận đã nhận tiền",
        goiY: "Cập nhật số tiền khách đã chuyển khoản",
      });
    }
    if (st.tao_van_don && !(chinh && chinh.attr.includes("data-ovandon"))) {
      them.push({
        attr: `data-ovandon="${o.id}"`,
        nhan: "Tạo vận đơn",
        goiY: `Đẩy vận đơn sang ${(VAN_CHUYEN?.hang || "hãng").toUpperCase()}`,
      });
    }
    if (st.cho_doi_soat_vd) {
      them.push({
        attr: `data-oxnvandon="${o.id}" data-omadon="${esc(o.ma_don)}" data-oref="${esc(o.van_don_client_order_code || o.ma_don)}"`,
        nhan: "Xác nhận GHN thủ công…",
        goiY: "Đối chiếu kết quả trên cổng GHN",
        nguy: true,
      });
    }
    if (st.erp_retry_duoc) {
      them.push({
        attr: `data-oerpretry="${o.id}"`,
        nhan: "Thử lại đồng bộ ERP",
        goiY: "Đẩy lại mã vận đơn sang Sales Order ERPNext",
      });
    }
    if (o.trang_thai !== "da_huy" && o.trang_thai !== "da_giao") {
      them.push({
        attr: `data-ocancel="${o.id}"`,
        nhan: "Huỷ đơn",
        goiY: o.ma_van_don
          ? "Chặn huỷ nếu hàng đã bàn giao hãng (BUG-17-04)"
          : "Huỷ đơn nội bộ và hoàn tồn nếu đủ điều kiện",
        nguy: true,
      });
    }
  }
  return { chinh, them };
}

function dhVeNutNhom(o, trongNgan = false) {
  const { chinh, them } = dhHanhDong(o);
  const nutChinh = chinh
    ? `<button type="button" class="btn btn--sm ${chinh.lop}" ${chinh.attr}>${esc(chinh.nhan)}</button>`
    : (!trongNgan ? `<button type="button" class="btn btn--sm btn--ghost" data-omo="${o.id}">Chi tiết</button>` : "");
  const nutThem = them.length ? `<details class="hd-them${trongNgan ? " cvx-them" : ""}">
      <summary class="btn btn--sm btn--ghost" aria-label="Thao tác khác" title="Thao tác khác">⋯</summary>
      <div class="hd-them__menu" role="menu">${them.map((m) =>
    `<button type="button" class="hd-them__muc${m.nguy ? " cvx-them__nguy" : ""}" role="menuitem" ${m.attr}>
          <span class="hd-them__ten">${esc(m.nhan)}</span><span class="hd-them__goiy">${esc(m.goiY)}</span></button>`).join("")}
      </div>
    </details>` : "";
  return `<span class="dh-act-grp">${nutChinh}${nutThem}</span>`;
}

function dhVeKpi(kpi) {
  const el = $("#orderKpi");
  if (!el || !kpi) return;
  const cur = dhState.status;
  el.innerHTML = [
    ["all", "Tổng đơn", kpi.tong_don, "trong phạm vi kênh"],
    ["cho_duyet", "Chờ duyệt", kpi.cho_duyet, "cần nhân viên xác nhận"],
    ["da_chot", "Đã chốt", kpi.da_chot, "đã xác nhận đơn hàng"],
    ["can_xu_ly", "Cần xử lý", kpi.can_xu_ly, "xin huỷ, đối soát, lỗi giao/ERP"],
  ].map(([key, label, count, hint]) => `<button type="button" class="readout__cell${cur === key ? " is-on" : ""}" data-okpi="${key}" aria-pressed="${cur === key}">
    <span class="readout__label">${label}</span><span class="readout__value">${num(count)}</span>
    <span class="readout__unit">${hint}</span></button>`).join("");
}

function dhCapNhatChip(dem) {
  if (!dem) return;
  $$("#orderfilter [data-ocnt]").forEach((b) => {
    const k = b.dataset.ocnt;
    b.textContent = dem[k] != null ? `(${dem[k]})` : "";
  });
  $$("#orderfilter .chip").forEach((c) => {
    c.classList.toggle("is-on", c.dataset.ostatus === dhState.status);
  });
}

function dhCoLoc() {
  return dhState.status !== "all" || !!dhState.q || dhState.channel !== "all"
    || dhState.thanh_toan !== "all" || dhState.van_chuyen !== "all"
    || !!dhState.tu_ngay || !!dhState.den_ngay;
}

function dhVeBang(items) {
  const box = $("#orders");
  if (!box) return;
  if (!items.length) {
    box.innerHTML = `<p class="empty">${dhCoLoc()
      ? "Không có đơn hàng nào khớp bộ lọc hiện tại."
      : "Chưa có đơn hàng nào."}</p>`;
    return;
  }

  const rowsHtml = items.map((o) => {
    const st = dhTinhTrang(o);
    const cls = (dhState.openId === o.id ? " is-on" : "")
      + (st.canh_bao_do ? " is-alert" : st.canh_bao_vang ? " is-warn" : "");
    const coTag = [
      st.xin_huy ? '<span class="tag tag--halt">Xin huỷ</span>' : "",
      st.doi_tra ? `<span class="tag tag--duyet">Đổi/trả</span>` : "",
      o.erp_van_chuyen_trang_thai === "dead" ? '<span class="tag tag--huy">Lỗi ERP</span>' : "",
    ].filter(Boolean).join(" ");
    return `<tr class="dh-tr${cls}" data-orow="${o.id}">
      <td>
        <button type="button" class="dh-code" data-omo="${o.id}">${esc(o.ma_don)}</button>
        ${o.erp_ma_don ? `<span class="dh-sub">ERP: ${esc(o.erp_ma_don)}</span>` : ""}
      </td>
      <td class="dh-col-cust">
        <span class="dh-cust">${esc(o.khach_ten)}</span>
        <span class="dh-sub">${esc(o.khach_sdt || "—")}</span>
      </td>
      <td>${srcBadge(o.channel, o.nen_tang)}</td>
      <td>
        <span class="dh-stack">
          <span class="tag tag--${ORDER_TONE[o.trang_thai] || "plain"}">${esc(ORDER_LABEL[o.trang_thai] || o.trang_thai)}</span>
          ${coTag ? `<span>${coTag}</span>` : ""}
        </span>
      </td>
      <td>${dhThanhToanBadge(o)}</td>
      <td class="dh-col-ship">${dhVanChuyenCell(o, st)}</td>
      <td class="is-num"><b>${vnd(o.tong_tien)}</b></td>
      <td class="dh-col-time" title="${esc(dhFullTime(o.created_at))}">${clock(o.created_at)}</td>
      <td class="is-act">${dhVeNutNhom(o, false)}</td>
    </tr>`;
  }).join("");

  const cardsHtml = items.map((o) => {
    const st = dhTinhTrang(o);
    const cls = (dhState.openId === o.id ? " is-on" : "")
      + (st.canh_bao_do ? " is-alert" : st.canh_bao_vang ? " is-warn" : "");
    return `<article class="dh-card${cls}" data-orow="${o.id}">
      <div class="dh-card__top">
        <button type="button" class="dh-code" data-omo="${o.id}">${esc(o.ma_don)}</button>
        <span class="tag tag--${ORDER_TONE[o.trang_thai] || "plain"}">${esc(ORDER_LABEL[o.trang_thai] || o.trang_thai)}</span>
      </div>
      <div class="dh-card__mid">
        <span><b>${esc(o.khach_ten)}</b> · ${esc(o.khach_sdt || "—")}</span>
        ${srcBadge(o.channel, o.nen_tang)}
      </div>
      <div class="dh-card__mid">
        <span>${dhThanhToanBadge(o)}</span>
        <span>${dhVanChuyenCell(o, st)}</span>
      </div>
      <div class="dh-card__bot">
        <span><b>${vnd(o.tong_tien)}</b> · <span style="color:hsl(var(--muted-foreground))">${clock(o.created_at)}</span></span>
        ${dhVeNutNhom(o, false)}
      </div>
    </article>`;
  }).join("");

  box.innerHTML = `<div class="dh-table-wrap">
      <table class="dh-table">
        <thead>
          <tr>
            <th>Mã đơn</th>
            <th>Khách hàng</th>
            <th>Kênh</th>
            <th>Trạng thái</th>
            <th>Thanh toán</th>
            <th>Vận chuyển</th>
            <th class="is-num">Tổng tiền</th>
            <th>Thời gian</th>
            <th class="is-act">Thao tác</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
    <div class="dh-cards">${cardsHtml}</div>`;
}

function dhVePhanTrang(total, page, totalPages, pageSize) {
  const el = $("#orderPager");
  if (!el) return;
  if (total <= 0) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  const tu = (page - 1) * pageSize + 1;
  const den = Math.min(total, page * pageSize);
  el.innerHTML = `<span>Hiển thị <b>${tu}–${den}</b> / <b>${total}</b> đơn hàng</span>
    <span class="dh-pager__nav">
      <button type="button" class="btn btn--sm btn--ghost" data-opage="${page - 1}"${page <= 1 ? " disabled" : ""}>← Trước</button>
      <span>Trang ${page}/${totalPages}</span>
      <button type="button" class="btn btn--sm btn--ghost" data-opage="${page + 1}"${page >= totalPages ? " disabled" : ""}>Sau →</button>
    </span>`;
}


/* ---------------- thực thi hành động đơn hàng ---------------- */

async function dhXuLyNut(btn) {
  const menu = btn.closest("details");
  if (menu) menu.open = false;

  if (btn.dataset.oapprove) {
    btn.disabled = true;
    try {
      const r = await api("/orders/" + btn.dataset.oapprove + "/approve", { method: "POST" });
      if (r.erp === "tu_choi") toast("ERP từ chối đơn " + r.ma_don + " — đơn đã huỷ, hàng trả về kho. " + (r.erp_loi || ""), true);
      else if (r.erp === "cho_lai") toast("Đã duyệt " + r.ma_don + ", nhưng chưa vào được ERP — máy tự thử lại.", true);
      else toast(r.erp_ma_don ? "Đã duyệt " + r.ma_don + " · ERP " + r.erp_ma_don + "." : "Đã duyệt đơn " + r.ma_don + ".");
    } catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; await loadOrders(); }
    return;
  }

  if (btn.dataset.ocancel) {
    btn.disabled = true;
    try {
      const r = await api("/orders/" + btn.dataset.ocancel + "/cancel", { method: "POST" });
      const nhac = [r.can_huy_tay, r.can_hoan_tien].filter(Boolean).join(" ");
      if (nhac) toast("Đã huỷ " + r.ma_don + ". " + nhac, true);
      else toast("Đã huỷ đơn.");
    } catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; await loadOrders(); }
    return;
  }

  if (btn.dataset.odathu) {
    const daCo = Number(btn.dataset.daThu || 0);
    const d = await hoiHop({
      tieu_de: `Xác nhận đã nhận tiền · ${btn.dataset.ma}`,
      phu: "Đối chiếu sao kê ngân hàng trước khi ghi — hệ thống không đọc được tài khoản. "
        + "Vận đơn tạo sau đó chỉ thu hộ phần còn lại.",
      truong: [
        {
          name: "so_tien", label: "Tổng số tiền đã nhận (đồng)", type: "number",
          value: daCo > 0 ? daCo : btn.dataset.goiY, min: 1, step: 1, required: true
        },
        { name: "ghi_chu", label: "Ghi chú", hint: "mã giao dịch ngân hàng…", maxlength: 300 },
      ],
      nut: "Xác nhận đã nhận tiền",
    });
    if (!d) return;
    try {
      const r = await api("/orders/" + btn.dataset.odathu + "/da-thu-tien", {
        method: "POST",
        body: JSON.stringify({ so_tien: parseInt(d.so_tien, 10), ghi_chu: d.ghi_chu || "" }),
      });
      if (r.can_sua_cod) toast("Đã ghi " + vnd(r.so_tien_da_thu) + ". " + r.can_sua_cod, true);
      else toast("Đã ghi nhận " + vnd(r.so_tien_da_thu) + " cho đơn " + r.ma_don
        + " · còn thu hộ " + vnd(r.thu_ho_cod) + ".");
      await loadOrders();
    } catch (e) { toast(e.message, true); }
    return;
  }

  if (btn.dataset.ovandon) {
    btn.disabled = true;
    try {
      const r = await api("/orders/" + btn.dataset.ovandon + "/van-don", { method: "POST", body: "{}" });
      toast(r.da_co_san ? "Đơn đã có vận đơn " + r.ma_van_don + "."
        : "Đã tạo vận đơn " + r.ma_van_don + " và nhắn mã cho khách.");
    } catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; await loadOrders(); }
    return;
  }

  if (btn.dataset.odoisoat) {
    btn.disabled = true;
    try {
      const r = await api("/orders/" + btn.dataset.odoisoat + "/shipping-reconcile", { method: "POST" });
      if (r.ok && r.ma_van_don) toast("Đã đối soát GHN: khôi phục vận đơn " + r.ma_van_don + ".");
      else toast(r.ly_do_chan || r.loi || "Chưa xác nhận được trên GHN; cần kiểm tra thủ công.", true);
    } catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; await loadOrders(); }
    return;
  }

  if (btn.dataset.oerpretry) {
    btn.disabled = true;
    try {
      const r = await api("/orders/" + btn.dataset.oerpretry + "/shipping-erp-retry", { method: "POST" });
      toast(r.ok ? `Đồng bộ ERP: ${ERP_SHIP_LABEL[r.trang_thai] || r.trang_thai}.`
        : (r.loi || "Đồng bộ ERP chưa thành công — máy sẽ thử lại."), !r.ok);
    } catch (e) { toast(e.message, true); }
    finally { btn.disabled = false; await loadOrders(); }
    return;
  }

  if (btn.dataset.oxnvandon) {
    const d = await hoiHop({
      tieu_de: `Xác nhận GHN thủ công · ${btn.dataset.omadon}`,
      phu: `Mã tham chiếu client_order_code: ${btn.dataset.oref}. Kiểm tra cổng GHN trước khi xác nhận.`,
      truong: [
        {
          name: "ket_qua",
          label: "Kết quả kiểm tra trên cổng GHN",
          type: "select",
          value: "da_co_van_don",
          options: [
            { value: "da_co_van_don", label: "GHN đã tạo vận đơn (nhập mã vận đơn bên dưới)" },
            { value: "chua_tao_tren_ghn", label: "GHN chưa tạo đơn — mở khoá tạo lại với cùng mã tham chiếu" },
          ],
          required: true,
        },
        { name: "ma_van_don", label: "Mã vận đơn GHN (bắt buộc nếu GHN đã tạo)", placeholder: "Ví dụ: L8XYZ9", maxlength: 64 },
        { name: "ghi_chu", label: "Bằng chứng / ghi chú đối soát", type: "textarea", rows: 2, required: true, maxlength: 500, placeholder: "Ví dụ: Đã kiểm tra cổng GHN ShopId..., không có đơn / đã có mã..." },
      ],
      nut: "Xác nhận",
      nguy_hiem: true,
    });
    if (!d) return;
    if (d.ket_qua === "da_co_van_don" && !d.ma_van_don) {
      toast("Vui lòng nhập mã vận đơn GHN khi chọn GHN đã tạo.", true);
      return;
    }
    try {
      const r = await api("/orders/" + btn.dataset.oxnvandon + "/shipping-manual-confirm", {
        method: "POST",
        body: JSON.stringify({
          ket_qua: d.ket_qua,
          ma_van_don: d.ma_van_don || "",
          ghi_chu: d.ghi_chu || "",
        }),
      });
      toast(r.ma_van_don
        ? `Đã xác nhận vận đơn ${r.ma_van_don}.`
        : "Đã xác nhận GHN chưa tạo đơn — có thể tạo vận đơn lại.");
      await loadOrders();
    } catch (e) { toast(e.message, true); }
  }
}

/* ---------------- gắn sự kiện một lần ---------------- */

function dhCapNhatChieuCaoToolbar() {
  const tb = $("#orderToolbar");
  const khung = $(".dh-khung");
  if (tb && khung) {
    khung.style.setProperty("--dh-toolbar-h", tb.offsetHeight + "px");
  }
}

function dhGanSuKien() {
  const view = $('.view[data-view="donhang"]');
  if (!view || view.dataset.dhBound) return;
  view.dataset.dhBound = "1";

  const tb = $("#orderToolbar", view);
  if (tb && typeof ResizeObserver !== "undefined") {
    new ResizeObserver(() => dhCapNhatChieuCaoToolbar()).observe(tb);
  }
  dhCapNhatChieuCaoToolbar();

  $$("#orderfilter .chip", view).forEach((chip) =>
    chip.addEventListener("click", () => {
      dhState.status = chip.dataset.ostatus;
      state.orderFilter = dhState.status;
      dhState.page = 1;
      loadOrders();
    })
  );

  $("#orderSearch", view)?.addEventListener("input", (e) => {
    dhState.q = e.target.value.trim();
    dhState.page = 1;
    clearTimeout(dhState.searchTimer);
    dhState.searchTimer = setTimeout(() => loadOrders(), 240);
  });

  const bindSel = (sel, key) => $(sel, view)?.addEventListener("change", (e) => {
    dhState[key] = e.target.value;
    dhState.page = 1;
    loadOrders();
  });
  bindSel("#orderChannel", "channel");
  bindSel("#orderPay", "thanh_toan");
  bindSel("#orderShip", "van_chuyen");
  bindSel("#orderFrom", "tu_ngay");
  bindSel("#orderTo", "den_ngay");

  $("#orderReset", view)?.addEventListener("click", () => {
    dhState.status = "all";
    state.orderFilter = "all";
    dhState.q = "";
    dhState.channel = "all";
    dhState.thanh_toan = "all";
    dhState.van_chuyen = "all";
    dhState.tu_ngay = "";
    dhState.den_ngay = "";
    dhState.page = 1;
    if ($("#orderSearch", view)) $("#orderSearch", view).value = "";
    if ($("#orderChannel", view)) $("#orderChannel", view).value = "all";
    if ($("#orderPay", view)) $("#orderPay", view).value = "all";
    if ($("#orderShip", view)) $("#orderShip", view).value = "all";
    if ($("#orderFrom", view)) $("#orderFrom", view).value = "";
    if ($("#orderTo", view)) $("#orderTo", view).value = "";
    loadOrders();
  });

  view.addEventListener("click", async (e) => {
    if (e.target.closest("[data-oretry]")) { await loadOrders(); return; }
    const kpi = e.target.closest("[data-okpi]");
    if (kpi) {
      dhState.status = kpi.dataset.okpi;
      state.orderFilter = dhState.status;
      dhState.page = 1;
      loadOrders();
      return;
    }
    const pg = e.target.closest("[data-opage]");
    if (pg && !pg.disabled) {
      dhState.page = Math.max(1, parseInt(pg.dataset.opage, 10) || 1);
      loadOrders();
      return;
    }
    if (e.target.closest("[data-odong]")) { dhDongNgan(); return; }
    const tabBtn = e.target.closest("[data-otab]");
    if (tabBtn) {
      dhState.tab = tabBtn.dataset.otab;
      dhVeChiTiet();
      $(`#orderDetail [data-otab="${dhState.tab}"]`)?.focus({ preventScroll: true });
      return;
    }
    const goTab = e.target.closest("[data-omo-tab]");
    if (goTab) {
      dhState.tab = goTab.dataset.omoTab;
      dhVeChiTiet();
      $(`#orderDetail [data-otab="${dhState.tab}"]`)?.focus({ preventScroll: true });
      return;
    }
    const moHt = e.target.closest("[data-omo-ht]");
    if (moHt) {
      const cid = moHt.dataset.omoHt;
      dhDongNgan();
      state.openConv = cid;
      if (typeof doiMan === "function") doiMan("hoithoai");
      else $('[data-view="hoithoai"]')?.click();
      if (typeof loadThread === "function") loadThread(cid);
      return;
    }
    const act = e.target.closest("[data-oapprove],[data-ocancel],[data-odathu],[data-ovandon],[data-odoisoat],[data-oxnvandon],[data-oerpretry]");
    if (act) {
      e.stopPropagation();
      await dhXuLyNut(act);
      return;
    }
    if (e.target.closest("details.hd-them")) {
      e.stopPropagation();
      return;
    }
    const mo = e.target.closest("[data-omo]") || e.target.closest("[data-orow]");
    if (mo) {
      const id = mo.dataset.omo || mo.dataset.orow;
      if (id) await dhTaiChiTiet(id, true);
    }
  });

  document.addEventListener("keydown", (e) => {
    const kpi = e.target.closest?.("[data-okpi]");
    if (kpi && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); kpi.click(); return; }
    if (e.key === "Tab" && dhState.openId && dhNganHep() && !hoiDangMo) {
      const focusable = $$("#orderDetail button:not([disabled]), #orderDetail a[href], #orderDetail summary")
        .filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (first && (e.shiftKey ? document.activeElement === first : document.activeElement === last)) {
        e.preventDefault(); (e.shiftKey ? last : first).focus();
      }
    }
    if (e.key !== "Escape" || !dhState.openId || hoiDangMo) return;
    if (typeof chuong !== "undefined" && chuong.mo) return;
    if (state.view !== "donhang") return;
    dhDongNgan();
  });

  window.matchMedia("(max-width: 1180px)").addEventListener?.("change", () => {
    if (dhState.openId) dhMoNgan();
  });
  document.addEventListener("click", (e) => {
    const nav = e.target.closest("button[data-view]");
    if (nav && nav.dataset.view !== "donhang" && dhState.openId) dhDongNgan();
  });
}

async function loadOrders() {
  dhGanSuKien();
  const request = ++dhState.listRequest;
  $("#orders")?.setAttribute("aria-busy", "true");
  try {
    if (VAN_CHUYEN === null) {
      try { VAN_CHUYEN = await api("/van-chuyen/cau-hinh"); }
      catch { VAN_CHUYEN = { that: false }; }
    }
    const p = new URLSearchParams({
      status: dhState.status || "all",
      q: dhState.q || "",
      channel: dhState.channel || "all",
      thanh_toan: dhState.thanh_toan || "all",
      van_chuyen: dhState.van_chuyen || "all",
      tu_ngay: dhState.tu_ngay || "",
      den_ngay: dhState.den_ngay || "",
      page: String(dhState.page || 1),
      page_size: String(dhState.pageSize || 20),
    });
    const data = await api("/orders/bang?" + p.toString());
    if (request !== dhState.listRequest) return;
    dhState.items = data.items || [];
    dhState.page = data.page || 1;
    $("#c-donhang").textContent = (data.kpi && data.kpi.cho_duyet) || "";

    const resetBtn = $("#orderReset");
    if (resetBtn) resetBtn.hidden = !dhCoLoc();
    const sum = $("#orderSummary");
    if (sum) sum.textContent = data.total ? `${data.total} đơn khớp bộ lọc` : "";

    dhVeKpi(data.kpi);
    const channels = $("#orderChannel");
    for (const channel of data.kenh_co || []) {
      if (channels && ![...channels.options].some(option => option.value === channel)) {
        channels.add(new Option(CHANNEL_LABEL[channel] || NEN_TANG_LABEL[channel] || channel, channel));
      }
    }
    dhCapNhatChip(data.dem_trang_thai);
    dhVeBang(dhState.items);
    dhVePhanTrang(data.total || 0, dhState.page, data.total_pages || 1, data.page_size || dhState.pageSize);
    dhCapNhatChieuCaoToolbar();

    /* Nếu đang mở ngăn chi tiết và người dùng không mở menu ⋯, cập nhật êm dữ liệu chi tiết. */
    if (dhState.openId && !$("#orderDetail details[open]")) {
      await dhTaiChiTiet(dhState.openId, false);
    }
  } catch (e) {
    if (request !== dhState.listRequest) return;
    $("#orders").innerHTML = `<p class="empty" role="alert">Không tải được đơn hàng: ${esc(e.message)} <button type="button" class="btn btn--sm" data-oretry>Thử lại</button></p>`;
    $("#orderPager").hidden = true;
    $("#orderSummary").textContent = "Không tải được dữ liệu";
  } finally {
    if (request === dhState.listRequest) $("#orders")?.setAttribute("aria-busy", "false");
  }
}

/* ---------------- kho hàng (2 tab: Tồn kho + Sổ biến động kho) ---------------- */

// Nhãn biến động và loại nhập kho dùng chung cho Đơn hàng và module Kho (05b-kho.js).
// hàng đã xuất / hoàn về chỉ nhập lại sau kiểm tra qua Nhập hàng hoàn.
const KHO_LY_DO = {
  ban: "xuất bán",
  huy_don: "huỷ đơn (tự hoàn)",
  hoan_hang: "nhập hàng hoàn",
  erp_tu_choi: "ERP từ chối",
  nhap: "nhập kho",
  kiem_ke: "kiểm kê",
};

const KHO_NHAP_LOAI = [
  { value: "nhap", label: "Nhập kho thông thường" },
  { value: "hoan_hang", label: "Nhập hàng hoàn từ đơn" },
];
