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
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "9170943429:AAF6Hlu5qwSzMFHQpZZgLClQf450zcP6CZE")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "8313153487")).split(",") if x.strip()]
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "0345222802")
SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "https://t.me/nguyennhuquynh28")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "nguyennhuquynh28")
ADMIN_PIN = os.getenv("ADMIN_PIN", "2802")

# ============================================================
#  2. CẤU HÌNH THANH TOÁN (VIETQR)
# ============================================================
BANK_ID = os.getenv("BANK_CODE", "TPB")
BANK_CODE = BANK_ID
BANK_NAME = "TPBank" if BANK_ID == "TPB" else os.getenv("BANK_NAME", "TPBank")
ACCOUNT_NO = os.getenv("BANK_ACCOUNT", "34528022007")
BANK_ACCOUNT = ACCOUNT_NO
ACCOUNT_NAME = "NGUYEN NHU QUYNH" if ACCOUNT_NO == "34528022007" else os.getenv("ACCOUNT_HOLDER", "NGUYEN NHU QUYNH")
ACCOUNT_HOLDER = ACCOUNT_NAME
PRICE_VND = int(os.getenv("PRICE_VND", "200000"))
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "False").lower() in ("true", "1", "yes")
SEPAY_API_TOKEN = os.getenv("SEPAY_API_TOKEN", "GUV55IMNQDTPTPZON8OXPHQUHD6FLY0JFNYBTB4CMRCVIAFJEWHGELCRUEZMLVXK")  # Tự động duyệt qua SePay API TPBank

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
#  4. DANH SÁCH DỊCH VỤ & BẢNG GIÁ (LOCKET & SPOTIFY)
# ============================================================
PRODUCTS = {
    "locket": {
        "name": "Locket Gold VIP",
        "emoji": "💛",
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
}

# ============================================================
#  6. ĐƯỜNG DẪN DỮ LIỆU
# ============================================================
DB_ORDERS = "data/orders.json"
DB_STATS  = "data/stats.json"
