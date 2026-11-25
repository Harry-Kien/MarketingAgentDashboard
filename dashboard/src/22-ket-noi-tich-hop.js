/* ---------------- Kết nối & Tích hợp: hệ thống ngoài ----------------
 *
 * Khu vực "Tích hợp hệ thống ngoài" của tab: ERPNext, GHN, GHTK — mỗi dịch
 * vụ MỘT bảng riêng, đóng sẵn, chỉ mở bảng người dùng chọn (UX-08-04). Trước
 * đây mười bốn ô của ba dịch vụ trải dọc một trang, xen giữa là webhook và
 * plugin kênh; người ta sửa nhầm ô GHTK khi tưởng đang ở GHN.
 *
 * Luật trạng thái (Chưa cấu hình / Chưa kiểm tra / Thành công / Lỗi) nằm ở
 * MÁY CHỦ (agent/ket_noi_tich_hop.py). Ở đây chỉ vẽ.
 *
 * Plugin kênh KHÔNG còn vẽ ở đây: thông tin từng tài khoản của nó (xác minh
 * gần nhất, webhook, tuỳ chọn Trang) gộp vào đúng dòng tài khoản ở khu vực
 * Kênh (18a-ket-noi-tai-khoan.js) qua `state.knttTk` / `state.knttKenh` — một
 * tài khoản, một chỗ (UX-08-02). Lịch sử cấu hình sang khu vực Lịch sử
 * (22b-ket-noi-lich-su.js).
 *
 * Gắn vào khung tab qua `GAN_TAB['cc-ket-noi']` (01b-dieu-huong.js `ganKhe`).
 *
 * KHÔNG nằm trong vòng làm mới 6 giây: ô bí mật đang dán dở mà bị dựng lại
 * là khoá mất trắng, rồi người ta bấm Lưu và tưởng đã lưu. Chỉ dựng lại khi
 * người dùng thao tác (Lưu, Kiểm tra, Tải lại).
 */
window.GAN_TAB = window.GAN_TAB || {};

const KNTT_MAU = { thanh_cong: "xanh", loi: "do", chua_kiem_tra: "vang", chua_cau_hinh: "tat", tat: "tat" };
/* Bốn trạng thái dịch vụ vẽ bằng CÙNG bộ nhãn màu với trạng thái tài khoản
 * kênh (UX-08-06): người đọc học một bảng màu, không phải hai. */
const KNTT_TT = { thanh_cong: "hoat_dong", loi: "loi", chua_kiem_tra: "canh-bao", chua_cau_hinh: "chua_ket_noi" };

function knttCham(tt, nhan) {
  return `<span class="kn-cham kn-cham--${KNTT_MAU[tt] || "tat"}" title="${esc(nhan || "")}" aria-hidden="true"></span>`;
}

function knttLuc(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN") : "—";
}

/* Ô nhập của một trường. Ô BÍ MẬT là password và KHÔNG có value: máy chủ
 * chỉ gửi bốn ký tự cuối, nên mọi chữ trong ô là người dùng vừa gõ. */
function knttO(m) {
  const nhan = `${esc(m.nhan)}${m.y_nghia ? ` <em class="hint">${esc(m.y_nghia)}</em>` : ""}`;
  let o;
  if (m.chon && m.chon.length) {
    o = `<select data-kntt-khoa="${esc(m.khoa)}">${m.chon.map((c) =>
      `<option value="${esc(c)}"${c === m.hien ? " selected" : ""}>${esc(c)}</option>`).join("")}</select>`;
  } else if (m.bi_mat) {
    o = `<input type="password" autocomplete="off" data-kntt-khoa="${esc(m.khoa)}"
      placeholder="${m.da_dat ? `đã đặt ${esc(m.hien)} — dán giá trị mới để thay` : "chưa đặt — dán vào đây"}">`;
  } else {
    o = `<input type="text" autocomplete="off" data-kntt-khoa="${esc(m.khoa)}" value="${esc(m.hien || "")}">`;
  }
  const nguon = { csdl: "lưu trên dashboard", env: "đang dùng .env", trong: "chưa đặt" }[m.nguon] || "";
  const xoa = m.nguon === "csdl"
    ? ` <button type="button" class="btn btn--sm btn--ghost" data-kntt-xoa="${esc(m.khoa)}"
         title="Bỏ giá trị lưu trên dashboard, quay về .env">Bỏ, dùng .env</button>` : "";
  const sua = m.sua_boi ? ` · sửa bởi ${esc(m.sua_boi)} lúc ${esc(knttLuc(m.sua_luc))}` : "";
  return `<label class="field"><span>${nhan}</span>${o}</label>
    <span class="row__sub">${esc(nguon)}${sua}${xoa}</span>`;
}

function knttThongKe(tk) {
  if (!tk || !tk.lan_cuoi) return '<span class="row__sub">Chưa nhận lời gọi nào (trong 30 ngày).</span>';
  const loi = tk.loi_cuoi
    ? `<br><span class="row__sub">Lỗi gần nhất ${esc(knttLuc(tk.loi_cuoi.luc))}${
      tk.loi_cuoi.ma_http ? ` (HTTP ${esc(tk.loi_cuoi.ma_http)})` : ""}: ${esc(tk.loi_cuoi.loi || "")}</span>` : "";
  return `<span class="row__sub">Nhận gần nhất: ${esc(knttLuc(tk.lan_cuoi))} · 24 giờ: ${
    esc(tk.dem_24h ?? 0)} lời gọi, ${esc(tk.loi_24h ?? 0)} lỗi${
    tk.tb_ms != null ? ` · xử lý TB ${esc(tk.tb_ms)} ms` : ""}</span>${loi}`;
}

function knttKetQuaKiem(k) {
  if (!k) return '<span class="row__sub">Chưa kiểm lần nào.</span>';
  const cu = k.con_hieu_luc ? "" : " — <b>đã đổi cấu hình sau lần kiểm này</b>, bấm Kiểm tra lại";
  return `<span class="row__sub">Kiểm lần cuối ${esc(knttLuc(k.luc))}${k.boi ? ` bởi ${esc(k.boi)}` : ""}: ${
    k.ok ? "✓" : "✗"} ${esc(k.chi_tiet)}${cu}</span>`;
}

function knttThongKeNgan(tk) {
  if (!tk || !tk.lan_cuoi) return '<span class="row__sub">— chưa nhận</span>';
  return `<span class="row__sub">— gần nhất ${esc(knttLuc(tk.lan_cuoi))}${
    tk.loi_24h ? `, <b>${esc(tk.loi_24h)} lỗi/24 giờ</b>` : ""}</span>`;
}

/* Bảng đang mở. MỘT lúc một bảng: mở GHTK thì GHN đóng lại, để không bao giờ
 * có hai bộ ô cùng nhãn "Token" trên màn hình. Sống qua lần dựng lại sau
 * Lưu/Kiểm tra — đóng sập ngay sau khi bấm Lưu là mất chỗ đang làm. */
let knttDvMo = null;

/* Một dịch vụ = một bảng gập. Đầu bảng chỉ có điều người vận hành cần biết
 * lúc lướt qua: tên, việc của nó, MỘT trạng thái. Webhook, bí mật URL, sự
 * kiện là chi tiết kỹ thuật — nằm trong "Chi tiết nâng cao" (UX-08-03). */
function knttTheDichVu(dv) {
  const mo = knttDvMo === dv.ma;
  const wh = dv.webhook;
  const webhook = wh ? `
    <details class="knh-nangcao kntt-webhook">
      <summary>Chi tiết nâng cao: webhook nhận vào ${knttThongKeNgan(wh.thong_ke)}</summary>
      <p><code>${esc(wh.url)}</code></p>
      <p class="row__sub">${esc(wh.xac_minh)}</p>
      ${wh.bi_mat ? `<p class="row__sub">Bí mật URL: ${wh.bi_mat.da_dat ? "đã đặt " + esc(wh.bi_mat.hien)
        : "<b>CHƯA ĐẶT — mọi webhook đang bị từ chối</b>"}. ${esc(wh.lay_bi_mat || "")}</p>` : ""}
      <p class="row__sub">Sự kiện: ${wh.su_kien.map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}
      <div class="rowbtns"><button type="button" class="btn btn--sm" data-kntt-lswh="${esc(dv.ma)}">Lịch sử nhận</button></div>
      <div data-kntt-lswh-o="${esc(dv.ma)}"></div>
    </details>` : "";
  return `<section class="kntt-the knh-dv${mo ? " is-mo" : ""}" data-kntt-dv="${esc(dv.ma)}">
    <button type="button" class="knh-dv__dau" data-knh-dv-mo="${esc(dv.ma)}" aria-expanded="${mo ? "true" : "false"}"
      aria-controls="knh-dv-${esc(dv.ma)}">
      <span class="knh-dv__ten"><b>${esc(dv.ten)}</b><small>${esc(dv.mo_ta)}</small></span>
      ${dv.kiem_duoc ? `<span class="knh-tt knh-tt--${KNTT_TT[dv.trang_thai] || "chua_ket_noi"}">${esc(dv.nhan_trang_thai)}</span>` : ""}
      <span class="knh-dv__mo">${mo ? "Đóng" : "Mở cấu hình"}</span>
    </button>
    <div class="knh-dv__than" id="knh-dv-${esc(dv.ma)}"${mo ? "" : " hidden"}>
      ${dv.ghi_chu.length ? `<ul class="knh-ghi-chu">${dv.ghi_chu.map((g) => `<li>${esc(g)}</li>`).join("")}</ul>` : ""}
      ${dv.thieu.length ? `<p class="knh-thieu"><b>Còn thiếu:</b> ${dv.thieu.map(esc).join(", ")}</p>` : ""}
      <div class="kntt-truong">${dv.truong.map(knttO).join("")}</div>
      <div class="knh-nhom-ds knh-nhom-ds--ngang">
        ${dv.kiem_duoc ? knNhomNut("Kiểm tra", "Chạy bằng giá trị đang gõ (ô trống = giá trị đang lưu). Không lưu gì.",
          `<button type="button" class="btn btn--sm" data-kntt-kiem="${esc(dv.ma)}">Kiểm tra kết nối</button>`) : ""}
        ${knNhomNut("Lưu", "Chỉ lưu ô bạn đã sửa. Có hiệu lực ngay, không cần khởi động lại.",
          `<button type="button" class="btn btn--sm btn--primary" data-kntt-luu="${esc(dv.ma)}">Lưu thay đổi</button>`)}
      </div>
      <p class="row__sub" data-kntt-kq="${esc(dv.ma)}" aria-live="polite"></p>
      ${dv.kiem_duoc ? knttKetQuaKiem(dv.kiem) : ""}
      ${webhook}
    </div>
  </section>`;
}

/* Kênh CŨ (kế thừa, khoá trong .env): còn tài khoản thì vẫn phải
 * thấy được, nhưng gập riêng ở cuối khu vực Kênh — không chen giữa kênh mới. */
function knttKenhCu(ds) {
  if (!ds.length) return "";
  return `<details class="panel knh-kenh-cu" data-kn-mo="kenh-cu"${knMo("kenh-cu")}>
    <summary class="panel__head">Kênh cũ (kế thừa) <span class="panel__note">${ds.length} plugin · cấu hình trong .env</span></summary>
    <div class="rows">${ds.map((p) => `<div class="row"><span class="row__flag row__flag--assist"></span>
      <span class="row__body"><span class="row__title">${esc(p.ten)}</span>
        <span class="row__sub">${esc(p.cach_noi)} · ${p.tai_khoan.map((t) => esc(t.display_name)).join(", ") || "không có tài khoản"}</span></span></div>`).join("")}</div>
  </details>`;
}

function knttBangWebhook(d) {
  const goi = d.goi_vao.map((r) => `<tr><td>${esc(knttLuc(r.nhan_luc))}</td><td>${esc(r.phuong_thuc)}</td>
    <td>${esc(r.ma_http)}</td><td>${esc(r.thoi_gian_ms)} ms</td><td>${esc(r.loi || "")}</td></tr>`).join("");
  const tin = (d.tin_da_nhan || []).map((r) => `<tr><td>${esc(knttLuc(r.received_at))}</td><td>${esc(r.status)}</td>
    <td>${esc(r.attempts)}</td><td>${r.xu_ly_ms != null ? esc(r.xu_ly_ms) + " ms" : "—"}</td><td>${esc(r.last_error || "")}</td></tr>`).join("");
  return `<div class="kntt-bang">
    <p class="row__sub"><b>Lời gọi vào</b> (cả lời bị từ chối)</p>
    ${goi ? `<table><thead><tr><th>Lúc</th><th>PT</th><th>HTTP</th><th>Thời gian</th><th>Lỗi</th></tr></thead><tbody>${goi}</tbody></table>`
      : '<p class="empty">Chưa có lời gọi nào.</p>'}
    ${d.tin_da_nhan ? `<p class="row__sub"><b>Tin đã nhận vào hộp thư</b></p>
    ${tin ? `<table><thead><tr><th>Lúc</th><th>Trạng thái</th><th>Lần thử</th><th>Xử lý</th><th>Lỗi</th></tr></thead><tbody>${tin}</tbody></table>`
      : '<p class="empty">Chưa có tin nào.</p>'}` : ""}
  </div>`;
}

/* ---------------- gom giá trị, lưu, kiểm ---------------- */

/* Gom ô trong MỘT thẻ. `chiDaSua`: khi Lưu chỉ gửi ô người dùng đã đổi —
 * gửi cả ô có sẵn giá trị máy chủ là ghi lại y nguyên và đếm "đã lưu" sai. */
function knttGom(the, chiDaSua) {
  const ra = {};
  $$("[data-kntt-khoa]", the).forEach((o) => {
    if (o.closest("[hidden]")) return;
    if (chiDaSua && !_oDaSua(o)) return;
    const v = (o.value || "").trim();
    if (v) ra[o.dataset.knttKhoa] = v;
  });
  return ra;
}

async function knttLuu(the, ma, napLai) {
  const kq = the.querySelector(`[data-kntt-kq="${ma}"]`);
  const gia_tri = knttGom(the, true);
  if (!Object.keys(gia_tri).length) {
    toast("Chưa đổi ô nào — nhập giá trị rồi bấm Lưu.", true);
    return;
  }
  try {
    const r = await api(`/ket-noi/dich-vu/${encodeURIComponent(ma)}`, { method: "PUT", body: JSON.stringify({ gia_tri }) });
    if (r.hong.length) {
      const tb = `Lưu được ${r.da_luu.length}, hỏng ${r.hong.length}: ` + r.hong.map((h) => h.loi).join("; ");
      toast(tb, true);
      if (kq) kq.textContent = tb;
      // Ô ĐÃ lưu thì xoá chữ để không trông như chưa lưu; ô hỏng để nguyên cho sửa tiếp.
      r.da_luu.forEach((k) => { const o = the.querySelector(`input[type=password][data-kntt-khoa="${k}"]`); if (o) o.value = ""; });
      if (r.da_luu.length) await napLai();
      return;
    }
    toast(`Đã lưu ${r.da_luu.length} trường — có hiệu lực ngay. Bấm Kiểm tra kết nối để xác nhận.`);
    await napLai();
  } catch (e) { toast(e.message, true); }
}

async function knttKiem(the, ma, napLai) {
  const kq = the.querySelector(`[data-kntt-kq="${ma}"]`);
  if (kq) kq.textContent = "đang kiểm…";
  try {
    const r = await api(`/ket-noi/dich-vu/${encodeURIComponent(ma)}/kiem-tra`, {
      method: "POST", body: JSON.stringify({ gia_tri: knttGom(the, true) }),
    });
    const ghi = r.dung_gia_tri_luu ? "" : " (kiểm bằng giá trị CHƯA LƯU — kết quả không ghi vào trạng thái)";
    const tb = (r.ok ? "✓ " : "✗ ") + r.chi_tiet + ghi;
    if (r.dung_gia_tri_luu) {
      await napLai();
      const kqMoi = document.querySelector(`[data-kntt-kq="${ma}"]`);
      if (kqMoi) kqMoi.textContent = tb;
    } else if (kq) kq.textContent = tb;
  } catch (e) {
    if (kq) kq.textContent = "";
    toast(e.message, true);
  }
}

/* Gắn MỘT lần các bộ nghe sự kiện cho một gốc; `napLai` dựng lại nội dung.
 * Dùng chung với thẻ AI (23-ai-co-ban.js). */
function knttGanSuKien(goc, napLai) {
  if (goc._knttDaGan) return;
  goc._knttDaGan = true;
  goc.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b || !goc.contains(b)) return;
    const the = b.closest("[data-kntt-dv]");
    try {
      if (b.dataset.knhDvMo) {
        // Mở bảng này, đóng bảng khác — không dựng lại để ô đang gõ dở ở
        // bảng khác (nếu có) không mất trước khi người dùng quyết định.
        const ma = b.dataset.knhDvMo;
        knttDvMo = knttDvMo === ma ? null : ma;
        $$("[data-knh-dv-mo]", goc).forEach((n) => {
          const on = n.dataset.knhDvMo === knttDvMo;
          n.setAttribute("aria-expanded", on ? "true" : "false");
          const mo = n.querySelector(".knh-dv__mo");
          if (mo) mo.textContent = on ? "Đóng" : "Mở cấu hình";
          n.closest(".knh-dv")?.classList.toggle("is-mo", on);
          const than = document.getElementById(n.getAttribute("aria-controls"));
          if (than) than.hidden = !on;
        });
        return;
      }
      if (b.dataset.knttLuu) return await knttLuu(the, b.dataset.knttLuu, napLai);
      if (b.dataset.knttKiem) return await knttKiem(the, b.dataset.knttKiem, napLai);
      if (b.dataset.knttXoa) {
        const ok = await hoiHop({
          tieu_de: `Bỏ giá trị ${b.dataset.knttXoa} lưu trên dashboard?`,
          phu: "Hệ thống quay về giá trị trong .env ngay lập tức — nếu .env không có giá trị này, dịch vụ sẽ ở trạng thái Chưa cấu hình cho tới khi nhập lại.",
          nut: "Bỏ, dùng .env", nguy_hiem: true,
        });
        if (!ok) return;
        await api(`/ket-noi/dich-vu/${encodeURIComponent(the.dataset.knttDv)}/${encodeURIComponent(b.dataset.knttXoa)}`, { method: "DELETE" });
        toast("Đã bỏ — đang dùng .env");
        return await napLai();
      }
      if (b.dataset.knttLswh) {
        const o = goc.querySelector(`[data-kntt-lswh-o="${b.dataset.knttLswh}"]`);
        o.innerHTML = knttBangWebhook(await api(`/ket-noi/webhook?dich_vu=${encodeURIComponent(b.dataset.knttLswh)}`));
        return;
      }
      if (b.dataset.knttTaiLai) return await napLai();
    } catch (err) {
      toast(err.message, true);
    }
  });
}

async function ganKetNoiTichHop(goc) {
  if (!goc) return;
  /* ganKhe() chèn khe gắn SAU .tab__goc, tức cuối tab — ngoài mọi khu vực.
     Chuyển nó vào khu vực "Tích hợp hệ thống ngoài" để knChonPhan ẩn/hiện nó
     như mọi phần khác; phần tử vẫn nằm trong #cc-ket-noi nên sự kiện
     `tab:hien` của khung tab vẫn tới. */
  const khuVuc = $("#kn-phan-tich-hop");
  if (khuVuc) { $("#kn-tich-hop-cho")?.remove(); khuVuc.append(goc); }
  // Lịch sử đọc bằng quyền riêng — không phụ thuộc /ket-noi nạp được hay không.
  knLsKhoiTao();
  const napLai = async () => {
    let d;
    try {
      d = await api("/ket-noi");
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được Tích hợp hệ thống ngoài: ${esc(e.message)}</p>`;
      return;
    }
    state.knttKenh = { theoKenh: Object.fromEntries(d.kenh.map((p) => [p.ma, p])) };
    state.knttTk = Object.fromEntries(d.kenh.flatMap((p) => p.tai_khoan.map((t) => [t.id, t])));
    goc.innerHTML = `<section class="panel knh-th">
      <h2 class="panel__head">Tích hợp hệ thống ngoài
        <span class="panel__note">${d.vault_san_sang ? "bí mật mã hoá trong CSDL, chỉ hiện 4 ký tự cuối"
          : "vault chưa cấu hình — chỉ xem được"}</span></h2>
      <p class="panel__note">Mỗi dịch vụ một bảng riêng — bấm vào dịch vụ cần sửa để mở.
        <b>Kiểm tra kết nối</b> chạy bằng đúng thứ bạn vừa gõ và không lưu gì; <b>Lưu thay đổi</b> có hiệu lực ngay.
        <button type="button" class="btn btn--sm btn--ghost" data-kntt-tai-lai="1">Tải lại</button></p>
      <div class="knh-dv-ds">${d.dich_vu.map((dv) => knttTheDichVu(dv)).join("")}</div>
    </section>`;
    knVe($("#kn-kenh-cu"), knttKenhCu(d.kenh.filter((p) => p.ke_thua && p.tai_khoan.length)));
    // Dòng tài khoản ở khu vực Kênh nhận thêm khả năng nền tảng và webhook.
    if (coQuyen("kenh.doc")) loadKetNoi().catch((e) => console.warn("Không vẽ lại được danh sách kênh:", e));
  };
  knttGanSuKien(goc, napLai);
  await napLai();
}

window.GAN_TAB["cc-ket-noi"] = (el) => ganKetNoiTichHop(el);
