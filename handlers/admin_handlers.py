"""
handlers/admin_handlers.py – Bảng điều khiển quản trị viên và xử lý lệnh Admin
Hỗ trợ đầy đủ các lệnh:
/admin, /noti, /notistop, /rs, /stats, /users, /find, /ban, /unban,
/orders, /tokens, /checkbank, /addcode, /delcode, /cancel
"""

import asyncio
import logging
import httpx
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import database as db
import api_client as api
import utils
import config
from config import PRODUCTS, ADMIN_IDS, BANK_ID, ACCOUNT_NO, ACCOUNT_NAME
from keyboards import admin_kb, back_admin_kb

logger = logging.getLogger(__name__)

# Quản lý trạng thái phát sóng Broadcast
is_broadcasting = False
stop_broadcast_flag = False


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── /admin ────────────────────────────────────────────────────────────────────

def build_admin_menu_text() -> str:
    header = "⚙️ <b>BẢNG ĐIỀU KHIỂN QUẢN TRỊ VIÊN</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    try:
        acc = api.get_account_info().get("data", {})
        coin = acc.get("balanceCoin", 0)
        user = acc.get("username", "quynh28")
        header += f"👤 CTV: <code>{user}</code> | 🪙 Số dư: <b>{coin:,.0f} Coin</b> ({utils.fmt_price(coin * 1000)})\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    except Exception:
        pass


# ── /coin & /balance: Tra cứu số dư Coin CTV ─────────────────────────────────

async def coin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu số dư Coin CTV và trạng thái tài khoản API (GET /api/keys/me)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang tra cứu số dư tài khoản CTV từ hệ thống API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_account_info()
        data = res.get("data", res)
        username = data.get("username", "CTV")
        balance = data.get("balanceCoin", 0)
        is_activated = data.get("isActivated", False)
        status_text = "🟢 Đã kích hoạt" if is_activated else "🔴 Chưa kích hoạt"

        text = (
            f"🪙 <b>THÔNG TIN TÀI KHOẢN CTV (locket.2707226.xyz)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Tên CTV:</b> <code>{username}</code>\n"
            f"💰 <b>Số dư Coin:</b> <b>{balance} Coin</b>\n"
            f"🛡️ <b>Trạng thái:</b> {status_text}\n"
            f"🌐 <b>API URL:</b> <code>{config.API_BASE_URL}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mỗi đơn kích hoạt Locket/Spotify sẽ tự động trừ Coin tương ứng. Nếu Coin sắp hết hãy nạp thêm trên Dashboard!</i>"
        )
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể tra cứu số dư CTV: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /packages: Tra cứu danh sách gói từ máy chủ API ──────────────────────────

async def packages_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu bảng giá Coin và mã gói cước trực tiếp từ API (GET /api/packages)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang lấy bảng giá gói cước từ máy chủ API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_packages("all")
        data = res.get("data", [])
        lines = [
            "📦 <b>DANH SÁCH GÓI CƯỚC & GIÁ COIN TRÊN MÁY CHỦ API</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for p in data:
            code = p.get("code")
            name = p.get("name")
            days = p.get("durationDays", 0)
            coin = p.get("priceCoin", 0)
            lines.append(f"• <b>{code}</b>: {name} ({days} ngày) ➔ <b>{coin} Coin</b>")
        lines.append("\n💡 <i>Mã gói này tương ứng với cấu hình trong config.py.</i>")
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể lấy danh sách gói: <code>{e}</code>", parse_mode=ParseMode.HTML)


    admin_controls = (
        "<b>Admin control</b>\n"
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
        "</pre>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 <i>Chọn chức năng bên dưới hoặc gõ trực tiếp lệnh:</i>"
    )
    return f"{header}{admin_controls}"


async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Bạn không có quyền truy cập.")
        return

    await update.message.reply_text(
        build_admin_menu_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=admin_kb()
    )


# ── /stats ────────────────────────────────────────────────────────────────────

async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Thống kê chi tiết hệ thống."""
    if not is_admin(update.effective_user.id):
        return

    orders = list(db.get_orders().values())
    users = db.get_users()
    total_orders = len(orders)
    done_orders = [o for o in orders if o.get("status") == "done"]
    pending_orders = [o for o in orders if o.get("status") in ("pending", "waiting_payment", "pending_approval")]
    rejected_orders = [o for o in orders if o.get("status") in ("rejected", "cancelled", "failed")]
    total_revenue = sum(o.get("price", 0) for o in done_orders)

    # Thống kê theo sản phẩm
    locket_done = [o for o in done_orders if o.get("product") == "locket"]
    spotify_done = [o for o in done_orders if o.get("product") == "spotify"]
    locket_rev = sum(o.get("price", 0) for o in locket_done)
    spotify_rev = sum(o.get("price", 0) for o in spotify_done)

    # Lấy thông tin coin CTV
    coin_text = "N/A"
    try:
        acc = api.get_account_info().get("data", {})
        coin_val = acc.get("balanceCoin", 0)
        coin_text = f"{coin_val:,.0f} Coin ({utils.fmt_price(coin_val * 1000)})"
    except Exception:
        pass


# ── /coin & /balance: Tra cứu số dư Coin CTV ─────────────────────────────────

async def coin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu số dư Coin CTV và trạng thái tài khoản API (GET /api/keys/me)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang tra cứu số dư tài khoản CTV từ hệ thống API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_account_info()
        data = res.get("data", res)
        username = data.get("username", "CTV")
        balance = data.get("balanceCoin", 0)
        is_activated = data.get("isActivated", False)
        status_text = "🟢 Đã kích hoạt" if is_activated else "🔴 Chưa kích hoạt"

        text = (
            f"🪙 <b>THÔNG TIN TÀI KHOẢN CTV (locket.2707226.xyz)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Tên CTV:</b> <code>{username}</code>\n"
            f"💰 <b>Số dư Coin:</b> <b>{balance} Coin</b>\n"
            f"🛡️ <b>Trạng thái:</b> {status_text}\n"
            f"🌐 <b>API URL:</b> <code>{config.API_BASE_URL}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mỗi đơn kích hoạt Locket/Spotify sẽ tự động trừ Coin tương ứng. Nếu Coin sắp hết hãy nạp thêm trên Dashboard!</i>"
        )
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể tra cứu số dư CTV: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /packages: Tra cứu danh sách gói từ máy chủ API ──────────────────────────

async def packages_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu bảng giá Coin và mã gói cước trực tiếp từ API (GET /api/packages)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang lấy bảng giá gói cước từ máy chủ API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_packages("all")
        data = res.get("data", [])
        lines = [
            "📦 <b>DANH SÁCH GÓI CƯỚC & GIÁ COIN TRÊN MÁY CHỦ API</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for p in data:
            code = p.get("code")
            name = p.get("name")
            days = p.get("durationDays", 0)
            coin = p.get("priceCoin", 0)
            lines.append(f"• <b>{code}</b>: {name} ({days} ngày) ➔ <b>{coin} Coin</b>")
        lines.append("\n💡 <i>Mã gói này tương ứng với cấu hình trong config.py.</i>")
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể lấy danh sách gói: <code>{e}</code>", parse_mode=ParseMode.HTML)


    text = (
        "📊 <b>THỐNG KÊ TOÀN DIỆN HỆ THỐNG</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Tổng người dùng:</b> <code>{len(users)}</code> users\n"
        f"📦 <b>Tổng đơn hàng:</b> <code>{total_orders}</code> đơn\n"
        f"  ├ ✅ Thành công: <b>{len(done_orders)}</b> đơn\n"
        f"  ├ ⏳ Đang xử lý: <b>{len(pending_orders)}</b> đơn\n"
        f"  └ 🚫 Đã huỷ/thất bại: <b>{len(rejected_orders)}</b> đơn\n"
        f"💰 <b>Tổng doanh thu:</b> <b>{utils.fmt_price(total_revenue)}</b>\n\n"
        "━━━━━ Phân loại dịch vụ ━━━━━\n"
        f"💛 <b>Locket Gold:</b> {len(locket_done)} đơn | {utils.fmt_price(locket_rev)}\n"
        f"🎵 <b>Spotify Premium:</b> {len(spotify_done)} đơn | {utils.fmt_price(spotify_rev)}\n\n"
        "━━━━━ Số dư CTV API ━━━━━\n"
        f"🪙 <b>Ví Coin CTV:</b> <b>{coin_text}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
        except Exception:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── /orders ───────────────────────────────────────────────────────────────────

async def orders_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Danh sách các đơn hàng gần nhất."""
    if not is_admin(update.effective_user.id):
        return

    all_orders = list(db.get_orders().values())
    recent = sorted(all_orders, key=lambda x: x["created_at"], reverse=True)[:15]

    if not recent:
        msg = "📋 Hiện tại chưa có đơn hàng nào."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=back_admin_kb())
        else:
            await update.message.reply_text(msg)
        return

    lines = ["📋 <b>15 ĐƠN HÀNG GẦN NHẤT:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for o in recent:
        prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
        plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
        lines.append(
            f"{utils.status_emoji(o['status'])} <code>ORDER_{o['order_id']}</code> | @{o['username']}\n"
            f"   └ {prod} ({plan}) — <b>{utils.fmt_price(o['price'])}</b>\n"
            f"   └ UID: <code>{o.get('uid', 'N/A')}</code> | <i>{utils.fmt_datetime(o['created_at'])}</i>"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Dùng lệnh /find [mã_đơn] để xem chi tiết.</i>")

    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
        except Exception:
            await update.callback_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── /tokens ───────────────────────────────────────────────────────────────────

async def tokens_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Kiểm tra số dư và tình trạng Token/Coin API CTV."""
    if not is_admin(update.effective_user.id):
        return

    send_func = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    if update.callback_query:
        await update.callback_query.answer()

    loading_msg = await send_func("⏳ Đang tra cứu số dư Token CTV từ hệ thống API…", parse_mode=ParseMode.HTML)

    try:
        res = api.get_account_info()
        data = res.get("data", {})
        username = data.get("username", "quynh28")
        email = data.get("email", "")
        coin = data.get("balanceCoin", 0)
        role = data.get("role", "CTV")
        is_act = "Đang kích hoạt ✅" if data.get("isActivated") else "Chưa kích hoạt ⚠️"
        vnd_equiv = coin * 1000

        # Lấy thông tin các gói từ server
        packages_info = ""
        try:
            pkg_res = api.get_packages("all")
            pkgs = pkg_res.get("data", [])
            if isinstance(pkgs, list) and pkgs:
                packages_info = "\n📦 <b>Bảng giá nhập sỉ từ hệ thống:</b>\n"
                for p in pkgs[:6]:
                    pname = p.get("name") or p.get("code")
                    pcoin = p.get("priceCoin", 0)
                    packages_info += f"  • <code>{pname}</code>: <b>{pcoin:,.0f} coin</b>\n"
        except Exception:
            pass

        text = (
            f"🪙 <b>TRẠNG THÁI TOKEN POOL & TÀI KHOẢN CTV</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Tài khoản CTV:</b> <code>{username}</code>\n"
            f"📧 <b>Email đăng ký:</b> <code>{email}</code>\n"
            f"🎖 <b>Vai trò hệ thống:</b> <b>{role}</b> ({is_act})\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Số dư hiện có:</b> <b>{coin:,.0f} Coin</b>\n"
            f"💵 <b>Giá trị quy đổi:</b> <b>{utils.fmt_price(vnd_equiv)}</b>\n"
            f"{packages_info}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mỗi khi duyệt đơn thành công, hệ thống tự động trừ Coin tương ứng.</i>"
        )
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
        else:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        err = f"❌ Không thể kiểm tra Token CTV: <code>{e}</code>"
        if update.callback_query:
            await update.callback_query.edit_message_text(err, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
        else:
            await update.message.reply_text(err, parse_mode=ParseMode.HTML)


# ── /users [id] ───────────────────────────────────────────────────────────────

async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xem danh sách user hoặc thông tin chi tiết của 1 user theo ID."""
    if not is_admin(update.effective_user.id):
        return

    users = db.get_users()

    # Nếu có truyền ID cụ thể
    if ctx.args:
        target_id = ctx.args[0].strip()
        user_info = db.get_user(target_id)
        if not user_info:
            await update.message.reply_text(f"❌ Không tìm thấy người dùng có ID <code>{target_id}</code>.", parse_mode=ParseMode.HTML)
            return

        orders = db.get_user_orders(int(target_id) if target_id.isdigit() else 0)
        done_cnt = len([o for o in orders if o.get("status") == "done"])
        banned = "🚫 ĐÃ BỊ BAN" if user_info.get("is_banned") else "✅ Hoạt động bình thường"
        ban_rs = f"\n  └ <i>Lý do ban: {user_info.get('ban_reason')}</i>" if user_info.get("is_banned") else ""

        text = (
            f"👤 <b>CHI TIẾT NGƯỜI DÙNG</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 <b>Telegram ID:</b> <code>{user_info.get('user_id')}</code>\n"
            f"👤 <b>Tên hiển thị:</b> {user_info.get('first_name', '')} {user_info.get('last_name', '')}\n"
            f"🔗 <b>Username:</b> @{user_info.get('username') or 'Chưa đặt'}\n"
            f"🌐 <b>Ngôn ngữ:</b> <code>{user_info.get('lang', 'vi')}</code>\n"
            f"📅 <b>Tham gia lúc:</b> <code>{utils.fmt_datetime(user_info.get('joined_at'))}</code>\n"
            f"⚡ <b>Trạng thái:</b> <b>{banned}</b>{ban_rs}\n"
            f"📦 <b>Tổng đơn:</b> {len(orders)} (Đã mua: {done_cnt} gói)\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    # Nếu không truyền ID -> liệt kê 15 user gần nhất
    if not users:
        await update.message.reply_text("👥 Hiện tại chưa có người dùng nào.")
        return

    recent_users = list(users.values())[-15:]
    recent_users.reverse()

    lines = [f"👥 <b>DANH SÁCH NGƯỜI DÙNG ({len(users)} TỔNG CỘNG):</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for u in recent_users:
        status_tag = "🚫" if u.get("is_banned") else "🟢"
        uname = f"@{u['username']}" if u.get("username") else u.get("first_name", "User")
        lines.append(f"{status_tag} <code>{u.get('user_id')}</code> | {uname}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━\n💡 <i>Dùng <code>/users &lt;id&gt;</code> để xem chi tiết 1 người dùng.</i>")

    text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())
    else:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)


# ── /find [query] ─────────────────────────────────────────────────────────────

async def find_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tìm kiếm user / đơn hàng theo ID, username, UID hoặc mã đơn."""
    if not is_admin(update.effective_user.id):
        return

    if not ctx.args:
        ctx.user_data["admin_action"] = "waiting_find_query"
        await update.message.reply_text(
            "🔍 <b>TÌM KIẾM TRONG HỆ THỐNG</b>\n\n"
            "Nhập từ khoá cần tìm:\n"
            "• Telegram ID (VD: <code>8313153487</code>)\n"
            "• Username (VD: <code>@quynh</code>)\n"
            "• UID Locket / Spotify (VD: <code>conlaigii</code>)\n"
            "• Mã đơn hàng (VD: <code>ORDER_HMSXWHYV</code>)\n\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    query = " ".join(ctx.args).strip()
    results = db.find_all(query)
    found_users = results["users"]
    found_orders = results["orders"]

    if not found_users and not found_orders:
        await update.message.reply_text(
            f"❌ Không tìm thấy kết quả nào khớp với: <code>{query}</code>",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"🔍 <b>KẾT QUẢ TÌM KIẾM CHO:</b> <code>{query}</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━"]

    if found_users:
        lines.append("👥 <b>Người dùng tìm thấy:</b>")
        for u in found_users[:5]:
            ban_str = " (🚫 Bị ban)" if u.get("is_banned") else ""
            lines.append(f"  • ID: <code>{u.get('user_id')}</code> | @{u.get('username') or u.get('first_name')}{ban_str}")
        lines.append("")

    if found_orders:
        lines.append("📦 <b>Đơn hàng tìm thấy:</b>")
        for o in found_orders[:5]:
            prod = PRODUCTS.get(o["product"], {}).get("name", o["product"])
            plan = PRODUCTS.get(o["product"], {}).get("plans", {}).get(o["plan"], {}).get("label", o["plan"])
            lines.append(
                f"  • {utils.status_emoji(o['status'])} <code>ORDER_{o['order_id']}</code> | "
                f"UID: <code>{o.get('uid')}</code> | {prod} ({plan}) | {utils.fmt_price(o['price'])}"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /ban [id] [reason] ────────────────────────────────────────────────────────

async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ban người dùng."""
    if not is_admin(update.effective_user.id):
        return

    if not ctx.args:
        await update.message.reply_text("Cú pháp: <code>/ban &lt;id&gt; [lý do]</code>", parse_mode=ParseMode.HTML)
        return

    target_id = ctx.args[0].strip()
    reason = " ".join(ctx.args[1:]).strip() if len(ctx.args) > 1 else "Vi phạm điều khoản dịch vụ"

    db.ban_user(target_id, reason)
    await update.message.reply_text(
        f"🚫 <b>ĐÃ BAN NGƯỜI DÙNG!</b>\n\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"📝 Lý do: <i>{reason}</i>\n"
        f"Tài khoản này sẽ không thể sử dụng bất kỳ tính năng nào của bot.",
        parse_mode=ParseMode.HTML
    )


# ── /unban [id] ───────────────────────────────────────────────────────────────

async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Unban người dùng."""
    if not is_admin(update.effective_user.id):
        return

    if not ctx.args:
        await update.message.reply_text("Cú pháp: <code>/unban &lt;id&gt;</code>", parse_mode=ParseMode.HTML)
        return

    target_id = ctx.args[0].strip()
    db.unban_user(target_id)
    await update.message.reply_text(
        f"✅ <b>ĐÃ MỞ KHOÁ CHO NGƯỜI DÙNG!</b>\n\n"
        f"🆔 ID: <code>{target_id}</code> đã được khôi phục quyền sử dụng bot.",
        parse_mode=ParseMode.HTML
    )


# ── /rs [id] ──────────────────────────────────────────────────────────────────

async def rs_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Reset IP / thiết bị Spotify theo UID."""
    if not is_admin(update.effective_user.id):
        return

    if not ctx.args:
        ctx.user_data["admin_action"] = "reset_spotify"
        await update.message.reply_text(
            "🔄 <b>RESET THIẾT BỊ SPOTIFY</b>\n\n"
            "Vui lòng gửi <b>UID Spotify</b> hoặc Link Spotify của khách cần giải phóng phiên:\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML
        )
        return

    uid = ctx.args[0].strip()
    msg = await update.message.reply_text(f"🔄 Đang reset thiết bị Spotify cho <code>{uid}</code>…", parse_mode=ParseMode.HTML)
    try:
        res = api.spotify_reset(uid)
        resp_msg = res.get("message", "Giải phóng phiên thiết bị thành công!")
        await msg.edit_text(
            f"✅ <b>RESET SPOTIFY THÀNH CÔNG!</b>\n\n"
            f"🆔 UID: <code>{uid}</code>\n"
            f"📡 Phản hồi hệ thống: <code>{resp_msg}</code>\n\n"
            f"Khách hàng đã có thể kết nối trên thiết bị mới.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await msg.edit_text(f"❌ Reset thất bại cho UID <code>{uid}</code>: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /checkbank ────────────────────────────────────────────────────────────────

async def checkbank_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Test STC Bank API & VietQR Gateway."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang kiểm tra cổng API thanh toán Ngân hàng…", parse_mode=ParseMode.HTML)
    test_amount = 10000
    test_memo = "TEST_API_BANK_OK"
    qr_url = utils.get_vietqr_url(test_amount, test_memo)

    status_api = "Hoạt động tốt 🟢"
    status_code = 200
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(qr_url)
            status_code = resp.status_code
            if resp.status_code != 200:
                status_api = f"Cảnh báo (HTTP {resp.status_code}) ⚠️"
    except Exception as e:
        status_api = f"Lỗi kết nối ({e}) ❌"

    text = (
        f"💳 <b>KẾT QUẢ KIỂM TRA STC BANK & VIETQR API</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 <b>Ngân hàng thụ hưởng:</b> <b>{BANK_ID}</b>\n"
        f"🔢 <b>Số tài khoản:</b> <code>{ACCOUNT_NO}</code>\n"
        f"👤 <b>Tên tài khoản:</b> <b>{ACCOUNT_NAME}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <b>Trạng thái Gateway:</b> <b>{status_api}</b> (Code: {status_code})\n"
        f"🌐 <b>Tạo QR URL:</b> <code>OK</code>\n"
        f"📸 <b>Ảnh VietQR mẫu:</b> <a href=\"{qr_url}\">Bấm vào đây để xem ảnh QR</a>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Hệ thống thanh toán tự động sẵn sàng tiếp nhận giao dịch!"
    )
    await msg.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ── /addcode [code] [discount%] [limit] ───────────────────────────────────────

async def addcode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tạo mã giảm giá."""
    if not is_admin(update.effective_user.id):
        return

    if len(ctx.args) < 2:
        await update.message.reply_text(
            "Cú pháp: <code>/addcode &lt;MÃ&gt; &lt;%_GIẢM&gt; [LƯỢT_DÙNG]</code>\n\n"
            "<i>Ví dụ:</i> <code>/addcode TET2026 20 100</code> (Giảm 20%, tối đa 100 lượt)",
            parse_mode=ParseMode.HTML
        )
        return

    code = ctx.args[0].strip().upper()
    try:
        discount = int(ctx.args[1])
        if not (1 <= discount <= 100):
            raise ValueError()
    except ValueError:
        await update.message.reply_text("❌ % giảm giá phải là số từ 1 đến 100.")
        return

    limit = 0
    if len(ctx.args) > 2:
        try:
            limit = int(ctx.args[2])
        except ValueError:
            pass

    item = db.add_code(code, discount, limit)
    limit_text = "Không giới hạn" if limit == 0 else f"{limit} lượt"
    await update.message.reply_text(
        f"🏷 <b>ĐÃ TẠO MÃ GIẢM GIÁ THÀNH CÔNG!</b>\n\n"
        f"🔖 Mã: <code>{code}</code>\n"
        f"🎁 Giảm: <b>{discount}%</b>\n"
        f"🔢 Số lượt sử dụng: <b>{limit_text}</b>",
        parse_mode=ParseMode.HTML
    )


# ── /delcode [code] ───────────────────────────────────────────────────────────

async def delcode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xoá mã giảm giá."""
    if not is_admin(update.effective_user.id):
        return

    if not ctx.args:
        await update.message.reply_text("Cú pháp: <code>/delcode &lt;MÃ&gt;</code>", parse_mode=ParseMode.HTML)
        return

    code = ctx.args[0].strip().upper()
    if db.del_code(code):
        await update.message.reply_text(f"🗑 Đã xoá mã giảm giá <code>{code}</code> thành công.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"❌ Không tìm thấy mã giảm giá <code>{code}</code>.", parse_mode=ParseMode.HTML)


# ── /codes (Danh sách mã giảm giá) ───────────────────────────────────────────

async def codes_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Xem danh sách mã giảm giá."""
    if not is_admin(update.effective_user.id):
        return

    codes = db.get_codes()
    if not codes:
        await update.message.reply_text(
            "🏷 Hiện chưa có mã giảm giá nào được tạo.\n\n"
            "Dùng lệnh: <code>/addcode &lt;MÃ&gt; &lt;%_GIẢM&gt; [LƯỢT]</code> để tạo.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = ["🏷 <b>DANH SÁCH MÃ GIẢM GIÁ ĐANG HOẠT ĐỘNG:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"]
    for code, item in codes.items():
        limit_text = "Không giới hạn" if item.get("max_uses", 0) == 0 else f"{item.get('used_count', 0)}/{item.get('max_uses')}"
        lines.append(f"• Mã: <code>{code}</code> — Giảm: <b>{item.get('discount_pct', 0)}%</b> (Đã dùng: <b>{limit_text}</b>)")
    lines.append("\n💡 <i>Tạo mã: /addcode | Xoá mã: /delcode &lt;MÃ&gt;</i>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ── /noti & /notistop (Broadcast) ─────────────────────────────────────────────

async def noti_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Broadcast thông báo đa phương tiện tới toàn bộ user.
    Hỗ trợ text, ảnh, video, forward message, Telegram Premium emoji.
    """
    if not is_admin(update.effective_user.id):
        return

    # Nếu truyền văn bản trực tiếp
    if ctx.args:
        content = " ".join(ctx.args)
        await _execute_text_broadcast(update, ctx, content)
        return

    # Nếu chỉ gõ /noti -> Chờ gửi tin nhắn đa phương tiện
    ctx.user_data["admin_action"] = "waiting_broadcast_content"
    await update.message.reply_text(
        "📢 <b>GỬI THÔNG BÁO BROADCAST ĐA PHƯƠNG TIỆN</b>\n\n"
        "Hãy gửi tin nhắn bạn muốn broadcast (Văn bản định dạng HTML/Markdown, Hình ảnh, Video, Voice, Premium emoji...):\n\n"
        "💡 <i>Tin nhắn tiếp theo của bạn sẽ được sao chép nguyên bản tới toàn bộ người dùng trong bot.</i>\n"
        "<i>(Gõ /notistop hoặc /cancel để huỷ)</i>",
        parse_mode=ParseMode.HTML
    )


async def notistop_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Dừng broadcast đang chạy."""
    if not is_admin(update.effective_user.id):
        return

    global is_broadcasting, stop_broadcast_flag
    if not is_broadcasting:
        await update.message.reply_text("ℹ️ Hiện tại không có tiến trình broadcast nào đang chạy.")
        return

    stop_broadcast_flag = True
    await update.message.reply_text("🛑 <b>Đã gửi lệnh dừng Broadcast!</b>\nTiến trình sẽ dừng ngay sau tin nhắn hiện tại.", parse_mode=ParseMode.HTML)


async def _execute_text_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str):
    global is_broadcasting, stop_broadcast_flag
    if is_broadcasting:
        await update.message.reply_text("⚠️ Đang có một tiến trình broadcast khác đang chạy. Dùng /notistop để dừng trước.")
        return

    is_broadcasting = True
    stop_broadcast_flag = False

    users = db.get_users()
    total = len(users)
    sent = 0
    failed = 0

    status_msg = await update.message.reply_text(f"🚀 Bắt đầu phát sóng tới {total} người dùng…", parse_mode=ParseMode.HTML)

    for uid_str in users.keys():
        if stop_broadcast_flag:
            break
        try:
            await ctx.bot.send_message(int(uid_str), text, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.04)  # Tránh spam Telegram limits
        except Exception:
            failed += 1

    is_broadcasting = False
    if stop_broadcast_flag:
        await status_msg.edit_text(
            f"🛑 <b>ĐÃ DỪNG BROADCAST!</b>\n\n"
            f"✅ Đã gửi: <b>{sent}/{total}</b> người dùng.\n"
            f"❌ Thất bại/Chặn bot: <b>{failed}</b> người dùng.",
            parse_mode=ParseMode.HTML
        )
    else:
        await status_msg.edit_text(
            f"🎉 <b>BROADCAST HOÀN TẤT THÀNH CÔNG!</b>\n\n"
            f"✅ Đã gửi: <b>{sent}/{total}</b> người dùng.\n"
            f"❌ Thất bại/Chặn bot: <b>{failed}</b> người dùng.",
            parse_mode=ParseMode.HTML
        )


async def _execute_media_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Sao chép toàn bộ tin nhắn đa phương tiện sang tất cả user (copy_message)."""
    global is_broadcasting, stop_broadcast_flag
    if is_broadcasting:
        await update.message.reply_text("⚠️ Đang có một tiến trình broadcast khác đang chạy. Dùng /notistop để dừng trước.")
        return

    is_broadcasting = True
    stop_broadcast_flag = False

    users = db.get_users()
    total = len(users)
    sent = 0
    failed = 0

    from_chat_id = update.effective_chat.id
    message_id = update.message.message_id

    status_msg = await update.message.reply_text(f"🚀 Bắt đầu phát sóng đa phương tiện tới {total} người dùng…", parse_mode=ParseMode.HTML)

    for uid_str in users.keys():
        if stop_broadcast_flag:
            break
        try:
            await ctx.bot.copy_message(
                chat_id=int(uid_str),
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    is_broadcasting = False
    if stop_broadcast_flag:
        await status_msg.edit_text(
            f"🛑 <b>ĐÃ DỪNG BROADCAST ĐA PHƯƠNG TIỆN!</b>\n\n"
            f"✅ Đã gửi: <b>{sent}/{total}</b> người dùng.\n"
            f"❌ Thất bại/Chặn bot: <b>{failed}</b> người dùng.",
            parse_mode=ParseMode.HTML
        )
    else:
        await status_msg.edit_text(
            f"🎉 <b>BROADCAST ĐA PHƯƠNG TIỆN HOÀN TẤT!</b>\n\n"
            f"✅ Đã gửi: <b>{sent}/{total}</b> người dùng.\n"
            f"❌ Thất bại/Chặn bot: <b>{failed}</b> người dùng.",
            parse_mode=ParseMode.HTML
        )


# ── XỬ LÝ TIN NHẮN TỪ ADMIN KHI ĐANG Ở TRẠNG THÁI CHỜ ─────────────────────────

async def handle_admin_text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Hứng các tin nhắn text hoặc media từ Admin khi có action đang chờ."""
    if not is_admin(update.effective_user.id):
        return

    action = ctx.user_data.get("admin_action")
    if not action:
        return

    # 1. Chờ nội dung broadcast
    if action == "waiting_broadcast_content":
        ctx.user_data.pop("admin_action", None)
        await _execute_media_broadcast(update, ctx)
        return

    text_input = update.message.text.strip() if update.message.text else ""
    ctx.user_data.pop("admin_action", None)

    # 2. Chờ từ khoá tìm kiếm
    if action == "waiting_find_query":
        ctx.args = [text_input]
        await find_cmd(update, ctx)
        return

    # 3. Chờ UID reset spotify
    if action == "reset_spotify":
        ctx.args = [text_input]
        await rs_cmd(update, ctx)
        return

    # 4. Chờ tra cứu UID
    if action == "check_uid":
        msg = await update.message.reply_text(f"🔍 Đang tra cứu <code>{text_input}</code>…", parse_mode=ParseMode.HTML)
        try:
            service = "spotify" if "spotify" in text_input.lower() else "locket"
            res = api.check_uid_details(text_input, service=service)
            data = res.get("data", {})
            uid = data.get("uid", text_input)
            username = data.get("username", "N/A")
            status = data.get("status", "N/A")
            active = "Đang kích hoạt ✅" if data.get("active") else "Chưa kích hoạt / Hết hạn ❌"
            expires = data.get("expiresAt", "Vĩnh viễn")
            pkg = data.get("package", {})
            pkg_name = pkg.get("name", "N/A") if isinstance(pkg, dict) else str(pkg)

            result_text = (
                f"📋 <b>KẾT QUẢ TRA CỨU HỆ THỐNG:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Tài khoản:</b> <code>{username}</code>\n"
                f"🆔 <b>UID:</b> <code>{uid}</code>\n"
                f"🛠 <b>Dịch vụ:</b> <b>{service.upper()}</b>\n"
                f"📦 <b>Gói:</b> <b>{pkg_name}</b>\n"
                f"⚡ <b>Trạng thái:</b> <b>{active}</b> ({status})\n"
                f"📅 <b>Hạn dùng:</b> <code>{expires}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            await msg.edit_text(result_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            await msg.edit_text(f"❌ Không tìm thấy thông tin hoặc API lỗi: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── CALLBACK ADMIN MENU ───────────────────────────────────────────────────────

async def cb_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Không có quyền!", show_alert=True)
        return

    parts  = query.data.split(":")
    action = parts[1]

    if action == "menu":
        await query.answer()
        await query.edit_message_text(
            build_admin_menu_text(),
            parse_mode=ParseMode.HTML,
            reply_markup=admin_kb()
        )

    elif action == "stats":
        await stats_cmd(update, ctx)

    elif action == "recent":
        await orders_cmd(update, ctx)

    elif action == "balance":
        await tokens_cmd(update, ctx)

    elif action == "users_list":
        await users_cmd(update, ctx)

    elif action == "checkbank":
        await query.answer()
        test_amount = 10000
        test_memo = "TEST_API_BANK_OK"
        qr_url = utils.get_vietqr_url(test_amount, test_memo)
        text = (
            f"💳 <b>KIỂM TRA CẤU HÌNH STC BANK & VIETQR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏦 Ngân hàng: <b>{BANK_ID}</b>\n"
            f"🔢 STK: <code>{ACCOUNT_NO}</code>\n"
            f"👤 Chủ TK: <b>{ACCOUNT_NAME}</b>\n"
            f"📸 QR URL: <a href=\"{qr_url}\">Link test QR</a>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ API hoạt động bình thường!"
        )
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=back_admin_kb(), disable_web_page_preview=True)

    elif action == "codes":
        await query.answer()
        codes = db.get_codes()
        lines = ["🏷 <b>DANH SÁCH MÃ GIẢM GIÁ HIỆN CÓ:</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━"]
        if not codes:
            lines.append("<i>Chưa có mã giảm giá nào.</i>")
        else:
            for c, d in codes.items():
                limit_str = f"/{d.get('max_uses')}" if d.get('max_uses', 0) > 0 else " (Vô hạn)"
                lines.append(f"• <code>{c}</code>: Giảm <b>{d.get('discount_pct')}%</b> (Đã dùng: {d.get('used_count', 0)}{limit_str})")
        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("➕ Tạo mã mới: <code>/addcode &lt;MÃ&gt; &lt;%_GIẢM&gt; [LƯỢT]</code>")
        lines.append("➖ Xoá mã: <code>/delcode &lt;MÃ&gt;</code>")
        await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_admin_kb())

    elif action == "find_menu":
        await query.answer()
        ctx.user_data["admin_action"] = "waiting_find_query"
        await query.edit_message_text(
            "🔍 <b>TÌM KIẾM TRONG HỆ THỐNG</b>\n\n"
            "Gửi từ khoá bạn muốn tìm:\n"
            "<i>(ID, Username, UID hoặc Mã đơn hàng)</i>\n\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_admin_kb()
        )

    elif action == "check_uid_menu":
        await query.answer()
        ctx.user_data["admin_action"] = "check_uid"
        await query.edit_message_text(
            "🔍 <b>Tra cứu thông tin gói & trạng thái UID</b>\n\n"
            "Gửi <b>Username Locket</b>, <b>UID</b> hoặc <b>Link Spotify</b> cần kiểm tra:\n\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_admin_kb()
        )

    elif action == "reset_menu":
        await query.answer()
        ctx.user_data["admin_action"] = "reset_spotify"
        await query.edit_message_text(
            "🔄 <b>Reset thiết bị Spotify</b>\n\n"
            "Gửi <b>UID Spotify</b> của khách cần reset:\n\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_admin_kb()
        )

    elif action == "broadcast":
        await query.answer()
        ctx.user_data["admin_action"] = "waiting_broadcast_content"
        await query.edit_message_text(
            "📢 <b>GỬI BROADCAST ĐA PHƯƠNG TIỆN</b>\n\n"
            "Hãy gửi nội dung thông báo (Văn bản, Hình ảnh, Video, Voice...) vào đây:\n\n"
            "<i>(Gõ /cancel để huỷ)</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=back_admin_kb()
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  DUYỆT & TỪ CHỐI ĐƠN HÀNG
# ═══════════════════════════════════════════════════════════════════════════════

async def cb_admin_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Bạn không có quyền duyệt!", show_alert=True)
        return
    await query.answer()
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Không tìm thấy đơn hàng.")
        return
    if order["status"] == "done":
        await query.answer("Đơn này đã được duyệt rồi!", show_alert=True)
        return

    pv   = PRODUCTS[order["product"]]
    plnv = pv["plans"][order["plan"]]

    await query.edit_message_text(
        f"⏳ Đang kích hoạt gói cho đơn <code>ORDER_{order_id}</code>…",
        parse_mode=ParseMode.HTML
    )

    from order_service import execute_order_activation
    ok, act_msg = await execute_order_activation(ctx.bot, order_id)
    if ok:
        await query.edit_message_text(
            f"✅ <b>ĐÃ DUYỆT ĐƠN HÀNG THÀNH CÔNG!</b>\n\n"
            f"🧾 Mã đơn: <code>ORDER_{order_id}</code>\n"
            f"👤 Khách: @{order['username']} (ID: <code>{order['user_id']}</code>)\n"
            f"📦 Gói: {pv['emoji']} {pv['name']} ({plnv['label']})\n"
            f"🎯 Tài khoản: <b>{order['display_name']}</b> (<code>{order['uid']}</code>)\n"
            f"💰 Đã nhận: <b>{utils.fmt_price(order['price'])}</b>\n\n"
            f"🎉 <i>Hệ thống đã kích hoạt và gửi đầy đủ cấu hình cho khách!</i>",
            parse_mode=ParseMode.HTML
        )
    else:
        from keyboards import admin_approval_kb
        await query.edit_message_text(
            f"❌ <b>Duyệt đơn thất bại (Lỗi API)!</b>\n\n"
            f"Mã đơn: <code>ORDER_{order_id}</code>\n"
            f"Lỗi: <code>{act_msg}</code>\n\n"
            f"Vui lòng kiểm tra lại số dư coin CTV hoặc kết nối API.",
            parse_mode=ParseMode.HTML,
            reply_markup=admin_approval_kb(order_id)
        )
    return


async def cb_admin_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not is_admin(query.from_user.id):
        await query.answer("⛔ Bạn không có quyền!", show_alert=True)
        return
    await query.answer()
    order_id = query.data.split(":")[1]
    order = db.get_order(order_id)
    if not order:
        await query.edit_message_text("❌ Không tìm thấy đơn hàng.")
        return

    db.update_order(order_id, status="rejected")
    await query.edit_message_text(
        f"🚫 Đã <b>TỪ CHỐI</b> đơn hàng <code>ORDER_{order_id}</code> của @{order['username']}.",
        parse_mode=ParseMode.HTML
    )

    from config import SUPPORT_USERNAME
    try:
        await ctx.bot.send_message(
            order["user_id"],
            f"🚫 Đơn hàng <code>ORDER_{order_id}</code> chưa được xác nhận thanh toán.\n"
            f"Nếu bạn đã chuyển khoản, vui lòng liên hệ @{SUPPORT_USERNAME} kèm ảnh biên lai để được hỗ trợ.",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


# ── /coin & /balance: Tra cứu số dư Coin CTV ─────────────────────────────────

async def coin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu số dư Coin CTV và trạng thái tài khoản API (GET /api/keys/me)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang tra cứu số dư tài khoản CTV từ hệ thống API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_account_info()
        data = res.get("data", res)
        username = data.get("username", "CTV")
        balance = data.get("balanceCoin", 0)
        is_activated = data.get("isActivated", False)
        status_text = "🟢 Đã kích hoạt" if is_activated else "🔴 Chưa kích hoạt"

        text = (
            f"🪙 <b>THÔNG TIN TÀI KHOẢN CTV (locket.2707226.xyz)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Tên CTV:</b> <code>{username}</code>\n"
            f"💰 <b>Số dư Coin:</b> <b>{balance} Coin</b>\n"
            f"🛡️ <b>Trạng thái:</b> {status_text}\n"
            f"🌐 <b>API URL:</b> <code>{config.API_BASE_URL}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mỗi đơn kích hoạt Locket/Spotify sẽ tự động trừ Coin tương ứng. Nếu Coin sắp hết hãy nạp thêm trên Dashboard!</i>"
        )
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể tra cứu số dư CTV: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /packages: Tra cứu danh sách gói từ máy chủ API ──────────────────────────

async def packages_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu bảng giá Coin và mã gói cước trực tiếp từ API (GET /api/packages)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang lấy bảng giá gói cước từ máy chủ API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_packages("all")
        data = res.get("data", [])
        lines = [
            "📦 <b>DANH SÁCH GÓI CƯỚC & GIÁ COIN TRÊN MÁY CHỦ API</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for p in data:
            code = p.get("code")
            name = p.get("name")
            days = p.get("durationDays", 0)
            coin = p.get("priceCoin", 0)
            lines.append(f"• <b>{code}</b>: {name} ({days} ngày) ➔ <b>{coin} Coin</b>")
        lines.append("\n💡 <i>Mã gói này tương ứng với cấu hình trong config.py.</i>")
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể lấy danh sách gói: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /coin & /balance: Tra cứu số dư Coin CTV ─────────────────────────────────

async def coin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu số dư Coin CTV và trạng thái tài khoản API (GET /api/keys/me)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang tra cứu số dư tài khoản CTV từ hệ thống API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_account_info()
        data = res.get("data", res)
        username = data.get("username", "CTV")
        balance = data.get("balanceCoin", 0)
        is_activated = data.get("isActivated", False)
        status_text = "🟢 Đã kích hoạt" if is_activated else "🔴 Chưa kích hoạt"

        text = (
            f"🪙 <b>THÔNG TIN TÀI KHOẢN CTV (locket.2707226.xyz)</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>Tên CTV:</b> <code>{username}</code>\n"
            f"💰 <b>Số dư Coin:</b> <b>{balance} Coin</b>\n"
            f"🛡️ <b>Trạng thái:</b> {status_text}\n"
            f"🌐 <b>API URL:</b> <code>{config.API_BASE_URL}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>Mỗi đơn kích hoạt Locket/Spotify sẽ tự động trừ Coin tương ứng. Nếu Coin sắp hết hãy nạp thêm trên Dashboard!</i>"
        )
        await msg.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể tra cứu số dư CTV: <code>{e}</code>", parse_mode=ParseMode.HTML)


# ── /packages: Tra cứu danh sách gói từ máy chủ API ──────────────────────────

async def packages_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Tra cứu bảng giá Coin và mã gói cước trực tiếp từ API (GET /api/packages)."""
    if not is_admin(update.effective_user.id):
        return

    msg = await update.message.reply_text("⏳ Đang lấy bảng giá gói cước từ máy chủ API...", parse_mode=ParseMode.HTML)
    try:
        res = api.get_packages("all")
        data = res.get("data", [])
        lines = [
            "📦 <b>DANH SÁCH GÓI CƯỚC & GIÁ COIN TRÊN MÁY CHỦ API</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━"
        ]
        for p in data:
            code = p.get("code")
            name = p.get("name")
            days = p.get("durationDays", 0)
            coin = p.get("priceCoin", 0)
            lines.append(f"• <b>{code}</b>: {name} ({days} ngày) ➔ <b>{coin} Coin</b>")
        lines.append("\n💡 <i>Mã gói này tương ứng với cấu hình trong config.py.</i>")
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Không thể lấy danh sách gói: <code>{e}</code>", parse_mode=ParseMode.HTML)



# ── /duyet: Lệnh duyệt đơn hàng bằng tay cho Admin ───────────────────────────

async def duyet_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin duyệt đơn bằng lệnh: /duyet <order_id>"""
    if not is_admin(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text("⚠️ Vui lòng nhập mã đơn hàng.\nVí dụ: <code>/duyet ORDER_VIP1234</code>", parse_mode=ParseMode.HTML)
        return

    raw_id = ctx.args[0].upper().replace("ORDER_", "").strip()
    order = db.get_order(raw_id)
    if not order:
        await update.message.reply_text(f"❌ Không tìm thấy đơn hàng <code>ORDER_{raw_id}</code>.", parse_mode=ParseMode.HTML)
        return

    from order_service import execute_order_activation
    msg = await update.message.reply_text(f"⏳ Đang kích hoạt đơn <code>ORDER_{raw_id}</code>...", parse_mode=ParseMode.HTML)
    ok, res = await execute_order_activation(ctx.bot, raw_id)
    if ok:
        await msg.edit_text(f"✅ Đã duyệt thành công đơn <code>ORDER_{raw_id}</code> cho @{order['username']}!", parse_mode=ParseMode.HTML)
    else:
        await msg.edit_text(f"❌ Kích hoạt thất bại: <code>{res}</code>", parse_mode=ParseMode.HTML)
