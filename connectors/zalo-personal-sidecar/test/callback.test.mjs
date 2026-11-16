/**
 * Callback về control plane phải sống sót qua lúc app khởi động lại.
 *
 * Lỗi đã xảy ra thật: `callback()` gọi fetch một lần, không đọc mã HTTP,
 * không thử lại, và `fetch failed` lọt ra thành unhandled rejection giết
 * cả sidecar. Hộp thư bền phía Python giả định "hãng gửi lại khi 5xx" —
 * sidecar là "hãng" ở đây, và nó không gửi lại gì.
 */
import assert from 'node:assert/strict';
import { createHmac } from 'node:crypto';
import test from 'node:test';

import { HangDoiCallback, kyCallback } from '../src/callback.mjs';

const SECRET = 's'.repeat(40);
const URL_GOC = 'http://127.0.0.1:8000/webhook/native/zalo-personal';

function ghiLog() {
  const dong = { warn: [], error: [] };
  return { dong, log: { warn: (s) => dong.warn.push(s), error: (s) => dong.error.push(s) } };
}

function phanHoi(status) {
  return { ok: status >= 200 && status < 300, status, text: async () => 'chi tiết' };
}

function hang(fetchImpl, extra = {}) {
  const { dong, log } = ghiLog();
  const h = new HangDoiCallback({
    baseUrl: URL_GOC, secret: SECRET, fetchImpl, log, treMinMs: 1, treMaxMs: 4, ...extra,
  });
  return { h, dong };
}

test('chữ ký khớp đúng công thức phía Python (verify_sidecar_callback)', () => {
  const body = '{"event":"message"}';
  const url = `${URL_GOC}/acc-1`;
  const h = kyCallback(SECRET, url, body, { now: 1_700_000_000_000, nonce: 'n1' });
  const mong = createHmac('sha256', SECRET)
    .update(`1700000000.n1.POST./webhook/native/zalo-personal/acc-1.${body}`).digest('hex');
  assert.equal(h['x-sidecar-signature'], `sha256=${mong}`);
  assert.equal(h['x-sidecar-timestamp'], '1700000000');
});

test('app đang khởi động lại (fetch failed, rồi 503) thì THỬ LẠI tới khi 2xx', async () => {
  const goi = [];
  const kichBan = ['loi_mang', 'loi_mang', 503, 200];
  const { h, dong } = hang(async (url, opts) => {
    goi.push({ url, body: opts.body, ky: opts.headers['x-sidecar-nonce'] });
    const buoc = kichBan.shift();
    if (buoc === 'loi_mang') throw new TypeError('fetch failed');
    return phanHoi(buoc);
  });
  await h.gui('acc-1', 'message', { msg_id: 'm1', text: 'alo' });
  await h.cho();
  assert.equal(goi.length, 4);
  assert.equal(h.dangCho, 0);
  assert.equal(JSON.parse(goi[3].body).message.msg_id, 'm1');
  assert.equal(new Set(goi.map((g) => g.ky)).size, 4, 'mỗi lần thử phải ký lại (nonce mới)');
  assert.ok(dong.warn.some((s) => s.includes('fetch failed')));
});

test('gui() không bao giờ ném, kể cả khi fetch ném', async () => {
  let lan = 0;
  const { h } = hang(async () => {
    lan += 1;
    if (lan < 3) throw new TypeError('fetch failed');
    return phanHoi(200);
  });
  await assert.doesNotReject(h.gui('acc-1', 'health', { status: 'connected' }));
  await h.cho();
  assert.equal(lan, 3);
});

test('giữ đúng THỨ TỰ: tin sau không vượt tin trước đang chờ', async () => {
  const toi = [];
  let lan = 0;
  const { h } = hang(async (_url, opts) => {
    lan += 1;
    if (lan === 1) return phanHoi(502);
    toi.push(JSON.parse(opts.body).message.msg_id);
    return phanHoi(200);
  });
  h.gui('acc-1', 'message', { msg_id: 'a' });
  h.gui('acc-1', 'message', { msg_id: 'b' });
  h.gui('acc-1', 'message', { msg_id: 'c' });
  await h.cho();
  assert.deepEqual(toi, ['a', 'b', 'c']);
});

test('401 ghi log TO và vẫn thử lại (sửa .env + khởi động app là hàng tự chảy)', async () => {
  const kichBan = [401, 401, 200];
  const { h, dong } = hang(async () => phanHoi(kichBan.shift()));
  h.gui('acc-1', 'message', { msg_id: 'm' });
  await h.cho();
  assert.equal(kichBan.length, 0);
  assert.ok(dong.error.some((s) => s.includes('401') && s.includes('chay_sidecar_zalo')));
});

test('4xx vô phương cứu (404/422) thì BỎ có ghi log, không chặn tin sau', async () => {
  const toi = [];
  const { h, dong } = hang(async (_url, opts) => {
    const id = JSON.parse(opts.body).message.msg_id;
    if (id === 'hong') return phanHoi(404);
    toi.push(id);
    return phanHoi(200);
  });
  h.gui('acc-1', 'message', { msg_id: 'hong' });
  h.gui('acc-1', 'message', { msg_id: 'tot' });
  await h.cho();
  assert.deepEqual(toi, ['tot']);
  assert.ok(dong.error.some((s) => s.includes('404') && s.includes('BỎ')));
});

test('5xx lặp mãi với cùng một sự kiện thì có trần, không chặn cả hàng', async () => {
  const toi = [];
  const { h, dong } = hang(async (_url, opts) => {
    const id = JSON.parse(opts.body).message.msg_id;
    if (id === 'doc') return phanHoi(500);
    toi.push(id);
    return phanHoi(200);
  }, { tranLoiMayChu: 3 });
  h.gui('acc-1', 'message', { msg_id: 'doc' });
  h.gui('acc-1', 'message', { msg_id: 'sau' });
  await h.cho();
  assert.deepEqual(toi, ['sau']);
  assert.ok(dong.error.some((s) => s.includes('3 lần liền')));
});

test('hàng đầy thì bỏ cái CŨ NHẤT và ghi log, không phình RAM vô hạn', async () => {
  let mo = null;
  const cong = new Promise((xong) => { mo = xong; });
  const toi = [];
  const { h, dong } = hang(async (_url, opts) => {
    await cong;
    toi.push(JSON.parse(opts.body).message.msg_id);
    return phanHoi(200);
  }, { gioiHan: 3 });
  for (const id of ['1', '2', '3', '4', '5']) h.gui('acc-1', 'message', { msg_id: id });
  assert.equal(h.dangCho, 3);
  assert.equal(dong.error.filter((s) => s.includes('TRÀN')).length, 2);
  mo();
  await h.cho();
  // '1' đang bay lúc tràn nên vẫn tới; '2' và '3' bị đẩy ra.
  assert.deepEqual(toi, ['1', '4', '5']);
});
