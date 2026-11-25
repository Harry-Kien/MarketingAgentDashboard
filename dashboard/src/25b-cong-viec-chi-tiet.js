/* ================= CÔNG VIỆC — ngăn chi tiết (UX-14-05/06/07) =================
 *
 * Chi tiết mở ở NGĂN BÊN PHẢI cạnh danh sách (máy tính) hoặc tấm phủ TOÀN
 * MÀN (điện thoại, ≤1180px). Trước đây nó nằm DƯỚI cả danh sách: bấm "Chi
 * tiết" ở dòng đầu là trang cuộn mất danh sách, đóng lại là mất chỗ đang
 * đọc — đo được ở danh sách 40 việc.
 *
 * Hành động theo TRẠNG THÁI: một nút chính + menu "⋯" (cùng khuôn với thanh
 * hội thoại, 03b). Mười nút ngang nhau cắt chữ trên điện thoại và không nói
 * bước tiếp theo là gì.
 */

const cvxCt = {
  locLs: "",            // nhóm lịch sử đang lọc: "" = tất cả (MD-UX-14-06)
  ketQua: "",           // nháp ô hoàn thành nhanh — sống qua vòng làm mới
  chon: null,           // ô chọn người nhận đang mở: { ds, gia_tri, ghi_chu }
  quayVe: null,         // phần tử để trả focus khi đóng ngăn
};

/* ---------------- ngăn ---------------- */

function cvxNganHep() { return window.matchMedia("(max-width: 1180px)").matches; }

function cvxMoNgan() {
  const o = cvx.el && $("#cvxCt", cvx.el);
  if (!o) return;
  if (o.hidden) cvxCt.quayVe = document.activeElement;
  o.hidden = false;
  $(".cvx-bo", cvx.el)?.classList.add("is-ngan");
  /* Tấm phủ toàn màn: khoá cuộn trang phía sau, không thì vuốt trong tấm
     phủ cuộn luôn danh sách bên dưới. */
  document.body.classList.toggle("cvx-khoa-cuon", cvxNganHep());
}

function cvxDongNgan() {
  const o = cvx.el && $("#cvxCt", cvx.el);
  cvx.moId = null; cvx.chiTiet = null; cvxCt.chon = null; cvxCt.ketQua = ""; cvxCt.locLs = "";
  if (o) { o.hidden = true; o.innerHTML = ""; }
  $(".cvx-bo", cvx.el)?.classList.remove("is-ngan");
  document.body.classList.remove("cvx-khoa-cuon");
  $$("#cvxDs .row", cvx.el).forEach((r) => r.classList.remove("is-on"));
  const ve = cvxCt.quayVe;
  cvxCt.quayVe = null;
  if (ve && document.contains(ve)) ve.focus({ preventScroll: true });
}

/* ---------------- tải ---------------- */

async function cvxTaiChiTiet(id, cuon = true) {
  if (!id) return;
  let d;
  try { d = await api(`/cong-viec/${encodeURIComponent(id)}`); }
  catch (e) {
    if (cvx.moId === id || cuon) cvxDongNgan();
    if (e.ma === 404) toast("Việc này không còn hoặc bạn không có quyền xem.", true);
    else toast(e.message, true);
    return;
  }
  const doiViec = cvx.moId !== id;
  cvx.moId = id;
  cvx.chiTiet = d;
  if (doiViec) { cvxCt.chon = null; cvxCt.ketQua = ""; cvxCt.locLs = ""; }
  cvx.dm = cvx.dm || { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon };
  /* Việc mở từ chuông có thể không nằm trong bộ lọc đang chọn: thêm vào
     `congViec.ds` để hộp xác nhận đơn vẫn tìm thấy nó, và ghim lên đầu
     danh sách (UX-19-01). */
  if (!congViec.ds.some((x) => x.id === id)) congViec.ds = congViec.ds.concat([d.cong_viec]);
  const trongDs = cvx.ds.some((x) => x.id === id);
  const ghimCu = cvx.ghim && cvx.ghim.id;
  cvx.ghim = trongDs ? null : d.cong_viec;
  if (cvx.ghim || ghimCu) cvxVeDs();
  cvxMoNgan();
  cvxVeChiTiet();
  $$("#cvxDs .row", cvx.el).forEach((r) => r.classList.toggle("is-on", r.dataset.cv === id));
  if (cuon) {
    const tieu = $("#cvxCtTen", cvx.el);
    if (tieu) tieu.focus({ preventScroll: true });
    if (!cvxNganHep()) $("#cvxCt", cvx.el).scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

/* ---------------- hành động theo trạng thái ---------------- */

/* Một nút CHÍNH (bước tiếp theo hiển nhiên) + phần còn lại vào menu. Trả
   { chinh: [ma, nhan, lop] | null, them: [[ma, nhan, goi_y, nguy_hiem]], xongNhanh }. */
function cvxHanhDong(v) {
  const sua = cvxCo("cong_viec.sua");
  const giao = cvxCo("cong_viec.giao");
  const mo = v.trang_thai === "moi" || v.trang_thai === "dang_lam";
  const laCuaToi = v.nguoi_nhan && String(v.nguoi_nhan) === String(state.toiId || "");
  const xuLyDon = typeof cvLaXuLyDon === "function" && cvLaXuLyDon(v);
  const xacNhanDon = mo && xuLyDon && typeof cvDuocXacNhan === "function" && cvDuocXacNhan();
  const batDau = mo && v.trang_thai === "moi" && sua && (laCuaToi || giao) && !v.chua_phan_cong;
  const xongNhanh = mo && sua && !xuLyDon;
  let chinh = null;
  if (mo && v.chua_phan_cong && sua) chinh = ["nhan", "Nhận việc", "btn--primary"];
  else if (xacNhanDon) chinh = ["don", "Xác nhận kết quả đơn…", "btn--primary"];
  else if (batDau) chinh = ["bat-dau", "Bắt đầu làm", "btn--primary"];
  else if (xongNhanh) chinh = ["xong-nhanh", "Hoàn thành", "btn--go"];
  else if (!mo && sua && !xuLyDon) chinh = ["mo-lai", "Mở lại", ""];
  const them = [];
  const co = (ma) => chinh && chinh[0] === ma;
  if (batDau && !co("bat-dau")) them.push(["bat-dau", "Bắt đầu làm", "Chuyển sang Đang thực hiện"]);
  if (xongNhanh && !co("xong-nhanh")) them.push(["xong-nhanh", "Hoàn thành", "Ghi kết quả rồi đóng việc"]);
  if (mo && sua) them.push(["tien-do", "Cập nhật tiến độ…", "Ghi một dòng vào lịch sử, không đổi trạng thái"]);
  if (mo && giao) them.push(["giao", v.nguoi_nhan ? "Chuyển cho người khác…" : "Giao cho…",
    "Xem ai đang trong ca và đang giữ bao nhiêu việc"]);
  if (mo && giao && v.chua_phan_cong) them.push(["tu-dong", "Tự phân công", "Người trong ca, lâu nhất chưa được giao"]);
  if (sua) them.push(["sua", "Sửa thông tin…", "Tiêu đề, mô tả, ưu tiên, hạn"]);
  if (!mo && sua && !xuLyDon && !co("mo-lai")) them.push(["mo-lai", "Mở lại", "Đưa về Đang thực hiện"]);
  if (mo && sua) them.push(["huy", "Hủy việc…", "Cần ghi lý do; người liên quan được báo", true]);
  return { chinh, them, xongNhanh };
}

function cvxVeHanhDong(v) {
  const hd = cvxHanhDong(v);
  /* "Hoàn thành" là chính ô hoàn thành nhanh ngay dưới đầu ngăn — vẽ thêm
     một nút cùng tên ở đầu là hai nút chính cho một việc. */
  const chinh = hd.chinh && hd.chinh[0] !== "xong-nhanh"
    ? `<button type="button" class="btn btn--sm ${hd.chinh[2]}" data-cvx-lam="${hd.chinh[0]}">${esc(hd.chinh[1])}</button>` : "";
  const them = hd.them.length ? `<details class="hd-them cvx-them">
      <summary class="btn btn--sm btn--ghost" aria-label="Hành động khác" title="Hành động khác">⋯</summary>
      <div class="hd-them__menu" role="menu">${hd.them.map(([ma, nhan, goiY, nguy]) =>
        `<button type="button" class="hd-them__muc${nguy ? " cvx-them__nguy" : ""}" role="menuitem" data-cvx-lam="${ma}">
          <span class="hd-them__ten">${esc(nhan)}</span><span class="hd-them__goiy">${esc(goiY)}</span></button>`).join("")}</div>
    </details>` : "";
  return `${chinh}${them}`;
}

/* ---------------- chọn người nhận (MD-UX-14-05) ---------------- */

/* Tình trạng ca từ DỮ LIỆU THẬT (`/cong-viec/nguoi-nhan-duoc` đọc `ca_truc`
   và `ca_nghi`). Không suy đoán gì thêm: một nhãn đoán là một nhãn sai đúng
   lúc người điều phối tin nó. Đang nghỉ đứng trước mọi thứ khác — người có
   lịch nghỉ hôm nay mà hiện "Ngoài ca" là bị giao việc lúc vắng mặt. */
function cvxTinhCa(n) {
  if (n.dang_nghi) return { lop: "nghi", nhan: "Đang nghỉ" };
  if (n.trong_ca_that) return { lop: "trong", nhan: "Đang trong ca" };
  if (n.co_lich) return { lop: "ngoai", nhan: "Ngoài ca" };
  return { lop: "chua", nhan: "Chưa xếp ca" };
}

async function cvxNguoiNhan(congViecId) {
  /* Danh sách người nhận lấy từ /cong-viec/nguoi-nhan-duoc (chỉ cần
     `cong_viec.giao`), không từ /nguoi-dung (cần `nguoi_dung.doc`): người
     điều phối việc không nhất thiết quản lý nhân sự. */
  const q = congViecId ? `?cong_viec_id=${encodeURIComponent(congViecId)}` : "";
  const d = await api(`/cong-viec/nguoi-nhan-duoc${q}`);
  return d.nguoi;
}

/* Danh sách chọn người: mỗi người một thẻ radio với chấm ca, chữ ca, số việc
   mở/quá hạn. `dau` = các lựa chọn đặc biệt đặt trước ([value, nhan, phu]). */
function cvxVeDsNguoi(ten, ds, giaTri, dau = []) {
  const muc = dau.map(([val, nhan, phu]) => `<label class="cvx-ng${String(giaTri) === String(val) ? " is-on" : ""}">
      <input type="radio" name="${ten}" value="${esc(val)}"${String(giaTri) === String(val) ? " checked" : ""}>
      <span class="cvx-ng__ten">${esc(nhan)}</span>${phu ? `<span class="cvx-ng__phu">${esc(phu)}</span>` : ""}</label>`)
    .concat((ds || []).map((n) => {
      const ca = cvxTinhCa(n);
      const bat = String(giaTri) === String(n.id);
      return `<label class="cvx-ng${bat ? " is-on" : ""}${n.cung_kenh === false ? " cvx-ng--khac-kenh" : ""}">
        <input type="radio" name="${ten}" value="${esc(n.id)}"${bat ? " checked" : ""}>
        <span class="cvx-ng__ten"><span class="cvx-cham cvx-cham--${ca.lop}" aria-hidden="true"></span>${esc(n.ten)}</span>
        <span class="cvx-ng__phu">${ca.nhan}${n.san_sang === false ? " · tắt sẵn sàng" : ""}${
          n.cung_kenh === false ? " · KHÔNG thuộc kênh của việc" : ""}</span>
        <span class="cvx-ng__tai${n.so_qua_han ? " cvx-ng__tai--qua" : ""}">${n.so_mo} việc mở${
          n.so_qua_han ? ` · ${n.so_qua_han} quá hạn` : ""}</span>
      </label>`;
    }));
  return `<div class="cvx-ds-ng" role="radiogroup">${muc.join("")}</div>`;
}

function cvxVeChon(v) {
  const c = cvxCt.chon;
  if (!c) return "";
  const dau = v.nguoi_nhan ? [["", "Thu hồi — để Chưa phân công", "người đang giữ được báo"]] : [];
  return `<section class="cvx-muc cvx-muc--chon" aria-label="Chọn người nhận">
    <h3 class="cvx-muc__tieu">${v.nguoi_nhan ? "Chuyển cho người khác" : "Giao việc"}</h3>
    ${c.ds.length || dau.length ? cvxVeDsNguoi("cvx_nguoi", c.ds, c.gia_tri, dau)
      : '<p class="cvx-muc__trong">Chưa có nhân viên nào nhận được việc.</p>'}
    <label class="field"><span>Ghi chú bàn giao <em class="hint">không bắt buộc</em></span>
      <input name="cvx_ghi_chu" maxlength="500" placeholder="Đã gọi một lần, khách hẹn chiều" value="${esc(c.ghi_chu)}"></label>
    <div class="cvx-muc__nut">
      <button type="button" class="btn btn--sm btn--primary" data-cvx-chon-luu>${v.nguoi_nhan ? "Chuyển" : "Giao"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-cvx-chon-thoi>Thôi</button>
    </div>
  </section>`;
}

/* ---------------- vẽ ---------------- */

function cvxVeLienKet(v) {
  const the = [];
  if (v.conversation_id) {
    the.push(`<button type="button" class="cvx-lk" data-cvx-ht="${esc(v.conversation_id)}">
      <span class="cvx-lk__loai">Hội thoại</span><span class="cvx-lk__ten">Mở hội thoại gốc</span></button>`);
  }
  if (v.contact_id) {
    the.push(`<button type="button" class="cvx-lk" data-cvx-kh="${esc(v.contact_id)}">
      <span class="cvx-lk__loai">Khách hàng</span><span class="cvx-lk__ten">${esc(v.khach_ten || "Hồ sơ khách")}</span></button>`);
  }
  if (v.order_id) {
    const nhanDon = (typeof ORDER_LABEL !== "undefined" && ORDER_LABEL[v.order_trang_thai]) || v.order_trang_thai || "";
    the.push(`<button type="button" class="cvx-lk" data-cvx-don="${esc(v.ma_don || "")}">
      <span class="cvx-lk__loai">Đơn hàng</span><span class="cvx-lk__ten">${esc(v.ma_don || "")}${
        nhanDon ? ` · ${esc(nhanDon)}` : ""}</span></button>`);
  }
  return the.length ? `<div class="cvx-lk-ds">${the.join("")}</div>`
    : '<p class="cvx-muc__trong">Việc này không gắn hội thoại, khách hay đơn nào.</p>';
}

function cvxVeLichSu(d) {
  const ds = (d.lich_su || []).slice().reverse();   // mới nhất lên đầu
  const nhom = d.nhom_lich_su || [];
  const dem = (ma) => ds.filter((l) => l.nhom === ma).length;
  const loc = cvxCt.locLs;
  const hien = loc ? ds.filter((l) => l.nhom === loc) : ds;
  const chip = [["", "Tất cả", ds.length]].concat(nhom.map((n) => [n.ma, n.nhan, dem(n.ma)]))
    .map(([ma, nhan, so]) => `<button type="button" class="chip cvx-chip${loc === ma ? " is-on" : ""}"
      data-cvx-ls="${ma}" aria-pressed="${loc === ma}">${esc(nhan)} <span class="cvx-chip__so">${so}</span></button>`).join("");
  const dong = hien.map((l) => {
    const chiTiet = [
      l.tu_nguoi || l.den_nguoi ? `${esc(l.tu_nguoi || "—")} → ${esc(l.den_nguoi || "—")}` : "",
      l.tu_trang_thai || l.den_trang_thai ? `${esc(l.tu_trang_thai || "—")} → ${esc(l.den_trang_thai || "—")}` : "",
      l.ghi_chu ? esc(l.ghi_chu) : "",
    ].filter(Boolean).join(" · ");
    return `<li class="cvx__ls-dong cvx__ls-dong--${esc(l.nhom || "khac")}"><time>${esc(cvxNgay(l.tao_luc))}</time>
      <b>${esc(l.nhan_loai)}</b> <span class="cvx__ls-ai">${esc(l.nguoi)}</span>
      ${chiTiet ? `<span class="cvx__ls-ct">${chiTiet}</span>` : ""}</li>`;
  }).join("");
  return `<div class="cvx-nhanh cvx-nhanh--ls" role="group" aria-label="Lọc lịch sử">${chip}</div>
    <ol class="cvx__ls">${dong || `<li class="cvx-muc__trong">${loc ? "Không có hoạt động loại này." : "Chưa có hoạt động."}</li>`}</ol>`;
}

function cvxVeChiTiet() {
  const o = cvx.el && $("#cvxCt", cvx.el);
  if (!o) return;
  const d = cvx.chiTiet;
  if (!d) { o.innerHTML = ""; return; }
  const v = d.cong_viec;
  const hd = cvxHanhDong(v);
  const tongQuan = [
    ["Người phụ trách", v.nguoi_nhan_ten || (v.chua_phan_cong ? "Chưa phân công" : "—")],
    ["Hạn", v.han ? cvxNgay(v.han) + (v.qua_han ? " — quá hạn" : "") : "Không có"],
    ["Ưu tiên", cvxNhan(v.uu_tien, d.uu_tien)],
    ["Nguồn", v.nhan_nguon],
    ["Người tạo", v.nguoi_giao_ten || v.nhan_nguon],
    ["Tạo lúc", cvxNgay(v.tao_luc)],
    ["Cập nhật", cvxNgay(v.sua_luc)],
  ].concat(v.xong_luc ? [["Hoàn thành lúc", cvxNgay(v.xong_luc)]] : []);
  const ketQua = v.ket_qua || (v.ket_qua_xu_ly_don
    ? `${v.ket_qua_xu_ly_don}${v.ly_do_ket_qua ? " — " + v.ly_do_ket_qua : ""}` : "");
  /* Hoàn thành nhanh (MD-UX-14-04): ngay trong ngăn, không qua hộp thoại.
     Vẫn BẮT BUỘC ghi kết quả — "Hoàn thành" không kèm một chữ nào là việc
     không ai kiểm lại được. Mẫu nhanh chỉ điền sẵn, người ta vẫn sửa được. */
  const xong = hd.xongNhanh ? `<form class="cvx-muc cvx-xong" data-cvx-xong-form novalidate>
      <label class="field"><span>Kết quả xử lý <em class="hint">bắt buộc để hoàn thành</em></span>
        <textarea name="ket_qua" rows="2" maxlength="2000" required
          placeholder="Đã gọi, khách đồng ý nhận hàng chiều mai">${esc(cvxCt.ketQua || v.ket_qua || "")}</textarea></label>
      <div class="cvx-muc__nut">
        <button type="submit" class="btn btn--sm btn--go">Hoàn thành</button>
        <span class="cvx-xong__mau">Mẫu nhanh:
          <button type="button" class="chip" data-cvx-mau="Đã liên hệ khách, xử lý xong.">Đã xử lý xong</button>
          <button type="button" class="chip" data-cvx-mau="Khách không cần hỗ trợ thêm.">Khách không cần nữa</button>
        </span>
      </div>
      <p class="cvx-xong__loi" role="alert"></p>
    </form>` : "";
  o.innerHTML = `<div class="cvx-ngan__dau">
      <div class="cvx-ngan__hang">
        ${cvxTrangThai(v)}${cvxUuTienTag(v)}${v.chua_phan_cong ? '<span class="cvx-tt cvx-tt--trong">Chưa phân công</span>' : ""}
        <button type="button" class="btn btn--sm btn--ghost cvx-ngan__dong" data-cvx-dong aria-label="Đóng chi tiết">✕</button>
      </div>
      <h2 class="cvx-ngan__ten" id="cvxCtTen" tabindex="-1">${esc(v.tieu_de)}</h2>
      <div class="cvx-ngan__hd hd">${cvxVeHanhDong(v)}</div>
    </div>
    <div class="cvx-ngan__than">
      ${cvxVeChon(v)}
      ${xong}
      <section class="cvx-muc"><h3 class="cvx-muc__tieu">Tổng quan</h3>
        <dl class="cvx-tq">${tongQuan.map(([n, g]) => `<div><dt>${esc(n)}</dt><dd>${esc(g)}</dd></div>`).join("")}</dl>
        <div class="cvx-tq__tien">${cvxTienDo(v)}</div>
      </section>
      <section class="cvx-muc"><h3 class="cvx-muc__tieu">Nội dung</h3>
        <p class="cvx-noidung">${v.mo_ta ? esc(v.mo_ta) : '<span class="cvx-muc__trong">Không có mô tả.</span>'}</p>
        ${ketQua ? `<p class="cvx-ketqua"><b>Kết quả:</b> ${esc(ketQua)}</p>` : ""}
      </section>
      <section class="cvx-muc"><h3 class="cvx-muc__tieu">Liên kết</h3>${cvxVeLienKet(v)}</section>
      <section class="cvx-muc"><h3 class="cvx-muc__tieu">Lịch sử hoạt động</h3>${cvxVeLichSu(d)}</section>
    </div>`;
}

/* ---------------- thao tác ---------------- */

async function cvxPut(id, than, xong) {
  try {
    await api(`/cong-viec/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(than) });
    if (xong) toast(xong);
    await cvxLamMoi(true);
    return true;
  } catch (e) { toast(e.message, true); return false; }
}

async function cvxLam(ma) {
  const d = cvx.chiTiet;
  if (!d) return;
  const v = d.cong_viec;
  const id = v.id;
  if (ma === "nhan") return cvxPut(id, { nguoi_nhan: state.toiId, trang_thai: "dang_lam" }, "Bạn đã nhận việc này.");
  if (ma === "bat-dau") return cvxPut(id, { trang_thai: "dang_lam" }, "Đã chuyển sang Đang thực hiện.");
  if (ma === "mo-lai") return cvxPut(id, { trang_thai: "dang_lam" }, "Đã mở lại việc.");
  if (ma === "don") { await cvMoKetQua(id, true); return; }
  if (ma === "xong-nhanh") {
    const o = $("[data-cvx-xong-form] textarea", cvx.el);
    if (o) { o.focus(); o.scrollIntoView({ behavior: "smooth", block: "center" }); }
    return;
  }
  if (ma === "huy") {
    const r = await hoiHop({ tieu_de: "Hủy việc này?", phu: v.tieu_de, nut: "Hủy việc", nguy_hiem: true,
      truong: [{ name: "ghi_chu", label: "Lý do", maxlength: 500, required: true,
                 placeholder: "Khách đã tự xử lý" }] });
    if (!r) return;
    return cvxPut(id, { trang_thai: "huy", ghi_chu: r.ghi_chu }, "Đã hủy việc — người liên quan được báo.");
  }
  if (ma === "tien-do") {
    const r = await hoiHop({ tieu_de: "Cập nhật tiến độ", phu: v.tieu_de, nut: "Ghi",
      truong: [{ name: "noi_dung", label: "Tiến độ", type: "textarea", rows: 3, maxlength: 2000,
                 required: true, placeholder: "Đã gọi lần 1, khách hẹn gọi lại 15h" }] });
    if (!r || !r.noi_dung) return;
    try {
      await api(`/cong-viec/${encodeURIComponent(id)}/tien-do`,
        { method: "POST", body: JSON.stringify({ noi_dung: r.noi_dung }) });
      toast("Đã ghi tiến độ.");
      await cvxLamMoi(true);
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "tu-dong") {
    try {
      const r = await api(`/cong-viec/${encodeURIComponent(id)}/tu-dong-giao`, { method: "POST" });
      toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      await cvxLamMoi(true);
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "giao") {
    let ds;
    try { ds = await cvxNguoiNhan(id); } catch (e) { toast(e.message, true); return; }
    cvxCt.chon = { ds, gia_tri: v.nguoi_nhan || "", ghi_chu: "" };
    cvxVeChiTiet();
    $(".cvx-muc--chon", cvx.el)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    $(".cvx-muc--chon input[type=radio]:checked, .cvx-muc--chon input[type=radio]", cvx.el)?.focus();
    return;
  }
  if (ma === "sua") {
    const r = await hoiHop({ tieu_de: "Sửa việc", nut: "Lưu", truong: [
      { name: "tieu_de", label: "Việc cần làm", required: true, maxlength: 200, value: v.tieu_de },
      { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 3, maxlength: 5000, value: v.mo_ta || "" },
      { name: "uu_tien", label: "Mức ưu tiên", type: "select", value: v.uu_tien,
        options: (d.uu_tien || []).map((u) => ({ value: u.ma, label: u.nhan })) },
      { name: "han", label: "Hạn", type: "date", hint: "để trống là bỏ hạn",
        value: v.han ? String(v.han).slice(0, 10) : "" },
    ] });
    if (!r) return;
    const than = { tieu_de: r.tieu_de, mo_ta: r.mo_ta, uu_tien: r.uu_tien };
    if (r.han) than.han = cvxHan(r.han); else than.xoa_han = true;
    return cvxPut(id, than, "Đã lưu việc.");
  }
}

async function cvxLuuChon() {
  const d = cvx.chiTiet;
  const c = cvxCt.chon;
  if (!d || !c) return;
  const v = d.cong_viec;
  const chon = $(".cvx-muc--chon input[type=radio]:checked", cvx.el);
  const giaTri = chon ? chon.value : "";
  if (!chon || (giaTri === "" && !v.nguoi_nhan)) { toast("Chọn một người nhận.", true); return; }
  if (String(giaTri) === String(v.nguoi_nhan || "")) { toast("Việc đang ở đúng người này rồi.", true); return; }
  const than = giaTri ? { nguoi_nhan: giaTri } : { xoa_nguoi_nhan: true };
  const ghiChu = ($(".cvx-muc--chon [name=cvx_ghi_chu]", cvx.el)?.value || "").trim();
  if (ghiChu) than.ghi_chu = ghiChu;
  cvxCt.chon = null;
  const ok = await cvxPut(v.id, than, giaTri ? "Đã giao — người nhận được báo." : "Đã thu hồi người nhận.");
  if (!ok) { cvxCt.chon = c; cvxVeChiTiet(); }
}

async function cvxXongNhanh(form) {
  const d = cvx.chiTiet;
  if (!d) return;
  const o = form.querySelector("textarea[name=ket_qua]");
  const loi = form.querySelector(".cvx-xong__loi");
  const kq = (o.value || "").trim();
  if (!kq) {
    loi.textContent = "Ghi một câu kết quả trước khi hoàn thành — người sau cần biết đã làm gì.";
    o.focus();
    return;
  }
  const nut = form.querySelector("button[type=submit]");
  nut.disabled = true;
  const ok = await cvxPut(d.cong_viec.id, { trang_thai: "xong", ket_qua: kq }, "Đã hoàn thành.");
  if (ok) cvxCt.ketQua = "";
  else nut.disabled = false;
}

/* Sự kiện của ngăn — gắn MỘT lần lên khung tab (ngăn vẽ lại liên tục). */
function cvxBatSuKienNgan(el) {
  el.addEventListener("click", async (e) => {
    if (!e.target.closest("#cvxCt")) return;
    if (e.target.closest("[data-cvx-dong]")) { cvxDongNgan(); return; }
    const ls = e.target.closest("[data-cvx-ls]");
    if (ls) { cvxCt.locLs = ls.dataset.cvxLs; cvxVeChiTiet(); return; }
    const mau = e.target.closest("[data-cvx-mau]");
    if (mau) {
      const o = $("[data-cvx-xong-form] textarea", el);
      if (o) { o.value = mau.dataset.cvxMau; cvxCt.ketQua = o.value; o.focus(); }
      return;
    }
    if (e.target.closest("[data-cvx-chon-thoi]")) { cvxCt.chon = null; cvxVeChiTiet(); return; }
    if (e.target.closest("[data-cvx-chon-luu]")) { await cvxLuuChon(); return; }
    const lam = e.target.closest("[data-cvx-lam]");
    if (lam) {
      const menu = lam.closest("details");
      if (menu) menu.open = false;
      await cvxLam(lam.dataset.cvxLam);
    }
  });
  el.addEventListener("submit", (e) => {
    const f = e.target.closest("[data-cvx-xong-form]");
    if (!f) return;
    e.preventDefault();
    cvxXongNhanh(f);
  });
  el.addEventListener("input", (e) => {
    if (e.target.matches("[data-cvx-xong-form] textarea")) cvxCt.ketQua = e.target.value;
    if (e.target.matches("[name=cvx_ghi_chu]") && cvxCt.chon) cvxCt.chon.ghi_chu = e.target.value;
  });
  el.addEventListener("change", (e) => {
    if (e.target.matches("[name=cvx_nguoi]") && cvxCt.chon) {
      cvxCt.chon.gia_tri = e.target.value;
      $$(".cvx-muc--chon .cvx-ng", el).forEach((l) => l.classList.toggle("is-on", l.contains(e.target)));
    }
  });
}

/* Esc đóng ngăn — trừ khi hộp hỏi chung hay chuông đang mở: Esc là của chúng. */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !cvx.chiTiet || hoiDangMo) return;
  if (typeof chuong !== "undefined" && chuong.mo) return;
  if (document.querySelector(".cvx-tao:not([hidden])")) return;
  if (!tabDangHien("cv-danh-sach")) return;
  cvxDongNgan();
});
/* Khổ màn đổi (xoay máy, kéo cửa sổ): ngăn đang mở phải đổi theo kiểu
   tấm phủ ↔ cột phải, kể cả khoá cuộn. */
window.matchMedia("(max-width: 1180px)").addEventListener?.("change", () => {
  if (cvx.chiTiet) document.body.classList.toggle("cvx-khoa-cuon", cvxNganHep());
});
