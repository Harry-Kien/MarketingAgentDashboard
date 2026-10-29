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
  if (dk.nhan_co) neu.push("có nhãn " + dk.nhan_co);
  if (dk.nhan_khong) neu.push("chưa có nhãn " + dk.nhan_khong);
  const thi = (q.hanh_dong || []).map((h) => ({
    gan_nhan: "gắn nhãn " + h.nhan,
    gui_mau: "gửi mẫu /" + h.ma_tat,
    tao_viec: "tạo việc «" + h.tieu_de + "»",
    chuyen_nguoi: "chuyển người",
  }[h.loai] || h.loai));
  return `Nếu ${neu.length ? neu.join(" và ") : "có tin bất kỳ"} → ${thi.join(", ")}`;
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
    return `
    <div class="row">
      <span class="row__flag ${!q.bat ? "row__flag--plain" : b.hong ? "row__flag--halt" : "row__flag--auto"}"></span>
      <span class="row__body"><span class="row__title">${esc(q.thu_tu)} · ${esc(q.ten)}${q.bat ? "" : " <em>(đang tắt)</em>"}</span>
        <span class="row__sub">${esc(_moTaQuyTac(q))}</span>
        <span class="row__sub">${tinh}${esc(lan)}</span></span>
      ${sua ? `<span class="row__side">
        <button type="button" class="btn btn--sm" data-qt-bat="${esc(q.id)}">${q.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm" data-qt-sua="${esc(q.id)}">Sửa</button>
        <button type="button" class="btn btn--sm btn--halt" data-qt-xoa="${esc(q.id)}">Xoá</button>
      </span>` : ""}
    </div>`;
  }).join("") : '<p class="empty">Chưa có quy tắc nào — agent và định tuyến chạy như thường.</p>';
  await loadQuyTacLanChay();
}

async function loadQuyTacLanChay() {
  const o = $("#qtLanChay");
  if (!o) return;
  let r;
  try { r = await api("/tu-dong/lan-chay?gioi_han=20"); } catch (e) { toast(e.message, true); return; }
  o.innerHTML = r.lan_chay.length ? r.lan_chay.map((l) => {
    const ct = l.chi_tiet || {};
    const viec = l.ket_qua === "hong" ? ("hỏng: " + (ct.loi || "?"))
      : l.ket_qua === "bo_qua" ? "khớp, không còn gì để làm (đã làm ở tin trước)"
      : (ct.lam || []).join(", ");
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
  if (f.nhan_co.value.trim()) dk.nhan_co = f.nhan_co.value.trim();
  if (f.nhan_khong.value.trim()) dk.nhan_khong = f.nhan_khong.value.trim();
  const hd = [];
  if (f.hd_gan_nhan.value.trim()) hd.push({ loai: "gan_nhan", nhan: f.hd_gan_nhan.value.trim() });
  if (f.hd_gui_mau.value.trim()) hd.push({ loai: "gui_mau", ma_tat: f.hd_gui_mau.value.trim().replace(/^\//, "") });
  if (f.hd_tao_viec.value.trim()) hd.push({ loai: "tao_viec", tieu_de: f.hd_tao_viec.value.trim() });
  if (f.hd_chuyen_nguoi.value.trim()) hd.push({ loai: "chuyen_nguoi", ly_do: f.hd_chuyen_nguoi.value.trim() });
  return {
    ten: f.ten.value.trim(), su_kien: "tin_khach", dieu_kien: dk, hanh_dong: hd,
    bat: f.bat.checked, thu_tu: Number(f.thu_tu.value || 100),
  };
}

function _datQuyTac(f, q) {
  const dk = q.dieu_kien || {};
  f.qt_id.value = q.id; f.ten.value = q.ten; f.thu_tu.value = q.thu_tu; f.bat.checked = q.bat;
  $$("[data-qt-kenh]").forEach((c) => { c.checked = (dk.kenh || []).includes(c.value); });
  f.chua_tu.value = (dk.chua_tu || []).join(", ");
  f.ngoai_gio.value = dk.ngoai_gio == null ? "" : String(dk.ngoai_gio);
  f.lan_dau.value = dk.lan_dau == null ? "" : String(dk.lan_dau);
  f.nhan_co.value = dk.nhan_co || ""; f.nhan_khong.value = dk.nhan_khong || "";
  const lay = (loai, k) => ((q.hanh_dong || []).find((h) => h.loai === loai) || {})[k] || "";
  f.hd_gan_nhan.value = lay("gan_nhan", "nhan");
  f.hd_gui_mau.value = lay("gui_mau", "ma_tat");
  f.hd_tao_viec.value = lay("tao_viec", "tieu_de");
  f.hd_chuyen_nguoi.value = lay("chuyen_nguoi", "ly_do");
}

function _xoaFormQuyTac() {
  const f = $("#qtForm");
  if (!f) return;
  f.reset(); f.qt_id.value = "";
  $$("[data-qt-kenh]").forEach((c) => { c.checked = false; });
}

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
        bat: !q.bat, thu_tu: q.thu_tu }) });
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
