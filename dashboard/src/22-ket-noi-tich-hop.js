/* ---------------- Kết nối & Tích hợp ----------------
 *
 * Một thẻ cho MỖI dịch vụ (ERPNext, GHN, GHTK) và mỗi plugin kênh: trường
 * cấu hình, nút Kiểm tra kết nối, webhook và lịch sử nhận — cùng một chỗ.
 * Người vận hành hỏi "GHN có chạy không", không hỏi "webhook có chạy không".
 *
 * Luật trạng thái (Chưa cấu hình / Chưa kiểm tra / Thành công / Lỗi) nằm ở
 * MÁY CHỦ (agent/ket_noi_tich_hop.py). Ở đây chỉ vẽ.
 *
 * Gắn vào khung tab qua `GAN_TAB['cc-ket-noi']`. Khi khung chưa có, phần tử
 * `[data-gan-tab]` trong index.html được gắn bằng `ganTabTam()`.
 *
 * KHÔNG nằm trong vòng làm mới 6 giây: ô bí mật đang dán dở mà bị dựng lại
 * là khoá mất trắng, rồi người ta bấm Lưu và tưởng đã lưu. Chỉ dựng lại khi
 * người dùng thao tác (Lưu, Kiểm tra, Tải lại).
 */
window.GAN_TAB = window.GAN_TAB || {};

const KNTT_MAU = { thanh_cong: "xanh", loi: "do", chua_kiem_tra: "vang", chua_cau_hinh: "tat", tat: "tat" };

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

/* Thẻ dịch vụ dùng chung cho ERPNext/GHN/GHTK và cả thẻ AI (23-ai-co-ban.js). */
function knttTheDichVu(dv, { boTruong = false } = {}) {
  const wh = dv.webhook;
  const webhook = wh ? `
    <details class="kntt-webhook">
      <summary>Webhook nhận vào ${knttThongKeNgan(wh.thong_ke)}</summary>
      <p><code>${esc(wh.url)}</code></p>
      <p class="row__sub">${esc(wh.xac_minh)}</p>
      ${wh.bi_mat ? `<p class="row__sub">Bí mật URL: ${wh.bi_mat.da_dat ? "đã đặt " + esc(wh.bi_mat.hien)
        : "<b>CHƯA ĐẶT — mọi webhook đang bị từ chối</b>"}. ${esc(wh.lay_bi_mat || "")}</p>` : ""}
      <p class="row__sub">Sự kiện: ${wh.su_kien.map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}
      <div class="rowbtns"><button type="button" class="btn btn--sm" data-kntt-lswh="${esc(dv.ma)}">Lịch sử nhận</button></div>
      <div data-kntt-lswh-o="${esc(dv.ma)}"></div>
    </details>` : "";
  return `<section class="kntt-the" data-kntt-dv="${esc(dv.ma)}">
    <h3 class="kntt-the__dau">${dv.kiem_duoc ? knttCham(dv.trang_thai, dv.nhan_trang_thai) : ""}
      <b>${esc(dv.ten)}</b> ${dv.kiem_duoc ? `<span class="tag tag--${
        { thanh_cong: "auto", loi: "halt", chua_kiem_tra: "assist" }[dv.trang_thai] || "plain"}">${
        esc(dv.nhan_trang_thai)}</span>` : ""}</h3>
    <p class="row__sub">${esc(dv.mo_ta)}</p>
    ${dv.ghi_chu.map((g) => `<p class="row__sub kntt-ghichu">${esc(g)}</p>`).join("")}
    ${dv.thieu.length ? `<p class="row__sub"><b>Còn thiếu:</b> ${dv.thieu.map(esc).join(", ")}</p>` : ""}
    ${boTruong ? "" : `<div class="kntt-truong">${dv.truong.map(knttO).join("")}</div>`}
    <div class="rowbtns">
      ${dv.kiem_duoc ? `<button type="button" class="btn btn--sm" data-kntt-kiem="${esc(dv.ma)}">Kiểm tra kết nối</button>` : ""}
      <button type="button" class="btn btn--sm btn--go" data-kntt-luu="${esc(dv.ma)}">Lưu</button>
      <span class="row__sub" data-kntt-kq="${esc(dv.ma)}" aria-live="polite"></span>
    </div>
    ${dv.kiem_duoc ? knttKetQuaKiem(dv.kiem) : ""}
    ${webhook}
  </section>`;
}

function knttThongKeNgan(tk) {
  if (!tk || !tk.lan_cuoi) return '<span class="row__sub">— chưa nhận</span>';
  return `<span class="row__sub">— gần nhất ${esc(knttLuc(tk.lan_cuoi))}${
    tk.loi_24h ? `, <b>${esc(tk.loi_24h)} lỗi/24 giờ</b>` : ""}</span>`;
}

/* ---------------- plugin kênh ---------------- */

function knttTaiKhoan(p, t) {
  const wh = t.webhook || {};
  const fb = t.an_binh_luan_co_sdt
    ? `<label class="field kntt-fb"><span>Tự ẩn bình luận có số điện thoại</span>
        <select data-kntt-fb="${esc(t.id)}">
          <option value="chung"${t.an_binh_luan_co_sdt.rieng ? "" : " selected"}>Theo cấu hình chung (đang ${
            t.an_binh_luan_co_sdt.chung === "bat" ? "bật" : "tắt"})</option>
          <option value="bat"${t.an_binh_luan_co_sdt.rieng === "bat" ? " selected" : ""}>Bật cho Trang này</option>
          <option value="tat"${t.an_binh_luan_co_sdt.rieng === "tat" ? " selected" : ""}>Tắt cho Trang này</option>
        </select></label>` : "";
  const kiem = t.kiem
    ? `<span class="row__sub">Xác minh gần nhất ${esc(knttLuc(t.kiem.luc))}: ${esc(t.kiem.code || "")}${
      t.kiem.ly_do ? " — " + esc(t.kiem.ly_do) : ""}</span>` : '<span class="row__sub">Chưa xác minh lần nào.</span>';
  return `<div class="kn-dong kntt-tk">
    ${knttCham(t.trang_thai, t.nhan_trang_thai)}
    <span><b>${esc(t.display_name)}</b><small>${esc(t.nhan_trang_thai)} · ${esc(t.status)}</small></span>
    <span>${kiem}<br>${knttThongKe(wh)}${t.url_webhook ? `<br><span class="row__sub">Webhook: <code>${esc(t.url_webhook)}</code></span>` : ""}${fb}</span>
    <span class="rowbtns">
      ${p.ke_thua ? "" : `<button type="button" class="btn btn--sm" data-kntt-xacminh="${esc(t.id)}">Kiểm tra kết nối</button>`}
      <button type="button" class="btn btn--sm" data-kntt-bat="${esc(t.id)}" data-bat="${t.bat ? "0" : "1"}">${t.bat ? "Tắt" : "Bật"}</button>
      <button type="button" class="btn btn--sm btn--ghost" data-kntt-lstk="${esc(t.id)}">Lịch sử webhook</button>
    </span>
    <div class="kntt-lstk" data-kntt-lstk-o="${esc(t.id)}"></div>
  </div>`;
}

function knttPlugin(p) {
  const wh = p.webhook;
  return `<section class="kntt-the">
    <h3 class="kntt-the__dau"><b>${esc(p.ten)}</b>${p.ke_thua ? ' <span class="tag tag--plain">kênh cũ</span>' : ""}
      <span class="row__sub">${esc(p.tai_khoan.length)} tài khoản · nối: ${esc(p.cach_noi)}</span></h3>
    <p class="kntt-khanang">${p.kha_nang.map((k) =>
      `<span class="tag ${k.co ? "tag--auto" : "tag--plain"}" title="${k.co ? "Có" : "Chưa hỗ trợ"}">${k.co ? "✓" : "✗"} ${esc(k.nhan)}</span>`).join(" ")}</p>
    ${wh ? `<details class="kntt-webhook"><summary>Webhook ${knttThongKeNgan(wh.thong_ke)}</summary>
      ${wh.theo_tai_khoan ? '<p class="row__sub">Mỗi tài khoản một địa chỉ — xem ở từng dòng bên dưới.</p>'
        : `<p><code>${esc(wh.url)}</code></p>`}
      <p class="row__sub">${esc(wh.xac_minh)}</p>
      <p class="row__sub">Sự kiện: ${wh.su_kien.map(esc).join(", ")}</p>
      ${knttThongKe(wh.thong_ke)}</details>`
      : '<p class="row__sub">Không dùng webhook.</p>'}
    ${p.tai_khoan.length ? p.tai_khoan.map((t) => knttTaiKhoan(p, t)).join("")
      : '<p class="empty">Chưa nối tài khoản nào — nối ở màn Kết nối.</p>'}
  </section>`;
}

function knttLichSu(ls) {
  const HD = { dat: "đặt", xoa: "bỏ (về .env)", doi_credential: "đổi thông tin đăng nhập", bat: "bật",
    tat: "tắt", doi_tuy_chon: "đổi tuỳ chọn", tao: "tạo", xoa_tai_khoan: "xoá tài khoản" };
  if (!ls.length) return '<p class="empty">Chưa có thay đổi nào được ghi.</p>';
  return ls.map((x) => `<div class="row"><span class="row__flag row__flag--auto"></span>
    <span class="row__body"><span class="row__title">${esc(x.sua_boi)} ${esc(HD[x.hanh_dong] || x.hanh_dong)} ${
      esc(x.truong)}${x.bi_mat ? " (bí mật)" : ""}</span>
      <span class="row__sub">${esc(x.dich_vu)}${x.doi_tuong ? " · " + esc(x.doi_tuong) : ""}</span></span>
    <span class="row__side"><span class="row__time">${esc(knttLuc(x.sua_luc))}</span></span></div>`).join("");
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

/* Gắn MỘT lần các bộ nghe sự kiện cho một gốc; `napLai` dựng lại nội dung. */
function knttGanSuKien(goc, napLai) {
  if (goc._knttDaGan) return;
  goc._knttDaGan = true;
  goc.addEventListener("click", async (e) => {
    const b = e.target.closest("button");
    if (!b || !goc.contains(b)) return;
    const the = b.closest("[data-kntt-dv]");
    try {
      if (b.dataset.knttLuu) return await knttLuu(the, b.dataset.knttLuu, napLai);
      if (b.dataset.knttKiem) return await knttKiem(the, b.dataset.knttKiem, napLai);
      if (b.dataset.knttXoa) {
        if (!confirm(`Bỏ giá trị ${b.dataset.knttXoa} lưu trên dashboard và quay về giá trị trong .env?`)) return;
        await api(`/ket-noi/dich-vu/${encodeURIComponent(the.dataset.knttDv)}/${encodeURIComponent(b.dataset.knttXoa)}`, { method: "DELETE" });
        toast("Đã bỏ — đang dùng .env");
        return await napLai();
      }
      if (b.dataset.knttLswh) {
        const o = goc.querySelector(`[data-kntt-lswh-o="${b.dataset.knttLswh}"]`);
        o.innerHTML = knttBangWebhook(await api(`/ket-noi/webhook?dich_vu=${encodeURIComponent(b.dataset.knttLswh)}`));
        return;
      }
      if (b.dataset.knttLstk) {
        const o = goc.querySelector(`[data-kntt-lstk-o="${b.dataset.knttLstk}"]`);
        o.innerHTML = knttBangWebhook(await api(`/ket-noi/webhook?account_id=${encodeURIComponent(b.dataset.knttLstk)}`));
        return;
      }
      if (b.dataset.knttXacminh) {
        b.disabled = true;
        const r = await api(`/channel-accounts/${b.dataset.knttXacminh}/verify`, { method: "POST" });
        toast(r.ok ? "Kết nối thành công" : `Kết nối lỗi: ${r.code}`, !r.ok);
        return await napLai();
      }
      if (b.dataset.knttBat) {
        const bat = b.dataset.bat === "1";
        if (!bat && !confirm("Tắt tài khoản kênh này? Tin khách gửi tới sẽ không vào hệ thống cho tới khi bật lại.")) return;
        await api(`/channel-accounts/${b.dataset.knttBat}/${bat ? "enable" : "disable"}`, { method: "POST" });
        toast(bat ? "Đã bật tài khoản kênh" : "Đã tắt tài khoản kênh");
        return await napLai();
      }
      if (b.dataset.knttTaiLai) return await napLai();
    } catch (err) {
      toast(err.message, true);
    } finally {
      if (b.dataset.knttXacminh) b.disabled = false;
    }
  });
  goc.addEventListener("change", async (e) => {
    const s = e.target.closest("[data-kntt-fb]");
    if (!s) return;
    try {
      await api(`/ket-noi/kenh/${s.dataset.knttFb}/tuy-chon`, {
        method: "PUT", body: JSON.stringify({ an_binh_luan_co_sdt: s.value }),
      });
      toast("Đã lưu tuỳ chọn ẩn bình luận cho Trang này");
    } catch (err) { toast(err.message, true); await napLai(); }
  });
}

async function ganKetNoiTichHop(goc) {
  if (!goc) return;
  const napLai = async () => {
    let d, ls;
    try {
      [d, ls] = await Promise.all([api("/ket-noi"), api("/ket-noi/lich-su?gioi_han=30")]);
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được Kết nối &amp; Tích hợp: ${esc(e.message)}</p>`;
      return;
    }
    goc.innerHTML = `
      <h2 class="panel__head">Kết nối &amp; Tích hợp
        <span class="panel__note">${d.vault_san_sang ? "bí mật mã hoá trong CSDL, chỉ hiện 4 ký tự cuối"
          : "vault chưa cấu hình — chỉ xem được"}</span></h2>
      <p class="panel__note">Mỗi dịch vụ một thẻ: cấu hình, kiểm tra kết nối thật, webhook nhận vào.
        Bấm <b>Kiểm tra kết nối</b> trước hoặc sau khi <b>Lưu</b> — kiểm chạy bằng đúng thứ bạn vừa gõ.
        <button type="button" class="btn btn--sm btn--ghost" data-kntt-tai-lai="1">Tải lại</button></p>
      <h3 class="kntt-nhom">Dịch vụ tích hợp</h3>
      ${d.dich_vu.map((dv) => knttTheDichVu(dv)).join("")}
      <h3 class="kntt-nhom">Kênh nhắn tin (plugin)</h3>
      ${d.kenh.map(knttPlugin).join("")}
      <h3 class="kntt-nhom">Lịch sử thay đổi cấu hình</h3>
      <p class="row__sub">Ai, lúc nào, trường nào — không bao giờ ghi giá trị.</p>
      <div class="rows">${knttLichSu(ls)}</div>`;
  };
  knttGanSuKien(goc, napLai);
  await napLai();
}

window.GAN_TAB["cc-ket-noi"] = (el) => ganKetNoiTichHop(el);

/* Gắn tạm khi khung tab chưa có: mỗi `[data-gan-tab]` trong màn đang mở
 * được gắn MỘT lần (dựng lại mỗi 6 giây là xoá khoá đang dán dở). */
function ganTabTam() {
  $$(".view.is-active [data-gan-tab]").forEach((el) => {
    if (el.dataset.daGan) return;
    const gan = window.GAN_TAB[el.dataset.ganTab];
    if (!gan) return;
    el.dataset.daGan = "1";
    gan(el);
  });
}
