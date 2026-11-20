function providerMessageId(result) {
  return String(
    result?.message?.msgId
      ?? result?.attachment?.[0]?.msgId
      ?? result?.msgId
      ?? '',
  );
}

// Loại tệp theo `msgType` của zca-js 2.x.
//
// VÌ SAO PHẢI ĐỌC THEO msgType: zca-js KHÔNG đưa ảnh/tệp vào một mảng
// `attachments`. Ảnh, tệp, video, ghi âm đến dưới dạng `content` là MỘT
// object `TAttachmentContent { title, description, href, thumb, params }`,
// và chỉ `msgType` nói nó là gì. Bản trước chỉ đọc `content.attachments` —
// thứ không bao giờ có — nên MỌI ảnh khách gửi qua Zalo cá nhân rơi mất:
// ảnh không kèm chữ thành tin rỗng, phía Python bỏ qua im lặng. Đo trên CSDL
// thật: 80 tin Zalo cá nhân, 0 tin có tệp. Đúng lỗi số 1 trong lịch sử repo
// ("bộ đọc webhook bỏ tin chỉ có ảnh"), quay lại qua một cửa khác.
const LOAI_THEO_MSG_TYPE = {
  'chat.photo': 'image',
  'chat.gif': 'gif',
  'chat.video.msg': 'video',
  'chat.voice': 'audio',
  'share.file': 'file',
};

// Loại tin mà `title` là TÊN TỆP chứ không phải lời khách. Đưa tên tệp vào
// `text` thì agent trả lời "Bao_gia_T11.pdf" như thể khách vừa hỏi câu ấy.
const TITLE_LA_TEN_TEP = new Set(['share.file']);

function docParams(raw) {
  if (raw && typeof raw === 'object') return raw;
  if (typeof raw !== 'string' || !raw) return {};
  try {
    const v = JSON.parse(raw);
    return v && typeof v === 'object' ? v : {};
  } catch {
    return {};
  }
}

function tepTuNoiDung(msgType, content) {
  // `content` dạng TAttachmentContent: href là bản gốc, thumb là ảnh nhỏ.
  // Ảnh thì lấy href (đủ nét cho agent nhìn); thiếu href mới lùi về thumb.
  const loai = LOAI_THEO_MSG_TYPE[msgType];
  if (!loai || !content || typeof content !== 'object') return null;
  const url = String(content.href || content.thumb || '');
  if (!url) return null;
  const params = docParams(content.params);
  const tep = { type: loai, url };
  if (content.thumb) tep.thumb = String(content.thumb);
  if (TITLE_LA_TEN_TEP.has(msgType) && content.title) tep.name = String(content.title);
  const kichThuoc = Number(params.fileSize ?? params.size);
  if (Number.isFinite(kichThuoc) && kichThuoc > 0) tep.size = kichThuoc;
  if (params.fileExt) tep.ext = String(params.fileExt);
  return tep;
}

// Loại thread của zca-js (`ThreadType`): 0 nhắn riêng, 1 nhóm.
export const THREAD_NHOM = 1;

// Bộ đệm tên nhóm.
//
// VÌ SAO CẦN TÊN NHÓM: tin nhóm của zca-js chỉ mang `uidFrom`/`dName` của
// NGƯỜI GỬI, không mang tên nhóm. Bản trước đẩy đúng hai trường ấy lên, nên
// hội thoại nhóm trên dashboard mang tên người nói sau cùng — và phía Python
// gắn cả nhóm vào hồ sơ riêng của người đó (trí nhớ riêng của họ lọt vào
// câu trả lời trong nhóm).
//
// VÌ SAO ĐỆM: `getGroupInfo` là một lượt gọi mạng tới Zalo. Nhóm sôi nổi có
// hàng trăm tin một giờ; hỏi mỗi tin là tự chuốc bị Zalo chặn. Tên nhóm hiếm
// khi đổi — đổi thì trễ nửa giờ mới thấy là chấp nhận được.
//
// Hỏng thì đệm NGẮN: để lần sau thử lại sớm, nhưng không hỏi lại ở từng tin
// của cùng một đợt hỏng.
export const TEN_NHOM_SONG_MS = 30 * 60 * 1000;
export const TEN_NHOM_LOI_MS = 2 * 60 * 1000;
// Tin khách không được chờ Zalo trả tên nhóm mãi: quá hạn thì đi tiếp với
// tên rỗng (Python tự đặt tên dự phòng).
export const TEN_NHOM_CHO_MS = 5000;
const TEN_NHOM_TOI_DA = 2000;

function coHan(promise, ms) {
  let hen;
  const het = new Promise((_, reject) => {
    hen = setTimeout(() => reject(new Error(`quá ${ms}ms`)), ms);
  });
  return Promise.race([promise, het]).finally(() => clearTimeout(hen));
}

export function normalizeMessage(raw) {
  const data = raw?.data ?? raw ?? {};
  const content = data.content ?? {};
  const msgType = String(data.msgType ?? '');
  const attachments = [];
  // Dạng mảng `attachments` (bản cũ / nguồn khác) — giữ để không hồi quy.
  const ds = (content && typeof content === 'object' ? content.attachments : undefined)
    ?? data.attachments ?? [];
  for (const item of Array.isArray(ds) ? ds : []) {
    const url = String(item?.href ?? item?.url ?? item?.thumbUrl ?? '');
    if (url) attachments.push({ type: item?.type ?? 'file', url });
  }
  const tep = attachments.length ? null : tepTuNoiDung(msgType, content);
  if (tep) attachments.push(tep);

  let text;
  if (typeof content === 'string') {
    text = content;
  } else if (TITLE_LA_TEN_TEP.has(msgType)) {
    text = '';
  } else if (msgType === 'chat.recommended' || msgType === 'chat.link') {
    // Khách dán đường dẫn (thường là link sản phẩm): chữ là tiêu đề + URL,
    // để agent và nhân viên đều thấy khách đang nói về trang nào.
    text = [content?.title, content?.href].filter(Boolean).join(' ');
  } else {
    text = String(content?.title ?? content?.msg ?? data?.msg ?? '');
  }
  const threadType = Number(raw?.type ?? data.type ?? 0);
  return {
    msg_id: String(data.msgId ?? data.msg_id ?? data.cliMsgId ?? ''),
    thread_id: String(raw?.threadId ?? data.threadId ?? ''),
    thread_type: threadType,
    // Khai TƯỜNG MINH là nhóm, không bắt phía Python tự hiểu con số 1:
    // nhầm nhóm thành nhắn riêng là AI nói chen vào nhóm của khách.
    is_group: threadType === THREAD_NHOM,
    // Điền sau, trong listener — cần gọi API Zalo (xem `layTenNhom`).
    group_name: '',
    // Với tin nhóm, hai trường dưới là NGƯỜI GỬI trong nhóm, không phải
    // danh tính của hội thoại.
    sender_id: String(data.uidFrom ?? data.senderId ?? ''),
    sender_name: String(data.dName ?? data.senderName ?? ''),
    // Gửi kèm để phía Python ghi được VÌ SAO một tin bị bỏ (sticker, loại
    // lạ…) thay vì bỏ im lặng.
    msg_type: msgType,
    text: String(text ?? ''),
    timestamp: Number(data.ts ?? data.timestamp ?? Date.now()),
    attachments,
  };
}

export class SessionManager {
  constructor({ zaloFactory, onEvent = async () => {}, log = console, now = () => Date.now() }) {
    this.zaloFactory = zaloFactory;
    this.onEvent = onEvent;
    this.log = log;
    this.now = now;
    this.sessions = new Map();
    this.epochs = new Map();
    this.tenNhom = new Map();
  }

  /**
   * Tên nhóm Zalo, có đệm. KHÔNG BAO GIỜ ném và không bao giờ làm rơi tin:
   * hỏng thì trả tên cũ đã biết, hoặc chuỗi rỗng — phía Python đặt tên dự
   * phòng "Nhóm Zalo …" và tin vẫn vào hộp thư. Mất tên nhóm là chuyện hiển
   * thị; mất tin khách là chuyện không ai biết.
   */
  async layTenNhom(accountId, api, groupId) {
    const khoa = `${accountId}:${groupId}`;
    const co = this.tenNhom.get(khoa);
    if (co && co.hetHan > this.now()) return co.ten;
    // Nhiều tin cùng nhóm tới dồn dập: chung một lượt hỏi, không mỗi tin một.
    if (co?.dangHoi) return co.dangHoi;
    const hoi = (async () => {
      let ten = '';
      let song = TEN_NHOM_LOI_MS;
      try {
        if (typeof api?.getGroupInfo !== 'function') {
          throw new Error('phiên Zalo không có getGroupInfo');
        }
        const kq = await coHan(api.getGroupInfo(String(groupId)), TEN_NHOM_CHO_MS);
        ten = String(kq?.gridInfoMap?.[groupId]?.name ?? '').trim();
        if (ten) song = TEN_NHOM_SONG_MS;
        else this.log.warn?.(`[sidecar] getGroupInfo không trả tên nhóm ${groupId} (${accountId})`);
      } catch (loi) {
        this.log.warn?.(`[sidecar] không lấy được tên nhóm ${groupId} (${accountId}): ${loi?.message ?? loi}`);
      }
      // Lần này hỏng mà lần trước đã biết tên: tên cũ đúng hơn tên dự phòng.
      if (!ten && co?.ten) ten = co.ten;
      if (this.tenNhom.size > TEN_NHOM_TOI_DA) this.tenNhom.clear();
      this.tenNhom.set(khoa, { ten, hetHan: this.now() + song });
      return ten;
    })();
    this.tenNhom.set(khoa, { ten: co?.ten ?? '', hetHan: 0, dangHoi: hoi });
    return hoi;
  }

  teardown(accountId) {
    const current = this.sessions.get(accountId);
    try { current?.api?.listener?.stop?.(); } catch { /* best effort */ }
    this.sessions.delete(accountId);
  }

  status(accountId) {
    const current = this.sessions.get(accountId);
    if (!current) return { status: 'disconnected' };
    return {
      status: current.status,
      qr_image: current.qrImage ?? null,
      own_id: current.ownId ?? null,
      last_activity: current.lastActivity?.toISOString?.() ?? null,
    };
  }

  async startQr(accountId) {
    this.teardown(accountId);
    const epoch = (this.epochs.get(accountId) ?? 0) + 1;
    this.epochs.set(accountId, epoch);
    const zalo = this.zaloFactory();
    const state = { zalo, api: null, status: 'qr_pending', epoch, qrExpired: 0 };
    this.sessions.set(accountId, state);

    state.loginPromise = zalo.loginQR({}, async (event) => {
      if (this.sessions.get(accountId)?.epoch !== epoch) return;
      if (event.type === 0) {
        state.qrImage = event.data?.image ?? null;
      } else if (event.type === 1) {
        state.qrExpired += 1;
        if (state.qrExpired < 3) event.actions?.retry?.();
        else {
          state.status = 'qr_expired';
          try { state.api?.listener?.stop?.(); } catch { /* best effort */ }
        }
      } else if (event.type === 2) {
        state.status = 'qr_scanned';
      } else if (event.type === 4) {
        await this.onEvent(accountId, 'session', {
          cookie: event.data?.cookie,
          imei: event.data?.imei,
          userAgent: event.data?.userAgent,
        });
      }
    }).then((api) => this.attach(accountId, epoch, api))
      .catch(async (error) => {
        // Lỗi trong chính nhánh bắt lỗi cũng là unhandled rejection — bắt nốt.
        try {
          if (this.sessions.get(accountId)?.epoch === epoch) {
            state.status = 'disconnected';
            await this.onEvent(accountId, 'health', { status: 'disconnected' });
          }
        } catch (loi) {
          this.log.error?.(`[sidecar] báo hỏng đăng nhập QR hỏng (${accountId}): ${loi?.stack ?? loi}`);
        }
        return error;
      });
    return this.status(accountId);
  }

  async restore(accountId, credentials) {
    this.teardown(accountId);
    const epoch = (this.epochs.get(accountId) ?? 0) + 1;
    this.epochs.set(accountId, epoch);
    const zalo = this.zaloFactory();
    const state = { zalo, api: null, status: 'connecting', epoch };
    this.sessions.set(accountId, state);
    const api = await zalo.login(credentials);
    return this.attach(accountId, epoch, api);
  }

  async attach(accountId, epoch, api) {
    const state = this.sessions.get(accountId);
    if (!state || state.epoch !== epoch) {
      try { api?.listener?.stop?.(); } catch { /* best effort */ }
      return this.status(accountId);
    }
    state.api = api;
    state.status = 'connected';
    state.ownId = String(await api.getOwnId());
    state.lastActivity = new Date();
    // MỌI handler của listener phải tự bắt lỗi.
    //
    // EventEmitter không chờ Promise của handler async: handler ném là một
    // unhandled rejection, và Node 24 GIẾT TIẾN TRÌNH vì nó. Đã xảy ra thật
    // (sidecar.log): app đang khởi động lại, callback ném `fetch failed`,
    // sidecar chết theo — mất phiên của MỌI nick, không ai nhận tin nữa.
    api.listener?.on?.('message', async (raw) => {
      try {
        state.lastActivity = new Date();
        const message = normalizeMessage(raw);
        if (!message.msg_id || !message.thread_id) return;
        // BỎ tin do chính tài khoản này gửi đi.
        //
        // Zalo vọng lại mọi tin trong luồng, kể cả tin ta vừa gửi. Không lọc
        // thì agent trả lời -> tin vọng về -> hệ thống ghi nhận như tin của
        // KHÁCH -> agent trả lời tiếp. Ở chế độ auto đó là vòng lặp vô hạn:
        // spam khách và đốt tiền model, không có gì tự dừng.
        //
        // Đã xảy ra thật: ba tin của chính hệ thống quay về cùng lúc và agent
        // bắt đầu soạn trả lời cho chính nó.
        if (state.ownId && message.sender_id === state.ownId) return;
        if (message.is_group) {
          // `layTenNhom` không ném, nhưng bọc thêm: một lỗi ở đây rơi xuống
          // `catch` ngoài là cả tin nhóm biến mất chỉ vì thiếu cái tên.
          try {
            message.group_name = await this.layTenNhom(accountId, api, message.thread_id);
          } catch (loi) {
            this.log.warn?.(`[sidecar] tên nhóm hỏng (${accountId}): ${loi?.message ?? loi}`);
            message.group_name = '';
          }
        }
        await this.onEvent(accountId, 'message', message);
      } catch (error) {
        this.log.error?.(`[sidecar] xử lý tin đến hỏng (${accountId}): ${error?.stack ?? error}`);
      }
    });
    api.listener?.on?.('closed', async () => {
      try {
        if (this.sessions.get(accountId)?.epoch === epoch) {
          state.status = 'disconnected';
          await this.onEvent(accountId, 'health', { status: 'disconnected' });
        }
      } catch (error) {
        this.log.error?.(`[sidecar] báo mất kết nối hỏng (${accountId}): ${error?.stack ?? error}`);
      }
    });
    api.listener?.start?.({ retryOnClose: true });
    await this.onEvent(accountId, 'health', { status: 'connected', own_id: state.ownId });
    return this.status(accountId);
  }

  requireConnected(accountId) {
    const state = this.sessions.get(accountId);
    if (!state?.api || state.status !== 'connected') {
      throw new Error('Tài khoản Zalo cá nhân chưa kết nối');
    }
    return state.api;
  }

  async sendText(accountId, { thread_id: threadId, thread_type: type = 0, text }) {
    const result = await this.requireConnected(accountId).sendMessage(
      { msg: String(text) }, String(threadId), Number(type),
    );
    return { message_id: providerMessageId(result) };
  }

  async sendFile(accountId, { thread_id: threadId, thread_type: type = 0, path, caption = '' }) {
    const result = await this.requireConnected(accountId).sendMessage(
      { msg: String(caption), attachments: [String(path)] },
      String(threadId),
      Number(type),
    );
    return { message_id: providerMessageId(result) };
  }
}
