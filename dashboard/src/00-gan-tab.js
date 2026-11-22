/* ---------------- sổ điểm gắn tab (GAN_TAB) ----------------
 *
 * Tệp ĐẦU TIÊN của app.js, cố ý chỉ có một dòng mã: mô-đun nào nằm ở tệp
 * sau cũng đăng ký được NGAY LÚC TẢI, không phụ thuộc thứ tự tên tệp.
 *
 *   window.GAN_TAB["ns-nhan-vien"] = (o, ctx) => { o.innerHTML = "…"; };
 *
 * Hợp đồng (01b-dieu-huong.js thực hiện):
 *   · Khoá là id của tab (cc-*, ai-*, ns-*, ht-*, cv-*) hoặc của một khe gắn
 *     bên trong tab (`data-gan="ai-co-ban-nha-cung-cap"`).
 *   · Hàm được gọi MỘT lần, lần đầu tab hiện ra, với một <div> mới làm chỗ
 *     vẽ và `ctx = { id, api, toast, esc, quyen }`.
 *   · Khi đã gắn, phần `.tab__goc` (nội dung mặc định) bị ẩn — các khối
 *     nằm ngoài `.tab__goc` thì ở lại. Mỗi lần tab hiện lại, khe phát sự
 *     kiện `tab:hien` để mô-đun tự làm mới nếu muốn.
 *   · Hàm ném lỗi thì nội dung mặc định hiện lại và người dùng được báo:
 *     một mô-đun hỏng không được biến cả tab thành trang trắng im lặng.
 */
window.GAN_TAB = window.GAN_TAB || {};
