"""
bot.py – Entry point của Bot VIP:
1. Gói Locket Gold VIP (API CTV)
2. Gói Spotify Premium (API CTV)
Tích hợp web server giữ kết nối 24/7 trên Render, bảng điều khiển Admin,
quản lý đơn hàng VietQR tự động.
"""

import os
import sys
import asyncio
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Đảm bảo UTF-8
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import config
from config import BOT_TOKEN, ADMIN_IDS
from handlers.user_handlers import (
    start, menu_cmd, myorders_cmd, support_cmd,
    help_cmd, account_cmd, apidocs_cmd, apierrors_cmd, setlang_cmd,
    cb_product, cb_plan,
    cb_paid, cb_buy, cb_cancel,
    cb_my_orders, cb_support, cb_my_account,
    cb_cmd_setlang, cb_lang, cb_apidocs, cb_get_mobileconfig,
    cb_back_main, cb_back_products, cb_show_qr,
    receive_identifier, cancel_conv, resetspotify_user_cmd, guide_cmd, cb_show_guide, cb_user_reset_spotify_menu,
    cb_coupon, cb_coupon_info, coupon_cmd, handle_user_coupon_text,
    WAITING_IDENTIFIER,
)
try:
    from handlers.user_handlers import zalo_cmd, cb_zalo_group
except (ImportError, AttributeError):
    async def zalo_cmd(update, ctx):
        import keyboards
        zkb = getattr(keyboards, "zalo_group_kb", getattr(keyboards, "support_kb", None))()
        await update.message.reply_text(
            "👥 <b>NHÓM HỖ TRỢ & GIAO LƯU ZALO — ALOPREMIUM</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Tham gia cộng đồng Zalo để được hỗ trợ kỹ thuật và nhận mã giảm giá VIP!\n"
            "Hotline / Zalo CSKH: <code>0345.222.802</code>",
            parse_mode="HTML",
            reply_markup=zkb
        )

    async def cb_zalo_group(update, ctx):
        query = update.callback_query
        await query.answer()
        import keyboards
        zkb = getattr(keyboards, "zalo_group_kb", getattr(keyboards, "support_kb", None))()
        await query.message.reply_text(
            "👥 <b>NHÓM HỖ TRỢ & GIAO LƯU ZALO — ALOPREMIUM</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Tham gia cộng đồng Zalo để được hỗ trợ kỹ thuật và nhận mã giảm giá VIP!\n"
            "Hotline / Zalo CSKH: <code>0345.222.802</code>",
            parse_mode="HTML",
            reply_markup=zkb
        )
try:
    from handlers.user_handlers import web_cmd
except (ImportError, AttributeError):
    async def web_cmd(update, ctx):
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
            f"• Nhận Link Studio chỉnh chú thích & đổi 38 khung viền\n\n"
            f"🔗 Truy cập ngay: <a href='{web_url}'>{web_url}</a>",
            parse_mode="HTML",
            reply_markup=kb
        )
try:
    from handlers.user_handlers import cb_ai_studio_opt, cb_buy_studio
except (ImportError, AttributeError):
    try:
        import user_handlers
        cb_ai_studio_opt = getattr(user_handlers, "cb_ai_studio_opt", None)
        cb_buy_studio = getattr(user_handlers, "cb_buy_studio", None)
    except Exception:
        cb_ai_studio_opt = None
        cb_buy_studio = None

if cb_ai_studio_opt is None:
    async def cb_ai_studio_opt(update, ctx):
        query = update.callback_query
        await query.answer("Hệ thống đang đồng bộ tính năng Studio, vui lòng thử lại sau giây lát!", show_alert=True)

if cb_buy_studio is None:
    async def cb_buy_studio(update, ctx):
        query = update.callback_query
        await query.answer("Hệ thống đang đồng bộ tính năng Studio, vui lòng thử lại sau giây lát!", show_alert=True)

from handlers.admin_handlers import (
    admin_cmd, cb_admin,
    cb_admin_approve, cb_admin_reject,
    noti_cmd, notistop_cmd,
    rs_cmd, stats_cmd, users_cmd, find_cmd,
    ban_cmd, unban_cmd, orders_cmd, tokens_cmd,
    checkbank_cmd, addcode_cmd, delcode_cmd, codes_cmd, coin_cmd, packages_cmd, duyet_cmd, setprice_cmd,
    handle_admin_text_input,
)

try:
    from handlers.admin_handlers import sync_cmd
except ImportError:
    async def sync_cmd(update, ctx):
        if update.effective_user.id not in ADMIN_IDS:
            return
        msg = await update.message.reply_text("⏳ Đang đồng bộ tài khoản từ web chủ...")
        try:
            from order_service import sync_upstream_orders
            cnt = await asyncio.to_thread(sync_upstream_orders)
            await msg.edit_text(f"✅ Đã đồng bộ <b>{cnt}</b> tài khoản từ web chủ thành công!", parse_mode="HTML")
        except Exception as e_s:
            await msg.edit_text(f"❌ Lỗi đồng bộ: {e_s}")

import web_server


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)



# ── Luồng quét tự động số dư ngân hàng qua SePay (Techcombank) ───────────────

async def check_sepay_auto_payments(bot):
    token = getattr(config, "SEPAY_API_TOKEN", "")
    if not token:
        return

    import database as db
    orders = db.get_orders()
    pending = [o for o in orders.values() if o.get("status") in ("waiting_payment", "pending_approval", "pending")]
    if not pending:
        return

    url = "https://my.sepay.vn/userapi/transactions/list?limit=20"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(url, headers=headers)
            if r.status_code != 200:
                return
            data = r.json()
            transactions = data.get("transactions", [])
            if not transactions:
                return

            from order_service import execute_order_activation
            import utils
            for order in pending:
                order_id = order["order_id"].upper()
                req_amount = float(order.get("price", 0))

                for tx in transactions:
                    tx_id = str(tx.get("id", ""))
                    if not tx_id or db.is_tx_used(tx_id):
                        continue

                    # Bắt buộc đúng tài khoản thụ hưởng
                    tx_acc = str(tx.get("account_number", "")).strip()
                    if tx_acc and tx_acc != str(config.ACCOUNT_NO).strip():
                        continue

                    content = str(tx.get("transaction_content", "")).upper()
                    amount_in = float(tx.get("amount_in", 0) or 0)

                    # Khớp mã đơn ORDER_XXXX hoặc XXXX và số tiền >= giá gói
                    if (order_id in content or f"ORDER_{order_id}" in content) and amount_in >= req_amount:
                        logger.info(f"✅ SePay tự động phát hiện thanh toán cho đơn ORDER_{order_id} ({amount_in}đ, TX: {tx_id})!")
                        ok, msg = await execute_order_activation(bot, order["order_id"])
                        if ok:
                            db.mark_tx_used(tx_id, order["order_id"])
                            try:
                                await bot.send_message(
                                    chat_id=order["user_id"],
                                    text=(
                                        f"🔔 <b>HỆ THỐNG ĐÃ TỰ ĐỘNG NHẬN ĐƯỢC THANH TOÁN {utils.fmt_price(int(amount_in))}!</b>\n"
                                        f"Gói dịch vụ <b>{order['product']}</b> đã được kích hoạt thành công."
                                    ),
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass

                            for aid in config.ADMIN_IDS:
                                try:
                                    await bot.send_message(
                                        chat_id=aid,
                                        text=(
                                            f"💰 <b>[SEPAY AUTO] NHẬN TIỀN THÀNH CÔNG!</b>\n\n"
                                            f"• Mã đơn: <code>ORDER_{order_id}</code>\n"
                                            f"• Khách: @{order['username']}\n"
                                            f"• Số tiền: <b>{utils.fmt_price(int(amount_in))}</b>\n"
                                            f"• Hệ thống đã tự động kích hoạt và giao hồ sơ cho khách!"
                                        ),
                                        parse_mode="HTML"
                                    )
                                except Exception:
                                    pass
                        break
    except Exception as e:
        logger.warning(f"SePay worker error: {e}")


async def sepay_worker(bot):
    """Vòng lặp chạy ngầm quét biến động số dư TPBank mỗi 4 giây và tự động hủy đơn hết hạn 5 phút"""
    logger.info("🚀 Luồng SePay worker đã khởi động (quét TPBank tự động mỗi 4s)...")
    import order_service
    cancel_counter = 0
    while True:
        try:
            await order_service.check_all_sepay_pending_payments(bot)
            # Quét và hủy các đơn hàng quá hạn 5 phút (kiểm tra mỗi 20 giây ~ 5 chu kỳ)
            cancel_counter += 1
            if cancel_counter >= 5:
                cancel_counter = 0
                cancel_fn = getattr(order_service, "cancel_expired_pending_orders", None)
                if cancel_fn:
                    await asyncio.to_thread(cancel_fn, 300)
        except Exception as e:
            logger.warning(f"SePay worker loop error: {e}")
        await asyncio.sleep(4)

async def keep_alive_worker():
    """Tự động ping server Render mỗi 10 phút để giữ máy chủ và bot luôn thức 24/7 (Async, không nghẽn)"""
    import httpx
    url = "https://alopremium.shop/health"
    while True:
        await asyncio.sleep(600)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(url, headers={"User-Agent": "RenderKeepAlive/1.0"})
        except Exception:
            pass


async def post_init(application):
    """Thiết lập danh sách lệnh Menu Telegram và đồng bộ Event Loop cho Web Server"""
    try:
        import web_server
        web_server.BOT_INSTANCE = application.bot
        web_server.BOT_LOOP = asyncio.get_running_loop()
    except Exception as e:
        logger.warning(f"Error binding bot loop: {e}")
    user_commands = [
        BotCommand("start", "Menu chính & Mua gói"),
        BotCommand("web", "Mở Website AloPremium.Shop"),
        BotCommand("account", "Tài khoản của tôi"),
        BotCommand("myorders", "Đơn hàng đã mua"),
        BotCommand("resetspotify", "Reset thiết bị Spotify"),
        BotCommand("support", "Hỗ trợ CSKH"),
        BotCommand("guide", "Hướng dẫn cài đặt iOS"),
        BotCommand("help", "Hướng dẫn sử dụng"),
    ]

    admin_commands = [
        BotCommand("start", "Menu chính"),
        BotCommand("web", "Mở Website AloPremium.Shop"),
        BotCommand("admin", "Bảng điều khiển Admin"),
        BotCommand("coin", "Số dư Coin CTV API"),
        BotCommand("packages", "Bảng giá gói cước API"),
        BotCommand("orders", "Danh sách đơn hàng"),
        BotCommand("stats", "Thống kê doanh thu"),
        BotCommand("users", "Quản lý người dùng"),
        BotCommand("find", "Tìm kiếm đơn / user"),
        BotCommand("rs", "Reset thiết bị Spotify"),
        BotCommand("addcode", "Tạo mã giảm giá"),
        BotCommand("noti", "Gửi thông báo toàn hệ thống"),
        BotCommand("duyet", "Duyệt đơn thủ công"),
        BotCommand("sync", "Đồng bộ đơn hàng từ web chủ"),
        BotCommand("cancel", "Hủy thao tác đang làm"),
    ]

    try:
        await application.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        for aid in ADMIN_IDS:
            try:
                await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=aid))
            except Exception:
                pass
        logger.info("✅ Đã cập nhật danh sách lệnh Telegram Menu thành công.")
    except Exception as e:
        logger.warning(f"Không thể cập nhật BotCommand: {e}")

    if getattr(config, "SEPAY_API_TOKEN", ""):
        asyncio.create_task(sepay_worker(application.bot))
        logger.info("⚡ Đã kích hoạt quét giao dịch tự động SePay.")

    asyncio.create_task(keep_alive_worker())
    logger.info("⚡ Đã kích hoạt cơ chế giữ máy chủ Render hoạt động 24/7.")

    async def sync_upstream_worker():
        from order_service import sync_upstream_orders
        while True:
            try:
                await asyncio.to_thread(sync_upstream_orders)
            except Exception as e_s:
                logger.warning(f"Sync upstream worker error: {e_s}")
            await asyncio.sleep(600)  # Lặp lại mỗi 10 phút

    asyncio.create_task(sync_upstream_worker())
    logger.info("⚡ Đã kích hoạt luồng tự động đồng bộ đơn hàng từ máy chủ CTV (web chủ).")


def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ LỖI: Chưa cấu hình TELEGRAM_BOT_TOKEN!")
        sys.exit(1)

    print("🚀 Đang khởi động Bot AloPremium.shop (Locket Gold & Spotify Premium)...")

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(True)
        .connection_pool_size(64)
        .build()
    )

    # ── ConversationHandler: Luồng mua hàng (allow_reentry=True, nhận click gói liên tục) ──
    buy_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_plan, pattern=r"^plan:"),
        ],
        states={
            WAITING_IDENTIFIER: [
                CallbackQueryHandler(cb_plan, pattern=r"^plan:"),
                CallbackQueryHandler(cb_product, pattern=r"^product:"),
                CallbackQueryHandler(cb_back_products, pattern=r"^back_products$"),
                CallbackQueryHandler(cb_back_main, pattern=r"^back_main$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_identifier),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("menu", menu_cmd),
            CommandHandler("web", web_cmd),
            CommandHandler("account", account_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("apidocs", apidocs_cmd),
            CommandHandler("setlang", setlang_cmd),
            CommandHandler("myorders", myorders_cmd),
            CommandHandler("support", support_cmd),
            CommandHandler("cancel", cancel_conv),
            CallbackQueryHandler(cb_plan, pattern=r"^plan:"),
            CallbackQueryHandler(cb_back_main, pattern=r"^back_main$"),
            CallbackQueryHandler(cb_back_products, pattern=r"^back_products$"),
            CallbackQueryHandler(cb_product, pattern=r"^product:"),
            CallbackQueryHandler(cb_support, pattern=r"^support$"),
            CallbackQueryHandler(cb_zalo_group, pattern=r"^zalo_group$"),
            CallbackQueryHandler(cb_show_guide, pattern=r"^show_guide$"),
            CallbackQueryHandler(cb_my_orders, pattern=r"^my_orders$"),
            CallbackQueryHandler(cb_my_account, pattern=r"^my_account$"),
        ],
        allow_reentry=True,
        per_user=True,
        per_chat=True,
        per_message=False,
    )

    # ── Lệnh người dùng ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("web",       web_cmd))
    app.add_handler(CommandHandler("zalo",      zalo_cmd))
    app.add_handler(CommandHandler("account",   account_cmd))
    app.add_handler(CommandHandler("apidocs",   apidocs_cmd))
    app.add_handler(CommandHandler("apierrors", apierrors_cmd))
    app.add_handler(CommandHandler("setlang",   setlang_cmd))
    app.add_handler(CommandHandler("help",      help_cmd))
    app.add_handler(CommandHandler("menu",      menu_cmd))
    app.add_handler(CommandHandler("myorders",  myorders_cmd))
    app.add_handler(CommandHandler("support",   support_cmd))
    app.add_handler(CommandHandler("guide",      guide_cmd))
    app.add_handler(CommandHandler("resetspotify", resetspotify_user_cmd))
    app.add_handler(CommandHandler("coupon",    coupon_cmd))
    app.add_handler(CommandHandler("magg",      coupon_cmd))
    app.add_handler(CommandHandler("cancel",    cancel_conv))

    # ── Lệnh Admin ───────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin",     admin_cmd))
    app.add_handler(CommandHandler("setprice",  setprice_cmd))
    app.add_handler(CommandHandler("duyet",     duyet_cmd))
    app.add_handler(CommandHandler("sync",      sync_cmd))
    app.add_handler(CommandHandler("coin",      coin_cmd))
    app.add_handler(CommandHandler("balance",   coin_cmd))
    app.add_handler(CommandHandler("packages",  packages_cmd))
    app.add_handler(CommandHandler("noti",      noti_cmd))
    app.add_handler(CommandHandler("notistop",  notistop_cmd))
    app.add_handler(CommandHandler("rs",        rs_cmd))
    app.add_handler(CommandHandler("resetspotify", rs_cmd))
    app.add_handler(CommandHandler("stats",     stats_cmd))
    app.add_handler(CommandHandler("users",     users_cmd))
    app.add_handler(CommandHandler("find",      find_cmd))
    app.add_handler(CommandHandler("ban",       ban_cmd))
    app.add_handler(CommandHandler("unban",     unban_cmd))
    app.add_handler(CommandHandler("orders",    orders_cmd))
    app.add_handler(CommandHandler("tokens",    tokens_cmd))
    app.add_handler(CommandHandler("checkbank", checkbank_cmd))
    app.add_handler(CommandHandler("addcode",   addcode_cmd))
    app.add_handler(CommandHandler("delcode",   delcode_cmd))
    app.add_handler(CommandHandler("codes",     codes_cmd))

    # ── Luồng mua hàng ───────────────────────────────────────────────────────
    app.add_handler(buy_conv)
    app.add_handler(CallbackQueryHandler(cb_plan, pattern=r"^plan:"))

    # ── Callback người dùng ──────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_show_guide,   pattern=r"^show_guide$"))
    app.add_handler(CallbackQueryHandler(cb_user_reset_spotify_menu, pattern=r"^user_reset_spotify_menu$"))
    app.add_handler(CallbackQueryHandler(cb_coupon,        pattern=r"^coupon:"))
    app.add_handler(CallbackQueryHandler(cb_coupon_info,   pattern=r"^coupon_info:"))
    app.add_handler(CallbackQueryHandler(cb_product,       pattern=r"^product:"))
    app.add_handler(CallbackQueryHandler(cb_ai_studio_opt, pattern=r"^ai_studio_opt:"))
    app.add_handler(CallbackQueryHandler(cb_buy_studio,    pattern=r"^buy_studio:"))
    app.add_handler(CallbackQueryHandler(cb_paid,          pattern=r"^paid:"))
    app.add_handler(CallbackQueryHandler(cb_buy,           pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(cb_cancel,        pattern=r"^cancel:"))
    app.add_handler(CallbackQueryHandler(cb_my_orders,     pattern=r"^my_orders$"))
    app.add_handler(CallbackQueryHandler(cb_my_account,    pattern=r"^my_account$"))
    app.add_handler(CallbackQueryHandler(cb_cmd_setlang,   pattern=r"^cmd_setlang$"))
    app.add_handler(CallbackQueryHandler(cb_lang,          pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(cb_apidocs,       pattern=r"^apidocs:"))
    app.add_handler(CallbackQueryHandler(cb_get_mobileconfig, pattern=r"^get_mobileconfig$"))
    app.add_handler(CallbackQueryHandler(cb_show_qr,          pattern=r"^show_qr(:.*)?$"))
    app.add_handler(CallbackQueryHandler(cb_support,       pattern=r"^support$"))
    app.add_handler(CallbackQueryHandler(cb_zalo_group,    pattern=r"^zalo_group$"))
    app.add_handler(CallbackQueryHandler(cb_back_products, pattern=r"^back_products$"))
    app.add_handler(CallbackQueryHandler(cb_back_main,     pattern=r"^back_main$"))

    # ── Callback admin ───────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_approve, pattern=r"^admin_approve:"))
    app.add_handler(CallbackQueryHandler(cb_admin_reject,  pattern=r"^admin_reject:"))
    app.add_handler(CallbackQueryHandler(cb_admin,         pattern=r"^admin:"))

    # ── Text input handler (User Coupon & Admin) ─────────────────────────────
    async def unified_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if await handle_user_coupon_text(update, ctx):
            return
        await handle_admin_text_input(update, ctx)

    app.add_handler(MessageHandler(
        (filters.ALL) & ~filters.COMMAND,
        unified_text_handler
    ))

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("Exception while handling an update:", exc_info=context.error)

    app.add_error_handler(error_handler)

    # Khởi động Web App Storefront & API Server trên cổng 8080 (hoặc $PORT trên Render)
    web_server.start_web_server(bot=app.bot)
    print("✅ Web App Storefront & Bot Telegram đã sẵn sàng hoạt động 24/7!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        print("💥 FATAL ERROR ON STARTUP:")
        traceback.print_exc()
        sys.exit(1)
