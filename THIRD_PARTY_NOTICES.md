# Third-party notices

Kien Omnichannel chứa hoặc có thể chạy cùng các thành phần bên thứ ba. File này
được giữ cho mục đích tuân thủ giấy phép; tên bên thứ ba không phải thương hiệu
của sản phẩm.

- `zca-js` 2.1.2 được dùng trong sidecar Zalo cá nhân. Giấy phép đi kèm package
  được cài trong `connectors/zalo-personal-sidecar/node_modules/zca-js/LICENSE`.
- Hai git submodule tương thích cũ vẫn được giữ tạm thời cho migration/canary.
  Mỗi submodule giữ nguyên lịch sử và giấy phép riêng trong thư mục của nó;
  dashboard native không nhúng giao diện của các thành phần này.
- Các package Python/Node và Docker image khác tuân theo license tại upstream
  tương ứng và lockfile/version pin của repository.

Khi phân phối source hoặc image, phải kèm license text bắt buộc của từng thành
phần và không xóa copyright notice. Việc custom giao diện/tên sản phẩm không
chuyển quyền sở hữu mã bên thứ ba sang dự án này.
