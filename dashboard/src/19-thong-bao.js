/* ---------------- chuông thông báo nội bộ ----------------
 *
 * Chuông nằm ở thanh trên, KHÔNG có mục riêng trên thanh điều hướng: thông
 * báo là lối tắt tới hội thoại / việc / đơn, không phải một màn để làm việc.
 * Bấm một dòng = đánh dấu đã đọc + đi tới chỗ liên quan. Đọc KHÔNG làm xong
 * việc gì: duyệt nháp, nhận hội thoại, đóng việc vẫn làm ở màn của chúng.
 *
 * Số chưa đọc làm mới theo vòng 6 giây và theo luồng SSE (10-vong-lam-moi).
 * Hỏng thì KHÔNG toast — vòng 6 giây sẽ bắn toast mãi — mà giữ số cũ và ghi
 * console; danh sách mở ra thì báo lỗi ngay trong khung. */

const chuong = { mo: false, chiChuaDoc: false, ds: [], conNua: false, dangTai: false };

function veSoChuong(n) {
  const o = $("#chuongSo");
  if (!o) return;
  o.textContent = n > 99 ? "99+" : String(n || "");
  o.hidden = !n;
  $("#chuongNut")?.setAttribute("aria-label", n ? `Thông báo — ${n} chưa đọc` : "Thông báo");
}

async function taiSoThongBao() {
  if (!$("#chuongNut")) return;
  try {
    const d = await api("/toi/thong-bao/so-chua-doc");
    veSoChuong(d.chua_doc);
  } catch (e) {
    console.warn("Không tải được số thông báo chưa đọc", e);
  }
}

function dongThongBao(t) {
  const ai = [t.ten_khach, t.kenh].filter(Boolean).map(esc).join(" · ");
  return `<button type="button" class="chuong__dong${t.da_doc ? "" : " is-moi"}" role="listitem"
      data-tb="${esc(t.id)}">
    <span class="chuong__loai chuong__loai--${esc(t.loai)}">${esc(t.nhan_loai)}</span>
    <b class="chuong__tieude">${esc(t.tieu_de)}</b>
    ${ai ? `<span class="chuong__phu">${ai}</span>` : ""}
    ${t.noi_dung ? `<span class="chuong__phu">${esc(t.noi_dung)}</span>` : ""}
    <time class="chuong__gio" datetime="${esc(t.tao_luc)}">${esc(clock(t.tao_luc))}${t.da_doc ? "" : " · chưa đọc"}</time>
  </button>`;
}

function veDanhSachChuong() {
  const ds = $("#chuongDs");
  if (!ds) return;
  ds.innerHTML = chuong.ds.length
    ? chuong.ds.map(dongThongBao).join("")
    : `<p class="empty">${chuong.chiChuaDoc ? "Không có thông báo chưa đọc." : "Chưa có thông báo nào."}</p>`;
  $("#chuongThem").hidden = !chuong.conNua;
}

async function taiDanhSachChuong(them = false) {
  if (chuong.dangTai) return;
  chuong.dangTai = true;
  try {
    const q = new URLSearchParams({ gioi_han: "20", bo_qua: String(them ? chuong.ds.length : 0) });
    if (chuong.chiChuaDoc) q.set("chua_doc", "true");
    const d = await api(`/toi/thong-bao?${q}`);
    chuong.ds = them ? chuong.ds.concat(d.thong_bao) : d.thong_bao;
    chuong.conNua = d.con_nua;
    veSoChuong(d.chua_doc);
    veDanhSachChuong();
  } catch (e) {
    $("#chuongDs").innerHTML = `<p class="empty">Không tải được thông báo: ${esc(e.message)}</p>`;
  } finally {
    chuong.dangTai = false;
  }
}

function moDongChuong(mo) {
  chuong.mo = mo;
  $("#chuongKhung").hidden = !mo;
  $("#chuongNut").setAttribute("aria-expanded", mo ? "true" : "false");
  if (mo) taiDanhSachChuong();
}

/* Đi tới chỗ thông báo trỏ vào. Dùng đúng đường điều hướng sẵn có
 * (`doiMan`, `state.openConv`) — một lối thứ hai là một chỗ nữa để lệch. */
async function diToiLienKet(lk) {
  if (!lk) return;
  if (lk.loai === "hoi_thoai") {
    state.openConv = lk.id;
    state.cuonToiChiTiet = true;
    doiMan("hoithoai");
    return;
  }
  if (lk.loai === "don_hang") { doiMan("donhang"); return; }
  if (lk.loai === "cong_viec") {
    doiMan("cv-danh-sach");
    try { await loadCongViec(); } catch { /* vòng làm mới sẽ thử lại */ }
    const dong = $(`#cv-ds [data-cv="${CSS.escape(lk.id)}"]`);
    if (!dong) { toast("Việc này không nằm trong bộ lọc đang chọn ở màn Công việc."); return; }
    dong.scrollIntoView({ behavior: "smooth", block: "center" });
    dong.classList.add("is-chuong");
    setTimeout(() => dong.classList.remove("is-chuong"), 2400);
  }
}

$("#chuongNut")?.addEventListener("click", (e) => {
  e.stopPropagation();
  moDongChuong(!chuong.mo);
});

$("#chuongChuaDoc")?.addEventListener("change", (e) => {
  chuong.chiChuaDoc = e.target.checked;
  taiDanhSachChuong();
});

$("#chuongThem")?.addEventListener("click", () => taiDanhSachChuong(true));

$("#chuongDocHet")?.addEventListener("click", async () => {
  try {
    await api("/toi/thong-bao/da-doc-het", { method: "POST" });
    await taiDanhSachChuong();
  } catch (e) { toast(e.message, true); }
});

$("#chuongDs")?.addEventListener("click", async (e) => {
  const nut = e.target.closest("[data-tb]");
  if (!nut) return;
  const t = chuong.ds.find((x) => x.id === nut.dataset.tb);
  if (!t) return;
  if (!t.da_doc) {
    try {
      await api(`/toi/thong-bao/${encodeURIComponent(t.id)}/da-doc`, { method: "POST" });
      t.da_doc = true;
      taiSoThongBao();
    } catch (err) { console.warn("Không đánh dấu đã đọc được", err); }
  }
  moDongChuong(false);
  await diToiLienKet(t.lien_ket);
});

/* Bấm ra ngoài hoặc Esc thì đóng — khung nổi che mất nội dung bên dưới. */
document.addEventListener("click", (e) => {
  if (chuong.mo && !e.target.closest("#chuong")) moDongChuong(false);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && chuong.mo) { moDongChuong(false); $("#chuongNut")?.focus(); }
});
