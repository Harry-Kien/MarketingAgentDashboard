/* ---------------- SLA → khu "Thứ tự áp dụng & Thử tính" (UX-15-03) ----------------
 *
 * Bốn nguồn cấu hình cùng quyết định MỘT hạn: lịch (dashboard → .env), đồng
 * hồ của mục tiêu (dashboard → .env), số phút (kênh × mức, lui về "mọi
 * kênh" / mức "thường"), giờ riêng của chính sách (chỉ khi chưa có lịch).
 * Đọc riêng từng khối thì không ai đoán được hạn thật — nên khu này nói
 * thứ tự ấy ra, kèm trạng thái ĐANG dùng nguồn nào, và cho thử một tình huống.
 *
 * Máy tính KHÔNG tính gì ở đây: nó gọi `/api/sla/xem-truoc-han`, nơi máy chủ
 * chạy chính biểu thức SQL đặt hạn thật. Chép công thức lịch sang JS là có
 * hai bản, và bản ở màn hình là bản không ai kiểm.
 */

function slaVeThuTu(d, cs) {
  const l = d.lich;
  const coLich = l.nguon === "csdl";
  const dongHo = d.muc_tieu.map((m) => `${esc(m.ten)}: <b>${esc(d.che_do[m.che_do] || m.che_do)}</b>`
    + ` <i>(${esc(slaNguon(m.nguon_che_do))})</i>`).join(" · ");
  const coKenhRieng = cs.some((p) => p.account_id);
  const dang = (chu) => `<span class="tag tag--auto">${chu}</span>`;
  const muc = [
    ["Giờ mở cửa", `Lịch lưu ở khu <b>Giờ làm việc</b> → nếu chưa lưu thì <code>.env</code> (GIO_LAM_VIEC_*).
      Tắt "tính theo giờ mở cửa" = mọi đồng hồ chạy 24/7.`,
      dang(coLich ? (l.bat ? "đang dùng lịch dashboard" : "lịch dashboard đang TẮT — trực 24/7") : "đang dùng .env")],
    ["Đồng hồ của từng mục tiêu", `Chọn ở khu <b>Mục tiêu &amp; Thời hạn</b> → nếu chưa chọn thì
      <code>.env</code> SLA_THEO_GIO_LAM_VIEC (một công tắc cho cả ba).`, `<span class="sla-mo-ta">${dongHo}</span>`],
    ["Số phút cho phép", `Chính sách của <b>đúng kênh</b> thắng chính sách <b>mọi kênh</b>; <b>đúng mức ưu tiên</b>
      thắng mức <b>thường</b> (thiếu mức ấy thì dùng mức thường). Không có chính sách nào → hội thoại không có hạn.`,
      dang(`${cs.length} chính sách${coKenhRieng ? ", có chính sách riêng theo kênh" : ""}`)],
    ["Giờ riêng của một chính sách", `Chỉ còn tác dụng khi <b>chưa</b> lưu lịch trên dashboard. Đã có lịch chung thì
      lịch chung là nguồn duy nhất.`,
      dang(d.gio_rieng_chinh_sach.con_tac_dung ? "đang có tác dụng" : "không còn tác dụng")],
    ["Ngưỡng cảnh báo", "Ngưỡng riêng của mục tiêu → ngưỡng chung → 80%.",
      dang(`chung ${esc(d.nguong_chung)}%`)],
    ["Khi nào áp dụng", `Hội thoại mới bắt đầu ở mức <b>thường</b>. Đổi ưu tiên chỉ <b>rút ngắn</b> hạn đang chạy
      (tính từ lúc đổi). Lịch và số phút mới áp cho hạn đặt SAU khi lưu — hội thoại đang chạy giữ hạn cũ.`, ""],
  ];
  return `<details class="panel nang-cao sla-thu-tu-gop">
    <summary class="panel__head sla-thu-tu-gop__dau">
      <span>Thứ tự áp dụng cấu hình SLA
        <span class="panel__note">6 quy tắc ưu tiên — bấm để xem chi tiết nguồn đang dùng</span></span>
    </summary>
    <ol class="sla-thu-tu">${muc.map(([ten, mo, tt]) => `<li>
      <div class="sla-thu-tu__dau"><b>${ten}</b> ${tt}</div>
      <p class="sla-mo-ta">${mo}</p></li>`).join("")}</ol>
  </details>`;
}

function slaGioVNHienTai() {
  /* Ô datetime-local không có múi giờ; máy chủ đọc nó là giờ Việt Nam —
     nên giá trị mặc định cũng phải là giờ VN, dù máy người xem đặt múi khác. */
  return new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 16);
}

function slaVeThuTinh(kenh) {
  const oKenh = '<option value="">mọi kênh (chính sách chung)</option>' + kenh.map((k) =>
    `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`).join("");
  return `<section class="panel">
    <h2 class="panel__head">Thử tính thời hạn SLA
      <span class="panel__note">tính bằng đúng phép tính đặt hạn thật trên máy chủ — không lưu dữ liệu</span></h2>
    <form class="form sla-thu-form" data-sla-form-thu>
      <div class="sla-thu-hang">
        <label class="field"><span>Kênh</span><select name="account_id">${oKenh}</select></label>
        <label class="field"><span>Mức ưu tiên</span><select name="uu_tien">${Object.entries(SLA_UU_TIEN).map(([k, v]) =>
    `<option value="${k}">${v}</option>`).join("")}</select></label>
        <label class="field"><span>Thời điểm bắt đầu (giờ VN)</span>
          <input type="datetime-local" name="bat_dau" value="${slaGioVNHienTai()}" required></label>
        <button type="submit" class="btn btn--primary sla-thu-nut">Tính hạn</button>
      </div>
    </form>
    <div class="sla-thu-kq" data-sla-kq-thu aria-live="polite">
      <div class="sla-thu-goi-y">
        <p class="sla-mo-ta">Chọn kênh, mức ưu tiên và thời điểm bắt đầu, rồi bấm <b>Tính hạn</b> để xem mốc hạn và thời điểm cảnh báo sớm. Thử một giờ tối thứ Bảy để thấy đồng hồ "giờ làm việc" dừng qua Chủ nhật.</p>
      </div>
    </div>
  </section>`;
}

function slaVeKetQuaThu(r) {
  const cs = r.chinh_sach;
  if (!cs) {
    return `<p class="dx-canh-bao">Không có chính sách SLA nào áp cho kênh và mức này — hội thoại sẽ <b>không có hạn</b>.
      Thêm thời hạn ở khu Mục tiêu &amp; Thời hạn.</p>`;
  }
  const nguon = `Áp chính sách <b>${cs.pham_vi === "kenh" ? "riêng của kênh" : "mọi kênh"}</b>, mức
    <b>${esc(SLA_UU_TIEN[cs.muc] || cs.muc)}</b>${cs.lui_ve_thuong
      ? ` <span class="tag tag--assist">không có mức ${esc(SLA_UU_TIEN[r.uu_tien] || r.uu_tien)} → dùng mức thường</span>` : ""}.`;
  const gr = cs.gio_rieng
    ? `<p class="sla-mo-ta">Chính sách có giờ riêng ${esc(cs.gio_rieng.bat_dau)}h–${esc(cs.gio_rieng.ket_thuc)}h —
      ${cs.gio_rieng_co_tac_dung ? "ĐANG áp thay lịch .env." : "không áp vì đã có lịch chung."}</p>` : "";
  const the = r.muc_tieu.map((m) => `<div class="sla-kq-the">
      <div class="sla-kq-the__dau">
        <b>${esc(m.ten)}</b>
        <span class="tag tag--plain">${m.che_do === "gio_lam_viec" ? "Giờ làm việc" : "24/7"}</span>
      </div>
      <div class="sla-kq-the__han">${m.han_chu ? esc(m.han_chu) : "Không đặt hạn"}</div>
      <dl class="sla-kq-the__meta">
        <div><dt>Cho phép</dt><dd>${m.phut ? esc(slaPhut(m.phut)) : "không đặt"}</dd></div>
        <div><dt>Chờ thực tế</dt><dd>${m.cho_thuc_phut == null ? "—" : esc(slaPhut(m.cho_thuc_phut))}</dd></div>
        <div><dt>Cảnh báo sớm</dt><dd>${m.canh_bao_sau_phut == null ? "—"
      : `sau ${esc(slaPhut(m.canh_bao_sau_phut))} (${esc(m.nguong_phan_tram)}%)`}</dd></div>
      </dl>
      <p class="sla-mo-ta">${esc(m.tu)}</p>
    </div>`).join("");
  return `<div class="sla-thu-tomtat">
      <div class="sla-thu-tomtat__hang">
        <span>Bắt đầu: <b>${esc(r.bat_dau_chu)}</b></span>
        <span class="tag ${r.lich.dang_mo_luc_bat_dau ? "tag--auto" : "tag--assist"}">${r.lich.dang_mo_luc_bat_dau ? "Trong giờ làm việc" : "Ngoài giờ làm việc"}</span>
      </div>
      <p class="sla-mo-ta">${nguon}</p>${gr}
    </div>
    <div class="sla-kq-luoi">${the}</div>
    <p class="sla-mo-ta">"Chờ thực tế" là thời gian đồng hồ treo tường từ lúc bắt đầu tới hạn — dài hơn thời gian cho phép khi đồng hồ SLA dừng ngoài giờ.</p>`;
}

async function slaThuTinh(f, el) {
  const v = Object.fromEntries(new FormData(f).entries());
  const q = new URLSearchParams({ uu_tien: v.uu_tien, bat_dau: v.bat_dau });
  if (v.account_id) q.set("account_id", v.account_id);
  const o = $("[data-sla-kq-thu]", el);
  const nut = f.querySelector("button[type=submit]");
  nut.disabled = true;
  o.innerHTML = '<p class="sla-mo-ta">Đang tính…</p>';
  try {
    o.innerHTML = slaVeKetQuaThu(await api(`/sla/xem-truoc-han?${q}`));
  } catch (err) {
    o.innerHTML = `<p class="dx-canh-bao">Không tính được: ${esc(err.message)}</p>`;
  } finally { nut.disabled = false; }
}
