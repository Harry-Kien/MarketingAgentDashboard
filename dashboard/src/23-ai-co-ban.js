/* ---------------- Cấu hình AI cơ bản: nhà cung cấp, khoá, model, thông báo AI ----------------
 *
 * Gắn qua `GAN_TAB['ai-co-ban-nha-cung-cap']`. Dùng chung bộ Lưu / Kiểm tra
 * / Bỏ-về-.env của 22-ket-noi-tich-hop.js (`knttGanSuKien`): thẻ AI chỉ là
 * một dịch vụ nữa (`ai`) với cách vẽ ô riêng.
 *
 * Công tắc bật/tắt AI và chế độ Gợi ý/Tự động KHÔNG ở đây — chúng thuộc
 * khung "Cấu hình cơ bản" của màn AI Agent.
 */

function aiTruong(d, khoa) {
  return d.the.truong.find((m) => m.khoa === khoa) || { khoa, nhan: khoa, hien: "", nguon: "trong" };
}

function aiChonModel(d, m) {
  const co = Object.values(d.model_theo_ho).some((ds) => ds.includes(m.hien));
  const nhom = Object.entries(d.model_theo_ho).map(([ho, ds]) =>
    `<optgroup label="${esc({ gemini: "Gemini", claude: "Claude", gpt: "OpenAI GPT" }[ho] || ho)}">${
      ds.map((x) => `<option value="${esc(x)}"${x === m.hien ? " selected" : ""}>${esc(x)}</option>`).join("")}</optgroup>`).join("");
  const nguon = { csdl: "lưu trên dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  return `<label class="field"><span>${esc(m.nhan)} <em class="hint">${esc(d.model_dung_cho[m.khoa] || "")}</em></span>
    <select data-kntt-khoa="${esc(m.khoa)}">${co ? "" : `<option value="${esc(m.hien)}" selected>${esc(m.hien || "—")}</option>`}${nhom}</select></label>
    <span class="row__sub">${esc(nguon)}${m.nguon === "csdl"
      ? ` <button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="${esc(m.khoa)}">Bỏ, dùng .env</button>` : ""}</span>`;
}

/* Chỉ hiện ô khoá/endpoint của nhà cung cấp ĐANG CHỌN. Hiện cả ba là mời
 * người ta dán khoá Anthropic khi đang chạy Gemini: lưu đúng, kiểm đúng,
 * agent vẫn im — không có gì nổ để mà biết nhìn đâu. Ô bị ẩn được xoá chữ
 * để khoá cũ không lén đi theo lần Lưu sau. */
function aiHienTheoNhaCungCap(the, d) {
  const sel = the.querySelector('[data-kntt-khoa="LLM_PROVIDER"]');
  if (!sel) return;
  const ncc = d.nha_cung_cap.find((n) => n.ma === sel.value) || {};
  $$("[data-ai-khoa-cua]", the).forEach((dong) => {
    const an = dong.dataset.aiKhoaCua !== ncc.khoa && !(dong.dataset.aiKhoaCua === "OPENAI_BASE_URL" && ncc.endpoint);
    dong.hidden = an;
    if (an) $$("input[type=password]", dong).forEach((o) => { o.value = ""; });
  });
  const note = the.querySelector("[data-ai-ghichu]");
  if (note) note.textContent = ncc.ghi_chu || "";
}

function aiTheNhaCungCap(d) {
  const p = aiTruong(d, "LLM_PROVIDER");
  const the = d.the;
  const chon = `<label class="field"><span>Nhà cung cấp</span><select data-kntt-khoa="LLM_PROVIDER">${
    d.nha_cung_cap.map((n) => `<option value="${esc(n.ma)}"${n.ma === p.hien ? " selected" : ""}${
      n.ho_tro ? "" : " disabled"}>${esc(n.ten)}${n.ho_tro ? "" : " (chưa hỗ trợ)"}</option>`).join("")}</select></label>
    <p class="row__sub" data-ai-ghichu></p>`;
  const khoa = ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL"].map((k) =>
    `<div data-ai-khoa-cua="${k}">${knttO(aiTruong(d, k))}</div>`).join("");
  const canh = d.canh_bao.length
    ? `<div class="kntt-canhbao">${d.canh_bao.map((c) => `<p class="row__sub"><b>⚠ ${esc(c)}</b></p>`).join("")}</div>` : "";
  return `<section class="kntt-the" data-kntt-dv="ai">
    <h3 class="kntt-the__dau">${knttCham(the.trang_thai, the.nhan_trang_thai)} <b>Nhà cung cấp AI</b>
      <span class="tag tag--${{ thanh_cong: "auto", loi: "halt", chua_kiem_tra: "assist" }[the.trang_thai] || "plain"}">${
        esc(the.nhan_trang_thai)}</span></h3>
    ${the.thieu.length ? `<p class="row__sub"><b>Còn thiếu:</b> ${the.thieu.map(esc).join(", ")}</p>` : ""}
    ${canh}
    <div class="kntt-truong">${chon}${khoa}
      ${["MODEL_CHAT", "MODEL_HARD", "MODEL_CHEAP"].map((k) => aiChonModel(d, aiTruong(d, k))).join("")}</div>
    <div class="rowbtns">
      <button type="button" class="btn btn--sm" data-kntt-kiem="ai">Kiểm tra kết nối</button>
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="ai">Lưu</button>
      <span class="row__sub" data-kntt-kq="ai" aria-live="polite"></span>
    </div>
    ${knttKetQuaKiem(the.kiem)}
    <p class="row__sub">Đổi nhà cung cấp, khoá hay model có hiệu lực từ tin nhắn kế tiếp, không cần khởi động lại.</p>
  </section>`;
}

function aiTheThongBao(d) {
  const tb = d.thong_bao_ai;
  const bat = tb.the.truong.find((m) => m.khoa === "THONG_BAO_AI") || { hien: "bat" };
  const nd = tb.the.truong.find((m) => m.khoa === "TIN_THONG_BAO_AI") || { hien: tb.mac_dinh, nguon: "env" };
  return `<section class="kntt-the" data-kntt-dv="thong_bao_ai">
    <h3 class="kntt-the__dau"><b>Thông báo minh bạch AI</b>
      <span class="tag ${bat.hien === "tat" ? "tag--halt" : "tag--auto"}">${bat.hien === "tat" ? "Đang tắt" : "Đang bật"}</span></h3>
    <p class="row__sub">Báo khách đang nói với trợ lý AI và cách gặp nhân viên (NĐ 356/2025). ${esc(tb.chong_lap)}</p>
    <label class="field"><span>Gửi thông báo</span><select data-kntt-khoa="THONG_BAO_AI">
      <option value="bat"${bat.hien !== "tat" ? " selected" : ""}>Bật</option>
      <option value="tat"${bat.hien === "tat" ? " selected" : ""}>Tắt (bảng kiểm sẵn sàng sẽ cảnh báo)</option></select></label>
    <label class="field"><span>Nội dung <em class="hint">{ten} = tên thương hiệu. Phải có chữ "AI", một cụm gọi người
      trong ngoặc kép mà hệ thống nhận ra (vd "gặp nhân viên"), và nhắc dữ liệu da là nhạy cảm.</em></span>
      <textarea rows="4" maxlength="600" data-kntt-khoa="TIN_THONG_BAO_AI">${esc(nd.hien)}</textarea></label>
    <p class="row__sub">Khách sẽ đọc: “${esc(tb.xem_truoc)}”</p>
    <div class="rowbtns">
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="thong_bao_ai">Lưu</button>
      ${nd.nguon === "csdl" ? '<button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="TIN_THONG_BAO_AI">Về câu mặc định</button>' : ""}
      <span class="row__sub" data-kntt-kq="thong_bao_ai" aria-live="polite"></span>
    </div>
  </section>`;
}

async function ganAiCoBan(goc) {
  if (!goc) return;
  let duLieu = null;
  const napLai = async () => {
    try {
      duLieu = await api("/ket-noi/ai");
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được cấu hình AI: ${esc(e.message)}</p>`;
      return;
    }
    /* Bọc trong `.panel` như mọi khối khác của màn (UX-17-04): trước đây
       tiêu đề và hai thẻ nằm trơ trên nền trang, trông như một màn khác. */
    goc.innerHTML = `<section class="panel ai-ncc">
      <h2 class="panel__head">Nhà cung cấp và model
        <span class="panel__note">${duLieu.vault_san_sang ? "khoá mã hoá trong CSDL, chỉ hiện 4 ký tự cuối"
          : "vault chưa cấu hình — chỉ xem được"}</span></h2>
      ${aiTheNhaCungCap(duLieu)}
      ${aiTheThongBao(duLieu)}
    </section>`;
    aiHienTheoNhaCungCap(goc.querySelector('[data-kntt-dv="ai"]'), duLieu);
  };
  knttGanSuKien(goc, napLai);
  goc.addEventListener("change", (e) => {
    if (e.target.closest('[data-kntt-khoa="LLM_PROVIDER"]') && duLieu) {
      aiHienTheoNhaCungCap(goc.querySelector('[data-kntt-dv="ai"]'), duLieu);
    }
  });
  await napLai();
}

window.GAN_TAB["ai-co-ban-nha-cung-cap"] = (el) => ganAiCoBan(el);
