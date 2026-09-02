/**
 * Đọc kích thước ảnh — thứ thiếu nó thì KHÔNG gửi được ảnh nào cho khách.
 *
 * Lỗi đã có thật trong hàng đợi:
 *     Missing `imageMetadataGetter`. Please provide it in the Zalo object options.
 * Một tin gửi ảnh sản phẩm thử 8 lần rồi chết, khách không nhận được gì.
 *
 * Test dựng byte thật của từng định dạng chứ không giả lập hàm đọc: chỗ dễ
 * sai nhất chính là offset và thứ tự byte, mà giả lập thì bỏ qua đúng chỗ đó.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { docKichThuoc, layMetadataAnh } from '../src/anh-metadata.mjs';

function png(w, h) {
  const b = Buffer.alloc(24);
  Buffer.from('89504e470d0a1a0a', 'hex').copy(b, 0);
  b.writeUInt32BE(13, 8);
  b.write('IHDR', 12, 'ascii');
  b.writeUInt32BE(w, 16);
  b.writeUInt32BE(h, 20);
  return b;
}

/** JPEG kèm một đoạn phụ trước SOF, giống hệt ảnh chụp từ điện thoại. */
function jpeg(w, h, { chenExif = false } = {}) {
  const phan = [Buffer.from([0xff, 0xd8])];
  if (chenExif) {
    const exif = Buffer.alloc(2 + 2 + 60);
    exif.writeUInt8(0xff, 0); exif.writeUInt8(0xe1, 1);
    exif.writeUInt16BE(62, 2);
    phan.push(exif);
  }
  const sof = Buffer.alloc(11);
  sof.writeUInt8(0xff, 0); sof.writeUInt8(0xc0, 1);
  sof.writeUInt16BE(8, 2);
  sof.writeUInt8(8, 4);
  sof.writeUInt16BE(h, 5);
  sof.writeUInt16BE(w, 7);
  phan.push(sof);
  return Buffer.concat(phan);
}

function gif(w, h) {
  const b = Buffer.alloc(10);
  b.write('GIF89a', 0, 'ascii');
  b.writeUInt16LE(w, 6);
  b.writeUInt16LE(h, 8);
  return b;
}

function webpVp8(w, h) {
  const b = Buffer.alloc(30);
  b.write('RIFF', 0, 'ascii');
  b.write('WEBP', 8, 'ascii');
  b.write('VP8 ', 12, 'ascii');
  b.writeUInt16LE(w, 26);
  b.writeUInt16LE(h, 28);
  return b;
}

test('đọc được PNG', () => {
  assert.deepEqual(docKichThuoc(png(1200, 800)), { width: 1200, height: 800 });
});

test('đọc được JPEG', () => {
  assert.deepEqual(docKichThuoc(jpeg(640, 480)), { width: 640, height: 480 });
});

test('JPEG có EXIF vẫn đọc đúng — không dùng offset cứng', () => {
  // Ảnh chụp từ điện thoại gần như luôn có EXIF trước SOF. Đọc offset cố
  // định sẽ trúng giữa khối EXIF và trả ra số rác.
  assert.deepEqual(
    docKichThuoc(jpeg(3024, 4032, { chenExif: true })),
    { width: 3024, height: 4032 },
  );
});

test('đọc được GIF', () => {
  assert.deepEqual(docKichThuoc(gif(320, 240)), { width: 320, height: 240 });
});

test('đọc được WebP', () => {
  assert.deepEqual(docKichThuoc(webpVp8(1024, 768)), { width: 1024, height: 768 });
});

test('định dạng lạ trả null, KHÔNG đoán bừa', () => {
  // Đoán 800x600 thì Zalo dựng khung xem trước sai tỉ lệ: ảnh hiện méo hoặc
  // bị cắt — hỏng theo kiểu khách nhìn thấy mà hệ thống không biết.
  assert.equal(docKichThuoc(Buffer.from('day khong phai anh')), null);
});

test('file cụt giữa chừng không làm nổ hàm', () => {
  assert.equal(docKichThuoc(png(100, 100).subarray(0, 14)), null);
});

test('kích thước 0 bị coi là không đọc được', () => {
  assert.equal(docKichThuoc(png(0, 0)), null);
});

test('layMetadataAnh trả đủ width, height và size của file thật', async () => {
  const thu = path.join(os.tmpdir(), `thu-anh-${Date.now()}.png`);
  const noiDung = Buffer.concat([png(500, 400), Buffer.alloc(2048)]);
  await fs.writeFile(thu, noiDung);
  try {
    assert.deepEqual(await layMetadataAnh(thu), {
      width: 500, height: 400, size: noiDung.length,
    });
  } finally {
    await fs.unlink(thu).catch(() => {});
  }
});

test('file không tồn tại trả null chứ không ném', async () => {
  assert.equal(await layMetadataAnh('/khong/co/file/nay.png'), null);
});

test('file rỗng trả null', async () => {
  const thu = path.join(os.tmpdir(), `thu-rong-${Date.now()}.png`);
  await fs.writeFile(thu, Buffer.alloc(0));
  try {
    assert.equal(await layMetadataAnh(thu), null);
  } finally {
    await fs.unlink(thu).catch(() => {});
  }
});
