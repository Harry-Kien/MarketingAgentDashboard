/* ---------------- Sổ yêu cầu của khách (Luật 91/2025, NĐ 356/2025) ---------------- */
/* Hạn và tình trạng do MÁY CHỦ tính (agent/core/yeu_cau_chu_the.py). Ở đây
 * chỉ hiện và gửi thao tác — tính hạn ở hai nơi là hai bản sự thật. */

const YC_TT = {
  qua_han: ["row__flag--halt", "QUÁ HẠN"],
  qua_han_phan_hoi: ["row__flag--halt", "quá hạn phản hồi"],
  sap_het_han: ["row__flag--assist", "sắp hết hạn"],
  dung_han: ["row__flag--auto", "trong hạn"],
  xong: ["row__flag--plain", "đã đóng"],
};

/* Hạn là 00:00 của ngày KẾ TIẾP (máy chủ tính "hết ngày"). Hiện "00:00 31-10"
 * thì người đọc tưởng còn tới sáng 31 — hiện "hết ngày 30-10" mới đúng nghĩa. */
function _han(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const vn = new Date(d.getTime() + 7 * 3600e3);
  if (vn.getUTCHours() === 0 && vn.getUTCMinutes() === 0) {
    const t = new Date(d.getTime() - 1);
    return "hết ngày " + t.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" });
  }
  return _ngayGio(iso);
}

function _ngayGio(iso) {
  return iso ? new Date(iso).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
}

async function loadYeuCauChuThe() {
  const pn = $("#ycPanel");
  if (!pn) return;
  const co = state.toiQuyen && state.toiQuyen.has("khach.pii");
  pn.hidden = !co;
  if (!co) return;
  let r;
  try { r = await api("/pdpd/yeu-cau"); } catch (e) { toast(e.message, true); return; }
  state.yeuCau = r.yeu_cau;
  const d = r.dem;
  $("#ycDem").textContent = d.qua_han || d.qua_han_phan_hoi
    ? `${d.qua_han + d.qua_han_phan_hoi} QUÁ HẠN · ${d.dang_mo} đang mở`
    : `${d.dang_mo} đang mở${d.sap_het_han ? ` · ${d.sap_het_han} sắp hết hạn` : ""}`;
  $("#ycDs").innerHTML = r.yeu_cau.length ? r.yeu_cau.map((y) => {
    const [co_, nhan] = YC_TT[y.tinh_trang] || YC_TT.dung_han;
    return `<div class="row">
      <span class="row__flag ${co_}"></span>
      <span class="row__body"><span class="row__title">${esc(y.ten_loai)} · <em>${esc(nhan)}</em></span>
        <span class="row__sub">xử lý xong <b>${esc(_han(y.han_xu_ly))}</b>${
          y.da_gia_han ? " (đã gia hạn)" : ""}${y.trang_thai === "moi"
          ? ` · phản hồi ${esc(_han(y.han_phan_hoi))}` : " · đã phản hồi"}</span>
        <span class="row__sub">nhận ${esc(_ngayGio(y.nhan_luc))}${y.noi_dung ? " · " + esc(y.noi_dung) : ""}</span></span>
      <span class="row__side">
        ${y.trang_thai === "moi" ? `<button type="button" class="btn btn--sm" data-yc-phan-hoi="${esc(y.id)}">Đã phản hồi</button>` : ""}
        ${y.da_gia_han ? "" : `<button type="button" class="btn btn--sm" data-yc-gia-han="${esc(y.id)}">Gia hạn</button>`}
        <button type="button" class="btn btn--sm btn--primary" data-yc-xong="${esc(y.id)}">Xong</button>
        <button type="button" class="btn btn--sm btn--halt" data-yc-tu-choi="${esc(y.id)}">Từ chối</button>
      </span>
    </div>`;
  }).join("") : '<p class="empty">Không có yêu cầu nào đang mở.</p>';
}

$("#ycDs")?.addEventListener("click", async (ev) => {
  const b = ev.target.closest("[data-yc-phan-hoi], [data-yc-gia-han], [data-yc-xong], [data-yc-tu-choi]");
  if (!b) return;
  const id = b.dataset.ycPhanHoi || b.dataset.ycGiaHan || b.dataset.ycXong || b.dataset.ycTuChoi;
  const y = (state.yeuCau || []).find((x) => x.id === id);
  if (!y) return;
  try {
    if (b.dataset.ycPhanHoi) {
      await api(`/pdpd/yeu-cau/${id}/phan-hoi`, { method: "POST" });
      toast("Đã ghi nhận phản hồi ban đầu.");
    } else if (b.dataset.ycGiaHan) {
      const d = await hoiHop({
        tieu_de: `Gia hạn: ${y.ten_loai}`,
        phu: "Chỉ gia hạn được MỘT lần. Phải báo khách lý do gia hạn — ghi lại lý do ở đây.",
        truong: [{ name: "so_ngay", label: "Thêm bao nhiêu ngày", type: "number", min: 1, max: 20, required: true },
                 { name: "ly_do", label: "Lý do (đã báo khách)", required: true, maxlength: 300 }],
      });
      if (!d) return;
      await api(`/pdpd/yeu-cau/${id}/gia-han`, { method: "POST",
        body: JSON.stringify({ so_ngay: Number(d.so_ngay), ly_do: d.ly_do }) });
      toast("Đã gia hạn.");
    } else {
      const tu_choi = !!b.dataset.ycTuChoi;
      const d = await hoiHop({
        tieu_de: tu_choi ? `Từ chối: ${y.ten_loai}` : `Đóng: ${y.ten_loai}`,
        phu: tu_choi
          ? "Chỉ từ chối khi luật cho phép (Luật 91/2025 Điều 14 khoản 2, Điều 19) — ví dụ đơn hàng phải giữ làm chứng từ kế toán. Ghi căn cứ."
          : "Ghi ngắn đã làm gì. Yêu cầu xoá thực hiện ở khung «Dữ liệu cá nhân» bên dưới sẽ tự đóng ở đây.",
        truong: [{ name: "ket_qua", label: tu_choi ? "Căn cứ từ chối" : "Đã làm gì", required: tu_choi, maxlength: 500 }],
        nut: tu_choi ? "Từ chối" : "Đóng", nguy_hiem: tu_choi,
      });
      if (!d) return;
      await api(`/pdpd/yeu-cau/${id}/dong`, { method: "POST",
        body: JSON.stringify({ ket_qua: d.ket_qua || "", tu_choi }) });
      toast(tu_choi ? "Đã ghi từ chối." : "Đã đóng yêu cầu.");
    }
    loadYeuCauChuThe();
  } catch (e) { toast(e.message, true); }
});

$("#ycForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const v = f.nhan_luc.value;
  const body = {
    loai: f.loai.value, kenh_nhan: f.kenh_nhan.value, sdt: f.sdt.value.trim(),
    noi_dung: f.noi_dung.value.trim(), co_ben_thu_ba: f.co_ben_thu_ba.checked,
    // Giờ Việt Nam TƯỜNG MINH — máy chủ không đoán múi giờ.
    nhan_luc: v ? (v.length === 16 ? v + ":00" : v) + "+07:00" : null,
  };
  try {
    const y = await api("/pdpd/yeu-cau", { method: "POST", body: JSON.stringify(body) });
    toast(y.tinh_trang === "qua_han" || y.tinh_trang === "qua_han_phan_hoi"
      ? "Đã ghi — yêu cầu này ĐÃ QUÁ HẠN theo ngày khách gửi. Xử lý ngay."
      : `Đã ghi. Phải xử lý xong ${_han(y.han_xu_ly)}.`, y.tinh_trang.startsWith("qua_han"));
    f.reset();
    loadYeuCauChuThe();
  } catch (e) { toast(e.message, true); }
});
