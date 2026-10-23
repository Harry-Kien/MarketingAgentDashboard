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
    // Và đóng luồng SSE: EventSource tự nối lại mãi sau 401, mỗi lần nối
    // lại kéo theo một lượt loadOverview -> đo được 25 lần 401 liên tiếp
    // vào /api/overview từ một tab đã hết phiên. Không nguy hiểm, nhưng là
    // một tab chết cứ gõ cửa máy chủ vài giây một lần, mãi mãi.
    if (state.stream) { state.stream.close(); state.stream = null; }
    throw new Error("Phiên đăng nhập đã hết hạn — đăng nhập lại để tiếp tục");
  }

  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch { /* giữ nguyên */ }
    // 429 của Phòng thử trả detail là object ({ly_do, ...}), không phải chuỗi.
    // Error() ép mọi message thành chuỗi bằng String() — không xử lý riêng thì
    // toast hiện "[object Object]", người dùng không biết vì sao bị chặn.
    // Object có `detail` lồng (409 bản nháp, 422 mẫu trả lời nhanh: {cum,
    // detail}) — lấy câu chữ, không hiện chuỗi JSON cho người trực.
    const err = new Error(typeof detail === "string" ? detail
      : (detail && (detail.ly_do || detail.detail)) || JSON.stringify(detail));
    /* Giữ nguyên `detail` dạng object cho nơi gọi cần rẽ nhánh theo nội
     * dung lỗi, không phải theo chuỗi chữ. Đọc lỗi bằng cách so chuỗi tiếng
     * Việt là thứ hỏng ngay lần đầu ai đó sửa lại câu thông báo. */
    err.chi_tiet = detail;
    err.ma = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

function hanDoc(iso) {
  /* HẠN nằm ở TƯƠNG LAI, còn `clock()` chỉ biết diễn đạt quá khứ: một hạn
     sáu giờ nữa rơi vào nhánh `diff < 60` và hiện ra "vừa xong".

     "Hạn vừa xong" là câu vô nghĩa, và tệ hơn là nó nghe như việc đã kết
     thúc — đúng ngược với ý. */
  const d = new Date(iso);
  const con = (d - Date.now()) / 1000;
  if (con < 0) return clock(iso);              // đã qua: "3 ngày", "08-09"
  if (con < 3600) return "trong " + Math.max(1, Math.floor(con / 60)) + " phút";
  if (con < 86400) return "trong " + Math.floor(con / 3600) + " giờ";
  if (con < 7 * 86400) return "trong " + Math.floor(con / 86400) + " ngày";
  return d.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

function ngayTu(iso) {
  /* Số NGÀY tính tới nay. Trả số nguyên, không "khoảng 2 tháng": ô chỉ số
     cần một con số so sánh được giữa các lần nhìn, không cần một câu văn. */
  const ms = Date.now() - new Date(iso).getTime();
  return Math.max(0, Math.floor(ms / 86400000));
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
    doiMan("hoithoai");
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

