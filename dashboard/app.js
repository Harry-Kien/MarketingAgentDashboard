/* Trạm điều độ — logic giao diện. Không framework, không build step. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { view: "ca", convFilter: "all", orderFilter: "all", postFilter: "all", khoFilter: "all", openConv: null, nickDefault: "", timer: null };

/* ---------------- tiện ích ---------------- */

async function api(path, options = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* giữ nguyên */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function toast(message, bad = false) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("toast--bad", bad);
  el.classList.add("is-on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("is-on"), 3200);
}

const usd = (n) => (n == null ? "—" : "$" + Number(n).toFixed(4));
const pct = (n) => (n == null ? "—" : Math.round(n * 100) + "%");

function clock(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d) / 1000;
  if (diff < 60) return "vừa xong";
  if (diff < 3600) return Math.floor(diff / 60) + " phút";
  if (diff < 86400) return Math.floor(diff / 3600) + " giờ";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

const hhmm = (iso) =>
  new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/* Trạng thái -> lớp màu tín hiệu. Một chỗ duy nhất định nghĩa ánh xạ này. */
const SIGNAL = { auto: "auto", assist: "assist", escalated: "halt", closed: "plain" };
const SIGNAL_LABEL = {
  auto: "Tự xử lý", assist: "Chờ duyệt", escalated: "Đã chuyển", closed: "Đã đóng",
};

/* ---------------- điều hướng ---------------- */

$$(".rail__item").forEach((btn) =>
  btn.addEventListener("click", () => {
    state.view = btn.dataset.view;
    $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b === btn));
    $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === state.view));
    refresh();
  })
);

/* ---------------- sáng / tối ---------------- */

$("#themetoggle").addEventListener("click", () => {
  const next =
    document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
});

/* ---------------- công tắc vận hành ---------------- */

$("#killswitch").addEventListener("click", async () => {
  const off = $("#killswitch").classList.contains("is-off");
  try {
    applyRuntime(await api("/runtime", {
      method: "POST", body: JSON.stringify({ enabled: off }),
    }));
    toast(off ? "Agent đã bật lại." : "Agent đã ngắt. Mọi tin nhắn chuyển cho người.");
  } catch (e) { toast(e.message, true); }
});

$$(".modeswitch__opt").forEach((btn) =>
  btn.addEventListener("click", async () => {
    try {
      applyRuntime(await api("/runtime", {
        method: "POST", body: JSON.stringify({ mode: btn.dataset.mode }),
      }));
      toast(btn.dataset.mode === "auto"
        ? "Chuyển sang tự động. Agent gửi thẳng cho khách."
        : "Chuyển sang gợi ý. Agent soạn, bạn duyệt trước khi gửi.");
    } catch (e) { toast(e.message, true); }
  })
);

function applyRuntime(rt) {
  const sw = $("#killswitch");
  sw.classList.toggle("is-off", !rt.enabled);
  $("#killswitch-label").textContent = rt.enabled ? "Đang chạy" : "Đã ngắt";
  $$(".modeswitch__opt").forEach((b) => b.classList.toggle("is-on", b.dataset.mode === rt.mode));
}

/* ---------------- băng ca trực (signature) ---------------- */

function drawTape(tape) {
  const strip = $("#tape");
  const SLOTS = 72;
  const pad = Math.max(0, SLOTS - tape.length);
  strip.innerHTML =
    Array.from({ length: pad }, () => '<span class="tick tick--empty" style="height:6px"></span>').join("") +
    tape.map((t) => {
      const sig = SIGNAL[t.status] || "empty";
      const h = Math.min(30, 8 + (t.messages || 1) * 3);
      const title = `${t.customer || "Khách"} · ${SIGNAL_LABEL[t.status] || t.status} · ` +
                    `${t.messages} tin · ${usd(t.cost)} · ${hhmm(t.at)}`;
      return `<button type="button" class="tick tick--${sig}" style="height:${h}px" ` +
             `title="${esc(title)}" data-conv="${t.id}" aria-label="${esc(title)}"></button>`;
    }).join("");

  strip.onclick = (ev) => {
    const id = ev.target.closest("[data-conv]")?.dataset.conv;
    if (!id) return;
    state.openConv = id;
    $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === "hoithoai"));
    $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === "hoithoai"));
    state.view = "hoithoai";
    refresh();
  };

  $("#tape-now").textContent = tape.length
    ? `${tape.length} hội thoại gần nhất · mới nhất ${hhmm(tape[tape.length - 1].at)}`
    : "chưa có hội thoại nào";
}

/* ---------------- ca trực ---------------- */

function cell(label, value, unit, ratio, tone) {
  const w = ratio == null ? 0 : Math.max(2, Math.min(100, ratio * 100));
  return `<div class="readout__cell">
    <span class="readout__label">${esc(label)}</span>
    <span class="readout__line">
      <span class="readout__value">${esc(value)}</span>
      <span class="readout__unit">${esc(unit || "")}</span>
    </span>
    <span class="readout__bar"><span class="readout__fill readout__fill--${tone}" style="width:${w}%"></span></span>
  </div>`;
}

async function loadOverview() {
  const o = await api("/overview");
  applyRuntime(o.runtime);
  drawTape(o.tape);

  // Huy hiệu "Ca trực" đếm MỌI hội thoại cần người, không riêng cái chờ
  // duyệt — nếu không thì bảy hội thoại đã chuyển người nằm ngoài con số
  // và người trực tưởng ca đang êm.
  $("#c-ca").textContent =
    (o.conversations.waiting || 0) + (o.conversations.escalated || 0);
  $("#c-hoithoai").textContent = o.conversations.total || 0;
  $("#c-video").textContent = o.video.review || 0;
  $("#rail-cost").textContent = usd(o.cost.total_usd);

  $("#readout").innerHTML = [
    cell("Hội thoại 24 giờ", o.conversations.total, "cuộc", null, "auto"),
    cell("Agent tự xử lý", pct(o.conversations.containment),
         `${o.conversations.handled}/${o.conversations.total}`,
         o.conversations.containment, "auto"),
    cell("Chờ người", o.conversations.waiting, "cuộc",
         o.conversations.total ? o.conversations.waiting / o.conversations.total : 0, "assist"),
    cell("Đã chuyển người", o.conversations.escalated, "cuộc",
         o.conversations.total ? o.conversations.escalated / o.conversations.total : 0, "halt"),
    cell("Có căn cứ tài liệu", pct(o.quality.grounding), `${o.quality.replies} lượt trả lời`,
         o.quality.grounding, "auto"),
    cell("Chi phí mỗi hội thoại", usd(o.cost.per_conversation), `tổng ${usd(o.cost.total_usd)}`,
         null, "spend"),
    cell("Token đọc từ cache", o.cost.cache_read.toLocaleString("vi-VN"), "token",
         o.cost.tokens_in + o.cost.cache_read
           ? o.cost.cache_read / (o.cost.tokens_in + o.cost.cache_read) : 0, "spend"),
    cell("Video sản xuất", o.video.total, `${o.video.seconds}s · ${o.video.failed} lỗi`,
         null, "auto"),
  ].join("");

  const waiting = await api("/conversations?status=can_nguoi&limit=12");
  $("#queue").innerHTML = waiting.length
    ? waiting.map(convRow).join("")
    : '<p class="empty">Không có hội thoại nào đang chờ. Ca trực êm.</p>';
  wireConvRows("#queue");

  const vids = (await api("/videos?limit=30")).filter((v) => v.status === "pending_review");
  $("#videoqueue").innerHTML = vids.length
    ? vids.map((v) => `<div class="row">
        <span class="row__flag row__flag--assist"></span>
        <span class="row__body">
          <span class="row__title">${esc(v.title)}</span>
          <span class="row__sub">${v.duration_s ? v.duration_s.toFixed(1) + "s" : "—"} · ${esc(v.renderer || "")}</span>
        </span>
        <span class="row__side"><span class="row__time">${clock(v.created_at)}</span></span>
      </div>`).join("")
    : '<p class="empty">Không có video nào chờ duyệt.</p>';
}

/* ---------------- hội thoại ---------------- */

const CHANNEL_LABEL = {
  zalocrm: "Zalo", zalo_oa: "Zalo OA", chatwoot: "Chatwoot",
  facebook: "Facebook", instagram: "Instagram", tiktok: "TikTok",
  whatsapp: "WhatsApp", web: "Web", test: "Thử",
};

/* Chatwoot là HỘP THƯ GỘP: Facebook Messenger, Instagram DM, WhatsApp,
   chat website, email, Telegram đều đổ về cùng một kênh. Hiện huy hiệu
   "Chatwoot" là mất đúng thông tin người trực cần — khách này đến từ đâu.
   Tên lớp Chatwoot đặt có dạng "Channel::FacebookPage"; bộ đọc đã cắt phần
   "Channel::" nên ở đây chỉ còn phần đuôi. */
const NEN_TANG_LABEL = {
  facebookpage: "Facebook", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp",
  webwidget: "Web chat", email: "Email", telegram: "Telegram",
  twiliosms: "SMS", line: "LINE", api: "API",
};

/* Nền tảng nào chưa có màu riêng thì mượn màu của Chatwoot — vẫn đúng, vì
   nó đến qua Chatwoot thật. */
const NEN_TANG_MAU = {
  facebook: "facebook", instagram: "instagram", whatsapp: "whatsapp",
  "web chat": "web", email: "chatwoot", telegram: "chatwoot",
  sms: "chatwoot", line: "chatwoot", api: "chatwoot",
};

function srcBadge(ch, nenTang) {
  const goc = String(nenTang || "").toLowerCase();
  const ten = NEN_TANG_LABEL[goc];
  if (ten) {
    const mau = NEN_TANG_MAU[ten.toLowerCase()] || "chatwoot";
    // Ghi rõ đường đi khi rê chuột: người trực biết trả lời qua đâu.
    const qua = CHANNEL_LABEL[ch] || ch;
    return `<span class="src src--${esc(mau)}" title="${esc(ten)} qua ${esc(qua)}">${esc(ten)}</span>`;
  }
  const key = ch || "web";
  return `<span class="src src--${esc(key)}">${esc(CHANNEL_LABEL[key] || key)}</span>`;
}

function convRow(c) {
  const sig = SIGNAL[c.status] || "plain";
  const sub = c.typing
    ? `<span class="row__typing"><i></i><i></i><i></i> đang soạn tin…</span>`
    : `<span class="row__sub">${esc(c.last_message || "—")}</span>`;
  return `<button type="button" class="row ${state.openConv === c.id ? "is-on" : ""}" data-conv="${c.id}">
    <span class="row__flag row__flag--${sig}"></span>
    <span class="row__body">
      <span class="row__title">${esc(c.customer || "Khách")} ${srcBadge(c.channel, c.nen_tang)}</span>
      ${sub}
    </span>
    <span class="row__side">
      <span class="row__num">${usd(c.cost)}</span>
      <span class="row__time">${clock(c.updated_at)}</span>
    </span>
  </button>`;
}

function wireConvRows(scope) {
  $$(`${scope} [data-conv]`).forEach((el) =>
    el.addEventListener("click", () => {
      state.openConv = el.dataset.conv;
      state.view = "hoithoai";
      $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === "hoithoai"));
      $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === "hoithoai"));
      refresh();
    })
  );
}

$$("#convfilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.convFilter = chip.dataset.status;
    $$("#convfilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadConversations();
  })
);

async function loadConversations() {
  const list = await api("/conversations?status=" + state.convFilter);
  $("#convlist").innerHTML = list.length
    ? list.map(convRow).join("")
    : '<p class="empty">Chưa có hội thoại nào.</p>';
  wireConvRows("#convlist");
  if (state.openConv) await loadThread(state.openConv);
}

async function loadThread(id) {
  let c;
  try { c = await api("/conversations/" + id); }
  catch { $("#convdetail").innerHTML = '<p class="empty">Không tìm thấy hội thoại.</p>'; return; }

  const msgs = c.messages.map((m) => {
    const draft = m.role === "agent" && !m.delivered;
    const who = { customer: "Khách", agent: "Agent", staff: "Nhân viên" }[m.role] || m.role;
    const meta = [
      hhmm(m.at), who,
      m.confidence != null ? "tin cậy " + m.confidence.toFixed(2) : "",
      m.grounded === false ? "KHÔNG có căn cứ" : "",
      m.cost ? usd(m.cost) : "",
      m.latency_ms ? m.latency_ms + "ms" : "",
      (m.sources || []).length ? "nguồn: " + m.sources.join(", ") : "",
    ].filter(Boolean).join(" · ");

    return `<div class="msg msg--${m.role} ${draft ? "msg--draft" : ""}">
      <div class="msg__bubble">${esc(m.content)}</div>
      <div class="msg__meta">
        <span>${esc(meta)}</span>
        ${draft ? `<button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>` : ""}
      </div>
    </div>`;
  }).join("");

  const taken = c.status === "escalated";
  $("#convdetail").innerHTML = `
    <div class="convo__title">
      <span class="convo__name">${esc(c.customer || "Khách")}</span>
      <span class="tag tag--${SIGNAL[c.status] || "plain"}">${SIGNAL_LABEL[c.status] || c.status}</span>
      <span class="convo__spacer"></span>
      ${srcBadge(c.channel, c.nen_tang)}<span class="msg__meta">${usd(c.cost)}</span>
      ${NICKS.length > 1 ? `<select class="nickpin" id="nickpin" title="Nick Zalo trả lời riêng cho hội thoại này">
        <option value="">nick mặc định${nickTen(state.nickDefault) ? " (" + esc(nickTen(state.nickDefault)) + ")" : ""}</option>
        ${NICKS.map((n) => `<option value="${esc(n.id)}"${n.id === c.zalo_account_id ? " selected" : ""}${n.san_sang ? "" : " disabled"}>${esc(n.ten)}</option>`).join("")}
      </select>` : ""}
      <button type="button" class="btn btn--sm ${taken ? "" : "btn--halt"}" id="btn-take">
        ${taken ? "Trả lại cho agent" : "Tôi tiếp quản"}
      </button>
    </div>
    <div class="thread" id="thread">${msgs || '<p class="empty">Chưa có tin nhắn.</p>'}
      ${c.typing ? '<div class="msg msg--agent"><div class="typing"><i></i><i></i><i></i></div></div>' : ""}
    </div>
    <form class="convo__bar" id="replyform">
      <textarea name="text" placeholder="Nhắn trực tiếp cho khách…" required></textarea>
      <button type="submit" class="btn btn--primary">Gửi</button>
    </form>`;

  const thread = $("#thread");
  if (thread) thread.scrollTop = thread.scrollHeight;

  $$("[data-approve]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        const r = await api("/messages/" + b.dataset.approve + "/approve", { method: "POST" });
        toast(r.ok ? "Đã gửi cho khách." : "Không gửi được: " + r.detail, !r.ok);
        refresh();
      } catch (e) { toast(e.message, true); }
    })
  );

  const pin = $("#nickpin");
  if (pin) pin.addEventListener("change", async () => {
    try {
      await api("/conversations/" + id + "/account", { method: "POST",
        body: JSON.stringify({ zalo_account_id: pin.value }) });
      toast(pin.value ? "Đã ghim nick cho hội thoại này." : "Đã bỏ ghim, dùng nick mặc định.");
    } catch (e) { toast(e.message, true); }
  });

  $("#btn-take").addEventListener("click", async () => {
    try {
      await api(`/conversations/${id}/${taken ? "release" : "takeover"}`, { method: "POST" });
      toast(taken ? "Đã trả hội thoại về cho agent." : "Bạn đang giữ hội thoại này.");
      refresh();
    } catch (e) { toast(e.message, true); }
  });

  $("#replyform").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = new FormData(ev.target).get("text").trim();
    if (!text) return;
    try {
      const r = await api(`/conversations/${id}/send`, {
        method: "POST", body: JSON.stringify({ text }),
      });
      toast(r.ok ? "Đã gửi." : "Không gửi được: " + r.detail, !r.ok);
      ev.target.reset();
      refresh();
    } catch (e) { toast(e.message, true); }
  });
}


/* ---------------- đơn hàng ---------------- */

const ORDER_LABEL = { cho_duyet: "Chờ duyệt", da_chot: "Đã chốt", da_huy: "Đã huỷ" };
const ORDER_TONE  = { cho_duyet: "duyet", da_chot: "chot", da_huy: "huy" };
const vnd = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

$$("#orderfilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.orderFilter = chip.dataset.ostatus;
    $$("#orderfilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadOrders();
  })
);

async function loadOrders() {
  const list = await api("/orders?status=" + (state.orderFilter || "all"));
  const cho = list.filter((o) => o.trang_thai === "cho_duyet").length;
  $("#c-donhang").textContent = cho || "";

  $("#orders").innerHTML = list.length ? list.map((o) => {
    const items = (Array.isArray(o.items) ? o.items : [])
      .map((i) => `<span class="order__line">${esc(i.ten)} &times;${i.so_luong} — ${vnd(i.thanh_tien)}</span>`)
      .join("");
    const cho_duyet = o.trang_thai === "cho_duyet";
    return `<div class="row">
      <span class="row__flag row__flag--${cho_duyet ? "assist" : o.trang_thai === "da_huy" ? "halt" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(o.ma_don)} · ${esc(o.khach_ten)}
          <span class="tag tag--${ORDER_TONE[o.trang_thai] || "plain"}">${ORDER_LABEL[o.trang_thai] || o.trang_thai}</span>
          ${srcBadge(o.channel, o.nen_tang)}</span>
        <span class="order__items">${items}</span>
        <span class="order__ship">${esc(o.khach_sdt)} · ${esc(o.khach_dia_chi)}</span>
      </span>
      <span class="row__side">
        <span class="order__total">${vnd(o.tong_tien)}</span>
        <span class="row__time">${clock(o.created_at)}</span>
        ${cho_duyet ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--go" data-oapprove="${o.id}">Duyệt</button>
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ</button>
          </span>` : ""}
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có đơn hàng nào.</p>';

  $$("[data-oapprove]").forEach((b) => b.addEventListener("click", async () => {
    await api("/orders/" + b.dataset.oapprove + "/approve", { method: "POST" });
    toast("Đã duyệt đơn."); loadOrders();
  }));
  $$("[data-ocancel]").forEach((b) => b.addEventListener("click", async () => {
    await api("/orders/" + b.dataset.ocancel + "/cancel", { method: "POST" });
    toast("Đã huỷ đơn."); loadOrders();
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

async function loadKho() {
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
    return `<div class="row">
      <span class="row__flag row__flag--${tone}"></span>
      <span class="row__body">
        <span class="row__title">${esc(x.ma)} · ${esc(x.ten)}
          ${x.so_luong === 0 ? '<span class="tag tag--huy">Hết hàng</span>'
            : x.sap_het ? '<span class="tag tag--duyet">Sắp hết</span>' : ""}</span>
        <span class="row__sub">${esc(x.loai)} · ${vnd(x.gia)}</span>
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
    const sl = prompt(`Nhập thêm bao nhiêu cho ${b.dataset.knhap}?`, "50");
    if (!sl) return;
    const ghi_chu = prompt("Ghi chú (số lô, nhà cung cấp…):", "") || "";
    try {
      const r = await api(`/kho/${encodeURIComponent(b.dataset.knhap)}/nhap`, {
        method: "POST",
        body: JSON.stringify({ so_luong: parseInt(sl, 10), ghi_chu }),
      });
      toast(`${r.ma}: tồn mới ${r.ton_moi}`);
      loadKho();
    } catch (e) { toast(e.message, true); }
  }));

  // Kiểm kê bắt buộc có lý do — kho LUÔN lệch, và không ghi vì sao thì
  // sau này không ai truy được lệch từ đâu.
  $$("[data-kkiemke]").forEach((b) => b.addEventListener("click", async () => {
    const moi = prompt(
      `Đếm thực tế được bao nhiêu? (hệ thống đang ghi ${b.dataset.kton})`,
      b.dataset.kton);
    if (moi === null) return;
    const ly_do = prompt("Lý do lệch (bắt buộc): vỡ, mất, đếm sai…", "");
    if (!ly_do) { toast("Kiểm kê bắt buộc có lý do.", true); return; }
    try {
      const r = await api(`/kho/${encodeURIComponent(b.dataset.kkiemke)}/kiem-ke`, {
        method: "POST",
        body: JSON.stringify({ so_luong_moi: parseInt(moi, 10), ly_do }),
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

/* ---------------- video ---------------- */

const VIDEO_STATUS = {
  queued: "Đang xếp hàng", claimed: "Đã nhận việc",
  looking: "Đang xem ảnh sản phẩm",
  scripting: "Đang viết kịch bản", voicing: "Đang thu giọng",
  rendering: "Đang dựng hình", pending_review: "Chờ duyệt", ready: "Đã duyệt", failed: "Lỗi",
};

async function loadVideos() {
  const list = await api("/videos");
  $("#videos").innerHTML = list.length ? list.map((v) => {
    const done = v.has_file;
    const tone = v.status === "failed" ? "halt" : v.status === "ready" ? "auto" : "assist";
    const scenes = Array.isArray(v.scenes) ? v.scenes.length : 0;
    const measured = Array.isArray(v.scenes)
      && v.scenes.some((s) => s.timing_source === "ffprobe");
    return `<article class="card">
      <div class="card__media">
        ${done
          ? `<video controls preload="metadata" src="/api/videos/${v.id}/file"></video>`
          : `<div class="card__pending">${esc(VIDEO_STATUS[v.status] || v.status)}${
              v.error ? "<br><br>" + esc(v.error.slice(0, 160)) : ""}</div>`}
      </div>
      <div class="card__body">
        <span class="card__title">${esc(v.title)}</span>
        <span class="gallery__meta">
          <span class="tag tag--${tone}">${esc(VIDEO_STATUS[v.status] || v.status)}</span>
          <span>${v.duration_s ? v.duration_s.toFixed(1) + "s" : "—"}</span>
          <span>${scenes} cảnh</span>
          <span>${esc(v.renderer || "—")}</span>
          <span>${measured ? "khớp giọng đọc" : "thời lượng ước lượng"}</span>
          <span>${usd(v.cost)}</span>
        </span>
      </div>
      ${v.status === "pending_review"
        ? `<div class="card__actions"><button type="button" class="btn btn--sm btn--go" data-vapprove="${v.id}">Duyệt</button></div>`
        : v.status === "failed"
        ? `<div class="card__actions"><button type="button" class="btn btn--sm" data-vretry="${v.id}">Chạy lại</button></div>`
        : ""}
    </article>`;
  }).join("") : '<p class="empty">Chưa có video nào. Đặt một cái ở khung phía trên.</p>';

  $$("[data-vapprove]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/videos/" + b.dataset.vapprove + "/approve", { method: "POST" });
      toast("Đã duyệt video.");
      loadVideos();
    })
  );

  $$("[data-vretry]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api("/videos/" + b.dataset.vretry + "/retry", { method: "POST" });
        toast("Đã đưa lại vào hàng đợi. Ảnh sản phẩm giữ nguyên, không cần tải lại.");
        loadVideos();
      } catch (e) { toast(e.message, true); }
    })
  );
}

/* Nạp danh mục vào ô chọn sản phẩm. Ghi rõ sản phẩm nào có ảnh trong kho —
   chọn phải mã không có ảnh thì video ra thẻ chữ, biết trước vẫn hơn. */
async function fillProductPicker() {
  const sel = $("#videoproduct");
  if (!sel || sel.dataset.loaded) return;
  try {
    const { san_pham } = await api("/catalog/products");
    sel.insertAdjacentHTML("beforeend", san_pham.map((p) =>
      `<option value="${esc(p.ma)}">${esc(p.ma)} — ${esc(p.ten)}` +
      `${p.so_anh ? ` (${p.so_anh} ảnh)` : " (chưa có ảnh)"}</option>`
    ).join(""));
    sel.dataset.loaded = "1";
  } catch { /* không có danh mục thì để ô rỗng, form vẫn dùng được */ }
}

/* Xem trước ảnh trước khi gửi — thấy mình chọn nhầm ảnh nào thì đổi ngay,
   thay vì phát hiện sau khi đã dựng xong mất mấy phút. */
$("#videoimages")?.addEventListener("change", (ev) => {
  const files = [...(ev.target.files || [])].slice(0, 8);
  $("#imgpreview").innerHTML = files
    .map((f) => `<img class="thumb" alt="${f.name}" src="${URL.createObjectURL(f)}">`)
    .join("");
  if ((ev.target.files || []).length > 8) toast("Chỉ nhận 8 ảnh đầu tiên.");
});

$("#videoform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const files = [...($("#videoimages")?.files || [])].slice(0, 8);

  try {
    if (files.length) {
      /* Có ảnh -> đường multipart. Không dùng api() vì hàm đó đặt sẵn
         Content-Type JSON; multipart phải để trình duyệt tự đặt boundary. */
      const body = new FormData();
      body.append("title", f.get("title"));
      body.append("brief", f.get("brief"));
      body.append("kind", f.get("kind"));
      files.forEach((file) => body.append("images", file));

      const r = await fetch("/api/videos/upload", { method: "POST", body });
      if (!r.ok) throw new Error((await r.text()).slice(0, 200));
      const out = await r.json();
      toast(`Đã nhận ${out.so_anh_nhan} ảnh. Agent đang xem ảnh trước khi viết kịch bản.`);
    } else {
      const out = await api("/videos", {
        method: "POST",
        body: JSON.stringify({
          title: f.get("title"), brief: f.get("brief"), kind: f.get("kind"),
          ma_san_pham: f.get("ma_san_pham") || "",
        }),
      });
      toast(out.so_anh_kho
        ? `Đã nhận, dùng ${out.so_anh_kho} ảnh trong kho. Agent đang xem ảnh trước khi viết kịch bản.`
        : "Đã nhận. Không gắn sản phẩm nên video sẽ là thẻ chữ, không có ảnh.");
    }
    ev.target.reset();
    $("#imgpreview").innerHTML = "";
    loadVideos();
  } catch (e) { toast(e.message, true); }
});

/* ---------------- khách đến từ đâu ---------------- */

/* Câu hỏi cơ bản nhất của người vận hành mà bảng cũ không trả lời được:
   khách của mình đến từ kênh nào, kênh nào agent tự lo được, kênh nào phải
   gọi người liên tục. Kênh có tỷ lệ chuyển người cao không phải kênh tệ —
   thường là kênh có loại câu hỏi khác hẳn, và đó là chỗ cần bổ sung tài liệu. */
const KENH_TEN = {
  zalocrm: "Zalo", chatwoot: "Chatwoot", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp", web: "Website", email: "Email",
};

async function loadAnalyticsKhach() {
  let d;
  try { d = await api("/analytics/khach"); } catch { return; }

  $("#anaKhachTong").innerHTML = [
    cell("Tổng hội thoại", d.tong.hoi_thoai, "cuộc", null, "auto"),
    cell("Khách khác nhau", d.tong.khach, "người", null, "auto"),
    cell("Số kênh đang có khách", d.tong.so_kenh, "kênh", null, "auto"),
    cell("Chi phí 30 ngày", usd(d.tong.chi_phi), "tổng", null, "spend"),
  ].join("");

  $("#anaKhach").innerHTML = d.kenh.length ? d.kenh.map((k) => {
    /* Màu theo tỷ lệ tự xử lý: đây là con số nói lên agent đang gánh được
       bao nhiêu, và nó là lý do tồn tại của cả hệ thống. */
    const tone = k.ty_le_tu_xu_ly >= 0.6 ? "auto"
               : k.ty_le_tu_xu_ly >= 0.3 ? "assist" : "halt";
    return `<div class="row">
      <span class="row__flag row__flag--${tone}"></span>
      <div class="row__main">
        <b>${esc(NEN_TANG_LABEL[String(k.nen_tang || "").toLowerCase()]
                  || KENH_TEN[k.nen_tang] || KENH_TEN[k.kenh] || k.nen_tang || k.kenh)}</b>
        ${k.nen_tang && k.nen_tang !== k.kenh
          ? `<span class="row__sub">qua ${esc(KENH_TEN[k.kenh] || k.kenh)}</span>` : ""}
        <span class="row__sub">${k.hoi_thoai} hội thoại · ${k.khach} khách · ${k.tin} tin
          · tự xử lý ${pct(k.ty_le_tu_xu_ly)} · chuyển người ${pct(k.ty_le_chuyen_nguoi)}
          ${k.co_can_cu != null ? "· có căn cứ " + pct(k.co_can_cu) : ""}
          ${k.tre_tb_ms ? "· trễ " + (k.tre_tb_ms / 1000).toFixed(1) + "s" : ""}</span>
      </div>
      <span class="row__num">${usd(k.chi_phi_moi_hoi_thoai)}<br>
        <span class="row__time">mỗi hội thoại</span></span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có hội thoại nào trong 30 ngày.</p>';
}

/* ---------------- các hệ thống đang chạy ---------------- */

/* Một CỔNG VÀO để nhớ, không phải một tiến trình để chạy. ZaloCRM và
   Chatwoot dùng đường dẫn tuyệt đối nên không proxy dưới tiền tố được mà
   không viết lại HTML/CSS/JS đang bay qua — xem agent/he_thong.py. */
async function loadHeThong() {
  const box = $("#hethong");
  const btn = $("#hethongrun");
  if (btn) btn.disabled = true;
  box.innerHTML = '<p class="empty">Đang hỏi từng dịch vụ…</p>';
  try {
    const d = await api("/he-thong");
    $("#c-hethong").textContent = `${d.dang_chay}/${d.tong}`;
    box.innerHTML = d.dich_vu.map((x) => `<div class="row">
        <span class="row__flag row__flag--${x.song ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(x.ten)}${x.chinh ? " · trang bạn đang xem" : ""}</b>
          <span class="row__sub">${esc(x.mo_ta)}
            ${x.can_dang_nhap ? "· cần đăng nhập riêng" : ""}</span>
        </div>
        ${x.song
          ? `<a class="btn btn--sm" href="${esc(x.url)}" target="_blank" rel="noopener">Mở</a>`
          : `<span class="tag tag--halt">không chạy</span>`}
      </div>`).join("");
    $("#hethongvisao").textContent = d.vi_sao_tach;
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

$("#hethongrun")?.addEventListener("click", loadHeThong);

/* ---------------- sức khoẻ hệ thống ---------------- */

/* KHÔNG tự chạy khi mở trang: phép kiểm gọi model thật và mất vài giây.
   Người vận hành bấm khi cần, không phải mỗi lần liếc qua dashboard. */
const HEALTH_TONE = { tot: "auto", canh_bao: "assist", hong: "halt" };
const HEALTH_LABEL = { tot: "Tốt", canh_bao: "Cảnh báo", hong: "Hỏng" };

$("#healthrun")?.addEventListener("click", async () => {
  const box = $("#health");
  const btn = $("#healthrun");
  btn.disabled = true;
  box.innerHTML = '<p class="empty">Đang gọi thật từng dịch vụ…</p>';
  try {
    const d = await api("/suc-khoe");
    box.innerHTML =
      `<div class="row"><span class="row__flag row__flag--${HEALTH_TONE[d.trang_thai]}"></span>
         <div class="row__main"><b>Tổng thể: ${HEALTH_LABEL[d.trang_thai] || d.trang_thai}</b>
         <span class="row__sub">kiểm trong ${d.kiem_trong_ms} ms · agent ${d.agent?.enabled ? "đang chạy" : "đã ngắt"} · chế độ ${esc(d.agent?.mode || "?")}</span></div></div>` +
      d.muc.map((m) => `<div class="row">
         <span class="row__flag row__flag--${HEALTH_TONE[m.trang_thai] || "plain"}"></span>
         <div class="row__main"><b>${esc(m.ten)}</b>
         <span class="row__sub">${esc(m.ghi_chu)}</span></div>
         <span class="tag tag--${HEALTH_TONE[m.trang_thai] || "plain"}">${HEALTH_LABEL[m.trang_thai] || m.trang_thai}</span>
       </div>`).join("");
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
});

/* ---------------- tri thức ---------------- */

async function loadDocs() {
  const docs = await api("/knowledge");
  $("#c-trithuc").textContent = docs.length;
  $("#docs").innerHTML = docs.length ? docs.map((d) => `<div class="row">
      <span class="row__flag row__flag--auto"></span>
      <span class="row__body">
        <span class="row__title">${esc(d.title)}</span>
        <span class="row__sub">${d.chunks} đoạn · nguồn ${esc(d.source)}</span>
      </span>
      <span class="row__side">
        <button type="button" class="btn btn--sm btn--halt" data-doc="${d.id}">Xoá</button>
        <span class="row__time">${clock(d.created_at)}</span>
      </span>
    </div>`).join("")
    : '<p class="empty">Chưa nạp tài liệu nào. Agent sẽ không có căn cứ để trả lời.</p>';

  $$("[data-doc]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api("/knowledge/" + b.dataset.doc, { method: "DELETE" });
      toast("Đã xoá tài liệu.");
      loadDocs();
    })
  );
}

$("#docform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  toast("Đang tạo embedding…");
  try {
    const r = await api("/knowledge", {
      method: "POST",
      body: JSON.stringify({ title: f.get("title"), text: f.get("text") }),
    });
    toast(`Đã nạp ${r.chunks} đoạn.`);
    ev.target.reset();
    loadDocs();
  } catch (e) { toast(e.message, true); }
});

$("#probeform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = new FormData(ev.target).get("question");
  try {
    const r = await api("/knowledge/probe", {
      method: "POST", body: JSON.stringify({ question: q }),
    });
    $("#probe").innerHTML = r.hits.length ? r.hits.map((h) => `<div class="row">
        <span class="row__flag row__flag--spend"></span>
        <span class="row__body">
          <span class="row__title">${esc(h.doc)}</span>
          <span class="row__sub">${esc(h.excerpt)}</span>
        </span>
        <span class="row__side"><span class="probe__score">${h.score.toFixed(3)}</span></span>
      </div>`).join("")
      : '<p class="empty">Không tìm thấy đoạn nào đủ khớp. Agent sẽ chuyển câu này cho người.</p>';
  } catch (e) { toast(e.message, true); }
});

/* ---------------- nhật ký ---------------- */

async function loadEvents() {
  const evs = await api("/events");
  $("#events").innerHTML = evs.length ? evs.map((e) => {
    const tone = e.kind.includes("error") || e.kind.includes("failed") ? "halt"
      : e.kind.includes("escalat") ? "assist" : "auto";
    return `<div class="row">
      <span class="row__flag row__flag--${tone}"></span>
      <span class="row__body">
        <span class="row__title">${esc(e.kind)}</span>
        <span class="row__sub">${esc(JSON.stringify(e.detail))}</span>
      </span>
      <span class="row__side">
        <span class="row__num">${esc(e.actor)}</span>
        <span class="row__time">${clock(e.at)}</span>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có sự kiện nào.</p>';
}


/* ---------------- nick Zalo ---------------- */

// Doanh nghiệp chạy nhiều nick. Nick mặc định áp cho hội thoại chưa ghim
// riêng; ghim riêng thắng, vì khách phải nhận trả lời từ đúng nick họ nhắn vào.
let NICKS = [];

function nickTen(id) {
  const n = NICKS.find((x) => x.id === id);
  return n ? n.ten : "";
}

async function loadChannelStrip() {
  const { channels } = await api("/channels");
  // Nói rõ kênh nào đẩy, kênh nào kéo. Hai cơ chế ngược nhau chạy song song
  // là điểm dễ gây hiểu nhầm nhất khi vận hành.
  $("#chanstrip").innerHTML = channels.map((c) =>
    `<span class="src src--${esc(c.ten)}" style="${c.dang_bat ? "" : "opacity:.45"}"
       title="${esc(c.co_che === "polling" ? "kéo tin mỗi vài giây" : "nhận webhook tức thì")}${c.dang_bat ? "" : " — chưa cấu hình"}">${esc(CHANNEL_LABEL[c.ten] || c.ten)} · ${esc(c.co_che)}</span>`
  ).join("");
}

async function loadNicks() {
  const r = await api("/zalo/accounts");
  NICKS = r.accounts;
  state.nickDefault = r.dang_chon;
  const opts = NICKS.map((n) =>
    `<option value="${esc(n.id)}"${n.id === r.dang_chon ? " selected" : ""}${n.san_sang ? "" : " disabled"}>`
    + `${esc(n.ten)}${n.sdt ? " · " + esc(n.sdt) : ""}${n.san_sang ? "" : " (mất kết nối)"}</option>`
  ).join("");
  $("#nickdefault").innerHTML = NICKS.length
    ? opts : '<option value="">— chưa có nick nào —</option>';
  $("#nickhint").textContent = r.ghi_chu
    || (NICKS.length > 1 ? "Ghim nick riêng cho từng hội thoại ở khung bên phải." : "");
}

$("#nickdefault").addEventListener("change", async (e) => {
  try {
    await api("/zalo/account", { method: "POST",
      body: JSON.stringify({ zalo_account_id: e.target.value }) });
    toast("Đã đổi nick trả lời mặc định.");
  } catch (err) { toast(err.message, true); loadNicks(); }
});

/* ---------------- đăng bài ---------------- */

const POST_LABEL = {
  cho_duyet: "Chờ duyệt", da_len_lich: "Đã hẹn giờ", dang_dang: "Đang đăng",
  da_dang: "Đã đăng", loi: "Lỗi", da_huy: "Đã huỷ", nhap: "Nháp",
};
const POST_TONE = {
  cho_duyet: "duyet", da_len_lich: "duyet", dang_dang: "duyet",
  da_dang: "chot", loi: "huy", da_huy: "huy",
};
const KENH_LABEL = {
  facebook: "Facebook", instagram: "Instagram",
  tiktok: "TikTok", youtube: "YouTube",
};
const num = (n) => Number(n || 0).toLocaleString("vi-VN");

$$("#postfilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.postFilter = chip.dataset.pstatus;
    $$("#postfilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadPosts();
  })
);

async function loadPubChannels() {
  const { kenh } = await api("/publish/channels");
  $("#pubchannels").innerHTML = kenh.map((k) => {
    const steps = k.duong_di.map((d) =>
      `<span class="lane__step lane__step--${d.san_sang ? "on" : "off"}">${esc(d.adapter)}</span>`
    ).join('<span class="lane__step" style="border:0;padding:0">&rarr;</span>');
    const chan = k.duong_di.filter((d) => !d.san_sang && d.ly_do);
    return `<div class="row">
      <span class="row__flag row__flag--${k.dang_dung === "manual" ? "assist" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(KENH_LABEL[k.kenh] || k.kenh)}</span>
        <span class="lane">${steps}</span>
        ${chan.map((d) => `<span class="lane__why">${esc(d.adapter)}: ${esc(d.ly_do)}</span>`).join("")}
      </span>
      <span class="row__side"><span class="row__num">${esc(k.dang_dung || "—")}</span></span>
    </div>`;
  }).join("");
}

async function fillPostPickers() {
  if (fillPostPickers.done) return;
  fillPostPickers.done = true;
  const [{ san_pham }, videos] = await Promise.all([
    api("/catalog/products"), api("/videos"),
  ]);
  $("#sanphamlist").innerHTML = san_pham
    .map((p) => `<option value="${esc(p.ma)}">${esc(p.ten)}</option>`).join("");
  const dung_duoc = videos.filter((v) => v.status === "ready" || v.status === "pending_review");
  const opts = '<option value="">— không gắn video —</option>'
    + dung_duoc.map((v) => `<option value="${esc(v.id)}">${esc(v.title)}</option>`).join("");
  $("#postvideo").innerHTML = opts;
  const cv = $("#campaignvideo");
  if (cv) cv.innerHTML = opts;
}

function drawDraft(d) {
  const tags = (d.hashtags || []).join(" ");
  const canhbao = d.so_lan_thu > 1
    ? `<span class="tag tag--duyet">Đã sửa ${d.so_lan_thu - 1} lần cho đúng luật quảng cáo</span>` : "";
  $("#postdraft").innerHTML = `<div class="draft__box">
    <div class="draft__title">${esc(d.tieu_de || "(không tiêu đề)")} ${canhbao}</div>
    <div class="draft__text">${esc(d.noi_dung)}</div>
    <div class="draft__tags">${esc(tags)}</div>
    <div class="draft__foot">
      <button type="button" class="btn btn--primary btn--sm" id="draftsave">Đưa vào hàng đợi</button>
      <input type="datetime-local" id="draftwhen" class="draft__sched" title="Để trống là đăng ngay sau khi duyệt">
      <button type="button" class="btn btn--sm" id="draftredo">Soạn lại</button>
      <span class="draft__meta">${esc(KENH_LABEL[d.kenh] || d.kenh)} · ${usd(d.chi_phi_usd)}</span>
    </div>
  </div>`;

  $("#draftsave").addEventListener("click", async () => {
    const when = $("#draftwhen").value;
    await api("/posts", { method: "POST", body: JSON.stringify({
      tieu_de: d.tieu_de, noi_dung: d.noi_dung, hashtags: d.hashtags,
      kenh: [d.kenh], video_id: d.video_id || null,
      lich_dang: when ? new Date(when).toISOString() : null,
    })});
    $("#postdraft").innerHTML = "";
    toast("Đã vào hàng đợi. Bấm Duyệt thì bài mới đi.");
    loadPosts();
  });
  $("#draftredo").addEventListener("click", () => $("#postform").requestSubmit());
}

$("#postform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  const f = Object.fromEntries(new FormData(e.target));
  btn.disabled = true; btn.textContent = "Agent đang viết…";
  try {
    drawDraft(await api("/posts/draft", { method: "POST", body: JSON.stringify({
      kenh: f.kenh, san_pham: f.san_pham || "", y_tuong: f.y_tuong || "",
      video_id: f.video_id || null,
    })}));
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Agent soạn bài";
  }
});

async function loadPosts() {
  const q = state.postFilter && state.postFilter !== "all"
    ? "?trang_thai=" + state.postFilter : "";
  const { posts } = await api("/posts" + q);
  const cho = posts.filter((p) => p.trang_thai === "cho_duyet").length;
  $("#c-dangbai").textContent = cho || "";

  const cho_duyet_n = posts.filter((p) => p.trang_thai === "cho_duyet").length;
  const thanh = $("#postbulk");
  if (thanh) {
    thanh.innerHTML = cho_duyet_n > 1
      ? `<button type="button" class="btn btn--sm btn--go" id="bulkapprove">Duyệt cả ${cho_duyet_n} bài</button>`
      : "";
    const bulk = $("#bulkapprove");
    if (bulk) bulk.addEventListener("click", async () => {
      bulk.disabled = true;
      const r = await api("/posts/approve-all", { method: "POST" });
      toast(r.bi_chan
        ? `Duyệt ${r.da_duyet} bài, ${r.bi_chan} bài bị chặn vì vi phạm quảng cáo.`
        : `Đã duyệt ${r.da_duyet} bài.`, !!r.bi_chan);
      loadPosts();
    });
  }

  $("#posts").innerHTML = posts.length ? posts.map((p) => {
    const kenhs = (p.kenh || []).map((k) =>
      `<span class="tag tag--plain">${esc(KENH_LABEL[k] || k)}</span>`).join(" ");
    const kq = p.ket_qua || {};
    const links = Object.entries(kq).map(([k, v]) => v.url
      ? `<a class="post__link" href="${esc(v.url)}" target="_blank" rel="noopener">${esc(k)} &#8599;</a>`
      : v.detail ? `<span class="post__link" style="color:hsl(var(--muted-foreground))">${esc(k)}: ${esc(v.detail)}</span>` : ""
    ).join("");
    const cho_duyet = p.trang_thai === "cho_duyet";
    const dang_roi = p.trang_thai === "da_dang" || p.trang_thai === "dang_dang";
    return `<div class="row">
      <span class="row__flag row__flag--${cho_duyet ? "assist" : p.trang_thai === "loi" ? "halt" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(p.tieu_de || "(không tiêu đề)")}
          <span class="tag tag--${POST_TONE[p.trang_thai] || "plain"}">${POST_LABEL[p.trang_thai] || p.trang_thai}</span>
          ${kenhs}${p.co_video ? '<span class="tag tag--plain">có video</span>' : ""}</span>
        <span class="post__body">${esc(p.noi_dung)}</span>
        <span class="post__links">${links}</span>
      </span>
      <span class="row__side">
        <span class="row__time">${p.lich_dang ? "hẹn " + clock(p.lich_dang) : clock(p.created_at)}</span>
        <span style="display:flex;gap:6px;margin-top:4px">
          ${cho_duyet ? `<button type="button" class="btn btn--sm btn--go" data-papprove="${p.id}">Duyệt &amp; đăng</button>` : ""}
          ${!dang_roi && p.trang_thai !== "da_huy" ? `<button type="button" class="btn btn--sm btn--halt" data-pcancel="${p.id}">Huỷ</button>` : ""}
          <button type="button" class="btn btn--sm" data-pkit="${p.id}">Bộ đăng tay</button>
          ${dang_roi ? `<button type="button" class="btn btn--sm" data-pmetric="${p.id}" data-pkenh="${esc((p.kenh || [])[0] || "")}">Nhập số liệu</button>` : ""}
        </span>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có bài đăng nào.</p>';

  $$("[data-papprove]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await api("/posts/" + b.dataset.papprove + "/approve", { method: "POST" });
      toast(r.trang_thai === "da_len_lich" ? "Đã xếp lịch." : "Đã gửi đi.");
    } catch (e) { toast(e.message, true); }
    loadPosts();
  }));
  $$("[data-pkit]").forEach((b) => b.addEventListener("click", () =>
    moKit(b.dataset.pkit, b.closest(".row"))));
  $$("[data-pcancel]").forEach((b) => b.addEventListener("click", async () => {
    await api("/posts/" + b.dataset.pcancel + "/cancel", { method: "POST" });
    toast("Đã huỷ bài."); loadPosts();
  }));
  // Chưa có quyền Insights API -> nhập tay. Cùng một bảng, cùng một biểu đồ.
  $$("[data-pmetric]").forEach((b) => b.addEventListener("click", async () => {
    const v = prompt("Nhập: lượt xem, lượt thích, bình luận, chia sẻ\n(ngăn cách bằng dấu phẩy)", "0,0,0,0");
    if (!v) return;
    const [x = 0, t = 0, bl = 0, cs = 0] = v.split(",").map((n) => parseInt(n.trim(), 10) || 0);
    await api("/posts/" + b.dataset.pmetric + "/metrics", { method: "POST", body: JSON.stringify({
      kenh: b.dataset.pkenh, luot_xem: x, luot_thich: t, binh_luan: bl, chia_se: cs,
    })});
    toast("Đã ghi số liệu."); loadAnalytics();
  }));
}

/* ---------------- chiến dịch đa nền tảng ---------------- */

// Không copy-paste một caption ra bốn chỗ: mỗi nền tảng được soạn riêng.
// Xem agent/publish/chien_dich.py để biết vì sao.
$("#campaignform").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const btn = form.querySelector('button[type="submit"]');
  const kenh = $$('#campaignkenh input:checked').map((i) => i.value);
  if (!kenh.length) { toast("Chọn ít nhất một nền tảng.", true); return; }

  const f = Object.fromEntries(new FormData(form));
  btn.disabled = true; btn.textContent = `Đang soạn ${kenh.length} bài…`;
  $("#campaignout").innerHTML = "";
  try {
    const r = await api("/campaigns", { method: "POST", body: JSON.stringify({
      ten: f.ten, kenh, san_pham: f.san_pham || "", y_tuong: f.y_tuong || "",
      video_id: f.video_id || null,
      gian_cach_phut: parseInt(f.gian_cach_phut, 10) || 0,
    })});
    drawCampaign(r);
    toast(`${r.so_bai} bài đã vào hàng chờ duyệt.`);
    loadPosts();
  } catch (err) {
    toast(err.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "Agent soạn cả chiến dịch";
  }
});

function drawCampaign(r) {
  const bai = r.bai.map((b) => `
    <div class="draft__box" style="margin-bottom:10px">
      <div class="draft__title">${esc(KENH_LABEL[b.kenh[0]] || b.kenh[0])}
        <span class="tag tag--duyet">Chờ duyệt</span>
        ${b.so_lan_thu > 1 ? `<span class="tag tag--plain">sửa ${b.so_lan_thu - 1} lần cho đúng luật</span>` : ""}
      </div>
      <div class="draft__text">${esc(b.noi_dung)}</div>
      <div class="draft__tags">${esc((b.hashtags || []).join(" "))}</div>
    </div>`).join("");
  const hong = r.kenh_hong.length
    ? `<p class="lane__why">Soạn hỏng: ${r.kenh_hong.map((h) => `${esc(h.kenh)} — ${esc(h.ly_do)}`).join("; ")}</p>`
    : "";
  $("#campaignout").innerHTML =
    `<p class="kit__note">${esc(r.ghi_chu)} · ${usd(r.chi_phi_usd)}</p>${bai}${hong}`;
}

/* ---------------- bộ đăng thủ công ---------------- */

// Chừng nào Facebook và TikTok chưa duyệt quyền, đây là con đường DUY NHẤT
// nội dung ra được cả bốn nền tảng. Làm cho nó nhanh còn hơn ngồi chờ.
async function moKit(id, o) {
  const cu = document.getElementById("kit-" + id);
  if (cu) { cu.remove(); return; }
  const k = await api(`/posts/${id}/kit`);
  const luuy = Object.entries(k.luu_y || {})
    .map(([kenh, t]) => `<div>${esc(KENH_LABEL[kenh] || kenh)}: ${esc(t)}</div>`).join("");
  const box = document.createElement("div");
  box.id = "kit-" + id;
  box.className = "kit";
  box.innerHTML = `
    <div class="kit__cap" id="cap-${id}">${esc(k.caption)}</div>
    <div class="kit__note">${luuy}</div>
    <div class="kit__row">
      <button type="button" class="btn btn--sm" data-copy="${id}">Chép caption</button>
      ${k.co_video ? `<a class="btn btn--sm" href="/api${k.video_url.replace('/api','')}" download>Tải video</a>` : ""}
      <button type="button" class="btn btn--sm btn--go" data-posted="${id}"
        data-kenh="${esc((k.kenh || [])[0] || "")}">Đã đăng xong</button>
    </div>`;
  o.after(box);

  box.querySelector("[data-copy]").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(k.caption);
      toast("Đã chép caption.");
    } catch { toast("Trình duyệt chặn chép tự động — bôi đen rồi Ctrl+C.", true); }
  });
  box.querySelector("[data-posted]").addEventListener("click", async () => {
    const url = prompt("Dán link bài vừa đăng (để đo hiệu quả sau này):", "");
    if (url === null) return;
    await api(`/posts/${id}/mark-posted`, { method: "POST", body: JSON.stringify({
      kenh: box.querySelector("[data-posted]").dataset.kenh, ok: true, url,
    })});
    toast("Đã ghi nhận."); loadPosts();
  });
}

/* ---------------- số hiệu ---------------- */

async function loadAnalytics() {
  const a = await api("/analytics");
  const t = a.tong;
  const maxView = Math.max(1, ...a.theo_kenh.map((k) => Number(k.luot_xem || 0)));

  $("#anaCards").innerHTML =
      cell("Lượt xem", num(t.luot_xem), "", 1, "spend")
    + cell("Tương tác", num(t.luot_thich + t.binh_luan + t.chia_se), "", null, "auto")
    + cell("Tỷ lệ tương tác", t.ty_le_tuong_tac, "%", Math.min(1, t.ty_le_tuong_tac / 10), "auto")
    + cell("Đã đăng", num(a.theo_trang_thai.da_dang || 0), "bài", null, "auto")
    + cell("Chờ duyệt", num(a.theo_trang_thai.cho_duyet || 0), "bài", null, "assist");

  $("#anaChannels").innerHTML = a.theo_kenh.length ? a.theo_kenh.map((k) => {
    const tt = k.luot_xem > 0
      ? ((Number(k.luot_thich) + Number(k.binh_luan) + Number(k.chia_se)) / k.luot_xem * 100).toFixed(2)
      : "0.00";
    return `<div class="row">
      <span class="row__flag row__flag--spend" style="width:3px"></span>
      <span class="row__body">
        <span class="row__title">${esc(KENH_LABEL[k.kenh] || k.kenh)}
          <span class="tag tag--plain">${k.so_bai} bài</span></span>
        <span class="row__sub">${num(k.luot_thich)} thích · ${num(k.binh_luan)} bình luận · ${num(k.chia_se)} chia sẻ · tương tác ${tt}%</span>
        <span class="readout__bar" style="margin-top:5px"><span class="readout__fill readout__fill--spend" style="width:${Math.max(2, k.luot_xem / maxView * 100)}%"></span></span>
      </span>
      <span class="row__side"><span class="row__num">${num(k.luot_xem)}</span>
        <span class="row__time">lượt xem</span></span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có số liệu. Đăng bài rồi nhập số liệu ở màn Đăng bài.</p>';

  $("#anaTop").innerHTML = a.bai_tot_nhat.length ? a.bai_tot_nhat.map((b) => `
    <div class="row">
      <span class="row__flag row__flag--auto"></span>
      <span class="row__body">
        <span class="row__title">${esc(b.tieu_de)}
          <span class="tag tag--plain">${esc(KENH_LABEL[b.kenh] || b.kenh)}</span></span>
        <span class="row__sub">${num(b.luot_thich)} thích · ${num(b.binh_luan)} bình luận · tương tác ${b.ty_le_tuong_tac}%</span>
      </span>
      <span class="row__side"><span class="row__num">${num(b.luot_xem)}</span>
        <span class="row__time">lượt xem</span></span>
    </div>`).join("") : '<p class="empty">Chưa đủ dữ liệu để xếp hạng.</p>';
}


/* ---------------- chi phí và hiệu năng ---------------- */

// Thay cho Langfuse. Mọi số này đã nằm sẵn trong bảng messages từ ngày đầu.
// Dựng từ dữ liệu của chính mình thì không phải cài thêm hệ thống nào, và
// không có container nào chạy nền mà không ai dùng.
const vnd0 = (n) => Math.round(Number(n || 0)).toLocaleString("vi-VN") + "đ";

async function loadCost() {
  const c = await api("/cost");
  const t = c.tong;
  const maxNgay = Math.max(1e-9, ...c.theo_ngay.map((d) => d.chi_phi));

  $("#costCards").innerHTML =
      cell("Chi phí 7 ngày", vnd0(t.chi_phi_vnd), "", 1, "spend")
    + cell("Mỗi tin nhắn", usd(t.trung_binh_moi_tin), "", null, "spend")
    + cell("Tin agent đã gửi", num(t.so_tin), "", null, "auto")
    + cell("Token vào", num(t.token_vao), "", null, "auto")
    + cell("Đọc từ cache", t.ty_le_cache, "%", Math.min(1, t.ty_le_cache / 100), "auto");

  $("#costDays").innerHTML = c.theo_ngay.length ? c.theo_ngay.map((d) => `
    <div class="row">
      <span class="row__flag row__flag--spend" style="width:3px"></span>
      <span class="row__body">
        <span class="row__title">${esc(d.ngay)}
          <span class="tag tag--plain">${d.so_tin} tin</span></span>
        <span class="row__sub">${num(d.token_vao)} vào · ${num(d.token_ra)} ra · ${num(d.token_cache)} cache</span>
        <span class="readout__bar" style="margin-top:5px"><span class="readout__fill readout__fill--spend"
          style="width:${Math.max(2, d.chi_phi / maxNgay * 100)}%"></span></span>
      </span>
      <span class="row__side"><span class="row__num">${vnd0(d.chi_phi * 25000)}</span>
        <span class="row__time">${usd(d.chi_phi)}</span></span>
    </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';

  $("#costModels").innerHTML = c.theo_model.length ? c.theo_model.map((m) => `
    <div class="row">
      <span class="row__flag row__flag--auto" style="width:3px"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.model)}
          <span class="tag tag--plain">${m.so_tin} tin</span></span>
        <span class="row__sub">độ trễ trung bình ${(m.tre_tb / 1000).toFixed(1)}s</span>
      </span>
      <span class="row__side"><span class="row__num">${usd(m.chi_phi)}</span></span>
    </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';

  $("#costTop").innerHTML = c.hoi_thoai_dat_nhat.length
    ? c.hoi_thoai_dat_nhat.map((h) => `
      <div class="row">
        <span class="row__flag row__flag--spend"></span>
        <span class="row__body">
          <span class="row__title">${esc(h.customer_name || "Khách")} ${srcBadge(h.channel)}</span>
          <span class="row__sub">${h.msg_count} tin</span>
        </span>
        <span class="row__side"><span class="row__num">${usd(h.chi_phi)}</span>
          <span class="row__time">${vnd0(h.chi_phi * 25000)}</span></span>
      </div>`).join("") : '<p class="empty">Chưa có dữ liệu.</p>';
}

/* ---------------- dữ liệu cá nhân (Nghị định 13/2023) ---------------- */

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

  $("#pdpdOut").innerHTML = `
    <h3 class="subhead">Đơn hàng (${d.so_don_hang}) — sẽ được ẩn danh, không xoá</h3>
    <div class="rows">${don || '<p class="empty">Không có.</p>'}</div>
    <h3 class="subhead">Hội thoại (${d.so_hoi_thoai}) — sẽ bị xoá hẳn cùng mọi tin nhắn</h3>
    <div class="rows">${hoi || '<p class="empty">Không có.</p>'}</div>
    <div class="danger">
      <div class="danger__head">Thực hiện yêu cầu xoá — không hoàn tác được</div>
      <div class="kit__note">Đơn hàng giữ lại mã đơn, sản phẩm và số tiền cho sổ sách;
        tên, số điện thoại và địa chỉ bị thay bằng dấu ẩn danh. Hội thoại và tin nhắn
        xoá hẳn. Mọi lần xoá đều được ghi vào nhật ký kèm căn cứ pháp lý.</div>
      <div class="danger__row">
        <input id="pdpdConfirm" placeholder="Gõ lại ${esc(d.so_dien_thoai)}" autocomplete="off">
        <input id="pdpdReason" placeholder="Lý do (khách yêu cầu qua Zalo…)" autocomplete="off">
        <button type="button" class="btn btn--sm btn--halt" id="pdpdDelete">Xoá dữ liệu</button>
      </div>
    </div>`;

  $("#pdpdDelete").addEventListener("click", async () => {
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
    $("#cong").classList.add("is-off");
    const nhan = $("#rail-nguoi");
    if (nhan) nhan.innerHTML =
      `${esc(nguoi.ho_ten || nguoi.ten_dang_nhap)}`
      + ` · <a href="#" id="logout" style="color:inherit">thoát</a>`;
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
    btn.disabled = false;
  }
});

/* ---------------- vòng làm mới ---------------- */

async function refresh() {
  try {
    await loadOverview();
    if (state.view === "hoithoai") { await loadChannelStrip(); await loadNicks(); await loadConversations(); }
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "video") { await fillProductPicker(); await loadVideos(); }
    if (state.view === "dangbai") { await fillPostPickers(); await loadPosts(); await loadPubChannels(); }
    if (state.view === "hethong") await loadHeThong();
    if (state.view === "sohieu") {
      await loadAnalyticsKhach(); await loadAnalytics(); await loadCost();
    }
    if (state.view === "trithuc") await loadDocs();
    if (state.view === "nhatky") { await loadPdpdPolicy(); await loadEvents(); }
  } catch (e) {
    toast("Không nối được máy chủ: " + e.message, true);
  }
}

// Chỉ bắt đầu vòng làm mới SAU KHI xác nhận có phiên. Gọi refresh() ngay
// khi chưa đăng nhập thì mọi request trả 401 và người dùng thấy một loạt
// thông báo lỗi trước cả khi kịp nhìn thấy ô đăng nhập.
kiemPhien().then((co) => {
  if (!co) return;
  refresh();
  state.timer = setInterval(refresh, 6000);
});
