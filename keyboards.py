"""
keyboards.py – Tất cả inline keyboard chuyên nghiệp của bot
Tích hợp copy 1 chạm, hướng dẫn iOS trực quan và điều khiển đơn hàng thông minh.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import config
from config import PRODUCTS, SUPPORT_USERNAME, SUPPORT_TELEGRAM, SUPPORT_PHONE


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
        InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide"),
        InlineKeyboardButton("💬 Hỗ trợ CSKH",          callback_data="support"),
    ])
    rows.append([
        InlineKeyboardButton("🌐 Đổi ngôn ngữ",        callback_data="cmd_setlang"),
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
            InlineKeyboardButton("📖 Hướng dẫn cài đặt", callback_data="show_guide"),
            InlineKeyboardButton("❌ Huỷ đơn hàng",       callback_data=f"cancel:{order_id}")
        ],
        [InlineKeyboardButton("🏠 Về trang chủ",         callback_data="back_main")],
    ])


def confirm_buy_kb(order_id: str) -> InlineKeyboardMarkup:
    return payment_kb(order_id)


# ── SAU KHI GỬI XÁC NHẬN HOẶC HOÀN THÀNH ─────────────────────────────────────

def pending_approval_kb() -> InlineKeyboardMarkup:
    """Bàn phím hiển thị khi khách bấm 'Tôi đã chuyển khoản' và đang chờ Admin duyệt.
    TUYỆT ĐỐI KHÔNG CÓ NÚT TẢI FILE / NHẬN DNS Ở ĐÂY."""
    rows = [
        [InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide")],
        [InlineKeyboardButton("💬 Hỗ trợ kỹ thuật", callback_data="support")],
        [InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(rows)


def success_kb(dns_link: str = None) -> InlineKeyboardMarkup:
    rows = []
    if dns_link:
        rows.append([
            InlineKeyboardButton("🌐 Mở Tải Trực Tiếp Safari", url=dns_link),
            InlineKeyboardButton("📋 Copy Link DNS", api_kwargs={"copy_text": {"text": dns_link}})
        ])
    rows.append([
        InlineKeyboardButton("📥 Tải file .mobileconfig", callback_data="get_mobileconfig"),
        InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide"),
    ])
    rows.append([
        InlineKeyboardButton("💬 Hỗ trợ kỹ thuật", callback_data="support"),
        InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")
    ])
    return InlineKeyboardMarkup(rows)


def orders_kb(has_done_order: bool = False, has_spotify: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_done_order:
        rows.append([InlineKeyboardButton("📥 Tải lại file cấu hình DNS", callback_data="get_mobileconfig")])
    if has_spotify:
        rows.append([InlineKeyboardButton("🔄 Reset thiết bị Spotify", callback_data="user_reset_spotify_menu")])
    rows.append([
        InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide"),
        InlineKeyboardButton("🛒 Mua thêm gói",         callback_data="back_products")
    ])
    rows.append([InlineKeyboardButton("🏠 Về trang chủ", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def support_kb() -> InlineKeyboardMarkup:
    tele_url = getattr(config, "SUPPORT_TELEGRAM", "https://t.me/nguyennhuquynh28")
    phone = getattr(config, "SUPPORT_PHONE", "0345222802")
    rows = [
        [
            InlineKeyboardButton("✈️ Chat Telegram (@nguyennhuquynh28)", url=tele_url),
            InlineKeyboardButton("💬 Chat Zalo", url=f"https://zalo.me/{phone}"),
        ],
        [InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide")],
        [InlineKeyboardButton("🏠 Về trang chủ", callback_data="back_main")],
    ]
    return InlineKeyboardMarkup(rows)


def account_kb(dns_link: str = None) -> InlineKeyboardMarkup:
    rows = []
    if dns_link:
        rows.append([
            InlineKeyboardButton("📋 Copy Link DNS Profile", api_kwargs={"copy_text": {"text": dns_link}})
        ])
        rows.append([
            InlineKeyboardButton("📥 Tải lại file .mobileconfig", callback_data="get_mobileconfig"),
        ])
    rows.append([
        InlineKeyboardButton("📦 Đơn hàng đã mua",        callback_data="my_orders"),
        InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS",  callback_data="show_guide"),
    ])
    rows.append([
        InlineKeyboardButton("🏠 Về menu chính",          callback_data="back_main"),
    ])
    return InlineKeyboardMarkup(rows)


def back_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide")],
        [InlineKeyboardButton("🏠 Về trang chủ", callback_data="back_main")]
    ])


def language_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Tiếng Việt 🇻🇳", callback_data="lang:vi"),
            InlineKeyboardButton("English 🇬🇧",    callback_data="lang:en"),
        ],
        [InlineKeyboardButton("🏠 Về trang chủ", callback_data="back_main")]
    ])


def apidocs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📑 Bảng tra cứu mã lỗi HTTP", callback_data="apidocs:errors"),
            InlineKeyboardButton("🏠 Về trang chủ",            callback_data="back_main"),
        ]
    ])


def apierrors_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📘 Tổng quan tài liệu API", callback_data="apidocs:overview"),
            InlineKeyboardButton("🏠 Về trang chủ",          callback_data="back_main"),
        ]
    ])


# ── ADMIN KEYBOARDS ──────────────────────────────────────────────────────────

def admin_approval_kb(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Duyệt & Kích hoạt", callback_data=f"admin_approve:{order_id}"),
            InlineKeyboardButton("❌ Từ chối",           callback_data=f"admin_reject:{order_id}"),
        ]
    ])


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Thống kê doanh thu", callback_data="admin:stats"),
            InlineKeyboardButton("📋 Đơn hàng gần đây",    callback_data="admin:recent"),
        ],
        [
            InlineKeyboardButton("🪙 Số dư Coin CTV",     callback_data="admin:balance"),
            InlineKeyboardButton("👥 Quản lý người dùng",  callback_data="admin:users_list"),
        ],
        [
            InlineKeyboardButton("💳 Kiểm tra VietQR",    callback_data="admin:checkbank"),
            InlineKeyboardButton("🔍 Tìm kiếm đơn / user", callback_data="admin:find_menu"),
        ],
        [
            InlineKeyboardButton("🔎 Tra cứu thông tin UID", callback_data="admin:check_uid_menu"),
            InlineKeyboardButton("🔄 Reset thiết bị Spotify", callback_data="admin:reset_menu"),
        ],
        [
            InlineKeyboardButton("📢 Gửi thông báo toàn hệ thống", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton("🏠 Đóng bảng điều khiển", callback_data="admin:close"),
        ]
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Về bảng điều khiển", callback_data="admin:menu")]
    ])
