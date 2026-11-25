/* ---------------- danh sách tài khoản kênh (hợp nhất) ----------------
 *
 * Tách khỏi 10-vong-lam-moi.js (quá 1000 dòng).
 *
 * MỘT CHỖ CHO MỖI TÀI KHOẢN (UX-08-02, UX-20-02)
 * ----------------------------------------------
 * Trước đây cùng một tài khoản hiện ở BA nơi: "Sức khoẻ kênh", lưới tài
 * khoản, và "Kênh nhắn tin (plugin)" ở cuối trang — ba nhãn trạng thái khác
 * nhau ("Sẵn sàng", chấm đỏ, "Kết nối thành công") cho cùng một thứ. Người
 * vận hành tin nhãn to nhất, và nhãn to nhất là nhãn sai (UX-20-01).
 *
 * Nay mỗi tài khoản là MỘT dòng: một trạng thái (máy chủ suy từ sức khoẻ
 * thật — agent/omnichannel/suc_khoe_kenh.py `trang_thai_ket_noi`), một câu
 * việc cần làm, một nút chính. Mọi thứ khác — thao tác chia theo mục đích,
 * mã kỹ thuật, webhook — nằm trong "Quản lý" / "Chi tiết nâng cao", đóng sẵn.
 */

/* Số tài khoản hiện sẵn trước khi thu gọn.
 *
 * Một tài khoản Facebook có thể quản lý hàng chục Trang. Đổ hết ra màn hình
 * thì mọi kênh khác — Zalo, Webchat — bị đẩy xuống dưới tầm nhìn, và người
 * trực phải cuộn rất lâu mới thấy thứ mình cần.
 *
 * Năm là đủ để thấy kênh có gì mà không nuốt mất cả trang. */
const SO_HIEN_SAN = 5;

const KENH_META = ["facebook", "instagram", "whatsapp"];
const KENH_KET_NOI = ["zalo_personal", "zalo_oa", "facebook", "instagram", "whatsapp", "webchat"];

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

/* Nhãn của `status` THÔ — chỉ còn dùng ở "Lần kiểm gần nhất" (02-van-hanh.js)
 * và trong Chi tiết nâng cao. Nhãn người vận hành thấy trên dòng là trạng
 * thái hợp nhất từ máy chủ. */
const ACCOUNT_STATUS_LABEL = {
  pending: "Chờ xác minh", active: "Sẵn sàng", degraded: "Gián đoạn",
  reauth_required: "Cần đăng nhập lại", disabled: "Đã tạm ngắt",
};

/* Chỉ dùng khi vòng sức khoẻ CHƯA về (lần vẽ đầu tiên): luật thật nằm ở máy
 * chủ, bảng này chỉ để dòng không trống trong một nhịp. Trạng thái lạ rơi về
 * "loi" như máy chủ — xanh giả nguy hiểm hơn đỏ giả. */
const KN_TT_TAM = { active: "hoat_dong", pending: "chua_ket_noi", degraded: "loi",
  reauth_required: "can_xac_thuc", disabled: "tam_ngat" };

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

/* Mã lỗi một mình KHÔNG hành động được.
 *
 * `provider.unreachable` đúng cho cả "sidecar chưa bật" lẫn "mạng chết"
 * lẫn "token hết hạn" — ba việc phải làm hoàn toàn khác nhau. Máy chủ trả
 * kèm `detail.ly_do`; giao diện ghép lý do + gợi ý, mã để CUỐI trong ngoặc
 * (UX-20-05): người đọc thấy lời trước, mã vẫn còn để tra cứu và nhắn cho
 * người khác.
 *
 * Ở CẤP TỆP, không lồng trong loadKetNoi như trước: form thêm kênh
 * (10-vong-lam-moi.js) và nút Sức khoẻ kênh (18-ket-noi-kenh.js) gọi nó từ
 * ngoài, và hàm lồng thì ở ngoài là ReferenceError — người dùng thấy
 * "lyDoKetNoi is not defined" thay cho lý do. */
const GOI_Y_LOI = {
  "provider.unreachable": "Không liên lạc được với nền tảng — kiểm tra dịch vụ trung gian (sidecar) đã chạy chưa.",
  "provider.unauthorized": "Nền tảng từ chối thông tin đăng nhập — token sai hoặc đã hết hạn, hãy kết nối lại.",
  "provider.rejected": "Nền tảng từ chối yêu cầu — xem lý do ở trên.",
  "provider.invalid_response": "Nền tảng trả về dữ liệu không đọc được — thử lại sau ít phút.",
  "provider.token_expired": "Token đã hết hạn — đăng nhập lại để gia hạn.",
  "provider.not_connected": "Tài khoản chưa đăng nhập — hoàn tất bước Quét QR / Đăng nhập.",
};

function lyDoKetNoi(kq) {
  const ma = kq && kq.code;
  const ly_do = kq && kq.detail && kq.detail.ly_do;
  const cau = [GOI_Y_LOI[ma], ly_do].filter(Boolean).join(" — ") || "Nền tảng chưa xác nhận kết nối.";
  return ma ? `${cau} (mã: ${ma})` : cau;
}

/* ---------------- trạng thái mở/đóng sống qua vòng làm mới ----------------
 *
 * Lưới dựng lại innerHTML khi dữ liệu đổi; `<details>` người dùng vừa mở mà
 * đóng sập sau vài giây là lý do người ta thôi bấm. Nhớ theo khoá
 * `data-kn-mo`, ghi bằng sự kiện `toggle` (không nổi bọt -> bắt ở pha capture). */
function knMo(khoa, macDinh = false) {
  const m = (state.knMo || {})[khoa];
  return (m === undefined ? macDinh : m) ? " open" : "";
}
document.addEventListener("toggle", (e) => {
  const d = e.target;
  if (!(d instanceof HTMLDetailsElement) || !d.dataset.knMo) return;
  state.knMo = state.knMo || {};
  state.knMo[d.dataset.knMo] = d.open;
}, true);

/* Trạng thái hợp nhất của một tài khoản: của máy chủ nếu vòng sức khoẻ đã về. */
function knTrangThai(account) {
  const h = (state.knSucKhoe || {})[account.id];
  if (h && h.trang_thai) return h;
  const tt = KN_TT_TAM[account.status] || "loi";
  return { trang_thai: tt, nhan_trang_thai: (state.knNhanTT || {})[tt] || ACCOUNT_STATUS_LABEL[account.status] || tt,
    viec: account.ly_do_hong || "", hanh_dong: "", canh_bao: false, giai_thich: null };
}

function knPillTT(h) {
  return `<span class="knh-tt knh-tt--${esc(h.trang_thai)}">${esc(h.nhan_trang_thai)}</span>${
    h.canh_bao ? ' <span class="knh-tt knh-tt--canh-bao">Cần để ý</span>' : ""}`;
}

/* Câu "việc cần làm" của sức khoẻ — trừ khi nó chính là lý do THÔ của nền
 * tảng (kiểu "ECONNREFUSED <địa chỉ sidecar>"): khi ấy lời giải thích đã nói thay,
 * còn bản thô nằm ở Chi tiết nâng cao (UX-20-05). */
function knViecDeDoc(h) {
  const g = h.giai_thich;
  if (g && g.ly_do_goc && String(h.viec || "").trim() === g.ly_do_goc) return "";
  return h.viec || "";
}

/* Lỗi = chuyện gì + vì sao + làm gì; mã thô xuống Chi tiết nâng cao. */
function knLoiDeDoc(g) {
  if (!g) return "";
  return `<div class="knh-loi" role="note"><b>${esc(g.tieu_de)}</b>
    <span><em>Nguyên nhân:</em> ${esc(g.nguyen_nhan)}</span>
    <span><em>Cách xử lý:</em> ${esc(g.cach_sua)}</span></div>`;
}

/* Nhóm nút theo MỤC ĐÍCH (UX-08-05, UX-20-06): người bấm biết trước nút ấy
 * làm gì và ảnh hưởng tới đâu, không phải đoán từ một hàng sáu nút giống nhau. */
function knNhomNut(ten, ghi, nut, nguyHiem = false) {
  if (!nut.trim()) return "";
  return `<div class="knh-nhom${nguyHiem ? " knh-nhom--nguy" : ""}">
    <span class="knh-nhom__ten">${esc(ten)}</span>
    <div class="knh-nhom__nut">${nut}</div>
    <p class="knh-nhom__ghi">${esc(ghi)}</p></div>`;
}

function knNangCaoTaiKhoan(account, h, t) {
  const g = h.giai_thich;
  const callback = connectionCallback(account);
  const dong = [
    ["Mã trạng thái", `<code>${esc(account.status)}</code> (${esc(ACCOUNT_STATUS_LABEL[account.status] || account.status)})`],
    g ? ["Mã lỗi", `<code>${esc(g.ma)}</code>`] : null,
    g && g.ly_do_goc ? ["Lý do gốc từ nền tảng", esc(g.ly_do_goc)] : null,
    ["ID trên nền tảng", esc(account.external_account_id || "chưa có")],
    callback ? ["Callback URL", `<code class="callback">${esc(callback)}</code>`] : null,
    t && t.url_webhook ? ["Webhook", `<code class="callback">${esc(t.url_webhook)}</code>`] : null,
    t ? ["Xác minh gần nhất", t.kiem ? `${esc(knttLuc(t.kiem.luc))} · <code>${esc(t.kiem.code || "")}</code>${
      t.kiem.ly_do ? " — " + esc(t.kiem.ly_do) : ""}` : "Chưa xác minh lần nào."] : null,
    t ? ["Webhook nhận vào", knttThongKe(t.webhook)] : null,
  ].filter(Boolean);
  const lsWh = (state.knLsWh || {})[account.id] || "";
  return `<details class="knh-nangcao" data-kn-mo="nc:${esc(account.id)}"${knMo("nc:" + account.id)}>
    <summary>Chi tiết nâng cao</summary>
    <dl class="knh-dl">${dong.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>
    ${t ? `<div class="rowbtns"><button type="button" class="btn btn--sm btn--ghost" data-kntt-lstk="${esc(account.id)}">Lịch sử webhook</button></div>
      <div class="kntt-lstk">${lsWh}</div>` : ""}
  </details>`;
}

function knDongTaiKhoan(account) {
  const h = knTrangThai(account);
  const tt = h.trang_thai;
  const t = (state.knttTk || {})[account.id];
  const tat = account.status === "disabled";
  const nutChinh = h.hanh_dong && KN_NUT[h.hanh_dong]
    ? `<button type="button" class="btn btn--sm${["loi", "can_xac_thuc"].includes(tt) ? " btn--primary" : ""}"
         data-kn-lam="${esc(h.hanh_dong)}" data-kn-id="${esc(account.id)}">${esc(KN_NUT[h.hanh_dong])}</button>` : "";
  const fb = t && t.an_binh_luan_co_sdt
    ? `<label class="field kntt-fb"><span>Tự ẩn bình luận có số điện thoại</span>
        <select data-kntt-fb="${esc(account.id)}">
          <option value="chung"${t.an_binh_luan_co_sdt.rieng ? "" : " selected"}>Theo cấu hình chung (đang ${
            t.an_binh_luan_co_sdt.chung === "bat" ? "bật" : "tắt"})</option>
          <option value="bat"${t.an_binh_luan_co_sdt.rieng === "bat" ? " selected" : ""}>Bật cho Trang này</option>
          <option value="tat"${t.an_binh_luan_co_sdt.rieng === "tat" ? " selected" : ""}>Tắt cho Trang này</option>
        </select></label>` : "";
  const nhom = [
    knNhomNut("Kết nối", "Đăng nhập hoặc làm mới phiên với nền tảng.", [
      account.channel === "zalo_personal" ? `<button type="button" class="btn btn--sm" data-qr="${account.id}" data-dang-chay="${account.status === "active" ? "1" : "0"}">Quét QR</button>` : "",
      ["facebook", "instagram"].includes(account.channel) && account.status === "pending"
        ? `<button type="button" class="btn btn--sm" data-subwebhook="${account.id}">Nhận tin</button>` : "",
    ].join("")),
    knNhomNut("Kiểm tra", "Chỉ hỏi nền tảng và ghi kết quả — không đổi cấu hình.", [
      tat ? "" : `<button type="button" class="btn btn--sm" data-verify="${account.id}">Kiểm tra kết nối</button>`,
      `<button type="button" class="btn btn--sm btn--ghost" data-health="${account.id}">Lần kiểm gần nhất</button>`,
      `<button type="button" class="btn btn--sm btn--ghost" data-kn-dtg="${esc(account.id)}">Dòng thời gian</button>`,
    ].join("")),
    knNhomNut("Điều khiển AI", "Bật/tắt AI trả lời riêng tài khoản này. Tin khách vẫn vào, tắt thì chuyển cho người.", [
      `<button type="button" class="btn btn--sm" data-agentbat="${account.id}"
        data-bat="${account.agent_bat === false ? "1" : "0"}">${account.agent_bat === false ? "Bật AI" : "Tắt AI"}</button>`,
      hoSoAgent.ds.length ? `<select class="hsa-chon" data-hsagan="${account.id}"
        title="Hồ sơ agent trả lời kênh này" aria-label="Hồ sơ agent cho ${esc(account.display_name)}">
        <option value="">Hồ sơ mặc định</option>
        ${hoSoAgent.ds.map((x) => `<option value="${esc(x.id)}"${x.id === account.agent_ho_so_id ? " selected" : ""}>${esc(x.ten)}</option>`).join("")}
      </select>` : "",
    ].join("")),
    fb ? knNhomNut("Tuỳ chọn Trang", "Áp dụng riêng cho Trang này.", fb) : "",
    knNhomNut("Quản lý tài khoản", "Tạm ngắt: ngừng nhận và gửi tin, giữ dữ liệu. Xoá: vĩnh viễn, chỉ khi chưa có hội thoại.", [
      tat ? `<button type="button" class="btn btn--sm" data-kn-lam="bat_lai" data-kn-id="${esc(account.id)}">Bật lại</button>`
        : `<button type="button" class="btn btn--sm" data-disable="${account.id}" data-ten-tk="${esc(account.display_name)}">Tạm ngắt</button>`,
      `<button type="button" class="btn btn--sm btn--halt" data-xoa-tk="${account.id}"
        data-ten-tk="${esc(account.display_name)}">Xoá</button>`,
    ].join(""), true),
  ].join("");
  return `<article class="account-line knh-tk knh-tk--${esc(tt)}" id="kn-tk-${esc(account.id)}">
    <span class="health-dot knh-cham knh-cham--${esc(tt)}" aria-hidden="true"></span>
    <div class="knh-tk__than">
      <div class="knh-tk__dau"><b>${esc(account.display_name)}</b> ${knPillTT(h)}${account.agent_bat === false
        /* Kênh đang TẮT AI phải nhìn thấy được ngay trên dòng: không hiện thì
           "vì sao kênh này không ai trả lời tự động" là câu hỏi không có chỗ
           nào trả lời — người ta đi kiểm token, kiểm sidecar, kiểm mạng. */
        ? ` <span class="knh-tt knh-tt--ai-tat" title="${esc(account.agent_tat_ly_do || "không ghi lý do")}">AI đang tắt</span>` : ""}</div>
      ${knViecDeDoc(h) ? `<small class="knh-tk__viec">${esc(knViecDeDoc(h))}</small>` : ""}
      ${tt === "hoat_dong" && !h.canh_bao ? "" : knLoiDeDoc(h.giai_thich)}
    </div>
    <div class="knh-tk__chinh">${nutChinh}</div>
    <details class="knh-quanly" data-kn-mo="tk:${esc(account.id)}"${knMo("tk:" + account.id)}>
      <summary>Quản lý tài khoản</summary>
      <div class="knh-nhom-ds">${nhom}</div>
      <div class="token-slot" data-tokenslot="${account.id}">${
      /* Kết quả "Lần kiểm gần nhất" phải SỐNG QUA vòng làm mới 6 giây. */
      (state.sucKhoeKenh || {})[account.id] || ""}</div>
      ${knNangCaoTaiKhoan(account, h, t)}
    </details>
  </article>`;
}

/* "Khả năng được nền tảng hỗ trợ" — tách hẳn khỏi trạng thái (MD-UX-20-02):
 * dải huy hiệu ✓ xanh từng bị đọc thành "tài khoản của tôi gửi ảnh được",
 * trong khi đó là khả năng của ADAPTER, đúng cả khi tài khoản đang lỗi. */
function knKhaNang(p) {
  if (!p || !p.kha_nang || !p.kha_nang.length) return "";
  const co = p.kha_nang.filter((k) => k.co).length;
  return `<details class="knh-khanang" data-kn-mo="kn:${esc(p.ma)}"${knMo("kn:" + p.ma)}>
    <summary>Khả năng được nền tảng hỗ trợ <span class="hint">${co}/${p.kha_nang.length}</span></summary>
    <p class="knh-ghi">Đây là khả năng của nền tảng, KHÔNG phải trạng thái tài khoản — tài khoản chỉ dùng được
      khi ở trạng thái <b>Hoạt động</b>.</p>
    <ul class="knh-khanang__ds">${p.kha_nang.map((k) => `<li class="${k.co ? "is-co" : "is-khong"}"
      aria-label="${esc(k.nhan)}: ${k.co ? "có" : "chưa hỗ trợ"}"><span aria-hidden="true">${k.co ? "✓" : "—"}</span> ${esc(k.nhan)}</li>`).join("")}</ul>
  </details>`;
}

function knNangCaoKenh(channel, items, p) {
  const url = callbackTheoKenh(channel);
  const wh = p && p.webhook;
  const meta = KENH_META.includes(channel) && items.length;
  if (!url && !wh && !meta) return "";
  return `<details class="knh-nangcao" data-kn-mo="nck:${esc(channel)}"${knMo("nck:" + channel)}>
    <summary>Chi tiết nâng cao của kênh (webhook)</summary>
    ${url ? `<p class="row__sub">Callback URL — khai đúng MỘT lần bên nền tảng:</p>
      <code class="callback" title="Khai đúng MỘT lần bên nhà cung cấp">${esc(url)}</code>` : ""}
    ${meta ? `<div class="rowbtns"><button type="button" class="btn btn--sm" data-verifytoken-kenh="${items[0].id}">Xem verify token</button></div>
      <div class="token-slot" data-tokenslot-kenh="${esc(channel)}">${oTokenDaHien(channel)}</div>` : ""}
    ${wh ? `<p class="row__sub">${esc(wh.xac_minh)}</p>
      <p class="row__sub">Sự kiện: ${(wh.su_kien || []).map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}` : ""}
  </details>`;
}

/* Kênh CHƯA có tài khoản: một dòng gọn kèm hướng dẫn và nút nối (UX-20-04),
 * không phải một thẻ to chỉ để nói "Chưa kết nối tài khoản nào". */
const KN_NOI_THEO_KENH = { facebook: "meta", instagram: "meta", zalo_oa: "zalo_oa",
  zalo_personal: "zalo_personal", webchat: "webchat", whatsapp: "whatsapp" };
const KN_GOI_Y_NOI = {
  facebook: "Đăng nhập Facebook, chọn Trang.",
  instagram: "Nối cùng Trang Facebook đã liên kết Instagram Business.",
  zalo_oa: "Đăng nhập Zalo, chọn OA — kênh chính thức.",
  zalo_personal: "Đặt tên rồi quét QR bằng app Zalo.",
  webchat: "Nhập địa chỉ website, dán một đoạn mã.",
  whatsapp: "Nhập Phone number ID và token từ Meta.",
};

function knKenhChuaNoi(ds) {
  if (!ds.length) return "";
  const dn = state.knDangNhap || {};
  return `<section class="knh-chua-noi" aria-label="Kênh chưa kết nối">
    <h3 class="knh-chua-noi__dau">Kênh chưa kết nối <span class="hint">nối khi cần — chưa có tài khoản nào</span></h3>
    <ul class="knh-chua-noi__ds">${ds.map((ch) => {
      const noi = KN_NOI_THEO_KENH[ch];
      const khoa = (noi === "meta" && dn.meta === false) || (noi === "zalo_oa" && dn.zalo_oa === false);
      const vi = noi === "meta" ? "Chưa khai ứng dụng Meta trong .env" : "Chưa khai ứng dụng Zalo OA trong .env";
      return `<li>${srcBadge(ch)}<span class="knh-chua-noi__goi-y">${esc(KN_GOI_Y_NOI[ch] || "")}${
        khoa ? ` <em class="hint">${esc(vi)}.</em>` : ""}</span>
        <button type="button" class="btn btn--sm" data-kn-noi-nhanh="${esc(noi)}"${khoa ? ` disabled title="${esc(vi)}"` : ""}>Kết nối</button></li>`;
    }).join("")}</ul>
  </section>`;
}

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
  const coTk = KENH_KET_NOI.filter((ch) => (grouped[ch] || []).length);
  const chuaNoi = KENH_KET_NOI.filter((ch) => !(grouped[ch] || []).length);
  const html = coTk.map((channel) => {
    const items = grouped[channel];
    const p = ((state.knttKenh || {}).theoKenh || {})[channel];
    const cho_xac_minh = items.filter((a) => a.status === "pending").length;
    const dem = {};
    items.forEach((a) => { const tt = knTrangThai(a).trang_thai; dem[tt] = (dem[tt] || 0) + 1; });
    const tomTat = Object.entries(dem).map(([tt, n]) =>
      `${n} ${((state.knNhanTT || {})[tt] || tt).toLowerCase()}`).join(" · ");
    /* Việc CHUNG của cả kênh gom lên đây, không nhân lên theo số tài khoản:
     * một nút đăng ký webhook hàng loạt là thứ cần thấy ngay; URL callback và
     * verify token là chi tiết kỹ thuật, nằm trong phần nâng cao. */
    const viecChung = KENH_META.includes(channel) && cho_xac_minh
      ? `<div class="channel-card__chung"><span class="row__sub">${cho_xac_minh} Trang chưa bật nhận tin.</span>
          <span class="channel-card__actions"><button type="button" class="btn btn--sm btn--go" data-subwebhook-all="${channel}">Nhận tin cho tất cả (${cho_xac_minh})</button></span></div>` : "";

    return `<section class="channel-card knh-kenh">
      <div class="channel-card__head">${srcBadge(channel)}<div><h3>${esc((p && p.ten) || CHANNEL_LABEL[channel])}</h3><p>${esc(tomTat)}</p></div>
        <span class="channel-card__count" title="Số tài khoản">${items.length}</span></div>
      ${viecChung}
      <div class="channel-card__body${items.length > SO_HIEN_SAN ? " is-thu-gon" : ""}"
           data-body="${channel}">${items.map(knDongTaiKhoan).join("")}</div>
      ${items.length > SO_HIEN_SAN ? `<button type="button" class="channel-card__them" data-mo="${channel}"
        data-them="Xem thêm ${items.length - SO_HIEN_SAN} tài khoản" data-bot="Thu gọn">
        Xem thêm ${items.length - SO_HIEN_SAN} tài khoản</button>` : ""}
      <div class="knh-kenh__chan">${knKhaNang(p)}${knNangCaoKenh(channel, items, p)}</div>
    </section>`;
  }).join("") + knKenhChuaNoi(chuaNoi);

  /* KHÔNG dựng lại khi không có gì đổi. Vòng làm mới gọi hàm này 6 giây một
   * lần; dựng lại vô cớ là đóng ô chọn hồ sơ đang thả xuống và cướp tiêu
   * điểm bàn phím của người đang thao tác. Listener gắn bên dưới vẫn còn
   * trên đúng các phần tử cũ, nên dừng ở đây là an toàn. */
  const luoi = $("#connectiongrid");
  if (luoi._knHtml === html) return;
  luoi._knHtml = html;
  luoi.innerHTML = html || '<p class="empty">Chưa nối kênh nào — bắt đầu ở mục Nối kênh mới.</p>';

  $$('[data-verify]').forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const result = await api(`/channel-accounts/${button.dataset.verify}/verify`, { method: "POST" });
      toast(result.ok ? "Kết nối tốt — nền tảng đã xác nhận tài khoản."
        : `Chưa xác minh được: ${lyDoKetNoi(result)}`, !result.ok);
      await loadSucKhoeKenh();
      loadKetNoi();
    } catch (e) { toast(e.message, true); }
    finally { button.disabled = false; }
  }));
  $$('[data-health]').forEach((b) => b.addEventListener("click", () => kenhSucKhoe(b)));

  /* Tạm ngắt HỎI TRƯỚC và nói hậu quả: bản cũ bấm là ngắt ngay, đứng sát
     nút "Kiểm tra" — một cú bấm trượt là khách nhắn vào hư không. */
  $$('[data-disable]').forEach((button) => button.addEventListener("click", async () => {
    const ten = button.dataset.tenTk || "tài khoản này";
    const ok = await hoiHop({
      tieu_de: `Tạm ngắt “${ten}”?`,
      phu: "Tài khoản ngừng nhận và gửi tin cho tới khi bật lại — tin khách gửi trong lúc ngắt KHÔNG vào hệ thống. Lịch sử hội thoại và thông tin đăng nhập vẫn giữ nguyên.",
      nut: "Tạm ngắt", nguy_hiem: true,
    });
    if (!ok) return;
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
    /* Hỏi LÝ DO khi tắt, không hỏi khi bật: lý do đi vào cột, nhật ký và
     * hiện ngay trên dòng tài khoản — người hỏi "vì sao kênh này AI không
     * trả lời" vài tuần sau có câu trả lời. */
    let ly_do = "";
    if (!bat) {
      const d = await hoiHop({
        tieu_de: "Tắt AI cho tài khoản này",
        phu: "Tin khách vẫn vào và vẫn chuyển cho người — hệ thống tự tạo một công việc cho mỗi hội thoại.",
        truong: [{
          name: "ly_do", label: "Lý do", hint: "hiện trên dòng tài khoản và trong nhật ký",
          placeholder: "Ví dụ: Trang không phải shop mỹ phẩm", maxlength: 300
        }],
        nut: "Tắt AI", nguy_hiem: true,
      });
      if (!d) return;
      ly_do = d.ly_do || "";
    }
    try {
      const d = await api(`/channel-accounts/${button.dataset.agentbat}/agent`, {
        method: "POST", body: JSON.stringify({ bat, ly_do }),
      });
      toast(d.agent_bat
        ? `AI đã bật lại cho “${d.display_name}”.`
        : `AI đã tắt cho “${d.display_name}”. Tin khách vẫn vào và chuyển cho người.`);
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
    const ok = await hoiHop({
      tieu_de: `Xoá vĩnh viễn “${ten}”?`,
      phu: "Thông tin đăng nhập đã lưu bị xoá theo và KHÔNG khôi phục được; muốn dùng lại phải nối lại từ đầu. Tài khoản này chưa có hội thoại nào nên không mất lịch sử. Chỉ muốn dừng tạm thời thì dùng “Tạm ngắt”.",
      nut: "Xoá vĩnh viễn", nguy_hiem: true,
    });
    if (!ok) return;

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

  /* Quét lại QR khi phiên ĐANG chạy là đăng nhập lại từ đầu: hỏi trước, nói
     rõ trong lúc chờ quét tin có thể gián đoạn. Phiên đã hỏng thì quét ngay. */
  $$('[data-qr]').forEach((button) => button.addEventListener("click", async () => {
    if (button.dataset.dangChay === "1" && !(await hoiHop({
      tieu_de: "Quét lại mã QR?",
      phu: "Tài khoản đang hoạt động. Quét lại sẽ đăng nhập lại phiên Zalo; trong lúc chờ quét, tin có thể gián đoạn vài phút.",
      nut: "Quét lại",
    }))) return;
    quetQR(button.dataset.qr);
  }));

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

    /* NÓI RA phần hỏng, không gộp vào một chữ "xong": báo "đã đăng ký 26
     * Trang" trong khi 4 Trang lỗi là xanh giả. */
    if (hong.length) {
      toast(`${xong} Trang đã đăng ký. ${hong.length} Trang HỎNG — xem mục Nhật ký.`, true);
      // Danh sách đầy đủ ra console: toast không đủ chỗ cho 4 dòng lý do.
      console.warn("Trang đăng ký webhook thất bại:", hong);
    } else {
      toast(`${xong} Trang đã đăng ký webhook — tin khách sẽ về từ giờ.`);
    }
    loadKetNoi();
  }));

  /* Đăng ký MỘT Trang vào webhook — bước quyết định có NHẬN được tin hay
   * không. Có token là gửi được ngay nên Trang trông như đã xong; nhận tin
   * thì cần đăng ký riêng, và không gì trên màn hình nói ra điều đó. */
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
   * KHÔNG hiện sẵn: màn hình Kết nối là chỗ người ta hay chụp lại để hỏi
   * nhau, và một chuỗi bí mật nằm sẵn ở đó sẽ đi theo mọi ảnh chụp. Bấm mới
   * hiện, ngay tại chỗ. Chỉ verify token được ra khỏi vault — access token
   * và app secret thì không (agent/api/channel_accounts.py).
   */
  $$("[data-verifytoken], [data-verifytoken-kenh]").forEach((button) => button.addEventListener("click", async () => {
    // Verify token dùng CHUNG cho mọi Trang của cùng một app — nên nút ở mức
    // kênh chỉ cần hỏi một tài khoản bất kỳ trong kênh đó.
    const id = button.dataset.verifytoken || button.dataset.verifytokenKenh;
    /* Ô của nút mức KÊNH tìm theo thẻ chứa nút: từng mang `data-tokenslot`
       TRÙNG id với ô Sức khoẻ của Trang đầu tiên, hai thứ ghi đè nhau. */
    const cho = button.dataset.verifytokenKenh
      ? button.closest(".channel-card")?.querySelector("[data-tokenslot-kenh]")
      : document.querySelector(`[data-tokenslot="${id}"]`);
    button.disabled = true;
    try {
      const r = await api(`/channel-accounts/${id}/verify-token`);
      const kenh = cho && cho.dataset.tokenslotKenh;
      if (kenh) {
        // Nhớ qua vòng làm mới — nhưng chỉ một phút: chuỗi bí mật không được
        // nằm sẵn trên màn hình mãi.
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

/* Hành động UỶ QUYỀN lên lưới: nút chính theo sức khoẻ, mở dòng thời gian,
 * lịch sử webhook, tuỳ chọn Trang, nối nhanh kênh chưa có tài khoản. Gắn MỘT
 * lần ở cấp tệp — lưới dựng lại innerHTML, gắn lên từng nút là gắn lại mãi. */
$("#connectiongrid")?.addEventListener("click", async (e) => {
  const lam = e.target.closest("[data-kn-lam]");
  if (lam) { await knLam(lam); return; }
  const dtg = e.target.closest("[data-kn-dtg]");
  if (dtg) { knMoDongThoiGian(dtg.dataset.knDtg); return; }
  const nhanh = e.target.closest("[data-kn-noi-nhanh]");
  if (nhanh) { $(`[data-noi="${nhanh.dataset.knNoiNhanh}"]`)?.click(); return; }
  const ls = e.target.closest("[data-kntt-lstk]");
  if (ls) {
    ls.disabled = true;
    try {
      const html = knttBangWebhook(await api(`/ket-noi/webhook?account_id=${encodeURIComponent(ls.dataset.knttLstk)}`));
      state.knLsWh = state.knLsWh || {};
      state.knLsWh[ls.dataset.knttLstk] = html;
      const o = ls.closest(".knh-nangcao")?.querySelector(".kntt-lstk");
      if (o) o.innerHTML = html;
    } catch (err) { toast(err.message, true); }
    finally { ls.disabled = false; }
  }
});

$("#connectiongrid")?.addEventListener("change", async (e) => {
  const s = e.target.closest("[data-kntt-fb]");
  if (!s) return;
  try {
    await api(`/ket-noi/kenh/${s.dataset.knttFb}/tuy-chon`, {
      method: "PUT", body: JSON.stringify({ an_binh_luan_co_sdt: s.value }),
    });
    toast("Đã lưu tuỳ chọn ẩn bình luận cho Trang này");
    const tk = (state.knttTk || {})[s.dataset.knttFb];
    if (tk && tk.an_binh_luan_co_sdt) tk.an_binh_luan_co_sdt.rieng = s.value === "chung" ? null : s.value;
  } catch (err) { toast(err.message, true); }
});
