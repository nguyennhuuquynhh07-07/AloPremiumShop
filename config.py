import os

# Tự động nạp file .env nếu tồn tại (hỗ trợ cả môi trường Local và Render /etc/secrets/.env)
candidate_env_paths = [
    os.path.join(os.path.dirname(__file__), ".env"),
    os.path.join(os.getcwd(), ".env"),
    "/etc/secrets/.env",
]
for env_path in candidate_env_paths:
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
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
def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Thiếu biến môi trường bắt buộc: {name}")
    return value


BOT_TOKEN = _required_env("TELEGRAM_BOT_TOKEN")
admin_ids_raw = os.getenv("ADMIN_IDS", os.getenv("ADMIN_ID", "")).strip()
if not admin_ids_raw:
    raise RuntimeError("Thiếu biến môi trường bắt buộc: ADMIN_IDS hoặc ADMIN_ID")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_raw.split(",") if x.strip()]
SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "")
SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://alopremium.shop").strip()
ZALO_GROUP_URL = os.getenv("ZALO_GROUP_URL", "").strip()
ZALO_GROUP_QR = os.getenv("ZALO_GROUP_QR", "zalo_group_qr.png").strip()
ADMIN_PIN = _required_env("ADMIN_PIN")

# ============================================================
#  2. CẤU HÌNH THANH TOÁN (VIETQR)
# ============================================================
BANK_ID = os.getenv("BANK_CODE", "").strip()
BANK_CODE = BANK_ID
BANK_NAME = os.getenv("BANK_NAME", "").strip()
ACCOUNT_NO = os.getenv("BANK_ACCOUNT", "").strip()
BANK_ACCOUNT = ACCOUNT_NO
ACCOUNT_NAME = os.getenv("ACCOUNT_HOLDER", "").strip()
ACCOUNT_HOLDER = ACCOUNT_NAME
PRICE_VND = int(os.getenv("PRICE_VND", "200000"))
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "False").lower() in ("true", "1", "yes")
SEPAY_API_TOKEN = _required_env("SEPAY_API_TOKEN")

# ============================================================
#  3. CẤU HÌNH API CTV (locket.2707226.xyz) - GÓI LOCKET & SPOTIFY
# ============================================================
SECRET_KEY = _required_env("SECRET_KEY")
PUBLIC_KEY = _required_env("PUBLIC_KEY")
API_KEY = SECRET_KEY
API_BASE_URL = (os.getenv("API_BASE_URL", "https://locket.2707226.xyz") or "https://locket.2707226.xyz").strip().rstrip("/")

DNS_BASE_URL = os.getenv("DNS_BASE_URL", "").strip()
DNS_SLUG = os.getenv("DNS_SLUG", "").strip()
DNS_COMBO_URL = os.getenv("DNS_COMBO_URL", f"{DNS_BASE_URL}/{DNS_SLUG}" if DNS_BASE_URL and DNS_SLUG else "https://doh.2707226.xyz/alopremiumshop").strip()

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
            "test": {"label": "Test 3 Ngày", "packageCode": "LKGT3D",   "price": 5000, "durationDays": 3, "priceCoin": 0},
            "6m":   {"label": "6 Tháng",     "packageCode": "LKG6M",    "price": 40000},
            "1y":   {"label": "1 Năm",       "packageCode": "LKG1Y",    "price": 60000},
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "LKGVV",    "price": 160000},
        },
    },
    "spotify": {
        "name": "Spotify Premium",
        "emoji": "🎵",
        "service": "spotify",
        "description": "Nghe nhạc không giới hạn, không quảng cáo, tải nhạc offline – Spotify Premium DNS.",
        "plans": {
            "test": {"label": "Test 3 Ngày", "packageCode": "SPT",      "price": 5000, "durationDays": 3, "priceCoin": 0},
            "6m":   {"label": "6 Tháng",     "packageCode": "SP6M",     "price": 40000},
            "1y":   {"label": "1 Năm",       "packageCode": "SPOTIFY1Y", "price": 60000},
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "SPVV",      "price": 180000},
        },
    },
    "locket_spotify": {
        "name": "Combo Duo VIP (Locket + Spotify)",
        "emoji": "👑",
        "service": "combo",
        "description": "Trọn bộ Locket Gold VIP & Spotify Premium – Tiết kiệm tới 81.000đ, kích hoạt đồng thời cả hai dịch vụ.",
        "plans": {
            "6m":   {"label": "6 Tháng",     "packageCode": "COMBO6M",  "price": 65000},
            "1y":   {"label": "1 Năm",       "packageCode": "COMBO1Y",  "price": 99000},
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "COMBOVV",  "price": 259000},
        },
    },
    "locket_ai": {
        "name": "VIP ALL-IN-ONE (Locket Gold & AI Filters)",
        "emoji": "✨",
        "service": "locket_ai",
        "description": "Gói Vĩnh Viễn All-in-One: Locket Gold, AI Filters, Spotify, SoundCloud Go+, YouTube Premium.",
        "plans": {
            "ltm":  {"label": "Vĩnh Viễn",   "packageCode": "VIP_ALLINONE", "price": 250000},
        },
    },
}

VIP_DOWNLOAD_URL = "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1"
STUDIO_CAPTION_BASE_URL = "https://locket.jayteam.click/caption.html?u="
STUDIO_CAPTION_PRICE = 10000
FILTER_TOPUP_PACKS = {
    "20":  {"label": "Gói 20 Lượt Filter AI",  "turns": 20,  "price": 7000},
    "50":  {"label": "Gói 50 Lượt Filter AI",  "turns": 50,  "price": 17000},
    "100": {"label": "Gói 100 Lượt Filter AI", "turns": 100, "price": 33000},
}
FREE_CAPTION_QUOTA = 5
CAPTION_TOPUP_PACKS = {
    "10": {"label": "Gói +10 Caption VIP", "captions": 10, "price": 5000},
    "30": {"label": "Gói +30 Caption VIP", "captions": 30, "price": 10000},
}

# ============================================================
#  6. ĐƯỜNG DẪN DỮ LIỆU
# ============================================================
DB_ORDERS = "data/orders.json"  
DB_STATS  = "data/stats.json"
