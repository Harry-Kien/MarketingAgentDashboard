/* TỆP SINH RA — ĐỪNG SỬA TAY. Mã nguồn ở dashboard/src/*.js; sửa ở đó rồi
   chạy: python -m scripts.dong_goi_dashboard */
/* ---------------- sổ điểm gắn tab (GAN_TAB) ----------------
 *
 * Tệp ĐẦU TIÊN của app.js, cố ý chỉ có một dòng mã: mô-đun nào nằm ở tệp
 * sau cũng đăng ký được NGAY LÚC TẢI, không phụ thuộc thứ tự tên tệp.
 *
 *   window.GAN_TAB["ns-nhan-vien"] = (o, ctx) => { o.innerHTML = "…"; };
 *
 * Hợp đồng (01b-dieu-huong.js thực hiện):
 *   · Khoá là id của tab (cc-*, ai-*, ns-*, ht-*, cv-*) hoặc của một khe gắn
 *     bên trong tab (`data-gan="ai-co-ban-nha-cung-cap"`).
 *   · Hàm được gọi MỘT lần, lần đầu tab hiện ra, với một <div> mới làm chỗ
 *     vẽ và `ctx = { id, api, toast, esc, quyen }`.
 *   · Khi đã gắn, phần `.tab__goc` (nội dung mặc định) bị ẩn — các khối
 *     nằm ngoài `.tab__goc` thì ở lại. Mỗi lần tab hiện lại, khe phát sự
 *     kiện `tab:hien` để mô-đun tự làm mới nếu muốn.
 *   · Hàm ném lỗi thì nội dung mặc định hiện lại và người dùng được báo:
 *     một mô-đun hỏng không được biến cả tab thành trang trắng im lặng.
 */
window.GAN_TAB = window.GAN_TAB || {};
/* Trạm điều độ — logic giao diện. Không framework, không build step. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { view: "hoithoai", tab: {}, convFilter: "all", orderFilter: "all", khoFilter: "all", openConv: null, openContact: null, contactQuery: "", timer: null };
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
  /* Riêng lời gọi ĐĂNG NHẬP: 401 ở đó không có nghĩa "phiên hết hạn" mà là
   * "cần mã 2FA" / "mã sai" / "sai mật khẩu" — máy chủ trả cả ba bằng 401,
   * kèm nội dung khác nhau. Đi nhánh hết phiên ở đây thì nội dung bị vứt
   * trước khi đọc: ô mã 2FA không bao giờ hiện, ai bật 2FA là tự khoá mình
   * ra ngoài, và người gõ sai mật khẩu được bảo "phiên đã hết hạn". Nên
   * 401 của /dang-nhap rơi xuống nhánh lỗi thường bên dưới, nơi JSON lỗi
   * được đọc và gắn vào `chi_tiet`. */
  if (res.status === 401 && path !== "/dang-nhap") {
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

/* Gán lại danh sách <option> cho một <select> mà KHÔNG làm mất lựa chọn.
 *
 * Vòng làm mới 6 giây dựng lại option của các ô chọn (đội, nhân viên, kênh,
 * khách để gộp). Gán `innerHTML` trần thì ô nhảy về option đầu: người vận
 * hành chọn "Đội Zalo" + "Lan", đứng đọc lại vài giây, bấm Thêm — và người
 * ĐẦU danh sách vào đội ĐẦU danh sách. Không lỗi, không toast, chỉ là dữ
 * liệu sai lặng lẽ.
 *
 * Danh sách không đổi thì không đụng gì cả (ô đang mở dở không bị đóng);
 * đổi thì gán lại rồi trả giá trị cũ nếu nó vẫn còn trong danh sách mới. */
function ganLuaChon(sel, html) {
  if (!sel) return;
  if (sel._nguonLuaChon === html) return;
  const cu = sel.value;
  sel.innerHTML = html;
  sel._nguonLuaChon = html;
  if ([...sel.options].some((o) => o.value === cu)) sel.value = cu;
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

/* ---------------- điều hướng ----------------
   doiMan(), nhóm "Cài đặt & Quản trị" và tab nằm ở 01b-dieu-huong.js. */

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
  /* Công tắc AI ở Cấu hình cơ bản và đèn ngắt khẩn cấp ở thanh trên là
     HAI mặt của cùng `runtime.enabled` — vẽ cả hai từ một chỗ, nên không
     bao giờ một bên nói "đang chạy" khi bên kia nói "đã ngắt". */
  const bat = $("#aiBat");
  if (bat) {
    bat.checked = !!rt.enabled;
    $("#aiBatNhan").textContent = rt.enabled ? "AI Agent đang BẬT" : "AI Agent đang TẮT";
  }
}

$("#aiBat")?.addEventListener("change", async (e) => {
  const bat = e.target.checked;
  try {
    applyRuntime(await api("/runtime", {
      method: "POST", body: JSON.stringify({ enabled: bat }),
    }));
    toast(bat ? "AI Agent đã bật cho mọi kênh. Hội thoại nhân viên đang giữ vẫn của nhân viên."
      : "AI Agent đã tắt. Tin khách vào thẳng hàng chờ người.");
  } catch (err) {
    // Máy chủ từ chối (thiếu quyền agent.dieu_khien…): trả công tắc về
    // đúng trạng thái đang chạy, không để nó nói dối.
    e.target.checked = !bat;
    toast(err.message, true);
  }
});

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

/* ---------------- điều hướng: thanh bên, nhóm Cài đặt, tab ----------------
 *
 * Cây menu theo phiếu việc của chủ dự án (20.11.2026): sáu màn nghiệp vụ,
 * rồi một nhóm "Cài đặt & Quản trị" bốn màn con, mỗi màn con chia tab.
 * Một tab là `<section class="tabpanel" id="…">` nằm thẳng trong `.view`;
 * id tab cũng là khoá điểm gắn trong `window.GAN_TAB` (00-gan-tab.js).
 */

/* Tên màn CŨ -> tab mới. Thông báo trên máy, nút "Cấu hình" ở màn Hệ thống
 * (`di_toi_man` do máy chủ trả) và mã cũ vẫn gọi doiMan("ca"),
 * doiMan("ketnoi")… — đổi tên mà không giữ bảng này thì mỗi lời gọi cũ là
 * một nút bấm không đi đâu, và không có gì báo lỗi. */
const MAN_CU = {
  ca: "cv-ca-truc",
  ketnoi: "cc-ket-noi",
  cauhinh: "ai-co-ban",
  trithuc: "ai-tri-thuc",
  kynang: "ai-ky-nang",
  phongthu: "ai-phong-thu",
  nhatky: "ht-nhat-ky",
};

/* Quyền để THẤY một tab — đủ MỘT quyền trong danh sách là thấy. Chỉ để
 * không mời người ta vào một màn toàn lỗi 403; chốt thật là `can_quyen`
 * ở máy chủ (agent/core/quyen.py), giấu ở đây không bảo vệ được gì. */
const QUYEN_TAB = {
  "cv-ca-truc": ["hoi_thoai.doc"],
  "cv-danh-sach": ["cong_viec.doc"],
  "cc-nhan": ["cau_hinh.doc", "khach.sua"],
  "cc-tu-dong": ["tra_loi_nhanh.sua", "dinh_tuyen.doc"],
  "cc-ket-noi": ["kenh.doc", "tich_hop.doc", "cau_hinh.doc"],
  "cc-sla": ["dinh_tuyen.doc"],
  "cc-dieu-phoi": ["dinh_tuyen.doc"],
  "ai-co-ban": ["agent.doc", "cau_hinh.doc"],
  "ai-tri-thuc": ["cau_hinh.doc"],
  "ai-ky-nang": ["ky_nang.doc"],
  "ai-chinh-sach": ["cau_hinh.doc"],
  "ai-phong-thu": ["phong_thu.dung"],
  "ns-nhan-vien": ["nguoi_dung.doc"],
  "ns-vai-tro": ["nguoi_dung.doc"],
  "ht-suc-khoe": ["cau_hinh.doc", "nhat_ky.doc"],
  "ht-sao-luu": ["khach.pii", "cau_hinh.doc"],
  "ht-nhat-ky": ["nhat_ky.doc"],
};
const QUYEN_MAN = {
  hoithoai: ["hoi_thoai.doc"],
  khachhang: ["khach.doc"],
  donhang: ["don.doc"],
  kho: ["kho.doc"],        // quyền riêng từ 0058 (trước dùng don.doc)
  nhansu: ["nguoi_dung.doc"],
  sohieu: ["bao_cao.doc"],
};

function duocThay(ds) {
  // Chưa biết quyền (chưa đăng nhập xong) thì không giấu gì: giấu trước rồi
  // hiện sau là thanh bên nhảy múa ngay lần tải đầu.
  if (!state.toiQuyen || !ds) return true;
  return ds.some((q) => state.toiQuyen.has(q));
}

function cacTab(man) {
  const v = $(`.view[data-view="${man}"]`);
  return v ? [...v.children].filter((c) => c.classList.contains("tabpanel")) : [];
}

function manCuaTab(id) {
  const t = document.getElementById(id);
  return t && t.classList.contains("tabpanel") ? t.closest(".view")?.dataset.view || null : null;
}

const tabDuocThay = (id) => duocThay(QUYEN_TAB[id]);

/* Một quyền đơn lẻ — dùng trong vòng làm mới cho tab gộp nhiều nguồn. */
const coQuyen = (q) => duocThay([q]);

function manDuocThay(man) {
  const tabs = cacTab(man);
  if (tabs.length) return tabs.some((t) => tabDuocThay(t.id));
  return duocThay(QUYEN_MAN[man]);
}

/* Tab đang mở của một màn: tab nhớ lần trước nếu còn được thấy, không thì
 * tab ĐẦU TIÊN được thấy. */
function tabCuaMan(man) {
  const tabs = cacTab(man).filter((t) => tabDuocThay(t.id));
  if (!tabs.length) return null;
  const nho = state.tab[man];
  return tabs.some((t) => t.id === nho) ? nho : tabs[0].id;
}

/* Tab đang HIỆN trên màn hình. */
function tabDangHien(id) {
  const man = manCuaTab(id);
  return !!man && state.view === man && tabCuaMan(man) === id;
}

/* Có mô-đun nào gắn vào (và gắn thành công) khe này chưa. */
const GAN_LOI = new Set();
function daGan(id) {
  return typeof window.GAN_TAB[id] === "function" && !GAN_LOI.has(id);
}

/* Tab đang hiện VÀ đang dùng nội dung mặc định — điều kiện để vòng làm mới
 * nạp dữ liệu cho nó. Đã có mô-đun thay thế thì nội dung cũ bị ẩn, nạp vào
 * đó là kéo dữ liệu đổ vào chỗ không ai nhìn (test_vong_lam_moi_khong_keo_thua). */
function dangMo(id) {
  return tabDangHien(id) && !daGan(id);
}

/* Gắn mô-đun vào MỘT khe (tab hoặc `[data-gan]` bên trong tab), một lần. */
function ganKhe(o) {
  const id = o && o.dataset.gan;
  if (!id || o._daGan || GAN_LOI.has(id)) return;
  const fn = window.GAN_TAB[id];
  if (typeof fn !== "function") return;
  o._daGan = true;
  const goc = [...o.children].find((c) => c.classList.contains("tab__goc"));
  const cho = document.createElement("div");
  cho.className = "tab__gan";
  cho.dataset.ganVao = id;
  if (goc) { goc.hidden = true; goc.after(cho); } else { o.append(cho); }
  try {
    fn(cho, { id, api, toast, esc, quyen: state.toiQuyen || new Set() });
  } catch (e) {
    /* Hỏng thì phải có người biết, và màn không được trắng: trả nội dung
       mặc định, báo bằng toast, ghi console cho người sửa. */
    GAN_LOI.add(id);
    cho.remove();
    if (goc) goc.hidden = false;
    console.error(`GAN_TAB["${id}"] hỏng:`, e);
    toast(`Mô-đun "${id}" lỗi khi mở — đang hiện nội dung mặc định.`, true);
  }
}

/* Gọi ở MỖI nhịp làm mới: mô-đun đăng ký muộn (sau lần đầu tab hiện) vẫn
 * được gắn, không bắt người dùng chuyển tab đi rồi quay lại. ganKhe() tự
 * bỏ qua khe đã gắn, nên gọi lặp không tốn gì. */
function ganTabDangHien() {
  const id = tabCuaMan(state.view);
  const o = id && document.getElementById(id);
  if (!o) return;
  ganKhe(o);
  $$("[data-gan]", o).forEach(ganKhe);
}

function veTab(man) {
  const id = tabCuaMan(man);
  const v = $(`.view[data-view="${man}"]`);
  if (!v || !id) return;
  state.tab[man] = id;
  $$(".tabbar__nut", v).forEach((b) => {
    const on = b.dataset.tab === id;
    b.hidden = !tabDuocThay(b.dataset.tab);
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  cacTab(man).forEach((t) => { t.hidden = t.id !== id; });
  const o = document.getElementById(id);
  ganKhe(o);
  $$("[data-gan]", o).forEach(ganKhe);
  o.dispatchEvent(new CustomEvent("tab:hien", { detail: { id } }));
  $$(".tab__gan", o).forEach((g) =>
    g.dispatchEvent(new CustomEvent("tab:hien", { detail: { id: g.dataset.ganVao } })));
}

/* MỘT chỗ đổi màn. `ten` là tên màn, tên màn cũ, hoặc id một tab. Trước
   đây logic này bị chép lại ở `moManKetNoi`, và mỗi bản chép là một chỗ có
   thể quên cập nhật khi thanh điều hướng đổi. `lamMoi = false` chỉ dành
   cho lúc dựng menu theo quyền: vòng làm mới đầu tiên chạy ngay sau đó. */
function doiMan(ten, tab, lamMoi = true) {
  ten = MAN_CU[ten] || ten;
  if (manCuaTab(ten)) { tab = ten; ten = manCuaTab(ten); }
  state.view = ten;
  if (tab) state.tab[ten] = tab;
  $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === ten));
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === ten));
  veTab(ten);
  if ($(`#railCaiDatCon [data-view="${ten}"]`)) moNhomCaiDat(true);
  dongMenuDiDong();
  if (lamMoi) refresh();
}

$$(".rail__item").forEach((btn) =>
  btn.addEventListener("click", () => doiMan(btn.dataset.view))
);

/* Nối nút tab với khung tab cho trình đọc màn hình (aria-labelledby). Dựng
   ở đây thay vì viết tay trong index.html: id nút suy ra từ id tab, nên đổi
   id tab không thể để lại một nhãn trỏ vào hư không. */
$$(".tabbar__nut").forEach((b) => {
  b.id = `${b.dataset.tab}-nut`;
  document.getElementById(b.dataset.tab)?.setAttribute("aria-labelledby", b.id);
});

/* Bấm tab, hoặc mũi tên trái/phải khi đang đứng trên thanh tab (mẫu tablist
   của WAI-ARIA — người dùng bàn phím không phải Tab qua từng nút). */
$$(".tabbar").forEach((bar) => {
  bar.addEventListener("click", (e) => {
    const b = e.target.closest(".tabbar__nut");
    if (b) doiMan(b.dataset.tab);
  });
  bar.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const nut = $$(".tabbar__nut", bar).filter((b) => !b.hidden);
    const i = nut.indexOf(document.activeElement);
    if (i < 0) return;
    const k = nut[(i + (e.key === "ArrowRight" ? 1 : nut.length - 1)) % nut.length];
    k.focus();
    doiMan(k.dataset.tab);
  });
});

/* ---- nhóm "Cài đặt & Quản trị" thu gọn được ---- */
function moNhomCaiDat(mo) {
  const con = $("#railCaiDatCon");
  if (!con) return;
  con.hidden = !mo;
  $("#railCaiDatNut").setAttribute("aria-expanded", mo ? "true" : "false");
  $("#railCaiDat").classList.toggle("is-mo", mo);
}
$("#railCaiDatNut")?.addEventListener("click", () =>
  moNhomCaiDat($("#railCaiDatCon").hidden));

/* ---- thanh bên ở khổ hẹp: ẩn hẳn, mở bằng nút ☰ ở thanh trên ---- */
function dongMenuDiDong() {
  $("#rail")?.classList.remove("is-mo");
  $("#railMo")?.setAttribute("aria-expanded", "false");
}
$("#railMo")?.addEventListener("click", () => {
  const mo = !$("#rail").classList.contains("is-mo");
  $("#rail").classList.toggle("is-mo", mo);
  $("#railMo").setAttribute("aria-expanded", mo ? "true" : "false");
});

/* Ẩn mục, tab, cả nhóm Cài đặt mà người này không có quyền. Gọi một lần
 * sau khi biết quyền (kiemPhien). Màn đang mở bị ẩn thì chuyển sang màn
 * đầu tiên còn thấy — không để người ta đứng trước một màn rỗng. */
function apDungQuyenMenu() {
  $$(".rail__item").forEach((b) => { b.hidden = !manDuocThay(b.dataset.view); });
  const nhom = $("#railCaiDat");
  if (nhom) nhom.hidden = !$$(".rail__item", nhom).some((b) => !b.hidden);
  $$(".tabbar__nut").forEach((b) => { b.hidden = !tabDuocThay(b.dataset.tab); });
  if (!manDuocThay(state.view)) {
    const dau = $$(".rail__item").find((b) => !b.hidden);
    if (dau) { doiMan(dau.dataset.view, undefined, false); return; }
  }
  veTab(state.view);
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
  dinhTuyen.thanhVien = c.members || [];
  dinhTuyen.canhBao = c.canh_bao || [];

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

  /* Đội hiện kèm THÀNH VIÊN. Trước đây chỉ có form "Thêm vào đội" mà không
     có danh sách, nên "đội này có ai" là câu không có chỗ trả lời. Đội rỗng
     là đội không giao được cho ai — nói thẳng. */
  $("#dtDoi").innerHTML = dinhTuyen.doi.length
    ? dinhTuyen.doi.map((d) => {
        const tv = dinhTuyen.thanhVien.filter((m) => m.team_id === d.id);
        const canh = new Set(dinhTuyen.canhBao.filter((c) => c.team_id === d.id).map((c) => c.user_id));
        return `<div class="row">
        <span class="row__flag row__flag--${d.status !== "active" ? "halt" : tv.length ? "auto" : "assist"}"></span>
        <div class="row__main">
          <b>${esc(d.name)}</b>
          <span class="row__sub">${esc(d.description || "—")}</span>
          <span class="row__sub">${tv.length
            ? tv.map((m) => `<span class="pill${canh.has(String(m.user_id)) ? " pill--warn" : ""}">${
                esc(m.ho_ten || m.ten_dang_nhap)} · tối đa ${m.max_active}${m.is_available ? "" : " · nghỉ"}</span>`).join(" ")
            : '<span class="pill pill--warn">chưa có ai — không giao được cho ai</span>'}</span>
        </div>
      </div>`;
      }).join("")
    : '<p class="empty">Chưa có đội nào.</p>';

  $("#dtCanhBao").innerHTML = dinhTuyen.canhBao.map((c) => `<div class="row">
      <span class="row__flag row__flag--halt"></span>
      <div class="row__main"><span class="row__sub">${esc(c.ly_do)}</span></div>
    </div>`).join("");

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
          <span class="row__sub">trả lời đầu ${s2.first_response_minutes} phút · xong ${s2.resolution_minutes} phút${
            s2.business_hours && s2.business_hours.bat_dau != null
              ? ` · giờ riêng ${s2.business_hours.bat_dau}h–${s2.business_hours.ket_thuc}h` : ""}</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa đặt hạn nào.</p>';

  const oDoi = dinhTuyen.doi
    .map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  /* ganLuaChon, KHÔNG gán innerHTML trần: hàm này chạy lại mỗi 6 giây, và
     gán trần là ô chọn nhảy về đầu giữa lúc người ta đang chọn — bấm Thêm
     là thêm NHẦM người vào NHẦM đội, không lỗi nào hiện ra. */
  ganLuaChon($("#dtChonDoi"), oDoi);
  ganLuaChon($("#dtLuatDoi"), oDoi);
  const dtThieu = (ten) => dinhTuyen.loi.includes(ten)
    ? `<option value="">— không đọc được danh sách ${ten}, thiếu quyền? —</option>`
    : "";
  ganLuaChon($("#dtChonNguoi"), dtThieu("nhân viên") + dinhTuyen.nguoi
    .filter((n) => !n.khoa)
    .map((n) => `<option value="${esc(n.id)}">${esc(n.ho_ten || n.ten_dang_nhap)}</option>`)
    .join(""));
  const oKenh = '<option value="">mọi kênh</option>' + dtThieu("kênh")
    + dinhTuyen.kenh
      .map((k) => `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`)
      .join("");
  ganLuaChon($("#dtChonKenh"), oKenh);
  ganLuaChon($("#dtSlaKenh"), oKenh);
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
    /* Hai ô trống = {} (giờ chung). Điền một ô mà bỏ ô kia thì gửi nguyên
       để máy chủ trả 422 có câu chữ — đoán hộ ô còn lại là đặt một giờ làm
       việc người quản trị chưa từng chọn. */
    business_hours: (d.bat_dau === "" && d.ket_thuc === "") ? {}
      : { bat_dau: d.bat_dau === "" ? null : Number(d.bat_dau),
          ket_thuc: d.ket_thuc === "" ? null : Number(d.ket_thuc) },
    active: true,
  }));
});

/* ==================== Đếm trước khi xoá (có duyệt) ====================
 *
 * `/api/data-retention/jobs` có từ lâu, không màn hình nào gọi. Điều quan
 * trọng nhất về nó: máy chủ KHÔNG có bộ thực thi xoá cho luồng này — việc
 * duy nhất nó làm được là ĐẾM số bản ghi sẽ bị ảnh hưởng (`execute-dry-run`),
 * sau khi một người KHÁC người tạo đã duyệt. Màn hình phải nói đúng như
 * vậy; gọi nó là "xoá có duyệt" là hứa một việc máy chủ không làm.
 */

const RT_TRANG_THAI = {
  pending_approval: ["chờ người khác duyệt", "assist"],
  approved: ["đã duyệt · chưa chạy đếm", "auto"],
  completed: ["đã đếm", "auto"],
  cancelled: ["đã huỷ", "halt"],
};

function rtKetQua(r) {
  if (!r || !Object.keys(r).length) return "";
  const ten = { conversations: "hội thoại", messages: "tin nhắn", attachments: "tệp",
                contact_points: "danh tính", tags: "nhãn", notes: "ghi chú", consents: "đồng ý" };
  return Object.entries(r).filter(([, v]) => v > 0)
    .map(([k, v]) => `${v} ${ten[k] || k}`).join(" · ") || "không có gì để xoá";
}

async function loadRetention() {
  const o = $("#dsRetention");
  if (!o) return;
  if (!state.toiQuyen.has("khach.xoa")) {
    o.innerHTML = '<p class="empty">Cần quyền khach.xoa để xem mục này.</p>';
    return;
  }
  let ds;
  // Khoá là `jobs`, không phải `items` như outbox. Bản đầu đọc `.items` và
  // panel báo "chưa có yêu cầu" mãi mãi — kịch bản nghiệm thu 11 bắt được.
  try { ds = (await api("/data-retention/jobs")).jobs || []; }
  catch (e) { o.innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  $("#rtNote").textContent = ds.length
    ? `${ds.filter((j) => j.status === "pending_approval").length} đang chờ duyệt`
    : "chưa có yêu cầu nào";
  o.innerHTML = ds.length ? ds.map((j) => {
    let [nhan, co] = RT_TRANG_THAI[j.status] || [j.status, "assist"];
    const cua_toi = String(j.requested_by) === String(state.toiId);
    const nut = [];
    /* Phiếu đã tiêu cho một lần xoá thật. Trạng thái trong CSDL vẫn là
       "approved", nên không có nhánh này thì nó hiện y như phiếu còn dùng
       được — kèm nút Chạy đếm và Huỷ, cả hai đều vô nghĩa với một phiếu đã
       hết hiệu lực. */
    const da_dung = !!j.xoa_thuc_hien_luc;
    if (da_dung) {
      nhan = "đã dùng để xoá · không dùng lại được";
      co = "halt";
    } else if (j.status === "pending_approval") {
      /* Người tạo không tự duyệt được — máy chủ chặn (409). Ẩn nút với họ
         để không tạo ra một cú bấm chắc chắn thất bại. */
      if (!cua_toi) nut.push(`<button type="button" class="btn btn--sm" data-rtduyet="${esc(j.id)}">Duyệt</button>`);
      nut.push(`<button type="button" class="btn btn--sm btn--ghost" data-rthuy="${esc(j.id)}">Huỷ</button>`);
    } else if (j.status === "approved") {
      /* Chạy đếm đếm theo `contact_id`. Phiếu xin từ màn Nhật ký khoá theo
         số điện thoại và thường không gắn khách nào — máy chủ từ chối
         (409 "không còn gắn với khách hàng"). Ẩn nút thay vì để nó trả lỗi:
         màn PDPD ở trên đã hiện sẵn đơn và hội thoại sẽ mất. */
      if (j.dry_run && j.contact_id) nut.push(`<button type="button" class="btn btn--sm" data-rtdem="${esc(j.id)}">Chạy đếm</button>`);
      nut.push(`<button type="button" class="btn btn--sm btn--ghost" data-rthuy="${esc(j.id)}">Huỷ</button>`);
    }
    return `<div class="row">
      <span class="row__flag row__flag--${co}"></span>
      <div class="row__main">
        <b>${esc(j.kind === "delete" ? "Xoá" : j.kind === "export" ? "Xuất" : "Lưu trữ")} · ${
          /* Phiếu xin từ màn Nhật ký khoá theo SỐ, không theo khách — và số
             ấy bị xoá khỏi phiếu ngay khi phiếu được dùng, nên có lúc không
             còn gì để hiện. Nói "không còn hiển thị" chứ đừng in "null…". */
          esc(j.contact_id ? "khách " + String(j.contact_id).slice(0, 8) + "…"
              : j.sdt_che ? "số " + j.sdt_che
              : "số đã ẩn sau khi xoá")
        }${cua_toi ? " · bạn tạo" : ""}</b>
        <span class="row__sub">${esc(j.reason || "")}</span>
        <span class="row__sub">${esc(nhan)} · ${clock(j.requested_at)}${j.result && Object.keys(j.result).length ? " · " + esc(rtKetQua(j.result)) : ""}</span>
      </div>
      <div class="row__side">${nut.length ? `<span class="row__nut">${nut.join("")}</span>` : ""}</div>
    </div>`;
  }).join("") : '<p class="empty">Chưa có yêu cầu nào. Tạo từ hồ sơ khách ở màn Khách hàng.</p>';
}

$("#dsRetention")?.addEventListener("click", async (e) => {
  const duyet = e.target.closest("[data-rtduyet]");
  const dem = e.target.closest("[data-rtdem]");
  const huy = e.target.closest("[data-rthuy]");
  const nut = duyet || dem || huy;
  if (!nut) return;
  const id = duyet?.dataset.rtduyet || dem?.dataset.rtdem || huy?.dataset.rthuy;
  const duong = duyet ? "approve" : dem ? "execute-dry-run" : "cancel";
  nut.disabled = true;
  try {
    const r = await api(`/data-retention/jobs/${id}/${duong}`, { method: "POST" });
    toast(duyet ? "Đã duyệt. Giờ bấm Chạy đếm."
      : dem ? `Đã đếm: ${rtKetQua(r.result)}.` : "Đã huỷ yêu cầu.");
    await loadRetention();
  } catch (err) { toast(err.message, true); nut.disabled = false; }
});

/* Tạo yêu cầu đếm từ hồ sơ khách. Luôn dry_run: máy chủ không thực thi gì
   khác, và gửi dry_run=false là tạo một yêu cầu mãi mãi "đã duyệt" mà không
   bao giờ chạy. */
async function rtYeuCauDem(contactId) {
  const d = await hoiHop({
    tieu_de: "Đếm dữ liệu sẽ xoá",
    phu: "Chỉ đếm, chưa xoá gì. Một người khác phải duyệt ở Hệ thống & Nhật ký → Sao lưu & Bảo trì. Lý do ghi vào nhật ký.",
    truong: [{ name: "ly_do", label: "Lý do", value: "Khách yêu cầu xoá dữ liệu",
               required: true, maxlength: 500 }],
    nut: "Tạo yêu cầu",
  });
  if (!d || !d.ly_do) return;
  try {
    await api(`/contacts/${contactId}/retention-jobs`, {
      method: "POST",
      body: JSON.stringify({ kind: "delete", reason: d.ly_do, dry_run: true }),
    });
    toast("Đã tạo yêu cầu. Một người khác cần duyệt ở Hệ thống & Nhật ký → Sao lưu & Bảo trì.");
  } catch (e) { toast(e.message, true); }
}

/* ==================== Sức khoẻ từng kênh ==================== */

/* Uỷ quyền lên #contactdetail: khung chi tiết dựng lại innerHTML mỗi lần
   chọn khách, gắn listener lên nút thì mỗi lần dựng lại phải gắn lại. */
$("#contactdetail")?.addEventListener("click", (e) => {
  const b = e.target.closest("[data-contact-rt]");
  if (b) rtYeuCauDem(b.dataset.contactRt);
});

async function kenhSucKhoe(nut) {
  const id = nut.dataset.health;
  const o = document.querySelector(`[data-tokenslot="${id}"]`);
  nut.disabled = true;
  try {
    const d = (await api(`/channel-accounts/${id}/health`)).latest;
    const html = d
      ? `<span class="row__sub">Lần kiểm gần nhất ${clock(d.observed_at)}: <b>${esc(ACCOUNT_STATUS_LABEL[d.status] || d.status)}</b> · <code>${esc(d.code || "")}</code></span>`
      : '<span class="row__sub">Chưa có lần kiểm nào — bấm Xác minh provider.</span>';
    state.sucKhoeKenh = state.sucKhoeKenh || {};
    state.sucKhoeKenh[id] = html;      // để lần dựng lại thẻ vẫn còn
    if (o) o.innerHTML = html;
  } catch (e) { toast(e.message, true); }
  finally { nut.disabled = false; }
}

/* Bấm ảnh trên dòng kho -> xem lớn. Uỷ quyền lên #khoRows vì danh sách dựng
   lại mỗi vòng làm mới; gắn lên từng ảnh là gắn lại mãi. */
$("#khoRows")?.addEventListener("click", (e) => {
  const a = e.target.closest("[data-xemanh]");
  if (!a) return;
  $("#anhLonImg").src = a.src;
  $("#anhLonTen").textContent = a.closest(".row")?.querySelector("b, .row__title")?.textContent || a.dataset.xemanh;
  $("#anhLon").classList.remove("is-off");
});
const anhLonDong = () => $("#anhLon").classList.add("is-off");
$("#anhLonDong")?.addEventListener("click", anhLonDong);
$("#anhLon")?.addEventListener("click", (e) => { if (e.target === e.currentTarget) anhLonDong(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#anhLon")?.classList.add("is-off"); });

/* BÁO CÓ KHÁCH CẦN NGƯỜI ngay trên máy người trực.
 *
 * Trước 29.10.2026, chuyển người trên Zalo, Instagram, WhatsApp, chat web chỉ
 * làm con số ở mục Ca trực nhảy lên — ai đang ở màn khác, hay đang ở tab
 * khác, thì không thấy gì. Hai lớp, cả hai không cần máy chủ gửi gì thêm:
 *   - tiêu đề tab mang số việc đang chờ: thấy được cả khi tab nằm sau;
 *   - thông báo của hệ điều hành khi số hội thoại chờ người TĂNG (không báo
 *     lần tải đầu: mở dashboard ra mà bị dội mười thông báo cũ là học cách
 *     tắt nó).
 * Ngoài dashboard thì đi đường webhook (canh_gac.bao_nhan_vien). */
const TIEU_DE_GOC = document.title;
let soCanNguoiTruoc = null;

function baoKhachCanNguoi(escalated, tong) {
  document.title = tong ? `(${tong}) ${TIEU_DE_GOC}` : TIEU_DE_GOC;
  const tang = soCanNguoiTruoc !== null && escalated > soCanNguoiTruoc;
  soCanNguoiTruoc = escalated;
  if (!tang || !("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const tb = new Notification("Khách cần người trả lời", {
      body: `${escalated} hội thoại đang chờ người · mở Công việc → Tổng quan ca trực để nhận`,
      tag: "khach-can-nguoi",
    });
    tb.onclick = () => { window.focus(); doiMan("ca"); tb.close(); };
  } catch { /* Vài trình duyệt di động chỉ cho thông báo qua service worker. */ }
}

function veNutThongBao() {
  const o = $("#batThongBao");
  if (!o) return;
  if (!("Notification" in window) || Notification.permission === "granted") { o.hidden = true; return; }
  o.hidden = false;
  if (Notification.permission === "denied") {
    o.textContent = "Trình duyệt đang chặn thông báo của trang này — mở cài đặt trang (biểu tượng ổ khoá) để cho phép, nếu muốn được báo khi có khách cần người.";
    return;
  }
  o.innerHTML = 'Máy này chưa được báo khi có khách cần người. <button type="button" class="btn btn--sm" id="nutThongBao">Bật thông báo</button>';
  $("#nutThongBao").addEventListener("click", async () => {
    try { await Notification.requestPermission(); } catch { /* trình duyệt cũ */ }
    veNutThongBao();
  });
}
veNutThongBao();

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
  baoKhachCanNguoi(o.conversations.escalated || 0,
    (o.conversations.waiting || 0) + (o.conversations.escalated || 0));
  $("#c-hoithoai").textContent = o.conversations.total || 0;
  $("#rail-cost").textContent = usd(o.cost.total_usd);

  $("#readout").innerHTML = [
    cell("Hội thoại 24 giờ", o.conversations.total, "cuộc", null, "auto"),
    /* "AI tự lo" đếm theo sự kiện: hội thoại có tin AI trong 24 giờ mà
       không ai can thiệp (chuyển người, tiếp quản, nhân viên nhắn, DUYỆT
       NHÁP). Ô cũ chia `status = auto` cho tổng — duyệt nháp lật assist
       thành auto, nên hội thoại người duyệt từng câu cũng thành "tự xử lý". */
    cell("AI tự lo (không người can thiệp)", pct(o.conversations.containment),
         `${o.conversations.ai_tu_lo}/${o.conversations.ai} có AI`,
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
  ].join("");

  /* limit=200, không phải 12. Khung này là HÀNG ĐỢI, không phải bản tin:
     cắt ở 12 nghĩa là khi có 20 khách chờ thì 8 người biến mất khỏi màn
     hình — và với thứ tự chờ-lâu-nhất-trước do API trả về, 8 người mất đi
     lại chính là 8 người mới nhắn. Thà cuộn dài còn hơn giấu người đang đợi.
     API đã xếp sẵn ai chờ lâu nhất lên đầu. */
  /* Khối dưới đây (`#queue`) chỉ tồn tại trong tab Tổng quan ca trực. Nạp nó khi
     đang mở màn khác là đổ dữ liệu vào DOM bị ẩn.
     ĐO ĐƯỢC 22.09.2026 trên dashboard đang chạy: `loadOverview()` phát BA
     request (hồi còn hàng chờ video), và `refresh()` gọi nó mỗi 6 giây bất
     kể màn nào đang mở — tức 30 request/phút mỗi tab, trong đó hai phần ba
     kéo tới 200 hội thoại và 30 video mà không ai nhìn. Nhân với số người
     trực thì đó là tải thật trên máy chủ, đổi lấy không gì cả.

     Vẫn giữ `/overview` chạy mọi lúc: nó nuôi các con số trên thanh điều
     hướng, và người trực cần thấy "Ca trực" nhảy số kể cả khi đang đứng ở
     màn khác — đó chính là cách họ biết có việc mới. */
  if (!dangMo("cv-ca-truc")) return;   // tab Tổng quan ca trực của màn Công việc

  const waiting = await api("/conversations?status=can_nguoi&limit=200");
  $("#queue").innerHTML = waiting.length
    ? waiting.map((c) => convRow(c, true)).join("")
    : '<p class="empty">Không có hội thoại nào đang chờ. Ca trực êm.</p>';
  wireConvRows("#queue");
}

/* ---------------- hội thoại ---------------- */

/* Nút "Duyệt và gửi" chỉ hiện cho người có `ai.duyet` (tách khỏi
   `hoi_thoai.tra_loi` từ 0058). Máy chủ vẫn chặn — đây là để màn hình không
   mời một 403 mỗi lần bấm. */
function nutDuyetDuoc() {
  return !!(state.toiQuyen && state.toiQuyen.has("ai.duyet"));
}

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
  facebookpage: "Facebook", facebook: "Facebook", facebook_comment: "Bình luận FB",
  instagram: "Instagram", whatsapp: "WhatsApp",
  webwidget: "Web chat", email: "Email", telegram: "Telegram",
  twiliosms: "SMS", line: "LINE", api: "API",
};

/* Nền tảng nào chưa có màu riêng thì dùng màu connector tương thích. */
const NEN_TANG_MAU = {
  facebook: "facebook", "bình luận fb": "facebook", instagram: "instagram", whatsapp: "whatsapp",
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

function slaBadge(c) {
  if (c.sla_breached) {
    return `<span class="tag tag--halt" title="Đã quá hạn SLA phản hồi đầu tiên">Quá hạn SLA</span>`;
  }
  if (c.sla_warning) {
    const luc = c.first_response_warning_at ? ` (${clock(c.first_response_warning_at)})` : "";
    return `<span class="tag tag--assist" title="Đã tiêu thụ 50% thời hạn SLA phản hồi đầu tiên${esc(luc)}">Sắp hết SLA</span>`;
  }
  return "";
}

/* Hội thoại NHÓM Zalo (thread_type 1). Người trực phải thấy ngay từ danh
 * sách: gõ vào đây là gửi cho CẢ NHÓM, và AI không bao giờ trả lời ở đây —
 * hội thoại nằm trong hàng chờ người là vì vậy, không phải vì AI hỏng. */
function laNhom(c) {
  return Number(c && c.thread_type) === 1;
}

function nhomBadge(c) {
  return laNhom(c)
    ? `<span class="tag tag--plain" title="Nhóm Zalo — chỉ nhân viên trả lời, AI không nói trong nhóm">Nhóm</span>`
    : "";
}

/* Ai nói câu cuối trong NHÓM (mục 9.5). "còn size M không" mà không kèm
 * tên thì người trực không biết thành viên nào đang chờ — trong khi tên
 * nhóm ở dòng trên là tên CẢ NHÓM. Tin riêng thì không cần: chỉ có khách. */
function nguoiTinCuoi(c) {
  if (!laNhom(c) || !c.last_role) return "";
  if (c.last_role === "customer") return c.last_sender_name || "Thành viên nhóm";
  return { staff: "Nhân viên", agent: "AI", system: "Hệ thống" }[c.last_role] || "";
}

function convRow(c, hangDoi) {
  const sig = SIGNAL[c.status] || "plain";
  const ai = nguoiTinCuoi(c);
  const sub = c.typing
    ? `<span class="row__typing"><i></i><i></i><i></i> đang soạn tin…</span>`
    : `<span class="row__sub">${ai ? `<b class="row__ai">${esc(ai)}:</b> ` : ""}${esc(c.last_message || "—")}</span>`;
  const customer = c.customer_name || c.customer || "Khách";
  const unread = Number(c.unread_count || 0);
  /* Hạn SLA KHÔNG hiện thường trực trên dòng (mục 15.7): giờ hạn trên mọi
   * dòng là con số người ta thôi nhìn sau ngày đầu. Chỉ còn huy hiệu khi
   * SẮP hoặc ĐÃ quá hạn (`slaBadge`), và chuông báo người trực. */
  return `<button type="button" class="row ${state.openConv === c.id ? "is-on" : ""}" data-conv="${c.id}">
    <span class="row__flag row__flag--${sig}"></span>
    <span class="row__body">
      <span class="row__title">${esc(customer)} ${nhomBadge(c)}${srcBadge(c.channel || c.account_channel, c.nen_tang)}</span>
      <span class="row__sub">${esc(c.account_name || "")}</span>
      ${sub}
      ${chipNhanDong(c)}
    </span>
    <span class="row__side">
      ${slaBadge(c)}
      ${hangDoi ? choBadge(c.cho_bao_lau_phut) : unread ? `<span class="unread">${unread}</span>` : ""}
      <span class="row__time">${clock(c.updated_at)}</span>
    </span>
  </button>`;
}

function wireConvRows(scope) {
  $$(`${scope} [data-conv]`).forEach((el) =>
    el.addEventListener("click", () => {
      state.openConv = el.dataset.conv;
      // Đánh dấu do NGƯỜI bấm, không phải do vòng làm mới vẽ lại: chỉ cú
      // bấm mới được kéo màn hình xuống khung chi tiết (xem loadThread).
      state.cuonToiChiTiet = true;
      doiMan("hoithoai");
    })
  );
}

/* Khổ ≤1180px (`app.css`: `.split, .convo` thành MỘT cột) khung chi tiết
 * nằm DƯỚI cả danh sách hội thoại. Bấm một dòng thì nội dung thay đổi ở
 * tận cuối trang, ngoài tầm nhìn — người trực thấy "bấm mà không có gì" và
 * tưởng nút hỏng. Chỉ cuộn khi bố cục đúng là một cột: ở khổ rộng hai khung
 * nằm cạnh nhau, cuộn là giật màn hình vô cớ. */
const KHO_HEP_HOI_THOAI = "(max-width: 1180px)";

function cuonToiChiTietNeuHep() {
  if (!state.cuonToiChiTiet) return;
  state.cuonToiChiTiet = false;
  if (!window.matchMedia || !window.matchMedia(KHO_HEP_HOI_THOAI).matches) return;
  $("#convdetail")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* Báo máy chủ "người này đã đọc tới đây".
 *
 * Số "chưa đọc" trên mỗi dòng tính từ `conversation_reads`, và bảng ấy chỉ
 * được ghi qua `POST /inbox/conversations/{id}/read`. Trước đây dashboard
 * KHÔNG gọi route này ở đâu cả: con số chỉ tăng, không bao giờ giảm, và một
 * huy hiệu luôn đỏ là huy hiệu người ta thôi nhìn — đúng lúc nó có ý nghĩa.
 *
 * Gọi lại khi tin KHÁCH mới nhất đổi (khách nhắn thêm trong hội thoại đang
 * mở), không gọi mỗi 6 giây. Chỉ gọi khi tab đang hiện: tab nằm nền thì
 * người trực chưa đọc gì cả, đánh dấu "đã đọc" lúc ấy là nói dối. Hỏng thì
 * KHÔNG toast (vòng 6 giây sẽ bắn toast mãi) nhưng ghi console và không nhớ
 * mốc, để lần vẽ sau thử lại. */
function danhDauDaDoc(id, messages) {
  const tinKhach = (messages || []).filter((m) => m.role === "customer");
  if (!tinKhach.length) return;
  const moc = String(tinKhach[tinKhach.length - 1].id);
  state.docDenTin = state.docDenTin || {};
  if (state.docDenTin[id] === moc) return;
  if (document.visibilityState && document.visibilityState !== "visible") return;
  state.docDenTin[id] = moc;
  api(`/inbox/conversations/${id}/read`, { method: "POST" })
    .then(() => $(`#convlist [data-conv="${id}"] .unread`)?.remove())
    .catch((e) => {
      delete state.docDenTin[id];
      console.warn("Không đánh dấu đã đọc được hội thoại", id, e);
    });
}

$$("#convfilter .chip").forEach((chip) =>
  chip.addEventListener("click", () => {
    state.convFilter = chip.dataset.status;
    $$("#convfilter .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
    loadConversations();
  })
);

async function loadConversations() {
  let query = state.convFilter === "all" ? "" : `&status=${encodeURIComponent(state.convFilter)}`;
  if (state.convTim) query += `&q=${encodeURIComponent(state.convTim)}`;
  if (state.convNhan) query += `&nhan_id=${encodeURIComponent(state.convNhan)}`;
  query += chuoiLocHopThu();
  napBoLocHopThu();
  const [result, nhanDs] = await Promise.all([
    api("/inbox/conversations?limit=100" + query),
    api("/inbox/nhan").catch(() => ({ nhan: [] })),
  ]);
  veLocNhan(nhanDs.nhan || []);
  const list = result.items || [];
  $("#convlist").innerHTML = list.length
    ? list.map(convRow).join("")
    : `<p class="empty">${state.convTim || state.convNhan || dangLocHopThu()
        ? "Không có hội thoại nào khớp." : "Chưa có hội thoại nào."}</p>`;
  wireConvRows("#convlist");
  if (state.openConv) await loadThread(state.openConv);
}

async function loadThread(id) {
  let c;
  let ghiChu = [];
  let deXuat = [];
  try {
    /* Thẻ đề xuất hành động của AI (mục 17) xen trong luồng như ghi chú —
     * hỏng thì luồng tin vẫn hiện, chỉ thiếu thẻ. */
    [c, ghiChu, deXuat] = await Promise.all([
      api("/inbox/conversations/" + id),
      api(`/inbox/conversations/${id}/ghi-chu`).then((r) => r.ghi_chu).catch(() => []),
      api(`/ai-de-xuat?hoi_thoai=${encodeURIComponent(id)}`).then((r) => r.de_xuat).catch(() => []),
    ]);
  }
  catch { $("#convdetail").innerHTML = '<p class="empty">Không tìm thấy hội thoại.</p>'; return; }

  const nhom = laNhom(c);
  /* Ghi chú nội bộ nằm XEN trong luồng theo thời gian — xem `xenGhiChu`. */
  const msgs = xenGhiChu(c.messages, ghiChu, deXuat).map((muc) => {
    if (muc.loai === "ghichu") return veGhiChuTrongLuong(muc.g);
    if (muc.loai === "dexuat") return veTheDeXuat(muc.d);
    const m = muc.m;
    const draft = m.role === "agent" && m.delivery_status === "draft";
    /* Trong nhóm, "Khách" không nói được ai gõ câu nào: tên trên đầu hội
     * thoại là tên NHÓM. Lấy tên người gửi của chính tin này. */
    const nguoiGui = nhom && m.role === "customer" ? (m.sender_name || "Thành viên nhóm") : "";
    const who = tenTacGia(m, nguoiGui, c.customer_name)
      || { customer: "Khách hàng", agent: "AI Agent", staff: "Nhân viên", system: "Hệ thống" }[m.role] || m.role;
    /* MỘT dòng chuẩn dưới mỗi tin: Thời gian · Người gửi · Trạng thái.
     * Thông tin kỹ thuật (độ tin cậy, nguồn, thời gian xử lý, model, chi phí)
     * KHÔNG hiện mặc định — người trực đọc hội thoại, không đọc nhật ký máy;
     * chúng nằm trong "Chi tiết" / "Xem căn cứ" của từng tin. */
    const meta = [gioTin(m.created_at), who, trangThaiTin(m)].filter(Boolean).join(" · ");

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
               ${nutDuyetDuoc() ? `<button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>` : ""}
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
      ${nguoiGui ? `<div class="msg__nguoi">${esc(nguoiGui)}</div>` : ""}
      ${anh}
      ${than}
      ${m.noi_dung_goc && state.xemGoc === m.id
        ? `<div class="msg__goc"><span class="msg__goc-nhan">Bản AI đã viết</span>${esc(m.noi_dung_goc)}</div>`
        : ""}
      <div class="msg__meta">
        <span>${esc(meta)}</span>
        ${ghiChuNguoiXuLy(m)}
        ${banGoc}
        ${nutChiTietTin(m, draft)}
        ${draft && !dangSua && nutDuyetDuoc() ? `<button type="button" class="btn btn--sm" data-edit="${m.id}">Sửa</button>
          <button type="button" class="btn btn--sm btn--go" data-approve="${m.id}">Duyệt và gửi</button>
          <button type="button" class="btn btn--sm btn--ghost" data-tu-choi-nhap="${m.id}">Từ chối</button>` : ""}
      </div>
      ${veChiTietTin(m, draft)}
    </div>`;
  }).join("");

  /* AI giữ hay NGƯỜI giữ — và người nào. Luật nút (trạng thái × quyền) nằm
   * ở `hanhDongXuLy` (03b-thanh-hoi-thoai.js), một hàm thuần test chạy thật.
   * `assigned_to` so với `state.toiId` (nạp từ /toi lúc kiểm phiên). */
  const nguoiGiu = c.mode === "human" ? (c.assigned_to ? String(c.assigned_to) : "") : "";
  const laCuaToi = !!nguoiGiu && nguoiGiu === String(state.toiId || "");
  /* "Chuyển nhân viên…" chỉ hiện khi máy chủ nói người này giao được cho người khác
   * (quản trị, hoặc quản lý của KÊNH này). Hỏi MỘT lần mỗi kênh rồi nhớ —
   * không hỏi mỗi 6 giây. */
  state.convDangMo = c;
  state.giaoDuoc = state.giaoDuoc || {};
  const giaoDuoc = state.giaoDuoc[c.account_id];
  if (giaoDuoc === undefined && state.toiQuyen && state.toiQuyen.has("hoi_thoai.nhan")) {
    state.giaoDuoc[c.account_id] = null;
    api(`/inbox/conversations/${id}/nguoi-nhan-duoc`)
      .then((r) => { state.giaoDuoc[c.account_id] = !!r.co_the_giao_khac;
        if (r.co_the_giao_khac && state.openConv === id) loadThread(id); })
      .catch(() => { state.giaoDuoc[c.account_id] = false; });
  }
  /* Nhãn và ghi chú nội bộ có quyền riêng từ 0058 (`hoi_thoai.ghi_chu`).
   * Vẽ nút cho người không có quyền là mời một 403 mỗi lần bấm. */
  const ghiChuDuoc = !!(state.toiQuyen && state.toiQuyen.has("hoi_thoai.ghi_chu"));
  const ghi = ghiChuDuoc && dangGhiChu(id);
  const hd = hanhDongXuLy(c, { toiId: state.toiId, quyen: state.toiQuyen, giaoDuoc: !!giaoDuoc });

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

  /* Thanh thông tin: Tên | Nhãn | Customer 360 | Hành động | Chi tiết
   * (03b). Trạng thái, kênh, Mode, ưu tiên, Version, SLA KHÔNG ở đây —
   * ưu tiên/Version/chế độ AI vào panel "Chi tiết" khi người trực mở. */
  $("#convdetail").innerHTML = `
    ${veThanhThongTin(c, hd)}
    ${veChiTietHoiThoai(c, laCuaToi)}
    <div class="thread" id="thread">${msgs || '<p class="empty">Chưa có tin nhắn.</p>'}
      ${c.typing ? '<div class="msg msg--agent"><div class="typing"><i></i><i></i><i></i></div></div>' : ""}
    </div>
    <form class="convo__bar${ghi ? " convo__bar--ghichu" : ""}" id="replyform">
      ${veCheDoSoan(id, ghiChuDuoc)}
      <div class="convo__soan">
        <textarea name="text" required aria-label="${ghi ? "Ghi chú nội bộ" : "Trả lời khách"}"
          placeholder="${ghi ? "Ghi chú nội bộ — chỉ nhân viên thấy, KHÔNG gửi cho khách…" : "Nhắn trực tiếp cho khách…"}"></textarea>
        ${ghi ? "" : `<span class="convo__dinhkem">
          <button type="button" class="btn btn--sm" data-dinhkem title="Gửi ảnh hoặc tài liệu">📎</button>
          <input type="file" id="tep-dinhkem" accept="image/jpeg,image/png,image/webp,image/gif,application/pdf" hidden>
        </span>`}
        <button type="submit" class="btn ${ghi ? "btn--ghichu" : "btn--primary"}">${ghi ? "Lưu ghi chú" : "Gửi"}</button>
      </div>
    </form>`;

  const thread = $("#thread");
  if (thread) thread.scrollTop = dang_o_day ? thread.scrollHeight : cuon_cu;
  danhDauDaDoc(id, c.messages);
  cuonToiChiTietNeuHep();

  /* Trả lại bản nháp.
   *
   * Gắn theo TỪNG hội thoại: giữ chung một biến là dán chữ soạn cho khách A
   * sang khung của khách B — tệ hơn mất chữ nhiều, vì nó gửi nhầm nội dung
   * cho nhầm người. Và theo từng KIỂU SOẠN (`khoaNhap`): ghi chú nội bộ
   * không bao giờ được nằm sẵn trong khung trả lời khách.
   */
  const o_moi = $('#replyform [name="text"]');
  const nhap = state.nhapTheoHoiThoai && state.nhapTheoHoiThoai[khoaNhap(id)];
  if (o_moi && nhap) {
    o_moi.value = nhap;
    if (dang_focus) {
      o_moi.focus();
      const vt = con_tro == null ? nhap.length : Math.min(con_tro, nhap.length);
      o_moi.setSelectionRange(vt, vt);
    }
  }
  if (o_moi && state.soanVuaDoi) {
    // Vừa đổi kiểu soạn: đưa con trỏ về ô, người bấm thẻ là để gõ ngay.
    state.soanVuaDoi = false;
    o_moi.focus();
  }
  if (o_moi) {
    // Gắn TRƯỚC phím Enter-gửi bên dưới: khi khung mẫu đang mở, Enter là
    // "chọn mẫu", và trình nghe này chặn không cho nó tới trình gửi tin.
    ganMauNhanh(o_moi);
    o_moi.addEventListener("input", () => {
      state.nhapTheoHoiThoai = state.nhapTheoHoiThoai || {};
      state.nhapTheoHoiThoai[khoaNhap(id)] = o_moi.value;
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

  // Tiếp quản / Kết thúc / Đổi chế độ / Mở lại: trình nghe ủy quyền ở
  // 03b-thanh-hoi-thoai.js — nút nằm trong menu "⋯" dựng lại liên tục.

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
      // Kiểu ghi chú không vẽ nút đính kèm; chặn thêm ở đây vì tệp đi thẳng
      // tới KHÁCH — ghi chú nội bộ không bao giờ được đi đường này.
      if (!f || dangGhiChu(id)) return;
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
          if (state.nhapTheoHoiThoai) delete state.nhapTheoHoiThoai[khoaNhap(id)];
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
    // Đọc kiểu soạn MỘT lần, trước mọi await: người bấm đổi thẻ trong lúc
    // chờ mạng không được làm ghi chú đổi đường thành tin gửi khách.
    const laGhiChu = dangGhiChu(id);
    try {
      const r = await guiTuKhungSoan(id, text, laGhiChu);
      if (laGhiChu) toast("Đã lưu ghi chú nội bộ — khách không thấy.");
      else toast(r.ok ? "Đã gửi." : "Không gửi được: " + r.detail, !r.ok);
      ev.target.reset();
      // Xoá bản nháp đã lưu, nếu không lần dựng lại kế tiếp sẽ chép nó
      // trở vào khung và người trực tưởng tin chưa gửi đi.
      if (state.nhapTheoHoiThoai) {
        delete state.nhapTheoHoiThoai[laGhiChu ? `${id}:ghichu` : String(id)];
      }
      refresh();
    } catch (e) { toast(e.message, true); }
  });
}

/* ---------------- Thanh thông tin hội thoại (mục 6 của bảng việc) ----------------
 *
 * Cấu trúc chủ dự án chốt (22.11.2026):
 *
 *   Tên khách hàng | Nhãn hội thoại | Customer 360 | Hành động xử lý | Chi tiết
 *
 * Trước bản này thanh ấy chở MƯỜI thứ một lúc: trạng thái, SLA, kênh, chế
 * độ, ưu tiên, version, ba bốn nút xử lý, nút ghi chú. Người trực mở hội
 * thoại để đọc khách nói gì — mười thứ thường trực là mười thứ mắt phải
 * nhảy qua trước khi tới câu đầu tiên. Nên:
 *
 *   · trạng thái, kênh, chế độ AI/Mode    -> bỏ (danh sách bên trái đã có),
 *                                           hoặc vào "Chi tiết" khi cần;
 *   · ưu tiên, Version, SLA               -> "Chi tiết" (SLA không hiện
 *                                           thường trực — cảnh báo SLA tới
 *                                           người trực qua chuông);
 *   · ghi chú nội bộ                      -> một kiểu soạn trong ô soạn tin;
 *   · nút xử lý                           -> MỘT nút chính + menu "⋯".
 *
 * Tệp riêng vì `03-hoi-thoai.js` đã gần trần 1000 dòng. Đặt tên `03b` để
 * đóng gói nằm ngay sau 03, trước Customer 360 (04).
 */

/* Các hành động xử lý. `id` giữ đúng id nút cũ: trình nghe ở dưới và các
 * test nút chết tìm theo id viết đủ. */
const HANH_DONG_HT = {
  tiepQuan: { id: "btn-take", nhan: "Tiếp quản", lop: "btn--halt",
              goi_y: "Nhận hội thoại về mình; AI dừng gửi" },
  giao: { id: "btn-giao", nhan: "Chuyển nhân viên…", lop: "",
          goi_y: "Giao hội thoại cho một nhân viên khác của kênh" },
  ketThuc: { id: "btn-release", nhan: "Kết thúc tiếp quản", lop: "",
             goi_y: "Trả hội thoại về chế độ AI gợi ý" },
  tuTraLoi: { id: "btn-chedo", nhan: "Để agent tự trả lời", lop: "", che_do: "auto",
              goi_y: "AI tự gửi câu trả lời, không chờ duyệt" },
  duyetTruoc: { id: "btn-chedo", nhan: "Duyệt trước khi gửi", lop: "", che_do: "assist",
                goi_y: "AI soạn xong chờ người duyệt rồi mới gửi" },
  giaiQuyet: { id: "btn-giai-quyet", nhan: "Đã giải quyết", lop: "btn--go",
               goi_y: "Đóng vụ việc; khách nhắn tiếp thì tự mở lại" },
  moLai: { id: "btn-mo-lai", nhan: "Mở lại", lop: "",
           goi_y: "Mở lại hội thoại đã giải quyết để xử lý tiếp" },
};

/* Hội thoại này, với người này, được làm gì — và việc nào là việc CHÍNH.
 *
 * Hàm THUẦN (không đọc `state`, không đụng DOM) để test chạy thật được bằng
 * node trên từng ô của bảng trạng thái × quyền. Luật nút trước đây nằm rải
 * trong một chuỗi template, mỗi nút một điều kiện riêng, và chỉ test được
 * bằng regex — đúng kiểu xanh giả với mã đã bị tắt.
 *
 * `ng` = { toiId, quyen: Set, giaoDuoc: bool (máy chủ nói giao người khác
 * được) }. Trả { chinh, them: [...], giu } — `giu` là dòng chữ "X đang giữ"
 * khi không có nút nào để bấm, để người xem biết VÌ SAO không có nút.
 *
 * Máy chủ vẫn chặn từng việc (`hoi_thoai.nhan`, luật can_assign/can_release).
 * Ẩn nút ở đây là để màn hình không mời một 403 — không phải lớp chặn. */
function hanhDongXuLy(c, ng) {
  const co = (q) => !!(ng && ng.quyen && ng.quyen.has(q));
  const kq = { chinh: null, them: [], giu: "" };
  const nguoiGiu = c.mode === "human" && c.assigned_to ? String(c.assigned_to) : "";
  const laCuaToi = !!nguoiGiu && nguoiGiu === String((ng && ng.toiId) || "");
  const nguoiKhacGiu = !!nguoiGiu && !laCuaToi;
  if (nguoiKhacGiu) kq.giu = `${c.assigned_to_ten || "Đồng nghiệp"} đang giữ`;
  // Mọi hành động xử lý đều đòi `hoi_thoai.nhan` ở máy chủ.
  if (!co("hoi_thoai.nhan")) return kq;
  const quanLy = co("hoi_thoai.xem_tat_ca");
  const ds = [];
  if (c.state === "resolved") {
    ds.push(HANH_DONG_HT.moLai);
  } else if (laCuaToi) {
    ds.push(HANH_DONG_HT.giaiQuyet);
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    ds.push(HANH_DONG_HT.ketThuc);
  } else if (nguoiKhacGiu) {
    // Hội thoại đồng nghiệp đang nói dở: chỉ người quản lý được can thiệp.
    // "Tiếp quản" KHÔNG hiện — giành việc là dùng "Chuyển nhân viên…".
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    if (quanLy) ds.push(HANH_DONG_HT.ketThuc, HANH_DONG_HT.giaiQuyet);
  } else {
    // AI đang xử lý, hoặc đã chuyển người mà chưa ai nhận.
    ds.push(HANH_DONG_HT.tiepQuan);
    const taken = c.mode === "human" || c.status === "escalated";
    // Không mời "Để agent tự trả lời" khi đang chờ người (phải tiếp quản
    // rồi kết thúc trước), và không bao giờ trong NHÓM — AI không nói ở đó.
    if (!taken && !laNhom(c)) {
      ds.push(c.mode === "auto" ? HANH_DONG_HT.duyetTruoc : HANH_DONG_HT.tuTraLoi);
    }
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    // Trả hội thoại agent đã chuyển người về cho AI là quyết định của quản
    // lý — nhân viên thường bấm thì máy chủ trả 403 (xem can_release).
    if (c.mode === "human" && quanLy) ds.push(HANH_DONG_HT.ketThuc);
    ds.push(HANH_DONG_HT.giaiQuyet);
  }
  kq.chinh = ds[0] || null;
  kq.them = ds.slice(1);
  return kq;
}

function _nutHanhDong(a, trongMenu) {
  const lop = trongMenu ? "hd-them__muc" : `btn btn--sm ${a.lop}`;
  return `<button type="button" class="${lop}" id="${a.id}" title="${esc(a.goi_y)}"
    ${a.che_do ? `data-chedo="${a.che_do}"` : ""} ${trongMenu ? 'role="menuitem"' : ""}>${esc(a.nhan)}</button>`;
}

/* Một nút chính + menu "⋯". Menu là <details>: mở/đóng không cần JS, và
 * trạng thái mở nhớ trong `state.moHanhDong` vì panel dựng lại mỗi 6 giây —
 * không nhớ là menu tự sập ngay dưới ngón tay người đang chọn. */
function veHanhDongXuLy(c, hd) {
  const mo = state.moHanhDong === String(c.id);
  return `<span class="hd" aria-label="Hành động xử lý">
    ${hd.giu ? `<span class="tag tag--assist">${esc(hd.giu)}</span>` : ""}
    ${hd.chinh ? _nutHanhDong(hd.chinh, false) : ""}
    ${hd.them.length ? `<details class="hd-them" data-hd-them="${esc(c.id)}" ${mo ? "open" : ""}>
      <summary class="btn btn--sm btn--ghost" aria-label="Hành động khác" title="Hành động khác">⋯</summary>
      <div class="hd-them__menu" role="menu">${hd.them.map((a) => _nutHanhDong(a, true)).join("")}</div>
    </details>` : ""}
  </span>`;
}

const ICON_C360 = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>`;

/* Đầu khung chi tiết. Nhãn hội thoại nằm NGAY DƯỚI tên (mục 6.3) — cùng
 * một khối với tên, không phải một hàng riêng kéo dài cả khung.
 *
 * Customer 360 không hiện cho NHÓM (mục 9.7): nhóm không phải một khách
 * hàng, và máy chủ trả 404 cho hồ sơ của nhóm. */
function veThanhThongTin(c, hd) {
  return `<div class="convo__title">
      <div class="convo__danh">
        <div class="convo__ten">
          <span class="convo__name">${esc(c.customer_name || "Khách")}</span>
          ${nhomBadge(c)}
        </div>
        <div class="nhanbar">${nhanHoiThoaiHtml(c)}
          ${state.toiQuyen && state.toiQuyen.has("cong_viec.sua")
            ? `<button type="button" class="btn btn--sm btn--ghost" id="btn-tao-viec-ht"
                title="Tạo công việc gắn với hội thoại và khách này">+ Việc</button>` : ""}</div>
      </div>
      <span class="convo__spacer"></span>
      ${c.contact_id && !laNhom(c) ? `<button type="button" class="btn btn--sm btn--icon" id="open-contact"
        data-contact="${c.contact_id}" title="Customer 360" aria-label="Mở Customer 360">${ICON_C360}</button>` : ""}
      ${veHanhDongXuLy(c, hd)}
      <button type="button" class="btn btn--sm btn--ghost" id="btn-chitiet-ht"
        aria-expanded="${state.moChiTietHT === String(c.id) ? "true" : "false"}">Chi tiết</button>
    </div>`;
}

document.addEventListener("toggle", (ev) => {
  const d = ev.target;
  if (!(d.dataset && d.dataset.hdThem)) return;
  if (d.open) state.moHanhDong = d.dataset.hdThem;
  else if (state.moHanhDong === d.dataset.hdThem) state.moHanhDong = null;
}, true);

/* <details> không tự đóng khi bấm ra ngoài hay chọn một mục — như mọi menu
 * khác thì phải đóng, không thì menu treo đè lên luồng tin. */
document.addEventListener("click", (ev) => {
  $$(".hd-them[open]").forEach((d) => {
    if (!d.contains(ev.target) || ev.target.closest(".hd-them__muc")) d.open = false;
  });
});

/* ---------------- Trình nghe hành động xử lý ----------------
 * Ủy quyền ở document: panel dựng lại mỗi lần làm mới, gắn vào từng nút là
 * gắn lại mãi. `state.convDangMo` là hội thoại đang vẽ (03-hoi-thoai.js). */
async function _goiHanhDong(duong, than, xong) {
  const c = state.convDangMo;
  if (!c) return;
  state.moHanhDong = null;
  try {
    const r = await api(`/inbox/conversations/${c.id}/${duong}`, {
      method: "POST",
      body: than ? JSON.stringify({ expected_version: c.version || 1, ...than }) : undefined,
    });
    xong(r);
    refresh();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", (ev) => {
  if (ev.target.closest("#btn-take")) {
    _goiHanhDong("takeover", { reason: "Nhân viên nhận xử lý" },
      () => toast("Bạn đang giữ hội thoại này. AI đã dừng gửi."));
  } else if (ev.target.closest("#btn-release")) {
    _goiHanhDong("release", { reason: "Nhân viên kết thúc tiếp quản" }, (r) => {
      /* `ghi_chu` = đã bật agent trong CSDL nhưng CHƯA giành lại quyền từ
       * Meta (Messenger) — agent bật mà câm. Phải hiện thành lỗi, không
       * được nuốt sau một toast xanh. */
      if (r && r.ghi_chu) toast(r.ghi_chu, true);
      else toast("Đã chuyển về chế độ gợi ý.");
    });
  } else if (ev.target.closest("#btn-chedo")) {
    /* Trả hội thoại VỀ cho agent, hoặc bắt duyệt trước khi gửi. Không có
     * nút này thì hội thoại rơi xuống "Chờ duyệt" là kẹt ở đó vĩnh viễn —
     * chỉ có nút đi xuống, không có nút đi lên. */
    const sang = ev.target.closest("#btn-chedo").dataset.chedo;
    _goiHanhDong("che-do", {
      che_do: sang,
      reason: sang === "auto" ? "Người trực trả hội thoại về cho agent" : "Người trực bật duyệt trước khi gửi",
    }, () => toast(sang === "auto" ? "Agent sẽ tự trả lời hội thoại này." : "Từ giờ AI soạn xong sẽ chờ bạn duyệt."));
  } else if (ev.target.closest("#btn-mo-lai")) {
    _goiHanhDong("mo-lai", null, (r) =>
      toast(r && r.da_mo ? "Đã mở lại hội thoại." : "Hội thoại đã mở từ trước."));
  }
});

/* ---------------- Ghi chú nội bộ trong ô soạn tin (mục 6.6) ----------------
 *
 * Ô soạn có HAI kiểu: "Trả lời khách" và "Ghi chú nội bộ". Kiểu ghi chú
 * KHÔNG BAO GIỜ đi qua đường gửi tin (`/send`, `/send-file`): chỉ gọi
 * `/inbox/conversations/{id}/ghi-chu`, và route ấy không đụng outbox.
 *
 * Kiểu soạn và BẢN NHÁP nhớ theo từng hội thoại, và bản nháp tách riêng
 * cho từng kiểu. Chung một bản nháp là lỗi nguy hiểm nhất ở đây: gõ ghi chú
 * "khách này hay bom hàng", lỡ bấm sang "Trả lời khách", Enter — câu ấy đi
 * thẳng tới khách. */
function dangGhiChu(id) {
  return !!(state.soanGhiChu && state.soanGhiChu[id]);
}

function khoaNhap(id) {
  return dangGhiChu(id) ? `${id}:ghichu` : String(id);
}

async function guiTuKhungSoan(id, text, laGhiChu) {
  if (laGhiChu) {
    await api(`/inbox/conversations/${id}/ghi-chu`, {
      method: "POST", body: JSON.stringify({ noi_dung: text }),
    });
    return { ok: true, ghi_chu: true };
  }
  return api(`/conversations/${id}/send`, {
    method: "POST", body: JSON.stringify({ text }),
  });
}

document.addEventListener("click", (ev) => {
  const nut = ev.target.closest("[data-soan]");
  if (!nut || !state.openConv) return;
  const id = state.openConv;
  state.soanGhiChu = state.soanGhiChu || {};
  state.soanGhiChu[id] = nut.dataset.soan === "ghichu";
  state.soanVuaDoi = true;
  loadThread(id);
});

/* Trộn ghi chú vào luồng tin theo THỜI GIAN. Ghi chú để riêng một hộp gấp
 * ở đầu hội thoại thì người đọc phải tự ghép "ghi chú này viết lúc khách
 * đang nói gì" — mà đó chính là ngữ cảnh làm ghi chú có nghĩa. */
function xenGhiChu(tin, ghiChu, deXuat) {
  const ds = (tin || []).map((m, i) => ({ loai: "tin", luc: m.created_at, thu_tu: i, m }));
  (ghiChu || []).forEach((g, i) => ds.push({ loai: "ghichu", luc: g.tao_luc, thu_tu: 1e6 + i, g }));
  (deXuat || []).forEach((d, i) => ds.push({ loai: "dexuat", luc: d.tao_luc, thu_tu: 2e6 + i, d }));
  const ms = (x) => { const t = Date.parse(x.luc || ""); return Number.isNaN(t) ? 0 : t; };
  return ds.sort((a, b) => ms(a) - ms(b) || a.thu_tu - b.thu_tu);
}

function veGhiChuTrongLuong(g) {
  return `<div class="msg msg--ghichu" role="note" aria-label="Ghi chú nội bộ">
    <div class="msg__bubble"><span class="msg__ghichu-nhan">Ghi chú nội bộ · khách không thấy</span>${esc(g.noi_dung)}</div>
    <div class="msg__meta"><span>${esc([gioTin(g.tao_luc), g.nguoi || "Nhân viên"].filter(Boolean).join(" · "))}</span></div>
  </div>`;
}

/* Hai thẻ chọn kiểu soạn. Người không có `hoi_thoai.ghi_chu` chỉ có một
 * kiểu — không vẽ thẻ nào, để khỏi mời một 403. */
function veCheDoSoan(id, ghiChuDuoc) {
  if (!ghiChuDuoc) return "";
  const ghi = dangGhiChu(id);
  const the = (ma, nhan, bat) => `<button type="button" role="tab" class="soan__tab${bat ? " is-on" : ""}"
    aria-selected="${bat ? "true" : "false"}" data-soan="${ma}">${nhan}</button>`;
  return `<div class="soan__che-do" role="tablist" aria-label="Kiểu soạn">
    ${the("tra_loi", "Trả lời khách", !ghi)}${the("ghichu", "Ghi chú nội bộ", ghi)}
  </div>`;
}
/* ---------------- Customer 360 ---------------- */

function openCustomer(id) {
  state.openContact = id;
  /* Đi qua `doiMan` chứ KHÔNG gọi thẳng `loadContacts()`.
   *
   * Bản cũ gọi thẳng, nên thiếu `loadTruongKhach()` mà `refresh()` vẫn gọi
   * cho màn này. Hệ quả: `oTruongKhach()` thấy `truongKhach.ds` rỗng và
   * `return ""` — toàn bộ trường tuỳ biến BIẾN MẤT, không báo gì, cho tới
   * khi vòng 6 giây tình cờ vá lại. Mở hồ sơ khách từ hội thoại là đúng
   * đường đi vào lỗi ấy. */
  doiMan("khachhang");
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
   * trực không biết mình có được vào hay không.
   *
   * KHÁCH CỦA CHÍNH MÌNH PHẢI KHÁC MÀU, KHÔNG CHỈ KHÁC TÊN.
   * Hiện đúng tên người là chưa đủ: nhân viên phải đọc từng dòng rồi tự đối
   * chiếu với tên mình — ở danh sách 100 khách thì không ai làm. Ba trạng
   * thái, ba màu, đọc được bằng cách liếc:
   *     của mình      → xanh, chữ "Bạn phụ trách"
   *     của người khác → xám, tên người ấy
   *     chưa giao      → vàng, "chưa có chủ" (của chung, ai cũng trả lời được)
   */
  if (contact.owner_user_id && contact.owner_user_id === state.toiId) {
    return '<span class="pill pill--toi">Bạn phụ trách</span>';
  }
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
  // loadContacts() gọi hàm này mỗi 6 giây: gán trần là hai ô nhảy về khách
  // đầu danh sách giữa lúc người ta đang chọn — rồi gộp nhầm người.
  ganLuaChon(o, html);
  ganLuaChon($("#gopDich"), html);
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
      const hoi = await hoiHop({
        tieu_de: "Gộp hai khách làm một",
        phu: "Hội thoại và danh tính dồn về bên giữ lại. Lý do ghi vào lịch sử, để hoàn tác còn hiểu được.",
        truong: [{ name: "ly_do", label: "Vì sao gộp", value: "Cùng một người, hai kênh",
                   required: true, maxlength: 500 }],
        nut: "Gộp", nguy_hiem: true,
      });
      if (!hoi || !hoi.ly_do) return;
      const ly_do = hoi.ly_do;
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
        /* Nút hoàn tác nằm NGAY trong kết quả, giữ đủ merge_id.
         *
         * Trước đây chỉ có toast "Hoàn tác được bằng mã 1a2b3c4d…": tám ký
         * tự đầu không gọi được route nào, toast biến mất sau vài giây, và
         * dashboard không có chỗ nào để dán mã. Lời hứa "hoàn tác được" là
         * lời hứa không ai thực hiện nổi — đúng lúc vừa gộp nhầm hai khách. */
        toast("Đã gộp hai khách.");
        $("#gopKetQua").innerHTML = `<p class="panel__note">Đã gộp. Gộp nhầm thì
             hoàn tác ngay ở đây — hội thoại và danh tính trả về khách cũ.</p>
           <div class="row__nut">
             <button type="button" class="btn btn--sm" data-merge-undo="${esc(r.merge_id)}">Hoàn tác</button>
           </div>`;
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

/* Hoàn tác một lần gộp. Hỏi lý do = bước xác nhận: route bắt buộc `reason`
 * (ghi vào lịch sử), và một hộp phải điền thì không ai bấm nhầm. */
$("#gopKetQua")?.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-merge-undo]");
  if (!nut) return;
  const hoi = await hoiHop({
    tieu_de: "Hoàn tác lần gộp này?",
    phu: "Hai khách tách lại như trước khi gộp. Lý do ghi vào lịch sử.",
    truong: [{ name: "ly_do", label: "Vì sao hoàn tác", value: "Gộp nhầm",
               required: true, maxlength: 500 }],
    nut: "Hoàn tác", nguy_hiem: true,
  });
  if (!hoi || !hoi.ly_do) return;
  nut.disabled = true;
  try {
    await api(`/contacts/merges/${encodeURIComponent(nut.dataset.mergeUndo)}/undo`, {
      method: "POST", body: JSON.stringify({ reason: hoi.ly_do }),
    });
    toast("Đã hoàn tác — hai khách đã tách lại.");
    $("#gopKetQua").innerHTML = "";
    $("#pnGop").classList.add("is-hidden");
    await loadContacts();
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
  }
});

async function loadContacts() {
  napLocNhanKhach();          // không chờ: ô lọc nhãn không được chặn danh sách
  const locNhan = state.khachNhan ? `&nhan_id=${encodeURIComponent(state.khachNhan)}` : "";
  const contacts = await api(`/contacts?limit=100&q=${encodeURIComponent(state.contactQuery)}${locNhan}`);
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
  /* Số ngay trên chip lọc. Không có nó thì phải bấm từng chip mới biết mình
     có bao nhiêu khách — và "Khách của tôi" rỗng trông hệt như bộ lọc hỏng. */
  const demToi = contacts.filter((c) => c.owner_user_id && c.owner_user_id === state.toiId).length;
  const demVoChu = contacts.filter((c) => !c.owner_user_id).length;
  const datDem = (sel, n) => {
    const chip = $(sel);
    if (chip) chip.querySelector(".chip__dem").textContent = n ? ` ${n}` : "";
  };
  datDem('[data-chuloc="tat_ca"]', contacts.length);
  datDem('[data-chuloc="cua_toi"]', demToi);
  datDem('[data-chuloc="vo_chu"]', demVoChu);
  gopDoO(contacts);
  /* Ô tick nằm NGOÀI nút hàng (nút không được chứa điều khiển khác), và
     trạng thái tick sống trong state.khachDaChon để qua vòng làm mới 6 giây
     không mất — tick mười khách rồi thấy mất sạch là thứ người ta bỏ luôn. */
  const giaoDuoc = state.toiQuyen.has("khach.giao");
  state.khachDaChon = state.khachDaChon || new Set();
  for (const id of [...state.khachDaChon]) {
    if (!contacts.some((c) => c.id === id)) state.khachDaChon.delete(id);
  }
  $("#contactlist").innerHTML = hien.length ? hien.map((contact) => `
    <div class="row-wrap">${giaoDuoc ? `<label class="chonkhach" title="Chọn để giao hàng loạt">
      <input type="checkbox" data-chon="${contact.id}"${state.khachDaChon.has(contact.id) ? " checked" : ""}></label>` : ""}
    <button type="button" class="row row--avatar ${state.openContact === contact.id ? "is-on" : ""}" data-contact="${contact.id}">
      <span class="avatar">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <span class="row__body"><span class="row__title">${esc(contact.display_name || "Khách")}</span>
        <span class="row__sub">${esc(contact.phone || contact.email || "Chưa có SĐT/email")} · ${contact.contact_point_count || 0} danh tính</span></span>
      <span class="row__side">${chuKhach(contact)}<span class="row__time">${clock(contact.last_seen)}</span></span>
    </button></div>`).join("")
    : `<p class="empty">${loc === "cua_toi"
        ? "Chưa có khách nào được giao cho bạn."
        : loc === "vo_chu"
          ? "Mọi khách trong phạm vi của bạn đều đã có người phụ trách."
          : "Không tìm thấy khách hàng trong phạm vi tài khoản của bạn."}</p>`;
  $$("#contactlist [data-contact]").forEach((row) => row.addEventListener("click", () => {
    state.openContact = row.dataset.contact;
    loadContacts();
  }));
  $$("#contactlist [data-chon]").forEach((o) => o.addEventListener("change", () => {
    if (o.checked) state.khachDaChon.add(o.dataset.chon);
    else state.khachDaChon.delete(o.dataset.chon);
    veChonBar();
  }));
  veChonBar();
  if (state.openContact) await loadContactDetail(state.openContact);
}

function veChonBar() {
  const n = (state.khachDaChon || new Set()).size;
  $("#chonbar")?.classList.toggle("is-hidden", n === 0);
  const d = $("#chonDem");
  if (d) d.textContent = `Đã chọn ${n} khách`;
}

$("#chonHuy")?.addEventListener("click", () => {
  state.khachDaChon = new Set();
  loadContacts();
});

/*
 * Giao hàng loạt: cùng lớp phủ chọn người với giao lẻ, nhưng gọi endpoint
 * một-giao-dịch. Không lặp endpoint đơn N lần: rớt mạng giữa chừng là nửa
 * số khách có chủ, nửa không, và người bấm không biết dừng ở đâu.
 */
$("#chonGiao")?.addEventListener("click", async () => {
  const ids = [...(state.khachDaChon || [])];
  if (!ids.length) return;
  let ds;
  try { ds = (await api("/nguoi-dung")).nguoi_dung.filter((n) => !n.khoa); }
  catch (e) { toast(e.message, true); return; }

  const o = $("#giaoAi");
  o.innerHTML = '<option value="">— Thu hồi: các khách này quay về của chung —</option>'
    + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ho_ten || n.ten_dang_nhap)} (${esc(n.ten_dang_nhap)})</option>`).join("");
  $("#giaoKhachTen").textContent = `${ids.length} khách đã chọn.`;
  $("#giaoLyDo").value = "Phân công ca trực";
  $("#congGiao").classList.remove("is-off");
  o.focus();

  const form = $("#giaoform");
  const dong = () => { $("#congGiao").classList.add("is-off"); form.onsubmit = null; $("#giaoHuy").onclick = null; };
  $("#giaoHuy").onclick = (e) => { e.preventDefault(); dong(); };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const nut = form.querySelector("button[type=submit]");
    nut.disabled = true;
    try {
      const r = await api("/contacts/chu-so-huu/hang-loat", {
        method: "PUT",
        body: JSON.stringify({ contact_ids: ids, owner_user_id: o.value || null,
                               ly_do: $("#giaoLyDo").value.trim() }),
      });
      toast(r.owner_ho_ten
        ? `Đã giao ${r.so_khach} khách cho ${r.owner_ho_ten}.`
        : `Đã thu hồi ${r.so_khach} khách về của chung.`);
      dong();
      state.khachDaChon = new Set();
      await loadContacts();
      if (dangMo("cv-ca-truc")) { await loadVoChu(); await loadOverview(); }
    } catch (err) { toast(err.message, true); }
    finally { nut.disabled = false; }
  };
});

$("#contactloc")?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-chuloc]");
  if (!chip) return;
  state.chuLoc = chip.dataset.chuloc;
  $$("#contactloc .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
  loadContacts();
});

async function giaoKhach(id, chuHienTai) {
  /* CHỌN từ danh sách, không gõ tên. Bản cũ là hộp thoại của trình duyệt
     liệt kê tên đăng nhập rồi bắt gõ lại: gõ sai một chữ là "Không có nhân
     viên tên…", và không gì trên màn hình cho biết tên đúng viết thế nào.

     Trả về Promise để nơi gọi (Ca trực, Khách hàng) chờ xong rồi tải lại. */
  let ds;
  try { ds = (await api("/nguoi-dung")).nguoi_dung.filter((n) => !n.khoa); }
  catch (e) { toast(e.message, true); return; }

  const o = $("#giaoAi");
  o.innerHTML = '<option value="">— Thu hồi: khách quay về của chung —</option>'
    + ds.map((n) => `<option value="${esc(n.id)}"${
        n.ten_dang_nhap === chuHienTai ? " selected" : ""}>${
        esc(n.ho_ten || n.ten_dang_nhap)} (${esc(n.ten_dang_nhap)})</option>`).join("");
  $("#giaoKhachTen").textContent = chuHienTai
    ? `Đang do ${chuHienTai} phụ trách.` : "Khách chưa ai phụ trách.";
  $("#giaoLyDo").value = "Phân công ca trực";
  $("#congGiao").classList.remove("is-off");
  o.focus();

  return new Promise((xong) => {
    const form = $("#giaoform");
    const dong = () => { $("#congGiao").classList.add("is-off"); form.onsubmit = null; $("#giaoHuy").onclick = null; };
    $("#giaoHuy").onclick = (e) => { e.preventDefault(); dong(); xong(false); };
    form.onsubmit = async (e) => {
      e.preventDefault();
      const ai = o.value, ly_do = $("#giaoLyDo").value.trim();
      const nut = form.querySelector("button[type=submit]");
      nut.disabled = true;
      try {
        if (!ai) {
          await api(`/contacts/${id}/chu-so-huu?ly_do=${encodeURIComponent(ly_do)}`,
                    { method: "DELETE" });
          toast("Đã thu hồi. Khách quay về của chung.");
        } else {
          await api(`/contacts/${id}/chu-so-huu`, {
            method: "PUT", body: JSON.stringify({ owner_user_id: ai, ly_do }),
          });
          toast(`Đã giao cho ${o.options[o.selectedIndex].text}.`);
        }
        dong();
        if (state.view === "khachhang") await loadContacts();
        xong(true);
      } catch (err) { toast(err.message, true); }
      finally { nut.disabled = false; }
    };
  });
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

/* Khoá nhận dạng một ô nhập, BỀN qua mỗi lần dựng lại DOM.
 *
 * Không dùng tham chiếu phần tử được: sau `innerHTML` thì phần tử cũ đã
 * chết. Phải là khoá tính từ nội dung — mã trường, hoặc form + tên ô. */
function _khoaO(o) {
  if (o.dataset.tkNhieu) return `tkn:${o.dataset.tkNhieu}:${o.value}`;
  if (o.dataset.tk) return `tk:${o.dataset.tk}`;
  // Màn Cấu hình: ô không nằm trong form, không có name — thiếu hai dòng
  // này thì MỌI ô ở đó cùng khoá "khong-form:" và giá trị ô này đè sang ô kia.
  if (o.dataset.ch) return `ch:${o.dataset.ch}`;
  if (o.dataset.apiKhoa) return `api:${o.dataset.apiKhoa}`;
  const f = o.closest("form");
  if (!f && !o.name && o.id) return `id:${o.id}`;
  return `${f ? f.id : "khong-form"}:${o.name || ""}`;
}

/* Ô này người ta có TỰ SỬA không?
 *
 * Phân biệt được điều đó mới là phần khó. Giữ lại TẤT CẢ các ô thì một
 * đồng nghiệp vừa đổi trường tuỳ biến ở máy khác sẽ bị giá trị cũ trên
 * màn này đè ngược lại — chữa một lỗi im lặng bằng một lỗi im lặng tệ hơn.
 *
 * `defaultValue`/`defaultChecked` chính là giá trị vừa dựng từ dữ liệu máy
 * chủ (DOM sinh bằng innerHTML nên thuộc tính HTML là bản của máy chủ).
 * Lệch với nó nghĩa là người dùng đã gõ. */
function _oDaSua(o) {
  if (o.type === "checkbox" || o.type === "radio") return o.checked !== o.defaultChecked;
  if (o.tagName === "SELECT") {
    const mac = o.querySelector("option[selected]");
    return o.value !== (mac ? mac.value : (o.options[0] || {}).value);
  }
  return o.value !== o.defaultValue;
}

function _luuDangGo(goc) {
  const giu = { gia: new Map(), oFocus: null, dau: null, cuoi: null };
  if (!goc) return giu;
  $$("input, textarea, select", goc).forEach((o) => {
    const k = _khoaO(o);
    if (_oDaSua(o)) {
      giu.gia.set(k, o.type === "checkbox" || o.type === "radio" ? o.checked : o.value);
    }
    if (document.activeElement === o) {
      giu.oFocus = k;
      // selectionStart ném với input type=email/number -> bọc try.
      try { giu.dau = o.selectionStart; giu.cuoi = o.selectionEnd; } catch { /* không có con trỏ */ }
    }
  });
  return giu;
}

function _traDangGo(goc, giu) {
  if (!goc) return;
  $$("input, textarea, select", goc).forEach((o) => {
    const k = _khoaO(o);
    if (giu.gia.has(k)) {
      const v = giu.gia.get(k);
      if (o.type === "checkbox" || o.type === "radio") o.checked = v;
      else o.value = v;
    }
    if (giu.oFocus === k) {
      o.focus();
      if (giu.dau != null && o.setSelectionRange) {
        try { o.setSelectionRange(giu.dau, giu.cuoi); } catch { /* ô không nhận con trỏ */ }
      }
    }
  });
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
  const notes = (contact.notes || []).map((note) => `
    <article class="contact-note"><p>${esc(note.body)}</p><small>${esc(note.visibility)} · ${clock(note.created_at)}</small></article>`).join("");
  const conversations = (contact.conversations || []).map((conv) => `
    <button class="timeline-item" type="button" data-open-conv="${conv.id}">
      ${srcBadge(conv.channel)}<span>${esc(conv.account_name)} · ${esc(conv.status)}</span><time>${clock(conv.updated_at)}</time>
    </button>`).join("");
  /* Panel này bị dựng lại mỗi 6 giây (refresh -> loadContacts -> hàm này).
   * Không giữ chữ đang gõ thì ô ghi chú bàn giao 5000 ký tự biến mất giữa
   * chừng: không lỗi, không toast, người trực chỉ thấy ô trống và tưởng
   * mình bấm nhầm. Cùng bài đã giải cho ô sửa tin nhắn bằng `state.suaText`
   * và cho ô Sức khoẻ kênh bằng `state.sucKhoeKenh`. */
  const oGoc = $("#contactdetail");
  const dangGo = _luuDangGo(oGoc);
  oGoc.innerHTML = `
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
        ${state.toiQuyen.has("khach.xoa")
          /* Đếm trước khi xoá — luồng bốn mắt. Chỉ hiện cho người có
             khach.xoa: người khác bấm là ăn 403, và một nút chắc chắn
             thất bại thì không phải là nút. */
          ? `<button type="button" class="btn btn--sm btn--ghost"
                data-contact-rt="${esc(contact.id)}">Đếm dữ liệu sẽ xoá</button>`
          : ""}
      </div>
    </div>
    <div id="contact-lichsu-giao"></div>
    ${oTruongKhach(contact)}
    <h3 class="subhead">Nhãn khách hàng</h3>
    ${nhanKhachHtml(contact)}
    <h3 class="subhead">Danh tính theo kênh</h3><div class="identity-grid">${points || '<p class="empty">Chưa có danh tính.</p>'}</div>
    <h3 class="subhead">Consent</h3><div class="consent-row">${consents || '<span class="empty">Chưa ghi nhận consent.</span>'}</div>
    <form id="contact-consent-form" class="consent-form">
      <input name="purpose" maxlength="80" required placeholder="Mục đích, ví dụ marketing">
      <select name="status" aria-label="Trạng thái consent"><option value="granted">Đồng ý</option><option value="denied">Từ chối</option><option value="withdrawn">Rút lại</option></select>
      <input name="source" maxlength="300" required placeholder="Nguồn bằng chứng">
      <button class="btn btn--sm" type="submit">Ghi consent</button>
    </form>
    <h3 class="subhead">Ghi chú nội bộ</h3><div class="contact-notes">${notes || '<span class="empty">Chưa có ghi chú.</span>'}</div>
    <form id="contact-note-form" class="note-form"><textarea name="body" maxlength="5000" required placeholder="Thông tin cần bàn giao cho đội chăm sóc…"></textarea>
      <select name="visibility" aria-label="Ai đọc được ghi chú này"><option value="team">Cả đội</option><option value="manager">Quản lý</option></select><button class="btn btn--sm" type="submit">Lưu ghi chú</button></form>
    <h3 class="subhead">Hội thoại</h3><div class="timeline">${conversations || '<p class="empty">Chưa có hội thoại.</p>'}</div>`;

  /* Trả lại NGAY sau khi dựng, trước khi gắn sự kiện: gán `.value` không
     phát `input`, nên không có nguy cơ kích hoạt nhầm handler nào. */
  _traDangGo(oGoc, dangGo);

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

  $("#contact-note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.body = String(values.body || "").trim();
    if (!values.body) return;
    try {
      await api(`/contacts/${id}/notes`, { method: "POST", body: JSON.stringify(values) });
      toast("Đã lưu ghi chú nội bộ.");
      form.reset();   // xem chú thích ở form nhãn: không reset là gửi trùng
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
      form.reset();   // xem chú thích ở form nhãn: không reset là gửi trùng
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $$('[data-open-conv]').forEach((button) => button.addEventListener("click", () => {
    state.openConv = button.dataset.openConv;
    doiMan("hoithoai");
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
/* Khớp `agent/shipping/models.InternalShippingStatus`. */
const NHAN_GIAO = {
  delivering: "đang giao", delivered: "đã giao",
  delivery_failed: "giao thất bại", returned: "đã hoàn về",
};
const VAN_DON_DOI_SOAT_CHAN = new Set([
  "sending", "unknown_timeout", "reconciling", "manual_required",
]);
const VAN_DON_YEU_CAU_LABEL = {
  sending: "Đang gửi GHN",
  unknown_timeout: "Chờ đối soát GHN",
  reconciling: "Đang đối soát GHN",
  manual_required: "Cần xác nhận GHN thủ công",
};
const vnd = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

/* Thanh toán VietQR ẨN khỏi giao diện theo phiếu việc của chủ dự án
   (20.11.2026): không có ô cấu hình tài khoản nhận tiền nào được vẽ, nên
   nút QR trên dòng đơn chỉ còn là nút bấm ra lỗi "chưa cấu hình". Mã và
   API (/api/orders/{id}/vietqr*) giữ nguyên — bật lại là đổi hằng này và
   cho nhóm `thanh_toan` một ô trong `[data-api-cac-nhom]`. */
const HIEN_VIETQR = false;

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
    /* Đơn ĐÃ GIAO thì cờ xin huỷ cũng thôi nghĩa: hàng đã ở nhà khách, đó là
       đổi trả — và máy chủ từ chối huỷ đơn đã giao (cộng kho món không có
       trên kệ). */
    const xin_huy = o.yeu_cau_huy_luc && o.trang_thai !== "da_huy" && o.trang_thai !== "da_giao";
    /* Tiền khách đã trả trước (VietQR). Hiện ngay trên dòng để người đóng
       gói biết; vận đơn chỉ thu hộ phần còn lại. Không có dòng này thì
       khách đã chuyển khoản bị shipper thu lần hai. */
    const da_thu = Number(o.so_tien_da_thu || 0);
    const con_mo = o.trang_thai === "da_chot" || o.trang_thai === "cho_dong_bo";
    const tt_yc_vd = o.van_don_trang_thai_yeucau || "not_sent";
    const cho_doi_soat_vd = !o.ma_van_don && VAN_DON_DOI_SOAT_CHAN.has(tt_yc_vd);
    /* Đơn đã chốt, chưa có vận đơn: nút tạo vận đơn ngay trên dòng. Hàm tạo
       vận đơn có bốn chốt từ lâu, nhưng trước 29.10.2026 không có nút nào
       gọi tới nó — đơn chốt xong rồi nằm im, phải lên trang hãng gõ tay. */
    const tao_van_don = VAN_CHUYEN && VAN_CHUYEN.that && o.trang_thai === "da_chot"
      && !o.ma_van_don && !xin_huy && !cho_doi_soat_vd;
    const doi_tra = o.yeu_cau_doi_tra_luc && o.trang_thai !== "da_huy";
    const bang_xin_huy = xin_huy
      ? `<span class="order__xinhuy"><b>Khách xin huỷ</b> — ${clock(o.yeu_cau_huy_luc)}${
          o.yeu_cau_huy_ly_do ? " · " + esc(o.yeu_cau_huy_ly_do) : ""
        }<br>Dừng đóng gói và gọi lại cho khách trước khi quyết định.</span>`
      : "";
    const bang_doi_soat_vd = cho_doi_soat_vd
      ? `<span class="order__xinhuy"><b>${esc(VAN_DON_YEU_CAU_LABEL[tt_yc_vd] || tt_yc_vd)}</b>${
          o.van_don_client_order_code ? " · mã tham chiếu <b>" + esc(o.van_don_client_order_code) + "</b>" : ""
        }${o.van_don_so_lan_doi_soat ? " · đã đối soát " + o.van_don_so_lan_doi_soat + " lần" : ""
        }<br>${esc(o.van_don_ly_do_chan || o.van_don_loi_cuoi || "Đã tạm khoá tạo lại để tránh tạo hai vận đơn GHN.")}</span>`
      : "";

    return `<div class="row${xin_huy ? " row--xinhuy" : ""}">
      <span class="row__flag row__flag--${(xin_huy || tt_yc_vd === "manual_required") ? "halt" : (cho_duyet || cho_dong_bo || cho_doi_soat_vd) ? "assist" : o.trang_thai === "da_huy" ? "halt" : "auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(o.ma_don)} · ${esc(o.khach_ten)}
          <span class="tag tag--${ORDER_TONE[o.trang_thai] || "plain"}">${ORDER_LABEL[o.trang_thai] || o.trang_thai}</span>
          ${xin_huy ? '<span class="tag tag--halt">Khách xin huỷ</span>' : ""}
          ${cho_doi_soat_vd ? `<span class="tag tag--${tt_yc_vd === "manual_required" ? "halt" : "duyet"}">${esc(VAN_DON_YEU_CAU_LABEL[tt_yc_vd] || tt_yc_vd)}</span>` : ""}
          ${srcBadge(o.channel, o.nen_tang)}</span>
        ${bang_xin_huy}
        ${bang_doi_soat_vd}
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
        ${da_thu > 0 ? `<span class="tag tag--auto" title="${
            o.da_thu_luc ? "Ghi lúc " + esc(clock(o.da_thu_luc)) : ""}">Đã thu ${vnd(da_thu)}</span>` : ""}
        <span class="row__time">${clock(o.created_at)}</span>
        ${HIEN_VIETQR && o.trang_thai === "da_chot" ? `<span class="order__qr">
            <a class="btn btn--sm btn--ghost" href="/api/orders/${o.id}/vietqr.svg" target="_blank"
               rel="noopener" title="Mở mã VietQR (tổng hàng + phí ship)">QR</a>
            ${o.conversation_id ? `<button type="button" class="btn btn--sm" data-oqr-gui="${o.id}"
               title="Gửi mã QR thanh toán vào hội thoại của đơn">Gửi QR</button>` : ""}
          </span>` : ""}
        ${con_mo ? `<button type="button" class="btn btn--sm btn--ghost" data-odathu="${o.id}"
            data-ma="${esc(o.ma_don)}" data-goi-y="${Number(o.tong_tien || 0) + Number(o.phi_van_chuyen || 0)}"
            data-da-thu="${da_thu}" title="Ghi nhận khách đã chuyển khoản — vận đơn chỉ thu hộ phần còn lại">Đã nhận tiền</button>` : ""}
        ${cho_duyet ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--go" data-oapprove="${o.id}">Duyệt</button>
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ</button>
          </span>` : xin_huy ? `<span style="display:flex;gap:6px;margin-top:4px">
            <button type="button" class="btn btn--sm btn--halt" data-ocancel="${o.id}">Huỷ đơn</button>
          </span>` : cho_doi_soat_vd ? `<span style="display:flex;gap:6px;margin-top:4px;flex-wrap:wrap">
            <button type="button" class="btn btn--sm" data-odoisoat="${o.id}"
              title="Kiểm tra lại vận đơn trên GHN theo client_order_code">Kiểm tra GHN</button>
            <button type="button" class="btn btn--sm btn--halt" data-oxnvandon="${o.id}"
              data-omadon="${esc(o.ma_don)}" data-oref="${esc(o.van_don_client_order_code || o.ma_don)}"
              title="Xác nhận kết quả kiểm tra thủ công trên cổng GHN">Xác nhận GHN</button>
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
    const nhac = [r.can_huy_tay, r.can_hoan_tien].filter(Boolean).join(" ");
    if (nhac) toast("Đã huỷ " + r.ma_don + ". " + nhac, true);
    else toast("Đã huỷ đơn.");
  }));
  /* "Đã nhận tiền": người đối chiếu sao kê rồi ghi TỔNG đã nhận. Máy chủ
     ghi đè chứ không cộng dồn — bấm hai lần không thành trừ COD hai lần. */
  $$("[data-odathu]").forEach((b) => bam(b, async () => {
    const daCo = Number(b.dataset.daThu || 0);
    const d = await hoiHop({
      tieu_de: `Đã nhận tiền đơn ${b.dataset.ma}`,
      phu: "Đối chiếu sao kê ngân hàng trước khi ghi — hệ thống không đọc được tài khoản. "
        + "Vận đơn tạo sau đó chỉ thu hộ phần còn lại.",
      truong: [
        { name: "so_tien", label: "Tổng số tiền đã nhận (đồng)", type: "number",
          value: daCo > 0 ? daCo : b.dataset.goiY, min: 1, step: 1, required: true },
        { name: "ghi_chu", label: "Ghi chú", hint: "mã giao dịch ngân hàng…", maxlength: 300 },
      ],
      nut: "Ghi đã nhận",
    });
    if (!d) return;
    const r = await api("/orders/" + b.dataset.odathu + "/da-thu-tien", {
      method: "POST",
      body: JSON.stringify({ so_tien: parseInt(d.so_tien, 10), ghi_chu: d.ghi_chu || "" }),
    });
    if (r.can_sua_cod) toast("Đã ghi " + vnd(r.so_tien_da_thu) + ". " + r.can_sua_cod, true);
    else toast("Đã ghi nhận " + vnd(r.so_tien_da_thu) + " cho đơn " + r.ma_don
      + " · còn thu hộ " + vnd(r.thu_ho_cod) + ".");
  }));
  $$("[data-ovandon]").forEach((b) => bam(b, async () => {
    const r = await api("/orders/" + b.dataset.ovandon + "/van-don", { method: "POST", body: "{}" });
    toast(r.da_co_san ? "Đơn đã có vận đơn " + r.ma_van_don + "."
      : "Đã tạo vận đơn " + r.ma_van_don + " và nhắn mã cho khách.");
  }));
  $$("[data-odoisoat]").forEach((b) => bam(b, async () => {
    const r = await api("/orders/" + b.dataset.odoisoat + "/shipping-reconcile", { method: "POST" });
    if (r.ok && r.ma_van_don) toast("Đã đối soát GHN: khôi phục vận đơn " + r.ma_van_don + ".");
    else toast(r.ly_do_chan || r.loi || "Chưa xác nhận được trên GHN; cần kiểm tra thủ công.", true);
  }));
  $$("[data-oxnvandon]").forEach((b) => b.addEventListener("click", async () => {
    const d = await hoiHop({
      tieu_de: `Xác nhận GHN thủ công · ${b.dataset.omadon}`,
      phu: `Mã tham chiếu client_order_code: ${b.dataset.oref}. Kiểm tra cổng GHN trước khi xác nhận.`,
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
      const r = await api("/orders/" + b.dataset.oxnvandon + "/shipping-manual-confirm", {
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
      loadOrders();
    } catch (e) { toast(e.message, true); }
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

/* ---------------- tên kênh ----------------
   Bảng "Khách đến từ đâu" (`/api/analytics/khach`) đã gỡ khỏi màn ngày
   20.11.2026: nó đếm "tự xử lý" theo `status = 'auto'`, đúng con số tô
   hồng mà màn Phân tích thay bằng số đếm theo sự kiện. */
const KENH_TEN = {
  zalocrm: "Zalo cá nhân", chatwoot: "Kênh tương thích", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp", web: "Website", email: "Email",
};

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
  if (!state.knowledgeAccounts) {
    state.knowledgeAccounts = await api("/knowledge/accounts");
    state.knowledgeAccount = state.knowledgeAccount || state.knowledgeAccounts[0]?.id || "";
    const select = $("#knowledge-account");
    select.innerHTML = state.knowledgeAccounts.map((account) =>
      `<option value="${esc(account.id)}">${esc(account.name)} · ${esc(account.channel)}</option>`
    ).join("");
    select.value = state.knowledgeAccount;
    select.addEventListener("change", () => {
      state.knowledgeAccount = select.value;
      $('#probeform [name="account_id"]').value = select.value;
      loadDocs();
    });
  }
  $('#probeform [name="account_id"]').value = state.knowledgeAccount || "";
  if (!state.knowledgeAccount) {
    $("#docs").innerHTML = '<p class="empty">Bạn chưa được cấp tài khoản kênh để quản lý tri thức.</p>';
    return;
  }
  const docs = await api(`/knowledge?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
  $("#c-trithuc").textContent = docs.length;
  const canEdit = state.toiQuyen && state.toiQuyen.has("cau_hinh.sua");
  $("#docs").innerHTML = docs.length ? docs.map((d) => `<div class="row">
      <span class="row__flag row__flag--${d.status === "published" ? "auto" : "assist"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(d.title)}
          <span class="tag tag--${d.status === "published" ? "auto" : "assist"}">${d.status === "published" ? `Published v${d.published_version}` : "Draft"}</span>
        </span>
        <span class="row__sub">${d.chunks} đoạn · ${d.draft_version ? `Draft v${d.draft_version} · index ${esc(d.index_status)}` : "không có Draft"}${d.index_error ? ` · ${esc(d.index_error)}` : ""}</span>
      </span>
      <span class="row__side">
        <span class="row__nut">
          ${canEdit ? `<button type="button" class="btn btn--sm" data-doc-edit="${d.id}">Sửa Draft</button>` : ""}
          ${canEdit && d.draft_version_id && d.index_status === "ready" ? `<button type="button" class="btn btn--sm btn--go" data-doc-publish="${d.id}" data-version="${d.draft_version_id}">Publish v${d.draft_version}</button>` : ""}
          <button type="button" class="btn btn--sm" data-doc-history="${d.id}" data-published="${d.published_version_id || ""}">Lịch sử</button>
          ${canEdit ? `<button type="button" class="btn btn--sm btn--halt" data-doc-archive="${d.id}">Lưu trữ</button>` : ""}
        </span>
        <span class="row__time">${clock(d.updated_at)}</span>
      </span>
    </div>`).join("")
    : '<p class="empty">Chưa có tài liệu. Tài liệu mới sẽ ở Draft cho tới khi được Publish.</p>';

  $$('[data-doc-edit]').forEach((b) =>
    b.addEventListener("click", async () => {
      const d = await api(`/knowledge/${b.dataset.docEdit}?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
      const f = $("#docform");
      f.elements.document_id.value = d.id;
      f.elements.title.value = d.title;
      f.elements.text.value = d.draft_content || d.published_content || "";
      $("#docsave").textContent = d.draft_version ? `Lưu Draft v${d.draft_version}` : "Tạo Draft mới";
      f.elements.title.focus();
    })
  );
  $$('[data-doc-publish]').forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await api(`/knowledge/${b.dataset.docPublish}/publish`, {
        method: "POST",
        body: JSON.stringify({ account_id: state.knowledgeAccount, version_id: b.dataset.version }),
      });
      toast(r.already_published ? "Phiên bản này đã Published trước đó." : `Đã Publish v${r.version}.`);
      await loadDocs();
    } catch (e) { toast(e.message, true); }
    finally { b.disabled = false; }
  }));
  $$('[data-doc-history]').forEach((b) => b.addEventListener("click", async () => {
    const versions = await api(`/knowledge/${b.dataset.docHistory}/versions?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
    $("#docversions").innerHTML = `<h3 class="panel__head">Lịch sử phiên bản</h3>` + versions.map((v) => `<div class="row">
      <span class="row__flag row__flag--${v.status === "published" ? "auto" : v.status === "draft" ? "assist" : "plain"}"></span>
      <span class="row__body"><span class="row__title">v${v.version} · ${esc(v.status)}</span>
        <span class="row__sub">${v.chunk_count} đoạn · index ${esc(v.index_status)} · ${esc(v.content).slice(0, 180)}</span></span>
      <span class="row__side">${canEdit && ["published", "superseded"].includes(v.status) && v.id !== b.dataset.published
        ? `<button type="button" class="btn btn--sm" data-doc-rollback="${b.dataset.docHistory}" data-version="${v.id}">Rollback từ v${v.version}</button>` : ""}
        <span class="row__time">${clock(v.published_at || v.created_at)}</span></span>
    </div>`).join("");
    $$('[data-doc-rollback]').forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const r = await api(`/knowledge/${button.dataset.docRollback}/rollback`, {
          method: "POST",
          body: JSON.stringify({ account_id: state.knowledgeAccount, version_id: button.dataset.version }),
        });
        toast(`Đã rollback thành Published v${r.version}.`);
        $("#docversions").innerHTML = "";
        await loadDocs();
      } catch (e) { toast(e.message, true); }
      finally { button.disabled = false; }
    }));
  }));
  $$('[data-doc-archive]').forEach((b) => b.addEventListener("click", async () => {
    /* Hỏi trước khi lưu trữ: tài liệu tri thức là CĂN CỨ agent dùng để trả
     * lời. Bấm trượt là agent mất căn cứ — nó không nói sai, nó chuyển người
     * ở mọi câu lẽ ra tự trả lời được, và không ai nhìn ra vì sao. */
    const ten = b.closest(".row")?.querySelector(".row__title")?.firstChild?.textContent || "tài liệu này";
    if (!confirm(`Lưu trữ "${ten.trim()}"?\n\n`
        + "Agent sẽ thôi dùng nó làm căn cứ trả lời. Lịch sử phiên bản vẫn được giữ.")) return;
    b.disabled = true;
    try {
      await api(`/knowledge/${b.dataset.docArchive}?account_id=${encodeURIComponent(state.knowledgeAccount)}`, { method: "DELETE" });
      toast("Đã lưu trữ tài liệu; lịch sử vẫn được bảo toàn.");
      await loadDocs();
    } catch (e) {
      toast(e.message, true);
      b.disabled = false;
    }
  }));
}

$("#docform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const documentId = f.get("document_id");
  const button = $("#docsave");
  button.disabled = true;
  toast("Đang lưu Draft và tạo embedding…");
  try {
    const r = await api(documentId ? `/knowledge/${documentId}/draft` : "/knowledge", {
      method: documentId ? "PUT" : "POST",
      body: JSON.stringify({ account_id: f.get("account_id"), title: f.get("title"), text: f.get("text") }),
    });
    toast(`Đã lưu Draft v${r.version} (${r.chunks} đoạn). Chưa dùng trong RAG cho tới khi Publish.`);
    ev.target.reset();
    ev.target.elements.account_id.value = state.knowledgeAccount;
    $("#docsave").textContent = "Lưu Draft";
    await loadDocs();
  } catch (e) { toast(e.message, true); }
  finally { button.disabled = false; }
});

$("#docnew").addEventListener("click", () => {
  const f = $("#docform");
  f.reset();
  f.elements.account_id.value = state.knowledgeAccount || "";
  $("#docsave").textContent = "Lưu Draft";
});

$("#probeform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = new FormData(ev.target).get("question");
  try {
    const r = await api("/knowledge/probe", {
      method: "POST", body: JSON.stringify({ account_id: state.knowledgeAccount, question: q }),
    });
    $("#probe").innerHTML = r.hits.length ? r.hits.map((h) => `<div class="row">
        <span class="row__flag row__flag--spend"></span>
        <span class="row__body">
          <span class="row__title">${esc(h.doc)} · v${h.version}</span>
          <span class="row__sub">${esc(h.excerpt)} · chunk ${esc(h.chunk_id || "—")}</span>
        </span>
        <span class="row__side"><span class="probe__score">${h.score.toFixed(3)}</span></span>
      </div>`).join("")
      : '<p class="empty">Không tìm thấy đoạn nào đủ khớp. Agent sẽ chuyển câu này cho người.</p>';
  } catch (e) { toast(e.message, true); }
});

/* ==================== Hộp thoại nhập chung ====================
 *
 * Thay cho prompt() của trình duyệt. prompt() có đúng một ô chữ: không
 * nhãn, không ô số, không ô ngày, không kiểm gì; hỏi hai thứ là hai hộp
 * nối nhau, bấm Huỷ ở hộp sau là mất hộp trước — đo được ở Tạo việc, Nhập
 * kho, Kiểm kê, Gộp khách, Đo bài đăng. Một hộp cho cả app, dựng ô theo mô
 * tả; dùng lại lớp phủ `.cong` của màn đăng nhập nên chỉ có MỘT kiểu hộp
 * thoại. Trả Promise<obj|null>: null là người dùng thôi.
 *
 *   hoiHop({ tieu_de, phu, truong: [{ name, label, type, value, required,
 *            placeholder, hint, min, max, step, maxlength, options, rows }],
 *            nut, nguy_hiem })
 */
let hoiDangMo = null;

function hoiHop({ tieu_de, phu = "", truong = [], nut = "Lưu", nguy_hiem = false }) {
  if (hoiDangMo) hoiDong(null);           // hộp mới thay hộp cũ, không chồng
  $("#hoiTen").textContent = tieu_de;
  $("#hoiPhu").textContent = phu;
  $("#hoiPhu").hidden = !phu;
  $("#hoiLoi").textContent = "";
  $("#hoiTruong").innerHTML = truong.map((t) => {
    const chung = `name="${esc(t.name)}"${t.required ? " required" : ""}`
      + (t.placeholder ? ` placeholder="${esc(t.placeholder)}"` : "")
      + (t.maxlength ? ` maxlength="${t.maxlength}"` : "");
    let o;
    if (t.type === "textarea") {
      o = `<textarea ${chung} rows="${t.rows || 3}">${esc(t.value ?? "")}</textarea>`;
    } else if (t.type === "select") {
      o = `<select ${chung}>${(t.options || []).map((c) =>
        `<option value="${esc(c.value)}"${String(c.value) === String(t.value ?? "") ? " selected" : ""}>${esc(c.label)}</option>`).join("")}</select>`;
    } else {
      o = `<input type="${esc(t.type || "text")}" ${chung} value="${esc(t.value ?? "")}"`
        + (t.min != null ? ` min="${t.min}"` : "") + (t.max != null ? ` max="${t.max}"` : "")
        + (t.step != null ? ` step="${t.step}"` : "") + ` autocomplete="off">`;
    }
    return `<label class="field"><span>${esc(t.label)}${
      t.hint ? ` <em class="hint">${esc(t.hint)}</em>` : ""}</span>${o}</label>`;
  }).join("");
  const nutGui = $("#hoiNut");
  nutGui.textContent = nut;
  nutGui.classList.toggle("btn--halt", nguy_hiem);
  nutGui.classList.toggle("btn--primary", !nguy_hiem);
  $("#congHoi").classList.remove("is-off");
  const dau = $("#hoiTruong").querySelector("input, textarea, select");
  if (dau) setTimeout(() => dau.focus(), 0);
  return new Promise((resolve) => { hoiDangMo = resolve; });
}

function hoiDong(gia_tri) {
  $("#congHoi").classList.add("is-off");
  const tra = hoiDangMo;
  hoiDangMo = null;
  if (tra) tra(gia_tri);
}

$("#hoiform")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const d = Object.fromEntries(new FormData(e.currentTarget).entries());
  for (const k of Object.keys(d)) if (typeof d[k] === "string") d[k] = d[k].trim();
  hoiDong(d);
});
$("#hoiHuy")?.addEventListener("click", (e) => { e.preventDefault(); hoiDong(null); });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && hoiDangMo) hoiDong(null);
});

/* ---------------- nhật ký ---------------- */

/* Chi tiết sự kiện cho NGƯỜI đọc, không phải JSON thô.
 *
 * `{"muc_do":"hong","tieu_de":"Hệ thống đang hỏng","chi_tiet":...}` dài
 * 2.600 ký tự bị cắt sau 90 — người trực thấy đúng phần vô nghĩa nhất.
 * Báo động thì hiện tiêu đề và chi tiết; lỗi thì hiện lỗi; còn lại là
 * `khoá: giá trị`. JSON đầy đủ vẫn còn trong `title` để rê chuột xem. */
function moTaChiTiet(d) {
  if (d == null) return "";
  if (typeof d !== "object") return String(d);
  if (d.tieu_de) return [d.tieu_de, d.chi_tiet].filter(Boolean).join(" — ");
  if (d.error) return String(d.error);
  return Object.entries(d).map(([k, v]) =>
    `${k}: ${v !== null && typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
}

async function loadEvents() {
  /* Nhật ký kiểm toán cần quyền riêng `nhat_ky.doc`. Không có quyền thì nói
     rõ ngay trên ô — để lỗi 403 nổ lên thì cả vòng làm mới màn Nhật ký dừng. */
  if (state.toiQuyen && !state.toiQuyen.has("nhat_ky.doc")) {
    $("#events").innerHTML = '<p class="empty">Cần quyền "Xem nhật ký kiểm toán" để xem mục này.</p>';
    return;
  }
  const evs = await api("/events");
  $("#events").innerHTML = evs.length ? evs.map((e) => {
    const tone = e.kind.includes("error") || e.kind.includes("failed") ? "halt"
      : e.kind.includes("escalat") ? "assist" : "auto";
    // Tác nhân là "system" hay UUID toàn số 0 đều là hệ thống tự làm —
    // in chuỗi 36 ký tự ấy ra chỉ tốn chỗ và không ai đọc.
    const ai = !e.actor || e.actor === "system" || /^0{8}-/.test(e.actor) ? "hệ thống" : e.actor;
    return `<div class="row">
      <span class="row__flag row__flag--${tone}"></span>
      <span class="row__body">
        <span class="row__title">${esc(e.kind)}</span>
        <span class="row__sub" title="${esc(JSON.stringify(e.detail))}">${esc(moTaChiTiet(e.detail))}</span>
      </span>
      <span class="row__side">
        <span class="row__num">${esc(ai)}</span>
        <span class="row__time">${clock(e.at)}</span>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có sự kiện nào.</p>';
}


/* Định dạng số kiểu Việt Nam — màn Kho và Chi phí dùng chung. */
const num = (n) => Number(n || 0).toLocaleString("vi-VN");


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
        Cấp quyền ấy cho ít nhất một người nữa ở <b>Nhân sự &amp; Phân quyền</b>.</div>`
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

  /* Máy chủ chỉ trả dữ liệu trong kênh người này được giao. Còn dữ liệu ở
     kênh khác thì PHẢI nói ra: im lặng là nhân viên trả lời khách "không
     giữ gì của anh/chị" trong khi kênh khác có — sai nghĩa vụ trả lời yêu
     cầu của chủ thể dữ liệu. */
  const ngoai = d.con_ngoai_pham_vi
    ? `<p class="kit__note"><b>Còn dữ liệu của số này ở kênh bạn không được giao.</b>
        Chuyển yêu cầu cho quản trị để xem và xử lý đủ.</p>` : "";
  if (!d.co_du_lieu) {
    $("#pdpdOut").innerHTML = ngoai ||
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
          ${h.nhan} nhãn${(h.nhan_ten || []).length ? ` (${esc(h.nhan_ten.join(", "))})` : ""} · ${h.dong_y} dòng đồng ý${h.co_sdt ? " · có số điện thoại" : ""}${
            h.co_email ? " · có email" : ""}</span>
      </span>
    </div>`).join("");

  $("#pdpdOut").innerHTML = `${ngoai}
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
      $("#mkform").mat_khau_cu.focus();
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
 *
 * Gửi kèm mật khẩu HIỆN TẠI: máy chủ đòi, để phiên bị chiếm không tự đổi
 * được mật khẩu rồi đá chủ thật ra khỏi mọi thiết bị.
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
      body: JSON.stringify({ mat_khau_cu: d.mat_khau_cu, mat_khau_moi: d.mat_khau_moi }),
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

const congViec = { trangThai: [], uuTien: [], ds: [], banNhap: {} };
let cvKetQuaDangGui = false;
let cvKetQuaBangChung = null;

const CV_LOAI_DON = { sua: "Sửa đơn", huy: "Hủy đơn" };
const CV_KET_QUA = {
  thanh_cong: "Đã xử lý thành công",
  khong_the: "Không thể thực hiện",
  cho_doi_soat: "Đang chờ đối soát",
};

function cvLaXuLyDon(v) {
  return Boolean(v.order_id && CV_LOAI_DON[v.loai_xu_ly_don]);
}

function cvDuocXacNhan() {
  return state.toiQuyen.has("don.sua")
    && state.toiQuyen.has("cong_viec.sua");
}

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
  const xuLyDon = cvLaXuLyDon(v);
  const loai = xuLyDon
    ? ` <span class="pill">${esc(CV_LOAI_DON[v.loai_xu_ly_don])}</span>` : "";
  const don = v.ma_don ? ` · đơn ${esc(v.ma_don)}` : "";
  const ketQua = v.ket_qua_xu_ly_don
    ? ` · ${esc(CV_KET_QUA[v.ket_qua_xu_ly_don] || v.ket_qua_xu_ly_don)}` : "";
  const xacNhan = xuLyDon && cvDuocXacNhan()
    && !["thanh_cong", "khong_the"].includes(v.ket_qua_xu_ly_don);
  return `<div class="row" data-cv="${esc(v.id)}">
    <span class="row__flag row__flag--${cvCoTrangThai(v)}"></span>
    <div class="row__main">
      <b>${esc(v.tieu_de)}${loai}${v.nguon === "agent"
        ? ' <span class="pill">agent chuyển</span>' : ""}</b>
      <span class="row__sub">${esc(nhanTT[v.trang_thai] || v.trang_thai)} · ${
        esc(nhanUT[v.uu_tien] || v.uu_tien)}${don}${ketQua}${
        v.khach_ten ? " · " + esc(v.khach_ten) : ""}${
        v.mo_ta ? " · " + esc(v.mo_ta.slice(0, 90)) : ""} · tạo ${clock(v.tao_luc)}</span>
    </div>
    <div class="row__side">
      <span>${chu} ${han}</span>
      <span class="row__nut">
        ${!xuLyDon && v.trang_thai !== "xong"
          ? `<button type="button" class="btn btn--sm btn--ghost" data-cvxong="${esc(v.id)}">Xong</button>`
          : !xuLyDon
            ? `<button type="button" class="btn btn--sm btn--ghost" data-cvmolai="${esc(v.id)}">Mở lại</button>`
            : ""}
        ${xuLyDon ? `<button type="button" class="btn btn--sm btn--ghost" data-cvchitiet="${esc(v.id)}">Chi tiết</button>` : ""}
        ${xacNhan ? `<button type="button" class="btn btn--sm" data-cvketqua="${esc(v.id)}">Xác nhận</button>` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-cvnhan="${esc(v.id)}">Nhận</button>
        <button type="button" class="btn btn--sm btn--ghost" data-cvsua="${esc(v.id)}">Sửa</button>
      </span>
    </div>
  </div>`;
}

function cvLuuBanNhap() {
  const id = congViec.dangXem;
  if (!id || !$("#cvkKetQua") || !$("#cvkLyDo")) return;
  congViec.banNhap[id] = {
    ket_qua: $("#cvkKetQua").value,
    ly_do: $("#cvkLyDo").value,
  };
}

function cvDongKetQua() {
  cvLuuBanNhap();
  $("#congCvKetQua").classList.add("is-off");
}

function cvLoiTheoMa(err) {
  const nhan = {
    403: "Bạn không có quyền xác nhận công việc này.",
    404: "Công việc hoặc đơn hàng không còn tồn tại.",
    409: "Trạng thái hoặc bằng chứng ERPNext không phù hợp.",
    422: "Dữ liệu xác nhận chưa hợp lệ.",
  };
  return `${nhan[err.ma] || "Không gửi được kết quả."} ${err.message || ""}`.trim();
}

async function cvApiCoHan(path, options = {}, ms = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await api(path, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function cvVeBangChung(v, data = null, loi = "") {
  const el = $("#cvkBangChung");
  el.classList.toggle("cvk__evidence--error", Boolean(loi));
  el.classList.toggle("cvk__evidence--pending", !data && !loi);
  if (loi) {
    el.textContent = loi;
  } else if (!data) {
    el.textContent = "Đang đọc trạng thái hiện hành từ ERPNext…";
  } else {
    el.innerHTML = `<b>ERPNext ${esc(data.erp_tham_chieu)}</b> · ${
      esc(data.trang_thai || "chưa có trạng thái")} · docstatus ${
      esc(data.docstatus)}<br>Phiên bản xác minh: ${esc(data.modified || "không có")}`;
  }
  $("#cvkDocLai").hidden = !cvDuocXacNhan() || !cvLaXuLyDon(v);
}

async function cvTaiBangChung(v) {
  cvKetQuaBangChung = null;
  cvVeBangChung(v);
  try {
    const path = `/orders/${encodeURIComponent(v.order_id)}/action-evidence?cong_viec_id=${
      encodeURIComponent(v.id)}`;
    cvKetQuaBangChung = await cvApiCoHan(path, {}, 15000);
    cvVeBangChung(v, cvKetQuaBangChung);
  } catch (err) {
    const msg = err.name === "AbortError"
      ? "ERPNext phản hồi quá lâu. Công việc chưa thay đổi; thử đọc lại sau."
      : cvLoiTheoMa(err);
    cvVeBangChung(v, null, msg);
  }
}

async function cvMoKetQua(id, moThaoTac = false) {
  const v = (congViec.ds || []).find((x) => x.id === id);
  if (!v || !cvLaXuLyDon(v)) return;
  cvLuuBanNhap();
  congViec.dangXem = id;
  cvKetQuaBangChung = null;
  const nhap = congViec.banNhap[id] || {
    ket_qua: v.ket_qua_xu_ly_don || "thanh_cong",
    ly_do: v.ly_do_ket_qua || "",
  };
  $("#cvkTen").textContent = v.tieu_de;
  $("#cvkPhu").textContent = `${CV_LOAI_DON[v.loai_xu_ly_don]} · đơn ${v.ma_don || "—"}`;
  $("#cvkChiTiet").innerHTML = [
    ["Trạng thái", v.trang_thai],
    ["Ưu tiên", v.uu_tien],
    ["Người phụ trách", v.nguoi_nhan_ten || "Chưa giao"],
    ["Tạo lúc", new Date(v.tao_luc).toLocaleString("vi-VN")],
    ["Mã ERP", v.order_erp_ma_don || "Chưa đồng bộ"],
    ["Trạng thái đơn", v.order_trang_thai || "—"],
    ["Xử lý bởi", v.xu_ly_boi_ten || "Chưa xác nhận"],
    ["Trạng thái ERP đã lưu", v.erp_trang_thai || "Chưa có"],
    ["Yêu cầu khách hàng", v.mo_ta || "Không có mô tả"],
    ["Kết quả đã lưu", v.ket_qua_xu_ly_don
      ? `${CV_KET_QUA[v.ket_qua_xu_ly_don] || v.ket_qua_xu_ly_don}${
          v.ly_do_ket_qua ? " — " + v.ly_do_ket_qua : ""}` : "Chưa có"],
  ].map(([label, value], i) => `<div class="cvk__item${i >= 8 ? " cvk__item--wide" : ""}">
      <span class="cvk__label">${esc(label)}</span><span class="cvk__value">${esc(value)}</span>
    </div>`).join("");
  $("#cvkKetQua").value = nhap.ket_qua;
  $("#cvkLyDo").value = nhap.ly_do;
  $("#cvkLoi").textContent = "";
  $("#cvkHoiThoai").hidden = !v.conversation_id;
  const duocLam = moThaoTac && cvDuocXacNhan()
    && !["thanh_cong", "khong_the"].includes(v.ket_qua_xu_ly_don);
  $("#cvkThaoTac").hidden = !duocLam;
  $("#cvkGui").hidden = !duocLam;
  $("#cvkDocLai").hidden = !duocLam;
  $("#congCvKetQua").classList.remove("is-off");
  if (duocLam) await cvTaiBangChung(v);
  else cvVeBangChung(v, v.erp_tham_chieu ? {
    erp_tham_chieu: v.erp_tham_chieu,
    trang_thai: v.erp_trang_thai,
    modified: v.erp_sua_luc,
    docstatus: "—",
  } : null, v.erp_tham_chieu ? "" : "Chưa có bằng chứng ERPNext đã lưu.");
}

async function cvGuiKetQua(e) {
  e.preventDefault();
  if (cvKetQuaDangGui) return;
  const v = (congViec.ds || []).find((x) => x.id === congViec.dangXem);
  if (!v || !cvDuocXacNhan()) return;
  const d = Object.fromEntries(new FormData(e.currentTarget).entries());
  const bangChungSua = cvKetQuaBangChung
    ? cvKetQuaBangChung.modified || null : null;
  if (d.ket_qua === "thanh_cong"
      && v.loai_xu_ly_don === "sua" && !bangChungSua) {
    $("#cvkLoi").textContent =
      "Yêu cầu sửa thành công chưa có phiên bản ERPNext đã xác minh. Bấm “Đọc lại ERPNext”.";
    return;
  }
  if (d.ket_qua === "khong_the" && String(d.ly_do || "").trim().length < 3) {
    $("#cvkLoi").textContent = "Kết quả không thể thực hiện cần có lý do rõ ràng.";
    return;
  }
  cvKetQuaDangGui = true;
  const cvkGui = $("#cvkGui");
  cvkGui.disabled = true;
  cvkGui.textContent = "Đang xác nhận…";
  $("#cvkLoi").textContent = "";
  try {
    const result = await cvApiCoHan(
      `/orders/${encodeURIComponent(v.order_id)}/confirm-action-result`,
      {
        method: "POST",
        body: JSON.stringify({
          cong_viec_id: v.id,
          loai: v.loai_xu_ly_don,
          ket_qua: d.ket_qua,
          ly_do: d.ly_do || "",
          erp_modified_at: bangChungSua,
        }),
      },
      20000,
    );
    delete congViec.banNhap[v.id];
    const cho = result.ket_qua === "cho_doi_soat";
    toast(result.thong_bao || (cho ? "Đang chờ đối soát." : "Đã ghi nhận kết quả."), cho);
    await loadCongViec();
    const moi = congViec.ds.find((x) => x.id === v.id);
    if (moi) {
      moi.trang_thai = result.trang_thai_cong_viec;
      moi.ket_qua_xu_ly_don = result.ket_qua;
    }
    cvDongKetQua();
  } catch (err) {
    $("#cvkLoi").textContent = err.name === "AbortError"
      ? "Yêu cầu bị Timeout; không đổi trạng thái công việc trên giao diện. Tải lại danh sách trước khi thử lại."
      : cvLoiTheoMa(err);
  } finally {
    cvKetQuaDangGui = false;
    cvkGui.disabled = false;
    cvkGui.textContent = "Xác nhận kết quả";
  }
}

$("#cvkForm")?.addEventListener("submit", cvGuiKetQua);
$("#cvkDong")?.addEventListener("click", (e) => { e.preventDefault(); cvDongKetQua(); });
$("#cvkDocLai")?.addEventListener("click", async () => {
  const v = congViec.ds.find((x) => x.id === congViec.dangXem);
  if (v && !cvKetQuaDangGui) await cvTaiBangChung(v);
});
$("#cvkHoiThoai")?.addEventListener("click", () => {
  const v = congViec.ds.find((x) => x.id === congViec.dangXem);
  if (!v?.conversation_id) return;
  cvDongKetQua();
  state.openConv = v.conversation_id;
  doiMan("hoithoai");
});

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
  ];
  if (!cvLaXuLyDon(v)) {
    truong.push({ name: "trang_thai", label: "Trạng thái", type: "select",
      value: v.trang_thai,
      options: congViec.trangThai.map((t) => ({ value: t.ma, label: t.nhan })) });
  }
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

  const than = { uu_tien: d.uu_tien };
  if (d.trang_thai) than.trang_thai = d.trang_thai;
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
  // Màn Công việc mới (25-cong-viec.js) nghe để vẽ lại sau khi hộp xác nhận
  // kết quả đơn ở đây vừa đổi dữ liệu.
  document.dispatchEvent(new CustomEvent("congviec:doi"));
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
  const ketqua = e.target.closest("[data-cvketqua]");
  if (ketqua) { await cvMoKetQua(ketqua.dataset.cvketqua, true); return; }
  const chitiet = e.target.closest("[data-cvchitiet]");
  if (chitiet) { await cvMoKetQua(chitiet.dataset.cvchitiet, false); return; }
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
    + (n.vai_tro_ngung || []).map((t) =>
      ` <span class="pill pill--warn" title="Vai trò đã ngừng dùng — không cấp quyền nào">${esc(t)} · ngừng dùng</span>`).join("")
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
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.email ? " · " + esc(n.email) : ""}${n.khoa ? " · đã khoá" : ""}${
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
  /* Vai trò từng có người mang chỉ NGỪNG DÙNG được (mục 13.9) — Xoá chỉ
   * hiện khi máy chủ sẽ cho xoá (`xoa_duoc`). */
  const nut = (v.toan_quyen
    ? ""
    : `<button type="button" class="btn btn--sm btn--ghost" data-suavai="${esc(v.id)}">Sửa</button>`)
      + (v.he_thong ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-trangthaivai="${esc(v.id)}">${v.dang_dung ? "Ngừng dùng" : "Dùng lại"}</button>`)
      + (v.xoa_duoc ? `<button type="button" class="btn btn--sm btn--ghost" data-xoavai="${esc(v.id)}">Xoá</button>` : "");
  return `<div class="row">
    <span class="row__flag row__flag--${v.toan_quyen ? "halt" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(v.ten)}${v.he_thong ? ' <span class="pill">dựng sẵn</span>' : ""}${
        v.dang_dung === false ? ' <span class="tag tag--plain">ngừng dùng</span>' : ""}</b>
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
  // Dùng CHUNG với 24-nhan-su.js: bảng tick theo nhóm chức năng, khoá kèm
  // chuyển việc, lịch sử — một bản luật, không hai.
  nsv.nguoi = ds;
  nsv.vaiTro = vt.vai_tro;
  nsv.nhom = dm.nhom_hien_thi || [];
  nsvVeLichSu($("#nsLichSu"));
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
      + nhanSu.vaiTro.filter((v) => v.dang_dung !== false)
        .map((v) => `<option value="${esc(v.id)}">${esc(v.ten)}</option>`).join("");
  }
}

/* Nhóm theo CHỨC NĂNG dashboard (phiếu việc mục 12.2) — dùng chung bảng
   của 24-nhan-su.js, không còn nhóm theo tiền tố mã quyền. */
function nsVeBangQuyen(dangCo) {
  return nsvBangQuyen(dangCo);
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
  const tt = e.target.closest("[data-trangthaivai]");
  if (tt) {
    if (await nsvDoiTrangThaiVai(nhanSu.vaiTro.find((v) => v.id === tt.dataset.trangthaivai))) {
      await loadNhanSu();
    }
    return;
  }
  const xoa = e.target.closest("[data-xoavai]");
  if (!xoa) return;
  const v = nhanSu.vaiTro.find((x) => x.id === xoa.dataset.xoavai);
  /* Nói SỐ NGƯỜI bị ảnh hưởng, không hỏi "bạn có chắc không".
   * "Có chắc không" là câu hỏi không mang thông tin nào — người ta bấm OK
   * theo phản xạ. "3 người sẽ mất các quyền này" thì họ dừng lại. */
  const loi = `Xoá hẳn vai trò “${v.ten}”? Chưa ai từng được gán vai trò này nên không mất lịch sử nào.`;
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
    /* Khoá người đang giữ hội thoại/việc: hỏi chuyển việc trước — cùng một
       hàm với tab Nhân viên mới (24-nhan-su.js). */
    const n = nsv.nguoi.find((x) => x.ten_dang_nhap === ten);
    if (!dangKhoa && n) { await nsvKhoa(n, loadNhanSu); return; }
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
      nhanSu.vaiTro.map((v) => {
        const co = dangCo.has(v.ten) || (hien.vai_tro_ngung || []).includes(v.ten);
        return `<label class="quyen__o">
        <input type="checkbox" value="${esc(v.id)}"${co ? " checked" : ""}${v.dang_dung === false && !co ? " disabled" : ""}>
        <span>${esc(v.ten)}${v.dang_dung === false ? " · ngừng dùng" : ""}</span>
        <small>${esc(v.mo_ta || "")}</small></label>`;
      }).join("")}
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
        email: String(d.email || "").trim() || null,
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
      : '<p class="empty">Chưa nối kênh nào. Nối ở Cấu hình chung → Kết nối & Tích hợp rồi quay lại.</p>'}
      </fieldset>
      <div class="row__nut">
        <button type="button" class="btn btn--sm btn--primary" data-kenhluu="${esc(id)}">Lưu</button>
        <button type="button" class="btn btn--sm btn--ghost" data-kenhhuy="${esc(id)}">Huỷ</button>
      </div>`;
    gan.closest(".row").insertAdjacentElement("afterend", bang);
  } catch (err) { toast(err.message, true); }
});

/* ---------------- vòng làm mới ---------------- */

async function refresh() {
  // Chuông chạy RIÊNG, không await: nó tự nuốt lỗi của mình, và một màn
  // hỏng ở dưới không được làm chuông đứng (19-thong-bao.js).
  taiSoThongBao();
  try {
    await loadOverview();
    // Mô-đun đăng ký SAU lần đầu tab hiện vẫn được gắn ở nhịp kế tiếp.
    ganTabDangHien();
    if (state.view === "hoithoai") await loadConversations();
    if (state.view === "khachhang") { await loadTruongKhach(); await loadContacts(); }
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "sohieu") {    // nhãn hiển thị: "Phân tích"
      if (!state.ptDaTai) await loadPhanTich();
      await loadCost();
    }
    /* Màn có tab: nạp THEO TAB đang hiện, không theo màn — mỗi màn cài đặt
       gộp ba bốn màn cũ, nạp cả màn là kéo dữ liệu cho ba tab không ai nhìn.
       `dangMo(id)` = tab đang hiện VÀ chưa bị mô-đun gắn vào thay thế;
       `tabDangHien(id)` cho các khối luôn ở lại dù có mô-đun gắn vào.
       Tab gộp nhiều nguồn thì mỗi nguồn kèm `coQuyen`: thiếu một quyền mà
       vẫn gọi là một 403 chặn mọi loader phía sau, mỗi 6 giây. */
    if (dangMo("cv-ca-truc")) { await loadTinChet(); await loadVoChu(); await loadCaCuaToi(); await loadTongQuanCa(); }
    if (dangMo("cv-danh-sach")) await loadCongViec();
    if (tabDangHien("cc-nhan")) await loadTruongKhach();
    if (dangMo("cc-tu-dong")) { await loadMauNhanh(); await loadQuyTac(); }
    if (tabDangHien("cc-ket-noi") && coQuyen("kenh.doc")) {
      if (coQuyen("agent.doc")) await loadHoSoAgent();
      await loadSucKhoeKenh(); await loadKetNoi();
    }
    if (dangMo("cc-ket-noi")) {
      await loadCaiDatApi();
      if (coQuyen("don.doc")) await loadErpCauHinh();
      if (coQuyen("tich_hop.doc")) await loadTichHop();
    }
    if (dangMo("cc-sla")) { await loadDinhTuyen(); await loadCaiDatApi(); }
    if (dangMo("cc-dieu-phoi")) await loadDinhTuyen();
    if (tabDangHien("ai-co-ban")) {
      if (coQuyen("cau_hinh.doc")) await loadCauHinh();
      if (coQuyen("agent.doc")) await loadHoSoAgent();
    }
    if (tabDangHien("ai-co-ban") && !daGan("ai-co-ban-nha-cung-cap")) await loadCaiDatApi();
    if (dangMo("ai-tri-thuc")) await loadDocs();
    if (dangMo("ai-ky-nang")) await loadKyNang();
    if (dangMo("ai-phong-thu") && !state.phongThuDaTai) await loadPhongThu();
    if (dangMo("ns-nhan-vien") || dangMo("ns-vai-tro")) await loadNhanSu();
    if (tabDangHien("ns-nhan-vien")) await loadLichCa();
    if (tabDangHien("ns-vai-tro")) await loadTamNhin();
    if (dangMo("ht-suc-khoe")) await loadHeThong();
    if (dangMo("ht-sao-luu")) {
      await loadYeuCauChuThe();
      if (coQuyen("khach.pii")) { await loadPdpdPolicy(); await loadRetention(); }
      await loadCaiDatApi();
    }
    if (dangMo("ht-nhat-ky")) await loadEvents();
  } catch (e) {
    toast("Không nối được máy chủ: " + e.message, true);
  }
}

function startInboxStream() {
  if (!("EventSource" in window)) return;
  const stream = new EventSource("/api/inbox/events");
  state.stream = stream;      // để api() đóng được khi phiên hết
  const schedule = () => {
    clearTimeout(inboxRefreshTimer);
    inboxRefreshTimer = setTimeout(async () => {
      taiSoThongBao();
      try {
        await loadOverview();
        if (state.view === "hoithoai") await loadConversations();
        if (state.view === "khachhang") await loadContacts();
      } catch { /* EventSource tự nối lại; polling 6 giây vẫn là fallback. */ }
    }, 120);
  };
  /* Mọi sự kiện SLA máy chủ phát (agent/omnichannel/sla.py) phải có ở đây:
     thiếu `sla.resolution_breached` là hội thoại trễ hạn giải quyết chỉ hiện
     ra ở nhịp 6 giây sau — hoặc không bao giờ, khi tab đang ở màn khác. */
  ["message.created", "message.sent", "conversation.updated", "conversation.takeover",
   "conversation.released", "conversation.priority_changed",
   "sla.first_response_warning", "sla.first_response_breached",
   "sla.resolution_warning", "sla.resolution_breached",
   "sla.handover_response_warning", "sla.handover_response_breached"]
    .forEach((topic) => stream.addEventListener(topic, schedule));
  /* Màn Phân tích không theo nhịp 6 giây; sự kiện SLA mới thì đánh dấu để
     lần tới mở màn (hoặc đang mở) tính lại. */
  ["sla.first_response_breached", "sla.resolution_breached",
   "sla.first_response_warning", "sla.resolution_warning",
   "sla.handover_response_warning", "sla.handover_response_breached"]
    .forEach((topic) => stream.addEventListener(topic, () => {
      state.ptDaTai = false;
    }));
  window.addEventListener("beforeunload", () => stream.close(), { once: true });
}

// Chỉ bắt đầu vòng làm mới SAU KHI xác nhận có phiên. Gọi refresh() ngay
// khi chưa đăng nhập thì mọi request trả 401 và người dùng thấy một loạt
// thông báo lỗi trước cả khi kịp nhìn thấy ô đăng nhập.
kiemPhien().then((co) => {
  if (!co) return;
  // Một chỗ quyết định mục nào hiện (01b-dieu-huong.js QUYEN_MAN / QUYEN_TAB).
  apDungQuyenMenu();
  refresh();
  startInboxStream();
  state.timer = setInterval(refresh, 6000);
});

/* Trung tâm kết nối native. Secret chỉ đi từ form tới vault; response không
   chứa credential nên DOM cũng không có gì để vô tình làm lộ. */
function moManKetNoi() {
  doiMan("cc-ket-noi");
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

function htmlToken(token) {
  return `<code class="token-hien">${esc(token)}</code>`
    + '<button type="button" class="btn btn--sm" data-copytoken>Chép</button>';
}

/* Verify token đã bấm xem của một kênh, nếu còn trong hạn một phút.
 *
 * Thẻ kênh dựng lại innerHTML mỗi 6 giây; trước đây chuỗi vừa hiện bị xoá
 * trước khi người ta kịp chép sang Meta — bấm "Xem" mà không thấy gì lâu
 * quá vài giây, tưởng nút hỏng. */
function oTokenDaHien(kenh) {
  const t = (state.tokenHien || {})[kenh];
  if (!t) return "";
  if (Date.now() > t.het) { delete state.tokenHien[kenh]; return ""; }
  return htmlToken(t.token);
}

/* Uỷ quyền: nút Chép nằm trong ô bị dựng lại mỗi vòng, gắn trực tiếp là
   mất listener sau 6 giây. */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copytoken]");
  if (!b) return;
  const chuoi = b.closest(".token-slot")?.querySelector(".token-hien")?.textContent || "";
  try {
    await navigator.clipboard.writeText(chuoi);
    toast("Đã chép. Dán vào ô \"Xác minh mã\" bên Meta.");
  } catch {
    // Trình duyệt chặn clipboard khi trang không chạy HTTPS —
    // chuỗi vẫn hiện trên màn hình nên người dùng bôi đen chép tay.
    toast("Không chép tự động được. Bôi đen chuỗi rồi chép tay.", true);
  }
});

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
          <div class="token-slot" data-tokenslot-kenh="${esc(channel)}">${oTokenDaHien(channel)}</div>` : ""}
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
          <div class="token-slot" data-tokenslot="${account.id}">${
            /* Kết quả Sức khoẻ phải SỐNG QUA vòng làm mới 6 giây: thẻ được
               dựng lại innerHTML mỗi vòng, ghi thẳng vào ô là mất sau vài
               giây và người bấm tưởng nút không làm gì. */
            (state.sucKhoeKenh || {})[account.id] || ""}</div>
          <div class="account-actions">
            ${account.channel === "zalo_personal" ? `<button class="btn btn--sm" data-qr="${account.id}">Quét QR</button>` : ""}
            ${["facebook", "instagram"].includes(account.channel) && account.status === "pending" ? `<button class="btn btn--sm" data-subwebhook="${account.id}">Nhận tin</button>` : ""}
            ${account.status !== "active" ? `<button class="btn btn--sm" data-verify="${account.id}">Xác minh provider</button>` : `<button class="btn btn--sm" data-disable="${account.id}">Tạm ngắt</button>`}
            <button class="btn btn--sm btn--ghost" data-health="${account.id}">Sức khoẻ</button>
            <button class="btn btn--sm btn--ghost" data-agentbat="${account.id}"
              data-bat="${account.agent_bat === false ? "1" : "0"}">${
              account.agent_bat === false ? "Bật agent" : "Tắt agent"}</button>
            ${hoSoAgent.ds.length ? `<select class="hsa-chon" data-hsagan="${account.id}"
              title="Hồ sơ agent trả lời kênh này" aria-label="Hồ sơ agent cho ${esc(account.display_name)}">
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
  $$('[data-health]').forEach((b) => b.addEventListener("click", () => kenhSucKhoe(b)));

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
      const d = await hoiHop({
        tieu_de: "Tắt agent cho kênh này",
        phu: "Tin khách vẫn vào và vẫn chuyển cho người — hệ thống tự tạo một công việc cho mỗi hội thoại.",
        truong: [{ name: "ly_do", label: "Lý do", hint: "hiện trên thẻ kênh và trong nhật ký",
                   placeholder: "Ví dụ: Trang không phải shop mỹ phẩm", maxlength: 300 }],
        nut: "Tắt agent", nguy_hiem: true,
      });
      if (!d) return;
      ly_do = d.ly_do || "";
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
      await hoiHop({
        tieu_de: `Không xoá được “${ten}”`,
        phu: `Còn ${truoc.dang_giu.join(", ")}. Lịch sử khách không bị xoá theo tài khoản — đó là bằng chứng của cửa hàng. Dùng “Tạm ngắt” để ngừng kênh mà vẫn giữ dữ liệu.`,
        nut: "Đã hiểu",
      });
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
    /* Ô của nút mức KÊNH là ô mức kênh, tìm theo thẻ chứa nút. Trước đây ô
       này mang `data-tokenslot` TRÙNG id với ô Sức khoẻ của Trang đầu tiên,
       nên hai thứ ghi đè lên nhau tuỳ cái nào đứng trước trong DOM. */
    const cho = button.dataset.verifytokenKenh
      ? button.closest(".channel-card")?.querySelector("[data-tokenslot-kenh]")
      : document.querySelector(`[data-tokenslot="${id}"]`);
    button.disabled = true;
    try {
      const r = await api(`/channel-accounts/${id}/verify-token`);
      const kenh = cho && cho.dataset.tokenslotKenh;
      if (kenh) {
        // Nhớ qua vòng làm mới 6 giây (thẻ dựng lại innerHTML) — nhưng chỉ
        // một phút: chuỗi bí mật không được nằm sẵn trên màn hình mãi.
        state.tokenHien = state.tokenHien || {};
        state.tokenHien[kenh] = { token: r.verify_token, het: Date.now() + 60000 };
        cho.innerHTML = oTokenDaHien(kenh);
      } else if (cho) {
        cho.innerHTML = htmlToken(r.verify_token);
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

  if (form.channel === "webchat") {
    /* Kênh web cần ĐỊA CHỈ WEBSITE được phép mở khung chat; form này không
     * có ô ấy, và kênh lưu thiếu nó bị máy chủ từ chối mọi phiên (403) —
     * khung chat hiện ra mà khách gõ gì cũng không vào (đo 19.11.2026). */
    toast('Kênh website nối bằng nút "Chat trên website" ở mục Nối kênh mới.', true);
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
    /* `/verify` trả 200 kèm `{ok:false}` khi provider từ chối — không ném
     * lỗi. Không đọc `ok` thì credential sai được báo XANH "xác minh xong":
     * xanh giả, lộ ra nhiều ngày sau khi khách nhắn mà không ai nhận. Cùng
     * cách đọc với nút "Xác minh provider" trên thẻ tài khoản. */
    const kq = await api(`/channel-accounts/${account.id}/verify`, { method: "POST" });
    toast(kq && kq.ok ? "Đã lưu và xác minh xong với provider."
                      : `Đã lưu, nhưng chưa xác minh được: ${lyDoKetNoi(kq || {})} — kiểm lại credential.`,
          !(kq && kq.ok));
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
  con_nguoi: "Con người",
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
    // `/knowledge` BẮT BUỘC account_id (gọi trơn là 422, mỗi lần mở tab Kỹ
    // năng — đo 23.11.2026). Gợi ý tên nhóm lấy từ kho DÙNG CHUNG mọi kênh.
    const ds = await api("/knowledge?account_id=00000000-0000-0000-0000-000000000000");
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
  // `aria-label`: nhãn của ô nằm ở cột trái cùng dòng, không phải <label>
  // bọc ô — trình đọc màn hình và bộ kiểm tự động thấy một ô không tên.
  if (m.kieu === "bool") {
    return `<label class="switch"><input type="checkbox" id="${id}" aria-label="${esc(m.nhan)}"
      data-ch="${m.khoa}" data-kieu="bool" ${m.gia_tri ? "checked" : ""}>
      <span>${m.gia_tri ? "đang bật" : "đang tắt"}</span></label>`;
  }
  if (m.kieu === "chon") {
    return `<select id="${id}" aria-label="${esc(m.nhan)}" data-ch="${m.khoa}" data-kieu="chon">${
      m.chon.map((c) => `<option value="${esc(c)}"${
        c === m.gia_tri ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  return `<input type="number" id="${id}" aria-label="${esc(m.nhan)}" data-ch="${m.khoa}" data-kieu="so"
    min="${m.min}" max="${m.max}" step="${m.buoc}" value="${m.gia_tri}">
    ${m.don_vi ? `<span class="row__sub">${esc(m.don_vi)}</span>` : ""}`;
}

/* `giuDangGo`: vòng làm mới 6 giây gọi hàm này với mặc định (giữ). Ô số
 * gửi đi ở sự kiện `change` — tức khi rời ô — nên giữa lúc gõ "0.7" và lúc
 * rời ô, một nhịp làm mới trả ô về giá trị cũ: người ta gõ xong, bấm ra
 * ngoài, và thứ được lưu là con số họ KHÔNG gõ.
 *
 * Sau khi lưu (hoặc lưu hỏng) thì gọi với `false`: lúc đó thứ phải hiện là
 * thứ máy chủ đang chạy, không phải thứ người ta vừa gõ mà bị từ chối. */
const KHOA_CO_KHOI_RIENG = new Set(["enabled", "mode"]);

async function loadCauHinh(giuDangGo = true) {
  const d = await api("/cau-hinh");
  const lech = d.muc.filter((m) => m.lech_mac_dinh).length;
  $("#c-cauhinh").textContent = lech ? `${lech} lệch` : "";

  const oGoc = $("#cauhinh-ds");
  const dangGo = giuDangGo ? _luuDangGo(oGoc) : null;
  /* Công tắc AI và chế độ Gợi ý/Tự động có khối riêng ngay trên (#aiTrangThai).
     Vẽ chúng ở đây nữa là hai công tắc cho cùng một cờ trên một màn. */
  oGoc.innerHTML = d.muc.filter((m) => !KHOA_CO_KHOI_RIENG.has(m.khoa)).map((m) => `<div class="row">
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
  if (dangGo) _traDangGo(oGoc, dangGo);

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
    await loadCauHinh(false);
  } catch (err) {
    toast(err.message, true);
    await loadCauHinh(false);
  }
});

$("#cauhinh-macdinh")?.addEventListener("click", async () => {
  if (!confirm("Quay về mặc định trong .env?\n\nMọi thiết lập đã lưu sẽ bị xoá."))
    return;
  try {
    await api("/cau-hinh/mac-dinh", { method: "POST" });
    toast("Đã quay về mặc định");
    await loadCauHinh(false);
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
  dung_bat_thuong: "halt",
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
        <span class="row__sub row__sub--truot">${ds.map((c) => `<button type="button" class="btn btn--sm" data-goiy="${esc(c.id)}"
            data-hoi="${esc(c.hoi)}" data-kyvong='${esc(JSON.stringify(c.ky_vong))}'>${esc(c.hoi)}</button>`).join(" ")}</span></span>
      </div>`).join("");
    // Khung chat trống trơn lúc mới mở trông như chưa tải xong. Vẽ ngay để
    // nó nói "chưa có lượt nào" thay vì im lặng.
    veChatPhongThu();
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
      <span class="row__body"><span class="row__title">${d.grounded ? "Có căn cứ" : "Thiếu căn cứ"} · điểm khớp ${d.confidence == null ? "—" : Number(d.confidence).toFixed(2)}</span>
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

/* Phiên thử sống trong RAM TIẾN TRÌNH (agent/core/phong_thu_phien.py), nên
 * nó biến mất mỗi lần máy chủ khởi động lại, và tự hết sau 2 giờ không dùng.
 * Tab đang mở thì vẫn giữ id cũ trong biến JS — gửi lên là 404.
 *
 * Trước bản này, 404 chỉ thành một toast "Phiên thử không tồn tại hoặc đã
 * hết hạn" rồi thôi: bấm Gửi lại cũng 404, mãi mãi, cho tới khi người dùng
 * đoán ra là phải bấm "Phiên mới" hoặc tải lại trang. Đo được trên máy chủ
 * thật 14.09.2026 — hai lần 404 liên tiếp cùng một tab, ngay sau khi tôi
 * bật lại máy chủ.
 *
 * Giờ tự mở phiên mới rồi gửi lại ĐÚNG MỘT LẦN. Phiên thử không mang dữ
 * liệu quý nên mở lại là vô hại — nhưng phải NÓI RA, vì lịch sử hội thoại
 * thử mất theo: agent không còn nhớ các lượt trước, và một màn hình vẫn
 * hiện lượt cũ trong khi agent đã quên là một màn hình nói dối.
 */
async function hoiPhongThu(cauHoi) {
  const q = (cauHoi || "").trim();
  if (!q) return;
  if (!state.phongThu.phien) await loadPhongThu();
  if (!state.phongThu.phien) {
    // Không có phiên mà vẫn gửi thì URL thành `/phien/null/hoi` — 404 với
    // một lý do khác hẳn lý do thật, và người đọc log sẽ đi tìm nhầm chỗ.
    toast("Chưa mở được phiên thử. Bấm “Phiên mới” hoặc tải lại trang.", true);
    return;
  }
  const body = { cau_hoi: q, ky_vong: phongThuKyVong };
  phongThuKyVong = null;
  const gui = () => api(
    `/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}/hoi`,
    { method: "POST", body: JSON.stringify(body) });
  try {
    let d;
    try {
      d = await gui();
    } catch (e) {
      if (e.ma !== 404) throw e;
      state.phongThu = { phien: null, luot: [] };
      state.phongThuDaTai = false;
      $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
      veChatPhongThu();
      await loadPhongThu();
      if (!state.phongThu.phien) throw e;     // mở phiên mới cũng hỏng: báo lỗi gốc
      toast("Phiên thử cũ đã hết (máy chủ khởi động lại hoặc để quá 2 giờ) — "
            + "đã mở phiên mới. Agent KHÔNG nhớ các lượt trước.");
      d = await gui();
    }
    state.phongThu.luot.push({ khach: q, agent: d.tra_loi, cost_usd: d.cost_usd, latency_ms: d.latency_ms,
      escalate: d.escalate, tone: d.luoi_bat ? (NHAN_LUOI_MAU[d.luoi_bat] || "assist") : "auto" });
    veChatPhongThu();
    veBenTrongPhongThu(d);
    await veNganSachPhongThu();
  } catch (e) { toast(e.message, true); }
}

/* Khoá nút trong lúc chờ model.
 *
 * Một lượt mất 3–7 giây, có ca đo được 100 giây. Không khoá thì người dùng
 * tưởng bấm hụt và bấm tiếp — mỗi lần là một lượt gọi model THẬT: tốn tiền
 * thật, và các câu trả lời về không đúng thứ tự làm khung chat nhảy loạn. */
$("#phongthu-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const o = f.querySelector("[name=cau_hoi]");
  const q = o.value;
  if (!q.trim()) return;
  const nut = f.querySelector("button[type=submit]");
  const chuCu = nut.textContent;
  nut.disabled = true;
  o.disabled = true;
  nut.textContent = "Đang hỏi…";
  o.value = "";
  try {
    await hoiPhongThu(q);
  } finally {
    nut.disabled = false;
    o.disabled = false;
    nut.textContent = chuCu;
    o.focus();
  }
});
// Xoá phiên trên máy chủ trước khi tạo hay bỏ hẳn — phiên bỏ đi thì trả
// RAM tiến trình ngay, không đợi dọn theo TTL 2 giờ (agent/core/phong_thu_phien.py).
async function xoaPhienPhongThuTrenMayChu() {
  if (!state.phongThu.phien) return;
  try {
    await api(`/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}`, { method: "DELETE" });
  } catch (e) {
    // 404 ở đây KHÔNG phải lỗi: phiên đã không còn trên máy chủ, mà đó đúng
    // là thứ đang muốn. Báo đỏ làm người dùng tưởng nút Phiên mới bị hỏng.
    if (e.ma !== 404) toast(e.message, true);
  }
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

const API_NHOM = { model: "Model ngôn ngữ", erp: "ERP (ERPNext)", van_chuyen: "Vận chuyển (GHN / GHTK)", thanh_toan: "Thanh toán (VietQR)", binh_luan: "Bình luận Facebook", csat: "Khảo sát hài lòng (CSAT)", bvdlcn: "Bảo vệ dữ liệu cá nhân", sla: "SLA — khi trễ hạn", media: "Media khách gửi — lưu trữ" };

/* Ô nhập cho một khoá. Ô BÍ MẬT là password và KHÔNG có value: giá trị
 * không có ở client để mà dựng — máy chủ chỉ gửi bốn ký tự cuối. */
function oNhapApi(m) {
  if (m.chon && m.chon.length) {
    return `<select data-api-khoa="${m.khoa}" aria-label="${esc(m.nhan || m.khoa)}">${
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

/* Mỗi nhóm khoá dựng vào ĐÚNG tab của nó (phiếu việc 20.11.2026): ô nào
 * mang `data-api-cac-nhom="erp,van_chuyen"` thì nhận đúng các nhóm ấy.
 * Model ở Cấu hình AI, SLA ở tab SLA, ERP/vận chuyển/bình luận ở Kết nối,
 * bảo vệ dữ liệu ở Hệ thống. `thanh_toan` (VietQR) và `csat` CỐ Ý không
 * có ô nào: chủ dự án ẩn hai tính năng này khỏi giao diện — mã và API giữ
 * nguyên, CSAT mặc định tắt (CSAT_BAT=tat). Ô nào cũng không nhận một
 * nhóm thì nhóm ấy đơn giản là không vẽ, không có cờ ẩn riêng để quên. */
async function loadCaiDatApi() {
  const cacO = $$("[data-api-cac-nhom]");
  if (!coQuyen("cau_hinh.doc")) {
    cacO.forEach((o) => { o.innerHTML = '<p class="empty">Cần quyền cau_hinh.doc để xem mục này.</p>'; });
    return;
  }
  const d = await api("/cai-dat-api");
  const vault = $("#api-vault");
  if (vault) vault.textContent = d.vault_san_sang ? "mã hoá AES-256 trong CSDL" : "vault chưa cấu hình — chỉ xem được";
  const nhom = {};
  for (const m of d.muc) (nhom[m.nhom] ||= []).push(m);
  /* Giữ khoá đang dán dở qua mỗi lần dựng lại.
   *
   * Hàm này nằm trong vòng làm mới 6 giây. Trước đây khoá API dán vào ô
   * password, URL, ô chọn LLM_PROVIDER đều bị xoá sau tối đa 6 giây; người
   * ta bấm Lưu và nhận toast XANH "Đã lưu 0 khoá" — xanh giả, vì không có
   * gì được lưu cả. Ô bí mật không có `value` từ máy chủ, nên bất kỳ chữ
   * nào trong đó đều là người dùng gõ — `_oDaSua` bắt đúng điều đó. */
  for (const oGoc of cacO) {
    const chi = oGoc.dataset.apiCacNhom.split(",").map((x) => x.trim());
    const dangGo = _luuDangGo(oGoc);
    oGoc.innerHTML = Object.entries(API_NHOM).filter(([ma]) => chi.includes(ma)).map(([ma, ten]) => `
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
    _traDangGo(oGoc, dangGo);
  }
  // Trả TRƯỚC hienODungProvider(): ô provider người ta vừa đổi quyết định
  // ô khoá nào hiện — làm ngược thì hiện ô khoá của provider cũ.
  hienODungProvider();
}

/* Provider nào cần khoá nào. gemini/vertex xác thực qua gcloud trên máy,
 * không có khoá nào để nhập — nên không có mục nào trong bảng này. */
const API_KHOA_THEO_PROVIDER = { gemini_api: "GEMINI_API_KEY", anthropic: "ANTHROPIC_API_KEY", openai: "OPENAI_API_KEY" };

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
function giaTriApiDangGo(ma, chiDaSua = false) {
  const ra = {};
  document.querySelectorAll(`[data-api-nhom="${ma}"] [data-api-khoa]`).forEach((o) => {
    /* Một ô đã ẩn là một ô người dùng không còn nhìn thấy — gửi giá trị của nó
     * đi là lưu thầm, có thể là khoá cũ từ trước khi đổi provider. Bỏ qua ô ẩn. */
    if (o.closest("[data-api-row]")?.hidden) return;
    /* Khi LƯU chỉ gửi ô người dùng đã đổi. Ô chọn provider và ô URL luôn có
     * sẵn giá trị máy chủ, nên gửi hết thì toast đếm "Đã lưu 1 khoá" cả khi
     * người ta chưa đổi gì — con số không nói thật điều gì đã được lưu. */
    if (chiDaSua && !_oDaSua(o)) return;
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
    const gia_tri = giaTriApiDangGo(ma, true);
    /* Không có gì để lưu thì NÓI RA, không toast xanh "Đã lưu 0 khoá" —
     * câu ấy đọc như thành công, và người ta đóng tab tin rằng khoá đã vào. */
    if (!Object.keys(gia_tri).length) {
      kq.textContent = "";
      toast("Chưa nhập khoá nào — dán khoá vào ô rồi bấm Lưu.", true);
      return;
    }
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
    // Ô bí mật của khoá ĐÃ lưu thì xoá chữ trước khi nạp lại: loadCaiDatApi
    // giữ mọi chữ đang gõ, và khoá đã lưu mà còn nằm trong ô thì trông như
    // chưa lưu. Khoá HỎNG thì để nguyên — người ta sửa tiếp chứ không dán lại.
    for (const khoa of da_luu) {
      const o = document.querySelector(`[data-api-nhom="${ma}"] input[type="password"][data-api-khoa="${khoa}"]`);
      if (o) o.value = "";
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

/* ---------------- Trả lời nhanh ---------------- */
/* Gõ "/" ở ĐẦU ô nhắn tin → khung gợi ý mẫu; ↑↓ chọn, Enter/Tab chèn, Esc đóng.
 *
 * Khung nằm NGOÀI #convdetail (gắn vào <body>): vòng làm mới 6 giây dựng lại
 * cả panel hội thoại, khung nằm trong đó thì cứ 6 giây biến mất một lần giữa
 * lúc người trực đang chọn. `ganMauNhanh` được gọi lại sau mỗi lần dựng nên
 * luôn bám đúng ô nhắn tin hiện tại. */
const mauNhanh = { ds: [], chon: 0, o: null, hen: null, lan: 0 };

function _khungMau() {
  let k = $("#mau-nhanh");
  if (!k) {
    k = document.createElement("div");
    k.id = "mau-nhanh";
    k.className = "mau-nhanh";
    k.setAttribute("role", "listbox");
    k.setAttribute("aria-label", "Mẫu trả lời nhanh");
    k.hidden = true;
    document.body.appendChild(k);
    // mousedown chứ không click: click tới SAU khi ô nhắn tin mất focus.
    k.addEventListener("mousedown", (ev) => {
      const d = ev.target.closest("[data-mau]");
      if (!d) return;
      ev.preventDefault();
      _chenMau(Number(d.dataset.mau));
    });
  }
  return k;
}

function _dongMau() {
  const k = $("#mau-nhanh");
  if (k) k.hidden = true;
  mauNhanh.ds = [];
}

function _veMau() {
  const k = _khungMau();
  const o = mauNhanh.o;
  if (!o || !document.body.contains(o) || !mauNhanh.ds.length) { _dongMau(); return; }
  k.innerHTML = mauNhanh.ds.map((m, i) => `
    <div class="mau-nhanh__dong${i === mauNhanh.chon ? " is-chon" : ""}" role="option"
         aria-selected="${i === mauNhanh.chon}" data-mau="${i}">
      <b>/${esc(m.ma_tat)}</b> <span>${esc(m.noi_dung)}</span>
    </div>`).join("");
  const r = o.getBoundingClientRect();
  k.style.left = `${Math.max(8, r.left)}px`;
  k.style.width = `${Math.min(r.width, window.innerWidth - 16)}px`;
  k.style.bottom = `${window.innerHeight - r.top + 6}px`;
  k.hidden = false;
}

function _chenMau(i) {
  const m = mauNhanh.ds[i];
  const o = mauNhanh.o;
  if (!m || !o) return;
  o.value = m.noi_dung;
  _dongMau();
  o.focus();
  o.setSelectionRange(o.value.length, o.value.length);
  // Báo cho trình giữ bản nháp biết chữ đã đổi.
  o.dispatchEvent(new Event("input", { bubbles: true }));
}

async function _timMau(q) {
  const lan = ++mauNhanh.lan;
  try {
    const r = await api(`/tra-loi-nhanh?q=${encodeURIComponent(q)}`);
    if (lan !== mauNhanh.lan) return;     // đã có lần gõ mới hơn
    mauNhanh.ds = r.mau.slice(0, 8);
    mauNhanh.chon = 0;
    _veMau();
  } catch { _dongMau(); }                  // thiếu quyền / lỗi mạng: im, không chặn gõ
}

function ganMauNhanh(o) {
  mauNhanh.o = o;
  if (mauNhanh.ds.length) _veMau();        // panel vừa dựng lại: bám ô mới
  o.addEventListener("input", () => {
    const v = o.value;
    const m = /^\/(\S{0,32})$/.exec(v);
    if (!m) { _dongMau(); return; }
    clearTimeout(mauNhanh.hen);
    mauNhanh.hen = setTimeout(() => _timMau(m[1]), 150);
  });
  o.addEventListener("keydown", (ev) => {
    const k = $("#mau-nhanh");
    if (!k || k.hidden || !mauNhanh.ds.length) return;
    if (ev.isComposing || ev.keyCode === 229) return;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      const n = mauNhanh.ds.length;
      mauNhanh.chon = (mauNhanh.chon + (ev.key === "ArrowDown" ? 1 : n - 1)) % n;
      _veMau();
    } else if (ev.key === "Enter" || ev.key === "Tab") {
      ev.preventDefault();
      ev.stopImmediatePropagation();       // không để Enter thành "Gửi"
      _chenMau(mauNhanh.chon);
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      _dongMau();
    }
  });
  // Chỉ đóng khi người dùng THẬT SỰ rời ô nhắn tin. Vòng làm mới 6 giây vứt
  // ô cũ (nó nhận `blur`) rồi trả focus cho ô mới — đóng vô điều kiện là
  // khung tự biến mất mỗi 6 giây giữa lúc đang chọn (đo được trên bản xem
  // trước 14.10.2026).
  o.addEventListener("blur", () => setTimeout(() => {
    if (document.activeElement !== mauNhanh.o) _dongMau();
  }, 120));
}

async function loadMauNhanh() {
  const ds = $("#mauNhanhDs");
  if (!ds) return;
  const sua = state.toiQuyen && state.toiQuyen.has("tra_loi_nhanh.sua");
  $("#mauNhanhForm").hidden = !sua;
  const r = await api("/tra-loi-nhanh");
  ds.innerHTML = r.mau.length ? r.mau.map((m) => `
    <div class="row">
      <span class="row__flag row__flag--plain"></span>
      <span class="row__body"><span class="row__title">/${esc(m.ma_tat)}</span>
        <span class="row__sub">${esc(m.noi_dung)}</span></span>
      ${sua ? `<span class="row__side">
        <button type="button" class="btn btn--sm" data-mau-sua="${esc(m.id)}">Sửa</button>
        <button type="button" class="btn btn--sm btn--halt" data-mau-xoa="${esc(m.id)}">Xoá</button>
      </span>` : ""}
    </div>`).join("")
    : '<p class="empty">Chưa có mẫu nào.</p>';
  ds.querySelectorAll("[data-mau-sua]").forEach((b) => b.addEventListener("click", () => {
    const m = r.mau.find((x) => x.id === b.dataset.mauSua);
    const f = $("#mauNhanhForm");
    f.mau_id.value = m.id; f.ma_tat.value = m.ma_tat; f.noi_dung.value = m.noi_dung;
    f.ma_tat.focus();
  }));
  ds.querySelectorAll("[data-mau-xoa]").forEach((b) => b.addEventListener("click", async () => {
    try {
      await api(`/tra-loi-nhanh/${b.dataset.mauXoa}`, { method: "DELETE" });
      toast("Đã xoá mẫu.");
      loadMauNhanh();
    } catch (e) { toast(e.message, true); }
  }));
}

$("#mauNhanhForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const id = f.mau_id.value;
  const body = JSON.stringify({ ma_tat: f.ma_tat.value.trim().toLowerCase(),
                                noi_dung: f.noi_dung.value });
  try {
    await api(id ? `/tra-loi-nhanh/${id}` : "/tra-loi-nhanh",
              { method: id ? "PUT" : "POST", body });
    toast("Đã lưu mẫu.");
    f.reset(); f.mau_id.value = "";
    loadMauNhanh();
  } catch (e) { toast(e.message, true); }   // 422 cụm cấm: giữ chữ để sửa
});
$("#mauNhanhHuy")?.addEventListener("click", () => {
  const f = $("#mauNhanhForm");
  f.reset(); f.mau_id.value = "";
});

/* ---------------- Nhãn, ghi chú, tìm hội thoại ---------------- */
/* Nhãn mô tả MỘT VỤ VIỆC ("chờ hàng về"), khác nhãn của khách ở Customer
 * 360. Thêm nhãn và ghi chú bằng hộp hỏi (`hoiHop`) chứ không bằng ô trong
 * panel: vòng làm mới 6 giây dựng lại cả panel, chữ đang gõ trong đó sẽ mất. */

/* Lọc theo ID nhãn (0056): đổi tên nhãn không làm gãy bộ lọc đang chọn. */
function veLocNhan(ds) {
  const k = $("#nhanfilter");
  if (!k) return;
  k.hidden = !ds.length && !state.convNhan;
  k.innerHTML = ds.map((n) => `<button type="button" class="chip ${state.convNhan === n.id ? "is-on" : ""}"
    data-loc-nhan="${esc(n.id)}">${chipNhan(n)} <span class="chip__so">${n.so}</span></button>`).join("");
}

$("#nhanfilter")?.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-loc-nhan]");
  if (!b) return;
  state.convNhan = state.convNhan === b.dataset.locNhan ? "" : b.dataset.locNhan;
  loadConversations();
});

$("#convtim")?.addEventListener("input", (ev) => {
  clearTimeout(state.henTim);
  state.henTim = setTimeout(() => {
    const q = ev.target.value.trim();
    state.convTim = q.length >= 2 ? q : "";
    loadConversations();
  }, 300);
});

// Gắn/gỡ NHÃN hội thoại: chọn từ danh mục — xem 21-nhan.js. Ghi chú nội bộ
// là một kiểu soạn trong ô soạn tin — xem 03b-thanh-hoi-thoai.js.

/* ---------------- Hiệu suất nhân viên ---------------- */
function _ngayVN(d) {
  // YYYY-MM-DD theo giờ máy người xem — dashboard dùng ở VN.
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
  return z.toISOString().slice(0, 10);
}

function _giay(g) {
  if (g == null) return "—";
  if (g < 60) return `${Math.round(g)} giây`;
  if (g < 3600) return `${Math.round(g / 60)} phút`;
  return `${(g / 3600).toFixed(1)} giờ`;
}

/* Bảng hiệu suất nhân viên giờ dựng ở màn Phân tích (19-phan-tich.js),
   thu hẹp theo bộ lọc chung; hai hàm trên là tiện ích dùng chung. */

/* ---------------- VietQR ---------------- */
/* Ủy quyền một trình nghe ở document: danh sách đơn dựng lại mỗi lần làm
 * mới, gắn vào từng nút là gắn lại mãi. */
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-oqr-gui]");
  if (!b) return;
  b.disabled = true;
  try {
    const r = await api(`/orders/${b.dataset.oqrGui}/vietqr/gui`, { method: "POST" });
    toast(r.duplicate ? "Mã QR này đã gửi trước đó." : "Đã xếp hàng gửi mã QR cho khách.");
  } catch (e) { toast(e.message, true); }
  finally { b.disabled = false; }
});

/* ---------------- Đã giải quyết ---------------- */
document.addEventListener("click", async (ev) => {
  if (!ev.target.closest("#btn-giai-quyet") || !state.openConv) return;
  state.moHanhDong = null;   // nút có thể nằm trong menu "⋯" — đóng nó lại
  try {
    const r = await api(`/inbox/conversations/${state.openConv}/giai-quyet`, { method: "POST" });
    toast(r.da_truoc ? "Hội thoại đã được giải quyết từ trước."
      : `Đã giải quyết${r.csat === "đã hỏi" ? " — đã hỏi khách chấm điểm" : ""}.`);
    loadConversations();
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Bảo mật hai bước (TOTP) ---------------- */
/* Bật là HAI bước: quét QR, rồi gõ một mã thật — bật ngay khi sinh bí mật
 * là khoá người dùng ra ngoài nếu họ quét hỏng. Mã dự phòng chỉ hiện MỘT
 * lần, ngay sau khi bật. */
document.addEventListener("click", async (ev) => {
  if (!ev.target.closest("#haibuoc")) return;
  ev.preventDefault();
  try {
    const tt = await api("/toi/hai-buoc");
    if (tt.bat) {
      const d = await hoiHop({
        tieu_de: "Tắt xác thực hai bước",
        phu: `Đang bật · còn ${tt.ma_du_phong_con} mã dự phòng. Tắt thì chỉ còn mật khẩu bảo vệ tài khoản.`,
        truong: [{ name: "mat_khau", label: "Gõ lại mật khẩu", type: "password", required: true }],
        nut: "Tắt", nguy_hiem: true,
      });
      if (!d || !d.mat_khau) return;
      await api("/toi/hai-buoc/tat", { method: "POST", body: JSON.stringify({ mat_khau: d.mat_khau }) });
      toast("Đã tắt xác thực hai bước.");
      return;
    }
    // Máy chủ đòi gõ lại mật khẩu trước khi sinh bí mật: phiên bị chiếm
    // không được tự gắn điện thoại của kẻ khác vào tài khoản.
    const xn = await hoiHop({
      tieu_de: "Bật xác thực hai bước",
      phu: "Gõ lại mật khẩu để tiếp tục.",
      truong: [{ name: "mat_khau", label: "Mật khẩu", type: "password", required: true }],
      nut: "Tiếp",
    });
    if (!xn || !xn.mat_khau) return;
    const moi = await api("/toi/hai-buoc/bat-dau", {
      method: "POST", body: JSON.stringify({ mat_khau: xn.mat_khau }),
    });
    const cho = hoiHop({
      tieu_de: "Bật xác thực hai bước",
      phu: "Quét mã bằng Google Authenticator, Authy hoặc 1Password, rồi nhập mã 6 số đang hiện.",
      truong: [{ name: "ma", label: "Mã 6 số", required: true, maxlength: 6 }],
      nut: "Bật",
    });
    // Ảnh QR do MÁY CHỦ vẽ (segno) — chèn vào phần mô tả của hộp hỏi.
    const phu = $("#hoiPhu");
    phu.innerHTML = `${esc(phu.textContent)}<span class="qr-2fa">${moi.svg}</span>`
      + `<small>Không quét được: nhập tay khoá trong <code>${esc(moi.uri.split("secret=")[1]?.split("&")[0] || "")}</code></small>`;
    const d = await cho;
    if (!d || !d.ma) return;
    const r = await api("/toi/hai-buoc/xac-nhan", { method: "POST", body: JSON.stringify({ ma: d.ma }) });
    await hoiHop({
      tieu_de: "Đã bật — lưu mã dự phòng",
      phu: "Mỗi mã dùng MỘT lần khi mất điện thoại. Lưu ở nơi an toàn; trang này sẽ không hiện lại.\n\n"
        + r.ma_du_phong.join("   "),
      truong: [], nut: "Đã lưu",
    });
  } catch (e) { toast(e.message, true); }
});
/* ---------------- Quy tắc tự động ---------------- */
/* Khi khách nhắn → nếu thoả điều kiện → làm hành động. Máy chủ kiểm lại
 * MỌI thứ (danh sách đóng, mẫu tồn tại, mẫu sạch cụm cấm); ở đây chỉ dựng
 * biểu mẫu cho dễ điền. Biểu mẫu là phần HTML tĩnh, không dựng lại theo vòng
 * làm mới — chữ đang gõ không mất. */

const TEN_KENH = {
  zalo_personal: "Zalo cá nhân", zalo_oa: "Zalo OA", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp", webchat: "Chat web",
};
// Tin đi qua hệ thống trung gian cũ mang tên kênh CŨ, không phải "facebook":
// giấu chúng đi là cửa hàng nhận FB/IG qua trung gian đặt quy tắc "kênh
// Facebook" mà không bao giờ khớp (rà soát 28.10.2026).
TEN_KENH.chatwoot = "Qua kênh trung gian cũ (FB/IG/web)";
TEN_KENH.zalocrm = "Qua hệ thống Zalo cũ";
TEN_KENH.messenger = "Messenger (cũ)";
const KENH_HIEN = Object.keys(TEN_KENH);

function _moTaQuyTac(q) {
  const dk = q.dieu_kien || {};
  const neu = [];
  if (dk.kenh) neu.push("kênh " + dk.kenh.map((k) => TEN_KENH[k] || k).join("/"));
  if (dk.chua_tu) neu.push("có từ «" + dk.chua_tu.join("», «") + "»");
  if (dk.ngoai_gio === true) neu.push("ngoài giờ");
  if (dk.ngoai_gio === false) neu.push("trong giờ");
  if (dk.lan_dau === true) neu.push("tin đầu tiên");
  if (dk.lan_dau === false) neu.push("không phải tin đầu");
  // Nhãn theo id (0056) — đọc tên qua `tenNhanTheoId` (21-nhan.js). Khoá
  // chữ cũ còn sót thì vẫn hiện chữ.
  const ten = (ds) => (ds || []).map(tenNhanTheoId).join(" / ");
  if (dk.nhan_hoi_thoai_co) neu.push("hội thoại có nhãn " + ten(dk.nhan_hoi_thoai_co));
  if (dk.nhan_hoi_thoai_khong) neu.push("hội thoại chưa có nhãn " + ten(dk.nhan_hoi_thoai_khong));
  if (dk.nhan_khach_co) neu.push("khách có nhãn " + ten(dk.nhan_khach_co));
  if (dk.nhan_khach_khong) neu.push("khách chưa có nhãn " + ten(dk.nhan_khach_khong));
  if (dk.nhan_co) neu.push("có nhãn " + dk.nhan_co);
  if (dk.nhan_khong) neu.push("chưa có nhãn " + dk.nhan_khong);
  const thi = (q.hanh_dong || []).map((h) => ({
    gan_nhan: "gắn nhãn " + h.nhan,
    gan_nhan_hoi_thoai: "gắn nhãn hội thoại " + tenNhanTheoId(h.nhan_id),
    gan_nhan_khach: "gắn nhãn khách " + tenNhanTheoId(h.nhan_id),
    gui_mau: "gửi mẫu /" + h.ma_tat,
    tao_viec: "tạo việc «" + h.tieu_de + "»" + (h.giao_tu_dong ? " (tự phân công)" : ""),
    chuyen_nguoi: "chuyển cho nhân viên",
  }[h.loai] || h.loai));
  return `Nếu ${neu.length ? neu.join(" và ") : "có tin bất kỳ"} → ${thi.join(", ")}`;
}

// Tóm tắt MỘT lần chạy: làm gì, bỏ qua gì và vì sao, hỏng gì. "Bỏ qua" phải
// nói lý do — "không gửi mẫu vì quy tắc X đã gửi" là câu trả lời cho câu hỏi
// người vận hành sẽ hỏi đầu tiên: "sao quy tắc của tôi không gửi?".
function _tomTatLanChay(ketQua, ct) {
  ct = ct || {};
  const lam = (ct.lam || []).join(", ");
  const boQua = (ct.bo_qua || []).join("; ");
  if (ketQua === "hong") return "hỏng: " + (ct.loi || "?");
  if (ketQua === "bo_qua") return "khớp nhưng bỏ qua — " + (boQua || "đã làm ở tin trước");
  let s = lam;
  if (ct.ai_nhuong) s += " · AI nhường tin này";
  if (boQua) s += " · bỏ qua: " + boQua;
  if (ct.loi) s += " · lỗi: " + ct.loi;
  if (ct.dung_xet_sau) s += " · dừng xét quy tắc sau";
  return s;
}

async function loadQuyTac() {
  const ds = $("#qtDs");
  if (!ds) return;
  // Thiếu quyền đọc thì ẩn cả khung; lỗi thì báo nhưng KHÔNG ném — ném ra là
  // các khung đứng sau trong trang Cấu hình không tải nữa.
  const doc = state.toiQuyen && state.toiQuyen.has("dinh_tuyen.doc");
  ds.closest(".panel").hidden = !doc;
  if (!doc) return;
  const sua = state.toiQuyen.has("dinh_tuyen.sua");
  $("#qtForm").hidden = !sua;
  let r;
  try { r = await api("/tu-dong"); } catch (e) { toast(e.message, true); return; }
  state.quyTac = r.quy_tac;
  await napONhanQuyTac();
  const kenh = (r.kenh || []).filter((k) => KENH_HIEN.includes(k));
  const o = $("#qtKenh");
  if (o && !o.children.length) {
    o.innerHTML = kenh.map((k) => `<label><input type="checkbox" data-qt-kenh value="${esc(k)}"> ${
      esc(TEN_KENH[k] || k)}</label>`).join("");
  }
  // Gợi ý mã tắt từ mẫu trả lời nhanh. Không đọc được (thiếu quyền) thì ô
  // vẫn gõ tay được — máy chủ vẫn chặn mã không tồn tại lúc lưu.
  // Trang Cấu hình làm mới 6 giây một lần: chỉ thay khi nội dung đổi, không
  // thì danh sách gợi ý đang mở dưới ô nhập bị đóng giữa chừng.
  api("/tra-loi-nhanh").then((m) => {
    const html = m.mau.map((x) =>
      `<option value="${esc(x.ma_tat)}">${esc(x.noi_dung.slice(0, 60))}</option>`).join("");
    const dl = $("#qtMauDs");
    if (dl && dl.innerHTML !== html) dl.innerHTML = html;
  }).catch(() => {});

  ds.innerHTML = r.quy_tac.length ? r.quy_tac.map((q) => {
    const b = q.bay_ngay || {};
    // Bật mà bảy ngày chưa khớp lần nào là điều đáng nói ra: trông y hệt
    // "đang chạy tốt", nhưng có thể điều kiện viết sai.
    const tinh = b.hong ? `<span class="pill pill--halt">${b.hong} lần hỏng</span> ` : "";
    const lan = b.da_lam ? `${b.da_lam} lần làm trong 7 ngày` + (b.lan_cuoi ? `, gần nhất ${clock(b.lan_cuoi)}` : "")
      : (q.bat ? "chưa khớp lần nào trong 7 ngày" : "");
    const co = [q.dung_xet_sau ? "dừng xét quy tắc sau" : "",
                q.cho_ai_tra_loi ? "AI vẫn trả lời sau mẫu" : ""].filter(Boolean);
    const c = q.lan_chay_cuoi;
    const cuoi = c ? `Lần chạy cuối ${clock(c.luc)}: ${c.tom_tat}` : "";
    // Lỗi cuối hiện NGAY trên dòng quy tắc, không chỉ trong nhật ký chung:
    // nhật ký chung trôi đi sau 20 lần chạy, lỗi thì vẫn còn đó. Nhưng lỗi
    // ĐÃ SỬA (quy tắc được lưu lại sau lỗi) hay quá bảy ngày thì thôi hiện —
    // một dòng đỏ mãi là dòng người ta thôi đọc.
    const loiCon = q.loi_cuoi && Date.parse(q.loi_cuoi.luc) > Date.parse(q.sua_luc)
      && Date.now() - Date.parse(q.loi_cuoi.luc) < 7 * 864e5;
    const loi = loiCon ? `<span class="row__sub"><span class="pill pill--halt">Lỗi gần nhất ${
      esc(clock(q.loi_cuoi.luc))}</span> ${esc(q.loi_cuoi.loi)}</span>` : "";
    return `
    <div class="row">
      <span class="row__flag ${!q.bat ? "row__flag--plain" : b.hong ? "row__flag--halt" : "row__flag--auto"}"></span>
      <span class="row__body"><span class="row__title">Ưu tiên ${esc(q.thu_tu)} · ${esc(q.ten)}${q.bat ? "" : " <em>(đang tắt)</em>"}${
        co.length ? ` <span class="pill">${esc(co.join(" · "))}</span>` : ""}</span>
        <span class="row__sub">${esc(_moTaQuyTac(q))}</span>
        <span class="row__sub">${tinh}${esc(lan)}</span>
        ${cuoi ? `<span class="row__sub">${esc(cuoi)}</span>` : ""}${loi}</span>
      <span class="row__side">
        <button type="button" class="btn btn--sm btn--ghost" data-qt-nhatky="${esc(q.id)}">Nhật ký</button>
      ${sua ? `
        <button type="button" class="btn btn--sm" data-qt-bat="${esc(q.id)}">${q.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm" data-qt-sua="${esc(q.id)}">Sửa</button>
        <button type="button" class="btn btn--sm btn--halt" data-qt-xoa="${esc(q.id)}">Xoá</button>` : ""}
      </span>
    </div>`;
  }).join("") : '<p class="empty">Chưa có quy tắc nào — agent và định tuyến chạy như thường.</p>';
  await loadQuyTacLanChay();
}

async function loadQuyTacLanChay() {
  const o = $("#qtLanChay");
  if (!o) return;
  // Lọc theo một quy tắc (nút "Nhật ký" trên dòng quy tắc). Quy tắc đã bị
  // xoá thì bỏ lọc — không để khung trống mà không nói vì sao.
  const loc = (state.quyTac || []).find((q) => q.id === state.qtLoc);
  if (!loc) state.qtLoc = null;
  const tieuDe = $("#qtLanChayTieuDe");
  if (tieuDe) {
    tieuDe.innerHTML = loc ? `Lần chạy gần đây — «${esc(loc.ten)}» <button type="button" class="btn btn--sm btn--ghost" data-qt-nhatky="">Xem tất cả</button>`
      : "Lần chạy gần đây";
  }
  let r;
  try {
    r = await api("/tu-dong/lan-chay?gioi_han=20" + (loc ? `&quy_tac_id=${encodeURIComponent(loc.id)}` : ""));
  } catch (e) { toast(e.message, true); return; }
  o.innerHTML = r.lan_chay.length ? r.lan_chay.map((l) => {
    const viec = _tomTatLanChay(l.ket_qua, l.chi_tiet);
    return `<div class="row">
      <span class="row__flag ${l.ket_qua === "hong" ? "row__flag--halt" : l.ket_qua === "da_lam" ? "row__flag--auto" : "row__flag--plain"}"></span>
      <span class="row__body"><span class="row__title">${esc(l.quy_tac)}</span>
        <span class="row__sub">${esc(viec)}</span></span>
      <span class="row__side">${esc(clock(l.luc))}</span>
    </div>`;
  }).join("") : '<p class="empty">Chưa quy tắc nào chạy.</p>';
}

function _gomQuyTac(f) {
  const dk = {};
  const kenh = $$("[data-qt-kenh]:checked").map((c) => c.value);
  if (kenh.length) dk.kenh = kenh;
  const tu = f.chua_tu.value.split(",").map((x) => x.trim()).filter(Boolean);
  if (tu.length) dk.chua_tu = tu;
  if (f.ngoai_gio.value) dk.ngoai_gio = f.ngoai_gio.value === "true";
  if (f.lan_dau.value) dk.lan_dau = f.lan_dau.value === "true";
  for (const k of ["nhan_hoi_thoai_co", "nhan_hoi_thoai_khong", "nhan_khach_co", "nhan_khach_khong"]) {
    if (f[k].value) dk[k] = [f[k].value];
  }
  const hd = [];
  if (f.hd_gan_nhan_hoi_thoai.value) hd.push({ loai: "gan_nhan_hoi_thoai", nhan_id: f.hd_gan_nhan_hoi_thoai.value });
  if (f.hd_gan_nhan_khach.value) hd.push({ loai: "gan_nhan_khach", nhan_id: f.hd_gan_nhan_khach.value });
  if (f.hd_gui_mau.value.trim()) hd.push({ loai: "gui_mau", ma_tat: f.hd_gui_mau.value.trim().replace(/^\//, "") });
  if (f.hd_tao_viec.value.trim()) {
    hd.push({ loai: "tao_viec", tieu_de: f.hd_tao_viec.value.trim(),
              ...(f.hd_tao_viec_tu_giao && f.hd_tao_viec_tu_giao.checked ? { giao_tu_dong: true } : {}) });
  }
  if (f.hd_chuyen_nguoi.value.trim()) hd.push({ loai: "chuyen_nguoi", ly_do: f.hd_chuyen_nguoi.value.trim() });
  return {
    ten: f.ten.value.trim(), su_kien: "tin_khach", dieu_kien: dk, hanh_dong: hd,
    bat: f.bat.checked, thu_tu: Number(f.thu_tu.value || 100),
    dung_xet_sau: f.dung_xet_sau.checked, cho_ai_tra_loi: f.cho_ai_tra_loi.checked,
  };
}

function _datQuyTac(f, q) {
  const dk = q.dieu_kien || {};
  f.qt_id.value = q.id; f.ten.value = q.ten; f.thu_tu.value = q.thu_tu; f.bat.checked = q.bat;
  f.dung_xet_sau.checked = !!q.dung_xet_sau; f.cho_ai_tra_loi.checked = !!q.cho_ai_tra_loi;
  $$("[data-qt-kenh]").forEach((c) => { c.checked = (dk.kenh || []).includes(c.value); });
  f.chua_tu.value = (dk.chua_tu || []).join(", ");
  f.ngoai_gio.value = dk.ngoai_gio == null ? "" : String(dk.ngoai_gio);
  f.lan_dau.value = dk.lan_dau == null ? "" : String(dk.lan_dau);
  for (const k of ["nhan_hoi_thoai_co", "nhan_hoi_thoai_khong", "nhan_khach_co", "nhan_khach_khong"]) {
    _datONhan(f[k], (dk[k] || [])[0] || "");
  }
  const lay = (loai, k) => ((q.hanh_dong || []).find((h) => h.loai === loai) || {})[k] || "";
  _datONhan(f.hd_gan_nhan_hoi_thoai, lay("gan_nhan_hoi_thoai", "nhan_id"));
  _datONhan(f.hd_gan_nhan_khach, lay("gan_nhan_khach", "nhan_id"));
  f.hd_gui_mau.value = lay("gui_mau", "ma_tat");
  f.hd_tao_viec.value = lay("tao_viec", "tieu_de");
  if (f.hd_tao_viec_tu_giao) f.hd_tao_viec_tu_giao.checked = !!lay("tao_viec", "giao_tu_dong");
  f.hd_chuyen_nguoi.value = lay("chuyen_nguoi", "ly_do");
}

function _xoaFormQuyTac() {
  const f = $("#qtForm");
  if (!f) return;
  f.reset(); f.qt_id.value = "";
  $$("[data-qt-kenh]").forEach((c) => { c.checked = false; });
}

// "Nhật ký" lọc khung lần chạy theo một quy tắc; "Xem tất cả" bỏ lọc. Gắn
// vào khung CHA vì nút "Xem tất cả" nằm ngoài #qtDs.
$("#cc-tu-dong")?.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-qt-nhatky]");
  if (!b) return;
  state.qtLoc = b.dataset.qtNhatky || null;
  loadQuyTacLanChay();
  if (state.qtLoc) $("#qtLanChay")?.scrollIntoView({ block: "nearest" });
});

$("#qtDs")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-qt-sua], [data-qt-xoa], [data-qt-bat]");
  if (!b) return;
  const id = b.dataset.qtSua || b.dataset.qtXoa || b.dataset.qtBat;
  const q = (state.quyTac || []).find((x) => x.id === id);
  if (!q) return;
  try {
    if (b.dataset.qtSua) {
      _datQuyTac($("#qtForm"), q);
      $("#qtForm").ten.focus();
      return;
    }
    if (b.dataset.qtXoa) {
      const ok = await hoiHop({ tieu_de: `Xoá quy tắc «${q.ten}»?`,
        phu: "Nhật ký lần chạy của quy tắc cũng bị xoá. Muốn dừng tạm thì bấm Tắt.",
        nut: "Xoá", nguy_hiem: true });
      if (!ok) return;
      await api(`/tu-dong/${id}`, { method: "DELETE" });
      toast("Đã xoá quy tắc.");
    } else {
      await api(`/tu-dong/${id}`, { method: "PUT", body: JSON.stringify({
        ten: q.ten, su_kien: q.su_kien, dieu_kien: q.dieu_kien, hanh_dong: q.hanh_dong,
        bat: !q.bat, thu_tu: q.thu_tu,
        dung_xet_sau: q.dung_xet_sau, cho_ai_tra_loi: q.cho_ai_tra_loi }) });
      toast(q.bat ? "Đã tắt quy tắc." : "Đã bật quy tắc.");
    }
    loadQuyTac();
  } catch (e) { toast(e.message, true); }
});

$("#qtForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const body = _gomQuyTac(f);
  if (!body.hanh_dong.length) { toast("Điền ít nhất một ô ở phần «Thì».", true); return; }
  const id = f.qt_id.value;
  try {
    await api(id ? `/tu-dong/${id}` : "/tu-dong",
              { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
    toast("Đã lưu quy tắc.");
    _xoaFormQuyTac();
    loadQuyTac();
  } catch (e) { toast(e.message, true); }   // 422: giữ chữ để sửa
});
$("#qtHuy")?.addEventListener("click", _xoaFormQuyTac);
/* ---------------- Lịch ca trực ---------------- */
/* Ai đang trong ca là câu hỏi của MÁY CHỦ (hàm SQL dang_trong_ca) — ở đây
 * chỉ hiện. Tính lại bằng JS là hai bản sự thật, và sớm muộn màn hình nói
 * "đang trong ca" trong khi bộ định tuyến bỏ qua người đó. */

const THU = ["", "Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"];

function _tomTatCa(ca) {
  if (!ca.length) return "chưa xếp ca — luôn được giao hội thoại";
  const theo = {};
  ca.forEach((c) => { (theo[c.thu] = theo[c.thu] || []).push(`${c.bat_dau}–${c.ket_thuc}`); });
  return Object.keys(theo).map((t) => `${THU[t]} ${theo[t].join(", ")}`).join(" · ");
}

async function loadCaCuaToi() {
  const o = $("#caCuaToi");
  if (!o) return;
  let r;
  try { r = await api("/lich-ca/cua-toi"); } catch { o.hidden = true; return; }
  // Chưa xếp ca và không nghỉ: luôn trực, không có gì để nói.
  if (!r.ca.length && !r.nghi.length) { o.hidden = true; return; }
  o.hidden = false;
  o.classList.toggle("is-ngoai", !r.trong_ca);
  o.textContent = (r.trong_ca ? "Bạn đang trong ca. "
    : "Bạn đang NGOÀI ca — bộ định tuyến không giao hội thoại mới cho bạn lúc này. ")
    + "Lịch: " + _tomTatCa(r.ca)
    + (r.nghi.length ? ` · nghỉ từ ${new Date(r.nghi[0].tu_luc).toLocaleString("vi-VN")}` : "");
}

async function loadLichCa() {
  const pn = $("#lcPanel");
  if (!pn) return;
  const doc = state.toiQuyen && state.toiQuyen.has("dinh_tuyen.doc");
  pn.hidden = !doc;
  if (!doc) return;
  const sua = state.toiQuyen.has("dinh_tuyen.sua");
  let r;
  try { r = await api("/lich-ca"); } catch (e) { toast(e.message, true); return; }
  state.lichCa = r;
  $("#lcCanhBao").innerHTML = r.canh_bao.map((c) => `
    <div class="row"><span class="row__flag row__flag--halt"></span>
      <span class="row__body"><span class="row__title">${esc(c.ghi)}</span>
        <span class="row__sub">Xếp thêm người vào ca, hoặc tạm tắt luật định tuyến của đội ở Cấu hình chung → Điều phối hội thoại.</span></span>
    </div>`).join("");
  $("#lcNguoi").innerHTML = r.nguoi.length ? r.nguoi.map((n) => {
    const tt = n.dang_nghi ? "đang nghỉ" : !n.ca.length ? "luôn trực" : n.trong_ca ? "đang trong ca" : "ngoài ca";
    const co = n.dang_nghi || (n.ca.length && !n.trong_ca) ? "row__flag--plain" : "row__flag--auto";
    return `<div class="row">
      <span class="row__flag ${co}"></span>
      <span class="row__body"><span class="row__title">${esc(n.ten)} <em>· ${esc(tt)}</em></span>
        <span class="row__sub">${esc(_tomTatCa(n.ca))}</span></span>
      ${sua ? `<span class="row__side">
        <button type="button" class="btn btn--sm" data-lc-ca="${esc(n.id)}">Xếp ca</button>
        <button type="button" class="btn btn--sm" data-lc-nghi="${esc(n.id)}">Thêm nghỉ</button>
      </span>` : ""}
    </div>`;
  }).join("") : '<p class="empty">Chưa có nhân viên.</p>';
  const ten = Object.fromEntries(r.nguoi.map((n) => [n.id, n.ten]));
  $("#lcNghi").innerHTML = r.nghi.length ? r.nghi.map((n) => `
    <div class="row"><span class="row__flag row__flag--plain"></span>
      <span class="row__body"><span class="row__title">${esc(ten[n.nguoi_dung_id] || "?")}</span>
        <span class="row__sub">${esc(new Date(n.tu_luc).toLocaleString("vi-VN"))} → ${
          esc(new Date(n.den_luc).toLocaleString("vi-VN"))}${n.ly_do ? " · " + esc(n.ly_do) : ""}</span></span>
      ${sua ? `<span class="row__side"><button type="button" class="btn btn--sm btn--halt" data-lc-xoa-nghi="${esc(n.id)}">Xoá</button></span>` : ""}
    </div>`).join("") : '<p class="empty">Không ai nghỉ sắp tới.</p>';
}

/* "08:00-14:00, 18:00-22:00" → [{bat_dau, ket_thuc}]. Gõ sai thì báo, không
 * đoán: "8-14" có thể là 8:00–14:00, cũng có thể là gõ dở. */
function _docKhoang(chu, thu) {
  return chu.split(",").map((x) => x.trim()).filter(Boolean).map((x) => {
    const m = x.match(/^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$/);
    if (!m) throw new Error(`${THU[thu]}: «${x}» phải dạng 08:00-14:00`);
    return { thu, bat_dau: m[1], ket_thuc: m[2] };
  });
}

$("#lcNguoi")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-lc-ca], [data-lc-nghi]");
  if (!b) return;
  const n = (state.lichCa?.nguoi || []).find((x) => x.id === (b.dataset.lcCa || b.dataset.lcNghi));
  if (!n) return;
  try {
    if (b.dataset.lcCa) {
      const d = await hoiHop({
        tieu_de: `Xếp ca hằng tuần cho ${n.ten}`,
        phu: "Mỗi ngày một hoặc vài khoảng, cách nhau bằng dấu phẩy. Ca qua đêm ghi 22:00-06:00 ở ngày bắt đầu. Để trống cả tuần = luôn trực.",
        truong: THU.slice(1).map((t, i) => ({
          name: `t${i + 1}`, label: t, placeholder: "08:00-14:00, 18:00-22:00",
          value: n.ca.filter((c) => c.thu === i + 1).map((c) => `${c.bat_dau}-${c.ket_thuc}`).join(", "),
        })),
      });
      if (!d) return;
      const ca = [];
      for (let t = 1; t <= 7; t++) ca.push(..._docKhoang(d[`t${t}`] || "", t));
      await api(`/lich-ca/${n.id}`, { method: "PUT", body: JSON.stringify({ ca }) });
      toast(ca.length ? `Đã xếp ${ca.length} ca cho ${n.ten}.` : `${n.ten} về chế độ luôn trực.`);
    } else {
      const d = await hoiHop({
        tieu_de: `Thêm lịch nghỉ cho ${n.ten}`,
        phu: "Trong lúc nghỉ, bộ định tuyến không giao hội thoại mới cho người này. Giờ Việt Nam.",
        truong: [
          { name: "tu_luc", label: "Từ", type: "datetime-local", required: true },
          { name: "den_luc", label: "Đến", type: "datetime-local", required: true },
          { name: "ly_do", label: "Lý do", maxlength: 200, placeholder: "nghỉ phép" },
        ],
      });
      if (!d) return;
      // Ghi múi giờ TƯỜNG MINH: máy chủ từ chối giờ không múi giờ thay vì đoán.
      const vn = (v) => (v.length === 16 ? v + ":00" : v) + "+07:00";
      await api("/lich-ca/nghi", { method: "POST", body: JSON.stringify({
        nguoi_dung_id: n.id, tu_luc: vn(d.tu_luc), den_luc: vn(d.den_luc), ly_do: d.ly_do || "" }) });
      toast("Đã thêm lịch nghỉ.");
    }
    loadLichCa();
  } catch (e) { toast(e.message, true); }
});

$("#lcNghi")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-lc-xoa-nghi]");
  if (!b) return;
  try {
    await api(`/lich-ca/nghi/${b.dataset.lcXoaNghi}`, { method: "DELETE" });
    toast("Đã xoá lịch nghỉ.");
    loadLichCa();
  } catch (e) { toast(e.message, true); }
});

/* ---------------- Tổng quan ca trực (Công việc → tab đầu) ----------------
 * Ba khối thêm vào màn Ca trực cũ: ai đang trong ca, hội thoại chưa ai
 * nhận, hội thoại quá hạn SLA. Không con số nào tính ở đây — "trong ca" là
 * hàm SQL dang_trong_ca (qua /lich-ca), hai danh sách là bộ lọc của hộp
 * thư (`chua_giao`, `qua_han_sla`). Tính lại bằng JS là hai bản sự thật.
 *
 * Mỗi khối hỏng RIÊNG: một khối lỗi ghi lỗi tại chỗ, không ném ra ngoài —
 * ném ra là chặn luôn hàng chờ "Chờ người xử lý" ngay bên dưới. */
const TQ_SO_DONG = 20;

async function loadTongQuanCa() {
  const pnCa = $("#cvTrongCaPanel");
  if (pnCa) {
    const doc = state.toiQuyen && state.toiQuyen.has("dinh_tuyen.doc");
    pnCa.hidden = !doc;
    if (doc) {
      try {
        const r = await api("/lich-ca");
        const truc = r.nguoi.filter((n) => !n.dang_nghi && (!n.ca.length || n.trong_ca));
        $("#cvTrongCaDem").textContent = `${truc.length}/${r.nguoi.length} người đang trực`;
        $("#cvTrongCa").innerHTML = truc.length ? truc.map((n) => `<div class="row">
            <span class="row__flag row__flag--auto"></span>
            <span class="row__body"><span class="row__title">${esc(n.ten)}</span>
              <span class="row__sub">${n.ca.length ? "đang trong ca" : "luôn trực (chưa xếp ca)"}</span></span>
          </div>`).join("")
          : '<p class="empty">Không ai đang trong ca — hội thoại mới sẽ nằm chờ người tự nhận.</p>';
      } catch (e) {
        $("#cvTrongCa").innerHTML = `<p class="empty">Không tải được lịch ca: ${esc(e.message)}</p>`;
      }
    }
  }
  await _tqDanhSach("#cvChuaGiao", "chua_giao=true",
    "Không có hội thoại nào chưa ai nhận.");
  await _tqDanhSach("#cvSla", "qua_han_sla=true",
    "Không hội thoại nào quá hạn SLA.");
}

async function _tqDanhSach(sel, loc, rong) {
  const o = $(sel);
  if (!o) return;
  try {
    const r = await api(`/inbox/conversations?limit=${TQ_SO_DONG}&${loc}`);
    const ds = r.items || [];
    o.innerHTML = ds.length
      ? ds.map((c) => convRow(c)).join("")
        + (r.next_cursor ? `<p class="empty">Còn nữa — mở Hội thoại và lọc để xem hết.</p>` : "")
      : `<p class="empty">${esc(rong)}</p>`;
    wireConvRows(sel);
  } catch (e) {
    o.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
}
/* ---------------- Sổ yêu cầu của khách (Luật 91/2025, NĐ 356/2025) ---------------- */
/* Hạn và tình trạng do MÁY CHỦ tính (agent/core/yeu_cau_chu_the.py). Ở đây
 * chỉ hiện và gửi thao tác — tính hạn ở hai nơi là hai bản sự thật. */

const YC_TT = {
  qua_han: ["row__flag--halt", "QUÁ HẠN"],
  qua_han_phan_hoi: ["row__flag--halt", "quá hạn phản hồi"],
  sap_het_han: ["row__flag--assist", "sắp hết hạn"],
  dung_han: ["row__flag--auto", "trong hạn"],
  xong: ["row__flag--plain", "đã đóng"],
};

/* Hạn là 00:00 của ngày KẾ TIẾP (máy chủ tính "hết ngày"). Hiện "00:00 31-10"
 * thì người đọc tưởng còn tới sáng 31 — hiện "hết ngày 30-10" mới đúng nghĩa. */
function _han(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const vn = new Date(d.getTime() + 7 * 3600e3);
  if (vn.getUTCHours() === 0 && vn.getUTCMinutes() === 0) {
    const t = new Date(d.getTime() - 1);
    return "hết ngày " + t.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
  }
  return _ngayGio(iso);
}

function _ngayGio(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
}

async function loadYeuCauChuThe() {
  const pn = $("#ycPanel");
  if (!pn) return;
  const co = state.toiQuyen && state.toiQuyen.has("khach.pii");
  pn.hidden = !co;
  if (!co) return;
  let r;
  try { r = await api("/pdpd/yeu-cau"); } catch (e) { toast(e.message, true); return; }
  state.yeuCau = r.yeu_cau;
  const d = r.dem;
  $("#ycDem").textContent = d.qua_han || d.qua_han_phan_hoi
    ? `${d.qua_han + d.qua_han_phan_hoi} QUÁ HẠN · ${d.dang_mo} đang mở`
    : `${d.dang_mo} đang mở${d.sap_het_han ? ` · ${d.sap_het_han} sắp hết hạn` : ""}`;
  $("#ycDs").innerHTML = r.yeu_cau.length ? r.yeu_cau.map((y) => {
    const [co_, nhan] = YC_TT[y.tinh_trang] || YC_TT.dung_han;
    return `<div class="row">
      <span class="row__flag ${co_}"></span>
      <span class="row__body"><span class="row__title">${esc(y.ten_loai)} · <em>${esc(nhan)}</em></span>
        <span class="row__sub">xử lý xong <b>${esc(_han(y.han_xu_ly))}</b>${
          y.da_gia_han ? " (đã gia hạn)" : ""}${y.trang_thai === "moi"
          ? ` · phản hồi ${esc(_han(y.han_phan_hoi))}` : " · đã phản hồi"}</span>
        <span class="row__sub">nhận ${esc(_ngayGio(y.nhan_luc))}${y.noi_dung ? " · " + esc(y.noi_dung) : ""}</span></span>
      <span class="row__side">
        ${y.trang_thai === "moi" ? `<button type="button" class="btn btn--sm" data-yc-phan-hoi="${esc(y.id)}">Đã phản hồi</button>` : ""}
        ${y.da_gia_han ? "" : `<button type="button" class="btn btn--sm" data-yc-gia-han="${esc(y.id)}">Gia hạn</button>`}
        <button type="button" class="btn btn--sm btn--primary" data-yc-xong="${esc(y.id)}">Xong</button>
        <button type="button" class="btn btn--sm btn--halt" data-yc-tu-choi="${esc(y.id)}">Từ chối</button>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Không có yêu cầu nào đang mở.</p>';
}

$("#ycDs")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-yc-phan-hoi], [data-yc-gia-han], [data-yc-xong], [data-yc-tu-choi]");
  if (!b) return;
  const id = b.dataset.ycPhanHoi || b.dataset.ycGiaHan || b.dataset.ycXong || b.dataset.ycTuChoi;
  const y = (state.yeuCau || []).find((x) => x.id === id);
  if (!y) return;
  try {
    if (b.dataset.ycPhanHoi) {
      await api(`/pdpd/yeu-cau/${id}/phan-hoi`, { method: "POST" });
      toast("Đã ghi nhận phản hồi ban đầu.");
    } else if (b.dataset.ycGiaHan) {
      const d = await hoiHop({
        tieu_de: `Gia hạn: ${y.ten_loai}`,
        phu: "Chỉ gia hạn được MỘT lần. Phải báo khách lý do gia hạn — ghi lại lý do ở đây.",
        truong: [{ name: "so_ngay", label: "Thêm bao nhiêu ngày", type: "number", min: 1, max: 20, required: true },
                 { name: "ly_do", label: "Lý do (đã báo khách)", required: true, maxlength: 300 }],
      });
      if (!d) return;
      await api(`/pdpd/yeu-cau/${id}/gia-han`, { method: "POST",
        body: JSON.stringify({ so_ngay: Number(d.so_ngay), ly_do: d.ly_do }) });
      toast("Đã gia hạn.");
    } else {
      const tu_choi = !!b.dataset.ycTuChoi;
      const d = await hoiHop({
        tieu_de: tu_choi ? `Từ chối: ${y.ten_loai}` : `Đóng: ${y.ten_loai}`,
        phu: tu_choi
          ? "Chỉ từ chối khi luật cho phép (Luật 91/2025 Điều 14 khoản 2, Điều 19) — ví dụ đơn hàng phải giữ làm chứng từ kế toán. Ghi căn cứ."
          : "Ghi ngắn đã làm gì. Yêu cầu xoá thực hiện ở khung «Dữ liệu cá nhân» bên dưới sẽ tự đóng ở đây.",
        truong: [{ name: "ket_qua", label: tu_choi ? "Căn cứ từ chối" : "Đã làm gì", required: tu_choi, maxlength: 500 }],
        nut: tu_choi ? "Từ chối" : "Đóng", nguy_hiem: tu_choi,
      });
      if (!d) return;
      await api(`/pdpd/yeu-cau/${id}/dong`, { method: "POST",
        body: JSON.stringify({ ket_qua: d.ket_qua || "", tu_choi }) });
      toast(tu_choi ? "Đã ghi từ chối." : "Đã đóng yêu cầu.");
    }
    loadYeuCauChuThe();
  } catch (e) { toast(e.message, true); }
});

$("#ycForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const v = f.nhan_luc.value;
  const body = {
    loai: f.loai.value, kenh_nhan: f.kenh_nhan.value, sdt: f.sdt.value.trim(),
    noi_dung: f.noi_dung.value.trim(), co_ben_thu_ba: f.co_ben_thu_ba.checked,
    // Giờ Việt Nam TƯỜNG MINH — máy chủ không đoán múi giờ.
    nhan_luc: v ? (v.length === 16 ? v + ":00" : v) + "+07:00" : null,
  };
  try {
    const y = await api("/pdpd/yeu-cau", { method: "POST", body: JSON.stringify(body) });
    toast(y.tinh_trang === "qua_han" || y.tinh_trang === "qua_han_phan_hoi"
      ? "Đã ghi — yêu cầu này ĐÃ QUÁ HẠN theo ngày khách gửi. Xử lý ngay."
      : `Đã ghi. Phải xử lý xong ${_han(y.han_xu_ly)}.`, y.tinh_trang.startsWith("qua_han"));
    f.reset();
    loadYeuCauChuThe();
  } catch (e) { toast(e.message, true); }
});
/* ---------------- kết nối kênh ----------------
 *
 * Tách khỏi 10-vong-lam-moi.js (quá 1000 dòng). Dùng hàm của tệp ấy —
 * quetQR, veFormKenh, lyDoKetNoi, goc_cong_khai — nên đứng SAU nó khi đóng gói.
 */

/* =====================================================================
 * KẾT NỐI KÊNH: điều kiện chung → nối kênh mới → sức khoẻ từng kênh.
 *
 * Luật xanh/vàng/đỏ nằm ở MÁY CHỦ (agent/omnichannel/suc_khoe_kenh.py),
 * không ở đây: giao diện chỉ vẽ. Hai nơi cùng giữ luật là hai nơi lệch nhau.
 * ===================================================================== */
const KN_MUC = { xanh: "Tốt", vang: "Cần để ý", do: "Hỏng", tat: "Đang tắt" };
const KN_NUT = {
  dang_nhap_meta: "Đăng nhập Facebook",
  quet_qr: "Quét QR",
  xac_minh: "Xác minh lại",
  nhan_tin: "Bật nhận tin",
  nhan_thu: "Kiểm lại",
  bat_lai: "Bật lại",
};

async function loadSucKhoeKenh() {
  let d;
  try {
    d = await api("/channel-accounts/suc-khoe-tong");
  } catch (e) {
    $("#kn-suckhoe").innerHTML = `<p class="empty">Không tải được sức khoẻ kênh: ${esc(e.message)}</p>`;
    return;
  }
  state.knDangNhap = d.dang_nhap || {};
  $("#kn-dieukien").innerHTML = `<h2 class="panel__head">Điều kiện chung</h2>` + d.dieu_kien.map((k) =>
    `<div class="kn-dk"><span class="kn-cham kn-cham--${esc(k.muc)}" aria-hidden="true"></span>
      <b>${esc(k.ten)}</b><span>${esc(k.viec)}</span></div>`).join("");

  /* Nút đăng nhập mà ứng dụng chưa khai thì bấm vào chỉ ra một lỗi 503 —
     khoá sẵn và nói lý do ngay trên thẻ. */
  const meta = $('[data-noi="meta"]'), zoa = $('[data-noi="zalo_oa"]');
  if (meta) { meta.disabled = !state.knDangNhap.meta; meta.title = meta.disabled ? "Chưa khai ứng dụng Meta trong .env" : ""; }
  if (zoa) { zoa.disabled = !state.knDangNhap.zalo_oa; zoa.title = zoa.disabled ? "Chưa khai ứng dụng Zalo OA trong .env" : ""; }

  const dem = d.dem || {};
  $("#kn-dem").textContent = `${dem.do || 0} hỏng · ${dem.vang || 0} cần để ý · ${dem.xanh || 0} tốt`
    + (dem.tat ? ` · ${dem.tat} đang tắt` : "");
  $("#kn-suckhoe").innerHTML = d.kenh.length ? d.kenh.map((k) => `<div class="kn-dong">
      <span class="kn-cham kn-cham--${esc(k.muc)}" title="${esc(KN_MUC[k.muc] || k.muc)}"></span>
      <span><b>${esc(k.display_name)}</b><small>${esc(CHANNEL_LABEL[k.channel] || k.channel)}</small></span>
      <span>${esc(k.viec)}<small>${k.tin_vao_gan_nhat
        ? "Tin khách gần nhất: " + esc(clock(k.tin_vao_gan_nhat)) : "Chưa có tin khách nào"}${
        k.token_con_ngay != null ? ` · quyền Meta còn ${Math.max(0, Math.floor(k.token_con_ngay))} ngày` : ""}</small></span>
      <span>${k.hanh_dong && KN_NUT[k.hanh_dong]
        ? `<button type="button" class="btn btn--sm${k.muc === "do" ? " btn--primary" : ""}"
             data-kn-lam="${esc(k.hanh_dong)}" data-kn-id="${esc(k.id)}">${esc(KN_NUT[k.hanh_dong])}</button>` : ""}</span>
    </div>`).join("")
    : '<p class="empty">Chưa nối kênh nào — bắt đầu ở mục Nối kênh mới phía trên.</p>';
}

$("#kn-suckhoe")?.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-kn-lam]");
  if (!b) return;
  const id = b.dataset.knId, lam = b.dataset.knLam;
  b.disabled = true;
  try {
    if (lam === "dang_nhap_meta") { $("#btn-oauth-meta")?.click(); return; }
    if (lam === "quet_qr") { await quetQR(id); return; }
    if (lam === "nhan_thu") {
      toast("Dùng một tài khoản cá nhân nhắn một tin vào kênh này, đợi vài giây rồi bấm lại. "
        + "Vẫn chưa thấy tin thì địa chỉ webhook khai bên hãng chưa đúng.");
      await loadSucKhoeKenh();
      return;
    }
    if (lam === "bat_lai") {
      await api(`/channel-accounts/${id}/enable`, { method: "POST" });
      toast("Đã bật lại kênh.");
    } else if (lam === "nhan_tin") {
      const r = await api(`/channel-accounts/${id}/dang-ky-webhook`, { method: "POST" });
      toast(r && r.ok === false ? "Chưa bật được nhận tin: " + (r.ly_do || "") : "Đã bật nhận tin.", r && r.ok === false);
    } else if (lam === "xac_minh") {
      const kq = await api(`/channel-accounts/${id}/verify`, { method: "POST" });
      /* `/verify` trả 200 kèm `{ok:false}` khi hãng từ chối — đọc `ok`,
         không thì báo xanh giả. */
      toast(kq && kq.ok ? "Đã xác minh xong." : "Chưa xác minh được: " + lyDoKetNoi(kq || {}), !(kq && kq.ok));
    }
    await loadSucKhoeKenh();
    await loadKetNoi();
  } catch (err) {
    toast(err.message, true);
  } finally {
    b.disabled = false;
  }
});

/* Bí mật ký phiên của widget: máy sinh, người không phải nghĩ ra chuỗi 32
   ký tự (form cũ bắt tự đặt — người ta gõ "123456" cho xong). */
function knBiMat() {
  const b = new Uint8Array(32);
  crypto.getRandomValues(b);
  return btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function knGocWebsite(nhap) {
  /* Chỉ lấy GỐC (scheme + tên miền + cổng): máy chủ so Origin của trình
     duyệt, mà Origin không bao giờ mang đường dẫn. Dán cả "…/san-pham" mà
     lưu nguyên thì không phiên nào khớp. */
  let s = String(nhap || "").trim();
  if (s && !/^https?:\/\//i.test(s)) s = "https://" + s;
  try { return new URL(s).origin; } catch { return ""; }
}

async function knNoiWebsite() {
  const d = await hoiHop({
    tieu_de: "Nối chat trên website",
    phu: "Khung chat chỉ mở được trên đúng website này.",
    truong: [
      { name: "ten", label: "Tên kênh", required: true, maxlength: 120, value: "Website BLANICA" },
      { name: "web", label: "Địa chỉ website", required: true, placeholder: "https://blanica.vn",
        hint: "trang chủ là đủ" },
    ],
    nut: "Tạo kênh",
  });
  if (!d) return;
  const goc = knGocWebsite(d.web);
  if (!goc) { toast("Địa chỉ website không hợp lệ.", true); return; }
  const tk = await api("/channel-accounts", { method: "POST", body: JSON.stringify({
    channel: "webchat", display_name: d.ten,
    capabilities: { send_text: true, receive_message: true }, metadata: {},
    credentials: { widget_secret: knBiMat(), allowed_origins: [goc] },
  }) });
  await api(`/channel-accounts/${tk.id}/enable`, { method: "POST" });
  const ma = `<script src="${goc_cong_khai()}/widget.js" data-account-id="${tk.id}"></script>`;
  $("#kn-ketqua").innerHTML = `<div class="kn-ma">
      <code id="kn-ma-nhung">${esc(ma)}</code>
      <button type="button" class="btn btn--sm btn--primary" id="kn-chep">Sao chép</button></div>
    <p class="row__sub">Dán đoạn này vào cuối trang của <b>${esc(goc)}</b> (trước thẻ &lt;/body&gt;).
      Khách mở website sẽ thấy khung chat; tin vào hộp thư chung.</p>`;
  $("#kn-chep").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(ma); toast("Đã sao chép mã nhúng."); }
    catch { toast("Trình duyệt chặn sao chép — bôi đen đoạn mã rồi Ctrl+C.", true); }
  });
  toast("Đã tạo kênh website.");
}

async function knNoiZaloCaNhan() {
  const d = await hoiHop({
    tieu_de: "Nối Zalo cá nhân",
    phu: "Zalo không có API chính thức cho tài khoản cá nhân — Zalo có thể khoá nick dùng cách này. Kênh bền lâu dài là Zalo OA.",
    truong: [{ name: "ten", label: "Tên gợi nhớ", required: true, maxlength: 120, placeholder: "Zalo shop — Lan" }],
    nut: "Tạo và quét QR",
  });
  if (!d) return;
  const tk = await api("/channel-accounts", { method: "POST", body: JSON.stringify({
    channel: "zalo_personal", display_name: d.ten,
    capabilities: { send_text: true, receive_message: true }, metadata: {}, credentials: {},
  }) });
  await quetQR(tk.id);
}

$$("[data-noi]").forEach((b) => b.addEventListener("click", async () => {
  const kenh = b.dataset.noi;
  try {
    if (kenh === "meta") { $("#btn-oauth-meta")?.click(); return; }
    if (kenh === "zalo_oa") { $("#btn-oauth-zalo-oa")?.click(); return; }
    if (kenh === "webchat") { await knNoiWebsite(); }
    else if (kenh === "zalo_personal") { await knNoiZaloCaNhan(); }
    else if (kenh === "whatsapp") {
      $("#connection-create").classList.remove("is-hidden");
      const chon = $('#connectionform [name="channel"]');
      chon.value = "whatsapp";
      veFormKenh("whatsapp");
      $("#nhap-tay")?.setAttribute("open", "");
      chon.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    await loadSucKhoeKenh();
    await loadKetNoi();
  } catch (e) {
    toast(e.message, true);
  }
}));
/* ==================== Phân tích ====================
 *
 * Định nghĩa từng con số ở agent/api/phan_tich.py và docs/phan-tich.md —
 * đọc trước khi dùng nó để đánh giá một người hay một hồ sơ AI. Mọi số đếm
 * theo SỰ KIỆN trong khoảng ngày; ô nào là ảnh chụp "bây giờ" thì nhãn nói
 * vậy. Không nạp theo vòng 6 giây: tám câu truy vấn trên cả khoảng ngày là
 * việc nặng, và con số theo ngày không đổi từng giây. */

const UU_TIEN_NHAN = { low: "thấp", normal: "thường", high: "cao", urgent: "gấp" };
const VAI_NHAN = { customer: "Khách", agent: "AI", staff: "Nhân viên", system: "Hệ thống" };

function _ptQuery(f) {
  const q = new URLSearchParams({ tu: f.tu.value, den: f.den.value });
  for (const k of ["kenh", "account_id", "nhan_vien", "ho_so"]) {
    if (f[k].value) q.set(k, f[k].value);
  }
  return q.toString();
}

async function _ptBoLoc(f) {
  if (state.ptBoLoc) return;
  const b = await api("/phan-tich/bo-loc");
  const tat = '<option value="">Tất cả</option>';
  ganLuaChon(f.kenh, tat + b.kenh.map((k) =>
    `<option value="${esc(k)}">${esc(NEN_TANG_LABEL[String(k).toLowerCase()] || KENH_TEN[k] || k)}</option>`).join(""));
  ganLuaChon(f.account_id, tat + b.tai_khoan.map((t) =>
    `<option value="${esc(t.id)}">${esc(t.ten)} (${esc(t.kenh)})</option>`).join(""));
  ganLuaChon(f.nhan_vien, tat + b.nhan_vien.map((n) =>
    `<option value="${esc(n.id)}">${esc(n.ten)}${n.khoa ? " (đã khoá)" : ""}</option>`).join(""));
  ganLuaChon(f.ho_so, tat + b.ho_so.map((h) =>
    `<option value="${esc(h.id)}">${esc(h.ten)}${h.bat === false ? " (đang tắt)" : ""}</option>`).join(""));
  state.ptBoLoc = true;
}

function _ptTiLe(x) { return x == null ? "—" : pct(x); }

async function loadPhanTich() {
  const f = $("#ptForm");
  if (!f) return;
  if (!f.tu.value) {
    const nay = new Date();
    f.den.value = _ngayVN(nay);
    f.tu.value = _ngayVN(new Date(nay.getTime() - 6 * 86400000));
  }
  state.ptDaTai = true;
  $("#ptExcel").href = `/api/bao-cao/nhan-vien.xlsx?tu=${f.tu.value}&den=${f.den.value}`;
  let d;
  try {
    await _ptBoLoc(f);
    d = await api(`/phan-tich?${_ptQuery(f)}`);
  } catch (e) { toast(e.message, true); return; }

  const h = d.hoi_thoai, k = d.khach, s = d.sla;
  const phDau = s.phan_hoi_dau;
  /* ---- Hiệu quả chăm sóc khách hàng ---- */
  $("#ptCskh").innerHTML = [
    cell("Hội thoại có hoạt động", h.hoat_dong, `${h.moi} mới`, null, "auto"),
    cell("Tỷ lệ xử lý", _ptTiLe(h.ty_le_xu_ly), `${h.hoi_thoai_giai_quyet} được giải quyết`,
         h.ty_le_xu_ly, "auto"),
    cell("Phản hồi đầu (trung vị)", _giay(phDau.tat_ca.trung_vi_giay), `${phDau.tat_ca.so} lượt · AI và nhân viên`, null, "plain"),
    cell("Thời gian giải quyết (trung vị)", _giay(s.thoi_gian_giai_quyet.trung_vi_giay),
         `${s.thoi_gian_giai_quyet.so} lượt`, null, "plain"),
    cell("Mở lại", h.mo_lai, "lượt", h.giai_quyet ? h.mo_lai / h.giai_quyet : null, "assist"),
    cell("Khách có nhắn", k.tong, `${k.moi} mới · ${k.quay_lai} quay lại`, null, "auto"),
    cell("Đang mở (bây giờ)", h.dang_mo, "hội thoại", null, "plain"),
  ].join("");

  /* ---- Hiệu quả AI Agent ---- */
  const at = d.ai_tong;
  $("#ptAiTong").innerHTML = [
    cell("Hội thoại AI xử lý", at.hoi_thoai, `${at.tu_giai_quyet} tự giải quyết`, null, "auto"),
    cell("Tỷ lệ chuyển giao nhân viên", _ptTiLe(at.ty_le_chuyen_giao), `${at.can_nguoi} cần người`,
         at.ty_le_chuyen_giao, "assist"),
    cell("Hiệu quả tự động hoá", _ptTiLe(at.tu_dong_hoa), "AI tự giải quyết / có hoạt động",
         at.tu_dong_hoa, "auto"),
    cell("Chi phí AI trong khoảng", usd(at.chi_phi_usd), "tổng", null, "spend"),
  ].join("");
  /* KHÔNG hiện "độ tin cậy": model tự chấm con số ấy, hiện thành phần trăm
     là mời người đọc tin nó như xác suất đúng. Báo tỉ lệ có / không căn cứ. */
  $("#ptAi").innerHTML = `<thead><tr><th>Hồ sơ</th><th>Hội thoại</th><th>Tự giải quyết</th>
    <th>Cần người</th><th>Chưa kết cục</th><th>Thành công</th><th>Chuyển giao</th>
    <th>AI tự chuyển</th><th>Có căn cứ</th><th>Không căn cứ</th><th>Chi phí</th></tr></thead><tbody>${
    d.ai.length ? d.ai.map((a) => `<tr><td>${esc(a.ten)}</td><td>${a.hoi_thoai}</td>
      <td>${a.tu_giai_quyet}</td><td>${a.can_nguoi}</td><td>${a.dang_do}</td>
      <td>${_ptTiLe(a.ty_le_thanh_cong)}</td><td>${_ptTiLe(a.ty_le_can_nguoi)}</td>
      <td>${a.ai_tu_chuyen}</td><td>${_ptTiLe(a.ty_le_co_can_cu)}</td>
      <td class="${a.ty_le_khong_can_cu ? "so--xau" : ""}">${_ptTiLe(a.ty_le_khong_can_cu)}</td>
      <td>${usd(a.chi_phi_usd)}</td></tr>`).join("")
    : '<tr><td colspan="11" class="empty">Không có tin AI nào trong khoảng này.</td></tr>'}</tbody>`;

  /* ---- Hiệu suất nhân viên ----
     Cột CSAT đã gỡ khỏi bảng: chủ dự án ẩn CSAT khỏi giao diện (phiếu việc
     20.11.2026) và câu hỏi chấm điểm mặc định TẮT — một cột luôn "—" là
     cột người ta học cách bỏ qua. API vẫn trả csat_tb/csat_so. */
  $("#ptNhanVien").innerHTML = `<thead><tr>
    <th>Nhân viên</th><th>Hội thoại được giao</th><th>Tin đã gửi</th>
    <th>Phản hồi đầu (trung vị)</th><th>p90</th><th>Chưa phản hồi</th>
    <th>Đơn</th><th>Trễ SLA</th></tr></thead><tbody>${d.nhan_vien.length
    ? d.nhan_vien.map((n) => `<tr>
      <td>${esc(n.ho_ten)}</td><td>${n.hoi_thoai}</td><td>${n.tin_gui}</td>
      <td>${_giay(n.phan_hoi_trung_vi_giay)}</td><td>${_giay(n.phan_hoi_p90_giay)}</td>
      <td class="${n.chua_phan_hoi ? "so--xau" : ""}">${n.chua_phan_hoi}</td>
      <td>${n.don}</td><td class="${n.tre_sla ? "so--xau" : ""}">${n.tre_sla}</td></tr>`).join("")
    : '<tr><td colspan="8" class="empty">Không có nhân viên nào trong phạm vi.</td></tr>'}</tbody>`;

  /* ---- Chỉ số SLA ---- */
  /* Mỗi mục tiêu có đồng hồ riêng (Cấu hình chung → SLA & Giờ làm việc):
     nói rõ con số nào đo theo cách nào, không gộp thành một chữ "24/7". */
  const cdm = d.che_do_muc_tieu || {};
  const cd = (m) => (cdm[m] === "gio_lam_viec" ? "giờ làm việc" : "24/7");
  $("#ptSlaNote").textContent = "tỷ lệ đáp ứng tính trên mục tiêu có hạn · đồng hồ: phản hồi đầu "
    + cd("phan_hoi_dau") + ", sau chuyển giao " + cd("phan_hoi_sau_chuyen_giao")
    + ", giải quyết " + cd("giai_quyet") + " · \"quá hạn\" là ảnh chụp bây giờ";
  const mcg = s.chuyen_giao || { dung_han: 0, tre_han: 0, ty_le_dung_han: null, canh_bao: 0,
    qua_han: 0, dang_cho: 0, khong_han: 0, thoi_gian: { so: 0 }, nhan_vien: [] };
  $("#ptSla").innerHTML = [
    cell("Đáp ứng phản hồi đầu", _ptTiLe(s.ty_le_dung_han_dau), `${s.dau_dat} đạt · ${s.dau_tre} trễ`,
         s.ty_le_dung_han_dau, s.ty_le_dung_han_dau != null && s.ty_le_dung_han_dau < 0.9 ? "halt" : "auto"),
    cell("Đáp ứng giải quyết", _ptTiLe(s.ty_le_dung_han_xong), `${s.xong_dat} đạt · ${s.xong_tre} trễ`,
         s.ty_le_dung_han_xong, s.ty_le_dung_han_xong != null && s.ty_le_dung_han_xong < 0.9 ? "halt" : "auto"),
    cell("Đáp ứng sau chuyển giao", _ptTiLe(mcg.ty_le_dung_han),
         `${mcg.dung_han} đạt · ${mcg.tre_han} trễ · ${mcg.dang_cho} đang chờ`,
         mcg.ty_le_dung_han, mcg.ty_le_dung_han != null && mcg.ty_le_dung_han < 0.9 ? "halt" : "auto"),
    cell("Số vi phạm", s.vi_pham_tat_ca ?? s.vi_pham,
         `${s.dau_canh_bao + s.xong_canh_bao + mcg.canh_bao} cảnh báo sớm`, null,
         (s.vi_pham_tat_ca ?? s.vi_pham) ? "halt" : "auto"),
    cell("Đang quá hạn (bây giờ)", s.qua_han,
         `${s.qua_han_dau} chưa phản hồi · ${s.qua_han_xong} chưa xong · ${mcg.qua_han} chờ nhân viên sau chuyển giao`,
         null, (s.qua_han || mcg.qua_han) ? "halt" : "auto"),
  ].join("");

  const dongTg = (ten, r, them = "") => `<tr><td>${esc(ten)}</td><td>${r.so}</td><td>${_giay(r.tb_giay)}</td>
    <td>${_giay(r.trung_vi_giay)}</td><td>${r.ty_le_dung_han !== undefined ? _ptTiLe(r.ty_le_dung_han) : "—"}</td>
    <td>${them}</td></tr>`;
  const cg = s.phan_hoi_sau_chuyen_giao;
  const tgVai = s.thoi_gian_giai_quyet.theo_vai || {};
  $("#ptThoiGian").innerHTML = `<thead><tr><th>Thước đo</th><th>Số lượt</th><th>Trung bình</th>
    <th>Trung vị</th><th>Đúng hạn</th><th>Ghi chú</th></tr></thead><tbody>
    ${dongTg("Phản hồi đầu — AI", phDau.theo_vai.agent, `${phDau.theo_vai.agent.tre_han} trễ`)}
    ${phDau.ho_so.map((r) => dongTg("   AI · " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${dongTg("Phản hồi đầu — nhân viên", phDau.theo_vai.staff, `${phDau.theo_vai.staff.tre_han} trễ`)}
    ${phDau.nhan_vien.map((r) => dongTg("   " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${phDau.theo_vai.khong_ro.so ? dongTg("Phản hồi đầu — không rõ (trước 20.11.2026)", phDau.theo_vai.khong_ro) : ""}
    ${dongTg("Phản hồi sau chuyển giao", cg, cg.chua_phan_hoi ? `${cg.chua_phan_hoi} chưa ai nhắn` : "")}
    ${cg.nhan_vien.map((r) => dongTg("   " + r.ten, r)).join("")}
    ${dongTg("Mục tiêu sau chuyển giao (theo lượt)", { ...mcg.thoi_gian, ty_le_dung_han: mcg.ty_le_dung_han },
       `${mcg.tre_han} trễ · ${mcg.khong_han} không đặt hạn`)}
    ${mcg.nhan_vien.map((r) => dongTg("   " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${dongTg("Thời gian giải quyết", s.thoi_gian_giai_quyet)}
    ${tgVai.agent ? dongTg("   AI tự lo", tgVai.agent, `${tgVai.agent.tre_han} trễ`) : ""}
    ${tgVai.staff ? dongTg("   Có nhân viên", tgVai.staff, `${tgVai.staff.tre_han} trễ`) : ""}
    </tbody>`;

  $("#ptNgay").innerHTML = `<thead><tr><th>Ngày</th><th>Mới</th><th>Giải quyết</th>
    <th>Có AI</th><th>Chuyển giao</th><th>Đáp ứng phản hồi đầu</th><th>Vi phạm SLA</th>
    <th>Chi phí AI</th></tr></thead><tbody>${
    d.theo_ngay.map((r) => `<tr><td>${esc(r.ngay)}</td><td>${r.moi}</td><td>${r.giai_quyet}</td>
      <td>${r.ai}</td><td>${_ptTiLe(r.ty_le_can_nguoi)}</td><td>${_ptTiLe(r.ty_le_dung_han_dau)}</td>
      <td class="${r.vi_pham ? "so--xau" : ""}">${r.vi_pham}</td><td>${usd(r.chi_phi_ai_usd)}</td></tr>`).join("")}</tbody>`;

  /* ---- Tin nhắn ---- */
  $("#ptTin").innerHTML = `<thead><tr><th>Nền tảng</th><th>Vai</th><th>Nhận</th>
    <th>Đã gửi</th><th>Gửi lỗi</th><th>Chưa gửi</th></tr></thead><tbody>${d.tin_nhan.length
    ? d.tin_nhan.map((t) => `<tr><td>${esc(NEN_TANG_LABEL[String(t.kenh || "").toLowerCase()] || KENH_TEN[t.kenh] || t.kenh)}</td>
      <td>${esc(VAI_NHAN[t.vai] || t.vai)}</td><td>${t.nhan}</td><td>${t.gui}</td>
      <td class="${t.loi ? "so--xau" : ""}">${t.loi}</td><td>${t.chua_gui}</td></tr>`).join("")
    : '<tr><td colspan="6" class="empty">Không có tin nào trong khoảng này.</td></tr>'}</tbody>`;
}

$("#ptForm")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  loadPhanTich();
});

/* ---------------- Đổi ưu tiên hội thoại ----------------
 *
 * Nút "Đổi" nằm cạnh mức ưu tiên trong panel "Chi tiết" của hội thoại
 * (mục 6.8 — không còn ở thanh thông tin). Luật hạn SLA
 * (chỉ rút ngắn, không kéo dài) ở agent/api/uu_tien.py — hộp thoại nói luật
 * ấy ra để người bấm không tưởng hạ ưu tiên là được thêm giờ. */
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-doi-uu-tien]");
  if (!b) return;
  const cid = b.dataset.doiUuTien;
  const d = await hoiHop({
    tieu_de: "Đổi mức ưu tiên",
    phu: "Nâng ưu tiên rút hạn SLA đang chạy (tính từ bây giờ, không trễ hơn hạn cũ). "
       + "Hạ ưu tiên KHÔNG kéo dài hạn của lượt này — mức mới áp dụng khi hội thoại mở lại.",
    truong: [
      { name: "uu_tien", label: "Mức mới", type: "select", value: b.dataset.uuTien,
        options: Object.entries(UU_TIEN_NHAN).map(([value, label]) => ({ value, label })) },
      { name: "ly_do", label: "Lý do", type: "textarea", required: true, maxlength: 500,
        placeholder: "vd khách khiếu nại, khách sỉ cần gấp…" },
    ],
    nut: "Đổi",
  });
  if (!d) return;
  try {
    const r = await api(`/conversations/${cid}/uu-tien`, {
      method: "PUT",
      body: JSON.stringify({ uu_tien: d.uu_tien, ly_do: d.ly_do,
                             version: b.dataset.version ? Number(b.dataset.version) : null }),
    });
    const rut = r.han_dau_moi !== r.han_dau_cu || r.han_xong_moi !== r.han_xong_cu;
    toast(`Đã đổi sang mức ${UU_TIEN_NHAN[r.uu_tien]}.${rut ? " Hạn SLA đã được rút ngắn." : " Hạn SLA của lượt này giữ nguyên."}`);
    if (state.openConv === cid) await loadThread(cid);
  } catch (e) { toast(e.message, true); }
});
/* ---------------- chuông thông báo nội bộ ----------------
 *
 * Chuông nằm ở thanh trên, KHÔNG có mục riêng trên thanh điều hướng: thông
 * báo là lối tắt tới hội thoại / việc / đơn, không phải một màn để làm việc.
 * Bấm một dòng = đánh dấu đã đọc + đi tới chỗ liên quan. Đọc KHÔNG làm xong
 * việc gì: duyệt nháp, nhận hội thoại, đóng việc vẫn làm ở màn của chúng.
 *
 * Số chưa đọc làm mới theo vòng 6 giây và theo luồng SSE (10-vong-lam-moi).
 * Hỏng thì KHÔNG toast — vòng 6 giây sẽ bắn toast mãi — mà giữ số cũ và ghi
 * console; danh sách mở ra thì báo lỗi ngay trong khung. */

const chuong = { mo: false, chiChuaDoc: false, ds: [], conNua: false, dangTai: false };

function veSoChuong(n) {
  const o = $("#chuongSo");
  if (!o) return;
  o.textContent = n > 99 ? "99+" : String(n || "");
  o.hidden = !n;
  $("#chuongNut")?.setAttribute("aria-label", n ? `Thông báo — ${n} chưa đọc` : "Thông báo");
}

async function taiSoThongBao() {
  if (!$("#chuongNut")) return;
  try {
    const d = await api("/toi/thong-bao/so-chua-doc");
    veSoChuong(d.chua_doc);
  } catch (e) {
    console.warn("Không tải được số thông báo chưa đọc", e);
  }
}

function dongThongBao(t) {
  const ai = [t.ten_khach, t.kenh].filter(Boolean).map(esc).join(" · ");
  return `<button type="button" class="chuong__dong${t.da_doc ? "" : " is-moi"}" role="listitem"
      data-tb="${esc(t.id)}">
    <span class="chuong__loai chuong__loai--${esc(t.loai)}">${esc(t.nhan_loai)}</span>
    <b class="chuong__tieude">${esc(t.tieu_de)}</b>
    ${ai ? `<span class="chuong__phu">${ai}</span>` : ""}
    ${t.noi_dung ? `<span class="chuong__phu">${esc(t.noi_dung)}</span>` : ""}
    <time class="chuong__gio" datetime="${esc(t.tao_luc)}">${esc(clock(t.tao_luc))}${t.da_doc ? "" : " · chưa đọc"}</time>
  </button>`;
}

function veDanhSachChuong() {
  const ds = $("#chuongDs");
  if (!ds) return;
  ds.innerHTML = chuong.ds.length
    ? chuong.ds.map(dongThongBao).join("")
    : `<p class="empty">${chuong.chiChuaDoc ? "Không có thông báo chưa đọc." : "Chưa có thông báo nào."}</p>`;
  $("#chuongThem").hidden = !chuong.conNua;
}

async function taiDanhSachChuong(them = false) {
  if (chuong.dangTai) return;
  chuong.dangTai = true;
  try {
    const q = new URLSearchParams({ gioi_han: "20", bo_qua: String(them ? chuong.ds.length : 0) });
    if (chuong.chiChuaDoc) q.set("chua_doc", "true");
    const d = await api(`/toi/thong-bao?${q}`);
    chuong.ds = them ? chuong.ds.concat(d.thong_bao) : d.thong_bao;
    chuong.conNua = d.con_nua;
    veSoChuong(d.chua_doc);
    veDanhSachChuong();
  } catch (e) {
    $("#chuongDs").innerHTML = `<p class="empty">Không tải được thông báo: ${esc(e.message)}</p>`;
  } finally {
    chuong.dangTai = false;
  }
}

function moDongChuong(mo) {
  chuong.mo = mo;
  $("#chuongKhung").hidden = !mo;
  $("#chuongNut").setAttribute("aria-expanded", mo ? "true" : "false");
  if (mo) taiDanhSachChuong();
}

/* Đi tới chỗ thông báo trỏ vào. Dùng đúng đường điều hướng sẵn có
 * (`doiMan`, `state.openConv`) — một lối thứ hai là một chỗ nữa để lệch. */
async function diToiLienKet(lk) {
  if (!lk) return;
  if (lk.loai === "hoi_thoai") {
    state.openConv = lk.id;
    state.cuonToiChiTiet = true;
    doiMan("hoithoai");
    return;
  }
  if (lk.loai === "don_hang") { doiMan("donhang"); return; }
  if (lk.loai === "cong_viec") {
    /* Màn Công việc mới (25-cong-viec.js) mở thẳng chi tiết + lịch sử, bất
       kể bộ lọc đang chọn. Mô-đun ấy hỏng thì lui về danh sách cũ. */
    if (typeof window.moCongViec === "function" && await window.moCongViec(lk.id)) return;
    doiMan("cv-danh-sach");
    try { await loadCongViec(); } catch { /* vòng làm mới sẽ thử lại */ }
    const dong = $(`#cv-ds [data-cv="${CSS.escape(lk.id)}"]`);
    if (!dong) { toast("Việc này không nằm trong bộ lọc đang chọn ở màn Công việc."); return; }
    dong.scrollIntoView({ behavior: "smooth", block: "center" });
    dong.classList.add("is-chuong");
    setTimeout(() => dong.classList.remove("is-chuong"), 2400);
  }
}

$("#chuongNut")?.addEventListener("click", (e) => {
  e.stopPropagation();
  moDongChuong(!chuong.mo);
});

$("#chuongChuaDoc")?.addEventListener("change", (e) => {
  chuong.chiChuaDoc = e.target.checked;
  taiDanhSachChuong();
});

$("#chuongThem")?.addEventListener("click", () => taiDanhSachChuong(true));

$("#chuongDocHet")?.addEventListener("click", async () => {
  try {
    await api("/toi/thong-bao/da-doc-het", { method: "POST" });
    await taiDanhSachChuong();
  } catch (e) { toast(e.message, true); }
});

$("#chuongDs")?.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-tb]");
  if (!nut) return;
  const t = chuong.ds.find((x) => x.id === nut.dataset.tb);
  if (!t) return;
  if (!t.da_doc) {
    try {
      await api(`/toi/thong-bao/${encodeURIComponent(t.id)}/da-doc`, { method: "POST" });
      t.da_doc = true;
      taiSoThongBao();
    } catch (err) { console.warn("Không đánh dấu đã đọc được", err); }
  }
  moDongChuong(false);
  await diToiLienKet(t.lien_ket);
});

/* Bấm ra ngoài hoặc Esc thì đóng — khung nổi che mất nội dung bên dưới. */
document.addEventListener("click", (e) => {
  if (chuong.mo && !e.target.closest("#chuong")) moDongChuong(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && chuong.mo) { moDongChuong(false); $("#chuongNut")?.focus(); }
});
/* ---------------- Trách nhiệm trong hội thoại ----------------
 *
 * Mọi việc trong một hội thoại phải quy được về người (hoặc AI) đã làm nó
 * (rà soát 20.11.2026). Trước bản này màn hội thoại chỉ hiện "Nhân viên"
 * không tên; không ai duyệt, không hồ sơ agent nào, không lưới nào — dù phần
 * lớn dữ liệu ấy nằm sẵn trong CSDL.
 *
 * QUY ƯỚC HIỂN THỊ (chủ dự án, 21.11.2026):
 *   · Dưới mỗi tin MỘT dòng: Thời gian · Người gửi · Trạng thái.
 *   · Thông tin kỹ thuật (độ tin cậy, nguồn, thời gian xử lý, model, chi
 *     phí) KHÔNG hiện mặc định — chỉ trong "Chi tiết" / "Xem căn cứ".
 *   · Độ tin cậy KHÔNG BAO GIỜ hiện thành phần trăm: "87%" đọc như xác suất
 *     câu trả lời đúng, mà nó chỉ là điểm khớp tài liệu. Người trực thấy
 *     "Có căn cứ" / "Thiếu căn cứ"; con số thô chỉ ở phần kỹ thuật.
 *   · Lịch sử bàn giao nằm trong panel "Chi tiết" của hội thoại, không
 *     chiếm chỗ thường trực ở đầu hội thoại.
 *
 * Tệp này giữ phần VẼ; `03-hoi-thoai.js` gọi vào. Tách riêng vì 03 đã gần
 * trần 1000 dòng.
 */

/* Giờ của MỘT tin: hôm nay thì hh:mm, ngày khác thì kèm ngày. Chỉ hh:mm là
 * người đọc lại hội thoại ba ngày tuổi tưởng mọi tin cùng một buổi — và
 * "khách nhắn 9:05, mình trả lời 9:07" thật ra là cách nhau hai ngày. */
function gioTin(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const nay = new Date();
  const cungNgay = d.getFullYear() === nay.getFullYear()
    && d.getMonth() === nay.getMonth() && d.getDate() === nay.getDate();
  const gio = hhmm(iso);
  if (cungNgay) return gio;
  const ngay = d.toLocaleDateString("vi-VN", {
    day: "2-digit", month: "2-digit",
    ...(d.getFullYear() !== nay.getFullYear() ? { year: "numeric" } : {}),
  });
  return `${ngay} ${gio}`;
}

/* Người gửi, cụ thể nhất có thể. Trả "" khi không có gì cụ thể hơn — nhãn
 * chung theo vai nằm ở `const who` trong `03-hoi-thoai.js`, một bảng duy
 * nhất cho cả bốn vai. Nhân viên KHÔNG tên là thông tin vô dụng khi hai
 * người trực cùng ca. Trong nhóm: tên NGƯỜI GỬI tin, không phải tên nhóm. */
function tenTacGia(m, nguoiGuiNhom, tenKhach) {
  const tg = m.tac_gia || {};
  if (nguoiGuiNhom) return nguoiGuiNhom;
  if (m.role === "staff" && tg.ten) return `Nhân viên (${tg.ten})`;
  if (m.role === "customer" && tenKhach) return `Khách hàng (${tenKhach})`;
  return "";
}

/* Trạng thái lấy NGUYÊN từ `delivery_status` (dữ liệu nền tảng trả về) —
 * không suy đoán. Tin khách vào (`received`) không có trạng thái gửi. */
const TRANG_THAI_TIN = {
  sent: "Đã gửi", delivered: "Đã nhận", read: "Đã đọc",
  draft: "Bản nháp", queued: "Đang gửi", sending: "Đang gửi",
  failed: "Gửi lỗi, đang thử lại", dead: "Không gửi được", cancelled: "Đã huỷ",
};

function trangThaiTin(m) {
  if (m.role === "customer" || m.delivery_status === "received") return "";
  return TRANG_THAI_TIN[m.delivery_status] || "";
}

/* Ai đã sửa / duyệt — một dòng chữ nhỏ cạnh dòng meta, không phải chip to:
 * thông tin cần truy được, không cần đập vào mắt mỗi lần đọc hội thoại. */
function ghiChuNguoiXuLy(m) {
  const tg = m.tac_gia || {};
  const phan = [];
  if (tg.sua_boi) phan.push(`đã sửa bởi ${tg.sua_boi}`);
  else if (m.sua_boi) phan.push(`đã sửa bởi ${m.sua_boi}`);
  if (tg.duyet_boi) phan.push(`duyệt bởi ${tg.duyet_boi}`);
  return phan.length ? `<span class="msg__ghi">${esc(phan.join(" · "))}</span>` : "";
}

function nhanCanCu(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (cc && cc.nhan) return cc.nhan;
  if (m.grounded === true) return "Có căn cứ";
  if (m.grounded === false) return "Thiếu căn cứ";
  return "";
}

/* Bốn trạng thái căn cứ (mục 16) do MÁY CHỦ phân loại từ kết quả tra cứu
 * thật của lượt — `agent/core/dau_vet_ai.py::phan_loai_can_cu`. Không phần
 * trăm. Tin cũ chưa có phân loại thì lui về Có/Thiếu căn cứ như trước. */
const TAG_CAN_CU = { du: "auto", chua_du: "assist", khong_co: "halt", mau_thuan: "halt" };

function tagCanCu(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (cc && cc.ma) return TAG_CAN_CU[cc.ma] || "plain";
  return m.grounded ? "auto" : "assist";
}

function veCanCuPhanLoai(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (!cc || !cc.ma || cc.ma === "du") return "";
  const ds = (mang) => (mang || []).map((x) => `<li>${esc(x)}</li>`).join("");
  return `<div class="ctt__canh">
    ${cc.huong_dan ? `<p><b>${esc(cc.huong_dan)}</b></p>` : ""}
    ${(cc.mau_thuan || []).length ? `<ul class="ctt__ds">${ds(cc.mau_thuan)}</ul>` : ""}
    ${(cc.thieu || []).length ? `<ul class="ctt__ds">${ds(cc.thieu)}</ul>` : ""}
    ${cc.cau_cho ? `<p class="hint">Câu chờ trung lập (KHÔNG phải câu trả lời nghiệp vụ):</p>
      <blockquote class="ctt__trich">${esc(cc.cau_cho)}</blockquote>
      <button type="button" class="btn btn--sm" data-dung-cau-cho="${esc(cc.cau_cho)}">Dùng câu chờ</button>` : ""}
  </div>`;
}

/* "Dùng câu chờ": chỉ ĐIỀN vào ô soạn, không gửi — người trực vẫn là người bấm Gửi. */
document.addEventListener("click", (e) => {
  const nut = e.target.closest("[data-dung-cau-cho]");
  if (!nut) return;
  const o = $('#replyform [name="text"]');
  if (!o) return;
  o.value = nut.dataset.dungCauCho;
  o.focus();
});

/* "Xem căn cứ" trên BẢN NHÁP AI (chế độ gợi ý) — người duyệt cần nó để quyết
 * gửi hay sửa. Tin khác: "Chi tiết" (cùng bảng, kèm thông tin kỹ thuật). */
function nutChiTietTin(m, draft) {
  const coGi = m.role === "agent" || m.tac_gia?.sua_boi || m.tac_gia?.duyet_boi || m.sua_boi;
  if (!coGi) return "";
  const mo = state.chiTietTin && state.chiTietTin.has(String(m.id));
  const nhan = draft ? "Xem căn cứ" : "Chi tiết";
  const can = draft && nhanCanCu(m)
    ? `<span class="tag tag--${tagCanCu(m)}">${esc(nhanCanCu(m))}</span>` : "";
  return `${can}<button type="button" class="msg__goc-nut" data-chi-tiet-tin="${esc(m.id)}"
    aria-expanded="${mo ? "true" : "false"}">${mo ? "Ẩn" : nhan}</button>`;
}

function dongCT(tieu, chi) {
  return `<div class="ctt__dong"><b>${tieu}</b>${chi ? `<span>${chi}</span>` : ""}</div>`;
}

/* Bảng chi tiết của MỘT tin. Ba phần căn cứ — tài liệu (kèm trích đoạn),
 * dữ liệu nghiệp vụ công cụ trả về, quy tắc và lớp lưới đã áp — rồi phần kỹ
 * thuật. KHÔNG có suy luận thô của model: hệ thống không lưu nó, và nó
 * không phải căn cứ. Tham số công cụ đã che số điện thoại/email và ẩn họ
 * tên, địa chỉ ở máy chủ (`agent/core/dau_vet_ai.py`). */
function veChiTietTin(m, draft) {
  if (!(state.chiTietTin && state.chiTietTin.has(String(m.id)))) return "";
  const dv = m.dau_vet_ai || null;
  const tg = m.tac_gia || {};
  let canCu = "";
  if (m.role === "agent") {
    const triThuc = dv && (dv.tri_thuc || []).length
      ? dv.tri_thuc.map((t) => `<li><b>${esc(t.title || "(không tên)")}</b>${
          t.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(t.version)}</span>` : ""}
          ${t.trich ? `<blockquote class="ctt__trich">${esc(t.trich)}</blockquote>` : ""}</li>`).join("")
      : (m.sources || []).map((n) => `<li><b>${esc(n)}</b></li>`).join("");
    const congCu = dv && (dv.cong_cu || []).length
      ? dv.cong_cu.map((c) => `<li><b>${esc(c.ten)}</b>
          <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></li>`).join("")
        + (dv.cong_cu_bo_bot ? `<li class="hint">… và ${esc(dv.cong_cu_bo_bot)} lần gọi nữa không lưu chi tiết.</li>` : "")
      : "";
    const che = (dv && dv.che_do) || {};
    const quyTac = dv ? [
      dongCT("Hồ sơ agent", esc((dv.ho_so && dv.ho_so.ten) || "Mặc định")),
      dongCT("Chế độ", esc((che.chung === "auto" ? "AI tự gửi" : "AI soạn, người duyệt")
        + (che.duyet_rieng ? " · hội thoại này bắt duyệt trước khi gửi" : ""))),
      dv.luoi ? dongCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma)) : dongCT("Lớp lưới", "không lưới nào bắt"),
      dv.chuyen_nguoi && dv.chuyen_nguoi.co ? dongCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : "",
      (dv.goi_ky_nang || []).length ? dongCT("Gói kỹ năng", esc(dv.goi_ky_nang.join(" · "))) : "",
    ].join("") : '<p class="hint">Tin AI này soạn trước khi hệ thống lưu dấu vết — chỉ còn tên tài liệu.</p>';
    canCu = `
      ${dongCT("Căn cứ", esc(nhanCanCu(m) || "—"))}
      ${veCanCuPhanLoai(m)}
      <h4 class="ctt__dau">Tài liệu đã dùng</h4>
      ${triThuc ? `<ul class="ctt__ds">${triThuc}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
      <h4 class="ctt__dau">Dữ liệu nghiệp vụ công cụ trả về</h4>
      ${congCu ? `<ul class="ctt__ds">${congCu}</ul>` : '<p class="hint">Không tra dữ liệu nghiệp vụ nào.</p>'}
      <h4 class="ctt__dau">Quy tắc đã áp</h4>${quyTac}`;
  }
  const tc = dv && dv.tin_cay;
  const kyThuat = m.role === "agent" ? [
    m.confidence != null ? dongCT("Điểm khớp tài liệu", esc(Number(m.confidence).toFixed(2)
      + (tc && tc.nguong != null ? ` (ngưỡng chuyển người ${Number(tc.nguong).toFixed(2)})` : ""))) : "",
    (dv && dv.model) || m.model ? dongCT("Model", esc((dv && dv.model) || m.model)) : "",
    m.latency_ms ? dongCT("Thời gian xử lý", esc(m.latency_ms + " ms")) : "",
    m.cost_usd != null || m.cost != null ? dongCT("Chi phí", esc(usd(m.cost_usd ?? m.cost))) : "",
  ].join("") : "";
  const nguoi = [
    tg.sua_boi ? dongCT("Sửa bởi", esc(tg.sua_boi + (tg.sua_luc ? " lúc " + gioTin(tg.sua_luc) : ""))) : "",
    tg.duyet_boi ? dongCT("Duyệt bởi", esc(tg.duyet_boi + (tg.duyet_luc ? " lúc " + gioTin(tg.duyet_luc) : ""))) : "",
  ].join("");
  return `<div class="ctt">${canCu}
    ${nguoi ? `<h4 class="ctt__dau">Người xử lý</h4>${nguoi}` : ""}
    ${kyThuat && !draft ? `<h4 class="ctt__dau">Kỹ thuật</h4>${kyThuat}` : ""}
    ${kyThuat && draft ? `<details class="ctt__kt"><summary>Kỹ thuật</summary>${kyThuat}</details>` : ""}
  </div>`;
}

/* ---------------- Chi tiết hội thoại ----------------
 * Người đang giữ, nhóm, và lịch sử bàn giao — trong MỘT panel mở bằng nút
 * "Chi tiết" ở đầu hội thoại. Tải lịch sử khi MỞ, tải lại khi version đổi;
 * không gọi mỗi 6 giây cho một panel không ai mở. */
function veChiTietHoiThoai(c, laCuaToi) {
  const id = String(c.id);
  if (state.moChiTietHT !== id) return "";
  const bo = state.lichSuPC && state.lichSuPC[id];
  if (!bo || bo.version !== c.version) taiLichSuPhanCong(c);
  let lichSu = '<p class="hint">Đang tải…</p>';
  if (bo && bo.loi) lichSu = `<p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  else if (bo && bo.items) {
    lichSu = bo.items.length ? bo.items.slice().reverse().map((m) => `<div class="lichsu__dong lichsu__dong--${esc(m.loai)}">
        <b>${esc(m.tieu_de)}</b>
        <span class="msg__meta">${esc(gioTin(m.luc))}${m.nguoi_lam ? " · bởi " + esc(m.nguoi_lam) : ""}${
          m.ket_thuc ? " · kết thúc " + esc(gioTin(m.ket_thuc)) : ""}</span>
        ${m.chi_tiet ? `<p>${esc(m.chi_tiet)}</p>` : ""}
      </div>`).join("") : '<p class="hint">Chưa có lần bàn giao nào.</p>';
  }
  let giu;
  if (c.mode !== "human") giu = c.assigned_to_ten ? `AI đang xử lý · theo dõi: ${esc(c.assigned_to_ten)}` : "AI đang xử lý";
  else if (!c.assigned_to) giu = "Chưa ai nhận";
  else giu = `${esc(laCuaToi ? "Bạn" : (c.assigned_to_ten || "Đồng nghiệp"))}${
    c.assigned_team_ten ? " · nhóm " + esc(c.assigned_team_ten) : ""}`;
  /* Ưu tiên, chế độ AI, Version, trạng thái, kênh — dời từ thanh thông tin
   * xuống đây (mục 6.1, 6.2, 6.7, 6.8): cần khi tra cứu, không cần mỗi lần
   * đọc hội thoại. SLA KHÔNG có ở đây (mục 15.7) — cảnh báo SLA đi qua
   * chuông. "Đổi" ưu tiên đòi `hoi_thoai.nhan` như máy chủ (uu_tien.py). */
  const doiUuTien = state.toiQuyen && state.toiQuyen.has("hoi_thoai.nhan") && c.state !== "resolved"
    ? ` <button type="button" class="btn btn--sm btn--ghost" data-doi-uu-tien="${esc(c.id)}"
        data-uu-tien="${esc(c.priority || "normal")}" data-version="${c.version || ""}">Đổi</button>` : "";
  const cheDo = { auto: "AI tự gửi", assist: "AI soạn, người duyệt", human: "Nhân viên xử lý" }[c.mode] || c.mode || "—";
  return `<section class="lichsu" aria-label="Chi tiết hội thoại">
    ${dongCT("Người đang giữ", giu)}
    ${dongCT("Trạng thái", esc(c.state === "resolved" ? "Đã giải quyết" : (SIGNAL_LABEL[c.status] || c.status || "—")))}
    ${dongCT("Chế độ AI", esc(cheDo))}
    <div class="ctt__dong"><b>Ưu tiên</b><span>${esc(UU_TIEN_NHAN[c.priority] || c.priority || "thường")}</span>${doiUuTien}</div>
    ${dongCT("Kênh", `${esc(c.account_name || "—")} · ${esc(CHANNEL_LABEL[c.account_channel] || c.account_channel || "")}`)}
    ${dongCT("Version", esc(c.version || 1))}
    <h4 class="ctt__dau">Lịch sử bàn giao</h4>${lichSu}
    ${typeof veNhatKyHoiThoai === "function" ? veNhatKyHoiThoai(c) : ""}
  </section>`;
}

async function taiLichSuPhanCong(c) {
  const id = String(c.id);
  state.lichSuPC = state.lichSuPC || {};
  if (state.lichSuPC[id] && state.lichSuPC[id].dangTai) return;
  state.lichSuPC[id] = { ...(state.lichSuPC[id] || {}), dangTai: true, version: c.version };
  try {
    const r = await api(`/inbox/conversations/${id}/lich-su-phan-cong`);
    state.lichSuPC[id] = { items: r.items || [], version: c.version };
  } catch (e) {
    // Hỏng thì NÓI trong panel, không toast: vòng 6 giây sẽ bắn toast mãi.
    state.lichSuPC[id] = { loi: e.message, version: c.version };
  }
  if (state.openConv === id) loadThread(id);
}

/* "Giao cho…" — chọn người (và nhóm) trong danh sách máy chủ trả về, theo
 * ĐÚNG luật `can_assign`. Nhân viên thường không có quyền giao người khác
 * thì không thấy nút: một danh sách bấm vào chỉ nhận 403 là bẫy. */
async function giaoHoiThoai(c) {
  let ds;
  try {
    ds = await api(`/inbox/conversations/${c.id}/nguoi-nhan-duoc`);
  } catch (e) { toast(e.message, true); return; }
  if (!ds.co_the_giao_khac) {
    toast("Giao cho người khác cần quyền quản lý kênh. Bạn vẫn tự nhận được.", true);
    return;
  }
  const d = await hoiHop({
    tieu_de: "Giao hội thoại",
    phu: "Người nhận phải là thành viên kênh; chọn nhóm thì người nhận phải thuộc nhóm đó.",
    truong: [
      { name: "assignee_id", label: "Giao cho", type: "select", required: true,
        value: c.assigned_to || "",
        options: ds.nguoi.map((n) => ({ value: n.id,
          label: `${n.ten}${n.dang_giu ? ` (đang giữ ${n.dang_giu})` : ""}` })) },
      { name: "team_id", label: "Nhóm", type: "select", value: c.assigned_team_id || "",
        options: [{ value: "", label: "— Không theo nhóm —" },
          ...ds.nhom.map((t) => ({ value: t.id, label: t.ten }))] },
      { name: "reason", label: "Lý do", required: true, maxlength: 500,
        value: "Bàn giao cho người phụ trách" },
    ],
    nut: "Giao",
  });
  if (!d) return;
  try {
    await api(`/inbox/conversations/${c.id}/takeover`, {
      method: "POST",
      body: JSON.stringify({
        assignee_id: d.assignee_id, team_id: d.team_id || null,
        expected_version: c.version || 1, reason: d.reason,
      }),
    });
    const ten = (ds.nguoi.find((n) => String(n.id) === String(d.assignee_id)) || {}).ten;
    toast(`Đã giao cho ${ten || "người nhận"}.`);
    if (state.lichSuPC) delete state.lichSuPC[String(c.id)];
    refresh();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", (ev) => {
  const nut = ev.target.closest("[data-chi-tiet-tin]");
  if (nut) {
    state.chiTietTin = state.chiTietTin || new Set();
    const mid = nut.dataset.chiTietTin;
    if (state.chiTietTin.has(mid)) state.chiTietTin.delete(mid); else state.chiTietTin.add(mid);
    if (state.openConv) loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-chitiet-ht") && state.openConv) {
    const id = String(state.openConv);
    state.moChiTietHT = state.moChiTietHT === id ? null : id;
    loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-giao") && state.convDangMo) {
    state.moHanhDong = null;   // nút nằm trong menu "⋯" — đóng nó lại
    giaoHoiThoai(state.convDangMo);
  }
});

/* ---------------- Bộ lọc hộp thư ----------------
 * Kênh, người giữ (tôi / chưa ai nhận / một người), riêng hay nhóm, quá hạn
 * SLA. API đã nhận kênh và người giữ từ lâu mà màn hình không dùng: người
 * trực muốn xem "việc của tôi" phải cuộn cả danh sách. */
state.convLoc = state.convLoc || { kenh: "", giu: "", loai: "", sla: false };

function chuoiLocHopThu() {
  const l = state.convLoc;
  let q = "";
  if (l.kenh) q += `&account_id=${encodeURIComponent(l.kenh)}`;
  if (l.giu === "chua_giao") q += "&chua_giao=true";
  else if (l.giu === "toi" && state.toiId) q += `&assignee_id=${encodeURIComponent(state.toiId)}`;
  else if (l.giu && l.giu !== "toi") q += `&assignee_id=${encodeURIComponent(l.giu)}`;
  if (l.loai) q += `&loai=${encodeURIComponent(l.loai)}`;
  if (l.sla) q += "&qua_han_sla=true";
  return q;
}

function dangLocHopThu() {
  const l = state.convLoc;
  return !!(l.kenh || l.giu || l.loai || l.sla);
}

/* Danh sách kênh và người cho hai ô chọn — nạp MỘT lần mỗi phiên trang.
 * Hỏng thì hai ô chỉ còn lựa chọn cố định; lần vào màn sau thử lại. */
async function napBoLocHopThu() {
  if (state.boLocDaNap || !$("#loc-kenh")) return;
  state.boLocDaNap = true;
  let d;
  try { d = await api("/inbox/bo-loc"); } catch (e) {
    state.boLocDaNap = false;
    console.warn("Không nạp được bộ lọc hộp thư", e);
    return;
  }
  $("#loc-kenh").innerHTML = '<option value="">Mọi kênh</option>' + (d.kenh || []).map((k) =>
    `<option value="${esc(k.id)}">${esc(k.ten)} · ${esc(CHANNEL_LABEL[k.channel] || k.channel)}</option>`).join("");
  $("#loc-giu").innerHTML = `<option value="">Mọi người giữ</option>
    <option value="toi">Của tôi</option><option value="chua_giao">Chưa ai nhận</option>`
    + (d.nguoi || []).filter((n) => String(n.id) !== String(state.toiId || "")).map((n) =>
      `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
  $("#loc-kenh").value = state.convLoc.kenh;
  $("#loc-giu").value = state.convLoc.giu;
}

/* Gắn TỪNG ô bằng id viết đủ: `tests/test_nut_chet.py` tìm "#loc-…" trong
 * app.js để biết ô có người nghe — ghép chuỗi id là ô trông như nút chết. */
function ganLoc(o, khoa) {
  o?.addEventListener("change", (ev) => {
    state.convLoc[khoa] = ev.target.value;
    loadConversations();
  });
}
ganLoc($("#loc-kenh"), "kenh");
ganLoc($("#loc-giu"), "giu");
ganLoc($("#loc-loai"), "loai");

$("#loc-sla")?.addEventListener("click", (ev) => {
  state.convLoc.sla = !state.convLoc.sla;
  ev.currentTarget.classList.toggle("is-on", state.convLoc.sla);
  ev.currentTarget.setAttribute("aria-pressed", state.convLoc.sla ? "true" : "false");
  loadConversations();
});
/* ---------------- Nhãn động (mục 3 của bảng việc) ---------------- */
/* MỘT danh mục, HAI loại độc lập (migration 0056, agent/core/nhan.py):
 *   nhãn KHÁCH     mô tả con người, gắn ở Customer 360, đi theo hồ sơ.
 *   nhãn HỘI THOẠI mô tả một vụ việc, gắn bằng nút "+ Nhãn" dưới tên khách
 *                  trên đầu hội thoại; KHÔNG thay trạng thái xử lý.
 * Nhãn đã ngừng không có trong ô chọn, nhưng chỗ đã gắn vẫn hiện (xám) —
 * ngừng dùng là thôi gắn MỚI, không phải xoá khỏi lịch sử.
 *
 * Mọi hộp nhập đi qua `hoiHop` chứ không là ô trong panel: vòng làm mới 6
 * giây dựng lại panel, chữ đang gõ trong đó sẽ mất. */

const LOAI_NHAN = {
  khach: { ten: "Nhãn khách hàng", duong: "/nhan/khach",
           giai_thich: "Mô tả con người, sống lâu: khách sỉ, da nhạy cảm. Gắn ở Customer 360." },
  hoi_thoai: { ten: "Nhãn hội thoại", duong: "/nhan/hoi-thoai",
               giai_thich: "Mô tả một vụ việc: chờ hàng về, khiếu nại ship. Gắn trên hội thoại; không thay trạng thái xử lý." },
};
const MAU_NHAN_MAC_DINH = "#4b5563";

/* Màu đi vào thuộc tính `style` — chỉ nhận đúng dạng #rrggbb. Máy chủ đã
 * kiểm, nhưng một chuỗi lạ lọt vào đây là chèn được CSS tuỳ ý. */
function _mauNhan(m) {
  return /^#[0-9a-f]{6}$/i.test(String(m || "")) ? String(m).toLowerCase() : MAU_NHAN_MAC_DINH;
}

/* Chữ trắng hay chữ đậm — cùng công thức WCAG với `mau_chu()` bên máy chủ.
 * Người quản trị chọn màu tuỳ ý; nhãn vàng nhạt chữ trắng là nhãn không ai
 * đọc được. */
function mauChuNhan(nen) {
  const m = _mauNhan(nen);
  const sang = (hex) => {
    const k = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const tp = (a, b) => { const [x, y] = [sang(a), sang(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  return tp(m, "#ffffff") >= tp(m, "#111827") ? "#ffffff" : "#111827";
}

/* Một chip nhãn. `go` = { loai, dich } thì có nút × gỡ. */
function chipNhan(n, go) {
  const mau = _mauNhan(n.mau);
  const ngung = n.dang_dung === false;
  const nut = go
    ? `<button type="button" class="nhan__go" data-nhan-go="${esc(n.id)}" data-nhan-loai="${esc(go.loai)}"
        data-nhan-dich="${esc(go.dich)}" aria-label="Gỡ nhãn ${esc(n.ten)}">×</button>`
    : "";
  return `<span class="nhan nhan--mau${ngung ? " is-ngung" : ""}"
    style="--nhan-nen:${mau};--nhan-chu:${mauChuNhan(mau)}"
    title="${esc(n.ten)}${ngung ? " — đã ngừng sử dụng" : ""}">${esc(n.ten)}${nut}</span>`;
}

/* Chip ở dòng danh sách hội thoại. Phản hồi cũ chỉ có `nhan` (tên). */
function chipNhanDong(c) {
  const ds = Array.isArray(c.nhan_chi_tiet) ? c.nhan_chi_tiet
    : (c.nhan || []).map((t) => ({ id: "", ten: t, mau: MAU_NHAN_MAC_DINH }));
  return ds.length ? `<span class="row__nhan">${ds.map((n) => chipNhan(n)).join("")}</span>` : "";
}

/* Hàng nhãn dưới tên khách trên đầu hội thoại (mục 6.3). Chỉ nhãn HỘI
 * THOẠI: nhãn khách sống ở Customer 360 (mục 6.4), không lặp lại ở đây. */
function nhanHoiThoaiHtml(c) {
  // Gắn/gỡ nhãn hội thoại đi theo `hoi_thoai.ghi_chu` (migration 0058) — cùng
  // quyền máy chủ đòi ở POST/DELETE .../nhan.
  const sua = state.toiQuyen && state.toiQuyen.has("hoi_thoai.ghi_chu");
  const ds = c.nhan_chi_tiet || [];
  return `${ds.map((n) => chipNhan(n, sua ? { loai: "hoi_thoai", dich: c.id } : null)).join("")}
    ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-nhan-them="hoi_thoai"
      data-nhan-dich="${esc(c.id)}">+ Nhãn</button>` : ""}`;
}

/* Khối nhãn khách trong Customer 360 (mục 6.4). */
function nhanKhachHtml(contact) {
  const sua = state.toiQuyen && state.toiQuyen.has("khach.sua");
  const ds = contact.nhan || [];
  return `<div class="profile-actions" id="contact-nhan">
    <div class="profile-tags">${ds.length
      ? ds.map((n) => chipNhan(n, sua ? { loai: "khach", dich: contact.id } : null)).join("")
      : '<span class="empty">Chưa có nhãn.</span>'}</div>
    ${sua ? `<button type="button" class="btn btn--sm" data-nhan-them="khach"
      data-nhan-dich="${esc(contact.id)}">+ Nhãn</button>` : ""}</div>`;
}

/* Hộp chọn một nhãn ĐANG DÙNG của một loại, bỏ những nhãn đã gắn. */
async function chonNhan(loai, daGan = []) {
  const L = LOAI_NHAN[loai];
  let ds;
  try { ds = (await api(L.duong)).nhan || []; } catch (e) { toast(e.message, true); return null; }
  const con = ds.filter((n) => !daGan.includes(n.id));
  if (!con.length) {
    toast(ds.length ? "Đã gắn hết các nhãn đang dùng."
      : `Chưa có ${L.ten.toLowerCase()} nào — tạo ở Cấu hình → Quản lý nhãn.`, true);
    return null;
  }
  const d = await hoiHop({
    tieu_de: `Gắn ${L.ten.toLowerCase()}`,
    phu: L.giai_thich,
    truong: [{ name: "nhan_id", label: "Nhãn", type: "select", required: true,
               options: con.map((n) => ({ value: n.id, label: n.mo_ta ? `${n.ten} — ${n.mo_ta}` : n.ten })) }],
    nut: "Gắn nhãn",
  });
  return d && d.nhan_id ? d.nhan_id : null;
}

function _napLaiSauNhan(loai, dich) {
  if (loai === "hoi_thoai") return loadConversations();
  if (typeof loadContactDetail === "function") return loadContactDetail(dich);
}

document.addEventListener("click", async (ev) => {
  const them = ev.target.closest("[data-nhan-them]");
  const go = ev.target.closest("[data-nhan-go]");
  if (!them && !go) return;
  const el = them || go;
  const loai = el.dataset.nhanThem || el.dataset.nhanLoai;
  const dich = el.dataset.nhanDich;
  const goc = loai === "hoi_thoai" ? `/inbox/conversations/${dich}/nhan` : `/contacts/${dich}/nhan`;
  try {
    if (them) {
      const khung = el.parentElement;
      const daGan = $$("[data-nhan-go]", khung).map((b) => b.dataset.nhanGo);
      const nid = await chonNhan(loai, daGan);
      if (!nid) return;
      await api(goc, { method: "POST", body: JSON.stringify({ nhan_id: nid }) });
      toast("Đã gắn nhãn.");
    } else {
      await api(`${goc}/${encodeURIComponent(el.dataset.nhanGo)}`, { method: "DELETE" });
      toast("Đã gỡ nhãn.");
    }
    await _napLaiSauNhan(loai, dich);
  } catch (e) { toast(e.message, true); }
});

/* Ô lọc danh sách khách theo nhãn khách. Lọc ở MÁY CHỦ (`nhan_id`), không
 * lọc 100 dòng đã tải: khách thứ 101 mang nhãn thì lọc phía giao diện nói
 * "không có ai" — sai mà trông đúng. */
async function napLocNhanKhach() {
  const o = $("#contactLocNhan");
  if (!o) return;
  let ds = [];
  try { ds = (await api(LOAI_NHAN.khach.duong)).nhan || []; } catch { o.hidden = true; return; }
  const html = '<option value="">Mọi nhãn khách</option>'
    + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
  if (o.dataset.html !== html) {
    o.innerHTML = html;
    o.dataset.html = html;
    o.value = state.khachNhan || "";
  }
  o.hidden = !ds.length && !state.khachNhan;
}

$("#contactLocNhan")?.addEventListener("change", (ev) => {
  state.khachNhan = ev.target.value;
  loadContacts();
});

/* ---------------- Quản lý nhãn (Cấu hình chung → tab "Quản lý nhãn") ---------------- */
/* Đăng ký như một mô-đun gắn được: khung tab (01b-dieu-huong.js `ganKhe`)
 * gọi `GAN_TAB['cc-nhan'](khung)` một lần, lần đầu tab hiện ra. */
window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["cc-nhan"] = (el) => moQuanLyNhan(el);

async function moQuanLyNhan(el) {
  if (!el) return;
  if (!el.dataset.nhanGan) {
    el.dataset.nhanGan = "1";
    el.addEventListener("click", (ev) => _bamQuanLyNhan(el, ev));
  }
  await _veQuanLyNhan(el);
}

async function _veQuanLyNhan(el) {
  let d;
  try { d = await api("/nhan"); }
  catch (e) { el.innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  el._nhan = d;
  const sua = state.toiQuyen && state.toiQuyen.has("cau_hinh.sua");
  const khoi = Object.keys(LOAI_NHAN).map((loai) => {
    const L = LOAI_NHAN[loai];
    const ds = d.nhan.filter((n) => n.loai === loai);
    const dong = ds.map((n) => {
      const dung = Number(n.so_khach || 0) + Number(n.so_hoi_thoai || 0) + Number(n.so_quy_tac || 0);
      const noi = loai === "khach" ? `${n.so_khach} khách` : `${n.so_hoi_thoai} hội thoại`;
      return `<div class="row${n.dang_dung ? "" : " is-ngung"}">
        <span class="row__body">
          <span class="row__title">${chipNhan(n)}${n.dang_dung ? "" : ' <em class="hint">đã ngừng sử dụng</em>'}</span>
          ${n.mo_ta ? `<span class="row__sub">${esc(n.mo_ta)}</span>` : ""}
          <span class="row__sub">Đang gắn: ${esc(noi)}${n.so_quy_tac ? ` · ${n.so_quy_tac} quy tắc tự động` : ""}</span>
        </span>
        ${sua ? `<span class="row__side">
          <button type="button" class="btn btn--sm" data-nl-sua="${esc(n.id)}">Sửa</button>
          <button type="button" class="btn btn--sm" data-nl-trang-thai="${esc(n.id)}"
            data-dang-dung="${n.dang_dung ? "1" : ""}">${n.dang_dung ? "Ngừng sử dụng" : "Dùng lại"}</button>
          ${dung ? "" : `<button type="button" class="btn btn--sm btn--halt" data-nl-xoa="${esc(n.id)}"
            title="Chỉ xoá được nhãn chưa từng dùng">Xoá</button>`}
        </span>` : ""}
      </div>`;
    }).join("");
    return `<section class="quan-ly-nhan__loai">
      <h3 class="subhead">${esc(L.ten)}
        ${sua ? `<button type="button" class="btn btn--sm btn--primary" data-nl-them="${loai}">+ Thêm nhãn</button>` : ""}</h3>
      <p class="panel__note">${esc(L.giai_thich)}</p>
      <div class="rows">${dong || '<p class="empty">Chưa có nhãn nào.</p>'}</div>
    </section>`;
  }).join("");
  const html = `<div class="quan-ly-nhan">${khoi}</div>`;
  // Chỉ thay khi đổi: trang Cấu hình làm mới 6 giây một lần, thay lại cả
  // khối là nút đang được rê chuột nhấp nháy.
  if (el.innerHTML !== html) el.innerHTML = html;
}

function _truongNhan(n, bangMau, soDaCo) {
  const mau = n ? n.mau : bangMau[soDaCo % bangMau.length];
  return [
    { name: "ten", label: "Tên nhãn", required: true, maxlength: 80, value: n ? n.ten : "" },
    { name: "mau", label: "Màu", type: "color", value: mau,
      hint: "chữ trên nhãn tự chọn trắng hoặc đậm cho dễ đọc" },
    { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 2, maxlength: 300, value: n ? n.mo_ta : "" },
    { name: "thu_tu", label: "Thứ tự", type: "number", min: 0, max: 10000, value: n ? n.thu_tu : 100,
      hint: "số nhỏ đứng trước trong ô chọn" },
  ];
}

async function _bamQuanLyNhan(el, ev) {
  const b = ev.target.closest("[data-nl-them], [data-nl-sua], [data-nl-trang-thai], [data-nl-xoa]");
  if (!b) return;
  const d = el._nhan || { nhan: [], bang_mau: [MAU_NHAN_MAC_DINH] };
  const tim = (id) => d.nhan.find((n) => n.id === id);
  try {
    if (b.dataset.nlThem) {
      const loai = b.dataset.nlThem;
      const v = await hoiHop({ tieu_de: `Thêm ${LOAI_NHAN[loai].ten.toLowerCase()}`,
        phu: LOAI_NHAN[loai].giai_thich,
        truong: _truongNhan(null, d.bang_mau, d.nhan.filter((n) => n.loai === loai).length), nut: "Tạo nhãn" });
      if (!v) return;
      await api("/nhan", { method: "POST", body: JSON.stringify({
        loai, ten: v.ten, mau: v.mau, mo_ta: v.mo_ta || "", thu_tu: Number(v.thu_tu || 100) }) });
      toast("Đã tạo nhãn.");
    } else if (b.dataset.nlSua) {
      const n = tim(b.dataset.nlSua);
      if (!n) return;
      const v = await hoiHop({ tieu_de: `Sửa nhãn «${n.ten}»`,
        phu: "Đổi tên hay màu là đổi ở MỌI chỗ đang gắn nhãn này. Không đổi được loại nhãn.",
        truong: _truongNhan(n, d.bang_mau, 0), nut: "Lưu" });
      if (!v) return;
      await api(`/nhan/${n.id}`, { method: "PUT", body: JSON.stringify({
        ten: v.ten, mau: v.mau, mo_ta: v.mo_ta || "", thu_tu: Number(v.thu_tu || 100) }) });
      toast("Đã lưu nhãn.");
    } else if (b.dataset.nlTrangThai) {
      const n = tim(b.dataset.nlTrangThai);
      if (!n) return;
      if (b.dataset.dangDung) {
        const ok = await hoiHop({ tieu_de: `Ngừng sử dụng «${n.ten}»?`,
          phu: "Nhãn biến khỏi ô chọn, không gắn mới được. Chỗ đã gắn GIỮ NGUYÊN (hiện xám), lịch sử vẫn đọc được tên. Bật lại lúc nào cũng được.",
          nut: "Ngừng sử dụng", nguy_hiem: true });
        if (!ok) return;
        const r = await api(`/nhan/${n.id}/ngung`, { method: "POST" });
        toast(r.canh_bao || "Đã ngừng sử dụng nhãn.", Boolean(r.canh_bao));
      } else {
        await api(`/nhan/${n.id}/dung-lai`, { method: "POST" });
        toast("Đã dùng lại nhãn.");
      }
    } else if (b.dataset.nlXoa) {
      const n = tim(b.dataset.nlXoa);
      if (!n) return;
      const ok = await hoiHop({ tieu_de: `Xoá nhãn «${n.ten}»?`,
        phu: "Chỉ xoá được nhãn CHƯA từng gắn ở đâu (tạo nhầm). Nhãn đã dùng thì hãy Ngừng sử dụng.",
        nut: "Xoá", nguy_hiem: true });
      if (!ok) return;
      await api(`/nhan/${n.id}`, { method: "DELETE" });
      toast("Đã xoá nhãn.");
    }
    await _veQuanLyNhan(el);
  } catch (e) { toast(e.message, true); }
}

/* ---------------- Nhãn trong quy tắc tự động (mục 7.8) ---------------- */
/* Sáu ô chọn của biểu mẫu quy tắc: ô `data-qt-nhan="hoi_thoai"` chỉ có nhãn
 * hội thoại, ô `"khach"` chỉ có nhãn khách. Tên nhãn theo id giữ trong
 * `state.tenNhan` để câu mô tả quy tắc đọc được ("có nhãn Chờ hàng"). */
async function napONhanQuyTac() {
  state.tenNhan = state.tenNhan || {};
  for (const loai of Object.keys(LOAI_NHAN)) {
    let ds = [];
    try { ds = (await api(LOAI_NHAN[loai].duong)).nhan || []; } catch { ds = []; }
    ds.forEach((n) => { state.tenNhan[n.id] = n.ten; });
    const html = '<option value="">— không xét —</option>'
      + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
    $$(`[data-qt-nhan="${loai}"]`).forEach((o) => {
      // Giữ lựa chọn đang có; chỉ thay khi danh sách đổi (làm mới 6 giây).
      if (o.dataset.html === html) return;
      const giu = o.value;
      o.innerHTML = html;
      o.dataset.html = html;
      if (giu) _datONhan(o, giu);
    });
  }
}

/* Chọn một id trong ô; nhãn đã ngừng (không có trong ô) thì thêm một dòng
 * "(đã ngừng)" — không thì mở sửa quy tắc là mất lặng lẽ điều kiện cũ. */
function _datONhan(o, id) {
  if (!id) { o.value = ""; return; }
  if (![...o.options].some((x) => x.value === id)) {
    const x = document.createElement("option");
    x.value = id;
    x.textContent = `${tenNhanTheoId(id)} (đã ngừng)`;
    o.appendChild(x);
  }
  o.value = id;
}

function tenNhanTheoId(id) {
  return (state.tenNhan && state.tenNhan[id]) || "nhãn đã ngừng";
}
/* ---------------- Kết nối & Tích hợp ----------------
 *
 * Một thẻ cho MỖI dịch vụ (ERPNext, GHN, GHTK) và mỗi plugin kênh: trường
 * cấu hình, nút Kiểm tra kết nối, webhook và lịch sử nhận — cùng một chỗ.
 * Người vận hành hỏi "GHN có chạy không", không hỏi "webhook có chạy không".
 *
 * Luật trạng thái (Chưa cấu hình / Chưa kiểm tra / Thành công / Lỗi) nằm ở
 * MÁY CHỦ (agent/ket_noi_tich_hop.py). Ở đây chỉ vẽ.
 *
 * Gắn vào khung tab qua `GAN_TAB['cc-ket-noi']` (01b-dieu-huong.js `ganKhe`).
 *
 * KHÔNG nằm trong vòng làm mới 6 giây: ô bí mật đang dán dở mà bị dựng lại
 * là khoá mất trắng, rồi người ta bấm Lưu và tưởng đã lưu. Chỉ dựng lại khi
 * người dùng thao tác (Lưu, Kiểm tra, Tải lại).
 */
window.GAN_TAB = window.GAN_TAB || {};

const KNTT_MAU = { thanh_cong: "xanh", loi: "do", chua_kiem_tra: "vang", chua_cau_hinh: "tat", tat: "tat" };

function knttCham(tt, nhan) {
  return `<span class="kn-cham kn-cham--${KNTT_MAU[tt] || "tat"}" title="${esc(nhan || "")}" aria-hidden="true"></span>`;
}

function knttLuc(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN") : "—";
}

/* Ô nhập của một trường. Ô BÍ MẬT là password và KHÔNG có value: máy chủ
 * chỉ gửi bốn ký tự cuối, nên mọi chữ trong ô là người dùng vừa gõ. */
function knttO(m) {
  const nhan = `${esc(m.nhan)}${m.y_nghia ? ` <em class="hint">${esc(m.y_nghia)}</em>` : ""}`;
  let o;
  if (m.chon && m.chon.length) {
    o = `<select data-kntt-khoa="${esc(m.khoa)}">${m.chon.map((c) =>
      `<option value="${esc(c)}"${c === m.hien ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  } else if (m.bi_mat) {
    o = `<input type="password" autocomplete="off" data-kntt-khoa="${esc(m.khoa)}"
      placeholder="${m.da_dat ? `đã đặt ${esc(m.hien)} — dán giá trị mới để thay` : "chưa đặt — dán vào đây"}">`;
  } else {
    o = `<input type="text" autocomplete="off" data-kntt-khoa="${esc(m.khoa)}" value="${esc(m.hien || "")}">`;
  }
  const nguon = { csdl: "lưu trên dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  const xoa = m.nguon === "csdl"
    ? ` <button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="${esc(m.khoa)}"
         title="Bỏ giá trị lưu trên dashboard, quay về .env">Bỏ, dùng .env</button>` : "";
  const sua = m.sua_boi ? ` · sửa bởi ${esc(m.sua_boi)} lúc ${esc(knttLuc(m.sua_luc))}` : "";
  return `<label class="field"><span>${nhan}</span>${o}</label>
    <span class="row__sub">${esc(nguon)}${sua}${xoa}</span>`;
}

function knttThongKe(tk) {
  if (!tk || !tk.lan_cuoi) return '<span class="row__sub">Chưa nhận lời gọi nào (trong 30 ngày).</span>';
  const loi = tk.loi_cuoi
    ? `<br><span class="row__sub">Lỗi gần nhất ${esc(knttLuc(tk.loi_cuoi.luc))}${
      tk.loi_cuoi.ma_http ? ` (HTTP ${esc(tk.loi_cuoi.ma_http)})` : ""}: ${esc(tk.loi_cuoi.loi || "")}</span>` : "";
  return `<span class="row__sub">Nhận gần nhất: ${esc(knttLuc(tk.lan_cuoi))} · 24 giờ: ${
    esc(tk.dem_24h ?? 0)} lời gọi, ${esc(tk.loi_24h ?? 0)} lỗi${
    tk.tb_ms != null ? ` · xử lý TB ${esc(tk.tb_ms)} ms` : ""}</span>${loi}`;
}

function knttKetQuaKiem(k) {
  if (!k) return '<span class="row__sub">Chưa kiểm lần nào.</span>';
  const cu = k.con_hieu_luc ? "" : " — <b>đã đổi cấu hình sau lần kiểm này</b>, bấm Kiểm tra lại";
  return `<span class="row__sub">Kiểm lần cuối ${esc(knttLuc(k.luc))}${k.boi ? ` bởi ${esc(k.boi)}` : ""}: ${
    k.ok ? "✓" : "✗"} ${esc(k.chi_tiet)}${cu}</span>`;
}

/* Thẻ dịch vụ dùng chung cho ERPNext/GHN/GHTK và cả thẻ AI (23-ai-co-ban.js). */
function knttTheDichVu(dv, { boTruong = false } = {}) {
  const wh = dv.webhook;
  const webhook = wh ? `
    <details class="kntt-webhook">
      <summary>Webhook nhận vào ${knttThongKeNgan(wh.thong_ke)}</summary>
      <p><code>${esc(wh.url)}</code></p>
      <p class="row__sub">${esc(wh.xac_minh)}</p>
      ${wh.bi_mat ? `<p class="row__sub">Bí mật URL: ${wh.bi_mat.da_dat ? "đã đặt " + esc(wh.bi_mat.hien)
        : "<b>CHƯA ĐẶT — mọi webhook đang bị từ chối</b>"}. ${esc(wh.lay_bi_mat || "")}</p>` : ""}
      <p class="row__sub">Sự kiện: ${wh.su_kien.map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}
      <div class="rowbtns"><button type="button" class="btn btn--sm" data-kntt-lswh="${esc(dv.ma)}">Lịch sử nhận</button></div>
      <div data-kntt-lswh-o="${esc(dv.ma)}"></div>
    </details>` : "";
  return `<section class="kntt-the" data-kntt-dv="${esc(dv.ma)}">
    <h3 class="kntt-the__dau">${dv.kiem_duoc ? knttCham(dv.trang_thai, dv.nhan_trang_thai) : ""}
      <b>${esc(dv.ten)}</b> ${dv.kiem_duoc ? `<span class="tag tag--${
        { thanh_cong: "auto", loi: "halt", chua_kiem_tra: "assist" }[dv.trang_thai] || "plain"}">${
        esc(dv.nhan_trang_thai)}</span>` : ""}</h3>
    <p class="row__sub">${esc(dv.mo_ta)}</p>
    ${dv.ghi_chu.map((g) => `<p class="row__sub kntt-ghichu">${esc(g)}</p>`).join("")}
    ${dv.thieu.length ? `<p class="row__sub"><b>Còn thiếu:</b> ${dv.thieu.map(esc).join(", ")}</p>` : ""}
    ${boTruong ? "" : `<div class="kntt-truong">${dv.truong.map(knttO).join("")}</div>`}
    <div class="rowbtns">
      ${dv.kiem_duoc ? `<button type="button" class="btn btn--sm" data-kntt-kiem="${esc(dv.ma)}">Kiểm tra kết nối</button>` : ""}
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="${esc(dv.ma)}">Lưu</button>
      <span class="row__sub" data-kntt-kq="${esc(dv.ma)}" aria-live="polite"></span>
    </div>
    ${dv.kiem_duoc ? knttKetQuaKiem(dv.kiem) : ""}
    ${webhook}
  </section>`;
}

function knttThongKeNgan(tk) {
  if (!tk || !tk.lan_cuoi) return '<span class="row__sub">— chưa nhận</span>';
  return `<span class="row__sub">— gần nhất ${esc(knttLuc(tk.lan_cuoi))}${
    tk.loi_24h ? `, <b>${esc(tk.loi_24h)} lỗi/24 giờ</b>` : ""}</span>`;
}

/* ---------------- plugin kênh ---------------- */

function knttTaiKhoan(p, t) {
  const wh = t.webhook || {};
  const fb = t.an_binh_luan_co_sdt
    ? `<label class="field kntt-fb"><span>Tự ẩn bình luận có số điện thoại</span>
        <select data-kntt-fb="${esc(t.id)}">
          <option value="chung"${t.an_binh_luan_co_sdt.rieng ? "" : " selected"}>Theo cấu hình chung (đang ${
            t.an_binh_luan_co_sdt.chung === "bat" ? "bật" : "tắt"})</option>
          <option value="bat"${t.an_binh_luan_co_sdt.rieng === "bat" ? " selected" : ""}>Bật cho Trang này</option>
          <option value="tat"${t.an_binh_luan_co_sdt.rieng === "tat" ? " selected" : ""}>Tắt cho Trang này</option>
        </select></label>` : "";
  const kiem = t.kiem
    ? `<span class="row__sub">Xác minh gần nhất ${esc(knttLuc(t.kiem.luc))}: ${esc(t.kiem.code || "")}${
      t.kiem.ly_do ? " — " + esc(t.kiem.ly_do) : ""}</span>` : '<span class="row__sub">Chưa xác minh lần nào.</span>';
  return `<div class="kn-dong kntt-tk">
    ${knttCham(t.trang_thai, t.nhan_trang_thai)}
    <span><b>${esc(t.display_name)}</b><small>${esc(t.nhan_trang_thai)} · ${esc(t.status)}</small></span>
    <span>${kiem}<br>${knttThongKe(wh)}${t.url_webhook ? `<br><span class="row__sub">Webhook: <code>${esc(t.url_webhook)}</code></span>` : ""}${fb}</span>
    <span class="rowbtns">
      ${p.ke_thua ? "" : `<button type="button" class="btn btn--sm" data-kntt-xacminh="${esc(t.id)}">Kiểm tra kết nối</button>`}
      <button type="button" class="btn btn--sm" data-kntt-bat="${esc(t.id)}" data-bat="${t.bat ? "0" : "1"}">${t.bat ? "Tắt" : "Bật"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-kntt-lstk="${esc(t.id)}">Lịch sử webhook</button>
    </span>
    <div class="kntt-lstk" data-kntt-lstk-o="${esc(t.id)}"></div>
  </div>`;
}

function knttPlugin(p) {
  const wh = p.webhook;
  return `<section class="kntt-the">
    <h3 class="kntt-the__dau"><b>${esc(p.ten)}</b>${p.ke_thua ? ' <span class="tag tag--plain">kênh cũ</span>' : ""}
      <span class="row__sub">${esc(p.tai_khoan.length)} tài khoản · nối: ${esc(p.cach_noi)}</span></h3>
    <p class="kntt-khanang">${p.kha_nang.map((k) =>
      `<span class="tag ${k.co ? "tag--auto" : "tag--plain"}" title="${k.co ? "Có" : "Chưa hỗ trợ"}">${k.co ? "✓" : "✗"} ${esc(k.nhan)}</span>`).join(" ")}</p>
    ${wh ? `<details class="kntt-webhook"><summary>Webhook ${knttThongKeNgan(wh.thong_ke)}</summary>
      ${wh.theo_tai_khoan ? '<p class="row__sub">Mỗi tài khoản một địa chỉ — xem ở từng dòng bên dưới.</p>'
        : `<p><code>${esc(wh.url)}</code></p>`}
      <p class="row__sub">${esc(wh.xac_minh)}</p>
      <p class="row__sub">Sự kiện: ${wh.su_kien.map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}</details>`
      : '<p class="row__sub">Không dùng webhook.</p>'}
    ${p.tai_khoan.length ? p.tai_khoan.map((t) => knttTaiKhoan(p, t)).join("")
      : '<p class="empty">Chưa nối tài khoản nào — nối ở màn Kết nối.</p>'}
  </section>`;
}

function knttLichSu(ls) {
  const HD = { dat: "đặt", xoa: "bỏ (về .env)", doi_credential: "đổi thông tin đăng nhập", bat: "bật",
    tat: "tắt", doi_tuy_chon: "đổi tuỳ chọn", tao: "tạo", xoa_tai_khoan: "xoá tài khoản" };
  if (!ls.length) return '<p class="empty">Chưa có thay đổi nào được ghi.</p>';
  return ls.map((x) => `<div class="row"><span class="row__flag row__flag--auto"></span>
    <span class="row__body"><span class="row__title">${esc(x.sua_boi)} ${esc(HD[x.hanh_dong] || x.hanh_dong)} ${
      esc(x.truong)}${x.bi_mat ? " (bí mật)" : ""}</span>
      <span class="row__sub">${esc(x.dich_vu)}${x.doi_tuong ? " · " + esc(x.doi_tuong) : ""}</span></span>
    <span class="row__side"><span class="row__time">${esc(knttLuc(x.sua_luc))}</span></span></div>`).join("");
}

function knttBangWebhook(d) {
  const goi = d.goi_vao.map((r) => `<tr><td>${esc(knttLuc(r.nhan_luc))}</td><td>${esc(r.phuong_thuc)}</td>
    <td>${esc(r.ma_http)}</td><td>${esc(r.thoi_gian_ms)} ms</td><td>${esc(r.loi || "")}</td></tr>`).join("");
  const tin = (d.tin_da_nhan || []).map((r) => `<tr><td>${esc(knttLuc(r.received_at))}</td><td>${esc(r.status)}</td>
    <td>${esc(r.attempts)}</td><td>${r.xu_ly_ms != null ? esc(r.xu_ly_ms) + " ms" : "—"}</td><td>${esc(r.last_error || "")}</td></tr>`).join("");
  return `<div class="kntt-bang">
    <p class="row__sub"><b>Lời gọi vào</b> (cả lời bị từ chối)</p>
    ${goi ? `<table><thead><tr><th>Lúc</th><th>PT</th><th>HTTP</th><th>Thời gian</th><th>Lỗi</th></tr></thead><tbody>${goi}</tbody></table>`
      : '<p class="empty">Chưa có lời gọi nào.</p>'}
    ${d.tin_da_nhan ? `<p class="row__sub"><b>Tin đã nhận vào hộp thư</b></p>
    ${tin ? `<table><thead><tr><th>Lúc</th><th>Trạng thái</th><th>Lần thử</th><th>Xử lý</th><th>Lỗi</th></tr></thead><tbody>${tin}</tbody></table>`
      : '<p class="empty">Chưa có tin nào.</p>'}` : ""}
  </div>`;
}

/* ---------------- gom giá trị, lưu, kiểm ---------------- */

/* Gom ô trong MỘT thẻ. `chiDaSua`: khi Lưu chỉ gửi ô người dùng đã đổi —
 * gửi cả ô có sẵn giá trị máy chủ là ghi lại y nguyên và đếm "đã lưu" sai. */
function knttGom(the, chiDaSua) {
  const ra = {};
  $$("[data-kntt-khoa]", the).forEach((o) => {
    if (o.closest("[hidden]")) return;
    if (chiDaSua && !_oDaSua(o)) return;
    const v = (o.value || "").trim();
    if (v) ra[o.dataset.knttKhoa] = v;
  });
  return ra;
}

async function knttLuu(the, ma, napLai) {
  const kq = the.querySelector(`[data-kntt-kq="${ma}"]`);
  const gia_tri = knttGom(the, true);
  if (!Object.keys(gia_tri).length) {
    toast("Chưa đổi ô nào — nhập giá trị rồi bấm Lưu.", true);
    return;
  }
  try {
    const r = await api(`/ket-noi/dich-vu/${encodeURIComponent(ma)}`, { method: "PUT", body: JSON.stringify({ gia_tri }) });
    if (r.hong.length) {
      const tb = `Lưu được ${r.da_luu.length}, hỏng ${r.hong.length}: ` + r.hong.map((h) => h.loi).join("; ");
      toast(tb, true);
      if (kq) kq.textContent = tb;
      // Ô ĐÃ lưu thì xoá chữ để không trông như chưa lưu; ô hỏng để nguyên cho sửa tiếp.
      r.da_luu.forEach((k) => { const o = the.querySelector(`input[type=password][data-kntt-khoa="${k}"]`); if (o) o.value = ""; });
      if (r.da_luu.length) await napLai();
      return;
    }
    toast(`Đã lưu ${r.da_luu.length} trường — có hiệu lực ngay. Bấm Kiểm tra kết nối để xác nhận.`);
    await napLai();
  } catch (e) { toast(e.message, true); }
}

async function knttKiem(the, ma, napLai) {
  const kq = the.querySelector(`[data-kntt-kq="${ma}"]`);
  if (kq) kq.textContent = "đang kiểm…";
  try {
    const r = await api(`/ket-noi/dich-vu/${encodeURIComponent(ma)}/kiem-tra`, {
      method: "POST", body: JSON.stringify({ gia_tri: knttGom(the, true) }),
    });
    const ghi = r.dung_gia_tri_luu ? "" : " (kiểm bằng giá trị CHƯA LƯU — kết quả không ghi vào trạng thái)";
    const tb = (r.ok ? "✓ " : "✗ ") + r.chi_tiet + ghi;
    if (r.dung_gia_tri_luu) {
      await napLai();
      const kqMoi = document.querySelector(`[data-kntt-kq="${ma}"]`);
      if (kqMoi) kqMoi.textContent = tb;
    } else if (kq) kq.textContent = tb;
  } catch (e) {
    if (kq) kq.textContent = "";
    toast(e.message, true);
  }
}

/* Gắn MỘT lần các bộ nghe sự kiện cho một gốc; `napLai` dựng lại nội dung. */
function knttGanSuKien(goc, napLai) {
  if (goc._knttDaGan) return;
  goc._knttDaGan = true;
  goc.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b || !goc.contains(b)) return;
    const the = b.closest("[data-kntt-dv]");
    try {
      if (b.dataset.knttLuu) return await knttLuu(the, b.dataset.knttLuu, napLai);
      if (b.dataset.knttKiem) return await knttKiem(the, b.dataset.knttKiem, napLai);
      if (b.dataset.knttXoa) {
        if (!confirm(`Bỏ giá trị ${b.dataset.knttXoa} lưu trên dashboard và quay về giá trị trong .env?`)) return;
        await api(`/ket-noi/dich-vu/${encodeURIComponent(the.dataset.knttDv)}/${encodeURIComponent(b.dataset.knttXoa)}`, { method: "DELETE" });
        toast("Đã bỏ — đang dùng .env");
        return await napLai();
      }
      if (b.dataset.knttLswh) {
        const o = goc.querySelector(`[data-kntt-lswh-o="${b.dataset.knttLswh}"]`);
        o.innerHTML = knttBangWebhook(await api(`/ket-noi/webhook?dich_vu=${encodeURIComponent(b.dataset.knttLswh)}`));
        return;
      }
      if (b.dataset.knttLstk) {
        const o = goc.querySelector(`[data-kntt-lstk-o="${b.dataset.knttLstk}"]`);
        o.innerHTML = knttBangWebhook(await api(`/ket-noi/webhook?account_id=${encodeURIComponent(b.dataset.knttLstk)}`));
        return;
      }
      if (b.dataset.knttXacminh) {
        b.disabled = true;
        const r = await api(`/channel-accounts/${b.dataset.knttXacminh}/verify`, { method: "POST" });
        toast(r.ok ? "Kết nối thành công" : `Kết nối lỗi: ${r.code}`, !r.ok);
        return await napLai();
      }
      if (b.dataset.knttBat) {
        const bat = b.dataset.bat === "1";
        if (!bat && !confirm("Tắt tài khoản kênh này? Tin khách gửi tới sẽ không vào hệ thống cho tới khi bật lại.")) return;
        await api(`/channel-accounts/${b.dataset.knttBat}/${bat ? "enable" : "disable"}`, { method: "POST" });
        toast(bat ? "Đã bật tài khoản kênh" : "Đã tắt tài khoản kênh");
        return await napLai();
      }
      if (b.dataset.knttTaiLai) return await napLai();
    } catch (err) {
      toast(err.message, true);
    } finally {
      if (b.dataset.knttXacminh) b.disabled = false;
    }
  });
  goc.addEventListener("change", async (e) => {
    const s = e.target.closest("[data-kntt-fb]");
    if (!s) return;
    try {
      await api(`/ket-noi/kenh/${s.dataset.knttFb}/tuy-chon`, {
        method: "PUT", body: JSON.stringify({ an_binh_luan_co_sdt: s.value }),
      });
      toast("Đã lưu tuỳ chọn ẩn bình luận cho Trang này");
    } catch (err) { toast(err.message, true); await napLai(); }
  });
}

async function ganKetNoiTichHop(goc) {
  if (!goc) return;
  const napLai = async () => {
    let d, ls;
    try {
      [d, ls] = await Promise.all([api("/ket-noi"), api("/ket-noi/lich-su?gioi_han=30")]);
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được Kết nối &amp; Tích hợp: ${esc(e.message)}</p>`;
      return;
    }
    goc.innerHTML = `
      <h2 class="panel__head">Kết nối &amp; Tích hợp
        <span class="panel__note">${d.vault_san_sang ? "bí mật mã hoá trong CSDL, chỉ hiện 4 ký tự cuối"
          : "vault chưa cấu hình — chỉ xem được"}</span></h2>
      <p class="panel__note">Mỗi dịch vụ một thẻ: cấu hình, kiểm tra kết nối thật, webhook nhận vào.
        Bấm <b>Kiểm tra kết nối</b> trước hoặc sau khi <b>Lưu</b> — kiểm chạy bằng đúng thứ bạn vừa gõ.
        <button type="button" class="btn btn--sm btn--ghost" data-kntt-tai-lai="1">Tải lại</button></p>
      <h3 class="kntt-nhom">Dịch vụ tích hợp</h3>
      ${d.dich_vu.map((dv) => knttTheDichVu(dv)).join("")}
      <h3 class="kntt-nhom">Kênh nhắn tin (plugin)</h3>
      ${d.kenh.map(knttPlugin).join("")}
      <h3 class="kntt-nhom">Lịch sử thay đổi cấu hình</h3>
      <p class="row__sub">Ai, lúc nào, trường nào — không bao giờ ghi giá trị.</p>
      <div class="rows">${knttLichSu(ls)}</div>`;
  };
  knttGanSuKien(goc, napLai);
  await napLai();
}

window.GAN_TAB["cc-ket-noi"] = (el) => ganKetNoiTichHop(el);

/* ---------------- Cấu hình AI cơ bản: nhà cung cấp, khoá, model, thông báo AI ----------------
 *
 * Gắn qua `GAN_TAB['ai-co-ban-nha-cung-cap']`. Dùng chung bộ Lưu / Kiểm tra
 * / Bỏ-về-.env của 22-ket-noi-tich-hop.js (`knttGanSuKien`): thẻ AI chỉ là
 * một dịch vụ nữa (`ai`) với cách vẽ ô riêng.
 *
 * Công tắc bật/tắt AI và chế độ Gợi ý/Tự động KHÔNG ở đây — chúng thuộc
 * khung "Cấu hình cơ bản" của màn AI Agent.
 */

function aiTruong(d, khoa) {
  return d.the.truong.find((m) => m.khoa === khoa) || { khoa, nhan: khoa, hien: "", nguon: "trong" };
}

function aiChonModel(d, m) {
  const co = Object.values(d.model_theo_ho).some((ds) => ds.includes(m.hien));
  const nhom = Object.entries(d.model_theo_ho).map(([ho, ds]) =>
    `<optgroup label="${esc({ gemini: "Gemini", claude: "Claude", gpt: "OpenAI GPT" }[ho] || ho)}">${
      ds.map((x) => `<option value="${esc(x)}"${x === m.hien ? " selected" : ""}>${esc(x)}</option>`).join("")}</optgroup>`).join("");
  const nguon = { csdl: "lưu trên dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  return `<label class="field"><span>${esc(m.nhan)} <em class="hint">${esc(d.model_dung_cho[m.khoa] || "")}</em></span>
    <select data-kntt-khoa="${esc(m.khoa)}">${co ? "" : `<option value="${esc(m.hien)}" selected>${esc(m.hien || "—")}</option>`}${nhom}</select></label>
    <span class="row__sub">${esc(nguon)}${m.nguon === "csdl"
      ? ` <button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="${esc(m.khoa)}">Bỏ, dùng .env</button>` : ""}</span>`;
}

/* Chỉ hiện ô khoá/endpoint của nhà cung cấp ĐANG CHỌN. Hiện cả ba là mời
 * người ta dán khoá Anthropic khi đang chạy Gemini: lưu đúng, kiểm đúng,
 * agent vẫn im — không có gì nổ để mà biết nhìn đâu. Ô bị ẩn được xoá chữ
 * để khoá cũ không lén đi theo lần Lưu sau. */
function aiHienTheoNhaCungCap(the, d) {
  const sel = the.querySelector('[data-kntt-khoa="LLM_PROVIDER"]');
  if (!sel) return;
  const ncc = d.nha_cung_cap.find((n) => n.ma === sel.value) || {};
  $$("[data-ai-khoa-cua]", the).forEach((dong) => {
    const an = dong.dataset.aiKhoaCua !== ncc.khoa && !(dong.dataset.aiKhoaCua === "OPENAI_BASE_URL" && ncc.endpoint);
    dong.hidden = an;
    if (an) $$("input[type=password]", dong).forEach((o) => { o.value = ""; });
  });
  const note = the.querySelector("[data-ai-ghichu]");
  if (note) note.textContent = ncc.ghi_chu || "";
}

function aiTheNhaCungCap(d) {
  const p = aiTruong(d, "LLM_PROVIDER");
  const the = d.the;
  const chon = `<label class="field"><span>Nhà cung cấp</span><select data-kntt-khoa="LLM_PROVIDER">${
    d.nha_cung_cap.map((n) => `<option value="${esc(n.ma)}"${n.ma === p.hien ? " selected" : ""}${
      n.ho_tro ? "" : " disabled"}>${esc(n.ten)}${n.ho_tro ? "" : " (chưa hỗ trợ)"}</option>`).join("")}</select></label>
    <p class="row__sub" data-ai-ghichu></p>`;
  const khoa = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"].map((k) =>
    `<div data-ai-khoa-cua="${k}">${knttO(aiTruong(d, k))}</div>`).join("");
  const canh = d.canh_bao.length
    ? `<div class="kntt-canhbao">${d.canh_bao.map((c) => `<p class="row__sub"><b>⚠ ${esc(c)}</b></p>`).join("")}</div>` : "";
  return `<section class="kntt-the" data-kntt-dv="ai">
    <h3 class="kntt-the__dau">${knttCham(the.trang_thai, the.nhan_trang_thai)} <b>Nhà cung cấp AI</b>
      <span class="tag tag--${{ thanh_cong: "auto", loi: "halt", chua_kiem_tra: "assist" }[the.trang_thai] || "plain"}">${
        esc(the.nhan_trang_thai)}</span></h3>
    ${the.thieu.length ? `<p class="row__sub"><b>Còn thiếu:</b> ${the.thieu.map(esc).join(", ")}</p>` : ""}
    ${canh}
    <div class="kntt-truong">${chon}${khoa}
      ${["MODEL_CHAT", "MODEL_HARD", "MODEL_CHEAP"].map((k) => aiChonModel(d, aiTruong(d, k))).join("")}</div>
    <div class="rowbtns">
      <button type="button" class="btn btn--sm" data-kntt-kiem="ai">Kiểm tra kết nối</button>
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="ai">Lưu</button>
      <span class="row__sub" data-kntt-kq="ai" aria-live="polite"></span>
    </div>
    ${knttKetQuaKiem(the.kiem)}
    <p class="row__sub">Đổi nhà cung cấp, khoá hay model có hiệu lực từ tin nhắn kế tiếp, không cần khởi động lại.</p>
  </section>`;
}

function aiTheThongBao(d) {
  const tb = d.thong_bao_ai;
  const bat = tb.the.truong.find((m) => m.khoa === "THONG_BAO_AI") || { hien: "bat" };
  const nd = tb.the.truong.find((m) => m.khoa === "TIN_THONG_BAO_AI") || { hien: tb.mac_dinh, nguon: "env" };
  return `<section class="kntt-the" data-kntt-dv="thong_bao_ai">
    <h3 class="kntt-the__dau"><b>Thông báo minh bạch AI</b>
      <span class="tag ${bat.hien === "tat" ? "tag--halt" : "tag--auto"}">${bat.hien === "tat" ? "Đang tắt" : "Đang bật"}</span></h3>
    <p class="row__sub">Báo khách đang nói với trợ lý AI và cách gặp nhân viên (NĐ 356/2025). ${esc(tb.chong_lap)}</p>
    <label class="field"><span>Gửi thông báo</span><select data-kntt-khoa="THONG_BAO_AI">
      <option value="bat"${bat.hien !== "tat" ? " selected" : ""}>Bật</option>
      <option value="tat"${bat.hien === "tat" ? " selected" : ""}>Tắt (bảng kiểm sẵn sàng sẽ cảnh báo)</option></select></label>
    <label class="field"><span>Nội dung <em class="hint">{ten} = tên thương hiệu. Phải có chữ "AI", một cụm gọi người
      trong ngoặc kép mà hệ thống nhận ra (vd "gặp nhân viên"), và nhắc dữ liệu da là nhạy cảm.</em></span>
      <textarea rows="4" maxlength="600" data-kntt-khoa="TIN_THONG_BAO_AI">${esc(nd.hien)}</textarea></label>
    <p class="row__sub">Khách sẽ đọc: “${esc(tb.xem_truoc)}”</p>
    <div class="rowbtns">
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="thong_bao_ai">Lưu</button>
      ${nd.nguon === "csdl" ? '<button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="TIN_THONG_BAO_AI">Về câu mặc định</button>' : ""}
      <span class="row__sub" data-kntt-kq="thong_bao_ai" aria-live="polite"></span>
    </div>
  </section>`;
}

async function ganAiCoBan(goc) {
  if (!goc) return;
  let duLieu = null;
  const napLai = async () => {
    try {
      duLieu = await api("/ket-noi/ai");
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được cấu hình AI: ${esc(e.message)}</p>`;
      return;
    }
    goc.innerHTML = `<h2 class="panel__head">Cấu hình AI cơ bản
        <span class="panel__note">${duLieu.vault_san_sang ? "khoá mã hoá trong CSDL, chỉ hiện 4 ký tự cuối"
          : "vault chưa cấu hình — chỉ xem được"}</span></h2>
      ${aiTheNhaCungCap(duLieu)}
      ${aiTheThongBao(duLieu)}`;
    aiHienTheoNhaCungCap(goc.querySelector('[data-kntt-dv="ai"]'), duLieu);
  };
  knttGanSuKien(goc, napLai);
  goc.addEventListener("change", (e) => {
    if (e.target.closest('[data-kntt-khoa="LLM_PROVIDER"]') && duLieu) {
      aiHienTheoNhaCungCap(goc.querySelector('[data-kntt-dv="ai"]'), duLieu);
    }
  });
  await napLai();
}

window.GAN_TAB["ai-co-ban-nha-cung-cap"] = (el) => ganAiCoBan(el);
/* ================= NHÂN SỰ & PHÂN QUYỀN (phiếu việc mục 12–13) =================
 *
 * Hai tab gắn vào khung tab của dashboard:
 *
 *   GAN_TAB["ns-nhan-vien"](el)  tài khoản, thông tin, trạng thái, vai trò,
 *                                khoá kèm chuyển việc
 *   GAN_TAB["ns-vai-tro"](el)    vai trò: tạo, sửa, ngừng dùng, cấp quyền
 *                                theo nhóm chức năng; lịch sử đổi quyền
 *
 * Màn "Nhân sự" cũ (09-nhan-su.js) dùng CHUNG các hàm ở đây cho ba việc
 * khó làm đúng hai lần: bảng tick quyền theo nhóm, khoá kèm chuyển việc,
 * và lịch sử. Hai bản chép là hai chỗ để một luật lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ. Ẩn nút theo quyền chỉ để màn hình
 * không mời một 403 mỗi lần bấm — không phải để bảo vệ gì.
 */
window.GAN_TAB = window.GAN_TAB || {};

const nsv = { nguoi: [], vaiTro: [], nhom: [] };

function nsvCo(quyen) {
  return !!(state.toiQuyen && state.toiQuyen.has(quyen));
}

async function nsvTaiDuLieu() {
  const [nd, vt, dm] = await Promise.all([
    api("/nguoi-dung"), api("/vai-tro"), api("/quyen"),
  ]);
  nsv.nguoi = nd.nguoi_dung || [];
  nsv.vaiTro = vt.vai_tro || [];
  nsv.nhom = dm.nhom_hien_thi || [];
}

/* Nhãn tiếng Việt của một mã quyền — lịch sử lưu MÃ (bền qua các lần đổi
   nhãn), màn hình hiện NHÃN (người đọc không thuộc mã). */
function nsvNhanQuyen(ma) {
  for (const g of nsv.nhom) {
    const q = g.quyen.find((x) => x.ma === ma);
    if (q) return q.nhan;
  }
  return ma;
}

function nsvNgay(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  }) : "—";
}

/* ---------------- dùng chung: bảng tick quyền theo nhóm ---------------- */

/* Nhóm theo CHỨC NĂNG dashboard (máy chủ trả `nhom_hien_thi`, đúng thứ tự
   phiếu việc), không theo tiền tố mã. `khoa` cho vai trò Quản trị: nó lấy
   quyền từ mã, tick/bỏ tick ở đó không có tác dụng gì. */
function nsvBangQuyen(dangCo, khoa = false) {
  const co = new Set(dangCo || []);
  if (!nsv.nhom.length) return '<p class="empty">Chưa tải được danh mục quyền.</p>';
  return nsv.nhom.map((g) => `
    <fieldset class="quyen__nhom">
      <legend>${esc(g.ten)}${khoa ? "" : ` <button type="button" class="btn btn--sm btn--ghost"
        data-nsv-ca-nhom="${esc(g.ma)}">chọn / bỏ cả nhóm</button>`}</legend>
      ${g.quyen.map((q) => `<label class="quyen__o">
        <input type="checkbox" name="quyen" value="${esc(q.ma)}"${co.has(q.ma) ? " checked" : ""}${khoa ? " disabled" : ""}>
        <span>${esc(q.nhan)}</span><code>${esc(q.ma)}</code>
      </label>`).join("")}
    </fieldset>`).join("");
}

document.addEventListener("click", (e) => {
  const nut = e.target.closest("[data-nsv-ca-nhom]");
  if (!nut) return;
  const o = $$('input[name="quyen"]:not(:disabled)', nut.closest("fieldset"));
  const batHet = o.some((i) => !i.checked);
  o.forEach((i) => { i.checked = batHet; });
});

/* ---------------- dùng chung: lịch sử ---------------- */

function nsvPill(ds, dau, lop) {
  return (ds || []).map((x) =>
    `<span class="pill${lop ? " " + lop : ""}">${dau} ${esc(nsvNhanQuyen(x))}</span>`).join(" ");
}

function nsvDongLichSu(d) {
  const ct = d.chi_tiet || {};
  const doiTuong = ct.ten || ct.ten_dang_nhap || ct.ten_moi || "";
  const truoc = ct.truoc || {};
  const sau = ct.sau || {};
  let them = "";
  if (d.loai === "nguoi_dung.vai_tro") {
    // Vai trò thêm/bớt, rồi QUYỀN HIỆU LỰC được/mất — vai trò khác cũng cấp
    // thì không tính là mất (mục 13.6).
    them = [nsvPill(ct.them, "+ vai trò", ""), nsvPill(ct.bot, "− vai trò", "pill--warn"),
            nsvPill(ct.quyen_them, "+", ""), nsvPill(ct.quyen_bot, "−", "pill--warn")]
      .filter(Boolean).join(" ");
  } else if (d.loai === "nguoi_dung.sua") {
    them = ["ho_ten", "email"].filter((k) => truoc[k] !== sau[k]).map((k) =>
      `<span class="pill">${k === "ho_ten" ? "Họ tên" : "Email"}: ${esc(truoc[k] || "—")} → ${esc(sau[k] || "—")}</span>`).join(" ");
  } else if (d.loai === "auth.khoa_nguoi_dung") {
    them = `<span class="pill${sau.khoa ? " pill--warn" : ""}">${sau.khoa ? "Khoá" : "Mở khoá"}</span>`
      + (ct.de_lai_viec ? ` <span class="pill pill--warn">để lại ${ct.de_lai_viec.so_hoi_thoai} hội thoại, ${ct.de_lai_viec.so_cong_viec} việc</span>` : "");
  } else if (d.loai === "nguoi_dung.chuyen_viec") {
    them = `<span class="pill">${ct.so_hoi_thoai || 0} hội thoại, ${ct.so_cong_viec || 0} việc → ${esc(sau.nguoi || "")}</span>`
      + (ct.khong_chuyen_duoc ? ` <span class="pill pill--warn">${ct.khong_chuyen_duoc} hội thoại không chuyển được</span>` : "");
  } else {
    if (truoc.ten && sau.ten && truoc.ten !== sau.ten) {
      them += `<span class="pill">Tên: ${esc(truoc.ten)} → ${esc(sau.ten)}</span> `;
    }
    them += [nsvPill(ct.them, "+", ""), nsvPill(ct.bot, "−", "pill--warn")].filter(Boolean).join(" ");
    if (ct.nguoi_anh_huong && ct.nguoi_anh_huong.length) {
      them += ` <span class="pill">ảnh hưởng: ${esc(ct.nguoi_anh_huong.join(", "))}</span>`;
    } else if (ct.so_nguoi_anh_huong) {
      them += ` <span class="pill">${ct.so_nguoi_anh_huong} người đang mang</span>`;
    }
  }
  return `<div class="row">
    <span class="row__flag row__flag--${(ct.bot || []).length || sau.khoa ? "assist" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(d.nhan)}${doiTuong ? ": " + esc(doiTuong) : ""}</b>
      <span class="row__sub">bởi ${esc(d.nguoi_lam)} · ${nsvNgay(d.luc)}</span>
      ${them ? `<div class="nsv-doi">${them}</div>` : ""}
    </div>
  </div>`;
}

async function nsvVeLichSu(el, loai = "tat_ca") {
  if (!el) return;
  try {
    const d = await api(`/nhan-su/lich-su?loai=${encodeURIComponent(loai)}&limit=60`);
    el.innerHTML = d.lich_su.length
      ? d.lich_su.map(nsvDongLichSu).join("")
      : '<p class="empty">Chưa có thay đổi nào về nhân sự hay phân quyền.</p>';
  } catch (err) {
    el.innerHTML = `<p class="empty">Không tải được lịch sử: ${esc(err.message)}</p>`;
  }
}

/* ---------------- dùng chung: khoá kèm chuyển việc (mục 13.8) ---------------- */

/* Hỏi chuyển việc cho AI. Trả null nếu người dùng thôi, `{deLai: true}` nếu
   chọn để lại việc (chỉ khi đang khoá), hoặc kết quả của máy chủ. */
async function nsvHoiChuyenViec(n, viec, khiKhoa) {
  if (!nsv.nguoi.length) await nsvTaiDuLieu();
  const ten = n.ho_ten || n.ten_dang_nhap;
  const nguoiNhan = nsv.nguoi.filter((x) => !x.khoa && x.id !== n.id);
  const lietKe = [
    ...viec.hoi_thoai.slice(0, 3).map((h) => `hội thoại với ${h.khach || "khách"}`),
    ...viec.cong_viec.slice(0, 3).map((v) => `việc “${v.tieu_de}”`),
  ].join("; ");
  const d = await hoiHop({
    tieu_de: khiKhoa ? `Khoá ${ten}: chuyển việc trước` : `Chuyển việc của ${ten}`,
    phu: `${ten} đang giữ ${viec.so_hoi_thoai} hội thoại và ${viec.so_cong_viec} việc chưa xong`
      + (lietKe ? ` (${lietKe}${viec.tong > 6 ? "…" : ""})` : "")
      + ". Khoá mà không chuyển là khách của họ chờ mà không ai trả lời.",
    truong: [{
      name: "nguoi_nhan", label: "Chuyển cho", type: "select", required: true,
      value: nguoiNhan.length ? nguoiNhan[0].id : "",
      options: [
        ...nguoiNhan.map((x) => ({ value: x.id, label: `${x.ho_ten || x.ten_dang_nhap} (${x.ten_dang_nhap})` })),
        ...(khiKhoa ? [{ value: "__de_lai__", label: "Không chuyển — khoá và để lại việc (khách có thể phải chờ)" }] : []),
      ],
    }],
    nut: khiKhoa ? "Chuyển rồi khoá" : "Chuyển việc",
    nguy_hiem: !!khiKhoa,
  });
  if (!d || !d.nguoi_nhan) return null;
  if (d.nguoi_nhan === "__de_lai__") return { deLai: true };
  try {
    const kq = await api(`/nguoi-dung/${n.id}/chuyen-viec`, {
      method: "POST",
      body: JSON.stringify({
        nguoi_nhan: d.nguoi_nhan,
        hoi_thoai: viec.so_hoi_thoai > 0,
        cong_viec: viec.so_cong_viec > 0,
      }),
    });
    toast(`Đã chuyển ${kq.so_hoi_thoai} hội thoại và ${kq.so_cong_viec} việc cho ${kq.nguoi_nhan}.`);
    return kq;
  } catch (err) {
    toast(err.message, true);
    return null;
  }
}

/* Khoá / mở khoá. Khoá thì HỎI VỀ VIỆC ĐANG GIỮ trước — máy chủ cũng chặn
   (409 `can_chuyen_viec`) nên gọi thẳng API hay màn cũ đều gặp cùng câu hỏi.
   Lời xác nhận nói điều sẽ xảy ra: phiên đang mở bị đá ra ngay. */
async function nsvKhoa(n, xong) {
  const ten = n.ten_dang_nhap;
  const goi = (khoa, boQua) => api(
    `/nguoi-dung/${encodeURIComponent(ten)}/khoa?khoa=${khoa}${boQua ? "&bo_qua_viec=true" : ""}`,
    { method: "POST" });
  if (n.khoa) {
    if (!confirm(`Mở khoá “${ten}”? Họ đăng nhập lại được ngay.`)) return;
    try { await goi(false); toast(`Đã mở khoá ${ten}.`); } catch (err) { toast(err.message, true); }
    if (xong) await xong();
    return;
  }
  let viec;
  try { viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`); } catch (err) { toast(err.message, true); return; }
  let boQua = false;
  if (viec.tong) {
    const kq = await nsvHoiChuyenViec(n, viec, true);
    if (!kq) return;
    if (kq.deLai) {
      boQua = true;
    } else if (kq.khong_chuyen_duoc && kq.khong_chuyen_duoc.length) {
      const lyDo = kq.khong_chuyen_duoc.map((x) => `${x.khach || "khách"}: ${x.ly_do}`).join("; ");
      if (!confirm(`${kq.khong_chuyen_duoc.length} hội thoại KHÔNG chuyển được (${lyDo}). `
        + `Vẫn khoá “${ten}” và để lại các hội thoại ấy?`)) { if (xong) await xong(); return; }
      boQua = true;
    }
    if (!confirm(`Khoá “${ten}”? Mọi phiên đang mở của họ bị đá ra ngay lập tức.`)) { if (xong) await xong(); return; }
  } else if (!confirm(`Khoá “${ten}”? Mọi phiên đang mở của họ bị đá ra ngay lập tức.`)) {
    return;
  }
  try {
    await goi(true, boQua);
    toast(`Đã khoá ${ten} và đá mọi phiên.`);
  } catch (err) {
    toast(err.message, true);
    // Ai đó vừa giao thêm việc cho người này giữa lúc đang hỏi: hỏi lại.
    if (err.chi_tiet && err.chi_tiet.can_chuyen_viec) return nsvKhoa(n, xong);
  }
  if (xong) await xong();
}

/* ======================== TAB "NHÂN VIÊN" ======================== */

function nsvDongNguoi(n) {
  const sua = nsvCo("nguoi_dung.sua");
  const vai = (n.vai_tro_ten || []).map((t) => `<span class="pill">${esc(t)}</span>`).join(" ")
    + (n.vai_tro_ngung || []).map((t) =>
      ` <span class="pill pill--warn" title="Vai trò đã ngừng dùng — không cấp quyền nào">${esc(t)} · ngừng dùng</span>`).join("")
    || '<span class="pill pill--warn">chưa có vai trò nào</span>';
  const giu = Number(n.so_hoi_thoai_giu || 0);
  const viec = Number(n.so_viec_chua_xong || 0);
  const ganViec = giu || viec
    ? ` <span class="pill${n.khoa ? " pill--warn" : ""}">giữ ${giu} hội thoại · ${viec} việc</span>` : "";
  return `<div class="row">
    <span class="row__flag row__flag--${n.khoa ? "halt" : (n.vai_tro_ten || []).length ? "auto" : "assist"}"></span>
    <div class="row__main">
      <b>${esc(n.ho_ten || n.ten_dang_nhap)}</b>
      <span class="tag tag--${n.khoa ? "halt" : "auto"}">${n.khoa ? "Đã khoá" : "Đang làm"}</span>
      <span class="row__sub">${esc(n.ten_dang_nhap)}${n.email ? " · " + esc(n.email) : ""}
        · tạo ${nsvNgay(n.tao_luc)}
        · ${n.dang_nhap_cuoi ? "vào lần cuối " + nsvNgay(n.dang_nhap_cuoi) : "chưa đăng nhập lần nào"}</span>
    </div>
    <div class="row__side">
      <span>${vai}${ganViec}</span>
      <span class="row__nut">
        <button type="button" class="btn btn--sm btn--ghost" data-nsv-quyen="${esc(n.id)}">Quyền</button>
        ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-sua="${esc(n.id)}">Sửa</button>
        ${giu || viec ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-chuyen="${esc(n.id)}">Chuyển việc</button>` : ""}
        <button type="button" class="btn btn--sm ${n.khoa ? "btn--ghost" : "btn--halt"}" data-nsv-khoa="${esc(n.id)}">${n.khoa ? "Mở khoá" : "Khoá"}</button>` : ""}
      </span>
    </div>
  </div>`;
}

/* Form thêm/sửa — MỘT form cho cả hai, vai trò là ô TICK (một người nhiều
   vai trò). Vai trò đã ngừng dùng: người đang mang thì vẫn hiện đã tick
   (gỡ được), người chưa mang thì khoá — máy chủ cũng từ chối gán mới. */
function nsvFormNguoi(n) {
  const moi = !n;
  const dangCo = new Set(n ? n.vai_tro_id || [] : []);
  return `<form class="form" data-nsv-form-nguoi="${moi ? "" : esc(n.id)}">
    <h3 class="panel__head">${moi ? "Thêm nhân viên" : `Sửa ${esc(n.ho_ten || n.ten_dang_nhap)}`}</h3>
    <div class="form__row">
      ${moi ? `<label class="field"><span>Tên đăng nhập</span>
        <input name="ten_dang_nhap" required minlength="3" maxlength="64" autocomplete="off" placeholder="lan.nv"></label>`
        : `<label class="field"><span>Tên đăng nhập <em class="hint">không đổi được — nhật ký cũ trỏ vào nó</em></span>
        <input value="${esc(n.ten_dang_nhap)}" disabled></label>`}
      <label class="field"><span>Họ tên</span>
        <input name="ho_ten" required maxlength="120" value="${esc(n ? n.ho_ten : "")}" autocomplete="off"></label>
    </div>
    <div class="form__row">
      <label class="field"><span>Email <em class="hint">không bắt buộc</em></span>
        <input name="email" type="email" maxlength="200" value="${esc(n ? n.email || "" : "")}" autocomplete="off"></label>
      ${moi ? `<label class="field"><span>Mật khẩu ban đầu</span>
        <input name="mat_khau" type="password" autocomplete="new-password" minlength="8" required></label>` : ""}
    </div>
    <fieldset class="quyen__nhom"><legend>Vai trò <em class="hint">quyền = hợp quyền mọi vai trò đang dùng</em></legend>
      ${nsv.vaiTro.map((v) => `<label class="quyen__o">
        <input type="checkbox" name="vai_tro" value="${esc(v.id)}"${dangCo.has(v.id) ? " checked" : ""}${
          !v.dang_dung && !dangCo.has(v.id) ? " disabled" : ""}>
        <span>${esc(v.ten)}${v.dang_dung ? "" : " · ngừng dùng"}</span>
        <small>${esc(v.mo_ta || "")}</small></label>`).join("")}
    </fieldset>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">${moi ? "Tạo tài khoản" : "Lưu"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-huy-form>Huỷ</button>
    </div>
  </form>`;
}

async function nsvLuuNguoi(f) {
  const id = f.dataset.nsvFormNguoi;
  const d = Object.fromEntries(new FormData(f).entries());
  const vai = $$('input[name="vai_tro"]:checked', f).map((i) => i.value);
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    if (!id) {
      await api("/nguoi-dung", {
        method: "POST",
        body: JSON.stringify({
          ten_dang_nhap: String(d.ten_dang_nhap || "").trim(),
          mat_khau: d.mat_khau, ho_ten: String(d.ho_ten || "").trim(),
          email: String(d.email || "").trim() || null, vai_tro_ids: vai,
        }),
      });
      toast(vai.length ? "Đã tạo tài khoản và cấp vai trò. Báo họ đổi mật khẩu ở mục Tôi."
        : "Đã tạo. Chưa có vai trò nên họ vào được mà mọi màn đều trống.");
    } else {
      await api(`/nguoi-dung/${id}`, {
        method: "PUT",
        body: JSON.stringify({ ho_ten: String(d.ho_ten || "").trim(),
                               email: String(d.email || "").trim() || null }),
      });
      const cu = (nsv.nguoi.find((x) => x.id === id) || {}).vai_tro_id || [];
      if ([...cu].sort().join() !== [...vai].sort().join()) {
        await api(`/nguoi-dung/${id}/vai-tro`, { method: "PUT", body: JSON.stringify({ vai_tro: vai }) });
      }
      toast("Đã lưu.");
    }
    return true;
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
    return false;
  }
}

/* Quyền THỰC TẾ của một người, theo nhóm chức năng, kèm vai trò nào cấp. */
function nsvVeQuyenNguoi(d) {
  const co = d.quyen || {};
  const nhom = nsv.nhom.map((g) => {
    const dong = g.quyen.filter((q) => co[q.ma]);
    return dong.length ? `<fieldset class="quyen__nhom"><legend>${esc(g.ten)}</legend>${
      dong.map((q) => `<div class="quyen__o"><span>${esc(q.nhan)}</span>
        <small>cấp bởi: ${esc(co[q.ma].join(", "))}</small></div>`).join("")}</fieldset>` : "";
  }).join("");
  return `<div class="ns-vaitro" data-nsv-xem-quyen>
    ${nhom || '<p class="empty">Chưa được cấp quyền nào. Người này đăng nhập được nhưng mọi màn đều trống.</p>'}
    ${(d.vai_tro_ngung || []).length ? `<p class="panel__note">Vai trò đã ngừng dùng (không cấp gì): ${esc(d.vai_tro_ngung.join(", "))}</p>` : ""}
    <div class="row__nut"><button type="button" class="btn btn--sm btn--ghost" data-nsv-dong>Đóng</button></div>
  </div>`;
}

async function nsvVeNhanVien(el) {
  await nsvTaiDuLieu();
  const ds = nsv.nguoi;
  const dangLam = ds.filter((n) => !n.khoa).length;
  const chuaVai = ds.filter((n) => !(n.vai_tro_ten || []).length).length;
  const dem = el.querySelector("[data-nsv-dem]");
  if (dem) {
    dem.textContent = [`${ds.length} tài khoản`, `${dangLam} đang làm`,
      ds.length - dangLam ? `${ds.length - dangLam} đã khoá` : "",
      chuaVai ? `${chuaVai} chưa có vai trò` : ""].filter(Boolean).join(" · ");
  }
  el.querySelector("[data-nsv-ds]").innerHTML = ds.length
    ? ds.map(nsvDongNguoi).join("") : '<p class="empty">Chưa có nhân viên nào.</p>';
}

GAN_TAB["ns-nhan-vien"] = async (el) => {
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Nhân viên <span class="panel__note" data-nsv-dem>đang tải…</span>
      ${nsvCo("nguoi_dung.sua") ? '<button type="button" class="btn btn--sm" data-nsv-them>Thêm nhân viên</button>' : ""}</h2>
    <div data-nsv-khung-form></div>
    <div class="rows" data-nsv-ds><p class="empty">Đang tải…</p></div>
  </section>`;
  if (!el.dataset.nsvGan) {
    el.dataset.nsvGan = "1";
    el.addEventListener("click", async (e) => {
      const tim = (k) => e.target.closest(`[${k}]`);
      const nguoiTheoId = (id) => nsv.nguoi.find((x) => x.id === id);
      const khung = el.querySelector("[data-nsv-khung-form]");
      if (tim("data-nsv-them")) {
        khung.innerHTML = nsvFormNguoi(null);
        khung.querySelector("input").focus();
      } else if (tim("data-nsv-sua")) {
        khung.innerHTML = nsvFormNguoi(nguoiTheoId(tim("data-nsv-sua").dataset.nsvSua));
        khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (tim("data-nsv-huy-form")) {
        khung.innerHTML = "";
      } else if (tim("data-nsv-khoa")) {
        await nsvKhoa(nguoiTheoId(tim("data-nsv-khoa").dataset.nsvKhoa), () => nsvVeNhanVien(el));
      } else if (tim("data-nsv-chuyen")) {
        const n = nguoiTheoId(tim("data-nsv-chuyen").dataset.nsvChuyen);
        try {
          const viec = await api(`/nguoi-dung/${n.id}/viec-dang-giu`);
          if (!viec.tong) { toast("Người này không còn giữ việc nào."); return; }
          await nsvHoiChuyenViec(n, viec, false);
        } catch (err) { toast(err.message, true); }
        await nsvVeNhanVien(el);
      } else if (tim("data-nsv-quyen")) {
        $$("[data-nsv-xem-quyen]", el).forEach((b) => b.remove());
        const nut = tim("data-nsv-quyen");
        try {
          const d = await api(`/nguoi-dung/${nut.dataset.nsvQuyen}/quyen`);
          nut.closest(".row").insertAdjacentHTML("afterend", nsvVeQuyenNguoi(d));
        } catch (err) { toast(err.message, true); }
      } else if (tim("data-nsv-dong")) {
        tim("data-nsv-dong").closest("[data-nsv-xem-quyen]").remove();
      }
    });
    el.addEventListener("submit", async (e) => {
      const f = e.target.closest("[data-nsv-form-nguoi]");
      if (!f) return;
      e.preventDefault();
      if (await nsvLuuNguoi(f)) {
        el.querySelector("[data-nsv-khung-form]").innerHTML = "";
        await nsvVeNhanVien(el);
      }
    });
  }
  try { await nsvVeNhanVien(el); } catch (err) {
    el.querySelector("[data-nsv-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};

/* ======================== TAB "VAI TRÒ & QUYỀN" ======================== */

function nsvDongVaiTro(v) {
  const sua = nsvCo("nguoi_dung.sua");
  const soQuyen = v.toan_quyen ? "toàn bộ quyền (lấy từ mã)" : `${v.quyen.length} quyền`;
  /* Nút Xoá chỉ hiện khi máy chủ sẽ cho xoá (`xoa_duoc`): vai trò từng có
     người mang chỉ NGỪNG DÙNG được — nút bấm vào rồi mới báo 409 dạy người
     ta rằng lỗi là chuyện bình thường. */
  const nut = !sua ? "" : [
    v.toan_quyen ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-nsv-sua-vai="${esc(v.id)}">Sửa quyền</button>`,
    v.he_thong ? "" : `<button type="button" class="btn btn--sm btn--ghost" data-nsv-trang-thai="${esc(v.id)}">${v.dang_dung ? "Ngừng dùng" : "Dùng lại"}</button>`,
    v.xoa_duoc ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-xoa-vai="${esc(v.id)}">Xoá</button>` : "",
  ].join("");
  return `<div class="row">
    <span class="row__flag row__flag--${!v.dang_dung ? "plain" : v.toan_quyen ? "halt" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(v.ten)}${v.he_thong ? ' <span class="pill">dựng sẵn</span>' : ""}${
        v.dang_dung ? "" : ' <span class="tag tag--plain">ngừng dùng</span>'}</b>
      <span class="row__sub">${esc(v.mo_ta || "—")}</span>
    </div>
    <div class="row__side">
      <span><span class="pill">${soQuyen}</span> <span class="pill">${v.so_nguoi} người</span></span>
      ${nut ? `<span class="row__nut">${nut}</span>` : ""}
    </div>
  </div>`;
}

function nsvFormVaiTro(v) {
  return `<form class="form" data-nsv-form-vai="${v ? esc(v.id) : ""}">
    <h3 class="panel__head">${v ? `Sửa vai trò “${esc(v.ten)}”` : "Tạo vai trò mới"}</h3>
    <label class="field"><span>Tên vai trò</span>
      <input name="ten" required maxlength="80" value="${esc(v ? v.ten : "")}" placeholder="Trưởng nhóm CSKH" autocomplete="off"></label>
    <label class="field"><span>Mô tả <em class="hint">để người sau hiểu vai trò này dành cho ai</em></span>
      <input name="mo_ta" maxlength="500" value="${esc(v ? v.mo_ta : "")}" autocomplete="off"></label>
    ${v && v.so_nguoi ? `<p class="panel__note">Lưu là ${v.so_nguoi} người đang mang vai trò này đổi quyền NGAY ở thao tác kế tiếp của họ.</p>` : ""}
    <div class="quyen">${nsvBangQuyen(v ? v.quyen : [])}</div>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">Lưu vai trò</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-huy-vai>Huỷ</button>
    </div>
  </form>`;
}

async function nsvVeVaiTro(el) {
  await nsvTaiDuLieu();
  el.querySelector("[data-nsv-vai-ds]").innerHTML = nsv.vaiTro.map(nsvDongVaiTro).join("");
  await nsvVeLichSu(el.querySelector("[data-nsv-lich-su]"),
                    el.querySelector("[data-nsv-loc-lich-su]")?.value || "tat_ca");
}

/* Ngừng dùng / dùng lại — nói SỐ NGƯỜI bị ảnh hưởng, không hỏi "có chắc
   không": câu ấy không mang thông tin, người ta bấm OK theo phản xạ. */
async function nsvDoiTrangThaiVai(v) {
  const loi = v.dang_dung
    ? `Ngừng dùng “${v.ten}”? ${v.so_nguoi} người đang mang nó mất các quyền này NGAY `
      + "(trừ quyền vai trò khác của họ cũng cấp). Vai trò vẫn nằm trong lịch sử và dùng lại được."
    : `Dùng lại “${v.ten}”? ${v.so_nguoi} người đang mang nó có lại các quyền này ngay.`;
  if (!confirm(loi)) return false;
  try {
    await api(`/vai-tro/${v.id}/trang-thai`, { method: "POST", body: JSON.stringify({ dang_dung: !v.dang_dung }) });
    toast(v.dang_dung ? "Đã ngừng dùng vai trò." : "Đã dùng lại vai trò.");
    return true;
  } catch (err) { toast(err.message, true); return false; }
}

GAN_TAB["ns-vai-tro"] = async (el) => {
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Vai trò &amp; Quyền
      <span class="panel__note">quyền của một người = hợp quyền mọi vai trò ĐANG DÙNG họ mang · sửa vai trò là mọi người mang nó đổi theo ngay</span>
      ${nsvCo("nguoi_dung.sua") ? '<button type="button" class="btn btn--sm" data-nsv-tao-vai>Tạo vai trò</button>' : ""}</h2>
    <div data-nsv-khung-vai></div>
    <div class="rows" data-nsv-vai-ds><p class="empty">Đang tải…</p></div>
  </section>
  <section class="panel">
    <h2 class="panel__head">Lịch sử nhân sự &amp; phân quyền
      <span class="panel__note">ai đổi gì, lúc nào — trước và sau</span>
      <select data-nsv-loc-lich-su>
        <option value="tat_ca">Tất cả</option>
        <option value="vai_tro">Vai trò &amp; quyền</option>
        <option value="nguoi_dung">Tài khoản nhân viên</option>
      </select></h2>
    <div class="rows" data-nsv-lich-su><p class="empty">Đang tải…</p></div>
  </section>`;
  if (!el.dataset.nsvGan) {
    el.dataset.nsvGan = "1";
    el.addEventListener("click", async (e) => {
      const tim = (k) => e.target.closest(`[${k}]`);
      const vaiTheoId = (id) => nsv.vaiTro.find((x) => x.id === id);
      const khung = el.querySelector("[data-nsv-khung-vai]");
      if (tim("data-nsv-tao-vai")) {
        khung.innerHTML = nsvFormVaiTro(null);
      } else if (tim("data-nsv-sua-vai")) {
        khung.innerHTML = nsvFormVaiTro(vaiTheoId(tim("data-nsv-sua-vai").dataset.nsvSuaVai));
        khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else if (tim("data-nsv-huy-vai")) {
        khung.innerHTML = "";
      } else if (tim("data-nsv-trang-thai")) {
        if (await nsvDoiTrangThaiVai(vaiTheoId(tim("data-nsv-trang-thai").dataset.nsvTrangThai))) {
          await nsvVeVaiTro(el);
        }
      } else if (tim("data-nsv-xoa-vai")) {
        const v = vaiTheoId(tim("data-nsv-xoa-vai").dataset.nsvXoaVai);
        if (!confirm(`Xoá hẳn vai trò “${v.ten}”? Chưa ai từng được gán vai trò này nên không mất lịch sử nào.`)) return;
        try {
          await api(`/vai-tro/${v.id}`, { method: "DELETE" });
          toast("Đã xoá vai trò.");
          await nsvVeVaiTro(el);
        } catch (err) { toast(err.message, true); }
      }
    });
    el.addEventListener("change", (e) => {
      if (e.target.closest("[data-nsv-loc-lich-su]")) {
        nsvVeLichSu(el.querySelector("[data-nsv-lich-su]"), e.target.value);
      }
    });
    el.addEventListener("submit", async (e) => {
      const f = e.target.closest("[data-nsv-form-vai]");
      if (!f) return;
      e.preventDefault();
      const id = f.dataset.nsvFormVai;
      const than = {
        ten: f.ten.value.trim(), mo_ta: f.mo_ta.value.trim(),
        quyen: $$('input[name="quyen"]:checked', f).map((i) => i.value),
      };
      try {
        await api(id ? `/vai-tro/${id}` : "/vai-tro",
                  { method: id ? "PUT" : "POST", body: JSON.stringify(than) });
        toast(id ? "Đã lưu vai trò." : "Đã tạo vai trò.");
        el.querySelector("[data-nsv-khung-vai]").innerHTML = "";
        await nsvVeVaiTro(el);
      } catch (err) { toast(err.message, true); }
    });
  }
  try { await nsvVeVaiTro(el); } catch (err) {
    el.querySelector("[data-nsv-vai-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};
/* ================= CÔNG VIỆC (phiếu việc mục 14) =================
 *
 * Hai điểm gắn vào khung tab (01b-dieu-huong.js `ganKhe`):
 *
 *   GAN_TAB["cv-danh-sach"]     Danh sách công việc: xem, tạo, tìm, lọc,
 *                               giao, chuyển, đổi trạng thái, ghi tiến độ,
 *                               ghi kết quả, xem lịch sử hoạt động.
 *   GAN_TAB["cv-ca-truc-viec"]  Khối "Công việc" trong Tổng quan ca trực:
 *                               tồn đọng, chưa phân công, ai đang trong ca.
 *
 * Danh sách cũ (08-tai-khoan.js) vẫn nằm trong `.tab__goc`: mô-đun này hỏng
 * thì ganKhe trả nó lại — màn không trắng. Hộp xác nhận kết quả ĐƠN (đối
 * soát ERPNext) dùng lại nguyên `cvMoKetQua` của tệp ấy, không chép lại:
 * hai bản luồng đối soát là hai chỗ để một chốt an toàn lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ (agent/api/cong_viec.py). Ẩn nút theo
 * quyền chỉ để màn hình không mời một 403 mỗi lần bấm.
 */
window.GAN_TAB = window.GAN_TAB || {};

const cvx = {
  el: null, ds: [], dm: null, moId: null, chiTiet: null,
  loc: { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
         chua_phan_cong: false, qua_han: false },
  nguoiNhan: null, dangTai: false, hen: null,
};

function cvxCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function cvxNgay(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
}

/* Hạn "ngày X" là HẾT ngày X theo giờ máy người dùng (cùng luật màn cũ). */
function cvxHan(ngay) { return ngay ? new Date(ngay + "T23:59:59").toISOString() : null; }

function cvxNhan(ma, ds) {
  const x = (ds || []).find((t) => t.ma === ma);
  return x ? x.nhan : ma;
}

/* Cờ màu theo TÌNH TRẠNG THẬT: quá hạn đỏ dù đang "Đang thực hiện". */
function cvxCo_mau(v) {
  if (v.qua_han) return "halt";
  if (v.trang_thai === "xong") return "auto";
  if (v.trang_thai === "huy") return "spend";
  if (v.chua_phan_cong || v.uu_tien === "gap" || v.uu_tien === "cao") return "assist";
  return "auto";
}

/* Liên kết NGỮ CẢNH (mục 14.8): hội thoại, hồ sơ khách, đơn — bấm là tới. */
function cvxLienKet(v) {
  return [
    v.conversation_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-ht="${esc(v.conversation_id)}">Hội thoại</button>` : "",
    v.contact_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-kh="${esc(v.contact_id)}">Khách${v.khach_ten ? ": " + esc(v.khach_ten) : ""}</button>` : "",
    v.order_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-don="${esc(v.ma_don || "")}">Đơn ${esc(v.ma_don || "")}</button>` : "",
  ].join("");
}

function cvxDong(v) {
  const nguoi = v.chua_phan_cong
    ? `<span class="pill pill--warn">${esc((cvx.dm && cvx.dm.nhan_chua_phan_cong) || "Chưa phân công")}</span>`
    : v.nguoi_nhan_ten ? `<span class="pill">${esc(v.nguoi_nhan_ten)}</span>` : "";
  const han = v.han
    ? `<span class="pill${v.qua_han ? " pill--warn" : ""}">${v.qua_han ? "quá hạn " : "hạn "}${esc(hanDoc(v.han))}</span>` : "";
  const nhanDuoc = v.chua_phan_cong && cvxCo("cong_viec.sua");
  return `<div class="row${cvx.moId === v.id ? " is-on" : ""}" data-cv="${esc(v.id)}">
    <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
    <div class="row__main">
      <b>${esc(v.tieu_de)}</b>
      <span class="row__sub">${esc(v.nhan_trang_thai)} · ${esc(cvxNhan(v.uu_tien, cvx.dm && cvx.dm.uu_tien))} · ${
        esc(v.nhan_nguon)}${v.khach_ten ? " · " + esc(v.khach_ten) : ""}${
        v.ma_don ? " · đơn " + esc(v.ma_don) : ""} · tạo ${esc(clock(v.tao_luc))}</span>
    </div>
    <div class="row__side">
      <span>${nguoi} ${han}</span>
      <span class="row__nut">
        ${nhanDuoc ? `<button type="button" class="btn btn--sm" data-cvx-nhan="${esc(v.id)}">Nhận</button>` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-cvx-mo="${esc(v.id)}">Chi tiết</button>
      </span>
    </div>
  </div>`;
}

/* ---------------- tải ---------------- */

async function cvxTaiDs() {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(cvx.loc)) {
    if (v === true) q.set(k, "true");
    else if (v) q.set(k, v);
  }
  const d = await api(`/cong-viec?${q}`);
  cvx.dm = { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon,
             nhan_chua_phan_cong: d.nhan_chua_phan_cong };
  cvx.ds = d.cong_viec;
  /* Hộp xác nhận kết quả ĐƠN của 08-tai-khoan.js tìm việc trong
     `congViec.ds` — giữ cùng danh sách để nó mở được từ màn này. */
  congViec.ds = d.cong_viec;
  congViec.trangThai = d.trang_thai;
  congViec.uuTien = d.uu_tien;
}

async function cvxTaiDem() {
  try {
    const t = await api("/cong-viec/tong-quan");
    $("#c-congviec").textContent = (t.dem.cho_xu_ly + t.dem.dang_thuc_hien) || "";
    return t;
  } catch (e) { console.warn("Không tải được tổng quan công việc", e); return null; }
}

async function cvxLamMoi() {
  if (!cvx.el || cvx.dangTai) return;
  cvx.dangTai = true;
  try {
    await cvxTaiDs();
    cvxVeDs();
    if (cvx.moId) await cvxTaiChiTiet(cvx.moId, false);
    cvxTaiDem();
  } catch (e) {
    $("#cvxDs", cvx.el).innerHTML = `<p class="empty">Không tải được công việc: ${esc(e.message)}</p>`;
  } finally { cvx.dangTai = false; }
}

function cvxVeDs() {
  const o = $("#cvxDs", cvx.el);
  o.innerHTML = cvx.ds.length ? cvx.ds.map(cvxDong).join("")
    : '<p class="empty">Không có việc nào trong bộ lọc này.</p>';
}

/* ---------------- chi tiết + lịch sử ---------------- */

async function cvxTaiChiTiet(id, cuon = true) {
  let d;
  try { d = await api(`/cong-viec/${encodeURIComponent(id)}`); }
  catch (e) {
    cvx.moId = null; cvx.chiTiet = null;
    $("#cvxCt", cvx.el).innerHTML = "";
    if (e.ma === 404) toast("Việc này không còn hoặc bạn không có quyền xem.", true);
    else toast(e.message, true);
    return;
  }
  cvx.moId = id;
  cvx.chiTiet = d;
  cvx.dm = cvx.dm || { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon };
  /* Việc mở từ chuông có thể không nằm trong bộ lọc đang chọn: thêm vào
     `congViec.ds` để hộp xác nhận đơn vẫn tìm thấy nó. */
  if (!congViec.ds.some((x) => x.id === id)) congViec.ds = congViec.ds.concat([d.cong_viec]);
  cvxVeChiTiet();
  $$("#cvxDs .row", cvx.el).forEach((r) => r.classList.toggle("is-on", r.dataset.cv === id));
  if (cuon) $("#cvxCt", cvx.el).scrollIntoView({ behavior: "smooth", block: "start" });
}

function cvxNutChiTiet(v) {
  const sua = cvxCo("cong_viec.sua");
  const giao = cvxCo("cong_viec.giao");
  const mo = v.trang_thai === "moi" || v.trang_thai === "dang_lam";
  const laCuaToi = v.nguoi_nhan && String(v.nguoi_nhan) === String(state.toiId || "");
  const xuLyDon = typeof cvLaXuLyDon === "function" && cvLaXuLyDon(v);
  const nut = [];
  if (mo && v.chua_phan_cong && sua) nut.push(["nhan", "Nhận việc", ""]);
  if (mo && v.trang_thai === "moi" && sua && (laCuaToi || giao)) nut.push(["bat-dau", "Bắt đầu", ""]);
  if (mo && sua && !xuLyDon) nut.push(["xong", "Hoàn thành…", "btn--go"]);
  if (mo && xuLyDon && typeof cvDuocXacNhan === "function" && cvDuocXacNhan())
    nut.push(["don", "Xác nhận kết quả đơn…", "btn--go"]);
  if (mo && sua) nut.push(["tien-do", "Cập nhật tiến độ…", ""]);
  if (mo && giao) nut.push(["giao", v.nguoi_nhan ? "Chuyển cho…" : "Giao cho…", ""]);
  if (mo && giao && v.chua_phan_cong) nut.push(["tu-dong", "Tự phân công", ""]);
  if (sua) nut.push(["sua", "Sửa…", "btn--ghost"]);
  if (!mo && sua && !xuLyDon) nut.push(["mo-lai", "Mở lại", "btn--ghost"]);
  if (mo && sua) nut.push(["huy", "Hủy việc…", "btn--halt"]);
  return nut.map(([ma, nhan, lop]) =>
    `<button type="button" class="btn btn--sm ${lop}" data-cvx-lam="${ma}">${esc(nhan)}</button>`).join("");
}

function cvxVeChiTiet() {
  const o = $("#cvxCt", cvx.el);
  const d = cvx.chiTiet;
  if (!d) { o.innerHTML = ""; return; }
  const v = d.cong_viec;
  const truong = [
    ["Trạng thái", v.nhan_trang_thai + (v.chua_phan_cong ? " · Chưa phân công" : "")],
    ["Ưu tiên", cvxNhan(v.uu_tien, d.uu_tien)],
    ["Người phụ trách", v.nguoi_nhan_ten || "—"],
    ["Người tạo", v.nguoi_giao_ten || v.nhan_nguon],
    ["Nguồn", v.nhan_nguon],
    ["Hạn", v.han ? cvxNgay(v.han) + (v.qua_han ? " (quá hạn)" : "") : "Không có"],
    ["Tạo lúc", cvxNgay(v.tao_luc)],
    ["Cập nhật lúc", cvxNgay(v.sua_luc)],
    ["Hoàn thành lúc", v.xong_luc ? cvxNgay(v.xong_luc) : "—"],
    ["Mô tả", v.mo_ta || "Không có mô tả"],
    ["Kết quả", v.ket_qua || (v.ket_qua_xu_ly_don
      ? `${v.ket_qua_xu_ly_don}${v.ly_do_ket_qua ? " — " + v.ly_do_ket_qua : ""}` : "Chưa có")],
  ];
  const lichSu = (d.lich_su || []).map((l) => {
    const chiTiet = [
      l.tu_nguoi || l.den_nguoi ? `${esc(l.tu_nguoi || "—")} → ${esc(l.den_nguoi || "—")}` : "",
      l.tu_trang_thai || l.den_trang_thai ? `${esc(l.tu_trang_thai || "—")} → ${esc(l.den_trang_thai || "—")}` : "",
      l.ghi_chu ? esc(l.ghi_chu) : "",
    ].filter(Boolean).join(" · ");
    return `<li class="cvx__ls-dong"><time>${esc(cvxNgay(l.tao_luc))}</time>
      <b>${esc(l.nhan_loai)}</b> <span class="cvx__ls-ai">${esc(l.nguoi)}</span>
      ${chiTiet ? `<span class="cvx__ls-ct">${chiTiet}</span>` : ""}</li>`;
  }).join("");
  o.innerHTML = `<section class="panel cvx__ct" aria-label="Chi tiết công việc">
    <h2 class="panel__head">${esc(v.tieu_de)}
      <button type="button" class="btn btn--sm btn--ghost" data-cvx-dong>Đóng</button></h2>
    <div class="cvk__detail">${truong.map(([nhan, gt], i) => `<div class="cvk__item${i >= 9 ? " cvk__item--wide" : ""}">
      <span class="cvk__label">${esc(nhan)}</span><span class="cvk__value">${esc(gt)}</span></div>`).join("")}</div>
    <div class="row__nut cvx__lienket">${cvxLienKet(v)}</div>
    <div class="row__nut cvx__nut">${cvxNutChiTiet(v)}</div>
    <h3 class="cvx__ls-tieu">Lịch sử hoạt động</h3>
    <ol class="cvx__ls">${lichSu || '<li class="empty">Chưa có hoạt động.</li>'}</ol>
  </section>`;
}

/* ---------------- thao tác ---------------- */

async function cvxNguoiNhan(congViecId) {
  /* Danh sách người nhận lấy từ /cong-viec/nguoi-nhan-duoc (chỉ cần
     `cong_viec.giao`), không từ /nguoi-dung (cần `nguoi_dung.doc`): người
     điều phối việc không nhất thiết quản lý nhân sự. */
  const q = congViecId ? `?cong_viec_id=${encodeURIComponent(congViecId)}` : "";
  const d = await api(`/cong-viec/nguoi-nhan-duoc${q}`);
  return d.nguoi.map((n) => ({
    value: n.id,
    label: `${n.ten}${n.trong_ca_that ? " · đang trong ca" : n.co_lich ? " · ngoài ca" : " · chưa xếp ca"}${
      n.san_sang ? "" : " · tắt sẵn sàng"}${n.cung_kenh ? "" : " · KHÔNG thuộc kênh của việc"} · ${n.so_mo} việc mở`,
  }));
}

async function cvxPut(id, than, xong) {
  try {
    await api(`/cong-viec/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(than) });
    if (xong) toast(xong);
    await cvxLamMoi();
  } catch (e) { toast(e.message, true); }
}

async function cvxLam(ma) {
  const d = cvx.chiTiet;
  if (!d) return;
  const v = d.cong_viec;
  const id = v.id;
  if (ma === "nhan") return cvxPut(id, { nguoi_nhan: state.toiId, trang_thai: "dang_lam" }, "Bạn đã nhận việc này.");
  if (ma === "bat-dau") return cvxPut(id, { trang_thai: "dang_lam" }, "Đã chuyển sang Đang thực hiện.");
  if (ma === "mo-lai") return cvxPut(id, { trang_thai: "dang_lam" }, "Đã mở lại việc.");
  if (ma === "don") { await cvMoKetQua(id, true); return; }
  if (ma === "xong") {
    const r = await hoiHop({ tieu_de: "Hoàn thành việc", phu: v.tieu_de, nut: "Hoàn thành",
      truong: [{ name: "ket_qua", label: "Kết quả", type: "textarea", rows: 4, maxlength: 2000,
                 value: v.ket_qua || "", placeholder: "Đã gọi, khách đồng ý nhận hàng chiều mai" }] });
    if (!r) return;
    return cvxPut(id, { trang_thai: "xong", ...(r.ket_qua ? { ket_qua: r.ket_qua } : {}) }, "Đã hoàn thành.");
  }
  if (ma === "huy") {
    const r = await hoiHop({ tieu_de: "Hủy việc này?", phu: v.tieu_de, nut: "Hủy việc", nguy_hiem: true,
      truong: [{ name: "ghi_chu", label: "Lý do", maxlength: 500, required: true,
                 placeholder: "Khách đã tự xử lý" }] });
    if (!r) return;
    return cvxPut(id, { trang_thai: "huy", ghi_chu: r.ghi_chu }, "Đã hủy việc — người liên quan được báo.");
  }
  if (ma === "tien-do") {
    const r = await hoiHop({ tieu_de: "Cập nhật tiến độ", phu: v.tieu_de, nut: "Ghi",
      truong: [{ name: "noi_dung", label: "Tiến độ", type: "textarea", rows: 3, maxlength: 2000,
                 required: true, placeholder: "Đã gọi lần 1, khách hẹn gọi lại 15h" }] });
    if (!r || !r.noi_dung) return;
    try {
      await api(`/cong-viec/${encodeURIComponent(id)}/tien-do`,
        { method: "POST", body: JSON.stringify({ noi_dung: r.noi_dung }) });
      toast("Đã ghi tiến độ.");
      await cvxTaiChiTiet(id, false);
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "tu-dong") {
    try {
      const r = await api(`/cong-viec/${encodeURIComponent(id)}/tu-dong-giao`, { method: "POST" });
      toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      await cvxLamMoi();
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "giao") {
    let chon;
    try { chon = await cvxNguoiNhan(id); } catch (e) { toast(e.message, true); return; }
    const r = await hoiHop({
      tieu_de: v.nguoi_nhan ? "Chuyển việc cho người khác" : "Giao việc", phu: v.tieu_de,
      nut: v.nguoi_nhan ? "Chuyển" : "Giao",
      truong: [
        { name: "nguoi_nhan", label: "Người nhận", type: "select", value: v.nguoi_nhan || "",
          options: [{ value: "", label: "— Thu hồi, để Chưa phân công —" }].concat(chon) },
        { name: "ghi_chu", label: "Ghi chú bàn giao", maxlength: 500,
          placeholder: "Đã gọi một lần, khách hẹn chiều" },
      ] });
    if (!r) return;
    const than = r.nguoi_nhan ? { nguoi_nhan: r.nguoi_nhan } : { xoa_nguoi_nhan: true };
    if (r.ghi_chu) than.ghi_chu = r.ghi_chu;
    return cvxPut(id, than, r.nguoi_nhan ? "Đã giao — người nhận được báo." : "Đã thu hồi người nhận.");
  }
  if (ma === "sua") {
    const r = await hoiHop({ tieu_de: "Sửa việc", nut: "Lưu", truong: [
      { name: "tieu_de", label: "Việc cần làm", required: true, maxlength: 200, value: v.tieu_de },
      { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 3, maxlength: 5000, value: v.mo_ta || "" },
      { name: "uu_tien", label: "Mức ưu tiên", type: "select", value: v.uu_tien,
        options: (d.uu_tien || []).map((u) => ({ value: u.ma, label: u.nhan })) },
      { name: "han", label: "Hạn", type: "date", hint: "để trống là bỏ hạn",
        value: v.han ? String(v.han).slice(0, 10) : "" },
    ] });
    if (!r) return;
    const than = { tieu_de: r.tieu_de, mo_ta: r.mo_ta, uu_tien: r.uu_tien };
    if (r.han) than.han = cvxHan(r.han); else than.xoa_han = true;
    return cvxPut(id, than, "Đã lưu việc.");
  }
}

/* Tạo việc — từ màn Công việc, hoặc từ một hội thoại (`ngu_canh` mang sẵn
 * hội thoại + khách). Phân công: tự nhận, chưa phân công, tự động, hay
 * một người cụ thể — hai lựa chọn sau chỉ hiện khi có `cong_viec.giao`. */
async function cvxTaoViec(ngu_canh = {}) {
  const giao = cvxCo("cong_viec.giao");
  let nguoi = [];
  if (giao) { try { nguoi = await cvxNguoiNhan(null); } catch { nguoi = []; } }
  const chon = [
    { value: "", label: "— Chưa phân công —" },
    { value: "__toi", label: "Tôi làm" },
  ].concat(giao ? [{ value: "__tu_dong", label: "Tự động: người đang trong ca, xoay vòng" }].concat(nguoi) : []);
  const r = await hoiHop({
    tieu_de: ngu_canh.ten_khach ? `Việc mới — ${ngu_canh.ten_khach}` : "Việc mới",
    phu: ngu_canh.conversation_id ? "Việc gắn với hội thoại đang mở — bấm vào việc là mở lại đúng hội thoại này." : "",
    nut: "Tạo việc",
    truong: [
      { name: "tieu_de", label: "Việc cần làm", required: true, maxlength: 200,
        placeholder: "Gọi lại chị Hoa xác nhận đơn" },
      { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 3, maxlength: 5000 },
      { name: "phan_cong", label: "Phân công", type: "select", value: giao ? "" : "__toi", options: chon },
      { name: "uu_tien", label: "Mức ưu tiên", type: "select", value: "thuong",
        options: ((cvx.dm && cvx.dm.uu_tien) || [{ ma: "thuong", nhan: "Thường" }])
          .map((u) => ({ value: u.ma, label: u.nhan })) },
      { name: "han", label: "Hạn", type: "date", hint: "để trống nếu không có" },
      { name: "ma_don", label: "Mã đơn liên quan", maxlength: 60, hint: "không bắt buộc",
        placeholder: "ĐH-…" },
    ],
  });
  if (!r || !r.tieu_de) return;
  const than = { tieu_de: r.tieu_de, mo_ta: r.mo_ta || "", uu_tien: r.uu_tien || "thuong",
                 han: cvxHan(r.han) };
  if (r.ma_don) than.ma_don = r.ma_don;
  if (ngu_canh.conversation_id) than.conversation_id = ngu_canh.conversation_id;
  if (ngu_canh.contact_id) than.contact_id = ngu_canh.contact_id;
  if (r.phan_cong === "__toi") than.nguoi_nhan = state.toiId;
  else if (r.phan_cong === "__tu_dong") than.giao_tu_dong = true;
  else if (r.phan_cong) than.nguoi_nhan = r.phan_cong;
  try {
    const kq = await api("/cong-viec", { method: "POST", body: JSON.stringify(than) });
    if (than.giao_tu_dong && !kq.nguoi_nhan) toast(`Đã tạo, nhưng chưa phân công được: ${kq.ly_do_khong_giao}`, true);
    else toast("Đã tạo việc.");
    if (cvx.el) { cvx.moId = kq.id; await cvxLamMoi(); }
    return kq.id;
  } catch (e) { toast(e.message, true); }
}

/* Mở ngữ cảnh của việc (mục 14.8). */
function cvxDiToiDon(ma) {
  state.orderFilter = "all";
  doiMan("donhang");
  if (!ma) return;
  setTimeout(() => {
    const dong = [...$$("#orders > *")].find((x) => x.textContent.includes(ma));
    if (dong) { dong.scrollIntoView({ behavior: "smooth", block: "center" }); dong.classList.add("is-chuong");
      setTimeout(() => dong.classList.remove("is-chuong"), 2400); }
  }, 900);
}

function cvxBatSuKienLienKet(o) {
  o.addEventListener("click", (e) => {
    const ht = e.target.closest("[data-cvx-ht]");
    if (ht) { state.openConv = ht.dataset.cvxHt; state.cuonToiChiTiet = true; doiMan("hoithoai"); return; }
    const kh = e.target.closest("[data-cvx-kh]");
    if (kh) { openCustomer(kh.dataset.cvxKh); return; }
    const don = e.target.closest("[data-cvx-don]");
    if (don) cvxDiToiDon(don.dataset.cvxDon);
  });
}

/* ---------------- gắn: Danh sách công việc ---------------- */

GAN_TAB["cv-danh-sach"] = (el) => {
  cvx.el = el;
  const opt = (ds) => ds.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  el.innerHTML = `
    <section class="panel">
      <h2 class="panel__head">Công việc
        <span class="panel__note">việc nội bộ cần người theo dõi — chuyển hội thoại cho người KHÔNG sinh việc</span>
        ${cvxCo("cong_viec.sua") ? '<button type="button" class="btn btn--sm btn--primary" id="cvxThem">Tạo việc</button>' : ""}</h2>
      <div class="filterbar cvx__loc" role="group" aria-label="Lọc công việc">
        <input type="search" id="cvxTim" class="cvx__tim" placeholder="Tìm tiêu đề, khách, mã đơn…" maxlength="100" aria-label="Tìm công việc">
        <select id="cvxTrangThai" aria-label="Trạng thái">${opt([["", "Mọi trạng thái"],
          ["moi", "Chờ xử lý"], ["dang_lam", "Đang thực hiện"], ["xong", "Hoàn thành"], ["huy", "Đã hủy"]])}</select>
        <select id="cvxUuTien" aria-label="Ưu tiên">${opt([["", "Mọi ưu tiên"], ["gap", "Gấp"],
          ["cao", "Cao"], ["thuong", "Thường"], ["thap", "Thấp"]])}</select>
        <select id="cvxNguon" aria-label="Nguồn">${opt([["", "Mọi nguồn"], ["nguoi", "Nhân viên tạo"],
          ["agent", "AI đề xuất"], ["tu_dong", "Tự động"], ["van_chuyen", "Vận chuyển"], ["don_hang", "Đơn hàng"]])}</select>
        <button type="button" class="chip" data-cvx-loc="cua_toi">Việc của tôi</button>
        <button type="button" class="chip" data-cvx-loc="chua_phan_cong">Chưa phân công</button>
        <button type="button" class="chip" data-cvx-loc="qua_han">Quá hạn</button>
      </div>
      <div id="cvxDs" class="rows"><p class="empty">Đang tải…</p></div>
    </section>
    <div id="cvxCt"></div>`;

  $("#cvxThem", el)?.addEventListener("click", () => cvxTaoViec());
  let hoan = null;
  $("#cvxTim", el).addEventListener("input", (e) => {
    clearTimeout(hoan);
    hoan = setTimeout(() => { cvx.loc.q = e.target.value.trim(); cvxLamMoi(); }, 300);
  });
  for (const [sel, k] of [["#cvxTrangThai", "trang_thai"], ["#cvxUuTien", "uu_tien"], ["#cvxNguon", "nguon"]]) {
    $(sel, el).addEventListener("change", (e) => { cvx.loc[k] = e.target.value; cvxLamMoi(); });
  }
  el.addEventListener("click", async (e) => {
    const loc = e.target.closest("[data-cvx-loc]");
    if (loc) {
      const k = loc.dataset.cvxLoc;
      cvx.loc[k] = !cvx.loc[k];
      loc.classList.toggle("is-on", cvx.loc[k]);
      cvxLamMoi();
      return;
    }
    const nhan = e.target.closest("[data-cvx-nhan]");
    if (nhan) {
      await cvxPut(nhan.dataset.cvxNhan, { nguoi_nhan: state.toiId, trang_thai: "dang_lam" }, "Bạn đã nhận việc này.");
      return;
    }
    const mo = e.target.closest("[data-cvx-mo]");
    if (mo) { await cvxTaiChiTiet(mo.dataset.cvxMo); return; }
    if (e.target.closest("[data-cvx-dong]")) {
      cvx.moId = null; cvx.chiTiet = null; cvxVeChiTiet();
      $$("#cvxDs .row", el).forEach((r) => r.classList.remove("is-on"));
      return;
    }
    const lam = e.target.closest("[data-cvx-lam]");
    if (lam) await cvxLam(lam.dataset.cvxLam);
  });
  cvxBatSuKienLienKet(el);
  el.addEventListener("tab:hien", () => cvxLamMoi());
  cvxLamMoi();
};

/* Vòng làm mới chung (10-vong-lam-moi) KHÔNG nạp tab đã gắn mô-đun — mô-đun
 * tự lo: làm mới khi tab đang hiện, và khi hộp xác nhận đơn của 08 vừa đổi
 * dữ liệu (nó gọi loadCongViec, phát `congviec:doi`). */
setInterval(() => {
  if (document.hidden) return;
  if (cvx.el && tabDangHien("cv-danh-sach")) cvxLamMoi();
  if (cvxCa.el && tabDangHien("cv-ca-truc")) cvxCaTai();
}, 20000);
document.addEventListener("congviec:doi", () => { if (cvx.el) cvxLamMoi(); });

/* Chuông "việc" và mọi lối khác mở thẳng chi tiết một việc. */
window.moCongViec = async (id) => {
  doiMan("cv-danh-sach");
  if (!cvx.el) return false;
  await cvxTaiChiTiet(id);
  return cvx.moId === id;
};

/* Nút "+ Tạo công việc" trong hội thoại (03-hoi-thoai.js vẽ lại khung mỗi
 * nhịp, nên bắt ở document). Gắn sẵn hội thoại + khách (mục 14.3). */
document.addEventListener("click", (e) => {
  if (!e.target.closest("#btn-tao-viec-ht")) return;
  const c = state.convDangMo;
  if (!c) return;
  cvxTaoViec({ conversation_id: c.id, contact_id: c.contact_id, ten_khach: c.customer_name });
});

/* ---------------- gắn: khối Công việc trong Tổng quan ca trực ---------------- */

const cvxCa = { el: null };

function cvxO(nhan, so, loc, mau) {
  return `<button type="button" class="readout__cell cvx__o" data-cvx-di="${loc}">
    <span class="readout__label">${esc(nhan)}</span>
    <span class="readout__line"><span class="readout__value">${so}</span></span>
    <span class="readout__bar"><span class="readout__fill readout__fill--${mau}" style="width:${so ? 100 : 0}%"></span></span>
  </button>`;
}

async function cvxCaTai() {
  const o = cvxCa.el;
  if (!o) return;
  const t = await cvxTaiDem();
  if (!t) { o.innerHTML = '<p class="empty">Không tải được tổng quan công việc.</p>'; return; }
  const d = t.dem;
  const giao = cvxCo("cong_viec.giao");
  const nv = t.nhan_vien;
  o.innerHTML = `<section class="panel">
    <h2 class="panel__head">Công việc
      <span class="panel__note">${t.tu_dong_duoc == null ? "trong phạm vi bạn thấy"
        : t.tu_dong_duoc ? `${t.tu_dong_duoc} người đang nhận được phân công tự động`
        : "LÚC NÀY không ai trong ca để phân công tự động — việc mới sẽ ở Chưa phân công"}</span></h2>
    <div class="readout">
      ${cvxO("Chưa phân công", d.chua_phan_cong, "chua_phan_cong", d.chua_phan_cong ? "assist" : "auto")}
      ${cvxO("Chờ xử lý", d.cho_xu_ly, "moi", "spend")}
      ${cvxO("Đang thực hiện", d.dang_thuc_hien, "dang_lam", "auto")}
      ${cvxO("Quá hạn", d.qua_han, "qua_han", d.qua_han ? "halt" : "auto")}
      ${cvxO("Hoàn thành hôm nay", d.xong_hom_nay, "xong", "auto")}
    </div>
    <div class="split">
      <div>
        <h3 class="cvx__ls-tieu">Việc chưa phân công</h3>
        <div class="rows">${t.chua_phan_cong.length ? t.chua_phan_cong.map((v) => `<div class="row">
          <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
          <div class="row__main"><b>${esc(v.tieu_de)}</b>
            <span class="row__sub">${esc(v.nhan_nguon)} · ${esc(cvxNhan(v.uu_tien, t.uu_tien))}${
              v.han ? " · hạn " + esc(hanDoc(v.han)) : ""}${v.khach_ten ? " · " + esc(v.khach_ten) : ""}</span></div>
          <div class="row__side"><span class="row__nut">
            ${cvxCo("cong_viec.sua") ? `<button type="button" class="btn btn--sm" data-cvx-ca-nhan="${esc(v.id)}">Nhận</button>` : ""}
            ${giao ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-tu-dong="${esc(v.id)}">Tự phân công</button>` : ""}
            <button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-mo="${esc(v.id)}">Mở</button>
          </span></div></div>`).join("") : '<p class="empty">Không có việc nào chờ phân công.</p>'}</div>
      </div>
      ${nv ? `<div>
        <h3 class="cvx__ls-tieu">Nhân viên và việc đang giữ</h3>
        <div class="rows">${nv.length ? nv.map((n) => `<div class="row">
          <span class="row__flag row__flag--${n.trong_ca_that && n.san_sang ? "auto" : "assist"}"></span>
          <div class="row__main"><b>${esc(n.ten)}</b>
            <span class="row__sub">${n.trong_ca_that ? "đang trong ca" : n.co_lich ? "ngoài ca" : "chưa xếp ca"}${
              n.san_sang ? "" : " · tắt sẵn sàng"}</span></div>
          <div class="row__side"><span><span class="pill">${n.so_mo} việc mở</span>${
            n.so_qua_han ? ` <span class="pill pill--warn">${n.so_qua_han} quá hạn</span>` : ""}</span></div>
        </div>`).join("") : '<p class="empty">Chưa có nhân viên nào làm được công việc.</p>'}</div>
      </div>` : ""}
    </div>
  </section>`;
}

GAN_TAB["cv-ca-truc-viec"] = (el) => {
  cvxCa.el = el;
  el.addEventListener("click", async (e) => {
    const di = e.target.closest("[data-cvx-di]");
    if (di) {
      const k = di.dataset.cvxDi;
      cvx.loc = { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
                  chua_phan_cong: k === "chua_phan_cong", qua_han: k === "qua_han" };
      if (k === "moi" || k === "dang_lam" || k === "xong") cvx.loc.trang_thai = k;
      doiMan("cv-danh-sach");
      if (cvx.el) {
        $("#cvxTrangThai", cvx.el).value = cvx.loc.trang_thai;
        $$("[data-cvx-loc]", cvx.el).forEach((c) => c.classList.toggle("is-on", !!cvx.loc[c.dataset.cvxLoc]));
        cvxLamMoi();
      }
      return;
    }
    const mo = e.target.closest("[data-cvx-ca-mo]");
    if (mo) { await window.moCongViec(mo.dataset.cvxCaMo); return; }
    const nhan = e.target.closest("[data-cvx-ca-nhan]");
    const tuDong = e.target.closest("[data-cvx-ca-tu-dong]");
    try {
      if (nhan) {
        await api(`/cong-viec/${encodeURIComponent(nhan.dataset.cvxCaNhan)}`, { method: "PUT",
          body: JSON.stringify({ nguoi_nhan: state.toiId, trang_thai: "dang_lam" }) });
        toast("Bạn đã nhận việc này.");
      } else if (tuDong) {
        const r = await api(`/cong-viec/${encodeURIComponent(tuDong.dataset.cvxCaTuDong)}/tu-dong-giao`, { method: "POST" });
        toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      } else return;
    } catch (err) { toast(err.message, true); }
    cvxCaTai();
  });
  el.addEventListener("tab:hien", () => cvxCaTai());
  cvxCaTai();
};
/* ---------------- Media khách gửi: dung lượng, hàng chờ tải, lượt dọn ----------------
 *
 * Gắn qua `GAN_TAB['ht-sao-luu-media']` (khe trong tab Sao lưu & Bảo trì).
 * Thời hạn giữ (`MEDIA_LUU_NGAY`) và trần dung lượng sửa ở ô `data-api-cac-nhom
 * ="media"` ngay dưới khung này — dùng chung bộ Lưu của 13-cau-hinh.js, không
 * dựng một ô sửa thứ hai để lệch nhau.
 *
 * "Dọn ngay" LUÔN xem trước: bấm lần đầu chỉ đếm, hộp xác nhận hiện đúng con
 * số sẽ xoá, rồi mới xoá thật. Một nút xoá dữ liệu khách chỉ cách một cú bấm
 * nhầm là nút người ta sẽ bấm nhầm.
 */

const MEDIA_TRANG_THAI = {
  cho: "Chờ tải", dang_tai: "Đang tải", da_tai: "Đã lưu", loi: "Hỏng sau nhiều lần thử",
  qua_lon: "Quá lớn — không tải", het_han: "Link hãng đã hết hạn", bo_qua: "Không có link / kiểu không cho phép",
  da_don: "Đã dọn theo thời hạn", mat_tep: "Mất tệp trên đĩa",
};
const MEDIA_LOAI = { image: "Ảnh", video: "Video", audio: "Âm thanh", application: "Tài liệu", text: "Văn bản" };

function mediaCo(n) {
  const b = Number(n || 0);
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(0)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}

function mediaVe(d, coSua) {
  const tt = d.trang_thai || {};
  const cho = (tt.cho || 0) + (tt.dang_tai || 0);
  const hong = (tt.loi || 0) + (tt.het_han || 0) + (tt.qua_lon || 0) + (tt.mat_tep || 0);
  const nhip = d.worker_luc ? `vòng tải đập lần cuối ${esc(clock(d.worker_luc))}${clock(d.worker_luc).match(/^\d/) ? " trước" : ""}`
    : "vòng tải CHƯA chạy lần nào trên máy chủ này";
  const lan = d.lan_don_cuoi;
  const dongLan = lan
    ? `${esc(new Date(lan.bat_dau).toLocaleString("vi-VN"))} (${lan.nguon === "thu_cong" ? `bấm tay bởi ${esc(lan.boi || "?")}` : "tự động"})
       — xoá ${lan.so_tep_xoa} tệp quá hạn, ${lan.so_mo_coi_xoa} tệp mồ côi, giải phóng <b>${mediaCo(lan.byte_giai_phong)}</b>${
       lan.so_dong_mat_tep ? `, <b>${lan.so_dong_mat_tep} dòng mất tệp</b>` : ""}${
       lan.xong_luc ? "" : " — <b>CHƯA chạy xong</b> (hỏng giữa chừng? xem Nhật ký: media.error)"}`
    : "chưa có lượt dọn nào";
  const loai = (d.theo_loai || []).map((r) =>
    `<span class="chip">${esc(MEDIA_LOAI[r.loai] || r.loai)} <span class="chip__so">${r.so_tep}</span> · ${mediaCo(r.so_byte)}</span>`).join(" ");
  const hongDs = (d.hong_gan_day || []).map((r) => `
    <div class="row"><span class="row__flag row__flag--${r.trang_thai === "het_han" || r.trang_thai === "qua_lon" ? "assist" : "halt"}"></span>
      <span class="row__body"><span class="row__title">${esc(MEDIA_TRANG_THAI[r.trang_thai] || r.trang_thai)} · ${esc(r.loai || "tệp")}</span>
        <span class="row__sub">${esc(r.ly_do || "—")} · ${esc(r.nguon || "không có link")} · thử ${esc(r.so_lan_thu)} lần</span></span>
      <span class="row__time">${esc(clock(r.luc))}</span></div>`).join("");
  return `
    <p class="row__sub">${nhip}. Giữ <b>${esc(d.thoi_han_ngay)} ngày</b> kể từ lần gửi gần nhất
      (${d.nguon_thoi_han === "csdl" ? "đặt trên dashboard" : "mặc định .env"}) · trần mỗi tệp <b>${esc(d.toi_da_mb)} MB</b>.</p>
    <div class="readout">
      <div class="readout__cell"><span class="readout__label">Media khách gửi</span>
        <span class="readout__value">${mediaCo(d.so_byte)}</span><span class="readout__unit">${d.so_tep} tệp</span></div>
      <div class="readout__cell"><span class="readout__label">Tệp nhân viên gửi</span>
        <span class="readout__value">${mediaCo(d.uploads.so_byte)}</span><span class="readout__unit">${d.uploads.so_tep} tệp</span></div>
      <div class="readout__cell"><span class="readout__label">Chống trùng tiết kiệm</span>
        <span class="readout__value">${mediaCo(d.trung_lap.byte_tiet_kiem)}</span><span class="readout__unit">${d.trung_lap.so_ban_khong_chep} bản không chép</span></div>
      <div class="readout__cell"><span class="readout__label">Đang chờ tải</span>
        <span class="readout__value">${cho}</span><span class="readout__unit">${hong} không giữ được</span></div>
    </div>
    ${loai ? `<p class="chips">${loai}</p>` : ""}
    <p class="row__sub"><b>Lượt dọn gần nhất:</b> ${dongLan}</p>
    ${d.so_mat_tep ? `<p class="row__sub row__sub--loi"><b>${d.so_mat_tep} tệp có trong CSDL nhưng không còn trên đĩa.</b>
      Vừa chuyển máy? Chép lại thư mục data/media từ bản sao lưu — dòng tự hết đánh dấu ở lượt dọn sau.</p>` : ""}
    ${hongDs ? `<h3 class="row__title">Không giữ được gần đây</h3><div class="rows">${hongDs}</div>` : ""}
    <div class="rowbtns">
      <button type="button" class="btn btn--sm" data-media="lam-moi">Làm mới</button>
      ${coSua ? `<button type="button" class="btn btn--sm btn--halt" data-media="don">Dọn ngay…</button>
        ${tt.loi ? `<button type="button" class="btn btn--sm" data-media="thu-lai">Thử tải lại ${tt.loi} tệp hỏng</button>` : ""}`
      : `<span class="row__sub">Cần quyền cau_hinh.sua để dọn.</span>`}
      <span class="row__sub" data-media-kq aria-live="polite"></span>
    </div>`;
}

async function ganMedia(goc, ctx) {
  const coSua = ctx.quyen.has("cau_hinh.sua");
  const kq = () => goc.querySelector("[data-media-kq]");
  const napLai = async () => {
    try {
      const d = await api("/media/tong-quan");
      goc.innerHTML = mediaVe(d, coSua);
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được số liệu media: ${esc(e.message)}</p>`;
    }
  };
  goc.addEventListener("click", async (e) => {
    const nut = e.target.closest("[data-media]");
    if (!nut) return;
    const viec = nut.dataset.media;
    if (viec === "lam-moi") { await napLai(); return; }
    nut.disabled = true;
    try {
      if (viec === "thu-lai") {
        const r = await api("/media/thu-lai", { method: "POST" });
        toast(`Đã đưa ${r.so_tep} tệp về hàng chờ tải.`);
      } else if (viec === "don") {
        if (kq()) kq().textContent = "Đang đếm…";
        const xem = await api("/media/don", { method: "POST", body: JSON.stringify({ xem_truoc: true }) });
        const tong = xem.so_tep_xoa + xem.so_mo_coi;
        if (!tong) {
          toast("Không có gì để dọn: chưa tệp nào quá hạn, không có tệp mồ côi.");
        } else {
          const ok = await hoiHop({
            tieu_de: `Xoá ${tong} tệp, giải phóng ${mediaCo(xem.byte_giai_phong)}?`,
            phu: `${xem.so_tep_xoa} tệp media không còn đính kèm nào trong ${xem.thoi_han_ngay} ngày gần đây, `
              + `${xem.so_mo_coi} tệp mồ côi (không dòng CSDL nào nhận, tệp tạm bỏ dở, tệp nhân viên của hội thoại đã xoá). `
              + "Không hoàn tác được. Ảnh sản phẩm và tài liệu công ty không bao giờ bị đụng.",
            nut: "Xoá", nguy_hiem: true,
          });
          if (ok) {
            const r = await api("/media/don", { method: "POST", body: JSON.stringify({ xem_truoc: false }) });
            toast(`Đã xoá ${r.so_tep_xoa + r.so_mo_coi} tệp, giải phóng ${mediaCo(r.byte_giai_phong)}`
              + (r.loi.length ? ` — ${r.loi.length} tệp KHÔNG xoá được, xem Nhật ký.` : "."), r.loi.length > 0);
          }
        }
      }
      await napLai();
    } catch (err) {
      toast(err.message, true);
      if (kq()) kq().textContent = "";
    } finally {
      nut.disabled = false;
    }
  });
  goc.addEventListener("tab:hien", napLai);
  await napLai();
}

window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["ht-sao-luu-media"] = (o, ctx) => { ganMedia(o, ctx); };
/* ---------------- SLA & Giờ làm việc (Cấu hình chung → tab cc-sla) ----------------
 *
 * Gắn qua `GAN_TAB['cc-sla']`. Bốn khối, cùng MỘT chỗ người quản trị đặt:
 *   1. Mục tiêu SLA — ba mục tiêu (phản hồi đầu, phản hồi sau chuyển giao,
 *      giải quyết), mỗi mục tiêu chọn đồng hồ "giờ làm việc" hay "24/7" và
 *      ngưỡng cảnh báo riêng (trống = ngưỡng chung).
 *   2. Hạn theo kênh × mức ưu tiên — số phút của ba mục tiêu
 *      (`/routing/sla-policies`).
 *   3. Lịch làm việc CHUNG — giờ mở/đóng từng thứ, ngày nghỉ lễ. Một nguồn
 *      cho hạn SLA, câu báo khách ngoài giờ, điều kiện "ngoài giờ" của quy
 *      tắc tự động (agent/core/lich_lam_viec.py).
 *   4. Ngưỡng chung và việc làm khi trễ — ô `cau_hinh_dong` sẵn có
 *      (`#api-nhom-sla` trong index.html, NGOÀI phần bị thay; 13-cau-hinh.js
 *      vẽ, mô-đun này chỉ gọi nạp).
 *
 * KHÔNG nằm trong vòng làm mới 6 giây: lịch đang sửa dở mà bị dựng lại là
 * mất trắng, rồi người ta bấm Lưu một lịch cũ. Chỉ vẽ lại khi mở tab hoặc
 * sau khi Lưu.
 *
 * SLA KHÔNG hiện thường trực trong khung hội thoại (phiếu việc mục 15.7) —
 * cảnh báo đi qua chuông, số liệu ở màn Phân tích.
 */
window.GAN_TAB = window.GAN_TAB || {};

const SLA_UU_TIEN = { normal: "thường", low: "thấp", high: "cao", urgent: "gấp" };
const SLA_GIAI_THICH = {
  phan_hoi_dau: "Khách nhắn → câu trả lời THẬT đầu tiên của AI hoặc nhân viên. Thông báo AI, câu báo chuyển người/ngoài giờ, tin mẫu tự động không tính.",
  phan_hoi_sau_chuyen_giao: "AI chuyển cho người → tin đầu tiên của NHÂN VIÊN. Mỗi lần chuyển giao một hạn riêng.",
  giai_quyet: "Bắt đầu lượt phục vụ → hội thoại được giải quyết.",
};

function slaLuc(iso) { return iso ? new Date(iso).toLocaleString("vi-VN") : "—"; }

function slaNguon(n) {
  return n === "csdl" ? "lưu trên dashboard" : "đang lấy từ .env";
}

function slaVeMucTieu(d, sua) {
  const dong = d.muc_tieu.map((m) => `<tr data-sla-mt="${esc(m.ma)}">
      <td><b>${esc(m.ten)}</b><br><span class="row__sub">${esc(SLA_GIAI_THICH[m.ma] || "")}</span></td>
      <td><select data-sla-che-do${sua ? "" : " disabled"}>${Object.entries(d.che_do).map(([k, v]) =>
        `<option value="${esc(k)}"${k === m.che_do ? " selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <br><span class="row__sub">${esc(slaNguon(m.nguon_che_do))}</span></td>
      <td><input type="number" min="10" max="95" step="1" data-sla-nguong style="width:6em"
        value="${m.nguong_canh_bao == null ? "" : esc(m.nguong_canh_bao)}"
        placeholder="${esc(d.nguong_chung)} (chung)"${sua ? "" : " disabled"}>
        <br><span class="row__sub">đang dùng ${esc(m.nguong_hieu_luc)}%</span></td>
    </tr>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Mục tiêu SLA
      <span class="panel__note">đồng hồ và ngưỡng cảnh báo của từng mục tiêu</span></h2>
    <div class="kntt-bang"><table>
      <thead><tr><th>Mục tiêu</th><th>Tính thời gian</th><th>Cảnh báo khi đã dùng (%)</th></tr></thead>
      <tbody>${dong}</tbody></table></div>
    <p class="row__sub">"Theo giờ làm việc": đồng hồ chỉ chạy trong giờ mở cửa của lịch bên dưới —
      khách nhắn lúc 22 giờ thì hạn tính từ giờ mở cửa hôm sau. "24/7": chạy liên tục.
      Cảnh báo sớm và vi phạm đi qua chuông thông báo tới người đang phụ trách hội thoại và người quản lý.</p>
    ${sua ? `<div class="rowbtns"><button type="button" class="btn btn--sm btn--go" data-sla-luu-mt>Lưu mục tiêu</button>
      <span class="row__sub" data-sla-kq-mt aria-live="polite"></span></div>` : ""}
  </section>`;
}

function slaTenKenh(kenh, id) {
  if (!id) return "mọi kênh";
  const k = kenh.find((x) => String(x.id) === String(id));
  return k ? (k.display_name || k.channel) : "kênh đã xoá";
}

function slaVeChinhSach(cs, kenh, gioRieng, sua) {
  const conTacDung = gioRieng.con_tac_dung;
  const ds = cs.length ? cs.map((p) => {
    const gr = p.business_hours && p.business_hours.bat_dau != null
      ? ` · giờ riêng ${esc(p.business_hours.bat_dau)}h–${esc(p.business_hours.ket_thuc)}h${
          conTacDung ? "" : " (không còn tác dụng — đã có lịch chung)"}` : "";
    return `<div class="row">
      <span class="row__flag row__flag--${p.active ? "auto" : "halt"}"></span>
      <div class="row__main">
        <b>${esc(slaTenKenh(kenh, p.account_id))} · mức ${esc(SLA_UU_TIEN[p.priority] || p.priority)}</b>
        <span class="row__sub">phản hồi đầu ${esc(p.first_response_minutes)} phút ·
          sau chuyển giao ${p.handover_response_minutes ? esc(p.handover_response_minutes) + " phút" : "không đặt"} ·
          giải quyết ${esc(p.resolution_minutes)} phút${gr}</span>
      </div></div>`;
  }).join("") : '<p class="empty">Chưa đặt hạn nào — chưa hội thoại nào có SLA.</p>';
  const oKenh = '<option value="">mọi kênh</option>' + kenh.map((k) =>
    `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Hạn theo kênh và mức ưu tiên
      <span class="panel__note">chỉ để ĐO và cảnh báo — không tự đóng hội thoại</span></h2>
    <div class="rows">${ds}</div>
    ${sua ? `<form class="form" data-sla-form-cs>
      <div class="form__row">
        <label class="field"><span>Kênh</span><select name="account_id">${oKenh}</select></label>
        <label class="field"><span>Mức ưu tiên</span><select name="priority">${Object.entries(SLA_UU_TIEN).map(([k, v]) =>
          `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label class="field"><span>Phản hồi đầu trong (phút)</span>
          <input name="first_response_minutes" type="number" min="1" max="43200" value="15" required></label>
        <label class="field"><span>Phản hồi sau chuyển giao (phút) <em class="hint">trống = không đặt hạn</em></span>
          <input name="handover_response_minutes" type="number" min="1" max="43200" placeholder="vd 30"></label>
        <label class="field"><span>Giải quyết trong (phút)</span>
          <input name="resolution_minutes" type="number" min="1" max="525600" value="1440" required></label>
      </div>
      <div class="rowbtns"><button type="submit" class="btn btn--sm">Lưu hạn</button></div>
    </form>
    <p class="row__sub">Cùng kênh và mức ưu tiên thì lưu là thay hạn cũ. Hội thoại đang chạy giữ hạn đã đặt;
      hạn mới áp cho hội thoại (và lượt chuyển giao) bắt đầu sau khi lưu.</p>` : ""}
  </section>`;
}

function slaVeLich(d, sua) {
  const l = d.lich;
  const ngay = l.tuan.map((x, i) => `<tr data-sla-thu="${i}">
      <td>${esc(x.thu)}</td>
      <td><label><input type="checkbox" data-sla-mo-cua${x.nghi ? "" : " checked"}${sua ? "" : " disabled"}> mở cửa</label></td>
      <td><input type="time" data-sla-gio-mo value="${esc(x.mo || "08:00")}"${sua ? "" : " disabled"}></td>
      <td><input type="time" data-sla-gio-dong value="${esc(x.dong === "24:00" ? "23:59" : (x.dong || "21:00"))}"${
        sua ? "" : " disabled"}></td>
    </tr>`).join("");
  const le = l.ngay_nghi.map((x) => `<li data-sla-le="${esc(x.ngay)}" data-sla-le-ten="${esc(x.ten)}">
      ${esc(x.ngay)}${x.ten ? ` — ${esc(x.ten)}` : ""}
      ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-le="${esc(x.ngay)}">Bỏ</button>` : ""}</li>`).join("");
  const tt = d.trang_thai;
  const nguon = l.nguon === "csdl"
    ? `Lịch lưu trên dashboard — sửa bởi ${esc(l.sua_boi || "?")} lúc ${esc(slaLuc(l.sua_luc))}.`
    : "Chưa có lịch trên dashboard — đang dùng .env (GIO_LAM_VIEC_BAT_DAU / _KET_THUC, mọi ngày như nhau, không ngày lễ).";
  const gr = d.gio_rieng_chinh_sach;
  const canhGioRieng = (!gr.con_tac_dung && gr.ds.length)
    ? `<p class="row__sub"><b>⚠ ${gr.ds.length} chính sách SLA có giờ riêng (business_hours) — không còn tác dụng
        từ khi có lịch chung.</b></p>` : "";
  return `<section class="panel">
    <h2 class="panel__head">Giờ làm việc
      <span class="panel__note">MỘT lịch cho hạn SLA, câu báo khách ngoài giờ và quy tắc tự động "ngoài giờ"</span></h2>
    <p class="row__sub">${nguon}</p>
    <p class="row__sub">Bây giờ: <b>${tt.dang_trong_gio ? "trong giờ làm việc" : "ngoài giờ làm việc"}</b>${
      !tt.dang_trong_gio && tt.mo_ke_tiep ? ` — có người lại lúc ${esc(slaLuc(tt.mo_ke_tiep))}` : ""}.</p>
    ${canhGioRieng}
    <label class="field"><span>Giờ làm việc</span><select data-sla-lich-bat${sua ? "" : " disabled"}>
      <option value="1"${l.bat ? " selected" : ""}>Bật — có giờ mở / đóng cửa</option>
      <option value="0"${l.bat ? "" : " selected"}>Tắt — coi như trực 24/7</option></select></label>
    <div class="kntt-bang"><table>
      <thead><tr><th>Thứ</th><th></th><th>Mở</th><th>Đóng</th></tr></thead>
      <tbody>${ngay}</tbody></table></div>
    <p class="row__sub">Giờ Việt Nam. Đóng 21:00 nghĩa là 20:59 còn trong giờ. Đặt đóng 23:59 = hết ngày.</p>
    <h3 class="kntt-the__dau">Ngày nghỉ lễ</h3>
    <ul class="rows" data-sla-ds-le>${le || '<li class="empty">Chưa có ngày nghỉ lễ nào.</li>'}</ul>
    ${sua ? `<div class="form__row">
        <label class="field"><span>Ngày</span><input type="date" data-sla-le-moi></label>
        <label class="field"><span>Tên <em class="hint">tuỳ chọn</em></span><input type="text" maxlength="80" data-sla-le-ten-moi placeholder="vd Quốc khánh"></label>
        <button type="button" class="btn btn--sm" data-sla-them-le>Thêm ngày nghỉ</button>
      </div>
      <div class="rowbtns">
        <button type="button" class="btn btn--sm btn--go" data-sla-luu-lich>Lưu giờ làm việc</button>
        ${l.nguon === "csdl" ? '<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-lich>Bỏ lịch, dùng .env</button>' : ""}
        <span class="row__sub" data-sla-kq-lich aria-live="polite"></span>
      </div>` : ""}
    <p class="row__sub">Thứ tự ưu tiên: lịch lưu ở đây → .env. Hội thoại đang chạy giữ hạn đã đặt; lịch mới áp cho hạn đặt sau khi lưu,
      còn câu báo ngoài giờ và quy tắc tự động đổi ngay (≤ 30 giây).</p>
  </section>`;
}

function slaGomLich(el) {
  const tuan = $$("[data-sla-thu]", el).map((r) => {
    const dong = $("[data-sla-gio-dong]", r);
    return {
      nghi: !$("[data-sla-mo-cua]", r).checked,
      mo: $("[data-sla-gio-mo]", r).value,
      /* Ô giờ của trình duyệt không cho gõ 24:00 — 23:59 nghĩa là hết ngày. */
      dong: dong.value === "23:59" ? "24:00" : dong.value,
    };
  });
  const ngay_nghi = $$("[data-sla-le]", el).map((li) => ({ ngay: li.dataset.slaLe, ten: li.dataset.slaLeTen || "" }));
  return { bat: $("[data-sla-lich-bat]", el).value === "1", tuan, ngay_nghi };
}

async function ganSla(el) {
  const sua = coQuyen("dinh_tuyen.sua");
  const ve = async () => {
    let d, cs = [], kenh = [];
    try {
      d = await api("/sla/cau-hinh");
    } catch (e) {
      el.innerHTML = `<p class="empty">Không tải được cấu hình SLA: ${esc(e.message)}</p>`;
      return;
    }
    try { cs = (await api("/routing")).sla_policies || []; } catch { cs = []; }
    try { kenh = await api("/channel-accounts") || []; } catch { kenh = []; }
    el.innerHTML = slaVeMucTieu(d, sua) + slaVeChinhSach(cs, kenh, d.gio_rieng_chinh_sach, sua)
      + slaVeLich(d, sua);
    /* Ô ngưỡng chung / khi trễ (`#api-nhom-sla`) nằm NGOÀI phần bị thay
       (index.html) — vòng làm mới không nạp nó khi mô-đun đã gắn, nên nạp ở đây. */
    try { await loadCaiDatApi(); } catch (e) { toast(e.message, true); }
  };
  const ketQua = (sel, chu, loi = false) => {
    const o = el.querySelector(sel);
    if (o) { o.textContent = chu; o.classList.toggle("is-loi", loi); }
  };

  el.addEventListener("click", async (e) => {
    if (e.target.closest("[data-sla-luu-mt]")) {
      const muc_tieu = $$("[data-sla-mt]", el).map((r) => ({
        ma: r.dataset.slaMt,
        che_do: $("[data-sla-che-do]", r).value,
        nguong_canh_bao: $("[data-sla-nguong]", r).value === "" ? null : Number($("[data-sla-nguong]", r).value),
      }));
      try {
        await api("/sla/muc-tieu", { method: "PUT", body: JSON.stringify({ muc_tieu }) });
        toast("Đã lưu mục tiêu SLA.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-mt]", err.message, true); }
    } else if (e.target.closest("[data-sla-them-le]")) {
      const ngay = $("[data-sla-le-moi]", el).value;
      if (!ngay) { ketQua("[data-sla-kq-lich]", "Chọn ngày trước khi thêm.", true); return; }
      if ($(`[data-sla-le="${CSS.escape(ngay)}"]`, el)) { ketQua("[data-sla-kq-lich]", "Ngày ấy đã có.", true); return; }
      const ul = $("[data-sla-ds-le]", el);
      $(".empty", ul)?.remove();
      const li = document.createElement("li");
      li.dataset.slaLe = ngay;
      li.dataset.slaLeTen = $("[data-sla-le-ten-moi]", el).value.trim();
      li.innerHTML = `${esc(ngay)}${li.dataset.slaLeTen ? ` — ${esc(li.dataset.slaLeTen)}` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-sla-bo-le="${esc(ngay)}">Bỏ</button>
        <em class="hint">chưa lưu</em>`;
      ul.append(li);
      $("[data-sla-le-moi]", el).value = "";
      $("[data-sla-le-ten-moi]", el).value = "";
    } else if (e.target.closest("[data-sla-bo-le]")) {
      e.target.closest("li")?.remove();
      ketQua("[data-sla-kq-lich]", "Đã bỏ khỏi danh sách — bấm Lưu để có hiệu lực.");
    } else if (e.target.closest("[data-sla-luu-lich]")) {
      try {
        await api("/sla/lich-lam-viec", { method: "PUT", body: JSON.stringify(slaGomLich(el)) });
        toast("Đã lưu giờ làm việc.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-lich]", err.message, true); }
    } else if (e.target.closest("[data-sla-bo-lich]")) {
      const ok = await hoiHop({
        tieu_de: "Bỏ lịch làm việc trên dashboard?",
        phu: "Mọi nơi quay về giờ trong .env (cùng một khung cho mọi ngày, không ngày lễ).",
        nut: "Bỏ lịch", nguy_hiem: true,
      });
      if (!ok) return;
      try {
        await api("/sla/lich-lam-viec", { method: "DELETE" });
        toast("Đã bỏ lịch — đang dùng .env.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-lich]", err.message, true); }
    }
  });

  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-sla-form-cs]");
    if (!f) return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    /* Không gửi `business_hours`: máy chủ giữ giờ riêng đang lưu (nếu có).
       Ô phút chuyển giao trống = null: chính sách không đặt mục tiêu ấy. */
    const than = {
      account_id: d.account_id || null, priority: d.priority,
      first_response_minutes: Number(d.first_response_minutes),
      handover_response_minutes: d.handover_response_minutes === "" ? null : Number(d.handover_response_minutes),
      resolution_minutes: Number(d.resolution_minutes), active: true,
    };
    const nut = f.querySelector("button[type=submit]");
    nut.disabled = true;
    try {
      await api("/routing/sla-policies", { method: "PUT", body: JSON.stringify(than) });
      toast("Đã lưu hạn SLA.");
      await ve();
    } catch (err) { toast(err.message, true); } finally { nut.disabled = false; }
  });

  /* Lần đầu tab hiện, `veTab` vừa gắn mô-đun vừa phát `tab:hien` — gộp
     hai lời gọi trùng nhau thành một lần tải. */
  let dangVe = null;
  const veMot = () => {
    if (!dangVe) dangVe = ve().finally(() => { dangVe = null; });
    return dangVe;
  };
  el.addEventListener("tab:hien", () => { veMot(); });
  await veMot();
}

window.GAN_TAB["cc-sla"] = (el) => ganSla(el);
/* ---------------- Nhật ký kiểm toán (phiếu việc mục 18) ----------------
 *
 * Cài đặt & Quản trị → Hệ thống & Nhật ký → tab "Nhật ký". Thay danh sách
 * 50 dòng thô (`/events`) bằng màn TRA CỨU: lọc theo thời gian, hội thoại,
 * loại tác nhân / người, nhóm hành động, trạng thái; phân trang; bảng chi
 * tiết có cấu trúc, và với việc của AI — cả LƯỢT xử lý (tin khách → tài
 * liệu → công cụ → lưới → trả lời).
 *
 * Mọi chữ hiện ở đây đã được máy chủ làm sạch (`lam_sach`): token, khoá,
 * số điện thoại, email, suy luận model không bao giờ tới trình duyệt.
 *
 * Ghi (đánh dấu sự cố, bước can thiệp, kết thúc, giải trình) cần quyền
 * `nhat_ky.su_co` và LUÔN là dòng mới — máy chủ chặn sửa/xoá nhật ký.
 *
 * Cuối tệp: mục "Nhật ký hội thoại" trong panel Chi tiết của MỘT hội thoại
 * (`veNhatKyHoiThoai`, gọi từ 19-trach-nhiem.js) cho nhân viên không có
 * quyền xem toàn bộ nhật ký.
 */

const NK_TONE = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "auto" };
const NK_TAG = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "plain" };

const nk = { loc: {}, conTro: [], trangNay: null, danhMuc: null, moId: null, xem: "su_kien", el: null };

function nkCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function nkGio(iso) { return iso ? (typeof gioTin === "function" ? gioTin(iso) : clock(iso)) : ""; }

function nkNgan(id) { return id ? String(id).slice(0, 8) : ""; }

function nkTacNhan(b) {
  const t = b.tac_nhan || {};
  if (t.loai === "nhan_vien") return t.ten ? `Nhân viên · ${t.ten}` : "Nhân viên";
  if (t.loai === "ai") return t.ten ? `AI · ${t.ten}` : "AI";
  return "Hệ thống";
}

/* Chuyển giá trị ô datetime-local (giờ máy người xem) sang ISO có múi giờ:
 * máy chủ hiểu giờ không múi là giờ Việt Nam, còn người xem có thể ở nơi khác. */
function nkIso(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? "" : d.toISOString();
}

function nkChuoiLoc(them = {}) {
  const p = new URLSearchParams();
  const l = { ...nk.loc, ...them };
  for (const [k, v] of Object.entries(l)) if (v !== "" && v != null) p.set(k, v);
  return p.toString();
}

function nkVeKhung(el) {
  const dm = nk.danhMuc || { nhom: [], loai_tac_nhan: [], trang_thai: [], nguoi: [] };
  const chon = (name, nhan, ds, giaTri) => `<label class="field"><span>${nhan}</span>
    <select name="${name}"><option value="">Tất cả</option>${ds.map((x) =>
      `<option value="${esc(x.ma ?? x.id)}"${String(giaTri || "") === String(x.ma ?? x.id) ? " selected" : ""}>${
        esc(x.nhan ?? x.ten)}</option>`).join("")}</select></label>`;
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Nhật ký kiểm toán
      <span class="panel__note">AI, nhân viên và hệ thống · chỉ thêm, không sửa được</span></h2>
    <div class="tabs" role="tablist">
      <button type="button" class="tabbar__nut" data-nk-xem="su_kien" aria-selected="${nk.xem === "su_kien"}">Sự kiện</button>
      <button type="button" class="tabbar__nut" data-nk-xem="de_xuat" aria-selected="${nk.xem === "de_xuat"}">Đề xuất của AI &amp; phê duyệt</button>
    </div>
    <form class="form" data-nk-loc ${nk.xem === "su_kien" ? "" : "hidden"}>
      <div class="form__row">
        <label class="field"><span>Từ</span><input type="datetime-local" name="tu" value="${esc(nk.loc.tu_o || "")}"></label>
        <label class="field"><span>Đến</span><input type="datetime-local" name="den" value="${esc(nk.loc.den_o || "")}"></label>
        ${chon("loai_tac_nhan", "Tác nhân", dm.loai_tac_nhan, nk.loc.loai_tac_nhan)}
        ${chon("nguoi_id", "Người", dm.nguoi, nk.loc.nguoi_id)}
        ${chon("nhom", "Loại hành động", dm.nhom, nk.loc.nhom)}
        ${chon("trang_thai", "Trạng thái", dm.trang_thai, nk.loc.trang_thai)}
        <label class="field"><span>Hội thoại (mã)</span><input name="hoi_thoai_id" value="${esc(nk.loc.hoi_thoai_id || "")}" placeholder="dán mã hội thoại" autocomplete="off"></label>
        <label class="field"><span>Lượt AI (mã)</span><input name="luot_id" value="${esc(nk.loc.luot_id || "")}" autocomplete="off"></label>
      </div>
      <div class="rowbtns">
        <button type="submit" class="btn btn--sm btn--primary">Lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-xoa-loc>Xoá lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-csv>Xuất CSV</button>
      </div>
    </form>
    <div class="rows" data-nk-ds><p class="empty">Đang tải…</p></div>
    <div class="rowbtns" data-nk-trang></div>
  </section>
  <section class="panel" data-nk-chi-tiet hidden></section>`;
}

function nkDong(b) {
  const tt = b.trang_thai || {};
  return `<div class="row${nk.moId === b.id ? " is-mo" : ""}" data-nk-dong="${b.id}" role="button" tabindex="0">
    <span class="row__flag row__flag--${NK_TONE[tt.ma] || "plain"}"></span>
    <span class="row__body">
      <span class="row__title">${esc(b.hanh_dong)}
        <span class="tag tag--plain">${esc((b.nhom || {}).nhan || "")}</span>
        <span class="tag tag--${NK_TAG[tt.ma] || "plain"}">${esc(tt.nhan || "")}</span></span>
      <span class="row__sub">${esc(nkTacNhan(b))}${b.che_do_ai ? " · chế độ " + esc(b.che_do_ai) : ""}${
        b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span>
    </span>
    <span class="row__side">
      ${b.hoi_thoai_id ? `<button type="button" class="row__nut" data-nk-loc-ht="${esc(b.hoi_thoai_id)}" title="Lọc theo hội thoại này">HT ${esc(nkNgan(b.hoi_thoai_id))}</button>` : ""}
      <span class="row__time">${esc(nkGio(b.luc))}</span>
    </span>
  </div>`;
}

async function nkTai() {
  const el = nk.el;
  if (!el) return;
  const ds = el.querySelector("[data-nk-ds]");
  const trang = el.querySelector("[data-nk-trang]");
  try {
    let kq;
    if (nk.xem === "de_xuat") {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky/de-xuat?" + new URLSearchParams(truoc ? { truoc } : {}).toString());
      ds.innerHTML = kq.items.length ? kq.items.map(nkDongDeXuat).join("")
        : '<p class="empty">Chưa có đề xuất nào của AI.</p>';
    } else {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky?" + nkChuoiLoc(truoc ? { truoc } : {}));
      ds.innerHTML = kq.items.length ? kq.items.map(nkDong).join("")
        : '<p class="empty">Không có sự kiện nào khớp bộ lọc.</p>';
    }
    nk.trangNay = kq;
    trang.innerHTML = `${nk.conTro.length ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-truoc>← Mới hơn</button>' : ""}
      <span class="hint">Trang ${nk.conTro.length + 1}</span>
      ${kq.next_cursor ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-sau>Cũ hơn →</button>' : ""}`;
  } catch (e) {
    ds.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
    trang.innerHTML = "";
  }
}

function nkDongDeXuat(d) {
  const tt = d.trang_thai || {};
  const tone = tt.ma === "cho_duyet" ? "assist" : tt.ma === "tu_choi" ? "halt" : "auto";
  const quyet = d.nguoi_quyet ? `duyệt bởi ${d.nguoi_quyet}${d.luc_quyet ? " lúc " + nkGio(d.luc_quyet) : ""}` : "";
  const sua = d.nguoi_sua ? `sửa bởi ${d.nguoi_sua}` : "";
  return `<div class="row">
    <span class="row__flag row__flag--${tone}"></span>
    <span class="row__body">
      <span class="row__title">${esc((d.de_xuat_boi || {}).ten || "AI")} đề xuất trả lời
        <span class="tag tag--${tone === "auto" ? "plain" : tone}">${esc(tt.nhan || "")}</span></span>
      <span class="row__sub">${esc(d.tom_tat || "")}</span>
      <span class="row__sub">${esc([sua, quyet].filter(Boolean).join(" · ") || "chưa ai quyết")}</span>
    </span>
    <span class="row__side">
      ${d.luot_id && nkCo("nhat_ky.doc") ? `<button type="button" class="row__nut" data-nk-mo-luot="${esc(d.luot_id)}">Xem lượt AI</button>` : ""}
      <span class="row__time">${esc(nkGio(d.luc_de_xuat))}</span>
    </span>
  </div>`;
}

function nkCT(tieu, chi) {
  return typeof dongCT === "function" ? dongCT(esc(tieu), chi)
    : `<div class="ctt__dong"><b>${esc(tieu)}</b><span>${chi}</span></div>`;
}

/* Một lượt AI theo thứ tự: tin khách → các bước → câu trả lời (kèm căn cứ). */
function nkVeLuot(l) {
  if (!l) return "";
  const buoc = (l.buoc || []).map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc((b.trang_thai || {}).nhan || "")}${
        b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span></div>`).join("");
  const traLoi = (l.tra_loi || []).map((t) => {
    const dv = t.dau_vet || {};
    const tl = (dv.tri_thuc || []).map((x) => `<li><b>${esc(x.title || "(không tên)")}</b>${
      x.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(x.version)}</span>` : ""}${
      x.trich ? `<blockquote class="ctt__trich">${esc(x.trich)}</blockquote>` : ""}</li>`).join("");
    const cc = (dv.cong_cu || []).map((c) => `<li><b>${esc(c.ten)}</b>
      <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></li>`).join("");
    return `<div class="lichsu__dong">
      <b>Câu trả lời · ${esc(t.trang_thai || "")}</b>
      <span class="msg__meta">${esc(nkGio(t.luc))}${t.sua_boi ? " · sửa bởi " + esc(t.sua_boi) : ""}${
        t.duyet_boi ? " · duyệt bởi " + esc(t.duyet_boi) : ""}</span>
      <p>${esc(t.noi_dung || "")}</p>
      ${dv.luoi ? nkCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma || "")) : ""}
      ${dv.chuyen_nguoi && dv.chuyen_nguoi.co ? nkCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : ""}
      <h4 class="ctt__dau">Tài liệu đã dùng (ảnh chụp lúc xử lý)</h4>
      ${tl ? `<ul class="ctt__ds">${tl}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
      <h4 class="ctt__dau">Dữ liệu công cụ trả về (ảnh chụp lúc xử lý)</h4>
      ${cc ? `<ul class="ctt__ds">${cc}</ul>` : '<p class="hint">Không gọi công cụ nào.</p>'}
    </div>`;
  }).join("");
  return `<section class="lichsu" aria-label="Lượt AI">
    <h4 class="ctt__dau">Lượt AI ${esc(nkNgan(l.luot_id))}</h4>
    ${l.tin_khach ? `<div class="lichsu__dong"><b>Tin khách</b>
      <span class="msg__meta">${esc(nkGio(l.tin_khach.luc))}</span>
      <p>${esc(l.tin_khach.noi_dung || "(không đọc được nội dung)")}</p></div>` : ""}
    ${buoc || '<p class="hint">Lượt này không để lại dòng nhật ký nào.</p>'}
    ${traLoi}
  </section>`;
}

function nkVeChiTiet(b) {
  const tt = b.trang_thai || {};
  const ghi = nkCo("nhat_ky.su_co");
  const laSuCo = b.kind === "su_co.danh_dau";
  const nut = [
    ghi && !b.kind.startsWith("su_co.") && b.kind !== "nhat_ky.giai_trinh" && tt.ma !== "su_co"
      ? `<button type="button" class="btn btn--sm btn--halt" data-nk-su-co="${b.id}">Đánh dấu sự cố</button>` : "",
    ghi && laSuCo ? `<button type="button" class="btn btn--sm" data-nk-buoc="${b.id}">Thêm bước can thiệp</button>
      <button type="button" class="btn btn--sm" data-nk-ket-thuc="${b.id}">Kết thúc sự cố</button>` : "",
    ghi ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-giai-trinh="${b.id}">Giải trình / đính chính</button>` : "",
    b.su_kien_goc ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-mo="${b.su_kien_goc}">Mở dòng gốc #${esc(b.su_kien_goc)}</button>` : "",
    `<button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button>`,
  ].join("");
  const lien = (b.lien_quan || []).map((x) => `<div class="lichsu__dong">
      <b>${esc(x.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(x.luc))} · ${esc(nkTacNhan(x))}</span>
      ${x.chi_tiet && x.chi_tiet.ghi_chu ? `<p>${esc(x.chi_tiet.ghi_chu)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.ket_qua ? `<p><b>Kết quả:</b> ${esc(x.chi_tiet.ket_qua)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.nhan ? `<p>${esc(x.chi_tiet.nhan)}</p>` : ""}
    </div>`).join("");
  return `<h2 class="panel__head">#${b.id} · ${esc(b.hanh_dong)}
      <span class="panel__note">${esc(b.kind)}</span></h2>
    <div class="ctt">
      ${nkCT("Thời gian", esc(new Date(b.luc).toLocaleString("vi-VN")))}
      ${nkCT("Tác nhân", esc(nkTacNhan(b)))}
      ${nkCT("Loại hành động", esc((b.nhom || {}).nhan || ""))}
      ${nkCT("Hội thoại", b.hoi_thoai_id ? `<span class="mono">${esc(b.hoi_thoai_id)}</span>` : "—")}
      ${nkCT("Chế độ AI", esc(b.che_do_ai || "—"))}
      ${nkCT("Mức uỷ quyền", esc(b.muc_uy_quyen || "chưa áp dụng"))}
      ${nkCT("Trạng thái", esc(tt.nhan || ""))}
      ${nkCT("Kết quả", esc(b.ket_qua || "—"))}
      ${b.luot_id ? nkCT("Lượt AI", `<span class="mono">${esc(b.luot_id)}</span>`) : ""}
      <details class="ctt__kt"><summary>Dữ liệu ghi nhận (đã che thông tin nhạy cảm)</summary>
        <pre class="pre">${esc(JSON.stringify(b.chi_tiet || {}, null, 2))}</pre></details>
      ${lien ? `<h4 class="ctt__dau">Sự cố &amp; giải trình</h4><section class="lichsu">${lien}</section>` : ""}
      ${b.luot ? nkVeLuot(b.luot) : ""}
    </div>
    <div class="rowbtns">${nut}</div>`;
}

async function nkMo(id) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  nk.moId = Number(id);
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeChiTiet(await api(`/nhat-ky/${id}`));
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
  khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function nkMoLuot(luotId) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeLuot(await api(`/nhat-ky/luot/${encodeURIComponent(luotId)}`))
      + '<div class="rowbtns"><button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button></div>';
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
}

/* Ghi một dòng mới (sự cố, bước, kết thúc, giải trình) rồi mở lại dòng gốc. */
async function nkGhi(duong, hop, moLai) {
  const d = await hoiHop(hop);
  if (!d) return;
  try {
    await api(duong, { method: "POST", body: JSON.stringify(d) });
    toast("Đã ghi vào nhật ký.");
    await nkTai();
    if (moLai) await nkMo(moLai);
  } catch (e) { toast(e.message, true); }
}

async function nkXuLyClick(e) {
  const tim = (k) => e.target.closest(`[${k}]`);
  let o;
  if ((o = tim("data-nk-xem"))) {
    nk.xem = o.dataset.nkXem; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-loc-ht"))) {
    e.stopPropagation();
    nk.loc = { hoi_thoai_id: o.dataset.nkLocHt }; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-mo-luot"))) {
    await nkMoLuot(o.dataset.nkMoLuot);
  } else if ((o = tim("data-nk-mo"))) {
    await nkMo(o.dataset.nkMo);
  } else if ((o = tim("data-nk-dong"))) {
    await nkMo(o.dataset.nkDong);
  } else if (tim("data-nk-dong-ct")) {
    nk.moId = null;
    const k = nk.el.querySelector("[data-nk-chi-tiet]"); k.hidden = true; k.innerHTML = "";
  } else if (tim("data-nk-sau")) {
    if (nk.trangNay && nk.trangNay.next_cursor) { nk.conTro.push(nk.trangNay.next_cursor); await nkTai(); }
  } else if (tim("data-nk-truoc")) {
    nk.conTro.pop(); await nkTai();
  } else if (tim("data-nk-xoa-loc")) {
    nk.loc = {}; nk.conTro = []; nkVeKhung(nk.el); await nkTai();
  } else if (tim("data-nk-csv")) {
    /* CSV theo đúng bộ lọc đang xem (trừ lượt AI — xuất một lượt thì
       xem ngay trên màn này là đủ). `*_o` là giá trị ô nhập, không phải lọc. */
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(nk.loc)) {
      if (v && k !== "luot_id" && !k.endsWith("_o")) p.set(k, v);
    }
    window.open("/api/nhat-ky/xuat.csv?" + p.toString(), "_blank");
  } else if ((o = tim("data-nk-su-co"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkSuCo}/su-co`, {
      tieu_de: "Đánh dấu sự cố", nut: "Đánh dấu", nguy_hiem: true,
      phu: "Ghi thành một dòng MỚI trỏ về hành động này; dòng gốc giữ nguyên.",
      truong: [{ name: "ghi_chu", label: "Vì sao đây là sự cố", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkSuCo);
  } else if ((o = tim("data-nk-buoc"))) {
    const dm = (nk.danhMuc && nk.danhMuc.buoc_can_thiep) || [];
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkBuoc}/buoc`, {
      tieu_de: "Bước can thiệp", nut: "Ghi bước",
      truong: [
        { name: "loai", label: "Đã làm gì", type: "select", required: true,
          options: dm.map((x) => ({ value: x.ma, label: x.nhan })) },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkBuoc);
  } else if ((o = tim("data-nk-ket-thuc"))) {
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkKetThuc}/ket-thuc`, {
      tieu_de: "Kết thúc sự cố", nut: "Kết thúc",
      truong: [
        { name: "ket_qua", label: "Kết quả", required: true, maxlength: 500 },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkKetThuc);
  } else if ((o = tim("data-nk-giai-trinh"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkGiaiTrinh}/giai-trinh`, {
      tieu_de: "Giải trình / đính chính", nut: "Ghi",
      phu: "Nhật ký không sửa được. Lời giải trình là một dòng mới đi kèm dòng này.",
      truong: [{ name: "ghi_chu", label: "Nội dung", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkGiaiTrinh);
  }
}

window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["ht-nhat-ky"] = async (el) => {
  nk.el = el;
  if (!nkCo("nhat_ky.doc")) {
    el.innerHTML = '<section class="panel"><p class="empty">Cần quyền "Xem nhật ký kiểm toán" để xem mục này.</p></section>';
    return;
  }
  nkVeKhung(el);
  el.addEventListener("click", (e) => { nkXuLyClick(e); });
  el.addEventListener("keydown", (e) => {
    const d = e.target.closest("[data-nk-dong]");
    if (d && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); nkMo(d.dataset.nkDong); }
  });
  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-nk-loc]");
    if (!f) return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    nk.loc = {
      tu: nkIso(d.tu), den: nkIso(d.den), tu_o: d.tu, den_o: d.den,
      loai_tac_nhan: d.loai_tac_nhan, nguoi_id: d.nguoi_id, nhom: d.nhom,
      trang_thai: d.trang_thai, hoi_thoai_id: (d.hoi_thoai_id || "").trim(),
      luot_id: (d.luot_id || "").trim(),
    };
    nk.conTro = [];
    await nkTai();
  });
  /* Làm mới trang ĐẦU mỗi lần tab hiện lại — trang sau giữ nguyên, kẻo
   * người đang đọc trang 3 bị kéo về trang 1. */
  el.closest("[data-gan]")?.addEventListener("tab:hien", () => { if (!nk.conTro.length) nkTai(); });
  try {
    nk.danhMuc = await api("/nhat-ky/danh-muc");
    nkVeKhung(el);
  } catch (e) { toast(e.message, true); }
  await nkTai();
};

/* ---------------- Nhật ký của MỘT hội thoại ----------------
 * Trong panel "Chi tiết" của hội thoại. Chỉ cần `hoi_thoai.doc` và hội
 * thoại thuộc kênh của người xem (máy chủ chặn) — nhân viên trực thấy "AI
 * đã làm gì với khách mình đang giữ" mà không thấy nhật ký cả cửa hàng.
 * Tải khi BẤM, không tải theo vòng 6 giây. */
function veNhatKyHoiThoai(c) {
  const id = String(c.id);
  const bo = (state.nkHT || {})[id];
  if (!bo) {
    return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
      <button type="button" class="btn btn--sm btn--ghost" data-nk-ht="${esc(id)}">Xem việc AI và nhân viên đã làm</button>`;
  }
  if (bo.dangTai) return '<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Đang tải…</p>';
  if (bo.loi) return `<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  const dong = bo.items.map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc(nkTacNhan(b))} · ${esc((b.trang_thai || {}).nhan || "")}</span>
      ${b.ket_qua ? `<p>${esc(b.ket_qua)}</p>` : ""}
      ${b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? `<button type="button" class="msg__goc-nut" data-nk-ht-luot="${esc(id)}|${esc(b.luot_id)}">${
          bo.luot && bo.luot.luot_id === b.luot_id ? "Ẩn lượt AI" : "Xem lượt AI"}</button>` : ""}
      ${bo.luot && bo.luot.luot_id === b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? nkVeLuot(bo.luot) : ""}
    </div>`).join("");
  return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
    ${dong || '<p class="hint">Chưa có sự kiện nào.</p>'}`;
}

document.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-nk-ht], [data-nk-ht-luot]");
  if (!nut) return;
  state.nkHT = state.nkHT || {};
  if (nut.dataset.nkHt) {
    const id = nut.dataset.nkHt;
    state.nkHT[id] = { dangTai: true };
    if (state.openConv === id && typeof loadThread === "function") loadThread(id);
    try {
      const r = await api(`/nhat-ky/hoi-thoai/${id}?limit=50`);
      state.nkHT[id] = { items: r.items || [] };
    } catch (err) {
      state.nkHT[id] = { loi: err.message };
    }
  } else {
    const [id, luot] = nut.dataset.nkHtLuot.split("|");
    const bo = state.nkHT[id];
    if (!bo) return;
    if (bo.luot && bo.luot.luot_id === luot) { bo.luot = null; }
    else {
      try { bo.luot = await api(`/nhat-ky/hoi-thoai/${id}/luot/${encodeURIComponent(luot)}`); }
      catch (err) { toast(err.message, true); }
    }
  }
  const id = nut.dataset.nkHt || nut.dataset.nkHtLuot.split("|")[0];
  if (state.openConv === id && typeof loadThread === "function") loadThread(id);
});
/* ---------------- Ủy quyền thực thi của AI (mục 17) ----------------
 *
 * Hai phần:
 *   1. Tab Cấu hình AI Agent → Chính sách & Ủy quyền (`GAN_TAB["ai-chinh-sach"]`):
 *      mức của từng hành động — Không sử dụng / Có phê duyệt / Tự động.
 *   2. THẺ ĐỀ XUẤT trong luồng hội thoại: AI đã chuẩn bị một hành động cụ
 *      thể và chờ người có thẩm quyền. Thẻ là NỘI BỘ — nằm giữa khung, viền
 *      riêng, không bao giờ trông như tin đã gửi khách. Không có ô sửa: ở
 *      giai đoạn này người duyệt chỉ Duyệt hoặc Từ chối (phiếu việc 17.10).
 *
 * Mọi chốt thật nằm ở máy chủ (agent/core/uy_quyen.py, agent/api/uy_quyen_ai.py).
 * Nút ẩn/hiện ở đây chỉ để không mời một 403 — máy chủ vẫn kiểm lại.
 */

const dxTien = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

const DX_TAG = {
  cho_duyet: "assist", da_duyet: "assist", da_thuc_hien: "auto",
  loi: "halt", tu_choi: "plain", het_han: "plain",
};

function dxCoQuyen(q) {
  return !!(state.toiQuyen && state.toiQuyen.has(q));
}

/* ---------- 1. Tab chính sách ---------- */

function dxDongChinhSach(h, sua) {
  let o;
  if (!h.ho_tro) {
    o = '<span class="tag tag--plain">Chưa hỗ trợ — chuyển nhân viên</span>';
  } else if (!h.cau_hinh_duoc) {
    o = `<span class="tag tag--auto">${esc(h.nhan_muc)} · luôn bật</span>`;
  } else {
    o = `<select data-dx-muc="${esc(h.ma)}"${sua ? "" : " disabled"} aria-label="Mức cho ${esc(h.ten)}">${
      ["khong_su_dung", "co_phe_duyet", "tu_dong"].map((m) => `<option value="${m}"${m === h.muc ? " selected" : ""}>${
        esc({ khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[m])}</option>`).join("")}
      </select>`;
  }
  const nguong = h.co_nguong
    ? `<label class="field dx-nguong"><span>Ngưỡng phải duyệt (ở mức Tự động) <em class="hint">mặc định ${
        esc(dxTien(h.nguong_mac_dinh))}</em></span>
        <input type="number" min="0" step="1000" data-dx-nguong="${esc(h.ma)}" value="${esc(h.nguong_vnd ?? "")}"${
          sua ? "" : " disabled"}></label>`
    : "";
  const co = !h.ho_tro ? "plain" : h.muc === "tu_dong" ? "auto" : h.muc === "co_phe_duyet" ? "assist" : "halt";
  return `<div class="row dx-cs">
    <span class="row__flag row__flag--${co}"></span>
    <div class="row__body">
      <b>${esc(h.ten)}</b>${h.da_doi ? ' <span class="tag tag--plain">đã đổi</span>' : ""}
      <p class="row__sub">${esc(h.mo_ta)}</p>
      ${h.ghi_chu ? `<p class="row__sub hint">${esc(h.ghi_chu)}</p>` : ""}
      ${h.ho_tro && h.cau_hinh_duoc ? `<p class="row__sub hint">Mặc định: ${esc(
        { khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[h.mac_dinh] || h.mac_dinh)}${
        h.quyen_thi_hanh ? ` · người duyệt cần thêm quyền ${esc(h.quyen_thi_hanh)}` : ""}${
        h.sua_boi ? ` · sửa bởi ${esc(h.sua_boi)}` : ""}</p>` : ""}
      ${nguong}
    </div>
    <div class="row__aside">${o}</div>
  </div>`;
}

async function ganChinhSachUyQuyen(goc) {
  if (!goc) return;
  const sua = dxCoQuyen("agent.dieu_khien");
  const ve = (d) => {
    goc.innerHTML = `<section class="panel dx-chinh-sach">
      <h2 class="panel__head">Chính sách &amp; Ủy quyền
        <span class="panel__note">AI được tự làm gì, việc gì phải có người duyệt</span></h2>
      <p class="row__sub">Chế độ AI hiện tại: <b>${d.che_do_chung === "auto" ? "Tự động" : "Gợi ý"}</b>.
        ${d.che_do_chung === "auto"
          ? "Mức của từng hành động dưới đây đang có hiệu lực."
          : "Ở chế độ Gợi ý, MỌI hành động thay đổi dữ liệu đều thành đề xuất chờ duyệt, bất kể mức bên dưới."}
        Hội thoại bật «Duyệt trước khi gửi» cũng được xử lý như Gợi ý.</p>
      <p class="row__sub hint">Tra cứu (sản phẩm, giá, tồn kho, đơn, vận chuyển, tài liệu) luôn được phép và không cần dòng nào ở đây.
        Hành động mới chưa có trong danh sách: mặc định <b>${esc(d.hanh_dong_la)}</b> (chuyển nhân viên).</p>
      <div class="rows">${d.hanh_dong.map((h) => dxDongChinhSach(h, sua)).join("")}</div>
      <label class="field dx-han"><span>Đề xuất hết hạn sau (giờ) <em class="hint">quá hạn thì không thi hành được nữa</em></span>
        <input type="number" min="1" max="${esc(d.han_toi_da_gio)}" data-dx-han value="${esc(d.han_gio)}"${sua ? "" : " disabled"}></label>
      <div class="rowbtns">
        ${sua ? '<button type="button" class="btn btn--sm btn--go" data-dx-luu>Lưu chính sách</button>'
              : '<span class="row__sub">Cần quyền agent.dieu_khien để sửa.</span>'}
        <span class="row__sub" data-dx-kq aria-live="polite"></span>
      </div>
    </section>`;
  };
  /* Lần đầu tab hiện, khe vừa gắn mô-đun vừa phát `tab:hien` — gộp hai lời
   * gọi đang bay làm một, không tải hai lần. */
  let dangNap = null;
  const nap = () => dangNap || (dangNap = (async () => {
    try { ve(await api("/ai-uy-quyen")); }
    catch (e) { goc.innerHTML = `<p class="empty">Không tải được chính sách: ${esc(e.message)}</p>`; }
  })().finally(() => { dangNap = null; }));
  goc.addEventListener("click", async (e) => {
    if (!e.target.closest("[data-dx-luu]")) return;
    const hanh_dong = {};
    $$("[data-dx-muc]", goc).forEach((s) => { hanh_dong[s.dataset.dxMuc] = { muc: s.value }; });
    $$("[data-dx-nguong]", goc).forEach((o) => {
      const ma = o.dataset.dxNguong;
      if (hanh_dong[ma] && o.value !== "") hanh_dong[ma].nguong_vnd = Number(o.value);
    });
    const han = $("[data-dx-han]", goc);
    const kq = $("[data-dx-kq]", goc);
    try {
      ve(await api("/ai-uy-quyen", { method: "PUT",
        body: JSON.stringify({ hanh_dong, han_gio: han && han.value ? Number(han.value) : null }) }));
      toast("Đã lưu chính sách ủy quyền");
    } catch (err) {
      if (kq) kq.textContent = err.message;
      toast(err.message, true);
    }
  });
  goc.addEventListener("tab:hien", nap);
  await nap();
}

window.GAN_TAB["ai-chinh-sach"] = (el) => ganChinhSachUyQuyen(el);

/* ---------- 2. Thẻ đề xuất trong hội thoại ---------- */

function dxDongHang(items) {
  return (items || []).map((it) => `<li>${esc(it.so_luong)} × ${esc(it.ten)}${
    it.don_gia != null ? ` — ${esc(dxTien(it.don_gia))}` : ""}</li>`).join("");
}

function dxTrangThaiDon(x) {
  if (!x) return "<p class=\"hint\">—</p>";
  const phan = [];
  if (x.trang_thai) phan.push(`<div><b>Trạng thái:</b> ${esc(x.trang_thai)}</div>`);
  if (x.items && x.items.length) phan.push(`<ul class="ctt__ds">${dxDongHang(x.items)}</ul>`);
  if (x.tong_tien != null) phan.push(`<div><b>Tổng:</b> ${esc(dxTien(x.tong_tien))}</div>`);
  if (x.nguoi_nhan) phan.push(`<div><b>Giao tới:</b> ${esc([x.nguoi_nhan, x.sdt, x.dia_chi].filter(Boolean).join(" · "))}</div>`);
  if (x.tra_kho && x.tra_kho.length) phan.push(`<div><b>Trả về kho:</b> ${esc(x.tra_kho.join(", "))}</div>`);
  if (x.ghi_chu) phan.push(`<div><b>Ghi chú:</b> ${esc(x.ghi_chu)}</div>`);
  return phan.join("") || "<p class=\"hint\">—</p>";
}

function dxKetQua(d) {
  if (d.trang_thai === "da_thuc_hien" && d.ket_qua) {
    const k = d.ket_qua;
    const dong = [
      k.ma_don ? `Mã đơn ${esc(k.ma_don)}` : "",
      k.qua === "man_don_hang" ? `Đã ${esc(k.viec || "xử lý")} ở màn Đơn hàng bởi ${esc(k.boi || "?")}` : "",
      k.can_huy_tay ? `⚠ ${esc(k.can_huy_tay)}` : "",
      k.can_hoan_tien ? `⚠ ${esc(k.can_hoan_tien)}` : "",
    ].filter(Boolean);
    return dong.length ? `<p class="row__sub">${dong.join("<br>")}</p>` : "";
  }
  if (d.trang_thai === "loi") return `<p class="row__sub"><b>Không thực hiện:</b> ${esc(d.loi || "")}</p>`;
  if (d.trang_thai === "tu_choi" && d.ly_do_tu_choi) return `<p class="row__sub"><b>Lý do từ chối:</b> ${esc(d.ly_do_tu_choi)}</p>`;
  return "";
}

/* Thẻ NỘI BỘ: phân biệt rõ với tin khách và tin đã gửi (17.10). */
function veTheDeXuat(d) {
  const dx = d.de_xuat || {};
  const cc = d.can_cu || {};
  const ai = [
    d.duyet_boi ? `duyệt bởi ${d.duyet_boi}` : "",
    d.tu_choi_boi ? `từ chối bởi ${d.tu_choi_boi}` : "",
  ].filter(Boolean).join(" · ");
  const ds = (mang) => (mang || []).map((x) => `<li>${esc(typeof x === "string" ? x : `${x.ten}: ${x.chi_tiet}`)}</li>`).join("");
  const nut = d.trang_thai === "cho_duyet"
    ? (d.duoc_duyet
      ? `<button type="button" class="btn btn--sm btn--go" data-dx-duyet="${esc(d.id)}">Phê duyệt</button>
         <button type="button" class="btn btn--sm btn--halt" data-dx-tu-choi="${esc(d.id)}">Từ chối</button>`
      : `<span class="row__sub hint">Cần quyền ${esc((d.thieu_quyen || []).join(" + "))} để duyệt.</span>`)
    : "";
  return `<div class="msg msg--dexuat" role="note" aria-label="Đề xuất hành động của AI — nội bộ">
    <div class="dx-the">
      <div class="dx-the__dau">
        <span class="dx-the__nhan">Đề xuất của AI · nội bộ, khách không thấy</span>
        <span class="tag tag--${DX_TAG[d.trang_thai] || "plain"}">${esc(d.nhan_trang_thai)}</span>
      </div>
      <b class="dx-the__tieu">${esc(dx.tieu_de || d.ten_hanh_dong)}</b>
      <p class="row__sub">${esc(dx.ly_do || "")}</p>
      <p class="row__sub"><b>Vì sao cần duyệt:</b> ${esc(d.ly_do_can_duyet)}</p>
      <div class="dx-the__hai">
        <div><h4 class="ctt__dau">Trước</h4>${dxTrangThaiDon(dx.truoc)}</div>
        <div><h4 class="ctt__dau">Sau khi thực hiện</h4>${dxTrangThaiDon(dx.sau)}</div>
      </div>
      <h4 class="ctt__dau">Căn cứ hệ thống đã kiểm</h4>
      ${(cc.nguon || []).length ? `<ul class="ctt__ds">${ds(cc.nguon)}</ul>` : '<p class="hint">Không có.</p>'}
      ${(cc.rui_ro || []).length ? `<h4 class="ctt__dau">Rủi ro</h4><ul class="ctt__ds">${ds(cc.rui_ro)}</ul>` : ""}
      ${(cc.thieu || []).length ? `<h4 class="ctt__dau">Điều kiện còn thiếu</h4><ul class="ctt__ds">${ds(cc.thieu)}</ul>` : ""}
      ${dxKetQua(d)}
      <div class="msg__meta">
        <span>${esc([gioTin(d.tao_luc), "AI Agent", d.trang_thai === "cho_duyet" && d.het_han_luc
          ? "hết hạn " + gioTin(d.het_han_luc) : "", ai].filter(Boolean).join(" · "))}</span>
        ${d.message_id ? `<button type="button" class="msg__goc-nut" data-dx-can-cu="${esc(d.message_id)}">Xem căn cứ lượt trả lời</button>` : ""}
        ${nut}
      </div>
    </div>
  </div>`;
}

/* Từ chối BẢN NHÁP AI: bản nháp thành "Đã huỷ", không gửi được nữa. Không
 * xoá — lịch sử phải còn thấy AI đã soạn gì và ai đã bác. */
document.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-tu-choi-nhap]");
  if (!nut) return;
  const v = await hoiHop({
    tieu_de: "Từ chối bản nháp AI", nut: "Từ chối", nguy_hiem: true,
    phu: "Bản nháp sẽ không gửi cho khách. Bạn tự trả lời khách ở ô soạn bên dưới.",
    truong: [{ name: "ly_do", label: "Lý do (không bắt buộc)", type: "textarea", maxlength: 500 }],
  });
  if (v === null) return;
  try {
    await api(`/messages/${nut.dataset.tuChoiNhap}/tu-choi`, {
      method: "POST", body: JSON.stringify({ ly_do: v.ly_do || "" }) });
    toast("Đã từ chối bản nháp");
  } catch (err) {
    toast(err.message, true);
  }
  if (state.openConv) await loadThread(state.openConv);
});

document.addEventListener("click", async (e) => {
  const duyet = e.target.closest("[data-dx-duyet]");
  const tuChoi = e.target.closest("[data-dx-tu-choi]");
  const canCu = e.target.closest("[data-dx-can-cu]");
  if (canCu) {
    state.chiTietTin = state.chiTietTin || new Set();
    state.chiTietTin.add(String(canCu.dataset.dxCanCu));
    if (state.openConv) await loadThread(state.openConv);
    return;
  }
  if (!duyet && !tuChoi) return;
  const nut = duyet || tuChoi;
  try {
    if (duyet) {
      nut.disabled = true;
      const r = await api(`/ai-de-xuat/${duyet.dataset.dxDuyet}/duyet`, { method: "POST" });
      toast(r.ok ? "Đã duyệt và thực hiện" : `Đã duyệt nhưng không thực hiện được: ${r.loi || ""}`, !r.ok);
    } else {
      const v = await hoiHop({
        tieu_de: "Từ chối đề xuất của AI", nut: "Từ chối", nguy_hiem: true,
        truong: [{ name: "ly_do", label: "Lý do (không bắt buộc)", type: "textarea", maxlength: 500 }],
      });
      if (v === null) return;
      const r = await api(`/ai-de-xuat/${tuChoi.dataset.dxTuChoi}/tu-choi`, {
        method: "POST", body: JSON.stringify({ ly_do: v.ly_do || "" }) });
      toast(r.canh_bao || "Đã từ chối đề xuất", !!r.canh_bao);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    nut.disabled = false;
    if (state.openConv) await loadThread(state.openConv);
  }
});
