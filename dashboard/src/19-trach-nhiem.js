/* ---------------- Trách nhiệm trong hội thoại ----------------
 *
 * Mọi việc trong một hội thoại phải quy được về người (hoặc AI) đã làm nó
 * (rà soát 20.11.2026). Trước bản này màn hội thoại chỉ hiện "Nhân viên"
 * không tên; không ai duyệt, không hồ sơ agent nào, không lưới nào — dù phần
 * lớn dữ liệu ấy nằm sẵn trong CSDL.
 *
 * QUY ƯỚC HIỂN THỊ (chủ dự án, 21.11.2026):
 *   · Dưới mỗi tin MỘT dòng: Thời gian · Người gửi · Trạng thái.
 *   · Thông tin kỹ thuật (độ tin cậy, nguồn, thời gian xử lý, model, chi
 *     phí) KHÔNG hiện mặc định — chỉ trong "Chi tiết" / "Xem căn cứ".
 *   · Độ tin cậy KHÔNG BAO GIỜ hiện thành phần trăm: "87%" đọc như xác suất
 *     câu trả lời đúng, mà nó chỉ là điểm khớp tài liệu. Người trực thấy
 *     "Có căn cứ" / "Thiếu căn cứ"; con số thô chỉ ở phần kỹ thuật.
 *   · Lịch sử bàn giao nằm trong panel "Chi tiết" của hội thoại, không
 *     chiếm chỗ thường trực ở đầu hội thoại.
 *
 * Tệp này giữ phần VẼ; `03-hoi-thoai.js` gọi vào. Tách riêng vì 03 đã gần
 * trần 1000 dòng.
 */

/* Giờ của MỘT tin: hôm nay thì hh:mm, ngày khác thì kèm ngày. Chỉ hh:mm là
 * người đọc lại hội thoại ba ngày tuổi tưởng mọi tin cùng một buổi — và
 * "khách nhắn 9:05, mình trả lời 9:07" thật ra là cách nhau hai ngày. */
function gioTin(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const nay = new Date();
  const cungNgay = d.getFullYear() === nay.getFullYear()
    && d.getMonth() === nay.getMonth() && d.getDate() === nay.getDate();
  const gio = hhmm(iso);
  if (cungNgay) return gio;
  const ngay = d.toLocaleDateString("vi-VN", {
    day: "2-digit", month: "2-digit",
    ...(d.getFullYear() !== nay.getFullYear() ? { year: "numeric" } : {}),
  });
  return `${ngay} ${gio}`;
}

/* Người gửi, cụ thể nhất có thể. Trả "" khi không có gì cụ thể hơn — nhãn
 * chung theo vai nằm ở `const who` trong `03-hoi-thoai.js`, một bảng duy
 * nhất cho cả bốn vai. Nhân viên KHÔNG tên là thông tin vô dụng khi hai
 * người trực cùng ca. Trong nhóm: tên NGƯỜI GỬI tin, không phải tên nhóm. */
function tenTacGia(m, nguoiGuiNhom, tenKhach) {
  const tg = m.tac_gia || {};
  if (nguoiGuiNhom) return nguoiGuiNhom;
  if (m.role === "staff" && tg.ten) return `Nhân viên (${tg.ten})`;
  if (m.role === "customer" && tenKhach) return `Khách hàng (${tenKhach})`;
  return "";
}

/* Trạng thái lấy NGUYÊN từ `delivery_status` (dữ liệu nền tảng trả về) —
 * không suy đoán. Tin khách vào (`received`) không có trạng thái gửi. */
const TRANG_THAI_TIN = {
  sent: "Đã gửi", delivered: "Đã nhận", read: "Đã đọc",
  draft: "Bản nháp", queued: "Đang gửi", sending: "Đang gửi",
  failed: "Gửi lỗi, đang thử lại", dead: "Không gửi được", cancelled: "Đã huỷ",
};

function trangThaiTin(m) {
  if (m.role === "customer" || m.delivery_status === "received") return "";
  return TRANG_THAI_TIN[m.delivery_status] || "";
}

/* Ai đã sửa / duyệt — một dòng chữ nhỏ cạnh dòng meta, không phải chip to:
 * thông tin cần truy được, không cần đập vào mắt mỗi lần đọc hội thoại. */
function ghiChuNguoiXuLy(m) {
  const tg = m.tac_gia || {};
  const phan = [];
  if (tg.sua_boi) phan.push(`đã sửa bởi ${tg.sua_boi}`);
  else if (m.sua_boi) phan.push(`đã sửa bởi ${m.sua_boi}`);
  if (tg.duyet_boi) phan.push(`duyệt bởi ${tg.duyet_boi}`);
  return phan.length ? `<span class="msg__ghi">${esc(phan.join(" · "))}</span>` : "";
}

function nhanCanCu(m) {
  if (m.grounded === true) return "Có căn cứ";
  if (m.grounded === false) return "Thiếu căn cứ";
  return "";
}

/* "Xem căn cứ" trên BẢN NHÁP AI (chế độ gợi ý) — người duyệt cần nó để quyết
 * gửi hay sửa. Tin khác: "Chi tiết" (cùng bảng, kèm thông tin kỹ thuật). */
function nutChiTietTin(m, draft) {
  const coGi = m.role === "agent" || m.tac_gia?.sua_boi || m.tac_gia?.duyet_boi || m.sua_boi;
  if (!coGi) return "";
  const mo = state.chiTietTin && state.chiTietTin.has(String(m.id));
  const nhan = draft ? "Xem căn cứ" : "Chi tiết";
  const can = draft && nhanCanCu(m)
    ? `<span class="tag tag--${m.grounded ? "auto" : "assist"}">${esc(nhanCanCu(m))}</span>` : "";
  return `${can}<button type="button" class="msg__goc-nut" data-chi-tiet-tin="${esc(m.id)}"
    aria-expanded="${mo ? "true" : "false"}">${mo ? "Ẩn" : nhan}</button>`;
}

function dongCT(tieu, chi) {
  return `<div class="ctt__dong"><b>${tieu}</b>${chi ? `<span>${chi}</span>` : ""}</div>`;
}

/* Bảng chi tiết của MỘT tin. Ba phần căn cứ — tài liệu (kèm trích đoạn),
 * dữ liệu nghiệp vụ công cụ trả về, quy tắc và lớp lưới đã áp — rồi phần kỹ
 * thuật. KHÔNG có suy luận thô của model: hệ thống không lưu nó, và nó
 * không phải căn cứ. Tham số công cụ đã che số điện thoại/email và ẩn họ
 * tên, địa chỉ ở máy chủ (`agent/core/dau_vet_ai.py`). */
function veChiTietTin(m, draft) {
  if (!(state.chiTietTin && state.chiTietTin.has(String(m.id)))) return "";
  const dv = m.dau_vet_ai || null;
  const tg = m.tac_gia || {};
  let canCu = "";
  if (m.role === "agent") {
    const triThuc = dv && (dv.tri_thuc || []).length
      ? dv.tri_thuc.map((t) => `<li><b>${esc(t.title || "(không tên)")}</b>${
          t.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(t.version)}</span>` : ""}
          ${t.trich ? `<blockquote class="ctt__trich">${esc(t.trich)}</blockquote>` : ""}</li>`).join("")
      : (m.sources || []).map((n) => `<li><b>${esc(n)}</b></li>`).join("");
    const congCu = dv && (dv.cong_cu || []).length
      ? dv.cong_cu.map((c) => `<li><b>${esc(c.ten)}</b>
          <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></li>`).join("")
        + (dv.cong_cu_bo_bot ? `<li class="hint">… và ${esc(dv.cong_cu_bo_bot)} lần gọi nữa không lưu chi tiết.</li>` : "")
      : "";
    const che = (dv && dv.che_do) || {};
    const quyTac = dv ? [
      dongCT("Hồ sơ agent", esc((dv.ho_so && dv.ho_so.ten) || "Mặc định")),
      dongCT("Chế độ", esc((che.chung === "auto" ? "AI tự gửi" : "AI soạn, người duyệt")
        + (che.duyet_rieng ? " · hội thoại này bắt duyệt trước khi gửi" : ""))),
      dv.luoi ? dongCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma)) : dongCT("Lớp lưới", "không lưới nào bắt"),
      dv.chuyen_nguoi && dv.chuyen_nguoi.co ? dongCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : "",
      (dv.goi_ky_nang || []).length ? dongCT("Gói kỹ năng", esc(dv.goi_ky_nang.join(" · "))) : "",
    ].join("") : '<p class="hint">Tin AI này soạn trước khi hệ thống lưu dấu vết — chỉ còn tên tài liệu.</p>';
    canCu = `
      ${dongCT("Căn cứ", esc(nhanCanCu(m) || "—"))}
      <h4 class="ctt__dau">Tài liệu đã dùng</h4>
      ${triThuc ? `<ul class="ctt__ds">${triThuc}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
      <h4 class="ctt__dau">Dữ liệu nghiệp vụ công cụ trả về</h4>
      ${congCu ? `<ul class="ctt__ds">${congCu}</ul>` : '<p class="hint">Không tra dữ liệu nghiệp vụ nào.</p>'}
      <h4 class="ctt__dau">Quy tắc đã áp</h4>${quyTac}`;
  }
  const tc = dv && dv.tin_cay;
  const kyThuat = m.role === "agent" ? [
    m.confidence != null ? dongCT("Điểm khớp tài liệu", esc(Number(m.confidence).toFixed(2)
      + (tc && tc.nguong != null ? ` (ngưỡng chuyển người ${Number(tc.nguong).toFixed(2)})` : ""))) : "",
    (dv && dv.model) || m.model ? dongCT("Model", esc((dv && dv.model) || m.model)) : "",
    m.latency_ms ? dongCT("Thời gian xử lý", esc(m.latency_ms + " ms")) : "",
    m.cost_usd != null || m.cost != null ? dongCT("Chi phí", esc(usd(m.cost_usd ?? m.cost))) : "",
  ].join("") : "";
  const nguoi = [
    tg.sua_boi ? dongCT("Sửa bởi", esc(tg.sua_boi + (tg.sua_luc ? " lúc " + gioTin(tg.sua_luc) : ""))) : "",
    tg.duyet_boi ? dongCT("Duyệt bởi", esc(tg.duyet_boi + (tg.duyet_luc ? " lúc " + gioTin(tg.duyet_luc) : ""))) : "",
  ].join("");
  return `<div class="ctt">${canCu}
    ${nguoi ? `<h4 class="ctt__dau">Người xử lý</h4>${nguoi}` : ""}
    ${kyThuat && !draft ? `<h4 class="ctt__dau">Kỹ thuật</h4>${kyThuat}` : ""}
    ${kyThuat && draft ? `<details class="ctt__kt"><summary>Kỹ thuật</summary>${kyThuat}</details>` : ""}
  </div>`;
}

/* ---------------- Chi tiết hội thoại ----------------
 * Người đang giữ, nhóm, và lịch sử bàn giao — trong MỘT panel mở bằng nút
 * "Chi tiết" ở đầu hội thoại. Tải lịch sử khi MỞ, tải lại khi version đổi;
 * không gọi mỗi 6 giây cho một panel không ai mở. */
function veChiTietHoiThoai(c, laCuaToi) {
  const id = String(c.id);
  if (state.moChiTietHT !== id) return "";
  const bo = state.lichSuPC && state.lichSuPC[id];
  if (!bo || bo.version !== c.version) taiLichSuPhanCong(c);
  let lichSu = '<p class="hint">Đang tải…</p>';
  if (bo && bo.loi) lichSu = `<p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  else if (bo && bo.items) {
    lichSu = bo.items.length ? bo.items.slice().reverse().map((m) => `<div class="lichsu__dong lichsu__dong--${esc(m.loai)}">
        <b>${esc(m.tieu_de)}</b>
        <span class="msg__meta">${esc(gioTin(m.luc))}${m.nguoi_lam ? " · bởi " + esc(m.nguoi_lam) : ""}${
          m.ket_thuc ? " · kết thúc " + esc(gioTin(m.ket_thuc)) : ""}</span>
        ${m.chi_tiet ? `<p>${esc(m.chi_tiet)}</p>` : ""}
      </div>`).join("") : '<p class="hint">Chưa có lần bàn giao nào.</p>';
  }
  let giu;
  if (c.mode !== "human") giu = c.assigned_to_ten ? `AI đang xử lý · theo dõi: ${esc(c.assigned_to_ten)}` : "AI đang xử lý";
  else if (!c.assigned_to) giu = "Chưa ai nhận";
  else giu = `${esc(laCuaToi ? "Bạn" : (c.assigned_to_ten || "Đồng nghiệp"))}${
    c.assigned_team_ten ? " · nhóm " + esc(c.assigned_team_ten) : ""}`;
  /* Ưu tiên, chế độ AI, Version, trạng thái, kênh — dời từ thanh thông tin
   * xuống đây (mục 6.1, 6.2, 6.7, 6.8): cần khi tra cứu, không cần mỗi lần
   * đọc hội thoại. SLA KHÔNG có ở đây (mục 15.7) — cảnh báo SLA đi qua
   * chuông. "Đổi" ưu tiên đòi `hoi_thoai.nhan` như máy chủ (uu_tien.py). */
  const doiUuTien = state.toiQuyen && state.toiQuyen.has("hoi_thoai.nhan") && c.state !== "resolved"
    ? ` <button type="button" class="btn btn--sm btn--ghost" data-doi-uu-tien="${esc(c.id)}"
        data-uu-tien="${esc(c.priority || "normal")}" data-version="${c.version || ""}">Đổi</button>` : "";
  const cheDo = { auto: "AI tự gửi", assist: "AI soạn, người duyệt", human: "Nhân viên xử lý" }[c.mode] || c.mode || "—";
  return `<section class="lichsu" aria-label="Chi tiết hội thoại">
    ${dongCT("Người đang giữ", giu)}
    ${dongCT("Trạng thái", esc(c.state === "resolved" ? "Đã giải quyết" : (SIGNAL_LABEL[c.status] || c.status || "—")))}
    ${dongCT("Chế độ AI", esc(cheDo))}
    <div class="ctt__dong"><b>Ưu tiên</b><span>${esc(UU_TIEN_NHAN[c.priority] || c.priority || "thường")}</span>${doiUuTien}</div>
    ${dongCT("Kênh", `${esc(c.account_name || "—")} · ${esc(CHANNEL_LABEL[c.account_channel] || c.account_channel || "")}`)}
    ${dongCT("Version", esc(c.version || 1))}
    <h4 class="ctt__dau">Lịch sử bàn giao</h4>${lichSu}
  </section>`;
}

async function taiLichSuPhanCong(c) {
  const id = String(c.id);
  state.lichSuPC = state.lichSuPC || {};
  if (state.lichSuPC[id] && state.lichSuPC[id].dangTai) return;
  state.lichSuPC[id] = { ...(state.lichSuPC[id] || {}), dangTai: true, version: c.version };
  try {
    const r = await api(`/inbox/conversations/${id}/lich-su-phan-cong`);
    state.lichSuPC[id] = { items: r.items || [], version: c.version };
  } catch (e) {
    // Hỏng thì NÓI trong panel, không toast: vòng 6 giây sẽ bắn toast mãi.
    state.lichSuPC[id] = { loi: e.message, version: c.version };
  }
  if (state.openConv === id) loadThread(id);
}

/* "Giao cho…" — chọn người (và nhóm) trong danh sách máy chủ trả về, theo
 * ĐÚNG luật `can_assign`. Nhân viên thường không có quyền giao người khác
 * thì không thấy nút: một danh sách bấm vào chỉ nhận 403 là bẫy. */
async function giaoHoiThoai(c) {
  let ds;
  try {
    ds = await api(`/inbox/conversations/${c.id}/nguoi-nhan-duoc`);
  } catch (e) { toast(e.message, true); return; }
  if (!ds.co_the_giao_khac) {
    toast("Giao cho người khác cần quyền quản lý kênh. Bạn vẫn tự nhận được.", true);
    return;
  }
  const d = await hoiHop({
    tieu_de: "Giao hội thoại",
    phu: "Người nhận phải là thành viên kênh; chọn nhóm thì người nhận phải thuộc nhóm đó.",
    truong: [
      { name: "assignee_id", label: "Giao cho", type: "select", required: true,
        value: c.assigned_to || "",
        options: ds.nguoi.map((n) => ({ value: n.id,
          label: `${n.ten}${n.dang_giu ? ` (đang giữ ${n.dang_giu})` : ""}` })) },
      { name: "team_id", label: "Nhóm", type: "select", value: c.assigned_team_id || "",
        options: [{ value: "", label: "— Không theo nhóm —" },
          ...ds.nhom.map((t) => ({ value: t.id, label: t.ten }))] },
      { name: "reason", label: "Lý do", required: true, maxlength: 500,
        value: "Bàn giao cho người phụ trách" },
    ],
    nut: "Giao",
  });
  if (!d) return;
  try {
    await api(`/inbox/conversations/${c.id}/takeover`, {
      method: "POST",
      body: JSON.stringify({
        assignee_id: d.assignee_id, team_id: d.team_id || null,
        expected_version: c.version || 1, reason: d.reason,
      }),
    });
    const ten = (ds.nguoi.find((n) => String(n.id) === String(d.assignee_id)) || {}).ten;
    toast(`Đã giao cho ${ten || "người nhận"}.`);
    if (state.lichSuPC) delete state.lichSuPC[String(c.id)];
    refresh();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", (ev) => {
  const nut = ev.target.closest("[data-chi-tiet-tin]");
  if (nut) {
    state.chiTietTin = state.chiTietTin || new Set();
    const mid = nut.dataset.chiTietTin;
    if (state.chiTietTin.has(mid)) state.chiTietTin.delete(mid); else state.chiTietTin.add(mid);
    if (state.openConv) loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-chitiet-ht") && state.openConv) {
    const id = String(state.openConv);
    state.moChiTietHT = state.moChiTietHT === id ? null : id;
    loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-giao") && state.convDangMo) {
    state.moHanhDong = null;   // nút nằm trong menu "⋯" — đóng nó lại
    giaoHoiThoai(state.convDangMo);
  }
});

/* ---------------- Bộ lọc hộp thư ----------------
 * Kênh, người giữ (tôi / chưa ai nhận / một người), riêng hay nhóm, quá hạn
 * SLA. API đã nhận kênh và người giữ từ lâu mà màn hình không dùng: người
 * trực muốn xem "việc của tôi" phải cuộn cả danh sách. */
state.convLoc = state.convLoc || { kenh: "", giu: "", loai: "", sla: false };

function chuoiLocHopThu() {
  const l = state.convLoc;
  let q = "";
  if (l.kenh) q += `&account_id=${encodeURIComponent(l.kenh)}`;
  if (l.giu === "chua_giao") q += "&chua_giao=true";
  else if (l.giu === "toi" && state.toiId) q += `&assignee_id=${encodeURIComponent(state.toiId)}`;
  else if (l.giu && l.giu !== "toi") q += `&assignee_id=${encodeURIComponent(l.giu)}`;
  if (l.loai) q += `&loai=${encodeURIComponent(l.loai)}`;
  if (l.sla) q += "&qua_han_sla=true";
  return q;
}

function dangLocHopThu() {
  const l = state.convLoc;
  return !!(l.kenh || l.giu || l.loai || l.sla);
}

/* Danh sách kênh và người cho hai ô chọn — nạp MỘT lần mỗi phiên trang.
 * Hỏng thì hai ô chỉ còn lựa chọn cố định; lần vào màn sau thử lại. */
async function napBoLocHopThu() {
  if (state.boLocDaNap || !$("#loc-kenh")) return;
  state.boLocDaNap = true;
  let d;
  try { d = await api("/inbox/bo-loc"); } catch (e) {
    state.boLocDaNap = false;
    console.warn("Không nạp được bộ lọc hộp thư", e);
    return;
  }
  $("#loc-kenh").innerHTML = '<option value="">Mọi kênh</option>' + (d.kenh || []).map((k) =>
    `<option value="${esc(k.id)}">${esc(k.ten)} · ${esc(CHANNEL_LABEL[k.channel] || k.channel)}</option>`).join("");
  $("#loc-giu").innerHTML = `<option value="">Mọi người giữ</option>
    <option value="toi">Của tôi</option><option value="chua_giao">Chưa ai nhận</option>`
    + (d.nguoi || []).filter((n) => String(n.id) !== String(state.toiId || "")).map((n) =>
      `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
  $("#loc-kenh").value = state.convLoc.kenh;
  $("#loc-giu").value = state.convLoc.giu;
}

/* Gắn TỪNG ô bằng id viết đủ: `tests/test_nut_chet.py` tìm "#loc-…" trong
 * app.js để biết ô có người nghe — ghép chuỗi id là ô trông như nút chết. */
function ganLoc(o, khoa) {
  o?.addEventListener("change", (ev) => {
    state.convLoc[khoa] = ev.target.value;
    loadConversations();
  });
}
ganLoc($("#loc-kenh"), "kenh");
ganLoc($("#loc-giu"), "giu");
ganLoc($("#loc-loai"), "loai");

$("#loc-sla")?.addEventListener("click", (ev) => {
  state.convLoc.sla = !state.convLoc.sla;
  ev.currentTarget.classList.toggle("is-on", state.convLoc.sla);
  ev.currentTarget.setAttribute("aria-pressed", state.convLoc.sla ? "true" : "false");
  loadConversations();
});
