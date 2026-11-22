/* ---------------- Ủy quyền thực thi của AI (mục 17) ----------------
 *
 * Hai phần:
 *   1. Tab Cấu hình AI Agent → Chính sách & Ủy quyền (`GAN_TAB["ai-chinh-sach"]`):
 *      mức của từng hành động — Không sử dụng / Có phê duyệt / Tự động.
 *   2. THẺ ĐỀ XUẤT trong luồng hội thoại: AI đã chuẩn bị một hành động cụ
 *      thể và chờ người có thẩm quyền. Thẻ là NỘI BỘ — nằm giữa khung, viền
 *      riêng, không bao giờ trông như tin đã gửi khách. Không có ô sửa: ở
 *      giai đoạn này người duyệt chỉ Duyệt hoặc Từ chối (phiếu việc 17.10).
 *
 * Mọi chốt thật nằm ở máy chủ (agent/core/uy_quyen.py, agent/api/uy_quyen_ai.py).
 * Nút ẩn/hiện ở đây chỉ để không mời một 403 — máy chủ vẫn kiểm lại.
 */

const dxTien = (n) => Number(n || 0).toLocaleString("vi-VN") + "đ";

const DX_TAG = {
  cho_duyet: "assist", da_duyet: "assist", da_thuc_hien: "auto",
  loi: "halt", tu_choi: "plain", het_han: "plain",
};

function dxCoQuyen(q) {
  return !!(state.toiQuyen && state.toiQuyen.has(q));
}

/* ---------- 1. Tab chính sách ---------- */

function dxDongChinhSach(h, sua) {
  let o;
  if (!h.ho_tro) {
    o = '<span class="tag tag--plain">Chưa hỗ trợ — chuyển nhân viên</span>';
  } else if (!h.cau_hinh_duoc) {
    o = `<span class="tag tag--auto">${esc(h.nhan_muc)} · luôn bật</span>`;
  } else {
    o = `<select data-dx-muc="${esc(h.ma)}"${sua ? "" : " disabled"} aria-label="Mức cho ${esc(h.ten)}">${
      ["khong_su_dung", "co_phe_duyet", "tu_dong"].map((m) => `<option value="${m}"${m === h.muc ? " selected" : ""}>${
        esc({ khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[m])}</option>`).join("")}
      </select>`;
  }
  const nguong = h.co_nguong
    ? `<label class="field dx-nguong"><span>Ngưỡng phải duyệt (ở mức Tự động) <em class="hint">mặc định ${
        esc(dxTien(h.nguong_mac_dinh))}</em></span>
        <input type="number" min="0" step="1000" data-dx-nguong="${esc(h.ma)}" value="${esc(h.nguong_vnd ?? "")}"${
          sua ? "" : " disabled"}></label>`
    : "";
  return `<div class="row dx-cs">
    <div class="row__body">
      <b>${esc(h.ten)}</b>${h.da_doi ? ' <span class="tag tag--plain">đã đổi</span>' : ""}
      <p class="row__sub">${esc(h.mo_ta)}</p>
      ${h.ghi_chu ? `<p class="row__sub hint">${esc(h.ghi_chu)}</p>` : ""}
      ${h.ho_tro && h.cau_hinh_duoc ? `<p class="row__sub hint">Mặc định: ${esc(
        { khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[h.mac_dinh] || h.mac_dinh)}${
        h.quyen_thi_hanh ? ` · người duyệt cần thêm quyền ${esc(h.quyen_thi_hanh)}` : ""}${
        h.sua_boi ? ` · sửa bởi ${esc(h.sua_boi)}` : ""}</p>` : ""}
      ${nguong}
    </div>
    <div class="row__aside">${o}</div>
  </div>`;
}

async function ganChinhSachUyQuyen(goc) {
  if (!goc) return;
  const sua = dxCoQuyen("agent.dieu_khien");
  const ve = (d) => {
    goc.innerHTML = `<section class="panel">
      <h2 class="panel__head">Chính sách &amp; Ủy quyền
        <span class="panel__note">AI được tự làm gì, việc gì phải có người duyệt</span></h2>
      <p class="row__sub">Chế độ AI hiện tại: <b>${d.che_do_chung === "auto" ? "Tự động" : "Gợi ý"}</b>.
        ${d.che_do_chung === "auto"
          ? "Mức của từng hành động dưới đây đang có hiệu lực."
          : "Ở chế độ Gợi ý, MỌI hành động thay đổi dữ liệu đều thành đề xuất chờ duyệt, bất kể mức bên dưới."}
        Hội thoại bật «Duyệt trước khi gửi» cũng được xử lý như Gợi ý.</p>
      <p class="row__sub hint">Tra cứu (sản phẩm, giá, tồn kho, đơn, vận chuyển, tài liệu) luôn được phép và không cần dòng nào ở đây.
        Hành động mới chưa có trong danh sách: mặc định <b>${esc(d.hanh_dong_la)}</b> (chuyển nhân viên).</p>
      <div class="rows">${d.hanh_dong.map((h) => dxDongChinhSach(h, sua)).join("")}</div>
      <label class="field dx-han"><span>Đề xuất hết hạn sau (giờ) <em class="hint">quá hạn thì không thi hành được nữa</em></span>
        <input type="number" min="1" max="${esc(d.han_toi_da_gio)}" data-dx-han value="${esc(d.han_gio)}"${sua ? "" : " disabled"}></label>
      <div class="rowbtns">
        ${sua ? '<button type="button" class="btn btn--sm btn--go" data-dx-luu>Lưu chính sách</button>'
              : '<span class="row__sub">Cần quyền agent.dieu_khien để sửa.</span>'}
        <span class="row__sub" data-dx-kq aria-live="polite"></span>
      </div>
    </section>`;
  };
  /* Lần đầu tab hiện, khe vừa gắn mô-đun vừa phát `tab:hien` — gộp hai lời
   * gọi đang bay làm một, không tải hai lần. */
  let dangNap = null;
  const nap = () => dangNap || (dangNap = (async () => {
    try { ve(await api("/ai-uy-quyen")); }
    catch (e) { goc.innerHTML = `<p class="empty">Không tải được chính sách: ${esc(e.message)}</p>`; }
  })().finally(() => { dangNap = null; }));
  goc.addEventListener("click", async (e) => {
    if (!e.target.closest("[data-dx-luu]")) return;
    const hanh_dong = {};
    $$("[data-dx-muc]", goc).forEach((s) => { hanh_dong[s.dataset.dxMuc] = { muc: s.value }; });
    $$("[data-dx-nguong]", goc).forEach((o) => {
      const ma = o.dataset.dxNguong;
      if (hanh_dong[ma] && o.value !== "") hanh_dong[ma].nguong_vnd = Number(o.value);
    });
    const han = $("[data-dx-han]", goc);
    const kq = $("[data-dx-kq]", goc);
    try {
      ve(await api("/ai-uy-quyen", { method: "PUT",
        body: JSON.stringify({ hanh_dong, han_gio: han && han.value ? Number(han.value) : null }) }));
      toast("Đã lưu chính sách ủy quyền");
    } catch (err) {
      if (kq) kq.textContent = err.message;
      toast(err.message, true);
    }
  });
  goc.addEventListener("tab:hien", nap);
  await nap();
}

window.GAN_TAB["ai-chinh-sach"] = (el) => ganChinhSachUyQuyen(el);

/* ---------- 2. Thẻ đề xuất trong hội thoại ---------- */

function dxDongHang(items) {
  return (items || []).map((it) => `<li>${esc(it.so_luong)} × ${esc(it.ten)}${
    it.don_gia != null ? ` — ${esc(dxTien(it.don_gia))}` : ""}</li>`).join("");
}

function dxTrangThaiDon(x) {
  if (!x) return "<p class=\"hint\">—</p>";
  const phan = [];
  if (x.trang_thai) phan.push(`<div><b>Trạng thái:</b> ${esc(x.trang_thai)}</div>`);
  if (x.items && x.items.length) phan.push(`<ul class="ctt__ds">${dxDongHang(x.items)}</ul>`);
  if (x.tong_tien != null) phan.push(`<div><b>Tổng:</b> ${esc(dxTien(x.tong_tien))}</div>`);
  if (x.nguoi_nhan) phan.push(`<div><b>Giao tới:</b> ${esc([x.nguoi_nhan, x.sdt, x.dia_chi].filter(Boolean).join(" · "))}</div>`);
  if (x.tra_kho && x.tra_kho.length) phan.push(`<div><b>Trả về kho:</b> ${esc(x.tra_kho.join(", "))}</div>`);
  if (x.ghi_chu) phan.push(`<div><b>Ghi chú:</b> ${esc(x.ghi_chu)}</div>`);
  return phan.join("") || "<p class=\"hint\">—</p>";
}

function dxKetQua(d) {
  if (d.trang_thai === "da_thuc_hien" && d.ket_qua) {
    const k = d.ket_qua;
    const dong = [
      k.ma_don ? `Mã đơn ${esc(k.ma_don)}` : "",
      k.qua === "man_don_hang" ? `Đã ${esc(k.viec || "xử lý")} ở màn Đơn hàng bởi ${esc(k.boi || "?")}` : "",
      k.can_huy_tay ? `⚠ ${esc(k.can_huy_tay)}` : "",
      k.can_hoan_tien ? `⚠ ${esc(k.can_hoan_tien)}` : "",
    ].filter(Boolean);
    return dong.length ? `<p class="row__sub">${dong.join("<br>")}</p>` : "";
  }
  if (d.trang_thai === "loi") return `<p class="row__sub"><b>Không thực hiện:</b> ${esc(d.loi || "")}</p>`;
  if (d.trang_thai === "tu_choi" && d.ly_do_tu_choi) return `<p class="row__sub"><b>Lý do từ chối:</b> ${esc(d.ly_do_tu_choi)}</p>`;
  return "";
}

/* Thẻ NỘI BỘ: phân biệt rõ với tin khách và tin đã gửi (17.10). */
function veTheDeXuat(d) {
  const dx = d.de_xuat || {};
  const cc = d.can_cu || {};
  const ai = [
    d.duyet_boi ? `duyệt bởi ${d.duyet_boi}` : "",
    d.tu_choi_boi ? `từ chối bởi ${d.tu_choi_boi}` : "",
  ].filter(Boolean).join(" · ");
  const ds = (mang) => (mang || []).map((x) => `<li>${esc(typeof x === "string" ? x : `${x.ten}: ${x.chi_tiet}`)}</li>`).join("");
  const nut = d.trang_thai === "cho_duyet"
    ? (d.duoc_duyet
      ? `<button type="button" class="btn btn--sm btn--go" data-dx-duyet="${esc(d.id)}">Phê duyệt</button>
         <button type="button" class="btn btn--sm btn--halt" data-dx-tu-choi="${esc(d.id)}">Từ chối</button>`
      : `<span class="row__sub hint">Cần quyền ${esc((d.thieu_quyen || []).join(" + "))} để duyệt.</span>`)
    : "";
  return `<div class="msg msg--dexuat" role="note" aria-label="Đề xuất hành động của AI — nội bộ">
    <div class="dx-the">
      <div class="dx-the__dau">
        <span class="dx-the__nhan">Đề xuất của AI · nội bộ, khách không thấy</span>
        <span class="tag tag--${DX_TAG[d.trang_thai] || "plain"}">${esc(d.nhan_trang_thai)}</span>
      </div>
      <b class="dx-the__tieu">${esc(dx.tieu_de || d.ten_hanh_dong)}</b>
      <p class="row__sub">${esc(dx.ly_do || "")}</p>
      <p class="row__sub"><b>Vì sao cần duyệt:</b> ${esc(d.ly_do_can_duyet)}</p>
      <div class="dx-the__hai">
        <div><h4 class="ctt__dau">Trước</h4>${dxTrangThaiDon(dx.truoc)}</div>
        <div><h4 class="ctt__dau">Sau khi thực hiện</h4>${dxTrangThaiDon(dx.sau)}</div>
      </div>
      <h4 class="ctt__dau">Căn cứ hệ thống đã kiểm</h4>
      ${(cc.nguon || []).length ? `<ul class="ctt__ds">${ds(cc.nguon)}</ul>` : '<p class="hint">Không có.</p>'}
      ${(cc.rui_ro || []).length ? `<h4 class="ctt__dau">Rủi ro</h4><ul class="ctt__ds">${ds(cc.rui_ro)}</ul>` : ""}
      ${(cc.thieu || []).length ? `<h4 class="ctt__dau">Điều kiện còn thiếu</h4><ul class="ctt__ds">${ds(cc.thieu)}</ul>` : ""}
      ${dxKetQua(d)}
      <div class="msg__meta">
        <span>${esc([gioTin(d.tao_luc), "AI Agent", d.trang_thai === "cho_duyet" && d.het_han_luc
          ? "hết hạn " + gioTin(d.het_han_luc) : "", ai].filter(Boolean).join(" · "))}</span>
        ${d.message_id ? `<button type="button" class="msg__goc-nut" data-dx-can-cu="${esc(d.message_id)}">Xem căn cứ lượt trả lời</button>` : ""}
        ${nut}
      </div>
    </div>
  </div>`;
}

/* Từ chối BẢN NHÁP AI: bản nháp thành "Đã huỷ", không gửi được nữa. Không
 * xoá — lịch sử phải còn thấy AI đã soạn gì và ai đã bác. */
document.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-tu-choi-nhap]");
  if (!nut) return;
  const v = await hoiHop({
    tieu_de: "Từ chối bản nháp AI", nut: "Từ chối", nguy_hiem: true,
    phu: "Bản nháp sẽ không gửi cho khách. Bạn tự trả lời khách ở ô soạn bên dưới.",
    truong: [{ name: "ly_do", label: "Lý do (không bắt buộc)", type: "textarea", maxlength: 500 }],
  });
  if (v === null) return;
  try {
    await api(`/messages/${nut.dataset.tuChoiNhap}/tu-choi`, {
      method: "POST", body: JSON.stringify({ ly_do: v.ly_do || "" }) });
    toast("Đã từ chối bản nháp");
  } catch (err) {
    toast(err.message, true);
  }
  if (state.openConv) await loadThread(state.openConv);
});

document.addEventListener("click", async (e) => {
  const duyet = e.target.closest("[data-dx-duyet]");
  const tuChoi = e.target.closest("[data-dx-tu-choi]");
  const canCu = e.target.closest("[data-dx-can-cu]");
  if (canCu) {
    state.chiTietTin = state.chiTietTin || new Set();
    state.chiTietTin.add(String(canCu.dataset.dxCanCu));
    if (state.openConv) await loadThread(state.openConv);
    return;
  }
  if (!duyet && !tuChoi) return;
  const nut = duyet || tuChoi;
  try {
    if (duyet) {
      nut.disabled = true;
      const r = await api(`/ai-de-xuat/${duyet.dataset.dxDuyet}/duyet`, { method: "POST" });
      toast(r.ok ? "Đã duyệt và thực hiện" : `Đã duyệt nhưng không thực hiện được: ${r.loi || ""}`, !r.ok);
    } else {
      const v = await hoiHop({
        tieu_de: "Từ chối đề xuất của AI", nut: "Từ chối", nguy_hiem: true,
        truong: [{ name: "ly_do", label: "Lý do (không bắt buộc)", type: "textarea", maxlength: 500 }],
      });
      if (v === null) return;
      const r = await api(`/ai-de-xuat/${tuChoi.dataset.dxTuChoi}/tu-choi`, {
        method: "POST", body: JSON.stringify({ ly_do: v.ly_do || "" }) });
      toast(r.canh_bao || "Đã từ chối đề xuất", !!r.canh_bao);
    }
  } catch (err) {
    toast(err.message, true);
  } finally {
    nut.disabled = false;
    if (state.openConv) await loadThread(state.openConv);
  }
});
