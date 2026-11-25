"""
handlers/user_handlers.py
Quy trình 4 bước bán Locket & Spotify theo API locket.2707226.xyz
Giao diện chuyên nghiệp, hỗ trợ điều hướng quay lại và huỷ thao tác mượt mà.
"""

import os
import sys
import asyncio

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import logging
from html import escape
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

import database as db
import api_client as api
import utils
import config
from config import PRODUCTS, SUPPORT_USERNAME, DNS_BASE_URL, DNS_SLUG
from keyboards import (
    main_menu_kb, plan_kb, confirm_buy_kb, back_main_kb,
    payment_kb, admin_approval_kb, back_to_plan_kb,
    success_kb, pending_approval_kb, orders_kb, support_kb, account_kb, language_kb,
    apidocs_kb, apierrors_kb, locket_ai_ask_studio_kb, locket_ai_success_kb, studio_success_kb
)

logger = logging.getLogger(__name__)

# ── ConversationHandler states ────────────────────────────────────────────────
WAITING_IDENTIFIER = 10   # chờ user nhập link/uid/username


# ═══════════════════════════════════════════════════════════════════════════════
#  /start  &  /menu & Các lệnh chính
# ═══════════════════════════════════════════════════════════════════════════════

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)

    banned, reason = db.is_banned(user.id)
    if banned:
        await update.message.reply_text(
            f"⛔ <b>Tài khoản của bạn đã bị tạm khoá!</b>\n\n"
            f"Lý do: <i>{reason}</i>\n"
            f"Liên hệ hỗ trợ: @{SUPPORT_USERNAME}",
            parse_mode=ParseMode.HTML
        )
        return ConversationHandler.END

    banner_line = ""
    try:
        b = db.get_banner_config()
        if b and b.get("enabled", True) and b.get("text"):
            badge = b.get("badge") or "🔥 HOT ƯU ĐÃI"
            banner_line = f"🎉 <b>[{badge}]</b> {b.get('text')}\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    except Exception:
        pass

    web_url = getattr(config, "WEBSITE_URL", "https://alopremium.shop")
    text = (
        f"👋 Xin chào <b>{user.first_name}</b>!\n"
        f"Chào mừng bạn đến với <b>AloPremium.Shop — Dịch Vụ Tự Động</b> 🌟\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{banner_line}"
        f"⚡ <b>Kích hoạt siêu tốc:</b> Cài đặt trực tiếp qua DNS Profile iOS\n"
        f"🔒 <b>Bảo mật 100%:</b> Không yêu cầu cung cấp mật khẩu tài khoản\n"
        f"🛡 <b>Bảo hành uy tín:</b> Đổi mới & hỗ trợ 1-1 trọn đời gói\n"
        f"🌐 <b>Website chính thức:</b> <a href='{web_url}'>AloPremium.Shop</a>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 <b>Chọn dịch vụ bạn muốn trải nghiệm hoặc mở Website bên dưới:</b>"
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb(),
        disable_web_page_preview=True
    )
    return ConversationHandler.END


async def web_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /web – Mở nhanh Website AloPremium.Shop."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    web_url = getattr(config, "WEBSITE_URL", "https://alopremium.shop")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Mở Website AloPremium.Shop", url=web_url)],
        [InlineKeyboardButton("🏠 Về Menu Chính", callback_data="back_main")]
    ])
    await update.message.reply_text(
        f"🌐 <b>TRANG WEB CHÍNH THỨC — ALOPREMIUM.SHOP</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Mua gói VIP Locket Gold, AI Filters & Spotify tự động 24/7\n"
        f"• Tra cứu lịch sử đơn hàng & Tải lại cấu hình DNS miễn phí\n"
        f"• Nhận Link Studio chỉnh chú thích & đổi 38 khung viền\n"
        f"• Hỗ trợ đổi máy / Reset thiết bị trực tiếp\n\n"
        f"🔗 Truy cập ngay: <a href='{web_url}'>{web_url}</a>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    banned, reason = db.is_banned(user.id)
    if banned:
        await update.message.reply_text(f"⛔ Tài khoản đã bị khoá: {reason}")
        return ConversationHandler.END

    await update.message.reply_text(
        utils.build_product_menu_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Hiển thị thông tin hướng dẫn sử dụng và danh sách lệnh có sẵn.
    Hiển thị cả Admin control nếu là admin.
    """
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    banned, reason = db.is_banned(user.id)
    if banned:
        await update.message.reply_text(f"⛔ Tài khoản đã bị khoá: {reason}")
        return

    text = (
        "📋 <b>Hướng dẫn sử dụng</b>\n\n"
        "<b>Bước 1</b>: Bấm /start hoặc chọn dịch vụ\n"
        "<b>Bước 2</b>: Nhập username hoặc link\n"
        "<b>Bước 3</b>: Chọn gói và phương thức thanh toán\n"
        "<b>Bước 4</b>: Cài file cấu hình ngay sau khi kích hoạt\n\n"
        "<b>Các lệnh có sẵn</b>\n"
        "<pre>\n"
        "/start    Menu chính\n"
        "/account  Tài khoản\n"
        "/apidocs  Tài liệu API\n"
        "/setlang  Đổi ngôn ngữ\n"
        "/help     Hướng dẫn\n"
        "</pre>\n\n"
        f"Liên hệ hỗ trợ @{SUPPORT_USERNAME}"
    )

    from config import ADMIN_IDS
    if user.id in ADMIN_IDS:
        text += (
            "\n\n<b>Admin control</b>\n"
            "<pre>\n"
            "/admin          Full control panel\n"
            "/noti           Broadcast đa phương tiện\n"
            "                (premium emoji OK)\n"
            "/notistop       Dừng broadcast đang chạy\n"
            "/rs [id]        Reset usage\n"
            "/stats          System stats\n"
            "/users [id]     Danh sách / chi tiết user\n"
            "/find [query]   Tìm user (id/username/\n"
            "                uid/order)\n"
            "/ban [id] [rs]  Ban user\n"
            "/unban [id]     Unban user\n"
            "/orders         Recent orders\n"
            "/tokens         Token pool status\n"
            "/checkbank      Test STC bank API\n"
            "/addcode        Tạo mã giảm giá\n"
            "/delcode        Xoá mã giảm giá\n"
            "/cancel         Huỷ thao tác hiện tại\n"
            "</pre>"
        )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def account_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /account – Xem thông tin tài khoản người dùng."""
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    banned, reason = db.is_banned(user.id)
    if banned:
        await update.message.reply_text(f"⛔ Tài khoản đã bị khoá: {reason}")
        return

    orders = db.get_user_orders(user.id)
    done_orders = [o for o in orders if o.get("status") == "done"]
    lang = db.get_user_lang(user.id)
    lang_name = "Tiếng Việt 🇻🇳" if lang == "vi" else "English 🇬🇧"

    lines = [
        "👤 <b>THÔNG TIN TÀI KHOẢN CÁ NHÂN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>",
        f"👤 <b>Họ tên:</b> {user.full_name}",
        f"🔗 <b>Username:</b> @{user.username or 'Chưa đặt'}",
        f"🌐 <b>Ngôn ngữ:</b> {lang_name}",
        f"📦 <b>Tổng đơn hàng:</b> <b>{len(orders)}</b> (Đã kích hoạt: {len(done_orders)})\n",
        "💎 <b>DỊCH VỤ ĐÃ KÍCH HOẠT:</b>"
    ]

    if done_orders:
        latest_done = sorted(done_orders, key=lambda x: x.get("created_at") or "", reverse=True)[0]
        prod_k = latest_done.get("product")
        if prod_k in ("combo", "locket_spotify"):
            dns_link = latest_done.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            link_label = "👑 <b>Link DNS Combo Duo VIP (Locket & Spotify):</b>"
        elif prod_k == "locket_ai":
            dns_link = latest_done.get("vip_download_url") or latest_done.get("dns_link") or getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
            link_label = "✨ <b>Link Cài Đặt VIP ALL-IN-ONE:</b>"
        else:
            dns_link = latest_done.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            link_label = "🌐 <b>Link DNS Profile iOS:</b>"

        for o in sorted(done_orders, key=lambda x: x["created_at"], reverse=True)[:5]:
            prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
            plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
            lines.append(f"• <b>{prod} ({plan})</b> — UID: <code>{o.get('uid')}</code>")
        lines.extend([
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{link_label}\n<code>{dns_link}</code>",
            "💡 <i>Mở link trên Safari để tải & cài đặt cấu hình VPN & DNS.</i>"
        ])
        kb = account_kb(dns_link=dns_link)
    else:
        lines.append("<i>Chưa có gói dịch vụ nào đang kích hoạt.</i>")
        lines.append("\n💡 <i>Bấm <b>'Mua gói ngay'</b> bên dưới để kích hoạt bản quyền VIP nhé!</i>")
        kb = account_kb(dns_link=None)

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


def build_api_docs_text() -> str:
    return (
        "📖 <b>TÀI LIỆU TÍCH HỢP HỆ THỐNG API (CTV / DEV)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>Base URL:</b> <code>https://locket.2707226.xyz</code>\n"
        "🔑 <b>Authentication:</b> <code>Bearer &lt;YOUR_API_KEY&gt;</code>\n"
        "Header: <code>Content-Type: application/json</code>\n\n"
        "📌 <b>CÁC ENDPOINTS CHÍNH:</b>\n\n"
        "1️⃣ <b>Kiểm tra tài khoản & Số dư Coin CTV:</b>\n"
        "• <code>GET /api/keys/me</code>\n\n"
        "2️⃣ <b>Danh sách bảng giá gói cước:</b>\n"
        "• <code>GET /api/packages?service=all|spotify|locket</code>\n\n"
        "3️⃣ <b>Tra cứu Locket Username ra UID & Avatar:</b>\n"
        "• <code>POST /api/uid/resolve</code>\n"
        "• Body: <code>{\"identifier\": \"conlaigii\", \"service\": \"locket\"}</code>\n\n"
        "4️⃣ <b>Mua gói / Kích hoạt tự động:</b>\n"
        "• <code>POST /api/uid/create</code>\n"
        "• Body: <code>{\"username\": \"UID\", \"packageCode\": \"LKG1Y\", \"service\": \"locket\"}</code>\n\n"
        "5️⃣ <b>Reset thiết bị Spotify:</b>\n"
        "• <code>POST /api/spotify/reset</code>\n"
        "• Body: <code>{\"uid\": \"spotify_uid\"}</code>\n\n"
        "6️⃣ <b>Kiểm tra Profile Spotify:</b>\n"
        "• <code>GET /api/spotify/check?uid=...</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <i>Bấm nút bên dưới để xem <b>Bảng Tra Cứu Mã Lỗi HTTP</b> hoặc liên hệ hỗ trợ.</i>"
    )


def build_api_errors_text() -> str:
    return (
        "⚠️ <b>BẢNG TRA CỨU MÃ LỖI HTTP (API TỰ ĐỘNG HÓA)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔴 <b>HTTP 400 | \"Thiếu username hoặc uid\"</b>\n"
        "• <b>Nguyên nhân:</b> Body hoặc Query gửi lên thiếu trường bắt buộc hoặc sai định dạng.\n"
        "• <b>Cách xử lý:</b> Kiểm tra lại tên key trong JSON body và chắc chắn có <code>Content-Type: application/json</code>.\n\n"
        "🔴 <b>HTTP 401 | \"Unauthorized\"</b>\n"
        "• <b>Nguyên nhân:</b> Secret Key sai, đã bị rotate đổi mới hoặc thiếu header Bearer.\n"
        "• <b>Cách xử lý:</b> Lấy lại Secret Token trong tab Mã API. Gửi header <code>Authorization: Bearer sk_....</code>\n\n"
        "🟡 <b>HTTP 402 | \"Không đủ coin. Cần 15, bạn có 8\"</b>\n"
        "• <b>Nguyên nhân:</b> Số dư tài khoản CTV không đủ để thanh toán gói này.\n"
        "• <b>Cách xử lý:</b> Nạp thêm coin trong tab Nạp Coin của Dashboard.\n\n"
        "🔴 <b>HTTP 403 | \"Tài khoản chưa kích hoạt\"</b>\n"
        "• <b>Nguyên nhân:</b> Tài khoản CTV mới tạo chưa nạp đủ 150.000đ kích hoạt ban đầu.\n"
        "• <b>Cách xử lý:</b> Nạp tối thiểu 150.000đ để kích hoạt tài khoản.\n\n"
        "🟡 <b>HTTP 404 | \"Gói không tồn tại hoặc đã ẩn\"</b>\n"
        "• <b>Nguyên nhân:</b> Mã gói packageCode viết sai (Ví dụ nhầm SPOTIFY_1Y).\n"
        "• <b>Cách xử lý:</b> Gọi <code>GET /api/packages</code> để lấy đúng mã gói (SPT, SP6M, SPOTIFY1Y, SPVV).\n\n"
        "🔴 <b>HTTP 409 | \"UID thuộc về người khác\"</b>\n"
        "• <b>Nguyên nhân:</b> UID này đã được mua bởi CTV khác và vẫn đang còn hạn dùng.\n"
        "• <b>Cách xử lý:</b> Khách phải chờ hết hạn cũ hoặc dùng đúng tài khoản CTV ban đầu gia hạn.\n\n"
        "🔴 <b>HTTP 429 | \"Tra cứu quá nhiều – thử lại sau\"</b>\n"
        "• <b>Nguyên nhân:</b> Vượt quá tần suất rate limit cho phép trong 1 giờ.\n"
        "• <b>Cách xử lý:</b> Thêm cache ở bot (ví dụ cache 30 giây cho cùng một khách) để giảm tải request.\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💬 <i>Liên hệ hỗ trợ @{SUPPORT_USERNAME}</i>"
    )


async def apidocs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /apidocs – Xem tài liệu API CTV."""
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    await update.message.reply_text(
        build_api_docs_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=apidocs_kb()
    )


async def apierrors_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /apierrors – Tra cứu bảng mã lỗi HTTP của API."""
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    await update.message.reply_text(
        build_api_errors_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=apierrors_kb()
    )


async def cb_apidocs(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Chuyển đổi giữa Tổng quan API và Bảng Mã Lỗi."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[1]

    if action == "errors":
        try:
            await query.edit_message_text(
                build_api_errors_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=apierrors_kb()
            )
        except Exception:
            await query.message.reply_text(
                build_api_errors_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=apierrors_kb()
            )
    else:  # overview
        try:
            await query.edit_message_text(
                build_api_docs_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=apidocs_kb()
            )
        except Exception:
            await query.message.reply_text(
                build_api_docs_text(),
                parse_mode=ParseMode.HTML,
                reply_markup=apidocs_kb()
            )


async def setlang_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /setlang – Đổi ngôn ngữ người dùng."""
    user = update.effective_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    await update.message.reply_text(
        "🌐 <b>CHỌN NGÔN NGỮ / SELECT LANGUAGE:</b>\n\nVui lòng chọn ngôn ngữ hiển thị bên dưới:",
        parse_mode=ParseMode.HTML,
        reply_markup=language_kb()
    )


async def cb_my_account(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback xem tài khoản cá nhân."""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db.upsert_user(user.id, user.username, user.first_name, user.last_name)
    orders = db.get_user_orders(user.id)
    done_orders = [o for o in orders if o.get("status") == "done"]
    lang = db.get_user_lang(user.id)
    lang_name = "Tiếng Việt 🇻🇳" if lang == "vi" else "English 🇬🇧"

    lines = [
        "👤 <b>THÔNG TIN TÀI KHOẢN CÁ NHÂN</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🆔 <b>Telegram ID:</b> <code>{user.id}</code>",
        f"👤 <b>Họ tên:</b> {user.full_name}",
        f"🔗 <b>Username:</b> @{user.username or 'Chưa đặt'}",
        f"🌐 <b>Ngôn ngữ:</b> {lang_name}",
        f"📦 <b>Tổng đơn hàng:</b> <b>{len(orders)}</b> (Đã kích hoạt: {len(done_orders)})\n",
        "💎 <b>DỊCH VỤ ĐÃ KÍCH HOẠT:</b>"
    ]

    if done_orders:
        latest_done = sorted(done_orders, key=lambda x: x.get("created_at") or "", reverse=True)[0]
        prod_k = latest_done.get("product")
        if prod_k in ("combo", "locket_spotify"):
            dns_link = latest_done.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            link_label = "👑 <b>Link DNS Combo Duo VIP (Locket & Spotify):</b>"
        elif prod_k == "locket_ai":
            dns_link = latest_done.get("vip_download_url") or latest_done.get("dns_link") or getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
            link_label = "✨ <b>Link Cài Đặt VIP ALL-IN-ONE:</b>"
        else:
            dns_link = latest_done.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            link_label = "🌐 <b>Link DNS Profile iOS:</b>"

        for o in sorted(done_orders, key=lambda x: x["created_at"], reverse=True)[:5]:
            prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
            plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
            lines.append(f"• <b>{prod} ({plan})</b> — UID: <code>{o.get('uid')}</code>")
        lines.extend([
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"{link_label}\n<code>{dns_link}</code>",
            "💡 <i>Mở link trên Safari để tải & cài đặt cấu hình VPN & DNS.</i>"
        ])
        kb = account_kb(dns_link=dns_link)
    else:
        lines.append("<i>Chưa có gói dịch vụ nào đang kích hoạt.</i>")
        lines.append("\n💡 <i>Bấm <b>'Mua gói ngay'</b> bên dưới để kích hoạt bản quyền VIP nhé!</i>")
        kb = account_kb(dns_link=None)

    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    except Exception:
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )


async def cb_cmd_setlang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback mở menu chọn ngôn ngữ."""
    query = update.callback_query
    await query.answer()
    try:
        await query.edit_message_text(
            "🌐 <b>CHỌN NGÔN NGỮ / SELECT LANGUAGE:</b>\n\nVui lòng chọn ngôn ngữ hiển thị bên dưới:",
            parse_mode=ParseMode.HTML,
            reply_markup=language_kb()
        )
    except Exception:
        await query.message.reply_text(
            "🌐 <b>CHỌN NGÔN NGỮ / SELECT LANGUAGE:</b>\n\nVui lòng chọn ngôn ngữ hiển thị bên dưới:",
            parse_mode=ParseMode.HTML,
            reply_markup=language_kb()
        )


async def cb_lang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback lưu ngôn ngữ người dùng."""
    query = update.callback_query
    await query.answer()
    lang = query.data.split(":")[1]
    db.set_user_lang(query.from_user.id, lang)
    msg = (
        "✅ Ngôn ngữ đã được đặt thành: <b>Tiếng Việt 🇻🇳</b>\n"
        "Đã lưu cài đặt của bạn thành công!"
        if lang == "vi" else
        "✅ Language set to: <b>English 🇬🇧</b>\n"
        "Your preferences have been saved successfully!"
    )
    try:
        await query.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())
    except Exception:
        await query.message.reply_text(msg, parse_mode=ParseMode.HTML, reply_markup=main_menu_kb())


async def cb_get_mobileconfig(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback gửi trực tiếp file .mobileconfig cho người dùng ĐÃ THANH TOÁN."""
    query = update.callback_query
    user = query.from_user

    orders = db.get_user_orders(user.id)
    done_orders = [o for o in orders if o.get("status") == "done"]

    if not done_orders:
        await query.answer(
            "⚠️ Bạn chưa có đơn hàng nào được duyệt thanh toán thành công!\nVui lòng thanh toán và đợi hệ thống duyệt để nhận file DNS.",
            show_alert=True
        )
        return

    await query.answer("Đang xuất file cấu hình...")
    latest = sorted(done_orders, key=lambda x: x.get("created_at") or "", reverse=True)[0]
    prod_key = latest.get("product", "locket")
    pv = PRODUCTS.get(prod_key, {})
    prod_name = pv.get("name", "Locket & Spotify Premium")
    uid_name = latest.get("display_name") or latest.get("uid") or user.first_name

    if prod_key in ("combo", "locket_spotify"):
        dns_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
    elif prod_key == "locket_ai":
        dns_link = latest.get("vip_download_url") or latest.get("dns_link") or getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
    else:
        dns_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
    profile_bytes = None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=5) as client:
            r_ctv = await client.get(dns_link)
            if r_ctv.is_success and b"PayloadContent" in r_ctv.content:
                profile_bytes = r_ctv.content
    except Exception:
        pass

    if profile_bytes:
        import io
        bio = io.BytesIO(profile_bytes)
        bio.name = f"LocketGold_{uid_name}.mobileconfig"
        bio.seek(0)
    else:
        bio = utils.generate_mobileconfig(
            service_name=prod_name,
            display_name=uid_name,
            dns_link=dns_link
        )
    safe_uid = str(uid_name).replace(" ", "_")
    bio.name = f"{prod_key.capitalize()}_{safe_uid}.mobileconfig"

    target_link = dns_link
    if target_link:
        try:
            qr_buf = utils.generate_qr_code(target_link)
            await ctx.bot.send_photo(
                chat_id=user.id,
                photo=qr_buf,
                caption=(
                    f"📷 <b>MÃ QR TẢI HỒ SƠ ({prod_name})</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Mở <b>Camera iPhone</b> quét mã để mở Safari tải tự động!\n"
                    f"Hoặc tải trực tiếp file đính kèm bên dưới:"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    caption = (
        f"📥 <b>HỒ SƠ CẤU HÌNH DNS PROFILE (.mobileconfig)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Tài khoản: <b>@{uid_name}</b>\n"
        f"📦 Dịch vụ: <b>{prod_name}</b>\n\n"
        f"⚡ <b>HƯỚNG DẪN CÀI ĐẶT 1 CHẠM TRÊN IPHONE:</b>\n"
        f"1️⃣ Bấm trực tiếp vào file đính kèm phía trên để tải về máy.\n"
        f"2️⃣ Bấm <b>\"Cho phép\" (Allow)</b> khi có thông báo hiện lên.\n"
        f"3️⃣ Mở <b>Cài đặt (Settings)</b> trên iPhone → Chọn mục <b>Đã tải về hồ sơ</b> (ở đầu trang Cài đặt).\n"
        f"4️⃣ Bấm <b>Cài đặt (Install)</b> ở góc trên bên phải → Nhập mật mã máy và xác nhận là xong! 🎉\n\n"
        f"💡 <i>Nếu cần hỗ trợ kỹ thuật, hãy bấm /support để gặp CSKH.</i>"
    )

    await ctx.bot.send_document(
        chat_id=user.id,
        document=bio,
        filename=bio.name,
        caption=caption,
        parse_mode=ParseMode.HTML
    )


async def cb_show_qr(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback bấm nút '📷 Tạo Mã QR Code' từ link DNS cấu hình của khách."""
    query = update.callback_query
    await query.answer("Đang tạo mã QR cho link DNS của bạn...")
    user = query.from_user

    orders = db.get_user_orders(user.id)
    done_orders = [o for o in orders if o.get("status") == "done"]

    if not done_orders:
        await query.answer("⚠️ Bạn chưa có đơn hàng nào được kích hoạt để tạo mã QR DNS!", show_alert=True)
        return

    target_service = query.data.split(":")[1] if ":" in query.data else None
    if target_service in ("combo", "locket_spotify"):
        matching = [o for o in done_orders if o.get("product") in ("combo", "locket_spotify")]
        if not matching:
            await query.answer("⚠️ Bạn chưa mua hoặc chưa thanh toán gói này!", show_alert=True)
            return
        latest = sorted(matching, key=lambda x: x.get("created_at") or "", reverse=True)[0]
        target_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
        prod_name = "Combo Duo VIP"
        uid_name = latest.get("display_name") or latest.get("uid") or user.first_name
    elif target_service:
        matching = [o for o in done_orders if o.get("product") == target_service]
        latest = sorted(matching, key=lambda x: x.get("created_at") or "", reverse=True)[0] if matching else sorted(done_orders, key=lambda x: x.get("created_at") or "", reverse=True)[0]
        prod_key = latest.get("product", "locket")
        pv = PRODUCTS.get(prod_key, {})
        prod_name = pv.get("name", "Dịch vụ Premium")
        uid_name = latest.get("display_name") or latest.get("uid") or user.first_name
        is_spotify = (prod_key == "spotify")
        svc_label = "Spotify" if is_spotify else "Locket"
        if prod_key in ("combo", "locket_spotify"):
            target_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            prod_name = "Combo Duo VIP"
            svc_label = "Combo Duo"
        elif prod_key == "locket_ai":
            target_link = latest.get("vip_download_url") or latest.get("dns_link") or getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
            prod_name = "VIP ALL-IN-ONE"
            svc_label = "VIP"
        else:
            target_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
    else:
        latest = sorted(done_orders, key=lambda x: x.get("created_at") or "", reverse=True)[0]
        prod_key = latest.get("product", "locket")
        pv = PRODUCTS.get(prod_key, {})
        prod_name = pv.get("name", "Dịch vụ Premium")
        uid_name = latest.get("display_name") or latest.get("uid") or user.first_name
        is_spotify = (prod_key == "spotify")
        svc_label = "Spotify" if is_spotify else "Locket"
        if prod_key in ("combo", "locket_spotify"):
            target_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"
            prod_name = "Combo Duo VIP"
            svc_label = "Combo Duo"
        elif prod_key == "locket_ai":
            target_link = latest.get("vip_download_url") or latest.get("dns_link") or getattr(config, "VIP_DOWNLOAD_URL", "https://locket.jayteam.click/download.php?token=jt_8b08db1702f75cc06d1c4516989913a0&server=1")
            prod_name = "VIP ALL-IN-ONE"
            svc_label = "VIP"
        else:
            target_link = latest.get("dns_link") or f"{DNS_BASE_URL}/{DNS_SLUG}"

    try:
        qr_buf = utils.generate_qr_code(target_link)
        caption = (
            f"📷 <b>MÃ QR CODE TẢI DNS PROFILE ({prod_name})</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 Tài khoản: <b>@{uid_name}</b>\n"
            f"🌐 Link DNS: <code>{target_link}</code>\n\n"
            f"⚡ <b>Cách quét mã cài đặt:</b>\n"
            f"1️⃣ Dùng <b>Camera iPhone</b> quét mã QR trên màn hình.\n"
            f"2️⃣ Bấm thông báo màu vàng <b>\"Mở trong Safari\"</b> để tải hồ sơ cấu hình vào máy!"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"📋 Copy Link DNS {svc_label}", api_kwargs={"copy_text": {"text": target_link}}),
                InlineKeyboardButton("📖 Hướng dẫn cài đặt iOS", callback_data="show_guide")
            ],
            [
                InlineKeyboardButton("💬 Hỗ trợ kỹ thuật", callback_data="support"),
                InlineKeyboardButton("🏠 Menu Chính", callback_data="back_main")
            ]
        ])
        await ctx.bot.send_photo(
            chat_id=user.id,
            photo=qr_buf,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    except Exception as e:
        logger.error(f"Error in cb_show_qr: {e}")
        await query.message.reply_text(f"❌ Không thể tạo mã QR: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 1: Chọn sản phẩm & Gói (Callback)
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_product(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_key = query.data.split(":")[1]
    ctx.user_data["product"] = product_key

    text = utils.build_plan_text(product_key)
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=plan_kb(product_key)
        )
    except Exception:
        await query.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=plan_kb(product_key)
        )


async def cb_plan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Người dùng chọn gói → lưu product/plan vào user_data → hỏi identifier.
    """
    query = update.callback_query
    await query.answer()
    _, product_key, plan_key = query.data.split(":")

    ctx.user_data["product"] = product_key
    ctx.user_data["plan"]    = plan_key

    prods = getattr(utils, "get_dynamic_products", lambda: PRODUCTS)()
    pv    = prods.get(product_key, PRODUCTS[product_key])
    plnv  = pv["plans"][plan_key]

    if product_key == "spotify":
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI LINK PROFILE SPOTIFY (BẮT BUỘC DẠNG LINK)</b>\n\n"
            f"<b>Cách lấy liên kết Spotify cá nhân:</b>\n"
            f"  1️⃣ Mở app Spotify → Bấm <b>Cài đặt (hoặc Avatar)</b>\n"
            f"  2️⃣ Chọn <b>Hồ sơ cá nhân</b> → Bấm <b>Chia sẻ</b> → <b>Sao chép liên kết</b>\n\n"
            f"• Link URL mẫu: <code>https://open.spotify.com/user/31t3tcqt...</code>\n\n"
            f"👇 <b>Dán Link Profile Spotify vào ô chat bên dưới:</b>\n"
            f"💡 <i>(Nếu có mã giảm giá, bạn có thể gửi kèm, ví dụ: <code>link MÃ_GIẢM_GIÁ</code> hoặc bấm nút nhập mã sau khi hoá đơn xuất hiện)</i>"
        )
    elif product_key == "locket_ai":
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>ĐẶC QUYỀN MỞ KHÓA TRỌN BỘ:</b>\n"
            f"👑 <b>Locket Gold:</b> Viền vàng Avatar VIP, Video 60s, Kho 38 khung viền, Tải ảnh 4K.\n"
            f"🎭 <b>AI Filters Mới:</b> Mở full 8 danh mục bộ lọc (Events, Goofy, Looks, Celebrate...).\n"
            f"✨ <b>Nút [✨ Tạo diện mạo]:</b> Tự do nhập prompt sáng tạo diện mạo AI cá nhân.\n"
            f"🎨 <b>Tặng kèm Studio Cá Nhân:</b> Link chỉnh chú thích & đổi 38 khung viền không giới hạn.\n"
            f"🎵 <b>Spotify Premium:</b> Chặn 100% Ads quảng cáo, Next bài vô hạn, Âm thanh 320kbps.\n"
            f"🟠 <b>SoundCloud Go+:</b> Mở khóa SoundCloud Go+ (Plus), Tải nghe Offline, Âm thanh HQ Audio.\n"
            f"🎬 <b>YouTube Premium:</b> Chặn 100% Ads video, Phát âm thanh tắt màn hình & Hình trong hình (PiP).\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI USERNAME LOCKET CỦA BẠN (CHỈ ĐIỀN USER, KHÔNG DÁN LINK)</b>\n\n"
            f"<b>Hướng dẫn:</b>\n"
            f"  Mở app Locket → Bấm Avatar góc trên → Xem phần <b>@username</b>\n\n"
            f"<i>Ví dụ:</i> <code>conlaigii</code>\n\n"
            f"👇 <b>Gửi Username Locket của bạn vào ô chat bên dưới:</b>\n"
            f"💡 <i>(Nếu có mã giảm giá, bạn có thể gửi kèm, ví dụ: <code>username MÃ_GIẢM_GIÁ</code>)</i>"
        )
    elif product_key in ("combo", "locket_spotify"):
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> 👑 <b>Combo Duo VIP — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code> <i>(Tiết kiệm tới 81.000đ)</i>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✨ <b>TÍNH NĂNG NỔI BẬT:</b>\n"
            f"• Trọn bộ tính năng Locket Gold VIP (Viền vàng, 60s, 4K gốc)\n"
            f"• Spotify nghe nhạc không quảng cáo, Lossless 320kbps\n"
            f"• Chuyển bài không giới hạn, phát nhạc theo thứ tự tuỳ thích\n"
            f"• Kích hoạt đồng thời cả 2 tài khoản qua 1 DNS chính chủ duy nhất!\n\n"
            f"📌 <b>BƯỚC 1: GỬI THÔNG TIN 2 DÒNG (LOCKET & SPOTIFY)</b>\n\n"
            f"<b>Vui lòng gửi tin nhắn gồm 2 dòng:</b>\n"
            f"1️⃣ <b>Dòng 1:</b> Username Locket (Chỉ điền Username, không dán link — VD: <code>conlaigii</code>)\n"
            f"2️⃣ <b>Dòng 2:</b> Link Profile Spotify (Bắt buộc dạng Link — VD: <code>https://open.spotify.com/user/...</code>)\n\n"
            f"<i>Ví dụ gửi đúng mẫu:</i>\n"
            f"<pre>conlaigii\nhttps://open.spotify.com/user/31xxxxxxxxxx</pre>\n\n"
            f"👇 <b>Gửi 2 dòng thông tin vào ô chat bên dưới:</b>"
        )
    else:  # locket
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI USERNAME LOCKET (CHỈ ĐIỀN USER, KHÔNG DÁN LINK)</b>\n\n"
            f"<b>Hướng dẫn:</b>\n"
            f"  Mở app Locket → Bấm Avatar góc trên → Xem phần <b>@username</b>\n\n"
            f"<i>Ví dụ:</i> <code>conlaigii</code>\n\n"
            f"👇 <b>Gửi Username Locket của bạn vào ô chat bên dưới:</b>\n"
            f"💡 <i>(Nếu có mã giảm giá, bạn có thể gửi kèm, ví dụ: <code>username MÃ_GIẢM_GIÁ</code> hoặc bấm nút nhập mã sau khi hoá đơn xuất hiện)</i>"
        )

    try:
        await query.edit_message_text(
            prompt, parse_mode=ParseMode.HTML,
            reply_markup=back_to_plan_kb(product_key)
        )
    except Exception as e:
        logger.warning(f"edit_message_text in cb_plan: {e}")
        try:
            await query.message.reply_text(
                prompt, parse_mode=ParseMode.HTML,
                reply_markup=back_to_plan_kb(product_key)
            )
        except Exception:
            pass
    return WAITING_IDENTIFIER


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 2: Nhận identifier → Xác thực Profile → Hiện hoá đơn & QR thanh toán
# ═══════════════════════════════════════════════════════════════════════════════

async def receive_identifier(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw_text = update.message.text.strip()
    tokens = raw_text.split()
    coupon_candidate = None
    product_key_pre = ctx.user_data.get("product")
    plan_key_pre = ctx.user_data.get("plan")
    prods = getattr(utils, "get_dynamic_products", lambda: PRODUCTS)()
    base_price = 0
    if product_key_pre and plan_key_pre:
        base_price = prods.get(product_key_pre, {}).get("plans", {}).get(plan_key_pre, {}).get("price", 0)

    if len(tokens) >= 2 and base_price > 0:
        potential = tokens[-1].strip().upper()
        chk = utils.check_and_apply_coupon(potential, base_price)
        if chk.get("ok"):
            coupon_candidate = chk
            raw_identifier = " ".join(tokens[:-1]).strip()
        else:
            raw_identifier = raw_text
    else:
        raw_identifier = raw_text
    product_key = ctx.user_data.get("product")
    plan_key    = ctx.user_data.get("plan")

    if not product_key or not plan_key:
        await update.message.reply_text(
            "⚠️ Phiên làm việc đã hết hạn. Vui lòng bấm bên dưới để bắt đầu lại:",
            reply_markup=main_menu_kb()
        )
        return ConversationHandler.END

    pv   = prods.get(product_key, PRODUCTS[product_key])
    plnv = pv["plans"][plan_key]

    checking_msg = await update.message.reply_text(
        f"🔍 <b>Đang kiểm tra tài khoản & Profile {pv['name']} trên hệ thống…</b>\nVui lòng chờ trong giây lát.",
        parse_mode=ParseMode.HTML
    )

    try:
        avatar_url = None
        spotify_extra_info = ""

        extra_order_fields = {}
        import re
        if product_key in ("combo", "locket_spotify"):
            # Yêu cầu gửi cả 2 thông tin: Dòng 1 Locket Username, Dòng 2 Link Profile Spotify
            lines = [l.strip() for l in raw_identifier.splitlines() if l.strip()]
            locket_part = ""
            spotify_part = ""

            if len(lines) >= 2:
                if re.search(r"spotify\.com", lines[1], re.I):
                    locket_part = lines[0]
                    spotify_part = lines[1]
                elif re.search(r"spotify\.com", lines[0], re.I):
                    spotify_part = lines[0]
                    locket_part = lines[1]
                else:
                    locket_part = lines[0]
                    spotify_part = lines[1]
            else:
                parts = raw_identifier.split()
                if len(parts) >= 2:
                    if re.search(r"spotify\.com", parts[1], re.I):
                        locket_part = parts[0]
                        spotify_part = parts[1]
                    elif re.search(r"spotify\.com", parts[0], re.I):
                        spotify_part = parts[0]
                        locket_part = parts[1]
                    else:
                        locket_part = parts[0]
                        spotify_part = parts[1]
                else:
                    raise ValueError(
                        "Gói Combo Duo VIP yêu cầu gửi đủ 2 dòng thông tin:\n"
                        "• Dòng 1: Username Locket (chỉ điền User, không dán link)\n"
                        "• Dòng 2: Link Profile Spotify (VD: https://open.spotify.com/user/...)\n\n"
                        "Vui lòng gửi lại đúng theo cú pháp 2 dòng trên!"
                    )

            # 1. Xác thực Locket
            if re.search(r"(https?://|/|spotify\.com|locket\.cam)", locket_part, re.I):
                raise ValueError("Dòng 1 (Locket) chỉ được điền Username Locket (VD: conlaigii), tuyệt đối không dán đường link!")
            cleaned_username = utils.clean_input(locket_part)
            res_lk = await asyncio.to_thread(api.locket_resolve, cleaned_username)
            data_lk = res_lk.get("data") if isinstance(res_lk.get("data"), dict) else res_lk
            locket_username = data_lk.get("username") or cleaned_username
            locket_avatar = data_lk.get("avatar") or data_lk.get("avatarUrl")

            # 2. Xác thực Spotify
            if not re.search(r"spotify\.com/user/[a-zA-Z0-9._-]+", spotify_part, re.I):
                raise ValueError("Dòng 2 (Spotify) bắt buộc phải dán đúng Link Profile Spotify (VD: https://open.spotify.com/user/...)!")
            cleaned_sp = utils.extract_spotify_uid(spotify_part)
            res_sp = await asyncio.to_thread(api.spotify_check, spotify_part)
            data_sp = res_sp.get("data") if isinstance(res_sp.get("data"), dict) else res_sp
            sp_uid = data_sp.get("uid") or data_sp.get("id") or cleaned_sp
            sp_display = data_sp.get("displayName") or data_sp.get("username") or data_sp.get("name") or sp_uid
            sp_avatar = data_sp.get("avatar") or data_sp.get("image") or data_sp.get("avatarUrl")
            sp_plan = data_sp.get("plan") or data_sp.get("product") or "Free"

            uid = f"{locket_username} | {sp_uid}"
            display = f"Locket: @{locket_username} | Spotify: {sp_display}"
            avatar_url = locket_avatar or sp_avatar
            spotify_extra_info = (
                f"🟡 <b>Locket Username:</b> <code>@{locket_username}</code>\n"
                f"🎵 <b>Spotify Profile:</b> <code>{sp_display}</code> (UID: <code>{sp_uid}</code>)\n"
                f"🏷 <b>Gói Spotify hiện tại:</b> <code>{sp_plan}</code>\n"
            )
            extra_order_fields = {
                "account_target": locket_username,
                "locket_username": locket_username,
                "spotify_uid": sp_uid,
                "avatar": avatar_url,
            }
        elif product_key == "spotify":
            if not re.search(r"spotify\.com/user/[a-zA-Z0-9._-]+", raw_identifier, re.I):
                raise ValueError("Phần Spotify chỉ nhận Link Profile Spotify (VD: https://open.spotify.com/user/...). Vui lòng sao chép liên kết hồ sơ từ ứng dụng Spotify!")
            cleaned_sp = utils.extract_spotify_uid(raw_identifier)
            res = await asyncio.to_thread(api.spotify_check, raw_identifier)
            data = res.get("data") if isinstance(res.get("data"), dict) else res
            uid  = data.get("uid") or data.get("id") or cleaned_sp
            display = data.get("displayName") or data.get("username") or data.get("name") or uid
            avatar_url = data.get("avatar") or data.get("image") or data.get("avatarUrl")
            current_plan = data.get("plan") or data.get("product") or "Free"
            is_bound = data.get("isBound")

            bound_text = "Đã kết nối IP thiết bị" if is_bound else "Chưa khoá IP (sẵn sàng)"

            spotify_extra_info = (
                f"🏷 <b>Gói hiện tại:</b> <code>{current_plan}</code>\n"
                f"📶 <b>Phiên IP:</b> <i>{bound_text}</i>\n"
            )
            extra_order_fields = {
                "account_target": uid or cleaned_sp,
                "spotify_uid": uid or cleaned_sp,
                "avatar": avatar_url,
            }
        else:
            if re.search(r"(https?://|/|spotify\.com|locket\.cam)", raw_identifier, re.I):
                raise ValueError("Phần Locket chỉ cho phép điền Username Locket (VD: conlaigii), tuyệt đối không dán đường link!")
            cleaned_username = utils.clean_input(raw_identifier)
            res = await asyncio.to_thread(api.locket_resolve, cleaned_username)
            data = res.get("data") if isinstance(res.get("data"), dict) else res
            locket_username = data.get("username") or cleaned_username
            uid  = data.get("uid") or data.get("id") or locket_username
            display = locket_username
            avatar_url = data.get("avatar") or data.get("avatarUrl")
            extra_order_fields = {
                "account_target": locket_username,
                "locket_username": locket_username,
                "avatar": avatar_url,
            }

        # Chặn dùng thử Test 3 Ngày lần 2 trên cùng một tài khoản
        if plan_key == "test" or str(plnv.get("packageCode") or "").upper() in ("LKGT3D", "SPT"):
            trial_cands = [
                uid, raw_identifier, display,
                extra_order_fields.get("locket_username", ""),
                extra_order_fields.get("spotify_uid", ""),
                extra_order_fields.get("account_target", ""),
            ]
            if utils.has_used_test_trial(product_key, trial_cands):
                raise ValueError("Mỗi tài khoản chỉ được dùng thử gói Test 3 Ngày 1 lần! Tài khoản này đã dùng thử trước đó — vui lòng bấm Quay lại để chọn gói 6 Tháng, 1 Năm hoặc Vĩnh Viễn.")

        # Tính toán giá sau giảm nếu khách gửi kèm mã giảm giá
        orig_price = plnv["price"]
        final_price = orig_price
        discount_amount = 0
        applied_coupon_code = ""
        discount_desc = ""

        if coupon_candidate and coupon_candidate.get("ok"):
            final_price = coupon_candidate["final_price"]
            discount_amount = coupon_candidate["discount_amount"]
            applied_coupon_code = coupon_candidate["code"]
            discount_desc = coupon_candidate.get("desc", "")

        extra_order_fields["discount_code"] = applied_coupon_code
        extra_order_fields["discount_amount"] = discount_amount
        extra_order_fields["original_price"] = orig_price

        # Tạo đơn hàng vào cơ sở dữ liệu
        order_id = utils.gen_order_id()
        user     = update.effective_user
        db.create_order(
            order_id=order_id,
            user_id=user.id,
            username=user.username or user.first_name,
            product=product_key,
            plan=plan_key,
            price=final_price,
            uid=uid,
            display_name=display,
            **extra_order_fields
        )
        db.update_order(order_id, expected_statuses=("pending",), status="waiting_payment")
        ctx.user_data["order_id"] = order_id

        await checking_msg.delete()

        # Tạo ảnh QR VietQR chuẩn
        transfer_memo = f"ORDER_{order_id}"
        qr_url = utils.get_vietqr_url(final_price, transfer_memo)
        bank_id = getattr(config, "BANK_ID", "TPB")
        account_no = getattr(config, "ACCOUNT_NO", "")
        account_name = getattr(config, "ACCOUNT_NAME", "")

        if applied_coupon_code and discount_amount > 0:
            price_line = (
                f"💵 <b>Giá gốc:</b> <s>{utils.fmt_price(orig_price)}</s>\n"
                f"🎟 <b>Mã giảm giá:</b> <code>{applied_coupon_code}</code> <i>({discount_desc})</i>\n"
                f"🔥 <b>Cần thanh toán:</b> <b>{utils.fmt_price(final_price)}</b> (-{utils.fmt_price(discount_amount)})\n"
            )
        else:
            price_line = f"💵 <b>Số tiền:</b> <b>{utils.fmt_price(final_price)}</b>\n"

        caption = (
            f"🧾 <b>HOÁ ĐƠN THANH TOÁN #{order_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Dịch vụ:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
            f"👤 <b>Tài khoản:</b> <b>{display}</b>\n"
            f"🆔 <b>UID:</b> <code>{uid}</code>\n"
            f"{spotify_extra_info}"
            f"{price_line}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Ngân hàng:</b> <b>{bank_id}</b>\n"
            f"🔢 <b>Số tài khoản:</b> <code>{account_no}</code>\n"
            f"👤 <b>Chủ tài khoản:</b> <b>{account_name}</b>\n"
            f"📝 <b>Nội dung CK:</b> <code>{transfer_memo}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>LƯU Ý:</b>\n"
            f"• Thời gian chuyển khoản là <b>5 phút</b> (đơn sẽ tự động hủy nếu quá hạn).\n"
            f"• Quét mã QR để chuyển khoản chính xác số tiền & nội dung.\n"
            f"• Hệ thống tự động kích hoạt ngay khi nhận tiền hoặc bấm nút <b>\"✅ Tôi đã chuyển khoản\"</b> bên dưới!"
        )

        try:
            await update.message.reply_photo(
                photo=qr_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=payment_kb(order_id, applied_coupon=applied_coupon_code)
            )
        except Exception as e:
            logger.error(f"Error sending QR photo: {e}")
            await update.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=payment_kb(order_id, applied_coupon=applied_coupon_code)
            )

        return ConversationHandler.END

    except Exception as e:
        logger.warning("Account check failed for %s: %s", product_key, type(e).__name__)
        message = str(e) if isinstance(e, ValueError) else "Chưa thể kiểm tra tài khoản. Vui lòng thử lại."
        await checking_msg.edit_text(
            f"❌ {escape(message)}\n\nHãy gửi lại thông tin tài khoản cho gói đã chọn.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_plan_kb(product_key),
        )
        return WAITING_IDENTIFIER


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 3: Khách bấm "Tôi đã chuyển khoản" → Báo Admin duyệt
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order or order.get("user_id") != query.from_user.id:
        await query.answer("Không tìm thấy đơn hàng của bạn.", show_alert=True)
        return
    await query.answer("Đang kiểm tra giao dịch…")

    from order_service import check_sepay_payments
    try:
        await check_sepay_payments(ctx.bot, order_id)
    except Exception:
        logger.warning("Could not check payment for %s", order_id)
    order = db.get_order(order_id)
    status = order.get("status")
    if status in ("paid_review", "done", "cancelled", "rejected", "pending_approval"):
        await show_order_details(query.message, order)
        return
    if not db.update_order(order_id, expected_statuses=("pending", "waiting_payment"), status="pending_approval"):
        await show_order_details(query.message, db.get_order(order_id))
        return

    pv = PRODUCTS.get(order["product"], {"name": "Studio", "emoji": "🎨"})
    plnv = pv.get("plans", {}).get(order["plan"], {"label": "Studio"})
    customer_msg = (
        f"⏳ <b>XÁC NHẬN THANH TOÁN ĐÃ ĐƯỢC GỬI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Mã đơn hàng:</b> <code>ORDER_{order_id}</code>\n"
        f"📦 <b>Dịch vụ:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
        f"👤 <b>Tài khoản:</b> <b>{order['display_name']}</b>\n"
        f"💰 <b>Số tiền:</b> <b>{utils.fmt_price(order['price'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Hệ thống chưa xác nhận được giao dịch. Hãy giữ mã đơn để đối soát."
    )
    try:
        await query.edit_message_caption(customer_msg, parse_mode=ParseMode.HTML, reply_markup=pending_approval_kb())
    except Exception:
        await query.edit_message_text(customer_msg, parse_mode=ParseMode.HTML, reply_markup=pending_approval_kb())

    # Gửi thông báo đến Admin
    from config import ADMIN_IDS
    admin_text = (
        f"🔔 <b>YÊU CẦU DUYỆT ĐƠN HÀNG MỚI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Mã đơn:</b> <code>ORDER_{order_id}</code>\n"
        f"👤 <b>Khách:</b> @{order['username']} (ID: <code>{order['user_id']}</code>)\n"
        f"📦 <b>Dịch vụ:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
        f"🎯 <b>Tài khoản nạp:</b> <b>{order['display_name']}</b>\n"
        f"🆔 <b>UID:</b> <code>{order['uid']}</code>\n"
        f"💰 <b>Số tiền:</b> <b>{utils.fmt_price(order['price'])}</b>\n"
        f"📝 <b>Nội dung CK:</b> <code>ORDER_{order_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Kiểm tra tài khoản {getattr(config, 'BANK_NAME', 'TPBank')} và chọn hành động:"
    )
    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.send_message(
                admin_id,
                admin_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_approval_kb(order_id)
            )
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")


async def cb_ai_studio_opt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xử lý lựa chọn Có / Không thêm Studio (+10.000đ) khi mua gói Locket Gold & AI Filters VIP."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    choice = parts[1]   # "yes" hoặc "no"
    order_id = parts[2]
    order = db.get_order(order_id)
    if not order:
        await query.answer("❌ Không tìm thấy đơn hàng!", show_alert=True)
        return

    has_studio = (choice == "yes")
    base_price = order.get("original_price") or PRODUCTS.get("locket_ai", {}).get("plans", {}).get("ltm", {}).get("price", 250000)
    discount_amount = order.get("discount_amount", 0)
    applied_coupon_code = order.get("discount_code", "")

    final_price = (base_price - discount_amount) + (10000 if has_studio else 0)

    db.update_order(
        order_id,
        price=final_price,
        has_studio=has_studio,
        studio_addon=has_studio
    )

    transfer_memo = f"ORDER_{order_id}"
    qr_url = utils.get_vietqr_url(final_price, transfer_memo)
    bank_id = getattr(config, "BANK_ID", "TPB")
    account_no = getattr(config, "ACCOUNT_NO", "")
    account_name = getattr(config, "ACCOUNT_NAME", "")

    pv = PRODUCTS.get("locket_ai", {"name": "Locket Gold & AI Filters VIP", "emoji": "✨"})
    plnv = pv.get("plans", {}).get("ltm", {"label": "Vĩnh Viễn"})

    studio_line = "🎨 <b>Gói Studio thêm:</b> <b>Đã chọn (+10.000đ)</b> ✓\n" if has_studio else ""

    caption = (
        f"🧾 <b>HOÁ ĐƠN THANH TOÁN #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Dịch vụ:</b> {pv.get('emoji', '✨')} {pv.get('name')} — {plnv.get('label')}\n"
        f"👤 <b>Tài khoản:</b> <b>{order.get('display_name')}</b>\n"
        f"🆔 <b>UID:</b> <code>{order.get('uid')}</code>\n"
        f"{studio_line}"
        f"💵 <b>Số tiền thanh toán:</b> <b>{utils.fmt_price(final_price)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>Ngân hàng:</b> <b>{bank_id}</b>\n"
        f"🔢 <b>Số tài khoản:</b> <code>{account_no}</code>\n"
        f"👤 <b>Chủ tài khoản:</b> <b>{account_name}</b>\n"
        f"📝 <b>Nội dung CK:</b> <code>{transfer_memo}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>LƯU Ý:</b>\n"
        f"• Quét mã QR để chuyển khoản chính xác số tiền & nội dung.\n"
        f"• Chuyển tiền xong, bấm nút <b>\"✅ Tôi đã chuyển khoản\"</b> bên dưới để Admin duyệt và nhận link cấu hình VIP!"
    )

    try:
        await query.message.reply_photo(
            photo=qr_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(order_id, applied_coupon=applied_coupon_code)
        )
        try:
            await query.message.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error replying QR photo in cb_ai_studio_opt: {e}")
        await query.message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(order_id, applied_coupon=applied_coupon_code)
        )


async def cb_buy_studio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Khách hàng đã mua gói VIP bấm thêm Studio Chỉnh Chú Thích & Khung Viền (+10.000đ)."""
    query = update.callback_query
    await query.answer()
    order_id = query.data.split(":")[1]
    parent_order = db.get_order(order_id)
    if not parent_order:
        await query.answer("❌ Không tìm thấy thông tin đơn hàng gốc!", show_alert=True)
        return

    user = update.effective_user
    sub_order_id = utils.gen_order_id()
    studio_price = getattr(config, "STUDIO_CAPTION_PRICE", 10000)

    db.create_order(
        order_id=sub_order_id,
        user_id=user.id,
        username=user.username or user.first_name,
        product="studio_caption",
        plan="extra",
        price=studio_price,
        uid=parent_order.get("uid"),
        display_name=parent_order.get("display_name"),
        parent_order_id=order_id
    )
    db.update_order(sub_order_id, expected_statuses=("pending",), status="waiting_payment")

    transfer_memo = f"ORDER_{sub_order_id}"
    qr_url = utils.get_vietqr_url(studio_price, transfer_memo)
    bank_id = getattr(config, "BANK_ID", "TPB")
    account_no = getattr(config, "ACCOUNT_NO", "")
    account_name = getattr(config, "ACCOUNT_NAME", "")

    caption = (
        f"🎨 <b>MỞ KHÓA STUDIO CHỈNH CHÚ THÍCH & ĐỔI KHUNG VIỀN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Mã đơn:</b> <code>ORDER_{sub_order_id}</code>\n"
        f"👤 <b>Tài khoản Locket:</b> <b>@{parent_order.get('display_name') or parent_order.get('uid')}</b>\n"
        f"💵 <b>Số tiền thanh toán:</b> <b>{utils.fmt_price(studio_price)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>Ngân hàng:</b> <b>{bank_id}</b>\n"
        f"🔢 <b>Số tài khoản:</b> <code>{account_no}</code>\n"
        f"👤 <b>Chủ tài khoản:</b> <b>{account_name}</b>\n"
        f"📝 <b>Nội dung CK:</b> <code>{transfer_memo}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 <i>Sau khi chuyển khoản thành công, bấm nút <b>'✅ Tôi đã chuyển khoản'</b> bên dưới để nhận Link Studio ngay nhé!</i>"
    )

    try:
        await query.message.reply_photo(
            photo=qr_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(sub_order_id)
        )
    except Exception as e:
        logger.error(f"Error sending studio QR: {e}")
        await query.message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(sub_order_id)
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 4: Hướng dẫn cài đặt cấu hình DNS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_success_message(order, pv, plnv, dns_link: str) -> str:
    is_test = order.get("plan") == "test" or plnv.get("packageCode") in ["LKGT3D", "SPT"]
    if is_test:
        days = int(order.get("duration_days") or plnv.get("durationDays") or 3)
        hours = days * 24
        exp_line = f"📅 <b>Hết hạn lúc:</b> <code>{utils.fmt_datetime(order['expires_at'])}</code>\n" if order.get("expires_at") else ""
        duration_note = (
            f"⏱️ <b>Thời hạn dùng thử:</b> <b>{days} Ngày ({hours} Giờ)</b>\n"
            f"{exp_line}"
            f"⚠️ <i>Lưu ý: Sau đúng {days} ngày, gói dùng thử sẽ tự động hết hạn (bạn có thể gia hạn bất cứ lúc nào).</i>"
        )
    else:
        duration_note = f"💡 <i>Chỉ cần cài 1 lần là dùng theo thời hạn gói. Nếu đổi thiết bị hãy nhắn Admin để reset.</i>"

    if order["product"] in ("combo", "locket_spotify"):
        dns_vip = order.get("dns_link") or getattr(config, "DNS_COMBO_URL", f"{config.DNS_BASE_URL}/{config.DNS_SLUG}")
        step4 = (
            f"📌 <b>BƯỚC CÀI ĐẶT CẤU HÌNH COMBO DUO VIP (LOCKET & SPOTIFY):</b>\n"
            f"1️⃣ Mở trình duyệt <b>Safari</b> trên iPhone và truy cập link DNS:\n"
            f"   👉 <code>{dns_vip}</code>\n"
            f"2️⃣ Bấm <b>Cho phép (Allow)</b> khi thông báo tải hồ sơ xuất hiện\n"
            f"3️⃣ Mở <b>Cài đặt iPhone</b> → <b>Đã tải về hồ sơ</b> → Bấm <b>Cài đặt</b>\n"
            f"4️⃣ Vào <b>Cài đặt chung</b> → <b>Giới thiệu</b> → Kéo xuống cuối → <b>Cài đặt tin cậy chứng nhận</b> → Bật xanh <b>LocketGold</b>\n"
            f"5️⃣ Mở đồng thời cả Locket và Spotify lên và tận hưởng trọn bộ tính năng VIP (Locket Gold 4K gốc, video 60s, Spotify nghe nhạc không quảng cáo)! 🎉\n\n"
            f"{duration_note}"
        )

    elif order["product"] == "spotify":
        step4 = (
            f"📌 <b>BƯỚC 4: CÀI ĐẶT CẤU HÌNH DNS SPOTIFY:</b>\n"
            f"1️⃣ Mở trình duyệt <b>Safari</b> trên iPhone và truy cập link DNS của bạn:\n"
            f"   👉 <code>{dns_link}</code>\n"
            f"2️⃣ Bấm <b>Cho phép tải về hồ sơ</b>\n"
            f"3️⃣ Mở <b>Cài đặt iPhone</b> → Chọn <b>Đã tải về hồ sơ</b> → Bấm <b>Cài đặt</b>\n"
            f"4️⃣ Vào <b>Cài đặt chung</b> → <b>Giới thiệu</b> → Kéo xuống cuối → <b>Cài đặt tin cậy chứng nhận</b> → Bật tin cậy chứng chỉ\n"
            f"5️⃣ Mở app Spotify và tận hưởng Premium không quảng cáo! 🎉\n\n"
            f"🛡 <b>Cơ chế dùng & đổi thiết bị:</b>\n"
            f"• <i>Hệ thống phát nhạc 1 thiết bị/IP tại 1 thời điểm.</i>\n"
            f"• <i>Tự động đổi mạng (Wifi/4G) & đổi máy: Dừng phát ở máy cũ, sau 25s máy mới tự động nhận quyền nghe hoàn toàn mà <b>không cần thao tác thủ công</b>!</i>\n"
            f"• <i>Nếu cần giải phóng phiên gấp khi đổi máy ngay lập tức, gõ lệnh <code>/resetspotify</code> hoặc liên hệ CSKH.</i>\n\n"
            f"{duration_note}"
        )
    elif order["product"] == "filter_topup":
        step4 = (
            f"🎭 <b>TRẠNG THÁI NẠP LƯỢT FILTER AI:</b>\n"
            f"• Hệ thống đã xác nhận thanh toán tự động cho gói <b>{plnv['label']}</b>.\n"
            f"• Admin đang cộng lượt chụp AI Filter trực tiếp vào tài khoản Locket của bạn (thường xong trong 1–3 phút).\n"
            f"• Mọi lượt mua thêm sẽ được cộng dồn trực tiếp và không bị reset theo tháng."
        )
    elif order["product"] == "caption_pack":
        step4 = (
            f"💬 <b>TRẠNG THÁI GÓI THÊM CAPTION VIP:</b>\n"
            f"• Hệ thống đã tự động cộng lượt tạo Caption mới (<b>{plnv['label']}</b>) vào tài khoản của bạn.\n"
            f"• Hãy quay lại mục <b>Tính Năng VIP → Caption Chú Thích</b> trên website để tạo thêm Caption ngay!"
        )
    else:
        step4 = (
            f"📌 <b>BƯỚC CÀI ĐẶT CẤU HÌNH DNS PROFILE:</b>\n"
            f"1️⃣ Mở trình duyệt <b>Safari</b> trên iPhone và truy cập link:\n"
            f"   👉 <code>{dns_link}</code>\n"
            f"2️⃣ Bấm <b>Cho phép tải về hồ sơ cấu hình</b>\n"
            f"3️⃣ Mở <b>Cài đặt iPhone</b> → <b>Đã tải về hồ sơ</b> → Bấm <b>Cài đặt</b>\n"
            f"4️⃣ Vào <b>Cài đặt</b> → <b>Cài đặt chung</b> → <b>Giới thiệu</b> → Kéo xuống cuối → Bấm <b>Cài đặt tin cậy chứng nhận</b> → Bật <b>LocketGold</b>\n"
            f"5️⃣ Mở app Locket và tận hưởng full tính năng Locket Gold! 🎉\n\n"
            f"{duration_note}"
        )

    return (
        f"🎉 <b>ĐƠN HÀNG ĐÃ ĐƯỢC KÍCH HOẠT THÀNH CÔNG!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Gói:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
        f"👤 <b>Tài khoản:</b> <b>{order['display_name']}</b>\n"
        f"🆔 <b>UID:</b> <code>{order['uid']}</code>\n"
        f"💰 <b>Đã thanh toán:</b> <b>{utils.fmt_price(order['price'])}</b>\n"
        f"🧾 <b>Mã đơn hàng:</b> <code>{order['order_id']}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{step4}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✨ <i>Cảm ơn bạn đã tin tưởng và đồng hành cùng shop!</i>"
    )


async def cb_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Fallback nếu dùng nút mua trực tiếp."""
    query = update.callback_query
    await query.answer()
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order:
        await query.edit_message_caption("❌ Không tìm thấy đơn hàng.")
        return
    await query.answer("Vui lòng chuyển khoản và bấm 'Tôi đã chuyển khoản' để Admin duyệt!", show_alert=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  HUỶ ĐƠN HÀNG
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order or order.get("user_id") != query.from_user.id:
        await query.answer("Không tìm thấy đơn hàng của bạn.", show_alert=True)
        return
    if not db.update_order(order_id, expected_statuses=("pending", "waiting_payment"), status="cancelled"):
        await query.answer("Đơn đã chuyển trạng thái. Hãy mở Đơn hàng của tôi để kiểm tra.", show_alert=True)
        return
    await query.answer()
    cancel_text = (
        f"❌ <b>ĐÃ HUỶ ĐƠN HÀNG</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Đơn hàng <code>ORDER_{order_id}</code> đã được huỷ bỏ theo yêu cầu của bạn.\n\n"
        f"Bạn có thể chọn gói dịch vụ khác bất kỳ lúc nào:"
    )
    try:
        await query.message.delete()
        await query.message.reply_text(
            cancel_text,
            parse_mode=ParseMode.HTML,
            reply_markup=orders_kb()
        )
    except Exception:
        try:
            await query.edit_message_caption(
                cancel_text,
                parse_mode=ParseMode.HTML,
                reply_markup=orders_kb()
            )
        except Exception:
            await query.edit_message_text(
                cancel_text,
                parse_mode=ParseMode.HTML,
                reply_markup=orders_kb()
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  ĐƠN HÀNG CỦA TÔI
# ═══════════════════════════════════════════════════════════════════════════════

def render_customer_orders(user_id: int):
    orders = sorted(db.get_user_orders(user_id), key=lambda o: o.get("created_at") or "", reverse=True)[:10]
    if not orders:
        return "Bạn chưa có đơn hàng nào.", orders_kb()

    lines = ["📦 <b>ĐƠN HÀNG CỦA TÔI</b>"]
    rows = []
    for order in orders:
        order_id = order["order_id"]
        product = PRODUCTS.get(order.get("product"), {})
        name = product.get("name", "Studio" if order.get("product") == "studio_caption" else "Dịch vụ")
        lines.append(
            f"<b>ORDER_{escape(order_id)}</b> · {escape(name)} · {utils.fmt_price(order.get('price', 0))}\n"
            f"{customer_order_status(order)}"
        )
        rows.append([InlineKeyboardButton(f"Xem đơn {order_id}", callback_data=f"order_details:{order_id}")])
    has_done = any(o.get("status") == "done" for o in orders)
    has_spotify = any("spotify" in o.get("product", "") for o in orders)
    rows.extend(orders_kb(has_done_order=has_done, has_spotify=has_spotify).inline_keyboard)
    return "\n\n".join(lines), InlineKeyboardMarkup(rows)


def customer_order_status(order: dict) -> str:
    from order_service import payment_deadline
    import time

    status = order.get("status")
    if status in ("pending", "waiting_payment"):
        deadline = payment_deadline(order)
        if deadline is not None and time.time() >= deadline:
            return "Hết hạn chuyển khoản"
    if status == "cancelled" and order.get("cancel_reason"):
        return "Hết hạn chuyển khoản"
    return {
        "done": "Hoàn tất", "pending_approval": "Đang kiểm tra giao dịch",
        "paid_review": "Đã nhận tiền · đang đối soát", "cancelled": "Đã hủy",
        "rejected": "Đã từ chối", "failed": "Cần hỗ trợ",
    }.get(status, "Chờ chuyển khoản")


async def show_order_details(message, order: dict):
    order_id = order["order_id"]
    status_text = customer_order_status(order)
    text = (
        f"<b>ORDER_{escape(order_id)}</b>\n{status_text}\n"
        f"Số tiền: <b>{utils.fmt_price(order.get('price', 0))}</b>"
    )
    if status_text == "Chờ chuyển khoản":
        memo = f"ORDER_{order_id}"
        text += (
            f"\nNgân hàng: {escape(str(getattr(config, 'BANK_NAME', 'TPBank')))}"
            f"\nSố tài khoản: <code>{escape(str(config.ACCOUNT_NO))}</code>"
            f"\nChủ tài khoản: {escape(str(config.ACCOUNT_NAME))}"
            f"\nNội dung: <code>{escape(memo)}</code>"
        )
        markup = payment_kb(order_id, applied_coupon=order.get("discount_code"))
        try:
            await message.reply_photo(
                utils.get_vietqr_url(order["price"], memo), caption=text,
                parse_mode=ParseMode.HTML, reply_markup=markup,
            )
            return
        except Exception:
            logger.warning("Could not send payment QR for %s", order_id)
    else:
        text += "\nNếu cần hỗ trợ, gửi kèm mã đơn ở trên."
        rows = [[InlineKeyboardButton("Liên hệ hỗ trợ", callback_data="support")]]
        if order.get("status") in ("cancelled", "pending", "waiting_payment", "pending_approval"):
            rows.insert(0, [InlineKeyboardButton("Kiểm tra giao dịch", callback_data=f"paid:{order_id}")])
        rows.append([InlineKeyboardButton("Đơn hàng của tôi", callback_data="my_orders")])
        markup = InlineKeyboardMarkup(rows)
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def cb_order_details(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order = db.get_order(query.data.split(":", 1)[1])
    if not order or order.get("user_id") != query.from_user.id:
        await query.answer("Không tìm thấy đơn hàng của bạn.", show_alert=True)
        return
    await query.answer()
    await show_order_details(query.message, order)


async def myorders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text, markup = render_customer_orders(update.effective_user.id)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def cb_my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text, markup = render_customer_orders(query.from_user.id)
    if query.message.text is None:
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def support_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    support_text = (
        "💬 <b>TRUNG TÂM HỖ TRỢ KHÁCH HÀNG 24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Đội ngũ kỹ thuật luôn sẵn sàng hỗ trợ bạn kích hoạt và giải quyết mọi thắc mắc:\n\n"
        "👤 <b>Admin hỗ trợ:</b> Như Quỳnh\n"
        "📞 <b>Hotline / Zalo:</b> <code>0345.222.802</code>\n"
        "✈️ <b>Telegram cá nhân:</b> <a href=\"https://t.me/nguyennhuquynh28\">@nguyennhuquynh28 (Click để chat)</a>\n"
        "⏰ <b>Thời gian làm việc:</b> 08:00 - 24:00 (Hàng ngày)\n"
        "🛡 <b>Chính sách cam kết:</b> Bảo hành 1-1 trọn đời gói mua\n\n"
        "💡 <i>Gửi kèm Mã đơn hàng hoặc ảnh chụp màn hình để được xử lý nhanh nhất!</i>"
    )
    await update.message.reply_text(
        support_text,
        parse_mode=ParseMode.HTML,
        reply_markup=support_kb()
    )


async def cb_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    support_text = (
        "💬 <b>TRUNG TÂM HỖ TRỢ KHÁCH HÀNG 24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Đội ngũ kỹ thuật luôn sẵn sàng hỗ trợ bạn kích hoạt và giải quyết mọi thắc mắc:\n\n"
        "👤 <b>Admin hỗ trợ:</b> Như Quỳnh\n"
        "📞 <b>Hotline / Zalo:</b> <code>0345.222.802</code>\n"
        "✈️ <b>Telegram cá nhân:</b> <a href=\"https://t.me/nguyennhuquynh28\">@nguyennhuquynh28 (Click để chat)</a>\n"
        "⏰ <b>Thời gian làm việc:</b> 08:00 - 24:00 (Hàng ngày)\n"
        "🛡 <b>Chính sách cam kết:</b> Bảo hành 1-1 trọn đời gói mua\n\n"
        "💡 <i>Gửi kèm Mã đơn hàng hoặc ảnh chụp màn hình để được xử lý nhanh nhất!</i>"
    )
    try:
        await query.edit_message_text(
            support_text,
            parse_mode=ParseMode.HTML,
            reply_markup=support_kb()
        )
    except Exception:
        await query.message.reply_text(
            support_text,
            parse_mode=ParseMode.HTML,
            reply_markup=support_kb()
        )


async def zalo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /zalo – Nhóm Hỗ Trợ & Giao Lưu Zalo."""
    from keyboards import zalo_group_kb
    qr_filename = getattr(config, "ZALO_GROUP_QR", "zalo_group_qr.png")
    qr_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), qr_filename)
    if not os.path.exists(qr_path):
        qr_path = os.path.join(os.getcwd(), qr_filename)

    caption = (
        "👥 <b>NHÓM HỖ TRỢ & GIAO LƯU ZALO — ALOPREMIUM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tham gia cộng đồng Zalo chính thức của shop để:\n"
        "• ⚡ Cập nhật chứng chỉ DNS & thông báo iOS mới nhất\n"
        "• 🛡 Được hỗ trợ kích hoạt, bảo hành 1-1 trực tiếp 24/7\n"
        "• 🎁 Nhận mã giảm giá độc quyền & GiveAway hàng tuần\n"
        "• 💬 Giao lưu và chia sẻ mẹo sử dụng Locket Gold, Spotify Premium\n\n"
        "📲 <b>Cách tham gia:</b>\n"
        "1️⃣ Mở ứng dụng <b>Zalo</b> trên điện thoại\n"
        "2️⃣ Bấm vào biểu tượng <b>Quét mã QR</b> góc trên màn hình\n"
        "3️⃣ Quét mã QR đính kèm hoặc bấm nút <b>Tham Gia Nhóm Ngay</b> bên dưới!"
    )

    if os.path.exists(qr_path):
        with open(qr_path, "rb") as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=zalo_group_kb()
            )
    else:
        await update.message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=zalo_group_kb()
        )


async def cb_zalo_group(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback hiển thị Nhóm Hỗ Trợ & Share Zalo."""
    query = update.callback_query
    await query.answer()
    from keyboards import zalo_group_kb

    qr_filename = getattr(config, "ZALO_GROUP_QR", "zalo_group_qr.png")
    qr_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), qr_filename)
    if not os.path.exists(qr_path):
        qr_path = os.path.join(os.getcwd(), qr_filename)

    caption = (
        "👥 <b>NHÓM HỖ TRỢ & GIAO LƯU ZALO — ALOPREMIUM</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Tham gia cộng đồng Zalo chính thức của shop để:\n"
        "• ⚡ Cập nhật chứng chỉ DNS & thông báo iOS mới nhất\n"
        "• 🛡 Được hỗ trợ kích hoạt, bảo hành 1-1 trực tiếp 24/7\n"
        "• 🎁 Nhận mã giảm giá độc quyền & GiveAway hàng tuần\n"
        "• 💬 Giao lưu và chia sẻ mẹo sử dụng Locket Gold, Spotify Premium\n\n"
        "📲 <b>Cách tham gia:</b>\n"
        "1️⃣ Mở ứng dụng <b>Zalo</b> trên điện thoại\n"
        "2️⃣ Bấm vào biểu tượng <b>Quét mã QR</b> góc trên màn hình\n"
        "3️⃣ Quét mã QR đính kèm hoặc bấm nút <b>Tham Gia Nhóm Ngay</b> bên dưới!"
    )

    if os.path.exists(qr_path):
        with open(qr_path, "rb") as photo:
            await query.message.reply_photo(
                photo=photo,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=zalo_group_kb()
            )
    else:
        try:
            await query.edit_message_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=zalo_group_kb()
            )
        except Exception:
            await query.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=zalo_group_kb()
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  ĐIỀU HƯỚNG QUAY LẠI & VỀ TRANG CHỦ
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_back_products(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Quay lại danh sách sản phẩm."""
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    text = utils.build_product_menu_text()
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb()
        )
    except Exception:
        try:
            await query.message.delete()
            await query.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_menu_kb()
            )
        except Exception:
            pass
    return ConversationHandler.END


async def cb_back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Về menu trang chủ từ bất kỳ đâu."""
    query = update.callback_query
    await query.answer()
    ctx.user_data.clear()
    text = (
        "🏠 <b>TRANG CHỦ ALOPREMIUM.SHOP</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Vui lòng chọn dịch vụ bạn quan tâm bên dưới:"
    )
    try:
        # Nếu đang ở tin nhắn có ảnh QR, xóa ảnh đi và gửi menu text mới
        await query.message.delete()
        await query.message.reply_text(
            text, parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb()
        )
    except Exception:
        try:
            await query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_menu_kb()
            )
        except Exception:
            await query.message.reply_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=main_menu_kb()
            )
    return ConversationHandler.END


async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /cancel hoặc huỷ thao tác."""
    ctx.user_data.clear()
    await update.message.reply_text(
        "↩️ <b>Đã huỷ thao tác hiện tại thành công.</b>\nĐưa bạn quay về menu chính:",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END



# ── /resetspotify: Khách tự giải phóng phiên thiết bị Spotify ─────────────────

async def resetspotify_user_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Khách hàng tự reset thiết bị Spotify khi đổi điện thoại / cài lại app (POST /api/spotify/reset)."""
    if not ctx.args:
        await update.message.reply_text(
            "🔄 <b>TỰ ĐỘNG RESET THIẾT BỊ SPOTIFY</b>\n\n"
            "Nếu bạn đổi điện thoại hoặc cài lại app Spotify, hãy gửi kèm Link hoặc UID Spotify theo cú pháp:\n"
            "👉 <code>/resetspotify &lt;link_hoặc_uid_spotify&gt;</code>\n\n"
            "<i>Ví dụ:</i>\n"
            "<code>/resetspotify 31t3tcqtl7dugzvuubw2ydhqy6km</code>",
            parse_mode=ParseMode.HTML
        )
        return

    raw_target = ctx.args[0].strip()
    msg = await update.message.reply_text("⏳ Đang kết nối API để giải phóng phiên thiết bị Spotify...", parse_mode=ParseMode.HTML)
    try:
        import re
        m = re.search(r"user/([a-zA-Z0-9]+)", raw_target)
        uid = m.group(1) if m else raw_target

        res = await asyncio.to_thread(api.spotify_reset, uid)
        resp_msg = res.get("message", "Đã giải phóng phiên thiết bị thành công!")
        await msg.edit_text(
            f"✅ <b>ĐÃ RESET THIẾT BỊ SPOTIFY THÀNH CÔNG!</b>\n\n"
            f"🆔 <b>UID:</b> <code>{uid}</code>\n"
            f"💬 <b>Kết quả:</b> {resp_msg}\n\n"
            f"👉 Bây giờ bạn có thể mở ứng dụng Spotify trên thiết bị mới để kết nối nghe nhạc bình thường!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await msg.edit_text(
            f"❌ <b>Reset thiết bị thất bại!</b>\n"
            f"Chi tiết: <code>{e}</code>\n\n"
            f"💡 <i>Vui lòng kiểm tra lại UID hoặc liên hệ hỗ trợ /support để được giúp đỡ.</i>",
            parse_mode=ParseMode.HTML
        )


# ── HƯỚNG DẪN CÀI ĐẶT TRỰC QUAN (SAFARI 3 BƯỚC) ──────────────────────────────

GUIDE_TEXT = """
📲 <b>HƯỚNG DẪN CÀI ĐẶT CẤU HÌNH TRÊN IPHONE (iOS)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━

🔹 <b>BƯỚC 1: Tải hồ sơ qua trình duyệt Safari</b>
• Nhấn nút <b>Copy Link DNS</b> hoặc link tải mà bot gửi.
• Mở trình duyệt <b>Safari</b> trên iPhone, dán link vào thanh địa chỉ rồi bấm <b>Đi (Go)</b>.
• Khi Safari hỏi: <i>"Trang web này đang cố tải về một hồ sơ cấu hình. Bạn có muốn cho phép không?"</i> → Bấm chọn <b>Cho phép (Allow)</b>.
• Khi hiện thông báo <i>"Đã tải về hồ sơ"</i> → Bấm <b>Đóng</b>.
<i>(Hồ sơ đã tự động nạp vào mục Cài đặt của iPhone, bạn KHÔNG CẦN tìm trong ứng dụng Tệp!)</i>

🔹 <b>BƯỚC 2: Cài đặt hồ sơ vào hệ thống</b>
• Mở ứng dụng <b>Cài đặt (Settings)</b> trên iPhone.
• Ở ngay dòng đầu tiên (dưới tên iCloud của bạn), nhấn vào <b>Đã tải về hồ sơ (Profile Downloaded)</b>.
• Nhấn <b>Cài đặt (Install)</b> ở góc trên bên phải → Nhập mật mã mở khóa màn hình iPhone → Tiếp tục nhấn <b>Cài đặt</b> xác nhận.

🔹 <b>BƯỚC 3: Bật tin cậy chứng chỉ (Nếu có)</b>
• Vào <b>Cài đặt (Settings)</b> → <b>Cài đặt chung (General)</b> → <b>Giới thiệu (About)</b>.
• Kéo xuống dưới cùng, chọn <b>Cài đặt tin cậy chứng nhận (Certificate Trust Settings)</b>.
• Tại mục <i>"Bật tin cậy hoàn toàn cho các chứng nhận gốc"</i>, tìm dòng <b>Locket Gold Root CA</b> và <b>BẬT XANH CÔNG TẮC (ON)</b>.
• Chọn <b>Tiếp tục (Continue)</b> để xác nhận.

🎉 <b>Hoàn tất!</b> Mở Locket hoặc Spotify lên để tận hưởng trọn vẹn các tính năng VIP!
"""

async def guide_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /guide – Xem hướng dẫn cài đặt iOS trực quan."""
    from keyboards import back_main_kb
    await update.message.reply_text(GUIDE_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_main_kb())


async def cb_free_locket(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xử lý thông báo gói DNS Free tạm đóng trong Telegram Bot"""
    query = update.callback_query
    await query.answer()
    web_url = getattr(config, "WEBSITE_URL", "https://alopremium.shop").rstrip("/")

    caption = (
        "🚫 <b>THÔNG BÁO: GÓI LOCKET GOLD FREE ĐÃ TẠM ĐÓNG</b>\n\n"
        "⚠️ Do hệ thống nâng cấp máy chủ DNS và đảm bảo quyền lợi dịch vụ, gói dùng thử miễn phí <b>Locket Gold Free 0đ</b> hiện đã tạm ngưng phát hành.\n\n"
        "👑 <b>GIẢI PHÁP TỐT HƠN DÀNH CHO BẠN:</b>\n"
        "Quý khách có thể lựa chọn các gói VIP bản quyền chính chủ, kích hoạt tự động chỉ 30 giây, không dính lỗi chứng chỉ và đầy đủ 100% đặc quyền cao cấp:\n"
        "• <b>Locket Gold VIP:</b> Chỉ từ <b>5.000đ</b>\n"
        "• <b>Spotify Premium:</b> Chỉ từ <b>5.000đ</b>\n"
        "• <b>Combo Duo VIP (Locket + Spotify):</b> Tiết kiệm tối đa\n"
        "• <b>VIP ALL-IN-ONE:</b> Bản quyền vĩnh viễn trọn đời\n\n"
        f"🌐 <i>Xem bảng giá và đặt mua ngay tại: <a href='{web_url}'>{web_url}</a></i>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👑 Xem Bảng Giá Locket VIP (Từ 5K)", callback_data="product:locket")],
        [InlineKeyboardButton("👑 Xem Gói Combo Duo VIP", callback_data="product:locket_spotify")],
        [InlineKeyboardButton("🌐 Mở Website Mua Hàng", url=web_url)],
        [InlineKeyboardButton("🏠 Menu Chính", callback_data="back_main")]
    ])

    await query.message.reply_text(
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )


async def cb_show_guide(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Callback bấm nút xem Hướng dẫn cài đặt iOS."""
    query = update.callback_query
    await query.answer()
    from keyboards import back_main_kb
    try:
        await query.message.reply_text(GUIDE_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_main_kb())
    except Exception:
        await query.edit_message_text(GUIDE_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_main_kb())


async def cb_user_reset_spotify_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Khách bấm nút Reset thiết bị Spotify trong menu đơn hàng."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    orders = db.get_user_orders(user_id)
    spot_orders = [o for o in orders if o.get("product") == "spotify" and o.get("status") == "done"]

    if spot_orders:
        latest_spot = sorted(spot_orders, key=lambda x: x["created_at"], reverse=True)[0]
        uid = latest_spot.get("uid")
        try:
            res = await asyncio.to_thread(api.spotify_reset, uid)
            resp_msg = res.get("message", "Đã giải phóng phiên thiết bị thành công!")
            text = (
                f"✅ <b>ĐÃ RESET THIẾT BỊ SPOTIFY THÀNH CÔNG!</b>\n\n"
                f"🆔 <b>UID:</b> <code>{uid}</code>\n"
                f"💬 <b>Kết quả:</b> {resp_msg}\n\n"
                f"👉 Bây giờ bạn có thể mở ứng dụng Spotify trên thiết bị mới để kết nối nghe nhạc bình thường!"
            )
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=orders_kb(True, True))
            return
        except Exception as e:
            logger.warning(f"Auto reset spotify error: {e}")

    await query.message.reply_text(
        "🔄 <b>TỰ ĐỘNG RESET THIẾT BỊ SPOTIFY</b>\n\n"
        "Nếu bạn đổi điện thoại hoặc cài lại app, hãy dùng lệnh sau để reset:\n"
        "👉 <code>/resetspotify &lt;uid_hoặc_link_spotify&gt;</code>\n\n"
        "<i>Ví dụ:</i> <code>/resetspotify 31t3tcqtl7dugzvuubw2ydhqy6km</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=orders_kb(True, True)
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  QUẢN LÝ MÃ GIẢM GIÁ (COUPON) TRÊN BOT TELEGRAM
# ═══════════════════════════════════════════════════════════════════════════════

async def _apply_and_respond_coupon(update: Update, ctx: ContextTypes.DEFAULT_TYPE, order_id: str, code: str):
    order = db.get_order(order_id)
    if not order:
        await update.message.reply_text("❌ Không tìm thấy thông tin đơn hàng!")
        return
    if order.get("status") not in ("waiting_payment", "pending"):
        await update.message.reply_text("⚠️ Đơn hàng này không ở trạng thái chờ thanh toán.")
        return
    if order.get("discount_code"):
        await update.message.reply_text(
            f"⚠️ Đơn hàng #{order_id} đã áp dụng mã <code>{order['discount_code']}</code> trước đó rồi.",
            parse_mode=ParseMode.HTML
        )
        return

    pv = PRODUCTS.get(order["product"], {})
    plnv = pv.get("plans", {}).get(order["plan"], {})
    orig_price = order.get("original_price") or plnv.get("price") or order.get("price", 0)

    chk = utils.check_and_apply_coupon(code, orig_price)
    if not chk.get("ok"):
        await update.message.reply_text(
            f"❌ {chk.get('error', 'Mã giảm giá không hợp lệ hoặc đã hết hạn.')}\n"
            f"Vui lòng kiểm tra lại mã hoặc thử mã khác.",
            parse_mode=ParseMode.HTML
        )
        return

    final_price = chk["final_price"]
    discount_amount = chk["discount_amount"]
    applied_code = chk["code"]
    desc = chk.get("desc", "")

    db.update_order(
        order_id,
        price=final_price,
        discount_code=applied_code,
        discount_amount=discount_amount,
        original_price=orig_price
    )
    ctx.user_data.pop("waiting_coupon_order", None)

    transfer_memo = f"ORDER_{order_id}"
    qr_url = utils.get_vietqr_url(final_price, transfer_memo)
    bank_id = getattr(config, "BANK_ID", "TPB")
    account_no = getattr(config, "ACCOUNT_NO", "")
    account_name = getattr(config, "ACCOUNT_NAME", "")
    display = order.get("display_name") or order.get("uid")

    caption = (
        f"🎉 <b>ÁP DỤNG MÃ GIẢM GIÁ THÀNH CÔNG!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔖 <b>Mã ưu đãi:</b> <code>{applied_code}</code>\n"
        f"🎁 <b>Chi tiết:</b> <i>{desc}</i>\n"
        f"💵 <b>Giá gốc:</b> <s>{utils.fmt_price(orig_price)}</s>\n"
        f"💰 <b>Tiết kiệm:</b> <b>-{utils.fmt_price(discount_amount)}</b>\n"
        f"🔥 <b>CẦN THANH TOÁN:</b> <b>{utils.fmt_price(final_price)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Dịch vụ:</b> {pv.get('emoji', '💎')} {pv.get('name', '')} — {plnv.get('label', '')}\n"
        f"👤 <b>Tài khoản:</b> <b>{display}</b>\n"
        f"🏦 <b>Ngân hàng:</b> <b>{bank_id}</b>\n"
        f"🔢 <b>Số tài khoản:</b> <code>{account_no}</code>\n"
        f"👤 <b>Chủ tài khoản:</b> <b>{account_name}</b>\n"
        f"📝 <b>Nội dung CK:</b> <code>{transfer_memo}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <i>Mã VietQR đã cập nhật lại đúng số tiền sau giảm. Vui lòng quét mã bên dưới để thanh toán:</i>"
    )

    try:
        await update.message.reply_photo(
            photo=qr_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(order_id, applied_coupon=applied_code)
        )
    except Exception as e:
        logger.error(f"Error sending updated QR: {e}")
        await update.message.reply_text(
            caption,
            parse_mode=ParseMode.HTML,
            reply_markup=payment_kb(order_id, applied_coupon=applied_code)
        )


async def cb_coupon(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order:
        await query.answer("❌ Đơn hàng không tồn tại!", show_alert=True)
        return
    if order.get("status") not in ("waiting_payment", "pending"):
        await query.answer("Đơn hàng này không còn ở trạng thái chờ thanh toán.", show_alert=True)
        return
    if order.get("discount_code"):
        await query.answer(f"Đơn hàng đã áp dụng mã: {order['discount_code']}", show_alert=True)
        return

    ctx.user_data["waiting_coupon_order"] = order_id
    await query.message.reply_text(
        f"🎟 <b>NHẬP MÃ GIẢM GIÁ CHO ĐƠN HÀNG #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 Vui lòng <b>gửi mã giảm giá</b> vào ô chat bên dưới:\n"
        f"<i>(Hoặc gõ lệnh: <code>/coupon MÃ_CỦA_BẠN</code>)</i>\n"
        f"<i>Gõ /cancel nếu muốn huỷ bỏ.</i>",
        parse_mode=ParseMode.HTML
    )


async def cb_coupon_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if order and order.get("discount_code"):
        await query.answer(
            f"Đã áp dụng mã {order['discount_code']}: Tiết kiệm {utils.fmt_price(order.get('discount_amount', 0))}",
            show_alert=True
        )
    else:
        await query.answer("Chưa áp dụng mã giảm giá.", show_alert=True)


async def coupon_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /coupon hoặc /magg <MÃ> để áp mã giảm giá vào đơn hàng chờ thanh toán."""
    user = update.effective_user
    if not ctx.args:
        await update.message.reply_text(
            "Cú pháp: <code>/coupon &lt;MÃ_GIẢM_GIÁ&gt;</code>\n"
            "<i>Ví dụ:</i> <code>/coupon MÃ_GIẢM_GIÁ</code>",
            parse_mode=ParseMode.HTML
        )
        return

    code = ctx.args[0].strip().upper()
    order_id = ctx.user_data.get("waiting_coupon_order") or ctx.user_data.get("order_id")
    if not order_id:
        orders = db.get_orders()
        user_pending = [o for o in orders.values() if o.get("user_id") == user.id and o.get("status") in ("waiting_payment", "pending")]
        if user_pending:
            user_pending.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            order_id = user_pending[0]["order_id"]

    if not order_id:
        await update.message.reply_text(
            "❌ Bạn hiện không có đơn hàng nào đang chờ thanh toán để áp dụng mã giảm giá.\n"
            "Hãy chọn gói dịch vụ trước bằng lệnh /start.",
            parse_mode=ParseMode.HTML
        )
        return

    await _apply_and_respond_coupon(update, ctx, order_id, code)


async def handle_user_coupon_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> bool:
    order_id = ctx.user_data.get("waiting_coupon_order")
    if not order_id:
        return False

    text = update.message.text.strip() if update.message and update.message.text else ""
    if not text:
        return False

    if text.startswith("/"):
        ctx.user_data.pop("waiting_coupon_order", None)
        return False

    code = text.upper()
    await _apply_and_respond_coupon(update, ctx, order_id, code)
    return True
