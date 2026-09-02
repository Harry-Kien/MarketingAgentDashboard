function providerMessageId(result) {
  return String(
    result?.message?.msgId
      ?? result?.attachment?.[0]?.msgId
      ?? result?.msgId
      ?? '',
  );
}

function normalizeMessage(raw) {
  const data = raw?.data ?? raw ?? {};
  const content = data.content ?? {};
  const attachments = [];
  for (const item of content.attachments ?? data.attachments ?? []) {
    const url = String(item?.href ?? item?.url ?? item?.thumbUrl ?? '');
    if (url) attachments.push({ type: item?.type ?? 'file', url });
  }
  const text = typeof content === 'string'
    ? content
    : String(content?.title ?? content?.msg ?? data?.msg ?? '');
  return {
    msg_id: String(data.msgId ?? data.msg_id ?? data.cliMsgId ?? ''),
    thread_id: String(raw?.threadId ?? data.threadId ?? ''),
    thread_type: Number(raw?.type ?? data.type ?? 0),
    sender_id: String(data.uidFrom ?? data.senderId ?? ''),
    sender_name: String(data.dName ?? data.senderName ?? ''),
    text,
    timestamp: Number(data.ts ?? data.timestamp ?? Date.now()),
    attachments,
  };
}

export class SessionManager {
  constructor({ zaloFactory, onEvent = async () => {} }) {
    this.zaloFactory = zaloFactory;
    this.onEvent = onEvent;
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
        if (this.sessions.get(accountId)?.epoch === epoch) {
          state.status = 'disconnected';
          await this.onEvent(accountId, 'health', { status: 'disconnected' });
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
    api.listener?.on?.('message', async (raw) => {
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
    });
    api.listener?.on?.('closed', async () => {
      if (this.sessions.get(accountId)?.epoch === epoch) {
        state.status = 'disconnected';
        await this.onEvent(accountId, 'health', { status: 'disconnected' });
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
