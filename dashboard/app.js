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
    // 429 của Phòng thử trả detail là object ({ly_do, ...}), không phải chuỗi.
    // Error() ép mọi message thành chuỗi bằng String() — không xử lý riêng thì
    // toast hiện "[object Object]", người dùng không biết vì sao bị chặn.
    const err = new Error(typeof detail === "string" ? detail : (detail && detail.ly_do) || JSON.stringify(detail));
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

/* ================= Tin không gửi được, và khách chưa có chủ =================
 *
 * Hai ô trên dải chỉ số Ca trực đếm hai thứ này từ lâu. Không có gì phía
 * sau con số — và một con số không bấm được là một con số người ta học
 * cách bỏ qua.
 *
 * CLAUDE.md xếp "outbox bỏ cuộc sau 8 lần thử mà không báo ai" vào bảng
 * lỗi nghiêm trọng nhất: tin nhân viên chết, khách chờ mãi không có trả
 * lời. Đếm được là nửa đường; nửa còn lại là gửi lại được.
 */

function dongChet(j) {
  const loi = j.last_error ? String(j.last_error).slice(0, 160) : "không rõ lý do";
  return `<div class="row">
    <span class="row__flag row__flag--halt"></span>
    <div class="row__main">
      <b>${esc(j.account_name || j.channel || "kênh đã xoá")}</b>
      <span class="row__sub">${esc(loi)}</span>
      <span class="row__sub">${j.attempts}/${j.max_attempts} lần thử · ${clock(j.updated_at)}</span>
    </div>
    <div class="row__side">
      <span class="row__nut">
        <button type="button" class="btn btn--sm" data-guilai="${esc(j.id)}">Gửi lại</button>
        <button type="button" class="btn btn--sm btn--ghost" data-bochet="${esc(j.id)}">Bỏ qua</button>
      </span>
    </div>
  </div>`;
}

async function loadTinChet() {
  /* Quyền thiếu KHÔNG được làm đỏ cả trang: nhân viên thường không có
     `outbox.doc`, và với họ panel này đơn giản là không tồn tại. */
  if (!state.toiQuyen.has("outbox.doc")) return;
  let ds = [];
  try {
    ds = (await api("/outbox/jobs?status=dead&limit=50")).items || [];
  } catch { return; }
  $("#pnChet").classList.toggle("is-hidden", ds.length === 0);
  if (!ds.length) return;
  $("#dsChet").innerHTML = ds.map(dongChet).join("");
  $("#chetNote").textContent =
    `${ds.length} tin khách không nhận được · gửi lại hoặc bỏ qua`;
}

async function loadVoChu() {
  if (!state.toiQuyen.has("khach.doc")) return;
  let d = { khach: [] };
  try { d = await api("/khach-vo-chu?limit=50"); } catch { return; }
  const ds = d.khach || [];
  $("#pnVoChu").classList.toggle("is-hidden", ds.length === 0);
  if (!ds.length) return;
  $("#dsVoChu").innerHTML = ds.map((k) => `<div class="row">
    <span class="row__flag row__flag--assist"></span>
    <div class="row__main">
      <b>${esc(k.display_name || "khách chưa có tên")}</b>
      <span class="row__sub">vào hệ thống ${ngayTu(k.first_seen)} ngày trước · nhắn lần cuối ${clock(k.last_seen)}</span>
    </div>
    <div class="row__side">
      <span class="row__nut">
        <button type="button" class="btn btn--sm" data-giaovc="${esc(k.id)}">Giao cho…</button>
      </span>
    </div>
  </div>`).join("");
  /* Nói SỐ TỔNG khi danh sách bị cắt: "50 khách" trong khi thật ra 214 là
     một con số làm người ta yên tâm sai chỗ. */
  $("#voChuNote").textContent = d.so > ds.length
    ? `${d.so} khách chưa ai chịu trách nhiệm · đang hiện ${ds.length} cũ nhất`
    : `${d.so} khách chưa ai chịu trách nhiệm`;
}

$("#dsChet")?.addEventListener("click", async (e) => {
  const lai = e.target.closest("[data-guilai]");
  const bo = e.target.closest("[data-bochet]");
  const nut = lai || bo;
  if (!nut) return;
  nut.disabled = true;
  try {
    if (lai) {
      await api(`/outbox/jobs/${lai.dataset.guilai}/retry`, { method: "POST" });
      toast("Đã xếp lại hàng đợi. Theo dõi vài giây xem nó đi được chưa.");
    } else {
      /* Bỏ qua là NÓI RA rằng khách sẽ không bao giờ nhận tin này. Không
         hỏi "có chắc không" — câu ấy không mang thông tin nào. */
      if (!confirm("Bỏ qua tin này? Khách sẽ KHÔNG BAO GIỜ nhận được nó."
                   + " Việc này không hoàn tác được.")) { nut.disabled = false; return; }
      await api(`/outbox/jobs/${bo.dataset.bochet}/cancel`, { method: "POST" });
      toast("Đã bỏ qua.");
    }
    await loadTinChet();
    await loadOverview();
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
  }
});

$("#dsVoChu")?.addEventListener("click", async (e) => {
  const g = e.target.closest("[data-giaovc]");
  if (!g) return;
  await giaoKhach(g.dataset.giaovc, "");
  await loadVoChu();
  await loadOverview();
});

/* ==================== Định tuyến tự động ====================
 *
 * `AutoRoutingWorker` chạy nền từ lâu (agent/main.py), nhưng không màn hình
 * nào tạo được đội hay luật — nên mỗi vòng nó không tìm thấy luật nào và
 * không làm gì. Một hệ thống con hoàn chỉnh nằm ngủ, và không có gì trên
 * dashboard nói rằng nó tồn tại.
 *
 * KHÔNG thay cho "giao khách cho nhân viên". Giao khách gán MỘT KHÁCH lâu
 * dài cho một người; định tuyến chia TỪNG HỘI THOẠI mới cho người đang rảnh.
 * Hai việc khác nhau, chạy song song được.
 */

const dinhTuyen = { doi: [], luat: [], sla: [], nguoi: [], kenh: [] };

function dtTenDoi(id) {
  const d = dinhTuyen.doi.find((x) => x.id === id);
  return d ? d.name : "đội đã xoá";
}

function dtTenKenh(id) {
  if (!id) return "mọi kênh";
  const k = dinhTuyen.kenh.find((x) => x.id === id);
  return k ? (k.display_name || k.channel) : "kênh đã xoá";
}

const DT_MUC = { low: "thấp", normal: "thường", high: "cao", urgent: "gấp" };

async function loadDinhTuyen() {
  if (!state.toiQuyen.has("dinh_tuyen.doc")) return;
  let c;
  try { c = await api("/routing"); } catch (e) { toast(e.message, true); return; }
  dinhTuyen.doi = c.teams || [];
  dinhTuyen.luat = c.rules || [];
  dinhTuyen.sla = c.sla_policies || [];

  /* Hai danh sách phụ chỉ để đổ vào ô chọn. Lỗi ở đây KHÔNG được làm hỏng
     cả panel: người không có `nguoi_dung.doc` vẫn phải xem được luật đang
     chạy.

     Nhưng lỗi cũng KHÔNG được nuốt im: ô chọn rỗng trông hệt như "chưa có
     nhân viên nào", và người vận hành sẽ đi tạo nhân viên thay vì đi xem
     mình thiếu quyền gì. `dtThieu` nói ra điều đó ngay trong ô chọn.

     `/channel-accounts` trả về MẢNG chứ không phải `{items}` — đọc nhầm là
     ô chọn kênh rỗng vĩnh viễn, không lỗi, không ai biết. */
  dinhTuyen.loi = [];
  try { dinhTuyen.nguoi = (await api("/nguoi-dung")).nguoi_dung || []; }
  catch { dinhTuyen.nguoi = []; dinhTuyen.loi.push("nhân viên"); }
  try { dinhTuyen.kenh = await api("/channel-accounts") || []; }
  catch { dinhTuyen.kenh = []; dinhTuyen.loi.push("kênh"); }

  const soLuat = dinhTuyen.luat.filter((r) => r.active).length;
  /* Nói thẳng trạng thái NGỦ. "0 luật" là một con số; "không làm gì cả" là
     một câu người vận hành hiểu được ngay. */
  $("#dtTrangThai").textContent = soLuat
    ? `${dinhTuyen.doi.length} đội · ${soLuat} luật đang chạy`
    : "chưa có luật nào — bộ định tuyến KHÔNG làm gì";

  $("#dtDoi").innerHTML = dinhTuyen.doi.length
    ? dinhTuyen.doi.map((d) => `<div class="row">
        <span class="row__flag row__flag--${d.status === "active" ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(d.name)}</b>
          <span class="row__sub">${esc(d.description || "—")}</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa có đội nào.</p>';

  $("#dtLuat").innerHTML = dinhTuyen.luat.length
    ? dinhTuyen.luat.map((r) => `<div class="row">
        <span class="row__flag row__flag--${r.active ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(dtTenKenh(r.account_id))} → ${esc(dtTenDoi(r.team_id))}</b>
          <span class="row__sub">mức ${esc(DT_MUC[r.priority] || "bất kỳ")} · trọng số ${r.weight}${r.active ? "" : " · đang tắt"}</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa có luật nào — hội thoại nằm chờ người tự nhận.</p>';

  $("#dtSla").innerHTML = dinhTuyen.sla.length
    ? dinhTuyen.sla.map((s2) => `<div class="row">
        <span class="row__flag row__flag--${s2.active ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(dtTenKenh(s2.account_id))} · mức ${esc(DT_MUC[s2.priority] || s2.priority)}</b>
          <span class="row__sub">trả lời đầu ${s2.first_response_minutes} phút · xong ${s2.resolution_minutes} phút</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa đặt hạn nào.</p>';

  const oDoi = dinhTuyen.doi
    .map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  $("#dtChonDoi").innerHTML = oDoi;
  $("#dtLuatDoi").innerHTML = oDoi;
  const dtThieu = (ten) => dinhTuyen.loi.includes(ten)
    ? `<option value="">— không đọc được danh sách ${ten}, thiếu quyền? —</option>`
    : "";
  $("#dtChonNguoi").innerHTML = dtThieu("nhân viên") + dinhTuyen.nguoi
    .filter((n) => !n.khoa)
    .map((n) => `<option value="${esc(n.id)}">${esc(n.ho_ten || n.ten_dang_nhap)}</option>`)
    .join("");
  const oKenh = '<option value="">mọi kênh</option>' + dtThieu("kênh")
    + dinhTuyen.kenh
      .map((k) => `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`)
      .join("");
  $("#dtChonKenh").innerHTML = oKenh;
  $("#dtSlaKenh").innerHTML = oKenh;
}

/* Gửi form rồi tải lại. Gom vào một hàm vì bốn form khác nhau đúng ở thân
   yêu cầu, còn phần xử lý lỗi và khoá nút thì giống hệt — và chép bốn lần
   là bốn chỗ để quên `finally`. */
async function dtGui(form, duong, phuong_thuc, dung_than) {
  const nut = form.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    const d = Object.fromEntries(new FormData(form).entries());
    await api(duong(d), { method: phuong_thuc, body: JSON.stringify(dung_than(d)) });
    form.reset();
    await loadDinhTuyen();
    toast("Đã lưu.");
  } catch (e) {
    toast(e.message, true);
  } finally {
    nut.disabled = false;
  }
}

$("#dtFormDoi")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget, () => "/routing/teams", "POST",
        (d) => ({ name: d.name, description: d.description || "" }));
});

$("#dtFormNguoi")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget,
        (d) => `/routing/teams/${d.team_id}/members/${d.user_id}`, "PUT",
        (d) => ({ role: "agent", skills: [],
                  max_active: Number(d.max_active) || 20, is_available: true }));
});

$("#dtFormLuat")?.addEventListener("submit", (e) => {
  e.preventDefault();
  /* `account_id` và `priority` rỗng phải thành null, KHÔNG phải chuỗi rỗng:
     máy chủ hiểu null là "mọi kênh / mọi mức", còn chuỗi rỗng thì trượt
     kiểm kiểu và trả 422 với một câu người vận hành không đọc được. */
  dtGui(e.currentTarget, () => "/routing/rules", "POST", (d) => ({
    account_id: d.account_id || null,
    team_id: d.team_id,
    priority: d.priority || null,
    required_skills: [],
    weight: Number(d.weight) || 100,
    active: true,
  }));
});

$("#dtFormSla")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget, () => "/routing/sla-policies", "PUT", (d) => ({
    account_id: d.account_id || null,
    priority: d.priority,
    first_response_minutes: Number(d.first_response_minutes),
    resolution_minutes: Number(d.resolution_minutes),
    business_hours: {},
    active: true,
  }));
});

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
    /* KHÁCH CHƯA CÓ CHỦ — cùng lý lẽ với ô trên: chỉ hiện khi CÓ.
     *
     * Chủ dự án chọn "khách chưa giao là của chung, không tự gán chủ", nên
     * khách vô chủ sẽ tích lại — đó là hệ quả đã biết trước, và một hàng
     * chờ không ai đếm thì không ai thấy.
     *
     * Kèm TUỔI của khách vô chủ lâu nhất, không chỉ số lượng: "412 khách"
     * là một con số người ta quen mắt sau một tuần; "lâu nhất 62 ngày" thì
     * không. */
    /* VIỆC QUÁ HẠN — cùng họ với hai ô trên, cũng chỉ hiện khi CÓ.
     * Đếm riêng việc CHƯA GIAO cho ai: đó là thứ dễ rơi nhất, vì không ai
     * thấy nó trong danh sách "việc của tôi". */
    (o.cong_viec && o.cong_viec.qua_han
      ? cell("Việc quá hạn", o.cong_viec.qua_han,
             o.cong_viec.chua_giao
               ? `${o.cong_viec.chua_giao} việc chưa giao cho ai`
               : "đều đã có người nhận", 1, "halt")
      : ""),
    (o.khach_vo_chu && o.khach_vo_chu.so
      ? cell("Khách chưa có chủ", o.khach_vo_chu.so,
             o.khach_vo_chu.lau_nhat
               ? `lâu nhất ${ngayTu(o.khach_vo_chu.lau_nhat)} ngày`
               : "chưa giao cho ai", 1, "assist")
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
      /* Nói ra là tin này đã qua tay người. Không nói thì con số "tin cậy
       * 0.77" ngay cạnh đây trông như đang chấm câu đang hiện — mà nó chấm
       * bản AI viết, tức là chấm một câu chữ khác. */
      m.sua_boi ? "đã sửa bởi " + m.sua_boi : "",
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

    /* Sửa NGAY TẠI bong bóng, không mở hộp thoại đè lên.
     *
     * Người sửa cần đọc lại câu khách vừa hỏi ngay phía trên trong lúc gõ —
     * một hộp thoại che mất đúng thứ họ cần nhìn, và họ sẽ đóng/mở nó vài
     * lần cho mỗi lần sửa. */
    const dangSua = draft && state.dangSua === m.id;
    const than = dangSua
      ? `<div class="msg__sua">
           <textarea class="msg__sua-o" data-sua-o rows="1"
             aria-label="Sửa nội dung bản nháp">${esc(m.content || "")}</textarea>
           <div class="msg__sua-chan">
             <span class="msg__sua-dem" data-sua-dem></span>
             <span class="msg__sua-nut">
               <button type="button" class="btn btn--sm" data-edit-cancel>Huỷ</button>
               <button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>
             </span>
           </div>
         </div>`
      : (m.content && !chuTrung ? `<div class="msg__bubble">${esc(m.content)}</div>` : "");

    /* Bản AI để đối chiếu, mặc định GẤP LẠI. Bung sẵn thì mỗi tin đã sửa
     * chiếm hai lần chỗ trong luồng, và người trực cuộn nhiều gấp đôi để
     * đọc một hội thoại — cái giá ấy trả mỗi ngày, còn nhu cầu đối chiếu
     * thì thỉnh thoảng. */
    const banGoc = m.noi_dung_goc
      ? `<button type="button" class="msg__goc-nut" data-xem-goc="${m.id}">
           ${state.xemGoc === m.id ? "ẩn bản AI" : "xem bản AI"}
         </button>`
      : "";

    return `<div class="msg msg--${m.role} ${draft ? "msg--draft" : ""} ${dangSua ? "msg--dangsua" : ""}">
      ${anh}
      ${than}
      ${m.noi_dung_goc && state.xemGoc === m.id
        ? `<div class="msg__goc"><span class="msg__goc-nhan">Bản AI đã viết</span>${esc(m.noi_dung_goc)}</div>`
        : ""}
      <div class="msg__meta">
        <span>${esc(meta)}</span>
        ${banGoc}
        ${draft && !dangSua ? `<button type="button" class="btn btn--sm" data-edit="${m.id}">Sửa</button>
          <button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>` : ""}
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
  /* Ô SỬA BẢN NHÁP cũng phải giữ, và giữ vì đúng lý do ở trên — mạnh hơn
   * nữa: chữ trong ô này là câu sắp gửi cho khách, không phải bản nháp riêng
   * của người trực. Mất nó giữa chừng là mất một câu đã cân nhắc từng chữ. */
  const o_sua_cu = $("[data-sua-o]");
  const sua_dang_focus = o_sua_cu && document.activeElement === o_sua_cu;
  const sua_con_tro = o_sua_cu ? o_sua_cu.selectionStart : null;
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

  /* Ô sửa bản nháp: trả lại chữ đang gõ, tự giãn theo nội dung, đếm ký tự.
   *
   * `state.suaText` là nguồn sự thật giữa hai lần vẽ — thẻ <textarea> cũ đã
   * bị vứt cùng cả panel, nên không đọc lại được từ DOM. */
  const o_sua = $("[data-sua-o]");
  if (o_sua) {
    if (state.suaText != null) o_sua.value = state.suaText;
    else state.suaText = o_sua.value;

    const dem = $("[data-sua-dem]");
    const gian = () => {
      // Tự giãn theo nội dung: một câu tư vấn dài 1.200 ký tự nằm trong ô
      // ba dòng thì người sửa phải cuộn trong lúc gõ, và không bao giờ nhìn
      // được cả câu sắp gửi — đúng thứ họ cần nhìn nhất.
      o_sua.style.height = "auto";
      o_sua.style.height = Math.min(o_sua.scrollHeight, 420) + "px";
      if (dem) dem.textContent = o_sua.value.trim().length + " / 4000 ký tự";
    };
    gian();

    o_sua.addEventListener("input", () => { state.suaText = o_sua.value; gian(); });
    o_sua.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") {
        state.dangSua = null; state.suaText = null; loadThread(id); return;
      }
      /* Ctrl+Enter gửi, KHÔNG phải Enter trần như ô trả lời bên dưới.
       * Ô kia soạn tin ngắn, ô này sửa một đoạn nhiều dòng có đánh số —
       * Enter ở đây phải xuống dòng, không thì không sửa nổi đoạn dài. */
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey) && !ev.isComposing) {
        ev.preventDefault();
        $(`[data-approve="${state.dangSua}"]`)?.click();
      }
    });

    if (sua_dang_focus) {
      o_sua.focus();
      const vt = sua_con_tro == null ? o_sua.value.length : Math.min(sua_con_tro, o_sua.value.length);
      o_sua.setSelectionRange(vt, vt);
    } else if (state.suaVuaMo) {
      o_sua.focus();
      o_sua.setSelectionRange(o_sua.value.length, o_sua.value.length);
      state.suaVuaMo = false;
    }
  }

  $$("[data-edit]").forEach((b) => b.addEventListener("click", () => {
    state.dangSua = b.dataset.edit;
    state.suaText = null;      // lấy lại từ nội dung tin ở lần vẽ ngay sau đây
    state.suaVuaMo = true;
    loadThread(id);
  }));

  $$("[data-edit-cancel]").forEach((b) => b.addEventListener("click", () => {
    state.dangSua = null; state.suaText = null; loadThread(id);
  }));

  $$("[data-xem-goc]").forEach((b) => b.addEventListener("click", () => {
    state.xemGoc = state.xemGoc === b.dataset.xemGoc ? null : b.dataset.xemGoc;
    loadThread(id);
  }));

  $$("[data-approve]").forEach((b) =>
    b.addEventListener("click", async () => {
      const mid = b.dataset.approve;
      const coSua = state.dangSua === mid;
      const gui = (xac_nhan) => api("/messages/" + mid + "/approve", {
        method: "POST",
        // Không sửa thì KHÔNG gửi body — đó đúng là đường cũ, và giữ nó
        // nguyên vẹn nghĩa là nút "Duyệt và gửi" quen thuộc không đổi hành vi.
        body: coSua ? JSON.stringify({ noi_dung: state.suaText || "", xac_nhan }) : undefined,
      });
      try {
        let r;
        try {
          r = await gui(false);
        } catch (e) {
          /* 409 = có cụm cấm quảng cáo. Hỏi lại chứ không chặn: người bấm
           * là người chịu trách nhiệm. Nhưng phải THẤY trước khi tin đi. */
          const ct = e.chi_tiet;
          if (!ct || !ct.can_xac_nhan) throw e;
          const dong_y = confirm(
            "Nội dung có cụm bị cấm trong quảng cáo mỹ phẩm:\n\n    "
            + (ct.cum || []).join(", ")
            + "\n\nAgent bị chặn không được nói những cụm này với khách.\n"
            + "Vẫn gửi? Lần bỏ qua này sẽ vào nhật ký."
          );
          if (!dong_y) return;
          r = await gui(true);
        }
        state.dangSua = null; state.suaText = null;
        toast(r && r.ok ? (coSua ? "Đã gửi bản đã sửa." : "Đã gửi cho khách.")
                        : "Không gửi được: " + (r && r.detail), !(r && r.ok));
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

function chuKhach(contact) {
  /* Hiện TÊN người phụ trách, không hiện UUID và không để trống.
   *
   * Để trống thì "chưa giao cho ai" trông hệt như "chưa tải xong", và người
   * trực không biết mình có được vào hay không. */
  if (contact.owner_ho_ten || contact.owner_ten_dang_nhap) {
    return `<span class="pill">${esc(contact.owner_ho_ten || contact.owner_ten_dang_nhap)}</span>`;
  }
  return '<span class="pill pill--warn">chưa có chủ</span>';
}

/* ==================== Gộp khách trùng ====================
 *
 * Một người nhắn Zalo rồi nhắn Facebook là HAI contact trong CSDL, và không
 * có gì tự nối lại. API gộp có đủ ba việc — xem trước, gộp, hoàn tác —
 * nhưng không màn hình nào gọi tới, nên lịch sử của một khách nằm rải ở hai
 * chỗ và người trực trả lời mà không thấy nửa còn lại.
 *
 * XEM TRƯỚC LÀ BẮT BUỘC, KHÔNG PHẢI TÙY CHỌN.
 * Gộp dồn hội thoại và danh tính sang một bên rồi đánh dấu bên kia là đã
 * gộp. Hoàn tác được, nhưng chỉ khi biết mình vừa gộp nhầm — mà gộp nhầm
 * hai khách trùng tên thì không ai nhận ra. Nên nút Gộp chỉ hiện SAU khi đã
 * xem trước, và xem trước nói rõ mỗi bên có bao nhiêu hội thoại, bao nhiêu
 * danh tính.
 */

function gopDoO(ds) {
  const o = $("#gopNguon");
  if (!o) return;
  const html = (ds || []).map((c) =>
    `<option value="${esc(c.id)}">${esc(c.display_name || "Khách")}`
    + ` · ${c.contact_point_count || 0} danh tính</option>`).join("");
  o.innerHTML = html;
  $("#gopDich").innerHTML = html;
}

$("#gopMo")?.addEventListener("click", () => {
  const pn = $("#pnGop");
  pn.classList.toggle("is-hidden");
  if (!pn.classList.contains("is-hidden")) gopDoO(state.danhSachKhach);
});

$("#gopDong")?.addEventListener("click", () => {
  $("#pnGop").classList.add("is-hidden");
  $("#gopKetQua").innerHTML = "";
});

$("#gopXem")?.addEventListener("click", async () => {
  const nguon = $("#gopNguon").value;
  const dich = $("#gopDich").value;
  if (!nguon || !dich) return;
  if (nguon === dich) {
    toast("Hai ô đang chọn cùng một khách.", true);
    return;
  }
  try {
    const d = await api(`/contacts/merge/preview?source_id=${encodeURIComponent(nguon)}`
                        + `&target_id=${encodeURIComponent(dich)}`);
    const ben = (t, x) => `<div class="row">
      <span class="row__flag row__flag--${t === "nguon" ? "halt" : "auto"}"></span>
      <div class="row__main">
        <b>${esc(x.display_name || "Khách")}</b>
        <span class="row__sub">${t === "nguon" ? "SẼ BIẾN MẤT khỏi danh sách" : "GIỮ LẠI, nhận hết về đây"}</span>
        <span class="row__sub">${x.conversation_count} hội thoại · ${x.point_count} danh tính</span>
      </div>
    </div>`;
    /* `can_manage` false nghĩa là người này không quản được mọi kênh của cả
       hai khách. Máy chủ sẽ từ chối — nói trước ở đây thay vì để họ điền
       xong lý do rồi mới ăn 403. */
    $("#gopKetQua").innerHTML = ben("nguon", d.source) + ben("dich", d.target)
      /* Câu cảnh báo là `panel__note`, KHÔNG phải một `.row` nữa: `.row__main`
         không có `<b>` thì co lại gần bằng không và chữ biến mất — nhìn trên
         trình duyệt mới thấy, đọc mã thì không. */
      + (d.can_manage
        ? `<p class="panel__note">Hoàn tác được sau khi gộp, nhưng chỉ khi bạn
             nhận ra mình gộp nhầm — nên xem kỹ hai dòng trên.</p>
           <div class="row__nut">
             <button type="button" class="btn btn--sm btn--halt" id="gopLam">Gộp</button>
           </div>`
        : `<p class="empty">Bạn không quản lý mọi kênh của hai khách này, nên
             không gộp được. Nhờ quản trị làm.</p>`);

    $("#gopLam")?.addEventListener("click", async () => {
      const ly_do = prompt("Vì sao gộp? (ghi vào lịch sử, để hoàn tác còn hiểu được)",
                           "Cùng một người, hai kênh");
      if (!ly_do) return;
      const nut = $("#gopLam");
      nut.disabled = true;
      try {
        /* Gửi kèm `version` đọc được lúc xem trước. Ai đó sửa một trong hai
           khách giữa lúc xem và lúc bấm thì máy chủ trả 409 và KHÔNG gộp —
           đúng hơn là gộp theo một bản xem trước đã cũ. */
        const r = await api("/contacts/merge", {
          method: "POST",
          body: JSON.stringify({
            source_id: d.source.id, target_id: d.target.id, reason: ly_do,
            expected_source_version: d.source.version,
            expected_target_version: d.target.version,
          }),
        });
        toast(`Đã gộp. Hoàn tác được bằng mã ${r.merge_id.slice(0, 8)}…`);
        $("#gopKetQua").innerHTML = "";
        $("#pnGop").classList.add("is-hidden");
        await loadContacts();
      } catch (e) {
        toast(e.ma === 409
          ? "Một trong hai khách vừa bị người khác sửa. Xem trước lại."
          : e.message, true);
        nut.disabled = false;
      }
    });
  } catch (e) { toast(e.message, true); }
});

async function loadContacts() {
  const contacts = await api(`/contacts?limit=100&q=${encodeURIComponent(state.contactQuery)}`);
  /* Lọc Ở PHÍA GIAO DIỆN là có chủ ý và chỉ hợp lệ vì nó KHÔNG phải lớp bảo
   * vệ: máy chủ đã lọc theo mức tầm nhìn trước khi trả về. Ba chip này chỉ
   * thu hẹp thứ người dùng đã được phép thấy. */
  const loc = state.chuLoc || "tat_ca";
  const hien = contacts.filter((c) =>
    loc === "cua_toi" ? c.owner_user_id && c.owner_user_id === state.toiId
    : loc === "vo_chu" ? !c.owner_user_id
    : true);
  state.danhSachKhach = contacts;
  $("#c-khachhang").textContent = contacts.length || "";
  gopDoO(contacts);
  $("#contactlist").innerHTML = hien.length ? hien.map((contact) => `
    <button type="button" class="row row--avatar ${state.openContact === contact.id ? "is-on" : ""}" data-contact="${contact.id}">
      <span class="avatar">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <span class="row__body"><span class="row__title">${esc(contact.display_name || "Khách")}</span>
        <span class="row__sub">${esc(contact.phone || contact.email || "Chưa có PII xác minh")} · ${contact.contact_point_count || 0} danh tính</span></span>
      <span class="row__side">${chuKhach(contact)}<span class="row__time">${clock(contact.last_seen)}</span></span>
    </button>`).join("")
    : `<p class="empty">${loc === "cua_toi"
        ? "Chưa có khách nào được giao cho bạn."
        : loc === "vo_chu"
          ? "Mọi khách trong phạm vi của bạn đều đã có người phụ trách."
          : "Không tìm thấy khách hàng trong phạm vi tài khoản của bạn."}</p>`;
  $$("#contactlist [data-contact]").forEach((row) => row.addEventListener("click", () => {
    state.openContact = row.dataset.contact;
    loadContacts();
  }));
  if (state.openContact) await loadContactDetail(state.openContact);
}

$("#contactloc")?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-chuloc]");
  if (!chip) return;
  state.chuLoc = chip.dataset.chuloc;
  $$("#contactloc .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
  loadContacts();
});

async function giaoKhach(id, chuHienTai) {
  /* Gán bằng TÊN ĐĂNG NHẬP chứ không bằng UUID: người quản lý biết "thao",
     không biết `a3f1…`. Đổi tên sang id ngay tại đây, và tên lạ thì báo
     ngay chứ không gửi một UUID rỗng lên máy chủ. */
  let ds;
  try { ds = (await api("/nguoi-dung")).nguoi_dung; }
  catch (e) { toast(e.message, true); return; }

  const ten = prompt(
    "Giao khách này cho ai? Gõ tên đăng nhập.\n"
    + "Để TRỐNG là thu hồi — khách quay về của chung.\n\n"
    + ds.map((n) => `${n.ten_dang_nhap} — ${n.ho_ten || ""}`).join("\n"),
    chuHienTai || "");
  if (ten === null) return;

  const ly_do = prompt("Lý do (ghi vào lịch sử giao khách):", "Phân công ca trực");
  if (!ly_do) return;

  try {
    if (!ten.trim()) {
      await api(`/contacts/${id}/chu-so-huu?ly_do=${encodeURIComponent(ly_do)}`,
                { method: "DELETE" });
      toast("Đã thu hồi. Khách quay về của chung.");
    } else {
      const nv = ds.find((n) => n.ten_dang_nhap === ten.trim());
      if (!nv) { toast(`Không có nhân viên tên “${ten.trim()}”.`, true); return; }
      await api(`/contacts/${id}/chu-so-huu`, {
        method: "PUT",
        body: JSON.stringify({ owner_user_id: nv.id, ly_do }),
      });
      toast(`Đã giao cho ${nv.ho_ten || nv.ten_dang_nhap}.`);
    }
    // Hàm này gọi được từ hai màn. Tải lại danh bạ khi đang đứng ở Ca trực
    // là một request vô ích ghi vào một khung không ai nhìn.
    if (state.view === "khachhang") await loadContacts();
  } catch (e) { toast(e.message, true); }
}

function oTruongKhach(contact) {
  /* Vẽ ô nhập theo KIỂU. Vẽ tất cả thành ô chữ cũng "chạy" — máy chủ vẫn
     kiểm — nhưng khi ấy người trực gõ sai rồi mới biết, mỗi lần một lần.
     Ô đúng kiểu là lớp phòng thứ nhất; máy chủ là lớp thứ hai. */
  if (!truongKhach.ds.length) return "";
  const co = contact.profile || {};
  const o = truongKhach.ds.map((t) => {
    const v = co[t.ma];
    const id = `tk-${t.ma}`;
    let nhap;
    if (t.kieu === "chon") {
      nhap = `<select id="${id}" data-tk="${esc(t.ma)}">
        <option value="">— chưa chọn —</option>
        ${(t.lua_chon || []).map((c) =>
          `<option${c === v ? " selected" : ""}>${esc(c)}</option>`).join("")}
      </select>`;
    } else if (t.kieu === "nhieu_chon") {
      nhap = `<span class="tk__nhieu">${(t.lua_chon || []).map((c) => `
        <label><input type="checkbox" data-tk-nhieu="${esc(t.ma)}" value="${esc(c)}"${
          Array.isArray(v) && v.includes(c) ? " checked" : ""}> ${esc(c)}</label>`).join("")}</span>`;
    } else if (t.kieu === "dung_sai") {
      nhap = `<input type="checkbox" id="${id}" data-tk="${esc(t.ma)}"${v ? " checked" : ""}>`;
    } else {
      const loai = t.kieu === "so" ? "number" : t.kieu === "ngay" ? "date" : "text";
      nhap = `<input type="${loai}" id="${id}" data-tk="${esc(t.ma)}"
                     value="${v === undefined || v === null ? "" : esc(String(v))}"
                     placeholder="${esc(t.goi_y || "")}">`;
    }
    return `<label class="field tk__o" for="${id}">
      <span>${esc(t.nhan)}${t.bat_buoc ? " *" : ""}</span>${nhap}</label>`;
  }).join("");
  return `<h3 class="subhead">Thông tin thêm</h3>
    <form id="contact-truong-form" class="form">${o}
      <button class="btn btn--sm" type="submit">Lưu thông tin thêm</button></form>`;
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
    <h3 class="subhead">Người phụ trách</h3>
    <div class="profile-actions">
      <div class="profile-tags">${chuKhach(contact)}</div>
      <div class="inline-action">
        <button type="button" class="btn btn--sm" id="contact-giao"
                data-contact-giao="${esc(contact.id)}"
                data-chu="${esc(contact.owner_ten_dang_nhap || "")}">Giao / thu hồi</button>
        <button type="button" class="btn btn--sm btn--ghost"
                data-contact-lichsu="${esc(contact.id)}">Lịch sử giao</button>
      </div>
    </div>
    <div id="contact-lichsu-giao"></div>
    ${oTruongKhach(contact)}
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

  $("#contact-truong-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const gia_tri = {};
    $$("[data-tk]", ev.currentTarget).forEach((o) => {
      gia_tri[o.dataset.tk] = o.type === "checkbox" ? o.checked : o.value;
    });
    /* Gom các ô "chọn nhiều" theo mã: mỗi ô tick là một phần tử, và một
       trường không tick ô nào phải gửi mảng RỖNG chứ không vắng mặt — vắng
       mặt nghĩa là "không đụng tới", nên bỏ hết tick sẽ không xoá được. */
    const daGom = new Set();
    $$("[data-tk-nhieu]", ev.currentTarget).forEach((o) => {
      const ma = o.dataset.tkNhieu;
      if (!daGom.has(ma)) { gia_tri[ma] = []; daGom.add(ma); }
      if (o.checked) gia_tri[ma].push(o.value);
    });
    try {
      await api(`/contacts/${id}/truong`, {
        method: "PUT", body: JSON.stringify({ gia_tri }),
      });
      toast("Đã lưu thông tin thêm.");
      await loadContactDetail(id);
    } catch (e) { toast(e.message, true); }
  });

  $("[data-contact-giao]")?.addEventListener("click", (ev) =>
    giaoKhach(ev.currentTarget.dataset.contactGiao, ev.currentTarget.dataset.chu));

  $("[data-contact-lichsu]")?.addEventListener("click", async (ev) => {
    const hop = $("#contact-lichsu-giao");
    if (hop.innerHTML) { hop.innerHTML = ""; return; }   // bấm lần hai là đóng
    try {
      const ds = (await api(`/contacts/${ev.currentTarget.dataset.contactLichsu}`
                            + "/chu-so-huu/lich-su")).lich_su;
      hop.innerHTML = ds.length
        ? `<div class="contact-notes">${ds.map((d) => `
            <article class="contact-note">
              <p>${d.owner_ho_ten
                    ? `Giao cho <b>${esc(d.owner_ho_ten)}</b>`
                    : "<b>Thu hồi</b> — khách quay về của chung"} · ${esc(d.ly_do)}</p>
              <small>${esc(d.actor_ten_dang_nhap || "?")} · ${clock(d.luc)}</small>
            </article>`).join("")}</div>`
        : '<p class="empty">Khách này chưa từng được giao cho ai.</p>';
    } catch (e) { toast(e.message, true); }
  });

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
    alert("Đã đổi. Đăng nhập lại bằng mật khẩu mới.");
    location.reload();
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
      </span>
    </div>
  </div>`;
}

async function loadCongViec() {
  const q = new URLSearchParams();
  if (state.cvTrangThai) q.set("trang_thai", state.cvTrangThai);
  if (state.cvCuaToi) q.set("cua_toi", "true");
  const d = await api(`/cong-viec?${q}`);
  congViec.trangThai = d.trang_thai;
  congViec.uuTien = d.uu_tien;
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
  const tieu_de = prompt("Việc cần làm:");
  if (!tieu_de) return;
  const han = prompt("Hạn (YYYY-MM-DD, để trống nếu không có):", "");
  try {
    await api("/cong-viec", {
      method: "POST",
      body: JSON.stringify({
        tieu_de: tieu_de.trim(),
        han: han && han.trim() ? new Date(han.trim()).toISOString() : null,
      }),
    });
    toast("Đã thêm việc.");
    await loadCongViec();
  } catch (e) { toast(e.message, true); }
});

$("#cv-ds")?.addEventListener("click", async (e) => {
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

async function hsaHoi(cu) {
  const ten = prompt("Tên hồ sơ (ví dụ: Bán hàng Zalo):", cu ? cu.ten : "");
  if (!ten) return null;
  const mo_ta = prompt("Mô tả ngắn — hồ sơ này dành cho kênh nào:",
                       cu ? cu.mo_ta : "");
  if (mo_ta === null) return null;
  const huong_dan = prompt(
    "Hướng dẫn THÊM cho agent khi trả lời ở kênh này.\n"
    + "Đây là phần thêm vào, không thay các câu cấm trong prompt gốc.",
    cu ? cu.huong_dan : "");
  if (huong_dan === null) return null;
  const ng = prompt(
    `Ngưỡng tự tin (0–1). Cao hơn = chuyển người sớm hơn.\n`
    + `Toàn cục đang là ${hoSoAgent.toanCuc.nguong_tu_tin}; đặt thấp hơn sẽ bị siết về mức ấy.\n`
    + `Để trống = dùng toàn cục.`,
    cu && cu.nguong_tu_tin !== null ? String(cu.nguong_tu_tin) : "");
  if (ng === null) return null;
  const tr = prompt(
    `Trần chi phí mỗi hội thoại (USD). Thấp hơn = dừng sớm hơn.\n`
    + `Toàn cục đang là ${hoSoAgent.toanCuc.tran_chi_phi}; đặt cao hơn sẽ bị siết về mức ấy.\n`
    + `Để trống = dùng toàn cục.`,
    cu && cu.tran_chi_phi !== null ? String(cu.tran_chi_phi) : "");
  if (tr === null) return null;
  return {
    ten: ten.trim(), mo_ta: mo_ta.trim(), huong_dan: huong_dan.trim(),
    nguong_tu_tin: ng.trim() ? Number(ng) : null,
    tran_chi_phi: tr.trim() ? Number(tr) : null,
    bat: cu ? cu.bat : true,
  };
}

$("#hsa-them")?.addEventListener("click", async () => {
  const than = await hsaHoi(null);
  if (!than) return;
  try {
    const d = await api("/ho-so-agent", {
      method: "POST", body: JSON.stringify(than) });
    toast(d.nguong_hieu_luc !== d.nguong_tu_tin && d.nguong_tu_tin !== null
      ? `Đã thêm. Ngưỡng bị siết về ${d.nguong_hieu_luc} (mức toàn cục).`
      : "Đã thêm hồ sơ.");
    await loadHoSoAgent();
  } catch (e) { toast(e.message, true); }
});

$("#hsa-ds")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-hsasua]");
  if (sua) {
    const cu = hoSoAgent.ds.find((h) => h.id === sua.dataset.hsasua);
    const than = await hsaHoi(cu);
    if (!than) return;
    try {
      await api(`/ho-so-agent/${cu.id}`, {
        method: "PUT", body: JSON.stringify(than) });
      toast("Đã lưu hồ sơ.");
      await loadHoSoAgent();
    } catch (err) { toast(err.message, true); }
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

$("#truong-them")?.addEventListener("click", async () => {
  const ma = prompt("Mã trường (chữ thường không dấu, ví dụ loai_da):");
  if (!ma) return;
  const nhan = prompt("Nhãn hiện cho người dùng:", ma);
  if (!nhan) return;
  const kieu = prompt(
    "Kiểu:\n" + truongKhach.kieu.map((k) => `${k.ma} — ${k.nhan}`).join("\n"),
    "chu");
  if (!kieu) return;
  let lua_chon = [];
  if (kieu === "chon" || kieu === "nhieu_chon") {
    const tra = prompt("Các lựa chọn, cách nhau bằng dấu phẩy:", "");
    lua_chon = (tra || "").split(",").map((s) => s.trim()).filter(Boolean);
  }
  try {
    await api("/truong-khach", {
      method: "POST",
      body: JSON.stringify({ ma: ma.trim(), nhan: nhan.trim(), kieu, lua_chon }),
    });
    toast("Đã thêm. Ô nhập hiện ngay trong hồ sơ mọi khách.");
    await loadTruongKhach();
  } catch (e) { toast(e.message, true); }
});

$("#truong-ds")?.addEventListener("click", async (e) => {
  const sua = e.target.closest("[data-truongsua]");
  if (sua) {
    const t = truongKhach.ds.find((x) => x.ma === sua.dataset.truongsua);
    const nhan = prompt("Nhãn:", t.nhan);
    if (nhan === null) return;
    const bat_buoc = confirm("Bắt buộc phải điền?\n(OK = bắt buộc, Huỷ = không)");
    let lua_chon = t.lua_chon || [];
    if (t.kieu === "chon" || t.kieu === "nhieu_chon") {
      const tra = prompt("Các lựa chọn, cách nhau bằng dấu phẩy:",
                         lua_chon.join(", "));
      if (tra === null) return;
      lua_chon = tra.split(",").map((s) => s.trim()).filter(Boolean);
    }
    try {
      await api(`/truong-khach/${t.ma}`, {
        method: "PUT",
        body: JSON.stringify({ nhan: nhan.trim(), goi_y: t.goi_y || "",
                               bat_buoc, lua_chon,
                               hien_danh_sach: t.hien_danh_sach,
                               thu_tu: t.thu_tu }),
      });
      toast("Đã lưu trường.");
      await loadTruongKhach();
    } catch (err) { toast(err.message, true); }
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
  return `<div class="row" data-nguoi="${esc(n.id)}">
    <span class="row__flag row__flag--${n.khoa ? "halt" : coVai ? "auto" : "assist"}"></span>
    <div class="row__main">
      <b>${esc(n.ho_ten || n.ten_dang_nhap)}</b>
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.khoa ? " · đã khoá" : ""}${
        n.dang_nhap_cuoi ? " · vào lần cuối " + clock(n.dang_nhap_cuoi) : " · chưa đăng nhập lần nào"}</span>
    </div>
    <div class="row__side">
      <span>${vai}</span>
      <span class="row__nut">
        <button type="button" class="btn btn--sm btn--ghost" data-xemquyen="${esc(n.id)}">Xem quyền</button>
        <button type="button" class="btn btn--sm btn--ghost" data-ganvai="${esc(n.id)}">Gán vai trò</button>
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
  $("#nsNguoi").innerHTML = ds.length
    ? ds.map(nsDongNguoi).join("")
    : '<p class="empty">Chưa có nhân viên nào.</p>';
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

  const gan = e.target.closest("[data-ganvai]");
  if (!gan) return;
  const id = gan.dataset.ganvai;
  try {
    const hien = await api(`/nguoi-dung/${id}/quyen`);
    const dangCo = new Set(hien.vai_tro);
    const chon = nhanSu.vaiTro.map((v) =>
      `${dangCo.has(v.ten) ? "[x]" : "[ ]"} ${v.ten}`).join("\n");
    const tra = prompt(
      `Gán vai trò cho ${hien.nguoi_dung.ho_ten || hien.nguoi_dung.ten_dang_nhap}.\n`
      + `Gõ tên các vai trò, cách nhau bằng dấu phẩy. Để trống là gỡ hết.\n\n${chon}`,
      hien.vai_tro.join(", "));
    if (tra === null) return;
    const ten = tra.split(",").map((s) => s.trim()).filter(Boolean);
    const la = ten.filter((t) => !nhanSu.vaiTro.some((v) => v.ten === t));
    if (la.length) { toast("Không có vai trò: " + la.join(", "), true); return; }
    const ids = nhanSu.vaiTro.filter((v) => ten.includes(v.ten)).map((v) => v.id);
    await api(`/nguoi-dung/${id}/vai-tro`, {
      method: "PUT", body: JSON.stringify({ vai_tro: ids }),
    });
    toast("Đã gán vai trò.");
    await loadNhanSu();
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
    f.reset();
    f.classList.add("is-hidden");
    await loadNhanSu();
  } catch (err) {
    toast(err.message, true);
  } finally {
    nut.disabled = false;
  }
});

/* ---------------- vòng làm mới ---------------- */

async function refresh() {
  try {
    await loadOverview();
    if (state.view === "ca") { await loadTinChet(); await loadVoChu(); }
    if (state.view === "hoithoai") await loadConversations();
    if (state.view === "khachhang") { await loadTruongKhach(); await loadContacts(); }
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "video") { await fillProductPicker(); await loadVideos(); }
    if (state.view === "dangbai") { await fillPostPickers(); await loadPosts(); await loadPubChannels(); }
    if (state.view === "hethong") await loadHeThong();
    if (state.view === "ketnoi") { await loadHoSoAgent(); await loadKetNoi(); await loadTichHop(); }
    if (state.view === "sohieu") {
      await loadAnalyticsKhach(); await loadAnalytics(); await loadCost();
    }
    if (state.view === "trithuc") await loadDocs();
    if (state.view === "kynang") await loadKyNang();
    if (state.view === "phongthu" && !state.phongThuDaTai) await loadPhongThu();
    if (state.view === "cauhinh") { await loadDinhTuyen(); await loadTamNhin(); await loadHoSoAgent(); await loadTruongKhach(); await loadCauHinh(); await loadCaiDatApi(); }
    if (state.view === "congviec") await loadCongViec();
    if (state.view === "nhansu") await loadNhanSu();
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
          ${account.agent_bat === false
            /* Kênh đang TẮT agent phải nhìn thấy được ngay trên thẻ.
             *
               Không hiện thì "vì sao kênh này agent không trả lời" là câu
               hỏi không có chỗ nào trả lời — người ta sẽ đi kiểm token,
               kiểm sidecar, kiểm mạng, và không ai nghĩ tới một ô tick đã
               bấm từ tuần trước. */
            ? `<span class="status-pill status-pill--degraded" title="${esc(account.agent_tat_ly_do || "không ghi lý do")}">agent TẮT</span>`
            : ""}
          <div class="token-slot" data-tokenslot="${account.id}"></div>
          <div class="account-actions">
            ${account.channel === "zalo_personal" ? `<button class="btn btn--sm" data-qr="${account.id}">Quét QR</button>` : ""}
            ${["facebook", "instagram"].includes(account.channel) && account.status === "pending" ? `<button class="btn btn--sm" data-subwebhook="${account.id}">Nhận tin</button>` : ""}
            ${account.status !== "active" ? `<button class="btn btn--sm" data-verify="${account.id}">Xác minh provider</button>` : `<button class="btn btn--sm" data-disable="${account.id}">Tạm ngắt</button>`}
            <button class="btn btn--sm btn--ghost" data-agentbat="${account.id}"
              data-bat="${account.agent_bat === false ? "1" : "0"}">${
              account.agent_bat === false ? "Bật agent" : "Tắt agent"}</button>
            ${hoSoAgent.ds.length ? `<select class="hsa-chon" data-hsagan="${account.id}"
              title="Hồ sơ agent trả lời kênh này">
              <option value="">Mặc định</option>
              ${hoSoAgent.ds.map((h) => `<option value="${esc(h.id)}"${
                h.id === account.agent_ho_so_id ? " selected" : ""}>${esc(h.ten)}</option>`).join("")}
            </select>` : ""}
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

  $$('[data-hsagan]').forEach((o) => o.addEventListener("change", async () => {
    try {
      const d = await api(`/channel-accounts/${o.dataset.hsagan}/ho-so-agent`, {
        method: "PUT",
        body: JSON.stringify({ ho_so_id: o.value || null }),
      });
      toast(d.ho_so_id
        ? `“${d.display_name}” dùng hồ sơ ${o.options[o.selectedIndex].text}.`
        : `“${d.display_name}” quay về cấu hình mặc định.`);
    } catch (e) { toast(e.message, true); loadKetNoi(); }
  }));

  $$('[data-agentbat]').forEach((button) => button.addEventListener("click", async () => {
    const bat = button.dataset.bat === "1";       // đang tắt -> bấm là bật
    /* Hỏi LÝ DO khi tắt, không hỏi khi bật.
     *
     * Tắt agent cho một kênh là quyết định người khác sẽ phải giải thích
     * lại sau vài tuần — thường là lúc có người hỏi "vì sao kênh này agent
     * không trả lời". Lý do đi vào cả cột lẫn nhật ký, và hiện ngay trên
     * thẻ kênh. */
    let ly_do = "";
    if (!bat) {
      ly_do = prompt(
        "Tắt agent cho kênh này. Tin khách VẪN vào và vẫn chuyển cho người —\n"
        + "hệ thống sẽ tự tạo một công việc cho mỗi hội thoại.\n\nLý do:", "");
      if (ly_do === null) return;
    }
    try {
      const d = await api(`/channel-accounts/${button.dataset.agentbat}/agent`, {
        method: "POST", body: JSON.stringify({ bat, ly_do }),
      });
      toast(d.agent_bat
        ? `Agent đã bật lại cho “${d.display_name}”.`
        : `Agent đã tắt cho “${d.display_name}”. Tin khách vẫn vào và chuyển cho người.`);
      loadKetNoi();
    } catch (e) { toast(e.message, true); }
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

/*
 * Kết nối Zalo OA bằng CẤP QUYỀN. Cùng khuôn với Meta ở trên.
 *
 * Khác một chỗ đáng nói: cửa sổ con KHÔNG tự đóng khi xong, vì nó còn hiện
 * địa chỉ webhook người dùng phải dán sang Zalo Developers — Zalo không có
 * API đăng ký webhook. Đóng hộ họ là lấy mất thứ duy nhất làm chiều nhận
 * tin chạy được.
 */
$("#btn-oauth-zalo-oa")?.addEventListener("click", async () => {
  const nut = $("#btn-oauth-zalo-oa");
  nut.disabled = true;
  try {
    const r = await api("/connect/zalo-oa/start");
    if (!r.url) throw new Error("Máy chủ không trả về địa chỉ cấp quyền");
    const cua_so = window.open(r.url, "ketnoi_zalo_oa", "width=620,height=760");
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

/* Bốn loại plugin, nói bằng tiếng Việt. Máy chủ chỉ biết mã (`tra_bang`…);
 * người vận hành chỉ cần biết nhãn. Bảng này là chỗ DUY NHẤT dịch hai chiều,
 * nên thêm loại thứ năm ở máy chủ mà quên đây thì test đọc form sẽ đỏ.
 *
 * `tham_so` là tham số mặc định: model điền gì vào công cụ. Người vận hành
 * hầu như không cần đụng — hai loại tra cứu luôn nhận đúng một thứ (điều
 * khách hỏi), chuyển người thì không nhận gì. Chỉ gọi API mới cần tự đặt,
 * vì tên tham số phải khớp chỗ `{ma}` trong địa chỉ. */
const PLUGIN_LOAI = {
  tra_bang: {
    nhan: "Tra bảng hỏi → đáp",
    giai_thich: "Bạn nạp một bảng hai cột. Khách hỏi trúng cột trái, agent trả lời bằng cột phải. Không khớp thì agent nói chưa có thông tin, không đoán.",
    tham_so: { ten: "khoa", mo_ta: "Điều khách đang hỏi, ví dụ tên sản phẩm hay tên chi nhánh" },
    thu: "Kem chống nắng",
  },
  tra_tai_lieu: {
    nhan: "Hỏi kho tri thức, giới hạn một nhóm tài liệu",
    giai_thich: "Như kỹ năng tìm kiến thức có sẵn, nhưng chỉ tra trong những tài liệu có tên chứa mẩu chữ bạn đặt. Dùng khi một chủ đề cần nguồn riêng, không lẫn tài liệu khác.",
    tham_so: { ten: "cau_hoi", mo_ta: "Câu hỏi của khách, giữ nguyên ý" },
    thu: "Bảo hành bao lâu?",
  },
  chuyen_chuyen_biet: {
    nhan: "Chuyển người kèm lý do riêng",
    giai_thich: "Gặp đúng tình huống này, agent dừng lại và giao cho người trực kèm một câu lý do bạn viết sẵn. Không tốn tiền, không trả lời thay.",
    tham_so: null,
    thu: "",
  },
  goi_api_doc: {
    nhan: "Gọi một hệ thống ngoài (chỉ đọc)",
    giai_thich: "Agent GET một địa chỉ HTTPS bạn cho phép và đọc kết quả. Máy chủ đó phải nằm trong KY_NANG_HOST_CHO_PHEP ở .env — lớp chặn này cố ý nằm ngoài dashboard.",
    tham_so: { ten: "ma", mo_ta: "Giá trị điền vào chỗ {ma} trong địa chỉ" },
    thu: "SP001",
  },
};

/* Mẫu có sẵn — người vận hành SỬA chứ không VIẾT, và đó là khác biệt giữa
 * dùng được và bỏ đó. Mỗi mẫu là một bản mô tả hoàn chỉnh; test đưa từng
 * mẫu qua `doc_ban_mo_ta` thật, nên mẫu sai không lọt ra được.
 *
 * Khoá mẫu phải ĐỦ RIÊNG: danh mục cửa hàng có bốn sản phẩm chứa chữ
 * "serum", nên một dòng "serum" trả lời thay cho cả bốn — chắc nịch, không
 * mơ hồ, nên cũng không có nhánh hỏi lại nào chạy. */
const PLUGIN_MAU = {
  bao_hanh: {
    nhan: "Bảo hành theo dòng sản phẩm",
    ten: "tra_bao_hanh",
    loai: "tra_bang",
    mo_ta: "Tra thời hạn bảo hành và hạn dùng sau khi mở nắp của một dòng sản phẩm theo tên dòng. Không dùng cho câu hỏi về đổi trả.",
    tham_so: [{ ten: "khoa", mo_ta: "Tên dòng sản phẩm khách hỏi", bat_buoc: true }],
    cau_hinh: { bang: {
      "Kem Chống Nắng": "12 tháng sau khi mở nắp",
      "Sữa Rửa Mặt": "12 tháng sau khi mở nắp",
      "Nước Tẩy Trang": "12 tháng sau khi mở nắp",
    } },
  },
  dia_chi: {
    nhan: "Địa chỉ và giờ mở cửa",
    ten: "tra_dia_chi_cua_hang",
    loai: "tra_bang",
    mo_ta: "Tra địa chỉ và giờ mở cửa của một chi nhánh theo tên khu vực hoặc tên đường. Không dùng cho câu hỏi giao hàng.",
    tham_so: [{ ten: "khoa", mo_ta: "Tên khu vực, quận hoặc tên đường khách hỏi", bat_buoc: true }],
    cau_hinh: { bang: {
      "Dĩ An": "90 Cây Da Xề, Đông Hoà, Dĩ An — 8h đến 21h hằng ngày",
      "Thủ Đức": "Số 1 Võ Văn Ngân, Thủ Đức — 8h đến 21h hằng ngày",
    } },
  },
  ban_buon: {
    nhan: "Chuyển bộ phận bán buôn",
    ten: "chuyen_ban_buon",
    loai: "chuyen_chuyen_biet",
    mo_ta: "Khách hỏi giá sỉ, mở đại lý, hợp tác phân phối hoặc mua số lượng lớn từ 20 sản phẩm trở lên.",
    tham_so: [],
    cau_hinh: { ly_do: "Khách hỏi hợp tác bán buôn hoặc mở đại lý" },
  },
  chinh_sach: {
    nhan: "Hỏi riêng tài liệu chính sách",
    ten: "tra_chinh_sach",
    loai: "tra_tai_lieu",
    mo_ta: "Tra các câu hỏi về chính sách đổi trả, hoàn tiền và bảo hành trong đúng nhóm tài liệu chính sách của cửa hàng.",
    tham_so: [{ ten: "cau_hoi", mo_ta: "Câu hỏi của khách, giữ nguyên ý", bat_buoc: true }],
    cau_hinh: { nhom_tai_lieu: "chinh-sach", k: 4 },
  },
};

/* Tên tiếng Việt → mã máy hợp lệ với `_TEN_RE` của máy chủ: chữ thường
 * không dấu, số, gạch dưới, bắt đầu bằng chữ, 3–40 ký tự.
 *
 * Luôn trả về một mã hợp lệ kể cả khi nhãn rỗng hay toàn ký hiệu — lỗi
 * "tên không hợp lệ" của máy chủ nói về chữ thường không dấu, đúng thứ ô
 * này sinh ra để giấu đi, nên không được để nó lộ ra lần nữa. */
function sinhMaPlugin(nhan) {
  let s = String(nhan || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase()
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/_+/g, "_");
  if (!/^[a-z]/.test(s)) s = "kn_" + s;
  s = s.slice(0, 40).replace(/_+$/g, "");
  while (s.length < 3) s += "_x";
  return s;
}

/* Đọc chữ dán vào bảng: mỗi dòng một cặp, cách nhau bằng tab (Excel), dấu
 * hai chấm, hoặc gạch đứng. Dòng trống bỏ qua; dòng không tách được thì giữ
 * nguyên ở cột trái để người nhìn thấy và tự sửa, thay vì mất im lặng. */
function docBangDan(text) {
  const ra = [];
  for (const dong of String(text || "").split(/\r?\n/)) {
    const d = dong.trim();
    if (!d) continue;
    let k = -1;
    for (const sep of ["\t", "|", ":"]) { const t = d.indexOf(sep); if (t > 0) { k = t; break; } }
    if (k < 0) { ra.push([d, ""]); continue; }
    ra.push([d.slice(0, k).trim(), d.slice(k + 1).trim()]);
  }
  return ra;
}

function themDongBang(khoa = "", gia_tri = "") {
  const tb = $("#plugin-bang tbody");
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input class="plugin-bang__khoa" placeholder="Hồ Chí Minh | Sài Gòn | TPHCM" maxlength="200"></td>
    <td><input class="plugin-bang__gia" placeholder="12 tháng sau khi mở nắp" maxlength="500"></td>
    <td><button type="button" class="btn btn--sm btn--ghost" data-bang-xoa title="Bỏ dòng">✕</button></td>`;
  tr.querySelector(".plugin-bang__khoa").value = khoa;
  tr.querySelector(".plugin-bang__gia").value = gia_tri;
  tb.appendChild(tr);
  return tr;
}

function docBang() {
  const bang = {};
  for (const tr of document.querySelectorAll("#plugin-bang tbody tr")) {
    const k = tr.querySelector(".plugin-bang__khoa").value.trim();
    const v = tr.querySelector(".plugin-bang__gia").value.trim();
    if (!k && !v) continue;
    if (!k || !v) throw new Error(`Dòng "${k || v}" thiếu một bên — cần đủ cả "khách hỏi về" và "agent trả lời".`);
    if (bang[k] !== undefined) throw new Error(`"${k}" xuất hiện hai lần trong bảng. Giữ một dòng thôi.`);
    bang[k] = v;
  }
  return bang;
}

function datBang(bang) {
  $("#plugin-bang tbody").innerHTML = "";
  for (const [k, v] of Object.entries(bang || {})) themDongBang(k, v);
  if (!Object.keys(bang || {}).length) { themDongBang(); themDongBang(); }
}

function themDongCauThu(hoi = "", mong_doi = "") {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input class="cauthu__hoi" placeholder="đi biển" maxlength="200"></td>
    <td><input class="cauthu__mong" placeholder="kháng nước" maxlength="200"></td>
    <td><button type="button" class="btn btn--sm btn--ghost" data-cauthu-xoa title="Bỏ câu thử">✕</button></td>`;
  tr.querySelector(".cauthu__hoi").value = hoi;
  tr.querySelector(".cauthu__mong").value = mong_doi;
  $("#plugin-cauthu tbody").appendChild(tr);
  return tr;
}

function docCauThu() {
  const ra = [];
  for (const tr of document.querySelectorAll("#plugin-cauthu tbody tr")) {
    const hoi = tr.querySelector(".cauthu__hoi").value.trim();
    const mong = tr.querySelector(".cauthu__mong").value.trim();
    /* Cột phải để trống là CÓ NGHĨA: câu ấy phải không khớp. Chỉ bỏ dòng
     * khi cả hai ô đều trống. */
    if (!hoi) continue;
    ra.push({ hoi, mong_doi: mong });
  }
  return ra;
}

function datCauThu(ds) {
  $("#plugin-cauthu tbody").innerHTML = "";
  for (const c of ds || []) themDongCauThu(c.hoi, c.mong_doi);
}

/* Kết quả câu thử sau mỗi lần Lưu. Trượt thì phải NHÌN THẤY, nên nó nằm
 * ngay ô kết quả chứ không phải một toast biến mất sau ba giây. */
function hienCauThu(ds) {
  if (!ds || !ds.length) return "";
  const truot = ds.filter((x) => !x.dat);
  const dong = (x) => `<div class="row">
      <span class="row__flag ${x.dat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${x.dat ? "Đạt" : "TRƯỢT"}: ${esc(x.hoi)}</span>
        <span class="row__sub row__sub--thu">${x.mong_doi
          ? "mong đợi có: " + esc(x.mong_doi)
          : "mong đợi KHÔNG khớp dòng nào"} · agent trả: ${esc(x.nhan_duoc)}</span>
      </span>
    </div>`;
  return `<p class="panel__note${truot.length ? " plugin-loi" : ""}">Câu thử: ${
    ds.length - truot.length}/${ds.length} đạt${
    truot.length ? " — sửa bảng hoặc sửa câu thử cho khớp lại." : "."}</p>`
    + ds.map(dong).join("");
}

/* Tên kỹ năng viết hoa cột trái để nhìn ra mẫu, nhưng mã máy mới là thứ gửi
 * đi — hiện nó ngay dưới ô để không có bất ngờ lúc lưu. */
function capNhatMaPlugin() {
  const f = $("#pluginform");
  if (!f) return;
  /* Ô tên còn trống thì hiện gạch ngang, không hiện mã.
   *
   * `sinhMaPlugin("")` buộc phải trả một mã HỢP LỆ vì máy chủ đòi thế,
   * nhưng đem mã ấy hiện ra là người vận hành đọc được một cái tên họ
   * chưa hề đặt, và tưởng hệ thống đã quyết hộ. */
  const nhan = f.elements.nhan.value.trim();
  $("#plugin-ma").textContent = nhan ? sinhMaPlugin(nhan) : "—";
}

function doiLoaiPlugin(loai, { giuThamSo = false } = {}) {
  const f = $("#pluginform");
  const meta = PLUGIN_LOAI[loai];
  if (!f || !meta) return;
  f.elements.loai.value = loai;
  $("#plugin-loai-giaithich").textContent = meta.giai_thich;
  for (const o of f.querySelectorAll("[data-cauhinh]")) o.hidden = o.dataset.cauhinh !== loai;
  const nangCao = $("#plugin-nangcao");
  const oThu = $("#plugin-thu-o");
  if (!meta.tham_so) {
    nangCao.hidden = true;
    oThu.hidden = true;
    f.elements.tham_so_ten.value = "";
    f.elements.tham_so_mo_ta.value = "";
  } else {
    nangCao.hidden = false;
    oThu.hidden = false;
    if (!giuThamSo) {
      f.elements.tham_so_ten.value = meta.tham_so.ten;
      f.elements.tham_so_mo_ta.value = meta.tham_so.mo_ta;
    }
    f.elements.thu_gia_tri.placeholder = meta.thu;
  }
  if (loai === "tra_bang" && !$("#plugin-bang tbody tr")) datBang({});
}

/* Nạp một plugin ĐÃ LƯU ngược vào form để sửa.
 *
 * Gán `.value` cho từng ô, không dựng HTML: bảng là chữ do người vận hành
 * gõ, và nó vẫn là chuỗi đi qua máy chủ trước khi về đây.
 *
 * Ô tên nhận lại MÃ MÁY chứ không phải một nhãn tiếng Việt đoán ngược ra
 * từ nó. `sinhMaPlugin` bỏ dấu nên không có đường về; đoán bừa một nhãn
 * rồi sinh lại mã khác đi là lưu ra plugin THỨ HAI, còn bản cũ vẫn nằm đó
 * với cấu hình cũ — hỏng im lặng, đúng kiểu repo này sợ. Mã máy đi qua
 * `sinhMaPlugin` cho lại chính nó, nên lưu là ghi đè đúng chỗ. */
function napPluginVaoForm(ten, bm) {
  const f = $("#pluginform");
  if (!f || !bm) return;
  f.reset();
  f.elements.nhan.value = ten;
  f.elements.mo_ta.value = bm.mo_ta || "";
  doiLoaiPlugin(bm.loai, { giuThamSo: true });
  const t = (bm.tham_so || [])[0];
  if (t) {
    f.elements.tham_so_ten.value = t.ten || "";
    f.elements.tham_so_mo_ta.value = t.mo_ta || "";
  }
  const ch = bm.cau_hinh || {};
  if (bm.loai === "tra_bang") { datBang(ch.bang || {}); datCauThu(bm.cau_thu); }
  if (bm.loai === "tra_tai_lieu") {
    f.elements.nhom_tai_lieu.value = ch.nhom_tai_lieu || "";
    f.elements.k.value = ch.k || 4;
  }
  if (bm.loai === "chuyen_chuyen_biet") f.elements.ly_do.value = ch.ly_do || "";
  if (bm.loai === "goi_api_doc") {
    f.elements.url.value = ch.url || "";
    f.elements.han_giay.value = ch.han_giay || 5;
  }
  capNhatMaPlugin();
  $("#plugin-ketqua").innerHTML = "";
  for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.remove("is-on");
  f.scrollIntoView({ block: "start", behavior: "smooth" });
  f.elements.mo_ta.focus();
}

function dienMauPlugin(ma) {
  const m = PLUGIN_MAU[ma];
  const f = $("#pluginform");
  if (!m || !f) return;
  f.reset();
  f.elements.nhan.value = m.nhan;
  f.elements.mo_ta.value = m.mo_ta;
  doiLoaiPlugin(m.loai);
  if (m.tham_so[0]) {
    f.elements.tham_so_ten.value = m.tham_so[0].ten;
    f.elements.tham_so_mo_ta.value = m.tham_so[0].mo_ta;
  }
  const ch = m.cau_hinh;
  if (m.loai === "tra_bang") datBang(ch.bang);
  if (m.loai === "tra_tai_lieu") { f.elements.nhom_tai_lieu.value = ch.nhom_tai_lieu; f.elements.k.value = ch.k || 4; }
  if (m.loai === "chuyen_chuyen_biet") f.elements.ly_do.value = ch.ly_do;
  if (m.loai === "goi_api_doc") { f.elements.url.value = ch.url; f.elements.han_giay.value = ch.han_giay || 5; }
  capNhatMaPlugin();
  $("#plugin-ketqua").innerHTML = "";
  for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.toggle("is-on", c.dataset.pluginMau === ma);
  f.elements.nhan.focus();
}

/* Đọc form thành bản mô tả. Dùng chung cho nút "Chạy thử" và nút "Lưu" —
 * hai đường khác nhau đọc form theo hai cách là chạy thử một thứ rồi lưu
 * một thứ khác, và người vận hành không có cách nào biết.
 *
 * Kiểm ở đây chỉ để nói lỗi bằng câu ngắn NGAY tại ô; bộ kiểm thật vẫn là
 * `doc_ban_mo_ta` ở máy chủ, và câu lỗi của nó cũng đã là tiếng Việt. */
function docFormPlugin() {
  const f = $("#pluginform");
  const g = (n) => (f.elements[n]?.value || "").trim();
  const loai = g("loai");
  const meta = PLUGIN_LOAI[loai];
  if (!meta) throw new Error("Chọn kỹ năng này làm gì trước.");
  if (!g("nhan")) throw new Error("Đặt tên kỹ năng trước — tiếng Việt có dấu cũng được.");
  if (g("mo_ta").length < 20) throw new Error("Mô tả quá ngắn. Viết rõ khi nào agent dùng và khi nào đừng dùng (ít nhất 20 ký tự).");

  let cau_hinh = {};
  if (loai === "tra_bang") {
    cau_hinh = { bang: docBang() };
    if (!Object.keys(cau_hinh.bang).length) throw new Error("Bảng đang trống. Thêm ít nhất một dòng.");
  } else if (loai === "tra_tai_lieu") {
    if (!g("nhom_tai_lieu")) throw new Error("Chọn hoặc gõ một mẩu tên nhóm tài liệu — bỏ trống thì kỹ năng này thành bản sao của tìm kiến thức.");
    cau_hinh = { nhom_tai_lieu: g("nhom_tai_lieu"), k: parseInt(g("k") || "4", 10) };
  } else if (loai === "chuyen_chuyen_biet") {
    if (!g("ly_do")) throw new Error("Viết câu người trực sẽ đọc.");
    cau_hinh = { ly_do: g("ly_do") };
  } else if (loai === "goi_api_doc") {
    if (!g("url").startsWith("https://")) throw new Error("Địa chỉ phải bắt đầu bằng https://");
    cau_hinh = { url: g("url"), han_giay: parseFloat(g("han_giay") || "5") };
  }

  const tham_so = [];
  if (meta.tham_so) {
    const ten = g("tham_so_ten") || meta.tham_so.ten;
    const mo_ta = g("tham_so_mo_ta") || meta.tham_so.mo_ta;
    tham_so.push({ ten, mo_ta, bat_buoc: true });
  }
  return { ten: sinhMaPlugin(g("nhan")), loai, mo_ta: g("mo_ta"), tham_so, cau_hinh,
           cau_thu: loai === "tra_bang" ? docCauThu() : [] };
}

/* Kết quả chạy thử thành câu người đọc được. Đây là dữ liệu do người vận
 * hành gõ vào bảng, nhưng vẫn là chuỗi đi vào innerHTML — esc() mọi thứ. */
function hienKetQuaThu(loai, r) {
  const dong = (nhan, gt, xau = false) => `<div class="row"><span class="row__flag ${
    xau ? "row__flag--halt" : "row__flag--auto"}"></span><span class="row__body"><span class="row__title">${
    esc(nhan)}</span><span class="row__sub row__sub--thu">${esc(gt)}</span></span></div>`;
  const ghiChu = r && r.ghi_chu ? dong("Agent được dặn", r.ghi_chu) : "";
  if (!r) return dong("Không có kết quả", "", true);
  if (r.loi) return dong("Lỗi", r.loi, true) + ghiChu;
  if (loai === "chuyen_chuyen_biet" || r.can_chuyen_nhan_vien) {
    return dong("Chuyển cho người", "Lý do người trực thấy: " + (r.ly_do || "")) + ghiChu;
  }
  if (r.tim_thay === false) {
    const nhieu = Array.isArray(r.nhieu_ket_qua) && r.nhieu_ket_qua.length
      ? " Khớp nhiều dòng: " + r.nhieu_ket_qua.join(", ") : "";
    return dong("Không tìm thấy", "Agent sẽ nói chưa có thông tin, không đoán." + nhieu, true) + ghiChu;
  }
  if (loai === "tra_bang") return dong("Tìm thấy: " + (r.khoa || ""), r.gia_tri || "") + ghiChu;
  if (loai === "tra_tai_lieu" && Array.isArray(r.doan)) {
    return r.doan.map((d) => dong("Tìm thấy trong " + (d.tai_lieu || ""), d.noi_dung || "")).join("") + ghiChu;
  }
  return dong("Tìm thấy", JSON.stringify(r).slice(0, 700)) + ghiChu;
}

/* Tên tài liệu đã nạp, cho ô "nhóm tài liệu" gợi ý. Tải MỘT lần khi mở
 * màn, không theo vòng 6 giây — vòng đó vẽ lại datalist là vẽ thừa. */
async function napNhomTaiLieuPlugin() {
  if (state.pluginNhomDaTai) return;
  try {
    const ds = await api("/knowledge");
    $("#plugin-nhom-ds").innerHTML = ds.map((d) => `<option value="${esc(d.title)}">`).join("");
    state.pluginNhomDaTai = true;
  } catch (e) { /* không có gợi ý thì vẫn gõ tay được */ }
}

function khoiTaoFormPlugin() {
  const f = $("#pluginform");
  if (!f || f.dataset.daKhoiTao) return;
  f.dataset.daKhoiTao = "1";
  $("#plugin-loai").innerHTML = Object.entries(PLUGIN_LOAI)
    .map(([ma, m]) => `<option value="${ma}">${esc(m.nhan)}</option>`).join("");
  $("#plugin-mau").innerHTML = Object.entries(PLUGIN_MAU)
    .map(([ma, m]) => `<button type="button" class="chip" data-plugin-mau="${ma}">${esc(m.nhan)}</button>`).join("");
  doiLoaiPlugin("tra_bang");
  capNhatMaPlugin();

  f.elements.nhan.addEventListener("input", capNhatMaPlugin);
  $("#plugin-loai").addEventListener("change", (e) => doiLoaiPlugin(e.target.value));
  $("#plugin-bang-them").addEventListener("click", () => themDongBang().querySelector("input").focus());
  $("#plugin-cauthu-them").addEventListener("click", () => themDongCauThu().querySelector("input").focus());
  $("#plugin-cauthu").addEventListener("click", (e) => {
    const b = e.target.closest("[data-cauthu-xoa]");
    if (b) b.closest("tr").remove();
  });
  $("#plugin-mau").addEventListener("click", (e) => {
    const c = e.target.closest("[data-plugin-mau]");
    if (c) dienMauPlugin(c.dataset.pluginMau);
  });
  $("#plugin-bang").addEventListener("click", (e) => {
    const b = e.target.closest("[data-bang-xoa]");
    if (b) b.closest("tr").remove();
  });
  /* Dán nhiều dòng từ Excel vào bất kỳ ô nào của bảng: mỗi dòng dán thành
   * một hàng, thay cho việc gõ từng ô. */
  $("#plugin-bang").addEventListener("paste", (e) => {
    const text = e.clipboardData?.getData("text") || "";
    if (!/[\r\n\t]/.test(text)) return;
    const cap = docBangDan(text);
    if (!cap.length) return;
    e.preventDefault();
    const tr = e.target.closest("tr");
    for (const [k, v] of cap) themDongBang(k, v);
    if (tr && !tr.querySelector(".plugin-bang__khoa").value && !tr.querySelector(".plugin-bang__gia").value) tr.remove();
  });
}

$("#plugin-thu")?.addEventListener("click", async () => {
  const hop = $("#plugin-ketqua");
  try {
    const bm = docFormPlugin();
    const args = {};
    if (bm.tham_so.length) {
      const v = $("#pluginform").elements.thu_gia_tri.value.trim();
      if (!v) throw new Error("Gõ một câu khách hỏi vào ô \"Thử với câu khách hỏi\" rồi bấm Chạy thử.");
      args[bm.tham_so[0].ten] = v;
    }
    hop.innerHTML = `<p class="empty">Đang chạy thử…</p>`;
    const r = await api("/ky-nang/plugin/thu", {
      method: "POST",
      body: JSON.stringify({ ban_mo_ta: bm, args }),
    });
    hop.innerHTML = hienKetQuaThu(bm.loai, r.ket_qua);
  } catch (e) {
    hop.innerHTML = `<p class="empty plugin-loi">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
});

$("#pluginform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const bm = docFormPlugin();
    const ket = await api("/ky-nang/plugin", { method: "POST", body: JSON.stringify(bm) });
    e.target.reset();
    doiLoaiPlugin("tra_bang");
    datBang({});
    capNhatMaPlugin();
    datCauThu([]);
    $("#plugin-ketqua").innerHTML = hienCauThu(ket.cau_thu);
    for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.remove("is-on");
    const truot = (ket.cau_thu || []).filter((x) => !x.dat).length;
    toast(truot
      ? `Đã lưu "${bm.ten}" — ${truot} câu thử TRƯỢT, xem bên dưới`
      : `Đã lưu và bật "${bm.ten}"`, !!truot);
    await loadKyNang();
  } catch (err) {
    $("#plugin-ketqua").innerHTML = `<p class="empty plugin-loi">${esc(err.message)}</p>`;
    toast(err.message, true);
  }
});

/* Ba cách thêm kỹ năng, mỗi cách một câu nói KHI NÀO dùng nó.
 *
 * Chỗ khó của màn này chưa bao giờ là số ô nhập, mà là câu "tôi nên dùng
 * đường nào". Trước đây hai form đặt cạnh nhau trông ngang hàng và không
 * chỗ nào trả lời câu đó. */
const THEM_CACH = {
  bang: {
    nhan: "Tự viết bảng hỏi đáp",
    giai_thich: "Cho số liệu ngắn của shop: phí ship, bảo hành, địa chỉ, giờ mở cửa. Bạn gõ bảng hai cột bằng tiếng Việt, không cần biết kỹ thuật. Đây là cách hay dùng nhất.",
  },
  goi: {
    nhan: "Cài gói có sẵn",
    giai_thich: "Khi một chủ đề cần cả hướng dẫn tư vấn, công cụ tra cứu và tài liệu đi cùng nhau. Gói có phiên bản và lịch sử, khôi phục được nếu bản mới tệ hơn.",
  },
  mcp: {
    nhan: "Nối máy chủ MCP",
    giai_thich: "Khi công cụ đã nằm ở hệ thống khác và bạn muốn agent gọi sang. Địa chỉ phải nằm trong danh sách cho phép ở .env, và công cụ mặc định chỉ đọc.",
  },
};

function doiCachThem(cach) {
  const meta = THEM_CACH[cach];
  if (!meta) return;
  $("#them-giaithich").textContent = meta.giai_thich;
  for (const c of document.querySelectorAll("#them-chon .chip")) {
    c.classList.toggle("is-on", c.dataset.them === cach);
  }
  for (const o of document.querySelectorAll("[data-them-o]")) {
    o.hidden = o.dataset.themO !== cach;
  }
}

/* Bốn nguồn, một hình dạng dòng.
 *
 * Kỹ năng viết sẵn và công cụ cắm thêm có hai hình dạng dữ liệu khác nhau
 * (một bên có `nhom`/`tat_thi_mat_gi`, bên kia có `loai`/`tham_so`), nên
 * hàm này chuẩn hoá về một `nguon` rồi mới vẽ. Trộn hai vòng lặp vẽ khác
 * nhau vào một danh sách là hai chỗ phải nhớ sửa mỗi lần đổi cột.
 *
 * `nguon` quyết định nút nào hiện, và điều đó KHÔNG phải để cho đẹp: chỗ
 * đi sửa mỗi loại một khác. Plugin rời sửa tại chỗ, công cụ của gói phải
 * cài lại gói, công cụ MCP phải đồng bộ lại máy chủ. Hiện nút Sửa cho cả
 * ba rồi để máy chủ từ chối là dạy người ta bỏ qua thông báo lỗi. */
function veDongKyNang(k) {
  const nguon = k.nguon;
  const bat = k.bat !== false;
  const huy_hieu = {
    viet_san: '<b class="pill">viết sẵn</b>',
    tu_tao: '<b class="pill pill--tu-tao">tự tạo</b>',
    goi: `<b class="pill">gói ${esc(k.goi || "")}</b>`,
    mcp: `<b class="pill">MCP · ${esc(k.mcp || "")}</b>`,
  }[nguon] || "";

  const truot = (k.khong_khop || []).length
    ? `<span class="row__sub row__sub--truot">
         Khách hỏi mà bảng chưa có: ${(k.khong_khop || []).map((x) =>
           /* Chữ model điền từ câu của khách, qua CSDL rồi vào innerHTML. */
           `<button type="button" class="chip" data-them-khoa="${esc(x.gia_tri)}"
              data-them-vao="${esc(k.ten)}" title="Thêm dòng này vào bảng"
              >${esc(x.gia_tri)} (${esc(String(x.so_lan))})</button>`).join(" ")}
       </span>`
    : "";

  const nut = nguon === "viet_san"
    ? (k.tat_duoc
        ? `<button type="button" class="btn btn--sm ${bat ? "btn--halt" : ""}"
             data-kynang="${esc(k.ten)}" data-bat="${bat ? "0" : "1"}">${
             bat ? "Tắt" : "Bật"}</button>`
        : "")
    : nguon === "tu_tao"
      ? `${k.ban_mo_ta ? `<button type="button" class="btn btn--sm"
             data-plugin-sua="${esc(k.ten)}">Sửa</button>
           <button type="button" class="btn btn--sm"
             data-plugin-lichsu="${esc(k.ten)}">Lịch sử</button> ` : ""}<button
             type="button" class="btn btn--sm btn--halt"
             data-plugin-xoa="${esc(k.ten)}">Xoá</button>`
      : "";

  return `<div class="row" data-nguon="${esc(nguon)}">
      <span class="row__flag ${bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(k.ten)} ${huy_hieu}
          ${k.muc_rui_ro === "hanh_dong" ? '<b class="pill pill--halt">HÀNH ĐỘNG</b>' : ""}
          ${nguon === "viet_san" && !k.tat_duoc ? '<b class="pill">không tắt được</b>' : ""}</span>
        <span class="row__sub">${esc(k.dong_phu)}</span>
        <span class="row__sub">${esc(k.tom_tat)}</span>
        ${k.tat_thi_mat_gi ? `<span class="row__sub"><em>Tắt thì:</em> ${esc(k.tat_thi_mat_gi)}</span>` : ""}
        ${truot}
      </span>
      <span class="row__side">${nut}</span>
    </div>`;
}

/* Gộp bốn nguồn về một hình dạng. Chuẩn hoá ở ĐÂY chứ không ở `veDongKyNang`
 * để hàm vẽ không phải biết hình dạng nào của máy chủ là của nguồn nào. */
function gopKyNang(d) {
  const ra = d.co_san.map((k) => ({
    ...k,
    nguon: "viet_san",
    dong_phu: `${NHOM_NHAN[k.nhom] || k.nhom} · ${RUI_RO_NHAN[k.muc_rui_ro] || k.muc_rui_ro}`
      + (k.can_erp ? " · cần ERP" : "")
      + (k.can_kho_tri_thuc ? " · cần kho tri thức" : "")
      + ` · gọi 7 ngày: ${k.so_lan_7_ngay || 0}`
      + (k.so_loi_7_ngay ? ` (${k.so_loi_7_ngay} lỗi)` : ""),
  }));
  for (const p of d.plugin) {
    ra.push({
      ...p,
      nguon: p.mcp ? "mcp" : p.goi ? "goi" : "tu_tao",
      tom_tat: p.mo_ta,
      dong_phu: (PLUGIN_LOAI[p.loai]?.nhan || p.loai)
        + (p.tham_so.length ? ` · tham số: ${p.tham_so.join(", ")}` : "")
        + ` · gọi 7 ngày: ${p.so_lan_7_ngay || 0}`
        + (p.so_loi_7_ngay ? ` (${p.so_loi_7_ngay} lỗi)` : ""),
    });
  }
  return ra;
}

function locKyNang(nguon) {
  state.locKyNang = nguon;
  for (const c of document.querySelectorAll("#kynang-loc .chip")) {
    c.classList.toggle("is-on", c.dataset.locNguon === nguon);
  }
  const map = { "viet-san": "viet_san", "tu-tao": "tu_tao", goi: "goi", mcp: "mcp" };
  for (const r of document.querySelectorAll("#kynang-tatca .row")) {
    r.hidden = nguon !== "tat-ca" && r.dataset.nguon !== map[nguon];
  }
}

async function loadKyNang() {
  khoiTaoFormPlugin();
  khoiTaoThemKyNang();
  napNhomTaiLieuPlugin();
  const d = await api("/ky-nang");
  const tat = d.co_san.filter((k) => !k.bat).length;
  $("#c-kynang").textContent = tat ? `${tat} tắt` : "";

  const tat_ca = gopKyNang(d);
  $("#kynang-tatca").innerHTML = tat_ca.map(veDongKyNang).join("");
  /* Trần 12 đếm CHUNG plugin rời, công cụ của gói và công cụ MCP. Ba danh
   * sách rời thì không chỗ nào hiện được tổng, và người vận hành chỉ biết
   * mình chạm trần đúng lúc bị từ chối. */
  $("#kynang-dem").textContent =
    `${tat_ca.length} kỹ năng · ${d.plugin.length}/${d.plugin_toi_da} suất cắm thêm đã dùng`;
  locKyNang(state.locKyNang || "tat-ca");

  try {
    await loadGoiKyNang();
  } catch (err) {
    // Lỗi của kho gói không được lan sang vòng làm mới 6 giây, và panel
    // phải NÓI là không tải được — "Chưa có gói nào." khi CSDL hỏng là xanh giả.
    $("#goi-ds").innerHTML = `<p class="empty">Không tải được gói kỹ năng: ${esc(err.message)}</p>`;
  }

  // Cùng lý do với gói: máy chủ MCP đọc riêng một bảng
  // (`mcp_may_chu`), lỗi ở đó (vault chưa cấu hình, cột thiếu) không được
  // làm chết cả màn Kỹ năng, và panel phải NÓI ra thay vì im lặng hiện
  // "Chưa có máy chủ MCP nào." — trông giống chưa từng ai nối, khác hẳn
  // sự thật là đã nối nhưng đang đọc lỗi.
  try {
    await loadMcp();
  } catch (err) {
    $("#mcp-ds").innerHTML = `<p class="empty">Không tải được máy chủ MCP: ${esc(err.message)}</p>`;
  }
}

function khoiTaoThemKyNang() {
  const hop = $("#them-chon");
  if (!hop || hop.dataset.daKhoiTao) return;
  hop.dataset.daKhoiTao = "1";
  doiCachThem("bang");
  hop.addEventListener("click", (e) => {
    const b = e.target.closest("[data-them]");
    if (b) doiCachThem(b.dataset.them);
  });
  $("#kynang-loc").addEventListener("click", (e) => {
    const b = e.target.closest("[data-loc-nguon]");
    if (b) locKyNang(b.dataset.locNguon);
  });
}

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
  const bk = e.target.closest("[data-them-khoa]");
  if (bk) {
    /* Bấm một khoá hay trượt là mở luôn form sửa với dòng ấy điền sẵn.
     * Nếu chỉ hiện danh sách thì người vận hành phải tự nhớ rồi tự gõ lại,
     * và bảng vẫn không lớn lên — đúng chỗ vòng cải thiện đứt. */
    try {
      const d = await api("/ky-nang");
      const p = d.plugin.find((x) => x.ten === bk.dataset.themVao);
      if (!p || !p.ban_mo_ta) { toast("Công cụ này sửa trong gói của nó", true); return; }
      napPluginVaoForm(p.ten, p.ban_mo_ta);
      const tr = themDongBang(bk.dataset.themKhoa, "");
      tr.querySelector(".plugin-bang__gia").focus();
      toast(`Điền câu trả lời cho "${bk.dataset.themKhoa}" rồi bấm Lưu và bật`);
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bl = e.target.closest("[data-plugin-lichsu]");
  if (bl) {
    const ten = bl.dataset.pluginLichsu;
    try {
      const ds = await api(`/ky-nang/plugin/${encodeURIComponent(ten)}/lich-su`);
      /* Vẽ ngay dưới ô kết quả của form, không mở hộp thoại: người đang so
       * bản cũ với bản đang chạy cần nhìn thấy cả hai. */
      $("#plugin-ketqua").innerHTML = ds.length
        ? `<p class="panel__note">Bản cũ của <b>${esc(ten)}</b> — khôi phục sẽ
             ghi đè bản đang chạy, và bản đang chạy vào lịch sử.</p>`
          + ds.map((x) => `<div class="row">
              <span class="row__flag row__flag--spend"></span>
              <span class="row__body">
                <span class="row__title">${esc(new Date(x.thay_luc).toLocaleString("vi-VN"))}</span>
                <span class="row__sub">người sửa: ${esc(x.thay_boi)}</span>
              </span>
              <span class="row__side"><button type="button" class="btn btn--sm"
                data-plugin-khoiphuc="${esc(ten)}" data-id="${esc(String(x.id))}"
                >Khôi phục</button></span>
            </div>`).join("")
        : `<p class="empty">${esc(ten)} chưa từng được sửa lần nào.</p>`;
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bkp = e.target.closest("[data-plugin-khoiphuc]");
  if (bkp) {
    const ten = bkp.dataset.pluginKhoiphuc;
    if (!confirm(`Khôi phục "${ten}" về bản này? Bản đang chạy sẽ vào lịch sử.`)) return;
    try {
      await api(`/ky-nang/plugin/${encodeURIComponent(ten)}/khoi-phuc/${encodeURIComponent(bkp.dataset.id)}`,
                { method: "POST" });
      $("#plugin-ketqua").innerHTML = "";
      toast(`Đã khôi phục "${ten}"`);
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bs = e.target.closest("[data-plugin-sua]");
  if (bs) {
    /* Đọc lại từ máy chủ chứ không giữ bản mô tả trong DOM: người khác có
     * thể vừa sửa chính plugin này, và nạp bản cũ vào form rồi bấm Lưu là
     * âm thầm quay ngược thay đổi của họ. */
    try {
      const d = await api("/ky-nang");
      const p = d.plugin.find((x) => x.ten === bs.dataset.pluginSua);
      if (!p || !p.ban_mo_ta) { toast("Công cụ này sửa trong gói của nó", true); return; }
      napPluginVaoForm(p.ten, p.ban_mo_ta);
      toast(`Đang sửa "${p.ten}" — bấm Lưu và bật để ghi đè`);
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

/* ---------------- gói kỹ năng ---------------- */
async function loadGoiKyNang() {
  const d = await api("/goi-ky-nang");
  $("#goi-ds").innerHTML = d.goi.length ? d.goi.map((g) => `<div class="row">
      <span class="row__flag ${g.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(g.ten)} <b class="pill">v${esc(g.phien_ban)}</b>${g.bat ? "" : ' <b class="pill pill--halt">tắt</b>'}</span>
        <span class="row__sub">${esc(g.mo_ta)}</span>
        <span class="row__sub">${g.so_cong_cu} công cụ · ${g.so_tai_lieu} tài liệu · gọi 7 ngày: ${g.so_lan_7_ngay}${g.so_loi_7_ngay ? " (" + g.so_loi_7_ngay + " lỗi)" : ""} · từ khoá: ${esc((g.tu_khoa || []).join(", "))}</span>
        <span class="row__sub" data-goi-lichsu-o="${esc(g.ten)}"></span>
      </span>
      <span class="row__side">
        <button type="button" class="btn btn--sm" data-goi-battat="${esc(g.ten)}" data-bat="${g.bat ? "0" : "1"}">${g.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm" data-goi-xuat="${esc(g.ten)}">Xuất</button>
        <button type="button" class="btn btn--sm" data-goi-lichsu="${esc(g.ten)}">Lịch sử</button>
        <button type="button" class="btn btn--sm btn--halt" data-goi-xoa="${esc(g.ten)}">Xoá</button>
      </span>
    </div>`).join("") : `<p class="empty">Chưa có gói nào. Tối đa ${d.goi_toi_da}. Mẫu: data/goi-ky-nang/tu-van-da-nhay-cam.example.json</p>`;
}

function docFormGoi() {
  const f = $("#goiform");
  const tep = $("#goi-tep").files[0];
  const chu = f.querySelector("[name=json]").value.trim();
  return { tep, chu };
}

async function caiGoiKyNang(chiKiem) {
  const { tep, chu } = docFormGoi();
  const hop = $("#goi-ketqua");
  try {
    /* Ưu tiên rõ ràng: đã chọn tệp thì TỆP thắng ô dán. Bản trước, nút Kiểm
     * bỏ qua tệp và lặng lẽ kiểm nội dung còn sót trong ô dán — người dùng
     * thấy "Hợp lệ" cho một gói KHÁC gói họ vừa chọn, rồi bấm Cài. */
    if (tep && !chiKiem) {
      // Tệp đi bằng FormData như gửi tệp trong hộp thư — KHÔNG đặt Content-Type,
      // trình duyệt tự thêm boundary.
      const fd = new FormData(); fd.append("tep", tep);
      const res = await fetch("/api" + "/goi-ky-nang/tep", { method: "POST", body: fd, credentials: "same-origin" });
      const d = await res.json();
      if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail));
      hop.innerHTML = `<p class="empty">Đã cài ${esc(d.ten)} v${esc(d.phien_ban)}.</p>`;
      toast("Đã cài và bật gói");
      await loadKyNang();
      return;
    }
    let tho;
    if (tep) {
      /* Nút Kiểm không được ghi gì, nên nó đọc tệp NGAY TRONG TRÌNH DUYỆT và
       * gửi JSON tới /kiem — không có endpoint kiểm-từ-tệp ở máy chủ. Với
       * .zip thì phải giải nén, mà bộ giải nén (goi.tu_zip) chỉ nằm trên
       * đường Cài; nói thẳng ra thay vì im lặng kiểm nhầm ô dán. */
      if (/\.zip$/i.test(tep.name)) {
        toast("Kiểm chỉ nhận .json; tệp .zip bấm Cài (máy chủ kiểm trước khi ghi)", true);
        return;
      }
      try { tho = JSON.parse(await tep.text()); }
      catch (e) { toast("Tệp không phải JSON hợp lệ: " + e.message, true); return; }
    } else {
      if (!chu) { toast("Dán JSON của gói hoặc chọn tệp", true); return; }
      try { tho = JSON.parse(chu); } catch (e) { toast("JSON không hợp lệ: " + e.message, true); return; }
    }
    const d = await api(chiKiem ? "/goi-ky-nang/kiem" : "/goi-ky-nang", { method: "POST", body: JSON.stringify(tho) });
    if (chiKiem) {
      hop.innerHTML = d.hop_le
        ? `<p class="empty">Hợp lệ: ${esc(d.tom_tat.ten)} v${esc(d.tom_tat.phien_ban)} · ${d.tom_tat.so_cong_cu} công cụ · ${d.tom_tat.so_tai_lieu} tài liệu · từ khoá ${esc(d.tom_tat.tu_khoa.join(", "))}</p>`
        : `<p class="empty">Không hợp lệ: ${esc(d.loi)}</p>`;
      return;
    }
    hop.innerHTML = `<p class="empty">Đã cài ${esc(d.ten)} v${esc(d.phien_ban)}.</p>`;
    toast("Đã cài và bật gói");
    await loadKyNang();
  } catch (e) { toast(e.message, true); }
}

$("#goi-kiem")?.addEventListener("click", () => caiGoiKyNang(true));
$("#goi-cai")?.addEventListener("click", () => caiGoiKyNang(false));
document.addEventListener("click", async (e) => {
  const bt = e.target.closest("[data-goi-battat]");
  if (bt) {
    try { await api(`/goi-ky-nang/${encodeURIComponent(bt.dataset.goiBattat)}/bat-tat`, { method: "POST", body: JSON.stringify({ bat: bt.dataset.bat === "1" }) }); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-goi-xoa]");
  if (bx) {
    if (!confirm(`Xoá gói "${bx.dataset.goiXoa}"? Lịch sử phiên bản vẫn giữ.`)) return;
    try { await api(`/goi-ky-nang/${encodeURIComponent(bx.dataset.goiXoa)}`, { method: "DELETE" }); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  const bxu = e.target.closest("[data-goi-xuat]");
  if (bxu) { window.open(`/api/goi-ky-nang/${encodeURIComponent(bxu.dataset.goiXuat)}/xuat`, "_blank"); return; }
  const bl = e.target.closest("[data-goi-lichsu]");
  if (bl) {
    try {
      const ds = await api(`/goi-ky-nang/${encodeURIComponent(bl.dataset.goiLichsu)}/lich-su`);
      const o = document.querySelector(`[data-goi-lichsu-o="${CSS.escape(bl.dataset.goiLichsu)}"]`);
      o.innerHTML = ds.length ? ds.map((h) => `v${esc(h.phien_ban)} (${esc(h.thay_boi)}) <button type="button" class="btn btn--sm" data-goi-khoiphuc="${esc(bl.dataset.goiLichsu)}" data-id="${h.id}">Khôi phục</button>`).join(" · ") : "Chưa có bản cũ.";
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bk = e.target.closest("[data-goi-khoiphuc]");
  if (bk) {
    try { await api(`/goi-ky-nang/${encodeURIComponent(bk.dataset.goiKhoiphuc)}/khoi-phuc/${encodeURIComponent(bkp.dataset.id)}`, { method: "POST" }); toast("Đã khôi phục"); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
  }
});

/* ---------------- máy chủ MCP ---------------- */

// Hai huy hiệu dùng chung cho cả bảng máy chủ và ô Kiểm — một chỗ đổi màu,
// không phải sửa ở hai nơi mỗi khi luật ĐỌC/GHI đổi.
const MCP_PILL_DOC = '<b class="pill">ĐỌC</b>';
const MCP_PILL_GHI = '<b class="pill pill--halt">GHI</b>';

function moTaCat120(s) {
  const t = String(s || "");
  return t.length > 120 ? t.slice(0, 120) + "…" : t;
}

async function loadMcp() {
  const d = await api("/mcp");
  $("#mcp-ds").innerHTML = d.may_chu.length ? d.may_chu.map((m) => {
    const sk = m.suc_khoe || {};
    const dongBo = sk.ok === true
      ? '<b class="pill">đồng bộ ok</b>'
      : sk.ok === false
      ? `<b class="pill pill--halt">lỗi đồng bộ${sk.loi ? ": " + esc(sk.loi) : ""}</b>`
      : "";
    const luc = sk.luc ? ` · lúc ${clock(sk.luc)}` : "";
    const bo = (sk.bo || []).length
      ? `<span class="row__sub row__sub--truot">Công cụ bị bỏ: ${
          sk.bo.map((b) => `${esc(b.ten)} (${esc(b.ly_do)})`).join(" · ")
        }</span>`
      : "";
    // Hàng máy chủ + hàng công cụ đi PHẲNG trong cùng một `#mcp-ds`, không
    // lồng `<div>` bên trong `<span class="row__body">` — lồng khối vào
    // trong phần tử dòng là HTML sai kiểu, trình duyệt tự "sửa" bằng cách
    // đẩy nó ra ngoài luồng .row, và lưới `.row { grid-template-columns }`
    // vỡ bố cục ngay từ hàng công cụ đầu tiên. Mỗi hàng công cụ tự nêu tên
    // máy chủ để không cần khối bao ngoài mà vẫn biết nó thuộc máy nào.
    const congCu = (m.cong_cu || []).map((c) => {
      const badge = c.ghi ? MCP_PILL_GHI : MCP_PILL_DOC;
      const goi7 = c.so_lan_7_ngay != null
        ? ` · gọi 7 ngày: ${c.so_lan_7_ngay}${c.so_loi_7_ngay ? " (" + c.so_loi_7_ngay + " lỗi)" : ""}`
        : "";
      const choPhepGhi = c.ghi ? `
          <label class="hint"><input type="checkbox" data-mcp-ghi
            data-may-chu="${esc(m.ten)}" data-ten="${esc(c.ten)}"
            ${c.ghi_cho_phep ? "checked" : ""}> cho phép ghi ngoài phòng thử</label>
          <span class="row__sub row__sub--truot">Bật rồi công cụ này SỬA được dữ liệu thật, không chỉ đọc.</span>`
        : "";
      return `<div class="row">
        <span class="row__flag ${c.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
        <span class="row__body">
          <span class="row__title">${esc(m.nhan)} · ${esc(c.ten)} ${badge}</span>
          <span class="row__sub">${esc(moTaCat120(c.mo_ta))}${goi7}</span>
          ${choPhepGhi}
        </span>
        <span class="row__side">
          <label class="hint"><input type="checkbox" data-mcp-cc
            data-may-chu="${esc(m.ten)}" data-ten="${esc(c.ten)}"
            ${c.bat ? "checked" : ""}> bật</label>
        </span>
      </div>`;
    }).join("");
    return `<div class="row">
      <span class="row__flag ${m.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.nhan)}${m.bat ? "" : ' <b class="pill pill--halt">tắt</b>'} ${dongBo}</span>
        <span class="row__sub">${esc(m.host)} · ${m.so_bat || 0}/${m.so_cong_cu || 0} công cụ bật${luc}</span>
        ${bo}
      </span>
      <span class="row__side">
        <button type="button" class="btn btn--sm" data-mcp-dongbo="${esc(m.ten)}">Đồng bộ</button>
        <button type="button" class="btn btn--sm ${m.bat ? "btn--halt" : ""}"
          data-mcp-battat="${esc(m.ten)}" data-bat="${m.bat ? "0" : "1"}">${m.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm btn--halt" data-mcp-xoa="${esc(m.ten)}">Xoá</button>
      </span>
    </div>${congCu}`;
  }).join("") : `<p class="empty">Chưa có máy chủ MCP nào. Tối đa ${d.may_chu_toi_da}.</p>`;
}

// Đọc form Nối máy chủ MCP. Trả về `null` (và tự toast lỗi) khi một dòng
// header không có dấu ":" — không ném exception ở đây vì lỗi này KHÔNG
// phải lỗi máy chủ, hỏi lại người gõ trước khi tốn một lượt gọi API.
function docFormMcp() {
  const f = $("#mcpform");
  const fd = new FormData(f);
  const ten = String(fd.get("ten") || "").trim();
  const nhan = String(fd.get("nhan") || "").trim();
  const dia_chi = String(fd.get("dia_chi") || "").trim();
  const headers = {};
  for (const dong_tho of String(fd.get("headers") || "").split("\n")) {
    const dong = dong_tho.trim();
    if (!dong) continue;
    const i = dong.indexOf(":");
    if (i < 0) {
      toast(`Dòng header không có dấu ":": "${dong}"`, true);
      return null;
    }
    headers[dong.slice(0, i).trim()] = dong.slice(i + 1).trim();
  }
  return { ten, nhan, dia_chi, headers: Object.keys(headers).length ? headers : null };
}

async function kiemMcp() {
  const dl = docFormMcp();
  if (!dl) return;
  if (!dl.dia_chi) { toast("Điền địa chỉ trước khi Kiểm", true); return; }
  const hop = $("#mcp-ketqua");
  try {
    const d = await api("/mcp/kiem", {
      method: "POST", body: JSON.stringify({ dia_chi: dl.dia_chi, headers: dl.headers }),
    });
    if (!d.ok) { hop.innerHTML = `<p class="empty">Không nối được: ${esc(d.loi)}</p>`; return; }
    hop.innerHTML = (d.cong_cu || []).map((c) => c.ly_do_bo
      ? `<div class="row"><span class="row__flag row__flag--halt"></span>
          <span class="row__body"><span class="row__title">${esc(c.ten)}</span>
          <span class="row__sub row__sub--truot">Bị bỏ: ${esc(c.ly_do_bo)}</span></span></div>`
      : `<div class="row"><span class="row__flag row__flag--auto"></span>
          <span class="row__body"><span class="row__title">${esc(c.ten)} ${c.ghi_goi_y ? MCP_PILL_GHI : MCP_PILL_DOC}</span>
          <span class="row__sub">${esc(moTaCat120(c.mo_ta))}</span></span></div>`
    ).join("") || '<p class="empty">Máy chủ không có công cụ nào.</p>';
  } catch (e) { toast(e.message, true); }
}

async function themMcp() {
  const dl = docFormMcp();
  if (!dl) return;
  if (!dl.ten || !dl.nhan || !dl.dia_chi) { toast("Điền đủ tên, nhãn và địa chỉ", true); return; }
  try {
    const d = await api("/mcp", {
      method: "POST",
      body: JSON.stringify({ ten: dl.ten, nhan: dl.nhan, dia_chi: dl.dia_chi, headers: dl.headers }),
    });
    /* 201 KHÔNG có nghĩa là đã nối được. Máy chủ vẫn được tạo khi lần đồng
     * bộ đầu hỏng — cố ý, để một lần mạng chập không làm mất bản ghi và bí
     * mật vừa mã hoá. Nhưng báo "Đã nối" cho một máy chủ chưa hề nối được
     * là người vận hành bỏ đi làm việc khác, còn agent thì thiếu công cụ:
     * sai địa chỉ, sai header và DNS hỏng đều trông y hệt một máy chủ thật
     * không có công cụ nào. Nói ra, kèm việc phải làm tiếp. */
    if (!d.ok) {
      $("#mcp-ketqua").innerHTML = `<p class="empty">Đã tạo "${esc(d.ten)}" nhưng chưa nối được: ${
        esc(d.loi || "không rõ lý do")} — sửa địa chỉ/header rồi bấm Đồng bộ.</p>`;
      toast(`Đã tạo "${d.ten}" nhưng chưa nối được máy chủ MCP`, true);
    } else {
      $("#mcp-ketqua").innerHTML = `<p class="empty">Đã nối "${esc(d.ten)}": ${d.so_bat}/${d.so_cong_cu} công cụ bật${
        d.so_bo ? ", " + d.so_bo + " bị bỏ" : ""}.</p>`;
      toast(`Đã nối máy chủ MCP "${d.ten}"`);
    }
    $("#mcpform").reset();
    mcpTenGoTay = false;
    await loadKyNang();
  } catch (e) { toast(e.message, true); }
}

/* Gợi ý ô Tên từ ô Nhãn (spec §5.5). Dùng lại `sinhMaPlugin` — cùng một
 * phép bỏ dấu, cùng một luật "luôn ra mã hợp lệ" — rồi cắt về 20 ký tự cho
 * khớp `_TEN_MAY_CHU_RE` ở máy chủ, vốn chặt hơn tên plugin (40).
 *
 * VÌ SAO PHẢI CÓ. Ô Tên đòi chữ thường không dấu, còn người vận hành nghĩ
 * bằng tiếng Việt có dấu; không gợi ý thì lỗi "tên không hợp lệ" xuất hiện
 * sau khi đã gõ xong cả form, ở đúng ô mà máy tự điền được. */
function sinhMaMcp(nhan) {
  return sinhMaPlugin(nhan).slice(0, 20).replace(/_+$/g, "");
}

/* Người đã tự gõ vào ô Tên thì THÔI gợi ý — đè lên chữ người đang gõ là
 * kiểu hỏng khó chịu nhất của mọi ô tự điền. Cờ được đặt lại khi form reset
 * (xem `themMcp`), vì form trống là một lần nhập mới. */
let mcpTenGoTay = false;

$("#mcpform")?.addEventListener("input", (e) => {
  const f = $("#mcpform");
  if (e.target === f.elements.ten) {
    mcpTenGoTay = String(f.elements.ten.value).trim() !== "";
    return;
  }
  if (e.target === f.elements.nhan && !mcpTenGoTay) {
    f.elements.ten.value = sinhMaMcp(f.elements.nhan.value);
  }
});

$("#mcp-kiem")?.addEventListener("click", kiemMcp);
$("#mcp-them")?.addEventListener("click", themMcp);

document.addEventListener("click", async (e) => {
  const bd = e.target.closest("[data-mcp-dongbo]");
  if (bd) {
    try {
      await api(`/mcp/${encodeURIComponent(bd.dataset.mcpDongbo)}/dong-bo`, { method: "POST" });
      toast("Đã đồng bộ với máy chủ MCP.");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bt = e.target.closest("[data-mcp-battat]");
  if (bt) {
    try {
      await api(`/mcp/${encodeURIComponent(bt.dataset.mcpBattat)}/bat-tat`, {
        method: "POST", body: JSON.stringify({ bat: bt.dataset.bat === "1" }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-mcp-xoa]");
  if (bx) {
    if (!confirm(`Xoá hẳn máy chủ MCP "${bx.dataset.mcpXoa}"? Mọi công cụ của nó cũng mất theo.`)) return;
    try {
      await api(`/mcp/${encodeURIComponent(bx.dataset.mcpXoa)}`, { method: "DELETE" });
      toast("Đã xoá máy chủ MCP.");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
  }
});

document.addEventListener("change", async (e) => {
  const cc = e.target.closest("[data-mcp-cc]");
  if (cc) {
    try {
      await api(`/mcp/${encodeURIComponent(cc.dataset.mayChu)}/cong-cu/${encodeURIComponent(cc.dataset.ten)}`, {
        method: "POST", body: JSON.stringify({ bat: cc.checked }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); cc.checked = !cc.checked; }
    return;
  }
  const gh = e.target.closest("[data-mcp-ghi]");
  if (gh) {
    try {
      await api(`/mcp/${encodeURIComponent(gh.dataset.mayChu)}/cong-cu/${encodeURIComponent(gh.dataset.ten)}`, {
        method: "POST", body: JSON.stringify({ ghi_cho_phep: gh.checked }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); gh.checked = !gh.checked; }
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


/* ---------------- phòng thử agent ---------------- */
// Phiên sống ở máy chủ (RAM); ở đây chỉ giữ id, lượt đã hiện và kỳ vọng
// của câu gợi ý vừa bấm. KHÔNG đưa vào vòng refresh() 6 giây: mỗi lượt
// là một lời gọi model, và người dùng cần đọc kết quả yên ổn.
state.phongThu = { phien: null, luot: [] };
state.phongThuDaTai = false;
let phongThuKyVong = null;

const NHAN_LUOI_MAU = {
  tran_hoi_thoai: "halt", tran_ngay: "halt", injection: "halt", tin_cay_thap: "assist",
  bat_buoc_chuyen: "halt", hua_khong_goi: "assist", chan_doan_y_te: "halt",
  cong_cu_chuyen_nguoi: "assist", cong_cu_yeu_cau: "assist", het_vong: "assist",
};

async function loadPhongThu() {
  state.phongThuDaTai = true;
  try {
    if (!state.phongThu.phien) {
      const p = await api("/phong-thu/phien", { method: "POST" });
      state.phongThu.phien = p.id;
    }
    const goiY = await api("/phong-thu/goi-y");
    $("#phongthu-goiy").innerHTML = Object.entries(goiY).map(([nhom, ds]) => `<div class="row">
        <span class="row__flag"></span>
        <span class="row__body"><span class="row__title">${esc(nhom)}</span>
        <span class="row__sub">${ds.map((c) => `<button type="button" class="btn btn--sm" data-goiy="${esc(c.id)}"
            data-hoi="${esc(c.hoi)}" data-kyvong='${esc(JSON.stringify(c.ky_vong))}'>${esc(c.hoi)}</button>`).join(" ")}</span></span>
      </div>`).join("");
    await veNganSachPhongThu();
  } catch (e) { toast(e.message, true); }
}

async function veNganSachPhongThu() {
  const ns = await api("/phong-thu/ngan-sach");
  $("#phongthu-ngansach").textContent = `Đã thử ${usd(ns.da_tieu)}${ns.tran > 0 ? " / trần " + usd(ns.tran) : ""}`;
}

function veChatPhongThu() {
  const box = $("#phongthu-chat");
  box.innerHTML = state.phongThu.luot.map((l) => `<div class="row">
      <span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Khách</span><span class="row__sub">${esc(l.khach)}</span></span>
    </div><div class="row">
      <span class="row__flag row__flag--${esc(l.tone)}"></span>
      <span class="row__body"><span class="row__title">Agent</span><span class="row__sub">${esc(l.agent)}</span>
      <span class="row__sub">${usd(l.cost_usd)} · ${l.latency_ms} ms${l.escalate ? " · CHUYỂN NGƯỜI" : ""}</span></span>
    </div>`).join("") || '<p class="empty">Chưa có lượt nào.</p>';
  box.scrollTop = box.scrollHeight;
}

function veBenTrongPhongThu(d) {
  const luoi = d.luoi_bat
    ? `<div class="row"><span class="row__flag row__flag--${esc(NHAN_LUOI_MAU[d.luoi_bat] || "assist")}"></span>
        <span class="row__body"><span class="row__title">Lưới bắt: ${esc(d.nhan_luoi || d.luoi_bat)}</span>
        <span class="row__sub">${esc(d.escalate_reason)}</span></span></div>`
    : `<div class="row"><span class="row__flag row__flag--auto"></span>
        <span class="row__body"><span class="row__title">Không lưới nào bắt</span></span></div>`;
  const congCu = d.cong_cu.length ? d.cong_cu.map((c, i) => `<details class="row">
      <summary class="row__body"><span class="row__title">${i + 1}. ${esc(c.ten)}${c.thu_nghiem ? " · ĐANG THỬ" : ""}</span>
      <span class="row__sub">vòng ${c.vong} · ${c.ms} ms</span></summary>
      <pre class="pre">${esc(JSON.stringify({ tham_so: c.tham_so, ket_qua: c.ket_qua }, null, 2))}</pre>
    </details>`).join("") : '<p class="empty">Không gọi công cụ nào.</p>';
  const cham = d.cham || {};
  const tuCam = (cham.tu_cam || []).length ? `Từ cấm: ${esc(cham.tu_cam.join(", "))}` : "Không có từ cấm";
  const ht = cham.hinh_thuc || {};
  const loiHt = Object.entries(ht).filter(([k, v]) => k !== "dat" && v && (!Array.isArray(v) || v.length)).map(([k]) => k);
  const boVang = cham.so_voi_bo_vang
    ? `<div class="row"><span class="row__flag row__flag--${cham.so_voi_bo_vang.dat ? "auto" : "halt"}"></span>
        <span class="row__body"><span class="row__title">So với bộ vàng: ${cham.so_voi_bo_vang.dat ? "ĐẠT" : "KHÔNG ĐẠT"}</span>
        <span class="row__sub">${esc([...(cham.so_voi_bo_vang.thieu || []).map((t) => "thiếu " + t),
          ...(cham.so_voi_bo_vang.cam || []).map((t) => "cấm " + t),
          ...(cham.so_voi_bo_vang.sai_chuyen ? ["sai chuyển người"] : [])].join(" · ") || "đủ từ khoá, đúng chuyển người")}</span></span></div>`
    : "";
  const nguon = d.sources || [];
  // Chi tiết từng vòng gọi model — số liệu thuần từ Reply.vong, không có
  // chuỗi máy chủ nào lọt vào (mọi trường đều là number), nên không cần esc().
  const cacVong = d.vong.map((v, i) => `<div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Vòng ${i + 1}: ${usd(v.cost_usd)} · ${v.latency_ms} ms</span>
      <span class="row__sub">${v.tokens_in} vào / ${v.tokens_out} ra token · ${v.so_cong_cu} công cụ</span></span></div>`).join("");
  $("#phongthu-bentrong").innerHTML = `${luoi}
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Độ tin cậy ${pct(d.confidence)}${d.grounded ? " · có căn cứ" : " · KHÔNG căn cứ"}</span>
      <span class="row__sub">${nguon.length ? esc(nguon.join(" · ")) : "không trích tài liệu nào"}</span></span></div>
    ${(d.goi_ky_nang || []).length ? `<div class="row"><span class="row__flag row__flag--spend"></span><span class="row__body"><span class="row__title">Gói kỹ năng kích hoạt</span><span class="row__sub">${esc(d.goi_ky_nang.join(" · "))}</span></span></div>` : ""}
    <h3 class="panel__head">Công cụ đã gọi</h3>${congCu}
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">${usd(d.cost_usd)} · ${d.latency_ms} ms · ${esc(d.model)}</span>
      <span class="row__sub">${d.vong.length} vòng · ${d.tokens_in} vào / ${d.tokens_out} ra token</span></span></div>
    ${cacVong}
    <h3 class="panel__head">Chấm nhanh</h3>
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">${tuCam}</span>
      <span class="row__sub">${loiHt.length ? "Lỗi hình thức: " + esc(loiHt.join(", ")) : "Hình thức đạt"}</span></span></div>
    ${boVang}`;
}

async function hoiPhongThu(cauHoi) {
  const q = (cauHoi || "").trim();
  if (!q) return;
  if (!state.phongThu.phien) await loadPhongThu();
  const body = { cau_hoi: q, ky_vong: phongThuKyVong };
  phongThuKyVong = null;
  try {
    const d = await api(`/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}/hoi`,
      { method: "POST", body: JSON.stringify(body) });
    state.phongThu.luot.push({ khach: q, agent: d.tra_loi, cost_usd: d.cost_usd, latency_ms: d.latency_ms,
      escalate: d.escalate, tone: d.luoi_bat ? (NHAN_LUOI_MAU[d.luoi_bat] || "assist") : "auto" });
    veChatPhongThu();
    veBenTrongPhongThu(d);
    await veNganSachPhongThu();
  } catch (e) { toast(e.message, true); }
}

$("#phongthu-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const o = e.target.querySelector("[name=cau_hoi]");
  const q = o.value;
  o.value = "";
  await hoiPhongThu(q);
});
// Xoá phiên trên máy chủ trước khi tạo hay bỏ hẳn — phiên bỏ đi thì trả
// RAM tiến trình ngay, không đợi dọn theo TTL 2 giờ (agent/core/phong_thu_phien.py).
async function xoaPhienPhongThuTrenMayChu() {
  if (!state.phongThu.phien) return;
  try {
    await api(`/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}`, { method: "DELETE" });
  } catch (e) { toast(e.message, true); }
}

$("#phongthu-moi")?.addEventListener("click", async () => {
  await xoaPhienPhongThuTrenMayChu();
  state.phongThu = { phien: null, luot: [] };
  state.phongThuDaTai = false;
  $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  veChatPhongThu();
  await loadPhongThu();
});
$("#phongthu-xoa")?.addEventListener("click", async () => {
  await xoaPhienPhongThuTrenMayChu();
  state.phongThu = { phien: null, luot: [] };
  state.phongThuDaTai = false;
  $("#phongthu-chat").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  toast("Đã xoá phiên thử");
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-goiy]");
  if (!b) return;
  $("#phongthu-form [name=cau_hoi]").value = b.dataset.hoi;
  try { phongThuKyVong = JSON.parse(b.dataset.kyvong); } catch { phongThuKyVong = null; }
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
