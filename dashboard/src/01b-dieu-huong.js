/* ---------------- điều hướng: thanh bên, nhóm Cài đặt, tab ----------------
 *
 * Cây menu theo phiếu việc của chủ dự án (20.11.2026): sáu màn nghiệp vụ,
 * rồi một nhóm "Cài đặt & Quản trị" bốn màn con, mỗi màn con chia tab.
 * Một tab là `<section class="tabpanel" id="…">` nằm thẳng trong `.view`;
 * id tab cũng là khoá điểm gắn trong `window.GAN_TAB` (00-gan-tab.js).
 */

/* Tên màn CŨ -> tab mới. Thông báo trên máy, nút "Cấu hình" ở màn Hệ thống
 * (`di_toi_man` do máy chủ trả) và mã cũ vẫn gọi doiMan("ca"),
 * doiMan("ketnoi")… — đổi tên mà không giữ bảng này thì mỗi lời gọi cũ là
 * một nút bấm không đi đâu, và không có gì báo lỗi. */
const MAN_CU = {
  ca: "cv-ca-truc",
  ketnoi: "cc-ket-noi",
  cauhinh: "ai-co-ban",
  trithuc: "ai-tri-thuc",
  kynang: "ai-ky-nang",
  phongthu: "ai-phong-thu",
  nhatky: "ht-nhat-ky",
};

/* Quyền để THẤY một tab — đủ MỘT quyền trong danh sách là thấy. Chỉ để
 * không mời người ta vào một màn toàn lỗi 403; chốt thật là `can_quyen`
 * ở máy chủ (agent/core/quyen.py), giấu ở đây không bảo vệ được gì. */
const QUYEN_TAB = {
  "cv-ca-truc": ["hoi_thoai.doc"],
  "cv-danh-sach": ["cong_viec.doc"],
  "cc-nhan": ["cau_hinh.doc", "khach.sua"],
  "cc-tu-dong": ["tra_loi_nhanh.sua", "dinh_tuyen.doc"],
  "cc-ket-noi": ["kenh.doc", "tich_hop.doc", "cau_hinh.doc"],
  "cc-sla": ["dinh_tuyen.doc"],
  "cc-dieu-phoi": ["dinh_tuyen.doc"],
  "ai-co-ban": ["agent.doc", "cau_hinh.doc"],
  "ai-tri-thuc": ["cau_hinh.doc"],
  "ai-ky-nang": ["ky_nang.doc"],
  "ai-chinh-sach": ["cau_hinh.doc"],
  "ai-phong-thu": ["phong_thu.dung"],
  "ns-nhan-vien": ["nguoi_dung.doc"],
  "ns-vai-tro": ["nguoi_dung.doc"],
  "ht-suc-khoe": ["cau_hinh.doc", "nhat_ky.doc"],
  "ht-sao-luu": ["khach.pii", "cau_hinh.doc"],
  "ht-nhat-ky": ["nhat_ky.doc"],
};
const QUYEN_MAN = {
  hoithoai: ["hoi_thoai.doc"],
  khachhang: ["khach.doc"],
  donhang: ["don.doc"],
  kho: ["kho.doc"],        // quyền riêng từ 0058 (trước dùng don.doc)
  nhansu: ["nguoi_dung.doc"],
  sohieu: ["bao_cao.doc"],
};

function duocThay(ds) {
  // Chưa biết quyền (chưa đăng nhập xong) thì không giấu gì: giấu trước rồi
  // hiện sau là thanh bên nhảy múa ngay lần tải đầu.
  if (!state.toiQuyen || !ds) return true;
  return ds.some((q) => state.toiQuyen.has(q));
}

function cacTab(man) {
  const v = $(`.view[data-view="${man}"]`);
  return v ? [...v.children].filter((c) => c.classList.contains("tabpanel")) : [];
}

function manCuaTab(id) {
  const t = document.getElementById(id);
  return t && t.classList.contains("tabpanel") ? t.closest(".view")?.dataset.view || null : null;
}

const tabDuocThay = (id) => duocThay(QUYEN_TAB[id]);

/* Một quyền đơn lẻ — dùng trong vòng làm mới cho tab gộp nhiều nguồn. */
const coQuyen = (q) => duocThay([q]);

function manDuocThay(man) {
  const tabs = cacTab(man);
  if (tabs.length) return tabs.some((t) => tabDuocThay(t.id));
  return duocThay(QUYEN_MAN[man]);
}

/* Tab đang mở của một màn: tab nhớ lần trước nếu còn được thấy, không thì
 * tab ĐẦU TIÊN được thấy. */
function tabCuaMan(man) {
  const tabs = cacTab(man).filter((t) => tabDuocThay(t.id));
  if (!tabs.length) return null;
  const nho = state.tab[man];
  return tabs.some((t) => t.id === nho) ? nho : tabs[0].id;
}

/* Tab đang HIỆN trên màn hình. */
function tabDangHien(id) {
  const man = manCuaTab(id);
  return !!man && state.view === man && tabCuaMan(man) === id;
}

/* Có mô-đun nào gắn vào (và gắn thành công) khe này chưa. */
const GAN_LOI = new Set();
function daGan(id) {
  return typeof window.GAN_TAB[id] === "function" && !GAN_LOI.has(id);
}

/* Tab đang hiện VÀ đang dùng nội dung mặc định — điều kiện để vòng làm mới
 * nạp dữ liệu cho nó. Đã có mô-đun thay thế thì nội dung cũ bị ẩn, nạp vào
 * đó là kéo dữ liệu đổ vào chỗ không ai nhìn (test_vong_lam_moi_khong_keo_thua). */
function dangMo(id) {
  return tabDangHien(id) && !daGan(id);
}

/* Gắn mô-đun vào MỘT khe (tab hoặc `[data-gan]` bên trong tab), một lần. */
function ganKhe(o) {
  const id = o && o.dataset.gan;
  if (!id || o._daGan || GAN_LOI.has(id)) return;
  const fn = window.GAN_TAB[id];
  if (typeof fn !== "function") return;
  o._daGan = true;
  const goc = [...o.children].find((c) => c.classList.contains("tab__goc"));
  const cho = document.createElement("div");
  cho.className = "tab__gan";
  cho.dataset.ganVao = id;
  if (goc) { goc.hidden = true; goc.after(cho); } else { o.append(cho); }
  try {
    fn(cho, { id, api, toast, esc, quyen: state.toiQuyen || new Set() });
  } catch (e) {
    /* Hỏng thì phải có người biết, và màn không được trắng: trả nội dung
       mặc định, báo bằng toast, ghi console cho người sửa. */
    GAN_LOI.add(id);
    cho.remove();
    if (goc) goc.hidden = false;
    console.error(`GAN_TAB["${id}"] hỏng:`, e);
    toast(`Mô-đun "${id}" lỗi khi mở — đang hiện nội dung mặc định.`, true);
  }
}

/* Gọi ở MỖI nhịp làm mới: mô-đun đăng ký muộn (sau lần đầu tab hiện) vẫn
 * được gắn, không bắt người dùng chuyển tab đi rồi quay lại. ganKhe() tự
 * bỏ qua khe đã gắn, nên gọi lặp không tốn gì. */
function ganTabDangHien() {
  const id = tabCuaMan(state.view);
  const o = id && document.getElementById(id);
  if (!o) return;
  ganKhe(o);
  $$("[data-gan]", o).forEach(ganKhe);
}

function veTab(man) {
  const id = tabCuaMan(man);
  const v = $(`.view[data-view="${man}"]`);
  if (!v || !id) return;
  state.tab[man] = id;
  $$(".tabbar__nut", v).forEach((b) => {
    const on = b.dataset.tab === id;
    b.hidden = !tabDuocThay(b.dataset.tab);
    b.classList.toggle("is-on", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
    b.tabIndex = on ? 0 : -1;
  });
  cacTab(man).forEach((t) => { t.hidden = t.id !== id; });
  const o = document.getElementById(id);
  ganKhe(o);
  $$("[data-gan]", o).forEach(ganKhe);
  o.dispatchEvent(new CustomEvent("tab:hien", { detail: { id } }));
  $$(".tab__gan", o).forEach((g) =>
    g.dispatchEvent(new CustomEvent("tab:hien", { detail: { id: g.dataset.ganVao } })));
}

/* MỘT chỗ đổi màn. `ten` là tên màn, tên màn cũ, hoặc id một tab. Trước
   đây logic này bị chép lại ở `moManKetNoi`, và mỗi bản chép là một chỗ có
   thể quên cập nhật khi thanh điều hướng đổi. `lamMoi = false` chỉ dành
   cho lúc dựng menu theo quyền: vòng làm mới đầu tiên chạy ngay sau đó. */
function doiMan(ten, tab, lamMoi = true) {
  ten = MAN_CU[ten] || ten;
  if (manCuaTab(ten)) { tab = ten; ten = manCuaTab(ten); }
  state.view = ten;
  if (tab) state.tab[ten] = tab;
  $$(".rail__item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === ten));
  $$(".view").forEach((v) => v.classList.toggle("is-active", v.dataset.view === ten));
  veTab(ten);
  if ($(`#railCaiDatCon [data-view="${ten}"]`)) moNhomCaiDat(true);
  dongMenuDiDong();
  if (lamMoi) refresh();
}

$$(".rail__item").forEach((btn) =>
  btn.addEventListener("click", () => doiMan(btn.dataset.view))
);

/* Nối nút tab với khung tab cho trình đọc màn hình (aria-labelledby). Dựng
   ở đây thay vì viết tay trong index.html: id nút suy ra từ id tab, nên đổi
   id tab không thể để lại một nhãn trỏ vào hư không. */
$$(".tabbar__nut").forEach((b) => {
  b.id = `${b.dataset.tab}-nut`;
  document.getElementById(b.dataset.tab)?.setAttribute("aria-labelledby", b.id);
});

/* Bấm tab, hoặc mũi tên trái/phải khi đang đứng trên thanh tab (mẫu tablist
   của WAI-ARIA — người dùng bàn phím không phải Tab qua từng nút). */
$$(".tabbar").forEach((bar) => {
  bar.addEventListener("click", (e) => {
    const b = e.target.closest(".tabbar__nut");
    if (b) doiMan(b.dataset.tab);
  });
  bar.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const nut = $$(".tabbar__nut", bar).filter((b) => !b.hidden);
    const i = nut.indexOf(document.activeElement);
    if (i < 0) return;
    const k = nut[(i + (e.key === "ArrowRight" ? 1 : nut.length - 1)) % nut.length];
    k.focus();
    doiMan(k.dataset.tab);
  });
});

/* ---- nhóm "Cài đặt & Quản trị" thu gọn được ---- */
function moNhomCaiDat(mo) {
  const con = $("#railCaiDatCon");
  if (!con) return;
  con.hidden = !mo;
  $("#railCaiDatNut").setAttribute("aria-expanded", mo ? "true" : "false");
  $("#railCaiDat").classList.toggle("is-mo", mo);
}
$("#railCaiDatNut")?.addEventListener("click", () =>
  moNhomCaiDat($("#railCaiDatCon").hidden));

/* ---- thanh bên ở khổ hẹp: ẩn hẳn, mở bằng nút ☰ ở thanh trên ---- */
function dongMenuDiDong() {
  $("#rail")?.classList.remove("is-mo");
  $("#railMo")?.setAttribute("aria-expanded", "false");
}
$("#railMo")?.addEventListener("click", () => {
  const mo = !$("#rail").classList.contains("is-mo");
  $("#rail").classList.toggle("is-mo", mo);
  $("#railMo").setAttribute("aria-expanded", mo ? "true" : "false");
});

/* Ẩn mục, tab, cả nhóm Cài đặt mà người này không có quyền. Gọi một lần
 * sau khi biết quyền (kiemPhien). Màn đang mở bị ẩn thì chuyển sang màn
 * đầu tiên còn thấy — không để người ta đứng trước một màn rỗng. */
function apDungQuyenMenu() {
  $$(".rail__item").forEach((b) => { b.hidden = !manDuocThay(b.dataset.view); });
  const nhom = $("#railCaiDat");
  if (nhom) nhom.hidden = !$$(".rail__item", nhom).some((b) => !b.hidden);
  $$(".tabbar__nut").forEach((b) => { b.hidden = !tabDuocThay(b.dataset.tab); });
  if (!manDuocThay(state.view)) {
    const dau = $$(".rail__item").find((b) => !b.hidden);
    if (dau) { doiMan(dau.dataset.view, undefined, false); return; }
  }
  veTab(state.view);
}
