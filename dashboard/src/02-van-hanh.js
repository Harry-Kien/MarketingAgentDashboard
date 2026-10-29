/* ================= Tin không gửi được, và khách chưa có chủ =================
 *
 * Hai ô trên dải chỉ số Ca trực đếm hai thứ này từ lâu. Không có gì phía
 * sau con số — và một con số không bấm được là một con số người ta học
 * cách bỏ qua.
 *
 * CLAUDE.md xếp "outbox bỏ cuộc sau 8 lần thử mà không báo ai" vào bảng
 * lỗi nghiêm trọng nhất: tin nhân viên chết, khách chờ mãi không có trả
 * lời. Đếm được là nửa đường; nửa còn lại là gửi lại được.
 */

function dongChet(j) {
  const loi = j.last_error ? String(j.last_error).slice(0, 160) : "không rõ lý do";
  return `<div class="row">
    <span class="row__flag row__flag--halt"></span>
    <div class="row__main">
      <b>${esc(j.account_name || j.channel || "kênh đã xoá")}</b>
      <span class="row__sub">${esc(loi)}</span>
      <span class="row__sub">${j.attempts}/${j.max_attempts} lần thử · ${clock(j.updated_at)}</span>
    </div>
    <div class="row__side">
      <span class="row__nut">
        <button type="button" class="btn btn--sm" data-guilai="${esc(j.id)}">Gửi lại</button>
        <button type="button" class="btn btn--sm btn--ghost" data-bochet="${esc(j.id)}">Bỏ qua</button>
      </span>
    </div>
  </div>`;
}

async function loadTinChet() {
  /* Quyền thiếu KHÔNG được làm đỏ cả trang: nhân viên thường không có
     `outbox.doc`, và với họ panel này đơn giản là không tồn tại. */
  if (!state.toiQuyen.has("outbox.doc")) return;
  let ds = [];
  try {
    ds = (await api("/outbox/jobs?status=dead&limit=50")).items || [];
  } catch { return; }
  $("#pnChet").classList.toggle("is-hidden", ds.length === 0);
  if (!ds.length) return;
  $("#dsChet").innerHTML = ds.map(dongChet).join("");
  $("#chetNote").textContent =
    `${ds.length} tin khách không nhận được · gửi lại hoặc bỏ qua`;
}

async function loadVoChu() {
  if (!state.toiQuyen.has("khach.doc")) return;
  let d = { khach: [] };
  try { d = await api("/khach-vo-chu?limit=50"); } catch { return; }
  const ds = d.khach || [];
  $("#pnVoChu").classList.toggle("is-hidden", ds.length === 0);
  if (!ds.length) return;
  $("#dsVoChu").innerHTML = ds.map((k) => `<div class="row">
    <span class="row__flag row__flag--assist"></span>
    <div class="row__main">
      <b>${esc(k.display_name || "khách chưa có tên")}</b>
      <span class="row__sub">vào hệ thống ${ngayTu(k.first_seen)} ngày trước · nhắn lần cuối ${clock(k.last_seen)}</span>
    </div>
    <div class="row__side">
      <span class="row__nut">
        <button type="button" class="btn btn--sm" data-giaovc="${esc(k.id)}">Giao cho…</button>
      </span>
    </div>
  </div>`).join("");
  /* Nói SỐ TỔNG khi danh sách bị cắt: "50 khách" trong khi thật ra 214 là
     một con số làm người ta yên tâm sai chỗ. */
  $("#voChuNote").textContent = d.so > ds.length
    ? `${d.so} khách chưa ai chịu trách nhiệm · đang hiện ${ds.length} cũ nhất`
    : `${d.so} khách chưa ai chịu trách nhiệm`;
}

$("#dsChet")?.addEventListener("click", async (e) => {
  const lai = e.target.closest("[data-guilai]");
  const bo = e.target.closest("[data-bochet]");
  const nut = lai || bo;
  if (!nut) return;
  nut.disabled = true;
  try {
    if (lai) {
      await api(`/outbox/jobs/${lai.dataset.guilai}/retry`, { method: "POST" });
      toast("Đã xếp lại hàng đợi. Theo dõi vài giây xem nó đi được chưa.");
    } else {
      /* Bỏ qua là NÓI RA rằng khách sẽ không bao giờ nhận tin này. Không
         hỏi "có chắc không" — câu ấy không mang thông tin nào. */
      if (!confirm("Bỏ qua tin này? Khách sẽ KHÔNG BAO GIỜ nhận được nó."
                   + " Việc này không hoàn tác được.")) { nut.disabled = false; return; }
      await api(`/outbox/jobs/${bo.dataset.bochet}/cancel`, { method: "POST" });
      toast("Đã bỏ qua.");
    }
    await loadTinChet();
    await loadOverview();
  } catch (err) {
    toast(err.message, true);
    nut.disabled = false;
  }
});

$("#dsVoChu")?.addEventListener("click", async (e) => {
  const g = e.target.closest("[data-giaovc]");
  if (!g) return;
  await giaoKhach(g.dataset.giaovc, "");
  await loadVoChu();
  await loadOverview();
});

/* ==================== Định tuyến tự động ====================
 *
 * `AutoRoutingWorker` chạy nền từ lâu (agent/main.py), nhưng không màn hình
 * nào tạo được đội hay luật — nên mỗi vòng nó không tìm thấy luật nào và
 * không làm gì. Một hệ thống con hoàn chỉnh nằm ngủ, và không có gì trên
 * dashboard nói rằng nó tồn tại.
 *
 * KHÔNG thay cho "giao khách cho nhân viên". Giao khách gán MỘT KHÁCH lâu
 * dài cho một người; định tuyến chia TỪNG HỘI THOẠI mới cho người đang rảnh.
 * Hai việc khác nhau, chạy song song được.
 */

const dinhTuyen = { doi: [], luat: [], sla: [], nguoi: [], kenh: [] };

function dtTenDoi(id) {
  const d = dinhTuyen.doi.find((x) => x.id === id);
  return d ? d.name : "đội đã xoá";
}

function dtTenKenh(id) {
  if (!id) return "mọi kênh";
  const k = dinhTuyen.kenh.find((x) => x.id === id);
  return k ? (k.display_name || k.channel) : "kênh đã xoá";
}

const DT_MUC = { low: "thấp", normal: "thường", high: "cao", urgent: "gấp" };

async function loadDinhTuyen() {
  if (!state.toiQuyen.has("dinh_tuyen.doc")) return;
  let c;
  try { c = await api("/routing"); } catch (e) { toast(e.message, true); return; }
  dinhTuyen.doi = c.teams || [];
  dinhTuyen.luat = c.rules || [];
  dinhTuyen.sla = c.sla_policies || [];
  dinhTuyen.thanhVien = c.members || [];
  dinhTuyen.canhBao = c.canh_bao || [];

  /* Hai danh sách phụ chỉ để đổ vào ô chọn. Lỗi ở đây KHÔNG được làm hỏng
     cả panel: người không có `nguoi_dung.doc` vẫn phải xem được luật đang
     chạy.

     Nhưng lỗi cũng KHÔNG được nuốt im: ô chọn rỗng trông hệt như "chưa có
     nhân viên nào", và người vận hành sẽ đi tạo nhân viên thay vì đi xem
     mình thiếu quyền gì. `dtThieu` nói ra điều đó ngay trong ô chọn.

     `/channel-accounts` trả về MẢNG chứ không phải `{items}` — đọc nhầm là
     ô chọn kênh rỗng vĩnh viễn, không lỗi, không ai biết. */
  dinhTuyen.loi = [];
  try { dinhTuyen.nguoi = (await api("/nguoi-dung")).nguoi_dung || []; }
  catch { dinhTuyen.nguoi = []; dinhTuyen.loi.push("nhân viên"); }
  try { dinhTuyen.kenh = await api("/channel-accounts") || []; }
  catch { dinhTuyen.kenh = []; dinhTuyen.loi.push("kênh"); }

  const soLuat = dinhTuyen.luat.filter((r) => r.active).length;
  /* Nói thẳng trạng thái NGỦ. "0 luật" là một con số; "không làm gì cả" là
     một câu người vận hành hiểu được ngay. */
  $("#dtTrangThai").textContent = soLuat
    ? `${dinhTuyen.doi.length} đội · ${soLuat} luật đang chạy`
    : "chưa có luật nào — bộ định tuyến KHÔNG làm gì";

  /* Đội hiện kèm THÀNH VIÊN. Trước đây chỉ có form "Thêm vào đội" mà không
     có danh sách, nên "đội này có ai" là câu không có chỗ trả lời. Đội rỗng
     là đội không giao được cho ai — nói thẳng. */
  $("#dtDoi").innerHTML = dinhTuyen.doi.length
    ? dinhTuyen.doi.map((d) => {
        const tv = dinhTuyen.thanhVien.filter((m) => m.team_id === d.id);
        const canh = new Set(dinhTuyen.canhBao.filter((c) => c.team_id === d.id).map((c) => c.user_id));
        return `<div class="row">
        <span class="row__flag row__flag--${d.status !== "active" ? "halt" : tv.length ? "auto" : "assist"}"></span>
        <div class="row__main">
          <b>${esc(d.name)}</b>
          <span class="row__sub">${esc(d.description || "—")}</span>
          <span class="row__sub">${tv.length
            ? tv.map((m) => `<span class="pill${canh.has(String(m.user_id)) ? " pill--warn" : ""}">${
                esc(m.ho_ten || m.ten_dang_nhap)} · tối đa ${m.max_active}${m.is_available ? "" : " · nghỉ"}</span>`).join(" ")
            : '<span class="pill pill--warn">chưa có ai — không giao được cho ai</span>'}</span>
        </div>
      </div>`;
      }).join("")
    : '<p class="empty">Chưa có đội nào.</p>';

  $("#dtCanhBao").innerHTML = dinhTuyen.canhBao.map((c) => `<div class="row">
      <span class="row__flag row__flag--halt"></span>
      <div class="row__main"><span class="row__sub">${esc(c.ly_do)}</span></div>
    </div>`).join("");

  $("#dtLuat").innerHTML = dinhTuyen.luat.length
    ? dinhTuyen.luat.map((r) => `<div class="row">
        <span class="row__flag row__flag--${r.active ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(dtTenKenh(r.account_id))} → ${esc(dtTenDoi(r.team_id))}</b>
          <span class="row__sub">mức ${esc(DT_MUC[r.priority] || "bất kỳ")} · trọng số ${r.weight}${r.active ? "" : " · đang tắt"}</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa có luật nào — hội thoại nằm chờ người tự nhận.</p>';

  $("#dtSla").innerHTML = dinhTuyen.sla.length
    ? dinhTuyen.sla.map((s2) => `<div class="row">
        <span class="row__flag row__flag--${s2.active ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(dtTenKenh(s2.account_id))} · mức ${esc(DT_MUC[s2.priority] || s2.priority)}</b>
          <span class="row__sub">trả lời đầu ${s2.first_response_minutes} phút · xong ${s2.resolution_minutes} phút</span>
        </div>
      </div>`).join("")
    : '<p class="empty">Chưa đặt hạn nào.</p>';

  const oDoi = dinhTuyen.doi
    .map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  $("#dtChonDoi").innerHTML = oDoi;
  $("#dtLuatDoi").innerHTML = oDoi;
  const dtThieu = (ten) => dinhTuyen.loi.includes(ten)
    ? `<option value="">— không đọc được danh sách ${ten}, thiếu quyền? —</option>`
    : "";
  $("#dtChonNguoi").innerHTML = dtThieu("nhân viên") + dinhTuyen.nguoi
    .filter((n) => !n.khoa)
    .map((n) => `<option value="${esc(n.id)}">${esc(n.ho_ten || n.ten_dang_nhap)}</option>`)
    .join("");
  const oKenh = '<option value="">mọi kênh</option>' + dtThieu("kênh")
    + dinhTuyen.kenh
      .map((k) => `<option value="${esc(k.id)}">${esc(k.display_name || k.channel)}</option>`)
      .join("");
  $("#dtChonKenh").innerHTML = oKenh;
  $("#dtSlaKenh").innerHTML = oKenh;
}

/* Gửi form rồi tải lại. Gom vào một hàm vì bốn form khác nhau đúng ở thân
   yêu cầu, còn phần xử lý lỗi và khoá nút thì giống hệt — và chép bốn lần
   là bốn chỗ để quên `finally`. */
async function dtGui(form, duong, phuong_thuc, dung_than) {
  const nut = form.querySelector("button[type=submit]");
  nut.disabled = true;
  try {
    const d = Object.fromEntries(new FormData(form).entries());
    await api(duong(d), { method: phuong_thuc, body: JSON.stringify(dung_than(d)) });
    form.reset();
    await loadDinhTuyen();
    toast("Đã lưu.");
  } catch (e) {
    toast(e.message, true);
  } finally {
    nut.disabled = false;
  }
}

$("#dtFormDoi")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget, () => "/routing/teams", "POST",
        (d) => ({ name: d.name, description: d.description || "" }));
});

$("#dtFormNguoi")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget,
        (d) => `/routing/teams/${d.team_id}/members/${d.user_id}`, "PUT",
        (d) => ({ role: "agent", skills: [],
                  max_active: Number(d.max_active) || 20, is_available: true }));
});

$("#dtFormLuat")?.addEventListener("submit", (e) => {
  e.preventDefault();
  /* `account_id` và `priority` rỗng phải thành null, KHÔNG phải chuỗi rỗng:
     máy chủ hiểu null là "mọi kênh / mọi mức", còn chuỗi rỗng thì trượt
     kiểm kiểu và trả 422 với một câu người vận hành không đọc được. */
  dtGui(e.currentTarget, () => "/routing/rules", "POST", (d) => ({
    account_id: d.account_id || null,
    team_id: d.team_id,
    priority: d.priority || null,
    required_skills: [],
    weight: Number(d.weight) || 100,
    active: true,
  }));
});

$("#dtFormSla")?.addEventListener("submit", (e) => {
  e.preventDefault();
  dtGui(e.currentTarget, () => "/routing/sla-policies", "PUT", (d) => ({
    account_id: d.account_id || null,
    priority: d.priority,
    first_response_minutes: Number(d.first_response_minutes),
    resolution_minutes: Number(d.resolution_minutes),
    business_hours: {},
    active: true,
  }));
});

/* ==================== Đếm trước khi xoá (có duyệt) ====================
 *
 * `/api/data-retention/jobs` có từ lâu, không màn hình nào gọi. Điều quan
 * trọng nhất về nó: máy chủ KHÔNG có bộ thực thi xoá cho luồng này — việc
 * duy nhất nó làm được là ĐẾM số bản ghi sẽ bị ảnh hưởng (`execute-dry-run`),
 * sau khi một người KHÁC người tạo đã duyệt. Màn hình phải nói đúng như
 * vậy; gọi nó là "xoá có duyệt" là hứa một việc máy chủ không làm.
 */

const RT_TRANG_THAI = {
  pending_approval: ["chờ người khác duyệt", "assist"],
  approved: ["đã duyệt · chưa chạy đếm", "auto"],
  completed: ["đã đếm", "auto"],
  cancelled: ["đã huỷ", "halt"],
};

function rtKetQua(r) {
  if (!r || !Object.keys(r).length) return "";
  const ten = { conversations: "hội thoại", messages: "tin nhắn", attachments: "tệp",
                contact_points: "danh tính", tags: "nhãn", notes: "ghi chú", consents: "đồng ý" };
  return Object.entries(r).filter(([, v]) => v > 0)
    .map(([k, v]) => `${v} ${ten[k] || k}`).join(" · ") || "không có gì để xoá";
}

async function loadRetention() {
  const o = $("#dsRetention");
  if (!o) return;
  if (!state.toiQuyen.has("khach.xoa")) {
    o.innerHTML = '<p class="empty">Cần quyền khach.xoa để xem mục này.</p>';
    return;
  }
  let ds;
  // Khoá là `jobs`, không phải `items` như outbox. Bản đầu đọc `.items` và
  // panel báo "chưa có yêu cầu" mãi mãi — kịch bản nghiệm thu 11 bắt được.
  try { ds = (await api("/data-retention/jobs")).jobs || []; }
  catch (e) { o.innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  $("#rtNote").textContent = ds.length
    ? `${ds.filter((j) => j.status === "pending_approval").length} đang chờ duyệt`
    : "chưa có yêu cầu nào";
  o.innerHTML = ds.length ? ds.map((j) => {
    let [nhan, co] = RT_TRANG_THAI[j.status] || [j.status, "assist"];
    const cua_toi = String(j.requested_by) === String(state.toiId);
    const nut = [];
    /* Phiếu đã tiêu cho một lần xoá thật. Trạng thái trong CSDL vẫn là
       "approved", nên không có nhánh này thì nó hiện y như phiếu còn dùng
       được — kèm nút Chạy đếm và Huỷ, cả hai đều vô nghĩa với một phiếu đã
       hết hiệu lực. */
    const da_dung = !!j.xoa_thuc_hien_luc;
    if (da_dung) {
      nhan = "đã dùng để xoá · không dùng lại được";
      co = "halt";
    } else if (j.status === "pending_approval") {
      /* Người tạo không tự duyệt được — máy chủ chặn (409). Ẩn nút với họ
         để không tạo ra một cú bấm chắc chắn thất bại. */
      if (!cua_toi) nut.push(`<button type="button" class="btn btn--sm" data-rtduyet="${esc(j.id)}">Duyệt</button>`);
      nut.push(`<button type="button" class="btn btn--sm btn--ghost" data-rthuy="${esc(j.id)}">Huỷ</button>`);
    } else if (j.status === "approved") {
      /* Chạy đếm đếm theo `contact_id`. Phiếu xin từ màn Nhật ký khoá theo
         số điện thoại và thường không gắn khách nào — máy chủ từ chối
         (409 "không còn gắn với khách hàng"). Ẩn nút thay vì để nó trả lỗi:
         màn PDPD ở trên đã hiện sẵn đơn và hội thoại sẽ mất. */
      if (j.dry_run && j.contact_id) nut.push(`<button type="button" class="btn btn--sm" data-rtdem="${esc(j.id)}">Chạy đếm</button>`);
      nut.push(`<button type="button" class="btn btn--sm btn--ghost" data-rthuy="${esc(j.id)}">Huỷ</button>`);
    }
    return `<div class="row">
      <span class="row__flag row__flag--${co}"></span>
      <div class="row__main">
        <b>${esc(j.kind === "delete" ? "Xoá" : j.kind === "export" ? "Xuất" : "Lưu trữ")} · ${
          /* Phiếu xin từ màn Nhật ký khoá theo SỐ, không theo khách — và số
             ấy bị xoá khỏi phiếu ngay khi phiếu được dùng, nên có lúc không
             còn gì để hiện. Nói "không còn hiển thị" chứ đừng in "null…". */
          esc(j.contact_id ? "khách " + String(j.contact_id).slice(0, 8) + "…"
              : j.sdt_che ? "số " + j.sdt_che
              : "số đã ẩn sau khi xoá")
        }${cua_toi ? " · bạn tạo" : ""}</b>
        <span class="row__sub">${esc(j.reason || "")}</span>
        <span class="row__sub">${esc(nhan)} · ${clock(j.requested_at)}${j.result && Object.keys(j.result).length ? " · " + esc(rtKetQua(j.result)) : ""}</span>
      </div>
      <div class="row__side">${nut.length ? `<span class="row__nut">${nut.join("")}</span>` : ""}</div>
    </div>`;
  }).join("") : '<p class="empty">Chưa có yêu cầu nào. Tạo từ hồ sơ khách ở màn Khách hàng.</p>';
}

$("#dsRetention")?.addEventListener("click", async (e) => {
  const duyet = e.target.closest("[data-rtduyet]");
  const dem = e.target.closest("[data-rtdem]");
  const huy = e.target.closest("[data-rthuy]");
  const nut = duyet || dem || huy;
  if (!nut) return;
  const id = duyet?.dataset.rtduyet || dem?.dataset.rtdem || huy?.dataset.rthuy;
  const duong = duyet ? "approve" : dem ? "execute-dry-run" : "cancel";
  nut.disabled = true;
  try {
    const r = await api(`/data-retention/jobs/${id}/${duong}`, { method: "POST" });
    toast(duyet ? "Đã duyệt. Giờ bấm Chạy đếm."
      : dem ? `Đã đếm: ${rtKetQua(r.result)}.` : "Đã huỷ yêu cầu.");
    await loadRetention();
  } catch (err) { toast(err.message, true); nut.disabled = false; }
});

/* Tạo yêu cầu đếm từ hồ sơ khách. Luôn dry_run: máy chủ không thực thi gì
   khác, và gửi dry_run=false là tạo một yêu cầu mãi mãi "đã duyệt" mà không
   bao giờ chạy. */
async function rtYeuCauDem(contactId) {
  const d = await hoiHop({
    tieu_de: "Đếm dữ liệu sẽ xoá",
    phu: "Chỉ đếm, chưa xoá gì. Một người khác phải duyệt ở màn Nhật ký. Lý do ghi vào nhật ký.",
    truong: [{ name: "ly_do", label: "Lý do", value: "Khách yêu cầu xoá dữ liệu",
               required: true, maxlength: 500 }],
    nut: "Tạo yêu cầu",
  });
  if (!d || !d.ly_do) return;
  try {
    await api(`/contacts/${contactId}/retention-jobs`, {
      method: "POST",
      body: JSON.stringify({ kind: "delete", reason: d.ly_do, dry_run: true }),
    });
    toast("Đã tạo yêu cầu. Một người khác cần duyệt ở màn Nhật ký.");
  } catch (e) { toast(e.message, true); }
}

/* ==================== Sức khoẻ từng kênh ==================== */

/* Uỷ quyền lên #contactdetail: khung chi tiết dựng lại innerHTML mỗi lần
   chọn khách, gắn listener lên nút thì mỗi lần dựng lại phải gắn lại. */
$("#contactdetail")?.addEventListener("click", (e) => {
  const b = e.target.closest("[data-contact-rt]");
  if (b) rtYeuCauDem(b.dataset.contactRt);
});

async function kenhSucKhoe(nut) {
  const id = nut.dataset.health;
  const o = document.querySelector(`[data-tokenslot="${id}"]`);
  nut.disabled = true;
  try {
    const d = (await api(`/channel-accounts/${id}/health`)).latest;
    const html = d
      ? `<span class="row__sub">Lần kiểm gần nhất ${clock(d.observed_at)}: <b>${esc(ACCOUNT_STATUS_LABEL[d.status] || d.status)}</b> · <code>${esc(d.code || "")}</code></span>`
      : '<span class="row__sub">Chưa có lần kiểm nào — bấm Xác minh provider.</span>';
    state.sucKhoeKenh = state.sucKhoeKenh || {};
    state.sucKhoeKenh[id] = html;      // để lần dựng lại thẻ vẫn còn
    if (o) o.innerHTML = html;
  } catch (e) { toast(e.message, true); }
  finally { nut.disabled = false; }
}

/* Bấm ảnh trên dòng kho -> xem lớn. Uỷ quyền lên #khoRows vì danh sách dựng
   lại mỗi vòng làm mới; gắn lên từng ảnh là gắn lại mãi. */
$("#khoRows")?.addEventListener("click", (e) => {
  const a = e.target.closest("[data-xemanh]");
  if (!a) return;
  $("#anhLonImg").src = a.src;
  $("#anhLonTen").textContent = a.closest(".row")?.querySelector("b, .row__title")?.textContent || a.dataset.xemanh;
  $("#anhLon").classList.remove("is-off");
});
const anhLonDong = () => $("#anhLon").classList.add("is-off");
$("#anhLonDong")?.addEventListener("click", anhLonDong);
$("#anhLon")?.addEventListener("click", (e) => { if (e.target === e.currentTarget) anhLonDong(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#anhLon")?.classList.add("is-off"); });

/* BÁO CÓ KHÁCH CẦN NGƯỜI ngay trên máy người trực.
 *
 * Trước 29.10.2026, chuyển người trên Zalo, Instagram, WhatsApp, chat web chỉ
 * làm con số ở mục Ca trực nhảy lên — ai đang ở màn khác, hay đang ở tab
 * khác, thì không thấy gì. Hai lớp, cả hai không cần máy chủ gửi gì thêm:
 *   - tiêu đề tab mang số việc đang chờ: thấy được cả khi tab nằm sau;
 *   - thông báo của hệ điều hành khi số hội thoại chờ người TĂNG (không báo
 *     lần tải đầu: mở dashboard ra mà bị dội mười thông báo cũ là học cách
 *     tắt nó).
 * Ngoài dashboard thì đi đường webhook (canh_gac.bao_nhan_vien). */
const TIEU_DE_GOC = document.title;
let soCanNguoiTruoc = null;

function baoKhachCanNguoi(escalated, tong) {
  document.title = tong ? `(${tong}) ${TIEU_DE_GOC}` : TIEU_DE_GOC;
  const tang = soCanNguoiTruoc !== null && escalated > soCanNguoiTruoc;
  soCanNguoiTruoc = escalated;
  if (!tang || !("Notification" in window) || Notification.permission !== "granted") return;
  try {
    const tb = new Notification("Khách cần người trả lời", {
      body: `${escalated} hội thoại đang chờ người · mở Ca trực để nhận`,
      tag: "khach-can-nguoi",
    });
    tb.onclick = () => { window.focus(); doiMan("ca"); tb.close(); };
  } catch { /* Vài trình duyệt di động chỉ cho thông báo qua service worker. */ }
}

function veNutThongBao() {
  const o = $("#batThongBao");
  if (!o) return;
  if (!("Notification" in window) || Notification.permission === "granted") { o.hidden = true; return; }
  o.hidden = false;
  if (Notification.permission === "denied") {
    o.textContent = "Trình duyệt đang chặn thông báo của trang này — mở cài đặt trang (biểu tượng ổ khoá) để cho phép, nếu muốn được báo khi có khách cần người.";
    return;
  }
  o.innerHTML = 'Máy này chưa được báo khi có khách cần người. <button type="button" class="btn btn--sm" id="nutThongBao">Bật thông báo</button>';
  $("#nutThongBao").addEventListener("click", async () => {
    try { await Notification.requestPermission(); } catch { /* trình duyệt cũ */ }
    veNutThongBao();
  });
}
veNutThongBao();

async function loadOverview() {
  const o = await api("/overview");
  applyRuntime(o.runtime);
  if (o.public_base_url) PUBLIC_BASE = o.public_base_url;
  drawTape(o.tape);

  // Huy hiệu "Ca trực" đếm MỌI hội thoại cần người, không riêng cái chờ
  // duyệt — nếu không thì bảy hội thoại đã chuyển người nằm ngoài con số
  // và người trực tưởng ca đang êm.
  $("#c-ca").textContent =
    (o.conversations.waiting || 0) + (o.conversations.escalated || 0);
  baoKhachCanNguoi(o.conversations.escalated || 0,
    (o.conversations.waiting || 0) + (o.conversations.escalated || 0));
  $("#c-hoithoai").textContent = o.conversations.total || 0;
  $("#c-video").textContent = o.video.review || 0;
  $("#rail-cost").textContent = usd(o.cost.total_usd);

  $("#readout").innerHTML = [
    cell("Hội thoại 24 giờ", o.conversations.total, "cuộc", null, "auto"),
    cell("Agent tự xử lý", pct(o.conversations.containment),
         `${o.conversations.handled}/${o.conversations.total}`,
         o.conversations.containment, "auto"),
    cell("Chờ người", o.conversations.waiting, "cuộc",
         o.conversations.total ? o.conversations.waiting / o.conversations.total : 0, "assist"),
    /* TIN CHẾT — ô này chỉ hiện khi có tin chết, và khi hiện thì nó đỏ.
     *
     * Một ô luôn hiện "0" là một ô người ta thôi nhìn sau tuần đầu. Ô chỉ
     * xuất hiện khi có chuyện thì sự xuất hiện của nó CHÍNH LÀ tín hiệu.
     *
     * Không cắt theo 24 giờ: tin không gửi được tuần trước vẫn là tin
     * khách không nhận được. Ba tin đã chết rải hơn một tuần mà không ai
     * biết, đúng vì không có chỗ nào đếm chúng. */
    (o.tin_chet && o.tin_chet.so
      ? cell("Tin KHÔNG gửi được", o.tin_chet.so, "khách không nhận được", 1, "halt")
      : ""),
    /* KHÁCH CHƯA CÓ CHỦ — cùng lý lẽ với ô trên: chỉ hiện khi CÓ.
     *
     * Chủ dự án chọn "khách chưa giao là của chung, không tự gán chủ", nên
     * khách vô chủ sẽ tích lại — đó là hệ quả đã biết trước, và một hàng
     * chờ không ai đếm thì không ai thấy.
     *
     * Kèm TUỔI của khách vô chủ lâu nhất, không chỉ số lượng: "412 khách"
     * là một con số người ta quen mắt sau một tuần; "lâu nhất 62 ngày" thì
     * không. */
    /* VIỆC QUÁ HẠN — cùng họ với hai ô trên, cũng chỉ hiện khi CÓ.
     * Đếm riêng việc CHƯA GIAO cho ai: đó là thứ dễ rơi nhất, vì không ai
     * thấy nó trong danh sách "việc của tôi". */
    (o.cong_viec && o.cong_viec.qua_han
      ? cell("Việc quá hạn", o.cong_viec.qua_han,
             o.cong_viec.chua_giao
               ? `${o.cong_viec.chua_giao} việc chưa giao cho ai`
               : "đều đã có người nhận", 1, "halt")
      : ""),
    (o.khach_vo_chu && o.khach_vo_chu.so
      ? cell("Khách chưa có chủ", o.khach_vo_chu.so,
             o.khach_vo_chu.lau_nhat
               ? `lâu nhất ${ngayTu(o.khach_vo_chu.lau_nhat)} ngày`
               : "chưa giao cho ai", 1, "assist")
      : ""),
    cell("Đã chuyển người", o.conversations.escalated, "cuộc",
         o.conversations.total ? o.conversations.escalated / o.conversations.total : 0, "halt"),
    cell("Có căn cứ tài liệu", pct(o.quality.grounding), `${o.quality.replies} lượt trả lời`,
         o.quality.grounding, "auto"),
    cell("Chi phí mỗi hội thoại", usd(o.cost.per_conversation), `tổng ${usd(o.cost.total_usd)}`,
         null, "spend"),
    cell("Token đọc từ cache", o.cost.cache_read.toLocaleString("vi-VN"), "token",
         o.cost.tokens_in + o.cost.cache_read
           ? o.cost.cache_read / (o.cost.tokens_in + o.cost.cache_read) : 0, "spend"),
    cell("Video sản xuất", o.video.total, `${o.video.seconds}s · ${o.video.failed} lỗi`,
         null, "auto"),
  ].join("");

  /* limit=200, không phải 12. Khung này là HÀNG ĐỢI, không phải bản tin:
     cắt ở 12 nghĩa là khi có 20 khách chờ thì 8 người biến mất khỏi màn
     hình — và với thứ tự chờ-lâu-nhất-trước do API trả về, 8 người mất đi
     lại chính là 8 người mới nhắn. Thà cuộn dài còn hơn giấu người đang đợi.
     API đã xếp sẵn ai chờ lâu nhất lên đầu. */
  /* Hai khối dưới đây (`#queue` và `#videoqueue`) chỉ tồn tại trong màn
     Ca trực. Nạp chúng khi đang mở màn khác là đổ dữ liệu vào DOM bị ẩn.
     ĐO ĐƯỢC 22.09.2026 trên dashboard đang chạy: `loadOverview()` phát BA
     request, và `refresh()` gọi nó mỗi 6 giây bất kể màn nào đang mở —
     tức 30 request/phút mỗi tab, trong đó hai phần ba kéo tới 200 hội
     thoại và 30 video mà không ai nhìn. Nhân với số người trực thì đó là
     tải thật trên máy chủ, đổi lấy không gì cả.

     Vẫn giữ `/overview` chạy mọi lúc: nó nuôi các con số trên thanh điều
     hướng, và người trực cần thấy "Ca trực" nhảy số kể cả khi đang đứng ở
     màn khác — đó chính là cách họ biết có việc mới. */
  if (state.view !== "ca") return;

  const waiting = await api("/conversations?status=can_nguoi&limit=200");
  $("#queue").innerHTML = waiting.length
    ? waiting.map((c) => convRow(c, true)).join("")
    : '<p class="empty">Không có hội thoại nào đang chờ. Ca trực êm.</p>';
  wireConvRows("#queue");

  const vids = (await api("/videos?limit=30")).filter((v) => v.status === "pending_review");
  $("#videoqueue").innerHTML = vids.length
    ? vids.map((v) => `<div class="row">
        <span class="row__flag row__flag--assist"></span>
        <span class="row__body">
          <span class="row__title">${esc(v.title)}</span>
          <span class="row__sub">${v.duration_s ? v.duration_s.toFixed(1) + "s" : "—"} · ${esc(v.renderer || "")}</span>
        </span>
        <span class="row__side"><span class="row__time">${clock(v.created_at)}</span></span>
      </div>`).join("")
    : '<p class="empty">Không có video nào chờ duyệt.</p>';
}

