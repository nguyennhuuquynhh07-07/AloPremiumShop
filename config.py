import os

# Tự động nạp file .env nếu tồn tại
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

# ============================================================
#  1. CẤU HÌNH BOT TELEGRAM & ADMIN
# ============================================================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9067929792:AAFA3a7hUEemQhX73uqnACaAaxi6qguihFQ")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "8313153487")).split(",") if x.strip()]
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "HeyLocket")

# ============================================================
#  2. CẤU HÌNH THANH TOÁN (VIETQR)
# ============================================================
BANK_ID = os.getenv("BANK_CODE", "TPB")
BANK_CODE = BANK_ID
BANK_NAME = os.getenv("BANK_NAME", "TPBank")
ACCOUNT_NO = os.getenv("BANK_ACCOUNT", "34528022007")
BANK_ACCOUNT = ACCOUNT_NO
ACCOUNT_NAME = os.getenv("ACCOUNT_HOLDER", "NGUYEN NHU QUYNH")
ACCOUNT_HOLDER = ACCOUNT_NAME
PRICE_VND = int(os.getenv("PRICE_VND", "200000"))
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "False").lower() in ("true", "1", "yes")
SEPAY_API_TOKEN = os.getenv("SEPAY_API_TOKEN", "")  # Tùy chọn: Token SePay để tự động duyệt chuyển khoản

# ============================================================
#  3. CẤU HÌNH API CTV (locket.2707226.xyz) - GÓI LOCKET & SPOTIFY
# ============================================================
SECRET_KEY = os.getenv("SECRET_KEY", "sk_19ad928a9bb4379792503b27e04e2f3d8533ddfe8a7727a9757344edd16a99e6")
PUBLIC_KEY = os.getenv("PUBLIC_KEY", "pk_5979f17ec3827247e8c5a5aef88561481d1e6c15f74f4d0fb9328b2a7b50a035")
API_KEY = SECRET_KEY
API_BASE_URL = os.getenv("API_BASE_URL", "https://locket.2707226.xyz")

DNS_BASE_URL = os.getenv("DNS_BASE_URL", "https://doh.2707226.xyz")
DNS_SLUG = os.getenv("DNS_SLUG", "nonoqy")

# ============================================================
#  4. CẤU HÌNH GÓI SIÊU VIP 3-IN-1 (LOCKET + SPOTIFY + YOUTUBE 2099)
# ============================================================
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "https://160-191-242-70.sslip.io")
STATUS_JSON_PATH = os.path.join(os.path.dirname(__file__), "status.json")

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

# ============================================================
#  5. DANH SÁCH 3 DỊCH VỤ & BẢNG GIÁ
# ============================================================
PRODUCTS = {
    "locket": {
        "name": "Locket Gold VIP",
        "emoji": "🪄",
        "service": "locket",
        "description": "Mở khoá toàn bộ tính năng Locket Gold – Widget ảnh live trên màn hình chính.",
        "plans": {
            "test": {"label": "Test 1 Ngày", "packageCode": "LKGT3D",   "price": 5000},
            "6m":   {"label": "6 Tháng",     "packageCode": "LKG6M",    "price": 40000},
            "1y":   {"label": "1 Năm",       "packageCode": "LKG1Y",    "price": 60000},
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "LKGVV",    "price": 149000},
        },
    },
    "spotify": {
        "name": "Spotify Premium",
        "emoji": "🎵",
        "service": "spotify",
        "description": "Nghe nhạc không giới hạn, không quảng cáo, tải nhạc offline – Spotify Premium DNS.",
        "plans": {
            "test": {"label": "Test 1 Ngày", "packageCode": "SPT",      "price": 5000},
            "6m":   {"label": "6 Tháng",     "packageCode": "SP6M",     "price": 40000},
            "1y":   {"label": "1 Năm",       "packageCode": "SPOTIFY1Y", "price": 60000},
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "SPVV",      "price": 160000},
        },
    },
    "combo3in1": {
        "name": "Siêu VIP 3-in-1",
        "emoji": "👑",
        "service": "combo3in1",
        "description": "Gói cao cấp nhất: Kích hoạt Locket Gold 2099 + Spotify Premium + YouTube Premium (Chặn quảng cáo & PiP nền).",
        "plans": {
            "ltm":  {"label": "Trọn Gói Vĩnh Viễn", "packageCode": "VIP3IN1", "price": 200000},
        },
    },
}

# ============================================================
#  6. ĐƯỜNG DẪN DỮ LIỆU
# ============================================================
DB_ORDERS = "data/orders.json"
DB_STATS  = "data/stats.json"
