/* ---------------- Nhật ký kiểm toán (phiếu việc mục 18) ----------------
 *
 * Cài đặt & Quản trị → Hệ thống & Nhật ký → tab "Nhật ký". Thay danh sách
 * 50 dòng thô (`/events`) bằng màn TRA CỨU: lọc theo thời gian, hội thoại,
 * loại tác nhân / người, nhóm hành động, trạng thái; phân trang; bảng chi
 * tiết có cấu trúc, và với việc của AI — cả LƯỢT xử lý (tin khách → tài
 * liệu → công cụ → lưới → trả lời).
 *
 * Mọi chữ hiện ở đây đã được máy chủ làm sạch (`lam_sach`): token, khoá,
 * số điện thoại, email, suy luận model không bao giờ tới trình duyệt.
 *
 * Ghi (đánh dấu sự cố, bước can thiệp, kết thúc, giải trình) cần quyền
 * `nhat_ky.su_co` và LUÔN là dòng mới — máy chủ chặn sửa/xoá nhật ký.
 *
 * Cuối tệp: mục "Nhật ký hội thoại" trong panel Chi tiết của MỘT hội thoại
 * (`veNhatKyHoiThoai`, gọi từ 19-trach-nhiem.js) cho nhân viên không có
 * quyền xem toàn bộ nhật ký.
 *
 * ĐỌC ĐƯỢC CHO NGƯỜI VẬN HÀNH (UX-18-01/02/03)
 * Mặc định chỉ hiện việc NGHIỆP VỤ và gộp dòng vận hành/kỹ thuật lặp liền
 * nhau: trước đây vài trăm dòng "ERP ngắt mạch", "bỏ qua tin Zalo" chôn mất
 * một lần nhân viên huỷ đơn. Mỗi dòng đọc thành "ai — làm gì — với đối
 * tượng nào — kết quả gì"; đối tượng bấm được CHỈ khi máy chủ nói người xem
 * mở được (`lien_ket[].mo_duoc`). Mã kỹ thuật (`kind`) chỉ còn trong phần
 * "Dữ liệu kỹ thuật" của chi tiết.
 */

const NK_TONE = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "auto" };
const NK_TAG = { su_co: "halt", loi: "halt", cho_duyet: "assist", chuyen_nguoi: "assist", thanh_cong: "plain" };

/* Ba nấc hiển thị — `muc_do` gửi lên máy chủ (lọc trước LIMIT, phân trang đúng). */
const NK_HIEN = [
  { ma: "nghiep_vu", nhan: "Nghiệp vụ quan trọng", muc: "nghiep_vu" },
  { ma: "van_hanh", nhan: "Thêm vận hành", muc: "nghiep_vu,van_hanh" },
  { ma: "tat_ca", nhan: "Nhật ký kỹ thuật (tất cả)", muc: "" },
];

const NK_LOAI_LK = { hoi_thoai: "Hội thoại", don_hang: "Đơn hàng", cong_viec: "Công việc",
  nhan_vien: "Nhân viên", tai_khoan_kenh: "Tài khoản kênh" };

const nk = { loc: {}, conTro: [], trangNay: null, danhMuc: null, moId: null, xem: "su_kien", el: null,
  hien: "nghiep_vu", gom: true, reqSeq: 0, locNangCao: false };

function nkMoTaHien() {
  if (nk.hien === "nghiep_vu" && (nk.loc.q || nk.loc.loai_doi_tuong || nk.loc.hoi_thoai_id || nk.loc.luot_id)) {
    return "Đang tìm kiếm trên toàn bộ mức sự kiện (bao gồm vận hành và kỹ thuật) khớp điều kiện lọc.";
  }
  return nk.hien === "nghiep_vu"
    ? "Đang ẩn sự kiện vận hành và kỹ thuật chạy nền. Sự cố đã đánh dấu luôn hiện."
    : nk.hien === "van_hanh"
      ? "Thêm sự kiện vận hành: kết nối kênh, đồng bộ, sao lưu, SLA."
      : "Toàn bộ nhật ký, kể cả bước kỹ thuật — dùng khi gỡ lỗi.";
}

function nkCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function nkGio(iso) { return iso ? (typeof gioTin === "function" ? gioTin(iso) : clock(iso)) : ""; }

function nkNgan(id) { return id ? String(id).slice(0, 8) : ""; }

function nkTacNhan(b) {
  const t = b.tac_nhan || {};
  if (t.loai === "nhan_vien") return t.ten ? `Nhân viên · ${t.ten}` : "Nhân viên";
  if (t.loai === "ai") return t.ten ? `AI · ${t.ten}` : "AI";
  if (t.loai === "tich_hop") return t.ten ? `Tích hợp · ${t.ten}` : "Tích hợp ngoài";
  return "Hệ thống";
}

/* Chuyển giá trị ô datetime-local (giờ máy người xem) sang ISO có múi giờ:
 * máy chủ hiểu giờ không múi là giờ Việt Nam, còn người xem có thể ở nơi khác. */
function nkIso(v) {
  if (!v) return "";
  const d = new Date(v);
  return isNaN(d) ? "" : d.toISOString();
}

function nkMucDo() {
  if (nk.hien === "nghiep_vu" && (nk.loc.q || nk.loc.loai_doi_tuong || nk.loc.hoi_thoai_id || nk.loc.luot_id)) {
    return "";
  }
  return (NK_HIEN.find((x) => x.ma === nk.hien) || NK_HIEN[0]).muc;
}

/* `*_o` là giá trị ô nhập (để vẽ lại form), không phải tham số lọc. */
function nkChuoiLoc(them = {}) {
  const p = new URLSearchParams();
  const l = { ...nk.loc, muc_do: nkMucDo(), gom: nk.gom ? "true" : "", ...them };
  for (const [k, v] of Object.entries(l)) {
    if (v !== "" && v != null && !k.endsWith("_o") && k !== "kind_nhan") p.set(k, v);
  }
  return p.toString();
}

/* Hội thoại / đơn / công việc / tài khoản kênh đi qua `diToiLienKet` của
 * chuông thông báo (mở thẳng side panel đơn hàng, chi tiết việc, hội thoại);
 * nhân viên mở tab Nhân sự. */
async function nkDiToi(lk) {
  if (lk.loai === "nhan_vien") { doiMan("ns-nhan-vien"); return; }
  if (typeof diToiLienKet === "function") await diToiLienKet(lk);
}

/* Đối tượng bị tác động: nút đi tới nếu mở được, chữ thường nếu không —
 * liên kết bấm vào ra "không có quyền" là liên kết nói dối. */
function nkDoiTuong(b, toiDa = 3) {
  const ds = (b.lien_ket || []).slice(0, toiDa);
  if (!ds.length) {
    const ten = (b.tai_khoan && b.tai_khoan.ten) || b.doi_tuong || "";
    return ten ? `<span class="nk-dt">${esc(ten)}</span>` : "";
  }
  return ds.map((lk) => lk.mo_duoc
    ? `<button type="button" class="nk-dt nk-dt--mo" data-nk-lk="${esc(lk.loai)}|${esc(lk.id)}"
        title="Mở ${esc((NK_LOAI_LK[lk.loai] || "").toLowerCase())}">${esc(lk.nhan)}</button>`
    : `<span class="nk-dt" title="${esc(NK_LOAI_LK[lk.loai] || "")} — không mở được với quyền hiện tại">${
      esc(lk.nhan)}</span>`).join("");
}

function nkKhoangGio(g) {
  if (!g) return "";
  return `${g.so_lan} lần · ${nkGio(g.tu)} – ${nkGio(g.den)}`;
}

function nkVeKhung(el) {
  const dm = nk.danhMuc || { nhom: [], loai_tac_nhan: [], trang_thai: [], nguoi: [] };
  const chon = (name, nhan, ds, giaTri) => `<label class="field"><span>${nhan}</span>
    <select name="${name}"><option value="">Tất cả</option>${ds.map((x) =>
      `<option value="${esc(x.ma ?? x.id)}"${String(giaTri || "") === String(x.ma ?? x.id) ? " selected" : ""}>${
        esc(x.nhan ?? x.ten)}</option>`).join("")}</select></label>`;
  const suKien = nk.xem === "su_kien";
  const locKind = nk.loc.kind
    ? `<p class="nk-loc-kind"><span class="tag tag--plain">Chỉ loại: ${esc(nk.loc.kind_nhan || nk.loc.kind)}</span>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-bo-kind>Bỏ lọc loại này</button></p>` : "";
  const nangCaoKeys = ["loai_tac_nhan", "nguoi_id", "nhom", "trang_thai", "hoi_thoai_id", "luot_id"];
  const soNangCao = nangCaoKeys.filter((k) => Boolean(nk.loc[k])).length;
  const moNangCao = Boolean(nk.locNangCao || soNangCao > 0);
  el.innerHTML = `<section class="panel">
    <h2 class="panel__head">Nhật ký kiểm toán
      <span class="panel__note">AI, nhân viên và hệ thống · chỉ thêm, không sửa được</span></h2>
    <div class="tabs" role="tablist">
      <button type="button" class="tabbar__nut" data-nk-xem="su_kien" aria-selected="${nk.xem === "su_kien"}">Sự kiện</button>
      <button type="button" class="tabbar__nut" data-nk-xem="de_xuat" aria-selected="${nk.xem === "de_xuat"}">Đề xuất của AI &amp; phê duyệt</button>
    </div>
    <div class="nk-hien" ${suKien ? "" : "hidden"}>
      <!-- KHÔNG dùng lớp .modeswitch__opt: applyRuntime() (01-nen.js) gỡ
           is-on và KHOÁ mọi nút mang lớp ấy khi AI tắt — bộ lọc nhật ký sẽ
           chết theo công tắc AI. -->
      <div class="modeswitch nk-hien__nhom" role="group" aria-label="Mức sự kiện hiển thị">
        ${NK_HIEN.map((x) => `<button type="button" class="nk-hien__opt${nk.hien === x.ma ? " is-on" : ""}"
          data-nk-hien="${x.ma}" aria-pressed="${nk.hien === x.ma}">${esc(x.nhan)}</button>`).join("")}
      </div>
      <label class="nk-gom"><input type="checkbox" data-nk-gom${nk.gom ? " checked" : ""}> Gộp sự kiện lặp liên tiếp</label>
      <p class="hint nk-hien__ghi" data-nk-hien-ghi>${esc(nkMoTaHien())}</p>
      ${locKind}
    </div>
    <form class="form" data-nk-loc ${suKien ? "" : "hidden"}>
      <div class="form__row">
        <label class="field"><span>Tìm kiếm</span><input type="search" name="q" maxlength="120" value="${esc(nk.loc.q || "")}" placeholder="Mã đơn, SKU, tên đối tượng, nội dung…"></label>
        ${chon("loai_doi_tuong", "Loại đối tượng", Object.entries({ ...NK_LOAI_LK, san_pham: "Sản phẩm / Kho", vai_tro: "Vai trò" }).map(([ma, nhan]) => ({ma, nhan})), nk.loc.loai_doi_tuong)}
        <label class="field"><span>Từ</span><input type="datetime-local" name="tu" value="${esc(nk.loc.tu_o || "")}"></label>
        <label class="field"><span>Đến</span><input type="datetime-local" name="den" value="${esc(nk.loc.den_o || "")}"></label>
      </div>
      <details class="nk-loc-nangcao"${moNangCao ? " open" : ""}>
        <summary>Bộ lọc nâng cao${soNangCao ? ` (${soNangCao} đang chọn)` : ""}</summary>
        <div class="form__row">
          ${chon("loai_tac_nhan", "Tác nhân", dm.loai_tac_nhan, nk.loc.loai_tac_nhan)}
          ${chon("nguoi_id", "Người", dm.nguoi, nk.loc.nguoi_id)}
          ${chon("nhom", "Loại hành động", dm.nhom, nk.loc.nhom)}
          ${chon("trang_thai", "Trạng thái", dm.trang_thai, nk.loc.trang_thai)}
          <label class="field"><span>Hội thoại (mã)</span><input name="hoi_thoai_id" value="${esc(nk.loc.hoi_thoai_id || "")}" placeholder="dán mã hội thoại" autocomplete="off"></label>
          <label class="field"><span>Lượt AI (mã)</span><input name="luot_id" value="${esc(nk.loc.luot_id || "")}" autocomplete="off"></label>
        </div>
      </details>
      <div class="rowbtns">
        <button type="submit" class="btn btn--sm btn--primary">Lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-xoa-loc>Xoá lọc</button>
        <button type="button" class="btn btn--sm btn--ghost" data-nk-csv>Xuất CSV</button>
      </div>
    </form>
    <div class="rows" data-nk-ds><p class="empty">Đang tải…</p></div>
    <div class="rowbtns" data-nk-trang></div>
  </section>
  <section class="panel" data-nk-chi-tiet hidden></section>`;
}

/* Một dòng = một câu: AI·tên — làm gì — với ai/cái gì — ra sao. Dòng gộp
 * nói thêm bao nhiêu lần và từ lúc nào tới lúc nào. */
function nkDong(b) {
  const tt = b.trang_thai || {};
  const md = (b.muc_do || {}).ma;
  const g = b.gom;
  const dt = nkDoiTuong(b);
  return `<div class="row nk-dong${nk.moId === b.id ? " is-mo" : ""}${g ? " nk-dong--gop" : ""}" data-nk-dong="${b.id}" role="button" tabindex="0">
    <span class="row__flag row__flag--${NK_TONE[tt.ma] || "plain"}"></span>
    <span class="row__body">
      <span class="row__title nk-dong__dau"><span class="nk-dong__viec">${esc(b.hanh_dong)}</span>
        ${g ? `<span class="tag tag--plain nk-dem" title="${esc(nkKhoangGio(g))}">×${esc(g.so_lan)}</span>` : ""}
        ${md && md !== "nghiep_vu" ? `<span class="tag tag--plain">${esc(b.muc_do.nhan)}</span>` : ""}
        ${tt.ma && tt.ma !== "thanh_cong" ? `<span class="tag tag--${NK_TAG[tt.ma] || "plain"}">${esc(tt.nhan || "")}</span>` : ""}</span>
      <span class="nk-cau"><b class="nk-cau__ai">${esc(nkTacNhan(b))}</b>${dt ? `<span class="nk-cau__noi">với</span>${dt}` : ""}</span>
      ${b.ket_qua ? `<span class="row__sub nk-cau__kq">Kết quả: ${esc(b.ket_qua)}</span>` : ""}
      ${g ? `<span class="row__sub">${esc(nkKhoangGio(g))}
        <button type="button" class="btn btn--sm btn--ghost nk-tung" data-nk-tung="${esc(b.kind)}" data-nk-tung-nhan="${esc(b.hanh_dong)}">Xem từng lần</button></span>` : ""}
    </span>
    <span class="row__side">
      ${b.hoi_thoai_id ? `<button type="button" class="row__nut" data-nk-loc-ht="${esc(b.hoi_thoai_id)}" title="Lọc nhật ký theo hội thoại này">Lọc HT ${esc(nkNgan(b.hoi_thoai_id))}</button>` : ""}
      <span class="row__time">${esc(nkGio(b.luc))}</span>
    </span>
  </div>`;
}

async function nkTai() {
  const el = nk.el;
  if (!el) return;
  const seq = ++nk.reqSeq;
  const ds = el.querySelector("[data-nk-ds]");
  const trang = el.querySelector("[data-nk-trang]");
  ds.setAttribute("aria-busy", "true");
  ds.innerHTML = '<p class="empty">Đang tải…</p>';
  try {
    let kq;
    if (nk.xem === "de_xuat") {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky/de-xuat?" + new URLSearchParams(truoc ? { truoc } : {}).toString());
      if (seq !== nk.reqSeq) return;
      ds.innerHTML = kq.items.length ? kq.items.map(nkDongDeXuat).join("")
        : '<p class="empty">Chưa có đề xuất nào của AI.</p>';
    } else {
      const truoc = nk.conTro[nk.conTro.length - 1];
      kq = await api("/nhat-ky?" + nkChuoiLoc(truoc ? { truoc } : {}));
      if (seq !== nk.reqSeq) return;
      ds.innerHTML = kq.items.length ? kq.items.map(nkDong).join("")
        : '<p class="empty">Không có sự kiện nào khớp bộ lọc.</p>';
    }
    nk.trangNay = kq;
    trang.innerHTML = `${nk.conTro.length ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-truoc>← Mới hơn</button>' : ""}
      <span class="hint">Trang ${nk.conTro.length + 1}</span>
      ${kq.next_cursor ? '<button type="button" class="btn btn--sm btn--ghost" data-nk-sau>Cũ hơn →</button>' : ""}`;
  } catch (e) {
    if (seq !== nk.reqSeq) return;
    ds.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
    trang.innerHTML = "";
  } finally {
    if (seq === nk.reqSeq) ds.setAttribute("aria-busy", "false");
  }
}

function nkDongDeXuat(d) {
  const tt = d.trang_thai || {};
  const tone = (tt.ma === "cho_duyet" || tt.ma === "cho_xu_ly_thu_cong" || tt.ma === "dang_thuc_thi")
    ? "assist"
    : (tt.ma === "tu_choi" || tt.ma === "loi") ? "halt" : "auto";
  const quyet = d.nguoi_quyet
    ? `${tt.ma === "da_xu_ly_thu_cong" ? "xử lý thủ công" : "duyệt"} bởi ${d.nguoi_quyet}${
        d.luc_quyet ? " lúc " + nkGio(d.luc_quyet) : ""}`
    : "";
  const sua = d.nguoi_sua ? `sửa bởi ${d.nguoi_sua}` : "";
  return `<div class="row">
    <span class="row__flag row__flag--${tone}"></span>
    <span class="row__body">
      <span class="row__title">${esc((d.de_xuat_boi || {}).ten || "AI")} đề xuất trả lời
        <span class="tag tag--${tone === "auto" ? "plain" : tone}">${esc(tt.nhan || "")}</span></span>
      <span class="row__sub">${esc(d.tom_tat || "")}</span>
      <span class="row__sub">${esc([sua, quyet].filter(Boolean).join(" · ") || "chưa ai quyết")}</span>
    </span>
    <span class="row__side">
      ${d.luot_id && nkCo("nhat_ky.doc") ? `<button type="button" class="row__nut" data-nk-mo-luot="${esc(d.luot_id)}">Xem lượt AI</button>` : ""}
      <span class="row__time">${esc(nkGio(d.luc_de_xuat))}</span>
    </span>
  </div>`;
}

function nkCT(tieu, chi) {
  return typeof dongCT === "function" ? dongCT(esc(tieu), chi)
    : `<div class="ctt__dong"><b>${esc(tieu)}</b><span>${chi}</span></div>`;
}

/* Một lượt AI theo thứ tự: tin khách → các bước → câu trả lời (kèm căn cứ). */
function nkVeLuot(l) {
  if (!l) return "";
  const buoc = (l.buoc || []).map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc((b.trang_thai || {}).nhan || "")}${
        b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span></div>`).join("");
  const traLoi = (l.tra_loi || []).map((t) => {
    const dv = t.dau_vet || {};
    const tl = (dv.tri_thuc || []).map((x) => `<li><b>${esc(x.title || "(không tên)")}</b>${
      x.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(x.version)}</span>` : ""}${
      x.trich ? `<blockquote class="ctt__trich">${esc(x.trich)}</blockquote>` : ""}</li>`).join("");
    const cc = (dv.cong_cu || []).map((c) => `<li><b>${esc(c.ten)}</b>
      <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></li>`).join("");
    return `<div class="lichsu__dong">
      <b>Câu trả lời · ${esc(t.trang_thai || "")}</b>
      <span class="msg__meta">${esc(nkGio(t.luc))}${t.sua_boi ? " · sửa bởi " + esc(t.sua_boi) : ""}${
        t.duyet_boi ? " · duyệt bởi " + esc(t.duyet_boi) : ""}</span>
      <p>${esc(t.noi_dung || "")}</p>
      ${dv.luoi ? nkCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma || "")) : ""}
      ${dv.chuyen_nguoi && dv.chuyen_nguoi.co ? nkCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : ""}
      <h4 class="ctt__dau">Tài liệu đã dùng (ảnh chụp lúc xử lý)</h4>
      ${tl ? `<ul class="ctt__ds">${tl}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
      <h4 class="ctt__dau">Dữ liệu công cụ trả về (ảnh chụp lúc xử lý)</h4>
      ${cc ? `<ul class="ctt__ds">${cc}</ul>` : '<p class="hint">Không gọi công cụ nào.</p>'}
    </div>`;
  }).join("");
  return `<section class="lichsu" aria-label="Lượt AI">
    <h4 class="ctt__dau">Lượt AI ${esc(nkNgan(l.luot_id))}</h4>
    ${l.tin_khach ? `<div class="lichsu__dong"><b>Tin khách</b>
      <span class="msg__meta">${esc(nkGio(l.tin_khach.luc))}</span>
      <p>${esc(l.tin_khach.noi_dung || "(không đọc được nội dung)")}</p></div>` : ""}
    ${buoc || '<p class="hint">Lượt này không để lại dòng nhật ký nào.</p>'}
    ${traLoi}
  </section>`;
}

function nkVeChiTiet(b) {
  const tt = b.trang_thai || {};
  const ghi = nkCo("nhat_ky.su_co");
  const laSuCo = b.kind === "su_co.danh_dau";
  const nut = [
    ghi && !b.kind.startsWith("su_co.") && b.kind !== "nhat_ky.giai_trinh" && tt.ma !== "su_co"
      ? `<button type="button" class="btn btn--sm btn--halt" data-nk-su-co="${b.id}">Đánh dấu sự cố</button>` : "",
    ghi && laSuCo ? `<button type="button" class="btn btn--sm" data-nk-buoc="${b.id}">Thêm bước can thiệp</button>
      <button type="button" class="btn btn--sm" data-nk-ket-thuc="${b.id}">Kết thúc sự cố</button>` : "",
    ghi ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-giai-trinh="${b.id}">Giải trình / đính chính</button>` : "",
    b.su_kien_goc ? `<button type="button" class="btn btn--sm btn--ghost" data-nk-mo="${b.su_kien_goc}">Mở dòng gốc #${esc(b.su_kien_goc)}</button>` : "",
    `<button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button>`,
  ].join("");
  const lien = (b.lien_quan || []).map((x) => `<div class="lichsu__dong">
      <b>${esc(x.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(x.luc))} · ${esc(nkTacNhan(x))}</span>
      ${x.chi_tiet && x.chi_tiet.ghi_chu ? `<p>${esc(x.chi_tiet.ghi_chu)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.ket_qua ? `<p><b>Kết quả:</b> ${esc(x.chi_tiet.ket_qua)}</p>` : ""}
      ${x.chi_tiet && x.chi_tiet.nhan ? `<p>${esc(x.chi_tiet.nhan)}</p>` : ""}
    </div>`).join("");
  const che = { auto: "AI tự trả lời", assist: "AI soạn nháp chờ duyệt" }[b.che_do_ai] || b.che_do_ai;
  const uq = { khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[b.muc_uy_quyen]
    || b.muc_uy_quyen;
  return `<h2 class="panel__head">${esc(b.hanh_dong)}
      <span class="panel__note">${esc((b.muc_do || {}).nhan || "")} · ${esc((b.nhom || {}).nhan || "")}</span></h2>
    <div class="ctt">
      ${nkCT("Thời gian", esc(new Date(b.luc).toLocaleString("vi-VN")))}
      ${nkCT("Tác nhân", esc(nkTacNhan(b)))}
      ${nkCT("Tài khoản / đối tượng", nkDoiTuong(b, 6) || "—")}
      ${nkCT("Trạng thái", esc(tt.nhan || ""))}
      ${nkCT("Kết quả", esc(b.ket_qua || "—"))}
      ${b.gom ? nkCT("Lặp lại", esc(nkKhoangGio(b.gom))) : ""}
      ${b.che_do_ai ? nkCT("Chế độ AI", esc(che)) : ""}
      ${b.muc_uy_quyen ? nkCT("Mức uỷ quyền", esc(uq)) : ""}
      <details class="ctt__kt"><summary>Dữ liệu kỹ thuật (đã che thông tin nhạy cảm)</summary>
        ${nkCT("Mã sự kiện", `<span class="mono">#${esc(b.id)} · ${esc(b.kind)}</span>`)}
        ${b.hoi_thoai_id ? nkCT("Mã hội thoại", `<span class="mono">${esc(b.hoi_thoai_id)}</span>`) : ""}
        ${b.luot_id ? nkCT("Mã lượt AI", `<span class="mono">${esc(b.luot_id)}</span>`) : ""}
        <pre class="pre">${esc(JSON.stringify(b.chi_tiet || {}, null, 2))}</pre></details>
      ${lien ? `<h4 class="ctt__dau">Sự cố &amp; giải trình</h4><section class="lichsu">${lien}</section>` : ""}
      ${b.luot ? nkVeLuot(b.luot) : ""}
    </div>
    <div class="rowbtns">${nut}</div>`;
}

async function nkMo(id) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  nk.moId = Number(id);
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeChiTiet(await api(`/nhat-ky/${id}`));
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
  khung.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function nkMoLuot(luotId) {
  const khung = nk.el && nk.el.querySelector("[data-nk-chi-tiet]");
  if (!khung) return;
  khung.hidden = false;
  khung.innerHTML = '<p class="hint">Đang tải…</p>';
  try {
    khung.innerHTML = nkVeLuot(await api(`/nhat-ky/luot/${encodeURIComponent(luotId)}`))
      + '<div class="rowbtns"><button type="button" class="btn btn--sm btn--ghost" data-nk-dong-ct>Đóng</button></div>';
  } catch (e) {
    khung.innerHTML = `<p class="empty">Không tải được: ${esc(e.message)}</p>`;
  }
}

/* Ghi một dòng mới (sự cố, bước, kết thúc, giải trình) rồi mở lại dòng gốc. */
async function nkGhi(duong, hop, moLai) {
  const d = await hoiHop(hop);
  if (!d) return;
  try {
    await api(duong, { method: "POST", body: JSON.stringify(d) });
    toast("Đã ghi vào nhật ký.");
    await nkTai();
    if (moLai) await nkMo(moLai);
  } catch (e) { toast(e.message, true); }
}

async function nkXuLyClick(e) {
  const tim = (k) => e.target.closest(`[${k}]`);
  let o;
  if ((o = tim("data-nk-lk"))) {
    /* Đi tới đối tượng bằng đường điều hướng sẵn có của chuông thông báo
       (19-thong-bao.js) — một lối thứ hai là một chỗ nữa để lệch. */
    e.stopPropagation();
    const [loai, id] = o.dataset.nkLk.split("|");
    await nkDiToi({ loai, id });
  } else if ((o = tim("data-nk-tung"))) {
    e.stopPropagation();
    nk.loc = { kind: o.dataset.nkTung, kind_nhan: o.dataset.nkTungNhan };
    nk.hien = "tat_ca"; nk.gom = false; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if (tim("data-nk-bo-kind")) {
    const { kind: _k, kind_nhan: _n, ...con } = nk.loc;
    nk.loc = con; nk.conTro = []; nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-hien"))) {
    nk.hien = o.dataset.nkHien; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-xem"))) {
    nk.xem = o.dataset.nkXem; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-loc-ht"))) {
    e.stopPropagation();
    nk.loc = { hoi_thoai_id: o.dataset.nkLocHt }; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if ((o = tim("data-nk-mo-luot"))) {
    await nkMoLuot(o.dataset.nkMoLuot);
  } else if ((o = tim("data-nk-mo"))) {
    await nkMo(o.dataset.nkMo);
  } else if ((o = tim("data-nk-dong"))) {
    await nkMo(o.dataset.nkDong);
  } else if (tim("data-nk-dong-ct")) {
    nk.moId = null;
    const k = nk.el.querySelector("[data-nk-chi-tiet]"); k.hidden = true; k.innerHTML = "";
  } else if (tim("data-nk-sau")) {
    if (nk.trangNay && nk.trangNay.next_cursor) { nk.conTro.push(nk.trangNay.next_cursor); await nkTai(); }
  } else if (tim("data-nk-truoc")) {
    nk.conTro.pop(); await nkTai();
  } else if (tim("data-nk-xoa-loc")) {
    nk.loc = {}; nk.hien = "nghiep_vu"; nk.gom = true; nk.conTro = [];
    nkVeKhung(nk.el); await nkTai();
  } else if (tim("data-nk-csv")) {
    /* CSV theo đúng bộ lọc và mức đang xem (trừ lượt AI — xuất một lượt thì
       xem ngay trên màn này là đủ). CSV luôn là từng dòng, không gộp. */
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(nk.loc)) {
      if (v && k !== "kind_nhan" && !k.endsWith("_o")) p.set(k, v);
    }
    if (nkMucDo()) p.set("muc_do", nkMucDo());
    window.open("/api/nhat-ky/xuat.csv?" + p.toString(), "_blank");
  } else if ((o = tim("data-nk-su-co"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkSuCo}/su-co`, {
      tieu_de: "Đánh dấu sự cố", nut: "Đánh dấu", nguy_hiem: true,
      phu: "Ghi thành một dòng MỚI trỏ về hành động này; dòng gốc giữ nguyên.",
      truong: [{ name: "ghi_chu", label: "Vì sao đây là sự cố", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkSuCo);
  } else if ((o = tim("data-nk-buoc"))) {
    const dm = (nk.danhMuc && nk.danhMuc.buoc_can_thiep) || [];
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkBuoc}/buoc`, {
      tieu_de: "Bước can thiệp", nut: "Ghi bước",
      truong: [
        { name: "loai", label: "Đã làm gì", type: "select", required: true,
          options: dm.map((x) => ({ value: x.ma, label: x.nhan })) },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkBuoc);
  } else if ((o = tim("data-nk-ket-thuc"))) {
    await nkGhi(`/nhat-ky/su-co/${o.dataset.nkKetThuc}/ket-thuc`, {
      tieu_de: "Kết thúc sự cố", nut: "Kết thúc",
      truong: [
        { name: "ket_qua", label: "Kết quả", required: true, maxlength: 500 },
        { name: "ghi_chu", label: "Ghi chú", type: "textarea", maxlength: 2000 },
      ],
    }, o.dataset.nkKetThuc);
  } else if ((o = tim("data-nk-giai-trinh"))) {
    await nkGhi(`/nhat-ky/${o.dataset.nkGiaiTrinh}/giai-trinh`, {
      tieu_de: "Giải trình / đính chính", nut: "Ghi",
      phu: "Nhật ký không sửa được. Lời giải trình là một dòng mới đi kèm dòng này.",
      truong: [{ name: "ghi_chu", label: "Nội dung", type: "textarea", required: true, maxlength: 2000 }],
    }, o.dataset.nkGiaiTrinh);
  }
}

function nkCapNhatDanhMuc(el) {
  const form = el.querySelector("[data-nk-loc]");
  const dm = nk.danhMuc;
  if (!form || !dm) return;
  const cap = (name, ds) => {
    const sel = form.elements[name];
    if (!sel) return;
    const html = '<option value="">Tất cả</option>' + (ds || []).map((x) =>
      `<option value="${esc(x.ma ?? x.id)}">${esc(x.nhan ?? x.ten)}</option>`).join("");
    ganLuaChon(sel, html);
  };
  cap("loai_tac_nhan", dm.loai_tac_nhan);
  cap("nguoi_id", dm.nguoi);
  cap("nhom", dm.nhom);
  cap("trang_thai", dm.trang_thai);
}

window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["ht-nhat-ky"] = async (el) => {
  nk.el = el;
  if (!nkCo("nhat_ky.doc")) {
    el.innerHTML = '<section class="panel"><p class="empty">Cần quyền "Xem nhật ký kiểm toán" để xem mục này.</p></section>';
    return;
  }
  nkVeKhung(el);
  el.addEventListener("click", (e) => { nkXuLyClick(e); });
  el.addEventListener("change", async (e) => {
    if (!e.target.matches("[data-nk-gom]")) return;
    nk.gom = e.target.checked; nk.conTro = [];
    await nkTai();
  });
  el.addEventListener("keydown", (e) => {
    const d = e.target.closest("[data-nk-dong]");
    if (d && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); nkMo(d.dataset.nkDong); }
  });
  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-nk-loc]");
    if (!f) return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    nk.loc = {
      q: (d.q || "").trim(), loai_doi_tuong: d.loai_doi_tuong || "",
      tu: nkIso(d.tu), den: nkIso(d.den), tu_o: d.tu, den_o: d.den,
      loai_tac_nhan: d.loai_tac_nhan, nguoi_id: d.nguoi_id, nhom: d.nhom,
      trang_thai: d.trang_thai, hoi_thoai_id: (d.hoi_thoai_id || "").trim(),
      luot_id: (d.luot_id || "").trim(),
    };
    nk.conTro = [];
    const ghi = el.querySelector("[data-nk-hien-ghi]");
    if (ghi) ghi.textContent = nkMoTaHien();
    await nkTai();
  });
  el.addEventListener("toggle", (e) => {
    if (e.target.matches(".nk-loc-nangcao")) nk.locNangCao = e.target.open;
  }, true);
  /* Làm mới trang ĐẦU mỗi lần tab hiện lại — trang sau giữ nguyên, kẻo
   * người đang đọc trang 3 bị kéo về trang 1. */
  el.closest("[data-gan]")?.addEventListener("tab:hien", () => { if (!nk.conTro.length) nkTai(); });
  try {
    nk.danhMuc = await api("/nhat-ky/danh-muc");
    nkCapNhatDanhMuc(el);
  } catch (e) { toast(e.message, true); }
  if (!nk.reqSeq) await nkTai();
};

async function nkLamMoi() {
  if (nk.el && !nk.conTro.length && nkCo("nhat_ky.doc")) await nkTai();
}
window.nkLamMoi = nkLamMoi;

/* ---------------- Nhật ký của MỘT hội thoại ----------------
 * Trong panel "Chi tiết" của hội thoại. Chỉ cần `hoi_thoai.doc` và hội
 * thoại thuộc kênh của người xem (máy chủ chặn) — nhân viên trực thấy "AI
 * đã làm gì với khách mình đang giữ" mà không thấy nhật ký cả cửa hàng.
 * Tải khi BẤM, không tải theo vòng 6 giây. */
function veNhatKyHoiThoai(c) {
  const id = String(c.id);
  const bo = (state.nkHT || {})[id];
  if (!bo) {
    return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
      <button type="button" class="btn btn--sm btn--ghost" data-nk-ht="${esc(id)}">Xem việc AI và nhân viên đã làm</button>`;
  }
  if (bo.dangTai) return '<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Đang tải…</p>';
  if (bo.loi) return `<h4 class="ctt__dau">Nhật ký hội thoại</h4><p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  const dong = bo.items.map((b) => `<div class="lichsu__dong">
      <b>${esc(b.hanh_dong)}</b>
      <span class="msg__meta">${esc(nkGio(b.luc))} · ${esc(nkTacNhan(b))} · ${esc((b.trang_thai || {}).nhan || "")}</span>
      ${b.ket_qua ? `<p>${esc(b.ket_qua)}</p>` : ""}
      ${b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? `<button type="button" class="msg__goc-nut" data-nk-ht-luot="${esc(id)}|${esc(b.luot_id)}">${
          bo.luot && bo.luot.luot_id === b.luot_id ? "Ẩn lượt AI" : "Xem lượt AI"}</button>` : ""}
      ${bo.luot && bo.luot.luot_id === b.luot_id && (b.kind === "ai.tu_gui" || b.kind === "ai.soan_nhap")
        ? nkVeLuot(bo.luot) : ""}
    </div>`).join("");
  return `<h4 class="ctt__dau">Nhật ký hội thoại</h4>
    ${dong || '<p class="hint">Chưa có sự kiện nào.</p>'}`;
}

document.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-nk-ht], [data-nk-ht-luot]");
  if (!nut) return;
  state.nkHT = state.nkHT || {};
  if (nut.dataset.nkHt) {
    const id = nut.dataset.nkHt;
    state.nkHT[id] = { dangTai: true };
    if (state.openConv === id && typeof loadThread === "function") loadThread(id);
    try {
      const r = await api(`/nhat-ky/hoi-thoai/${id}?limit=50`);
      state.nkHT[id] = { items: r.items || [] };
    } catch (err) {
      state.nkHT[id] = { loi: err.message };
    }
  } else {
    const [id, luot] = nut.dataset.nkHtLuot.split("|");
    const bo = state.nkHT[id];
    if (!bo) return;
    if (bo.luot && bo.luot.luot_id === luot) { bo.luot = null; }
    else {
      try { bo.luot = await api(`/nhat-ky/hoi-thoai/${id}/luot/${encodeURIComponent(luot)}`); }
      catch (err) { toast(err.message, true); }
    }
  }
  const id = nut.dataset.nkHt || nut.dataset.nkHtLuot.split("|")[0];
  if (state.openConv === id && typeof loadThread === "function") loadThread(id);
});
