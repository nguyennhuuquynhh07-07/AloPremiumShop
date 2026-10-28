import asyncio
import io
import os
import sys
import requests

# Đảm bảo mã hóa UTF-8 trên Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import config
from locket_service import (
    clean_input,
    resolve_locket_profile,
    check_server_health,
    get_stats,
)
from order_manager import (
    create_order,
    get_order,
    update_order_status,
    build_qr_url,
    get_pending_orders,
)

def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", ".") + "đ"

# Cấu hình logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Text hướng dẫn cài đặt iOS
GUIDE_TEXT = """
📲 *HƯỚNG DẪN CÀI ĐẶT CẤU HÌNH TRÊN IPHONE (iOS)*

*Bước 1: Copy link dán vào Safari để tải hồ sơ*
• Bấm nút *📋 Copy Link Tải Hồ Sơ* (hoặc chạm vào dòng link) để sao chép link.
• Mở trình duyệt *Safari* trên iPhone, dán link vừa copy vào thanh địa chỉ rồi bấm *Đi* (Go).
• Khi Safari hỏi _"Trang web này đang cố tải về một hồ sơ cấu hình. Bạn có muốn cho phép không?"_, chọn *Cho phép* (Allow).
• Thông báo hiện lên: _"Đã tải về hồ sơ"_, chọn *Đóng*.
*(Hồ sơ sẽ tự động nạp thẳng vào Cài đặt của iPhone, bạn KHÔNG CẦN vào ứng dụng Tệp!)*

*Bước 2: Cài đặt hồ sơ vào hệ thống*
• Mở ứng dụng *Cài đặt* (Settings) trên iPhone.
• Ở ngay dòng đầu tiên (dưới tên iCloud của bạn), nhấn vào *Đã tải về hồ sơ* (Profile Downloaded).
• Nhấn nút *Cài đặt* (Install) ở góc trên bên phải -> Nhập mật khẩu mở khóa màn hình iPhone -> Tiếp tục nhấn *Cài đặt*.

*Bước 3: Bật tin cậy chứng chỉ gốc (Quan trọng nhất!)*
• Vào *Cài đặt* (Settings) -> *Cài đặt chung* (General) -> *Giới thiệu* (About).
• Kéo xuống dưới cùng, chọn *Cài đặt tin cậy chứng nhận* (Certificate Trust Settings).
• Tại mục _"Bật tin cậy hoàn toàn cho các chứng nhận gốc"_, tìm dòng *Locket Gold Root CA* và *BẬT CÔNG TẮC XANH* (ON).
• Chọn *Tiếp tục* (Continue) để xác nhận.

🎉 *Hoàn tất!* Mở app Locket, Spotify hoặc YouTube lên để tận hưởng các tính năng VIP!
"""

ABOUT_TEXT = """
ℹ️ *NGUYÊN LÝ HOẠT ĐỘNG & LƯU Ý BẢO MẬT*

💡 *Nguyên lý:*
• Cấu hình này sử dụng cơ chế *DNS over HTTPS (DoH)* kết hợp *Chứng chỉ Root CA*.
• Khi điện thoại của bạn gửi yêu cầu xác thực gói trả phí tới máy chủ RevenueCat (`api.revenuecat.com`) của Locket hoặc các dịch vụ quảng cáo của YouTube/Spotify, DNS sẽ điều hướng qua máy chủ proxy trung gian.
• Máy chủ này sẽ phản hồi giả lập (spoofing) rằng tài khoản của bạn đã mua gói *Gold/Premium* đến năm 2099, đồng thời chặn các tên miền quảng cáo.

⚠️ *Lưu ý quan trọng:*
1. Đây là giải pháp can thiệp phía thiết bị (Client-side bypass), *không phải kích hoạt vĩnh viễn trên máy chủ chính thức* của Locket/Spotify/Google.
2. Nếu bạn tắt cấu hình DNS, xóa chứng chỉ hoặc đổi sang thiết bị khác, tính năng VIP sẽ mất.
3. Vì cần cài chứng chỉ Root CA bên thứ ba để can thiệp HTTPS, bạn nên cân nhắc tính an toàn thông tin cá nhân và chỉ sử dụng cho mục đích thử nghiệm/trải nghiệm.
"""

def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("📖 Hướng Dẫn Cài Đặt iOS", callback_data="show_guide"),
            InlineKeyboardButton("📡 Trạng Thái Server", callback_data="server_status"),
        ],
        [
            InlineKeyboardButton("ℹ️ Nguyên Lý & Lưu Ý", callback_data="show_about"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /start"""
    user_first = update.effective_user.first_name or "bạn"
    msg = f"""
👋 Chào *{user_first}*!

Chào mừng bạn đến với **Bot Kích Hoạt 3-in-1**:
👑 *Locket Gold VIP (Vĩnh viễn 2099)*
🎵 *Spotify Premium*
▶️ *YouTube Premium* (Chặn 100% quảng cáo + PiP phát trong nền)
💰 **Giá kích hoạt trọn gói:** *{format_price(config.PRICE_VND)}* / Tài khoản

🎯 *Cách thức mua gói VIP:*
1️⃣ Gửi **Username** hoặc **Link Locket** của bạn vào đây (Ví dụ: `@conlaigii` hoặc `locket.cam/conlaigii`).
2️⃣ Hệ thống kiểm tra tài khoản và gửi mã QR thanh toán {format_price(config.PRICE_VND)}.
3️⃣ Chuyển khoản xong, bấm xác nhận để nhận ngay Link Cấu Hình DNS!
"""
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /help"""
    msg = f"""
📚 *DANH SÁCH LỆNH CỦA BOT:*

• `/start` : Bắt đầu và xem menu chính
• `/guide` : Hướng dẫn chi tiết cách cài đặt trên Safari
• `/status` : Kiểm tra trạng thái máy chủ DNS
• `/about` : Giải thích nguyên lý hoạt động & lưu ý bảo mật
• `/lookup <username>` : Tra cứu UID Locket
• `/myid` : Xem Telegram Chat ID của bạn (dành cho Admin)
• `/duyet <mã_đơn>` : Admin duyệt đơn hàng thanh toán

💰 Giá kích hoạt: *{format_price(config.PRICE_VND)}*
👉 Bạn có thể gửi username hoặc link Locket bất cứ lúc nào để bắt đầu!
"""
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def guide_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /guide"""
    await update.message.reply_text(GUIDE_TEXT, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /about"""
    await update.message.reply_text(ABOUT_TEXT, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /status"""
    loading_msg = await update.message.reply_text("⏳ Đang kiểm tra kết nối tới máy chủ DNS...")
    res = check_server_health()
    stats = get_stats()

    if res["online"]:
        status_line = f"🟢 *Hoạt động tốt* (Ping: `{res['latency_ms']} ms`)"
    else:
        status_line = f"🔴 *Mất kết nối* (`{res.get('error', 'Không phản hồi')}`)"

    msg = f"""
📡 *TÌNH TRẠNG HỆ THỐNG MÁY CHỦ DNS PROXY:*

• **Máy chủ:** `{res['server_url']}`
• **Trạng thái:** {status_line}
• **Tổng số tài khoản đã kích hoạt:** `{stats['user_count']}` tài khoản
• **Hỗ trợ iOS:** Full iOS 14 — 18.x / 19+
• **Các dịch vụ hỗ trợ:** Locket Gold VIP, Spotify Premium, YouTube AdBlock & PiP
"""
    await loading_msg.edit_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def lookup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /lookup <username>"""
    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng cung cấp username hoặc link Locket.\nVí dụ: `/lookup hippobbie`", parse_mode="Markdown")
        return

    raw = context.args[0]
    loading = await update.message.reply_text("🔍 Đang tra cứu thông tin tài khoản...")
    profile = resolve_locket_profile(raw)

    if not profile["ok"]:
        await loading.edit_text(f"❌ {profile['error']}")
        return

    caption = f"""
👤 *THÔNG TIN TÀI KHOẢN LOCKET:*
• **Tên hiển thị:** {profile['full_name']}
• **Username:** `@{profile['username']}`
• **UID (28 ký tự):** `{profile['uid']}`
• **Token DNS:** `{profile['token']}`
• **Nguồn dữ liệu:** `{profile['source']}`
"""
    await loading.delete()
    if profile.get("avatar"):
        try:
            await update.message.reply_photo(photo=profile["avatar"], caption=caption, parse_mode="Markdown")
            return
        except Exception:
            pass
    await update.message.reply_text(caption, parse_mode="Markdown")

async def send_activated_profile(context: ContextTypes.DEFAULT_TYPE, chat_id: int, order: dict):
    """Gửi link cấu hình DNS đã kích hoạt sau khi thanh toán thành công"""
    username = order["username"]
    full_name = order.get("full_name") or username
    uid = order.get("uid") or ""
    token = order.get("token") or ""
    download_url = order["download_url"]

    info_text = f"""
🎉 *THANH TOÁN THÀNH CÔNG! ĐÃ KÍCH HOẠT VIP 3-IN-1*

👤 **Người dùng:** {full_name} (`@{username}`)
🆔 **UID:** `{uid}`
🔑 **Token DNS:** `{token}`
📦 **Gói kích hoạt:**
  • 💛 *Locket Gold Pro* (Vĩnh viễn 2099)
  • 🎵 *Spotify Premium*
  • ▶️ *YouTube Premium* (Chặn QC + PiP nền)
🛡️ **Trạng thái:** ✅ *Đã thanh toán {format_price(config.PRICE_VND)}*

📋 **Link Tải Hồ Sơ (Chạm để sao chép):**
`{download_url}`

👉 *Copy link trên rồi mở Safari dán vào thanh địa chỉ để tải hồ sơ về máy!*
"""
    buttons = [
        [
            InlineKeyboardButton("📋 Copy Link Tải Hồ Sơ", api_kwargs={"copy_text": {"text": download_url}}),
        ],
        [
            InlineKeyboardButton("📖 Hướng Dẫn Cài Đặt", callback_data="show_guide"),
            InlineKeyboardButton("🔄 Kích Hoạt Tài Khoản Khác", callback_data="start_over"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    avatar = order.get("avatar")
    if avatar:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=avatar,
                caption=info_text,
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
            return
        except Exception:
            pass

    await context.bot.send_message(
        chat_id=chat_id,
        text=info_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi người dùng gửi tin nhắn (username hoặc link Locket) -> Tạo hóa đơn thanh toán 200.000đ"""
    text = update.message.text
    if not text:
        return

    clean = clean_input(text)
    if not clean:
        await update.message.reply_text("⚠️ Vui lòng gửi một Username hoặc Link Locket hợp lệ!")
        return

    loading = await update.message.reply_text(f"🔍 Đang kiểm tra tài khoản `@`*{clean}*...", parse_mode="Markdown")

    profile = resolve_locket_profile(clean)

    if not profile["ok"]:
        await loading.edit_text(
            f"❌ *Không tìm thấy tài khoản:*\n{profile['error']}\n\n💡 Mẹo: Bạn có thể vào app Locket -> Mời bạn bè -> Sao chép liên kết rồi dán vào đây.",
            parse_mode="Markdown"
        )
        return

    await loading.delete()

    # Tạo đơn hàng thanh toán 200.000đ
    order = create_order(
        chat_id=update.effective_chat.id,
        tg_user=update.effective_user.name or update.effective_user.full_name,
        locket_data=profile
    )
    order_id = order["order_id"]
    memo = order["memo"]
    amount_str = format_price(config.PRICE_VND)
    qr_url = build_qr_url(config.BANK_CODE, config.BANK_ACCOUNT, config.PRICE_VND, memo)

    invoice_text = f"""
💳 *HÓA ĐƠN THANH TOÁN KÍCH HOẠT VIP 3-IN-1*

👤 **Tài khoản Locket:** {profile['full_name']} (`@{profile['username']}`)
🆔 **UID:** `{profile['uid']}`
📦 **Gói dịch vụ:** Locket Gold 2099 + Spotify + YouTube Premium
💰 **Số tiền thanh toán:** *{amount_str}*

━━━━━━━━━━━━━━━━━━━
🏦 **Ngân hàng:** {config.BANK_NAME}
🔢 **Số tài khoản:** `{config.BANK_ACCOUNT}`
👤 **Chủ tài khoản:** {config.ACCOUNT_HOLDER}
📝 **Nội dung chuyển khoản (bắt buộc):**
`{memo}`
━━━━━━━━━━━━━━━━━━━

⚠️ *Quét mã VietQR ở trên hoặc chuyển khoản đúng {amount_str} kèm đúng nội dung `{memo}`.*
👉 *Sau khi chuyển tiền thành công, hãy bấm nút "Tôi Đã Chuyển Khoản" bên dưới để nhận cấu hình DNS nhé!*
"""

    buttons = [
        [
            InlineKeyboardButton(f"✅ Tôi Đã Chuyển Khoản {amount_str}", callback_data=f"paid:{order_id}"),
        ],
        [
            InlineKeyboardButton("📖 Hướng Dẫn Cài Đặt", callback_data="show_guide"),
            InlineKeyboardButton("❌ Hủy Đơn", callback_data=f"cancel:{order_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    # Gửi ảnh mã QR thanh toán
    try:
        await update.message.reply_photo(
            photo=qr_url,
            caption=invoice_text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.warning(f"Failed to send QR photo: {e}")
        await update.message.reply_text(invoice_text, parse_mode="Markdown", reply_markup=reply_markup)

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý sự kiện bấm nút Inline"""
    query = update.callback_query
    await query.answer()

    if query.data == "show_guide":
        await query.message.reply_text(GUIDE_TEXT, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif query.data == "show_about":
        await query.message.reply_text(ABOUT_TEXT, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif query.data == "server_status":
        res = check_server_health()
        stats = get_stats()
        if res["online"]:
            status_line = f"🟢 *Hoạt động tốt* (Ping: `{res['latency_ms']} ms`)"
        else:
            status_line = f"🔴 *Mất kết nối* (`{res.get('error', 'Không phản hồi')}`)"
        msg = f"""
📡 *TÌNH TRẠNG MÁY CHỦ DNS PROXY:*
• **Máy chủ:** `{res['server_url']}`
• **Trạng thái:** {status_line}
• **Số lượng tài khoản đã tạo:** `{stats['user_count']}`
"""
        await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif query.data.startswith("copy_link:"):
        await query.answer("📋 Đã sao chép link! Mở Safari dán vào để tải hồ sơ nhé.", show_alert=False)
    elif query.data.startswith("paid:"):
        order_id = query.data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await query.message.reply_text("❌ Đơn hàng không tồn tại hoặc đã hết hạn.")
            return

        if order.get("status") == "approved":
            await send_activated_profile(context, query.message.chat_id, order)
            return

        # Nếu bật chế độ tự động duyệt (AUTO_APPROVE = True)
        if config.AUTO_APPROVE:
            update_order_status(order_id, "approved")
            await send_activated_profile(context, query.message.chat_id, order)
            return

        # Cập nhật trạng thái đơn thành đã bấm thanh toán
        update_order_status(order_id, "paid")
        amount_str = format_price(order['amount'])

        await query.message.reply_text(
            f"⏳ *ĐÃ TIẾP NHẬN YÊU CẦU XÁC NHẬN!*\n\nCảm ơn bạn! Đơn hàng `{order_id}` ({amount_str}) của bạn đang được kiểm tra.\nSau khi xác nhận giao dịch thành công, link cấu hình DNS sẽ được gửi ngay tại đây!",
            parse_mode="Markdown"
        )

        # Gửi thông báo cho Admin nếu có ADMIN_ID
        if config.ADMIN_ID:
            try:
                adm_text = f"""
🔔 *CÓ ĐƠN HÀNG 200.000Đ CẦN DUYỆT!*

🏷️ **Mã đơn:** `{order_id}`
👤 **Khách hàng:** {order['tg_user']} (Chat ID: `{order['chat_id']}`)
📱 **Locket:** `@{order['username']}` ({order['full_name']})
🆔 **UID:** `{order['uid']}`
💰 **Số tiền:** {amount_str}
📝 **Nội dung CK:** `{order['memo']}`
⏰ **Thời gian:** {order['created_at']}
"""
                adm_buttons = [
                    [
                        InlineKeyboardButton(f"✅ Duyệt & Cấp DNS ({order_id})", callback_data=f"adm_appr:{order_id}"),
                        InlineKeyboardButton(f"❌ Từ Chối", callback_data=f"adm_rej:{order_id}"),
                    ]
                ]
                await context.bot.send_message(
                    chat_id=int(config.ADMIN_ID),
                    text=adm_text,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(adm_buttons)
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin: {e}")

    elif query.data.startswith("adm_appr:"):
        order_id = query.data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await query.message.reply_text(f"❌ Đơn hàng `{order_id}` không tồn tại.")
            return

        update_order_status(order_id, "approved")
        await query.edit_message_text(f"✅ *ĐÃ DUYỆT ĐƠN HÀNG `{order_id}`! Cấu hình DNS đã được gửi cho khách hàng.*", parse_mode="Markdown")
        await send_activated_profile(context, order["chat_id"], order)

    elif query.data.startswith("adm_rej:"):
        order_id = query.data.split(":", 1)[1]
        order = get_order(order_id)
        if not order:
            await query.message.reply_text(f"❌ Đơn hàng `{order_id}` không tồn tại.")
            return

        update_order_status(order_id, "rejected")
        await query.edit_message_text(f"❌ *ĐÃ TỪ CHỐI ĐƠN HÀNG `{order_id}`.*", parse_mode="Markdown")
        try:
            await context.bot.send_message(
                chat_id=order["chat_id"],
                text=f"❌ *Đơn hàng `{order_id}` của bạn chưa được xác nhận thanh toán.*\nVui lòng kiểm tra lại giao dịch {format_price(order['amount'])} hoặc liên hệ Admin.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    elif query.data.startswith("cancel:"):
        order_id = query.data.split(":", 1)[1]
        update_order_status(order_id, "cancelled")
        await query.message.reply_text("❌ Đã hủy đơn hàng. Bạn có thể gửi lại Username Locket bất cứ lúc nào để tạo đơn mới.", parse_mode="Markdown")

    elif query.data == "start_over":
        await query.message.reply_text("💬 Vui lòng gửi Username hoặc Link Locket bạn muốn kích hoạt:", parse_mode="Markdown")

async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /myid xem Telegram ID để cấu hình Admin"""
    chat_id = update.effective_chat.id
    msg = f"""
🆔 *THÔNG TIN TELEGRAM CỦA BẠN:*
• **Chat ID:** `{chat_id}`
• **Tên:** {update.effective_user.full_name}
• **Username:** @{update.effective_user.username or 'Chưa đặt'}

👉 *Nếu bạn là Chủ bot / Quản trị viên, hãy copy `Chat ID` trên và dán vào `ADMIN_ID` trong file `config.py` để nhận thông báo duyệt đơn hàng 200.000đ nhé!*
"""
    await update.message.reply_text(msg, parse_mode="Markdown")

async def duyet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lệnh /duyet <mã_đơn> dành cho Admin duyệt đơn nhanh"""
    if config.ADMIN_ID and str(update.effective_user.id) != str(config.ADMIN_ID):
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng lệnh này.")
        return

    if not context.args:
        await update.message.reply_text("⚠️ Vui lòng nhập mã đơn hàng.\nVí dụ: `/duyet VIP1234`", parse_mode="Markdown")
        return

    order_id = context.args[0].upper()
    order = get_order(order_id)
    if not order:
        await update.message.reply_text(f"❌ Không tìm thấy đơn hàng `{order_id}`", parse_mode="Markdown")
        return

    update_order_status(order_id, "approved")
    await send_activated_profile(context, order["chat_id"], order)
    await update.message.reply_text(f"✅ Đã duyệt thành công đơn `{order_id}` cho @{order['username']}!", parse_mode="Markdown")

async def check_sepay_auto_payments(bot):
    """Kiểm tra biến động số dư ngân hàng Techcombank tự động qua SePay"""
    token = config.SEPAY_API_TOKEN
    if not token or token == "YOUR_SEPAY_API_TOKEN":
        return

    pending = get_pending_orders()
    if not pending:
        return

    url = "https://my.sepay.vn/userapi/transactions/list?limit=20"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code != 200:
            return
        data = r.json()
        transactions = data.get("transactions", [])
        if not transactions:
            return

        for order in pending:
            order_id = order["order_id"].upper()
            required_amount = float(order.get("amount", config.PRICE_VND))

            for tx in transactions:
                content = str(tx.get("transaction_content", "")).upper()
                amount_in = float(tx.get("amount_in", 0) or 0)

                # Khớp mã đơn (VIPxxxx) và số tiền chuyển >= 200.000đ
                if order_id in content and amount_in >= required_amount:
                    logger.info(f"✅ Tự động nhận diện thanh toán SePay cho đơn {order_id}!")
                    update_order_status(order_id, "approved")

                    # Gửi link cấu hình DNS đã kích hoạt cho khách hàng
                    dummy_context = type("DummyContext", (), {"bot": bot})()
                    await send_activated_profile(dummy_context, order["chat_id"], order)

                    # Báo tin nhắn chúc mừng cho khách
                    try:
                        await bot.send_message(
                            chat_id=order["chat_id"],
                            text=f"🔔 *HỆ THỐNG ĐÃ TỰ ĐỘNG NHẬN ĐƯỢC {format_price(int(amount_in))}!*\nCấu hình DNS VIP đã được kích hoạt thành công.",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

                    # Báo về Telegram của Admin
                    if config.ADMIN_ID:
                        try:
                            await bot.send_message(
                                chat_id=int(config.ADMIN_ID),
                                text=f"💰 *TỰ ĐỘNG NHẬN TIỀN THÀNH CÔNG!*\n\n• Mã đơn: `{order_id}`\n• Khách hàng: `@{order['username']}`\n• Số tiền: *{format_price(int(amount_in))}*\n• Cấu hình DNS đã tự động gửi cho khách!",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
                    break
    except Exception as e:
        logger.warning(f"SePay error: {e}")

async def sepay_worker(bot):
    """Vòng lặp chạy ngầm quét giao dịch mỗi 8 giây"""
    logger.info("🚀 Đã khởi động luồng tự động quét biến động số dư SePay (Techcombank)...")
    while True:
        try:
            await check_sepay_auto_payments(bot)
        except Exception as e:
            logger.warning(f"SePay worker loop error: {e}")
        await asyncio.sleep(8)

async def on_startup(app):
    if config.SEPAY_API_TOKEN:
        asyncio.create_task(sepay_worker(app.bot))
    else:
        logger.info("ℹ️ SEPAY_API_TOKEN chưa cấu hình -> Đang chạy ở chế độ Admin duyệt tay.")

def main():
    token = config.BOT_TOKEN
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("❌ LỖI: Bạn chưa cài đặt TELEGRAM_BOT_TOKEN!")
        print("1. Hãy mở bot @BotFather trên ứng dụng Telegram.")
        print("2. Gửi lệnh /newbot để tạo bot mới và lấy Token.")
        print("3. Điền Token vào file config.py hoặc tạo file .env với nội dung:")
        print("   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuVWXyz")
        print("=" * 60)
        sys.exit(1)

    # Khởi tạo event loop cho Python 3.12+ và Python 3.14+
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Khởi chạy health-check server ngầm (để chạy 24/7 trên Render / Koyeb)
    try:
        from keep_alive import keep_alive
        keep_alive()
    except Exception as e:
        logger.warning(f"Không thể khởi động keep_alive server: {e}")

    print("🚀 Đang khởi động Telegram Bot Kích Hoạt Locket Gold 3-in-1...")
    app = ApplicationBuilder().token(token).post_init(on_startup).build()

    # Đăng ký các handler
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("guide", guide_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("lookup", lookup_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("duyet", duyet_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot đã sẵn sàng nhận tin nhắn! Nhấn Ctrl + C để dừng bot.")
    app.run_polling()

if __name__ == "__main__":
    main()
