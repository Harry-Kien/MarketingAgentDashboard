/* ---------------- Customer 360 ---------------- */

function openCustomer(id) {
  state.openContact = id;
  /* Đi qua `doiMan` chứ KHÔNG gọi thẳng `loadContacts()`.
   *
   * Bản cũ gọi thẳng, nên thiếu `loadTruongKhach()` mà `refresh()` vẫn gọi
   * cho màn này. Hệ quả: `oTruongKhach()` thấy `truongKhach.ds` rỗng và
   * `return ""` — toàn bộ trường tuỳ biến BIẾN MẤT, không báo gì, cho tới
   * khi vòng 6 giây tình cờ vá lại. Mở hồ sơ khách từ hội thoại là đúng
   * đường đi vào lỗi ấy. */
  doiMan("khachhang");
}

$("#contactsearch")?.addEventListener("submit", (ev) => {
  ev.preventDefault();
  state.contactQuery = String(new FormData(ev.target).get("q") || "").trim();
  loadContacts();
});

function chuKhach(contact) {
  /* Hiện TÊN người phụ trách, không hiện UUID và không để trống.
   *
   * Để trống thì "chưa giao cho ai" trông hệt như "chưa tải xong", và người
   * trực không biết mình có được vào hay không.
   *
   * KHÁCH CỦA CHÍNH MÌNH PHẢI KHÁC MÀU, KHÔNG CHỈ KHÁC TÊN.
   * Hiện đúng tên người là chưa đủ: nhân viên phải đọc từng dòng rồi tự đối
   * chiếu với tên mình — ở danh sách 100 khách thì không ai làm. Ba trạng
   * thái, ba màu, đọc được bằng cách liếc:
   *     của mình      → xanh, chữ "Bạn phụ trách"
   *     của người khác → xám, tên người ấy
   *     chưa giao      → vàng, "chưa có chủ" (của chung, ai cũng trả lời được)
   */
  if (contact.owner_user_id && contact.owner_user_id === state.toiId) {
    return '<span class="pill pill--toi">Bạn phụ trách</span>';
  }
  if (contact.owner_ho_ten || contact.owner_ten_dang_nhap) {
    return `<span class="pill">${esc(contact.owner_ho_ten || contact.owner_ten_dang_nhap)}</span>`;
  }
  return '<span class="pill pill--warn">chưa có chủ</span>';
}

/* ==================== Gộp khách trùng ====================
 *
 * Một người nhắn Zalo rồi nhắn Facebook là HAI contact trong CSDL, và không
 * có gì tự nối lại. API gộp có đủ ba việc — xem trước, gộp, hoàn tác —
 * nhưng không màn hình nào gọi tới, nên lịch sử của một khách nằm rải ở hai
 * chỗ và người trực trả lời mà không thấy nửa còn lại.
 *
 * XEM TRƯỚC LÀ BẮT BUỘC, KHÔNG PHẢI TÙY CHỌN.
 * Gộp dồn hội thoại và danh tính sang một bên rồi đánh dấu bên kia là đã
 * gộp. Hoàn tác được, nhưng chỉ khi biết mình vừa gộp nhầm — mà gộp nhầm
 * hai khách trùng tên thì không ai nhận ra. Nên nút Gộp chỉ hiện SAU khi đã
 * xem trước, và xem trước nói rõ mỗi bên có bao nhiêu hội thoại, bao nhiêu
 * danh tính.
 */

function gopDoO(ds) {
  const o = $("#gopNguon");
  if (!o) return;
  const html = (ds || []).map((c) =>
    `<option value="${esc(c.id)}">${esc(c.display_name || "Khách")}`
    + ` · ${c.contact_point_count || 0} danh tính</option>`).join("");
  o.innerHTML = html;
  $("#gopDich").innerHTML = html;
}

$("#gopMo")?.addEventListener("click", () => {
  const pn = $("#pnGop");
  pn.classList.toggle("is-hidden");
  if (!pn.classList.contains("is-hidden")) gopDoO(state.danhSachKhach);
});

$("#gopDong")?.addEventListener("click", () => {
  $("#pnGop").classList.add("is-hidden");
  $("#gopKetQua").innerHTML = "";
});

$("#gopXem")?.addEventListener("click", async () => {
  const nguon = $("#gopNguon").value;
  const dich = $("#gopDich").value;
  if (!nguon || !dich) return;
  if (nguon === dich) {
    toast("Hai ô đang chọn cùng một khách.", true);
    return;
  }
  try {
    const d = await api(`/contacts/merge/preview?source_id=${encodeURIComponent(nguon)}`
                        + `&target_id=${encodeURIComponent(dich)}`);
    const ben = (t, x) => `<div class="row">
      <span class="row__flag row__flag--${t === "nguon" ? "halt" : "auto"}"></span>
      <div class="row__main">
        <b>${esc(x.display_name || "Khách")}</b>
        <span class="row__sub">${t === "nguon" ? "SẼ BIẾN MẤT khỏi danh sách" : "GIỮ LẠI, nhận hết về đây"}</span>
        <span class="row__sub">${x.conversation_count} hội thoại · ${x.point_count} danh tính</span>
      </div>
    </div>`;
    /* `can_manage` false nghĩa là người này không quản được mọi kênh của cả
       hai khách. Máy chủ sẽ từ chối — nói trước ở đây thay vì để họ điền
       xong lý do rồi mới ăn 403. */
    $("#gopKetQua").innerHTML = ben("nguon", d.source) + ben("dich", d.target)
      /* Câu cảnh báo là `panel__note`, KHÔNG phải một `.row` nữa: `.row__main`
         không có `<b>` thì co lại gần bằng không và chữ biến mất — nhìn trên
         trình duyệt mới thấy, đọc mã thì không. */
      + (d.can_manage
        ? `<p class="panel__note">Hoàn tác được sau khi gộp, nhưng chỉ khi bạn
             nhận ra mình gộp nhầm — nên xem kỹ hai dòng trên.</p>
           <div class="row__nut">
             <button type="button" class="btn btn--sm btn--halt" id="gopLam">Gộp</button>
           </div>`
        : `<p class="empty">Bạn không quản lý mọi kênh của hai khách này, nên
             không gộp được. Nhờ quản trị làm.</p>`);

    $("#gopLam")?.addEventListener("click", async () => {
      const hoi = await hoiHop({
        tieu_de: "Gộp hai khách làm một",
        phu: "Hội thoại và danh tính dồn về bên giữ lại. Lý do ghi vào lịch sử, để hoàn tác còn hiểu được.",
        truong: [{ name: "ly_do", label: "Vì sao gộp", value: "Cùng một người, hai kênh",
                   required: true, maxlength: 500 }],
        nut: "Gộp", nguy_hiem: true,
      });
      if (!hoi || !hoi.ly_do) return;
      const ly_do = hoi.ly_do;
      const nut = $("#gopLam");
      nut.disabled = true;
      try {
        /* Gửi kèm `version` đọc được lúc xem trước. Ai đó sửa một trong hai
           khách giữa lúc xem và lúc bấm thì máy chủ trả 409 và KHÔNG gộp —
           đúng hơn là gộp theo một bản xem trước đã cũ. */
        const r = await api("/contacts/merge", {
          method: "POST",
          body: JSON.stringify({
            source_id: d.source.id, target_id: d.target.id, reason: ly_do,
            expected_source_version: d.source.version,
            expected_target_version: d.target.version,
          }),
        });
        toast(`Đã gộp. Hoàn tác được bằng mã ${r.merge_id.slice(0, 8)}…`);
        $("#gopKetQua").innerHTML = "";
        $("#pnGop").classList.add("is-hidden");
        await loadContacts();
      } catch (e) {
        toast(e.ma === 409
          ? "Một trong hai khách vừa bị người khác sửa. Xem trước lại."
          : e.message, true);
        nut.disabled = false;
      }
    });
  } catch (e) { toast(e.message, true); }
});

async function loadContacts() {
  const contacts = await api(`/contacts?limit=100&q=${encodeURIComponent(state.contactQuery)}`);
  /* Lọc Ở PHÍA GIAO DIỆN là có chủ ý và chỉ hợp lệ vì nó KHÔNG phải lớp bảo
   * vệ: máy chủ đã lọc theo mức tầm nhìn trước khi trả về. Ba chip này chỉ
   * thu hẹp thứ người dùng đã được phép thấy. */
  const loc = state.chuLoc || "tat_ca";
  const hien = contacts.filter((c) =>
    loc === "cua_toi" ? c.owner_user_id && c.owner_user_id === state.toiId
    : loc === "vo_chu" ? !c.owner_user_id
    : true);
  state.danhSachKhach = contacts;
  $("#c-khachhang").textContent = contacts.length || "";
  /* Số ngay trên chip lọc. Không có nó thì phải bấm từng chip mới biết mình
     có bao nhiêu khách — và "Khách của tôi" rỗng trông hệt như bộ lọc hỏng. */
  const demToi = contacts.filter((c) => c.owner_user_id && c.owner_user_id === state.toiId).length;
  const demVoChu = contacts.filter((c) => !c.owner_user_id).length;
  const datDem = (sel, n) => {
    const chip = $(sel);
    if (chip) chip.querySelector(".chip__dem").textContent = n ? ` ${n}` : "";
  };
  datDem('[data-chuloc="tat_ca"]', contacts.length);
  datDem('[data-chuloc="cua_toi"]', demToi);
  datDem('[data-chuloc="vo_chu"]', demVoChu);
  gopDoO(contacts);
  /* Ô tick nằm NGOÀI nút hàng (nút không được chứa điều khiển khác), và
     trạng thái tick sống trong state.khachDaChon để qua vòng làm mới 6 giây
     không mất — tick mười khách rồi thấy mất sạch là thứ người ta bỏ luôn. */
  const giaoDuoc = state.toiQuyen.has("khach.giao");
  state.khachDaChon = state.khachDaChon || new Set();
  for (const id of [...state.khachDaChon]) {
    if (!contacts.some((c) => c.id === id)) state.khachDaChon.delete(id);
  }
  $("#contactlist").innerHTML = hien.length ? hien.map((contact) => `
    <div class="row-wrap">${giaoDuoc ? `<label class="chonkhach" title="Chọn để giao hàng loạt">
      <input type="checkbox" data-chon="${contact.id}"${state.khachDaChon.has(contact.id) ? " checked" : ""}></label>` : ""}
    <button type="button" class="row row--avatar ${state.openContact === contact.id ? "is-on" : ""}" data-contact="${contact.id}">
      <span class="avatar">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <span class="row__body"><span class="row__title">${esc(contact.display_name || "Khách")}</span>
        <span class="row__sub">${esc(contact.phone || contact.email || "Chưa có SĐT/email")} · ${contact.contact_point_count || 0} danh tính</span></span>
      <span class="row__side">${chuKhach(contact)}<span class="row__time">${clock(contact.last_seen)}</span></span>
    </button></div>`).join("")
    : `<p class="empty">${loc === "cua_toi"
        ? "Chưa có khách nào được giao cho bạn."
        : loc === "vo_chu"
          ? "Mọi khách trong phạm vi của bạn đều đã có người phụ trách."
          : "Không tìm thấy khách hàng trong phạm vi tài khoản của bạn."}</p>`;
  $$("#contactlist [data-contact]").forEach((row) => row.addEventListener("click", () => {
    state.openContact = row.dataset.contact;
    loadContacts();
  }));
  $$("#contactlist [data-chon]").forEach((o) => o.addEventListener("change", () => {
    if (o.checked) state.khachDaChon.add(o.dataset.chon);
    else state.khachDaChon.delete(o.dataset.chon);
    veChonBar();
  }));
  veChonBar();
  if (state.openContact) await loadContactDetail(state.openContact);
}

function veChonBar() {
  const n = (state.khachDaChon || new Set()).size;
  $("#chonbar")?.classList.toggle("is-hidden", n === 0);
  const d = $("#chonDem");
  if (d) d.textContent = `Đã chọn ${n} khách`;
}

$("#chonHuy")?.addEventListener("click", () => {
  state.khachDaChon = new Set();
  loadContacts();
});

/*
 * Giao hàng loạt: cùng lớp phủ chọn người với giao lẻ, nhưng gọi endpoint
 * một-giao-dịch. Không lặp endpoint đơn N lần: rớt mạng giữa chừng là nửa
 * số khách có chủ, nửa không, và người bấm không biết dừng ở đâu.
 */
$("#chonGiao")?.addEventListener("click", async () => {
  const ids = [...(state.khachDaChon || [])];
  if (!ids.length) return;
  let ds;
  try { ds = (await api("/nguoi-dung")).nguoi_dung.filter((n) => !n.khoa); }
  catch (e) { toast(e.message, true); return; }

  const o = $("#giaoAi");
  o.innerHTML = '<option value="">— Thu hồi: các khách này quay về của chung —</option>'
    + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ho_ten || n.ten_dang_nhap)} (${esc(n.ten_dang_nhap)})</option>`).join("");
  $("#giaoKhachTen").textContent = `${ids.length} khách đã chọn.`;
  $("#giaoLyDo").value = "Phân công ca trực";
  $("#congGiao").classList.remove("is-off");
  o.focus();

  const form = $("#giaoform");
  const dong = () => { $("#congGiao").classList.add("is-off"); form.onsubmit = null; $("#giaoHuy").onclick = null; };
  $("#giaoHuy").onclick = (e) => { e.preventDefault(); dong(); };
  form.onsubmit = async (e) => {
    e.preventDefault();
    const nut = form.querySelector("button[type=submit]");
    nut.disabled = true;
    try {
      const r = await api("/contacts/chu-so-huu/hang-loat", {
        method: "PUT",
        body: JSON.stringify({ contact_ids: ids, owner_user_id: o.value || null,
                               ly_do: $("#giaoLyDo").value.trim() }),
      });
      toast(r.owner_ho_ten
        ? `Đã giao ${r.so_khach} khách cho ${r.owner_ho_ten}.`
        : `Đã thu hồi ${r.so_khach} khách về của chung.`);
      dong();
      state.khachDaChon = new Set();
      await loadContacts();
      if (state.view === "ca") { await loadVoChu(); await loadOverview(); }
    } catch (err) { toast(err.message, true); }
    finally { nut.disabled = false; }
  };
});

$("#contactloc")?.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-chuloc]");
  if (!chip) return;
  state.chuLoc = chip.dataset.chuloc;
  $$("#contactloc .chip").forEach((c) => c.classList.toggle("is-on", c === chip));
  loadContacts();
});

async function giaoKhach(id, chuHienTai) {
  /* CHỌN từ danh sách, không gõ tên. Bản cũ là hộp thoại của trình duyệt
     liệt kê tên đăng nhập rồi bắt gõ lại: gõ sai một chữ là "Không có nhân
     viên tên…", và không gì trên màn hình cho biết tên đúng viết thế nào.

     Trả về Promise để nơi gọi (Ca trực, Khách hàng) chờ xong rồi tải lại. */
  let ds;
  try { ds = (await api("/nguoi-dung")).nguoi_dung.filter((n) => !n.khoa); }
  catch (e) { toast(e.message, true); return; }

  const o = $("#giaoAi");
  o.innerHTML = '<option value="">— Thu hồi: khách quay về của chung —</option>'
    + ds.map((n) => `<option value="${esc(n.id)}"${
        n.ten_dang_nhap === chuHienTai ? " selected" : ""}>${
        esc(n.ho_ten || n.ten_dang_nhap)} (${esc(n.ten_dang_nhap)})</option>`).join("");
  $("#giaoKhachTen").textContent = chuHienTai
    ? `Đang do ${chuHienTai} phụ trách.` : "Khách chưa ai phụ trách.";
  $("#giaoLyDo").value = "Phân công ca trực";
  $("#congGiao").classList.remove("is-off");
  o.focus();

  return new Promise((xong) => {
    const form = $("#giaoform");
    const dong = () => { $("#congGiao").classList.add("is-off"); form.onsubmit = null; $("#giaoHuy").onclick = null; };
    $("#giaoHuy").onclick = (e) => { e.preventDefault(); dong(); xong(false); };
    form.onsubmit = async (e) => {
      e.preventDefault();
      const ai = o.value, ly_do = $("#giaoLyDo").value.trim();
      const nut = form.querySelector("button[type=submit]");
      nut.disabled = true;
      try {
        if (!ai) {
          await api(`/contacts/${id}/chu-so-huu?ly_do=${encodeURIComponent(ly_do)}`,
                    { method: "DELETE" });
          toast("Đã thu hồi. Khách quay về của chung.");
        } else {
          await api(`/contacts/${id}/chu-so-huu`, {
            method: "PUT", body: JSON.stringify({ owner_user_id: ai, ly_do }),
          });
          toast(`Đã giao cho ${o.options[o.selectedIndex].text}.`);
        }
        dong();
        if (state.view === "khachhang") await loadContacts();
        xong(true);
      } catch (err) { toast(err.message, true); }
      finally { nut.disabled = false; }
    };
  });
}


function oTruongKhach(contact) {
  /* Vẽ ô nhập theo KIỂU. Vẽ tất cả thành ô chữ cũng "chạy" — máy chủ vẫn
     kiểm — nhưng khi ấy người trực gõ sai rồi mới biết, mỗi lần một lần.
     Ô đúng kiểu là lớp phòng thứ nhất; máy chủ là lớp thứ hai. */
  if (!truongKhach.ds.length) return "";
  const co = contact.profile || {};
  const o = truongKhach.ds.map((t) => {
    const v = co[t.ma];
    const id = `tk-${t.ma}`;
    let nhap;
    if (t.kieu === "chon") {
      nhap = `<select id="${id}" data-tk="${esc(t.ma)}">
        <option value="">— chưa chọn —</option>
        ${(t.lua_chon || []).map((c) =>
          `<option${c === v ? " selected" : ""}>${esc(c)}</option>`).join("")}
      </select>`;
    } else if (t.kieu === "nhieu_chon") {
      nhap = `<span class="tk__nhieu">${(t.lua_chon || []).map((c) => `
        <label><input type="checkbox" data-tk-nhieu="${esc(t.ma)}" value="${esc(c)}"${
          Array.isArray(v) && v.includes(c) ? " checked" : ""}> ${esc(c)}</label>`).join("")}</span>`;
    } else if (t.kieu === "dung_sai") {
      nhap = `<input type="checkbox" id="${id}" data-tk="${esc(t.ma)}"${v ? " checked" : ""}>`;
    } else {
      const loai = t.kieu === "so" ? "number" : t.kieu === "ngay" ? "date" : "text";
      nhap = `<input type="${loai}" id="${id}" data-tk="${esc(t.ma)}"
                     value="${v === undefined || v === null ? "" : esc(String(v))}"
                     placeholder="${esc(t.goi_y || "")}">`;
    }
    return `<label class="field tk__o" for="${id}">
      <span>${esc(t.nhan)}${t.bat_buoc ? " *" : ""}</span>${nhap}</label>`;
  }).join("");
  return `<h3 class="subhead">Thông tin thêm</h3>
    <form id="contact-truong-form" class="form">${o}
      <button class="btn btn--sm" type="submit">Lưu thông tin thêm</button></form>`;
}

/* Khoá nhận dạng một ô nhập, BỀN qua mỗi lần dựng lại DOM.
 *
 * Không dùng tham chiếu phần tử được: sau `innerHTML` thì phần tử cũ đã
 * chết. Phải là khoá tính từ nội dung — mã trường, hoặc form + tên ô. */
function _khoaO(o) {
  if (o.dataset.tkNhieu) return `tkn:${o.dataset.tkNhieu}:${o.value}`;
  if (o.dataset.tk) return `tk:${o.dataset.tk}`;
  const f = o.closest("form");
  return `${f ? f.id : "khong-form"}:${o.name || ""}`;
}

/* Ô này người ta có TỰ SỬA không?
 *
 * Phân biệt được điều đó mới là phần khó. Giữ lại TẤT CẢ các ô thì một
 * đồng nghiệp vừa đổi trường tuỳ biến ở máy khác sẽ bị giá trị cũ trên
 * màn này đè ngược lại — chữa một lỗi im lặng bằng một lỗi im lặng tệ hơn.
 *
 * `defaultValue`/`defaultChecked` chính là giá trị vừa dựng từ dữ liệu máy
 * chủ (DOM sinh bằng innerHTML nên thuộc tính HTML là bản của máy chủ).
 * Lệch với nó nghĩa là người dùng đã gõ. */
function _oDaSua(o) {
  if (o.type === "checkbox" || o.type === "radio") return o.checked !== o.defaultChecked;
  if (o.tagName === "SELECT") {
    const mac = o.querySelector("option[selected]");
    return o.value !== (mac ? mac.value : (o.options[0] || {}).value);
  }
  return o.value !== o.defaultValue;
}

function _luuDangGo(goc) {
  const giu = { gia: new Map(), oFocus: null, dau: null, cuoi: null };
  if (!goc) return giu;
  $$("input, textarea, select", goc).forEach((o) => {
    const k = _khoaO(o);
    if (_oDaSua(o)) {
      giu.gia.set(k, o.type === "checkbox" || o.type === "radio" ? o.checked : o.value);
    }
    if (document.activeElement === o) {
      giu.oFocus = k;
      // selectionStart ném với input type=email/number -> bọc try.
      try { giu.dau = o.selectionStart; giu.cuoi = o.selectionEnd; } catch { /* không có con trỏ */ }
    }
  });
  return giu;
}

function _traDangGo(goc, giu) {
  if (!goc) return;
  $$("input, textarea, select", goc).forEach((o) => {
    const k = _khoaO(o);
    if (giu.gia.has(k)) {
      const v = giu.gia.get(k);
      if (o.type === "checkbox" || o.type === "radio") o.checked = v;
      else o.value = v;
    }
    if (giu.oFocus === k) {
      o.focus();
      if (giu.dau != null && o.setSelectionRange) {
        try { o.setSelectionRange(giu.dau, giu.cuoi); } catch { /* ô không nhận con trỏ */ }
      }
    }
  });
}

async function loadContactDetail(id) {
  let contact;
  try { contact = await api(`/contacts/${id}`); }
  catch (e) { $("#contactdetail").innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  const points = (contact.contact_points || []).map((point) => `
    <div class="identity-card">${srcBadge(point.channel)}<div><b>${esc(point.account_name)}</b>
      <small>${esc(point.handle || point.external_user_id)}</small></div>
      <span>${clock(point.last_seen)}</span></div>`).join("");
  const consents = (contact.consents || []).map((consent) => `
    <span class="consent consent--${esc(consent.status)}">${esc(consent.purpose)} · ${esc(consent.status)}</span>`).join("");
  const tags = (contact.tags || []).map((tag) => `<span class="profile-tag">${esc(tag.tag)}</span>`).join("");
  const notes = (contact.notes || []).map((note) => `
    <article class="contact-note"><p>${esc(note.body)}</p><small>${esc(note.visibility)} · ${clock(note.created_at)}</small></article>`).join("");
  const conversations = (contact.conversations || []).map((conv) => `
    <button class="timeline-item" type="button" data-open-conv="${conv.id}">
      ${srcBadge(conv.channel)}<span>${esc(conv.account_name)} · ${esc(conv.status)}</span><time>${clock(conv.updated_at)}</time>
    </button>`).join("");
  /* Panel này bị dựng lại mỗi 6 giây (refresh -> loadContacts -> hàm này).
   * Không giữ chữ đang gõ thì ô ghi chú bàn giao 5000 ký tự biến mất giữa
   * chừng: không lỗi, không toast, người trực chỉ thấy ô trống và tưởng
   * mình bấm nhầm. Cùng bài đã giải cho ô sửa tin nhắn bằng `state.suaText`
   * và cho ô Sức khoẻ kênh bằng `state.sucKhoeKenh`. */
  const oGoc = $("#contactdetail");
  const dangGo = _luuDangGo(oGoc);
  oGoc.innerHTML = `
    <div class="profile-head"><span class="avatar avatar--lg">${esc((contact.display_name || "K").slice(0, 1).toUpperCase())}</span>
      <div><p class="eyebrow">CUSTOMER 360</p><h2>${esc(contact.display_name || "Khách")}</h2>
        <p>${esc(contact.phone || "Chưa có số điện thoại")} · ${esc(contact.email || "Chưa có email")}</p></div>
      <span class="privacy-pill">${contact.pii_masked ? "PII đã ẩn theo quyền" : "PII được phép xem"}</span></div>
    <div class="profile-grid"><div><span>Trạng thái</span><b>${esc(contact.status)}</b></div><div><span>Phiên bản</span><b>${contact.version}</b></div>
      <div><span>Lần đầu</span><b>${clock(contact.first_seen)}</b></div><div><span>Gần nhất</span><b>${clock(contact.last_seen)}</b></div></div>
    <h3 class="subhead">Người phụ trách</h3>
    <div class="profile-actions">
      <div class="profile-tags">${chuKhach(contact)}</div>
      <div class="inline-action">
        <button type="button" class="btn btn--sm" id="contact-giao"
                data-contact-giao="${esc(contact.id)}"
                data-chu="${esc(contact.owner_ten_dang_nhap || "")}">Giao / thu hồi</button>
        <button type="button" class="btn btn--sm btn--ghost"
                data-contact-lichsu="${esc(contact.id)}">Lịch sử giao</button>
        ${state.toiQuyen.has("khach.xoa")
          /* Đếm trước khi xoá — luồng bốn mắt. Chỉ hiện cho người có
             khach.xoa: người khác bấm là ăn 403, và một nút chắc chắn
             thất bại thì không phải là nút. */
          ? `<button type="button" class="btn btn--sm btn--ghost"
                data-contact-rt="${esc(contact.id)}">Đếm dữ liệu sẽ xoá</button>`
          : ""}
      </div>
    </div>
    <div id="contact-lichsu-giao"></div>
    ${oTruongKhach(contact)}
    <h3 class="subhead">Nhãn chăm sóc</h3>
    <div class="profile-actions"><div class="profile-tags">${tags || '<span class="empty">Chưa có nhãn.</span>'}</div>
      <form id="contact-tag-form" class="inline-action"><input name="tag" maxlength="80" required placeholder="VIP, cần gọi lại…"><button class="btn btn--sm" type="submit">Thêm nhãn</button></form></div>
    <h3 class="subhead">Danh tính theo kênh</h3><div class="identity-grid">${points || '<p class="empty">Chưa có danh tính.</p>'}</div>
    <h3 class="subhead">Consent</h3><div class="consent-row">${consents || '<span class="empty">Chưa ghi nhận consent.</span>'}</div>
    <form id="contact-consent-form" class="consent-form">
      <input name="purpose" maxlength="80" required placeholder="Mục đích, ví dụ marketing">
      <select name="status" aria-label="Trạng thái consent"><option value="granted">Đồng ý</option><option value="denied">Từ chối</option><option value="withdrawn">Rút lại</option></select>
      <input name="source" maxlength="300" required placeholder="Nguồn bằng chứng">
      <button class="btn btn--sm" type="submit">Ghi consent</button>
    </form>
    <h3 class="subhead">Ghi chú nội bộ</h3><div class="contact-notes">${notes || '<span class="empty">Chưa có ghi chú.</span>'}</div>
    <form id="contact-note-form" class="note-form"><textarea name="body" maxlength="5000" required placeholder="Thông tin cần bàn giao cho đội chăm sóc…"></textarea>
      <select name="visibility" aria-label="Ai đọc được ghi chú này"><option value="team">Cả đội</option><option value="manager">Quản lý</option></select><button class="btn btn--sm" type="submit">Lưu ghi chú</button></form>
    <h3 class="subhead">Hội thoại</h3><div class="timeline">${conversations || '<p class="empty">Chưa có hội thoại.</p>'}</div>`;

  /* Trả lại NGAY sau khi dựng, trước khi gắn sự kiện: gán `.value` không
     phát `input`, nên không có nguy cơ kích hoạt nhầm handler nào. */
  _traDangGo(oGoc, dangGo);

  $("#contact-truong-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const gia_tri = {};
    $$("[data-tk]", ev.currentTarget).forEach((o) => {
      gia_tri[o.dataset.tk] = o.type === "checkbox" ? o.checked : o.value;
    });
    /* Gom các ô "chọn nhiều" theo mã: mỗi ô tick là một phần tử, và một
       trường không tick ô nào phải gửi mảng RỖNG chứ không vắng mặt — vắng
       mặt nghĩa là "không đụng tới", nên bỏ hết tick sẽ không xoá được. */
    const daGom = new Set();
    $$("[data-tk-nhieu]", ev.currentTarget).forEach((o) => {
      const ma = o.dataset.tkNhieu;
      if (!daGom.has(ma)) { gia_tri[ma] = []; daGom.add(ma); }
      if (o.checked) gia_tri[ma].push(o.value);
    });
    try {
      await api(`/contacts/${id}/truong`, {
        method: "PUT", body: JSON.stringify({ gia_tri }),
      });
      toast("Đã lưu thông tin thêm.");
      await loadContactDetail(id);
    } catch (e) { toast(e.message, true); }
  });

  $("[data-contact-giao]")?.addEventListener("click", (ev) =>
    giaoKhach(ev.currentTarget.dataset.contactGiao, ev.currentTarget.dataset.chu));

  $("[data-contact-lichsu]")?.addEventListener("click", async (ev) => {
    const hop = $("#contact-lichsu-giao");
    if (hop.innerHTML) { hop.innerHTML = ""; return; }   // bấm lần hai là đóng
    try {
      const ds = (await api(`/contacts/${ev.currentTarget.dataset.contactLichsu}`
                            + "/chu-so-huu/lich-su")).lich_su;
      hop.innerHTML = ds.length
        ? `<div class="contact-notes">${ds.map((d) => `
            <article class="contact-note">
              <p>${d.owner_ho_ten
                    ? `Giao cho <b>${esc(d.owner_ho_ten)}</b>`
                    : "<b>Thu hồi</b> — khách quay về của chung"} · ${esc(d.ly_do)}</p>
              <small>${esc(d.actor_ten_dang_nhap || "?")} · ${clock(d.luc)}</small>
            </article>`).join("")}</div>`
        : '<p class="empty">Khách này chưa từng được giao cho ai.</p>';
    } catch (e) { toast(e.message, true); }
  });

  $("#contact-tag-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const tag = String(new FormData(form).get("tag") || "").trim();
    if (!tag) return;
    try {
      await api(`/contacts/${id}/tags`, { method: "POST", body: JSON.stringify({ tag }) });
      toast("Đã thêm nhãn khách hàng.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $("#contact-note-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    values.body = String(values.body || "").trim();
    if (!values.body) return;
    try {
      await api(`/contacts/${id}/notes`, { method: "POST", body: JSON.stringify(values) });
      toast("Đã lưu ghi chú nội bộ.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $("#contact-consent-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const values = Object.fromEntries(new FormData(form));
    const purpose = String(values.purpose || "").trim();
    if (!purpose) return;
    try {
      await api(`/contacts/${id}/consents/${encodeURIComponent(purpose)}`, {
        method: "PUT",
        body: JSON.stringify({ status: values.status, source: String(values.source || "").trim(), evidence: { captured_via: "dashboard" } }),
      });
      toast("Đã cập nhật consent và nhật ký kiểm toán.");
      await loadContactDetail(id);
    } catch (error) { toast(error.message, true); }
  });
  $$('[data-open-conv]').forEach((button) => button.addEventListener("click", () => {
    state.openConv = button.dataset.openConv;
    doiMan("hoithoai");
  }));
}


