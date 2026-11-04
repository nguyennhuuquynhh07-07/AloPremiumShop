# Telegram Bot & Web Kích Hoạt Locket Gold VIP + Spotify Premium

Dự án chuyển đổi toàn bộ tính năng của giao diện Web kích hoạt DNS Locket Gold thành **Telegram Bot** tự động hóa 100%.

---

## 🔍 I. ĐÁNH GIÁ THỰC HƯ: WEB NÀY CÓ PHẢI KÍCH HOẠT LOCKET & SPOTIFY THẬT KHÔNG?

### 1. Cơ chế hoạt động thực tế (Bản chất kỹ thuật)
* **Đây KHÔNG PHẢI là kích hoạt bản quyền chính thức trên máy chủ của Locket hay Spotify.**
* **Nguyên lý thực tế:** Đây là phương pháp **Bypass phía thiết bị (Client-Side MITM Proxy qua DNS-over-HTTPS)**.
  1. **Với Locket:** Ứng dụng Locket dùng dịch vụ của bên thứ ba là RevenueCat (`api.revenuecat.com`) để kiểm tra thuê bao Gold. Khi cài cấu hình DNS và chứng chỉ Root CA (`Locket Gold Root CA`), lưu lượng mạng tới `api.revenuecat.com` bị chuyển hướng qua máy chủ proxy (`160.191.242.70`). Máy chủ này chặn yêu cầu và giả lập (spoofing) một phản hồi JSON khẳng định rằng tài khoản của bạn đã mua gói Gold VIP vĩnh viễn đến năm 2099. Nhờ đó, ứng dụng Locket trên máy mở khóa toàn bộ tính năng Gold.
  2. **Với Spotify:** Cấu hình DNS chặn các domain máy chủ quảng cáo của Spotify (`spclient.wg.spotify.com`,...) giúp hạn chế quảng cáo và can thiệp một số tính năng phát nhạc.
  3. **Với YouTube:** Cấu hình DNS chặn các máy chủ phân phối quảng cáo của Google/YouTube (`googleads.g.doubleclick.net`, `ad.youtube.com`, `static.doubleclick.net`), đồng thời hỗ trợ xem PiP (Picture-in-Picture) và nghe nhạc khi tắt màn hình ngay trên app iOS.

### 2. Ưu và nhược điểm
* **Ưu điểm:**
  * Không cần Jailbreak iPhone.
  * Dùng trực tiếp trên các ứng dụng gốc tải từ App Store.
  * Cài đặt 1 lần thông qua cấu hình `.mobileconfig`.
* **Nhược điểm & Rủi ro bảo mật:**
  * Phụ thuộc 100% vào máy chủ proxy của tác giả (`160.191.242.70`). Nếu máy chủ này sập hoặc đổi IP, tính năng VIP sẽ mất và có thể gây mất mạng trên các ứng dụng liên quan.
  * **Rủi ro Root CA:** Cài đặt chứng chỉ Root CA từ bên ngoài cho phép máy chủ proxy giải mã các gói tin HTTPS của các tên miền được chỉ định. Bạn nên cân nhắc khi sử dụng trên thiết bị chứa nhiều dữ liệu nhạy cảm.

---

## 🤖 II. TÍNH NĂNG CỦA TELEGRAM BOT

1. **Tạo Cấu Hình Tự Động:** Người dùng chỉ cần gửi username hoặc link Locket (`@username` hoặc `https://locket.cam/username`), bot sẽ tự giải mã UID 28 ký tự, tải avatar và sinh file cấu hình `.mobileconfig` gửi trực tiếp vào Telegram.
2. **Hỗ Trợ Ký Số CMS Xanh (iOS Verified):** Tải trực tiếp file profile đã ký số từ máy chủ proxy nếu server online, hoặc tự động fallback sinh profile XML tương thích 100% với iOS.
3. **Tra Cứu Tài Khoản (`/lookup <username>`):** Kiểm tra thông tin UID, tên hiển thị, ảnh đại diện Locket.
4. **Kiểm Tra Server (`/status`):** Theo dõi trạng thái máy chủ proxy, độ trễ mạng (ping ms) và số lượng tài khoản đã tạo.
5. **Hướng Dẫn Cài Đặt Chi Tiết (`/guide`):** Từng bước cài đặt cấu hình và bật tin cậy chứng chỉ trên iPhone.

---

## 🚀 III. HƯỚNG DẪN CÀI ĐẶT & CHẠY BOT

### Bước 1: Tạo Bot trên Telegram và lấy Token
1. Mở ứng dụng Telegram, tìm kiếm bot **[@BotFather](https://t.me/BotFather)**.
2. Gửi lệnh `/newbot`.
3. Nhập tên hiển thị cho bot và username của bot (phải kết thúc bằng chữ `bot`, ví dụ: `LocketGoldActivatorBot`).
4. `@BotFather` sẽ gửi cho bạn một mã **HTTP API Token** (dạng `123456789:ABCdefGhIJKlmNoPQRstuVWXyz`).

### Bước 2: Cấu hình Token vào dự án
* Mở file `.env.example`, đổi tên thành `.env` (hoặc tạo file mới tên `.env`).
* Dán token của bạn vào:
  ```env
  TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz
  ```
*(Hoặc bạn có thể mở file `config.py` và sửa trực tiếp dòng `BOT_TOKEN = "..."`)*

### Bước 3: Khởi chạy Bot
* **Trên Windows:** Chỉ cần nhấp đúp vào file `run_bot.bat`.
* **Hoặc bằng dòng lệnh Terminal/PowerShell:**
  ```bash
  pip install -r requirements.txt
  python bot.py
  ```

---

## 📱 IV. HƯỚNG DẪN DÀNH CHO NGƯỜI DÙNG IPHONE

1. Mở Telegram, vào chat với bot và gửi link/username Locket của bạn.
2. Bot gửi về thông tin kích hoạt kèm link tải và nút **📋 Copy Link Tải Hồ Sơ**.
3. Bấm nút copy (hoặc chạm vào dòng link) để sao chép link.
4. Mở trình duyệt **Safari** trên iPhone, dán link vào thanh địa chỉ và truy cập.
5. Safari sẽ hỏi _"Trang web này đang cố tải về một hồ sơ cấu hình. Bạn có muốn cho phép không?"_ -> Chọn **Cho phép** (Allow).
6. Mở **Cài đặt** (Settings) trên iPhone:
   * Chọn dòng **Đã tải về hồ sơ** ở đầu trang -> Nhấn **Cài đặt** (Install) -> Nhập passcode màn hình.
7. **Bật tin cậy chứng chỉ:**
   * Vào **Cài đặt** -> **Cài đặt chung** (General) -> **Giới thiệu** (About) -> **Cài đặt tin cậy chứng nhận** (Certificate Trust Settings).
   * Bật **XANH** công tắc cho chứng chỉ **Locket Gold Root CA**.
8. Mở Locket hoặc Spotify lên để trải nghiệm!

