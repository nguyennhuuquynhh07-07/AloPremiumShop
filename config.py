import os

# Tự động đọc file .env nếu có
env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_file):
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass

# Telegram Bot Token (Lấy từ @BotFather trên Telegram)
# Được nạp từ biến môi trường TELEGRAM_BOT_TOKEN hoặc file .env
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Cấu hình thanh toán
PRICE_VND = int(os.getenv("PRICE_VND", "200000"))
BANK_CODE = os.getenv("BANK_CODE", "Techcombank")    # Mã ngân hàng VietQR: Techcombank, MBBank, Vietcombank, ACB...
BANK_NAME = os.getenv("BANK_NAME", "Techcombank")
BANK_ACCOUNT = os.getenv("BANK_ACCOUNT", "")
ACCOUNT_HOLDER = os.getenv("ACCOUNT_HOLDER", "")
ADMIN_ID = os.getenv("ADMIN_ID", "")               # ID Telegram của Admin
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "False").lower() in ("true", "1", "yes")

# Tự động nhận diện thanh toán ngân hàng qua SePay.vn (Tùy chọn)
# Đăng ký tài khoản miễn phí tại https://sepay.vn để lấy API Token kết nối Techcombank
SEPAY_API_TOKEN = os.getenv("SEPAY_API_TOKEN", "")

# Máy chủ DNS Proxy & Ký profile iOS
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "https://160-191-242-70.sslip.io")

# File dữ liệu cache người dùng
STATUS_JSON_PATH = os.path.join(os.path.dirname(__file__), "status.json")

# Danh sách domain cần bypass qua DoH
MATCH_DOMAINS = [
    "api.revenuecat.com",
    "firebaseremoteconfig.googleapis.com",
    "spclient.wg.spotify.com",
    "wg.spotify.com",
    "apresolve.spotify.com",
    "gae2-spclient.spotify.com",
    "guc3-spclient.spotify.com",
    "gue1-spclient.spotify.com",
    "gew1-spclient.spotify.com",
    "guc3.spotify.com",
    "gue3.spotify.com",
    "gua3.spotify.com",
    "youtubei.googleapis.com",
    "googleads.g.doubleclick.net",
    "pagead2.googlesyndication.com",
    "static.doubleclick.net",
    "ad.youtube.com",
    "ads.youtube.com",
    "s0.2mdn.net",
]

# Chứng chỉ gốc Locket Gold Root CA (DER Base64)
CA_DER_B64 = (
    "MIIDejCCAmKgAwIBAgIJAPs4V/Q5JaaQMA0GCSqGSIb3DQEBCwUAMEoxCzAJBgNVBAYTAlVT"
    "MR0wGwYDVQQKDBRMb2NrZXQgR29sZCBVbmxvY2tlcjEcMBoGA1UEAwwTTG9ja2V0IEdvbGQg"
    "Um9vdCBDQTAeFw0yNjEwMTkwNjU4MDJaFw0zNjEwMTYwNjU4MDJaMEoxCzAJBgNVBAYTAlVT"
    "MR0wGwYDVQQKDBRMb2NrZXQgR29sZCBVbmxvY2tlcjEcMBoGA1UEAwwTTG9ja2V0IEdvbGQg"
    "Um9vdCBDQTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBAKDRQdnLjyznevdF+p8c"
    "zU7BiK+V3AlNV0kdijJ1guFtAWR8H4Gp/n9bYDReYgG1T1wULP/Ycin6jmEJgyHj7+Sdf+aW"
    "bdbSH9sJ88eNUSKBkQj7pM1FEzmtpn2sYYRBlpHyPq+DSN7F1SIxQjLxkcn/o2R4TBub/yAG"
    "ie8t0wUiplU3ERVPdOXXxp4zyVCUgsNqlPpPbu9bWvAPj/esglBfXsoxGs+RVWSpRBIZCu1q"
    "Uh/M42+pfiHMBnbtEHV2b3UPp9nrMG0jQfgILSGeBNYen1zp/kbQrn1yDExPL/JYTJrvUxLr"
    "DT2F6eTHE4mM64MrlcIWrM5VPr3jZ1gliW0CAwEAAaNjMGEwHQYDVR0OBBYEFAYsC40T2bhG"
    "a93UwuIsCKQJpuolMB8GA1UdIwQYMBaAFAYsC40T2bhGa93UwuIsCKQJpuolMA8GA1UdEwEB"
    "/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgGGMA0GCSqGSIb3DQEBCwUAA4IBAQASWfR8qZg2r0cW"
    "CQZ3BAKz05QQyU4s3mkb5VRWSDjCzwZjB6vzSZpa0uBzHK78iqDsBO5B6nYLGW/KByf9JTAS"
    "LVUv5biOCiuJ8feFyLIijbmQo2ZrUFCxc9W9fl66VC5CuCTLwMxzVqLPe0TppTSHTjhIKJAt"
    "vOKyn4z8AmRKuaYZmQ4jWUH+VTp6RLmWnXe3Q0XshC/sDuBUA4TIYKq/7XlPGHWKqGE0EILX"
    "OQ8honADNhMTM8DWBrFbgqOU5b0l/xWZuilmEHnXc2yO9d1/74DTbxgSlpC6OtwOg1wQR1xN"
    "4hA1mLUu3kdnJRBTMZ0TaoEqTMWcF8QRHfLXal81"
)
