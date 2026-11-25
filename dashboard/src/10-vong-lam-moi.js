/* ---------------- vòng làm mới ---------------- */

async function dongBoQuyen() {
  try {
    const nguoi = await api("/toi");
    const moi = new Set(nguoi.quyen || []);
    const cu = state.toiQuyen;
    const khac = !cu || cu.size !== moi.size || [...moi].some((q) => !cu.has(q));
    if (khac) {
      state.toiId = nguoi.id;
      state.toiQuyen = moi;
      if (!coQuyen("hoi_thoai.doc") && state.stream) {
        state.stream.close();
        state.stream = null;
      } else if (coQuyen("hoi_thoai.doc") && !state.stream) {
        startInboxStream();
      }
      apDungQuyenMenu();
    }
  } catch { /* bỏ qua khi mất mạng tạm thời; api() đã tự xử lý 401 */ }
}

async function refresh() {
  // Chuông chạy RIÊNG, không await: nó tự nuốt lỗi của mình, và một màn
  // hỏng ở dưới không được làm chuông đứng (19-thong-bao.js).
  taiSoThongBao();
  try {
    await dongBoQuyen();
    if (coQuyen("hoi_thoai.doc")) await loadOverview();
    // Mô-đun đăng ký SAU lần đầu tab hiện vẫn được gắn ở nhịp kế tiếp.
    ganTabDangHien();
    if (state.view === "hoithoai") await loadConversations();
    if (state.view === "khachhang") { await loadTruongKhach(); await loadContacts(); }
    if (state.view === "donhang") await loadOrders();
    if (state.view === "kho") await loadKho();
    if (state.view === "sohieu") {    // nhãn hiển thị: "Phân tích"
      if (!state.ptDaTai) await loadPhanTich();
      await loadCost();
    }
    /* Màn có tab: nạp THEO TAB đang hiện, không theo màn — mỗi màn cài đặt
       gộp ba bốn màn cũ, nạp cả màn là kéo dữ liệu cho ba tab không ai nhìn.
       `dangMo(id)` = tab đang hiện VÀ chưa bị mô-đun gắn vào thay thế;
       `tabDangHien(id)` cho các khối luôn ở lại dù có mô-đun gắn vào.
       Tab gộp nhiều nguồn thì mỗi nguồn kèm `coQuyen`: thiếu một quyền mà
       vẫn gọi là một 403 chặn mọi loader phía sau, mỗi 6 giây. */
    if (dangMo("cv-ca-truc")) { await loadTinChet(); await loadVoChu(); await loadCaCuaToi(); await loadTongQuanCa(); }
    if (dangMo("cv-danh-sach")) await loadCongViec();
    if (tabDangHien("cc-nhan")) await loadTruongKhach();
    if (dangMo("cc-tu-dong")) { await loadMauNhanh(); await loadQuyTac(); }
    if (tabDangHien("cc-ket-noi") && coQuyen("kenh.doc")) {
      if (coQuyen("agent.doc")) await loadHoSoAgent();
      await loadSucKhoeKenh(); await loadKetNoi();
    }
    if (dangMo("cc-ket-noi")) {
      await loadCaiDatApi();
      if (coQuyen("don.doc")) await loadErpCauHinh();
      if (coQuyen("tich_hop.doc")) await loadTichHop();
    }
    if (dangMo("cc-sla")) { await loadDinhTuyen(); await loadCaiDatApi(); }
    if (dangMo("cc-dieu-phoi")) await loadDinhTuyen();
    if (tabDangHien("ai-co-ban")) {
      if (coQuyen("cau_hinh.doc")) await loadCauHinh();
      if (coQuyen("agent.doc")) await loadHoSoAgent();
    }
    if (tabDangHien("ai-co-ban") && !daGan("ai-co-ban-nha-cung-cap")) await loadCaiDatApi();
    if (dangMo("ai-tri-thuc")) await loadDocs();
    if (dangMo("ai-ky-nang")) await loadKyNang();
    if (dangMo("ai-phong-thu") && !state.phongThuDaTai) await loadPhongThu();
    if (dangMo("ns-nhan-vien") || dangMo("ns-vai-tro")) await loadNhanSu();
    if (tabDangHien("ns-lich-ca")) await loadLichCa();
    if (tabDangHien("ns-vai-tro")) await loadTamNhin();
    if (dangMo("ht-suc-khoe")) await loadHeThong();
    if (dangMo("ht-sao-luu")) {
      await loadYeuCauChuThe();
      if (coQuyen("khach.pii")) { await loadPdpdPolicy(); await loadRetention(); }
      await loadCaiDatApi();
    }
    if (dangMo("ht-nhat-ky")) await loadEvents();
  } catch (e) {
    toast("Không nối được máy chủ: " + e.message, true);
  }
}

function startInboxStream() {
  if (!("EventSource" in window) || !coQuyen("hoi_thoai.doc") || state.stream) return;
  const stream = new EventSource("/api/inbox/events");
  state.stream = stream;      // để api() đóng được khi phiên hết
  const schedule = () => {
    clearTimeout(inboxRefreshTimer);
    inboxRefreshTimer = setTimeout(async () => {
      taiSoThongBao();
      try {
        if (coQuyen("hoi_thoai.doc")) await loadOverview();
        if (state.view === "hoithoai") await loadConversations();
        if (state.view === "khachhang") await loadContacts();
      } catch { /* EventSource tự nối lại; polling 6 giây vẫn là fallback. */ }
    }, 120);
  };
  /* Mọi sự kiện SLA máy chủ phát (agent/omnichannel/sla.py) phải có ở đây:
     thiếu `sla.resolution_breached` là hội thoại trễ hạn giải quyết chỉ hiện
     ra ở nhịp 6 giây sau — hoặc không bao giờ, khi tab đang ở màn khác. */
  ["message.created", "message.sent", "conversation.updated", "conversation.takeover",
    "conversation.released", "conversation.priority_changed",
    "sla.first_response_warning", "sla.first_response_breached",
    "sla.resolution_warning", "sla.resolution_breached",
    "sla.handover_response_warning", "sla.handover_response_breached"]
    .forEach((topic) => stream.addEventListener(topic, schedule));
  /* Màn Phân tích không theo nhịp 6 giây; sự kiện SLA mới thì đánh dấu để
     lần tới mở màn (hoặc đang mở) tính lại. */
  ["sla.first_response_breached", "sla.resolution_breached",
    "sla.first_response_warning", "sla.resolution_warning",
    "sla.handover_response_warning", "sla.handover_response_breached"]
    .forEach((topic) => stream.addEventListener(topic, () => {
      state.ptDaTai = false;
    }));
  window.addEventListener("beforeunload", () => stream.close(), { once: true });
}

// Chỉ bắt đầu vòng làm mới SAU KHI xác nhận có phiên. Gọi refresh() ngay
// khi chưa đăng nhập thì mọi request trả 401 và người dùng thấy một loạt
// thông báo lỗi trước cả khi kịp nhìn thấy ô đăng nhập.
kiemPhien().then((co) => {
  if (!co) return;
  // Một chỗ quyết định mục nào hiện (01b-dieu-huong.js QUYEN_MAN / QUYEN_TAB).
  apDungQuyenMenu();
  refresh();
  startInboxStream();
  state.timer = setInterval(refresh, 6000);
});

/* Trung tâm kết nối native. Secret chỉ đi từ form tới vault; response không
   chứa credential nên DOM cũng không có gì để vô tình làm lộ. */
function moManKetNoi() {
  doiMan("cc-ket-noi");
}

/*
 * Địa chỉ CÔNG KHAI của hệ thống, do máy chủ báo qua overview.
 *
 * Trình duyệt chỉ biết `location.origin` — tức `http://127.0.0.1:8000` khi
 * người vận hành mở dashboard tại chỗ. Meta và Zalo KHÔNG BAO GIỜ gọi vào
 * được địa chỉ đó, nhưng copy nó dán vào Meta thì lỗi báo về chỉ nói "không
 * xác minh được URL" — không nói vì sao.
 *
 * Chưa dựng tunnel thì máy chủ vẫn trả localhost, và lúc đó hiện
 * `location.origin` cũng đúng — nên đường lui giữ nguyên hành vi cũ.
 */
let PUBLIC_BASE = "";

function goc_cong_khai() {
  return (PUBLIC_BASE || location.origin).replace(/\/+$/, "");
}

/* Danh sách tài khoản kênh (loadKetNoi và các hằng của nó) đã tách sang
 * 18a-ket-noi-tai-khoan.js: tệp này quá 1000 dòng, và màn Kết nối là một
 * miền màn hình riêng. */

/*
 * Quét QR Zalo cá nhân.
 *
 * VÌ SAO PHẢI HỎI LẠI, KHÔNG DÙNG NGAY PHẢN HỒI CỦA /qr
 * ------------------------------------------------------
 * Sidecar trả lời `login-qr` NGAY khi nhận việc, còn ảnh QR thì tới sau —
 * nó đến qua callback của thư viện Zalo vài trăm mili giây sau đó. Nên lúc
 * `/qr` trả về, `qr_image` luôn null.
 *
 * Bản trước đọc đúng phản hồi ấy rồi hiện toast "chờ sidecar cập nhật trạng
 * thái" và dừng lại. Người dùng nhìn một dòng chữ, không có gì để quét, và
 * không có gì gợi ý bước tiếp theo — nút bấm xong coi như hỏng.
 *
 * Ảnh nằm ở `/status`. Hỏi lại theo nhịp cho tới khi có ảnh, rồi tiếp tục
 * hỏi cho tới khi phiên `connected` để đóng khung lại đúng lúc.
 */
const QR_NHIP_MS = 2000;
const QR_TOI_DA_LUOT = 60;          // ~2 phút, dài hơn hạn sống của một mã QR

async function quetQR(accountId) {
  const khung = $("#qrbox");
  if (khung) khung.remove();
  document.body.insertAdjacentHTML("beforeend", `
    <div class="qrbox" id="qrbox">
      <div class="qrbox__panel">
        <h3>Quét bằng ứng dụng Zalo</h3>
        <div id="qrslot"><p class="empty">Đang xin mã từ sidecar…</p></div>
        <p class="qrbox__hint">Mở Zalo trên điện thoại → Thêm → Quét mã QR</p>
        <button type="button" class="btn" id="qrclose">Đóng</button>
      </div>
    </div>`);
  const dong = () => { const b = $("#qrbox"); if (b) b.remove(); loadKetNoi(); };
  $("#qrclose").addEventListener("click", dong);

  const slot = () => $("#qrslot");
  try {
    await api(`/channel-accounts/${accountId}/zalo-personal/qr`, { method: "POST" });
  } catch (e) {
    if (slot()) slot().innerHTML = `<p class="empty">Không xin được mã: ${esc(e.message)}</p>`;
    return;
  }

  let daHienAnh = false;
  for (let luot = 0; luot < QR_TOI_DA_LUOT; luot += 1) {
    if (!$("#qrbox")) return;                 // người dùng đã đóng khung
    await new Promise((r) => setTimeout(r, QR_NHIP_MS));
    let st;
    try { st = await api(`/channel-accounts/${accountId}/zalo-personal/status`); }
    catch (e) { continue; }                   // sidecar bận, thử lại nhịp sau

    if (st.qr_image && !daHienAnh) {
      daHienAnh = true;
      // Sidecar trả ảnh dạng base64 thuần hoặc đã có tiền tố data:.
      const src = String(st.qr_image).startsWith("data:")
        ? st.qr_image : `data:image/png;base64,${st.qr_image}`;
      if (slot()) slot().innerHTML = `<img alt="Mã QR đăng nhập Zalo" src="${esc(src)}">`;
    }
    if (st.status === "qr_scanned" && slot()) {
      slot().innerHTML = '<p class="empty">Đã quét. Đang xác nhận trên điện thoại…</p>';
    }
    if (st.status === "connected") {
      toast("Đã kết nối Zalo cá nhân. Phiên được lưu mã hoá trong vault.");
      dong();
      return;
    }
    if (st.status === "qr_expired") {
      if (slot()) slot().innerHTML = '<p class="empty">Mã QR hết hạn. Đóng rồi bấm Quét QR lại.</p>';
      return;
    }
  }
  if (slot()) slot().innerHTML = '<p class="empty">Hết thời gian chờ. Đóng rồi thử lại.</p>';
}

/*
 * Kết nối tài khoản kênh — mỗi kênh một bộ trường riêng.
 *
 * VÌ SAO KHÔNG DÙNG CHUNG MỘT FORM CHO SÁU KÊNH
 * ----------------------------------------------
 * Bản đầu hiện đủ sáu ô cho mọi kênh, với nhãn gộp kiểu "Refresh token /
 * sidecar secret / widget secret". Người vận hành phải tự đoán ô nào dành
 * cho kênh mình, và bốn ô để trống mà không có gì nói ra điều đó.
 *
 * Nối tài khoản là việc làm MỘT LẦN cho mỗi kênh, với những chuỗi dài
 * giống hệt nhau. Sai ở đây không nổ: credential vẫn được mã hoá, tài
 * khoản vẫn hiện trên dashboard, chỉ có tin khách là không bao giờ tới —
 * và có thể nhiều ngày sau mới ai đó nhận ra.
 *
 * Ba lớp chặn ba kiểu sai khác nhau:
 *   1. chỉ hiện ô kênh đó cần   -> không dán nhầm ô
 *   2. nhãn + chỉ dẫn lấy ở đâu -> không dán nhầm giá trị
 *   3. cắt khoảng trắng thừa    -> không hỏng vì một dấu cách vô hình
 *
 * Lớp 3 nghe vặt nhưng là lỗi kinh điển: copy từ trang web thường dính
 * khoảng trắng cuối, sai một byte là HMAC hỏng, và thông báo lỗi của
 * provider không bao giờ nói "bạn thừa một dấu cách".
 */
const KENH_TRUONG = {
  zalo_personal: {
    // KHÔNG hỏi gì cả — chỉ cần đặt tên rồi quét QR.
    //
    // Trước đây ô này bắt người dùng "mở file .env copy dòng
    // ZALO_SIDECAR_SECRET". Nhưng đó là bí mật của MÁY CHỦ: mọi tài khoản
    // Zalo dùng chung một giá trị, và người dùng không có `.env` để mở.
    // Máy chủ tự điền — xem agent/omnichannel/bi_mat_may_chu.py
    truong: [],
    ke_tiep: 'Lưu xong, bấm "Quét QR" trên thẻ tài khoản rồi quét bằng app Zalo.',
  },
  zalo_oa: {
    truong: [
      {
        o: "external_account_id", nhan: "OA ID", bat_buoc: true,
        goi_y: "Zalo OA Console → Thông tin OA → OA ID"
      },
      {
        o: "app_id", nhan: "App ID", bat_buoc: true,
        goi_y: "Zalo Developers → Ứng dụng của bạn → App ID"
      },
      {
        o: "app_secret", nhan: "Secret key", bat_buoc: true,
        goi_y: "Zalo Developers → Ứng dụng → Secret Key"
      },
      {
        o: "secondary_secret", nhan: "Refresh token", bat_buoc: true,
        goi_y: "Zalo OA Console → sau khi cấp quyền cho ứng dụng, lấy Refresh Token"
      },
    ],
    ke_tiep: "Cần URL HTTPS công khai để Zalo gọi webhook vào.",
  },
  facebook: {
    dang_nhap: true,
    truong: [
      {
        o: "external_account_id", nhan: "Page ID", bat_buoc: true,
        goi_y: "Meta Business → Trang của bạn → Giới thiệu → ID trang"
      },
      {
        o: "access_token", nhan: "Page access token", bat_buoc: true,
        goi_y: "Meta App Dashboard → Messenger → Settings → Generate Token cho đúng Trang"
      },
      {
        o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret"
      },
      {
        o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT. Phải dán đúng chuỗi này vào Meta khi đăng ký webhook"
      },
    ],
    ke_tiep: "Cần URL HTTPS công khai, rồi đăng ký webhook trong Meta App Dashboard.",
  },
  instagram: {
    dang_nhap: true,
    truong: [
      {
        o: "external_account_id", nhan: "Instagram business ID", bat_buoc: true,
        goi_y: "Meta App Dashboard → Instagram → Instagram Business Account ID"
      },
      {
        o: "access_token", nhan: "Access token", bat_buoc: true,
        goi_y: "Cùng token với Trang Facebook đã liên kết Instagram"
      },
      {
        o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret"
      },
      {
        o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT, dùng chung với webhook Meta"
      },
    ],
    ke_tiep: "Instagram phải là tài khoản Business và đã liên kết một Trang Facebook.",
  },
  whatsapp: {
    truong: [
      {
        o: "external_account_id", nhan: "Phone number ID", bat_buoc: true,
        goi_y: "Meta App Dashboard → WhatsApp → API Setup → Phone number ID (KHÔNG phải số điện thoại)"
      },
      {
        o: "access_token", nhan: "Access token", bat_buoc: true,
        goi_y: "Meta App Dashboard → WhatsApp → API Setup → Temporary/Permanent token"
      },
      {
        o: "app_secret", nhan: "App secret", bat_buoc: true,
        goi_y: "Meta App Dashboard → Settings → Basic → App Secret"
      },
      {
        o: "verify_token", nhan: "Verify token", bat_buoc: true,
        goi_y: "Chuỗi bạn TỰ ĐẶT, dùng chung với webhook Meta"
      },
    ],
    ke_tiep: "Cần URL HTTPS công khai để Meta gọi webhook vào.",
  },
  webchat: {
    truong: [
      {
        o: "external_account_id", nhan: "Khoá website", bat_buoc: true,
        goi_y: "Tên ngắn không dấu để phân biệt từng website, ví dụ: web-chinh"
      },
      {
        o: "secondary_secret", nhan: "Widget secret", bat_buoc: true,
        goi_y: "Bạn tự đặt — chuỗi ngẫu nhiên từ 32 ký tự. Dùng để ký phiên của widget"
      },
    ],
    ke_tiep: "Chạy được ngay, không cần HTTPS công khai khi thử tại chỗ.",
  },
};

const O_CREDENTIAL = [
  "external_account_id", "app_id", "access_token",
  "app_secret", "verify_token", "secondary_secret",
];

function veFormKenh(kenh) {
  const cau_hinh = KENH_TRUONG[kenh];
  if (!cau_hinh) return;
  const theo_o = new Map(cau_hinh.truong.map((t) => [t.o, t]));

  for (const ten of O_CREDENTIAL) {
    const input = document.querySelector(`#connectionform [name="${ten}"]`);
    if (!input) continue;
    const khung = input.closest(".field");
    const dung = theo_o.get(ten);

    khung.classList.toggle("is-hidden", !dung);
    input.required = Boolean(dung && dung.bat_buoc);
    if (!dung) { input.value = ""; continue; }

    khung.querySelector("span").textContent =
      dung.nhan + (dung.bat_buoc ? "" : " (không bắt buộc)");

    // Chỉ dẫn lấy giá trị ở đâu. Không có nó thì người vận hành rời
    // dashboard đi tìm, quay lại dán nhầm ô — hoặc bỏ dở giữa chừng.
    let goi_y = khung.querySelector(".field__goiy");
    if (!goi_y) {
      goi_y = document.createElement("small");
      goi_y.className = "field__goiy";
      khung.appendChild(goi_y);
    }
    goi_y.textContent = dung.goi_y;
  }

  /* Kênh nối được bằng đăng nhập thì ĐỪNG đòi dán token.
   *
   * Màn hình cũ có nút "Kết nối bằng đăng nhập" ở trên và ngay dưới là bốn ô
   * token bắt buộc cho đúng kênh đó — hai thứ nói ngược nhau, và người dùng
   * làm theo cái dễ đọc hơn là form trước mắt.
   *
   * Đi đường dán tay không chỉ mất thời gian: token dán tay KHÔNG tự gia
   * hạn, nên vài tuần sau kênh chết câm mà không ai biết cho tới khi khách
   * kêu. Và `app_secret` phải đi qua trình duyệt, trong khi đường đăng nhập
   * giữ nó ở máy chủ suốt.
   *
   * Không xoá hẳn ô nhập tay: vẫn có ca cần khi app Meta chưa được duyệt,
   * hoặc khi gỡ lỗi. Nó thành đường phụ, đóng sẵn.
   */
  const khoi_tay = $("#nhap-tay");
  const nhac = $("#khuyen-dang-nhap");
  if (khoi_tay && nhac) {
    if (cau_hinh.dang_nhap) {
      khoi_tay.open = false;
      khoi_tay.querySelector("summary").textContent =
        "Nhập thủ công (nâng cao — chỉ khi không dùng được đăng nhập)";
      nhac.textContent = "Kênh này nối bằng nút \"Kết nối Facebook / Instagram "
        + "bằng đăng nhập\" ở trên: chọn Trang, hệ thống tự nhận token và tự "
        + "gia hạn. Chỉ mở phần nhập thủ công khi bạn có lý do riêng.";
      nhac.classList.remove("is-hidden");
    } else {
      khoi_tay.open = true;
      khoi_tay.querySelector("summary").textContent = "Thông tin kết nối";
      nhac.classList.add("is-hidden");
    }
  }

  /* Ô `required` nằm trong `<details>` đang ĐÓNG thì trình duyệt chặn gửi
   * form mà không hiện được lỗi ở đâu — người dùng bấm Lưu và không có gì
   * xảy ra. Kênh có đường đăng nhập thì bỏ `required` hết; phần kiểm thiếu
   * trường vẫn chạy ở `luuKetNoi`, nơi báo được bằng toast. */
  if (cau_hinh.dang_nhap) {
    for (const ten of O_CREDENTIAL) {
      const input = document.querySelector(`#connectionform [name="${ten}"]`);
      if (input) input.required = false;
    }
  }

  const chan = $("#connection-ketiep");
  if (chan) chan.textContent = cau_hinh.ke_tiep || "";
}

$('#connectionform [name="channel"]')?.addEventListener("change", (ev) =>
  veFormKenh(ev.target.value)
);
if ($("#connectionform")) veFormKenh($('#connectionform [name="channel"]').value);

$("#connectionform")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const tho = Object.fromEntries(new FormData(ev.target));
  // Cắt khoảng trắng cho MỌI giá trị, không riêng token: tên hiển thị dính
  // dấu cách đầu dòng cũng làm danh sách tài khoản trông lệch.
  const form = {};
  for (const [k, v] of Object.entries(tho)) form[k] = String(v ?? "").trim();

  const cau_hinh = KENH_TRUONG[form.channel];
  const thieu = (cau_hinh?.truong || [])
    .filter((t) => t.bat_buoc && !form[t.o])
    .map((t) => t.nhan);
  if (thieu.length) {
    /* Kênh có đường đăng nhập mà người dùng bấm Lưu với ô trống thì gần như
     * chắc chắn họ đang ở nhầm chỗ. Liệt kê bốn token còn thiếu là đẩy họ đi
     * tìm những chuỗi mà hệ thống tự lấy được. */
    toast(cau_hinh?.dang_nhap
      ? 'Kênh này nối bằng nút "Kết nối Facebook / Instagram bằng đăng nhập" ở trên.'
      : "Còn thiếu: " + thieu.join(", "), true);
    return;
  }

  if (form.channel === "webchat") {
    /* Kênh web cần ĐỊA CHỈ WEBSITE được phép mở khung chat; form này không
     * có ô ấy, và kênh lưu thiếu nó bị máy chủ từ chối mọi phiên (403) —
     * khung chat hiện ra mà khách gõ gì cũng không vào (đo 19.11.2026). */
    toast('Kênh website nối bằng nút "Chat trên website" ở mục Nối kênh mới.', true);
    return;
  }

  const credentials = {};
  for (const key of ["app_id", "access_token", "verify_token"]) {
    if (form[key]) credentials[key] = form[key];
  }
  if (form.app_secret) {
    if (form.channel === "zalo_oa") credentials.secret_key = form.app_secret;
    else credentials.app_secret = form.app_secret;
  }
  if (form.secondary_secret) {
    if (form.channel === "zalo_oa") credentials.refresh_token = form.secondary_secret;
    else if (form.channel === "webchat") credentials.widget_secret = form.secondary_secret;
  }

  let account;
  try {
    account = await api("/channel-accounts", {
      method: "POST", body: JSON.stringify({
        channel: form.channel, display_name: form.display_name,
        external_account_id: form.external_account_id || null,
        capabilities: { send_text: true, receive_message: true }, metadata: {}, credentials,
      })
    });
  } catch (e) { toast(e.message, true); return; }

  ev.target.reset();
  veFormKenh($('#connectionform [name="channel"]').value);
  $("#connection-create").classList.add("is-hidden");

  // XÁC MINH NGAY, không đợi người bấm nút riêng.
  //
  // Lưu xong mà không kiểm thì người dùng tưởng đã xong. Credential sai chỉ
  // lộ ra khi khách nhắn mà không ai nhận — có thể nhiều ngày sau, và lúc
  // đó không ai còn nhớ mình đã dán gì vào đâu.
  //
  // Zalo cá nhân là ngoại lệ: nó chưa có gì để xác minh cho tới khi quét QR.
  if (form.channel === "zalo_personal") {
    toast('Đã lưu. Bấm "Quét QR" trên thẻ tài khoản để đăng nhập Zalo.');
    loadKetNoi();
    return;
  }
  try {
    /* `/verify` trả 200 kèm `{ok:false}` khi provider từ chối — không ném
     * lỗi. Không đọc `ok` thì credential sai được báo XANH "xác minh xong":
     * xanh giả, lộ ra nhiều ngày sau khi khách nhắn mà không ai nhận. Cùng
     * cách đọc với nút "Xác minh provider" trên thẻ tài khoản. */
    const kq = await api(`/channel-accounts/${account.id}/verify`, { method: "POST" });
    toast(kq && kq.ok ? "Đã lưu và xác minh xong với provider."
      : `Đã lưu, nhưng chưa xác minh được: ${lyDoKetNoi(kq || {})} — kiểm lại credential.`,
      !(kq && kq.ok));
  } catch (e) {
    toast("Đã lưu, nhưng provider từ chối: " + e.message + " — kiểm lại credential.", true);
  }
  loadKetNoi();
});


/*
 * Kết nối Facebook/Instagram bằng ĐĂNG NHẬP.
 *
 * Mở cửa sổ mới thay vì chuyển hướng cả trang: người dùng đang ở giữa việc
 * cấu hình, và kéo họ ra khỏi dashboard rồi thả về là mất ngữ cảnh. Cửa sổ
 * con tự đóng và tự làm mới trang cha khi xong.
 */
$("#btn-oauth-meta")?.addEventListener("click", async () => {
  const nut = $("#btn-oauth-meta");
  nut.disabled = true;
  try {
    const r = await api("/connect/meta/start");
    if (!r.url) throw new Error("Máy chủ không trả về địa chỉ đăng nhập");
    // Mở TRƯỚC khi await gì thêm: trình duyệt chỉ cho mở cửa sổ mới trong
    // nhịp xử lý cú bấm, chờ lâu là bị chặn pop-up.
    const cua_so = window.open(r.url, "ketnoi_meta", "width=620,height=740");
    if (!cua_so) {
      toast("Trình duyệt đã chặn cửa sổ. Cho phép pop-up rồi thử lại.", true);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    nut.disabled = false;
  }
});

/*
 * Kết nối Zalo OA bằng CẤP QUYỀN. Cùng khuôn với Meta ở trên.
 *
 * Khác một chỗ đáng nói: cửa sổ con KHÔNG tự đóng khi xong, vì nó còn hiện
 * địa chỉ webhook người dùng phải dán sang Zalo Developers — Zalo không có
 * API đăng ký webhook. Đóng hộ họ là lấy mất thứ duy nhất làm chiều nhận
 * tin chạy được.
 */
$("#btn-oauth-zalo-oa")?.addEventListener("click", async () => {
  const nut = $("#btn-oauth-zalo-oa");
  nut.disabled = true;
  try {
    const r = await api("/connect/zalo-oa/start");
    if (!r.url) throw new Error("Máy chủ không trả về địa chỉ cấp quyền");
    const cua_so = window.open(r.url, "ketnoi_zalo_oa", "width=620,height=760");
    if (!cua_so) {
      toast("Trình duyệt đã chặn cửa sổ. Cho phép pop-up rồi thử lại.", true);
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    nut.disabled = false;
  }
});
