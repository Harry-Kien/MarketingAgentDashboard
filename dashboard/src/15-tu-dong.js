/* ---------------- Quy tắc tự động ---------------- */
/* Khi khách nhắn → nếu thoả điều kiện → làm hành động. Máy chủ kiểm lại
 * MỌI thứ (danh sách đóng, mẫu tồn tại, mẫu sạch cụm cấm); ở đây chỉ dựng
 * biểu mẫu cho dễ điền. Biểu mẫu là phần HTML tĩnh, không dựng lại theo vòng
 * làm mới — chữ đang gõ không mất.
 *
 * Biểu mẫu KHI – NẾU – THÌ (UX-07-01): mỗi điều kiện / hành động là một
 * KHỐI ẩn sẵn trong HTML, hiện ra khi bấm "+ Thêm điều kiện" / "+ Thêm hành
 * động". Bản trước bày cả mười ba ô cùng lúc — người tạo quy tắc "chào ngoài
 * giờ" phải đọc qua bốn ô nhãn và ô tạo việc không liên quan. Khối thay cho
 * ô, KHÔNG thay định dạng JSON lưu xuống: `quyTacTuGiaTri` / `giaTriTuQuyTac`
 * là hai hàm thuần, test chạy khứ hồi bằng node. */

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

/* Khối của biểu mẫu. `o` = `data-qt-o` của khối = `name` của ô chính. */
const QT_DK = [
  { o: "kenh", ten: "Kênh nhận tin" },
  { o: "chua_tu", ten: "Tin có chứa từ" },
  { o: "ngoai_gio", ten: "Giờ làm việc" },
  { o: "lan_dau", ten: "Tin đầu tiên" },
  { o: "nhan_hoi_thoai_co", ten: "Hội thoại CÓ nhãn" },
  { o: "nhan_hoi_thoai_khong", ten: "Hội thoại CHƯA có nhãn" },
  { o: "nhan_khach_co", ten: "Khách CÓ nhãn" },
  { o: "nhan_khach_khong", ten: "Khách CHƯA có nhãn" },
];
const QT_HD = [
  { o: "hd_gui_mau", loai: "gui_mau", ten: "Gửi mẫu trả lời nhanh" },
  { o: "hd_gan_nhan_hoi_thoai", loai: "gan_nhan_hoi_thoai", ten: "Gắn nhãn hội thoại" },
  { o: "hd_gan_nhan_khach", loai: "gan_nhan_khach", ten: "Gắn nhãn khách hàng" },
  { o: "hd_tao_viec", loai: "tao_viec", ten: "Tạo công việc" },
  { o: "hd_chuyen_nguoi", loai: "chuyen_nguoi", ten: "Chuyển cho nhân viên" },
];
const QT_NHAN_O = ["nhan_hoi_thoai_co", "nhan_hoi_thoai_khong", "nhan_khach_co", "nhan_khach_khong"];

const _tuKhoa = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);
const _maTat = (s) => String(s || "").trim().replace(/^\//, "");

/* Giá trị biểu mẫu (đối tượng phẳng) + tập khối đang hiện -> thân gửi máy chủ.
 *
 * Khối ẨN không bao giờ vào quy tắc, kể cả khi ô bên trong còn giá trị:
 * `form.reset()` đưa <select> về lựa chọn đầu, và một ô ẩn mang "chỉ ngoài
 * giờ" là điều kiện người dùng không nhìn thấy mà quy tắc vẫn xét. Thứ tự
 * hành động giữ đúng như bản cũ (nhãn → mẫu → việc → chuyển người). */
function quyTacTuGiaTri(v, hien) {
  const co = (o) => hien.has(o);
  const dk = {};
  if (co("kenh") && (v.kenh || []).length) dk.kenh = [...v.kenh];
  const tu = _tuKhoa(v.chua_tu);
  if (co("chua_tu") && tu.length) dk.chua_tu = tu;
  if (co("ngoai_gio") && v.ngoai_gio) dk.ngoai_gio = v.ngoai_gio === "true";
  if (co("lan_dau") && v.lan_dau) dk.lan_dau = v.lan_dau === "true";
  for (const k of QT_NHAN_O) if (co(k) && v[k]) dk[k] = [v[k]];
  const hd = [];
  if (co("hd_gan_nhan_hoi_thoai") && v.hd_gan_nhan_hoi_thoai) hd.push({ loai: "gan_nhan_hoi_thoai", nhan_id: v.hd_gan_nhan_hoi_thoai });
  if (co("hd_gan_nhan_khach") && v.hd_gan_nhan_khach) hd.push({ loai: "gan_nhan_khach", nhan_id: v.hd_gan_nhan_khach });
  if (co("hd_gui_mau") && _maTat(v.hd_gui_mau)) hd.push({ loai: "gui_mau", ma_tat: _maTat(v.hd_gui_mau) });
  if (co("hd_tao_viec") && String(v.hd_tao_viec || "").trim()) {
    hd.push({ loai: "tao_viec", tieu_de: String(v.hd_tao_viec).trim(),
              ...(v.hd_tao_viec_tu_giao ? { giao_tu_dong: true } : {}) });
  }
  if (co("hd_chuyen_nguoi") && String(v.hd_chuyen_nguoi || "").trim()) {
    hd.push({ loai: "chuyen_nguoi", ly_do: String(v.hd_chuyen_nguoi).trim() });
  }
  return {
    ten: String(v.ten || "").trim(), su_kien: "tin_khach", dieu_kien: dk, hanh_dong: hd,
    bat: !!v.bat, thu_tu: Number(v.thu_tu === "" || v.thu_tu == null ? 100 : v.thu_tu),
    dung_xet_sau: !!v.dung_xet_sau, cho_ai_tra_loi: !!v.cho_ai_tra_loi,
  };
}

/* Quy tắc đã lưu -> { v, hien }. Khối hiện khi quy tắc CÓ thứ đó — kể cả
 * hành động thiếu chữ (chuyển người không lý do): hiện ra để người sửa thấy
 * và điền, thay vì bản cũ lặng lẽ đánh rơi nó ở lần lưu sau. */
function giaTriTuQuyTac(q) {
  const dk = q.dieu_kien || {};
  const lay = (loai) => (q.hanh_dong || []).find((h) => h.loai === loai);
  const v = {
    ten: q.ten || "", thu_tu: String(q.thu_tu ?? 100), bat: q.bat !== false,
    dung_xet_sau: !!q.dung_xet_sau, cho_ai_tra_loi: !!q.cho_ai_tra_loi,
    kenh: [...(dk.kenh || [])], chua_tu: (dk.chua_tu || []).join(", "),
    ngoai_gio: dk.ngoai_gio == null ? "" : String(dk.ngoai_gio),
    lan_dau: dk.lan_dau == null ? "" : String(dk.lan_dau),
    hd_gan_nhan_hoi_thoai: (lay("gan_nhan_hoi_thoai") || {}).nhan_id || "",
    hd_gan_nhan_khach: (lay("gan_nhan_khach") || {}).nhan_id || "",
    hd_gui_mau: (lay("gui_mau") || {}).ma_tat || "",
    hd_tao_viec: (lay("tao_viec") || {}).tieu_de || "",
    hd_tao_viec_tu_giao: !!(lay("tao_viec") || {}).giao_tu_dong,
    hd_chuyen_nguoi: (lay("chuyen_nguoi") || {}).ly_do || "",
  };
  for (const k of QT_NHAN_O) v[k] = (dk[k] || [])[0] || "";
  const hien = new Set();
  if (v.kenh.length) hien.add("kenh");
  if (v.chua_tu) hien.add("chua_tu");
  for (const k of ["ngoai_gio", "lan_dau", ...QT_NHAN_O]) if (v[k]) hien.add(k);
  for (const h of QT_HD) if (lay(h.loai)) hien.add(h.o);
  return { v, hien };
}

/* Khối đang hiện mà không góp gì vào quy tắc — tên để báo người dùng. Bỏ
 * qua im lặng là đúng kiểu hỏng im lặng: thêm "Tin có chứa từ" rồi để
 * trống, quy tắc lưu ra áp cho MỌI tin mà người tạo tưởng đã lọc. */
function khoiTrong(v, hien) {
  const gop = {
    kenh: (v.kenh || []).length, chua_tu: _tuKhoa(v.chua_tu).length,
    hd_gui_mau: _maTat(v.hd_gui_mau),
    hd_tao_viec: String(v.hd_tao_viec || "").trim(),
    hd_chuyen_nguoi: String(v.hd_chuyen_nguoi || "").trim(),
  };
  return [...QT_DK, ...QT_HD]
    .filter((k) => hien.has(k.o) && !(k.o in gop ? gop[k.o] : v[k.o]))
    .map((k) => k.ten);
}

/* Câu mô tả, tách hai vế NẾU / THÌ để danh sách hiện thành hai dòng. */
function _moTaQuyTacPhan(q) {
  const dk = q.dieu_kien || {};
  const neu = [];
  if (dk.kenh) neu.push("kênh " + dk.kenh.map((k) => TEN_KENH[k] || k).join("/"));
  if (dk.chua_tu) neu.push("có từ «" + dk.chua_tu.join("», «") + "»");
  if (dk.ngoai_gio === true) neu.push("ngoài giờ");
  if (dk.ngoai_gio === false) neu.push("trong giờ");
  if (dk.lan_dau === true) neu.push("tin đầu tiên");
  if (dk.lan_dau === false) neu.push("không phải tin đầu");
  // Nhãn theo id (0056) — đọc tên qua `tenNhanTheoId` (21-nhan.js). Khoá
  // chữ cũ còn sót thì vẫn hiện chữ.
  const ten = (ds) => (ds || []).map(tenNhanTheoId).join(" / ");
  if (dk.nhan_hoi_thoai_co) neu.push("hội thoại có nhãn " + ten(dk.nhan_hoi_thoai_co));
  if (dk.nhan_hoi_thoai_khong) neu.push("hội thoại chưa có nhãn " + ten(dk.nhan_hoi_thoai_khong));
  if (dk.nhan_khach_co) neu.push("khách có nhãn " + ten(dk.nhan_khach_co));
  if (dk.nhan_khach_khong) neu.push("khách chưa có nhãn " + ten(dk.nhan_khach_khong));
  if (dk.nhan_co) neu.push("có nhãn " + dk.nhan_co);
  if (dk.nhan_khong) neu.push("chưa có nhãn " + dk.nhan_khong);
  const thi = (q.hanh_dong || []).map((h) => ({
    gan_nhan: "gắn nhãn " + h.nhan,
    gan_nhan_hoi_thoai: "gắn nhãn hội thoại " + tenNhanTheoId(h.nhan_id),
    gan_nhan_khach: "gắn nhãn khách " + tenNhanTheoId(h.nhan_id),
    gui_mau: "gửi mẫu /" + h.ma_tat,
    tao_viec: "tạo việc «" + h.tieu_de + "»" + (h.giao_tu_dong ? " (tự phân công)" : ""),
    chuyen_nguoi: "chuyển cho nhân viên",
  }[h.loai] || h.loai));
  return { neu: neu.length ? neu.join(" và ") : "mọi tin khách", thi: thi.join(", ") };
}

// Tóm tắt MỘT lần chạy: làm gì, bỏ qua gì và vì sao, hỏng gì. "Bỏ qua" phải
// nói lý do — "không gửi mẫu vì quy tắc X đã gửi" là câu trả lời cho câu hỏi
// người vận hành sẽ hỏi đầu tiên: "sao quy tắc của tôi không gửi?".
function _tomTatLanChay(ketQua, ct) {
  ct = ct || {};
  const lam = (ct.lam || []).join(", ");
  const boQua = (ct.bo_qua || []).join("; ");
  if (ketQua === "hong") return "hỏng: " + (ct.loi || "?");
  if (ketQua === "bo_qua") return "khớp nhưng bỏ qua — " + (boQua || "đã làm ở tin trước");
  let s = lam;
  if (ct.ai_nhuong) s += " · AI nhường tin này";
  if (boQua) s += " · bỏ qua: " + boQua;
  if (ct.loi) s += " · lỗi: " + ct.loi;
  if (ct.dung_xet_sau) s += " · dừng xét quy tắc sau";
  return s;
}

/* Một dòng quy tắc (UX-07-02): công tắc Bật/Tắt, số thứ tự chạy THẬT (vị
 * trí trong danh sách, cùng thứ tự máy chủ chạy), NẾU / THÌ hai dòng, dấu
 * vết chạy, rồi ↑ ↓ Sửa Xoá. Người không có quyền sửa vẫn thấy công tắc —
 * bị khoá — vì "đang bật hay tắt" là điều họ cần biết. */
function _dongQuyTac(q, i, n, sua) {
  const b = q.bay_ngay || {};
  // Bật mà bảy ngày chưa khớp lần nào là điều đáng nói ra: trông y hệt
  // "đang chạy tốt", nhưng có thể điều kiện viết sai.
  const tinh = b.hong ? `<span class="pill pill--halt">${b.hong} lần hỏng</span> ` : "";
  const lan = b.da_lam ? `${b.da_lam} lần làm trong 7 ngày` + (b.lan_cuoi ? `, gần nhất ${clock(b.lan_cuoi)}` : "")
    : (q.bat ? "chưa khớp lần nào trong 7 ngày" : "");
  const co = [q.dung_xet_sau ? "dừng xét quy tắc sau" : "",
              q.cho_ai_tra_loi ? "AI vẫn trả lời sau mẫu" : ""].filter(Boolean);
  const c = q.lan_chay_cuoi;
  const cuoi = c ? `Lần chạy cuối ${clock(c.luc)}: ${c.tom_tat}` : "";
  // Lỗi cuối hiện NGAY trên dòng quy tắc, không chỉ trong nhật ký chung:
  // nhật ký chung trôi đi sau 20 lần chạy, lỗi thì vẫn còn đó. Nhưng lỗi
  // ĐÃ SỬA (quy tắc được lưu lại sau lỗi) hay quá bảy ngày thì thôi hiện —
  // một dòng đỏ mãi là dòng người ta thôi đọc.
  const loiCon = q.loi_cuoi && Date.parse(q.loi_cuoi.luc) > Date.parse(q.sua_luc)
    && Date.now() - Date.parse(q.loi_cuoi.luc) < 7 * 864e5;
  const loi = loiCon ? `<span class="qt-dong__vi"><span class="pill pill--halt">Lỗi gần nhất ${
    esc(clock(q.loi_cuoi.luc))}</span> ${esc(q.loi_cuoi.loi)}</span>` : "";
  const p = _moTaQuyTacPhan(q);
  const id = esc(q.id);
  return `
    <div class="row qt-dong${q.bat ? "" : " is-tat"}">
      <span class="row__flag ${!q.bat ? "row__flag--plain" : b.hong ? "row__flag--halt" : "row__flag--auto"}"></span>
      <span class="row__body">
        <span class="qt-dong__dau">
          <span class="qt-dong__so" title="Chạy thứ ${i + 1} — giá trị ưu tiên ${esc(q.thu_tu)}">${i + 1}</span>
          <span class="row__title">${esc(q.ten)}</span>
          ${q.bat ? "" : '<span class="tag tag--plain">Đang tắt</span>'}
          ${co.length ? `<span class="pill">${esc(co.join(" · "))}</span>` : ""}
        </span>
        <span class="qt-dong__vi"><b class="qt-dong__nhan">Nếu</b> ${esc(p.neu)}</span>
        <span class="qt-dong__vi"><b class="qt-dong__nhan">Thì</b> ${esc(p.thi)}</span>
        <span class="row__sub">${tinh}${esc(lan)}</span>
        ${cuoi ? `<span class="row__sub">${esc(cuoi)}</span>` : ""}${loi}
      </span>
      <span class="row__side qt-dong__nut">
        <label class="switch" title="${q.bat ? "Đang bật — bấm để tắt" : "Đang tắt — bấm để bật"}">
          <input type="checkbox" role="switch" data-qt-bat="${id}" ${q.bat ? "checked" : ""} ${sua ? "" : "disabled"}
            aria-label="Bật quy tắc ${esc(q.ten)}"> ${q.bat ? "Bật" : "Tắt"}</label>
        <span class="qt-dong__hang">
          ${sua ? `<button type="button" class="btn btn--sm btn--ghost btn--icon" data-qt-len="${id}" ${i === 0 ? "disabled" : ""}
              aria-label="Đưa «${esc(q.ten)}» lên trước" title="Chạy sớm hơn">↑</button>
            <button type="button" class="btn btn--sm btn--ghost btn--icon" data-qt-xuong="${id}" ${i === n - 1 ? "disabled" : ""}
              aria-label="Đưa «${esc(q.ten)}» xuống sau" title="Chạy muộn hơn">↓</button>` : ""}
          <button type="button" class="btn btn--sm btn--ghost" data-qt-nhatky="${id}">Nhật ký</button>
          ${sua ? `<button type="button" class="btn btn--sm" data-qt-sua="${id}">Sửa</button>
            <button type="button" class="btn btn--sm btn--halt" data-qt-xoa="${id}">Xoá</button>` : ""}
        </span>
      </span>
    </div>`;
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
  const tao = $("#qtTaoMoi");
  if (tao) tao.hidden = !sua;
  let r;
  try { r = await api("/tu-dong"); } catch (e) { toast(e.message, true); return; }
  state.quyTac = r.quy_tac;
  await napONhanQuyTac();
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

  const html = r.quy_tac.length
    ? r.quy_tac.map((q, i) => _dongQuyTac(q, i, r.quy_tac.length, sua)).join("")
    : `<p class="empty">Chưa có quy tắc nào — agent và định tuyến chạy như thường.${
      sua ? " Bấm «+ Tạo quy tắc» để thêm." : ""}</p>`;
  // Chỉ thay khi đổi: vòng 6 giây thay lại cả khối là công tắc đang được
  // rê chuột nhấp nháy, và nút ↑ vừa bấm mất tiêu điểm bàn phím.
  if (ds.innerHTML !== html) ds.innerHTML = html;
  await loadQuyTacLanChay();
}

async function loadQuyTacLanChay() {
  const o = $("#qtLanChay");
  if (!o) return;
  // Lọc theo một quy tắc (nút "Nhật ký" trên dòng quy tắc). Quy tắc đã bị
  // xoá thì bỏ lọc — không để khung trống mà không nói vì sao.
  const loc = (state.quyTac || []).find((q) => q.id === state.qtLoc);
  if (!loc) state.qtLoc = null;
  const tieuDe = $("#qtLanChayTieuDe");
  if (tieuDe) {
    tieuDe.innerHTML = loc ? `Lần chạy gần đây — «${esc(loc.ten)}» <button type="button" class="btn btn--sm btn--ghost" data-qt-nhatky="">Xem tất cả</button>`
      : "Lần chạy gần đây";
  }
  let r;
  try {
    r = await api("/tu-dong/lan-chay?gioi_han=20" + (loc ? `&quy_tac_id=${encodeURIComponent(loc.id)}` : ""));
  } catch (e) { toast(e.message, true); return; }
  o.innerHTML = r.lan_chay.length ? r.lan_chay.map((l) => {
    const viec = _tomTatLanChay(l.ket_qua, l.chi_tiet);
    return `<div class="row">
      <span class="row__flag ${l.ket_qua === "hong" ? "row__flag--halt" : l.ket_qua === "da_lam" ? "row__flag--auto" : "row__flag--plain"}"></span>
      <span class="row__body"><span class="row__title">${esc(l.quy_tac)}</span>
        <span class="row__sub">${esc(viec)}</span></span>
      <span class="row__side">${esc(clock(l.luc))}</span>
    </div>`;
  }).join("") : '<p class="empty">Chưa quy tắc nào chạy.</p>';
}

/* ---------------- Biểu mẫu <-> DOM ---------------- */

function _gomQuyTac(f) {
  return quyTacTuGiaTri(_docForm(f), _khoiHien(f));
}

function _docForm(f) {
  const v = {
    ten: f.ten.value, thu_tu: f.thu_tu.value, bat: f.bat.checked,
    dung_xet_sau: f.dung_xet_sau.checked, cho_ai_tra_loi: f.cho_ai_tra_loi.checked,
    kenh: $$("[data-qt-kenh]:checked", f).map((c) => c.value),
    hd_tao_viec_tu_giao: !!(f.hd_tao_viec_tu_giao && f.hd_tao_viec_tu_giao.checked),
  };
  for (const k of ["chua_tu", "ngoai_gio", "lan_dau", ...QT_NHAN_O, "hd_gan_nhan_hoi_thoai",
                   "hd_gan_nhan_khach", "hd_gui_mau", "hd_tao_viec", "hd_chuyen_nguoi"]) {
    v[k] = f[k].value;
  }
  return v;
}

function _khoiHien(f) {
  return new Set($$("[data-qt-o]", f).filter((k) => !k.hidden).map((k) => k.dataset.qtO));
}

function _datQuyTac(f, q) {
  const { v, hien } = giaTriTuQuyTac(q);
  f.qt_id.value = q.id; f.ten.value = v.ten; f.thu_tu.value = v.thu_tu; f.bat.checked = v.bat;
  f.dung_xet_sau.checked = v.dung_xet_sau; f.cho_ai_tra_loi.checked = v.cho_ai_tra_loi;
  $$("[data-qt-kenh]", f).forEach((c) => { c.checked = v.kenh.includes(c.value); });
  for (const k of ["chua_tu", "ngoai_gio", "lan_dau", "hd_gui_mau", "hd_tao_viec", "hd_chuyen_nguoi"]) {
    f[k].value = v[k];
  }
  for (const k of [...QT_NHAN_O, "hd_gan_nhan_hoi_thoai", "hd_gan_nhan_khach"]) _datONhan(f[k], v[k]);
  if (f.hd_tao_viec_tu_giao) f.hd_tao_viec_tu_giao.checked = v.hd_tao_viec_tu_giao;
  // Đặt mở rộng "Thứ tự chạy" khi quy tắc dùng cờ ít gặp — không thì cờ
  // nằm khuất mà vẫn có hiệu lực.
  const nc = $(".qt-nang-cao", f);
  if (nc) nc.open = v.dung_xet_sau;
  _hienKhoi(f, hien);
}

function _xoaFormQuyTac() {
  const f = $("#qtForm");
  if (!f) return;
  f.reset(); f.qt_id.value = "";
  $$("[data-qt-kenh]", f).forEach((c) => { c.checked = false; });
  _hienKhoi(f, new Set());
}

/* Hiện đúng các khối trong `hien`; mục menu "+ Thêm…" của khối đã hiện thì
 * ẩn đi (mỗi loại một lần — như máy chủ đọc). */
function _hienKhoi(f, hien) {
  $$("[data-qt-o]", f).forEach((k) => { k.hidden = !hien.has(k.dataset.qtO); });
  $$("[data-qt-mo]", f).forEach((b) => { b.hidden = hien.has(b.dataset.qtMo); });
  for (const nhom of ["neu", "thi"]) {
    const trong = $(`[data-qt-trong="${nhom}"]`, f);
    const coKhoi = $$(`[data-qt-nhom="${nhom}"] [data-qt-o]`, f).some((k) => !k.hidden);
    if (trong) trong.hidden = coKhoi;
    const them = $(`[data-qt-them="${nhom}"]`, f);
    if (them) them.hidden = !$$("[data-qt-mo]", them).some((b) => !b.hidden);
  }
}

/* Bỏ một khối: XOÁ giá trị rồi mới ẩn — lớp thứ hai sau `quyTacTuGiaTri`
 * (vốn đã bỏ qua khối ẩn), để mở lại khối là ô trống, không phải giá trị cũ. */
function _boKhoi(f, o) {
  const k = $(`[data-qt-o="${o}"]`, f);
  if (!k) return;
  $$("input, select, textarea", k).forEach((x) => {
    if (x.type === "checkbox") x.checked = false; else x.value = "";
  });
  _hienKhoi(f, new Set([..._khoiHien(f)].filter((x) => x !== o)));
}

function _moKhoi(f, o) {
  const k = $(`[data-qt-o="${o}"]`, f);
  if (!k) return;
  // Ô chọn hai chiều (giờ làm việc, tin đầu): thêm điều kiện là đã muốn
  // lọc — chọn sẵn vế đầu thay vì "bất kỳ", vốn bằng với không thêm.
  $$("select", k).forEach((s) => {
    if (!s.value && !s.dataset.qtNhan && s.options.length > 1) s.value = s.options[1].value;
  });
  _hienKhoi(f, new Set([..._khoiHien(f), o]));
  $("input:not([type=checkbox]), select, textarea", k)?.focus();
}

/* ---------------- Ngăn sửa quy tắc ---------------- */
/* Sửa trong NGĂN bên phải thay vì biểu mẫu dưới đáy danh sách: bấm "Sửa" ở
 * quy tắc đầu là biểu mẫu nằm tận cuối trang, người sửa không biết nó đã
 * mở, và không thấy được quy tắc mình đang sửa nằm đâu trong thứ tự. */
function moNganQuyTac(q) {
  const f = $("#qtForm");
  if (!f || f.hidden) return;          // `hidden` = không có quyền sửa
  _xoaFormQuyTac();
  if (q) _datQuyTac(f, q);
  $("#qtNganTieuDe").textContent = q ? `Sửa quy tắc «${q.ten}»` : "Tạo quy tắc";
  $("#qtNgan").hidden = false;
  $("#qtNganNen").hidden = false;
  f.ten.focus();
}

function dongNganQuyTac() {
  if ($("#qtNgan")) $("#qtNgan").hidden = true;
  if ($("#qtNganNen")) $("#qtNganNen").hidden = true;
}

$("#qtTaoMoi")?.addEventListener("click", () => moNganQuyTac(null));
$("#qtNganDong")?.addEventListener("click", dongNganQuyTac);
$("#qtNganNen")?.addEventListener("click", dongNganQuyTac);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && $("#qtNgan") && !$("#qtNgan").hidden) dongNganQuyTac();
});

$("#qtForm")?.addEventListener("click", (ev) => {
  const f = ev.currentTarget;
  const mo = ev.target.closest("[data-qt-mo]");
  const bo = ev.target.closest("[data-qt-bo]");
  if (mo) {
    const menu = mo.closest("details");
    if (menu) menu.open = false;
    _moKhoi(f, mo.dataset.qtMo);
  } else if (bo) {
    _boKhoi(f, bo.dataset.qtBo);
  }
});

// "Nhật ký" lọc khung lần chạy theo một quy tắc; "Xem tất cả" bỏ lọc. Gắn
// vào khung CHA vì nút "Xem tất cả" nằm ngoài #qtDs.
$("#cc-tu-dong")?.addEventListener("click", (ev) => {
  const b = ev.target.closest("[data-qt-nhatky]");
  if (!b) return;
  state.qtLoc = b.dataset.qtNhatky || null;
  loadQuyTacLanChay();
  if (state.qtLoc) $("#qtLanChay")?.scrollIntoView({ block: "nearest" });
});

/* Đổi chỗ với quy tắc kề bên rồi gửi CẢ danh sách (`/tu-dong/sap-xep`):
 * máy chủ đánh số lại 10, 20, 30… — xem lý do ở tu_dong_api.sap_xep. */
async function _doiCho(id, buoc) {
  const ids = (state.quyTac || []).map((q) => q.id);
  const i = ids.indexOf(id);
  const j = i + buoc;
  if (i < 0 || j < 0 || j >= ids.length) return;
  [ids[i], ids[j]] = [ids[j], ids[i]];
  await api("/tu-dong/sap-xep", { method: "POST", body: JSON.stringify({ ids }) });
  toast("Đã đổi thứ tự chạy.");
}

$("#qtDs")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-qt-sua], [data-qt-xoa], [data-qt-len], [data-qt-xuong]");
  if (!b) return;
  const id = b.dataset.qtSua || b.dataset.qtXoa || b.dataset.qtLen || b.dataset.qtXuong;
  const q = (state.quyTac || []).find((x) => x.id === id);
  if (!q) return;
  try {
    if (b.dataset.qtSua) { moNganQuyTac(q); return; }
    if (b.dataset.qtLen || b.dataset.qtXuong) {
      await _doiCho(id, b.dataset.qtLen ? -1 : 1);
    } else {
      const ok = await hoiHop({ tieu_de: `Xoá quy tắc «${q.ten}»?`,
        phu: "Nhật ký lần chạy của quy tắc cũng bị xoá. Muốn dừng tạm thì gạt công tắc sang Tắt.",
        nut: "Xoá", nguy_hiem: true });
      if (!ok) return;
      await api(`/tu-dong/${id}`, { method: "DELETE" });
      toast("Đã xoá quy tắc.");
    }
  } catch (e) { toast(e.message, true); }
  loadQuyTac();
});

/* Công tắc Bật/Tắt: gửi lại CẢ quy tắc như nút cũ — máy chủ giữ cờ khi
 * thiếu khoá, nhưng giao diện vẫn gửi đủ (hai lớp). Hỏng (422: bật quy tắc
 * có mẫu đã xoá) thì vẽ lại theo máy chủ, công tắc không nói dối. */
$("#qtDs")?.addEventListener("change", async (ev) => {
  const b = ev.target.closest("[data-qt-bat]");
  if (!b) return;
  const q = (state.quyTac || []).find((x) => x.id === b.dataset.qtBat);
  if (!q) return;
  try {
    await api(`/tu-dong/${q.id}`, { method: "PUT", body: JSON.stringify({
      ten: q.ten, su_kien: q.su_kien, dieu_kien: q.dieu_kien, hanh_dong: q.hanh_dong,
      bat: !q.bat, thu_tu: q.thu_tu,
      dung_xet_sau: q.dung_xet_sau, cho_ai_tra_loi: q.cho_ai_tra_loi }) });
    toast(q.bat ? "Đã tắt quy tắc." : "Đã bật quy tắc.");
  } catch (e) { toast(e.message, true); }
  loadQuyTac();
});

$("#qtForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const v = _docForm(f);
  const hien = _khoiHien(f);
  const trong = khoiTrong(v, hien);
  if (trong.length) {
    toast(`Ô «${trong[0]}» đang trống — điền vào, hoặc bấm × để bỏ.`, true);
    return;
  }
  const body = quyTacTuGiaTri(v, hien);
  if (!body.hanh_dong.length) { toast("Thêm ít nhất một hành động ở phần «Thì».", true); return; }
  const id = f.qt_id.value;
  try {
    await api(id ? `/tu-dong/${id}` : "/tu-dong",
              { method: id ? "PUT" : "POST", body: JSON.stringify(body) });
    toast("Đã lưu quy tắc.");
    _xoaFormQuyTac();
    dongNganQuyTac();
    loadQuyTac();
  } catch (e) { toast(e.message, true); }   // 422: giữ chữ để sửa
});
$("#qtHuy")?.addEventListener("click", () => { _xoaFormQuyTac(); dongNganQuyTac(); });
