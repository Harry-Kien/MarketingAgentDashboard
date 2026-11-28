/* ---------------- Kết nối & Tích hợp: lịch sử ----------------
 *
 * Khu vực "Lịch sử" của tab, hai bảng:
 *
 *   · Dòng thời gian MỘT tài khoản kênh (UX-08-09): trạng thái kết nối
 *     (account_health_events), sự kiện hệ thống (events) và đổi cấu hình
 *     (lich_su_ket_noi) trên một trục. Trước đây câu "Zalo này rớt lúc nào,
 *     ai bật lại" phải ghép tay từ ba chỗ, một trong số đó không có màn nào.
 *   · Lịch sử thay đổi cấu hình (UX-08-08), lọc theo dịch vụ và thời gian —
 *     trước nằm ở đáy một trang 2.500px, 30 dòng mới nhất, không lọc được.
 *
 * Lọc ở MÁY CHỦ (agent/ket_noi_tich_hop.py): lọc "GHN tháng trước" trên 30
 * dòng mới nhất ở trình duyệt là trả rỗng trong khi sổ có dữ liệu.
 */

const KN_LS_HD = { dat: "đặt", xoa: "bỏ (về .env)", doi_credential: "đổi thông tin đăng nhập", bat: "bật",
  tat: "tạm ngắt", doi_tuy_chon: "đổi tuỳ chọn", tao: "tạo", xoa_tai_khoan: "xoá tài khoản" };
const KN_LS_DICH_VU = { erpnext: "ERPNext", ghn: "Giao Hàng Nhanh", ghtk: "Giao Hàng Tiết Kiệm",
  ai: "Nhà cung cấp AI", thong_bao_ai: "Thông báo minh bạch AI", zalo_personal: "Zalo cá nhân",
  zalo_oa: "Zalo OA", facebook: "Facebook", instagram: "Instagram", whatsapp: "WhatsApp", webchat: "Web chat" };
const KN_DTG_LOAI = { suc_khoe: "Kết nối", su_kien: "Sự kiện", cau_hinh: "Cấu hình" };
const knLsTrang = { dich_vu: 0, kenh: 0, dich_vu_seq: 0, kenh_seq: 0, mobTab: "kenh" };
const KN_LS_TRUONG = { API_KEY: "Khoá API", API_SECRET: "Khoá bí mật API", TOKEN: "Token truy cập",
  SHOP_ID: "Mã cửa hàng", URL: "Địa chỉ dịch vụ", BASE_URL: "Địa chỉ dịch vụ", credentials: "Thông tin xác thực",
  tai_khoan: "Tài khoản", trang_thai: "Trạng thái", an_binh_luan_co_sdt: "Ẩn bình luận có số điện thoại",
  LLM_PROVIDER: "Nhà cung cấp AI", MODEL_CHAT: "Model trả lời khách", MODEL_HARD: "Model việc khó",
  MODEL_CHEAP: "Model kiểm sức khoẻ", MA_DOI_TAC: "Mã đối tác", KHO_ID: "Mã kho lấy hàng",
  THONG_BAO_AI: "Công tắc thông báo minh bạch AI", TIN_THONG_BAO_AI: "Nội dung thông báo minh bạch AI" };
function knLsNhanTruong(x, nhanServer = "") {
  const k = String(x || "").trim();
  if (nhanServer && nhanServer.toLowerCase() !== k.toLowerCase()) return nhanServer;
  const chuan = k.toUpperCase().replace(/^(ERPNEXT|NEXTERP|GHN|GHTK|ZALO_OA|META|OPENAI|GEMINI|ANTHROPIC)_/, "");
  return KN_LS_TRUONG[k] || KN_LS_TRUONG[chuan] || "Thiết lập kết nối";
}
function knLsPhanTrang(loai, con) {
  return `<nav class="ls-trang" aria-label="Phân trang ${loai === 'kenh' ? 'tài khoản kênh' : 'dịch vụ'}">
    <button class="btn btn--sm btn--ghost" data-kn-ls-page="${loai}" data-buoc="-1" ${knLsTrang[loai] ? '' : 'disabled'}>Trước</button>
    <span>Trang ${knLsTrang[loai] + 1}</span>
    <button class="btn btn--sm btn--ghost" data-kn-ls-page="${loai}" data-buoc="1" ${con ? '' : 'disabled'}>Sau</button></nav>`;
}

/* Mốc "từ" của bộ lọc "N ngày qua", theo giờ máy người xem. Trống = không lọc. */
function knLsTu(ngay) {
  const n = Number(ngay);
  return n > 0 ? new Date(Date.now() - n * 86400000).toISOString() : "";
}

function knttLichSu(ls) {
  if (!ls.length) return '<p class="empty">Không có thay đổi nào trong khoảng đã chọn.</p>';
  return ls.map((x) => `<div class="row"><span class="row__flag row__flag--auto"></span>
    <span class="row__body"><span class="row__title">${esc(x.sua_boi)} ${esc(KN_LS_HD[x.hanh_dong] || x.hanh_dong)} ${
      esc(knLsNhanTruong(x.truong, x.nhan_truong))}${x.bi_mat ? " (bí mật — không hiển thị giá trị)" : ""}</span>
      <span class="row__sub">${esc(KN_LS_DICH_VU[x.dich_vu] || x.dich_vu)}${x.doi_tuong ? " · " + esc(x.doi_tuong) : ""}</span></span>
    <span class="row__side"><span class="row__time">${esc(knttLuc(x.sua_luc))}</span></span></div>`).join("");
}

async function knLsTai() {
  const o = $("#kn-ls-o"), loc = $("#kn-ls-loc");
  if (!o || !loc) return;
  const seq = ++knLsTrang.dich_vu_seq;
  // Sổ cấu hình là của quản trị (luật số 2, agent/api/ket_noi_tich_hop.py):
  // nói thẳng thiếu quyền, đừng để một bảng trống trông như "chưa ai đổi gì".
  if (!coQuyen("cau_hinh.sua")) {
    o.innerHTML = '<div class="ls-cuon"><p class="empty">Cần quyền sửa cấu hình để xem lịch sử thay đổi cấu hình.</p></div>';
    return;
  }
  const q = new URLSearchParams({ gioi_han: "21", bo_qua: String(knLsTrang.dich_vu * 20), chi_dich_vu: "true" });
  if (loc.elements.dich_vu.value) q.set("dich_vu", loc.elements.dich_vu.value);
  const tu = knLsTu(loc.elements.ngay.value);
  if (tu) q.set("tu", tu);
  try {
    o.innerHTML = '<div class="ls-cuon"><p class="empty">Đang tải…</p></div>';
    const rows = await api(`/ket-noi/lich-su?${q}`);
    if (seq !== knLsTrang.dich_vu_seq) return;
    o.innerHTML = `<div class="ls-cuon">${knttLichSu(rows.slice(0, 20))}</div>` + knLsPhanTrang('dich_vu', rows.length > 20);
  } catch (e) {
    if (seq !== knLsTrang.dich_vu_seq) return;
    o.innerHTML = `<div class="ls-cuon"><p class="empty">Không tải được lịch sử: ${esc(e.message)}</p></div>`;
  }
}

function knDtgDong(x) {
  // Do not render arbitrary technical values (including historical credentials).
  const kt = [];
  return `<li class="knh-dtg__muc knh-dtg__muc--${esc(x.muc)}">
    <span class="knh-cham knh-cham--${esc(x.muc)}" aria-hidden="true"></span>
    <div class="knh-dtg__than">
      <div><span class="knh-dtg__loai">${esc(KN_DTG_LOAI[x.loai] || x.loai)}</span> <b>${esc(x.tieu_de)}</b>${
        x.mo_ta ? ` <span class="knh-dtg__mo-ta">${esc(x.mo_ta)}</span>` : ""}</div>
      <small><time datetime="${esc(x.luc)}">${esc(knttLuc(x.luc))}</time> · ${esc(x.boi || "Hệ thống")}</small>
      ${kt.length ? `<details class="knh-nangcao"><summary>Chi tiết kỹ thuật</summary>
        <dl class="knh-dl">${kt.map(([k, v]) => `<dt>${esc(k)}</dt><dd><code>${esc(v)}</code></dd>`).join("")}</dl></details>` : ""}
    </div></li>`;
}

async function knDtgTai() {
  const o = $("#kn-dtg-o"), loc = $("#kn-dtg-loc");
  if (!o || !loc) return;
  const seq = ++knLsTrang.kenh_seq;
  const id = loc.elements.account_id.value;
  if (!id) { o.innerHTML = '<div class="ls-cuon"><p class="empty">Chọn một tài khoản để xem dòng thời gian.</p></div>'; return; }
  const q = new URLSearchParams({ gioi_han: "21", bo_qua: String(knLsTrang.kenh * 20) });
  if (loc.elements.loai.value) q.set("loai", loc.elements.loai.value);
  const tu = knLsTu(loc.elements.ngay.value);
  if (tu) q.set("tu", tu);
  o.innerHTML = '<div class="ls-cuon"><p class="empty">Đang tải…</p></div>';
  try {
    const d = await api(`/ket-noi/kenh/${encodeURIComponent(id)}/dong-thoi-gian?${q}`);
    if (seq !== knLsTrang.kenh_seq) return;
    const noiDung = d.su_kien.length
      ? `<p class="hint ls-cuon__ten">${esc(d.display_name)}</p><ol class="knh-dtg">${d.su_kien.slice(0, 20).map(knDtgDong).join("")}</ol>`
      : '<p class="empty">Không có sự kiện nào trong khoảng đã chọn — thử mở rộng thời gian.</p>';
    o.innerHTML = `<div class="ls-cuon">${noiDung}</div>` + knLsPhanTrang('kenh', d.su_kien.length > 20);
  } catch (e) {
    if (seq !== knLsTrang.kenh_seq) return;
    o.innerHTML = `<div class="ls-cuon"><p class="empty">Không tải được dòng thời gian: ${esc(e.message)}</p></div>`;
  }
}

/* Danh sách tài khoản cho ô chọn — lấy theo phạm vi kênh của người xem. */
async function knDtgDanhSach() {
  const chon = $("#kn-dtg-tk");
  if (!chon || !coQuyen("kenh.doc")) return;
  try {
    const ds = await api("/channel-accounts");
    const cu = chon.value;
    chon.innerHTML = '<option value="">— Chọn tài khoản —</option>' + ds.map((a) =>
      `<option value="${esc(a.id)}">${esc(a.display_name)} · ${esc(CHANNEL_LABEL[a.channel] || a.channel)}</option>`).join("");
    if (cu && ds.some((a) => a.id === cu)) chon.value = cu;
  } catch (e) {
    chon.innerHTML = '<option value="">Không tải được tài khoản</option>';
    toast(e.message, true);
  }
}

/* Mở khu vực Lịch sử: nạp lại cả hai bảng. Chỉ khi đã đăng nhập — hàm có thể
 * được gọi lúc khôi phục khu vực đã nhớ, trước khi phiên kịp kiểm. */
async function knLsMo() {
  if (!state.toiQuyen || !$("#kn-ls-o")?._knGan) return;
  await knDtgDanhSach();
  await Promise.all([knLsTai(), knDtgTai()]);
}

function knChonLsTab(tab) {
  const goc = $("#kn-phan-lich-su");
  knLsTrang.mobTab = tab === "dich_vu" ? "dich_vu" : "kenh";
  if (!goc) return;
  goc.dataset.lsTab = knLsTrang.mobTab;
  $$("[data-kn-ls-tab]", goc).forEach((b) => {
    const on = b.dataset.knLsTab === knLsTrang.mobTab;
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
}

/* Nút "Dòng thời gian" trên dòng tài khoản: sang khu vực Lịch sử, chọn sẵn. */
async function knMoDongThoiGian(id) {
  knLsTrang.kenh = 0;
  knChonLsTab("kenh");
  knChonPhan("lich-su");
  await knDtgDanhSach();
  const chon = $("#kn-dtg-tk");
  if (chon) chon.value = id;
  await knDtgTai();
  $("#kn-dtg-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/* Gắn MỘT lần, khi mô-đun tab được gắn (22-ket-noi-tich-hop.js). */
function knLsKhoiTao() {
  const o = $("#kn-ls-o");
  if (!o || o._knGan) return;
  o._knGan = true;
  knChonLsTab(knLsTrang.mobTab);
  const dv = $("#kn-ls-dv");
  if (dv) dv.innerHTML = '<option value="">Tất cả dịch vụ</option>' + Object.entries(KN_LS_DICH_VU)
    .map(([ma, ten]) => `<option value="${esc(ma)}">${esc(ten)}</option>`).join("");
  $("#kn-ls-loc")?.addEventListener("change", () => { knLsTrang.dich_vu = 0; knLsTai(); });
  $("#kn-dtg-loc")?.addEventListener("change", () => { knLsTrang.kenh = 0; knDtgTai(); });
  $("#kn-phan-lich-su")?.addEventListener("click", e => {
    const tabBtn = e.target.closest("[data-kn-ls-tab]");
    if (tabBtn) {
      knChonLsTab(tabBtn.dataset.knLsTab);
      return;
    }
    const b = e.target.closest('[data-kn-ls-page]');
    if (!b || b.disabled) return;
    const loai = b.dataset.knLsPage;
    knLsTrang[loai] = Math.max(0, knLsTrang[loai] + Number(b.dataset.buoc));
    if (loai === 'kenh') knDtgTai(); else knLsTai();
  });
  // Ô chọn là bộ lọc, không có nút gửi: chặn Enter khỏi tải lại trang.
  $$("#kn-ls-loc, #kn-dtg-loc").forEach((f) => f.addEventListener("submit", (e) => e.preventDefault()));
  if (state.knPhan === "lich-su") knLsMo();
}
