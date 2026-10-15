#!/bin/sh
# Chép dữ liệu mặc định của image sang volume của cửa hàng — CHỈ tệp còn
# thiếu, không bao giờ ghi đè.
#
# Vì sao: /app/data là volume riêng từng cửa hàng (catalog thật, tệp khách
# gửi, sao lưu). Gắn volume rỗng là che mất ảnh sản phẩm mẫu, gói kỹ năng
# và bản .example mà mã có đường lui tới — app vẫn lên nhưng thiếu dữ liệu,
# đúng kiểu hỏng im lặng. Ghi đè thì xoá mất catalog thật của cửa hàng.
set -eu

if [ -d /app/data_mac_dinh ]; then
  cp -rn /app/data_mac_dinh/. /app/data/ 2>/dev/null || true
fi
mkdir -p /app/data/uploads

exec "$@"
