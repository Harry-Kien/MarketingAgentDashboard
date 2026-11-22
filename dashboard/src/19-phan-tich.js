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
  $("#ptExcel").href = `/api/bao-cao/nhan-vien.xlsx?tu=${f.tu.value}&den=${f.den.value}`;
  let d;
  try {
    await _ptBoLoc(f);
    d = await api(`/phan-tich?${_ptQuery(f)}`);
  } catch (e) { toast(e.message, true); return; }

  const h = d.hoi_thoai, k = d.khach, s = d.sla;
  const phDau = s.phan_hoi_dau;
  /* ---- Hiệu quả chăm sóc khách hàng ---- */
  $("#ptCskh").innerHTML = [
    cell("Hội thoại có hoạt động", h.hoat_dong, `${h.moi} mới`, null, "auto"),
    cell("Tỷ lệ xử lý", _ptTiLe(h.ty_le_xu_ly), `${h.hoi_thoai_giai_quyet} được giải quyết`,
         h.ty_le_xu_ly, "auto"),
    cell("Phản hồi đầu (trung vị)", _giay(phDau.tat_ca.trung_vi_giay), `${phDau.tat_ca.so} lượt · AI và nhân viên`, null, "plain"),
    cell("Thời gian giải quyết (trung vị)", _giay(s.thoi_gian_giai_quyet.trung_vi_giay),
         `${s.thoi_gian_giai_quyet.so} lượt`, null, "plain"),
    cell("Mở lại", h.mo_lai, "lượt", h.giai_quyet ? h.mo_lai / h.giai_quyet : null, "assist"),
    cell("Khách có nhắn", k.tong, `${k.moi} mới · ${k.quay_lai} quay lại`, null, "auto"),
    cell("Đang mở (bây giờ)", h.dang_mo, "hội thoại", null, "plain"),
  ].join("");

  /* ---- Hiệu quả AI Agent ---- */
  const at = d.ai_tong;
  $("#ptAiTong").innerHTML = [
    cell("Hội thoại AI xử lý", at.hoi_thoai, `${at.tu_giai_quyet} tự giải quyết`, null, "auto"),
    cell("Tỷ lệ chuyển giao nhân viên", _ptTiLe(at.ty_le_chuyen_giao), `${at.can_nguoi} cần người`,
         at.ty_le_chuyen_giao, "assist"),
    cell("Hiệu quả tự động hoá", _ptTiLe(at.tu_dong_hoa), "AI tự giải quyết / có hoạt động",
         at.tu_dong_hoa, "auto"),
    cell("Chi phí AI trong khoảng", usd(at.chi_phi_usd), "tổng", null, "spend"),
  ].join("");
  /* KHÔNG hiện "độ tin cậy": model tự chấm con số ấy, hiện thành phần trăm
     là mời người đọc tin nó như xác suất đúng. Báo tỉ lệ có / không căn cứ. */
  $("#ptAi").innerHTML = `<thead><tr><th>Hồ sơ</th><th>Hội thoại</th><th>Tự giải quyết</th>
    <th>Cần người</th><th>Chưa kết cục</th><th>Thành công</th><th>Chuyển giao</th>
    <th>AI tự chuyển</th><th>Có căn cứ</th><th>Không căn cứ</th><th>Chi phí</th></tr></thead><tbody>${
    d.ai.length ? d.ai.map((a) => `<tr><td>${esc(a.ten)}</td><td>${a.hoi_thoai}</td>
      <td>${a.tu_giai_quyet}</td><td>${a.can_nguoi}</td><td>${a.dang_do}</td>
      <td>${_ptTiLe(a.ty_le_thanh_cong)}</td><td>${_ptTiLe(a.ty_le_can_nguoi)}</td>
      <td>${a.ai_tu_chuyen}</td><td>${_ptTiLe(a.ty_le_co_can_cu)}</td>
      <td class="${a.ty_le_khong_can_cu ? "so--xau" : ""}">${_ptTiLe(a.ty_le_khong_can_cu)}</td>
      <td>${usd(a.chi_phi_usd)}</td></tr>`).join("")
    : '<tr><td colspan="11" class="empty">Không có tin AI nào trong khoảng này.</td></tr>'}</tbody>`;

  /* ---- Hiệu suất nhân viên ----
     Cột CSAT đã gỡ khỏi bảng: chủ dự án ẩn CSAT khỏi giao diện (phiếu việc
     20.11.2026) và câu hỏi chấm điểm mặc định TẮT — một cột luôn "—" là
     cột người ta học cách bỏ qua. API vẫn trả csat_tb/csat_so. */
  $("#ptNhanVien").innerHTML = `<thead><tr>
    <th>Nhân viên</th><th>Hội thoại được giao</th><th>Tin đã gửi</th>
    <th>Phản hồi đầu (trung vị)</th><th>p90</th><th>Chưa phản hồi</th>
    <th>Đơn</th><th>Trễ SLA</th></tr></thead><tbody>${d.nhan_vien.length
    ? d.nhan_vien.map((n) => `<tr>
      <td>${esc(n.ho_ten)}</td><td>${n.hoi_thoai}</td><td>${n.tin_gui}</td>
      <td>${_giay(n.phan_hoi_trung_vi_giay)}</td><td>${_giay(n.phan_hoi_p90_giay)}</td>
      <td class="${n.chua_phan_hoi ? "so--xau" : ""}">${n.chua_phan_hoi}</td>
      <td>${n.don}</td><td class="${n.tre_sla ? "so--xau" : ""}">${n.tre_sla}</td></tr>`).join("")
    : '<tr><td colspan="8" class="empty">Không có nhân viên nào trong phạm vi.</td></tr>'}</tbody>`;

  /* ---- Chỉ số SLA ---- */
  /* Mỗi mục tiêu có đồng hồ riêng (Cấu hình chung → SLA & Giờ làm việc):
     nói rõ con số nào đo theo cách nào, không gộp thành một chữ "24/7". */
  const cdm = d.che_do_muc_tieu || {};
  const cd = (m) => (cdm[m] === "gio_lam_viec" ? "giờ làm việc" : "24/7");
  $("#ptSlaNote").textContent = "tỷ lệ đáp ứng tính trên mục tiêu có hạn · đồng hồ: phản hồi đầu "
    + cd("phan_hoi_dau") + ", sau chuyển giao " + cd("phan_hoi_sau_chuyen_giao")
    + ", giải quyết " + cd("giai_quyet") + " · \"quá hạn\" là ảnh chụp bây giờ";
  const mcg = s.chuyen_giao || { dung_han: 0, tre_han: 0, ty_le_dung_han: null, canh_bao: 0,
    qua_han: 0, dang_cho: 0, khong_han: 0, thoi_gian: { so: 0 }, nhan_vien: [] };
  $("#ptSla").innerHTML = [
    cell("Đáp ứng phản hồi đầu", _ptTiLe(s.ty_le_dung_han_dau), `${s.dau_dat} đạt · ${s.dau_tre} trễ`,
         s.ty_le_dung_han_dau, s.ty_le_dung_han_dau != null && s.ty_le_dung_han_dau < 0.9 ? "halt" : "auto"),
    cell("Đáp ứng giải quyết", _ptTiLe(s.ty_le_dung_han_xong), `${s.xong_dat} đạt · ${s.xong_tre} trễ`,
         s.ty_le_dung_han_xong, s.ty_le_dung_han_xong != null && s.ty_le_dung_han_xong < 0.9 ? "halt" : "auto"),
    cell("Đáp ứng sau chuyển giao", _ptTiLe(mcg.ty_le_dung_han),
         `${mcg.dung_han} đạt · ${mcg.tre_han} trễ · ${mcg.dang_cho} đang chờ`,
         mcg.ty_le_dung_han, mcg.ty_le_dung_han != null && mcg.ty_le_dung_han < 0.9 ? "halt" : "auto"),
    cell("Số vi phạm", s.vi_pham_tat_ca ?? s.vi_pham,
         `${s.dau_canh_bao + s.xong_canh_bao + mcg.canh_bao} cảnh báo sớm`, null,
         (s.vi_pham_tat_ca ?? s.vi_pham) ? "halt" : "auto"),
    cell("Đang quá hạn (bây giờ)", s.qua_han,
         `${s.qua_han_dau} chưa phản hồi · ${s.qua_han_xong} chưa xong · ${mcg.qua_han} chờ nhân viên sau chuyển giao`,
         null, (s.qua_han || mcg.qua_han) ? "halt" : "auto"),
  ].join("");

  const dongTg = (ten, r, them = "") => `<tr><td>${esc(ten)}</td><td>${r.so}</td><td>${_giay(r.tb_giay)}</td>
    <td>${_giay(r.trung_vi_giay)}</td><td>${r.ty_le_dung_han !== undefined ? _ptTiLe(r.ty_le_dung_han) : "—"}</td>
    <td>${them}</td></tr>`;
  const cg = s.phan_hoi_sau_chuyen_giao;
  const tgVai = s.thoi_gian_giai_quyet.theo_vai || {};
  $("#ptThoiGian").innerHTML = `<thead><tr><th>Thước đo</th><th>Số lượt</th><th>Trung bình</th>
    <th>Trung vị</th><th>Đúng hạn</th><th>Ghi chú</th></tr></thead><tbody>
    ${dongTg("Phản hồi đầu — AI", phDau.theo_vai.agent, `${phDau.theo_vai.agent.tre_han} trễ`)}
    ${phDau.ho_so.map((r) => dongTg("   AI · " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${dongTg("Phản hồi đầu — nhân viên", phDau.theo_vai.staff, `${phDau.theo_vai.staff.tre_han} trễ`)}
    ${phDau.nhan_vien.map((r) => dongTg("   " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${phDau.theo_vai.khong_ro.so ? dongTg("Phản hồi đầu — không rõ (trước 20.11.2026)", phDau.theo_vai.khong_ro) : ""}
    ${dongTg("Phản hồi sau chuyển giao", cg, cg.chua_phan_hoi ? `${cg.chua_phan_hoi} chưa ai nhắn` : "")}
    ${cg.nhan_vien.map((r) => dongTg("   " + r.ten, r)).join("")}
    ${dongTg("Mục tiêu sau chuyển giao (theo lượt)", { ...mcg.thoi_gian, ty_le_dung_han: mcg.ty_le_dung_han },
       `${mcg.tre_han} trễ · ${mcg.khong_han} không đặt hạn`)}
    ${mcg.nhan_vien.map((r) => dongTg("   " + r.ten, r, `${r.tre_han} trễ`)).join("")}
    ${dongTg("Thời gian giải quyết", s.thoi_gian_giai_quyet)}
    ${tgVai.agent ? dongTg("   AI tự lo", tgVai.agent, `${tgVai.agent.tre_han} trễ`) : ""}
    ${tgVai.staff ? dongTg("   Có nhân viên", tgVai.staff, `${tgVai.staff.tre_han} trễ`) : ""}
    </tbody>`;

  $("#ptNgay").innerHTML = `<thead><tr><th>Ngày</th><th>Mới</th><th>Giải quyết</th>
    <th>Có AI</th><th>Chuyển giao</th><th>Đáp ứng phản hồi đầu</th><th>Vi phạm SLA</th>
    <th>Chi phí AI</th></tr></thead><tbody>${
    d.theo_ngay.map((r) => `<tr><td>${esc(r.ngay)}</td><td>${r.moi}</td><td>${r.giai_quyet}</td>
      <td>${r.ai}</td><td>${_ptTiLe(r.ty_le_can_nguoi)}</td><td>${_ptTiLe(r.ty_le_dung_han_dau)}</td>
      <td class="${r.vi_pham ? "so--xau" : ""}">${r.vi_pham}</td><td>${usd(r.chi_phi_ai_usd)}</td></tr>`).join("")}</tbody>`;

  /* ---- Tin nhắn ---- */
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
 * Nút "Đổi" nằm cạnh mức ưu tiên trong panel "Chi tiết" của hội thoại
 * (mục 6.8 — không còn ở thanh thông tin). Luật hạn SLA
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
