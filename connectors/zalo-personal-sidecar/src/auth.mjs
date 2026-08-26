import { createHmac, timingSafeEqual } from 'node:crypto';

export function signRequest(secret, { timestamp, nonce, method, path, body }) {
  const canonical = `${timestamp}.${nonce}.${method.toUpperCase()}.${path}.`;
  return `sha256=${createHmac('sha256', secret)
    .update(canonical)
    .update(body)
    .digest('hex')}`;
}

export function verifyRequest(secret, request, rawBody, nonceStore, now = Date.now()) {
  const timestamp = request.headers['x-sidecar-timestamp'];
  const nonce = request.headers['x-sidecar-nonce'];
  const supplied = request.headers['x-sidecar-signature'];
  const seconds = Number(timestamp);
  if (!timestamp || !nonce || !supplied || !Number.isFinite(seconds)) return false;
  if (Math.abs(Math.floor(now / 1000) - seconds) > 60) return false;
  if (nonceStore.has(nonce)) return false;
  const expected = signRequest(secret, {
    timestamp,
    nonce,
    method: request.method,
    path: new URL(request.url, 'http://127.0.0.1').pathname,
    body: rawBody,
  });
  const left = Buffer.from(supplied);
  const right = Buffer.from(expected);
  if (left.length !== right.length || !timingSafeEqual(left, right)) return false;
  nonceStore.set(nonce, now);
  for (const [key, seenAt] of nonceStore) {
    if (now - seenAt > 120_000) nonceStore.delete(key);
  }
  return true;
}
