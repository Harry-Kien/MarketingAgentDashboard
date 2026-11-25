/* ---------------- kết nối kênh ----------------
 *
 * Tách khỏi 10-vong-lam-moi.js (quá 1000 dòng). Dùng hàm của tệp ấy —
 * quetQR, veFormKenh, lyDoKetNoi, goc_cong_khai — nên đứng SAU nó khi đóng gói.
 */

/* =====================================================================
 * KẾT NỐI KÊNH: tình trạng (hàng đợi cần xử lý) → điều kiện chung → nối
 * kênh mới → danh sách tài khoản (18a-ket-noi-tai-khoan.js).
 *
 * Luật trạng thái nằm ở MÁY CHỦ (agent/omnichannel/suc_khoe_kenh.py),
 * không ở đây: giao diện chỉ vẽ. Hai nơi cùng giữ luật là hai nơi lệch nhau.
 * ===================================================================== */
const KN_NUT = {
  dang_nhap_meta: "Đăng nhập Facebook",
  quet_qr: "Quét QR",
  xac_minh: "Xác minh lại",
  nhan_tin: "Bật nhận tin",
  nhan_thu: "Kiểm lại",
  bat_lai: "Bật lại",
};

/* Chỉ gán innerHTML khi nội dung ĐỔI: vòng làm mới 6 giây dựng lại mà
 * không đổi gì là đóng `<details>` người dùng vừa mở và cướp tiêu điểm. */
function knVe(o, html) {
  if (!o || o._knHtml === html) return;
  o._knHtml = html;
  o.innerHTML = html;
}

/* Những tài khoản CẦN NGƯỜI làm gì đó. Tạm ngắt là người ta chủ động — không
 * cần xử lý; hoạt động mà có cảnh báo (token sắp hết, chưa thấy tin nào về)
 * thì có. */
function knCanXuLy(k) {
  return ["loi", "can_xac_thuc", "chua_ket_noi"].includes(k.trang_thai) || Boolean(k.canh_bao);
}

async function loadSucKhoeKenh() {
  let d;
  try {
    d = await api("/channel-accounts/suc-khoe-tong");
  } catch (e) {
    knVe($("#kn-suckhoe"), `<p class="empty">Không tải được tình trạng kết nối: ${esc(e.message)}</p>`);
    return;
  }
  state.knDangNhap = d.dang_nhap || {};
  state.knNhanTT = d.nhan_trang_thai || {};
  state.knSucKhoe = Object.fromEntries(d.kenh.map((k) => [k.id, k]));

  /* Điều kiện chung thu gọn khi đã đủ: ba dòng xanh mỗi lần mở màn là ba
     dòng người ta học cách bỏ qua — và rồi bỏ qua luôn lúc nó đỏ. */
  const dat = d.dieu_kien.filter((k) => k.muc === "xanh").length;
  knVe($("#kn-dieukien"), `<details data-kn-mo="dieukien"${knMo("dieukien", dat < d.dieu_kien.length)}>
    <summary class="panel__head">Điều kiện chung <span class="panel__note">${dat}/${d.dieu_kien.length} đạt</span></summary>
    ${d.dieu_kien.map((k) => `<div class="kn-dk"><span class="kn-cham kn-cham--${esc(k.muc)}" aria-hidden="true"></span>
      <b>${esc(k.ten)}</b><span>${esc(k.viec)}</span></div>`).join("")}</details>`);

  /* Nút đăng nhập mà ứng dụng chưa khai thì bấm vào chỉ ra một lỗi 503 —
     khoá sẵn và nói lý do ngay trên thẻ. */
  const meta = $('[data-noi="meta"]'), zoa = $('[data-noi="zalo_oa"]');
  if (meta) { meta.disabled = !state.knDangNhap.meta; meta.title = meta.disabled ? "Chưa khai ứng dụng Meta trong .env" : ""; }
  if (zoa) { zoa.disabled = !state.knDangNhap.zalo_oa; zoa.title = zoa.disabled ? "Chưa khai ứng dụng Zalo OA trong .env" : ""; }

  const dem = d.dem_trang_thai || {};
  const canXuLy = d.kenh.filter(knCanXuLy);
  $("#kn-dem").textContent = Object.entries(dem).filter(([, n]) => n)
    .map(([tt, n]) => `${n} ${String(state.knNhanTT[tt] || tt).toLowerCase()}`).join(" · ");
  const nav = $("#kn-nav-dem");
  if (nav) { nav.textContent = canXuLy.length ? String(canXuLy.length) : ""; nav.hidden = !canXuLy.length; }

  /* "Cần xử lý" chỉ là HÀNG ĐỢI việc — tên, việc cần làm, một nút — không
     phải bản sao thứ hai của danh sách tài khoản (UX-08-02). Chi tiết ở
     đúng dòng tài khoản bên dưới; nút "Xem" đưa tới đó. */
  knVe($("#kn-suckhoe"), !d.kenh.length
    ? '<p class="empty">Chưa nối kênh nào — bắt đầu ở mục Nối kênh mới bên dưới.</p>'
    : !canXuLy.length
      ? '<p class="knh-tot">✓ Mọi tài khoản đang hoạt động bình thường.</p>'
      : canXuLy.map((k) => `<div class="kn-dong knh-can">
      <span class="knh-tt knh-tt--${esc(k.canh_bao ? "canh-bao" : k.trang_thai)}">${esc(k.canh_bao ? "Cần để ý" : k.nhan_trang_thai)}</span>
      <span><b>${esc(k.display_name)}</b><small>${esc(CHANNEL_LABEL[k.channel] || k.channel)}</small></span>
      <span>${esc(knViecDeDoc(k) || (k.giai_thich && k.giai_thich.tieu_de) || k.viec)}<small>${k.tin_vao_gan_nhat
        ? "Tin khách gần nhất: " + esc(clock(k.tin_vao_gan_nhat)) : "Chưa có tin khách nào"}${
        k.token_con_ngay != null ? ` · quyền Meta còn ${Math.max(0, Math.floor(k.token_con_ngay))} ngày` : ""}</small></span>
      <span class="knh-can__nut">${k.hanh_dong && KN_NUT[k.hanh_dong]
        ? `<button type="button" class="btn btn--sm${k.muc === "do" ? " btn--primary" : ""}"
             data-kn-lam="${esc(k.hanh_dong)}" data-kn-id="${esc(k.id)}">${esc(KN_NUT[k.hanh_dong])}</button>` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-kn-den="${esc(k.id)}">Xem</button></span>
    </div>`).join(""));
}

/* Đưa mắt tới đúng dòng tài khoản và mở phần Quản lý của nó. */
function knDenTaiKhoan(id) {
  knChonPhan("kenh");
  const dong = document.getElementById("kn-tk-" + id);
  if (!dong) return;
  dong.closest(".channel-card__body")?.classList.remove("is-thu-gon");
  const ql = dong.querySelector(".knh-quanly");
  if (ql) ql.open = true;
  dong.scrollIntoView({ behavior: "smooth", block: "center" });
}

$("#kn-suckhoe")?.addEventListener("click", async (e) => {
  const den = e.target.closest("[data-kn-den]");
  if (den) { knDenTaiKhoan(den.dataset.knDen); return; }
  const b = e.target.closest("[data-kn-lam]");
  if (b) await knLam(b);
});

/* Nút chính theo sức khoẻ — dùng chung cho hàng đợi "Cần xử lý" và dòng tài
 * khoản (18a-ket-noi-tai-khoan.js), để hai chỗ không bao giờ làm hai việc khác
 * nhau cho cùng một nhãn nút. */
async function knLam(b) {
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
}

/* ---------------- ba khu vực của tab ----------------
 *
 * Tab từng là MỘT trang dọc hơn 2.500px: điều kiện chung, nối kênh, sức khoẻ,
 * lưới tài khoản, checklist, rồi ERPNext/GHN/GHTK, rồi plugin kênh, rồi lịch
 * sử ở tận đáy (UX-08-01). Kênh nói chuyện với KHÁCH và hệ thống ngoài của
 * CỬA HÀNG là hai việc của hai lúc khác nhau (MD-UX-20-01) — tách thành khu
 * vực riêng, mỗi lúc chỉ hiện một.
 *
 * Phần tử thuộc khu vực nào khai bằng `data-kn-thuoc`; khối mô-đun gắn vào
 * (22-ket-noi-tich-hop.js) cũng tự khai, nên một hàm ẩn/hiện được hết. */
const KN_PHAN = ["kenh", "tich-hop", "lich-su"];

function knChonPhan(phan) {
  const tab = $("#cc-ket-noi");
  if (!tab || !KN_PHAN.includes(phan)) return;
  state.knPhan = phan;
  $$("[data-kn-phan-nut]", tab).forEach((b) => {
    const on = b.dataset.knPhanNut === phan;
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  $$("[data-kn-thuoc]", tab).forEach((o) => { o.hidden = o.dataset.knThuoc !== phan; });
  // Nhớ khu vực theo từng người xem — tiện, không phải dữ liệu.
  try { localStorage.setItem("kn.phan", phan); } catch { /* chế độ riêng tư: bỏ qua */ }
  if (phan === "lich-su" && typeof knLsMo === "function") knLsMo();
}

$(".kn-phan-nav")?.addEventListener("click", (e) => {
  const b = e.target.closest("[data-kn-phan-nut]");
  if (b) knChonPhan(b.dataset.knPhanNut);
});
// Phím mũi tên giữa các khu vực, như thanh tab chuẩn (role="tablist").
$(".kn-phan-nav")?.addEventListener("keydown", (e) => {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const i = KN_PHAN.indexOf(state.knPhan || "kenh");
  const moi = KN_PHAN[(i + (e.key === "ArrowRight" ? 1 : KN_PHAN.length - 1)) % KN_PHAN.length];
  knChonPhan(moi);
  $(`[data-kn-phan-nut="${moi}"]`)?.focus();
});
{
  let nho = "kenh";
  try { nho = localStorage.getItem("kn.phan") || "kenh"; } catch { /* không có bộ nhớ: mặc định */ }
  knChonPhan(KN_PHAN.includes(nho) ? nho : "kenh");
}

/* "Thêm tài khoản" mở mục Nối kênh mới — đường một-nút — chứ không mở thẳng
 * form dán token: form ấy là đường phụ, chỉ khi không đăng nhập được. */
$("#connection-add-toggle")?.addEventListener("click", () => {
  knChonPhan("kenh");
  const moi = $("#kn-moi");
  if (moi) { moi.open = true; moi.scrollIntoView({ behavior: "smooth", block: "start" }); }
});
$("#kn-nhap-tay-mo")?.addEventListener("click", () => {
  const f = $("#connection-create");
  f.classList.toggle("is-hidden");
  if (!f.classList.contains("is-hidden")) f.scrollIntoView({ behavior: "smooth", block: "start" });
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
