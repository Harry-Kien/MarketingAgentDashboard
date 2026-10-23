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
    const so = (name, label) => ({ name, label, type: "number", value: 0, min: 0, step: 1 });
    const d = await hoiHop({
      tieu_de: "Ghi số liệu bài đăng",
      phu: "Chép từ trang quản lý của nền tảng. Cùng một bảng, cùng một biểu đồ với số liệu tự lấy.",
      truong: [so("luot_xem", "Lượt xem"), so("luot_thich", "Lượt thích"),
               so("binh_luan", "Bình luận"), so("chia_se", "Chia sẻ")],
      nut: "Ghi số liệu",
    });
    if (!d) return;
    const n = (v) => parseInt(v, 10) || 0;
    try {
      await api("/posts/" + b.dataset.pmetric + "/metrics", { method: "POST", body: JSON.stringify({
        kenh: b.dataset.pkenh, luot_xem: n(d.luot_xem), luot_thich: n(d.luot_thich),
        binh_luan: n(d.binh_luan), chia_se: n(d.chia_se),
      })});
      toast("Đã ghi số liệu."); loadAnalytics();
    } catch (e) { toast(e.message, true); }
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
    const d = await hoiHop({
      tieu_de: "Đã đăng bài này",
      phu: "Dán link bài vừa đăng để về sau đo hiệu quả. Để trống vẫn ghi nhận được.",
      truong: [{ name: "url", label: "Link bài đăng", type: "url", placeholder: "https://…" }],
      nut: "Ghi nhận",
    });
    if (!d) return;
    try {
      await api(`/posts/${id}/mark-posted`, { method: "POST", body: JSON.stringify({
        kenh: box.querySelector("[data-posted]").dataset.kenh, ok: true, url: d.url || "",
      })});
      toast("Đã ghi nhận."); loadPosts();
    } catch (e) { toast(e.message, true); }
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

