/**
 * Ảnh/tệp khách gửi qua Zalo cá nhân PHẢI tới được control plane.
 *
 * Lỗi đã xảy ra thật: `normalizeMessage` chỉ đọc `content.attachments`,
 * trong khi zca-js 2.x đưa ảnh/tệp dưới dạng `content` là MỘT object
 * `TAttachmentContent` kèm `msgType`. Đo trên CSDL thật: 80 tin Zalo cá
 * nhân, 0 tin có tệp — ảnh không kèm chữ biến mất hoàn toàn.
 *
 * Payload dưới đây dựng theo đúng hình `TMessage` của zca-js (xem
 * node_modules/zca-js/dist/models/Message.d.ts), không phải hình ta mong.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeMessage, SessionManager } from '../src/session-manager.mjs';

function tinZca(msgType, content, extra = {}) {
  return {
    type: 0,
    threadId: 'khach-1',
    isSelf: false,
    data: {
      actionId: '1', msgId: `m-${msgType}`, cliMsgId: 'c1', msgType,
      uidFrom: 'khach-1', idTo: 'own-1', dName: 'Chị Lan', ts: '1763280000000',
      status: 1, content, notify: '1', ttl: 0, userId: '0', uin: '0',
      cmd: 501, st: 3, at: 5, realMsgId: '0', quote: undefined,
      ...extra,
    },
  };
}

test('ảnh KHÔNG kèm chữ (chat.photo) thành một tệp ảnh, không thành tin rỗng', () => {
  const m = normalizeMessage(tinZca('chat.photo', {
    title: '',
    description: '',
    href: 'https://photo-stal-1.zdn.vn/goc/anh-da.jpg',
    thumb: 'https://photo-stal-1.zdn.vn/thumb/anh-da.jpg',
    childnumber: 0,
    action: 'recommened.link',
    params: '{"width":1280,"height":960,"rawUrl":"https://photo-stal-1.zdn.vn/goc/anh-da.jpg"}',
    type: '',
  }));
  assert.equal(m.text, '');
  assert.equal(m.msg_type, 'chat.photo');
  assert.equal(m.attachments.length, 1);
  assert.equal(m.attachments[0].type, 'image');
  assert.equal(m.attachments[0].url, 'https://photo-stal-1.zdn.vn/goc/anh-da.jpg');
  assert.equal(m.attachments[0].thumb, 'https://photo-stal-1.zdn.vn/thumb/anh-da.jpg');
});

test('ảnh CÓ chú thích giữ cả chữ lẫn ảnh', () => {
  const m = normalizeMessage(tinZca('chat.photo', {
    title: 'mẫu này còn không shop', description: '', href: 'https://x/goc.jpg',
    thumb: 'https://x/thumb.jpg', childnumber: 0, action: '', params: '', type: '',
  }));
  assert.equal(m.text, 'mẫu này còn không shop');
  assert.equal(m.attachments[0].url, 'https://x/goc.jpg');
});

test('ảnh thiếu href thì lùi về thumb, không bỏ', () => {
  const m = normalizeMessage(tinZca('chat.photo', {
    title: '', description: '', href: '', thumb: 'https://x/thumb.jpg',
    childnumber: 0, action: '', params: '', type: '',
  }));
  assert.equal(m.attachments[0].url, 'https://x/thumb.jpg');
});

test('tệp (share.file): tên tệp vào tệp đính kèm, KHÔNG vào lời khách', () => {
  const m = normalizeMessage(tinZca('share.file', {
    title: 'Bao_gia_T11.pdf',
    description: '',
    href: 'https://f21-zpc.zdn.vn/1234/Bao_gia_T11.pdf',
    thumb: '',
    childnumber: 0,
    action: 'recommened.file',
    params: '{"fileSize":"183245","checksum":"abc","fileExt":"pdf","fType":1,"fdata":"{}"}',
    type: '',
  }));
  assert.equal(m.text, '', 'tên tệp không phải câu khách hỏi');
  assert.deepEqual(m.attachments, [{
    type: 'file',
    url: 'https://f21-zpc.zdn.vn/1234/Bao_gia_T11.pdf',
    name: 'Bao_gia_T11.pdf',
    size: 183245,
    ext: 'pdf',
  }]);
});

test('video và ghi âm cũng thành tệp đúng loại', () => {
  const v = normalizeMessage(tinZca('chat.video.msg', {
    title: '', description: '', href: 'https://x/v.mp4', thumb: 'https://x/v.jpg',
    childnumber: 0, action: '', params: '{"duration":5000}', type: '',
  }));
  assert.equal(v.attachments[0].type, 'video');
  const a = normalizeMessage(tinZca('chat.voice', {
    title: '', description: '', href: 'https://x/a.m4a', thumb: '',
    childnumber: 0, action: '', params: '', type: '',
  }));
  assert.equal(a.attachments[0].type, 'audio');
});

test('tin chữ thường vẫn như cũ', () => {
  const m = normalizeMessage(tinZca('webchat', 'xin chào shop'));
  assert.equal(m.text, 'xin chào shop');
  assert.deepEqual(m.attachments, []);
  assert.equal(m.msg_id, 'm-webchat');
  assert.equal(m.thread_id, 'khach-1');
});

test('sticker không có URL: không bịa tệp, nhưng mang msg_type để phía Python ghi lý do', () => {
  const m = normalizeMessage(tinZca('chat.sticker', { id: 1234, catId: 10, type: 7 }));
  assert.deepEqual(m.attachments, []);
  assert.equal(m.msg_type, 'chat.sticker');
});

test('ảnh đi trọn đường listener -> onEvent', async () => {
  const nhan = [];
  let onMessage = null;
  const manager = new SessionManager({
    zaloFactory: () => ({
      login: async () => ({
        getOwnId: async () => 'own-1',
        listener: { on(ten, h) { if (ten === 'message') onMessage = h; }, start() {}, stop() {} },
        sendMessage: async () => ({}),
      }),
    }),
    onEvent: async (_a, event, data) => { if (event === 'message') nhan.push(data); },
  });
  await manager.restore('account-a', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await onMessage(tinZca('chat.photo', {
    title: '', description: '', href: 'https://x/goc.jpg', thumb: '',
    childnumber: 0, action: '', params: '', type: '',
  }));
  assert.equal(nhan.length, 1);
  assert.equal(nhan[0].attachments[0].url, 'https://x/goc.jpg');
});

test('handler listener KHÔNG để lọt rejection khi onEvent ném', async () => {
  // Node 24 giết tiến trình vì unhandled rejection; EventEmitter không chờ
  // Promise của handler. Đã xảy ra thật: `fetch failed` lúc app khởi động lại.
  let onMessage = null;
  let onClosed = null;
  const loi = [];
  const manager = new SessionManager({
    zaloFactory: () => ({
      login: async () => ({
        getOwnId: async () => 'own-1',
        listener: {
          on(ten, h) { if (ten === 'message') onMessage = h; if (ten === 'closed') onClosed = h; },
          start() {}, stop() {},
        },
        sendMessage: async () => ({}),
      }),
    }),
    onEvent: async (_a, event) => {
      if (event !== 'health') throw new TypeError('fetch failed');
      if (onClosed && loi.length) throw new TypeError('fetch failed');
    },
    log: { error: (s) => loi.push(s), warn() {} },
  });
  await manager.restore('account-a', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await assert.doesNotReject(onMessage(tinZca('webchat', 'alo')));
  await assert.doesNotReject(onClosed());
  assert.ok(loi.some((s) => s.includes('fetch failed')), 'lỗi phải được ghi, không nuốt');
});
