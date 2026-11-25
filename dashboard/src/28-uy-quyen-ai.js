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
  dang_thuc_thi: "assist", cho_xu_ly_thu_cong: "assist",
  loi: "halt", tu_choi: "plain", het_han: "plain",
};

function dxCoQuyen(q) {
  return !!(state.toiQuyen && state.toiQuyen.has(q));
}

/* ---------- 1. Tab chính sách ---------- */

function dxDongChinhSach(h, sua) {
  let o;
  if (!h.ho_tro) {
    o = h.ho_tro_de_xuat
      ? `<span class="tag tag--assist">Chỉ đề xuất — xử lý thủ công</span>`
      : `<span class="tag tag--plain">Chưa hỗ trợ tự động — chuyển nhân viên</span>`;
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
  const co = !h.ho_tro ? "plain" : h.muc === "tu_dong" ? "auto" : h.muc === "co_phe_duyet" ? "assist" : "halt";
  const chiTietPhan = [
    h.mo_ta ? `<p class="row__sub">${esc(h.mo_ta)}</p>` : "",
    h.ghi_chu ? `<p class="row__sub hint">${esc(h.ghi_chu)}</p>` : "",
    h.ho_tro && h.cau_hinh_duoc ? `<p class="row__sub hint">Mặc định: ${esc(
      { khong_su_dung: "Không sử dụng", co_phe_duyet: "Có phê duyệt", tu_dong: "Tự động" }[h.mac_dinh] || h.mac_dinh)}${
      h.quyen_thi_hanh ? ` · người duyệt cần thêm quyền ${esc(h.quyen_thi_hanh)}` : ""}${
      h.sua_boi ? ` · sửa bởi ${esc(h.sua_boi)}` : ""}</p>` : "",
    nguong,
  ].filter(Boolean).join("");
  const coChiTiet = Boolean(chiTietPhan);
  return `<div class="row dx-cs" data-dx-dong="${esc(h.ma)}">
    <span class="row__flag row__flag--${co}"></span>
    <div class="row__body">
      <b>${esc(h.ten)}</b>${h.da_doi ? ' <span class="tag tag--plain">đã đổi</span>' : ""}
      ${h.mo_ta ? `<p class="row__sub dx-cs__mo-ta-ngan">${esc(h.mo_ta)}</p>` : ""}
      ${coChiTiet ? `<div class="dx-cs__chi-tiet" data-dx-chi-tiet="${esc(h.ma)}" hidden>${chiTietPhan}</div>` : ""}
    </div>
    <div class="row__aside">${o}${coChiTiet ? `<button type="button" class="btn btn--sm btn--ghost" data-dx-mo-rong="${esc(h.ma)}" aria-expanded="false">Chi tiết ▾</button>` : ""}</div>
  </div>`;
}

function dxNhomChinhSach(tieuDe, moTa, ds, sua) {
  if (!ds.length) return "";
  return `<details class="dx-nhom" open>
    <summary class="dx-nhom__dau">
      <h3 class="dx-nhom__tieu-de"><span>${esc(tieuDe)} (${ds.length})</span><span class="hint">Thu gọn / Mở</span></h3>
      <p class="dx-nhom__mo-ta">${esc(moTa)}</p>
    </summary>
    <div class="rows">${ds.map((h) => dxDongChinhSach(h, sua)).join("")}</div>
  </details>`;
}

async function ganChinhSachUyQuyen(goc) {
  if (!goc) return;
  const sua = dxCoQuyen("agent.dieu_khien");
  const ve = (d) => {
    const ds = d.hanh_dong || [];
    const coTheCauHinh = ds.filter((h) => h.ho_tro && h.cau_hinh_duoc);
    const luonBat = ds.filter((h) => h.ho_tro && !h.cau_hinh_duoc);
    const chuaHoTroTuDong = ds.filter((h) => !h.ho_tro);
    goc.innerHTML = `<section class="panel dx-chinh-sach">
      <h2 class="panel__head">Chính sách &amp; Ủy quyền
        <span class="panel__note">AI được tự làm gì, việc gì phải có người duyệt</span></h2>
      <p class="row__sub">Chế độ AI hiện tại: <b>${d.che_do_chung === "auto" ? "Tự động" : "Gợi ý"}</b>.
        ${d.che_do_chung === "auto"
          ? "Mức của từng hành động dưới đây đang có hiệu lực."
          : "Ở chế độ Gợi ý, MỌI hành động thay đổi dữ liệu đều thành đề xuất chờ duyệt, bất kể mức bên dưới."}
        Hội thoại bật «Duyệt trước khi gửi» cũng được xử lý như Gợi ý.</p>
      <p class="row__sub hint">Tra cứu (sản phẩm, giá, tồn kho, đơn, vận chuyển, tài liệu) luôn được phép và không cần dòng nào ở đây.
        Hành động mới chưa có trong danh sách: mặc định <b>${esc(d.hanh_dong_la)}</b> (chuyển nhân viên).</p>
      <div class="dx-canh-bao" role="note">
        <b>Lưu ý tích hợp ERPNext:</b> Tự động sửa Sales Order trên ERPNext hiện <b>chưa được hỗ trợ</b> (Integration Pending). Các đề xuất sửa đơn chỉ dừng ở mức chờ duyệt và nhân viên xác nhận xử lý thủ công.
      </div>
      ${dxNhomChinhSach(
        "Có thể cấu hình tự động hoặc phê duyệt",
        "Backend đã hỗ trợ thực thi. Bạn có thể chọn Không sử dụng, Có phê duyệt hoặc Tự động (theo ngưỡng nếu có).",
        coTheCauHinh,
        sua
      )}
      ${dxNhomChinhSach(
        "Hành động cố định theo hệ thống",
        "Luôn bật theo quy tắc an toàn của hệ thống, không thể tắt.",
        luonBat,
        sua
      )}
      ${dxNhomChinhSach(
        "Chỉ đề xuất / Chưa hỗ trợ tự động",
        "Backend chưa hỗ trợ thực thi tự động — không thể bật chế độ Tự động. AI chỉ tạo đề xuất chờ xử lý thủ công hoặc chuyển nhân viên.",
        chuaHoTroTuDong,
        sua
      )}
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
    const nutMo = e.target.closest("[data-dx-mo-rong]");
    if (nutMo) {
      const ma = nutMo.dataset.dxMoRong;
      const dong = nutMo.closest("[data-dx-dong]");
      const ct = dong && dong.querySelector(`[data-dx-chi-tiet="${CSS.escape(ma)}"]`);
      if (ct) {
        const dangAn = ct.hidden;
        ct.hidden = !dangAn;
        nutMo.setAttribute("aria-expanded", dangAn ? "true" : "false");
        nutMo.textContent = dangAn ? "Thu gọn ▴" : "Chi tiết ▾";
      }
      return;
    }
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
  if (d.trang_thai === "cho_xu_ly_thu_cong") {
    return `<p class="row__sub"><b>Chờ xử lý thủ công — chưa sửa đơn:</b> ${esc(d.loi || "")}</p>`;
  }
  if (d.trang_thai === "da_thuc_hien" && d.ket_qua) {
    const k = d.ket_qua;
    if (k.qua === "xu_ly_thu_cong") {
      const dongTC = [
        `<b>Đã xử lý thủ công bởi ${esc(k.boi || "?")}</b> (không tự động sửa ERPNext)`,
        k.ma_don ? `Mã đơn ${esc(k.ma_don)}` : "",
        k.ghi_chu ? `Ghi chú: ${esc(k.ghi_chu)}` : "",
        k.ma_tham_chieu ? `Mã tham chiếu: ${esc(k.ma_tham_chieu)}` : "",
      ].filter(Boolean);
      return `<p class="row__sub">${dongTC.join("<br>")}</p>`;
    }
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
         <button type="button" class="btn btn--sm btn--halt" data-dx-tu-choi="${esc(d.id)}" data-dx-loai="${esc(d.hanh_dong)}">Từ chối</button>`
      : `<span class="row__sub hint">Cần quyền ${esc((d.thieu_quyen || []).join(" + "))} để duyệt.</span>`)
    : d.trang_thai === "cho_xu_ly_thu_cong"
      ? (d.duoc_hoan_tat_thu_cong
        ? `<button type="button" class="btn btn--sm btn--go" data-dx-thu-cong="${esc(d.id)}">Xác nhận đã xử lý thủ công</button>`
        : `<span class="row__sub hint">Cần quyền ${esc((d.thieu_quyen || []).join(" + "))} để xác nhận xử lý thủ công.</span>`)
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
        <div><h4 class="ctt__dau">${d.hanh_dong === "sua_don" ? "Khách yêu cầu — chưa sửa đơn" : "Sau khi thực hiện"}</h4>${dxTrangThaiDon(dx.sau)}</div>
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
  const thuCong = e.target.closest("[data-dx-thu-cong]");
  const canCu = e.target.closest("[data-dx-can-cu]");
  if (canCu) {
    state.chiTietTin = state.chiTietTin || new Set();
    state.chiTietTin.add(String(canCu.dataset.dxCanCu));
    if (state.openConv) await loadThread(state.openConv);
    return;
  }
  if (!duyet && !tuChoi && !thuCong) return;
  const nut = duyet || tuChoi || thuCong;
  try {
    if (duyet) {
      nut.disabled = true;
      const r = await api(`/ai-de-xuat/${duyet.dataset.dxDuyet}/duyet`, { method: "POST" });
      const choThuCong = r.trang_thai === "cho_xu_ly_thu_cong";
      toast(choThuCong ? `Chờ xử lý thủ công — chưa sửa đơn: ${r.loi || ""}`
        : r.ok ? "Đã duyệt và thực hiện" : `Đã duyệt nhưng không thực hiện được: ${r.loi || ""}`, !r.ok && !choThuCong);
    } else if (thuCong) {
      const v = await hoiHop({
        tieu_de: "Xác nhận đã xử lý thủ công",
        nut: "Xác nhận hoàn tất",
        phu: "Chỉ xác nhận sau khi bạn đã tự kiểm tra và sửa đơn trên sổ đơn / ERPNext. Hệ thống sẽ đối soát lại đơn nhưng KHÔNG tự sửa ERPNext.",
        truong: [
          { name: "ghi_chu", label: "Ghi chú kết quả đã xử lý (bắt buộc)", type: "textarea", required: true, maxlength: 1000 },
          { name: "ma_tham_chieu", label: "Mã tham chiếu / chứng từ ERP (nếu có)", maxlength: 120 },
        ],
      });
      if (v === null) return;
      const ghiChu = (v.ghi_chu || "").trim();
      if (ghiChu.length < 3) { toast("Cần ghi chú kết quả xử lý (tối thiểu 3 ký tự).", true); return; }
      nut.disabled = true;
      await api(`/ai-de-xuat/${thuCong.dataset.dxThuCong}/hoan-tat-thu-cong`, {
        method: "POST",
        body: JSON.stringify({ ghi_chu: ghiChu, ma_tham_chieu: (v.ma_tham_chieu || "").trim() }),
      });
      toast("Đã ghi nhận hoàn tất xử lý thủ công");
    } else {
      const canLyDo = tuChoi.dataset.dxLoai === "sua_don";
      const v = await hoiHop({
        tieu_de: "Từ chối đề xuất của AI", nut: "Từ chối", nguy_hiem: true,
        truong: [{ name: "ly_do", label: canLyDo ? "Lý do từ chối (bắt buộc)" : "Lý do (không bắt buộc)", type: "textarea", maxlength: 500 }],
      });
      if (v === null) return;
      if (canLyDo && !(v.ly_do || "").trim()) { toast("Cần lý do từ chối đề xuất sửa đơn.", true); return; }
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
