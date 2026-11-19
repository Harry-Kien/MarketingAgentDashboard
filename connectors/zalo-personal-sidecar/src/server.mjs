import { createServer } from 'node:http';
import { Zalo } from 'zca-js';

import { verifyRequest } from './auth.mjs';
import { layMetadataAnh } from './anh-metadata.mjs';
import { HangDoiCallback } from './callback.mjs';
import { kiemDiaChiNghe } from './dia-chi-nghe.mjs';
import { SessionManager } from './session-manager.mjs';

const host = process.env.ZALO_SIDECAR_HOST ?? '127.0.0.1';
const port = Number(process.env.ZALO_SIDECAR_PORT ?? 3210);
const secret = process.env.ZALO_SIDECAR_SECRET ?? '';
const callbackUrl = process.env.ZALO_CONTROL_PLANE_URL ?? 'http://127.0.0.1:8000/webhook/native/zalo-personal';
if (secret.length < 32) throw new Error('ZALO_SIDECAR_SECRET phải dài ít nhất 32 ký tự');
kiemDiaChiNghe(host, process.env);

// Lưới cuối: một Promise bị bỏ rơi KHÔNG được giết tiến trình.
//
// Node 24 mặc định thoát khi có unhandled rejection. Đã xảy ra thật
// (sidecar.log): app khởi động lại, callback ném `fetch failed`, sidecar
// chết theo — mất phiên RAM của MỌI nick Zalo, không nhận tin nào nữa cho
// tới khi người canh dựng lại. Ghi to rồi sống tiếp: một sự kiện hỏng rẻ hơn
// cả cụm phiên.
process.on('unhandledRejection', (reason) => {
  console.error(`[sidecar] UNHANDLED REJECTION (đã chặn, tiến trình vẫn sống): ${reason?.stack ?? reason}`);
});

// Tin khách, phiên, sức khoẻ đi qua hàng đợi thử lại — xem callback.mjs.
const hangDoi = new HangDoiCallback({ baseUrl: callbackUrl, secret });

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled Rejection in Zalo sidecar:', reason);
});
process.on('uncaughtException', (err) => {
  console.error('Uncaught Exception in Zalo sidecar:', err);
});

const manager = new SessionManager({
  zaloFactory: () => new Zalo({
    logging: false,
    selfListen: true,
    // BẮT BUỘC để gửi được ảnh từ Node.
    //
    // Trên trình duyệt `zca-js` tự đọc kích thước từ thẻ <img>; ở Node không
    // có DOM nên nó ném `Missing imageMetadataGetter` và MỌI lần gửi ảnh đều
    // hỏng. Đã xảy ra thật: một tin gửi ảnh sản phẩm thử 8 lần rồi chết
    // trong hàng đợi, khách không nhận được gì, và không có gì trên dashboard
    // nói ra lý do.
    imageMetadataGetter: layMetadataAnh,
  }),
  onEvent: (accountId, event, data) => hangDoi.gui(accountId, event, data),
});
const nonceStore = new Map();

function json(response, status, data) {
  const body = JSON.stringify(data);
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
  });
  response.end(body);
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 1024 * 1024) throw new Error('Payload vượt quá 1 MB');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

createServer(async (request, response) => {
  try {
    if (request.method === 'GET' && request.url === '/healthz') {
      // Số sự kiện đang ứ: >0 kéo dài nghĩa là control plane không nhận.
      return json(response, 200, { ok: true, callback_cho: hangDoi.dangCho });
    }
    const match = new URL(request.url, `http://${host}`).pathname.match(
      /^\/v1\/accounts\/([0-9a-f-]{36})\/(login-qr|restore-session|send-text|send-file|status)$/,
    );
    if (!match) return json(response, 404, { ok: false, error: 'Không tìm thấy endpoint' });
    const rawBody = await readBody(request);
    if (!verifyRequest(secret, request, rawBody, nonceStore)) {
      return json(response, 401, { ok: false, error: 'Chữ ký sidecar không hợp lệ' });
    }
    const [, accountId, action] = match;
    const body = rawBody.length ? JSON.parse(rawBody.toString('utf8')) : {};
    if (action === 'login-qr') {
      const state = await manager.startQr(accountId);
      return json(response, 202, { ok: true, ...state });
    }
    if (action === 'restore-session') {
      const state = await manager.restore(accountId, body.session ?? {});
      return json(response, 200, { ok: true, ...state });
    }
    if (action === 'send-text') {
      return json(response, 200, { ok: true, ...await manager.sendText(accountId, body) });
    }
    if (action === 'send-file') {
      return json(response, 200, { ok: true, ...await manager.sendFile(accountId, body) });
    }
    return json(response, 200, { ok: true, ...manager.status(accountId) });
  } catch (error) {
    return json(response, 409, { ok: false, error: String(error?.message ?? error).slice(0, 200) });
  }
}).listen(port, host, () => {
  process.stdout.write(`Zalo personal sidecar listening on http://${host}:${port}\n`);
});
