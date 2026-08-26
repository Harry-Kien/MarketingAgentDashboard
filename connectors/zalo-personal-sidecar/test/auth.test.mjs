import assert from 'node:assert/strict';
import test from 'node:test';

import { signRequest, verifyRequest } from '../src/auth.mjs';

test('HMAC chặn replay nonce và body bị sửa', () => {
  const now = 1_787_600_000_000;
  const timestamp = String(Math.floor(now / 1000));
  const body = Buffer.from('{"text":"xin chào"}');
  const signature = signRequest('a'.repeat(32), {
    timestamp, nonce: 'nonce-1', method: 'POST', path: '/v1/accounts/a/send-text', body,
  });
  const request = {
    method: 'POST',
    url: '/v1/accounts/a/send-text',
    headers: {
      'x-sidecar-timestamp': timestamp,
      'x-sidecar-nonce': 'nonce-1',
      'x-sidecar-signature': signature,
    },
  };
  const seen = new Map();
  assert.equal(verifyRequest('a'.repeat(32), request, body, seen, now), true);
  assert.equal(verifyRequest('a'.repeat(32), request, body, seen, now), false);
});
