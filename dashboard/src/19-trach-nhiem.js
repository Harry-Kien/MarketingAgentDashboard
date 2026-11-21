/* ---------------- Trách nhiệm trong hội thoại ----------------
 *
 * Mọi việc trong một hội thoại phải quy được về người (hoặc AI) đã làm nó
 * (rà soát 20.11.2026). Trước bản này màn hội thoại chỉ hiện "Nhân viên"
 * không tên, "tin cậy 0.77" và "có nguồn tham chiếu"; không ai duyệt, không
 * hồ sơ agent nào, không lưới nào — dù phần lớn dữ liệu ấy nằm sẵn trong CSDL.
 *
 * Tệp này giữ phần VẼ; `03-hoi-thoai.js` gọi vào. Tách riêng vì 03 đã gần
 * trần 1000 dòng, và vì đây là một miền riêng: ai làm gì, vì sao.
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

/* Tên người viết tin. Nhân viên KHÔNG tên là thông tin vô dụng khi có hai
 * người trực cùng ca; AI thì kèm hồ sơ agent khi kênh có hồ sơ riêng.
 * Trả "" khi không có gì cụ thể hơn — nhãn chung theo vai nằm ở chỗ gọi
 * (`03-hoi-thoai.js`), một bảng duy nhất cho cả bốn vai. */
function tenTacGia(m, nguoiGuiNhom) {
  const tg = m.tac_gia || {};
  if (nguoiGuiNhom) return nguoiGuiNhom;
  if (m.role === "staff" && tg.ten) return `Nhân viên ${tg.ten}`;
  if (m.role === "agent" && tg.ten && tg.ten !== "Mặc định") return `AI · ${tg.ten}`;
  return "";
}

/* "Sửa bởi X", "Duyệt bởi Y lúc …" — hai việc của người trên một câu AI. */
function chipTrachNhiem(m) {
  const tg = m.tac_gia || {};
  const chip = [];
  if (tg.sua_boi) {
    chip.push(`<span class="tag tag--plain" title="Bản AI viết vẫn xem lại được bằng nút 'xem bản AI'">
      Sửa bởi ${esc(tg.sua_boi)}${tg.sua_luc ? " lúc " + esc(gioTin(tg.sua_luc)) : ""}</span>`);
  }
  if (tg.duyet_boi) {
    chip.push(`<span class="tag tag--auto">Duyệt bởi ${esc(tg.duyet_boi)}${
      tg.duyet_luc ? " lúc " + esc(gioTin(tg.duyet_luc)) : ""}</span>`);
  }
  return chip.join("");
}

function nutViSao(m) {
  if (m.role !== "agent" || !m.dau_vet_ai) return "";
  const mo = state.viSao && state.viSao.has(String(m.id));
  return `<button type="button" class="msg__goc-nut" data-vi-sao="${esc(m.id)}"
    aria-expanded="${mo ? "true" : "false"}">${mo ? "ẩn vì sao" : "Vì sao?"}</button>`;
}

/* Bảng "Vì sao AI nói câu này" — đọc từ `messages.dau_vet_ai` (0053). */
function veViSao(m) {
  if (!(state.viSao && state.viSao.has(String(m.id))) || !m.dau_vet_ai) return "";
  const dv = m.dau_vet_ai;
  const tc = dv.tin_cay || {};
  const duoiNguong = tc.nguong != null && tc.diem != null && tc.diem < tc.nguong;
  const cheDo = dv.che_do || {};
  const dong = (tieu, chi, mau = "") => `<div class="row"><span class="row__flag ${mau ? "row__flag--" + mau : ""}"></span>
    <span class="row__body"><span class="row__title">${tieu}</span>
    ${chi ? `<span class="row__sub">${chi}</span>` : ""}</span></div>`;
  const luoi = dv.luoi
    ? dong(`Lưới bắt: ${esc(dv.luoi.nhan || dv.luoi.ma)}`,
      esc((dv.chuyen_nguoi && dv.chuyen_nguoi.ly_do) || ""),
      (typeof NHAN_LUOI_MAU !== "undefined" && NHAN_LUOI_MAU[dv.luoi.ma]) || "assist")
    : dong("Không lưới nào bắt", dv.chuyen_nguoi && dv.chuyen_nguoi.co
      ? esc("Chuyển người: " + (dv.chuyen_nguoi.ly_do || "")) : "", "auto");
  const congCu = (dv.cong_cu || []).length
    ? dv.cong_cu.map((c, i) => `<details class="row">
        <summary class="row__body"><span class="row__title">${i + 1}. ${esc(c.ten)}</span>
        <span class="row__sub">${c.vong != null ? "vòng " + esc(c.vong) : ""}${c.ms != null ? " · " + esc(c.ms) + " ms" : ""}</span></summary>
        <pre class="pre">${esc(JSON.stringify({ tham_so: c.tham_so, ket_qua: c.ket_qua }, null, 2))}</pre>
      </details>`).join("")
      + (dv.cong_cu_bo_bot ? `<p class="hint">… và ${esc(dv.cong_cu_bo_bot)} lần gọi nữa không lưu chi tiết.</p>` : "")
    : '<p class="hint">Không gọi công cụ nào.</p>';
  const triThuc = (dv.tri_thuc || []).length
    ? dv.tri_thuc.map((t) => `<li>${esc(t.title || "(không tên)")}${
        t.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(t.version)}</span>` : ""}</li>`).join("")
    : (dv.nguon || []).map((n) => `<li>${esc(n)}</li>`).join("");
  return `<div class="visao">
    ${dong(`Hồ sơ agent: <b>${esc((dv.ho_so && dv.ho_so.ten) || "Mặc định")}</b>`,
      esc(`Chế độ chung: ${cheDo.chung === "auto" ? "AI tự gửi" : "AI soạn, người duyệt"}`
        + (cheDo.duyet_rieng ? " · hội thoại này bắt duyệt trước khi gửi" : "")
        + (cheDo.tu_gui ? " · đã TỰ GỬI" : " · lưu NHÁP chờ duyệt")))}
    ${dong(`Độ tin cậy ${pct(tc.diem)} — ngưỡng ${pct(tc.nguong)}`,
      tc.co_can_cu ? "có căn cứ" : "KHÔNG có căn cứ", duoiNguong ? "assist" : "auto")}
    ${luoi}
    <h4 class="visao__dau">Công cụ đã gọi</h4>${congCu}
    <h4 class="visao__dau">Tài liệu đã đọc</h4>
    ${triThuc ? `<ul class="visao__ds">${triThuc}</ul>` : '<p class="hint">Không trích tài liệu nào.</p>'}
    ${(dv.goi_ky_nang || []).length ? dong("Gói kỹ năng kích hoạt", esc(dv.goi_ky_nang.join(" · "))) : ""}
    <p class="hint">${esc(dv.model || "")} · ${usd(dv.cost_usd)} · ${esc(dv.latency_ms || 0)} ms · ${esc(dv.so_vong || 0)} vòng${
      (dv.da_rut_gon || []).length ? " · dấu vết đã rút gọn vì quá dài" : ""}</p>
  </div>`;
}

/* Người đang giữ hội thoại, nói bằng TÊN. "Đồng nghiệp đang giữ" không trả
 * lời được câu người trực cần hỏi tiếp: hỏi ai? */
function veNguoiGiu(c, laCuaToi) {
  if (c.mode !== "human") {
    return c.assigned_to_ten
      ? `<span class="tag tag--plain" title="Người theo dõi hội thoại AI đang xử lý">Theo dõi: ${esc(c.assigned_to_ten)}</span>`
      : "";
  }
  if (!c.assigned_to) return '<span class="tag tag--halt">Chưa ai nhận</span>';
  const ten = laCuaToi ? "Bạn" : (c.assigned_to_ten || "Đồng nghiệp");
  return `<span class="tag tag--assist">${esc(ten)} đang giữ${
    c.assigned_team_ten ? " · nhóm " + esc(c.assigned_team_ten) : ""}</span>`;
}

/* Lịch sử bàn giao — tải khi MỞ, tải lại khi version hội thoại đổi. Không
 * gọi mỗi 6 giây cho một khung không ai mở. */
function veLichSuPhanCong(c) {
  const id = String(c.id);
  const mo = state.moLichSu === id;
  const bo = state.lichSuPC && state.lichSuPC[id];
  let than = '<p class="hint">Đang tải…</p>';
  if (bo && bo.loi) than = `<p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  else if (bo && bo.items) {
    than = bo.items.length ? bo.items.slice().reverse().map((m) => `<div class="lichsu__dong lichsu__dong--${esc(m.loai)}">
        <b>${esc(m.tieu_de)}</b>
        <span class="msg__meta">${esc(gioTin(m.luc))}${m.nguoi_lam ? " · bởi " + esc(m.nguoi_lam) : ""}${
          m.ket_thuc ? " · kết thúc " + esc(gioTin(m.ket_thuc)) : ""}</span>
        ${m.chi_tiet ? `<p>${esc(m.chi_tiet)}</p>` : ""}
      </div>`).join("") : '<p class="hint">Chưa có lần bàn giao nào.</p>';
  }
  if (mo && (!bo || bo.version !== c.version)) taiLichSuPhanCong(c);
  return `<details class="lichsu" data-lichsu="${esc(id)}" ${mo ? "open" : ""}>
    <summary>Lịch sử bàn giao</summary>${mo ? than : ""}
  </details>`;
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
    // Hỏng thì NÓI trong khung, không toast: vòng 6 giây sẽ bắn toast mãi.
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
  const nut = ev.target.closest("[data-vi-sao]");
  if (nut) {
    state.viSao = state.viSao || new Set();
    const mid = nut.dataset.viSao;
    if (state.viSao.has(mid)) state.viSao.delete(mid); else state.viSao.add(mid);
    if (state.openConv) loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-giao") && state.convDangMo) giaoHoiThoai(state.convDangMo);
});

/* Mở/đóng lịch sử: nhớ theo hội thoại, vì panel dựng lại mỗi 6 giây. */
document.addEventListener("toggle", (ev) => {
  const el = ev.target;
  if (!(el instanceof HTMLElement) || !el.matches("[data-lichsu]")) return;
  const id = el.dataset.lichsu;
  if (el.open && state.moLichSu !== id) {
    state.moLichSu = id;
    if (state.openConv) loadThread(state.openConv);
  } else if (!el.open && state.moLichSu === id) {
    state.moLichSu = null;
  }
}, true);

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
