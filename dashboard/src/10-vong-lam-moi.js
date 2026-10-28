/* ---------------- vòng làm mới ---------------- */

async function refresh() {
  try {
    await loadOverview();
    if (state.view === "ca") { await loadTinChet(); await loadVoChu(); await loadCaCuaToi(); }
    if (state.view === "hoithoai") await loadConversations();
    if (state.view === "khachhang") { await loadTruongKhach(); await loadContacts(); }
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "video") { await fillProductPicker(); await loadVideos(); }
    if (state.view === "dangbai") { await fillPostPickers(); await loadPosts(); await loadPubChannels(); }
    if (state.view === "hethong") await loadHeThong();
    if (state.view === "ketnoi") { await loadHoSoAgent(); await loadKetNoi(); await loadTichHop(); }
    if (state.view === "sohieu") {
      if (!state.bcnvDaTai) await loadBaoCaoNhanVien();
      await loadAnalyticsKhach(); await loadAnalytics(); await loadCost();
    }
    if (state.view === "trithuc") await loadDocs();
    if (state.view === "kynang") await loadKyNang();
    if (state.view === "phongthu" && !state.phongThuDaTai) await loadPhongThu();
    if (state.view === "cauhinh") { await loadMauNhanh(); await loadQuyTac(); await loadDinhTuyen(); await loadTamNhin(); await loadHoSoAgent(); await loadTruongKhach(); await loadCauHinh(); await loadCaiDatApi(); }
    if (state.view === "congviec") await loadCongViec();
    if (state.view === "nhansu") { await loadNhanSu(); await loadLichCa(); }
    if (state.view === "nhatky") { await loadPdpdPolicy(); await loadRetention(); await loadEvents(); }
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

