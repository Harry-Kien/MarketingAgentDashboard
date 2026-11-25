/* ---------------- Trách nhiệm trong hội thoại ----------------
 *
 * Mọi việc trong một hội thoại phải quy được về người (hoặc AI) đã làm nó
 * (rà soát 20.11.2026). Trước bản này màn hội thoại chỉ hiện "Nhân viên"
 * không tên; không ai duyệt, không hồ sơ agent nào, không lưới nào — dù phần
 * lớn dữ liệu ấy nằm sẵn trong CSDL.
 *
 * QUY ƯỚC HIỂN THỊ (chủ dự án, 21.11.2026):
 *   · Dưới mỗi tin MỘT dòng: Thời gian · Người gửi · Trạng thái.
 *   · Thông tin kỹ thuật (độ tin cậy, nguồn, thời gian xử lý, model, chi
 *     phí) KHÔNG hiện mặc định — chỉ trong "Chi tiết" / "Xem căn cứ".
 *   · Độ tin cậy KHÔNG BAO GIỜ hiện thành phần trăm: "87%" đọc như xác suất
 *     câu trả lời đúng, mà nó chỉ là điểm khớp tài liệu. Người trực thấy
 *     "Có căn cứ" / "Thiếu căn cứ"; con số thô chỉ ở phần kỹ thuật.
 *   · Lịch sử xử lý (bàn giao, sửa, duyệt, từ chối, đề xuất AI) nằm trong
 *     panel "Chi tiết" của hội thoại, không chiếm chỗ thường trực ở đầu
 *     hội thoại.
 *
 * Tệp này giữ phần VẼ; `03-hoi-thoai.js` gọi vào. Tách riêng vì 03 đã gần
 * trần 1000 dòng.
 */

/* Giờ của MỘT tin: hôm nay thì hh:mm, ngày khác thì kèm ngày. Chỉ hh:mm là
 * người đọc lại hội thoại ba ngày tuổi tưởng mọi tin cùng một buổi — và
 * "khách nhắn 9:05, mình trả lời 9:07" thật ra là cách nhau hai ngày. */
function gioTin(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const nay = new Date();
  const cungNgay = d.getFullYear() === nay.getFullYear()
    && d.getMonth() === nay.getMonth() && d.getDate() === nay.getDate();
  const gio = hhmm(iso);
  if (cungNgay) return gio;
  const ngay = d.toLocaleDateString("vi-VN", {
    day: "2-digit", month: "2-digit",
    ...(d.getFullYear() !== nay.getFullYear() ? { year: "numeric" } : {}),
  });
  return `${ngay} ${gio}`;
}

/* Người gửi, cụ thể nhất có thể. Trả "" khi không có gì cụ thể hơn — nhãn
 * chung theo vai nằm ở `const who` trong `03-hoi-thoai.js`, một bảng duy
 * nhất cho cả bốn vai. Nhân viên KHÔNG tên là thông tin vô dụng khi hai
 * người trực cùng ca. Trong nhóm: tên NGƯỜI GỬI tin, không phải tên nhóm. */
function tenTacGia(m, nguoiGuiNhom, tenKhach) {
  const tg = m.tac_gia || {};
  if (nguoiGuiNhom) return nguoiGuiNhom;
  if (m.role === "staff" && tg.ten) return `Nhân viên (${tg.ten})`;
  if (m.role === "customer" && tenKhach) return `Khách hàng (${tenKhach})`;
  return "";
}

/* Trạng thái lấy NGUYÊN từ `delivery_status` (dữ liệu nền tảng trả về) —
 * không suy đoán. Tin khách vào (`received`) không có trạng thái gửi. */
const TRANG_THAI_TIN = {
  sent: "Đã gửi", delivered: "Đã nhận", read: "Đã đọc",
  draft: "Bản nháp", queued: "Đang gửi", sending: "Đang gửi",
  failed: "Gửi lỗi, đang thử lại", dead: "Không gửi được", cancelled: "Đã huỷ",
};

function trangThaiTin(m) {
  if (m.role === "customer" || m.delivery_status === "received") return "";
  return TRANG_THAI_TIN[m.delivery_status] || "";
}

/* Ai đã sửa / duyệt — một dòng chữ nhỏ cạnh dòng meta, không phải chip to:
 * thông tin cần truy được, không cần đập vào mắt mỗi lần đọc hội thoại. */
function ghiChuNguoiXuLy(m) {
  const tg = m.tac_gia || {};
  const phan = [];
  if (tg.sua_boi) phan.push(`đã sửa bởi ${tg.sua_boi}`);
  else if (m.sua_boi) phan.push(`đã sửa bởi ${m.sua_boi}`);
  if (tg.duyet_boi) phan.push(`duyệt bởi ${tg.duyet_boi}`);
  return phan.length ? `<span class="msg__ghi">${esc(phan.join(" · "))}</span>` : "";
}

function nhanCanCu(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (cc && cc.nhan) return cc.nhan;
  if (m.grounded === true) return "Có căn cứ";
  if (m.grounded === false) return "Thiếu căn cứ";
  return "";
}

/* Năm trạng thái căn cứ (mục 16) do MÁY CHỦ phân loại từ kết quả tra cứu
 * thật của lượt — `agent/core/dau_vet_ai.py::phan_loai_can_cu`. Không phần
 * trăm. Tin cũ chưa có phân loại thì lui về Có/Thiếu căn cứ như trước. */
const TAG_CAN_CU = {
  du: "auto",
  chua_du: "assist",
  khong_co: "halt",
  mau_thuan: "halt",
  khong_can: "plain",
};

function tagCanCu(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (cc && cc.ma) return TAG_CAN_CU[cc.ma] || "plain";
  return m.grounded ? "auto" : "assist";
}

function veCanCuPhanLoai(m) {
  const cc = m.dau_vet_ai && m.dau_vet_ai.can_cu;
  if (!cc || !cc.ma || cc.ma === "du" || cc.ma === "khong_can") return "";
  const ds = (mang) => (mang || []).map((x) => `<li>${esc(x)}</li>`).join("");
  return `<div class="ctt__canh">
    ${cc.huong_dan ? `<p><b>${esc(cc.huong_dan)}</b></p>` : ""}
    ${(cc.mau_thuan || []).length ? `<ul class="ctt__ds">${ds(cc.mau_thuan)}</ul>` : ""}
    ${(cc.thieu || []).length ? `<ul class="ctt__ds">${ds(cc.thieu)}</ul>` : ""}
    ${cc.cau_cho ? `<p class="hint">Câu chờ trung lập (KHÔNG phải câu trả lời nghiệp vụ):</p>
      <blockquote class="ctt__trich">${esc(cc.cau_cho)}</blockquote>
      <button type="button" class="btn btn--sm" data-dung-cau-cho="${esc(cc.cau_cho)}">Dùng câu chờ</button>` : ""}
  </div>`;
}

/* "Dùng câu chờ": chỉ ĐIỀN vào ô soạn, không gửi — người trực vẫn là người bấm Gửi. */
document.addEventListener("click", (e) => {
  const nut = e.target.closest("[data-dung-cau-cho]");
  if (!nut) return;
  const o = $('#replyform [name="text"]');
  if (!o) return;
  // Bấm từ ngăn căn cứ đầy đủ thì đóng ngăn: nó che đúng ô soạn vừa điền.
  if (nut.closest(".ngan-phu")) dongNganPhu();
  o.value = nut.dataset.dungCauCho;
  o.focus();
});

/* "Xem căn cứ" trên BẢN NHÁP AI (chế độ gợi ý) — người duyệt cần nó để quyết
 * gửi hay sửa. Tin khác: "Chi tiết" (cùng bảng, kèm thông tin kỹ thuật). */
function nutChiTietTin(m, draft) {
  const coGi = m.role === "agent" || m.tac_gia?.sua_boi || m.tac_gia?.duyet_boi || m.sua_boi;
  if (!coGi) return "";
  const mo = state.chiTietTin && state.chiTietTin.has(String(m.id));
  const nhan = draft ? "Xem căn cứ" : "Chi tiết";
  const can = draft && nhanCanCu(m)
    ? `<span class="tag tag--${tagCanCu(m)}">${esc(nhanCanCu(m))}</span>` : "";
  return `${can}<button type="button" class="msg__goc-nut" data-chi-tiet-tin="${esc(m.id)}"
    aria-expanded="${mo ? "true" : "false"}">${mo ? "Ẩn" : nhan}</button>`;
}

function dongCT(tieu, chi) {
  return `<div class="ctt__dong"><b>${tieu}</b>${chi ? `<span>${chi}</span>` : ""}</div>`;
}

/* Nguồn tài liệu xếp theo điểm khớp, cao trước (UX-16-02). Dấu vết lưu theo
 * thứ tự các lần tra trong lượt — hai lần tra là hai cụm xen nhau, và tài
 * liệu khớp nhất có thể nằm cuối. Thiếu điểm thì xuống cuối; bằng điểm thì
 * giữ thứ tự gốc (sắp ổn định theo chỉ số). Điểm thô KHÔNG hiện cạnh tên —
 * chỉ trong phần Kỹ thuật (quy ước 21.11.2026). */
function sapXepNguon(ds) {
  const diem = (t) => {
    const d = t && t.diem != null && t.diem !== "" ? Number(t.diem) : NaN;
    return Number.isFinite(d) ? d : -Infinity;
  };
  return (ds || []).map((t, i) => ({ t, i }))
    .sort((a, b) => (diem(b.t) - diem(a.t)) || (a.i - b.i)).map((x) => x.t);
}

/* Đoạn trích: phần đầu hiện ngay, toàn văn gấp lại. Một đoạn 1.500 ký tự
 * bung sẵn là thứ đẩy câu trả lời đang cần duyệt ra khỏi màn hình. */
const TRICH_NGAN = 220;
function veTrich(s) {
  const chu = String(s || "").trim();
  if (!chu) return "";
  if (chu.length <= TRICH_NGAN) return `<blockquote class="ctt__trich">${esc(chu)}</blockquote>`;
  const cat = chu.slice(0, TRICH_NGAN);
  const dau = cat.slice(0, Math.max(cat.lastIndexOf(" "), TRICH_NGAN - 40)).trim();
  return `<blockquote class="ctt__trich">${esc(dau)}…</blockquote>
    <details class="ctt__toan"><summary>Xem toàn văn đoạn trích</summary>
      <blockquote class="ctt__trich">${esc(chu)}</blockquote></details>`;
}

/* Chi tiết NGAY TRONG luồng tin (UX-16-01): bản TÓM — căn cứ, tên vài tài
 * liệu, công cụ nào đã tra, lưới nào đã bắt, ai sửa/duyệt. Bản cũ bung cả
 * trích đoạn và JSON kết quả công cụ vào giữa hội thoại; một bản nháp có ba
 * tài liệu là ba màn hình cuộn chen giữa câu khách hỏi và câu trả lời cần
 * duyệt. Bản đầy đủ mở trong ngăn bên (`veCanCuDayDu`). */
function veChiTietTin(m, draft) {
  if (!(state.chiTietTin && state.chiTietTin.has(String(m.id)))) return "";
  const dv = m.dau_vet_ai || null;
  const tg = m.tac_gia || {};
  const nguoi = [
    tg.sua_boi ? dongCT("Sửa bởi", esc(tg.sua_boi + (tg.sua_luc ? " lúc " + gioTin(tg.sua_luc) : ""))) : "",
    tg.duyet_boi ? dongCT("Duyệt bởi", esc(tg.duyet_boi + (tg.duyet_luc ? " lúc " + gioTin(tg.duyet_luc) : ""))) : "",
  ].join("");
  if (m.role !== "agent") return nguoi ? `<div class="ctt ctt--gon">${nguoi}</div>` : "";
  const ten = dv && (dv.tri_thuc || []).length
    ? sapXepNguon(dv.tri_thuc).map((t) => t.title || "(không tên)") : (m.sources || []);
  const tomTL = ten.length
    ? esc(ten.slice(0, 2).join(" · ")) + (ten.length > 2 ? ` <span class="hint">và ${ten.length - 2} tài liệu khác</span>` : "")
    : "không trích tài liệu nào";
  const cc = dv ? [...new Set((dv.cong_cu || []).map((c) => c.ten))] : [];
  return `<div class="ctt ctt--gon">
    ${dongCT("Căn cứ", esc(nhanCanCu(m) || "—"))}
    ${veCanCuPhanLoai(m)}
    ${dongCT("Tài liệu", tomTL)}
    ${dongCT("Dữ liệu nghiệp vụ", cc.length ? esc(cc.join(" · ")) : "không tra")}
    ${dv && dv.luoi ? dongCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma)) : ""}
    ${dv && dv.chuyen_nguoi && dv.chuyen_nguoi.co ? dongCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : ""}
    ${nguoi}
    ${dv ? "" : '<p class="hint">Tin AI này soạn trước khi hệ thống lưu dấu vết — chỉ còn tên tài liệu.</p>'}
    <div class="ctt__nut">
      <button type="button" class="btn btn--sm" data-can-cu-day-du="${esc(m.id)}">Xem đầy đủ căn cứ</button>
      ${dv && dv.luot_id ? `<button type="button" class="btn btn--sm btn--ghost" data-xem-luot="${esc(dv.luot_id)}">Xem chi tiết lượt xử lý</button>` : ""}
    </div>
  </div>`;
}

/* Bảng căn cứ ĐẦY ĐỦ của một tin, trong ngăn bên. Ba phần căn cứ — tài liệu
 * (xếp theo mức khớp, trích đoạn gấp), dữ liệu nghiệp vụ công cụ trả về,
 * quy tắc và lớp lưới đã áp — rồi người xử lý và phần kỹ thuật. KHÔNG có
 * suy luận thô của model: hệ thống không lưu nó, và nó không phải căn cứ.
 * Tham số công cụ đã che số điện thoại/email và ẩn họ tên, địa chỉ ở máy
 * chủ (`agent/core/dau_vet_ai.py`). */
function veCanCuDayDu(m) {
  const dv = m.dau_vet_ai || null;
  const tg = m.tac_gia || {};
  const tl = sapXepNguon(dv ? dv.tri_thuc : []);
  const triThuc = tl.length
    ? tl.map((t, i) => `<li class="nguon">
        <div class="nguon__dau"><span class="nguon__hang" aria-label="Hạng ${i + 1}">${i + 1}</span>
          <b>${esc(t.title || "(không tên)")}</b>${
          t.version != null ? ` <span class="tag tag--plain">phiên bản ${esc(t.version)}</span>` : ""}</div>
        ${veTrich(t.trich)}</li>`).join("")
    : (m.sources || []).map((n) => `<li class="nguon"><b>${esc(n)}</b></li>`).join("");
  const congCu = dv && (dv.cong_cu || []).length
    ? dv.cong_cu.map((c) => `<li><details class="ctt__toan"><summary><b>${esc(c.ten)}</b></summary>
        <pre class="pre">${esc(JSON.stringify(c.ket_qua ?? null, null, 2))}</pre></details></li>`).join("")
      + (dv.cong_cu_bo_bot ? `<li class="hint">… và ${esc(dv.cong_cu_bo_bot)} lần gọi nữa không lưu chi tiết.</li>` : "")
    : "";
  const che = (dv && dv.che_do) || {};
  const quyTac = dv ? [
    dongCT("Hồ sơ agent", esc((dv.ho_so && dv.ho_so.ten) || "Mặc định")),
    dongCT("Chế độ", esc((che.chung === "auto" ? "AI tự gửi" : "AI soạn, người duyệt")
      + (che.duyet_rieng ? " · hội thoại này bắt duyệt trước khi gửi" : ""))),
    dv.luoi ? dongCT("Lớp lưới đã bắt", esc(dv.luoi.nhan || dv.luoi.ma)) : dongCT("Lớp lưới", "không lưới nào bắt"),
    dv.chuyen_nguoi && dv.chuyen_nguoi.co ? dongCT("Chuyển người", esc(dv.chuyen_nguoi.ly_do || "")) : "",
    (dv.goi_ky_nang || []).length ? dongCT("Gói kỹ năng", esc(dv.goi_ky_nang.join(" · "))) : "",
  ].join("") : '<p class="hint">Tin AI này soạn trước khi hệ thống lưu dấu vết — chỉ còn tên tài liệu.</p>';
  const tc = dv && dv.tin_cay;
  const diemTL = tl.filter((t) => t.diem != null)
    .map((t) => `${t.title || "(không tên)"} ${Number(t.diem).toFixed(2)}`).join(" · ");
  const kyThuat = [
    m.confidence != null ? dongCT("Điểm khớp tài liệu", esc(Number(m.confidence).toFixed(2)
      + (tc && tc.nguong != null ? ` (ngưỡng chuyển người ${Number(tc.nguong).toFixed(2)})` : ""))) : "",
    diemTL ? dongCT("Điểm khớp từng tài liệu", esc(diemTL)) : "",
    (dv && dv.model) || m.model ? dongCT("Model", esc((dv && dv.model) || m.model)) : "",
    m.latency_ms ? dongCT("Thời gian xử lý", esc(m.latency_ms + " ms")) : "",
    m.cost_usd != null || m.cost != null ? dongCT("Chi phí", esc(usd(m.cost_usd ?? m.cost))) : "",
  ].join("");
  const nguoi = [
    tg.sua_boi ? dongCT("Sửa bởi", esc(tg.sua_boi + (tg.sua_luc ? " lúc " + gioTin(tg.sua_luc) : ""))) : "",
    tg.duyet_boi ? dongCT("Duyệt bởi", esc(tg.duyet_boi + (tg.duyet_luc ? " lúc " + gioTin(tg.duyet_luc) : ""))) : "",
  ].join("");
  return `<div class="ctt ctt--day">
    ${dongCT("Căn cứ", esc(nhanCanCu(m) || "—"))}
    ${veCanCuPhanLoai(m)}
    <h4 class="ctt__dau">Tài liệu đã dùng <span class="hint">· xếp theo mức khớp, cao trước</span></h4>
    ${triThuc ? `<ol class="nguon-ds">${triThuc}</ol>` : '<p class="hint">Không trích tài liệu nào.</p>'}
    <h4 class="ctt__dau">Dữ liệu nghiệp vụ công cụ trả về</h4>
    ${congCu ? `<ul class="ctt__ds">${congCu}</ul>` : '<p class="hint">Không tra dữ liệu nghiệp vụ nào.</p>'}
    <h4 class="ctt__dau">Quy tắc đã áp</h4>${quyTac}
    ${nguoi ? `<h4 class="ctt__dau">Người xử lý</h4>${nguoi}` : ""}
    ${kyThuat ? `<details class="ctt__kt"><summary>Kỹ thuật</summary>${kyThuat}</details>` : ""}
  </div>`;
}

/* ---------------- Lịch sử xử lý (UX-18-04) ----------------
 * MỘT dòng thời gian trong panel "Chi tiết": bàn giao, sửa và duyệt bản
 * nháp, từ chối bản nháp, đề xuất của AI và quyết định của người. Trước đây
 * bốn thứ ấy nằm bốn nơi — lịch sử bàn giao trong panel, "đã sửa bởi" dưới
 * từng tin, thẻ đề xuất xen trong luồng, việc từ chối chỉ trong Nhật ký —
 * và câu "ai đã làm gì với hội thoại này" phải ghép tay.
 *
 * Hàm THUẦN để test chạy thật bằng node. Mới nhất ở trên, như bản cũ. */
function gopLichSuXuLy({ banGiao = [], tin = [], deXuat = [], suKien = [] } = {}) {
  const ds = [];
  const them = (x) => ds.push({ nguoi: "", chi_tiet: "", ...x });
  for (const b of banGiao) {
    them({ luc: b.luc, loai: b.loai || "ban_giao", tieu_de: b.tieu_de, nguoi: b.nguoi_lam || "",
           chi_tiet: b.chi_tiet || "", ket_thuc: b.ket_thuc || null });
  }
  // Ai từ chối và vì sao chỉ có trong nhật ký (tin chỉ đổi sang "cancelled").
  const tuChoi = new Map(suKien.filter((e) => e.kind === "ai.ban_nhap.tu_choi")
    .map((e) => [String((e.chi_tiet || {}).message_id || ""), e]));
  const ngan = (s) => { const t = String(s || "").trim(); return t.length > 120 ? t.slice(0, 120) + "…" : t; };
  for (const m of tin) {
    if (m.role !== "agent") continue;
    const tg = m.tac_gia || {};
    const sua = tg.sua_boi || m.sua_boi;
    if (sua) {
      them({ luc: tg.sua_luc || m.sua_luc || m.created_at, loai: "sua", tieu_de: "Sửa bản nháp AI",
             nguoi: sua, chi_tiet: ngan(m.content), tin_id: m.id });
    }
    if (tg.duyet_boi) {
      them({ luc: tg.duyet_luc || m.created_at, loai: "duyet",
             tieu_de: sua ? "Duyệt và gửi bản đã sửa" : "Duyệt và gửi bản nháp AI",
             nguoi: tg.duyet_boi, chi_tiet: sua ? "" : ngan(m.content), tin_id: m.id });
    }
    if (m.delivery_status === "cancelled") {
      const e = tuChoi.get(String(m.id));
      const lyDo = e && e.chi_tiet && e.chi_tiet.ly_do;
      // Chỉ nhận tên khi nhật ký xếp tác nhân là NHÂN VIÊN: bộ phân loại
      // của nhật ký xếp mọi kind "ai.*" là AI, kể cả việc người bấm Từ chối
      // — hiện "bởi AI" ở đây là nói sai người đã quyết.
      const tn = e && e.tac_nhan;
      them({ luc: e ? e.luc : m.created_at, loai: "tu_choi", tieu_de: "Từ chối bản nháp AI",
             nguoi: tn && tn.loai === "nhan_vien" ? (tn.ten || "") : "",
             chi_tiet: lyDo ? "Lý do: " + lyDo
               : (e ? ngan(m.content) : "Giờ ghi là lúc AI soạn — nhật ký chưa cho biết ai từ chối."),
             tin_id: m.id });
    }
  }
  for (const d of deXuat) {
    const ten = (d.de_xuat && d.de_xuat.tieu_de) || d.ten_hanh_dong || "hành động";
    them({ luc: d.tao_luc, loai: "de_xuat", tieu_de: `AI đề xuất: ${ten}`, nguoi: "AI",
           chi_tiet: [d.nhan_trang_thai, d.ly_do_can_duyet].filter(Boolean).join(" · ") });
    if (d.duyet_boi) {
      them({ luc: d.duyet_luc || d.tao_luc, loai: "de_xuat_duyet", tieu_de: `Phê duyệt đề xuất: ${ten}`,
             nguoi: d.duyet_boi });
    }
    if (d.tu_choi_boi) {
      them({ luc: d.tu_choi_luc || d.tao_luc, loai: "de_xuat_tu_choi", tieu_de: `Từ chối đề xuất: ${ten}`,
             nguoi: d.tu_choi_boi, chi_tiet: d.ly_do_tu_choi ? "Lý do: " + d.ly_do_tu_choi : "" });
    }
  }
  const ms = (x) => { const t = Date.parse(x.luc || ""); return Number.isNaN(t) ? 0 : t; };
  return ds.map((x, i) => ({ x, i })).sort((a, b) => (ms(b.x) - ms(a.x)) || (b.i - a.i)).map((o) => o.x);
}

function veLichSuXuLyHtml(bo, c) {
  if (!bo || bo.dangTai && !bo.items) return '<p class="hint">Đang tải…</p>';
  if (bo.loi) return `<p class="hint">Không tải được: ${esc(bo.loi)}</p>`;
  const dx = state.deXuatDangMo && state.deXuatDangMo.id === String(c.id) ? state.deXuatDangMo.ds : [];
  const ds = gopLichSuXuLy({ banGiao: bo.items || [], tin: c.messages || [], deXuat: dx, suKien: bo.suKien || [] });
  const canh = bo.loiSuKien ? `<p class="hint">Không đọc được nhật ký từ chối: ${esc(bo.loiSuKien)}</p>` : "";
  return canh + (ds.length ? ds.map((m) => `<div class="lichsu__dong lichsu__dong--${esc(m.loai)}">
      <b>${esc(m.tieu_de)}</b>
      <span class="msg__meta">${esc(gioTin(m.luc))}${m.nguoi ? " · bởi " + esc(m.nguoi) : ""}${
        m.ket_thuc ? " · kết thúc " + esc(gioTin(m.ket_thuc)) : ""}</span>
      ${m.chi_tiet ? `<p>${esc(m.chi_tiet)}</p>` : ""}
    </div>`).join("") : '<p class="hint">Chưa có bàn giao, duyệt hay đề xuất nào.</p>');
}

/* Khoá làm mới của lịch sử: version của hội thoại KHÔNG đổi khi từ chối hay
 * sửa bản nháp — chỉ theo version là dòng thời gian đứng yên sau đúng những
 * việc nó sinh ra để ghi. */
function khoaLichSu(c) {
  const tin = c.messages || [];
  return `${c.version}:${tin.length}:${tin.filter((m) => m.delivery_status === "cancelled").length}`;
}

function capNhatChiTietHoiThoai(drawerEl, c, laCuaToi) {
  if (!drawerEl || !c) return;
  const content = drawerEl.querySelector(".convo-drawer__content");
  if (!content) return;
  content.innerHTML = _noiDungChiTietHT(c, laCuaToi);
}

/* ---------------- Chi tiết hội thoại ----------------
 * Người đang giữ, nhóm, và lịch sử xử lý — trong MỘT panel mở bằng nút
 * "Chi tiết" ở đầu hội thoại. Tải lịch sử khi MỞ, tải lại khi khoá đổi;
 * không gọi mỗi 6 giây cho một panel không ai mở. */
function veChiTietHoiThoai(c, laCuaToi) {
  const id = String(c.id);
  if (state.moChiTietHT !== id) return "";
  const anim = state.vuaMoChiTietHT === id ? " is-animating" : "";
  return `<div class="convo-drawer-backdrop" id="convo-drawer-backdrop"></div>
  <aside class="convo-drawer is-open${anim}" id="convo-drawer" aria-label="Chi tiết hội thoại">
    <div class="convo-drawer__header">
      <div class="convo-drawer__header-left">
        <h3 class="convo-drawer__title">Chi tiết hội thoại</h3>
        <span class="convo-drawer__id">#${esc(c.id)}</span>
      </div>
      <button type="button" class="btn btn--sm btn--ghost convo-drawer__close" id="btn-dong-chitiet-ht"
        aria-label="Đóng chi tiết hội thoại" title="Đóng (Esc)">✕ Đóng</button>
    </div>
    <div class="convo-drawer__content">${_noiDungChiTietHT(c, laCuaToi)}</div>
  </aside>`;
}

/* Thân panel — MỘT hàm cho cả lần vẽ đầu lẫn lần cập nhật khi panel được
 * giữ qua vòng làm mới (bản trước chép hai lần, và hai bản đã bắt đầu lệch). */
function _noiDungChiTietHT(c, laCuaToi) {
  const id = String(c.id);
  const bo = state.lichSuPC && state.lichSuPC[id];
  if (!bo || bo.khoa !== khoaLichSu(c)) taiLichSuPhanCong(c);
  let giu;
  if (c.mode !== "human") giu = c.assigned_to_ten ? `AI đang xử lý · theo dõi: ${esc(c.assigned_to_ten)}` : "AI đang xử lý";
  else if (!c.assigned_to) giu = "Chưa ai nhận";
  else giu = `${esc(laCuaToi ? "Bạn" : (c.assigned_to_ten || "Đồng nghiệp"))}${
    c.assigned_team_ten ? " · nhóm " + esc(c.assigned_team_ten) : ""}`;
  /* Ưu tiên, chế độ AI, Version, trạng thái, kênh — dời từ thanh thông tin
   * xuống đây (mục 6.1, 6.2, 6.7, 6.8): cần khi tra cứu, không cần mỗi lần
   * đọc hội thoại. Hạn phản hồi KHÔNG có ở đây (mục 15.7) — cảnh báo đi qua
   * chuông. "Đổi" ưu tiên đòi `hoi_thoai.nhan` như máy chủ (uu_tien.py). */
  const doiUuTien = state.toiQuyen && state.toiQuyen.has("hoi_thoai.nhan") && c.state !== "resolved"
    ? ` <button type="button" class="btn btn--sm btn--ghost" data-doi-uu-tien="${esc(c.id)}"
        data-uu-tien="${esc(c.priority || "normal")}" data-version="${c.version || ""}">Đổi</button>` : "";
  const cheDo = { auto: "AI tự gửi", assist: "AI soạn, người duyệt", human: "Nhân viên xử lý" }[c.mode] || c.mode || "—";
  const dx = state.deXuatDangMo && state.deXuatDangMo.id === id ? state.deXuatDangMo.ds : [];
  const soMuc = bo && bo.items
    ? gopLichSuXuLy({ banGiao: bo.items, tin: c.messages || [], deXuat: dx, suKien: bo.suKien || [] }).length : 0;
  const moBanGiao = !!(state.moBanGiao && state.moBanGiao[id]);
  return `
      <!-- 1. Thông tin xử lý -->
      <section class="convo-drawer__sec">
        <h4 class="ctt__dau convo-drawer__sec-title">Thông tin xử lý</h4>
        ${dongCT("Người đang giữ", giu)}
        ${dongCT("Trạng thái", esc(c.state === "resolved" ? "Đã giải quyết" : (SIGNAL_LABEL[c.status] || c.status || "—")))}
        ${dongCT("Chế độ AI", esc(cheDo))}
        <div class="ctt__dong"><b>Ưu tiên</b><span>${esc(UU_TIEN_NHAN[c.priority] || c.priority || "thường")}</span>${doiUuTien}</div>
      </section>

      <!-- 2. Thông tin hội thoại -->
      <section class="convo-drawer__sec">
        <h4 class="ctt__dau convo-drawer__sec-title">Thông tin hội thoại</h4>
        ${dongCT("Kênh", `${esc(c.account_name || "—")} · ${esc(CHANNEL_LABEL[c.account_channel] || c.account_channel || "")}`)}
        ${dongCT("Thời gian tạo", esc(gioTin(c.created_at) || "—"))}
        ${dongCT("Cập nhật", esc(gioTin(c.updated_at) || "—"))}
        ${dongCT("Version", esc(c.version || 1))}
      </section>

      <!-- 3. Lịch sử xử lý (một dòng thời gian, thu gọn mặc định) -->
      <section class="convo-drawer__sec">
        <details class="convo-drawer__details" id="accordion-ban-giao" data-bg-id="${esc(id)}" ${moBanGiao ? "open" : ""}>
          <summary class="convo-drawer__summary">
            <span class="ctt__dau convo-drawer__sec-title" style="margin:0">Lịch sử xử lý</span>
            <span class="convo-drawer__count" id="convo-drawer-count">${soMuc} mục</span>
          </summary>
          <p class="hint lichsu__chu">Bàn giao, sửa · duyệt · từ chối bản nháp, đề xuất của AI — mới nhất ở trên.</p>
          <div class="lichsu__timeline" id="convo-drawer-timeline">
            ${veLichSuXuLyHtml(bo, c)}
          </div>
        </details>
      </section>

      <!-- 4. Nhật ký liên quan -->
      <section class="convo-drawer__sec convo-drawer__sec--nhatky">
        <h4 class="ctt__dau convo-drawer__sec-title" style="margin-bottom:6px">Nhật ký liên quan</h4>
        ${typeof veNhatKyHoiThoai === "function" ? veNhatKyHoiThoai(c) : ""}
      </section>`;
}

/* Bàn giao (`/lich-su-phan-cong`) và việc từ chối bản nháp (nhật ký của
 * hội thoại — chỉ cần `hoi_thoai.doc` trong kênh). Nhật ký hỏng thì dòng
 * thời gian VẪN hiện phần bàn giao, kèm một dòng nói phần nào thiếu. */
async function taiLichSuPhanCong(c) {
  const id = String(c.id);
  const khoa = khoaLichSu(c);
  state.lichSuPC = state.lichSuPC || {};
  if (state.lichSuPC[id] && state.lichSuPC[id].dangTai) return;
  state.lichSuPC[id] = { ...(state.lichSuPC[id] || {}), dangTai: true, khoa };
  let loiSuKien = "";
  try {
    const [r, nk] = await Promise.all([
      api(`/inbox/conversations/${id}/lich-su-phan-cong`),
      api(`/nhat-ky/hoi-thoai/${id}?limit=50`).catch((e) => { loiSuKien = e.message; return { items: [] }; }),
    ]);
    state.lichSuPC[id] = { items: r.items || [], suKien: nk.items || [], loiSuKien, khoa };
  } catch (e) {
    // Hỏng thì NÓI trong panel, không toast: vòng 6 giây sẽ bắn toast mãi.
    state.lichSuPC[id] = { loi: e.message, khoa };
  }
  const tl = $("#convo-drawer-timeline");
  const c2 = state.convDangMo && String(state.convDangMo.id) === id ? state.convDangMo : c;
  if (tl) {
    tl.innerHTML = veLichSuXuLyHtml(state.lichSuPC[id], c2);
    const cnt = $("#convo-drawer-count");
    if (cnt && state.lichSuPC[id].items) {
      const dx = state.deXuatDangMo && state.deXuatDangMo.id === id ? state.deXuatDangMo.ds : [];
      cnt.textContent = `${gopLichSuXuLy({ banGiao: state.lichSuPC[id].items, tin: c2.messages || [],
        deXuat: dx, suKien: state.lichSuPC[id].suKien || [] }).length} mục`;
    }
  } else if (state.openConv === id) {
    loadThread(id);
  }
}

/* "Giao cho…" — chọn người (và nhóm) trong danh sách máy chủ trả về, theo
 * ĐÚNG luật `can_assign`. Nhân viên thường không có quyền giao người khác
 * thì không thấy nút: một danh sách bấm vào chỉ nhận 403 là bẫy. */
async function giaoHoiThoai(c) {
  let ds;
  try {
    ds = await api(`/inbox/conversations/${c.id}/nguoi-nhan-duoc`);
  } catch (e) { toast(e.message, true); return; }
  if (!ds.co_the_giao_khac) {
    toast("Giao cho người khác cần quyền quản lý kênh. Bạn vẫn tự nhận được.", true);
    return;
  }
  const d = await hoiHop({
    tieu_de: "Giao hội thoại",
    phu: "Người nhận phải là thành viên kênh; chọn nhóm thì người nhận phải thuộc nhóm đó.",
    truong: [
      { name: "assignee_id", label: "Giao cho", type: "select", required: true,
        value: c.assigned_to || "",
        options: ds.nguoi.map((n) => ({ value: n.id,
          label: `${n.ten}${n.dang_giu ? ` (đang giữ ${n.dang_giu})` : ""}` })) },
      { name: "team_id", label: "Nhóm", type: "select", value: c.assigned_team_id || "",
        options: [{ value: "", label: "— Không theo nhóm —" },
          ...ds.nhom.map((t) => ({ value: t.id, label: t.ten }))] },
      { name: "reason", label: "Lý do", required: true, maxlength: 500,
        value: "Bàn giao cho người phụ trách" },
    ],
    nut: "Giao",
  });
  if (!d) return;
  try {
    await api(`/inbox/conversations/${c.id}/takeover`, {
      method: "POST",
      body: JSON.stringify({
        assignee_id: d.assignee_id, team_id: d.team_id || null,
        expected_version: c.version || 1, reason: d.reason,
      }),
    });
    const ten = (ds.nguoi.find((n) => String(n.id) === String(d.assignee_id)) || {}).ten;
    toast(`Đã giao cho ${ten || "người nhận"}.`);
    if (state.lichSuPC) delete state.lichSuPC[String(c.id)];
    refresh();
  } catch (e) { toast(e.message, true); }
}

function dongChiTietHT() {
  state.moChiTietHT = null;
  state.vuaMoChiTietHT = null;
  const d = $("#convo-drawer");
  const b = $("#convo-drawer-backdrop");
  if (d) d.remove();
  if (b) b.remove();
}

function moChiTietHT(id) {
  dongChiTietHT();
  state.moChiTietHT = id;
  state.vuaMoChiTietHT = id;
  const c = state.convDangMo;
  if (c && String(c.id) === id && $("#convdetail")) {
    const nguoiGiu = c.mode === "human" ? (c.assigned_to ? String(c.assigned_to) : "") : "";
    const laCuaToi = !!nguoiGiu && nguoiGiu === String(state.toiId || "");
    const html = veChiTietHoiThoai(c, laCuaToi);
    state.vuaMoChiTietHT = null;
    if (html) {
      const t = document.createElement("div");
      t.innerHTML = html;
      while (t.firstChild) {
        $("#convdetail").appendChild(t.firstChild);
      }
      const d = $("#convo-drawer");
      if (d) {
        d.addEventListener("animationend", () => d.classList.remove("is-animating"), { once: true });
      }
      return;
    }
  }
  loadThread(id);
}

document.addEventListener("click", (ev) => {
  const nut = ev.target.closest("[data-chi-tiet-tin]");
  if (nut) {
    state.chiTietTin = state.chiTietTin || new Set();
    const mid = nut.dataset.chiTietTin;
    if (state.chiTietTin.has(mid)) state.chiTietTin.delete(mid); else state.chiTietTin.add(mid);
    if (state.openConv) loadThread(state.openConv);
    return;
  }
  if (ev.target.closest("#btn-chitiet-ht") && state.openConv) {
    const id = String(state.openConv);
    if (state.moChiTietHT === id) {
      dongChiTietHT();
    } else {
      moChiTietHT(id);
    }
    return;
  }
  if (ev.target.closest("#btn-dong-chitiet-ht") || ev.target.closest("#convo-drawer-backdrop")) {
    dongChiTietHT();
    return;
  }
  if (ev.target.closest("#btn-giao") && state.convDangMo) {
    state.moHanhDong = null;   // nút nằm trong menu "⋯" — đóng nó lại
    giaoHoiThoai(state.convDangMo);
  }
});

document.addEventListener("toggle", (ev) => {
  const d = ev.target;
  if (!d || !d.dataset || !d.dataset.bgId) return;
  state.moBanGiao = state.moBanGiao || {};
  state.moBanGiao[d.dataset.bgId] = d.open;
}, true);

document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && state.moChiTietHT) {
    dongChiTietHT();
  }
});

/* ---------------- Bộ lọc hộp thư ----------------
 * Kênh, người giữ (tôi / chưa ai nhận / một người), riêng hay nhóm, quá hạn
 * SLA. API đã nhận kênh và người giữ từ lâu mà màn hình không dùng: người
 * trực muốn xem "việc của tôi" phải cuộn cả danh sách. */
state.convLoc = state.convLoc || { kenh: "", giu: "", loai: "", sla: false };

function chuoiLocHopThu() {
  const l = state.convLoc;
  let q = "";
  if (l.kenh) q += `&account_id=${encodeURIComponent(l.kenh)}`;
  if (l.giu === "chua_giao") q += "&chua_giao=true";
  else if (l.giu === "toi" && state.toiId) q += `&assignee_id=${encodeURIComponent(state.toiId)}`;
  else if (l.giu && l.giu !== "toi") q += `&assignee_id=${encodeURIComponent(l.giu)}`;
  if (l.loai) q += `&loai=${encodeURIComponent(l.loai)}`;
  if (l.sla) q += "&qua_han_sla=true";
  return q;
}

function dangLocHopThu() {
  const l = state.convLoc;
  return !!(l.kenh || l.giu || l.loai || l.sla);
}

/* Danh sách kênh và người cho hai ô chọn — nạp MỘT lần mỗi phiên trang.
 * Hỏng thì hai ô chỉ còn lựa chọn cố định; lần vào màn sau thử lại. */
async function napBoLocHopThu() {
  if (state.boLocDaNap || !$("#loc-kenh")) return;
  state.boLocDaNap = true;
  let d;
  try { d = await api("/inbox/bo-loc"); } catch (e) {
    state.boLocDaNap = false;
    console.warn("Không nạp được bộ lọc hộp thư", e);
    return;
  }
  $("#loc-kenh").innerHTML = '<option value="">Mọi kênh</option>' + (d.kenh || []).map((k) =>
    `<option value="${esc(k.id)}">${esc(k.ten)} · ${esc(CHANNEL_LABEL[k.channel] || k.channel)}</option>`).join("");
  $("#loc-giu").innerHTML = `<option value="">Mọi người giữ</option>
    <option value="toi">Của tôi</option><option value="chua_giao">Chưa ai nhận</option>`
    + (d.nguoi || []).filter((n) => String(n.id) !== String(state.toiId || "")).map((n) =>
      `<option value="${esc(n.id)}">${esc(n.ten)}</option>`).join("");
  $("#loc-kenh").value = state.convLoc.kenh;
  $("#loc-giu").value = state.convLoc.giu;
}

/* Gắn TỪNG ô bằng id viết đủ: `tests/test_nut_chet.py` tìm "#loc-…" trong
 * app.js để biết ô có người nghe — ghép chuỗi id là ô trông như nút chết. */
function ganLoc(o, khoa) {
  o?.addEventListener("change", (ev) => {
    state.convLoc[khoa] = ev.target.value;
    loadConversations();
  });
}
ganLoc($("#loc-kenh"), "kenh");
ganLoc($("#loc-giu"), "giu");
ganLoc($("#loc-loai"), "loai");

$("#loc-sla")?.addEventListener("click", (ev) => {
  state.convLoc.sla = !state.convLoc.sla;
  ev.currentTarget.classList.toggle("is-on", state.convLoc.sla);
  ev.currentTarget.setAttribute("aria-pressed", state.convLoc.sla ? "true" : "false");
  loadConversations();
});
