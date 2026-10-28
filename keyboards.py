"""
keyboards.py – Tất cả inline keyboard chuyên nghiệp của bot
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import PRODUCTS, SUPPORT_USERNAME


# ── MENU CHÍNH ────────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for pk, pv in PRODUCTS.items():
        rows.append([InlineKeyboardButton(
            f"{pv['emoji']} {pv['name']} (Xem bảng giá)",
            callback_data=f"product:{pk}"
        )])
    rows.append([
        InlineKeyboardButton("👤 Tài khoản của tôi", callback_data="my_account"),
        InlineKeyboardButton("📦 Đơn hàng đã mua",  callback_data="my_orders"),
    ])
    rows.append([
        InlineKeyboardButton("🌐 Đổi ngôn ngữ",    callback_data="cmd_setlang"),
        InlineKeyboardButton("💬 Hỗ trợ CSKH",      callback_data="support"),
    ])
    return InlineKeyboardMarkup(rows)


# ── CHỌN GÓI ─────────────────────────────────────────────────────────────────

def plan_kb(product_key: str) -> InlineKeyboardMarkup:
    plans = PRODUCTS[product_key]["plans"]
    rows = []
    for pk, pv in plans.items():
        from utils import fmt_price
        rows.append([InlineKeyboardButton(
            f"⚡ {pv['label']} ➔ {fmt_price(pv['price'])}",
            callback_data=f"plan:{product_key}:{pk}"
        )])
    rows.append([
        InlineKeyboardButton("🔙 Đổi dịch vụ khác", callback_data="back_products"),
        InlineKeyboardButton("🏠 Về trang chủ",      callback_data="back_main")
    ])
    return InlineKeyboardMarkup(rows)


# ── ĐANG Ở BƯỚC NHẬP USERNAME ────────────────────────────────────────────────

def back_to_plan_kb(product_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Đổi gói khác",  callback_data=f"product:{product_key}"),
            InlineKeyboardButton("🏠 Về trang chủ", callback_data="back_main")
        ]
    ])


# ── XÁC NHẬN THANH TOÁN (Khách) ──────────────────────────────────────────────

def payment_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tôi đã chuyển khoản", callback_data=f"paid:{order_id}")],
        [
            InlineKeyboardButton("❌ Huỷ đơn hàng",   callback_data=f"cancel:{order_id}"),
            InlineKeyboardButton("🏠 Về trang chủ",  callback_data="back_main")
        ],
    ])


def confirm_buy_kb(order_id: str) -> InlineKeyboardMarkup:
    return payment_kb(order_id)


# ── SAU KHI GỬI XÁC NHẬN HOẶC HOÀN THÀNH ─────────────────────────────────────

def success_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Tải file .mobileconfig", callback_data="get_mobileconfig"),
            InlineKeyboardButton("💬 Hỗ trợ kỹ thuật", callback_data="support"),
        ],
        [
            InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")
        ]
    ])


def orders_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛒 Mua gói dịch vụ", callback_data="back_products"),
            InlineKeyboardButton("🏠 Về trang chủ",   callback_data="back_main")
        ]
    ])


def support_kb() -> InlineKeyboardMarkup:
    val = SUPPORT_USERNAME.lstrip("@").strip()
    rows = []
    if val and val != "yoursupport":
        if val.isdigit():
            rows.append([InlineKeyboardButton(f"💬 Nhắn Zalo ({val})", url=f"https://zalo.me/{val}")])
            rows.append([InlineKeyboardButton("✈️ Nhắn Telegram hỗ trợ", url=f"https://t.me/+84{val[1:] if val.startswith('0') else val}")])
        else:
            rows.append([InlineKeyboardButton(f"💬 Nhắn tin hỗ trợ (@{val})", url=f"https://t.me/{val}")])
    rows.append([InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


# ── TÀI KHOẢN (Account) ───────────────────────────────────────────────────────

def account_kb(dns_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📥 Tải file .mobileconfig (1 chạm)", callback_data="get_mobileconfig"),
        ],
        [
            InlineKeyboardButton("🌐 Cài qua Safari", url=dns_link),
            InlineKeyboardButton("📦 Đơn đã mua", callback_data="my_orders"),
        ],
        [
            InlineKeyboardButton("🛒 Mua thêm gói", callback_data="back_products"),
            InlineKeyboardButton("🏠 Menu chính",   callback_data="back_main")
        ]
    ])


# ── ĐỔI NGÔN NGỮ (Language) ───────────────────────────────────────────────────

def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇻🇳 Tiếng Việt (Mặc định)", callback_data="lang:vi"),
            InlineKeyboardButton("🇬🇧 English",             callback_data="lang:en"),
        ],
        [InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")]
    ])


# ── TÀI LIỆU API & BẢNG MÃ LỖI ───────────────────────────────────────────────

def apidocs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Bảng Mã Lỗi HTTP", callback_data="apidocs:errors"),
            InlineKeyboardButton("💬 Hỗ trợ CTV",       callback_data="support"),
        ],
        [InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")]
    ])


def apierrors_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Xem Endpoints API", callback_data="apidocs:overview"),
            InlineKeyboardButton("💬 Hỗ trợ CTV",       callback_data="support"),
        ],
        [InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")]
    ])



# ── DUYỆT ĐƠN HÀNG (Admin) ───────────────────────────────────────────────────

def admin_approval_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt & Kích hoạt", callback_data=f"admin_approve:{order_id}"),
            InlineKeyboardButton("❌ Từ chối",           callback_data=f"admin_reject:{order_id}"),
        ]
    ])


# ── ADMIN ─────────────────────────────────────────────────────────────────────

def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Thống kê (/stats)", callback_data="admin:stats"),
            InlineKeyboardButton("📋 Đơn gần đây (/orders)", callback_data="admin:recent"),
        ],
        [
            InlineKeyboardButton("👥 Người dùng (/users)", callback_data="admin:users_list"),
            InlineKeyboardButton("🪙 Token CTV (/tokens)", callback_data="admin:balance"),
        ],
        [
            InlineKeyboardButton("🔍 Tìm kiếm (/find)",   callback_data="admin:find_menu"),
            InlineKeyboardButton("🔄 Reset Spotify (/rs)", callback_data="admin:reset_menu"),
        ],
        [
            InlineKeyboardButton("📢 Gửi broadcast (/noti)", callback_data="admin:broadcast"),
            InlineKeyboardButton("💳 Test Bank (/checkbank)", callback_data="admin:checkbank"),
        ],
        [
            InlineKeyboardButton("🏷️ Mã giảm giá (/addcode)", callback_data="admin:codes"),
            InlineKeyboardButton("🏠 Về menu người dùng",      callback_data="back_main"),
        ]
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Quay lại Admin", callback_data="admin:menu")
    ]])


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")
    ]])
