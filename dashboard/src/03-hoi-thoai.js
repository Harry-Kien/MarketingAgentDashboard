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

function convRow(c, hangDoi) {
  // Nhãn của hội thoại đang mở lấy từ DÒNG danh sách (đã có sẵn trong phản
  // hồi), khỏi thêm một request nữa mỗi 6 giây.
  if (Array.isArray(c.nhan)) {
    state.nhanTheoHoiThoai = state.nhanTheoHoiThoai || {};
    state.nhanTheoHoiThoai[c.id] = c.nhan;
  }
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
      ${(c.nhan || []).length ? `<span class="row__nhan">${c.nhan.map((n) =>
        `<span class="nhan">${esc(n)}</span>`).join("")}</span>` : ""}
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
      doiMan("hoithoai");
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
  let query = state.convFilter === "all" ? "" : `&status=${encodeURIComponent(state.convFilter)}`;
  if (state.convTim) query += `&q=${encodeURIComponent(state.convTim)}`;
  if (state.convNhan) query += `&nhan=${encodeURIComponent(state.convNhan)}`;
  const [result, nhanDs] = await Promise.all([
    api("/inbox/conversations?limit=100" + query),
    api("/inbox/nhan").catch(() => ({ nhan: [] })),
  ]);
  veLocNhan(nhanDs.nhan || []);
  const list = result.items || [];
  $("#convlist").innerHTML = list.length
    ? list.map(convRow).join("")
    : `<p class="empty">${state.convTim || state.convNhan
        ? "Không có hội thoại nào khớp." : "Chưa có hội thoại nào."}</p>`;
  wireConvRows("#convlist");
  if (state.openConv) await loadThread(state.openConv);
}

async function loadThread(id) {
  let c;
  let ghiChu = [];
  try {
    [c, ghiChu] = await Promise.all([
      api("/inbox/conversations/" + id),
      api(`/inbox/conversations/${id}/ghi-chu`).then((r) => r.ghi_chu).catch(() => []),
    ]);
  }
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
      ${c.state !== "resolved" ? `<button type="button" class="btn btn--sm btn--go" id="btn-giai-quyet"
        title="Đóng vụ việc: SLA giải quyết được tính, khách nhắn tiếp thì tự mở lại">Đã giải quyết</button>`
        : '<span class="tag tag--auto">Đã giải quyết</span>'}
      <button type="button" class="btn btn--sm ${taken ? "" : "btn--halt"}" id="btn-take">
        ${taken ? "Kết thúc tiếp quản" : "Tôi tiếp quản"}
      </button>
    </div>
    <div class="nhanbar">
      ${(state.nhanTheoHoiThoai && state.nhanTheoHoiThoai[id] || []).map((n) =>
        `<span class="nhan">${esc(n)}<button type="button" class="nhan__go" data-go-nhan="${esc(n)}"
          aria-label="Gỡ nhãn ${esc(n)}">×</button></span>`).join("")}
      <button type="button" class="btn btn--sm btn--ghost" id="btn-them-nhan">+ Nhãn</button>
      <button type="button" class="btn btn--sm btn--ghost" id="btn-them-ghichu">+ Ghi chú nội bộ</button>
    </div>
    ${ghiChu.length ? `<details class="ghichu" ${state.moGhiChu ? "open" : ""}>
      <summary>Ghi chú nội bộ (${ghiChu.length}) — khách không thấy</summary>
      ${ghiChu.map((g) => `<div class="ghichu__dong"><b>${esc(g.nguoi || "—")}</b>
        <span class="msg__meta">${clock(g.tao_luc)}</span><p>${esc(g.noi_dung)}</p></div>`).join("")}
    </details>` : ""}
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
    // Gắn TRƯỚC phím Enter-gửi bên dưới: khi khung mẫu đang mở, Enter là
    // "chọn mẫu", và trình nghe này chặn không cho nó tới trình gửi tin.
    ganMauNhanh(o_moi);
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

