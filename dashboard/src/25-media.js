/* ---------------- Media khách gửi: dung lượng, hàng chờ tải, lượt dọn ----------------
 *
 * Gắn qua `GAN_TAB['ht-sao-luu-media']` (khe trong tab Sao lưu & Bảo trì).
 * Thời hạn giữ (`MEDIA_LUU_NGAY`) và trần dung lượng sửa ở ô `data-api-cac-nhom
 * ="media"` ngay dưới khung này — dùng chung bộ Lưu của 13-cau-hinh.js, không
 * dựng một ô sửa thứ hai để lệch nhau.
 *
 * "Dọn ngay" LUÔN xem trước: bấm lần đầu chỉ đếm, hộp xác nhận hiện đúng con
 * số sẽ xoá, rồi mới xoá thật. Một nút xoá dữ liệu khách chỉ cách một cú bấm
 * nhầm là nút người ta sẽ bấm nhầm.
 */

const MEDIA_TRANG_THAI = {
  cho: "Chờ tải", dang_tai: "Đang tải", da_tai: "Đã lưu", loi: "Hỏng sau nhiều lần thử",
  qua_lon: "Quá lớn — không tải", het_han: "Link hãng đã hết hạn", bo_qua: "Không có link / kiểu không cho phép",
  da_don: "Đã dọn theo thời hạn", mat_tep: "Mất tệp trên đĩa",
};
const MEDIA_LOAI = { image: "Ảnh", video: "Video", audio: "Âm thanh", application: "Tài liệu", text: "Văn bản" };

function mediaCo(n) {
  const b = Number(n || 0);
  if (b < 1024) return `${b} B`;
  if (b < 1024 ** 2) return `${(b / 1024).toFixed(0)} KB`;
  if (b < 1024 ** 3) return `${(b / 1024 ** 2).toFixed(1)} MB`;
  return `${(b / 1024 ** 3).toFixed(2)} GB`;
}

function mediaVe(d, coSua) {
  const tt = d.trang_thai || {};
  const cho = (tt.cho || 0) + (tt.dang_tai || 0);
  const hong = (tt.loi || 0) + (tt.het_han || 0) + (tt.qua_lon || 0) + (tt.mat_tep || 0);
  const nhip = d.worker_luc ? `vòng tải đập lần cuối ${esc(clock(d.worker_luc))}${clock(d.worker_luc).match(/^\d/) ? " trước" : ""}`
    : "vòng tải CHƯA chạy lần nào trên máy chủ này";
  const lan = d.lan_don_cuoi;
  const dongLan = lan
    ? `${esc(new Date(lan.bat_dau).toLocaleString("vi-VN"))} (${lan.nguon === "thu_cong" ? `bấm tay bởi ${esc(lan.boi || "?")}` : "tự động"})
       — xoá ${lan.so_tep_xoa} tệp quá hạn, ${lan.so_mo_coi_xoa} tệp mồ côi, giải phóng <b>${mediaCo(lan.byte_giai_phong)}</b>${
       lan.so_dong_mat_tep ? `, <b>${lan.so_dong_mat_tep} dòng mất tệp</b>` : ""}${
       lan.xong_luc ? "" : " — <b>CHƯA chạy xong</b> (hỏng giữa chừng? xem Nhật ký: media.error)"}`
    : "chưa có lượt dọn nào";
  const loai = (d.theo_loai || []).map((r) =>
    `<span class="chip">${esc(MEDIA_LOAI[r.loai] || r.loai)} <span class="chip__so">${r.so_tep}</span> · ${mediaCo(r.so_byte)}</span>`).join(" ");
  const hongDs = (d.hong_gan_day || []).map((r) => `
    <div class="row"><span class="row__flag row__flag--${r.trang_thai === "het_han" || r.trang_thai === "qua_lon" ? "assist" : "halt"}"></span>
      <span class="row__body"><span class="row__title">${esc(MEDIA_TRANG_THAI[r.trang_thai] || r.trang_thai)} · ${esc(r.loai || "tệp")}</span>
        <span class="row__sub">${esc(r.ly_do || "—")} · ${esc(r.nguon || "không có link")} · thử ${esc(r.so_lan_thu)} lần</span></span>
      <span class="row__time">${esc(clock(r.luc))}</span></div>`).join("");
  return `
    <p class="row__sub">${nhip}. Giữ <b>${esc(d.thoi_han_ngay)} ngày</b> kể từ lần gửi gần nhất
      (${d.nguon_thoi_han === "csdl" ? "đặt trên dashboard" : "mặc định .env"}) · trần mỗi tệp <b>${esc(d.toi_da_mb)} MB</b>.</p>
    <div class="readout">
      <div class="readout__cell"><span class="readout__label">Media khách gửi</span>
        <span class="readout__value">${mediaCo(d.so_byte)}</span><span class="readout__unit">${d.so_tep} tệp</span></div>
      <div class="readout__cell"><span class="readout__label">Tệp nhân viên gửi</span>
        <span class="readout__value">${mediaCo(d.uploads.so_byte)}</span><span class="readout__unit">${d.uploads.so_tep} tệp</span></div>
      <div class="readout__cell"><span class="readout__label">Chống trùng tiết kiệm</span>
        <span class="readout__value">${mediaCo(d.trung_lap.byte_tiet_kiem)}</span><span class="readout__unit">${d.trung_lap.so_ban_khong_chep} bản không chép</span></div>
      <div class="readout__cell"><span class="readout__label">Đang chờ tải</span>
        <span class="readout__value">${cho}</span><span class="readout__unit">${hong} không giữ được</span></div>
    </div>
    ${loai ? `<p class="chips">${loai}</p>` : ""}
    <p class="row__sub"><b>Lượt dọn gần nhất:</b> ${dongLan}</p>
    ${d.so_mat_tep ? `<p class="row__sub row__sub--loi"><b>${d.so_mat_tep} tệp có trong CSDL nhưng không còn trên đĩa.</b>
      Vừa chuyển máy? Chép lại thư mục data/media từ bản sao lưu — dòng tự hết đánh dấu ở lượt dọn sau.</p>` : ""}
    ${hongDs ? `<h3 class="row__title">Không giữ được gần đây</h3><div class="rows">${hongDs}</div>` : ""}
    <div class="rowbtns">
      <button type="button" class="btn btn--sm" data-media="lam-moi">Làm mới</button>
      ${coSua ? `<button type="button" class="btn btn--sm btn--halt" data-media="don">Dọn ngay…</button>
        ${tt.loi ? `<button type="button" class="btn btn--sm" data-media="thu-lai">Thử tải lại ${tt.loi} tệp hỏng</button>` : ""}`
      : `<span class="row__sub">Cần quyền cau_hinh.sua để dọn.</span>`}
      <span class="row__sub" data-media-kq aria-live="polite"></span>
    </div>`;
}

async function ganMedia(goc, ctx) {
  const coSua = ctx.quyen.has("cau_hinh.sua");
  const kq = () => goc.querySelector("[data-media-kq]");
  const napLai = async () => {
    try {
      const d = await api("/media/tong-quan");
      goc.innerHTML = mediaVe(d, coSua);
    } catch (e) {
      goc.innerHTML = `<p class="empty">Không tải được số liệu media: ${esc(e.message)}</p>`;
    }
  };
  goc.addEventListener("click", async (e) => {
    const nut = e.target.closest("[data-media]");
    if (!nut) return;
    const viec = nut.dataset.media;
    if (viec === "lam-moi") { await napLai(); return; }
    nut.disabled = true;
    try {
      if (viec === "thu-lai") {
        const r = await api("/media/thu-lai", { method: "POST" });
        toast(`Đã đưa ${r.so_tep} tệp về hàng chờ tải.`);
      } else if (viec === "don") {
        if (kq()) kq().textContent = "Đang đếm…";
        const xem = await api("/media/don", { method: "POST", body: JSON.stringify({ xem_truoc: true }) });
        const tong = xem.so_tep_xoa + xem.so_mo_coi;
        if (!tong) {
          toast("Không có gì để dọn: chưa tệp nào quá hạn, không có tệp mồ côi.");
        } else {
          const ok = await hoiHop({
            tieu_de: `Xoá ${tong} tệp, giải phóng ${mediaCo(xem.byte_giai_phong)}?`,
            phu: `${xem.so_tep_xoa} tệp media không còn đính kèm nào trong ${xem.thoi_han_ngay} ngày gần đây, `
              + `${xem.so_mo_coi} tệp mồ côi (không dòng CSDL nào nhận, tệp tạm bỏ dở, tệp nhân viên của hội thoại đã xoá). `
              + "Không hoàn tác được. Ảnh sản phẩm và tài liệu công ty không bao giờ bị đụng.",
            nut: "Xoá", nguy_hiem: true,
          });
          if (ok) {
            const r = await api("/media/don", { method: "POST", body: JSON.stringify({ xem_truoc: false }) });
            toast(`Đã xoá ${r.so_tep_xoa + r.so_mo_coi} tệp, giải phóng ${mediaCo(r.byte_giai_phong)}`
              + (r.loi.length ? ` — ${r.loi.length} tệp KHÔNG xoá được, xem Nhật ký.` : "."), r.loi.length > 0);
          }
        }
      }
      await napLai();
    } catch (err) {
      toast(err.message, true);
      if (kq()) kq().textContent = "";
    } finally {
      nut.disabled = false;
    }
  });
  goc.addEventListener("tab:hien", napLai);
  await napLai();
}

window.GAN_TAB = window.GAN_TAB || {};
GAN_TAB["ht-sao-luu-media"] = (o, ctx) => { ganMedia(o, ctx); };
