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
