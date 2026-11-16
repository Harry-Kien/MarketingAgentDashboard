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
  return {
    msg_id: String(data.msgId ?? data.msg_id ?? data.cliMsgId ?? ''),
    thread_id: String(raw?.threadId ?? data.threadId ?? ''),
    thread_type: Number(raw?.type ?? data.type ?? 0),
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
  constructor({ zaloFactory, onEvent = async () => {}, log = console }) {
    this.zaloFactory = zaloFactory;
    this.onEvent = onEvent;
    this.log = log;
    this.sessions = new Map();
    this.epochs = new Map();
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
