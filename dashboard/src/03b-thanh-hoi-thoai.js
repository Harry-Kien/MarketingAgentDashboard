/* ---------------- Thanh thông tin hội thoại (mục 6 của bảng việc) ----------------
 *
 * Cấu trúc chủ dự án chốt (22.11.2026):
 *
 *   Tên khách hàng | Nhãn hội thoại | Customer 360 | Hành động xử lý | Chi tiết
 *
 * Trước bản này thanh ấy chở MƯỜI thứ một lúc: trạng thái, SLA, kênh, chế
 * độ, ưu tiên, version, ba bốn nút xử lý, nút ghi chú. Người trực mở hội
 * thoại để đọc khách nói gì — mười thứ thường trực là mười thứ mắt phải
 * nhảy qua trước khi tới câu đầu tiên. Nên:
 *
 *   · trạng thái, kênh, chế độ AI/Mode    -> bỏ (danh sách bên trái đã có),
 *                                           hoặc vào "Chi tiết" khi cần;
 *   · ưu tiên, Version, SLA               -> "Chi tiết" (SLA không hiện
 *                                           thường trực — cảnh báo SLA tới
 *                                           người trực qua chuông);
 *   · ghi chú nội bộ                      -> một kiểu soạn trong ô soạn tin;
 *   · nút xử lý                           -> MỘT nút chính + menu "⋯".
 *
 * Tệp riêng vì `03-hoi-thoai.js` đã gần trần 1000 dòng. Đặt tên `03b` để
 * đóng gói nằm ngay sau 03, trước Customer 360 (04).
 */

/* Các hành động xử lý. `id` giữ đúng id nút cũ: trình nghe ở dưới và các
 * test nút chết tìm theo id viết đủ. */
const HANH_DONG_HT = {
  tiepQuan: { id: "btn-take", nhan: "Tiếp quản", lop: "btn--halt",
              goi_y: "Nhận hội thoại về mình; AI dừng gửi" },
  giao: { id: "btn-giao", nhan: "Chuyển nhân viên…", lop: "",
          goi_y: "Giao hội thoại cho một nhân viên khác của kênh" },
  ketThuc: { id: "btn-release", nhan: "Kết thúc tiếp quản", lop: "",
             goi_y: "Trả hội thoại về chế độ AI gợi ý" },
  tuTraLoi: { id: "btn-chedo", nhan: "Để agent tự trả lời", lop: "", che_do: "auto",
              goi_y: "AI tự gửi câu trả lời, không chờ duyệt" },
  duyetTruoc: { id: "btn-chedo", nhan: "Duyệt trước khi gửi", lop: "", che_do: "assist",
                goi_y: "AI soạn xong chờ người duyệt rồi mới gửi" },
  giaiQuyet: { id: "btn-giai-quyet", nhan: "Đã giải quyết", lop: "btn--go",
               goi_y: "Đóng vụ việc; khách nhắn tiếp thì tự mở lại" },
  moLai: { id: "btn-mo-lai", nhan: "Mở lại", lop: "",
           goi_y: "Mở lại hội thoại đã giải quyết để xử lý tiếp" },
};

/* Hội thoại này, với người này, được làm gì — và việc nào là việc CHÍNH.
 *
 * Hàm THUẦN (không đọc `state`, không đụng DOM) để test chạy thật được bằng
 * node trên từng ô của bảng trạng thái × quyền. Luật nút trước đây nằm rải
 * trong một chuỗi template, mỗi nút một điều kiện riêng, và chỉ test được
 * bằng regex — đúng kiểu xanh giả với mã đã bị tắt.
 *
 * `ng` = { toiId, quyen: Set, giaoDuoc: bool (máy chủ nói giao người khác
 * được) }. Trả { chinh, them: [...], giu } — `giu` là dòng chữ "X đang giữ"
 * khi không có nút nào để bấm, để người xem biết VÌ SAO không có nút.
 *
 * Máy chủ vẫn chặn từng việc (`hoi_thoai.nhan`, luật can_assign/can_release).
 * Ẩn nút ở đây là để màn hình không mời một 403 — không phải lớp chặn. */
function hanhDongXuLy(c, ng) {
  const co = (q) => !!(ng && ng.quyen && ng.quyen.has(q));
  const kq = { chinh: null, them: [], giu: "" };
  const nguoiGiu = c.mode === "human" && c.assigned_to ? String(c.assigned_to) : "";
  const laCuaToi = !!nguoiGiu && nguoiGiu === String((ng && ng.toiId) || "");
  const nguoiKhacGiu = !!nguoiGiu && !laCuaToi;
  if (nguoiKhacGiu) kq.giu = `${c.assigned_to_ten || "Đồng nghiệp"} đang giữ`;
  // Mọi hành động xử lý đều đòi `hoi_thoai.nhan` ở máy chủ.
  if (!co("hoi_thoai.nhan")) return kq;
  const quanLy = co("hoi_thoai.xem_tat_ca");
  const ds = [];
  if (c.state === "resolved") {
    ds.push(HANH_DONG_HT.moLai);
  } else if (laCuaToi) {
    ds.push(HANH_DONG_HT.giaiQuyet);
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    ds.push(HANH_DONG_HT.ketThuc);
  } else if (nguoiKhacGiu) {
    // Hội thoại đồng nghiệp đang nói dở: chỉ người quản lý được can thiệp.
    // "Tiếp quản" KHÔNG hiện — giành việc là dùng "Chuyển nhân viên…".
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    if (quanLy) ds.push(HANH_DONG_HT.ketThuc, HANH_DONG_HT.giaiQuyet);
  } else {
    // AI đang xử lý, hoặc đã chuyển người mà chưa ai nhận.
    ds.push(HANH_DONG_HT.tiepQuan);
    const taken = c.mode === "human" || c.status === "escalated";
    // Không mời "Để agent tự trả lời" khi đang chờ người (phải tiếp quản
    // rồi kết thúc trước), và không bao giờ trong NHÓM — AI không nói ở đó.
    if (!taken && !laNhom(c)) {
      ds.push(c.mode === "auto" ? HANH_DONG_HT.duyetTruoc : HANH_DONG_HT.tuTraLoi);
    }
    if (ng.giaoDuoc) ds.push(HANH_DONG_HT.giao);
    // Trả hội thoại agent đã chuyển người về cho AI là quyết định của quản
    // lý — nhân viên thường bấm thì máy chủ trả 403 (xem can_release).
    if (c.mode === "human" && quanLy) ds.push(HANH_DONG_HT.ketThuc);
    ds.push(HANH_DONG_HT.giaiQuyet);
  }
  kq.chinh = ds[0] || null;
  kq.them = ds.slice(1);
  return kq;
}

function _nutHanhDong(a, trongMenu) {
  const lop = trongMenu ? "hd-them__muc" : `btn btn--sm ${a.lop}`;
  return `<button type="button" class="${lop}" id="${a.id}" title="${esc(a.goi_y)}"
    ${a.che_do ? `data-chedo="${a.che_do}"` : ""} ${trongMenu ? 'role="menuitem"' : ""}>${esc(a.nhan)}</button>`;
}

/* Một nút chính + menu "⋯". Menu là <details>: mở/đóng không cần JS, và
 * trạng thái mở nhớ trong `state.moHanhDong` vì panel dựng lại mỗi 6 giây —
 * không nhớ là menu tự sập ngay dưới ngón tay người đang chọn. */
function veHanhDongXuLy(c, hd) {
  const mo = state.moHanhDong === String(c.id);
  return `<span class="hd" aria-label="Hành động xử lý">
    ${hd.giu ? `<span class="tag tag--assist">${esc(hd.giu)}</span>` : ""}
    ${hd.chinh ? _nutHanhDong(hd.chinh, false) : ""}
    ${hd.them.length ? `<details class="hd-them" data-hd-them="${esc(c.id)}" ${mo ? "open" : ""}>
      <summary class="btn btn--sm btn--ghost" aria-label="Hành động khác" title="Hành động khác">⋯</summary>
      <div class="hd-them__menu" role="menu">${hd.them.map((a) => _nutHanhDong(a, true)).join("")}</div>
    </details>` : ""}
  </span>`;
}

const ICON_C360 = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>`;

/* Đầu khung chi tiết. Nhãn hội thoại nằm NGAY DƯỚI tên (mục 6.3) — cùng
 * một khối với tên, không phải một hàng riêng kéo dài cả khung.
 *
 * Customer 360 không hiện cho NHÓM (mục 9.7): nhóm không phải một khách
 * hàng, và máy chủ trả 404 cho hồ sơ của nhóm. */
function veThanhThongTin(c, hd) {
  return `<div class="convo__title">
      <div class="convo__danh">
        <div class="convo__ten">
          <span class="convo__name">${esc(c.customer_name || "Khách")}</span>
          ${nhomBadge(c)}
        </div>
        <div class="nhanbar">${nhanHoiThoaiHtml(c)}
          ${state.toiQuyen && state.toiQuyen.has("cong_viec.sua")
            ? `<button type="button" class="btn btn--sm btn--ghost" id="btn-tao-viec-ht"
                title="Tạo công việc gắn với hội thoại và khách này">+ Việc</button>` : ""}</div>
      </div>
      <span class="convo__spacer"></span>
      ${c.contact_id && !laNhom(c) ? `<button type="button" class="btn btn--sm btn--icon" id="open-contact"
        data-contact="${c.contact_id}" title="Customer 360" aria-label="Mở Customer 360">${ICON_C360}</button>` : ""}
      ${veHanhDongXuLy(c, hd)}
      <button type="button" class="btn btn--sm btn--ghost" id="btn-chitiet-ht"
        aria-expanded="${state.moChiTietHT === String(c.id) ? "true" : "false"}">Chi tiết</button>
    </div>`;
}

document.addEventListener("toggle", (ev) => {
  const d = ev.target;
  if (!(d.dataset && d.dataset.hdThem)) return;
  if (d.open) state.moHanhDong = d.dataset.hdThem;
  else if (state.moHanhDong === d.dataset.hdThem) state.moHanhDong = null;
}, true);

/* <details> không tự đóng khi bấm ra ngoài hay chọn một mục — như mọi menu
 * khác thì phải đóng, không thì menu treo đè lên luồng tin. */
document.addEventListener("click", (ev) => {
  $$(".hd-them[open]").forEach((d) => {
    if (!d.contains(ev.target) || ev.target.closest(".hd-them__muc")) d.open = false;
  });
});

/* ---------------- Trình nghe hành động xử lý ----------------
 * Ủy quyền ở document: panel dựng lại mỗi lần làm mới, gắn vào từng nút là
 * gắn lại mãi. `state.convDangMo` là hội thoại đang vẽ (03-hoi-thoai.js). */
async function _goiHanhDong(duong, than, xong) {
  const c = state.convDangMo;
  if (!c) return;
  state.moHanhDong = null;
  try {
    const r = await api(`/inbox/conversations/${c.id}/${duong}`, {
      method: "POST",
      body: than ? JSON.stringify({ expected_version: c.version || 1, ...than }) : undefined,
    });
    xong(r);
    refresh();
  } catch (e) { toast(e.message, true); }
}

document.addEventListener("click", (ev) => {
  if (ev.target.closest("#btn-take")) {
    _goiHanhDong("takeover", { reason: "Nhân viên nhận xử lý" },
      () => toast("Bạn đang giữ hội thoại này. AI đã dừng gửi."));
  } else if (ev.target.closest("#btn-release")) {
    _goiHanhDong("release", { reason: "Nhân viên kết thúc tiếp quản" }, (r) => {
      /* `ghi_chu` = đã bật agent trong CSDL nhưng CHƯA giành lại quyền từ
       * Meta (Messenger) — agent bật mà câm. Phải hiện thành lỗi, không
       * được nuốt sau một toast xanh. */
      if (r && r.ghi_chu) toast(r.ghi_chu, true);
      else toast("Đã chuyển về chế độ gợi ý.");
    });
  } else if (ev.target.closest("#btn-chedo")) {
    /* Trả hội thoại VỀ cho agent, hoặc bắt duyệt trước khi gửi. Không có
     * nút này thì hội thoại rơi xuống "Chờ duyệt" là kẹt ở đó vĩnh viễn —
     * chỉ có nút đi xuống, không có nút đi lên. */
    const sang = ev.target.closest("#btn-chedo").dataset.chedo;
    _goiHanhDong("che-do", {
      che_do: sang,
      reason: sang === "auto" ? "Người trực trả hội thoại về cho agent" : "Người trực bật duyệt trước khi gửi",
    }, () => toast(sang === "auto" ? "Agent sẽ tự trả lời hội thoại này." : "Từ giờ AI soạn xong sẽ chờ bạn duyệt."));
  } else if (ev.target.closest("#btn-mo-lai")) {
    _goiHanhDong("mo-lai", null, (r) =>
      toast(r && r.da_mo ? "Đã mở lại hội thoại." : "Hội thoại đã mở từ trước."));
  }
});

/* ---------------- Ghi chú nội bộ trong ô soạn tin (mục 6.6) ----------------
 *
 * Ô soạn có HAI kiểu: "Trả lời khách" và "Ghi chú nội bộ". Kiểu ghi chú
 * KHÔNG BAO GIỜ đi qua đường gửi tin (`/send`, `/send-file`): chỉ gọi
 * `/inbox/conversations/{id}/ghi-chu`, và route ấy không đụng outbox.
 *
 * Kiểu soạn và BẢN NHÁP nhớ theo từng hội thoại, và bản nháp tách riêng
 * cho từng kiểu. Chung một bản nháp là lỗi nguy hiểm nhất ở đây: gõ ghi chú
 * "khách này hay bom hàng", lỡ bấm sang "Trả lời khách", Enter — câu ấy đi
 * thẳng tới khách. */
function dangGhiChu(id) {
  return !!(state.soanGhiChu && state.soanGhiChu[id]);
}

function khoaNhap(id) {
  return dangGhiChu(id) ? `${id}:ghichu` : String(id);
}

async function guiTuKhungSoan(id, text, laGhiChu) {
  if (laGhiChu) {
    await api(`/inbox/conversations/${id}/ghi-chu`, {
      method: "POST", body: JSON.stringify({ noi_dung: text }),
    });
    return { ok: true, ghi_chu: true };
  }
  return api(`/conversations/${id}/send`, {
    method: "POST", body: JSON.stringify({ text }),
  });
}

document.addEventListener("click", (ev) => {
  const nut = ev.target.closest("[data-soan]");
  if (!nut || !state.openConv) return;
  const id = state.openConv;
  state.soanGhiChu = state.soanGhiChu || {};
  state.soanGhiChu[id] = nut.dataset.soan === "ghichu";
  state.soanVuaDoi = true;
  loadThread(id);
});

/* Trộn ghi chú vào luồng tin theo THỜI GIAN. Ghi chú để riêng một hộp gấp
 * ở đầu hội thoại thì người đọc phải tự ghép "ghi chú này viết lúc khách
 * đang nói gì" — mà đó chính là ngữ cảnh làm ghi chú có nghĩa. */
function xenGhiChu(tin, ghiChu, deXuat) {
  const ds = (tin || []).map((m, i) => ({ loai: "tin", luc: m.created_at, thu_tu: i, m }));
  (ghiChu || []).forEach((g, i) => ds.push({ loai: "ghichu", luc: g.tao_luc, thu_tu: 1e6 + i, g }));
  (deXuat || []).forEach((d, i) => ds.push({ loai: "dexuat", luc: d.tao_luc, thu_tu: 2e6 + i, d }));
  const ms = (x) => { const t = Date.parse(x.luc || ""); return Number.isNaN(t) ? 0 : t; };
  return ds.sort((a, b) => ms(a) - ms(b) || a.thu_tu - b.thu_tu);
}

function veGhiChuTrongLuong(g) {
  return `<div class="msg msg--ghichu" role="note" aria-label="Ghi chú nội bộ">
    <div class="msg__bubble"><span class="msg__ghichu-nhan">Ghi chú nội bộ · khách không thấy</span>${esc(g.noi_dung)}</div>
    <div class="msg__meta"><span>${esc([gioTin(g.tao_luc), g.nguoi || "Nhân viên"].filter(Boolean).join(" · "))}</span></div>
  </div>`;
}

/* Hai thẻ chọn kiểu soạn. Người không có `hoi_thoai.ghi_chu` chỉ có một
 * kiểu — không vẽ thẻ nào, để khỏi mời một 403. */
function veCheDoSoan(id, ghiChuDuoc) {
  if (!ghiChuDuoc) return "";
  const ghi = dangGhiChu(id);
  const the = (ma, nhan, bat) => `<button type="button" role="tab" class="soan__tab${bat ? " is-on" : ""}"
    aria-selected="${bat ? "true" : "false"}" data-soan="${ma}">${nhan}</button>`;
  return `<div class="soan__che-do" role="tablist" aria-label="Kiểu soạn">
    ${the("tra_loi", "Trả lời khách", !ghi)}${the("ghichu", "Ghi chú nội bộ", ghi)}
  </div>`;
}
