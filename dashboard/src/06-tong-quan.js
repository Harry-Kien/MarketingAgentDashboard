/* ---------------- tên kênh ----------------
   Bảng "Khách đến từ đâu" (`/api/analytics/khach`) đã gỡ khỏi màn ngày
   20.11.2026: nó đếm "tự xử lý" theo `status = 'auto'`, đúng con số tô
   hồng mà màn Phân tích thay bằng số đếm theo sự kiện. */
const KENH_TEN = {
  zalocrm: "Zalo cá nhân", chatwoot: "Kênh tương thích", facebook: "Facebook",
  instagram: "Instagram", whatsapp: "WhatsApp", web: "Website", email: "Email",
};

/* ---------------- các hệ thống đang chạy ---------------- */

/* Màn vận hành chỉ hiển thị các dịch vụ thuộc sản phẩm hiện tại. Connector
   tương thích cũ vẫn có thể chạy ở backend trong giai đoạn chuyển đổi nhưng
   không được biến thành một ứng dụng con hay thương hiệu trên dashboard. */
/* `dangCho` = NGƯỜI vừa bấm nút, đang đợi và cần phản hồi ngay.
   Vòng làm mới 6 giây gọi hàm này KHÔNG kèm cờ, và phải vẽ đè im lặng.

   Bản đầu gán ô chờ vô điều kiện: cứ 6 giây panel trắng xoá rồi hiện lại
   sau khi dò xong 5 dịch vụ. Đó là cái nhấp nháy người dùng nhìn thấy. */
async function loadHeThong(dangCho = false) {
  const box = $("#hethong");
  const btn = $("#hethongrun");
  if (btn) btn.disabled = true;
  if (dangCho || !box.innerHTML.trim()) {
    box.innerHTML = '<p class="empty">Đang hỏi từng dịch vụ…</p>';
  }
  try {
    const d = await api("/he-thong");
    const visible = d.dich_vu.filter((x) => !["zalocrm", "chatwoot"].includes(x.ma));
    const running = visible.filter((x) => x.song).length;
    $("#c-hethong").textContent = `${running}/${visible.length}`;
    box.innerHTML = visible.map((x) => `<div class="row">
        <span class="row__flag row__flag--${x.song ? "auto" : "halt"}"></span>
        <div class="row__main">
          <b>${esc(x.ten)}${x.chinh ? " · trang bạn đang xem" : ""}</b>
          <span class="row__sub">${esc(x.mo_ta)}
            ${x.nhung_duoc ? "· mở ngay trong đây"
              : x.can_dang_nhap ? "· cần đăng nhập riêng" : ""}</span>
        </div>
        ${x.di_toi_man
          /* Chưa nối được thì KHÔNG có gì để "Mở". Đưa người dùng tới màn
             làm được việc, và nói đúng việc nút làm. Bản đầu render <a href>
             trỏ về chính dashboard: bấm vào trang quay về trang chính, nhìn
             như nút hỏng. */
          ? `<button type="button" class="btn btn--sm" data-di-toi="${esc(x.di_toi_man)}">Cấu hình</button>`
          : !x.song
          ? `<span class="tag tag--halt">không chạy</span>`
          : x.nhung_duoc
            /* Nhúng được thì mở NGAY TRONG dashboard. Nút mở tab mới vẫn
               giữ bên cạnh: iframe hỏng thì người vận hành phải còn một
               đường vào, nếu không một lỗi giao diện thành mất quyền
               truy cập cả hệ thống con. */
            ? `<button type="button" class="btn btn--sm" data-mo-trong="${esc(x.ma)}">Mở</button>
               <a class="btn btn--sm btn--ghost" href="${esc(x.url)}" target="_blank" rel="noopener" title="Mở tab mới">↗</a>`
            : `<a class="btn btn--sm" href="${esc(x.url)}" target="_blank" rel="noopener">Mở</a>`}
      </div>`).join("");
    $("#hethongvisao").textContent = "Các thành phần vận hành dùng chung một dashboard, cùng xác thực và nhật ký kiểm toán.";
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* Bọc trong arrow function, KHÔNG gán thẳng `loadHeThong`: gán thẳng thì
   tham số đầu là đối tượng Event — truthy, nên nó vô tình chạy đúng. Dựa
   vào tình cờ là thứ hỏng ở lần refactor sau. */
$("#hethongrun")?.addEventListener("click", () => loadHeThong(true));

/* Bấm "Mở" ở màn Hệ thống -> nhảy sang màn Kết nối và mở đúng app đó.
   Gắn trên vùng chứa chứ không trên từng nút: danh sách dựng lại sau mỗi
   lần Kiểm tra, và listener gắn trên nút cũ thì chết theo nút cũ. */
/* Nút "Cấu hình" của mục chưa nối: chuyển sang màn tương ứng trong chính
   dashboard, không mở tab mới. Gắn trên vùng chứa vì danh sách được dựng
   lại sau mỗi lần làm mới. */
$("#hethong")?.addEventListener("click", (e) => {
  const diToi = e.target.closest("[data-di-toi]");
  if (diToi) {
    e.preventDefault();
    doiMan(diToi.dataset.diToi);
    return;
  }
  const nut = e.target.closest("[data-mo-trong]");
  if (!nut) return;
  moManKetNoi(nut.dataset.moTrong);
});

/* ---------------- sức khoẻ hệ thống ---------------- */

/* KHÔNG tự chạy khi mở trang: phép kiểm gọi model thật và mất vài giây.
   Người vận hành bấm khi cần, không phải mỗi lần liếc qua dashboard. */
const HEALTH_TONE = { tot: "auto", canh_bao: "assist", hong: "halt" };
const HEALTH_LABEL = { tot: "Tốt", canh_bao: "Cảnh báo", hong: "Hỏng" };

$("#healthrun")?.addEventListener("click", async () => {
  const box = $("#health");
  const btn = $("#healthrun");
  btn.disabled = true;
  box.innerHTML = '<p class="empty">Đang gọi thật từng dịch vụ…</p>';
  try {
    const d = await api("/suc-khoe");
    box.innerHTML =
      `<div class="row"><span class="row__flag row__flag--${HEALTH_TONE[d.trang_thai]}"></span>
         <div class="row__main"><b>Tổng thể: ${HEALTH_LABEL[d.trang_thai] || d.trang_thai}</b>
         <span class="row__sub">kiểm trong ${d.kiem_trong_ms} ms · agent ${d.agent?.enabled ? "đang chạy" : "đã ngắt"} · chế độ ${esc(d.agent?.mode || "?")}</span></div></div>` +
      d.muc.map((m) => `<div class="row">
         <span class="row__flag row__flag--${HEALTH_TONE[m.trang_thai] || "plain"}"></span>
         <div class="row__main"><b>${esc(m.ten)}</b>
         <span class="row__sub">${esc(m.ghi_chu)}</span></div>
         <span class="tag tag--${HEALTH_TONE[m.trang_thai] || "plain"}">${HEALTH_LABEL[m.trang_thai] || m.trang_thai}</span>
       </div>`).join("");
  } catch (e) {
    box.innerHTML = `<p class="empty">Không kiểm được: ${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
});

/* ---------------- tri thức ---------------- */

async function loadDocs() {
  if (!state.knowledgeAccounts) {
    state.knowledgeAccounts = await api("/knowledge/accounts");
    state.knowledgeAccount = state.knowledgeAccount || state.knowledgeAccounts[0]?.id || "";
    const select = $("#knowledge-account");
    select.innerHTML = state.knowledgeAccounts.map((account) =>
      `<option value="${esc(account.id)}">${esc(account.name)} · ${esc(account.channel)}</option>`
    ).join("");
    select.value = state.knowledgeAccount;
    select.addEventListener("change", () => {
      state.knowledgeAccount = select.value;
      $('#probeform [name="account_id"]').value = select.value;
      loadDocs();
    });
  }
  $('#probeform [name="account_id"]').value = state.knowledgeAccount || "";
  if (!state.knowledgeAccount) {
    $("#docs").innerHTML = '<p class="empty">Bạn chưa được cấp tài khoản kênh để quản lý tri thức.</p>';
    return;
  }
  const docs = await api(`/knowledge?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
  $("#c-trithuc").textContent = docs.length;
  const canEdit = state.toiQuyen && state.toiQuyen.has("cau_hinh.sua");
  $("#docs").innerHTML = docs.length ? docs.map((d) => `<div class="row">
      <span class="row__flag row__flag--${d.status === "published" ? "auto" : "assist"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(d.title)}
          <span class="tag tag--${d.status === "published" ? "auto" : "assist"}">${d.status === "published" ? `Published v${d.published_version}` : "Draft"}</span>
        </span>
        <span class="row__sub">${d.chunks} đoạn · ${d.draft_version ? `Draft v${d.draft_version} · index ${esc(d.index_status)}` : "không có Draft"}${d.index_error ? ` · ${esc(d.index_error)}` : ""}</span>
      </span>
      <span class="row__side">
        <span class="row__nut">
          ${canEdit ? `<button type="button" class="btn btn--sm" data-doc-edit="${d.id}">Sửa Draft</button>` : ""}
          ${canEdit && d.draft_version_id && d.index_status === "ready" ? `<button type="button" class="btn btn--sm btn--go" data-doc-publish="${d.id}" data-version="${d.draft_version_id}">Publish v${d.draft_version}</button>` : ""}
          <button type="button" class="btn btn--sm" data-doc-history="${d.id}" data-published="${d.published_version_id || ""}">Lịch sử</button>
          ${canEdit ? `<button type="button" class="btn btn--sm btn--halt" data-doc-archive="${d.id}">Lưu trữ</button>` : ""}
        </span>
        <span class="row__time">${clock(d.updated_at)}</span>
      </span>
    </div>`).join("")
    : '<p class="empty">Chưa có tài liệu. Tài liệu mới sẽ ở Draft cho tới khi được Publish.</p>';

  $$('[data-doc-edit]').forEach((b) =>
    b.addEventListener("click", async () => {
      const d = await api(`/knowledge/${b.dataset.docEdit}?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
      const f = $("#docform");
      f.elements.document_id.value = d.id;
      f.elements.title.value = d.title;
      f.elements.text.value = d.draft_content || d.published_content || "";
      $("#docsave").textContent = d.draft_version ? `Lưu Draft v${d.draft_version}` : "Tạo Draft mới";
      f.elements.title.focus();
    })
  );
  $$('[data-doc-publish]').forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await api(`/knowledge/${b.dataset.docPublish}/publish`, {
        method: "POST",
        body: JSON.stringify({ account_id: state.knowledgeAccount, version_id: b.dataset.version }),
      });
      toast(r.already_published ? "Phiên bản này đã Published trước đó." : `Đã Publish v${r.version}.`);
      await loadDocs();
    } catch (e) { toast(e.message, true); }
    finally { b.disabled = false; }
  }));
  $$('[data-doc-history]').forEach((b) => b.addEventListener("click", async () => {
    const versions = await api(`/knowledge/${b.dataset.docHistory}/versions?account_id=${encodeURIComponent(state.knowledgeAccount)}`);
    $("#docversions").innerHTML = `<h3 class="panel__head">Lịch sử phiên bản</h3>` + versions.map((v) => `<div class="row">
      <span class="row__flag row__flag--${v.status === "published" ? "auto" : v.status === "draft" ? "assist" : "plain"}"></span>
      <span class="row__body"><span class="row__title">v${v.version} · ${esc(v.status)}</span>
        <span class="row__sub">${v.chunk_count} đoạn · index ${esc(v.index_status)} · ${esc(v.content).slice(0, 180)}</span></span>
      <span class="row__side">${canEdit && ["published", "superseded"].includes(v.status) && v.id !== b.dataset.published
        ? `<button type="button" class="btn btn--sm" data-doc-rollback="${b.dataset.docHistory}" data-version="${v.id}">Rollback từ v${v.version}</button>` : ""}
        <span class="row__time">${clock(v.published_at || v.created_at)}</span></span>
    </div>`).join("");
    $$('[data-doc-rollback]').forEach((button) => button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const r = await api(`/knowledge/${button.dataset.docRollback}/rollback`, {
          method: "POST",
          body: JSON.stringify({ account_id: state.knowledgeAccount, version_id: button.dataset.version }),
        });
        toast(`Đã rollback thành Published v${r.version}.`);
        $("#docversions").innerHTML = "";
        await loadDocs();
      } catch (e) { toast(e.message, true); }
      finally { button.disabled = false; }
    }));
  }));
  $$('[data-doc-archive]').forEach((b) => b.addEventListener("click", async () => {
    /* Hỏi trước khi lưu trữ: tài liệu tri thức là CĂN CỨ agent dùng để trả
     * lời. Bấm trượt là agent mất căn cứ — nó không nói sai, nó chuyển người
     * ở mọi câu lẽ ra tự trả lời được, và không ai nhìn ra vì sao. */
    const ten = b.closest(".row")?.querySelector(".row__title")?.firstChild?.textContent || "tài liệu này";
    if (!confirm(`Lưu trữ "${ten.trim()}"?\n\n`
        + "Agent sẽ thôi dùng nó làm căn cứ trả lời. Lịch sử phiên bản vẫn được giữ.")) return;
    b.disabled = true;
    try {
      await api(`/knowledge/${b.dataset.docArchive}?account_id=${encodeURIComponent(state.knowledgeAccount)}`, { method: "DELETE" });
      toast("Đã lưu trữ tài liệu; lịch sử vẫn được bảo toàn.");
      await loadDocs();
    } catch (e) {
      toast(e.message, true);
      b.disabled = false;
    }
  }));
}

$("#docform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = new FormData(ev.target);
  const documentId = f.get("document_id");
  const button = $("#docsave");
  button.disabled = true;
  toast("Đang lưu Draft và tạo embedding…");
  try {
    const r = await api(documentId ? `/knowledge/${documentId}/draft` : "/knowledge", {
      method: documentId ? "PUT" : "POST",
      body: JSON.stringify({ account_id: f.get("account_id"), title: f.get("title"), text: f.get("text") }),
    });
    toast(`Đã lưu Draft v${r.version} (${r.chunks} đoạn). Chưa dùng trong RAG cho tới khi Publish.`);
    ev.target.reset();
    ev.target.elements.account_id.value = state.knowledgeAccount;
    $("#docsave").textContent = "Lưu Draft";
    await loadDocs();
  } catch (e) { toast(e.message, true); }
  finally { button.disabled = false; }
});

$("#docnew").addEventListener("click", () => {
  const f = $("#docform");
  f.reset();
  f.elements.account_id.value = state.knowledgeAccount || "";
  $("#docsave").textContent = "Lưu Draft";
});

$("#probeform").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const q = new FormData(ev.target).get("question");
  try {
    const r = await api("/knowledge/probe", {
      method: "POST", body: JSON.stringify({ account_id: state.knowledgeAccount, question: q }),
    });
    $("#probe").innerHTML = r.hits.length ? r.hits.map((h) => `<div class="row">
        <span class="row__flag row__flag--spend"></span>
        <span class="row__body">
          <span class="row__title">${esc(h.doc)} · v${h.version}</span>
          <span class="row__sub">${esc(h.excerpt)} · chunk ${esc(h.chunk_id || "—")}</span>
        </span>
        <span class="row__side"><span class="probe__score">${h.score.toFixed(3)}</span></span>
      </div>`).join("")
      : '<p class="empty">Không tìm thấy đoạn nào đủ khớp. Agent sẽ chuyển câu này cho người.</p>';
  } catch (e) { toast(e.message, true); }
});

