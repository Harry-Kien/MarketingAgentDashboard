/**
 * Tin NHÓM Zalo phải tới control plane với danh tính của NHÓM, kèm người gửi.
 *
 * Lỗi đã xảy ra thật: sidecar chỉ đẩy `uidFrom`/`dName` (người gửi) mà
 * không có tên nhóm. Phía Python lấy người gửi làm danh tính của hội thoại:
 * hội thoại nhóm mang tên người nói sau cùng, và bị gắn vào hồ sơ riêng của
 * người đó — trí nhớ riêng của họ lọt vào câu trả lời trong nhóm.
 *
 * Payload dựng theo đúng hình `GroupMessage` của zca-js 2.x
 * (node_modules/zca-js/dist/models/Message.d.ts): `type: 1`, `threadId` là
 * id nhóm, `data.uidFrom` là người gửi.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  normalizeMessage, SessionManager, TEN_NHOM_LOI_MS, TEN_NHOM_SONG_MS,
} from '../src/session-manager.mjs';

function tinNhom(msgId, uidFrom = 'ban-1', dName = 'Chị Lan') {
  return {
    type: 1,
    threadId: 'nhom-9',
    isSelf: false,
    data: { msgId, uidFrom, dName, msgType: 'webchat', content: 'shop ơi', ts: '1763280000000' },
  };
}

function dungPhien({ getGroupInfo, now }) {
  const daNhan = [];
  const canhBao = [];
  let onMessage = null;
  const manager = new SessionManager({
    now,
    log: { warn: (s) => canhBao.push(s), error: (s) => canhBao.push(s) },
    zaloFactory: () => ({
      login: async () => ({
        getOwnId: async () => 'own-1',
        getGroupInfo,
        listener: {
          on(ten, handler) { if (ten === 'message') onMessage = handler; },
          start() {}, stop() {},
        },
      }),
    }),
    onEvent: async (_acc, event, data) => { if (event === 'message') daNhan.push(data); },
  });
  return { manager, daNhan, canhBao, gui: (raw) => onMessage(raw) };
}

test('tin nhóm khai TƯỜNG MINH là nhóm, người gửi vẫn là người gửi', () => {
  const m = normalizeMessage(tinNhom('g1', 'ban-7', 'Anh Tú'));
  assert.equal(m.is_group, true);
  assert.equal(m.thread_type, 1);
  assert.equal(m.thread_id, 'nhom-9');
  assert.equal(m.sender_id, 'ban-7');
  assert.equal(m.sender_name, 'Anh Tú');
});

test('tin nhắn riêng KHÔNG bị coi là nhóm', () => {
  const m = normalizeMessage({ type: 0, threadId: 'khach-1', data: { msgId: 'r1', uidFrom: 'khach-1', content: 'hi' } });
  assert.equal(m.is_group, false);
  assert.equal(m.group_name, '');
});

test('tên nhóm được lấy một lần rồi đệm, không hỏi Zalo mỗi tin', async () => {
  let goi = 0;
  let bayGio = 1_000;
  const p = dungPhien({
    now: () => bayGio,
    getGroupInfo: async (id) => {
      goi += 1;
      return { gridInfoMap: { [id]: { name: 'Hội mê skincare' } } };
    },
  });
  await p.manager.restore('acc', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await p.gui(tinNhom('g1'));
  await p.gui(tinNhom('g2', 'ban-2', 'Anh Tú'));
  assert.equal(goi, 1, 'tin thứ hai dùng tên trong đệm');
  assert.deepEqual(p.daNhan.map((m) => m.group_name), ['Hội mê skincare', 'Hội mê skincare']);
  assert.deepEqual(p.daNhan.map((m) => m.sender_name), ['Chị Lan', 'Anh Tú']);

  bayGio += TEN_NHOM_SONG_MS + 1;      // đệm hết hạn -> hỏi lại (tên nhóm có thể đã đổi)
  await p.gui(tinNhom('g3'));
  assert.equal(goi, 2);
});

test('Zalo hỏng khi hỏi tên nhóm: tin VẪN đi, có ghi cảnh báo, thử lại sau ít phút', async () => {
  let goi = 0;
  let bayGio = 1_000;
  const p = dungPhien({
    now: () => bayGio,
    getGroupInfo: async () => { goi += 1; throw new Error('Tham số không hợp lệ'); },
  });
  await p.manager.restore('acc', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await p.gui(tinNhom('g1'));
  await p.gui(tinNhom('g2'));
  assert.equal(p.daNhan.length, 2, 'không được làm rơi tin chỉ vì thiếu tên nhóm');
  assert.equal(p.daNhan[0].group_name, '');
  assert.equal(p.daNhan[0].is_group, true);
  assert.equal(goi, 1, 'đợt hỏng không hỏi lại ở từng tin');
  assert.ok(p.canhBao.some((s) => s.includes('nhom-9')), 'hỏng phải để lại dấu vết');

  bayGio += TEN_NHOM_LOI_MS + 1;
  await p.gui(tinNhom('g3'));
  assert.equal(goi, 2);
});

test('lần hỏi sau hỏng thì giữ tên cũ đã biết, không lùi về rỗng', async () => {
  let bayGio = 1_000;
  let hong = false;
  const p = dungPhien({
    now: () => bayGio,
    getGroupInfo: async (id) => {
      if (hong) throw new Error('mạng chập');
      return { gridInfoMap: { [id]: { name: 'Nhóm sỉ HN' } } };
    },
  });
  await p.manager.restore('acc', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await p.gui(tinNhom('g1'));
  hong = true;
  bayGio += TEN_NHOM_SONG_MS + 1;
  await p.gui(tinNhom('g2'));
  assert.deepEqual(p.daNhan.map((m) => m.group_name), ['Nhóm sỉ HN', 'Nhóm sỉ HN']);
});

test('phiên không có getGroupInfo (bản zca-js khác) vẫn cho tin nhóm đi', async () => {
  const p = dungPhien({ now: () => 0, getGroupInfo: undefined });
  await p.manager.restore('acc', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await p.gui(tinNhom('g1'));
  assert.equal(p.daNhan.length, 1);
  assert.equal(p.daNhan[0].group_name, '');
});

test('tin nhắn riêng không gọi getGroupInfo', async () => {
  let goi = 0;
  const p = dungPhien({ now: () => 0, getGroupInfo: async () => { goi += 1; return {}; } });
  await p.manager.restore('acc', { cookie: {}, imei: 'a', userAgent: 'ua' });
  await p.gui({ type: 0, threadId: 'khach-1', data: { msgId: 'r1', uidFrom: 'khach-1', content: 'hi' } });
  assert.equal(goi, 0);
  assert.equal(p.daNhan.length, 1);
});
