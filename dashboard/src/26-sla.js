/* ---------------- SLA & Giờ làm việc (Cấu hình chung → tab cc-sla) ----------------
 *
 * Gắn qua `GAN_TAB['cc-sla']`. Bốn khối, cùng MỘT chỗ người quản trị đặt:
 *   1. Mục tiêu SLA — ba mục tiêu (phản hồi đầu, phản hồi sau chuyển giao,
 *      giải quyết), mỗi mục tiêu chọn đồng hồ "giờ làm việc" hay "24/7" và
 *      ngưỡng cảnh báo riêng (trống = ngưỡng chung).
 *   2. Hạn theo kênh × mức ưu tiên — số phút của ba mục tiêu
 *      (`/routing/sla-policies`).
 *   3. Lịch làm việc CHUNG — giờ mở/đóng từng thứ, ngày nghỉ lễ. Một nguồn
 *      cho hạn SLA, câu báo khách ngoài giờ, điều kiện "ngoài giờ" của quy
 *      tắc tự động (agent/core/lich_lam_viec.py).
 *   4. Ngưỡng chung và việc làm khi trễ — ô `cau_hinh_dong` sẵn có
 *      (`#api-nhom-sla` trong index.html, NGOÀI phần bị thay; 13-cau-hinh.js
 *      vẽ, mô-đun này chỉ gọi nạp).
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
const SLA_GIAI_THICH = {
  phan_hoi_dau: "Khách nhắn → câu trả lời THẬT đầu tiên của AI hoặc nhân viên. Thông báo AI, câu báo chuyển người/ngoài giờ, tin mẫu tự động không tính.",
  phan_hoi_sau_chuyen_giao: "AI chuyển cho người → tin đầu tiên của NHÂN VIÊN. Mỗi lần chuyển giao một hạn riêng.",
  giai_quyet: "Bắt đầu lượt phục vụ → hội thoại được giải quyết.",
};

function slaLuc(iso) { return iso ? new Date(iso).toLocaleString("vi-VN") : "—"; }

function slaNguon(n) {
  return n === "csdl" ? "lưu trên dashboard" : "đang lấy từ .env";
}

function slaVeMucTieu(d, sua) {
  const dong = d.muc_tieu.map((m) => `<tr data-sla-mt="${esc(m.ma)}">
      <td><b>${esc(m.ten)}</b><br><span class="row__sub">${esc(SLA_GIAI_THICH[m.ma] || "")}</span></td>
      <td><select data-sla-che-do${sua ? "" : " disabled"}>${Object.entries(d.che_do).map(([k, v]) =>
        `<option value="${esc(k)}"${k === m.che_do ? " selected" : ""}>${esc(v)}</option>`).join("")}</select>
        <br><span class="row__sub">${esc(slaNguon(m.nguon_che_do))}</span></td>
      <td><input type="number" min="10" max="95" step="1" data-sla-nguong style="width:6em"
        value="${m.nguong_canh_bao == null ? "" : esc(m.nguong_canh_bao)}"
        placeholder="${esc(d.nguong_chung)} (chung)"${sua ? "" : " disabled"}>
        <br><span class="row__sub">đang dùng ${esc(m.nguong_hieu_luc)}%</span></td>
    </tr>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Mục tiêu SLA
      <span class="panel__note">đồng hồ và ngưỡng cảnh báo của từng mục tiêu</span></h2>
    <div class="kntt-bang"><table>
      <thead><tr><th>Mục tiêu</th><th>Tính thời gian</th><th>Cảnh báo khi đã dùng (%)</th></tr></thead>
      <tbody>${dong}</tbody></table></div>
    <p class="row__sub">"Theo giờ làm việc": đồng hồ chỉ chạy trong giờ mở cửa của lịch bên dưới —
      khách nhắn lúc 22 giờ thì hạn tính từ giờ mở cửa hôm sau. "24/7": chạy liên tục.
      Cảnh báo sớm và vi phạm đi qua chuông thông báo tới người đang phụ trách hội thoại và người quản lý.</p>
    ${sua ? `<div class="rowbtns"><button type="button" class="btn btn--sm btn--go" data-sla-luu-mt>Lưu mục tiêu</button>
      <span class="row__sub" data-sla-kq-mt aria-live="polite"></span></div>` : ""}
  </section>`;
}

function slaTenKenh(kenh, id) {
  if (!id) return "mọi kênh";
  const k = kenh.find((x) => String(x.id) === String(id));
  return k ? (k.display_name || k.channel) : "kênh đã xoá";
}

function slaVeChinhSach(cs, kenh, gioRieng, sua) {
  const conTacDung = gioRieng.con_tac_dung;
  const ds = cs.length ? cs.map((p) => {
    const gr = p.business_hours && p.business_hours.bat_dau != null
      ? ` · giờ riêng ${esc(p.business_hours.bat_dau)}h–${esc(p.business_hours.ket_thuc)}h${
          conTacDung ? "" : " (không còn tác dụng — đã có lịch chung)"}` : "";
    return `<div class="row">
      <span class="row__flag row__flag--${p.active ? "auto" : "halt"}"></span>
      <div class="row__main">
        <b>${esc(slaTenKenh(kenh, p.account_id))} · mức ${esc(SLA_UU_TIEN[p.priority] || p.priority)}</b>
        <span class="row__sub">phản hồi đầu ${esc(p.first_response_minutes)} phút ·
          sau chuyển giao ${p.handover_response_minutes ? esc(p.handover_response_minutes) + " phút" : "không đặt"} ·
          giải quyết ${esc(p.resolution_minutes)} phút${gr}</span>
      </div></div>`;
  }).join("") : '<p class="empty">Chưa đặt hạn nào — chưa hội thoại nào có SLA.</p>';
  const oKenh = '<option value="">mọi kênh</option>' + kenh.map((k) =>
    `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Hạn theo kênh và mức ưu tiên
      <span class="panel__note">chỉ để ĐO và cảnh báo — không tự đóng hội thoại</span></h2>
    <div class="rows">${ds}</div>
    ${sua ? `<form class="form" data-sla-form-cs>
      <div class="form__row">
        <label class="field"><span>Kênh</span><select name="account_id">${oKenh}</select></label>
        <label class="field"><span>Mức ưu tiên</span><select name="priority">${Object.entries(SLA_UU_TIEN).map(([k, v]) =>
          `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label class="field"><span>Phản hồi đầu trong (phút)</span>
          <input name="first_response_minutes" type="number" min="1" max="43200" value="15" required></label>
        <label class="field"><span>Phản hồi sau chuyển giao (phút) <em class="hint">trống = không đặt hạn</em></span>
          <input name="handover_response_minutes" type="number" min="1" max="43200" placeholder="vd 30"></label>
        <label class="field"><span>Giải quyết trong (phút)</span>
          <input name="resolution_minutes" type="number" min="1" max="525600" value="1440" required></label>
      </div>
      <div class="rowbtns"><button type="submit" class="btn btn--sm">Lưu hạn</button></div>
    </form>
    <p class="row__sub">Cùng kênh và mức ưu tiên thì lưu là thay hạn cũ. Hội thoại đang chạy giữ hạn đã đặt;
      hạn mới áp cho hội thoại (và lượt chuyển giao) bắt đầu sau khi lưu.</p>` : ""}
  </section>`;
}

function slaVeLich(d, sua) {
  const l = d.lich;
  const ngay = l.tuan.map((x, i) => `<tr data-sla-thu="${i}">
      <td>${esc(x.thu)}</td>
      <td><label><input type="checkbox" data-sla-mo-cua${x.nghi ? "" : " checked"}${sua ? "" : " disabled"}> mở cửa</label></td>
      <td><input type="time" data-sla-gio-mo value="${esc(x.mo || "08:00")}"${sua ? "" : " disabled"}></td>
      <td><input type="time" data-sla-gio-dong value="${esc(x.dong === "24:00" ? "23:59" : (x.dong || "21:00"))}"${
        sua ? "" : " disabled"}></td>
    </tr>`).join("");
  const le = l.ngay_nghi.map((x) => `<li data-sla-le="${esc(x.ngay)}" data-sla-le-ten="${esc(x.ten)}">
      ${esc(x.ngay)}${x.ten ? ` — ${esc(x.ten)}` : ""}
      ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-le="${esc(x.ngay)}">Bỏ</button>` : ""}</li>`).join("");
  const tt = d.trang_thai;
  const nguon = l.nguon === "csdl"
    ? `Lịch lưu trên dashboard — sửa bởi ${esc(l.sua_boi || "?")} lúc ${esc(slaLuc(l.sua_luc))}.`
    : "Chưa có lịch trên dashboard — đang dùng .env (GIO_LAM_VIEC_BAT_DAU / _KET_THUC, mọi ngày như nhau, không ngày lễ).";
  const gr = d.gio_rieng_chinh_sach;
  const canhGioRieng = (!gr.con_tac_dung && gr.ds.length)
    ? `<p class="row__sub"><b>⚠ ${gr.ds.length} chính sách SLA có giờ riêng (business_hours) — không còn tác dụng
        từ khi có lịch chung.</b></p>` : "";
  return `<section class="panel">
    <h2 class="panel__head">Giờ làm việc
      <span class="panel__note">MỘT lịch cho hạn SLA, câu báo khách ngoài giờ và quy tắc tự động "ngoài giờ"</span></h2>
    <p class="row__sub">${nguon}</p>
    <p class="row__sub">Bây giờ: <b>${tt.dang_trong_gio ? "trong giờ làm việc" : "ngoài giờ làm việc"}</b>${
      !tt.dang_trong_gio && tt.mo_ke_tiep ? ` — có người lại lúc ${esc(slaLuc(tt.mo_ke_tiep))}` : ""}.</p>
    ${canhGioRieng}
    <label class="field"><span>Giờ làm việc</span><select data-sla-lich-bat${sua ? "" : " disabled"}>
      <option value="1"${l.bat ? " selected" : ""}>Bật — có giờ mở / đóng cửa</option>
      <option value="0"${l.bat ? "" : " selected"}>Tắt — coi như trực 24/7</option></select></label>
    <div class="kntt-bang"><table>
      <thead><tr><th>Thứ</th><th></th><th>Mở</th><th>Đóng</th></tr></thead>
      <tbody>${ngay}</tbody></table></div>
    <p class="row__sub">Giờ Việt Nam. Đóng 21:00 nghĩa là 20:59 còn trong giờ. Đặt đóng 23:59 = hết ngày.</p>
    <h3 class="kntt-the__dau">Ngày nghỉ lễ</h3>
    <ul class="rows" data-sla-ds-le>${le || '<li class="empty">Chưa có ngày nghỉ lễ nào.</li>'}</ul>
    ${sua ? `<div class="form__row">
        <label class="field"><span>Ngày</span><input type="date" data-sla-le-moi></label>
        <label class="field"><span>Tên <em class="hint">tuỳ chọn</em></span><input type="text" maxlength="80" data-sla-le-ten-moi placeholder="vd Quốc khánh"></label>
        <button type="button" class="btn btn--sm" data-sla-them-le>Thêm ngày nghỉ</button>
      </div>
      <div class="rowbtns">
        <button type="button" class="btn btn--sm btn--go" data-sla-luu-lich>Lưu giờ làm việc</button>
        ${l.nguon === "csdl" ? '<button type="button" class="btn btn--sm btn--ghost" data-sla-bo-lich>Bỏ lịch, dùng .env</button>' : ""}
        <span class="row__sub" data-sla-kq-lich aria-live="polite"></span>
      </div>` : ""}
    <p class="row__sub">Thứ tự ưu tiên: lịch lưu ở đây → .env. Hội thoại đang chạy giữ hạn đã đặt; lịch mới áp cho hạn đặt sau khi lưu,
      còn câu báo ngoài giờ và quy tắc tự động đổi ngay (≤ 30 giây).</p>
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

async function ganSla(el) {
  const sua = coQuyen("dinh_tuyen.sua");
  const ve = async () => {
    let d, cs = [], kenh = [];
    try {
      d = await api("/sla/cau-hinh");
    } catch (e) {
      el.innerHTML = `<p class="empty">Không tải được cấu hình SLA: ${esc(e.message)}</p>`;
      return;
    }
    try { cs = (await api("/routing")).sla_policies || []; } catch { cs = []; }
    try { kenh = await api("/channel-accounts") || []; } catch { kenh = []; }
    el.innerHTML = slaVeMucTieu(d, sua) + slaVeChinhSach(cs, kenh, d.gio_rieng_chinh_sach, sua)
      + slaVeLich(d, sua);
    /* Ô ngưỡng chung / khi trễ (`#api-nhom-sla`) nằm NGOÀI phần bị thay
       (index.html) — vòng làm mới không nạp nó khi mô-đun đã gắn, nên nạp ở đây. */
    try { await loadCaiDatApi(); } catch (e) { toast(e.message, true); }
  };
  const ketQua = (sel, chu, loi = false) => {
    const o = el.querySelector(sel);
    if (o) { o.textContent = chu; o.classList.toggle("is-loi", loi); }
  };

  el.addEventListener("click", async (e) => {
    if (e.target.closest("[data-sla-luu-mt]")) {
      const muc_tieu = $$("[data-sla-mt]", el).map((r) => ({
        ma: r.dataset.slaMt,
        che_do: $("[data-sla-che-do]", r).value,
        nguong_canh_bao: $("[data-sla-nguong]", r).value === "" ? null : Number($("[data-sla-nguong]", r).value),
      }));
      try {
        await api("/sla/muc-tieu", { method: "PUT", body: JSON.stringify({ muc_tieu }) });
        toast("Đã lưu mục tiêu SLA.");
        await ve();
      } catch (err) { ketQua("[data-sla-kq-mt]", err.message, true); }
    } else if (e.target.closest("[data-sla-them-le]")) {
      const ngay = $("[data-sla-le-moi]", el).value;
      if (!ngay) { ketQua("[data-sla-kq-lich]", "Chọn ngày trước khi thêm.", true); return; }
      if ($(`[data-sla-le="${CSS.escape(ngay)}"]`, el)) { ketQua("[data-sla-kq-lich]", "Ngày ấy đã có.", true); return; }
      const ul = $("[data-sla-ds-le]", el);
      $(".empty", ul)?.remove();
      const li = document.createElement("li");
      li.dataset.slaLe = ngay;
      li.dataset.slaLeTen = $("[data-sla-le-ten-moi]", el).value.trim();
      li.innerHTML = `${esc(ngay)}${li.dataset.slaLeTen ? ` — ${esc(li.dataset.slaLeTen)}` : ""}
        <button type="button" class="btn btn--sm btn--ghost" data-sla-bo-le="${esc(ngay)}">Bỏ</button>
        <em class="hint">chưa lưu</em>`;
      ul.append(li);
      $("[data-sla-le-moi]", el).value = "";
      $("[data-sla-le-ten-moi]", el).value = "";
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
    const f = e.target.closest("[data-sla-form-cs]");
    if (!f) return;
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f).entries());
    /* Không gửi `business_hours`: máy chủ giữ giờ riêng đang lưu (nếu có).
       Ô phút chuyển giao trống = null: chính sách không đặt mục tiêu ấy. */
    const than = {
      account_id: d.account_id || null, priority: d.priority,
      first_response_minutes: Number(d.first_response_minutes),
      handover_response_minutes: d.handover_response_minutes === "" ? null : Number(d.handover_response_minutes),
      resolution_minutes: Number(d.resolution_minutes), active: true,
    };
    const nut = f.querySelector("button[type=submit]");
    nut.disabled = true;
    try {
      await api("/routing/sla-policies", { method: "PUT", body: JSON.stringify(than) });
      toast("Đã lưu hạn SLA.");
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

window.GAN_TAB["cc-sla"] = (el) => ganSla(el);
