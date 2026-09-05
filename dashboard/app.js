/* Trạm điều độ — logic giao diện. Không framework, không build step. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { view: "ca", convFilter: "all", orderFilter: "all", postFilter: "all", khoFilter: "all", openConv: null, openContact: null, contactQuery: "", timer: null };
let inboxRefreshTimer = null;

/* ---------------- tiện ích ---------------- */

async function api(path, options = {}) {
  const res = await fetch("/api" + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  /* 401 KHÁC mọi lỗi khác, và phải xử lý riêng.
   *
   * Ở contact center người trực mở tab suốt ca, nên phiên hết hạn là chuyện
   * CHẮC CHẮN xảy ra — hết hạn thật, hoặc máy chủ khởi động lại.
   *
   * Trước đây không có nhánh này. Hệ quả: mọi panel hiện chữ "Unauthorized"
   * (tiếng Anh, giữa giao diện tiếng Việt), vòng làm mới 6 giây vẫn chạy nên
   * toast lỗi bắn lại mỗi 6 giây mãi mãi, và không chỗ nào bảo người dùng
   * đăng nhập lại — màn đăng nhập vẫn ẩn. Họ nhìn một dashboard chết trong
   * khi khách vẫn đang nhắn tới.
   */
  if (res.status === 401) {
    $("#cong")?.classList.remove("is-off");
    // Dừng vòng làm mới: không dừng thì cứ 6 giây một toast lỗi, và mỗi
    // lần là một request vô ích tới máy chủ.
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    throw new Error("Phiên đăng nhập đã hết hạn — đăng nhập lại để tiếp tục");
  }

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

// Thoát cả `'` dù mọi thuộc tính trong file này đều dùng nháy kép. Lý do là
// người sửa sau: đổi một chỗ sang nháy đơn là chuyện vô hại ở mọi dự án
// khác, và ở đây nó lặng lẽ mở đường cho XSS. Tên khách và nội dung tin đến
// thẳng từ nhà cung cấp — người lạ gõ gì vào cũng được.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* Trạng thái -> lớp màu tín hiệu. Một chỗ duy nhất định nghĩa ánh xạ này. */
const SIGNAL = { auto: "auto", assist: "assist", escalated: "halt", closed: "plain" };
const SIGNAL_LABEL = {
  auto: "Tự xử lý", assist: "Chờ duyệt", escalated: "Đã chuyển", closed: "Đã đóng",
};

/* ---------------- điều hướng ---------------- */

/* MỘT chỗ đổi màn. Trước đây logic này bị chép lại ở `moManKetNoi`, và mỗi
   bản chép là một chỗ có thể quên cập nhật khi thanh điều hướng đổi. */
function doiMan(ten) {
  state.view = ten;
  $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === ten));
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === ten));
  refresh();
}

$$(".rail__item").forEach((btn) =>
  btn.addEventListener("click", () => doiMan(btn.dataset.view))
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
  if (o.public_base_url) PUBLIC_BASE = o.public_base_url;
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
    /* TIN CHẾT — ô này chỉ hiện khi có tin chết, và khi hiện thì nó đỏ.
     *
     * Một ô luôn hiện "0" là một ô người ta thôi nhìn sau tuần đầu. Ô chỉ
     * xuất hiện khi có chuyện thì sự xuất hiện của nó CHÍNH LÀ tín hiệu.
     *
     * Không cắt theo 24 giờ: tin không gửi được tuần trước vẫn là tin
     * khách không nhận được. Ba tin đã chết rải hơn một tuần mà không ai
     * biết, đúng vì không có chỗ nào đếm chúng. */
    (o.tin_chet && o.tin_chet.so
      ? cell("Tin KHÔNG gửi được", o.tin_chet.so, "khách không nhận được", 1, "halt")
      : ""),
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

  /* limit=200, không phải 12. Khung này là HÀNG ĐỢI, không phải bản tin:
     cắt ở 12 nghĩa là khi có 20 khách chờ thì 8 người biến mất khỏi màn
     hình — và với thứ tự chờ-lâu-nhất-trước do API trả về, 8 người mất đi
     lại chính là 8 người mới nhắn. Thà cuộn dài còn hơn giấu người đang đợi.
     API đã xếp sẵn ai chờ lâu nhất lên đầu. */
  const waiting = await api("/conversations?status=can_nguoi&limit=200");
  $("#queue").innerHTML = waiting.length
    ? waiting.map((c) => convRow(c, true)).join("")
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
  zalo_personal: "Zalo cá nhân", zalo_oa: "Zalo OA",
  facebook: "Facebook", instagram: "Instagram",
  whatsapp: "WhatsApp", webchat: "Web chat", web: "Web chat",
};

/* Một connector tương thích có thể là HỘP THƯ GỘP: Facebook Messenger, Instagram DM, WhatsApp,
   chat website, email, Telegram đều đổ về cùng một kênh. Hiện huy hiệu
   tên connector là mất đúng thông tin người trực cần — khách này đến từ đâu.
   Tên lớp connector có dạng "Channel::FacebookPage"; bộ đọc đã cắt phần
   "Channel::" nên ở đây chỉ còn phần đuôi. */
const NEN_TANG_LABEL = {
  facebookpage: "Facebook", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp",
  webwidget: "Web chat", email: "Email", telegram: "Telegram",
  twiliosms: "SMS", line: "LINE", api: "API",
};

/* Nền tảng nào chưa có màu riêng thì dùng màu connector tương thích. */
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

/* Ngưỡng để một ô chờ chuyển sang màu cảnh báo. Khớp với
   `cho_nguoi_toi_da_phut` trong config — cùng một con số thì thứ người
   trực nhìn thấy trên màn hình và thứ canh gác nhắn cho họ là một. */
const CHO_LAU_PHUT = 30;

function choBadge(phut) {
  if (phut === undefined || phut === null) return "";
  const nhan = phut < 60 ? `chờ ${phut}p`
             : `chờ ${Math.floor(phut / 60)}h${String(phut % 60).padStart(2, "0")}`;
  const lop = phut >= CHO_LAU_PHUT ? " row__wait--lau" : "";
  return `<span class="row__wait${lop}">${nhan}</span>`;
}

function convRow(c, hangDoi) {
  const sig = SIGNAL[c.status] || "plain";
  const sub = c.typing
    ? `<span class="row__typing"><i></i><i></i><i></i> đang soạn tin…</span>`
    : `<span class="row__sub">${esc(c.last_message || "—")}</span>`;
  const customer = c.customer_name || c.customer || "Khách";
  const unread = Number(c.unread_count || 0);
  const due = c.first_response_due_at || c.resolution_due_at;
  return `<button type="button" class="row ${state.openConv === c.id ? "is-on" : ""}" data-conv="${c.id}">
    <span class="row__flag row__flag--${sig}"></span>
    <span class="row__body">
      <span class="row__title">${esc(customer)} ${srcBadge(c.channel || c.account_channel, c.nen_tang)}</span>
      <span class="row__sub">${esc(c.account_name || "")}${due ? ` · SLA ${clock(due)}` : ""}</span>
      ${sub}
    </span>
    <span class="row__side">
      ${hangDoi ? choBadge(c.cho_bao_lau_phut) : unread ? `<span class="unread">${unread}</span>` : ""}
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
  const query = state.convFilter === "all" ? "" : `&status=${encodeURIComponent(state.convFilter)}`;
  const result = await api("/inbox/conversations?limit=100" + query);
  const list = result.items || [];
  $("#convlist").innerHTML = list.length
    ? list.map(convRow).join("")
    : '<p class="empty">Chưa có hội thoại nào.</p>';
  wireConvRows("#convlist");
  if (state.openConv) await loadThread(state.openConv);
}

async function loadThread(id) {
  let c;
  try { c = await api("/inbox/conversations/" + id); }
  catch { $("#convdetail").innerHTML = '<p class="empty">Không tìm thấy hội thoại.</p>'; return; }

  const msgs = c.messages.map((m) => {
    const draft = m.role === "agent" && m.delivery_status === "draft";
    const who = { customer: "Khách", agent: "AI", staff: "Nhân viên", system: "Hệ thống" }[m.role] || m.role;
    const meta = [
      hhmm(m.created_at), who, m.delivery_status || "",
      m.confidence != null ? "tin cậy " + m.confidence.toFixed(2) : "",
      m.grounded === false ? "KHÔNG có căn cứ" : "",
      m.cost ? usd(m.cost) : "",
      m.latency_ms ? m.latency_ms + "ms" : "",
      (m.sources || []).length ? "có nguồn tham chiếu" : "",
    ].filter(Boolean).join(" · ");

    /* Ảnh khách gửi. Đường dẫn đã trỏ qua proxy từ lúc đọc webhook, nên
       hiện được bằng chính phiên dashboard — người trực không phải đăng
       nhập hệ thống trung gian lần nữa chỉ để xem một tấm ảnh.

       Ảnh nằm TRÊN bong bóng chữ: khách gửi ảnh trước rồi mới gõ chú
       thích, và đảo thứ tự làm người đọc hiểu ngược ý họ. */
    /* Nguồn ảnh: URL của nhà cung cấp nếu có, còn không thì đường phục vụ
     * tệp của chính hệ thống.
     *
     * Tin NHÂN VIÊN gửi không có `url` — `queue_file` chỉ lưu `storage_key`,
     * tức đường dẫn trên máy chủ. Vẽ thẳng `url` cho ra ảnh vỡ: người trực
     * gửi ảnh cho khách xong, nhìn lại khung chat thì thấy biểu tượng hỏng.
     */
    const nguonAnh = (a) => a.url || (a.id ? `/api/attachments/${a.id}/file` : "");

    const anh = (m.attachments || []).length
      ? `<div class="msg__anh">${m.attachments.map((a) => {
          const src = nguonAnh(a);
          const ten = (a.metadata && a.metadata.caption) || "";
          if (!src) return "";
          return (a.kind || a.loai) === "image"
            ? `<a href="${esc(src)}" target="_blank" rel="noopener" title="${esc(ten)}">
                 <img src="${esc(src)}" alt="${esc(ten || "ảnh")}" loading="lazy"></a>`
            : `<a class="msg__file" href="${esc(src)}" target="_blank" rel="noopener">
                 📎 ${esc(ten || a.kind || "tệp đính kèm")}</a>`;
        }).join("")}</div>`
      : "";

    /* Không lặp lại tên tệp dưới ảnh.
     *
     * `queue_file` đặt nội dung tin BẰNG chú thích, và chú thích mặc định là
     * tên tệp. Vẽ cả hai thì khung chat hiện ảnh rồi ngay dưới là một bong
     * bóng xanh ghi "WIN_20241105_22_45_28_Pro.jpg" — Messenger và Zalo đều
     * không làm vậy: ảnh tự nói lên nó là gì. */
    const tenTep = (m.attachments || [])
      .map((a) => (a.metadata && a.metadata.caption) || "").filter(Boolean);
    const chuTrung = m.content && tenTep.includes(m.content.trim());

    return `<div class="msg msg--${m.role} ${draft ? "msg--draft" : ""}">
      ${anh}
      ${m.content && !chuTrung ? `<div class="msg__bubble">${esc(m.content)}</div>` : ""}
      <div class="msg__meta">
        <span>${esc(meta)}</span>
        ${draft ? `<button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>` : ""}
      </div>
    </div>`;
  }).join("");

  const taken = c.mode === "human" || c.status === "escalated";

  /* Nhớ những gì NGƯỜI DÙNG đang giữ, TRƯỚC khi đập panel đi dựng lại.
   *
   * Panel này dựng lại bằng `innerHTML` mỗi lần refresh — SSE báo tin mới,
   * hoặc nhịp 6 giây. Thẻ <textarea> cũ bị vứt cùng cả khối, nên chữ đang
   * gõ dở biến mất. Nghịch lý: KHÁCH CÀNG NHẮN NHIỀU thì nhân viên càng
   * hay mất chữ — đúng lúc hội thoại đang nóng.
   *
   * Ba thứ phải giữ, mỗi thứ chặn một kiểu khó chịu khác nhau:
   *   bản nháp   -> không mất chữ
   *   con trỏ    -> không nhảy về đầu dòng, đang gõ giữa câu vẫn gõ tiếp được
   *   vị trí cuộn-> đang đọc lại đoạn cũ thì không bị giật xuống đáy
   */
  const o_cu = $("#replyform") ? $('#replyform [name="text"]') : null;
  const dang_focus = o_cu && document.activeElement === o_cu;
  const con_tro = o_cu ? o_cu.selectionStart : null;
  const thread_cu = $("#thread");
  // Cách đáy dưới 40px thì coi như đang theo dõi tin mới -> cuộn tiếp.
  // Ở xa hơn nghĩa là đang đọc đoạn cũ -> giữ nguyên chỗ họ đang đọc.
  const dang_o_day = !thread_cu
    || thread_cu.scrollHeight - thread_cu.scrollTop - thread_cu.clientHeight < 40;
  const cuon_cu = thread_cu ? thread_cu.scrollTop : 0;

  $("#convdetail").innerHTML = `
    <div class="convo__title">
      <span class="convo__name">${esc(c.customer_name || "Khách")}</span>
      <span class="tag tag--${SIGNAL[c.status] || "plain"}">${SIGNAL_LABEL[c.status] || c.status}</span>
      <span class="convo__spacer"></span>
      ${srcBadge(c.account_channel, c.nen_tang)}<span class="msg__meta">${esc(c.account_name || "")}</span>
      ${c.contact_id ? `<button type="button" class="btn btn--sm" id="open-contact" data-contact="${c.contact_id}">Customer 360</button>` : ""}
      ${!taken ? `<button type="button" class="btn btn--sm ${c.mode === "auto" ? "" : "btn--go"}" id="btn-chedo"
        data-chedo="${c.mode === "auto" ? "assist" : "auto"}">
        ${c.mode === "auto" ? "Duyệt trước khi gửi" : "Để agent tự trả lời"}
      </button>` : ""}
      <button type="button" class="btn btn--sm ${taken ? "" : "btn--halt"}" id="btn-take">
        ${taken ? "Kết thúc tiếp quản" : "Tôi tiếp quản"}
      </button>
    </div>
    <div class="opsbar">
      <span>Mode <b>${esc(c.mode || "auto")}</b></span><span>Ưu tiên <b>${esc(c.priority || "normal")}</b></span>
      <span>SLA phản hồi <b>${c.first_response_due_at ? clock(c.first_response_due_at) : "chưa áp dụng"}</b></span>
      <span>Version <b>${c.version || 1}</b></span>
    </div>
    <div class="thread" id="thread">${msgs || '<p class="empty">Chưa có tin nhắn.</p>'}
      ${c.typing ? '<div class="msg msg--agent"><div class="typing"><i></i><i></i><i></i></div></div>' : ""}
    </div>
    <form class="convo__bar" id="replyform">
      <textarea name="text" placeholder="Nhắn trực tiếp cho khách…" required></textarea>
      <span class="convo__dinhkem">
        <button type="button" class="btn btn--sm" data-dinhkem title="Gửi ảnh hoặc tài liệu">📎</button>
        <input type="file" id="tep-dinhkem" accept="image/jpeg,image/png,image/webp,image/gif,application/pdf" hidden>
      </span>
      <button type="submit" class="btn btn--primary">Gửi</button>
    </form>`;

  const thread = $("#thread");
  if (thread) thread.scrollTop = dang_o_day ? thread.scrollHeight : cuon_cu;

  /* Trả lại bản nháp.
   *
   * Gắn theo TỪNG hội thoại: giữ chung một biến là dán chữ soạn cho khách A
   * sang khung của khách B — tệ hơn mất chữ nhiều, vì nó gửi nhầm nội dung
   * cho nhầm người.
   */
  const o_moi = $('#replyform [name="text"]');
  const nhap = state.nhapTheoHoiThoai && state.nhapTheoHoiThoai[id];
  if (o_moi && nhap) {
    o_moi.value = nhap;
    if (dang_focus) {
      o_moi.focus();
      const vt = con_tro == null ? nhap.length : Math.min(con_tro, nhap.length);
      o_moi.setSelectionRange(vt, vt);
    }
  }
  if (o_moi) {
    o_moi.addEventListener("input", () => {
      state.nhapTheoHoiThoai = state.nhapTheoHoiThoai || {};
      state.nhapTheoHoiThoai[id] = o_moi.value;
    });

    /* Enter gửi, Shift+Enter xuống dòng.
     *
     * Mặc định của trình duyệt với <textarea> là Enter xuống dòng và không
     * submit. Không phải lỗi trình duyệt — nhưng người trực gõ theo phản xạ
     * từ Zalo và Messenger, nơi Enter luôn gửi. Giữ mặc định ở đây là bắt
     * họ với chuột sang nút Gửi sau mỗi câu.
     *
     * `isComposing` là bắt buộc với tiếng Việt: bộ gõ dấu dùng Enter để
     * chốt từ đang gõ. Không kiểm cờ này thì gõ "phường" bị gửi mất nửa
     * chừng thành "phươn".
     */
    o_moi.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing || ev.keyCode === 229) return;
      ev.preventDefault();
      $("#replyform").requestSubmit();
    });
  }

  $$("[data-approve]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        const r = await api("/messages/" + b.dataset.approve + "/approve", { method: "POST" });
        toast(r.ok ? "Đã gửi cho khách." : "Không gửi được: " + r.detail, !r.ok);
        refresh();
      } catch (e) { toast(e.message, true); }
    })
  );

  const openContact = $("#open-contact");
  if (openContact) openContact.addEventListener("click", () => openCustomer(openContact.dataset.contact));

  /* Trả hội thoại VỀ cho agent, hoặc bắt duyệt trước khi gửi.
   *
   * Trước khi có nút này, hội thoại rơi xuống "Chờ duyệt" hay "Đã chuyển
   * người" là KẸT ở đó vĩnh viễn: chỉ có nút đi xuống, không có nút đi lên.
   * Ô xanh "Agent xử lý" trên chú giải là một lời hứa hệ thống không giữ
   * được, và mọi hội thoại cũ dồn dần vào hàng chờ duyệt.
   *
   * Không hiện khi đang có người tiếp quản: phải "Kết thúc tiếp quản" trước.
   * Bật auto sau lưng người đang giữ là để AI nhắn chen vào giữa cuộc họ
   * đang xử lý. */
  const nutCheDo = $("#btn-chedo");
  if (nutCheDo) nutCheDo.addEventListener("click", async () => {
    const sang = nutCheDo.dataset.chedo;
    const ly_do = sang === "auto"
      ? "Người trực trả hội thoại về cho agent"
      : "Người trực bật duyệt trước khi gửi";
    nutCheDo.disabled = true;
    try {
      await api(`/inbox/conversations/${id}/che-do`, {
        method: "POST",
        body: JSON.stringify({
          che_do: sang, expected_version: c.version || 1, reason: ly_do,
        }),
      });
      toast(sang === "auto"
        ? "Agent sẽ tự trả lời hội thoại này."
        : "Từ giờ AI soạn xong sẽ chờ bạn duyệt.");
      refresh();
    } catch (e) {
      toast(e.message, true);
      nutCheDo.disabled = false;
    }
  });

  $("#btn-take").addEventListener("click", async () => {
    try {
      await api(`/inbox/conversations/${id}/${taken ? "release" : "takeover"}`, {
        method: "POST",
        body: JSON.stringify({ expected_version: c.version || 1, reason: taken ? "Nhân viên kết thúc tiếp quản" : "Nhân viên nhận xử lý" }),
      });
      toast(taken ? "Đã chuyển về chế độ gợi ý." : "Bạn đang giữ hội thoại này. AI đã dừng gửi.");
      refresh();
    } catch (e) { toast(e.message, true); }
  });

  /* Đính kèm ảnh hoặc tài liệu — như mọi công cụ chat thật.
   *
   * Trước đây agent gửi được ảnh sản phẩm còn NGƯỜI TRỰC thì không. Khách
   * hỏi "cho xem ảnh thật cái đã mở nắp" thì họ phải mở Zalo riêng ra gửi,
   * và tin đó nằm ngoài hội thoại — không ai truy được về sau.
   *
   * Gửi ngay khi chọn tệp, không đợi bấm Gửi: người dùng quen với Messenger
   * và Zalo, cả hai đều gửi ngay. Bắt bấm thêm một nút là bước thừa mà
   * không ai nhớ.
   */
  const nutKem = $("[data-dinhkem]");
  const oTep = $("#tep-dinhkem");
  if (nutKem && oTep) {
    nutKem.addEventListener("click", () => oTep.click());
    oTep.addEventListener("change", async () => {
      const f = oTep.files && oTep.files[0];
      if (!f) return;
      nutKem.disabled = true;
      const chu = nutKem.textContent;
      nutKem.textContent = "⏳";
      try {
        const fd = new FormData();
        fd.append("tep", f);
        // Chú thích lấy từ ô soạn tin nếu người trực đã gõ sẵn — họ thường
        // viết "ảnh thật bên em nè" rồi mới chọn ảnh.
        const oChu = $('#replyform [name="text"]');
        if (oChu && oChu.value.trim()) fd.append("chu_thich", oChu.value.trim());

        // KHÔNG đặt Content-Type: trình duyệt phải tự sinh boundary cho
        // multipart. Đặt tay là máy chủ không tách được phần tệp.
        const r = await fetch(`/api/conversations/${id}/send-file`, {
          method: "POST", body: fd, credentials: "same-origin",
        });
        if (!r.ok) {
          const loi = await r.json().catch(() => ({}));
          throw new Error(loi.detail || `Không gửi được (HTTP ${r.status})`);
        }
        toast("Đã gửi tệp cho khách.");
        if (oChu) {
          oChu.value = "";
          if (state.nhapTheoHoiThoai) delete state.nhapTheoHoiThoai[id];
        }
        refresh();
      } catch (e) {
        toast(e.message, true);
      } finally {
        oTep.value = "";
        nutKem.disabled = false;
        nutKem.textContent = chu;
      }
    });
  }

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
      // Xoá bản nháp đã lưu, nếu không lần dựng lại kế tiếp sẽ chép nó
      // trở vào khung và người trực tưởng tin chưa gửi đi.
      if (state.nhapTheoHoiThoai) delete state.nhapTheoHoiThoai[id];
      refresh();
    } catch (e) { toast(e.message, true); }
  });
}

/* ---------------- Customer 360 ---------------- */

function openCustomer(id) {
  state.openContact = id;
  state.view = "khachhang";
  $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === "khachhang"));
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === "khachhang"));
  loadContacts();
}

$("#contactsearch")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  state.contactQuery = String(new FormData(ev.target).get("q") || "").trim();
  loadContacts();
});

async function loadContacts() {
  const contacts = await api(`/contacts?limit=100&q=${encodeURIComponent(state.contactQuery)}`);
  $("#c-khachhang").textContent = contacts.length || "";
  $("#contactlist").innerHTML = contacts.length ? contacts.map((contact) => `
    <button type="button" class="row row--avatar ${state.openContact === contact.id ? "is-on" : ""}" data-contact="${contact.id}">
      <span class="avatar">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <span class="row__body"><span class="row__title">${esc(contact.display_name || "Khách")}</span>
        <span class="row__sub">${esc(contact.phone || contact.email || "Chưa có PII xác minh")} · ${contact.contact_point_count || 0} danh tính</span></span>
      <span class="row__side"><span class="row__time">${clock(contact.last_seen)}</span></span>
    </button>`).join("") : '<p class="empty">Không tìm thấy khách hàng trong phạm vi tài khoản của bạn.</p>';
  $$("#contactlist [data-contact]").forEach((row) => row.addEventListener("click", () => {
    state.openContact = row.dataset.contact;
    loadContacts();
  }));
  if (state.openContact) await loadContactDetail(state.openContact);
}

async function loadContactDetail(id) {
  let contact;
  try { contact = await api(`/contacts/${id}`); }
  catch (e) { $("#contactdetail").innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  const points = (contact.contact_points || []).map((point) => `
    <div class="identity-card">${srcBadge(point.channel)}<div><b>${esc(point.account_name)}</b>
      <small>${esc(point.handle || point.external_user_id)}</small></div>
      <span>${clock(point.last_seen)}</span></div>`).join("");
  const consents = (contact.consents || []).map((consent) => `
    <span class="consent consent--${esc(consent.status)}">${esc(consent.purpose)} · ${esc(consent.status)}</span>`).join("");
  const tags = (contact.tags || []).map((tag) => `<span class="profile-tag">${esc(tag.tag)}</span>`).join("");
  const notes = (contact.notes || []).map((note) => `
    <article class="contact-note"><p>${esc(note.body)}</p><small>${esc(note.visibility)} · ${clock(note.created_at)}</small></article>`).join("");
  const conversations = (contact.conversations || []).map((conv) => `
    <button class="timeline-item" type="button" data-open-conv="${conv.id}">
      ${srcBadge(conv.channel)}<span>${esc(conv.account_name)} · ${esc(conv.status)}</span><time>${clock(conv.updated_at)}</time>
    </button>`).join("");
  $("#contactdetail").innerHTML = `
    <div class="profile-head"><span class="avatar avatar--lg">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <div><p class="eyebrow">CUSTOMER 360</p><h2>${esc(contact.display_name || "Khách")}</h2>
        <p>${esc(contact.phone || "Chưa có số điện thoại")} · ${esc(contact.email || "Chưa có email")}</p></div>
      <span class="privacy-pill">${contact.pii_masked ? "PII đã ẩn theo quyền" : "PII được phép xem"}</span></div>
    <div class="profile-grid"><div><span>Trạng thái</span><b>${esc(contact.status)}</b></div><div><span>Phiên bản</span><b>${contact.version}</b></div>
      <div><span>Lần đầu</span><b>${clock(contact.first_seen)}</b></div><div><span>Gần nhất</span><b>${clock(contact.last_seen)}</b></div></div>
    <h3 class="subhead">Nhãn chăm sóc</h3>
    <div class="profile-actions"><div class="profile-tags">${tags || '<span class="empty">Chưa có nhãn.</span>'}</div>
      <form id="contact-tag-form" class="inline-action"><input name="tag" maxlength="80" required placeholder="VIP, cần gọi lại…"><button class="btn btn--sm" type="submit">Thêm nhãn</button></form></div>
    <h3 class="subhead">Danh tính theo kênh</h3><div class="identity-grid">${points || '<p class="empty">Chưa có danh tính.</p>'}</div>
    <h3 class="subhead">Consent</h3><div class="consent-row">${consents || '<span class="empty">Chưa ghi nhận consent.</span>'}</div>
    <form id="contact-consent-form" class="consent-form">
      <input name="purpose" maxlength="80" required placeholder="Mục đích, ví dụ marketing">
      <select name="status"><option value="granted">Đồng ý</option><option value="denied">Từ chối</option><option value="withdrawn">Rút lại</option></select>
      <input name="source" maxlength="300" required placeholder="Nguồn bằng chứng">
      <button class="btn btn--sm" type="submit">Ghi consent</button>
    </form>
    <h3 class="subhead">Ghi chú nội bộ</h3><div class="contact-notes">${notes || '<span class="empty">Chưa có ghi chú.</span>'}</div>
    <form id="contact-note-form" class="note-form"><textarea name="body" maxlength="5000" required placeholder="Thông tin cần bàn giao cho đội chăm sóc…"></textarea>
      <select name="visibility"><option value="team">Cả đội</option><option value="manager">Quản lý</option></select><button class="btn btn--sm" type="submit">Lưu ghi chú</button></form>
    <h3 class="subhead">Hội thoại</h3><div class="timeline">${conversations || '<p class="empty">Chưa có hội thoại.</p>'}</div>`;

  $("#contact-tag-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const tag = String(new FormData(form).get("tag") || "").trim();
    if (!tag) return;
    try {
      await api(`/contacts/${id}/tags`, { method: "POST", body: JSON.stringify({ tag }) });
      toast("Đã thêm nhãn khách hàng.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $("#contact-note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.body = String(values.body || "").trim();
    if (!values.body) return;
    try {
      await api(`/contacts/${id}/notes`, { method: "POST", body: JSON.stringify(values) });
      toast("Đã lưu ghi chú nội bộ.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $("#contact-consent-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const purpose = String(values.purpose || "").trim();
    if (!purpose) return;
    try {
      await api(`/contacts/${id}/consents/${encodeURIComponent(purpose)}`, {
        method: "PUT",
        body: JSON.stringify({ status: values.status, source: String(values.source || "").trim(), evidence: { captured_via: "dashboard" } }),
      });
      toast("Đã cập nhật consent và nhật ký kiểm toán.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $$('[data-open-conv]').forEach((button) => button.addEventListener("click", () => {
    state.openConv = button.dataset.openConv; state.view = "hoithoai";
    $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === "hoithoai"));
    $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === "hoithoai"));
    loadConversations();
  }));
}


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
        ${cho_duyet ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--go" data-oapprove="${o.id}">Duyệt</button>
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ</button>
          </span>` : xin_huy ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ đơn</button>
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
  zalocrm: "Zalo cá nhân", chatwoot: "Kênh tương thích", facebook: "Facebook",
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

/* Màn vận hành chỉ hiển thị các dịch vụ thuộc sản phẩm hiện tại. Connector
   tương thích cũ vẫn có thể chạy ở backend trong giai đoạn chuyển đổi nhưng
   không được biến thành một ứng dụng con hay thương hiệu trên dashboard. */
/* `dangCho` = NGƯỜI vừa bấm nút, đang đợi và cần phản hồi ngay.
   Vòng làm mới 6 giây gọi hàm này KHÔNG kèm cờ, và phải vẽ đè im lặng.

   Bản đầu gán ô chờ vô điều kiện: cứ 6 giây panel trắng xoá rồi hiện lại
   sau khi dò xong 5 dịch vụ. Đó là cái nhấp nháy người dùng nhìn thấy. */
async function loadHeThong(dangCho = false) {
  const box = $("#hethong");
  const btn = $("#hethongrun");
  if (btn) btn.disabled = true;
  if (dangCho || !box.innerHTML.trim()) {
    box.innerHTML = '<p class="empty">Đang hỏi từng dịch vụ…</p>';
  }
  try {
    const d = await api("/he-thong");
    const visible = d.dich_vu.filter((x) => !["zalocrm", "chatwoot"].includes(x.ma));
    const running = visible.filter((x) => x.song).length;
    $("#c-hethong").textContent = `${running}/${visible.length}`;
    box.innerHTML = visible.map((x) => `<div class="row">
        <span class="row__flag row__flag--${x.song ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(x.ten)}${x.chinh ? " · trang bạn đang xem" : ""}</b>
          <span class="row__sub">${esc(x.mo_ta)}
            ${x.nhung_duoc ? "· mở ngay trong đây"
              : x.can_dang_nhap ? "· cần đăng nhập riêng" : ""}</span>
        </div>
        ${x.di_toi_man
          /* Chưa nối được thì KHÔNG có gì để "Mở". Đưa người dùng tới màn
             làm được việc, và nói đúng việc nút làm. Bản đầu render <a href>
             trỏ về chính dashboard: bấm vào trang quay về trang chính, nhìn
             như nút hỏng. */
          ? `<button type="button" class="btn btn--sm" data-di-toi="${esc(x.di_toi_man)}">Cấu hình</button>`
          : !x.song
          ? `<span class="tag tag--halt">không chạy</span>`
          : x.nhung_duoc
            /* Nhúng được thì mở NGAY TRONG dashboard. Nút mở tab mới vẫn
               giữ bên cạnh: iframe hỏng thì người vận hành phải còn một
               đường vào, nếu không một lỗi giao diện thành mất quyền
               truy cập cả hệ thống con. */
            ? `<button type="button" class="btn btn--sm" data-mo-trong="${esc(x.ma)}">Mở</button>
               <a class="btn btn--sm btn--ghost" href="${esc(x.url)}" target="_blank" rel="noopener" title="Mở tab mới">↗</a>`
            : `<a class="btn btn--sm" href="${esc(x.url)}" target="_blank" rel="noopener">Mở</a>`}
      </div>`).join("");
    $("#hethongvisao").textContent = "Các thành phần vận hành dùng chung một dashboard, cùng xác thực và nhật ký kiểm toán.";
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* Bọc trong arrow function, KHÔNG gán thẳng `loadHeThong`: gán thẳng thì
   tham số đầu là đối tượng Event — truthy, nên nó vô tình chạy đúng. Dựa
   vào tình cờ là thứ hỏng ở lần refactor sau. */
$("#hethongrun")?.addEventListener("click", () => loadHeThong(true));

/* Bấm "Mở" ở màn Hệ thống -> nhảy sang màn Kết nối và mở đúng app đó.
   Gắn trên vùng chứa chứ không trên từng nút: danh sách dựng lại sau mỗi
   lần Kiểm tra, và listener gắn trên nút cũ thì chết theo nút cũ. */
/* Nút "Cấu hình" của mục chưa nối: chuyển sang màn tương ứng trong chính
   dashboard, không mở tab mới. Gắn trên vùng chứa vì danh sách được dựng
   lại sau mỗi lần làm mới. */
$("#hethong")?.addEventListener("click", (e) => {
  const diToi = e.target.closest("[data-di-toi]");
  if (diToi) {
    e.preventDefault();
    doiMan(diToi.dataset.diToi);
    return;
  }
  const nut = e.target.closest("[data-mo-trong]");
  if (!nut) return;
  moManKetNoi(nut.dataset.moTrong);
});

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
    if (state.view === "hoithoai") await loadConversations();
    if (state.view === "khachhang") await loadContacts();
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "video") { await fillProductPicker(); await loadVideos(); }
    if (state.view === "dangbai") { await fillPostPickers(); await loadPosts(); await loadPubChannels(); }
    if (state.view === "hethong") await loadHeThong();
    if (state.view === "ketnoi") { await loadKetNoi(); await loadTichHop(); }
    if (state.view === "sohieu") {
      await loadAnalyticsKhach(); await loadAnalytics(); await loadCost();
    }
    if (state.view === "trithuc") await loadDocs();
    if (state.view === "kynang") await loadKyNang();
    if (state.view === "cauhinh") { await loadCauHinh(); await loadCaiDatApi(); }
    if (state.view === "nhatky") { await loadPdpdPolicy(); await loadEvents(); }
  } catch (e) {
    toast("Không nối được máy chủ: " + e.message, true);
  }
}

function startInboxStream() {
  if (!("EventSource" in window)) return;
  const stream = new EventSource("/api/inbox/events");
  const schedule = () => {
    clearTimeout(inboxRefreshTimer);
    inboxRefreshTimer = setTimeout(async () => {
      try {
        await loadOverview();
        if (state.view === "hoithoai") await loadConversations();
        if (state.view === "khachhang") await loadContacts();
      } catch { /* EventSource tự nối lại; polling 6 giây vẫn là fallback. */ }
    }, 120);
  };
  ["message.created", "message.sent", "conversation.updated", "conversation.takeover", "conversation.released"]
    .forEach((topic) => stream.addEventListener(topic, schedule));
  window.addEventListener("beforeunload", () => stream.close(), { once: true });
}

// Chỉ bắt đầu vòng làm mới SAU KHI xác nhận có phiên. Gọi refresh() ngay
// khi chưa đăng nhập thì mọi request trả 401 và người dùng thấy một loạt
// thông báo lỗi trước cả khi kịp nhìn thấy ô đăng nhập.
kiemPhien().then((co) => {
  if (!co) return;
  refresh();
  startInboxStream();
  state.timer = setInterval(refresh, 6000);
});

/* Trung tâm kết nối native. Secret chỉ đi từ form tới vault; response không
   chứa credential nên DOM cũng không có gì để vô tình làm lộ. */
function moManKetNoi() {
  doiMan("ketnoi");
}

$("#connection-add-toggle")?.addEventListener("click", () => {
  $("#connection-create").classList.toggle("is-hidden");
});

/*
 * Địa chỉ CÔNG KHAI của hệ thống, do máy chủ báo qua overview.
 *
 * Trình duyệt chỉ biết `location.origin` — tức `http://127.0.0.1:8000` khi
 * người vận hành mở dashboard tại chỗ. Meta và Zalo KHÔNG BAO GIỜ gọi vào
 * được địa chỉ đó, nhưng copy nó dán vào Meta thì lỗi báo về chỉ nói "không
 * xác minh được URL" — không nói vì sao.
 *
 * Chưa dựng tunnel thì máy chủ vẫn trả localhost, và lúc đó hiện
 * `location.origin` cũng đúng — nên đường lui giữ nguyên hành vi cũ.
 */
let PUBLIC_BASE = "";

function goc_cong_khai() {
  return (PUBLIC_BASE || location.origin).replace(/\/+$/, "");
}

/* Số tài khoản hiện sẵn trước khi thu gọn.
 *
 * Một tài khoản Facebook có thể quản lý hàng chục Trang. Đổ hết ra màn hình
 * thì mọi kênh khác — Zalo, Webchat — bị đẩy xuống dưới tầm nhìn, và người
 * trực phải cuộn rất lâu mới thấy thứ mình cần.
 *
 * Năm là đủ để thấy kênh có gì mà không nuốt mất cả trang. */
const SO_HIEN_SAN = 5;

const KENH_META = ["facebook", "instagram", "whatsapp"];

/*
 * URL callback theo KÊNH, không theo từng tài khoản.
 *
 * Meta chỉ cho khai MỘT callback URL cho mỗi app, và hệ thống đã có đường
 * dùng chung `/webhook/native/meta` tự phân phát tin về đúng Trang. Hiện một
 * URL riêng cho mỗi Trang là dựng ra 26 địa chỉ mà không ai cần tới — tệ hơn
 * là rối: người dùng tưởng phải khai 26 lần bên Meta rồi bỏ dở.
 */
function callbackTheoKenh(channel) {
  if (KENH_META.includes(channel)) return `${goc_cong_khai()}/webhook/native/meta`;
  if (channel === "zalo_personal") return `${goc_cong_khai()}/webhook/native/zalo-personal`;
  /* Zalo OA KHÔNG dùng đường chung: mỗi OA có secret key riêng, nên phải
     biết OA nào TRƯỚC khi kiểm được chữ ký. URL vì thế mang account_id, và
     phải dựng ở `connectionCallback` nơi có đối tượng account. */
  return "";
}

function connectionCallback(account) {
  // Kênh Meta dùng đường chung -> không hiện gì ở dòng tài khoản.
  if (KENH_META.includes(account.channel)) return "";
  if (account.channel === "zalo_oa") {
    return `${goc_cong_khai()}/webhook/native/zalo-oa/${account.id}`;
  }
  return callbackTheoKenh(account.channel);
}

/* Thứ tự hiện tài khoản trong một kênh. Số nhỏ lên trên.
 *
 * Người trực mở màn hình này để hỏi "kênh của mình có sống không" — câu trả
 * lời phải nằm ở dòng đầu, không phải dòng thứ mười chín.
 *
 * `degraded` và `reauth_required` xếp ngay sau `active` chứ KHÔNG xuống dưới
 * `pending`: chúng là Trang đã từng chạy rồi hỏng, tức đang mất tin của
 * khách NGAY LÚC NÀY. Chôn chúng dưới hai mươi Trang chưa dùng bao giờ là
 * giấu đúng thứ cần xử lý gấp nhất.
 *
 * `pending` chưa bao giờ nhận tin nên chưa mất gì. `disabled` là người ta chủ
 * động tắt — không cần chiếm chỗ trên cùng.
 */
const UU_TIEN_TRANG_THAI = {
  active: 0, degraded: 1, reauth_required: 2, pending: 3, disabled: 4,
};

const ACCOUNT_STATUS_LABEL = {
  pending: "Chờ xác minh", active: "Sẵn sàng", degraded: "Gián đoạn",
  reauth_required: "Cần đăng nhập lại", disabled: "Đã tạm ngắt",
};

async function loadKetNoi() {
  const accounts = await api("/channel-accounts");
  const grouped = Object.fromEntries(Object.keys(CHANNEL_LABEL).map((key) => [key, []]));
  accounts.forEach((account) => (grouped[account.channel] ||= []).push(account));

  /* Sắp xếp mỗi kênh: đang chạy lên đầu, hỏng ngay sau, chưa nối xuống dưới.
   *
   * Tiêu chí phụ là TÊN, và nó bắt buộc: không có nó thì hai Trang cùng
   * trạng thái đổi chỗ nhau mỗi lần làm mới (6 giây một lần), và mắt người
   * trực phải tìm lại từ đầu mỗi lượt. */
  Object.values(grouped).forEach((ds) => ds.sort((a, b) => {
    const ua = UU_TIEN_TRANG_THAI[a.status] ?? 9;
    const ub = UU_TIEN_TRANG_THAI[b.status] ?? 9;
    if (ua !== ub) return ua - ub;
    return String(a.display_name || "").localeCompare(String(b.display_name || ""), "vi");
  }));
  $("#connectiongrid").innerHTML = Object.entries(grouped)
    .filter(([channel]) => ["zalo_personal", "zalo_oa", "facebook", "instagram", "whatsapp", "webchat"].includes(channel))
    .map(([channel, items]) => {
      /* Việc CHUNG của cả kênh gom lên đây, không nhân lên theo số tài khoản:
       * một URL callback, một verify token, một nút đăng ký webhook hàng loạt.
       * Chỉ "Xác minh provider" là thật sự riêng theo từng Trang. */
      const url_chung = callbackTheoKenh(channel);
      const cho_xac_minh = items.filter((a) => a.status === "pending").length;
      const thanh_chung = url_chung ? `<div class="channel-card__chung">
        <code class="callback" title="Khai đúng MỘT lần bên nhà cung cấp">${esc(url_chung)}</code>
        ${KENH_META.includes(channel) && items.length ? `
          <span class="channel-card__actions">
            <button type="button" class="btn btn--sm" data-verifytoken-kenh="${items[0].id}">Xem verify token</button>
            ${cho_xac_minh ? `<button type="button" class="btn btn--sm btn--go" data-subwebhook-all="${channel}">Nhận tin cho tất cả (${cho_xac_minh})</button>` : ""}
          </span>
          <div class="token-slot" data-tokenslot="${items[0].id}"></div>` : ""}
      </div>` : "";

      return `<section class="channel-card">
      <div class="channel-card__head">${srcBadge(channel)}<div><h3>${esc(CHANNEL_LABEL[channel])}</h3><p>${items.length} tài khoản</p></div>
        <span class="channel-card__count">${items.length}</span></div>
      ${thanh_chung}
      <div class="channel-card__body${items.length > SO_HIEN_SAN ? " is-thu-gon" : ""}"
           data-body="${channel}">${items.length ? items.map((account) => {
        const callback = connectionCallback(account);
        return `<article class="account-line">
          <span class="health-dot health-dot--${esc(account.status)}"></span>
          <div><b>${esc(account.display_name)}</b><small>${esc(account.external_account_id || "Chưa có provider ID")}</small>
            ${account.ly_do_hong
              /* Lý do NẰM LẠI trên thẻ. Toast báo xong là biến mất, nên
                 người mở dashboard sáng hôm sau chỉ thấy một chữ vàng
                 trống rỗng và không biết phải làm gì. */
              ? `<span class="row__sub row__sub--loi">${esc(account.ly_do_hong)}</span>`
              : ""}
            ${callback ? `<code class="callback" title="Callback URL">${esc(callback)}</code>` : ""}</div>
          <span class="status-pill status-pill--${esc(account.status)}">${esc(ACCOUNT_STATUS_LABEL[account.status] || account.status)}</span>
          <div class="token-slot" data-tokenslot="${account.id}"></div>
          <div class="account-actions">
            ${account.channel === "zalo_personal" ? `<button class="btn btn--sm" data-qr="${account.id}">Quét QR</button>` : ""}
            ${["facebook", "instagram"].includes(account.channel) && account.status === "pending" ? `<button class="btn btn--sm" data-subwebhook="${account.id}">Nhận tin</button>` : ""}
            ${account.status !== "active" ? `<button class="btn btn--sm" data-verify="${account.id}">Xác minh provider</button>` : `<button class="btn btn--sm" data-disable="${account.id}">Tạm ngắt</button>`}
            <button class="btn btn--sm btn--halt" data-xoa-tk="${account.id}"
              data-ten-tk="${esc(account.display_name)}">Xoá</button>
          </div>
        </article>`;
      }).join("") : '<p class="empty">Chưa kết nối tài khoản nào.</p>'}</div>
      ${items.length > SO_HIEN_SAN ? `<button type="button" class="channel-card__them" data-mo="${channel}"
        data-them="Xem thêm ${items.length - SO_HIEN_SAN} tài khoản" data-bot="Thu gọn">
        Xem thêm ${items.length - SO_HIEN_SAN} tài khoản</button>` : ""}
    </section>`;
    }).join("");

/* Mã lỗi một mình KHÔNG hành động được.
 *
 * `provider.unreachable` đúng cho cả "sidecar chưa bật" lẫn "mạng chết"
 * lẫn "token hết hạn" — ba việc phải làm hoàn toàn khác nhau. Máy chủ đã
 * trả kèm `detail.ly_do` từ bản vá trước; giao diện thì vứt đi và chỉ hiện
 * cái mã.
 *
 * Hậu quả đo được: người dùng thấy "provider.unreachable", không biết làm
 * gì, phải hỏi — trong khi câu trả lời "sidecar không phản hồi" đã nằm sẵn
 * trong chính phản hồi ấy. */
const GOI_Y_LOI = {
  "provider.unreachable": "Kiểm tra dịch vụ đó đã chạy chưa.",
  "provider.unauthorized": "Credential sai hoặc đã hết hạn — nhập lại.",
  "provider.rejected": "Provider từ chối. Xem lý do bên dưới.",
  "provider.invalid_response": "Provider trả về dữ liệu lạ.",
};

function lyDoKetNoi(kq) {
  const ly_do = kq && kq.detail && kq.detail.ly_do;
  const goi_y = GOI_Y_LOI[kq && kq.code] || "";
  /* Giữ CẢ mã: người vận hành đọc lý do, còn mã là thứ tra được trong tài
     liệu và nhắn cho người khác. Bỏ mã đi là mất đường tra cứu. */
  return [kq && kq.code, ly_do, goi_y].filter(Boolean).join(" — ");
}

  $$('[data-verify]').forEach((button) => button.addEventListener("click", async () => {
    try {
      const result = await api(`/channel-accounts/${button.dataset.verify}/verify`, { method: "POST" });
      toast(result.ok ? "Provider đã xác minh; tài khoản sẵn sàng."
                      : `Chưa xác minh được: ${lyDoKetNoi(result)}`, !result.ok);
      loadKetNoi();
    } catch (e) { toast(e.message, true); }
  }));
  $$('[data-disable]').forEach((button) => button.addEventListener("click", async () => {
    try { await api(`/channel-accounts/${button.dataset.disable}/disable`, { method: "POST" }); toast("Đã tạm ngắt tài khoản."); loadKetNoi(); }
    catch (e) { toast(e.message, true); }
  }));

  /* XOÁ TÀI KHOẢN KÊNH.
   *
   * Hỏi máy chủ TRƯỚC xem có xoá được không, rồi mới hiện hộp thoại. Bấm
   * Xoá rồi mới nhận lỗi "còn 12 hội thoại" là bắt người dùng thử để biết
   * — trong khi máy chủ biết câu trả lời từ trước.
   *
   * Lịch sử khách KHÔNG bao giờ bị xoá theo: lược đồ khai `ON DELETE
   * RESTRICT` cho hội thoại, danh tính khách, tin chờ gửi và webhook. */
  $$("[data-xoa-tk]").forEach((button) => button.addEventListener("click", async () => {
    const id = button.dataset.xoaTk;
    const ten = button.dataset.tenTk || "tài khoản này";
    let truoc;
    try {
      truoc = await api("/channel-accounts/" + id + "/co-xoa-duoc");
    } catch (e) { toast(e.message, true); return; }

    if (!truoc.xoa_duoc) {
      alert(
        `Không xoá được "${ten}".\n\n` +
        `Còn ${truoc.dang_giu.join(", ")}.\n\n` +
        "Lịch sử khách không bị xoá theo tài khoản — đó là bằng chứng của " +
        'cửa hàng. Dùng nút "Tạm ngắt" để ngừng kênh mà vẫn giữ dữ liệu.');
      return;
    }
    if (!confirm(
        `Xoá hẳn "${ten}" khỏi hệ thống?\n\n` +
        "Credential đã lưu sẽ bị xoá theo và không khôi phục được.\n" +
        "Tài khoản này chưa có hội thoại nào nên không mất lịch sử.")) return;

    try {
      await api("/channel-accounts/" + id, { method: "DELETE" });
      toast("Đã xoá \"" + ten + "\"");
      loadKetNoi();
    } catch (e) { toast(e.message, true); }
  }));
  /* Mở rộng và THU GỌN LẠI — cùng một nút.
   *
   * Bản trước nút tự xoá sau khi mở, nên muốn thu lại phải tải cả trang. Mở
   * ra mà không đóng lại được thì lần sau người ta ngại bấm.
   *
   * Bật/tắt class thay vì đặt chiều cao: để CSS quyết định cách hiện, JS chỉ
   * nói trạng thái. */
  $$("[data-mo]").forEach((button) => button.addEventListener("click", () => {
    const than = document.querySelector(`[data-body="${button.dataset.mo}"]`);
    if (!than) return;
    const dang_thu_gon = than.classList.toggle("is-thu-gon");
    button.textContent = dang_thu_gon ? button.dataset.them : button.dataset.bot;
    // Thu lại thì kéo mắt về đầu kênh, nếu không người dùng đang đứng giữa
    // danh sách sẽ thấy màn hình nhảy mà không hiểu vì sao.
    if (dang_thu_gon) than.scrollIntoView({ block: "nearest" });
  }));

  $$('[data-qr]').forEach((button) => button.addEventListener("click", () => quetQR(button.dataset.qr)));

  /*
   * Đăng ký Trang vào webhook — bước quyết định có NHẬN được tin hay không.
   *
   * Có token là gửi tin đi được ngay, nên Trang trông như đã xong. Nhận tin
   * thì cần đăng ký riêng. Trang nối trước khi hệ thống biết làm bước này
   * vẫn đang treo, và không có gì trên màn hình nói ra điều đó — nút này là
   * đường chữa mà không phải gỡ ra nối lại (gỡ là mất lịch sử hội thoại).
   */
  /*
   * Đăng ký webhook cho TẤT CẢ Trang còn chờ, một lần bấm.
   *
   * 26 Trang bấm tay từng cái là việc không ai làm hết được — và bỏ dở giữa
   * chừng thì những Trang chưa bấm im lặng không nhận tin nào.
   *
   * Chạy TUẦN TỰ chứ không bắn song song: Graph giới hạn tần suất, và 26 lời
   * gọi cùng lúc là cách chắc chắn nhất để bị chặn rồi phải làm lại từ đầu.
   */
  $$("[data-subwebhook-all]").forEach((button) => button.addEventListener("click", async () => {
    const kenh = button.dataset.subwebhookAll;
    const cho = (await api("/channel-accounts"))
      .filter((a) => a.channel === kenh && a.status === "pending");
    if (!cho.length) { toast("Không còn Trang nào chờ."); return; }

    button.disabled = true;
    const chu_cu = button.textContent;
    const hong = [];
    let xong = 0;

    for (const [i, tk] of cho.entries()) {
      button.textContent = `Đang đăng ký ${i + 1}/${cho.length}...`;
      try {
        await api(`/channel-accounts/${tk.id}/dang-ky-webhook`, { method: "POST" });
        xong += 1;
      } catch (e) {
        hong.push(`${tk.display_name}: ${e.message}`);
      }
    }

    button.disabled = false;
    button.textContent = chu_cu;

    /* NÓI RA phần hỏng, không gộp vào một chữ "xong".
     *
     * Báo "đã đăng ký 26 Trang" trong khi 4 Trang lỗi là xanh giả: người
     * dùng đóng màn hình, yên tâm, rồi vài ngày sau mới biết bốn Trang đó
     * chưa từng nhận tin nào. */
    if (hong.length) {
      toast(`${xong} Trang đã đăng ký. ${hong.length} Trang HỎNG — xem mục Nhật ký.`, true);
      // Danh sách đầy đủ ra console: toast không đủ chỗ cho 4 dòng lý do,
      // mà lý do mới là thứ nói được vì sao Trang đó hỏng.
      console.warn("Trang đăng ký webhook thất bại:", hong);
    } else {
      toast(`${xong} Trang đã đăng ký webhook — tin khách sẽ về từ giờ.`);
    }
    loadKetNoi();
  }));

  $$("[data-subwebhook]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    const chu = button.textContent;
    button.textContent = "Đang đăng ký...";
    try {
      const r = await api(`/channel-accounts/${button.dataset.subwebhook}/dang-ky-webhook`,
                          { method: "POST" });
      toast(`${r.trang} đã đăng ký webhook — tin khách sẽ về từ giờ.`);
    } catch (e) {
      toast(e.message, true);
    } finally {
      button.disabled = false;
      button.textContent = chu;
    }
  }));

  /*
   * Xem verify token để dán sang Meta.
   *
   * KHÔNG hiện sẵn trên thẻ: màn hình Kết nối là chỗ người ta hay chụp lại
   * để hỏi nhau, và một chuỗi bí mật nằm sẵn ở đó sẽ đi theo mọi ảnh chụp.
   * Bấm mới hiện, và hiện ngay tại chỗ chứ không mở cửa sổ mới.
   *
   * Chỉ verify token được ra khỏi vault — access token và app secret thì
   * không, vì hai cái đó lộ là mất Trang. Xem agent/api/channel_accounts.py.
   */
  $$("[data-verifytoken], [data-verifytoken-kenh]").forEach((button) => button.addEventListener("click", async () => {
    // Verify token dùng CHUNG cho mọi Trang của cùng một app — nên nút ở mức
    // kênh chỉ cần hỏi một tài khoản bất kỳ trong kênh đó.
    const id = button.dataset.verifytoken || button.dataset.verifytokenKenh;
    const cho = document.querySelector(`[data-tokenslot="${id}"]`);
    button.disabled = true;
    try {
      const r = await api(`/channel-accounts/${id}/verify-token`);
      if (cho) {
        cho.innerHTML = `<code class="token-hien">${esc(r.verify_token)}</code>`
          + '<button type="button" class="btn btn--sm" data-copytoken>Chép</button>';
        cho.querySelector("[data-copytoken]").addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(r.verify_token);
            toast("Đã chép. Dán vào ô \"Xác minh mã\" bên Meta.");
          } catch {
            // Trình duyệt chặn clipboard khi trang không chạy HTTPS —
            // chuỗi vẫn hiện trên màn hình nên người dùng bôi đen chép tay.
            toast("Không chép tự động được. Bôi đen chuỗi rồi chép tay.", true);
          }
        });
      }
    } catch (e) {
      toast(e.message, true);
    } finally {
      button.disabled = false;
    }
  }));
}

/*
 * Quét QR Zalo cá nhân.
 *
 * VÌ SAO PHẢI HỎI LẠI, KHÔNG DÙNG NGAY PHẢN HỒI CỦA /qr
 * ------------------------------------------------------
 * Sidecar trả lời `login-qr` NGAY khi nhận việc, còn ảnh QR thì tới sau —
 * nó đến qua callback của thư viện Zalo vài trăm mili giây sau đó. Nên lúc
 * `/qr` trả về, `qr_image` luôn null.
 *
 * Bản trước đọc đúng phản hồi ấy rồi hiện toast "chờ sidecar cập nhật trạng
 * thái" và dừng lại. Người dùng nhìn một dòng chữ, không có gì để quét, và
 * không có gì gợi ý bước tiếp theo — nút bấm xong coi như hỏng.
 *
 * Ảnh nằm ở `/status`. Hỏi lại theo nhịp cho tới khi có ảnh, rồi tiếp tục
 * hỏi cho tới khi phiên `connected` để đóng khung lại đúng lúc.
 */
const QR_NHIP_MS = 2000;
const QR_TOI_DA_LUOT = 60;          // ~2 phút, dài hơn hạn sống của một mã QR

async function quetQR(accountId) {
  const khung = $("#qrbox");
  if (khung) khung.remove();
  document.body.insertAdjacentHTML("beforeend", `
    <div class="qrbox" id="qrbox">
      <div class="qrbox__panel">
        <h3>Quét bằng ứng dụng Zalo</h3>
        <div id="qrslot"><p class="empty">Đang xin mã từ sidecar…</p></div>
        <p class="qrbox__hint">Mở Zalo trên điện thoại → Thêm → Quét mã QR</p>
        <button type="button" class="btn" id="qrclose">Đóng</button>
      </div>
    </div>`);
  const dong = () => { const b = $("#qrbox"); if (b) b.remove(); loadKetNoi(); };
  $("#qrclose").addEventListener("click", dong);

  const slot = () => $("#qrslot");
  try {
    await api(`/channel-accounts/${accountId}/zalo-personal/qr`, { method: "POST" });
  } catch (e) {
    if (slot()) slot().innerHTML = `<p class="empty">Không xin được mã: ${esc(e.message)}</p>`;
    return;
  }

  let daHienAnh = false;
  for (let luot = 0; luot < QR_TOI_DA_LUOT; luot += 1) {
    if (!$("#qrbox")) return;                 // người dùng đã đóng khung
    await new Promise((r) => setTimeout(r, QR_NHIP_MS));
    let st;
    try { st = await api(`/channel-accounts/${accountId}/zalo-personal/status`); }
    catch (e) { continue; }                   // sidecar bận, thử lại nhịp sau

    if (st.qr_image && !daHienAnh) {
      daHienAnh = true;
      // Sidecar trả ảnh dạng base64 thuần hoặc đã có tiền tố data:.
      const src = String(st.qr_image).startsWith("data:")
        ? st.qr_image : `data:image/png;base64,${st.qr_image}`;
      if (slot()) slot().innerHTML = `<img alt="Mã QR đăng nhập Zalo" src="${esc(src)}">`;
    }
    if (st.status === "qr_scanned" && slot()) {
      slot().innerHTML = '<p class="empty">Đã quét. Đang xác nhận trên điện thoại…</p>';
    }
    if (st.status === "connected") {
      toast("Đã kết nối Zalo cá nhân. Phiên được lưu mã hoá trong vault.");
      dong();
      return;
    }
    if (st.status === "qr_expired") {
      if (slot()) slot().innerHTML = '<p class="empty">Mã QR hết hạn. Đóng rồi bấm Quét QR lại.</p>';
      return;
    }
  }
  if (slot()) slot().innerHTML = '<p class="empty">Hết thời gian chờ. Đóng rồi thử lại.</p>';
}

/*
 * Kết nối tài khoản kênh — mỗi kênh một bộ trường riêng.
 *
 * VÌ SAO KHÔNG DÙNG CHUNG MỘT FORM CHO SÁU KÊNH
 * ----------------------------------------------
 * Bản đầu hiện đủ sáu ô cho mọi kênh, với nhãn gộp kiểu "Refresh token /
 * sidecar secret / widget secret". Người vận hành phải tự đoán ô nào dành
 * cho kênh mình, và bốn ô để trống mà không có gì nói ra điều đó.
 *
 * Nối tài khoản là việc làm MỘT LẦN cho mỗi kênh, với những chuỗi dài
 * giống hệt nhau. Sai ở đây không nổ: credential vẫn được mã hoá, tài
 * khoản vẫn hiện trên dashboard, chỉ có tin khách là không bao giờ tới —
 * và có thể nhiều ngày sau mới ai đó nhận ra.
 *
 * Ba lớp chặn ba kiểu sai khác nhau:
 *   1. chỉ hiện ô kênh đó cần   -> không dán nhầm ô
 *   2. nhãn + chỉ dẫn lấy ở đâu -> không dán nhầm giá trị
 *   3. cắt khoảng trắng thừa    -> không hỏng vì một dấu cách vô hình
 *
 * Lớp 3 nghe vặt nhưng là lỗi kinh điển: copy từ trang web thường dính
 * khoảng trắng cuối, sai một byte là HMAC hỏng, và thông báo lỗi của
 * provider không bao giờ nói "bạn thừa một dấu cách".
 */
const KENH_TRUONG = {
  zalo_personal: {
    // KHÔNG hỏi gì cả — chỉ cần đặt tên rồi quét QR.
    //
    // Trước đây ô này bắt người dùng "mở file .env copy dòng
    // ZALO_SIDECAR_SECRET". Nhưng đó là bí mật của MÁY CHỦ: mọi tài khoản
    // Zalo dùng chung một giá trị, và người dùng không có `.env` để mở.
    // Máy chủ tự điền — xem agent/omnichannel/bi_mat_may_chu.py
    truong: [],
    ke_tiep: 'Lưu xong, bấm "Quét QR" trên thẻ tài khoản rồi quét bằng app Zalo.',
  },
  zalo_oa: {
    truong: [
      { o: "external_account_id", nhan: "OA ID", bat_buoc: true,
        goi_y: "Zalo OA Console → Thông tin OA → OA ID" },
      { o: "app_id", nhan: "App ID", bat_buoc: true,
        goi_y: "Zalo Developers → Ứng dụng của bạn → App ID" },
      { o: "app_secret", nhan: "Secret key", bat_buoc: true,
        goi_y: "Zalo Developers → Ứng dụng → Secret Key" },
      { o: "secondary_secret", nhan: "Refresh token", bat_buoc: true,
        goi_y: "Zalo OA Console → sau khi cấp quyền cho ứng dụng, lấy Refresh Token" },
    ],
    ke_tiep: "Cần URL HTTPS công khai để Zalo gọi webhook vào.",
  },
  facebook: {
    dang_nhap: true,
    truong: [
      { o: "external_account_id", nhan: "Page ID", bat_buoc: true,
        goi_y: "Meta Business → Trang của bạn → Giới thiệu → ID trang" },
      { o: "access_token", nhan: "Page access token", bat_buoc: true,
        goi_y: "Meta App Dashboard → Messenger → Settings → Generate Token cho đúng Trang" },
      { o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret" },
      { o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT. Phải dán đúng chuỗi này vào Meta khi đăng ký webhook" },
    ],
    ke_tiep: "Cần URL HTTPS công khai, rồi đăng ký webhook trong Meta App Dashboard.",
  },
  instagram: {
    dang_nhap: true,
    truong: [
      { o: "external_account_id", nhan: "Instagram business ID", bat_buoc: true,
        goi_y: "Meta App Dashboard → Instagram → Instagram Business Account ID" },
      { o: "access_token", nhan: "Access token", bat_buoc: true,
        goi_y: "Cùng token với Trang Facebook đã liên kết Instagram" },
      { o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret" },
      { o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT, dùng chung với webhook Meta" },
    ],
    ke_tiep: "Instagram phải là tài khoản Business và đã liên kết một Trang Facebook.",
  },
  whatsapp: {
    truong: [
      { o: "external_account_id", nhan: "Phone number ID", bat_buoc: true,
        goi_y: "Meta App Dashboard → WhatsApp → API Setup → Phone number ID (KHÔNG phải số điện thoại)" },
      { o: "access_token", nhan: "Access token", bat_buoc: true,
        goi_y: "Meta App Dashboard → WhatsApp → API Setup → Temporary/Permanent token" },
      { o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret" },
      { o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT, dùng chung với webhook Meta" },
    ],
    ke_tiep: "Cần URL HTTPS công khai để Meta gọi webhook vào.",
  },
  webchat: {
    truong: [
      { o: "external_account_id", nhan: "Khoá website", bat_buoc: true,
        goi_y: "Tên ngắn không dấu để phân biệt từng website, ví dụ: web-chinh" },
      { o: "secondary_secret", nhan: "Widget secret", bat_buoc: true,
        goi_y: "Bạn tự đặt — chuỗi ngẫu nhiên từ 32 ký tự. Dùng để ký phiên của widget" },
    ],
    ke_tiep: "Chạy được ngay, không cần HTTPS công khai khi thử tại chỗ.",
  },
};

const O_CREDENTIAL = [
  "external_account_id", "app_id", "access_token",
  "app_secret", "verify_token", "secondary_secret",
];

function veFormKenh(kenh) {
  const cau_hinh = KENH_TRUONG[kenh];
  if (!cau_hinh) return;
  const theo_o = new Map(cau_hinh.truong.map((t) => [t.o, t]));

  for (const ten of O_CREDENTIAL) {
    const input = document.querySelector(`#connectionform [name="${ten}"]`);
    if (!input) continue;
    const khung = input.closest(".field");
    const dung = theo_o.get(ten);

    khung.classList.toggle("is-hidden", !dung);
    input.required = Boolean(dung && dung.bat_buoc);
    if (!dung) { input.value = ""; continue; }

    khung.querySelector("span").textContent =
      dung.nhan + (dung.bat_buoc ? "" : " (không bắt buộc)");

    // Chỉ dẫn lấy giá trị ở đâu. Không có nó thì người vận hành rời
    // dashboard đi tìm, quay lại dán nhầm ô — hoặc bỏ dở giữa chừng.
    let goi_y = khung.querySelector(".field__goiy");
    if (!goi_y) {
      goi_y = document.createElement("small");
      goi_y.className = "field__goiy";
      khung.appendChild(goi_y);
    }
    goi_y.textContent = dung.goi_y;
  }

  /* Kênh nối được bằng đăng nhập thì ĐỪNG đòi dán token.
   *
   * Màn hình cũ có nút "Kết nối bằng đăng nhập" ở trên và ngay dưới là bốn ô
   * token bắt buộc cho đúng kênh đó — hai thứ nói ngược nhau, và người dùng
   * làm theo cái dễ đọc hơn là form trước mắt.
   *
   * Đi đường dán tay không chỉ mất thời gian: token dán tay KHÔNG tự gia
   * hạn, nên vài tuần sau kênh chết câm mà không ai biết cho tới khi khách
   * kêu. Và `app_secret` phải đi qua trình duyệt, trong khi đường đăng nhập
   * giữ nó ở máy chủ suốt.
   *
   * Không xoá hẳn ô nhập tay: vẫn có ca cần khi app Meta chưa được duyệt,
   * hoặc khi gỡ lỗi. Nó thành đường phụ, đóng sẵn.
   */
  const khoi_tay = $("#nhap-tay");
  const nhac = $("#khuyen-dang-nhap");
  if (khoi_tay && nhac) {
    if (cau_hinh.dang_nhap) {
      khoi_tay.open = false;
      khoi_tay.querySelector("summary").textContent =
        "Nhập thủ công (nâng cao — chỉ khi không dùng được đăng nhập)";
      nhac.textContent = "Kênh này nối bằng nút \"Kết nối Facebook / Instagram "
        + "bằng đăng nhập\" ở trên: chọn Trang, hệ thống tự nhận token và tự "
        + "gia hạn. Chỉ mở phần nhập thủ công khi bạn có lý do riêng.";
      nhac.classList.remove("is-hidden");
    } else {
      khoi_tay.open = true;
      khoi_tay.querySelector("summary").textContent = "Thông tin kết nối";
      nhac.classList.add("is-hidden");
    }
  }

  /* Ô `required` nằm trong `<details>` đang ĐÓNG thì trình duyệt chặn gửi
   * form mà không hiện được lỗi ở đâu — người dùng bấm Lưu và không có gì
   * xảy ra. Kênh có đường đăng nhập thì bỏ `required` hết; phần kiểm thiếu
   * trường vẫn chạy ở `luuKetNoi`, nơi báo được bằng toast. */
  if (cau_hinh.dang_nhap) {
    for (const ten of O_CREDENTIAL) {
      const input = document.querySelector(`#connectionform [name="${ten}"]`);
      if (input) input.required = false;
    }
  }

  const chan = $("#connection-ketiep");
  if (chan) chan.textContent = cau_hinh.ke_tiep || "";
}

$('#connectionform [name="channel"]')?.addEventListener("change", (ev) =>
  veFormKenh(ev.target.value)
);
if ($("#connectionform")) veFormKenh($('#connectionform [name="channel"]').value);

$("#connectionform")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const tho = Object.fromEntries(new FormData(ev.target));
  // Cắt khoảng trắng cho MỌI giá trị, không riêng token: tên hiển thị dính
  // dấu cách đầu dòng cũng làm danh sách tài khoản trông lệch.
  const form = {};
  for (const [k, v] of Object.entries(tho)) form[k] = String(v ?? "").trim();

  const cau_hinh = KENH_TRUONG[form.channel];
  const thieu = (cau_hinh?.truong || [])
    .filter((t) => t.bat_buoc && !form[t.o])
    .map((t) => t.nhan);
  if (thieu.length) {
    /* Kênh có đường đăng nhập mà người dùng bấm Lưu với ô trống thì gần như
     * chắc chắn họ đang ở nhầm chỗ. Liệt kê bốn token còn thiếu là đẩy họ đi
     * tìm những chuỗi mà hệ thống tự lấy được. */
    toast(cau_hinh?.dang_nhap
      ? 'Kênh này nối bằng nút "Kết nối Facebook / Instagram bằng đăng nhập" ở trên.'
      : "Còn thiếu: " + thieu.join(", "), true);
    return;
  }

  const credentials = {};
  for (const key of ["app_id", "access_token", "verify_token"]) {
    if (form[key]) credentials[key] = form[key];
  }
  if (form.app_secret) {
    if (form.channel === "zalo_oa") credentials.secret_key = form.app_secret;
    else credentials.app_secret = form.app_secret;
  }
  if (form.secondary_secret) {
    if (form.channel === "zalo_oa") credentials.refresh_token = form.secondary_secret;
    else if (form.channel === "webchat") credentials.widget_secret = form.secondary_secret;
  }

  let account;
  try {
    account = await api("/channel-accounts", { method: "POST", body: JSON.stringify({
      channel: form.channel, display_name: form.display_name,
      external_account_id: form.external_account_id || null,
      capabilities: { send_text: true, receive_message: true }, metadata: {}, credentials,
    }) });
  } catch (e) { toast(e.message, true); return; }

  ev.target.reset();
  veFormKenh($('#connectionform [name="channel"]').value);
  $("#connection-create").classList.add("is-hidden");

  // XÁC MINH NGAY, không đợi người bấm nút riêng.
  //
  // Lưu xong mà không kiểm thì người dùng tưởng đã xong. Credential sai chỉ
  // lộ ra khi khách nhắn mà không ai nhận — có thể nhiều ngày sau, và lúc
  // đó không ai còn nhớ mình đã dán gì vào đâu.
  //
  // Zalo cá nhân là ngoại lệ: nó chưa có gì để xác minh cho tới khi quét QR.
  if (form.channel === "zalo_personal") {
    toast('Đã lưu. Bấm "Quét QR" trên thẻ tài khoản để đăng nhập Zalo.');
    loadKetNoi();
    return;
  }
  try {
    await api(`/channel-accounts/${account.id}/verify`, { method: "POST" });
    toast("Đã lưu và xác minh xong với provider.");
  } catch (e) {
    toast("Đã lưu, nhưng provider từ chối: " + e.message + " — kiểm lại credential.", true);
  }
  loadKetNoi();
});


/*
 * Kết nối Facebook/Instagram bằng ĐĂNG NHẬP.
 *
 * Mở cửa sổ mới thay vì chuyển hướng cả trang: người dùng đang ở giữa việc
 * cấu hình, và kéo họ ra khỏi dashboard rồi thả về là mất ngữ cảnh. Cửa sổ
 * con tự đóng và tự làm mới trang cha khi xong.
 */
$("#btn-oauth-meta")?.addEventListener("click", async () => {
  const nut = $("#btn-oauth-meta");
  nut.disabled = true;
  try {
    const r = await api("/connect/meta/start");
    if (!r.url) throw new Error("Máy chủ không trả về địa chỉ đăng nhập");
    // Mở TRƯỚC khi await gì thêm: trình duyệt chỉ cho mở cửa sổ mới trong
    // nhịp xử lý cú bấm, chờ lâu là bị chặn pop-up.
    const cua_so = window.open(r.url, "ketnoi_meta", "width=620,height=740");
    if (!cua_so) {
      toast("Trình duyệt đã chặn cửa sổ. Cho phép pop-up rồi thử lại.", true);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    nut.disabled = false;
  }
});

/* ---------------- kỹ năng (skill) và plugin ---------------- */

const RUI_RO_NHAN = { doc: "đọc", ghi_nhan: "ghi nhận", hanh_dong: "HÀNH ĐỘNG" };
const NHOM_NHAN = {
  tu_van: "Tư vấn", don_hang: "Đơn hàng", sau_ban: "Sau bán",
  marketing: "Marketing", con_nguoi: "Con người",
};

/* Mẫu cấu hình cho từng loại. Ô cấu hình là JSON, và JSON gõ tay từ đầu thì
 * ai cũng gõ sai lần đầu — điền sẵn mẫu đúng thì người vận hành SỬA chứ
 * không VIẾT, và đó là khác biệt giữa dùng được và bỏ đó. */
const PLUGIN_MAU = {
  /* Khoá mẫu phải ĐỦ RIÊNG, và đây không phải chuyện thẩm mỹ.
   *
   * Mẫu cũ dùng khoá "serum". Danh mục cửa hàng này có BỐN sản phẩm chứa
   * chữ ấy, nên một dòng "serum" trả lời thay cho cả bốn — chắc nịch, không
   * mơ hồ, nên cũng không có nhánh hỏi lại nào chạy. Người vận hành SỬA mẫu
   * chứ không VIẾT lại, nên mẫu xấu là cái bẫy được nhân bản.
   *
   * `ban_mo_ta.khoa_long_nhau` nay chặn khoá lồng nhau lúc lưu, nhưng mẫu
   * vẫn nên dạy đúng ngay từ đầu thay vì đợi bị từ chối. */
  tra_bang: '{\n  "bang": {\n    "Kem Chống Nắng": "12 tháng sau khi mở nắp",\n    "Sữa Rửa Mặt": "12 tháng sau khi mở nắp"\n  }\n}',
  tra_tai_lieu: '{\n  "nhom_tai_lieu": "bao-hanh",\n  "k": 4\n}',
  chuyen_chuyen_biet: '{\n  "ly_do": "Khách hỏi hợp tác bán buôn"\n}',
  goi_api_doc: '{\n  "url": "https://noi-bo.example.com/tra/{ma}",\n  "han_giay": 5\n}',
};

async function loadKyNang() {
  const d = await api("/ky-nang");
  const tat = d.co_san.filter((k) => !k.bat).length;
  $("#c-kynang").textContent = tat ? `${tat} tắt` : "";

  $("#kynang-cosan").innerHTML = d.co_san.map((k) => `<div class="row">
      <span class="row__flag ${k.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(k.ten)}
          ${k.muc_rui_ro === "hanh_dong" ? '<b class="pill pill--halt">HÀNH ĐỘNG</b>' : ""}
          ${k.tat_duoc ? "" : '<b class="pill">không tắt được</b>'}</span>
        <span class="row__sub">${esc(NHOM_NHAN[k.nhom] || k.nhom)} ·
          ${esc(RUI_RO_NHAN[k.muc_rui_ro] || k.muc_rui_ro)}${
            k.can_erp ? " · cần ERP" : ""}${
            k.can_kho_tri_thuc ? " · cần kho tri thức" : ""}</span>
        <span class="row__sub">${esc(k.tom_tat)}</span>
        <span class="row__sub"><em>Tắt thì:</em> ${esc(k.tat_thi_mat_gi)}</span>
      </span>
      <span class="row__side">
        ${k.tat_duoc
          ? `<button type="button" class="btn btn--sm ${k.bat ? "btn--halt" : ""}"
               data-kynang="${esc(k.ten)}" data-bat="${k.bat ? "0" : "1"}">${
               k.bat ? "Tắt" : "Bật"}</button>`
          : ""}
      </span>
    </div>`).join("");

  $("#kynang-plugin").innerHTML = d.plugin.length
    ? d.plugin.map((p) => `<div class="row">
        <span class="row__flag row__flag--auto"></span>
        <span class="row__body">
          <span class="row__title">${esc(p.ten)}</span>
          <span class="row__sub">${esc(p.loai)}${
            p.tham_so.length ? " · tham số: " + esc(p.tham_so.join(", ")) : ""}</span>
          <span class="row__sub">${esc(p.mo_ta)}</span>
        </span>
        <span class="row__side">
          <button type="button" class="btn btn--sm btn--halt"
            data-plugin-xoa="${esc(p.ten)}">Xoá</button>
        </span>
      </div>`).join("")
    : `<p class="empty">Chưa có plugin nào. Tối đa ${d.plugin_toi_da}.</p>`;
}

/* Đọc form thành bản mô tả. Dùng chung cho nút "Chạy thử" và nút "Lưu" —
 * hai đường khác nhau đọc form theo hai cách là chạy thử một thứ rồi lưu
 * một thứ khác, và người vận hành không có cách nào biết. */
function docFormPlugin() {
  const f = $("#pluginform");
  const g = (n) => (f.elements[n]?.value || "").trim();
  let cau_hinh = {};
  const tho = g("cau_hinh");
  if (tho) {
    try {
      cau_hinh = JSON.parse(tho);
    } catch (e) {
      throw new Error("Ô cấu hình không phải JSON hợp lệ: " + e.message);
    }
  }
  const tham_so = [];
  if (g("tham_so_ten")) {
    tham_so.push({ ten: g("tham_so_ten"), mo_ta: g("tham_so_mo_ta"), bat_buoc: true });
  }
  return { ten: g("ten"), loai: g("loai"), mo_ta: g("mo_ta"), tham_so, cau_hinh };
}

$("#plugin-loai")?.addEventListener("change", (e) => {
  const o = $("#plugin-cauhinh");
  if (o && !o.value.trim()) o.value = PLUGIN_MAU[e.target.value] || "";
});

$("#plugin-thu")?.addEventListener("click", async () => {
  const hop = $("#plugin-ketqua");
  try {
    const bm = docFormPlugin();
    const args = {};
    if (bm.tham_so.length) {
      const v = prompt(`Giá trị thử cho tham số "${bm.tham_so[0].ten}":`, "");
      if (v === null) return;
      args[bm.tham_so[0].ten] = v;
    }
    const r = await api("/ky-nang/plugin/thu", {
      method: "POST",
      body: JSON.stringify({ ban_mo_ta: bm, args }),
    });
    hop.innerHTML = `<pre class="pre">${esc(JSON.stringify(r.ket_qua, null, 2))}</pre>`;
  } catch (e) {
    hop.innerHTML = `<p class="empty">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
});

$("#pluginform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/ky-nang/plugin", {
      method: "POST",
      body: JSON.stringify(docFormPlugin()),
    });
    e.target.reset();
    $("#plugin-ketqua").innerHTML = "";
    toast("Đã lưu và bật plugin");
    await loadKyNang();
  } catch (err) {
    toast(err.message, true);
  }
});

document.addEventListener("click", async (e) => {
  const bt = e.target.closest("[data-kynang]");
  if (bt) {
    const bat = bt.dataset.bat === "1";
    /* Xác nhận CHỈ khi tắt, không hỏi khi bật. Hỏi cả hai chiều thì hộp
     * thoại thành thói quen bấm OK, và lúc đó nó không còn chặn gì. */
    if (!bat && !confirm(
      `Tắt "${bt.dataset.kynang}"?\n\nAgent sẽ chuyển hội thoại cho người ` +
      `mỗi khi cần dùng kỹ năng này.`)) return;
    try {
      await api("/ky-nang/bat-tat", {
        method: "POST",
        body: JSON.stringify({ ten: bt.dataset.kynang, bat }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-plugin-xoa]");
  if (bx) {
    if (!confirm(`Xoá hẳn plugin "${bx.dataset.pluginXoa}"?`)) return;
    try {
      await api("/ky-nang/plugin/" + encodeURIComponent(bx.dataset.pluginXoa),
                { method: "DELETE" });
      toast("Đã xoá");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
  }
});

/* ---------------- ứng dụng nhúng (tích hợp) ---------------- */

async function loadTichHop() {
  const d = await api("/tich-hop/ung-dung");
  const ve = (a) => `<div class="row">
      <span class="row__flag ${a.xoa_duoc ? "row__flag--auto" : ""}"></span>
      <span class="row__body">
        <span class="row__title">${esc(a.nhan)}
          ${a.xoa_duoc ? "" : '<b class="pill">viết sẵn</b>'}</span>
        <span class="row__sub">${esc(a.dia_chi)}</span>
      </span>
      <span class="row__side">
        <a class="btn btn--sm" href="/tich-hop/${encodeURIComponent(a.ten)}/"
           target="_blank" rel="noopener">Mở</a>
        ${a.xoa_duoc
          ? `<button type="button" class="btn btn--sm btn--halt"
               data-tichhop-xoa="${esc(a.ten)}">Xoá</button>`
          : ""}
      </span>
    </div>`;
  $("#tichhop-ds").innerHTML =
    d.mac_dinh.map(ve).join("") + d.tu_them.map(ve).join("");
}

/* Đọc form một chỗ duy nhất, dùng chung cho "Thử" và "Lưu".
 * Hai đường đọc form theo hai cách là thử một thứ rồi lưu một thứ khác, và
 * người vận hành không có cách nào biết. */
function docFormTichHop() {
  const f = $("#tichhopform");
  const g = (n) => (f.elements[n]?.value || "").trim();
  return { ten: g("ten"), nhan: g("nhan") || g("ten"), dia_chi: g("dia_chi") };
}

$("#tichhop-thu")?.addEventListener("click", async () => {
  const hop = $("#tichhop-ketqua");
  try {
    const r = await api("/tich-hop/ung-dung/thu", {
      method: "POST",
      body: JSON.stringify(docFormTichHop()),
    });
    hop.innerHTML = r.noi_duoc
      ? `<p class="empty">Nối được ${esc(r.dia_chi)} — HTTP ${r.ma}.</p>`
      : `<p class="empty">Không nối được ${esc(r.dia_chi)}: ${esc(r.ly_do)}</p>`;
  } catch (e) {
    hop.innerHTML = `<p class="empty">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
});

$("#tichhopform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/tich-hop/ung-dung", {
      method: "POST",
      body: JSON.stringify(docFormTichHop()),
    });
    e.target.reset();
    $("#tichhop-ketqua").innerHTML = "";
    toast("Đã thêm ứng dụng nhúng");
    await loadTichHop();
  } catch (err) {
    toast(err.message, true);
  }
});

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-tichhop-xoa]");
  if (!b) return;
  if (!confirm(`Gỡ ứng dụng "${b.dataset.tichhopXoa}" khỏi dashboard?`)) return;
  try {
    await api("/tich-hop/ung-dung/" + encodeURIComponent(b.dataset.tichhopXoa),
              { method: "DELETE" });
    toast("Đã gỡ");
    await loadTichHop();
  } catch (err) { toast(err.message, true); }
});

/* ---------------- cấu hình agent ---------------- */

/* Ô nhập dựng theo `kieu` do máy chủ khai, không đoán từ giá trị.
 * Đoán từ giá trị thì `confidence_floor = 1` (số nguyên) sẽ ra ô checkbox,
 * và người vận hành mất luôn thanh trượt. */
function oNhapCauHinh(m) {
  const id = `ch-${m.khoa}`;
  if (m.kieu === "bool") {
    return `<label class="switch"><input type="checkbox" id="${id}"
      data-ch="${m.khoa}" data-kieu="bool" ${m.gia_tri ? "checked" : ""}>
      <span>${m.gia_tri ? "đang bật" : "đang tắt"}</span></label>`;
  }
  if (m.kieu === "chon") {
    return `<select id="${id}" data-ch="${m.khoa}" data-kieu="chon">${
      m.chon.map((c) => `<option value="${esc(c)}"${
        c === m.gia_tri ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  return `<input type="number" id="${id}" data-ch="${m.khoa}" data-kieu="so"
    min="${m.min}" max="${m.max}" step="${m.buoc}" value="${m.gia_tri}">
    ${m.don_vi ? `<span class="row__sub">${esc(m.don_vi)}</span>` : ""}`;
}

async function loadCauHinh() {
  const d = await api("/cau-hinh");
  const lech = d.muc.filter((m) => m.lech_mac_dinh).length;
  $("#c-cauhinh").textContent = lech ? `${lech} lệch` : "";

  $("#cauhinh-ds").innerHTML = d.muc.map((m) => `<div class="row">
      <span class="row__flag ${m.lech_mac_dinh ? "row__flag--halt" : "row__flag--auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.nhan)}
          ${m.lech_mac_dinh
            ? `<b class="pill">khác mặc định (${esc(String(m.mac_dinh))})</b>`
            : ""}</span>
        <span class="row__sub">${esc(m.y_nghia)}</span>
        <span class="row__sub"><em>Lưu ý:</em> ${esc(m.tat_thi)}</span>
      </span>
      <span class="row__side">${oNhapCauHinh(m)}</span>
    </div>`).join("");

  await loadLichSuCauHinh();
}

/* JSON thô trong nhật ký là thứ LẬP TRÌNH VIÊN đọc được, không phải người
 * trực ca. `{"mode":"auto","enabled":"True","zalo_account_id":null,...}` dài
 * 200 ký tự và chôn mất thứ duy nhất đáng nhìn: cái gì vừa đổi.
 *
 * Chỉ hiện những khoá NGƯỜI chỉnh được, bỏ phần còn lại. */
const NHAN_CAU_HINH = {
  enabled: "Công tắc agent",
  mode: "Chế độ trả lời",
  confidence_floor: "Ngưỡng tin cậy",
  max_cost_per_conversation: "Trần mỗi hội thoại",
  tran_chi_phi_ngay_usd: "Trần mỗi ngày",
};

function doiThayCauHinh(ct) {
  if (!ct || typeof ct !== "object") return "đặt lại về mặc định";
  const phan = Object.entries(NHAN_CAU_HINH)
    .filter(([k]) => ct[k] !== undefined && ct[k] !== null)
    .map(([k, nhan]) => `${nhan} = ${ct[k]}`);
  return phan.length ? phan.join(" · ") : "đặt lại về mặc định";
}

async function loadLichSuCauHinh() {
  const ls = await api("/cau-hinh/lich-su?limit=12");
  $("#cauhinh-lichsu").innerHTML = ls.length
    /* `.row` là lưới `3px minmax(0,1fr) auto`. Cột đầu LÀ dải màu — thiếu
       `.row__flag` thì `.row__body` rơi vào cột 3px và nội dung biến mất
       hoàn toàn. Nhìn ra là một danh sách toàn dòng trống. */
    ? ls.map((x) => `<div class="row">
        <span class="row__flag row__flag--auto"></span>
        <span class="row__body">
          <span class="row__title">${esc(x.boi || "?")}</span>
          <span class="row__sub">${esc(doiThayCauHinh(x.chi_tiet))}</span>
        </span>
        <span class="row__side"><span class="row__time">${clock(x.luc)}</span></span>
      </div>`).join("")
    : '<p class="empty">Chưa có thay đổi nào được ghi.</p>';
}

/* Gửi ngay khi đổi, không có nút Lưu riêng.
 * Nút Lưu riêng nghĩa là có một trạng thái "đã sửa nhưng chưa lưu" hiện
 * trên màn hình — và người vận hành đóng tab ở đúng trạng thái đó sẽ tin
 * là mình đã đổi. Gửi ngay thì thứ nhìn thấy luôn là thứ đang chạy. */
document.addEventListener("change", async (e) => {
  const el = e.target.closest("[data-ch]");
  if (!el) return;
  const kieu = el.dataset.kieu;
  const gt = kieu === "bool" ? el.checked
           : kieu === "so" ? Number(el.value)
           : el.value;
  try {
    await api("/runtime", {
      method: "POST",
      body: JSON.stringify({ [el.dataset.ch]: gt }),
    });
    toast("Đã lưu — có hiệu lực từ tin nhắn kế tiếp");
    await loadCauHinh();
  } catch (err) {
    toast(err.message, true);
    await loadCauHinh();
  }
});

$("#cauhinh-macdinh")?.addEventListener("click", async () => {
  if (!confirm("Quay về mặc định trong .env?\n\nMọi thiết lập đã lưu sẽ bị xoá."))
    return;
  try {
    await api("/cau-hinh/mac-dinh", { method: "POST" });
    toast("Đã quay về mặc định");
    await loadCauHinh();
  } catch (err) { toast(err.message, true); }
});


/* ---------------- cài đặt API ---------------- */

const API_NHOM = { model: "Model ngôn ngữ", erp: "ERP (ERPNext)", van_chuyen: "Vận chuyển (GHN)" };

/* Ô nhập cho một khoá. Ô BÍ MẬT là password và KHÔNG có value: giá trị
 * không có ở client để mà dựng — máy chủ chỉ gửi bốn ký tự cuối. */
function oNhapApi(m) {
  if (m.chon && m.chon.length) {
    return `<select data-api-khoa="${m.khoa}">${
      m.chon.map((c) => `<option value="${esc(c)}"${c === m.hien ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  if (m.bi_mat) {
    return `<input type="password" autocomplete="off" data-api-khoa="${m.khoa}"
      placeholder="${m.da_dat ? `đã đặt ${esc(m.hien)} — dán khoá mới để thay` : "chưa đặt — dán khoá vào đây"}">`;
  }
  return `<input type="text" data-api-khoa="${m.khoa}" value="${esc(m.hien || "")}"
    placeholder="${esc(m.nhan)}">`;
}

function trangThaiApi(m) {
  const nguon = { csdl: "từ dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  const kiem = m.kiem_ket_qua ? ` · kiểm ${new Date(m.kiem_luc).toLocaleString("vi-VN")}: ${esc(m.kiem_ket_qua)}` : "";
  return `<span class="row__sub">${nguon}${kiem}</span>`;
}

async function loadCaiDatApi() {
  const d = await api("/cai-dat-api");
  $("#api-vault").textContent = d.vault_san_sang ? "mã hoá AES-256 trong CSDL" : "vault chưa cấu hình — chỉ xem được";
  const nhom = {};
  for (const m of d.muc) (nhom[m.nhom] ||= []).push(m);
  $("#api-nhom").innerHTML = Object.entries(API_NHOM).map(([ma, ten]) => `
    <div class="row" data-api-nhom="${ma}">
      <span class="row__flag ${(nhom[ma] || []).some((m) => m.da_dat) ? "row__flag--auto" : ""}"></span>
      <span class="row__body">
        <span class="row__title">${esc(ten)}</span>
        ${(nhom[ma] || []).map((m) => {
          // Tách riêng biến này: giá trị từ máy chủ chỉ được nhắc tới trong
          // template SAU khi đã qua esc() — không để điều kiện rẽ nhánh nằm
          // ngay trong dấu ${...} kèm giá trị thô.
          const yNghia = m.y_nghia ? ` — ${esc(m.y_nghia)}` : "";
          return `<div class="rows" style="margin:.35rem 0" data-api-row="${esc(m.khoa)}">
          <label class="row__sub">${esc(m.nhan)}${yNghia}</label>
          ${oNhapApi(m)} ${trangThaiApi(m)}
        </div>`;
        }).join("")}
        <div class="rowbtns">
          <button type="button" class="btn btn--sm" data-api-kiem="${ma}">Kiểm tra</button>
          <button type="button" class="btn btn--sm btn--go" data-api-luu="${ma}">Lưu</button>
          <span class="row__sub" data-api-kq="${ma}"></span>
        </div>
      </span>
    </div>`).join("");
  hienODungProvider();
}

/* Provider nào cần khoá nào. gemini/vertex xác thực qua gcloud trên máy,
 * không có khoá nào để nhập — nên không có mục nào trong bảng này. */
const API_KHOA_THEO_PROVIDER = { gemini_api: "GEMINI_API_KEY", anthropic: "ANTHROPIC_API_KEY" };

/* Chỉ hiện ô khoá của provider đang chọn.
 *
 * Hiện cả hai ô là mời người ta dán khoá Anthropic trong khi provider là
 * gemini_api: khoá lưu đúng, nút Kiểm tra báo đúng, và agent vẫn không trả
 * lời được — không có gì nổ, người dùng không biết nhìn đâu. */
function hienODungProvider() {
  const o = document.querySelector('[data-api-nhom="model"] [data-api-khoa="LLM_PROVIDER"]');
  if (!o) return;
  const can = API_KHOA_THEO_PROVIDER[o.value] || "";
  for (const khoa of Object.values(API_KHOA_THEO_PROVIDER)) {
    const dong = document.querySelector(`[data-api-row="${khoa}"]`);
    if (dong) {
      const dang_an = khoa !== can;
      dong.hidden = dang_an;
      /* Khi ẩn dòng, xoá tất cả password đã gõ để khoá cũ không thể quay lại
       * nếu người dùng đổi provider rồi đổi lại. */
      if (dang_an) {
        dong.querySelectorAll('input[type="password"]').forEach((ip) => {
          ip.value = "";
        });
      }
    }
  }
}

document.addEventListener("change", (e) => {
  const o = e.target.closest('[data-api-nhom="model"] [data-api-khoa="LLM_PROVIDER"]');
  if (o) hienODungProvider();
});

/* Gom giá trị đang gõ trong một nhóm; bỏ ô trống để không ghi đè khoá đã
 * lưu bằng chuỗi rỗng. */
function giaTriApiDangGo(ma) {
  const ra = {};
  document.querySelectorAll(`[data-api-nhom="${ma}"] [data-api-khoa]`).forEach((o) => {
    /* Một ô đã ẩn là một ô người dùng không còn nhìn thấy — gửi giá trị của nó
     * đi là lưu thầm, có thể là khoá cũ từ trước khi đổi provider. Bỏ qua ô ẩn. */
    if (o.closest("[data-api-row]")?.hidden) return;
    const v = (o.value || "").trim();
    if (v) ra[o.dataset.apiKhoa] = v;
  });
  return ra;
}

document.addEventListener("click", async (e) => {
  const kiem = e.target.closest("[data-api-kiem]");
  const luu = e.target.closest("[data-api-luu]");
  if (!kiem && !luu) return;
  const ma = (kiem || luu).dataset.apiKiem || (kiem || luu).dataset.apiLuu;
  const kq = $(`[data-api-kq="${ma}"]`);
  try {
    if (kiem) {
      kq.textContent = "đang kiểm…";
      const r = await api("/cai-dat-api/kiem-tra", {
        method: "POST", body: JSON.stringify({ nhom: ma, gia_tri: giaTriApiDangGo(ma) }),
      });
      kq.textContent = (r.ok ? "✓ " : "✗ ") + r.chi_tiet;
      return;
    }
    const gia_tri = giaTriApiDangGo(ma);
    const da_luu = [];
    const hong = [];
    // Lưu từng khoá riêng: một khoá hỏng không được che khoá đã lưu, và
    // người dùng phải biết đúng khoá nào hỏng — gộp chung một try thì khoá
    // 1 đã ghi vào CSDL nhưng người dùng chỉ thấy "lỗi", tưởng chưa lưu gì.
    for (const [khoa, v] of Object.entries(gia_tri)) {
      try {
        await api(`/cai-dat-api/${khoa}`, { method: "PUT", body: JSON.stringify({ gia_tri: v }) });
        da_luu.push(khoa);
      } catch (err) {
        hong.push({ khoa, loi: err.message });
      }
    }
    // Nạp lại LUÔN, kể cả khi có khoá hỏng: khoá đã lưu phải hiện trạng thái
    // mới (nguồn = csdl, bốn ký tự cuối), không đứng khựng ở dữ liệu cũ.
    await loadCaiDatApi();
    if (!hong.length) {
      toast(`Đã lưu ${da_luu.length} khoá — có hiệu lực ngay`);
    } else {
      const thongBao = `Lưu được ${da_luu.length}, hỏng ${hong.length}: ` +
        hong.map((h) => h.khoa + " (" + h.loi + ")").join("; ");
      toast(thongBao, true);
      // kq cũ đã bị loadCaiDatApi() dựng lại DOM mới — lấy lại tham chiếu.
      const kqMoi = $(`[data-api-kq="${ma}"]`);
      if (kqMoi) kqMoi.textContent = thongBao;
    }
  } catch (err) {
    kq.textContent = "";
    toast(err.message, true);
  }
});


/* ---------------- xác nhận bảng giá ---------------- */

/* Mục "Bảng giá" là thứ máy KHÔNG tự kiểm được: nó chỉ thấy một cái tên và
 * một con số, không biết bảng nào là bảng bán lẻ.
 *
 * Nhưng một cảnh báo không bao giờ tắt được thì tệ hơn không có cảnh báo —
 * người vận hành biết mục ấy lúc nào cũng vàng, nên lần sau có mục vàng
 * THẬT thì mắt họ lướt qua. */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-bg-xacnhan]");
  if (!b) return;
  const ghi = b.dataset.bgXacnhan === "ghi";
  if (ghi && !confirm(
      "Xác nhận bảng giá đang dùng ĐÚNG là giá bán lẻ?\n\n" +
      "Sai thì agent báo giá sỉ cho khách lẻ, rất tự tin.\n" +
      "Xác nhận này gắn với tên bảng giá hiện tại — đổi sang bảng khác thì " +
      "cảnh báo quay lại.")) return;
  try {
    await api("/erp/xac-nhan-bang-gia", { method: ghi ? "POST" : "DELETE" });
    toast(ghi ? "Đã ghi nhận xác nhận" : "Đã gỡ — cảnh báo quay lại");
    $("#erpthu")?.click();
  } catch (err) { toast(err.message, true); }
});
