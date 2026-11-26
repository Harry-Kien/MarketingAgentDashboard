/* ---------------- SLA & Giờ làm việc (Cấu hình chung → tab cc-sla) ----------------
 *
 * Gắn qua `GAN_TAB['cc-sla']`. Màn này từng là MỘT trang dài bốn khối liền
 * nhau (UX-15-01): người quản trị cuộn qua bảng mục tiêu, danh sách hạn, lịch
 * bảy ngày và ô khoá kỹ thuật mà không biết mình đang ở phần nào. Nay chia
 * bốn khu, mỗi khu một câu hỏi:
 *
 *   1. Mục tiêu & Thời hạn — đồng hồ của ba mục tiêu (giờ làm việc / 24/7)
 *      và số phút theo kênh × mức ưu tiên (`/routing/sla-policies`).
 *   2. Giờ làm việc — lịch CHUNG (agent/core/lich_lam_viec.py): một nguồn cho
 *      hạn SLA, câu báo khách ngoài giờ, quy tắc tự động "ngoài giờ".
 *   3. Cảnh báo — ngưỡng chung, việc làm khi trễ, ngưỡng riêng từng mục tiêu;
 *      ô khoá kỹ thuật (`#api-nhom-sla` trong index.html) dời vào phần
 *      "Nâng cao" thu gọn (UX-15-05).
 *   4. Thứ tự áp dụng & Thử tính — luật ưu tiên giữa các cấu hình và máy tính
 *      hạn gọi `/api/sla/xem-truoc-han` (26b-sla-thu-tinh.js, UX-15-03).
 *
 * MỖI NÚT LƯU CHỈ GỬI ĐIỀU KHU CỦA NÓ HIỆN: đồng hồ và ngưỡng riêng cùng đi
 * qua `PUT /sla/muc-tieu`, nhưng nằm ở hai khu. Lưu ở khu Mục tiêu gửi ngưỡng
 * ĐANG LƯU trên máy chủ, không gửi ô ngưỡng ở khu Cảnh báo — một ô người ta
 * gõ dở rồi bỏ đi không được lặng lẽ thành cấu hình.
 *
 * KHÔNG nằm trong vòng làm mới 6 giây: lịch đang sửa dở mà bị dựng lại là
 * mất trắng, rồi người ta bấm Lưu một lịch cũ. Chỉ vẽ lại khi mở tab hoặc
 * sau khi Lưu.
 *
 * SLA KHÔNG hiện thường trực trong khung hội thoại (phiếu việc mục 15.7) —
 * cảnh báo đi qua chuông, số liệu ở màn Phân tích.
 */
window.GAN_TAB = window.GAN_TAB || {};

const SLA_UU_TIEN = { normal: "thường", low: "thấp", high: "cao", urgent: "gấp" };
const SLA_KHU = [
  ["muc-tieu", "Mục tiêu & Thời hạn"],
  ["gio", "Giờ làm việc"],
  ["canh-bao", "Cảnh báo"],
  ["thu-tinh", "Thứ tự áp dụng & Thử tính"],
];
/* Mỗi mục tiêu: một câu nói nó đo gì, một ví dụ nghiệp vụ (UX-15-02). Ví dụ
   nói rõ điều người ta hay hiểu nhầm nhất — tin tự động không tính. */
const SLA_GIAI_THICH = {
  phan_hoi_dau: {
    y: "Từ lúc khách nhắn tới câu trả lời THẬT đầu tiên của AI hoặc nhân viên.",
    vd: "Đặt 15 phút: khách nhắn 9:00 thì phải có AI/người trả lời thật trước 9:15. Tin tự động \"đã nhận\", câu báo chuyển người hay ngoài giờ KHÔNG tính.",
  },
  phan_hoi_sau_chuyen_giao: {
    y: "Từ lúc AI chuyển cho người tới tin đầu tiên của NHÂN VIÊN.",
    vd: "Đặt 30 phút: AI chuyển lúc 10:00 thì nhân viên phải nhắn khách trước 10:30. Mỗi lần chuyển giao là một hạn riêng.",
  },
  giai_quyet: {
    y: "Từ lúc bắt đầu lượt phục vụ tới khi hội thoại được đánh dấu giải quyết.",
    vd: "Đặt 1 ngày: lượt bắt đầu 9:00 thứ Hai phải xong trước 9:00 thứ Ba (nếu chạy 24/7).",
  },
};
const SLA_CHE_DO_GIAI_THICH = {
  gio_lam_viec: "Đồng hồ dừng ngoài giờ mở cửa và ngày nghỉ — khách nhắn 22:00 thì hạn tính từ giờ mở cửa hôm sau.",
  "24_7": "Đồng hồ chạy liên tục, kể cả ban đêm và ngày lễ — hợp với việc AI trực đêm.",
};

function slaLuc(iso) { return iso ? new Date(iso).toLocaleString("vi-VN") : "—"; }

function slaNguon(n) {
  return n === "csdl" ? "lưu trên dashboard" : "đang lấy từ .env";
}

/* 90 → "1 giờ 30 phút", 1440 → "1 ngày". Số phút nhập vào là số thật lưu
   trong CSDL; dòng này chỉ đọc lại cho người khỏi phải chia nhẩm. */
function slaPhut(p) {
  if (p == null || p === "") return "—";
  let con = Math.round(Number(p));
  const ngay = Math.floor(con / 1440); con -= ngay * 1440;
  const gio = Math.floor(con / 60); con -= gio * 60;
  const phan = [];
  if (ngay) phan.push(`${ngay} ngày`);
  if (gio) phan.push(`${gio} giờ`);
  if (con || !phan.length) phan.push(`${con} phút`);
  return phan.join(" ");
}

function slaGoiY(moTa, vd = "", ten = "") {
  const nhan = ten ? `Giải thích ${ten}` : "Giải thích";
  return `<span class="sla-tip-boc">
    <button type="button" class="sla-goi-y" data-sla-tip aria-expanded="false" aria-label="${esc(nhan)}">?</button>
    <span class="sla-tip" role="tooltip">
      <span class="sla-tip__y">${esc(moTa)}</span>
      ${vd ? `<span class="sla-tip__vd"><b>Ví dụ:</b> ${esc(vd)}</span>` : ""}
    </span>
  </span>`;
}

/* ---------------- khu 1: mục tiêu & thời hạn ---------------- */

function slaVeMucTieu(d, sua) {
  const the = d.muc_tieu.map((m) => {
    const g = SLA_GIAI_THICH[m.ma] || { y: "", vd: "" };
    const ghiChu = `${SLA_CHE_DO_GIAI_THICH[m.che_do] || ""} (${slaNguon(m.nguon_che_do)})`;
    return `<div class="sla-mt" data-sla-mt="${esc(m.ma)}">
      <div class="sla-mt__dau"><b>${esc(m.ten)}</b> ${slaGoiY(g.y, g.vd, m.ten)}</div>
      <label class="field sla-mt__chon"><span>Đồng hồ tính</span>
        <select data-sla-che-do title="${esc(ghiChu)}"${sua ? "" : " disabled"}>${Object.entries(d.che_do).map(([k, v]) =>
          `<option value="${esc(k)}"${k === m.che_do ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
    </div>`;
  }).join("");
  return `<section class="panel">
    <h2 class="panel__head">Ba mục tiêu SLA
      <span class="panel__note">mỗi mục tiêu chọn đồng hồ tính riêng</span></h2>
    <div class="sla-luoi">${the}</div>
    ${sua ? `<div class="rowbtns sla-nut"><button type="button" class="btn btn--sm btn--go" data-sla-luu-mt>Lưu đồng hồ</button>
      <span class="sla-kq" data-sla-kq-mt aria-live="polite"></span></div>` : ""}
  </section>`;
}

function slaTenKenh(kenh, id) {
  if (!id) return "mọi kênh";
  const k = kenh.find((x) => String(x.id) === String(id));
  return k ? (k.display_name || k.channel) : "kênh đã xoá";
}

function slaVeChinhSach(cs, kenh, gioRieng, sua) {
  const conTacDung = gioRieng.con_tac_dung;
  /* Chính sách "mọi kênh" lên đầu, rồi theo kênh, trong mỗi nhóm theo mức. */
  const bac = { urgent: 0, high: 1, normal: 2, low: 3 };
  const xep = [...cs].sort((a, b) => (a.account_id ? 1 : 0) - (b.account_id ? 1 : 0)
    || slaTenKenh(kenh, a.account_id).localeCompare(slaTenKenh(kenh, b.account_id))
    || (bac[a.priority] ?? 9) - (bac[b.priority] ?? 9));
  const dong = xep.map((p) => {
    const gr = p.business_hours && p.business_hours.bat_dau != null
      ? `<span class="sla-mo-ta">giờ riêng ${esc(p.business_hours.bat_dau)}h–${esc(p.business_hours.ket_thuc)}h${
          conTacDung ? "" : " — không còn tác dụng vì đã có lịch chung"}</span>` : "";
    return `<tr>
      <td data-nhan="Kênh">${esc(slaTenKenh(kenh, p.account_id))}${gr}</td>
      <td data-nhan="Mức"><span class="tag tag--plain">${esc(SLA_UU_TIEN[p.priority] || p.priority)}</span>${
        p.active ? "" : ' <span class="tag tag--halt">tắt</span>'}</td>
      <td data-nhan="Phản hồi đầu">${esc(slaPhut(p.first_response_minutes))}</td>
      <td data-nhan="Sau chuyển giao">${p.handover_response_minutes ? esc(slaPhut(p.handover_response_minutes)) : '<span class="sla-mo-ta">không đặt</span>'}</td>
      <td data-nhan="Giải quyết">${esc(slaPhut(p.resolution_minutes))}</td>
    </tr>`;
  }).join("");
  const iconRong = `<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`;
  const bang = cs.length ? `<div class="bang-cuon"><table class="bang sla-bang">
      <thead><tr><th>Kênh</th><th>Mức ưu tiên</th><th>Phản hồi đầu</th><th>Sau chuyển giao</th><th>Giải quyết</th></tr></thead>
      <tbody>${dong}</tbody></table></div>`
    : `<div class="sla-rong">
        <div class="sla-rong__icon">${iconRong}</div>
        <p class="sla-rong__ten">Chưa có chính sách thời hạn SLA</p>
        <p class="sla-mo-ta">Chưa hội thoại nào được đặt hạn. Thêm chính sách chung cho mọi kênh hoặc riêng từng kênh để bắt đầu đo và cảnh báo.</p>
        ${sua ? '<button type="button" class="btn btn--sm btn--primary" data-sla-mo-them-cs>+ Thêm chính sách đầu tiên</button>' : ""}
      </div>`;
  const oKenh = '<option value="">mọi kênh</option>' + kenh.map((k) =>
    `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`).join("");
  return `<section class="panel">
    <div class="panel__head sla-head-nut">
      <span>Chính sách thời hạn SLA
        <span class="panel__note">chỉ để đo và cảnh báo — không tự đóng hội thoại</span></span>
      <span class="sla-head-nut__phai">
        <button type="button" class="btn btn--sm btn--ghost" data-sla-khu="thu-tinh">Thử tính hạn →</button>
        ${sua ? '<button type="button" class="btn btn--sm btn--primary" data-sla-mo-them-cs>+ Thêm chính sách</button>' : ""}
      </span>
    </div>
    <p class="sla-chu">Ưu tiên chính sách <b>đúng kênh</b> trước, sau đó <b>mọi kênh</b>; đúng mức ưu tiên trước, sau đó mức <b>thường</b>.</p>
    ${bang}
    ${sua ? `<details class="nang-cao sla-them" data-sla-them-cs>
      <summary>Thêm hoặc cập nhật chính sách thời hạn</summary>
      <form class="form" data-sla-form-cs>
      <div class="form__row sla-cs-hang">
        <label class="field"><span>Kênh</span><select name="account_id">${oKenh}</select></label>
        <label class="field"><span>Mức ưu tiên</span><select name="priority">${Object.entries(SLA_UU_TIEN).map(([k, v]) =>
          `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label class="field"><span>Phản hồi đầu (phút)</span>
          <input name="first_response_minutes" type="number" min="1" max="43200" value="15" required></label>
        <label class="field"><span>Sau chuyển giao (phút) <em class="hint">trống = không đặt</em></span>
          <input name="handover_response_minutes" type="number" min="1" max="43200" placeholder="vd 30"></label>
        <label class="field"><span>Giải quyết (phút) <em class="hint">1440 = 1 ngày</em></span>
          <input name="resolution_minutes" type="number" min="1" max="525600" value="1440" required></label>
      </div>
      <div class="rowbtns"><button type="submit" class="btn btn--sm btn--primary">Lưu thời hạn</button></div>
      <p class="sla-mo-ta">Cùng kênh và mức ưu tiên sẽ cập nhật hạn cũ. Hội thoại đang chạy giữ hạn đã đặt; hạn mới áp cho hội thoại mới sau khi lưu.</p>
    </form></details>` : ""}
  </section>`;
}

/* ---------------- khu 2: giờ làm việc ---------------- */

/* Gom NGÀY LIỀN NHAU cùng giờ: "Thứ Hai – Thứ Sáu: 08:00–21:00" (UX-15-04).
   Đọc từ đúng dữ liệu sẽ gửi đi (slaGomLich) nên bản tóm tắt luôn nói điều
   nút Lưu sẽ lưu, kể cả khi đang sửa dở. */
function slaGomNgay(tuan, ten) {
  const nhom = [];
  tuan.forEach((x, i) => {
    const khoa = x.nghi ? "nghi" : `${x.mo}-${x.dong}`;
    const cuoi = nhom[nhom.length - 1];
    if (cuoi && cuoi.khoa === khoa) cuoi.den = i;
    else nhom.push({ khoa, tu: i, den: i, x });
  });
  return nhom.map((g) => ({
    ngay: g.tu === g.den ? ten[g.tu] : `${ten[g.tu]} – ${ten[g.den]}`,
    gio: g.x.nghi ? "nghỉ" : `${g.x.mo}–${g.x.dong === "24:00" ? "hết ngày" : g.x.dong}`,
    nghi: g.x.nghi,
  }));
}

function slaVeTomTat(tuan, ten, bat) {
  if (!bat) return '<span class="tag tag--plain">Trực 24/7 — không tính giờ mở cửa</span>';
  return slaGomNgay(tuan, ten).map((g) =>
    `<span class="sla-ngay${g.nghi ? " sla-ngay--nghi" : ""}"><b>${esc(g.ngay)}</b> ${esc(g.gio)}</span>`).join("");
}

function slaChuNgay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d));
  const thu = ["Chủ nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"][t.getUTCDay()];
  return `${thu}, ${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}/${y}`;
}

function slaVeNgayLe(x, sua, homNay, chuaLuu = false) {
  const qua = x.ngay < homNay;
  return `<li class="sla-le${qua ? " sla-le--qua" : ""}" data-sla-le="${esc(x.ngay)}" data-sla-le-ten="${esc(x.ten || "")}">
    <span class="sla-le__ngay">${esc(slaChuNgay(x.ngay))}</span>
    <span class="sla-le__ten">${esc(x.ten || "Ngày nghỉ")}${qua ? ' <span class="tag tag--plain">đã qua</span>' : ""}${
      chuaLuu ? ' <span class="tag tag--assist">chưa lưu</span>' : ""}</span>
    ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-le="${esc(x.ngay)}" aria-label="Bỏ ngày ${esc(x.ngay)}">✕</button>` : ""}
  </li>`;
}

function slaHomNay() {
  return new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 10);
}

function slaVeLich(d, sua) {
  const l = d.lich;
  const ten = l.tuan.map((x) => x.thu);
  const ngay = l.tuan.map((x, i) => `<tr data-sla-thu="${i}">
      <td class="sla-tuan__thu">${esc(x.thu)}</td>
      <td><label class="sla-o-mo"><input type="checkbox" aria-label="${esc(x.thu)} mở cửa" data-sla-mo-cua${x.nghi ? "" : " checked"}${
        sua ? "" : " disabled"}><span class="sla-o-mo__chu">${x.nghi ? "Nghỉ" : "Mở"}</span></label></td>
      <td><input type="time" aria-label="${esc(x.thu)} mở cửa" data-sla-gio-mo value="${esc(x.mo || "08:00")}"${sua ? "" : " disabled"}></td>
      <td><input type="time" aria-label="${esc(x.thu)} đóng cửa" data-sla-gio-dong value="${esc(x.dong === "24:00" ? "23:59" : (x.dong || "21:00"))}"${
        sua ? "" : " disabled"}></td>
    </tr>`).join("");
  const homNay = slaHomNay();
  const le = [...l.ngay_nghi].sort((a, b) => a.ngay.localeCompare(b.ngay))
    .map((x) => slaVeNgayLe(x, sua, homNay)).join("");
  const tt = d.trang_thai;
  const nguon = l.nguon === "csdl"
    ? `Lịch lưu trên dashboard — sửa bởi ${esc(l.sua_boi || "?")} lúc ${esc(slaLuc(l.sua_luc))}.`
    : "Đang dùng cấu hình .env (cùng một khung giờ cho mọi ngày, chưa có ngày lễ).";
  const gr = d.gio_rieng_chinh_sach;
  const canhGioRieng = (!gr.con_tac_dung && gr.ds.length)
    ? `<p class="dx-canh-bao">${gr.ds.length} chính sách SLA có giờ riêng — không còn tác dụng từ khi có lịch chung.</p>` : "";
  return `<section class="panel">
    <h2 class="panel__head">Giờ làm việc
      <span class="panel__note">một lịch chung cho hạn SLA, câu báo ngoài giờ và quy tắc tự động</span></h2>
    <div class="sla-than">
      <div class="sla-gio-dau">
        <div class="sla-gio-dau__tt">
          <span class="tag ${tt.dang_trong_gio ? "tag--auto" : "tag--assist"}">${
            tt.dang_trong_gio ? "Đang trong giờ làm việc" : "Đang ngoài giờ làm việc"}</span>
          ${!tt.dang_trong_gio && tt.mo_ke_tiep ? `<span class="sla-mo-ta">Mở lại lúc <b>${esc(slaLuc(tt.mo_ke_tiep))}</b></span>` : ""}
          <span class="sla-mo-ta">${nguon}</span>
        </div>
        <div class="sla-tom-tat" data-sla-tom-tat aria-live="polite">${slaVeTomTat(l.tuan, ten, l.bat)}</div>
      </div>
      ${canhGioRieng}
      <div class="sla-gio-2cot">
        <div class="sla-hop">
          <div class="sla-hop__dau">
            <h3 class="subhead">Lịch làm việc trong tuần</h3>
            <label class="field sla-bat"><span>Chế độ áp dụng</span><select data-sla-lich-bat${sua ? "" : " disabled"}>
              <option value="1"${l.bat ? " selected" : ""}>Bật — tính theo giờ mở / đóng cửa</option>
              <option value="0"${l.bat ? "" : " selected"}>Tắt — coi như trực 24/7</option></select></label>
          </div>
          <div class="sla-tuan"><table class="bang sla-tuan__bang">
            <thead><tr><th>Thứ</th><th>Trạng thái</th><th>Mở cửa</th><th>Đóng cửa</th></tr></thead>
            <tbody>${ngay}</tbody></table></div>
          ${sua ? '<div class="rowbtns"><button type="button" class="btn btn--sm btn--ghost" data-sla-chep-t2>Chép giờ Thứ Hai → Thứ Sáu</button></div>' : ""}
          <p class="sla-mo-ta">Giờ Việt Nam. Đặt 23:59 là hết ngày; không hỗ trợ ca qua đêm.</p>
        </div>
        <div class="sla-hop">
          <div class="sla-hop__dau">
            <h3 class="subhead">Ngày nghỉ lễ <span class="tag tag--plain">${l.ngay_nghi.length}</span></h3>
            <p class="sla-mo-ta">Đồng hồ SLA theo giờ làm việc sẽ tạm dừng vào các ngày này.</p>
          </div>
          <ul class="sla-ds-le" data-sla-ds-le>${le || '<li class="empty">Chưa có ngày nghỉ lễ nào.</li>'}</ul>
          ${sua ? `<div class="sla-them-le">
              <div class="sla-them-le__hang">
                <label class="field"><span>Ngày nghỉ</span><input type="date" data-sla-le-moi></label>
                <label class="field"><span>Tên ngày lễ <em class="hint">tuỳ chọn</em></span><input type="text" maxlength="80" data-sla-le-ten-moi placeholder="vd Quốc khánh"></label>
              </div>
              <button type="button" class="btn btn--sm" data-sla-them-le>+ Thêm ngày nghỉ</button>
            </div>` : ""}
        </div>
      </div>
      ${sua ? `<div class="sla-cuoi-bar">
          <div class="rowbtns sla-nut">
            <button type="button" class="btn btn--sm btn--go" data-sla-luu-lich>Lưu giờ làm việc</button>
            ${l.nguon === "csdl" ? '<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-lich>Bỏ lịch, dùng .env</button>' : ""}
            <span class="sla-kq" data-sla-kq-lich aria-live="polite"></span>
          </div>
          <p class="sla-mo-ta">Hội thoại đang chạy giữ hạn cũ; lịch mới áp cho hạn đặt sau khi lưu. Câu báo ngoài giờ và quy tắc tự động đổi ngay (≤ 30 giây).</p>
        </div>` : ""}
    </div>
  </section>`;
}

function slaGomLich(el) {
  const tuan = $$("[data-sla-thu]", el).map((r) => {
    const dong = $("[data-sla-gio-dong]", r);
    return {
      nghi: !$("[data-sla-mo-cua]", r).checked,
      mo: $("[data-sla-gio-mo]", r).value,
      /* Ô giờ của trình duyệt không cho gõ 24:00 — 23:59 nghĩa là hết ngày. */
      dong: dong.value === "23:59" ? "24:00" : dong.value,
    };
  });
  const ngay_nghi = $$("[data-sla-le]", el).map((li) => ({ ngay: li.dataset.slaLe, ten: li.dataset.slaLeTen || "" }));
  return { bat: $("[data-sla-lich-bat]", el).value === "1", tuan, ngay_nghi };
}

/* ---------------- khu 3: cảnh báo ---------------- */

const SLA_KHI_TRE = {
  bao: ["Chỉ báo", "Chuông thông báo tới người phụ trách và quản lý; hội thoại giữ nguyên mức ưu tiên."],
  bao_va_nang_uu_tien: ["Báo + nâng ưu tiên", "Như trên, và hội thoại lên một bậc ưu tiên để nổi lên đầu hàng chờ. Hạn không bị rút thêm."],
};

function slaVeCanhBao(d, suaMt) {
  /* Ngưỡng chung và việc làm khi trễ là khoá `cau_hinh_dong`: ghi cần
     `cau_hinh.sua`, khác quyền của phần còn lại của màn này. */
  const suaCh = coQuyen("cau_hinh.sua");
  const tat = suaCh ? "" : " disabled";
  const khiTre = Object.entries(SLA_KHI_TRE).map(([k, [ten, mo]]) => `<label class="sla-chon">
      <input type="radio" name="sla_khi_tre" value="${esc(k)}" data-sla-khi-tre${k === d.khi_tre ? " checked" : ""}${tat}>
      <span><b>${esc(ten)}</b><span class="sla-mo-ta">${esc(mo)}</span></span></label>`).join("");
  const rieng = d.muc_tieu.map((m) => `<div class="sla-rieng-dong">
      <div class="sla-rieng-dong__ten">
        <b>${esc(m.ten)}</b>
        <span class="sla-mo-ta">Đang áp dụng: ${esc(m.nguong_hieu_luc)}%</span>
      </div>
      <span class="sla-so-donvi">
        <input type="number" min="10" max="95" step="1" class="sla-o-so" data-sla-nguong-mt="${esc(m.ma)}"
          aria-label="Ngưỡng riêng ${esc(m.ten)}" value="${m.nguong_canh_bao == null ? "" : esc(m.nguong_canh_bao)}"
          placeholder="${esc(d.nguong_chung)}"${suaMt ? "" : " disabled"}>
        <span>%</span>
      </span>
    </div>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Cảnh báo sớm và xử lý khi quá hạn
      <span class="panel__note">gửi qua chuông thông báo tới người phụ trách và quản lý</span></h2>
    <div class="sla-than">
      <div class="sla-cb-2cot">
        <div class="sla-hop">
          <div class="sla-hop__dau">
            <h3 class="subhead">Cảnh báo chung</h3>
            <p class="sla-mo-ta">Áp dụng mặc định cho mọi mục tiêu SLA chưa đặt ngưỡng riêng.</p>
          </div>
          <div class="field">
            <span>Ngưỡng cảnh báo sớm (%) ${slaGoiY("Phần thời gian cho phép đã dùng thì gửi cảnh báo trước. Số nguyên 10–95.")}</span>
            <div class="sla-truot-nhom">
              <input type="range" min="10" max="95" step="1" class="sla-truot" data-sla-nguong-truot
                aria-label="Thanh trượt ngưỡng cảnh báo (%)" value="${esc(d.nguong_chung)}"${tat}>
              <span class="sla-so-donvi">
                <input type="number" min="10" max="95" step="1" class="sla-o-so" data-sla-nguong-chung
                  aria-label="Ngưỡng cảnh báo (%)" value="${esc(d.nguong_chung)}"${tat}>
                <span>%</span>
              </span>
            </div>
          </div>
          <p class="sla-vd" data-sla-vd-nguong><b>Ví dụ:</b> ${esc(slaVdNguong(d.nguong_chung))}</p>
          <fieldset class="sla-khi-tre"><legend>Xử lý khi quá hạn</legend>${khiTre}</fieldset>
          <div class="sla-hop__cuoi">
            ${suaCh ? `<div class="rowbtns sla-nut"><button type="button" class="btn btn--sm btn--go" data-sla-luu-canh-bao>Lưu cảnh báo chung</button>
              <span class="sla-kq" data-sla-kq-cb aria-live="polite"></span></div>`
              : '<p class="sla-mo-ta">Cần quyền <b>cau_hinh.sua</b> để đổi ngưỡng chung và xử lý khi quá hạn.</p>'}
          </div>
        </div>
        <div class="sla-hop">
          <div class="sla-hop__dau">
            <h3 class="subhead">Ngưỡng riêng từng mục tiêu</h3>
            <p class="sla-mo-ta">Tuỳ chọn — để trống để dùng theo ngưỡng chung (${esc(d.nguong_chung)}%).</p>
          </div>
          <div class="sla-rieng-ds">${rieng}</div>
          <div class="sla-hop__cuoi">
            ${suaMt ? `<div class="rowbtns sla-nut"><button type="button" class="btn btn--sm" data-sla-luu-nguong-mt>Lưu ngưỡng riêng</button>
              <span class="sla-kq" data-sla-kq-nguong aria-live="polite"></span></div>`
              : '<p class="sla-mo-ta">Cần quyền <b>dinh_tuyen.sua</b> để đổi ngưỡng riêng từng mục tiêu.</p>'}
          </div>
        </div>
      </div>
      <details class="nang-cao sla-nang-cao">
        <summary>Nâng cao — khoá cấu hình kỹ thuật (SLA_NGUONG_CANH_BAO, SLA_KHI_TRE)</summary>
        <div data-sla-nang-cao></div>
      </details>
    </div>
  </section>`;
}

function slaVdNguong(n) {
  const v = Number(n);
  if (!(v >= 10 && v <= 95)) return "nhập số nguyên từ 10 tới 95.";
  const so = (x) => (Math.round(x * 100) / 100).toLocaleString("vi-VN");
  return `${v}% với hạn phản hồi 15 phút → báo khi đã qua ${so(15 * v / 100)} phút; hạn 1 ngày → báo khi đã qua ${so(24 * v / 100)} giờ.`;
}

/* ---------------- khung bốn khu ---------------- */

/* Trông như `.modeswitch` nhưng KHÔNG mang class `.modeswitch__opt`:
   `applyRuntime()` (01-nen.js) quét MỌI `.modeswitch__opt` trong trang mỗi
   nhịp làm mới — gỡ `is-on` khỏi nút không có `data-mode`, và khoá hết
   khi agent bị ngắt. Mượn class ấy là thanh chọn khu mất đánh dấu sau 6
   giây, và bị khoá chết đúng lúc người quản trị ngắt AI. */
function slaVeKhu(khu) {
  return `<div class="sla-khu" role="tablist" aria-label="Phần cấu hình SLA">${SLA_KHU.map(([ma, ten]) =>
    `<button type="button" role="tab" class="sla-khu__nut${ma === khu ? " is-on" : ""}" data-sla-khu="${ma}"
      aria-selected="${ma === khu}">${esc(ten)}</button>`).join("")}</div>`;
}

function slaDoiKhu(el, khu) {
  $$("[data-sla-o]", el).forEach((o) => { o.hidden = o.dataset.slaO !== khu; });
  $$(".sla-khu [data-sla-khu]", el).forEach((b) => {
    const on = b.dataset.slaKhu === khu;
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
}

async function ganSla(el) {
  const sua = coQuyen("dinh_tuyen.sua");
  let khu = "muc-tieu";
  let d = null;
  /* Ô khoá kỹ thuật `#api-nhom-sla` là nội dung TĨNH của index.html, nằm
     ngoài phần mô-đun thay (13-cau-hinh.js vẽ nó). Dời cả khối vào phần
     "Nâng cao" của khu Cảnh báo; giữ tham chiếu để mỗi lần dựng lại không
     xoá mất nó — và không mất chữ ai đó đang gõ trong đó. */
  const khoiKyThuat = document.getElementById("api-nhom-sla")?.closest("section.panel");
  const ve = async () => {
    let cs = [], kenh = [];
    try {
      d = await api("/sla/cau-hinh");
    } catch (e) {
      el.innerHTML = `<p class="empty">Không tải được cấu hình SLA: ${esc(e.message)}</p>`;
      return;
    }
    try { cs = (await api("/routing")).sla_policies || []; } catch { cs = []; }
    try { kenh = await api("/channel-accounts") || []; } catch { kenh = []; }
    if (khoiKyThuat && el.contains(khoiKyThuat)) khoiKyThuat.remove();
    el.innerHTML = slaVeKhu(khu)
      + `<div data-sla-o="muc-tieu" role="tabpanel">${slaVeMucTieu(d, sua) + slaVeChinhSach(cs, kenh, d.gio_rieng_chinh_sach, sua)}</div>`
      + `<div data-sla-o="gio" role="tabpanel">${slaVeLich(d, sua)}</div>`
      + `<div data-sla-o="canh-bao" role="tabpanel">${slaVeCanhBao(d, sua)}</div>`
      + `<div data-sla-o="thu-tinh" role="tabpanel">${slaVeThuTinh(kenh) + slaVeThuTu(d, cs)}</div>`;
    if (khoiKyThuat) $("[data-sla-nang-cao]", el)?.append(khoiKyThuat);
    slaDoiKhu(el, khu);
    /* Ô ngưỡng chung / khi trễ (`#api-nhom-sla`) nằm NGOÀI phần bị thay
       (index.html) — vòng làm mới không nạp nó khi mô-đun đã gắn, nên nạp ở đây. */
    try { await loadCaiDatApi(); } catch (e) { toast(e.message, true); }
  };
  const ketQua = (sel, chu, loi = false) => {
    const o = el.querySelector(sel);
    if (o) { o.textContent = chu; o.classList.toggle("is-loi", loi); }
  };
  /* Một nút gửi `PUT /sla/muc-tieu` với phần của khu mình; phần kia lấy
     từ bản máy chủ vừa trả (`d`), không đọc ô của khu khác. */
  const luuMucTieu = async (lay, sel, chuOk) => {
    const muc_tieu = d.muc_tieu.map((m) => ({ ma: m.ma, che_do: m.che_do, nguong_canh_bao: m.nguong_canh_bao, ...lay(m) }));
    try {
      await api("/sla/muc-tieu", { method: "PUT", body: JSON.stringify({ muc_tieu }) });
      toast(chuOk);
      await ve();
    } catch (err) { ketQua(sel, err.message, true); }
  };

  el.addEventListener("input", (e) => {
    if (e.target.closest("[data-sla-thu]") || e.target.closest("[data-sla-lich-bat]")) {
      const l = slaGomLich(el);
      $("[data-sla-tom-tat]", el).innerHTML = slaVeTomTat(l.tuan, d.lich.tuan.map((x) => x.thu), l.bat);
    } else if (e.target.closest("[data-sla-nguong-truot]")) {
      const v = e.target.value;
      const so = $("[data-sla-nguong-chung]", el);
      if (so) so.value = v;
      $("[data-sla-vd-nguong]", el).innerHTML = `<b>Ví dụ:</b> ${esc(slaVdNguong(v))}`;
    } else if (e.target.closest("[data-sla-nguong-chung]")) {
      const v = e.target.value;
      const tr = $("[data-sla-nguong-truot]", el);
      if (tr && Number(v) >= 10 && Number(v) <= 95) tr.value = v;
      $("[data-sla-vd-nguong]", el).innerHTML = `<b>Ví dụ:</b> ${esc(slaVdNguong(v))}`;
    }
  });
  /* Ô chọn và ô tick phát `change`, không phải lúc nào cũng `input`. */
  el.addEventListener("change", (e) => {
    const cd = e.target.closest("[data-sla-che-do]");
    if (cd) {
      cd.title = `${SLA_CHE_DO_GIAI_THICH[cd.value] || ""} (chưa lưu)`;
    }
    const moCua = e.target.closest("[data-sla-mo-cua]");
    if (moCua) {
      const chu = moCua.closest(".sla-o-mo")?.querySelector(".sla-o-mo__chu");
      if (chu) chu.textContent = moCua.checked ? "Mở" : "Nghỉ";
    }
    if (moCua || e.target.closest("[data-sla-lich-bat]")) {
      e.target.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  if (!window._slaTipDocBound) {
    window._slaTipDocBound = true;
    const dongHetTip = (tru = null) => {
      document.querySelectorAll(".sla-tip-boc.is-open").forEach((b) => {
        if (b !== tru) {
          b.classList.remove("is-open");
          b.querySelector("[data-sla-tip]")?.setAttribute("aria-expanded", "false");
        }
      });
    };
    document.addEventListener("click", (ev) => {
      const nut = ev.target.closest("[data-sla-tip]");
      if (nut) {
        ev.preventDefault();
        const boc = nut.closest(".sla-tip-boc");
        const dangMo = boc.classList.contains("is-open");
        dongHetTip(boc);
        boc.classList.toggle("is-open", !dangMo);
        nut.setAttribute("aria-expanded", dangMo ? "false" : "true");
        return;
      }
      if (!ev.target.closest(".sla-tip-boc")) dongHetTip();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") dongHetTip();
    });
  }

  el.addEventListener("click", async (e) => {
    const nutKhu = e.target.closest("[data-sla-khu]");
    if (nutKhu) {
      khu = nutKhu.dataset.slaKhu;
      slaDoiKhu(el, khu);
      return;
    }
    if (e.target.closest("[data-sla-mo-them-cs]")) {
      const det = $("[data-sla-them-cs]", el);
      if (det) {
        det.open = true;
        det.scrollIntoView({ behavior: "smooth", block: "nearest" });
        det.querySelector("select, input")?.focus();
      }
      return;
    }
    if (e.target.closest("[data-sla-luu-mt]")) {
      const chon = Object.fromEntries($$("[data-sla-mt]", el).map((r) => [r.dataset.slaMt, $("[data-sla-che-do]", r).value]));
      await luuMucTieu((m) => ({ che_do: chon[m.ma] || m.che_do }), "[data-sla-kq-mt]", "Đã lưu đồng hồ của mục tiêu SLA.");
    } else if (e.target.closest("[data-sla-luu-nguong-mt]")) {
      const nguong = Object.fromEntries($$("[data-sla-nguong-mt]", el).map((o) =>
        [o.dataset.slaNguongMt, o.value === "" ? null : Number(o.value)]));
      await luuMucTieu((m) => ({ nguong_canh_bao: nguong[m.ma] ?? null }), "[data-sla-kq-nguong]", "Đã lưu ngưỡng riêng.");
    } else if (e.target.closest("[data-sla-luu-canh-bao]")) {
      await slaLuuCanhBao(el, d, ketQua, ve);
    } else if (e.target.closest("[data-sla-chep-t2]")) {
      const hang = $$("[data-sla-thu]", el);
      const t2 = hang[0];
      const moT2 = $("[data-sla-mo-cua]", t2).checked;
      for (const r of hang.slice(1, 5)) {
        $("[data-sla-mo-cua]", r).checked = moT2;
        const chu = r.querySelector(".sla-o-mo__chu");
        if (chu) chu.textContent = moT2 ? "Mở" : "Nghỉ";
        $("[data-sla-gio-mo]", r).value = $("[data-sla-gio-mo]", t2).value;
        $("[data-sla-gio-dong]", r).value = $("[data-sla-gio-dong]", t2).value;
      }
      t2.dispatchEvent(new Event("input", { bubbles: true }));
      ketQua("[data-sla-kq-lich]", "Đã chép — bấm Lưu để có hiệu lực.");
    } else if (e.target.closest("[data-sla-them-le]")) {
      const ngay = $("[data-sla-le-moi]", el).value;
      if (!ngay) { ketQua("[data-sla-kq-lich]", "Chọn ngày trước khi thêm.", true); return; }
      if ($(`[data-sla-le="${CSS.escape(ngay)}"]`, el)) { ketQua("[data-sla-kq-lich]", "Ngày ấy đã có.", true); return; }
      const ul = $("[data-sla-ds-le]", el);
      $(".empty", ul)?.remove();
      const tam = document.createElement("ul");
      tam.innerHTML = slaVeNgayLe({ ngay, ten: $("[data-sla-le-ten-moi]", el).value.trim() }, true, slaHomNay(), true);
      const li = tam.firstElementChild;
      /* Chèn đúng thứ tự ngày — danh sách lễ đọc từ trên xuống như lịch. */
      const sau = $$("[data-sla-le]", ul).find((x) => x.dataset.slaLe > ngay);
      ul.insertBefore(li, sau || null);
      $("[data-sla-le-moi]", el).value = "";
      $("[data-sla-le-ten-moi]", el).value = "";
      ketQua("[data-sla-kq-lich]", "Đã thêm vào danh sách — bấm Lưu để có hiệu lực.");
    } else if (e.target.closest("[data-sla-bo-le]")) {
      e.target.closest("li")?.remove();
      ketQua("[data-sla-kq-lich]", "Đã bỏ khỏi danh sách — bấm Lưu để có hiệu lực.");
    } else if (e.target.closest("[data-sla-luu-lich]")) {
      try {
        await api("/sla/lich-lam-viec", { method: "PUT", body: JSON.stringify(slaGomLich(el)) });
        toast("Đã lưu giờ làm việc.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-lich]", err.message, true); }
    } else if (e.target.closest("[data-sla-bo-lich]")) {
      const ok = await hoiHop({
        tieu_de: "Bỏ lịch làm việc trên dashboard?",
        phu: "Mọi nơi quay về giờ trong .env (cùng một khung cho mọi ngày, không ngày lễ).",
        nut: "Bỏ lịch", nguy_hiem: true,
      });
      if (!ok) return;
      try {
        await api("/sla/lich-lam-viec", { method: "DELETE" });
        toast("Đã bỏ lịch — đang dùng .env.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-lich]", err.message, true); }
    }
  });

  el.addEventListener("submit", async (e) => {
    const thu = e.target.closest("[data-sla-form-thu]");
    if (thu) { e.preventDefault(); await slaThuTinh(thu, el); return; }
    const f = e.target.closest("[data-sla-form-cs]");
    if (!f) return;
    e.preventDefault();
    const v = Object.fromEntries(new FormData(f).entries());
    /* Không gửi `business_hours`: máy chủ giữ giờ riêng đang lưu (nếu có).
       Ô phút chuyển giao trống = null: chính sách không đặt mục tiêu ấy. */
    const than = {
      account_id: v.account_id || null, priority: v.priority,
      first_response_minutes: Number(v.first_response_minutes),
      handover_response_minutes: v.handover_response_minutes === "" ? null : Number(v.handover_response_minutes),
      resolution_minutes: Number(v.resolution_minutes), active: true,
    };
    const nut = f.querySelector("button[type=submit]");
    nut.disabled = true;
    try {
      await api("/routing/sla-policies", { method: "PUT", body: JSON.stringify(than) });
      toast("Đã lưu thời hạn SLA.");
      await ve();
    } catch (err) { toast(err.message, true); } finally { nut.disabled = false; }
  });

  /* Lần đầu tab hiện, `veTab` vừa gắn mô-đun vừa phát `tab:hien` — gộp
     hai lời gọi trùng nhau thành một lần tải. */
  let dangVe = null;
  const veMot = () => {
    if (!dangVe) dangVe = ve().finally(() => { dangVe = null; });
    return dangVe;
  };
  el.addEventListener("tab:hien", () => { veMot(); });
  await veMot();
}

/* Lưu ngưỡng chung và việc làm khi trễ qua đúng đường của Cài đặt API —
   chỉ khoá nào ĐÃ ĐỔI, để nhật ký cấu hình không ghi một lần "đổi" giả. */
async function slaLuuCanhBao(el, d, ketQua, ve) {
  const nguong = $("[data-sla-nguong-chung]", el).value.trim();
  const khiTre = $("[data-sla-khi-tre]:checked", el)?.value || d.khi_tre;
  const doi = {};
  if (nguong !== String(d.nguong_chung)) doi.SLA_NGUONG_CANH_BAO = nguong;
  if (khiTre !== d.khi_tre) doi.SLA_KHI_TRE = khiTre;
  if (!Object.keys(doi).length) { ketQua("[data-sla-kq-cb]", "Chưa đổi gì để lưu."); return; }
  try {
    for (const [khoa, gia_tri] of Object.entries(doi)) {
      await api(`/cai-dat-api/${khoa}`, { method: "PUT", body: JSON.stringify({ gia_tri }) });
    }
    toast("Đã lưu cảnh báo SLA — có hiệu lực ở vòng canh kế tiếp.");
    await ve();
  } catch (err) { ketQua("[data-sla-kq-cb]", err.message, true); }
}

window.GAN_TAB["cc-sla"] = (el) => ganSla(el);
