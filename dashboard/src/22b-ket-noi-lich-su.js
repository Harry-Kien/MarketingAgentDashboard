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

/* Mốc "từ" của bộ lọc "N ngày qua", theo giờ máy người xem. Trống = không lọc. */
function knLsTu(ngay) {
  const n = Number(ngay);
  return n > 0 ? new Date(Date.now() - n * 86400000).toISOString() : "";
}

function knttLichSu(ls) {
  if (!ls.length) return '<p class="empty">Không có thay đổi nào trong khoảng đã chọn.</p>';
  return ls.map((x) => `<div class="row"><span class="row__flag row__flag--auto"></span>
    <span class="row__body"><span class="row__title">${esc(x.sua_boi)} ${esc(KN_LS_HD[x.hanh_dong] || x.hanh_dong)} ${
      esc(x.nhan_truong || x.truong)}${x.bi_mat ? " (bí mật)" : ""}</span>
      <span class="row__sub">${esc(KN_LS_DICH_VU[x.dich_vu] || x.dich_vu)}${x.doi_tuong ? " · " + esc(x.doi_tuong) : ""}</span></span>
    <span class="row__side"><span class="row__time">${esc(knttLuc(x.sua_luc))}</span></span></div>`).join("");
}

async function knLsTai() {
  const o = $("#kn-ls-o"), loc = $("#kn-ls-loc");
  if (!o || !loc) return;
  // Sổ cấu hình là của quản trị (luật số 2, agent/api/ket_noi_tich_hop.py):
  // nói thẳng thiếu quyền, đừng để một bảng trống trông như "chưa ai đổi gì".
  if (!coQuyen("cau_hinh.sua")) {
    o.innerHTML = '<p class="empty">Cần quyền sửa cấu hình để xem lịch sử thay đổi cấu hình.</p>';
    return;
  }
  const q = new URLSearchParams({ gioi_han: "100" });
  if (loc.elements.dich_vu.value) q.set("dich_vu", loc.elements.dich_vu.value);
  const tu = knLsTu(loc.elements.ngay.value);
  if (tu) q.set("tu", tu);
  try {
    o.innerHTML = knttLichSu(await api(`/ket-noi/lich-su?${q}`));
  } catch (e) {
    o.innerHTML = `<p class="empty">Không tải được lịch sử: ${esc(e.message)}</p>`;
  }
}

function knDtgDong(x) {
  const kt = Object.entries(x.ky_thuat || {}).filter(([, v]) => v != null && v !== "");
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
  const id = loc.elements.account_id.value;
  if (!id) { o.innerHTML = '<p class="empty">Chọn một tài khoản để xem dòng thời gian.</p>'; return; }
  const q = new URLSearchParams({ gioi_han: "150" });
  if (loc.elements.loai.value) q.set("loai", loc.elements.loai.value);
  const tu = knLsTu(loc.elements.ngay.value);
  if (tu) q.set("tu", tu);
  o.innerHTML = '<p class="empty">Đang tải…</p>';
  try {
    const d = await api(`/ket-noi/kenh/${encodeURIComponent(id)}/dong-thoi-gian?${q}`);
    o.innerHTML = d.su_kien.length
      ? `<ol class="knh-dtg">${d.su_kien.map(knDtgDong).join("")}</ol>`
      : '<p class="empty">Không có sự kiện nào trong khoảng đã chọn — thử mở rộng thời gian.</p>';
  } catch (e) {
    o.innerHTML = `<p class="empty">Không tải được dòng thời gian: ${esc(e.message)}</p>`;
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

/* Nút "Dòng thời gian" trên dòng tài khoản: sang khu vực Lịch sử, chọn sẵn. */
async function knMoDongThoiGian(id) {
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
  const dv = $("#kn-ls-dv");
  if (dv) dv.innerHTML = '<option value="">Tất cả dịch vụ</option>' + Object.entries(KN_LS_DICH_VU)
    .map(([ma, ten]) => `<option value="${esc(ma)}">${esc(ten)}</option>`).join("");
  $("#kn-ls-loc")?.addEventListener("change", knLsTai);
  $("#kn-dtg-loc")?.addEventListener("change", knDtgTai);
  // Ô chọn là bộ lọc, không có nút gửi: chặn Enter khỏi tải lại trang.
  $$("#kn-ls-loc, #kn-dtg-loc").forEach((f) => f.addEventListener("submit", (e) => e.preventDefault()));
  if (state.knPhan === "lich-su") knLsMo();
}
