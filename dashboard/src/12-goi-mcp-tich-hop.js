/* ---------------- gói kỹ năng ---------------- */
async function loadGoiKyNang() {
  const d = await api("/goi-ky-nang");
  $("#goi-ds").innerHTML = d.goi.length ? d.goi.map((g) => `<div class="row">
      <span class="row__flag ${g.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(g.ten)} <b class="pill">v${esc(g.phien_ban)}</b>${g.bat ? "" : ' <b class="pill pill--halt">tắt</b>'}</span>
        <span class="row__sub">${esc(g.mo_ta)}</span>
        <span class="row__sub">${g.so_cong_cu} công cụ · ${g.so_tai_lieu} tài liệu · gọi 7 ngày: ${g.so_lan_7_ngay}${g.so_loi_7_ngay ? " (" + g.so_loi_7_ngay + " lỗi)" : ""} · từ khoá: ${esc((g.tu_khoa || []).join(", "))}</span>
        <span class="row__sub" data-goi-lichsu-o="${esc(g.ten)}"></span>
      </span>
      <span class="row__side">
        <button type="button" class="btn btn--sm" data-goi-battat="${esc(g.ten)}" data-bat="${g.bat ? "0" : "1"}">${g.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm" data-goi-xuat="${esc(g.ten)}">Xuất</button>
        <button type="button" class="btn btn--sm" data-goi-lichsu="${esc(g.ten)}">Lịch sử</button>
        <button type="button" class="btn btn--sm btn--halt" data-goi-xoa="${esc(g.ten)}">Xoá</button>
      </span>
    </div>`).join("") : `<p class="empty">Chưa có gói nào. Tối đa ${d.goi_toi_da}. Mẫu: data/goi-ky-nang/tu-van-da-nhay-cam.example.json</p>`;
}

function docFormGoi() {
  const f = $("#goiform");
  const tep = $("#goi-tep").files[0];
  const chu = f.querySelector("[name=json]").value.trim();
  return { tep, chu };
}

async function caiGoiKyNang(chiKiem) {
  const { tep, chu } = docFormGoi();
  const hop = $("#goi-ketqua");
  try {
    /* Ưu tiên rõ ràng: đã chọn tệp thì TỆP thắng ô dán. Bản trước, nút Kiểm
     * bỏ qua tệp và lặng lẽ kiểm nội dung còn sót trong ô dán — người dùng
     * thấy "Hợp lệ" cho một gói KHÁC gói họ vừa chọn, rồi bấm Cài. */
    if (tep && !chiKiem) {
      // Tệp đi bằng FormData như gửi tệp trong hộp thư — KHÔNG đặt Content-Type,
      // trình duyệt tự thêm boundary.
      const fd = new FormData(); fd.append("tep", tep);
      const res = await fetch("/api" + "/goi-ky-nang/tep", { method: "POST", body: fd, credentials: "same-origin" });
      const d = await res.json();
      if (!res.ok) throw new Error(typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail));
      hop.innerHTML = `<p class="empty">Đã cài ${esc(d.ten)} v${esc(d.phien_ban)}.</p>`;
      toast("Đã cài và bật gói");
      await loadKyNang();
      return;
    }
    let tho;
    if (tep) {
      /* Nút Kiểm không được ghi gì, nên nó đọc tệp NGAY TRONG TRÌNH DUYỆT và
       * gửi JSON tới /kiem — không có endpoint kiểm-từ-tệp ở máy chủ. Với
       * .zip thì phải giải nén, mà bộ giải nén (goi.tu_zip) chỉ nằm trên
       * đường Cài; nói thẳng ra thay vì im lặng kiểm nhầm ô dán. */
      if (/\.zip$/i.test(tep.name)) {
        toast("Kiểm chỉ nhận .json; tệp .zip bấm Cài (máy chủ kiểm trước khi ghi)", true);
        return;
      }
      try { tho = JSON.parse(await tep.text()); }
      catch (e) { toast("Tệp không phải JSON hợp lệ: " + e.message, true); return; }
    } else {
      if (!chu) { toast("Dán JSON của gói hoặc chọn tệp", true); return; }
      try { tho = JSON.parse(chu); } catch (e) { toast("JSON không hợp lệ: " + e.message, true); return; }
    }
    const d = await api(chiKiem ? "/goi-ky-nang/kiem" : "/goi-ky-nang", { method: "POST", body: JSON.stringify(tho) });
    if (chiKiem) {
      hop.innerHTML = d.hop_le
        ? `<p class="empty">Hợp lệ: ${esc(d.tom_tat.ten)} v${esc(d.tom_tat.phien_ban)} · ${d.tom_tat.so_cong_cu} công cụ · ${d.tom_tat.so_tai_lieu} tài liệu · từ khoá ${esc(d.tom_tat.tu_khoa.join(", "))}</p>`
        : `<p class="empty">Không hợp lệ: ${esc(d.loi)}</p>`;
      return;
    }
    hop.innerHTML = `<p class="empty">Đã cài ${esc(d.ten)} v${esc(d.phien_ban)}.</p>`;
    toast("Đã cài và bật gói");
    await loadKyNang();
  } catch (e) { toast(e.message, true); }
}

$("#goi-kiem")?.addEventListener("click", () => caiGoiKyNang(true));
$("#goi-cai")?.addEventListener("click", () => caiGoiKyNang(false));
document.addEventListener("click", async (e) => {
  const bt = e.target.closest("[data-goi-battat]");
  if (bt) {
    try { await api(`/goi-ky-nang/${encodeURIComponent(bt.dataset.goiBattat)}/bat-tat`, { method: "POST", body: JSON.stringify({ bat: bt.dataset.bat === "1" }) }); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-goi-xoa]");
  if (bx) {
    if (!confirm(`Xoá gói "${bx.dataset.goiXoa}"? Lịch sử phiên bản vẫn giữ.`)) return;
    try { await api(`/goi-ky-nang/${encodeURIComponent(bx.dataset.goiXoa)}`, { method: "DELETE" }); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
    return;
  }
  const bxu = e.target.closest("[data-goi-xuat]");
  if (bxu) { window.open(`/api/goi-ky-nang/${encodeURIComponent(bxu.dataset.goiXuat)}/xuat`, "_blank"); return; }
  const bl = e.target.closest("[data-goi-lichsu]");
  if (bl) {
    try {
      const ds = await api(`/goi-ky-nang/${encodeURIComponent(bl.dataset.goiLichsu)}/lich-su`);
      const o = document.querySelector(`[data-goi-lichsu-o="${CSS.escape(bl.dataset.goiLichsu)}"]`);
      o.innerHTML = ds.length ? ds.map((h) => `v${esc(h.phien_ban)} (${esc(h.thay_boi)}) <button type="button" class="btn btn--sm" data-goi-khoiphuc="${esc(bl.dataset.goiLichsu)}" data-id="${h.id}">Khôi phục</button>`).join(" · ") : "Chưa có bản cũ.";
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bk = e.target.closest("[data-goi-khoiphuc]");
  if (bk) {
    try { await api(`/goi-ky-nang/${encodeURIComponent(bk.dataset.goiKhoiphuc)}/khoi-phuc/${encodeURIComponent(bkp.dataset.id)}`, { method: "POST" }); toast("Đã khôi phục"); await loadKyNang(); }
    catch (err) { toast(err.message, true); }
  }
});

/* ---------------- máy chủ MCP ---------------- */

// Hai huy hiệu dùng chung cho cả bảng máy chủ và ô Kiểm — một chỗ đổi màu,
// không phải sửa ở hai nơi mỗi khi luật ĐỌC/GHI đổi.
const MCP_PILL_DOC = '<b class="pill">ĐỌC</b>';
const MCP_PILL_GHI = '<b class="pill pill--halt">GHI</b>';

function moTaCat120(s) {
  const t = String(s || "");
  return t.length > 120 ? t.slice(0, 120) + "…" : t;
}

async function loadMcp() {
  const d = await api("/mcp");
  $("#mcp-ds").innerHTML = d.may_chu.length ? d.may_chu.map((m) => {
    const sk = m.suc_khoe || {};
    const dongBo = sk.ok === true
      ? '<b class="pill">đồng bộ ok</b>'
      : sk.ok === false
      ? `<b class="pill pill--halt">lỗi đồng bộ${sk.loi ? ": " + esc(sk.loi) : ""}</b>`
      : "";
    const luc = sk.luc ? ` · lúc ${clock(sk.luc)}` : "";
    const bo = (sk.bo || []).length
      ? `<span class="row__sub row__sub--truot">Công cụ bị bỏ: ${
          sk.bo.map((b) => `${esc(b.ten)} (${esc(b.ly_do)})`).join(" · ")
        }</span>`
      : "";
    // Hàng máy chủ + hàng công cụ đi PHẲNG trong cùng một `#mcp-ds`, không
    // lồng `<div>` bên trong `<span class="row__body">` — lồng khối vào
    // trong phần tử dòng là HTML sai kiểu, trình duyệt tự "sửa" bằng cách
    // đẩy nó ra ngoài luồng .row, và lưới `.row { grid-template-columns }`
    // vỡ bố cục ngay từ hàng công cụ đầu tiên. Mỗi hàng công cụ tự nêu tên
    // máy chủ để không cần khối bao ngoài mà vẫn biết nó thuộc máy nào.
    const congCu = (m.cong_cu || []).map((c) => {
      const badge = c.ghi ? MCP_PILL_GHI : MCP_PILL_DOC;
      const goi7 = c.so_lan_7_ngay != null
        ? ` · gọi 7 ngày: ${c.so_lan_7_ngay}${c.so_loi_7_ngay ? " (" + c.so_loi_7_ngay + " lỗi)" : ""}`
        : "";
      const choPhepGhi = c.ghi ? `
          <label class="hint"><input type="checkbox" data-mcp-ghi
            data-may-chu="${esc(m.ten)}" data-ten="${esc(c.ten)}"
            ${c.ghi_cho_phep ? "checked" : ""}> cho phép ghi ngoài phòng thử</label>
          <span class="row__sub row__sub--truot">Bật rồi công cụ này SỬA được dữ liệu thật, không chỉ đọc.</span>`
        : "";
      return `<div class="row">
        <span class="row__flag ${c.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
        <span class="row__body">
          <span class="row__title">${esc(m.nhan)} · ${esc(c.ten)} ${badge}</span>
          <span class="row__sub">${esc(moTaCat120(c.mo_ta))}${goi7}</span>
          ${choPhepGhi}
        </span>
        <span class="row__side">
          <label class="hint"><input type="checkbox" data-mcp-cc
            data-may-chu="${esc(m.ten)}" data-ten="${esc(c.ten)}"
            ${c.bat ? "checked" : ""}> bật</label>
        </span>
      </div>`;
    }).join("");
    return `<div class="row">
      <span class="row__flag ${m.bat ? "row__flag--auto" : "row__flag--halt"}"></span>
      <span class="row__body">
        <span class="row__title">${esc(m.nhan)}${m.bat ? "" : ' <b class="pill pill--halt">tắt</b>'} ${dongBo}</span>
        <span class="row__sub">${esc(m.host)} · ${m.so_bat || 0}/${m.so_cong_cu || 0} công cụ bật${luc}</span>
        ${bo}
      </span>
      <span class="row__side">
        <button type="button" class="btn btn--sm" data-mcp-dongbo="${esc(m.ten)}">Đồng bộ</button>
        <button type="button" class="btn btn--sm ${m.bat ? "btn--halt" : ""}"
          data-mcp-battat="${esc(m.ten)}" data-bat="${m.bat ? "0" : "1"}">${m.bat ? "Tắt" : "Bật"}</button>
        <button type="button" class="btn btn--sm btn--halt" data-mcp-xoa="${esc(m.ten)}">Xoá</button>
      </span>
    </div>${congCu}`;
  }).join("") : `<p class="empty">Chưa có máy chủ MCP nào. Tối đa ${d.may_chu_toi_da}.</p>`;
}

// Đọc form Nối máy chủ MCP. Trả về `null` (và tự toast lỗi) khi một dòng
// header không có dấu ":" — không ném exception ở đây vì lỗi này KHÔNG
// phải lỗi máy chủ, hỏi lại người gõ trước khi tốn một lượt gọi API.
function docFormMcp() {
  const f = $("#mcpform");
  const fd = new FormData(f);
  const ten = String(fd.get("ten") || "").trim();
  const nhan = String(fd.get("nhan") || "").trim();
  const dia_chi = String(fd.get("dia_chi") || "").trim();
  const headers = {};
  for (const dong_tho of String(fd.get("headers") || "").split("\n")) {
    const dong = dong_tho.trim();
    if (!dong) continue;
    const i = dong.indexOf(":");
    if (i < 0) {
      toast(`Dòng header không có dấu ":": "${dong}"`, true);
      return null;
    }
    headers[dong.slice(0, i).trim()] = dong.slice(i + 1).trim();
  }
  return { ten, nhan, dia_chi, headers: Object.keys(headers).length ? headers : null };
}

async function kiemMcp() {
  const dl = docFormMcp();
  if (!dl) return;
  if (!dl.dia_chi) { toast("Điền địa chỉ trước khi Kiểm", true); return; }
  const hop = $("#mcp-ketqua");
  try {
    const d = await api("/mcp/kiem", {
      method: "POST", body: JSON.stringify({ dia_chi: dl.dia_chi, headers: dl.headers }),
    });
    if (!d.ok) { hop.innerHTML = `<p class="empty">Không nối được: ${esc(d.loi)}</p>`; return; }
    hop.innerHTML = (d.cong_cu || []).map((c) => c.ly_do_bo
      ? `<div class="row"><span class="row__flag row__flag--halt"></span>
          <span class="row__body"><span class="row__title">${esc(c.ten)}</span>
          <span class="row__sub row__sub--truot">Bị bỏ: ${esc(c.ly_do_bo)}</span></span></div>`
      : `<div class="row"><span class="row__flag row__flag--auto"></span>
          <span class="row__body"><span class="row__title">${esc(c.ten)} ${c.ghi_goi_y ? MCP_PILL_GHI : MCP_PILL_DOC}</span>
          <span class="row__sub">${esc(moTaCat120(c.mo_ta))}</span></span></div>`
    ).join("") || '<p class="empty">Máy chủ không có công cụ nào.</p>';
  } catch (e) { toast(e.message, true); }
}

async function themMcp() {
  const dl = docFormMcp();
  if (!dl) return;
  if (!dl.ten || !dl.nhan || !dl.dia_chi) { toast("Điền đủ tên, nhãn và địa chỉ", true); return; }
  try {
    const d = await api("/mcp", {
      method: "POST",
      body: JSON.stringify({ ten: dl.ten, nhan: dl.nhan, dia_chi: dl.dia_chi, headers: dl.headers }),
    });
    /* 201 KHÔNG có nghĩa là đã nối được. Máy chủ vẫn được tạo khi lần đồng
     * bộ đầu hỏng — cố ý, để một lần mạng chập không làm mất bản ghi và bí
     * mật vừa mã hoá. Nhưng báo "Đã nối" cho một máy chủ chưa hề nối được
     * là người vận hành bỏ đi làm việc khác, còn agent thì thiếu công cụ:
     * sai địa chỉ, sai header và DNS hỏng đều trông y hệt một máy chủ thật
     * không có công cụ nào. Nói ra, kèm việc phải làm tiếp. */
    if (!d.ok) {
      $("#mcp-ketqua").innerHTML = `<p class="empty">Đã tạo "${esc(d.ten)}" nhưng chưa nối được: ${
        esc(d.loi || "không rõ lý do")} — sửa địa chỉ/header rồi bấm Đồng bộ.</p>`;
      toast(`Đã tạo "${d.ten}" nhưng chưa nối được máy chủ MCP`, true);
    } else {
      $("#mcp-ketqua").innerHTML = `<p class="empty">Đã nối "${esc(d.ten)}": ${d.so_bat}/${d.so_cong_cu} công cụ bật${
        d.so_bo ? ", " + d.so_bo + " bị bỏ" : ""}.</p>`;
      toast(`Đã nối máy chủ MCP "${d.ten}"`);
    }
    $("#mcpform").reset();
    mcpTenGoTay = false;
    await loadKyNang();
  } catch (e) { toast(e.message, true); }
}

/* Gợi ý ô Tên từ ô Nhãn (spec §5.5). Dùng lại `sinhMaPlugin` — cùng một
 * phép bỏ dấu, cùng một luật "luôn ra mã hợp lệ" — rồi cắt về 20 ký tự cho
 * khớp `_TEN_MAY_CHU_RE` ở máy chủ, vốn chặt hơn tên plugin (40).
 *
 * VÌ SAO PHẢI CÓ. Ô Tên đòi chữ thường không dấu, còn người vận hành nghĩ
 * bằng tiếng Việt có dấu; không gợi ý thì lỗi "tên không hợp lệ" xuất hiện
 * sau khi đã gõ xong cả form, ở đúng ô mà máy tự điền được. */
function sinhMaMcp(nhan) {
  return sinhMaPlugin(nhan).slice(0, 20).replace(/_+$/g, "");
}

/* Người đã tự gõ vào ô Tên thì THÔI gợi ý — đè lên chữ người đang gõ là
 * kiểu hỏng khó chịu nhất của mọi ô tự điền. Cờ được đặt lại khi form reset
 * (xem `themMcp`), vì form trống là một lần nhập mới. */
let mcpTenGoTay = false;

$("#mcpform")?.addEventListener("input", (e) => {
  const f = $("#mcpform");
  if (e.target === f.elements.ten) {
    mcpTenGoTay = String(f.elements.ten.value).trim() !== "";
    return;
  }
  if (e.target === f.elements.nhan && !mcpTenGoTay) {
    f.elements.ten.value = sinhMaMcp(f.elements.nhan.value);
  }
});

$("#mcp-kiem")?.addEventListener("click", kiemMcp);
$("#mcp-them")?.addEventListener("click", themMcp);

document.addEventListener("click", async (e) => {
  const bd = e.target.closest("[data-mcp-dongbo]");
  if (bd) {
    try {
      await api(`/mcp/${encodeURIComponent(bd.dataset.mcpDongbo)}/dong-bo`, { method: "POST" });
      toast("Đã đồng bộ với máy chủ MCP.");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bt = e.target.closest("[data-mcp-battat]");
  if (bt) {
    try {
      await api(`/mcp/${encodeURIComponent(bt.dataset.mcpBattat)}/bat-tat`, {
        method: "POST", body: JSON.stringify({ bat: bt.dataset.bat === "1" }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
    return;
  }
  const bx = e.target.closest("[data-mcp-xoa]");
  if (bx) {
    if (!confirm(`Xoá hẳn máy chủ MCP "${bx.dataset.mcpXoa}"? Mọi công cụ của nó cũng mất theo.`)) return;
    try {
      await api(`/mcp/${encodeURIComponent(bx.dataset.mcpXoa)}`, { method: "DELETE" });
      toast("Đã xoá máy chủ MCP.");
      await loadKyNang();
    } catch (err) { toast(err.message, true); }
  }
});

document.addEventListener("change", async (e) => {
  const cc = e.target.closest("[data-mcp-cc]");
  if (cc) {
    try {
      await api(`/mcp/${encodeURIComponent(cc.dataset.mayChu)}/cong-cu/${encodeURIComponent(cc.dataset.ten)}`, {
        method: "POST", body: JSON.stringify({ bat: cc.checked }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); cc.checked = !cc.checked; }
    return;
  }
  const gh = e.target.closest("[data-mcp-ghi]");
  if (gh) {
    try {
      await api(`/mcp/${encodeURIComponent(gh.dataset.mayChu)}/cong-cu/${encodeURIComponent(gh.dataset.ten)}`, {
        method: "POST", body: JSON.stringify({ ghi_cho_phep: gh.checked }),
      });
      await loadKyNang();
    } catch (err) { toast(err.message, true); gh.checked = !gh.checked; }
  }
});

/* ---------------- ứng dụng nhúng (tích hợp) ---------------- */

async function loadTichHop() {
  const d = await api("/tich-hop/ung-dung");
  const ve = (a) => `<div class="row">
      <span class="row__flag ${a.xoa_duoc ? "row__flag--auto" : ""}"></span>
      <span class="row__body">
        <span class="row__title">${esc(a.nhan)}
          ${a.xoa_duoc ? "" : '<b class="pill">viết sẵn</b>'}</span>
        <span class="row__sub">${esc(a.dia_chi)}</span>
      </span>
      <span class="row__side">
        <a class="btn btn--sm" href="/tich-hop/${encodeURIComponent(a.ten)}/"
           target="_blank" rel="noopener">Mở</a>
        ${a.xoa_duoc
          ? `<button type="button" class="btn btn--sm btn--halt"
               data-tichhop-xoa="${esc(a.ten)}">Xoá</button>`
          : ""}
      </span>
    </div>`;
  $("#tichhop-ds").innerHTML =
    d.mac_dinh.map(ve).join("") + d.tu_them.map(ve).join("");
}

/* Đọc form một chỗ duy nhất, dùng chung cho "Thử" và "Lưu".
 * Hai đường đọc form theo hai cách là thử một thứ rồi lưu một thứ khác, và
 * người vận hành không có cách nào biết. */
function docFormTichHop() {
  const f = $("#tichhopform");
  const g = (n) => (f.elements[n]?.value || "").trim();
  return { ten: g("ten"), nhan: g("nhan") || g("ten"), dia_chi: g("dia_chi") };
}

$("#tichhop-thu")?.addEventListener("click", async () => {
  const hop = $("#tichhop-ketqua");
  try {
    const r = await api("/tich-hop/ung-dung/thu", {
      method: "POST",
      body: JSON.stringify(docFormTichHop()),
    });
    hop.innerHTML = r.noi_duoc
      ? `<p class="empty">Nối được ${esc(r.dia_chi)} — HTTP ${r.ma}.</p>`
      : `<p class="empty">Không nối được ${esc(r.dia_chi)}: ${esc(r.ly_do)}</p>`;
  } catch (e) {
    hop.innerHTML = `<p class="empty">${esc(e.message)}</p>`;
    toast(e.message, true);
  }
});

$("#tichhopform")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/tich-hop/ung-dung", {
      method: "POST",
      body: JSON.stringify(docFormTichHop()),
    });
    e.target.reset();
    $("#tichhop-ketqua").innerHTML = "";
    toast("Đã thêm ứng dụng nhúng");
    await loadTichHop();
  } catch (err) {
    toast(err.message, true);
  }
});

document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-tichhop-xoa]");
  if (!b) return;
  if (!confirm(`Gỡ ứng dụng "${b.dataset.tichhopXoa}" khỏi dashboard?`)) return;
  try {
    await api("/tich-hop/ung-dung/" + encodeURIComponent(b.dataset.tichhopXoa),
              { method: "DELETE" });
    toast("Đã gỡ");
    await loadTichHop();
  } catch (err) { toast(err.message, true); }
});

