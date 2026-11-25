/* ---------------- Ngăn bên: căn cứ đầy đủ & chi tiết lượt xử lý ----------------
 *
 * UX-16-01 và MD-UX-18-02. Hai thứ dài — căn cứ đầy đủ của một câu trả lời,
 * và cả một lượt AI từ tin khách tới bản nháp — mở trong MỘT ngăn bên phải
 * (điện thoại: tấm trượt từ dưới), không bung giữa luồng tin.
 *
 * Ngăn gắn vào <body>, KHÔNG vào #convdetail: khung hội thoại dựng lại bằng
 * innerHTML mỗi lần làm mới (SSE hoặc nhịp 6 giây), và một ngăn nằm trong đó
 * sẽ biến mất giữa lúc người trực đang đọc. Nội dung là ảnh chụp lúc bấm —
 * căn cứ của một tin đã gửi không đổi theo thời gian.
 *
 * Tệp riêng vì 19-trach-nhiem.js đã dài; `19b` để đóng gói nằm ngay sau nó.
 */

function moNganPhu({ tieu_de, phu = "", html }) {
  dongNganPhu();
  const nen = document.createElement("div");
  nen.className = "ngan-phu-nen";
  nen.id = "nganPhuNen";
  const n = document.createElement("aside");
  n.className = "ngan-phu";
  n.id = "nganPhu";
  n.setAttribute("role", "dialog");
  n.setAttribute("aria-modal", "true");
  n.setAttribute("aria-labelledby", "nganPhuTieu");
  n.innerHTML = `<div class="ngan-phu__dau">
      <div class="ngan-phu__chu"><h3 class="ngan-phu__tieu" id="nganPhuTieu">${esc(tieu_de)}</h3>
        ${phu ? `<span class="ngan-phu__phu">${esc(phu)}</span>` : ""}</div>
      <button type="button" class="btn btn--sm btn--ghost" data-ngan-phu-dong aria-label="Đóng" title="Đóng (Esc)">✕ Đóng</button>
    </div>
    <div class="ngan-phu__than" id="nganPhuThan">${html}</div>`;
  document.body.append(nen, n);
  // Mỗi lần mở một mã mới: kết quả tải về muộn của lần mở TRƯỚC không được
  // đè lên ngăn đang hiện nội dung khác.
  state.nganPhuMa = (state.nganPhuMa || 0) + 1;
  $("[data-ngan-phu-dong]", n)?.focus();
  return state.nganPhuMa;
}

function capNhatNganPhu(ma, html) {
  const than = $("#nganPhuThan");
  if (than && state.nganPhuMa === ma) than.innerHTML = html;
}

function dongNganPhu() {
  $("#nganPhu")?.remove();
  $("#nganPhuNen")?.remove();
}

document.addEventListener("click", (ev) => {
  if (ev.target.closest("[data-ngan-phu-dong]") || ev.target.id === "nganPhuNen") dongNganPhu();
});
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && $("#nganPhu")) dongNganPhu();
});

/* ---------------- Một lượt AI, theo thứ tự xảy ra ----------------
 * Tin khách → tra tài liệu → gọi công cụ → kiểm chính sách → bản nháp /
 * phê duyệt, rồi nhật ký thô của từng bước (gấp lại). Hàm THUẦN — test
 * chạy thật bằng node trên một lượt mẫu.
 *
 * Nguồn: `/api/nhat-ky/hoi-thoai/{cid}/luot/{luot_id}` — máy chủ chặn theo
 * kênh của người xem VÀ chặn lượt không thuộc hội thoại trong đường dẫn, nên
 * nhân viên trực xem được lượt của khách mình mà không cần quyền nhật ký cả
 * cửa hàng. */
function veLuotXuLy(l) {
  if (!l) return '<p class="empty">Không có dữ liệu lượt này.</p>';
  const tl = l.tra_loi || [];
  const dv = (tl[0] && tl[0].dau_vet) || {};
  const buocLuot = (so, ten, tt, than) => `<li class="luot__buoc luot__buoc--${tt}">
      <span class="luot__so" aria-hidden="true">${so}</span>
      <div class="luot__noi"><h4 class="luot__ten">${ten}</h4>${than}</div></li>`;

  const khach = l.tin_khach
    ? `<span class="msg__meta">${esc(gioTin(l.tin_khach.luc))}</span>
       <p class="luot__chu">${esc(l.tin_khach.noi_dung || "(không đọc được nội dung)")}</p>`
    : '<p class="hint">Không tìm thấy tin khách mở đầu lượt.</p>';

  const nguon = sapXepNguon(dv.tri_thuc || []);
  const raG = nguon.length
    ? `<p class="hint">${nguon.length} đoạn tài liệu, xếp theo mức khớp</p><ol class="nguon-ds">${nguon.map((t, i) => `<li class="nguon">
        <div class="nguon__dau"><span class="nguon__hang">${i + 1}</span><b>${esc(t.title || "(không tên)")}</b>${
          t.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(t.version)}</span>` : ""}</div>
        ${veTrich(t.trich)}</li>`).join("")}</ol>`
    : '<p class="hint">Không trích tài liệu nào.</p>';

  const cc = dv.cong_cu || [];
  const congCu = cc.length
    ? `<ul class="ctt__ds">${cc.map((c) => `<li><details class="ctt__toan"><summary><b>${esc(c.ten)}</b>${
        c.ms != null ? ` <span class="hint">${esc(c.ms)} ms</span>` : ""}</summary>
        <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></details></li>`).join("")}</ul>`
      + (dv.cong_cu_bo_bot ? `<p class="hint">… và ${esc(dv.cong_cu_bo_bot)} lần gọi nữa không lưu chi tiết.</p>` : "")
    : '<p class="hint">Không gọi công cụ nào.</p>';

  const cu = dv.can_cu || {};
  const che = dv.che_do || {};
  const chinhSach = [
    cu.nhan ? dongCT("Căn cứ", `<span class="tag tag--${TAG_CAN_CU[cu.ma] || "plain"}">${esc(cu.nhan)}</span>`) : "",
    cu.huong_dan ? `<p class="hint">${esc(cu.huong_dan)}</p>` : "",
    dv.luoi ? dongCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma)) : dongCT("Lớp lưới", "không lưới nào bắt"),
    dv.chuyen_nguoi && dv.chuyen_nguoi.co ? dongCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : "",
    che.chung ? dongCT("Chế độ", esc((che.chung === "auto" ? "AI tự gửi" : "AI soạn, người duyệt")
      + (che.duyet_rieng ? " · hội thoại này bắt duyệt trước khi gửi" : ""))) : "",
  ].join("");
  const ttChinhSach = dv.luoi || (dv.chuyen_nguoi && dv.chuyen_nguoi.co) ? "canh" : "xong";

  const traLoi = tl.length ? tl.map((t) => `<div class="luot__tra-loi">
      <span class="msg__meta">${esc([gioTin(t.luc), TRANG_THAI_TIN[t.trang_thai] || t.trang_thai,
        t.sua_boi ? "sửa bởi " + t.sua_boi : "", t.duyet_boi ? "duyệt bởi " + t.duyet_boi : ""]
        .filter(Boolean).join(" · "))}</span>
      <p class="luot__chu">${esc(t.noi_dung || "")}</p></div>`).join("")
    : '<p class="hint">Lượt này không để lại câu trả lời — có thể đã chuyển người hoặc lỗi.</p>';
  const ttTraLoi = tl.some((t) => t.trang_thai === "cancelled") ? "loi"
    : tl.some((t) => t.trang_thai === "draft") ? "canh" : tl.length ? "xong" : "canh";

  const nhatKy = (l.buoc || []).length ? `<details class="ctt__toan luot__nhat-ky">
      <summary>Nhật ký các bước (${l.buoc.length})</summary>
      ${l.buoc.map((b) => `<div class="lichsu__dong"><b>${esc(b.hanh_dong)}</b>
        <span class="msg__meta">${esc(gioTin(b.luc))} · ${esc((b.trang_thai || {}).nhan || "")}${
          b.ket_qua ? " · " + esc(b.ket_qua) : ""}</span></div>`).join("")}
    </details>` : "";
  const ket = l.ket_qua ? `<p class="luot__ket">Kết thúc lượt: <b>${esc(l.ket_qua.hanh_dong || "")}</b>${
    l.ket_qua.luc ? ` · ${esc(gioTin(l.ket_qua.luc))}` : ""}</p>` : "";

  return `<ol class="luot">
      ${buocLuot(1, "Tin khách", l.tin_khach ? "xong" : "canh", khach)}
      ${buocLuot(2, "Tra tài liệu", nguon.length ? "xong" : "trong", raG)}
      ${buocLuot(3, "Gọi công cụ", cc.length ? "xong" : "trong", congCu)}
      ${buocLuot(4, "Kiểm tra chính sách", ttChinhSach, chinhSach)}
      ${buocLuot(5, "Bản nháp / phê duyệt", ttTraLoi, traLoi)}
    </ol>${ket}${nhatKy}`;
}

async function moLuotXuLy(luotId) {
  const cid = state.openConv;
  if (!cid || !luotId) return;
  const ma = moNganPhu({ tieu_de: "Chi tiết lượt xử lý",
    phu: `Lượt AI ${String(luotId).slice(0, 8)}`, html: '<p class="hint">Đang tải…</p>' });
  try {
    const l = await api(`/nhat-ky/hoi-thoai/${encodeURIComponent(cid)}/luot/${encodeURIComponent(luotId)}`);
    capNhatNganPhu(ma, veLuotXuLy(l));
  } catch (e) {
    capNhatNganPhu(ma, `<p class="empty">Không tải được lượt xử lý: ${esc(e.message)}</p>`);
  }
}

document.addEventListener("click", (ev) => {
  const luot = ev.target.closest("[data-xem-luot]");
  if (luot) { moLuotXuLy(luot.dataset.xemLuot); return; }
  const cc = ev.target.closest("[data-can-cu-day-du]");
  if (!cc) return;
  const c = state.convDangMo;
  const m = c && (c.messages || []).find((x) => String(x.id) === cc.dataset.canCuDayDu);
  if (!m) { toast("Tin này không còn trong hội thoại đang mở.", true); return; }
  const dv = m.dau_vet_ai || {};
  moNganPhu({
    tieu_de: m.delivery_status === "draft" ? "Căn cứ của bản nháp AI" : "Căn cứ của câu trả lời",
    phu: [gioTin(m.created_at), TRANG_THAI_TIN[m.delivery_status] || ""].filter(Boolean).join(" · "),
    html: veCanCuDayDu(m) + (dv.luot_id ? `<div class="ctt__nut">
      <button type="button" class="btn btn--sm btn--ghost" data-xem-luot="${esc(dv.luot_id)}">Xem chi tiết lượt xử lý</button></div>` : ""),
  });
});
