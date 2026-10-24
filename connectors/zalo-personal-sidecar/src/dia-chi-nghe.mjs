// Sidecar được nghe ở địa chỉ nào.
//
// Mặc định CHỈ localhost: sidecar giữ phiên đăng nhập Zalo của cửa hàng, mở
// ra mạng là ai gửi được yêu cầu (dù có HMAC) cũng chạm được phiên đó.
//
// Ngoại lệ DUY NHẤT: trong container. Ở đó app gọi sidecar bằng tên dịch vụ
// qua mạng nội bộ của cửa hàng, nên sidecar PHẢI nghe trên giao diện của
// container (0.0.0.0) — và cổng không được publish ra máy chủ. Ngoại lệ
// phải được bật RÕ bằng ZALO_SIDECAR_TRONG_CONTAINER=1 (Dockerfile đặt);
// không bật thì vẫn nổ như cũ.
//
// Đo 24.10.2026: trước khi có ngoại lệ này, Dockerfile đặt 0.0.0.0 còn mã
// cấm mọi địa chỉ khác localhost — container sidecar khởi động lại vô hạn,
// tức Zalo cá nhân chết trên MỌI bản triển khai Docker. Test bằng runner
// giả không bắt được; chỉ lộ ra khi dựng thật.

const LOCALHOST = ['127.0.0.1', '::1', 'localhost'];

export function kiemDiaChiNghe(host, moiTruong = {}) {
  if (LOCALHOST.includes(host)) return host;
  if (moiTruong.ZALO_SIDECAR_TRONG_CONTAINER === '1' && host === '0.0.0.0') return host;
  throw new Error(
    'Sidecar chỉ được bind localhost (trong container: đặt ZALO_SIDECAR_TRONG_CONTAINER=1 '
    + 'và ZALO_SIDECAR_HOST=0.0.0.0, KHÔNG publish cổng)',
  );
}
