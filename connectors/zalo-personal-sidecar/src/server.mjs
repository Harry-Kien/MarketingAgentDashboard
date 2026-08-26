import { createHmac, randomBytes } from 'node:crypto';
import { createServer } from 'node:http';
import { Zalo } from 'zca-js';

import { verifyRequest } from './auth.mjs';
import { SessionManager } from './session-manager.mjs';

const host = process.env.ZALO_SIDECAR_HOST ?? '127.0.0.1';
const port = Number(process.env.ZALO_SIDECAR_PORT ?? 3210);
const secret = process.env.ZALO_SIDECAR_SECRET ?? '';
const callbackUrl = process.env.ZALO_CONTROL_PLANE_URL ?? 'http://127.0.0.1:8000/webhook/native/zalo-personal';
if (secret.length < 32) throw new Error('ZALO_SIDECAR_SECRET phải dài ít nhất 32 ký tự');
if (!['127.0.0.1', '::1', 'localhost'].includes(host)) {
  throw new Error('Sidecar chỉ được bind localhost');
}

async function callback(accountId, event, data) {
  const body = JSON.stringify({ event, ...(event === 'message' ? { message: data } : { data }) });
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = randomBytes(16).toString('base64url');
  const path = new URL(`${callbackUrl}/${accountId}`).pathname;
  const canonical = `${timestamp}.${nonce}.POST.${path}.${body}`;
  const signature = `sha256=${createHmac('sha256', secret).update(canonical).digest('hex')}`;
  await fetch(`${callbackUrl}/${accountId}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-sidecar-timestamp': timestamp,
      'x-sidecar-nonce': nonce,
      'x-sidecar-signature': signature,
    },
    body,
  });
}

const manager = new SessionManager({
  zaloFactory: () => new Zalo({ logging: false, selfListen: true }),
  onEvent: callback,
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
      return json(response, 200, { ok: true });
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
