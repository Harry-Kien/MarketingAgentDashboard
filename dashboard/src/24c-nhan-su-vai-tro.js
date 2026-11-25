/* ======================== TAB "VAI TRÒ & QUYỀN" và "LỊCH SỬ" ========================
 *
 * Phần dùng chung (bảng tick quyền, ngăn kéo, lịch sử) ở 24-nhan-su.js.
 */

function nsvDongVaiTro(v) {
  const sua = nsvCo("nguoi_dung.sua");
  const soQuyen = v.toan_quyen ? "toàn bộ quyền" : `${v.quyen.length} quyền`;
  const nc = nsvQuyenCuaVai({ ...v, dang_dung: true }).filter(nsvLaNhayCam).length;
  /* Nút Xoá chỉ hiện khi máy chủ sẽ cho xoá (`xoa_duoc`): vai trò từng có
     người mang chỉ NGỪNG DÙNG được — nút bấm vào rồi mới báo 409 dạy người
     ta rằng lỗi là chuyện bình thường. "Xem quyền" có ở MỌI vai trò, kể cả
     Quản trị (UX-12-05): trước đây hàng Quản trị không có nút nào, và câu
     "Quản trị làm được gì" không trả lời được trên màn hình. */
  const nut = [
    `<button type="button" class="btn btn--sm btn--ghost" data-nsv-xem-vai="${esc(v.id)}">Xem quyền</button>`,
    sua && !v.toan_quyen ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-sua-vai="${esc(v.id)}">Sửa quyền</button>` : "",
    sua && !v.he_thong ? `<button type="button" class="btn btn--sm btn--ghost" data-nsv-trang-thai="${esc(v.id)}">${v.dang_dung ? "Ngừng dùng" : "Dùng lại"}</button>` : "",
    sua && v.xoa_duoc ? `<button type="button" class="btn btn--sm btn--halt" data-nsv-xoa-vai="${esc(v.id)}">Xoá</button>` : "",
  ].join("");
  return `<div class="row nsv-dong">
    <span class="row__flag row__flag--${!v.dang_dung ? "plain" : v.toan_quyen ? "halt" : "auto"}"></span>
    <div class="row__main">
      <b>${esc(v.ten)}${v.he_thong ? ' <span class="pill">dựng sẵn</span>' : ""}${
        v.dang_dung ? "" : ' <span class="tag tag--plain">ngừng dùng</span>'}</b>
      <span class="row__sub">${esc(v.mo_ta || "—")}</span>
      <div class="nsv-vai"><span class="pill">${soQuyen}</span> <span class="pill">${v.so_nguoi} người</span>${
        nc ? ` <span class="pill pill--halt">${v.toan_quyen ? "mọi" : nc} quyền nhạy cảm</span>` : ""}</div>
    </div>
    <div class="row__side"><span class="row__nut">${nut}</span></div>
  </div>`;
}

function nsvFormVaiTro(v) {
  return `<form class="form nsv-form" data-nsv-form-vai="${v ? esc(v.id) : ""}">
    <label class="field"><span>Tên vai trò</span>
      <input name="ten" required maxlength="80" value="${esc(v ? v.ten : "")}" placeholder="Trưởng nhóm CSKH" autocomplete="off"></label>
    <label class="field"><span>Mô tả <em class="hint">để người sau hiểu vai trò này dành cho ai</em></span>
      <input name="mo_ta" maxlength="500" value="${esc(v ? v.mo_ta : "")}" autocomplete="off"></label>
    ${v && v.so_nguoi ? `<p class="panel__note">Lưu là ${v.so_nguoi} người đang mang vai trò này đổi quyền NGAY ở thao tác kế tiếp của họ.</p>` : ""}
    <div class="quyen">${nsvBangQuyen(v ? v.quyen : [])}</div>
    <div class="row__nut">
      <button type="submit" class="btn btn--sm btn--primary">Lưu vai trò</button>
      <button type="button" class="btn btn--sm btn--ghost" data-nsv-ngan-dong>Huỷ</button>
    </div>
  </form>`;
}

/* Xem quyền CHỈ ĐỌC — mọi vai trò, đặc biệt Quản trị (lấy quyền từ mã, không
   sửa được). Cùng bảng nhóm + tìm như khi sửa, các ô khoá. */
function nsvXemVaiTro(v) {
  return `<div class="nsv-ct">
    <p class="panel__note">${v.toan_quyen
      ? "Vai trò dựng sẵn <b>Quản trị</b> luôn có TOÀN BỘ quyền, lấy thẳng từ mã — quyền mới thêm ở bản sau cũng tự có. Muốn giới hạn ai đó thì tạo vai trò riêng thay vì gán Quản trị."
      : esc(v.mo_ta || "Chưa có mô tả.")}</p>
    <div class="quyen">${nsvBangQuyen(v.quyen, true)}</div>
  </div>`;
}

async function nsvVeVaiTro(el) {
  await nsvTaiDuLieu();
  el.querySelector("[data-nsv-tao-vai]").hidden = !nsvCo("nguoi_dung.sua");   // xem nsvVeNhanVien
  el.querySelector("[data-nsv-vai-ds]").innerHTML = nsv.vaiTro.map(nsvDongVaiTro).join("");
}

/* Ngừng dùng / dùng lại — nói SỐ NGƯỜI và QUYỀN bị ảnh hưởng, không hỏi "có
   chắc không": câu ấy không mang thông tin, người ta bấm OK theo phản xạ. */
async function nsvDoiTrangThaiVai(v) {
  const mang = nsv.nguoi.filter((n) => (n.vai_tro_id || []).includes(v.id))
    .map((n) => n.ho_ten || n.ten_dang_nhap);
  const d = await hoiHop({
    tieu_de: v.dang_dung ? `Ngừng dùng vai trò “${v.ten}”?` : `Dùng lại vai trò “${v.ten}”?`,
    phu: `${v.quyen.length} quyền · ${v.so_nguoi} người đang mang`,
    anh_huong: v.dang_dung
      ? [`${v.so_nguoi} người đang mang nó MẤT các quyền này ngay (trừ quyền vai trò khác của họ cũng cấp).`,
         "Không gán mới được cho tới khi dùng lại.",
         "Vai trò vẫn nằm trong danh sách và lịch sử — dùng lại được."]
      : [`${v.so_nguoi} người đang mang nó có lại các quyền này ngay.`],
    canh_bao: mang.length ? { tieu_de: "Người bị ảnh hưởng:", muc: mang.slice(0, 8).concat(
      mang.length > 8 ? [`… và ${mang.length - 8} người khác`] : []) } : null,
    nut: v.dang_dung ? "Ngừng dùng" : "Dùng lại",
    nguy_hiem: !!v.dang_dung,
  });
  if (!d) return false;
  try {
    await api(`/vai-tro/${v.id}/trang-thai`, { method: "POST", body: JSON.stringify({ dang_dung: !v.dang_dung }) });
    toast(v.dang_dung ? "Đã ngừng dùng vai trò." : "Đã dùng lại vai trò.");
    return true;
  } catch (err) { toast(err.message, true); return false; }
}

/* Xoá hẳn — chỉ vai trò chưa từng được gán (máy chủ chặn phần còn lại). */
async function nsvXoaVaiTro(v) {
  const d = await hoiHop({
    tieu_de: `Xoá hẳn vai trò “${v.ten}”?`,
    anh_huong: ["Vai trò biến mất khỏi danh sách — không hoàn tác được.",
                "Chưa ai từng được gán vai trò này nên không mất dấu vết ai từng có quyền gì."],
    nut: "Xoá vai trò", nguy_hiem: true,
  });
  if (!d) return false;
  try {
    await api(`/vai-tro/${v.id}`, { method: "DELETE" });
    toast("Đã xoá vai trò.");
    return true;
  } catch (err) { toast(err.message, true); return false; }
}

GAN_TAB["ns-vai-tro"] = async (el) => {
  /* Ghi chú tách khỏi dòng tiêu đề (UX-12-05): nằm chung một dòng thì câu
     giải thích dài đẩy nút "Tạo vai trò" xuống hàng dưới, lệch khỏi tiêu đề. */
  el.innerHTML = `<section class="panel nsv-panel">
    <div class="nsv-dau">
      <h2 class="panel__head">Vai trò &amp; Quyền</h2>
      <button type="button" class="btn btn--sm btn--primary" data-nsv-tao-vai hidden>Tạo vai trò</button>
    </div>
    <p class="panel__note nsv-ghi">Quyền của một người = hợp quyền mọi vai trò ĐANG DÙNG họ mang.
      Sửa một vai trò là mọi người mang nó đổi theo ngay. Quyền tô đỏ là quyền nhạy cảm.</p>
    <div class="rows" data-nsv-vai-ds><p class="empty">Đang tải…</p></div>
  </section>${nsvKhungNgan()}`;
  const veLai = () => nsvVeVaiTro(el).catch((err) => toast(err.message, true));
  const theoId = (id) => nsv.vaiTro.find((x) => x.id === id);
  const ngan = el.querySelector("[data-nsv-ngan]");
  el.addEventListener("click", async (e) => {
    const tim = (k) => e.target.closest(`[${k}]`);
    if (tim("data-nsv-tao-vai")) {
      nsvMoNgan(el, "Tạo vai trò mới", nsvFormVaiTro(null));
    } else if (tim("data-nsv-xem-vai")) {
      const v = theoId(tim("data-nsv-xem-vai").dataset.nsvXemVai);
      nsvMoNgan(el, `Quyền của “${v.ten}”`, nsvXemVaiTro(v));
    } else if (tim("data-nsv-sua-vai")) {
      const v = theoId(tim("data-nsv-sua-vai").dataset.nsvSuaVai);
      nsvMoNgan(el, `Sửa vai trò “${v.ten}”`, nsvFormVaiTro(v));
    } else if (tim("data-nsv-trang-thai")) {
      if (await nsvDoiTrangThaiVai(theoId(tim("data-nsv-trang-thai").dataset.nsvTrangThai))) await veLai();
    } else if (tim("data-nsv-xoa-vai")) {
      if (await nsvXoaVaiTro(theoId(tim("data-nsv-xoa-vai").dataset.nsvXoaVai))) await veLai();
    }
  });
  el.addEventListener("submit", async (e) => {
    const f = e.target.closest("[data-nsv-form-vai]");
    if (!f) return;
    e.preventDefault();
    const id = f.dataset.nsvFormVai;
    const than = {
      ten: f.ten.value.trim(), mo_ta: f.mo_ta.value.trim(),
      quyen: $$('input[name="quyen"]:checked', f).map((i) => i.value),
    };
    try {
      await api(id ? `/vai-tro/${id}` : "/vai-tro",
                { method: id ? "PUT" : "POST", body: JSON.stringify(than) });
      toast(id ? "Đã lưu vai trò." : "Đã tạo vai trò.");
      nsvDongNgan(ngan);
      await veLai();
    } catch (err) { toast(err.message, true); }
  });
  el.addEventListener("tab:hien", () => { if (ngan.hidden) veLai(); });
  try { await nsvVeVaiTro(el); } catch (err) {
    el.querySelector("[data-nsv-vai-ds]").innerHTML = `<p class="empty">${esc(err.message)}</p>`;
  }
};

/* Lịch sử ở tab RIÊNG (UX-13-08): trước đây nằm dưới danh sách vai trò, nên
   muốn đọc lịch sử phải cuộn qua mọi vai trò — và tab Vai trò thì dài theo
   số vai trò. Lọc theo loại ở máy chủ, tìm theo tên ở máy khách. */
GAN_TAB["ns-lich-su"] = async (el) => {
  el.innerHTML = `<section class="panel nsv-panel">
    <h2 class="panel__head">Lịch sử nhân sự &amp; phân quyền</h2>
    <p class="panel__note nsv-ghi">Ai đổi gì, lúc nào — trước và sau. 200 thay đổi gần nhất.</p>
    <div class="nsv-loc" role="search">
      <input type="search" class="nsv-tim" data-nsv-tim-ls autocomplete="off"
             placeholder="Tìm người làm, người/vai trò bị đổi…" aria-label="Tìm trong lịch sử">
      <select data-nsv-loc-lich-su aria-label="Lọc theo loại thay đổi">
        <option value="tat_ca">Tất cả</option>
        <option value="vai_tro">Vai trò &amp; quyền</option>
        <option value="nguoi_dung">Tài khoản nhân viên</option>
      </select>
    </div>
    <div class="rows" data-nsv-lich-su><p class="empty">Đang tải…</p></div>
  </section>`;
  const khung = el.querySelector("[data-nsv-lich-su]");
  const loc = () => {
    const k = nsvBoDau(el.querySelector("[data-nsv-tim-ls]").value).trim();
    $$(".row", khung).forEach((r) => { r.hidden = !!k && !nsvBoDau(r.textContent).includes(k); });
  };
  const veLai = async () => {
    if (!nsv.nhom.length) await nsvTaiDuLieu();     // nhãn quyền cho các dòng "+ quyền"
    await nsvVeLichSu(khung, el.querySelector("[data-nsv-loc-lich-su]").value, "", 200);
    loc();
  };
  el.addEventListener("input", (e) => { if (e.target.matches("[data-nsv-tim-ls]")) loc(); });
  el.addEventListener("change", (e) => { if (e.target.matches("[data-nsv-loc-lich-su]")) veLai(); });
  el.addEventListener("tab:hien", () => veLai());
  await veLai();
};

/* ---------------- bắt đổi mật khẩu ở lần đăng nhập tới (UX-13-07) ---------------- */

/* kiemPhien() gọi khi /api/toi trả `phai_doi_mat_khau`. Dùng lại đúng hộp
 * Đổi mật khẩu (#congMk) — chỉ đổi lời và bỏ lối "Quay lại": quay lại là về
 * một dashboard mà máy chủ chặn mọi màn (403), trông như hệ thống hỏng.
 * Lối thoát duy nhất là đăng xuất. Chặn thật nằm ở máy chủ (main.py). */
function nsvBatDoiMatKhau() {
  const f = $("#mkform");
  if (!f) return;
  f.dataset.batBuoc = "1";
  f.querySelector(".cong__ten").textContent = "Đặt mật khẩu mới để tiếp tục";
  f.querySelector(".cong__phu").textContent = "Quản trị vừa đặt mật khẩu tạm cho tài khoản này. "
    + "Mật khẩu tạm là thứ người khác biết — đặt mật khẩu của riêng bạn trước khi dùng dashboard.";
  const nhan = f.mat_khau_cu && f.mat_khau_cu.closest("label").querySelector("span");
  if (nhan) nhan.textContent = "Mật khẩu tạm";
  $("#mkhuy").textContent = "Đăng xuất";
  $("#mkerr").textContent = "";
  $("#cong").classList.add("is-off");
  $("#congMk").classList.remove("is-off");
  f.mat_khau_cu.focus();
}
