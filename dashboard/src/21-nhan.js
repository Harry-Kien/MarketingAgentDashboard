/* ---------------- Nhãn động (mục 3 của bảng việc) ---------------- */
/* MỘT danh mục, HAI loại độc lập (migration 0056, agent/core/nhan.py):
 *   nhãn KHÁCH     mô tả con người, gắn ở Customer 360, đi theo hồ sơ.
 *   nhãn HỘI THOẠI mô tả một vụ việc, gắn bằng nút "+ Nhãn" dưới tên khách
 *                  trên đầu hội thoại; KHÔNG thay trạng thái xử lý.
 * Nhãn đã ngừng không có trong ô chọn, nhưng chỗ đã gắn vẫn hiện (xám) —
 * ngừng dùng là thôi gắn MỚI, không phải xoá khỏi lịch sử.
 *
 * Mọi hộp nhập đi qua `hoiHop` chứ không là ô trong panel: vòng làm mới 6
 * giây dựng lại panel, chữ đang gõ trong đó sẽ mất. */

const LOAI_NHAN = {
  khach: { ten: "Nhãn khách hàng", duong: "/nhan/khach",
           giai_thich: "Mô tả con người, sống lâu: khách sỉ, da nhạy cảm. Gắn ở Customer 360." },
  hoi_thoai: { ten: "Nhãn hội thoại", duong: "/nhan/hoi-thoai",
               giai_thich: "Mô tả một vụ việc: chờ hàng về, khiếu nại ship. Gắn trên hội thoại; không thay trạng thái xử lý." },
};
const MAU_NHAN_MAC_DINH = "#4b5563";

/* Màu đi vào thuộc tính `style` — chỉ nhận đúng dạng #rrggbb. Máy chủ đã
 * kiểm, nhưng một chuỗi lạ lọt vào đây là chèn được CSS tuỳ ý. */
function _mauNhan(m) {
  return /^#[0-9a-f]{6}$/i.test(String(m || "")) ? String(m).toLowerCase() : MAU_NHAN_MAC_DINH;
}

/* Chữ trắng hay chữ đậm — cùng công thức WCAG với `mau_chu()` bên máy chủ.
 * Người quản trị chọn màu tuỳ ý; nhãn vàng nhạt chữ trắng là nhãn không ai
 * đọc được. */
function mauChuNhan(nen) {
  const m = _mauNhan(nen);
  const sang = (hex) => {
    const k = [1, 3, 5].map((i) => {
      const c = parseInt(hex.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * k[0] + 0.7152 * k[1] + 0.0722 * k[2];
  };
  const tp = (a, b) => { const [x, y] = [sang(a), sang(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  return tp(m, "#ffffff") >= tp(m, "#111827") ? "#ffffff" : "#111827";
}

/* Một chip nhãn. `go` = { loai, dich } thì có nút × gỡ. */
function chipNhan(n, go) {
  const mau = _mauNhan(n.mau);
  const ngung = n.dang_dung === false;
  const nut = go
    ? `<button type="button" class="nhan__go" data-nhan-go="${esc(n.id)}" data-nhan-loai="${esc(go.loai)}"
        data-nhan-dich="${esc(go.dich)}" aria-label="Gỡ nhãn ${esc(n.ten)}">×</button>`
    : "";
  return `<span class="nhan nhan--mau${ngung ? " is-ngung" : ""}"
    style="--nhan-nen:${mau};--nhan-chu:${mauChuNhan(mau)}"
    title="${esc(n.ten)}${ngung ? " — đã ngừng sử dụng" : ""}">${esc(n.ten)}${nut}</span>`;
}

/* Chip ở dòng danh sách hội thoại. Phản hồi cũ chỉ có `nhan` (tên). */
function chipNhanDong(c) {
  const ds = Array.isArray(c.nhan_chi_tiet) ? c.nhan_chi_tiet
    : (c.nhan || []).map((t) => ({ id: "", ten: t, mau: MAU_NHAN_MAC_DINH }));
  return ds.length ? `<span class="row__nhan">${ds.map((n) => chipNhan(n)).join("")}</span>` : "";
}

/* Hàng nhãn dưới tên khách trên đầu hội thoại (mục 6.3). Chỉ nhãn HỘI
 * THOẠI: nhãn khách sống ở Customer 360 (mục 6.4), không lặp lại ở đây. */
function nhanHoiThoaiHtml(c) {
  const sua = state.toiQuyen && state.toiQuyen.has("hoi_thoai.tra_loi");
  const ds = c.nhan_chi_tiet || [];
  return `${ds.map((n) => chipNhan(n, sua ? { loai: "hoi_thoai", dich: c.id } : null)).join("")}
    ${sua ? `<button type="button" class="btn btn--sm btn--ghost" data-nhan-them="hoi_thoai"
      data-nhan-dich="${esc(c.id)}">+ Nhãn</button>` : ""}`;
}

/* Khối nhãn khách trong Customer 360 (mục 6.4). */
function nhanKhachHtml(contact) {
  const sua = state.toiQuyen && state.toiQuyen.has("khach.sua");
  const ds = contact.nhan || [];
  return `<div class="profile-actions" id="contact-nhan">
    <div class="profile-tags">${ds.length
      ? ds.map((n) => chipNhan(n, sua ? { loai: "khach", dich: contact.id } : null)).join("")
      : '<span class="empty">Chưa có nhãn.</span>'}</div>
    ${sua ? `<button type="button" class="btn btn--sm" data-nhan-them="khach"
      data-nhan-dich="${esc(contact.id)}">+ Nhãn</button>` : ""}</div>`;
}

/* Hộp chọn một nhãn ĐANG DÙNG của một loại, bỏ những nhãn đã gắn. */
async function chonNhan(loai, daGan = []) {
  const L = LOAI_NHAN[loai];
  let ds;
  try { ds = (await api(L.duong)).nhan || []; } catch (e) { toast(e.message, true); return null; }
  const con = ds.filter((n) => !daGan.includes(n.id));
  if (!con.length) {
    toast(ds.length ? "Đã gắn hết các nhãn đang dùng."
      : `Chưa có ${L.ten.toLowerCase()} nào — tạo ở Cấu hình → Quản lý nhãn.`, true);
    return null;
  }
  const d = await hoiHop({
    tieu_de: `Gắn ${L.ten.toLowerCase()}`,
    phu: L.giai_thich,
    truong: [{ name: "nhan_id", label: "Nhãn", type: "select", required: true,
               options: con.map((n) => ({ value: n.id, label: n.mo_ta ? `${n.ten} — ${n.mo_ta}` : n.ten })) }],
    nut: "Gắn nhãn",
  });
  return d && d.nhan_id ? d.nhan_id : null;
}

function _napLaiSauNhan(loai, dich) {
  if (loai === "hoi_thoai") return loadConversations();
  if (typeof loadContactDetail === "function") return loadContactDetail(dich);
}

document.addEventListener("click", async (ev) => {
  const them = ev.target.closest("[data-nhan-them]");
  const go = ev.target.closest("[data-nhan-go]");
  if (!them && !go) return;
  const el = them || go;
  const loai = el.dataset.nhanThem || el.dataset.nhanLoai;
  const dich = el.dataset.nhanDich;
  const goc = loai === "hoi_thoai" ? `/inbox/conversations/${dich}/nhan` : `/contacts/${dich}/nhan`;
  try {
    if (them) {
      const khung = el.parentElement;
      const daGan = $$("[data-nhan-go]", khung).map((b) => b.dataset.nhanGo);
      const nid = await chonNhan(loai, daGan);
      if (!nid) return;
      await api(goc, { method: "POST", body: JSON.stringify({ nhan_id: nid }) });
      toast("Đã gắn nhãn.");
    } else {
      await api(`${goc}/${encodeURIComponent(el.dataset.nhanGo)}`, { method: "DELETE" });
      toast("Đã gỡ nhãn.");
    }
    await _napLaiSauNhan(loai, dich);
  } catch (e) { toast(e.message, true); }
});

/* Ô lọc danh sách khách theo nhãn khách. Lọc ở MÁY CHỦ (`nhan_id`), không
 * lọc 100 dòng đã tải: khách thứ 101 mang nhãn thì lọc phía giao diện nói
 * "không có ai" — sai mà trông đúng. */
async function napLocNhanKhach() {
  const o = $("#contactLocNhan");
  if (!o) return;
  let ds = [];
  try { ds = (await api(LOAI_NHAN.khach.duong)).nhan || []; } catch { o.hidden = true; return; }
  const html = '<option value="">Mọi nhãn khách</option>'
    + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
  if (o.dataset.html !== html) {
    o.innerHTML = html;
    o.dataset.html = html;
    o.value = state.khachNhan || "";
  }
  o.hidden = !ds.length && !state.khachNhan;
}

$("#contactLocNhan")?.addEventListener("change", (ev) => {
  state.khachNhan = ev.target.value;
  loadContacts();
});

/* ---------------- Quản lý nhãn (Cấu hình chung → tab "Quản lý nhãn") ---------------- */
/* Đăng ký như một mô-đun gắn được: khung tab (01b-dieu-huong.js `ganKhe`)
 * gọi `GAN_TAB['cc-nhan'](khung)` một lần, lần đầu tab hiện ra. */
window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["cc-nhan"] = (el) => moQuanLyNhan(el);

async function moQuanLyNhan(el) {
  if (!el) return;
  if (!el.dataset.nhanGan) {
    el.dataset.nhanGan = "1";
    el.addEventListener("click", (ev) => _bamQuanLyNhan(el, ev));
  }
  await _veQuanLyNhan(el);
}

async function _veQuanLyNhan(el) {
  let d;
  try { d = await api("/nhan"); }
  catch (e) { el.innerHTML = `<p class="empty">${esc(e.message)}</p>`; return; }
  el._nhan = d;
  const sua = state.toiQuyen && state.toiQuyen.has("cau_hinh.sua");
  const khoi = Object.keys(LOAI_NHAN).map((loai) => {
    const L = LOAI_NHAN[loai];
    const ds = d.nhan.filter((n) => n.loai === loai);
    const dong = ds.map((n) => {
      const dung = Number(n.so_khach || 0) + Number(n.so_hoi_thoai || 0) + Number(n.so_quy_tac || 0);
      const noi = loai === "khach" ? `${n.so_khach} khách` : `${n.so_hoi_thoai} hội thoại`;
      return `<div class="row${n.dang_dung ? "" : " is-ngung"}">
        <span class="row__body">
          <span class="row__title">${chipNhan(n)}${n.dang_dung ? "" : ' <em class="hint">đã ngừng sử dụng</em>'}</span>
          ${n.mo_ta ? `<span class="row__sub">${esc(n.mo_ta)}</span>` : ""}
          <span class="row__sub">Đang gắn: ${esc(noi)}${n.so_quy_tac ? ` · ${n.so_quy_tac} quy tắc tự động` : ""}</span>
        </span>
        ${sua ? `<span class="row__side">
          <button type="button" class="btn btn--sm" data-nl-sua="${esc(n.id)}">Sửa</button>
          <button type="button" class="btn btn--sm" data-nl-trang-thai="${esc(n.id)}"
            data-dang-dung="${n.dang_dung ? "1" : ""}">${n.dang_dung ? "Ngừng sử dụng" : "Dùng lại"}</button>
          ${dung ? "" : `<button type="button" class="btn btn--sm btn--halt" data-nl-xoa="${esc(n.id)}"
            title="Chỉ xoá được nhãn chưa từng dùng">Xoá</button>`}
        </span>` : ""}
      </div>`;
    }).join("");
    return `<section class="quan-ly-nhan__loai">
      <h3 class="subhead">${esc(L.ten)}
        ${sua ? `<button type="button" class="btn btn--sm btn--primary" data-nl-them="${loai}">+ Thêm nhãn</button>` : ""}</h3>
      <p class="panel__note">${esc(L.giai_thich)}</p>
      <div class="rows">${dong || '<p class="empty">Chưa có nhãn nào.</p>'}</div>
    </section>`;
  }).join("");
  const html = `<div class="quan-ly-nhan">${khoi}</div>`;
  // Chỉ thay khi đổi: trang Cấu hình làm mới 6 giây một lần, thay lại cả
  // khối là nút đang được rê chuột nhấp nháy.
  if (el.innerHTML !== html) el.innerHTML = html;
}

function _truongNhan(n, bangMau, soDaCo) {
  const mau = n ? n.mau : bangMau[soDaCo % bangMau.length];
  return [
    { name: "ten", label: "Tên nhãn", required: true, maxlength: 80, value: n ? n.ten : "" },
    { name: "mau", label: "Màu", type: "color", value: mau,
      hint: "chữ trên nhãn tự chọn trắng hoặc đậm cho dễ đọc" },
    { name: "mo_ta", label: "Mô tả", type: "textarea", rows: 2, maxlength: 300, value: n ? n.mo_ta : "" },
    { name: "thu_tu", label: "Thứ tự", type: "number", min: 0, max: 10000, value: n ? n.thu_tu : 100,
      hint: "số nhỏ đứng trước trong ô chọn" },
  ];
}

async function _bamQuanLyNhan(el, ev) {
  const b = ev.target.closest("[data-nl-them], [data-nl-sua], [data-nl-trang-thai], [data-nl-xoa]");
  if (!b) return;
  const d = el._nhan || { nhan: [], bang_mau: [MAU_NHAN_MAC_DINH] };
  const tim = (id) => d.nhan.find((n) => n.id === id);
  try {
    if (b.dataset.nlThem) {
      const loai = b.dataset.nlThem;
      const v = await hoiHop({ tieu_de: `Thêm ${LOAI_NHAN[loai].ten.toLowerCase()}`,
        phu: LOAI_NHAN[loai].giai_thich,
        truong: _truongNhan(null, d.bang_mau, d.nhan.filter((n) => n.loai === loai).length), nut: "Tạo nhãn" });
      if (!v) return;
      await api("/nhan", { method: "POST", body: JSON.stringify({
        loai, ten: v.ten, mau: v.mau, mo_ta: v.mo_ta || "", thu_tu: Number(v.thu_tu || 100) }) });
      toast("Đã tạo nhãn.");
    } else if (b.dataset.nlSua) {
      const n = tim(b.dataset.nlSua);
      if (!n) return;
      const v = await hoiHop({ tieu_de: `Sửa nhãn «${n.ten}»`,
        phu: "Đổi tên hay màu là đổi ở MỌI chỗ đang gắn nhãn này. Không đổi được loại nhãn.",
        truong: _truongNhan(n, d.bang_mau, 0), nut: "Lưu" });
      if (!v) return;
      await api(`/nhan/${n.id}`, { method: "PUT", body: JSON.stringify({
        ten: v.ten, mau: v.mau, mo_ta: v.mo_ta || "", thu_tu: Number(v.thu_tu || 100) }) });
      toast("Đã lưu nhãn.");
    } else if (b.dataset.nlTrangThai) {
      const n = tim(b.dataset.nlTrangThai);
      if (!n) return;
      if (b.dataset.dangDung) {
        const ok = await hoiHop({ tieu_de: `Ngừng sử dụng «${n.ten}»?`,
          phu: "Nhãn biến khỏi ô chọn, không gắn mới được. Chỗ đã gắn GIỮ NGUYÊN (hiện xám), lịch sử vẫn đọc được tên. Bật lại lúc nào cũng được.",
          nut: "Ngừng sử dụng", nguy_hiem: true });
        if (!ok) return;
        const r = await api(`/nhan/${n.id}/ngung`, { method: "POST" });
        toast(r.canh_bao || "Đã ngừng sử dụng nhãn.", Boolean(r.canh_bao));
      } else {
        await api(`/nhan/${n.id}/dung-lai`, { method: "POST" });
        toast("Đã dùng lại nhãn.");
      }
    } else if (b.dataset.nlXoa) {
      const n = tim(b.dataset.nlXoa);
      if (!n) return;
      const ok = await hoiHop({ tieu_de: `Xoá nhãn «${n.ten}»?`,
        phu: "Chỉ xoá được nhãn CHƯA từng gắn ở đâu (tạo nhầm). Nhãn đã dùng thì hãy Ngừng sử dụng.",
        nut: "Xoá", nguy_hiem: true });
      if (!ok) return;
      await api(`/nhan/${n.id}`, { method: "DELETE" });
      toast("Đã xoá nhãn.");
    }
    await _veQuanLyNhan(el);
  } catch (e) { toast(e.message, true); }
}

/* ---------------- Nhãn trong quy tắc tự động (mục 7.8) ---------------- */
/* Sáu ô chọn của biểu mẫu quy tắc: ô `data-qt-nhan="hoi_thoai"` chỉ có nhãn
 * hội thoại, ô `"khach"` chỉ có nhãn khách. Tên nhãn theo id giữ trong
 * `state.tenNhan` để câu mô tả quy tắc đọc được ("có nhãn Chờ hàng"). */
async function napONhanQuyTac() {
  state.tenNhan = state.tenNhan || {};
  for (const loai of Object.keys(LOAI_NHAN)) {
    let ds = [];
    try { ds = (await api(LOAI_NHAN[loai].duong)).nhan || []; } catch { ds = []; }
    ds.forEach((n) => { state.tenNhan[n.id] = n.ten; });
    const html = '<option value="">— không xét —</option>'
      + ds.map((n) => `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
    $$(`[data-qt-nhan="${loai}"]`).forEach((o) => {
      // Giữ lựa chọn đang có; chỉ thay khi danh sách đổi (làm mới 6 giây).
      if (o.dataset.html === html) return;
      const giu = o.value;
      o.innerHTML = html;
      o.dataset.html = html;
      if (giu) _datONhan(o, giu);
    });
  }
}

/* Chọn một id trong ô; nhãn đã ngừng (không có trong ô) thì thêm một dòng
 * "(đã ngừng)" — không thì mở sửa quy tắc là mất lặng lẽ điều kiện cũ. */
function _datONhan(o, id) {
  if (!id) { o.value = ""; return; }
  if (![...o.options].some((x) => x.value === id)) {
    const x = document.createElement("option");
    x.value = id;
    x.textContent = `${tenNhanTheoId(id)} (đã ngừng)`;
    o.appendChild(x);
  }
  o.value = id;
}

function tenNhanTheoId(id) {
  return (state.tenNhan && state.tenNhan[id]) || "nhãn đã ngừng";
}
