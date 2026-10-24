import assert from 'node:assert/strict';
import { test } from 'node:test';

import { kiemDiaChiNghe } from '../src/dia-chi-nghe.mjs';

test('localhost luôn được', () => {
  for (const h of ['127.0.0.1', '::1', 'localhost']) assert.equal(kiemDiaChiNghe(h, {}), h);
});

test('0.0.0.0 bị chặn khi KHÔNG bật cờ container', () => {
  assert.throws(() => kiemDiaChiNghe('0.0.0.0', {}), /localhost/);
});

test('0.0.0.0 được khi bật rõ cờ container', () => {
  assert.equal(kiemDiaChiNghe('0.0.0.0', { ZALO_SIDECAR_TRONG_CONTAINER: '1' }), '0.0.0.0');
});

test('cờ container không mở cửa cho địa chỉ tuỳ ý', () => {
  assert.throws(() => kiemDiaChiNghe('192.168.1.5', { ZALO_SIDECAR_TRONG_CONTAINER: '1' }));
});
