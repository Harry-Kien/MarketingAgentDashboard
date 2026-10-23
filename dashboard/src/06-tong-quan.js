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

