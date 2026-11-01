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

def payment_kb(order_id: str, applied_coupon: str = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("✅ Tôi đã chuyển khoản", callback_data=f"paid:{order_id}")],
    ]
    if applied_coupon:
        rows.append([InlineKeyboardButton(f"🎟 Đã áp mã: {applied_coupon} ✓", callback_data=f"coupon_info:{order_id}")])
    else:
        rows.append([InlineKeyboardButton("🎟 Nhập mã giảm giá", callback_data=f"coupon:{order_id}")])
    rows.extend([
        [
            InlineKeyboardButton("📖 Hướng dẫn cài đặt", callback_data="show_guide"),
            InlineKeyboardButton("❌ Huỷ đơn hàng",       callback_data=f"cancel:{order_id}")
        ],
        [InlineKeyboardButton("🏠 Về trang chủ",         callback_data="back_main")],
    ])
    return InlineKeyboardMarkup(rows)


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


def combo_success_kb(dns_locket: str = None, dns_spotify: str = None) -> InlineKeyboardMarkup:
    dns_locket = dns_locket or "https://alopremium.shop"
    dns_spotify = dns_spotify or "https://alopremium.shop"
    rows = [
        [
            InlineKeyboardButton("📋 Copy Link Locket", api_kwargs={"copy_text": {"text": dns_locket}}),
            InlineKeyboardButton("📋 Copy Link Spotify", api_kwargs={"copy_text": {"text": dns_spotify}}),
        ],
        [
            InlineKeyboardButton("📷 Tạo Mã QR DNS", callback_data="show_qr")
        ],
        [
            InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide"),
            InlineKeyboardButton("💬 Hỗ trợ CSKH 24/7", callback_data="support"),
        ],
        [
            InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")
        ]
    ]
    return InlineKeyboardMarkup(rows)


def success_kb(dns_link: str = None, service: str = "locket") -> InlineKeyboardMarkup:
    rows = []
    is_spotify = (service == "spotify")
    svc_label = "Spotify" if is_spotify else "Locket"
    qr_text = f"📷 Tạo Mã QR {svc_label}"
    copy_text = f"📋 Copy Link DNS {svc_label}"

    if dns_link:
        rows.append([
            InlineKeyboardButton(qr_text, callback_data=f"show_qr:{service}"),
            InlineKeyboardButton(copy_text, api_kwargs={"copy_text": {"text": dns_link}})
        ])
    else:
        rows.append([
            InlineKeyboardButton(qr_text, callback_data=f"show_qr:{service}")
        ])
    rows.append([
        InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide"),
        InlineKeyboardButton("💬 Hỗ trợ kỹ thuật", callback_data="support")
    ])
    rows.append([
        InlineKeyboardButton("🏠 Về menu chính", callback_data="back_main")
    ])
    return InlineKeyboardMarkup(rows)


def orders_kb(has_done_order: bool = False, has_spotify: bool = False) -> InlineKeyboardMarkup:
    rows = []
    if has_done_order:
        rows.append([
            InlineKeyboardButton("📷 Tạo Mã QR DNS", callback_data="show_qr")
        ])
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
            InlineKeyboardButton("📷 Tạo Mã QR DNS", callback_data="show_qr"),
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


def admin_kb(pending_count: int = 0) -> InlineKeyboardMarkup:
    pending_label = f"⚡ Duyệt đơn chờ ({pending_count})" if pending_count > 0 else "⚡ Đơn chờ duyệt"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(pending_label,           callback_data="admin:orders:pending"),
            InlineKeyboardButton("📊 Doanh thu & Thống kê", callback_data="admin:stats"),
        ],
        [
            InlineKeyboardButton("📦 Tất cả đơn hàng",    callback_data="admin:orders:all"),
            InlineKeyboardButton("👥 Quản lý khách hàng", callback_data="admin:users_list"),
        ],
        [
            InlineKeyboardButton("💰 Chỉnh sửa bảng giá", callback_data="admin:edit_prices"),
            InlineKeyboardButton("🎟 Mã giảm giá",         callback_data="admin:codes_list"),
        ],
        [
            InlineKeyboardButton("🪙 Số dư Coin CTV",     callback_data="admin:balance"),
            InlineKeyboardButton("💳 Kiểm tra VietQR",    callback_data="admin:checkbank"),
        ],
        [
            InlineKeyboardButton("🔍 Tìm kiếm đơn/user",   callback_data="admin:find_menu"),
            InlineKeyboardButton("🔎 Tra cứu UID API",    callback_data="admin:check_uid_menu"),
        ],
        [
            InlineKeyboardButton("🔄 Reset máy Spotify",  callback_data="admin:reset_menu"),
            InlineKeyboardButton("📢 Gửi thông báo toàn bot", callback_data="admin:broadcast"),
        ],
        [
            InlineKeyboardButton("🌐 Mở Web Admin",       url="https://alopremium.shop/admin"),
        ],
        [
            InlineKeyboardButton("🏠 Đóng bảng điều khiển", callback_data="admin:close"),
        ]
    ])


def admin_orders_kb(filter_type: str = "all") -> InlineKeyboardMarkup:
    all_btn = f"{'🔘' if filter_type == 'all' else '⚪'} Tất cả"
    done_btn = f"{'🔘' if filter_type == 'done' else '⚪'} Đã duyệt"
    pending_btn = f"{'🔘' if filter_type == 'pending' else '⚪'} Chờ TT"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(all_btn, callback_data="admin:orders:all"),
            InlineKeyboardButton(done_btn, callback_data="admin:orders:done"),
            InlineKeyboardButton(pending_btn, callback_data="admin:orders:pending"),
        ],
        [
            InlineKeyboardButton("🔄 Làm mới", callback_data=f"admin:orders:{filter_type}"),
            InlineKeyboardButton("🔙 Menu Admin", callback_data="admin:menu"),
        ]
    ])


def back_admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Về bảng điều khiển", callback_data="admin:menu")]
    ])


def admin_prices_overview_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💛 Sửa giá Locket Gold", callback_data="admin:price_prod:locket"),
            InlineKeyboardButton("🎵 Sửa giá Spotify",     callback_data="admin:price_prod:spotify"),
        ],
        [
            InlineKeyboardButton("👑 Sửa giá Combo Duo VIP", callback_data="admin:price_prod:combo"),
        ],
        [
            InlineKeyboardButton("🔄 Khôi phục giá mặc định", callback_data="admin:reset_prices_confirm"),
        ],
        [
            InlineKeyboardButton("🔙 Menu Admin", callback_data="admin:menu"),
        ]
    ])


def admin_prices_plans_kb(product_key: str) -> InlineKeyboardMarkup:
    from config import PRODUCTS
    prod = PRODUCTS.get(product_key, {})
    plans = prod.get("plans", {})
    rows = []
    for plan_key, plan_data in plans.items():
        lbl = plan_data.get("label", plan_key)
        p = plan_data.get("price", 0)
        p_str = f"{p:,}đ".replace(",", ".")
        btn_text = f"✏️ {lbl} — {p_str}"
        rows.append([InlineKeyboardButton(btn_text, callback_data=f"admin:setprice:{product_key}:{plan_key}")])
    rows.append([
        InlineKeyboardButton("🔙 Chọn dịch vụ khác", callback_data="admin:edit_prices"),
        InlineKeyboardButton("🔙 Menu Admin", callback_data="admin:menu")
    ])
    return InlineKeyboardMarkup(rows)
