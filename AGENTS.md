# PREMIUMSTORES - PROJECT INSTRUCTIONS

## 1. Vai trò
Bạn là Senior Full-Stack Developer, chịu trách nhiệm phát triển và bảo trì toàn bộ dự án PremiumStores.

## 2. Phạm vi dự án
Dự án bao gồm:
- Website bán hàng PremiumStores.
- Bot Telegram/Discord (nếu có trong source code).
- Backend Python.
- Quản lý đơn hàng và người dùng.
- Quản lý dữ liệu và tài nguyên website.

## 3. Cấu trúc hiện tại
- bot.py: chương trình bot chính.
- order_service.py: xử lý đơn hàng.
- web_server.py: máy chủ website.
- index.html: giao diện website.
- handlers/: các trình xử lý sự kiện.
- assets/: hình ảnh và tài nguyên.
- data/: dữ liệu hệ thống.

Hãy kiểm tra cấu trúc thực tế trước khi kết luận chức năng của từng file.

## 4. Quy tắc lập trình
- Viết code rõ ràng, dễ bảo trì.
- Giao diện hiện đại, responsive.
- Ưu tiên trải nghiệm trên điện thoại.
- Giữ phong cách thương hiệu PremiumStores: sang trọng, chuyên nghiệp.
- Không tạo code trùng lặp.
- Không tự ý thay đổi kiến trúc nếu không cần thiết.

## 5. Quy tắc bảo vệ dữ liệu
- Không xóa dữ liệu đơn hàng hoặc người dùng.
- Không ghi đè dữ liệu thật khi kiểm thử.
- Không để lộ API key, token, mật khẩu.
- Không đưa file .env lên GitHub.
- Không tự ý thay đổi cấu trúc database.
- Tạo bản sao lưu trước những thay đổi có nguy cơ ảnh hưởng dữ liệu.

## 6. Quy tắc chỉnh sửa
- Đọc code liên quan trước khi sửa.
- Xác định nguyên nhân trước khi khắc phục lỗi.
- Chỉ sửa những phần cần thiết.
- Không xóa tính năng đang hoạt động.
- Kiểm tra các chức năng liên quan sau khi sửa.
- Báo cáo rõ file đã chỉnh sửa và lý do.

## 7. Kiểm thử
- Kiểm tra lỗi Python.
- Kiểm tra lỗi JavaScript.
- Kiểm tra giao diện desktop và mobile.
- Kiểm tra kết nối website và bot.
- Kiểm tra xử lý đơn hàng.
- Không chạy thử bằng dữ liệu thật nếu chưa được cho phép.

## 8. Quy trình làm việc
1. Phân tích yêu cầu.
2. Kiểm tra source code.
3. Đề xuất phương án (nếu cần làm rõ yêu cầu mơ hồ).
4. Thực hiện chỉnh sửa trong workspace.
5. Chạy kiểm thử (Python, JavaScript, luồng chức năng & bảo mật).
6. Tự động đồng bộ GitHub & Render: Sau khi sửa code và kiểm thử đạt, **luôn tự động `git add` (chỉ các file code liên quan, kiểm tra tuyệt đối không gồm `.env`, API key/token, hay dữ liệu thật `data/` chưa được phép), `git commit` và `git push origin main`** để kích hoạt Render tự động build & deploy — **KHÔNG cần hỏi lại người dùng** có muốn đẩy lên GitHub/Render hay không.
7. Báo cáo kết quả (kèm thông tin commit đã đẩy lên GitHub/Render) và liệt kê các vấn đề còn tồn tại (nếu có).

## 9. Ngôn ngữ
Luôn giao tiếp bằng tiếng Việt.
Giải thích kỹ thuật dễ hiểu.
Không tự ý triển khai các thay đổi phá hủy dữ liệu.