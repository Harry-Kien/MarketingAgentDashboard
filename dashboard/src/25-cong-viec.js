/* ================= CÔNG VIỆC (phiếu việc mục 14) =================
 *
 * Hai điểm gắn vào khung tab (01b-dieu-huong.js `ganKhe`):
 *
 *   GAN_TAB["cv-danh-sach"]     Danh sách công việc: xem, tạo, tìm, lọc,
 *                               giao, chuyển, đổi trạng thái, ghi tiến độ,
 *                               ghi kết quả, xem lịch sử hoạt động.
 *   GAN_TAB["cv-ca-truc-viec"]  Khối "Công việc" trong Tổng quan ca trực:
 *                               tồn đọng, chưa phân công, ai đang trong ca.
 *
 * Danh sách cũ (08-tai-khoan.js) vẫn nằm trong `.tab__goc`: mô-đun này hỏng
 * thì ganKhe trả nó lại — màn không trắng. Hộp xác nhận kết quả ĐƠN (đối
 * soát ERPNext) dùng lại nguyên `cvMoKetQua` của tệp ấy, không chép lại:
 * hai bản luồng đối soát là hai chỗ để một chốt an toàn lệch nhau.
 *
 * MỌI NÚT Ở ĐÂY ĐỀU CÓ CHỐT Ở MÁY CHỦ (agent/api/cong_viec.py). Ẩn nút theo
 * quyền chỉ để màn hình không mời một 403 mỗi lần bấm.
 */
window.GAN_TAB = window.GAN_TAB || {};

const cvx = {
  el: null, ds: [], dm: null, moId: null, chiTiet: null,
  loc: { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
         chua_phan_cong: false, qua_han: false },
  nguoiNhan: null, dangTai: false, hen: null,
};

function cvxCo(q) { return !!(state.toiQuyen && state.toiQuyen.has(q)); }

function cvxNgay(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
}

/* Hạn "ngày X" là HẾT ngày X theo giờ máy người dùng (cùng luật màn cũ). */
function cvxHan(ngay) { return ngay ? new Date(ngay + "T23:59:59").toISOString() : null; }

function cvxNhan(ma, ds) {
  const x = (ds || []).find((t) => t.ma === ma);
  return x ? x.nhan : ma;
}

/* Cờ màu theo TÌNH TRẠNG THẬT: quá hạn đỏ dù đang "Đang thực hiện". */
function cvxCo_mau(v) {
  if (v.qua_han) return "halt";
  if (v.trang_thai === "xong") return "auto";
  if (v.trang_thai === "huy") return "spend";
  if (v.chua_phan_cong || v.uu_tien === "gap" || v.uu_tien === "cao") return "assist";
  return "auto";
}

/* Liên kết NGỮ CẢNH (mục 14.8): hội thoại, hồ sơ khách, đơn — bấm là tới. */
function cvxLienKet(v) {
  return [
    v.conversation_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-ht="${esc(v.conversation_id)}">Hội thoại</button>` : "",
    v.contact_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-kh="${esc(v.contact_id)}">Khách${v.khach_ten ? ": " + esc(v.khach_ten) : ""}</button>` : "",
    v.order_id ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-don="${esc(v.ma_don || "")}">Đơn ${esc(v.ma_don || "")}</button>` : "",
  ].join("");
}

function cvxDong(v) {
  const nguoi = v.chua_phan_cong
    ? `<span class="pill pill--warn">${esc((cvx.dm && cvx.dm.nhan_chua_phan_cong) || "Chưa phân công")}</span>`
    : v.nguoi_nhan_ten ? `<span class="pill">${esc(v.nguoi_nhan_ten)}</span>` : "";
  const han = v.han
    ? `<span class="pill${v.qua_han ? " pill--warn" : ""}">${v.qua_han ? "quá hạn " : "hạn "}${esc(hanDoc(v.han))}</span>` : "";
  const nhanDuoc = v.chua_phan_cong && cvxCo("cong_viec.sua");
  return `<div class="row${cvx.moId === v.id ? " is-on" : ""}" data-cv="${esc(v.id)}">
    <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
    <div class="row__main">
      <b>${esc(v.tieu_de)}</b>
      <span class="row__sub">${esc(v.nhan_trang_thai)} · ${esc(cvxNhan(v.uu_tien, cvx.dm && cvx.dm.uu_tien))} · ${
        esc(v.nhan_nguon)}${v.khach_ten ? " · " + esc(v.khach_ten) : ""}${
        v.ma_don ? " · đơn " + esc(v.ma_don) : ""} · tạo ${esc(clock(v.tao_luc))}</span>
    </div>
    <div class="row__side">
      <span>${nguoi} ${han}</span>
      <span class="row__nut">
        ${nhanDuoc ? `<button type="button" class="btn btn--sm" data-cvx-nhan="${esc(v.id)}">Nhận</button>` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-cvx-mo="${esc(v.id)}">Chi tiết</button>
      </span>
    </div>
  </div>`;
}

/* ---------------- tải ---------------- */

async function cvxTaiDs() {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(cvx.loc)) {
    if (v === true) q.set(k, "true");
    else if (v) q.set(k, v);
  }
  const d = await api(`/cong-viec?${q}`);
  cvx.dm = { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon,
             nhan_chua_phan_cong: d.nhan_chua_phan_cong };
  cvx.ds = d.cong_viec;
  /* Hộp xác nhận kết quả ĐƠN của 08-tai-khoan.js tìm việc trong
     `congViec.ds` — giữ cùng danh sách để nó mở được từ màn này. */
  congViec.ds = d.cong_viec;
  congViec.trangThai = d.trang_thai;
  congViec.uuTien = d.uu_tien;
}

async function cvxTaiDem() {
  if (!cvxCo("cong_viec.doc")) return null;
  try {
    const t = await api("/cong-viec/tong-quan");
    $("#c-congviec").textContent = (t.dem.cho_xu_ly + t.dem.dang_thuc_hien) || "";
    return t;
  } catch (e) { console.warn("Không tải được tổng quan công việc", e); return null; }
}

async function cvxLamMoi() {
  if (!cvx.el || cvx.dangTai || !cvxCo("cong_viec.doc")) return;
  cvx.dangTai = true;
  try {
    await cvxTaiDs();
    cvxVeDs();
    if (cvx.moId) await cvxTaiChiTiet(cvx.moId, false);
    cvxTaiDem();
  } catch (e) {
    $("#cvxDs", cvx.el).innerHTML = `<p class="empty">Không tải được công việc: ${esc(e.message)}</p>`;
  } finally { cvx.dangTai = false; }
}

function cvxVeDs() {
  const o = $("#cvxDs", cvx.el);
  o.innerHTML = cvx.ds.length ? cvx.ds.map(cvxDong).join("")
    : '<p class="empty">Không có việc nào trong bộ lọc này.</p>';
}

/* ---------------- chi tiết + lịch sử ---------------- */

async function cvxTaiChiTiet(id, cuon = true) {
  let d;
  try { d = await api(`/cong-viec/${encodeURIComponent(id)}`); }
  catch (e) {
    cvx.moId = null; cvx.chiTiet = null;
    $("#cvxCt", cvx.el).innerHTML = "";
    if (e.ma === 404) toast("Việc này không còn hoặc bạn không có quyền xem.", true);
    else toast(e.message, true);
    return;
  }
  cvx.moId = id;
  cvx.chiTiet = d;
  cvx.dm = cvx.dm || { trang_thai: d.trang_thai, uu_tien: d.uu_tien, nguon: d.nguon };
  /* Việc mở từ chuông có thể không nằm trong bộ lọc đang chọn: thêm vào
     `congViec.ds` để hộp xác nhận đơn vẫn tìm thấy nó. */
  if (!congViec.ds.some((x) => x.id === id)) congViec.ds = congViec.ds.concat([d.cong_viec]);
  cvxVeChiTiet();
  $$("#cvxDs .row", cvx.el).forEach((r) => r.classList.toggle("is-on", r.dataset.cv === id));
  if (cuon) $("#cvxCt", cvx.el).scrollIntoView({ behavior: "smooth", block: "start" });
}

function cvxNutChiTiet(v) {
  const sua = cvxCo("cong_viec.sua");
  const giao = cvxCo("cong_viec.giao");
  const mo = v.trang_thai === "moi" || v.trang_thai === "dang_lam";
  const laCuaToi = v.nguoi_nhan && String(v.nguoi_nhan) === String(state.toiId || "");
  const xuLyDon = typeof cvLaXuLyDon === "function" && cvLaXuLyDon(v);
  const nut = [];
  if (mo && v.chua_phan_cong && sua) nut.push(["nhan", "Nhận việc", ""]);
  if (mo && v.trang_thai === "moi" && sua && (laCuaToi || giao)) nut.push(["bat-dau", "Bắt đầu", ""]);
  if (mo && sua && !xuLyDon) nut.push(["xong", "Hoàn thành…", "btn--go"]);
  if (mo && xuLyDon && typeof cvDuocXacNhan === "function" && cvDuocXacNhan())
    nut.push(["don", "Xác nhận kết quả đơn…", "btn--go"]);
  if (mo && sua) nut.push(["tien-do", "Cập nhật tiến độ…", ""]);
  if (mo && giao) nut.push(["giao", v.nguoi_nhan ? "Chuyển cho…" : "Giao cho…", ""]);
  if (mo && giao && v.chua_phan_cong) nut.push(["tu-dong", "Tự phân công", ""]);
  if (sua) nut.push(["sua", "Sửa…", "btn--ghost"]);
  if (!mo && sua && !xuLyDon) nut.push(["mo-lai", "Mở lại", "btn--ghost"]);
  if (mo && sua) nut.push(["huy", "Hủy việc…", "btn--halt"]);
  return nut.map(([ma, nhan, lop]) =>
    `<button type="button" class="btn btn--sm ${lop}" data-cvx-lam="${ma}">${esc(nhan)}</button>`).join("");
}

function cvxVeChiTiet() {
  const o = $("#cvxCt", cvx.el);
  const d = cvx.chiTiet;
  if (!d) { o.innerHTML = ""; return; }
  const v = d.cong_viec;
  const truong = [
    ["Trạng thái", v.nhan_trang_thai + (v.chua_phan_cong ? " · Chưa phân công" : "")],
    ["Ưu tiên", cvxNhan(v.uu_tien, d.uu_tien)],
    ["Người phụ trách", v.nguoi_nhan_ten || "—"],
    ["Người tạo", v.nguoi_giao_ten || v.nhan_nguon],
    ["Nguồn", v.nhan_nguon],
    ["Hạn", v.han ? cvxNgay(v.han) + (v.qua_han ? " (quá hạn)" : "") : "Không có"],
    ["Tạo lúc", cvxNgay(v.tao_luc)],
    ["Cập nhật lúc", cvxNgay(v.sua_luc)],
    ["Hoàn thành lúc", v.xong_luc ? cvxNgay(v.xong_luc) : "—"],
    ["Mô tả", v.mo_ta || "Không có mô tả"],
    ["Kết quả", v.ket_qua || (v.ket_qua_xu_ly_don
      ? `${v.ket_qua_xu_ly_don}${v.ly_do_ket_qua ? " — " + v.ly_do_ket_qua : ""}` : "Chưa có")],
  ];
  const lichSu = (d.lich_su || []).map((l) => {
    const chiTiet = [
      l.tu_nguoi || l.den_nguoi ? `${esc(l.tu_nguoi || "—")} → ${esc(l.den_nguoi || "—")}` : "",
      l.tu_trang_thai || l.den_trang_thai ? `${esc(l.tu_trang_thai || "—")} → ${esc(l.den_trang_thai || "—")}` : "",
      l.ghi_chu ? esc(l.ghi_chu) : "",
    ].filter(Boolean).join(" · ");
    return `<li class="cvx__ls-dong"><time>${esc(cvxNgay(l.tao_luc))}</time>
      <b>${esc(l.nhan_loai)}</b> <span class="cvx__ls-ai">${esc(l.nguoi)}</span>
      ${chiTiet ? `<span class="cvx__ls-ct">${chiTiet}</span>` : ""}</li>`;
  }).join("");
  o.innerHTML = `<section class="panel cvx__ct" aria-label="Chi tiết công việc">
    <h2 class="panel__head">${esc(v.tieu_de)}
      <button type="button" class="btn btn--sm btn--ghost" data-cvx-dong>Đóng</button></h2>
    <div class="cvk__detail">${truong.map(([nhan, gt], i) => `<div class="cvk__item${i >= 9 ? " cvk__item--wide" : ""}">
      <span class="cvk__label">${esc(nhan)}</span><span class="cvk__value">${esc(gt)}</span></div>`).join("")}</div>
    <div class="row__nut cvx__lienket">${cvxLienKet(v)}</div>
    <div class="row__nut cvx__nut">${cvxNutChiTiet(v)}</div>
    <h3 class="cvx__ls-tieu">Lịch sử hoạt động</h3>
    <ol class="cvx__ls">${lichSu || '<li class="empty">Chưa có hoạt động.</li>'}</ol>
  </section>`;
}

/* ---------------- thao tác ---------------- */

async function cvxNguoiNhan(congViecId) {
  /* Danh sách người nhận lấy từ /cong-viec/nguoi-nhan-duoc (chỉ cần
     `cong_viec.giao`), không từ /nguoi-dung (cần `nguoi_dung.doc`): người
     điều phối việc không nhất thiết quản lý nhân sự. */
  const q = congViecId ? `?cong_viec_id=${encodeURIComponent(congViecId)}` : "";
  const d = await api(`/cong-viec/nguoi-nhan-duoc${q}`);
  return d.nguoi.map((n) => ({
    value: n.id,
    label: `${n.ten}${n.trong_ca_that ? " · đang trong ca" : n.co_lich ? " · ngoài ca" : " · chưa xếp ca"}${
      n.san_sang ? "" : " · tắt sẵn sàng"}${n.cung_kenh ? "" : " · KHÔNG thuộc kênh của việc"} · ${n.so_mo} việc mở`,
  }));
}

async function cvxPut(id, than, xong) {
  try {
    await api(`/cong-viec/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(than) });
    if (xong) toast(xong);
    await cvxLamMoi();
  } catch (e) { toast(e.message, true); }
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
  if (ma === "xong") {
    const r = await hoiHop({ tieu_de: "Hoàn thành việc", phu: v.tieu_de, nut: "Hoàn thành",
      truong: [{ name: "ket_qua", label: "Kết quả", type: "textarea", rows: 4, maxlength: 2000,
                 value: v.ket_qua || "", placeholder: "Đã gọi, khách đồng ý nhận hàng chiều mai" }] });
    if (!r) return;
    return cvxPut(id, { trang_thai: "xong", ...(r.ket_qua ? { ket_qua: r.ket_qua } : {}) }, "Đã hoàn thành.");
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
      await cvxTaiChiTiet(id, false);
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "tu-dong") {
    try {
      const r = await api(`/cong-viec/${encodeURIComponent(id)}/tu-dong-giao`, { method: "POST" });
      toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      await cvxLamMoi();
    } catch (e) { toast(e.message, true); }
    return;
  }
  if (ma === "giao") {
    let chon;
    try { chon = await cvxNguoiNhan(id); } catch (e) { toast(e.message, true); return; }
    const r = await hoiHop({
      tieu_de: v.nguoi_nhan ? "Chuyển việc cho người khác" : "Giao việc", phu: v.tieu_de,
      nut: v.nguoi_nhan ? "Chuyển" : "Giao",
      truong: [
        { name: "nguoi_nhan", label: "Người nhận", type: "select", value: v.nguoi_nhan || "",
          options: [{ value: "", label: "— Thu hồi, để Chưa phân công —" }].concat(chon) },
        { name: "ghi_chu", label: "Ghi chú bàn giao", maxlength: 500,
          placeholder: "Đã gọi một lần, khách hẹn chiều" },
      ] });
    if (!r) return;
    const than = r.nguoi_nhan ? { nguoi_nhan: r.nguoi_nhan } : { xoa_nguoi_nhan: true };
    if (r.ghi_chu) than.ghi_chu = r.ghi_chu;
    return cvxPut(id, than, r.nguoi_nhan ? "Đã giao — người nhận được báo." : "Đã thu hồi người nhận.");
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

/* Tạo việc — từ màn Công việc, hoặc từ một hội thoại (`ngu_canh` mang sẵn
 * hội thoại + khách). Phân công: tự nhận, chưa phân công, tự động, hay
 * một người cụ thể — hai lựa chọn sau chỉ hiện khi có `cong_viec.giao`. */
async function cvxTaoViec(ngu_canh = {}) {
  const giao = cvxCo("cong_viec.giao");
  let nguoi = [];
  if (giao) { try { nguoi = await cvxNguoiNhan(null); } catch { nguoi = []; } }
  const chon = [
    { value: "", label: "— Chưa phân công —" },
    { value: "__toi", label: "Tôi làm" },
  ].concat(giao ? [{ value: "__tu_dong", label: "Tự động: người đang trong ca, xoay vòng" }].concat(nguoi) : []);
  const r = await hoiHop({
    tieu_de: ngu_canh.ten_khach ? `Việc mới — ${ngu_canh.ten_khach}` : "Việc mới",
    phu: ngu_canh.conversation_id ? "Việc gắn với hội thoại đang mở — bấm vào việc là mở lại đúng hội thoại này." : "",
    nut: "Tạo việc",
    truong: [
      { name: "tieu_de", label: "Việc cần làm", required: true, maxlength: 200,
        placeholder: "Gọi lại chị Hoa xác nhận đơn" },
      { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 3, maxlength: 5000 },
      { name: "phan_cong", label: "Phân công", type: "select", value: giao ? "" : "__toi", options: chon },
      { name: "uu_tien", label: "Mức ưu tiên", type: "select", value: "thuong",
        options: ((cvx.dm && cvx.dm.uu_tien) || [{ ma: "thuong", nhan: "Thường" }])
          .map((u) => ({ value: u.ma, label: u.nhan })) },
      { name: "han", label: "Hạn", type: "date", hint: "để trống nếu không có" },
      { name: "ma_don", label: "Mã đơn liên quan", maxlength: 60, hint: "không bắt buộc",
        placeholder: "ĐH-…" },
    ],
  });
  if (!r || !r.tieu_de) return;
  const than = { tieu_de: r.tieu_de, mo_ta: r.mo_ta || "", uu_tien: r.uu_tien || "thuong",
                 han: cvxHan(r.han) };
  if (r.ma_don) than.ma_don = r.ma_don;
  if (ngu_canh.conversation_id) than.conversation_id = ngu_canh.conversation_id;
  if (ngu_canh.contact_id) than.contact_id = ngu_canh.contact_id;
  if (r.phan_cong === "__toi") than.nguoi_nhan = state.toiId;
  else if (r.phan_cong === "__tu_dong") than.giao_tu_dong = true;
  else if (r.phan_cong) than.nguoi_nhan = r.phan_cong;
  try {
    const kq = await api("/cong-viec", { method: "POST", body: JSON.stringify(than) });
    if (than.giao_tu_dong && !kq.nguoi_nhan) toast(`Đã tạo, nhưng chưa phân công được: ${kq.ly_do_khong_giao}`, true);
    else toast("Đã tạo việc.");
    if (cvx.el) { cvx.moId = kq.id; await cvxLamMoi(); }
    return kq.id;
  } catch (e) { toast(e.message, true); }
}

/* Mở ngữ cảnh của việc (mục 14.8). */
function cvxDiToiDon(ma) {
  state.orderFilter = "all";
  doiMan("donhang");
  if (!ma) return;
  setTimeout(() => {
    const dong = [...$$("#orders > *")].find((x) => x.textContent.includes(ma));
    if (dong) { dong.scrollIntoView({ behavior: "smooth", block: "center" }); dong.classList.add("is-chuong");
      setTimeout(() => dong.classList.remove("is-chuong"), 2400); }
  }, 900);
}

function cvxBatSuKienLienKet(o) {
  o.addEventListener("click", (e) => {
    const ht = e.target.closest("[data-cvx-ht]");
    if (ht) { state.openConv = ht.dataset.cvxHt; state.cuonToiChiTiet = true; doiMan("hoithoai"); return; }
    const kh = e.target.closest("[data-cvx-kh]");
    if (kh) { openCustomer(kh.dataset.cvxKh); return; }
    const don = e.target.closest("[data-cvx-don]");
    if (don) cvxDiToiDon(don.dataset.cvxDon);
  });
}

/* ---------------- gắn: Danh sách công việc ---------------- */

GAN_TAB["cv-danh-sach"] = (el) => {
  cvx.el = el;
  if (!cvxCo("cong_viec.doc")) {
    el.innerHTML = '<section class="panel"><p class="empty">Bạn không có quyền xem công việc.</p></section>';
    return;
  }
  const opt = (ds) => ds.map(([v, n]) => `<option value="${v}">${n}</option>`).join("");
  el.innerHTML = `
    <section class="panel">
      <h2 class="panel__head">Công việc
        <span class="panel__note">việc nội bộ cần người theo dõi — chuyển hội thoại cho người KHÔNG sinh việc</span>
        ${cvxCo("cong_viec.sua") ? '<button type="button" class="btn btn--sm btn--primary" id="cvxThem">Tạo việc</button>' : ""}</h2>
      <div class="filterbar cvx__loc" role="group" aria-label="Lọc công việc">
        <input type="search" id="cvxTim" class="cvx__tim" placeholder="Tìm tiêu đề, khách, mã đơn…" maxlength="100" aria-label="Tìm công việc">
        <select id="cvxTrangThai" aria-label="Trạng thái">${opt([["", "Mọi trạng thái"],
          ["moi", "Chờ xử lý"], ["dang_lam", "Đang thực hiện"], ["xong", "Hoàn thành"], ["huy", "Đã hủy"]])}</select>
        <select id="cvxUuTien" aria-label="Ưu tiên">${opt([["", "Mọi ưu tiên"], ["gap", "Gấp"],
          ["cao", "Cao"], ["thuong", "Thường"], ["thap", "Thấp"]])}</select>
        <select id="cvxNguon" aria-label="Nguồn">${opt([["", "Mọi nguồn"], ["nguoi", "Nhân viên tạo"],
          ["agent", "AI đề xuất"], ["tu_dong", "Tự động"], ["van_chuyen", "Vận chuyển"], ["don_hang", "Đơn hàng"]])}</select>
        <button type="button" class="chip" data-cvx-loc="cua_toi">Việc của tôi</button>
        <button type="button" class="chip" data-cvx-loc="chua_phan_cong">Chưa phân công</button>
        <button type="button" class="chip" data-cvx-loc="qua_han">Quá hạn</button>
      </div>
      <div id="cvxDs" class="rows"><p class="empty">Đang tải…</p></div>
    </section>
    <div id="cvxCt"></div>`;

  $("#cvxThem", el)?.addEventListener("click", () => cvxTaoViec());
  let hoan = null;
  $("#cvxTim", el).addEventListener("input", (e) => {
    clearTimeout(hoan);
    hoan = setTimeout(() => { cvx.loc.q = e.target.value.trim(); cvxLamMoi(); }, 300);
  });
  for (const [sel, k] of [["#cvxTrangThai", "trang_thai"], ["#cvxUuTien", "uu_tien"], ["#cvxNguon", "nguon"]]) {
    $(sel, el).addEventListener("change", (e) => { cvx.loc[k] = e.target.value; cvxLamMoi(); });
  }
  el.addEventListener("click", async (e) => {
    const loc = e.target.closest("[data-cvx-loc]");
    if (loc) {
      const k = loc.dataset.cvxLoc;
      cvx.loc[k] = !cvx.loc[k];
      loc.classList.toggle("is-on", cvx.loc[k]);
      cvxLamMoi();
      return;
    }
    const nhan = e.target.closest("[data-cvx-nhan]");
    if (nhan) {
      await cvxPut(nhan.dataset.cvxNhan, { nguoi_nhan: state.toiId, trang_thai: "dang_lam" }, "Bạn đã nhận việc này.");
      return;
    }
    const mo = e.target.closest("[data-cvx-mo]");
    if (mo) { await cvxTaiChiTiet(mo.dataset.cvxMo); return; }
    if (e.target.closest("[data-cvx-dong]")) {
      cvx.moId = null; cvx.chiTiet = null; cvxVeChiTiet();
      $$("#cvxDs .row", el).forEach((r) => r.classList.remove("is-on"));
      return;
    }
    const lam = e.target.closest("[data-cvx-lam]");
    if (lam) await cvxLam(lam.dataset.cvxLam);
  });
  cvxBatSuKienLienKet(el);
  el.addEventListener("tab:hien", () => cvxLamMoi());
  cvxLamMoi();
};

/* Vòng làm mới chung (10-vong-lam-moi) KHÔNG nạp tab đã gắn mô-đun — mô-đun
 * tự lo: làm mới khi tab đang hiện, và khi hộp xác nhận đơn của 08 vừa đổi
 * dữ liệu (nó gọi loadCongViec, phát `congviec:doi`). */
setInterval(() => {
  if (document.hidden) return;
  if (cvx.el && tabDangHien("cv-danh-sach")) cvxLamMoi();
  if (cvxCa.el && tabDangHien("cv-ca-truc")) cvxCaTai();
}, 20000);
document.addEventListener("congviec:doi", () => { if (cvx.el) cvxLamMoi(); });

/* Chuông "việc" và mọi lối khác mở thẳng chi tiết một việc. */
window.moCongViec = async (id) => {
  if (!cvxCo("cong_viec.doc")) return false;
  if (doiMan("cv-danh-sach") === false) return false;
  if (!cvx.el) return false;
  await cvxTaiChiTiet(id);
  return cvx.moId === id;
};

/* Nút "+ Tạo công việc" trong hội thoại (03-hoi-thoai.js vẽ lại khung mỗi
 * nhịp, nên bắt ở document). Gắn sẵn hội thoại + khách (mục 14.3). */
document.addEventListener("click", (e) => {
  if (!e.target.closest("#btn-tao-viec-ht")) return;
  const c = state.convDangMo;
  if (!c) return;
  cvxTaoViec({ conversation_id: c.id, contact_id: c.contact_id, ten_khach: c.customer_name });
});

/* ---------------- gắn: khối Công việc trong Tổng quan ca trực ---------------- */

const cvxCa = { el: null };

function cvxO(nhan, so, loc, mau) {
  return `<button type="button" class="readout__cell cvx__o" data-cvx-di="${loc}">
    <span class="readout__label">${esc(nhan)}</span>
    <span class="readout__line"><span class="readout__value">${so}</span></span>
    <span class="readout__bar"><span class="readout__fill readout__fill--${mau}" style="width:${so ? 100 : 0}%"></span></span>
  </button>`;
}

async function cvxCaTai() {
  const o = cvxCa.el;
  if (!o) return;
  if (!cvxCo("cong_viec.doc")) { o.innerHTML = ""; return; }
  const t = await cvxTaiDem();
  if (!t) { o.innerHTML = '<p class="empty">Không tải được tổng quan công việc.</p>'; return; }
  const d = t.dem;
  const giao = cvxCo("cong_viec.giao");
  const nv = t.nhan_vien;
  o.innerHTML = `<section class="panel">
    <h2 class="panel__head">Công việc
      <span class="panel__note">${t.tu_dong_duoc == null ? "trong phạm vi bạn thấy"
        : t.tu_dong_duoc ? `${t.tu_dong_duoc} người đang nhận được phân công tự động`
        : "LÚC NÀY không ai trong ca để phân công tự động — việc mới sẽ ở Chưa phân công"}</span></h2>
    <div class="readout">
      ${cvxO("Chưa phân công", d.chua_phan_cong, "chua_phan_cong", d.chua_phan_cong ? "assist" : "auto")}
      ${cvxO("Chờ xử lý", d.cho_xu_ly, "moi", "spend")}
      ${cvxO("Đang thực hiện", d.dang_thuc_hien, "dang_lam", "auto")}
      ${cvxO("Quá hạn", d.qua_han, "qua_han", d.qua_han ? "halt" : "auto")}
      ${cvxO("Hoàn thành hôm nay", d.xong_hom_nay, "xong", "auto")}
    </div>
    <div class="split">
      <div>
        <h3 class="cvx__ls-tieu">Việc chưa phân công</h3>
        <div class="rows">${t.chua_phan_cong.length ? t.chua_phan_cong.map((v) => `<div class="row">
          <span class="row__flag row__flag--${cvxCo_mau(v)}"></span>
          <div class="row__main"><b>${esc(v.tieu_de)}</b>
            <span class="row__sub">${esc(v.nhan_nguon)} · ${esc(cvxNhan(v.uu_tien, t.uu_tien))}${
              v.han ? " · hạn " + esc(hanDoc(v.han)) : ""}${v.khach_ten ? " · " + esc(v.khach_ten) : ""}</span></div>
          <div class="row__side"><span class="row__nut">
            ${cvxCo("cong_viec.sua") ? `<button type="button" class="btn btn--sm" data-cvx-ca-nhan="${esc(v.id)}">Nhận</button>` : ""}
            ${giao ? `<button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-tu-dong="${esc(v.id)}">Tự phân công</button>` : ""}
            <button type="button" class="btn btn--sm btn--ghost" data-cvx-ca-mo="${esc(v.id)}">Mở</button>
          </span></div></div>`).join("") : '<p class="empty">Không có việc nào chờ phân công.</p>'}</div>
      </div>
      ${nv ? `<div>
        <h3 class="cvx__ls-tieu">Nhân viên và việc đang giữ</h3>
        <div class="rows">${nv.length ? nv.map((n) => `<div class="row">
          <span class="row__flag row__flag--${n.trong_ca_that && n.san_sang ? "auto" : "assist"}"></span>
          <div class="row__main"><b>${esc(n.ten)}</b>
            <span class="row__sub">${n.trong_ca_that ? "đang trong ca" : n.co_lich ? "ngoài ca" : "chưa xếp ca"}${
              n.san_sang ? "" : " · tắt sẵn sàng"}</span></div>
          <div class="row__side"><span><span class="pill">${n.so_mo} việc mở</span>${
            n.so_qua_han ? ` <span class="pill pill--warn">${n.so_qua_han} quá hạn</span>` : ""}</span></div>
        </div>`).join("") : '<p class="empty">Chưa có nhân viên nào làm được công việc.</p>'}</div>
      </div>` : ""}
    </div>
  </section>`;
}

GAN_TAB["cv-ca-truc-viec"] = (el) => {
  cvxCa.el = el;
  el.addEventListener("click", async (e) => {
    const di = e.target.closest("[data-cvx-di]");
    if (di) {
      const k = di.dataset.cvxDi;
      cvx.loc = { trang_thai: "", uu_tien: "", nguon: "", q: "", cua_toi: false,
                  chua_phan_cong: k === "chua_phan_cong", qua_han: k === "qua_han" };
      if (k === "moi" || k === "dang_lam" || k === "xong") cvx.loc.trang_thai = k;
      doiMan("cv-danh-sach");
      if (cvx.el) {
        $("#cvxTrangThai", cvx.el).value = cvx.loc.trang_thai;
        $$("[data-cvx-loc]", cvx.el).forEach((c) => c.classList.toggle("is-on", !!cvx.loc[c.dataset.cvxLoc]));
        cvxLamMoi();
      }
      return;
    }
    const mo = e.target.closest("[data-cvx-ca-mo]");
    if (mo) { await window.moCongViec(mo.dataset.cvxCaMo); return; }
    const nhan = e.target.closest("[data-cvx-ca-nhan]");
    const tuDong = e.target.closest("[data-cvx-ca-tu-dong]");
    try {
      if (nhan) {
        await api(`/cong-viec/${encodeURIComponent(nhan.dataset.cvxCaNhan)}`, { method: "PUT",
          body: JSON.stringify({ nguoi_nhan: state.toiId, trang_thai: "dang_lam" }) });
        toast("Bạn đã nhận việc này.");
      } else if (tuDong) {
        const r = await api(`/cong-viec/${encodeURIComponent(tuDong.dataset.cvxCaTuDong)}/tu-dong-giao`, { method: "POST" });
        toast(r.nguoi_nhan ? `Đã giao cho ${r.nguoi_nhan_ten}.` : `Không phân công được: ${r.ly_do}`, !r.nguoi_nhan);
      } else return;
    } catch (err) { toast(err.message, true); }
    cvxCaTai();
  });
  el.addEventListener("tab:hien", () => cvxCaTai());
  cvxCaTai();
};
