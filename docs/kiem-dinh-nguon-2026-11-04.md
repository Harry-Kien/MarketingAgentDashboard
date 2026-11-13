# Kiểm định mã nguồn ngày 04.11.2026

Bản ghi tại thời điểm kiểm tra, không phải chứng nhận production hay cam kết không còn lỗi chưa phát hiện.

Phạm vi: bản sửa cục bộ trên nhánh `codex/production-hardening-20261104`, nền commit `d85a9ff1bf10c8f232a5f0ac37ae5ac10a84ea90`. Chưa commit/push/deploy. Dữ liệu chưa theo dõi `data/bao-cao/` được giữ nguyên.

## Các lỗi đã xử lý

- Readiness đọc webhook Zalo OA trước khi mở DB, và crash khi mất DB: tự khởi tạo, báo CHẶN, không lộ chuỗi kết nối, vẫn in hết bảng.
- Pool DB còn được giữ sau lỗi schema/migration: đóng pool lỗi, chỉ công bố pool sau khi khởi tạo thành công.
- Tên hãng vận chuyển sai hoặc chế độ tắt tự rơi về mock: từ chối cấu hình không hợp lệ trước khi chạm DB/kho; tra cứu và webhook trả lỗi có kiểm soát.
- Proxy nhiều HTTP method sinh operationId trùng: không đưa proxy giao thức bên ngoài vào OpenAPI nghiệp vụ; giữ nguyên các quyền truy cập.
- Test watchdog gọi nhánh tunnel, backup và heartbeat thật: cô lập các tác dụng phụ ngoài miền đang kiểm.
- Test ký tự điều khiển bò vào submodule/vendor: cắt nhánh trước khi duyệt, không sửa mã upstream.
- Test client MCP phụ thuộc cách SDK cũ công khai nội dung ngoại lệ: dùng lỗi giao thức thật để tiếp tục kiểm chốt quét injection ở nhánh lỗi.
- Chế độ `eval_nhieu_luot --kho` vẫn chạm DB và chấm câu giả như chất lượng AI: chế độ khô hoàn toàn ngoại tuyến, ghi rõ chỉ kiểm bộ chạy, không sinh điểm đánh giá AI.
- Vá dependency trực tiếp và gián tiếp; ghim các phiên bản an toàn để pip không giữ bản cũ chỉ vì nó vẫn thoả điều kiện của gói cha.
- CI quét bảo mật thành job độc lập, bỏ việc cho qua lỗi CVE; cố định runner Ubuntu 24.04 và cập nhật Actions chính thức.

Các lỗi có test hồi quy tương ứng. Các test mới cho readiness, pool DB, OpenAPI, cấu hình hãng và CLI evaluator đã được quan sát thất bại trước khi sửa.

## Bằng chứng

| Kiểm tra | Kết quả và giới hạn |
|---|---|
| Bản mã sạch, không `.env`/catalog thật/submodule | 3910 passed, 5 skipped; không lỗi. `output/hardening-clean.xml`, `output/hardening-clean.log`. |
| Nghiệm thu nghiệp vụ | 18 kịch bản trên app đầy đủ và PostgreSQL thật đều đạt trong bản mã sạch. Không gọi provider/model trả phí. |
| Evaluator sau sửa | 43 test đạt ở cả workspace và bản mã sạch; chạy khô hết 12 kịch bản/43 lượt, không DB/model. |
| Mã nguồn kèm coverage, lượt tuần tự cuối | 3913 passed, 3 skipped, không lỗi; coverage 74,02% (sàn 70%). `output/hardening-final.xml`, `output/hardening-serial.log`, `output/coverage-hardening-final.xml`. |
| Ruff / Mypy / cú pháp | Ruff sạch; Mypy không lỗi trong 198 file; JavaScript và Bash triển khai parse được. |
| Dependency | `pip check` đạt; `pip-audit --strict` không phát hiện CVE ở môi trường mới và môi trường local sau cập nhật. Không phải quét lỗ hổng hệ điều hành/container base. |
| Sidecar | 18/18 test trên local và ngay trong image Node 22, npm audit không phát hiện lỗ hổng. |
| Trình duyệt | Đăng nhập tài khoản tổng hợp, điều hướng đủ 17 màn hình ở 1440px và 390px; không pageerror, HTTP 5xx hoặc tràn ngang. DB trống riêng, không phải nghiệm thu dữ liệu/tài khoản khách thật. |
| Image Linux | App và sidecar đều build thành công. App import 197 module, khởi động với PostgreSQL thử, `/healthz` 200 và UID 10001. Sidecar `/healthz` 200. |
| Điều kiện CI chạy local | 27 test Postgres/JavaScript đạt khi bật biến CI. Chưa có lượt GitHub Actions cho bản sửa chưa push này. |

Ảnh và báo cáo trình duyệt: `output/playwright/hardening/desktop.png`, `mobile.png`, `report.json`.

Image thử: `cskh-app:validation-20261104`, `cskh-sidecar:validation-20261104`; log ở `output/hardening-build-*.log`. Các image không mang `.env`/database cửa hàng.

Lượt PostgreSQL chuyên dụng dùng container riêng, tmpfs, tắt fsync/synchronous_commit/full_page_writes để giảm chi phí đĩa cho DB thử tạo/xoá liên tục. Đây là bằng chứng về logic SQL, quyền, transaction và migration; không phải thử mất điện hay độ bền ổ đĩa production.

Lượt chạy đồng thời ban đầu có lỗi teardown `WinError 10055` (thiếu buffer/socket Windows), mặc dù các assertion nghiệp vụ đạt và coverage 74,02%. Tám test thuộc nhóm liên quan chạy lại đều đạt. Lượt tuần tự cuối chạy toàn bộ từ đầu, không lỗi, được dùng làm kết quả chốt.

Ba skip của lượt cuối: hai phép kiểm chỉ chạy khi có biến CI, và phép kiểm chặn dữ liệu mẫu lên ERP thật chủ động bỏ qua vì catalog local đã là dữ liệu thật. Nhóm CI đã được chạy riêng với biến CI và đạt; không bỏ qua test PostgreSQL. Năm skip ở bản mã sạch gồm hai phép kiểm CI, ca chặn dữ liệu mẫu không có catalog, và hai ca cần lịch sử eval không đi theo repo.

Còn 373 cảnh báo deprecation trong lượt đầy đủ, chủ yếu các fixture kiểm thử cũ dùng `on_event` và alias của thư viện. Không có warning trùng operationId sau sửa. Đây không phải bằng chứng rằng code đã được kiểm 100%: coverage thực tế là 74,02%.

Báo cáo audit máy đọc được: `output/hardening-audit.json` (114 gói Python trong môi trường kiểm định, 0 advisory) và `output/hardening-node-audit.json` (0 vulnerability).

## Khi có hạ tầng và tài khoản nhà cung cấp

Chưa thực hiện: chạy installer trên VPS Ubuntu thật; domain/TLS production; nhận/gửi/media trên Zalo/Meta thật; ERP thật; vận chuyển thật; backup mã hoá ngoài VPS và phục hồi từ bản đó; giám sát bên ngoài; diễn tập rollback/cutover; đánh giá model trả phí và tải thực tế.

Các mục này cần môi trường/tài khoản hiện chưa có. Không dùng dữ liệu mô phỏng để xác nhận chúng đã đạt. Tiếp tục theo `docs/len-vps.md`, chạy readiness và nghiệm thu từng provider trước khi nhận traffic khách.
