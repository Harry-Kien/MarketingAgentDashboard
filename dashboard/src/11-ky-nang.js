/* ---------------- kỹ năng (skill) và plugin ---------------- */

const RUI_RO_NHAN = { doc: "đọc", ghi_nhan: "ghi nhận", hanh_dong: "HÀNH ĐỘNG" };
const NHOM_NHAN = {
  tu_van: "Tư vấn", don_hang: "Đơn hàng", sau_ban: "Sau bán",
  marketing: "Marketing", con_nguoi: "Con người",
};

/* Bốn loại plugin, nói bằng tiếng Việt. Máy chủ chỉ biết mã (`tra_bang`…);
 * người vận hành chỉ cần biết nhãn. Bảng này là chỗ DUY NHẤT dịch hai chiều,
 * nên thêm loại thứ năm ở máy chủ mà quên đây thì test đọc form sẽ đỏ.
 *
 * `tham_so` là tham số mặc định: model điền gì vào công cụ. Người vận hành
 * hầu như không cần đụng — hai loại tra cứu luôn nhận đúng một thứ (điều
 * khách hỏi), chuyển người thì không nhận gì. Chỉ gọi API mới cần tự đặt,
 * vì tên tham số phải khớp chỗ `{ma}` trong địa chỉ. */
const PLUGIN_LOAI = {
  tra_bang: {
    nhan: "Tra bảng hỏi → đáp",
    giai_thich: "Bạn nạp một bảng hai cột. Khách hỏi trúng cột trái, agent trả lời bằng cột phải. Không khớp thì agent nói chưa có thông tin, không đoán.",
    tham_so: { ten: "khoa", mo_ta: "Điều khách đang hỏi, ví dụ tên sản phẩm hay tên chi nhánh" },
    thu: "Kem chống nắng",
  },
  tra_tai_lieu: {
    nhan: "Hỏi kho tri thức, giới hạn một nhóm tài liệu",
    giai_thich: "Như kỹ năng tìm kiến thức có sẵn, nhưng chỉ tra trong những tài liệu có tên chứa mẩu chữ bạn đặt. Dùng khi một chủ đề cần nguồn riêng, không lẫn tài liệu khác.",
    tham_so: { ten: "cau_hoi", mo_ta: "Câu hỏi của khách, giữ nguyên ý" },
    thu: "Bảo hành bao lâu?",
  },
  chuyen_chuyen_biet: {
    nhan: "Chuyển người kèm lý do riêng",
    giai_thich: "Gặp đúng tình huống này, agent dừng lại và giao cho người trực kèm một câu lý do bạn viết sẵn. Không tốn tiền, không trả lời thay.",
    tham_so: null,
    thu: "",
  },
  goi_api_doc: {
    nhan: "Gọi một hệ thống ngoài (chỉ đọc)",
    giai_thich: "Agent GET một địa chỉ HTTPS bạn cho phép và đọc kết quả. Máy chủ đó phải nằm trong KY_NANG_HOST_CHO_PHEP ở .env — lớp chặn này cố ý nằm ngoài dashboard.",
    tham_so: { ten: "ma", mo_ta: "Giá trị điền vào chỗ {ma} trong địa chỉ" },
    thu: "SP001",
  },
};

/* Mẫu có sẵn — người vận hành SỬA chứ không VIẾT, và đó là khác biệt giữa
 * dùng được và bỏ đó. Mỗi mẫu là một bản mô tả hoàn chỉnh; test đưa từng
 * mẫu qua `doc_ban_mo_ta` thật, nên mẫu sai không lọt ra được.
 *
 * Khoá mẫu phải ĐỦ RIÊNG: danh mục cửa hàng có bốn sản phẩm chứa chữ
 * "serum", nên một dòng "serum" trả lời thay cho cả bốn — chắc nịch, không
 * mơ hồ, nên cũng không có nhánh hỏi lại nào chạy. */
const PLUGIN_MAU = {
  bao_hanh: {
    nhan: "Bảo hành theo dòng sản phẩm",
    ten: "tra_bao_hanh",
    loai: "tra_bang",
    mo_ta: "Tra thời hạn bảo hành và hạn dùng sau khi mở nắp của một dòng sản phẩm theo tên dòng. Không dùng cho câu hỏi về đổi trả.",
    tham_so: [{ ten: "khoa", mo_ta: "Tên dòng sản phẩm khách hỏi", bat_buoc: true }],
    cau_hinh: { bang: {
      "Kem Chống Nắng": "12 tháng sau khi mở nắp",
      "Sữa Rửa Mặt": "12 tháng sau khi mở nắp",
      "Nước Tẩy Trang": "12 tháng sau khi mở nắp",
    } },
  },
  dia_chi: {
    nhan: "Địa chỉ và giờ mở cửa",
    ten: "tra_dia_chi_cua_hang",
    loai: "tra_bang",
    mo_ta: "Tra địa chỉ và giờ mở cửa của một chi nhánh theo tên khu vực hoặc tên đường. Không dùng cho câu hỏi giao hàng.",
    tham_so: [{ ten: "khoa", mo_ta: "Tên khu vực, quận hoặc tên đường khách hỏi", bat_buoc: true }],
    cau_hinh: { bang: {
      "Dĩ An": "90 Cây Da Xề, Đông Hoà, Dĩ An — 8h đến 21h hằng ngày",
      "Thủ Đức": "Số 1 Võ Văn Ngân, Thủ Đức — 8h đến 21h hằng ngày",
    } },
  },
  ban_buon: {
    nhan: "Chuyển bộ phận bán buôn",
    ten: "chuyen_ban_buon",
    loai: "chuyen_chuyen_biet",
    mo_ta: "Khách hỏi giá sỉ, mở đại lý, hợp tác phân phối hoặc mua số lượng lớn từ 20 sản phẩm trở lên.",
    tham_so: [],
    cau_hinh: { ly_do: "Khách hỏi hợp tác bán buôn hoặc mở đại lý" },
  },
  chinh_sach: {
    nhan: "Hỏi riêng tài liệu chính sách",
    ten: "tra_chinh_sach",
    loai: "tra_tai_lieu",
    mo_ta: "Tra các câu hỏi về chính sách đổi trả, hoàn tiền và bảo hành trong đúng nhóm tài liệu chính sách của cửa hàng.",
    tham_so: [{ ten: "cau_hoi", mo_ta: "Câu hỏi của khách, giữ nguyên ý", bat_buoc: true }],
    cau_hinh: { nhom_tai_lieu: "chinh-sach", k: 4 },
  },
};

/* Tên tiếng Việt → mã máy hợp lệ với `_TEN_RE` của máy chủ: chữ thường
 * không dấu, số, gạch dưới, bắt đầu bằng chữ, 3–40 ký tự.
 *
 * Luôn trả về một mã hợp lệ kể cả khi nhãn rỗng hay toàn ký hiệu — lỗi
 * "tên không hợp lệ" của máy chủ nói về chữ thường không dấu, đúng thứ ô
 * này sinh ra để giấu đi, nên không được để nó lộ ra lần nữa. */
function sinhMaPlugin(nhan) {
  let s = String(nhan || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d").replace(/Đ/g, "D").toLowerCase()
    .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").replace(/_+/g, "_");
  if (!/^[a-z]/.test(s)) s = "kn_" + s;
  s = s.slice(0, 40).replace(/_+$/g, "");
  while (s.length < 3) s += "_x";
  return s;
}

/* Đọc chữ dán vào bảng: mỗi dòng một cặp, cách nhau bằng tab (Excel), dấu
 * hai chấm, hoặc gạch đứng. Dòng trống bỏ qua; dòng không tách được thì giữ
 * nguyên ở cột trái để người nhìn thấy và tự sửa, thay vì mất im lặng. */
function docBangDan(text) {
  const ra = [];
  for (const dong of String(text || "").split(/\r?\n/)) {
    const d = dong.trim();
    if (!d) continue;
    let k = -1;
    for (const sep of ["\t", "|", ":"]) { const t = d.indexOf(sep); if (t > 0) { k = t; break; } }
    if (k < 0) { ra.push([d, ""]); continue; }
    ra.push([d.slice(0, k).trim(), d.slice(k + 1).trim()]);
  }
  return ra;
}

function themDongBang(khoa = "", gia_tri = "") {
  const tb = $("#plugin-bang tbody");
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input class="plugin-bang__khoa" placeholder="Hồ Chí Minh | Sài Gòn | TPHCM" maxlength="200"></td>
    <td><input class="plugin-bang__gia" placeholder="12 tháng sau khi mở nắp" maxlength="500"></td>
    <td><button type="button" class="btn btn--sm btn--ghost" data-bang-xoa title="Bỏ dòng">✕</button></td>`;
  tr.querySelector(".plugin-bang__khoa").value = khoa;
  tr.querySelector(".plugin-bang__gia").value = gia_tri;
  tb.appendChild(tr);
  return tr;
}

function docBang() {
  const bang = {};
  for (const tr of document.querySelectorAll("#plugin-bang tbody tr")) {
    const k = tr.querySelector(".plugin-bang__khoa").value.trim();
    const v = tr.querySelector(".plugin-bang__gia").value.trim();
    if (!k && !v) continue;
    if (!k || !v) throw new Error(`Dòng "${k || v}" thiếu một bên — cần đủ cả "khách hỏi về" và "agent trả lời".`);
    if (bang[k] !== undefined) throw new Error(`"${k}" xuất hiện hai lần trong bảng. Giữ một dòng thôi.`);
    bang[k] = v;
  }
  return bang;
}

function datBang(bang) {
  $("#plugin-bang tbody").innerHTML = "";
  for (const [k, v] of Object.entries(bang || {})) themDongBang(k, v);
  if (!Object.keys(bang || {}).length) { themDongBang(); themDongBang(); }
}

function themDongCauThu(hoi = "", mong_doi = "") {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input class="cauthu__hoi" placeholder="đi biển" maxlength="200"></td>
    <td><input class="cauthu__mong" placeholder="kháng nước" maxlength="200"></td>
    <td><button type="button" class="btn btn--sm btn--ghost" data-cauthu-xoa title="Bỏ câu thử">✕</button></td>`;
  tr.querySelector(".cauthu__hoi").value = hoi;
  tr.querySelector(".cauthu__mong").value = mong_doi;
  $("#plugin-cauthu tbody").appendChild(tr);
  return tr;
}

function docCauThu() {
  const ra = [];
  for (const tr of document.querySelectorAll("#plugin-cauthu tbody tr")) {
    const hoi = tr.querySelector(".cauthu__hoi").value.trim();
    const mong = tr.querySelector(".cauthu__mong").value.trim();
    /* Cột phải để trống là CÓ NGHĨA: câu ấy phải không khớp. Chỉ bỏ dòng
     * khi cả hai ô đều trống. */
    if (!hoi) continue;
    ra.push({ hoi, mong_doi: mong });
  }
  return ra;
}

function datCauThu(ds) {
  $("#plugin-cauthu tbody").innerHTML = "";
  for (const c of ds || []) themDongCauThu(c.hoi, c.mong_doi);
}

/* Kết quả câu thử sau mỗi lần Lưu. Trượt thì phải NHÌN THẤY, nên nó nằm
 * ngay ô kết quả chứ không phải một toast biến mất sau ba giây. */
function hienCauThu(ds) {
  if (!ds || !ds.length) return "";
  const truot = ds.filter((x) => !x.dat);
  const dong = (x) => `<div class="row">
      <span class="row__flag ${x.dat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${x.dat ? "Đạt" : "TRƯỢT"}: ${esc(x.hoi)}</span>
        <span class="row__sub row__sub--thu">${x.mong_doi
          ? "mong đợi có: " + esc(x.mong_doi)
          : "mong đợi KHÔNG khớp dòng nào"} · agent trả: ${esc(x.nhan_duoc)}</span>
      </span>
    </div>`;
  return `<p class="panel__note${truot.length ? " plugin-loi" : ""}">Câu thử: ${
    ds.length - truot.length}/${ds.length} đạt${
    truot.length ? " — sửa bảng hoặc sửa câu thử cho khớp lại." : "."}</p>`
    + ds.map(dong).join("");
}

/* Tên kỹ năng viết hoa cột trái để nhìn ra mẫu, nhưng mã máy mới là thứ gửi
 * đi — hiện nó ngay dưới ô để không có bất ngờ lúc lưu. */
function capNhatMaPlugin() {
  const f = $("#pluginform");
  if (!f) return;
  /* Ô tên còn trống thì hiện gạch ngang, không hiện mã.
   *
   * `sinhMaPlugin("")` buộc phải trả một mã HỢP LỆ vì máy chủ đòi thế,
   * nhưng đem mã ấy hiện ra là người vận hành đọc được một cái tên họ
   * chưa hề đặt, và tưởng hệ thống đã quyết hộ. */
  const nhan = f.elements.nhan.value.trim();
  $("#plugin-ma").textContent = nhan ? sinhMaPlugin(nhan) : "—";
}

function doiLoaiPlugin(loai, { giuThamSo = false } = {}) {
  const f = $("#pluginform");
  const meta = PLUGIN_LOAI[loai];
  if (!f || !meta) return;
  f.elements.loai.value = loai;
  $("#plugin-loai-giaithich").textContent = meta.giai_thich;
  for (const o of f.querySelectorAll("[data-cauhinh]")) o.hidden = o.dataset.cauhinh !== loai;
  const nangCao = $("#plugin-nangcao");
  const oThu = $("#plugin-thu-o");
  if (!meta.tham_so) {
    nangCao.hidden = true;
    oThu.hidden = true;
    f.elements.tham_so_ten.value = "";
    f.elements.tham_so_mo_ta.value = "";
  } else {
    nangCao.hidden = false;
    oThu.hidden = false;
    if (!giuThamSo) {
      f.elements.tham_so_ten.value = meta.tham_so.ten;
      f.elements.tham_so_mo_ta.value = meta.tham_so.mo_ta;
    }
    f.elements.thu_gia_tri.placeholder = meta.thu;
  }
  if (loai === "tra_bang" && !$("#plugin-bang tbody tr")) datBang({});
}

/* Nạp một plugin ĐÃ LƯU ngược vào form để sửa.
 *
 * Gán `.value` cho từng ô, không dựng HTML: bảng là chữ do người vận hành
 * gõ, và nó vẫn là chuỗi đi qua máy chủ trước khi về đây.
 *
 * Ô tên nhận lại MÃ MÁY chứ không phải một nhãn tiếng Việt đoán ngược ra
 * từ nó. `sinhMaPlugin` bỏ dấu nên không có đường về; đoán bừa một nhãn
 * rồi sinh lại mã khác đi là lưu ra plugin THỨ HAI, còn bản cũ vẫn nằm đó
 * với cấu hình cũ — hỏng im lặng, đúng kiểu repo này sợ. Mã máy đi qua
 * `sinhMaPlugin` cho lại chính nó, nên lưu là ghi đè đúng chỗ. */
function napPluginVaoForm(ten, bm) {
  const f = $("#pluginform");
  if (!f || !bm) return;
  f.reset();
  f.elements.nhan.value = ten;
  f.elements.mo_ta.value = bm.mo_ta || "";
  doiLoaiPlugin(bm.loai, { giuThamSo: true });
  const t = (bm.tham_so || [])[0];
  if (t) {
    f.elements.tham_so_ten.value = t.ten || "";
    f.elements.tham_so_mo_ta.value = t.mo_ta || "";
  }
  const ch = bm.cau_hinh || {};
  if (bm.loai === "tra_bang") { datBang(ch.bang || {}); datCauThu(bm.cau_thu); }
  if (bm.loai === "tra_tai_lieu") {
    f.elements.nhom_tai_lieu.value = ch.nhom_tai_lieu || "";
    f.elements.k.value = ch.k || 4;
  }
  if (bm.loai === "chuyen_chuyen_biet") f.elements.ly_do.value = ch.ly_do || "";
  if (bm.loai === "goi_api_doc") {
    f.elements.url.value = ch.url || "";
    f.elements.han_giay.value = ch.han_giay || 5;
  }
  capNhatMaPlugin();
  $("#plugin-ketqua").innerHTML = "";
  for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.remove("is-on");
  f.scrollIntoView({ block: "start", behavior: "smooth" });
  f.elements.mo_ta.focus();
}

function dienMauPlugin(ma) {
  const m = PLUGIN_MAU[ma];
  const f = $("#pluginform");
  if (!m || !f) return;
  f.reset();
  f.elements.nhan.value = m.nhan;
  f.elements.mo_ta.value = m.mo_ta;
  doiLoaiPlugin(m.loai);
  if (m.tham_so[0]) {
    f.elements.tham_so_ten.value = m.tham_so[0].ten;
    f.elements.tham_so_mo_ta.value = m.tham_so[0].mo_ta;
  }
  const ch = m.cau_hinh;
  if (m.loai === "tra_bang") datBang(ch.bang);
  if (m.loai === "tra_tai_lieu") { f.elements.nhom_tai_lieu.value = ch.nhom_tai_lieu; f.elements.k.value = ch.k || 4; }
  if (m.loai === "chuyen_chuyen_biet") f.elements.ly_do.value = ch.ly_do;
  if (m.loai === "goi_api_doc") { f.elements.url.value = ch.url; f.elements.han_giay.value = ch.han_giay || 5; }
  capNhatMaPlugin();
  $("#plugin-ketqua").innerHTML = "";
  for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.toggle("is-on", c.dataset.pluginMau === ma);
  f.elements.nhan.focus();
}

/* Đọc form thành bản mô tả. Dùng chung cho nút "Chạy thử" và nút "Lưu" —
 * hai đường khác nhau đọc form theo hai cách là chạy thử một thứ rồi lưu
 * một thứ khác, và người vận hành không có cách nào biết.
 *
 * Kiểm ở đây chỉ để nói lỗi bằng câu ngắn NGAY tại ô; bộ kiểm thật vẫn là
 * `doc_ban_mo_ta` ở máy chủ, và câu lỗi của nó cũng đã là tiếng Việt. */
function docFormPlugin() {
  const f = $("#pluginform");
  const g = (n) => (f.elements[n]?.value || "").trim();
  const loai = g("loai");
  const meta = PLUGIN_LOAI[loai];
  if (!meta) throw new Error("Chọn kỹ năng này làm gì trước.");
  if (!g("nhan")) throw new Error("Đặt tên kỹ năng trước — tiếng Việt có dấu cũng được.");
  if (g("mo_ta").length < 20) throw new Error("Mô tả quá ngắn. Viết rõ khi nào agent dùng và khi nào đừng dùng (ít nhất 20 ký tự).");

  let cau_hinh = {};
  if (loai === "tra_bang") {
    cau_hinh = { bang: docBang() };
    if (!Object.keys(cau_hinh.bang).length) throw new Error("Bảng đang trống. Thêm ít nhất một dòng.");
  } else if (loai === "tra_tai_lieu") {
    if (!g("nhom_tai_lieu")) throw new Error("Chọn hoặc gõ một mẩu tên nhóm tài liệu — bỏ trống thì kỹ năng này thành bản sao của tìm kiến thức.");
    cau_hinh = { nhom_tai_lieu: g("nhom_tai_lieu"), k: parseInt(g("k") || "4", 10) };
  } else if (loai === "chuyen_chuyen_biet") {
    if (!g("ly_do")) throw new Error("Viết câu người trực sẽ đọc.");
    cau_hinh = { ly_do: g("ly_do") };
  } else if (loai === "goi_api_doc") {
    if (!g("url").startsWith("https://")) throw new Error("Địa chỉ phải bắt đầu bằng https://");
    cau_hinh = { url: g("url"), han_giay: parseFloat(g("han_giay") || "5") };
  }

  const tham_so = [];
  if (meta.tham_so) {
    const ten = g("tham_so_ten") || meta.tham_so.ten;
    const mo_ta = g("tham_so_mo_ta") || meta.tham_so.mo_ta;
    tham_so.push({ ten, mo_ta, bat_buoc: true });
  }
  return { ten: sinhMaPlugin(g("nhan")), loai, mo_ta: g("mo_ta"), tham_so, cau_hinh,
           cau_thu: loai === "tra_bang" ? docCauThu() : [] };
}

/* Kết quả chạy thử thành câu người đọc được. Đây là dữ liệu do người vận
 * hành gõ vào bảng, nhưng vẫn là chuỗi đi vào innerHTML — esc() mọi thứ. */
function hienKetQuaThu(loai, r) {
  const dong = (nhan, gt, xau = false) => `<div class="row"><span class="row__flag ${
    xau ? "row__flag--halt" : "row__flag--auto"}"></span><span class="row__body"><span class="row__title">${
    esc(nhan)}</span><span class="row__sub row__sub--thu">${esc(gt)}</span></span></div>`;
  const ghiChu = r && r.ghi_chu ? dong("Agent được dặn", r.ghi_chu) : "";
  if (!r) return dong("Không có kết quả", "", true);
  if (r.loi) return dong("Lỗi", r.loi, true) + ghiChu;
  if (loai === "chuyen_chuyen_biet" || r.can_chuyen_nhan_vien) {
    return dong("Chuyển cho người", "Lý do người trực thấy: " + (r.ly_do || "")) + ghiChu;
  }
  if (r.tim_thay === false) {
    const nhieu = Array.isArray(r.nhieu_ket_qua) && r.nhieu_ket_qua.length
      ? " Khớp nhiều dòng: " + r.nhieu_ket_qua.join(", ") : "";
    return dong("Không tìm thấy", "Agent sẽ nói chưa có thông tin, không đoán." + nhieu, true) + ghiChu;
  }
  if (loai === "tra_bang") return dong("Tìm thấy: " + (r.khoa || ""), r.gia_tri || "") + ghiChu;
  if (loai === "tra_tai_lieu" && Array.isArray(r.doan)) {
    return r.doan.map((d) => dong("Tìm thấy trong " + (d.tai_lieu || ""), d.noi_dung || "")).join("") + ghiChu;
  }
  return dong("Tìm thấy", JSON.stringify(r).slice(0, 700)) + ghiChu;
}

/* Tên tài liệu đã nạp, cho ô "nhóm tài liệu" gợi ý. Tải MỘT lần khi mở
 * màn, không theo vòng 6 giây — vòng đó vẽ lại datalist là vẽ thừa. */
async function napNhomTaiLieuPlugin() {
  if (state.pluginNhomDaTai) return;
  try {
    const ds = await api("/knowledge");
    $("#plugin-nhom-ds").innerHTML = ds.map((d) => `<option value="${esc(d.title)}">`).join("");
    state.pluginNhomDaTai = true;
  } catch (e) { /* không có gợi ý thì vẫn gõ tay được */ }
}

function khoiTaoFormPlugin() {
  const f = $("#pluginform");
  if (!f || f.dataset.daKhoiTao) return;
  f.dataset.daKhoiTao = "1";
  $("#plugin-loai").innerHTML = Object.entries(PLUGIN_LOAI)
    .map(([ma, m]) => `<option value="${ma}">${esc(m.nhan)}</option>`).join("");
  $("#plugin-mau").innerHTML = Object.entries(PLUGIN_MAU)
    .map(([ma, m]) => `<button type="button" class="chip" data-plugin-mau="${ma}">${esc(m.nhan)}</button>`).join("");
  doiLoaiPlugin("tra_bang");
  capNhatMaPlugin();

  f.elements.nhan.addEventListener("input", capNhatMaPlugin);
  $("#plugin-loai").addEventListener("change", (e) => doiLoaiPlugin(e.target.value));
  $("#plugin-bang-them").addEventListener("click", () => themDongBang().querySelector("input").focus());
  $("#plugin-cauthu-them").addEventListener("click", () => themDongCauThu().querySelector("input").focus());
  $("#plugin-cauthu").addEventListener("click", (e) => {
    const b = e.target.closest("[data-cauthu-xoa]");
    if (b) b.closest("tr").remove();
  });
  $("#plugin-mau").addEventListener("click", (e) => {
    const c = e.target.closest("[data-plugin-mau]");
    if (c) dienMauPlugin(c.dataset.pluginMau);
  });
  $("#plugin-bang").addEventListener("click", (e) => {
    const b = e.target.closest("[data-bang-xoa]");
    if (b) b.closest("tr").remove();
  });
  /* Dán nhiều dòng từ Excel vào bất kỳ ô nào của bảng: mỗi dòng dán thành
   * một hàng, thay cho việc gõ từng ô. */
  $("#plugin-bang").addEventListener("paste", (e) => {
    const text = e.clipboardData?.getData("text") || "";
    if (!/[\r\n\t]/.test(text)) return;
    const cap = docBangDan(text);
    if (!cap.length) return;
    e.preventDefault();
    const tr = e.target.closest("tr");
    for (const [k, v] of cap) themDongBang(k, v);
    if (tr && !tr.querySelector(".plugin-bang__khoa").value && !tr.querySelector(".plugin-bang__gia").value) tr.remove();
  });
}

$("#plugin-thu")?.addEventListener("click", async () => {
  const hop = $("#plugin-ketqua");
  try {
    const bm = docFormPlugin();
    const args = {};
    if (bm.tham_so.length) {
      const v = $("#pluginform").elements.thu_gia_tri.value.trim();
      if (!v) throw new Error("Gõ một câu khách hỏi vào ô \"Thử với câu khách hỏi\" rồi bấm Chạy thử.");
      args[bm.tham_so[0].ten] = v;
    }
    hop.innerHTML = `<p class="empty">Đang chạy thử…</p>`;
    const r = await api("/ky-nang/plugin/thu", {
      method: "POST",
      body: JSON.stringify({ ban_mo_ta: bm, args }),
    });
    hop.innerHTML = hienKetQuaThu(bm.loai, r.ket_qua);
  } catch (e) {
    hop.innerHTML = `<p class="empty plugin-loi">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
});

$("#pluginform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const bm = docFormPlugin();
    const ket = await api("/ky-nang/plugin", { method: "POST", body: JSON.stringify(bm) });
    e.target.reset();
    doiLoaiPlugin("tra_bang");
    datBang({});
    capNhatMaPlugin();
    datCauThu([]);
    $("#plugin-ketqua").innerHTML = hienCauThu(ket.cau_thu);
    for (const c of document.querySelectorAll("#plugin-mau .chip")) c.classList.remove("is-on");
    const truot = (ket.cau_thu || []).filter((x) => !x.dat).length;
    toast(truot
      ? `Đã lưu "${bm.ten}" — ${truot} câu thử TRƯỢT, xem bên dưới`
      : `Đã lưu và bật "${bm.ten}"`, !!truot);
    await loadKyNang();
  } catch (err) {
    $("#plugin-ketqua").innerHTML = `<p class="empty plugin-loi">${esc(err.message)}</p>`;
    toast(err.message, true);
  }
});

/* Ba cách thêm kỹ năng, mỗi cách một câu nói KHI NÀO dùng nó.
 *
 * Chỗ khó của màn này chưa bao giờ là số ô nhập, mà là câu "tôi nên dùng
 * đường nào". Trước đây hai form đặt cạnh nhau trông ngang hàng và không
 * chỗ nào trả lời câu đó. */
const THEM_CACH = {
  bang: {
    nhan: "Tự viết bảng hỏi đáp",
    giai_thich: "Cho số liệu ngắn của shop: phí ship, bảo hành, địa chỉ, giờ mở cửa. Bạn gõ bảng hai cột bằng tiếng Việt, không cần biết kỹ thuật. Đây là cách hay dùng nhất.",
  },
  goi: {
    nhan: "Cài gói có sẵn",
    giai_thich: "Khi một chủ đề cần cả hướng dẫn tư vấn, công cụ tra cứu và tài liệu đi cùng nhau. Gói có phiên bản và lịch sử, khôi phục được nếu bản mới tệ hơn.",
  },
  mcp: {
    nhan: "Nối máy chủ MCP",
    giai_thich: "Khi công cụ đã nằm ở hệ thống khác và bạn muốn agent gọi sang. Địa chỉ phải nằm trong danh sách cho phép ở .env, và công cụ mặc định chỉ đọc.",
  },
};

function doiCachThem(cach) {
  const meta = THEM_CACH[cach];
  if (!meta) return;
  $("#them-giaithich").textContent = meta.giai_thich;
  for (const c of document.querySelectorAll("#them-chon .chip")) {
    c.classList.toggle("is-on", c.dataset.them === cach);
  }
  for (const o of document.querySelectorAll("[data-them-o]")) {
    o.hidden = o.dataset.themO !== cach;
  }
}

/* Bốn nguồn, một hình dạng dòng.
 *
 * Kỹ năng viết sẵn và công cụ cắm thêm có hai hình dạng dữ liệu khác nhau
 * (một bên có `nhom`/`tat_thi_mat_gi`, bên kia có `loai`/`tham_so`), nên
 * hàm này chuẩn hoá về một `nguon` rồi mới vẽ. Trộn hai vòng lặp vẽ khác
 * nhau vào một danh sách là hai chỗ phải nhớ sửa mỗi lần đổi cột.
 *
 * `nguon` quyết định nút nào hiện, và điều đó KHÔNG phải để cho đẹp: chỗ
 * đi sửa mỗi loại một khác. Plugin rời sửa tại chỗ, công cụ của gói phải
 * cài lại gói, công cụ MCP phải đồng bộ lại máy chủ. Hiện nút Sửa cho cả
 * ba rồi để máy chủ từ chối là dạy người ta bỏ qua thông báo lỗi. */
function veDongKyNang(k) {
  const nguon = k.nguon;
  const bat = k.bat !== false;
  const huy_hieu = {
    viet_san: '<b class="pill">viết sẵn</b>',
    tu_tao: '<b class="pill pill--tu-tao">tự tạo</b>',
    goi: `<b class="pill">gói ${esc(k.goi || "")}</b>`,
    mcp: `<b class="pill">MCP · ${esc(k.mcp || "")}</b>`,
  }[nguon] || "";

  const truot = (k.khong_khop || []).length
    ? `<span class="row__sub row__sub--truot">
         Khách hỏi mà bảng chưa có: ${(k.khong_khop || []).map((x) =>
           /* Chữ model điền từ câu của khách, qua CSDL rồi vào innerHTML. */
           `<button type="button" class="chip" data-them-khoa="${esc(x.gia_tri)}"
              data-them-vao="${esc(k.ten)}" title="Thêm dòng này vào bảng"
              >${esc(x.gia_tri)} (${esc(String(x.so_lan))})</button>`).join(" ")}
       </span>`
    : "";

  const nut = nguon === "viet_san"
    ? (k.tat_duoc
        ? `<button type="button" class="btn btn--sm ${bat ? "btn--halt" : ""}"
             data-kynang="${esc(k.ten)}" data-bat="${bat ? "0" : "1"}">${
             bat ? "Tắt" : "Bật"}</button>`
        : "")
    : nguon === "tu_tao"
      ? `${k.ban_mo_ta ? `<button type="button" class="btn btn--sm"
             data-plugin-sua="${esc(k.ten)}">Sửa</button>
           <button type="button" class="btn btn--sm"
             data-plugin-lichsu="${esc(k.ten)}">Lịch sử</button> ` : ""}<button
             type="button" class="btn btn--sm btn--halt"
             data-plugin-xoa="${esc(k.ten)}">Xoá</button>`
      : "";

  return `<div class="row" data-nguon="${esc(nguon)}">
      <span class="row__flag ${bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(k.ten)} ${huy_hieu}
          ${k.muc_rui_ro === "hanh_dong" ? '<b class="pill pill--halt">HÀNH ĐỘNG</b>' : ""}
          ${nguon === "viet_san" && !k.tat_duoc ? '<b class="pill">không tắt được</b>' : ""}</span>
        <span class="row__sub">${esc(k.dong_phu)}</span>
        <span class="row__sub">${esc(k.tom_tat)}</span>
        ${k.tat_thi_mat_gi ? `<span class="row__sub"><em>Tắt thì:</em> ${esc(k.tat_thi_mat_gi)}</span>` : ""}
        ${truot}
      </span>
      <span class="row__side">${nut}</span>
    </div>`;
}

/* Gộp bốn nguồn về một hình dạng. Chuẩn hoá ở ĐÂY chứ không ở `veDongKyNang`
 * để hàm vẽ không phải biết hình dạng nào của máy chủ là của nguồn nào. */
function gopKyNang(d) {
  const ra = d.co_san.map((k) => ({
    ...k,
    nguon: "viet_san",
    dong_phu: `${NHOM_NHAN[k.nhom] || k.nhom} · ${RUI_RO_NHAN[k.muc_rui_ro] || k.muc_rui_ro}`
      + (k.can_erp ? " · cần ERP" : "")
      + (k.can_kho_tri_thuc ? " · cần kho tri thức" : "")
      + ` · gọi 7 ngày: ${k.so_lan_7_ngay || 0}`
      + (k.so_loi_7_ngay ? ` (${k.so_loi_7_ngay} lỗi)` : ""),
  }));
  for (const p of d.plugin) {
    ra.push({
      ...p,
      nguon: p.mcp ? "mcp" : p.goi ? "goi" : "tu_tao",
      tom_tat: p.mo_ta,
      dong_phu: (PLUGIN_LOAI[p.loai]?.nhan || p.loai)
        + (p.tham_so.length ? ` · tham số: ${p.tham_so.join(", ")}` : "")
        + ` · gọi 7 ngày: ${p.so_lan_7_ngay || 0}`
        + (p.so_loi_7_ngay ? ` (${p.so_loi_7_ngay} lỗi)` : ""),
    });
  }
  return ra;
}

function locKyNang(nguon) {
  state.locKyNang = nguon;
  for (const c of document.querySelectorAll("#kynang-loc .chip")) {
    c.classList.toggle("is-on", c.dataset.locNguon === nguon);
  }
  const map = { "viet-san": "viet_san", "tu-tao": "tu_tao", goi: "goi", mcp: "mcp" };
  for (const r of document.querySelectorAll("#kynang-tatca .row")) {
    r.hidden = nguon !== "tat-ca" && r.dataset.nguon !== map[nguon];
  }
}

async function loadKyNang() {
  khoiTaoFormPlugin();
  khoiTaoThemKyNang();
  napNhomTaiLieuPlugin();
  const d = await api("/ky-nang");
  const tat = d.co_san.filter((k) => !k.bat).length;
  $("#c-kynang").textContent = tat ? `${tat} tắt` : "";

  const tat_ca = gopKyNang(d);
  $("#kynang-tatca").innerHTML = tat_ca.map(veDongKyNang).join("");
  /* Trần 12 đếm CHUNG plugin rời, công cụ của gói và công cụ MCP. Ba danh
   * sách rời thì không chỗ nào hiện được tổng, và người vận hành chỉ biết
   * mình chạm trần đúng lúc bị từ chối. */
  $("#kynang-dem").textContent =
    `${tat_ca.length} kỹ năng · ${d.plugin.length}/${d.plugin_toi_da} suất cắm thêm đã dùng`;
  locKyNang(state.locKyNang || "tat-ca");

  try {
    await loadGoiKyNang();
  } catch (err) {
    // Lỗi của kho gói không được lan sang vòng làm mới 6 giây, và panel
    // phải NÓI là không tải được — "Chưa có gói nào." khi CSDL hỏng là xanh giả.
    $("#goi-ds").innerHTML = `<p class="empty">Không tải được gói kỹ năng: ${esc(err.message)}</p>`;
  }

  // Cùng lý do với gói: máy chủ MCP đọc riêng một bảng
  // (`mcp_may_chu`), lỗi ở đó (vault chưa cấu hình, cột thiếu) không được
  // làm chết cả màn Kỹ năng, và panel phải NÓI ra thay vì im lặng hiện
  // "Chưa có máy chủ MCP nào." — trông giống chưa từng ai nối, khác hẳn
  // sự thật là đã nối nhưng đang đọc lỗi.
  try {
    await loadMcp();
  } catch (err) {
    $("#mcp-ds").innerHTML = `<p class="empty">Không tải được máy chủ MCP: ${esc(err.message)}</p>`;
  }
}

function khoiTaoThemKyNang() {
  const hop = $("#them-chon");
  if (!hop || hop.dataset.daKhoiTao) return;
  hop.dataset.daKhoiTao = "1";
  doiCachThem("bang");
  hop.addEventListener("click", (e) => {
    const b = e.target.closest("[data-them]");
    if (b) doiCachThem(b.dataset.them);
  });
  $("#kynang-loc").addEventListener("click", (e) => {
    const b = e.target.closest("[data-loc-nguon]");
    if (b) locKyNang(b.dataset.locNguon);
  });
}

document.addEventListener("click", async (e) => {
  const bt = e.target.closest("[data-kynang]");
  if (bt) {
    const bat = bt.dataset.bat === "1";
    /* Xác nhận CHỈ khi tắt, không hỏi khi bật. Hỏi cả hai chiều thì hộp
     * thoại thành thói quen bấm OK, và lúc đó nó không còn chặn gì. */
    if (!bat && !confirm(
      `Tắt "${bt.dataset.kynang}"?\n\nAgent sẽ chuyển hội thoại cho người ` +
      `mỗi khi cần dùng kỹ năng này.`)) return;
    try {
      await api("/ky-nang/bat-tat", {
        method: "POST",
        body: JSON.stringify({ ten: bt.dataset.kynang, bat }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bk = e.target.closest("[data-them-khoa]");
  if (bk) {
    /* Bấm một khoá hay trượt là mở luôn form sửa với dòng ấy điền sẵn.
     * Nếu chỉ hiện danh sách thì người vận hành phải tự nhớ rồi tự gõ lại,
     * và bảng vẫn không lớn lên — đúng chỗ vòng cải thiện đứt. */
    try {
      const d = await api("/ky-nang");
      const p = d.plugin.find((x) => x.ten === bk.dataset.themVao);
      if (!p || !p.ban_mo_ta) { toast("Công cụ này sửa trong gói của nó", true); return; }
      napPluginVaoForm(p.ten, p.ban_mo_ta);
      const tr = themDongBang(bk.dataset.themKhoa, "");
      tr.querySelector(".plugin-bang__gia").focus();
      toast(`Điền câu trả lời cho "${bk.dataset.themKhoa}" rồi bấm Lưu và bật`);
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bl = e.target.closest("[data-plugin-lichsu]");
  if (bl) {
    const ten = bl.dataset.pluginLichsu;
    try {
      const ds = await api(`/ky-nang/plugin/${encodeURIComponent(ten)}/lich-su`);
      /* Vẽ ngay dưới ô kết quả của form, không mở hộp thoại: người đang so
       * bản cũ với bản đang chạy cần nhìn thấy cả hai. */
      $("#plugin-ketqua").innerHTML = ds.length
        ? `<p class="panel__note">Bản cũ của <b>${esc(ten)}</b> — khôi phục sẽ
             ghi đè bản đang chạy, và bản đang chạy vào lịch sử.</p>`
          + ds.map((x) => `<div class="row">
              <span class="row__flag row__flag--spend"></span>
              <span class="row__body">
                <span class="row__title">${esc(new Date(x.thay_luc).toLocaleString("vi-VN"))}</span>
                <span class="row__sub">người sửa: ${esc(x.thay_boi)}</span>
              </span>
              <span class="row__side"><button type="button" class="btn btn--sm"
                data-plugin-khoiphuc="${esc(ten)}" data-id="${esc(String(x.id))}"
                >Khôi phục</button></span>
            </div>`).join("")
        : `<p class="empty">${esc(ten)} chưa từng được sửa lần nào.</p>`;
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bkp = e.target.closest("[data-plugin-khoiphuc]");
  if (bkp) {
    const ten = bkp.dataset.pluginKhoiphuc;
    if (!confirm(`Khôi phục "${ten}" về bản này? Bản đang chạy sẽ vào lịch sử.`)) return;
    try {
      await api(`/ky-nang/plugin/${encodeURIComponent(ten)}/khoi-phuc/${encodeURIComponent(bkp.dataset.id)}`,
                { method: "POST" });
      $("#plugin-ketqua").innerHTML = "";
      toast(`Đã khôi phục "${ten}"`);
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bs = e.target.closest("[data-plugin-sua]");
  if (bs) {
    /* Đọc lại từ máy chủ chứ không giữ bản mô tả trong DOM: người khác có
     * thể vừa sửa chính plugin này, và nạp bản cũ vào form rồi bấm Lưu là
     * âm thầm quay ngược thay đổi của họ. */
    try {
      const d = await api("/ky-nang");
      const p = d.plugin.find((x) => x.ten === bs.dataset.pluginSua);
      if (!p || !p.ban_mo_ta) { toast("Công cụ này sửa trong gói của nó", true); return; }
      napPluginVaoForm(p.ten, p.ban_mo_ta);
      toast(`Đang sửa "${p.ten}" — bấm Lưu và bật để ghi đè`);
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-plugin-xoa]");
  if (bx) {
    if (!confirm(`Xoá hẳn plugin "${bx.dataset.pluginXoa}"?`)) return;
    try {
      await api("/ky-nang/plugin/" + encodeURIComponent(bx.dataset.pluginXoa),
                { method: "DELETE" });
      toast("Đã xoá");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
  }
});

