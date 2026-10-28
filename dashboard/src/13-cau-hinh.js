/* ---------------- cấu hình agent ---------------- */

/* Ô nhập dựng theo `kieu` do máy chủ khai, không đoán từ giá trị.
 * Đoán từ giá trị thì `confidence_floor = 1` (số nguyên) sẽ ra ô checkbox,
 * và người vận hành mất luôn thanh trượt. */
function oNhapCauHinh(m) {
  const id = `ch-${m.khoa}`;
  // `aria-label`: nhãn của ô nằm ở cột trái cùng dòng, không phải <label>
  // bọc ô — trình đọc màn hình và bộ kiểm tự động thấy một ô không tên.
  if (m.kieu === "bool") {
    return `<label class="switch"><input type="checkbox" id="${id}" aria-label="${esc(m.nhan)}"
      data-ch="${m.khoa}" data-kieu="bool" ${m.gia_tri ? "checked" : ""}>
      <span>${m.gia_tri ? "đang bật" : "đang tắt"}</span></label>`;
  }
  if (m.kieu === "chon") {
    return `<select id="${id}" aria-label="${esc(m.nhan)}" data-ch="${m.khoa}" data-kieu="chon">${
      m.chon.map((c) => `<option value="${esc(c)}"${
        c === m.gia_tri ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  return `<input type="number" id="${id}" aria-label="${esc(m.nhan)}" data-ch="${m.khoa}" data-kieu="so"
    min="${m.min}" max="${m.max}" step="${m.buoc}" value="${m.gia_tri}">
    ${m.don_vi ? `<span class="row__sub">${esc(m.don_vi)}</span>` : ""}`;
}

async function loadCauHinh() {
  const d = await api("/cau-hinh");
  const lech = d.muc.filter((m) => m.lech_mac_dinh).length;
  $("#c-cauhinh").textContent = lech ? `${lech} lệch` : "";

  $("#cauhinh-ds").innerHTML = d.muc.map((m) => `<div class="row">
      <span class="row__flag ${m.lech_mac_dinh ? "row__flag--halt" : "row__flag--auto"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.nhan)}
          ${m.lech_mac_dinh
            ? `<b class="pill">khác mặc định (${esc(String(m.mac_dinh))})</b>`
            : ""}</span>
        <span class="row__sub">${esc(m.y_nghia)}</span>
        <span class="row__sub"><em>Lưu ý:</em> ${esc(m.tat_thi)}</span>
      </span>
      <span class="row__side">${oNhapCauHinh(m)}</span>
    </div>`).join("");

  await loadLichSuCauHinh();
}

/* JSON thô trong nhật ký là thứ LẬP TRÌNH VIÊN đọc được, không phải người
 * trực ca. `{"mode":"auto","enabled":"True","zalo_account_id":null,...}` dài
 * 200 ký tự và chôn mất thứ duy nhất đáng nhìn: cái gì vừa đổi.
 *
 * Chỉ hiện những khoá NGƯỜI chỉnh được, bỏ phần còn lại. */
const NHAN_CAU_HINH = {
  enabled: "Công tắc agent",
  mode: "Chế độ trả lời",
  confidence_floor: "Ngưỡng tin cậy",
  max_cost_per_conversation: "Trần mỗi hội thoại",
  tran_chi_phi_ngay_usd: "Trần mỗi ngày",
};

function doiThayCauHinh(ct) {
  if (!ct || typeof ct !== "object") return "đặt lại về mặc định";
  const phan = Object.entries(NHAN_CAU_HINH)
    .filter(([k]) => ct[k] !== undefined && ct[k] !== null)
    .map(([k, nhan]) => `${nhan} = ${ct[k]}`);
  return phan.length ? phan.join(" · ") : "đặt lại về mặc định";
}

async function loadLichSuCauHinh() {
  const ls = await api("/cau-hinh/lich-su?limit=12");
  $("#cauhinh-lichsu").innerHTML = ls.length
    /* `.row` là lưới `3px minmax(0,1fr) auto`. Cột đầu LÀ dải màu — thiếu
       `.row__flag` thì `.row__body` rơi vào cột 3px và nội dung biến mất
       hoàn toàn. Nhìn ra là một danh sách toàn dòng trống. */
    ? ls.map((x) => `<div class="row">
        <span class="row__flag row__flag--auto"></span>
        <span class="row__body">
          <span class="row__title">${esc(x.boi || "?")}</span>
          <span class="row__sub">${esc(doiThayCauHinh(x.chi_tiet))}</span>
        </span>
        <span class="row__side"><span class="row__time">${clock(x.luc)}</span></span>
      </div>`).join("")
    : '<p class="empty">Chưa có thay đổi nào được ghi.</p>';
}

/* Gửi ngay khi đổi, không có nút Lưu riêng.
 * Nút Lưu riêng nghĩa là có một trạng thái "đã sửa nhưng chưa lưu" hiện
 * trên màn hình — và người vận hành đóng tab ở đúng trạng thái đó sẽ tin
 * là mình đã đổi. Gửi ngay thì thứ nhìn thấy luôn là thứ đang chạy. */
document.addEventListener("change", async (e) => {
  const el = e.target.closest("[data-ch]");
  if (!el) return;
  const kieu = el.dataset.kieu;
  const gt = kieu === "bool" ? el.checked
           : kieu === "so" ? Number(el.value)
           : el.value;
  try {
    await api("/runtime", {
      method: "POST",
      body: JSON.stringify({ [el.dataset.ch]: gt }),
    });
    toast("Đã lưu — có hiệu lực từ tin nhắn kế tiếp");
    await loadCauHinh();
  } catch (err) {
    toast(err.message, true);
    await loadCauHinh();
  }
});

$("#cauhinh-macdinh")?.addEventListener("click", async () => {
  if (!confirm("Quay về mặc định trong .env?\n\nMọi thiết lập đã lưu sẽ bị xoá."))
    return;
  try {
    await api("/cau-hinh/mac-dinh", { method: "POST" });
    toast("Đã quay về mặc định");
    await loadCauHinh();
  } catch (err) { toast(err.message, true); }
});


/* ---------------- phòng thử agent ---------------- */
// Phiên sống ở máy chủ (RAM); ở đây chỉ giữ id, lượt đã hiện và kỳ vọng
// của câu gợi ý vừa bấm. KHÔNG đưa vào vòng refresh() 6 giây: mỗi lượt
// là một lời gọi model, và người dùng cần đọc kết quả yên ổn.
state.phongThu = { phien: null, luot: [] };
state.phongThuDaTai = false;
let phongThuKyVong = null;

const NHAN_LUOI_MAU = {
  tran_hoi_thoai: "halt", tran_ngay: "halt", injection: "halt", tin_cay_thap: "assist",
  bat_buoc_chuyen: "halt", hua_khong_goi: "assist", chan_doan_y_te: "halt",
  cong_cu_chuyen_nguoi: "assist", cong_cu_yeu_cau: "assist", het_vong: "assist",
};

async function loadPhongThu() {
  state.phongThuDaTai = true;
  try {
    if (!state.phongThu.phien) {
      const p = await api("/phong-thu/phien", { method: "POST" });
      state.phongThu.phien = p.id;
    }
    const goiY = await api("/phong-thu/goi-y");
    $("#phongthu-goiy").innerHTML = Object.entries(goiY).map(([nhom, ds]) => `<div class="row">
        <span class="row__flag"></span>
        <span class="row__body"><span class="row__title">${esc(nhom)}</span>
        <span class="row__sub row__sub--truot">${ds.map((c) => `<button type="button" class="btn btn--sm" data-goiy="${esc(c.id)}"
            data-hoi="${esc(c.hoi)}" data-kyvong='${esc(JSON.stringify(c.ky_vong))}'>${esc(c.hoi)}</button>`).join(" ")}</span></span>
      </div>`).join("");
    // Khung chat trống trơn lúc mới mở trông như chưa tải xong. Vẽ ngay để
    // nó nói "chưa có lượt nào" thay vì im lặng.
    veChatPhongThu();
    await veNganSachPhongThu();
  } catch (e) { toast(e.message, true); }
}

async function veNganSachPhongThu() {
  const ns = await api("/phong-thu/ngan-sach");
  $("#phongthu-ngansach").textContent = `Đã thử ${usd(ns.da_tieu)}${ns.tran > 0 ? " / trần " + usd(ns.tran) : ""}`;
}

function veChatPhongThu() {
  const box = $("#phongthu-chat");
  box.innerHTML = state.phongThu.luot.map((l) => `<div class="row">
      <span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Khách</span><span class="row__sub">${esc(l.khach)}</span></span>
    </div><div class="row">
      <span class="row__flag row__flag--${esc(l.tone)}"></span>
      <span class="row__body"><span class="row__title">Agent</span><span class="row__sub">${esc(l.agent)}</span>
      <span class="row__sub">${usd(l.cost_usd)} · ${l.latency_ms} ms${l.escalate ? " · CHUYỂN NGƯỜI" : ""}</span></span>
    </div>`).join("") || '<p class="empty">Chưa có lượt nào.</p>';
  box.scrollTop = box.scrollHeight;
}

function veBenTrongPhongThu(d) {
  const luoi = d.luoi_bat
    ? `<div class="row"><span class="row__flag row__flag--${esc(NHAN_LUOI_MAU[d.luoi_bat] || "assist")}"></span>
        <span class="row__body"><span class="row__title">Lưới bắt: ${esc(d.nhan_luoi || d.luoi_bat)}</span>
        <span class="row__sub">${esc(d.escalate_reason)}</span></span></div>`
    : `<div class="row"><span class="row__flag row__flag--auto"></span>
        <span class="row__body"><span class="row__title">Không lưới nào bắt</span></span></div>`;
  const congCu = d.cong_cu.length ? d.cong_cu.map((c, i) => `<details class="row">
      <summary class="row__body"><span class="row__title">${i + 1}. ${esc(c.ten)}${c.thu_nghiem ? " · ĐANG THỬ" : ""}</span>
      <span class="row__sub">vòng ${c.vong} · ${c.ms} ms</span></summary>
      <pre class="pre">${esc(JSON.stringify({ tham_so: c.tham_so, ket_qua: c.ket_qua }, null, 2))}</pre>
    </details>`).join("") : '<p class="empty">Không gọi công cụ nào.</p>';
  const cham = d.cham || {};
  const tuCam = (cham.tu_cam || []).length ? `Từ cấm: ${esc(cham.tu_cam.join(", "))}` : "Không có từ cấm";
  const ht = cham.hinh_thuc || {};
  const loiHt = Object.entries(ht).filter(([k, v]) => k !== "dat" && v && (!Array.isArray(v) || v.length)).map(([k]) => k);
  const boVang = cham.so_voi_bo_vang
    ? `<div class="row"><span class="row__flag row__flag--${cham.so_voi_bo_vang.dat ? "auto" : "halt"}"></span>
        <span class="row__body"><span class="row__title">So với bộ vàng: ${cham.so_voi_bo_vang.dat ? "ĐẠT" : "KHÔNG ĐẠT"}</span>
        <span class="row__sub">${esc([...(cham.so_voi_bo_vang.thieu || []).map((t) => "thiếu " + t),
          ...(cham.so_voi_bo_vang.cam || []).map((t) => "cấm " + t),
          ...(cham.so_voi_bo_vang.sai_chuyen ? ["sai chuyển người"] : [])].join(" · ") || "đủ từ khoá, đúng chuyển người")}</span></span></div>`
    : "";
  const nguon = d.sources || [];
  // Chi tiết từng vòng gọi model — số liệu thuần từ Reply.vong, không có
  // chuỗi máy chủ nào lọt vào (mọi trường đều là number), nên không cần esc().
  const cacVong = d.vong.map((v, i) => `<div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Vòng ${i + 1}: ${usd(v.cost_usd)} · ${v.latency_ms} ms</span>
      <span class="row__sub">${v.tokens_in} vào / ${v.tokens_out} ra token · ${v.so_cong_cu} công cụ</span></span></div>`).join("");
  $("#phongthu-bentrong").innerHTML = `${luoi}
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">Độ tin cậy ${pct(d.confidence)}${d.grounded ? " · có căn cứ" : " · KHÔNG căn cứ"}</span>
      <span class="row__sub">${nguon.length ? esc(nguon.join(" · ")) : "không trích tài liệu nào"}</span></span></div>
    ${(d.goi_ky_nang || []).length ? `<div class="row"><span class="row__flag row__flag--spend"></span><span class="row__body"><span class="row__title">Gói kỹ năng kích hoạt</span><span class="row__sub">${esc(d.goi_ky_nang.join(" · "))}</span></span></div>` : ""}
    <h3 class="panel__head">Công cụ đã gọi</h3>${congCu}
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">${usd(d.cost_usd)} · ${d.latency_ms} ms · ${esc(d.model)}</span>
      <span class="row__sub">${d.vong.length} vòng · ${d.tokens_in} vào / ${d.tokens_out} ra token</span></span></div>
    ${cacVong}
    <h3 class="panel__head">Chấm nhanh</h3>
    <div class="row"><span class="row__flag"></span>
      <span class="row__body"><span class="row__title">${tuCam}</span>
      <span class="row__sub">${loiHt.length ? "Lỗi hình thức: " + esc(loiHt.join(", ")) : "Hình thức đạt"}</span></span></div>
    ${boVang}`;
}

/* Phiên thử sống trong RAM TIẾN TRÌNH (agent/core/phong_thu_phien.py), nên
 * nó biến mất mỗi lần máy chủ khởi động lại, và tự hết sau 2 giờ không dùng.
 * Tab đang mở thì vẫn giữ id cũ trong biến JS — gửi lên là 404.
 *
 * Trước bản này, 404 chỉ thành một toast "Phiên thử không tồn tại hoặc đã
 * hết hạn" rồi thôi: bấm Gửi lại cũng 404, mãi mãi, cho tới khi người dùng
 * đoán ra là phải bấm "Phiên mới" hoặc tải lại trang. Đo được trên máy chủ
 * thật 14.09.2026 — hai lần 404 liên tiếp cùng một tab, ngay sau khi tôi
 * bật lại máy chủ.
 *
 * Giờ tự mở phiên mới rồi gửi lại ĐÚNG MỘT LẦN. Phiên thử không mang dữ
 * liệu quý nên mở lại là vô hại — nhưng phải NÓI RA, vì lịch sử hội thoại
 * thử mất theo: agent không còn nhớ các lượt trước, và một màn hình vẫn
 * hiện lượt cũ trong khi agent đã quên là một màn hình nói dối.
 */
async function hoiPhongThu(cauHoi) {
  const q = (cauHoi || "").trim();
  if (!q) return;
  if (!state.phongThu.phien) await loadPhongThu();
  if (!state.phongThu.phien) {
    // Không có phiên mà vẫn gửi thì URL thành `/phien/null/hoi` — 404 với
    // một lý do khác hẳn lý do thật, và người đọc log sẽ đi tìm nhầm chỗ.
    toast("Chưa mở được phiên thử. Bấm “Phiên mới” hoặc tải lại trang.", true);
    return;
  }
  const body = { cau_hoi: q, ky_vong: phongThuKyVong };
  phongThuKyVong = null;
  const gui = () => api(
    `/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}/hoi`,
    { method: "POST", body: JSON.stringify(body) });
  try {
    let d;
    try {
      d = await gui();
    } catch (e) {
      if (e.ma !== 404) throw e;
      state.phongThu = { phien: null, luot: [] };
      state.phongThuDaTai = false;
      $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
      veChatPhongThu();
      await loadPhongThu();
      if (!state.phongThu.phien) throw e;     // mở phiên mới cũng hỏng: báo lỗi gốc
      toast("Phiên thử cũ đã hết (máy chủ khởi động lại hoặc để quá 2 giờ) — "
            + "đã mở phiên mới. Agent KHÔNG nhớ các lượt trước.");
      d = await gui();
    }
    state.phongThu.luot.push({ khach: q, agent: d.tra_loi, cost_usd: d.cost_usd, latency_ms: d.latency_ms,
      escalate: d.escalate, tone: d.luoi_bat ? (NHAN_LUOI_MAU[d.luoi_bat] || "assist") : "auto" });
    veChatPhongThu();
    veBenTrongPhongThu(d);
    await veNganSachPhongThu();
  } catch (e) { toast(e.message, true); }
}

/* Khoá nút trong lúc chờ model.
 *
 * Một lượt mất 3–7 giây, có ca đo được 100 giây. Không khoá thì người dùng
 * tưởng bấm hụt và bấm tiếp — mỗi lần là một lượt gọi model THẬT: tốn tiền
 * thật, và các câu trả lời về không đúng thứ tự làm khung chat nhảy loạn. */
$("#phongthu-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  const o = f.querySelector("[name=cau_hoi]");
  const q = o.value;
  if (!q.trim()) return;
  const nut = f.querySelector("button[type=submit]");
  const chuCu = nut.textContent;
  nut.disabled = true;
  o.disabled = true;
  nut.textContent = "Đang hỏi…";
  o.value = "";
  try {
    await hoiPhongThu(q);
  } finally {
    nut.disabled = false;
    o.disabled = false;
    nut.textContent = chuCu;
    o.focus();
  }
});
// Xoá phiên trên máy chủ trước khi tạo hay bỏ hẳn — phiên bỏ đi thì trả
// RAM tiến trình ngay, không đợi dọn theo TTL 2 giờ (agent/core/phong_thu_phien.py).
async function xoaPhienPhongThuTrenMayChu() {
  if (!state.phongThu.phien) return;
  try {
    await api(`/phong-thu/phien/${encodeURIComponent(state.phongThu.phien)}`, { method: "DELETE" });
  } catch (e) {
    // 404 ở đây KHÔNG phải lỗi: phiên đã không còn trên máy chủ, mà đó đúng
    // là thứ đang muốn. Báo đỏ làm người dùng tưởng nút Phiên mới bị hỏng.
    if (e.ma !== 404) toast(e.message, true);
  }
}

$("#phongthu-moi")?.addEventListener("click", async () => {
  await xoaPhienPhongThuTrenMayChu();
  state.phongThu = { phien: null, luot: [] };
  state.phongThuDaTai = false;
  $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  veChatPhongThu();
  await loadPhongThu();
});
$("#phongthu-xoa")?.addEventListener("click", async () => {
  await xoaPhienPhongThuTrenMayChu();
  state.phongThu = { phien: null, luot: [] };
  state.phongThuDaTai = false;
  $("#phongthu-chat").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  $("#phongthu-bentrong").innerHTML = '<p class="empty">Chưa có lượt nào.</p>';
  toast("Đã xoá phiên thử");
});
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-goiy]");
  if (!b) return;
  $("#phongthu-form [name=cau_hoi]").value = b.dataset.hoi;
  try { phongThuKyVong = JSON.parse(b.dataset.kyvong); } catch { phongThuKyVong = null; }
});


/* ---------------- cài đặt API ---------------- */

const API_NHOM = { model: "Model ngôn ngữ", erp: "ERP (ERPNext)", van_chuyen: "Vận chuyển (GHN / GHTK)", thanh_toan: "Thanh toán (VietQR)", binh_luan: "Bình luận Facebook", csat: "Khảo sát hài lòng (CSAT)", bvdlcn: "Bảo vệ dữ liệu cá nhân" };

/* Ô nhập cho một khoá. Ô BÍ MẬT là password và KHÔNG có value: giá trị
 * không có ở client để mà dựng — máy chủ chỉ gửi bốn ký tự cuối. */
function oNhapApi(m) {
  if (m.chon && m.chon.length) {
    return `<select data-api-khoa="${m.khoa}" aria-label="${esc(m.nhan || m.khoa)}">${
      m.chon.map((c) => `<option value="${esc(c)}"${c === m.hien ? " selected" : ""}>${esc(c)}</option>`).join("")
    }</select>`;
  }
  if (m.bi_mat) {
    return `<input type="password" autocomplete="off" data-api-khoa="${m.khoa}"
      placeholder="${m.da_dat ? `đã đặt ${esc(m.hien)} — dán khoá mới để thay` : "chưa đặt — dán khoá vào đây"}">`;
  }
  return `<input type="text" data-api-khoa="${m.khoa}" value="${esc(m.hien || "")}"
    placeholder="${esc(m.nhan)}">`;
}

function trangThaiApi(m) {
  const nguon = { csdl: "từ dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  const kiem = m.kiem_ket_qua ? ` · kiểm ${new Date(m.kiem_luc).toLocaleString("vi-VN")}: ${esc(m.kiem_ket_qua)}` : "";
  return `<span class="row__sub">${nguon}${kiem}</span>`;
}

async function loadCaiDatApi() {
  const d = await api("/cai-dat-api");
  $("#api-vault").textContent = d.vault_san_sang ? "mã hoá AES-256 trong CSDL" : "vault chưa cấu hình — chỉ xem được";
  const nhom = {};
  for (const m of d.muc) (nhom[m.nhom] ||= []).push(m);
  $("#api-nhom").innerHTML = Object.entries(API_NHOM).map(([ma, ten]) => `
    <div class="row" data-api-nhom="${ma}">
      <span class="row__flag ${(nhom[ma] || []).some((m) => m.da_dat) ? "row__flag--auto" : ""}"></span>
      <span class="row__body">
        <span class="row__title">${esc(ten)}</span>
        ${(nhom[ma] || []).map((m) => {
          // Tách riêng biến này: giá trị từ máy chủ chỉ được nhắc tới trong
          // template SAU khi đã qua esc() — không để điều kiện rẽ nhánh nằm
          // ngay trong dấu ${...} kèm giá trị thô.
          const yNghia = m.y_nghia ? ` — ${esc(m.y_nghia)}` : "";
          return `<div class="rows" style="margin:.35rem 0" data-api-row="${esc(m.khoa)}">
          <label class="row__sub">${esc(m.nhan)}${yNghia}</label>
          ${oNhapApi(m)} ${trangThaiApi(m)}
        </div>`;
        }).join("")}
        <div class="rowbtns">
          <button type="button" class="btn btn--sm" data-api-kiem="${ma}">Kiểm tra</button>
          <button type="button" class="btn btn--sm btn--go" data-api-luu="${ma}">Lưu</button>
          <span class="row__sub" data-api-kq="${ma}"></span>
        </div>
      </span>
    </div>`).join("");
  hienODungProvider();
}

/* Provider nào cần khoá nào. gemini/vertex xác thực qua gcloud trên máy,
 * không có khoá nào để nhập — nên không có mục nào trong bảng này. */
const API_KHOA_THEO_PROVIDER = { gemini_api: "GEMINI_API_KEY", anthropic: "ANTHROPIC_API_KEY" };

/* Chỉ hiện ô khoá của provider đang chọn.
 *
 * Hiện cả hai ô là mời người ta dán khoá Anthropic trong khi provider là
 * gemini_api: khoá lưu đúng, nút Kiểm tra báo đúng, và agent vẫn không trả
 * lời được — không có gì nổ, người dùng không biết nhìn đâu. */
function hienODungProvider() {
  const o = document.querySelector('[data-api-nhom="model"] [data-api-khoa="LLM_PROVIDER"]');
  if (!o) return;
  const can = API_KHOA_THEO_PROVIDER[o.value] || "";
  for (const khoa of Object.values(API_KHOA_THEO_PROVIDER)) {
    const dong = document.querySelector(`[data-api-row="${khoa}"]`);
    if (dong) {
      const dang_an = khoa !== can;
      dong.hidden = dang_an;
      /* Khi ẩn dòng, xoá tất cả password đã gõ để khoá cũ không thể quay lại
       * nếu người dùng đổi provider rồi đổi lại. */
      if (dang_an) {
        dong.querySelectorAll('input[type="password"]').forEach((ip) => {
          ip.value = "";
        });
      }
    }
  }
}

document.addEventListener("change", (e) => {
  const o = e.target.closest('[data-api-nhom="model"] [data-api-khoa="LLM_PROVIDER"]');
  if (o) hienODungProvider();
});

/* Gom giá trị đang gõ trong một nhóm; bỏ ô trống để không ghi đè khoá đã
 * lưu bằng chuỗi rỗng. */
function giaTriApiDangGo(ma) {
  const ra = {};
  document.querySelectorAll(`[data-api-nhom="${ma}"] [data-api-khoa]`).forEach((o) => {
    /* Một ô đã ẩn là một ô người dùng không còn nhìn thấy — gửi giá trị của nó
     * đi là lưu thầm, có thể là khoá cũ từ trước khi đổi provider. Bỏ qua ô ẩn. */
    if (o.closest("[data-api-row]")?.hidden) return;
    const v = (o.value || "").trim();
    if (v) ra[o.dataset.apiKhoa] = v;
  });
  return ra;
}

document.addEventListener("click", async (e) => {
  const kiem = e.target.closest("[data-api-kiem]");
  const luu = e.target.closest("[data-api-luu]");
  if (!kiem && !luu) return;
  const ma = (kiem || luu).dataset.apiKiem || (kiem || luu).dataset.apiLuu;
  const kq = $(`[data-api-kq="${ma}"]`);
  try {
    if (kiem) {
      kq.textContent = "đang kiểm…";
      const r = await api("/cai-dat-api/kiem-tra", {
        method: "POST", body: JSON.stringify({ nhom: ma, gia_tri: giaTriApiDangGo(ma) }),
      });
      kq.textContent = (r.ok ? "✓ " : "✗ ") + r.chi_tiet;
      return;
    }
    const gia_tri = giaTriApiDangGo(ma);
    const da_luu = [];
    const hong = [];
    // Lưu từng khoá riêng: một khoá hỏng không được che khoá đã lưu, và
    // người dùng phải biết đúng khoá nào hỏng — gộp chung một try thì khoá
    // 1 đã ghi vào CSDL nhưng người dùng chỉ thấy "lỗi", tưởng chưa lưu gì.
    for (const [khoa, v] of Object.entries(gia_tri)) {
      try {
        await api(`/cai-dat-api/${khoa}`, { method: "PUT", body: JSON.stringify({ gia_tri: v }) });
        da_luu.push(khoa);
      } catch (err) {
        hong.push({ khoa, loi: err.message });
      }
    }
    // Nạp lại LUÔN, kể cả khi có khoá hỏng: khoá đã lưu phải hiện trạng thái
    // mới (nguồn = csdl, bốn ký tự cuối), không đứng khựng ở dữ liệu cũ.
    await loadCaiDatApi();
    if (!hong.length) {
      toast(`Đã lưu ${da_luu.length} khoá — có hiệu lực ngay`);
    } else {
      const thongBao = `Lưu được ${da_luu.length}, hỏng ${hong.length}: ` +
        hong.map((h) => h.khoa + " (" + h.loi + ")").join("; ");
      toast(thongBao, true);
      // kq cũ đã bị loadCaiDatApi() dựng lại DOM mới — lấy lại tham chiếu.
      const kqMoi = $(`[data-api-kq="${ma}"]`);
      if (kqMoi) kqMoi.textContent = thongBao;
    }
  } catch (err) {
    kq.textContent = "";
    toast(err.message, true);
  }
});


/* ---------------- xác nhận bảng giá ---------------- */

/* Mục "Bảng giá" là thứ máy KHÔNG tự kiểm được: nó chỉ thấy một cái tên và
 * một con số, không biết bảng nào là bảng bán lẻ.
 *
 * Nhưng một cảnh báo không bao giờ tắt được thì tệ hơn không có cảnh báo —
 * người vận hành biết mục ấy lúc nào cũng vàng, nên lần sau có mục vàng
 * THẬT thì mắt họ lướt qua. */
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-bg-xacnhan]");
  if (!b) return;
  const ghi = b.dataset.bgXacnhan === "ghi";
  if (ghi && !confirm(
      "Xác nhận bảng giá đang dùng ĐÚNG là giá bán lẻ?\n\n" +
      "Sai thì agent báo giá sỉ cho khách lẻ, rất tự tin.\n" +
      "Xác nhận này gắn với tên bảng giá hiện tại — đổi sang bảng khác thì " +
      "cảnh báo quay lại.")) return;
  try {
    await api("/erp/xac-nhan-bang-gia", { method: ghi ? "POST" : "DELETE" });
    toast(ghi ? "Đã ghi nhận xác nhận" : "Đã gỡ — cảnh báo quay lại");
    $("#erpthu")?.click();
  } catch (err) { toast(err.message, true); }
});

