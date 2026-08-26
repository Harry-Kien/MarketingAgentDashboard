import assert from 'node:assert/strict';
import test from 'node:test';

import { SessionManager } from '../src/session-manager.mjs';

test('hai account có session độc lập và gửi bằng đúng API', async () => {
  let index = 0;
  const apis = [];
  const manager = new SessionManager({
    zaloFactory: () => ({
      login: async () => {
        const ownId = `own-${++index}`;
        const api = {
          getOwnId: async () => ownId,
          listener: { on() {}, start() {}, stop() {} },
          sendMessage: async (_payload, threadId) => ({ message: { msgId: `${ownId}:${threadId}` } }),
        };
        apis.push(api);
        return api;
      },
    }),
  });
  await manager.restore('account-a', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await manager.restore('account-b', { cookie: {}, imei: 'b', userAgent: 'ua' });
  const first = await manager.sendText('account-a', { thread_id: 'customer', text: 'A' });
  const second = await manager.sendText('account-b', { thread_id: 'customer', text: 'B' });
  assert.equal(first.message_id, 'own-1:customer');
  assert.equal(second.message_id, 'own-2:customer');
  assert.equal(apis.length, 2);
});

test('tin do chính tài khoản gửi KHÔNG được đẩy ngược vào hệ thống', async () => {
  // LỖI ĐÃ XẢY RA THẬT: listener đẩy mọi tin lên control plane, kể cả tin do
  // chính tài khoản này vừa gửi đi. Agent trả lời -> Zalo vọng lại -> hệ
  // thống ghi nhận như tin của KHÁCH -> agent trả lời tiếp. Ở chế độ auto
  // đó là vòng lặp vô hạn: spam khách và đốt tiền model.
  const daNhan = [];
  let onMessage = null;
  const manager = new SessionManager({
    zaloFactory: () => ({
      login: async () => ({
        getOwnId: async () => 'own-123',
        listener: {
          on(ten, handler) { if (ten === 'message') onMessage = handler; },
          start() {}, stop() {},
        },
        sendMessage: async () => ({ message: { msgId: 'm1' } }),
      }),
    }),
    onEvent: async (_accountId, event, data) => {
      if (event === 'message') daNhan.push(data);
    },
  });
  await manager.restore('account-a', { cookie: {}, imei: 'a', userAgent: 'ua' });

  // Tin của khách -> phải nhận
  await onMessage({ threadId: 'khach-1', data: { msgId: 'm-khach', uidFrom: 'khach-1', content: 'xin chào' } });
  // Tin của CHÍNH MÌNH vọng về -> phải bỏ
  await onMessage({ threadId: 'khach-1', data: { msgId: 'm-tu-minh', uidFrom: 'own-123', content: 'em là Linh đây ạ' } });

  assert.equal(daNhan.length, 1, 'chỉ tin của khách được đẩy lên');
  assert.equal(daNhan[0].msg_id, 'm-khach');
});
