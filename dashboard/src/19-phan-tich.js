/* ==================== Phân tích ====================
 *
 * Định nghĩa từng con số ở agent/api/phan_tich.py và docs/phan-tich.md —
 * đọc trước khi dùng nó để đánh giá một người hay một hồ sơ AI. Mọi số đếm
 * theo SỰ KIỆN trong khoảng ngày; ô nào là ảnh chụp "bây giờ" thì nhãn nói
 * vậy. Không nạp theo vòng 6 giây: tám câu truy vấn trên cả khoảng ngày là
 * việc nặng, và con số theo ngày không đổi từng giây. */

const UU_TIEN_NHAN = { low: "thấp", normal: "thường", high: "cao", urgent: "gấp" };
const VAI_NHAN = { customer: "Khách", agent: "AI", staff: "Nhân viên", system: "Hệ thống" };

function _ptQuery(f) {
  const q = new URLSearchParams({ tu: f.tu.value, den: f.den.value });
  for (const k of ["kenh", "account_id", "nhan_vien", "ho_so"]) {
    if (f[k].value) q.set(k, f[k].value);
  }
  return q.toString();
}

async function _ptBoLoc(f) {
  if (state.ptBoLoc) return;
  const b = await api("/phan-tich/bo-loc");
  const tat = '<option value="">Tất cả</option>';
  ganLuaChon(f.kenh, tat + b.kenh.map((k) =>
    `<option value="${esc(k)}">${esc(NEN_TANG_LABEL[String(k).toLowerCase()] || KENH_TEN[k] || k)}</option>`).join(""));
  ganLuaChon(f.account_id, tat + b.tai_khoan.map((t) =>
    `<option value="${esc(t.id)}">${esc(t.ten)} (${esc(t.kenh)})</option>`).join(""));
  ganLuaChon(f.nhan_vien, tat + b.nhan_vien.map((n) =>
    `<option value="${esc(n.id)}">${esc(n.ten)}${n.khoa ? " (đã khoá)" : ""}</option>`).join(""));
  ganLuaChon(f.ho_so, tat + b.ho_so.map((h) =>
    `<option value="${esc(h.id)}">${esc(h.ten)}${h.bat === false ? " (đang tắt)" : ""}</option>`).join(""));
  state.ptBoLoc = true;
}

function _ptTiLe(x) { return x == null ? "—" : pct(x); }

async function loadPhanTich() {
  const f = $("#ptForm");
  if (!f) return;
  if (!f.tu.value) {
    const nay = new Date();
    f.den.value = _ngayVN(nay);
    f.tu.value = _ngayVN(new Date(nay.getTime() - 6 * 86400000));
  }
  state.ptDaTai = true;
  let d;
  try {
    await _ptBoLoc(f);
    d = await api(`/phan-tich?${_ptQuery(f)}`);
  } catch (e) { toast(e.message, true); return; }

  const h = d.hoi_thoai;
  $("#ptHoiThoai").innerHTML = [
    cell("Mới", h.moi, "hội thoại", null, "auto"),
    cell("Có hoạt động", h.hoat_dong, "hội thoại", null, "auto"),
    cell("Lượt giải quyết", h.giai_quyet, `${h.tu_giai_quyet} tự đóng`, null, "auto"),
    cell("Mở lại", h.mo_lai, "lượt", h.giai_quyet ? h.mo_lai / h.giai_quyet : null, "assist"),
    cell("AI chuyển người", h.chuyen_nguoi, "hội thoại", null, "halt"),
    cell("Người tiếp quản", h.tiep_quan, "hội thoại", null, "assist"),
    cell("Đang mở (bây giờ)", h.dang_mo, "hội thoại", null, "plain"),
  ].join("");

  $("#ptNgay").innerHTML = `<thead><tr><th>Ngày</th><th>Mới</th><th>Giải quyết</th>
    <th>Có AI</th><th>Cần người</th><th>Tỉ lệ cần người</th></tr></thead><tbody>${
    d.theo_ngay.map((r) => `<tr><td>${esc(r.ngay)}</td><td>${r.moi}</td><td>${r.giai_quyet}</td>
      <td>${r.ai}</td><td>${r.can_nguoi}</td><td>${_ptTiLe(r.ty_le_can_nguoi)}</td></tr>`).join("")}</tbody>`;

  const k = d.khach;
  $("#ptKhach").innerHTML = [
    cell("Khách có nhắn", k.tong, "người", null, "auto"),
    cell("Khách mới", k.moi, "người", k.tong ? k.moi / k.tong : null, "auto"),
    cell("Khách quay lại", k.quay_lai, "người", k.tong ? k.quay_lai / k.tong : null, "assist"),
  ].join("");

  $("#ptAi").innerHTML = `<thead><tr><th>Hồ sơ</th><th>Hội thoại</th><th>Tự giải quyết</th>
    <th>Cần người</th><th>Chưa kết cục</th><th>Thành công</th><th>Tỉ lệ cần người</th>
    <th>AI tự chuyển</th><th>Tin cậy TB</th><th>Có căn cứ</th><th>Chi phí</th></tr></thead><tbody>${
    d.ai.length ? d.ai.map((a) => `<tr><td>${esc(a.ten)}</td><td>${a.hoi_thoai}</td>
      <td>${a.tu_giai_quyet}</td><td>${a.can_nguoi}</td><td>${a.dang_do}</td>
      <td>${_ptTiLe(a.ty_le_thanh_cong)}</td><td>${_ptTiLe(a.ty_le_can_nguoi)}</td>
      <td>${a.ai_tu_chuyen}</td><td>${a.tin_cay_tb == null ? "—" : a.tin_cay_tb.toFixed(2)}</td>
      <td>${_ptTiLe(a.ty_le_co_can_cu)}</td><td>${usd(a.chi_phi_usd)}</td></tr>`).join("")
    : '<tr><td colspan="11" class="empty">Không có tin AI nào trong khoảng này.</td></tr>'}</tbody>`;

  const s = d.sla;
  $("#ptSla").innerHTML = [
    cell("Phản hồi đầu đúng hạn", _ptTiLe(s.ty_le_dung_han_dau), `${s.dau_dat} đạt · ${s.dau_tre} trễ`,
         s.ty_le_dung_han_dau, s.ty_le_dung_han_dau != null && s.ty_le_dung_han_dau < 0.9 ? "halt" : "auto"),
    cell("Giải quyết đúng hạn", _ptTiLe(s.ty_le_dung_han_xong), `${s.xong_dat} đạt · ${s.xong_tre} trễ`,
         s.ty_le_dung_han_xong, s.ty_le_dung_han_xong != null && s.ty_le_dung_han_xong < 0.9 ? "halt" : "auto"),
    cell("Cảnh báo 50%", s.dau_canh_bao + s.xong_canh_bao,
         `${s.dau_canh_bao} phản hồi · ${s.xong_canh_bao} giải quyết`, null, "assist"),
    cell("Đang quá hạn (bây giờ)", s.qua_han,
         `${s.qua_han_dau} chưa phản hồi · ${s.qua_han_xong} chưa xong`, null, s.qua_han ? "halt" : "auto"),
  ].join("");

  const ph = s.phan_hoi_dau;
  const dongPh = (ten, r) => `<tr><td>${esc(ten)}</td><td>${r.so}</td><td>${_giay(r.tb_giay)}</td>
    <td>${_giay(r.trung_vi_giay)}</td><td>${_ptTiLe(r.ty_le_dung_han)}</td>
    <td class="${r.tre_han ? "so--xau" : ""}">${r.tre_han}</td></tr>`;
  $("#ptPhanHoi").innerHTML = `<thead><tr><th>Ai trả lời</th><th>Số lượt</th><th>Trung bình</th>
    <th>Trung vị</th><th>Đúng hạn</th><th>Trễ</th></tr></thead><tbody>
    ${dongPh("AI — tất cả hồ sơ", ph.theo_vai.agent)}
    ${ph.ho_so.map((r) => dongPh("  AI · " + r.ten, r)).join("")}
    ${dongPh("Nhân viên — tất cả", ph.theo_vai.staff)}
    ${ph.nhan_vien.map((r) => dongPh("  " + r.ten, r)).join("")}
    ${ph.theo_vai.khong_ro.so ? dongPh("Không rõ (trước 20.11.2026)", ph.theo_vai.khong_ro) : ""}
    </tbody>`;

  $("#ptNhanVien").innerHTML = `<thead><tr>
    <th>Nhân viên</th><th>Hội thoại được giao</th><th>Tin đã gửi</th>
    <th>Phản hồi đầu (trung vị)</th><th>p90</th><th>Chưa phản hồi</th>
    <th>Đơn</th><th>Trễ SLA</th><th>CSAT</th></tr></thead><tbody>${d.nhan_vien.length
    ? d.nhan_vien.map((n) => `<tr>
      <td>${esc(n.ho_ten)}</td><td>${n.hoi_thoai}</td><td>${n.tin_gui}</td>
      <td>${_giay(n.phan_hoi_trung_vi_giay)}</td><td>${_giay(n.phan_hoi_p90_giay)}</td>
      <td class="${n.chua_phan_hoi ? "so--xau" : ""}">${n.chua_phan_hoi}</td>
      <td>${n.don}</td><td class="${n.tre_sla ? "so--xau" : ""}">${n.tre_sla}</td>
      <td>${n.csat_so ? `${n.csat_tb} <span class="msg__meta">(${n.csat_so})</span>` : "—"}</td></tr>`).join("")
    : '<tr><td colspan="9" class="empty">Không có nhân viên nào trong phạm vi.</td></tr>'}</tbody>`;

  $("#ptTin").innerHTML = `<thead><tr><th>Nền tảng</th><th>Vai</th><th>Nhận</th>
    <th>Đã gửi</th><th>Gửi lỗi</th><th>Chưa gửi</th></tr></thead><tbody>${d.tin_nhan.length
    ? d.tin_nhan.map((t) => `<tr><td>${esc(NEN_TANG_LABEL[String(t.kenh || "").toLowerCase()] || KENH_TEN[t.kenh] || t.kenh)}</td>
      <td>${esc(VAI_NHAN[t.vai] || t.vai)}</td><td>${t.nhan}</td><td>${t.gui}</td>
      <td class="${t.loi ? "so--xau" : ""}">${t.loi}</td><td>${t.chua_gui}</td></tr>`).join("")
    : '<tr><td colspan="6" class="empty">Không có tin nào trong khoảng này.</td></tr>'}</tbody>`;
}

$("#ptForm")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  loadPhanTich();
});

/* ---------------- Đổi ưu tiên hội thoại ----------------
 *
 * Nút "Đổi" nằm cạnh mức ưu tiên ở thanh trạng thái hội thoại. Luật hạn SLA
 * (chỉ rút ngắn, không kéo dài) ở agent/api/uu_tien.py — hộp thoại nói luật
 * ấy ra để người bấm không tưởng hạ ưu tiên là được thêm giờ. */
document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-doi-uu-tien]");
  if (!b) return;
  const cid = b.dataset.doiUuTien;
  const d = await hoiHop({
    tieu_de: "Đổi mức ưu tiên",
    phu: "Nâng ưu tiên rút hạn SLA đang chạy (tính từ bây giờ, không trễ hơn hạn cũ). "
       + "Hạ ưu tiên KHÔNG kéo dài hạn của lượt này — mức mới áp dụng khi hội thoại mở lại.",
    truong: [
      { name: "uu_tien", label: "Mức mới", type: "select", value: b.dataset.uuTien,
        options: Object.entries(UU_TIEN_NHAN).map(([value, label]) => ({ value, label })) },
      { name: "ly_do", label: "Lý do", type: "textarea", required: true, maxlength: 500,
        placeholder: "vd khách khiếu nại, khách sỉ cần gấp…" },
    ],
    nut: "Đổi",
  });
  if (!d) return;
  try {
    const r = await api(`/conversations/${cid}/uu-tien`, {
      method: "PUT",
      body: JSON.stringify({ uu_tien: d.uu_tien, ly_do: d.ly_do,
                             version: b.dataset.version ? Number(b.dataset.version) : null }),
    });
    const rut = r.han_dau_moi !== r.han_dau_cu || r.han_xong_moi !== r.han_xong_cu;
    toast(`Đã đổi sang mức ${UU_TIEN_NHAN[r.uu_tien]}.${rut ? " Hạn SLA đã được rút ngắn." : " Hạn SLA của lượt này giữ nguyên."}`);
    if (state.openConv === cid) await loadThread(cid);
  } catch (e) { toast(e.message, true); }
});
