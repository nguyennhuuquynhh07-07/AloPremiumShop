"""
handlers/user_handlers.py
Quy trình 4 bước bán Locket & Spotify theo API locket.2707226.xyz
Giao diện chuyên nghiệp, hỗ trợ điều hướng quay lại và huỷ thao tác mượt mà.
"""

import logging
from telegram import Update
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
    success_kb, orders_kb, support_kb, account_kb, language_kb,
    apidocs_kb, apierrors_kb
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

    text = (
        f"👋 Xin chào <b>{user.first_name}</b>!\n"
        f"Chào mừng bạn đến với <b>Hệ Thống Dịch Vụ Premium Tự Động</b> 🌟\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Kích hoạt siêu tốc:</b> Cài đặt trực tiếp qua DNS Profile iOS\n"
        f"🔒 <b>Bảo mật 100%:</b> Không yêu cầu cung cấp mật khẩu tài khoản\n"
        f"🛡 <b>Bảo hành uy tín:</b> Đổi mới & hỗ trợ 1-1 trọn đời gói\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👇 <b>Chọn dịch vụ bạn muốn trải nghiệm bên dưới:</b>"
    )
    await update.message.reply_text(
        text, parse_mode=ParseMode.HTML,
        reply_markup=main_menu_kb()
    )
    return ConversationHandler.END


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
    dns_link = f"{DNS_BASE_URL}/{DNS_SLUG}"
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
        for o in sorted(done_orders, key=lambda x: x["created_at"], reverse=True)[:5]:
            prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
            plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
            lines.append(f"• <b>{prod} ({plan})</b> — UID: <code>{o.get('uid')}</code>")
    else:
        lines.append("<i>Chưa có gói dịch vụ nào đang kích hoạt.</i>")

    lines.extend([
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>Link DNS Profile iOS:</b>\n<code>{dns_link}</code>",
        "💡 <i>Mở link trên Safari để tải & cài đặt cấu hình VPN & DNS.</i>"
    ])

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=account_kb(dns_link)
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
    dns_link = f"{DNS_BASE_URL}/{DNS_SLUG}"
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
        for o in sorted(done_orders, key=lambda x: x["created_at"], reverse=True)[:5]:
            prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
            plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
            lines.append(f"• <b>{prod} ({plan})</b> — UID: <code>{o.get('uid')}</code>")
    else:
        lines.append("<i>Chưa có gói dịch vụ nào đang kích hoạt.</i>")

    lines.extend([
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🌐 <b>Link DNS Profile iOS:</b>\n<code>{dns_link}</code>",
        "💡 <i>Mở link trên Safari để tải & cài đặt cấu hình VPN & DNS.</i>"
    ])

    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=account_kb(dns_link)
        )
    except Exception:
        await query.message.reply_text(
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            reply_markup=account_kb(dns_link)
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
    """Callback gửi trực tiếp file .mobileconfig cho người dùng."""
    query = update.callback_query
    await query.answer("Đang xuất file cấu hình...")
    user = query.from_user

    orders = db.get_user_orders(user.id)
    done_orders = [o for o in orders if o.get("status") == "done"]

    dns_link = f"{DNS_BASE_URL}/{DNS_SLUG}"
    if done_orders:
        latest = sorted(done_orders, key=lambda x: x["created_at"], reverse=True)[0]
        prod_name = PRODUCTS.get(latest.get("product"), {}).get("name", "Locket & Spotify")
        uid_name = latest.get("display_name") or latest.get("uid") or user.first_name
    else:
        prod_name = "Locket & Spotify Premium"
        uid_name = user.username or user.first_name or "VIP"

    profile_file = utils.generate_mobileconfig(
        service_name=prod_name,
        display_name=uid_name,
        dns_link=dns_link
    )
    safe_uid = str(uid_name).replace(" ", "_")
    file_name = f"DNS_{safe_uid}.mobileconfig"

    caption = (
        f"📥 <b>HỒ SƠ CẤU HÌNH DNS PROFILE (.mobileconfig)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Tài khoản: <b>@{uid_name}</b>\n"
        f"📦 Dịch vụ: <b>{prod_name}</b>\n"
        f"🌐 DNS Server: <code>{dns_link}</code>\n\n"
        f"⚡ <b>HƯỚNG DẪN CÀI ĐẶT 1 CHẠM TRÊN IPHONE:</b>\n"
        f"1️⃣ Bấm trực tiếp vào file đính kèm phía trên để tải về máy.\n"
        f"2️⃣ Bấm <b>\"Cho phép\" (Allow)</b> khi có thông báo hiện lên.\n"
        f"3️⃣ Mở <b>Cài đặt (Settings)</b> trên iPhone → Chọn mục <b>Đã tải về hồ sơ</b> (ở đầu trang Cài đặt).\n"
        f"4️⃣ Bấm <b>Cài đặt (Install)</b> ở góc trên bên phải → Nhập mật mã máy và xác nhận là xong! 🎉\n\n"
        f"💡 <i>Nếu cần hỗ trợ kỹ thuật, hãy bấm /support để gặp CSKH.</i>"
    )

    await ctx.bot.send_document(
        chat_id=user.id,
        document=profile_file,
        filename=file_name,
        caption=caption,
        parse_mode=ParseMode.HTML
    )


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

    pv   = PRODUCTS[product_key]
    plnv = pv["plans"][plan_key]

    if product_key == "spotify":
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI LINK HOẶC UID SPOTIFY</b>\n\n"
            f"<b>Cách lấy liên kết Spotify cá nhân:</b>\n"
            f"  1️⃣ Mở app Spotify → Bấm <b>Cài đặt (hoặc Avatar)</b>\n"
            f"  2️⃣ Chọn <b>Hồ sơ cá nhân</b> → Bấm <b>Chia sẻ</b> → <b>Sao chép liên kết</b>\n\n"
            f"<i>Hệ thống tự động lọc cả hai dạng:</i>\n"
            f"• Link URL: <code>https://open.spotify.com/user/31t3tcqt...</code>\n"
            f"• Hoặc UID trực tiếp: <code>31t3tcqt17dugzvuubw2ydhqy6km</code>\n\n"
            f"👇 <b>Gửi Link hoặc UID Spotify vào ô chat bên dưới:</b>"
        )
    elif product_key == "combo3in1":
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá trọn gói:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI USERNAME HOẶC LINK LOCKET</b>\n\n"
            f"<b>Hướng dẫn lấy thông tin Locket:</b>\n"
            f"  • Mở app Locket → Bấm Avatar góc trên → Xem <b>@username</b>\n"
            f"  • Hoặc chọn <i>'Mời bạn bè'</i> → <i>Sao chép liên kết</i> (<code>locket.cam/...</code>)\n\n"
            f"👑 <i>Gói này sẽ tự động tích hợp:</i>\n"
            f"• 💛 <b>Locket Gold Pro (Vĩnh viễn 2099)</b>\n"
            f"• 🎵 <b>Spotify Premium</b>\n"
            f"• ▶️ <b>YouTube Premium (Chặn QC + PiP nền)</b>\n\n"
            f"👇 <b>Gửi Username hoặc Link Locket của bạn vào ô chat bên dưới:</b>"
        )
    else:  # locket
        prompt = (
            f"📦 <b>DỊCH VỤ ĐÃ CHỌN:</b> {pv['emoji']} <b>{pv['name']} — {plnv['label']}</b>\n"
            f"💰 <b>Giá thanh toán:</b> <code>{utils.fmt_price(plnv['price'])}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 <b>BƯỚC 1: GỬI USERNAME LOCKET</b>\n\n"
            f"<b>Hướng dẫn:</b>\n"
            f"  Mở app Locket → Bấm Avatar góc trên → Xem phần <b>@username</b>\n\n"
            f"<i>Ví dụ:</i> <code>conlaigii</code> hoặc <code>minhkim</code>\n\n"
            f"👇 <b>Gửi Username Locket của bạn vào ô chat bên dưới:</b>"
        )

    await query.edit_message_text(
        prompt, parse_mode=ParseMode.HTML,
        reply_markup=back_to_plan_kb(product_key)
    )
    return WAITING_IDENTIFIER


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 2: Nhận identifier → Xác thực Profile → Hiện hoá đơn & QR thanh toán
# ═══════════════════════════════════════════════════════════════════════════════

async def receive_identifier(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    raw_identifier = update.message.text.strip()
    product_key = ctx.user_data.get("product")
    plan_key    = ctx.user_data.get("plan")

    if not product_key or not plan_key:
        await update.message.reply_text(
            "⚠️ Phiên làm việc đã hết hạn. Vui lòng bấm bên dưới để bắt đầu lại:",
            reply_markup=main_menu_kb()
        )
        return ConversationHandler.END

    pv   = PRODUCTS[product_key]
    plnv = pv["plans"][plan_key]

    checking_msg = await update.message.reply_text(
        f"🔍 <b>Đang kiểm tra tài khoản & Profile {pv['name']} trên hệ thống…</b>\nVui lòng chờ trong giây lát.",
        parse_mode=ParseMode.HTML
    )

    try:
        avatar_url = None
        spotify_extra_info = ""

        extra_order_fields = {}
        if product_key == "spotify":
            res = api.spotify_check(raw_identifier)
            data = res.get("data") if isinstance(res.get("data"), dict) else res
            uid  = data.get("uid") or data.get("id") or raw_identifier
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
                "account_target": uid or raw_identifier,
                "avatar": avatar_url,
            }
        elif product_key == "combo3in1":
            from locket_service import resolve_locket_profile, clean_input
            cleaned = clean_input(raw_identifier)
            res_3in1 = resolve_locket_profile(cleaned)
            if not res_3in1.get("ok"):
                raise Exception(res_3in1.get("error", "Không tìm thấy tài khoản Locket."))
            uid = res_3in1.get("uid") or cleaned
            display = res_3in1.get("full_name") or res_3in1.get("username") or cleaned
            avatar_url = res_3in1.get("avatar")
            extra_order_fields = {
                "token": res_3in1.get("token"),
                "download_url": res_3in1.get("download_url"),
                "avatar": avatar_url,
                "locket_username": res_3in1.get("username") or cleaned,
                "account_target": res_3in1.get("username") or cleaned,
            }
        else:
            from locket_service import clean_input
            cleaned_username = clean_input(raw_identifier)
            res = api.locket_resolve(cleaned_username)
            data = res.get("data") if isinstance(res.get("data"), dict) else res
            uid  = data.get("uid") or data.get("id") or cleaned_username
            display = data.get("displayName") or data.get("username") or data.get("name") or cleaned_username
            avatar_url = data.get("avatar") or data.get("avatarUrl")
            extra_order_fields = {
                "account_target": display or cleaned_username,
                "avatar": avatar_url,
            }

        # Tạo đơn hàng vào cơ sở dữ liệu
        order_id = utils.gen_order_id()
        user     = update.effective_user
        db.create_order(
            order_id=order_id,
            user_id=user.id,
            username=user.username or user.first_name,
            product=product_key,
            plan=plan_key,
            price=plnv["price"],
            uid=uid,
            display_name=display,
            **extra_order_fields
        )
        db.update_order(order_id, status="waiting_payment")
        ctx.user_data["order_id"] = order_id

        await checking_msg.delete()

        # Tạo ảnh QR VietQR chuẩn
        transfer_memo = f"ORDER_{order_id}"
        qr_url = utils.get_vietqr_url(plnv['price'], transfer_memo)
        bank_id = getattr(config, "BANK_ID", "TCB")
        account_no = getattr(config, "ACCOUNT_NO", "")
        account_name = getattr(config, "ACCOUNT_NAME", "")

        caption = (
            f"🧾 <b>HOÁ ĐƠN THANH TOÁN #{order_id}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 <b>Dịch vụ:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
            f"👤 <b>Tài khoản:</b> <b>{display}</b>\n"
            f"🆔 <b>UID:</b> <code>{uid}</code>\n"
            f"{spotify_extra_info}"
            f"💵 <b>Số tiền:</b> <b>{utils.fmt_price(plnv['price'])}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 <b>Ngân hàng:</b> <b>{bank_id}</b>\n"
            f"🔢 <b>Số tài khoản:</b> <code>{account_no}</code>\n"
            f"👤 <b>Chủ tài khoản:</b> <b>{account_name}</b>\n"
            f"📝 <b>Nội dung CK:</b> <code>{transfer_memo}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>LƯU Ý:</b>\n"
            f"• Quét mã QR để chuyển khoản chính xác số tiền & nội dung.\n"
            f"• Chuyển tiền xong, hãy bấm nút <b>\"✅ Tôi đã chuyển khoản\"</b> bên dưới để Admin duyệt và nhận link cài đặt DNS Profile!"
        )

        try:
            await update.message.reply_photo(
                photo=qr_url,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=payment_kb(order_id)
            )
        except Exception as e:
            logger.error(f"Error sending QR photo: {e}")
            await update.message.reply_text(
                caption,
                parse_mode=ParseMode.HTML,
                reply_markup=payment_kb(order_id)
            )

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"API verify error: {e}")
        await checking_msg.edit_text(
            f"❌ <b>Không thể tìm thấy tài khoản!</b>\n\n"
            f"Chi tiết lỗi: <code>{e}</code>\n\n"
            f"Vui lòng kiểm tra lại Link/UID Spotify hoặc Username Locket xem đã chính xác chưa.",
            parse_mode=ParseMode.HTML,
            reply_markup=back_to_plan_kb(product_key)
        )
        return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 3: Khách bấm "Tôi đã chuyển khoản" → Báo Admin duyệt
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)

    if not order:
        await query.answer("❌ Không tìm thấy thông tin đơn hàng!", show_alert=True)
        return
    if order["status"] == "done":
        await query.answer("Đơn hàng này đã được duyệt hoàn thành trước đó!", show_alert=True)
        return
    if order["status"] == "pending_approval":
        await query.answer("Đơn hàng đang chờ Admin duyệt, bạn vui lòng không bấm lại!", show_alert=True)
        return

    pv = PRODUCTS[order["product"]]
    plnv = pv["plans"][order["plan"]]

    if getattr(config, "AUTO_APPROVE", False):
        from order_service import execute_order_activation
        ok, act_msg = await execute_order_activation(ctx.bot, order_id)
        if ok:
            from config import ADMIN_IDS
            for admin_id in ADMIN_IDS:
                try:
                    await ctx.bot.send_message(
                        admin_id,
                        f"⚡ <b>[AUTO-APPROVE] ĐƠN HÀNG ĐÃ DUYỆT TỰ ĐỘNG!</b>\n\n"
                        f"🧾 Mã đơn: <code>ORDER_{order_id}</code>\n"
                        f"👤 Khách: @{order['username']} (ID: <code>{order['user_id']}</code>)\n"
                        f"📦 Gói: {pv['emoji']} {pv['name']} — {plnv['label']}\n"
                        f"💰 Số tiền: <b>{utils.fmt_price(order['price'])}</b>\n"
                        f"🎯 Tài khoản: <b>{order['display_name']}</b>",
                        parse_mode=ParseMode.HTML
                    )
                except Exception:
                    pass
            return

    db.update_order(order_id, status="pending_approval")

    customer_msg = (
        f"⏳ <b>XÁC NHẬN THANH TOÁN ĐÃ ĐƯỢC GỬI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Mã đơn hàng:</b> <code>ORDER_{order_id}</code>\n"
        f"📦 <b>Dịch vụ:</b> {pv['emoji']} {pv['name']} — {plnv['label']}\n"
        f"👤 <b>Tài khoản:</b> <b>{order['display_name']}</b>\n"
        f"💰 <b>Số tiền:</b> <b>{utils.fmt_price(order['price'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Admin đang kiểm tra giao dịch và sẽ duyệt đơn cho bạn ngay lập tức.\n"
        f"🚀 <i>Link cấu hình DNS Profile sẽ tự động gửi tới đây ngay sau khi duyệt!</i>"
    )
    try:
        await query.edit_message_caption(customer_msg, parse_mode=ParseMode.HTML, reply_markup=success_kb())
    except Exception:
        await query.edit_message_text(customer_msg, parse_mode=ParseMode.HTML, reply_markup=success_kb())

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
        f"Kiểm tra tài khoản Techcombank và chọn hành động:"
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


# ═══════════════════════════════════════════════════════════════════════════════
#  BƯỚC 4: Hướng dẫn cài đặt cấu hình DNS
# ═══════════════════════════════════════════════════════════════════════════════

def _build_success_message(order, pv, plnv, dns_link: str) -> str:
    is_test = order.get("plan") == "test" or plnv.get("packageCode") in ["LKGT3D", "SPT"]
    if is_test:
        duration_note = (
            f"⏱️ <b>Thời hạn dùng thử:</b> <b>24 Giờ (1 Ngày)</b>\n"
            f"⚠️ <i>Lưu ý: Hết 24h, hệ thống API & DNS sẽ tự động ngắt kích hoạt cho tài khoản này.</i>"
        )
    else:
        duration_note = f"💡 <i>Chỉ cần cài 1 lần là dùng theo thời hạn gói. Nếu đổi thiết bị hãy nhắn Admin để reset.</i>"

    if order["product"] == "spotify":
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
    await query.answer()
    order_id = query.data.split(":")[1]
    db.update_order(order_id, status="cancelled")
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

async def myorders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    orders = db.get_user_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text(
            "📦 <b>LỊCH SỬ ĐƠN HÀNG</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Bạn chưa có đơn hàng nào trong hệ thống.\n\n"
            "Hãy khám phá các gói dịch vụ hấp dẫn của chúng tôi ngay hôm nay!",
            parse_mode=ParseMode.HTML,
            reply_markup=orders_kb()
        )
        return

    lines = [
        "📦 <b>LỊCH SỬ ĐƠN HÀNG CỦA BẠN (Gần nhất)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    for o in sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]:
        prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
        plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
        lines.append(
            f"{utils.status_emoji(o['status'])} <b>Mã:</b> <code>ORDER_{o['order_id']}</code>\n"
            f"   └ {prod} ({plan}) — {utils.fmt_price(o['price'])}\n"
            f"   └ <i>Ngày đặt: {utils.fmt_datetime(o['created_at'])}</i>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Ghi chú: ✅ Đã duyệt | ⏳ Chờ duyệt | 💳 Chờ thanh toán</i>")
    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
        reply_markup=orders_kb()
    )


async def cb_my_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    orders = db.get_user_orders(query.from_user.id)
    if not orders:
        await query.edit_message_text(
            "📦 <b>LỊCH SỬ ĐƠN HÀNG</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Bạn chưa có đơn hàng nào trong hệ thống.\n\n"
            "Hãy khám phá các gói dịch vụ hấp dẫn của chúng tôi ngay hôm nay!",
            parse_mode=ParseMode.HTML,
            reply_markup=orders_kb()
        )
        return

    lines = [
        "📦 <b>LỊCH SỬ ĐƠN HÀNG CỦA BẠN (Gần nhất)</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    ]
    for o in sorted(orders, key=lambda x: x["created_at"], reverse=True)[:10]:
        prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
        plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
        lines.append(
            f"{utils.status_emoji(o['status'])} <b>Mã:</b> <code>ORDER_{o['order_id']}</code>\n"
            f"   └ {prod} ({plan}) — {utils.fmt_price(o['price'])}\n"
            f"   └ <i>Ngày đặt: {utils.fmt_datetime(o['created_at'])}</i>\n"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Ghi chú: ✅ Đã duyệt | ⏳ Chờ duyệt | 💳 Chờ thanh toán</i>")
    await query.edit_message_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
        reply_markup=orders_kb()
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  HỖ TRỢ CSKH
# ═══════════════════════════════════════════════════════════════════════════════

async def support_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    contact_label = "Hotline / Zalo hỗ trợ:" if SUPPORT_USERNAME.isdigit() else "Admin hỗ trợ:"
    support_text = (
        "💬 <b>TRUNG TÂM HỖ TRỢ KHÁCH HÀNG 24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Đội ngũ kỹ thuật luôn sẵn sàng hỗ trợ bạn kích hoạt và giải quyết mọi thắc mắc:\n\n"
        f"📞 <b>{contact_label}</b> <code>{SUPPORT_USERNAME}</code>\n"
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
    contact_label = "Hotline / Zalo hỗ trợ:" if SUPPORT_USERNAME.isdigit() else "Admin hỗ trợ:"
    support_text = (
        "💬 <b>TRUNG TÂM HỖ TRỢ KHÁCH HÀNG 24/7</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Đội ngũ kỹ thuật luôn sẵn sàng hỗ trợ bạn kích hoạt và giải quyết mọi thắc mắc:\n\n"
        f"📞 <b>{contact_label}</b> <code>{SUPPORT_USERNAME}</code>\n"
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
        "🏠 <b>TRANG CHỦ DỊCH VỤ PREMIUM</b>\n"
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

        res = api.spotify_reset(uid)
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

🔹 <b>BƯỚC 3: Bật tin cậy chứng chỉ (Dành cho gói Siêu VIP 3-in-1)</b>
• Vào <b>Cài đặt (Settings)</b> → <b>Cài đặt chung (General)</b> → <b>Giới thiệu (About)</b>.
• Kéo xuống dưới cùng, chọn <b>Cài đặt tin cậy chứng nhận (Certificate Trust Settings)</b>.
• Tại mục <i>"Bật tin cậy hoàn toàn cho các chứng nhận gốc"</i>, tìm dòng <b>Locket Gold Root CA</b> và <b>BẬT XANH CÔNG TẮC (ON)</b>.
• Chọn <b>Tiếp tục (Continue)</b> để xác nhận.

🎉 <b>Hoàn tất!</b> Mở Locket, Spotify hoặc YouTube lên để tận hưởng trọn vẹn các tính năng VIP!
"""

async def guide_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Lệnh /guide – Xem hướng dẫn cài đặt iOS trực quan."""
    from keyboards import back_main_kb
    await update.message.reply_text(GUIDE_TEXT, parse_mode=ParseMode.HTML, reply_markup=back_main_kb())


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
            res = api.spotify_reset(uid)
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
