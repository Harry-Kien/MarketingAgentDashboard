/**
 * Đọc kích thước ảnh từ chính vài byte đầu file.
 *
 * VÌ SAO CẦN
 * ----------
 * `zca-js` bắt buộc có `imageMetadataGetter` khi gửi ảnh từ Node: nó cần
 * width/height/size để dựng khung xem trước bên Zalo. Trên trình duyệt thư
 * viện tự đọc được từ thẻ <img>; ở Node thì không có DOM nên phải tự cấp.
 *
 * Thiếu nó thì mọi lần gửi ảnh đều ném:
 *     Missing `imageMetadataGetter`. Please provide it in the Zalo object options.
 *
 * Đã xảy ra thật: một tin gửi ảnh sản phẩm cho khách thử 8 lần rồi chết
 * trong hàng đợi, và khách không bao giờ nhận được ảnh.
 *
 * VÌ SAO TỰ ĐỌC, KHÔNG THÊM THƯ VIỆN
 * -----------------------------------
 * Sidecar này đã mang rủi ro điều khoản của Zalo; thêm một phụ thuộc npm là
 * thêm bề mặt chuỗi cung ứng cho đúng tiến trình đang giữ phiên đăng nhập
 * của chủ shop. Kích thước ảnh nằm ngay trong vài chục byte đầu file — đọc
 * trực tiếp rẻ hơn nhiều so với kéo cả một thư viện xử lý ảnh về.
 *
 * TRẢ null KHI KHÔNG ĐỌC ĐƯỢC, KHÔNG ĐOÁN
 * ----------------------------------------
 * `zca-js` ném lỗi rõ ràng khi nhận null. Đoán bừa 800x600 thì Zalo dựng
 * khung xem trước sai tỉ lệ, ảnh hiện méo hoặc bị cắt — hỏng theo kiểu khách
 * nhìn thấy mà hệ thống không biết.
 */
import fs from 'node:fs/promises';

/** PNG: sau 8 byte chữ ký là chunk IHDR, width/height là uint32 big-endian. */
function doPng(b) {
  if (b.length < 24) return null;
  const chuKy = b.subarray(0, 8);
  if (chuKy.toString('hex') !== '89504e470d0a1a0a') return null;
  if (b.subarray(12, 16).toString('ascii') !== 'IHDR') return null;
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

/**
 * JPEG: phải DUYỆT QUA các đoạn, không đọc offset cố định.
 *
 * Ảnh JPEG có thể mở đầu bằng EXIF, ICC profile, thumbnail — mỗi thứ một
 * đoạn dài ngắn khác nhau. Kích thước thật chỉ nằm trong đoạn SOF (Start Of
 * Frame). Ảnh chụp từ điện thoại gần như luôn có EXIF, nên đọc offset cứng
 * là sai với đúng loại ảnh khách hay gửi nhất.
 */
function doJpeg(b) {
  if (b.length < 4 || b[0] !== 0xff || b[1] !== 0xd8) return null;

  let i = 2;
  while (i + 3 < b.length) {
    if (b[i] !== 0xff) { i += 1; continue; }      // byte đệm, bỏ qua
    const dau = b[i + 1];
    if (dau === 0xff) { i += 1; continue; }
    // D0-D9 và 01 là đoạn KHÔNG có phần độ dài đi kèm.
    if ((dau >= 0xd0 && dau <= 0xd9) || dau === 0x01) { i += 2; continue; }

    const dai = b.readUInt16BE(i + 2);
    // SOF0..SOF15, trừ C4 (bảng Huffman), C8 (mở rộng), CC (bảng số học) —
    // ba cái đó dùng chung dải mã nhưng không phải khung ảnh.
    const laSof = dau >= 0xc0 && dau <= 0xcf
      && dau !== 0xc4 && dau !== 0xc8 && dau !== 0xcc;
    if (laSof) {
      if (i + 9 > b.length) return null;
      return { height: b.readUInt16BE(i + 5), width: b.readUInt16BE(i + 7) };
    }
    if (dai < 2) return null;                      // độ dài hỏng -> dừng
    i += 2 + dai;
  }
  return null;
}

/** GIF: width/height là uint16 little-endian ngay sau 6 byte chữ ký. */
function doGif(b) {
  if (b.length < 10) return null;
  const chuKy = b.subarray(0, 6).toString('ascii');
  if (chuKy !== 'GIF87a' && chuKy !== 'GIF89a') return null;
  return { width: b.readUInt16LE(6), height: b.readUInt16LE(8) };
}

/** WebP: ba biến thể VP8 / VP8L / VP8X, mỗi cái để kích thước một chỗ. */
function doWebp(b) {
  if (b.length < 30) return null;
  if (b.subarray(0, 4).toString('ascii') !== 'RIFF') return null;
  if (b.subarray(8, 12).toString('ascii') !== 'WEBP') return null;

  const loai = b.subarray(12, 16).toString('ascii');
  if (loai === 'VP8 ') {
    // 14 bit thấp là kích thước; 2 bit cao là tỉ lệ thu phóng.
    return { width: b.readUInt16LE(26) & 0x3fff, height: b.readUInt16LE(28) & 0x3fff };
  }
  if (loai === 'VP8L') {
    const n = b.readUInt32LE(21);
    return { width: (n & 0x3fff) + 1, height: ((n >> 14) & 0x3fff) + 1 };
  }
  if (loai === 'VP8X') {
    // Kích thước khung là số 24 bit little-endian, lưu dạng "giá trị trừ 1".
    const w = b[24] | (b[25] << 8) | (b[26] << 16);
    const h = b[27] | (b[28] << 8) | (b[29] << 16);
    return { width: w + 1, height: h + 1 };
  }
  return null;
}

const BO_DOC = [doPng, doJpeg, doGif, doWebp];

/** Kích thước ảnh từ buffer, hoặc null nếu không nhận ra định dạng. */
export function docKichThuoc(buffer) {
  if (!buffer || buffer.length < 10) return null;
  for (const doc of BO_DOC) {
    try {
      const kq = doc(buffer);
      // 0 hoặc số âm nghĩa là đọc trúng rác, không phải kích thước thật.
      if (kq && kq.width > 0 && kq.height > 0) return kq;
    } catch {
      // File cụt giữa chừng làm readUInt* ném. Thử bộ đọc tiếp theo.
    }
  }
  return null;
}

/**
 * Hàm `zca-js` gọi trước mỗi lần gửi ảnh.
 *
 * Chỉ đọc 64KB đầu: mọi định dạng trên đều để kích thước trong vài chục byte
 * đầu, còn ảnh sản phẩm thì có thể vài megabyte. Nạp cả file vào bộ nhớ cho
 * mỗi lần gửi là lãng phí ở đúng chỗ nằm trên đường trả lời khách.
 */
export async function layMetadataAnh(filePath) {
  let fh;
  try {
    const thongTin = await fs.stat(filePath);
    if (!thongTin.isFile() || thongTin.size === 0) return null;

    fh = await fs.open(filePath, 'r');
    const dem = Buffer.alloc(Math.min(65536, thongTin.size));
    await fh.read(dem, 0, dem.length, 0);

    const kt = docKichThuoc(dem);
    if (!kt) return null;
    return { width: kt.width, height: kt.height, size: thongTin.size };
  } catch {
    // File không tồn tại, không đọc được, hoặc hỏng. Trả null để `zca-js`
    // ném lỗi rõ ràng thay vì gửi đi một khung xem trước sai.
    return null;
  } finally {
    await fh?.close?.().catch(() => {});
  }
}
