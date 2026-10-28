"""
bot.py – Entry point của Bot Đa Năng 3-in-1:
1. Gói Locket Gold VIP (API CTV)
2. Gói Spotify Premium (API CTV)
3. Gói Siêu VIP 3-in-1 (Locket + Spotify + YouTube 2099 - Proxy & DoH)
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

from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
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
    cb_back_main, cb_back_products,
    receive_identifier, cancel_conv, resetspotify_user_cmd, guide_cmd, cb_show_guide, cb_user_reset_spotify_menu,
    WAITING_IDENTIFIER,
)
from handlers.admin_handlers import (
    admin_cmd, cb_admin,
    cb_admin_approve, cb_admin_reject,
    noti_cmd, notistop_cmd,
    rs_cmd, stats_cmd, users_cmd, find_cmd,
    ban_cmd, unban_cmd, orders_cmd, tokens_cmd,
    checkbank_cmd, addcode_cmd, delcode_cmd, coin_cmd, packages_cmd, duyet_cmd,
    handle_admin_text_input,
)

# ── Health-check HTTP server giữ bot sống 24/7 trên Render ───────────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"Bot Locket Gold + Spotify + 3in1 is running 24/7!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info(f"🌐 Health-check HTTP server da khoi dong tren cong {port}")


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
                    content = str(tx.get("transaction_content", "")).upper()
                    amount_in = float(tx.get("amount_in", 0) or 0)

                    # Khớp mã đơn ORDER_XXXX hoặc XXXX và số tiền >= giá gói
                    if (order_id in content or f"ORDER_{order_id}" in content) and amount_in >= req_amount:
                        logger.info(f"✅ SePay tự động phát hiện thanh toán cho đơn ORDER_{order_id} ({amount_in}đ)!")
                        ok, msg = await execute_order_activation(bot, order["order_id"])
                        if ok:
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
    """Vòng lặp chạy ngầm quét biến động số dư Techcombank mỗi 8 giây"""
    logger.info("🚀 Luồng SePay worker đã khởi động (quét Techcombank tự động)...")
    while True:
        try:
            await check_sepay_auto_payments(bot)
        except Exception as e:
            logger.warning(f"SePay worker loop error: {e}")
        await asyncio.sleep(8)

async def post_init(application):
    """Thiết lập danh sách lệnh Menu Telegram cho Người dùng và Admin"""
    user_commands = [
        BotCommand("start", "Menu chính & Mua gói"),
        BotCommand("account", "Tài khoản của tôi"),
        BotCommand("myorders", "Đơn hàng đã mua"),
        BotCommand("resetspotify", "Reset thiết bị Spotify"),
        BotCommand("support", "Hỗ trợ CSKH"),
        BotCommand("guide", "Hướng dẫn cài đặt iOS"),
        BotCommand("help", "Hướng dẫn sử dụng"),
    ]

    admin_commands = [
        BotCommand("start", "Menu chính"),
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


def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ LỖI: Chưa cấu hình TELEGRAM_BOT_TOKEN!")
        sys.exit(1)

    print("🚀 Đang khởi động Bot VIP 3-in-1 (Locket + Spotify + 3-in-1 Combo)...")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # ── ConversationHandler: Luồng mua hàng ──────────────────────────────────
    buy_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_plan, pattern=r"^plan:"),
        ],
        states={
            WAITING_IDENTIFIER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_identifier),
            ],
        },
        fallbacks=[
            CommandHandler("start", start),
            CommandHandler("menu", menu_cmd),
            CommandHandler("account", account_cmd),
            CommandHandler("help", help_cmd),
            CommandHandler("apidocs", apidocs_cmd),
            CommandHandler("setlang", setlang_cmd),
            CommandHandler("myorders", myorders_cmd),
            CommandHandler("support", support_cmd),
            CommandHandler("cancel", cancel_conv),
            CallbackQueryHandler(cb_back_main, pattern=r"^back_main$"),
            CallbackQueryHandler(cb_back_products, pattern=r"^back_products$"),
            CallbackQueryHandler(cb_product, pattern=r"^product:"),
        ],
        per_user=True,
        per_chat=True,
        per_message=False,
    )

    # ── Lệnh người dùng ──────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",     start))
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
    app.add_handler(CommandHandler("cancel",    cancel_conv))

    # ── Lệnh Admin ───────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin",     admin_cmd))
    app.add_handler(CommandHandler("duyet",     duyet_cmd))
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

    # ── Luồng mua hàng ───────────────────────────────────────────────────────
    app.add_handler(buy_conv)

    # ── Callback người dùng ──────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_show_guide,   pattern=r"^show_guide$"))
    app.add_handler(CallbackQueryHandler(cb_user_reset_spotify_menu, pattern=r"^user_reset_spotify_menu$"))
    app.add_handler(CallbackQueryHandler(cb_product,       pattern=r"^product:"))
    app.add_handler(CallbackQueryHandler(cb_paid,          pattern=r"^paid:"))
    app.add_handler(CallbackQueryHandler(cb_buy,           pattern=r"^buy:"))
    app.add_handler(CallbackQueryHandler(cb_cancel,        pattern=r"^cancel:"))
    app.add_handler(CallbackQueryHandler(cb_my_orders,     pattern=r"^my_orders$"))
    app.add_handler(CallbackQueryHandler(cb_my_account,    pattern=r"^my_account$"))
    app.add_handler(CallbackQueryHandler(cb_cmd_setlang,   pattern=r"^cmd_setlang$"))
    app.add_handler(CallbackQueryHandler(cb_lang,          pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(cb_apidocs,       pattern=r"^apidocs:"))
    app.add_handler(CallbackQueryHandler(cb_get_mobileconfig, pattern=r"^get_mobileconfig$"))
    app.add_handler(CallbackQueryHandler(cb_support,       pattern=r"^support$"))
    app.add_handler(CallbackQueryHandler(cb_back_products, pattern=r"^back_products$"))
    app.add_handler(CallbackQueryHandler(cb_back_main,     pattern=r"^back_main$"))

    # ── Callback admin ───────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(cb_admin_approve, pattern=r"^admin_approve:"))
    app.add_handler(CallbackQueryHandler(cb_admin_reject,  pattern=r"^admin_reject:"))
    app.add_handler(CallbackQueryHandler(cb_admin,         pattern=r"^admin:"))

    # ── Admin input handler ──────────────────────────────────────────────────
    app.add_handler(MessageHandler(
        (filters.ALL) & ~filters.COMMAND,
        handle_admin_text_input
    ))

    # Khởi động web server ngầm để Render ping 24/7
    start_health_server()
    print("✅ Bot đã sẵn sàng nhận tin nhắn trên Telegram 24/7!")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
