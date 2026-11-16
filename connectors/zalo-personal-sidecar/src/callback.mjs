/**
 * Đẩy sự kiện (tin khách, phiên, sức khoẻ) về control plane — KHÔNG ĐƯỢC MẤT.
 *
 * VÌ SAO CẦN HÀNG ĐỢI
 * -------------------
 * Bản trước `await fetch(...)` một lần rồi thôi: không đọc mã HTTP, không
 * thử lại. Hộp thư bền phía Python (agent/omnichannel/hop_thu_ben.py) giả
 * định "CSDL hỏng thì trả 5xx, HÃNG TỰ GỬI LẠI" — đúng với Meta và Zalo OA,
 * SAI với sidecar: ở đây sidecar chính là "hãng", và nó không gửi lại gì cả.
 * App khởi động lại (29 lần trong 11 ngày trên laptop này) là mọi tin khách
 * đến trong khoảng ấy biến mất: không lỗi, không nhật ký, không ai biết.
 * Tệ hơn, `fetch failed` ném ra từ handler async làm Node 24 chết vì
 * unhandled rejection — mất phiên của mọi nick.
 *
 * Nay: mỗi sự kiện vào hàng FIFO trong RAM; gửi tới khi nhận 2xx, giãn cách
 * 1s, 2s, 4s… tối đa 60s. Phía Python chống trùng theo msgId, nên gửi lại
 * một tin đã tới là vô hại.
 *
 * GIỚI HẠN PHẢI NÓI RÕ: hàng đợi nằm trong RAM. Sidecar chết thì mất phần
 * đang chờ — vẫn tốt hơn hẳn "mất mọi tin trong lúc app khởi động lại", và
 * mỗi lần tràn hay bỏ đều ghi log to, không bỏ im lặng.
 */
import { createHmac, randomBytes } from 'node:crypto';

// Mã HTTP gửi lại vô ích: payload sai, tài khoản không tồn tại. Thử lại
// mãi chỉ chặn đầu hàng và giữ các tin sau lại phía sau nó.
const MA_BO_LUON = new Set([400, 404, 413, 422]);

export function kyCallback(secret, url, body, { now = Date.now(), nonce } = {}) {
  const timestamp = String(Math.floor(now / 1000));
  const n = nonce ?? randomBytes(16).toString('base64url');
  const path = new URL(url).pathname;
  const canonical = `${timestamp}.${n}.POST.${path}.${body}`;
  return {
    'content-type': 'application/json',
    'x-sidecar-timestamp': timestamp,
    'x-sidecar-nonce': n,
    'x-sidecar-signature': `sha256=${createHmac('sha256', secret).update(canonical).digest('hex')}`,
  };
}

export class HangDoiCallback {
  constructor({
    baseUrl,
    secret,
    fetchImpl = globalThis.fetch,
    log = console,
    gioiHan = 1000,
    treMinMs = 1000,
    treMaxMs = 60_000,
    timeoutMs = 15_000,
    tranLoiMayChu = 20,
  }) {
    this.tranLoiMayChu = tranLoiMayChu;
    this.baseUrl = baseUrl;
    this.secret = secret;
    this.fetchImpl = fetchImpl;
    this.log = log;
    this.gioiHan = gioiHan;
    this.treMinMs = treMinMs;
    this.treMaxMs = treMaxMs;
    this.timeoutMs = timeoutMs;
    this.hang = [];
    this.dangChay = null;
    this.daBoVi = { tran: 0, tu_choi: 0 };
  }

  get dangCho() {
    return this.hang.length;
  }

  /**
   * Xếp một sự kiện vào hàng và kích vòng gửi. KHÔNG BAO GIỜ ném: chỗ gọi là
   * handler của listener zca-js, và một lần ném ở đó từng giết cả tiến trình.
   */
  gui(accountId, event, data) {
    try {
      this.hang.push({ accountId, event, data, lanThu: 0 });
      if (this.hang.length > this.gioiHan) {
        // Bỏ cái CŨ NHẤT: tin mới nhất là thứ khách đang chờ trả lời. Trừ
        // mục đang bay — nó có thể tới nơi ngay sau, và ghi "đã bỏ" cho một
        // tin thực ra đã tới là nhật ký nói dối.
        const viTri = this.hang[0] === this.dangGui && this.hang.length > 1 ? 1 : 0;
        const [bo] = this.hang.splice(viTri, 1);
        this.daBoVi.tran += 1;
        this.log.error?.(
          `[sidecar] HÀNG ĐỢI CALLBACK TRÀN (${this.gioiHan}) — BỎ sự kiện `
          + `${bo.event} của ${bo.accountId}. Control plane không nhận được gì `
          + 'từ lâu: kiểm app cổng 8000.',
        );
      }
      this._kich();
    } catch (error) {
      this.log.error?.(`[sidecar] không xếp được callback: ${error?.stack ?? error}`);
    }
    return Promise.resolve();
  }

  /** Chờ hàng gửi xong (hoặc vòng dừng). Dùng cho test và lúc tắt. */
  cho() {
    return this.dangChay ?? Promise.resolve();
  }

  _kich() {
    if (this.dangChay) return;
    this.dangChay = this._vong()
      .catch((error) => {
        this.log.error?.(`[sidecar] vòng gửi callback hỏng: ${error?.stack ?? error}`);
      })
      .finally(() => {
        this.dangChay = null;
        // Có thể vừa có sự kiện mới xếp vào đúng lúc vòng kết thúc.
        if (this.hang.length) this._kich();
      });
  }

  async _vong() {
    while (this.hang.length) {
      const muc = this.hang[0];
      this.dangGui = muc;
      let kq;
      try {
        kq = await this._guiMot(muc);
      } finally {
        this.dangGui = null;
      }
      if (kq === 'thu_lai') {
        muc.lanThu += 1;
        const tre = Math.min(this.treMaxMs, this.treMinMs * 2 ** (muc.lanThu - 1));
        await new Promise((xong) => setTimeout(xong, tre));
        continue;
      }
      // So bằng danh tính, không shift() mù: lúc chờ mạng, mục đầu có thể đã
      // bị đẩy ra vì tràn hàng.
      const i = this.hang.indexOf(muc);
      if (i >= 0) this.hang.splice(i, 1);
    }
  }

  async _guiMot(muc) {
    const { accountId, event, data } = muc;
    const url = `${this.baseUrl}/${accountId}`;
    const body = JSON.stringify({ event, ...(event === 'message' ? { message: data } : { data }) });
    let response;
    try {
      // Ký LẠI mỗi lần thử: phía Python chỉ nhận chữ ký trong 60 giây và
      // không nhận lại nonce cũ.
      response = await this.fetchImpl(url, {
        method: 'POST',
        headers: kyCallback(this.secret, url, body),
        body,
        signal: AbortSignal.timeout(this.timeoutMs),
      });
    } catch (error) {
      this.log.warn?.(
        `[sidecar] callback ${event} chưa tới control plane (lần ${muc.lanThu + 1}, `
        + `còn ${this.hang.length} chờ): ${error?.cause?.code ?? error?.message ?? error}`,
      );
      return 'thu_lai';
    }
    if (response.ok) {
      if (muc.lanThu > 0) {
        this.log.warn?.(`[sidecar] callback ${event} đã tới sau ${muc.lanThu + 1} lần thử.`);
      }
      return 'ok';
    }
    if (response.status === 401) {
      // Ghi TO: đây là bệnh đã làm callback bị 401 tám ngày liền mà không ai
      // biết (xem agent/omnichannel/bi_mat_may_chu.py). Vẫn thử lại — sửa
      // .env rồi khởi động lại app là hàng tự chảy tiếp.
      this.log.error?.(
        '[sidecar] ********** CALLBACK BỊ TỪ CHỐI 401 — ZALO_SIDECAR_SECRET của '
        + 'sidecar LỆCH với .env của app. Tin khách đang ỨN LẠI trong RAM '
        + `(${this.hang.length} sự kiện). Khởi động lại sidecar: `
        + 'python -m scripts.chay_sidecar_zalo **********',
      );
      return 'thu_lai';
    }
    if (MA_BO_LUON.has(response.status)) {
      this.daBoVi.tu_choi += 1;
      let chiTiet = '';
      try { chiTiet = (await response.text()).slice(0, 200); } catch { /* bỏ qua */ }
      this.log.error?.(
        `[sidecar] control plane TỪ CHỐI callback ${event} của ${accountId} `
        + `(HTTP ${response.status}) — BỎ, gửi lại không chữa được: ${chiTiet}`,
      );
      return 'bo';
    }
    // App ĐANG SỐNG mà vẫn trả lỗi cho đúng sự kiện này: có thể là một tin
    // "độc" làm app hỏng mỗi lần. Thử lại mãi thì nó chặn đầu hàng và mọi tin
    // sau đó chết theo — nên có trần, và bỏ thì bỏ TO. Mất mạng (app tắt) thì
    // không tính vào đây: chờ bao lâu cũng được.
    muc.loiMayChu = (muc.loiMayChu ?? 0) + 1;
    if (muc.loiMayChu >= this.tranLoiMayChu) {
      this.daBoVi.tu_choi += 1;
      this.log.error?.(
        `[sidecar] callback ${event} của ${accountId} nhận HTTP ${response.status} `
        + `${muc.loiMayChu} lần liền — BỎ để không chặn các tin sau. Xem log app.`,
      );
      return 'bo';
    }
    this.log.warn?.(
      `[sidecar] callback ${event} nhận HTTP ${response.status} (lần ${muc.lanThu + 1}) — sẽ thử lại.`,
    );
    return 'thu_lai';
  }
}
